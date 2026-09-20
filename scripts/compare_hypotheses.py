"""Compare the synthetic rescue hypotheses and emit a markdown receipt.

Runs both tracked synthetic hypothesis tables through
``compare_hypotheses`` and writes a judge-facing comparison artifact.
Synthetic fixtures only; a passing gate is a method-specification check,
not a biological result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mva_hackathon.candidate_ledger import (  # noqa: E402
    _finite_json_float,
    _reject_json_constant,
    _strict_object,
)
from mva_hackathon.hypothesis_compare import (  # noqa: E402
    compare_hypotheses,
)

HYPOTHESES = {
    "chaperone_pair": REPO
    / "templates"
    / "community"
    / "observed_inferred_unknown.synthetic.json",
    "proteostasis_stabilizer": REPO
    / "templates"
    / "hypotheses"
    / "proteostasis_stabilizer.synthetic.json",
}
DEFAULT_OUTPUT = REPO / "reports" / "TRACK2_HYPOTHESIS_COMPARISON.md"


def load(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_json_constant,
        parse_float=_finite_json_float,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payloads = {name: load(path) for name, path in HYPOTHESES.items()}
    comparison = compare_hypotheses(payloads)
    rows = comparison["hypotheses"]

    lines = [
        "# Track 2 — competing rescue hypothesis comparison",
        "",
        f"Selection rule: `{comparison['selection_rule']}`",
        f"Lead hypothesis: `{comparison['lead_hypothesis']}`",
        f"Passing hypotheses: `{comparison['passing_hypotheses']}`",
        "",
        "| hypothesis | status | reason | child_claim | work_ceiling | falsifiers | alternatives | controls |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in sorted(rows):
        row = rows[name]
        lines.append(
            f"| {name} | {row['status']} | {row['reason']} | "
            f"{row['child_claim_strength']} | {row['work_ceiling']} | "
            f"{row['falsifier_count']} | {row['alternative_count']} | "
            f"{row['control_count']} |"
        )
    lines += [
        "",
        "Both hypotheses share the same rescue method (exact correction as "
        "positive control, lineage-tracked endpoint, predeclared numeric kill "
        "rule, interference counterscreen, multiplicity rule) but assert "
        "different mechanisms: functional rescue via a chaperone-style probe "
        "versus abundance rescue via a proteostasis stabilizer.",
        "",
        "A pass is a method-specification check on synthetic fixtures — not "
        "evidence that either mechanism is biologically true.",
        "",
    ]
    for name, path in HYPOTHESES.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"- `{name}` fixture sha256: `{digest}`")
    # The default output is the tracked report this script exists to
    # regenerate; any other path still refuses to overwrite.
    if os.path.lexists(args.output) and args.output != DEFAULT_OUTPUT:
        parser.error("output already exists; refusing to overwrite")
    target = args.output.absolute()
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            parser.error("output path resolves through a link")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0 if comparison["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
