"""Public aggregate arithmetic, with assumed culture exposure kept explicit.

No child, brain, intracellular, efficacy, dose or advancement model is fitted.
The historical exposure gate is deliberately not called or changed.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def fraction(value: object, label: str) -> float:
    number = positive(value, label)
    if number > 1:
        raise ValueError(f"{label} must be no greater than one")
    return number


def mass_auc_to_molar(value: object, unit: str, molecular_weight: object) -> float:
    """Convert the declared mass AUC to micromolar hours.

    One ug/mL is one mg/L, so multiply by 1000 / MW in g/mol.
    One ng/mL is one ug/L, so divide by MW. Reject undeclared units.
    """
    scale = {"ug*h/mL": 1000.0, "ng*h/mL": 1.0}.get(unit)
    if scale is None:
        raise ValueError("unsupported mass AUC unit")
    return positive(value, "mass AUC") * scale / positive(molecular_weight, "molecular weight")


def analyze_pba(data: Mapping[str, Any]) -> dict[str, Any]:
    if data.get("analyte") != "parent phenylbutyric acid":
        raise ValueError("PBA comparison requires the parent free-acid analyte")
    clinical_hours = positive(data.get("clinical_interval_hours"), "clinical interval")
    reference_hours = positive(data.get("culture_reference_hours"), "reference interval")
    if clinical_hours != reference_hours:
        raise ValueError("compare matching intervals; do not silently rescale daily summaries")
    nominal = positive(data.get("culture_nominal_uM"), "nominal culture reference")
    bound_range = data.get("external_plasma_bound_fraction_range")
    if not isinstance(bound_range, list) or len(bound_range) != 2:
        raise ValueError("binding requires an ordered two-value range")
    bound_low, bound_high = [fraction(v, "bound fraction") for v in bound_range]
    if bound_low > bound_high or bound_high >= 1:
        raise ValueError("binding range must be ordered and leave a nonzero free fraction")
    free_low, free_high = 1 - bound_high, 1 - bound_low
    medium_values = data.get("assumed_medium_free_fractions")
    if not isinstance(medium_values, list) or not medium_values:
        raise ValueError("declare medium-free-fraction assumptions")
    medium_fractions = [fraction(v, "medium free fraction") for v in medium_values]
    nominal_auc = nominal * reference_hours
    profiles = data.get("clinical_profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("clinical aggregate profiles required")
    rows = []
    for profile in profiles:
        if not isinstance(profile, Mapping) or not isinstance(profile.get("formulation"), str):
            raise ValueError("each aggregate profile needs a formulation")
        total = mass_auc_to_molar(profile.get("total_parent_auc"), data.get("clinical_auc_unit"), data.get("molecular_weight_g_mol"))
        illustrative_free = [total * free_low, total * free_high]
        rows.append({
            "formulation": profile["formulation"],
            "reported_total_parent_auc_mass": profile["total_parent_auc"],
            "total_parent_plasma_auc_uM_h": total,
            "total_parent_plasma_mean_uM": total / clinical_hours,
            "total_auc_over_assumed_nominal_reference": total / nominal_auc,
            "illustrative_fixed_fraction_free_plasma_auc_uM_h": illustrative_free,
            "assumed_medium_free_fraction_for_equal_integrals": [v / nominal_auc for v in illustrative_free],
            "medium_scenarios": [{
                "assumed_medium_free_fraction": f,
                "assumed_medium_free_auc_uM_h": nominal_auc * f,
                "illustrative_plasma_free_auc_over_assumed_medium_free_auc_range": [v / (nominal_auc * f) for v in illustrative_free],
            } for f in medium_fractions],
        })
    return {
        "clinical_source": data.get("clinical_source"),
        "clinical_context": data.get("clinical_context"),
        "compared_interval_hours": clinical_hours,
        "binding_source": data.get("binding_source"),
        "binding_boundary": data.get("binding_boundary"),
        "external_assumed_plasma_free_fraction_range": [free_low, free_high],
        "culture_source": data.get("culture_source"),
        "assumed_nominal_culture_reference_auc_uM_h": nominal_auc,
        "culture_reference_boundary": data.get("culture_reference_boundary"),
        "profiles": rows,
        "inference": "Interpret the numerical ratios only under the declared interval and binding assumptions. Neuronal exposure and efficacy remain unidentified. AUC equality cannot establish matching peaks, troughs, duration above a threshold or persistent biological response.",
    }


def analyze_peak_rectangle(data: Mapping[str, Any]) -> dict[str, Any]:
    if data.get("analyte") != "parent elamipretide":
        raise ValueError("elamipretide comparison requires its declared parent analyte")
    peak = positive(data.get("cmax_ng_ml"), "peak")
    observed_auc = positive(data.get("auc_tau_ng_h_ml"), "AUC")
    interval = positive(data.get("tau_hours"), "interval")
    rectangle = peak * interval
    if rectangle < observed_auc:
        raise ValueError("a matched peak-times-interval rectangle cannot be below the AUC")
    return {
        "source": data.get("source"), "context": data.get("context"),
        "reported_cmax_ng_ml": peak,
        "reported_auc_tau_ng_h_ml": observed_auc,
        "assumed_peak_held_for_interval_auc_ng_h_ml": rectangle,
        "peak_rectangle_over_reported_auc": rectangle / observed_auc,
        "boundary": data.get("boundary"),
    }


def analyze(inputs: Mapping[str, Any]) -> dict[str, Any]:
    if inputs.get("schema") != "mva.public-literature-exposure/v1":
        raise ValueError("unsupported public input schema")
    return {
        "schema": "mva.public-literature-exposure-result/v1",
        "claim_boundary": "Deterministic arithmetic on public aggregate observations plus explicitly assumed binding/culture scenarios. Not a fitted PK simulation, measured free exposure, neural delivery, efficacy ranking or clinical recommendation.",
        "pba": analyze_pba(inputs["pba"]),
        "elamipretide_peak_warning": analyze_peak_rectangle(inputs["elamipretide"]),
        "clinical_advancement_granted": False,
        "historical_gate_modified": False,
    }
