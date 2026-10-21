# Isolated missense-correction contract candidate

This is an additive, standalone software-contract milestone. It is not an
implemented replacement for the legacy hypomorph gate, a biological result,
a signed release, or a clinical claim. Every sample is invented synthetic data.

## Execute

From the repository root, using Python 3.12 or later:

```sh
python scripts/assess_correction_control.py \
  --plan examples/correction_control/plan.synthetic.json \
  --evidence examples/correction_control/evidence.synthetic.json
python -m unittest tests.test_correction_control -v
```

The command prints a machine-readable receipt to stdout. Exit 0 means the
narrow declared contract is satisfied; exit 1 means a contrast did not meet
its frozen margin; exit 2 means invalid/missing metadata. All outputs say
`assessment_scope: correction_control_only` and `legacy_pipeline_eligible: false`.
No output is signed, deployed, submitted or incorporated into published files.

## Version and compatibility boundary

Existing `mva.community-allele-function-scorecard/v1` and program-gate APIs,
fixtures and receipts are unchanged. They remain legacy with respect to this
new genotype-aware contract, not retrospectively verified or invalidated.
New entry requires `mva.missense-correction-plan/v2` and
`mva.missense-correction-evidence/v2`; missing genotype fields fail closed.
The new result has its own `mva.missense-correction-control/v2` schema, not a
legacy hypomorph receipt schema. No existing save, replication, hypothesis,
release or attestation route consumes it. End-to-end genotype-aware routing
is still unimplemented. A satisfied standalone contract must not be passed
as full hypomorph, replication or drug eligibility.

## Exact boundary enforced

Only N1002K-only correction of the declared trans L737Ter/N1002K compound
state is accepted. Its resulting and independently generated comparator
states must both be L737Ter/WT. Stop-only correction to WT/N1002K and double
correction to WT/WT require separate future contracts, not aliases here.
Genotype arrays use ordered canonical transcript-level allele labels shown
in the samples. The phase vocabulary declares the retained allele placement;
it does not authenticate a molecular phasing assay.

The plan freezes comparator/specimen identities, genotype-evidence references,
background, assay protocol, analysis method, confidence level, units, endpoint
direction, carrier-equivalence bounds and a restoration margin of at least
one half. Distinct corrected/comparator specimen and derivation-event IDs
are required. All five fixed endpoints must occur exactly once. Evidence
must match the frozen plan and its digest, with a later outcome-unblinding
time. Bounds must be finite, ordered, in matching units, and numeric, not
booleans. Frozen equivalence bounds straddle zero.

Each endpoint has a frozen role. Abundance and half-life must be
`defect_reversal`; function axes may instead be `preservation_equivalence`
when already normal. No post-hoc omission or role change is allowed.
The fixed raw abundance and half-life endpoints require higher-is-better;
first-division error requires lower-is-better. Inverse transforms require
future distinct typed endpoint definitions, not flipped labels here.
Localization and checkpoint direction requires assay-specific interpretation
frozen in the analysis method: checkpoint duration is not inherently monotonic
and prolonged arrest cannot automatically be called better function.
For each defect-reversal endpoint an external prespecified analysis supplies
three contrast intervals and mutant, carrier and corrected means:

- Oriented mutant-to-carrier gap: sign × (carrier − mutant), with sign +1 for
  higher-is-better and −1 for lower-is-better. Its entire CI must be positive.
- Corrected minus carrier: the entire CI must lie within equivalence bounds.
- Restored fraction: sign × (corrected − mutant) / oriented gap. Its lower CI
  bound must meet the frozen minimum restoration margin.

For preservation-equivalence axes, the mutant-minus-carrier baseline CI
must be fully contained in separately frozen baseline-equivalence bounds,
and the corrected-minus-carrier CI must meet the usual carrier-equivalence
bounds. There is no division by a zero gap or required rescue of a nonexistent
defect. All five endpoints remain mandatory.

The corresponding mean contrasts must fall inside the submitted intervals.
The implementation does not derive ratio CIs from independent marginal CIs
or pretend to resolve covariance. Supplied analysis metadata and contrast
intervals require independent statistical review, event-level replication,
scientific margin justification, multiplicity handling, and source audit.
WT/WT is not the comparator; a carrier can be below the WT ceiling and still
satisfy this narrow contract. No tRNA workflow or arimoclomol exposure,
transcript/dependence, generation-selection, completion, or safety gates are
changed or bypassed.

## Attestation limits

Plan/evidence semantic hashes and result self-digest bind every submitted
numeric field and metadata field. Hashes, timestamps, distinct identifiers,
and evidence-reference strings do NOT establish authentic preregistration,
actual independence, genotype, wet-cellular/endogenous assay qualification,
or the truth of supplied measurements. A caller could fabricate all of them.
Authenticating freeze records, genotype evidence and raw statistical analysis
is outside this candidate. The receipt explicitly carries that limitation.
