# Track 2 judge package — method documentation drafts

Scope boundary, stated once and applicable to every section: this package is a
**method plus a synthetic fail-closed gate suite**, not a treatment claim. Every
evidence object in the repository is synthetic and carries `synthetic_only: true`
plus a claim-boundary string. No medicine is activated; arimoclomol appears only
as a comparator-only concept. The submission GO checker
(`scripts/check_submission_go.py`) reports NO-GO until five external attestation
artifacts exist (release signature, timestamp proof, operator authorization,
participant-data authorization, privacy review) — all five are present under
`attestation/` as of 2026-09-24, including a verifiable Ed25519 detached
signature and a granted RFC 3161 timestamp token. A green check is documented
in its own docstring as necessary, never sufficient.

Central thesis under test: *exact correction supplies the participant-specific
cellular positive control that a repurposed medicine must match, while lineage
tracking prevents selection or cytostasis from masquerading as rescue.*

Source anchors: `src/mva_hackathon/lineage.py`, `exposure_gate.py`,
`assay_power.py`, `clone_safety.py`, `save_path.py`,
`program_gates.py`, `community_pipeline.py`.

---

## 1. Worked example — `clean_generation` fixture, then one flipped input

Fixture: `build_adversarial_fixture("clean_generation")`
(`lineage.py:1686-1705`). Three paired edit events; each (event, arm) enrolls
110 founders with the identical competing-risk partition: 108 completed, 1
pre-division death, 1 no-division, 0 dropout. Error-bearing completions differ:
vehicle 24/108, treatment 6/108. Every completed founder produces two recorded
daughters; by construction one carries a resolved fate (`reproduced`) and one is
`not_followed`. Verified analyzer output (`analyze_lineage_study`):

| Estimand | Vehicle per event | Treatment per event | Ratio estimate [interval] | Disposition |
|---|---|---|---|---|
| generation_rate | 24/108 = 0.222 | 6/108 = 0.0556 | 0.265 [0.165, 0.428] | reduced (<=0.75, upper<1) |
| founder_error_bearing_completion | 24/110 = 0.218 | 6/110 = 0.0545 | 0.265 [0.165, 0.428] | reduced (co-primary) |
| division_completion | 108/110 = 0.982 | 108/110 = 0.982 | 1.000 [0.977, 1.023] | inside [0.95, 1.10] |
| relative_error_daughter_reproduction | 24/24 vs 84/84 | 6/6 vs 102/102 | 0.947 [0.829, 1.081] | estimable, neutral |
| pre_division_death | 1/110 | 1/110 | 1.000 [0.272, 3.683] | estimable, no spike |
| dropout | 0/110 | 0/110 | inestimable | `no_observed_events` — refused, not zero-width |

Mechanics the analyzer applies, per event-arm pair: Jeffreys-smoothed point
rates `(k+0.5)/(n+1)`; per-event paired log-ratios pooled across the three
events; interval half-width is the quadrature sum of a Student-t component at
df=2 (4.303, estimated between-event variance — here identically zero because
all three events are numerically identical) and a normal-z component (1.96,
known within-event delta-method variance). Both co-primary intervals sit
entirely below 1.0 with ratios under the 0.75 cutoff; the division interval
sits entirely inside the pediatric band with zero absolute drop; the selection
estimand is estimable and neutral; all nine QC flags and five adverse
biological flags are false; only `generation_reduction` is set. Result:
`clean_generation_signal = true`, interpretation
`generation_reduction_without_detected_configured_confound`. Minimums met
throughout: 3 paired events, 2 clones per event-arm, >=8 completed per
event-arm, resolved-daughter floors (>=2 error / >=8 non-error per event-arm).

**The flip: censor half the resolved daughters.** Two layers respond
differently, and the difference is the point of the design.

- At the founder-level analyzer (verified): halving resolved daughters leaves
  12 error / 42 non-error resolved on vehicle and 3 / 51 on treatment — still
  above the floors, so the selection estimand stays estimable
  (0.908 [0.703, 1.174]) and the study still certifies clean. The analyzer
  requires only enough resolved progeny to deconvolve selection; it is
  deliberately tolerant of partial censoring. Pushing past the floors —
  censoring *all* resolved daughters — makes the selection estimand
  inestimable and the interpretation degrades to
  `generation_signal_incomplete_deconvolution`: a generation drop the
  analyzer cannot separate from daughter-fate selection is never certified
  clean.
- At the clone-safety gate on the lineage-counts table (verified, upstream of
  lineage analysis in the pipeline): the same half-censoring fires
  `not_assessable`. Per (event, clone, run) nest, treatment-arm resolved
  error daughters drop 8 -> 4, below the fixed `MINIMUM_RESOLVED = 8` floor
  (`insufficient_positive_followup`); vehicle-arm resolved drop 24 -> 12,
  below the 24 declared daughter slots (`incomplete_positive_followup`).
  Censored or `not_followed` daughters count in `followed` but never in
  `resolved = reproduced + died`, so they cannot satisfy the completeness
  obligation or dilute a rate. The gate holds the program before any rescue
  interpretation is reached.

