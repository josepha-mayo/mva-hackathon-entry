from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.allele_confirmation import (
    MINIMUM_OBSERVATIONS,
    PINNED_FASTQ_NAME_DIGEST,
    confirm_alleles,
)
from mva_hackathon.clone_safety import assess_clone_safety
from mva_hackathon.arm_allocation import (
    make_allocation_analysis_plan_sha256,
    make_assignment_input_commitment,
)
from mva_hackathon.exposure_gate import assess_exposure_gate
from mva_hackathon.hypothesis import assess_hypothesis_strength, mark_pair_program_observed
from mva_hackathon.provenance import receipt_sha256
from mva_hackathon.program_gates import (
    CLAIM_BOUNDARY,
    CONFIRMATION_SCHEMA,
    PROGRAM_SCHEMA,
    TRANSCRIPT_SCHEMA,
    ProgramGateError,
    assess_confirmation_gate,
    assess_count_table_identity,
    assess_endpoint_concordance,
    assess_hypomorph_gate,
    assess_phase_gate,
    assess_replication_decision,
    assess_transcript_gate,
)
from mva_hackathon.save_path import (
    _relabel_unattested_synthetic_fixture_to_seed,
    passing_exposure,
)


ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = ROOT / "templates" / "community"


def _json(name: str) -> dict:
    return json.loads((COMMUNITY / name).read_text(encoding="utf-8"))


def _lineage_counts(
    *,
    n_events: int = 3,
    n_clones: int = 2,
    treatment_positive: int = 4,
    vehicle_positive: int = 12,
    treatment_divisions: int = 36,
    vehicle_divisions: int = 36,
    opportunities: int = 38,
    treatment_death: int = 1,
    vehicle_death: int = 1,
    treatment_dropout: int = 0,
    vehicle_dropout: int = 0,
    followed: int | None = None,
    reproduced: int | None = None,
    died: int | None = None,
) -> dict:
    treatment_profile_id = next(
        row["exposure_profile_id"]
        for row in _json("measured_exposure_table.synthetic.json")["rows"]
        if row["nominal_uM"] == 1.0 and row["pulse_vs_constant"] == "constant"
    )
    runs = []
    for index in range(1, n_events + 1):
        event_id = f"syn-event-{index}"
        for clone_index in range(1, n_clones + 1):
            clone_id = f"syn-clone-{index}-{clone_index}"
            for arm, positive, divisions, death, dropout, member in (
                (
                    "vehicle",
                    vehicle_positive,
                    vehicle_divisions,
                    vehicle_death,
                    vehicle_dropout,
                    "member-a",
                ),
                (
                    "treatment",
                    treatment_positive,
                    treatment_divisions,
                    treatment_death,
                    treatment_dropout,
                    "member-b",
                ),
            ):
                no_division = opportunities - divisions - death - dropout
                if no_division < 0:
                    raise AssertionError("test counts cannot partition first-attempt outcomes")
                arm_followed = followed if followed is not None else 2 * positive
                arm_reproduced = (
                    reproduced if reproduced is not None else arm_followed // 2
                )
                # Default to fully resolved fates: every observed daughter
                # either reproduces or dies. An explicit died value below
                # (followed - reproduced) leaves censored daughters — the
                # unresolved channel the contract now fails closed on.
                arm_died = (
                    died if died is not None else arm_followed - arm_reproduced
                )
                if arm_followed > 2 * positive:
                    raise AssertionError("test follow-up exceeds two daughters per error division")
                if arm_reproduced + arm_died > arm_followed:
                    raise AssertionError("test resolved daughters exceed followed")
                runs.append(
                    {
                        "arm": arm,
                        "edit_event_id": event_id,
                        "clone_id": clone_id,
                        "run_id": f"syn-run-{index}",
                        "batch_id": "syn-batch-a",
                        "functional_execution_id": (
                            f"syn-functional-{index}-{clone_index}-{member}"
                        ),
                        "exposure_support_record_id": (
                            "syn-measurement-3"
                            if arm == "treatment"
                            else "syn-vehicle-control-record-a"
                        ),
                        "exposure_profile_id": (
                            treatment_profile_id
                            if arm == "treatment"
                            else "profile-vehicle-control"
                        ),
                        "exposure_probe_id": (
                            "syn-probe-a" if arm == "treatment" else "syn-vehicle-a"
                        ),
                        "exposure_started_at": "2026-08-29T01:00:00Z",
                        "endpoint_recorded_at": "2026-08-30T02:00:00Z",
                        "latest_enrolled_at": "2026-08-29T00:00:00Z",
                        "opportunities": opportunities,
                        "detected_divisions": divisions,
                        "event_positive_divisions": positive,
                        "event_negative_divisions": divisions - positive,
                        "event_positive_daughters_followed": arm_followed,
                        "event_positive_daughters_reproduced": arm_reproduced,
                        "event_positive_daughters_died": arm_died,
                        "event_negative_daughters_followed": 8,
                        "event_negative_daughters_reproduced": 8,
                        "event_negative_daughters_died": 0,
                        "pre_division_death": death,
                        "no_division": no_division,
                        "dropout_censored": dropout,
                    }
                )
    return {
        "schema": "mva-track2-lineage-counts/v1",
        "study_id": "syn-save-path-lineage",
        "synthetic_only": True,
        "lock_state": "locked",
        "blinded": True,
        "runs": runs,
    }


def _scorecard(
    *,
    checkpoint: str = "not_assessable",
    specificity: str = "exact",
    exact_abundance: str = "negative",
    chaperone_pd: str | None = None,
) -> dict:
    card = _json("allele_function_scorecard.synthetic.json")
    for row in card["rows"]:
        if row["genotype_class"] == "missense":
            row["allele_specificity"] = specificity
            if chaperone_pd is not None:
                row["assessments"].append(
                    {
                        "endpoint": "chaperone_pd",
                        "assessment_status": chaperone_pd,
                        "assay_class": "wet",
                    }
                )
        if row["genotype_class"] in {"missense", "recreated_missense"}:
            for item in row["assessments"]:
                if item["endpoint"] == "checkpoint":
                    item["assessment_status"] = checkpoint
                    if checkpoint == "positive":
                        item["assay_class"] = "wet"
                        item["condition_class"] = "basal"
                        item["system_class"] = "cellular"
                        item["expression_class"] = "endogenous"
                        item["specimen_class"] = "assay_matched"
        if row["genotype_class"] == "exact_corrected":
            for item in row["assessments"]:
                if item["endpoint"] == "abundance":
                    item["assessment_status"] = exact_abundance
    return card


def _set_carrier_endpoint(
    card: dict, genotype_class: str, endpoint: str, status: str
) -> None:
    for row in card["rows"]:
        if row["genotype_class"] != genotype_class:
            continue
        for item in row["assessments"]:
            if item["endpoint"] == endpoint:
                item["assessment_status"] = status
                item["assay_class"] = "wet"
                item["condition_class"] = "basal"
                item["system_class"] = "cellular"
                item["expression_class"] = "endogenous"
                item["specimen_class"] = "assay_matched"


def _child_claim_ready_evidence() -> dict:
    return mark_pair_program_observed(_json("observed_inferred_unknown.synthetic.json"))


def _bound_child_claim_hypothesis(*, hypomorph: dict | None = None) -> dict:
    return assess_hypothesis_strength(
        _child_claim_ready_evidence(),
        confirmation=_pass_confirmation(),
        phase=_pass_phase(),
        transcript=_pass_transcript(),
        hypomorph=hypomorph
        if hypomorph is not None
        else assess_hypomorph_gate(_scorecard(checkpoint="positive")),
        exposure=assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
    )


def _pass_confirmation() -> dict:
    return assess_confirmation_gate(
        {
            "schema": CONFIRMATION_SCHEMA,
            "specimen_identity_resolved": True,
            "second_aliquot": True,
            "layout_complete": True,
            "both_strands_counted": True,
            "allele_1_status": "both_alleles_observed",
            "allele_2_status": "both_alleles_observed",
            "declared_status": "both_alleles_observed",
            "producer": "synthetic_handoff",
            "library_molecule": "genomic",
            "confirmation_specimen": "assay_matched",
        }
    )


def _pass_phase() -> dict:
    return assess_phase_gate(_json("phase_record.synthetic.json"))


def _pass_transcript() -> dict:
    return assess_transcript_gate(
        {
            "schema": TRANSCRIPT_SCHEMA,
            "stop_allele_rna": "deplete",
            "missense_allele_rna": "expressed",
            "declared_status": "stop_depleted_missense_expressed",
            "transcript_method": "allele_specific",
            "transcript_specimen": "assay_matched",
        }
    )


def _nested_replication(
    *,
    hypomorph: dict | None = None,
    hypothesis: dict | None = None,
    concordant: bool = True,
    confirmation: dict | None = None,
    phase: dict | None = None,
    transcript: dict | None = None,
) -> dict:
    payload = _json("replication_decision.synthetic.json")
    payload["endpoints_concordant"] = concordant
    counts = _lineage_counts()
    kwargs: dict = {
        "clone_safety": assess_clone_safety(counts),
        "exposure": assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
        "concordance": assess_endpoint_concordance(counts),
        "confirmation": confirmation if confirmation is not None else _pass_confirmation(),
        "phase": phase if phase is not None else _pass_phase(),
        "transcript": transcript if transcript is not None else _pass_transcript(),
    }
    if hypomorph is not None:
        kwargs["hypomorph"] = hypomorph
    if hypothesis is not None:
        kwargs["hypothesis"] = hypothesis
    return assess_replication_decision(payload, **kwargs)


