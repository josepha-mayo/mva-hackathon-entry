from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.lineage import LineageError, run_adversarial_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the synthetic timestamped lineage adversarial suite."
    )
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        result = run_adversarial_suite()
    except LineageError as exc:
        parser.error(str(exc))
    if os.path.lexists(arguments.output):
        parser.error("output already exists; refusing to overwrite")
    target = arguments.output.absolute()
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            parser.error("output path resolves through a link")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"lineage adversarial suite: {result['passed']}/{result['n_cases']} "
        f"cases passed; all_passed={result['all_passed']}"
    )
    return 0 if result["all_passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
