from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.provenance import (
    PRIVATE_MANIFEST_SCHEMA,
    PUBLIC_MANIFEST_SCHEMA,
    STAGE_SCHEMA,
    ProvenanceError,
    PublicManifestError,
    ResumeValidationError,
    StageDigests,
    StageRecord,
    build_private_manifest,
    build_public_manifest,
    canonical_json_bytes,
    load_stage_record,
    private_manifest_sensitive_values,
    resume_is_valid,
    semantic_digest,
    validate_public_manifest,
    validate_resume,
    write_stage_record,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


def windows_fixture_path(*parts: str) -> str:
    return "X:" + "\\" + "\\".join(parts)


class ProvenanceTests(unittest.TestCase):
    def digests(self, **updates: object) -> StageDigests:
        values: dict[str, object] = {
            "code": digest("a"),
            "config": digest("b"),
            "tools": {"synthetic-tool": digest("c")},
            "inputs": {"synthetic-input": digest("d")},
        }
        values.update(updates)
        return StageDigests(**values)  # type: ignore[arg-type]

    def success(self, digests: StageDigests | None = None) -> StageRecord:
        return StageRecord.success(
            stage="synthetic_qc",
            started_at="2026-08-26T12:00:00Z",
            finished_at="2026-08-26T12:00:01Z",
            command=["synthetic-tool", "--offline", "fixture.json"],
            digests=digests or self.digests(),
            semantic_validations={"schema_valid": True},
            output_digests={"summary": digest("e")},
        )

    def public_manifest(self, **updates: object) -> dict[str, object]:
        values: dict[str, object] = {
            "code_revision": "0123456789abcdef0123456789abcdef01234567",
            "code_digest": digest("1"),
            "tools": {
                "synthetic-tool": {"version": "1.2.3", "digest": digest("2")}
            },
            "public_references": {"reference-build": "GRCh38.p14"},
            "settings": {"threads": 2, "network": "disabled"},
            "aggregate_methods": ["aggregate synthetic quality checks"],
        }
        values.update(updates)
        return build_public_manifest(**values)  # type: ignore[arg-type]

    def test_semantic_hash_ignores_mapping_order_and_json_whitespace(self) -> None:
        first = {"beta": [1, True, None], "alpha": {"x": "caf\u00e9"}}
        second = json.loads(
            '{\n  "alpha": {"x": "caf\\u00e9"},\n  "beta": [1, true, null]\n}'
        )
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        self.assertEqual(semantic_digest(first), semantic_digest(second))
        self.assertNotEqual(semantic_digest(first), semantic_digest({"beta": [], "alpha": {}}))

    def test_semantic_hash_normalises_unicode_and_rejects_non_json_values(self) -> None:
        self.assertEqual(semantic_digest("e\u0301"), semantic_digest("\u00e9"))
        with self.assertRaisesRegex(ProvenanceError, "non-finite"):
            semantic_digest({"unsafe": float("nan")})
        with self.assertRaisesRegex(ProvenanceError, "outside the canonical JSON domain"):
            semantic_digest({"not-json": {1, 2}})

    def test_success_stage_json_is_atomic_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "run", "stage.json")
            written = write_stage_record(path, self.success())
            self.assertEqual(written, path)
            self.assertEqual(load_stage_record(path), self.success())
            self.assertFalse(list(path.parent.glob(".stage.*.tmp")))
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["schema"], STAGE_SCHEMA)
            self.assertEqual(raw["status"], "success")
            self.assertEqual(raw["exit_code"], 0)
            self.assertIsNone(raw["error"])

    def test_failed_atomic_replace_preserves_previous_stage_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "stage.json")
            original = b'{"prior":"record"}\n'
            path.write_bytes(original)
            with patch("mva_hackathon.provenance.os.replace", side_effect=OSError("fixture")):
                with self.assertRaisesRegex(OSError, "fixture"):
                    write_stage_record(path, self.success())
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(list(path.parent.glob(".stage.*.tmp")))

    def test_failure_stage_json_has_a_distinct_valid_terminal_schema(self) -> None:
        record = StageRecord.failure(
            stage="synthetic_qc",
            started_at="2026-08-26T12:00:00Z",
            finished_at="2026-08-26T12:00:01Z",
            exit_code=17,
            command=["synthetic-tool", "--offline", "fixture.json"],
            digests=self.digests(),
            semantic_validations={"schema_valid": False},
            error="synthetic validation failed",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "stage.json")
            write_stage_record(path, record)
            loaded = load_stage_record(path)
        self.assertEqual(loaded.status, "failure")
        self.assertEqual(loaded.exit_code, 17)
        self.assertEqual(loaded.error, "synthetic validation failed")
        self.assertEqual(dict(loaded.output_digests), {})
        semantic_failure = StageRecord.failure(
            stage="synthetic_qc",
            started_at="2026-08-26T12:00:00Z",
            finished_at="2026-08-26T12:00:01Z",
            exit_code=0,
            command=["synthetic-tool"],
            digests=self.digests(),
            semantic_validations={"schema_valid": False},
            error="synthetic semantic validation failed",
        )
        self.assertEqual(semantic_failure.exit_code, 0)
        with self.assertRaisesRegex(ProvenanceError, "failed semantic validation"):
            StageRecord.failure(
                stage="synthetic_qc",
                started_at="2026-08-26T12:00:00Z",
                finished_at="2026-08-26T12:00:01Z",
                exit_code=0,
                command=["synthetic-tool"],
                digests=self.digests(),
                semantic_validations={},
                error="failed",
            )

    def test_success_requires_semantic_validation_and_output_digest(self) -> None:
        with self.assertRaisesRegex(ProvenanceError, "passing semantic validation"):
            StageRecord.success(
                stage="synthetic_qc",
                started_at="2026-08-26T12:00:00Z",
                finished_at="2026-08-26T12:00:01Z",
                command=["synthetic-tool"],
                digests=self.digests(),
                semantic_validations={},
                output_digests={"summary": digest("e")},
            )
        with self.assertRaisesRegex(ProvenanceError, "at least one digest"):
            StageRecord.success(
                stage="synthetic_qc",
                started_at="2026-08-26T12:00:00Z",
                finished_at="2026-08-26T12:00:01Z",
                command=["synthetic-tool"],
                digests=self.digests(),
                semantic_validations={"schema_valid": True},
                output_digests={},
            )

    def test_resume_requires_exact_code_config_tool_and_input_digests(self) -> None:
        record = self.success()
        self.assertIs(validate_resume(record, self.digests()), record)
        mismatch_cases = {
            "code": self.digests(code=digest("f")),
            "config": self.digests(config=digest("f")),
            "tools": self.digests(tools={"synthetic-tool": digest("f")}),
            "inputs": self.digests(inputs={"synthetic-input": digest("f")}),
        }
        for field, changed in mismatch_cases.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(ResumeValidationError, field):
                    validate_resume(record, changed)
                self.assertFalse(resume_is_valid(record, changed))

    def test_resume_rejects_failure_and_incomplete_digest_schema(self) -> None:
        failed = StageRecord.failure(
            stage="synthetic_qc",
            started_at="2026-08-26T12:00:00Z",
            finished_at="2026-08-26T12:00:01Z",
            exit_code=1,
            command=["synthetic-tool"],
            digests=self.digests(),
            semantic_validations={},
            error="synthetic failure",
        )
        with self.assertRaisesRegex(ResumeValidationError, "did not succeed"):
            validate_resume(failed, self.digests())
        with self.assertRaisesRegex(ProvenanceError, "fields must be exactly"):
            validate_resume(
                self.success(),
                {"code": digest("a"), "config": digest("b"), "tools": {}},
            )

    def test_public_and_private_manifests_have_disjoint_schemas(self) -> None:
        private = build_private_manifest(
            controlled_inputs={
                "synthetic-source": {
                    "path": windows_fixture_path("offline-fixtures", "child_fixture.vcf.gz"),
                    "digest": digest("9"),
                }
            },
            stage_records={"synthetic-qc": digest("8")},
        )
        public = self.public_manifest()
        self.assertEqual(private["schema"], PRIVATE_MANIFEST_SCHEMA)
        self.assertEqual(public["schema"], PUBLIC_MANIFEST_SCHEMA)
        self.assertIn("controlled_inputs", private)
        self.assertNotIn("controlled_inputs", public)
        self.assertNotIn("code", private)
        self.assertNotIn("stage_records", public)

    def test_public_manifest_rejects_private_fields_paths_and_filenames(self) -> None:
        base = self.public_manifest()
        for settings, message in (
            ({"path": "synthetic.txt"}, "private-only field"),
            ({"cache": windows_fixture_path("private", "fixture.txt")}, "paths are forbidden"),
            ({"source": "child_fixture.vcf.gz"}, "filename is forbidden"),
        ):
            with self.subTest(settings=settings):
                candidate = dict(base)
                candidate["settings"] = settings
                with self.assertRaisesRegex(PublicManifestError, message):
                    validate_public_manifest(candidate)

    def test_public_manifest_rejects_hashes_outside_allowlisted_digest_fields(self) -> None:
        base = self.public_manifest()
        base["settings"] = {"source_fingerprint": digest("7")}
        with self.assertRaisesRegex(PublicManifestError, "hash-like content"):
            validate_public_manifest(base)

    def test_known_controlled_values_are_rejected_even_in_allowed_digest_fields(self) -> None:
        private = build_private_manifest(
            controlled_inputs={
                "synthetic-source": {
                    "path": windows_fixture_path("offline-fixtures", "child_fixture.vcf.gz"),
                    "digest": digest("9"),
                }
            },
            stage_records={"synthetic-qc": digest("8")},
        )
        forbidden = private_manifest_sensitive_values(private)
        with self.assertRaisesRegex(PublicManifestError, "controlled filename"):
            self.public_manifest(
                settings={"description": "derived from child_fixture.vcf.gz"},
                controlled_values=forbidden,
            )
        with self.assertRaisesRegex(PublicManifestError, "controlled filename"):
            self.public_manifest(code_digest=digest("9"), controlled_values=forbidden)

    def test_public_manifest_allows_only_declared_code_and_tool_hashes(self) -> None:
        manifest = self.public_manifest()
        self.assertEqual(manifest["code"]["digest"], digest("1"))  # type: ignore[index]
        self.assertEqual(
            manifest["tools"]["synthetic-tool"]["digest"],  # type: ignore[index]
            digest("2"),
        )


if __name__ == "__main__":
    unittest.main()
