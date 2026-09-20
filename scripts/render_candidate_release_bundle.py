from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.candidate_ledger import (  # noqa: E402
    CandidateLedgerError,
    canonical_candidate_ledger_bytes,
    canonical_candidate_ranking_bytes,
    load_candidate_ledger,
    load_sample_stewardship_plan,
    validate_candidate_release_bundle_bytes,
)


LEDGER_NAME = "track2-candidate-ledger.json"
RANKING_NAME = "track2-candidate-ranking.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage a canonical public-only candidate ledger and its exact "
            "computed ranking in a new directory without publishing them."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--sample-plan",
        type=Path,
        help=(
            "strict local sample-stewardship plan required when the ledger "
            "contains a sample promotion; the plan is validated but not staged"
        ),
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()

    if arguments.output_dir.exists():
        parser.error("output directory already exists; refusing to overwrite")
    # A junction or symlink in any existing ancestor would redirect the staged
    # bundle away from the path the operator named.
    output_dir = arguments.output_dir.absolute()
    for ancestor in (output_dir, *output_dir.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            parser.error("output directory resolves through a link")
    try:
        sample_plan = (
            None
            if arguments.sample_plan is None
            else load_sample_stewardship_plan(arguments.sample_plan)
        )
        ledger = load_candidate_ledger(
            arguments.input, public_only=True, sample_plan=sample_plan
        )
        ledger_bytes = canonical_candidate_ledger_bytes(
            ledger, public_only=True, sample_plan=sample_plan
        )
        ranking_bytes = canonical_candidate_ranking_bytes(
            ledger, sample_plan=sample_plan
        )
        validate_candidate_release_bundle_bytes(
            ledger_bytes, ranking_bytes, sample_plan=sample_plan
        )
    except CandidateLedgerError as exc:
        parser.error(str(exc))

    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    ledger_path = arguments.output_dir / LEDGER_NAME
    ranking_path = arguments.output_dir / RANKING_NAME
    ledger_path.write_bytes(ledger_bytes)
    ranking_path.write_bytes(ranking_bytes)
    summary = {
        "schema": "mva.track2-candidate-release-staging/v1",
        "published": False,
        "ledger": {
            "name": LEDGER_NAME,
            "sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        },
        "ranking": {
            "name": RANKING_NAME,
            "sha256": hashlib.sha256(ranking_bytes).hexdigest(),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
