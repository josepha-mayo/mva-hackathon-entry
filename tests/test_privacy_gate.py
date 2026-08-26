from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from privacy_gate import (
    RELEASE_ARTIFACT_PATHS,
    RELEASE_MANIFEST_SCHEMA,
    RELEASE_MANIFEST_PATH,
    findings,
)
from mva_hackathon.submission import REQUIRED_FIELDS


class PrivacyGateTests(unittest.TestCase):
    def release_path(self, root: Path, role: str) -> Path:
        return root.joinpath(*RELEASE_ARTIFACT_PATHS[role].parts)

    def release_csv_bytes(self, *, fieldnames: tuple[str, ...] = REQUIRED_FIELDS) -> bytes:
        identifier = "control".upper() + str(42)
        row: dict[str, object] = {
            "proband_id": "PROBAND01",
            "chrom_1": "chr7",
            "pos_1": 101_001,
            "ref_1": "A",
            "alt_1": "G",
            "chrom_2": "chr7",
            "pos_2": 101_249,
            "ref_2": "C",
            "alt_2": "T",
            "epcr": 0.5,
            "finding_type": "primary",
            "notes": f"Candidate gene {identifier}; coordinate " + "chr7:" + str(101_001),
        }
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
        return buffer.getvalue().encode("utf-8")

    def write_release_csv(
        self,
        root: Path,
        *,
        fieldnames: tuple[str, ...] = REQUIRED_FIELDS,
    ) -> Path:
        path = self.release_path(root, "track1_submission_csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.release_csv_bytes(fieldnames=fieldnames))
        return path

    def write_manifest(
        self,
        root: Path,
        *,
        csv_status: str = "planned",
        report_status: str = "planned",
        track2_report_status: str = "planned",
        pitch_status: str = "planned",
        reproducibility_status: str = "planned",
    ) -> tuple[Path, dict[str, object]]:
        artifacts: list[dict[str, object]] = []
        for role, status in (
            ("track1_submission_csv", csv_status),
            ("track1_methods_report", report_status),
            ("track2_repositioning_report", track2_report_status),
            ("track2_pitch_script", pitch_status),
            ("track2_reproducibility_manifest", reproducibility_status),
        ):
            artifact_path = self.release_path(root, role)
            digest = None
            if status == "released":
                digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            artifacts.append(
                {
                    "role": role,
                    "path": RELEASE_ARTIFACT_PATHS[role].as_posix(),
                    "status": status,
                    "sha256": digest,
                }
            )
        manifest: dict[str, object] = {
            "schema": RELEASE_MANIFEST_SCHEMA,
            "artifacts": artifacts,
        }
        manifest_path = root.joinpath(*RELEASE_MANIFEST_PATH.parts)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest_path, manifest

    def test_scans_nested_public_tree_for_non_synthetic_biology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "reports" / "review"
            nested.mkdir(parents=True)
            identifier = "control".upper() + str(42)
            protein_change = ".".join(("p", "Arg123Ter"))
            (nested / "draft.md").write_text(
                f"Candidate gene `{identifier}` has change `{protein_change}`.\n",
                encoding="utf-8",
            )
            issues = findings(root, include_git=False)
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in issues))
            self.assertTrue(any("HGVS-like variant" in issue for issue in issues))

    def test_root_directory_allowlist_does_not_hide_nested_namesake(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "public" / ".venv"
            nested.mkdir(parents=True)
            identifier = "control".upper() + str(42)
            (nested / "draft.md").write_text(
                f"Candidate gene `{identifier}`.\n", encoding="utf-8"
            )
            self.assertTrue(
                any(
                    "non-synthetic biological identifier" in issue
                    for issue in findings(root, include_git=False)
                )
            )

    def test_allows_only_explicit_policy_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / "scripts" / "privacy_gate.py"
            allowed.parent.mkdir()
            receipt = "official registration " + "completed"
            allowed.write_text(receipt, encoding="utf-8")
            self.assertEqual(findings(root, include_git=False), [])

            copied = root / "copies" / "scripts" / "privacy_gate.py"
            copied.parent.mkdir(parents=True)
            copied.write_text(receipt, encoding="utf-8")
            self.assertTrue(
                any("registration/access receipt" in issue for issue in findings(root, include_git=False))
            )

    def test_detects_operational_receipt_without_embedding_personal_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label = "City" + " and Country"
            (root / "receipt.md").write_text(f"- {label}: [redacted]\n", encoding="utf-8")
            self.assertTrue(
                any("personal registration field" in issue for issue in findings(root, include_git=False))
            )

    def test_synthetic_identifiers_are_public_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.md").write_text(
                "Candidate gene `SYNGENE42` is an explicitly synthetic fixture.\n",
                encoding="utf-8",
            )
            self.assertEqual(findings(root, include_git=False), [])

    def test_release_csv_requires_exact_manifest_digest_and_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_csv = self.write_release_csv(root)

            undeclared = findings(root, include_git=False)
            self.assertTrue(any("exists without the required manifest" in issue for issue in undeclared))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in undeclared))

            self.write_manifest(root)
            planned = findings(root, include_git=False)
            self.assertTrue(any("planned artifact exists" in issue for issue in planned))

            self.write_manifest(root, csv_status="released")
            self.assertEqual(findings(root, include_git=False), [])

            release_csv.write_bytes(release_csv.read_bytes() + b"\n")
            mismatched = findings(root, include_git=False)
            self.assertTrue(any("digest does not match" in issue for issue in mismatched))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in mismatched))

    def test_release_allowance_does_not_follow_identical_bytes_to_another_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_csv = self.write_release_csv(root)
            self.write_manifest(root, csv_status="released")
            copied = root / "copies" / "replayed.csv"
            copied.parent.mkdir(parents=True)
            copied.write_bytes(release_csv.read_bytes())

            biology = [
                issue
                for issue in findings(root, include_git=False)
                if "non-synthetic biological identifier" in issue
            ]
            self.assertTrue(any("copies/replayed.csv" in issue for issue in biology))
            self.assertFalse(
                any(RELEASE_ARTIFACT_PATHS["track1_submission_csv"].as_posix() in issue for issue in biology)
            )

    def test_release_manifest_rejects_surplus_and_wrong_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_release_csv(root)
            manifest_path, manifest = self.write_manifest(root, csv_status="released")
            artifacts = manifest["artifacts"]
            self.assertIsInstance(artifacts, list)
            assert isinstance(artifacts, list)

            artifacts.append(dict(artifacts[0]))
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            surplus = findings(root, include_git=False)
            self.assertTrue(any("exactly the fixed release artifacts" in issue for issue in surplus))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in surplus))

            _, manifest = self.write_manifest(root, csv_status="released")
            artifacts = manifest["artifacts"]
            assert isinstance(artifacts, list)
            first = artifacts[0]
            assert isinstance(first, dict)
            first["path"] = "submissions/track1/surplus.txt"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            wrong_path = findings(root, include_git=False)
            self.assertTrue(any("fixed path and extension" in issue for issue in wrong_path))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in wrong_path))

    def test_manifest_bound_csv_must_pass_canonical_header_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reordered = list(REQUIRED_FIELDS)
            reordered[0], reordered[1] = reordered[1], reordered[0]
            self.write_release_csv(root, fieldnames=tuple(reordered))
            self.write_manifest(root, csv_status="released")

            issues = findings(root, include_git=False)
            self.assertTrue(any("header order" in issue for issue in issues))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in issues))

    def test_legacy_v1_manifest_remains_valid_for_git_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = self.write_release_csv(root)
            report_path = self.release_path(root, "track1_methods_report")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("# Track 1 methods\n", encoding="utf-8")
            artifacts = []
            for role, artifact_path in (
                ("track1_submission_csv", csv_path),
                ("track1_methods_report", report_path),
            ):
                artifacts.append(
                    {
                        "role": role,
                        "path": RELEASE_ARTIFACT_PATHS[role].as_posix(),
                        "status": "released",
                        "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                    }
                )
            manifest_path = root.joinpath(*RELEASE_MANIFEST_PATH.parts)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema": "mva-public-release-quarantine/v1",
                        "artifacts": artifacts,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(findings(root, include_git=False), [])

    def test_planned_report_receives_no_quarantine_until_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.release_path(root, "track1_methods_report")
            report.parent.mkdir(parents=True)
            identifier = "control".upper() + str(42)
            report.write_text(
                f"Candidate gene {identifier} at " + "chr7:" + str(101_001) + ".\n",
                encoding="utf-8",
            )
            self.write_manifest(root)

            planned = findings(root, include_git=False)
            self.assertTrue(any("planned artifact exists" in issue for issue in planned))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in planned))

            self.write_manifest(root, report_status="released")
            self.assertEqual(findings(root, include_git=False), [])

    def test_release_report_never_suppresses_non_biological_detectors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.release_path(root, "track1_methods_report")
            report.parent.mkdir(parents=True)
            identifier = "control".upper() + str(42)
            secret = "hf_" + "C" * 32
            payload_marker = "##fileformat=" + "VCFv4.2"
            phenotype_bundle = " ".join("HP:" + f"{number:07d}" for number in range(1, 4))
            report.write_text(
                f"Candidate gene {identifier} at " + "chr7:" + str(101_001) + ".\n"
                f"{secret}\n{payload_marker}\n{phenotype_bundle}\n",
                encoding="utf-8",
            )
            self.write_manifest(root, report_status="released")

            issues = findings(root, include_git=False)
            self.assertTrue(any("Hugging Face token" in issue for issue in issues))
            self.assertTrue(any("VCF payload" in issue for issue in issues))
            self.assertTrue(any("phenotype bundle" in issue for issue in issues))
            self.assertFalse(any("non-synthetic biological identifier" in issue for issue in issues))
            self.assertFalse(any("genomic coordinate" in issue for issue in issues))

    def test_track2_report_requires_digest_and_complete_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.release_path(root, "track2_repositioning_report")
            report.parent.mkdir(parents=True)
            identifier = "control".upper() + str(42)
            report.write_text(
                "# Research report\n\n"
                "## Executive decision\n\n"
                f"Candidate gene {identifier}.\n\n"
                "## Falsification and decision table\n\n"
                "A negative result rejects the hypothesis.\n\n"
                "## Limitations\n\n"
                "Synthetic test only.\n\n"
                "## References\n\n"
                "Primary sources.\n",
                encoding="utf-8",
            )

            self.write_manifest(root)
            planned = findings(root, include_git=False)
            self.assertTrue(any("planned artifact exists" in issue for issue in planned))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in planned))

            self.write_manifest(root, track2_report_status="released")
            self.assertEqual(findings(root, include_git=False), [])

    def test_released_report_rejects_unresolved_placeholder_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.release_path(root, "track1_methods_report")
            report.parent.mkdir(parents=True)
            identifier = "control".upper() + str(42)
            marker = "<!-- " + "RESULT_PENDING" + " -->"
            report.write_text(
                f"Candidate gene {identifier}.\n{marker}\n",
                encoding="utf-8",
            )
            self.write_manifest(root, report_status="released")

            unresolved = findings(root, include_git=False)
            self.assertTrue(any("unresolved placeholder marker" in issue for issue in unresolved))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in unresolved))

            report.write_text(
                f"Candidate gene {identifier}. Result recorded.\n",
                encoding="utf-8",
            )
            self.write_manifest(root, report_status="released")
            self.assertEqual(findings(root, include_git=False), [])

    def test_public_development_split_tokens_are_not_biological_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_label = "".join(("M", "V", "A"))
            second_label = "".join(("P", "P", "S"))
            content = json.dumps({"development_splits": [first_label, second_label]})
            config = root / "configs" / "phen2gene-development-baseline.json"
            config.parent.mkdir()
            config.write_text(content, encoding="utf-8")
            copied = root / "other-config.json"
            copied.write_text(content, encoding="utf-8")

            issues = findings(root, include_git=False)
            self.assertTrue(
                any(
                    "non-synthetic biological identifier" in issue
                    and "other-config.json" in issue
                    for issue in issues
                )
            )
            self.assertFalse(
                any("configs/phen2gene-development-baseline.json" in issue for issue in issues)
            )

    def test_detects_renamed_vcf_by_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "innocent.txt").write_text("##fileformat=VCFv4.2\n", encoding="utf-8")
            self.assertTrue(any("VCF payload" in issue for issue in findings(root, include_git=False)))

    def test_detects_renamed_compressed_payload_by_magic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "innocent.bin").write_bytes(b"\x1f\x8b\x08\x00")
            self.assertTrue(any("gzip/BGZF" in issue for issue in findings(root, include_git=False)))

    def test_scans_secrets_beyond_two_mebibytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "hf_" + "A" * 32
            (root / "large.txt").write_text("x" * (3 * 1024 * 1024) + secret, encoding="utf-8")
            self.assertTrue(any("Hugging Face token" in issue for issue in findings(root, include_git=False)))

    def test_detects_lfs_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pointer = (
                "version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{'c' * 64}\n"
                "size 123456\n"
            )
            (root / "renamed.txt").write_text(pointer, encoding="utf-8")
            self.assertTrue(any("Git LFS pointer" in issue for issue in findings(root, include_git=False)))

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_working_release_cannot_approve_a_planned_index_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            self.write_release_csv(root)
            self.write_manifest(root)
            subprocess.run(
                ["git", "-c", "core.autocrlf=false", "add", "."],
                cwd=root,
                check=True,
            )

            self.write_manifest(root, csv_status="released")
            issues = findings(root)
            release_path = RELEASE_ARTIFACT_PATHS["track1_submission_csv"].as_posix()
            self.assertTrue(
                any(
                    "Git index" in issue
                    and release_path in issue
                    and "non-synthetic biological identifier" in issue
                    for issue in issues
                )
            )
            self.assertFalse(
                any(
                    "working tree" in issue
                    and release_path in issue
                    and "non-synthetic biological identifier" in issue
                    for issue in issues
                )
            )

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_history_quarantine_is_bound_to_each_tree_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            release_csv = self.write_release_csv(root)
            self.write_manifest(root, csv_status="released")
            subprocess.run(
                ["git", "-c", "core.autocrlf=false", "add", "."],
                cwd=root,
                check=True,
            )
            commit = [
                "git", "-c", "user.name=Privacy Test", "-c",
                "user.email=privacy@example.invalid", "commit", "-qm",
            ]
            subprocess.run([*commit, "declared release"], cwd=root, check=True)

            copied = root / "copies" / "replayed.csv"
            copied.parent.mkdir(parents=True)
            copied.write_bytes(release_csv.read_bytes())
            subprocess.run(
                ["git", "-c", "core.autocrlf=false", "add", "copies/replayed.csv"],
                cwd=root,
                check=True,
            )
            subprocess.run([*commit, "undeclared copy"], cwd=root, check=True)
            subprocess.run(["git", "rm", "-q", "copies/replayed.csv"], cwd=root, check=True)
            subprocess.run([*commit, "remove copy"], cwd=root, check=True)

            history_issues = [
                issue
                for issue in findings(root)
                if "Git history" in issue and "copies/replayed.csv" in issue
            ]
            self.assertTrue(
                any("non-synthetic biological identifier" in issue for issue in history_issues)
            )
            self.assertFalse(
                any(
                    RELEASE_ARTIFACT_PATHS["track1_submission_csv"].as_posix() in issue
                    and "non-synthetic biological identifier" in issue
                    for issue in findings(root)
                )
            )

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_detects_secret_deleted_from_worktree_but_kept_in_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            leaked = root / "notes.txt"
            leaked.write_text("hf_" + "B" * 32, encoding="utf-8")
            subprocess.run(["git", "add", "notes.txt"], cwd=root, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=Privacy Test", "-c", "user.email=privacy@example.invalid",
                    "commit", "-qm", "fixture",
                ],
                cwd=root, check=True,
            )
            leaked.unlink()
            self.assertTrue(any("Git history" in issue for issue in findings(root)))


if __name__ == "__main__":
    unittest.main()
