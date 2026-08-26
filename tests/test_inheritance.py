from __future__ import annotations

import dataclasses
import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.inheritance import (
    AlleleRecord,
    InheritanceInputError,
    InheritanceModel,
    LocusClass,
    PhaseState,
    ReasonCode,
    Zygosity,
    classify_locus,
    generate_inheritance_candidates,
    pair_phase_state,
)


def allele(
    pos: int,
    *,
    gene: str = "SYN1",
    chrom: str = "chr7",
    ref: str = "A",
    alt: str = "G",
    zygosity: Zygosity | str = Zygosity.HETEROZYGOUS,
    phase_set: str | None = None,
    haplotype: str | None = None,
) -> AlleleRecord:
    return AlleleRecord(
        gene=gene,
        chrom=chrom,
        pos=pos,
        ref=ref,
        alt=alt,
        zygosity=zygosity,
        phase_set=phase_set,
        haplotype=haplotype,
    )


class InheritanceCandidateTests(unittest.TestCase):
    def test_trans_compound_pair_is_same_gene_sorted_and_reasoned(self) -> None:
        later = allele(200, phase_set="block-1", haplotype="2")
        earlier = allele(100, phase_set="block-1", haplotype="1", ref="C", alt="T")

        candidates = generate_inheritance_candidates([later, earlier])
        compound = [row for row in candidates if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS]

        self.assertEqual(len(compound), 1)
        self.assertEqual(compound[0].variant_keys, (earlier.variant_key, later.variant_key))
        self.assertIs(compound[0].phase_state, PhaseState.TRANS_CONFIRMED)
        self.assertEqual(
            compound[0].reason_codes,
            (
                ReasonCode.AUTOSOMAL_LOCUS,
                ReasonCode.SAME_GENE,
                ReasonCode.TWO_HETEROZYGOUS_ALLELES,
                ReasonCode.PHASE_TRANS_CONFIRMED,
            ),
        )

    def test_confirmed_cis_pair_is_excluded_but_single_candidates_remain(self) -> None:
        first = allele(100, phase_set="p", haplotype="1")
        second = allele(200, phase_set="p", haplotype="1", ref="C", alt="T")

        self.assertIs(pair_phase_state(first, second), PhaseState.CIS_CONFIRMED)
        candidates = generate_inheritance_candidates([first, second])

        self.assertFalse(any(row.model is InheritanceModel.COMPOUND_HETEROZYGOUS for row in candidates))
        self.assertEqual([row.model for row in candidates], [InheritanceModel.DOMINANT] * 2)

    def test_missing_or_incomparable_phase_evidence_is_unresolved(self) -> None:
        unphased = allele(100)
        block_a = allele(200, phase_set="a", haplotype="1", ref="C", alt="T")
        block_b = allele(300, phase_set="b", haplotype="2", ref="G", alt="A")

        self.assertIs(pair_phase_state(unphased, block_a), PhaseState.UNRESOLVED)
        self.assertIs(pair_phase_state(block_a, block_b), PhaseState.UNRESOLVED)
        compounds = [
            row
            for row in generate_inheritance_candidates([unphased, block_a, block_b])
            if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS
        ]
        self.assertEqual(len(compounds), 3)
        self.assertTrue(all(row.phase_state is PhaseState.UNRESOLVED for row in compounds))
        self.assertTrue(all(ReasonCode.PHASE_UNRESOLVED in row.reason_codes for row in compounds))

    def test_pairing_never_crosses_gene_or_chromosome_partition(self) -> None:
        records = [
            allele(100, gene="SYN1", chrom="chr1"),
            allele(200, gene="SYN2", chrom="chr1"),
            allele(300, gene="SYN1", chrom="chr2"),
        ]
        compounds = [
            row
            for row in generate_inheritance_candidates(records)
            if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS
        ]
        self.assertEqual(compounds, [])

    def test_three_heterozygous_alleles_generate_each_non_cis_pair_once(self) -> None:
        one = allele(100, phase_set="p", haplotype="1")
        two = allele(200, phase_set="p", haplotype="1", ref="C", alt="T")
        three = allele(300, phase_set="p", haplotype="2", ref="G", alt="A")

        compounds = [
            row
            for row in generate_inheritance_candidates([three, one, two])
            if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS
        ]
        self.assertEqual(
            [row.variant_keys for row in compounds],
            [(one.variant_key, three.variant_key), (two.variant_key, three.variant_key)],
        )
        self.assertTrue(all(row.phase_state is PhaseState.TRANS_CONFIRMED for row in compounds))

    def test_homozygous_recessive_and_heterozygous_dominant_are_distinct(self) -> None:
        het = allele(100)
        hom = allele(200, ref="C", alt="T", zygosity="homozygous")

        candidates = generate_inheritance_candidates([hom, het])
        singles = {row.variant_keys[0]: row for row in candidates}

        self.assertIs(singles[het.variant_key].model, InheritanceModel.DOMINANT)
        self.assertIs(singles[hom.variant_key].model, InheritanceModel.HOMOZYGOUS_RECESSIVE)
        self.assertIn(ReasonCode.HETEROZYGOUS_ALLELE, singles[het.variant_key].reason_codes)
        self.assertIn(ReasonCode.HOMOZYGOUS_ALLELE, singles[hom.variant_key].reason_codes)

    def test_chr_x_par_is_diploid_and_nonpar_is_x_linked(self) -> None:
        par_first = allele(10_001, chrom="X")
        par_last = allele(156_030_895, chrom="chrX", ref="C", alt="T")
        before_par = allele(10_000, chrom="chrX", ref="G", alt="A")
        after_par = allele(156_030_896, chrom="chrX", ref="T", alt="C")

        self.assertIs(classify_locus(par_first), LocusClass.PSEUDOAUTOSOMAL)
        self.assertIs(classify_locus(par_last), LocusClass.PSEUDOAUTOSOMAL)
        self.assertIs(classify_locus(before_par), LocusClass.X_NONPAR)
        self.assertIs(classify_locus(after_par), LocusClass.X_NONPAR)

        candidates = generate_inheritance_candidates([par_first, par_last, before_par, after_par])
        by_key = {row.variant_keys[0]: row for row in candidates if len(row.alleles) == 1}
        self.assertIs(by_key[par_first.variant_key].model, InheritanceModel.DOMINANT)
        self.assertIs(by_key[par_first.variant_key].locus_class, LocusClass.PSEUDOAUTOSOMAL)
        self.assertIs(by_key[before_par.variant_key].model, InheritanceModel.X_LINKED)
        self.assertIs(by_key[after_par.variant_key].model, InheritanceModel.X_LINKED)

    def test_y_par_is_pseudoautosomal_and_nonpar_is_not_mislabelled_x_linked(self) -> None:
        par = allele(56_887_903, chrom="chrY")
        nonpar = allele(20_000_000, chrom="chrY", ref="C", alt="T")

        self.assertIs(classify_locus(par), LocusClass.PSEUDOAUTOSOMAL)
        self.assertIs(classify_locus(nonpar), LocusClass.Y_NONPAR)
        candidates = generate_inheritance_candidates([par, nonpar])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].variant_keys, (par.variant_key,))
        self.assertIs(candidates[0].model, InheritanceModel.DOMINANT)

    def test_reference_allele_spanning_par_boundary_is_rejected(self) -> None:
        crossing = allele(9_999, chrom="chrX", ref="AAAA", alt="A")
        with self.assertRaisesRegex(InheritanceInputError, "spans the GRCh38 PAR1 boundary"):
            classify_locus(crossing)

    def test_x_nonpar_heterozygous_pairs_keep_explicit_phase(self) -> None:
        first = allele(5_000_000, chrom="chrX", phase_set="x", haplotype="maternal")
        second = allele(
            5_000_100,
            chrom="chrX",
            ref="C",
            alt="T",
            phase_set="x",
            haplotype="paternal",
        )
        compounds = [
            row
            for row in generate_inheritance_candidates([first, second])
            if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS
        ]
        self.assertEqual(len(compounds), 1)
        self.assertIs(compounds[0].locus_class, LocusClass.X_NONPAR)
        self.assertIs(compounds[0].phase_state, PhaseState.TRANS_CONFIRMED)
        self.assertIn(ReasonCode.X_NONPAR_LOCUS, compounds[0].reason_codes)

    def test_mitochondrial_states_generate_mitochondrial_candidates(self) -> None:
        heteroplasmic = allele(100, gene="SYNMT-HET", chrom="MT", zygosity="heteroplasmic")
        homoplasmic = allele(
            200,
            gene="SYNMT-HOM",
            chrom="chrM",
            ref="C",
            alt="T",
            zygosity=Zygosity.HOMOPLASMIC,
        )

        candidates = generate_inheritance_candidates([homoplasmic, heteroplasmic])

        self.assertEqual([row.model for row in candidates], [InheritanceModel.MITOCHONDRIAL] * 2)
        self.assertIn(ReasonCode.HETEROPLASMIC_ALLELE, candidates[0].reason_codes)
        self.assertIn(ReasonCode.HOMOPLASMIC_ALLELE, candidates[1].reason_codes)

    def test_output_is_identical_for_every_input_permutation(self) -> None:
        records = [
            allele(300, gene="SYN2"),
            allele(200, gene="SYN1", ref="C", alt="T"),
            allele(100, gene="SYN1"),
        ]
        expected = generate_inheritance_candidates(records)
        for permutation in itertools.permutations(records):
            self.assertEqual(generate_inheritance_candidates(permutation), expected)

    def test_identical_duplicate_is_deduplicated_and_richer_phase_is_merged(self) -> None:
        plain = allele(100)
        phased = allele(100, phase_set="p", haplotype="1")
        mate = allele(200, ref="C", alt="T", phase_set="p", haplotype="2")

        candidates = generate_inheritance_candidates([plain, phased, mate, plain])
        compounds = [row for row in candidates if row.model is InheritanceModel.COMPOUND_HETEROZYGOUS]

        self.assertEqual(len(compounds), 1)
        self.assertIs(compounds[0].phase_state, PhaseState.TRANS_CONFIRMED)
        self.assertEqual(len([row for row in candidates if row.model is InheritanceModel.DOMINANT]), 2)

    def test_conflicting_duplicate_metadata_fails_closed(self) -> None:
        het = allele(100, zygosity="heterozygous")
        hom = allele(100, zygosity="homozygous")
        with self.assertRaisesRegex(InheritanceInputError, "conflicting zygosity"):
            generate_inheritance_candidates([het, hom])

    def test_invalid_records_fail_before_candidate_generation(self) -> None:
        with self.assertRaisesRegex(InheritanceInputError, "gene"):
            allele(100, gene=" ")
        with self.assertRaisesRegex(InheritanceInputError, "haplotype requires"):
            allele(100, haplotype="1")
        with self.assertRaisesRegex(InheritanceInputError, "pos must be positive"):
            allele(0)
        with self.assertRaisesRegex(InheritanceInputError, "ref and alt cannot"):
            allele(100, ref="a", alt="A")

    def test_records_and_candidates_have_no_patient_or_phenotype_fields(self) -> None:
        forbidden = {"proband_id", "sample_id", "patient_id", "hpo", "controls", "diagnosis"}
        self.assertTrue(forbidden.isdisjoint(field.name for field in dataclasses.fields(AlleleRecord)))
        self.assertTrue(
            forbidden.isdisjoint(field.name for field in dataclasses.fields(generate_inheritance_candidates([allele(1)])[0]))
        )

    def test_generator_input_is_supported_and_empty_input_is_stable(self) -> None:
        records = (record for record in [allele(100), allele(200, ref="C", alt="T")])
        self.assertEqual(len(generate_inheritance_candidates(records)), 3)
        self.assertEqual(generate_inheritance_candidates([]), ())


if __name__ == "__main__":
    unittest.main()
