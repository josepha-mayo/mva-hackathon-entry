from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.save_path import (
    CLAIM_BOUNDARY,
    SCHEMA,
    SavePathError,
    _relabel_unattested_synthetic_fixture_to_seed,
    passing_exposure,
    passing_lineage,
    passing_power,
    run_save_path_suite,
)


class SavePathTests(unittest.TestCase):
    def test_synthetic_reseal_rejects_non_synthetic_inputs_without_mutation(self) -> None:
        base_lineage = passing_lineage()
        base_exposure = passing_exposure(base_lineage, passing_power())
        mutations = (
            lambda exposure, _lineage: exposure.update(schema="wrong-schema"),
            lambda exposure, _lineage: exposure.update(privacy_class="controlled"),
            lambda exposure, _lineage: exposure.pop("privacy_class"),
            lambda _exposure, lineage: lineage.update(schema="wrong-schema"),
            lambda _exposure, lineage: lineage.update(synthetic_only=False),
            lambda _exposure, lineage: lineage.pop("synthetic_only"),
            lambda exposure, _lineage: exposure["preexposure_allocation"][
                "randomization"
            ].update(entropy_authenticity="attested"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                exposure = copy.deepcopy(base_exposure)
                lineage = copy.deepcopy(base_lineage)
                mutate(exposure, lineage)
                before_exposure = copy.deepcopy(exposure)
                before_lineage = copy.deepcopy(lineage)
                with self.assertRaisesRegex(SavePathError, "synthetic"):
                    _relabel_unattested_synthetic_fixture_to_seed(
                        exposure=exposure,
                        lineage=lineage,
                    )
                self.assertEqual(exposure, before_exposure)
                self.assertEqual(lineage, before_lineage)

    def test_synthetic_reseal_rejects_inconsistent_inputs_without_mutation(self) -> None:
        # Raise paths after the schema/privacy/entropy checks — manifest
        # mismatch, incomplete biological pairs, and missing support records —
        # must also leave both declared structures byte-identical. A caller
        # that catches the error must not hold half-moved arms, payloads, or
        # zeroed support lists.
        base_lineage = passing_lineage()
        base_exposure = passing_exposure(base_lineage, passing_power())
        mutations = (
            # A run id outside the allocation manifest.
            lambda _exposure, lineage: lineage["runs"][0].update(
                functional_execution_id="alien-exec"
            ),
            # Two vehicle rows inside one biological pair (runs[0] is
            # treatment after the fixture reseal).
            lambda _exposure, lineage: lineage["runs"][0].update(arm="vehicle"),
            # A vehicle-control record id no run's pointer can resolve.
            lambda exposure, _lineage: exposure["vehicle_controls"][0].update(
                control_execution_id="alien-record"
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                exposure = copy.deepcopy(base_exposure)
                lineage = copy.deepcopy(base_lineage)
                mutate(exposure, lineage)
                before_exposure = copy.deepcopy(exposure)
                before_lineage = copy.deepcopy(lineage)
                with self.assertRaises(SavePathError):
                    _relabel_unattested_synthetic_fixture_to_seed(
                        exposure=exposure,
                        lineage=lineage,
                    )
                self.assertEqual(exposure, before_exposure)
                self.assertEqual(lineage, before_lineage)

    def test_complete_nested_objects_can_open_and_false_stories_cannot(self) -> None:
        result = run_save_path_suite()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertTrue(result["save_path_reachable"])
        self.assertTrue(result["false_paths_blocked_from_advancing"])
        self.assertEqual(result["n_true_path_opened"], result["n_true_path"])
        self.assertEqual(
            result["n_false_paths_blocked_from_advancing"],
            result["n_false_path"],
        )
        # The matrix is a declared contract: the declared false-path count
        # must be exercised and the combined suite flag must reflect both
        # halves.
        self.assertEqual(result["n_false_path"], 126)
        self.assertEqual(result["n_true_path"], 1)
        self.assertTrue(result["save_path_suite_passed"])
        by_name = {item["name"]: item for item in result["scenarios"]}
        self.assertEqual(by_name["reachable_save_path"]["decision"], "advance")
        self.assertIsNone(by_name["reachable_save_path"]["blocked_by"])
        self.assertEqual(by_name["incomplete_confirmation"]["blocked_by"], "confirmation")
        self.assertEqual(by_name["cis_pair"]["blocked_by"], "phase")
        self.assertEqual(by_name["linkage_not_recorded"]["blocked_by"], "phase")
        self.assertEqual(by_name["computational_phase"]["blocked_by"], "phase")
        self.assertEqual(
            by_name["computational_phase"]["block_reason"],
            "computational_phase_not_molecule",
        )
        self.assertEqual(by_name["unmatched_phase_specimen"]["blocked_by"], "phase")
        self.assertEqual(
            by_name["unmatched_phase_specimen"]["block_reason"],
            "unmatched_phase_specimen",
        )
        self.assertEqual(by_name["analog_as_function"]["blocked_by"], "hypomorph")
        self.assertEqual(by_name["analog_correction"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["analog_correction"]["block_reason"],
            "analog_correction_not_exact",
        )
        self.assertEqual(by_name["heat_shock_pd"]["earliest_nonpass_gate"], "hypomorph")
        self.assertEqual(by_name["heat_shock_pd"]["earliest_nonpass_reason"], "pd_not_checkpoint")
        self.assertEqual(by_name["competing_risk"]["blocked_by"], "count_identity")
        self.assertEqual(by_name["organ_size_overclaim"]["blocked_by"], "evidence")
        self.assertEqual(by_name["unlinked_confirmation"]["blocked_by"], "confirmation")
        self.assertEqual(by_name["incomplete_transcript"]["blocked_by"], "transcript")
        self.assertEqual(by_name["computational_transcript"]["blocked_by"], "transcript")
        self.assertEqual(
            by_name["computational_transcript"]["block_reason"],
            "computational_transcript_not_assay",
        )
        self.assertEqual(by_name["unmatched_transcript_specimen"]["blocked_by"], "transcript")
        self.assertEqual(
            by_name["unmatched_transcript_specimen"]["block_reason"],
            "unmatched_transcript_specimen",
        )
        self.assertEqual(by_name["computational_stability"]["blocked_by"], "hypomorph")
        self.assertEqual(by_name["computational_correction"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["computational_correction"]["block_reason"],
            "computational_correction_not_assay",
        )
        self.assertEqual(by_name["failed_reciprocal_recreation"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["failed_reciprocal_recreation"]["block_reason"],
            "recreation_did_not_restore_defect",
        )
        self.assertEqual(by_name["imposed_extrinsic_stress"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["imposed_extrinsic_stress"]["block_reason"],
            "imposed_stress_not_basal_defect",
        )
        self.assertEqual(by_name["cell_free_biophysical"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["cell_free_biophysical"]["block_reason"],
            "cell_free_not_cellular_defect",
        )
        self.assertEqual(by_name["cell_free_correction"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["cell_free_correction"]["block_reason"],
            "cell_free_correction_not_cellular",
        )
        self.assertEqual(by_name["imposed_stress_correction"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["imposed_stress_correction"]["block_reason"],
            "imposed_stress_correction_not_basal",
        )
        self.assertEqual(by_name["ectopic_expression"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["ectopic_expression"]["block_reason"],
            "ectopic_not_endogenous_defect",
        )
        self.assertEqual(by_name["ectopic_correction"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["ectopic_correction"]["block_reason"],
            "ectopic_correction_not_endogenous",
        )
        self.assertEqual(by_name["unmatched_assay_specimen"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["unmatched_assay_specimen"]["block_reason"],
            "unmatched_not_assay_matched_defect",
        )
        self.assertEqual(by_name["unmatched_correction"]["blocked_by"], "hypomorph")
        self.assertEqual(
            by_name["unmatched_correction"]["block_reason"],
            "unmatched_correction_not_assay_matched",
        )
        self.assertEqual(by_name["probe_before_identity"]["blocked_by"], "next_experiment")
        self.assertEqual(by_name["kmer_without_nest"]["blocked_by"], "confirmation")
        self.assertEqual(by_name["kmer_without_file_layout"]["blocked_by"], "confirmation")
        self.assertEqual(by_name["rna_confirmation"]["blocked_by"], "confirmation")
        self.assertEqual(by_name["rna_confirmation"]["block_reason"], "rna_not_genomic")
        self.assertEqual(by_name["unmatched_confirmation_specimen"]["blocked_by"], "confirmation")
        self.assertEqual(
            by_name["unmatched_confirmation_specimen"]["block_reason"],
            "unmatched_confirmation_specimen",
        )
        self.assertEqual(by_name["nontranslational_exposure"]["blocked_by"], "exposure")
        # The exposure hold cedes attribution to the hypothesis gate, which
        # stops the observed probe/controls bound to the failed receipt.
        self.assertEqual(
            by_name["discordant_exposure"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["missing_exposure_duration"]["earliest_nonpass_gate"],
            "exposure",
        )
        self.assertEqual(
            by_name["missing_exposure_duration"]["earliest_nonpass_reason"],
            "time_hours_missing",
        )
        self.assertEqual(
            by_name["pulse_only_exposure"]["earliest_nonpass_gate"],
            "exposure",
        )
        self.assertEqual(
            by_name["pulse_only_exposure"]["earliest_nonpass_reason"],
            "pulse_only_not_advancing",
        )
        self.assertEqual(
            by_name["exposure_assay_file_collage"]["earliest_nonpass_gate"],
            "count_identity",
        )
        self.assertEqual(
            by_name["exposure_assay_file_collage"]["earliest_nonpass_reason"],
            "exposure_assay_source_mismatch",
        )
        self.assertEqual(
            by_name["arm_position_confounding"]["earliest_nonpass_gate"],
            "exposure",
        )
        self.assertEqual(
            by_name["arm_position_confounding"]["earliest_nonpass_reason"],
            "allocation_input_commitment_mismatch",
        )
        for scenario in (
            "arm_exact_column_gradient",
            "arm_row_half_interaction",
            "arm_event_order_alias",
        ):
            self.assertEqual(by_name[scenario]["earliest_nonpass_gate"], "exposure")
            self.assertEqual(
                by_name[scenario]["earliest_nonpass_reason"],
                "allocation_input_commitment_mismatch",
            )
        self.assertEqual(
            by_name["arm_local_quadratic_order_artifact"][
                "earliest_nonpass_gate"
            ],
            "count_identity",
        )
        self.assertEqual(
            by_name["arm_local_quadratic_order_artifact"][
                "earliest_nonpass_reason"
            ],
            "exact_pvalue_above_threshold",
        )
        self.assertEqual(
            by_name["arm_local_order_interaction_artifact"][
                "earliest_nonpass_gate"
            ],
            "count_identity",
        )
        self.assertEqual(
            by_name["arm_local_order_interaction_artifact"][
                "earliest_nonpass_reason"
            ],
            "exact_pvalue_above_threshold",
        )
        self.assertEqual(by_name["family_overclaim"]["blocked_by"], "family")
        self.assertEqual(by_name["dropout_compatible_phase"]["blocked_by"], "phase")
        self.assertEqual(by_name["strand_imbalance_phase"]["blocked_by"], "phase")
        self.assertEqual(by_name["unlocked_power_plan"]["blocked_by"], "assay_power")
        self.assertEqual(by_name["underpowered_plan"]["blocked_by"], "assay_power")
        self.assertEqual(by_name["missing_falsifier"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["observed_falsifier"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["unmeasured_rna_child_claim"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["bulk_aneuploidy_rescue"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["missing_alternative"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["observed_alternative"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["observed_without_gate"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["missing_controls"]["blocked_by"], "hypothesis")
        self.assertEqual(by_name["control_failed"]["blocked_by"], "hypothesis")
        self.assertEqual(
            by_name["missing_multiplicity"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["missing_counterscreen"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["missing_evidence_chain"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["supports_donation_falsifier"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["unwatched_falsifier"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["unanchored_kill_bound"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["unwatched_endpoint"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["unwatched_alternative"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["multiplicity_without_alpha"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["endpoint_without_spec"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["falsifier_bound_unequal"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["unwatched_probe_chain"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(by_name["watch_cycle"]["blocked_by"], "hypothesis")
        self.assertEqual(
            by_name["endpoint_unkilled"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["endpoint_uncontrolled"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["probe_unscreened"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["multiplicity_family_uncovered"]["blocked_by"],
            "hypothesis",
        )
        self.assertEqual(
            by_name["vacuous_second_endpoint"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["endpoint_wrong_comparator"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["endpoint_unblinded"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["observed_stability_without_assay"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(by_name["pediatric_crash_plan"]["blocked_by"], "assay_power")
        self.assertEqual(
            by_name["observed_endpoint_without_concordance"]["blocked_by"], "hypothesis"
        )
        self.assertEqual(
            by_name["later_identity_before_confirmation"]["blocked_by"],
            "next_experiment",
        )
        self.assertEqual(by_name["imaging_before_assay"]["blocked_by"], "next_experiment")
        self.assertEqual(by_name["imaging_before_assay"]["block_reason"], "imaging_before_assay")
        self.assertEqual(by_name["fitter_error_daughters"]["blocked_by"], "clone_safety")
        self.assertEqual(
            by_name["event_negative_daughter_viability"]["blocked_by"],
            "clone_safety",
        )
        self.assertEqual(by_name["bulk_fraction_endpoint"]["blocked_by"], "assay_power")
        self.assertEqual(by_name["bulk_fraction_endpoint"]["block_reason"], "false_bulk_rescue_likely")
        self.assertFalse(result["structure_ranking"]["checkpoint_ready"])
        self.assertEqual(
            by_name["predicted_stability_as_function"]["block_reason"],
            "ranking_is_not_an_assay",
        )
        # Hand-edited blinded tables must disagree with the lineage counts —
        # the core count_tables_inconsistent surface.
        self.assertEqual(
            by_name["blinded_table_tampered"]["earliest_nonpass_gate"],
            "count_identity",
        )
        self.assertEqual(
            by_name["blinded_table_tampered"]["earliest_nonpass_reason"],
            "count_tables_inconsistent",
        )
        self.assertEqual(
            by_name["blinded_row_dropped"]["earliest_nonpass_gate"],
            "count_identity",
        )
        # A flat clone that survives pooled inference must still fail the
        # per-clone concordance check — concordance's first direct coverage.
        self.assertEqual(
            by_name["single_flat_clone"]["earliest_nonpass_gate"],
            "concordance",
        )
        self.assertEqual(
            by_name["single_flat_clone"]["earliest_nonpass_reason"],
            "endpoints_not_concordant",
        )
        # The replication decision file's declared surface is corrupted.
        self.assertEqual(
            by_name["replication_declared_discordant"]["earliest_nonpass_gate"],
            "replication",
        )
        self.assertEqual(
            by_name["replication_same_site"]["earliest_nonpass_gate"],
            "replication",
        )
        self.assertEqual(
            by_name["replication_declared_exposure_failed"][
                "earliest_nonpass_gate"
            ],
            "replication",
        )
        # A bogus declared gate id stops at next_experiment on its own merit.
        self.assertEqual(by_name["unknown_next_gate"]["blocked_by"], "next_experiment")
        self.assertEqual(
            by_name["unknown_next_gate"]["block_reason"], "unknown_next_gate"
        )
        # A negated comparator label cannot satisfy the endpoint spec.
        self.assertEqual(
            by_name["endpoint_negated_comparator"]["blocked_by"], "hypothesis"
        )
        # Raise-path coverage: malformed artifacts fail closed as domain
        # errors rather than last-win or silent acceptance.
        self.assertEqual(
            by_name["blinded_duplicate_keys"]["error_type"],
            "CommunityPipelineError",
        )
        self.assertEqual(
            by_name["blinded_negative_shared_count"]["error_type"],
            "ProgramGateError",
        )
        self.assertTrue(
            by_name["blinded_duplicate_keys"]["blocked_from_advancing"]
        )
        self.assertTrue(
            by_name["blinded_negative_shared_count"]["blocked_from_advancing"]
        )
        # Every non-error false path must name the first gate that refused
        # it — a blocked row with no gate attribution is a harness failure.
        for item in result["scenarios"]:
            if (
                item["kind"] == "false_path"
                and not str(item["decision"]).startswith("error:")
            ):
                self.assertIsNotNone(
                    item["earliest_nonpass_gate"], item["name"]
                )
        # Checkpoint and manufacturability stories pin to their own gates:
        # an unassayed checkpoint holds at replication, a measured-negative
        # checkpoint stops at hypomorph, and a powered-but-unmanufacturable
        # window stops at assay_power — none may drift to a later gate.
        self.assertEqual(
            by_name["checkpoint_not_assayed"]["earliest_nonpass_gate"],
            "replication",
        )
        self.assertEqual(
            by_name["checkpoint_not_assayed"]["earliest_nonpass_reason"],
            "checkpoint_not_ready",
        )
        self.assertEqual(
            by_name["checkpoint_negative"]["earliest_nonpass_gate"],
            "hypomorph",
        )
        self.assertEqual(
            by_name["checkpoint_negative"]["earliest_nonpass_reason"],
            "no_checkpoint_defect",
        )
        self.assertEqual(
            by_name["unmanufacturable_window"]["earliest_nonpass_gate"],
            "assay_power",
        )
        self.assertEqual(
            by_name["unmanufacturable_window"]["earliest_nonpass_reason"],
            "powered_but_unmanufacturable",
        )
        self.assertEqual(
            by_name["ranking_cannot_open_checkpoint"]["earliest_nonpass_gate"],
            "hypomorph",
        )
        self.assertEqual(
            by_name["ranking_cannot_open_checkpoint"]["earliest_nonpass_reason"],
            "no_checkpoint_defect",
        )
        # Only the declared raise scenarios may error — an unexpected crash
        # anywhere else must surface as a failure, not a blocked row.
        erroring = {
            item["name"]
            for item in result["scenarios"]
            if str(item["decision"]).startswith("error:")
        }
        self.assertEqual(
            erroring,
            {
                "blinded_duplicate_keys",
                "blinded_negative_shared_count",
                "stop_transcript_persists",
                "nominal_only_exposure",
            },
        )
        # Transcript fate floors: declared status cannot outrun the measured
        # fields, a protein surrogate cannot stand in for RNA, and an invalid
        # stop-fate vocabulary raises closed.
        self.assertEqual(
            by_name["missense_not_expressed"]["earliest_nonpass_gate"],
            "transcript",
        )
        self.assertEqual(
            by_name["missense_not_expressed"]["earliest_nonpass_reason"],
            "declared_overstrong",
        )
        self.assertEqual(
            by_name["protein_not_transcript"]["earliest_nonpass_reason"],
            "protein_not_transcript",
        )
        self.assertEqual(
            by_name["stop_transcript_persists"]["error_type"],
            "ProgramGateError",
        )
        # Phase floors: disagreeing linkage calls, a single guide set, and a
        # span count under the floor all hold at phase.
        self.assertEqual(
            by_name["linkage_disagreement"]["earliest_nonpass_reason"],
            "linkage_disagreement",
        )
        self.assertEqual(
            by_name["need_two_guide_configurations"]["earliest_nonpass_reason"],
            "need_two_guide_configurations",
        )
        self.assertEqual(
            by_name["guide_span_floor"]["earliest_nonpass_reason"],
            "guide_span_floor",
        )
        # Confirmation floors cannot be silently unticked while the record
        # still claims both alleles observed.
        self.assertEqual(
            by_name["strands_not_counted"]["earliest_nonpass_reason"],
            "declared_overstrong",
        )
        self.assertEqual(
            by_name["identity_unresolved"]["earliest_nonpass_reason"],
            "declared_overstrong",
        )
        # Exposure: a nominal-only table is a vocabulary reject; nonpositive
        # exposure duration is a structured hold.
        self.assertEqual(
            by_name["nominal_only_exposure"]["error_type"],
            "ExposureGateError",
        )
        self.assertEqual(
            by_name["time_hours_nonpositive"]["earliest_nonpass_reason"],
            "time_hours_nonpositive",
        )
        # Zeroed daughter follow-ups cannot satisfy the clone-safety floor.
        self.assertEqual(
            by_name["clone_safety_under_followed"]["earliest_nonpass_gate"],
            "clone_safety",
        )
        # Treatment error daughters left unfollowed above the count floor
        # still leave unaccounted fates — completeness check holds it.
        self.assertEqual(
            by_name["clone_safety_selective_positive_followup"][
                "earliest_nonpass_gate"
            ],
            "clone_safety",
        )
        # A lineage row sampled before exposure completed cannot bind.
        self.assertEqual(
            by_name["exposure_timing_mismatch"]["earliest_nonpass_reason"],
            "exposure_timing_mismatch",
        )
        # A declared constant window below the translational floor is a
        # measurement at the instant dosing began — it cannot advance.
        self.assertEqual(
            by_name["constant_window_sub_floor"]["earliest_nonpass_gate"],
            "exposure",
        )
        # Composite tampering: the earlier defect still reports first, even
        # though a later hypothesis stop takes blocked_by attribution.
        self.assertEqual(
            by_name["composite_confirmation_plus_blinded"][
                "earliest_nonpass_gate"
            ],
            "confirmation",
        )
        # Dropping a clone's runs shrinks realized depth below the locked
        # plan, but the exposure-execution binding catches the shrinkage one
        # gate earlier — a quietly reduced realized set cannot slip through.
        self.assertEqual(
            by_name["dropped_clone_caught_by_binding"]["earliest_nonpass_gate"],
            "count_identity",
        )
        self.assertEqual(
            by_name["dropped_clone_caught_by_binding"]["earliest_nonpass_reason"],
            "exposure_assay_source_mismatch",
        )
        # A classified exposure row without vehicle controls cannot pass; the
        # stricter allocation binding fires first on the shared field.
        self.assertEqual(
            by_name["vehicle_baseline_missing"]["earliest_nonpass_gate"],
            "exposure",
        )
        self.assertEqual(
            by_name["vehicle_baseline_missing"]["earliest_nonpass_reason"],
            "allocation_execution_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
