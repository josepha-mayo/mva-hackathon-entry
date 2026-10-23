# A real NALL source-data check, with unresolved biological replication

Executed public-data reanalysis · 23 October 2026. This reproduces reported per-ROI time constants; it does not measure BUB1B response, fit drug efficacy or validate a clinical hypothesis.

The primary JCI article provides a [public source workbook](https://www.jci.org/articles/view/196137/sd/5), SHA-256 `3bcd611735652efed3b72292ea0bbad1670741e0c30235be58f6756bbcb89001`. Its sheet labeled `Fig 3I` maps to published Figure 3K by explicit GBA1-L444P condition headers, ROI counts and rounded means. Sheet `SFig7A` contains the labeled LRRK2-R1441C comparison. Blank cells are absent observations, not zeros or paired outcomes. [Primary paper](https://doi.org/10.1172/JCI196137)

| Source group | ROIs | Mean, seconds | Sample SD, seconds | Arithmetic SEM, seconds |
|---|---|---|---|---|
| GBA1 untreated | 89 | 133.161 | 49.822 | 5.281 |
| GBA1 NALL | 59 | 105.318 | 44.486 | 5.792 |
| LRRK2 untreated | 72 | 150.236 | 63.894 | 7.530 |
| LRRK2 NALL | 83 | 106.078 | 54.271 | 5.957 |

The GBA1 counts and means reproduce the main caption. Its printed ±5.3/5.8 match **SEM rather than the stated SD**. The supplemental Figure 7A caption repeats the GBA1 counts/means, which do not match its explicitly labeled LRRK2 source sheet. Preserve that discrepancy rather than silently treating the repeated caption as independent replication. These are descriptive checks on identified public files, not allegations about intent. [Supplemental material](https://doi.org/10.1172/JCI196137DS1)

The target sheets supply no culture/run/donor identifiers or grouping key. ROI counts are therefore not a biological replicate count, and spreadsheet row alignment does not establish pairing. Arithmetic SEM is reported to diagnose the caption; it is **not qualified biological uncertainty**. No cluster-aware P value, confidence interval or efficacy threshold was computed. The available trace columns stop before the recovery interval, preventing independent decay refitting. A lower mean fitted time constant also does not establish better transmitter release, network computation or whole-well useful output.

## Reproduce without changing source identity

Download the workbook from the article's data link, then run:

```sh
python scripts/audit_nall_source_data.py /path/to/JCI196137.sdval.xlsx --output nall-source-result.json
python -m unittest tests.test_nall_source_data -v
```

The [configuration](../configs/nall-source-data.json) binds source URL/checksum and exact sheet/header/count schema. The [stdlib implementation](../src/mva_hackathon/nall_source_data.py) verifies original bytes before extraction, retains source cell addresses, rejects invalid/formula/nonfinite values and exports the measured series plus descriptive checks. It performs no network request. Seven focused tests and independent extraction review support this software result, not the study's biological independence or treatment translation.

The [NALL hypothesis](levacetylleucine_challenger.md) still rests primarily on the separate randomized human A–T functional signal. That trial cannot resolve these cell-source discrepancies; these discrepancies cannot erase that clinical result. Useful BUB1B function at defensible neural exposure remains the missing experiment.
