"""Truth-blind aggregate-count benchmark for generation-versus-selection studies.

The v3 generator produces paired run-level sufficient statistics at an explicit
edit-event/clone/run hierarchy. The analyst receives only those observed
counts and observed calibration/audit counts. Generator parameters and
realized latent truth remain in an evaluator-only object.

This is a synthetic software and study-design stress test. It is not a
timestamped lineage model, a competing-risk analysis, or evidence of efficacy.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import platform
import re
import subprocess
from pathlib import Path
from typing import Any


SCHEMA = "mva-generation-selection-benchmark/v3"
ARM_NAMES = ("vehicle", "treatment")
BIOLOGICAL_FLAGS = (
    "generation_reduction",
    "error_daughter_pruning",
    "error_daughter_preservation",
    "cytostasis",
    "general_toxicity",
)
MEASUREMENT_FLAGS = (
    "event_detection_bias",
    "event_specificity_bias",
    "division_detection_bias",
    "informative_followup_bias",
)
COMPONENT_FLAGS = (*BIOLOGICAL_FLAGS, *MEASUREMENT_FLAGS)
ESTIMANDS = (
    "generation_rate",
    "founder_error_bearing_completion",
    "relative_error_daughter_reproduction",
    "division_completion",
    "nonerror_daughter_death",
)
GATE_PROFILES = ("required", "power_curve", "fail_closed")


class GenerationSelectionError(ValueError):
    """Raised when a benchmark contract or observed study is malformed."""


def _probability(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenerationSelectionError(f"{field} must be a finite probability")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise GenerationSelectionError(f"{field} must be between zero and one")
    return result


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenerationSelectionError(f"{field} must be positive and finite")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise GenerationSelectionError(f"{field} must be positive and finite")
    return result


def _nonnegative_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenerationSelectionError(f"{field} must be non-negative and finite")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise GenerationSelectionError(f"{field} must be non-negative and finite")
    return result


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GenerationSelectionError(f"{field} must be a positive integer")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GenerationSelectionError(f"{field} must be a non-negative integer")
    return value


def _strict_object(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise GenerationSelectionError(f"{label} has missing or surplus fields")
    return value


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise GenerationSelectionError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise GenerationSelectionError(f"non-finite JSON number {value}")


def _logit(value: float) -> float:
    bounded = min(1.0 - 1e-12, max(1e-12, value))
    return math.log(bounded / (1.0 - bounded))


def _expit(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


class StableRng:
    """Small version-stable PRNG used only for deterministic synthetic data."""

    _MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise GenerationSelectionError("seed must be a non-negative integer")
        self._state = (seed + 0x9E3779B97F4A7C15) & self._MASK
        if self._state == 0:
            self._state = 0xA5A5A5A5A5A5A5A5

    def _next_u64(self) -> int:
        value = self._state
        value ^= value >> 12
        value ^= (value << 25) & self._MASK
        value ^= value >> 27
        self._state = value & self._MASK
        return (self._state * 0x2545F4914F6CDD1D) & self._MASK

    def random(self) -> float:
        return (self._next_u64() >> 11) * (1.0 / (1 << 53))

    def normal(self, standard_deviation: float) -> float:
        if standard_deviation == 0.0:
            return 0.0
        first = max(self.random(), 1e-15)
        second = self.random()
        standard = math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)
        return standard * standard_deviation


def _binomial(count: int, probability: float, rng: StableRng) -> int:
    if count <= 0 or probability <= 0.0:
        return 0
    if probability >= 1.0:
        return count
    if probability > 0.5:
        return count - _binomial(count, 1.0 - probability, rng)
    complement = 1.0 - probability
    mode = min(count, math.floor((count + 1) * probability))
    log_probability_mass = (
        math.lgamma(count + 1)
        - math.lgamma(mode + 1)
        - math.lgamma(count - mode + 1)
        + mode * math.log(probability)
        + (count - mode) * math.log(complement)
    )
    mode_mass = math.exp(log_probability_mass)
    draw = rng.random()
    cumulative = mode_mass
    if draw < cumulative:
        return mode
    left = mode
    right = mode
    left_mass = mode_mass
    right_mass = mode_mass
    while left > 0 or right < count:
        if left > 0:
            left_mass *= left / (count - left + 1) * complement / probability
            left -= 1
            cumulative += left_mass
            if draw < cumulative:
                return left
        if right < count:
            right_mass *= (count - right) / (right + 1) * probability / complement
            right += 1
            cumulative += right_mass
            if draw < cumulative:
                return right
    return right


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
            probability * (1.0 - probability) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return (max(0.0, center - half), min(1.0, center + half))


@dataclasses.dataclass(frozen=True)
class StudyDesign:
    edit_events: int
    clones_per_edit_event: int
    runs_per_clone: int
    observation_opportunities_per_run: int
    shared_event_reference_errors: int
    shared_event_reference_nonerrors: int
    shared_division_reference_events: int
    arm_event_audit_errors: int
    arm_event_audit_nonerrors: int
    arm_division_audit_events: int

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            object.__setattr__(
                self,
                field.name,
                _positive_integer(getattr(self, field.name), field.name),
            )
        if self.edit_events < 3:
            raise GenerationSelectionError("at least three edit events are required")

    @property
    def clone_count(self) -> int:
        return self.edit_events * self.clones_per_edit_event

    @property
    def planned_opportunities_per_arm(self) -> int:
        return (
            self.clone_count
            * self.runs_per_clone
            * self.observation_opportunities_per_run
        )


@dataclasses.dataclass(frozen=True)
class Heterogeneity:
    edit_event_sd: float
    clone_sd: float
    run_sd: float
    arm_well_sd: float
    edit_treatment_sd: float
    clone_treatment_sd: float

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            object.__setattr__(
                self,
                field.name,
                _nonnegative_number(getattr(self, field.name), field.name),
            )


@dataclasses.dataclass(frozen=True)
class ArmParameters:
    division_probability: float
    new_error_probability: float
    error_daughter_reproduction_probability: float
    nonerror_daughter_reproduction_probability: float
    error_daughter_death_probability: float
    nonerror_daughter_death_probability: float

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            object.__setattr__(
                self,
                field.name,
                _probability(getattr(self, field.name), field.name),
            )
        for prefix in ("error", "nonerror"):
            reproduced = getattr(self, f"{prefix}_daughter_reproduction_probability")
            died = getattr(self, f"{prefix}_daughter_death_probability")
            if reproduced + died >= 1.0:
                raise GenerationSelectionError(
                    f"{prefix} daughter reproduction plus death must be below one"
                )


@dataclasses.dataclass(frozen=True)
class MeasurementParameters:
    division_detection_probability: float
    error_event_sensitivity: float
    error_event_specificity: float
    followup_if_reproduced: float
    followup_if_died: float
    followup_if_other: float

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            object.__setattr__(
                self,
                field.name,
                _probability(getattr(self, field.name), field.name),
            )
        if self.error_event_sensitivity + self.error_event_specificity <= 1.0:
            raise GenerationSelectionError("event observation must outperform chance")


@dataclasses.dataclass(frozen=True)
class AnalysisThresholds:
    generation_reduction_ratio: float
    selection_reduction_ratio: float
    selection_increase_ratio: float
    division_reduction_ratio: float
    division_equivalence_lower_ratio: float
    division_equivalence_upper_ratio: float
    toxicity_increase_ratio: float
    event_detection_bias_ratio: float
    event_false_positive_increase_ratio: float
    division_detection_bias_ratio: float
    followup_bias_ratio: float
    minimum_calibration_youden: float
    minimum_detected_divisions_per_edit_event: int
    minimum_event_positive_followed_per_edit_event: int
    minimum_event_negative_followed_per_edit_event: int
    minimum_posterior_separation: float
    confidence_multiplier: float

    def __post_init__(self) -> None:
        probability_fields = (
            "generation_reduction_ratio",
            "selection_reduction_ratio",
            "division_reduction_ratio",
            "division_equivalence_lower_ratio",
            "event_detection_bias_ratio",
            "division_detection_bias_ratio",
            "followup_bias_ratio",
            "minimum_calibration_youden",
            "minimum_posterior_separation",
        )
        for name in probability_fields:
            object.__setattr__(self, name, _probability(getattr(self, name), name))
        for name in (
            "generation_reduction_ratio",
            "selection_reduction_ratio",
            "division_reduction_ratio",
            "event_detection_bias_ratio",
            "division_detection_bias_ratio",
            "followup_bias_ratio",
        ):
            if getattr(self, name) >= 1.0:
                raise GenerationSelectionError(f"{name} must be below one")
        object.__setattr__(
            self,
            "division_equivalence_upper_ratio",
            _positive_number(
                self.division_equivalence_upper_ratio,
                "division_equivalence_upper_ratio",
            ),
        )
        if self.division_equivalence_upper_ratio <= 1.0:
            raise GenerationSelectionError(
                "division_equivalence_upper_ratio must exceed one"
            )
        if self.division_equivalence_lower_ratio >= 1.0:
            raise GenerationSelectionError(
                "division_equivalence_lower_ratio must be below one"
            )
        for name in ("selection_increase_ratio", "toxicity_increase_ratio"):
            object.__setattr__(self, name, _positive_number(getattr(self, name), name))
            if getattr(self, name) <= 1.0:
                raise GenerationSelectionError(f"{name} must exceed one")
        object.__setattr__(
            self,
            "event_false_positive_increase_ratio",
            _positive_number(
                self.event_false_positive_increase_ratio,
                "event_false_positive_increase_ratio",
            ),
        )
        if self.event_false_positive_increase_ratio <= 1.0:
            raise GenerationSelectionError(
                "event_false_positive_increase_ratio must exceed one"
            )
        for name in (
            "minimum_detected_divisions_per_edit_event",
            "minimum_event_positive_followed_per_edit_event",
            "minimum_event_negative_followed_per_edit_event",
        ):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        object.__setattr__(
            self,
            "confidence_multiplier",
            _positive_number(self.confidence_multiplier, "confidence_multiplier"),
        )


@dataclasses.dataclass(frozen=True)
class SharedCalibrationCounts:
    reference_errors: int
    detected_reference_errors: int
    reference_nonerrors: int
    false_positive_reference_nonerrors: int
    reference_divisions: int
    detected_reference_divisions: int

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            object.__setattr__(
                self,
                field.name,
                _nonnegative_integer(getattr(self, field.name), field.name),
            )
        if self.reference_errors < 1 or self.reference_nonerrors < 1:
            raise GenerationSelectionError("event calibration denominators must be positive")
        if self.reference_divisions < 1:
            raise GenerationSelectionError("division calibration denominator must be positive")
        if self.detected_reference_errors > self.reference_errors:
            raise GenerationSelectionError("detected reference errors exceed denominator")
        if self.false_positive_reference_nonerrors > self.reference_nonerrors:
            raise GenerationSelectionError("false positives exceed denominator")
        if self.detected_reference_divisions > self.reference_divisions:
            raise GenerationSelectionError("detected divisions exceed denominator")

    @property
    def sensitivity(self) -> float:
        return (self.detected_reference_errors + 0.5) / (self.reference_errors + 1.0)

    @property
    def specificity(self) -> float:
        true_negatives = self.reference_nonerrors - self.false_positive_reference_nonerrors
        return (true_negatives + 0.5) / (self.reference_nonerrors + 1.0)

    @property
    def division_detection(self) -> float:
        return (self.detected_reference_divisions + 0.5) / (
            self.reference_divisions + 1.0
        )


@dataclasses.dataclass(frozen=True)
class ArmAuditCounts:
    reference_errors: int
    detected_reference_errors: int
    reference_nonerrors: int
    false_positive_reference_nonerrors: int
    reference_divisions: int
    detected_reference_divisions: int

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            object.__setattr__(
                self,
                field.name,
                _nonnegative_integer(getattr(self, field.name), field.name),
            )
        if (
            self.reference_errors < 1
            or self.reference_nonerrors < 1
            or self.reference_divisions < 1
        ):
            raise GenerationSelectionError("arm audit denominators must be positive")
        if self.detected_reference_errors > self.reference_errors:
            raise GenerationSelectionError("arm event audit exceeds denominator")
        if self.detected_reference_divisions > self.reference_divisions:
            raise GenerationSelectionError("arm division audit exceeds denominator")
        if self.false_positive_reference_nonerrors > self.reference_nonerrors:
            raise GenerationSelectionError("arm specificity audit exceeds denominator")

    @property
    def event_sensitivity(self) -> float:
        return (self.detected_reference_errors + 0.5) / (self.reference_errors + 1.0)

    @property
    def event_specificity(self) -> float:
        true_negatives = self.reference_nonerrors - self.false_positive_reference_nonerrors
        return (true_negatives + 0.5) / (self.reference_nonerrors + 1.0)

    @property
    def event_false_positive_rate(self) -> float:
        return (self.false_positive_reference_nonerrors + 0.5) / (
            self.reference_nonerrors + 1.0
        )

    @property
    def division_detection(self) -> float:
        return (self.detected_reference_divisions + 0.5) / (
            self.reference_divisions + 1.0
        )


@dataclasses.dataclass(frozen=True)
class ObservedRun:
    arm: str
    edit_event_id: int
    clone_id: int
    run_id: int
    opportunities: int
    detected_divisions: int
    event_positive_divisions: int
    event_negative_divisions: int
    event_positive_daughters_followed: int
    event_positive_daughters_reproduced: int
    event_positive_daughters_died: int
    event_negative_daughters_followed: int
    event_negative_daughters_reproduced: int
    event_negative_daughters_died: int

    def __post_init__(self) -> None:
        if self.arm not in ARM_NAMES:
            raise GenerationSelectionError("unsupported arm")
        for name in ("edit_event_id", "clone_id", "run_id", "opportunities"):
            _positive_integer(getattr(self, name), name)
        for name in (
            "detected_divisions",
            "event_positive_divisions",
            "event_negative_divisions",
            "event_positive_daughters_followed",
            "event_positive_daughters_reproduced",
            "event_positive_daughters_died",
            "event_negative_daughters_followed",
            "event_negative_daughters_reproduced",
            "event_negative_daughters_died",
        ):
            _nonnegative_integer(getattr(self, name), name)
        if self.event_positive_divisions + self.event_negative_divisions != self.detected_divisions:
            raise GenerationSelectionError("event labels must partition detected divisions")
        if self.detected_divisions > self.opportunities:
            raise GenerationSelectionError("detected divisions exceed opportunities")
        for label in ("positive", "negative"):
            divisions = getattr(self, f"event_{label}_divisions")
            followed = getattr(self, f"event_{label}_daughters_followed")
            reproduced = getattr(self, f"event_{label}_daughters_reproduced")
            died = getattr(self, f"event_{label}_daughters_died")
            if followed > 2 * divisions:
                raise GenerationSelectionError("followed daughters exceed generated daughters")
            if reproduced + died > followed:
                raise GenerationSelectionError("daughter outcomes are not mutually exclusive")


@dataclasses.dataclass(frozen=True)
class ObservedAggregateStudy:
    runs: tuple[ObservedRun, ...]
    shared_calibration: SharedCalibrationCounts
    arm_audits: dict[str, ArmAuditCounts]

    def __post_init__(self) -> None:
        if not self.runs:
            raise GenerationSelectionError("observed study must contain runs")
        if set(self.arm_audits) != set(ARM_NAMES):
            raise GenerationSelectionError("observed study requires both arm audits")


@dataclasses.dataclass(frozen=True)
class RealizedTruth:
    ratios: dict[str, float]


@dataclasses.dataclass(frozen=True)
class SimulatedAggregateStudy:
    observed: ObservedAggregateStudy
    truth: RealizedTruth


@dataclasses.dataclass(frozen=True)
class RatioEstimate:
    estimable: bool
    ratio: float | None
    lower: float | None
    upper: float | None
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _dataclass_from_dict(cls: type[Any], value: object, label: str) -> Any:
    fields = {field.name for field in dataclasses.fields(cls)}
    return cls(**_strict_object(value, fields, label))


def _draw_effects(rng: StableRng, standard_deviation: float) -> dict[str, float]:
    return {
        field.name: rng.normal(standard_deviation)
        for field in dataclasses.fields(ArmParameters)
    }


def _realize_parameters(
    *,
    base: ArmParameters,
    vehicle: ArmParameters,
    is_treatment: bool,
    event_effects: dict[str, float],
    clone_effects: dict[str, float],
    run_effects: dict[str, float],
    well_effects: dict[str, float],
    event_treatment_effects: dict[str, float],
    clone_treatment_effects: dict[str, float],
) -> ArmParameters:
    values: dict[str, float] = {}
    for field in dataclasses.fields(ArmParameters):
        name = field.name
        value = _logit(getattr(base, name))
        value += event_effects[name] + clone_effects[name] + run_effects[name]
        value += well_effects[name]
        if is_treatment and getattr(base, name) != getattr(vehicle, name):
            value += event_treatment_effects[name] + clone_treatment_effects[name]
        values[name] = _expit(value)
    for prefix in ("error", "nonerror"):
        reproduction_name = f"{prefix}_daughter_reproduction_probability"
        death_name = f"{prefix}_daughter_death_probability"
        total = values[reproduction_name] + values[death_name]
        if total >= 0.98:
            scale = 0.98 / total
            values[reproduction_name] *= scale
            values[death_name] *= scale
    return ArmParameters(**values)


def _daughter_outcomes(
    count: int,
    reproduction_probability: float,
    death_probability: float,
    measurement: MeasurementParameters,
    rng: StableRng,
) -> tuple[int, int, int]:
    reproduced = _binomial(count, reproduction_probability, rng)
    remaining = count - reproduced
    conditional_death = (
        death_probability / (1.0 - reproduction_probability)
        if remaining > 0
        else 0.0
    )
    died = _binomial(remaining, conditional_death, rng)
    other = remaining - died
    followed_reproduced = _binomial(reproduced, measurement.followup_if_reproduced, rng)
    followed_died = _binomial(died, measurement.followup_if_died, rng)
    followed_other = _binomial(other, measurement.followup_if_other, rng)
    return (
        followed_reproduced + followed_died + followed_other,
        followed_reproduced,
        followed_died,
    )


def _combine_outcomes(*values: tuple[int, int, int]) -> tuple[int, int, int]:
    combined = tuple(sum(value[index] for value in values) for index in range(3))
    return (combined[0], combined[1], combined[2])


def _simulate_shared_calibration(
    design: StudyDesign,
    measurement: MeasurementParameters,
    rng: StableRng,
) -> SharedCalibrationCounts:
    return SharedCalibrationCounts(
        reference_errors=design.shared_event_reference_errors,
        detected_reference_errors=_binomial(
            design.shared_event_reference_errors,
            measurement.error_event_sensitivity,
            rng,
        ),
        reference_nonerrors=design.shared_event_reference_nonerrors,
        false_positive_reference_nonerrors=_binomial(
            design.shared_event_reference_nonerrors,
            1.0 - measurement.error_event_specificity,
            rng,
        ),
        reference_divisions=design.shared_division_reference_events,
        detected_reference_divisions=_binomial(
            design.shared_division_reference_events,
            measurement.division_detection_probability,
            rng,
        ),
    )


def _simulate_arm_audit(
    design: StudyDesign,
    measurement: MeasurementParameters,
    rng: StableRng,
) -> ArmAuditCounts:
    return ArmAuditCounts(
        reference_errors=design.arm_event_audit_errors,
        detected_reference_errors=_binomial(
            design.arm_event_audit_errors,
            measurement.error_event_sensitivity,
            rng,
        ),
        reference_nonerrors=design.arm_event_audit_nonerrors,
        false_positive_reference_nonerrors=_binomial(
            design.arm_event_audit_nonerrors,
            1.0 - measurement.error_event_specificity,
            rng,
        ),
        reference_divisions=design.arm_division_audit_events,
        detected_reference_divisions=_binomial(
            design.arm_division_audit_events,
            measurement.division_detection_probability,
            rng,
        ),
    )


def simulate_aggregate_study(
    *,
    design: StudyDesign,
    heterogeneity: Heterogeneity,
    vehicle: ArmParameters,
    treatment: ArmParameters,
    shared_measurement: MeasurementParameters,
    vehicle_measurement: MeasurementParameters,
    treatment_measurement: MeasurementParameters,
    seed: int,
    shared_calibration_counts: SharedCalibrationCounts | None = None,
) -> SimulatedAggregateStudy:
    """Generate observed aggregate counts plus evaluator-only realized truth."""

    rng = StableRng(seed)
    runs: list[ObservedRun] = []
    truth_accumulator = {
        event: {
            arm: {
                "opportunities": 0.0,
                "expected_divisions": 0.0,
                "expected_errors": 0.0,
                "error_reproduction": 0.0,
                "nonerror_reproduction": 0.0,
                "nonerror_death": 0.0,
            }
            for arm in ARM_NAMES
        }
        for event in range(1, design.edit_events + 1)
    }
    clone_counter = 0
    for event_id in range(1, design.edit_events + 1):
        event_effects = _draw_effects(rng, heterogeneity.edit_event_sd)
        event_treatment_effects = _draw_effects(rng, heterogeneity.edit_treatment_sd)
        for _clone_within_event in range(design.clones_per_edit_event):
            clone_counter += 1
            clone_effects = _draw_effects(rng, heterogeneity.clone_sd)
            clone_treatment_effects = _draw_effects(rng, heterogeneity.clone_treatment_sd)
            for run_id in range(1, design.runs_per_clone + 1):
                run_effects = _draw_effects(rng, heterogeneity.run_sd)
                for arm, base, measurement in (
                    ("vehicle", vehicle, vehicle_measurement),
                    ("treatment", treatment, treatment_measurement),
                ):
                    adjusted = _realize_parameters(
                        base=base,
                        vehicle=vehicle,
                        is_treatment=arm == "treatment",
                        event_effects=event_effects,
                        clone_effects=clone_effects,
                        run_effects=run_effects,
                        well_effects=_draw_effects(rng, heterogeneity.arm_well_sd),
                        event_treatment_effects=event_treatment_effects,
                        clone_treatment_effects=clone_treatment_effects,
                    )
                    opportunities = design.observation_opportunities_per_run
                    latent_divisions = _binomial(
                        opportunities, adjusted.division_probability, rng
                    )
                    true_errors = _binomial(
                        latent_divisions, adjusted.new_error_probability, rng
                    )
                    detected_true_errors = _binomial(
                        true_errors, measurement.division_detection_probability, rng
                    )
                    detected_true_nonerrors = _binomial(
                        latent_divisions - true_errors,
                        measurement.division_detection_probability,
                        rng,
                    )
                    positive_true = _binomial(
                        detected_true_errors, measurement.error_event_sensitivity, rng
                    )
                    positive_false = _binomial(
                        detected_true_nonerrors,
                        1.0 - measurement.error_event_specificity,
                        rng,
                    )
                    negative_true = detected_true_errors - positive_true
                    negative_true_nonerror = detected_true_nonerrors - positive_false

                    positive_outcomes = _combine_outcomes(
                        _daughter_outcomes(
                            2 * positive_true,
                            adjusted.error_daughter_reproduction_probability,
                            adjusted.error_daughter_death_probability,
                            measurement,
                            rng,
                        ),
                        _daughter_outcomes(
                            2 * positive_false,
                            adjusted.nonerror_daughter_reproduction_probability,
                            adjusted.nonerror_daughter_death_probability,
                            measurement,
                            rng,
                        ),
                    )
                    negative_outcomes = _combine_outcomes(
                        _daughter_outcomes(
                            2 * negative_true,
                            adjusted.error_daughter_reproduction_probability,
                            adjusted.error_daughter_death_probability,
                            measurement,
                            rng,
                        ),
                        _daughter_outcomes(
                            2 * negative_true_nonerror,
                            adjusted.nonerror_daughter_reproduction_probability,
                            adjusted.nonerror_daughter_death_probability,
                            measurement,
                            rng,
                        ),
                    )
                    detected_divisions = detected_true_errors + detected_true_nonerrors
                    runs.append(
                        ObservedRun(
                            arm=arm,
                            edit_event_id=event_id,
                            clone_id=clone_counter,
                            run_id=run_id,
                            opportunities=opportunities,
                            detected_divisions=detected_divisions,
                            event_positive_divisions=positive_true + positive_false,
                            event_negative_divisions=negative_true + negative_true_nonerror,
                            event_positive_daughters_followed=positive_outcomes[0],
                            event_positive_daughters_reproduced=positive_outcomes[1],
                            event_positive_daughters_died=positive_outcomes[2],
                            event_negative_daughters_followed=negative_outcomes[0],
                            event_negative_daughters_reproduced=negative_outcomes[1],
                            event_negative_daughters_died=negative_outcomes[2],
                        )
                    )

                    truth = truth_accumulator[event_id][arm]
                    expected_divisions = opportunities * adjusted.division_probability
                    expected_errors = expected_divisions * adjusted.new_error_probability
                    expected_nonerrors = expected_divisions - expected_errors
                    truth["opportunities"] += opportunities
                    truth["expected_divisions"] += expected_divisions
                    truth["expected_errors"] += expected_errors
                    truth["error_reproduction"] += (
                        expected_errors * adjusted.error_daughter_reproduction_probability
                    )
                    truth["nonerror_reproduction"] += (
                        expected_nonerrors * adjusted.nonerror_daughter_reproduction_probability
                    )
                    truth["nonerror_death"] += (
                        expected_nonerrors * adjusted.nonerror_daughter_death_probability
                    )

    event_truth: dict[str, list[float]] = {name: [] for name in ESTIMANDS}
    for event_id in range(1, design.edit_events + 1):
        arm_values: dict[str, dict[str, float]] = {}
        for arm in ARM_NAMES:
            row = truth_accumulator[event_id][arm]
            expected_divisions = row["expected_divisions"]
            expected_errors = row["expected_errors"]
            expected_nonerrors = expected_divisions - expected_errors
            arm_values[arm] = {
                "generation": expected_errors / expected_divisions,
                "division": expected_divisions / row["opportunities"],
                "error_reproduction": row["error_reproduction"] / expected_errors,
                "nonerror_reproduction": row["nonerror_reproduction"] / expected_nonerrors,
                "nonerror_death": row["nonerror_death"] / expected_nonerrors,
            }
        event_truth["generation_rate"].append(
            arm_values["treatment"]["generation"]
            / arm_values["vehicle"]["generation"]
        )
        treatment_founder_error = (
            truth_accumulator[event_id]["treatment"]["expected_errors"]
            / truth_accumulator[event_id]["treatment"]["opportunities"]
        )
        vehicle_founder_error = (
            truth_accumulator[event_id]["vehicle"]["expected_errors"]
            / truth_accumulator[event_id]["vehicle"]["opportunities"]
        )
        event_truth["founder_error_bearing_completion"].append(
            treatment_founder_error / vehicle_founder_error
        )
        treatment_selection = (
            arm_values["treatment"]["error_reproduction"]
            / arm_values["treatment"]["nonerror_reproduction"]
        )
        vehicle_selection = (
            arm_values["vehicle"]["error_reproduction"]
            / arm_values["vehicle"]["nonerror_reproduction"]
        )
        event_truth["relative_error_daughter_reproduction"].append(
            treatment_selection / vehicle_selection
        )
        event_truth["division_completion"].append(
            arm_values["treatment"]["division"]
            / arm_values["vehicle"]["division"]
        )
        event_truth["nonerror_daughter_death"].append(
            arm_values["treatment"]["nonerror_death"]
            / arm_values["vehicle"]["nonerror_death"]
        )
    realized_ratios = {
        name: math.exp(sum(math.log(value) for value in values) / len(values))
        for name, values in event_truth.items()
    }
    observed = ObservedAggregateStudy(
        runs=tuple(runs),
        shared_calibration=(
            shared_calibration_counts
            if shared_calibration_counts is not None
            else _simulate_shared_calibration(design, shared_measurement, rng)
        ),
        arm_audits={
            "vehicle": _simulate_arm_audit(design, vehicle_measurement, rng),
            "treatment": _simulate_arm_audit(design, treatment_measurement, rng),
        },
    )
    return SimulatedAggregateStudy(observed, RealizedTruth(realized_ratios))


def _empty_counts() -> dict[str, int]:
    return {
        "opportunities": 0,
        "divisions": 0,
        "positive_divisions": 0,
        "negative_divisions": 0,
        "positive_followed": 0,
        "positive_reproduced": 0,
        "positive_died": 0,
        "negative_followed": 0,
        "negative_reproduced": 0,
        "negative_died": 0,
    }


def _event_counts(
    study: ObservedAggregateStudy, design: StudyDesign
) -> dict[int, dict[str, dict[str, int]]]:
    result = {
        event: {arm: _empty_counts() for arm in ARM_NAMES}
        for event in range(1, design.edit_events + 1)
    }
    seen: set[tuple[str, int, int, int]] = set()
    for run in study.runs:
        if not 1 <= run.edit_event_id <= design.edit_events:
            raise GenerationSelectionError("run has unsupported edit event")
        key = (run.arm, run.edit_event_id, run.clone_id, run.run_id)
        if key in seen:
            raise GenerationSelectionError("duplicate observed run")
        seen.add(key)
        row = result[run.edit_event_id][run.arm]
        row["opportunities"] += run.opportunities
        row["divisions"] += run.detected_divisions
        row["positive_divisions"] += run.event_positive_divisions
        row["negative_divisions"] += run.event_negative_divisions
        row["positive_followed"] += run.event_positive_daughters_followed
        row["positive_reproduced"] += run.event_positive_daughters_reproduced
        row["positive_died"] += run.event_positive_daughters_died
        row["negative_followed"] += run.event_negative_daughters_followed
        row["negative_reproduced"] += run.event_negative_daughters_reproduced
        row["negative_died"] += run.event_negative_daughters_died
    expected_runs = design.edit_events * design.clones_per_edit_event * design.runs_per_clone
    for arm in ARM_NAMES:
        if sum(1 for key in seen if key[0] == arm) != expected_runs:
            raise GenerationSelectionError("observed study has missing or surplus runs")
    return result


def _correct_event_rate(
    positive: int,
    total: int,
    sensitivity: float,
    specificity: float,
) -> tuple[float | None, str | None]:
    if total <= 0:
        return (None, "no detected divisions")
    denominator = sensitivity + specificity - 1.0
    if denominator <= 0.0:
        return (None, "event calibration does not identify truth")
    corrected = (positive / total + specificity - 1.0) / denominator
    if not 0.0 < corrected < 1.0:
        return (None, "corrected event rate is on or beyond a probability boundary")
    return (corrected, None)


def _solve_latent_outcomes(
    *,
    generation_rate: float,
    sensitivity: float,
    specificity: float,
    positive_followed: int,
    positive_successes: int,
    negative_followed: int,
    negative_successes: int,
    minimum_positive_followed: int,
    minimum_negative_followed: int,
    minimum_separation: float,
) -> tuple[float | None, float | None, str | None]:
    if positive_followed < minimum_positive_followed:
        return (None, None, "too few followed event-positive daughters")
    if negative_followed < minimum_negative_followed:
        return (None, None, "too few followed event-negative daughters")
    positive_probability = (
        generation_rate * sensitivity
        + (1.0 - generation_rate) * (1.0 - specificity)
    )
    negative_probability = (
        generation_rate * (1.0 - sensitivity)
        + (1.0 - generation_rate) * specificity
    )
    if positive_probability <= 0.0 or negative_probability <= 0.0:
        return (None, None, "event-label posterior is undefined")
    posterior_positive = generation_rate * sensitivity / positive_probability
    posterior_negative = generation_rate * (1.0 - sensitivity) / negative_probability
    separation = posterior_positive - posterior_negative
    if separation < minimum_separation:
        return (None, None, "event-label posterior separation is inadequate")
    observed_positive = positive_successes / positive_followed
    observed_negative = negative_successes / negative_followed
    true_error = (
        observed_positive * (1.0 - posterior_negative)
        - observed_negative * (1.0 - posterior_positive)
    ) / separation
    true_nonerror = (
        observed_negative * posterior_positive
        - observed_positive * posterior_negative
    ) / separation
    if not 0.0 < true_error < 1.0 or not 0.0 < true_nonerror < 1.0:
        return (None, None, "latent outcome solution is on a probability boundary")
    return (true_error, true_nonerror, None)


def _ratio_estimate(
    vehicle_values: list[float | None],
    treatment_values: list[float | None],
    confidence_multiplier: float,
    reason: str | None = None,
) -> RatioEstimate:
    if reason is not None:
        return RatioEstimate(False, None, None, None, reason)
    if len(vehicle_values) != len(treatment_values):
        raise GenerationSelectionError("paired event vectors must have equal length")
    if len(vehicle_values) < 3 or any(
        value is None for value in (*vehicle_values, *treatment_values)
    ):
        return RatioEstimate(
            False, None, None, None, "fewer than three estimable edit events"
        )
    log_ratios = [
        math.log(float(treatment) / float(vehicle))
        for vehicle, treatment in zip(vehicle_values, treatment_values, strict=True)
    ]
    mean_log = sum(log_ratios) / len(log_ratios)
    variance = sum((value - mean_log) ** 2 for value in log_ratios) / (
        len(log_ratios) - 1
    )
    half_width = confidence_multiplier * math.sqrt(variance / len(log_ratios))
    return RatioEstimate(
        True,
        math.exp(mean_log),
        math.exp(mean_log - half_width),
        math.exp(mean_log + half_width),
        None,
    )


def analyze_observed_study(
    study: ObservedAggregateStudy,
    *,
    design: StudyDesign,
    thresholds: AnalysisThresholds,
) -> dict[str, Any]:
    """Analyze observed aggregates and observed calibration counts only."""

    calibration = study.shared_calibration
    sensitivity = calibration.sensitivity
    specificity = calibration.specificity
    division_detection = calibration.division_detection
    calibration_reason = None
    if sensitivity + specificity - 1.0 < thresholds.minimum_calibration_youden:
        calibration_reason = "shared event calibration is too weak"
    counts = _event_counts(study, design)
    rates = {
        event: {
            arm: {
                "generation": None,
                "founder_error": None,
                "division": None,
                "error_reproduction": None,
                "nonerror_reproduction": None,
                "nonerror_death": None,
                "followup": None,
                "reasons": [],
            }
            for arm in ARM_NAMES
        }
        for event in range(1, design.edit_events + 1)
    }
    for event in range(1, design.edit_events + 1):
        for arm in ARM_NAMES:
            row = counts[event][arm]
            target = rates[event][arm]
            sufficient_divisions = (
                row["divisions"]
                >= thresholds.minimum_detected_divisions_per_edit_event
            )
            if not sufficient_divisions:
                target["reasons"].append("too few detected divisions")
            generation, generation_reason = _correct_event_rate(
                row["positive_divisions"],
                row["divisions"],
                sensitivity,
                specificity,
            )
            if generation_reason is not None:
                target["reasons"].append(generation_reason)
            elif sufficient_divisions and calibration_reason is None:
                target["generation"] = generation
            corrected_division = (
                row["divisions"] / row["opportunities"] / division_detection
                if row["opportunities"] > 0 and division_detection > 0.0
                else None
            )
            if (
                not sufficient_divisions
                or corrected_division is None
                or not 0.0 < corrected_division < 1.0
            ):
                target["reasons"].append("division completion is not estimable")
            else:
                target["division"] = corrected_division
            if target["generation"] is not None and target["division"] is not None:
                target["founder_error"] = (
                    float(target["generation"]) * float(target["division"])
                )
            total_daughters = 2 * row["divisions"]
            target["followup"] = (
                (row["positive_followed"] + row["negative_followed"])
                / total_daughters
                if total_daughters > 0
                else None
            )
            if target["generation"] is not None:
                error_reproduction, nonerror_reproduction, reproduction_reason = (
                    _solve_latent_outcomes(
                        generation_rate=generation,
                        sensitivity=sensitivity,
                        specificity=specificity,
                        positive_followed=row["positive_followed"],
                        positive_successes=row["positive_reproduced"],
                        negative_followed=row["negative_followed"],
                        negative_successes=row["negative_reproduced"],
                        minimum_positive_followed=(
                            thresholds.minimum_event_positive_followed_per_edit_event
                        ),
                        minimum_negative_followed=(
                            thresholds.minimum_event_negative_followed_per_edit_event
                        ),
                        minimum_separation=thresholds.minimum_posterior_separation,
                    )
                )
                if reproduction_reason is not None:
                    target["reasons"].append(reproduction_reason)
                else:
                    target["error_reproduction"] = error_reproduction
                    target["nonerror_reproduction"] = nonerror_reproduction
                _error_death, nonerror_death, death_reason = _solve_latent_outcomes(
                    generation_rate=generation,
                    sensitivity=sensitivity,
                    specificity=specificity,
                    positive_followed=row["positive_followed"],
                    positive_successes=row["positive_died"],
                    negative_followed=row["negative_followed"],
                    negative_successes=row["negative_died"],
                    minimum_positive_followed=(
                        thresholds.minimum_event_positive_followed_per_edit_event
                    ),
                    minimum_negative_followed=(
                        thresholds.minimum_event_negative_followed_per_edit_event
                    ),
                    minimum_separation=thresholds.minimum_posterior_separation,
                )
                if death_reason is not None:
                    target["reasons"].append(death_reason)
                else:
                    target["nonerror_death"] = nonerror_death

    generation = _ratio_estimate(
        [rates[event]["vehicle"]["generation"] for event in rates],
        [rates[event]["treatment"]["generation"] for event in rates],
        thresholds.confidence_multiplier,
        calibration_reason,
    )
    division = _ratio_estimate(
        [rates[event]["vehicle"]["division"] for event in rates],
        [rates[event]["treatment"]["division"] for event in rates],
        thresholds.confidence_multiplier,
    )
    founder_error = _ratio_estimate(
        [rates[event]["vehicle"]["founder_error"] for event in rates],
        [rates[event]["treatment"]["founder_error"] for event in rates],
        thresholds.confidence_multiplier,
        calibration_reason,
    )
    death = _ratio_estimate(
        [rates[event]["vehicle"]["nonerror_death"] for event in rates],
        [rates[event]["treatment"]["nonerror_death"] for event in rates],
        thresholds.confidence_multiplier,
    )
    vehicle_selection: list[float | None] = []
    treatment_selection: list[float | None] = []
    for event in rates:
        for arm, target in (
            ("vehicle", vehicle_selection),
            ("treatment", treatment_selection),
        ):
            error_value = rates[event][arm]["error_reproduction"]
            nonerror_value = rates[event][arm]["nonerror_reproduction"]
            target.append(
                error_value / nonerror_value
                if error_value is not None and nonerror_value is not None
                else None
            )
    selection = _ratio_estimate(
        vehicle_selection,
        treatment_selection,
        thresholds.confidence_multiplier,
    )
    followup = _ratio_estimate(
        [rates[event]["vehicle"]["followup"] for event in rates],
        [rates[event]["treatment"]["followup"] for event in rates],
        thresholds.confidence_multiplier,
    )
    estimates = {
        "generation_rate": generation,
        "founder_error_bearing_completion": founder_error,
        "relative_error_daughter_reproduction": selection,
        "division_completion": division,
        "nonerror_daughter_death": death,
        "daughter_followup": followup,
    }

    vehicle_audit = study.arm_audits["vehicle"]
    treatment_audit = study.arm_audits["treatment"]
    event_audit_ratio = treatment_audit.event_sensitivity / vehicle_audit.event_sensitivity
    _vehicle_fpr_lower, vehicle_fpr_upper = _wilson(
        vehicle_audit.false_positive_reference_nonerrors,
        vehicle_audit.reference_nonerrors,
    )
    treatment_fpr_lower, _treatment_fpr_upper = _wilson(
        treatment_audit.false_positive_reference_nonerrors,
        treatment_audit.reference_nonerrors,
    )
    division_audit_ratio = (
        treatment_audit.division_detection / vehicle_audit.division_detection
    )
    measurement_flags = {
        "event_detection_bias": (
            event_audit_ratio <= thresholds.event_detection_bias_ratio
        ),
        "event_specificity_bias": (
            treatment_fpr_lower
            >= thresholds.event_false_positive_increase_ratio
            * vehicle_fpr_upper
        ),
        "division_detection_bias": (
            division_audit_ratio <= thresholds.division_detection_bias_ratio
        ),
        "informative_followup_bias": (
            followup.estimable
            and followup.ratio is not None
            and followup.ratio <= thresholds.followup_bias_ratio
            and followup.upper is not None
            and followup.upper < 1.0
        ),
    }
    measurement_invalid = any(measurement_flags.values())

    def reduced(estimate: RatioEstimate, cutoff: float) -> bool:
        return bool(
            estimate.estimable
            and estimate.ratio is not None
            and estimate.upper is not None
            and estimate.ratio <= cutoff
            and estimate.upper < 1.0
        )

    def increased(estimate: RatioEstimate, cutoff: float) -> bool:
        return bool(
            estimate.estimable
            and estimate.ratio is not None
            and estimate.lower is not None
            and estimate.ratio >= cutoff
            and estimate.lower > 1.0
        )

    conditional_generation_reduction = reduced(
        generation, thresholds.generation_reduction_ratio
    )
    founder_error_reduction = reduced(
        founder_error, thresholds.generation_reduction_ratio
    )
    biological_flags = {
        "generation_reduction": (
            conditional_generation_reduction and founder_error_reduction
        ),
        "error_daughter_pruning": reduced(
            selection, thresholds.selection_reduction_ratio
        ),
        "error_daughter_preservation": increased(
            selection, thresholds.selection_increase_ratio
        ),
        "cytostasis": reduced(division, thresholds.division_reduction_ratio),
        "general_toxicity": increased(death, thresholds.toxicity_increase_ratio),
    }
    if measurement_invalid:
        biological_flags = {name: False for name in BIOLOGICAL_FLAGS}
        conditional_generation_reduction = False
        founder_error_reduction = False
        estimates = {
            name: (
                RatioEstimate(
                    False,
                    None,
                    None,
                    None,
                    "arm-specific measurement QC failed",
                )
                if name in ESTIMANDS
                else estimate
            )
            for name, estimate in estimates.items()
        }
    all_core_estimable = all(estimates[name].estimable for name in ESTIMANDS)
    if not all_core_estimable:
        biological_flags = {name: False for name in BIOLOGICAL_FLAGS}
        conditional_generation_reduction = False
        founder_error_reduction = False
    flags = {**biological_flags, **measurement_flags}
    division_equivalent = bool(
        not measurement_invalid
        and division.estimable
        and division.lower is not None
        and division.upper is not None
        and division.lower >= thresholds.division_equivalence_lower_ratio
        and division.upper <= thresholds.division_equivalence_upper_ratio
    )
    adverse_biology = any(
        biological_flags[name]
        for name in BIOLOGICAL_FLAGS
        if name != "generation_reduction"
    )
    clean_generation_signal = bool(
        biological_flags["generation_reduction"]
        and all_core_estimable
        and division_equivalent
        and not adverse_biology
    )
    if measurement_invalid:
        interpretation = "measurement_invalid"
    elif biological_flags["generation_reduction"] and not all_core_estimable:
        interpretation = "generation_signal_incomplete_deconvolution"
    elif biological_flags["generation_reduction"] and not division_equivalent:
        interpretation = "generation_signal_with_unresolved_competing_completion"
    elif clean_generation_signal:
        interpretation = "generation_reduction_without_detected_configured_confound"
    elif any(biological_flags.values()):
        interpretation = "mixed_components"
    elif not all_core_estimable:
        interpretation = "insufficient_information"
    else:
        interpretation = "no_detectable_component"
    return {
        "estimates": {name: estimate.as_dict() for name, estimate in estimates.items()},
        "estimability": {
            name: {
                "estimable": estimates[name].estimable,
                "reason": estimates[name].reason,
            }
            for name in ESTIMANDS
        },
        "status": {
            "measurement_valid": not measurement_invalid,
            "all_core_estimable": all_core_estimable,
            "division_completion_equivalent": division_equivalent,
            "clean_generation_signal": clean_generation_signal,
            "conditional_generation_reduction": conditional_generation_reduction,
            "founder_error_bearing_completion_reduction": founder_error_reduction,
            "primary_generation_concordant": (
                conditional_generation_reduction and founder_error_reduction
            ),
            "primary_cohort_outcome_model": (
                "fixed cohort; first attempt is no-completion/death, "
                "completed-no-error, or completed-error"
            ),
            "primary_cohort_boundary": (
                "pre-division death is not separable from other non-completion"
            ),
        },
        "flags": flags,
        "interpretation": interpretation,
        "calibration": {
            "shared_event_sensitivity": sensitivity,
            "shared_event_specificity": specificity,
            "shared_division_detection": division_detection,
            "vehicle_event_audit_sensitivity": vehicle_audit.event_sensitivity,
            "treatment_event_audit_sensitivity": treatment_audit.event_sensitivity,
            "vehicle_event_audit_specificity": vehicle_audit.event_specificity,
            "treatment_event_audit_specificity": treatment_audit.event_specificity,
            "vehicle_division_audit_detection": vehicle_audit.division_detection,
            "treatment_division_audit_detection": treatment_audit.division_detection,
        },
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonicalize_floats(value: Any) -> Any:
    if isinstance(value, float):
        return float(format(value, ".12g"))
    if isinstance(value, list):
        return [_canonicalize_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalize_floats(item) for key, item in value.items()}
    return value


def _git_receipt(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        tracked_status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {"git_source_commit": None, "git_tracked_worktree_clean": False}
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        return {"git_source_commit": None, "git_tracked_worktree_clean": False}
    return {
        "git_source_commit": commit,
        "git_tracked_worktree_clean": not tracked_status.strip(),
    }


def runtime_receipt(config_path: Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    receipt: dict[str, Any] = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "canonical_command": (
            "python scripts/run_generation_selection_benchmark.py --config "
            "configs/track2-generation-selection-benchmark.json --output <new-path>"
        ),
        "source_sha256": _sha256(Path(__file__).resolve()),
        "runner_sha256": _sha256(root / "scripts" / "run_generation_selection_benchmark.py"),
        "test_sha256": _sha256(root / "tests" / "test_generation_selection.py"),
        **_git_receipt(root),
    }
    if config_path is not None:
        receipt["config_sha256"] = _sha256(config_path.resolve())
    return receipt


def _rate_summary(successes: int, total: int) -> dict[str, Any]:
    lower, upper = _wilson(successes, total)
    return {
        "successes": successes,
        "total": total,
        "rate": successes / total if total else None,
        "wilson_lower": lower,
        "wilson_upper": upper,
    }


def run_benchmark(config: dict[str, Any]) -> dict[str, Any]:
    root = _strict_object(
        config,
        {
            "schema",
            "seed",
            "monte_carlo_replicates",
            "design",
            "heterogeneity",
            "vehicle",
            "shared_measurement",
            "vehicle_measurement",
            "thresholds",
            "acceptance",
            "scenarios",
        },
        "config",
    )
    if root["schema"] != SCHEMA:
        raise GenerationSelectionError("unsupported benchmark schema")
    seed = _nonnegative_integer(root["seed"], "seed")
    replicates = _positive_integer(
        root["monte_carlo_replicates"], "monte_carlo_replicates"
    )
    design = _dataclass_from_dict(StudyDesign, root["design"], "design")
    heterogeneity = _dataclass_from_dict(
        Heterogeneity, root["heterogeneity"], "heterogeneity"
    )
    vehicle = _dataclass_from_dict(ArmParameters, root["vehicle"], "vehicle")
    shared_measurement = _dataclass_from_dict(
        MeasurementParameters, root["shared_measurement"], "shared_measurement"
    )
    vehicle_measurement = _dataclass_from_dict(
        MeasurementParameters, root["vehicle_measurement"], "vehicle_measurement"
    )
    thresholds = _dataclass_from_dict(
        AnalysisThresholds, root["thresholds"], "thresholds"
    )
    acceptance = _strict_object(
        root["acceptance"],
        {
            "minimum_component_sensitivity_wilson_lower",
            "minimum_component_specificity_wilson_lower",
            "minimum_expected_flag_set_wilson_lower",
            "minimum_interval_coverage_wilson_lower",
            "maximum_absolute_log_ratio_bias",
            "minimum_generation_detection_wilson_lower",
            "maximum_false_generation_wilson_upper",
            "maximum_invalid_fraction_wilson_upper",
        },
        "acceptance",
    )
    minimum_sensitivity = _probability(
        acceptance["minimum_component_sensitivity_wilson_lower"],
        "minimum_component_sensitivity_wilson_lower",
    )
    minimum_specificity = _probability(
        acceptance["minimum_component_specificity_wilson_lower"],
        "minimum_component_specificity_wilson_lower",
    )
    minimum_flag_set = _probability(
        acceptance["minimum_expected_flag_set_wilson_lower"],
        "minimum_expected_flag_set_wilson_lower",
    )
    minimum_coverage = _probability(
        acceptance["minimum_interval_coverage_wilson_lower"],
        "minimum_interval_coverage_wilson_lower",
    )
    maximum_bias = _positive_number(
        acceptance["maximum_absolute_log_ratio_bias"],
        "maximum_absolute_log_ratio_bias",
    )
    minimum_generation = _probability(
        acceptance["minimum_generation_detection_wilson_lower"],
        "minimum_generation_detection_wilson_lower",
    )
    maximum_false_generation = _probability(
        acceptance["maximum_false_generation_wilson_upper"],
        "maximum_false_generation_wilson_upper",
    )
    maximum_invalid = _probability(
        acceptance["maximum_invalid_fraction_wilson_upper"],
        "maximum_invalid_fraction_wilson_upper",
    )

    raw_scenarios = root["scenarios"]
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise GenerationSelectionError("scenarios must be a non-empty list")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_scenario in enumerate(raw_scenarios, start=1):
        scenario = _strict_object(
            raw_scenario,
            {"name", "gate", "treatment", "treatment_measurement", "expected_flags"},
            f"scenario {index}",
        )
        name = scenario["name"]
        if not isinstance(name, str) or not name or name in seen:
            raise GenerationSelectionError("scenario names must be unique non-empty strings")
        seen.add(name)
        gate = scenario["gate"]
        if gate not in GATE_PROFILES:
            raise GenerationSelectionError(
                "scenario gate must be required, power_curve, or fail_closed"
            )
        expected_raw = scenario["expected_flags"]
        if (
            not isinstance(expected_raw, list)
            or any(not isinstance(flag, str) for flag in expected_raw)
            or len(expected_raw) != len(set(expected_raw))
            or not set(expected_raw) <= set(COMPONENT_FLAGS)
        ):
            raise GenerationSelectionError("expected_flags must be unique supported strings")
        parsed.append(
            {
                "name": name,
                "gate": gate,
                "treatment": _dataclass_from_dict(
                    ArmParameters, scenario["treatment"], f"scenario {index} treatment"
                ),
                "treatment_measurement": _dataclass_from_dict(
                    MeasurementParameters,
                    scenario["treatment_measurement"],
                    f"scenario {index} treatment_measurement",
                ),
                "expected_flags": set(expected_raw),
            }
        )
    required_generation = [
        scenario
        for scenario in parsed
        if scenario["gate"] == "required"
        and "generation_reduction" in scenario["expected_flags"]
    ]
    required_confound = [
        scenario
        for scenario in parsed
        if scenario["gate"] == "required"
        and "generation_reduction" not in scenario["expected_flags"]
    ]
    if not required_generation or not required_confound:
        raise GenerationSelectionError(
            "at least one required G and one required non-G scenario are required"
        )

    rows: list[dict[str, Any]] = []
    shared_calibrations = [
        _simulate_shared_calibration(
            design,
            shared_measurement,
            StableRng(seed + 900_000_000 + replicate),
        )
        for replicate in range(replicates)
    ]
    for index, scenario in enumerate(parsed, start=1):
        flag_counts = {flag: 0 for flag in COMPONENT_FLAGS}
        exact_flag_sets = 0
        measurement_invalid_count = 0
        fail_closed_count = 0
        estimable_counts = {name: 0 for name in ESTIMANDS}
        coverage_counts = {name: 0 for name in ESTIMANDS}
        log_error_sums = {name: 0.0 for name in ESTIMANDS}
        truth_log_sums = {name: 0.0 for name in ESTIMANDS}
        representative: dict[str, Any] | None = None
        for replicate in range(replicates):
            replicate_seed = seed + index * 10_000_000 + replicate
            simulation = simulate_aggregate_study(
                design=design,
                heterogeneity=heterogeneity,
                vehicle=vehicle,
                treatment=scenario["treatment"],
                shared_measurement=shared_measurement,
                vehicle_measurement=vehicle_measurement,
                treatment_measurement=scenario["treatment_measurement"],
                seed=replicate_seed,
                shared_calibration_counts=shared_calibrations[replicate],
            )
            analysis = analyze_observed_study(
                simulation.observed, design=design, thresholds=thresholds
            )
            if representative is None:
                representative = analysis
            observed_flags = {
                flag for flag, enabled in analysis["flags"].items() if enabled
            }
            measurement_invalid_count += not analysis["status"]["measurement_valid"]
            fail_closed_count += (
                analysis["status"]["measurement_valid"]
                and not analysis["status"]["all_core_estimable"]
                and not any(
                    analysis["flags"][flag] for flag in BIOLOGICAL_FLAGS
                )
                and analysis["interpretation"] == "insufficient_information"
            )
            exact_flag_sets += observed_flags == scenario["expected_flags"]
            for flag in COMPONENT_FLAGS:
                flag_counts[flag] += bool(analysis["flags"][flag])
            for estimand in ESTIMANDS:
                truth = simulation.truth.ratios[estimand]
                truth_log_sums[estimand] += math.log(truth)
                estimate = analysis["estimates"][estimand]
                if not estimate["estimable"]:
                    continue
                estimable_counts[estimand] += 1
                ratio = float(estimate["ratio"])
                coverage_counts[estimand] += (
                    float(estimate["lower"]) <= truth <= float(estimate["upper"])
                )
                log_error_sums[estimand] += math.log(ratio / truth)

        flag_summaries = {
            flag: _rate_summary(flag_counts[flag], replicates)
            for flag in COMPONENT_FLAGS
        }
        exact_summary = _rate_summary(exact_flag_sets, replicates)
        measurement_invalid_summary = _rate_summary(
            measurement_invalid_count, replicates
        )
        fail_closed_summary = _rate_summary(fail_closed_count, replicates)
        estimand_summaries: dict[str, Any] = {}
        for estimand in ESTIMANDS:
            valid = estimable_counts[estimand]
            invalid = replicates - valid
            coverage_summary = _rate_summary(coverage_counts[estimand], valid)
            invalid_summary = _rate_summary(invalid, replicates)
            estimand_summaries[estimand] = {
                "valid_replicates": valid,
                "invalid_fraction": invalid_summary["rate"],
                "invalid_fraction_wilson_upper": invalid_summary["wilson_upper"],
                "interval_coverage": coverage_summary["rate"],
                "coverage_wilson_lower": coverage_summary["wilson_lower"],
                "coverage_wilson_upper": coverage_summary["wilson_upper"],
                "absolute_log_ratio_bias": (
                    abs(log_error_sums[estimand] / valid) if valid else None
                ),
                "mean_realized_truth_ratio": math.exp(
                    truth_log_sums[estimand] / replicates
                ),
            }
        expected_pass = all(
            flag_summaries[flag]["wilson_lower"] >= minimum_sensitivity
            for flag in scenario["expected_flags"]
        )
        absent_pass = all(
            flag_summaries[flag]["wilson_upper"] <= 1.0 - minimum_specificity
            for flag in set(COMPONENT_FLAGS) - scenario["expected_flags"]
        )
        expects_measurement_failure = bool(
            scenario["expected_flags"] & set(MEASUREMENT_FLAGS)
        )
        if expects_measurement_failure:
            method_pass = (
                measurement_invalid_summary["wilson_lower"] >= minimum_sensitivity
            )
        else:
            method_pass = all(
                summary["valid_replicates"] > 0
                and summary["coverage_wilson_lower"] >= minimum_coverage
                and summary["invalid_fraction_wilson_upper"] <= maximum_invalid
                and summary["absolute_log_ratio_bias"] is not None
                and summary["absolute_log_ratio_bias"] <= maximum_bias
                for summary in estimand_summaries.values()
            )
        false_generation_pass = (
            "generation_reduction" in scenario["expected_flags"]
            or flag_summaries["generation_reduction"]["wilson_upper"]
            <= maximum_false_generation
        )
        if scenario["gate"] == "required":
            passed = (
                expected_pass
                and absent_pass
                and exact_summary["wilson_lower"] >= minimum_flag_set
                and method_pass
                and false_generation_pass
            )
        elif scenario["gate"] == "fail_closed":
            passed = (
                fail_closed_summary["wilson_lower"] >= minimum_sensitivity
                and measurement_invalid_summary["wilson_upper"]
                <= 1.0 - minimum_specificity
            )
        else:
            passed = method_pass
        rows.append(
            {
                "name": scenario["name"],
                "gate": scenario["gate"],
                "expected_flags": sorted(scenario["expected_flags"]),
                "component_detection": flag_summaries,
                "exact_expected_flag_set": exact_summary,
                "measurement_invalid": measurement_invalid_summary,
                "fail_closed_insufficient_information": fail_closed_summary,
                "estimands": estimand_summaries,
                "false_generation_wilson_upper": (
                    None
                    if "generation_reduction" in scenario["expected_flags"]
                    else flag_summaries["generation_reduction"]["wilson_upper"]
                ),
                "representative_observed_analysis": representative,
                "passed": passed,
            }
        )

    required_rows = [row for row in rows if row["gate"] == "required"]
    required_generation_rows = [
        row
        for row in required_rows
        if "generation_reduction" in row["expected_flags"]
    ]
    required_confound_rows = [
        row
        for row in required_rows
        if "generation_reduction" not in row["expected_flags"]
    ]
    minimum_generation_lower = min(
        row["component_detection"]["generation_reduction"]["wilson_lower"]
        for row in required_generation_rows
    )
    maximum_confound_upper = max(
        row["component_detection"]["generation_reduction"]["wilson_upper"]
        for row in required_confound_rows
    )
    all_passed = all(row["passed"] for row in rows)
    acceptance_passed = (
        all_passed
        and minimum_generation_lower >= minimum_generation
        and maximum_confound_upper <= maximum_false_generation
    )
    power_curve = [
        {
            "name": row["name"],
            "mean_realized_generation_ratio": row["estimands"]["generation_rate"][
                "mean_realized_truth_ratio"
            ],
            "generation_detection_rate": row["component_detection"][
                "generation_reduction"
            ]["rate"],
            "generation_detection_wilson_lower": row["component_detection"][
                "generation_reduction"
            ]["wilson_lower"],
            "generation_detection_wilson_upper": row["component_detection"][
                "generation_reduction"
            ]["wilson_upper"],
        }
        for row in rows
        if row["gate"] == "power_curve"
    ]
    power_curve.sort(key=lambda row: row["mean_realized_generation_ratio"])
    return _canonicalize_floats(
        {
            "schema": SCHEMA,
            "seed": seed,
            "synthetic_only": True,
            "claim_boundary": (
                "Paired fixed-cohort first-attempt aggregate-count stress test only; "
                "pre-division death is inseparable from other non-completion, later "
                "daughter outcomes are secondary, and this is not a timestamped "
                "lineage model, biological validation, or efficacy evidence."
            ),
            "design": {
                **dataclasses.asdict(design),
                "clone_count_per_arm": design.clone_count,
                "planned_observation_opportunities_per_arm": (
                    design.planned_opportunities_per_arm
                ),
                "highest_inferential_unit": "edit_event",
                "primary_estimands": [
                    "conditional error per completed first division",
                    "error-bearing completed first division per enrolled founder",
                ],
                "interval_method": (
                    "paired edit-event log-ratio interval with predeclared "
                    "small-sample multiplier"
                ),
            },
            "heterogeneity": dataclasses.asdict(heterogeneity),
            "calibration_design": {
                "shared_panel_role": (
                    "one reusable external truth-labeled panel sampled once per "
                    "synthetic study and used for both-arm correction; it is not "
                    "regenerated per arm or comparison"
                ),
                "truth_establishment": (
                    "reference labels are assumed established independently of "
                    "treatment assignment and blinded to the benchmark analyst"
                ),
                "arm_drift_audits": (
                    "separate blinded arm-specific positive, negative, and division "
                    "checks trigger fail-closed QC and are not used to recalibrate"
                ),
            },
            "unmodeled_measurement_boundaries": [
                (
                    "daughter reproduced/died/other label misclassification is not "
                    "generated, corrected, or audited; those labels are assumed "
                    "adjudicated in this benchmark"
                ),
                (
                    "outcome-dependent missingness engineered to preserve identical "
                    "arm-level marginal follow-up is not identifiable from these "
                    "aggregate sufficient statistics"
                ),
            ],
            "monte_carlo_replicates_per_scenario": replicates,
            "total_simulated_vehicle_treatment_comparisons": replicates * len(rows),
            "thresholds": dataclasses.asdict(thresholds),
            "acceptance": dict(acceptance),
            "scenarios": rows,
            "local_alternative_power_curve": power_curve,
            "summary": {
                "passed": sum(bool(row["passed"]) for row in rows),
                "total": len(rows),
                "all_passed": all_passed,
                "minimum_required_generation_detection_wilson_lower": (
                    minimum_generation_lower
                ),
                "maximum_false_generation_wilson_upper_per_required_confound": (
                    maximum_confound_upper
                ),
                "acceptance_passed": acceptance_passed,
            },
        }
    )


def load_and_run_benchmark(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationSelectionError(f"cannot read benchmark config: {exc}") from exc
    if not isinstance(config, dict):
        raise GenerationSelectionError("benchmark config root must be an object")
    result = run_benchmark(config)
    result["runtime_receipt"] = runtime_receipt(path)
    return result


__all__ = [
    "ARM_NAMES",
    "BIOLOGICAL_FLAGS",
    "COMPONENT_FLAGS",
    "ESTIMANDS",
    "MEASUREMENT_FLAGS",
    "SCHEMA",
    "AnalysisThresholds",
    "ArmAuditCounts",
    "ArmParameters",
    "GenerationSelectionError",
    "Heterogeneity",
    "MeasurementParameters",
    "ObservedAggregateStudy",
    "ObservedRun",
    "RatioEstimate",
    "SharedCalibrationCounts",
    "SimulatedAggregateStudy",
    "StableRng",
    "StudyDesign",
    "analyze_observed_study",
    "load_and_run_benchmark",
    "run_benchmark",
    "runtime_receipt",
    "simulate_aggregate_study",
]
