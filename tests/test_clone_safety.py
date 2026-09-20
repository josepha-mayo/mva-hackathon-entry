from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.clone_safety import (
    CLAIM_BOUNDARY,
    DEATH_RATIO_STOP,
    MAXIMUM_RESOLVED,
    MINIMUM_RESOLVED,
    MIN_RATIO_STOP,
    RATIO_STOP,
    SCHEMA,
    STATUSES,
    CloneSafetyError,
    assess_clone_safety,
)
from mva_hackathon.lineage import (
    build_adversarial_fixture,
    export_first_attempt_aggregates,
)


def _export(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema": "mva-track2-lineage-counts/v1",
        "study_id": "syn-clone-safety",
        "synthetic_only": True,
        "lock_state": "locked",
        "blinded": True,
        "forbidden_keys_absent": [],
        "claim_boundary": "synthetic",
        "runs": rows,
    }


def _row(
    arm: str,
    *,
    clone_id: str = "syn-clone-1",
    followed: int,
    reproduced: int,
    event_id: str = "syn-event-1",
    run_id: str = "syn-run-1",
    positive_died: int | None = None,
    negative_followed: int = 10,
    negative_reproduced: int = 8,
    negative_died: int | None = None,
    positive_divisions: int | None = None,
    negative_divisions: int | None = None,
) -> dict[str, object]:
    if positive_divisions is None:
        positive_divisions = -(-followed // 2)
    if negative_divisions is None:
        negative_divisions = -(-negative_followed // 2)
    # Default to fully resolved fates: observed daughters either reproduce or
    # die. Passing an explicit died value below the remainder leaves censored
    # daughters — the unresolved channel the contract fails closed on.
    if positive_died is None:
        positive_died = followed - reproduced
    if negative_died is None:
        negative_died = negative_followed - negative_reproduced
    return {
        "arm": arm,
        "edit_event_id": event_id,
        "clone_id": clone_id,
        "run_id": run_id,
        "event_positive_divisions": positive_divisions,
        "event_negative_divisions": negative_divisions,
        "event_positive_daughters_followed": followed,
        "event_positive_daughters_reproduced": reproduced,
        "event_positive_daughters_died": positive_died,
        "event_negative_daughters_followed": negative_followed,
        "event_negative_daughters_reproduced": negative_reproduced,
        "event_negative_daughters_died": negative_died,
    }


class CloneSafetyTests(unittest.TestCase):
    def test_equal_rates_pass(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=10, reproduced=4),
                    _row("treatment", followed=10, reproduced=4),
                ]
            )
        )
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["clone_safety_stop"])
        self.assertFalse(result["advancement_blocked"])
        self.assertEqual(result["nests"][0]["ratio"], 1.0)

    def test_fitter_error_daughters_stop(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=10, reproduced=4),
                    _row("treatment", followed=10, reproduced=8),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertTrue(result["clone_safety_stop"])
        self.assertTrue(result["advancement_blocked"])
        self.assertGreater(result["nests"][0]["ratio"], RATIO_STOP)
        self.assertEqual(result["nests"][0]["reason"], "error_daughter_reproduction_ratio")

    def test_exact_ratio_boundary_stops(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=8, reproduced=4),
                    _row("treatment", followed=8, reproduced=5),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertTrue(result["clone_safety_stop"])
        self.assertEqual(result["nests"][0]["ratio"], RATIO_STOP)

    def test_exact_death_ratio_boundary_stops(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row(
                        "vehicle",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=7,
                        negative_died=1,
                    ),
                    _row(
                        "treatment",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=6,
                        negative_died=2,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertTrue(result["clone_safety_stop"])
        self.assertEqual(
            result["nests"][0]["negative_death_ratio"], DEATH_RATIO_STOP
        )

    def test_unbounded_increase_stops(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=10, reproduced=0),
                    _row("treatment", followed=10, reproduced=3),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertTrue(result["nests"][0]["ratio_unbounded"])
        self.assertIsNone(result["nests"][0]["ratio"])

    def test_incomplete_positive_followup_blocks(self) -> None:
        # Treatment error-daughter follow-up above the count floor but below
        # the two-per-division potential leaves unaccounted daughters whose
        # reproduction could be hidden — not_assessable, never a pass.
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=10, reproduced=4),
                    _row(
                        "treatment",
                        followed=10,
                        reproduced=4,
                        positive_divisions=8,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["clone_safety_stop"])
        self.assertTrue(result["advancement_blocked"])
        self.assertEqual(
            result["nests"][0]["reason"], "incomplete_positive_followup"
        )
        self.assertFalse(result["nests"][0]["positive_followup_complete"])

    def test_multipolar_slots_under_followed_blocks(self) -> None:
        # Declared multipolar slots widen the follow-up obligation: tracking
        # only the bipolar default leaves multipolar daughters unaccounted.
        treatment = _row(
            "treatment", followed=10, reproduced=4, positive_divisions=5
        )
        treatment["event_positive_multipolar_divisions"] = 1
        treatment["event_positive_daughter_slots"] = 12
        result = assess_clone_safety(
            _export([_row("vehicle", followed=10, reproduced=4), treatment])
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["nests"][0]["reason"], "incomplete_positive_followup"
        )

    def test_multipolar_slots_fully_followed_can_pass(self) -> None:
        treatment = _row(
            "treatment", followed=12, reproduced=4, positive_divisions=5
        )
        treatment["event_positive_multipolar_divisions"] = 1
        treatment["event_positive_daughter_slots"] = 12
        result = assess_clone_safety(
            _export([_row("vehicle", followed=10, reproduced=4), treatment])
        )
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["clone_safety_stop"])

    def test_multipolar_slots_require_the_declaration(self) -> None:
        # A slots claim beyond the bipolar default without a co-declared
        # multipolar count is a contract error, not a soft hold.
        treatment = _row(
            "treatment", followed=12, reproduced=4, positive_divisions=5
        )
        treatment["event_positive_daughter_slots"] = 12
        with self.assertRaises(CloneSafetyError):
            assess_clone_safety(
                _export([_row("vehicle", followed=10, reproduced=4), treatment])
            )
        treatment["event_positive_multipolar_divisions"] = 6
        with self.assertRaises(CloneSafetyError):
            assess_clone_safety(
                _export([_row("vehicle", followed=10, reproduced=4), treatment])
            )

    def test_daughter_slot_bounds_fail_closed(self) -> None:
        treatment = _row(
            "treatment", followed=10, reproduced=4, positive_divisions=4
        )
        treatment["event_positive_daughter_slots"] = 17
        with self.assertRaises(CloneSafetyError):
            assess_clone_safety(
                _export([_row("vehicle", followed=10, reproduced=4), treatment])
            )
        treatment = _row(
            "treatment", followed=4, reproduced=2, positive_divisions=4
        )
        treatment["event_positive_daughter_slots"] = 7
        with self.assertRaises(CloneSafetyError):
            assess_clone_safety(
                _export([_row("vehicle", followed=10, reproduced=4), treatment])
            )
        treatment = _row("treatment", followed=10, reproduced=4)
        treatment["event_negative_daughter_slots"] = 11
        with self.assertRaises(CloneSafetyError):
            assess_clone_safety(
                _export([_row("vehicle", followed=10, reproduced=4), treatment])
            )

    def test_sparse_vehicle_negative_followup_is_not_assessable(self) -> None:
        # Under-following vehicle non-error daughters skews the vehicle
        # positive-vs-negative baseline the relative ratio is judged
        # against — the asymmetry guard is bidirectional.
        result = assess_clone_safety(
            _export(
                [
                    _row(
                        "vehicle",
                        followed=10,
                        reproduced=4,
                        negative_followed=8,
                        negative_divisions=32,
                    ),
                    _row(
                        "treatment",
                        followed=10,
                        reproduced=4,
                        negative_followed=10,
                        negative_divisions=5,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["clone_safety_stop"])
        self.assertFalse(result["nests"][0]["negative_followup_symmetric"])
        self.assertEqual(
            result["nests"][0]["reason"], "asymmetric_negative_followup"
        )

    def test_insufficient_followup_blocks_without_calling_stop(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=MINIMUM_RESOLVED, reproduced=4),
                    _row("treatment", followed=MINIMUM_RESOLVED - 1, reproduced=7),
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["clone_safety_stop"])
        self.assertTrue(result["advancement_blocked"])
        self.assertEqual(
            result["nests"][0]["reason"], "insufficient_positive_followup"
        )

    def test_nests_are_not_pooled_across_clones(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", clone_id="syn-clone-1", followed=10, reproduced=8),
                    _row("treatment", clone_id="syn-clone-1", followed=10, reproduced=8),
                    _row("vehicle", clone_id="syn-clone-2", followed=10, reproduced=2),
                    _row("treatment", clone_id="syn-clone-2", followed=10, reproduced=8),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        by_clone = {item["clone_id"]: item["status"] for item in result["nests"]}
        self.assertEqual(by_clone["syn-clone-1"], "pass")
        self.assertEqual(by_clone["syn-clone-2"], "stop")

    def test_relative_error_daughter_preservation_stops(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row(
                        "vehicle",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=6,
                    ),
                    _row(
                        "treatment",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=3,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(
            result["nests"][0]["relative_positive_negative_reproduction_ratio"],
            2.0,
        )
        self.assertEqual(
            result["nests"][0]["reason"],
            "relative_error_daughter_preservation_ratio",
        )

    def test_event_negative_death_increase_stops(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row(
                        "vehicle",
                        followed=8,
                        reproduced=4,
                        negative_followed=10,
                        negative_reproduced=9,
                        negative_died=1,
                    ),
                    _row(
                        "treatment",
                        followed=8,
                        reproduced=1,
                        negative_followed=10,
                        negative_reproduced=4,
                        negative_died=5,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertGreater(result["nests"][0]["negative_death_ratio"], DEATH_RATIO_STOP)
        self.assertEqual(result["nests"][0]["reason"], "negative_daughter_death_ratio")

    def test_symmetric_positive_and_negative_viability_passes(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row(
                        "vehicle",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=6,
                        negative_died=2,
                    ),
                    _row(
                        "treatment",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=6,
                        negative_died=2,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "pass")

    def test_insufficient_event_negative_followup_holds(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=8, reproduced=4, negative_followed=8),
                    _row(
                        "treatment",
                        followed=8,
                        reproduced=4,
                        negative_followed=7,
                        negative_reproduced=5,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertIn(
            result["nests"][0]["reason"],
            {"insufficient_stratified_followup", "insufficient_negative_followup"},
        )

    def test_negative_death_zero_boundary_is_fail_closed(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row("vehicle", followed=8, reproduced=4, negative_died=0),
                    _row("treatment", followed=8, reproduced=4, negative_died=1),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertTrue(result["nests"][0]["negative_death_ratio_unbounded"])

    def test_zero_control_negative_reproduction_is_not_assessable(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row(
                        "vehicle",
                        followed=8,
                        reproduced=4,
                        negative_reproduced=0,
                    ),
                    _row(
                        "treatment",
                        followed=8,
                        reproduced=4,
                        negative_reproduced=2,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")

    def test_reproduced_plus_died_cannot_exceed_followed(self) -> None:
        with self.assertRaisesRegex(CloneSafetyError, "reproduced plus died"):
            assess_clone_safety(
                _export(
                    [
                        _row(
                            "vehicle",
                            followed=8,
                            reproduced=4,
                            negative_followed=8,
                            negative_reproduced=7,
                            negative_died=2,
                        ),
                        _row("treatment", followed=8, reproduced=4),
                    ]
                )
            )

    def test_hazardous_nest_beats_an_insufficient_nest(self) -> None:
        result = assess_clone_safety(
            _export(
                [
                    _row(
                        "vehicle",
                        clone_id="syn-clone-1",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=6,
                    ),
                    _row(
                        "treatment",
                        clone_id="syn-clone-1",
                        followed=8,
                        reproduced=4,
                        negative_followed=8,
                        negative_reproduced=3,
                    ),
                    _row(
                        "vehicle",
                        clone_id="syn-clone-2",
                        followed=8,
                        reproduced=4,
                        negative_followed=7,
                        negative_reproduced=5,
                    ),
                    _row(
                        "treatment",
                        clone_id="syn-clone-2",
                        followed=8,
                        reproduced=4,
                        negative_followed=7,
                        negative_reproduced=5,
                    ),
                ]
            )
        )
        self.assertEqual(result["status"], "stop")

    def test_malformed_counts_raise_even_when_unlocked(self) -> None:
        payload = _export(
            [
                _row("vehicle", followed=8, reproduced=4),
                _row("treatment", followed=8, reproduced=4),
            ]
        )
        payload["lock_state"] = "unlocked"
        payload["runs"][0]["event_negative_daughters_died"] = True
        with self.assertRaisesRegex(CloneSafetyError, "non-negative integer"):
            assess_clone_safety(payload)

    def test_unlocked_counts_cannot_pass_or_stop(self) -> None:
        payload = _export(
            [
                _row("vehicle", followed=10, reproduced=4),
                _row("treatment", followed=10, reproduced=8),
            ]
        )
        payload["lock_state"] = "unlocked"
        result = assess_clone_safety(payload)
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["clone_safety_stop"])
        self.assertTrue(result["advancement_blocked"])
        self.assertEqual(result["nests"][0]["status"], "stop")

    def test_unblinded_counts_cannot_pass(self) -> None:
        payload = _export(
            [
                _row("vehicle", followed=10, reproduced=4),
                _row("treatment", followed=10, reproduced=4),
            ]
        )
        payload["blinded"] = False
        result = assess_clone_safety(payload)
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["clone_safety_stop"])
        self.assertTrue(result["advancement_blocked"])

    def test_duplicate_arm_fails_closed(self) -> None:
        with self.assertRaisesRegex(CloneSafetyError, "duplicate"):
            assess_clone_safety(
                _export(
                    [
                        _row("vehicle", followed=10, reproduced=4),
                        _row("vehicle", followed=10, reproduced=5),
                        _row("treatment", followed=10, reproduced=4),
                    ]
                )
            )

    def test_nonfinite_or_nonnumeric_ratio_thresholds_fail_closed(self) -> None:
        payload = _export(
            [
                _row("vehicle", followed=10, reproduced=4),
                _row("treatment", followed=10, reproduced=8),
            ]
        )
        for value in (float("nan"), float("inf"), float("-inf"), True, "2.0"):
            with self.subTest(field="ratio_stop", value=value):
                with self.assertRaisesRegex(CloneSafetyError, "finite"):
                    assess_clone_safety(payload, ratio_stop=value)  # type: ignore[arg-type]
            with self.subTest(field="death_ratio_stop", value=value):
                with self.assertRaisesRegex(CloneSafetyError, "finite"):
                    assess_clone_safety(
                        payload, death_ratio_stop=value  # type: ignore[arg-type]
                    )

    def test_followup_floor_rejects_bool_and_noninteger_values(self) -> None:
        payload = _export(
            [
                _row("vehicle", followed=10, reproduced=4),
                _row("treatment", followed=10, reproduced=4),
            ]
        )
        for value in (True, False, 1.5, "8", 0, -1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CloneSafetyError, "positive integer"):
                    assess_clone_safety(
                        payload, minimum_resolved=value  # type: ignore[arg-type]
                    )

    def test_thresholds_cannot_be_lenient(self) -> None:
        payload = _export(
            [
                _row("vehicle", followed=10, reproduced=4),
                _row("treatment", followed=10, reproduced=4),
            ]
        )
        with self.assertRaisesRegex(CloneSafetyError, "ceiling"):
            assess_clone_safety(payload, ratio_stop=1e308)
        with self.assertRaisesRegex(CloneSafetyError, "ceiling"):
            assess_clone_safety(payload, death_ratio_stop=1e308)
        with self.assertRaisesRegex(CloneSafetyError, "safety minimum"):
            assess_clone_safety(payload, minimum_resolved=1)

    def test_thresholds_cannot_be_vacuously_strict(self) -> None:
        payload = _export(
            [
                _row("vehicle", followed=10, reproduced=4),
                _row("treatment", followed=10, reproduced=4),
            ]
        )
        with self.assertRaisesRegex(CloneSafetyError, "safety floor"):
            assess_clone_safety(payload, ratio_stop=1.000001)
        with self.assertRaisesRegex(CloneSafetyError, "safety floor"):
            assess_clone_safety(payload, death_ratio_stop=1.000001)
        with self.assertRaisesRegex(CloneSafetyError, "safety maximum"):
            assess_clone_safety(payload, minimum_resolved=10**9)
        # Boundary values remain admissible.
        result = assess_clone_safety(
            payload, ratio_stop=MIN_RATIO_STOP, minimum_resolved=MAXIMUM_RESOLVED
        )
        self.assertIn(result["status"], STATUSES)

    def test_wrong_schema_fails_closed(self) -> None:
        with self.assertRaisesRegex(CloneSafetyError, "lineage-count"):
            assess_clone_safety({"schema": "mva-generation-selection-benchmark/v3", "runs": []})

    def test_clean_generation_export_is_assessable(self) -> None:
        export = export_first_attempt_aggregates(
            build_adversarial_fixture("clean_generation")
        )
        result = assess_clone_safety(export)
        self.assertIn(result["status"], STATUSES)
        self.assertTrue(result["nests"])


if __name__ == "__main__":
    unittest.main()
