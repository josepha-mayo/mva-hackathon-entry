"""All examples are invented contract fixtures, not experimental evidence."""
import copy
import sys
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mva_hackathon.correction_control import (
    PLAN_SCHEMA, EVIDENCE_SCHEMA, ENDPOINTS, SOURCE, CARRIER,
    CorrectionControlError, assess_missense_correction_control,
)
from mva_hackathon.provenance import semantic_digest, receipt_sha256_ok


def fixture():
    specimens = {
        role: {"specimen_id": role, "derivation_event_id": role + "-event",
               "genotype": copy.deepcopy(genotype), "phase": "trans_confirmed",
               "background_id": "synthetic-background", "assay_protocol_id": "synthetic-protocol",
               "genotype_evidence_id": "synthetic-" + role}
        for role, genotype in (("mutant", SOURCE), ("corrected", CARRIER), ("comparator", CARRIER))
    }
    plan = {"schema": PLAN_SCHEMA, "correction_scope": "N1002K_only", "specimens": specimens,
            "frozen_at": "2026-01-01T00:00:00Z", "freeze_record_id": "synthetic-freeze",
            "contrast_method_id": "synthetic-joint-event-contrast", "confidence_level": 0.95,
            "endpoints": [{"endpoint": key, "direction": "higher_is_better", "units": "synthetic-unit",
                           "equivalence_bounds": [-0.2, 0.2], "role": "defect_reversal", "minimum_gap_restoration": 0.5}
                          for key in ENDPOINTS]}
    evidence = {"schema": EVIDENCE_SCHEMA, "specimens": copy.deepcopy(specimens),
                "plan_sha256": semantic_digest(plan), "outcome_unblinded_at": "2026-02-01T00:00:00Z",
                "contrast_method_id": plan["contrast_method_id"], "analysis_record_id": "synthetic-analysis",
                "confidence_level": 0.95,
                "endpoints": [{"endpoint": key, "direction": "higher_is_better", "units": "synthetic-unit",
                               "mutant_mean": 1, "carrier_mean": 2, "corrected_mean": 1.9,
                               "oriented_mutant_to_carrier_gap_ci": [0.8, 1.2],
                               "corrected_minus_carrier_ci": [-0.15, 0.05],
                               "gap_restoration_fraction_ci": [0.6, 1.1]} for key in ENDPOINTS]}
    plan["endpoints"][-1]["direction"] = "lower_is_better"
    evidence["endpoints"][-1].update(direction="lower_is_better", mutant_mean=3,
                                   carrier_mean=2, corrected_mean=2.1,
                                   corrected_minus_carrier_ci=[-0.05, 0.15])
    evidence["plan_sha256"] = semantic_digest(plan)
    return plan, evidence


