# When lower aneuploidy is not rescue

## An exposure-gated arimoclomol screen with generation-versus-selection deconvolution for a BUB1B-associated MVA hypothesis

**Entry:** Joseph Mayo
**Track:** 2 — drug repositioning
**Version:** 2026-08-26 evidence freeze
**License:** CC BY 4.0
**Scope:** preclinical research prioritization only

This report proposes a falsifiable ex-vivo screen, not a treatment, prescription, clinical-trial recommendation, or claim of cure. No medicine described here should be given to the child on the basis of this work. Research results require confirmation through an appropriately qualified clinical genetics team and validated laboratory.

## Executive decision

**Single lead:** arimoclomol, used only as an exposure-gated ex-vivo probe.

**Why this lead:** if the uncharacterized p.Asn1002Lys allele proves to be an expressed, fold-unstable but intrinsically functional BUBR1 hypomorph, stress-dependent chaperone amplification could raise functional BUBR1 abundance. MIPLYFFA's FDA indication is for use in combination with miglustat for a different disease, and its current label provides estimated pediatric steady-state serum concentrations. Unrelated preclinical cell studies report improved biochemical processing and activity of mutant GCase or reduced aggregation of transfected P23H rhodopsin; neither constitutes BUBR1 evidence, patient rescue, or clinical benefit.

**Why this is not yet a drug answer:** there is no direct arimoclomol evidence for BUB1B, p.Asn1002Lys, MVA, spindle-checkpoint rescue, or chromosome-segregation rescue. Pharmacologic HSP90 inhibition depleted the tested unstable I909T and L1012P BUBR1 constructs, whereas arimoclomol studies most clearly document stress-contingent HSP70-family induction. This is an unproven chaperone bridge, not a demonstrated target match. The current FDA-approved label says arimoclomol's clinical mechanism in NPC is unknown. Published Gaucher-cell studies used nominal culture concentrations far above the label-estimated pediatric mean serum peak.

**Exposure rule:** all micromolar values below are culture-media concentrations, not patient dosing instructions. Test 0.2, 0.5, 1, and 2 micromolar as the primary concentration window. Only a result at no more than 2 micromolar can satisfy the concentration gate, and only after exposure duration, unbound medium concentration, and intracellular exposure are characterized. Five micromolar is mechanistic exploration and cannot advance the candidate by itself; a signal confined to 50–100 micromolar or above is a repositioning **NO-GO**.

**Biological rule:** first confirm that the variants are in trans and that p.Asn1002Lys causes an exact-allele defect. Cis phase or a functionally WT-like missense allele rejects the submitted causal chain. If exact correction fails across independent, quality-controlled clones, causal attribution remains unresolved and the program does not advance; one failed edit or clone is not sufficient to declare biological falsification.

**Outcome rule:** lower bulk aneuploidy is not accepted as rescue. In a founder cohort enrolled before treatment, first-division errors must fall both per completed division and per enrolled founder while division completion remains equivalent. Daughter outcome, abnormal-clone fitness, toxicity, and final aneuploid fraction are measured separately.

**Decision now:** GO only for orthogonal confirmation and direct phase (Gates 0–1). Hold RNA, editing, and every drug experiment until those gates pass; hold arimoclomol specifically until trans phase and an exact N1002K stability defect are demonstrated. NO-GO for administration, dosing, combination therapy, or any cure claim.

## 1. What is observed, inferred, and unknown

The Track 1 research hypothesis contains two heterozygous *BUB1B* calls on the shared MANE Select transcript NM_001211.6:

1. `c.2210T>G`, p.(Leu737Ter), a premature-stop allele; and
2. `c.3006T>G`, p.(Asn1002Lys), an uncharacterized missense allele.

The following evidence labels are deliberately noninterchangeable.

| Link in the causal chain | Current status | What the evidence supports | What it does not support |
|---|---|---|---|
| Both calls exist in the supplied single-sample call set | Observed in challenge data | A two-variant research candidate | Orthogonal confirmation, germline origin, or phase |
| p.Leu737Ter is loss-of-function-compatible | Public database plus inference | A nonsense allele in a gene where loss of function is disease-relevant | Participant-specific NMD, zero protein, or clinical causality |
| p.Asn1002Lys lies in the C-terminal BUBR1 domain | Sequence/domain fact | A plausible region for structural or functional disruption | Instability, pathogenicity, or HSP responsiveness |
| The pair is in trans | Unknown | Nothing yet | Compound heterozygosity cannot be claimed until measured |
| p.Asn1002Lys lowers abundance or half-life | Unknown | A testable hypothesis based on other BUBR1 missense alleles | Exact-allele mechanism |
| The pair impairs chromosome segregation | Unknown for this genotype | A mechanistically coherent experiment | Diagnosis or phenotype attribution |
| Arimoclomol restores exact-allele function | Unknown | A screening question | Treatment efficacy or clinical benefit |

### 1.1 Precision on the ClinVar anchor

