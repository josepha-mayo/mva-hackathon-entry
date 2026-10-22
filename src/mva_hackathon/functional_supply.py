"""Synthetic counterexamples for experiment design, never a biological fitter.

Two compartments separate protein entering a pre-assembly pool from protein
reaching a mature pool. Pool membership does not establish folding or function.
All example rates are invented; none is estimated from participant material.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math


def _number(value: float, name: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")


@dataclass(frozen=True)
class SupplyModel:
    """Rates per hour and an arbitrary abundance scale.

    input_rate is entry into the measured pool, not ribosomal initiation.
    dilution represents per-cell dilution; it is not biochemical destruction.
    activity is an illustrative independent functional weight, not a measured
    conversion from protein amount to spindle-checkpoint output.
    """

    input_rate: float
    maturation: float
    early_loss: float
    mature_loss: float
    dilution: float = 0.0
    activity: float = 1.0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            _number(value, name)
        if self.activity > 1:
            raise ValueError("activity must be at most one")
        if self.early_exit <= 0 or self.mature_exit <= 0:
            raise ValueError("both pool exit rates must be positive")

    @property
    def early_exit(self) -> float:
        return self.maturation + self.early_loss + self.dilution

    @property
    def mature_exit(self) -> float:
        return self.mature_loss + self.dilution

    def steady_state(self) -> tuple[float, float]:
        early = self.input_rate / self.early_exit
        return early, self.maturation * early / self.mature_exit

    def chase(self, hours: float, early: float, mature: float) -> tuple[float, float]:
        """Exact homogeneous solution for a labeled cohort with no new label.

        Unlabeled synthesis may continue. This does not simulate effects caused
        by translation inhibitors or labeling perturbations.
        """
        for name, value in (("hours", hours), ("early", early), ("mature", mature)):
            _number(value, name)
        a, b = self.early_exit, self.mature_exit
        ea, eb = math.exp(-a * hours), math.exp(-b * hours)
        # Stable convolution, including equal and nearly equal exit rates.
        gap = abs(a - b)
        convolution = hours * ea if gap == 0 else math.exp(-min(a, b) * hours) * (-math.expm1(-gap * hours)) / gap
        return early * ea, mature * eb + self.maturation * early * convolution

    def new_label(self, hours: float) -> tuple[float, float]:
        """Ideal step-label accumulation with constant input and perfect recovery."""
        steady = self.steady_state()
        old = self.chase(hours, *steady)
        return tuple(max(0.0, s - o) for s, o in zip(steady, old))

    def pulse_cohort(self, pulse_hours: float, chase_hours: float) -> tuple[float, float]:
        """A finite pulse includes ages zero through pulse_hours, not one age."""
        return self.chase(chase_hours, *self.new_label(pulse_hours))


def demonstration() -> dict:
    """Return deterministic, explicitly synthetic non-identifiability witnesses."""
    models = {
        "reference": SupplyModel(1, 1, 0, 0.1),
        "early_loss": SupplyModel(1, 1, 9, 0.1),
        "low_input": SupplyModel(0.1, 1, 0, 0.1),
        "mature_loss": SupplyModel(1, 1, 0, 10),
        "inactive_mature_pool": SupplyModel(1, 1, 0, 0.1, activity=0.1),
    }
    times = (0, 0.25, 0.5, 1, 2, 4, 8)
    rows = {}
    for name, model in models.items():
        early, mature = model.steady_state()
        rows[name] = {
            "invented_parameters": asdict(model),
            "steady_early": early,
            "steady_mature": mature,
            "steady_total": early + mature,
            "illustrative_functional_supply": model.activity * mature,
            "ideal_new_label_total": [sum(model.new_label(t)) for t in times],
            "short_pulse_chase_total": [sum(model.pulse_cohort(0.25, t)) for t in times],
        }
    reference, inactive = rows["reference"], rows["inactive_mature_pool"]
    # At a fixed maturation/exit combination, scaling input and unknown assay
    # recovery reciprocally makes the entire measured labeling curve identical.
    high_input = SupplyModel(2, 1, 0, 0.1)
    scaled_recovery = [0.5 * sum(high_input.new_label(t)) for t in times]
    # Equal one-hour changes in early loss, applied at different cohort ages.
    # This is a model perturbation, not a drug or exposure-response model.
    baseline = models["early_loss"]
    reduced_early_loss = SupplyModel(1, 1, 1, 0.1)
    untreated = baseline.chase(4, 1, 0)[1]
    early_window = baseline.chase(3, *reduced_early_loss.chase(1, 1, 0))[1]
    late_window = reduced_early_loss.chase(1, *baseline.chase(3, 1, 0))[1]
    checks = {
        "three_mechanisms_have_same_low_total": all(
            math.isclose(rows[name]["steady_total"], 1.1)
            for name in ("early_loss", "low_input", "mature_loss")
        ),
        "identical_turnover_does_not_identify_function": (
            reference["ideal_new_label_total"] == inactive["ideal_new_label_total"]
            and math.isclose(reference["illustrative_functional_supply"], 10 * inactive["illustrative_functional_supply"])
        ),
        "unknown_recovery_confounds_input": scaled_recovery == reference["ideal_new_label_total"],
        "ideal_timecourse_can_separate_selected_low_total_worlds": (
            rows["early_loss"]["ideal_new_label_total"] != rows["low_input"]["ideal_new_label_total"]
        ),
        "early_loss_perturbation_depends_on_cohort_age": (
            early_window > 3 * untreated
            and math.isclose(late_window, untreated, rel_tol=1e-9)
        ),
    }
    return {
        "schema": "mva.synthetic-functional-supply/v1",
        "scope": "invented counterexamples only; no fitting, patient evidence, drug ranking, or biological power",
        "times_hours": times,
        "pulse_hours": 0.25,
        "worlds": rows,
        "invented_timing_probe": {
            "initial_cohort": {"early": 1, "mature": 0},
            "readout_hours": 4,
            "perturbation": "early-loss rate reduced from nine to one for one hour; other rates fixed",
            "untreated_mature": untreated,
            "early_window_mature": early_window,
            "late_window_mature": late_window,
            "scope": "model timing counterexample only; no drug kinetics, pharmacodynamics or biological time window",
        },
        "checks": checks,
        "all_counterexamples_reproduced": all(checks.values()),
        "mechanism_identified_in_child": False,
    }
