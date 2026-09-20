from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from privacy_gate import (
    NEXT_RELEASE_MANIFEST_SCHEMA,
    RELEASE_ARTIFACT_PATHS,
    RELEASE_MANIFEST_SCHEMA,
    RELEASE_MANIFEST_PATH,
    ReleaseAllowance,
    _inspect_bytes,
    _validate_release_manifest,
    findings,
)
from mva_hackathon.candidate_ledger import (
    RESCUE_GATE_NAMES,
    canonical_candidate_ledger_bytes,
    canonical_candidate_ranking_bytes,
    sample_stewardship_plan_sha256,
    validate_candidate_ledger,
)
from mva_hackathon.sample_stewardship import make_completion_receipt
from mva_hackathon.submission import REQUIRED_FIELDS


REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_TEMPLATE = (
    REPO_ROOT / "templates" / "track2_candidate_ledger.synthetic.json"
)
SAMPLE_TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "track2_sample_stewardship.synthetic.json"
)

PROMOTION_EVIDENCE: dict[str, object] = {
    "analytic_transfer_result_sha256": "a" * 64,
    "site2_blinding_state": "blinded",
    "site2_blinding_id": "syn-blinding-site2-phenotype",
    "site2_blinding_evidence_sha256": "c" * 64,
    "discovery_event_family_ids": ["syn-event-discovery-phenotype"],
    "replication_event_family_ids": ["syn-event-replication-phenotype"],
    "discovery_site_id": "syn-site-discovery-phenotype",
    "replication_site_id": "syn-site-replication-phenotype",
}


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
            json.dumps(manifest, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return manifest_path, manifest

    def write_candidate_release_bundle(self, root: Path) -> tuple[Path, Path]:
        payload = json.loads(CANDIDATE_TEMPLATE.read_text(encoding="utf-8"))
        identifier = "control".upper() + str(42)
        payload["entries"][0]["claim"] = (  # type: ignore[index]
            f"Candidate gene {identifier} is named only inside this digest-bound release fixture."
        )
        ledger = validate_candidate_ledger(payload, public_only=True)
        ledger_path = self.release_path(root, "track2_candidate_evidence_ledger")
        ranking_path = self.release_path(root, "track2_candidate_ranking_receipt")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_bytes(
            canonical_candidate_ledger_bytes(ledger, public_only=True)
        )
        ranking_path.write_bytes(canonical_candidate_ranking_bytes(ledger))
        return ledger_path, ranking_path

    def promoted_sample_plan(self, entry: dict[str, object]) -> dict[str, object]:
        plan = json.loads(SAMPLE_TEMPLATE.read_text(encoding="utf-8"))
        assays = {item["assay_id"]: item for item in plan["assays"]}
        for assay_id in (
            "syn-a0-phenotype",
            "syn-a1-phenotype-bridge",
            "syn-tier-b-phenotype-context",
            "syn-tier-b-phenotype-lineage",
            "syn-held-out-phenotype",
        ):
            plan["completed"][assay_id] = make_completion_receipt(
                assays[assay_id],
                "positive",
                "syn-completion-" + assay_id.removeprefix("syn-"),
            )
        plan["completed"]["syn-replication-phenotype"] = make_completion_receipt(
            assays["syn-replication-phenotype"],
            "positive",
            "syn-completion-replication-phenotype",
            promotion_evidence=PROMOTION_EVIDENCE,
        )
        held_lock = assays["syn-held-out-phenotype"]["held_out_lock"]
        replication_lock = assays["syn-replication-phenotype"]["replication_lock"]
        design = entry["replication_design"]
        design["discovery_site_id"] = PROMOTION_EVIDENCE["discovery_site_id"]
        design["replication_site_id"] = PROMOTION_EVIDENCE["replication_site_id"]
        design["discovery_edit_event_family_ids"] = list(
            PROMOTION_EVIDENCE["discovery_event_family_ids"]
        )
        design["replication_edit_event_family_ids"] = list(
            PROMOTION_EVIDENCE["replication_event_family_ids"]
        )
        design["frozen_exposure_identity_id"] = held_lock["frozen_exposure_id"]
        design["frozen_endpoint_identity_id"] = held_lock["frozen_endpoint_id"]
        design["frozen_margin_identity_id"] = held_lock["frozen_margin_id"]
        design["frozen_protocol_identity_id"] = replication_lock[
            "frozen_protocol_id"
        ]
        design["frozen_analysis_identity_id"] = replication_lock[
            "frozen_analysis_id"
        ]
        design["analytic_transfer_result_sha256"] = PROMOTION_EVIDENCE[
            "analytic_transfer_result_sha256"
        ]
        design["site2_blinding_state"] = "blinded"
        design["site2_blinding_evidence_sha256"] = PROMOTION_EVIDENCE[
            "site2_blinding_evidence_sha256"
        ]
        held_receipt = plan["completed"]["syn-held-out-phenotype"]
        replication_receipt = plan["completed"]["syn-replication-phenotype"]
        entry["sample_stewardship_promotion"] = {
            "held_out_assay_id": "syn-held-out-phenotype",
            "replication_assay_id": "syn-replication-phenotype",
            "held_out_receipt_id": held_receipt["receipt_id"],
            "replication_receipt_id": replication_receipt["receipt_id"],
            "held_out_receipt_sha256": held_receipt["receipt_sha256"],
            "replication_receipt_sha256": replication_receipt["receipt_sha256"],
            "sample_plan_sha256": sample_stewardship_plan_sha256(plan),
        }
        return plan

    def write_promoted_candidate_release_bundle(
        self,
        root: Path,
    ) -> tuple[Path, Path, dict[str, object]]:
        payload = json.loads(CANDIDATE_TEMPLATE.read_text(encoding="utf-8"))
        entry = payload["entries"][0]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["decision_effect"] = "promote"
        entry["functional_hit_state"] = "replicated_full_phenocopy"
        entry["screen_context"] = "participant_lineage_tier_b"
        entry["translation_state"] = "preclinical_replication_ready"
        entry["discovery_lane"] = "correction_trained_phenotypic"
        entry["therapeutic_context"] = "postnatal_nontransformed_proliferative"
        entry["architecture_lineage_state"] = "architecture_preserving"
        entry["mitotic_context_class"] = "epithelial_architecture_dependent"
        entry["transformation_state"] = "primary_finite"
        entry["independent_replication"] = "replicated"
        entry["advancement_state"] = "conditional_hold"
        entry["rescue_gates"] = {name: "pass" for name in RESCUE_GATE_NAMES}
        plan = self.promoted_sample_plan(entry)
        ledger = validate_candidate_ledger(
            payload, public_only=True, sample_plan=plan
        )
        ledger_path = self.release_path(root, "track2_candidate_evidence_ledger")
        ranking_path = self.release_path(root, "track2_candidate_ranking_receipt")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_bytes(
            canonical_candidate_ledger_bytes(
                ledger, public_only=True, sample_plan=plan
            )
        )
        ranking_path.write_bytes(
            canonical_candidate_ranking_bytes(ledger, sample_plan=plan)
        )
        return ledger_path, ranking_path, plan

    def write_next_manifest(
        self,
        root: Path,
        *,
        candidate_status: str = "released",
        ranking_status: str = "released",
        track2_report_status: str = "planned",
    ) -> tuple[Path, dict[str, object]]:
        statuses = {
            role: "planned"
            for role in RELEASE_ARTIFACT_PATHS
        }
        statuses["track2_candidate_evidence_ledger"] = candidate_status
        statuses["track2_candidate_ranking_receipt"] = ranking_status
        statuses["track2_repositioning_report"] = track2_report_status
        artifacts: list[dict[str, object]] = []
        for role, artifact_path in RELEASE_ARTIFACT_PATHS.items():
            status = statuses[role]
            path = root.joinpath(*artifact_path.parts)
            digest = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if status == "released"
                else None
            )
            artifacts.append(
                {
                    "role": role,
                    "path": artifact_path.as_posix(),
                    "status": status,
                    "sha256": digest,
                }
            )
        manifest: dict[str, object] = {
            "schema": NEXT_RELEASE_MANIFEST_SCHEMA,
            "artifacts": artifacts,
        }
        manifest_path = root.joinpath(*RELEASE_MANIFEST_PATH.parts)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return manifest_path, manifest

    def write_candidate_bound_report(
        self,
        root: Path,
        ledger_path: Path,
        ranking_path: Path,
    ) -> Path:
        identifier = "control".upper() + str(42)
        report = self.release_path(root, "track2_repositioning_report")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "# Research report\n\n"
            "## Executive decision\n\n"
            f"Candidate gene {identifier} remains a falsifiable research hypothesis.\n\n"
            "## Falsification and decision table\n\n"
            "A negative result rejects the hypothesis.\n\n"
            "## Limitations\n\n"
            "Synthetic test only.\n\n"
            f"**Candidate evidence ledger SHA-256:** `{hashlib.sha256(ledger_path.read_bytes()).hexdigest()}`\n\n"
            f"**Candidate ranking receipt SHA-256:** `{hashlib.sha256(ranking_path.read_bytes()).hexdigest()}`\n\n"
            "## References\n\n"
            "Primary sources.\n",
            encoding="utf-8",
        )
        return report

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

    def test_policy_source_path_cannot_host_banned_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "scripts" / "privacy_gate.py"
            policy.parent.mkdir()
            receipt = "official registration " + "completed"
            policy.write_text(receipt, encoding="utf-8")
            self.assertTrue(
                any(
                    "registration/access receipt" in issue
                    for issue in findings(root, include_git=False)
                )
            )

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

    def test_material_tier_vocabulary_is_not_a_subject_identifier(self) -> None:
        # The material-class vocabulary (nonparticipant A0, minimal
        # participant A1, participant-lineage Tier B) uses single-character
        # tier codes — it is not a subject identifier and must not flag.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.md").write_text(
                "Only a valid participant A1 signal may spend material; "
                "nonparticipant A0 and participant-lineage Tier B stay.\n",
                encoding="utf-8",
            )
            self.assertEqual(findings(root, include_git=False), [])
            (root / "real_subject.md").write_text(
                "Analysis used " + "subject-" + str(42) + " and "
                + "proband id " + "p".upper() + "07" + " samples.\n",
                encoding="utf-8",
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("subject identifier" in issue for issue in issues),
                msg=f"expected a subject identifier finding, got {issues}",
            )

    def test_declared_synthetic_labels_pass_the_subject_identifier_check(
        self,
    ) -> None:
        # The reviewed PROBAND01 label and the SYN- namespace are declared
        # synthetic; an undeclared digit-bearing subject ID still flags.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.md").write_text(
                "Enrolment covered " + "proband".upper() + "01" + " and "
                + "participant SYN42 cohorts; control used "
                + "subject-" + str(99) + ".\n",
                encoding="utf-8",
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("subject identifier" in issue for issue in issues),
                msg=f"expected the undeclared subject ID to flag, got {issues}",
            )
            self.assertFalse(
                any("SYN42" in issue for issue in issues),
                msg=f"SYN-namespace label must not flag: {issues}",
            )

    def test_constant_and_path_tokens_are_not_base64_payloads(self) -> None:
        # Uppercase constants, hex digests, and slash-delimited paths decode
        # as base64 by coincidence; only payload-shaped tokens are decoded.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.md").write_text(
                "See TRANSCRIPT_SPECIMEN_STOP_REASONS, commit "
                + "23a062aac99f35d3e5967acd2575ee1c7f46e528411a"
                + ", and reports/TRACK2_PROGRAM_GATES.\n",
                encoding="utf-8",
            )
            self.assertEqual(findings(root, include_git=False), [])

    def test_allowlist_applies_to_unescaped_views(self) -> None:
        # A reviewed-path token must not re-flag inside the %XX-unescaped
        # view of its own file — allowance attaches to the file, not the view.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts" / "assess_clone_safety.py").write_text(
                "# noqa: " + "ble".upper() + str(1).zfill(3) + " "
                + "%20 trailing escape\n",
                encoding="utf-8",
            )
            self.assertEqual(findings(root, include_git=False), [])

    def test_method_tokens_are_allowed_only_at_reviewed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            level_token = "alpha".upper()
            contract_token = "schema".upper()
            digest_token = "hmac-sha256".upper()
            citation_token = "pmc".upper() + str(7_610_696)
            model_token = "gpt".upper() + "-" + str(5)
            reviewed = {
                "COMPETITION_CONTRACT.md": f"`{model_token}.6 Sol`\n",
                "src/mva_hackathon/allocation_inference.py": (
                    f"`{level_token}` `{contract_token}`\n"
                ),
                "reports/TRACK2_AI_LINE.md": f"`{model_token}.6 Sol`\n",
                "reports/TRACK2_SESSION_HANDOFF.md": f"`{model_token}.6 Sol`\n",
                "reports/TRACK2_ATTEMPT2_DELTA.md": f"`{digest_token}`\n",
                "reports/TRACK2_METHOD_IMPROVEMENTS.md": f"`{digest_token}`\n",
                "reports/TRACK2_RANDOMIZATION_CONTRACT.md": (
                    f"`{digest_token}` `{citation_token}`\n"
                ),
            }
            for relative, content in reviewed.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            self.assertEqual(findings(root, include_git=False), [])

            copied = root / "reports" / "unreviewed-copy.md"
            copied.write_text(
                f"`{digest_token}` `{citation_token}` `{model_token}`\n",
                encoding="utf-8",
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any(
                    f"non-synthetic biological identifier {digest_token!r}" in issue
                    and "reports/unreviewed-copy.md" in issue
                    for issue in issues
                )
            )
            self.assertTrue(
                any(
                    f"non-synthetic biological identifier {citation_token!r}" in issue
                    and "reports/unreviewed-copy.md" in issue
                    for issue in issues
                )
            )
            self.assertTrue(
                any(
                    f"non-synthetic biological identifier {model_token!r}" in issue
                    and "reports/unreviewed-copy.md" in issue
                    for issue in issues
                )
            )

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

    def test_next_manifest_binds_candidate_ledger_to_exact_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, ranking_path = self.write_candidate_release_bundle(root)

            undeclared = findings(root, include_git=False)
            self.assertTrue(any("exists without the required manifest" in issue for issue in undeclared))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in undeclared))

            self.write_next_manifest(root)
            self.assertEqual(findings(root, include_git=False), [])

            stale = json.loads(ranking_path.read_text(encoding="utf-8"))
            stale["conditional_probe_ids"] = []
            ranking_path.write_text(
                json.dumps(stale, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            self.write_next_manifest(root)
            stale_issues = findings(root, include_git=False)
            self.assertTrue(any("candidate release bundle failed" in issue for issue in stale_issues))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in stale_issues))

            self.write_candidate_release_bundle(root)
            ledger_path.write_bytes(ledger_path.read_bytes().replace(b"\n", b"\r\n"))
            self.write_next_manifest(root)
            noncanonical = findings(root, include_git=False)
            self.assertTrue(any("exact canonical rendering" in issue for issue in noncanonical))

    def test_promoted_candidate_bundle_requires_sample_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_promoted_candidate_release_bundle(root)
            self.write_next_manifest(root)

            missing = findings(root, include_git=False)
            self.assertTrue(
                any("requires a sample-stewardship plan" in issue for issue in missing)
            )

            _ledger_path, _ranking_path, plan = (
                self.write_promoted_candidate_release_bundle(root)
            )
            self.write_next_manifest(root)
            self.assertEqual(
                findings(root, include_git=False, sample_plan=plan),
                [],
            )

            stale_plan = json.loads(SAMPLE_TEMPLATE.read_text(encoding="utf-8"))
            stale = findings(root, include_git=False, sample_plan=stale_plan)
            self.assertTrue(
                any("does not match the submitted sample plan" in issue for issue in stale)
            )

    def test_unpromoted_candidate_bundle_ignores_supplied_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_candidate_release_bundle(root)
            self.write_next_manifest(root)
            plan = json.loads(SAMPLE_TEMPLATE.read_text(encoding="utf-8"))
            self.assertEqual(
                findings(root, include_git=False, sample_plan=plan),
                [],
            )

    def test_release_allowance_is_rechecked_against_scanned_bytes(self) -> None:
        identifier = "control".upper() + str(42)
        approved = f"Candidate gene {identifier}.\n".encode("utf-8")
        changed = approved + b"Changed after manifest validation.\n"
        allowance = ReleaseAllowance(
            role="track2_candidate_evidence_ledger",
            sha256=hashlib.sha256(approved).hexdigest(),
        )
        issues = _inspect_bytes(
            RELEASE_ARTIFACT_PATHS["track2_candidate_evidence_ledger"],
            changed,
            "working tree",
            release_allowance=allowance,
        )
        self.assertTrue(any("changed after manifest validation" in issue for issue in issues))
        self.assertTrue(any("non-synthetic biological identifier" in issue for issue in issues))

    def test_non_utf8_encoded_identifiers_are_flagged(self) -> None:
        payload = (
            "The participant carries "
            + "nm_".upper()
            + "000123.4:"
            + "c." + "123A>G in "
            + "brca".upper()
            + "1 with ClinVar "
            + "vcv".upper()
            + "000533901"
        )
        for encoded in (
            payload.encode("utf-16-le"),
            payload.encode("utf-16-be"),
            b"\xff\xfe" + payload.encode("utf-16-le"),
            payload.encode("utf-32-le"),
            b"plain\x00binary" + payload.encode("utf-8"),
        ):
            issues = _inspect_bytes(
                PurePosixPath("reports/evil.md"), encoded, "working tree"
            )
            self.assertTrue(
                any("non-UTF-8" in issue for issue in issues),
                f"unflagged payload: {encoded[:24]!r}",
            )

    def test_invalid_utf8_bytes_are_flagged_not_silently_dropped(self) -> None:
        smuggled = b"hf_" + b"\x80" + b"A" * 24 + b" in a note"
        issues = _inspect_bytes(
            PurePosixPath("reports/evil.md"), smuggled, "working tree"
        )
        self.assertTrue(
            any("non-UTF-8" in issue for issue in issues),
            f"invalid UTF-8 accepted silently: {issues!r}",
        )

    def test_final_snapshot_detects_release_deletion_after_initial_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, _ranking_path = self.write_candidate_release_bundle(root)
            self.write_next_manifest(root)
            changed = False

            def validating_then_delete(*args, **kwargs):
                nonlocal changed
                result = _validate_release_manifest(*args, **kwargs)
                if not changed:
                    changed = True
                    ledger_path.unlink()
                return result

            with patch(
                "privacy_gate._validate_release_manifest",
                side_effect=validating_then_delete,
            ):
                issues = findings(root, include_git=False)
            self.assertTrue(
                any(
                    "released artifact is missing" in issue
                    or "changed during scan" in issue
                    for issue in issues
                )
            )

    def test_next_manifest_candidate_pair_statuses_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_candidate_release_bundle(root)
            self.write_next_manifest(root, ranking_status="planned")
            issues = findings(root, include_git=False)
            self.assertTrue(any("must share one release status" in issue for issue in issues))

    def test_next_manifest_binds_released_report_to_candidate_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, ranking_path = self.write_candidate_release_bundle(root)
            report = self.write_candidate_bound_report(root, ledger_path, ranking_path)
            self.write_next_manifest(root, track2_report_status="released")
            self.assertEqual(findings(root, include_git=False), [])

            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
                    "0" * 64,
                ),
                encoding="utf-8",
            )
            self.write_next_manifest(root, track2_report_status="released")
            issues = findings(root, include_git=False)
            self.assertTrue(any("stale track2_candidate_evidence_ledger" in issue for issue in issues))

    def test_released_report_cannot_bind_a_planned_candidate_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, ranking_path = self.write_candidate_release_bundle(root)
            self.write_candidate_bound_report(root, ledger_path, ranking_path)
            ledger_path.unlink()
            ranking_path.unlink()
            self.write_next_manifest(
                root,
                candidate_status="planned",
                ranking_status="planned",
                track2_report_status="released",
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("declares candidate digests while the candidate pair is not released" in issue for issue in issues)
            )

    def test_candidate_pair_validation_uses_one_digest_checked_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, ranking_path = self.write_candidate_release_bundle(root)
            manifest_path, _manifest = self.write_next_manifest(root)
            fixed = {
                RELEASE_ARTIFACT_PATHS["track2_candidate_evidence_ledger"]: ledger_path,
                RELEASE_ARTIFACT_PATHS["track2_candidate_ranking_receipt"]: ranking_path,
            }
            counts = {path: 0 for path in fixed}

            def flapping_loader(path):
                if path not in fixed:
                    return None
                counts[path] += 1
                if counts[path] == 1:
                    return fixed[path].read_bytes()
                return b"{}\n"

            allowances, issues = _validate_release_manifest(
                manifest_path.read_bytes(),
                flapping_loader,
                "single-snapshot test",
            )
            self.assertEqual(issues, [])
            self.assertIn(
                RELEASE_ARTIFACT_PATHS["track2_candidate_evidence_ledger"],
                allowances,
            )
            self.assertTrue(all(count == 1 for count in counts.values()))

    def test_frozen_manifest_cannot_silently_host_future_candidate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_candidate_release_bundle(root)
            self.write_manifest(root)
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("not declared by the active manifest schema" in issue for issue in issues)
            )

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
            manifest_path.write_text(json.dumps(manifest, allow_nan=False) + "\n", encoding="utf-8")
            surplus = findings(root, include_git=False)
            self.assertTrue(any("exactly the fixed release artifacts" in issue for issue in surplus))
            self.assertTrue(any("non-synthetic biological identifier" in issue for issue in surplus))

            _, manifest = self.write_manifest(root, csv_status="released")
            artifacts = manifest["artifacts"]
            assert isinstance(artifacts, list)
            first = artifacts[0]
            assert isinstance(first, dict)
            first["path"] = "submissions/track1/surplus.txt"
            manifest_path.write_text(json.dumps(manifest, allow_nan=False) + "\n", encoding="utf-8")
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
                    indent=2, allow_nan=False)
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
            content = json.dumps({"development_splits": [first_label, second_label]}, allow_nan=False)
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

    def test_policy_source_cannot_hide_planted_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            source = (REPO_ROOT / "scripts" / "privacy_gate.py").read_text(
                encoding="utf-8"
            )
            gene = "brca".upper() + "1"
            accession = "vcv".upper() + "000533901"
            planted = source + f"\n# Patient {gene} carries {accession}.\n"
            (scripts / "privacy_gate.py").write_text(planted, encoding="utf-8")
            issues = findings(root, include_git=False)
            self.assertTrue(any(gene in issue for issue in issues), issues)
            self.assertTrue(any(accession in issue for issue in issues), issues)

    def test_policy_source_cannot_hide_planted_receipt_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            source = (REPO_ROOT / "scripts" / "privacy_gate.py").read_text(
                encoding="utf-8"
            )
            planted = source + "\n# official " + "registration com" + "pleted today\n"
            (scripts / "privacy_gate.py").write_text(planted, encoding="utf-8")
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("registration/access receipt" in issue for issue in issues),
                issues,
            )

    def test_base64_embedded_identifier_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            encoded = base64.b64encode(
                b"Candidate gene "
                + "brca".upper().encode()
                + b"1 with "
                + "vcv".upper().encode()
                + b"000533901."
            ).decode("ascii")
            (root / "notes.md").write_text(
                f"Review appendix: {encoded}\n", encoding="utf-8"
            )
            issues = findings(root, include_git=False)
            self.assertTrue(issues, "base64-embedded identifier was not flagged")

    def test_embedded_binary_signature_mid_file_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b"# Research report\n" + b" " * 64 + b"\x1f\x8b" + b"x" * 32
            (root / "report.md").write_bytes(payload)
            issues = findings(root, include_git=False)
            self.assertTrue(issues, "embedded gzip signature was not flagged")

    def test_confusable_identifier_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            confusable = "".join(
                chr(code)
                for code in (0x1D435, 0x1D445, 0x1D436, 0x1D434, 0x1D7CF)
            )
            (root / "report.md").write_text(
                f"Candidate gene {confusable} confirmed.\n", encoding="utf-8"
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("identifier" in issue for issue in issues),
                issues,
            )

    def test_refseq_and_database_accessions_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = "nm_".upper() + "000123.4"
            gene_db = "hgnc".upper() + ":12345"
            disease_db = "omim".upper() + " " + "600123"
            (root / "report.md").write_text(
                f"Transcript {transcript} with {gene_db} and {disease_db}.\n",
                encoding="utf-8",
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("accession" in issue for issue in issues), issues
            )

    def test_lowercase_and_spaced_accessions_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.md").write_text(
                "Transcript "
                + "nm" + "_" + "000123.4"
                + " with "
                + "omim" + ":" + "600123"
                + " and "
                + "hp" + ":" + "0000123"
                + " plus "
                + "hp".upper() + ":" + " 0000456"
                + ".\n",
                encoding="utf-8",
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("accession" in issue for issue in issues),
                f"lowercase/spaced accessions evaded: {issues!r}",
            )

    def test_base64_evasion_paths_are_flagged(self) -> None:
        inner = base64.b64encode(
            b"Candidate gene " + b"brca".upper() + b"1 with "
            + b"vcv".upper() + b"000533901."
        ).decode("ascii")
        variants = [
            inner,
            inner.translate(str.maketrans("+/", "-_")),
            "\n".join(inner[index : index + 8] for index in range(0, len(inner), 8)),
            " ".join(
                inner[index : index + 12] for index in range(0, len(inner), 12)
            ),
        ]
        for variant in variants:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "notes.md").write_text(
                    f"Appendix: {variant}\n", encoding="utf-8"
                )
                issues = findings(root, include_git=False)
                self.assertTrue(
                    issues,
                    f"base64 evasion not flagged: {variant[:24]!r}",
                )

    def test_utf8_bom_cannot_hide_payload_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "reads.txt").write_bytes(
                b"\xef\xbb\xbf@read1\nACGTACGTACGT\n+\nIIIIIIIIIIII\n"
            )
            issues = findings(root, include_git=False)
            self.assertTrue(
                any("fastq".upper() in issue for issue in issues),
                f"UTF-8 BOM hid FASTQ shape: {issues!r}",
            )

    def test_non_work_tree_reports_unverified_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.txt").write_text("clean text\n", encoding="utf-8")
            issues = findings(root)
            self.assertTrue(
                any("Git history unavailable" in issue for issue in issues),
                issues,
            )

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_identifier_in_commit_message_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "note.txt").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "note.txt"], cwd=root, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=Privacy Test", "-c",
                    "user.email=privacy@example.invalid", "commit", "-qm",
                    "proband carries " + "brca".upper() + "1 " + "vcv".upper() + "000533901",
                ],
                cwd=root,
                check=True,
            )
            self.assertTrue(
                any(
                    "Git history" in issue and "identifier" in issue
                    for issue in findings(root)
                )
            )


if __name__ == "__main__":
    unittest.main()
