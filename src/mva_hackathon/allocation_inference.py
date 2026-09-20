"""Conditional Fisher randomization inference for a committed allocation.

This module deliberately sits after the pre-exposure allocation validator.  It
uses biological-pair contrasts as analysis units, reconstructs the finite set of
arm-label vectors allowed by the arm-blind manifest, replays the committed
selection, and evaluates two predeclared error-rate endpoints over that exact
set.  It does not attest the origin of the revealed seed or establish efficacy.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .arm_allocation import assess_preexposure_allocation

try:
    from .arm_allocation import (
        ALLOCATION_ANALYSIS_PLAN,
        SeedModuloBiasRejection,
        enumerate_admissible_assignment_vectors,
        make_allocation_analysis_plan_sha256,
        make_seed_commitment,
        rejection_sampled_candidate_index,
    )
except ImportError:  # The older allocation contract must fail closed, not crash.
    ALLOCATION_ANALYSIS_PLAN = None
    SeedModuloBiasRejection = None
    enumerate_admissible_assignment_vectors = None
    make_allocation_analysis_plan_sha256 = None
    make_seed_commitment = None
    rejection_sampled_candidate_index = None


SCHEMA = "mva-track2-constrained-randomization-inference/v2"
TABLE_SCHEMA = "mva.community-measured-exposure-table/v1"
LINEAGE_SCHEMA = "mva-track2-lineage-counts/v1"
MANIFEST_SCHEMA = "mva-track2-arm-blind-assignment-manifest/v1"
GENERATOR = "seed_uint256_rejection_index_v1"
MIN_PAIRS_PER_CONTEXT = 6
MIN_ASSIGNMENT_SPACE = 64
MAX_ASSIGNMENT_SPACE = 1_000_000
MIN_ARM_INFORMATION_RATIO = 0.75
ALPHA = 0.05
# The declared biological_replication_unit is clone_edit_event — a single
# (edit_event_id, clone_id) unit may not supply more than half of the pairs,
# and at least two distinct units must be present, or the declared unit is
# not actually replicated.
MIN_BIOLOGICAL_UNITS = 2
MAX_CLONE_PAIR_SHARE = 0.5
CLAIM_BOUNDARY = (
    "Conditional Fisher randomization test over the distinct declared, replayed, "
    "prespecified information-filtered admissible arm-label vectors selected by "
    "an exact uint256 rejection-sampled index. Exactness "
    "is for the global sharp null only, not the weak null of zero average effect. "
    "The observed equal-pair-weighted difference is a reported contrast. The "
    "software does not attest the uniform pre-outcome draw, causal assumptions, "
    "entropy source, physical execution, biological rescue, efficacy, or clinical "
    "use."
)
_EXPECTED_INFERENCE_PLAN = {
    "treatment_application_unit": "functional_execution_well",
    "randomization_unit": "biological_pair",
    "analysis_unit": "biological_pair",
    "biological_replication_unit": "clone_edit_event",
    "endpoints": [
        {
            "endpoint_id": "error_per_detected_division",
            "numerator": "event_positive_divisions",
            "denominator": "detected_divisions",
        },
        {
            "endpoint_id": "error_per_enrolled_founder",
            "numerator": "event_positive_divisions",
            "denominator": "opportunities",
        },
    ],
    "reported_contrast": (
        "mean_within_pair_treatment_minus_vehicle_observed_rate_difference"
    ),
    "tested_null": "global_fisher_sharp_null_no_effect_on_any_execution",
    "tested_null_statement": (
        "for_every_functional_execution_the_treatment_and_vehicle_"
        "potential_outcomes_are_identical"
    ),
    "p_value_scope": (
        "exact_for_the_global_fisher_sharp_null_not_a_weak_average_null"
    ),
    "assignment_probability_model": (
        "exact_uniform_over_canonical_information_filtered_support_"
        "conditional_on_uint256_rejection_acceptance"
    ),
    "causal_interpretation_assumptions": [
        "genuine_preoutcome_seed_draw_from_the_declared_uniform_model",
        "consistency_and_single_version_of_each_arm",
        "no_interference_carryover_or_cross_well_contamination",
        "fixed_manifest_with_no_postassignment_exclusion",
        "arm_blinded_outcome_ascertainment",
    ],
    "assumptions_satisfied": "not_software_attested",
    "nuisance_residualization": {
        "method": "fixed_unit_level_ols",
        "intercept": True,
        "context_coding": "k_minus_1_lexicographic_reference",
        "context_reference": "lexicographically_first_context",
        "centering": {
            "dosing_order": (
                "arithmetic_mean_within_plate_batch_run_event_context"
            ),
            "acquisition_order": (
                "arithmetic_mean_within_plate_batch_run_event_context"
            ),
        },
        "covariates": [
            "context_indicators",
            "context_interacted_within_context_centered_dosing_order",
            "context_interacted_squared_within_context_centered_dosing_order",
            "context_interacted_within_context_centered_acquisition_order",
            "context_interacted_squared_within_context_centered_acquisition_order",
            "context_interacted_centered_dosing_times_centered_acquisition",
        ],
        "context_interactions": {
            "context_order": "lexicographic_plate_batch_run_event",
            "outside_context_value": 0.0,
            "coefficient_sharing": "none_across_contexts",
            "column_order": "context_major_then_declared_covariate_order",
            "columns_per_context": [
                "within_context_centered_dosing_order",
                "squared_within_context_centered_dosing_order",
                "within_context_centered_acquisition_order",
                "squared_within_context_centered_acquisition_order",
                "centered_dosing_times_centered_acquisition",
            ],
            "design_width": "6_times_number_of_contexts",
            "observations_at_six_pairs_per_context": (
                "12_times_number_of_contexts"
            ),
        },
        "outcome_fit": "once_per_endpoint_without_arm_before_enumeration",
        "assignment_dependent_refit": False,
        "residual_definition": "outcome_minus_fitted_value",
        "solver": {
            "algorithm": "modified_gram_schmidt_two_pass_qr",
            "summation_algorithm": "explicit_left_to_right_binary64_v1",
            "column_pivoting": False,
            "rank_rule": (
                "residual_column_norm_lte_1e-10_times_max_1_"
                "original_column_norm_is_rank_deficient"
            ),
            "coefficient_solve": "upper_triangular_back_substitution",
        },
    },
    "statistic": {
        "unit_contrast": "residual_treatment_minus_vehicle",
        "aggregation": "arithmetic_mean_over_biological_pairs",
        "pair_weighting": "equal",
    },
    "randomization_test": {
        "alternative": "lower",
        "tail_rule": "candidate_statistic_lte_observed_plus_tolerance",
        "tolerance_rule": "1e-12_times_max_1_abs_observed_statistic",
        "alpha": ALPHA,
        "minimum_support_size": MIN_ASSIGNMENT_SPACE,
        "observed_assignment_included": True,
    },
    "direction_rule": "observed_raw_mean_difference_lt_zero",
    "joint_decision_rule": "both_endpoints_must_pass",
    "missing_data": "no_imputation",
    "rank_deficient_design": "not_assessable",
}
_EXPECTED_ALLOCATION_INFORMATION_FILTER = {
    "scope": "each_context_candidate",
    "timing": (
        "after_hard_constraints_before_context_cartesian_product_and_"
        "seed_index_selection"
    ),
    "row_order": "functional_execution_id_lexicographic_within_context",
    "arm_indicator": {
        "treatment": 1.0,
        "vehicle": -1.0,
        "centering": "arithmetic_mean_within_context",
    },
    "nuisance_design_columns": [
        "intercept",
        "within_context_centered_dosing_order",
        "squared_within_context_centered_dosing_order",
        "within_context_centered_acquisition_order",
        "squared_within_context_centered_acquisition_order",
        "centered_dosing_times_centered_acquisition",
    ],
    "coefficient_sharing": "none_across_contexts",
    "solver": {
        "algorithm": "modified_gram_schmidt_two_pass_qr",
        "column_pivoting": False,
        "summation_algorithm": "explicit_left_to_right_binary64_v1",
        "rank_rule": (
            "residual_column_norm_lte_1e-10_times_max_1_"
            "original_column_norm_is_rank_deficient"
        ),
        "residual_projection": (
            "centered_arm_indicator_minus_q_times_q_transpose_centered_"
            "arm_indicator"
        ),
        "numeric_arithmetic": "ieee_754_binary64",
        "dot_product_order": "declared_row_order",
    },
    "information_ratio": (
        "squared_euclidean_norm_residualized_centered_arm_indicator_"
        "divided_by_squared_euclidean_norm_centered_arm_indicator"
    ),
    "minimum_information_ratio": MIN_ARM_INFORMATION_RATIO,
    "equivalent_max_variance_inflation_factor": "4_over_3",
    "equivalent_max_standard_error_inflation": "sqrt_4_over_3",
    "acceptance_rule": (
        "residual_norm_squared_plus_tolerance_gte_0.75_times_raw_"
        "centered_norm_squared"
    ),
    "tolerance_rule": "1e-12_times_max_1_raw_centered_arm_norm_squared",
    "rank_deficient_context": "fail_closed",
    "local_survivors": (
        "all_distinct_candidates_passing_hard_constraints_and_"
        "information_rule"
    ),
    "joint_support_count": "product_of_local_survivor_counts",
    "minimum_joint_support_size": MIN_ASSIGNMENT_SPACE,
    "insufficient_joint_support": "fail_closed_before_seed_index_selection",
}
_EXPECTED_ENUMERATION_SAFETY = {
    "required_pair_count_parity_within_context": "even",
    "context_candidate_generation": (
        "lexicographic_combinations_of_exactly_half_the_pair_ids_with_"
        "dosing_later_member_as_treatment"
    ),
    "raw_local_candidate_count": "binomial_n_choose_n_over_2",
    "prospective_joint_upper_bound": "product_of_raw_local_candidate_counts",
    "maximum_candidate_vectors": MAX_ASSIGNMENT_SPACE,
    "bound_check_timing": "before_candidate_generation",
    "bound_exceeded": "fail_closed",
}

_MANIFEST_KEYS = frozenset({"schema", "plate_dimensions", "pair_units"})
_PAIR_KEYS = frozenset({"pair_id", "members"})
_MEMBER_KEYS = frozenset(
    {
        "functional_execution_id",
        "edit_event_id",
        "clone_id",
        "culture_batch_id",
        "functional_assay_run_id",
        "allocation_block_id",
        "functional_assay_plate_id",
        "plate_row",
        "plate_column",
        "dosing_order",
        "acquisition_order",
    }
)
_PLATE_KEYS = frozenset({"functional_assay_plate_id", "n_rows", "n_columns"})
_RANDOMIZATION_KEYS = frozenset(
    {
        "generator",
        "seed_commitment_sha256",
        "seed_commitment_record",
        "seed_committed_at",
        "seed_reveal_hex",
        "seed_revealed_at",
        "entropy_authenticity",
        "record",
        "admissible_space_count",
        "admissible_space_sha256",
        "selected_vector_sha256",
    }
)
_RECORD_KEYS = frozenset({"mechanism", "record_id", "recorded_at"})
_COMMITMENT_RECORD_KEYS = frozenset(
    {"mechanism", "record_id", "recorded_at", "digest_sha256"}
)
_ASSIGNMENT_FIELDS = (
    "edit_event_id",
    "clone_id",
    "culture_batch_id",
    "functional_assay_run_id",
    "allocation_block_id",
    "functional_assay_plate_id",
    "plate_row",
    "plate_column",
    "dosing_order",
    "acquisition_order",
)
_LINEAGE_FIELDS = {
    "edit_event_id": "edit_event_id",
    "clone_id": "clone_id",
    "culture_batch_id": "batch_id",
    "functional_assay_run_id": "run_id",
    "allocation_block_id": "allocation_block_id",
    "functional_assay_plate_id": "functional_assay_plate_id",
    "plate_row": "plate_row",
    "plate_column": "plate_column",
    "dosing_order": "dosing_order",
    "acquisition_order": "acquisition_order",
}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class AllocationInferenceError(ValueError):
    """Internal fail-closed signal carrying a stable public reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason


