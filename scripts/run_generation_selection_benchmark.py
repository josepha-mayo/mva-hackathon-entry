from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.generation_selection import (  # noqa: E402
    GenerationSelectionError,
    load_and_run_benchmark,
)


def benchmark_exit_code(result: dict) -> int:
    summary = result.get("summary")
    if not isinstance(summary, dict):
        return 1
    return 0 if summary.get("acceptance_passed") is True else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the synthetic aggregate-count generation-versus-selection benchmark."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        result = load_and_run_benchmark(arguments.config)
    except GenerationSelectionError as exc:
        parser.error(str(exc))
    if arguments.output.exists():
        parser.error("output already exists; refusing to overwrite")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"aggregate-count benchmark: {result['summary']['passed']}/"
        f"{result['summary']['total']} scenarios passed; "
        f"acceptance={result['summary']['acceptance_passed']}"
    )
    return benchmark_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
