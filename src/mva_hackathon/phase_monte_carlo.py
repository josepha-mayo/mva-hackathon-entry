"""Dropout-aware phase split check. Balanced counts are not a haplotype.

A trans tick still needs agreeing guide linkage. This only rejects splits
that still look like allelic dropout or strand bias. It does not call phase
on a person and is not a diagnosis.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any


SCHEMA = "mva-track2-phase-monte-carlo/v1"
STRAND_LOW = 0.35
STRAND_HIGH = 0.65
DROPOUT_MAJORITY = 0.92
CIS_TAIL = 0.05
N_SIMS = 800
MAX_N_SIMS = 10_000
MINIMUM_PHASE_FLOOR = 8
MAX_PHASE_MOLECULES = 10_000_000
SEED = 20260829
CLAIM_BOUNDARY = (
    "Phase-split software contract only; dropout rejection is not a trans "
    "call; this is not a diagnosis and not efficacy evidence."
)


class PhaseMonteCarloError(ValueError):
    """Raised when a phase-split input is unusable."""


def _binomial(rng: random.Random, n: int, probability: float) -> int:
    if n <= 0:
        return 0
    return rng.binomialvariate(n, probability)


def assess_phase_split(
    hap_a: int,
    hap_b: int,
    minimum: int,
    strand_balances: Sequence[float],
    *,
    n_sims: int = N_SIMS,
    seed: int = SEED,
) -> dict[str, Any]:
    """Hold when the recovered split still looks like dropout or strand bias."""

    for value in (hap_a, hap_b, minimum, n_sims, seed):
        if isinstance(value, bool) or not isinstance(value, int):
            raise PhaseMonteCarloError("counts, n_sims, and seed must be integers")
    if hap_a < 0 or hap_b < 0:
        raise PhaseMonteCarloError("molecule counts must be usable")
    if hap_a + hap_b > MAX_PHASE_MOLECULES:
        raise PhaseMonteCarloError(
            "total molecule count exceeds the bounded simulation ceiling"
        )
    if minimum < MINIMUM_PHASE_FLOOR:
        raise PhaseMonteCarloError(
            "minimum cannot drop below the declared protocol floor"
        )
    if n_sims < N_SIMS:
        raise PhaseMonteCarloError("n_sims cannot drop below the declared floor")
    if n_sims > MAX_N_SIMS:
        raise PhaseMonteCarloError(
            "n_sims exceeds the bounded simulation ceiling"
        )
    if seed != SEED:
        raise PhaseMonteCarloError("seed is fixed at the declared constant")
    balances = list(strand_balances)
    if not balances:
        raise PhaseMonteCarloError("at least one strand balance is required")
    if any(
        isinstance(balance, bool) or not isinstance(balance, (int, float))
        for balance in balances
    ):
        raise PhaseMonteCarloError("strand balances must be numeric")
    if any(not (STRAND_LOW <= balance <= STRAND_HIGH) for balance in balances):
        return {
            "schema": SCHEMA,
            "synthetic_only": True,
            "claim_boundary": CLAIM_BOUNDARY,
            "strand_ok": False,
            "dropout_rejected": False,
            "p_as_extreme_under_dropout": None,
            "reason": "strand_imbalance",
        }
    total = hap_a + hap_b
    observed_min = min(hap_a, hap_b)
    rng = random.Random(seed)
    as_extreme = 0
    for _ in range(n_sims):
        majority = _binomial(rng, total, DROPOUT_MAJORITY)
        if rng.random() < 0.5:
            majority = total - majority
        if min(majority, total - majority) >= observed_min:
            as_extreme += 1
    p_extreme = as_extreme / n_sims if n_sims else 1.0
    dropout_rejected = p_extreme < CIS_TAIL and observed_min >= minimum
    if not dropout_rejected:
        reason = "dropout_compatible"
    else:
        reason = "dropout_rejected"
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "strand_ok": True,
        "dropout_rejected": dropout_rejected,
        "p_as_extreme_under_dropout": p_extreme,
        "reason": reason,
        "n_sims": n_sims,
        "seed": seed,
    }


__all__ = [
    "CLAIM_BOUNDARY",
    "SCHEMA",
    "PhaseMonteCarloError",
    "assess_phase_split",
]
