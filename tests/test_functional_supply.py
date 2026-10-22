"""Numerical and identifiability checks on invented protein-pool models."""

from pathlib import Path
import math
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.functional_supply import SupplyModel, demonstration


class FunctionalSupplyTests(unittest.TestCase):
    def test_matches_independent_small_step_integration(self):
        # Independent forward integration of the differential equations.
        model = SupplyModel(1.7, 0.8, 1.1, 0.2, dilution=0.03)
        step = 0.00001
        early = mature = 0.0
        for _ in range(100000):
            de = model.input_rate - model.early_exit * early
            dm = model.maturation * early - model.mature_exit * mature
            early, mature = early + step * de, mature + step * dm
        exact = model.new_label(1)
        self.assertAlmostEqual(early, exact[0], places=5)
        self.assertAlmostEqual(mature, exact[1], places=5)

    def test_mass_balance_and_label_complement(self):
        model = SupplyModel(1, 0.7, 0.3, 0.2, dilution=0.1)
        early, mature = model.steady_state()
        self.assertAlmostEqual(model.input_rate, (model.early_loss + model.dilution) * early + model.mature_exit * mature)
        for hours in (0, 0.1, 2, 20):
            old = model.chase(hours, early, mature)
            new = model.new_label(hours)
            for total, a, b in zip((early, mature), old, new):
                self.assertAlmostEqual(total, a + b)

    def test_equal_exit_rates_and_near_equal_limit(self):
        model = SupplyModel(1, 0.4, 0.6, 1)
        early, mature = model.chase(2, 3, 4)
        self.assertAlmostEqual(early, 3 * math.exp(-2))
        self.assertAlmostEqual(mature, (4 + 0.4 * 3 * 2) * math.exp(-2))
        near = SupplyModel(1, 0.4, 0.6, 1 + 1e-12).chase(2, 3, 4)
        self.assertAlmostEqual(mature, near[1], places=10)

    def test_chase_semigroup_for_finite_age_mixture(self):
        model = SupplyModel(1, 0.7, 2, 0.1)
        for pulse in (0.05, 0.25, 4, 24):
            direct = model.pulse_cohort(pulse, 3)
            staged = model.chase(2, *model.pulse_cohort(pulse, 1))
            for a, b in zip(direct, staged):
                self.assertAlmostEqual(a, b)
        short = model.pulse_cohort(0.25, 0)
        long = model.pulse_cohort(24, 0)
        self.assertNotAlmostEqual(short[1] / sum(short), long[1] / sum(long))

    def test_nonidentifiability_witnesses(self):
        result = demonstration()
        self.assertTrue(result["all_counterexamples_reproduced"])
        self.assertFalse(result["mechanism_identified_in_child"])
        self.assertEqual(result, demonstration())

    def test_early_loss_timing_probe_has_no_late_recovery_of_lost_cohort(self):
        result = demonstration()["invented_timing_probe"]
        self.assertGreater(result["early_window_mature"], 3 * result["untreated_mature"])
        self.assertAlmostEqual(result["late_window_mature"], result["untreated_mature"], places=10)

    def test_invalid_rates_and_times(self):
        for value in (True, -1, float("nan"), float("inf"), "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SupplyModel(value, 1, 0, 0.1)
        for args in ((1, 0, 0, 0.1), (1, 1, 0, 0)):
            with self.assertRaises(ValueError):
                SupplyModel(*args)
        model = SupplyModel(1, 1, 0, 0.1)
        with self.assertRaises(ValueError):
            model.chase(-1, 1, 1)
        with self.assertRaises(ValueError):
            SupplyModel(1, 1, 0, 0.1, activity=1.1)


if __name__ == "__main__":
    unittest.main()
