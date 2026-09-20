from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.arm_allocation import (
    ALLOCATION_ANALYSIS_PLAN,
    ASSIGNMENT_MANIFEST_SCHEMA,
    CLAIM_BOUNDARY,
    PLAN_SCHEMA,
    SCHEMA,
    SEED_SPACE_SIZE,
    ArmAllocationError,
    SeedModuloBiasRejection,
    assess_preexposure_allocation,
    enumerate_admissible_assignment_vectors,
    make_allocation_analysis_plan_sha256,
    make_assignment_input_commitment,
    make_preexposure_allocation_id,
    make_seed_commitment,
    rejection_sampled_candidate_index,
    replay_seeded_assignment,
    _canonical_json_array_sha256,
    _canonical_json_bytes,
)
from mva_hackathon.exposure_gate import (
    ExposureGateError,
    assess_exposure_execution_binding,
    assess_exposure_gate,
)
from mva_hackathon.save_path import passing_exposure, passing_lineage, passing_power


_VALID_SEED_REVEAL: str | None = "0" * 60 + "11ae"


def _fixture_constructor_replay(
    *,
    assignment_manifest: dict,
    assignment_input_commitment_sha256: str,
    seed_reveal_hex: str,
) -> dict:
    del assignment_input_commitment_sha256, seed_reveal_hex
    selected_vector = [
        {
            "pair_id": pair["pair_id"],
            "treatment_execution_id": next(
                member["functional_execution_id"]
                for member in pair["members"]
                if member["functional_execution_id"].endswith("-member-b")
            ),
        }
        for pair in assignment_manifest["pair_units"]
    ]
    selected_vector.sort(key=lambda item: item["pair_id"])
    return {
        "admissible_space_count": 8000,
        "admissible_space_sha256": "0" * 64,
        "selected_vector": selected_vector,
        "selected_vector_sha256": "0" * 64,
    }


def _manifest_from_allocation(allocation: dict) -> dict:
    member_fields = (
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
    )
    pairs: dict[tuple[str, str, str], list[dict]] = {}
    for assignment in allocation["assignments"]:
        key = (
            assignment["edit_event_id"],
            assignment["clone_id"],
            assignment["functional_assay_run_id"],
        )
        pairs.setdefault(key, []).append(
            {field: assignment[field] for field in member_fields}
        )
    return {
        "schema": ASSIGNMENT_MANIFEST_SCHEMA,
        "plate_dimensions": copy.deepcopy(allocation["plate_dimensions"]),
        "pair_units": [
            {
                "pair_id": f"syn-pair-{index:03d}",
                "members": members,
            }
            for index, (_key, members) in enumerate(sorted(pairs.items()), start=1)
        ],
    }


def _actual_vector(allocation: dict) -> list[dict[str, str]]:
    treatment_ids = {
        item["functional_execution_id"]
        for item in allocation["assignments"]
        if item["arm"] == "treatment"
    }
    vector = []
    for pair in allocation["assignment_manifest"]["pair_units"]:
        treatment = [
            member["functional_execution_id"]
            for member in pair["members"]
            if member["functional_execution_id"] in treatment_ids
        ]
        if len(treatment) != 1:
            raise AssertionError("fixture pair does not have one treatment member")
        vector.append(
            {
                "pair_id": pair["pair_id"],
                "treatment_execution_id": treatment[0],
            }
        )
    return sorted(vector, key=lambda item: item["pair_id"])


def _upgrade_allocation(exposure: dict, lineage: dict) -> None:
    global _VALID_SEED_REVEAL

    allocation = exposure["preexposure_allocation"]
    allocation["schema"] = PLAN_SCHEMA
    allocation["assignment_method"] = "seed_committed_constrained_randomization"
    allocation["assignment_algorithm"] = "paired_constrained_seed_index_rejection_v1"
    allocation["analysis_plan_sha256"] = make_allocation_analysis_plan_sha256()
    allocation["assignment_manifest"] = _manifest_from_allocation(allocation)
    allocation["assignment_input_commitment_sha256"] = (
        make_assignment_input_commitment(
            study_id=allocation["study_id"],
            assay_plan_sha256=allocation["assay_plan_sha256"],
            analysis_plan_sha256=allocation["analysis_plan_sha256"],
            assignment_method=allocation["assignment_method"],
            assignment_algorithm=allocation["assignment_algorithm"],
            allocation_unit=allocation["allocation_unit"],
            assignment_manifest=allocation["assignment_manifest"],
        )
    )
    locked_at = datetime.fromisoformat(
        allocation["locked_at"].replace("Z", "+00:00")
    )
    allocation["assignment_input_commitment_record"] = {
        "mechanism": "append_only_registry",
        "record_id": "syn-input-commitment-record-a",
        "recorded_at": (locked_at + timedelta(minutes=5)).isoformat(),
        "digest_sha256": allocation["assignment_input_commitment_sha256"],
    }
    target = _actual_vector(allocation)
    if _VALID_SEED_REVEAL is None:
        for seed_number in range(1, 10_000):
            seed_reveal = seed_number.to_bytes(32, "big").hex()
            replay = replay_seeded_assignment(
                assignment_manifest=allocation["assignment_manifest"],
                assignment_input_commitment_sha256=allocation[
                    "assignment_input_commitment_sha256"
                ],
                seed_reveal_hex=seed_reveal,
            )
            if replay["selected_vector"] == target:
                _VALID_SEED_REVEAL = seed_reveal
                break
        else:
            raise AssertionError("could not find a deterministic fixture seed")
    replay = replay_seeded_assignment(
        assignment_manifest=allocation["assignment_manifest"],
        assignment_input_commitment_sha256=allocation[
            "assignment_input_commitment_sha256"
        ],
        seed_reveal_hex=_VALID_SEED_REVEAL,
    )
    if replay["selected_vector"] != target:
        raise AssertionError("cached fixture seed selected a different vector")
    seed_commitment = make_seed_commitment(
        _VALID_SEED_REVEAL,
        assignment_input_commitment_sha256=allocation[
            "assignment_input_commitment_sha256"
        ],
    )
    seed_committed_at = (locked_at + timedelta(minutes=10)).isoformat()
    allocation["randomization"] = {
        "generator": "seed_uint256_rejection_index_v1",
        "seed_commitment_sha256": seed_commitment,
        "seed_commitment_record": {
            "mechanism": "append_only_registry",
            "record_id": "syn-seed-commitment-record-a",
            "recorded_at": seed_committed_at,
            "digest_sha256": seed_commitment,
        },
        "seed_committed_at": seed_committed_at,
        "seed_reveal_hex": _VALID_SEED_REVEAL,
        "seed_revealed_at": (locked_at + timedelta(minutes=20)).isoformat(),
        "entropy_authenticity": "not_attested",
        "record": {
            "mechanism": "append_only_registry",
            "record_id": "syn-randomization-record-a",
            "recorded_at": (locked_at + timedelta(minutes=30)).isoformat(),
        },
        "admissible_space_count": replay["admissible_space_count"],
        "admissible_space_sha256": replay["admissible_space_sha256"],
        "selected_vector_sha256": replay["selected_vector_sha256"],
    }
    allocation_id = _rehash(exposure)
    lineage["allocation_id"] = allocation_id


