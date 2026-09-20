from __future__ import annotations

import hashlib
import importlib.util
import json
import os
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
            json.dumps(config, sort_keys=True, allow_nan=False) + "\n"
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
            "scenarios": [
                {"name": f"scenario_{index}", "passed": True}
                for index in range(14)
            ],
            "summary": {
                "acceptance_passed": True,
                "all_passed": True,
                "passed": 14,
                "total": 14,
            },
            "total_simulated_vehicle_treatment_comparisons": 14000,
        }
        files[ARTIFACT_PATHS["benchmark_receipt"]] = (
            json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n"
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
        return (json.dumps(manifest, sort_keys=True, allow_nan=False) + "\n").encode(), files

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
        files[receipt_path] = (json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n").encode()
        manifest = json.loads(manifest_data)
        for entry in manifest["artifacts"]:
            if entry["role"] == "benchmark_receipt":
                entry["sha256"] = hashlib.sha256(files[receipt_path]).hexdigest()
        issues = validate_manifest_bytes(
            (json.dumps(manifest, sort_keys=True, allow_nan=False) + "\n").encode(), files.get
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
            (json.dumps(decoded, sort_keys=True, allow_nan=False) + "\n").encode(), files.get
        )
        self.assertTrue(any("unknown role" in issue for issue in issues))

    def test_receipt_counts_must_match_bound_configuration(self) -> None:
        manifest_data, files = self.fixture()
        receipt_path = ARTIFACT_PATHS["benchmark_receipt"]
        receipt = json.loads(files[receipt_path])
        receipt["summary"]["total"] = 13
        receipt["total_simulated_vehicle_treatment_comparisons"] = 13000
        files[receipt_path] = (json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n").encode()
        manifest = json.loads(manifest_data)
        for entry in manifest["artifacts"]:
            if entry["role"] == "benchmark_receipt":
                entry["sha256"] = hashlib.sha256(files[receipt_path]).hexdigest()
        issues = validate_manifest_bytes(
            (json.dumps(manifest, sort_keys=True, allow_nan=False) + "\n").encode(), files.get
        )
        self.assertTrue(any("every configured scenario" in issue for issue in issues))
        self.assertTrue(any("comparison count" in issue for issue in issues))

    def _receipt_mutation_issues(
        self, mutate: object
    ) -> list[str]:
        manifest_data, files = self.fixture()
        receipt_path = ARTIFACT_PATHS["benchmark_receipt"]
        receipt = json.loads(files[receipt_path])
        mutate(receipt)  # type: ignore[operator]
        # Fixture-only: the mutation may intentionally inject non-finite
        # floats to verify the loader rejects them, so the dump must opt out
        # of the allow_nan guard for this crafted payload.
        files[receipt_path] = (
            json.dumps(receipt, sort_keys=True, allow_nan=True) + "\n"
        ).encode()
        manifest = json.loads(manifest_data)
        for entry in manifest["artifacts"]:
            if entry["role"] == "benchmark_receipt":
                entry["sha256"] = hashlib.sha256(files[receipt_path]).hexdigest()
        return validate_manifest_bytes(
            (json.dumps(manifest, sort_keys=True, allow_nan=False) + "\n").encode(), files.get
        )

    def test_receipt_counts_reject_booleans(self) -> None:
        issues = self._receipt_mutation_issues(
            lambda receipt: receipt["summary"].update(passed=True)
        )
        self.assertTrue(any("every configured scenario" in issue for issue in issues))
        issues = self._receipt_mutation_issues(
            lambda receipt: receipt.update(
                total_simulated_vehicle_treatment_comparisons=True
            )
        )
        self.assertTrue(any("comparison count" in issue for issue in issues))
        issues = self._receipt_mutation_issues(
            lambda receipt: receipt.update(
                monte_carlo_replicates_per_scenario=True
            )
        )
        self.assertTrue(any("replicate count" in issue for issue in issues))

    def test_nested_nonfinite_summary_values_are_rejected(self) -> None:
        issues = self._receipt_mutation_issues(
            lambda receipt: receipt["summary"].update(
                per_scenario=[{"score": [0.5, {"nested": 1e400}]}]
            )
        )
        self.assertTrue(any("non-finite" in issue for issue in issues))

    def test_summary_cannot_override_failed_scenario_rows(self) -> None:
        def mutate(receipt: dict) -> None:
            for row in receipt["scenarios"]:
                row["passed"] = False

        issues = self._receipt_mutation_issues(mutate)
        self.assertTrue(any("scenario row did not pass" in issue for issue in issues))
        self.assertTrue(
            any("rows disagree with the summary" in issue for issue in issues)
        )

    def test_receipt_scenario_names_must_match_configuration(self) -> None:
        def mutate(receipt: dict) -> None:
            receipt["scenarios"][0]["name"] = "renamed_scenario"

        issues = self._receipt_mutation_issues(mutate)
        self.assertTrue(any("scenario names differ" in issue for issue in issues))

    def test_missing_receipt_scenario_list_fails_closed(self) -> None:
        issues = self._receipt_mutation_issues(
            lambda receipt: receipt.pop("scenarios")
        )
        self.assertTrue(any("scenario result list" in issue for issue in issues))

    def test_verifier_script_reports_no_go_under_divergent_tree(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_track2_reproducibility.py"),
                str(ROOT),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("NO-GO", result.stdout)
        self.assertNotIn("GO: Track 2", result.stdout)

    def test_every_bound_artifact_is_eol_pinned(self) -> None:
        """Cross-machine digest stability: every bound artifact must carry
        eol=lf so a fresh checkout produces identical bytes on any platform.
        Without it, autocrlf converts LF blobs to CRLF working bytes on
        Windows, so a manifest minted there binds CRLF digests a Linux
        verifier can never reproduce."""
        import shutil
        import subprocess

        if shutil.which("git") is None:
            self.skipTest("git not available")
        if subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=ROOT,
            capture_output=True,
        ).returncode != 0:
            self.skipTest("not inside a Git worktree")
        for role, path in ARTIFACT_PATHS.items():
            result = subprocess.run(
                ["git", "check-attr", "eol", "--", path.as_posix()],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertIn(
                "eol: lf",
                result.stdout,
                f"{role} ({path.as_posix()}) lacks eol=lf in .gitattributes",
            )

    def test_builder_refuses_nonnormalized_working_bytes(self) -> None:
        """A clean worktree is not byte-identical: under autocrlf a CRLF
        working file reads clean while differing from the LF blob. The
        builder must refuse to bind working bytes that differ from the
        committed blob, or the manifest fails verification on machines
        whose checkout normalizes differently."""
        import shutil
        import subprocess
        import tempfile

        if shutil.which("git") is None:
            self.skipTest("git not available")
        scripts_dir = str(ROOT / "scripts")
        spec = importlib.util.spec_from_file_location(
            "create_track2_reproducibility_manifest",
            str(Path(scripts_dir) / "create_track2_reproducibility_manifest.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
                       GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                       GIT_COMMITTER_EMAIL="t@t")
            subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
            for path in ARTIFACT_PATHS.values():
                target = repo.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(
                    (ROOT.joinpath(*path.parts)).read_bytes()
                )
            subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "init"], cwd=repo, env=env, check=True
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            # Everything committed clean; now corrupt one bound file's
            # working-tree line endings (git still reports the tree clean
            # under EOL normalization, but raw bytes differ from the blob).
            victim = repo.joinpath(*ARTIFACT_PATHS["python_contract"].parts)
            victim.write_bytes(victim.read_bytes().replace(b"\n", b"\r\n"))
            with self.assertRaisesRegex(ValueError, "committed blob"):
                module.build_manifest(repo, head)


if __name__ == "__main__":
    unittest.main()
