# Three-minute Track 2 pitch: When lower aneuploidy is not rescue

**Target runtime:** 2:30–2:35 at 140–145 spoken words per minute; allow up to 2:55 for pauses and slide transitions
**Claim boundary:** preclinical research prioritization only; not a diagnosis, treatment, dose, safety claim, clinical recommendation, or claim of cure

## 0:00–0:22 — The problem judges should remember

**On screen:** `LOWER ANEUPLOIDY ≠ FEWER NEW ERRORS`

**Narration:**

“A lower aneuploid-cell count can lie. It may mean fewer segregation errors—or abnormal daughters died, cells stopped dividing, or measurement failed. In a suspected chromosome-instability disorder, those mechanisms imply opposite decisions. Our entry builds a false-rescue firewall before any medicine hypothesis advances.”

## 0:22–0:50 — The exact genetic hypothesis

**On screen:** `BUB1B: p.Leu737Ter + p.Asn1002Lys | phase unresolved`

**Narration:**

“Track 1 nominates BUB1B L737Ter plus N1002K; phase remains unresolved. N1002 is conserved in checked homologs. Wild-type structures support an Asn-contact motif, and AlphaMissense scores it 0.9229. None proves dysfunction. The next gate is orthogonal confirmation and direct phasing. Exact correction and isogenic assays then test stability and function. Cis phase, WT-equivalent abundance and half-life, or WT-equivalent function stops the relevant branch.”

## 0:50–1:19 — One bounded repositioning lead

**On screen:** `ARIMOCLOMOL = EX-VIVO PROBE, NOT A MEDICINE ANSWER`

**Narration:**

“Arimoclomol is the lead ex-vivo probe. If N1002K destabilizes BUBR1, heat-shock amplification might raise usable protein. In eleven paired samples from the arimoclomol arm, mean PBMC HSP70 increased from baseline at month twelve, but sample loss precluded a controlled placebo comparison. No study tests it in BUB1B or MVA. The label says its clinical mechanism in NPC is unknown. Trials in ALS and inclusion-body myositis missed efficacy endpoints. And Gaucher assays often used concentrations far above the label-estimated pediatric serum peak.”

## 1:19–1:52 — The exposure and causal funnel

**On screen:** `CONFIRM → PHASE → EXACT ALLELE → EXPOSURE → FUNCTION → SAFETY`

**Narration:**

“Only after the allele shows the predicted stability defect do we test 0.2 to 2 micromolar, measuring unbound concentration in the medium and intracellular drug by LC-MS, with pulse-and-washout conditions. Five micromolar is non-advancing exploration. Any signal seen only above 2 micromolar is a no-go. Exact correction is the causal anchor. Advancement requires checkpoint improvement and a concordant reduction in first-division errors, measured both per completed division and per enrolled founder, without cytostasis, toxicity, or increased abnormal-clone fitness.”

## 1:52–2:31 — The differentiator and its receipt

**On screen:** `AGGREGATE-COUNT STRESS TEST | EDIT-EVENT INFERENCE | ARTIFACT QC`

**Narration:**

“We implemented a deterministic benchmark for paired, hierarchical aggregate counts. The analyzer never receives the hidden simulation truth. Each independent edit event is the unit of inference. And a prespecified observed-data rule returns insufficient information instead of inventing a biological answer. Across fourteen thousand comparisons, all fourteen prespecified benchmark checks passed. Detection of strong new-error generation was ninety point six percent. The Wilson upper confidence bound for false new-error generation calls was zero point five six percent. And the sparse mixed case failed closed eighty five point two percent. Bulk-only results remain limited to the toy dynamics.”

## 2:31–2:58 — Why this can matter

**On screen:** `A REUSABLE FALSE-RESCUE FIREWALL`

**Narration:**

“This is not a cure claim. It is a modular path from confirmation and phase to one exposure-bounded experiment, plus a reusable firewall against false rescue. A positive result nominates independent preclinical replication—not treatment. A negative result records which prespecified gate failed, then stops unsupported medicine. For this child and future studies, rigor means learning the right mechanism before calling anything rescue.”

## Visual evidence notes

- Show the report's causal graph and decision gates; never show controlled genomic files or clinical narrative.
- Display the checked benchmark receipt hash and public repository URL during the benchmark segment.
- Add persistent footer: `Preclinical hypothesis only — no administration, dosing, efficacy, safety, or cure claim`.
- Source labels on the relevant frames: current MIPLYFFA prescribing information; Hanks 2004; Suijkerbuijk 2010; AlphaFold DB O60566; AlphaMissense/Cheng 2023; Mengel 2021; Fog 2018; Parfitt 2014; Benatar 2024; Machado 2023; repository benchmark receipt.
