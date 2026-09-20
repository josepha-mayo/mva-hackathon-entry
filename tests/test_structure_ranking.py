from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.structure_ranking import (
    CLAIM_BOUNDARY,
    SCHEMA,
    StructureRankingError,
    assess_structure_ranking,
)


ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = ROOT / "templates" / "community"


def _table() -> dict:
    return json.loads((COMMUNITY / "structure_ranking.synthetic.json").read_text(encoding="utf-8"))


class StructureRankingTests(unittest.TestCase):
    def test_geometry_can_prioritize_an_assay_but_not_checkpoint(self) -> None:
        result = assess_structure_ranking(_table())
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["assay_priority"], "prioritize_assay")
        self.assertEqual(result["reason"], "exact_closer_to_analog")
        self.assertFalse(result["checkpoint_ready"])
        self.assertFalse(result["probe_eligible"])
        self.assertEqual(result["program_effect"], "pass")
        self.assertTrue(result["exact_claimed"])
        self.assertTrue(result["features_usable"])
        self.assertTrue(result["residue_ids_usable"])
        self.assertTrue(result["table_usable"])

    def test_predicted_stability_cannot_replace_an_assay(self) -> None:
        for method in ("foldx_alphafold", "alphamissense"):
            with self.subTest(method=method):
                table = _table()
                table["method"] = method
                result = assess_structure_ranking(table)
                self.assertEqual(result["status"], "not_assessable")
                self.assertEqual(result["program_effect"], "hold")
                self.assertEqual(result["assay_priority"], "similar")
                self.assertEqual(result["reason"], "method_cannot_replace_assay")
                self.assertFalse(result["checkpoint_ready"])

    def test_using_ranking_as_function_stops(self) -> None:
        table = _table()
        table["used_as_function"] = True
        result = assess_structure_ranking(table)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "ranking_is_not_an_assay")

    def test_analog_claimed_as_exact_stops(self) -> None:
        table = _table()
        for row in table["residues"]:
            if row["role"] == "analog_unstable":
                row["claimed_as_exact"] = True
        result = assess_structure_ranking(table)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "analog_as_exact_function")

    def test_exact_residue_must_be_claimed_as_exact(self) -> None:
        table = _table()
        for row in table["residues"]:
            if row["role"] == "exact":
                row["claimed_as_exact"] = False
        result = assess_structure_ranking(table)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "exact_claim_required")
        self.assertFalse(result["checkpoint_ready"])
        self.assertFalse(result["exact_claimed"])

    def test_out_of_range_features_cannot_prioritize(self) -> None:
        cases = (
            ("exact", "plddt", 900.0),
            ("exact", "rsa", 1.5),
            ("exact", "polar_contacts", -1),
            ("exact", "polar_contacts", 3.5),
            ("analog_unstable", "rsa", 2.0),
            ("nearby_benign", "plddt", -1.0),
        )
        for role, field, value in cases:
            with self.subTest(role=role, field=field, value=value):
                table = _table()
                for row in table["residues"]:
                    if row["role"] == role:
                        row[field] = value
                result = assess_structure_ranking(table)
                self.assertEqual(result["status"], "not_assessable")
                self.assertEqual(result["program_effect"], "hold")
                self.assertEqual(result["reason"], "ranking_features_unusable")
                self.assertEqual(result["assay_priority"], "similar")
                self.assertFalse(result["features_usable"])
                self.assertFalse(result["checkpoint_ready"])

    def test_oversized_integer_features_fail_controlled(self) -> None:
        table = _table()
        for row in table["residues"]:
            if row["role"] == "exact":
                row["plddt"] = 10 ** 400
        with self.assertRaisesRegex(StructureRankingError, "finite"):
            assess_structure_ranking(table)

    def test_duplicate_or_blank_residue_ids_cannot_prioritize(self) -> None:
        analog_id = next(
            row["residue_id"] for row in _table()["residues"] if row["role"] == "analog_unstable"
        )
        exact_id = next(
            row["residue_id"] for row in _table()["residues"] if row["role"] == "exact"
        )
        confusable = exact_id.replace("e", "е")
        assert confusable != exact_id and confusable.casefold() != exact_id.casefold()
        cases = (
            ("exact", analog_id),
            ("exact", analog_id.upper()),
            ("exact", ""),
            ("exact", confusable),
            ("nearby_benign", " syn-residue-benign"),
        )
        for role, residue_id in cases:
            with self.subTest(role=role, residue_id=residue_id):
                table = _table()
                for row in table["residues"]:
                    if row["role"] == role:
                        row["residue_id"] = residue_id
                result = assess_structure_ranking(table)
                self.assertEqual(result["status"], "not_assessable")
                self.assertEqual(result["program_effect"], "hold")
                self.assertEqual(result["reason"], "ranking_residue_ids_unusable")
                self.assertEqual(result["assay_priority"], "similar")
                self.assertFalse(result["residue_ids_usable"])
                self.assertFalse(result["checkpoint_ready"])

    def test_extra_residue_claimed_as_exact_stops(self) -> None:
        table = _table()
        table["residues"].append(
            {
                "residue_id": "syn-residue-extra",
                "role": "extra",
                "plddt": 90.0,
                "rsa": 0.2,
                "polar_contacts": 2,
                "claimed_as_exact": True,
            }
        )
        result = assess_structure_ranking(table)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "analog_as_exact_function")
        self.assertTrue(result["analog_as_exact"])
        self.assertFalse(result["table_usable"])

    def test_extra_residue_cannot_open_prioritization(self) -> None:
        table = _table()
        table["residues"].append(
            {
                "residue_id": "syn-residue-extra",
                "role": "extra",
                "plddt": 90.0,
                "rsa": 0.2,
                "polar_contacts": 2,
                "claimed_as_exact": False,
            }
        )
        result = assess_structure_ranking(table)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "ranking_table_unusable")
        self.assertFalse(result["table_usable"])
        self.assertFalse(result["checkpoint_ready"])

    def test_exact_closer_to_benign_deprioritizes(self) -> None:
        table = _table()
        for row in table["residues"]:
            if row["role"] == "exact":
                row["rsa"] = 0.44
                row["polar_contacts"] = 1
        result = assess_structure_ranking(table)
        self.assertEqual(result["assay_priority"], "deprioritize_assay")
        self.assertEqual(result["reason"], "exact_closer_to_benign")
        self.assertFalse(result["checkpoint_ready"])

    def test_low_plddt_cannot_prioritize(self) -> None:
        table = _table()
        for row in table["residues"]:
            if row["role"] == "exact":
                row["plddt"] = 40.0
        result = assess_structure_ranking(table)
        self.assertEqual(result["assay_priority"], "similar")
        self.assertEqual(result["reason"], "exact_geometry_unreliable")

    def test_missing_role_cannot_prioritize(self) -> None:
        table = _table()
        table["residues"] = [row for row in table["residues"] if row["role"] != "nearby_benign"]
        result = assess_structure_ranking(table)
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["program_effect"], "hold")
        self.assertEqual(result["reason"], "ranking_table_unusable")
        self.assertFalse(result["table_usable"])
        self.assertFalse(result["checkpoint_ready"])


if __name__ == "__main__":
    unittest.main()
