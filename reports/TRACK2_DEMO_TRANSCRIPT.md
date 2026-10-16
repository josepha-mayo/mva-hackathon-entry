# Demo transcript — the contract refusing a rigged rescue, no install required

This file is the captured output of `python scripts/demo_contract.py` (≈90
seconds, standard library only, synthetic fixtures — no participant data). It
runs the production analyzer over 16 named scenarios × 120 replicates: one
genuine rescue it should certify, one honest null it should stay silent on, and
fourteen attacks that a naive "fewer errors per division" reading would score
as rescue. Every attack is refused with a named reason.

Reproduce byte-for-byte:

```bash
python scripts/demo_contract.py
```

```text
demo: 16 scenarios x 120 synthetic replicates — fixtures only, no data

[ 1/16] fewer_new_errors_strong
  scenario: a genuine rescue: fewer new errors per completed division
  rate-only reading would claim: rescue
  contract verdict: certified clean — the contract CAN pass (clean 51/120 = 42.5%; modal interpretation: generation_reduction_without_detected_configured_confound)

[ 2/16] no_change
  scenario: a true null: treatment does nothing
  rate-only reading would claim: nothing
  contract verdict: no clean signal — correct silence (clean 0/120 = 0.0%; modal interpretation: no_detectable_component)

[ 3/16] generic_cytostasis
  scenario: the treatment slows divisions overall; fewer divisions means fewer recorded errors without fixed segregation
  rate-only reading would claim: rescue
  contract verdict: refused — no clean generation signal (clean 0/120 = 0.0%; modal interpretation: mixed_components)
  triggered flags: cytostasis

[ 4/16] rescue_plus_moderate_cytostasis
  scenario: a real rescue, but riding on moderate cytostasis
  rate-only reading would claim: rescue
  contract verdict: refused — the confound blocks certification even when truth is real (clean 0/120 = 0.0%; modal interpretation: generation_signal_with_unresolved_competing_completion)

[ 5/16] masked_followup_rescue
  scenario: a real rescue where error-bearing daughters are followed up less often — selection masquerading as generation
  rate-only reading would claim: rescue
  contract verdict: refused — daughter-fate selection cannot certify (clean 0/120 = 0.0%; modal interpretation: mixed_components)

[ 6/16] error_daughter_pruning
  scenario: error-bearing daughters preferentially die
  rate-only reading would claim: rescue
  contract verdict: refused — differential death is a selection artifact (clean 0/120 = 0.0%; modal interpretation: mixed_components)
  triggered flags: error_daughter_pruning

[ 7/16] error_daughter_preservation
  scenario: error-bearing daughters preferentially survive
  rate-only reading would claim: harm visible as 'more errors'
  contract verdict: refused — flagged as preservation, not rescue (clean 0/120 = 0.0%; modal interpretation: mixed_components)
  triggered flags: error_daughter_preservation

[ 8/16] event_scoped_completion_drop_rescue
  scenario: a real rescue where one edit event's completion collapses — invisible to the pooled completion ratio
  rate-only reading would claim: rescue
  contract verdict: refused — per-event completion drops still count (clean 0/120 = 0.0%; modal interpretation: generation_signal_with_unresolved_competing_completion)

[ 9/16] completion_overshoot_rescue
  scenario: a real rescue that also hyper-completes divisions
  rate-only reading would claim: rescue
  contract verdict: refused — overshooting the completion band is not rescue either (clean 0/120 = 0.0%; modal interpretation: generation_signal_with_unresolved_competing_completion)

[10/16] completion_band_edge_rescue
  scenario: a real rescue pushed just past the completion-band edge
  rate-only reading would claim: rescue
  contract verdict: refused — the band edge is a boundary, not a loophole (clean 0/120 = 0.0%; modal interpretation: generation_signal_with_unresolved_competing_completion)

[11/16] generic_toxicity
  scenario: the treatment is generally toxic
  rate-only reading would claim: rescue
  contract verdict: refused — toxicity is flagged, not averaged away (clean 0/120 = 0.0%; modal interpretation: mixed_components)
  triggered flags: general_toxicity

[12/16] informative_followup_bias
  scenario: follow-up is preferentially skipped where errors occurred
  rate-only reading would claim: rescue
  contract verdict: refused — biased follow-up is a named flag (clean 0/120 = 0.0%; modal interpretation: measurement_invalid)
  triggered flags: informative_followup_bias

[13/16] division_detection_bias
  scenario: the instrument detects divisions differently by arm
  rate-only reading would claim: rescue
  contract verdict: refused — measurement bias across arms is caught (clean 0/120 = 0.0%; modal interpretation: measurement_invalid)
  triggered flags: division_detection_bias

[14/16] event_detection_bias
  scenario: the instrument detects error events differently by arm
  rate-only reading would claim: rescue
  contract verdict: refused — event-level detection bias is caught (clean 0/120 = 0.0%; modal interpretation: measurement_invalid)
  triggered flags: event_detection_bias

[15/16] event_specificity_bias
  scenario: the instrument calls false events differently by arm
  rate-only reading would claim: rescue
  contract verdict: refused — specificity bias is caught (clean 0/120 = 0.0%; modal interpretation: measurement_invalid)
  triggered flags: event_specificity_bias

[16/16] zero_division_arm
  scenario: a degenerate arm: no divisions observed at all
  rate-only reading would claim: undefined — nothing to compute
  contract verdict: refused — 1,000/1,000 no-decision, never a pass (clean 0/120 = 0.0%; modal interpretation: insufficient_information)

synthetic-only: these certify the analyzer's behavior on fixtures, not biology — full receipt: reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json
```

## How to read it

- **`fewer_new_errors_strong` certifies 42.5% of replicates** — certification
  requires the generation flag, completion equivalence, and selection
  equivalence simultaneously, so a true rescue is certified only when the data
  are strong enough to clear all three at once. Low certification power is the
  cost of refusing everything else; the benchmark receipt prices it openly
  (374/1,000 at 1,000 replicates) rather than hiding it.
- **Every "rate-only rescue" row is refused** — cytostasis, daughter pruning,
  masked follow-up, informative dropout, instrument bias, band-edge games —
  each fails with a named flag or a non-clean interpretation, not a silent
  miss.
- **`zero_division_arm` shows the failure direction**: when the contract has
  nothing to decide on, it says `insufficient_information` — never a pass.
- **`clean N/120` is certified-clean rate over 120 synthetic replicates**; the
  full 24-scenario × 1,000-replicate benchmark receipt is at
  `reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json` and is digest-bound in
  `release/release-artifacts.json`.

This transcript is bound in `release/track2-reproducibility.json` as
`demo_transcript`: its numbers are frozen claims, verified against the
authoritative receipts it cites — `reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json`
(24 scenarios × 1,000 replicates) is the bound benchmark of record.
