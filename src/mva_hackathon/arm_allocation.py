"""Pre-exposure arm-allocation contract for paired functional executions.

The contract rejects a favorable aggregate when treatment and vehicle are
structurally separated by plate position, batch, run, or acquisition tranche.
It validates declared metadata and a digest-backed commitment only. It cannot
prove that a physical well was plated, dosed, or acquired as declared.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


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


TABLE_SCHEMA = "mva.community-measured-exposure-table/v1"
PLAN_SCHEMA = "mva.community-preexposure-allocation/v3"
SCHEMA = "mva-track2-preexposure-allocation/v2"
ARMS = ("vehicle", "treatment")
ASSIGNMENT_METHODS = ("seed_committed_constrained_randomization",)
ASSIGNMENT_ALGORITHMS = ("paired_constrained_seed_index_rejection_v1",)
COMMITMENT_MECHANISMS = (
    "append_only_registry",
    "signed_timestamp",
    "version_control_commit",
)
ALLOCATION_UNIT = "functional_execution_well"
ASSIGNMENT_MANIFEST_SCHEMA = "mva-track2-arm-blind-assignment-manifest/v1"
RANDOMIZATION_GENERATOR = "seed_uint256_rejection_index_v1"
RANDOMIZATION_ENTROPY_AUTHENTICITY = "not_attested"
SEED_SPACE_SIZE = 1 << 256
MINIMUM_PAIRS_PER_CONTEXT = 6
MINIMUM_ADMISSIBLE_SPACE = 64
MINIMUM_ARM_INFORMATION_RATIO = 0.75
ARM_INFORMATION_TOLERANCE_FACTOR = 1e-12
MAX_ADMISSIBLE_VECTORS = 1_000_000
ALLOCATION_ANALYSIS_PLAN = {
    "schema": "mva-track2-allocation-analysis-plan/v2",
    "allocation_unit": ALLOCATION_UNIT,
    "admissible_space": "distinct_joint_arm_label_vectors",
    "candidate_vector": "pair_id_to_treatment_execution_id",
    "candidate_order": "compact_canonical_json_lexicographic",
    "context_fields": [
        "functional_assay_plate_id",
        "culture_batch_id",
        "functional_assay_run_id",
        "edit_event_id",
    ],
    "minimum_pairs_per_context": MINIMUM_PAIRS_PER_CONTEXT,
    "hard_constraints": [
        "one_vehicle_and_one_treatment_per_pair",
        "exact_plate_column_distribution_by_arm_within_context",
        "balanced_lower_column_orientation_within_context",
        "zero_signed_column_difference_within_context",
        "balanced_outer_column_orientation_within_context",
        "zero_signed_outer_column_difference_within_context",
        "balanced_dosing_first_orientation_within_context",
        "zero_signed_dosing_order_difference_within_context",
        "balanced_acquisition_first_orientation_within_context",
        "zero_signed_acquisition_order_difference_within_context",
    ],
    "allocation_information_filter": {
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
        "minimum_information_ratio": MINIMUM_ARM_INFORMATION_RATIO,
        "equivalent_max_variance_inflation_factor": "4_over_3",
        "equivalent_max_standard_error_inflation": "sqrt_4_over_3",
        "acceptance_rule": (
            "residual_norm_squared_plus_tolerance_gte_0.75_times_raw_"
            "centered_norm_squared"
        ),
        "tolerance_rule": (
            "1e-12_times_max_1_raw_centered_arm_norm_squared"
        ),
        "rank_deficient_context": "fail_closed",
        "local_survivors": (
            "all_distinct_candidates_passing_hard_constraints_and_"
            "information_rule"
        ),
        "joint_support_count": "product_of_local_survivor_counts",
        "minimum_joint_support_size": MINIMUM_ADMISSIBLE_SPACE,
        "insufficient_joint_support": "fail_closed_before_seed_index_selection",
    },
    "enumeration_safety": {
        "required_pair_count_parity_within_context": "even",
        "context_candidate_generation": (
            "lexicographic_combinations_of_exactly_half_the_pair_ids_with_"
            "dosing_later_member_as_treatment"
        ),
        "raw_local_candidate_count": "binomial_n_choose_n_over_2",
        "prospective_joint_upper_bound": "product_of_raw_local_candidate_counts",
        "maximum_candidate_vectors": MAX_ADMISSIBLE_VECTORS,
        "bound_check_timing": "before_candidate_generation",
        "bound_exceeded": "fail_closed",
    },
    "selection_generator": RANDOMIZATION_GENERATOR,
    "selection_rule": (
        "big_endian_uint256_seed_modulo_canonical_support_after_exact_"
        "modulo_bias_rejection"
    ),
    "uniform_index_mapping": {
        "seed_integer": "unsigned_big_endian_256_bit_integer",
        "support_order": "compact_canonical_json_lexicographic",
        "acceptance_limit": "floor_2_pow_256_over_n_times_n",
        "acceptance_rule": "seed_integer_strictly_less_than_acceptance_limit",
        "selected_index": "seed_integer_modulo_n",
        "rejected_seed": "fail_closed_without_redraw",
        "equiprobability": (
            "each_index_has_exactly_floor_2_pow_256_over_n_accepted_seeds"
        ),
    },
    "randomization_entropy_plan": {
        "seed_length_bits": 256,
        "required_sampling_distribution": "uniform_over_all_256_bit_keys",
        "independence_requirements": [
            "independent_of_assignment_manifest",
            "independent_of_observed_and_potential_outcomes",
        ],
        "timing_requirement": (
            "sampled_and_committed_before_reveal_and_before_any_exposure"
        ),
        "authenticity_requirement": (
            "externally_verifiable_attestation_required_for_nonsynthetic_pass"
        ),
    },
    "inference": {
        "treatment_application_unit": ALLOCATION_UNIT,
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
            "alpha": 0.05,
            "minimum_support_size": MINIMUM_ADMISSIBLE_SPACE,
            "observed_assignment_included": True,
        },
        "direction_rule": "observed_raw_mean_difference_lt_zero",
        "joint_decision_rule": "both_endpoints_must_pass",
        "missing_data": "no_imputation",
        "rank_deficient_design": "not_assessable",
    },
}
CLAIM_BOUNDARY = (
    "Declared pre-exposure rejection-sampled constrained-randomization replay "
    "and digest binding "
    "to prespecified conditional inference only; matching digests, timestamps, "
    "a revealed seed, well map, and selected arm vector do not prove seed honesty "
    "or unpredictability, absence of seed-shopping, external timestamp or record "
    "authenticity, physical placement, dosing or acquisition adherence, "
    "biological rescue, efficacy, or clinical benefit."
    " Treatment is applied per functional-execution well; randomization and "
    "analysis operate on biological pairs; biological replication is at the "
    "clone/edit-event level."
)
ROOT_KEYS = frozenset(
    {
        "schema",
        "allocation_id",
        "lock_state",
        "locked_at",
        "study_id",
        "assay_plan_sha256",
        "analysis_plan_sha256",
        "assignment_method",
        "assignment_algorithm",
        "assignment_input_commitment_sha256",
        "assignment_input_commitment_record",
        "assignment_manifest",
        "randomization",
        "allocation_unit",
        "commitment",
        "plate_dimensions",
        "assignments",
    }
)
COMMITMENT_KEYS = frozenset(
    {"mechanism", "record_id", "recorded_at", "plan_sha256"}
)
PRE_REVEAL_COMMITMENT_RECORD_KEYS = frozenset(
    {"mechanism", "record_id", "recorded_at", "digest_sha256"}
)
PLATE_KEYS = frozenset({"functional_assay_plate_id", "n_rows", "n_columns"})
MANIFEST_KEYS = frozenset({"schema", "plate_dimensions", "pair_units"})
PAIR_UNIT_KEYS = frozenset({"pair_id", "members"})
MANIFEST_MEMBER_KEYS = frozenset(
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
RANDOMIZATION_KEYS = frozenset(
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
RANDOMIZATION_RECORD_KEYS = frozenset(
    {"mechanism", "record_id", "recorded_at"}
)
ASSIGNMENT_KEYS = frozenset(
    {
        "functional_execution_id",
        "arm",
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
        "deviation_status",
    }
)
PLAN_HASH_KEYS = (
    "schema",
    "lock_state",
    "locked_at",
    "study_id",
    "assay_plan_sha256",
    "analysis_plan_sha256",
    "assignment_method",
    "assignment_algorithm",
    "assignment_input_commitment_sha256",
    "assignment_input_commitment_record",
    "assignment_manifest",
    "randomization",
    "allocation_unit",
    "commitment",
    "plate_dimensions",
    "assignments",
)


class ArmAllocationError(ValueError):
    """Raised when allocation metadata violates the strict schema."""


class SeedModuloBiasRejection(ArmAllocationError):
    """Raised when a 256-bit draw falls in the exact modulo-bias rejection tail."""


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ArmAllocationError(f"{field} must be a non-empty identifier")
    if not value.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise ArmAllocationError(f"{field} contains unsupported characters")
    if not value[0].isalpha():
        raise ArmAllocationError(f"{field} must start with a letter")
    return value


def _allocation_context_identifier(value: object, field: str) -> str:
    result = _identifier(value, field)
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", result) is None:
        raise ArmAllocationError(f"{field} must be a lowercase opaque identifier")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ArmAllocationError(f"{field} must be a positive integer")
    return value


def _sha256_text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ArmAllocationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ArmAllocationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArmAllocationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArmAllocationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _identifier_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ArmAllocationError(f"{field} must be an identifier array")
    parsed = tuple(_identifier(item, field) for item in value)
    if len(set(parsed)) != len(parsed):
        raise ArmAllocationError(f"{field} contains duplicate identifiers")
    return parsed


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], field: str) -> None:
    missing = sorted(expected - set(value))
    surplus = sorted(set(value) - expected)
    if missing:
        raise ArmAllocationError(f"{field} is missing required fields: {missing}")
    if surplus:
        raise ArmAllocationError(f"{field} has unsupported fields: {surplus}")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_json_array_sha256(items: Sequence[bytes]) -> str:
    """Hash a canonical JSON array without joining it into one document.

    Each item must already be canonical JSON bytes. The digest equals SHA-256
    of ``_canonical_json_bytes`` over the decoded list.
    """

    digest = hashlib.sha256()
    digest.update(b"[")
    for index, item in enumerate(items):
        if index:
            digest.update(b",")
        digest.update(item)
    digest.update(b"]")
    return digest.hexdigest()


def _left_to_right_binary64_sum(values: Iterable[float]) -> float:
    """Reduce floats in declared iteration order using binary64 additions."""

    total = 0.0
    for value in values:
        total += float(value)
    return total


def _arm_blind_identifier(value: object, field: str) -> str:
    result = _allocation_context_identifier(value, field)
    forbidden_tokens = {*ARMS, "control", "drug"}
    identifier_tokens = set(re.split(r"[._-]+", result))
    if forbidden_tokens & identifier_tokens or any(
        token in result for token in forbidden_tokens
    ):
        raise ArmAllocationError(f"{field} leaks an arm label")
    return result


def _seed_reveal(value: object, field: str = "seed_reveal_hex") -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ArmAllocationError(f"{field} must be 32 lowercase hexadecimal bytes")
    return value


def make_allocation_analysis_plan_sha256() -> str:
    """Return the digest of the frozen allocation-analysis semantics."""

    return hashlib.sha256(_canonical_json_bytes(ALLOCATION_ANALYSIS_PLAN)).hexdigest()


def make_seed_commitment(
    seed_reveal_hex: str,
    *,
    assignment_input_commitment_sha256: str | None = None,
) -> str:
    """Commit a 32-byte reveal without claiming its entropy was honest.

    The legacy branch exists only for constructors of pre-v3 fixtures. Accepted
    v3 allocation plans require the experiment-specific v3 commitment.
    """

    reveal = _seed_reveal(seed_reveal_hex)
    if assignment_input_commitment_sha256 is None:
        payload = b"mva-track2-seed-commitment/v1\0" + bytes.fromhex(reveal)
    else:
        input_commitment = _sha256_text(
            assignment_input_commitment_sha256,
            "assignment_input_commitment_sha256",
        )
        payload = (
            b"mva-track2-seed-commitment/v3\0"
            + input_commitment.encode("ascii")
            + b"\0"
            + bytes.fromhex(reveal)
        )
    return hashlib.sha256(payload).hexdigest()


def rejection_sampled_candidate_index(
    seed_reveal_hex: str,
    support_size: int,
) -> int:
    """Map an accepted uniform 256-bit draw exactly uniformly to support.

    The largest incomplete modulo bucket is rejected. No redraw is synthesized:
    callers must fail closed because this contract commits exactly one seed.
    """

    reveal = _seed_reveal(seed_reveal_hex)
    if (
        isinstance(support_size, bool)
        or not isinstance(support_size, int)
        or support_size < 1
    ):
        raise ArmAllocationError("support_size must be a positive integer")
    acceptance_limit = (SEED_SPACE_SIZE // support_size) * support_size
    seed_integer = int(reveal, 16)
    if seed_integer >= acceptance_limit:
        raise SeedModuloBiasRejection(
            "seed lies in the modulo-bias rejection region"
        )
    return seed_integer % support_size


def _parse_plate_dimensions(
    value: object,
    *,
    field: str,
    arm_blind: bool,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, int]]]:
    if not isinstance(value, list) or not value:
        raise ArmAllocationError(f"{field} must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    dimensions: dict[str, tuple[int, int]] = {}
    identifier_parser = _arm_blind_identifier if arm_blind else _allocation_context_identifier
    for item in value:
        if not isinstance(item, Mapping):
            raise ArmAllocationError(f"{field} item must be an object")
        _exact_keys(item, PLATE_KEYS, f"{field} item")
        plate_id = identifier_parser(
            item.get("functional_assay_plate_id"),
            f"{field}.functional_assay_plate_id",
        )
        if plate_id in dimensions:
            raise ArmAllocationError(f"{field} contains duplicate plate identifiers")
        n_rows = _positive_int(item.get("n_rows"), f"{field}.n_rows")
        n_columns = _positive_int(item.get("n_columns"), f"{field}.n_columns")
        if n_rows < 2 or n_columns < 2:
            raise ArmAllocationError("plate dimensions must each be at least two")
        dimensions[plate_id] = (n_rows, n_columns)
        normalized.append(
            {
                "functional_assay_plate_id": plate_id,
                "n_rows": n_rows,
                "n_columns": n_columns,
            }
        )
    normalized.sort(key=lambda item: item["functional_assay_plate_id"])
    return normalized, dimensions


def _normalize_assignment_manifest(
    manifest: object,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, tuple[int, int]]]:
    if not isinstance(manifest, Mapping):
        raise ArmAllocationError("assignment_manifest must be an object")
    _exact_keys(manifest, MANIFEST_KEYS, "assignment_manifest")
    if manifest.get("schema") != ASSIGNMENT_MANIFEST_SCHEMA:
        raise ArmAllocationError("assignment_manifest has the wrong schema")
    canonical_plates, plate_dimensions = _parse_plate_dimensions(
        manifest.get("plate_dimensions"),
        field="assignment_manifest.plate_dimensions",
        arm_blind=True,
    )
    raw_pairs = manifest.get("pair_units")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise ArmAllocationError("assignment_manifest.pair_units must be non-empty")

    pair_ids: set[str] = set()
    execution_ids: set[str] = set()
    biological_pairs: set[tuple[str, str, str]] = set()
    wells: set[tuple[str, int, int]] = set()
    dosing_orders: set[int] = set()
    acquisition_orders: set[int] = set()
    normalized_pairs: list[dict[str, Any]] = []
    identifier_fields = (
        "functional_execution_id",
        "edit_event_id",
        "clone_id",
        "culture_batch_id",
        "functional_assay_run_id",
        "allocation_block_id",
        "functional_assay_plate_id",
    )
    for raw_pair in raw_pairs:
        if not isinstance(raw_pair, Mapping):
            raise ArmAllocationError("assignment_manifest pair unit must be an object")
        _exact_keys(raw_pair, PAIR_UNIT_KEYS, "assignment_manifest pair unit")
        pair_id = _arm_blind_identifier(raw_pair.get("pair_id"), "pair_id")
        if pair_id in pair_ids:
            raise ArmAllocationError("assignment_manifest contains duplicate pair_id")
        pair_ids.add(pair_id)
        raw_members = raw_pair.get("members")
        if not isinstance(raw_members, list) or len(raw_members) != 2:
            raise ArmAllocationError("assignment_manifest pair must contain two members")
        normalized_members: list[dict[str, Any]] = []
        for raw_member in raw_members:
            if not isinstance(raw_member, Mapping):
                raise ArmAllocationError("assignment_manifest member must be an object")
            _exact_keys(
                raw_member,
                MANIFEST_MEMBER_KEYS,
                "assignment_manifest member",
            )
            member: dict[str, Any] = {
                name: _arm_blind_identifier(
                    raw_member.get(name), f"assignment_manifest.{name}"
                )
                for name in identifier_fields
            }
            execution_id = str(member["functional_execution_id"])
            if execution_id in execution_ids:
                raise ArmAllocationError(
                    "assignment_manifest contains duplicate functional_execution_id"
                )
            execution_ids.add(execution_id)
            plate_id = str(member["functional_assay_plate_id"])
            if plate_id not in plate_dimensions:
                raise ArmAllocationError("assignment_manifest references an unknown plate")
            row = _positive_int(
                raw_member.get("plate_row"), "assignment_manifest.plate_row"
            )
            column = _positive_int(
                raw_member.get("plate_column"), "assignment_manifest.plate_column"
            )
            n_rows, n_columns = plate_dimensions[plate_id]
            if row > n_rows or column > n_columns:
                raise ArmAllocationError("assignment_manifest well is outside the plate")
            well = (plate_id, row, column)
            if well in wells:
                raise ArmAllocationError("assignment_manifest contains a duplicate well")
            wells.add(well)
            dosing_order = _positive_int(
                raw_member.get("dosing_order"), "assignment_manifest.dosing_order"
            )
            acquisition_order = _positive_int(
                raw_member.get("acquisition_order"),
                "assignment_manifest.acquisition_order",
            )
            if dosing_order in dosing_orders:
                raise ArmAllocationError(
                    "assignment_manifest contains duplicate dosing_order"
                )
            if acquisition_order in acquisition_orders:
                raise ArmAllocationError(
                    "assignment_manifest contains duplicate acquisition_order"
                )
            dosing_orders.add(dosing_order)
            acquisition_orders.add(acquisition_order)
            member.update(
                plate_row=row,
                plate_column=column,
                dosing_order=dosing_order,
                acquisition_order=acquisition_order,
            )
            normalized_members.append(member)

        normalized_members.sort(key=lambda item: item["functional_execution_id"])
        shared_fields = (
            "edit_event_id",
            "clone_id",
            "culture_batch_id",
            "functional_assay_run_id",
            "allocation_block_id",
            "functional_assay_plate_id",
            "plate_row",
        )
        if any(
            normalized_members[0][name] != normalized_members[1][name]
            for name in shared_fields
        ):
            raise ArmAllocationError(
                "assignment_manifest pair members must share biological context"
            )
        plate_id = str(normalized_members[0]["functional_assay_plate_id"])
        n_rows, n_columns = plate_dimensions[plate_id]
        for derived in (
            lambda item: "edge"
            if item["plate_row"] in {1, n_rows}
            or item["plate_column"] in {1, n_columns}
            else "interior",
            lambda item: item["plate_column"] % 2,
            lambda item: item["plate_column"] <= n_columns / 2,
        ):
            if derived(normalized_members[0]) != derived(normalized_members[1]):
                raise ArmAllocationError(
                    "assignment_manifest pair members cross a position stratum"
                )
        if abs(
            normalized_members[0]["dosing_order"]
            - normalized_members[1]["dosing_order"]
        ) != 1 or abs(
            normalized_members[0]["acquisition_order"]
            - normalized_members[1]["acquisition_order"]
        ) != 1:
            raise ArmAllocationError(
                "assignment_manifest pair members must be adjacent in both orders"
            )
        biological_key = (
            str(normalized_members[0]["edit_event_id"]),
            str(normalized_members[0]["clone_id"]),
            str(normalized_members[0]["functional_assay_run_id"]),
        )
        if biological_key in biological_pairs:
            raise ArmAllocationError(
                "assignment_manifest contains duplicate biological pairs"
            )
        biological_pairs.add(biological_key)
        normalized_pairs.append(
            {"pair_id": pair_id, "members": normalized_members}
        )

    normalized_pairs.sort(key=lambda item: item["pair_id"])
    expected_orders = set(range(1, 2 * len(normalized_pairs) + 1))
    if dosing_orders != expected_orders or acquisition_orders != expected_orders:
        raise ArmAllocationError(
            "assignment_manifest orders must be contiguous across every member"
        )
    used_plates = {
        str(member["functional_assay_plate_id"])
        for pair in normalized_pairs
        for member in pair["members"]
    }
    if used_plates != set(plate_dimensions):
        raise ArmAllocationError("assignment_manifest contains an unused plate")
    canonical = {
        "schema": ASSIGNMENT_MANIFEST_SCHEMA,
        "plate_dimensions": canonical_plates,
        "pair_units": normalized_pairs,
    }
    return canonical, normalized_pairs, plate_dimensions


def _orientation_is_balanced(counts: Counter[str]) -> bool:
    return abs(counts["vehicle"] - counts["treatment"]) <= 1


def _context_candidate_is_admissible(
    pairs: list[dict[str, Any]],
    treatment_by_pair: Mapping[str, str],
    plate_dimensions: Mapping[str, tuple[int, int]],
) -> bool:
    by_arm_columns: dict[str, Counter[int]] = {
        "vehicle": Counter(),
        "treatment": Counter(),
    }
    orientations: dict[str, Counter[str]] = defaultdict(Counter)
    signed: dict[str, list[int]] = defaultdict(list)
    for pair in pairs:
        members = pair["members"]
        treatment_id = treatment_by_pair[str(pair["pair_id"])]
        treatment = next(
            member
            for member in members
            if member["functional_execution_id"] == treatment_id
        )
        vehicle = next(member for member in members if member is not treatment)
        by_arm_columns["vehicle"][int(vehicle["plate_column"])] += 1
        by_arm_columns["treatment"][int(treatment["plate_column"])] += 1
        for metric, field in (
            ("column_lower", "plate_column"),
            ("dosing_first", "dosing_order"),
            ("acquisition_first", "acquisition_order"),
        ):
            vehicle_value = int(vehicle[field])
            treatment_value = int(treatment[field])
            lower_arm = "vehicle" if vehicle_value < treatment_value else "treatment"
            orientations[metric][lower_arm] += 1
            signed[metric].append(treatment_value - vehicle_value)
        plate_id = str(vehicle["functional_assay_plate_id"])
        n_columns = plate_dimensions[plate_id][1]
        vehicle_distance = abs(2 * int(vehicle["plate_column"]) - (n_columns + 1))
        treatment_distance = abs(
            2 * int(treatment["plate_column"]) - (n_columns + 1)
        )
        if vehicle_distance != treatment_distance:
            outer_arm = (
                "vehicle" if vehicle_distance > treatment_distance else "treatment"
            )
            orientations["column_outer"][outer_arm] += 1
        signed["column_outer"].append(treatment_distance - vehicle_distance)
    return (
        by_arm_columns["vehicle"] == by_arm_columns["treatment"]
        and all(_orientation_is_balanced(counts) for counts in orientations.values())
        and all(sum(values) == 0 for values in signed.values())
    )


def _context_information_basis(
    pairs: list[dict[str, Any]],
) -> tuple[list[str], list[list[float]]]:
    members = sorted(
        (member for pair in pairs for member in pair["members"]),
        key=lambda item: item["functional_execution_id"],
    )
    count = float(len(members))
    dosing_mean = _left_to_right_binary64_sum(
        float(member["dosing_order"]) for member in members
    ) / count
    acquisition_mean = (
        _left_to_right_binary64_sum(
            float(member["acquisition_order"]) for member in members
        )
        / count
    )
    design: list[list[float]] = []
    for member in members:
        centered_dosing = float(member["dosing_order"]) - dosing_mean
        centered_acquisition = (
            float(member["acquisition_order"]) - acquisition_mean
        )
        row = [
            1.0,
            centered_dosing,
            centered_dosing * centered_dosing,
            centered_acquisition,
            centered_acquisition * centered_acquisition,
            centered_dosing * centered_acquisition,
        ]
        if not all(math.isfinite(value) for value in row):
            raise ArmAllocationError(
                "assignment_manifest context nuisance design is malformed"
            )
        design.append(row)
    return [str(member["functional_execution_id"]) for member in members], design


def _two_pass_mgs_basis(design: list[list[float]]) -> list[list[float]]:
    if not design or len(design) <= len(design[0]) or any(
        len(row) != len(design[0]) for row in design
    ):
        raise ArmAllocationError(
            "assignment_manifest context nuisance design is rank deficient"
        )
    columns = [
        [float(row[column_index]) for row in design]
        for column_index in range(len(design[0]))
    ]
    q_columns: list[list[float]] = []
    for column in columns:
        vector = list(column)
        original_norm = math.sqrt(
            _left_to_right_binary64_sum(value * value for value in vector)
        )
        for q_column in q_columns:
            coefficient = _left_to_right_binary64_sum(
                q * value for q, value in zip(q_column, vector, strict=True)
            )
            vector = [
                value - coefficient * q
                for value, q in zip(vector, q_column, strict=True)
            ]
        for q_column in q_columns:
            correction = _left_to_right_binary64_sum(
                q * value for q, value in zip(q_column, vector, strict=True)
            )
            vector = [
                value - correction * q
                for value, q in zip(vector, q_column, strict=True)
            ]
        norm = math.sqrt(
            _left_to_right_binary64_sum(value * value for value in vector)
        )
        if norm <= 1e-10 * max(1.0, original_norm):
            raise ArmAllocationError(
                "assignment_manifest context nuisance design is rank deficient"
            )
        q_columns.append([value / norm for value in vector])
    return q_columns


def _context_candidate_has_arm_information(
    *,
    execution_ids: list[str],
    q_columns: list[list[float]],
    treatment_by_pair: Mapping[str, str],
) -> bool:
    treatment_ids = set(treatment_by_pair.values())
    arm_indicator = [
        1.0 if execution_id in treatment_ids else -1.0
        for execution_id in execution_ids
    ]
    indicator_mean = _left_to_right_binary64_sum(arm_indicator) / float(
        len(arm_indicator)
    )
    centered = [value - indicator_mean for value in arm_indicator]
    raw_norm_squared = _left_to_right_binary64_sum(
        value * value for value in centered
    )
    tolerance = ARM_INFORMATION_TOLERANCE_FACTOR * max(1.0, raw_norm_squared)
    if raw_norm_squared <= tolerance:
        raise ArmAllocationError(
            "assignment_manifest candidate has zero centered arm information"
        )
    projections = [
        _left_to_right_binary64_sum(
            q * value for q, value in zip(q_column, centered, strict=True)
        )
        for q_column in q_columns
    ]
    residual = [
        value
        - _left_to_right_binary64_sum(
            q_columns[column_index][row_index] * projections[column_index]
            for column_index in range(len(q_columns))
        )
        for row_index, value in enumerate(centered)
    ]
    residual_norm_squared = _left_to_right_binary64_sum(
        value * value for value in residual
    )
    return residual_norm_squared + tolerance >= (
        MINIMUM_ARM_INFORMATION_RATIO * raw_norm_squared
    )


def _admissible_candidate_bytes(
    assignment_manifest: object,
) -> tuple[list[bytes], str]:
    canonical, pairs, plate_dimensions = _normalize_assignment_manifest(
        assignment_manifest
    )
    del canonical
    by_context: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        member = pair["members"][0]
        context = (
            str(member["functional_assay_plate_id"]),
            str(member["culture_batch_id"]),
            str(member["functional_assay_run_id"]),
            str(member["edit_event_id"]),
        )
        by_context[context].append(pair)

    ordered_contexts = sorted(by_context.items())
    prospective_joint_upper_bound = 1
    for _context, context_pairs in ordered_contexts:
        n_pairs = len(context_pairs)
        if n_pairs < MINIMUM_PAIRS_PER_CONTEXT:
            raise ArmAllocationError(
                "assignment_manifest requires at least six pairs per context"
            )
        if n_pairs % 2:
            raise ArmAllocationError(
                "assignment_manifest requires an even pair count per context"
            )
        raw_local_count = math.comb(n_pairs, n_pairs // 2)
        if (
            raw_local_count > MAX_ADMISSIBLE_VECTORS
            or prospective_joint_upper_bound
            > MAX_ADMISSIBLE_VECTORS // raw_local_count
        ):
            raise ArmAllocationError(
                "prospective arm-vector space exceeds verifier limit"
            )
        prospective_joint_upper_bound *= raw_local_count

    local_candidates: list[list[tuple[tuple[str, str], ...]]] = []
    for context, context_pairs in ordered_contexts:
        context_pairs.sort(key=lambda item: item["pair_id"])
        execution_ids, information_design = _context_information_basis(context_pairs)
        information_basis = _two_pass_mgs_basis(information_design)
        valid: list[tuple[tuple[str, str], ...]] = []
        dosing_ordered_member_ids = [
            tuple(
                str(member["functional_execution_id"])
                for member in sorted(
                    pair["members"], key=lambda item: item["dosing_order"]
                )
            )
            for pair in context_pairs
        ]
        pair_indexes = range(len(context_pairs))
        for dosing_later_treatment_indexes in itertools.combinations(
            pair_indexes, len(context_pairs) // 2
        ):
            dosing_later = set(dosing_later_treatment_indexes)
            selected_treatments = tuple(
                member_ids[1] if pair_index in dosing_later else member_ids[0]
                for pair_index, member_ids in enumerate(dosing_ordered_member_ids)
            )
            treatment_by_pair = {
                str(pair["pair_id"]): treatment_id
                for pair, treatment_id in zip(
                    context_pairs, selected_treatments, strict=True
                )
            }
            if not _context_candidate_is_admissible(
                context_pairs, treatment_by_pair, plate_dimensions
            ):
                continue
            if not _context_candidate_has_arm_information(
                execution_ids=execution_ids,
                q_columns=information_basis,
                treatment_by_pair=treatment_by_pair,
            ):
                continue
            valid.append(
                tuple(sorted(treatment_by_pair.items(), key=lambda item: item[0]))
            )
        if not valid:
            raise ArmAllocationError(
                "assignment_manifest context has no information-admissible arm "
                f"vectors: {context}"
            )
        local_candidates.append(valid)

    joint_count = 1
    for candidates in local_candidates:
        joint_count *= len(candidates)
    if joint_count < MINIMUM_ADMISSIBLE_SPACE:
        raise ArmAllocationError(
            "admissible arm-vector space has fewer than 64 candidates"
        )
    if joint_count > MAX_ADMISSIBLE_VECTORS:
        raise ArmAllocationError("admissible arm-vector space exceeds verifier limit")

    encoded: set[bytes] = set()
    for selected_contexts in itertools.product(*local_candidates):
        flattened = sorted(
            (item for context in selected_contexts for item in context),
            key=lambda item: item[0],
        )
        vector = [
            {"pair_id": pair_id, "treatment_execution_id": execution_id}
            for pair_id, execution_id in flattened
        ]
        encoded.add(_canonical_json_bytes(vector))
    candidates = sorted(encoded)
    encoded.clear()
    space_sha256 = _canonical_json_array_sha256(candidates)
    return candidates, space_sha256


def enumerate_admissible_assignment_vectors(
    assignment_manifest: object,
) -> tuple[tuple[bytes, ...], str]:
    """Return exact canonical candidate bytes and their joint-space digest."""

    candidates, digest = _admissible_candidate_bytes(assignment_manifest)
    return tuple(candidates), digest


def replay_seeded_assignment(
    *,
    assignment_manifest: object,
    assignment_input_commitment_sha256: str,
    seed_reveal_hex: str,
) -> dict[str, Any]:
    """Recompute support and its exact rejection-sampled seed index."""

    input_commitment = _sha256_text(
        assignment_input_commitment_sha256,
        "assignment_input_commitment_sha256",
    )
    reveal = _seed_reveal(seed_reveal_hex)
    candidates, space_sha256 = _admissible_candidate_bytes(assignment_manifest)
    del input_commitment
    selected_index = rejection_sampled_candidate_index(reveal, len(candidates))
    winner = candidates[selected_index]
    return {
        "admissible_space_count": len(candidates),
        "admissible_space_sha256": space_sha256,
        "selected_index": selected_index,
        "selected_vector": json.loads(
            winner.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        ),
        "selected_vector_sha256": hashlib.sha256(winner).hexdigest(),
    }


def _canonical_plan_payload(plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise ArmAllocationError("preexposure_allocation must be an object")
    plates = plan.get("plate_dimensions")
    assignments = plan.get("assignments")
    if not isinstance(plates, list) or not all(isinstance(item, Mapping) for item in plates):
        raise ArmAllocationError("plate_dimensions must be an object array")
    if not isinstance(assignments, list) or not all(
        isinstance(item, Mapping) for item in assignments
    ):
        raise ArmAllocationError("assignments must be an object array")
    payload: dict[str, Any] = {key: plan.get(key) for key in PLAN_HASH_KEYS}
    payload["locked_at"] = _utc(plan.get("locked_at"), "locked_at").isoformat()
    payload["plate_dimensions"] = sorted(
        (dict(item) for item in plates),
        key=lambda item: str(item.get("functional_assay_plate_id")),
    )
    payload["assignments"] = sorted(
        (dict(item) for item in assignments),
        key=lambda item: str(item.get("functional_execution_id")),
    )
    commitment = plan.get("commitment")
    if isinstance(commitment, Mapping):
        payload["commitment"] = {
            "mechanism": commitment.get("mechanism"),
            "record_id": commitment.get("record_id"),
            "recorded_at": _utc(
                commitment.get("recorded_at"), "commitment.recorded_at"
            ).isoformat(),
        }
    input_commitment_record = plan.get("assignment_input_commitment_record")
    if isinstance(input_commitment_record, Mapping):
        payload["assignment_input_commitment_record"] = {
            **dict(input_commitment_record),
            "recorded_at": _utc(
                input_commitment_record.get("recorded_at"),
                "assignment_input_commitment_record.recorded_at",
            ).isoformat(),
        }
    manifest = plan.get("assignment_manifest")
    if isinstance(manifest, Mapping):
        payload["assignment_manifest"] = _normalize_assignment_manifest(manifest)[0]
    randomization = plan.get("randomization")
    if isinstance(randomization, Mapping):
        normalized_randomization = dict(randomization)
        for name in ("seed_committed_at", "seed_revealed_at"):
            normalized_randomization[name] = _utc(
                randomization.get(name), f"randomization.{name}"
            ).isoformat()
        record = randomization.get("record")
        if isinstance(record, Mapping):
            normalized_randomization["record"] = {
                **dict(record),
                "recorded_at": _utc(
                    record.get("recorded_at"),
                    "randomization.record.recorded_at",
                ).isoformat(),
            }
        seed_commitment_record = randomization.get("seed_commitment_record")
        if isinstance(seed_commitment_record, Mapping):
            normalized_randomization["seed_commitment_record"] = {
                **dict(seed_commitment_record),
                "recorded_at": _utc(
                    seed_commitment_record.get("recorded_at"),
                    "randomization.seed_commitment_record.recorded_at",
                ).isoformat(),
            }
        payload["randomization"] = normalized_randomization
    return payload


def make_preexposure_allocation_id(plan: Mapping[str, Any]) -> str:
    """Return an order-invariant digest of every semantic plan field."""

    encoded = json.dumps(
        _canonical_plan_payload(plan),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return "allocation-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def make_assignment_input_commitment(
    *,
    study_id: str,
    assay_plan_sha256: str,
    assignment_method: str,
    assignment_algorithm: str,
    analysis_plan_sha256: str | None = None,
    assignment_manifest: Mapping[str, Any] | None = None,
    allocation_unit: str = ALLOCATION_UNIT,
    functional_execution_ids: list[str] | None = None,
) -> str:
    """Bind the full canonical arm-blind assignment input.

    The legacy execution-id-only branch exists solely so older synthetic fixture
    constructors can finish building an object before a caller upgrades it. The
    assessor never accepts that legacy shape as a verified randomization.
    """

    if assignment_manifest is None:
        if functional_execution_ids is None:
            raise ArmAllocationError("assignment_manifest is required")
        payload = {
            "schema": "mva-track2-allocation-input-commitment/v1",
            "study_id": study_id,
            "assay_plan_sha256": assay_plan_sha256,
            "assignment_method": assignment_method,
            "assignment_algorithm": assignment_algorithm,
            "functional_execution_ids": sorted(functional_execution_ids),
        }
        return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()

    declared_analysis_plan = _sha256_text(
        analysis_plan_sha256, "analysis_plan_sha256"
    )
    canonical_manifest = _normalize_assignment_manifest(assignment_manifest)[0]
    candidates, support_sha256 = _admissible_candidate_bytes(canonical_manifest)
    payload = {
        "schema": "mva-track2-allocation-input-commitment/v4",
        "study_id": _identifier(study_id, "study_id"),
        "assay_plan_sha256": _sha256_text(
            assay_plan_sha256, "assay_plan_sha256"
        ),
        "analysis_plan_sha256": declared_analysis_plan,
        "assignment_method": assignment_method,
        "assignment_algorithm": assignment_algorithm,
        "randomization_generator": RANDOMIZATION_GENERATOR,
        "candidate_order": ALLOCATION_ANALYSIS_PLAN["candidate_order"],
        "selection_rule": ALLOCATION_ANALYSIS_PLAN["selection_rule"],
        "allocation_unit": allocation_unit,
        "assignment_manifest": canonical_manifest,
        "admissible_space_count": len(candidates),
        "admissible_space_sha256": support_sha256,
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _result(
    *,
    status: str,
    reason: str,
    n_planned_executions: int,
    n_assignments: int,
    synthetic_only: bool,
    entropy_authenticity: str | None = None,
    software_contract_verified: bool | None = None,
    allocation_id: str | None = None,
    allocation_fingerprint: str | None = None,
    assignments: list[dict[str, Any]] | None = None,
    balance_checks: list[dict[str, Any]] | None = None,
    skipped: bool = False,
) -> dict[str, Any]:
    passed = status == "pass"
    conditional_software_contract_verified = bool(
        passed and n_planned_executions > 0
        if software_contract_verified is None
        else software_contract_verified
    )
    entropy_authenticity_verified = bool(
        entropy_authenticity
        and entropy_authenticity != RANDOMIZATION_ENTROPY_AUTHENTICITY
    )
    return {
        "schema": SCHEMA,
        "synthetic_only": synthetic_only,
        "claim_boundary": CLAIM_BOUNDARY,
        "treatment_application_unit": ALLOCATION_UNIT,
        "randomization_unit": "biological_pair",
        "analysis_unit": "biological_pair",
        "biological_replication_unit": "clone_edit_event",
        "status": status,
        "program_effect": "pass" if passed else "hold",
        "reason": reason,
        "allocation_verified": passed and n_planned_executions > 0,
        "conditional_software_contract_verified": (
            conditional_software_contract_verified
        ),
        "entropy_authenticity": entropy_authenticity,
        "entropy_authenticity_verified": entropy_authenticity_verified,
        "authenticated_randomization_verified": (
            conditional_software_contract_verified
            and entropy_authenticity_verified
        ),
        "advancement_blocked": not passed,
        "skipped": skipped,
        "n_planned_executions": n_planned_executions,
        "n_assignments": n_assignments,
        "allocation_id": allocation_id,
        "allocation_fingerprint": allocation_fingerprint,
        "assignments": assignments or [],
        "balance_checks": balance_checks or [],
    }


def skipped_preexposure_allocation(reason: str) -> dict[str, Any]:
    """Return an explicit non-assessment when an earlier stop has priority."""

    return _result(
        status="not_assessable",
        reason=reason,
        n_planned_executions=0,
        n_assignments=0,
        synthetic_only=True,
        skipped=True,
    )


def _planned_execution_context(
    table: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], datetime | None]:
    planned: dict[str, dict[str, Any]] = {}
    starts: list[datetime] = []

    rows = table.get("rows")
    if not isinstance(rows, list):
        raise ArmAllocationError("measured-exposure rows must be an array")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ArmAllocationError("measured-exposure row must be an object")
        supports = _identifier_list(
            row.get("supports_functional_execution_ids", []),
            "supports_functional_execution_ids",
        )
        if not supports:
            continue
        _identifier(row.get("exposure_profile_id"), "exposure_profile_id")
        _identifier(row.get("measurement_execution_id"), "measurement_execution_id")
        batch = _identifier(row.get("culture_batch_id"), "culture_batch_id")
        run_ids = _identifier_list(
            row.get("functional_assay_run_ids", []), "functional_assay_run_ids"
        )
        if not run_ids:
            raise ArmAllocationError("planned treatment execution has no assay run")
        started = _utc(row.get("exposure_started_at"), "exposure_started_at")
        starts.append(started)
        for execution_id in supports:
            if execution_id in planned:
                planned[execution_id] = {
                    "arm": "conflict",
                    "culture_batch_id": batch,
                    "allowed_run_ids": frozenset(run_ids),
                }
                continue
            planned[execution_id] = {
                "arm": "treatment",
                "culture_batch_id": batch,
                "allowed_run_ids": frozenset(run_ids),
            }

    controls = table.get("vehicle_controls", [])
    if not isinstance(controls, list):
        raise ArmAllocationError("vehicle_controls must be an array")
    for control in controls:
        if not isinstance(control, Mapping):
            raise ArmAllocationError("vehicle control must be an object")
        supports = _identifier_list(
            control.get("supports_functional_execution_ids", []),
            "supports_functional_execution_ids",
        )
        if not supports:
            continue
        _identifier(control.get("exposure_profile_id"), "exposure_profile_id")
        _identifier(control.get("control_execution_id"), "control_execution_id")
        batch = _identifier(control.get("culture_batch_id"), "culture_batch_id")
        run_ids = _identifier_list(
            control.get("functional_assay_run_ids", []), "functional_assay_run_ids"
        )
        if not run_ids:
            raise ArmAllocationError("planned vehicle execution has no assay run")
        started = _utc(control.get("exposure_started_at"), "exposure_started_at")
        starts.append(started)
        for execution_id in supports:
            if execution_id in planned:
                planned[execution_id] = {
                    "arm": "conflict",
                    "culture_batch_id": batch,
                    "allowed_run_ids": frozenset(run_ids),
                }
                continue
            planned[execution_id] = {
                "arm": "vehicle",
                "culture_batch_id": batch,
                "allowed_run_ids": frozenset(run_ids),
            }
    return planned, min(starts) if starts else None


def _balanced(arms: list[str]) -> bool:
    counts = Counter(arms)
    return bool(counts["vehicle"] and counts["treatment"]) and abs(
        counts["vehicle"] - counts["treatment"]
    ) <= 1


def assess_preexposure_allocation(table: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a digest-backed, paired allocation before exposure starts."""

    if not isinstance(table, Mapping) or table.get("schema") != TABLE_SCHEMA:
        raise ArmAllocationError("allocation accepts the measured-exposure table only")
    synthetic_only = table.get("privacy_class") == "synthetic"
    entropy_authenticity: str | None = None

    def _assessment_result(**values: Any) -> dict[str, Any]:
        return _result(
            synthetic_only=synthetic_only,
            entropy_authenticity=entropy_authenticity,
            **values,
        )

    planned, earliest_exposure = _planned_execution_context(table)
    if not planned:
        # No functional executions were planned — nothing requires an
        # allocation, but a bare "pass" is a footgun for callers that read
        # status without allocation_verified. Not assessable is honest.
        return _assessment_result(
            status="not_assessable",
            reason="no_planned_functional_executions",
            n_planned_executions=0,
            n_assignments=0,
        )

    raw_plan = table.get("preexposure_allocation")
    if raw_plan is None:
        return _assessment_result(
            status="not_assessable",
            reason="preexposure_allocation_missing",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    if not isinstance(raw_plan, Mapping):
        raise ArmAllocationError("preexposure_allocation must be an object")
    _exact_keys(raw_plan, ROOT_KEYS, "preexposure_allocation")
    if raw_plan.get("schema") != PLAN_SCHEMA:
        raise ArmAllocationError("preexposure_allocation has the wrong schema")
    if raw_plan.get("lock_state") != "locked":
        return _assessment_result(
            status="not_assessable",
            reason="preexposure_allocation_unlocked",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    if raw_plan.get("assignment_method") not in ASSIGNMENT_METHODS:
        raise ArmAllocationError("assignment_method is not in the allowed vocabulary")
    if raw_plan.get("assignment_algorithm") not in ASSIGNMENT_ALGORITHMS:
        raise ArmAllocationError("assignment_algorithm is not in the allowed vocabulary")
    expected_algorithm = "paired_constrained_seed_index_rejection_v1"
    if raw_plan.get("assignment_algorithm") != expected_algorithm:
        raise ArmAllocationError("assignment method and algorithm do not agree")
    declared_study_id = _identifier(raw_plan.get("study_id"), "study_id")
    declared_assay_plan = _sha256_text(
        raw_plan.get("assay_plan_sha256"), "assay_plan_sha256"
    )
    declared_analysis_plan = _sha256_text(
        raw_plan.get("analysis_plan_sha256"), "analysis_plan_sha256"
    )
    if declared_analysis_plan != make_allocation_analysis_plan_sha256():
        return _assessment_result(
            status="not_assessable",
            reason="allocation_analysis_plan_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    if raw_plan.get("allocation_unit") != ALLOCATION_UNIT:
        raise ArmAllocationError("allocation_unit must be functional_execution_well")
    canonical_manifest, manifest_pairs, manifest_plate_dimensions = (
        _normalize_assignment_manifest(raw_plan.get("assignment_manifest"))
    )
    declared_input_commitment = _sha256_text(
        raw_plan.get("assignment_input_commitment_sha256"),
        "assignment_input_commitment_sha256",
    )
    expected_input_commitment = make_assignment_input_commitment(
        study_id=declared_study_id,
        assay_plan_sha256=declared_assay_plan,
        analysis_plan_sha256=declared_analysis_plan,
        assignment_method=str(raw_plan.get("assignment_method")),
        assignment_algorithm=str(raw_plan.get("assignment_algorithm")),
        allocation_unit=ALLOCATION_UNIT,
        assignment_manifest=canonical_manifest,
    )
    if declared_input_commitment != expected_input_commitment:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_input_commitment_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    input_commitment_record = raw_plan.get("assignment_input_commitment_record")
    if not isinstance(input_commitment_record, Mapping):
        raise ArmAllocationError(
            "assignment_input_commitment_record must be an object"
        )
    _exact_keys(
        input_commitment_record,
        PRE_REVEAL_COMMITMENT_RECORD_KEYS,
        "assignment_input_commitment_record",
    )
    if input_commitment_record.get("mechanism") not in COMMITMENT_MECHANISMS:
        raise ArmAllocationError(
            "assignment input commitment record mechanism is not supported"
        )
    input_commitment_record_id = _identifier(
        input_commitment_record.get("record_id"),
        "assignment_input_commitment_record.record_id",
    )
    input_commitment_recorded_at = _utc(
        input_commitment_record.get("recorded_at"),
        "assignment_input_commitment_record.recorded_at",
    )
    recorded_input_digest = _sha256_text(
        input_commitment_record.get("digest_sha256"),
        "assignment_input_commitment_record.digest_sha256",
    )
    if recorded_input_digest != declared_input_commitment:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_input_commitment_record_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )

    locked_at = _utc(raw_plan.get("locked_at"), "locked_at")
    commitment = raw_plan.get("commitment")
    if not isinstance(commitment, Mapping):
        raise ArmAllocationError("commitment must be an object")
    _exact_keys(commitment, COMMITMENT_KEYS, "commitment")
    if commitment.get("mechanism") not in COMMITMENT_MECHANISMS:
        raise ArmAllocationError("commitment mechanism is not supported")
    commitment_record_id = _identifier(
        commitment.get("record_id"), "commitment.record_id"
    )
    recorded_at = _utc(commitment.get("recorded_at"), "commitment.recorded_at")
    if earliest_exposure is None:
        raise ArmAllocationError("planned executions have no exposure start")
    if locked_at > recorded_at or recorded_at >= earliest_exposure:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_commitment_not_preexposure",
            n_planned_executions=len(planned),
            n_assignments=0,
        )

    randomization = raw_plan.get("randomization")
    if not isinstance(randomization, Mapping):
        raise ArmAllocationError("randomization must be an object")
    _exact_keys(randomization, RANDOMIZATION_KEYS, "randomization")
    if randomization.get("generator") != RANDOMIZATION_GENERATOR:
        raise ArmAllocationError("randomization generator is not supported")
    raw_entropy_authenticity = randomization.get("entropy_authenticity")
    if raw_entropy_authenticity != RANDOMIZATION_ENTROPY_AUTHENTICITY:
        raise ArmAllocationError("entropy_authenticity must be not_attested")
    entropy_authenticity = str(raw_entropy_authenticity)
    seed_commitment = _sha256_text(
        randomization.get("seed_commitment_sha256"),
        "randomization.seed_commitment_sha256",
    )
    seed_reveal = _seed_reveal(
        randomization.get("seed_reveal_hex"), "randomization.seed_reveal_hex"
    )
    seed_committed_at = _utc(
        randomization.get("seed_committed_at"), "randomization.seed_committed_at"
    )
    seed_revealed_at = _utc(
        randomization.get("seed_revealed_at"), "randomization.seed_revealed_at"
    )
    seed_commitment_record = randomization.get("seed_commitment_record")
    if not isinstance(seed_commitment_record, Mapping):
        raise ArmAllocationError(
            "randomization.seed_commitment_record must be an object"
        )
    _exact_keys(
        seed_commitment_record,
        PRE_REVEAL_COMMITMENT_RECORD_KEYS,
        "randomization.seed_commitment_record",
    )
    if seed_commitment_record.get("mechanism") not in COMMITMENT_MECHANISMS:
        raise ArmAllocationError(
            "randomization seed commitment record mechanism is not supported"
        )
    seed_commitment_record_id = _identifier(
        seed_commitment_record.get("record_id"),
        "randomization.seed_commitment_record.record_id",
    )
    seed_commitment_recorded_at = _utc(
        seed_commitment_record.get("recorded_at"),
        "randomization.seed_commitment_record.recorded_at",
    )
    recorded_seed_digest = _sha256_text(
        seed_commitment_record.get("digest_sha256"),
        "randomization.seed_commitment_record.digest_sha256",
    )
    if (
        recorded_seed_digest != seed_commitment
        or seed_commitment_recorded_at != seed_committed_at
    ):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_seed_commitment_record_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    randomization_record = randomization.get("record")
    if not isinstance(randomization_record, Mapping):
        raise ArmAllocationError("randomization.record must be an object")
    _exact_keys(
        randomization_record,
        RANDOMIZATION_RECORD_KEYS,
        "randomization.record",
    )
    if randomization_record.get("mechanism") not in COMMITMENT_MECHANISMS:
        raise ArmAllocationError("randomization record mechanism is not supported")
    randomization_record_id = _identifier(
        randomization_record.get("record_id"), "randomization.record.record_id"
    )
    randomization_recorded_at = _utc(
        randomization_record.get("recorded_at"),
        "randomization.record.recorded_at",
    )
    declared_space_count = _positive_int(
        randomization.get("admissible_space_count"),
        "randomization.admissible_space_count",
    )
    declared_space_sha256 = _sha256_text(
        randomization.get("admissible_space_sha256"),
        "randomization.admissible_space_sha256",
    )
    declared_vector_sha256 = _sha256_text(
        randomization.get("selected_vector_sha256"),
        "randomization.selected_vector_sha256",
    )
    if len(
        {
            input_commitment_record_id,
            seed_commitment_record_id,
            randomization_record_id,
            commitment_record_id,
        }
    ) != 4:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_commitment_record_id_reuse",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    if not (
        locked_at <= input_commitment_recorded_at
        < seed_committed_at
        < seed_revealed_at
        <= randomization_recorded_at
        <= recorded_at
        < earliest_exposure
    ):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_randomization_timeline_invalid",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    if seed_commitment != make_seed_commitment(
        seed_reveal,
        assignment_input_commitment_sha256=declared_input_commitment,
    ):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_seed_commitment_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    try:
        replay = replay_seeded_assignment(
            assignment_manifest=canonical_manifest,
            assignment_input_commitment_sha256=declared_input_commitment,
            seed_reveal_hex=seed_reveal,
        )
    except SeedModuloBiasRejection:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_seed_rejected_for_modulo_bias",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    if (
        declared_space_count != replay["admissible_space_count"]
        or declared_space_sha256 != replay["admissible_space_sha256"]
    ):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_candidate_space_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )
    if declared_vector_sha256 != replay["selected_vector_sha256"]:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_randomization_selection_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )

    canonical_plates, plate_dimensions = _parse_plate_dimensions(
        raw_plan.get("plate_dimensions"), field="plate_dimensions", arm_blind=False
    )
    if (
        canonical_plates != canonical_manifest["plate_dimensions"]
        or plate_dimensions != manifest_plate_dimensions
    ):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_manifest_plate_mismatch",
            n_planned_executions=len(planned),
            n_assignments=0,
        )

    raw_assignments = raw_plan.get("assignments")
    if not isinstance(raw_assignments, list) or not raw_assignments:
        raise ArmAllocationError("assignments must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_wells: set[tuple[str, int, int]] = set()
    dosing_orders: set[int] = set()
    acquisition_orders: set[int] = set()
    execution_mismatch = False
    deviation = False
    for assignment in raw_assignments:
        if not isinstance(assignment, Mapping):
            raise ArmAllocationError("allocation assignment must be an object")
        _exact_keys(assignment, ASSIGNMENT_KEYS, "allocation assignment")
        execution_id = _identifier(
            assignment.get("functional_execution_id"), "functional_execution_id"
        )
        if execution_id in seen_ids:
            raise ArmAllocationError("duplicate allocation functional_execution_id")
        seen_ids.add(execution_id)
        arm = assignment.get("arm")
        if arm not in ARMS:
            raise ArmAllocationError("allocation arm must be vehicle or treatment")
        edit_event_id = _identifier(assignment.get("edit_event_id"), "edit_event_id")
        clone_id = _identifier(assignment.get("clone_id"), "clone_id")
        batch_id = _identifier(assignment.get("culture_batch_id"), "culture_batch_id")
        run_id = _identifier(
            assignment.get("functional_assay_run_id"), "functional_assay_run_id"
        )
        block_id = _allocation_context_identifier(
            assignment.get("allocation_block_id"), "allocation_block_id"
        )
        plate_id = _allocation_context_identifier(
            assignment.get("functional_assay_plate_id"),
            "functional_assay_plate_id",
        )
        if plate_id not in plate_dimensions:
            raise ArmAllocationError("assignment references an unknown plate")
        row = _positive_int(assignment.get("plate_row"), "plate_row")
        column = _positive_int(assignment.get("plate_column"), "plate_column")
        n_rows, n_columns = plate_dimensions[plate_id]
        if row > n_rows or column > n_columns:
            raise ArmAllocationError("assignment well lies outside plate dimensions")
        well = (plate_id, row, column)
        if well in seen_wells:
            raise ArmAllocationError("duplicate physical well assignment")
        seen_wells.add(well)
        dosing_order = _positive_int(assignment.get("dosing_order"), "dosing_order")
        acquisition_order = _positive_int(
            assignment.get("acquisition_order"), "acquisition_order"
        )
        if dosing_order in dosing_orders:
            raise ArmAllocationError("duplicate dosing_order")
        if acquisition_order in acquisition_orders:
            raise ArmAllocationError("duplicate acquisition_order")
        dosing_orders.add(dosing_order)
        acquisition_orders.add(acquisition_order)
        deviation_status = assignment.get("deviation_status")
        if deviation_status not in {"none", "declared"}:
            raise ArmAllocationError("deviation_status must be none or declared")
        deviation = deviation or deviation_status != "none"
        expected = planned.get(execution_id)
        if (
            expected is None
            or expected["arm"] != arm
            or expected["culture_batch_id"] != batch_id
            or run_id not in expected["allowed_run_ids"]
        ):
            execution_mismatch = True
        position = (
            "edge"
            if row in {1, n_rows} or column in {1, n_columns}
            else "interior"
        )
        column_parity = "odd" if column % 2 else "even"
        column_half = "left" if column <= n_columns / 2 else "right"
        normalized.append(
            {
                "functional_execution_id": execution_id,
                "arm": arm,
                "edit_event_id": edit_event_id,
                "clone_id": clone_id,
                "culture_batch_id": batch_id,
                "functional_assay_run_id": run_id,
                "allocation_block_id": block_id,
                "functional_assay_plate_id": plate_id,
                "plate_row": row,
                "plate_column": column,
                "position_stratum": position,
                "column_parity": column_parity,
                "column_half": column_half,
                "dosing_order": dosing_order,
                "acquisition_order": acquisition_order,
                "deviation_status": deviation_status,
            }
        )

    expected_id = make_preexposure_allocation_id(raw_plan)
    declared_id = raw_plan.get("allocation_id")
    if declared_id != expected_id or commitment.get(
        "plan_sha256"
    ) != expected_id.removeprefix("allocation-"):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_commitment_mismatch",
            n_planned_executions=len(planned),
            n_assignments=len(normalized),
            allocation_id=str(declared_id) if declared_id is not None else None,
        )
    allocation_fingerprint = expected_id.removeprefix("allocation-")

    n_assignments = len(normalized)
    expected_orders = set(range(1, n_assignments + 1))
    if dosing_orders != expected_orders or acquisition_orders != expected_orders:
        execution_mismatch = True
    if set(planned) != seen_ids or n_assignments != len(planned):
        execution_mismatch = True
    if set(plate_dimensions) != {
        item["functional_assay_plate_id"] for item in normalized
    }:
        execution_mismatch = True
    normalized.sort(key=lambda item: item["functional_execution_id"])
    if execution_mismatch:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_execution_mismatch",
            n_planned_executions=len(planned),
            n_assignments=n_assignments,
            allocation_id=expected_id,
            allocation_fingerprint=allocation_fingerprint,
            assignments=normalized,
        )
    normalized_by_id = {
        str(item["functional_execution_id"]): item for item in normalized
    }
    manifest_members = {
        str(member["functional_execution_id"]): member
        for pair in manifest_pairs
        for member in pair["members"]
    }
    if set(manifest_members) != set(normalized_by_id):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_manifest_assignment_mismatch",
            n_planned_executions=len(planned),
            n_assignments=n_assignments,
            allocation_id=expected_id,
            allocation_fingerprint=allocation_fingerprint,
            assignments=normalized,
        )
    for execution_id, member in manifest_members.items():
        assignment = normalized_by_id[execution_id]
        if any(assignment[field] != member[field] for field in MANIFEST_MEMBER_KEYS):
            return _assessment_result(
                status="not_assessable",
                reason="allocation_manifest_assignment_mismatch",
                n_planned_executions=len(planned),
                n_assignments=n_assignments,
                allocation_id=expected_id,
                allocation_fingerprint=allocation_fingerprint,
                assignments=normalized,
            )
    actual_vector: list[dict[str, str]] = []
    for pair in manifest_pairs:
        treatment_ids = [
            str(member["functional_execution_id"])
            for member in pair["members"]
            if normalized_by_id[str(member["functional_execution_id"])]["arm"]
            == "treatment"
        ]
        if len(treatment_ids) != 1:
            return _assessment_result(
                status="not_assessable",
                reason="allocation_randomization_replay_mismatch",
                n_planned_executions=len(planned),
                n_assignments=n_assignments,
                allocation_id=expected_id,
                allocation_fingerprint=allocation_fingerprint,
                assignments=normalized,
            )
        actual_vector.append(
            {
                "pair_id": str(pair["pair_id"]),
                "treatment_execution_id": treatment_ids[0],
            }
        )
    actual_vector.sort(key=lambda item: item["pair_id"])
    if _canonical_json_bytes(actual_vector) != _canonical_json_bytes(
        replay["selected_vector"]
    ):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_randomization_replay_mismatch",
            n_planned_executions=len(planned),
            n_assignments=n_assignments,
            allocation_id=expected_id,
            allocation_fingerprint=allocation_fingerprint,
            assignments=normalized,
        )
    if deviation:
        return _assessment_result(
            status="not_assessable",
            reason="allocation_deviation_declared",
            n_planned_executions=len(planned),
            n_assignments=n_assignments,
            allocation_id=expected_id,
            allocation_fingerprint=allocation_fingerprint,
            assignments=normalized,
        )

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        "plate": defaultdict(list),
        "batch": defaultdict(list),
        "run": defaultdict(list),
        "plate_position": defaultdict(list),
        "plate_row": defaultdict(list),
        "plate_column_parity": defaultdict(list),
        "plate_column_half": defaultdict(list),
        "row_column_parity": defaultdict(list),
        "biological_pair": defaultdict(list),
        "block": defaultdict(list),
    }
    for item in normalized:
        grouped["plate"][item["functional_assay_plate_id"]].append(item)
        grouped["batch"][item["culture_batch_id"]].append(item)
        grouped["run"][item["functional_assay_run_id"]].append(item)
        grouped["plate_position"][
            f"{item['functional_assay_plate_id']}:{item['position_stratum']}"
        ].append(item)
        grouped["plate_row"][
            f"{item['functional_assay_plate_id']}:row-{item['plate_row']}"
        ].append(item)
        grouped["plate_column_parity"][
            f"{item['functional_assay_plate_id']}:{item['column_parity']}"
        ].append(item)
        grouped["plate_column_half"][
            f"{item['functional_assay_plate_id']}:{item['column_half']}"
        ].append(item)
        grouped["row_column_parity"][
            f"{item['functional_assay_plate_id']}:row-{item['plate_row']}:{item['column_parity']}"
        ].append(item)
        grouped["biological_pair"][
            f"{item['edit_event_id']}:{item['clone_id']}:{item['functional_assay_run_id']}"
        ].append(item)
        grouped["block"][item["allocation_block_id"]].append(item)

    checks: list[dict[str, Any]] = []
    confounded = False
    for group_type in (
        "plate",
        "batch",
        "run",
        "plate_position",
        "plate_row",
        "plate_column_parity",
        "plate_column_half",
        "row_column_parity",
    ):
        for group_id, items in sorted(grouped[group_type].items()):
            arms = [str(item["arm"]) for item in items]
            passed = _balanced(arms)
            counts = Counter(arms)
            checks.append(
                {
                    "stratum_type": group_type,
                    "stratum_id": group_id,
                    "vehicle": counts["vehicle"],
                    "treatment": counts["treatment"],
                    "balanced": passed,
                }
            )
            confounded = confounded or not passed

    pair_orientation: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    pair_signed_differences: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    pair_column_distributions: dict[str, dict[str, Counter[int]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    for pair_id, items in sorted(grouped["biological_pair"].items()):
        arms = [str(item["arm"]) for item in items]
        same_context = (
            len(items) == 2
            and len({item["allocation_block_id"] for item in items}) == 1
            and len({item["functional_assay_plate_id"] for item in items}) == 1
            and len({item["culture_batch_id"] for item in items}) == 1
            and len({item["functional_assay_run_id"] for item in items}) == 1
            and len({item["position_stratum"] for item in items}) == 1
            and len({item["plate_row"] for item in items}) == 1
            and len({item["column_parity"] for item in items}) == 1
            and len({item["column_half"] for item in items}) == 1
        )
        passed = _balanced(arms) and same_context
        counts = Counter(arms)
        checks.append(
            {
                "stratum_type": "biological_pair",
                "stratum_id": pair_id,
                "vehicle": counts["vehicle"],
                "treatment": counts["treatment"],
                "balanced": passed,
            }
        )
        confounded = confounded or not passed
        if passed:
            vehicle = next(item for item in items if item["arm"] == "vehicle")
            treatment = next(item for item in items if item["arm"] == "treatment")
            context_id = (
                f"{vehicle['functional_assay_plate_id']}:"
                f"{vehicle['culture_batch_id']}:"
                f"{vehicle['functional_assay_run_id']}:"
                f"{vehicle['edit_event_id']}"
            )
            n_rows, n_columns = plate_dimensions[
                str(vehicle["functional_assay_plate_id"])
            ]
            pair_column_distributions[context_id]["vehicle"][
                int(vehicle["plate_column"])
            ] += 1
            pair_column_distributions[context_id]["treatment"][
                int(treatment["plate_column"])
            ] += 1
            for metric, field in (
                ("column_lower", "plate_column"),
                ("dosing_first", "dosing_order"),
                ("acquisition_first", "acquisition_order"),
            ):
                vehicle_value = int(vehicle[field])
                treatment_value = int(treatment[field])
                lower_arm = "vehicle" if vehicle_value < treatment_value else "treatment"
                pair_orientation[context_id][metric][lower_arm] += 1
                pair_signed_differences[context_id][metric].append(
                    treatment_value - vehicle_value
                )
            for metric, field, dimension in (
                ("column_outer", "plate_column", n_columns),
                ("row_outer", "plate_row", n_rows),
            ):
                vehicle_distance = abs(2 * int(vehicle[field]) - (dimension + 1))
                treatment_distance = abs(
                    2 * int(treatment[field]) - (dimension + 1)
                )
                if vehicle_distance != treatment_distance:
                    outer_arm = (
                        "vehicle"
                        if vehicle_distance > treatment_distance
                        else "treatment"
                    )
                    pair_orientation[context_id][metric][outer_arm] += 1
                pair_signed_differences[context_id][metric].append(
                    treatment_distance - vehicle_distance
                )

    for context_id, metrics in sorted(pair_orientation.items()):
        for metric, counts in sorted(metrics.items()):
            n_pairs = counts["vehicle"] + counts["treatment"]
            passed = n_pairs < 2 or abs(
                counts["vehicle"] - counts["treatment"]
            ) <= 1
            checks.append(
                {
                    "stratum_type": f"biological_pair_{metric}_orientation",
                    "stratum_id": context_id,
                    "vehicle": counts["vehicle"],
                    "treatment": counts["treatment"],
                    "balanced": passed,
                }
            )
            confounded = confounded or not passed
    for context_id, by_arm in sorted(pair_column_distributions.items()):
        vehicle_columns = by_arm["vehicle"]
        treatment_columns = by_arm["treatment"]
        n_pairs = sum(vehicle_columns.values())
        replicated = n_pairs >= MINIMUM_PAIRS_PER_CONTEXT
        checks.append(
            {
                "stratum_type": "biological_pair_context_replication",
                "stratum_id": context_id,
                "n_pairs": n_pairs,
                "minimum_pairs": MINIMUM_PAIRS_PER_CONTEXT,
                "balanced": replicated,
            }
        )
        confounded = confounded or not replicated
        same_distribution = vehicle_columns == treatment_columns
        checks.append(
            {
                "stratum_type": "biological_pair_column_distribution",
                "stratum_id": context_id,
                "vehicle_columns": {
                    str(column): count
                    for column, count in sorted(vehicle_columns.items())
                },
                "treatment_columns": {
                    str(column): count
                    for column, count in sorted(treatment_columns.items())
                },
                "balanced": same_distribution,
            }
        )
        confounded = confounded or not same_distribution
    for context_id, metrics in sorted(pair_signed_differences.items()):
        for metric, values in sorted(metrics.items()):
            signed_total = sum(values)
            passed = len(values) < 2 or signed_total == 0
            checks.append(
                {
                    "stratum_type": f"biological_pair_{metric}_signed_balance",
                    "stratum_id": context_id,
                    "n_pairs": len(values),
                    "signed_total": signed_total,
                    "balanced": passed,
                }
            )
            confounded = confounded or not passed

    dosing_first_by_context: dict[str, Counter[str]] = defaultdict(Counter)
    acquisition_first_by_context: dict[str, Counter[str]] = defaultdict(Counter)
    for block_id, items in sorted(grouped["block"].items()):
        arms = [str(item["arm"]) for item in items]
        context_id = (
            f"{items[0]['functional_assay_plate_id']}:"
            f"{items[0]['culture_batch_id']}:"
            f"{items[0]['functional_assay_run_id']}"
        )
        same_context = (
            len(items) >= 2
            and len(items) % 2 == 0
            and len({item["functional_assay_plate_id"] for item in items}) == 1
            and len({item["culture_batch_id"] for item in items}) == 1
            and len({item["functional_assay_run_id"] for item in items}) == 1
            and max(item["dosing_order"] for item in items)
            - min(item["dosing_order"] for item in items)
            == len(items) - 1
            and max(item["acquisition_order"] for item in items)
            - min(item["acquisition_order"] for item in items)
            == len(items) - 1
        )
        passed = _balanced(arms) and same_context
        counts = Counter(arms)
        checks.append(
            {
                "stratum_type": "joint_allocation_block",
                "stratum_id": block_id,
                "vehicle": counts["vehicle"],
                "treatment": counts["treatment"],
                "balanced": passed,
            }
        )
        confounded = confounded or not passed
        for nuisance in (
            "position_stratum",
            "plate_row",
            "column_parity",
            "column_half",
        ):
            nuisance_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in items:
                nuisance_groups[str(item[nuisance])].append(item)
            for value, nuisance_items in sorted(nuisance_groups.items()):
                nuisance_arms = [str(item["arm"]) for item in nuisance_items]
                nuisance_passed = _balanced(nuisance_arms)
                nuisance_counts = Counter(nuisance_arms)
                checks.append(
                    {
                        "stratum_type": f"joint_block_{nuisance}",
                        "stratum_id": f"{block_id}:{value}",
                        "vehicle": nuisance_counts["vehicle"],
                        "treatment": nuisance_counts["treatment"],
                        "balanced": nuisance_passed,
                    }
                )
                confounded = confounded or not nuisance_passed

        for order_name, counter, order_field in (
            ("dosing", dosing_first_by_context, "dosing_order"),
            ("acquisition", acquisition_first_by_context, "acquisition_order"),
        ):
            ordered = sorted(items, key=lambda item: item[order_field])
            for tranche_index in range(0, len(ordered), 2):
                tranche = ordered[tranche_index : tranche_index + 2]
                tranche_arms = [str(item["arm"]) for item in tranche]
                tranche_passed = len(tranche) == 2 and _balanced(tranche_arms)
                tranche_counts = Counter(tranche_arms)
                checks.append(
                    {
                        "stratum_type": f"{order_name}_tranche",
                        "stratum_id": f"{block_id}:{tranche_index // 2 + 1}",
                        "vehicle": tranche_counts["vehicle"],
                        "treatment": tranche_counts["treatment"],
                        "balanced": tranche_passed,
                    }
                )
                confounded = confounded or not tranche_passed
                if len(tranche) == 2:
                    counter[context_id][tranche[0]["arm"]] += 1

    for order_type, by_context in (
        ("dosing_first_within_context", dosing_first_by_context),
        ("acquisition_first_within_context", acquisition_first_by_context),
    ):
        for context_id, counts in sorted(by_context.items()):
            passed = abs(counts["vehicle"] - counts["treatment"]) <= 1
            checks.append(
                {
                    "stratum_type": order_type,
                    "stratum_id": context_id,
                    "vehicle": counts["vehicle"],
                    "treatment": counts["treatment"],
                    "balanced": passed,
                }
            )
            confounded = confounded or not passed

    if (
        not confounded
        and not synthetic_only
        and entropy_authenticity == RANDOMIZATION_ENTROPY_AUTHENTICITY
    ):
        return _assessment_result(
            status="not_assessable",
            reason="allocation_entropy_not_attested_for_nonsynthetic_input",
            n_planned_executions=len(planned),
            n_assignments=n_assignments,
            software_contract_verified=True,
            allocation_id=expected_id,
            allocation_fingerprint=allocation_fingerprint,
            assignments=normalized,
            balance_checks=checks,
        )

    return _assessment_result(
        status="not_assessable" if confounded else "pass",
        reason=(
            "allocation_confounding_detected"
            if confounded
            else "preexposure_allocation_balanced"
        ),
        n_planned_executions=len(planned),
        n_assignments=n_assignments,
        allocation_id=expected_id,
        allocation_fingerprint=allocation_fingerprint,
        assignments=normalized,
        balance_checks=checks,
    )


__all__ = [
    "ALLOCATION_ANALYSIS_PLAN",
    "ALLOCATION_UNIT",
    "ARMS",
    "ASSIGNMENT_MANIFEST_SCHEMA",
    "ASSIGNMENT_ALGORITHMS",
    "ASSIGNMENT_METHODS",
    "CLAIM_BOUNDARY",
    "COMMITMENT_MECHANISMS",
    "PLAN_SCHEMA",
    "SCHEMA",
    "SEED_SPACE_SIZE",
    "TABLE_SCHEMA",
    "ArmAllocationError",
    "SeedModuloBiasRejection",
    "assess_preexposure_allocation",
    "enumerate_admissible_assignment_vectors",
    "make_allocation_analysis_plan_sha256",
    "make_preexposure_allocation_id",
    "make_assignment_input_commitment",
    "make_seed_commitment",
    "replay_seeded_assignment",
    "rejection_sampled_candidate_index",
    "skipped_preexposure_allocation",
]
