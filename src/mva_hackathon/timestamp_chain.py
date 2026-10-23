"""Offline cryptographic verification of the frozen FreeTSA response.

Certificate file digests were independently checked against the official
https://freetsa.org/index_en.php on 23 October 2026. An arbitrary embedded
root is never trusted. No timestamp, upload or revocation request is made.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

CERTIFICATE_PINS = {
    "tsa.crt": "8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467",
    "cacert.pem": "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438",
}


class TimestampError(ValueError):
    pass


def find_openssl() -> str | None:
    executable = shutil.which("openssl")
    if executable:
        return executable
    if os.name != "nt":
        return None
    bundled = Path("C:/Program Files/Git/usr/bin/openssl.exe")
    return str(bundled) if bundled.is_file() else None


def _run(openssl: str, *arguments: str) -> str:
    try:
        result = subprocess.run([openssl, *arguments], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TimestampError("OpenSSL unavailable or verification timed out") from exc
    if result.returncode != 0:
        raise TimestampError("OpenSSL rejected the response, certificate extraction or signature verification")
    return result.stdout


def verify_timestamp_chain(root: Path, openssl: str | None = None) -> dict:
    root = root.resolve()
    executable = openssl or find_openssl()
    if not executable:
        raise TimestampError("OpenSSL is required; metadata matching is not cryptographic verification")
    try:
        manifest = (root / "release/release-artifacts.json").read_bytes()
        proof = json.loads((root / "attestation/timestamp-proof.json").read_text(encoding="utf-8"))
        token = bytes.fromhex(proof["rfc3161_token_hex"])
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise TimestampError("Unreadable timestamp proof or token") from exc
    digest = hashlib.sha256(manifest).hexdigest()
    if proof.get("schema") != "mva-track2-timestamp-proof/v1" or proof.get("artifact") != "release/release-artifacts.json":
        raise TimestampError("Timestamp proof names an unsupported artifact or schema")
    if proof.get("artifact_sha256") != digest:
        raise TimestampError("Declared artifact digest does not match manifest bytes")
    with tempfile.TemporaryDirectory(prefix="mva-timestamp-") as directory:
        temporary = Path(directory).resolve()
        # Verify the standard library's recursive-cleanup target before use.
        if not temporary.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise TimestampError("Unexpected temporary directory")
        response = temporary / "response.der"
        signed_data = temporary / "signed-data.der"
        response.write_bytes(token)
        parsed = _run(executable, "ts", "-reply", "-in", str(response), "-text")
        _run(executable, "ts", "-reply", "-in", str(response), "-token_out", "-out", str(signed_data))
        certificates = _run(executable, "pkcs7", "-inform", "DER", "-in", str(signed_data), "-print_certs")
        found = set()
        for block in re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", certificates, re.S):
            pem = (block.replace("\r\n", "\n") + "\n").encode("ascii")
            certificate_digest = hashlib.sha256(pem).hexdigest()
            names = [name for name, pin in CERTIFICATE_PINS.items() if pin == certificate_digest]
            if len(names) != 1 or names[0] in found:
                raise TimestampError("Unpinned or duplicate embedded certificate")
            found.add(names[0])
            (temporary / names[0]).write_bytes(pem)
        if found != set(CERTIFICATE_PINS):
            raise TimestampError("The independently pinned certificate chain is incomplete")
        verified = _run(executable, "ts", "-verify", "-in", str(response), "-digest", digest,
            "-CAfile", str(temporary / "cacert.pem"), "-untrusted", str(temporary / "tsa.crt"))
        if "Verification: OK" not in verified:
            raise TimestampError("OpenSSL did not confirm cryptographic verification")
    serial = re.search(r"^Serial number:\s*(\S+)\s*$", parsed, re.M)
    stamp = re.search(r"^Time stamp:\s*(.+)\s*$", parsed, re.M)
    if not serial or not stamp or "Status: Granted." not in parsed:
        raise TimestampError("No granted timestamp serial/time in verified response")
    try:
        actual_time = datetime.strptime(stamp.group(1).strip(), "%b %d %H:%M:%S %Y GMT").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise TimestampError("Unexpected OpenSSL timestamp representation") from exc
    time_utc = actual_time.isoformat().replace("+00:00", "Z")
    claimed = proof.get("tst", {})
    if not isinstance(claimed, dict) or claimed.get("time_stamp_utc") != time_utc or str(claimed.get("serial_number", "")).lower() != serial.group(1).lower():
        raise TimestampError("Claimed serial/time differs from the verified response")
    if claimed.get("hash_algorithm") != "sha256" or claimed.get("message_imprint") != digest:
        raise TimestampError("Claimed imprint/algorithm differs from verified manifest digest")
    return {"manifest_sha256": digest, "token_sha256": hashlib.sha256(token).hexdigest(),
        "cryptographic_signature_and_pinned_chain_verified": True,
        "serial_number": serial.group(1), "time_stamp_utc": time_utc,
        "certificate_pem_sha256_pins": CERTIFICATE_PINS,
        "pin_source": "https://freetsa.org/index_en.php", "pin_source_checked_on": "2026-10-23",
        "network_request_made": False, "revocation_status_checked": False,
        "claim_boundary": "Verification of this frozen manifest timestamp under the pinned chain and OpenSSL verifier conditions. Not a signature on new research, source validity, clinical evidence or submission approval."}
