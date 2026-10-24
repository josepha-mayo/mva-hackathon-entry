Declared UTC: 2026-10-24T12:52:42.942315+00:00

# Public fly-count analysis plan

Question: do within-cohort relative-expression contrasts support transferring a simple-trisomy neural stress mechanism to complex chromosome instability? This is a descriptive source-data check, not a drug-response experiment or clinical simulation. Primary paper: doi10.1038/s41467-026-70521-0. Public GEO series: GSE290206 and GSE301548. Sources have been acquired and metadata inspected; no contrasts have been calculated.

Map workbook columns to explicit Library name metadata, never column order. Require unique gene IDs, nonnegative integer counts, complete genotype/batch mapping, and matched three-day sets. Contrasts: CIN/control, CDXX/CDXY, T2L/C2L. Oregon is not a substitute matched control. Three pools per condition, each containing three brains, are three expression units rather than nine. The cohorts differ in temperature; trisomy/control chronological ages differ although late larval stage is reported. Never pool absolute counts across series.

Normalize each six-library contrast separately using median ratios over genes positive in all six samples. Record size factors/reference-gene count. Compute paired normalized log2 differences with pseudocount0.5; retain three pool contrasts and their median. This is not DESeq2 estimation or reproduction of the paper's P values. Primary detection filter: at least1CPM in at least three of six libraries. Sensitivities:0.5/5CPM and library-sum normalization. Compare intersecting gene IDs only; do not impute missing deposited rows as zeros. Report cross-contrast Spearman correlations/directional agreement descriptively without gene-as-replicate P values.

Inspect a fixed mechanistic panel from the publication: bub3; Hsp70Ba/Bb/Bc/Bbb; Hsp60/Hsp60c; Sod2/GTPx-1; pros/dpn/wor/Myc. Freeze an official annotation, preserve missing/multiple mappings and examine mitochondrial-genome coverage if possible. Inspect whether cross-contrast agreement depends on trisomic-chromosome genes only if annotation supports it. This is a targeted check of published claims, not unbiased drug discovery.

Cell mixture, development, RNAi and relative normalization limit interpretation. No per-cell RNA/protein-load inference without spike-ins. Shared expression supports only part of an analogy; divergence weakens a blanket transfer without disproving common mechanisms. Neither result establishes drug rescue, a medicine rank or patient benefit. Stop if sample identity/count validity cannot be qualified. Preserve null/adverse findings and do not tune settings to match the expected result.

## Pre-execution amendment after independent design review

UTC 2026-10-24T13:23:30.074586+00:00

The publication normalizes trisomy contrasts chromosome by chromosome. Global median-ratio results estimate a different quantity. Retain them as descriptive sensitivities, and require chromosome-stratified and off-trisomic-arm comparisons before discussing mechanism similarity. Normalize both sides of a chromosome-stratified comparison within the same chromosome assignment. Exclude and report ambiguous/unknown assignments. This is not reproduction of the paper's DESeq2 analysis.

The trisomy workbook's8,990 rows are a strict subset of the CIN workbook's14,150; row-selection provenance is unresolved. Add common-positive-reference normalization as a sensitivity to differing row sets. The independent audit identifies8,916 genes positive in all18 relevant libraries and8,711 in the primary shared CPM universe; verify these counts independently. Do not infer zero expression from absent rows.

Scale library-sum size factors to geometric mean1 before adding pseudocount0.5 in count units. Prefer canonical symbol matches over aliases; preserve Hsp60's ambiguous alias mappings unless primary provenance resolves them. No broad pathway/drug ranking follows from the covered genes. Conclusions remain conditional on row selection, annotation, normalization, development and cell composition.

Pre-execution implementation clarification, 24 October 2026: chromosome-stratified factors use uniquely assigned nuclear arms X, 2L, 2R, 3L, 3R and 4 only. Mitochondrial, Y, ambiguous and unknown genes are reported separately, not silently classified as off-dosage. Compare off-X (also excluding Y), off-2L, and a common non-X/non-Y/non-2L nuclear background. Use both all-positive-within-contrast and common-positive reference sensitivities within each arm, along with global median, common-reference and library-sum factors. Report marker-panel ambiguity rather than choosing the most favorable match. These are declared before effect calculations.
