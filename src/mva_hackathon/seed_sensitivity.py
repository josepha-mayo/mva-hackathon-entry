"""Supplementary seed-sensitivity sweep for the aggregate-count benchmark.

The bound benchmark receipt answers "does the analyzer satisfy the frozen
contract at the declared seed?"; it does not answer "was that seed lucky?"
This module replays the identical benchmark configuration across a
predeclared list of supplementary master seeds and aggregates per-seed
outcomes into a single receipt. The sweep is descriptive robustness
evidence, not a validation of biology: it exercises the same synthetic
aggregate-count generator, so it inherits every limitation the main
receipt discloses (aggregate-only, no timestamped lineage, configured
scenarios only).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from mva_hackathon.generation_selection import (
    GenerationSelectionError,
    _finite_json_float,
    _reject_json_constant,
    _strict_json_object,
    run_benchmark,
)

SCHEMA = "mva-track2-seed-sensitivity/v1"
MAX_SEEDS = 16
HARVESTED_METRIC_KEYS = (
    "maximum_false_generation_wilson_upper_per_required_confound",
    "minimum_required_generation_detection_wilson_lower",
)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GenerationSelectionError(f"{field} must be a positive integer")
    return value


def _strict_object(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GenerationSelectionError(f"{label} must be an object")
    keys = set(value)
    if keys != expected:
        raise GenerationSelectionError(
            f"{label} keys must be exactly {sorted(expected)}; got {sorted(keys)}"
        )
    return value


def _load_json_strict(path: Path, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise GenerationSelectionError(f"cannot read {label}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise GenerationSelectionError(f"{label} root must be an object")
    return parsed


def validate_sweep_config(config: object) -> dict[str, Any]:
    config = _strict_object(
        config, {"schema", "seeds", "acceptance"}, "seed-sweep config"
    )
    if config["schema"] != SCHEMA:
        raise GenerationSelectionError("unsupported seed-sweep schema")
    seeds = config["seeds"]
    if not isinstance(seeds, list) or not seeds or len(seeds) > MAX_SEEDS:
        raise GenerationSelectionError(
            f"seeds must be a non-empty list of at most {MAX_SEEDS} entries"
        )
    for index, seed in enumerate(seeds):
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise GenerationSelectionError(f"seeds[{index}] must be a non-negative integer")
    if len(set(seeds)) != len(seeds):
        raise GenerationSelectionError("seeds must be distinct")
    acceptance = _strict_object(
        config["acceptance"], {"min_accepting_seeds"}, "seed-sweep acceptance"
    )
    min_accepting = _positive_integer(
        acceptance["min_accepting_seeds"], "acceptance.min_accepting_seeds"
    )
    if min_accepting > len(seeds):
        raise GenerationSelectionError(
            "acceptance.min_accepting_seeds cannot exceed the seed count"
        )
    return config


def load_sweep_config(path: Path) -> dict[str, Any]:
    return validate_sweep_config(
        _load_json_strict(path, "seed-sweep config")
    )


def run_seed_sweep(
    sweep_config: dict[str, Any], base_config: dict[str, Any], base_sha256: str
) -> dict[str, Any]:
    """Run the base benchmark once per supplementary seed and aggregate."""
    sweep_config = validate_sweep_config(sweep_config)
    seeds = sweep_config["seeds"]
    min_accepting = sweep_config["acceptance"]["min_accepting_seeds"]
    primary_seed = base_config.get("seed")

    per_seed: list[dict[str, Any]] = []
    for seed in seeds:
        if seed == primary_seed:
            raise GenerationSelectionError(
                "supplementary seed duplicates the primary bound seed"
            )
        variant = dict(base_config)
        variant["seed"] = seed
        result = run_benchmark(variant)
        summary = result["summary"]
        failed = [
            scenario["name"]
            for scenario in result["scenarios"]
            if scenario.get("passed") is not True
        ]
        harvested = {key: summary[key] for key in HARVESTED_METRIC_KEYS}
        for key, value in harvested.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise GenerationSelectionError(
                    f"seed {seed} summary metric {key} is not a finite number"
                )
        per_seed.append(
            {
                "seed": seed,
                "scenarios_passed": summary["passed"],
                "scenarios_total": summary["total"],
                "acceptance_passed": summary["acceptance_passed"],
                "failed_scenarios": failed,
                **harvested,
            }
        )

    seeds_accepted = sum(1 for row in per_seed if row["acceptance_passed"] is True)
    metric_ranges = {
        key: {
            "min": min(row[key] for row in per_seed),
            "max": max(row[key] for row in per_seed),
        }
        for key in HARVESTED_METRIC_KEYS
    }
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": (
            "supplementary robustness receipt: replays the bound synthetic "
            "aggregate-count benchmark across predeclared master seeds. "
            "Answers whether the primary bound seed was favorable by chance; "
            "inherits every limitation of the primary receipt and is not "
            "real-data validation."
        ),
        "primary_seed": primary_seed,
        "supplementary_seeds": seeds,
        "base_config_sha256": base_sha256,
        "per_seed": per_seed,
        "metric_ranges": metric_ranges,
        "summary": {
            "seeds_run": len(seeds),
            "seeds_accepted": seeds_accepted,
            "min_accepting_seeds": min_accepting,
            "acceptance_passed": seeds_accepted >= min_accepting,
        },
    }


def load_and_run_seed_sweep(config_path: Path, base_config_path: Path) -> dict[str, Any]:
    sweep_config = load_sweep_config(config_path)
    base_bytes = base_config_path.read_bytes()
    base_config = _load_json_strict(base_config_path, "base benchmark config")
    return run_seed_sweep(
        sweep_config, base_config, hashlib.sha256(base_bytes).hexdigest()
    )
