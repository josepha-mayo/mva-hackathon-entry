# Track 2 pre-exposure randomization and exact-inference contract

Status: living identifier-free method contract. It is not a submission, a result from a person, or evidence of biological rescue, efficacy, safety, diagnosis, treatment, or cure.

## Decision

The contract distinguishes four units. Treatment is applied to a `functional_execution_well`; randomization and analysis operate on a biological pair; biological replication is at the clone/edit-event level. A biological pair contains two reserved functional executions from the same edit event, clone, run, batch, plate, block, **exact plate row**, and coarse plate-position strata. Exactly one member is assigned treatment and the other vehicle. The pair is therefore the randomization and analysis unit, not the sole biological replication unit.

The minimum design is **six biological pairs in every exact plate x batch x run x edit-event context**. Four pairs are no longer permitted. With four pairs, a full bivariate-quadratic order adjustment leaves most otherwise balanced allocations with zero treatment information; keeping only the informative states leaves too few assignments for the exact alpha gate. Five pairs cannot meet the signed within-pair balance rule. Six is the first usable size under this contract.

Allocation is generated only after an arm-blind manifest and both assay and analysis plans are locked and a separate pre-reveal input-commitment record exists. The v4 input digest includes the algorithm and generator versions, canonical support ordering, selection rule, canonical manifest, and enumerated admissible-support count and digest, so the complete mapping is fixed before the seed is committed or used. The experiment-specific v3 seed commitment binds that input digest. The realized vector must replay byte-for-byte from the revealed seed and the committed inputs.

## Why this exists

