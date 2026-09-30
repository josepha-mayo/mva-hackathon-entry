# Independent verification

Everything needed to verify the release receipts is in this directory; no
private key is required or present.

## 1. Manifest digests

```
sha256sum release/release-artifacts.json
sha256sum release/track2-reproducibility.json
```

Expected values are recorded in `attestation/operator-authorization.md` and in
`attestation/timestamp-proof.json` (`artifact_sha256` / `message_imprint`).

## 2. Ed25519 detached signature over the release manifest

`release-signature-pubkey.txt` holds the raw 32-byte Ed25519 public key,
base64-encoded. `release-signature.asc` is the base64-encoded detached
signature over the exact bytes of `release/release-artifacts.json`.

One-line check (requires `openssl`):

```
python -c "import base64,sys;sys.stdout.buffer.write(bytes.fromhex('302a300506032b6570032100')+base64.b64decode(open('attestation/release-signature-pubkey.txt').read().strip()))" > /tmp/pub.der
openssl pkey -pubin -inform DER -in /tmp/pub.der -out /tmp/pub.pem
python -c "import base64,sys;sys.stdout.buffer.write(base64.b64decode(open('attestation/release-signature.asc').read().strip()))" > /tmp/sig.bin
openssl pkeyutl -verify -pubin -inkey /tmp/pub.pem -rawin -in release/release-artifacts.json -sigfile /tmp/sig.bin
# expected: Signature Verified Successfully
```

The hex prefix `302a300506032b6570032100` is the standard DER SubjectPublicKeyInfo
wrapper for an Ed25519 public key; it wraps the published raw key.

## 3. RFC 3161 timestamp

`timestamp-proof.json` carries `rfc3161_token_hex` — the full DER-encoded
timestamp response for the release-manifest digest.

```
python -c "import json,sys;sys.stdout.buffer.write(bytes.fromhex(json.load(open('attestation/timestamp-proof.json'))['rfc3161_token_hex']))" > /tmp/token.tsr
openssl ts -reply -in /tmp/token.tsr -text
# check: Status Granted, message imprint equals the release-manifest sha256
```

Full chain verification additionally needs the FreeTSA CA certificates
(`cacert.pem`, `tsa.crt` from https://freetsa.org):

```
openssl ts -verify -in /tmp/token.tsr -digest <release-manifest-sha256-hex> \
  -CAfile cacert.pem -untrusted tsa.crt
```

## 4. Reproducibility manifest

```
python scripts/verify_track2_reproducibility.py
# expected: GO: Track 2 report, pitch, code, tests, configuration, and receipt match
```
