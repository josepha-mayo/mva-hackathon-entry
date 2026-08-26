from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_phen2gene_development.py"
SPEC = importlib.util.spec_from_file_location("phen2gene_development_adapter", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load development adapter")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


class SyntheticPhen2GeneFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "official-source"
        self.repo.mkdir()
        (self.repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        (self.repo / "phen2gene.py").write_text(
            "from collections import OrderedDict\n"
            "def results(kb, manuals=None, weight_model=None, verbosity=False, cl=True):\n"
            "    genes = OrderedDict([\n"
            "        ('SYNTRUTH', (None, 1.0, 'SeedGene')),\n"
            "        ('SYNDISTRACTOR', (None, 0.5, 'Predicted')),\n"
            "    ])\n"
            "    return genes, 'synthetic diagnostic', weight_model\n",
            encoding="utf-8",
        )
        git(self.repo, "init", "-q")
        git(self.repo, "add", ".gitignore", "phen2gene.py")
        git(
            self.repo,
            "-c",
            "user.name=Synthetic Test",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "synthetic fixture",
        )
        self.commit = git(self.repo, "rev-parse", "HEAD")
        self.source_tree = git(self.repo, "rev-parse", "HEAD^{tree}")

        self.kb = root / "knowledge"
        for directory in ("Knowledgebase", "weights", "skewness"):
            target = self.kb / directory
            target.mkdir(parents=True)
            (target / "synthetic.txt").write_text(
                f"synthetic {directory}\n", encoding="utf-8"
            )
        self.tree = adapter.knowledge_tree_receipt(self.kb)
        self.kb_archive = root / "knowledge-release.bin"
        self.kb_archive.write_bytes(b"synthetic public knowledge release")

        self.phenopacket_archive = root / "public-phenopackets.zip"
        packet = {
            "phenotypicFeatures": [
                {"type": {"id": "HP:0000001"}},
                {"type": {"id": "HP:0000002"}},
                {"type": {"id": "HP:0000002"}, "excluded": True},
            ]
        }
        with zipfile.ZipFile(self.phenopacket_archive, "w") as archive:
            archive.writestr("synthetic/case.json", json.dumps(packet))

        self.salt_segments = ["mva", "pps", "0.1.27", "v1"]
        self.development_identifier = self._identifier_for("development")
        self.selector = root / "development-selector.json"
        self.selector_value = {
            "split": "development_smoke",
            "cases": [
                {
                    "hgnc_id": self.development_identifier,
                    "archive_path": "synthetic/case.json",
                    "truth_gene": "SYNTRUTH",
                }
            ],
        }
        write_json(self.selector, self.selector_value)

        self.config = root / "config.json"
        self.config_value = {
            "schema": adapter.CONFIG_SCHEMA,
            "scope": "public development only; synthetic contract test",
            "official_source": {
                "repository": "https://example.invalid/official-source",
                "commit": self.commit,
                "tree": self.source_tree,
                "license": "MIT License",
            },
            "knowledge_base": {
                "release": "synthetic",
                "release_url": "https://example.invalid/knowledge-release",
                "asset_url": "https://example.invalid/knowledge-release.bin",
                "asset_bytes": self.kb_archive.stat().st_size,
                "asset_sha256": file_sha256(self.kb_archive),
                **self.tree,
                "knowledge_date": "synthetic",
                "redistribution": "synthetic fixture only",
            },
            "public_input": {
                "repository": "https://example.invalid/public-input",
                "release": "synthetic",
                "release_url": "https://example.invalid/public-input/release",
                "tag_commit": "synthetic",
                "archive_url": "https://example.invalid/public-input.zip",
                "archive_bytes": self.phenopacket_archive.stat().st_size,
                "archive_sha256": file_sha256(self.phenopacket_archive),
                "license": "synthetic fixture only",
                "selector_sha256": file_sha256(self.selector),
                "case_count": 1,
                "unique_gene_count": 1,
                "split_salt_segments": self.salt_segments,
                "uppercase_first_two_salt_segments": True,
                "development_basis_points": 6000,
                "calibration_basis_points": 2000,
                "test_basis_points": 2000,
            },
            "evaluation": {
                "weight_model": "sk",
                "minimum_positive_hpo_terms": 2,
                "candidate_gene_list": None,
                "negative_hpo_policy": (
                    "omit excluded terms because Phen2Gene accepts positive terms only"
                ),
                "bootstrap_seed": 7,
                "bootstrap_replicates": 100,
                "rank_semantics": "synthetic ordered result position",
            },
        }
        write_json(self.config, self.config_value)

    def _identifier_for(self, split: str) -> str:
        for index in range(10_000):
            candidate = f"SYN-ID-{index}"
            if adapter.split_for_identifier(candidate, self.salt_segments) == split:
                return candidate
        raise AssertionError("could not construct a synthetic split identifier")

    def rewrite_selector(self, identifier: str, *, refresh_pin: bool) -> None:
        self.selector_value["cases"][0]["hgnc_id"] = identifier
        write_json(self.selector, self.selector_value)
        if refresh_pin:
            self.config_value["public_input"]["selector_sha256"] = file_sha256(
                self.selector
            )
            write_json(self.config, self.config_value)

    def run(self, output_name: str = "receipt.json") -> dict[str, object]:
        return adapter.run_development_baseline(
            config_path=self.config,
            repo=self.repo,
            kb_archive=self.kb_archive,
            kb=self.kb,
            phenopacket_archive=self.phenopacket_archive,
            selector_path=self.selector,
            output_path=self.root / output_name,
        )


class Phen2GeneDevelopmentAdapterTests(unittest.TestCase):
    def test_synthetic_end_to_end_is_aggregate_and_development_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticPhen2GeneFixture(Path(temporary))
            result = fixture.run()
            self.assertEqual(result["status"], "development_only_complete")
            self.assertEqual(result["truth_universe_recall"], 1.0)
            self.assertEqual(result["official_metrics"]["top1"]["point"], 1.0)
            self.assertEqual(result["negative_hpo_terms_omitted"], 1)
            self.assertEqual(result["safety"]["development_entries_read"], 1)
            self.assertEqual(result["safety"]["calibration_cases_read"], 0)
            self.assertEqual(result["safety"]["heldout_test_cases_read"], 0)
            self.assertEqual(result["safety"]["controlled_patient_files_read"], 0)
            self.assertEqual(result["safety"]["case_identifiers_written"], 0)
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn(str(fixture.root), serialized)
            self.assertNotIn(fixture.development_identifier, serialized)
            self.assertNotIn("SYNTRUTH", serialized)

    def test_repeat_has_identical_deterministic_core(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticPhen2GeneFixture(Path(temporary))
            first = fixture.run("first.json")
            second = fixture.run("second.json")
            self.assertEqual(first["core_sha256"], second["core_sha256"])
            self.assertEqual(first["case_receipt_sha256"], second["case_receipt_sha256"])

    def test_nondevelopment_identifier_is_rejected_after_valid_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticPhen2GeneFixture(Path(temporary))
            fixture.rewrite_selector(
                fixture._identifier_for("test"), refresh_pin=True
            )
            with self.assertRaisesRegex(adapter.AdapterInputError, "split guard"):
                fixture.run()

    def test_selector_tamper_and_dirty_source_both_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticPhen2GeneFixture(Path(temporary))
            fixture.rewrite_selector(
                fixture._identifier_for("calibration"), refresh_pin=False
            )
            with self.assertRaisesRegex(adapter.AdapterInputError, "selector digest"):
                fixture.run()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticPhen2GeneFixture(Path(temporary))
            (fixture.repo / "untracked.txt").write_text("synthetic\n", encoding="utf-8")
            with self.assertRaisesRegex(adapter.AdapterInputError, "dirty"):
                fixture.run()

    def test_tree_tamper_and_existing_output_both_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticPhen2GeneFixture(Path(temporary))
            (fixture.kb / "weights" / "synthetic.txt").write_text(
                "changed synthetic weight\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(adapter.AdapterInputError, "tree receipt"):
                fixture.run()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticPhen2GeneFixture(Path(temporary))
            output = fixture.root / "receipt.json"
            output.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(adapter.AdapterInputError, "overwrite"):
                fixture.run()


if __name__ == "__main__":
    unittest.main()