class CorrectionControlTests(unittest.TestCase):
    def assess(self, p, e):
        return assess_missense_correction_control(p, e)

    def test_carrier_equivalence_without_wt_equivalence(self):
        p, e = fixture()
        original = copy.deepcopy((p, e))
        result = self.assess(p, e)
        self.assertEqual(result["status"], "contract_satisfied")
        self.assertEqual(result["assessment_scope"], "correction_control_only")
        self.assertFalse(result["legacy_pipeline_eligible"])
        self.assertTrue(receipt_sha256_ok(result))
        self.assertEqual((p, e), original)
        # A separate WT ceiling may be 4 units: carrier=2, corrected=1.9.
        # No WT=carrier equivalence is assumed or required by this contract.

    def test_missing_required_metadata_fail_closed(self):
        for side, keys in ((0, ("specimens", "correction_scope", "freeze_record_id", "frozen_at", "endpoints")),
                           (1, ("specimens", "plan_sha256", "analysis_record_id", "outcome_unblinded_at", "endpoints"))):
            for key in keys:
                with self.subTest(side=side, key=key):
                    pair = fixture()
                    del pair[side][key]
                    with self.assertRaises(CorrectionControlError): self.assess(*pair)

    def test_legacy_rejected(self):
        p, e = fixture()
        p["schema"] = "mva.community-allele-function-scorecard/v1"
        with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_scope_and_swapped_carrier_rejected_even_if_rehashed(self):
        for scope in ("L737Ter_only", "double_correction", "unknown", None):
            p, e = fixture(); p["correction_scope"] = scope
            e["plan_sha256"] = semantic_digest(p)
            with self.assertRaises(CorrectionControlError): self.assess(p, e)
        for role in ("mutant", "corrected", "comparator"):
            p, e = fixture()
            p["specimens"][role]["genotype"] = ["NM_001211.6:WT", "NM_001211.6:c.3006T>G"]
            e["specimens"] = copy.deepcopy(p["specimens"]); e["plan_sha256"] = semantic_digest(p)
            with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_comparator_cannot_be_corrected_clone_or_same_event(self):
        for key in ("specimen_id", "derivation_event_id"):
            p, e = fixture()
            p["specimens"]["comparator"][key] = p["specimens"]["corrected"][key]
            e["specimens"] = copy.deepcopy(p["specimens"]); e["plan_sha256"] = semantic_digest(p)
            with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_plan_binding_and_frozen_time(self):
        p, e = fixture(); p["endpoints"][0]["equivalence_bounds"] = [-2, 2]
        with self.assertRaises(CorrectionControlError): self.assess(p, e)
        for value in ("2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z", "2026-01-01", "bad"):
            p, e = fixture(); p["frozen_at"] = value; e["plan_sha256"] = semantic_digest(p)
            with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_partial_overlap_not_equivalence(self):
        p, e = fixture(); e["endpoints"][0]["corrected_minus_carrier_ci"] = [-0.3, 0.05]
        self.assertEqual(self.assess(p, e)["status"], "hold")

    def test_restoration_lower_bound_not_point_estimate(self):
        p, e = fixture(); e["endpoints"][0]["gap_restoration_fraction_ci"] = [0.49, 1.1]
        self.assertEqual(self.assess(p, e)["status"], "hold")

    def test_zero_uncertain_and_wrong_direction_gaps_hold(self):
        for mutant, carrier, corrected, ci in ((2, 2, 2, [0, 0]), (1, 2, 1.9, [-0.1, 1.2]),
                                               (3, 2, 2, [-1.2, -0.8])):
            p, e = fixture(); row = e["endpoints"][0]
            row.update(mutant_mean=mutant, carrier_mean=carrier, corrected_mean=corrected,
                       oriented_mutant_to_carrier_gap_ci=ci)
            self.assertEqual(self.assess(p, e)["status"], "hold")

    def test_lower_is_better_first_division_error(self):
        p, e = fixture()
        self.assertEqual(p["endpoints"][-1]["direction"], "lower_is_better")
        self.assertGreater(e["endpoints"][-1]["mutant_mean"], e["endpoints"][-1]["corrected_mean"])
        self.assertEqual(self.assess(p, e)["status"], "contract_satisfied")

    def test_fixed_endpoint_direction_cannot_be_inverted_even_if_rehashed(self):
        for index, direction in ((0, "lower_is_better"), (1, "lower_is_better"), (4, "higher_is_better")):
            p, e = fixture(); p["endpoints"][index]["direction"] = direction
            e["endpoints"][index]["direction"] = direction
            e["plan_sha256"] = semantic_digest(p)
            with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_duplicate_or_missing_endpoints(self):
        for side in (0, 1):
            for duplicate in (False, True):
                pair = fixture()
                if duplicate: pair[side]["endpoints"][-1] = copy.deepcopy(pair[side]["endpoints"][0])
                else: pair[side]["endpoints"].pop()
                pair[1]["plan_sha256"] = semantic_digest(pair[0])
                with self.assertRaises(CorrectionControlError): self.assess(*pair)

    def test_nonfinite_boolean_and_malformed_intervals(self):
        for value in ([float("nan"), 1], [0, float("inf")], [True, 1], [2, 1], [1], "positive"):
            p, e = fixture(); e["endpoints"][0]["gap_restoration_fraction_ci"] = value
            with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_missing_genotype_and_mean_or_direction_mismatch(self):
        p, e = fixture(); del p["specimens"]["corrected"]["genotype"]
        with self.assertRaises(CorrectionControlError): self.assess(p, e)
        p, e = fixture(); e["endpoints"][0]["direction"] = "lower_is_better"
        with self.assertRaises(CorrectionControlError): self.assess(p, e)
        p, e = fixture(); e["endpoints"][0]["mutant_mean"] = 9
        with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_endpoint_metadata_and_margin_rejected(self):
        for key, value in (("direction", "unknown"), ("units", ""),
                           ("minimum_gap_restoration", 0.49), ("minimum_gap_restoration", True),
                           ("equivalence_bounds", [0, 1]), ("equivalence_bounds", [-1, 0])):
            p, e = fixture(); p["endpoints"][0][key] = value
            e["plan_sha256"] = semantic_digest(p)
            with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_observed_identity_phase_and_method_mismatch(self):
        for key in ("specimen_id", "genotype_evidence_id", "background_id", "assay_protocol_id", "phase"):
            p, e = fixture(); e["specimens"]["comparator"][key] = "swapped"
            with self.assertRaises(CorrectionControlError): self.assess(p, e)
        p, e = fixture(); e["contrast_method_id"] = "posthoc-method"
        with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_exact_margin_boundaries(self):
        p, e = fixture()
        for row in e["endpoints"]:
            row["corrected_minus_carrier_ci"] = [-0.2, 0.2]
            row["gap_restoration_fraction_ci"] = [0.5, 1.1]
        self.assertEqual(self.assess(p, e)["status"], "contract_satisfied")

    def test_cli_success_hold_and_invalid(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "assess_correction_control.py"
        for mode, expected in (("success", 0), ("hold", 1), ("invalid", 2)):
            p, e = fixture()
            if mode == "hold": e["endpoints"][0]["gap_restoration_fraction_ci"] = [0.4, 1.1]
            if mode == "invalid": del p["specimens"]
            with tempfile.TemporaryDirectory() as temp:
                plan, evidence = Path(temp) / "plan.json", Path(temp) / "evidence.json"
                plan.write_text(json.dumps(p)); evidence.write_text(json.dumps(e))
                result = subprocess.run([sys.executable, str(script), "--plan", str(plan), "--evidence", str(evidence)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt["assessment_scope"], "correction_control_only")
                self.assertIs(receipt["legacy_pipeline_eligible"], False)

    def test_normal_function_axes_can_preserve_equivalence(self):
        p, e = fixture()
        for planned, observed in zip(p["endpoints"][2:], e["endpoints"][2:]):
            planned.update(role="preservation_equivalence", baseline_equivalence_bounds=[-0.2, 0.2])
            del planned["minimum_gap_restoration"]
            observed.update(mutant_mean=2, carrier_mean=2, corrected_mean=2,
                            mutant_minus_carrier_ci=[-0.1, 0.1], corrected_minus_carrier_ci=[-0.1, 0.1])
            del observed["oriented_mutant_to_carrier_gap_ci"]
            del observed["gap_restoration_fraction_ci"]
        e["plan_sha256"] = semantic_digest(p)
        self.assertEqual(self.assess(p, e)["status"], "contract_satisfied")
        e["endpoints"][2]["mutant_minus_carrier_ci"] = [-0.3, 0.1]
        self.assertEqual(self.assess(p, e)["status"], "hold")

    def test_instability_cannot_be_relabelled_preservation(self):
        for index in (0, 1):
            p, e = fixture(); p["endpoints"][index]["role"] = "preservation_equivalence"
            e["plan_sha256"] = semantic_digest(p)
            with self.assertRaises(CorrectionControlError): self.assess(p, e)
        p, e = fixture(); del p["endpoints"][2]["role"]
        e["plan_sha256"] = semantic_digest(p)
        with self.assertRaises(CorrectionControlError): self.assess(p, e)

    def test_receipt_binds_numeric_evidence(self):
        p, e = fixture(); first = self.assess(p, e)
        e["endpoints"][0]["gap_restoration_fraction_ci"] = [0.7, 1.1]
        second = self.assess(p, e)
        self.assertNotEqual(first["evidence_sha256"], second["evidence_sha256"])
        self.assertNotEqual(first["receipt_sha256"], second["receipt_sha256"])


if __name__ == "__main__": unittest.main()
