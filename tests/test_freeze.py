from __future__ import annotations

import csv
import hashlib
import json
import os
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
from mva_hackathon.community_pipeline import run_community_pipeline
from mva_hackathon.provenance import receipt_sha256
from mva_hackathon.save_path import (
    _copy_toolkit,
    _prepare_reachable,
    declare_next_gate,
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
        # The freeze receipt must be the real recomputed pipeline result over
        # the bound toolkit — a self-digested fabrication no longer seals.
        self.toolkit = _copy_toolkit(self.private)
        _prepare_reachable(self.toolkit)
        declare_next_gate(self.toolkit, "syn-gate-replication")
        receipt = run_community_pipeline(self.toolkit)
        self.program_receipt = self._private_file(
            "inputs/program-receipt.json",
            (
                json.dumps(receipt, indent=2, allow_nan=False) + "\n"
            ).encode("utf-8"),
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

    @staticmethod
    def _program_receipt_bytes(decision: str = "advance", *, stamp: bool = True) -> bytes:
        receipt: dict[str, object] = {
            "schema": "mva-track2-community-pipeline/v1",
            "synthetic_only": True,
            "decision": decision,
            "blocked_by": None,
            "block_reason": None,
            "n_steps": 16,
            "n_skipped": 0,
            "steps": [],
        }
        if stamp:
            receipt["receipt_sha256"] = receipt_sha256(receipt)
        return json.dumps(receipt, indent=2, allow_nan=False).encode("utf-8") + b"\n"

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
        official_space_commit: str = COMMIT,
        track2_reproducibility: Path | None = None,
        track2_root: Path | None = None,
        git_root: Path | None = None,
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
            official_space_commit=official_space_commit,
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
                "program-receipt": self.program_receipt,
            },
            community_toolkit_root=self.toolkit,
            public_commitment_nonces=nonces
            if nonces is not None
            else {"synthetic-input": NONCE},
            track2_reproducibility=track2_reproducibility,
            track2_root=track2_root,
            git_root=git_root,
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
        rendered = json.dumps(public, sort_keys=True, allow_nan=False)

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

    def test_case_tampered_manifest_path_fails_verification(self) -> None:
        path = self.write_and_verify(self.manifest([self.csv("one.csv", 10_001)]))
        stored = json.loads(path.read_text(encoding="utf-8"))
        entry = stored["artifacts"]["report"][0]
        original = entry["path"]
        tampered = original.upper()
        if tampered == original:
            tampered = original.capitalize()
        entry["path"] = tampered
        path.write_text(json.dumps(stored, allow_nan=False), encoding="utf-8")
        probe = self.public / tampered
        if not probe.exists():
            self.skipTest("case-sensitive filesystem resolves the tampered path absent")
        with self.assertRaisesRegex(FreezeError, "stored path does not match"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_hardlinked_public_files_cannot_hold_two_roles(self) -> None:
        alias = self.public / "code" / "pipeline-alias.py"
        alias.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(self.code, alias)
        except OSError:
            self.skipTest("hard links unavailable on this filesystem")
        path = self.write_and_verify(self.manifest([self.csv("one.csv", 10_001)]))
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["artifacts"]["code"].insert(
            0,
            {
                "path": "code/pipeline-alias.py",
                "size_bytes": alias.stat().st_size,
                "sha256": hashlib.sha256(alias.read_bytes()).hexdigest(),
            },
        )
        path.write_text(json.dumps(stored, allow_nan=False), encoding="utf-8")
        with self.assertRaisesRegex(FreezeError, "multiple frozen roles"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_non_finite_manifest_constant_fails_closed(self) -> None:
        path = self.write_and_verify(self.manifest([self.csv("one.csv", 10_001)]))
        raw = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(raw, allow_nan=False)
        path.write_text(text[:-1] + ',"extra": NaN}', encoding="utf-8")
        with self.assertRaisesRegex(FreezeError, "unreadable"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_tampered_upload_order_is_detected(self) -> None:
        files = [self.csv("one.csv", 10_001), self.csv("two.csv", 20_001)]
        manifest = self.manifest(files)
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["upload_order"].reverse()
        path.write_text(json.dumps(stored, allow_nan=False), encoding="utf-8")
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
        path.write_text(json.dumps(stored, allow_nan=False), encoding="utf-8")
        with self.assertRaisesRegex(FreezeError, "calibration identity changed"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_sealing_refuses_a_tree_that_drifted_after_build(self) -> None:
        manifest = self.manifest([self.csv("one.csv", 10_001)])
        self.report.write_bytes(b"tampered after hashing\n")
        with self.assertRaises(FreezeError):
            write_manifest(
                self.root / "freeze.json",
                manifest,
                artifact_root=self.public,
                private_raw_root=self.private,
            )
        self.assertFalse((self.root / "freeze.json").exists())

    def test_sealing_passes_when_the_tree_is_stable(self) -> None:
        manifest = self.manifest([self.csv("one.csv", 10_001)])
        path = self.root / "freeze.json"
        write_manifest(
            path,
            manifest,
            artifact_root=self.public,
            private_raw_root=self.private,
        )
        self.assertTrue(path.exists())
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

    def test_freeze_requires_an_advancing_program_receipt(self) -> None:
        file = self.csv("one.csv", 10_001)
        held = self._private_file(
            "inputs/program-receipt.json",
            self._program_receipt_bytes(decision="hold"),
        )
        self.program_receipt = held
        with self.assertRaisesRegex(FreezeError, "did not advance"):
            self.manifest([file])

    def test_freeze_rejects_an_undigested_program_receipt(self) -> None:
        file = self.csv("one.csv", 10_001)
        self.program_receipt = self._private_file(
            "inputs/program-receipt.json",
            self._program_receipt_bytes(stamp=False),
        )
        with self.assertRaisesRegex(FreezeError, "self-integrity digest"):
            self.manifest([file])

    def test_freeze_rejects_a_fabricated_advancing_receipt(self) -> None:
        # A self-digested "advance" receipt that the bound toolkit does not
        # reproduce is a forgery — self-integrity is not authenticity.
        file = self.csv("one.csv", 10_001)
        self.program_receipt = self._private_file(
            "inputs/program-receipt.json",
            self._program_receipt_bytes(decision="advance"),
        )
        with self.assertRaisesRegex(
            FreezeError, "does not match the bound community toolkit"
        ):
            self.manifest([file])

    def test_freeze_rejects_a_toolkit_mismatched_receipt(self) -> None:
        file = self.csv("one.csv", 10_001)
        with tempfile.TemporaryDirectory() as other:
            other_toolkit = _copy_toolkit(Path(other))
            _prepare_reachable(other_toolkit)
            declare_next_gate(other_toolkit, "syn-gate-replication")
            evidence_path = (
                other_toolkit / "observed_inferred_unknown.synthetic.json"
            )
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["links"][0]["statement"] = (
                "Rescue differs under treatment at generation resolution (edited)."
            )
            evidence_path.write_text(
                json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8"
            )
            # Still advancing, but bound to a different toolkit — its receipt
            # cannot seal this freeze.
            other_receipt = run_community_pipeline(other_toolkit)
            self.assertEqual(other_receipt["decision"], "advance")
            self.program_receipt = self._private_file(
                "inputs/program-receipt.json",
                (
                    json.dumps(other_receipt, indent=2, allow_nan=False) + "\n"
                ).encode("utf-8"),
            )
            with self.assertRaisesRegex(
                FreezeError, "does not match the bound community toolkit"
            ):
                self.manifest([file])

    def test_freeze_rejects_a_missing_program_receipt(self) -> None:
        file = self.csv("one.csv", 10_001)
        with self.assertRaisesRegex(FreezeError, "program-receipt"):
            build_manifest(
                [file],
                {file.name: "A sufficiently detailed synthetic method rationale."},
                official_space_commit=COMMIT,
                created_at_utc="2026-08-26T14:00:00+00:00",
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
                community_toolkit_root=self.toolkit,
            )

    def test_zero_byte_artifact_cannot_satisfy_a_role(self) -> None:
        file = self.csv("one.csv", 10_001)
        empty = self._public_file("report/empty.md", b"")
        artifacts = self.artifacts()
        artifacts["report"] = [empty]
        with self.assertRaisesRegex(FreezeError, "0-byte"):
            self.manifest([file], artifacts=artifacts)

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
                private_raw_paths={
                    "synthetic-input": self.raw,
                    "program-receipt": self.program_receipt,
                },
                community_toolkit_root=self.toolkit,
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

    def test_hard_linked_evidence_files_cannot_fill_two_roles(self) -> None:
        alias = self.public / "reference" / "aliased.txt"
        try:
            os.link(self.report, alias)
        except (OSError, NotImplementedError):
            self.skipTest("hard links unavailable on this filesystem")
        artifacts = self.artifacts()
        artifacts["reference"] = [alias]
        with self.assertRaisesRegex(FreezeError, "hard-linked"):
            self.manifest([self.csv("one.csv", 10_001)], artifacts=artifacts)

    def test_hard_linked_csv_cannot_fill_two_slots(self) -> None:
        first = self.csv("one.csv", 10_001)
        second = self.public / "submissions" / "two.csv"
        try:
            os.link(first, second)
        except (OSError, NotImplementedError):
            self.skipTest("hard links unavailable on this filesystem")
        with self.assertRaisesRegex(FreezeError, "hard-linked"):
            self.manifest([first, second])

    def test_hard_linked_csv_cannot_alias_an_evidence_artifact(self) -> None:
        file = self.csv("one.csv", 10_001)
        alias = self.public / "code" / "aliased.py"
        try:
            os.link(file, alias)
        except (OSError, NotImplementedError):
            self.skipTest("hard links unavailable on this filesystem")
        artifacts = self.artifacts()
        artifacts["code"] = [alias]
        with self.assertRaisesRegex(FreezeError, "hard-linked"):
            self.manifest([file], artifacts=artifacts)

    def _track2_tree(self, commit: str) -> tuple[Path, Path]:
        """Write a complete, valid Track 2 reproducibility tree to disk."""
        from mva_hackathon.reproducibility import (
            ARTIFACT_PATHS,
            COMMANDS,
            MANIFEST_PATH,
            SCHEMA,
        )

        tree = self.root / "track2"
        files = {
            path: f"fixture:{role}\n".encode() for role, path in ARTIFACT_PATHS.items()
        }
        config = {
            "schema": "mva-generation-selection-benchmark/v3",
            "monte_carlo_replicates": 1000,
            "scenarios": [{"name": f"scenario_{index}"} for index in range(14)],
        }
        files[ARTIFACT_PATHS["benchmark_config"]] = (
            json.dumps(config, sort_keys=True, allow_nan=False) + "\n"
        ).encode()
        receipt = {
            "runtime_receipt": {
                "canonical_command": COMMANDS["benchmark"],
                "config_sha256": hashlib.sha256(
                    files[ARTIFACT_PATHS["benchmark_config"]]
                ).hexdigest(),
                "source_sha256": hashlib.sha256(
                    files[ARTIFACT_PATHS["benchmark_source"]]
                ).hexdigest(),
                "runner_sha256": hashlib.sha256(
                    files[ARTIFACT_PATHS["benchmark_runner"]]
                ).hexdigest(),
                "test_sha256": hashlib.sha256(
                    files[ARTIFACT_PATHS["benchmark_test"]]
                ).hexdigest(),
                "git_source_commit": commit,
                "git_tracked_worktree_clean": True,
            },
            "monte_carlo_replicates_per_scenario": 1000,
            "scenarios": [
                {"name": f"scenario_{index}", "passed": True}
                for index in range(14)
            ],
            "summary": {
                "acceptance_passed": True,
                "all_passed": True,
                "passed": 14,
                "total": 14,
            },
            "total_simulated_vehicle_treatment_comparisons": 14000,
        }
        files[ARTIFACT_PATHS["benchmark_receipt"]] = (
            json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n"
        ).encode()
        for path, payload in files.items():
            target = tree.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        manifest = {
            "schema": SCHEMA,
            "source_commit": commit,
            "commands": COMMANDS,
            "artifacts": [
                {
                    "role": role,
                    "path": path.as_posix(),
                    "sha256": hashlib.sha256(files[path]).hexdigest(),
                }
                for role, path in ARTIFACT_PATHS.items()
            ],
        }
        manifest_path = tree.joinpath(*MANIFEST_PATH.parts)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(
            (json.dumps(manifest, sort_keys=True, allow_nan=False) + "\n").encode()
        )
        return tree, manifest_path

    def test_track2_binding_builds_and_verifies(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        files = [self.csv("full.csv", 10_001)]
        manifest = self.manifest(
            files,
            track2_reproducibility=track2_manifest,
            track2_root=tree,
        )
        binding = manifest["track2_reproducibility"]
        self.assertEqual(binding["source_commit"], COMMIT)  # type: ignore[index]
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        verify_manifest(
            path, self.public, private_raw_root=self.private, track2_root=tree
        )

    def test_track2_binding_rejects_commit_mismatch(self) -> None:
        tree, track2_manifest = self._track2_tree("b" * 40)
        with self.assertRaisesRegex(FreezeError, "source_commit"):
            self.manifest(
                [self.csv("one.csv", 10_001)],
                track2_reproducibility=track2_manifest,
                track2_root=tree,
            )

    def test_track2_binding_rejects_stale_manifest(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        from mva_hackathon.reproducibility import ARTIFACT_PATHS

        tampered = tree.joinpath(*ARTIFACT_PATHS["track2_report"].parts)
        tampered.write_bytes(tampered.read_bytes() + b"drift")
        with self.assertRaisesRegex(FreezeError, "stale or invalid"):
            self.manifest(
                [self.csv("one.csv", 10_001)],
                track2_reproducibility=track2_manifest,
                track2_root=tree,
            )

    def test_track2_binding_requires_track2_root(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        with self.assertRaisesRegex(FreezeError, "track2_root is required"):
            self.manifest(
                [self.csv("one.csv", 10_001)],
                track2_reproducibility=track2_manifest,
            )

    def test_verify_rejects_track2_root_without_binding(self) -> None:
        tree, _ = self._track2_tree(COMMIT)
        manifest = self.manifest([self.csv("one.csv", 10_001)])
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        with self.assertRaisesRegex(FreezeError, "binds no"):
            verify_manifest(
                path, self.public, private_raw_root=self.private, track2_root=tree
            )

    def test_verify_rejects_binding_without_track2_root(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        manifest = self.manifest(
            [self.csv("one.csv", 10_001)],
            track2_reproducibility=track2_manifest,
            track2_root=tree,
        )
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        with self.assertRaisesRegex(FreezeError, "without track2_root"):
            verify_manifest(path, self.public, private_raw_root=self.private)

    def test_verify_rejects_tampered_binding_digest(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        manifest = self.manifest(
            [self.csv("one.csv", 10_001)],
            track2_reproducibility=track2_manifest,
            track2_root=tree,
        )
        manifest["track2_reproducibility"]["sha256"] = "0" * 64  # type: ignore[index]
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        with self.assertRaisesRegex(FreezeError, "does not match"):
            verify_manifest(
                path, self.public, private_raw_root=self.private, track2_root=tree
            )

    def test_git_root_proves_commit_existence(self) -> None:
        import subprocess

        repo = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.skipTest("repository has no Git HEAD")
        commit = proc.stdout.strip()
        tree, track2_manifest = self._track2_tree(commit)
        manifest = self.manifest(
            [self.csv("one.csv", 10_001)],
            official_space_commit=commit,
            track2_reproducibility=track2_manifest,
            track2_root=tree,
            git_root=repo,
        )
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        verify_manifest(
            path,
            self.public,
            private_raw_root=self.private,
            track2_root=tree,
            git_root=repo,
        )
        with self.assertRaisesRegex(FreezeError, "does not resolve"):
            self.manifest(
                [self.csv("two.csv", 20_001)],
                official_space_commit="0" * 40,
                git_root=repo,
            )

    def test_write_manifest_seals_with_track2_and_git_roots(self) -> None:
        import subprocess

        repo = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.skipTest("repository has no Git HEAD")
        commit = proc.stdout.strip()
        tree, track2_manifest = self._track2_tree(commit)
        manifest = self.manifest(
            [self.csv("one.csv", 10_001)],
            official_space_commit=commit,
            track2_reproducibility=track2_manifest,
            track2_root=tree,
            git_root=repo,
        )
        path = self.root / "freeze.json"
        write_manifest(
            path,
            manifest,
            artifact_root=self.public,
            private_raw_root=self.private,
            track2_root=tree,
            git_root=repo,
        )
        self.assertTrue(path.is_file())

    def test_write_manifest_rejects_roots_without_artifact_root(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        manifest = self.manifest(
            [self.csv("one.csv", 10_001)],
            track2_reproducibility=track2_manifest,
            track2_root=tree,
        )
        with self.assertRaisesRegex(FreezeError, "require artifact_root"):
            write_manifest(
                self.root / "freeze.json",
                manifest,
                track2_root=tree,
            )

    def test_verify_detects_post_freeze_manifest_drift(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        manifest = self.manifest(
            [self.csv("one.csv", 10_001)],
            track2_reproducibility=track2_manifest,
            track2_root=tree,
        )
        path = self.root / "freeze.json"
        write_manifest(path, manifest)
        track2_manifest.write_bytes(track2_manifest.read_bytes() + b" ")
        with self.assertRaisesRegex(FreezeError, "does not match"):
            verify_manifest(
                path, self.public, private_raw_root=self.private, track2_root=tree
            )

    def test_public_projection_carries_the_track2_binding(self) -> None:
        tree, track2_manifest = self._track2_tree(COMMIT)
        manifest = self.manifest(
            [self.csv("one.csv", 10_001)],
            track2_reproducibility=track2_manifest,
            track2_root=tree,
        )
        projection = build_public_commitment_manifest(manifest)
        self.assertEqual(
            projection["track2_reproducibility"],
            manifest["track2_reproducibility"],
        )
        broken = dict(manifest)
        broken["track2_reproducibility"] = {"path": "release/x.json"}
        with self.assertRaisesRegex(FreezeError, "malformed"):
            build_public_commitment_manifest(broken)
        mismatched = dict(manifest)
        mismatched["track2_reproducibility"] = {
            **manifest["track2_reproducibility"],  # type: ignore[index]
            "source_commit": "b" * 40,
        }
        with self.assertRaisesRegex(FreezeError, "does not match"):
            build_public_commitment_manifest(mismatched)


if __name__ == "__main__":
    unittest.main()
