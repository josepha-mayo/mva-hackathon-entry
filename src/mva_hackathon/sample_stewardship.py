"""Fail-closed planning for scarce participant-derived material.

The planner uses vector resource budgets and dominance, not a fabricated
scalar value-of-information score. It validates two independent discovery
paths through A0, A1, therapeutic-context qualification, native-lineage
confirmation, held-out confirmation, and replication. Completion receipts
bind an outcome and exact resource debit to one assay-contract snapshot. The
module does not choose a medicine or establish biological rescue.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "mva.track2-sample-stewardship/v17"
RESULT_SCHEMA = "mva.track2-sample-stewardship-result/v17"
CLAIM_BOUNDARY = (
    "Synthetic sample-stewardship contract only; vector budgets, receipt "
    "digests, and ordering do not establish participant biology, treatment, "
    "safety, dose, or benefit."
)

RESOURCE_AXES = (
    "dna_aliquots",
    "rna_aliquots",
    "viable_cell_equivalents",
    "population_doublings",
    "edit_event_families",
)
PARTITIONS = (
    "renewable_nonparticipant",
    "participant_discovery",
    "participant_held_out",
    "independent_site",
)
STAGES = ("A0", "A1", "TIER_B", "HELD_OUT", "REPLICATION")
STAGE_PARTITIONS = {
    "A0": {"renewable_nonparticipant"},
    "A1": {"participant_discovery"},
    "TIER_B": {"participant_discovery"},
    "HELD_OUT": {"participant_held_out"},
    "REPLICATION": {"independent_site"},
}
DISCOVERY_LANES = (
    "targeted_hypothesis",
    "correction_trained_phenotypic",
)
OUTCOMES = ("positive", "negative", "invalid")
CONSENT_STATES = ("consented", "not_consented", "withdrawn", "not_applicable")
PARTICIPANT_PARTITIONS = {
    "participant_discovery",
    "participant_held_out",
    "independent_site",
}
ALLOWED_ACTIONS = {
    "reject_condition",
    "revise_mechanism",
    "advance_to_a1",
    "participant_branch_no_hit",
    "advance_to_context_qualification",
    "advance_to_native_lineage",
    "record_mechanism_only",
    "held_out_confirmation",
    "independent_replication",
    "stop_unsafe",
    "hold_invalid",
}
A0_SHARED_VALIDITY_REQUIREMENTS = {
    "measured_exposure",
    "valid_controls",
    "locked_function",
    "same_background_correction_rescue",
    "same_background_reciprocal_recreation",
    "genotype_harm_counterscreen",
}
A0_PHENOTYPE_VALIDITY_REQUIREMENTS = A0_SHARED_VALIDITY_REQUIREMENTS | {
    "correction_signature_separation",
}
A0_SHARED_EVIDENCE_FIELDS = (
    "measured_exposure_id",
    "valid_controls_id",
    "locked_function_id",
    "same_background_correction_id",
    "same_background_recreation_id",
    "genotype_harm_counterscreen_id",
)
A0_PHENOTYPE_EVIDENCE_FIELDS = A0_SHARED_EVIDENCE_FIELDS + (
    "correction_signature_separation_id",
)
A1_NO_HIT_REQUIREMENTS = {
    "measured_exposure",
    "valid_controls",
    "participant_context",
    "locked_function",
    "short_term_viability_completion",
}
A1_EVIDENCE_FIELDS = (
    "measured_exposure_id",
    "valid_controls_id",
    "participant_context_id",
    "locked_function_id",
    "short_term_viability_id",
)
HELD_OUT_VALIDITY_REQUIREMENTS = {
    "frozen_exposure",
    "frozen_endpoint",
    "frozen_margin",
    "blinded_execution",
}
HELD_OUT_EVIDENCE_FIELDS = (
    "frozen_exposure_id",
    "frozen_endpoint_id",
    "frozen_margin_id",
    "blinded_execution_id",
)
CONTEXT_SHARED_VALIDITY_REQUIREMENTS = {
    "postnatal_lineage_rationale",
    "nontransformed_proliferative_context",
    "paired_2d_comparison",
    "same_context_correction_rescue",
    "same_context_reciprocal_recreation",
    "opaque_context_receipt_identity",
}
CONTEXT_VALIDITY_REQUIREMENTS = CONTEXT_SHARED_VALIDITY_REQUIREMENTS | {
    "architecture_preserving_context",
}
LINEAGE_INTRINSIC_VALIDITY_REQUIREMENTS = CONTEXT_SHARED_VALIDITY_REQUIREMENTS | {
    "lineage_intrinsic_mitotic_context",
}
MITOTIC_CONTEXT_CLASSES = frozenset(
    {
        "epithelial_architecture_dependent",
        "lineage_intrinsic_mitotic",
        "not_assessable",
    }
)
TRANSFORMATION_STATES = frozenset(
    {
        "primary_finite",
        "renewable_nontransformed_isogenic",
        "immortalized_or_transformed",
        "reprogrammed",
        "not_assessable",
    }
)
CONTEXT_ENUM_FIELDS = {
    "mitotic_context_class": MITOTIC_CONTEXT_CLASSES,
    "transformation_state": TRANSFORMATION_STATES,
}
CONTEXT_ID_FIELDS = (
    "postnatal_lineage_rationale_id",
    "architecture_preserving_context_id",
    "paired_2d_comparison_id",
    "same_context_correction_id",
    "same_context_recreation_id",
    "receipt_identity_id",
)
NATIVE_LINEAGE_REQUIREMENTS = {
    "native_fidelity",
    "completion_equivalence",
    "clone_safety",
}
NATIVE_LINEAGE_EVIDENCE_FIELDS = (
    "native_fidelity_id",
    "completion_equivalence_id",
    "clone_safety_id",
)
REPLICATION_REQUIREMENTS = {
    "different_site",
    "nonoverlapping_edit_event_families",
    "frozen_exposure",
    "frozen_endpoint",
    "frozen_margin",
    "frozen_protocol",
    "frozen_analysis",
    "blinded_site2",
    "common_reference_transfer_qc",
}
REPLICATION_EVIDENCE_FIELDS = (
    "frozen_exposure_id",
    "frozen_endpoint_id",
    "frozen_margin_id",
    "frozen_protocol_id",
    "frozen_analysis_id",
    "common_reference_transfer_qc_id",
)
SHARED_HELD_OUT_REPLICATION_FIELDS = (
    "frozen_exposure_id",
    "frozen_endpoint_id",
    "frozen_margin_id",
)
TOP_LEVEL_FIELDS = {"schema", "synthetic_only", "inventory", "completed", "assays"}
ASSAY_REQUIRED_FIELDS = {
    "assay_id",
    "stage",
    "partition",
    "discovery_lane",
    "destructive",
    "consumption",
    "prerequisites",
    "decision_changes",
    "validity_requirements",
    "outcome_actions",
}
ASSAY_OPTIONAL_FIELDS = {
    "consent_state",
    "independence_requirements",
    "context_qualification",
    "correction_core",
    "a1_lock",
    "held_out_lock",
    "replication_lock",
    "lineage_lock",
}
COMPLETION_RECEIPT_REQUIRED_FIELDS = {
    "receipt_id",
    "assay_contract_sha256",
    "outcome",
    "outcome_action",
    "partition",
    "resource_debit",
    "receipt_sha256",
}
COMPLETION_RECEIPT_OPTIONAL_FIELDS = {"promotion_evidence"}
PROMOTION_EVIDENCE_FIELDS = {
    "analytic_transfer_result_sha256",
    "site2_blinding_state",
    "site2_blinding_id",
    "site2_blinding_evidence_sha256",
    "discovery_event_family_ids",
    "replication_event_family_ids",
    "discovery_site_id",
    "replication_site_id",
}
OPAQUE_ID_PATTERN = re.compile(r"^syn-[a-z0-9][a-z0-9-]*$")
COMPLETION_ID_PATTERN = re.compile(r"^syn-completion-[a-z0-9][a-z0-9-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SampleStewardshipError(ValueError):
    """Raised when a sample-stewardship plan is unsafe or ambiguous."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SampleStewardshipError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SampleStewardshipError(f"{label} must be a list")
    return value


