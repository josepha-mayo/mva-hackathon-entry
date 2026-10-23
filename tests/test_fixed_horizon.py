"""Counterexamples for a fixed-horizon estimand, not real-study validation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from mva_hackathon.fixed_horizon import FollowupError, SCHEMA, assess_fixed_horizon_followup


def stamp(hours):
    return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def example():
    study = {"schema": SCHEMA, "study_id": "syn-followup", "synthetic_only": True,
        "horizon_hours": 48, "prespecified_at": stamp(-24), "adjudication_blinded": True,
        "adjudication_locked_at": stamp(168), "unblinded_at": stamp(169), "founders": [], "daughters": []}
    for arm in ("vehicle", "treatment"):
        parent = "syn-" + arm
        children = [parent + "-a", parent + "-b"]
        study["founders"].append({"founder_id": parent, "arm": arm, "edit_event_id": "syn-event-1",
            "exposure_started_at": stamp(0), "division_completed_at": stamp(12),
            "division_class": "bipolar", "daughter_ids": children})
        for child in children:
            study["daughters"].append({"daughter_id": child, "founder_id": parent,
                "observation_started_at": stamp(12), "observed_until": stamp(18),
                "continuous_observation": True, "first_reproduced_at": stamp(18), "died_at": None})
    return study


def group(result, arm):
    return next(row for row in result["per_event_arm"] if row["arm"] == arm)


class FixedHorizonTests(unittest.TestCase):
    def test_early_first_events_resolve_without_waiting_to_horizon(self):
        result = assess_fixed_horizon_followup(example())
        self.assertTrue(result["timing_and_accounting_qualified"])
        self.assertEqual(group(result, "treatment")["reproduced_by_horizon"], 2)
        self.assertFalse(result["advancement_granted"])

    def test_faster_mother_division_with_same_daughter_history_is_qualified(self):
        study = example()
        study["founders"][1]["division_completed_at"] = stamp(6)
        for row in study["daughters"][2:]:
            row.update(observation_started_at=stamp(6), observed_until=stamp(12), first_reproduced_at=stamp(12))
        result = assess_fixed_horizon_followup(study)
        self.assertTrue(result["timing_and_accounting_qualified"])
        self.assertEqual(group(result, "vehicle")["reproduced_by_horizon"], group(result, "treatment")["reproduced_by_horizon"])

    def test_unequal_terminal_event_times_can_both_be_within_horizon(self):
        study = example()
        for row in study["daughters"]:
            event = 12 + (0.1 if row["founder_id"] == "syn-treatment" else 24)
            row.update(observed_until=stamp(event), first_reproduced_at=stamp(event))
        self.assertTrue(assess_fixed_horizon_followup(study)["timing_and_accounting_qualified"])

    def test_72_hour_reproduction_is_not_within_a_48_hour_horizon(self):
        study = example()
        for row in study["daughters"][2:]:
            row.update(observed_until=stamp(84), first_reproduced_at=stamp(84))
        result = assess_fixed_horizon_followup(study)
        self.assertTrue(result["timing_and_accounting_qualified"])
        self.assertEqual(group(result, "treatment")["reproduced_by_horizon"], 0)
        self.assertEqual(group(result, "treatment")["alive_without_reproduction"], 2)
        self.assertEqual(group(result, "treatment")["latest_recorded_observation"], stamp(84))

    def test_surviving_nondividers_at_horizon_are_retained(self):
        study = example()
        study["daughters"][0].update(observed_until=stamp(60), first_reproduced_at=None)
        study["daughters"][1].update(observed_until=stamp(24), first_reproduced_at=None, died_at=stamp(24))
        result = assess_fixed_horizon_followup(study)
        row = group(result, "vehicle")
        self.assertTrue(result["timing_and_accounting_qualified"])
        self.assertEqual(row["alive_without_reproduction"], 1)
        self.assertEqual(row["died_before_reproduction"], 1)
        self.assertEqual(row["reproduction_fraction_lower_bound"], 0)
        self.assertEqual(row["reproduction_fraction_upper_bound"], 0)

    def test_early_loss_has_bounds_instead_of_becoming_a_nondivider(self):
        study = example()
        study["daughters"][0].update(first_reproduced_at=None)
        result = assess_fixed_horizon_followup(study)
        row = group(result, "vehicle")
        self.assertFalse(result["timing_and_accounting_qualified"])
        self.assertEqual((row["reproduction_fraction_lower_bound"], row["reproduction_fraction_upper_bound"]), (0.5, 1))

    def test_missing_daughter_is_not_removed_from_denominator(self):
        study = example()
        study["daughters"].pop()
        result = assess_fixed_horizon_followup(study)
        self.assertFalse(result["timing_and_accounting_qualified"])
        self.assertEqual(result["missing_daughter_observations"], 1)
        self.assertEqual(group(result, "treatment")["expected_daughters"], 2)

    def test_observation_gaps_do_not_establish_first_event(self):
        study = example()
        study["daughters"][0]["continuous_observation"] = False
        self.assertFalse(assess_fixed_horizon_followup(study)["timing_and_accounting_qualified"])
        study = example()
        study["daughters"][0]["observation_started_at"] = stamp(13)
        self.assertFalse(assess_fixed_horizon_followup(study)["timing_and_accounting_qualified"])

    def test_lock_cannot_precede_recorded_data(self):
        study = example()
        study["adjudication_locked_at"] = stamp(15)
        with self.assertRaisesRegex(FollowupError, "observation interval"):
            assess_fixed_horizon_followup(study)

    def test_protocol_cannot_be_selected_after_exposure(self):
        study = example()
        study["prespecified_at"] = stamp(1)
        with self.assertRaisesRegex(FollowupError, "protocol"):
            assess_fixed_horizon_followup(study)

    def test_unblinding_cannot_precede_lock(self):
        study = example()
        study["unblinded_at"] = stamp(15)
        with self.assertRaisesRegex(FollowupError, "unblinding"):
            assess_fixed_horizon_followup(study)

    def test_unblinded_adjudication_does_not_qualify(self):
        study = example()
        study["adjudication_blinded"] = False
        self.assertFalse(assess_fixed_horizon_followup(study)["timing_and_accounting_qualified"])

    def test_events_must_be_recorded_inside_the_observation_interval(self):
        for event in (11, 19):
            with self.subTest(event=event):
                study = example()
                study["daughters"][0]["first_reproduced_at"] = stamp(event)
                with self.assertRaisesRegex(FollowupError, "event must fall"):
                    assess_fixed_horizon_followup(study)

    def test_conflicting_or_duplicate_first_events_are_rejected(self):
        study = example()
        study["daughters"][0]["died_at"] = stamp(17)
        with self.assertRaisesRegex(FollowupError, "first competing event"):
            assess_fixed_horizon_followup(study)
        study = example()
        study["daughters"].append(deepcopy(study["daughters"][0]))
        with self.assertRaisesRegex(FollowupError, "duplicate"):
            assess_fixed_horizon_followup(study)

    def test_horizon_is_explicit_not_implicitly_48_hours(self):
        study = example()
        study["horizon_hours"] = 4
        result = assess_fixed_horizon_followup(study)
        self.assertEqual(group(result, "vehicle")["reproduced_by_horizon"], 0)
        self.assertEqual(group(result, "vehicle")["alive_without_reproduction"], 2)
        study.pop("horizon_hours")
        with self.assertRaises(FollowupError):
            assess_fixed_horizon_followup(study)

    def test_legacy_schema_cannot_inherit_timing_assurance(self):
        with self.assertRaises(FollowupError):
            assess_fixed_horizon_followup({"schema": "mva-track2-lineage-study/v1"})


if __name__ == "__main__":
    unittest.main()
