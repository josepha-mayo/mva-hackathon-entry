from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from mva_hackathon.generation_selection import GenerationSelectionError, run_benchmark
from mva_hackathon.seed_sensitivity import (
    MAX_SEEDS,
    SCHEMA,
    load_and_run_seed_sweep,
    load_sweep_config,
    run_seed_sweep,
    validate_sweep_config,
)

BASE_CONFIG = ROOT / "configs" / "track2-generation-selection-benchmark.json"
SWEEP_CONFIG = ROOT / "configs" / "track2-seed-sensitivity.json"


def _base() -> dict:
    return json.loads(BASE_CONFIG.read_text(encoding="utf-8"))


def _sweep(**overrides) -> dict:
    config = {"schema": SCHEMA, "seeds": [17032027], "acceptance": {"min_accepting_seeds": 1}}
    config.update(overrides)
    return config


def _mini_base() -> dict:
    """Cheap config: tiny replicate count so sweep tests run in seconds."""
    base = _base()
    base["monte_carlo_replicates"] = 8
    return base


class SeedSensitivityConfigTests(unittest.TestCase):
    def test_checked_in_config_is_valid(self) -> None:
        config = load_sweep_config(SWEEP_CONFIG)
        self.assertEqual(len(config["seeds"]), 5)
        self.assertEqual(config["acceptance"]["min_accepting_seeds"], 5)

    def test_seeds_are_distinct_from_primary(self) -> None:
        config = load_sweep_config(SWEEP_CONFIG)
        primary = _base()["seed"]
        self.assertNotIn(primary, config["seeds"])

    def test_rejects_duplicate_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.json"
            path.write_text(json.dumps(_sweep(seeds=[7, 7])), encoding="utf-8")
            with self.assertRaises(GenerationSelectionError):
                load_sweep_config(path)

    def test_rejects_non_list_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.json"
            path.write_text(json.dumps(_sweep(seeds="17032027")), encoding="utf-8")
            with self.assertRaises(GenerationSelectionError):
                load_sweep_config(path)

    def test_rejects_negative_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.json"
            path.write_text(json.dumps(_sweep(seeds=[-1])), encoding="utf-8")
            with self.assertRaises(GenerationSelectionError):
                load_sweep_config(path)

    def test_rejects_min_accepting_above_seed_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.json"
            path.write_text(
                json.dumps(_sweep(seeds=[1], acceptance={"min_accepting_seeds": 2})),
                encoding="utf-8",
            )
            with self.assertRaises(GenerationSelectionError):
                load_sweep_config(path)

    def test_rejects_unknown_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.json"
            extra = _sweep()
            extra["surprise"] = True
            path.write_text(json.dumps(extra), encoding="utf-8")
            with self.assertRaises(GenerationSelectionError):
                load_sweep_config(path)

    def test_rejects_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.json"
            path.write_text(json.dumps(_sweep(schema="other/v9")), encoding="utf-8")
            with self.assertRaises(GenerationSelectionError):
                load_sweep_config(path)

    def test_rejects_empty_seeds(self) -> None:
        with self.assertRaises(GenerationSelectionError):
            validate_sweep_config(_sweep(seeds=[]))

    def test_rejects_too_many_seeds(self) -> None:
        with self.assertRaises(GenerationSelectionError):
            validate_sweep_config(_sweep(seeds=list(range(MAX_SEEDS + 1))))

    def test_rejects_zero_min_accepting(self) -> None:
        with self.assertRaises(GenerationSelectionError):
            validate_sweep_config(
                _sweep(seeds=[1], acceptance={"min_accepting_seeds": 0})
            )

    def test_rejects_non_integer_seeds(self) -> None:
        for bad in (1.5, True, "7"):
            with self.assertRaises(GenerationSelectionError):
                validate_sweep_config(_sweep(seeds=[bad]))


