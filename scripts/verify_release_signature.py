"""Verify the Ed25519 detached signature over release/release-artifacts.json.

Checks, in order:

1. ``attestation/release-signature-pubkey.txt`` — raw 32-byte Ed25519 public
   key, base64-encoded.
2. ``attestation/release-signature.asc`` — base64-encoded detached signature.
3. ``release/release-artifacts.json`` — the exact committed bytes that were
   signed.

Uses a pure-stdlib RFC 8032 verification so the check runs anywhere Python
does — no OpenSSL or third-party dependency required. ``attestation/VERIFY.md``
documents the equivalent ``openssl pkeyutl -verify`` recipe for reviewers who
prefer that path.

Usage: python scripts/verify_release_signature.py <repo-root>
Exit 0 on SIGNATURE OK; nonzero (fail-closed) otherwise.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

# RFC 8032 field/group constants.
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)
# Base point coordinates.
_BY = (4 * pow(5, _P - 2, _P)) % _P
_BX = None


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BX = _xrecover(_BY)
_B = (_BX, _BY)
_O = (0, 1)


def _point_add(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    (x1, y1), (x2, y2) = p, q
    denom = pow(1 + _D * x1 * x2 * y1 * y2, _P - 2, _P)
    x3 = (x1 * y2 + x2 * y1) * denom % _P
    denom2 = pow(1 - _D * x1 * x2 * y1 * y2, _P - 2, _P)
    y3 = (y1 * y2 + x1 * x2) * denom2 % _P
    return (x3, y3)


def _scalarmult(p: tuple[int, int], e: int) -> tuple[int, int]:
    if e == 0:
        return _O
    q = _scalarmult(p, e // 2)
    q = _point_add(q, q)
    if e % 2:
        q = _point_add(q, p)
    return q


def _decode_point(s: bytes) -> tuple[int, int]:
    if len(s) != 32:
        raise ValueError("bad point length")
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if bool(x & 1) != bool(s[31] & 0x80):
        x = _P - x
    pt = (x, y)
    if not _is_on_curve(pt):
        raise ValueError("point is not on the curve")
    return pt


def _is_on_curve(pt: tuple[int, int]) -> bool:
    x, y = pt
    return (-x * x + y * y - 1 - _D * x * x * y * y) % _P == 0


def _hint(data: bytes) -> int:
    import hashlib

    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def ed25519_verify(pubkey: bytes, signature: bytes, message: bytes) -> bool:
    """Return True iff ``signature`` is a valid RFC 8032 signature."""
    if len(pubkey) != 32 or len(signature) != 64:
        return False
    try:
        a = _decode_point(pubkey)
        r = _decode_point(signature[:32])
    except ValueError:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = _hint(signature[:32] + pubkey + message) % _Q
    return _scalarmult(_B, s) == _point_add(r, _scalarmult(a, h))


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    manifest = root / "release" / "release-artifacts.json"
    pubkey_path = root / "attestation" / "release-signature-pubkey.txt"
    sig_path = root / "attestation" / "release-signature.asc"
    for path in (manifest, pubkey_path, sig_path):
        if not path.is_file():
            print(f"SIGNATURE FAIL — missing {path.relative_to(root)}")
            return 2
    try:
        pubkey = base64.b64decode(pubkey_path.read_text().strip(), validate=True)
        signature = base64.b64decode(sig_path.read_text().strip(), validate=True)
    except ValueError as exc:
        print(f"SIGNATURE FAIL — base64 decode error: {exc}")
        return 2
    payload = manifest.read_bytes()
    if ed25519_verify(pubkey, signature, payload):
        print(
            "SIGNATURE OK — Ed25519 signature over "
            "release/release-artifacts.json verifies"
        )
        return 0
    print("SIGNATURE FAIL — signature does not verify against the manifest bytes")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
