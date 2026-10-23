"""Isolated audit of timing semantics in the frozen lineage contract.

All records are invented. This does not change the repository or its tests.
Run from the repository root with Python 3.12+. This prints invented results only.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mva_hackathon.clone_safety import assess_clone_safety
from mva_hackathon.lineage import (
    analyze_lineage_study,
    export_first_attempt_aggregates,
    lineage_study_from_counts,
)


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def make_study(*, treatment_attempt_hours: float = 12.0):
    counts = {
        f"syn-event-{i}": {
            "vehicle": {"completed_error": 96, "completed_no_error": 336},
            "treatment": {"completed_error": 24, "completed_no_error": 408},
        }
        for i in (1, 2, 3)
    }
    original = lineage_study_from_counts(
        study_id="syn-timing-audit",
        per_event=counts,
        attempt_hours_by_arm={"vehicle": 12.0, "treatment": treatment_attempt_hours},
    )
    # Resolve both recorded daughters to avoid the separate clone-safety
    # completeness stop. Equal complete reproduction rates are deliberate.
    return dataclasses.replace(
        original,
        daughters=tuple(dataclasses.replace(d, outcome="reproduced") for d in original.daughters),
    )


def summary(study) -> dict:
    analysis = analyze_lineage_study(study)
    clone = assess_clone_safety(export_first_attempt_aggregates(study))
    parents = {f.founder_id: f for f in study.founders}
    by_arm = {"vehicle": [], "treatment": []}
    for daughter in study.daughters:
        parent = parents[daughter.founder_id]
        elapsed = (
            datetime.fromisoformat(daughter.observed_at.replace("Z", "+00:00"))
            - datetime.fromisoformat(parent.first_attempt_ended_at.replace("Z", "+00:00"))
        ).total_seconds() / 3600
        by_arm[parent.arm].append(elapsed)
    return {
        "actual_daughter_elapsed_hours": {
            arm: {"minimum": min(values), "maximum": max(values)}
            for arm, values in by_arm.items()
        },
        "reported_followup_hours_ratio": analysis["followup_hours_ratio"],
        "unequal_followup_flag": analysis["flags"]["unequal_followup"],
        "clean_generation_signal": analysis["status"]["clean_generation_signal"],
        "measurement_valid": analysis["status"]["measurement_valid"],
        "interpretation": analysis["interpretation"],
        "clone_safety": clone["status"],
    }


def main() -> None:
    baseline = make_study()
    parents = {f.founder_id: f for f in baseline.founders}
    mismatched_daughters = dataclasses.replace(
        baseline,
        daughters=tuple(
            dataclasses.replace(
                d,
                observed_at=stamp(
                    datetime.fromisoformat(parents[d.founder_id].first_attempt_ended_at.replace("Z", "+00:00"))
                    + timedelta(hours=0.1 if parents[d.founder_id].arm == "treatment" else 24.0)
                ),
            )
            for d in baseline.daughters
        ),
    )
    before_observations = dataclasses.replace(
        baseline,
        adjudication_locked_at=baseline.founders[0].exposure_started_at,
    )
    # Isolate the report's fixed-48-hour endpoint from the lock-order issue:
    # treatment reproduction is at72h after division, with lock after day7.
    # It cannot be a reproduction-within48h event even if it later occurs.
    late_treatment_events = dataclasses.replace(
        baseline,
        adjudication_locked_at=stamp(
            datetime.fromisoformat(baseline.adjudication_locked_at.replace("Z", "+00:00"))
            + timedelta(days=7)
        ),
        daughters=tuple(
            dataclasses.replace(
                d,
                observed_at=stamp(
                    datetime.fromisoformat(parents[d.founder_id].first_attempt_ended_at.replace("Z", "+00:00"))
                    + timedelta(hours=72.0 if parents[d.founder_id].arm == "treatment" else 6.0)
                ),
            )
            for d in baseline.daughters
        ),
    )
    result = {
        "scope": "invented records, software timing semantics only; no biological result",
        "baseline": summary(baseline),
        "same_daughter_terminal_times_faster_mother": summary(make_study(treatment_attempt_hours=6.0)),
        "same_mitosis_different_terminal_observation_times": summary(mismatched_daughters),
        "adjudication_lock_before_all_observations": summary(before_observations),
        "treatment_reproductions_after_report_48h_horizon": summary(late_treatment_events),
    }
    assert result["baseline"]["clean_generation_signal"]
    assert result["baseline"]["clone_safety"] == "pass"
    assert result["same_daughter_terminal_times_faster_mother"]["unequal_followup_flag"]
    assert result["same_mitosis_different_terminal_observation_times"]["clean_generation_signal"]
    assert result["adjudication_lock_before_all_observations"]["clean_generation_signal"]
    assert result["treatment_reproductions_after_report_48h_horizon"]["clean_generation_signal"]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
