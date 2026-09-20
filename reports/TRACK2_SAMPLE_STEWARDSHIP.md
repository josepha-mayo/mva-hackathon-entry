# Track 2 scarce-material and transfer contract

Status: synthetic, identifier-free method contract, schema `mva.track2-sample-stewardship/v17`. It contains no participant inventory and does not authorize sample use, treatment, freeze, upload, or submission.

## Why this exists

Residual participant-derived cells are irrecoverable. A dependency-order chooser can prevent skip-ahead errors, but it is not a numerical value-of-information model and it does not prove that an experiment is the best use of scarce material. This contract therefore uses a vector budget and a within-stage, within-partition, within-lane, same-decision dominance rule without inventing priors, utilities, prices, timelines, or cell counts.

The private laboratory record must keep separate, controlled inventories for DNA aliquots, RNA aliquots, viable-cell equivalents, remaining population doublings, and independent edit-event families. The public template contains synthetic values and `syn-` identifiers only.

## Two lane-specific paths

The targeted-hypothesis and correction-trained-phenotypic lanes never share an ambiguous OR prerequisite. The runtime requires each arrow below to be represented by a direct, lane-matched predecessor, so a later node cannot satisfy the graph with a remote ancestor while skipping the intervening role:

`lane-specific A0` → `lane-specific A1` → `lane-specific Tier-B context qualification` → `lane-specific Tier-B native lineage` → `lane-specific held-out confirmation` → `lane-specific replication`

- **A0, renewable nonparticipant discovery:** optimize exposure, target engagement, toxicity, assay performance, and correction-trained screening. A0 may reject a condition or mechanism. It cannot create a participant-branch `no_hit` or jump to replication. Both lanes must already carry a locked correction-defined function, same-background exact correction rescue, reciprocal recreation, measured exposure, valid controls, and a genotype-harm counterscreen before a positive result may open A1. Those axes are bound as opaque evidence identities in an A0 `correction_core` object and into the assay-contract digest, so listing the requirement names is not enough and the two lanes cannot share one identity. The phenotypic lane additionally requires correction-signature separation, including its own evidence identity, so a screen cannot be unblinded against an unlocked core. Those A0 locks stay on renewable material; they do not mint participant context.
- **A1, minimal participant bridge:** each lane has its own bridge and positive A0 ancestor. Use the smallest governed exact-genotype/corrected-sibling panel that can test measured exposure, valid controls, one locked correction-qualified function, and short-term viability/completion. Listing those requirement names is not enough: every A1 must bind unique opaque identities for those axes in an `a1_lock`. Those identities cannot be reused across the plan or borrowed from a renewable A0 core, context object, native-lineage lock, held-out lock, replication freeze lock, or replication site identity. Changing a lock identity invalidates the completion-receipt digest. A non-A1 assay cannot carry this lock. The no-hit basis also requires `short_term_viability_completion`, so a negative without viability/completion cannot close the participant branch. An A1 node is illegal unless a same-lane native-lineage successor exists. Eligibility then reserves the remaining participant-discovery vector for that A1 plus its incomplete context and lineage descendants, so two ready bridges cannot both spend when that would strand lineage. A completed A1, including a valid no-hit, does not open the other bridge unless remaining inventory can still pay for a lineage-complete path.
- **Tier-B context qualification:** before native-lineage promotion, the contract requires opaque evidence identities for a predeclared postnatal lineage rationale, nontransformed proliferative context, paired 2-D comparison, same-context exact-correction rescue, and same-context reciprocal recreation. Those identities must be unique within the assay, unique across assays, and disjoint from A0 correction-core identities. The mitotic context class is lineage-matched: epithelial claims additionally require architecture-preserving evidence; lineage-intrinsic mitotic claims require that class instead of a fake organoid. Immortalized, reprogrammed, or unknown cultures cannot qualify. The public identifiers point only to synthetic examples; governed evidence stays private.
- **Tier-B native-lineage confirmation:** only a positive context receipt opens the larger allocation needed for native first-division `gC`/`gE`, completion, clone safety, and functional-hit classification. Listing those requirement names is not enough: every native-lineage assay must bind unique opaque identities for native fidelity, completion equivalence, and clone safety in a `lineage_lock`. Those identities cannot be reused across the plan or borrowed from an A0 core, context object, held-out lock, replication freeze lock, or replication site identity. Changing a lock identity invalidates the completion-receipt digest. A context-qualification assay cannot carry this lock.
- **Held-out confirmation:** uses a partition that discovery cannot consume. Every held-out assay must declare frozen exposure, frozen endpoint, frozen margin, and blinded execution, and bind unique opaque identities for those axes in a `held_out_lock`. Blinded-execution identities cannot be reused across the plan or borrowed from an A0 core or context-qualification object. Frozen-exposure, frozen-endpoint, and frozen-margin identities must be the same objects later bound by that lane's replication lock; they still cannot be borrowed from an A0 core, later lock, or the other discovery lane. Changing a lock identity invalidates the completion-receipt digest. Listing the requirement names is not enough.
- **Independent replication:** uses a second reserved partition and requires both analytic transfer and biological independence. Listing independence names is not enough: every replication assay must bind freeze and transfer-QC identities in a `replication_lock`. Frozen-endpoint, frozen-margin, and frozen-exposure identities must match the same-lane held-out lock, so a second site cannot pass by measuring a different claim or a different dose. Other freeze and transfer-QC identities remain unique and cannot be borrowed from an A0 core, context-qualification object, or held-out lock. Changing a lock identity invalidates the completion-receipt digest. A positive replication receipt must also bind unique opaque discovery and replication site identities in `promotion_evidence`. Those two identities must differ, cannot be reused across lanes, and cannot be borrowed from an A0 core, context object, held-out lock, or replication freeze lock. The independence name `different_site` is not enough. The same receipt must bind unique opaque discovery and replication event-family identities; those IDs cannot be reused across lanes or borrowed from an A0 core, A1 bridge, context object, native-lineage lock, held-out lock, replication freeze lock, or site identity. The requirement name `nonoverlapping_edit_event_families` is not enough. Analytic transfer likewise cannot pass as a copied hash: the result fingerprint must be unique across the plan, cannot be reused across lanes, and cannot equal any frozen assay-contract digest in the plan. Site-2 blinding likewise cannot pass as the word blinded: each positive replication receipt must bind a unique opaque site-2 blinding identity, and that identity cannot be borrowed from an A0 core, lock, site, or event-family object.

