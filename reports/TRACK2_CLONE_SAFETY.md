# Track 2 clone-safety contract

Status: synthetic software contract only. This document names no subject-specific gene, allele, or medicine.

A lower bulk error fraction is not rescue if treatment selectively preserves event-positive daughters or harms event-negative daughters. This observed-label contract sits beside the lineage analyzer. It does not replace the frozen v3 aggregate receipt and does not claim biological validation.

## What it does

- Reads a locked, blinded lineage-count export. Unlocked or unblinded tables cannot pass or stop.
- Nests vehicle versus treatment under edit event, clone, and run. Counts are not pooled across clones.
- Requires at least eight followed daughters in **each arm and each observed label stratum**: vehicle event-positive, treatment event-positive, vehicle event-negative, and treatment event-negative. Sparse or zero-boundary cases that cannot support a configured comparison block advancement as `not_assessable`.
- When division counts are present, requires **complete event-positive daughter follow-up in both arms**: followed event-positive daughters must reach the declared daughter slots — two per division by default, or the declared multipolar count when `event_positive_daughter_slots` is present (`incomplete_positive_followup` otherwise). Reporting only the non-reproducing error daughters while leaving the rest unaccounted is exactly how a treatment-arm fitness gain could hide, and over-selecting reproduced vehicle error daughters could inflate the baseline the ratio is judged against. A multipolar division therefore widens the follow-up obligation rather than silently dropping its extra error-line daughters.
- Requires the event-negative strata to be followed with **symmetric depth between arms**: neither arm's negative follow-up share may drop materially below the other's (`asymmetric_negative_followup` otherwise). Under-following treatment non-error daughters hides death or arrest behind sparse counts; under-following vehicle's skews the positive-vs-negative baseline the relative reproduction ratio is judged against — either direction can mask a treatment-arm fitness gain.
- Applies three configured stop rules:
  1. The higher treatment-to-vehicle event-positive daughter reproduction rate exceeds `1.25`, or the vehicle rate is zero while the treatment rate is positive.
  2. The treatment-to-vehicle change in event-positive reproduction relative to event-negative reproduction exceeds `1.25`, or treatment has positive event-positive reproduction but zero event-negative reproduction at an otherwise assessable boundary.
  3. The treatment-to-vehicle event-negative daughter death-rate ratio exceeds `2.0`, or vehicle has zero event-negative daughter death while treatment has any.
- Requires the two ratio thresholds to be finite numeric values strictly greater than one and the follow-up floor to be a positive integer. A ratio exactly equal to a configured threshold is a stop: the boundary fails closed rather than passing on a rounding edge.
- Validates reproduced-plus-died does not exceed followed, and, when division counts are present, followed daughters do not exceed the declared daughter slots for either observed label. Declared slots are bounded to [two, four] per division in that stratum, and event-negative (clean) divisions can never declare more than two.
- Lets a detected stop beat an insufficient comparison elsewhere, while still refusing to issue a stop from an unlocked or unblinded table.

A pass is required before a site can advance. `not_assessable` is not a pass. A stop also requires locked, blinded counts.

## What it refuses to do

- Treat fitter abnormal daughters as efficacy.
- Average a bad clone into a good one.
- Convert sparse follow-up into a quiet green light.
- Treat observed event labels as true genotype. Label misclassification is not corrected by this gate.
- Treat the eight-daughter floor or fixed ratios as a power calculation, confidence interval, safety margin, or clinically validated threshold.

The floor and ratios are conservative software heuristics for refusing a false advance. A pass means only that these configured observed-label patterns were not detected in the supplied locked, blinded table. It is not evidence of adequate statistical power, biological rescue, treatment safety, or efficacy.

## How to run

```powershell
python -m unittest tests.test_clone_safety -v
python scripts/export_lineage_counts.py --fixture clean_generation --output local_dev/track2-lineage-counts.json
python scripts/assess_clone_safety.py --input local_dev/track2-lineage-counts.json --output local_dev/track2-clone-safety.json
```

Write receipts to a new path. Do not overwrite `reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json`.

## Claim boundary

Observed-label clone-safety software contract only. A higher treatment-to-vehicle event-positive daughter reproduction rate, disproportionate event-positive versus event-negative reproduction, or event-negative daughter death above the configured ratio is a stop, not a rescue. Observed labels can be misclassified and do not establish true genotype, mechanism, treatment safety, efficacy, or clinical benefit.
