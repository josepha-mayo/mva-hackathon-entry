"""Clone-safety contract nested under edit event, clone, and run.

A treatment arm that leaves error-line daughters more able to reproduce
than vehicle is a stop. Fitness of abnormal daughters is not rescue and
is not efficacy evidence. Unlocked or unblinded counts cannot pass or stop.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from mva_hackathon.provenance import receipt_sha256

from mva_hackathon.lineage import lineage_source_fingerprint


SCHEMA = "mva-track2-clone-safety/v2"
LINEAGE_COUNTS_SCHEMA = "mva-track2-lineage-counts/v1"
RATIO_STOP = 1.25
DEATH_RATIO_STOP = 2.0
MINIMUM_RESOLVED = 8
# A stop threshold below this fires on noise — a trivially-easy stop is as
# vacuous as a trivially-easy pass.
MIN_RATIO_STOP = 1.1
# A follow-up floor this high makes every nest not_assessable — the check
# would never actually run.
MAXIMUM_RESOLVED = 128
STATUSES = ("pass", "stop", "not_assessable")
ARMS = ("vehicle", "treatment")
CLAIM_BOUNDARY = (
    "Observed-label clone-safety software contract only; higher absolute "
    "event-positive daughter reproduction, disproportionate event-positive "
    "versus event-negative reproduction, or event-negative daughter death "
    "above the configured ratio is a stop, not a rescue. Observed labels do "
    "not establish true genotype, mechanism, treatment safety, efficacy, or "
    "clinical benefit."
)


class CloneSafetyError(ValueError):
    """Raised when a clone-safety input violates its contract."""


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise CloneSafetyError(f"{field} must be a non-empty identifier")
    if not value.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise CloneSafetyError(f"{field} contains unsupported characters")
    if not value[0].isalpha():
        raise CloneSafetyError(f"{field} must start with a letter")
    return value


def _nonneg(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CloneSafetyError(f"{field} must be a non-negative integer")
    return value


def _rate(reproduced: int, followed: int) -> float | None:
    if followed <= 0:
        return None
    return reproduced / followed


def _ratio_threshold(value: object, field: str, ceiling: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 1.0
    ):
        raise CloneSafetyError(f"{field} must be finite and greater than 1")
    if float(value) < MIN_RATIO_STOP:
        raise CloneSafetyError(
            f"{field} cannot drop below the fixed safety floor {MIN_RATIO_STOP}"
        )
    if float(value) > ceiling:
        raise CloneSafetyError(
            f"{field} cannot exceed the fixed safety ceiling {ceiling}"
        )
    return float(value)


def _followup_floor(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CloneSafetyError("follow-up floor must be a positive integer")
    if value < MINIMUM_RESOLVED:
        raise CloneSafetyError(
            "follow-up floor cannot drop below the fixed safety minimum"
        )
    if value > MAXIMUM_RESOLVED:
        raise CloneSafetyError(
            "follow-up floor cannot exceed the fixed safety maximum "
            f"{MAXIMUM_RESOLVED}"
        )
    return value


def _label_counts(row: Mapping[str, Any], label: str) -> dict[str, int | None]:
    prefix = f"event_{label}_daughters"
    followed = _nonneg(row.get(f"{prefix}_followed"), f"{prefix}_followed")
    reproduced = _nonneg(
        row.get(f"{prefix}_reproduced"), f"{prefix}_reproduced"
    )
    died = _nonneg(row.get(f"{prefix}_died"), f"{prefix}_died")
    if reproduced + died > followed:
        raise CloneSafetyError(
            f"{label} reproduced plus died daughters cannot exceed followed daughters"
        )
    divisions: int | None = None
    division_field = f"event_{label}_divisions"
    slots: int | None = None
    slots_field = f"event_{label}_daughter_slots"
    multipolar = 0
    if label == "positive":
        multipolar_raw = row.get("event_positive_multipolar_divisions")
        if multipolar_raw is not None:
            multipolar = _nonneg(
                multipolar_raw, "event_positive_multipolar_divisions"
            )
    if division_field in row:
        divisions = _nonneg(row.get(division_field), division_field)
        if multipolar > divisions:
            raise CloneSafetyError(
                "multipolar divisions cannot exceed event-positive divisions"
            )
        if slots_field in row:
            slots = _nonneg(row.get(slots_field), slots_field)
            if slots < 2 * divisions + multipolar:
                raise CloneSafetyError(
                    f"{label} daughter slots cannot be fewer than two per division"
                )
            if label == "negative" and slots > 2 * divisions:
                raise CloneSafetyError(
                    "clean divisions cannot produce more than two daughters"
                )
            if slots > 2 * divisions + 2 * multipolar:
                raise CloneSafetyError(
                    f"{label} daughter slots exceed the multipolar bound"
                )
        else:
            if multipolar:
                raise CloneSafetyError(
                    "declared multipolar divisions require declared daughter slots"
                )
            slots = 2 * divisions
        if followed > slots:
            raise CloneSafetyError(
                f"{label} followed daughters exceed the declared daughter slots"
            )
    return {
        "followed": followed,
        # A censored daughter is unaccounted progeny: it was observed but
        # never reached a terminal fate, so it satisfies no obligation and
        # enters no rate denominator. Resolved fates are reproduced + died.
        "resolved": reproduced + died,
        "reproduced": reproduced,
        "died": died,
        "divisions": divisions,
        "slots": slots,
    }


def _round_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def assess_clone_safety(
    export: Mapping[str, Any],
    *,
    ratio_stop: float = RATIO_STOP,
    death_ratio_stop: float = DEATH_RATIO_STOP,
    minimum_resolved: int = MINIMUM_RESOLVED,
) -> dict[str, Any]:
    """Stop observed-label fitness or viability shifts that mimic rescue."""

    ratio_stop = _ratio_threshold(ratio_stop, "ratio stop", RATIO_STOP)
    death_ratio_stop = _ratio_threshold(
        death_ratio_stop, "death ratio stop", DEATH_RATIO_STOP
    )
    minimum_resolved = _followup_floor(minimum_resolved)
    if not isinstance(export, Mapping):
        raise CloneSafetyError("clone-safety input must be an object")
    if export.get("schema") != LINEAGE_COUNTS_SCHEMA:
        raise CloneSafetyError("clone-safety accepts lineage-count exports only")
    runs = export.get("runs")
    if not isinstance(runs, list) or not runs:
        raise CloneSafetyError("lineage-count export has no runs")
    if len(runs) > 500_000:
        raise CloneSafetyError("lineage-count export exceeds the run ceiling")

    grouped: dict[tuple[str, str, str], dict[str, dict[str, int]]] = {}
    for row in runs:
        if not isinstance(row, Mapping):
            raise CloneSafetyError("count row must be an object")
        arm = row.get("arm")
        if arm not in ARMS:
            raise CloneSafetyError("arm must be vehicle or treatment")
        nest = (
            _identifier(row.get("edit_event_id"), "edit_event_id"),
            _identifier(row.get("clone_id"), "clone_id"),
            _identifier(row.get("run_id"), "run_id"),
        )
        positive = _label_counts(row, "positive")
        negative = _label_counts(row, "negative")
        by_arm = grouped.setdefault(nest, {})
        if arm in by_arm:
            raise CloneSafetyError("duplicate arm inside an event-clone-run nest")
        by_arm[str(arm)] = {"positive": positive, "negative": negative}

    nests = []
    for nest_key in sorted(grouped):
        by_arm = grouped[nest_key]
        event_id, clone_id, run_id = nest_key
        payload: dict[str, Any] = {
            "edit_event_id": event_id,
            "clone_id": clone_id,
            "run_id": run_id,
            "vehicle_followed": by_arm.get("vehicle", {})
            .get("positive", {})
            .get("followed", 0),
            "vehicle_reproduced": by_arm.get("vehicle", {})
            .get("positive", {})
            .get("reproduced", 0),
            "treatment_followed": by_arm.get("treatment", {})
            .get("positive", {})
            .get("followed", 0),
            "treatment_reproduced": by_arm.get("treatment", {})
            .get("positive", {})
            .get("reproduced", 0),
            "vehicle_rate": None,
            "treatment_rate": None,
            "ratio": None,
            "ratio_unbounded": False,
            "vehicle_negative_followed": by_arm.get("vehicle", {})
            .get("negative", {})
            .get("followed", 0),
            "vehicle_negative_reproduced": by_arm.get("vehicle", {})
            .get("negative", {})
            .get("reproduced", 0),
            "vehicle_negative_died": by_arm.get("vehicle", {})
            .get("negative", {})
            .get("died", 0),
            "treatment_negative_followed": by_arm.get("treatment", {})
            .get("negative", {})
            .get("followed", 0),
            "treatment_negative_reproduced": by_arm.get("treatment", {})
            .get("negative", {})
            .get("reproduced", 0),
            "treatment_negative_died": by_arm.get("treatment", {})
            .get("negative", {})
            .get("died", 0),
            "vehicle_negative_reproduction_rate": None,
            "treatment_negative_reproduction_rate": None,
            "vehicle_negative_death_rate": None,
            "treatment_negative_death_rate": None,
            "relative_positive_negative_reproduction_ratio": None,
            "relative_reproduction_ratio_unbounded": False,
            "negative_death_ratio": None,
            "negative_death_ratio_unbounded": False,
            "checks": [],
            "status": "not_assessable",
            "reason": "missing_arm",
        }
        if "vehicle" not in by_arm or "treatment" not in by_arm:
            nests.append(payload)
            continue
        # Rates are computed on resolved fates only: a censored daughter is
        # unaccounted and belongs in neither numerator nor denominator.
        vehicle_resolved = by_arm["vehicle"]["positive"]["resolved"]
        treatment_resolved = by_arm["treatment"]["positive"]["resolved"]
        vehicle_negative_resolved = by_arm["vehicle"]["negative"]["resolved"]
        treatment_negative_resolved = by_arm["treatment"]["negative"]["resolved"]
        vehicle_rate = _rate(payload["vehicle_reproduced"], vehicle_resolved)
        treatment_rate = _rate(
            payload["treatment_reproduced"], treatment_resolved
        )
        vehicle_negative_rate = _rate(
            payload["vehicle_negative_reproduced"],
            vehicle_negative_resolved,
        )
        treatment_negative_rate = _rate(
            payload["treatment_negative_reproduced"],
            treatment_negative_resolved,
        )
        vehicle_negative_death = _rate(
            payload["vehicle_negative_died"], vehicle_negative_resolved
        )
        treatment_negative_death = _rate(
            payload["treatment_negative_died"],
            treatment_negative_resolved,
        )
        payload["vehicle_rate"] = _round_ratio(vehicle_rate)
        payload["treatment_rate"] = _round_ratio(treatment_rate)
        payload["vehicle_negative_reproduction_rate"] = _round_ratio(
            vehicle_negative_rate
        )
        payload["treatment_negative_reproduction_rate"] = _round_ratio(
            treatment_negative_rate
        )
        payload["vehicle_negative_death_rate"] = _round_ratio(
            vehicle_negative_death
        )
        payload["treatment_negative_death_rate"] = _round_ratio(
            treatment_negative_death
        )

        stop_reasons: list[str] = []
        hold_reasons: list[str] = []
        positive_adequate = (
            vehicle_resolved >= minimum_resolved
            and treatment_resolved >= minimum_resolved
        )
        negative_adequate = (
            vehicle_negative_resolved >= minimum_resolved
            and treatment_negative_resolved >= minimum_resolved
        )
        # Every error-positive daughter on both arms must carry a known fate:
        # unfollowed treatment daughters could hide a reproduction gain, and
        # over-selected vehicle daughters could inflate the baseline rate the
        # ratio is judged against — both directions mint a missed stop.
        vehicle_positive_divisions = by_arm["vehicle"]["positive"]["divisions"]
        treatment_positive_divisions = by_arm["treatment"]["positive"]["divisions"]
        positive_followup_complete = all(
            counts["divisions"] is not None
            and counts["resolved"] >= counts["slots"]
            for counts in (
                by_arm["vehicle"]["positive"],
                by_arm["treatment"]["positive"],
            )
        )
        # The negative stratum keeps the count floor plus a bidirectional
        # symmetry guard on resolved fates: resolving one arm's non-error
        # daughters far less thoroughly than the other's skews that arm's
        # negative rate — a sparse treatment stratum hides death or arrest
        # behind sparse counts, and a sparse vehicle stratum inflates the
        # vehicle positive-vs-negative baseline the relative ratio is judged
        # against. Either direction can mask a treatment fitness gain.
        vehicle_negative = by_arm["vehicle"]["negative"]
        treatment_negative = by_arm["treatment"]["negative"]
        if (
            vehicle_negative["divisions"]
            and treatment_negative["divisions"]
        ):
            negative_followup_symmetric = (
                4
                * treatment_negative["resolved"]
                * vehicle_negative["divisions"]
                >= 3
                * treatment_negative["divisions"]
                * vehicle_negative["resolved"]
                and 4
                * vehicle_negative["resolved"]
                * treatment_negative["divisions"]
                >= 3
                * vehicle_negative["divisions"]
                * treatment_negative["resolved"]
            )
        else:
            negative_followup_symmetric = (
                vehicle_negative["divisions"] == 0
                and treatment_negative["divisions"] == 0
            )
        payload["vehicle_positive_divisions"] = vehicle_positive_divisions
        payload["treatment_positive_divisions"] = treatment_positive_divisions
        payload["positive_followup_complete"] = positive_followup_complete
        payload["negative_followup_symmetric"] = negative_followup_symmetric

        positive_check = {
            "name": "error_daughter_reproduction",
            "status": "pass",
            "reason": "within_ratio",
            "ratio": None,
            "unbounded": False,
        }
        if not positive_adequate or vehicle_rate is None or treatment_rate is None:
            positive_check.update(
                status="not_assessable", reason="insufficient_positive_followup"
            )
            hold_reasons.append("insufficient_positive_followup")
        elif not positive_followup_complete:
            positive_check.update(
                status="not_assessable", reason="incomplete_positive_followup"
            )
            hold_reasons.append("incomplete_positive_followup")
        elif vehicle_rate == 0.0:
            if treatment_rate > 0.0:
                payload["ratio_unbounded"] = True
                positive_check.update(
                    status="stop",
                    reason="error_daughter_reproduction_unbounded",
                    unbounded=True,
                )
                stop_reasons.append("error_daughter_reproduction_unbounded")
            else:
                positive_check.update(
                    status="not_assessable",
                    reason="positive_reproduction_zero_boundary",
                )
                hold_reasons.append("positive_reproduction_zero_boundary")
        else:
            ratio = treatment_rate / vehicle_rate
            payload["ratio"] = _round_ratio(ratio)
            positive_check["ratio"] = _round_ratio(ratio)
            if ratio >= ratio_stop:
                positive_check.update(
                    status="stop", reason="error_daughter_reproduction_ratio"
                )
                stop_reasons.append("error_daughter_reproduction_ratio")
        payload["checks"].append(positive_check)

        relative_check = {
            "name": "relative_positive_negative_reproduction",
            "status": "pass",
            "reason": "within_ratio",
            "ratio": None,
            "unbounded": False,
        }
        if not positive_adequate or not negative_adequate:
            relative_check.update(
                status="not_assessable", reason="insufficient_stratified_followup"
            )
            hold_reasons.append("insufficient_stratified_followup")
        elif not negative_followup_symmetric:
            relative_check.update(
                status="not_assessable", reason="asymmetric_negative_followup"
            )
            hold_reasons.append("asymmetric_negative_followup")
        elif vehicle_negative_rate == 0.0:
            relative_check.update(
                status="not_assessable",
                reason="vehicle_negative_reproduction_zero_boundary",
            )
            hold_reasons.append("vehicle_negative_reproduction_zero_boundary")
        elif treatment_negative_rate == 0.0:
            if treatment_rate is not None and treatment_rate > 0.0:
                payload["relative_reproduction_ratio_unbounded"] = True
                relative_check.update(
                    status="stop",
                    reason="relative_error_daughter_preservation_unbounded",
                    unbounded=True,
                )
                stop_reasons.append("relative_error_daughter_preservation_unbounded")
            else:
                relative_check.update(
                    status="not_assessable",
                    reason="treatment_reproduction_zero_boundary",
                )
                hold_reasons.append("treatment_reproduction_zero_boundary")
        elif vehicle_rate == 0.0:
            relative_check.update(
                status="not_assessable",
                reason="vehicle_positive_reproduction_zero_boundary",
            )
            hold_reasons.append("vehicle_positive_reproduction_zero_boundary")
        else:
            vehicle_relative = vehicle_rate / vehicle_negative_rate
            treatment_relative = treatment_rate / treatment_negative_rate
            relative_ratio = treatment_relative / vehicle_relative
            payload["relative_positive_negative_reproduction_ratio"] = _round_ratio(
                relative_ratio
            )
            relative_check["ratio"] = _round_ratio(relative_ratio)
            if relative_ratio >= ratio_stop:
                relative_check.update(
                    status="stop",
                    reason="relative_error_daughter_preservation_ratio",
                )
                stop_reasons.append("relative_error_daughter_preservation_ratio")
        payload["checks"].append(relative_check)

        death_check = {
            "name": "event_negative_daughter_death",
            "status": "pass",
            "reason": "within_ratio",
            "ratio": None,
            "unbounded": False,
        }
        if (
            not negative_adequate
            or vehicle_negative_death is None
            or treatment_negative_death is None
        ):
            death_check.update(
                status="not_assessable", reason="insufficient_negative_followup"
            )
            hold_reasons.append("insufficient_negative_followup")
        elif not negative_followup_symmetric:
            death_check.update(
                status="not_assessable", reason="asymmetric_negative_followup"
            )
            hold_reasons.append("asymmetric_negative_followup")
        elif vehicle_negative_death == 0.0:
            if treatment_negative_death > 0.0:
                payload["negative_death_ratio_unbounded"] = True
                death_check.update(
                    status="stop",
                    reason="negative_daughter_death_unbounded",
                    unbounded=True,
                )
                stop_reasons.append("negative_daughter_death_unbounded")
            else:
                payload["negative_death_ratio"] = 1.0
                death_check["ratio"] = 1.0
                death_check["reason"] = "no_negative_daughter_death"
        else:
            death_ratio = treatment_negative_death / vehicle_negative_death
            payload["negative_death_ratio"] = _round_ratio(death_ratio)
            death_check["ratio"] = _round_ratio(death_ratio)
            if death_ratio >= death_ratio_stop:
                death_check.update(
                    status="stop", reason="negative_daughter_death_ratio"
                )
                stop_reasons.append("negative_daughter_death_ratio")
        payload["checks"].append(death_check)

        if stop_reasons:
            payload["status"] = "stop"
            payload["reason"] = stop_reasons[0]
        elif hold_reasons:
            payload["status"] = "not_assessable"
            payload["reason"] = hold_reasons[0]
        else:
            payload["status"] = "pass"
            payload["reason"] = "within_configured_ratios"
        nests.append(payload)

    statuses = {item["status"] for item in nests}
    if export.get("lock_state") != "locked":
        overall = "not_assessable"
        clone_safety_stop = False
    elif export.get("blinded") is not True:
        overall = "not_assessable"
        clone_safety_stop = False
    elif "stop" in statuses:
        overall = "stop"
        clone_safety_stop = True
    elif "not_assessable" in statuses or not nests:
        overall = "not_assessable"
        clone_safety_stop = False
    else:
        overall = "pass"
        clone_safety_stop = False
    result = {
        "schema": SCHEMA,
        "synthetic_only": bool(export.get("synthetic_only", True)),
        "claim_boundary": CLAIM_BOUNDARY,
        "ratio_stop": ratio_stop,
        "death_ratio_stop": death_ratio_stop,
        "minimum_resolved": minimum_resolved,
        "status": overall,
        "program_effect": (
            "pass" if overall == "pass" else ("stop" if overall == "stop" else "hold")
        ),
        "clone_safety_stop": clone_safety_stop,
        "advancement_blocked": overall != "pass",
        "source_fingerprint": lineage_source_fingerprint(export),
        "nests": nests,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


__all__ = [
    "ARMS",
    "CLAIM_BOUNDARY",
    "DEATH_RATIO_STOP",
    "MINIMUM_RESOLVED",
    "RATIO_STOP",
    "SCHEMA",
    "STATUSES",
    "CloneSafetyError",
    "assess_clone_safety",
]