## Immutable structured completion receipts

`completed` is not a map of free outcome strings. Every completion is a structured receipt containing:

- an opaque synthetic receipt id;
- the lowercase SHA-256 of the normalized assay contract;
- outcome and contract-derived action;
- the exact partition and resource-debit vector; and
- a digest over the receipt body.

The validator requires the debit to equal the assay contract, subtracts all completed debits cumulatively from each partition, rejects aggregate overdraw, and blocks otherwise eligible assays that no longer fit the remaining vector. Changing a completed assay, outcome, action, partition, debit, or receipt field invalidates its digest binding. These hashes detect drift and bind a static plan; they are not signatures and do not replace an append-only governed laboratory record.

## Context and replication evidence

A held-out completion receipt binds the three opaque freeze and blinding identities through the assay-contract digest. An A1 completion receipt binds five opaque bridge identities through the assay-contract digest. A context-qualification receipt binds the six opaque context-evidence identities through the assay-contract digest. A native-lineage assay binds three additional opaque fidelity, completion, and clone-safety identities in `lineage_lock`. A replication assay binds freeze and transfer-QC identities in `replication_lock`; frozen exposure, endpoint, and margin must be the same identities already bound by that lane's held-out lock. A positive replication receipt additionally binds:

- an analytic-transfer result fingerprint;
- an explicit `blinded` site-2 state plus a unique opaque site-2 blinding identity;
- nonempty, disjoint discovery and replication edit-event-family identities that cannot be reused across the plan or borrowed from A0, A1, context, lineage, held-out, freeze-lock, or site objects; and
- unique opaque discovery and replication site identities that differ from each other and from A0, context, held-out, and freeze-lock identities.

A different site is necessary but insufficient. The replication contract also freezes exposure, endpoint, margin, protocol, and analysis identities and requires common-reference transfer QC. Same-lane held-out and replication must share the exposure, endpoint, and margin identities; a second site cannot pass by measuring a different claim or a different dose. The analytic-transfer fingerprint is bound into the same uniqueness map as those identities; a copied SHA-256 or any assay-contract digest in the plan cannot satisfy transfer. Only both analytic and biological axes may support independent replication elsewhere in the candidate program.

## Selection rule

Every assay declares prerequisites, lane, stage, partition, conservative consumption, destructiveness, result-to-action branches, and the decisions it could change. Dominance is considered only between assays in the same stage, partition, discovery lane, and exact decision-change contract. Within that comparable set, an assay is removed only when another uses no more of every resource, is no more destructive, and is strictly better on at least one declared dimension.

The output is a set of non-dominated choices, not a scalar ranking. Laboratory feasibility and governance still determine the plan. Real material values, context rationale, and edit-event identities must remain controlled; only identifier-free aggregate method artifacts may be released.

## Reproduce the synthetic check

```powershell
python scripts/assess_sample_stewardship.py --plan templates/track2_sample_stewardship.synthetic.json
python -m unittest tests.test_sample_stewardship -v
```

Passing these checks validates declared bookkeeping only. It does not establish sample availability, a biological effect, clinical relevance, safety, dose, efficacy, or benefit to the child.
