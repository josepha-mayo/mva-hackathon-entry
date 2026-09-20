"""Truth-blind timestamped lineage contract for first-attempt competing risks.

This module is a production data contract and fail-closed analyzer for
founder-to-daughter records. It is not a mixed-effects biology engine, not a
replacement for the v3 aggregate-count firewall, and not evidence of efficacy.

The analyst payload contains observed identifiers, timestamps, locked labels,
and competing first-attempt outcomes only. Generator parameters, scenario
names, and latent truth are forbidden in the analyzed object.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from mva_hackathon.generation_selection import StableRng


SCHEMA = "mva-track2-lineage-study/v1"
ARM_NAMES = ("vehicle", "treatment")
LOCK_STATES = ("locked", "unlocked")
FIRST_ATTEMPT_OUTCOMES = (
    "completed_error",
    "completed_no_error",
    "no_division",
    "death_before_completion",
    "dropout_censored",
)
COMPLETED_OUTCOMES = frozenset({"completed_error", "completed_no_error"})
DAUGHTER_OUTCOMES = ("reproduced", "died", "censored", "not_followed")
DIVISION_CLASSES = ("bipolar", "multipolar")
DAUGHTERS_PER_BIPOLAR_DIVISION = 2
MAX_DAUGHTERS_PER_MULTIPOLAR_DIVISION = 4
FORBIDDEN_ANALYST_KEYS = frozenset(
    {
        "generator_truth",
        "scenario_name",
        "intended_flags",
        "latent_error",
        "unblinded_label",
        "realized_truth",
    }
)
ESTIMANDS = (
    "generation_rate",
    "founder_error_bearing_completion",
    "relative_error_daughter_reproduction",
    "division_completion",
    "pre_division_death",
    "dropout",
)
BIOLOGICAL_FLAGS = (
    "generation_reduction",
    "error_daughter_pruning",
    "error_daughter_preservation",
    "cytostasis",
    "general_toxicity",
    "per_event_harm_spike",
)
QC_FLAGS = (
    "label_leakage",
    "unlocked",
    "treatment_dependent_dropout",
    "unequal_followup",
    "clone_concentration",
    "field_concentration",
    "single_clone_effect",
    "single_edit_event_effect",
    "clone_selection_conflict",
)
CLAIM_BOUNDARY = (
    "Timestamped first-attempt competing-risk software contract only; "
    "pre-division death is labeled separately from other non-completion; "
    "this is not biological validation, mixed-effects clinical inference, "
    "or efficacy evidence."
)
# Student-t 0.975 critical value at df = 2: the minimum-study design is
# three paired edit events, and between-event variance is *estimated*
# from those events, so it carries the t correction. More events keep
# the same multiplier, which stays conservative.
DEFAULT_CONFIDENCE_MULTIPLIER = 4.30265272991
# Normal 0.975 critical value for the within-event component: Jeffreys
# delta-method variance is *known* from the observed denominators, not
# estimated from the event count, so no degrees-of-freedom correction
# applies to it.
WITHIN_Z_CRITICAL = 1.959963984540054
GENERATION_REDUCTION_RATIO = 0.75
# The row ceiling (500k founders / 1M daughters) is the real bound; a study
# file larger than this could never fit inside it.
MAX_LINEAGE_STUDY_BYTES = 256 * 1024 * 1024
SELECTION_REDUCTION_RATIO = 0.75
SELECTION_INCREASE_RATIO = 1.25
DIVISION_REDUCTION_RATIO = 0.75
TOXICITY_INCREASE_RATIO = 2.0
DROPOUT_INCREASE_RATIO = 1.25
FOLLOWUP_HOURS_RATIO_FLOOR = 0.85
CLONE_SHARE_LIMIT = 0.60
FIELD_SHARE_LIMIT = 0.70
UNIT_REDUCTION_RATIO = 0.75
MINIMUM_EDIT_EVENTS = 3
MINIMUM_CLONES_PER_EVENT = 2
MINIMUM_COMPLETED_PER_EVENT_ARM = 8
MINIMUM_RESOLVED_ERROR_DAUGHTERS = 2
MINIMUM_RESOLVED_NONERROR_DAUGHTERS = 8
MINIMUM_RESOLVED_CLONE_DAUGHTERS = 2
ALLOCATION_REALIZATION_FIELDS = (
    "allocation_block_id",
    "functional_assay_plate_id",
    "plate_row",
    "plate_column",
    "dosing_order",
    "acquisition_order",
)
CORE_ESTIMANDS = (
    "generation_rate",
    "founder_error_bearing_completion",
    "division_completion",
)


class LineageError(ValueError):
    """Raised when a lineage contract or observed study is malformed."""


def _strict_object(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise LineageError(f"{label} has missing or surplus fields")
    forbidden = FORBIDDEN_ANALYST_KEYS.intersection(value)
    if forbidden:
        raise LineageError("analyst payload contains forbidden truth or scenario keys")
    return value


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise LineageError(f"{field} must be a non-empty identifier")
    if not value.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise LineageError(f"{field} contains unsupported characters")
    if not value[0].isalpha():
        raise LineageError(f"{field} must start with a letter")
    return value


def _allocation_identifier(value: object) -> str:
    result = _identifier(value, "allocation_id")
    prefix = "allocation-"
    digest = result.removeprefix(prefix)
    if (
        not result.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise LineageError(
            "allocation_id must be allocation- followed by a lowercase SHA-256 digest"
        )
    return result


def _allocation_context_identifier(value: object, field: str) -> str:
    result = _identifier(value, field)
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", result) is None:
        raise LineageError(f"{field} must be a lowercase opaque identifier")
    return result


def _enum(value: object, allowed: tuple[str, ...] | frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise LineageError(f"{field} is not a supported value")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise LineageError(f"{field} must be a boolean")
    return value


def _float_or_raise(value: object, field: str) -> float:
    # float() of a huge int raises OverflowError — normalize to the module
    # error so a hostile count cannot escape as an unhandled exception.
    try:
        return float(value)
    except (OverflowError, ValueError) as exc:
        raise LineageError(f"{field} must be a finite number") from exc


def _probability(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LineageError(f"{field} must be a finite probability")
    result = _float_or_raise(value, field)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise LineageError(f"{field} must be between zero and one")
    return result


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LineageError(f"{field} must be positive and finite")
    result = _float_or_raise(value, field)
    if not math.isfinite(result) or result <= 0.0:
        raise LineageError(f"{field} must be positive and finite")
    return result


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LineageError(f"{field} must be a positive integer")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LineageError(f"{field} must be a non-negative integer")
    return value


@functools.lru_cache(maxsize=8192)
def _parse_utc_cached(value: str) -> datetime:
    """Memoized ISO-8601 parse — repeated identical stamps are common."""

    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise LineageError("timestamp must be UTC")
    return parsed


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LineageError(f"{field} must be a UTC timestamp ending in Z")
    try:
        return _parse_utc_cached(value)
    except ValueError as exc:
        raise LineageError(f"{field} is not a valid timestamp") from exc


def _clone_row(proto: object, **overrides: object) -> object:
    """Clone a frozen dataclass row without re-running validation.

    Used by synthetic builders where the row values are program-generated:
    the prototype instance carried the validation cost, and overrides are
    restricted to freshly-generated identifier fields.
    """

    instance = object.__new__(type(proto))
    instance.__dict__.update(vars(proto))
    for key, value in overrides.items():
        object.__setattr__(instance, key, value)
    return instance


def _optional_utc(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    return _parse_utc(value, field)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass(frozen=True)
class CompletionBand:
    """Pediatric first-attempt completion equivalence band.

    This band is intentionally stricter than the v3 aggregate software band.
    A large relative interval can hide an absolute drop that would itself be
    harmful in a growth-disorder assay.
    """

    relative_lower: float
    relative_upper: float
    absolute_drop_max: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "relative_lower", _probability(self.relative_lower, "relative_lower")
        )
        object.__setattr__(
            self,
            "relative_upper",
            _positive_number(self.relative_upper, "relative_upper"),
        )
        object.__setattr__(
            self,
            "absolute_drop_max",
            _probability(self.absolute_drop_max, "absolute_drop_max"),
        )
        if not 0.90 <= self.relative_lower < 1.0:
            raise LineageError("relative_lower must lie in [0.90, 1)")
        if not 1.0 < self.relative_upper <= 1.15:
            raise LineageError("relative_upper must lie in (1, 1.15]")
        if not 0.0 < self.absolute_drop_max <= 0.10:
            raise LineageError("absolute_drop_max must lie in (0, 0.10]")
        # The declared band may only NARROW the protocol default; a caller
        # must not be able to relax the pediatric equivalence test.
        if (
            self.relative_lower < 0.95
            or self.relative_upper > 1.10
            or self.absolute_drop_max > 0.05
        ):
            raise LineageError(
                "completion band cannot be laxer than the protocol default "
                "(relative_lower >= 0.95, relative_upper <= 1.10, "
                "absolute_drop_max <= 0.05)"
            )


@dataclasses.dataclass(frozen=True)
class Founder:
    founder_id: str
    arm: str
    edit_event_id: str
    clone_id: str
    run_id: str
    field_id: str
    batch_id: str
    functional_execution_id: str
    exposure_support_record_id: str
    exposure_profile_id: str
    exposure_probe_id: str
    enrolled_at: str
    exposure_started_at: str
    first_attempt_started_at: str | None
    first_attempt_ended_at: str | None
    first_attempt_outcome: str
    censor_reason: str | None
    allocation_block_id: str | None = None
    functional_assay_plate_id: str | None = None
    plate_row: int | None = None
    plate_column: int | None = None
    dosing_order: int | None = None
    acquisition_order: int | None = None
    division_class: str = "bipolar"

    def __post_init__(self) -> None:
        object.__setattr__(self, "founder_id", _identifier(self.founder_id, "founder_id"))
        object.__setattr__(self, "arm", _enum(self.arm, ARM_NAMES, "arm"))
        for name in (
            "edit_event_id",
            "clone_id",
            "run_id",
            "field_id",
            "batch_id",
            "functional_execution_id",
            "exposure_support_record_id",
            "exposure_profile_id",
            "exposure_probe_id",
        ):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        enrolled = _parse_utc(self.enrolled_at, "enrolled_at")
        exposure = _parse_utc(self.exposure_started_at, "exposure_started_at")
        if exposure < enrolled:
            raise LineageError("exposure cannot start before enrollment")
        started = _optional_utc(self.first_attempt_started_at, "first_attempt_started_at")
        ended = _optional_utc(self.first_attempt_ended_at, "first_attempt_ended_at")
        object.__setattr__(
            self,
            "first_attempt_outcome",
            _enum(self.first_attempt_outcome, FIRST_ATTEMPT_OUTCOMES, "first_attempt_outcome"),
        )
        if self.censor_reason is not None:
            object.__setattr__(
                self, "censor_reason", _identifier(self.censor_reason, "censor_reason")
            )
        object.__setattr__(
            self,
            "division_class",
            _enum(self.division_class, DIVISION_CLASSES, "division_class"),
        )
        outcome = self.first_attempt_outcome
        if self.division_class == "multipolar" and outcome != "completed_error":
            raise LineageError(
                "multipolar divisions are segregation errors and must be "
                "scored completed_error"
            )
        if outcome == "dropout_censored":
            if self.censor_reason is None:
                raise LineageError("dropout requires a censor reason")
        elif self.censor_reason is not None:
            raise LineageError("censor reason is only allowed for dropout")
        allocation_values = tuple(
            getattr(self, field) for field in ALLOCATION_REALIZATION_FIELDS
        )
        if any(value is not None for value in allocation_values):
            if any(value is None for value in allocation_values):
                raise LineageError(
                    "realized allocation fields must be supplied together"
                )
            for name in ("allocation_block_id", "functional_assay_plate_id"):
                object.__setattr__(
                    self,
                    name,
                    _allocation_context_identifier(getattr(self, name), name),
                )
            for name in (
                "plate_row",
                "plate_column",
                "dosing_order",
                "acquisition_order",
            ):
                object.__setattr__(
                    self, name, _positive_integer(getattr(self, name), name)
                )
        if outcome in COMPLETED_OUTCOMES or outcome == "no_division":
            if started is None or ended is None:
                raise LineageError("completed and no-division outcomes require both timestamps")
            if started < exposure or ended < started:
                raise LineageError("attempt timestamps are not ordered")
        if outcome == "death_before_completion":
            if ended is None:
                raise LineageError("pre-division death requires an end timestamp")
            if started is not None and (started < exposure or ended < started):
                raise LineageError("death timestamps are not ordered")
            if started is None and ended < exposure:
                raise LineageError("death cannot precede exposure")


@dataclasses.dataclass(frozen=True)
class Daughter:
    daughter_id: str
    founder_id: str
    observed_at: str
    outcome: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "daughter_id", _identifier(self.daughter_id, "daughter_id")
        )
        object.__setattr__(self, "founder_id", _identifier(self.founder_id, "founder_id"))
        _parse_utc(self.observed_at, "observed_at")
        object.__setattr__(self, "outcome", _enum(self.outcome, DAUGHTER_OUTCOMES, "outcome"))


@dataclasses.dataclass(frozen=True)
class LineageStudy:
    schema: str
    study_id: str
    blinded: bool
    lock_state: str
    unblinded_at: str | None
    adjudication_locked_at: str
    completion_band: CompletionBand
    founders: tuple[Founder, ...]
    daughters: tuple[Daughter, ...]
    allocation_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise LineageError("unsupported lineage schema")
        object.__setattr__(self, "study_id", _identifier(self.study_id, "study_id"))
        if self.allocation_id is not None:
            object.__setattr__(
                self,
                "allocation_id",
                _allocation_identifier(self.allocation_id),
            )
        object.__setattr__(self, "blinded", _boolean(self.blinded, "blinded"))
        object.__setattr__(
            self, "lock_state", _enum(self.lock_state, LOCK_STATES, "lock_state")
        )
        _parse_utc(self.adjudication_locked_at, "adjudication_locked_at")
        _optional_utc(self.unblinded_at, "unblinded_at")
        if not self.founders:
            raise LineageError("study must contain founders")
        founder_ids = [row.founder_id for row in self.founders]
        if len(set(founder_ids)) != len(founder_ids):
            raise LineageError("duplicate founder identifiers")
        founder_index = {row.founder_id: row for row in self.founders}
        clone_events: dict[str, str] = {}
        execution_contexts: dict[str, tuple[object, ...]] = {}
        for row in self.founders:
            has_realized_allocation = row.allocation_block_id is not None
            if (self.allocation_id is not None) != has_realized_allocation:
                raise LineageError(
                    "allocation_id and realized founder allocation must be supplied together"
                )
            previous = clone_events.get(row.clone_id)
            if previous is None:
                clone_events[row.clone_id] = row.edit_event_id
            elif previous != row.edit_event_id:
                raise LineageError("clone identifiers must nest inside one edit event")
            execution_context = (
                row.arm,
                row.edit_event_id,
                row.clone_id,
                row.run_id,
                row.batch_id,
                *(getattr(row, field) for field in ALLOCATION_REALIZATION_FIELDS),
            )
            prior_context = execution_contexts.get(row.functional_execution_id)
            if prior_context is None:
                execution_contexts[row.functional_execution_id] = execution_context
            elif prior_context != execution_context:
                raise LineageError(
                    "functional execution identifiers must have one realized context"
                )
        daughter_ids = [row.daughter_id for row in self.daughters]
        if len(set(daughter_ids)) != len(daughter_ids):
            raise LineageError("duplicate daughter identifiers")
        daughters_by_founder: dict[str, int] = {}
        for child in self.daughters:
            parent = founder_index.get(child.founder_id)
            if parent is None:
                raise LineageError("daughter is missing a parent founder")
            if parent.first_attempt_outcome not in COMPLETED_OUTCOMES:
                raise LineageError("daughters are only allowed after a completed division")
            observed = _parse_utc(child.observed_at, "observed_at")
            ended = _parse_utc(parent.first_attempt_ended_at, "first_attempt_ended_at")
            if observed < ended:
                raise LineageError("daughter observation precedes division completion")
            daughters_by_founder[child.founder_id] = (
                daughters_by_founder.get(child.founder_id, 0) + 1
            )
            max_daughters = (
                MAX_DAUGHTERS_PER_MULTIPOLAR_DIVISION
                if parent.division_class == "multipolar"
                else DAUGHTERS_PER_BIPOLAR_DIVISION
            )
            if daughters_by_founder[child.founder_id] > max_daughters:
                raise LineageError(
                    "a bipolar division cannot produce more than two daughters; "
                    "a multipolar division cannot produce more than four"
                )
        for row in self.founders:
            if (
                row.division_class == "multipolar"
                and daughters_by_founder.get(row.founder_id, 0) < 3
            ):
                raise LineageError(
                    "a multipolar division requires at least three recorded "
                    "daughters; fewer cannot be distinguished from a bipolar "
                    "scoring error"
                )


@dataclasses.dataclass(frozen=True)
class RatioEstimate:
    estimable: bool
    ratio: float | None
    lower: float | None
    upper: float | None
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _proportion_smoothed(k: int, n: int) -> float:
    """Jeffreys posterior-mean rate (k + 0.5) / (n + 1).

    The interval's point estimate must live on the same smoothed scale
    the within-variance was derived for: a raw zero numerator clamped to
    a tiny constant would center the log-ratio near -20 while the
    variance stays at its fixed (2n+1)/n bound — a certified reduction
    on one event's worth of luck. The smoothed rate stays finite and
    honest about the 0.5-pseudo-count floor.
    """

    return (k + 0.5) / (n + 1.0)


def _rate_point(k: int, n: int) -> float:
    """Raw rate k/n for the interval's point estimate.

    Smoothing is a boundary correction, not a general shrinkage: a raw
    zero numerator sends the log-ratio to -inf, so only that cell falls
    back to the Jeffreys rate (Woolf-Haldane convention). Applying the
    pseudocount to positive counts would bias large ratios toward 1 and
    collapse interval coverage on strong preservation/toxicity effects.
    """

    if k > 0:
        return k / n
    return _proportion_smoothed(k, n)


def _proportion_within(k: int, n: int) -> float:
    """Delta-method variance of log(p̃) under a Jeffreys-smoothed rate.

    p̃ = (k + 0.5) / (n + 1) keeps zero and full cells finite, and
    (1 - p̃) / (p̃ · n) is the corresponding within-event variance of
    log p̃ — the sparse-denominator noise a between-event-only interval
    ignores.
    """

    smoothed = (k + 0.5) / (n + 1.0)
    return (1.0 - smoothed) / (smoothed * n)


def _ratio_estimate(
    vehicle_values: list[float | None],
    treatment_values: list[float | None],
    confidence_multiplier: float,
    reason: str | None = None,
    vehicle_within: list[float | None] | None = None,
    treatment_within: list[float | None] | None = None,
    vehicle_numerators: list[int | None] | None = None,
    treatment_numerators: list[int | None] | None = None,
    vehicle_points: list[float | None] | None = None,
    treatment_points: list[float | None] | None = None,
) -> RatioEstimate:
    if reason is not None:
        return RatioEstimate(False, None, None, None, reason)
    if len(vehicle_values) != len(treatment_values) or len(vehicle_values) < MINIMUM_EDIT_EVENTS:
        return RatioEstimate(
            False, None, None, None, "fewer than three paired edit events"
        )
    if any(value is None for value in (*vehicle_values, *treatment_values)):
        return RatioEstimate(
            False, None, None, None, "one or more edit events are not estimable"
        )
    if (
        vehicle_numerators is not None
        and treatment_numerators is not None
        and not any(
            numerator
            for numerator in (*vehicle_numerators, *treatment_numerators)
        )
    ):
        # Every event in both arms observed a zero numerator: the data carry
        # no information about the ratio, and a zero-width interval on
        # all-zero cells is arithmetic, not evidence.
        return RatioEstimate(False, None, None, None, "no_observed_events")
    # The interval is centered on the raw event rates, with Jeffreys
    # smoothing reserved for zero-numerator cells whose raw log-ratio
    # is non-finite: a raw zero numerator floored to a tiny constant
    # would center the log-ratio near -20 while the variance stays at
    # its fixed (2n+1)/n bound — a certified reduction on one event's
    # worth of luck. Conditional smoothing keeps the center and the
    # width internally consistent without biasing strong effects.
    point_vehicle = (
        vehicle_points if vehicle_points is not None else vehicle_values
    )
    point_treatment = (
        treatment_points if treatment_points is not None else treatment_values
    )
    log_ratios = [
        math.log(max(float(treatment), 1e-9) / max(float(vehicle), 1e-9))
        for vehicle, treatment in zip(point_vehicle, point_treatment, strict=True)
        if vehicle is not None and treatment is not None
    ]
    if len(log_ratios) < MINIMUM_EDIT_EVENTS:
        return RatioEstimate(
            False, None, None, None, "log-ratio is undefined for a zero cell"
        )
    mean_log = sum(log_ratios) / len(log_ratios)
    variance = sum((value - mean_log) ** 2 for value in log_ratios) / (
        len(log_ratios) - 1
    )
    # Within-event sampling variance rides on top of the between-event
    # spread: a rate estimated from a sparse denominator cannot borrow
    # precision from its siblings. The two components carry different
    # critical values — the between-event scatter is estimated from k
    # events (Student-t, df = k - 1 baked into confidence_multiplier)
    # while the within-event variance is known from the observed
    # denominators (normal critical value). Applying the t multiplier
    # to both would double-penalize sparse-but-honest data; quadrature
    # keeps each component at its own critical value and stays
    # conservative because t > z on the estimated component.
    within_mean = 0.0
    if vehicle_within is not None and treatment_within is not None:
        within_mean = sum(
            vehicle + treatment
            for vehicle, treatment in zip(
                vehicle_within, treatment_within, strict=True
            )
        ) / len(log_ratios)
    half_width = math.sqrt(
        (confidence_multiplier**2) * (variance / len(log_ratios))
        + (WITHIN_Z_CRITICAL**2) * (within_mean / len(log_ratios))
    )
    return RatioEstimate(
        True,
        math.exp(mean_log),
        math.exp(mean_log - half_width),
        math.exp(mean_log + half_width),
        None,
    )


def _reduced(estimate: RatioEstimate, cutoff: float) -> bool:
    return bool(
        estimate.estimable
        and estimate.ratio is not None
        and estimate.upper is not None
        and estimate.ratio <= cutoff
        and estimate.upper < 1.0
    )


def _increased(estimate: RatioEstimate, cutoff: float) -> bool:
    return bool(
        estimate.estimable
        and estimate.ratio is not None
        and estimate.lower is not None
        and estimate.ratio >= cutoff
        and estimate.lower > 1.0
    )


def parse_lineage_study(value: object) -> LineageStudy:
    """Parse a strict analyst payload and reject truth or scenario keys."""

    if not isinstance(value, dict):
        raise LineageError("lineage study must be an object")
    leaked = FORBIDDEN_ANALYST_KEYS.intersection(value)
    if leaked:
        raise LineageError("analyst payload contains forbidden truth or scenario keys")
    root_fields = {
        "schema",
        "study_id",
        "blinded",
        "lock_state",
        "unblinded_at",
        "adjudication_locked_at",
        "completion_band",
        "founders",
        "daughters",
    }
    if set(value) not in (root_fields, root_fields | {"allocation_id"}):
        raise LineageError("lineage study has missing or surplus fields")
    root = value
    allocation_id = (
        _allocation_identifier(root["allocation_id"])
        if "allocation_id" in root
        else None
    )
    band_raw = _strict_object(
        root["completion_band"],
        {"relative_lower", "relative_upper", "absolute_drop_max"},
        "completion_band",
    )
    if not isinstance(root["founders"], list) or not isinstance(root["daughters"], list):
        raise LineageError("founders and daughters must be arrays")
    # Unbounded row arrays are a resource-exhaustion surface; a real study
    # is orders of magnitude below this ceiling.
    if len(root["founders"]) > 500_000 or len(root["daughters"]) > 1_000_000:
        raise LineageError("founders/daughters exceed the parse ceiling")
    founder_fields = set(Founder.__dataclass_fields__)
    founder_optional_fields = {"division_class"}
    founder_base_fields = (
        founder_fields - set(ALLOCATION_REALIZATION_FIELDS) - founder_optional_fields
    )
    founder_alloc_fields = founder_fields - founder_optional_fields
    parsed_founders = []
    for index, row in enumerate(root["founders"], start=1):
        if not isinstance(row, dict) or set(row) not in (
            founder_base_fields,
            founder_base_fields | founder_optional_fields,
            founder_alloc_fields,
            founder_fields,
        ):
            raise LineageError(f"founder {index} has missing or surplus fields")
        leaked_founder = FORBIDDEN_ANALYST_KEYS.intersection(row)
        if leaked_founder:
            raise LineageError("analyst payload contains forbidden truth or scenario keys")
        parsed_founders.append(Founder(**row))
    founders = tuple(parsed_founders)
    daughters = tuple(
        Daughter(
            **_strict_object(
                row,
                set(Daughter.__dataclass_fields__),
                f"daughter {index}",
            )
        )
        for index, row in enumerate(root["daughters"], start=1)
    )
    return LineageStudy(
        schema=root["schema"],
        study_id=root["study_id"],
        blinded=root["blinded"],
        lock_state=root["lock_state"],
        unblinded_at=root["unblinded_at"],
        adjudication_locked_at=root["adjudication_locked_at"],
        completion_band=CompletionBand(**band_raw),
        founders=founders,
        daughters=daughters,
        allocation_id=allocation_id,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LineageError(f"lineage study contains duplicate key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise LineageError(f"lineage study contains non-finite number: {value}")


def _finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except (OverflowError, ValueError) as exc:
        raise LineageError(
            f"lineage study contains non-finite number: {value}"
        ) from exc
    if not math.isfinite(parsed):
        raise LineageError(f"lineage study contains non-finite number: {value}")
    return parsed


def load_lineage_study(path: str | Path) -> LineageStudy:
    try:
        source = Path(path)
        if source.stat().st_size > MAX_LINEAGE_STUDY_BYTES:
            raise LineageError("lineage study exceeds the byte ceiling")
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
            parse_float=_finite_float,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LineageError(f"cannot read lineage study: {exc}") from exc
    except (OverflowError, MemoryError) as exc:
        raise LineageError("lineage study contains an out-of-range value") from exc
    return parse_lineage_study(payload)


def _empty_arm_counts() -> dict[str, int]:
    return {name: 0 for name in FIRST_ATTEMPT_OUTCOMES}


def _event_ids(study: LineageStudy) -> tuple[str, ...]:
    return tuple(sorted({row.edit_event_id for row in study.founders}))


def analyze_lineage_study(study: LineageStudy) -> dict[str, Any]:
    """Analyze locked, blinded lineage records without generator truth."""

    if not isinstance(study, LineageStudy):
        raise LineageError("analyzer accepts a parsed lineage study only")
    events = _event_ids(study)
    qc = {name: False for name in QC_FLAGS}
    if not study.blinded or study.unblinded_at is not None:
        qc["label_leakage"] = True
    if study.lock_state != "locked":
        qc["unlocked"] = True

    founders_by_event: dict[str, dict[str, list[Founder]]] = {
        event: {arm: [] for arm in ARM_NAMES} for event in events
    }
    for founder in study.founders:
        founders_by_event[founder.edit_event_id][founder.arm].append(founder)
    daughters_by_founder = {row.founder_id: [] for row in study.founders}
    for child in study.daughters:
        daughters_by_founder[child.founder_id].append(child)

    selection: list[tuple[float | None, float | None]] = []
    followup_hours: list[tuple[float | None, float | None]] = []
    clone_g_c: dict[str, dict[str, list[tuple[str, float]]]] = {
        event: {arm: [] for arm in ARM_NAMES} for event in events
    }
    event_g_c_ratio: list[float | None] = []
    competing = {arm: _empty_arm_counts() for arm in ARM_NAMES}
    field_errors: dict[str, dict[str, int]] = {arm: {} for arm in ARM_NAMES}
    field_completions: dict[str, dict[str, int]] = {arm: {} for arm in ARM_NAMES}
    rates: dict[str, dict[str, dict[str, float | None]]] = {}
    within: dict[str, dict[str, dict[str, float | None]]] = {}
    numerators: dict[str, dict[str, dict[str, int | None]]] = {}
    points: dict[str, dict[str, dict[str, float | None]]] = {}
    _PROPORTION_ESTIMANDS = (
        "generation",
        "founder_error",
        "division",
        "death",
        "dropout",
        "selection",
    )

    for event in events:
        event_generation: dict[str, float | None] = {}
        event_founder_error: dict[str, float | None] = {}
        event_division: dict[str, float | None] = {}
        event_death: dict[str, float | None] = {}
        event_dropout: dict[str, float | None] = {}
        event_selection: dict[str, float | None] = {}
        event_hours: dict[str, float | None] = {}
        event_within: dict[str, dict[str, float | None]] = {
            name: {} for name in _PROPORTION_ESTIMANDS
        }
        event_numerators: dict[str, dict[str, int | None]] = {
            name: {} for name in _PROPORTION_ESTIMANDS
        }
        event_point: dict[str, dict[str, float | None]] = {
            name: {} for name in _PROPORTION_ESTIMANDS
        }
        for arm in ARM_NAMES:
            rows = founders_by_event[event][arm]
            enrolled = len(rows)
            counts = _empty_arm_counts()
            clone_completed: dict[str, int] = {}
            clone_error: dict[str, int] = {}
            hours: list[float] = []
            error_followed = 0
            error_reproduced = 0
            nonerror_followed = 0
            nonerror_reproduced = 0
            clone_err_followed: dict[str, int] = {}
            clone_err_reproduced: dict[str, int] = {}
            clone_nonerr_followed: dict[str, int] = {}
            clone_nonerr_reproduced: dict[str, int] = {}
            for founder in rows:
                counts[founder.first_attempt_outcome] += 1
                competing[arm][founder.first_attempt_outcome] += 1
                clone_completed.setdefault(founder.clone_id, 0)
                clone_error.setdefault(founder.clone_id, 0)
                if founder.first_attempt_outcome in COMPLETED_OUTCOMES:
                    clone_completed[founder.clone_id] += 1
                    field_completions[arm][founder.field_id] = (
                        field_completions[arm].get(founder.field_id, 0) + 1
                    )
                    started = _parse_utc(
                        founder.first_attempt_started_at, "first_attempt_started_at"
                    )
                    ended = _parse_utc(
                        founder.first_attempt_ended_at, "first_attempt_ended_at"
                    )
                    hours.append((ended - started).total_seconds() / 3600.0)
                if founder.first_attempt_outcome == "completed_error":
                    clone_error[founder.clone_id] += 1
                    field_errors[arm][founder.field_id] = (
                        field_errors[arm].get(founder.field_id, 0) + 1
                    )
                for child in daughters_by_founder[founder.founder_id]:
                    # Only a resolved terminal fate counts as followed: a
                    # censored daughter is unaccounted progeny and cannot
                    # satisfy the follow-up obligation or dilute a rate.
                    followed = child.outcome in ("reproduced", "died")
                    reproduced = child.outcome == "reproduced"
                    if founder.first_attempt_outcome == "completed_error":
                        error_followed += int(followed)
                        error_reproduced += int(reproduced)
                        clone_err_followed[founder.clone_id] = (
                            clone_err_followed.get(founder.clone_id, 0)
                            + int(followed)
                        )
                        clone_err_reproduced[founder.clone_id] = (
                            clone_err_reproduced.get(founder.clone_id, 0)
                            + int(reproduced)
                        )
                    elif founder.first_attempt_outcome == "completed_no_error":
                        nonerror_followed += int(followed)
                        nonerror_reproduced += int(reproduced)
                        clone_nonerr_followed[founder.clone_id] = (
                            clone_nonerr_followed.get(founder.clone_id, 0)
                            + int(followed)
                        )
                        clone_nonerr_reproduced[founder.clone_id] = (
                            clone_nonerr_reproduced.get(founder.clone_id, 0)
                            + int(reproduced)
                        )
            completed = counts["completed_error"] + counts["completed_no_error"]
            if (
                enrolled == 0
                or completed < MINIMUM_COMPLETED_PER_EVENT_ARM
                or len(clone_completed) < MINIMUM_CLONES_PER_EVENT
            ):
                event_generation[arm] = None
                event_founder_error[arm] = None
                event_division[arm] = None
                event_death[arm] = None
                event_dropout[arm] = None
                for name in (
                    "generation",
                    "founder_error",
                    "division",
                    "death",
                    "dropout",
                ):
                    event_within[name][arm] = None
                    event_numerators[name][arm] = None
                    event_point[name][arm] = None
            else:
                event_generation[arm] = counts["completed_error"] / completed
                event_founder_error[arm] = counts["completed_error"] / enrolled
                event_division[arm] = completed / enrolled
                event_death[arm] = counts["death_before_completion"] / enrolled
                event_dropout[arm] = counts["dropout_censored"] / enrolled
                event_within["generation"][arm] = _proportion_within(
                    counts["completed_error"], completed
                )
                event_within["founder_error"][arm] = _proportion_within(
                    counts["completed_error"], enrolled
                )
                event_within["division"][arm] = _proportion_within(
                    completed, enrolled
                )
                event_within["death"][arm] = _proportion_within(
                    counts["death_before_completion"], enrolled
                )
                event_within["dropout"][arm] = _proportion_within(
                    counts["dropout_censored"], enrolled
                )
                event_numerators["generation"][arm] = counts["completed_error"]
                event_numerators["founder_error"][arm] = counts["completed_error"]
                event_numerators["division"][arm] = completed
                event_numerators["death"][arm] = counts["death_before_completion"]
                event_numerators["dropout"][arm] = counts["dropout_censored"]
                event_point["generation"][arm] = _rate_point(
                    counts["completed_error"], completed
                )
                event_point["founder_error"][arm] = _rate_point(
                    counts["completed_error"], enrolled
                )
                event_point["division"][arm] = _rate_point(
                    completed, enrolled
                )
                event_point["death"][arm] = _rate_point(
                    counts["death_before_completion"], enrolled
                )
                event_point["dropout"][arm] = _rate_point(
                    counts["dropout_censored"], enrolled
                )
            if completed > 0:
                dominant = max(clone_completed.values()) / completed
                if dominant > CLONE_SHARE_LIMIT:
                    qc["clone_concentration"] = True
            for clone_id, clone_n in clone_completed.items():
                if clone_n > 0:
                    clone_g_c[event][arm].append(
                        (clone_id, clone_error.get(clone_id, 0) / clone_n)
                    )
            if (
                error_followed >= MINIMUM_RESOLVED_ERROR_DAUGHTERS
                and nonerror_followed >= MINIMUM_RESOLVED_NONERROR_DAUGHTERS
                and nonerror_reproduced > 0
            ):
                event_selection[arm] = (error_reproduced / error_followed) / (
                    nonerror_reproduced / nonerror_followed
                )
                # A ratio of proportions: the log-space within variance is
                # the sum of the two component variances.
                event_within["selection"][arm] = _proportion_within(
                    error_reproduced, error_followed
                ) + _proportion_within(
                    nonerror_reproduced, nonerror_followed
                )
                event_numerators["selection"][arm] = error_reproduced
                # A ratio of proportions: each component rate uses the
                # raw estimate when positive, smoothing only a zero
                # numerator (nonerror_reproduced > 0 is guaranteed by
                # the estimability gate above).
                event_point["selection"][arm] = _rate_point(
                    error_reproduced, error_followed
                ) / (nonerror_reproduced / nonerror_followed)
            else:
                event_selection[arm] = None
                event_within["selection"][arm] = None
                event_numerators["selection"][arm] = None
                event_point["selection"][arm] = None
            clone_selection_ratios: list[float] = []
            for clone_id, followed in clone_err_followed.items():
                nonerr_followed = clone_nonerr_followed.get(clone_id, 0)
                if (
                    followed < MINIMUM_RESOLVED_CLONE_DAUGHTERS
                    or nonerr_followed < MINIMUM_RESOLVED_CLONE_DAUGHTERS
                ):
                    continue
                err_reproduced = clone_err_reproduced.get(clone_id, 0)
                nonerr_reproduced = clone_nonerr_reproduced.get(clone_id, 0)
                if nonerr_reproduced == 0:
                    if err_reproduced > 0:
                        clone_selection_ratios.append(math.inf)
                    continue
                clone_selection_ratios.append(
                    (err_reproduced / followed)
                    / (nonerr_reproduced / nonerr_followed)
                )
            pooled = event_selection[arm]
            if (
                clone_selection_ratios
                and (
                    max(clone_selection_ratios) >= SELECTION_INCREASE_RATIO
                    or min(clone_selection_ratios) <= SELECTION_REDUCTION_RATIO
                )
                and (
                    pooled is None
                    or SELECTION_REDUCTION_RATIO <= pooled <= SELECTION_INCREASE_RATIO
                )
            ):
                qc["clone_selection_conflict"] = True
            event_hours[arm] = sum(hours) / len(hours) if hours else None
        selection.append((event_selection["vehicle"], event_selection["treatment"]))
        followup_hours.append((event_hours["vehicle"], event_hours["treatment"]))
        if (
            event_generation["vehicle"] not in (None, 0.0)
            and event_generation["treatment"] is not None
        ):
            event_g_c_ratio.append(
                event_generation["treatment"] / event_generation["vehicle"]
            )
        else:
            event_g_c_ratio.append(None)
        rates[event] = {
            "generation": event_generation,
            "founder_error": event_founder_error,
            "division": event_division,
            "death": event_death,
            "dropout": event_dropout,
        }
        within[event] = event_within
        numerators[event] = event_numerators
        points[event] = event_point

    vehicle_generation = [rates[event]["generation"]["vehicle"] for event in events]
    treatment_generation = [rates[event]["generation"]["treatment"] for event in events]
    vehicle_founder_error = [rates[event]["founder_error"]["vehicle"] for event in events]
    treatment_founder_error = [rates[event]["founder_error"]["treatment"] for event in events]
    vehicle_division = [rates[event]["division"]["vehicle"] for event in events]
    treatment_division = [rates[event]["division"]["treatment"] for event in events]
    vehicle_death = [rates[event]["death"]["vehicle"] for event in events]
    treatment_death = [rates[event]["death"]["treatment"] for event in events]
    vehicle_dropout = [rates[event]["dropout"]["vehicle"] for event in events]
    treatment_dropout = [rates[event]["dropout"]["treatment"] for event in events]

    def _event_spike(
        vehicle_values: list[float | None],
        treatment_values: list[float | None],
        ratio_cutoff: float,
    ) -> bool:
        for vehicle, treatment in zip(vehicle_values, treatment_values):
            if vehicle is None or treatment is None:
                continue
            if vehicle == 0.0:
                if treatment > 0.0:
                    return True
            elif treatment / vehicle >= ratio_cutoff:
                return True
        return False

    event_death_spike = _event_spike(
        vehicle_death, treatment_death, TOXICITY_INCREASE_RATIO
    )
    event_dropout_spike = _event_spike(
        vehicle_dropout, treatment_dropout, DROPOUT_INCREASE_RATIO
    )
    # A single event's ≥2x harm must not dilute into a pooled reduction —
    # the event-level spike guards the primary estimands the way death
    # and dropout are already guarded.
    event_generation_spike = _event_spike(
        vehicle_generation, treatment_generation, TOXICITY_INCREASE_RATIO
    )
    event_founder_spike = _event_spike(
        vehicle_founder_error, treatment_founder_error, TOXICITY_INCREASE_RATIO
    )

    def _estimand_kwargs(name: str) -> dict[str, list]:
        return {
            "vehicle_within": [within[e][name]["vehicle"] for e in events],
            "treatment_within": [within[e][name]["treatment"] for e in events],
            "vehicle_numerators": [numerators[e][name]["vehicle"] for e in events],
            "treatment_numerators": [
                numerators[e][name]["treatment"] for e in events
            ],
            "vehicle_points": [points[e][name]["vehicle"] for e in events],
            "treatment_points": [points[e][name]["treatment"] for e in events],
        }

    generation_est = _ratio_estimate(
        vehicle_generation,
        treatment_generation,
        DEFAULT_CONFIDENCE_MULTIPLIER,
        **_estimand_kwargs("generation"),
    )
    founder_est = _ratio_estimate(
        vehicle_founder_error,
        treatment_founder_error,
        DEFAULT_CONFIDENCE_MULTIPLIER,
        **_estimand_kwargs("founder_error"),
    )
    division_est = _ratio_estimate(
        vehicle_division,
        treatment_division,
        DEFAULT_CONFIDENCE_MULTIPLIER,
        **_estimand_kwargs("division"),
    )
    death_est = _ratio_estimate(
        vehicle_death,
        treatment_death,
        DEFAULT_CONFIDENCE_MULTIPLIER,
        **_estimand_kwargs("death"),
    )
    dropout_est = _ratio_estimate(
        vehicle_dropout,
        treatment_dropout,
        DEFAULT_CONFIDENCE_MULTIPLIER,
        **_estimand_kwargs("dropout"),
    )
    selection_est = _ratio_estimate(
        [pair[0] for pair in selection],
        [pair[1] for pair in selection],
        DEFAULT_CONFIDENCE_MULTIPLIER,
        **_estimand_kwargs("selection"),
    )
    # Follow-up hours are durations, not proportions — no within-event
    # proportion variance or numerator-informativeness check applies.
    followup_est = _ratio_estimate(
        [pair[0] for pair in followup_hours],
        [pair[1] for pair in followup_hours],
        DEFAULT_CONFIDENCE_MULTIPLIER,
    )

    if _increased(dropout_est, DROPOUT_INCREASE_RATIO) or event_dropout_spike:
        qc["treatment_dependent_dropout"] = True
    if (
        followup_est.estimable
        and followup_est.ratio is not None
        and followup_est.ratio <= FOLLOWUP_HOURS_RATIO_FLOOR
        and followup_est.upper is not None
        and followup_est.upper < 1.0
    ):
        qc["unequal_followup"] = True

    n_fields = {arm: len({row.field_id for row in study.founders if row.arm == arm}) for arm in ARM_NAMES}
    for arm in ARM_NAMES:
        completions = sum(field_completions[arm].values())
        errors = sum(field_errors[arm].values())
        if completions > 0 and n_fields[arm] > 1:
            max_completion_share = max(field_completions[arm].values()) / completions
            if max_completion_share > FIELD_SHARE_LIMIT:
                qc["field_concentration"] = True
        if errors > 0 and n_fields[arm] > 1:
            max_error_share = max(field_errors[arm].values()) / errors
            if max_error_share > FIELD_SHARE_LIMIT:
                qc["field_concentration"] = True

    reduced_events = [
        ratio is not None and ratio <= UNIT_REDUCTION_RATIO for ratio in event_g_c_ratio
    ]
    if sum(reduced_events) == 1:
        qc["single_edit_event_effect"] = True

    for index, event in enumerate(events):
        event_ratio = event_g_c_ratio[index]
        if event_ratio is None or event_ratio > UNIT_REDUCTION_RATIO:
            continue
        vehicle_clones = {name: rate for name, rate in clone_g_c[event]["vehicle"]}
        event_clones_tested = 0
        event_clone_reductions = 0
        for clone_id, treatment_rate in clone_g_c[event]["treatment"]:
            vehicle_rate = vehicle_clones.get(clone_id)
            if vehicle_rate is None or treatment_rate is None:
                continue
            event_clones_tested += 1
            if (
                vehicle_rate > 0.0
                and treatment_rate / vehicle_rate <= UNIT_REDUCTION_RATIO
            ):
                event_clone_reductions += 1
        if event_clones_tested < 2 or event_clone_reductions == 1:
            qc["single_clone_effect"] = True
            break

    qc_failed = any(qc.values())
    biological = {
        "generation_reduction": (
            _reduced(generation_est, GENERATION_REDUCTION_RATIO)
            and _reduced(founder_est, GENERATION_REDUCTION_RATIO)
        ),
        "error_daughter_pruning": _reduced(selection_est, SELECTION_REDUCTION_RATIO),
        "error_daughter_preservation": _increased(
            selection_est, SELECTION_INCREASE_RATIO
        ),
        "cytostasis": _reduced(division_est, DIVISION_REDUCTION_RATIO),
        "general_toxicity": (
            _increased(death_est, TOXICITY_INCREASE_RATIO) or event_death_spike
        ),
        "per_event_harm_spike": (
            event_generation_spike or event_founder_spike
        ),
    }
    estimates = {
        "generation_rate": generation_est,
        "founder_error_bearing_completion": founder_est,
        "relative_error_daughter_reproduction": selection_est,
        "division_completion": division_est,
        "pre_division_death": death_est,
        "dropout": dropout_est,
    }
    if qc_failed:
        biological = {name: False for name in BIOLOGICAL_FLAGS}
        estimates = {
            name: RatioEstimate(False, None, None, None, "lineage quality control failed")
            for name in ESTIMANDS
        }
    core_estimable = all(estimates[name].estimable for name in CORE_ESTIMANDS)
    all_core_estimable = core_estimable and estimates[
        "relative_error_daughter_reproduction"
    ].estimable

    mean_vehicle_division = None
    mean_treatment_division = None
    max_event_drop = None
    paired_division = [
        (float(vehicle), float(treatment))
        for vehicle, treatment in zip(vehicle_division, treatment_division)
        if vehicle is not None and treatment is not None
    ]
    if all(value is not None for value in (*vehicle_division, *treatment_division)):
        mean_vehicle_division = sum(float(value) for value in vehicle_division) / len(
            vehicle_division
        )
        mean_treatment_division = sum(float(value) for value in treatment_division) / len(
            treatment_division
        )
    if paired_division:
        max_event_drop = max(vehicle - treatment for vehicle, treatment in paired_division)
    pediatric_equivalent = bool(
        not qc_failed
        and division_est.estimable
        and division_est.lower is not None
        and division_est.upper is not None
        and division_est.lower >= study.completion_band.relative_lower
        and division_est.upper <= study.completion_band.relative_upper
        and mean_vehicle_division is not None
        and mean_treatment_division is not None
        and (mean_vehicle_division - mean_treatment_division)
        <= study.completion_band.absolute_drop_max
        and max_event_drop is not None
        and max_event_drop <= study.completion_band.absolute_drop_max
    )
    adverse = any(biological[name] for name in BIOLOGICAL_FLAGS if name != "generation_reduction")
    clean = bool(
        biological["generation_reduction"]
        and all_core_estimable
        and pediatric_equivalent
        and not adverse
        and not qc_failed
    )
    if qc["label_leakage"] or qc["unlocked"]:
        interpretation = "label_leakage" if qc["label_leakage"] else "unlocked"
    elif qc_failed and not biological["generation_reduction"]:
        interpretation = "measurement_invalid"
    elif biological["generation_reduction"] and not pediatric_equivalent:
        interpretation = "generation_signal_with_unresolved_competing_completion"
    elif biological["generation_reduction"] and core_estimable and not all_core_estimable:
        interpretation = "generation_signal_incomplete_deconvolution"
    elif clean:
        interpretation = "generation_reduction_without_detected_configured_confound"
    elif any(biological.values()):
        interpretation = "mixed_components"
    elif not core_estimable:
        interpretation = "insufficient_information"
    else:
        interpretation = "no_detectable_component"
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_cohort_outcome_model": (
            "enrolled founder; first attempt is dropout, pre-division death, "
            "no division, completed-no-error, or completed-error"
        ),
        "primary_cohort_boundary": (
            "pre-division death is labeled separately from other non-completion"
        ),
        "estimates": {name: estimate.as_dict() for name, estimate in estimates.items()},
        "followup_hours_ratio": followup_est.as_dict(),
        "status": {
            "blinded": study.blinded,
            "locked": study.lock_state == "locked",
            "measurement_valid": not qc_failed,
            "core_estimable": core_estimable,
            "all_core_estimable": all_core_estimable,
            "pediatric_completion_equivalent": pediatric_equivalent,
            "clean_generation_signal": clean,
            "pre_division_death_separated": True,
            "highest_inferential_unit": "edit_event",
            "clone_is_not_an_independent_replicate": True,
        },
        "flags": {**biological, **qc},
        "interpretation": interpretation,
        "competing_first_attempt": competing,
        "n_edit_events": len(events),
        "n_founders": len(study.founders),
        "n_daughters": len(study.daughters),
    }


def default_completion_band() -> CompletionBand:
    return CompletionBand(
        relative_lower=0.95, relative_upper=1.10, absolute_drop_max=0.05
    )


def _stamp(hours: float) -> str:
    origin = datetime(2026, 8, 29, tzinfo=timezone.utc)
    return _format_utc(origin + timedelta(hours=hours))


def lineage_study_from_counts(
    *,
    study_id: str,
    per_event: dict[str, dict[str, dict[str, int]]],
    daughter_plan: dict[str, dict[str, dict[str, int]]] | None = None,
    daughter_plan_by_clone: (
        dict[str, dict[str, dict[str, dict[str, int]]]] | None
    ) = None,
    field_by_event: dict[str, str] | None = None,
    split_error_fields: bool = False,
    attempt_hours_by_arm: dict[str, float] | None = None,
    zero_error_treatment_clone: str | None = None,
    blinded: bool = True,
    lock_state: str = "locked",
    unblinded_at: str | None = None,
    enroll_after_exposure: bool = False,
    extra_followup_hours: dict[str, float] | None = None,
    clones_per_event: int = 2,
    validate: bool = True,
) -> LineageStudy:
    """Build a locked synthetic study from exact competing-risk counts.

    ``validate=False`` skips the study-level ``LineageStudy`` checks —
    reserved for hot simulation loops whose generated counts satisfy the
    study invariants by construction (unique serial ids, clone nesting
    inside one event, consistent execution contexts). Fixture and test
    callers always validate.
    """

    if daughter_plan_by_clone is not None and zero_error_treatment_clone is not None:
        raise LineageError(
            "per-clone daughter plans cannot be combined with a zeroed error clone"
        )
    if (
        not isinstance(clones_per_event, int)
        or isinstance(clones_per_event, bool)
        or clones_per_event < 1
    ):
        raise LineageError("clones_per_event must be a positive integer")
    from mva_hackathon.exposure_gate import make_exposure_profile_id

    treatment_profile = {
        "nominal_uM": 1.0,
        "unbound_medium_uM": 0.71,
        "intracellular_parent": 0.33,
        "time_hours": 24,
        "pulse_vs_constant": "constant",
        "washout": False,
        "measurement_class": "culture_measured",
    }
    treatment_profile_id = make_exposure_profile_id(
        treatment_profile, "syn-probe-a"
    )
    founders: list[Founder] = []
    daughters: list[Daughter] = []
    clone_key_serial: dict[tuple[str, str], int] = {}
    extra_hours = extra_followup_hours or {}
    attempt_hours = attempt_hours_by_arm or {}
    for event_id, arms in per_event.items():
        default_field = (field_by_event or {}).get(event_id, "syn-field-shared")
        for arm, counts in arms.items():
            unknown = set(counts) - set(FIRST_ATTEMPT_OUTCOMES)
            if unknown:
                raise LineageError("unsupported first-attempt count key")
            total_rows = 0
            for outcome in FIRST_ATTEMPT_OUTCOMES:
                count_value = counts.get(outcome, 0)
                if (
                    not isinstance(count_value, int)
                    or isinstance(count_value, bool)
                    or count_value < 0
                ):
                    raise LineageError(
                        "first-attempt counts must be non-negative integers"
                    )
                total_rows += count_value
            # Counts materialize one Founder object each; without a bound a
            # single arm key can request arbitrarily many objects.
            if total_rows > 100_000:
                raise LineageError(
                    "first-attempt counts exceed the materialization ceiling"
                )
            serial = 0
            # Founders within an (event, arm, clone, outcome) block are
            # identical except for the unique founder_id — build one
            # validated prototype per block and copy it, so dense
            # fixtures do not pay per-row validation cost for values the
            # builder itself generated.
            founder_protos: dict[tuple[object, ...], Founder] = {}
            daughter_protos: dict[tuple[object, ...], Daughter] = {}
            for outcome in FIRST_ATTEMPT_OUTCOMES:
                for _ in range(int(counts.get(outcome, 0))):
                    serial += 1
                    clone_index = (serial - 1) % clones_per_event + 1
                    clone_id = f"syn-clone-{event_id}-{clone_index}"
                    assigned_outcome = outcome
                    if (
                        zero_error_treatment_clone is not None
                        and arm == "treatment"
                        and clone_id == zero_error_treatment_clone
                        and outcome == "completed_error"
                    ):
                        assigned_outcome = "completed_no_error"
                    founder_id = f"syn-f-{event_id}-{arm}-{serial}"
                    duration = attempt_hours.get(arm, 12.0)
                    if split_error_fields:
                        field_id = (
                            "syn-field-hot"
                            if assigned_outcome == "completed_error"
                            else "syn-field-cold"
                        )
                    else:
                        field_id = default_field
                    proto_key = (
                        arm, event_id, clone_id, assigned_outcome, field_id
                    )
                    founder = founder_protos.get(proto_key)
                    if founder is None:
                        enrolled_at = _stamp(0.0)
                        exposure_at = _stamp(
                            -1.0 if enroll_after_exposure else 1.0
                        )
                        started_at = None
                        ended_at = None
                        censor_reason = None
                        if assigned_outcome == "dropout_censored":
                            censor_reason = "syn-lost-contact"
                        elif assigned_outcome == "death_before_completion":
                            started_at = _stamp(2.0)
                            ended_at = _stamp(2.0 + duration / 2.0)
                        else:
                            started_at = _stamp(2.0)
                            ended_at = _stamp(2.0 + duration)
                        founder = Founder(
                            founder_id=founder_id,
                            arm=arm,
                            edit_event_id=event_id,
                            clone_id=clone_id,
                            run_id="syn-run-1",
                            field_id=field_id,
                            batch_id="syn-batch-1",
                            functional_execution_id=(
                                f"syn-functional-{event_id}-{clone_index}-{arm}"
                            ),
                            exposure_support_record_id=(
                                "syn-measurement-3"
                                if arm == "treatment"
                                else "syn-vehicle-control-record-a"
                            ),
                            exposure_profile_id=(
                                treatment_profile_id
                                if arm == "treatment"
                                else "profile-vehicle-control"
                            ),
                            exposure_probe_id=(
                                "syn-probe-a" if arm == "treatment" else "syn-vehicle-a"
                            ),
                            enrolled_at=enrolled_at,
                            exposure_started_at=exposure_at,
                            first_attempt_started_at=started_at,
                            first_attempt_ended_at=ended_at,
                            first_attempt_outcome=assigned_outcome,
                            censor_reason=censor_reason,
                        )
                        founder_protos[proto_key] = founder
                    else:
                        founder = _clone_row(founder, founder_id=founder_id)
                    founders.append(founder)
                    if assigned_outcome not in COMPLETED_OUTCOMES:
                        continue
                    plan_root = (daughter_plan or {}).get(event_id, {}).get(arm, {})
                    clone_plan = (
                        (daughter_plan_by_clone or {})
                        .get(event_id, {})
                        .get(arm, {})
                        .get(clone_id, {})
                    )
                    key = "error" if assigned_outcome == "completed_error" else "nonerror"
                    reproduced_raw = plan_root.get(f"{key}_reproduced", 1)
                    died_raw = plan_root.get(f"{key}_died", 0)
                    died_every_raw = clone_plan.get(f"{key}_died_every", 0)
                    for plan_value in (reproduced_raw, died_raw, died_every_raw):
                        if (
                            not isinstance(plan_value, int)
                            or isinstance(plan_value, bool)
                            or plan_value < 0
                        ):
                            raise LineageError(
                                "daughter plan counts must be non-negative integers"
                            )
                    reproduced = reproduced_raw
                    died = died_raw
                    died_every = died_every_raw
                    key_serial = (
                        clone_key_serial.get((clone_id, key), 0) + 1
                    )
                    clone_key_serial[(clone_id, key)] = key_serial
                    first_outcome = "reproduced"
                    if died_every > 0 and key_serial % died_every == 0:
                        first_outcome = "died"
                    elif died > 0 and reproduced == 0:
                        first_outcome = "died"
                    observe_at = _stamp(2.0 + duration + 6.0 + extra_hours.get(arm, 0.0))
                    daughter_key = (first_outcome, observe_at)
                    pair = daughter_protos.get(daughter_key)
                    if pair is None:
                        pair = (
                            Daughter(
                                daughter_id=f"{founder_id}-d1",
                                founder_id=founder_id,
                                observed_at=observe_at,
                                outcome=first_outcome,
                            ),
                            Daughter(
                                daughter_id=f"{founder_id}-d2",
                                founder_id=founder_id,
                                observed_at=observe_at,
                                outcome="not_followed",
                            ),
                        )
                        daughter_protos[daughter_key] = pair
                    else:
                        first, second = pair
                        pair = (
                            _clone_row(
                                first,
                                daughter_id=f"{founder_id}-d1",
                                founder_id=founder_id,
                            ),
                            _clone_row(
                                second,
                                daughter_id=f"{founder_id}-d2",
                                founder_id=founder_id,
                            ),
                        )
                    daughters.extend(pair)
    payload = {
        "schema": SCHEMA,
        "study_id": study_id,
        "blinded": blinded,
        "lock_state": lock_state,
        "unblinded_at": unblinded_at,
        "adjudication_locked_at": _stamp(48.0),
        "completion_band": default_completion_band(),
        "founders": tuple(founders),
        "daughters": tuple(daughters),
        "allocation_id": None,
    }
    if validate:
        return LineageStudy(**payload)
    study = object.__new__(LineageStudy)
    study.__dict__.update(payload)
    return study


def balanced_event_counts(
    *,
    completed_error: int,
    completed_no_error: int,
    no_division: int = 1,
    death_before_completion: int = 1,
    dropout_censored: int = 0,
) -> dict[str, int]:
    return {
        "completed_error": completed_error,
        "completed_no_error": completed_no_error,
        "no_division": no_division,
        "death_before_completion": death_before_completion,
        "dropout_censored": dropout_censored,
    }


def _three_events(vehicle: dict[str, int], treatment: dict[str, int]) -> dict[str, dict[str, dict[str, int]]]:
    return {
        f"syn-event-{index}": {"vehicle": dict(vehicle), "treatment": dict(treatment)}
        for index in (1, 2, 3)
    }


def build_adversarial_fixture(name: str) -> LineageStudy:
    """Return a truth-free observed study for a named software stress case."""

    vehicle = balanced_event_counts(completed_error=8, completed_no_error=28)
    if name == "clean_generation":
        # Denser denominators than the shared vehicle arm: the completion
        # band requires the division ratio's interval to sit inside
        # [0.95, 1.10], and the generation/founder reductions must clear
        # their 0.75 upper-bound cutoffs under the within-event variance
        # term. At 36 completed per arm the sampling noise alone is wider
        # than the band; 108 completed per arm is what a real certifiable
        # reduction needs.
        dense_vehicle = balanced_event_counts(
            completed_error=24, completed_no_error=84
        )
        treatment = balanced_event_counts(
            completed_error=6, completed_no_error=102
        )
        return lineage_study_from_counts(
            study_id="syn-clean-generation",
            per_event=_three_events(dense_vehicle, treatment),
        )
    if name == "pruning_only":
        treatment = dict(vehicle)
        plan = {
            f"syn-event-{index}": {
                "vehicle": {"error_reproduced": 1, "error_died": 0, "nonerror_reproduced": 1, "nonerror_died": 0},
                "treatment": {"error_reproduced": 0, "error_died": 1, "nonerror_reproduced": 1, "nonerror_died": 0},
            }
            for index in (1, 2, 3)
        }
        return lineage_study_from_counts(
            study_id="syn-pruning-only",
            per_event=_three_events(vehicle, treatment),
            daughter_plan=plan,
        )
    if name == "cytostasis":
        treatment = balanced_event_counts(completed_error=3, completed_no_error=9, no_division=12)
        return lineage_study_from_counts(
            study_id="syn-cytostasis",
            per_event=_three_events(vehicle, treatment),
        )
    if name == "mixed_insufficient":
        # A genuine generation signal (0.05 vs 0.22 error-bearing
        # completion) sitting on top of a suppressed division rate —
        # dense enough that the reduction is certifiable, so the
        # expected outcome is the cytostasis interpretation rather than
        # an inestimable washout.
        treatment = balanced_event_counts(
            completed_error=3, completed_no_error=57, no_division=48
        )
        plan = {
            f"syn-event-{index}": {
                "vehicle": {"error_reproduced": 1, "error_died": 0, "nonerror_reproduced": 1, "nonerror_died": 0},
                "treatment": {"error_reproduced": 0, "error_died": 1, "nonerror_reproduced": 1, "nonerror_died": 0},
            }
            for index in (1, 2, 3)
        }
        return lineage_study_from_counts(
            study_id="syn-mixed-insufficient",
            per_event=_three_events(vehicle, treatment),
            daughter_plan=plan,
        )
    if name == "field_concentration":
        treatment = balanced_event_counts(completed_error=2, completed_no_error=34)
        return lineage_study_from_counts(
            study_id="syn-field-concentration",
            per_event=_three_events(vehicle, treatment),
            split_error_fields=True,
        )
    if name == "one_clone_false_positive":
        return lineage_study_from_counts(
            study_id="syn-one-clone-false-positive",
            per_event=_three_events(vehicle, vehicle),
            zero_error_treatment_clone="syn-clone-syn-event-1-1",
        )
    if name == "one_edit_event_false_positive":
        per_event = _three_events(vehicle, vehicle)
        per_event["syn-event-1"]["treatment"] = balanced_event_counts(
            completed_error=1, completed_no_error=35
        )
        return lineage_study_from_counts(
            study_id="syn-one-edit-event-false-positive",
            per_event=per_event,
        )
    if name == "toxic_pruning":
        treatment = balanced_event_counts(
            completed_error=8,
            completed_no_error=8,
            no_division=1,
            death_before_completion=19,
        )
        return lineage_study_from_counts(
            study_id="syn-toxic-pruning",
            per_event=_three_events(vehicle, treatment),
        )
    if name == "preservation":
        treatment = dict(vehicle)
        plan = {
            f"syn-event-{index}": {
                "vehicle": {"error_reproduced": 0, "error_died": 1, "nonerror_reproduced": 1, "nonerror_died": 0},
                "treatment": {"error_reproduced": 1, "error_died": 0, "nonerror_reproduced": 1, "nonerror_died": 0},
            }
            for index in (1, 2, 3)
        }
        return lineage_study_from_counts(
            study_id="syn-preservation",
            per_event=_three_events(vehicle, treatment),
            daughter_plan=plan,
        )
    if name == "clone_selection_washout":
        treatment = balanced_event_counts(completed_error=5, completed_no_error=30)
        clone_plan = {
            f"syn-event-{index}": {
                "treatment": {
                    f"syn-clone-syn-event-{index}-1": {"nonerror_died_every": 2},
                    f"syn-clone-syn-event-{index}-2": {"error_died_every": 2},
                }
            }
            for index in (1, 2, 3)
        }
        return lineage_study_from_counts(
            study_id="syn-clone-selection-washout",
            per_event=_three_events(vehicle, treatment),
            daughter_plan_by_clone=clone_plan,
        )
    if name == "label_leakage":
        treatment = balanced_event_counts(completed_error=2, completed_no_error=34)
        return lineage_study_from_counts(
            study_id="syn-label-leakage",
            per_event=_three_events(vehicle, treatment),
            blinded=False,
            unblinded_at=_stamp(24.0),
        )
    if name == "treatment_dependent_dropout":
        treatment = balanced_event_counts(
            completed_error=6,
            completed_no_error=14,
            dropout_censored=16,
            no_division=0,
            death_before_completion=0,
        )
        return lineage_study_from_counts(
            study_id="syn-treatment-dependent-dropout",
            per_event=_three_events(vehicle, treatment),
        )
    if name == "enroll_after_exposure":
        treatment = balanced_event_counts(completed_error=2, completed_no_error=34)
        return lineage_study_from_counts(
            study_id="syn-enroll-after-exposure",
            per_event=_three_events(vehicle, treatment),
            enroll_after_exposure=True,
        )
    if name == "unequal_followup":
        treatment = balanced_event_counts(completed_error=2, completed_no_error=34)
        return lineage_study_from_counts(
            study_id="syn-unequal-followup",
            per_event=_three_events(vehicle, treatment),
            attempt_hours_by_arm={"vehicle": 24.0, "treatment": 6.0},
        )
    if name == "zero_error_arm":
        # Every treatment founder completes without error. The smoothed
        # point estimate keeps the ratio finite and honest (~0.02, not a
        # 1e-9 artifact), but with zero error-bearing daughters the
        # preservation-vs-pruning deconvolution is structurally
        # impossible — the correct verdict is incomplete deconvolution,
        # never a clean signal.
        dense_vehicle = balanced_event_counts(
            completed_error=24, completed_no_error=84
        )
        treatment = balanced_event_counts(
            completed_error=0, completed_no_error=108
        )
        return lineage_study_from_counts(
            study_id="syn-zero-error-arm",
            per_event=_three_events(dense_vehicle, treatment),
        )
    if name == "diluted_harm_event":
        # Two events reduce while one event spikes error-bearing
        # completion at 2.5x vehicle. The pooled point still favors
        # treatment; the per-event harm spike must flag so a single
        # disastrous event cannot dilute into a population-level rescue.
        treatment_reduce = balanced_event_counts(
            completed_error=2, completed_no_error=34
        )
        treatment_spike = balanced_event_counts(
            completed_error=20, completed_no_error=16
        )
        return lineage_study_from_counts(
            study_id="syn-diluted-harm-event",
            per_event={
                "syn-event-1": {
                    "vehicle": dict(vehicle),
                    "treatment": dict(treatment_reduce),
                },
                "syn-event-2": {
                    "vehicle": dict(vehicle),
                    "treatment": dict(treatment_reduce),
                },
                "syn-event-3": {
                    "vehicle": dict(vehicle),
                    "treatment": dict(treatment_spike),
                },
            },
        )
    raise LineageError("unsupported adversarial fixture name")


ADVERSARIAL_CASES = (
    "clean_generation",
    "pruning_only",
    "cytostasis",
    "mixed_insufficient",
    "field_concentration",
    "one_clone_false_positive",
    "one_edit_event_false_positive",
    "toxic_pruning",
    "preservation",
    "label_leakage",
    "treatment_dependent_dropout",
    "unequal_followup",
    "clone_selection_washout",
    "zero_error_arm",
    "diluted_harm_event",
)


def expected_fixture_behavior(name: str) -> dict[str, Any]:
    """Evaluator-only expectations; never passed into the analyzer."""

    table = {
        "clean_generation": {
            "interpretation": "generation_reduction_without_detected_configured_confound",
            "require_flags": ("generation_reduction",),
            "forbid_flags": ("cytostasis", "error_daughter_pruning", "label_leakage"),
            "clean": True,
        },
        "pruning_only": {
            "interpretation": "mixed_components",
            "require_flags": ("error_daughter_pruning",),
            "forbid_flags": ("generation_reduction",),
            "clean": False,
        },
        "cytostasis": {
            "interpretation": "mixed_components",
            "require_flags": ("cytostasis",),
            "forbid_flags": ("generation_reduction",),
            "clean": False,
        },
        "mixed_insufficient": {
            "clean": False,
            "forbid_flags": (),
            "require_flags": ("cytostasis",),
            "interpretation": "generation_signal_with_unresolved_competing_completion",
        },
        "field_concentration": {
            "clean": False,
            "require_flags": ("field_concentration",),
            "forbid_flags": (),
            "interpretation": "measurement_invalid",
        },
        "one_clone_false_positive": {
            "clean": False,
            "require_flags": ("single_clone_effect",),
            "forbid_flags": (),
            "interpretation": "measurement_invalid",
        },
        "one_edit_event_false_positive": {
            "clean": False,
            "require_flags": ("single_edit_event_effect",),
            "forbid_flags": (),
            "interpretation": "measurement_invalid",
        },
        "toxic_pruning": {
            "clean": False,
            "require_flags": ("general_toxicity",),
            "forbid_flags": (),
            "interpretation": "mixed_components",
        },
        "preservation": {
            "clean": False,
            "require_flags": ("error_daughter_preservation",),
            "forbid_flags": ("generation_reduction",),
            "interpretation": "mixed_components",
        },
        "label_leakage": {
            "clean": False,
            "require_flags": ("label_leakage",),
            "forbid_flags": ("generation_reduction",),
            "interpretation": "label_leakage",
        },
        "treatment_dependent_dropout": {
            "clean": False,
            "require_flags": ("treatment_dependent_dropout",),
            "forbid_flags": (),
            "interpretation": "measurement_invalid",
        },
        "unequal_followup": {
            "clean": False,
            "require_flags": ("unequal_followup",),
            "forbid_flags": (),
            "interpretation": "measurement_invalid",
        },
        "clone_selection_washout": {
            "clean": False,
            "require_flags": ("clone_selection_conflict",),
            "forbid_flags": (),
            "interpretation": "measurement_invalid",
        },
        "zero_error_arm": {
            "clean": False,
            "require_flags": ("generation_reduction",),
            "forbid_flags": ("general_toxicity", "per_event_harm_spike"),
            "interpretation": "generation_signal_incomplete_deconvolution",
        },
        "diluted_harm_event": {
            "clean": False,
            "require_flags": ("per_event_harm_spike",),
            "forbid_flags": ("generation_reduction",),
            "interpretation": "mixed_components",
        },
    }
    if name not in table:
        raise LineageError("unsupported adversarial fixture name")
    return table[name]


def evaluate_fixture(name: str) -> dict[str, Any]:
    """Run the truth-blind analyzer and score it with evaluator-only expectations."""

    if name == "enroll_after_exposure":
        try:
            build_adversarial_fixture(name)
        except LineageError as exc:
            return {
                "name": name,
                "passed": "exposure cannot start before enrollment" in str(exc),
                "analysis": None,
                "reason": str(exc),
            }
        return {"name": name, "passed": False, "analysis": None, "reason": "contract accepted"}
    study = build_adversarial_fixture(name)
    analysis = analyze_lineage_study(study)
    expected = expected_fixture_behavior(name)
    passed = analysis["status"]["clean_generation_signal"] is expected["clean"]
    if expected["interpretation"] is not None:
        passed = passed and analysis["interpretation"] == expected["interpretation"]
    for flag in expected["require_flags"]:
        passed = passed and bool(analysis["flags"][flag])
    for flag in expected["forbid_flags"]:
        passed = passed and not bool(analysis["flags"][flag])
    return {"name": name, "passed": passed, "analysis": analysis, "reason": None}


def run_adversarial_suite() -> dict[str, Any]:
    rows = [evaluate_fixture(name) for name in (*ADVERSARIAL_CASES, "enroll_after_exposure")]
    passed = sum(bool(row["passed"]) for row in rows)
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "n_cases": len(rows),
        "passed": passed,
        "all_passed": passed == len(rows),
        "cases": [
            {
                "name": row["name"],
                "passed": row["passed"],
                "interpretation": (
                    None
                    if row["analysis"] is None
                    else row["analysis"]["interpretation"]
                ),
                "clean_generation_signal": (
                    None
                    if row["analysis"] is None
                    else row["analysis"]["status"]["clean_generation_signal"]
                ),
                "reason": row["reason"],
            }
            for row in rows
        ],
    }


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 1.0)
    probability = successes / total
    z = 1.959963984540054
    denominator = 1.0 + z * z / total
    center = (probability + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(
            probability * (1.0 - probability) / total + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return (max(0.0, center - half), min(1.0, center + half))


def export_first_attempt_aggregates(study: LineageStudy) -> dict[str, Any]:
    """Export truth-free per-clone first-attempt counts for lab handoff."""

    if not isinstance(study, LineageStudy):
        raise LineageError("exporter accepts a parsed lineage study only")
    daughters_by_founder: dict[str, list[Daughter]] = {
        row.founder_id: [] for row in study.founders
    }
    for child in study.daughters:
        daughters_by_founder[child.founder_id].append(child)
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for founder in study.founders:
        key = (founder.arm, founder.edit_event_id, founder.clone_id, founder.run_id)
        row = grouped.setdefault(
            key,
            {
                "contexts": set(),
                "endpoint_recorded_at": None,
                "latest_enrolled_at": None,
                "opportunities": 0,
                "detected_divisions": 0,
                "event_positive_divisions": 0,
                "event_negative_divisions": 0,
                "event_positive_daughters_followed": 0,
                "event_positive_daughters_reproduced": 0,
                "event_positive_daughters_died": 0,
                "event_positive_daughter_slots": 0,
                "event_positive_multipolar_divisions": 0,
                "event_negative_daughters_followed": 0,
                "event_negative_daughters_reproduced": 0,
                "event_negative_daughters_died": 0,
                "pre_division_death": 0,
                "no_division": 0,
                "dropout_censored": 0,
            },
        )
        context = (
            founder.batch_id,
            founder.functional_execution_id,
            founder.exposure_support_record_id,
            founder.exposure_profile_id,
            founder.exposure_probe_id,
            founder.exposure_started_at,
        )
        if study.allocation_id is not None:
            context += tuple(
                getattr(founder, field) for field in ALLOCATION_REALIZATION_FIELDS
            )
        row["contexts"].add(context)
        enrolled = _parse_utc(founder.enrolled_at, "enrolled_at")
        previous_enrolled = row["latest_enrolled_at"]
        if previous_enrolled is None or enrolled > previous_enrolled[0]:
            row["latest_enrolled_at"] = (enrolled, founder.enrolled_at)
        if founder.first_attempt_ended_at is not None:
            previous_end = row["endpoint_recorded_at"]
            if previous_end is None or founder.first_attempt_ended_at > previous_end:
                row["endpoint_recorded_at"] = founder.first_attempt_ended_at
        row["opportunities"] += 1
        if founder.first_attempt_outcome == "completed_error":
            row["detected_divisions"] += 1
            row["event_positive_divisions"] += 1
            row["event_positive_daughter_slots"] += max(
                DAUGHTERS_PER_BIPOLAR_DIVISION,
                len(daughters_by_founder[founder.founder_id]),
            )
            if founder.division_class == "multipolar":
                row["event_positive_multipolar_divisions"] += 1
        elif founder.first_attempt_outcome == "completed_no_error":
            row["detected_divisions"] += 1
            row["event_negative_divisions"] += 1
        elif founder.first_attempt_outcome == "death_before_completion":
            row["pre_division_death"] += 1
        elif founder.first_attempt_outcome == "no_division":
            row["no_division"] += 1
        elif founder.first_attempt_outcome == "dropout_censored":
            row["dropout_censored"] += 1
        for child in daughters_by_founder[founder.founder_id]:
            followed = child.outcome != "not_followed"
            if founder.first_attempt_outcome == "completed_error":
                row["event_positive_daughters_followed"] += int(followed)
                row["event_positive_daughters_reproduced"] += int(
                    child.outcome == "reproduced"
                )
                row["event_positive_daughters_died"] += int(child.outcome == "died")
            elif founder.first_attempt_outcome == "completed_no_error":
                row["event_negative_daughters_followed"] += int(followed)
                row["event_negative_daughters_reproduced"] += int(
                    child.outcome == "reproduced"
                )
                row["event_negative_daughters_died"] += int(child.outcome == "died")
    runs = []
    for arm, event_id, clone_id, run_id in sorted(grouped):
        payload = grouped[(arm, event_id, clone_id, run_id)]
        contexts = payload.pop("contexts")
        if len(contexts) != 1:
            raise LineageError("aggregate row merges multiple exposure contexts")
        context = next(iter(contexts))
        (
            batch_id,
            functional_execution_id,
            exposure_support_record_id,
            exposure_profile_id,
            exposure_probe_id,
            exposure_started_at,
            *realized_allocation,
        ) = context
        latest_enrolled = payload.pop("latest_enrolled_at")
        if (
            payload["event_positive_daughter_slots"]
            == DAUGHTERS_PER_BIPOLAR_DIVISION
            * payload["event_positive_divisions"]
        ):
            payload.pop("event_positive_daughter_slots")
        if payload["event_positive_multipolar_divisions"] == 0:
            payload.pop("event_positive_multipolar_divisions")
        run = {
            "arm": arm,
            "edit_event_id": event_id,
            "clone_id": clone_id,
            "run_id": run_id,
            "batch_id": batch_id,
            "functional_execution_id": functional_execution_id,
            "exposure_support_record_id": exposure_support_record_id,
            "exposure_profile_id": exposure_profile_id,
            "exposure_probe_id": exposure_probe_id,
            "exposure_started_at": exposure_started_at,
            "latest_enrolled_at": (
                None if latest_enrolled is None else latest_enrolled[1]
            ),
            **payload,
        }
        if study.allocation_id is not None:
            run.update(dict(zip(ALLOCATION_REALIZATION_FIELDS, realized_allocation)))
        runs.append(run)
    export = {
        "schema": "mva-track2-lineage-counts/v1",
        "study_id": study.study_id,
        "synthetic_only": True,
        "lock_state": study.lock_state,
        "blinded": study.blinded,
        "forbidden_keys_absent": sorted(FORBIDDEN_ANALYST_KEYS),
        "claim_boundary": CLAIM_BOUNDARY,
        "runs": runs,
    }
    if study.allocation_id is not None:
        export["allocation_id"] = study.allocation_id
    return export


def map_lineage_counts_to_observed_runs(
    export: Mapping[str, Any],
    *,
    id_map: Mapping[str, int],
) -> tuple[Any, ...]:
    """Map lineage counts into v3 observed-run integers, or refuse.

    Pre-division death, no-division, and dropout cannot be represented by the
    v3 aggregate contract. Silent dropping of those labels is forbidden.
    """

    from mva_hackathon.generation_selection import ObservedRun

    if not isinstance(export, Mapping) or export.get("schema") != "mva-track2-lineage-counts/v1":
        raise LineageError("mapper accepts lineage-count exports only")
    if export.get("lock_state") != "locked":
        raise LineageError("unlocked counts cannot be mapped into the aggregate contract")
    if export.get("blinded") is not True:
        raise LineageError("unblinded counts cannot be mapped into the aggregate contract")
    runs = export.get("runs")
    if not isinstance(runs, list) or not runs:
        raise LineageError("lineage-count export has no runs")
    mapped = []
    seen_rows: set[tuple[object, int, int, int]] = set()
    for row in runs:
        if not isinstance(row, Mapping):
            raise LineageError("count row must be an object")
        competing = (
            _nonnegative_integer(row.get("pre_division_death", 0), "pre_division_death")
            + _nonnegative_integer(row.get("no_division", 0), "no_division")
            + _nonnegative_integer(row.get("dropout_censored", 0), "dropout_censored")
        )
        if competing:
            raise LineageError(
                "competing-risk labels cannot be mapped into the aggregate contract"
            )
        try:
            event_id = id_map[str(row["edit_event_id"])]
            clone_id = id_map[str(row["clone_id"])]
            run_id = id_map[str(row["run_id"])]
        except KeyError as exc:
            raise LineageError("id_map is missing a lineage identifier") from exc
        # Count-integrity invariants for externally authored tables. The
        # exporter produces these by construction; a hand-authored table
        # must satisfy them too or it describes impossible biology:
        #   * every detected division is event-positive or event-negative;
        #   * with competing labels excluded, every opportunity divided;
        #   * daughters followed cannot exceed two per division;
        #   * reproduced/died daughters are a subset of followed.
        opportunities = _nonnegative_integer(row["opportunities"], "opportunities")
        detected = _nonnegative_integer(
            row["detected_divisions"], "detected_divisions"
        )
        pos_div = _nonnegative_integer(
            row["event_positive_divisions"], "event_positive_divisions"
        )
        neg_div = _nonnegative_integer(
            row["event_negative_divisions"], "event_negative_divisions"
        )
        if detected != pos_div + neg_div:
            raise LineageError(
                "detected divisions must equal event-positive plus event-negative"
            )
        if opportunities != detected:
            raise LineageError(
                "opportunities must equal detected divisions when competing labels are zero"
            )
        for sign, divisions in (("positive", pos_div), ("negative", neg_div)):
            followed = _nonnegative_integer(
                row[f"event_{sign}_daughters_followed"],
                f"event_{sign}_daughters_followed",
            )
            reproduced = _nonnegative_integer(
                row[f"event_{sign}_daughters_reproduced"],
                f"event_{sign}_daughters_reproduced",
            )
            died = _nonnegative_integer(
                row[f"event_{sign}_daughters_died"],
                f"event_{sign}_daughters_died",
            )
            # Declared daughter slots must be co-consistent with the declared
            # multipolar-division count: each multipolar division contributes
            # 3-4 recorded daughters, so slots live in
            # [2*div + multipolar, 2*div + 2*multipolar]. A slots claim beyond
            # the bipolar default without a multipolar declaration is
            # self-asserted evidence the contract does not accept.
            multipolar = 0
            if sign == "positive":
                multipolar_raw = row.get("event_positive_multipolar_divisions")
                if multipolar_raw is not None:
                    multipolar = _nonnegative_integer(
                        multipolar_raw, "event_positive_multipolar_divisions"
                    )
                    if multipolar > divisions:
                        raise LineageError(
                            "multipolar divisions cannot exceed event-positive divisions"
                        )
            slots_key = f"event_{sign}_daughter_slots"
            slots_raw = row.get(slots_key)
            if slots_raw is None:
                slots = DAUGHTERS_PER_BIPOLAR_DIVISION * divisions
                if multipolar:
                    raise LineageError(
                        "declared multipolar divisions require declared daughter slots"
                    )
            else:
                slots = _nonnegative_integer(slots_raw, slots_key)
                if slots < DAUGHTERS_PER_BIPOLAR_DIVISION * divisions + multipolar:
                    raise LineageError(
                        f"event_{sign}_daughter_slots cannot be fewer than two per division"
                    )
                if slots > (
                    DAUGHTERS_PER_BIPOLAR_DIVISION * divisions
                    + 2 * multipolar
                ):
                    raise LineageError(
                        f"event_{sign}_daughter_slots exceed the multipolar bound"
                    )
                if sign == "negative" and slots > DAUGHTERS_PER_BIPOLAR_DIVISION * divisions:
                    raise LineageError(
                        "clean divisions cannot produce more than two daughters"
                    )
            if followed > slots:
                raise LineageError(
                    f"event_{sign}_daughters_followed exceeds the declared daughter slots"
                )
            if reproduced + died > followed:
                raise LineageError(
                    f"event_{sign} reproduced/died daughters exceed followed"
                )
        row_key = (row["arm"], event_id, clone_id, run_id)
        if row_key in seen_rows:
            raise LineageError(
                "duplicate lineage-count row for one arm/event/clone/run"
            )
        seen_rows.add(row_key)
        mapped.append(
            ObservedRun(
                arm=row["arm"],
                edit_event_id=event_id,
                clone_id=clone_id,
                run_id=run_id,
                opportunities=_nonnegative_integer(row["opportunities"], "opportunities"),
                detected_divisions=_nonnegative_integer(
                    row["detected_divisions"], "detected_divisions"
                ),
                event_positive_divisions=_nonnegative_integer(
                    row["event_positive_divisions"], "event_positive_divisions"
                ),
                event_negative_divisions=_nonnegative_integer(
                    row["event_negative_divisions"], "event_negative_divisions"
                ),
                event_positive_daughters_followed=_nonnegative_integer(
                    row["event_positive_daughters_followed"],
                    "event_positive_daughters_followed",
                ),
                event_positive_daughters_reproduced=_nonnegative_integer(
                    row["event_positive_daughters_reproduced"],
                    "event_positive_daughters_reproduced",
                ),
                event_positive_daughters_died=_nonnegative_integer(
                    row["event_positive_daughters_died"],
                    "event_positive_daughters_died",
                ),
                event_negative_daughters_followed=_nonnegative_integer(
                    row["event_negative_daughters_followed"],
                    "event_negative_daughters_followed",
                ),
                event_negative_daughters_reproduced=_nonnegative_integer(
                    row["event_negative_daughters_reproduced"],
                    "event_negative_daughters_reproduced",
                ),
                event_negative_daughters_died=_nonnegative_integer(
                    row["event_negative_daughters_died"],
                    "event_negative_daughters_died",
                ),
                event_positive_daughter_slots=row.get(
                    "event_positive_daughter_slots"
                ),
                event_negative_daughter_slots=row.get(
                    "event_negative_daughter_slots"
                ),
                event_positive_multipolar_divisions=row.get(
                    "event_positive_multipolar_divisions"
                ),
                pre_division_death=_nonnegative_integer(
                    row.get("pre_division_death", 0), "pre_division_death"
                ),
                no_division=_nonnegative_integer(
                    row.get("no_division", 0), "no_division"
                ),
                dropout_censored=_nonnegative_integer(
                    row.get("dropout_censored", 0), "dropout_censored"
                ),
            )
        )
    return tuple(mapped)


FINGERPRINT_KEYS = (
    "arm",
    "edit_event_id",
    "clone_id",
    "run_id",
    "batch_id",
    "functional_execution_id",
    "exposure_support_record_id",
    "exposure_profile_id",
    "exposure_probe_id",
    "exposure_started_at",
    "endpoint_recorded_at",
    "allocation_block_id",
    "functional_assay_plate_id",
    "plate_row",
    "plate_column",
    "dosing_order",
    "acquisition_order",
    "opportunities",
    "detected_divisions",
    "event_positive_divisions",
    "event_negative_divisions",
    "event_positive_daughters_followed",
    "event_positive_daughters_reproduced",
    "event_positive_daughters_died",
    "event_positive_daughter_slots",
    "event_positive_multipolar_divisions",
    "event_negative_daughters_followed",
    "event_negative_daughters_reproduced",
    "event_negative_daughters_died",
    "event_negative_daughter_slots",
    "pre_division_death",
    "no_division",
    "dropout_censored",
)


def lineage_source_fingerprint(export: Mapping[str, Any]) -> str:
    """Canonical digest of study context and every lineage-count field used."""

    if not isinstance(export, Mapping) or export.get("schema") != "mva-track2-lineage-counts/v1":
        raise LineageError("fingerprint accepts lineage-count exports only")
    runs = export.get("runs")
    if not isinstance(runs, list) or not runs:
        raise LineageError("lineage-count export has no runs")
    allocation_present = "allocation_id" in export
    allocation_id = (
        _allocation_identifier(export.get("allocation_id"))
        if allocation_present
        else None
    )
    normalized_rows = []
    for row in runs:
        if not isinstance(row, Mapping):
            raise LineageError("count row must be an object")
        realized_present = [field in row for field in ALLOCATION_REALIZATION_FIELDS]
        if allocation_present and not all(realized_present):
            raise LineageError(
                "allocated lineage rows require every realized allocation field"
            )
        if not allocation_present and any(realized_present):
            raise LineageError(
                "realized allocation fields require a root allocation_id"
            )
        if allocation_present:
            _allocation_context_identifier(
                row.get("allocation_block_id"), "allocation_block_id"
            )
            _allocation_context_identifier(
                row.get("functional_assay_plate_id"),
                "functional_assay_plate_id",
            )
            for field in (
                "plate_row",
                "plate_column",
                "dosing_order",
                "acquisition_order",
            ):
                _positive_integer(row.get(field), field)
        normalized = {key: row.get(key) for key in FINGERPRINT_KEYS}
        normalized_rows.append(normalized)
    normalized_rows.sort(
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        , allow_nan=False)
    )
    payload = {
        "schema": "mva-track2-lineage-source-fingerprint/v3",
        "source": {
            "lineage_schema": export.get("schema"),
            "study_id": export.get("study_id"),
            "synthetic_only": export.get("synthetic_only"),
            "lock_state": export.get("lock_state"),
            "blinded": export.get("blinded"),
            "allocation_id": allocation_id,
        },
        "runs": normalized_rows,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def simulate_noisy_clean_generation(seed: int, *, noise: float = 0.02) -> LineageStudy:
    """Deterministic count jitter around the clean-generation fixture."""

    rng = StableRng(seed)
    per_event: dict[str, dict[str, dict[str, int]]] = {}
    for index in (1, 2, 3):
        vehicle_error = 8 if rng.random() > noise else 7
        treatment_error = 2 if rng.random() > noise else 3
        per_event[f"syn-event-{index}"] = {
            "vehicle": balanced_event_counts(
                completed_error=vehicle_error, completed_no_error=36 - vehicle_error
            ),
            "treatment": balanced_event_counts(
                completed_error=treatment_error, completed_no_error=36 - treatment_error
            ),
        }
    return lineage_study_from_counts(
        study_id=f"syn-noisy-clean-{seed}",
        per_event=per_event,
    )


__all__ = [
    "ADVERSARIAL_CASES",
    "ARM_NAMES",
    "CLAIM_BOUNDARY",
    "CompletionBand",
    "DAUGHTER_OUTCOMES",
    "Daughter",
    "ESTIMANDS",
    "FIRST_ATTEMPT_OUTCOMES",
    "FORBIDDEN_ANALYST_KEYS",
    "Founder",
    "LineageError",
    "LineageStudy",
    "SCHEMA",
    "analyze_lineage_study",
    "balanced_event_counts",
    "build_adversarial_fixture",
    "default_completion_band",
    "evaluate_fixture",
    "export_first_attempt_aggregates",
    "lineage_source_fingerprint",
    "lineage_study_from_counts",
    "load_lineage_study",
    "map_lineage_counts_to_observed_runs",
    "parse_lineage_study",
    "run_adversarial_suite",
    "simulate_noisy_clean_generation",
]