Net: partial censoring is absorbed at the estimand layer but refused at the
completeness layer; total censoring is refused at both. The save-path suite
exercises the same refusal as named false paths (`censored_daughters_dilute`,
`clone_safety_under_followed`, `multipolar_daughters_unfollowed`).

---

## 2. Precedent / source table

Status vocabulary: **cited** = named external precedent, not re-derived here;
**novel-here** = no precedent claimed, integration is this package's;
**synthetic** = exists only as software contract/fixture.

| Method component | Closest precedent | Status | What this package adds |
|---|---|---|---|
| Corrected-isogenic control | Merkert 2019, Parkinson GBA | cited | The control is a required genotype class (`exact_corrected`) inside a gate lattice, not a figure panel; a correction that is computational, cell-free, ectopic, unmatched-line, imposed-stress, or analog-allele cannot discharge it, and the control defines the bar a comparator must match — it is never itself a medicine result |
| Reciprocal editing | Soldner 2011, isogenic iPSC pairs | cited | `recreated_missense` must restore the exact endpoints the defect was called on; analog, homolog, nearby, or unlabeled recreation is refused at gate level, making reciprocity an executable precondition rather than a suggestion |
| Division-gated micronucleus scoring | CBMN assay / OECD TG 487 | cited (TG 487 also cited in `reports/TRACK2_EXPOSURE_GATE.md` with OECD GD 211) | The per-division error outcome and the exposure-schedule vocabulary (constant vs pulse, washout, >=1 h window) are contract fields with pass/stop semantics, not guideline text |
| Exact competing-risk first-attempt lineage | none claimed | novel-here | Enrolled-founder first-attempt partition across five exhaustive outcomes with pre-division death labeled separately from other non-completion; daughters attach only to completed divisions and resolve to terminal fates |
| Selection-agent carryover quarantine | none claimed | novel-here | Aminoglycoside history class blocks advancement outright; clearance honored only with a declared method; batch declaration all-or-none with whole-batch taint; selection metadata binds into the execution fingerprint so post-hoc edits fail binding |
| Analyzer-priced power lock | none claimed | novel-here | `detection_rate` is the fraction of 400 seeded simulations in which the *production analyzer* certifies `clean_generation_signal` — the priced object is the real decision rule, not a pooled binomial surrogate; Wilson lower bound must also clear the >=0.8 floor |
| Event-level paired inference with quadrature interval | none claimed | novel-here | Per-edit-event paired log-ratio estimands; Student-t df=2 on estimated between-event variance plus normal z on known within-event variance, combined in quadrature so sparse-but-honest denominators are not double-penalized and sparse events cannot borrow precision |

No other citations are claimed. Merkert 2019 and Soldner 2011 are named as
prior art for the *concept* of isogenic correction controls; this package does
not reproduce, extend, or validate their biology.

---

## 3. Candidate card — BUB1B compound heterozygote, MVA setting

Like every other Track 2 method document, this package is identifier-free:
exact allele notations, accessions, and the shared transcript are named only
in the judged report and the bound attempt-1 artifacts. What follows is the
structure of the submitted hypothesis.

**Alleles** (on one shared MANE Select transcript, per the judged report):
- A premature-stop allele — a germline Pathogenic/Likely-pathogenic ClinVar
  aggregate from expected nonsense consequence plus the established BUB1B
  loss-of-function mechanism; a database assertion, not participant-specific
  confirmation.
- An uncharacterized missense allele in the C-terminal kinase-domain region.
  No ClinVar record exists for the exact nucleotide change; an alternative
  substitution encoding the same protein change is a single-submitter VUS,
  and its in-silico pathogenicity score is prioritization, not function.

**Hypothesis class:** stability-rescue candidate, *unconfirmed*. Causal chain
under test: trans phase -> stop-allele transcript depletion plus a missense
defect -> insufficient functional BUBR1 -> checkpoint/attachment failure ->
new segregation errors per division. Each link is labeled observed, inferred,
or unknown in the evidence record; most are unknown today.

**Pivotal unknowns the lattice is built to settle:**
- *Function-when-abundant*: is the missense allele a dose problem (functional
  when its abundance is normalized — the Suijkerbuijk-class hypomorph
  pattern) or qualitatively broken? `missense_at_abundance` row decides; an
  allele still defective at normalized abundance cannot be rescued by
  raising abundance.
