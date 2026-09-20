"""Finite-doubling competing-risk operating characteristic.

A short primary-culture window can make bulk aneuploid fraction fall when
error-line cells die more, even if new error on completed euploid mitoses
does not. Generation here is that new-error rate, not the mix of already
aneuploid cells. This is a synthetic operating characteristic, not this
child's cells, not a wet assay, and not efficacy evidence.
"""

from __future__ import annotations

import random
from typing import Any


SCHEMA = "mva-track2-culture-window/v1"
N_SIMS = 80
SEED = 20260829
MAX_FALSE_RESCUE = 0.20
MAX_REMAINING_PD = 128
MAX_N_SIMS = 10_000
START_EUPLOID = 24
START_ANEUPLOID = 12
VEHICLE_DEATH_EUPLOID = 0.04
VEHICLE_DEATH_ANEUPLOID = 0.08
COPING_DEATH_EUPLOID = 0.04
COPING_DEATH_ANEUPLOID = 0.45
ERROR_ON_DIVISION = 0.33
BULK_DROP = 0.75
GENERATION_DROP = 0.75
CLAIM_BOUNDARY = (
    "Culture-window software operating characteristic only; finite "
    "doublings are synthetic; this is not a child's culture, not a wet "
    "assay, and not efficacy evidence."
)


class CultureWindowError(ValueError):
    """Raised when a culture-window simulation input is unusable."""


def _binomial(rng: random.Random, n: int, probability: float) -> int:
    if n <= 0:
        return 0
    return rng.binomialvariate(n, probability)


def _stochastic_round(rng: random.Random, value: float) -> int:
    """Unbiased rounding: floor plus a seeded Bernoulli draw on the fraction."""
    base = int(value)
    return base + (1 if rng.random() < value - base else 0)


def _arm(
    rng: random.Random,
    *,
    remaining_pd: int,
    death_euploid: float,
    death_aneuploid: float,
    error_p: float,
) -> tuple[float, float]:
    euploid = START_EUPLOID
    aneuploid = START_ANEUPLOID
    euploid_completed = 0
    new_error_divisions = 0
    for _ in range(remaining_pd):
        living_eu = euploid - _binomial(rng, euploid, death_euploid)
        living_an = aneuploid - _binomial(rng, aneuploid, death_aneuploid)
        new_eu = 0
        new_an = 0
        if living_eu:
            error_from_eu = _binomial(rng, living_eu, error_p)
            euploid_completed += living_eu
            new_error_divisions += error_from_eu
            new_eu += (living_eu - error_from_eu) * 2
            new_an += error_from_eu * 2
        if living_an:
            new_an += living_an * 2
        total = new_eu + new_an
        if total > 4096:
            scale = 4096 / total
            new_eu = _stochastic_round(rng, new_eu * scale)
            new_an = _stochastic_round(rng, new_an * scale)
        euploid, aneuploid = new_eu, new_an
    living = euploid + aneuploid
    bulk = aneuploid / living if living else 0.0
    generation = new_error_divisions / euploid_completed if euploid_completed else 0.0
    return bulk, generation


def simulate_false_bulk_rescue(
    *,
    remaining_pd: int,
    n_sims: int = N_SIMS,
    seed: int = SEED,
) -> dict[str, Any]:
    """Estimate how often death-masking fakes a bulk-fraction rescue."""

    if not isinstance(remaining_pd, int) or isinstance(remaining_pd, bool) or remaining_pd < 1:
        raise CultureWindowError("remaining_population_doublings must be a positive integer")
    if remaining_pd > MAX_REMAINING_PD:
        raise CultureWindowError(
            "remaining_population_doublings exceeds a manufacturable ceiling"
        )
    if not isinstance(n_sims, int) or isinstance(n_sims, bool) or n_sims < N_SIMS:
        raise CultureWindowError(
            "n_sims cannot drop below the declared replicate floor"
        )
    if n_sims > MAX_N_SIMS:
        raise CultureWindowError(
            "n_sims exceeds the bounded simulation ceiling"
        )
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise CultureWindowError("seed must be an integer")
    if seed != SEED:
        raise CultureWindowError("seed is fixed at the declared constant")
    rng = random.Random(seed)
    hits = 0
    unmeasurable = 0
    for _ in range(n_sims):
        vehicle_bulk, vehicle_gen = _arm(
            rng,
            remaining_pd=remaining_pd,
            death_euploid=VEHICLE_DEATH_EUPLOID,
            death_aneuploid=VEHICLE_DEATH_ANEUPLOID,
            error_p=ERROR_ON_DIVISION,
        )
        coping_bulk, coping_gen = _arm(
            rng,
            remaining_pd=remaining_pd,
            death_euploid=COPING_DEATH_EUPLOID,
            death_aneuploid=COPING_DEATH_ANEUPLOID,
            error_p=ERROR_ON_DIVISION,
        )
        bulk_drop = vehicle_bulk > 0 and coping_bulk < BULK_DROP * vehicle_bulk
        # A vehicle arm with no measurable new-error divisions cannot
        # demonstrate the generation held — the trial cannot exclude
        # death-masking, so it is counted as false-rescue-prone (the
        # conservative alarm direction) and reported separately.
        generation_held = vehicle_gen <= 0 or coping_gen >= GENERATION_DROP * vehicle_gen
        if vehicle_gen <= 0:
            unmeasurable += 1
        if bulk_drop and generation_held:
            hits += 1
    rate = hits / n_sims
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "remaining_population_doublings": remaining_pd,
        "n_sims": n_sims,
        "p_false_bulk_rescue": rate,
        "vehicle_generation_unmeasurable_fraction": unmeasurable / n_sims,
        "false_rescue_likely": rate >= MAX_FALSE_RESCUE,
        "max_false_rescue": MAX_FALSE_RESCUE,
        "reason": "false_bulk_rescue_likely" if rate >= MAX_FALSE_RESCUE else "generation_estimand_required",
    }


__all__ = [
    "CLAIM_BOUNDARY",
    "MAX_FALSE_RESCUE",
    "SCHEMA",
    "CultureWindowError",
    "simulate_false_bulk_rescue",
]
