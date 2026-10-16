# Track 2 portability map — what transfers, what must be rebuilt

The scalability claim in the report (§7) is deliberately narrow: this package
is not a drug-discovery platform. It is a **decision contract** for
chromosome-instability rescue screens — the layer that decides whether an
observed "fewer errors" is a real rescue or a selection artifact. That layer is
the part that ports; the biology plugged into it does not. This map makes the
boundary explicit.

## Transfers unchanged (the contract machinery)

| Component | Where implemented | Why it is disease-agnostic |
|---|---|---|
| Generation-vs-selection estimand pair | `mva_hackathon/lineage.py` | Competing-risk first-attempt partition; enrolled-founder denominators; daughter-fate deconvolution — all defined on division outcomes, not on any gene |
| Completion-equivalence rule | `mva_hackathon/lineage.py` | Four-region ratio-interval rule on the predeclared [0.95, 1.10] band — an inference rule, not a biology claim |
| Clone-safety lattice | `mva_hackathon/clone_safety.py` | Resolved-daughter completeness floors (`MINIMUM_RESOLVED`), positive-vs-negative reproduction ratios, `not_assessable` refusal — all generic |
| Selection-agent quarantine | `mva_hackathon/clone_safety.py`, exposure records | Aminoglycoside-history class, batch taint semantics — applies wherever a selection antibiotic is used |
| Save-path suite | `mva_hackathon/save_path.py` (126 cases) | Named false paths are confound classes (cytostasis, pruning, masked follow-up, measurement bias), not gene-specific scenarios |
| Attestation & reproducibility | `release/`, `scripts/verify_track2_reproducibility.py`, RFC 3161 timestamp | Byte-bound manifest, Ed25519 signature, TSA proof — domain-independent |
| Community templates | `templates/community/` (14 files) | Identifier-free schemas for phase record, allele-function scorecard, exposure table, blinded count table, replication decision, family-facing summary |

## Must be rebuilt per disease class (the plugged-in biology)

| Component | This package (BUB1B-class MVA) | What rebuild means |
|---|---|---|
| Candidate mechanism | N1002K missense hypomorph → chaperone-axis abundance rescue | A new allele needs its own mechanistic hypothesis and its own falsifier |
| Gate 2–4 assay content | Transcript/protein abundance, localization, correction controls | New gene ⇒ new functional assays and new exact-correction anchor |
| Exposure gate & ladder | Arimoclomol ≤ 2 µM from label-derived pediatric PK | New candidate ⇒ new exposure window and harm boundary |
| Functional endpoints | Kinetochore-assembly/segregation error readouts | Endpoint must measure the class's actual defect |
| Completion-band rationale | Growth-disorder context ⇒ completion loss is harm | Re-derive for each indication's harm direction |
| Named false paths | Configured for this assay stack | New assay ⇒ new fixture set (the *classes* persist; the fixtures are re-built) |

## Class-by-class

| Target class | What transfers | What is rebuilt |
|---|---|---|
| **TRIP13-biallelic MVA** (checkpoint-impaired, same segregation-error phenotype; in-disease exact-correction precedent: Yost 2017 restored checkpoint function in patient cells) | Entire contract; estimands; save-path classes; exact-correction control class (the precedent already exists in-disease) | Candidate hypothesis (TRIP13 AAA+ ATPase substrate — different mechanism axis), Gate 4 stability readout for the TRIP13 allele, exposure window for whichever candidate is proposed |
| **CEP57-class / unexplained MVA** (minimal checkpoint deficiency in reported series) | Contract machinery transfers | The counterscreen logic must be re-aimed — this class's defect is not spindle-checkpoint-driven, so the generation endpoint and the harm direction need re-derivation; the checkpoint-defective assumption in this package's §5 does not carry |
| **Generic CIN rescue screen** (e.g., tumor-cell chromosome-instability modulation) | Generation-vs-selection estimands, completion band, clone-safety lattice — the machinery exists precisely because CIN screens are confounded by selection | Assay endpoints, exposure window, and — critically — the harm direction may *invert*: in an oncology screen, killing error-bearing daughters may be the goal rather than the confound. The contract's confound classes still apply, but their interpretation is re-aimed |

## What this is not

- Not a claim that the BUB1B hypothesis generalizes — the candidate card is
  specific to N1002K and is expected to die in Gates 2–4 for most alleles.
- Not a second instantiation yet: the community templates are the porting
  surface, and each row above names what a second disease class must rebuild.
  A demonstrated second-class run is the natural next artifact.
- Not a platform claim: the value transferred is a falsification discipline
  (estimands, quarantine, save-path enumeration), executable as shipped.
