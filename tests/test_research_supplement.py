"""Changes to bytes, diagnostics and scope cannot inherit an exact review."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_research_supplement import MANIFEST, SCHEMA, check, finding_digest


class ResearchSupplementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "release").mkdir()
        self.source = self.root / "docs/example.md"
        self.source.write_bytes(b"Public research text.\n")
        self.row = {"path": "docs/example.md", "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                    "identifier_finding_count": 0, "identifier_findings_sha256": finding_digest([])}
        self.manifest = {"schema": SCHEMA, "legacy_policy_changed": False, "files": [self.row]}
        self.save()

    def save(self):
        (self.root / MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_exact_fixture_matches_without_a_privacy_allowance(self):
        result = check(self.root)
        self.assertTrue(result["exact_reviewed_bytes_and_diagnostics_match"])
        self.assertFalse(result["privacy_allowance_granted"])

    def test_byte_change_invalidates_review_even_without_new_findings(self):
        self.source.write_bytes(self.source.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            check(self.root)

    def test_new_diagnostic_invalidates_same_bytes(self):
        with self.assertRaisesRegex(ValueError, "diagnostic changed"):
            check(self.root, lambda *args: ["non-synthetic biological identifier new diagnostic"])

    def test_non_identifier_cannot_be_accepted_even_if_prelisted(self):
        diagnostic = ["credential pattern: synthetic demonstration"]
        self.row.update(identifier_finding_count=1, identifier_findings_sha256=finding_digest(diagnostic))
        self.save()
        with self.assertRaisesRegex(ValueError, "Non-identifier"):
            check(self.root, lambda *args: diagnostic)

    def test_path_escape_rejected(self):
        self.row["path"] = "../example.md"
        self.save()
        with self.assertRaisesRegex(ValueError, "escapes"):
            check(self.root)

    def test_duplicate_path_rejected(self):
        self.manifest["files"].append(dict(self.row))
        self.save()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            check(self.root)


if __name__ == "__main__":
    unittest.main()
