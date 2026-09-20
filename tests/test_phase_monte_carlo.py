from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.phase_monte_carlo import (
    CLAIM_BOUNDARY,
    SCHEMA,
    PhaseMonteCarloError,
    assess_phase_split,
)


class PhaseMonteCarloTests(unittest.TestCase):
    def test_community_split_rejects_dropout(self) -> None:
        result = assess_phase_split(41, 38, 30, (0.52, 0.47))
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertTrue(result["strand_ok"])
        self.assertTrue(result["dropout_rejected"])
        self.assertEqual(result["reason"], "dropout_rejected")
        self.assertLess(result["p_as_extreme_under_dropout"], 0.05)

    def test_majority_split_stays_dropout_compatible(self) -> None:
        result = assess_phase_split(40, 2, 8, (0.50, 0.50))
        self.assertTrue(result["strand_ok"])
        self.assertFalse(result["dropout_rejected"])
        self.assertEqual(result["reason"], "dropout_compatible")
        self.assertGreaterEqual(result["p_as_extreme_under_dropout"], 0.05)

    def test_strand_bias_cannot_confirm(self) -> None:
        result = assess_phase_split(41, 38, 30, (0.95, 0.47))
        self.assertFalse(result["strand_ok"])
        self.assertFalse(result["dropout_rejected"])
        self.assertEqual(result["reason"], "strand_imbalance")
        self.assertIsNone(result["p_as_extreme_under_dropout"])

    def test_zero_or_negative_sims_cannot_reject_dropout(self) -> None:
        for bad_sims in (0, -1, 1, 799, True, 800.5):
            with self.assertRaises(PhaseMonteCarloError):
                assess_phase_split(41, 38, 30, (0.5, 0.5), n_sims=bad_sims)

    def test_seed_is_fixed(self) -> None:
        with self.assertRaisesRegex(PhaseMonteCarloError, "seed is fixed"):
            assess_phase_split(41, 38, 30, (0.5, 0.5), seed=12345)

    def test_minimum_cannot_drop_below_protocol_floor(self) -> None:
        for bad_minimum in (0, 1, 7, -1):
            with self.assertRaisesRegex(PhaseMonteCarloError, "protocol floor"):
                assess_phase_split(41, 38, bad_minimum, (0.5, 0.5))

    def test_n_sims_ceiling(self) -> None:
        with self.assertRaisesRegex(PhaseMonteCarloError, "ceiling"):
            assess_phase_split(41, 38, 30, (0.5, 0.5), n_sims=10_001)

    def test_total_molecule_ceiling(self) -> None:
        with self.assertRaisesRegex(PhaseMonteCarloError, "ceiling"):
            assess_phase_split(10_000_001, 0, 8, (0.5, 0.5))

    def test_missing_or_bad_strand_balance_cannot_reject_dropout(self) -> None:
        with self.assertRaises(PhaseMonteCarloError):
            assess_phase_split(41, 38, 30, ())
        with self.assertRaises(PhaseMonteCarloError):
            assess_phase_split(41, 38, 30, ("0.5",))
        nan_result = assess_phase_split(41, 38, 30, (float("nan"),))
        self.assertFalse(nan_result["strand_ok"])
        self.assertFalse(nan_result["dropout_rejected"])


if __name__ == "__main__":
    unittest.main()
