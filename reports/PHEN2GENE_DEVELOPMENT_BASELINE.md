# Phen2Gene development baseline

## Claim boundary

Phen2Gene is retained here as a **development-only historical comparator**. It is not the Track 1 champion, not evidence of clinical validity, and not suitable for patient care. The knowledge snapshot is identified by the upstream README as **January 2021**, so this receipt must not be presented as a current gene-disease knowledge evaluation.

This execution read 64 selected cases from a public release and nothing else:

- development cases read: **64**;
- calibration cases read: **0**;
- held-out test cases read: **0**;
- controlled patient files read: **0**;
- network calls during inference: **0**.

No controlled challenge data, participant output, account state, machine path, patient identifier, case-level phenotype bundle, or case-level result is included in this repository.

## Exact public pins

| Component | Public release and content pin | Reuse boundary |
|---|---|---|
| Phen2Gene source | [Official repository](https://github.com/WGLab/Phen2Gene), commit `47ab30af0751ff4d2060e9bf241c0a758cd0d7a3`, tree `9000a260e6b0db22385e43097440fe911bfe3c04` | MIT License; cite the [official paper](https://doi.org/10.1093/nargab/lqaa032) |
| Phen2Gene knowledge base | [Release 1.1.0](https://github.com/WGLab/Phen2Gene/releases/tag/1.1.0), [official asset](https://github.com/WGLab/Phen2Gene/releases/download/1.1.0/H2GKBs.zip), 597,808,012 bytes, SHA-256 `d4b9dafca83aafac17e49b6ed7fa949572dc11fa565ec082a38b0b2819aabee0` | January 2021 historical snapshot; keep local and do not redistribute the bundle without a separate rights review |
| Extracted knowledge tree | 42,777 files, 2,028,082,850 bytes, portable tree SHA-256 `5e69f096ec1433633d7211bee4741cf66f64731a321883d2bba279d84e9702c2` | Digest covers sorted relative path, byte count, and per-file SHA-256 records; no tree content is published here |
| Public cases | [Phenopacket Store 0.1.27](https://github.com/monarch-initiative/phenopacket-store/releases/tag/0.1.27), tag commit `3f3619800b2c949f8bfb457a122346c2fae7e482` | [BSD 3-Clause License](https://github.com/monarch-initiative/phenopacket-store/blob/0.1.27/LICENSE) |
| Public case archive | [Official release asset](https://github.com/monarch-initiative/phenopacket-store/releases/download/0.1.27/all_phenopackets.zip), 19,431,098 bytes, SHA-256 `d0c70005bb09b87035087516252b6b539fbc0415be7c664b73c9cde7eedf205a` | Acquired outside the public repository; not redistributed here |
| Sealed development selector | 64 cases, 64 unique genes, 64 unique archive entries; SHA-256 `84f8a7811d0f85678c45475093151ab40b0b2b6939437b369ac1355b485ce7e5` | Case-level selector remains outside this publication tree; the adapter accepts only this exact digest |

Git remote HEAD matched the pinned source commit on 2026-08-26, and the checkout was clean before and after the development execution. GitHub did not publish a digest for the knowledge-base asset; its SHA-256 above is this audit's content pin, not an upstream checksum attestation.

The Phen2Gene source is covered by its MIT License. The release page and downloaded knowledge bundle did not state one aggregate license covering every bundled upstream source. For that reason, this repository publishes only URLs, release identifiers, byte counts, and cryptographic receipts. It does **not** contain the archive, extracted tree, derived file manifest, or copied knowledge-base rows.

## Leakage-safe adapter contract

The checked-in [configuration](../configs/phen2gene-development-baseline.json) contains only public URLs, versions, hashes, aggregate counts, and evaluation settings. The data-free [runner](../scripts/run_phen2gene_development.py) has no calibration, test, controlled-data, upload, or submission mode.

Before inference, the runner fails closed unless all of the following hold:

1. the official source checkout is clean and at the exact commit;
2. the separately acquired knowledge archive matches its byte count and SHA-256;
3. the complete extracted tree matches its file count, byte count, and portable tree digest;
4. the public Phenopacket archive matches its byte count and SHA-256;
5. the selector matches its SHA-256, declares `development_smoke`, contains exactly 64 unique archive entries and 64 unique genes, and every identifier hashes to the development partition;
6. no candidate-gene restriction is active and the `sk` weight model is unchanged;
7. the output path does not already exist.

The split salt is constructed from the four literal components **MVA**, **PPS**, **0.1.27**, and **v1**, joined by hyphens. The first 60% of the first-eight-byte SHA-256 bucket space is development, the next 20% calibration, and the final 20% test. The public runner can execute development only; it cannot select the other partitions.

The runner writes aggregate metrics and digests, never case identifiers, causal gene symbols, phenotype terms, or machine-local paths. Its tests construct a temporary fake official API, tiny invented knowledge tree, and `SYN`-namespaced truth. They exercise deterministic repetition, split rejection, source dirtiness, selector tampering, tree tampering, overwrite refusal, and zero calibration/test/patient access without downloading any public or controlled data.

## Why the adapter calls the official API

The documented command-line custom-database option is unreachable in a clean checkout: `phen2gene.py` checks `lib/h2gpath.config` and exits before parsing `-d/--database`. Mutating the official checkout to install a machine path would invalidate the clean-source receipt.

The adapter therefore imports the pinned official module and calls its public `results()` API, the same calculation and ranking path called by the command-line wrapper. The API was sanity-checked against the single-term example in the upstream README before the development run. No Phen2Gene ranking code is copied into this repository.

The aggregate metrics below were produced by the completed audit adapter. The checked-in runner is its sanitized, data-free portability implementation and was validated here only with synthetic fixtures; this publication pass did not rerun the 64 public cases. Its output schema intentionally omits case-level fields and its default full-tree re-hash is stricter than the per-run manifest check used by the completed audit. Consequently, a future public-runner core digest is not expected to equal the audit-internal digest below; the exact pins and metric values are the cross-implementation comparison contract.

## Development result

Configuration: 64 cases and 64 genes; `sk` weighting; unrestricted candidate universe; excluded phenotype terms omitted; 2,000 nonparametric case-bootstrap replicates; seed `20260826`; percentile 95% confidence intervals. A truth absent from the returned universe counts as a miss and reciprocal rank zero.

| Metric | Point estimate | 95% case-bootstrap interval | Count |
|---|---:|---:|---:|
| Truth-universe coverage | 0.843750 | not bootstrapped | 54 / 64 |
| Top-1 | 0.109375 | [0.046875, 0.187500] | 7 / 64 |
| Top-3 | 0.140625 | [0.062500, 0.234375] | 9 / 64 |
| Top-5 | 0.140625 | [0.062500, 0.234375] | 9 / 64 |
| Top-10 | 0.250000 | [0.140625, 0.359375] | 16 / 64 |
| Mean reciprocal rank | 0.141089 | [0.071386, 0.228334] | 64 cases |
| Median rank among present truths | 531 | not bootstrapped | 54 present truths |

Ten truth genes were absent from the returned candidate universe. Candidate counts ranged from 10,342 to 20,297. Official rank means the one-based insertion position returned by Phen2Gene. Four cases differed under pessimistic end-of-tie ranking, with a maximum tie width of 1,145; Top-1/3/5/10 did not change. Pessimistic mean reciprocal rank was 0.141084 with 95% interval [0.071377, 0.228325].

The two completed development executions produced the same canonical aggregate-and-rank core digest: `e67f4450b7d506f748f2b88ab11d726c6c6d50b200813d94d1681c741d4d2740`.

## Unsupported negative phenotype evidence

Phen2Gene accepts positive HPO terms but does not provide a negative-term interface. Fifty of 64 development cases contained excluded phenotype evidence, totaling 572 terms. The adapter omitted those terms and recorded their aggregate count. It did not invert, soften, or silently treat them as positive evidence. This unsupported evidence channel is a material limitation of the comparator.

## Official acquisition and execution contract

The knowledge bundle and public case archive must remain outside the repository. The following PowerShell contract uses a caller-supplied external public-reference root; it does not upload, publish, or submit anything.

```powershell
$refs = (Get-Item -LiteralPath $env:MVA_PUBLIC_REFS).FullName
$source = Join-Path $refs 'phen2gene-source'
$release = Join-Path $refs 'phen2gene-release-1.1.0'
$kbArchive = Join-Path $release 'H2GKBs.zip'
$kb = Join-Path $release 'kb'
$packets = Join-Path $refs 'phenopacket-store-0.1.27.zip'
$selector = Join-Path $refs 'development-selector.json'
$receipt = Join-Path $refs 'development-receipt.json'

git clone https://github.com/WGLab/Phen2Gene.git $source
git -C $source checkout --detach 47ab30af0751ff4d2060e9bf241c0a758cd0d7a3
New-Item -ItemType Directory -Path $release | Out-Null
curl.exe -L --fail --retry 5 --output $kbArchive https://github.com/WGLab/Phen2Gene/releases/download/1.1.0/H2GKBs.zip
curl.exe -L --fail --retry 5 --output $packets https://github.com/monarch-initiative/phenopacket-store/releases/download/0.1.27/all_phenopackets.zip

if ((Get-Item -LiteralPath $kbArchive).Length -ne 597808012) { throw 'knowledge archive byte mismatch' }
if ((Get-FileHash -LiteralPath $kbArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'd4b9dafca83aafac17e49b6ed7fa949572dc11fa565ec082a38b0b2819aabee0') { throw 'knowledge archive digest mismatch' }
if ((Get-Item -LiteralPath $packets).Length -ne 19431098) { throw 'public case archive byte mismatch' }
if ((Get-FileHash -LiteralPath $packets -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'd0c70005bb09b87035087516252b6b539fbc0415be7c664b73c9cde7eedf205a') { throw 'public case archive digest mismatch' }

Expand-Archive -LiteralPath $kbArchive -DestinationPath $kb
uv python install 3.8
uv venv --python 3.8 (Join-Path $refs 'phen2gene-runtime')
uv pip install --python (Join-Path $refs 'phen2gene-runtime/Scripts/python.exe') 'numpy==1.17.3'

& (Join-Path $refs 'phen2gene-runtime/Scripts/python.exe') scripts/run_phen2gene_development.py `
  --config configs/phen2gene-development-baseline.json `
  --repo $source `
  --kb-archive $kbArchive `
  --kb $kb `
  --phenopacket-archive $packets `
  --selector $selector `
  --output $receipt
```

The sealed selector is intentionally not published because it contains case-level biological labels that this repository's publication gate forbids. A local selector is accepted only if it matches the recorded SHA-256. The runner re-hashes the entire extracted knowledge tree, so first-run validation is dominated by small-file I/O rather than inference.

## Decision

**GO:** keep Phen2Gene as a reproducible historical comparator and methods transparency artifact.

**NO-GO:** do not promote it to champion, calibration, or held-out evaluation. It has a January 2021 knowledge snapshot, 84.375% truth-universe coverage, unsupported negative phenotype evidence, Top-10 of 25%, and a mean reciprocal-rank lower confidence bound of 0.071386. Calibration and held-out test remain sealed until a stronger development method passes a predeclared promotion gate.