def _blinded_from_lineage(lineage: dict) -> dict:
    runs = []
    for row in lineage["runs"]:
        runs.append(
            {
                "arm": row["arm"],
                "edit_event_id": int(str(row["edit_event_id"]).rsplit("-", 1)[-1]),
                "clone_id": int(str(row["clone_id"]).rsplit("-", 1)[-1]),
                "run_id": int(str(row["run_id"]).rsplit("-", 1)[-1]),
                "opportunities": row["opportunities"],
                "detected_divisions": row["detected_divisions"],
                "event_positive_divisions": row["event_positive_divisions"],
                "event_negative_divisions": row["event_negative_divisions"],
                "event_positive_daughters_followed": row[
                    "event_positive_daughters_followed"
                ],
                "event_positive_daughters_reproduced": row[
                    "event_positive_daughters_reproduced"
                ],
                "event_positive_daughters_died": row.get(
                    "event_positive_daughters_died", 0
                ),
                "event_negative_daughters_followed": row.get(
                    "event_negative_daughters_followed", 0
                ),
                "event_negative_daughters_reproduced": row.get(
                    "event_negative_daughters_reproduced", 0
                ),
                "event_negative_daughters_died": row.get(
                    "event_negative_daughters_died", 0
                ),
                "event_positive_daughter_slots": row.get(
                    "event_positive_daughter_slots"
                ),
                "event_negative_daughter_slots": row.get(
                    "event_negative_daughter_slots"
                ),
                "event_positive_multipolar_divisions": row.get(
                    "event_positive_multipolar_divisions"
                ),
                "pre_division_death": row.get("pre_division_death", 0),
                "no_division": row.get("no_division", 0),
                "dropout_censored": row.get("dropout_censored", 0),
            }
        )
    return {
        "schema": "mva.community-blinded-count-table/v2",
        "privacy_class": "synthetic",
        "purpose": "Aligned synthetic blinded counts for identity tests.",
        "observed_run_fields": [
            "arm",
            "edit_event_id",
            "clone_id",
            "run_id",
            "opportunities",
            "detected_divisions",
            "event_positive_divisions",
            "event_negative_divisions",
            "event_positive_daughters_followed",
            "event_positive_daughters_reproduced",
            "event_positive_daughters_died",
            "event_negative_daughters_followed",
            "event_negative_daughters_reproduced",
            "event_negative_daughters_died",
            "event_positive_daughter_slots",
            "event_negative_daughter_slots",
            "event_positive_multipolar_divisions",
            "pre_division_death",
            "no_division",
            "dropout_censored",
        ],
        "runs": runs,
    }


def _linked_count_inputs() -> tuple[dict, dict, dict, dict]:
    counts = _lineage_counts(
        n_clones=6,
        opportunities=36,
        treatment_death=0,
        vehicle_death=0,
    )
    plan = _json("assay_power.synthetic.json")
    exposure = passing_exposure(counts, plan)
    return counts, _blinded_from_lineage(counts), exposure, plan


