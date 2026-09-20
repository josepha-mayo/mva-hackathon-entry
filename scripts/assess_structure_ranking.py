from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.structure_ranking import (  # noqa: E402
    StructureRankingError,
    assess_structure_ranking,
)




def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StructureRankingError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise StructureRankingError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise StructureRankingError(f"non-finite JSON number: {value}")
    return parsed


def _load_json(path: Path) -> object:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
        parse_float=_finite_float,
    )

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank an exact residue against analog and nearby-benign controls without treating ranking as an assay."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        table = _load_json(arguments.input)
        result = assess_structure_ranking(table)
    except (StructureRankingError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - normalize unexpected bugs
        parser.error(f"unexpected error: {exc}")
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is not None:
        if arguments.output.exists():
            parser.error("output already exists; refusing to overwrite")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0 if result.get("program_effect") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
