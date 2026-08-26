from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.freeze import (
    COMMITMENT_SCHEME,
    PUBLIC_COMMITMENT_SCHEMA,
    SCHEMA_VERSION,
    FreezeError,
    build_manifest,
    build_public_commitment_manifest,
    verify_manifest,
    write_manifest,
)
from mva_hackathon.submission import REQUIRED_FIELDS

COMMIT = "d27c33953ecb0cfd7fa316c7cd93ff0ffb05cc1d"
NONCE = bytes(range(16))


class FreezeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.public = self.root / "public"
        self.private = self.root / "private"
        self.public.mkdir()
        self.private.mkdir()

        self.report = self._public_file(
            "report/methods.md", b"Synthetic Track 1 methods report.\n"
        )
        self.config = self._public_file(
            "config/calibration.json", b'{"method":"synthetic-isotonic","version":1}\n'
        )
        self.config_alt = self._public_file(
            "config/calibration-alt.json",
            b'{"method":"synthetic-logistic","version":1}\n',
        )
        self.code = self._public_file(
            "code/pipeline.py", b"def rank_synthetic(rows):\n    return rows\n"
        )
        self.reference = self._public_file(
            "reference/resources.lock", b"synthetic-reference==1\n"
        )
        self.benchmark = self._public_file(
            "benchmark/heldout.json", b'{"synthetic_score":0.75}\n'
        )
        self.benchmark_alt = self._public_file(
            "benchmark/heldout-alt.json", b'{"synthetic_score":0.70}\n'
        )
        self.raw = self._private_file(
            "inputs/synthetic-input.bin", b"strictly synthetic raw input bytes"
        )
        self.raw_without_commitment = self._private_file(
            "inputs/synthetic-index.bin", b"strictly synthetic index bytes"
        )

    def _public_file(self, relative: str, payload: bytes) -> Path:
        path = self.public / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def _private_file(self, relative: str, payload: bytes) -> Path:
        path = self.private / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def csv(self, name: str, position: int) -> Path:
        path = self.public / "submissions" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "proband_id": "PROBAND01",
            "chrom_1": "chr3",
            "pos_1": position,
            "ref_1": "A",
            "alt_1": "G",
            "chrom_2": "chr3",
            "pos_2": position + 101,
            "ref_2": "C",
            "alt_2": "T",
            "epcr": 0.9,
            "finding_type": "primary",
            "notes": "synthetic fixture",
        }
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REQUIRED_FIELDS)
            writer.writeheader()
            writer.writerow(row)
        return path

    def artifacts(self) -> dict[str, list[Path]]:
        return {
            "report": [self.report],
            "config": [self.config, self.config_alt],
            "code": [self.code],
            "reference": [self.reference],
            "benchmark": [self.benchmark, self.benchmark_alt],
        }

    @staticmethod
    def ablation(
        baseline: str, variant: str, direction: str = "lower"
    ) -> dict[str, str]:
        return {
            "ablation_id": "without-phenotype-rerank",
            "baseline": baseline,
            "variant": variant,
            "metric": "official_track1_score",
            "expected_direction": direction,
            "rationale": "Phenotype reranking is expected to improve candidate ordering.",
        }

    def manifest(
        self,
        files: list[Path],
        *,
        upload_order: list[str] | None = None,
        direction: str = "lower",
        artifacts: dict[str, list[Path]] | None = None,
        method_ids: dict[str, str] | None = None,
        calibrations: dict[str, dict[str, str]] | None = None,
        champion_method_id: str | None = None,
        nonces: dict[str, bytes] | None = None,
    ) -> dict[str, object]:
        rationales = {
            path.name: f"Predeclared synthetic method represented by {path.name}."
            for path in files
        }
        expected_ablations = (
            [self.ablation(files[0].name, files[1].name, direction)]
            if len(files) > 1
            else []
        )
        frozen_method_ids = (
            method_ids
            if method_ids is not None
            else {
                path.name: "S1_CHAMPION" if index == 0 else f"S{index + 1}_ABLATION"
                for index, path in enumerate(files)
            }
        )
        fitted_calibrations = calibrations if calibrations is not None else {
            method_id: {
                "calibration_id": f"{method_id.lower()}-calibration-v1",
                "method": (
                    "Isotonic regression on a synthetic held-out benchmark"
                    if index == 0
                    else "Logistic calibration on a synthetic held-out benchmark"
                ),
                "config_artifact": (
                    "config/calibration.json"
                    if index == 0
                    else "config/calibration-alt.json"
                ),
                "benchmark_artifact": (
                    "benchmark/heldout.json"
                    if index == 0
                    else "benchmark/heldout-alt.json"
                ),
            }
            for index, method_id in enumerate(frozen_method_ids.values())
        }
        return build_manifest(
            files,
            rationales,
            official_space_commit=COMMIT,
            created_at_utc="2026-08-26T14:00:00+00:00",
            artifact_root=self.public,
            artifacts=artifacts or self.artifacts(),
            expected_ablations=expected_ablations,
            method_ids=frozen_method_ids,
            calibrations=fitted_calibrations,
            champion_method_id=champion_method_id
            or frozen_method_ids[files[0].name],
            upload_order=(
                upload_order if upload_order is not None else [path.name for path in files]
            ),
            private_raw_root=self.private,
            private_raw_paths={
                "synthetic-input": self.raw,
                "synthetic-index": self.raw_without_commitment,
            },
            public_commitment_nonces=nonces
            if nonces is not None
            else {"synthetic-input": NONCE},
        )

    def write_and_verify(self, manifest: dict[str, object]) -> Path:
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        verify_manifest(path, self.public, private_raw_root=self.private)
        return path

    def test_complete_v2_freeze_and_verification(self) -> None:
        files = [self.csv("full.csv", 10_001), self.csv("ablated.csv", 20_001)]
        manifest = self.manifest(files, upload_order=["full.csv", "ablated.csv"])
        self.write_and_verify(manifest)

        self.assertEqual(manifest["schema"], SCHEMA_VERSION)
        self.assertEqual(
            set(manifest["artifacts"]),  # type: ignore[arg-type]
            {"report", "config", "code", "reference", "benchmark"},
        )
        self.assertEqual(
            [entry["filename"] for entry in manifest["upload_order"]],  # type: ignore[index]
            ["full.csv", "ablated.csv"],
        )
        self.assertEqual(
            manifest["expected_ablations"][0]["expected_direction"],  # type: ignore[index]
            "lower",
        )
        self.assertRegex(
            manifest["calibrations"][0]["identity_sha256"],  # type: ignore[index]
            r"^[0-9a-f]{64}$",
        )
        self.assertNotEqual(
            manifest["calibrations"][0]["identity_sha256"],  # type: ignore[index]
            manifest["calibrations"][1]["identity_sha256"],  # type: ignore[index]
        )
        self.assertEqual(manifest["champion_method_id"], "S1_CHAMPION")
        self.assertEqual(
            manifest["upload_order"][0]["method_id"],  # type: ignore[index]
            "S1_CHAMPION",
        )

    def test_identical_csvs_are_marked_as_converged_and_uploaded_once(self) -> None:
        first = self.csv("full.csv", 10_001)
        second = self.public / "submissions" / "alternate.csv"
        second.write_bytes(first.read_bytes())

        manifest = self.manifest(
            [first, second],
            upload_order=["full.csv"],
            direction="no_change",
        )
        self.write_and_verify(manifest)

        submissions = manifest["submissions"]
        self.assertTrue(all(entry["converged_output"] for entry in submissions))  # type: ignore[union-attr]
        self.assertEqual(submissions[0]["upload_slot"], 1)  # type: ignore[index]
        self.assertIsNone(submissions[1]["upload_slot"])  # type: ignore[index]
        self.assertEqual(len(manifest["convergence_groups"]), 1)  # type: ignore[arg-type]
        self.assertTrue(
            manifest["expected_ablations"][0]["outputs_converged"]  # type: ignore[index]
        )
        self.assertEqual(len(manifest["upload_order"]), 1)  # type: ignore[arg-type]

    def test_duplicate_csvs_cannot_waste_two_upload_slots(self) -> None:
        first = self.csv("one.csv", 10_001)
        second = self.public / "submissions" / "two.csv"
        second.write_bytes(first.read_bytes())
        with self.assertRaisesRegex(FreezeError, "waste a slot"):
            self.manifest(
                [first, second],
                upload_order=["one.csv", "two.csv"],
                direction="no_change",
            )

    def test_upload_order_must_cover_every_distinct_output(self) -> None:
        files = [self.csv("one.csv", 10_001), self.csv("two.csv", 20_001)]
        with self.assertRaisesRegex(FreezeError, "exactly one representative"):
            self.manifest(files, upload_order=["one.csv"])

    def test_identical_output_ablation_must_expect_no_change(self) -> None:
        first = self.csv("one.csv", 10_001)
        second = self.public / "submissions" / "two.csv"
        second.write_bytes(first.read_bytes())
        with self.assertRaisesRegex(FreezeError, "must expect no_change"):
            self.manifest([first, second], upload_order=["one.csv"], direction="lower")

    def test_private_hash_and_nonce_prefixed_commitment_are_exact(self) -> None:
        manifest = self.manifest([self.csv("one.csv", 10_001)])
        raw_entries = {
            entry["artifact_id"]: entry
            for entry in manifest["private_raw_artifacts"]  # type: ignore[union-attr]
        }
        committed = raw_entries["synthetic-input"]
        self.assertEqual(
            committed["private_sha256"],
            hashlib.sha256(self.raw.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            committed["public_commitment"]["digest"],  # type: ignore[index]
            hashlib.sha256(NONCE + self.raw.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            committed["public_commitment"]["scheme"],  # type: ignore[index]
            COMMITMENT_SCHEME,
        )
        self.assertNotIn("public_commitment", raw_entries["synthetic-index"])

    def test_public_projection_hides_path_raw_hash_and_nonce(self) -> None:
        manifest = self.manifest([self.csv("one.csv", 10_001)])
        public = build_public_commitment_manifest(manifest)
        rendered = json.dumps(public, sort_keys=True)

        self.assertEqual(public["schema"], PUBLIC_COMMITMENT_SCHEMA)
        self.assertEqual(len(public["commitments"]), 1)  # type: ignore[arg-type]
        self.assertNotIn("synthetic-input.bin", rendered)
        self.assertNotIn(hashlib.sha256(self.raw.read_bytes()).hexdigest(), rendered)
        self.assertNotIn(NONCE.hex(), rendered)
        self.assertIn(hashlib.sha256(NONCE + self.raw.read_bytes()).hexdigest(), rendered)

    def test_reused_commitment_nonce_is_rejected(self) -> None:
        with self.assertRaisesRegex(FreezeError, "unique nonce"):
            self.manifest(
                [self.csv("one.csv", 10_001)],
                nonces={
                    "synthetic-input": NONCE,
                    "synthetic-index": NONCE,
                },
            )

    def test_changed_csv_fails_verification(self) -> None:
        candidate = self.csv("one.csv", 10_001)
        path = self.write_and_verify(self.manifest([candidate]))
        payload = candidate.read_bytes()
        candidate.write_bytes(payload[:-1] + (b"\r" if payload[-1:] != b"\r" else b"\n"))
        with self.assertRaisesRegex(FreezeError, "CSV hash changed"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_changed_evidence_artifact_fails_verification(self) -> None:
        path = self.write_and_verify(self.manifest([self.csv("one.csv", 10_001)]))
        payload = self.report.read_bytes()
        self.report.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
        with self.assertRaisesRegex(FreezeError, "report artifact 1 hash changed"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_changed_private_raw_fails_verification(self) -> None:
        path = self.write_and_verify(self.manifest([self.csv("one.csv", 10_001)]))
        payload = self.raw.read_bytes()
        self.raw.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
        with self.assertRaisesRegex(FreezeError, "private raw artifact synthetic-input hash changed"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_private_root_is_required_for_full_verification(self) -> None:
        path = self.write_and_verify(self.manifest([self.csv("one.csv", 10_001)]))
        with self.assertRaisesRegex(FreezeError, "private_raw_root is required"):
            verify_manifest(path, self.public)

    def test_tampered_upload_order_is_detected(self) -> None:
        files = [self.csv("one.csv", 10_001), self.csv("two.csv", 20_001)]
        manifest = self.manifest(files)
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["upload_order"].reverse()
        path.write_text(json.dumps(stored), encoding="utf-8")
        with self.assertRaisesRegex(FreezeError, "upload order is malformed|annotations changed"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_calibration_identity_changes_when_linked_config_changes(self) -> None:
        file = self.csv("one.csv", 10_001)
        first = self.manifest([file])
        old_identity = first["calibrations"][0]["identity_sha256"]  # type: ignore[index]
        payload = self.config.read_bytes()
        self.config.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
        second = self.manifest([file])
        self.assertNotEqual(
            old_identity,
            second["calibrations"][0]["identity_sha256"],  # type: ignore[index]
        )

    def test_calibration_must_link_correct_artifact_roles(self) -> None:
        with self.assertRaisesRegex(FreezeError, "config_artifact"):
            self.manifest(
                [self.csv("one.csv", 10_001)],
                calibrations={
                    "S1_CHAMPION": {
                        "calibration_id": "synthetic-isotonic-v1",
                        "method": "Isotonic regression on a synthetic benchmark",
                        "config_artifact": "report/methods.md",
                        "benchmark_artifact": "benchmark/heldout.json",
                    },
                },
            )

    def test_every_method_requires_its_own_fitted_calibration(self) -> None:
        files = [self.csv("one.csv", 10_001), self.csv("two.csv", 20_001)]
        with self.assertRaisesRegex(FreezeError, "exactly one fitted identity"):
            self.manifest(
                files,
                calibrations={
                    "S1_CHAMPION": {
                        "calibration_id": "s1-calibration-v1",
                        "method": "Isotonic regression on a synthetic benchmark",
                        "config_artifact": "config/calibration.json",
                        "benchmark_artifact": "benchmark/heldout.json",
                    }
                },
            )

    def test_per_method_calibration_tampering_is_detected(self) -> None:
        files = [self.csv("one.csv", 10_001), self.csv("two.csv", 20_001)]
        manifest = self.manifest(files)
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["calibrations"][1]["method"] = "Tampered logistic calibration method"
        path.write_text(json.dumps(stored), encoding="utf-8")
        with self.assertRaisesRegex(FreezeError, "calibration identity changed"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_upload_order_must_start_with_predeclared_champion(self) -> None:
        files = [self.csv("one.csv", 10_001), self.csv("two.csv", 20_001)]
        with self.assertRaisesRegex(FreezeError, "start with.*champion"):
            self.manifest(files, upload_order=["two.csv", "one.csv"])

    def test_every_evidence_artifact_kind_is_required(self) -> None:
        artifacts = self.artifacts()
        del artifacts["reference"]
        with self.assertRaisesRegex(FreezeError, "missing=.*reference"):
            self.manifest([self.csv("one.csv", 10_001)], artifacts=artifacts)

    def test_non_utc_freeze_timestamp_is_rejected(self) -> None:
        file = self.csv("one.csv", 10_001)
        with self.assertRaisesRegex(FreezeError, "UTC offset"):
            build_manifest(
                [file],
                {file.name: "A sufficiently detailed synthetic method rationale."},
                official_space_commit=COMMIT,
                created_at_utc="2026-08-26T15:00:00+01:00",
                artifact_root=self.public,
                artifacts=self.artifacts(),
                expected_ablations=[],
                method_ids={file.name: "S1_CHAMPION"},
                calibrations={
                    "S1_CHAMPION": {
                        "calibration_id": "synthetic-isotonic-v1",
                        "method": "Isotonic regression on a synthetic benchmark",
                        "config_artifact": "config/calibration.json",
                        "benchmark_artifact": "benchmark/heldout.json",
                    },
                },
                champion_method_id="S1_CHAMPION",
                upload_order=[file.name],
                private_raw_root=self.private,
                private_raw_paths={"synthetic-input": self.raw},
            )

    def test_overwrite_is_rejected(self) -> None:
        manifest = self.manifest([self.csv("one.csv", 10_001)])
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        with self.assertRaisesRegex(FreezeError, "refusing to overwrite"):
            write_manifest(path, manifest)

    def test_v1_manifest_is_explicitly_unsupported(self) -> None:
        path = self.root / "freeze.json"
        path.write_text('{"schema":"mva-track1-freeze/v1"}', encoding="utf-8")
        with self.assertRaisesRegex(FreezeError, "unsupported"):
            verify_manifest(path, self.public, private_raw_root=self.private)


if __name__ == "__main__":
    unittest.main()
