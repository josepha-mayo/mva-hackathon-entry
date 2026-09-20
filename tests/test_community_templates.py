from __future__ import annotations

import dataclasses
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.clone_safety import assess_clone_safety
from mva_hackathon.generation_selection import ObservedRun
from mva_hackathon.lineage import CLAIM_BOUNDARY, FORBIDDEN_ANALYST_KEYS

ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = ROOT / "templates" / "community"

EXPECTED_NAMES = frozenset(
    {
        "README.md",
        "phase_record.synthetic.json",
        "allele_function_scorecard.synthetic.json",
        "measured_exposure_table.synthetic.json",
        "blinded_count_table.synthetic.json",
        "replication_decision.synthetic.json",
        "observed_inferred_unknown.synthetic.json",
        "family_plain_language.synthetic.md",
        "causal_chain_worksheet.synthetic.json",
        "lineage_count_table.synthetic.json",
        "clone_safety_table.synthetic.json",
        "confirmation_record.synthetic.json",
        "transcript_record.synthetic.json",
        "structure_ranking.synthetic.json",
        "assay_power.synthetic.json",
        "coordinate_model.synthetic.pdb",
    }
)
JSON_NAMES = frozenset(name for name in EXPECTED_NAMES if name.endswith(".json"))
JSON_TOP_LEVEL = {
    "phase_record.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "gate_id",
            "alleles",
            "interval_bp",
            "guide_configurations",
            "molecule_counts",
            "decision",
            "phase_method",
            "phase_specimen",
            "confidence_bound",
            "allelic_dropout_criterion",
            "notes",
        }
    ),
    "allele_function_scorecard.synthetic.json": frozenset(
        {"schema", "privacy_class", "purpose", "endpoints", "rows"}
    ),
    "measured_exposure_table.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "probe_id",
            "endpoint_class",
            "success_rule",
            "note",
            "preexposure_allocation",
            "vehicle_controls",
            "columns",
            "rows",
        }
    ),
    "blinded_count_table.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "observed_run_fields",
            "runs",
        }
    ),
    "replication_decision.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "site_id",
            "originating_site_id",
            "endpoints_concordant",
            "clone_safety_stop",
            "exposure_gate_passed",
            "decision",
            "rationale",
        }
    ),
    "observed_inferred_unknown.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "declared_overall_strength",
            "declared_probe_is_medicine",
            "status_vocabulary",
            "links",
        }
    ),
    "causal_chain_worksheet.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "owner_lab_roles",
            "declared_next_gate_id",
            "gates",
        }
    ),
    "lineage_count_table.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "study_id",
            "synthetic_only",
            "lock_state",
            "blinded",
            "allocation_id",
            "forbidden_keys_absent",
            "claim_boundary",
            "runs",
        }
    ),
    "clone_safety_table.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "synthetic_only",
            "claim_boundary",
            "ratio_stop",
            "death_ratio_stop",
            "minimum_resolved",
            "status",
            "program_effect",
            "clone_safety_stop",
            "advancement_blocked",
            "source_fingerprint",
            "nests",
        }
    ),
    "confirmation_record.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "specimen_identity_resolved",
            "second_aliquot",
            "layout_complete",
            "both_strands_counted",
            "allele_1_status",
            "allele_2_status",
            "declared_status",
            "producer",
            "library_molecule",
            "confirmation_specimen",
        }
    ),
    "transcript_record.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "stop_allele_rna",
            "missense_allele_rna",
            "declared_status",
            "transcript_method",
            "transcript_specimen",
        }
    ),
    "structure_ranking.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "synthetic_only",
            "method",
            "used_as_function",
            "residues",
        }
    ),
    "assay_power.synthetic.json": frozenset(
        {
            "schema",
            "privacy_class",
            "purpose",
            "locked",
            "n_edit_events",
            "n_clones_per_event",
            "n_opportunities",
            "locked_vehicle_error_rate",
            "locked_treatment_error_rate",
            "locked_vehicle_completion_rate",
            "locked_treatment_completion_rate",
            "minimum_detection",
            "remaining_population_doublings",
            "endpoint_class",
            "success_rule",
        }
    ),
}
DECISIONS = frozenset({"trans_confirmed", "cis_confirmed", "unresolved"})
ASSESSMENT_STATUSES = frozenset({"positive", "negative", "not_assessable"})
EVIDENCE_STATUSES = frozenset(
    {
        "observed",
        "inferred",
        "unknown",
        "hypothesis",
        "synthetic_test",
        "planned_experiment",
    }
)
OWNER_LABS = frozenset(
    {
        "clinical_genetics",
        "editing",
        "proteomics",
        "imaging",
        "statistics",
        "oncology",
    }
)
SITE_DECISIONS = frozenset({"hold", "advance", "stop"})


