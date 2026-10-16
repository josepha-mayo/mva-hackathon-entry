"""Ninety-second demo: watch the contract refuse rigged rescues.

Runs a narrated subset of the committed generation-versus-selection
benchmark scenarios on synthetic fixtures — no data, no network. Each
scenario prints what the trick is, what a rate-only readout would claim,
and what the contract actually emits.

The full 24-scenario receipt is `reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json`;
reproduce it with:

    python scripts/run_generation_selection_benchmark.py \
        --config configs/track2-generation-selection-benchmark.json \
        --output <new-path>

Usage: python scripts/demo_contract.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon import generation_selection as gs

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "track2-generation-selection-benchmark.json"
REPLICATES = 120

STORY = {
    "fewer_new_errors_strong": (
        "a genuine rescue: fewer new errors per completed division",
        "rescue",
        "certified clean — the contract CAN pass",
    ),
    "no_change": (
        "a true null: treatment does nothing",
        "nothing",
        "no clean signal — correct silence",
    ),
    "generic_cytostasis": (
        "the treatment slows divisions overall; fewer divisions means "
        "fewer recorded errors without fixed segregation",
        "rescue",
        "refused — no clean generation signal",
    ),
    "rescue_plus_moderate_cytostasis": (
        "a real rescue, but riding on moderate cytostasis",
        "rescue",
        "refused — the confound blocks certification even when truth is real",
    ),
    "masked_followup_rescue": (
        "a real rescue where error-bearing daughters are followed up "
        "less often — selection masquerading as generation",
        "rescue",
        "refused — daughter-fate selection cannot certify",
    ),
    "error_daughter_pruning": (
        "error-bearing daughters preferentially die",
        "rescue",
        "refused — differential death is a selection artifact",
    ),
    "error_daughter_preservation": (
        "error-bearing daughters preferentially survive",
        "harm visible as 'more errors'",
        "refused — flagged as preservation, not rescue",
    ),
    "event_scoped_completion_drop_rescue": (
        "a real rescue where one edit event's completion collapses — "
        "invisible to the pooled completion ratio",
        "rescue",
        "refused — per-event completion drops still count",
    ),
    "completion_overshoot_rescue": (
        "a real rescue that also hyper-completes divisions",
        "rescue",
        "refused — overshooting the completion band is not rescue either",
    ),
    "completion_band_edge_rescue": (
        "a real rescue pushed just past the completion-band edge",
        "rescue",
        "refused — the band edge is a boundary, not a loophole",
    ),
    "generic_toxicity": (
        "the treatment is generally toxic",
        "rescue",
        "refused — toxicity is flagged, not averaged away",
    ),
    "informative_followup_bias": (
        "follow-up is preferentially skipped where errors occurred",
        "rescue",
        "refused — biased follow-up is a named flag",
    ),
    "division_detection_bias": (
        "the instrument detects divisions differently by arm",
        "rescue",
        "refused — measurement bias across arms is caught",
    ),
    "event_detection_bias": (
        "the instrument detects error events differently by arm",
        "rescue",
        "refused — event-level detection bias is caught",
    ),
    "event_specificity_bias": (
        "the instrument calls false events differently by arm",
        "rescue",
        "refused — specificity bias is caught",
    ),
    "zero_division_arm": (
        "a degenerate arm: no divisions observed at all",
        "undefined — nothing to compute",
        "refused — 1,000/1,000 no-decision, never a pass",
    ),
}


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    wanted = [s for s in config["scenarios"] if s["name"] in STORY]
    if len(wanted) != len(STORY):
        missing = sorted(set(STORY) - {s["name"] for s in wanted})
        print(f"demo_contract: committed config lacks scenario(s): {missing}")
        return 2
    demo = copy.deepcopy(config)
    demo["scenarios"] = [
        s for name in STORY for s in wanted if s["name"] == name
    ]
    demo["monte_carlo_replicates"] = REPLICATES
    # The acceptance block is part of the strict config schema, so it stays —
    # the demo narrates verdicts rather than asserting the aggregate gate.
    print(
        f"demo: {len(demo['scenarios'])} scenarios x {REPLICATES} synthetic "
        "replicates — fixtures only, no data\n"
    )
    result = gs.run_benchmark(demo)
    width = len(str(len(STORY)))
    for index, scenario in enumerate(result["scenarios"], start=1):
        name = scenario["name"]
        what, naive, verdict = STORY[name]
        clean = scenario["clean_generation_signal"]
        rate = clean["successes"] / clean["total"]
        interp = max(
            scenario["interpretation_counts"].items(), key=lambda kv: kv[1]
        )[0]
        flags = [
            flag
            for flag, det in scenario["component_detection"].items()
            if det["successes"] / det["total"] >= 0.5 and flag != "generation_reduction"
        ]
        print(f"[{index:>{width}}/{len(STORY)}] {name}")
        print(f"  scenario: {what}")
        print(f"  rate-only reading would claim: {naive}")
        print(
            f"  contract verdict: {verdict} "
            f"(clean {clean['successes']}/{clean['total']} = {rate:.1%}; "
            f"modal interpretation: {interp})"
        )
        if flags:
            print(f"  triggered flags: {', '.join(sorted(flags))}")
        print()
    print(
        "synthetic-only: these certify the analyzer's behavior on fixtures, "
        "not biology — full receipt: reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
