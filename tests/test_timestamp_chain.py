"""The genuine frozen response must pass; metadata and malformed tokens cannot."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mva_hackathon.timestamp_chain import TimestampError, find_openssl, verify_timestamp_chain

REPO = Path(__file__).resolve().parents[1]
OPENSSL = find_openssl()


@unittest.skipUnless(OPENSSL, "OpenSSL required; absence does not count as verification")
class TimestampChainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mva-ts-test-")
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(self.temporary.cleanup)
        (self.root / "release").mkdir()
        (self.root / "attestation").mkdir()
        self.manifest = self.root / "release/release-artifacts.json"
        self.manifest.write_bytes((REPO / "release/release-artifacts.json").read_bytes())
        self.proof = json.loads((REPO / "attestation/timestamp-proof.json").read_text())
        self.save()

    def save(self):
        (self.root / "attestation/timestamp-proof.json").write_text(json.dumps(self.proof), encoding="utf-8")

    def test_genuine_frozen_response_verifies_against_pinned_chain(self):
        result = verify_timestamp_chain(self.root)
        self.assertTrue(result["cryptographic_signature_and_pinned_chain_verified"])
        self.assertEqual(result["time_stamp_utc"], "2026-10-16T11:19:45Z")
        self.assertFalse(result["network_request_made"])

    def test_non_der_blob_cannot_pass_with_matching_json_imprint(self):
        self.proof["rfc3161_token_hex"] = (b"synthetic invalid timestamp " * 20).hex()
        self.save()
        with self.assertRaises(TimestampError):
            verify_timestamp_chain(self.root, OPENSSL)

    def test_signature_tampering_is_rejected(self):
        token = bytearray.fromhex(self.proof["rfc3161_token_hex"])
        token[-1] ^= 1
        self.proof["rfc3161_token_hex"] = token.hex()
        self.save()
        with self.assertRaises(TimestampError):
            verify_timestamp_chain(self.root, OPENSSL)

    def test_changed_manifest_cannot_be_approved_by_rewriting_metadata(self):
        self.manifest.write_bytes(self.manifest.read_bytes() + b" ")
        digest = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.proof["artifact_sha256"] = digest
        self.proof["tst"]["message_imprint"] = digest
        self.save()
        with self.assertRaises(TimestampError):
            verify_timestamp_chain(self.root, OPENSSL)

    def test_claimed_time_must_match_cryptographically_verified_response(self):
        self.proof["tst"]["time_stamp_utc"] = "1900-01-01T00:00:00Z"
        self.save()
        with self.assertRaisesRegex(TimestampError, "serial/time"):
            verify_timestamp_chain(self.root, OPENSSL)


class TimestampDiscoveryTests(unittest.TestCase):
    def test_windows_fallback_cannot_resolve_a_checkout_relative_posix_path(self):
        with patch("mva_hackathon.timestamp_chain.shutil.which", return_value=None), \
             patch("mva_hackathon.timestamp_chain.os.name", "posix"), \
             patch("mva_hackathon.timestamp_chain.Path") as path:
            self.assertIsNone(find_openssl())
            path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
