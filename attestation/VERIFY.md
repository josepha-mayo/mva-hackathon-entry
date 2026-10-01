# Independent verification

Everything needed to verify the release receipts is in this repository; no
private key is required or present. Commands are run from the repository
root. Python snippets are shell-agnostic; POSIX-style paths below work under
Git Bash on Windows (use `local_dev/` instead of `/tmp/` under PowerShell).

## 1. Fastest check — one command

```
python scripts/verify_track2_reproducibility.py .
# expected: GO — the bound report, pitch, code, tests, configuration,
# and receipts match their recorded digests
```

If this prints GO, the transitive manifest bound the tree state the
attestations describe. The remaining sections verify the cryptographic
binding independently.

## 2. Ed25519 detached signature over the release manifest

`release-signature-pubkey.txt` holds the raw 32-byte Ed25519 public key,
base64-encoded. `release-signature.asc` is the base64-encoded detached
signature over the exact bytes of `release/release-artifacts.json`.

```
python -c "import base64,sys;sys.stdout.buffer.write(bytes.fromhex('302a300506032b6570032100')+base64.b64decode(open('attestation/release-signature-pubkey.txt').read().strip()))" > pub.der
openssl pkey -pubin -inform DER -in pub.der -out pub.pem
python -c "import base64,sys;sys.stdout.buffer.write(base64.b64decode(open('attestation/release-signature.asc').read().strip()))" > sig.bin
openssl pkeyutl -verify -pubin -inkey pub.pem -rawin -in release/release-artifacts.json -sigfile sig.bin
# expected: Signature Verified Successfully
```

The hex prefix `302a300506032b6570032100` is the standard DER
SubjectPublicKeyInfo wrapper for an Ed25519 public key; it wraps the
published raw key.

## 3. RFC 3161 timestamp

`timestamp-proof.json` carries `rfc3161_token_hex` — the full DER-encoded
timestamp response for the release-manifest digest.

```
python -c "import json,sys;sys.stdout.buffer.write(bytes.fromhex(json.load(open('attestation/timestamp-proof.json'))['rfc3161_token_hex']))" > token.tsr
openssl ts -reply -in token.tsr -text
# check: Status Granted, message imprint equals the release-manifest sha256
```

Full chain verification additionally needs the FreeTSA CA certificates
(`cacert.pem`, `tsa.crt` from https://freetsa.org):

```
openssl ts -verify -in token.tsr -digest <release-manifest-sha256-hex> \
  -CAfile cacert.pem -untrusted tsa.crt
```

## 4. Manifest digests

```
sha256sum release/release-artifacts.json
sha256sum release/track2-reproducibility.json
```

Expected values are recorded in `attestation/operator-authorization.md` and
in `attestation/timestamp-proof.json` (`artifact_sha256` / `message_imprint`).

## 5. Re-run the bound benchmarks

```
python scripts/run_generation_selection_benchmark.py --config configs/track2-generation-selection-benchmark.json --output local_dev/track2-generation-selection.json
python scripts/run_seed_sensitivity.py --config configs/track2-seed-sensitivity.json --output local_dev/track2-seed-sensitivity.json
```

The generated receipts should match `reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json`
and `reports/TRACK2_SEED_SENSITIVITY.json` in their metric fields (the
`runtime_receipt` block reflects the run environment by design).
