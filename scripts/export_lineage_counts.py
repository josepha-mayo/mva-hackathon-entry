from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from jsonschema import Draft202012Validator  # noqa: E402

from mva_hackathon.lineage import (  # noqa: E402
    LineageError,
    _finite_float,
    _reject_duplicate_json_keys,
    _reject_json_constant,
    build_adversarial_fixture,
    export_first_attempt_aggregates,
    load_lineage_study,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "track2_lineage_counts.schema.json"
)
_SCHEMA = Draft202012Validator(
    json.loads(
        SCHEMA_PATH.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
        parse_constant=_reject_json_constant,
        parse_float=_finite_float,
    )
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export truth-free first-attempt lineage counts."
    )
    parser.add_argument("--output", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--fixture", type=str)
    arguments = parser.parse_args()
    try:
        if arguments.input is not None:
            study = load_lineage_study(arguments.input)
        else:
            study = build_adversarial_fixture(arguments.fixture)
        payload = export_first_attempt_aggregates(study)
    except LineageError as exc:
        parser.error(str(exc))
    problems = sorted(
        _SCHEMA.iter_errors(payload), key=lambda error: list(error.path)
    )
    if problems:
        parser.error(
            "exported counts fail the lineage-counts schema: "
            + "; ".join(problem.message for problem in problems[:3])
        )
    # A junction/symlink in the output path (including a broken link whose
    # exists() is False) would redirect the write away from the named path.
    if os.path.lexists(arguments.output):
        parser.error("output already exists; refusing to overwrite")
    target = arguments.output.absolute()
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            parser.error("output path resolves through a link")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(payload['runs'])} count rows to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
