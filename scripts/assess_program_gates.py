from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.program_gates import (  # noqa: E402
    ProgramGateError,
    assess_confirmation_gate,
    assess_count_table_identity,
    assess_endpoint_concordance,
    assess_hypomorph_gate,
    assess_phase_gate,
    assess_replication_decision,
    assess_transcript_gate,
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProgramGateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ProgramGateError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ProgramGateError(f"non-finite JSON number: {value}")
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
        description="Fail-closed phase, hypomorph, or replication program gates."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--phase", type=Path)
    source.add_argument("--confirmation", type=Path)
    source.add_argument("--transcript", type=Path)
    source.add_argument("--scorecard", type=Path)
    source.add_argument("--concordance", type=Path)
    source.add_argument("--count-identity", type=Path)
    source.add_argument("--replication", type=Path)
    parser.add_argument("--clone-safety", type=Path)
    parser.add_argument("--exposure", type=Path)
    parser.add_argument("--lineage-counts", type=Path)
    parser.add_argument("--blinded", type=Path)
    parser.add_argument("--measured-exposure", type=Path)
    parser.add_argument("--assay-plan", type=Path)
    parser.add_argument("--hypomorph", type=Path)
    parser.add_argument("--hypothesis", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.phase is not None:
            payload = _load_json(arguments.phase)
            result = assess_phase_gate(payload)
        elif arguments.confirmation is not None:
            payload = _load_json(arguments.confirmation)
            result = assess_confirmation_gate(payload)
        elif arguments.transcript is not None:
            payload = _load_json(arguments.transcript)
            result = assess_transcript_gate(payload)
        elif arguments.scorecard is not None:
            payload = _load_json(arguments.scorecard)
            result = assess_hypomorph_gate(payload)
        elif arguments.concordance is not None:
            payload = _load_json(arguments.concordance)
            result = assess_endpoint_concordance(payload)
        elif arguments.count_identity is not None:
            if (
                arguments.blinded is None
                or arguments.measured_exposure is None
                or arguments.assay_plan is None
            ):
                parser.error(
                    "--count-identity requires --blinded, --measured-exposure, "
                    "and --assay-plan"
                )
            result = assess_count_table_identity(
                _load_json(arguments.count_identity),
                _load_json(arguments.blinded),
                _load_json(arguments.measured_exposure),
                _load_json(arguments.assay_plan),
            )
        else:
            payload = _load_json(arguments.replication)
            clone_safety = None
            exposure = None
            concordance = None
            hypomorph = None
            hypothesis = None
            if arguments.clone_safety is not None:
                clone_safety = _load_json(arguments.clone_safety)
            if arguments.exposure is not None:
                exposure = _load_json(arguments.exposure)
            if arguments.lineage_counts is not None:
                concordance = assess_endpoint_concordance(
                    _load_json(arguments.lineage_counts)
                )
            if arguments.hypomorph is not None:
                hypomorph = _load_json(arguments.hypomorph)
            if arguments.hypothesis is not None:
                hypothesis = _load_json(arguments.hypothesis)
            result = assess_replication_decision(
                payload,
                clone_safety=clone_safety,
                exposure=exposure,
                concordance=concordance,
                hypomorph=hypomorph,
                hypothesis=hypothesis,
            )
    except (ProgramGateError, OSError, json.JSONDecodeError) as exc:
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
    effect = result.get("program_effect")
    passed = effect == "pass" or (
        effect == "advance" and result.get("gate") == "replication"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
