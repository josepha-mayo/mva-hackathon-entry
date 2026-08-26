from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.evidence_ledger import (
    ASSESSMENT_STATUSES,
    DECISION_EFFECTS,
    DIRECTIONS,
    INDEPENDENT_REPLICATION_STATES,
    PHASE_STATES,
    PHASES,
    PRIVACY_CLASSES,
    SOURCE_CLASSES,
    EvidenceEntry,
    EvidenceLedgerError,
    load_evidence_ledger,
    validate_evidence_ledger,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "track1_evidence_ledger.synthetic.json"
SCHEMA = ROOT / "schemas" / "track1_evidence_ledger.schema.json"


class EvidenceLedgerTests(unittest.TestCase):
    def fixture(self) -> dict[str, object]:
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def test_synthetic_template_round_trips_through_public_gate(self) -> None:
        ledger = load_evidence_ledger(TEMPLATE, public_only=True)
        self.assertEqual(
            [entry.assessment_status for entry in ledger.entries],
            ["positive", "negative", "not_assessable"],
        )
        self.assertEqual(validate_evidence_ledger(ledger, public_only=True), ledger)
        self.assertEqual(ledger.to_dict(), self.fixture())

    def test_normalized_audit_fields_are_all_mandatory(self) -> None:
        expected = {
            "model_slot", "claim", "allele_or_pair_id", "source_class",
            "source_identifier", "source_version", "source_url", "tool_name",
            "tool_version", "tool_digest", "run_digest", "config_digest", "result",
            "unit", "independent_replication", "uncertainty", "counterevidence",
            "decision_effect", "phase_state", "artifact_path", "artifact_sha256",
            "manual_action", "reviewer", "reviewed_at"
        }
        self.assertTrue(expected.issubset(EvidenceEntry.__dataclass_fields__))
        candidate = self.fixture()
        del candidate["entries"][0]["claim"]  # type: ignore[index]
        with self.assertRaisesRegex(EvidenceLedgerError, "fields must be exactly"):
            validate_evidence_ledger(candidate)

    def test_negative_is_assessed_but_not_assessable_has_no_result(self) -> None:
        ledger = load_evidence_ledger(TEMPLATE)
        negative = ledger.entries[1]
        unavailable = ledger.entries[2]
        self.assertIsNotNone(negative.result)
        self.assertIsNone(negative.not_assessable_reason)
        self.assertIsNone(unavailable.result)
        self.assertIsNone(unavailable.unit)
        self.assertIsNotNone(unavailable.not_assessable_reason)
        self.assertEqual(unavailable.direction, "neutral")
        self.assertEqual(unavailable.decision_effect, "defer")

    def test_required_enumerations_fail_closed(self) -> None:
        fields = {
            "privacy_class": "secret-ish",
            "phase": "after-looking-at-leaderboard",
            "phase_state": "probably-trans",
            "direction": "probably-supports",
            "assessment_status": "unknown",
            "source_class": "web-search",
            "independent_replication": "maybe",
            "decision_effect": "nudge",
        }
        for field, invalid in fields.items():
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][0][field] = invalid  # type: ignore[index]
                with self.assertRaisesRegex(EvidenceLedgerError, field):
                    validate_evidence_ledger(candidate)

    def test_not_assessable_invariants_prevent_negative_inference(self) -> None:
        mutations = (
            ("direction", "supports", "neutral direction"),
            ("result", "absent", "cannot contain a result"),
            ("unit", "categorical", "cannot contain a result"),
            ("independent_replication", "not_attempted", "replication state"),
            ("phase_state", "unresolved", "non-assertive phase_state"),
            ("decision_effect", "exclude", "cannot promote, demote, or exclude"),
            ("not_assessable_reason", None, "expected text"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][2][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(EvidenceLedgerError, message):
                    validate_evidence_ledger(candidate)

    def test_assessed_status_requires_result_and_null_gap_reason(self) -> None:
        mutations = (
            ("result", None, "requires a result"),
            ("not_assessable_reason", "Not actually unavailable.", "must set"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][1][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(EvidenceLedgerError, message):
                    validate_evidence_ledger(candidate)

    def test_lineage_fields_are_atomic_groups(self) -> None:
        mutations = (
            ("tool_version", None, "tool_name, tool_version, and tool_digest"),
            ("config_digest", None, "run_digest and config_digest"),
            ("artifact_sha256", None, "artifact_path and artifact_sha256"),
            ("reviewed_at", None, "reviewer and reviewed_at"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][0][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(EvidenceLedgerError, message):
                    validate_evidence_ledger(candidate)

    def test_artifact_hash_is_real_and_paths_cannot_escape(self) -> None:
        ledger = load_evidence_ledger(TEMPLATE)
        entry = ledger.entries[0]
        artifact = ROOT / entry.artifact_path  # type: ignore[arg-type]
        observed = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.assertEqual(observed, entry.artifact_sha256)
        candidate = self.fixture()
        candidate["entries"][0]["artifact_path"] = "../outside.txt"  # type: ignore[index]
        with self.assertRaisesRegex(EvidenceLedgerError, "relative and non-traversing"):
            validate_evidence_ledger(candidate)

    def test_public_sources_require_safe_https_url(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["privacy_class"] = "public"
        entry["source_class"] = "public_database"
        entry["source_identifier"] = "synthetic-public-reference"
        entry["source_url"] = "https://example.invalid/reference"
        validate_evidence_ledger(candidate, public_only=True)
        entry["source_url"] = "https://user:secret@example.invalid/reference"
        with self.assertRaisesRegex(EvidenceLedgerError, "without credentials"):
            validate_evidence_ledger(candidate, public_only=True)

    def test_public_gate_rejects_controlled_class_and_source_mismatch(self) -> None:
        candidate = self.fixture()
        candidate["entries"][0]["privacy_class"] = "controlled"  # type: ignore[index]
        validate_evidence_ledger(candidate)
        with self.assertRaisesRegex(EvidenceLedgerError, "forbidden privacy classes"):
            validate_evidence_ledger(candidate, public_only=True)
        candidate["entries"][0]["privacy_class"] = "synthetic"  # type: ignore[index]
        candidate["entries"][0]["source_class"] = "controlled_source"  # type: ignore[index]
        with self.assertRaisesRegex(EvidenceLedgerError, "cannot label a controlled source"):
            validate_evidence_ledger(candidate)

    def test_duplicate_evidence_ids_unknown_fields_and_duplicate_keys_rejected(self) -> None:
        duplicate = self.fixture()
        duplicate["entries"][1]["evidence_id"] = duplicate["entries"][0]["evidence_id"]  # type: ignore[index]
        with self.assertRaisesRegex(EvidenceLedgerError, "duplicate evidence_id"):
            validate_evidence_ledger(duplicate)
        surplus = self.fixture()
        surplus["entries"][0]["rank"] = 1  # type: ignore[index]
        with self.assertRaisesRegex(EvidenceLedgerError, "fields must be exactly"):
            validate_evidence_ledger(surplus)
        payload = (
            '{"schema":"mva.track1-evidence-ledger/v1",'
            '"ledger_id":"one","ledger_id":"two",'
            '"purpose":"A sufficiently long synthetic purpose.","entries":[]}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "ledger.json")
            path.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(EvidenceLedgerError, "duplicate JSON key"):
                load_evidence_ledger(path)

    def test_json_schema_enums_match_runtime_validator(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        properties = schema["$defs"]["evidenceEntry"]["properties"]
        expected = {
            "privacy_class": PRIVACY_CLASSES,
            "phase": PHASES,
            "phase_state": PHASE_STATES,
            "direction": DIRECTIONS,
            "assessment_status": ASSESSMENT_STATUSES,
            "source_class": SOURCE_CLASSES,
            "independent_replication": INDEPENDENT_REPLICATION_STATES,
            "decision_effect": DECISION_EFFECTS,
        }
        for field, values in expected.items():
            with self.subTest(field=field):
                self.assertEqual(set(properties[field]["enum"]), values)


if __name__ == "__main__":
    unittest.main()
