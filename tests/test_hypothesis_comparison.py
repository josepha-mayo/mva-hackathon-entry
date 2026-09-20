from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.hypothesis_compare import (
    SCHEMA as COMPARE_SCHEMA,
    HypothesisComparisonError,
    compare_hypotheses,
)


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = json.loads(
    (ROOT / "templates" / "community" / "observed_inferred_unknown.synthetic.json")
    .read_text(encoding="utf-8")
)
STABILIZER = json.loads(
    (ROOT / "templates" / "hypotheses" / "proteostasis_stabilizer.synthetic.json")
    .read_text(encoding="utf-8")
)


class HypothesisComparisonTests(unittest.TestCase):
    def test_both_hypotheses_pass_independently(self) -> None:
        result = compare_hypotheses(
            {"chaperone_pair": CANONICAL, "proteostasis_stabilizer": STABILIZER}
        )
        comparison = result["hypotheses"]
        for name, row in comparison.items():
            with self.subTest(hypothesis=name):
                self.assertEqual(row["status"], "pass")
                self.assertEqual(row["reason"], "weakest_link_respected")
                # Identity links are still unknown, so the participant claim
                # is unsupported while the isogenic work ceiling allows the
                # declared experiment_to_run.
                self.assertEqual(row["child_claim_strength"], "unsupported")
                self.assertEqual(row["work_ceiling"], "experiment_to_run")

    def test_the_two_hypotheses_are_mechanistically_distinct(self) -> None:
        canonical_probe = next(
            link for link in CANONICAL["links"] if link["hypothesis_role"] == "probe"
        )
        stabilizer_probe = next(
            link for link in STABILIZER["links"] if link["hypothesis_role"] == "probe"
        )
        self.assertIn("chaperone", canonical_probe["statement"])
        self.assertIn("stabilizer", stabilizer_probe["statement"])
        self.assertNotIn("chaperone", stabilizer_probe["statement"])
        canonical_ids = {link["link_id"] for link in CANONICAL["links"]}
        stabilizer_ids = {link["link_id"] for link in STABILIZER["links"]}
        self.assertFalse(canonical_ids & stabilizer_ids)

    def test_the_gate_discriminates_a_weakened_competitor(self) -> None:
        weakened = copy.deepcopy(STABILIZER)
        for link in weakened["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "Under the predeclared rule: if the stabilizer probe does "
                    "not improve the exact-corrected endpoint amid selection, "
                    "batch, drift, or interference, the proteostasis "
                    "program stops."
                )
        comparison = compare_hypotheses(
            {"chaperone_pair": CANONICAL, "proteostasis_stabilizer": weakened}
        )["hypotheses"]
        self.assertEqual(comparison["chaperone_pair"]["status"], "pass")
        self.assertEqual(comparison["proteostasis_stabilizer"]["status"], "stop")
        self.assertEqual(
            comparison["proteostasis_stabilizer"]["reason"],
            "falsifier_without_boundary",
        )

    def test_comparison_module_reports_a_tied_lead_honestly(self) -> None:
        result = compare_hypotheses(
            {"chaperone_pair": CANONICAL, "proteostasis_stabilizer": STABILIZER}
        )
        self.assertEqual(result["schema"], COMPARE_SCHEMA)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["selection_rule"], "tied_no_lead")
        self.assertIsNone(result["lead_hypothesis"])
        self.assertEqual(
            sorted(result["passing_hypotheses"]),
            ["chaperone_pair", "proteostasis_stabilizer"],
        )

    def test_comparison_requires_at_least_two_tables(self) -> None:
        with self.assertRaises(HypothesisComparisonError):
            compare_hypotheses({"chaperone_pair": CANONICAL})

    def test_comparison_stop_when_no_hypothesis_survives(self) -> None:
        weakened = copy.deepcopy(STABILIZER)
        weakened["links"] = [
            link
            for link in weakened["links"]
            if link["hypothesis_role"] != "falsifier"
        ]
        other = copy.deepcopy(CANONICAL)
        other["links"] = [
            link
            for link in other["links"]
            if link["hypothesis_role"] != "falsifier"
        ]
        result = compare_hypotheses(
            {"chaperone_pair": other, "proteostasis_stabilizer": weakened}
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["selection_rule"], "no_surviving_hypothesis")
        self.assertEqual(result["passing_hypotheses"], [])

    def test_comparison_report_artifact_documents_both_hypotheses(self) -> None:
        report = (ROOT / "reports" / "TRACK2_HYPOTHESIS_COMPARISON.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("chaperone_pair", report)
        self.assertIn("proteostasis_stabilizer", report)
        self.assertIn("tied_no_lead", report)
        self.assertIn("fixture sha256", report)

    def test_unkillable_alternative_sinks_only_its_own_hypothesis(self) -> None:
        weakened = copy.deepcopy(STABILIZER)
        for link in weakened["links"]:
            if link["link_id"] == "syn2-link-alternative-batch":
                link["statement"] = (
                    "Overgrowth of the endpoint row could look like a probe "
                    "gain rather than restored missense abundance."
                )
        comparison = compare_hypotheses(
            {"chaperone_pair": CANONICAL, "proteostasis_stabilizer": weakened}
        )["hypotheses"]
        self.assertEqual(comparison["chaperone_pair"]["status"], "pass")
        self.assertEqual(comparison["proteostasis_stabilizer"]["status"], "stop")
        self.assertEqual(
            comparison["proteostasis_stabilizer"]["reason"],
            "alternative_not_killable",
        )


if __name__ == "__main__":
    unittest.main()
