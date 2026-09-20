# Track 2 lineage contract

Status: synthetic software contract only. This document names no subject-specific gene, allele, or medicine.

The v3 aggregate-count firewall remains the frozen generation-versus-selection receipt. This lineage contract sits beside it. It does not replace that receipt and does not claim biological validation.

## Why a second contract exists

Aggregate counts cannot separate pre-division death from other non-completion. They also cannot see clone nesting, imaging-field concentration, label leakage, or a signal that lives in one edit event or one clone. A lower error fraction can still be manufactured by cytostasis, toxic pruning, dropout, or clone selection.

The lineage analyzer therefore requires timestamped founder records with mutually exclusive first-attempt labels:

- dropout
- pre-division death
- no division
- completed, no error
- completed, error

Daughters are allowed only after a completed division — at most two per bipolar founder, three or four per founder explicitly marked `division_class: multipolar`.

## Pediatric completion band

The v3 aggregate software band of 0.80-1.25 is not reused here. A 20 percent drop in completed divisions can itself be harmful in a growth-disorder assay and can manufacture an apparently lower error fraction.

The lineage contract freezes a stricter band before unblinding:

- relative completion ratio interval inside `[0.90, 1.15]`
- default analysis band `[0.95, 1.10]`
- absolute completion drop at most 0.10, default 0.05

A generation claim requires concordance of error-per-completed-division and error-bearing-completion-per-enrolled-founder, plus this pediatric completion band, plus no competing toxicity, pruning, preservation, dropout, field, clone, or leakage flag.

Clone-safety v2 is a separate observed-label contract nested by edit event, clone, and run. Rates are computed on **resolved fates only** (`reproduced + died`): a censored daughter — observed but never reaching a terminal fate — is unaccounted progeny, satisfies no follow-up obligation, and enters no rate denominator. The contract requires at least eight resolved daughters per arm in both the event-positive and event-negative strata; when division counts are present it additionally requires complete event-positive daughter fate resolution in both arms (resolved daughters must cover the declared daughter slots — two per division by default, more under a declared multipolar count — so unaccounted or censored daughters cannot hide a fitness gain) and symmetric event-negative resolved-fate depth between arms (so under-resolved treatment non-error daughters cannot hide death or arrest). Advancement stops at-or-above the thresholds: when the treatment-to-vehicle event-positive daughter reproduction rate ratio reaches `1.25`, when event-positive reproduction rises disproportionately to event-negative reproduction at a ratio of `1.25`, or when the event-negative daughter death-rate ratio reaches `2.0`; corresponding zero-control, positive-treatment cases are unbounded stops. Thresholds must be finite and are strict, heuristic software boundaries rather than a power analysis. Event labels can be misclassified and do not establish daughter genotype. See `reports/TRACK2_CLONE_SAFETY.md`.

## Fail-closed cases

The checked-in adversarial suite includes:

- clean generation under the pediatric band
- error-daughter pruning without generation change
- cytostasis
- mixed generation, selection, and cytostasis
- imaging-field concentration
- one-clone false positive
- one-edit-event false positive
- toxic pruning
- preservation of error daughters
- label leakage
- treatment-dependent dropout
- unequal follow-up
- enrollment after exposure, which the contract rejects

The analyzer never receives scenario names or generator truth. Evaluator-only expectations live in a separate function.

## How to run

```powershell
python -m unittest tests.test_lineage -v
python scripts/run_lineage_adversarial_benchmark.py --output local_dev/track2-lineage-adversarial.json
python scripts/export_lineage_counts.py --fixture clean_generation --output local_dev/track2-lineage-counts.json
```

Write the receipt to a new path. Do not overwrite the frozen v3 aggregate receipt. The checked-in lineage receipt is `reports/TRACK2_LINEAGE_ADVERSARIAL.json`. It is a separate software artifact and is not part of `release/track2-reproducibility.json`.

Lineage counts cannot be fed to the v3 aggregate analyzer unless every row has zero pre-division death, no-division, and dropout, the export is locked, and the labels are still blinded. The mapper raises if those labels are present, if lock_state is not locked, or if blinded is not true. That is intentional.

