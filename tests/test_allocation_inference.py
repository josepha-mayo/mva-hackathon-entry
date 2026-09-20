from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import mva_hackathon.allocation_inference as allocation_inference
from mva_hackathon.allocation_inference import (
    CLAIM_BOUNDARY,
    MIN_ARM_INFORMATION_RATIO,
    assess_constrained_randomization_inference,
)
from mva_hackathon.arm_allocation import (
    ALLOCATION_ANALYSIS_PLAN,
    PLAN_SCHEMA,
    ArmAllocationError,
    assess_preexposure_allocation,
    enumerate_admissible_assignment_vectors,
    make_allocation_analysis_plan_sha256,
    make_assignment_input_commitment,
    make_preexposure_allocation_id,
    make_seed_commitment,
    replay_seeded_assignment,
)


MEMBER_FIELDS = (
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


def _fixture(
    *,
    column_pairs: tuple[tuple[int, int], ...] = ((2, 4), (4, 8), (6, 12)),
    seed_number: int = 37,
    diversify_acquisition: bool = True,
) -> tuple[dict, dict]:
    if len(column_pairs) != 3:
        raise AssertionError("the fixture has exactly three contexts")
    plates = [
        {
            "functional_assay_plate_id": f"syn-plate-{context}",
            "n_rows": 8,
            "n_columns": 32,
        }
        for context in range(1, 4)
    ]
    pair_units: list[dict] = []
    acquisition_pair_order = (1, 0, 4, 3, 2, 5)
    acquisition_rank = {
        pair_index: rank
        for rank, pair_index in enumerate(acquisition_pair_order)
    }
    pair_ordinal = 0
    for context_index, (column_a, column_b) in enumerate(column_pairs, start=1):
        for pair_index in range(6):
            pair_ordinal += 1
            members = []
            for member_index, (suffix, column) in enumerate(
                (("a", column_a), ("b", column_b))
            ):
                dosing_order = 2 * pair_ordinal - 1 + member_index
                acquisition_order = (
                    12 * (context_index - 1)
                    + 2 * acquisition_rank[pair_index]
                    + 1
                    + member_index
                    if diversify_acquisition
                    else dosing_order
                )
                members.append(
                    {
                        "functional_execution_id": (
                            f"syn-exec-{context_index}-{pair_index + 1}-{suffix}"
                        ),
                        "edit_event_id": f"syn-event-{context_index}",
                        "clone_id": f"syn-clone-{context_index}-{pair_index + 1}",
                        "culture_batch_id": f"syn-batch-{context_index}",
                        "functional_assay_run_id": f"syn-run-{context_index}",
                        "allocation_block_id": (
                            f"syn-block-{context_index}-{pair_index + 1}"
                        ),
                        "functional_assay_plate_id": f"syn-plate-{context_index}",
                        "plate_row": pair_index + 2,
                        "plate_column": column,
                        "dosing_order": dosing_order,
                        "acquisition_order": acquisition_order,
                    }
                )
            pair_units.append(
                {
                    "pair_id": f"syn-pair-{context_index}-{pair_index + 1}",
                    "members": members,
                }
            )
    manifest = {
        "schema": "mva-track2-arm-blind-assignment-manifest/v1",
        "plate_dimensions": copy.deepcopy(plates),
        "pair_units": pair_units,
    }
    study_id = "syn-allocation-inference-study"
    assay_plan_sha256 = "a" * 64
    analysis_plan_sha256 = make_allocation_analysis_plan_sha256()
    assignment_method = "seed_committed_constrained_randomization"
    assignment_algorithm = "paired_constrained_seed_index_rejection_v1"
    input_commitment = make_assignment_input_commitment(
        study_id=study_id,
        assay_plan_sha256=assay_plan_sha256,
        analysis_plan_sha256=analysis_plan_sha256,
        assignment_method=assignment_method,
        assignment_algorithm=assignment_algorithm,
        allocation_unit="functional_execution_well",
        assignment_manifest=manifest,
    )
    seed_reveal = seed_number.to_bytes(32, "big").hex()
    replay = replay_seeded_assignment(
        assignment_manifest=manifest,
        assignment_input_commitment_sha256=input_commitment,
        seed_reveal_hex=seed_reveal,
    )
    treatment_ids = {
        item["treatment_execution_id"] for item in replay["selected_vector"]
    }
    assignments = []
    for pair in pair_units:
        for member in pair["members"]:
            assignments.append(
                {
                    **{field: member[field] for field in MEMBER_FIELDS},
                    "arm": (
                        "treatment"
                        if member["functional_execution_id"] in treatment_ids
                        else "vehicle"
                    ),
                    "deviation_status": "none",
                }
            )
    allocation = {
        "schema": PLAN_SCHEMA,
        "allocation_id": "allocation-pending",
        "lock_state": "locked",
        "locked_at": "2026-08-30T00:00:00Z",
        "study_id": study_id,
        "assay_plan_sha256": assay_plan_sha256,
        "analysis_plan_sha256": analysis_plan_sha256,
        "assignment_method": assignment_method,
        "assignment_algorithm": assignment_algorithm,
        "assignment_input_commitment_sha256": input_commitment,
        "assignment_input_commitment_record": {
            "mechanism": "append_only_registry",
            "record_id": "syn-input-commitment-record",
            "recorded_at": "2026-08-30T00:05:00Z",
            "digest_sha256": input_commitment,
        },
        "assignment_manifest": manifest,
        "randomization": {
            "generator": "seed_uint256_rejection_index_v1",
            "seed_commitment_sha256": make_seed_commitment(
                seed_reveal,
                assignment_input_commitment_sha256=input_commitment,
            ),
            "seed_commitment_record": {
                "mechanism": "append_only_registry",
                "record_id": "syn-seed-commitment-record",
                "recorded_at": "2026-08-30T00:10:00Z",
                "digest_sha256": make_seed_commitment(
                    seed_reveal,
                    assignment_input_commitment_sha256=input_commitment,
                ),
            },
            "seed_committed_at": "2026-08-30T00:10:00Z",
            "seed_reveal_hex": seed_reveal,
            "seed_revealed_at": "2026-08-30T00:20:00Z",
            "entropy_authenticity": "not_attested",
            "record": {
                "mechanism": "append_only_registry",
                "record_id": "syn-randomization-record",
                "recorded_at": "2026-08-30T00:30:00Z",
            },
            "admissible_space_count": replay["admissible_space_count"],
            "admissible_space_sha256": replay["admissible_space_sha256"],
            "selected_vector_sha256": replay["selected_vector_sha256"],
        },
        "allocation_unit": "functional_execution_well",
        "commitment": {
            "mechanism": "append_only_registry",
            "record_id": "syn-allocation-record",
            "recorded_at": "2026-08-30T00:40:00Z",
            "plan_sha256": "pending",
        },
        "plate_dimensions": copy.deepcopy(plates),
        "assignments": assignments,
    }
    allocation_id = make_preexposure_allocation_id(allocation)
    allocation["allocation_id"] = allocation_id
    allocation["commitment"]["plan_sha256"] = allocation_id.removeprefix(
        "allocation-"
    )

    treatment_by_context: dict[int, list[str]] = {index: [] for index in range(1, 4)}
    vehicle_by_context: dict[int, list[str]] = {index: [] for index in range(1, 4)}
    for assignment in assignments:
        context_index = int(assignment["edit_event_id"].rsplit("-", 1)[1])
        target = (
            treatment_by_context
            if assignment["arm"] == "treatment"
            else vehicle_by_context
        )
        target[context_index].append(assignment["functional_execution_id"])
    rows = [
        {
            "exposure_profile_id": f"syn-profile-{context}",
            "measurement_execution_id": f"syn-measurement-{context}",
            "supports_functional_execution_ids": sorted(
                treatment_by_context[context]
            ),
            "functional_assay_run_ids": [f"syn-run-{context}"],
            "culture_batch_id": f"syn-batch-{context}",
            "exposure_started_at": "2026-08-30T01:00:00Z",
        }
        for context in range(1, 4)
    ]
    controls = [
        {
            "exposure_profile_id": f"syn-control-profile-{context}",
            "control_execution_id": f"syn-control-{context}",
            "supports_functional_execution_ids": sorted(vehicle_by_context[context]),
            "functional_assay_run_ids": [f"syn-run-{context}"],
            "culture_batch_id": f"syn-batch-{context}",
            "exposure_started_at": "2026-08-30T01:00:00Z",
        }
        for context in range(1, 4)
    ]
    exposure = {
        "schema": "mva.community-measured-exposure-table/v1",
        "privacy_class": "synthetic",
        "preexposure_allocation": allocation,
        "rows": rows,
        "vehicle_controls": controls,
    }

    lineage_runs = []
    for assignment in assignments:
        errors = 1 if assignment["arm"] == "treatment" else 8
        lineage_runs.append(
            {
                "functional_execution_id": assignment["functional_execution_id"],
                "arm": assignment["arm"],
                "edit_event_id": assignment["edit_event_id"],
                "clone_id": assignment["clone_id"],
                "batch_id": assignment["culture_batch_id"],
                "run_id": assignment["functional_assay_run_id"],
                "allocation_block_id": assignment["allocation_block_id"],
                "functional_assay_plate_id": assignment[
                    "functional_assay_plate_id"
                ],
                "plate_row": assignment["plate_row"],
                "plate_column": assignment["plate_column"],
                "dosing_order": assignment["dosing_order"],
                "acquisition_order": assignment["acquisition_order"],
                "opportunities": 24,
                "detected_divisions": 20,
                "event_positive_divisions": errors,
                "event_negative_divisions": 20 - errors,
                "pre_division_death": 0,
                "no_division": 4,
                "dropout_censored": 0,
            }
        )
    lineage = {
        "schema": "mva-track2-lineage-counts/v1",
        "study_id": study_id,
        "synthetic_only": True,
        "lock_state": "locked",
        "blinded": True,
        "allocation_id": allocation_id,
        "runs": lineage_runs,
    }
    return lineage, exposure


class AllocationInferenceTests(unittest.TestCase):
    def test_frozen_plan_copies_match_shared_allocator_exactly(self) -> None:
        self.assertEqual(
            allocation_inference._EXPECTED_INFERENCE_PLAN,
            ALLOCATION_ANALYSIS_PLAN["inference"],
        )
        self.assertEqual(
            allocation_inference._EXPECTED_ALLOCATION_INFORMATION_FILTER,
            ALLOCATION_ANALYSIS_PLAN["allocation_information_filter"],
        )
        self.assertEqual(
            allocation_inference._EXPECTED_ENUMERATION_SAFETY,
            ALLOCATION_ANALYSIS_PLAN["enumeration_safety"],
        )

    def test_all_shared_candidates_retain_prespecified_arm_information(self) -> None:
        _lineage, exposure = _fixture()
        allocation = exposure["preexposure_allocation"]
        manifest = allocation["assignment_manifest"]
        candidates, digest = enumerate_admissible_assignment_vectors(manifest)

        self.assertEqual(len(candidates), 8000)
        self.assertEqual(digest, allocation["randomization"]["admissible_space_sha256"])
        pairs_by_context: dict[tuple[str, str, str, str], list[dict]] = {}
        context_by_pair: dict[str, tuple[str, str, str, str]] = {}
        for pair in manifest["pair_units"]:
            member = pair["members"][0]
            context = (
                member["functional_assay_plate_id"],
                member["culture_batch_id"],
                member["functional_assay_run_id"],
                member["edit_event_id"],
            )
            pairs_by_context.setdefault(context, []).append(pair)
            context_by_pair[pair["pair_id"]] = context

        local_treatment_sets: dict[tuple[str, str, str, str], set[tuple[str, ...]]] = {
            context: set() for context in pairs_by_context
        }
        for candidate in candidates:
            selected_by_context: dict[
                tuple[str, str, str, str], list[str]
            ] = {context: [] for context in pairs_by_context}
            for item in json.loads(candidate.decode("utf-8")):
                selected_by_context[context_by_pair[item["pair_id"]]].append(
                    item["treatment_execution_id"]
                )
            for context, selected in selected_by_context.items():
                local_treatment_sets[context].add(tuple(sorted(selected)))

        minimum_ratio = 1.0
        for context, pairs in pairs_by_context.items():
            self.assertEqual(len(local_treatment_sets[context]), 20)
            members = sorted(
                (member for pair in pairs for member in pair["members"]),
                key=lambda member: member["functional_execution_id"],
            )
            dosing_mean = sum(member["dosing_order"] for member in members) / len(
                members
            )
            acquisition_mean = sum(
                member["acquisition_order"] for member in members
            ) / len(members)
            design = []
            for member in members:
                dosing = member["dosing_order"] - dosing_mean
                acquisition = member["acquisition_order"] - acquisition_mean
                design.append(
                    [
                        1.0,
                        dosing,
                        dosing * dosing,
                        acquisition,
                        acquisition * acquisition,
                        dosing * acquisition,
                    ]
                )
            for selected in local_treatment_sets[context]:
                treatment_ids = set(selected)
                indicator = [
                    1.0
                    if member["functional_execution_id"] in treatment_ids
                    else -1.0
                    for member in members
                ]
                residual = allocation_inference._ols_residuals(design, indicator)
                raw_norm_squared = sum(value * value for value in indicator)
                residual_norm_squared = sum(value * value for value in residual)
                ratio = residual_norm_squared / raw_norm_squared
                minimum_ratio = min(minimum_ratio, ratio)
                self.assertGreaterEqual(
                    residual_norm_squared
                    + 1e-12 * max(1.0, raw_norm_squared),
                    MIN_ARM_INFORMATION_RATIO * raw_norm_squared,
                )
        self.assertGreater(minimum_ratio, 0.90)

    def test_fixed_seed37_true_effect_has_exact_support_and_passes(self) -> None:
        lineage, exposure = _fixture()
        self.assertNotIn("privacy_class", lineage)
        allocation = assess_preexposure_allocation(exposure)
        self.assertEqual(allocation["status"], "pass", allocation)

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["reason"], "both_endpoints_pass")
        self.assertEqual(result["n_contexts"], 3)
        self.assertEqual(result["n_pairs"], 18)
        self.assertEqual(result["n_admissible_treatment_assignments"], 8000)
        self.assertTrue(result["selected_assignment_verified"])
        self.assertTrue(result["conditional_software_contract_verified"])
        self.assertFalse(result["authenticated_randomization_verified"])
        self.assertFalse(result["entropy_authenticity_verified"])
        self.assertEqual(result["treatment_application_unit"], "functional_execution_well")
        self.assertEqual(result["randomization_unit"], "biological_pair")
        self.assertEqual(result["analysis_unit"], "biological_pair")
        self.assertEqual(
            result["tested_null"],
            "global_fisher_sharp_null_no_effect_on_any_execution",
        )
        self.assertIn("not_a_weak_average_null", result["p_value_scope"])
        self.assertEqual(result["assumptions_satisfied"], "not_software_attested")
        self.assertEqual(
            result["summation_algorithm"],
            "explicit_left_to_right_binary64_v1",
        )
        self.assertEqual(len(result["endpoints"]), 2)
        for endpoint in result["endpoints"]:
            self.assertNotIn("estimand", endpoint)
            self.assertEqual(endpoint["tested_null"], result["tested_null"])
            self.assertEqual(endpoint["p_value_scope"], result["p_value_scope"])
            self.assertEqual(
                endpoint["assumptions_satisfied"], "not_software_attested"
            )
            self.assertLess(endpoint["observed_raw_mean_difference"], 0)
            self.assertEqual(endpoint["lower_tail_count"], 1)
            self.assertEqual(endpoint["exact_lower_tail_p_value"], 1 / 8000)
            self.assertTrue(endpoint["passed"])
        self.assertEqual(result["minimum_arm_information_ratio"], 0.75)
        self.assertIn("information-filtered", result["assignment_space"])
        self.assertIn("global sharp null", CLAIM_BOUNDARY)
        self.assertIn("not the weak null", CLAIM_BOUNDARY)
        self.assertIn("does not attest", CLAIM_BOUNDARY)
        self.assertIn("efficacy", CLAIM_BOUNDARY)

    def test_matching_optional_lineage_privacy_class_preserves_pass(self) -> None:
        lineage, exposure = _fixture()
        lineage["privacy_class"] = "synthetic"

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["reason"], "both_endpoints_pass")
        self.assertTrue(result["synthetic_only"])

    def test_malformed_optional_lineage_privacy_class_fails_closed(self) -> None:
        for malformed in (None, True, 7, "", " synthetic", "synthetic "):
            with self.subTest(malformed=malformed):
                lineage, exposure = _fixture()
                lineage["privacy_class"] = malformed

                result = assess_constrained_randomization_inference(
                    lineage, exposure
                )

                self.assertEqual(result["status"], "not_assessable")
                self.assertEqual(result["program_effect"], "hold")
                self.assertEqual(
                    result["reason"], "artifact_classification_malformed"
                )
                self.assertTrue(result["advancement_blocked"])

    def test_optional_lineage_privacy_class_synthetic_conflict_fails_closed(
        self,
    ) -> None:
        lineage, exposure = _fixture()
        lineage["privacy_class"] = "controlled"

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "artifact_classification_mismatch")
        self.assertTrue(result["advancement_blocked"])

    def test_optional_lineage_privacy_class_exposure_conflict_fails_closed(
        self,
    ) -> None:
        lineage, exposure = _fixture()
        lineage["synthetic_only"] = False
        lineage["privacy_class"] = "public"
        exposure["privacy_class"] = "controlled"

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "artifact_classification_mismatch")
        self.assertTrue(result["advancement_blocked"])

    def test_lineage_real_exposure_synthetic_mismatch_fails_closed(self) -> None:
        lineage, exposure = _fixture()
        lineage["synthetic_only"] = False

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "artifact_classification_mismatch")
        self.assertFalse(result["synthetic_only"])
        self.assertFalse(result["selected_assignment_verified"])
        self.assertFalse(result["conditional_software_contract_verified"])
        self.assertFalse(result["authenticated_randomization_verified"])

    def test_real_real_unattested_cannot_use_conditional_software_pass(self) -> None:
        lineage, exposure = _fixture()
        lineage["synthetic_only"] = False
        lineage["privacy_class"] = "controlled"
        exposure["privacy_class"] = "controlled"

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "authenticated_randomization_required")
        self.assertFalse(result["synthetic_only"])
        self.assertTrue(result["conditional_software_contract_verified"])
        self.assertFalse(result["authenticated_randomization_verified"])

    def test_rejected_uint256_seed_holds_inference_without_redraw(self) -> None:
        lineage, exposure = _fixture()
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
        allocation_id = make_preexposure_allocation_id(allocation)
        allocation["allocation_id"] = allocation_id
        allocation["commitment"]["plan_sha256"] = allocation_id.removeprefix(
            "allocation-"
        )
        lineage["allocation_id"] = allocation_id

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "allocation_seed_rejected_for_modulo_bias"
        )
        self.assertTrue(result["advancement_blocked"])

    def test_legacy_plan_without_manifest_fails_closed(self) -> None:
        lineage, exposure = _fixture()
        exposure["preexposure_allocation"].pop("assignment_manifest")

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "allocation_manifest_missing")
        self.assertTrue(result["advancement_blocked"])

    def test_missing_endpoint_is_not_imputed(self) -> None:
        lineage, exposure = _fixture()
        lineage["runs"][0].pop("detected_divisions")

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "endpoint_data_malformed")

    def test_zero_denominator_is_not_assessable(self) -> None:
        lineage, exposure = _fixture()
        lineage["runs"][0]["detected_divisions"] = 0
        lineage["runs"][0]["event_positive_divisions"] = 0

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "endpoint_denominator_zero")

    def test_selected_arm_must_match_lineage_execution(self) -> None:
        lineage, exposure = _fixture()
        lineage["runs"][0]["arm"] = (
            "vehicle" if lineage["runs"][0]["arm"] == "treatment" else "treatment"
        )

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "lineage_assignment_mismatch")

    def test_unlinked_exposure_context_cannot_bypass_verification(self) -> None:
        lineage, exposure = _fixture()
        exposure["rows"] = []
        exposure["vehicle_controls"] = []

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "preexposure_allocation_not_verified")
        self.assertFalse(result["selected_assignment_verified"])

    def test_member_identifier_cannot_encode_an_arm_label(self) -> None:
        _lineage, exposure = _fixture()
        plan = copy.deepcopy(exposure["preexposure_allocation"])
        manifest = plan["assignment_manifest"]
        manifest["pair_units"][0]["members"][0]["functional_execution_id"] = (
            "syn-exec-treatment-1"
        )
        manifest["pair_units"][1]["members"][1]["clone_id"] = (
            "syn-clone-vehicle-2"
        )

        with self.assertRaisesRegex(
            allocation_inference.AllocationInferenceError, "arm label"
        ):
            allocation_inference._parse_manifest(plan)

    def test_collinear_schedule_fails_closed_before_selection_and_inference(self) -> None:
        _lineage, exposure = _fixture()
        plan = copy.deepcopy(exposure["preexposure_allocation"])
        manifest = plan["assignment_manifest"]
        for pair in manifest["pair_units"]:
            for member in pair["members"]:
                member["acquisition_order"] = member["dosing_order"]

        with self.assertRaisesRegex(ArmAllocationError, "rank deficient"):
            enumerate_admissible_assignment_vectors(manifest)

        pairs, member_index = allocation_inference._parse_manifest(plan)
        execution_ids, design = allocation_inference._nuisance_design(
            pairs, member_index
        )
        with self.assertRaises(allocation_inference.AllocationInferenceError) as caught:
            allocation_inference._ols_residuals(
                design, [0.0 for _execution_id in execution_ids]
            )
        self.assertEqual(caught.exception.reason, "nuisance_design_rank_deficient")

    def test_nonlower_endpoint_stops_even_with_valid_replay(self) -> None:
        lineage, exposure = _fixture()
        for row in lineage["runs"]:
            row["event_positive_divisions"] = 8 if row["arm"] == "treatment" else 1
            row["event_negative_divisions"] = 20 - row["event_positive_divisions"]

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "stop", result)
        self.assertEqual(result["reason"], "endpoint_not_directionally_lower")
        self.assertTrue(result["advancement_blocked"])

    def test_u_shaped_order_only_signal_cannot_pass(self) -> None:
        for order_field in ("dosing_order", "acquisition_order"):
            with self.subTest(order_field=order_field):
                lineage, exposure = _fixture()
                for row in lineage["runs"]:
                    errors = (2 * row[order_field] - 37) ** 2
                    row.update(
                        opportunities=2000,
                        detected_divisions=2000,
                        event_positive_divisions=errors,
                        event_negative_divisions=2000 - errors,
                        pre_division_death=0,
                        no_division=0,
                        dropout_censored=0,
                    )

                result = assess_constrained_randomization_inference(
                    lineage, exposure
                )

                self.assertEqual(result["status"], "stop", result)
                for endpoint in result["endpoints"]:
                    self.assertGreater(endpoint["exact_lower_tail_p_value"], 0.05)
                    self.assertFalse(endpoint["passed"])

    def test_seed54_context_local_u_shape_cannot_pass(self) -> None:
        for order_field in ("dosing_order", "acquisition_order"):
            with self.subTest(order_field=order_field):
                lineage, exposure = _fixture(seed_number=54)
                for row in lineage["runs"]:
                    local_order = (row[order_field] - 1) % 12 + 1
                    errors = (2 * local_order - 13) ** 2
                    row.update(
                        opportunities=200,
                        detected_divisions=200,
                        event_positive_divisions=errors,
                        event_negative_divisions=200 - errors,
                        pre_division_death=0,
                        no_division=0,
                        dropout_censored=0,
                    )

                result = assess_constrained_randomization_inference(
                    lineage, exposure
                )

                self.assertEqual(result["status"], "stop", result)
                for endpoint in result["endpoints"]:
                    self.assertEqual(endpoint["exact_lower_tail_p_value"], 1.0)
                    self.assertFalse(endpoint["passed"])

    def test_seed106_mixed_context_u_shapes_cannot_pass(self) -> None:
        lineage, exposure = _fixture(seed_number=106)
        for row in lineage["runs"]:
            context_number = int(row["edit_event_id"].rsplit("-", 1)[1])
            order_field = (
                "acquisition_order" if context_number in {1, 2} else "dosing_order"
            )
            local_order = (row[order_field] - 1) % 12 + 1
            errors = (2 * local_order - 13) ** 2
            row.update(
                opportunities=200,
                detected_divisions=200,
                event_positive_divisions=errors,
                event_negative_divisions=200 - errors,
                pre_division_death=0,
                no_division=0,
                dropout_censored=0,
            )

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "stop", result)
        for endpoint in result["endpoints"]:
            self.assertEqual(endpoint["exact_lower_tail_p_value"], 1.0)
            self.assertFalse(endpoint["passed"])

    def test_seed269_dosing_acquisition_cross_term_cannot_pass(self) -> None:
        lineage, exposure = _fixture(seed_number=269)
        for row in lineage["runs"]:
            local_dosing = (row["dosing_order"] - 1) % 12 + 1
            local_acquisition = (row["acquisition_order"] - 1) % 12 + 1
            doubled_centered_dosing = 2 * local_dosing - 13
            quadrupled_centered_acquisition = 4 * local_acquisition - 26
            errors = (
                doubled_centered_dosing - quadrupled_centered_acquisition
            ) ** 2
            row.update(
                opportunities=1500,
                detected_divisions=1500,
                event_positive_divisions=errors,
                event_negative_divisions=1500 - errors,
                pre_division_death=0,
                no_division=0,
                dropout_censored=0,
            )

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "stop", result)
        for endpoint in result["endpoints"]:
            self.assertEqual(endpoint["exact_lower_tail_p_value"], 1.0)
            self.assertFalse(endpoint["passed"])

    def test_coercible_counts_are_rejected(self) -> None:
        lineage, exposure = _fixture()
        lineage["runs"][0]["opportunities"] = "24"

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "endpoint_data_malformed")

    def test_internally_inconsistent_counts_are_rejected(self) -> None:
        lineage, exposure = _fixture()
        lineage["runs"][0]["event_negative_divisions"] -= 1

        result = assess_constrained_randomization_inference(lineage, exposure)

        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "endpoint_data_malformed")


if __name__ == "__main__":
    unittest.main()
