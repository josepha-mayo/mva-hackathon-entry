"""Freeze a complete, non-adaptive Track 1 submission plan.

The private v2 manifest binds submitted CSVs to the report, configuration,
code, references, benchmarks, calibration, raw inputs, ablation expectations,
and upload order that produced them. It permits independent methods to
converge on byte-identical CSVs, while allowing only one member of each
identical-output group to consume an upload slot.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from .submission import SubmissionError, load_predictions

SCHEMA_VERSION = "mva-track1-freeze/v2"
PUBLIC_COMMITMENT_SCHEMA = "mva-track1-public-commitments/v1"
COMMITMENT_SCHEME = "SHA256(nonce||bytes)"
REQUIRED_ARTIFACT_KINDS = ("report", "config", "code", "reference", "benchmark")
ABLATION_DIRECTIONS = frozenset({"higher", "lower", "no_change"})

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_POLICY = {
    "frozen_before_first_submission": True,
    "adaptive_leaderboard_revision_prohibited": True,
    "upload_order_is_fixed": True,
    "identical_csv_outputs_may_be_frozen": True,
    "duplicate_content_uploads_prohibited": True,
    "first_upload_is_predeclared_champion": True,
}


class FreezeError(ValueError):
    """Raised when a submission plan cannot be frozen or no longer verifies."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_prefixed(path: Path, prefix: bytes) -> str:
    digest = hashlib.sha256(prefix)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _text(value: object, label: str, *, minimum: int = 1, maximum: int = 2_000) -> str:
    if not isinstance(value, str):
        raise FreezeError(f"{label} must be text")
    cleaned = value.strip()
    if not minimum <= len(cleaned) <= maximum:
        raise FreezeError(f"{label} must contain {minimum} to {maximum} characters")
    if _CONTROL_CHARACTERS.search(cleaned):
        raise FreezeError(f"{label} contains control characters")
    return cleaned


def _commit(value: object) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value.lower()
    ):
        raise FreezeError("official Space commit must be a 40-character Git SHA")
    return value.lower()