@dataclass(frozen=True)
class _Member:
    execution_id: str
    event_id: str
    clone_id: str
    batch_id: str
    run_id: str
    block_id: str
    plate_id: str
    plate_row: int
    plate_column: int
    dosing_order: int
    acquisition_order: int


@dataclass(frozen=True)
class _Pair:
    pair_id: str
    members: tuple[_Member, _Member]

    @property
    def context(self) -> tuple[str, str, str, str]:
        member = self.members[0]
        return (member.plate_id, member.batch_id, member.run_id, member.event_id)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = item
    return result


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON float {value!r} is not allowed")
    return parsed


def _strict_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except RecursionError as exc:
        raise AllocationInferenceError(
            "allocation_contract_malformed",
            "allocation JSON is nested too deeply",
        ) from exc


def _left_to_right_binary64_sum(values: Iterable[float]) -> float:
    """Use the reduction order frozen in the allocation-analysis plan."""

    total = 0.0
    for value in values:
        total += float(value)
    return total


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], field: str) -> None:
    if set(value) != expected:
        raise AllocationInferenceError(
            "allocation_contract_malformed",
            f"{field} keys do not match the constrained-allocation contract",
        )


def _identifier(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or not value[0].isalpha()
        or not value.replace("-", "").replace("_", "").replace(".", "").isalnum()
    ):
        raise AllocationInferenceError(
            "allocation_contract_malformed", f"{field} is not a valid identifier"
        )
    return value


_ARM_LABEL_SUBSTRINGS = ("vehicle", "treatment", "control", "drug")