- *Dominant-interference carrier dose*: does the heterozygous missense carrier
  show function-axis defects the stop carrier lacks? `missense_carrier` vs
  `stop` decides; a carrier-only defect is dominant interference, and
  stabilizing an interfering product is contraindicated — the gate stops.

**Comparator-only concept:** arimoclomol. Rationale is an exposure-gated
ex-vivo probe of stress-contingent chaperone amplification only. No direct
evidence exists for BUB1B, the missense allele, MVA, spindle-checkpoint
rescue, or segregation rescue; the FDA label leaves the NPC mechanism
unknown; published
Gaucher-cell nominal concentrations sit ~30-480x the label-estimated
pediatric mean serum peak; two completed randomized trials in other diseases
failed their efficacy endpoints. It cannot repair cis phase or restore a
depleted stop transcript.

**Required before any medicine comparison is even assessable:** orthogonal
confirmation of both alleles -> direct trans phase -> allele-specific RNA
fate -> exact-allele basal cellular endogenous defect reversed by exact
correction and restored by reciprocal recreation -> informative carrier dose
control and function-at-abundance -> measured selection-agent-clean exposure
-> powered locked design -> blinded lineage counts -> clone safety -> clean
co-primary lineage signal. Current decision state: GO for confirmation and
phase only; everything downstream holds.

**Explicitly not claimed:** treatment, dosing, administration, clinical
benefit, cure, rescue of a person; missense-allele pathogenicity, instability,
or drug responsiveness; arimoclomol efficacy in any indication relevant here.

---

## 4. Gate chain mapped to a real rescue program

Pipeline order implemented in `community_pipeline.py:179-438` (stop-early: the
first non-pass blocks every downstream step). One line per gate — what it
proves vs what it refuses.

- **Confirmation** — proves both alleles observed in an assay-matched genomic
  library with the pinned layout digest and both strands counted; refuses
  truncated lane sets, RNA libraries, unmatched specimens, single-strand
  calls, and filename-digest mismatches.
- **Phase** — proves trans configuration via molecule-level or parental
  evidence from the matched line; refuses computational haplotype calls,
  RNA-seq phase, and unmatched-line spanning molecules.
- **Transcript** — proves allele-specific RNA fate (stop depleted, missense
  expressed) in the confirmed line; refuses computational NMD predictors,
  protein-surrogate rows, and unmatched genotype lines.
- **Allele function (hypomorph lattice)** — proves an exact-allele basal,
  cellular, endogenous defect that exact correction reverses and exact
  recreation restores; refuses analog/homolog/nearby alleles, computational
  or cell-free rows, ectopic expression, unmatched specimens, imposed-stress
  conditions; `missense_carrier` dose control separates dose loss from
  dominant interference; `missense_at_abundance` separates unstable-but-
  functional from broken-at-any-abundance.
- **Exposure** — proves measured unbound-medium plus intracellular parent
  inside the <=2 µM conservative window with constant contact >=1 h, verified
  allocation, recorded vehicle baseline, and clean selection history;
  refuses nominal-only rows, pulse-only support, >=50 µM (hard stop),
  aminoglycoside carryover, clearance claims without a declared method,
  partial or inconsistent batch declarations.
- **Assay power** — proves the locked design detects the predeclared
  generation drop through the production analyzer at >=0.8 (400 sims, Wilson
  lower bound also >= floor), sized no larger than the realized counts;
  refuses unlocked plans, sub-minimum designs, missing locked margins,
  pediatric-band-incompatible completion, bulk-fraction endpoints, and
  insufficient remaining population doublings.
- **Blinded lineage counts / count identity** — proves blinded count rows
  reconcile exactly with the lineage counts, the power plan, and the
  exposure context; refuses disagreement, dropped or duplicated rows,
  arm-dependent payload drift, and competing labels silently absent from the
  blinded table.
- **Clone safety** — proves error-line daughters did not gain reproductive
  fitness under treatment and the negative stratum shows no death shift;
  refuses resolved below the >=8 floor, resolved below declared slots,
  reproduction ratio >=1.25, negative death ratio >=2x, and asymmetric
  negative follow-up; unlocked or unblinded tables cannot pass. Multipolar
  divisions are declared segregation errors: each requires >=3 recorded
  daughters and co-declared slots in [2*divisions + multipolar,
  2*divisions + 2*multipolar]; a widened slot obligation without resolved
  fates to fill it holds the nest rather than letting progeny slip the net.
- **Lineage analysis** — proves co-primary reductions certified, all core
  estimands plus the selection estimand estimable, pediatric completion
  equivalence, zero adverse and zero QC flags; refuses certification when
  any flag fires, any required estimand is inestimable, or completion drops.
- **Interpretation** — proves a single governed verdict word from the bounded
  vocabulary; refuses free-text rescue — there is no word for "rescue" that
  the analyzer can emit.