Plate position, treatment order, and acquisition order can create a treatment-looking signal even when treatment has no effect. ARRIVE 2.0 asks investigators to identify the experimental unit, explain sample size, report the randomization sequence method, and describe how order and location confounders were controlled ([Percie du Sert et al., 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7610696/)). Microtiter-plate position effects are empirically large enough that block randomization has reduced assay bias in published work ([Roselle et al., 2016](https://pubmed.ncbi.nlm.nih.gov/27116421/)).

This software therefore rejects a `randomized: true` declaration as evidence. It requires a replayable allocation object and later requires the result rows to reproduce its exact realized tuple.

## Locked chronology

The required order is:

1. Reserve every functional execution and record its arm-blind manifest row.
2. Lock the assay-power and analysis plans, including endpoints, nuisance basis, assignment model, alpha, and decision rule.
3. Enumerate the information-filtered admissible support.
4. Compute the v4 canonical input digest over the study id, assay-plan digest, analysis-plan digest, treatment-application unit, assignment method and algorithm, generator version, canonical support ordering, selection rule, full canonical arm-blind manifest, and admissible-support count and digest.
5. Write a separate `assignment_input_commitment_record` containing its mechanism, unique record id, timestamp, and the v4 input digest.
6. Draw one 256-bit seed under the predeclared uniform model and write a separate `seed_commitment_record`. Its v3 digest is experiment-specific because it commits to both the seed and the v4 input digest.
7. Reveal the seed and interpret its 32 raw bytes as an unsigned big-endian integer. Apply the precommitted modulo-bias rejection boundary. If accepted, use its residue as the zero-based index into the canonical support; if rejected, HOLD without an implicit redraw.
8. Write the selected-vector randomization record, then the full allocation-plan commitment, all before the earliest exposure.
9. Preserve the realized allocation tuple in every lineage row.
10. After outcomes exist, validate plan-versus-realization equality and run the frozen inference.

The verifier enforces this UTC ordering exactly:

`locked_at <= input_recorded_at < seed_committed_at == seed_recorded_at < seed_revealed_at <= randomization_recorded_at <= plan_recorded_at < earliest_exposure`

The input, seed, randomization, and final-plan records must have four distinct record ids. The independently recorded input and seed receipt objects both have exactly `{mechanism, record_id, recorded_at, digest_sha256}`. Their declared mechanisms may be an append-only registry, signed timestamp, or version-control commit. Software verifies the schema, digest equality, uniqueness, and chronology; it does not authenticate the external registry, signature, commit, or timestamp.

Any reversed or missing timestamp, digest mismatch, uncommitted manifest mutation, selected-vector mismatch, or realized-tuple mismatch fails closed.

## Arm-blind manifest

The manifest contains plate dimensions and paired units. Each member records only allocation-relevant identifiers and fixed covariates:

- opaque functional execution id
- edit event and clone ids
- culture batch and assay run ids
- allocation block and assay plate ids
- plate row and column
- dosing order
- acquisition order

Arm labels are forbidden in the manifest. The public identifier grammar also rejects obvious treatment, vehicle, control, and drug encodings. This is a syntactic safeguard only: software cannot prove that an opaque id does not covertly encode an arm.

## Hard balance constraints

Each retained candidate has:

- one treatment and one vehicle member per biological pair;
- exact equality of the per-arm plate-column distribution inside every exact context;
- exact same-row matching within every pair, plus balanced lower-column and outer-column orientations;
- balanced dosing-first and acquisition-first orientations;
- zero signed treatment-minus-vehicle difference for column, dosing order, and acquisition order; the row difference is structurally zero because pair members must share the exact row;
- no missing, duplicate, or out-of-manifest execution.

The constraints operate on fixed arm-blind covariates. They do not inspect outcomes.

## Allocation-information floor

Hard balance alone is insufficient. A candidate can satisfy margins while its treatment indicator lies inside the prespecified nuisance span, making an additive effect mathematically unidentifiable.

For every context candidate, the verifier forms the centered binary treatment indicator and residualizes it against the same frozen context nuisance basis used for the outcome analysis. It retains the candidate only when:

`residual arm norm squared / raw centered arm norm squared >= 0.75`

This bounds nuisance-adjustment variance inflation at `4/3` and standard-error inflation at `sqrt(4/3)`. The exact binary64 arithmetic, declared lexicographic row order, two-pass modified Gram-Schmidt solver, rank tolerance, comparison tolerance, and `explicit_left_to_right_binary64_v1` summation algorithm are digest-bound in the analysis plan. Floating reductions are accumulated left to right in declared order; they are not reassociated or delegated to an unspecified parallel reduction.

Filtering happens after hard constraints but before the context Cartesian product and before seed-index selection. Because the rule depends only on the arm-blind manifest and a candidate label vector, not outcomes, the filtered support remains prespecified randomization support. The rule is symmetric under swapping treatment and vehicle labels.

The final joint support is the product of the context survivor counts. It must contain at least 64 and at most 1,000,000 distinct joint vectors. Enumeration is bounded before exponential work. Insufficient support, excessive support, a rank-deficient nuisance matrix, or a context with no surviving vector fails closed.

## Frozen nuisance basis

The outcome nuisance fit uses one row per functional execution and is fitted once per endpoint without the arm indicator, before enumerating assignments. It contains, separately for every lexicographically ordered context:

- a context intercept;
- within-context centered dosing order;
- squared within-context centered dosing order;
- within-context centered acquisition order;
- squared within-context centered acquisition order;
- centered dosing order times centered acquisition order.

The implementation uses an intercept plus `k - 1` context indicators and then five zero-outside-context order columns per context. This is exactly `6k` columns for `k` contexts. Coefficients are not shared across contexts.

The interaction term is required. Without it, a bivariate quadratic order surface can produce a favorable raw treatment contrast and a nominal sharp-null p-value below 0.05 even when outcomes are entirely arm-free.

## Seeded assignment and replay

Let `n` be the number of distinct candidate vectors after they are encoded as compact canonical JSON and sorted lexicographically. Interpret the raw 32 seed bytes as an unsigned big-endian integer `x`, and define:

`L = floor(2^256 / n) * n`

If `x >= L`, the single committed seed is in the incomplete modulo bucket and the verifier returns HOLD with `allocation_seed_rejected_for_modulo_bias`. This contract has no independently committed redraw blocks, so software must not synthesize or choose a replacement. If `x < L`, the selected zero-based support index is `x mod n`.

Conditional on acceptance of a genuine uniform 256-bit draw, every support index has exactly `floor(2^256 / n)` seed preimages. This is the source of equiprobability; no mathematical-uniformity claim is made from a hash or pseudorandom-function score, and there are no score ties or tie breakers.

The accepted input-commitment payload identifies itself as `mva-track2-allocation-input-commitment/v4`. It binds `paired_constrained_seed_index_rejection_v1`, `seed_uint256_rejection_index_v1`, compact-canonical-JSON lexicographic support ordering, the rejection-and-residue selection rule, and the support count and digest. The accepted seed commitment is:

`SHA256("mva-track2-seed-commitment/v3\0" || input_digest_ascii || "\0" || 32_seed_bytes)`

The one-argument v1 seed helper remains only for legacy fixture construction; the v3 allocation verifier accepts only the experiment-bound form above. The later randomization receipt repeats the seed commitment and its separate record, reveal, candidate-space count and digest, and selected-vector digest. The allocation record must contain exactly that selected vector.

The frozen entropy plan requires one seed sampled uniformly from all 256-bit keys, before outcomes, independently of the manifest and observed or potential outcomes, and committed before reveal and exposure. The analysis probability model is exact uniformity over the canonical information-filtered support conditional on acceptance at the declared uint256 rejection boundary. Software replay does not establish that this draw was genuine.

The present fixtures therefore declare entropy authenticity `not_attested`. A synthetic allocation may pass only as a conditional software control, and inference requires both `lineage.synthetic_only == true` and `exposure.privacy_class == "synthetic"`. Legacy lineage exports may omit `lineage.privacy_class`; when it is present, it must be a non-empty trimmed string, match `exposure.privacy_class` exactly, and agree with the synthetic meaning of `lineage.synthetic_only`. Any malformed or disagreeing declared classification fails closed. Any real classification requires authenticated randomization; a non-synthetic table with planned executions cannot pass with `not_attested` entropy and returns the provenance reason `allocation_entropy_not_attested_for_nonsynthetic_input`. `conditional_software_contract_verified` is kept separate from `authenticated_randomization_verified` so a replayable software path cannot be mistaken for authenticated randomization.

The private fixture relabel helper replays one caller-declared **fixed synthetic seed** and moves already synthetic arm-dependent payloads within complete pairs so the synthetic objects remain internally consistent after a plan-digest change. Repository callers use declared fixed synthetic constants. The helper checks the synthetic exposure schema and `privacy_class`, the synthetic lineage schema and `synthetic_only` flag, unattested entropy, a seed-commitment record, that replay-selected treatment ids belong to the assignment set, that lineage and assignment execution-id sets match, complete pairs, and support-record availability. It does not search seeds. Applying it to observed, controlled, or real data is prohibited and fails its executable synthetic guards. Searching candidate seeds for a favorable allocation or outcome is seed shopping and is prohibited even for documentation of a prospective real design.

A real run requires an actually verifiable entropy-attestation mode that is not implemented by the current contract. An independently witnessed uniform 256-bit draw could satisfy a future mode. Alternatively, a named future public randomness pulse could be converted to a uniform 256-bit key only under a precommitted, unbiased rejection-sampling, pulse-selection, fallback, and combining rule. NIST describes public beacon pulses as indexed, time-stamped, signed, and hash-chained ([NIST Interoperable Randomness Beacons](https://csrc.nist.gov/projects/interoperable-randomness-beacons/beacon-20)). Until such an attestation is implemented and verified, non-synthetic allocation remains HOLD.

## Exact inference

Inference re-enumerates the same public candidate support. It does not trust a recorded support count. The observed vector must be in that support and must replay from the committed seed.

Treatment is applied per functional-execution well. The biological pair is the randomization and analysis unit and all pairs receive equal analysis weight. Biological replication remains at the clone/edit-event level. Two generation endpoints are required:

1. event-positive divisions per detected division;
2. event-positive divisions per enrolled opportunity.

For each endpoint, the verifier:

1. rejects missing, non-finite, zero-denominator, inconsistent, imputed, or rank-deficient input;
2. fits the frozen arm-free nuisance model once;
3. residualizes the fixed observed outcomes;
4. computes the mean within-pair treatment-minus-vehicle residual difference for every admissible joint vector;
5. includes the observed assignment and all ties in the lower tail;
6. reports the one-sided p-value as `lower-tail count / support size` under the declared model that is uniform on the canonical support conditional on uint256 rejection acceptance.

The tested null is the **global Fisher sharp null**: for every functional execution, the treatment and vehicle potential outcomes are identical. The p-value is exact for that sharp null, conditional on acceptance of the genuine uniform uint256 draw, the declared rejection-and-index assignment model, frozen support, and causal assumptions. It is not an exact test of the weak null that the average treatment effect is zero. The reported mean within-pair treatment-minus-vehicle observed rate difference is a contrast, not a separately identified weak-null estimand.

Advancement requires both raw observed differences to be lower than zero and both sharp-null one-sided p-values to be at most 0.05. Failure of either endpoint stops advancement. Causal interpretation additionally requires: a genuine pre-outcome draw from the declared uniform model; consistency and a single version of each arm; no interference, carryover, or cross-well contamination; a fixed manifest with no post-assignment exclusion; and arm-blinded outcome ascertainment. These assumptions are explicitly `not_software_attested`. Regression adjustment in paired randomized experiments can improve precision while retaining a design-based interpretation when handled carefully ([Fogarty, 2018](https://academic.oup.com/biomet/article/105/4/994/5047363)); this implementation nevertheless claims only its narrower, explicitly enumerated conditional Fisher test.

## Synthetic six-pair design audit

The checked synthetic schedule uses acquisition pair ranks `(1, 0, 4, 3, 2, 5)` for dosing-pair ordinals `0..5`, with adjacent members. This schedule is committed as data, not silently inferred.

For one context:

- hard-balanced local vectors: `C(6,3) = 20`;
- raw centered arm-indicator norm squared: `12`;
- minimum residual information fraction across the 20 vectors: about `0.901`;
- vectors retained at the 0.75 floor: `20/20`.

Across three contexts, the exact support is `20^3 = 8,000`. Exhaustive synthetic checks found that, for a pure additive treatment effect under this fixed design, every permitted observed vector is the unique lower-tail minimum, giving `1/8,000 = 0.000125`. This is a software/design positive control, not a prospective power calculation and not biological evidence.

Adversarial negative controls include:

- arm-position separation;
- exact-column gradients;
- row-by-half interactions;
- event-specific order aliasing;
- context-specific dosing and acquisition U-shapes;
- context-specific dosing-by-acquisition quadratic interactions;
- post-commit manifest and assignment mutations;
- replay, digest, timing, and support tampering.

## What this contract cannot prove

It cannot prove:

- that the seed was unpredictable or honestly chosen;
- that the seed was genuinely sampled uniformly from all 256-bit keys before outcomes and independently of the manifest and potential outcomes;
- that timestamps came from an independent append-only system;
- that physical wells match declared wells;
- that dosing or acquisition happened in the declared order;
- chain of custody or sample identity;
- absence of unmeasured spatial, temporal, batch, operator, or instrument effects;
- that the quadratic nuisance surface is the true data-generating process;
- rescue, target engagement, safety, efficacy, clinical benefit, or a cure.

The outcome is still conditional on the declared manifest, retained support, endpoint definitions, and successful physical execution. Independent replication and orthogonal biological confirmation remain necessary.

## Freeze checklist

Before a real allocation:

- verify every arm-blind manifest row against the lab reservation sheet;
- verify six or more pairs in every exact context;
- verify the assay and analysis digests;
- run bounded support enumeration and record the support digest;
- verify every retained candidate meets the 0.75 information floor;
- verify joint support is between 64 and 1,000,000;
- record the v4 input commitment, including algorithm, generator, ordering, selection rule, support count, and support digest, before the seed commitment;
- precommit a genuine uniform 256-bit entropy source and its independence requirements;
- record the experiment-bound v3 seed commitment in a distinct independently witnessed record;
- have a second person authenticate all four distinct pre-exposure records and their chronology;
- reveal the seed only after those checks; verify it is below the committed rejection boundary, then replay and print the indexed allocation, or HOLD without redraw if it is rejected;
- preserve deviations rather than silently editing the committed plan.

The current software has no verifiable real-run entropy-attestation mode, so this checklist does not convert the present non-synthetic HOLD into GO.

No upload, publication, or clinical action is authorized by this contract.
