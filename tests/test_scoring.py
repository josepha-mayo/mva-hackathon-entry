from __future__ import annotations

import math
import unittest

from mva_hackathon.scoring import score_rows
from mva_hackathon.submission import Prediction, SubmissionError


TRUE = frozenset(
    {
        ("chr7", 101001, "A", "G"),
        ("chr7", 101249, "C", "T"),
    }
)


def _row(epcr: float, index: int = 2) -> Prediction:
    return Prediction("PROBAND01", TRUE, epcr, "primary", "", index)


class ScoreRowsValidationTests(unittest.TestCase):
    def test_nan_epcr_is_rejected_not_ranked(self) -> None:
        with self.assertRaises(SubmissionError):
            score_rows([_row(float("nan"), index=1)], TRUE)

    def test_infinite_epcr_is_rejected_not_ranked(self) -> None:
        with self.assertRaises(SubmissionError):
            score_rows([_row(float("inf"))], TRUE)
        with self.assertRaises(SubmissionError):
            score_rows([_row(float("-inf"))], TRUE)

    def test_out_of_range_epcr_is_rejected(self) -> None:
        for bad in (0.0, -0.5, 1.5):
            with self.assertRaises(SubmissionError):
                score_rows([_row(bad)], TRUE)

    def test_boolean_epcr_is_rejected(self) -> None:
        with self.assertRaises(SubmissionError):
            score_rows([_row(True)], TRUE)  # type: ignore[arg-type]

    def test_valid_epcr_scores_normally(self) -> None:
        result = score_rows([_row(0.9)], TRUE)
        self.assertEqual(result.full_match_rank, 1)
        self.assertEqual(result.rank_points, 100.0)
        self.assertTrue(math.isfinite(result.f_max))


if __name__ == "__main__":
    unittest.main()