class SeedSensitivityRunTests(unittest.TestCase):
    def test_sweep_aggregates_per_seed_outcomes(self) -> None:
        base = _mini_base()
        sha = hashlib.sha256(json.dumps(base).encode()).hexdigest()
        receipt = run_seed_sweep(_sweep(seeds=[17032027]), base, sha)
        self.assertEqual(receipt["schema"], SCHEMA)
        self.assertTrue(receipt["synthetic_only"])
        self.assertEqual(receipt["primary_seed"], base["seed"])
        self.assertEqual(receipt["base_config_sha256"], sha)
        self.assertEqual(len(receipt["per_seed"]), 1)
        row = receipt["per_seed"][0]
        self.assertEqual(row["seed"], 17032027)
        self.assertEqual(row["scenarios_total"], len(base["scenarios"]))
        self.assertIn("acceptance_passed", row)
        self.assertIn("maximum_false_generation_wilson_upper_per_required_confound", row)
        self.assertIn("metric_ranges", receipt)
        self.assertIn("acceptance_passed", receipt["summary"])

    def test_sweep_fails_closed_when_a_seed_rejects(self) -> None:
        base = _mini_base()
        # Sabotage a guaranteed-unattainable acceptance bound so the run rejects.
        sabotaged = copy.deepcopy(base)
        sabotaged["acceptance"] = dict(base["acceptance"])
        sabotaged["acceptance"]["minimum_generation_detection_wilson_lower"] = 0.9999999
        receipt = run_seed_sweep(
            _sweep(seeds=[17032027, 17032028], acceptance={"min_accepting_seeds": 2}),
            sabotaged,
            "0" * 64,
        )
        rejected = sum(1 for r in receipt["per_seed"] if r["acceptance_passed"] is False)
        self.assertGreater(rejected, 0)
        self.assertFalse(receipt["summary"]["acceptance_passed"])
        self.assertEqual(
            receipt["summary"]["seeds_accepted"],
            receipt["summary"]["seeds_run"] - rejected,
        )

    def test_rejects_seed_equal_to_primary(self) -> None:
        base = _mini_base()
        with self.assertRaises(GenerationSelectionError):
            run_seed_sweep(_sweep(seeds=[base["seed"]]), base, "0" * 64)

    def test_run_validates_unvalidated_config(self) -> None:
        base = _mini_base()
        # Direct in-process callers must not bypass the schema gate: an empty
        # seed list or a vacuous acceptance floor must raise, not accept.
        with self.assertRaises(GenerationSelectionError):
            run_seed_sweep(_sweep(seeds=[]), base, "0" * 64)
        with self.assertRaises(GenerationSelectionError):
            run_seed_sweep(
                _sweep(seeds=[17032027], acceptance={"min_accepting_seeds": 0}),
                base,
                "0" * 64,
            )

    def test_deterministic_across_identical_runs(self) -> None:
        base = _mini_base()
        a = run_seed_sweep(_sweep(seeds=[17032027, 17032028]), base, "x")
        b = run_seed_sweep(_sweep(seeds=[17032027, 17032028]), base, "x")
        self.assertEqual(a, b)

    def test_checked_in_receipt_is_internally_consistent(self) -> None:
        receipt_path = ROOT / "reports" / "TRACK2_SEED_SENSITIVITY.json"
        if not receipt_path.exists():
            self.skipTest("sensitivity receipt not yet minted")
        committed = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(committed["schema"], SCHEMA)
        self.assertTrue(committed["synthetic_only"])
        self.assertEqual(committed["supplementary_seeds"], load_sweep_config(SWEEP_CONFIG)["seeds"])
        base_bytes = BASE_CONFIG.read_bytes()
        self.assertEqual(
            committed["base_config_sha256"], hashlib.sha256(base_bytes).hexdigest()
        )
        per_seed = committed["per_seed"]
        self.assertEqual(len(per_seed), committed["summary"]["seeds_run"])
        self.assertEqual(
            committed["summary"]["seeds_accepted"],
            sum(1 for row in per_seed if row["acceptance_passed"] is True),
        )
        self.assertEqual(
            committed["summary"]["acceptance_passed"],
            committed["summary"]["seeds_accepted"]
            >= committed["summary"]["min_accepting_seeds"],
        )
        for key in (
            "maximum_false_generation_wilson_upper_per_required_confound",
            "minimum_required_generation_detection_wilson_lower",
        ):
            self.assertEqual(
                committed["metric_ranges"][key]["min"],
                min(r[key] for r in per_seed),
            )
            self.assertEqual(
                committed["metric_ranges"][key]["max"],
                max(r[key] for r in per_seed),
            )


if __name__ == "__main__":
    unittest.main()
