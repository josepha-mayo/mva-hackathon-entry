"""Versioned, standalone missense-correction contrast contract.

This checks declared metadata and externally computed contrast intervals, not
raw observations, genotype authenticity, power, covariance, or clinical rescue.
It deliberately cannot produce legacy pipeline eligibility.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from mva_hackathon.provenance import semantic_digest, receipt_sha256

PLAN_SCHEMA = "mva.missense-correction-plan/v2"
EVIDENCE_SCHEMA = "mva.missense-correction-evidence/v2"
RESULT_SCHEMA = "mva.missense-correction-control/v2"
ENDPOINTS = ("abundance", "half_life", "localization", "checkpoint", "first_division_error")
SOURCE = ["NM_001211.6:c.2210T>G", "NM_001211.6:c.3006T>G"]
CARRIER = ["NM_001211.6:c.2210T>G", "NM_001211.6:WT"]


class CorrectionControlError(ValueError):
    """Input is missing, ambiguous, or outside this isolated contract."""


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CorrectionControlError(f"{name} must be an object")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CorrectionControlError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise CorrectionControlError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise CorrectionControlError(f"{name} must be finite")
    return number


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise CorrectionControlError(f"{name} must be nonempty text of at most 256 characters")
    return value


def _time(value: Any, name: str) -> datetime:
    try:
        result = datetime.fromisoformat(_text(value, name).replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError("timezone required")
        return result
    except ValueError as exc:
        raise CorrectionControlError(f"{name} must be a timezone-aware ISO timestamp") from exc


def _interval(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise CorrectionControlError(f"{name} must have exactly two bounds")
    lower, upper = (_number(x, name) for x in value)
    if lower > upper:
        raise CorrectionControlError(f"{name} bounds are reversed")
    return lower, upper


def _endpoints(value: Any, name: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != len(ENDPOINTS):
        raise CorrectionControlError(f"{name} requires all five endpoints exactly once")
    result = {}
    for row in value:
        item = _object(row, name)
        endpoint = item.get("endpoint")
        if not isinstance(endpoint, str) or endpoint not in ENDPOINTS or endpoint in result:
            raise CorrectionControlError(f"{name} has an unknown or duplicate endpoint")
        result[endpoint] = item
    return result


def _specimens(value: Any) -> Mapping[str, Any]:
    specimens = _object(value, "specimens")
    ids, events, backgrounds, protocols = [], [], [], []
    for role, genotype in (("mutant", SOURCE), ("corrected", CARRIER), ("comparator", CARRIER)):
        item = _object(specimens.get(role), role)
        if item.get("genotype") != genotype or item.get("phase") != "trans_confirmed":
            raise CorrectionControlError(f"{role} genotype/phase is not the required exact genotype")
        ids.append(_text(item.get("specimen_id"), "specimen_id"))
        events.append(_text(item.get("derivation_event_id"), "derivation_event_id"))
        backgrounds.append(_text(item.get("background_id"), "background_id"))
        protocols.append(_text(item.get("assay_protocol_id"), "assay_protocol_id"))
        _text(item.get("genotype_evidence_id"), "genotype_evidence_id")
    if len(set(ids)) != 3 or events[1] == events[2]:
        raise CorrectionControlError("independently generated comparator must not be the corrected specimen/event")
    if len(set(backgrounds)) != 1 or len(set(protocols)) != 1:
        raise CorrectionControlError("specimens must share background and assay protocol")
    return specimens


def assess_missense_correction_control(plan: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed on invalid contracts; hold on inconclusive/failed contrasts.

    Intervals are supplied by an external, prespecified joint contrast analysis.
    In particular no ratio CI is inferred by dividing independent marginal CIs.
    A digest is an integrity binding, never evidence of authentic preregistration.
    """
    plan, evidence = _object(plan, "plan"), _object(evidence, "evidence")
    if plan.get("schema") != PLAN_SCHEMA or evidence.get("schema") != EVIDENCE_SCHEMA:
        raise CorrectionControlError("explicit v2 plan and evidence required; v1 is legacy/unassessed")
    if plan.get("correction_scope") != "N1002K_only":
        raise CorrectionControlError("only exact N1002K-only correction is supported")
    specimens = _specimens(plan.get("specimens"))
    if evidence.get("specimens") != specimens:
        raise CorrectionControlError("observed specimen identity/genotype differs from frozen plan")
    frozen = _time(plan.get("frozen_at"), "frozen_at")
    if frozen >= _time(evidence.get("outcome_unblinded_at"), "outcome_unblinded_at"):
        raise CorrectionControlError("plan must be frozen strictly before outcome unblinding")
    _text(plan.get("freeze_record_id"), "freeze_record_id")
    plan_digest = semantic_digest(plan)
    if evidence.get("plan_sha256") != plan_digest:
        raise CorrectionControlError("evidence is not bound to this frozen plan")
    method = _text(plan.get("contrast_method_id"), "contrast_method_id")
    if evidence.get("contrast_method_id") != method:
        raise CorrectionControlError("contrast method differs from frozen plan")
    _text(evidence.get("analysis_record_id"), "analysis_record_id")
    confidence = _number(plan.get("confidence_level"), "confidence_level")
    if not 0.95 <= confidence < 1 or evidence.get("confidence_level") != confidence:
        raise CorrectionControlError("matching confidence level of at least 0.95 is required")
    planned = _endpoints(plan.get("endpoints"), "plan endpoints")
    observed = _endpoints(evidence.get("endpoints"), "evidence endpoints")
    failed = []
    for endpoint in ENDPOINTS:
        p, e = planned[endpoint], observed[endpoint]
        if p.get("direction") not in ("higher_is_better", "lower_is_better"):
            raise CorrectionControlError("endpoint direction must be prespecified")
        expected_direction = {"abundance": "higher_is_better", "half_life": "higher_is_better",
                              "first_division_error": "lower_is_better"}.get(endpoint)
        if expected_direction is not None and p["direction"] != expected_direction:
            raise CorrectionControlError("fixed raw endpoint has an invalid biological direction")
        if e.get("direction") != p["direction"] or e.get("units") != _text(p.get("units"), "units"):
            raise CorrectionControlError("endpoint direction or units differ from plan")
        lo, hi = _interval(p.get("equivalence_bounds"), "equivalence_bounds")
        if not lo < 0 < hi:
            raise CorrectionControlError("equivalence bounds must straddle zero")
        role = p.get("role")
        if role not in ("defect_reversal", "preservation_equivalence"):
            raise CorrectionControlError("endpoint role must be prespecified")
        if endpoint in ("abundance", "half_life") and role != "defect_reversal":
            raise CorrectionControlError("instability endpoints require defect reversal")
        delta = _interval(e.get("corrected_minus_carrier_ci"), "equivalence_ci")
        mutant, carrier, corrected = [_number(e.get(key), key) for key in
                                      ("mutant_mean", "carrier_mean", "corrected_mean")]
        sign = 1 if p["direction"] == "higher_is_better" else -1
        oriented_gap = sign * (carrier - mutant)
        difference = corrected - carrier
        if not math.isfinite(oriented_gap) or not math.isfinite(difference):
            raise CorrectionControlError("contrast arithmetic overflow")
        if not delta[0] <= difference <= delta[1]:
            raise CorrectionControlError("equivalence interval does not contain its declared mean contrast")
        reasons = []
        if delta[0] < lo or delta[1] > hi:
            reasons.append("carrier_equivalence_not_established")
        if role == "defect_reversal":
            minimum = _number(p.get("minimum_gap_restoration"), "minimum_gap_restoration")
            if not 0.5 <= minimum <= 1:
                raise CorrectionControlError("restoration margin must be between 0.5 and 1")
            gap = _interval(e.get("oriented_mutant_to_carrier_gap_ci"), "gap_ci")
            restoration = _interval(e.get("gap_restoration_fraction_ci"), "restoration_ci")
            if not gap[0] <= oriented_gap <= gap[1]:
                raise CorrectionControlError("gap interval does not contain its declared mean contrast")
            if oriented_gap > 0:
                fraction = sign * (corrected - mutant) / oriented_gap
                if not math.isfinite(fraction) or not restoration[0] <= fraction <= restoration[1]:
                    raise CorrectionControlError("restoration interval does not contain declared mean ratio")
            if gap[0] <= 0:
                reasons.append("positive_oriented_gap_not_established")
            if restoration[0] < minimum:
                reasons.append("half_gap_restoration_not_established")
        else:
            baseline_lo, baseline_hi = _interval(p.get("baseline_equivalence_bounds"), "baseline_equivalence_bounds")
            if not baseline_lo < 0 < baseline_hi:
                raise CorrectionControlError("baseline equivalence bounds must straddle zero")
            baseline = _interval(e.get("mutant_minus_carrier_ci"), "baseline_ci")
            if not baseline[0] <= mutant - carrier <= baseline[1]:
                raise CorrectionControlError("baseline interval does not contain declared mean contrast")
            if baseline[0] < baseline_lo or baseline[1] > baseline_hi:
                reasons.append("baseline_carrier_equivalence_not_established")
        if reasons:
            failed.append({"endpoint": endpoint, "reasons": reasons})
    result = {
        "schema": RESULT_SCHEMA,
        "assessment_scope": "correction_control_only",
        "legacy_pipeline_eligible": False,
        "status": "contract_satisfied" if not failed else "hold",
        "plan_sha256": plan_digest,
        "evidence_sha256": semantic_digest(evidence),
        "failed_endpoints": failed,
        "claim_boundary": "Declared metadata and supplied contrast intervals only. Not genotype authentication, preregistration verification, full hypomorph eligibility, efficacy, or clinical benefit. End-to-end genotype-aware routing remains unimplemented.",
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result
