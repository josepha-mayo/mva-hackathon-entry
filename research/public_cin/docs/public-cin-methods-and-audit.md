# Methods and audit limits

The script preserves audited run02 estimators and filters. Three independent collection-day libraries per condition each pool three female larval brains; nine brains do not constitute nine expression observations. Pairing follows explicit GEO Library name and batch fields. The three comparisons are CIN/control, CDXX/CDXY and T2L/C2L; Oregon is not their matched control. Batch 6 changes workbook column order.

Each six-library contrast is normalized independently. Median-ratio references require positive counts in all six libraries; the common-reference sensitivity uses the same 8,916 genes positive in all 18 libraries. Factors are centered to geometric mean one. Each batch effect is log2((case/factor+0.5)/(control/factor+0.5)); the reported effect is the median of three paired differences. Library-sum and chromosome-specific variants retain that same count scale. Nuclear-arm normalization uses uniquely assigned X,2L,2R,3L,3R,4; Y, mitochondrial and unknown assignments stay separate.

Detection requires at least 1 CPM in at least three of six libraries, with 0.5 and 5 CPM sensitivities. CPM denominators are sums of deposited counts. Cross-series missing rows are never zero-imputed. Five normalization methods and all thresholds are retained. Average-tie rank correlations and exact sign agreement are descriptive, with no gene-as-replicate P values. Near-zero signs are unstable.

Primary side-by-side results use an identical three-way detected background on 2R,3L,3R,4: 5,599 genes, with chromosome-specific common-positive references. CIN/X rho is -0.1321923554; CIN/2L rho is +0.1398827208. The overall common universe has 8,990 genes; 8,711 pass primary three-way detection before chromosome restriction. Results are weak, contrast-dependent expression associations, not evidence of a reversible or drug-addressable mechanism.

**Later post hoc diagnostic:** stability across the recorded normalization/filter choices did not extend to omitting pool pairs. With all full-data factors, references and the same 5,599 genes held fixed, nine combinations of one omitted pair from each contrast yield CIN/X rho from -0.3414 to +0.1647 and CIN/2L rho from -0.0983 to +0.2946. These are overlapping conditional summaries, not confidence intervals or a refitted analysis. Robust biological directional alignment is not established. See [the separate post hoc note](public-cin-posthoc-pool-sensitivity.md); original plans and primary results are unchanged.

## Source and normalization limits

GSE301548 contains 8,990 rows, a strict subset of GSE290206's 14,150. Its selection rule remains unresolved after the main paper, GEO metadata and all nine public supplements were examined. Original counting annotation release, DESeq2 design, shrinkage settings and exact chromosome normalization code were not established.

The frozen five-column annotation TSV retains every original NCBI row linked to any deposited gene plus all canonical or synonym matches to the fixed panel. Source order, complete cross-reference fields, multiple mappings and panel ambiguities are preserved. All 77 deposited IDs without an original NCBI match are listed separately. The source gzip hash is recorded, but no future rolling NCBI download is required. This snapshot is not asserted to be the original counting annotation.

Supplementary Figure S5 labels its axes as log2 shrunken fold changes and compares trisomy effects before/after chromosome normalization. It displays R approximately -0.13 for CIN/X and -0.07 for CIN/2L, without identifying Pearson versus Spearman in the inspected caption/methods. The source workbook lacks a Figure S5 sheet. This capsule uses unshrunken paired-median effects and chromosome-normalizes both sides of its symmetric comparisons; it does not reproduce that estimator. A similar X coefficient or differing 2L sign cannot establish agreement with or refutation of the paper.

## Exact supplementary-table conflict

Supplementary Data 1 has different FBgn IDs for 27 of 61 shared gene symbols across its stricter and broader sheets, while all 61 retain identical P and fold-change values. For Hsp70Bb, stricter B8/C8/D8 are FBgn0013278/Hsp70Bb/3R; broader B6/C6/D6 are FBgn0260475/Hsp70Bb/3R. FlyBase identifies FBgn0260475 as CG30059/2R and FBgn0013278 as Hsp70Bb/3R. The broader sheet must not silently replace the frozen annotation or be joined by inconsistent IDs. Cause and impact on other paper results are unknown. This conflict does not invalidate the paper's biology or establish errors in GEO counts.

Keep scales distinct: the supplementary table's `fold change (shrinked)` value for Hsp70Bb is 6.6293, whereas this audit's median log2 effect is 2.7943. A signed fold convention appears likely, but its exact transform is not established in the examined table. No silent unit conversion is justified.

## Correction history and biological scope

A plan was saved before run01. Run01 used the same chromosome classes but pairwise detection masks, so its background gene sets differed between comparisons. Run02 adds an identical three-way detected subset after audit feedback. Both exact plans/scripts/results are retained; the per-gene TSV hash is unchanged. Do not present every run02 detail as fixed before any effects were viewed.

An independent audit reproduced all 150 run02 correlations and 640,264 exported effect values. That checks arithmetic, not disease-model validity. Cohorts differ in temperature; trisomy/control chronological ages differ despite reported late-L3 staging. Systemic trisomy and neuroblast-targeted bub3 RNAi affect different cell populations. Bulk composition, developmental stage and genetic background remain confounded. This is not BUB1B patient data. Hsp60 ambiguity and low-count Hsp60C are retained; mitochondrial RNA abundance is not respiration or mitochondrial quantity. No drug, functional-rescue or clinical-benefit inference follows.

Primary sources: [article](https://doi.org/10.1038/s41467-026-70521-0), [CIN GEO](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE290206), [trisomy GEO](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE301548), [public supplement bundle](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13121444/supplementaryFiles?inlineImages=false), [Hsp70Bb](https://flybase.org/reports/FBgn0013278), [CG30059](https://flybase.org/reports/FBgn0260475).