def _utc_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise FreezeError("created_at_utc must be ISO 8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FreezeError("created_at_utc must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FreezeError("created_at_utc must use a UTC offset")
    return value


def _root(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise FreezeError(f"{label} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FreezeError(f"{label} does not exist") from exc
    if not resolved.is_dir():
        raise FreezeError(f"{label} must be a directory")
    return resolved


def _regular_file_under(path: Path, root: Path, label: str) -> tuple[Path, str]:
    lexical = Path(path)
    if not lexical.is_absolute():
        lexical = root / lexical
    if lexical.is_symlink():
        raise FreezeError(f"{label} must be a regular non-symlink file")
    try:
        resolved = lexical.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise FreezeError(f"{label} must remain inside its declared root") from exc
    if not resolved.is_file():
        raise FreezeError(f"{label} must be a regular non-symlink file")
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise FreezeError(f"{label} must not traverse a symlink")
    return resolved, relative.as_posix()


def _manifest_relative_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise FreezeError(f"{label} is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FreezeError(f"{label} is not a safe relative path")
    if ":" in path.parts[0]:
        raise FreezeError(f"{label} is not a safe relative path")
    return path


def _manifest_file(root: Path, value: object, label: str) -> tuple[Path, str]:
    relative = _manifest_relative_path(value, label)
    return _regular_file_under(Path(*relative.parts), root, label)


def _valid_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_SHA256.fullmatch(value):
        raise FreezeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _artifact_entries(
    artifact_paths: Mapping[str, Sequence[Path]], artifact_root: Path
) -> dict[str, list[dict[str, object]]]:
    if not isinstance(artifact_paths, Mapping):
        raise FreezeError("artifacts must map each required kind to files")
    supplied = set(artifact_paths)
    required = set(REQUIRED_ARTIFACT_KINDS)
    if supplied != required:
        raise FreezeError(
            "artifacts must contain exactly report, config, code, reference, and benchmark; "
            f"missing={sorted(required - supplied)}, unexpected={sorted(supplied - required)}"
        )

    seen_paths: set[str] = set()
    result: dict[str, list[dict[str, object]]] = {}
    for kind in REQUIRED_ARTIFACT_KINDS:
        paths = artifact_paths[kind]
        if isinstance(paths, (str, bytes, Path)) or not isinstance(paths, Sequence) or not paths:
            raise FreezeError(f"artifact kind {kind} must contain at least one file")
        entries: list[dict[str, object]] = []
        for index, path in enumerate(paths, start=1):
            resolved, relative = _regular_file_under(
                Path(path), artifact_root, f"{kind} artifact {index}"
            )
            key = relative.casefold()
            if key in seen_paths:
                raise FreezeError("one evidence file cannot occupy multiple artifact roles")
            seen_paths.add(key)
            entries.append(
                {
                    "path": relative,
                    "sha256": _sha256(resolved),
                    "size_bytes": resolved.stat().st_size,
                }
            )
        result[kind] = sorted(entries, key=lambda entry: str(entry["path"]).casefold())
    return result


def _calibration_identity(
    calibration: Mapping[str, str],
    artifacts_by_path: Mapping[str, tuple[str, Mapping[str, object]]],
    method_id: str,
) -> dict[str, object]:
    if not isinstance(calibration, Mapping):
        raise FreezeError("calibration must be a mapping")
    required = {"calibration_id", "method", "config_artifact", "benchmark_artifact"}
    if set(calibration) != required:
        raise FreezeError(f"calibration must contain exactly {sorted(required)}")

    calibration_id = _text(
        calibration["calibration_id"], "calibration_id", maximum=128
    )
    if not _SAFE_ID.fullmatch(calibration_id):
        raise FreezeError("calibration_id contains unsafe characters")
    method = _text(calibration["method"], "calibration method", minimum=3, maximum=256)
    config_path = _manifest_relative_path(
        calibration["config_artifact"], "calibration config_artifact"
    ).as_posix()
    benchmark_path = _manifest_relative_path(
        calibration["benchmark_artifact"], "calibration benchmark_artifact"
    ).as_posix()

    config = artifacts_by_path.get(config_path.casefold())
    benchmark = artifacts_by_path.get(benchmark_path.casefold())
    if config is None or config[0] != "config":
        raise FreezeError("calibration config_artifact must name a frozen config artifact")
    if benchmark is None or benchmark[0] != "benchmark":
        raise FreezeError(
            "calibration benchmark_artifact must name a frozen benchmark artifact"
        )

    identity = {
        "method_id": method_id,
        "calibration_id": calibration_id,
        "method": method,
        "config_artifact": {
            "path": str(config[1]["path"]),
            "sha256": str(config[1]["sha256"]),
        },
        "benchmark_artifact": {
            "path": str(benchmark[1]["path"]),
            "sha256": str(benchmark[1]["sha256"]),
        },
    }
    return {**identity, "identity_sha256": _canonical_sha256(identity)}


def _expected_ablations(
    ablations: Sequence[Mapping[str, str]],
    submissions_by_name: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    if isinstance(ablations, (str, bytes)) or not isinstance(ablations, Sequence):
        raise FreezeError("expected_ablations must be a sequence")
    if len(ablations) > 64:
        raise FreezeError("at most 64 expected ablations may be frozen")

    required = {
        "ablation_id",
        "baseline",
        "variant",
        "metric",
        "expected_direction",
        "rationale",
    }
    seen_ids: set[str] = set()
    normalized: list[dict[str, object]] = []
    for index, record in enumerate(ablations, start=1):
        if not isinstance(record, Mapping) or set(record) != required:
            raise FreezeError(f"ablation {index} must contain exactly {sorted(required)}")
        ablation_id = _text(record["ablation_id"], f"ablation {index} id", maximum=128)
        if not _SAFE_ID.fullmatch(ablation_id) or ablation_id.casefold() in seen_ids:
            raise FreezeError(f"ablation {index} has an unsafe or duplicate id")
        seen_ids.add(ablation_id.casefold())
        baseline = _text(record["baseline"], f"ablation {index} baseline", maximum=255)
        variant = _text(record["variant"], f"ablation {index} variant", maximum=255)
        if baseline == variant:
            raise FreezeError(f"ablation {index} baseline and variant must differ")
        if baseline not in submissions_by_name or variant not in submissions_by_name:
            raise FreezeError(f"ablation {index} references an unknown frozen submission")
        direction = _text(
            record["expected_direction"],
            f"ablation {index} expected_direction",
            maximum=16,
        )
        if direction not in ABLATION_DIRECTIONS:
            raise FreezeError(
                f"ablation {index} expected_direction must be higher, lower, or no_change"
            )
        outputs_converged = (
            submissions_by_name[baseline]["sha256"]
            == submissions_by_name[variant]["sha256"]
        )
        if outputs_converged and direction != "no_change":
            raise FreezeError(
                f"ablation {index} has identical outputs and therefore must expect no_change"
            )
        normalized.append(
            {
                "ablation_id": ablation_id,
                "baseline": baseline,
                "variant": variant,
                "metric": _text(
                    record["metric"], f"ablation {index} metric", maximum=128
                ),
                "expected_direction": direction,
                "rationale": _text(
                    record["rationale"],
                    f"ablation {index} rationale",
                    minimum=20,
                    maximum=2_000,
                ),
                "outputs_converged": outputs_converged,
            }
        )
    return normalized


def _private_raw_entries(
    private_raw_paths: Mapping[str, Path],
    private_raw_root: Path,
    public_commitment_nonces: Mapping[str, bytes],
) -> list[dict[str, object]]:
    if not isinstance(private_raw_paths, Mapping) or not private_raw_paths:
        raise FreezeError("at least one private raw artifact must be frozen")
    if not isinstance(public_commitment_nonces, Mapping):
        raise FreezeError("public_commitment_nonces must be a mapping")
    unknown_nonce_ids = set(public_commitment_nonces) - set(private_raw_paths)
    if unknown_nonce_ids:
        raise FreezeError(
            f"commitment nonce supplied for unknown raw artifact ids: {sorted(unknown_nonce_ids)}"
        )

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_nonces: set[bytes] = set()
    result: list[dict[str, object]] = []
    for artifact_id, path in sorted(
        private_raw_paths.items(), key=lambda item: str(item[0]).casefold()
    ):
        if not isinstance(artifact_id, str) or not _SAFE_ID.fullmatch(artifact_id):
            raise FreezeError("private raw artifact ids must be public-safe identifiers")
        if artifact_id.casefold() in seen_ids:
            raise FreezeError("private raw artifact ids must be unique ignoring case")
        seen_ids.add(artifact_id.casefold())
        resolved, relative = _regular_file_under(
            Path(path), private_raw_root, f"private raw artifact {artifact_id}"
        )
        if relative.casefold() in seen_paths:
            raise FreezeError("one private raw file cannot occupy multiple artifact ids")
        seen_paths.add(relative.casefold())
        entry: dict[str, object] = {
            "artifact_id": artifact_id,
            "path": relative,
            "size_bytes": resolved.stat().st_size,
            "private_sha256": _sha256(resolved),
        }
        if artifact_id in public_commitment_nonces:
            nonce = public_commitment_nonces[artifact_id]
            if not isinstance(nonce, bytes) or not 16 <= len(nonce) <= 64:
                raise FreezeError(
                    f"commitment nonce for {artifact_id} must be 16 to 64 bytes"
                )
            if nonce in seen_nonces:
                raise FreezeError("each public commitment must use a unique nonce")
            seen_nonces.add(nonce)
            entry["private_commitment_nonce_hex"] = nonce.hex()
            entry["public_commitment"] = {
                "scheme": COMMITMENT_SCHEME,
                "digest": _sha256_prefixed(resolved, nonce),
            }
        result.append(entry)
    return result


def build_manifest(
    csv_paths: Sequence[Path],
    rationales: Mapping[str, str],
    *,
    official_space_commit: str,
    created_at_utc: str,
    artifact_root: Path,
    artifacts: Mapping[str, Sequence[Path]],
    expected_ablations: Sequence[Mapping[str, str]],
    method_ids: Mapping[str, str],
    calibrations: Mapping[str, Mapping[str, str]],
    champion_method_id: str,
    upload_order: Sequence[str],
    private_raw_root: Path,
    private_raw_paths: Mapping[str, Path],
    public_commitment_nonces: Mapping[str, bytes] | None = None,
) -> dict[str, object]:
    """Build a complete private v2 freeze manifest without copying any files."""

    if isinstance(csv_paths, (str, bytes, Path)) or not isinstance(csv_paths, Sequence):
        raise FreezeError("csv_paths must be a sequence")
    if not 1 <= len(csv_paths) <= 6:
        raise FreezeError("freeze set must contain between one and six CSV files")
    if not isinstance(rationales, Mapping):
        raise FreezeError("rationales must be a mapping")
    if not isinstance(method_ids, Mapping):
        raise FreezeError("method_ids must map every frozen filename to a method id")
    if not isinstance(calibrations, Mapping):
        raise FreezeError("calibrations must map every method id to its fitted identity")
    public_root = _root(Path(artifact_root), "artifact_root")
    raw_root = _root(Path(private_raw_root), "private_raw_root")

    evidence = _artifact_entries(artifacts, public_root)
    evidence_paths = {
        str(entry["path"]).casefold()
        for entries in evidence.values()
        for entry in entries
    }
    artifacts_by_path = {
        str(entry["path"]).casefold(): (kind, entry)
        for kind, entries in evidence.items()
        for entry in entries
    }

    resolved_csvs: list[tuple[Path, str]] = []
    seen_filenames: set[str] = set()
    seen_paths: set[str] = set()
    for slot, path in enumerate(csv_paths, start=1):
        resolved, relative = _regular_file_under(
            Path(path), public_root, f"submission slot {slot}"
        )
        if resolved.suffix.lower() != ".csv":
            raise FreezeError(f"slot {slot}: expected a CSV file")
        if resolved.name.casefold() in seen_filenames:
            raise FreezeError("submission filenames must be unique ignoring case")
        if relative.casefold() in seen_paths:
            raise FreezeError("the same submission file cannot occupy two freeze slots")
        if relative.casefold() in evidence_paths:
            raise FreezeError("a submission CSV cannot also occupy an evidence-artifact role")
        seen_filenames.add(resolved.name.casefold())
        seen_paths.add(relative.casefold())
        resolved_csvs.append((resolved, relative))

    filenames = [path.name for path, _ in resolved_csvs]
    if set(method_ids) != set(filenames):
        raise FreezeError(
            "method_ids must contain exactly one entry for every frozen submission filename"
        )
    normalized_method_ids: dict[str, str] = {}
    seen_method_ids: set[str] = set()
    for filename in filenames:
        method_id = _text(
            method_ids[filename], f"method id for {filename}", maximum=128
        )
        if not _SAFE_ID.fullmatch(method_id) or method_id.casefold() in seen_method_ids:
            raise FreezeError("method ids must be public-safe and unique ignoring case")
        seen_method_ids.add(method_id.casefold())
        normalized_method_ids[filename] = method_id

    champion = _text(champion_method_id, "champion_method_id", maximum=128)
    if not _SAFE_ID.fullmatch(champion) or champion not in normalized_method_ids.values():
        raise FreezeError("champion_method_id must name exactly one frozen method")
    if set(calibrations) != set(normalized_method_ids.values()):
        raise FreezeError(
            "calibrations must contain exactly one fitted identity for every frozen method id"
        )

    entries: list[dict[str, object]] = []
    for slot, (path, relative) in enumerate(resolved_csvs, start=1):
        rationale_value = rationales.get(relative, rationales.get(path.name, ""))
        rationale = _text(
            rationale_value,
            f"slot {slot} rationale",
            minimum=20,
            maximum=2_000,
        )
        try:
            predictions = load_predictions(path)
        except SubmissionError as exc:
            raise FreezeError(f"slot {slot}: submission validation failed: {exc}") from exc
        entries.append(
            {
                "freeze_slot": slot,
                "path": relative,
                "filename": path.name,
                "method_id": normalized_method_ids[path.name],
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "candidate_rows": len(predictions),
                "method_rationale": rationale,
            }
        )

    if isinstance(upload_order, (str, bytes)) or not isinstance(upload_order, Sequence):
        raise FreezeError("upload_order must be a sequence of frozen filenames")
    order = list(upload_order)
    if not all(isinstance(name, str) for name in order):
        raise FreezeError("upload_order must contain filenames")
    by_name = {str(entry["filename"]): entry for entry in entries}
    if len(order) != len(set(order)) or any(name not in by_name for name in order):
        raise FreezeError("upload_order contains a duplicate or unknown filename")
    unique_hashes = {str(entry["sha256"]) for entry in entries}
    ordered_hashes = [str(by_name[name]["sha256"]) for name in order]
    if len(ordered_hashes) != len(set(ordered_hashes)):
        raise FreezeError("upload_order would waste a slot on byte-identical CSV content")
    if set(ordered_hashes) != unique_hashes:
        raise FreezeError(
            "upload_order must contain exactly one representative of every distinct CSV output"
        )
    if not order or by_name[order[0]]["method_id"] != champion:
        raise FreezeError(
            "upload_order must start with the explicitly predeclared champion method"
        )

    calibration_records: list[dict[str, object]] = []
    seen_calibration_ids: set[str] = set()
    for entry in entries:
        method_id = str(entry["method_id"])
        identity = _calibration_identity(
            calibrations[method_id], artifacts_by_path, method_id
        )
        calibration_id_key = str(identity["calibration_id"]).casefold()
        if calibration_id_key in seen_calibration_ids:
            raise FreezeError("each frozen method must have a unique calibration_id")
        seen_calibration_ids.add(calibration_id_key)
        entry["calibration_identity_sha256"] = identity["identity_sha256"]
        calibration_records.append(
            {
                "freeze_slot": entry["freeze_slot"],
                "filename": entry["filename"],
                **identity,
            }
        )

    representative_by_hash = {
        str(by_name[name]["sha256"]): name for name in order
    }
    upload_slot_by_name = {name: slot for slot, name in enumerate(order, start=1)}
    members_by_hash: dict[str, list[str]] = {}
    for entry in entries:
        members_by_hash.setdefault(str(entry["sha256"]), []).append(str(entry["filename"]))
    for entry in entries:
        digest = str(entry["sha256"])
        filename = str(entry["filename"])
        entry.update(
            {
                "convergence_group": f"sha256:{digest}",
                "converged_output": len(members_by_hash[digest]) > 1,
                "upload_representative": representative_by_hash[digest] == filename,
                "upload_slot": upload_slot_by_name.get(filename),
            }
        )

    convergence_groups = [
        {
            "convergence_group": f"sha256:{digest}",
            "members": members,
            "upload_representative": representative_by_hash[digest],
            "upload_representative_method_id": by_name[
                representative_by_hash[digest]
            ]["method_id"],
        }
        for digest, members in members_by_hash.items()
        if len(members) > 1
    ]
    upload_plan = [
        {
            "upload_slot": slot,
            "filename": name,
            "method_id": by_name[name]["method_id"],
            "sha256": str(by_name[name]["sha256"]),
        }
        for slot, name in enumerate(order, start=1)
    ]

    ablations = _expected_ablations(expected_ablations, by_name)
    private_raw = _private_raw_entries(
        private_raw_paths,
        raw_root,
        public_commitment_nonces or {},
    )

    return {
        "schema": SCHEMA_VERSION,
        "created_at_utc": _utc_timestamp(created_at_utc),
        "official_space_commit": _commit(official_space_commit),
        "policy": dict(_POLICY),
        "champion_method_id": champion,
        "artifacts": evidence,
        "private_raw_artifacts": private_raw,
        "calibrations": calibration_records,
        "expected_ablations": ablations,
        "submissions": entries,
        "convergence_groups": convergence_groups,
        "upload_order": upload_plan,
    }


def build_public_commitment_manifest(
    private_manifest: Mapping[str, object],
) -> dict[str, object]:
    """Return a safe projection containing commitments, never raw hashes or nonces."""

    if not isinstance(private_manifest, Mapping) or private_manifest.get("schema") != SCHEMA_VERSION:
        raise FreezeError("unsupported freeze-manifest schema")
    created_at = _utc_timestamp(private_manifest.get("created_at_utc"))
    commit = _commit(private_manifest.get("official_space_commit"))
    raw_entries = private_manifest.get("private_raw_artifacts")
    if not isinstance(raw_entries, list):
        raise FreezeError("freeze manifest has an invalid private raw-artifact list")

    commitments: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, Mapping):
            raise FreezeError(f"private raw artifact {index} is malformed")
        artifact_id = entry.get("artifact_id")
        if (
            not isinstance(artifact_id, str)
            or not _SAFE_ID.fullmatch(artifact_id)
            or artifact_id.casefold() in seen_ids
        ):
            raise FreezeError("private raw artifact ids are unsafe or duplicated")
        seen_ids.add(artifact_id.casefold())
        commitment = entry.get("public_commitment")
        if commitment is None:
            continue
        if (
            not isinstance(commitment, Mapping)
            or commitment.get("scheme") != COMMITMENT_SCHEME
        ):
            raise FreezeError(f"public commitment for {artifact_id} is malformed")
        digest = _valid_sha256(
            commitment.get("digest"), f"public commitment for {artifact_id}"
        )
        commitments.append(
            {
                "artifact_id": artifact_id,
                "scheme": COMMITMENT_SCHEME,
                "digest": digest,
            }
        )

    return {
        "schema": PUBLIC_COMMITMENT_SCHEMA,
        "created_at_utc": created_at,
        "official_space_commit": commit,
        "commitments": commitments,
    }


def write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    """Write a new manifest atomically and refuse to overwrite a prior freeze."""

    if manifest.get("schema") != SCHEMA_VERSION:
        raise FreezeError("refusing to write an unsupported freeze-manifest schema")
    path = path.resolve()
    if path.exists():
        raise FreezeError("freeze manifest already exists; refusing to overwrite it")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _verify_file_entry(
    entry: object, root: Path, label: str, *, private_hash: bool = False
) -> tuple[str, str]:
    required = {"path", "size_bytes", "private_sha256" if private_hash else "sha256"}
    if not isinstance(entry, Mapping) or set(entry) != required:
        raise FreezeError(f"{label} is malformed")
    path, relative = _manifest_file(root, entry["path"], label)
    size = entry["size_bytes"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise FreezeError(f"{label} has an invalid byte size")
    if path.stat().st_size != size:
        raise FreezeError(f"{label} byte size changed")
    hash_key = "private_sha256" if private_hash else "sha256"
    digest = _valid_sha256(entry[hash_key], f"{label} hash")
    if _sha256(path) != digest:
        raise FreezeError(f"{label} hash changed")
    return relative, digest


def verify_manifest(
    path: Path,
    artifact_root: Path,
    *,
    private_raw_root: Path | None = None,
) -> None:
    """Verify every v2 binding, including private raw bytes and upload policy."""

    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, json.JSONDecodeError, UnicodeError, _DuplicateJsonKey) as exc:
        raise FreezeError("freeze manifest is unreadable") from exc
    if not isinstance(manifest, Mapping) or manifest.get("schema") != SCHEMA_VERSION:
        raise FreezeError("unsupported freeze-manifest schema")
    _utc_timestamp(manifest.get("created_at_utc"))
    _commit(manifest.get("official_space_commit"))
    if manifest.get("policy") != _POLICY:
        raise FreezeError("freeze manifest policy is missing or changed")

    public_root = _root(Path(artifact_root), "artifact_root")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(REQUIRED_ARTIFACT_KINDS):
        raise FreezeError("freeze manifest has an invalid evidence-artifact map")
    seen_public_paths: set[str] = set()
    artifacts_by_path: dict[str, tuple[str, Mapping[str, object]]] = {}
    for kind in REQUIRED_ARTIFACT_KINDS:
        entries = artifacts[kind]
        if not isinstance(entries, list) or not entries:
            raise FreezeError(f"artifact kind {kind} must contain at least one file")
        stored_paths: list[str] = []
        for index, entry in enumerate(entries, start=1):
            relative, _ = _verify_file_entry(
                entry, public_root, f"{kind} artifact {index}"
            )
            key = relative.casefold()
            if key in seen_public_paths:
                raise FreezeError("one public file occupies multiple frozen roles")
            seen_public_paths.add(key)
            stored_paths.append(relative)
            artifacts_by_path[key] = (kind, entry)
        if stored_paths != sorted(stored_paths, key=str.casefold):
            raise FreezeError(f"artifact kind {kind} is not in canonical path order")

    submissions = manifest.get("submissions")
    if not isinstance(submissions, list) or not 1 <= len(submissions) <= 6:
        raise FreezeError("freeze manifest has an invalid submission list")
    submission_keys = {
        "freeze_slot",
        "path",
        "filename",
        "method_id",
        "calibration_identity_sha256",
        "sha256",
        "size_bytes",
        "candidate_rows",
        "method_rationale",
        "convergence_group",
        "converged_output",
        "upload_representative",
        "upload_slot",
    }
    by_name: dict[str, Mapping[str, object]] = {}
    by_method: dict[str, Mapping[str, object]] = {}
    seen_method_ids: set[str] = set()
    seen_submission_paths: set[str] = set()
    for expected_slot, entry in enumerate(submissions, start=1):
        if (
            not isinstance(entry, Mapping)
            or set(entry) != submission_keys
            or entry.get("freeze_slot") != expected_slot
        ):
            raise FreezeError("freeze manifest submission slots are malformed")
        candidate, relative = _manifest_file(
            public_root, entry["path"], f"submission slot {expected_slot}"
        )
        filename = entry["filename"]
        if (
            not isinstance(filename, str)
            or candidate.suffix.lower() != ".csv"
            or candidate.name != filename
            or filename in by_name
        ):
            raise FreezeError(f"slot {expected_slot}: frozen CSV name is malformed")
        if relative.casefold() in seen_public_paths or relative.casefold() in seen_submission_paths:
            raise FreezeError("one public file occupies multiple frozen roles")
        seen_submission_paths.add(relative.casefold())
        digest = _valid_sha256(entry["sha256"], f"slot {expected_slot} CSV hash")
        if _sha256(candidate) != digest:
            raise FreezeError(f"slot {expected_slot}: frozen CSV hash changed")
        size = entry["size_bytes"]
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or candidate.stat().st_size != size
        ):
            raise FreezeError(f"slot {expected_slot}: frozen CSV byte size changed")
        try:
            predictions = load_predictions(candidate)
        except SubmissionError as exc:
            raise FreezeError(
                f"slot {expected_slot}: frozen CSV no longer validates"
            ) from exc
        if len(predictions) != entry["candidate_rows"]:
            raise FreezeError(f"slot {expected_slot}: candidate-row count changed")
        _text(
            entry["method_rationale"],
            f"slot {expected_slot} rationale",
            minimum=20,
            maximum=2_000,
        )
        method_id = _text(
            entry["method_id"], f"slot {expected_slot} method_id", maximum=128
        )
        if not _SAFE_ID.fullmatch(method_id) or method_id.casefold() in seen_method_ids:
            raise FreezeError("frozen method ids are unsafe or duplicated")
        seen_method_ids.add(method_id.casefold())
        _valid_sha256(
            entry["calibration_identity_sha256"],
            f"slot {expected_slot} calibration identity",
        )
        by_name[filename] = entry
        by_method[method_id] = entry

    champion = manifest.get("champion_method_id")
    if (
        not isinstance(champion, str)
        or not _SAFE_ID.fullmatch(champion)
        or champion not in by_method
    ):
        raise FreezeError("champion_method_id does not name a frozen method")

    upload_order = manifest.get("upload_order")
    if not isinstance(upload_order, list):
        raise FreezeError("freeze manifest has an invalid upload order")
    unique_hashes = {str(entry["sha256"]) for entry in submissions}
    if len(upload_order) != len(unique_hashes):
        raise FreezeError("upload order must use exactly one slot per distinct CSV output")
    representative_by_hash: dict[str, str] = {}
    upload_slot_by_name: dict[str, int] = {}
    for expected_slot, upload in enumerate(upload_order, start=1):
        if (
            not isinstance(upload, Mapping)
            or set(upload) != {"upload_slot", "filename", "method_id", "sha256"}
            or upload.get("upload_slot") != expected_slot
        ):
            raise FreezeError("upload order is malformed")
        filename = upload.get("filename")
        if not isinstance(filename, str) or filename not in by_name:
            raise FreezeError("upload order references an unknown submission")
        if upload.get("method_id") != by_name[filename]["method_id"]:
            raise FreezeError("upload order has a mismatched method id")
        digest = _valid_sha256(upload.get("sha256"), "upload-order hash")
        if digest != by_name[filename]["sha256"]:
            raise FreezeError("upload-order hash does not match its frozen CSV")
        if digest in representative_by_hash or filename in upload_slot_by_name:
            raise FreezeError("upload order wastes a slot on duplicate CSV content")
        representative_by_hash[digest] = filename
        upload_slot_by_name[filename] = expected_slot
    if set(representative_by_hash) != unique_hashes:
        raise FreezeError("upload order omits a distinct CSV output")
    if not upload_order or upload_order[0]["method_id"] != champion:
        raise FreezeError("upload order does not start with the predeclared champion")

    members_by_hash: dict[str, list[str]] = {}
    for entry in submissions:
        members_by_hash.setdefault(str(entry["sha256"]), []).append(str(entry["filename"]))
    for entry in submissions:
        digest = str(entry["sha256"])
        filename = str(entry["filename"])
        expected = {
            "convergence_group": f"sha256:{digest}",
            "converged_output": len(members_by_hash[digest]) > 1,
            "upload_representative": representative_by_hash[digest] == filename,
            "upload_slot": upload_slot_by_name.get(filename),
        }
        if any(entry[key] != value for key, value in expected.items()):
            raise FreezeError("submission convergence or upload annotations changed")
    expected_groups = [
        {
            "convergence_group": f"sha256:{digest}",
            "members": members,
            "upload_representative": representative_by_hash[digest],
            "upload_representative_method_id": by_name[
                representative_by_hash[digest]
            ]["method_id"],
        }
        for digest, members in members_by_hash.items()
        if len(members) > 1
    ]
    if manifest.get("convergence_groups") != expected_groups:
        raise FreezeError("convergence groups are malformed")

    stored_ablations = manifest.get("expected_ablations")
    if not isinstance(stored_ablations, list):
        raise FreezeError("expected ablations are malformed")
    ablation_core: list[dict[str, str]] = []
    core_keys = {
        "ablation_id",
        "baseline",
        "variant",
        "metric",
        "expected_direction",
        "rationale",
    }
    for entry in stored_ablations:
        if not isinstance(entry, Mapping) or set(entry) != core_keys | {"outputs_converged"}:
            raise FreezeError("expected ablations are malformed")
        ablation_core.append({key: entry[key] for key in core_keys})  # type: ignore[misc]
    if _expected_ablations(ablation_core, by_name) != stored_ablations:
        raise FreezeError("expected ablation directions or convergence markers changed")

    stored_calibrations = manifest.get("calibrations")
    if not isinstance(stored_calibrations, list) or len(stored_calibrations) != len(
        submissions
    ):
        raise FreezeError("per-submission calibration identities are malformed")
    seen_calibration_ids: set[str] = set()
    for expected_slot, stored in enumerate(stored_calibrations, start=1):
        if not isinstance(stored, Mapping):
            raise FreezeError("per-submission calibration identities are malformed")
        submission = submissions[expected_slot - 1]
        try:
            calibration_core = {
                "calibration_id": stored["calibration_id"],
                "method": stored["method"],
                "config_artifact": stored["config_artifact"]["path"],  # type: ignore[index]
                "benchmark_artifact": stored["benchmark_artifact"]["path"],  # type: ignore[index]
            }
            expected_identity = _calibration_identity(
                calibration_core,
                artifacts_by_path,
                str(submission["method_id"]),
            )
        except (KeyError, TypeError):
            raise FreezeError("per-submission calibration identity is malformed") from None
        calibration_id_key = str(expected_identity["calibration_id"]).casefold()
        if calibration_id_key in seen_calibration_ids:
            raise FreezeError("per-submission calibration ids are duplicated")
        seen_calibration_ids.add(calibration_id_key)
        expected_record = {
            "freeze_slot": expected_slot,
            "filename": submission["filename"],
            **expected_identity,
        }
        if stored != expected_record:
            raise FreezeError("per-submission calibration identity changed")
        if submission["calibration_identity_sha256"] != expected_identity["identity_sha256"]:
            raise FreezeError("submission calibration-identity link changed")

    raw_entries = manifest.get("private_raw_artifacts")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise FreezeError("freeze manifest must contain private raw-artifact hashes")
    if private_raw_root is None:
        raise FreezeError("private_raw_root is required to verify private raw artifacts")
    raw_root = _root(Path(private_raw_root), "private_raw_root")
    seen_raw_ids: set[str] = set()
    seen_raw_paths: set[str] = set()
    seen_nonces: set[bytes] = set()
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, Mapping):
            raise FreezeError(f"private raw artifact {index} is malformed")
        base_keys = {"artifact_id", "path", "size_bytes", "private_sha256"}
        has_commitment = "public_commitment" in entry or "private_commitment_nonce_hex" in entry
        expected_keys = base_keys | (
            {"public_commitment", "private_commitment_nonce_hex"} if has_commitment else set()
        )
        if set(entry) != expected_keys:
            raise FreezeError(f"private raw artifact {index} is malformed")
        artifact_id = entry["artifact_id"]
        if (
            not isinstance(artifact_id, str)
            or not _SAFE_ID.fullmatch(artifact_id)
            or artifact_id.casefold() in seen_raw_ids
        ):
            raise FreezeError("private raw artifact ids are unsafe or duplicated")
        seen_raw_ids.add(artifact_id.casefold())
        relative, _ = _verify_file_entry(
            {key: entry[key] for key in base_keys - {"artifact_id"}},
            raw_root,
            f"private raw artifact {artifact_id}",
            private_hash=True,
        )
        if relative.casefold() in seen_raw_paths:
            raise FreezeError("one private raw file occupies multiple artifact ids")
        seen_raw_paths.add(relative.casefold())
        if has_commitment:
            nonce_hex = entry["private_commitment_nonce_hex"]
            if not isinstance(nonce_hex, str) or len(nonce_hex) % 2:
                raise FreezeError(f"private commitment nonce for {artifact_id} is malformed")
            try:
                nonce = bytes.fromhex(nonce_hex)
            except ValueError as exc:
                raise FreezeError(
                    f"private commitment nonce for {artifact_id} is malformed"
                ) from exc
            if nonce.hex() != nonce_hex or not 16 <= len(nonce) <= 64 or nonce in seen_nonces:
                raise FreezeError(
                    f"private commitment nonce for {artifact_id} is unsafe or reused"
                )
            seen_nonces.add(nonce)
            commitment = entry["public_commitment"]
            if (
                not isinstance(commitment, Mapping)
                or set(commitment) != {"scheme", "digest"}
                or commitment.get("scheme") != COMMITMENT_SCHEME
            ):
                raise FreezeError(f"public commitment for {artifact_id} is malformed")
            digest = _valid_sha256(
                commitment.get("digest"), f"public commitment for {artifact_id}"
            )
            raw_path, _ = _manifest_file(
                raw_root, entry["path"], f"private raw artifact {artifact_id}"
            )
            if _sha256_prefixed(raw_path, nonce) != digest:
                raise FreezeError(f"public commitment for {artifact_id} changed")


__all__ = [
    "ABLATION_DIRECTIONS",
    "COMMITMENT_SCHEME",
    "FreezeError",
    "PUBLIC_COMMITMENT_SCHEMA",
    "REQUIRED_ARTIFACT_KINDS",
    "SCHEMA_VERSION",
    "build_manifest",
    "build_public_commitment_manifest",
    "verify_manifest",
    "write_manifest",
]
