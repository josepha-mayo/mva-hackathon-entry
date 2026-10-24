# Public CIN source-analysis capsule

This stages the audited run02 comparison of public Drosophila brain RNA-count deposits GSE290206 and GSE301548. It reproduces descriptive relative-expression summaries, not DESeq2, drug effects, functional rescue or patient efficacy. No external publication is performed.

**Post hoc limitation:** correlation signs change when selected pool pairs are omitted while full-data normalization and gene selection remain fixed. The original computational sensitivities do not establish robust biological direction. Read the separate post hoc note alongside the primary results.

Use Python 3.12 (the audited runtime was 3.12.14) in an isolated environment. From this directory:

```sh
python -m pip install -r requirements-public-cin.txt
python analysis/public_cin/acquire_inputs.py
python analysis/public_cin/compare_public_cin_counts.py
python analysis/public_cin/verify_results.py
```

The additional diagnostic was proposed after reviewing the primary results. It is explicitly post hoc, not part of the original plan:

```sh
python analysis/public_cin/posthoc_pool_sensitivity.py --verify
```

An optional plot reproduces the already reported primary comparison and its post hoc caveat:

```sh
python -m pip install -r requirements-public-cin-plot.txt
python analysis/public_cin/plot_public_cin_comparison.py
```

See [figure reproduction and provenance](docs/public-cin-figure.md). The inspected [SVG](figures/public_cin/cin-trisomy-relative-expression.svg) is shipped; regeneration writes SVG only under the data directory.

Each script accepts `--data-dir PATH`. Without it, inputs and regenerated results go under this project's ignored `data/public_cin/`, regardless of the current working directory. Existing input checksum mismatches stop acquisition without replacement. `acquire_inputs.py --verify-only` performs no network requests.

The acquisition script downloads only four fixed public GEO processed/metadata files (about 1.57 MB total), never FASTQ or the rolling NCBI annotation. The frozen annotation projection is included and hash checked. The 20 MB gene-effect TSV is not shipped; execution regenerates it under the data directory.

- `docs/public-cin-methods-and-audit.md`: estimators, limits, source conflicts and correction history.
- `docs/public-cin-posthoc-pool-sensitivity.md`: held-fixed quantities and interpretation of the later diagnostic.
- `fixtures/public_cin/sources.json`: exact public URLs and hashes.
- `fixtures/public_cin/gene_info_projection.tsv`: frozen annotation fields used by the original analysis.
- `results/public_cin/run02-summary.json`: slim descriptive results and explicit subset.
- `results/public_cin/posthoc-pool-sensitivity.json`: portable, path-sanitized later diagnostic; ranges are not confidence intervals.
- `provenance/public_cin/`: exact original plans, results and scripts as text for both runs.
- `verification/public_cin-verification.json`: measured capsule checks.
- `verification/public_cin-posthoc-verification.json`: separate later checks; original primary files remain unchanged.
- `manifest.json`: shipped paths and SHA-256 hashes; `manifest.sha256` hashes the manifest itself.

Verification is scoped to these listed public inputs, code and outputs. It is not a global repository or conversation-history review. This capsule is local preparation only.
