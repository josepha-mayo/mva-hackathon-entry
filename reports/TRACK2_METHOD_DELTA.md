# Track 2 method-delta comparison

Status: public software comparison only. This file names no subject-specific gene, allele, or medicine. It does not authorize an upload and does not raise a survival percentage.

Desktop software cannot save a child. It tests constructed synthetic objects that satisfy the declared contracts and blocks configured synthetic false-rescue cases from advancing before a culture window is spent. It does not establish that real laboratory records exist, are authentic, or would pass. This comparison exists so a later increment cannot look "better" just by adding files; it does not establish that the permitted experiment is clinically right or beneficial.

## What "better" means

An increment is `better` only if every invariant still holds and at least one of these is true:

1. More independently motivated false-story families are first-blocked from advancing.
2. The same families are first-blocked earlier on the spend ladder (higher mean culture remaining).
3. Identity-first ranking accuracy rises.

An increment is `worse` if the true nested path closes, freeze bytes move, public confirmation no longer holds, or a new gate never first-blocks a false story.

An increment is `complex_not_better` if invariants hold but discrimination did not improve. Extra tests that only trip the gate they were written for are tautological and do not count.

The CLI also prints a second **reviewer** verdict beside the numeric script. Exit 0 requires the script in `{better, complex_not_better}` **and** `reviewer.agreed`. If family count rises while mean remaining falls, the script may still say `better` (`independent_families_blocked_from_advancing`) while the reviewer says `agree_complex` (`families_up_mean_diluted`). That is intentional: leftover remaining-0 families must not be sold as an earlier block. Official Track 2 has no live leaderboard; this dual verdict is an internal research contract, not a panel score.

## Invariants

- The synthetic true nested path still `advance`s.
- The public community toolkit still `hold`s at confirmation.
- Bound attempt-1 hashes still match `release/track2-reproducibility.json`.
- The living method receipt binds the exact source, scripts, tests, schemas, templates, and configurations evaluated under one deterministic bundle digest.
- The public ranking fixture still cannot make checkpoint-ready.
- Identity-first ranking still stops a probe spend while confirmation is open.

## Spend ladder (ordinal culture remaining)

First-blocking at confirmation saves more remaining spend than first-blocking at replication. Software steps that share one lab object (count identity, assay power, clone-safety, concordance) are the same imaging campaign. A new Python gate on that object is not an earlier block.

`mean_culture_remaining` is the mean, across independently motivated false-story families, of the **highest** remaining spend saved in that family. Higher is earlier. Cloning a later block inside a family already blocked at confirmation cannot lower the score, and a later-only increment is `worse`.

Holdout families (incomplete confirmation, cis phase, heat-shock PD, probe-before-identity, ranking-as-assay) must stay blocked from advancing. Losing one fails invariants.

## How to run

```powershell
python -m unittest tests.test_method_delta -q
python scripts/assess_method_delta.py
python scripts/assess_method_delta.py --previous work/track2-method-delta-analog-correction.json --output work/track2-method-delta-<new-name>.json
```

Write receipts to a new path. Do not overwrite the frozen v3 aggregate receipt, preserved `final4`, or the current living comparison root. `--previous` accepts a valid raw snapshot or hardened wrapper; a linked v2 receipt embeds and verifies its exact immediate parent. Compare later increments to a previous snapshot, not to test count. A fresh receipt must change when a bound living artifact changes; an outcome-only receipt that stays byte-identical after code repair is not reproducibility evidence.

The living comparison root is `work/track2-method-delta-analog-correction.json` (48 families, mean remaining 14.854166666666666). Its parent is `work/track2-method-delta-unmatched-correction.json`. Preserved `work/track2-method-delta-unbiased-allocation-hardened-v2-final4.json` remains the freeze-envelope parent (`parent_snapshot_id=null`). Snapshot, deterministic comparison, and complete receipt have separate content ids. Those ids detect a mismatch relative to retained expected ids; they do not provide external authentication, proof that a record existed before exposure, whole-reseal resistance without an independent anchor, or proof of physical execution.

Hardened v2 comparisons set `external_outcomes.child_benefit` and `external_outcomes.competition_prize` to `not_established`; legacy `child_help` and `prize_help` booleans are rejected. Internal synthetic proxy fields establish neither benefit nor improved judging, ranking, prize probability, or submission readiness. Report the underlying synthetic first-block metrics instead.

## Claim boundary

Method-delta software comparison only. A `better` internal verdict is not evidence of benefit to a child, not a survival percentage, not a panel judgment, and not an upload.
