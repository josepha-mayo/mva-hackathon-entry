"""Deterministic public/synthetic evaluation for inheritance candidate generation.

This is a component-contract benchmark, not biological validation and not a
diagnostic ranking benchmark. It intentionally contains no proband identifiers,
phenotypes, real genes, or controlled coordinates.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable

from .inheritance import (
    AlleleRecord,
    InheritanceModel,
    PhaseState,
    VariantKey,
    generate_inheritance_candidates,
)


class BenchmarkInputError(ValueError):
    """Raised when a benchmark fixture or run configuration is malformed."""


@dataclass(frozen=True)
class SyntheticTruth:
    gene: str
    model: InheritanceModel
    variant_keys: frozenset[VariantKey]
    phase_state: PhaseState | None = None

    def __post_init__(self) -> None:
        gene = self.gene.strip().upper() if isinstance(self.gene, str) else ""
        if not gene.startswith("SYN"):
            raise BenchmarkInputError("synthetic truth genes must start with SYN")
        try:
            model = self.model if isinstance(self.model, InheritanceModel) else InheritanceModel(self.model)
        except (TypeError, ValueError) as exc:
            raise BenchmarkInputError("truth model is invalid") from exc
        if not isinstance(self.variant_keys, frozenset) or not self.variant_keys:
            raise BenchmarkInputError("truth variant_keys must be a non-empty frozenset")
        phase = self.phase_state
        if phase is not None and not isinstance(phase, PhaseState):
            try:
                phase = PhaseState(phase)
            except (TypeError, ValueError) as exc:
                raise BenchmarkInputError("truth phase_state is invalid") from exc
        if model is InheritanceModel.COMPOUND_HETEROZYGOUS:
            if len(self.variant_keys) != 2 or phase not in {
                PhaseState.TRANS_CONFIRMED,
                PhaseState.UNRESOLVED,
            }:
                raise BenchmarkInputError("compound truth requires two alleles and eligible phase")
        elif len(self.variant_keys) != 1 or phase is not None:
            raise BenchmarkInputError("single-allele truth requires one allele and no phase")
        object.__setattr__(self, "gene", gene)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "phase_state", phase)


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    records: tuple[AlleleRecord, ...]
    truth: SyntheticTruth | None

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.startswith("SYNCASE-"):
            raise BenchmarkInputError("case_id must use the SYNCASE- synthetic namespace")
        if not isinstance(self.records, tuple) or not self.records:
            raise BenchmarkInputError("records must be a non-empty tuple")
        if any(not isinstance(record, AlleleRecord) for record in self.records):
            raise BenchmarkInputError("records must contain only AlleleRecord values")
        if any(not record.gene.startswith("SYN") for record in self.records):
            raise BenchmarkInputError("benchmark records must use synthetic gene names")
        if self.truth is not None:
            available = {record.variant_key for record in self.records}
            if not self.truth.variant_keys <= available:
                raise BenchmarkInputError("truth alleles must be present in case records")


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _bootstrap_rate(
    observations: list[int], *, seed: int, iterations: int
) -> tuple[float, float]:
    if not observations:
        return (math.nan, math.nan)
    if iterations < 100:
        raise BenchmarkInputError("bootstrap_iterations must be at least 100")
    generator = random.Random(seed)
    count = len(observations)
    estimates = [
        sum(observations[generator.randrange(count)] for _ in range(count)) / count
        for _ in range(iterations)
    ]
    return (_percentile(estimates, 0.025), _percentile(estimates, 0.975))


def evaluate_synthetic_cases(
    cases: Iterable[SyntheticCase], *, seed: int = 20260826, bootstrap_iterations: int = 2_000
) -> dict[str, object]:
    """Evaluate truth-universe recovery and false compound-pair emission.

    False-pair fraction measures enumeration breadth against the synthetic truth;
    it is not a ranked false-positive rate because this engine does not rank.
    """

    materialized = tuple(cases)
    if not materialized:
        raise BenchmarkInputError("at least one synthetic case is required")
    if len({case.case_id for case in materialized}) != len(materialized):
        raise BenchmarkInputError("case_id values must be unique")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise BenchmarkInputError("seed must be an integer")

    positive_outcomes: list[int] = []
    pair_outcomes: list[int] = []
    emitted_pairs = 0
    false_pairs = 0
    cis_leaks = 0

    for case in materialized:
        if not isinstance(case, SyntheticCase):
            raise BenchmarkInputError("cases must contain only SyntheticCase values")
        candidates = generate_inheritance_candidates(case.records)
        pair_candidates = [
            candidate
            for candidate in candidates
            if candidate.model is InheritanceModel.COMPOUND_HETEROZYGOUS
        ]
        emitted_pairs += len(pair_candidates)
        cis_leaks += sum(candidate.phase_state is PhaseState.CIS_CONFIRMED for candidate in pair_candidates)

        truth_match = None
        if case.truth is not None:
            matches = [
                candidate
                for candidate in candidates
                if candidate.gene == case.truth.gene
                and candidate.model is case.truth.model
                and frozenset(candidate.variant_keys) == case.truth.variant_keys
                and candidate.phase_state is case.truth.phase_state
            ]
            if len(matches) > 1:
                raise AssertionError("candidate engine emitted duplicate truth matches")
            truth_match = matches[0] if matches else None
            positive_outcomes.append(int(truth_match is not None))
            if case.truth.model is InheritanceModel.COMPOUND_HETEROZYGOUS:
                pair_outcomes.append(int(truth_match is not None))

        for candidate in pair_candidates:
            if case.truth is None or not (
                case.truth.model is InheritanceModel.COMPOUND_HETEROZYGOUS
                and candidate.gene == case.truth.gene
                and frozenset(candidate.variant_keys) == case.truth.variant_keys
                and candidate.phase_state is case.truth.phase_state
            ):
                false_pairs += 1

    truth_recovered = sum(positive_outcomes)
    pair_recovered = sum(pair_outcomes)
    truth_ci = _bootstrap_rate(
        positive_outcomes, seed=seed, iterations=bootstrap_iterations
    )
    pair_ci = _bootstrap_rate(
        pair_outcomes, seed=seed + 1, iterations=bootstrap_iterations
    ) if pair_outcomes else (math.nan, math.nan)

    return {
        "schema": "mva-synthetic-inheritance-benchmark/v1",
        "scope": "component-contract-only; not biological validation or diagnostic ranking",
        "seed": seed,
        "bootstrap_iterations": bootstrap_iterations,
        "cases": len(materialized),
        "positive_cases": len(positive_outcomes),
        "truth_recovered": truth_recovered,
        "truth_recall": truth_recovered / len(positive_outcomes) if positive_outcomes else math.nan,
        "truth_recall_bootstrap_95_ci": list(truth_ci),
        "compound_positive_cases": len(pair_outcomes),
        "compound_truth_recovered": pair_recovered,
        "compound_truth_recall": pair_recovered / len(pair_outcomes) if pair_outcomes else math.nan,
        "compound_truth_recall_bootstrap_95_ci": list(pair_ci),
        "emitted_compound_candidates": emitted_pairs,
        "false_compound_candidates": false_pairs,
        "false_compound_fraction": false_pairs / emitted_pairs if emitted_pairs else 0.0,
        "confirmed_cis_leaks": cis_leaks,
    }


__all__ = [
    "BenchmarkInputError",
    "SyntheticCase",
    "SyntheticTruth",
    "evaluate_synthetic_cases",
]
