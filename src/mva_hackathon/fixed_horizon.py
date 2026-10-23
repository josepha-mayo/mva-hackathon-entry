"""Explicit first-event daughter follow-up at a prespecified horizon.

This unsigned research supplement replaces no signed artifact. It addresses
timing/accounting only: it cannot award a clean generation, clone-safety,
biological or clinical certificate. Event times are not observation horizons.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
import re
from typing import Any

SCHEMA = "mva-fixed-horizon-followup/v1"
OUTCOMES = ("reproduced_by_horizon", "died_before_reproduction", "alive_without_reproduction", "unresolved")


class FollowupError(ValueError):
    """Missing or contradictory protocol/observation information."""


def _object(value: Any, required: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != required:
        raise FollowupError(f"{name} must contain exactly: {', '.join(sorted(required))}")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", value) or len(value) > 128:
        raise FollowupError(f"{name} must be an opaque identifier")
    return value


def _time(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise FollowupError(f"{name} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FollowupError(f"{name} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FollowupError(f"{name} must be a UTC timestamp")
    return parsed


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def assess_fixed_horizon_followup(payload: dict) -> dict:
    root = _object(payload, {"schema", "study_id", "synthetic_only", "horizon_hours", "prespecified_at",
        "adjudication_blinded", "adjudication_locked_at", "unblinded_at", "founders", "daughters"}, "study")
    if root["schema"] != SCHEMA:
        raise FollowupError("explicit fixed-horizon schema required; legacy records do not establish an observation horizon")
    study_id = _identifier(root["study_id"], "study_id")
    if type(root["synthetic_only"]) is not bool or type(root["adjudication_blinded"]) is not bool:
        raise FollowupError("synthetic_only and adjudication_blinded must be booleans")
    hours = root["horizon_hours"]
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(hours) or hours <= 0:
        raise FollowupError("horizon_hours must be finite and positive")
    try:
        horizon = timedelta(hours=hours)
    except OverflowError as exc:
        raise FollowupError("horizon_hours is outside timestamp range") from exc
    if horizon <= timedelta(0):
        raise FollowupError("horizon_hours is below timestamp resolution")
    prespecified = _time(root["prespecified_at"], "prespecified_at")
    locked = _time(root["adjudication_locked_at"], "adjudication_locked_at")
    unblinded = None if root["unblinded_at"] is None else _time(root["unblinded_at"], "unblinded_at")
    if unblinded is not None and unblinded < locked:
        raise FollowupError("unblinding cannot precede adjudication lock")
    if not isinstance(root["founders"], list) or not root["founders"]:
        raise FollowupError("at least one completed founder division is required")
    if not isinstance(root["daughters"], list):
        raise FollowupError("daughters must be a list")

    founders = {}
    expected = {}
    groups = defaultdict(lambda: {"expected_daughters": 0, **{key: 0 for key in OUTCOMES},
        "latest_horizon_end": None, "latest_recorded_observation": None})
    for item in root["founders"]:
        row = _object(item, {"founder_id", "arm", "edit_event_id", "exposure_started_at",
            "division_completed_at", "division_class", "daughter_ids"}, "founder")
        key = _identifier(row["founder_id"], "founder_id")
        event = _identifier(row["edit_event_id"], "edit_event_id")
        if key in founders:
            raise FollowupError("duplicate founder")
        if row["arm"] not in ("vehicle", "treatment"):
            raise FollowupError("unknown arm")
        exposure = _time(row["exposure_started_at"], "exposure_started_at")
        birth = _time(row["division_completed_at"], "division_completed_at")
        if not prespecified < exposure <= birth <= locked:
            raise FollowupError("protocol, exposure, completion and lock are not ordered")
        children = row["daughter_ids"]
        if not isinstance(children, list):
            raise FollowupError("daughter_ids must list all expected daughters")
        if row["division_class"] == "bipolar":
            valid_number = len(children) == 2
        elif row["division_class"] == "multipolar":
            valid_number = len(children) >= 3
        else:
            raise FollowupError("unknown division_class")
        if not valid_number:
            raise FollowupError("expected daughter count contradicts division class")
        try:
            end = birth + horizon
        except OverflowError as exc:
            raise FollowupError("horizon end is outside timestamp range") from exc
        founders[key] = (row, birth, end)
        group = groups[(event, row["arm"])]
        group["expected_daughters"] += len(children)
        group["latest_horizon_end"] = max(group["latest_horizon_end"] or end, end)
        for child in children:
            child = _identifier(child, "daughter_id")
            if child in expected:
                raise FollowupError("duplicate expected daughter")
            expected[child] = key

    seen = set()
    for item in root["daughters"]:
        row = _object(item, {"daughter_id", "founder_id", "observation_started_at", "observed_until",
            "continuous_observation", "first_reproduced_at", "died_at"}, "daughter")
        child = _identifier(row["daughter_id"], "daughter_id")
        if child in seen:
            raise FollowupError("duplicate daughter observation")
        seen.add(child)
        if child not in expected or row["founder_id"] != expected[child]:
            raise FollowupError("daughter does not match its expected founder")
        parent, birth, end = founders[row["founder_id"]]
        start = _time(row["observation_started_at"], "observation_started_at")
        observed = _time(row["observed_until"], "observed_until")
        if type(row["continuous_observation"]) is not bool:
            raise FollowupError("continuous_observation must be boolean")
        reproduction = None if row["first_reproduced_at"] is None else _time(row["first_reproduced_at"], "first_reproduced_at")
        death = None if row["died_at"] is None else _time(row["died_at"], "died_at")
        if reproduction is not None and death is not None:
            raise FollowupError("record the first competing event only, not both reproduction and death")
        event_time = reproduction if reproduction is not None else death
        if not start <= observed <= locked or observed < birth:
            raise FollowupError("observation interval and adjudication lock are not ordered")
        if event_time is not None and not max(start, birth) <= event_time <= observed:
            raise FollowupError("event must fall within the observed postdivision interval")
        group = groups[(parent["edit_event_id"], parent["arm"])]
        group["latest_recorded_observation"] = max(group["latest_recorded_observation"] or observed, observed)
        if not row["continuous_observation"] or start > birth:
            outcome = "unresolved"
        elif event_time is not None and event_time <= end:
            outcome = "reproduced_by_horizon" if reproduction is not None else "died_before_reproduction"
        elif observed >= end:
            # A first event after the horizon cannot become a within-horizon
            # reproduction. The uninterrupted earlier window is still known.
            outcome = "alive_without_reproduction"
        else:
            outcome = "unresolved"
        group[outcome] += 1

    for child in expected.keys() - seen:
        parent, _, _ = founders[expected[child]]
        groups[(parent["edit_event_id"], parent["arm"])]["unresolved"] += 1
    results = []
    for (event, arm), counts in sorted(groups.items()):
        n = counts["expected_daughters"]
        assert sum(counts[key] for key in OUTCOMES) == n
        results.append({"edit_event_id": event, "arm": arm, **counts,
            "latest_horizon_end": _stamp(counts["latest_horizon_end"]),
            "latest_recorded_observation": None if counts["latest_recorded_observation"] is None else _stamp(counts["latest_recorded_observation"]),
            "reproduction_fraction_lower_bound": counts["reproduced_by_horizon"] / n,
            "reproduction_fraction_upper_bound": (counts["reproduced_by_horizon"] + counts["unresolved"]) / n})
    complete = all(row["unresolved"] == 0 for row in results)
    return {"schema": "mva-fixed-horizon-followup-assessment/v1", "study_id": study_id,
        "synthetic_only": root["synthetic_only"], "horizon_hours": hours,
        "timing_and_accounting_qualified": complete and root["adjudication_blinded"],
        "adjudication_blinded": root["adjudication_blinded"],
        "missing_daughter_observations": len(expected.keys() - seen), "per_event_arm": results,
        "advancement_granted": False,
        "claim_boundary": "Declared timing, complete accounting and fixed-horizon descriptive bounds only. Recorded declarations are not independently verified. Not generation analysis, clone safety, calibrated inference, biological efficacy or clinical benefit."}
