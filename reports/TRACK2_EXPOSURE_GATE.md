# Track 2 exposure-gate contract v2

Status: synthetic software contract only. This document names no subject-specific gene, allele, or medicine.

A label, plasma total, or nominal bath micromolar value is a recipe, not cell exposure. Zero measured intracellular parent is also not cell exposure. This contract sits beside the candidate ledger. It does not replace the frozen attempt-1 report and does not claim pharmacokinetics in a person.

## What it does

- Reads the measured-exposure community table.
- Requires unbound medium and intracellular parent on a row, both greater than zero, before that row can count.
- Requires a finite, positive `time_hours` and a declared contact pattern on every row used to advance; a `constant` row must also meet the 1-hour minimum window, since a shorter declared window is a measurement at the instant dosing began, not a bounded culture window. A pulse additionally requires an explicit successful washout; continuous contact does not require a row-level washout value.
- Lets a program pass only when at least one complete row sits at or below 2 micromolar.
- Treats `constant` as continuous contact with compound-containing medium, not proof that free or intracellular concentration stayed constant.
- Treats the current single-point `pulse` row as supportive only. A pulse/washout schedule needs a concentration-time series and recovery sampling that this v1 table cannot represent before it can be an advancing window by itself.
- Labels 5 micromolar complete rows as exploratory. Exploratory-only tables cannot advance.
- Stops if any nominal or measured value is 50 micromolar or higher.
- Treats a measured zero inside the cell as not assessable, not as a conservative-window pass.

## What it refuses to do

- Treat serum total as intracellular exposure.
- Advance on a nominal-only recipe.
- Advance on a missing, zero, non-finite, or unspecified duration.
- Treat one concentration measurement during a pulse as a post-washout exposure profile.
- Convert an exploratory high concentration into the conservative window.

## Pulse evidence needed for a later schema

A future pulse-capable table should separate pulse duration, recovery duration, endpoint time, wash/removal procedure, matched sham wash, and measured unbound-medium and intracellular-parent timepoints. Until that series exists, `pulse` documents an experimental arm but cannot be the only row that advances the exposure gate.

In the stop-early suite, an underdescribed exposure is the **earliest non-pass** and saves the exposure object. If a downstream hypothesis record nevertheless labels the probe observed, that overclaim becomes the terminal stop. Receipts report both fields; “first-blocked at exposure” must not be rewritten as “the exposure gate was the terminal stop.”

