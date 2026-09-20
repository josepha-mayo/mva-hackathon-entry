from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.next_experiment import (
    CLAIM_BOUNDARY,
    SCHEMA,
    NextExperimentError,
    assess_next_experiment,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSHEET = json.loads(
    (ROOT / "templates" / "community" / "causal_chain_worksheet.synthetic.json").read_text(
        encoding="utf-8"
    )
)


def _step(name: str, effect: str, *, skipped: bool = False) -> dict:
    return {
        "name": name,
        "skipped": skipped,
        "program_effect": effect,
        "status": "pass" if effect == "pass" else "not_assessable",
    }


class NextExperimentTests(unittest.TestCase):
    def test_pass_effect_requires_pass_status(self) -> None:
        fabricated = _step("confirmation", "pass")
        fabricated["status"] = "not_assessable"
        with self.assertRaisesRegex(
            NextExperimentError, "pass program_effect requires a pass status"
        ):
            assess_next_experiment(WORKSHEET, [fabricated])
        absent = _step("confirmation", "pass")
        del absent["status"]
        with self.assertRaisesRegex(
            NextExperimentError, "pass program_effect requires a pass status"
        ):
            assess_next_experiment(WORKSHEET, [absent])

    def test_public_worksheet_recommends_confirmation(self) -> None:
        result = assess_next_experiment(WORKSHEET, [])
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["recommended_step"], "confirmation")
        self.assertEqual(result["recommended_gate_id"], "syn-gate-confirm")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "identity_first")
        self.assertFalse(result["identity_complete"])

    def test_later_identity_before_confirmation_stops(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-phase"}
        result = assess_next_experiment(
            worksheet,
            [_step("confirmation", "hold")],
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "later_identity_before_confirmation")
        self.assertEqual(result["recommended_step"], "confirmation")

    def test_probe_before_identity_stops(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-replication"}
        result = assess_next_experiment(
            worksheet,
            [_step("confirmation", "hold")],
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["program_effect"], "stop")
        self.assertEqual(result["reason"], "probe_before_identity")
        self.assertEqual(result["recommended_step"], "confirmation")

    def test_imaging_is_allowed_after_identity(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-stability"}
        result = assess_next_experiment(
            worksheet,
            [
                _step("confirmation", "pass"),
                _step("phase", "pass"),
                _step("transcript", "pass"),
                _step("hypomorph", "hold"),
            ],
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["recommended_step"], "hypomorph")
        self.assertTrue(result["identity_complete"])

    def test_imaging_before_assay_stops(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-replication"}
        result = assess_next_experiment(
            worksheet,
            [
                _step("confirmation", "pass"),
                _step("phase", "pass"),
                _step("transcript", "pass"),
                _step("hypomorph", "hold"),
            ],
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "imaging_before_assay")
        self.assertEqual(result["recommended_step"], "hypomorph")

    def test_isogenic_alias_is_the_missense_assay(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-isogenic"}
        result = assess_next_experiment(
            worksheet,
            [
                _step("confirmation", "pass"),
                _step("phase", "pass"),
                _step("transcript", "pass"),
                _step("hypomorph", "hold"),
            ],
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["recommended_step"], "hypomorph")

    def test_missing_declared_gate_fails_closed(self) -> None:
        with self.assertRaises(NextExperimentError):
            assess_next_experiment({"schema": WORKSHEET["schema"]}, [])

    def test_unknown_declared_gate_cannot_skip_identity(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-unlisted"}
        result = assess_next_experiment(
            worksheet,
            [_step("confirmation", "hold")],
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["program_effect"], "stop")
        self.assertEqual(result["reason"], "unknown_next_gate")
        self.assertEqual(result["recommended_step"], "confirmation")

    def test_stale_earlier_declaration_holds(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-confirm"}
        result = assess_next_experiment(
            worksheet,
            [
                _step("confirmation", "pass"),
                _step("phase", "pass"),
                _step("transcript", "pass"),
                _step("hypomorph", "stop"),
            ],
        )
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "stale_declared_gate")
        self.assertEqual(result["recommended_step"], "hypomorph")
        self.assertTrue(result["identity_complete"])

    def test_generation_alias_is_concordance_when_concordance_is_next(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-generation"}
        result = assess_next_experiment(
            worksheet,
            [
                _step("confirmation", "pass"),
                _step("phase", "pass"),
                _step("transcript", "pass"),
                _step("hypomorph", "pass"),
                _step("exposure", "pass"),
                _step("count_identity", "pass"),
                _step("assay_power", "pass"),
                _step("clone_safety", "pass"),
                _step("concordance", "hold"),
            ],
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "identity_first")
        self.assertEqual(result["recommended_step"], "concordance")
        self.assertEqual(result["recommended_gate_id"], "syn-gate-generation")

    def test_generation_alias_cannot_skip_the_missense_assay(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-generation"}
        result = assess_next_experiment(
            worksheet,
            [
                _step("confirmation", "pass"),
                _step("phase", "pass"),
                _step("transcript", "pass"),
                _step("hypomorph", "hold"),
            ],
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "imaging_before_assay")
        self.assertEqual(result["recommended_step"], "hypomorph")

    def test_unknown_declared_gate_cannot_stand_in_after_identity(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-unlisted"}
        result = assess_next_experiment(
            worksheet,
            [
                _step("confirmation", "pass"),
                _step("phase", "pass"),
                _step("transcript", "pass"),
                _step("hypomorph", "hold"),
            ],
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unknown_next_gate")
        self.assertEqual(result["recommended_step"], "hypomorph")

    def test_duplicate_step_names_fail_closed(self) -> None:
        worksheet = {**WORKSHEET, "declared_next_gate_id": "syn-gate-isogenic"}
        with self.assertRaisesRegex(NextExperimentError, "repeat a gate name"):
            assess_next_experiment(
                worksheet,
                [
                    _step("confirmation", "hold"),
                    _step("confirmation", "pass"),
                    _step("phase", "pass"),
                    _step("transcript", "pass"),
                ],
            )

    def test_non_mapping_steps_fail_closed(self) -> None:
        with self.assertRaisesRegex(NextExperimentError, "gate result objects"):
            assess_next_experiment(WORKSHEET, ["confirmation"])

    def test_missing_step_name_fails_closed(self) -> None:
        with self.assertRaisesRegex(NextExperimentError, "canonical gate name"):
            assess_next_experiment(WORKSHEET, [{"program_effect": "pass"}])

    def test_noncanonical_step_name_fails_closed(self) -> None:
        for name in ("Confirmation", "confirmation ", "bogus"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    NextExperimentError, "canonical gate name"
                ):
                    assess_next_experiment(
                        WORKSHEET,
                        [{"name": name, "program_effect": "pass"}],
                    )

    def test_nonvocab_program_effect_fails_closed(self) -> None:
        for effect in ("advance", "passed", None, True):
            with self.subTest(effect=effect):
                with self.assertRaisesRegex(
                    NextExperimentError, "program_effect"
                ):
                    assess_next_experiment(
                        WORKSHEET,
                        [{"name": "confirmation", "program_effect": effect}],
                    )

    def test_status_and_effect_disagreement_fails_closed(self) -> None:
        with self.assertRaisesRegex(NextExperimentError, "cannot disagree"):
            assess_next_experiment(
                WORKSHEET,
                [
                    {
                        "name": "confirmation",
                        "program_effect": "pass",
                        "status": "stop",
                    }
                ],
            )

    def test_verdict_is_marked_advisory(self) -> None:
        result = assess_next_experiment(WORKSHEET, [])
        self.assertTrue(result["advisory_only"])


if __name__ == "__main__":
    unittest.main()
