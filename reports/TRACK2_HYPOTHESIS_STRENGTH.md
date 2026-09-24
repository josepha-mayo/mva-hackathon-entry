# Track 2 hypothesis-strength contract

Status: synthetic software contract only. This document names no subject-specific gene, allele, or medicine.

A precise experimental hypothesis is how this package could help a child without pretending a desktop result is a rescue. Weakest link wins. Analog-allele, homolog, species-model, complementation, docking, AlphaFold, FoldX, AlphaMissense, geometry-ranking, coordinate-geometry, in-silico, pathogenicity-score, ESM, REVEL, MAVE, frequency, conservation, ClinVar, official-label, software, literature, cell-free, ectopic, unmatched, imposed-stress, ranking, predictor, unlabeled, transgene, overexpression, computational, cDNA, transient, biophysical, thermal-shift, purified-protein, protein-surrogate, unmatched-line, RNA-seq, or computational-haplotype evidence cannot stand in for an exact-allele assay. Heat-shock-family upregulation after aneuploidy cannot count as checkpoint rescue.

## What it scores

- Accepts the community observed/inferred/unknown table.
- Every link must carry a `hypothesis_role`: confirmation, pair, transcript, stability, probe, endpoint, falsifier, alternative, positive_control, negative_control, or other.
- Status maps to a ceiling: unknown is `unsupported`; hypothesis, inferred, planned, and synthetic-test are `experiment_to_run`; observed is `conditional_ex_vivo` for that link only.
- **Pair-program strength** (the child-facing probe) is the minimum of confirmation, pair, transcript, stability, and probe. Unmeasured RNA cannot support a child claim. A call-set presence tick is not orthogonal confirmation.
- **Isogenic-probe strength** is the minimum of stability and probe. Allele-class work can still be labeled work to run when phase is unresolved.
- At least one `falsifier` link, one `alternative` link, one `positive_control` link, and one `negative_control` link are required. Planned kill-rules, competing explanations, and controls are enough to keep working. An observed falsifier, an observed unexcluded alternative, or an observed failed control stops the lead.
- An `observed` confirmation, pair, transcript, stability, probe, or endpoint label without a matching gate pass is a stop (`observed_without_gate`), including when those nested objects are omitted. Identity binds to confirmation, phase, and transcript. Stability binds to hypomorph. Probe binds to exposure. Endpoint binds to concordance. A nested `status` tick, or a `program_effect=pass` object without the matching assessor schema (and gate, when that object carries one), cannot bind.
- A clone-safety stop, or concordance `competing_toxicity`, auto-fails the alternative (`syn-auto-competing-toxicity`). Fitter error-line daughters cannot sit beside a planned competing explanation.
- `declared_overall_strength` cannot exceed the work ceiling, and cannot be `conditional_ex_vivo` unless the pair-program strength is already there.
- `declared_probe_is_medicine` is always a stop.

The checked-in synthetic table is honest: pair strength `unsupported`, isogenic probe `experiment_to_run`, child claim `unsupported`.

## What it refuses to do

- Call a probe a medicine, dose, or cure.
- Let an analog allele, homolog, ortholog, paralog, mouse, yeast, rat, Drosophila, zebrafish, Xenopus, or C. elegans allele, nearby polymorphism, AlphaFold, FoldX, AlphaMissense, geometry ranking, coordinate geometry, docking, complementation, in-silico score, pathogenicity score, ESM, REVEL, MAVE, population frequency, conservation, ClinVar assertion, official medicine label, software result, public software catalog, public database, ontology, literature record, cell-free thermal shift, purified-protein row, cell-free biophysical row, ectopic transgene, transient transfection row, cDNA row, overexpression row, protein-surrogate row, unlabeled restoration, computational assay, imposed-stress assay, RNA-seq phase call, computational haplotype caller, desktop ranking, computational predictor, or unmatched line prove exact-allele function.
- Treat heat-shock-family upregulation, organ-size restoration, chaperone PD, lower bulk aneuploidy, selection, arrest, or death-masking as checkpoint rescue or target engagement.
- Let a declared `conditional_ex_vivo` leapfrog unresolved phase or unmeasured RNA.
- Keep a pair-program story that cannot name a kill-rule, a competing explanation, or a positive and negative control, or keep a lead after that kill-rule, alternative, or failed control is observed.
- Label confirmation, phase, transcript, stability, probe, or endpoint `observed` when the nested gate has not passed, including when those objects are omitted. A nested status tick or schema-less pass object is not a nested pass.

## How to run

```powershell
python -m unittest tests.test_hypothesis -v
python scripts/assess_hypothesis_strength.py --input templates/community/observed_inferred_unknown.synthetic.json
```

## Claim boundary

Hypothesis-strength software contract only. Weakest link wins. A precise experimental hypothesis is not a treatment, dose, or cure.
