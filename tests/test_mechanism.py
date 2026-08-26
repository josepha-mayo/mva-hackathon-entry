from __future__ import annotations

import dataclasses
import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.inheritance import (
    AlleleRecord,
    InheritanceCandidate,
    InheritanceModel,
    LocusClass,
    PhaseState,
    ReasonCode,
    generate_inheritance_candidates,
)
from mva_hackathon.mechanism import (
    AlleleTranscriptEffects,
    ConditionRelevance,
    DiseaseConditionEvidence,
    DiseaseMechanismRule,
    EvidenceConfidence,
    GenotypeDepthEvidence,
    MechanismFit,
    MechanismInputError,
    RuleMechanism,
    ScoredAssessment,
    TranscriptEffect,
    VariantGeneEvidence,
    assess_mechanism_pair,
    parse_evidence_confidence,
    rank_assessments,
)


GENE = "SYNPAIR"


def allele(
    pos: int,
    *,
    chrom: str = "chr1",
    gene: str = GENE,
    ref: str = "A",
    alt: str = "C",
    haplotype: str = "1",
) -> AlleleRecord:
    return AlleleRecord(
        gene=gene,
        chrom=chrom,
        pos=pos,
        ref=ref,
        alt=alt,
        zygosity="heterozygous",
        phase_set="SYNPHASE",
        haplotype=haplotype,
    )


def generated_pair() -> InheritanceCandidate:
    first = allele(101, haplotype="1")
    second = allele(202, ref="G", alt="T", haplotype="2")
    compounds = [
        row
        for row in generate_inheritance_candidates((first, second))
        if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS
    ]
    assert len(compounds) == 1
    return compounds[0]


def effects(
    variant_key: tuple[str, int, str, str],
    *rows: tuple[str, frozenset[str]],
) -> AlleleTranscriptEffects:
    return AlleleTranscriptEffects(
        variant_key=variant_key,
        effects=tuple(TranscriptEffect(transcript, terms) for transcript, terms in rows),
    )


def lof_rule(gene: str = GENE) -> DiseaseMechanismRule:
    return DiseaseMechanismRule(
        "SYN-RULE-1",
        gene,
        RuleMechanism.LOSS_OF_FUNCTION,
        EvidenceConfidence.MODERATE,
    )


def strict_effect_rows(
    candidate: InheritanceCandidate,
) -> tuple[AlleleTranscriptEffects, AlleleTranscriptEffects]:
    first, second = candidate.alleles
    return (
        effects(first.variant_key, ("SYN-SHARED", frozenset({"stop_gained"}))),
        effects(second.variant_key, ("SYN-SHARED", frozenset({"splice_donor"}))),
    )


