from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.method_delta import (
    CLAIM_BOUNDARY,
    CULTURE_REMAINING_DIRECTION,
    EXTERNAL_ANCHOR_REQUIREMENT,
    FAMILY_BY_SCENARIO,
    HOLDOUT_FAMILIES,
    LEGACY_SCHEMA,
    SCHEMA,
    SPEND_LADDER,
    MethodDeltaError,
    _metrics,
    _scenario_row,
    comparison_sha256,
    compare_method_delta,
    earliest_remaining_by_family,
    freeze_pointers,
    living_method_pointers,
    receipt_sha256,
    seal_method_delta_receipt,
    seal_snapshot,
    snapshot_sha256,
    snapshot_method,
    validate_method_delta_receipt,
    validate_snapshot,
)
from mva_hackathon.reproducibility import MANIFEST_PATH
from scripts import assess_method_delta as method_delta_cli


ROOT = Path(__file__).resolve().parents[1]
METHOD_DELTA_SCHEMA = ROOT / "schemas" / "track2_method_delta.schema.json"


def _maliciously_readdress(payload: dict, identity_field: str) -> None:
    clone = copy.deepcopy(payload)
    clone[identity_field] = None
    encoded = json.dumps(
        clone,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    payload[identity_field] = "sha256:" + hashlib.sha256(encoded).hexdigest()


_HOLDOUT_SCENARIO = {
    "identity.incomplete_confirmation": "incomplete_confirmation",
    "phase.cis": "cis_pair",
    "false_rescue.heat_shock_pd": "heat_shock_pd",
    "chooser.probe_before_identity": "probe_before_identity",
    "ranking.not_an_assay": "predicted_stability_as_function",
}


def _gate_for(remaining: float) -> str:
    spends = {spend: gate for gate, (_, spend) in SPEND_LADDER.items()}
    target = min(spends, key=lambda spend: (abs(spend - remaining), spend))
    return spends[target]


def _snapshot(
    *,
    families: int,
    remaining: float,
    true_opened: int = 1,
    gates=None,
    first_blocks=None,
    ranking=1.0,
    parent_snapshot_id: str | None = None,
) -> dict:
    gate_list = list(gates or ["confirmation", "hypomorph"])
    first_block_list = list(first_blocks or [_gate_for(remaining)])
    scenario_rows = [
        {
            "scenario_id": "syn-true-path",
            "kind": "true_path",
            "family_id": "other.syn-true-path",
            "motivation": "envelope_gap",
            "decision": "pass",
            "blocked_by": None,
            "block_reason": None,
            "terminal_blocked_by": None,
            "terminal_block_reason": None,
            "earliest_nonpass_gate": None,
            "earliest_nonpass_effect": None,
            "earliest_nonpass_reason": None,
            "lab_object": "desktop_claim",
            "culture_remaining": 0,
            "blocked_from_advancing": False,
            "opened": true_opened == 1,
            "discriminable_at_freeze": False,
        }
    ]
    for index in range(families):
        gate = first_block_list[index % len(first_block_list)]
        scenario_id = (
            _HOLDOUT_SCENARIO[HOLDOUT_FAMILIES[index]]
            if index < len(HOLDOUT_FAMILIES)
            else f"syn-false-{index}"
        )
        scenario_rows.append(
            {
                "scenario_id": scenario_id,
                "kind": "false_path",
                "family_id": FAMILY_BY_SCENARIO.get(
                    scenario_id, f"other.{scenario_id}"
                ),
                "motivation": "literature_family",
                "decision": "stop",
                "blocked_by": gate,
                "block_reason": "syn_blocked",
                "terminal_blocked_by": gate,
                "terminal_block_reason": "syn_blocked",
                "earliest_nonpass_gate": gate,
                "earliest_nonpass_effect": "stop",
                "earliest_nonpass_reason": "syn_blocked",
                "lab_object": SPEND_LADDER.get(gate, ("desktop_claim", 0))[0],
                "culture_remaining": SPEND_LADDER.get(
                    gate, ("desktop_claim", 0)
                )[1],
                "blocked_from_advancing": True,
                "opened": False,
                "discriminable_at_freeze": False,
            }
        )
    scenario_rows.append(
        {
            "scenario_id": "ranking_cannot_open_checkpoint",
            "kind": "false_path",
            "family_id": FAMILY_BY_SCENARIO["ranking_cannot_open_checkpoint"],
            "motivation": "literature_family",
            "decision": "hold",
            "blocked_by": "structure_ranking",
            "block_reason": "checkpoint_not_ready",
            "terminal_blocked_by": "structure_ranking",
            "terminal_block_reason": "checkpoint_not_ready",
            "earliest_nonpass_gate": "structure_ranking",
            "earliest_nonpass_effect": "hold",
            "earliest_nonpass_reason": "checkpoint_not_ready",
            "lab_object": "desktop_claim",
            "culture_remaining": 0,
            "blocked_from_advancing": True,
            "opened": False,
            "discriminable_at_freeze": False,
        }
    )
    ranking_rows = [
        {
            "case_id": "public_toolkit",
            "expected_step": "confirmation",
            "observed_step": "confirmation" if ranking >= 1.0 else None,
            "identity_complete": False,
            "probe_before_identity_stopped": False,
            "correct": ranking >= 1.0,
        },
        {
            "case_id": "probe_before_identity",
            "expected_step": "confirmation",
            "observed_step": "confirmation",
            "identity_complete": False,
            "probe_before_identity_stopped": ranking > 0.0,
            "correct": ranking > 0.0,
        },
    ]
    return seal_snapshot(
        {
            "schema": SCHEMA,
            "record_kind": "snapshot",
            "snapshot_id": None,
            "parent_snapshot_id": parent_snapshot_id,
            "synthetic_only": True,
            "claim_boundary": CLAIM_BOUNDARY,
            "chronology": {
                "recorded_at": None,
                "exposure_started_at": None,
                "timestamp_authenticity": "not_established",
                "exposure_boundary": "not_established",
                "exposure_boundary_authenticity": "not_established",
            },
            "invariants": {
                "true_path_opens": {
                    "passed": true_opened == 1,
                    "detail": "true_path_opens",
                },
                "public_confirmation_holds": {
                    "passed": True,
                    "detail": "public_confirmation_holds",
                },
                "freeze_bytes_untouched": {
                    "passed": True,
                    "detail": "freeze_bytes_untouched",
                },
                "no_medicine_claim": {
                    "passed": True,
                    "detail": "no_medicine_claim",
                },
                "ranking_cannot_open_checkpoint": {
                    "passed": True,
                    "detail": "ranking_cannot_open_checkpoint",
                },
                "identity_violations_zero": {
                    "passed": True,
                    "detail": "identity_violations_zero",
                },
                "public_recommended_confirmation": {
                    "passed": True,
                    "detail": "public_recommended_confirmation",
                },
                "holdout_families_still_blocked": {
                    "passed": True,
                    "detail": "holdout_families_still_blocked",
                },
                "living_method_surface_bound": {
                    "passed": True,
                    "detail": "living_method_surface_bound",
                },
            },
            "freeze_pointers": {
                "source_commit": "0" * 40,
                "n_artifacts_checked": 1,
                "passed": True,
                "artifacts": [
                    {
                        "path": "release/bound.json",
                        "role": "receipt",
                        "sha256": "ab" * 32,
                    }
                ],
            },
            "living_method_integrity": {
                "n_artifacts": 1,
                "bundle_sha256": hashlib.sha256(
                    json.dumps(
                        [
                            {
                                "path": "src/mva_hackathon/synthetic.py",
                                "sha256": "cd" * 32,
                            }
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=True, allow_nan=False).encode("utf-8")
                ).hexdigest(),
                "artifacts": [
                    {
                        "path": "src/mva_hackathon/synthetic.py",
                        "sha256": "cd" * 32,
                    }
                ],
            },
            "public_toolkit": {
                "decision": "hold",
                "blocked_by": "confirmation",
                "block_reason": "syn-block",
            },
            "save_path": {
                "n_true_path_opened": true_opened,
                "n_true_path": 1,
                "n_false_paths_blocked_from_advancing": families,
                "n_false_path": families,
                "save_path_reachable": true_opened == 1,
                "structure_ranking_checkpoint_ready": False,
            },
            "registered_gates": gate_list,
            "metrics": _metrics(scenario_rows, ranking_rows),
            "scenarios": scenario_rows,
            "ranking_cases": ranking_rows,
        },
        parent_snapshot_id=parent_snapshot_id,
    )


class MethodDeltaTests(unittest.TestCase):
    def _schema_validator(self) -> Draft202012Validator:
        schema = json.loads(METHOD_DELTA_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def assertSchemaValid(self, payload: object) -> None:
        errors = list(self._schema_validator().iter_errors(payload))
        self.assertEqual([], [error.message for error in errors])

    def assertSchemaInvalid(self, payload: object) -> None:
        errors = list(self._schema_validator().iter_errors(payload))
        self.assertTrue(errors, "payload unexpectedly satisfied method-delta schema")

    def test_every_false_path_scenario_has_a_declared_family(self) -> None:
        source = (ROOT / "src" / "mva_hackathon" / "save_path.py").read_text(
            encoding="utf-8"
        )
        registrations = re.findall(
            r'_run_mutated\(\s*"([a-z_0-9]+)",\s*"([a-z_]+)"', source
        )
        false_names = [
            name for name, kind in registrations if kind == "false_path"
        ]
        self.assertTrue(false_names)
        missing = [
            name for name in false_names if name not in FAMILY_BY_SCENARIO
        ]
        self.assertEqual(missing, [])

    def test_scenario_row_rejects_undeclared_false_path_family(self) -> None:
        with self.assertRaisesRegex(MethodDeltaError, "declared family"):
            _scenario_row(
                {
                    "name": "invented_unmapped_scenario",
                    "kind": "false_path",
                    "blocked_from_advancing": True,
                }
            )

    def test_computational_correction_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["computational_correction"],
            "function.computational_correction_reversal",
        )
        self.assertEqual(
            FAMILY_BY_SCENARIO["computational_stability"],
            "function.analog_or_computational",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_correction"],
            FAMILY_BY_SCENARIO["computational_stability"],
        )

    def test_reciprocal_recreation_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["failed_reciprocal_recreation"],
            "function.reciprocal_recreation",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["failed_reciprocal_recreation"],
            FAMILY_BY_SCENARIO["computational_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["failed_reciprocal_recreation"],
            FAMILY_BY_SCENARIO["computational_stability"],
        )

    def test_imposed_extrinsic_stress_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["imposed_extrinsic_stress"],
            "function.imposed_extrinsic_stress",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["imposed_extrinsic_stress"],
            FAMILY_BY_SCENARIO["heat_shock_pd"],
        )

    def test_cell_free_biophysical_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["cell_free_biophysical"],
            "function.cell_free_biophysical",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["cell_free_biophysical"],
            FAMILY_BY_SCENARIO["computational_stability"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["cell_free_biophysical"],
            FAMILY_BY_SCENARIO["imposed_extrinsic_stress"],
        )

    def test_cell_free_correction_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["cell_free_correction"],
            "function.cell_free_correction_reversal",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["cell_free_correction"],
            FAMILY_BY_SCENARIO["cell_free_biophysical"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["cell_free_correction"],
            FAMILY_BY_SCENARIO["computational_correction"],
        )

    def test_imposed_stress_correction_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["imposed_stress_correction"],
            "function.imposed_stress_correction_reversal",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["imposed_stress_correction"],
            FAMILY_BY_SCENARIO["imposed_extrinsic_stress"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["imposed_stress_correction"],
            FAMILY_BY_SCENARIO["cell_free_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["imposed_stress_correction"],
            FAMILY_BY_SCENARIO["computational_correction"],
        )

    def test_ectopic_expression_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["ectopic_expression"],
            "function.ectopic_expression",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["ectopic_expression"],
            FAMILY_BY_SCENARIO["cell_free_biophysical"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["ectopic_expression"],
            FAMILY_BY_SCENARIO["imposed_extrinsic_stress"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["ectopic_expression"],
            FAMILY_BY_SCENARIO["imposed_stress_correction"],
        )

    def test_ectopic_correction_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["ectopic_correction"],
            "function.ectopic_correction_reversal",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["ectopic_correction"],
            FAMILY_BY_SCENARIO["ectopic_expression"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["ectopic_correction"],
            FAMILY_BY_SCENARIO["cell_free_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["ectopic_correction"],
            FAMILY_BY_SCENARIO["imposed_stress_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["ectopic_correction"],
            FAMILY_BY_SCENARIO["computational_correction"],
        )

    def test_rna_confirmation_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["rna_confirmation"],
            "identity.rna_not_genomic",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["rna_confirmation"],
            FAMILY_BY_SCENARIO["incomplete_confirmation"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["rna_confirmation"],
            FAMILY_BY_SCENARIO["kmer_without_nest"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["rna_confirmation"],
            FAMILY_BY_SCENARIO["kmer_without_file_layout"],
        )

    def test_computational_transcript_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["computational_transcript"],
            "transcript.not_an_assay",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_transcript"],
            FAMILY_BY_SCENARIO["incomplete_transcript"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_transcript"],
            FAMILY_BY_SCENARIO["computational_stability"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_transcript"],
            FAMILY_BY_SCENARIO["predicted_stability_as_function"],
        )

    def test_computational_phase_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["computational_phase"],
            "phase.not_a_molecule",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_phase"],
            FAMILY_BY_SCENARIO["cis_pair"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_phase"],
            FAMILY_BY_SCENARIO["dropout_compatible_phase"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_phase"],
            FAMILY_BY_SCENARIO["computational_transcript"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["computational_phase"],
            FAMILY_BY_SCENARIO["rna_confirmation"],
        )

    def test_unmatched_transcript_specimen_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
            "transcript.unmatched_specimen",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
            FAMILY_BY_SCENARIO["incomplete_transcript"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
            FAMILY_BY_SCENARIO["computational_transcript"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
            FAMILY_BY_SCENARIO["rna_confirmation"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
            FAMILY_BY_SCENARIO["ectopic_expression"],
        )

    def test_unmatched_confirmation_specimen_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["unmatched_confirmation_specimen"],
            "identity.unmatched_specimen",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_confirmation_specimen"],
            FAMILY_BY_SCENARIO["incomplete_confirmation"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_confirmation_specimen"],
            FAMILY_BY_SCENARIO["rna_confirmation"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_confirmation_specimen"],
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_confirmation_specimen"],
            FAMILY_BY_SCENARIO["unlinked_confirmation"],
        )

    def test_unmatched_phase_specimen_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["unmatched_phase_specimen"],
            "phase.unmatched_specimen",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_phase_specimen"],
            FAMILY_BY_SCENARIO["computational_phase"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_phase_specimen"],
            FAMILY_BY_SCENARIO["cis_pair"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_phase_specimen"],
            FAMILY_BY_SCENARIO["unmatched_confirmation_specimen"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_phase_specimen"],
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
        )

    def test_unmatched_assay_specimen_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["unmatched_assay_specimen"],
            "function.unmatched_specimen",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_assay_specimen"],
            FAMILY_BY_SCENARIO["ectopic_expression"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_assay_specimen"],
            FAMILY_BY_SCENARIO["ectopic_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_assay_specimen"],
            FAMILY_BY_SCENARIO["unmatched_confirmation_specimen"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_assay_specimen"],
            FAMILY_BY_SCENARIO["unmatched_transcript_specimen"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_assay_specimen"],
            FAMILY_BY_SCENARIO["unmatched_phase_specimen"],
        )

    def test_unmatched_correction_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["unmatched_correction"],
            "function.unmatched_correction_reversal",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_correction"],
            FAMILY_BY_SCENARIO["unmatched_assay_specimen"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_correction"],
            FAMILY_BY_SCENARIO["ectopic_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_correction"],
            FAMILY_BY_SCENARIO["cell_free_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_correction"],
            FAMILY_BY_SCENARIO["imposed_stress_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["unmatched_correction"],
            FAMILY_BY_SCENARIO["computational_correction"],
        )

    def test_analog_correction_is_its_own_family(self) -> None:
        self.assertEqual(
            FAMILY_BY_SCENARIO["analog_correction"],
            "function.analog_correction_reversal",
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["analog_correction"],
            FAMILY_BY_SCENARIO["analog_as_function"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["analog_correction"],
            FAMILY_BY_SCENARIO["computational_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["analog_correction"],
            FAMILY_BY_SCENARIO["unmatched_correction"],
        )
        self.assertNotEqual(
            FAMILY_BY_SCENARIO["analog_correction"],
            FAMILY_BY_SCENARIO["ectopic_correction"],
        )

    def test_freeze_pointers_match_bound_hashes_without_reading_report_text(self) -> None:
        pointers = freeze_pointers(ROOT)
        # The release manifest is minted at the release source commit and binds
        # that commit's artifact bytes exactly, so every bound artifact matches
        # its pinned hash on a clean release tree.
        self.assertTrue(pointers["passed"])
        mismatched = {
            item["path"]
            for item in pointers["artifacts"]
            if not item["matched"]
        }
        self.assertEqual(mismatched, set())
        self.assertGreaterEqual(pointers["n_artifacts_checked"], 10)
        self.assertEqual(
            pointers["source_commit"],
            "0f14d6725417f582a8e0c32843a79201d4924208",
        )

    def test_living_method_pointers_reject_hard_link_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "src" / "mva_hackathon"
            source.mkdir(parents=True)
            first = source / "first.py"
            second = source / "second.py"
            first.write_text("same living method bytes\n", encoding="utf-8")
            os.link(first, second)

            with self.assertRaises(MethodDeltaError) as raised:
                living_method_pointers(directory)

            message = str(raised.exception)
            self.assertIn("same underlying file", message)
            self.assertIn("src/mva_hackathon/first.py", message)
            self.assertIn("src/mva_hackathon/second.py", message)

    def test_freeze_pointers_rejects_empty_artifact_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release").mkdir()
            (root / MANIFEST_PATH).write_text(
                json.dumps(
                    {"source_commit": "0" * 40, "artifacts": []}
                , allow_nan=False),
                encoding="utf-8",
            )
            pointers = freeze_pointers(root)
            self.assertFalse(pointers["passed"])
            self.assertEqual(pointers["n_artifacts_checked"], 0)

    def test_freeze_pointers_confine_artifacts_to_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            (root / "release").mkdir()
            outside = Path(directory) / "outside.txt"
            outside.write_text("outside bytes\n", encoding="utf-8")
            digest = hashlib.sha256(outside.read_bytes()).hexdigest()
            (root / MANIFEST_PATH).write_text(
                json.dumps(
                    {
                        "source_commit": "0" * 40,
                        "artifacts": [
                            {"path": "../outside.txt", "sha256": digest},
                            {"path": str(outside).replace("\\", "/"), "sha256": digest},
                        ],
                    }
                , allow_nan=False),
                encoding="utf-8",
            )
            pointers = freeze_pointers(root)
            self.assertFalse(pointers["passed"])
            self.assertFalse(
                any(item["matched"] for item in pointers["artifacts"])
            )

    def test_living_method_pointers_reject_symlink_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "mva_hackathon"
            source.mkdir(parents=True)
            target = Path(directory) / "outside.py"
            target.write_text("outside bytes\n", encoding="utf-8")
            try:
                (source / "linked.py").symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            with self.assertRaises(MethodDeltaError):
                living_method_pointers(root)

    def test_living_method_pointers_allow_distinct_files_with_identical_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "src" / "mva_hackathon"
            source.mkdir(parents=True)
            for name in ("first.py", "second.py"):
                (source / name).write_text(
                    "same living method bytes\n",
                    encoding="utf-8",
                )

            pointers = living_method_pointers(directory)

            self.assertEqual(pointers["n_artifacts"], 2)
            self.assertEqual(
                len({item["sha256"] for item in pointers["artifacts"]}),
                1,
            )

    def test_nested_method_beats_freeze_envelope(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        result = compare_method_delta(current)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["verdict"], "better")
        self.assertEqual(result["compared_to"], "freeze_envelope")
        self.assertEqual(result["current_snapshot_sha256"], snapshot_sha256(current))
        self.assertIsNone(result["previous_snapshot_sha256"])

    def test_snapshot_id_is_deterministic_and_parent_bound(self) -> None:
        snapshot = _snapshot(families=8, remaining=12.0)
        reordered = dict(reversed(list(snapshot.items())))
        resealed = seal_snapshot(reordered)
        self.assertEqual(resealed["snapshot_id"], snapshot["snapshot_id"])
        self.assertEqual(validate_snapshot(resealed), snapshot_sha256(snapshot))

        parent_a = _snapshot(families=7, remaining=11.0)
        parent_b = _snapshot(families=6, remaining=10.0)
        unlinked = copy.deepcopy(snapshot)
        linked_a = seal_snapshot(
            snapshot,
            parent_snapshot_id=parent_a["snapshot_id"],
        )
        linked_b = seal_snapshot(
            snapshot,
            parent_snapshot_id=parent_b["snapshot_id"],
        )
        self.assertEqual(snapshot, unlinked)
        self.assertEqual(linked_a["metrics"], linked_b["metrics"])
        self.assertNotEqual(linked_a["snapshot_id"], linked_b["snapshot_id"])
        self.assertNotEqual(snapshot_sha256(linked_a), snapshot_sha256(linked_b))

    def test_comparison_binds_parent_and_exact_snapshot_bytes(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(current["parent_snapshot_id"], previous["snapshot_id"])
        self.assertEqual(result["parent_snapshot_id"], previous["snapshot_id"])
        self.assertEqual(result["current_snapshot_sha256"], snapshot_sha256(current))
        self.assertEqual(
            result["previous_snapshot_sha256"],
            snapshot_sha256(previous),
        )
        receipt = seal_method_delta_receipt(current, previous=previous)
        validated = validate_method_delta_receipt(
            receipt,
            previous=previous,
        )
        self.assertEqual(validated, current)
        self.assertEqual(receipt["previous_snapshot"], previous)
        self.assertRegex(receipt["receipt_id"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(result["comparison_id"], r"^sha256:[0-9a-f]{64}$")

    def test_tampered_current_snapshot_is_rejected(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        current["invariants"]["no_medicine_claim"]["passed"] = False
        with self.assertRaisesRegex(MethodDeltaError, "snapshot_id does not match"):
            compare_method_delta(current)
        fabricated = _snapshot(families=8, remaining=12.0)
        fabricated["metrics"]["n_independent_families_blocked_from_advancing"] = 99
        with self.assertRaisesRegex(
            MethodDeltaError, "metrics do not match the scenario and ranking rows"
        ):
            compare_method_delta(fabricated)

    def test_tampered_previous_snapshot_is_rejected(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        previous["invariants"]["no_medicine_claim"]["passed"] = False
        with self.assertRaisesRegex(MethodDeltaError, "snapshot_id does not match"):
            compare_method_delta(current, previous=previous)
        previous = _snapshot(families=8, remaining=12.0)
        previous["metrics"]["mean_culture_remaining"] = 99.0
        with self.assertRaisesRegex(
            MethodDeltaError, "metrics do not match the scenario and ranking rows"
        ):
            compare_method_delta(current, previous=previous)

    def test_substituted_previous_snapshot_breaks_parent_link(self) -> None:
        original = _snapshot(families=8, remaining=12.0)
        substitute = _snapshot(families=7, remaining=11.0)
        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=original["snapshot_id"],
        )
        compare_method_delta(current, previous=original)
        with self.assertRaisesRegex(MethodDeltaError, "resealed"):
            compare_method_delta(current, previous=substitute)

    def test_comparison_does_not_mutate_an_unlinked_sealed_snapshot(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(families=9, remaining=13.0)
        original = copy.deepcopy(current)

        with self.assertRaisesRegex(MethodDeltaError, "resealed"):
            compare_method_delta(current, previous=previous)

        self.assertEqual(current, original)
        self.assertIsNone(current["parent_snapshot_id"])
        self.assertEqual(validate_snapshot(current), snapshot_sha256(current))

    def test_receipt_rejects_substituted_snapshot_or_digest(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        receipt = seal_method_delta_receipt(current, previous=previous)

        substituted = copy.deepcopy(receipt)
        substituted["snapshot"]["invariants"]["no_medicine_claim"]["passed"] = False
        with self.assertRaisesRegex(MethodDeltaError, "snapshot_id does not match"):
            validate_method_delta_receipt(substituted, previous=previous)

        fabricated = copy.deepcopy(receipt)
        fabricated["snapshot"]["metrics"][
            "n_independent_families_blocked_from_advancing"
        ] = 999
        with self.assertRaisesRegex(
            MethodDeltaError, "metrics do not match the scenario and ranking rows"
        ):
            validate_method_delta_receipt(fabricated, previous=previous)

        wrong_digest = copy.deepcopy(receipt)
        wrong_digest["comparison"]["current_snapshot_sha256"] = "0" * 64
        with self.assertRaisesRegex(MethodDeltaError, "comparison_id does not match"):
            validate_method_delta_receipt(wrong_digest, previous=previous)

        wrong_previous_digest = copy.deepcopy(receipt)
        wrong_previous_digest["comparison"]["previous_snapshot_sha256"] = "0" * 64
        with self.assertRaisesRegex(MethodDeltaError, "comparison_id does not match"):
            validate_method_delta_receipt(
                wrong_previous_digest,
                previous=previous,
            )

    def test_baseline_receipt_requires_both_digest_fields(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        receipt = seal_method_delta_receipt(current)
        self.assertEqual(validate_method_delta_receipt(receipt), current)

        missing_previous_digest = copy.deepcopy(receipt)
        del missing_previous_digest["comparison"]["previous_snapshot_sha256"]
        with self.assertRaisesRegex(MethodDeltaError, "wrong fields"):
            validate_method_delta_receipt(missing_previous_digest)

    def test_readdressed_comparison_tamper_fails_deterministic_recomputation(
        self,
    ) -> None:
        current = _snapshot(families=8, remaining=12.0)
        receipt = seal_method_delta_receipt(current)
        tampered = copy.deepcopy(receipt)
        tampered["comparison"]["verdict"] = "worse"
        tampered["comparison"]["reason"] = "attacker_changed_reason"
        tampered["comparison"]["internal_joint_verdict"] = "worse"
        _maliciously_readdress(tampered["comparison"], "comparison_id")
        _maliciously_readdress(tampered, "receipt_id")
        self.assertSchemaValid(tampered)
        with self.assertRaisesRegex(MethodDeltaError, "deterministic recomputation"):
            validate_method_delta_receipt(tampered)

    def test_linked_receipt_cannot_omit_or_substitute_embedded_parent(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        receipt = seal_method_delta_receipt(current, previous=previous)

        omitted = copy.deepcopy(receipt)
        omitted["previous_snapshot"] = None
        _maliciously_readdress(omitted, "receipt_id")
        with self.assertRaisesRegex(MethodDeltaError, "must embed"):
            validate_method_delta_receipt(omitted)

        substitute = _snapshot(families=7, remaining=11.0)
        substituted = copy.deepcopy(receipt)
        substituted["previous_snapshot"] = substitute
        _maliciously_readdress(substituted, "receipt_id")
        with self.assertRaisesRegex(MethodDeltaError, "parent_snapshot_id"):
            validate_method_delta_receipt(substituted)
        with self.assertRaisesRegex(MethodDeltaError, "differs from embedded"):
            validate_method_delta_receipt(receipt, previous=substitute)

    def test_sealing_and_validation_return_detached_nested_structures(self) -> None:
        unsealed = copy.deepcopy(_snapshot(families=8, remaining=12.0))
        unsealed["snapshot_id"] = None
        sealed = seal_snapshot(unsealed)
        self.assertIsNot(sealed["metrics"], unsealed["metrics"])
        unsealed["metrics"]["mean_culture_remaining"] = 999.0
        self.assertEqual(sealed["metrics"]["mean_culture_remaining"], 13.0)

        receipt = seal_method_delta_receipt(sealed)
        returned = validate_method_delta_receipt(receipt)
        self.assertIsNot(returned["metrics"], receipt["snapshot"]["metrics"])
        returned["metrics"]["mean_culture_remaining"] = 1.0
        self.assertEqual(
            receipt["snapshot"]["metrics"]["mean_culture_remaining"], 13.0
        )

    def test_modified_sealed_snapshot_cannot_be_silently_resealed(self) -> None:
        snapshot = _snapshot(families=8, remaining=12.0)
        snapshot["invariants"]["no_medicine_claim"]["passed"] = False
        with self.assertRaisesRegex(MethodDeltaError, "snapshot_id does not match"):
            seal_snapshot(snapshot)
        fabricated = _snapshot(families=8, remaining=12.0)
        fabricated["metrics"]["mean_culture_remaining"] = 99.0
        with self.assertRaisesRegex(
            MethodDeltaError, "metrics do not match the scenario and ranking rows"
        ):
            seal_snapshot(fabricated)

    def test_declared_chronology_is_bound_but_never_authenticated(self) -> None:
        snapshot = _snapshot(families=8, remaining=12.0)
        snapshot["snapshot_id"] = None
        snapshot["chronology"] = {
            "recorded_at": "2026-08-30T09:00:00Z",
            "exposure_started_at": "2026-08-30T10:00:00Z",
            "timestamp_authenticity": "not_established",
            "exposure_boundary": "declared_pre_exposure",
            "exposure_boundary_authenticity": "not_established",
        }
        snapshot = seal_snapshot(snapshot)
        validate_snapshot(snapshot)
        self.assertEqual(
            snapshot["chronology"]["exposure_boundary"], "declared_pre_exposure"
        )

        false_authentication = copy.deepcopy(snapshot)
        false_authentication["chronology"]["timestamp_authenticity"] = "authenticated"
        _maliciously_readdress(false_authentication, "snapshot_id")
        with self.assertRaisesRegex(MethodDeltaError, "authenticated local time"):
            validate_snapshot(false_authentication)

    def test_receipt_declares_external_anchor_boundary_and_addresses_every_layer(
        self,
    ) -> None:
        receipt = seal_method_delta_receipt(
            _snapshot(families=8, remaining=12.0)
        )
        self.assertEqual(
            receipt["external_anchor"]["requirement"],
            EXTERNAL_ANCHOR_REQUIREMENT,
        )
        self.assertEqual(
            receipt["external_anchor"]["authenticity"], "not_established"
        )
        self.assertEqual(len(receipt_sha256(receipt)), 64)
        self.assertEqual(len(comparison_sha256(receipt["comparison"])), 64)
        self.assertNotIn("child_help", receipt["comparison"])
        self.assertNotIn("prize_help", receipt["comparison"])
        self.assertNotIn("joint_verdict", receipt["comparison"])
        self.assertEqual(
            receipt["comparison"]["external_outcomes"],
            {
                "child_benefit": "not_established",
                "competition_prize": "not_established",
            },
        )

    def test_whole_reseal_gets_a_new_identity_and_still_needs_external_anchor(
        self,
    ) -> None:
        original_snapshot = _snapshot(families=8, remaining=12.0)
        original_receipt = seal_method_delta_receipt(original_snapshot)
        replacement_snapshot = copy.deepcopy(original_snapshot)
        replacement_snapshot["snapshot_id"] = None
        replacement_snapshot["chronology"]["recorded_at"] = "2026-09-11T00:00:00Z"
        replacement_snapshot = seal_snapshot(replacement_snapshot)
        replacement_receipt = seal_method_delta_receipt(replacement_snapshot)
        validate_method_delta_receipt(original_receipt)
        validate_method_delta_receipt(replacement_receipt)
        self.assertNotEqual(
            replacement_receipt["receipt_id"], original_receipt["receipt_id"]
        )
        self.assertEqual(
            replacement_receipt["external_anchor"]["authenticity"],
            "not_established",
        )

    def test_legacy_wrapper_compatibility_is_snapshot_only_and_labeled(self) -> None:
        legacy = copy.deepcopy(_snapshot(families=8, remaining=12.0))
        legacy["schema"] = LEGACY_SCHEMA
        legacy.pop("chronology")
        legacy["snapshot_id"] = None
        _maliciously_readdress(legacy, "snapshot_id")
        validate_snapshot(legacy)
        wrapper = {"snapshot": legacy, "comparison": {"verdict": "attacker"}}
        with self.assertRaisesRegex(MethodDeltaError, "not authenticated receipts"):
            validate_method_delta_receipt(wrapper)
        with (
            mock.patch.object(Path, "read_text", return_value=json.dumps(wrapper, allow_nan=False)),
            self.assertWarnsRegex(RuntimeWarning, "legacy v1 wrapper"),
        ):
            loaded = method_delta_cli._load_snapshot(Path("legacy.json"))
        self.assertEqual(loaded, legacy)

        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=legacy["snapshot_id"],
        )
        receipt = seal_method_delta_receipt(current, previous=legacy)
        self.assertEqual(
            receipt["comparison"]["previous_linkage_status"],
            "legacy_snapshot_content_only",
        )
        validate_method_delta_receipt(receipt)

    def test_cli_rejects_duplicate_json_keys(self) -> None:
        duplicate = '{"schema":"first","schema":"second"}'
        with mock.patch.object(Path, "read_text", return_value=duplicate):
            with self.assertRaisesRegex(MethodDeltaError, "duplicate key"):
                method_delta_cli._load_snapshot(Path("duplicate.json"))

    def test_schema_requires_sealed_ids_digests_and_a_coherent_chain(self) -> None:
        baseline_snapshot = _snapshot(families=8, remaining=12.0)
        baseline_comparison = compare_method_delta(baseline_snapshot)
        baseline_receipt = seal_method_delta_receipt(baseline_snapshot)
        for payload in (
            baseline_snapshot,
            baseline_comparison,
            baseline_receipt,
        ):
            self.assertSchemaValid(payload)

        previous = _snapshot(families=8, remaining=12.0)
        linked_snapshot = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        linked_comparison = compare_method_delta(
            linked_snapshot,
            previous=previous,
        )
        linked_receipt = seal_method_delta_receipt(
            linked_snapshot,
            previous=previous,
        )
        for payload in (
            linked_snapshot,
            linked_comparison,
            linked_receipt,
        ):
            self.assertSchemaValid(payload)

        malformed_snapshot_id = copy.deepcopy(baseline_snapshot)
        malformed_snapshot_id["snapshot_id"] = "sha256:" + "A" * 64
        self.assertSchemaInvalid(malformed_snapshot_id)

        malformed_parent = copy.deepcopy(linked_snapshot)
        malformed_parent["parent_snapshot_id"] = "sha256:" + "0" * 63
        self.assertSchemaInvalid(malformed_parent)

        prefixed_snapshot_digest = copy.deepcopy(baseline_comparison)
        prefixed_snapshot_digest["current_snapshot_sha256"] = (
            "sha256:" + "0" * 64
        )
        self.assertSchemaInvalid(prefixed_snapshot_digest)

        baseline_claiming_previous = copy.deepcopy(baseline_comparison)
        baseline_claiming_previous["previous_snapshot_sha256"] = "0" * 64
        self.assertSchemaInvalid(baseline_claiming_previous)

        linked_without_previous_digest = copy.deepcopy(linked_comparison)
        linked_without_previous_digest["previous_snapshot_sha256"] = None
        self.assertSchemaInvalid(linked_without_previous_digest)

        linked_to_freeze = copy.deepcopy(linked_comparison)
        linked_to_freeze["compared_to"] = "freeze_envelope"
        self.assertSchemaInvalid(linked_to_freeze)

        receipt_with_unbound_field = copy.deepcopy(linked_receipt)
        receipt_with_unbound_field["unbound"] = True
        self.assertSchemaInvalid(receipt_with_unbound_field)

    def test_cli_loads_only_validated_raw_or_wrapped_previous_snapshots(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)

        with mock.patch.object(
            Path,
            "read_text",
            return_value=json.dumps(previous, allow_nan=False),
        ):
            self.assertEqual(
                method_delta_cli._load_snapshot(Path("previous.json")),
                previous,
            )

        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        receipt = seal_method_delta_receipt(current, previous=previous)
        with mock.patch.object(
            Path,
            "read_text",
            return_value=json.dumps(receipt, allow_nan=False),
        ):
            self.assertEqual(
                method_delta_cli._load_snapshot(Path("receipt.json")),
                current,
            )

        tampered_raw = copy.deepcopy(previous)
        tampered_raw["invariants"]["no_medicine_claim"]["passed"] = False
        with mock.patch.object(
            Path,
            "read_text",
            return_value=json.dumps(tampered_raw, allow_nan=False),
        ):
            with self.assertRaisesRegex(MethodDeltaError, "snapshot_id does not match"):
                method_delta_cli._load_snapshot(Path("tampered-raw.json"))

        tampered_receipt = copy.deepcopy(receipt)
        tampered_receipt["comparison"]["current_snapshot_sha256"] = "0" * 64
        with mock.patch.object(
            Path,
            "read_text",
            return_value=json.dumps(tampered_receipt, allow_nan=False),
        ):
            with self.assertRaisesRegex(MethodDeltaError, "comparison_id does not match"):
                method_delta_cli._load_snapshot(Path("tampered-receipt.json"))

        substituted_receipt = copy.deepcopy(receipt)
        substituted_receipt["snapshot"]["invariants"]["no_medicine_claim"][
            "passed"
        ] = False
        with mock.patch.object(
            Path,
            "read_text",
            return_value=json.dumps(substituted_receipt, allow_nan=False),
        ):
            with self.assertRaisesRegex(MethodDeltaError, "snapshot_id does not match"):
                method_delta_cli._load_snapshot(Path("substituted-receipt.json"))

        with mock.patch.object(Path, "read_text", return_value="[]"):
            with self.assertRaisesRegex(MethodDeltaError, "must be an object"):
                method_delta_cli._load_snapshot(Path("list.json"))

    def test_cli_loads_previous_before_snapshotting_and_links_parent(self) -> None:
        parent_snapshot = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=9,
            remaining=13.0,
            parent_snapshot_id=parent_snapshot["snapshot_id"],
        )
        receipt = seal_method_delta_receipt(current, previous=parent_snapshot)
        receipt["comparison"]["reviewer"]["agreed"] = True
        calls: list[str] = []

        def load_previous(path: Path) -> dict:
            self.assertEqual(path, Path("previous.json"))
            calls.append("load")
            return parent_snapshot

        def snapshot(
            repo: Path,
            *,
            parent_snapshot_id: str | None,
            recorded_at: str | None,
            exposure_started_at: str | None,
        ) -> dict:
            self.assertEqual(repo, Path("repo"))
            self.assertEqual(parent_snapshot_id, parent_snapshot["snapshot_id"])
            self.assertIsNone(recorded_at)
            self.assertIsNone(exposure_started_at)
            calls.append("snapshot")
            return current

        def seal(current_arg: dict, *, previous: dict | None) -> dict:
            self.assertIs(current_arg, current)
            self.assertIs(previous, parent_snapshot)
            calls.append("seal")
            return receipt

        with (
            mock.patch.object(
                method_delta_cli,
                "_load_snapshot",
                side_effect=load_previous,
            ),
            mock.patch.object(
                method_delta_cli,
                "snapshot_method",
                side_effect=snapshot,
            ),
            mock.patch.object(
                method_delta_cli,
                "seal_method_delta_receipt",
                side_effect=seal,
            ),
            mock.patch.object(
                sys,
                "argv",
                [
                    "assess_method_delta.py",
                    "--repo",
                    "repo",
                    "--previous",
                    "previous.json",
                ],
            ),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(method_delta_cli.main(), 0)
        self.assertEqual(calls, ["load", "snapshot", "seal"])

    def test_cli_existing_output_remains_no_overwrite(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        receipt = seal_method_delta_receipt(current)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.json"
            output.write_text("sentinel", encoding="utf-8")
            with (
                mock.patch.object(
                    method_delta_cli, "snapshot_method", return_value=current
                ),
                mock.patch.object(
                    method_delta_cli,
                    "seal_method_delta_receipt",
                    return_value=receipt,
                ),
                mock.patch.object(
                    sys,
                    "argv",
                    ["assess_method_delta.py", "--output", str(output)],
                ),
                mock.patch.object(sys, "stderr", new=io.StringIO()),
            ):
                with self.assertRaises(SystemExit) as raised:
                    method_delta_cli.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "sentinel")

    def test_exclusive_writer_uses_create_new_and_flushes_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new.json"
            with mock.patch.object(
                method_delta_cli.os,
                "fsync",
                wraps=method_delta_cli.os.fsync,
            ) as fsync:
                method_delta_cli._write_exclusive_durable(output, "payload\n")
            self.assertEqual(output.read_bytes(), b"payload\n")
            self.assertGreaterEqual(fsync.call_count, 1)
            with self.assertRaises(FileExistsError):
                method_delta_cli._write_exclusive_durable(output, "replacement\n")
            self.assertEqual(output.read_bytes(), b"payload\n")

    def test_unused_new_gate_is_worse(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=8,
            remaining=12.0,
            gates=["confirmation", "hypomorph", "exposure"],
            first_blocks=["confirmation", "hypomorph"],
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(result["verdict"], "worse")
        self.assertEqual(result["reason"], "unused_new_gate")

    def test_earlier_block_is_better(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=8,
            remaining=18.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(result["verdict"], "better")
        self.assertEqual(result["reason"], "earlier_block")

    def test_more_families_with_a_diluted_mean_is_not_an_earlier_block(self) -> None:
        previous = _snapshot(families=8, remaining=16.0)
        current = _snapshot(
            families=12,
            remaining=13.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(result["verdict"], "better")
        self.assertEqual(
            result["reason"], "independent_families_blocked_from_advancing"
        )
        self.assertEqual(result["reviewer"]["reviewer_verdict"], "agree_complex")
        self.assertEqual(result["reviewer"]["reason"], "families_up_mean_diluted")

    def test_later_block_without_new_families_is_worse(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=8,
            remaining=6.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(result["verdict"], "worse")
        self.assertEqual(result["reason"], "later_block")

    def test_family_remaining_uses_earliest_block_not_cloned_late_blocks(self) -> None:
        remaining = earliest_remaining_by_family(
            [
                {
                    "kind": "false_path",
                    "blocked_from_advancing": True,
                    "family_id": "identity.incomplete_confirmation",
                    "culture_remaining": 24,
                    "motivation": "literature_family",
                },
                {
                    "kind": "false_path",
                    "blocked_from_advancing": True,
                    "family_id": "identity.incomplete_confirmation",
                    "culture_remaining": 0,
                    "motivation": "literature_family",
                },
            ]
        )
        self.assertEqual(remaining["identity.incomplete_confirmation"], 24)

    def test_cloned_fixture_without_gain_is_complex_not_better(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=8,
            remaining=12.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(result["verdict"], "complex_not_better")

    def test_closing_the_true_path_is_worse(self) -> None:
        previous = _snapshot(families=8, remaining=12.0)
        current = _snapshot(
            families=9,
            remaining=6.0,
            true_opened=0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        current["invariants"]["true_path_opens"] = {
            "passed": False,
            "detail": "true_path_opens_failed",
        }
        current["snapshot_id"] = None
        current = seal_snapshot(
            current,
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(result["verdict"], "invalid")

    def test_arbitrary_invariant_map_cannot_declare_success(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        current["invariants"] = {"anything": {"passed": True}}
        current["snapshot_id"] = None
        current = seal_snapshot(current)
        result = compare_method_delta(current)
        self.assertEqual(result["verdict"], "invalid")
        self.assertEqual(result["reason"], "invariants_failed")

    def test_declared_invariant_must_match_backing_record(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        current["freeze_pointers"]["passed"] = False
        current["snapshot_id"] = None
        current = seal_snapshot(current)
        result = compare_method_delta(current)
        self.assertEqual(result["verdict"], "invalid")
        self.assertEqual(result["reason"], "invariants_failed")

    def test_missing_backing_subrecord_fails_invariants(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        current["public_toolkit"] = {}
        current["snapshot_id"] = None
        current = seal_snapshot(current)
        result = compare_method_delta(current)
        self.assertEqual(result["verdict"], "invalid")

    def test_contradictory_scenario_row_is_rejected(self) -> None:
        # A fabricated row that is both "opened" and "blocked" — or that
        # names a gate outside the structural vocabulary — cannot carry a
        # forged pass through validation.
        for mutate in (
            lambda row: row.update(opened=True),
            lambda row: row.update(blocked_from_advancing=False),
            lambda row: row.update(earliest_nonpass_gate="not_a_gate"),
        ):
            with self.subTest(mutate=mutate):
                current = _snapshot(families=8, remaining=12.0)
                row = current["scenarios"][1]
                mutate(row)
                current["snapshot_id"] = None
                with self.assertRaises(MethodDeltaError):
                    seal_snapshot(current)

    def test_ranking_accuracy_only_gain_is_not_better(self) -> None:
        previous = _snapshot(families=8, remaining=12.0, ranking=0.5)
        current = _snapshot(
            families=8,
            remaining=12.0,
            ranking=1.0,
            parent_snapshot_id=previous["snapshot_id"],
        )
        result = compare_method_delta(current, previous=previous)
        self.assertEqual(result["verdict"], "complex_not_better")
        self.assertEqual(result["reason"], "ranking_accuracy_only")
        self.assertEqual(
            result["internal_joint_verdict"], "complex_not_better"
        )
        self.assertNotEqual(
            result["reviewer"]["reviewer_verdict"], "agree_better"
        )

    def test_declared_invariant_must_match_derivable_scenario_row(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        for row in current["ranking_cases"]:
            if row["case_id"] == "public_toolkit":
                row["observed_step"] = "assay"
                row["correct"] = False
        current["metrics"] = _metrics(
            current["scenarios"], current["ranking_cases"]
        )
        current["snapshot_id"] = None
        current = seal_snapshot(current)
        result = compare_method_delta(current)
        self.assertEqual(result["verdict"], "invalid")
        self.assertEqual(result["reason"], "invariants_failed")

    def test_duplicate_ranking_case_ids_rejected(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        current["ranking_cases"].append(
            dict(current["ranking_cases"][0])
        )
        current["metrics"] = _metrics(
            current["scenarios"], current["ranking_cases"]
        )
        current["snapshot_id"] = None
        with self.assertRaises(MethodDeltaError):
            seal_snapshot(current)

    def test_declared_spend_must_match_its_gate(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        row = current["scenarios"][1]
        row["culture_remaining"] = row["culture_remaining"] + 500
        current["metrics"] = _metrics(
            current["scenarios"], current["ranking_cases"]
        )
        current["snapshot_id"] = None
        with self.assertRaises(MethodDeltaError):
            seal_snapshot(current)

    def test_registered_gates_must_be_structural(self) -> None:
        with self.assertRaises(MethodDeltaError):
            _snapshot(
                families=8, remaining=12.0, gates=["bogus_gate"]
            )

    def test_true_path_opens_derives_from_scenario_rows(self) -> None:
        current = _snapshot(families=8, remaining=12.0, true_opened=0)
        current["invariants"]["true_path_opens"] = {
            "passed": True,
            "detail": "true_path_opens",
        }
        current["snapshot_id"] = None
        current = seal_snapshot(current)
        result = compare_method_delta(current)
        self.assertEqual(result["verdict"], "invalid")

    def test_verdict_never_exceeds_internal_joint_verdict(self) -> None:
        current = _snapshot(families=8, remaining=0.0)
        result = compare_method_delta(current)
        self.assertEqual(result["verdict"], "complex_not_better")
        self.assertEqual(
            result["verdict"], result["internal_joint_verdict"]
        )

    def test_living_bundle_must_match_its_artifacts(self) -> None:
        current = _snapshot(families=8, remaining=12.0)
        current["living_method_integrity"]["bundle_sha256"] = "ff" * 32
        current["snapshot_id"] = None
        current = seal_snapshot(current)
        result = compare_method_delta(current)
        self.assertEqual(result["verdict"], "invalid")

    def test_freeze_pointers_rejects_drive_letter_and_duplicate_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release").mkdir()
            bound = root / "release" / "bound.txt"
            bound.write_text("bound bytes\n", encoding="utf-8")
            digest = hashlib.sha256(bound.read_bytes()).hexdigest()
            (root / MANIFEST_PATH).write_text(
                json.dumps(
                    {
                        "source_commit": "0" * 40,
                        "artifacts": [
                            {
                                "path": "release/bound.txt",
                                "sha256": digest,
                            },
                            {
                                "path": "release/bound.txt",
                                "sha256": digest,
                            },
                            {
                                "path": "C:/outside.txt",
                                "sha256": digest,
                            },
                        ],
                    }
                , allow_nan=False),
                encoding="utf-8",
            )
            pointers = freeze_pointers(root)
            self.assertFalse(pointers["passed"])

    def test_live_snapshot_verifies_frozen_release_bytes(self) -> None:
        current = snapshot_method(ROOT)
        comparison = compare_method_delta(current)
        self.assertTrue(current["invariants"]["true_path_opens"]["passed"])
        self.assertTrue(current["invariants"]["public_confirmation_holds"]["passed"])
        # The release manifest is minted at the release source commit, so
        # every freeze-bound artifact matches its pinned hash on the release
        # tree.
        mismatched = {
            item["path"]
            for item in freeze_pointers(ROOT)["artifacts"]
            if not item["matched"]
        }
        self.assertEqual(mismatched, set())
        self.assertTrue(
            current["invariants"]["freeze_bytes_untouched"]["passed"]
        )
        self.assertTrue(current["invariants"]["living_method_surface_bound"]["passed"])
        self.assertGreater(current["living_method_integrity"]["n_artifacts"], 20)
        self.assertEqual(len(current["living_method_integrity"]["bundle_sha256"]), 64)
        bound_paths = {
            item["path"]
            for item in current["living_method_integrity"]["artifacts"]
        }
        self.assertIn("PIPELINE_SPEC.md", bound_paths)
        self.assertIn(
            "reports/TRACK2_RANDOMIZATION_CONTRACT.md",
            bound_paths,
        )
        self.assertNotIn("reports/TRACK2_SESSION_HANDOFF.md", bound_paths)
        self.assertEqual(comparison["verdict"], "better")
        self.assertEqual(comparison["reason"], "nested_method_beyond_freeze")
        self.assertEqual(len(current["snapshot_id"]), len("sha256:") + 64)
        self.assertEqual(
            comparison["current_snapshot_sha256"], snapshot_sha256(current)
        )
        self.assertIsNone(comparison["previous_snapshot_sha256"])
        validate_method_delta_receipt(seal_method_delta_receipt(current))
        self.assertGreaterEqual(
            current["metrics"][
                "n_independent_families_blocked_from_advancing"
            ],
            8,
        )
        self.assertEqual(current["metrics"]["n_true_opened"], 1)
        self.assertEqual(
            current["metrics"]["culture_remaining_direction"],
            CULTURE_REMAINING_DIRECTION,
        )
        self.assertEqual(current["metrics"]["holdout_families_not_blocked"], [])
        self.assertIn("exposure", current["metrics"]["first_block_gates"])
        self.assertIn("family", current["metrics"]["first_block_gates"])
        families = {
            row["family_id"]
            for row in current["scenarios"]
            if row["kind"] == "false_path" and row["blocked_from_advancing"]
        }
        self.assertIn("false_rescue.exposure_time_profile", families)
        self.assertIn("provenance.exposure_assay_execution", families)
        self.assertIn("design.pre_exposure_arm_allocation", families)
        schedule_row = next(
            row
            for row in current["scenarios"]
            if row["scenario_id"] == "missing_exposure_duration"
        )
        self.assertEqual(schedule_row["earliest_nonpass_gate"], "exposure")
        self.assertEqual(schedule_row["earliest_nonpass_reason"], "time_hours_missing")
        self.assertEqual(schedule_row["terminal_blocked_by"], "hypothesis")
        self.assertEqual(schedule_row["terminal_block_reason"], "observed_without_gate")
        collage_row = next(
            row
            for row in current["scenarios"]
            if row["scenario_id"] == "exposure_assay_file_collage"
        )
        self.assertEqual(collage_row["earliest_nonpass_gate"], "count_identity")
        self.assertEqual(
            collage_row["earliest_nonpass_reason"],
            "exposure_assay_source_mismatch",
        )
        self.assertEqual(collage_row["culture_remaining"], 8)
        allocation_row = next(
            row
            for row in current["scenarios"]
            if row["scenario_id"] == "arm_position_confounding"
        )
        self.assertEqual(allocation_row["family_id"], "design.pre_exposure_arm_allocation")
        self.assertEqual(allocation_row["earliest_nonpass_gate"], "exposure")
        self.assertEqual(allocation_row["culture_remaining"], 13)
        for scenario_id in (
            "arm_exact_column_gradient",
            "arm_row_half_interaction",
            "arm_event_order_alias",
        ):
            row = next(
                item
                for item in current["scenarios"]
                if item["scenario_id"] == scenario_id
            )
            self.assertEqual(row["family_id"], "design.pre_exposure_arm_allocation")
            self.assertEqual(row["earliest_nonpass_gate"], "exposure")
            self.assertEqual(row["culture_remaining"], 13)
        for scenario_id in (
            "arm_local_quadratic_order_artifact",
            "arm_local_order_interaction_artifact",
        ):
            row = next(
                item
                for item in current["scenarios"]
                if item["scenario_id"] == scenario_id
            )
            self.assertEqual(row["family_id"], "design.pre_exposure_arm_allocation")
            self.assertEqual(row["earliest_nonpass_gate"], "count_identity")
            self.assertEqual(row["earliest_nonpass_reason"], "exact_pvalue_above_threshold")
            self.assertEqual(row["culture_remaining"], 8)
        viability_row = next(
            row
            for row in current["scenarios"]
            if row["scenario_id"] == "event_negative_daughter_viability"
        )
        self.assertEqual(viability_row["family_id"], "competing_risk.fitter_daughters")
        self.assertEqual(comparison["reviewer"]["reviewer_verdict"], "agree_better")
        self.assertEqual(comparison["reviewer"]["reason"], "script_and_reviewer_agree")
        self.assertTrue(comparison["reviewer"]["agreed"])


if __name__ == "__main__":
    unittest.main()