class CommunityTemplateTests(unittest.TestCase):
    def test_expected_files_exist_and_nothing_else(self) -> None:
        self.assertTrue(COMMUNITY.is_dir())
        names = {path.name for path in COMMUNITY.iterdir()}
        self.assertEqual(names, EXPECTED_NAMES)

    def test_json_templates_load(self) -> None:
        for name in sorted(JSON_NAMES):
            path = COMMUNITY / name
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(payload, dict)
            self.assertEqual(payload.get("privacy_class"), "synthetic")
            self.assertEqual(set(payload), JSON_TOP_LEVEL[name])

    def test_phase_record_uses_synthetic_alleles(self) -> None:
        payload = json.loads(
            (COMMUNITY / "phase_record.synthetic.json").read_text(encoding="utf-8")
        )
        alleles = payload["alleles"]
        self.assertEqual(len(alleles), 2)
        self.assertTrue(all(item.startswith("SYN-") for item in alleles))
        self.assertIn(payload["decision"], DECISIONS)
        self.assertEqual(payload["phase_method"], "molecule_spanning")
        self.assertEqual(payload["phase_specimen"], "assay_matched")
        self.assertIn("interval_bp", payload)
        self.assertIn("molecule_counts", payload)
        self.assertIn("guide_configurations", payload)
        for guide in payload["guide_configurations"]:
            self.assertIn(guide["linkage_call"], {"trans", "cis", "unresolved"})
        self.assertIn("confidence_bound", payload)
        self.assertIn("allelic_dropout_criterion", payload)

    def test_scorecard_rows_and_statuses(self) -> None:
        payload = json.loads(
            (COMMUNITY / "allele_function_scorecard.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        classes = [row["genotype_class"] for row in payload["rows"]]
        self.assertEqual(
            classes,
            [
                "wt",
                "missense",
                "stop",
                "missense_carrier",
                "missense_at_abundance",
                "compound",
                "exact_corrected",
                "recreated_missense",
            ],
        )
        missense = next(row for row in payload["rows"] if row["genotype_class"] == "missense")
        self.assertEqual(missense["allele_specificity"], "exact")
        corrected = next(
            row for row in payload["rows"] if row["genotype_class"] == "exact_corrected"
        )
        self.assertEqual(corrected["allele_specificity"], "exact")
        recreated = next(
            row for row in payload["rows"] if row["genotype_class"] == "recreated_missense"
        )
        self.assertEqual(recreated["allele_specificity"], "exact")
        for row in payload["rows"]:
            self.assertTrue(str(row["genotype_id"]).startswith("syn-"))
            endpoints = [item["endpoint"] for item in row["assessments"]]
            self.assertEqual(endpoints, payload["endpoints"])
            for item in row["assessments"]:
                self.assertIn(item["assessment_status"], ASSESSMENT_STATUSES)
                self.assertIn(item["assay_class"], {"wet", "unlabeled"})
                if item["assessment_status"] == "positive":
                    self.assertEqual(item.get("condition_class", "unlabeled"), "basal")
                    self.assertEqual(item.get("system_class", "unlabeled"), "cellular")
                    self.assertEqual(item.get("expression_class", "unlabeled"), "endogenous")
                    self.assertEqual(item.get("specimen_class", "unlabeled"), "assay_matched")
                if row["genotype_class"] == "exact_corrected" and item[
                    "assessment_status"
                ] == "negative":
                    self.assertEqual(item.get("condition_class", "unlabeled"), "basal")
                    self.assertEqual(item.get("system_class", "unlabeled"), "cellular")
                    self.assertEqual(item.get("expression_class", "unlabeled"), "endogenous")
                    self.assertEqual(item.get("specimen_class", "unlabeled"), "assay_matched")

    def test_count_table_maps_to_observed_run(self) -> None:
        payload = json.loads(
            (COMMUNITY / "blinded_count_table.synthetic.json").read_text(encoding="utf-8")
        )
        expected = [field.name for field in dataclasses.fields(ObservedRun)]
        self.assertEqual(payload["observed_run_fields"], expected)
        arms: set[str] = set()
        events: set[int] = set()
        for row in payload["runs"]:
            self.assertEqual(set(row), set(expected))
            ObservedRun(**row)
            arms.add(row["arm"])
            events.add(row["edit_event_id"])
        self.assertEqual(arms, {"vehicle", "treatment"})
        self.assertEqual(events, {1, 2, 3})

    def test_lineage_count_table_keeps_pre_division_death(self) -> None:
        payload = json.loads(
            (COMMUNITY / "lineage_count_table.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["schema"], "mva-track2-lineage-counts/v1")
        self.assertEqual(payload["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(
            set(payload["forbidden_keys_absent"]), FORBIDDEN_ANALYST_KEYS
        )
        required = {
            "arm",
            "edit_event_id",
            "clone_id",
            "run_id",
            "batch_id",
            "functional_execution_id",
            "exposure_support_record_id",
            "exposure_profile_id",
            "exposure_probe_id",
            "exposure_started_at",
            "endpoint_recorded_at",
            "allocation_block_id",
            "functional_assay_plate_id",
            "plate_row",
            "plate_column",
            "dosing_order",
            "acquisition_order",
            "opportunities",
            "detected_divisions",
            "event_positive_divisions",
            "event_negative_divisions",
            "event_positive_daughters_followed",
            "event_positive_daughters_reproduced",
            "event_positive_daughters_died",
            "event_negative_daughters_followed",
            "event_negative_daughters_reproduced",
            "event_negative_daughters_died",
            "pre_division_death",
            "no_division",
            "dropout_censored",
            "latest_enrolled_at",
        }
        deaths = 0
        for row in payload["runs"]:
            self.assertEqual(set(row), required)
            self.assertIsInstance(row["edit_event_id"], str)
            deaths += row["pre_division_death"]
            self.assertEqual(
                row["detected_divisions"]
                + row["pre_division_death"]
                + row["no_division"]
                + row["dropout_censored"],
                row["opportunities"],
            )
            self.assertEqual(
                row["event_positive_divisions"] + row["event_negative_divisions"],
                row["detected_divisions"],
            )
            self.assertLessEqual(
                row["event_positive_daughters_followed"],
                2 * row["event_positive_divisions"],
            )
            self.assertLessEqual(
                row["event_positive_daughters_reproduced"],
                row["event_positive_daughters_followed"],
            )
        lineage_schema = json.loads(
            (ROOT / "schemas" / "track2_lineage_counts.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(
            list(Draft202012Validator(lineage_schema).iter_errors(payload))
        )
        self.assertGreater(deaths, 0)
        clone_safety = assess_clone_safety(
            {
                key: payload[key]
                for key in (
                    "schema",
                    "synthetic_only",
                    "lock_state",
                    "blinded",
                    "allocation_id",
                    "runs",
                )
            }
        )
        self.assertEqual(clone_safety["status"], "not_assessable")
        self.assertFalse(clone_safety["clone_safety_stop"])
        self.assertTrue(clone_safety["advancement_blocked"])

    def test_clone_safety_template_matches_assessor(self) -> None:
        payload = json.loads(
            (COMMUNITY / "clone_safety_table.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        runs = []
        for nest in payload["nests"]:
            for arm, followed_key, reproduced_key in (
                ("vehicle", "vehicle_followed", "vehicle_reproduced"),
                ("treatment", "treatment_followed", "treatment_reproduced"),
            ):
                runs.append(
                    {
                        "arm": arm,
                        "edit_event_id": nest["edit_event_id"],
                        "clone_id": nest["clone_id"],
                        "run_id": nest["run_id"],
                        "event_positive_divisions": 5,
                        "event_negative_divisions": 5,
                        "event_positive_daughters_followed": nest[followed_key],
                        "event_positive_daughters_reproduced": nest[reproduced_key],
                        # Resolved-complete reconstruction: every followed
                        # daughter carries a terminal fate.
                        "event_positive_daughters_died": (
                            nest[followed_key] - nest[reproduced_key]
                        ),
                        "event_negative_daughters_followed": nest[
                            f"{arm}_negative_followed"
                        ],
                        "event_negative_daughters_reproduced": nest[
                            f"{arm}_negative_reproduced"
                        ],
                        "event_negative_daughters_died": nest[
                            f"{arm}_negative_died"
                        ],
                    }
                )
        result = assess_clone_safety(
            {
                "schema": "mva-track2-lineage-counts/v1",
                "synthetic_only": True,
                "lock_state": "locked",
                "blinded": True,
                "runs": runs,
            }
        )
        self.assertEqual(result["status"], payload["status"])
        self.assertEqual(result["clone_safety_stop"], payload["clone_safety_stop"])
        self.assertEqual(result["advancement_blocked"], payload["advancement_blocked"])
        self.assertEqual(
            [item["status"] for item in result["nests"]],
            [item["status"] for item in payload["nests"]],
        )
        clone_schema = json.loads(
            (ROOT / "schemas" / "track2_clone_safety.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(
            list(Draft202012Validator(clone_schema).iter_errors(payload))
        )

    def test_replication_and_chain_vocabularies(self) -> None:
        replication = json.loads(
            (COMMUNITY / "replication_decision.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("site_id", replication)
        self.assertIn("originating_site_id", replication)
        self.assertNotEqual(replication["site_id"], replication["originating_site_id"])
        self.assertIsInstance(replication["endpoints_concordant"], bool)
        self.assertIsInstance(replication["clone_safety_stop"], bool)
        self.assertIsInstance(replication["exposure_gate_passed"], bool)
        self.assertIn(replication["decision"], SITE_DECISIONS)

        chain = json.loads(
            (COMMUNITY / "causal_chain_worksheet.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(set(chain["owner_lab_roles"]), OWNER_LABS)
        orders = [gate["order"] for gate in chain["gates"]]
        self.assertEqual(orders, list(range(1, len(orders) + 1)))
        self.assertEqual({gate["owner_lab"] for gate in chain["gates"]}, OWNER_LABS)
        self.assertEqual(chain["declared_next_gate_id"], "syn-gate-confirm")

        links = json.loads(
            (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(set(links["status_vocabulary"]), EVIDENCE_STATUSES)
        self.assertEqual({row["status"] for row in links["links"]}, EVIDENCE_STATUSES)

    def test_family_worksheet_has_blanks(self) -> None:
        text = (COMMUNITY / "family_plain_language.synthetic.md").read_text(
            encoding="utf-8"
        )
        for token in ("[result]", "[next gate]", "[what this does not mean]"):
            self.assertIn(token, text)

    def test_shipped_json_has_no_duplicate_keys_or_nonfinite_values(self) -> None:
        def _reject_duplicates(pairs: list) -> dict:
            seen: set = set()
            out: dict = {}
            for key, value in pairs:
                if key in seen:
                    raise ValueError(f"duplicate JSON key {key!r}")
                seen.add(key)
                out[key] = value
            return out

        def _reject_constant(value: str) -> None:
            raise ValueError(f"non-finite JSON constant {value}")

        roots = (ROOT / "templates", ROOT / "schemas")
        checked = 0
        for root in roots:
            for path in sorted(root.rglob("*.json")):
                json.loads(
                    path.read_text(encoding="utf-8"),
                    object_pairs_hook=_reject_duplicates,
                    parse_constant=_reject_constant,
                )
                checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
