from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.save_path import (  # noqa: E402
    SavePathError,
    run_save_path_suite,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a complete nested lab path can advance and that false rescue stories cannot."
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        result = run_save_path_suite()
    except (SavePathError, ValueError, OSError) as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - normalize unexpected bugs
        parser.error(f"unexpected error: {exc}")
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is not None:
        if arguments.output.exists():
            parser.error("output already exists; refusing to overwrite")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(
        "save-path simulation: "
        f"reachable={result['save_path_reachable']}; "
        f"true_opened={result['n_true_path_opened']}/{result['n_true_path']}; "
        "false_blocked_from_advancing="
        f"{result['n_false_paths_blocked_from_advancing']}/"
        f"{result['n_false_path']}"
    )
    return (
        0
        if result["save_path_reachable"]
        and result["false_paths_blocked_from_advancing"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
