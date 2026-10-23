# What the measured Aurora challenge actually shows

24 October 2026. An executed descriptive reanalysis of a public workbook, **not a simulation of drug benefit or the child's response**. All 60 published percentages and all ten means/sample SDs reproduce from the checksum-frozen source. The [JSON result](../reports/aurora_source_reanalysis.json) retains each source cell and value; the [standard-library script](../scripts/reanalyse_aurora_source.py) performs the calculation.

The source is Weaver et al., eLife 2016, Figure 7B/source data 1. It measures misalignment after an imposed attachment challenge in WT or transgenic-expression mouse embryonic fibroblasts. AZD1152-HQPA is the active compound in this experiment; it is not evidence about systemic prodrug exposure. This is neither the hypomorphic survival cohort nor an exact-child MVA model. The held-metaphase endpoint does not measure completed faithful daughters. [Primary article](https://doi.org/10.7554/eLife.16620), [public workbook](https://cdn.elifesciences.org/articles/16620/elife-16620-fig7-data1-v1.xlsx)

| Source expression group | Vehicle mean misalignment (%) | AZD mean misalignment (%) | Difference of means (percentage points) |
|---|---:|---:|---:|
| Wild-type | 4.00 | 20.00 | +16.00 |
| Full-length Bub1b | 2.67 | 12.67 | +10.00 |
| Bub1b ΔI | 6.00 | 14.67 | +8.67 |
| Bub1b ΔN | 6.00 | 18.67 | +12.67 |
| Bub1b N | 6.67 | 16.67 | +10.00 |

Every group's mean misalignment increases with the inhibitor. The paper's full-length/ΔI protection comparison is against WT under the same challenge; it is not an improvement caused by adding the drug. This is why a positive result in a different organismal endpoint cannot certify improved chromosome correction.

The caption reports six lines and at least 25 cells per line. The source provides line-level percentages without explicit line identifiers or raw cell denominators. No within-line pairing, exact cell counts, new significance tests or confidence intervals are inferred. Zeros are valid observations, not missing data. The displayed differences are contrasts of descriptive group means.

```sh
python scripts/reanalyse_aurora_source.py --source /path/to/elife-16620-fig7-data1-v1.xlsx --output /path/to/result.json
```

Source SHA-256: `62e710b61a15a697f64f57fece56de4f7ea4698422fc0790ff8ce9b841e4742d`. A changed source fails validation. Independent extraction and a separate CLI rerun reproduced the values and output. This checks source identity and arithmetic; it supplies no medicine ranking, clinical validation or assurance that the same response occurs in BUB1B patient cells.