The chain's refusal semantics are asymmetric on purpose: `stop` verdicts are
falsifications or safety events; `hold`/`not_assessable` verdicts mean the
evidence cannot currently be interpreted — the design treats
"cannot assess" as a blocking state, not a soft pass.

---

## 5. Estimand scope and the co-primary coincidence boundary

The six estimands are **first-generation cellular lineage estimands**. They
describe what the enrolled founder's first division attempt produced —
error-bearing completion, clean completion, no division, pre-division death,
dropout — plus one daughter-generation quantity (relative error-daughter
reproduction). They are not durability estimates, not multi-generation
stability, and not clinical outcomes. Nothing in the contract measures
whether corrected or treated lineages remain euploid beyond the daughters'
first resolved fate.

The co-primary pair is `generation_rate` (error-bearing / completed) and
`founder_error_bearing_completion` (error-bearing / enrolled). Algebraically,
founder = generation x completion, so their *ratios* coincide exactly when
the division-completion ratio is 1.0 — and the pediatric band forces
certified runs toward that point. In the worked example both ratios are
0.265 because both arms completed 108/110; the intervals differ only in the
within-event term (n=108 vs n=110 denominators). In the limiting case —
zero competing risks, detected == opportunities — the two estimands are
literally the same quantity.

That is the honest coincidence boundary: the second estimand is not
independent replication of the first. Its real function is a coincidence
check — the estimands diverge precisely when competing-risk censoring is
asymmetric across arms, which is the signature under which selection,
survival bias, or cytostasis would masquerade as rescue. Requiring both to
certify is therefore cheap insurance in the clean regime and the actual
detector in the dirty one. The cost is bounded: where the two coincide,
the co-primary rule adds no incremental information beyond forcing the
completion estimand into the same inferential frame — a price the method
pays deliberately so that a per-division error rate can never be
certified while founders are silently being lost upstream.

---

## 6. Residual risks and declared-metadata limitations

What the suite cannot prove, stated plainly:

- **Declared metadata is self-reported.** `culture_batch_id`,
  `selection_agent`, `selection_agent_cleared`, `selection_clearance_method`,
  timestamps, and specimen labels are declared fields. The contract enforces
  internal consistency (all-or-none batches, fingerprint binding, vocabulary)
  — it cannot verify the physical truth of any declaration.
- **Physical execution needs external attestation.** Dosing accuracy,
  randomization entropy authenticity, sample identity, and operator
  authorization are outside the software boundary; the GO checker names five
  required attestation artifacts and reports NO-GO without them. The
  synthetic fixture seed is explicitly recorded as *unattested* entropy and
  is not a model for a real allocation.
- **Synthetic fixtures are not biological evidence.** Every fixture,
  benchmark, and receipt describes software behavior. A reachable true path
  demonstrates the contract can be satisfied, not that any real experiment
  was performed or that rescue occurred.
- **The power certificate is a 400-simulation Monte Carlo bound.** It carries
  sampling error (hence the mandatory Wilson lower bound) and a fidelity
  ceiling (~16k simulated founders per study). It prices the decision rule,
  not biology.
- **Homogeneous-event plans report an upper bound.** Without
  `locked_between_event_concentration`, simulated events are exchangeable at
  the locked rates; real heterogeneity, dropout, and daughter censoring can
  only lower the certified rate — daughters are simulated fully resolved, so
  censoring and selection drift are not priced at all.
- **Declared clearance is not measured clearance.** A clearance claim is
  honored only alongside a declared method, but the method itself is
  declared, not analytically verified; aminoglycoside history blocks
  regardless because the confound (readthrough agents inducing the claimed
  phenotype) cannot be excluded by declaration.
- **Configured thresholds are judgment frozen into code.** Share limits
  (clone 0.60, field 0.70), ratio cutoffs (0.75/1.25/2.0), resolved-fate
  floors, and the pediatric band are declared constants. The clean
  interpretation is correspondingly named
  `generation_reduction_without_detected_configured_confound` — detection
  is bounded to configured confounds.
- **The save-path suite is a configured matrix, not exhaustive coverage.**
  126 blocked synthetic false paths demonstrate the declared contract holds
  on the scenarios authors anticipated; unanticipated real-world failure
  modes are outside the demonstrated surface.

---

## 7. Why this is not just a test suite

The method is the predeclared set of estimands plus the gates that bound
their interpretation; the software is that method made executable, so the
contract — not a narrative — is the reviewed object. The save-path suite
exists to demonstrate the contract cannot be trivially satisfied: exactly
one synthetic true path opens while 126 configured false paths stay blocked,
and cardinality drift in that matrix is itself a failure. The GO checker
refuses self-certification: it verifies every machine-checkable blocker and
names the external attestations a machine cannot produce, so the package
fails closed until human and institutional evidence exists.
