"""Fail-closed computational ranking that cannot stand in for an assay.

Local geometry can only change the order of wet experiments. Predicted
stability, pathogenicity scores, and analog residues cannot make
checkpoint-ready true. This is not a docking study and not efficacy evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mva_hackathon.provenance import receipt_sha256


SCHEMA = "mva-track2-structure-ranking/v1"
ROLES = ("exact", "analog_unstable", "nearby_benign")
METHODS = ("geometry", "alphamissense", "foldx_alphafold")
PRIORITIES = ("prioritize_assay", "similar", "deprioritize_assay")
MARGIN = 0.05
MINIMUM_PLDDT = 70.0
CLAIM_BOUNDARY = (
    "Computational ranking only; predicted stability and local geometry are "
    "not an exact-allele assay; ranking cannot make checkpoint_ready true; "
    "this is not efficacy evidence."
)


class StructureRankingError(ValueError):
    """Raised when a structure-ranking table violates its contract."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StructureRankingError(f"{label} must be an object")
    return value


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise StructureRankingError(f"{field} must be a boolean")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StructureRankingError(f"{field} must be a finite number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise StructureRankingError(f"{field} must be a finite number") from exc
    if result != result or result in {float("inf"), float("-inf")}:
        raise StructureRankingError(f"{field} must be a finite number")
    return result


def _role_row(residues: list[Any], role: str) -> Mapping[str, Any] | None:
    matches = [
        row
        for row in residues
        if isinstance(row, Mapping) and row.get("role") == role
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _feature_distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    rsa_gap = abs(_finite(left.get("rsa"), "rsa") - _finite(right.get("rsa"), "rsa"))
    contact_gap = abs(
        _finite(left.get("polar_contacts"), "polar_contacts")
        - _finite(right.get("polar_contacts"), "polar_contacts")
    ) / 10.0
    return rsa_gap + contact_gap


def _features_usable(by_role: Mapping[str, Mapping[str, Any]]) -> bool:
    for row in by_role.values():
        rsa = _finite(row.get("rsa"), "rsa")
        contacts = _finite(row.get("polar_contacts"), "polar_contacts")
        plddt = _finite(row.get("plddt"), "plddt")
        if not 0.0 <= rsa <= 1.0:
            return False
        if contacts < 0.0 or contacts != int(contacts):
            return False
        if not 0.0 <= plddt <= 100.0:
            return False
    return True


def _residue_ids_usable(by_role: Mapping[str, Mapping[str, Any]]) -> bool:
    ids: list[str] = []
    for row in by_role.values():
        residue_id = row.get("residue_id")
        if (
            not isinstance(residue_id, str)
            or not residue_id
            or residue_id != residue_id.strip()
            or not residue_id.isascii()
        ):
            return False
        ids.append(residue_id.casefold())
    return len(set(ids)) == len(ids)


def assess_structure_ranking(table: Mapping[str, Any]) -> dict[str, Any]:
    """Rank an exact residue against analog-unstable and nearby-benign controls.

    Geometry can prioritize or deprioritize a wet assay. FoldX-on-AlphaFold and
    pathogenicity scores cannot, and they cannot pass the stop-early ranking
    gate. The exact-role residue must be claimed as exact. RSA must be a unit
    fraction, polar contacts must be a whole-number count, and pLDDT must be a
    percent.     The three role rows must carry distinct residue ids, including after
    case folding. Extra residues, missing control roles, or duplicate roles
    cannot open confirmation. used_as_function is always a stop.
    """

    payload = _mapping(table, "structure ranking")
    if payload.get("schema") != SCHEMA:
        raise StructureRankingError("structure ranking accepts the ranking table only")
    method = payload.get("method")
    if method not in METHODS:
        raise StructureRankingError("method is not in the allowed vocabulary")
    used_as_function = _bool(payload.get("used_as_function"), "used_as_function")
    residues = payload.get("residues")
    if not isinstance(residues, list) or not residues or len(residues) > 64:
        raise StructureRankingError("residues must be a bounded non-empty list")
    by_role_found = {role: _role_row(residues, role) for role in ROLES}
    analog_as_exact = any(
        isinstance(row, Mapping)
        and row.get("role") != "exact"
        and _bool(row.get("claimed_as_exact", False), "claimed_as_exact")
        for row in residues
    )
    exact = by_role_found["exact"]
    analog = by_role_found["analog_unstable"]
    benign = by_role_found["nearby_benign"]
    table_usable = len(residues) == 3 and None not in by_role_found.values()
    if table_usable:
        by_role = {
            "exact": exact,
            "analog_unstable": analog,
            "nearby_benign": benign,
        }
        exact_claimed = _bool(exact.get("claimed_as_exact", False), "claimed_as_exact")
        features_usable = _features_usable(by_role)
        residue_ids_usable = _residue_ids_usable(by_role)
        exact_plddt = _finite(exact.get("plddt"), "plddt")
        analog_distance = _feature_distance(exact, analog)
        benign_distance = _feature_distance(exact, benign)
    else:
        exact_claimed = False
        features_usable = False
        residue_ids_usable = False
        exact_plddt = 0.0
        analog_distance = 0.0
        benign_distance = 0.0

    if used_as_function:
        status = "stop"
        effect = "stop"
        reason = "ranking_is_not_an_assay"
        priority = "similar"
    elif analog_as_exact:
        status = "stop"
        effect = "stop"
        reason = "analog_as_exact_function"
        priority = "similar"
    elif method != "geometry":
        status = "not_assessable"
        effect = "hold"
        reason = "method_cannot_replace_assay"
        priority = "similar"
    elif not table_usable:
        status = "not_assessable"
        effect = "hold"
        reason = "ranking_table_unusable"
        priority = "similar"
    elif not exact_claimed:
        status = "not_assessable"
        effect = "hold"
        reason = "exact_claim_required"
        priority = "similar"
    elif not features_usable:
        status = "not_assessable"
        effect = "hold"
        reason = "ranking_features_unusable"
        priority = "similar"
    elif not residue_ids_usable:
        status = "not_assessable"
        effect = "hold"
        reason = "ranking_residue_ids_unusable"
        priority = "similar"
    elif exact_plddt < MINIMUM_PLDDT:
        status = "pass"
        effect = "pass"
        reason = "exact_geometry_unreliable"
        priority = "similar"
    elif analog_distance + MARGIN < benign_distance:
        status = "pass"
        effect = "pass"
        reason = "exact_closer_to_analog"
        priority = "prioritize_assay"
    elif benign_distance + MARGIN < analog_distance:
        status = "pass"
        effect = "pass"
        reason = "exact_closer_to_benign"
        priority = "deprioritize_assay"
    else:
        status = "pass"
        effect = "pass"
        reason = "geometry_similar"
        priority = "similar"

    result = {
        "schema": SCHEMA,
        "gate": "structure_ranking",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": effect,
        "reason": reason,
        "method": method,
        "assay_priority": priority,
        "checkpoint_ready": False,
        "probe_eligible": False,
        "used_as_function": used_as_function,
        "analog_as_exact": analog_as_exact,
        "exact_claimed": exact_claimed,
        "features_usable": features_usable,
        "residue_ids_usable": residue_ids_usable,
        "table_usable": table_usable,
        "analog_distance": analog_distance,
        "benign_distance": benign_distance,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


__all__ = [
    "CLAIM_BOUNDARY",
    "METHODS",
    "PRIORITIES",
    "SCHEMA",
    "StructureRankingError",
    "assess_structure_ranking",
]
