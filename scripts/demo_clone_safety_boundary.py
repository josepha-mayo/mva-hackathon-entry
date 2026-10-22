"""A threshold pass does not establish absence of observed fitness gain.

All counts are invented. This exercises one existing observed-label checker,
not the complete pipeline, an experimental study or clinical safety.
"""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mva_hackathon.clone_safety import assess_clone_safety


def _row(arm: str, reproduced: int) -> dict:
    return {
        "arm": arm, "edit_event_id": "syn-event", "clone_id": "syn-clone", "run_id": "syn-run",
        "event_positive_divisions": 50, "event_negative_divisions": 50,
        "event_positive_daughters_followed": 100,
        "event_positive_daughters_reproduced": reproduced,
        "event_positive_daughters_died": 100 - reproduced,
        "event_negative_daughters_followed": 100,
        "event_negative_daughters_reproduced": 80,
        "event_negative_daughters_died": 20,
    }


def demonstration() -> dict:
    cases = []
    for name, reproduced in (("equal", 40), ("observed_gain_below_threshold", 48), ("configured_stop_boundary", 50)):
        fixture = {
            "schema": "mva-track2-lineage-counts/v1", "study_id": "syn-threshold-audit",
            "synthetic_only": True, "lock_state": "locked", "blinded": True,
            "forbidden_keys_absent": [], "claim_boundary": "Invented count-table demonstration only.",
            "runs": [_row("vehicle", 40), _row("treatment", reproduced)],
        }
        result = assess_clone_safety(fixture)
        cases.append({"case": name, "vehicle_reproduced_of_100": 40,
            "treatment_reproduced_of_100": reproduced,
            "observed_reproduction_ratio": result["nests"][0]["ratio"],
            "configured_gate_status": result["status"]})
    assert [case["configured_gate_status"] for case in cases] == ["pass", "pass", "stop"]
    assert [case["observed_reproduction_ratio"] for case in cases] == [1.0, 1.2, 1.25]
    return {"synthetic_only": True, "cases": cases,
        "demonstrates_absence_of_fitness_gain": False,
        "thresholds_changed_by_demo": False,
        "claim_boundary": "One configured observed-label threshold gate only. Not full-pipeline eligibility, true genotype, biological safety, a harm margin, study power or clinical benefit.",
        "design_requirement": "Justify confirmatory harm margins and event/background-aware uncertainty bounds before unblinding; a threshold pass cannot substitute for them."}


if __name__ == "__main__":
    print(json.dumps(demonstration(), indent=2))
