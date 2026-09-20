from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import tempfile
import warnings
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.method_delta import (  # noqa: E402
    LEGACY_SCHEMA,
    SCHEMA,
    MethodDeltaError,
    seal_method_delta_receipt,
    snapshot_method,
    validate_method_delta_receipt,
    validate_snapshot,
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise MethodDeltaError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise MethodDeltaError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise MethodDeltaError(f"non-finite JSON number: {value}")
    return parsed


def _load_snapshot(path: Path) -> dict:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
        parse_float=_finite_float,
    )
    if not isinstance(payload, dict):
        raise MethodDeltaError("previous snapshot payload must be an object")
    if payload.get("schema") in {SCHEMA, LEGACY_SCHEMA} and payload.get(
        "record_kind"
    ) == "snapshot":
        validate_snapshot(payload, label="previous snapshot")
        return copy.deepcopy(payload)
    if isinstance(payload.get("snapshot"), dict):
        if payload["snapshot"].get("schema") == LEGACY_SCHEMA:
            validate_snapshot(payload["snapshot"], label="legacy previous snapshot")
            warnings.warn(
                "legacy v1 wrapper comparison is unauthenticated; only its "
                "content-addressed embedded snapshot is being used",
                RuntimeWarning,
                stacklevel=2,
            )
            return copy.deepcopy(payload["snapshot"])
        return validate_method_delta_receipt(payload)
    raise MethodDeltaError("previous snapshot has the wrong schema")


def _write_exclusive_durable(path: Path, encoded: str) -> None:
    """Atomically publish one durable output without replacing an existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        data = encoded.encode("utf-8")
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise OSError("exclusive receipt write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        # A same-directory hard link publishes the complete temporary inode and
        # fails if the destination already exists; unlike replace(), it cannot
        # overwrite a receipt created by a concurrent process.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    if hasattr(os, "O_DIRECTORY") and os.name != "nt":
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | os.O_DIRECTORY,
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Snapshot the living Track 2 method and compare it to the freeze "
            "envelope or a previous snapshot. More gates are not a rescued child."
        )
    )
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--recorded-at",
        help="Caller-declared ISO-8601 time; recorded as unauthenticated.",
    )
    parser.add_argument(
        "--exposure-started-at",
        help="Caller-declared ISO-8601 boundary; recorded as unauthenticated.",
    )
    arguments = parser.parse_args()
    try:
        previous = None
        if arguments.previous is not None:
            previous = _load_snapshot(arguments.previous)
        current = snapshot_method(
            arguments.repo,
            parent_snapshot_id=(
                None if previous is None else previous["snapshot_id"]
            ),
            recorded_at=arguments.recorded_at,
            exposure_started_at=arguments.exposure_started_at,
        )
        receipt = seal_method_delta_receipt(current, previous=previous)
        comparison = receipt["comparison"]
        encoded = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if arguments.output is not None:
            _write_exclusive_durable(arguments.output, encoded)
    except FileExistsError:
        parser.error("output already exists; refusing to overwrite")
    except (MethodDeltaError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - normalize unexpected bugs
        parser.error(f"unexpected error: {exc}")
    print(
        "method-delta: "
        f"verdict={comparison['verdict']}; "
        f"reason={comparison['reason']}; "
        f"reviewer={comparison.get('reviewer', {}).get('reviewer_verdict')}; "
        f"joint={comparison.get('internal_joint_verdict')}; "
        f"true_opened={current['metrics']['n_true_opened']}/"
        f"{current['metrics']['n_true']}; "
        "families_blocked_from_advancing="
        f"{current['metrics']['n_independent_families_blocked_from_advancing']}; "
        f"mean_culture_remaining={current['metrics']['mean_culture_remaining']:.2f}"
    )
    script_ok = comparison["verdict"] in {"better", "complex_not_better"}
    reviewer_ok = (comparison.get("reviewer") or {}).get("agreed") is True
    return 0 if script_ok and reviewer_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