class MechanismCoreTests(unittest.TestCase):
    def test_cross_contig_same_symbol_pair_fails_closed(self) -> None:
        first = allele(101, chrom="chr1", haplotype="1")
        second = allele(202, chrom="chr2", ref="G", alt="T", haplotype="2")
        candidate = InheritanceCandidate(
            gene=GENE,
            model=InheritanceModel.COMPOUND_HETEROZYGOUS,
            alleles=(first, second),
            locus_class=LocusClass.AUTOSOMAL,
            phase_state=PhaseState.UNRESOLVED,
            reason_codes=(
                ReasonCode.AUTOSOMAL_LOCUS,
                ReasonCode.SAME_GENE,
                ReasonCode.TWO_HETEROZYGOUS_ALLELES,
                ReasonCode.PHASE_UNRESOLVED,
            ),
        )
        rows = (
            effects(first.variant_key, ("SYN-TX", frozenset({"stop_gained"}))),
            effects(second.variant_key, ("SYN-TX", frozenset({"stop_gained"}))),
        )

        result = assess_mechanism_pair(candidate, rows, lof_rule())

        self.assertIs(result.fit, MechanismFit.LOCUS_MISMATCH)
        self.assertFalse(result.eligible_for_strict_pair_lane)

    def test_off_shared_transcript_lof_cannot_upgrade_pair(self) -> None:
        candidate = generated_pair()
        first, second = candidate.alleles
        rows = (
            effects(
                first.variant_key,
                ("SYN-SHARED", frozenset({"missense"})),
                ("SYN-OTHER", frozenset({"frameshift"})),
            ),
            effects(second.variant_key, ("SYN-SHARED", frozenset({"missense"}))),
        )

        result = assess_mechanism_pair(candidate, rows, lof_rule())

        self.assertIs(
            result.fit,
            MechanismFit.TWO_PROTEIN_ALTERING_NONLOF_HYPOTHESIS,
        )
        self.assertEqual(result.supporting_transcripts, ("SYN-SHARED",))
        self.assertFalse(result.eligible_for_strict_pair_lane)

    def test_two_lof_effects_on_one_shared_transcript_pass(self) -> None:
        candidate = generated_pair()

        result = assess_mechanism_pair(candidate, strict_effect_rows(candidate), lof_rule())

        self.assertIs(result.fit, MechanismFit.STRICT_TWO_ALLELE_LOF_MATCH)
        self.assertTrue(result.eligible_for_strict_pair_lane)

    def test_disjoint_transcripts_are_an_explicit_reject(self) -> None:
        candidate = generated_pair()
        first, second = candidate.alleles
        rows = (
            effects(first.variant_key, ("SYN-TX-A", frozenset({"stop_gained"}))),
            effects(second.variant_key, ("SYN-TX-B", frozenset({"splice_donor"}))),
        )

        result = assess_mechanism_pair(candidate, rows, lof_rule())

        self.assertIs(result.fit, MechanismFit.NO_SHARED_TRANSCRIPT)
        self.assertFalse(result.eligible_for_strict_pair_lane)

    def test_unresolved_phase_never_enters_strict_pair_lane(self) -> None:
        first = AlleleRecord(GENE, "chr1", 101, "A", "C", "heterozygous")
        second = AlleleRecord(GENE, "chr1", 202, "G", "T", "heterozygous")
        candidate = next(
            row
            for row in generate_inheritance_candidates((first, second))
            if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS
        )

        result = assess_mechanism_pair(candidate, strict_effect_rows(candidate), lof_rule())

        self.assertIs(result.fit, MechanismFit.STRICT_TWO_ALLELE_LOF_MATCH)
        self.assertIs(result.phase_state, PhaseState.UNRESOLVED)
        self.assertFalse(result.eligible_for_strict_pair_lane)

    def test_variant_evidence_must_match_gene_and_allele(self) -> None:
        candidate = generated_pair()
        first, second = candidate.alleles
        wrong_gene = VariantGeneEvidence(
            "SYN-EVIDENCE-WRONG",
            first.variant_key,
            "SYNOTHER",
            strict_pathogenic=True,
            review_stars=3,
        )
        correct_gene = VariantGeneEvidence(
            "SYN-EVIDENCE-RIGHT",
            second.variant_key,
            GENE,
            strict_pathogenic=True,
            review_stars=3,
        )

        result = assess_mechanism_pair(
            candidate,
            strict_effect_rows(candidate),
            lof_rule(),
            (wrong_gene, correct_gene),
        )

        self.assertEqual(result.strict_pathogenic_anchor_count, 1)

    def test_disease_condition_relevance_is_separate_from_variant_gene_match(self) -> None:
        candidate = generated_pair()
        anchor = VariantGeneEvidence(
            "SYN-EVIDENCE-ANCHOR",
            candidate.variant_keys[0],
            GENE,
            strict_pathogenic=True,
            review_stars=3,
        )

        unassessed = assess_mechanism_pair(
            candidate,
            strict_effect_rows(candidate),
            lof_rule(),
            (anchor,),
        )
        matched = assess_mechanism_pair(
            candidate,
            strict_effect_rows(candidate),
            lof_rule(),
            (anchor,),
            (
                DiseaseConditionEvidence(
                    "SYN-CONDITION-MATCH",
                    "SYN-RULE-1",
                    ConditionRelevance.MATCHED,
                ),
            ),
        )

        self.assertEqual(unassessed.strict_pathogenic_anchor_count, 1)
        self.assertIs(unassessed.condition_relevance, ConditionRelevance.NOT_ASSESSED)
        self.assertEqual(matched.strict_pathogenic_anchor_count, 1)
        self.assertIs(matched.condition_relevance, ConditionRelevance.MATCHED)

    def test_conflicting_condition_observations_remain_explicit(self) -> None:
        candidate = generated_pair()
        condition_rows = (
            DiseaseConditionEvidence(
                "SYN-CONDITION-A",
                "SYN-RULE-1",
                ConditionRelevance.MATCHED,
            ),
            DiseaseConditionEvidence(
                "SYN-CONDITION-B",
                "SYN-RULE-1",
                ConditionRelevance.MISMATCHED,
            ),
        )

        result = assess_mechanism_pair(
            candidate,
            strict_effect_rows(candidate),
            lof_rule(),
            condition_evidence=condition_rows,
        )

        self.assertIs(result.condition_relevance, ConditionRelevance.CONFLICTING)

    def test_multiallelic_gt_requires_explicit_allele_depth_semantics(self) -> None:
        with self.assertRaisesRegex(MechanismInputError, "multiallelic GT requires"):
            GenotypeDepthEvidence("1/2", (2, 8, 10))

        explicit = GenotypeDepthEvidence(
            "1/2",
            (2, 8, 10),
            target_alt_index=2,
            ad_allele_indices=(0, 1, 2),
        )
        self.assertEqual(explicit.target_depth, 10)
        self.assertEqual(explicit.target_fraction_of_all_depth, 0.5)

    def test_unknown_evidence_confidence_is_rejected_not_scored_as_zero(self) -> None:
        self.assertIs(
            parse_evidence_confidence("moderate"),
            EvidenceConfidence.MODERATE,
        )
        with self.assertRaisesRegex(MechanismInputError, "confidence must be one of"):
            parse_evidence_confidence("SYN-UNKNOWN")
        with self.assertRaisesRegex(MechanismInputError, "confidence must be one of"):
            DiseaseMechanismRule(
                "SYN-RULE-2",
                GENE,
                RuleMechanism.LOSS_OF_FUNCTION,
                "SYN-UNKNOWN",
            )

    def test_ties_are_stable_and_share_rank_interval(self) -> None:
        candidate = generated_pair()
        assessment = assess_mechanism_pair(
            candidate,
            strict_effect_rows(candidate),
            lof_rule(),
        )
        tied = (
            ScoredAssessment("SYN-ASSESS-B", (3, 1, 4), assessment),
            ScoredAssessment("SYN-ASSESS-A", (3, 1, 4), assessment),
        )
        expected = rank_assessments(tied)

        for permutation in itertools.permutations(tied):
            self.assertEqual(rank_assessments(permutation), expected)
        self.assertEqual(
            [row.assessment_id for row in expected],
            ["SYN-ASSESS-A", "SYN-ASSESS-B"],
        )
        self.assertTrue(all(row.rank_interval == (1, 2) for row in expected))
        self.assertTrue(all(row.midrank == 1.5 for row in expected))

    def test_unknown_consequence_and_duplicate_identifiers_fail_closed(self) -> None:
        with self.assertRaisesRegex(MechanismInputError, "unsupported protein consequence"):
            TranscriptEffect("SYN-TX", frozenset({"unknown_effect"}))

        candidate = generated_pair()
        assessment = assess_mechanism_pair(
            candidate,
            strict_effect_rows(candidate),
            lof_rule(),
        )
        duplicate = ScoredAssessment("SYN-DUPLICATE", (1,), assessment)
        with self.assertRaisesRegex(MechanismInputError, "must be unique"):
            rank_assessments((duplicate, duplicate))

    def test_core_records_have_no_person_or_phenotype_fields(self) -> None:
        forbidden = {
            "proband_id",
            "sample_id",
            "patient_id",
            "hpo",
            "phenotype",
            "diagnosis",
        }
        record_types = (
            AlleleTranscriptEffects,
            DiseaseConditionEvidence,
            DiseaseMechanismRule,
            GenotypeDepthEvidence,
            VariantGeneEvidence,
        )
        for record_type in record_types:
            field_names = {field.name for field in dataclasses.fields(record_type)}
            self.assertTrue(forbidden.isdisjoint(field_names))


if __name__ == "__main__":
    unittest.main()
