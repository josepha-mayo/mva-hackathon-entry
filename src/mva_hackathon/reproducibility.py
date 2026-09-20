"""Strict integrity contract for the public Track 2 evidence package."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
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
    # The verifiers and receipt-minting pipeline are themselves bound bytes —
    # an unbound verifier could be weakened without any manifest detecting it.
    "freeze_source": PurePosixPath("src/mva_hackathon/freeze.py"),
    "privacy_gate": PurePosixPath("scripts/privacy_gate.py"),
    "pipeline_source": PurePosixPath("src/mva_hackathon/community_pipeline.py"),
    "gates_source": PurePosixPath("src/mva_hackathon/program_gates.py"),
    # The decision surface that evolved under the adversarial program:
    # a release must bind the gates, analyzers, and adversarial suite the
    # verdicts were computed with, not just the benchmark harness.
    "lineage_source": PurePosixPath("src/mva_hackathon/lineage.py"),
    "exposure_gate_source": PurePosixPath("src/mva_hackathon/exposure_gate.py"),
    "assay_power_source": PurePosixPath("src/mva_hackathon/assay_power.py"),
    "clone_safety_source": PurePosixPath("src/mva_hackathon/clone_safety.py"),
    "save_path_source": PurePosixPath("src/mva_hackathon/save_path.py"),
    "method_delta_source": PurePosixPath("src/mva_hackathon/method_delta.py"),
    "submission_go_checker": PurePosixPath("scripts/check_submission_go.py"),
    "lineage_test": PurePosixPath("tests/test_lineage.py"),
    "exposure_gate_test": PurePosixPath("tests/test_exposure_gate.py"),
    "save_path_test": PurePosixPath("tests/test_save_path.py"),
    "assay_power_test": PurePosixPath("tests/test_assay_power.py"),
    "clone_safety_test": PurePosixPath("tests/test_clone_safety.py"),
    "lineage_counts_schema": PurePosixPath(
        "schemas/track2_lineage_counts.schema.json"
    ),
    "clone_safety_schema": PurePosixPath(
        "schemas/track2_clone_safety.schema.json"
    ),
    "method_delta_schema": PurePosixPath(
        "schemas/track2_method_delta.schema.json"
    ),
    "candidate_ledger_schema": PurePosixPath(
        "schemas/track2_candidate_ledger.schema.json"
    ),
    # The community synthetic package is the dataset the gates were
    # exercised on — a swapped fixture after verification must fail.
    "template_readme": PurePosixPath("templates/community/README.md"),
    "template_allele_scorecard": PurePosixPath(
        "templates/community/allele_function_scorecard.synthetic.json"
    ),
    "template_assay_power_plan": PurePosixPath(
        "templates/community/assay_power.synthetic.json"
    ),
    "template_blinded_counts": PurePosixPath(
        "templates/community/blinded_count_table.synthetic.json"
    ),
    "template_causal_chain": PurePosixPath(
        "templates/community/causal_chain_worksheet.synthetic.json"
    ),
    "template_clone_safety": PurePosixPath(
        "templates/community/clone_safety_table.synthetic.json"
    ),
    "template_confirmation": PurePosixPath(
        "templates/community/confirmation_record.synthetic.json"
    ),
    "template_coordinate_model": PurePosixPath(
        "templates/community/coordinate_model.synthetic.pdb"
    ),
    "template_family_language": PurePosixPath(
        "templates/community/family_plain_language.synthetic.md"
    ),
    "template_lineage_counts": PurePosixPath(
        "templates/community/lineage_count_table.synthetic.json"
    ),
    "template_measured_exposure": PurePosixPath(
        "templates/community/measured_exposure_table.synthetic.json"
    ),
    "template_observed_inferred": PurePosixPath(
        "templates/community/observed_inferred_unknown.synthetic.json"
    ),
    "template_phase_record": PurePosixPath(
        "templates/community/phase_record.synthetic.json"
    ),
    "template_replication": PurePosixPath(
        "templates/community/replication_decision.synthetic.json"
    ),
    "template_structure_ranking": PurePosixPath(
        "templates/community/structure_ranking.synthetic.json"
    ),
    "template_transcript": PurePosixPath(
        "templates/community/transcript_record.synthetic.json"
    ),
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
# Byte ceilings — a manifest or artifact larger than this is rejected before
# parsing/hashing so a hostile payload cannot exhaust memory.
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024


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


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ReproducibilityError(f"non-finite JSON number: {value}")
    return parsed


def _load_json(data: bytes, label: str) -> tuple[Any | None, list[str]]:
    if len(data) > MAX_MANIFEST_BYTES:
        return None, [f"{label} exceeds the byte ceiling"]
    if data.startswith(b"\xef\xbb\xbf"):
        return None, [f"{label} must not contain a UTF-8 BOM"]
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ReproducibilityError) as exc:
        return None, [f"{label} is not strict duplicate-free UTF-8 JSON ({exc})"]
    except RecursionError:
        return None, [f"{label} JSON is nested too deeply"]
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
        if len(artifact_data) > MAX_ARTIFACT_BYTES:
            issues.append(f"{label} exceeds the artifact byte ceiling")
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
    def _norm_digest(value: Any) -> str:
        text = value if isinstance(value, str) else ""
        return text.removeprefix("sha256:").lower()

    if any(
        _norm_digest(runtime.get(key)) != _norm_digest(value)
        for key, value in expected_runtime_hashes.items()
    ):
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
                    passed = summary.get("passed")
                    total = summary.get("total")
                    if (
                        not isinstance(passed, int)
                        or isinstance(passed, bool)
                        or not isinstance(total, int)
                        or isinstance(total, bool)
                        or passed != scenario_count
                        or total != scenario_count
                        or summary.get("all_passed") is not True
                    ):
                        issues.append(
                            "benchmark did not pass every configured scenario"
                        )
                    receipt_scenarios = receipt.get("scenarios")
                    if not isinstance(receipt_scenarios, list):
                        issues.append(
                            "benchmark receipt lacks a scenario result list"
                        )
                    else:
                        if len(receipt_scenarios) != scenario_count:
                            issues.append(
                                "benchmark receipt scenario count differs from configuration"
                            )
                        row_passed = 0
                        receipt_names: set[object] = set()
                        for row in receipt_scenarios:
                            if not isinstance(row, Mapping):
                                issues.append(
                                    "benchmark receipt scenario row is not an object"
                                )
                                continue
                            receipt_names.add(row.get("name"))
                            if row.get("passed") is True:
                                row_passed += 1
                            else:
                                issues.append(
                                    "benchmark receipt scenario row did not pass"
                                )
                        config_names = {
                            item.get("name")
                            for item in scenarios
                            if isinstance(item, Mapping)
                        }
                        if isinstance(passed, int) and row_passed != passed:
                            issues.append(
                                "benchmark scenario rows disagree with the summary"
                            )
                        if (
                            receipt_names != config_names
                            or None in receipt_names
                        ):
                            issues.append(
                                "benchmark receipt scenario names differ from configuration"
                            )
                    replicates_reported = receipt.get(
                        "monte_carlo_replicates_per_scenario"
                    )
                    if (
                        not isinstance(replicates_reported, int)
                        or isinstance(replicates_reported, bool)
                        or replicates_reported != replicates
                    ):
                        issues.append(
                            "benchmark receipt replicate count differs from configuration"
                        )
                    comparisons_reported = receipt.get(
                        "total_simulated_vehicle_treatment_comparisons"
                    )
                    if (
                        not isinstance(comparisons_reported, int)
                        or isinstance(comparisons_reported, bool)
                        or comparisons_reported != comparison_count
                    ):
                        issues.append(
                            "benchmark receipt comparison count differs from configuration"
                        )

    def _nonfinite(value: object) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, float):
            return not math.isfinite(value)
        if isinstance(value, Mapping):
            return any(_nonfinite(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(_nonfinite(item) for item in value)
        return False

    if _nonfinite(summary):
        issues.append("benchmark summary contains a non-finite number")
    return issues


__all__ = [
    "ARTIFACT_PATHS",
    "COMMANDS",
    "MANIFEST_PATH",
    "SCHEMA",
    "validate_manifest_bytes",
]
