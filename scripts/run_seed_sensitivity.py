from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.generation_selection import GenerationSelectionError  # noqa: E402
from mva_hackathon.seed_sensitivity import load_and_run_seed_sweep  # noqa: E402

BASE_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "track2-generation-selection-benchmark.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the supplementary seed-sensitivity sweep over the bound "
            "aggregate-count benchmark configuration."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        result = load_and_run_seed_sweep(arguments.config, BASE_CONFIG)
    except GenerationSelectionError as exc:
        parser.error(str(exc))
    if arguments.output.exists():
        parser.error("output already exists; refusing to overwrite")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary = result["summary"]
    print(
        f"seed sensitivity: {summary['seeds_accepted']}/{summary['seeds_run']} "
        f"supplementary seeds accepted; acceptance={summary['acceptance_passed']}"
    )
    return 0 if summary["acceptance_passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