def _member_identifier(value: object, field: str) -> str:
    result = _identifier(value, field)
    lowered = result.lower()
    if any(token in lowered for token in _ARM_LABEL_SUBSTRINGS):
        raise AllocationInferenceError(
            "allocation_contract_malformed",
            f"{field} must not contain an arm label",
        )
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AllocationInferenceError(
            "allocation_contract_malformed", f"{field} must be a positive integer"
        )
    return value


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AllocationInferenceError(
            "endpoint_data_malformed", f"{field} must be a non-negative integer"
        )
    return value


def _sha256(value: object, field: str, *, reason: str = "allocation_contract_malformed") -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise AllocationInferenceError(reason, f"{field} must be a lowercase SHA-256")
    return value


def _base_result(
    *,
    status: str,
    reason: str,
    detail: str,
    synthetic_only: bool,
    n_contexts: int = 0,
    n_pairs: int = 0,
    pairs_per_context: Mapping[str, int] | None = None,
    n_admissible: int = 0,
    selected_verified: bool = False,
    conditional_software_contract_verified: bool = False,
    authenticated_randomization_verified: bool = False,
    analysis_plan_sha256: str | None = None,
    endpoints: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    passed = status == "pass"
    return {
        "schema": SCHEMA,
        "synthetic_only": synthetic_only,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": "pass" if passed else ("stop" if status == "stop" else "hold"),
        "reason": reason,
        "detail": detail,
        "advancement_blocked": not passed,
        "treatment_application_unit": _EXPECTED_INFERENCE_PLAN[
            "treatment_application_unit"
        ],
        "randomization_unit": _EXPECTED_INFERENCE_PLAN["randomization_unit"],
        "analysis_unit": _EXPECTED_INFERENCE_PLAN["analysis_unit"],
        "biological_replication_unit": _EXPECTED_INFERENCE_PLAN[
            "biological_replication_unit"
        ],
        "reported_contrast": _EXPECTED_INFERENCE_PLAN["reported_contrast"],
        "tested_null": _EXPECTED_INFERENCE_PLAN["tested_null"],
        "tested_null_statement": _EXPECTED_INFERENCE_PLAN[
            "tested_null_statement"
        ],
        "p_value_scope": _EXPECTED_INFERENCE_PLAN["p_value_scope"],
        "assignment_probability_model": _EXPECTED_INFERENCE_PLAN[
            "assignment_probability_model"
        ],
        "causal_interpretation_assumptions": list(
            _EXPECTED_INFERENCE_PLAN["causal_interpretation_assumptions"]
        ),
        "assumptions_satisfied": _EXPECTED_INFERENCE_PLAN[
            "assumptions_satisfied"
        ],
        "summation_algorithm": "explicit_left_to_right_binary64_v1",
        "minimum_pairs_per_context": MIN_PAIRS_PER_CONTEXT,
        "minimum_assignment_space": MIN_ASSIGNMENT_SPACE,
        "minimum_arm_information_ratio": MIN_ARM_INFORMATION_RATIO,
        "assignment_space": (
            "exact shared information-filtered admissible arm-label vectors"
        ),
        "maximum_enumerated_assignment_space": MAX_ASSIGNMENT_SPACE,
        "alpha": ALPHA,
        "alternative": "lower",
        "n_contexts": n_contexts,
        "n_pairs": n_pairs,
        "pairs_per_context": dict(pairs_per_context or {}),
        "n_admissible_treatment_assignments": n_admissible,
        "selected_assignment_verified": selected_verified,
        "conditional_software_contract_verified": (
            conditional_software_contract_verified
        ),
        "entropy_authenticity_verified": authenticated_randomization_verified,
        "authenticated_randomization_verified": (
            authenticated_randomization_verified
        ),
        "analysis_plan_sha256": analysis_plan_sha256,
        "endpoints": [dict(item) for item in endpoints],
    }


def _parse_manifest(plan: Mapping[str, Any]) -> tuple[list[_Pair], dict[str, _Member]]:
    raw_manifest = plan.get("assignment_manifest")
    if raw_manifest is None:
        raise AllocationInferenceError(
            "allocation_manifest_missing",
            "the arm-blind assignment manifest is absent",
        )
    if not isinstance(raw_manifest, Mapping):
        raise AllocationInferenceError("allocation_contract_malformed")
    _exact_keys(raw_manifest, _MANIFEST_KEYS, "assignment_manifest")
    if raw_manifest.get("schema") != MANIFEST_SCHEMA:
        raise AllocationInferenceError(
            "allocation_contract_malformed", "assignment_manifest has the wrong schema"
        )

    raw_plates = raw_manifest.get("plate_dimensions")
    if not isinstance(raw_plates, list) or not raw_plates:
        raise AllocationInferenceError("allocation_contract_malformed")
    plates: dict[str, tuple[int, int]] = {}
    for raw_plate in raw_plates:
        if not isinstance(raw_plate, Mapping):
            raise AllocationInferenceError("allocation_contract_malformed")
        _exact_keys(raw_plate, _PLATE_KEYS, "assignment_manifest.plate_dimensions")
        plate_id = _identifier(
            raw_plate.get("functional_assay_plate_id"), "functional_assay_plate_id"
        )
        if plate_id in plates:
            raise AllocationInferenceError("allocation_contract_malformed", "duplicate plate")
        plates[plate_id] = (
            _positive_int(raw_plate.get("n_rows"), "n_rows"),
            _positive_int(raw_plate.get("n_columns"), "n_columns"),
        )

    raw_pairs = raw_manifest.get("pair_units")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise AllocationInferenceError("allocation_contract_malformed")
    parsed_pairs: list[_Pair] = []
    member_index: dict[str, _Member] = {}
    seen_pairs: set[str] = set()
    seen_wells: set[tuple[str, int, int]] = set()
    seen_dosing: set[int] = set()
    seen_acquisition: set[int] = set()
    for raw_pair in raw_pairs:
        if not isinstance(raw_pair, Mapping):
            raise AllocationInferenceError("allocation_contract_malformed")
        _exact_keys(raw_pair, _PAIR_KEYS, "assignment_manifest.pair_units")
        pair_id = _identifier(raw_pair.get("pair_id"), "pair_id")
        if pair_id in seen_pairs:
            raise AllocationInferenceError("allocation_contract_malformed", "duplicate pair")
        seen_pairs.add(pair_id)
        raw_members = raw_pair.get("members")
        if not isinstance(raw_members, list) or len(raw_members) != 2:
            raise AllocationInferenceError(
                "allocation_contract_malformed", "each pair must contain two members"
            )
        members: list[_Member] = []
        for raw_member in raw_members:
            if not isinstance(raw_member, Mapping):
                raise AllocationInferenceError("allocation_contract_malformed")
            _exact_keys(raw_member, _MEMBER_KEYS, "assignment_manifest member")
            member = _Member(
                execution_id=_member_identifier(
                    raw_member.get("functional_execution_id"),
                    "functional_execution_id",
                ),
                event_id=_member_identifier(
                    raw_member.get("edit_event_id"), "edit_event_id"
                ),
                clone_id=_member_identifier(raw_member.get("clone_id"), "clone_id"),
                batch_id=_member_identifier(
                    raw_member.get("culture_batch_id"), "culture_batch_id"
                ),
                run_id=_member_identifier(
                    raw_member.get("functional_assay_run_id"),
                    "functional_assay_run_id",
                ),
                block_id=_member_identifier(
                    raw_member.get("allocation_block_id"), "allocation_block_id"
                ),
                plate_id=_member_identifier(
                    raw_member.get("functional_assay_plate_id"),
                    "functional_assay_plate_id",
                ),
                plate_row=_positive_int(raw_member.get("plate_row"), "plate_row"),
                plate_column=_positive_int(
                    raw_member.get("plate_column"), "plate_column"
                ),
                dosing_order=_positive_int(
                    raw_member.get("dosing_order"), "dosing_order"
                ),
                acquisition_order=_positive_int(
                    raw_member.get("acquisition_order"), "acquisition_order"
                ),
            )
            if member.execution_id in member_index:
                raise AllocationInferenceError(
                    "allocation_contract_malformed", "execution belongs to multiple pairs"
                )
            if member.plate_id not in plates:
                raise AllocationInferenceError(
                    "allocation_contract_malformed", "member references an unknown plate"
                )
            n_rows, n_columns = plates[member.plate_id]
            if member.plate_row > n_rows or member.plate_column > n_columns:
                raise AllocationInferenceError(
                    "allocation_contract_malformed", "member well is outside the plate"
                )
            well = (member.plate_id, member.plate_row, member.plate_column)
            if well in seen_wells:
                raise AllocationInferenceError(
                    "allocation_contract_malformed", "duplicate physical well"
                )
            if member.dosing_order in seen_dosing or member.acquisition_order in seen_acquisition:
                raise AllocationInferenceError(
                    "allocation_contract_malformed", "duplicate execution order"
                )
            seen_wells.add(well)
            seen_dosing.add(member.dosing_order)
            seen_acquisition.add(member.acquisition_order)
            member_index[member.execution_id] = member
            members.append(member)
        members.sort(key=lambda item: item.execution_id)
        first, second = members
        if first.execution_id == second.execution_id:
            raise AllocationInferenceError("allocation_contract_malformed")
        if (
            first.event_id,
            first.clone_id,
            first.batch_id,
            first.run_id,
            first.block_id,
            first.plate_id,
        ) != (
            second.event_id,
            second.clone_id,
            second.batch_id,
            second.run_id,
            second.block_id,
            second.plate_id,
        ):
            raise AllocationInferenceError(
                "allocation_contract_malformed",
                "pair members do not share biological and execution context",
            )
        parsed_pairs.append(_Pair(pair_id=pair_id, members=(first, second)))
    parsed_pairs.sort(key=lambda item: item.pair_id)
    unit_share: dict[tuple[str, str], int] = defaultdict(int)
    for pair in parsed_pairs:
        member = pair.members[0]
        unit_share[(member.event_id, member.clone_id)] += 1
    if len(unit_share) < MIN_BIOLOGICAL_UNITS:
        raise AllocationInferenceError(
            "insufficient_biological_units",
            "the declared clone_edit_event replication unit is not replicated",
        )
    if max(unit_share.values()) > MAX_CLONE_PAIR_SHARE * len(parsed_pairs):
        raise AllocationInferenceError(
            "clone_share_ceiling_exceeded",
            "a single clone_edit_event unit supplies more than half the pairs",
        )
    return parsed_pairs, member_index


def _enumerate_candidate_vectors(
    assignment_manifest: object,
    pairs: Sequence[_Pair],
) -> tuple[list[bytes], dict[str, int]]:
    by_context: dict[tuple[str, str, str, str], list[_Pair]] = defaultdict(list)
    for pair in pairs:
        by_context[pair.context].append(pair)
    for items in by_context.values():
        items.sort(key=lambda item: item.pair_id)

    pairs_per_context = {
        f"context-{index:03d}": len(items)
        for index, (_context, items) in enumerate(
            sorted(by_context.items()), start=1
        )
    }
    if any(count < MIN_PAIRS_PER_CONTEXT for count in pairs_per_context.values()):
        raise AllocationInferenceError(
            "insufficient_pairs_per_context",
            f"each context requires at least {MIN_PAIRS_PER_CONTEXT} biological pairs",
        )
    if enumerate_admissible_assignment_vectors is None:
        raise AllocationInferenceError(
            "analysis_plan_contract_unavailable",
            "the allocation module does not expose exact candidate enumeration",
        )
    try:
        exact_candidates, exact_digest = enumerate_admissible_assignment_vectors(
            assignment_manifest
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise AllocationInferenceError(
            "allocation_contract_malformed",
            "exact admissible-space reconstruction failed",
        ) from exc
    # Materialize at most the ceiling plus one — a caller-supplied lazy
    # iterable must not expand past the assignment-space bound in memory,
    # and a mid-iteration failure fails closed rather than propagating.
    try:
        ordered = list(
            itertools.islice(iter(exact_candidates), MAX_ASSIGNMENT_SPACE + 1)
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise AllocationInferenceError(
            "allocation_contract_malformed",
            "exact admissible-space materialization failed",
        ) from exc
    if (
        not ordered
        or len(ordered) > MAX_ASSIGNMENT_SPACE
        or ordered != sorted(set(ordered))
        or any(not isinstance(candidate, bytes) for candidate in ordered)
        or exact_digest != _space_digest(ordered)
    ):
        raise AllocationInferenceError(
            "allocation_contract_malformed",
            "shared admissible-space helper returned a noncanonical support",
        )
    if len(ordered) < MIN_ASSIGNMENT_SPACE:
        raise AllocationInferenceError(
            "insufficient_assignment_space",
            f"only {len(ordered)} unique treatment-label vectors survive",
        )
    return ordered, pairs_per_context


def _space_digest(candidates: Sequence[bytes]) -> str:
    digest = hashlib.sha256()
    digest.update(b"[")
    for index, candidate in enumerate(candidates):
        if index:
            digest.update(b",")
        digest.update(candidate)
    digest.update(b"]")
    return digest.hexdigest()


def _selected_vector(
    plan: Mapping[str, Any], pairs: Sequence[_Pair], member_index: Mapping[str, _Member]
) -> tuple[bytes, dict[str, str]]:
    raw_assignments = plan.get("assignments")
    if not isinstance(raw_assignments, list) or not raw_assignments:
        raise AllocationInferenceError("allocation_contract_malformed")
    assignments: dict[str, Mapping[str, Any]] = {}
    for raw in raw_assignments:
        if not isinstance(raw, Mapping):
            raise AllocationInferenceError("allocation_contract_malformed")
        execution_id = _member_identifier(raw.get("functional_execution_id"), "functional_execution_id")
        if execution_id in assignments:
            raise AllocationInferenceError("allocation_contract_malformed", "duplicate assignment")
        assignments[execution_id] = raw
    if set(assignments) != set(member_index):
        raise AllocationInferenceError(
            "selected_assignment_manifest_mismatch",
            "selected assignments and manifest executions differ",
        )

    arm_by_execution: dict[str, str] = {}
    selected: list[dict[str, str]] = []
    for pair in pairs:
        treatment_ids: list[str] = []
        for member in pair.members:
            assignment = assignments[member.execution_id]
            arm = assignment.get("arm")
            if arm not in {"vehicle", "treatment"}:
                raise AllocationInferenceError("allocation_contract_malformed")
            arm_by_execution[member.execution_id] = str(arm)
            for manifest_field in _ASSIGNMENT_FIELDS:
                manifest_value = getattr(
                    member,
                    {
                        "edit_event_id": "event_id",
                        "culture_batch_id": "batch_id",
                        "functional_assay_run_id": "run_id",
                        "allocation_block_id": "block_id",
                        "functional_assay_plate_id": "plate_id",
                    }.get(manifest_field, manifest_field),
                )
                if assignment.get(manifest_field) != manifest_value:
                    raise AllocationInferenceError(
                        "selected_assignment_manifest_mismatch",
                        f"selected assignment differs at {manifest_field}",
                    )
            if assignment.get("deviation_status") != "none":
                raise AllocationInferenceError(
                    "selected_assignment_manifest_mismatch", "allocation deviation is present"
                )
            if arm == "treatment":
                treatment_ids.append(member.execution_id)
        if len(treatment_ids) != 1:
            raise AllocationInferenceError(
                "selected_assignment_not_admissible",
                "each biological pair must have one treatment and one vehicle",
            )
        selected.append(
            {"pair_id": pair.pair_id, "treatment_execution_id": treatment_ids[0]}
        )
    return _canonical_json(selected), arm_by_execution


def _replay_randomization(
    plan: Mapping[str, Any], candidates: Sequence[bytes], selected: bytes
) -> None:
    raw = plan.get("randomization")
    if raw is None:
        raise AllocationInferenceError(
            "randomization_record_missing", "the selected-assignment replay record is absent"
        )
    if not isinstance(raw, Mapping):
        raise AllocationInferenceError("allocation_contract_malformed")
    _exact_keys(raw, _RANDOMIZATION_KEYS, "randomization")
    if raw.get("generator") != GENERATOR:
        raise AllocationInferenceError("allocation_contract_malformed", "unknown generator")
    if raw.get("entropy_authenticity") != "not_attested":
        raise AllocationInferenceError(
            "allocation_contract_malformed",
            "entropy authenticity must remain explicitly unattested",
        )
    record = raw.get("record")
    if not isinstance(record, Mapping):
        raise AllocationInferenceError("allocation_contract_malformed")
    _exact_keys(record, _RECORD_KEYS, "randomization.record")

    declared_count = _positive_int(raw.get("admissible_space_count"), "admissible_space_count")
    if declared_count != len(candidates):
        raise AllocationInferenceError(
            "admissible_space_mismatch", "declared and reconstructed support counts differ"
        )
    declared_space = _sha256(raw.get("admissible_space_sha256"), "admissible_space_sha256")
    if not hmac.compare_digest(declared_space, _space_digest(candidates)):
        raise AllocationInferenceError(
            "admissible_space_mismatch", "declared and reconstructed support digests differ"
        )
    selected_digest = _sha256(raw.get("selected_vector_sha256"), "selected_vector_sha256")
    if not hmac.compare_digest(selected_digest, hashlib.sha256(selected).hexdigest()):
        raise AllocationInferenceError(
            "selected_assignment_digest_mismatch", "selected-vector digest does not match"
        )
    if selected not in candidates:
        raise AllocationInferenceError(
            "selected_assignment_not_admissible", "selected vector is outside support"
        )

    seed_hex = raw.get("seed_reveal_hex")
    if not isinstance(seed_hex, str) or _HEX64.fullmatch(seed_hex) is None:
        raise AllocationInferenceError("allocation_contract_malformed", "seed reveal is malformed")
    seed_commitment = _sha256(
        raw.get("seed_commitment_sha256"), "seed_commitment_sha256"
    )
    seed_commitment_record = raw.get("seed_commitment_record")
    if not isinstance(seed_commitment_record, Mapping):
        raise AllocationInferenceError(
            "allocation_contract_malformed", "seed commitment record is absent"
        )
    _exact_keys(
        seed_commitment_record,
        _COMMITMENT_RECORD_KEYS,
        "randomization.seed_commitment_record",
    )
    recorded_seed_digest = _sha256(
        seed_commitment_record.get("digest_sha256"),
        "randomization.seed_commitment_record.digest_sha256",
    )
    if (
        not hmac.compare_digest(recorded_seed_digest, seed_commitment)
        or seed_commitment_record.get("recorded_at")
        != raw.get("seed_committed_at")
    ):
        raise AllocationInferenceError(
            "seed_commitment_mismatch",
            "seed commitment record does not match the declared commitment",
        )
    if make_seed_commitment is None:
        raise AllocationInferenceError(
            "analysis_plan_contract_unavailable",
            "the allocation module does not expose seed-commitment replay",
        )
    input_digest = _sha256(
        plan.get("assignment_input_commitment_sha256"),
        "assignment_input_commitment_sha256",
    )
    try:
        expected_seed_commitment = make_seed_commitment(
            seed_hex,
            assignment_input_commitment_sha256=input_digest,
        )
    except (TypeError, ValueError) as exc:
        raise AllocationInferenceError("allocation_contract_malformed") from exc
    if not hmac.compare_digest(seed_commitment, expected_seed_commitment):
        raise AllocationInferenceError(
            "seed_commitment_mismatch", "revealed seed does not match its commitment"
        )
    if rejection_sampled_candidate_index is None or SeedModuloBiasRejection is None:
        raise AllocationInferenceError(
            "analysis_plan_contract_unavailable",
            "the allocation module does not expose exact rejection sampling",
        )
    try:
        selected_index = rejection_sampled_candidate_index(seed_hex, len(candidates))
    except SeedModuloBiasRejection as exc:
        raise AllocationInferenceError(
            "allocation_seed_rejected_for_modulo_bias",
            "the committed uint256 seed lies in the modulo-bias rejection tail",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise AllocationInferenceError("allocation_contract_malformed") from exc
    winner = candidates[selected_index]
    if not hmac.compare_digest(winner, selected):
        raise AllocationInferenceError(
            "selected_assignment_replay_mismatch",
            "selected vector is not the committed generator winner",
        )


def _validate_analysis_plan(plan: Mapping[str, Any]) -> str:
    if ALLOCATION_ANALYSIS_PLAN is None or make_allocation_analysis_plan_sha256 is None:
        raise AllocationInferenceError(
            "analysis_plan_contract_unavailable",
            "the allocation module does not expose the prespecified analysis plan",
        )
    if (
        not isinstance(ALLOCATION_ANALYSIS_PLAN, Mapping)
        or ALLOCATION_ANALYSIS_PLAN.get("minimum_pairs_per_context")
        != MIN_PAIRS_PER_CONTEXT
        or ALLOCATION_ANALYSIS_PLAN.get("allocation_information_filter")
        != _EXPECTED_ALLOCATION_INFORMATION_FILTER
        or ALLOCATION_ANALYSIS_PLAN.get("enumeration_safety")
        != _EXPECTED_ENUMERATION_SAFETY
        or ALLOCATION_ANALYSIS_PLAN.get("inference") != _EXPECTED_INFERENCE_PLAN
    ):
        raise AllocationInferenceError(
            "analysis_plan_semantics_mismatch",
            "shared analysis-plan semantics differ from this implementation",
        )
    declared = _sha256(plan.get("analysis_plan_sha256"), "analysis_plan_sha256")
    try:
        expected = make_allocation_analysis_plan_sha256()
    except (TypeError, ValueError) as exc:
        raise AllocationInferenceError(
            "analysis_plan_contract_unavailable", "analysis-plan digest helper failed"
        ) from exc
    _sha256(expected, "expected analysis_plan_sha256")
    if not hmac.compare_digest(declared, expected):
        raise AllocationInferenceError(
            "analysis_plan_mismatch", "allocation is not bound to the implemented analysis plan"
        )
    return declared


def _lineage_rates(
    lineage: Mapping[str, Any],
    plan: Mapping[str, Any],
    member_index: Mapping[str, _Member],
    arm_by_execution: Mapping[str, str],
) -> dict[str, tuple[float, float]]:
    if lineage.get("schema") != LINEAGE_SCHEMA:
        raise AllocationInferenceError("lineage_contract_malformed", "wrong lineage schema")
    if lineage.get("study_id") != plan.get("study_id"):
        raise AllocationInferenceError("lineage_assignment_mismatch", "study IDs differ")
    if lineage.get("lock_state") != "locked" or lineage.get("blinded") is not True:
        raise AllocationInferenceError(
            "lineage_contract_malformed", "lineage counts must be locked and blinded"
        )
    if lineage.get("allocation_id") != plan.get("allocation_id"):
        raise AllocationInferenceError(
            "lineage_assignment_mismatch", "lineage allocation ID does not match"
        )
    raw_runs = lineage.get("runs")
    if not isinstance(raw_runs, list) or not raw_runs:
        raise AllocationInferenceError("lineage_contract_malformed")
    run_index: dict[str, Mapping[str, Any]] = {}
    for row in raw_runs:
        if not isinstance(row, Mapping):
            raise AllocationInferenceError("lineage_contract_malformed")
        execution_id = _member_identifier(row.get("functional_execution_id"), "functional_execution_id")
        if execution_id in run_index:
            raise AllocationInferenceError(
                "lineage_contract_malformed", "duplicate lineage execution"
            )
        run_index[execution_id] = row
    if set(run_index) != set(member_index):
        raise AllocationInferenceError(
            "lineage_assignment_mismatch",
            "lineage must consume the exact manifest execution set",
        )

    rates: dict[str, tuple[float, float]] = {}
    for execution_id, member in member_index.items():
        row = run_index[execution_id]
        if row.get("arm") != arm_by_execution[execution_id]:
            raise AllocationInferenceError(
                "lineage_assignment_mismatch", "lineage arm differs from selected allocation"
            )
        for manifest_field, lineage_field in _LINEAGE_FIELDS.items():
            member_value = getattr(
                member,
                {
                    "edit_event_id": "event_id",
                    "culture_batch_id": "batch_id",
                    "functional_assay_run_id": "run_id",
                    "allocation_block_id": "block_id",
                    "functional_assay_plate_id": "plate_id",
                }.get(manifest_field, manifest_field),
            )
            if row.get(lineage_field) != member_value:
                raise AllocationInferenceError(
                    "lineage_assignment_mismatch",
                    f"lineage differs from manifest at {lineage_field}",
                )
        opportunities = _count(row.get("opportunities"), "opportunities")
        detected = _count(row.get("detected_divisions"), "detected_divisions")
        errors = _count(
            row.get("event_positive_divisions"), "event_positive_divisions"
        )
        event_negative = _count(
            row.get("event_negative_divisions"), "event_negative_divisions"
        )
        pre_division_death = _count(
            row.get("pre_division_death"), "pre_division_death"
        )
        no_division = _count(row.get("no_division"), "no_division")
        dropout_censored = _count(
            row.get("dropout_censored"), "dropout_censored"
        )
        if opportunities == 0 or detected == 0:
            raise AllocationInferenceError(
                "endpoint_denominator_zero",
                "both prespecified endpoint denominators must be positive",
            )
        if (
            errors + event_negative != detected
            or detected + pre_division_death + no_division + dropout_censored
            != opportunities
        ):
            raise AllocationInferenceError(
                "endpoint_data_malformed", "lineage endpoint counts are internally inconsistent"
            )
        rates[execution_id] = (errors / detected, errors / opportunities)
    return rates


def _nuisance_design(
    pairs: Sequence[_Pair], member_index: Mapping[str, _Member]
) -> tuple[list[str], list[list[float]]]:
    execution_ids = sorted(member_index)
    contexts = sorted({pair.context for pair in pairs})
    context_index = {context: index for index, context in enumerate(contexts)}
    context_by_execution = {
        member.execution_id: pair.context for pair in pairs for member in pair.members
    }
    order_means: dict[tuple[str, str, str, str], tuple[float, float]] = {}
    for context in contexts:
        context_members = [
            member
            for pair in pairs
            if pair.context == context
            for member in pair.members
        ]
        context_count = float(len(context_members))
        order_means[context] = (
            _left_to_right_binary64_sum(
                float(member.dosing_order) for member in context_members
            )
            / context_count,
            _left_to_right_binary64_sum(
                float(member.acquisition_order) for member in context_members
            )
            / context_count,
        )

    design: list[list[float]] = []
    for execution_id in execution_ids:
        member = member_index[execution_id]
        context = context_by_execution[execution_id]
        dosing_mean, acquisition_mean = order_means[context]
        centered_dosing = member.dosing_order - dosing_mean
        centered_acquisition = member.acquisition_order - acquisition_mean
        row = [1.0]
        row.extend(
            1.0 if context_index[context] == index else 0.0
            for index in range(1, len(contexts))
        )
        nuisance_block = (
            centered_dosing,
            centered_dosing * centered_dosing,
            centered_acquisition,
            centered_acquisition * centered_acquisition,
            centered_dosing * centered_acquisition,
        )
        for block_context in contexts:
            row.extend(nuisance_block if block_context == context else (0.0,) * 5)
        if len(row) != 6 * len(contexts):
            raise AllocationInferenceError("nuisance_design_malformed")
        if not all(math.isfinite(value) for value in row):
            raise AllocationInferenceError("nuisance_design_malformed")
        design.append(row)
    return execution_ids, design


def _ols_residuals(design: Sequence[Sequence[float]], outcome: Sequence[float]) -> list[float]:
    if not design or len(design) != len(outcome):
        raise AllocationInferenceError("nuisance_design_malformed")
    width = len(design[0])
    if width == 0 or len(design) <= width or any(len(row) != width for row in design):
        raise AllocationInferenceError("nuisance_design_rank_deficient")
    columns = [[float(row[column]) for row in design] for column in range(width)]
    q_columns: list[list[float]] = []
    upper = [[0.0] * width for _ in range(width)]
    for column_index, column in enumerate(columns):
        vector = list(column)
        original_norm = math.sqrt(
            _left_to_right_binary64_sum(value * value for value in vector)
        )
        for prior_index, q_column in enumerate(q_columns):
            coefficient = _left_to_right_binary64_sum(
                q * value for q, value in zip(q_column, vector, strict=True)
            )
            upper[prior_index][column_index] = coefficient
            vector = [
                value - coefficient * q
                for value, q in zip(vector, q_column, strict=True)
            ]
        # A second pass makes the rank decision stable for correlated order terms.
        for prior_index, q_column in enumerate(q_columns):
            correction = _left_to_right_binary64_sum(
                q * value for q, value in zip(q_column, vector, strict=True)
            )
            upper[prior_index][column_index] += correction
            vector = [
                value - correction * q
                for value, q in zip(vector, q_column, strict=True)
            ]
        norm = math.sqrt(
            _left_to_right_binary64_sum(value * value for value in vector)
        )
        if norm <= 1e-10 * max(1.0, original_norm):
            raise AllocationInferenceError(
                "nuisance_design_rank_deficient",
                "prespecified nuisance design is not full column rank",
            )
        upper[column_index][column_index] = norm
        q_columns.append([value / norm for value in vector])

    q_transpose_y = [
        _left_to_right_binary64_sum(
            q * value for q, value in zip(q_column, outcome, strict=True)
        )
        for q_column in q_columns
    ]
    coefficients = [0.0] * width
    for row_index in range(width - 1, -1, -1):
        remainder = _left_to_right_binary64_sum(
            upper[row_index][column_index] * coefficients[column_index]
            for column_index in range(row_index + 1, width)
        )
        coefficients[row_index] = (
            q_transpose_y[row_index] - remainder
        ) / upper[row_index][row_index]
    fitted = [
        _left_to_right_binary64_sum(
            value * coefficient
            for value, coefficient in zip(row, coefficients, strict=True)
        )
        for row in design
    ]
    residuals = [
        value - prediction for value, prediction in zip(outcome, fitted, strict=True)
    ]
    if not all(math.isfinite(value) for value in residuals):
        raise AllocationInferenceError("nuisance_design_malformed")
    return residuals


def _candidate_treatments(candidate: bytes) -> dict[str, str]:
    parsed = _strict_loads(candidate.decode("utf-8"))
    return {str(item["pair_id"]): str(item["treatment_execution_id"]) for item in parsed}


def _mean_pair_difference(
    values: Mapping[str, float], pairs: Sequence[_Pair], treatment_by_pair: Mapping[str, str]
) -> float:
    differences: list[float] = []
    for pair in pairs:
        treatment_id = treatment_by_pair[pair.pair_id]
        first, second = pair.members
        vehicle_id = second.execution_id if treatment_id == first.execution_id else first.execution_id
        differences.append(values[treatment_id] - values[vehicle_id])
    return _left_to_right_binary64_sum(differences) / len(differences)


def _endpoint_results(
    *,
    candidates: Sequence[bytes],
    selected: bytes,
    pairs: Sequence[_Pair],
    rates: Mapping[str, tuple[float, float]],
    member_index: Mapping[str, _Member],
) -> list[dict[str, Any]]:
    execution_ids, design = _nuisance_design(pairs, member_index)
    endpoint_definitions = (
        ("error_per_detected_division", 0),
        ("error_per_enrolled_founder", 1),
    )
    selected_map = _candidate_treatments(selected)
    results: list[dict[str, Any]] = []
    for endpoint_id, endpoint_index in endpoint_definitions:
        raw_values = {
            execution_id: rates[execution_id][endpoint_index]
            for execution_id in execution_ids
        }
        outcome = [raw_values[execution_id] for execution_id in execution_ids]
        residual_values = dict(
            zip(execution_ids, _ols_residuals(design, outcome), strict=True)
        )
        observed_raw = _mean_pair_difference(raw_values, pairs, selected_map)
        observed = _mean_pair_difference(residual_values, pairs, selected_map)
        tolerance = 1e-12 * max(1.0, abs(observed))
        lower_tail_count = 0
        for candidate in candidates:
            candidate_statistic = _mean_pair_difference(
                residual_values, pairs, _candidate_treatments(candidate)
            )
            if candidate_statistic <= observed + tolerance:
                lower_tail_count += 1
        p_value = lower_tail_count / len(candidates)
        directionally_lower = observed_raw < 0.0
        passed = directionally_lower and p_value <= ALPHA
        results.append(
            {
                "endpoint_id": endpoint_id,
                "reported_contrast": _EXPECTED_INFERENCE_PLAN[
                    "reported_contrast"
                ],
                "tested_null": _EXPECTED_INFERENCE_PLAN["tested_null"],
                "tested_null_statement": _EXPECTED_INFERENCE_PLAN[
                    "tested_null_statement"
                ],
                "p_value_scope": _EXPECTED_INFERENCE_PLAN["p_value_scope"],
                "assignment_probability_model": _EXPECTED_INFERENCE_PLAN[
                    "assignment_probability_model"
                ],
                "causal_interpretation_assumptions": list(
                    _EXPECTED_INFERENCE_PLAN[
                        "causal_interpretation_assumptions"
                    ]
                ),
                "assumptions_satisfied": _EXPECTED_INFERENCE_PLAN[
                    "assumptions_satisfied"
                ],
                "nuisance_residualization": (
                    "fixed unit-level OLS with context-specific intercepts and "
                    "context-interacted, within-context centered dosing and "
                    "acquisition order linear, squared, and cross-product terms"
                ),
                "observed_raw_mean_difference": observed_raw,
                "observed_residualized_mean_difference": observed,
                "lower_tail_count": lower_tail_count,
                "support_size": len(candidates),
                "exact_lower_tail_p_value": p_value,
                "directionally_lower": directionally_lower,
                "passed": passed,
            }
        )
    return results


def assess_constrained_randomization_inference(
    lineage: Mapping[str, Any], exposure_table: Mapping[str, Any]
) -> dict[str, Any]:
    """Assess both prespecified error endpoints over the exact arm-vector support.

    Any absent, malformed, unmatched, rank-deficient, or non-replayable input is
    returned as ``not_assessable``.  A fully valid analysis returns ``pass`` only
    when both raw within-pair directions are lower under treatment and both
    Fisher sharp-null lower-tail p-values are at most 0.05; otherwise it returns
    ``stop``. These p-values are not exact tests of a weak zero-average-effect
    null, and the causal assumptions remain outside software attestation.
    """

    synthetic_only = False
    conditional_software_contract_verified = False
    authenticated_randomization_verified = False
    analysis_digest: str | None = None
    pairs: list[_Pair] = []
    pairs_per_context: dict[str, int] = {}
    candidates: list[bytes] = []
    selected_verified = False
    try:
        if not isinstance(lineage, Mapping) or not isinstance(exposure_table, Mapping):
            raise AllocationInferenceError("input_contract_malformed")
        lineage_synthetic = lineage.get("synthetic_only")
        exposure_privacy_class = exposure_table.get("privacy_class")
        if not isinstance(lineage_synthetic, bool) or not isinstance(
            exposure_privacy_class, str
        ):
            raise AllocationInferenceError(
                "artifact_classification_malformed",
                "lineage synthetic_only and exposure privacy_class are required",
            )
        exposure_synthetic = exposure_privacy_class == "synthetic"
        if lineage_synthetic != exposure_synthetic:
            raise AllocationInferenceError(
                "artifact_classification_mismatch",
                "lineage and exposure synthetic classifications disagree",
            )
        if "privacy_class" in lineage:
            lineage_privacy_class = lineage.get("privacy_class")
            if (
                not isinstance(lineage_privacy_class, str)
                or not lineage_privacy_class
                or lineage_privacy_class.strip() != lineage_privacy_class
            ):
                raise AllocationInferenceError(
                    "artifact_classification_malformed",
                    "optional lineage privacy_class must be a non-empty trimmed string",
                )
            if (
                lineage_privacy_class != exposure_privacy_class
                or (lineage_privacy_class == "synthetic") != lineage_synthetic
            ):
                raise AllocationInferenceError(
                    "artifact_classification_mismatch",
                    "lineage privacy_class contradicts declared artifact "
                    "classifications",
                )
        synthetic_only = exposure_synthetic
        if exposure_table.get("schema") != TABLE_SCHEMA:
            raise AllocationInferenceError("exposure_contract_malformed")
        plan = exposure_table.get("preexposure_allocation")
        if plan is None:
            raise AllocationInferenceError("allocation_plan_missing")
        if not isinstance(plan, Mapping):
            raise AllocationInferenceError("allocation_contract_malformed")
        if plan.get("assignment_manifest") is None:
            raise AllocationInferenceError(
                "allocation_manifest_missing",
                "the arm-blind assignment manifest is absent",
            )
        if plan.get("randomization") is None:
            raise AllocationInferenceError(
                "randomization_record_missing",
                "the selected-assignment replay record is absent",
            )
        try:
            allocation_result = assess_preexposure_allocation(exposure_table)
        except (TypeError, ValueError, KeyError) as exc:
            raise AllocationInferenceError(
                "preexposure_allocation_not_verified",
                "the pre-exposure allocation validator rejected the input",
            ) from exc
        authenticated_randomization_verified = bool(
            allocation_result.get("authenticated_randomization_verified") is True
        )
        conditional_software_contract_verified = bool(
            allocation_result.get("conditional_software_contract_verified") is True
        )
        if (
            not synthetic_only
            and conditional_software_contract_verified
            and not authenticated_randomization_verified
        ):
            raise AllocationInferenceError(
                "authenticated_randomization_required",
                str(
                    allocation_result.get(
                        "reason",
                        "non-synthetic inference requires authenticated randomization",
                    )
                ),
            )
        if (
            allocation_result.get("status") != "pass"
            or allocation_result.get("allocation_verified") is not True
        ):
            allocation_reason = str(
                allocation_result.get("reason", "allocation did not pass")
            )
            raise AllocationInferenceError(
                (
                    "allocation_seed_rejected_for_modulo_bias"
                    if allocation_reason
                    == "allocation_seed_rejected_for_modulo_bias"
                    else "preexposure_allocation_not_verified"
                ),
                allocation_reason,
            )
        if synthetic_only:
            if not conditional_software_contract_verified:
                raise AllocationInferenceError(
                    "conditional_software_contract_not_verified"
                )
        elif not authenticated_randomization_verified:
            raise AllocationInferenceError(
                "authenticated_randomization_required",
                "non-synthetic inference requires authenticated randomization",
            )
        analysis_digest = _validate_analysis_plan(plan)
        pairs, member_index = _parse_manifest(plan)
        candidates, pairs_per_context = _enumerate_candidate_vectors(
            plan.get("assignment_manifest"), pairs
        )
        selected, arm_by_execution = _selected_vector(plan, pairs, member_index)
        _replay_randomization(plan, candidates, selected)
        selected_verified = True
        rates = _lineage_rates(lineage, plan, member_index, arm_by_execution)
        endpoint_results = _endpoint_results(
            candidates=candidates,
            selected=selected,
            pairs=pairs,
            rates=rates,
            member_index=member_index,
        )
        passed = all(item["passed"] for item in endpoint_results)
        if passed:
            reason = "both_endpoints_pass"
            detail = "both prespecified lower-tail tests pass"
            status = "pass"
        elif any(not item["directionally_lower"] for item in endpoint_results):
            reason = "endpoint_not_directionally_lower"
            detail = "at least one treatment-minus-vehicle raw rate is not lower"
            status = "stop"
        else:
            reason = "exact_pvalue_above_threshold"
            detail = "at least one exact one-sided p-value exceeds 0.05"
            status = "stop"
        return _base_result(
            status=status,
            reason=reason,
            detail=detail,
            synthetic_only=synthetic_only,
            n_contexts=len(pairs_per_context),
            n_pairs=len(pairs),
            pairs_per_context=pairs_per_context,
            n_admissible=len(candidates),
            selected_verified=True,
            conditional_software_contract_verified=(
                conditional_software_contract_verified
            ),
            authenticated_randomization_verified=(
                authenticated_randomization_verified
            ),
            analysis_plan_sha256=analysis_digest,
            endpoints=endpoint_results,
        )
    except AllocationInferenceError as exc:
        return _base_result(
            status="not_assessable",
            reason=exc.reason,
            detail=exc.detail,
            synthetic_only=synthetic_only,
            n_contexts=len(pairs_per_context),
            n_pairs=len(pairs),
            pairs_per_context=pairs_per_context,
            n_admissible=len(candidates),
            selected_verified=selected_verified,
            conditional_software_contract_verified=(
                conditional_software_contract_verified
            ),
            authenticated_randomization_verified=(
                authenticated_randomization_verified
            ),
            analysis_plan_sha256=analysis_digest,
        )


__all__ = [
    "ALPHA",
    "CLAIM_BOUNDARY",
    "MANIFEST_SCHEMA",
    "MAX_ASSIGNMENT_SPACE",
    "MIN_ARM_INFORMATION_RATIO",
    "MIN_ASSIGNMENT_SPACE",
    "MIN_PAIRS_PER_CONTEXT",
    "SCHEMA",
    "assess_constrained_randomization_inference",
]
