"""Unit and compartment counterexamples for the public exposure arithmetic."""
import copy
import json
from pathlib import Path
import unittest

from mva_hackathon.published_exposure import analyze, mass_auc_to_molar

INPUTS = Path(__file__).resolve().parents[1] / 'configs/published-exposure-inputs.json'


class PublishedExposureTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(INPUTS.read_text(encoding='utf-8'))

    def test_equivalent_mass_units_do_not_create_thousandfold_difference(self):
        self.assertAlmostEqual(mass_auc_to_molar(433, 'ug*h/mL', 164.2011), mass_auc_to_molar(433000, 'ng*h/mL', 164.2011))

    def test_reference_mass_one_millimolar_hour(self):
        self.assertAlmostEqual(mass_auc_to_molar(164.2011, 'ug*h/mL', 164.2011), 1000)

    def test_paa_is_not_accepted_as_parent_pba(self):
        self.data['pba']['analyte'] = 'phenylacetate'
        with self.assertRaises(ValueError):
            analyze(self.data)

    def test_unequal_intervals_cannot_be_silently_compared(self):
        self.data['pba']['culture_reference_hours'] = 336
        with self.assertRaises(ValueError):
            analyze(self.data)

    def test_ambiguous_mass_unit_is_rejected(self):
        self.data['pba']['clinical_auc_unit'] = 'mg*h'
        with self.assertRaises(ValueError):
            analyze(self.data)

    def test_binding_range_and_medium_fraction_are_not_unchecked_percentages(self):
        for field, value in [('external_plasma_bound_fraction_range', [0.98, 0.81]), ('external_plasma_bound_fraction_range', [81, 98]), ('assumed_medium_free_fractions', [0]), ('assumed_medium_free_fractions', [float('nan')])]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.data)
                data['pba'][field] = value
                with self.assertRaises(ValueError):
                    analyze(data)

    def test_unknown_medium_binding_can_reverse_an_integral_comparison(self):
        result = analyze(self.data)
        for profile in result['pba']['profiles']:
            scenarios = profile['medium_scenarios']
            self.assertGreater(scenarios[0]['illustrative_plasma_free_auc_over_assumed_medium_free_auc_range'][0], 1)
            self.assertLess(scenarios[-1]['illustrative_plasma_free_auc_over_assumed_medium_free_auc_range'][1], 1)
        self.assertFalse(result['clinical_advancement_granted'])
        self.assertFalse(result['historical_gate_modified'])

    def test_same_auc_can_hide_completely_different_profiles(self):
        # Both invented profiles integrate to 2400 uM*h. One never reaches
        # 200 uM; the other reaches it for 12 h. This is not patient PK.
        flat = [(24, 100)]
        pulse = [(12, 200), (12, 0)]
        integral = lambda rows: sum(hours * concentration for hours, concentration in rows)
        self.assertEqual(integral(flat), integral(pulse))
        self.assertNotEqual(sum(h for h, c in flat if c >= 200), sum(h for h, c in pulse if c >= 200))

    def test_matched_elam_peak_is_not_a_daily_exposure(self):
        result = analyze(self.data)['elamipretide_peak_warning']
        self.assertAlmostEqual(result['peak_rectangle_over_reported_auc'], 8.54025974025974)
        self.data['elamipretide']['auc_tau_ng_h_ml'] = 40000
        with self.assertRaises(ValueError):
            analyze(self.data)

    def test_other_metabolite_cannot_inherit_elamipretide_label(self):
        self.data['elamipretide']['analyte'] = 'phenylacetate'
        with self.assertRaises(ValueError):
            analyze(self.data)

    def test_modified_summary_cannot_inherit_fixed_overlap_claim(self):
        for profile in self.data['pba']['clinical_profiles']:
            profile['total_parent_auc'] /= 100
        result = analyze(self.data)['pba']
        self.assertNotIn('similar', result['inference'])
        self.assertLess(result['profiles'][0]['total_auc_over_assumed_nominal_reference'], 0.02)


if __name__ == '__main__':
    unittest.main()
