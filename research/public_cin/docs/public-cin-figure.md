# Reproducing the public source-data figure

The shipped SVG is the exact inspected source figure, SHA-256 `09b6620d4ed59367fbab4c4a3fdf51c9b12b3d870239708b17dbaf394355e893`. It is a view of the existing run02 results, not an additional biological analysis. No binary PNG/PDF files or full effect TSV are shipped.

After regenerating the inputs and primary results using the [capsule instructions](../README.md), install the optional plotting dependency and run:

```sh
python -m pip install -r requirements-public-cin-plot.txt
python analysis/public_cin/plot_public_cin_comparison.py
```

Use `--data-dir PATH` to locate a different regenerated effect table. The script reads the exact frozen primary result JSON from `provenance/public_cin/run02/` and the portable post hoc diagnostic from `results/public_cin/`; both are hash checked. It reads the regenerated TSV under the data directory, also hash checked. SVG and its figure manifest are written to `data/public_cin/figures/` by default, never over the shipped figure. No machine-specific path is serialized.

The code preserves the original plot's data expressions, hexbin settings, limits, layout, labels, coefficients and caveat. Only paths/loading/provenance and the SVG-only output selection change. The original plot-script hash is `94820ffb61ee2953ac86f392bf4b8dd1e8d2c225ab2fbb27e77e99784fb350e3`.

Both panels use the same frozen 5,599 genes on nuclear arms 2R, 3L, 3R and 4, with run02 chromosome/common-reference effects. Displayed descriptive Spearman coefficients are -0.132 for CIN/X and +0.140 for CIN/2L. The axes are median log2 differences in normalized counts; colour encodes genes per hexagon on a log scale. Three matched collection-day pools per condition are the biological units.

The neutral title and explicit caveat are retained: a separate **post hoc** omission of collection-day pairs can reverse either correlation sign. The figure is not DESeq2 reproduction, drug response, patient benefit or evidence of robust biological direction. The underlying post hoc ranges are conditional summaries, not confidence intervals.

The portable diagnostic retains the exact scientific values of the original reviewer result (source SHA-256 `9b7863b5649577412061e5d30fab32b4889863a332846c2c5440e151b3574f6a`); its sanitized file has a separate recorded hash. See `figures/public_cin/figure-provenance.json` and `verification/public_cin-plot-verification.json` for source and regeneration checks. SVG byte hashes can change on regeneration because Matplotlib emits creation metadata and generated element IDs; the inspected shipped SVG remains frozen and separately identified.