def _string_set(value: object, label: str) -> set[str]:
    items = _sequence(value, label)
    result: set[str] = set()
    for item in items:
        if not isinstance(item, str) or not item:
            raise SampleStewardshipError(f"{label} must contain non-empty strings")
        if item in result:
            raise SampleStewardshipError(f"{label} contains duplicate {item!r}")
        result.add(item)
    return result


def _canonical_strings(value: object, label: str) -> list[str]:
    if isinstance(value, (set, frozenset)):
        for item in value:
            if not isinstance(item, str) or not item:
                raise SampleStewardshipError(
                    f"{label} must contain non-empty strings"
                )
        return sorted(value)
    return sorted(_string_set(value, label))


def _resource_vector(value: object, label: str) -> dict[str, int]:
    record = _mapping(value, label)
    extra = set(record) - set(RESOURCE_AXES)
    missing = set(RESOURCE_AXES) - set(record)
    if extra or missing:
        raise SampleStewardshipError(
            f"{label} must contain exactly {', '.join(RESOURCE_AXES)}"
        )
    result: dict[str, int] = {}
    for axis in RESOURCE_AXES:
        amount = record[axis]
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise SampleStewardshipError(f"{label}.{axis} must be a non-negative integer")
        result[axis] = amount
    return result


def _opaque_id(value: object, label: str, *, completion: bool = False) -> str:
    pattern = COMPLETION_ID_PATTERN if completion else OPAQUE_ID_PATTERN
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        expected = "opaque syn-completion-" if completion else "opaque syn-"
        raise SampleStewardshipError(f"{label} must use an {expected} identifier")
    return value


def _correction_core(value: object, label: str, lane: str) -> dict[str, str]:
    record = _mapping(value, label)
    expected = (
        A0_PHENOTYPE_EVIDENCE_FIELDS
        if lane == "correction_trained_phenotypic"
        else A0_SHARED_EVIDENCE_FIELDS
    )
    if set(record) != set(expected):
        raise SampleStewardshipError(
            f"{label} must contain exactly {', '.join(expected)}"
        )
    parsed = {
        field: _opaque_id(record[field], f"{label}.{field}") for field in expected
    }
    seen: dict[str, str] = {}
    for field, identifier in parsed.items():
        previous = seen.get(identifier)
        if previous is not None:
            raise SampleStewardshipError(
                f"{label} reuses {identifier!r} for {previous} and {field}"
            )
        seen[identifier] = field
    return parsed


def _a1_lock(value: object, label: str) -> dict[str, str]:
    record = _mapping(value, label)
    if set(record) != set(A1_EVIDENCE_FIELDS):
        raise SampleStewardshipError(
            f"{label} must contain exactly {', '.join(A1_EVIDENCE_FIELDS)}"
        )
    parsed = {
        field: _opaque_id(record[field], f"{label}.{field}")
        for field in A1_EVIDENCE_FIELDS
    }
    seen: dict[str, str] = {}
    for field, identifier in parsed.items():
        previous = seen.get(identifier)
        if previous is not None:
            raise SampleStewardshipError(
                f"{label} reuses {identifier!r} for {previous} and {field}"
            )
        seen[identifier] = field
    return parsed


def _lineage_lock(value: object, label: str) -> dict[str, str]:
    record = _mapping(value, label)
    if set(record) != set(NATIVE_LINEAGE_EVIDENCE_FIELDS):
        raise SampleStewardshipError(
            f"{label} must contain exactly {', '.join(NATIVE_LINEAGE_EVIDENCE_FIELDS)}"
        )
    parsed = {
        field: _opaque_id(record[field], f"{label}.{field}")
        for field in NATIVE_LINEAGE_EVIDENCE_FIELDS
    }
    seen: dict[str, str] = {}
    for field, identifier in parsed.items():
        previous = seen.get(identifier)
        if previous is not None:
            raise SampleStewardshipError(
                f"{label} reuses {identifier!r} for {previous} and {field}"
            )
        seen[identifier] = field
    return parsed


def _held_out_lock(value: object, label: str) -> dict[str, str]:
    record = _mapping(value, label)
    if set(record) != set(HELD_OUT_EVIDENCE_FIELDS):
        raise SampleStewardshipError(
            f"{label} must contain exactly {', '.join(HELD_OUT_EVIDENCE_FIELDS)}"
        )
    parsed = {
        field: _opaque_id(record[field], f"{label}.{field}")
        for field in HELD_OUT_EVIDENCE_FIELDS
    }
    seen: dict[str, str] = {}
    for field, identifier in parsed.items():
        previous = seen.get(identifier)
        if previous is not None:
            raise SampleStewardshipError(
                f"{label} reuses {identifier!r} for {previous} and {field}"
            )
        seen[identifier] = field
    return parsed


def _replication_lock(value: object, label: str) -> dict[str, str]:
    record = _mapping(value, label)
    if set(record) != set(REPLICATION_EVIDENCE_FIELDS):
        raise SampleStewardshipError(
            f"{label} must contain exactly {', '.join(REPLICATION_EVIDENCE_FIELDS)}"
        )
    parsed = {
        field: _opaque_id(record[field], f"{label}.{field}")
        for field in REPLICATION_EVIDENCE_FIELDS
    }
    seen: dict[str, str] = {}
    for field, identifier in parsed.items():
        previous = seen.get(identifier)
        if previous is not None:
            raise SampleStewardshipError(
                f"{label} reuses {identifier!r} for {previous} and {field}"
            )
        seen[identifier] = field
    return parsed


def _shared_estimand_partners(
    assay_id: str,
    assay: Mapping[str, Any],
    field: str,
    assays_by_id: Mapping[str, Mapping[str, Any]],
) -> frozenset[str]:
    if field not in SHARED_HELD_OUT_REPLICATION_FIELDS:
        return frozenset()
    lane = assay["discovery_lane"]
    stage = assay["stage"]
    partners: set[str] = set()
    for other_id, other in assays_by_id.items():
        if other_id == assay_id or other["discovery_lane"] != lane:
            continue
        if stage == "REPLICATION" and other["stage"] == "HELD_OUT":
            partners.add(f"{other_id}.held_out_lock")
        elif stage == "HELD_OUT" and other["stage"] == "REPLICATION":
            partners.add(f"{other_id}.replication_lock")
    return frozenset(partners)