class ProgramGateTests(unittest.TestCase):
    def test_community_phase_passes_when_floors_met(self) -> None:
        result = assess_phase_gate(_json("phase_record.synthetic.json"))
        self.assertEqual(result["schema"], PROGRAM_SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["computed_decision"], "trans_confirmed")
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["declared_overridden"])
        self.assertEqual(result["phase_method"], "molecule_spanning")
        self.assertEqual(result["phase_specimen"], "assay_matched")

    def test_phase_overrides_trans_when_molecule_floor_fails(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["molecule_counts"]["haplotype_b_full_span"] = 2
        result = assess_phase_gate(record)
        self.assertEqual(result["computed_decision"], "unresolved")
        self.assertTrue(result["declared_overridden"])
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "allelic_dropout_floor")

    def test_duplicate_guide_configurations_cannot_confirm_trans(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["guide_configurations"][1]["config_id"] = record["guide_configurations"][0][
            "config_id"
        ]
        result = assess_phase_gate(record)
        self.assertEqual(result["computed_decision"], "unresolved")
        self.assertEqual(result["reason"], "duplicate_guide_configurations")
        self.assertEqual(result["program_effect"], "hold")

    def test_cis_stops_the_pair_story(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["decision"] = "cis_confirmed"
        for guide in record["guide_configurations"]:
            guide["linkage_call"] = "cis"
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["program_effect"], "stop")
        self.assertEqual(result["reason"], "linkage_agreed_cis")

    def test_trans_tick_without_linkage_cannot_pass(self) -> None:
        record = _json("phase_record.synthetic.json")
        for guide in record["guide_configurations"]:
            guide.pop("linkage_call", None)
        result = assess_phase_gate(record)
        self.assertEqual(result["computed_decision"], "unresolved")
        self.assertEqual(result["reason"], "linkage_not_recorded")
        self.assertEqual(result["program_effect"], "hold")

    def test_guide_linkage_disagreement_holds(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["guide_configurations"][1]["linkage_call"] = "cis"
        result = assess_phase_gate(record)
        self.assertEqual(result["reason"], "linkage_disagreement")
        self.assertEqual(result["program_effect"], "hold")

    def test_trans_guides_cannot_upgrade_a_cis_declaration(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["decision"] = "cis_confirmed"
        result = assess_phase_gate(record)
        self.assertEqual(result["reason"], "declared_linkage_mismatch")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["computed_decision"], "unresolved")

    def test_community_confirmation_holds(self) -> None:
        result = assess_confirmation_gate(_json("confirmation_record.synthetic.json"))
        self.assertEqual(result["schema"], PROGRAM_SCHEMA)
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "layout_incomplete")
        self.assertEqual(result["computed_status"], "incomplete_inputs")

    def test_declared_both_alleles_without_floors_is_overstrong(self) -> None:
        record = _json("confirmation_record.synthetic.json")
        record["declared_status"] = "both_alleles_observed"
        result = assess_confirmation_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "declared_overstrong")

    def test_complete_confirmation_passes(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "synthetic_handoff",
                "library_molecule": "genomic",
                "confirmation_specimen": "assay_matched",
            }
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "confirmation_floors_met")
        self.assertEqual(result["confirmation_specimen"], "assay_matched")

    def test_ticked_confirmation_without_a_producer_cannot_pass(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "unlinked",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "declared_overstrong")
        self.assertEqual(result["computed_status"], "incomplete_inputs")

    def test_kmer_digest_without_nested_object_cannot_pass(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "kmer_layout",
                "layout_digest": PINNED_FASTQ_NAME_DIGEST,
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "declared_overstrong")
        self.assertEqual(result["computed_status"], "incomplete_inputs")

    def test_nested_kmer_confirmation_can_pass(self) -> None:
        flank_left = "ACGTACGTACGTACGTACGTACGTA"
        flank_right = "TGCATGCATGCATGCATGCATGCAT"
        allele_one = {
            "allele_id": "syn-allele-1",
            "flank_left": flank_left,
            "ref": "A",
            "alt": "C",
            "flank_right": flank_right,
        }
        allele_two = {
            "allele_id": "syn-allele-2",
            "flank_left": flank_left,
            "ref": "G",
            "alt": "T",
            "flank_right": flank_right,
        }
        sequences = (
            [flank_left + "A" + flank_right] * MINIMUM_OBSERVATIONS
            + [flank_left + "C" + flank_right] * MINIMUM_OBSERVATIONS
            + [flank_left + "G" + flank_right] * MINIMUM_OBSERVATIONS
            + [flank_left + "T" + flank_right] * MINIMUM_OBSERVATIONS
        )
        nested = confirm_alleles([allele_one, allele_two], sequences)
        layout = {
            "n_files": 8,
            "expected_n_files": 8,
            "incomplete": False,
            "name_digest": PINNED_FASTQ_NAME_DIGEST,
            "paired_stems": 4,
            "unpaired_stems": 0,
            "unlabeled_files": 0,
            "reasons": [],
        }
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "kmer_layout",
                "layout_digest": PINNED_FASTQ_NAME_DIGEST,
                "kmer_confirmation": nested,
                "layout": layout,
                "library_molecule": "genomic",
                "confirmation_specimen": "assay_matched",
            }
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "confirmation_floors_met")
        self.assertEqual(result["producer"], "kmer_layout")

    def test_truncated_kmer_layout_cannot_pass(self) -> None:
        nested = {
            "schema": "mva-track2-allele-confirmation/v1",
            "incomplete_inputs": False,
            "reverse_complement_counted": True,
            "alleles": [
                {
                    "status": "both_alleles_observed",
                    "by_k": [
                        {"k": 31, "status": "both_alleles_observed"},
                        {"k": 51, "status": "both_alleles_observed"},
                    ],
                },
                {
                    "status": "both_alleles_observed",
                    "by_k": [
                        {"k": 31, "status": "both_alleles_observed"},
                        {"k": 51, "status": "both_alleles_observed"},
                    ],
                },
            ],
        }
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "kmer_layout",
                "layout_digest": PINNED_FASTQ_NAME_DIGEST,
                "kmer_confirmation": nested,
                "layout": {
                    "n_files": 5,
                    "expected_n_files": 8,
                    "incomplete": True,
                    "name_digest": PINNED_FASTQ_NAME_DIGEST,
                    "reasons": ["fewer_files_than_expected"],
                },
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "declared_overstrong")
        self.assertEqual(result["computed_status"], "incomplete_inputs")

    def test_rna_library_cannot_confirm_genomic_genotype(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "synthetic_handoff",
                "library_molecule": "rna",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "rna_not_genomic")
        self.assertEqual(result["computed_status"], "incomplete_inputs")
        self.assertEqual(result["library_molecule"], "rna")

    def test_unlabeled_library_molecule_cannot_confirm(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "synthetic_handoff",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "library_molecule_required")
        self.assertEqual(result["library_molecule"], "unlabeled")

    def test_invalid_library_molecule_is_malformed(self) -> None:
        with self.assertRaisesRegex(ProgramGateError, "library_molecule"):
            assess_confirmation_gate(
                {
                    "schema": CONFIRMATION_SCHEMA,
                    "specimen_identity_resolved": True,
                    "second_aliquot": True,
                    "layout_complete": True,
                    "both_strands_counted": True,
                    "allele_1_status": "both_alleles_observed",
                    "allele_2_status": "both_alleles_observed",
                    "declared_status": "both_alleles_observed",
                    "producer": "synthetic_handoff",
                    "library_molecule": "protein",
                }
            )

    def test_unmatched_confirmation_specimen_cannot_stand_in(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "synthetic_handoff",
                "library_molecule": "genomic",
                "confirmation_specimen": "unmatched",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unmatched_confirmation_specimen")
        self.assertEqual(result["computed_status"], "incomplete_inputs")
        self.assertEqual(result["confirmation_specimen"], "unmatched")

    def test_unlabeled_confirmation_specimen_cannot_pass(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "synthetic_handoff",
                "library_molecule": "genomic",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "confirmation_specimen_required")
        self.assertEqual(result["confirmation_specimen"], "unlabeled")

    def test_invalid_confirmation_specimen_is_malformed(self) -> None:
        with self.assertRaisesRegex(ProgramGateError, "confirmation_specimen"):
            assess_confirmation_gate(
                {
                    "schema": CONFIRMATION_SCHEMA,
                    "specimen_identity_resolved": True,
                    "second_aliquot": True,
                    "layout_complete": True,
                    "both_strands_counted": True,
                    "allele_1_status": "both_alleles_observed",
                    "allele_2_status": "both_alleles_observed",
                    "declared_status": "both_alleles_observed",
                    "producer": "synthetic_handoff",
                    "library_molecule": "genomic",
                    "confirmation_specimen": "blood",
                }
            )

    def test_rna_library_still_blocks_before_unmatched_specimen(self) -> None:
        result = assess_confirmation_gate(
            {
                "schema": CONFIRMATION_SCHEMA,
                "specimen_identity_resolved": True,
                "second_aliquot": True,
                "layout_complete": True,
                "both_strands_counted": True,
                "allele_1_status": "both_alleles_observed",
                "allele_2_status": "both_alleles_observed",
                "declared_status": "both_alleles_observed",
                "producer": "synthetic_handoff",
                "library_molecule": "rna",
                "confirmation_specimen": "unmatched",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "rna_not_genomic")

    def test_incomplete_confirmation_holds_before_specimen_class(self) -> None:
        result = assess_confirmation_gate(_json("confirmation_record.synthetic.json"))
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "layout_incomplete")
        self.assertEqual(result["confirmation_specimen"], "unlabeled")

    def test_guide_span_below_floor_cannot_confirm_trans(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["guide_configurations"][1]["full_span_molecules"] = 2
        result = assess_phase_gate(record)
        self.assertEqual(result["reason"], "guide_span_floor")
        self.assertEqual(result["program_effect"], "hold")

    def test_dropout_compatible_split_cannot_confirm_trans(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["molecule_counts"]["minimum_full_span_per_haplotype"] = 8
        record["molecule_counts"]["haplotype_a_full_span"] = 100
        record["molecule_counts"]["haplotype_b_full_span"] = 8
        result = assess_phase_gate(record)
        self.assertEqual(result["computed_decision"], "unresolved")
        self.assertEqual(result["reason"], "dropout_compatible")
        self.assertEqual(result["program_effect"], "hold")

    def test_strand_imbalance_cannot_confirm_trans(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["guide_configurations"][0]["strand_balance"] = 0.95
        result = assess_phase_gate(record)
        self.assertEqual(result["computed_decision"], "unresolved")
        self.assertEqual(result["reason"], "strand_imbalance")
        self.assertEqual(result["program_effect"], "hold")

    def test_computational_phase_cannot_stand_in_for_molecules(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_method"] = "computational"
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["program_effect"], "stop")
        self.assertEqual(result["reason"], "computational_phase_not_molecule")
        self.assertEqual(result["computed_decision"], "unresolved")

    def test_rna_phase_cannot_stand_in_for_genomic_phase(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_method"] = "rna"
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "rna_phase_not_genomic")

    def test_unlabeled_phase_method_cannot_pass(self) -> None:
        record = _json("phase_record.synthetic.json")
        record.pop("phase_method", None)
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "phase_method_required")

    def test_parental_phase_can_pass_when_floors_met(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_method"] = "parental"
        record["phase_specimen"] = "parental"
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["computed_decision"], "trans_confirmed")
        self.assertEqual(result["phase_method"], "parental")
        self.assertEqual(result["phase_specimen"], "parental")

    def test_unmatched_phase_specimen_cannot_stand_in(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_specimen"] = "unmatched"
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unmatched_phase_specimen")
        self.assertEqual(result["computed_decision"], "unresolved")

    def test_unlabeled_phase_specimen_cannot_pass(self) -> None:
        record = _json("phase_record.synthetic.json")
        record.pop("phase_specimen", None)
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "phase_specimen_required")

    def test_invalid_phase_specimen_is_malformed(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_specimen"] = "blood"
        with self.assertRaisesRegex(ProgramGateError, "phase_specimen"):
            assess_phase_gate(record)

    def test_computational_phase_still_blocks_before_unmatched_specimen(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_method"] = "computational"
        record["phase_specimen"] = "unmatched"
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "computational_phase_not_molecule")

    def test_parental_method_on_assay_matched_specimen_cannot_pass(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_method"] = "parental"
        record["phase_specimen"] = "assay_matched"
        result = assess_phase_gate(record)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unmatched_phase_specimen")

    def test_dropout_hold_is_not_stolen_by_unlabeled_specimen(self) -> None:
        record = _json("phase_record.synthetic.json")
        record.pop("phase_specimen", None)
        record["molecule_counts"]["minimum_full_span_per_haplotype"] = 8
        record["molecule_counts"]["haplotype_a_full_span"] = 100
        record["molecule_counts"]["haplotype_b_full_span"] = 8
        result = assess_phase_gate(record)
        self.assertEqual(result["reason"], "dropout_compatible")
        self.assertEqual(result["program_effect"], "hold")

    def test_invalid_phase_method_is_malformed(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["phase_method"] = "imputation"
        with self.assertRaisesRegex(ProgramGateError, "phase_method"):
            assess_phase_gate(record)

    def test_computational_phase_does_not_steal_cis(self) -> None:
        record = _json("phase_record.synthetic.json")
        record["decision"] = "cis_confirmed"
        record["phase_method"] = "computational"
        for guide in record["guide_configurations"]:
            guide["linkage_call"] = "cis"
        result = assess_phase_gate(record)
        self.assertEqual(result["computed_decision"], "cis_confirmed")
        self.assertEqual(result["program_effect"], "stop")
        self.assertEqual(result["reason"], "linkage_agreed_cis")

    def test_community_transcript_holds(self) -> None:
        result = assess_transcript_gate(_json("transcript_record.synthetic.json"))
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "transcript_not_measured")

    def test_depleted_stop_and_expressed_missense_can_pass_transcript(self) -> None:
        result = _pass_transcript()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "stop_depleted_missense_expressed")
        self.assertEqual(result["transcript_method"], "allele_specific")
        self.assertEqual(result["transcript_specimen"], "assay_matched")

    def test_unmatched_transcript_specimen_cannot_stand_in(self) -> None:
        result = assess_transcript_gate(
            {
                "schema": TRANSCRIPT_SCHEMA,
                "stop_allele_rna": "deplete",
                "missense_allele_rna": "expressed",
                "declared_status": "stop_depleted_missense_expressed",
                "transcript_method": "allele_specific",
                "transcript_specimen": "unmatched",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unmatched_transcript_specimen")

    def test_unlabeled_transcript_specimen_cannot_pass(self) -> None:
        result = assess_transcript_gate(
            {
                "schema": TRANSCRIPT_SCHEMA,
                "stop_allele_rna": "deplete",
                "missense_allele_rna": "expressed",
                "declared_status": "stop_depleted_missense_expressed",
                "transcript_method": "allele_specific",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "transcript_specimen_required")

    def test_invalid_transcript_specimen_is_malformed(self) -> None:
        with self.assertRaisesRegex(ProgramGateError, "transcript_specimen"):
            assess_transcript_gate(
                {
                    "schema": TRANSCRIPT_SCHEMA,
                    "stop_allele_rna": "deplete",
                    "missense_allele_rna": "expressed",
                    "declared_status": "stop_depleted_missense_expressed",
                    "transcript_method": "allele_specific",
                    "transcript_specimen": "blood",
                }
            )

    def test_unmeasured_rna_holds_before_specimen_class(self) -> None:
        result = assess_transcript_gate(_json("transcript_record.synthetic.json"))
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "transcript_not_measured")

    def test_computational_transcript_cannot_stand_in_for_rna(self) -> None:
        result = assess_transcript_gate(
            {
                "schema": TRANSCRIPT_SCHEMA,
                "stop_allele_rna": "deplete",
                "missense_allele_rna": "expressed",
                "declared_status": "stop_depleted_missense_expressed",
                "transcript_method": "computational",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "computational_transcript_not_assay")

    def test_protein_surrogate_cannot_stand_in_for_rna(self) -> None:
        result = assess_transcript_gate(
            {
                "schema": TRANSCRIPT_SCHEMA,
                "stop_allele_rna": "deplete",
                "missense_allele_rna": "expressed",
                "declared_status": "stop_depleted_missense_expressed",
                "transcript_method": "protein_surrogate",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "protein_not_transcript")

    def test_unlabeled_transcript_method_cannot_pass(self) -> None:
        result = assess_transcript_gate(
            {
                "schema": TRANSCRIPT_SCHEMA,
                "stop_allele_rna": "deplete",
                "missense_allele_rna": "expressed",
                "declared_status": "stop_depleted_missense_expressed",
            }
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "transcript_method_required")

    def test_invalid_transcript_method_is_malformed(self) -> None:
        with self.assertRaisesRegex(ProgramGateError, "transcript_method"):
            assess_transcript_gate(
                {
                    "schema": TRANSCRIPT_SCHEMA,
                    "stop_allele_rna": "deplete",
                    "missense_allele_rna": "expressed",
                    "declared_status": "stop_depleted_missense_expressed",
                    "transcript_method": "western",
                }
            )

    def test_computational_stability_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assay_class"] = "computational_structure"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "computational_not_assay")
        self.assertFalse(result["probe_eligible"])

    def test_computational_correction_cannot_reverse_a_wet_missense_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["assay_class"] = "computational_structure"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "computational_correction_not_assay")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["computational_correction_endpoints"])

    def test_unlabeled_correction_cannot_reverse_a_wet_missense_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["assay_class"] = "unlabeled"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unlabeled_correction_not_assay")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_correction_endpoints"])

    def test_cell_free_correction_cannot_reverse_a_cellular_missense_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["system_class"] = "cell_free_biophysical"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "cell_free_correction_not_cellular")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["cell_free_correction_endpoints"])

    def test_unlabeled_correction_system_class_cannot_reverse_a_cellular_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                item.pop("system_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unlabeled_correction_system_class")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_correction_system_endpoints"])

    def test_imposed_stress_correction_cannot_reverse_a_basal_missense_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["condition_class"] = "imposed_extrinsic_stress"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "imposed_stress_correction_not_basal")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["imposed_stress_correction_endpoints"])

    def test_unlabeled_correction_condition_class_cannot_reverse_a_basal_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                item.pop("condition_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unlabeled_correction_condition_class")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_correction_condition_endpoints"])

    def test_ectopic_correction_cannot_reverse_an_endogenous_missense_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["expression_class"] = "ectopic"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "ectopic_correction_not_endogenous")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["ectopic_correction_endpoints"])

    def test_unlabeled_correction_expression_class_cannot_reverse_an_endogenous_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                item.pop("expression_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unlabeled_correction_expression_class")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_correction_expression_endpoints"])

    def test_unmatched_correction_cannot_reverse_an_assay_matched_missense_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["specimen_class"] = "unmatched"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unmatched_correction_not_assay_matched")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unmatched_correction_endpoints"])

    def test_unlabeled_correction_specimen_cannot_reverse_an_assay_matched_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                item.pop("specimen_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unlabeled_correction_specimen_class")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_correction_specimen_endpoints"])

    def test_ectopic_correction_still_blocks_before_unmatched_correction(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["expression_class"] = "ectopic"
                    item["specimen_class"] = "unmatched"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["reason"], "ectopic_correction_not_endogenous")

    def test_analog_correction_cannot_reverse_an_exact_missense_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "exact_corrected":
                row["allele_specificity"] = "analog"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "analog_correction_not_exact")
        self.assertFalse(result["probe_eligible"])
        self.assertEqual(result["correction_allele_specificity"], "analog")

    def test_homolog_and_nearby_correction_are_the_same_analog_family(self) -> None:
        for specificity in ("homolog", "nearby"):
            scorecard = _scorecard()
            for row in scorecard["rows"]:
                if row["genotype_class"] == "exact_corrected":
                    row["allele_specificity"] = specificity
            result = assess_hypomorph_gate(scorecard)
            self.assertEqual(result["reason"], "analog_correction_not_exact")

    def test_unlabeled_correction_specificity_cannot_reverse_an_exact_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "exact_corrected":
                row.pop("allele_specificity", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "correction_specificity_required")
        self.assertFalse(result["probe_eligible"])

    def test_invalid_correction_specificity_is_malformed(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "exact_corrected":
                row["allele_specificity"] = "parental"
        with self.assertRaises(ProgramGateError):
            assess_hypomorph_gate(scorecard)

    def test_analog_missense_still_blocks_before_analog_correction(self) -> None:
        scorecard = _scorecard(specificity="analog")
        for row in scorecard["rows"]:
            if row["genotype_class"] == "exact_corrected":
                row["allele_specificity"] = "analog"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["reason"], "analog_as_exact_function")

    def test_unmatched_correction_still_blocks_before_analog_correction(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "exact_corrected":
                continue
            row["allele_specificity"] = "analog"
            for item in row["assessments"]:
                if item["assessment_status"] == "negative":
                    item["specimen_class"] = "unmatched"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["reason"], "unmatched_correction_not_assay_matched")

    def test_missing_recreated_missense_row_is_malformed(self) -> None:
        scorecard = _json("allele_function_scorecard.synthetic.json")
        scorecard["rows"] = [
            row
            for row in scorecard["rows"]
            if row["genotype_class"] != "recreated_missense"
        ]
        with self.assertRaises(ProgramGateError):
            assess_hypomorph_gate(scorecard)

    def test_failed_recreation_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assessment_status"] = "negative"
                    item["assay_class"] = "wet"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_did_not_restore_defect")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["restoration_failed_endpoints"])

    def test_computational_recreation_cannot_restore_a_wet_missense_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assay_class"] = "computational_structure"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "computational_recreation_not_assay")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["computational_recreation_endpoints"])

    def test_unlabeled_recreation_cannot_restore_a_wet_missense_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assay_class"] = "unlabeled"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unlabeled_recreation_not_assay")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_recreation_endpoints"])

    def test_imposed_stress_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["condition_class"] = "imposed_extrinsic_stress"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "imposed_stress_not_basal_defect")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["imposed_stress_endpoints"])

    def test_unlabeled_condition_class_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                item.pop("condition_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "condition_class_required")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_condition_endpoints"])

    def test_imposed_stress_recreation_cannot_restore_a_basal_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["condition_class"] = "imposed_extrinsic_stress"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_imposed_stress_not_basal")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["recreation_imposed_stress_endpoints"])

    def test_cell_free_biophysical_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["system_class"] = "cell_free_biophysical"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "cell_free_not_cellular_defect")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["cell_free_endpoints"])

    def test_unlabeled_system_class_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                item.pop("system_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "system_class_required")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_system_endpoints"])

    def test_cell_free_recreation_cannot_restore_a_cellular_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["system_class"] = "cell_free_biophysical"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_cell_free_not_cellular")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["recreation_cell_free_endpoints"])

    def test_unlabeled_recreation_system_class_cannot_restore_a_cellular_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                item.pop("system_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_system_class_required")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_recreation_system_endpoints"])

    def test_ectopic_expression_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["expression_class"] = "ectopic"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "ectopic_not_endogenous_defect")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["ectopic_expression_endpoints"])

    def test_unlabeled_expression_class_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                item.pop("expression_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "expression_class_required")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_expression_endpoints"])

    def test_ectopic_recreation_cannot_restore_an_endogenous_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["expression_class"] = "ectopic"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_ectopic_not_endogenous")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["recreation_ectopic_endpoints"])

    def test_unlabeled_recreation_expression_cannot_restore_an_endogenous_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                item.pop("expression_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_expression_class_required")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_recreation_expression_endpoints"])

    def test_unmatched_assay_specimen_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["specimen_class"] = "unmatched"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "unmatched_not_assay_matched_defect")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unmatched_specimen_endpoints"])

    def test_unlabeled_specimen_class_cannot_make_a_probe_eligible(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                item.pop("specimen_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "specimen_class_required")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_specimen_endpoints"])

    def test_invalid_specimen_class_is_malformed(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["specimen_class"] = "parental"
        with self.assertRaises(ProgramGateError):
            assess_hypomorph_gate(scorecard)

    def test_ectopic_still_blocks_before_unmatched_specimen(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["expression_class"] = "ectopic"
                    item["specimen_class"] = "unmatched"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["reason"], "ectopic_not_endogenous_defect")

    def test_unmatched_recreation_cannot_restore_an_assay_matched_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                if item["assessment_status"] == "positive":
                    item["specimen_class"] = "unmatched"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_unmatched_not_assay_matched")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["recreation_unmatched_specimen_endpoints"])

    def test_unlabeled_recreation_specimen_cannot_restore_an_assay_matched_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            for item in row["assessments"]:
                item.pop("specimen_class", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_specimen_class_required")
        self.assertFalse(result["probe_eligible"])
        self.assertIn("abundance", result["unlabeled_recreation_specimen_endpoints"])

    def test_community_scorecard_makes_a_probe_eligible(self) -> None:
        result = assess_hypomorph_gate(_json("allele_function_scorecard.synthetic.json"))
        self.assertTrue(result["probe_eligible"])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["allele_specificity"], "exact")
        self.assertEqual(result["recreation_allele_specificity"], "exact")
        self.assertFalse(result["checkpoint_ready"])
        self.assertFalse(result["pharmacodynamic_not_target"])

    def test_negative_missense_stability_stops_the_probe(self) -> None:
        scorecard = _json("allele_function_scorecard.synthetic.json")
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assessment_status"] = "negative"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertFalse(result["probe_eligible"])
        self.assertEqual(result["reason"], "no_missense_stability_defect")

    def test_wildtype_positive_stability_fails_closed(self) -> None:
        scorecard = _json("allele_function_scorecard.synthetic.json")
        for row in scorecard["rows"]:
            if row["genotype_class"] != "wt":
                continue
            for item in row["assessments"]:
                if item["endpoint"] == "abundance":
                    item["assessment_status"] = "positive"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "wildtype_stability_positive")

    def test_dominant_interference_stops_the_probe(self) -> None:
        scorecard = _json("allele_function_scorecard.synthetic.json")
        _set_carrier_endpoint(scorecard, "missense_carrier", "checkpoint", "positive")
        _set_carrier_endpoint(scorecard, "stop", "checkpoint", "negative")
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "dominant_interference_possible")
        self.assertFalse(result["probe_eligible"])

    def test_carrier_defect_without_dose_control_holds(self) -> None:
        scorecard = _json("allele_function_scorecard.synthetic.json")
        _set_carrier_endpoint(scorecard, "missense_carrier", "checkpoint", "positive")
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "carrier_dose_control_required")
        self.assertFalse(result["probe_eligible"])

    def test_dose_consistent_carrier_defect_does_not_stop(self) -> None:
        scorecard = _json("allele_function_scorecard.synthetic.json")
        _set_carrier_endpoint(scorecard, "missense_carrier", "checkpoint", "positive")
        _set_carrier_endpoint(scorecard, "stop", "checkpoint", "positive")
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "missense_stability_defect")
        self.assertTrue(result["probe_eligible"])

    def test_uninterpretable_carrier_positive_holds(self) -> None:
        scorecard = _json("allele_function_scorecard.synthetic.json")
        for row in scorecard["rows"]:
            if row["genotype_class"] != "missense_carrier":
                continue
            for item in row["assessments"]:
                if item["endpoint"] == "checkpoint":
                    item["assessment_status"] = "positive"
                    item["condition_class"] = "imposed_extrinsic_stress"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "carrier_assay_class_required")

    def test_community_replication_holds(self) -> None:
        result = assess_replication_decision(_json("replication_decision.synthetic.json"))
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "endpoints_not_concordant")

    def test_community_lineage_demonstrates_synthetic_concordance(self) -> None:
        result = assess_endpoint_concordance(_json("lineage_count_table.synthetic.json"))
        self.assertEqual(result["schema"], PROGRAM_SCHEMA)
        self.assertEqual(result["gate"], "concordance")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "concordant_generation")
        self.assertTrue(result["endpoints_concordant"])
        self.assertTrue(result["synthetic_only"])
        self.assertEqual(result["n_edit_events"], 3)
        self.assertEqual(result["minimum_edit_events"], 3)
        self.assertTrue(all(event["n_clones"] == 6 for event in result["events"]))
        self.assertEqual(result["completion_band"]["relative_lower"], 0.95)

    def test_three_events_can_pass_concordance(self) -> None:
        result = assess_endpoint_concordance(_lineage_counts())
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["endpoints_concordant"])
        self.assertEqual(result["n_edit_events"], 3)
        self.assertEqual(result["minimum_clones_per_event"], 2)
        self.assertTrue(all(event["n_clones"] == 2 for event in result["events"]))

    def test_one_clone_per_event_cannot_pass_concordance(self) -> None:
        result = assess_endpoint_concordance(_lineage_counts(n_clones=1))
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "insufficient_clones")
        self.assertFalse(result["endpoints_concordant"])

    def test_discordant_clone_cannot_be_pooled_into_a_pass(self) -> None:
        export = _lineage_counts()
        for row in export["runs"]:
            if row["edit_event_id"] == "syn-event-1" and row["clone_id"] == "syn-clone-1-2":
                if row["arm"] == "treatment":
                    row["event_positive_divisions"] = 16
                    row["event_negative_divisions"] = 20
                    row["event_positive_daughters_followed"] = 8
                    row["event_positive_daughters_reproduced"] = 4
        result = assess_endpoint_concordance(export)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "endpoints_not_concordant")
        self.assertFalse(result["endpoints_concordant"])
        self.assertTrue(result["events"][0]["pooled_would_pass"])
        clone_status = {
            item["clone_id"]: item["status"] for item in result["events"][0]["clones"]
        }
        self.assertEqual(clone_status["syn-clone-1-1"], "pass")
        self.assertEqual(clone_status["syn-clone-1-2"], "hold")

    def test_missing_event_negative_divisions_cannot_skip_conservation(
        self,
    ) -> None:
        export = _lineage_counts()
        for row in export["runs"]:
            row.pop("event_negative_divisions")
        with self.assertRaises(ProgramGateError):
            assess_endpoint_concordance(export)

    def test_missing_or_excess_daughter_fields_fail_conservation(self) -> None:
        export = _lineage_counts()
        for row in export["runs"]:
            row.pop("event_positive_daughters_died")
        with self.assertRaises(ProgramGateError):
            assess_endpoint_concordance(export)

        export = _lineage_counts()
        for row in export["runs"]:
            row["event_negative_daughters_followed"] = 10_000
        with self.assertRaises(ProgramGateError):
            assess_endpoint_concordance(export)

        export = _lineage_counts()
        for row in export["runs"]:
            row["event_positive_daughters_died"] = (
                row["event_positive_daughters_followed"] + 1
            )
        with self.assertRaises(ProgramGateError):
            assess_endpoint_concordance(export)

    def test_clone_arm_split_across_runs_fails(self) -> None:
        export = _lineage_counts()
        extra = dict(export["runs"][1])
        extra["run_id"] = "syn-run-split"
        extra["event_positive_divisions"] = 0
        extra["event_negative_divisions"] = extra["detected_divisions"]
        export["runs"].append(extra)
        with self.assertRaisesRegex(ProgramGateError, "multiple runs"):
            assess_endpoint_concordance(export)

    def test_unlocked_counts_cannot_claim_concordance(self) -> None:
        export = _lineage_counts()
        export["lock_state"] = "unlocked"
        result = assess_endpoint_concordance(export)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "counts_not_locked")
        self.assertFalse(result["endpoints_concordant"])

    def test_unblinded_counts_cannot_claim_concordance(self) -> None:
        export = _lineage_counts()
        export["blinded"] = False
        result = assess_endpoint_concordance(export)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "counts_not_blinded")
        self.assertFalse(result["endpoints_concordant"])

    def test_error_increase_is_not_concordant(self) -> None:
        result = assess_endpoint_concordance(_lineage_counts(treatment_positive=16))
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "endpoints_not_concordant")
        self.assertFalse(result["endpoints_concordant"])

    def test_completion_drop_outside_pediatric_band(self) -> None:
        result = assess_endpoint_concordance(
            _lineage_counts(
                opportunities=40,
                vehicle_divisions=30,
                treatment_divisions=28,
                vehicle_death=8,
                treatment_death=10,
            )
        )
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "pediatric_band")

    def test_large_completion_drop_via_no_division_is_competing(self) -> None:
        result = assess_endpoint_concordance(_lineage_counts(treatment_divisions=30))
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "competing_toxicity")

    def test_competing_toxicity_stops_concordance(self) -> None:
        result = assess_endpoint_concordance(_lineage_counts(treatment_death=2))
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "competing_toxicity")

    def test_no_division_increase_is_competing_cytostasis(self) -> None:
        result = assess_endpoint_concordance(_lineage_counts(treatment_divisions=35))
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "competing_toxicity")
        self.assertTrue(result["events"][0]["competing_toxicity"])

    def test_impossible_partition_fails_closed(self) -> None:
        export = _lineage_counts()
        for row in export["runs"]:
            if row["arm"] == "treatment":
                row["pre_division_death"] = 5
        with self.assertRaisesRegex(ProgramGateError, "partition"):
            assess_endpoint_concordance(export)

    def test_excess_followed_daughters_fail_closed(self) -> None:
        export = _lineage_counts()
        for row in export["runs"]:
            if row["arm"] == "treatment":
                row["event_positive_daughters_followed"] = 9
        with self.assertRaisesRegex(ProgramGateError, "declared daughter slots"):
            assess_endpoint_concordance(export)

    def test_duplicate_count_rows_fail_closed(self) -> None:
        export = _lineage_counts(n_events=1)
        export["runs"].append(dict(export["runs"][0]))
        with self.assertRaisesRegex(ProgramGateError, "duplicate"):
            assess_endpoint_concordance(export)

    def test_green_booleans_cannot_advance_without_nested_passes(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        payload["clone_safety_stop"] = False
        payload["exposure_gate_passed"] = True
        result = assess_replication_decision(payload)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "insufficient_gate_objects")

    def test_nested_passes_without_function_identity_cannot_advance(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        counts = _lineage_counts()
        clone_safety = assess_clone_safety(counts)
        exposure = assess_exposure_gate(_json("measured_exposure_table.synthetic.json"))
        concordance = assess_endpoint_concordance(counts)
        result = assess_replication_decision(
            payload,
            clone_safety=clone_safety,
            exposure=exposure,
            concordance=concordance,
        )
        self.assertEqual(clone_safety["status"], "pass")
        self.assertEqual(concordance["status"], "pass")
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "insufficient_gate_objects")

    def test_ticked_concordance_cannot_override_computed_miss(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        counts = _lineage_counts(treatment_positive=16)
        result = assess_replication_decision(
            payload,
            clone_safety=assess_clone_safety(counts),
            exposure=assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
            concordance=assess_endpoint_concordance(counts),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "computed_not_concordant")
        self.assertFalse(result["endpoints_concordant"])

    def test_computed_pass_cannot_override_declared_discordant(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        counts = _lineage_counts()
        result = assess_replication_decision(
            payload,
            clone_safety=assess_clone_safety(counts),
            exposure=assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
            concordance=assess_endpoint_concordance(counts),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "declared_discordant")

    def test_same_site_cannot_count_as_independent_replication(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        payload["originating_site_id"] = payload["site_id"]
        counts = _lineage_counts()
        result = assess_replication_decision(
            payload,
            clone_safety=assess_clone_safety(counts),
            exposure=assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
            concordance=assess_endpoint_concordance(counts),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "same_site")
        self.assertFalse(result["independent_site"])

    def test_missing_originating_site_cannot_advance(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        del payload["originating_site_id"]
        counts = _lineage_counts()
        result = assess_replication_decision(
            payload,
            clone_safety=assess_clone_safety(counts),
            exposure=assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
            concordance=assess_endpoint_concordance(counts),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "independent_site_unproven")

    def test_clone_safety_stop_beats_concordant_endpoints(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        clone_safety = assess_clone_safety(
            {
                "schema": "mva-track2-lineage-counts/v1",
                "synthetic_only": True,
                "lock_state": "locked",
                "blinded": True,
                "runs": [
                    {
                        "arm": "vehicle",
                        "edit_event_id": "syn-event-1",
                        "clone_id": "syn-clone-1",
                        "run_id": "syn-run-1",
                        "event_positive_divisions": 5,
                        "event_negative_divisions": 5,
                        "event_positive_daughters_followed": 10,
                        "event_positive_daughters_reproduced": 4,
                        "event_positive_daughters_died": 6,
                        "event_negative_daughters_followed": 10,
                        "event_negative_daughters_reproduced": 8,
                        "event_negative_daughters_died": 2,
                    },
                    {
                        "arm": "treatment",
                        "edit_event_id": "syn-event-1",
                        "clone_id": "syn-clone-1",
                        "run_id": "syn-run-1",
                        "event_positive_divisions": 5,
                        "event_negative_divisions": 5,
                        "event_positive_daughters_followed": 10,
                        "event_positive_daughters_reproduced": 8,
                        "event_positive_daughters_died": 2,
                        "event_negative_daughters_followed": 10,
                        "event_negative_daughters_reproduced": 8,
                        "event_negative_daughters_died": 2,
                    },
                ],
            }
        )
        exposure = assess_exposure_gate(_json("measured_exposure_table.synthetic.json"))
        result = assess_replication_decision(
            payload,
            clone_safety=clone_safety,
            exposure=exposure,
            concordance=assess_endpoint_concordance(_lineage_counts()),
        )
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["reason"], "clone_safety_stop")

    def test_analog_missense_cannot_count_as_exact_function(self) -> None:
        result = assess_hypomorph_gate(_scorecard(specificity="analog"))
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "analog_as_exact_function")
        self.assertFalse(result["probe_eligible"])
        self.assertFalse(result["checkpoint_ready"])

    def test_analog_recreation_cannot_restore_an_exact_missense_defect(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "recreated_missense":
                row["allele_specificity"] = "analog"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "analog_as_exact_function")
        self.assertFalse(result["probe_eligible"])

    def test_unlabeled_recreation_specificity_cannot_restore_an_exact_defect(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "recreated_missense":
                row.pop("allele_specificity", None)
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "recreation_specificity_required")
        self.assertEqual(result["recreation_allele_specificity"], "unlabeled")
        self.assertFalse(result["probe_eligible"])

    def test_invalid_recreation_specificity_is_malformed(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "recreated_missense":
                row["allele_specificity"] = "parental"
        with self.assertRaises(ProgramGateError):
            assess_hypomorph_gate(scorecard)

    def test_unmatched_recreation_still_blocks_before_unlabeled_specificity(
        self,
    ) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] != "recreated_missense":
                continue
            row.pop("allele_specificity", None)
            for item in row["assessments"]:
                if item.get("assessment_status") == "positive":
                    item["specimen_class"] = "unmatched"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["reason"], "recreation_unmatched_not_assay_matched")

    def test_analog_recreation_still_blocks_before_unlabeled_specificity(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "recreated_missense":
                row["allele_specificity"] = "analog"
        result = assess_hypomorph_gate(scorecard)
        self.assertEqual(result["reason"], "analog_as_exact_function")

    def test_uncorrected_missense_cannot_count_as_function_identity(self) -> None:
        result = assess_hypomorph_gate(_scorecard(exact_abundance="positive"))
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "correction_did_not_reverse_defect")
        self.assertIn("abundance", result["reversal_failed_endpoints"])

    def test_chaperone_pd_cannot_make_checkpoint_ready(self) -> None:
        result = assess_hypomorph_gate(_scorecard(chaperone_pd="positive"))
        self.assertTrue(result["probe_eligible"])
        self.assertTrue(result["pharmacodynamic_not_target"])
        self.assertFalse(result["checkpoint_ready"])
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "pd_not_checkpoint")

    def test_checkpoint_unknown_cannot_advance_even_with_pretty_counts(self) -> None:
        result = _nested_replication(
            hypomorph=assess_hypomorph_gate(_scorecard()),
            hypothesis=assess_hypothesis_strength(
                _json("observed_inferred_unknown.synthetic.json")
            ),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "checkpoint_not_ready")
        self.assertFalse(result["checkpoint_ready"])

    def test_child_claim_too_weak_cannot_advance(self) -> None:
        result = _nested_replication(
            hypomorph=assess_hypomorph_gate(_scorecard(checkpoint="positive")),
            hypothesis=assess_hypothesis_strength(
                _json("observed_inferred_unknown.synthetic.json")
            ),
        )
        self.assertTrue(result["checkpoint_ready"])
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "child_claim_too_weak")

    def test_analog_nested_hypomorph_stops_replication(self) -> None:
        result = _nested_replication(
            hypomorph=assess_hypomorph_gate(_scorecard(specificity="analog")),
            hypothesis=assess_hypothesis_strength(_child_claim_ready_evidence()),
        )
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["reason"], "analog_as_exact_function")

    def test_unlabeled_recreation_nested_hypomorph_stops_replication(self) -> None:
        scorecard = _scorecard()
        for row in scorecard["rows"]:
            if row["genotype_class"] == "recreated_missense":
                row.pop("allele_specificity", None)
        result = _nested_replication(
            hypomorph=assess_hypomorph_gate(scorecard),
            hypothesis=assess_hypothesis_strength(_child_claim_ready_evidence()),
        )
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["reason"], "recreation_specificity_required")

    def test_exact_allele_function_and_child_claim_can_advance(self) -> None:
        result = _nested_replication(
            hypomorph=assess_hypomorph_gate(_scorecard(checkpoint="positive")),
            hypothesis=_bound_child_claim_hypothesis(),
        )
        self.assertEqual(result["decision"], "advance")
        self.assertEqual(result["reason"], "gates_concordant")
        self.assertTrue(result["checkpoint_ready"])
        self.assertEqual(result["child_claim_strength"], "conditional_ex_vivo")

    def test_nested_effect_pass_cannot_override_failed_status(self) -> None:
        forged = dict(_pass_phase())
        forged["status"] = "not_assessable"
        forged["program_effect"] = "pass"
        forged["receipt_sha256"] = receipt_sha256(forged)
        result = _nested_replication(
            hypomorph=assess_hypomorph_gate(_scorecard(checkpoint="positive")),
            hypothesis=_bound_child_claim_hypothesis(),
            phase=forged,
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "phase_not_passed")

    def test_nested_status_pass_cannot_override_stop_effect(self) -> None:
        forged = dict(_pass_transcript())
        forged["status"] = "pass"
        forged["program_effect"] = "stop"
        forged["receipt_sha256"] = receipt_sha256(forged)
        result = _nested_replication(
            hypomorph=assess_hypomorph_gate(_scorecard(checkpoint="positive")),
            hypothesis=_bound_child_claim_hypothesis(),
            transcript=forged,
        )
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["reason"], "transcript_stop")

    def test_replication_cannot_skip_confirmation_phase_or_transcript(self) -> None:
        result = assess_replication_decision(
            {**_json("replication_decision.synthetic.json"), "endpoints_concordant": True},
            clone_safety=assess_clone_safety(_lineage_counts()),
            exposure=assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
            concordance=assess_endpoint_concordance(_lineage_counts()),
            hypomorph=assess_hypomorph_gate(_scorecard(checkpoint="positive")),
            hypothesis=_bound_child_claim_hypothesis(),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "insufficient_gate_objects")

    def test_nested_gate_strings_cannot_satisfy_boolean_requirements(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        with self.assertRaisesRegex(
            ProgramGateError, "clone_safety.clone_safety_stop"
        ):
            assess_replication_decision(
                payload,
                clone_safety={
                    "schema": "mva-track2-clone-safety/v2",
                    "status": "pass",
                    "clone_safety_stop": 0,
                    "source_fingerprint": "same",
                },
            )
        with self.assertRaisesRegex(
            ProgramGateError, "exposure.exposure_gate_passed"
        ):
            assess_replication_decision(
                payload,
                exposure={
                    "schema": "mva-track2-exposure-gate/v2",
                    "status": "pass",
                    "exposure_gate_passed": "yes",
                },
            )
        with self.assertRaisesRegex(
            ProgramGateError, "concordance.endpoints_concordant"
        ):
            assess_replication_decision(
                payload,
                concordance={
                    "schema": "mva-track2-program-gates/v1",
                    "gate": "concordance",
                    "status": "pass",
                    "endpoints_concordant": "true",
                    "source_fingerprint": "same",
                },
            )
        with self.assertRaisesRegex(
            ProgramGateError, "hypomorph.checkpoint_ready"
        ):
            assess_replication_decision(
                payload,
                hypomorph={
                    "schema": "mva-track2-program-gates/v1",
                    "gate": "hypomorph",
                    "status": "pass",
                    "probe_eligible": "no",
                    "checkpoint_ready": "False",
                    "allele_specificity": "exact",
                },
            )

    def test_nested_clone_safety_cannot_silence_declared_stop(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["clone_safety_stop"] = True
        result = assess_replication_decision(
            payload,
            clone_safety={
                "schema": "mva-track2-clone-safety/v2",
                "status": "pass",
                "clone_safety_stop": False,
                "source_fingerprint": "syn-source",
                "receipt_sha256": receipt_sha256(
                    {
                        "schema": "mva-track2-clone-safety/v2",
                        "status": "pass",
                        "clone_safety_stop": False,
                        "source_fingerprint": "syn-source",
                    }
                ),
            },
        )
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["reason"], "clone_safety_stop")

    def test_nested_exposure_cannot_override_declared_fail(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        payload["exposure_gate_passed"] = False
        counts = _lineage_counts()
        result = assess_replication_decision(
            payload,
            clone_safety=assess_clone_safety(counts),
            exposure=assess_exposure_gate(
                _json("measured_exposure_table.synthetic.json")
            ),
            concordance=assess_endpoint_concordance(counts),
            hypomorph=assess_hypomorph_gate(_scorecard(checkpoint="positive")),
            hypothesis=_bound_child_claim_hypothesis(),
            confirmation=_pass_confirmation(),
            phase=_pass_phase(),
            transcript=_pass_transcript(),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "exposure_not_passed")

    def test_community_count_tables_hold_on_competing_risk(self) -> None:
        result = assess_count_table_identity(
            _json("lineage_count_table.synthetic.json"),
            _json("blinded_count_table.synthetic.json"),
            _json("measured_exposure_table.synthetic.json"),
            _json("assay_power.synthetic.json"),
        )
        self.assertEqual(result["gate"], "count_identity")
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "competing_risk_present")
        self.assertFalse(result["tables_aligned"])
        self.assertTrue(result["competing_risk_present"])

    def test_aligned_counts_with_competing_risk_cannot_be_a_rescue_table(self) -> None:
        counts = _lineage_counts(n_clones=6)
        plan = _json("assay_power.synthetic.json")
        result = assess_count_table_identity(
            counts,
            _blinded_from_lineage(counts),
            passing_exposure(counts, plan),
            plan,
        )
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "competing_risk_present")
        self.assertTrue(result["competing_risk_present"])

    def test_aligned_counts_without_competing_risk_pass_identity(self) -> None:
        counts = _lineage_counts(
            n_clones=6,
            opportunities=36,
            treatment_death=0,
            vehicle_death=0,
        )
        plan = _json("assay_power.synthetic.json")
        result = assess_count_table_identity(
            counts,
            _blinded_from_lineage(counts),
            passing_exposure(counts, plan),
            plan,
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "count_tables_aligned")
        self.assertTrue(result["tables_aligned"])
        self.assertTrue(result["exposure_execution_linked"])
        self.assertIsInstance(result["linked_assay_fingerprint"], str)
        self.assertEqual(result["allocation_inference_status"], "pass")
        self.assertEqual(
            result["allocation_inference_reason"], "both_endpoints_pass"
        )
        self.assertEqual(
            result["allocation_inference"][
                "n_admissible_treatment_assignments"
            ],
            8000,
        )

    def test_order_only_u_shape_cannot_advance_count_identity(self) -> None:
        counts = _lineage_counts(
            n_clones=6,
            opportunities=36,
            treatment_death=0,
            vehicle_death=0,
        )
        plan = _json("assay_power.synthetic.json")
        exposure = passing_exposure(counts, plan)
        for row in counts["runs"]:
            local_order = (int(row["dosing_order"]) - 1) % 12 + 1
            errors = round((local_order - 6.5) ** 2)
            row["event_positive_divisions"] = errors
            row["event_negative_divisions"] = 36 - errors
            row["event_positive_daughters_followed"] = 0
            row["event_positive_daughters_reproduced"] = 0
            row["event_positive_daughters_died"] = 0
        result = assess_count_table_identity(
            counts,
            _blinded_from_lineage(counts),
            exposure,
            plan,
        )
        self.assertNotEqual(result["status"], "pass")
        self.assertEqual(result["allocation_inference_status"], "stop")
        self.assertIn(
            result["allocation_inference_reason"],
            {"endpoint_not_directionally_lower", "exact_pvalue_above_threshold"},
        )

    def test_malformed_competing_risk_counts_fail_closed(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        next(row for row in counts["runs"] if row["arm"] == "treatment")[
            "pre_division_death"
        ] = -1
        with self.assertRaises(ProgramGateError):
            assess_count_table_identity(counts, blinded, exposure, plan)

    def test_unmapped_row_competing_counts_still_fail_closed(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        row = counts["runs"][0]
        row["arm"] = "bogus_arm"
        row["pre_division_death"] = -1
        with self.assertRaises(ProgramGateError):
            assess_count_table_identity(counts, blinded, exposure, plan)

    def test_ambiguous_trailing_integer_identity_fails_closed(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        # Two distinct clone labels in the same event sharing the trailing
        # integer must not merge into one blinded index key.
        for row in counts["runs"]:
            if (
                row["edit_event_id"] == "syn-event-1"
                and row["clone_id"] == "syn-clone-1-2"
            ):
                row["clone_id"] = "syn-otherclone-1"
        with self.assertRaisesRegex(ProgramGateError, "ambiguous clone_id"):
            assess_count_table_identity(counts, blinded, exposure, plan)
        # A label consistently renamed across both arms of one event stays
        # legitimate — the collision scope is per-event, not global.
        counts, blinded, exposure, plan = _linked_count_inputs()
        for row in counts["runs"]:
            if (
                row["edit_event_id"] == "syn-event-1"
                and row["clone_id"] == "syn-clone-1-1"
            ):
                row["clone_id"] = "syn-renamed-1"
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertIn(result["status"], {"pass", "hold", "stop"})

    def test_missing_execution_reference_holds_count_identity(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        next(row for row in counts["runs"] if row["arm"] == "treatment").pop(
            "functional_execution_id"
        )
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_execution_missing")
        self.assertTrue(result["tables_aligned"])

    def test_missing_study_context_holds_count_identity(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        counts.pop("study_id")
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_context_missing")

    def test_missing_vehicle_execution_context_holds_count_identity(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        next(row for row in counts["runs"] if row["arm"] == "vehicle").pop(
            "functional_execution_id"
        )
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_execution_missing")

    def test_treatment_and_vehicle_cannot_share_execution_context(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        treatment = next(row for row in counts["runs"] if row["arm"] == "treatment")
        vehicle = next(
            row
            for row in counts["runs"]
            if row["arm"] == "vehicle"
            and row["edit_event_id"] == treatment["edit_event_id"]
            and row["clone_id"] == treatment["clone_id"]
            and row["run_id"] == treatment["run_id"]
        )
        vehicle["functional_execution_id"] = treatment["functional_execution_id"]
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_execution_ids_are_globally_disjoint_across_arms(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        treatment = next(row for row in counts["runs"] if row["arm"] == "treatment")
        vehicle = next(
            row
            for row in counts["runs"]
            if row["arm"] == "vehicle"
            and (
                row["edit_event_id"], row["clone_id"], row["run_id"]
            )
            != (
                treatment["edit_event_id"],
                treatment["clone_id"],
                treatment["run_id"],
            )
        )
        vehicle["functional_execution_id"] = treatment["functional_execution_id"]
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_unpaired_vehicle_cannot_hide_duplicate_functional_execution(self) -> None:
        counts, _, exposure, plan = _linked_count_inputs()
        vehicle = next(row for row in counts["runs"] if row["arm"] == "vehicle")
        unpaired = json.loads(json.dumps(vehicle, allow_nan=False))
        unpaired["edit_event_id"] = "syn-event-99"
        unpaired["clone_id"] = "syn-clone-99"
        counts["runs"].append(unpaired)
        blinded = _blinded_from_lineage(counts)
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_measurement_and_control_record_ids_are_disjoint(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        control = exposure["vehicle_controls"][0]
        control["control_execution_id"] = selected["measurement_execution_id"]
        for row in counts["runs"]:
            if row["arm"] == "vehicle":
                row["exposure_support_record_id"] = control["control_execution_id"]
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_unrelated_exposure_execution_cannot_rescue_attractive_counts(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        next(row for row in counts["runs"] if row["arm"] == "treatment")[
            "functional_execution_id"
        ] = "syn-functional-unrelated"
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")
        self.assertFalse(result["exposure_execution_linked"])

    def test_measurement_execution_must_be_anchored_by_lineage(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        selected["measurement_execution_id"] = "syn-measurement-unrelated"
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_mixed_treatment_profiles_cannot_be_pooled(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        treatment = next(row for row in counts["runs"] if row["arm"] == "treatment")
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        alternate = next(
            row
            for row in exposure["rows"]
            if row["nominal_uM"] == 0.5 and row["pulse_vs_constant"] == "constant"
        )
        functional_id = treatment["functional_execution_id"]
        selected["supports_functional_execution_ids"].remove(functional_id)
        alternate["supports_functional_execution_ids"] = [functional_id]
        for field in (
            "functional_assay_run_ids",
            "culture_batch_id",
            "sample_relation",
            "exposure_started_at",
            "measurement_sampled_at",
        ):
            alternate[field] = selected[field]
        treatment["exposure_profile_id"] = alternate["exposure_profile_id"]
        treatment["exposure_support_record_id"] = alternate[
            "measurement_execution_id"
        ]
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_duplicate_or_unused_treatment_supports_hold(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        treatment_rows = [row for row in counts["runs"] if row["arm"] == "treatment"]
        treatment_rows[1]["functional_execution_id"] = treatment_rows[0][
            "functional_execution_id"
        ]
        duplicate = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(duplicate["reason"], "exposure_assay_source_mismatch")

        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        selected["supports_functional_execution_ids"].append("syn-functional-unused")
        unused = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(unused["reason"], "exposure_not_passed")

    def test_declared_assay_run_sets_must_be_consumed_exactly(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        selected["functional_assay_run_ids"].append("syn-run-unused")
        treatment_extra = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(
            treatment_extra["reason"], "exposure_assay_source_mismatch"
        )

        counts, blinded, exposure, plan = _linked_count_inputs()
        exposure["vehicle_controls"][0]["functional_assay_run_ids"].append(
            "syn-run-unused"
        )
        control_extra = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(control_extra["reason"], "exposure_assay_source_mismatch")

        counts, blinded, exposure, plan = _linked_count_inputs()
        unlinked = next(
            row for row in exposure["rows"] if not row["supports_functional_execution_ids"]
        )
        unlinked["functional_assay_run_ids"] = ["syn-run-unused"]
        with self.assertRaisesRegex(ProgramGateError, "binding is malformed"):
            assess_count_table_identity(counts, blinded, exposure, plan)

        counts, blinded, exposure, plan = _linked_count_inputs()
        hidden = next(
            row
            for row in exposure["rows"]
            if not row["supports_functional_execution_ids"]
        )
        hidden.pop("exposure_profile_id")
        hidden["supports_functional_execution_ids"] = ["syn-functional-unused"]
        hidden["functional_assay_run_ids"] = ["syn-run-unused"]
        hidden["culture_batch_id"] = "syn-batch-hidden"
        hidden["sample_relation"] = "matched_parallel_culture"
        hidden["exposure_started_at"] = "2026-08-29T00:00:00Z"
        hidden["measurement_sampled_at"] = "2026-08-29T01:00:00Z"
        with self.assertRaisesRegex(ProgramGateError, "binding is malformed"):
            assess_count_table_identity(counts, blinded, exposure, plan)

    def test_vehicle_control_record_and_endpoint_are_required(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        vehicle = next(row for row in counts["runs"] if row["arm"] == "vehicle")
        vehicle.pop("endpoint_recorded_at")
        missing_time = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(missing_time["reason"], "exposure_execution_missing")

        counts, blinded, exposure, plan = _linked_count_inputs()
        vehicle = next(row for row in counts["runs"] if row["arm"] == "vehicle")
        vehicle["exposure_profile_id"] = "profile-arbitrary-control"
        vehicle["exposure_probe_id"] = "syn-arbitrary-control"
        mismatched = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(mismatched["reason"], "exposure_assay_source_mismatch")

    def test_batch_mismatch_holds_the_whole_treatment_aggregate(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        next(row for row in counts["runs"] if row["arm"] == "treatment")[
            "batch_id"
        ] = "syn-batch-unrelated"
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["reason"], "exposure_assay_source_mismatch")

    def test_stale_profile_digest_holds(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        selected["unbound_medium_uM"] = 0.70
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["reason"], "exposure_profile_mismatch")

    def test_pulse_profile_cannot_supply_a_functional_execution(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        pulse = next(
            row for row in exposure["rows"] if row["pulse_vs_constant"] == "pulse"
        )
        for field in (
            "supports_functional_execution_ids",
            "functional_assay_run_ids",
            "culture_batch_id",
            "sample_relation",
            "exposure_started_at",
            "exposure_measurement_plate_id",
            "probe_lot_id",
        ):
            pulse[field] = selected[field]
        pulse["measurement_sampled_at"] = "2026-08-29T05:00:00Z"
        selected["supports_functional_execution_ids"] = []
        selected["functional_assay_run_ids"] = []
        selected["sample_relation"] = None
        for row in counts["runs"]:
            if row["arm"] == "treatment":
                row["exposure_profile_id"] = pulse["exposure_profile_id"]
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["reason"], "linked_exposure_not_qualified")

    def test_timing_mismatch_holds(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        selected["measurement_sampled_at"] = "2026-08-30T00:00:00Z"
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["reason"], "exposure_timing_mismatch")

    def test_zero_duration_vehicle_control_endpoint_holds(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        vehicle = next(row for row in counts["runs"] if row["arm"] == "vehicle")
        vehicle["endpoint_recorded_at"] = vehicle["exposure_started_at"]
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertTrue(str(result["reason"]).startswith("exposure_"))

    def test_optional_plate_and_lot_do_not_block_and_order_is_canonical(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        selected = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        selected.pop("exposure_measurement_plate_id", None)
        selected.pop("probe_lot_id", None)
        first = assess_count_table_identity(counts, blinded, exposure, plan)
        counts["runs"].reverse()
        blinded["runs"].reverse()
        exposure["rows"].reverse()
        second = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(first["status"], "pass")
        self.assertEqual(second["status"], "pass")
        self.assertEqual(
            first["linked_assay_fingerprint"],
            second["linked_assay_fingerprint"],
        )

    def test_repeated_profile_across_distinct_batches_can_pass(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        moved_event_id = "syn-event-1"
        treatments = [
            row
            for row in counts["runs"]
            if row["arm"] == "treatment"
            and row["edit_event_id"] == moved_event_id
        ]
        vehicles = [
            row
            for row in counts["runs"]
            if row["arm"] == "vehicle"
            and row["edit_event_id"] == moved_event_id
        ]
        moved_treatment_ids = {
            row["functional_execution_id"] for row in treatments
        }
        moved_vehicle_ids = {
            row["functional_execution_id"] for row in vehicles
        }
        moved_run_ids = sorted({row["run_id"] for row in treatments})
        original = next(
            row for row in exposure["rows"] if row["supports_functional_execution_ids"]
        )
        repeated = json.loads(json.dumps(original, allow_nan=False))
        repeated["measurement_execution_id"] = "syn-measurement-batch-b"
        repeated["supports_functional_execution_ids"] = sorted(
            moved_treatment_ids
        )
        repeated["functional_assay_run_ids"] = moved_run_ids
        repeated["culture_batch_id"] = "syn-batch-b"
        original["supports_functional_execution_ids"] = sorted(
            set(original["supports_functional_execution_ids"])
            - moved_treatment_ids
        )
        original["functional_assay_run_ids"] = sorted(
            set(original["functional_assay_run_ids"]) - set(moved_run_ids)
        )
        for treatment in treatments:
            treatment["batch_id"] = "syn-batch-b"
            treatment["exposure_support_record_id"] = repeated[
                "measurement_execution_id"
            ]
        original_control = exposure["vehicle_controls"][0]
        repeated_control = json.loads(json.dumps(original_control, allow_nan=False))
        repeated_control["control_execution_id"] = "syn-vehicle-control-record-b"
        repeated_control["supports_functional_execution_ids"] = sorted(
            moved_vehicle_ids
        )
        repeated_control["functional_assay_run_ids"] = moved_run_ids
        repeated_control["culture_batch_id"] = "syn-batch-b"
        original_control["supports_functional_execution_ids"] = sorted(
            set(original_control["supports_functional_execution_ids"])
            - moved_vehicle_ids
        )
        original_control["functional_assay_run_ids"] = sorted(
            set(original_control["functional_assay_run_ids"])
            - set(moved_run_ids)
        )
        for vehicle in vehicles:
            vehicle["batch_id"] = "syn-batch-b"
            vehicle["exposure_support_record_id"] = repeated_control[
                "control_execution_id"
            ]
        exposure["rows"].append(repeated)
        exposure["vehicle_controls"].append(repeated_control)
        allocation = exposure["preexposure_allocation"]
        for assignment in allocation["assignments"]:
            if assignment["functional_execution_id"] in (
                moved_treatment_ids | moved_vehicle_ids
            ):
                assignment["culture_batch_id"] = "syn-batch-b"
        for pair in allocation["assignment_manifest"]["pair_units"]:
            for member in pair["members"]:
                if member["functional_execution_id"] in (
                    moved_treatment_ids | moved_vehicle_ids
                ):
                    member["culture_batch_id"] = "syn-batch-b"
        allocation["analysis_plan_sha256"] = (
            make_allocation_analysis_plan_sha256()
        )
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
        allocation["assignment_input_commitment_record"]["digest_sha256"] = (
            allocation["assignment_input_commitment_sha256"]
        )
        _relabel_unattested_synthetic_fixture_to_seed(
            exposure=exposure,
            lineage=counts,
        )
        blinded = _blinded_from_lineage(counts)
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "pass")

    def test_all_shared_daughter_counts_participate_in_identity(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        blinded["runs"][0]["event_negative_daughters_followed"] = 1
        blinded["runs"][0]["event_negative_daughters_reproduced"] = 1
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "count_tables_inconsistent")

    def test_declared_daughter_slots_participate_in_identity(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        counts["runs"][0]["event_positive_multipolar_divisions"] = 1
        counts["runs"][0]["event_positive_daughter_slots"] = (
            2 * counts["runs"][0]["event_positive_divisions"] + 1
        )
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "count_tables_inconsistent")
        counts, blinded, exposure, plan = _linked_count_inputs()
        blinded["runs"][0]["event_positive_multipolar_divisions"] = 1
        blinded["runs"][0]["event_positive_daughter_slots"] = (
            2 * blinded["runs"][0]["event_positive_divisions"] + 1
        )
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "hold")
        self.assertEqual(result["reason"], "count_tables_inconsistent")

    def test_matching_daughter_slots_still_align(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        counts["runs"][0]["event_positive_multipolar_divisions"] = 1
        counts["runs"][0]["event_positive_daughter_slots"] = (
            2 * counts["runs"][0]["event_positive_divisions"] + 1
        )
        blinded["runs"][0]["event_positive_multipolar_divisions"] = 1
        blinded["runs"][0]["event_positive_daughter_slots"] = (
            2 * blinded["runs"][0]["event_positive_divisions"] + 1
        )
        result = assess_count_table_identity(counts, blinded, exposure, plan)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["tables_aligned"])

    def test_daughter_slots_outside_multipolar_bounds_fail_closed(self) -> None:
        counts, blinded, exposure, plan = _linked_count_inputs()
        row = counts["runs"][0]
        row["event_positive_daughter_slots"] = (
            4 * row["event_positive_divisions"] + 1
        )
        with self.assertRaisesRegex(ProgramGateError, "multipolar bound"):
            assess_count_table_identity(counts, blinded, exposure, plan)
        counts, blinded, exposure, plan = _linked_count_inputs()
        row = counts["runs"][0]
        row["event_positive_daughter_slots"] = (
            2 * row["event_positive_divisions"] - 1
        )
        with self.assertRaisesRegex(ProgramGateError, "fewer than two"):
            assess_count_table_identity(counts, blinded, exposure, plan)
        counts, blinded, exposure, plan = _linked_count_inputs()
        row = counts["runs"][0]
        row["event_negative_daughter_slots"] = (
            2 * row["event_negative_divisions"] + 1
        )
        with self.assertRaisesRegex(ProgramGateError, "clean divisions"):
            assess_count_table_identity(counts, blinded, exposure, plan)

    def test_zero_valued_shared_counts_cannot_be_omitted(self) -> None:
        for field in (
            "event_positive_daughters_died",
            "event_negative_daughters_followed",
            "event_negative_daughters_reproduced",
            "event_negative_daughters_died",
        ):
            with self.subTest(field=field):
                counts, blinded, exposure, plan = _linked_count_inputs()
                counts["runs"][0].pop(field)
                result = assess_count_table_identity(
                    counts, blinded, exposure, plan
                )
                self.assertEqual(result["status"], "hold")
                self.assertEqual(result["reason"], "count_tables_inconsistent")

    def test_blinded_shared_counts_cannot_be_coerced_to_integers(self) -> None:
        for bad_value in ("0", 0.5, False):
            with self.subTest(bad_value=bad_value):
                counts, blinded, exposure, plan = _linked_count_inputs()
                blinded["runs"][0]["event_negative_daughters_died"] = bad_value
                with self.assertRaisesRegex(
                    ProgramGateError, "non-negative integers"
                ):
                    assess_count_table_identity(counts, blinded, exposure, plan)

    def test_blinded_identity_keys_cannot_be_coerced_to_integers(self) -> None:
        for field, bad_value in (
            ("edit_event_id", 1.5),
            ("clone_id", "1"),
            ("run_id", True),
        ):
            with self.subTest(field=field, bad_value=bad_value):
                counts, blinded, exposure, plan = _linked_count_inputs()
                blinded["runs"][0][field] = bad_value
                with self.assertRaisesRegex(
                    ProgramGateError, "identity keys must be positive integers"
                ):
                    assess_count_table_identity(counts, blinded, exposure, plan)

    def test_clone_safety_from_a_different_lineage_cannot_advance(self) -> None:
        payload = _json("replication_decision.synthetic.json")
        payload["endpoints_concordant"] = True
        counts = _lineage_counts()
        result = assess_replication_decision(
            payload,
            clone_safety=assess_clone_safety(
                {
                    "schema": "mva-track2-lineage-counts/v1",
                    "synthetic_only": True,
                    "lock_state": "locked",
                    "blinded": True,
                    "runs": [
                        {
                            "arm": "vehicle",
                            "edit_event_id": "syn-event-1",
                            "clone_id": "syn-clone-1",
                            "run_id": "syn-run-1",
                            "event_positive_divisions": 5,
                            "event_negative_divisions": 5,
                            "event_positive_daughters_followed": 10,
                            "event_positive_daughters_reproduced": 4,
                            "event_positive_daughters_died": 6,
                            "event_negative_daughters_followed": 10,
                            "event_negative_daughters_reproduced": 8,
                            "event_negative_daughters_died": 2,
                        },
                        {
                            "arm": "treatment",
                            "edit_event_id": "syn-event-1",
                            "clone_id": "syn-clone-1",
                            "run_id": "syn-run-1",
                            "event_positive_divisions": 5,
                            "event_negative_divisions": 5,
                            "event_positive_daughters_followed": 10,
                            "event_positive_daughters_reproduced": 4,
                            "event_positive_daughters_died": 6,
                            "event_negative_daughters_followed": 10,
                            "event_negative_daughters_reproduced": 8,
                            "event_negative_daughters_died": 2,
                        },
                    ],
                }
            ),
            exposure=assess_exposure_gate(_json("measured_exposure_table.synthetic.json")),
            concordance=assess_endpoint_concordance(counts),
            hypomorph=assess_hypomorph_gate(_scorecard(checkpoint="positive")),
            hypothesis=_bound_child_claim_hypothesis(),
        )
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["reason"], "clone_safety_source_mismatch")

    def test_wrong_schema_fails_closed(self) -> None:
        with self.assertRaisesRegex(ProgramGateError, "phase gate"):
            assess_phase_gate({"schema": "mva-track2-clone-safety/v1"})


if __name__ == "__main__":
    unittest.main()