Count rows that cannot exist also fail closed in the concordance gate: first-attempt outcomes must partition opportunities, and followed daughters cannot exceed the declared daughter slots. A bipolar division defaults to two slots; a founder marked `division_class: multipolar` (a `completed_error`-only label) may record three or four daughters and must record at least three — fewer cannot be distinguished from a bipolar scoring error, and a multipolar claim on any non-error outcome fails closed. At the count level a multipolar claim is **co-declared**: `event_positive_multipolar_divisions` states how many of the error-positive divisions were multipolar, and `event_positive_daughter_slots` must then lie in `[2*divisions + multipolar, 2*divisions + 2*multipolar]` (each multipolar division contributes three or four daughters). A slots claim beyond the bipolar default without the multipolar declaration is a contract error, and a declared multipolar count without declared slots is one too — self-asserted capacity cannot float free of its mechanism. Clean (event-negative) divisions can never declare more than two slots. The exporter emits both fields only when a row's slots exceed the bipolar default, so bipolar exports are byte-identical to the previous contract. Clone-safety uses declared slots — not a fixed two-per-division — for its complete resolved-fate requirement in both observed label strata when division counts are present. Count identity requires all thirteen shared observed-run counts to be present as nonnegative integers — including the competing-risk fields `pre_division_death`, `no_division`, and `dropout_censored`, so the blinded table attests that no outcome volume is unattributed rather than leaving the `opportunities − detected` gap unlabelled; omitted zero-valued fields cannot pass by defaulting to zero. Declared daughter slots and the multipolar count participate in count identity and the source fingerprint, so a multipolar claim cannot differ between the lineage table and the blinded table.

Each founder now carries the functional execution, exposure-support record, exposure profile, probe or control, run, culture batch, and exposure start that generated its first-attempt observation. When allocation is declared, the study also carries the canonical allocation id and every founder carries the realized allocation block, assay plate, row, column, dosing order, and acquisition order as an all-or-none tuple. The aggregate exporter preserves those contexts and rejects any arm x event x clone x run group that would merge multiple exposure or allocation contexts. The lineage source fingerprint canonically sorts rows and includes study context, all shared daughter counts, every exposure-context field, the allocation id, and the realized allocation tuple; row reordering cannot create a false mismatch, and omitted daughter outcomes cannot create false source equality.

The v2 pre-exposure allocation assessment gate distinguishes the treatment-application unit (functional-execution well), randomization and analysis unit (biological pair), and biological replication unit (clone/edit-event). Its input plan is v3. The gate requires one vehicle and one treatment execution in each pair, exact same-row and fixed-context matching within the pair, and at least six pairs within every plate x batch x run x event context. In each context, exact per-arm plate-column distributions must match.

The arm-blind support is filtered before the seed commitment to retain at least 75% of centered arm-indicator information after the frozen context-specific dosing/acquisition linear, squared, and cross-product adjustment; joint support must contain 64 to 1,000,000 vectors. The v4 input commitment binds the canonical manifest, exact support ordering, support count and digest, algorithm, generator, and selection rule in a separate pre-reveal record. A second record holds the experiment-bound v3 seed commitment. An accepted raw 256-bit draw indexes the canonical support directly; the incomplete modulo bucket is rejected without synthesized redraw. The strict chain is lock, input record, seed record, seed reveal, selected-vector record, final plan record, then exposure; all four record ids are distinct. Both allocation and inference floating reductions use the digest-bound `explicit_left_to_right_binary64_v1` rule.

The later count-identity gate requires every realized tuple and the selected arm vector to match the committed plan and seed replay exactly. It then requires favorable raw directions and one-sided p-values at or below 0.05 for both generation endpoints with biological pairs weighted equally. Those p-values are exact only for the global Fisher sharp null of no effect on any execution, conditional on the declared uniform assignment model and frozen support; they are not exact for a weak zero-average-effect null. Every treatment aggregate must also resolve exactly once to an eligible measured-exposure execution and every vehicle to an explicit control record; a valid exposure file from another run cannot be collaged with attractive counts.

The uniform pre-outcome seed draw and the other causal assumptions—consistency/single arm versions, no interference/carryover/cross-well contamination, a fixed manifest with no post-assignment exclusion, and arm-blinded outcome ascertainment—are `not_software_attested`. Current `not_attested` entropy permits only a conditional synthetic software pass; a non-synthetic allocation holds. The private fixed-seed relabel helper rejects non-synthetic exposure or lineage and never authorizes seed search, observed-data resealing, or real allocation. These are conditional allocation, inference, and referential-integrity checks only. They cannot authenticate entropy or prove that physical cells occupied the declared wells, received the declared exposure, or were biologically rescued. See `reports/TRACK2_RANDOMIZATION_CONTRACT.md`.

## Claim boundary

This is a timestamped first-attempt competing-risk software contract. It is not mixed-effects clinical inference, not a real blinded calibration, and not evidence that any perturbation improves chromosome segregation.
