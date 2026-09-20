"""Pre-unblind imaging power lock under the pediatric generation design.

An underpowered table cannot be treated as generation-versus-selection
evidence. Locked margins cannot be revised after peeking. This is not
real-study power and not efficacy evidence.

The detection certificate simulates the production lineage analyzer
end-to-end: each simulated study is materialized as a competing-risk
founder table and scored by ``analyze_lineage_study``, so the reported
rate prices the real decision rule — co-primary generation/founder
intervals, pediatric completion equivalence, daughter-resolution
adequacy, and every QC flag. Simulation assumptions are disclosed in the
receipt; homogeneous (exchangeable-event) plans report an upper bound
on achievable power, since real between-event heterogeneity, dropout,
and daughter censoring can only lower it.
"""

from __future__ import annotations

import functools
import math
import random
from collections.abc import Mapping
from typing import Any

from mva_hackathon.clone_safety import LINEAGE_COUNTS_SCHEMA
from mva_hackathon.culture_window import simulate_false_bulk_rescue
from mva_hackathon.lineage import (
    analyze_lineage_study,
    default_completion_band,
    lineage_study_from_counts,
)


SCHEMA = "mva-track2-assay-power/v2"
PLAN_SCHEMA = "mva.community-assay-power/v1"
MINIMUM_EVENTS = 3
MINIMUM_CLONES = 2
MINIMUM_OPPORTUNITIES = 24
N_SIMS = 400
SEED = 20260829
# The certificate materializes a full founder/daughter table per
# simulated study; this ceiling bounds that cost. Designs needing more
# than ~16k enrolled founders per simulated study are outside what the
# certificate can honestly price and fail closed.
SIM_MAX_FOUNDERS = 16_384
WILSON_Z = 1.959963984540054
ENDPOINT_CLASSES = ("generation", "bulk_aneuploid_fraction", "organ_size")
SUCCESS_RULES = ("generation_drop", "bulk_aneuploid_drop")
CLAIM_BOUNDARY = (
    "Assay-power software contract only; a locked plan is not a completed "
    "imaging study; this is not efficacy evidence."
)
SIMULATION_ASSUMPTIONS = (
    "each simulated study is materialized as competing-risk founders and "
    "scored by the production lineage analyzer (clean_generation_signal)",
    "locked_*_error_rate is the error-bearing fraction of completed "
    "divisions (the generation estimand); the founder-completion "
    "estimand couples it with the locked completion rate",
    "without locked_between_event_concentration, events are exchangeable "
    "at the locked rates — an upper bound, since real between-event "
    "heterogeneity can only lower the certified rate",
    "non-completion is partitioned across pre-division death, dropout, "
    "and no-division at the locked rates (default zero death/dropout)",
    "daughters are simulated fully resolved with neutral reproduction, "
    "so daughter censoring and selection drift are not priced",
)


