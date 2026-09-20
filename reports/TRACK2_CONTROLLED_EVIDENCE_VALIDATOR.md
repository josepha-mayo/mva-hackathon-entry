# Track 2 controlled-evidence validator — design requirements

Status: design requirements only. No controlled-evidence schema, plan loader,
or promotion path exists in this repository today. This document does not
authorize participant material use, a medicine claim, a freeze, a host, an
upload, or a submission. Real `active_lead` promotion remains HOLD until an
implementation of this contract exists **and** passes independent review.

## Why this exists

The candidate ledger admits `privacy_class="controlled"` and
`source_class="controlled_source"` vocabulary, and the public release path
already rejects both. The sample-stewardship engine validates only
`synthetic_only=true` plans: synthetic evidence may bind only synthetic-fixture
candidate rows and can never authorize a biologically interpreted `active_lead`.
That is the correct fail-closed posture — no path to a biological active lead
exists on this desktop.

If governed (private, participant-relevant) evidence ever exists, a second,
separate validator must check that evidence before any controlled row may
advance. A synthetic plan that is merely relabeled, or a controlled plan checked
only by the synthetic contract, must fail. This document fixes the requirements
for that validator before any code is written.

## Hard invariants

1. **Separate artifact family.** Controlled evidence uses its own schema id,
   distinct from `mva.track2-sample-stewardship/v*`. A controlled plan must be
   rejected by `assess_sample_stewardship` and by every loader that expects a
   synthetic plan. A synthetic plan must be rejected by the controlled loader.
   Neither validator may silently reinterpret the other's documents.
2. **Mutual binding preserved.** A ledger row carrying
   `sample_stewardship_promotion` fails closed without a plan; a plan supplied
   to a ledger with no promotion fails as unbound; a digest mismatch fails as
   stale. The controlled path keeps this shape exactly.
3. **Privacy symmetry.** A controlled plan may bind only rows whose effective
   source class is `controlled_source` and whose `privacy_class` is
   `controlled`. A `derived_evidence` row resolves to its
   `parent_source_class`. Mixing synthetic and controlled evidence in one plan,
   or binding controlled receipts to public/synthetic rows, is rejected.
4. **Public surface unchanged.** `public_only` loading, ranking, and
   canonicalization keep rejecting controlled rows. The controlled validator
   emits identifier-free verdicts and digests only; no controlled payload,
   receipt body, or identifier is printed, staged, or written into this public
   tree.
5. **Fail closed on doubt.** Missing, malformed, mismatched, stale, or
   unverifiable fields reject. Absence of an attestation is a rejection, never
   a warning. No field is optional where a synthetic analogue was required.

## Evidence-binding requirements the synthetic contract cannot express

The synthetic contract binds opaque identities inside a self-contained plan.
That is sufficient for a simulation and insufficient for governed evidence,
because every assertion is self-issued. The controlled validator must
additionally require:

1. **External attestation.** Every controlled completion receipt names a
   governed record identity, the lowercase SHA-256 of the controlled artifact
   it summarizes, and the attesting party identity for that site. A
   self-computed digest with no attesting party is rejected.
2. **Distinct trust roots.** The discovery-site and replication-site
   attestations must come from different attesting identities. Two different
   opaque site ids signed by the same attesting party do not satisfy
   independent replication.
3. **Frozen artifact digests.** Frozen protocol, analysis, exposure, endpoint,
   and margin identities in a controlled lock must each carry the digest of the
   governed artifact they name, not only an opaque id. The held-out and
   replication estimand equivalence rules are unchanged: those identities must
   match within a lane.
4. **Site-2 blinding attestation.** The site-2 blinding evidence digest must be
   a distinct receipt from the analytic-transfer digest and must be attested by
   the replication site, not self-declared by the discovery side.
5. **Edit-event family grounding.** Discovery and replication event-family
   identities must name controlled edit-event records under the attesting
   sites' custody; borrowing identities across lanes, locks, or sites remains
   rejected.
6. **Validator self-binding.** A controlled promotion verdict records the
   validator schema id and implementation digest it was produced under, so a
   later reviewer can tell exactly which rules a promotion was checked
   against.
7. **Recorded independent review.** The validator refuses to certify any
   controlled promotion until its own review binding names the validator
   version and an independent-review receipt identity. The review receipt is a
   governed artifact; this public design does not specify its issuer.

## What the validator must never do

- Mint, infer, or upgrade evidence. It checks bindings only; it cannot create
  a positive completion, a rescue-gate pass, or a functional-hit state.
- Decide clinical action, dose, safety, efficacy, or benefit. Promotion remains
  a research-state label inside the ledger contract.
- Weaken any synthetic gate. Every synthetic-only rule stays exactly as tested;
  the controlled path is additive and more restrictive, never a relaxation.
- Write into the public tree, public receipts, or public release artifacts.
- Permit a controlled row in any public-only rendering.

## Decisions the implementation specification must resolve

This document is requirements, not an implementable spec. Before any code is
written, a separate implementation specification must settle, at minimum:

1. **Schema identity and module placement.** The controlled plan schema id,
   its top-level field set, and the module path of the validator. The id must
   be disjoint from `mva.track2-sample-stewardship/v*`.
2. **Controlled receipt field set.** Which fields carry the governed record
   identity, artifact digest, attesting party, validator schema id,
   implementation digest, and review-receipt identity, and whether the ledger
   gains a distinct controlled-promotion object or extends
   `sample_stewardship_promotion`.
3. **Private ranking and rendering path.** `canonical_candidate_ranking_bytes`
   has no `public_only` mode and emits candidate ids. A controlled ledger must
   never pass through the public-only ranking path; the spec must define a
   private-only rendering and a private staging command analogous to
   `render_candidate_release_bundle.py`, plus how controlled bundles interact
   with the release-manifest pipeline (they must never occupy a public release
   role).
4. **Attestation trust model.** How attesting-party identities are grounded —
   an issuer registry, key custody, rotation — so two colluding self-minted
   strings cannot impersonate independent sites.
5. **Freshness and revocation.** Attestation lifetimes, re-attestation after a
   protocol amendment, and interaction between governed artifact versioning
   and stale-digest rejection.
6. **Review receipt format.** The schema, issuer class, and private storage
   location of the independent-review receipt that unblocks first use.
7. **Controlled staging privacy rules.** How the existing identifier scanner,
   unsafe-path, and size limits treat private controlled staging directories;
   the scanner must not ingest controlled payloads, and controlled paths must
   stay outside this tree.
8. **Regression fixtures.** Concrete adversarial payloads: controlled plan
   bound to a synthetic row, synthetic plan bound to a controlled row, shared
   trust roots, reused event families, missing or stale attestations, unbound
   and missing plans, and a promoted controlled row rejected by every
   public-only path.

## Acceptance criteria before first use

- A regression suite mirroring the synthetic suite exists: forged or missing
  attestations, shared trust roots, reused identities, stale digests,
  cross-lane borrowing, synthetic-as-controlled and controlled-as-synthetic
  confusion, and unbound or missing plans all fail closed.
- The existing synthetic suite passes unchanged; the gated6 canonical ledger
  and ranking hashes are byte-identical before and after.
- An independent reviewer has inspected the implementation against this
  document, and the review receipt is bound as described above.

No reproduction command exists for this document because the validator is not
implemented. Until the open decisions are specified, the criteria are met, and
an independent review is bound, every ledger row stays `not_tested`,
`active_lead_id` stays null, and the HOLD stands.
