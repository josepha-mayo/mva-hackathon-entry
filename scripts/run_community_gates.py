from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.community_pipeline import (  # noqa: E402
    CommunityPipelineError,
    run_community_pipeline,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run community toolkit gates in order and stop after the first fail."
    )
    parser.add_argument("--community", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        result = run_community_pipeline(arguments.community)
    except CommunityPipelineError as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - normalize unexpected bugs
        # Gate modules raise their own error types (ProgramGateError,
        # ExposureGateError, NextExperimentError, ...). A gate error must
        # still surface as a clean CLI failure, never a raw traceback on
        # judge-facing logs.
        parser.error(f"unexpected error: {exc}")
    encoded = (
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    if arguments.output is not None:
        if os.path.lexists(arguments.output):
            parser.error("output already exists; refusing to overwrite")
        target = arguments.output.absolute()
        for ancestor in (target, *target.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                parser.error("output path resolves through a link")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(
        f"community pipeline: decision={result['decision']}; "
        f"blocked_by={result['blocked_by']}; skipped={result['n_skipped']}"
    )
    return 0 if result["decision"] == "advance" else 1


if __name__ == "__main__":
    raise SystemExit(main())
