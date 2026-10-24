# POST HOC pool-pair sensitivity diagnostic

This diagnostic was proposed by an independent reviewer **after the primary results were available**. It is not part of the original plan or a preregistered analysis. It leaves the original run02 results and files unchanged.

The primary correlation signs persisted across the recorded normalization and detection sensitivities. They do **not** persist across this later pool-pair omission diagnostic. A stable biological direction of model-to-model expression alignment is therefore not established by these data.

## Exact held-fixed quantities

The input is the exact audited `all-gene-descriptive-effects.tsv`, SHA-256 `364d2840e4db304d13c5ff0626130dbc556757ad3d26a3e03178a9422bd849ca`. Only rows from `chromosome_common_reference` are used.

- Size factors remain those estimated from all six libraries per contrast within each nuclear arm. **They are not re-estimated after omission and still contain information from the omitted libraries.**
- The 8,916-gene common-positive reference universe, its per-arm subsets, the frozen annotation and the 0.5 normalized-count pseudocount remain fixed.
- Detection remains the full-data rule: at least 1 CPM in at least three of six libraries in each of all three contrasts. No genes are re-filtered after omission.
- Every correlation uses the identical frozen 5,599-gene background on 2R, 3L, 3R and 4. The shipped gene-ID list is checked exactly.

The script first correlates paired-effect vectors from collection days 4, 5 and 6 within each contrast. It then independently omits one matched control/case collection-day pair from CIN and one from the other contrast, enumerating all 3×3 combinations. Reused batch labels are not treated as matching dates across series. Each gene is summarized by the median of its two remaining paired log2 effects—numerically their arithmetic mean—and the two vectors are compared using average-tie rank correlation.

A dropped pair means two pooled-library observations, one control and one case. It does not mean dropping one individual brain. Each library still represents a pool of three brains.

## Results

Within-CIN paired-effect rank correlations are 0.03296 (days 4/5), 0.26785 (4/6) and 0.29999 (5/6). Low agreement is a limitation of the observed aggregate effects; it does not independently identify a faulty library or authorize excluding an outlier.

| Cross-contrast diagnostic | Minimum of nine summaries | Maximum of nine summaries |
|---|---:|---:|
| CIN versus X trisomy | −0.3414181400 | +0.1646698785 |
| CIN versus 2L trisomy | −0.0983233646 | +0.2945981943 |

These are **ranges of nine overlapping, deterministic summaries**, not confidence intervals, P values, independent experiments or a sampling distribution. Holding full-data preprocessing fixed makes this a conditional diagnostic, not a complete pipeline refit or independent validation. With three pool pairs, aggregation changes from a median of three to a median/mean of two; both pair selection and that two-pair summary matter.

Neither the primary coefficients nor this diagnostic establishes a drug mechanism, functional rescue, clinical efficacy or BUB1B patient behavior. The sign changes weaken any biological-direction inference from the earlier computational sign stability; they do not refute all findings in the source paper.

## Reproduction

After regenerating the primary effect export:

```sh
python analysis/public_cin/posthoc_pool_sensitivity.py --verify
```

Use `--data-dir PATH` for a different input/output directory. The result stores logical project-relative paths, never the supplied machine-specific path. The script writes `posthoc-pool-sensitivity.json` under the data directory and checks its scientific values against the shipped portable result when `--verify` is given. It uses the already declared NumPy dependency and the primary script's average-tie rank helper; no new package is required.

Original reviewer script SHA-256: `e556a248d31490fd1b65db7aa771e7c90f44dab5e3ab6e2bef2d1daf3fd26d98`. Separate origin and verification records document the exact comparison with that reviewer result and the preserved primary files.