As of 2026-08-26, [ClinVar VCV000533901.9](https://www.ncbi.nlm.nih.gov/clinvar/variation/533901/) shows a germline Pathogenic/Likely pathogenic variant-level aggregate with criteria provided, multiple submitters, no conflicts, two contributing submissions, and two-star review status. The MVA1-specific [RCV000641226.9](https://www.ncbi.nlm.nih.gov/clinvar/RCV000641226/) is Pathogenic with criteria provided, one submitter, and one-star review status. That submitter states that p.Leu737Ter has not been reported in the literature in individuals with BUB1B-related conditions and classifies it from the expected premature-stop consequence plus the established BUB1B loss-of-function disease mechanism. These are database assertions, not participant-specific confirmation or case evidence.

A bounded ClinVar and PubMed search on 2026-08-26 found no ClinVar record for `c.3006T>G` and no indexed PubMed title/abstract record for `c.3006T>G`, `Asn1002Lys`, or `N1002K`. A different nucleotide substitution, `c.3006T>A`, encodes the same p.Asn1002Lys change and is classified as Uncertain significance with criteria provided by one submitter in [VCV004600147.1](https://www.ncbi.nlm.nih.gov/clinvar/variation/4600147/), last evaluated 2025-09-19 under the broad trait “Inborn genetic diseases.” It is not MVA-specific evidence and does not classify the challenge allele.

### 1.2 Disease-class bridge

The original human MVA series identified truncating and missense *BUB1B* mutations in affected families [Hanks et al., 2004](https://pubmed.ncbi.nlm.nih.gov/15475955/). Suijkerbuijk et al. subsequently described biallelic cases as a missense allele paired with a truncating allele and linked absent truncating-mutant transcripts plus increased missense-protein turnover to low BUBR1 abundance. Across immortalized patient-derived lymphoblastoid and fibroblast lines, they found an impaired mitotic checkpoint and chromosome-alignment defects. Separately, in BUBR1-depleted U2OS replacement assays, forced expression of I909T or L1012P to WT-comparable abundance fully restored the nocodazole-response readout [Suijkerbuijk et al., 2010](https://pmc.ncbi.nlm.nih.gov/articles/PMC2887387/). This was mutant-construct restoration of one engineered checkpoint readout, not rescue of a patient, organism, or p.Asn1002Lys.

Those findings establish an experimental allele class, not the mechanism of p.Asn1002Lys. Independent experimental mutation or removal of BUBR1's C-terminal pseudokinase domain decreased KARD phosphorylation and PP2A-B56 recruitment and impaired checkpoint silencing and chromosome alignment [Gama Braga et al., 2020](https://pubmed.ncbi.nlm.nih.gov/33207204/); those constructs were not p.Asn1002Lys and do not establish a clinical-variant mechanism. Mouse L1002P corresponds to human L1012P, not human N1002K, and mouse-human and allele-specific effects were substantial [Sieben et al., 2020](https://www.jci.org/articles/view/126863). The exact missense allele must therefore be allowed to falsify the stability hypothesis.

Public sequence and structure evidence supplies a bounded reason to test that hypothesis, not proof that it is true. N1002 lies in the annotated BUBR1 protein-kinase domain and is conserved in the checked mouse, rat, frog, and Drosophila homologs. At N1002, the wild-type [AlphaFold DB model for O60566](https://alphafold.ebi.ac.uk/entry/O60566) has pLDDT 91.06; this is per-residue local coordinate confidence, not a mutant-effect score. Reproducible local analysis gives RSA 0.1422 (48.07th percentile within the annotated kinase domain), consistent with partial but unremarkable domain-relative burial, and predicts three short side-chain-to-backbone polar contacts. The mapped homologous Asn has the same contact topology in experimental Drosophila structures [6JKK](https://www.rcsb.org/structure/6JKK) and [6JKM](https://www.rcsb.org/structure/6JKM); the aligned deposited construct is only 27.5% identical to the human region, so this is homolog-level—not human structural—evidence. The official 2023 AlphaMissense catalogue gives N1002K a score of 0.9229, but that is in-silico prioritization; no experimental human structure contains atoms at N1002, and a different nucleotide substitution encoding the same protein change remains a single-submitter ClinVar VUS. This evidence prioritizes an exact-allele stability assay; it does not establish pathogenicity, folding loss, or drug responsiveness.

### 1.3 Causal graph

The proposed chain is:

`trans phase` → `hypothesized stop-allele transcript depletion` + `hypothesized N1002K defect` → `insufficient functional BUBR1` → `checkpoint/attachment failure` → `new segregation errors per division`

Arimoclomol enters only between a demonstrated N1002K folding/stability defect and functional BUBR1 abundance. It cannot repair cis phase, restore the stop-bearing transcript if that transcript is depleted, or prove the upstream genetic model.

## 2. Why arimoclomol leads—and where the hypothesis is weakest

### 2.1 Regulatory and exposure facts

FDA approved MIPLYFFA in 2024. Its current indication is MIPLYFFA in combination with miglustat for neurological manifestations of NPC in adult and pediatric patients aged two years and older. The [current FDA-approved labeling, revised March 2026](https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid=5feffc0e-453d-47fa-91dd-38d4952309bc&type=display) says the mechanism underlying clinical effects in NPC is unknown. It reports estimated pediatric steady-state mean ± SD serum trough and peak concentrations of 206 ± 60 and 523 ± 194 ng/mL. The label gives citrate molecular weight 505.90 g/mol and a rounded strength equivalence of 124 mg arimoclomol to 200 mg arimoclomol citrate, implying a base-equivalent molecular weight of approximately `505.90 × 124 / 200 = 313.7 g/mol`. On that basis, 206 and 523 ng/mL correspond to approximately 0.66 and 1.67 micromolar. These are label-estimated mean serum concentrations in pediatric NPC under recommended dosing, not unbound, intracellular, sustained, or MVA-specific exposures.

The label records hypersensitivity, animal embryofetal and fertility findings, reversible creatinine increases associated with OCT2 inhibition, reduced dosing frequency for eGFR 15 to less than 50 mL/minute, and no PK evaluation below eGFR 15 mL/minute. It does not establish safety or efficacy in MVA or with arimoclomol monotherapy; even in NPC, the label states that data were insufficient to determine effectiveness without miglustat.

### 2.2 Mechanistic support

In primary Gaucher fibroblasts and a human neuronal model, arimoclomol increased HSP70-family proteins and improved mutant GCase maturation, lysosomal localization, and residual activity [Fog et al., 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC6306395/). In transfected human SK-N-SH cells, 1 micromolar arimoclomol for 24 hours significantly increased Hsp70 and reduced P23H rhodopsin inclusions and insoluble material [Parfitt et al., 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC4047904/). That nominal concentration is of the same order as, but below, the label-estimated pediatric mean serum Cmax; a constant 24-hour culture exposure is not equivalent to a transient systemic peak, and the label reports an approximately four-hour half-life in healthy adults. Neither model tested BUBR1.

A randomized NPC trial contains a limited, uncontrolled within-arm observation: in the arimoclomol arm, PBMC HSP70 increased from baseline at month 12 in the 11 paired samples available (`P = 0.001`) [Mengel et al., 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC9293014/). Central-laboratory sample loss left only four placebo paired samples, so the authors could not use placebo as a control for HSP70. This within-arm change is compatible with, but does not establish, an arimoclomol-induced human HSP70 response; it does not demonstrate BUBR1 engagement, explain the labeled clinical effect, establish an MVA-relevant exposure, or predict N1002K rescue.

The patient-derived Gaucher-cell work is also central counterevidence: HSPA1A induction used 100–400 micromolar, residual GCase-activity studies used 50–800 micromolar, and the authors noted a beginning cytostatic effect at 400–800 micromolar. Dividing those nominal culture concentrations by the estimated pediatric mean serum peak gives a roughly 30–480-fold concentration ratio. This is not an exposure-equivalence calculation because it omits unbound concentration, culture-medium binding, intracellular partitioning, exposure duration, tissue distribution, and metabolites. Fog et al. also disclosed Orphazyme funding and use of proprietary Orphazyme arimoclomol citrate; independent replication is required.

### 2.3 Unproven chaperone bridge

Suijkerbuijk et al. found that five-hour geldanamycin treatment severely depleted the tested I909T and L1012P BUBR1 constructs, while MG132 prevented the enhanced turnover, supporting HSP90-dependent folding and proteasomal routing in that engineered assay. Published arimoclomol studies describe it as a co-inducer or amplifier of a pre-existing heat-shock response and most consistently document HSP70-family induction; they do not establish an HSP90-directed molecular target. The FDA label leaves the clinical mechanism unknown. There is no direct evidence that arimoclomol at a nominal culture concentration of no more than 2 micromolar creates the chaperone state required by N1002K; this gate is a conservative screen, not a label-validated cellular exposure threshold.

The screen therefore requires, in order:

1. participant- or exact-isogenic N1002K instability;
2. a prespecified chaperone-response signal at no more than 2 micromolar—for example, HSF1-state and HSPA1A/B responses—without calling this a validated direct molecular target;
3. increased soluble, correctly localized full-length BUBR1;
4. improved checkpoint and chromosome-segregation function; and
5. no apparent benefit explained by cytostasis, toxicity, or abnormal-clone selection.

### 2.4 Negative clinical evidence

Arimoclomol failed to improve efficacy outcomes in two completed randomized trials. In phase 3 ORARIALS-01, the modified-intention-to-treat CAFS score did not differ between arimoclomol and placebo (0.51 versus 0.49; `P = 0.62`), and adverse events led to discontinuation in 16% versus 5%; the authors concluded that higher dosing likely would not have been tolerated [Benatar et al., 2024](https://pubmed.ncbi.nlm.nih.gov/38782015/). In the completed randomized inclusion-body myositis trial, the month-20 IBMFRS mean difference was -0.99 (95% CI -2.23 to 0.24; `P = 0.12`), with adverse-event discontinuations in 18% versus 5% [Machado et al., 2023](https://pubmed.ncbi.nlm.nih.gov/37739573/). The ALS authors also stated that biomarker data were insufficient to exclude all future HSP-response strategies. Neither trial tested BUB1B or MVA, but both oppose any claim that generalized heat-shock-response amplification is predictably clinically effective. The ALS paper disclosed Orphazyme funding; the IBM paper disclosed FDA Office of Orphan Products Development and Orphazyme funding.

### 2.5 Why the alternatives are comparators, not co-leads

The selection matrix was frozen around evidence that could falsify this exact mechanism; approval status alone does not rank a drug.

| Candidate | BUB1B-direct evidence | Human pharmacodynamic observation | Human-exposure information | Key limitation/counterevidence | Role |
|---|---|---|---|---|---|
| Arimoclomol | none | uncontrolled within-arm PBMC HSP70 increase in 11 paired NPC samples; only four placebo pairs, so no controlled HSP70 comparison | label-estimated pediatric mean serum Cmax (not unbound or intracellular); unrelated 1-micromolar/24-hour culture result is not PK-equivalent | high concentrations in many Gaucher-cell assays; randomized ALS and IBM trials did not improve their prespecified efficacy outcomes; NPC mechanism unknown | single conditional ex-vivo lead |
| Teprenone / GGA | none | oral HSP70-family induction in human gastric or atrial tissue | no BUBR1-relevant systemic or pediatric information | HSP70-independent UPR/CHOP at ≥100 micromolar and apoptosis in mesangial cells | orthogonal comparator only |
| Sodium phenylbutyrate | none | no exact-mechanism human bridge used here | adult single-dose label PK only | sodium burden; pediatric PK gap; mechanistically nonspecific | pharmacologically distinct comparator only |

Arimoclomol leads because it has the least-bad combination of a bounded low-micromolar cellular observation, a small uncontrolled within-arm human HSP70 observation, and current label exposure information—not because it is proven, unique, or BUBR1-directed. The exact-allele Gate 4 stop prevents those indirect observations from carrying a failed stability premise.

- **Teprenone / geranylgeranylacetone:** PMDA lists teprenone as the active ingredient of Selbex, a marketed Japanese anti-ulcer medication [PMDA product record](https://www.pmda.go.jp/PmdaSearch/rdDetail/iyaku/2329012C1026_1?user=1). Oral GGA increased HSP70-family proteins in human gastric or atrial tissue [Yanaka et al., 2007](https://pubmed.ncbi.nlm.nih.gov/17684364/); [van Marion et al., 2020](https://pubmed.ncbi.nlm.nih.gov/31302249/). The cited studies do not establish systemic or pediatric exposure relevant to BUBR1. At concentrations of at least 100 micromolar, GGA induced an HSP70-independent ER-stress/UPR program including CHOP; in mesangial cells it also induced apoptosis [Endo et al., 2007](https://pubmed.ncbi.nlm.nih.gov/17702888/).
- **Sodium phenylbutyrate:** BUPHENYL is indicated as adjunctive chronic therapy for specified urea-cycle disorders. Its [current label](https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid=463a36fa-3eb2-4326-8bd0-c8c7a11bca3a&type=display) reports an adult fasting phenylbutyrate peak of 218 micrograms/mL after a single 5-g tablet dose—approximately 1.17 millimolar using the label's molecular weight of 186—and a 0.77-hour half-life. The label states that PK studies were not conducted in the primary neonatal, infant, and child population and records approximately 124–125 mg sodium per gram of sodium phenylbutyrate. It is retained only as a pharmacologically distinct laboratory comparator, not as a pediatric exposure bridge or dosing proposal.
- **Proteasome inhibitors:** MG132 is retained solely as the in-vitro degradation-pathway control used by Suijkerbuijk et al. No proteasome inhibitor is proposed as a repositioning candidate.

Exact N1002K correction is the causal anchor. Expression-matched full-length WT BUB1B is a complementary pathway-rescue control; it cannot substitute for exact correction or be interpreted as a drug-equivalent result.

## 3. Sequential experiment: every gate can stop the program

### Gate 0 — orthogonal confirmation, identity, and governance

Confirm both variants from a second DNA aliquot using an orthogonal clinical-grade assay. Verify trio identity and Mendelian consistency before interpreting segregation. Use residual clinical material or an already obtained fibroblast culture; do not request an invasive pediatric biopsy solely for this research. Keep coded samples and a prespecified incidental-findings and return-of-results pathway through qualified clinicians.

**Stop:** either call fails orthogonal confirmation, specimen identity is unresolved, or governance does not permit the planned use.

### Gate 1 — direct phase

Perform PCR-free Cas9-targeted long-read sequencing across the approximately 10.9-kb interval with two independent guide configurations. Require at least 30 high-quality full-span molecules per recovered haplotype, strand/guide balance, and concordant allele linkage. PCR-free Cas9 enrichment avoids PCR-generated chimeras and amplification bias, but it does not eliminate guide-site, fragment-length, allelic-recovery, or strand bias [Gilpatrick et al., 2020](https://pubmed.ncbi.nlm.nih.gov/32042167/); independent guide configurations are therefore required. If parental DNA is available through approved channels, genotype both parents independently and require trio consistency as orthogonal evidence. Parental availability strengthens but does not replace direct molecular phasing, and its absence must not be represented as phase resolution.

- **Trans:** proceed with the pair hypothesis.
- **Cis:** reject the submitted pair; N1002K may still be studied as variant biology.
- **Unresolved:** functional work may continue, but no participant-specific compound-heterozygous claim advances.

### Gate 2 — allele-specific RNA and stop-allele fate

Measure total BUB1B RNA by RT-ddPCR and allelic ratios at c.2210 and c.3006 by UMI amplicon sequencing plus orthogonal dual-probe ddPCR. Normalize cDNA allele ratios to gDNA controls. Test two nonoverlapping UPF1 perturbations and an independently optimized SMG1-pathway perturbation, each with viability and endogenous NMD controls. Targeted long-read cDNA sequencing checks splice and full-length isoforms; N- and C-terminal BUBR1 antibodies test for a possible truncated product.

Support the specific NMD model only if the untreated stop-bearing transcript is substantially depleted, two valid independent perturbations raise it in the same direction, and assay controls pass. If the transcript persists, revise the null model rather than forcing an NMD label.

### Gate 3 — endogenous isogenic allelic series

Build a near-diploid, p53-intact nontransformed allelic series, with confirmation in patient-derived cells or a second nontransformed background. Escalate rather than constructing every line at once: the minimal causal series is WT/WT, the exact trans test genotype, and its exact-corrected derivative; add carrier-dose, instability-comparator, same-site, and assay-floor controls only when the preceding gate justifies them.

| Genotype | Purpose |
|---|---|
| WT/WT | normal baseline |
| L737*/WT | truncation-carrier control |
| WT/N1002K | missense-carrier dose control |
| L737*/N1002K, confirmed trans | exact test genotype |
| L737*/N1002= | same-site editing control after normal splicing is verified |
| L737*/L1012P | known MVA-associated instability comparator, not an N1002K surrogate |
| exact corrected compound clone | primary causal rescue |
| acute BUB1B depletion | assay-floor control |

Use six clones per genotype nested within three independent editing events, with two independently derived clones per event, for the feasibility stage. These are three—not six—independent highest-level units. Confirm local sequence and phase, fingerprint identity, mycoplasma status, modal karyotype, copy-number integrity, and relevant off-targets. Reject unexplained aneuploid or structurally altered clones. Before confirmatory inference, use blinded event-level variance to determine whether additional independent edit events or biological backgrounds are required; three events are a feasibility floor, not an asserted universal power calculation.

### Gate 4 — exact N1002K abundance and stability

Use a C-terminal antibody to measure the full-length missense product without counting a possible L737* fragment. Quantify steady-state protein with total-protein normalization and targeted proteomics; measure half-life by cycloheximide chase and pulse-SILAC; match cell-cycle state; and quantify kinetochore-localized BUBR1 after spindle disruption.

Before unblinding N1002K outcomes, freeze biologically meaningful effect and equivalence margins from external assay performance and control biology. A blinded control-only pilot may estimate variance and sample size, but cannot choose margins after showing favorable separation. A stability-hypomorph call requires materially lower full-length abundance and half-life, concordant orthogonal turnover evidence, and rescue by exact correction. If N1002K falls within the prespecified WT-equivalence range for abundance and half-life, the stability hypothesis is rejected and the **arimoclomol branch stops**. Candidate-agnostic functional characterization may continue, but WT-equivalent abundance and half-life stop this stability-rescue rationale.

### Gate 5 — exposure-gated arimoclomol screen, only after a Gate 4 stability defect

Use vehicle and arimoclomol at 0.2, 0.5, 1, and 2 micromolar. Only a response at no more than 2 micromolar can satisfy the concentration gate. Five micromolar is mechanistic exploration and cannot advance the candidate by itself; concentrations from 50 micromolar upward may be retained only to diagnose a nontranslational mechanism.

Concentration matching alone is not human exposure matching. Quantify total and unbound medium concentration and intracellular arimoclomol by a qualified LC-MS method, report concentration-time profiles, and include a pulse/washout arm informed by—but not claimed to reproduce—the label's approximately 0.5-hour adult `tmax` and four-hour adult half-life. The pediatric label supplies serum point estimates, not intracellular exposure or a validated MVA pharmacokinetic model. Run drug × proteotoxic-stress factorial arms so a stress-contingent response is distinguished from constitutive drug activity.

Measure:

- HSF1 state, HSPA1A/B and related HSP70-family induction, and HSP90/co-chaperone abundance as prespecified pharmacodynamic-response measurements—not assumed direct-target engagement;
- soluble and insoluble full-length BUBR1;
- BUBR1 half-life, complex assembly, and kinetochore localization;
- PP2A-B56 recruitment;
- viability, apoptosis, cell-cycle distribution, UPR/CHOP, and general proteotoxicity;
- matched WT and corrected-clone effects.

Mechanistic-dependency controls test whether any observed response requires HSF1 or HSPA1A/B; they do not identify a direct arimoclomol target. An abundance clamp that equalizes BUBR1 protein across arms tests whether a functional change exceeds the amount of restored protein. Full-length WT BUB1B provides a pathway-rescue ceiling. Teprenone and sodium phenylbutyrate serve only as orthogonal comparator controls.

**Stop:** no prespecified chaperone-response signal at no more than 2 micromolar under the measured exposure conditions; signal confined above 2 micromolar; no prespecified drug × genotype benefit in BUBR1/checkpoint endpoints after accounting for the contemporaneous WT and exact-corrected drug responses; adverse WT perturbation; UPR, toxicity, or cell-cycle arrest accounts for the result; or N1002K protein rises without correct localization.

### Gate 6 — checkpoint and chromosome segregation

Co-primary functional measurements are:

1. live-cell time in mitosis after nocodazole plus an orthogonal 4N MPM2/pH3-positive checkpoint fraction; and
2. predefined segregation errors in the first attempted unperturbed division of mothers enrolled before treatment, including lagging chromosomes, nondisjunction, bridges, multipolar division, and centromere-validated micronuclei.

Advancement requires **both** co-primary families to pass their frozen margins in the favorable direction under an intersection-union rule; one successful endpoint cannot compensate for failure of the other. Enroll and randomize the mother-cell cohort before exposure, then classify each mother's first attempted division into mutually exclusive outcomes: pre-division death/non-completion, completed without a scored error, or completed with at least one scored error. Report both the conditional error probability per completed first division and the cumulative error-bearing-division probability per enrolled founder. A clean-fidelity claim requires concordant reduction in both, plus containment of the division-completion contrast within its prespecified equivalence band; otherwise report a mixed or non-estimable result. A division is counted once even if it has multiple error features; a blinded adjudication hierarchy assigns category labels for secondary analyses and prevents double-counting. Later-generation and state-stratified rates are secondary. Additional doses and secondary endpoints remain multiplicity-controlled and cannot rescue a failed co-primary result.

Secondary measurements include cyclin B1/securin degradation, chromosome alignment after monastrol washout, premature chromatid separation, and shallow single-cell DNA sequencing after fixed population doublings.

The independent edit event is the highest-level biological unit; clones are nested within edit event, and repeated thaws are technical run blocks rather than new biological replicates. The feasibility design uses three edit events, two independently derived clones per event, three run blocks per clone, and 250 tracked mother-cell observation opportunities per run. Confirmatory event count is set from blinded event-level variance before outcome unblinding. Randomize plate position, blind sample IDs, and lock analysis before outcome unblinding. Exact correction must restore at least half of the mutant-control gap and satisfy a prespecified equivalence margin to the relevant control. A failed positive control invalidates the run. A blinded pilot may update variance and sample size, but not outcomes, mechanisms, or success margins.

Use one prespecified primary exposure plus a monotone dose-response trend for confirmatory inference; control additional dose contrasts with Dunnett or Holm adjustment. Add an acute or polyclonal perturbation arm to detect clone-selection artifacts that can arise during prolonged derivation. A finding that exists only in one clone, one edit event, or chronically selected clones does not advance.

## 4. The differentiator: generation versus selection

### 4.1 Why bulk aneuploidy is ambiguous

A lower final fraction of abnormal cells can arise from at least four different processes:

- fewer new segregation errors;
- selective death or arrest of abnormal daughters;
- fewer completed divisions in all cells;
- altered persistence of pre-existing abnormal clones.

Aneuploid daughters can undergo p53-dependent arrest after chromosome missegregation in nontransformed diploid-cell experiments [Hinchcliffe et al., 2016](https://pubmed.ncbi.nlm.nih.gov/27136267/). Valind et al. combined measured missegregation and aneuploidy prevalence with modeling of aneuploid-cell fitness, showing why prevalence reflects both error generation and selection [Valind et al., 2013](https://pubmed.ncbi.nlm.nih.gov/23894657/). Cross-sectional karyotype prevalence is therefore a composite outcome, not the primary rescue endpoint.

### 4.2 Planned full-lineage estimands—not the aggregate benchmark

Perform 72–96-hour lineage-resolved imaging in gridded microwells with chromosome labeling, a death marker, automated segmentation, fixed blinded manual adjudication, and recovery of selected lineages for endpoint single-cell DNA sequencing. Enroll and randomize a founder cohort before exposure. Score the first attempted division of every founder—including death or non-completion—before daughter fate is known, then follow both daughters for death, arrest, and another division. Later divisions and endpoint karyotype strata are secondary rather than substitutes for the fixed-cohort primary window.

| Symbol | Estimand | Interpretation |
|---|---|---|
| `gC` | conditional probability of any prespecified new segregation error in the first completed division of a pre-treatment-enrolled mother | per-completed-division generation component |
| `gE` | probability of an error-bearing completed first division per pre-treatment-enrolled mother | fixed-cohort cumulative component; interpreted with death/non-completion |
| `s` | probability a daughter from an adjudicated error-positive division produces another generation within 48 hours, with death and no division retained as competing outcomes | post-event selection/retention |
| `λ` | completed divisions per viable cell-hour plus intermitotic-time distribution | cytostasis/proliferation |
| `pA(t)` | abnormal-cell fraction at a fixed time | composite secondary outcome |

The primary generation decision requires concordant favorable `RRgC` and `RRgE` contrasts plus division-completion equivalence. Daughter outcome and division-intensity contrasts are estimated separately. A genetic or drug perturbation can remain biologically interesting if effects are mixed, but it cannot be called improved chromosome-segregation fidelity when only the conditional denominator improves or completion differs materially.

Use logistic or beta-binomial mixed models for `gC` and `gE`, a multistate competing-risk model for daughter death/next division, and a recurrent-event or negative-binomial model with viable cell-hours for `λ`. Clone, editing event, batch, and imaging field are hierarchical effects. Cells are nested observations, never independent biological replicates. These timestamped estimands specify the future assay analysis; the implemented aggregate-count stress test below is intentionally narrower.

### 4.3 Implemented synthetic stress test

This repository implements a deterministic, standard-library **paired hierarchical fixed-cohort first-attempt aggregate-count stress test** in `mva_hackathon.generation_selection`; it is not a timestamped lineage or competing-risk implementation. Each pre-enrolled founder contributes one first attempted division classified as no-completion/death, completed-no-error, or completed-error. Each simulated arm follows a hierarchy of three edit events, two clones per event, and three run blocks per clone. The analyzer is restricted to observed aggregate counts and independently observed calibration counts; generator parameters and realized truth are evaluator-only objects. The edit event—not the clone, run, or cell—is the highest inferential unit. A version-stable pseudorandom generator, strict schema, and fail-closed runner make the final receipt reproducible under its recorded environment.

The predeclared v3 configuration runs 1,000 independent vehicle-treatment comparisons in each of 14 scenarios, for 14,000 comparisons total. The scenarios cover:

1. a no-change null and a strong generation reduction;
2. three local generation ratios—0.75, 0.6875, and 0.625—for an effect-specific power curve;
3. pure error-daughter pruning and preservation;
4. generic cytostasis and generic toxicity;
5. a sparse mixed generation, selection, and cytostasis case scored only for fail-closed behavior;
6. arm-specific event-sensitivity and event-specificity drift;
7. division-detection drift; and
8. informative marginal daughter follow-up.

All 14 configured gates passed in the deterministic release probe. The strong generation effect was detected in 906/1,000 comparisons, with a 95% Wilson lower bound of 88.63%; its exact expected flag set occurred in 905/1,000 and 37/1,000 returned insufficient information. Across required scenarios without a true generation reduction, the maximum false-generation 95% Wilson upper bound was 0.564%. Pure pruning and preservation produced the exact expected flag set in 962/1,000 and 834/1,000 comparisons, respectively. The sparse mixed case returned insufficient information in 852/1,000 comparisons—95% Wilson lower bound 82.86%—and is evidence of fail-closed behavior, not of selection sensitivity. Event-sensitivity, event-specificity, division-detection, and informative-follow-up drift were correctly flagged in 1,000/1,000, 992/1,000, 1,000/1,000, and 999/1,000 comparisons. Local-generation detection was 23.1%, 41.4%, and 61.1% at true treatment-to-vehicle ratios 0.75, 0.6875, and 0.625; those are effect-specific simulation results, not a real-study power guarantee.

The analysis uses one observed-data information/QC rule in every scenario. An endpoint with inadequate event counts, unstable calibration, or a detected follow-up artifact returns `insufficient_information`, suppresses the corresponding biological flag, and contributes to the reported non-estimable fraction; no scenario-truth list can waive a failing endpoint. A clean generation signal requires statistically supported, concordant reductions in both conditional error per completed first division and error-bearing completed divisions per enrolled founder, plus a division-completion ratio confidence interval wholly contained in the predeclared 0.80–1.25 equivalence band. Intervals and performance summaries operate at the edit-event level and include Monte Carlo uncertainty.

One reusable external truth-labeled calibration panel is shared across arm comparisons; it is not regenerated per arm or used as treatment-specific truth. Its reference labels are assumed to be established independently of treatment assignment and blinded to the benchmark analyst. Separate blinded arm-specific positive, negative, and division audits test measurement drift and trigger fail-closed invalidation; they do not recalibrate the treatment comparison.

Daughter reproduced/died/other label misclassification is not generated, corrected, or audited in v3, so those labels are assumed adjudicated. Outcome-dependent missingness deliberately constructed to preserve identical arm-level marginal follow-up is not identifiable from these aggregate sufficient statistics. Aggregate counts also cannot separate pre-division death from other causes of non-completion, and later daughter outcomes are secondary. These boundaries require external outcome adjudication and timestamped lineage data; the benchmark does not establish general measurement-artifact robustness.

The most important stress comparison is qualitative and explicitly limited to the configured toy bulk dynamics: a bulk-only endpoint can call improvement when the modeled new-error probability is unchanged because abnormal daughters are pruned or division completion falls. The component analysis keeps observed event-call probability, followed event-positive daughter reproduction, division completion, general daughter outcome, measurement quality, and bulk composition separate rather than collapsing them into one “rescue” label.

Reproduce the receipt with:

```powershell
python scripts/run_generation_selection_benchmark.py `
  --config configs/track2-generation-selection-benchmark.json `
  --output local_dev/track2-generation-selection.json
```

The versioned receipt is [TRACK2_GENERATION_SELECTION_BENCHMARK.json](TRACK2_GENERATION_SELECTION_BENCHMARK.json). Before real data are unblinded, the protocol implementation must add timestamped lineage IDs, competing outcomes, field/batch effects, empirically justified calibration, dropout and censoring models, and the prespecified mixed-effects analyses above. The aggregate-count benchmark tests recoverability only for its configured effect sizes and artifact scenarios—not real-data power, imaging accuracy, biological correctness, candidate activity, treatment efficacy, or benefit to a person.

## 5. Oncology and pediatric safety boundary

MVA is a cancer-predisposition disorder. Any intervention that amplifies proteostasis could help abnormal or malignant clones survive. HSF1 can support malignant-cell proliferation and survival [Dai et al., 2007](https://pubmed.ncbi.nlm.nih.gov/17889646/). A short ex-vivo normalization of one chromosome endpoint cannot settle long-term tumor risk.

Relevant counterevidence must also be retained: the current MIPLYFFA label reports no increased tumor incidence in two-year rat and 26-week rasH2-mouse carcinogenicity studies at systemic exposures approximately eight- and eleven-fold the human exposure by AUC. Those negative animal studies reduce, but do not eliminate, concern in a cancer-predisposed germline context that was not studied.

The ex-vivo counterscreen therefore asks whether arimoclomol:

- increases survival, reproductive output, or clonogenicity of existing aneuploid cells;
- protects transformed cells or alters response to likely oncology agents;
- reduces antitumor stress responses;
- creates an apparent benefit by killing cells or preventing division.

Label-derived hypersensitivity, embryofetal, fertility, renal/OCT2, and drug-interaction risks are external clinical constraints. This ex-vivo screen cannot clear them.

Any increased malignant/aneuploid clone fitness is a program-level stop even if BUBR1 abundance rises. No oncology therapy should be changed on the basis of this proposal.

## 6. Falsification and decision table

| Result | Predeclared interpretation | Action |
|---|---|---|
| Either variant fails orthogonal confirmation | input hypothesis invalid | stop |
| Variants confirmed cis | submitted recessive pair rejected | stop participant-pair program |
| Phase unresolved | compound-heterozygous status unknown | continue variant biology only |
| Stop transcript persists and is NMD-insensitive | specific NMD-null model rejected | assay truncated product and revise |
| N1002K abundance and half-life are WT-equivalent | stability/chaperone premise unsupported | stop arimoclomol; functional biology may continue with a different candidate |
| N1002K abundance, localization, checkpoint behavior, and segregation outcomes are all WT-equivalent | exact-allele causal chain unsupported in the tested system | stop participant-specific functional program |
| Exact correction fails to rescue | causal attribution unresolved | investigate clone/background; do not advance |
| Arimoclomol lacks the prespecified chaperone-response signal at ≤2 micromolar under acceptable measured exposure | concentration/mechanistic bridge fails | stop repositioning |
| Effect appears only at ≥50–100 micromolar | nontranslational mechanism only | no-go for repositioning |
| Protein increases without checkpoint/segregation correction | marker change, not functional rescue | stop |
| Bulk abnormal fraction falls but `gC`/`gE` do not concordantly fall under completion equivalence | selection, cytostasis, or mixed process | do not call rescue |
| `gC` and `gE` fall but abnormal-clone retention rises | mixed result with oncology concern | stop pending independent safety work |
| `gC` and `gE` concordantly fall under completion equivalence at a prespecified nominal concentration ≤2 micromolar with medium and intracellular exposure characterized, exact correction triangulates the mechanism, and ex-vivo clone-fitness/toxicity counterscreens show no prespecified hazard signal | bounded preclinical screening signal | independent replication; still not treatment, efficacy, or safety evidence |

No branch demonstrates clinical benefit. A negative result is valuable: it prevents an unsupported medicine from advancing and clarifies whether N1002K is a stability, non-abundance functional, or WT-like allele in the tested systems.

## 7. Innovation, impact, and scalability

### Scientific rigor

The proposal separates phase, transcript fate, exact-allele abundance, direct function, drug concentration and time profile, outcome generation, clone selection, and toxicity. Exact correction is the causal anchor; expression-matched WT BUB1B is a pathway-rescue control. Label-estimated serum concentrations inform a conservative screening boundary; they do not establish human-equivalent cell exposure.

### Potential impact

The first useful output is not a prescription. It is a staged, decisive answer to three questions. The immediate GO is only for Gate 0 confirmation and Gate 1 phase; every costly downstream layer is conditional on the preceding result:

1. Is the pair truly in trans?
2. Is N1002K a rescuable functional-protein deficit?
3. Does an approved-drug probe reduce new errors, or merely change which cells remain?

A positive result nominates a bounded preclinical direction. A negative result reduces the risk of advancing a false rescue story and leaves a reusable mechanistic profile; it does not itself protect or clinically benefit the child.

The participant-facing output is deliberately modest: no research result is sent directly to the family and no drug instruction is produced. Through organizer-approved clinical channels, a qualified team could translate validated results into a one-page status record stating what was confirmed, what remains unknown, which gate stopped, and why no treatment conclusion follows. That makes a negative result legible instead of disappearing and minimizes additional sampling by prioritizing residual material and exact stop rules.

### Innovation

Arimoclomol itself is not claimed as novel. The innovation is the exact-allele and exposure funnel coupled to an implemented false-rescue firewall that separates new-error generation from daughter outcome, cytostasis, and measurement failure. The aggregate-count benchmark distinguishes only the biological effects and measurement artifacts explicitly configured in its final receipt; it is not evidence that the classifier will succeed on real biological data.

### Scalability

The reusable unit is a five-gate assay contract:

`phase/RNA` → `protein stability` → `exact function` → `generation-selection deconvolution` → `independent replication`

The software component uses the Python standard library, is config-driven, and runs its predeclared synthetic comparisons on a CPU without participant data. Its public observed-run schema, calibration layer, independent mechanism flags, and receipt-bound acceptance gates can be reused in other studies that must separate event generation from post-event outcome. Adaptation still requires a gene-specific functional assay, empirically calibrated observation model, measured exposure, and disease-specific safety boundary; one cell-line workflow cannot classify every VUS.

Execution is modular and outsourceable rather than “fast”: a clinical genetics laboratory owns confirmation and phase; an RNA/editing core owns the gated allelic series; a proteomics/LC-MS core owns abundance and exposure; an imaging core exports the prespecified aggregate-count schema; and an independent site repeats only a fully qualified positive. Each handoff has a bounded artifact—phase record, allele-function scorecard, measured-exposure table, blinded count table, and replication decision—so a failed gate stops downstream spend. The public software and reporting contract can be reused without sharing this participant's controlled data.

Wet-lab duration and cost are not claimed from a desktop estimate. They should be quoted by the executing clinical/research laboratories after sample availability, editing strategy, sequencing depth, and replication sites are fixed.

## 8. Limitations

1. The variants have not been orthogonally confirmed or phased in the evidence available to this entry.
2. p.Leu737Ter NMD and p.Asn1002Lys abundance/function are inferred hypotheses, not participant measurements.
3. There is no direct BUB1B, N1002K, MVA, checkpoint, or chromosome-segregation evidence for arimoclomol.
4. In an engineered U2OS assay, pharmacologic HSP90 inhibition depleted the tested I909T and L1012P constructs; arimoclomol studies most consistently document HSP70-family induction. Applicability to N1002K is unknown.
5. Label-estimated pediatric mean serum concentrations are below the nominal culture concentrations used in many positive mutant-protein experiments; this comparison is not PK equivalence.
6. MIPLYFFA's FDA indication is for use in combination with miglustat in NPC, not for MVA or monotherapy; the label says the clinical mechanism is unknown.
7. Cell correction is not organismal or clinical benefit. Developmental timing, tissue specificity, pharmacology, and cancer risk remain unresolved.
8. The synthetic simulator validates declared software behavior only. It does not validate real imaging, real effect sizes, or the proposed medicine.
9. Patient-derived cultures represent one child; repeated wells do not create population-level evidence.
10. Bounded searches can miss unindexed, unpublished, non-English, or newly released evidence. Regulatory status and challenge rules require refresh before the irreversible submission.

## 9. Methods-form abstract (under 500 words)

We propose arimoclomol as a single exposure-gated ex-vivo screening hypothesis for a candidate BUB1B-associated MVA genotype containing p.Leu737Ter and p.Asn1002Lys. The proposal is not a treatment recommendation. Phase is unresolved, the stop-allele transcript has not been measured, and the missense allele has no direct functional evidence. The program therefore begins with orthogonal confirmation and direct phase. Cis phase rejects the pair.

If trans is established, allele-specific RNA and independent NMD perturbations test the stop-allele model. An endogenous isogenic allelic series then tests whether p.Asn1002Lys lowers full-length BUBR1 abundance or half-life, disrupts localization or PP2A-B56 recruitment, weakens the spindle checkpoint, or increases chromosome-segregation errors. Exact correction is the causal anchor; expression-matched WT BUB1B is a pathway-rescue positive control.

Arimoclomol was generated as a candidate through a mechanism-first primary-literature and regulatory search. MIPLYFFA's FDA indication is for use in combination with miglustat for neurological NPC in patients aged at least two years and its label provides estimated pediatric serum concentrations. Patient-derived Gaucher cells and transfected human rhodopsin-model cells show HSP70-family and mutant-protein biochemical effects, but there is no BUB1B-direct evidence and the label says the clinical mechanism in NPC is unknown. Fog et al. used 100–400 micromolar for HSPA1A induction and 50–800 micromolar in residual GCase-activity studies, versus a label-estimated pediatric mean serum peak of approximately 1.67 micromolar. That nominal ratio is not PK equivalence. Randomized ALS and inclusion-body-myositis trials did not improve efficacy outcomes; neither disease is BUB1B-associated MVA, but the null results are counterevidence against assuming a broadly effective heat-shock-response therapy. We therefore screen 0.2–2 micromolar, treat 5 micromolar as non-advancing exploration, and reject repositioning if no result occurs at no more than 2 micromolar under acceptable measured exposure.

The main methodological innovation separates true reduction of new segregation errors from selective loss/preservation of abnormal clones, cytostasis, toxicity, and measurement bias. In a pre-treatment-enrolled founder cohort, the proposed real experiment uses lineage imaging to estimate first-division errors both per completed division and per enrolled founder, with completion/death as competing outcomes; daughter retention and later division intensity remain separate. The implemented paired hierarchical aggregate-count benchmark tests whether its simplified analysis distinguishes configured biological effects from measurement artifacts while respecting edit-event nesting and observed-data non-estimability. Bulk-only results are scoped to the configured toy dynamics. This is a software and study-design stress test, not biological validation or a full lineage-analysis implementation.

The candidate advances only if exact N1002K dysfunction exists, arimoclomol produces the prespecified chaperone-response signal at no more than 2 micromolar under acceptable measured exposure, soluble and correctly localized full-length BUBR1 increases, checkpoint function improves, both fixed-cohort generation metrics concordantly improve under completion equivalence, exact correction triangulates causality, and ex-vivo oncology/clone-fitness counterscreens show no prespecified hazard signal. This would remain a preclinical screening result, not evidence of clinical safety or benefit. Any treatment, dose, combination, or cure claim remains out of scope.

### Methods disclosure

- **Candidate generation:** structured mechanism-first search of current official labels, ClinVar, PubMed/PMC primary studies, and target-specific human evidence; alternatives retained as comparators.
- **Automation:** local scripts performed deterministic evidence organization, strict output validation, and the paired hierarchical aggregate-count benchmark.
- **Manual work:** allele interpretation, source verification, causal graph design, exposure comparison, experiment design, and claim-by-claim counterevidence review.
- **LLM assistance:** used for research orchestration, drafting, code generation, and adversarial review. Every material external factual claim was checked against cited primary or official evidence; no LLM output was treated as biological evidence.
- **Proprietary sources:** none used as scientific support.
- **Participant outputs:** used only as segregated landscape context, never as biological or ranking evidence.
- **Estimated effort:** multi-agent literature, experimental-design, and judging audits plus local implementation and testing on 2026-08-26; elapsed effort is not a proxy for scientific validity.

## 10. Ethics, privacy, and acknowledgment

No raw gated genome, raw reads, verbatim clinical narrative, or avoidable identifying detail is published in this repository. The participant must not be recontacted outside organizer-approved channels. Research interpretations are not returned as clinical results without validated confirmation and a qualified care team. Gated source and individual-level derived data remain controlled and are subject to the challenge deletion agreement.

Dataset: Sage Bionetworks, [MVA Hackathon 2026 gated data](https://huggingface.co/datasets/SageBio/mva-hackathon-2026-data), pinned analysis revision `f534cb0c1a607110c6dad0194299bd3dd62df542`.

> This work was made possible through the Hackathon, organized by Sage Bionetworks in partnership with the MVA Society, Hugging Face, and BEACON (The Benchmarking, Evaluation, and Assessment Consortium for Science), with prize sponsorship from AWS and Anthropic. We are deeply grateful to the child and their family who generously contributed their data and their story to advance research into this rare disease. We acknowledge their trust in making this Hackathon possible.

## References

1. Hanks S, et al. [Constitutional aneuploidy and cancer predisposition caused by biallelic mutations in BUB1B](https://pubmed.ncbi.nlm.nih.gov/15475955/). *Nature Genetics*. 2004.
2. Suijkerbuijk SJE, et al. [Molecular causes for BUBR1 dysfunction in the human cancer predisposition syndrome mosaic variegated aneuploidy](https://pmc.ncbi.nlm.nih.gov/articles/PMC2887387/). *Cancer Research*. 2010.
3. Gama Braga L, et al. [BUBR1 pseudokinase domain promotes kinetochore PP2A-B56 recruitment, spindle checkpoint silencing, and chromosome alignment](https://pubmed.ncbi.nlm.nih.gov/33207204/). *Cell Reports*. 2020.
4. Sieben CJ, et al. [BubR1 allelic effects drive phenotypic heterogeneity in mosaic-variegated aneuploidy progeria syndrome](https://www.jci.org/articles/view/126863). *Journal of Clinical Investigation*. 2020.
5. FDA/DailyMed. [MIPLYFFA (arimoclomol) prescribing information](https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid=5feffc0e-453d-47fa-91dd-38d4952309bc&type=display). Revised March 2026; initial U.S. approval 2024.
6. Fog CK, et al. [The heat shock protein amplifier arimoclomol improves refolding, maturation and lysosomal activity of glucocerebrosidase](https://pmc.ncbi.nlm.nih.gov/articles/PMC6306395/). *EBioMedicine*. 2018.
7. Parfitt DA, et al. [The heat-shock response co-inducer arimoclomol protects against retinal degeneration in rhodopsin retinitis pigmentosa](https://pmc.ncbi.nlm.nih.gov/articles/PMC4047904/). *Cell Death & Disease*. 2014.
8. Gilpatrick T, et al. [Targeted nanopore sequencing with Cas9-guided adapter ligation](https://pubmed.ncbi.nlm.nih.gov/32042167/). *Nature Biotechnology*. 2020.
9. Hinchcliffe EH, et al. [Chromosome missegregation during anaphase triggers p53 cell cycle arrest through histone H3.3 Ser31 phosphorylation](https://pubmed.ncbi.nlm.nih.gov/27136267/). *Nature Cell Biology*. 2016.
10. Valind A, et al. [Elevated tolerance to aneuploidy in cancer cells: estimating the fitness effects of chromosome number alterations by in silico modelling of somatic genome evolution](https://pubmed.ncbi.nlm.nih.gov/23894657/). *PLoS ONE*. 2013.
11. Bollen Y, et al. [Reconstructing single-cell karyotype alterations in colorectal cancer identifies punctuated and gradual diversification patterns](https://pubmed.ncbi.nlm.nih.gov/34211178/). *Nature Genetics*. 2021.
12. Dai C, et al. [Heat shock factor 1 is a powerful multifaceted modifier of carcinogenesis](https://pubmed.ncbi.nlm.nih.gov/17889646/). *Cell*. 2007.
13. ClinVar. [VCV000533901.9](https://www.ncbi.nlm.nih.gov/clinvar/variation/533901/), [RCV000641226.9](https://www.ncbi.nlm.nih.gov/clinvar/RCV000641226/), and [VCV004600147.1](https://www.ncbi.nlm.nih.gov/clinvar/variation/4600147/). Accessed 2026-08-26.
14. Sage Bionetworks. [Rare Disease, Real Kid: The MVA Hackathon 2026](https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026). Accessed 2026-08-26.
15. Benatar M, et al. [Safety and efficacy of arimoclomol in patients with early amyotrophic lateral sclerosis (ORARIALS-01): a randomised, double-blind, placebo-controlled, multicentre, phase 3 trial](https://pubmed.ncbi.nlm.nih.gov/38782015/). *Lancet Neurology*. 2024.
16. Machado PM, et al. [Safety and efficacy of arimoclomol for inclusion body myositis: a multicentre, randomised, double-blind, placebo-controlled trial](https://pubmed.ncbi.nlm.nih.gov/37739573/). *Lancet Neurology*. 2023.
17. Yanaka A, et al. [Geranylgeranylacetone protects the human gastric mucosa from diclofenac-induced injury via induction of heat shock protein 70](https://pubmed.ncbi.nlm.nih.gov/17684364/). *Digestion*. 2007.
18. van Marion DMS, et al. [Oral geranylgeranylacetone treatment increases heat shock protein expression in human atrial tissue](https://pubmed.ncbi.nlm.nih.gov/31302249/). *Heart Rhythm*. 2020.
19. Endo S, et al. [Geranylgeranylacetone, an inducer of the 70-kDa heat shock protein (HSP70), elicits unfolded protein response and coordinates cellular fate independently of HSP70](https://pubmed.ncbi.nlm.nih.gov/17702888/). *Molecular Pharmacology*. 2007.
20. DailyMed. [BUPHENYL (sodium phenylbutyrate) prescribing information](https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid=463a36fa-3eb2-4326-8bd0-c8c7a11bca3a&type=display). Current label accessed 2026-08-26.
21. PMDA. [Selbex/teprenone product record](https://www.pmda.go.jp/PmdaSearch/rdDetail/iyaku/2329012C1026_1?user=1). Accessed 2026-08-26.
22. Mengel E, et al. [Efficacy and safety of arimoclomol in Niemann-Pick disease type C: Results from a double-blind, randomised, placebo-controlled, multinational phase 2/3 trial](https://pmc.ncbi.nlm.nih.gov/articles/PMC9293014/). *Journal of Inherited Metabolic Disease*. 2021.
23. Cheng J, et al. [Accurate proteome-wide missense variant effect prediction with AlphaMissense](https://doi.org/10.1126/science.adg7492). *Science*. 2023.
24. Huang Y, et al. [BubR1 phosphorylates CENP-E as a switch enabling the transition from lateral association to end-on capture of spindle microtubules](https://pubmed.ncbi.nlm.nih.gov/31201382/). *Cell Research*. 2019.