def _register_lock_ids(
    assay_id: str,
    assay: Mapping[str, Any],
    lock: Mapping[str, str],
    lock_name: str,
    seen_evidence_ids: dict[str, str],
    assays_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    owner = f"{assay_id}.{lock_name}"
    for field, identifier in lock.items():
        previous = seen_evidence_ids.get(identifier)
        if previous is not None and previous != owner:
            partners = _shared_estimand_partners(
                assay_id, assay, field, assays_by_id
            )
            if previous not in partners:
                raise SampleStewardshipError(
                    f"{assay_id} {lock_name} reuses {identifier!r} from {previous}"
                )
            continue
        if previous is None:
            seen_evidence_ids[identifier] = owner


def _assert_held_out_replication_estimand_equivalence(
    assays_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    by_lane: dict[str, dict[str, list[tuple[str, Mapping[str, str]]]]] = {}
    for assay_id, assay in assays_by_id.items():
        stage = assay["stage"]
        if stage == "HELD_OUT":
            lock = assay.get("held_out_lock")
        elif stage == "REPLICATION":
            lock = assay.get("replication_lock")
        else:
            continue
        if not isinstance(lock, dict):
            continue
        by_lane.setdefault(assay["discovery_lane"], {}).setdefault(
            stage, []
        ).append((assay_id, lock))
    for stages in by_lane.values():
        held = stages.get("HELD_OUT", [])
        replication = stages.get("REPLICATION", [])
        if not held or not replication:
            continue
        for field in SHARED_HELD_OUT_REPLICATION_FIELDS:
            held_values = {lock[field] for _, lock in held}
            replication_values = {lock[field] for _, lock in replication}
            if held_values != replication_values or len(held_values) != 1:
                raise SampleStewardshipError(
                    f"{replication[0][0]} {field} must match same-lane "
                    "held-out frozen estimand"
                )


def _context_qualification(value: object, label: str) -> dict[str, Any]:
    record = _mapping(value, label)
    expected = set(CONTEXT_ID_FIELDS) | set(CONTEXT_ENUM_FIELDS)
    if set(record) != expected:
        raise SampleStewardshipError(
            f"{label} must contain exactly {', '.join(sorted(expected))}"
        )
    parsed: dict[str, Any] = {
        field: _opaque_id(record[field], f"{label}.{field}")
        for field in CONTEXT_ID_FIELDS
    }
    seen: dict[str, str] = {}
    for field in CONTEXT_ID_FIELDS:
        identifier = parsed[field]
        previous = seen.get(identifier)
        if previous is not None:
            raise SampleStewardshipError(
                f"{label} reuses {identifier!r} for {previous} and {field}"
            )
        seen[identifier] = field
    for field, allowed in CONTEXT_ENUM_FIELDS.items():
        observed = record[field]
        if observed not in allowed:
            raise SampleStewardshipError(
                f"{label}.{field} must be one of {sorted(allowed)}"
            )
        parsed[field] = observed
    if parsed["transformation_state"] != "primary_finite":
        raise SampleStewardshipError(
            f"{label} transformed, reprogrammed, renewable-isogenic, or unknown "
            "cultures cannot qualify postnatal nontransformed context"
        )
    if parsed["mitotic_context_class"] == "not_assessable":
        raise SampleStewardshipError(
            f"{label} mitotic_context_class cannot be not_assessable"
        )
    return parsed


def _promotion_evidence(value: object, label: str) -> dict[str, Any]:
    record = _mapping(value, label)
    if set(record) != PROMOTION_EVIDENCE_FIELDS:
        raise SampleStewardshipError(
            f"{label} must contain exactly "
            + ", ".join(sorted(PROMOTION_EVIDENCE_FIELDS))
        )
    fingerprints: dict[str, str] = {}
    for field in (
        "analytic_transfer_result_sha256",
        "site2_blinding_evidence_sha256",
    ):
        fingerprint = record[field]
        if (
            not isinstance(fingerprint, str)
            or SHA256_PATTERN.fullmatch(fingerprint) is None
        ):
            raise SampleStewardshipError(
                f"{label}.{field} must be lowercase SHA-256"
            )
        fingerprints[field] = fingerprint
    if len(set(fingerprints.values())) != len(fingerprints):
        raise SampleStewardshipError(
            f"{label} analytic-transfer and site-2 blinding evidence "
            "fingerprints must identify distinct receipts"
        )
    if record["site2_blinding_state"] != "blinded":
        raise SampleStewardshipError(f"{label}.site2_blinding_state must be blinded")
    discovery = _string_set(
        record["discovery_event_family_ids"],
        f"{label}.discovery_event_family_ids",
    )
    replication = _string_set(
        record["replication_event_family_ids"],
        f"{label}.replication_event_family_ids",
    )
    if not discovery or not replication:
        raise SampleStewardshipError(f"{label} event-family sets must be nonempty")
    for field, identifiers in (
        ("discovery_event_family_ids", discovery),
        ("replication_event_family_ids", replication),
    ):
        for identifier in identifiers:
            _opaque_id(identifier, f"{label}.{field}")
    overlap = discovery & replication
    if overlap:
        raise SampleStewardshipError(
            f"{label} discovery and replication event families overlap: "
            f"{sorted(overlap)}"
        )
    discovery_site = _opaque_id(record["discovery_site_id"], f"{label}.discovery_site_id")
    replication_site = _opaque_id(
        record["replication_site_id"], f"{label}.replication_site_id"
    )
    if discovery_site == replication_site:
        raise SampleStewardshipError(
            f"{label} discovery_site_id and replication_site_id must differ"
        )
    family_ids = discovery | replication
    site_overlap = {discovery_site, replication_site} & family_ids
    if site_overlap:
        raise SampleStewardshipError(
            f"{label} site identities overlap event families: {sorted(site_overlap)}"
        )
    blinding_id = _opaque_id(record["site2_blinding_id"], f"{label}.site2_blinding_id")
    blinding_overlap = {blinding_id} & family_ids.union({discovery_site, replication_site})
    if blinding_overlap:
        raise SampleStewardshipError(
            f"{label} site2_blinding_id overlaps site or event-family identities: "
            f"{sorted(blinding_overlap)}"
        )
    return {
        **fingerprints,
        "site2_blinding_state": "blinded",
        "site2_blinding_id": blinding_id,
        "discovery_event_family_ids": sorted(discovery),
        "replication_event_family_ids": sorted(replication),
        "discovery_site_id": discovery_site,
        "replication_site_id": replication_site,
    }


def _uses_no_more(left: Mapping[str, int], right: Mapping[str, int]) -> bool:
    return all(left[axis] <= right[axis] for axis in RESOURCE_AXES)


def _strictly_better_resource(left: Mapping[str, int], right: Mapping[str, int]) -> bool:
    return any(left[axis] < right[axis] for axis in RESOURCE_AXES)


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_assay_contract(assay: Mapping[str, Any]) -> dict[str, Any]:
    """Return assay fields in a deterministic, digestable representation."""

    record = _mapping(assay, "assay contract")
    contract: dict[str, Any] = {
        "assay_id": record.get("assay_id"),
        "stage": record.get("stage"),
        "partition": record.get("partition"),
        "discovery_lane": record.get("discovery_lane"),
        "destructive": record.get("destructive"),
        "consumption": _resource_vector(record.get("consumption"), "assay consumption"),
        "prerequisites": _canonical_strings(
            record.get("prerequisites"), "assay prerequisites"
        ),
        "decision_changes": _canonical_strings(
            record.get("decision_changes"), "assay decision_changes"
        ),
        "validity_requirements": _canonical_strings(
            record.get("validity_requirements"), "assay validity_requirements"
        ),
        "outcome_actions": dict(
            _mapping(record.get("outcome_actions"), "assay outcome_actions")
        ),
    }
    if "independence_requirements" in record:
        contract["independence_requirements"] = _canonical_strings(
            record["independence_requirements"],
            "assay independence_requirements",
        )
    if "context_qualification" in record:
        contract["context_qualification"] = _context_qualification(
            record["context_qualification"], "assay context_qualification"
        )
    if "correction_core" in record:
        contract["correction_core"] = _correction_core(
            record["correction_core"],
            "assay correction_core",
            str(record.get("discovery_lane")),
        )
    if "a1_lock" in record:
        contract["a1_lock"] = _a1_lock(record["a1_lock"], "assay a1_lock")
    if "held_out_lock" in record:
        contract["held_out_lock"] = _held_out_lock(
            record["held_out_lock"],
            "assay held_out_lock",
        )
    if "replication_lock" in record:
        contract["replication_lock"] = _replication_lock(
            record["replication_lock"],
            "assay replication_lock",
        )
    if "lineage_lock" in record:
        contract["lineage_lock"] = _lineage_lock(
            record["lineage_lock"],
            "assay lineage_lock",
        )
    return contract


def assay_contract_sha256(assay: Mapping[str, Any]) -> str:
    """Digest the normalized assay contract referenced by a receipt."""

    return _canonical_json_sha256(_canonical_assay_contract(assay))


def completion_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    """Digest a completion receipt body, excluding its self-digest field."""

    record = dict(_mapping(receipt, "completion receipt"))
    record.pop("receipt_sha256", None)
    return _canonical_json_sha256(record)


def make_completion_receipt(
    assay: Mapping[str, Any],
    outcome: str,
    receipt_id: str,
    *,
    promotion_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic synthetic receipt; this does not record an outcome."""

    contract = _canonical_assay_contract(assay)
    _opaque_id(receipt_id, "receipt_id", completion=True)
    if outcome not in OUTCOMES:
        raise SampleStewardshipError(f"outcome must be one of {OUTCOMES}")
    actions = _mapping(contract["outcome_actions"], "assay outcome_actions")
    if set(actions) != set(OUTCOMES):
        raise SampleStewardshipError(
            f"assay outcome_actions must contain exactly {', '.join(OUTCOMES)}"
        )
    body: dict[str, Any] = {
        "receipt_id": receipt_id,
        "assay_contract_sha256": _canonical_json_sha256(contract),
        "outcome": outcome,
        "outcome_action": actions[outcome],
        "partition": contract["partition"],
        "resource_debit": contract["consumption"],
    }
    requires_promotion = contract["stage"] == "REPLICATION" and outcome == "positive"
    if requires_promotion:
        if promotion_evidence is None:
            raise SampleStewardshipError(
                "positive replication receipt requires structured promotion_evidence"
            )
        body["promotion_evidence"] = _promotion_evidence(
            promotion_evidence, "promotion_evidence"
        )
        for field, label in (
            ("analytic_transfer_result_sha256", "analytic transfer"),
            ("site2_blinding_evidence_sha256", "site-2 blinding evidence"),
        ):
            if body["promotion_evidence"][field] == body["assay_contract_sha256"]:
                raise SampleStewardshipError(
                    f"{label} cannot be the assay-contract digest"
                )
    elif promotion_evidence is not None:
        raise SampleStewardshipError(
            "promotion_evidence is restricted to a positive replication receipt"
        )
    body["receipt_sha256"] = completion_receipt_sha256(body)
    return body


def _children_map(
    assays_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {assay_id: [] for assay_id in assays_by_id}
    for assay_id, assay in assays_by_id.items():
        for parent in assay["prerequisites"]:
            children[parent].append(assay_id)
    return children


def _descendants(assay_id: str, children: Mapping[str, Sequence[str]]) -> list[str]:
    found: list[str] = []
    stack = list(children[assay_id])
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        found.append(node)
        stack.extend(children[node])
    return found


def _is_native_lineage(assay: Mapping[str, Any]) -> bool:
    return (
        assay["stage"] == "TIER_B"
        and assay.get("context_qualification") is None
        and assay["partition"] == "participant_discovery"
    )


def _a1_priority(assay: Mapping[str, Any]) -> tuple[int, int, str]:
    lane_rank = 0 if assay["discovery_lane"] == "targeted_hypothesis" else 1
    return (lane_rank, assay["consumption"]["edit_event_families"], assay["assay_id"])


def _a1_discovery_reservation(
    assay: Mapping[str, Any],
    assays_by_id: Mapping[str, Mapping[str, Any]],
    children: Mapping[str, Sequence[str]],
    completed_outcomes: Mapping[str, str],
) -> dict[str, int]:
    reserved = {axis: assay["consumption"][axis] for axis in RESOURCE_AXES}
    for descendant_id in _descendants(assay["assay_id"], children):
        if descendant_id in completed_outcomes:
            continue
        descendant = assays_by_id[descendant_id]
        if (
            descendant["partition"] != assay["partition"]
            or descendant["stage"] != "TIER_B"
        ):
            continue
        for axis in RESOURCE_AXES:
            reserved[axis] += descendant["consumption"][axis]
    return reserved


def _has_direct_role_prerequisite(
    assay_id: str,
    required_stage: str,
    assays_by_id: Mapping[str, Mapping[str, Any]],
    *,
    context_role: bool | None = None,
) -> bool:
    """Return whether a direct predecessor has the required stage and Tier-B role."""

    for prerequisite in assays_by_id[assay_id]["prerequisites"]:
        parent = assays_by_id[prerequisite]
        if parent["stage"] != required_stage:
            continue
        if context_role is None:
            return True
        is_context = parent.get("context_qualification") is not None
        if is_context == context_role:
            return True
    return False


def _assert_acyclic(
    assay_id: str,
    assays_by_id: Mapping[str, Mapping[str, Any]],
    visiting: set[str],
    visited: set[str],
) -> None:
    # Iterative three-color DFS — a deep prerequisite chain must not hit the
    # recursion limit and escape as an unnormalized RecursionError. The stack
    # holds (node, expanded) pairs; an unexpanded node enters `visiting`, an
    # expanded node moves to `visited`.
    stack: list[tuple[str, bool]] = [(assay_id, False)]
    while stack:
        current, expanded = stack.pop()
        if expanded:
            visiting.discard(current)
            visited.add(current)
            continue
        if current in visited:
            continue
        if current in visiting:
            raise SampleStewardshipError(
                f"prerequisite cycle contains {current!r}"
            )
        visiting.add(current)
        stack.append((current, True))
        for prerequisite in assays_by_id[current]["prerequisites"]:
            if prerequisite in visiting:
                raise SampleStewardshipError(
                    f"prerequisite cycle contains {prerequisite!r}"
                )
            if prerequisite not in visited:
                stack.append((prerequisite, False))


def assess_sample_stewardship(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a synthetic staged plan and return non-dominated next assays."""

    record = _mapping(plan, "sample-stewardship plan")
    if set(record) != TOP_LEVEL_FIELDS:
        raise SampleStewardshipError(
            "sample-stewardship plan fields must be exactly "
            + ", ".join(sorted(TOP_LEVEL_FIELDS))
        )
    if record.get("schema") != SCHEMA:
        raise SampleStewardshipError(f"schema must be {SCHEMA!r}")
    if record.get("synthetic_only") is not True:
        raise SampleStewardshipError("public plan must set synthetic_only=true")

    inventory_record = _mapping(record.get("inventory"), "inventory")
    if set(inventory_record) != set(PARTITIONS):
        raise SampleStewardshipError(
            f"inventory must contain exactly {', '.join(PARTITIONS)}"
        )
    inventory = {
        partition: _resource_vector(inventory_record[partition], f"inventory.{partition}")
        for partition in PARTITIONS
    }

    raw_assays = _sequence(record.get("assays"), "assays")
    if not raw_assays:
        raise SampleStewardshipError("assays must not be empty")
    assays_by_id: dict[str, dict[str, Any]] = {}
    contract_hash_by_id: dict[str, str] = {}
    for index, raw_assay in enumerate(raw_assays):
        assay = dict(_mapping(raw_assay, f"assays[{index}]"))
        missing = ASSAY_REQUIRED_FIELDS - set(assay)
        extra = set(assay) - ASSAY_REQUIRED_FIELDS - ASSAY_OPTIONAL_FIELDS
        if missing or extra:
            raise SampleStewardshipError(
                f"assays[{index}] fields are invalid; missing={sorted(missing)}, "
                f"extra={sorted(extra)}"
            )
        assay_id = _opaque_id(assay.get("assay_id"), f"assays[{index}].assay_id")
        if assay_id in assays_by_id:
            raise SampleStewardshipError(f"duplicate assay_id {assay_id!r}")
        stage = assay.get("stage")
        if stage not in STAGES:
            raise SampleStewardshipError(f"{assay_id}.stage must be one of {STAGES}")
        partition = assay.get("partition")
        if partition not in STAGE_PARTITIONS[stage]:
            raise SampleStewardshipError(
                f"{assay_id} stage {stage} cannot consume partition {partition!r}"
            )
        lane = assay.get("discovery_lane")
        if lane not in DISCOVERY_LANES:
            raise SampleStewardshipError(
                f"{assay_id}.discovery_lane must be one of {DISCOVERY_LANES}"
            )
        # Participant-bound partitions cannot be consumed without an explicit
        # consent declaration; a renewable non-participant partition must not
        # carry a participant consent claim.
        consent = assay.get("consent_state")
        if partition in PARTICIPANT_PARTITIONS:
            if consent is None:
                raise SampleStewardshipError(
                    f"{assay_id} consumes {partition} without a declared consent_state"
                )
            if consent not in CONSENT_STATES:
                raise SampleStewardshipError(
                    f"{assay_id}.consent_state must be one of {CONSENT_STATES}"
                )
            if consent != "consented":
                raise SampleStewardshipError(
                    f"{assay_id} cannot consume {partition} while consent_state is {consent!r}"
                )
        elif consent is not None:
            if consent not in CONSENT_STATES:
                raise SampleStewardshipError(
                    f"{assay_id}.consent_state must be one of {CONSENT_STATES}"
                )
            if consent != "not_applicable":
                raise SampleStewardshipError(
                    f"{assay_id} uses the renewable partition; consent_state must be 'not_applicable'"
                )
        assay["consumption"] = _resource_vector(
            assay.get("consumption"), f"{assay_id}.consumption"
        )
        assay["prerequisites"] = _string_set(
            assay.get("prerequisites"), f"{assay_id}.prerequisites"
        )
        assay["decision_changes"] = _string_set(
            assay.get("decision_changes"), f"{assay_id}.decision_changes"
        )
        if not assay["decision_changes"]:
            raise SampleStewardshipError(f"{assay_id}.decision_changes must not be empty")
        assay["validity_requirements"] = _string_set(
            assay.get("validity_requirements"), f"{assay_id}.validity_requirements"
        )
        outcome_actions = dict(
            _mapping(assay.get("outcome_actions"), f"{assay_id}.outcome_actions")
        )
        if set(outcome_actions) != set(OUTCOMES):
            raise SampleStewardshipError(
                f"{assay_id}.outcome_actions must contain exactly {', '.join(OUTCOMES)}"
            )
        for outcome, action in outcome_actions.items():
            if action not in ALLOWED_ACTIONS:
                raise SampleStewardshipError(
                    f"{assay_id}.{outcome} has unsupported action {action!r}"
                )
        assay["outcome_actions"] = outcome_actions
        if outcome_actions["invalid"] != "hold_invalid":
            raise SampleStewardshipError(
                f"{assay_id} invalid results must map to hold_invalid"
            )
        if not isinstance(assay.get("destructive"), bool):
            raise SampleStewardshipError(f"{assay_id}.destructive must be boolean")
        if not _uses_no_more(assay["consumption"], inventory[partition]):
            raise SampleStewardshipError(
                f"{assay_id} exceeds the {partition} resource vector"
            )

        if stage == "A0":
            if assay["prerequisites"]:
                raise SampleStewardshipError(f"{assay_id} A0 must be a root assay")
            if outcome_actions["positive"] != "advance_to_a1":
                raise SampleStewardshipError(f"{assay_id} A0 positive must advance_to_a1")
            if outcome_actions["negative"] not in {
                "reject_condition",
                "revise_mechanism",
                "stop_unsafe",
            }:
                raise SampleStewardshipError(
                    f"{assay_id} A0 results cannot use that negative action"
                )
            missing_a0 = A0_SHARED_VALIDITY_REQUIREMENTS - assay["validity_requirements"]
            if missing_a0:
                raise SampleStewardshipError(
                    f"{assay_id} A0 correction core is missing {sorted(missing_a0)}"
                )
            if lane == "correction_trained_phenotypic":
                missing_phenotype = (
                    A0_PHENOTYPE_VALIDITY_REQUIREMENTS
                    - assay["validity_requirements"]
                )
                if missing_phenotype:
                    raise SampleStewardshipError(
                        f"{assay_id} phenotypic A0 cannot unblind a screen "
                        f"without {sorted(missing_phenotype)}"
                    )
            if "correction_core" not in assay:
                raise SampleStewardshipError(
                    f"{assay_id} A0 must bind opaque correction-core evidence"
                )
            assay["correction_core"] = _correction_core(
                assay["correction_core"],
                f"{assay_id}.correction_core",
                lane,
            )
        elif "correction_core" in assay:
            raise SampleStewardshipError(
                f"{assay_id} correction_core is restricted to A0"
            )
        if stage == "A1":
            if outcome_actions["positive"] != "advance_to_context_qualification":
                raise SampleStewardshipError(
                    f"{assay_id} A1 positive must advance_to_context_qualification"
                )
            if outcome_actions["negative"] != "participant_branch_no_hit":
                raise SampleStewardshipError(
                    f"{assay_id} A1 negative must create participant_branch_no_hit"
                )
            missing_no_hit = A1_NO_HIT_REQUIREMENTS - assay["validity_requirements"]
            if missing_no_hit:
                raise SampleStewardshipError(
                    f"{assay_id} no-hit basis is missing {sorted(missing_no_hit)}"
                )
            if "a1_lock" not in assay:
                raise SampleStewardshipError(
                    f"{assay_id} A1 must bind opaque bridge evidence"
                )
            assay["a1_lock"] = _a1_lock(assay["a1_lock"], f"{assay_id}.a1_lock")
        elif "a1_lock" in assay:
            raise SampleStewardshipError(
                f"{assay_id} a1_lock is restricted to A1"
            )

        context = None
        if "context_qualification" in assay:
            context = _context_qualification(
                assay["context_qualification"], f"{assay_id}.context_qualification"
            )
            assay["context_qualification"] = context
        if stage == "TIER_B" and context is not None:
            if outcome_actions["positive"] != "advance_to_native_lineage":
                raise SampleStewardshipError(
                    f"{assay_id} context positive must advance_to_native_lineage"
                )
            if outcome_actions["negative"] != "record_mechanism_only":
                raise SampleStewardshipError(
                    f"{assay_id} context negative must record_mechanism_only"
                )
            missing_shared = (
                CONTEXT_SHARED_VALIDITY_REQUIREMENTS
                - assay["validity_requirements"]
            )
            if missing_shared:
                raise SampleStewardshipError(
                    f"{assay_id} context qualification is missing "
                    f"{sorted(missing_shared)}"
                )
            mitotic_class = context["mitotic_context_class"]
            if mitotic_class == "epithelial_architecture_dependent":
                required_extra = "architecture_preserving_context"
                forbidden_extra = "lineage_intrinsic_mitotic_context"
            else:
                required_extra = "lineage_intrinsic_mitotic_context"
                forbidden_extra = "architecture_preserving_context"
            if required_extra not in assay["validity_requirements"]:
                raise SampleStewardshipError(
                    f"{assay_id} context qualification is missing "
                    f"{sorted([required_extra])}"
                )
            if forbidden_extra in assay["validity_requirements"]:
                raise SampleStewardshipError(
                    f"{assay_id} mitotic_context_class {mitotic_class} cannot "
                    f"declare {forbidden_extra}"
                )
            if "lineage_lock" in assay:
                raise SampleStewardshipError(
                    f"{assay_id} lineage_lock is restricted to native-lineage"
                )
        elif context is not None:
            raise SampleStewardshipError(
                f"{assay_id} context_qualification is restricted to Tier B"
            )
        elif stage == "TIER_B":
            if outcome_actions["positive"] != "held_out_confirmation":
                raise SampleStewardshipError(
                    f"{assay_id} native-lineage positive must enter held_out_confirmation"
                )
            if outcome_actions["negative"] != "reject_condition":
                raise SampleStewardshipError(
                    f"{assay_id} native-lineage negative must reject_condition"
                )
            missing_lineage = NATIVE_LINEAGE_REQUIREMENTS - assay["validity_requirements"]
            if missing_lineage:
                raise SampleStewardshipError(
                    f"{assay_id} native-lineage contract is missing "
                    f"{sorted(missing_lineage)}"
                )
            if "lineage_lock" not in assay:
                raise SampleStewardshipError(
                    f"{assay_id} native-lineage work must bind opaque lineage evidence"
                )
            assay["lineage_lock"] = _lineage_lock(
                assay["lineage_lock"],
                f"{assay_id}.lineage_lock",
            )
        elif "lineage_lock" in assay:
            raise SampleStewardshipError(
                f"{assay_id} lineage_lock is restricted to native-lineage"
            )
        if stage == "HELD_OUT":
            if outcome_actions["positive"] != "independent_replication":
                raise SampleStewardshipError(
                    f"{assay_id} held-out positive must enter independent_replication"
                )
            if outcome_actions["negative"] != "reject_condition":
                raise SampleStewardshipError(
                    f"{assay_id} held-out negative must reject_condition"
                )
            missing_held_out = (
                HELD_OUT_VALIDITY_REQUIREMENTS - assay["validity_requirements"]
            )
            if missing_held_out:
                raise SampleStewardshipError(
                    f"{assay_id} held-out contract is missing {sorted(missing_held_out)}"
                )
            if "held_out_lock" not in assay:
                raise SampleStewardshipError(
                    f"{assay_id} HELD_OUT must bind opaque freeze and blinding evidence"
                )
            assay["held_out_lock"] = _held_out_lock(
                assay["held_out_lock"],
                f"{assay_id}.held_out_lock",
            )
        elif "held_out_lock" in assay:
            raise SampleStewardshipError(
                f"{assay_id} held_out_lock is restricted to held-out"
            )

        if stage == "REPLICATION":
            independence = _string_set(
                assay.get("independence_requirements"),
                f"{assay_id}.independence_requirements",
            )
            missing_replication = REPLICATION_REQUIREMENTS - independence
            if missing_replication:
                raise SampleStewardshipError(
                    f"{assay_id} replication is missing {sorted(missing_replication)}"
                )
            assay["independence_requirements"] = independence
            if "replication_lock" not in assay:
                raise SampleStewardshipError(
                    f"{assay_id} REPLICATION must bind opaque freeze and transfer evidence"
                )
            assay["replication_lock"] = _replication_lock(
                assay["replication_lock"],
                f"{assay_id}.replication_lock",
            )
            if outcome_actions["positive"] != "independent_replication":
                raise SampleStewardshipError(
                    f"{assay_id} replication positive must record independent_replication"
                )
            if outcome_actions["negative"] != "reject_condition":
                raise SampleStewardshipError(
                    f"{assay_id} replication negative must reject_condition"
                )
        elif "independence_requirements" in assay:
            raise SampleStewardshipError(
                f"{assay_id}.independence_requirements is restricted to replication"
            )
        elif "replication_lock" in assay:
            raise SampleStewardshipError(
                f"{assay_id} replication_lock is restricted to replication"
            )

        assays_by_id[assay_id] = assay
        contract_hash_by_id[assay_id] = assay_contract_sha256(assay)

    seen_evidence_ids: dict[str, str] = {}
    for assay_id, assay in assays_by_id.items():
        core = assay.get("correction_core")
        if isinstance(core, dict):
            for identifier in core.values():
                previous = seen_evidence_ids.get(identifier)
                if previous is not None:
                    raise SampleStewardshipError(
                        f"{assay_id} correction_core reuses {identifier!r} "
                        f"from {previous}"
                    )
                seen_evidence_ids[identifier] = assay_id
        lock = assay.get("a1_lock")
        if isinstance(lock, dict):
            for identifier in lock.values():
                previous = seen_evidence_ids.get(identifier)
                if previous is not None:
                    raise SampleStewardshipError(
                        f"{assay_id} a1_lock reuses {identifier!r} from {previous}"
                    )
                seen_evidence_ids[identifier] = f"{assay_id}.a1_lock"
        context = assay.get("context_qualification")
        if isinstance(context, dict):
            for field in CONTEXT_ID_FIELDS:
                identifier = context[field]
                previous = seen_evidence_ids.get(identifier)
                if previous is not None:
                    raise SampleStewardshipError(
                        f"{assay_id} context_qualification reuses "
                        f"{identifier!r} from {previous}"
                    )
                seen_evidence_ids[identifier] = f"{assay_id}.context_qualification"
        lock = assay.get("held_out_lock")
        if isinstance(lock, dict):
            _register_lock_ids(
                assay_id,
                assay,
                lock,
                "held_out_lock",
                seen_evidence_ids,
                assays_by_id,
            )
        lock = assay.get("replication_lock")
        if isinstance(lock, dict):
            _register_lock_ids(
                assay_id,
                assay,
                lock,
                "replication_lock",
                seen_evidence_ids,
                assays_by_id,
            )
        lock = assay.get("lineage_lock")
        if isinstance(lock, dict):
            for identifier in lock.values():
                previous = seen_evidence_ids.get(identifier)
                if previous is not None:
                    raise SampleStewardshipError(
                        f"{assay_id} lineage_lock reuses {identifier!r} from {previous}"
                    )
                seen_evidence_ids[identifier] = f"{assay_id}.lineage_lock"

    _assert_held_out_replication_estimand_equivalence(assays_by_id)

    for assay_id, assay in assays_by_id.items():
        unknown = assay["prerequisites"] - set(assays_by_id)
        if unknown:
            raise SampleStewardshipError(
                f"{assay_id} has unknown prerequisites {sorted(unknown)}"
            )
        if assay_id in assay["prerequisites"]:
            raise SampleStewardshipError(f"{assay_id} cannot require itself")
        wrong_lane = [
            prerequisite
            for prerequisite in sorted(assay["prerequisites"])
            if assays_by_id[prerequisite]["discovery_lane"]
            != assay["discovery_lane"]
        ]
        if wrong_lane:
            raise SampleStewardshipError(
                f"{assay_id} crosses discovery lanes through {wrong_lane}"
            )
    visited: set[str] = set()
    for assay_id in assays_by_id:
        _assert_acyclic(assay_id, assays_by_id, set(), visited)
    children = _children_map(assays_by_id)
    for assay_id, assay in assays_by_id.items():
        stage = assay["stage"]
        if stage == "A1" and not _has_direct_role_prerequisite(
            assay_id, "A0", assays_by_id
        ):
            raise SampleStewardshipError(
                f"{assay_id} A1 requires a direct A0 predecessor"
            )
        if stage == "A1":
            lineage_descendants = [
                child
                for child in _descendants(assay_id, children)
                if _is_native_lineage(assays_by_id[child])
                and assays_by_id[child]["discovery_lane"] == assay["discovery_lane"]
            ]
            if not lineage_descendants:
                raise SampleStewardshipError(
                    f"{assay_id} A1 requires a native-lineage successor"
                )
        if (
            stage == "TIER_B"
            and assay.get("context_qualification") is not None
            and not _has_direct_role_prerequisite(assay_id, "A1", assays_by_id)
        ):
            raise SampleStewardshipError(
                f"{assay_id} Tier-B context requires a direct A1 predecessor"
            )
        if (
            stage == "TIER_B"
            and assay.get("context_qualification") is None
            and not _has_direct_role_prerequisite(
                assay_id, "TIER_B", assays_by_id, context_role=True
            )
        ):
            raise SampleStewardshipError(
                f"{assay_id} native-lineage work requires a direct "
                "context-qualified predecessor"
            )
        if stage == "HELD_OUT" and not _has_direct_role_prerequisite(
            assay_id, "TIER_B", assays_by_id, context_role=False
        ):
            raise SampleStewardshipError(
                f"{assay_id} held-out work requires a direct native-lineage "
                "predecessor"
            )
        if stage == "REPLICATION" and not _has_direct_role_prerequisite(
            assay_id, "HELD_OUT", assays_by_id
        ):
            raise SampleStewardshipError(
                f"{assay_id} replication requires a direct held-out predecessor"
            )

    completed_record = _mapping(record.get("completed"), "completed")
    unknown_completed = set(completed_record) - set(assays_by_id)
    if unknown_completed:
        raise SampleStewardshipError(
            f"completed has unknown assay ids {sorted(unknown_completed)}"
        )
    spent = {
        partition: {axis: 0 for axis in RESOURCE_AXES} for partition in PARTITIONS
    }
    completed_outcomes: dict[str, str] = {}
    completed_receipt_ids: dict[str, str] = {}
    seen_receipt_ids: set[str] = set()
    for assay_id, raw_receipt in completed_record.items():
        receipt = dict(_mapping(raw_receipt, f"completed.{assay_id}"))
        missing_receipt = COMPLETION_RECEIPT_REQUIRED_FIELDS - set(receipt)
        extra_receipt = (
            set(receipt)
            - COMPLETION_RECEIPT_REQUIRED_FIELDS
            - COMPLETION_RECEIPT_OPTIONAL_FIELDS
        )
        if missing_receipt or extra_receipt:
            raise SampleStewardshipError(
                f"completed.{assay_id} must be an immutable structured receipt"
            )
        receipt_id = _opaque_id(
            receipt.get("receipt_id"),
            f"completed.{assay_id}.receipt_id",
            completion=True,
        )
        if receipt_id in seen_receipt_ids:
            raise SampleStewardshipError(f"duplicate completion receipt_id {receipt_id!r}")
        seen_receipt_ids.add(receipt_id)
        outcome = receipt.get("outcome")
        if outcome not in OUTCOMES:
            raise SampleStewardshipError(
                f"completed.{assay_id}.outcome must be one of {OUTCOMES}"
            )
        assay = assays_by_id[assay_id]
        if receipt.get("assay_contract_sha256") != contract_hash_by_id[assay_id]:
            raise SampleStewardshipError(
                f"completed.{assay_id} assay contract digest mismatch"
            )
        if receipt.get("partition") != assay["partition"]:
            raise SampleStewardshipError(
                f"completed.{assay_id} partition does not match assay contract"
            )
        debit = _resource_vector(
            receipt.get("resource_debit"), f"completed.{assay_id}.resource_debit"
        )
        if debit != assay["consumption"]:
            raise SampleStewardshipError(
                f"completed.{assay_id} resource debit must equal assay consumption"
            )
        expected_action = assay["outcome_actions"][outcome]
        if receipt.get("outcome_action") != expected_action:
            raise SampleStewardshipError(
                f"completed.{assay_id} outcome action does not match assay contract"
            )
        requires_promotion = assay["stage"] == "REPLICATION" and outcome == "positive"
        if requires_promotion:
            if "promotion_evidence" not in receipt:
                raise SampleStewardshipError(
                    f"completed.{assay_id} positive replication requires "
                    "promotion_evidence"
                )
            receipt["promotion_evidence"] = _promotion_evidence(
                receipt["promotion_evidence"],
                f"completed.{assay_id}.promotion_evidence",
            )
            promotion = receipt["promotion_evidence"]
            for field in ("discovery_site_id", "replication_site_id"):
                identifier = promotion[field]
                previous = seen_evidence_ids.get(identifier)
                if previous is not None:
                    raise SampleStewardshipError(
                        f"{assay_id} promotion_evidence reuses {identifier!r} "
                        f"from {previous}"
                    )
                seen_evidence_ids[identifier] = (
                    f"{assay_id}.promotion_evidence.{field}"
                )
            for field in (
                "discovery_event_family_ids",
                "replication_event_family_ids",
            ):
                for identifier in promotion[field]:
                    previous = seen_evidence_ids.get(identifier)
                    if previous is not None:
                        raise SampleStewardshipError(
                            f"{assay_id} promotion_evidence reuses "
                            f"{identifier!r} from {previous}"
                        )
                    seen_evidence_ids[identifier] = (
                        f"{assay_id}.promotion_evidence.{field}"
                    )
            blinding_id = promotion["site2_blinding_id"]
            previous = seen_evidence_ids.get(blinding_id)
            if previous is not None:
                raise SampleStewardshipError(
                    f"{assay_id} promotion_evidence reuses {blinding_id!r} "
                    f"from {previous}"
                )
            seen_evidence_ids[blinding_id] = (
                f"{assay_id}.promotion_evidence.site2_blinding_id"
            )
            for field, label in (
                ("analytic_transfer_result_sha256", "analytic transfer"),
                ("site2_blinding_evidence_sha256", "site-2 blinding evidence"),
            ):
                fingerprint = promotion[field]
                if fingerprint in set(contract_hash_by_id.values()):
                    raise SampleStewardshipError(
                        f"{assay_id} {label} cannot be an assay-contract digest"
                    )
                previous = seen_evidence_ids.get(fingerprint)
                if previous is not None:
                    raise SampleStewardshipError(
                        f"{assay_id} promotion_evidence reuses {fingerprint!r} "
                        f"from {previous}"
                    )
                seen_evidence_ids[fingerprint] = (
                    f"{assay_id}.promotion_evidence.{field}"
                )
        elif "promotion_evidence" in receipt:
            raise SampleStewardshipError(
                f"completed.{assay_id} promotion_evidence is not allowed"
            )
        receipt_digest = receipt.get("receipt_sha256")
        if (
            not isinstance(receipt_digest, str)
            or SHA256_PATTERN.fullmatch(receipt_digest) is None
            or receipt_digest != completion_receipt_sha256(receipt)
        ):
            raise SampleStewardshipError(
                f"completed.{assay_id} completion receipt digest mismatch"
            )
        partition = assay["partition"]
        for axis in RESOURCE_AXES:
            spent[partition][axis] += debit[axis]
            if spent[partition][axis] > inventory[partition][axis]:
                raise SampleStewardshipError(
                    f"completed assays cumulatively exceed {partition}.{axis}"
                )
        completed_outcomes[assay_id] = outcome
        completed_receipt_ids[assay_id] = receipt_id

    for assay_id in completed_outcomes:
        unmet_history = [
            parent
            for parent in sorted(assays_by_id[assay_id]["prerequisites"])
            if completed_outcomes.get(parent) != "positive"
        ]
        if unmet_history:
            raise SampleStewardshipError(
                f"completed.{assay_id} skips prerequisites {unmet_history}"
            )

    remaining = {
        partition: {
            axis: inventory[partition][axis] - spent[partition][axis]
            for axis in RESOURCE_AXES
        }
        for partition in PARTITIONS
    }
    eligible: list[dict[str, Any]] = []
    blocked: dict[str, list[str]] = {}
    resource_blocked: dict[str, list[str]] = {}
    for assay_id, assay in assays_by_id.items():
        if assay_id in completed_outcomes:
            continue
        unmet = [
            parent
            for parent in sorted(assay["prerequisites"])
            if completed_outcomes.get(parent) != "positive"
        ]
        if unmet:
            blocked[assay_id] = unmet
            continue
        unavailable = [
            axis
            for axis in RESOURCE_AXES
            if assay["consumption"][axis] > remaining[assay["partition"]][axis]
        ]
        if unavailable:
            resource_blocked[assay_id] = unavailable
            continue
        eligible.append(assay)

    eligible_a1 = [assay for assay in eligible if assay["stage"] == "A1"]
    eligible = [assay for assay in eligible if assay["stage"] != "A1"]
    reserved_used = {
        partition: {axis: 0 for axis in RESOURCE_AXES} for partition in PARTITIONS
    }
    for assay in sorted(eligible_a1, key=_a1_priority):
        reserved = _a1_discovery_reservation(
            assay, assays_by_id, children, completed_outcomes
        )
        partition = assay["partition"]
        overflow = [
            axis
            for axis in RESOURCE_AXES
            if reserved_used[partition][axis] + reserved[axis]
            > remaining[partition][axis]
        ]
        if overflow:
            resource_blocked[assay["assay_id"]] = overflow
            continue
        for axis in RESOURCE_AXES:
            reserved_used[partition][axis] += reserved[axis]
        eligible.append(assay)

    nondominated: list[str] = []
    for assay in eligible:
        dominated = False
        for challenger in eligible:
            if challenger["assay_id"] == assay["assay_id"]:
                continue
            if (
                challenger["stage"] != assay["stage"]
                or challenger["decision_changes"] != assay["decision_changes"]
                or challenger["partition"] != assay["partition"]
                or challenger["discovery_lane"] != assay["discovery_lane"]
            ):
                continue
            no_more_resource = _uses_no_more(
                challenger["consumption"], assay["consumption"]
            )
            no_more_destructive = not challenger["destructive"] or assay["destructive"]
            covers_actions = challenger["decision_changes"] >= assay["decision_changes"]
            strictly_better = (
                _strictly_better_resource(
                    challenger["consumption"], assay["consumption"]
                )
                or (not challenger["destructive"] and assay["destructive"])
                or challenger["decision_changes"] > assay["decision_changes"]
            )
            if no_more_resource and no_more_destructive and covers_actions and strictly_better:
                dominated = True
                break
        if not dominated:
            nondominated.append(assay["assay_id"])

    return {
        "schema": RESULT_SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "selection_rule": "vector_dominance_not_scalar_voi",
        "eligible_ids": sorted(assay["assay_id"] for assay in eligible),
        "nondominated_ids": sorted(nondominated),
        "blocked_by": {key: blocked[key] for key in sorted(blocked)},
        "resource_blocked": {
            key: resource_blocked[key] for key in sorted(resource_blocked)
        },
        "completed_receipt_ids": {
            key: completed_receipt_ids[key] for key in sorted(completed_receipt_ids)
        },
        "spent_inventory": spent,
        "remaining_inventory": remaining,
        "participant_reserves_segregated": True,
        "completion_receipts_bound": True,
        "cumulative_debits_enforced": True,
        "lane_paths_separate": True,
        "a0_correction_core_required": True,
        "a0_correction_core_evidence_bound": True,
        "a1_lineage_reservation_enforced": True,
        "a1_bridge_identities_bound": True,
        "context_evidence_identities_bound": True,
        "held_out_freeze_and_blinding_bound": True,
        "replication_independence_identities_bound": True,
        "replication_site_identities_bound": True,
        "replication_event_family_identities_bound": True,
        "analytic_transfer_fingerprint_bound": True,
        "analytic_transfer_excludes_all_assay_contracts": True,
        "replication_site2_blinding_identity_bound": True,
        "replication_site2_blinding_evidence_bound": True,
        "held_out_replication_estimand_equivalence_bound": True,
        "held_out_replication_exposure_equivalence_bound": True,
        "native_lineage_identities_bound": True,
        "context_qualification_required": True,
        "replication_promotion_evidence_bound": True,
        "invalid_results_hold": True,
    }


__all__ = [
    "A0_PHENOTYPE_EVIDENCE_FIELDS",
    "A0_PHENOTYPE_VALIDITY_REQUIREMENTS",
    "A0_SHARED_EVIDENCE_FIELDS",
    "A0_SHARED_VALIDITY_REQUIREMENTS",
    "A1_EVIDENCE_FIELDS",
    "A1_NO_HIT_REQUIREMENTS",
    "HELD_OUT_EVIDENCE_FIELDS",
    "HELD_OUT_VALIDITY_REQUIREMENTS",
    "REPLICATION_EVIDENCE_FIELDS",
    "CLAIM_BOUNDARY",
    "CONTEXT_ID_FIELDS",
    "CONTEXT_VALIDITY_REQUIREMENTS",
    "LINEAGE_INTRINSIC_VALIDITY_REQUIREMENTS",
    "NATIVE_LINEAGE_EVIDENCE_FIELDS",
    "NATIVE_LINEAGE_REQUIREMENTS",
    "MITOTIC_CONTEXT_CLASSES",
    "TRANSFORMATION_STATES",
    "DISCOVERY_LANES",
    "PARTITIONS",
    "REPLICATION_REQUIREMENTS",
    "SHARED_HELD_OUT_REPLICATION_FIELDS",
    "RESOURCE_AXES",
    "RESULT_SCHEMA",
    "SCHEMA",
    "STAGES",
    "SampleStewardshipError",
    "assay_contract_sha256",
    "assess_sample_stewardship",
    "completion_receipt_sha256",
    "make_completion_receipt",
]
