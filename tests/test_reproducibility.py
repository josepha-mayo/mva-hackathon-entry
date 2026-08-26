from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from pathlib import PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mva_hackathon.reproducibility import (
    ARTIFACT_PATHS,
    COMMANDS,
    SCHEMA,
    validate_manifest_bytes,
)


class ReproducibilityManifestTests(unittest.TestCase):
    def fixture(self) -> tuple[bytes, dict[PurePosixPath, bytes]]:
        commit = "a" * 40
        files = {path: f"fixture:{role}\n".encode() for role, path in ARTIFACT_PATHS.items()}
        config = {
            "schema": "mva-generation-selection-benchmark/v3",
            "monte_carlo_replicates": 1000,
            "scenarios": [{"name": f"scenario_{index}"} for index in range(14)],
        }
        files[ARTIFACT_PATHS["benchmark_config"]] = (
            json.dumps(config, sort_keys=True) + "\n"
        ).encode()
        receipt = {
            "runtime_receipt": {
                "canonical_command": COMMANDS["benchmark"],
                "config_sha256": hashlib.sha256(files[ARTIFACT_PATHS["benchmark_config"]]).hexdigest(),
                "source_sha256": hashlib.sha256(files[ARTIFACT_PATHS["benchmark_source"]]).hexdigest(),
                "runner_sha256": hashlib.sha256(files[ARTIFACT_PATHS["benchmark_runner"]]).hexdigest(),
                "test_sha256": hashlib.sha256(files[ARTIFACT_PATHS["benchmark_test"]]).hexdigest(),
                "git_source_commit": commit,
                "git_tracked_worktree_clean": True,
            },
            "monte_carlo_replicates_per_scenario": 1000,
            "summary": {
                "acceptance_passed": True,
                "all_passed": True,
                "passed": 14,
                "total": 14,
            },
            "total_simulated_vehicle_treatment_comparisons": 14000,
        }
        files[ARTIFACT_PATHS["benchmark_receipt"]] = (
            json.dumps(receipt, sort_keys=True) + "\n"
        ).encode()
        artifacts = [
            {
                "role": role,
                "path": path.as_posix(),
                "sha256": hashlib.sha256(files[path]).hexdigest(),
            }
            for role, path in ARTIFACT_PATHS.items()
        ]
        manifest = {
            "schema": SCHEMA,
            "source_commit": commit,
            "commands": COMMANDS,
            "artifacts": artifacts,
        }
        return (json.dumps(manifest, sort_keys=True) + "\n").encode(), files

    def test_valid_manifest_binds_complete_receipt_chain(self) -> None:
        manifest, files = self.fixture()
        self.assertEqual(validate_manifest_bytes(manifest, files.get), [])

    def test_tampered_artifact_fails(self) -> None:
        manifest, files = self.fixture()
        files[ARTIFACT_PATHS["benchmark_source"]] += b"tamper"
        issues = validate_manifest_bytes(manifest, files.get)
        self.assertTrue(any("digest does not match" in issue for issue in issues))

    def test_receipt_commit_and_acceptance_fail_closed(self) -> None:
        manifest_data, files = self.fixture()
        receipt_path = ARTIFACT_PATHS["benchmark_receipt"]
        receipt = json.loads(files[receipt_path])
        receipt["runtime_receipt"]["git_source_commit"] = "b" * 40
        receipt["summary"]["acceptance_passed"] = False
        files[receipt_path] = (json.dumps(receipt, sort_keys=True) + "\n").encode()
        manifest = json.loads(manifest_data)
        for entry in manifest["artifacts"]:
            if entry["role"] == "benchmark_receipt":
                entry["sha256"] = hashlib.sha256(files[receipt_path]).hexdigest()
        issues = validate_manifest_bytes(
            (json.dumps(manifest, sort_keys=True) + "\n").encode(), files.get
        )
        self.assertTrue(any("source_commit" in issue for issue in issues))
        self.assertTrue(any("global acceptance" in issue for issue in issues))

    def test_duplicate_json_key_and_unknown_role_fail(self) -> None:
        manifest, files = self.fixture()
        duplicate = manifest.replace(b'"schema":', b'"schema":"x","schema":', 1)
        self.assertTrue(validate_manifest_bytes(duplicate, files.get))

        decoded = json.loads(manifest)
        decoded["artifacts"][0]["role"] = "unknown"
        issues = validate_manifest_bytes(
            (json.dumps(decoded, sort_keys=True) + "\n").encode(), files.get
        )
        self.assertTrue(any("unknown role" in issue for issue in issues))

    def test_receipt_counts_must_match_bound_configuration(self) -> None:
        manifest_data, files = self.fixture()
        receipt_path = ARTIFACT_PATHS["benchmark_receipt"]
        receipt = json.loads(files[receipt_path])
        receipt["summary"]["total"] = 13
        receipt["total_simulated_vehicle_treatment_comparisons"] = 13000
        files[receipt_path] = (json.dumps(receipt, sort_keys=True) + "\n").encode()
        manifest = json.loads(manifest_data)
        for entry in manifest["artifacts"]:
            if entry["role"] == "benchmark_receipt":
                entry["sha256"] = hashlib.sha256(files[receipt_path]).hexdigest()
        issues = validate_manifest_bytes(
            (json.dumps(manifest, sort_keys=True) + "\n").encode(), files.get
        )
        self.assertTrue(any("every configured scenario" in issue for issue in issues))
        self.assertTrue(any("comparison count" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
