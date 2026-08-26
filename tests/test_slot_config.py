from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.slot_config import (
    EXPECTED_VARIANTS,
    METHODS,
    SlotConfig,
    SlotConfigError,
    load_slot_plan,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs" / "track1_slots" / "plan.json"


class SlotConfigTests(unittest.TestCase):
    def test_plan_loads_exact_six_predeclared_methods(self) -> None:
        configs = load_slot_plan(PLAN)
        self.assertEqual(tuple(config.method_id for config in configs), METHODS)
        self.assertEqual(tuple(config.slot for config in configs), (1, 2, 3, 4, 5, 6))
        self.assertTrue(all(config.network_access == "disabled" for config in configs))
        self.assertTrue(
            all(config.leaderboard_adaptation == "prohibited" for config in configs)
        )
        self.assertTrue(all(config.manual_candidate_injection is False for config in configs))

    def test_each_slot_matches_its_predeclared_ablation_vector(self) -> None:
        for config in load_slot_plan(PLAN):
            actual = (
                config.phenotype_mode,
                config.gene_disease_knowledge,
                config.ranking_backend,
                config.input_evidence,
                config.compound_heterozygous_pairing,
            )
            self.assertEqual(actual, EXPECTED_VARIANTS[config.method_id])

    def test_wrong_slot_and_ambiguous_ablation_fail_closed(self) -> None:
        source = json.loads((PLAN.parent / "01-full-public-auto.json").read_text())
        wrong_slot = dict(source, slot=2)
        with self.assertRaisesRegex(SlotConfigError, "wrong predeclared slot"):
            SlotConfig.from_dict(wrong_slot)
        ambiguous = dict(source, phenotype_mode="disabled")
        with self.assertRaisesRegex(SlotConfigError, "predeclared ablation"):
            SlotConfig.from_dict(ambiguous)

    def test_unsafe_shared_policy_fails_closed(self) -> None:
        source = json.loads((PLAN.parent / "01-full-public-auto.json").read_text())
        mutations = {
            "resource_scope": "hosted-service",
            "execution_mode": "manual",
            "manual_candidate_injection": True,
            "network_access": "enabled",
            "leaderboard_adaptation": "allowed",
            "tool_lock_policy": "latest",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                candidate = dict(source, **{field: value})
                with self.assertRaisesRegex(SlotConfigError, field):
                    SlotConfig.from_dict(candidate)

    def test_plan_rejects_path_escape(self) -> None:
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        plan["config_files"][0] = "../01-full-public-auto.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(SlotConfigError, "unsafe config filename"):
                load_slot_plan(path)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        payload = (
            '{"schema":"mva.track1-slot-config/v1","slot":1,"slot":2,'
            '"method_id":"full-public-auto","scientific_question":"A long enough question for a synthetic test.",'
            '"resource_scope":"public_offline_only","execution_mode":"fully_automated",'
            '"phenotype_mode":"enabled","gene_disease_knowledge":"enabled",'
            '"ranking_backend":"integrated_public_auto",'
            '"input_evidence":"full_prespecified_local_evidence",'
            '"compound_heterozygous_pairing":"enabled","manual_candidate_injection":false,'
            '"network_access":"disabled","leaderboard_adaptation":"prohibited",'
            '"tool_lock_policy":"version_and_digest_required_before_execution"}'
        )
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "01-full-public-auto.json").write_text(payload, encoding="utf-8")
            for name in plan["config_files"][1:]:
                source = PLAN.parent / name
                (root / name).write_bytes(source.read_bytes())
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(SlotConfigError, "duplicate JSON key"):
                load_slot_plan(plan_path)

    def test_public_scaffold_has_no_hpo_bundle_or_candidate_coordinate_literals(self) -> None:
        paths = list(PLAN.parent.glob("*.json")) + [
            ROOT / "templates" / "track1_evidence_ledger.synthetic.json"
        ]
        hpo = re.compile(r"\bHP:\d{7}\b")
        coordinate = re.compile(r"\bchr(?:[1-9]|1\d|2[0-2]|X|Y|M|MT):\d+\b", re.I)
        for path in paths:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(hpo.search(text))
                self.assertIsNone(coordinate.search(text))


if __name__ == "__main__":
    unittest.main()