class AssayPowerError(ValueError):
    """Raised when an assay-power plan is unusable."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssayPowerError(f"{label} must be an object")
    return value


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise AssayPowerError(f"{field} must be a boolean")
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AssayPowerError(f"{field} must be a positive integer")
    return value


def _rate(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssayPowerError(f"{field} must be a probability")
    try:
        result = float(value)
    except OverflowError:
        raise AssayPowerError(f"{field} must be a probability") from None
    if result != result or result < 0.0 or result > 1.0:
        raise AssayPowerError(f"{field} must be a probability")
    return result


def _optional_rate(payload: Mapping[str, Any], field: str) -> float:
    value = payload.get(field)
    if value is None:
        return 0.0
    return _rate(value, field)


def _concentration(payload: Mapping[str, Any]) -> float | None:
    value = payload.get("locked_between_event_concentration")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssayPowerError(
            "locked_between_event_concentration must be a number >= 1"
        )
    try:
        numeric = float(value)
    except OverflowError:
        raise AssayPowerError(
            "locked_between_event_concentration must be a number >= 1"
        ) from None
    if not math.isfinite(numeric) or numeric < 1.0:
        raise AssayPowerError(
            "locked_between_event_concentration must be a number >= 1"
        )
    return numeric


def _binomial(rng: random.Random, n: int, probability: float) -> int:
    if n <= 0 or probability <= 0.0:
        return 0
    if probability >= 1.0:
        return n
    # Exact draw — a clipped normal approximation distorts tail events.
    return rng.binomialvariate(n, probability)


def _multinomial_partition(
    rng: random.Random,
    enrolled: int,
    death_p: float,
    dropout_p: float,
    completion_p: float,
) -> tuple[int, int, int, int]:
    """Draw (death, dropout, completed, no_division) with multinomial marginals.

    Sequential conditional binomials reproduce the marginal partition:
    X1 ~ Bin(n, p1); X2 | X1 ~ Bin(n - X1, p2/(1 - p1)); and so on.
    """

    death = _binomial(rng, enrolled, death_p)
    remaining = enrolled - death
    dropout_denominator = 1.0 - death_p
    dropout = (
        _binomial(rng, remaining, dropout_p / dropout_denominator)
        if dropout_denominator > 0.0
        else 0
    )
    remaining -= dropout
    completion_denominator = 1.0 - death_p - dropout_p
    # A dispersed completion draw can exceed the feasibility ceiling
    # (1 - death - dropout); the binomial saturates at p >= 1, so the
    # realized marginal completion is at most the nominal plan value —
    # the certificate is conservative, never over-powered.
    completed = (
        _binomial(rng, remaining, completion_p / completion_denominator)
        if completion_denominator > 0.0
        else 0
    )
    return death, dropout, completed, remaining - completed


def _dispersed_rate(
    rng: random.Random, probability: float, concentration: float | None
) -> float:
    """Per-event rate under optional Beta(concentration*p, concentration*(1-p)) dispersion."""

    if concentration is None or probability <= 0.0 or probability >= 1.0:
        return probability
    return rng.betavariate(
        concentration * probability, concentration * (1.0 - probability)
    )


@functools.lru_cache(maxsize=64)
def _analyzer_clean_rate(
    *,
    n_events: int,
    n_clones: int,
    n_opportunities: int,
    vehicle_error: float,
    treatment_error: float,
    vehicle_completion: float,
    treatment_completion: float,
    death_rate: float,
    dropout_rate: float,
    concentration: float | None,
    n_sims: int,
    seed: int,
) -> int:
    """Simulate full studies through the production analyzer.

    Each replicate materializes competing-risk founders via
    ``lineage_study_from_counts`` and scores ``clean_generation_signal``
    with ``analyze_lineage_study`` — the certificate prices the real
    event-level decision rule, not a pooled surrogate. Memoized: the
    seeded simulation is deterministic, so identical plans share one
    certificate. Returns the hit count.
    """

    rng = random.Random(seed)
    hits = 0
    enrolled_per_arm_event = n_clones * n_opportunities
    for sim_index in range(n_sims):
        per_event: dict[str, dict[str, dict[str, int]]] = {}
        for event_index in range(1, n_events + 1):
            arms: dict[str, dict[str, int]] = {}
            for arm, error_p, completion_p in (
                ("vehicle", vehicle_error, vehicle_completion),
                ("treatment", treatment_error, treatment_completion),
            ):
                event_error_p = _dispersed_rate(rng, error_p, concentration)
                event_completion_p = _dispersed_rate(
                    rng, completion_p, concentration
                )
                death, dropout, completed, no_division = _multinomial_partition(
                    rng,
                    enrolled_per_arm_event,
                    death_rate,
                    dropout_rate,
                    event_completion_p,
                )
                error_completed = _binomial(rng, completed, event_error_p)
                arms[arm] = {
                    "completed_error": error_completed,
                    "completed_no_error": completed - error_completed,
                    "no_division": no_division,
                    "death_before_completion": death,
                    "dropout_censored": dropout,
                }
            per_event[f"sim-event-{event_index}"] = arms
        study = lineage_study_from_counts(
            study_id=f"sim-power-{seed}-{sim_index}",
            per_event=per_event,
            clones_per_event=n_clones,
            validate=False,
        )
        analysis = analyze_lineage_study(study)
        if analysis["status"]["clean_generation_signal"]:
            hits += 1
    return hits


def _wilson_lower_bound(hits: int, n_sims: int) -> float:
    """One-sided-style 95% Wilson lower bound on the Monte Carlo rate."""

    if n_sims <= 0:
        return 0.0
    p = hits / n_sims
    z2 = WILSON_Z * WILSON_Z
    denominator = 1.0 + z2 / n_sims
    center = p + z2 / (2.0 * n_sims)
    margin = WILSON_Z * math.sqrt(
        p * (1.0 - p) / n_sims + z2 / (4.0 * n_sims * n_sims)
    )
    return max(0.0, (center - margin) / denominator)


MINIMUM_VEHICLE_COMPLETION = 0.9
MAX_REMAINING_PD = 128
MAX_DESIGN_DRAWS = 10_000_000

_LINEAGE_COUNT_FIELDS = (
    "detected_divisions",
    "event_positive_divisions",
    "event_negative_divisions",
    "event_positive_daughters_followed",
    "event_positive_daughters_reproduced",
    "event_positive_daughters_died",
    "event_negative_daughters_followed",
    "event_negative_daughters_reproduced",
    "event_negative_daughters_died",
    "pre_division_death",
    "no_division",
    "dropout_censored",
)


def _nonneg_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _count_row_complete(row: Mapping[str, Any]) -> bool:
    """A realized row must carry the full first-attempt count payload."""

    if not all(_nonneg_int(row.get(field)) for field in _LINEAGE_COUNT_FIELDS):
        return False
    for label in ("positive", "negative"):
        followed = row[f"event_{label}_daughters_followed"]
        if (
            row[f"event_{label}_daughters_reproduced"]
            + row[f"event_{label}_daughters_died"]
            > followed
        ):
            return False
        divisions = row[f"event_{label}_divisions"]
        multipolar = 0
        if label == "positive":
            multipolar_raw = row.get("event_positive_multipolar_divisions")
            if multipolar_raw is not None:
                if not _nonneg_int(multipolar_raw) or multipolar_raw > divisions:
                    return False
                multipolar = multipolar_raw
        slots_raw = row.get(f"event_{label}_daughter_slots")
        if slots_raw is None:
            if multipolar:
                return False
            slots = 2 * divisions
        else:
            if not _nonneg_int(slots_raw):
                return False
            slots = slots_raw
            if slots < 2 * divisions + multipolar:
                return False
            if slots > 2 * divisions + 2 * multipolar:
                return False
            if label == "negative" and slots > 2 * divisions:
                return False
        if followed > slots:
            return False
    if row["detected_divisions"] != (
        row["event_positive_divisions"] + row["event_negative_divisions"]
    ):
        return False
    outcomes = (
        row["detected_divisions"]
        + row["pre_division_death"]
        + row["no_division"]
        + row["dropout_censored"]
    )
    return _nonneg_int(row.get("opportunities")) and outcomes == row["opportunities"]


def _in_pediatric_band(vehicle: float, treatment: float) -> bool:
    band = default_completion_band()
    if vehicle < MINIMUM_VEHICLE_COMPLETION:
        return False
    relative = treatment / vehicle
    drop = vehicle - treatment
    return (
        band.relative_lower <= relative <= band.relative_upper
        and drop <= band.absolute_drop_max
    )


def assess_assay_power(
    plan: Mapping[str, Any],
    lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pass only a locked design that can detect the predeclared generation drop."""

    payload = _mapping(plan, "assay-power plan")
    if payload.get("schema") != PLAN_SCHEMA:
        raise AssayPowerError("assay power accepts the community power plan only")
    locked = _bool(payload.get("locked"), "locked")
    n_events = _positive_int(payload.get("n_edit_events"), "n_edit_events")
    n_clones = _positive_int(payload.get("n_clones_per_event"), "n_clones_per_event")
    n_opportunities = _positive_int(payload.get("n_opportunities"), "n_opportunities")
    vehicle_rate = _rate(payload.get("locked_vehicle_error_rate"), "locked_vehicle_error_rate")
    treatment_rate = _rate(
        payload.get("locked_treatment_error_rate"), "locked_treatment_error_rate"
    )
    vehicle_completion = _rate(
        payload.get("locked_vehicle_completion_rate"), "locked_vehicle_completion_rate"
    )
    treatment_completion = _rate(
        payload.get("locked_treatment_completion_rate"),
        "locked_treatment_completion_rate",
    )
    minimum_detection = _rate(payload.get("minimum_detection"), "minimum_detection")
    if minimum_detection < 0.8:
        raise AssayPowerError(
            "minimum_detection must be at least 0.8 — a lower power floor "
            "cannot claim a powered design"
        )
    death_rate = _optional_rate(payload, "locked_pre_division_death_rate")
    dropout_rate = _optional_rate(payload, "locked_dropout_rate")
    concentration = _concentration(payload)
    for label, completion in (
        ("locked_vehicle_completion_rate", vehicle_completion),
        ("locked_treatment_completion_rate", treatment_completion),
    ):
        if completion + death_rate + dropout_rate > 1.0:
            raise AssayPowerError(
                f"{label} plus the locked death and dropout rates exceeds "
                "the first-attempt partition"
            )
    endpoint = payload.get("endpoint_class")
    if endpoint not in ENDPOINT_CLASSES:
        raise AssayPowerError("endpoint_class is not in the allowed vocabulary")
    success_rule = payload.get("success_rule")
    if success_rule not in SUCCESS_RULES:
        raise AssayPowerError("success_rule is not in the allowed vocabulary")
    remaining = payload.get("remaining_population_doublings")
    if remaining is not None:
        remaining = _positive_int(remaining, "remaining_population_doublings")
        if remaining > MAX_REMAINING_PD:
            raise AssayPowerError(
                "remaining_population_doublings exceeds a manufacturable ceiling"
            )
    n = n_events * n_clones * n_opportunities
    if n > MAX_DESIGN_DRAWS:
        raise AssayPowerError(
            "design exceeds the bounded simulation draw ceiling"
        )
    simulated_founders = 2 * n
    realized_events = None
    realized_depth_ok = True
    if lineage is None:
        realized_events = 0
        realized_depth_ok = False
    else:
        if not isinstance(lineage, Mapping) or lineage.get("schema") != LINEAGE_COUNTS_SCHEMA:
            realized_events = 0
            realized_depth_ok = False
        else:
            runs = lineage.get("runs")
            if not isinstance(runs, list) or len(runs) > 500_000:
                realized_events = 0
                realized_depth_ok = False
            else:
                event_ids: set[object] = set()
                clones_by_event_arm: dict[tuple[object, object], set[object]] = {}
                opportunities_by_clone: dict[tuple[object, object, object], int] = {}
                seen_rows: set[tuple[object, object, object]] = set()
                for row in runs:
                    if not isinstance(row, Mapping):
                        realized_depth_ok = False
                        continue
                    event = row.get("edit_event_id")
                    arm = row.get("arm")
                    clone = row.get("clone_id")
                    if (
                        not isinstance(event, (str, int))
                        or isinstance(event, bool)
                        or not isinstance(arm, (str, int))
                        or isinstance(arm, bool)
                        or not isinstance(clone, (str, int))
                        or isinstance(clone, bool)
                    ):
                        # Unhashable or non-scalar identifiers cannot join
                        # the dedup set — degrade to a structured verdict
                        # instead of raising TypeError out of the gate.
                        realized_depth_ok = False
                        continue
                    if not _count_row_complete(row):
                        realized_depth_ok = False
                        continue
                    key = (event, arm, clone)
                    if key in seen_rows:
                        realized_depth_ok = False
                        continue
                    seen_rows.add(key)
                    event_ids.add(event)
                    clones_by_event_arm.setdefault((event, arm), set()).add(clone)
                    opportunities = row.get("opportunities")
                    if (
                        isinstance(opportunities, int)
                        and not isinstance(opportunities, bool)
                        and opportunities > 0
                    ):
                        opportunities_by_clone[key] = opportunities
                realized_events = len(event_ids)
                for event in event_ids:
                    for arm in ("vehicle", "treatment"):
                        clones = clones_by_event_arm.get((event, arm)) or set()
                        if len(clones) < n_clones:
                            realized_depth_ok = False
                            continue
                        for clone in clones:
                            if (
                                opportunities_by_clone.get((event, arm, clone), 0)
                                < n_opportunities
                            ):
                                realized_depth_ok = False

    window = None
    if locked and remaining is not None:
        window = simulate_false_bulk_rescue(remaining_pd=remaining)

    # Cheap structural checks run before the simulation: the analyzer-
    # faithful certificate is the most expensive check in the gate, so
    # plans that fail on structure never pay for it.
    detection = None
    detection_mc_lower = None
    if not locked:
        status = "not_assessable"
        reason = "plan_unlocked"
        eligible = False
    elif n_events < MINIMUM_EVENTS or n_clones < MINIMUM_CLONES or n_opportunities < MINIMUM_OPPORTUNITIES:
        status = "not_assessable"
        reason = "underpowered_design"
        eligible = False
    elif treatment_rate >= vehicle_rate:
        status = "not_assessable"
        reason = "no_locked_generation_margin"
        eligible = False
    elif simulated_founders > SIM_MAX_FOUNDERS:
        status = "not_assessable"
        reason = "design_exceeds_simulation_fidelity"
        eligible = False
    elif lineage is None:
        status = "not_assessable"
        reason = "realized_lineage_required"
        eligible = False
    elif realized_events is None or (
        realized_events < n_events or not realized_depth_ok
    ):
        status = "not_assessable"
        reason = "realized_smaller_than_plan"
        eligible = False
    elif not _in_pediatric_band(vehicle_completion, treatment_completion):
        status = "not_assessable"
        reason = "pediatric_band_incompatible"
        eligible = False
    elif remaining is None:
        status = "not_assessable"
        reason = "remaining_pd_required"
        eligible = False
    elif remaining < n_events:
        status = "not_assessable"
        reason = "powered_but_unmanufacturable"
        eligible = False
    elif endpoint != "generation":
        status = "not_assessable"
        reason = "bulk_fraction_not_generation"
        eligible = False
    elif success_rule == "bulk_aneuploid_drop" and window is not None and window.get("false_rescue_likely"):
        status = "not_assessable"
        reason = "false_bulk_rescue_likely"
        eligible = False
    elif success_rule != "generation_drop":
        status = "not_assessable"
        reason = "endpoint_rule_mismatch"
        eligible = False
    else:
        hits = _analyzer_clean_rate(
            n_events=n_events,
            n_clones=n_clones,
            n_opportunities=n_opportunities,
            vehicle_error=vehicle_rate,
            treatment_error=treatment_rate,
            vehicle_completion=vehicle_completion,
            treatment_completion=treatment_completion,
            death_rate=death_rate,
            dropout_rate=dropout_rate,
            concentration=concentration,
            n_sims=N_SIMS,
            seed=SEED,
        )
        detection = hits / N_SIMS
        detection_mc_lower = _wilson_lower_bound(hits, N_SIMS)
        if detection < minimum_detection:
            status = "not_assessable"
            reason = "underpowered"
            eligible = False
        elif detection_mc_lower < minimum_detection:
            status = "not_assessable"
            reason = "underpowered_mc_uncertainty"
            eligible = False
        else:
            status = "pass"
            reason = "powered_locked_plan"
            eligible = True

    return {
        "schema": SCHEMA,
        "gate": "assay_power",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": "pass" if eligible else "hold",
        "reason": reason,
        "locked": locked,
        "n_per_arm": n,
        "detection_rate": detection,
        "detection_rate_basis": "event_level_lineage_analyzer",
        "detection_rate_mc_lower_bound": detection_mc_lower,
        "n_sims": N_SIMS,
        "sim_seed": SEED,
        "simulated_founders_per_study": simulated_founders,
        "simulation_assumptions": list(SIMULATION_ASSUMPTIONS),
        "minimum_detection": minimum_detection,
        "realized_edit_events": realized_events,
        "locked_vehicle_completion_rate": vehicle_completion,
        "locked_treatment_completion_rate": treatment_completion,
        "remaining_population_doublings": remaining,
        "endpoint_class": endpoint,
        "success_rule": success_rule,
        "p_false_bulk_rescue": None if window is None else window.get("p_false_bulk_rescue"),
        "false_rescue_likely": None if window is None else window.get("false_rescue_likely"),
    }


__all__ = [
    "CLAIM_BOUNDARY",
    "SCHEMA",
    "AssayPowerError",
    "assess_assay_power",
]