def _fixture() -> tuple[dict, dict, dict]:
    lineage = passing_lineage()
    plan = passing_power()
    exposure = passing_exposure(lineage, plan)
    return lineage, plan, exposure


def _rehash(exposure: dict) -> str:
    allocation = exposure["preexposure_allocation"]
    allocation_id = make_preexposure_allocation_id(allocation)
    allocation["allocation_id"] = allocation_id
    allocation["commitment"]["plan_sha256"] = allocation_id.removeprefix(
        "allocation-"
    )
    return allocation_id


class ArmAllocationTests(unittest.TestCase):
    def test_analysis_plan_digest_binds_exact_residualization_solver(self) -> None:
        self.assertEqual(
            make_allocation_analysis_plan_sha256(),
            "d0f62a582158762f234fa9aa682fb9106b62710a8d5f279685190ee160483b9e",
        )
        inference = ALLOCATION_ANALYSIS_PLAN["inference"]
        self.assertEqual(
            inference["reported_contrast"],
            "mean_within_pair_treatment_minus_vehicle_observed_rate_difference",
        )
        self.assertEqual(
            inference["tested_null"],
            "global_fisher_sharp_null_no_effect_on_any_execution",
        )
        self.assertEqual(
            inference["tested_null_statement"],
            (
                "for_every_functional_execution_the_treatment_and_vehicle_"
                "potential_outcomes_are_identical"
            ),
        )
        self.assertEqual(
            inference["p_value_scope"],
            "exact_for_the_global_fisher_sharp_null_not_a_weak_average_null",
        )
        self.assertEqual(
            inference["assignment_probability_model"],
            (
                "exact_uniform_over_canonical_information_filtered_support_"
                "conditional_on_uint256_rejection_acceptance"
            ),
        )
        self.assertEqual(
            inference["causal_interpretation_assumptions"],
            [
                "genuine_preoutcome_seed_draw_from_the_declared_uniform_model",
                "consistency_and_single_version_of_each_arm",
                "no_interference_carryover_or_cross_well_contamination",
                "fixed_manifest_with_no_postassignment_exclusion",
                "arm_blinded_outcome_ascertainment",
            ],
        )
        self.assertEqual(inference["assumptions_satisfied"], "not_software_attested")
        self.assertEqual(inference["treatment_application_unit"], "functional_execution_well")
        self.assertEqual(inference["randomization_unit"], "biological_pair")
        self.assertEqual(inference["analysis_unit"], "biological_pair")
        self.assertEqual(inference["biological_replication_unit"], "clone_edit_event")
        self.assertNotIn("experimental_unit", inference)
        self.assertEqual(
            ALLOCATION_ANALYSIS_PLAN["randomization_entropy_plan"],
            {
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
        )
        nuisance = ALLOCATION_ANALYSIS_PLAN["inference"][
            "nuisance_residualization"
        ]
        self.assertEqual(
            nuisance["solver"]["summation_algorithm"],
            "explicit_left_to_right_binary64_v1",
        )
        self.assertEqual(
            nuisance["centering"],
            {
                "dosing_order": (
                    "arithmetic_mean_within_plate_batch_run_event_context"
                ),
                "acquisition_order": (
                    "arithmetic_mean_within_plate_batch_run_event_context"
                ),
            },
        )
        self.assertTrue(nuisance["intercept"])
        self.assertEqual(
            nuisance["context_coding"], "k_minus_1_lexicographic_reference"
        )
        self.assertEqual(
            nuisance["context_interactions"],
            {
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
        )
        self.assertEqual(
            ALLOCATION_ANALYSIS_PLAN["allocation_information_filter"],
            {
                "scope": "each_context_candidate",
                "timing": (
                    "after_hard_constraints_before_context_cartesian_product_"
                    "and_seed_index_selection"
                ),
                "row_order": (
                    "functional_execution_id_lexicographic_within_context"
                ),
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
                    "summation_algorithm": (
                        "explicit_left_to_right_binary64_v1"
                    ),
                    "rank_rule": (
                        "residual_column_norm_lte_1e-10_times_max_1_"
                        "original_column_norm_is_rank_deficient"
                    ),
                    "residual_projection": (
                        "centered_arm_indicator_minus_q_times_q_transpose_"
                        "centered_arm_indicator"
                    ),
                    "numeric_arithmetic": "ieee_754_binary64",
                    "dot_product_order": "declared_row_order",
                },
                "information_ratio": (
                    "squared_euclidean_norm_residualized_centered_arm_"
                    "indicator_divided_by_squared_euclidean_norm_centered_"
                    "arm_indicator"
                ),
                "minimum_information_ratio": 0.75,
                "equivalent_max_variance_inflation_factor": "4_over_3",
                "equivalent_max_standard_error_inflation": "sqrt_4_over_3",
                "acceptance_rule": (
                    "residual_norm_squared_plus_tolerance_gte_0.75_times_"
                    "raw_centered_norm_squared"
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
                "minimum_joint_support_size": 64,
                "insufficient_joint_support": (
                    "fail_closed_before_seed_index_selection"
                ),
            },
        )
        self.assertEqual(
            nuisance["outcome_fit"],
            "once_per_endpoint_without_arm_before_enumeration",
        )
        self.assertFalse(nuisance["assignment_dependent_refit"])
        self.assertEqual(
            nuisance["solver"],
            {
                "algorithm": "modified_gram_schmidt_two_pass_qr",
                "summation_algorithm": "explicit_left_to_right_binary64_v1",
                "column_pivoting": False,
                "rank_rule": (
                    "residual_column_norm_lte_1e-10_times_max_1_"
                    "original_column_norm_is_rank_deficient"
                ),
                "coefficient_solve": "upper_triangular_back_substitution",
            },
        )

    def test_balanced_preexposure_allocation_passes(self) -> None:
        lineage, plan, exposure = _fixture()
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["allocation_verified"])
        self.assertTrue(result["synthetic_only"])
        self.assertTrue(result["conditional_software_contract_verified"])
        self.assertEqual(result["entropy_authenticity"], "not_attested")
        self.assertFalse(result["entropy_authenticity_verified"])
        self.assertFalse(result["authenticated_randomization_verified"])
        self.assertEqual(
            result["treatment_application_unit"], "functional_execution_well"
        )
        self.assertEqual(result["randomization_unit"], "biological_pair")
        self.assertEqual(result["analysis_unit"], "biological_pair")
        self.assertEqual(result["biological_replication_unit"], "clone_edit_event")
        self.assertEqual(result["n_assignments"], len(lineage["runs"]))
        self.assertTrue(all(item["balanced"] for item in result["balance_checks"]))
        allocation = exposure["preexposure_allocation"]
        self.assertEqual(
            allocation["randomization"]["admissible_space_count"], 20**3
        )
        nuisance_covariates = ALLOCATION_ANALYSIS_PLAN["inference"][
            "nuisance_residualization"
        ]["covariates"]
        self.assertIn(
            "context_interacted_squared_within_context_centered_dosing_order",
            nuisance_covariates,
        )
        self.assertIn(
            "context_interacted_squared_within_context_centered_acquisition_order",
            nuisance_covariates,
        )
        self.assertIn(
            "context_interacted_centered_dosing_times_centered_acquisition",
            nuisance_covariates,
        )
        plate_columns = {
            item["functional_assay_plate_id"]: item["n_columns"]
            for item in allocation["plate_dimensions"]
        }
        by_context: dict[tuple[str, str, str, str], list[dict]] = {}
        for item in allocation["assignments"]:
            self.assertGreater(item["plate_column"], 1)
            self.assertLess(
                item["plate_column"],
                plate_columns[item["functional_assay_plate_id"]],
            )
            context = (
                item["functional_assay_plate_id"],
                item["culture_batch_id"],
                item["functional_assay_run_id"],
                item["edit_event_id"],
            )
            by_context.setdefault(context, []).append(item)
        for items in by_context.values():
            self.assertGreaterEqual(len(items) // 2, 2)
            self.assertEqual(
                sorted(
                    item["plate_column"]
                    for item in items
                    if item["arm"] == "vehicle"
                ),
                sorted(
                    item["plate_column"]
                    for item in items
                    if item["arm"] == "treatment"
                ),
            )
        binding = assess_exposure_execution_binding(exposure, lineage, plan)
        self.assertEqual(binding["status"], "pass")

    def test_unattested_entropy_holds_for_nonsynthetic_input(self) -> None:
        _lineage, _plan, exposure = _fixture()
        exposure["privacy_class"] = "controlled"
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"],
            "allocation_entropy_not_attested_for_nonsynthetic_input",
        )
        self.assertFalse(result["synthetic_only"])
        self.assertFalse(result["allocation_verified"])
        self.assertTrue(result["conditional_software_contract_verified"])
        self.assertEqual(result["entropy_authenticity"], "not_attested")
        self.assertFalse(result["entropy_authenticity_verified"])
        self.assertFalse(result["authenticated_randomization_verified"])

    def test_v1_allocation_schema_cannot_bypass_v2_records(self) -> None:
        _lineage, _plan, exposure = _fixture()
        exposure["preexposure_allocation"]["schema"] = (
            "mva.community-preexposure-allocation/v1"
        )
        with self.assertRaisesRegex(ArmAllocationError, "wrong schema"):
            assess_preexposure_allocation(exposure)

    def test_allocation_link_identifiers_use_public_opaque_grammar(self) -> None:
        for field in ("allocation_block_id", "functional_assay_plate_id"):
            with self.subTest(field=field):
                _lineage, _plan, exposure = _fixture()
                allocation = exposure["preexposure_allocation"]
                allocation["assignments"][0][field] = "Syn-invalid-allocation"
                _rehash(exposure)
                with self.assertRaisesRegex(ArmAllocationError, "lowercase opaque"):
                    assess_preexposure_allocation(exposure)

        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["plate_dimensions"][0][
            "functional_assay_plate_id"
        ] = "Syn-invalid-allocation"
        _rehash(exposure)
        with self.assertRaisesRegex(ArmAllocationError, "lowercase opaque"):
            assess_preexposure_allocation(exposure)

        for field in ("allocation_block_id", "functional_assay_plate_id"):
            with self.subTest(realized_field=field):
                lineage, plan, exposure = _fixture()
                lineage["runs"][0][field] = "Syn-invalid-allocation"
                with self.assertRaisesRegex(ExposureGateError, "lowercase opaque"):
                    assess_exposure_execution_binding(exposure, lineage, plan)

    def test_linked_executions_require_an_allocation(self) -> None:
        _lineage, _plan, exposure = _fixture()
        exposure.pop("preexposure_allocation")
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "preexposure_allocation_missing")

    def test_unlinked_concentration_rows_do_not_require_an_allocation(self) -> None:
        exposure = {
            "schema": "mva.community-measured-exposure-table/v1",
            "rows": [
                {
                    "supports_functional_execution_ids": [],
                    "functional_assay_run_ids": [],
                }
            ],
        }
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["allocation_verified"])
        self.assertEqual(result["reason"], "no_planned_functional_executions")

    def test_commitment_must_precede_every_exposure(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["commitment"]["recorded_at"] = "2026-08-29T01:00:00Z"
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_commitment_not_preexposure")

    def test_digest_mismatch_holds(self) -> None:
        _lineage, _plan, exposure = _fixture()
        exposure["preexposure_allocation"]["assignments"][0]["plate_column"] += 1
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_commitment_mismatch")

    def test_support_ids_arms_and_context_must_match(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        assignment = allocation["assignments"][0]
        assignment["arm"] = (
            "vehicle" if assignment["arm"] == "treatment" else "treatment"
        )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_execution_mismatch")

    def test_joint_plate_position_block_confounding_holds(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        vehicles = sorted(
            (item for item in allocation["assignments"] if item["arm"] == "vehicle"),
            key=lambda item: item["functional_execution_id"],
        )
        treatments = sorted(
            (item for item in allocation["assignments"] if item["arm"] == "treatment"),
            key=lambda item: item["functional_execution_id"],
        )
        for index, item in enumerate(vehicles, start=1):
            item["plate_row"] = 1
            item["plate_column"] = index
        for index, item in enumerate(treatments, start=2):
            item["plate_row"] = 2
            item["plate_column"] = index
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_assignment_mismatch")

    def test_order_orientation_cannot_alias_arm_across_blocks(self) -> None:
        _lineage, _plan, exposure = _fixture()
        blocks: dict[str, list[dict]] = {}
        for item in exposure["preexposure_allocation"]["assignments"]:
            blocks.setdefault(item["allocation_block_id"], []).append(item)
        for block_number, items in enumerate(sorted(blocks.values(), key=str), start=1):
            vehicle = next(item for item in items if item["arm"] == "vehicle")
            treatment = next(item for item in items if item["arm"] == "treatment")
            vehicle["dosing_order"] = 2 * block_number - 1
            vehicle["acquisition_order"] = 2 * block_number - 1
            treatment["dosing_order"] = 2 * block_number
            treatment["acquisition_order"] = 2 * block_number
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_assignment_mismatch")

    def test_uncommitted_crossover_block_mutation_holds(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        for item in allocation["assignments"]:
            item["allocation_block_id"] = (
                f"syn-crossover-{item['functional_assay_run_id']}"
            )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_assignment_mismatch")

    def test_row_and_column_arm_separation_cannot_pass(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        for index, item in enumerate(allocation["assignments"], start=1):
            item["plate_row"] = 2 if item["arm"] == "vehicle" else 3
            item["plate_column"] = 2 * index - (0 if item["arm"] == "vehicle" else 1)
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_assignment_mismatch")

    def test_exact_column_gradient_cannot_hide_inside_balanced_margins(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["plate_dimensions"][0]["n_rows"] = 8
        pairs: dict[tuple[str, str, str], list[dict]] = {}
        for item in allocation["assignments"]:
            key = (
                item["edit_event_id"],
                item["clone_id"],
                item["functional_assay_run_id"],
            )
            pairs.setdefault(key, []).append(item)
        for row_number, items in enumerate(pairs.values(), start=2):
            for item in items:
                item["plate_row"] = row_number
                item["plate_column"] = 2 if item["arm"] == "vehicle" else 8
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_plate_mismatch")

    def test_signed_column_imbalance_cannot_hide_behind_direction_counts(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["plate_dimensions"][0]["n_rows"] = 8
        by_event: dict[str, list[list[dict]]] = {}
        pairs: dict[tuple[str, str, str], list[dict]] = {}
        for item in allocation["assignments"]:
            key = (
                item["edit_event_id"],
                item["clone_id"],
                item["functional_assay_run_id"],
            )
            pairs.setdefault(key, []).append(item)
        for key, items in sorted(pairs.items()):
            by_event.setdefault(key[0], []).append(items)
        row_number = 2
        for event_pairs in by_event.values():
            for pair_index, items in enumerate(event_pairs):
                columns = (
                    {"vehicle": 2, "treatment": 8}
                    if pair_index == 0
                    else {"vehicle": 8, "treatment": 6}
                )
                for item in items:
                    item["plate_row"] = row_number
                    item["plate_column"] = columns[item["arm"]]
                row_number += 1
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_plate_mismatch")

    def test_single_pair_context_fragmentation_cannot_bypass_balance(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        pairs: dict[tuple[str, str, str], list[dict]] = {}
        for item in allocation["assignments"]:
            key = (
                item["edit_event_id"],
                item["clone_id"],
                item["functional_assay_run_id"],
            )
            pairs.setdefault(key, []).append(item)
        allocation["plate_dimensions"] = []
        for pair_number, items in enumerate(pairs.values(), start=1):
            plate_id = f"syn-fragment-plate-{pair_number}"
            allocation["plate_dimensions"].append(
                {
                    "functional_assay_plate_id": plate_id,
                    "n_rows": 4,
                    "n_columns": 24,
                }
            )
            for item in items:
                item["functional_assay_plate_id"] = plate_id
                item["plate_row"] = 2
                item["plate_column"] = 2 if item["arm"] == "vehicle" else 8
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_plate_mismatch")

    def test_nonlinear_column_alias_fails_exact_distribution(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["plate_dimensions"][0].update(n_rows=24, n_columns=24)
        pairs: dict[tuple[str, str, str], list[dict]] = {}
        by_event: dict[str, list[list[dict]]] = {}
        for item in allocation["assignments"]:
            key = (
                item["edit_event_id"],
                item["clone_id"],
                item["functional_assay_run_id"],
            )
            pairs.setdefault(key, []).append(item)
        for key, items in sorted(pairs.items()):
            by_event.setdefault(key[0], []).append(items)
        row_number = 2
        for event_pairs in by_event.values():
            for items, columns in zip(
                event_pairs,
                (
                    {"vehicle": 2, "treatment": 8},
                    {"vehicle": 12, "treatment": 6},
                    {"vehicle": 2, "treatment": 8},
                    {"vehicle": 12, "treatment": 6},
                    {"vehicle": 2, "treatment": 8},
                    {"vehicle": 12, "treatment": 6},
                ),
                strict=True,
            ):
                for item in items:
                    item["plate_row"] = row_number
                    item["plate_column"] = columns[item["arm"]]
                row_number += 1
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_plate_mismatch")

    def test_row_by_half_interaction_fails_at_the_biological_pair(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["plate_dimensions"][0]["n_rows"] = 8
        pairs: dict[tuple[str, str, str], list[dict]] = {}
        for item in allocation["assignments"]:
            key = (
                item["edit_event_id"],
                item["clone_id"],
                item["functional_assay_run_id"],
            )
            pairs.setdefault(key, []).append(item)
        for pair_number, (key, items) in enumerate(sorted(pairs.items()), start=1):
            within_run = 1 if pair_number % 2 else 2
            for item in items:
                item["allocation_block_id"] = f"syn-interaction-{key[2]}"
                item["plate_row"] = pair_number + 1
                if within_run == 1:
                    item["plate_column"] = 2 if item["arm"] == "vehicle" else 14
                else:
                    item["plate_column"] = 16 if item["arm"] == "vehicle" else 4
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_plate_mismatch")

    def test_event_level_order_aliasing_cannot_hide_in_one_run(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        pairs: dict[tuple[str, str], list[dict]] = {}
        for item in allocation["assignments"]:
            item["functional_assay_run_id"] = "syn-run-1"
            pairs.setdefault(
                (item["edit_event_id"], item["clone_id"]), []
            ).append(item)
        order = 0
        for event_number, event_id in enumerate(sorted({key[0] for key in pairs})):
            event_pairs = [
                items for key, items in sorted(pairs.items()) if key[0] == event_id
            ]
            for pair_number, items in enumerate(event_pairs):
                if event_number == 0:
                    first_arm = "vehicle"
                elif event_number == 1:
                    first_arm = "treatment"
                else:
                    first_arm = "vehicle" if pair_number == 0 else "treatment"
                second_arm = "treatment" if first_arm == "vehicle" else "vehicle"
                by_arm = {item["arm"]: item for item in items}
                for arm in (first_arm, second_arm):
                    order += 1
                    by_arm[arm]["dosing_order"] = order
                    by_arm[arm]["acquisition_order"] = order
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_assignment_mismatch")

    def test_dummy_assignment_input_commitment_cannot_pass(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["assignment_input_commitment_sha256"] = "0" * 64
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_input_commitment_mismatch")

    def test_input_commitment_requires_an_independent_pre_reveal_record(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation.pop("assignment_input_commitment_record")
        with self.assertRaisesRegex(ArmAllocationError, "missing required fields"):
            assess_preexposure_allocation(exposure)

        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["assignment_input_commitment_record"]["digest_sha256"] = (
            "0" * 64
        )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_input_commitment_record_mismatch"
        )

    def test_seed_commitment_requires_an_independent_pre_reveal_record(self) -> None:
        _lineage, _plan, exposure = _fixture()
        randomization = exposure["preexposure_allocation"]["randomization"]
        randomization.pop("seed_commitment_record")
        with self.assertRaisesRegex(ArmAllocationError, "missing required fields"):
            assess_preexposure_allocation(exposure)

        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["randomization"]["seed_commitment_record"][
            "digest_sha256"
        ] = "0" * 64
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_seed_commitment_record_mismatch"
        )

    def test_pre_reveal_commitment_chronology_is_strict(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["assignment_input_commitment_record"]["recorded_at"] = (
            allocation["randomization"]["seed_committed_at"]
        )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_randomization_timeline_invalid"
        )

        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        reveal_time = allocation["randomization"]["seed_revealed_at"]
        allocation["randomization"]["seed_committed_at"] = reveal_time
        allocation["randomization"]["seed_commitment_record"][
            "recorded_at"
        ] = reveal_time
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_randomization_timeline_invalid"
        )

    def test_commitment_receipts_must_have_distinct_record_ids(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["randomization"]["seed_commitment_record"]["record_id"] = (
            allocation["assignment_input_commitment_record"]["record_id"]
        )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_commitment_record_id_reuse"
        )

    def test_seed_commitment_is_experiment_specific(self) -> None:
        seed = "ab" * 32
        first = make_seed_commitment(
            seed,
            assignment_input_commitment_sha256="0" * 64,
        )
        second = make_seed_commitment(
            seed,
            assignment_input_commitment_sha256="1" * 64,
        )
        self.assertNotEqual(first, second)

    def test_uint256_index_mapping_accepts_boundary_and_rejects_tail(self) -> None:
        support_size = 3
        acceptance_limit = (SEED_SPACE_SIZE // support_size) * support_size
        mapped = [
            rejection_sampled_candidate_index(
                seed_integer.to_bytes(32, "big").hex(), support_size
            )
            for seed_integer in range(6)
        ]
        self.assertEqual(mapped, [0, 1, 2, 0, 1, 2])
        self.assertEqual(
            rejection_sampled_candidate_index(
                (acceptance_limit - 1).to_bytes(32, "big").hex(), support_size
            ),
            support_size - 1,
        )
        with self.assertRaises(SeedModuloBiasRejection):
            rejection_sampled_candidate_index(
                acceptance_limit.to_bytes(32, "big").hex(), support_size
            )

    def test_replay_uses_direct_index_without_scores_or_tie_breaking(self) -> None:
        candidates = [b"[0]", b"[1]", b"[2]"]
        with patch(
            "mva_hackathon.arm_allocation._admissible_candidate_bytes",
            return_value=(candidates, "0" * 64),
        ):
            first = replay_seeded_assignment(
                assignment_manifest={},
                assignment_input_commitment_sha256="0" * 64,
                seed_reveal_hex=(1).to_bytes(32, "big").hex(),
            )
            second = replay_seeded_assignment(
                assignment_manifest={},
                assignment_input_commitment_sha256="1" * 64,
                seed_reveal_hex=(1).to_bytes(32, "big").hex(),
            )
        self.assertEqual(first["selected_index"], 1)
        self.assertEqual(first["selected_vector"], [1])
        self.assertEqual(second["selected_vector"], first["selected_vector"])

    def test_v4_input_commitment_binds_algorithm_order_count_and_digest(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        arguments = {
            "study_id": allocation["study_id"],
            "assay_plan_sha256": allocation["assay_plan_sha256"],
            "analysis_plan_sha256": allocation["analysis_plan_sha256"],
            "assignment_method": allocation["assignment_method"],
            "assignment_algorithm": allocation["assignment_algorithm"],
            "allocation_unit": allocation["allocation_unit"],
            "assignment_manifest": allocation["assignment_manifest"],
        }
        with patch(
            "mva_hackathon.arm_allocation._admissible_candidate_bytes",
            return_value=([b"{}"], "0" * 64),
        ):
            first = make_assignment_input_commitment(**arguments)
        with patch(
            "mva_hackathon.arm_allocation._admissible_candidate_bytes",
            return_value=([b"{}"], "1" * 64),
        ):
            changed_digest = make_assignment_input_commitment(**arguments)
        with patch(
            "mva_hackathon.arm_allocation._admissible_candidate_bytes",
            return_value=([b"{}", b"[]"], "0" * 64),
        ):
            changed_count = make_assignment_input_commitment(**arguments)
        self.assertNotEqual(first, changed_digest)
        self.assertNotEqual(first, changed_count)
        changed_algorithm_arguments = dict(arguments)
        changed_algorithm_arguments["assignment_algorithm"] = "other_algorithm_v1"
        with patch(
            "mva_hackathon.arm_allocation._admissible_candidate_bytes",
            return_value=([b"{}"], "0" * 64),
        ):
            changed_algorithm = make_assignment_input_commitment(
                **changed_algorithm_arguments
            )
        self.assertNotEqual(first, changed_algorithm)
        with patch(
            "mva_hackathon.arm_allocation._admissible_candidate_bytes",
            return_value=([b"{}"], "0" * 64),
        ), patch(
            "mva_hackathon.arm_allocation.RANDOMIZATION_GENERATOR",
            "other_generator_v1",
        ):
            changed_generator = make_assignment_input_commitment(**arguments)
        self.assertNotEqual(first, changed_generator)
        with patch(
            "mva_hackathon.arm_allocation._admissible_candidate_bytes",
            return_value=([b"{}"], "0" * 64),
        ), patch.dict(
            ALLOCATION_ANALYSIS_PLAN,
            {"candidate_order": "other_canonical_order_v1"},
        ):
            changed_order = make_assignment_input_commitment(**arguments)
        self.assertNotEqual(first, changed_order)

    def test_manifest_rejects_arm_label_leakage(self) -> None:
        for forbidden_token in ("vehicle", "treatment", "control", "drug"):
            with self.subTest(forbidden_token=forbidden_token):
                _lineage, _plan, exposure = _fixture()
                manifest = exposure["preexposure_allocation"][
                    "assignment_manifest"
                ]
                manifest["pair_units"][0]["members"][0][
                    "functional_execution_id"
                ] = f"syn-{forbidden_token}-member"
                with self.assertRaisesRegex(
                    ArmAllocationError, "leaks an arm label"
                ):
                    assess_preexposure_allocation(exposure)

    def test_manifest_rejects_arm_label_substring_leakage(self) -> None:
        for obfuscated in (
            "syn-vehicle1",
            "syn-treatment01",
            "syn-member-controlx",
            "syn-xdrug-member",
        ):
            with self.subTest(obfuscated=obfuscated):
                _lineage, _plan, exposure = _fixture()
                manifest = exposure["preexposure_allocation"][
                    "assignment_manifest"
                ]
                manifest["pair_units"][0]["members"][0][
                    "functional_execution_id"
                ] = obfuscated
                with self.assertRaisesRegex(
                    ArmAllocationError, "leaks an arm label"
                ):
                    assess_preexposure_allocation(exposure)

    def test_manifest_array_order_is_canonical_but_fixed_order_mutation_holds(
        self,
    ) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["assignment_manifest"]["pair_units"].reverse()
        for pair in allocation["assignment_manifest"]["pair_units"]:
            pair["members"].reverse()
        self.assertEqual(assess_preexposure_allocation(exposure)["status"], "pass")

        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        first, second = allocation["assignments"][:2]
        first["dosing_order"], second["dosing_order"] = (
            second["dosing_order"],
            first["dosing_order"],
        )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_assignment_mismatch")

    def test_manifest_semantic_mutation_breaks_input_commitment(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["assignment_manifest"]["pair_units"][0]["pair_id"] = (
            "syn-pair-mutated"
        )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_input_commitment_mismatch")

    def test_seed_reveal_must_match_prior_commitment(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        reveal = allocation["randomization"]["seed_reveal_hex"]
        allocation["randomization"]["seed_reveal_hex"] = (
            reveal[:-1] + ("0" if reveal[-1] != "0" else "1")
        )
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_seed_commitment_mismatch")

    def test_modulo_bias_rejection_tail_holds_without_redraw(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        reveal = "f" * 64
        commitment = make_seed_commitment(
            reveal,
            assignment_input_commitment_sha256=allocation[
                "assignment_input_commitment_sha256"
            ],
        )
        allocation["randomization"]["seed_reveal_hex"] = reveal
        allocation["randomization"]["seed_commitment_sha256"] = commitment
        allocation["randomization"]["seed_commitment_record"][
            "digest_sha256"
        ] = commitment
        _rehash(exposure)

        result = assess_preexposure_allocation(exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_seed_rejected_for_modulo_bias"
        )
        self.assertTrue(result["advancement_blocked"])

    def test_selected_vector_digest_tamper_holds(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["randomization"]["selected_vector_sha256"] = "0" * 64
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_randomization_selection_mismatch"
        )

    def test_candidate_space_count_or_digest_tamper_holds(self) -> None:
        for field, value in (
            ("admissible_space_count", 217),
            ("admissible_space_sha256", "0" * 64),
        ):
            with self.subTest(field=field):
                _lineage, _plan, exposure = _fixture()
                allocation = exposure["preexposure_allocation"]
                allocation["randomization"][field] = value
                _rehash(exposure)
                result = assess_preexposure_allocation(exposure)
                self.assertEqual(result["status"], "not_assessable")
                self.assertEqual(
                    result["reason"], "allocation_candidate_space_mismatch"
                )

    def test_fewer_than_six_pairs_per_context_is_rejected(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["assignment_manifest"]["pair_units"] = allocation[
            "assignment_manifest"
        ]["pair_units"][:5]
        with self.assertRaisesRegex(ArmAllocationError, "at least six pairs"):
            make_assignment_input_commitment(
                study_id=allocation["study_id"],
                assay_plan_sha256=allocation["assay_plan_sha256"],
                analysis_plan_sha256=allocation["analysis_plan_sha256"],
                assignment_method=allocation["assignment_method"],
                assignment_algorithm=allocation["assignment_algorithm"],
                allocation_unit=allocation["allocation_unit"],
                assignment_manifest=allocation["assignment_manifest"],
            )

    def test_actual_arm_vector_must_equal_seed_index_selected_vector(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        pair = allocation["assignment_manifest"]["pair_units"][0]
        first_id, second_id = [
            member["functional_execution_id"] for member in pair["members"]
        ]
        for assignment in allocation["assignments"]:
            if assignment["functional_execution_id"] in {first_id, second_id}:
                assignment["arm"] = (
                    "vehicle" if assignment["arm"] == "treatment" else "treatment"
                )
        for record in [*exposure["rows"], *exposure["vehicle_controls"]]:
            supports = record.get("supports_functional_execution_ids", [])
            record["supports_functional_execution_ids"] = [
                second_id
                if execution_id == first_id
                else first_id
                if execution_id == second_id
                else execution_id
                for execution_id in supports
            ]
        _rehash(exposure)
        result = assess_preexposure_allocation(exposure)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_randomization_replay_mismatch"
        )

    def test_public_candidate_enumerator_matches_receipt(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        candidates, digest = enumerate_admissible_assignment_vectors(
            allocation["assignment_manifest"]
        )
        self.assertEqual(len(candidates), 8000)
        self.assertEqual(
            digest, allocation["randomization"]["admissible_space_sha256"]
        )
        self.assertEqual(
            digest,
            "b977fecec671cc77fb79642841dc4ca10e9d96d8535e6c0dc6ab1af8ad8315cd",
        )
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertEqual(list(candidates), sorted(candidates))

    def test_canonical_array_digest_matches_materialized_dumps(self) -> None:
        payload = [
            [{"pair_id": "syn-pair-b", "treatment_execution_id": "syn-t2"}],
            [{"pair_id": "syn-pair-a", "treatment_execution_id": "syn-t1"}],
        ]
        encoded = sorted(_canonical_json_bytes(item) for item in payload)
        materialized = hashlib.sha256(
            _canonical_json_bytes(
                [json.loads(item.decode("utf-8")) for item in encoded]
            )
        ).hexdigest()
        self.assertEqual(_canonical_json_array_sha256(encoded), materialized)

    def test_information_filter_removes_low_information_local_vectors(self) -> None:
        _lineage, _plan, exposure = _fixture()
        manifest = copy.deepcopy(
            exposure["preexposure_allocation"]["assignment_manifest"]
        )
        first_context = min(
            str(pair["members"][0]["edit_event_id"])
            for pair in manifest["pair_units"]
        )
        context_pairs = sorted(
            (
                pair
                for pair in manifest["pair_units"]
                if pair["members"][0]["edit_event_id"] == first_context
            ),
            key=lambda pair: min(
                member["dosing_order"] for member in pair["members"]
            ),
        )
        acquisition_pair_order = (0, 1, 2, 3, 5, 4)
        acquisition_rank = {
            pair_index: rank
            for rank, pair_index in enumerate(acquisition_pair_order)
        }
        acquisition_offset = min(
            member["acquisition_order"]
            for pair in context_pairs
            for member in pair["members"]
        ) - 1
        for pair_index, pair in enumerate(context_pairs):
            for member_index, member in enumerate(
                sorted(pair["members"], key=lambda item: item["dosing_order"])
            ):
                member["acquisition_order"] = (
                    acquisition_offset
                    + 2 * acquisition_rank[pair_index]
                    + 1
                    + member_index
                )

        candidates, _digest = enumerate_admissible_assignment_vectors(manifest)

        self.assertEqual(len(candidates), 6 * 20 * 20)

    def test_joint_support_below_64_fails_before_seed_index_selection(self) -> None:
        _lineage, _plan, exposure = _fixture()
        manifest = copy.deepcopy(
            exposure["preexposure_allocation"]["assignment_manifest"]
        )
        first_context = min(
            str(pair["members"][0]["edit_event_id"])
            for pair in manifest["pair_units"]
        )
        manifest["pair_units"] = [
            pair
            for pair in manifest["pair_units"]
            if pair["members"][0]["edit_event_id"] == first_context
        ]
        with self.assertRaisesRegex(ArmAllocationError, "fewer than 64"):
            enumerate_admissible_assignment_vectors(manifest)

    def test_oversized_context_fails_before_candidate_generation(self) -> None:
        pair_units = []
        for pair_index in range(24):
            members = []
            for member_index, column in enumerate((2, 4)):
                members.append(
                    {
                        "functional_execution_id": (
                            f"syn-opaque-exec-{pair_index:02d}-{member_index}"
                        ),
                        "edit_event_id": "syn-opaque-event",
                        "clone_id": f"syn-opaque-clone-{pair_index:02d}",
                        "culture_batch_id": "syn-opaque-batch",
                        "functional_assay_run_id": "syn-opaque-run",
                        "allocation_block_id": (
                            f"syn-opaque-block-{pair_index:02d}"
                        ),
                        "functional_assay_plate_id": "syn-opaque-plate",
                        "plate_row": pair_index + 2,
                        "plate_column": column,
                        "dosing_order": 2 * pair_index + member_index + 1,
                        "acquisition_order": 2 * pair_index + member_index + 1,
                    }
                )
            pair_units.append(
                {
                    "pair_id": f"syn-opaque-pair-{pair_index:02d}",
                    "members": members,
                }
            )
        manifest = {
            "schema": ASSIGNMENT_MANIFEST_SCHEMA,
            "plate_dimensions": [
                {
                    "functional_assay_plate_id": "syn-opaque-plate",
                    "n_rows": 26,
                    "n_columns": 32,
                }
            ],
            "pair_units": pair_units,
        }
        with patch(
            "mva_hackathon.arm_allocation.itertools.combinations",
            side_effect=AssertionError("candidate generation must not start"),
        ):
            with self.assertRaisesRegex(
                ArmAllocationError, "prospective arm-vector space exceeds"
            ):
                enumerate_admissible_assignment_vectors(manifest)

    def test_input_commitment_binds_full_canonical_manifest(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        declared = allocation["assignment_input_commitment_sha256"]
        self.assertEqual(
            declared,
            make_assignment_input_commitment(
                study_id=allocation["study_id"],
                assay_plan_sha256=allocation["assay_plan_sha256"],
                analysis_plan_sha256=allocation["analysis_plan_sha256"],
                assignment_method=allocation["assignment_method"],
                assignment_algorithm=allocation["assignment_algorithm"],
                allocation_unit=allocation["allocation_unit"],
                assignment_manifest=allocation["assignment_manifest"],
            ),
        )
        changed_manifest = copy.deepcopy(allocation["assignment_manifest"])
        changed_manifest["pair_units"][0]["members"][0][
            "functional_execution_id"
        ] = "syn-unreserved-execution"
        self.assertNotEqual(
            declared,
            make_assignment_input_commitment(
                study_id=allocation["study_id"],
                assay_plan_sha256=allocation["assay_plan_sha256"],
                analysis_plan_sha256=allocation["analysis_plan_sha256"],
                assignment_method=allocation["assignment_method"],
                assignment_algorithm=allocation["assignment_algorithm"],
                allocation_unit=allocation["allocation_unit"],
                assignment_manifest=changed_manifest,
            ),
        )

    def test_physical_wells_and_orders_are_unique_strict_integers(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        allocation["assignments"][1]["plate_row"] = allocation["assignments"][0][
            "plate_row"
        ]
        allocation["assignments"][1]["plate_column"] = allocation["assignments"][0][
            "plate_column"
        ]
        _rehash(exposure)
        with self.assertRaisesRegex(ArmAllocationError, "duplicate physical well"):
            assess_preexposure_allocation(exposure)

        _lineage, _plan, exposure = _fixture()
        exposure["preexposure_allocation"]["assignments"][0]["dosing_order"] = True
        _rehash(exposure)
        with self.assertRaisesRegex(ArmAllocationError, "positive integer"):
            assess_preexposure_allocation(exposure)

    def test_fingerprint_is_order_invariant_and_semantic(self) -> None:
        _lineage, _plan, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        expected = make_preexposure_allocation_id(allocation)
        reordered = copy.deepcopy(allocation)
        reordered["assignments"].reverse()
        reordered["plate_dimensions"].reverse()
        self.assertEqual(expected, make_preexposure_allocation_id(reordered))
        changed = copy.deepcopy(allocation)
        changed["assignments"][0]["acquisition_order"] = 99
        self.assertNotEqual(expected, make_preexposure_allocation_id(changed))

        for mutator in (
            lambda item: item.update(lock_state="unlocked"),
            lambda item: item["commitment"].update(
                mechanism="version_control_commit"
            ),
            lambda item: item["commitment"].update(record_id="syn-other-record"),
            lambda item: item["commitment"].update(
                recorded_at="2026-08-28T23:59:00Z"
            ),
        ):
            changed = copy.deepcopy(allocation)
            mutator(changed)
            self.assertNotEqual(expected, make_preexposure_allocation_id(changed))

        equivalent = copy.deepcopy(allocation)
        for container, key in (
            (equivalent, "locked_at"),
            (equivalent["commitment"], "recorded_at"),
            (equivalent["assignment_input_commitment_record"], "recorded_at"),
            (equivalent["randomization"], "seed_committed_at"),
            (equivalent["randomization"]["seed_commitment_record"], "recorded_at"),
            (equivalent["randomization"], "seed_revealed_at"),
            (equivalent["randomization"]["record"], "recorded_at"),
        ):
            instant = datetime.fromisoformat(
                container[key].replace("Z", "+00:00")
            )
            container[key] = instant.astimezone(
                timezone(timedelta(hours=1))
            ).isoformat()
        self.assertEqual(expected, make_preexposure_allocation_id(equivalent))

    def test_nontranslational_stop_precedes_malformed_allocation(self) -> None:
        _lineage, _plan, exposure = _fixture()
        exposure["rows"][0]["nominal_uM"] = 50.0
        exposure["preexposure_allocation"] = {"malformed": True}
        result = assess_exposure_gate(exposure)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "nontranslational_high")
        self.assertEqual(
            result["preexposure_allocation"]["reason"],
            "nontranslational_high_precedence",
        )

    def test_realized_well_or_order_swap_holds_at_count_identity(self) -> None:
        lineage, plan, exposure = _fixture()
        first, second = lineage["runs"][:2]
        first["plate_column"], second["plate_column"] = (
            second["plate_column"],
            first["plate_column"],
        )
        result = assess_exposure_execution_binding(exposure, lineage, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_study_and_assay_plan_binding_are_checked_later(self) -> None:
        lineage, plan, exposure = _fixture()
        lineage["study_id"] = "syn-other-study"
        result = assess_exposure_execution_binding(exposure, lineage, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_context_mismatch")


if __name__ == "__main__":
    unittest.main()
