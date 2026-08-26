# Track 2 public research-plan template — mechanism and falsifiability

Status: **generic preclinical design only; no subject-specific gene, allele, medicine hypothesis, or recommendation is published here**.

## Competitive landscape

Public entries cover several broad intervention classes. This repository records only the generic comparison axes; participant-derived candidate names and subject-specific mechanistic links stay outside the public analysis branch.

| Axis | Public comparison question |
|---|---|
| Protein stabilization | Can target abundance and function improve without broadly disrupting proteostasis? |
| Premature-stop rescue | Is exact-context full-length functional rescue possible at a clinically reachable exposure? |
| Checkpoint abundance | Does target engagement restore checkpoint function rather than merely change a marker? |
| Aneuploid-cell vulnerability | Is an apparent benefit actually selective toxicity or cell-cycle arrest? |
| Cancer milieu | Does the perturbation protect premalignant or transformed clones? |

A winning report should not be a longer drug list. It should resolve the two alleles separately, predeclare exposures and failure gates, and show why a candidate can improve mitotic fidelity without protecting premalignant clones.

The entry should complement existing community research with an allele-class causal chain and a governed cell-validation plan, not imply ownership of broader screening strategies.

## Generic hypothesis ladder

### 1. Synthetic stop-allele rescue challenger

`SYN-ALLELE-STOP` represents a wholly synthetic premature-stop example. A future private hypothesis may nominate an eligible perturbation only after the exact molecular context, current regulatory status, and exposure bridge are independently verified.

Why it is only a challenger:

- no subject-specific target or exact-context evidence is published here;
- readthrough amino-acid identity may not restore native sequence or function;
- published active concentrations must be reconciled with free systemic exposure;
- regulatory eligibility under the challenge is a hard gate.

Required experiment: exact-context reporter, allele-specific RNA, full-length target-protein measurement, inserted-amino-acid identification, checkpoint duration, localization, and single-cell aneuploidy at exposure-matched concentrations.

### 2. Synthetic missense-allele rescue challenger

`SYN-ALLELE-MISSENSE` represents a wholly synthetic folding/stability example. A future private hypothesis must identify a target-specific perturbation and demonstrate that its active concentration is compatible with clinically reachable unbound exposure.

Why it is only a challenger:

- no subject-specific target evidence is published here;
- chemical-chaperone effects are protein- and concentration-specific;
- broad transcriptional effects could confound apparent rescue;
- cancer-predisposition and chronic-exposure risks need explicit counterscreens.

Required experiment: isogenic wild-type, each single synthetic allele, compound synthetic genotype, and corrected control; endogenous target abundance and half-life; thermal stability; checkpoint-complex assembly and localization; mitotic timing; missegregation; micronuclei; proliferation and transformation counterscreens.

### 3. Mechanistic controls, not treatments

- A degradation-pathway perturbation can test whether degradation limits a missense allele, but a mechanistic control is not automatically a plausible chronic treatment.
- A chaperone-amplification control can distinguish target stabilization from nonspecific stress responses.
- A laboratory readthrough control may be unsuitable as a chronic lead because control utility and therapeutic suitability are separate questions.
- A target-abundance control can test the causal axis, but mechanistically adjacent compounds cannot be treated as interchangeable.

### Explicit no-go classes

- Spindle-checkpoint inhibitors.
- Antimitotics.
- Genotoxic drugs or DNA-damage amplifiers, especially for replication/cohesion mechanisms.
- Any perturbation whose apparent benefit is explained by arresting division or selectively killing aneuploid cells.
- Any proposal whose required current regulatory eligibility is not independently verified from an authoritative source.

## Factorial rescue design

Do not combine agents until each single-agent arm passes:

1. **Target engagement:** allele-specific RNA/protein effect at unbound, clinically reachable exposure.
2. **Mechanism rescue:** restored checkpoint and kinetochore function, not just a larger immunoblot band.
3. **Chromosome outcome:** fewer new missegregation events and micronuclei by blinded single-cell analysis.
4. **Clone safety:** no selective expansion or survival advantage for pre-existing aneuploid or transformed cells.
5. **Oncology compatibility:** no protection from current/likely sarcoma therapies; no reduction of antitumor immune function.
6. **Replication:** preregistered effect size and independent-laboratory replication.

Only then test a stop-allele strategy plus a missense-stabilization strategy. The combination advances only if it outperforms both single-agent arms without crossing a safety boundary.

## What can win the judging rubric

- **Scientific rigor (35%):** allele-specific causal graph, current regulatory verification, exposure bridge, negative controls, and predeclared no-go thresholds.
- **Potential impact (25%):** a decisive experiment that could rule a strategy in or out quickly, plus immediately useful pharmacology contraindications.
- **Innovation (25%):** dual-allele rescue rather than downstream symptom buffering, with direct protein-function and clone-safety coupling.
- **Scalability (15%):** a reusable null-plus-hypomorph rescue framework for other recessive rare diseases.

## Immediate next evidence tasks

1. Verify the private alleles and transcript context independently without copying identifiers into the public branch.
2. Verify every proposed perturbation's current regulatory status and systemic exposure from authoritative sources; reject it if the challenge criterion is not met.
3. Quantify free exposure against the concentration required for the proposed mechanism.
4. Search primary literature for direct target stabilization or functional-rescue evidence without using participant outputs as pipeline inputs.
5. Build a private evidence matrix with source, model, concentration, direction, contradiction, and go/no-go fields; export only a separately reviewed, identifier-free public summary.