The timing requirement is methodologically motivated, not a claimed clinical threshold. OECD guidance for describing non-guideline in-vitro methods calls for the exposure regime to specify dosage, exposure time, and observation frequency ([OECD Guidance Document 211](https://one.oecd.org/document/ENV/JM/MONO%282014%2935/en/pdf)). The in-vitro micronucleus guideline treats short treatment followed by removal and continuous treatment through sampling as distinct schedules tied to cell division ([OECD Test Guideline 487](https://www.oecd.org/en/publications/test-no-487-in-vitro-mammalian-cell-micronucleus-test_9789264264861-en.html)). Growth-response measurements can also vary with assay duration and the number of cell divisions independently of underlying drug biology ([Hafner et al., 2016](https://doi.org/10.1038/nmeth.3853)). These sources justify recording and separating schedules; they do not validate this software as OECD-compliant or establish an exposure for a person.

## Clone-selection agent carryover

Clone-selection antibiotics are a direct confound in a suppression assay: aminoglycosides (G418/neomycin class) are canonical nonsense-readthrough agents and can themselves induce the phenotype a rescue claim would attribute to the probe. Every measured row therefore declares a `selection_agent` from a closed vocabulary (`none`, `aminoglycoside`, `non_aminoglycoside`); a missing declaration is `unlabeled` and cannot qualify.

- A row's clearance claim is honored only as `selection_agent_cleared: true` **with** a declared `selection_clearance_method` (`serial_passage_without_agent` or `documented_media_exchange`). A bare checkbox is the same class of unverifiable evidence this contract rejects for randomization; cleared-without-method is reported as `selection_clearance_method_unverified` and treated as uncleared.
- An uncleared aminoglycoside row is classified `aminoglycoside_carryover`; an uncleared non-aminoglycoside row is `not_assessable` (`selection_agent_carryover`). Either can hold the table even when a sibling row qualifies.
- Selection history is a property of the culture, not of a row. All rows sharing a `culture_batch_id` must agree on the agent and (among rows that claim clearance) the method; conflicting declarations make the batch history unreliable (`selection_agent_inconsistent_within_batch`). A batch is cleared only when every member row agrees it was cleared with a declared method — one uncleared or unverified sibling voids the clearance claim on the whole batch.
- The declared agent, cleared flag, and method are bound into the exposure-execution fingerprint, so editing a clearance claim after the fact changes the record's identity and fails binding instead of silently upgrading a row.

## Pre-exposure allocation

When an exposure or vehicle-control record supports planned functional executions, the exposure gate also evaluates a strict allocation record before exposure begins.

- The v3 allocation plan binds the study id, assay- and analysis-plan digests, assignment method and algorithm, treatment-application unit, and complete arm-blind manifest. Its separate input-commitment record binds a v4 digest that also includes the exact canonical support ordering, support count and digest, rejection generator, and selection rule. A second separate record holds the experiment-bound v3 seed commitment. An accepted raw 256-bit draw indexes that support directly; the incomplete modulo bucket is rejected without synthesized redraw. A `randomization=true` checkbox is not accepted as evidence.
- Chronology is fail-closed: `locked_at <= input_recorded_at < seed_committed_at == seed_recorded_at < seed_revealed_at <= randomization_recorded_at <= plan_recorded_at < earliest_exposure`. The input, seed, randomization, and final-plan record ids must all differ. Software validates declared record metadata, digests, and time order but does not authenticate the external recorder.
- Every planned functional execution must appear exactly once with a unique physical well, dosing order, and acquisition order. Declared deviations hold rather than being silently treated as balanced.
- Treatment is applied to a functional-execution well. Randomization and analysis operate on biological pairs, while biological replication is at the clone/edit-event level. A pair is one vehicle and one treatment execution for the same edit event, clone, and functional assay run. The two executions must share the declared allocation block, plate, culture batch, run, **exact row**, edge/interior stratum, column parity, and column half.
- Within every **plate x batch x run x event** context, at least six biological pairs are required. The exact per-arm plate-column distributions must be identical; matching only edge/interior, parity, half, or marginal counts is insufficient. Signed column, dosing-order, acquisition-order, and plate-center orientation checks prevent a consistent arm direction from hiding inside apparently balanced margins.
- The arm-blind candidate support is filtered before the input and seed commitments so every retained context vector preserves at least 75% of its centered arm-indicator information after the frozen context-specific dosing/acquisition linear, squared, and cross-product nuisance adjustment. The exact joint support must contain 64 to 1,000,000 vectors. Both the allocation filter and later OLS inference bind `explicit_left_to_right_binary64_v1` reductions in declared row order.
- The entropy plan requires a genuine pre-outcome seed drawn uniformly from all 256-bit keys, independently of the manifest and observed or potential outcomes. Current records are `not_attested`: synthetic fixtures can pass only as conditional software controls, while any non-synthetic planned allocation returns a provenance HOLD until a verifiable attestation mode exists.
- At count identity, the selected vector is verified against the experiment-bound seed replay. Both generation endpoints must have a favorable raw direction and an equal-pair-weighted one-sided randomization p-value at or below 0.05. Exactness is for the global Fisher sharp null of no effect on any execution, conditional on the declared uniform assignment model and frozen support; it is not exact for a weak zero-average-effect null. Full details and limitations are in `reports/TRACK2_RANDOMIZATION_CONTRACT.md`.
- Each joint allocation block must remain in one plate/batch/run context, contain balanced even-sized arm sets, and preserve paired dosing and acquisition tranches.

The pre-exposure result can detect a declared confounded plan while culture remains unspent. It proves only internal consistency of declared metadata and digest binding. The causal assumptions—a genuine uniform pre-outcome draw, consistency/single arm versions, no interference/carryover/cross-well contamination, no post-assignment exclusion from the fixed manifest, and arm-blinded outcome ascertainment—remain `not_software_attested`. The result does not prove external timestamp authenticity, physical well placement, actual dosing, acquisition adherence, random generation of assignments, or biological efficacy.

The private save-path relabel helper is executable only for a synthetic exposure table paired with `synthetic_only` lineage and `not_attested` entropy. It replays one declared fixed synthetic seed and moves already synthetic arm-dependent payloads within complete pairs; it does not search seeds. It must never reseal observed, controlled, or real data. Seed shopping is prohibited.

## Exposure-to-assay execution binding

Passing the exposure gate is not enough to support a favorable functional table. The measured-exposure object and the lineage-count object are separate files, so the count-identity gate now checks that every treatment aggregate resolves to exactly one eligible measured profile through an explicit execution-support relation.

- A profile id is recomputed from a canonical semantic payload: probe, nominal, unbound-medium and intracellular values, duration, contact pattern, washout, and measurement class. It is not trusted merely because two files copied the same digest. The same semantic profile id may legitimately recur in distinct measurement executions or culture batches.
- Every measured row carries a canonical semantic profile id and unique measurement-execution id. A row cannot avoid the support audit by dropping its profile id. It also carries the functional executions it supports, functional assay runs, culture batch, sample relation, and actual exposure and sampling times. A matched parallel culture is allowed; a shared physical plate is not required.
- The timestamped founder records carry functional execution, an exposure-support record anchor, profile, probe, run, batch, and exposure start. The aggregate exporter preserves that founder-derived context and refuses to pool multiple contexts into one row.
- When allocation is declared, the same founder records carry the realized allocation block, functional assay plate, row, column, dosing order, and acquisition order, while the study carries the canonical allocation id. Those fields are all-or-none, remain in the canonical lineage fingerprint, and must match the committed assignment exactly at count identity.
- Every treatment row must resolve exactly once, every declared functional support and assay-run id must be used by that measurement or control record, and functional execution ids are globally unique across every aggregate row and arm, including unpaired vehicle rows. An unlinked exposure row cannot declare a functional assay run or sample relation. Measurement and vehicle-control record ids also use disjoint namespaces. A valid but unrelated exposure row, a stale profile digest, an unanchored measurement execution, an exploratory or pulse-only row, a mismatched run or batch, or impossible timing holds the whole table.
- One unstratified treatment analysis must use one semantic exposure profile. Repeated executions of that profile across distinct batches are allowed; pooling different profiles or doses is not.
- The paired vehicle row must resolve to an explicit vehicle-control record, keep its own distinct execution, profile, and probe/control identity, and share the declared assay run, culture batch, exposure start, and endpoint time.
- The assay plan and exposure table must agree on an explicit endpoint class and success rule. Assay power still decides whether the endpoint itself is acceptable.
- Plate and probe-lot ids are optional fingerprint metadata. Their absence alone cannot block a legitimate matched-parallel-culture design.

This check runs at `count_identity`, with eight culture units remaining in the synthetic cost model, because realized functional rows are needed. Moving it into the earlier exposure gate would incorrectly claim that downstream file collage was detected before the culture was run. Missing links, mixed profiles, duplicate or unused mappings, vehicle-control mismatches, and timing mismatches are variants of one provenance family, `provenance.exposure_assay_execution`.

This reconstruction-ready linkage is motivated by [OECD GIVIMP, Second Edition (2025)](https://www.oecd.org/en/publications/guidance-document-on-good-in-vitro-method-practices-givimp-second-edition_5ba6777b-en.html), while the [provenance data model recommendation](https://www.w3.org/TR/prov-dm/) supplies the generic entity/activity relationship and [FAIR principles](https://doi.org/10.1038/sdata.2016.18) support persistent identifiers and detailed provenance. These sources motivate traceable records. Software checks only that declared metadata are internally consistent; it does not prove physical sample identity, actual dosing, target engagement, efficacy, regulatory compliance, or benefit to a person.

## How to run

```powershell
python -m unittest tests.test_exposure_gate -v
python -m unittest tests.test_arm_allocation tests.test_lineage -v
python scripts/assess_exposure_gate.py --input templates/community/measured_exposure_table.synthetic.json
python scripts/assess_program_gates.py --count-identity templates/community/lineage_count_table.synthetic.json --blinded templates/community/blinded_count_table.synthetic.json --measured-exposure templates/community/measured_exposure_table.synthetic.json --assay-plan templates/community/assay_power.synthetic.json
```

## Claim boundary

Exposure and declared-allocation software contracts only. Nominal bath concentration is not cell exposure. Contact pattern does not establish constant free concentration. Allocation metadata and successful replay do not authenticate entropy, physical placement, dosing, acquisition, or randomization. Sharp-null software inference is not a weak-null treatment-effect estimate. This is not a human dose and not efficacy evidence.
