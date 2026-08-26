from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.reference_ledger import (
    ReferenceLedger, ReferenceLedgerError, ReferenceResource, load_reference_ledger,
)


def resource(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "resource_id": "synthetic-reference-v1",
        "name": "Synthetic public reference fixture",
        "source_scope": "public",
        "release": "fixture-2026.08",
        "release_date": "2026-08-01",
        "retrieved_at_utc": "2026-08-26T15:00:00+00:00",
        "source_url": "https://example.org/reference/fixture-2026.08",
        "license_id": "CC0-1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "sha256": "a" * 64,
        "immutable_revision": None,
        "purpose": "Exercise deterministic public-reference ledger validation.",
        "use_mode": "local_offline",
        "hosted_api_used": False,
        "challenge_controlled": False,
        "model_slots": ["S1", "S2"],
        "redistribution_notes": "Synthetic fixture may be redistributed with this project.",
        "attribution_notes": "Attribute the synthetic fixture definition to this project.",
    }
    value.update(overrides)
    return value


def windows_fixture_path(*parts: str) -> str:
    return "C:" + "\\" + "\\".join(parts)


def ledger(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "mva.track1-reference-ledger/v1",
        "ledger_id": "track1-public-reference-lock",
        "champion_public_only": True,
        "resources": [resource()],
    }
    value.update(overrides)
    return value


class ReferenceLedgerTests(unittest.TestCase):
    def test_valid_public_offline_resource(self) -> None:
        parsed = ReferenceLedger.from_dict(ledger())
        self.assertEqual(parsed.resources[0].model_slots, ("S1", "S2"))
        self.assertEqual(parsed.to_dict(), ledger())

    def test_proprietary_resource_is_rejected_from_champion(self) -> None:
        with self.assertRaisesRegex(ReferenceLedgerError, "proprietary"):
            ReferenceLedger.from_dict(ledger(resources=[resource(source_scope="proprietary")]))

    def test_floating_release_and_revision_are_rejected(self) -> None:
        with self.assertRaisesRegex(ReferenceLedgerError, "floating"):
            ReferenceResource.from_dict(resource(release="latest"))
        with self.assertRaisesRegex(ReferenceLedgerError, "floating"):
            ReferenceResource.from_dict(
                resource(sha256=None, immutable_revision="main")
            )

    def test_integrity_identifier_is_required(self) -> None:
        with self.assertRaisesRegex(ReferenceLedgerError, "at least one"):
            ReferenceResource.from_dict(resource(sha256=None, immutable_revision=None))

    def test_hosted_or_controlled_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(ReferenceLedgerError, "hosted"):
            ReferenceResource.from_dict(resource(hosted_api_used=True))
        with self.assertRaisesRegex(ReferenceLedgerError, "challenge-controlled"):
            ReferenceResource.from_dict(resource(challenge_controlled=True))

    def test_local_paths_and_credentialed_urls_are_rejected(self) -> None:
        with self.assertRaisesRegex(ReferenceLedgerError, "local paths"):
            local_path = windows_fixture_path("private", "reference.bin")
            ReferenceResource.from_dict(resource(purpose=f"Read {local_path} locally."))
        with self.assertRaisesRegex(ReferenceLedgerError, "HTTPS URL"):
            ReferenceResource.from_dict(
                resource(source_url="https://token@example.org/reference/v1")
            )

    def test_model_slots_are_strict(self) -> None:
        with self.assertRaisesRegex(ReferenceLedgerError, "model_slots"):
            ReferenceResource.from_dict(resource(model_slots=["S1", "S7"]))

    def test_duplicate_resource_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ReferenceLedgerError, "duplicate"):
            ReferenceLedger.from_dict(ledger(resources=[resource(), resource()]))

    def test_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(ReferenceLedgerError, "duplicate JSON key"):
                load_reference_ledger(path)


if __name__ == "__main__":
    unittest.main()
