from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.evidence_ledger import load_evidence_ledger
from mva_hackathon.provenance import validate_public_manifest
from mva_hackathon.submission import load_predictions
from mva_hackathon.synthetic_pipeline import (
    OUTPUT_FILENAMES,
    SyntheticPipelineError,
    load_synthetic_bundle,
    run_synthetic_pipeline,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "synthetic-miniature-bundle.json"
CONFIG_DIR = ROOT / "configs" / "track1_slots"


class SyntheticPipelineTests(unittest.TestCase):
    def test_two_runs_are_byte_identical_and_every_artifact_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first = run_synthetic_pipeline(
                slot_config=CONFIG_DIR / "01-full-public-auto.json",
                synthetic_bundle=FIXTURE,
                output_dir=base / "first",
            )
            second = run_synthetic_pipeline(
                slot_config=CONFIG_DIR / "01-full-public-auto.json",
                synthetic_bundle=FIXTURE,
                output_dir=base / "second",
            )
            self.assertEqual({path.name for path in first.artifacts}, set(OUTPUT_FILENAMES))
            for name in OUTPUT_FILENAMES:
                with self.subTest(name=name):
                    self.assertEqual(
                        (first.output_dir / name).read_bytes(),
                        (second.output_dir / name).read_bytes(),
                    )

            predictions = load_predictions(first.output_dir / "submission.csv")
            ledger = load_evidence_ledger(
                first.output_dir / "evidence-ledger.json", public_only=True
            )
            provenance = json.loads(
                (first.output_dir / "provenance-runtime.json").read_text(encoding="utf-8")
            )
            report = json.loads(
                (first.output_dir / "report-input.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(predictions), 6)
            self.assertEqual(len(ledger.entries), len(predictions) + 1)
            self.assertEqual(validate_public_manifest(provenance), provenance)
            self.assertTrue(provenance["settings"]["determinism"]["timestamps_omitted"])
            self.assertEqual(report["counts"]["not_assessable_entries"], 1)
            self.assertIn("no biological causality", report["limitations"][2].lower())

    def test_all_six_declared_slots_apply_their_synthetic_ablation_switches(self) -> None:
        config_names = (
            "01-full-public-auto.json",
            "02-minus-phenotype.json",
            "03-novel-gene-mask.json",
            "04-exomiser-baseline.json",
            "05-vcf-only.json",
            "06-no-comphet-pairing.json",
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reports: list[dict[str, object]] = []
            for index, name in enumerate(config_names, start=1):
                run = run_synthetic_pipeline(
                    slot_config=CONFIG_DIR / name,
                    synthetic_bundle=FIXTURE,
                    output_dir=base / f"slot-{index}",
                )
                report = json.loads(
                    (run.output_dir / "report-input.json").read_text(encoding="utf-8")
                )
                reports.append(report)
                self.assertEqual(report["slot"]["number"], index)
                self.assertFalse(report["execution"]["controlled_content_used"])
                self.assertEqual(report["execution"]["network_access"], "disabled")

            full_components = reports[0]["ranking"][0]["score_components"]
            self.assertGreater(full_components["phenotype"], 0)
            self.assertGreater(full_components["orthogonal"], 0)
            self.assertGreater(full_components["gene_disease"], 0)

            self.assertTrue(
                all(row["score_components"]["phenotype"] == 0 for row in reports[1]["ranking"])
            )
            self.assertTrue(
                all(row["score_components"]["phenotype"] == 0 for row in reports[2]["ranking"])
            )
            self.assertTrue(
                all(row["score_components"]["gene_disease"] == 0 for row in reports[2]["ranking"])
            )
            for report in reports[3:5]:
                self.assertTrue(
                    all(row["score_components"]["orthogonal"] == 0 for row in report["ranking"])
                )
            self.assertEqual(
                reports[3]["slot"]["ranking_engine"], "synthetic-exomiser-surrogate"
            )
            self.assertTrue(
                all(
                    row["inheritance_model"] != "compound_heterozygous"
                    for row in reports[5]["ranking"]
                )
            )
            self.assertGreater(
                reports[5]["counts"]["generated_candidates"],
                reports[5]["counts"]["eligible_candidates"],
            )

    def test_bundle_rejects_non_synthetic_gene_and_unknown_fields(self) -> None:
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.json"
            source["alleles"][0]["gene"] = "".join(("R", "E", "A", "L", "1"))
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(SyntheticPipelineError, "SYN namespace"):
                load_synthetic_bundle(path)

            source = json.loads(FIXTURE.read_text(encoding="utf-8"))
            source["unexpected"] = True
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(SyntheticPipelineError, "fields must be exactly"):
                load_synthetic_bundle(path)

    def test_existing_output_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run_synthetic_pipeline(
                slot_config=CONFIG_DIR / "01-full-public-auto.json",
                synthetic_bundle=FIXTURE,
                output_dir=output,
            )
            original = {name: (output / name).read_bytes() for name in OUTPUT_FILENAMES}
            with self.assertRaisesRegex(SyntheticPipelineError, "overwrite is prohibited"):
                run_synthetic_pipeline(
                    slot_config=CONFIG_DIR / "02-minus-phenotype.json",
                    synthetic_bundle=FIXTURE,
                    output_dir=output,
                )
            self.assertEqual(
                original, {name: (output / name).read_bytes() for name in OUTPUT_FILENAMES}
            )

    def test_script_cli_runs_without_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli-run"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_synthetic_pipeline.py"),
                    "--slot-config",
                    str(CONFIG_DIR / "01-full-public-auto.json"),
                    "--synthetic-bundle",
                    str(FIXTURE),
                    "--output-dir",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("no biological validation or submission", completed.stdout)
            self.assertEqual({path.name for path in output.iterdir()}, set(OUTPUT_FILENAMES))


if __name__ == "__main__":
    unittest.main()
