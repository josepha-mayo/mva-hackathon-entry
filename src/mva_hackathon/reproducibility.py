"""Strict integrity contract for the public Track 2 evidence package."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any


SCHEMA = "mva-track2-reproducibility/v2"
MANIFEST_PATH = PurePosixPath("release/track2-reproducibility.json")
ARTIFACT_PATHS = {
    "track2_report": PurePosixPath("reports/josephmayo_track2_report.md"),
    "track2_pitch_script": PurePosixPath("reports/josephmayo_track2_pitch_script.md"),
    "benchmark_config": PurePosixPath(
        "configs/track2-generation-selection-benchmark.json"
    ),
    "benchmark_source": PurePosixPath("src/mva_hackathon/generation_selection.py"),
    "benchmark_runner": PurePosixPath("scripts/run_generation_selection_benchmark.py"),
    "benchmark_test": PurePosixPath("tests/test_generation_selection.py"),
    "benchmark_receipt": PurePosixPath(
        "reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json"
    ),
    "integrity_source": PurePosixPath("src/mva_hackathon/reproducibility.py"),
    "integrity_runner": PurePosixPath("scripts/verify_track2_reproducibility.py"),
    "integrity_test": PurePosixPath("tests/test_reproducibility.py"),
    "manifest_builder": PurePosixPath(
        "scripts/create_track2_reproducibility_manifest.py"
    ),
    "python_contract": PurePosixPath("pyproject.toml"),
}
COMMANDS = {
    "benchmark": (
        "python scripts/run_generation_selection_benchmark.py --config "
        "configs/track2-generation-selection-benchmark.json --output <new-path>"
    ),
    "integrity": "python scripts/verify_track2_reproducibility.py .",
    "manifest": (
        "python scripts/create_track2_reproducibility_manifest.py . "
        "--source-commit <40-hex>"
    ),
    "tests": "python -m unittest discover -s tests -v",
    "privacy": "python scripts/privacy_gate.py .",
}
TOP_LEVEL_KEYS = frozenset({"schema", "source_commit", "commands", "artifacts"})
ARTIFACT_KEYS = frozenset({"role", "path", "sha256"})
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class ReproducibilityError(ValueError):
    """Raised when a strict JSON object contains a duplicate key."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReproducibilityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReproducibilityError(f"non-finite JSON number: {value}")


def _load_json(data: bytes, label: str) -> tuple[Any | None, list[str]]:
    if data.startswith(b"\xef\xbb\xbf"):
        return None, [f"{label} must not contain a UTF-8 BOM"]
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ReproducibilityError) as exc:
        return None, [f"{label} is not strict duplicate-free UTF-8 JSON ({exc})"]
    return value, []


