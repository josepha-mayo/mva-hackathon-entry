# Where is functional protein being lost?

Research design candidate, 22 October 2026. All computed examples below are
invented. This supplement is outside the signed release and does not change
any advancement gate. It adds no medicine, dose, biological result, or claim
of benefit.

The child needs a useful experiment, not a more confident drug name. The
specific question is whether too little functional checkpoint protein reaches
the next division because of low input, loss before assembly, clearance after
assembly, or a defect that remains when protein amount is restored. Those
possibilities predict different experiments and can retire different rescue
strategies. None has been established for the proposed genotype.

The stronger hypothesis is **a shortage of functional protein at the time it
is needed**, with competing causes. A folding intervention earns a place only
if the measured bottleneck is compatible with it. The existing generation
versus selection contract then asks whether fewer new chromosome errors are
made without losing divisions or protecting abnormal clones.

## Evidence and inference

Published experiments on other disease-associated alleles distinguish
abundance defects from specific functional defects; restoration of an
engineered checkpoint readout at matched protein abundance supports testing
that distinction. It does not establish this allele's mechanism or response
to a medicine. [Suijkerbuijk et al., 2010](https://pubmed.ncbi.nlm.nih.gov/20516114/)

Proteome-wide pulse-chase work found age-dependent loss for a subset of
proteins and modeled an early state transitioning to a later state. That is
the precedent for the illustrative model here; it does not identify either
state with folding, assembly, or function for this target.
[McShane et al., 2016](https://doi.org/10.1016/j.cell.2016.09.015)

Protein birthdating also demonstrates that molecular age can be measured in
defined windows. A labeling window contains a distribution of ages; it is
not a pure mature population. These studies justify an assay-design question,
not a biological discovery in the child.
[Meadow et al., 2024](https://doi.org/10.1016/j.mcpro.2024.100791)

## An executable counterexample

```sh
python scripts/demo_functional_supply.py
python -m unittest tests.test_functional_supply -v
```

The [source](../src/mva_hackathon/functional_supply.py) solves two linear
compartment equations exactly. `U` is a pre-assembly pool and `M` a mature
pool; these are model labels, not experimentally established states:

```text
dU/dt = s - (m + u + g) U
dM/dt = m U - (d + g) M

steady U = s / (m + u + g)
steady M = m U / (d + g)
measured total = U + M
illustrative functional supply = a M
```

`s` is input into the measured pool, `m` transition, `u` early loss, `d`
mature loss, and `g` per-cell dilution. Dilution is not destruction. `a` is
an independent illustrative functional weight. Input is not ribosomal
initiation; mature amount is not itself a functional assay. The model assumes
constant rates, linear detection, perfect label incorporation, and no feedback.

| Invented world | Input s | Transition m | Early loss u | Mature loss d | Total | Mature amount |
|---|---:|---:|---:|---:|---:|---:|
| Reference | 1 | 1 | 0 | 0.1 | 11 | 10 |
| Early loss | 1 | 1 | 9 | 0.1 | 1.1 | 1 |
| Low input | 0.1 | 1 | 0 | 0.1 | 1.1 | 1 |
| Mature loss | 1 | 1 | 0 | 10 | 1.1 | 0.1 |

All rows use `g = 0`. Rates use arbitrary per-hour units. Three distinct
causes give **the same tenfold fall in bulk protein**. No bulk threshold can
choose between them. The demo further constructs identical total-protein and
labeling trajectories with a tenfold difference in the independent functional
weight: even an ideal turnover curve cannot establish function.

An additional exact ambiguity matters experimentally: doubling input while
halving unknown recovery produces the same entire measured new-label curve.
Ideal, absolutely calibrated time courses can separate the selected low-total
examples, but that does not prove identifiability under a real assay's noise,
age mixtures, changing synthesis, cell-cycle effects, or recovery bias.

The demo prints every invented parameter and time point as JSON. Five
counterexamples reproduce. No rates are fitted, no study power is estimated,
and no mechanism is selected. Save stdout outside the checkout to retain a run.

## One small experiment with several possible answers

This is a plan for a qualified laboratory after the existing identity and
material gates pass. It does not authorize work on the child's cells.

Start method development in renewable material. Then compare the confirmed
test genotype, precise single-allele correction, and an independently derived
matched carrier-state control. Correcting one allele leaves the other allele
present: a full wild-type line is an additional reference, not an automatic
equivalence target for a single-allele edit. Independent events, reciprocal
recreation, and the existing clone qualification remain required.

Measure a short labeled cohort and a longer cohort with declared age windows,
sampling both at early and later chase times. Qualify target recovery, label
incorporation, precursor-pool behavior, cell number, and cell-cycle balance.
Independently assess nascent input before claiming synthesis or a maturation
yield. A long pulse, a translation-block chase, and an induced degradation
tag are perturbations or age mixtures; none alone defines native mature
protein half-life. Choose actual timing, input requirements, error model,
equivalence margins, and stopping rules from blinded assay feasibility data;
the toy model's times and rates are not a laboratory protocol.

| Qualified result | Next discriminating question | Consequence for the hypothesis |
|---|---|---|
| Input low; conditional survival normal | Does the transcript/input deficit reverse with precise correction? | Reconsider an input-limited route; do not call it a folding lesion |
| Excess early loss; later survival preserved | Is acquisition of assembly/localization and function reduced per independently measured input? | Test an early maturation bottleneck; retain alternatives to misfolding |
| Comparable early recovery; excess later loss | Does native loss remain after age mixture, state and dilution controls? | Investigate mature maintenance; do not assume a chaperone match |
| Amount restored; function remains defective | Does precise correction restore the missing functional endpoint? | Stop abundance-only rescue as a sufficient explanation |
| Abundance and function normal | Is the proposed causal chain wrong or the model uninformative? | Retire this bottleneck in the tested system; reopen alternatives |
| Recovery, input, or age windows unqualified | Which measurement is identifiable? | Report mechanism unresolved; spend no drug-screen material |

Mixed mechanisms are allowed. A negative result in one lineage does not
exclude a different mechanism elsewhere. Orthogonal native-turnover methods
that disagree should trigger an age-mixture and perturbation audit, not a vote
for the more attractive half-life.

## The sharper rescue hypothesis: intervene during the vulnerable window

If independent input is preserved, early loss is excessive, and the surviving
protein remains functional, the actionable hypothesis is that **functional
delivery can improve during a restricted early-life window even when the
mature pool's decay rate does not change**. That is more specific than asking
whether a perturbation increases total protein or its apparent half-life.

The demo illustrates the timing consequence. For a wholly invented cohort,
the same one-hour reduction in early loss is applied immediately or after
three hours. Read at four hours, early intervention produces over three times
the mature amount, while late intervention cannot recover the already lost
cohort. This is a mathematical example with a fixed rate change, not a drug
model or a predicted therapeutic window.

After a scientifically qualified comparison and an independently justified
exposure protocol support a probe experiment, compare exposure during
the labeled cohort's birth window with exposure after that cohort has aged.
Qualify intracellular concentration-time profiles, response onset, carryover,
recovery and state matching. Do not equate equal nominal exposure with equal
effective perturbation. Measure delivery into the function-qualified pool
per independently identified input, then division-level function. A timing
difference alone cannot prove folding or direct target action: transcription,
delayed pharmacodynamics, assembly and measurement recovery remain rivals.
If the input or recovery denominator is unidentified, this experiment cannot
report a maturation yield.

## What success would buy

The useful output is a measured reason to retain or retire a rescue class
before scarce participant material is spent on a broad screen. A later
candidate must still improve division-level function at qualified exposure,
preserve completion and daughter outcomes, and undergo justified abnormal-
clone assessment and independent replication. The historical lineage/power
assurances are withdrawn in the [current audit](research_audit.md); its old
gate labels cannot license advancement. Neither more
protein nor a cleaner endpoint cell population is sufficient.

This is an executable explanation of a measurement ambiguity and a proposed
way to investigate it. It is not evidence that the child has this bottleneck,
that a candidate will work, or that developmental injury or cancer risk can
be reversed.
