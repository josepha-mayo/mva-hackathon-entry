from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.assay_power import (
    CLAIM_BOUNDARY,
    SCHEMA,
    AssayPowerError,
    assess_assay_power,
)


ROOT = Path(__file__).resolve().parents[1]


def _strict_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


PLAN = json.loads(
    (ROOT / "templates" / "community" / "assay_power.synthetic.json").read_text(
        encoding="utf-8"
    ),
    object_pairs_hook=_strict_object,
    parse_constant=_reject_constant,
)


def _lineage(n_events: int) -> dict:
    runs = []
    for index in range(1, n_events + 1):
        for clone in range(1, 7):
            for arm in ("vehicle", "treatment"):
                runs.append(
                    {
                        "arm": arm,
                        "edit_event_id": f"syn-event-{index}",
                        "clone_id": f"syn-clone-{index}-{clone}",
                        "run_id": f"syn-run-{index}-{clone}-{arm}",
                        "opportunities": 36,
                        "detected_divisions": 36,
                        "event_positive_divisions": 8,
                        "event_negative_divisions": 28,
                        "event_positive_daughters_followed": 8,
                        "event_positive_daughters_reproduced": 2,
                        "event_positive_daughters_died": 1,
                        "event_negative_daughters_followed": 28,
                        "event_negative_daughters_reproduced": 20,
                        "event_negative_daughters_died": 0,
                        "pre_division_death": 0,
                        "no_division": 0,
                        "dropout_censored": 0,
                    }
                )
    return {"schema": "mva-track2-lineage-counts/v1", "runs": runs}


