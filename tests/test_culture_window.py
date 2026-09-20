from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.culture_window import (
    CLAIM_BOUNDARY,
    MAX_FALSE_RESCUE,
    SCHEMA,
    CultureWindowError,
    simulate_false_bulk_rescue,
)


class CultureWindowTests(unittest.TestCase):
    def test_death_masking_fakes_a_bulk_fraction_drop(self) -> None:
        result = simulate_false_bulk_rescue(remaining_pd=8)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertGreaterEqual(result["p_false_bulk_rescue"], MAX_FALSE_RESCUE)
        self.assertTrue(result["false_rescue_likely"])

    def test_unusable_window_fails_closed(self) -> None:
        with self.assertRaises(CultureWindowError):
            simulate_false_bulk_rescue(remaining_pd=0)

    def test_zero_simulations_fail_closed(self) -> None:
        with self.assertRaises(CultureWindowError):
            simulate_false_bulk_rescue(remaining_pd=8, n_sims=0)
        with self.assertRaises(CultureWindowError):
            simulate_false_bulk_rescue(remaining_pd=8, n_sims=True)

    def test_below_floor_and_bad_seed_fail_closed(self) -> None:
        with self.assertRaises(CultureWindowError):
            simulate_false_bulk_rescue(remaining_pd=8, n_sims=1)
        with self.assertRaises(CultureWindowError):
            simulate_false_bulk_rescue(remaining_pd=8, seed="0")

    def test_seed_is_fixed_and_doublings_capped(self) -> None:
        with self.assertRaisesRegex(CultureWindowError, "seed is fixed"):
            simulate_false_bulk_rescue(remaining_pd=8, seed=12345)
        with self.assertRaisesRegex(CultureWindowError, "ceiling"):
            simulate_false_bulk_rescue(remaining_pd=10**9)
        with self.assertRaisesRegex(CultureWindowError, "ceiling"):
            simulate_false_bulk_rescue(remaining_pd=8, n_sims=10_001)


if __name__ == "__main__":
    unittest.main()
