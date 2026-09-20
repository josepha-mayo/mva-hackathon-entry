from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.benchmark import (
    BenchmarkInputError,
    SyntheticCase,
    SyntheticTruth,
    evaluate_synthetic_cases,
)
from mva_hackathon.inheritance import AlleleRecord, InheritanceModel, PhaseState, Zygosity


def _strict_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def allele(
    gene: str, pos: int, *, phase_set: str | None = None, haplotype: str | None = None,
    zygosity: Zygosity = Zygosity.HETEROZYGOUS,
) -> AlleleRecord:
    return AlleleRecord(
        gene=gene, chrom="chr7", pos=pos, ref="A", alt="G", zygosity=zygosity,
        phase_set=phase_set, haplotype=haplotype,
    )


def positive_pair(case_id: str = "SYNCASE-1", offset: int = 0) -> SyntheticCase:
    first = allele(
        "SYNTRUTH", 10_001 + offset, phase_set="SYNPHASE1", haplotype="1"
    )
    second = allele(
        "SYNTRUTH", 10_101 + offset, phase_set="SYNPHASE1", haplotype="2"
    )
    return SyntheticCase(
        case_id=case_id,
        records=(first, second),
        truth=SyntheticTruth(
            gene="SYNTRUTH",
            model=InheritanceModel.COMPOUND_HETEROZYGOUS,
            variant_keys=frozenset((first.variant_key, second.variant_key)),
            phase_state=PhaseState.TRANS_CONFIRMED,
        ),
    )


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_recovers_trans_pair_and_reports_component_scope(self) -> None:
        result = evaluate_synthetic_cases([positive_pair()], bootstrap_iterations=100)
        self.assertEqual(result["truth_recall"], 1.0)
        self.assertEqual(result["compound_truth_recall"], 1.0)
        self.assertEqual(result["false_compound_candidates"], 0)
        self.assertIn("not biological validation", result["scope"])

    def test_unresolved_truth_requires_unresolved_output(self) -> None:
        first = allele("SYNPAIR", 20_001)
        second = allele("SYNPAIR", 20_101)
        case = SyntheticCase(
            case_id="SYNCASE-U",
            records=(first, second),
            truth=SyntheticTruth(
                gene="SYNPAIR",
                model="compound_heterozygous",
                variant_keys=frozenset((first.variant_key, second.variant_key)),
                phase_state="unresolved",
            ),
        )
        result = evaluate_synthetic_cases([case], bootstrap_iterations=100)
        self.assertEqual(result["compound_truth_recovered"], 1)

    def test_confirmed_cis_negative_never_leaks_a_pair(self) -> None:
        first = allele("SYNCIS", 30_001, phase_set="P", haplotype="1")
        second = allele("SYNCIS", 30_101, phase_set="P", haplotype="1")
        result = evaluate_synthetic_cases(
            [SyntheticCase("SYNCASE-CIS", (first, second), None)], bootstrap_iterations=100
        )
        self.assertEqual(result["emitted_compound_candidates"], 0)
        self.assertEqual(result["confirmed_cis_leaks"], 0)
        self.assertTrue(math.isnan(result["truth_recall"]))

    def test_distractor_pair_is_counted_as_false_not_silently_negative(self) -> None:
        truth = positive_pair()
        distractor_a = allele("SYNDISTRACTOR", 40_001)
        distractor_b = allele("SYNDISTRACTOR", 40_101)
        case = SyntheticCase(
            "SYNCASE-D",
            truth.records + (distractor_a, distractor_b),
            truth.truth,
        )
        result = evaluate_synthetic_cases([case], bootstrap_iterations=100)
        self.assertEqual(result["truth_recovered"], 1)
        self.assertEqual(result["emitted_compound_candidates"], 2)
        self.assertEqual(result["false_compound_candidates"], 1)
        self.assertEqual(result["false_compound_fraction"], 0.5)

    def test_single_allele_truth_is_supported(self) -> None:
        record = allele("SYNREC", 50_001, zygosity=Zygosity.HOMOZYGOUS)
        case = SyntheticCase(
            "SYNCASE-R",
            (record,),
            SyntheticTruth(
                "SYNREC", InheritanceModel.HOMOZYGOUS_RECESSIVE,
                frozenset((record.variant_key,)),
            ),
        )
        result = evaluate_synthetic_cases([case], bootstrap_iterations=100)
        self.assertEqual(result["truth_recall"], 1.0)
        self.assertTrue(math.isnan(result["compound_truth_recall"]))

    def test_bootstrap_is_deterministic(self) -> None:
        cases = [
            positive_pair(f"SYNCASE-{index}", offset=index * 1_000)
            for index in range(5)
        ]
        first = evaluate_synthetic_cases(cases, seed=7, bootstrap_iterations=100)
        second = evaluate_synthetic_cases(cases, seed=7, bootstrap_iterations=100)
        self.assertEqual(first, second)

    def test_rejects_non_synthetic_namespace_and_missing_truth_allele(self) -> None:
        non_synthetic = allele("control".upper() + str(42), 60_001)
        with self.assertRaisesRegex(BenchmarkInputError, "synthetic gene"):
            SyntheticCase("SYNCASE-X", (non_synthetic,), None)
        synthetic = allele("SYNOK", 60_101)
        absent = allele("SYNOK", 60_201)
        with self.assertRaisesRegex(BenchmarkInputError, "present"):
            SyntheticCase(
                "SYNCASE-Y", (synthetic,),
                SyntheticTruth(
                    "SYNOK", InheritanceModel.DOMINANT, frozenset((absent.variant_key,))
                ),
            )

    def test_rejects_duplicate_case_ids_and_too_few_bootstraps(self) -> None:
        case = positive_pair()
        with self.assertRaisesRegex(BenchmarkInputError, "unique"):
            evaluate_synthetic_cases([case, case], bootstrap_iterations=100)
        with self.assertRaisesRegex(BenchmarkInputError, "at least 100"):
            evaluate_synthetic_cases([case], bootstrap_iterations=99)
        for bogus in (100.0, True, "200"):
            with self.subTest(bootstrap_iterations=bogus):
                with self.assertRaisesRegex(BenchmarkInputError, "integer"):
                    evaluate_synthetic_cases([case], bootstrap_iterations=bogus)

    def test_duplicate_case_content_cannot_pad_recall(self) -> None:
        case = positive_pair()
        twin = SyntheticCase("SYNCASE-TWIN", case.records, case.truth)
        with self.assertRaisesRegex(BenchmarkInputError, "unique"):
            evaluate_synthetic_cases([case, twin], bootstrap_iterations=100)

    def test_reordered_case_content_cannot_pad_recall(self) -> None:
        case = positive_pair()
        twin = SyntheticCase(
            "SYNCASE-TWIN", tuple(reversed(case.records)), case.truth
        )
        with self.assertRaisesRegex(BenchmarkInputError, "unique"):
            evaluate_synthetic_cases([case, twin], bootstrap_iterations=100)

    def test_bootstrap_iterations_above_ceiling_rejected(self) -> None:
        with self.assertRaisesRegex(BenchmarkInputError, "ceiling"):
            evaluate_synthetic_cases(
                [positive_pair()], bootstrap_iterations=100_001
            )


class InheritanceBenchmarkCliTests(unittest.TestCase):
    SCRIPT = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_synthetic_inheritance_benchmark.py"
    )

    def test_output_refuses_overwrite_and_serializes_finite(self) -> None:
        import json
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt.json"
            command = [
                sys.executable,
                str(self.SCRIPT),
                "--cases",
                "120",
                "--bootstrap-iterations",
                "100",
                "--output",
                str(target),
            ]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("refusing to overwrite", again.stderr)
            payload = target.read_text(encoding="utf-8")
            self.assertNotIn("NaN", payload)
            self.assertNotIn("Infinity", payload)
            parsed = json.loads(
                payload,
                object_pairs_hook=_strict_object,
                parse_constant=_reject_constant,
            )
            self.assertTrue(
                math.isfinite(parsed["truth_recall"])
                and math.isfinite(parsed["false_compound_candidates"])
            )


if __name__ == "__main__":
    unittest.main()