class AssayPowerTests(unittest.TestCase):
    def test_public_plan_is_powered_and_locked(self) -> None:
        result = assess_assay_power(PLAN, _lineage(3))
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["program_effect"], "pass")
        self.assertEqual(result["reason"], "powered_locked_plan")
        self.assertGreaterEqual(result["detection_rate"], 0.8)
        self.assertEqual(result["n_per_arm"], 648)
        # Golden hit count — the seeded certificate is deterministic, so an
        # exact detection rate locks the simulation bitwise. A regression
        # that keeps the rate inside [0.8, 1.0) still fails here.
        self.assertEqual(result["detection_rate"], 0.97)

    def test_unlocked_plan_cannot_pass(self) -> None:
        result = assess_assay_power({**PLAN, "locked": False}, _lineage(3))
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "plan_unlocked")
        self.assertEqual(result["program_effect"], "hold")

    def test_tiny_design_is_underpowered(self) -> None:
        result = assess_assay_power({**PLAN, "n_opportunities": 1}, _lineage(3))
        self.assertEqual(result["reason"], "underpowered_design")

    def test_realized_table_cannot_shrink_the_lock(self) -> None:
        result = assess_assay_power(PLAN, _lineage(2))
        self.assertEqual(result["reason"], "realized_smaller_than_plan")
        self.assertEqual(result["realized_edit_events"], 2)

    def test_pediatric_crash_cannot_look_powered(self) -> None:
        result = assess_assay_power(
            {**PLAN, "locked_treatment_completion_rate": 0.5},
            _lineage(3),
        )
        self.assertEqual(result["reason"], "pediatric_band_incompatible")
        self.assertEqual(result["program_effect"], "hold")

    def test_bulk_fraction_success_rule_cannot_pass_when_masquerade_is_likely(self) -> None:
        result = assess_assay_power(
            {**PLAN, "success_rule": "bulk_aneuploid_drop"},
            _lineage(3),
        )
        self.assertEqual(result["reason"], "false_bulk_rescue_likely")
        self.assertEqual(result["program_effect"], "hold")
        self.assertTrue(result["false_rescue_likely"])

    def test_organ_size_endpoint_cannot_count_as_generation(self) -> None:
        result = assess_assay_power(
            {**PLAN, "endpoint_class": "organ_size"},
            _lineage(3),
        )
        self.assertEqual(result["reason"], "bulk_fraction_not_generation")

    def test_missing_endpoint_and_rule_fail_closed(self) -> None:
        for field in ("endpoint_class", "success_rule"):
            plan = {**PLAN}
            del plan[field]
            with self.assertRaises(AssayPowerError):
                assess_assay_power(plan, _lineage(3))

    def test_inconsistent_rule_cannot_pass_even_when_masquerade_unlikely(self) -> None:
        plan = {**PLAN, "success_rule": "bulk_aneuploid_drop"}
        plan["remaining_population_doublings"] = 60
        result = assess_assay_power(plan, _lineage(3))
        self.assertNotEqual(result["program_effect"], "pass")
        self.assertIn(
            result["reason"],
            {"false_bulk_rescue_likely", "endpoint_rule_mismatch"},
        )

    def test_realized_shallow_clones_cannot_pass(self) -> None:
        runs = [
            {
                "arm": arm,
                "edit_event_id": f"syn-event-{index}",
                "clone_id": f"syn-clone-{index}-1",
                "run_id": f"syn-run-{index}-{arm}",
                "opportunities": 500,
            }
            for index in range(1, 4)
            for arm in ("vehicle", "treatment")
        ]
        result = assess_assay_power(
            PLAN, {"schema": "mva-track2-lineage-counts/v1", "runs": runs}
        )
        self.assertEqual(result["reason"], "realized_smaller_than_plan")

    def test_schema_less_lineage_cannot_supply_realized_depth(self) -> None:
        lineage = _lineage(3)
        del lineage["schema"]
        result = assess_assay_power(PLAN, lineage)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "realized_smaller_than_plan")

    def test_wrong_schema_lineage_fails_closed(self) -> None:
        lineage = _lineage(3)
        lineage["schema"] = "mva-track2-lineage-counts/v0"
        result = assess_assay_power(PLAN, lineage)
        self.assertEqual(result["status"], "not_assessable")

    def test_duplicate_clone_runs_cannot_sum_to_the_floor(self) -> None:
        lineage = _lineage(3)
        doubled = dict(lineage)
        doubled["runs"] = [
            dict(row, opportunities=18, run_id=row["run_id"] + "-a")
            for row in lineage["runs"]
        ] + [
            dict(row, opportunities=18, run_id=row["run_id"] + "-b")
            for row in lineage["runs"]
        ]
        result = assess_assay_power(PLAN, doubled)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "realized_smaller_than_plan")

    def test_realized_shallow_opportunities_cannot_pass(self) -> None:
        lineage = _lineage(3)
        for row in lineage["runs"]:
            row["opportunities"] = 5
        result = assess_assay_power(PLAN, lineage)
        self.assertEqual(result["reason"], "realized_smaller_than_plan")

    def test_equal_low_completion_cannot_look_pediatric(self) -> None:
        result = assess_assay_power(
            {
                **PLAN,
                "locked_vehicle_completion_rate": 0.01,
                "locked_treatment_completion_rate": 0.0105,
            },
            _lineage(3),
        )
        self.assertEqual(result["reason"], "pediatric_band_incompatible")

    def test_stub_rows_without_count_fields_cannot_supply_realized_depth(self) -> None:
        runs = [
            {
                "arm": arm,
                "edit_event_id": f"evt-{index}",
                "clone_id": f"c-{index}-{clone}",
                "run_id": f"r-{index}-{clone}-{arm}",
                "opportunities": 36,
            }
            for index in range(1, 4)
            for clone in range(1, 7)
            for arm in ("vehicle", "treatment")
        ]
        result = assess_assay_power(
            PLAN, {"schema": "mva-track2-lineage-counts/v1", "runs": runs}
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "realized_smaller_than_plan")

    def test_inconsistent_count_fields_cannot_supply_realized_depth(self) -> None:
        lineage = _lineage(3)
        for row in lineage["runs"]:
            row["opportunities"] = 40
        result = assess_assay_power(PLAN, lineage)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "realized_smaller_than_plan")

    def test_remaining_population_doublings_has_a_ceiling(self) -> None:
        plan = {**PLAN, "remaining_population_doublings": 10**9}
        with self.assertRaisesRegex(AssayPowerError, "ceiling"):
            assess_assay_power(plan)

    def test_wrong_schema_fails_closed(self) -> None:
        with self.assertRaises(AssayPowerError):
            assess_assay_power({"schema": "other", "locked": True})

    def test_missing_lineage_cannot_pass(self) -> None:
        result = assess_assay_power(PLAN)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "realized_lineage_required")
        self.assertNotEqual(result["program_effect"], "pass")

    def test_zero_minimum_detection_is_rejected(self) -> None:
        plan = {**PLAN, "minimum_detection": 0.0}
        with self.assertRaisesRegex(AssayPowerError, "minimum_detection"):
            assess_assay_power(plan, _lineage(3))

    def test_detection_rate_prices_the_production_analyzer(self) -> None:
        result = assess_assay_power(PLAN, _lineage(3))
        self.assertEqual(
            result["detection_rate_basis"], "event_level_lineage_analyzer"
        )
        self.assertEqual(result["n_sims"], 400)
        self.assertGreater(result["detection_rate_mc_lower_bound"], 0.8)
        self.assertTrue(result["simulation_assumptions"])

    def test_marginal_margin_is_underpowered_under_the_real_rule(self) -> None:
        # A treatment rate just inside the 0.75 pooled cutoff could pass
        # the old point-estimate certificate; the event-level interval
        # cannot certify a marginal reduction at three events.
        plan = {
            **PLAN,
            "locked_vehicle_error_rate": 0.30,
            "locked_treatment_error_rate": 0.21,
        }
        result = assess_assay_power(plan, _lineage(3))
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "underpowered")

    def test_oversized_design_fails_closed(self) -> None:
        plan = {**PLAN, "n_clones_per_event": 400, "n_opportunities": 200}
        result = assess_assay_power(plan, _lineage(3))
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "design_exceeds_simulation_fidelity")

    def test_locked_death_and_dropout_feed_the_partition(self) -> None:
        # Marginal interpretation: death + dropout + completion <= 1 per
        # arm, matching the analyzer's completed/enrolled estimand.
        plan = {
            **PLAN,
            "locked_vehicle_completion_rate": 0.95,
            "locked_treatment_completion_rate": 0.95,
            "locked_pre_division_death_rate": 0.02,
            "locked_dropout_rate": 0.02,
        }
        result = assess_assay_power(plan, _lineage(3))
        self.assertIn(result["status"], {"pass", "not_assessable"})
        self.assertIn(
            result["reason"],
            {
                "powered_locked_plan",
                "underpowered",
                "underpowered_mc_uncertainty",
            },
        )

    def test_partition_rates_cannot_exceed_one(self) -> None:
        plan = {
            **PLAN,
            "locked_pre_division_death_rate": 0.5,
            "locked_dropout_rate": 0.6,
        }
        with self.assertRaisesRegex(AssayPowerError, "partition"):
            assess_assay_power(plan, _lineage(3))

    def test_between_event_concentration_must_be_at_least_one(self) -> None:
        plan = {**PLAN, "locked_between_event_concentration": 0.5}
        with self.assertRaisesRegex(AssayPowerError, "concentration"):
            assess_assay_power(plan, _lineage(3))


if __name__ == "__main__":
    unittest.main()