def validate_manifest_bytes(
    data: bytes,
    load_artifact: Callable[[PurePosixPath], bytes | None],
) -> list[str]:
    """Validate the manifest, every bound artifact, and receipt cross-links."""

    manifest, issues = _load_json(data, "reproducibility manifest")
    if issues:
        return issues
    if not isinstance(manifest, dict):
        return ["reproducibility manifest root must be an object"]
    if set(manifest) != TOP_LEVEL_KEYS:
        return ["reproducibility manifest has missing or surplus root keys"]
    if manifest.get("schema") != SCHEMA:
        issues.append("unsupported reproducibility manifest schema")

    source_commit = manifest.get("source_commit")
    if not isinstance(source_commit, str) or COMMIT_PATTERN.fullmatch(source_commit) is None:
        issues.append("source_commit must be a lowercase 40-character Git commit")
    if manifest.get("commands") != COMMANDS:
        issues.append("reproducibility commands differ from the frozen contract")

    entries = manifest.get("artifacts")
    if not isinstance(entries, list):
        issues.append("reproducibility artifacts must be a list")
        return issues
    if len(entries) != len(ARTIFACT_PATHS):
        issues.append("reproducibility manifest must bind every fixed artifact")

    seen_roles: set[str] = set()
    seen_paths: set[str] = set()
    digests: dict[str, str] = {}
    for index, entry in enumerate(entries, start=1):
        label = f"reproducibility artifact {index}"
        if not isinstance(entry, dict):
            issues.append(f"{label} must be an object")
            continue
        if set(entry) != ARTIFACT_KEYS:
            issues.append(f"{label} has missing or surplus keys")
            continue
        role = entry.get("role")
        path_text = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(role, str) or role not in ARTIFACT_PATHS:
            issues.append(f"{label} has an unknown role")
            continue
        if role in seen_roles:
            issues.append(f"{label} duplicates a role")
        seen_roles.add(role)
        expected_path = ARTIFACT_PATHS[role]
        if not isinstance(path_text, str) or path_text != expected_path.as_posix():
            issues.append(f"{label} does not use the role's fixed path")
            continue
        if path_text in seen_paths:
            issues.append(f"{label} duplicates a path")
        seen_paths.add(path_text)
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            issues.append(f"{label} requires a lowercase SHA-256")
            continue
        artifact_data = load_artifact(expected_path)
        if artifact_data is None:
            issues.append(f"{label} is missing or unreadable")
            continue
        observed_digest = hashlib.sha256(artifact_data).hexdigest()
        if observed_digest != digest:
            issues.append(f"{label} digest does not match exact bytes")
            continue
        digests[role] = digest

    if set(ARTIFACT_PATHS) != seen_roles:
        issues.append("reproducibility manifest is missing one or more fixed roles")
    if issues:
        return issues

    receipt_bytes = load_artifact(ARTIFACT_PATHS["benchmark_receipt"])
    if receipt_bytes is None:
        return ["benchmark receipt is missing"]
    receipt, receipt_issues = _load_json(receipt_bytes, "benchmark receipt")
    if receipt_issues:
        return receipt_issues
    if not isinstance(receipt, dict):
        return ["benchmark receipt root must be an object"]
    runtime = receipt.get("runtime_receipt")
    summary = receipt.get("summary")
    if not isinstance(runtime, dict) or not isinstance(summary, dict):
        return ["benchmark receipt lacks runtime or summary objects"]

    expected_runtime_hashes = {
        "config_sha256": digests["benchmark_config"],
        "source_sha256": digests["benchmark_source"],
        "runner_sha256": digests["benchmark_runner"],
        "test_sha256": digests["benchmark_test"],
    }
    if any(runtime.get(key) != value for key, value in expected_runtime_hashes.items()):
        issues.append("benchmark runtime hashes do not match bound artifacts")
    if runtime.get("canonical_command") != COMMANDS["benchmark"]:
        issues.append("benchmark receipt command differs from the frozen contract")
    if runtime.get("git_source_commit") != source_commit:
        issues.append("benchmark receipt is not tied to source_commit")
    if runtime.get("git_tracked_worktree_clean") is not True:
        issues.append("benchmark receipt was not generated from a clean tracked worktree")
    if summary.get("acceptance_passed") is not True:
        issues.append("benchmark global acceptance did not pass")

    config_bytes = load_artifact(ARTIFACT_PATHS["benchmark_config"])
    if config_bytes is None:
        issues.append("benchmark configuration is missing")
    else:
        config, config_issues = _load_json(config_bytes, "benchmark configuration")
        issues.extend(config_issues)
        if not config_issues:
            if not isinstance(config, dict):
                issues.append("benchmark configuration root must be an object")
            else:
                scenarios = config.get("scenarios")
                replicates = config.get("monte_carlo_replicates")
                if not isinstance(scenarios, list) or not scenarios:
                    issues.append("benchmark configuration needs at least one scenario")
                if (
                    not isinstance(replicates, int)
                    or isinstance(replicates, bool)
                    or replicates <= 0
                ):
                    issues.append(
                        "benchmark configuration needs positive Monte Carlo replicates"
                    )
                if (
                    isinstance(scenarios, list)
                    and scenarios
                    and isinstance(replicates, int)
                    and not isinstance(replicates, bool)
                    and replicates > 0
                ):
                    scenario_count = len(scenarios)
                    comparison_count = scenario_count * replicates
                    if (
                        summary.get("passed") != scenario_count
                        or summary.get("total") != scenario_count
                        or summary.get("all_passed") is not True
                    ):
                        issues.append(
                            "benchmark did not pass every configured scenario"
                        )
                    if (
                        receipt.get("monte_carlo_replicates_per_scenario")
                        != replicates
                    ):
                        issues.append(
                            "benchmark receipt replicate count differs from configuration"
                        )
                    if (
                        receipt.get(
                            "total_simulated_vehicle_treatment_comparisons"
                        )
                        != comparison_count
                    ):
                        issues.append(
                            "benchmark receipt comparison count differs from configuration"
                        )

    for value in summary.values():
        if isinstance(value, float) and not math.isfinite(value):
            issues.append("benchmark summary contains a non-finite number")
            break
    return issues


__all__ = [
    "ARTIFACT_PATHS",
    "COMMANDS",
    "MANIFEST_PATH",
    "SCHEMA",
    "validate_manifest_bytes",
]
