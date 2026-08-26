"""Local reproduction of the public SageBio Track 1 evaluator.

The official Space source is CC BY 4.0. This implementation intentionally keeps
the same rank tiers and individual-variant F-max behavior while accepting the
strict ``Prediction`` objects produced by :mod:`mva_hackathon.submission`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .submission import Prediction, Variant

RANK_POINT_TIERS = ((1, 100), (3, 50), (5, 25), (10, 10))


@dataclass(frozen=True)
class ScoreResult:
    full_match_rank: int | None
    partial_match_rank: int | None
    rank_points: float
    f_max: float
    f_max_threshold: float | None
    n_predictions_at_f_max: int


def _rank_points(rank: int) -> int:
    for maximum, points in RANK_POINT_TIERS:
        if rank <= maximum:
            return points
    return 0


def score_rows(rows: Iterable[Prediction], true_variants: frozenset[Variant]) -> ScoreResult:
    ranked = sorted(enumerate(rows), key=lambda item: (-item[1].epcr, item[0]))
    predictions = [row for _, row in ranked]

    full_rank = next(
        (rank for rank, row in enumerate(predictions, start=1) if row.variants == true_variants),
        None,
    )
    partial_rank = None
    if len(true_variants) == 2 and full_rank is None:
        partial_rank = next(
            (
                rank
                for rank, row in enumerate(predictions, start=1)
                if row.variants & true_variants
            ),
            None,
        )

    if full_rank is not None:
        rank_points = float(_rank_points(full_rank))
    elif partial_rank is not None:
        rank_points = 0.5 * _rank_points(partial_rank)
    else:
        rank_points = 0.0

    best_f = 0.0
    best_threshold = None
    best_n = 0
    for threshold in sorted({row.epcr for row in predictions}, reverse=True):
        selected = [row for row in predictions if row.epcr >= threshold]
        predicted: set[Variant] = set()
        for row in selected:
            predicted.update(row.variants)
        true_positive = len(predicted & true_variants)
        false_positive = len(predicted - true_variants)
        false_negative = len(true_variants - predicted)
        precision = true_positive / (true_positive + false_positive) if predicted else 0.0
        recall = true_positive / (true_positive + false_negative) if true_variants else 0.0
        f_score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if f_score > best_f:
            best_f = f_score
            best_threshold = threshold
            best_n = len(selected)

    return ScoreResult(
        full_match_rank=full_rank,
        partial_match_rank=partial_rank,
        rank_points=rank_points,
        f_max=best_f,
        f_max_threshold=best_threshold,
        n_predictions_at_f_max=best_n,
    )
