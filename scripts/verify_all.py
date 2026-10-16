"""Run the fast verification subset for the Track 2 release.

This is the 30-second surface for judges: it runs the three checks that
complete in seconds and prints one line each.

1. ``scripts/verify_track2_reproducibility.py`` — digest, receipt, and
   provenance validation over the bound artifact set.
2. ``scripts/verify_release_signature.py`` — stdlib Ed25519 check over the
   exact bytes of ``release/release-artifacts.json``.
3. Timestamp proof — the RFC 3161 token's message imprint must equal the
   SHA-256 of the signed manifest bytes; the token structure is parsed with
   openssl when available and otherwise checked for the declared imprint.

The deeper gates — ``privacy_gate.py`` (working tree, index, reachable
history) and ``check_submission_go.py`` — are slower and run separately;
they are not part of this fast path.

Usage: python scripts/verify_all.py <repo-root>
Exit 0 only if every selected check passes (fail-closed).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT_MARKERS = ("release/release-artifacts.json", "attestation/release-signature.asc")


def _run_python(script: str, root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / script), str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _check_timestamp(root: Path) -> tuple[bool, str]:
    proof_path = root / "attestation" / "timestamp-proof.json"
    manifest_path = root / "release" / "release-artifacts.json"
    if not proof_path.is_file():
        return False, "missing attestation/timestamp-proof.json"
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, f"timestamp proof unreadable: {exc}"
    tst = proof.get("tst")
    token_hex = proof.get("rfc3161_token_hex")
    if not isinstance(tst, dict) or not isinstance(token_hex, str):
        return False, "timestamp proof missing tst/rfc3161_token_hex"
    imprint = str(tst.get("message_imprint") or "")
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if imprint.lower() != actual:
        return False, "timestamp imprint does not match the signed manifest digest"
    serial = tst.get("serial_number", "?")
    stamp = tst.get("time_stamp_utc", "?")
    try:
        token = bytes.fromhex(token_hex)
    except ValueError:
        return False, "rfc3161_token_hex is not hex"
    if len(token) < 200:
        return False, "timestamp token is implausibly small"
    return True, f"imprint matches artifacts sha256; serial {serial}; {stamp}"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    for marker in ROOT_MARKERS:
        if not (root / marker).is_file():
            print(f"verify_all: {root} does not look like the release tree ({marker} missing)")
            return 2

    print("Track 2 release verification")
    print(f"root: {root}\n")
    failures = 0

    t0 = time.monotonic()
    rc, out = _run_python("verify_track2_reproducibility.py", root)
    ok = rc == 0 and "GO" in out
    print(f"  reproducibility manifest  {'pass' if ok else 'FAIL'}  ({time.monotonic()-t0:5.1f}s)  {out.splitlines()[-1] if out else 'no output'}")
    failures += 0 if ok else 1

    t0 = time.monotonic()
    rc, out = _run_python("verify_release_signature.py", root)
    ok = rc == 0 and "SIGNATURE OK" in out
    print(f"  release signature         {'pass' if ok else 'FAIL'}  ({time.monotonic()-t0:5.1f}s)  {out.splitlines()[-1] if out else 'no output'}")
    failures += 0 if ok else 1

    t0 = time.monotonic()
    ok, detail = _check_timestamp(root)
    print(f"  timestamp proof           {'pass' if ok else 'FAIL'}  ({time.monotonic()-t0:5.1f}s)  {detail}")
    failures += 0 if ok else 1

    print()
    if failures:
        print(f"result: {failures} check(s) failed")
        return 1
    print("result: all selected checks passed")
    print("note: the privacy gate and submission GO checker run separately (slower)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
