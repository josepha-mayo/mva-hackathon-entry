from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.candidate_ledger import (  # noqa: E402
    CandidateLedgerError,
    load_candidate_ledger,
    load_sample_stewardship_plan,
    rank_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank a Track 2 candidate ledger without asserting efficacy."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--sample-plan",
        type=Path,
        help=(
            "strict local sample-stewardship plan required when the ledger "
            "contains a sample promotion"
        ),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--public-only", action="store_true")
    arguments = parser.parse_args()
    try:
        sample_plan = (
            None
            if arguments.sample_plan is None
            else load_sample_stewardship_plan(arguments.sample_plan)
        )
        ledger = load_candidate_ledger(
            arguments.input,
            public_only=arguments.public_only,
            sample_plan=sample_plan,
        )
        ranking = rank_candidates(ledger, sample_plan=sample_plan)
    except CandidateLedgerError as exc:
        parser.error(str(exc))
    encoded = json.dumps(ranking, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is not None:
        if os.path.lexists(arguments.output):
            parser.error("output already exists; refusing to overwrite")
        target = arguments.output.absolute()
        for ancestor in (target, *target.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                parser.error("output path resolves through a link")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
