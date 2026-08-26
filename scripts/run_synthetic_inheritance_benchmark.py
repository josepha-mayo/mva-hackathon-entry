"""Run a deterministic, aggregate-only inheritance component benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.benchmark import SyntheticCase, SyntheticTruth, evaluate_synthetic_cases
from mva_hackathon.inheritance import AlleleRecord, InheritanceModel, PhaseState, Zygosity


def _allele(
    gene: str,
    chrom: str,
    pos: int,
    *,
    zygosity: Zygosity,
    ref: str = "A",
    alt: str = "G",
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


def generate_cases(count: int) -> tuple[tuple[SyntheticCase, ...], Counter[str]]:
    if count < 60:
        raise ValueError("--cases must be at least 60")
    cases: list[SyntheticCase] = []
    distribution: Counter[str] = Counter()
    for index in range(count):
        kind = index % 6
        base = 100_000 + index * 1_000
        gene = f"SYNTRUTH{index:05d}"
        case_id = f"SYNCASE-{index:05d}"
        records: list[AlleleRecord] = []
        truth: SyntheticTruth | None

        if kind in {0, 1}:
            phase_set = f"P{index}" if kind == 0 else None
            first = _allele(
                gene, "chr7", base, zygosity=Zygosity.HETEROZYGOUS,
                phase_set=phase_set, haplotype="1" if phase_set else None,
            )
            second = _allele(
                gene, "chr7", base + 100, zygosity=Zygosity.HETEROZYGOUS,
                ref="C", alt="T", phase_set=phase_set,
                haplotype="2" if phase_set else None,
            )
            records.extend((first, second))
            phase = PhaseState.TRANS_CONFIRMED if phase_set else PhaseState.UNRESOLVED
            truth = SyntheticTruth(
                gene, InheritanceModel.COMPOUND_HETEROZYGOUS,
                frozenset((first.variant_key, second.variant_key)), phase,
            )
            distribution[f"compound_{phase.value}"] += 1
        elif kind == 2:
            record = _allele(gene, "chr7", base, zygosity=Zygosity.HOMOZYGOUS)
            records.append(record)
            truth = SyntheticTruth(
                gene, InheritanceModel.HOMOZYGOUS_RECESSIVE,
                frozenset((record.variant_key,)),
            )
            distribution["homozygous_recessive"] += 1
        elif kind == 3:
            record = _allele(gene, "chrX", 5_000_000 + index, zygosity=Zygosity.HEMIZYGOUS)
            records.append(record)
            truth = SyntheticTruth(
                gene, InheritanceModel.X_LINKED, frozenset((record.variant_key,))
            )
            distribution["x_linked"] += 1
        elif kind == 4:
            record = _allele(
                gene, "chrM", 1_000 + index % 10_000, zygosity=Zygosity.HETEROPLASMIC
            )
            records.append(record)
            truth = SyntheticTruth(
                gene, InheritanceModel.MITOCHONDRIAL, frozenset((record.variant_key,))
            )
            distribution["mitochondrial"] += 1
        else:
            first = _allele(
                gene, "chr7", base, zygosity=Zygosity.HETEROZYGOUS,
                phase_set=f"C{index}", haplotype="1",
            )
            second = _allele(
                gene, "chr7", base + 100, zygosity=Zygosity.HETEROZYGOUS,
                ref="C", alt="T", phase_set=f"C{index}", haplotype="1",
            )
            records.extend((first, second))
            truth = None
            distribution["confirmed_cis_negative"] += 1

        # One in ten cases receives a same-gene unresolved distractor pair.
        # Enumeration should retain it; downstream ranking/calibration must
        # distinguish it. This prevents a misleading all-perfect component test.
        if index % 10 == 0:
            distractor_gene = f"SYNDIST{index:05d}"
            records.extend(
                (
                    _allele(
                        distractor_gene, "chr9", base, zygosity=Zygosity.HETEROZYGOUS
                    ),
                    _allele(
                        distractor_gene, "chr9", base + 100,
                        zygosity=Zygosity.HETEROZYGOUS, ref="G", alt="T",
                    ),
                )
            )
            distribution["cases_with_unresolved_distractor_pair"] += 1

        cases.append(SyntheticCase(case_id, tuple(records), truth))
    return tuple(cases), distribution


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=600)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--bootstrap-iterations", type=int, default=2_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases, distribution = generate_cases(args.cases)
    result = evaluate_synthetic_cases(
        cases, seed=args.seed, bootstrap_iterations=args.bootstrap_iterations
    )
    result["fixture_distribution"] = dict(sorted(distribution.items()))
    result["generator"] = "scripts/run_synthetic_inheritance_benchmark.py/v1"
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=True) + "\n"
    if args.output:
        args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.resolve().write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
