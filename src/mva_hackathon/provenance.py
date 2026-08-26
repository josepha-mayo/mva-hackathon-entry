"""Deterministic, privacy-aware provenance primitives.

This module deliberately does not discover, open, or hash input files.  Callers
must calculate private file digests inside the controlled environment and pass
only the resulting digest strings to the private stage-record APIs.  The public
manifest API is a separate, allowlisted schema with conservative leak checks.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, Iterable, Literal, Mapping, Sequence


STAGE_SCHEMA = "mva.stage/v1"
PUBLIC_MANIFEST_SCHEMA = "mva.public-provenance/v1"
PRIVATE_MANIFEST_SCHEMA = "mva.private-provenance/v1"
MAX_STAGE_RECORD_BYTES = 1024 * 1024

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_DIGEST_TOKEN = re.compile(r"(?i)(?<![0-9a-f])(?:sha256:)?[0-9a-f]{64}(?![0-9a-f])")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_STAGE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_CONTROLLED_FILENAME = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]+\."
    r"(?:bam|bai|bcf|bed|crai|cram|csi|dcm|dicom|fam|fastq(?:\.gz)?|"
    r"fq(?:\.gz)?|g\.vcf(?:\.gz)?|gvcf(?:\.gz)?|h5|h5ad|hdf5|mt|"
    r"docx|parquet|ped|pgen|phenopacket\.json|psam|pvar|sam|tbi|vcf(?:\.gz|\.bgz)?)"
    r"(?![A-Za-z0-9_.-])"
)
_PRIVATE_FIELD_NAMES = {
    "command",
    "commands",
    "controlled",
    "controlled_inputs",
    "exact_command",
    "input",
    "input_digest",
    "input_digests",
    "inputs",
    "path",
    "paths",
    "phenotype",
    "private",
    "proband_id",
    "sample_id",
    "source_filename",
    "stage_records",
}


class ProvenanceError(ValueError):
    """Raised when provenance does not satisfy its fail-closed schema."""


class ResumeValidationError(ProvenanceError):
    """Raised when an existing stage cannot safely be resumed."""


class PublicManifestError(ProvenanceError):
    """Raised when a value is unsafe for the public provenance manifest."""


def _normalise_json(value: Any, *, location: str = "$") -> Any:
    """Return a canonical JSON-domain value or reject ambiguous input."""

    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProvenanceError(f"{location}: non-finite numbers are not canonical JSON")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise ProvenanceError(f"{location}: JSON object keys must be strings")
            key = unicodedata.normalize("NFC", raw_key)
            if key in result:
                raise ProvenanceError(
                    f"{location}: object keys collide after Unicode normalisation: {key!r}"
                )
            result[key] = _normalise_json(raw_value, location=f"{location}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _normalise_json(item, location=f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ProvenanceError(
        f"{location}: {type(value).__name__} is outside the canonical JSON domain"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-domain value deterministically.

    Mapping insertion order and insignificant JSON whitespace do not affect the
    result.  Array order and scalar values do affect it.  Strings and keys are
    normalised to Unicode NFC before serialization.
    """

    normalised = _normalise_json(value)
    return json.dumps(
        normalised,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def semantic_digest(value: Any) -> str:
    """Return a lower-case, algorithm-labelled SHA-256 semantic digest."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_digest(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ProvenanceError(
            f"{location}: digest must be lower-case sha256 followed by 64 hex characters"
        )
    return value


def _require_safe_name(value: Any, *, location: str, stage: bool = False) -> str:
    pattern = _STAGE_NAME if stage else _SAFE_NAME
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ProvenanceError(f"{location}: invalid name")
    return value


def _require_text(value: Any, *, location: str, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise ProvenanceError(f"{location}: expected text")
    value = unicodedata.normalize("NFC", value)
    if nonempty and not value:
        raise ProvenanceError(f"{location}: text must not be empty")
    if _CONTROL_CHARACTERS.search(value):
        raise ProvenanceError(f"{location}: control characters are forbidden")
    return value


def _digest_map(
    values: Any,
    *,
    location: str,
    allow_empty: bool = False,
) -> Mapping[str, str]:
    if not isinstance(values, Mapping):
        raise ProvenanceError(f"{location}: expected a digest mapping")
    if not values and not allow_empty:
        raise ProvenanceError(f"{location}: at least one digest is required")
    result: dict[str, str] = {}
    for raw_name, raw_digest in values.items():
        name = _require_safe_name(raw_name, location=f"{location} key")
        result[name] = _require_digest(raw_digest, location=f"{location}.{name}")
    return MappingProxyType(dict(sorted(result.items())))


@dataclass(frozen=True)
class StageDigests:
    """All digest classes whose exact equality is required for resume."""

    code: str
    config: str
    tools: Mapping[str, str]
    inputs: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_digest(self.code, location="digests.code"))
        object.__setattr__(
            self, "config", _require_digest(self.config, location="digests.config")
        )
        object.__setattr__(
            self, "tools", _digest_map(self.tools, location="digests.tools")
        )
        object.__setattr__(
            self, "inputs", _digest_map(self.inputs, location="digests.inputs")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "config": self.config,
            "tools": dict(self.tools),
            "inputs": dict(self.inputs),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "StageDigests":
        if not isinstance(value, Mapping):
            raise ProvenanceError("digests: expected an object")
        expected = {"code", "config", "tools", "inputs"}
        if set(value) != expected:
            raise ProvenanceError(
                f"digests: fields must be exactly {sorted(expected)}"
            )
        return cls(
            code=value["code"],
            config=value["config"],
            tools=value["tools"],
            inputs=value["inputs"],
        )


def _utc_timestamp(value: Any, *, location: str) -> tuple[str, datetime]:
    value = _require_text(value, location=location)
    if not value.endswith("Z"):
        raise ProvenanceError(f"{location}: timestamp must be UTC and end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProvenanceError(f"{location}: invalid ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ProvenanceError(f"{location}: timestamp must be UTC")
    return value, parsed


def _command(value: Any) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ProvenanceError("command: expected a non-empty argument array")
    return tuple(
        _require_text(argument, location=f"command[{index}]")
        for index, argument in enumerate(value)
    )


def _validations(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping):
        raise ProvenanceError("semantic_validations: expected an object")
    result: dict[str, bool] = {}
    for raw_name, passed in value.items():
        name = _require_safe_name(raw_name, location="semantic_validations key")
        if not isinstance(passed, bool):
            raise ProvenanceError(f"semantic_validations.{name}: expected boolean")
        result[name] = passed
    return MappingProxyType(dict(sorted(result.items())))


@dataclass(frozen=True)
class StageRecord:
    """Validated private ``stage.json`` record for either terminal outcome."""

    stage: str
    status: Literal["success", "failure"]
    started_at: str
    finished_at: str
    exit_code: int
    command: Sequence[str]
    digests: StageDigests
    semantic_validations: Mapping[str, bool]
    output_digests: Mapping[str, str]
    error: str | None = None
    schema: str = STAGE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != STAGE_SCHEMA:
            raise ProvenanceError(f"schema must be {STAGE_SCHEMA!r}")
        object.__setattr__(
            self, "stage", _require_safe_name(self.stage, location="stage", stage=True)
        )
        if not isinstance(self.status, str) or self.status not in {"success", "failure"}:
            raise ProvenanceError("status must be success or failure")
        started_at, started = _utc_timestamp(self.started_at, location="started_at")
        finished_at, finished = _utc_timestamp(self.finished_at, location="finished_at")
        if finished < started:
            raise ProvenanceError("finished_at precedes started_at")
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "finished_at", finished_at)
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise ProvenanceError("exit_code must be an integer")
        object.__setattr__(self, "command", _command(self.command))
        if isinstance(self.digests, Mapping):
            object.__setattr__(self, "digests", StageDigests.from_dict(self.digests))
        elif not isinstance(self.digests, StageDigests):
            raise ProvenanceError("digests: expected StageDigests")
        validations = _validations(self.semantic_validations)
        outputs = _digest_map(
            self.output_digests,
            location="output_digests",
            allow_empty=self.status == "failure",
        )
        object.__setattr__(self, "semantic_validations", validations)
        object.__setattr__(self, "output_digests", outputs)

        if self.status == "success":
            if self.exit_code != 0:
                raise ProvenanceError("a successful stage must have exit_code 0")
            if not validations or not all(validations.values()):
                raise ProvenanceError(
                    "a successful stage requires at least one passing semantic validation"
                )
            if self.error is not None:
                raise ProvenanceError("a successful stage cannot contain an error")
        else:
            if self.exit_code == 0 and not any(not passed for passed in validations.values()):
                raise ProvenanceError(
                    "a failed stage needs a non-zero exit_code or a failed semantic validation"
                )
            object.__setattr__(
                self, "error", _require_text(self.error, location="error")
            )

    @classmethod
    def success(
        cls,
        *,
        stage: str,
        started_at: str,
        finished_at: str,
        command: Sequence[str],
        digests: StageDigests,
        semantic_validations: Mapping[str, bool],
        output_digests: Mapping[str, str],
    ) -> "StageRecord":
        return cls(
            stage=stage,
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            exit_code=0,
            command=command,
            digests=digests,
            semantic_validations=semantic_validations,
            output_digests=output_digests,
        )

    @classmethod
    def failure(
        cls,
        *,
        stage: str,
        started_at: str,
        finished_at: str,
        exit_code: int,
        command: Sequence[str],
        digests: StageDigests,
        semantic_validations: Mapping[str, bool],
        output_digests: Mapping[str, str] | None = None,
        error: str,
    ) -> "StageRecord":
        return cls(
            stage=stage,
            status="failure",
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            command=command,
            digests=digests,
            semantic_validations=semantic_validations,
            output_digests={} if output_digests is None else output_digests,
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "command": list(self.command),
            "digests": self.digests.to_dict(),
            "semantic_validations": dict(self.semantic_validations),
            "output_digests": dict(self.output_digests),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "StageRecord":
        if not isinstance(value, Mapping):
            raise ProvenanceError("stage record must be an object")
        expected = {
            "schema",
            "stage",
            "status",
            "started_at",
            "finished_at",
            "exit_code",
            "command",
            "digests",
            "semantic_validations",
            "output_digests",
            "error",
        }
        if set(value) != expected:
            raise ProvenanceError(
                f"stage record fields must be exactly {sorted(expected)}"
            )
        return cls(
            schema=value["schema"],
            stage=value["stage"],
            status=value["status"],
            started_at=value["started_at"],
            finished_at=value["finished_at"],
            exit_code=value["exit_code"],
            command=value["command"],
            digests=StageDigests.from_dict(value["digests"]),
            semantic_validations=value["semantic_validations"],
            output_digests=value["output_digests"],
            error=value["error"],
        )


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _stage_json_path(path: str | Path) -> Path:
    result = Path(path)
    if result.name != "stage.json":
        raise ProvenanceError("stage records must be written to a file named stage.json")
    return result


def write_stage_record(path: str | Path, record: StageRecord | Mapping[str, Any]) -> Path:
    """Atomically replace ``stage.json`` with a fully validated terminal record."""

    destination = _stage_json_path(path)
    validated = record if isinstance(record, StageRecord) else StageRecord.from_dict(record)
    payload = canonical_json_bytes(validated.to_dict()) + b"\n"
    if len(payload) > MAX_STAGE_RECORD_BYTES:
        raise ProvenanceError("stage record exceeds the 1 MiB safety limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=".stage.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_stage_record(path: str | Path) -> StageRecord:
    """Load and strictly validate a private ``stage.json`` record."""

    source = _stage_json_path(path)
    payload = source.read_bytes()
    if len(payload) > MAX_STAGE_RECORD_BYTES:
        raise ProvenanceError("stage record exceeds the 1 MiB safety limit")
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_strict_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError("stage record is not valid UTF-8 JSON") from exc
    return StageRecord.from_dict(value)


def validate_resume(
    record_or_path: StageRecord | str | Path,
    expected: StageDigests | Mapping[str, Any],
) -> StageRecord:
    """Return the record only when every resume invariant still matches."""

    record = (
        record_or_path
        if isinstance(record_or_path, StageRecord)
        else load_stage_record(record_or_path)
    )
    expected_digests = (
        expected if isinstance(expected, StageDigests) else StageDigests.from_dict(expected)
    )
    if record.status != "success":
        raise ResumeValidationError("resume rejected: prior stage did not succeed")

    mismatches: list[str] = []
    if record.digests.code != expected_digests.code:
        mismatches.append("code")
    if record.digests.config != expected_digests.config:
        mismatches.append("config")
    if dict(record.digests.tools) != dict(expected_digests.tools):
        mismatches.append("tools")
    if dict(record.digests.inputs) != dict(expected_digests.inputs):
        mismatches.append("inputs")
    if mismatches:
        raise ResumeValidationError(
            "resume rejected: digest mismatch in " + ", ".join(mismatches)
        )
    return record


def resume_is_valid(
    record_or_path: StageRecord | str | Path,
    expected: StageDigests | Mapping[str, Any],
) -> bool:
    """Boolean convenience wrapper for fail-closed resume checks."""

    try:
        validate_resume(record_or_path, expected)
    except (OSError, ProvenanceError):
        return False
    return True


def _looks_like_path(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    lowered = stripped.casefold()
    if lowered.startswith(("file://", "~/", "~\\")):
        return True
    if re.search(r"(?i)(?:^|[\s\"'])(?:[a-z]:[\\/]|\\\\|//)", stripped):
        return True
    if re.search(r"(?:^|[\s\"'])/(?:[^/\s]+/)*[^/\s]*", stripped):
        return True
    if "\\" in stripped:
        return True
    without_urls = re.sub(r"https?://[^\s]+", "", stripped, flags=re.IGNORECASE)
    return bool(
        re.search(
            r"(?:^|[\s\"'])(?:\.{1,2}/|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
            without_urls,
        )
    )


def _controlled_tokens(values: Iterable[str | Path]) -> tuple[str, ...]:
    tokens: set[str] = set()
    for raw_value in values:
        if not isinstance(raw_value, (str, Path)):
            raise PublicManifestError("controlled_values must contain only text or paths")
        value = unicodedata.normalize("NFC", str(raw_value)).strip()
        if not value:
            raise PublicManifestError("controlled_values cannot contain empty text")
        candidates = {value}
        candidates.add(PureWindowsPath(value).name)
        candidates.add(PurePosixPath(value).name)
        if value.casefold().startswith("sha256:"):
            candidates.add(value[7:])
        elif re.fullmatch(r"(?i)[0-9a-f]{64}", value):
            candidates.add("sha256:" + value)
        for candidate in candidates:
            candidate = candidate.strip().casefold()
            if candidate:
                tokens.add(candidate)
    return tuple(sorted(tokens, key=lambda token: (-len(token), token)))


def _scan_public_value(
    value: Any,
    *,
    location: str,
    allowed_digest_locations: set[str],
    controlled_tokens: tuple[str, ...],
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_location = f"{location}.{key}"
            if key.casefold() in _PRIVATE_FIELD_NAMES:
                raise PublicManifestError(
                    f"{key_location}: private-only field is forbidden in a public manifest"
                )
            _scan_public_value(
                key,
                location=key_location + " (key)",
                allowed_digest_locations=set(),
                controlled_tokens=controlled_tokens,
            )
            _scan_public_value(
                item,
                location=key_location,
                allowed_digest_locations=allowed_digest_locations,
                controlled_tokens=controlled_tokens,
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _scan_public_value(
                item,
                location=f"{location}[{index}]",
                allowed_digest_locations=allowed_digest_locations,
                controlled_tokens=controlled_tokens,
            )
        return
    if not isinstance(value, str):
        return

    if location == "$.schema" and value == PUBLIC_MANIFEST_SCHEMA:
        return

    folded = unicodedata.normalize("NFC", value).casefold()
    for token in controlled_tokens:
        if token in folded:
            raise PublicManifestError(
                f"{location}: value matches a controlled filename, path, or digest"
            )
    if _CONTROL_CHARACTERS.search(value):
        raise PublicManifestError(f"{location}: control characters are forbidden")
    if _looks_like_path(value):
        raise PublicManifestError(f"{location}: paths are forbidden in a public manifest")
    if _CONTROLLED_FILENAME.search(value):
        raise PublicManifestError(
            f"{location}: controlled/genomic filename is forbidden in a public manifest"
        )
    if value.startswith("##fileformat=VCF") or re.search(r"(?m)^@(?:HD|SQ|RG|PG)\t", value):
        raise PublicManifestError(f"{location}: controlled payload marker is forbidden")
    if _DIGEST_TOKEN.search(value) and location not in allowed_digest_locations:
        raise PublicManifestError(
            f"{location}: hash-like content is private unless the schema explicitly allows it"
        )


def validate_public_manifest(
    manifest: Mapping[str, Any],
    *,
    controlled_values: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Validate and return a canonical public-manifest value.

    ``controlled_values`` should contain every private source path, filename,
    and digest known to the caller.  Matching is case-insensitive and includes
    basenames and labelled/unlabelled SHA-256 forms.
    """

    normalised = _normalise_json(manifest)
    if not isinstance(normalised, dict):
        raise PublicManifestError("public manifest must be an object")
    expected = {
        "schema",
        "code",
        "tools",
        "public_references",
        "settings",
        "aggregate_methods",
    }
    if set(normalised) != expected:
        raise PublicManifestError(
            f"public manifest fields must be exactly {sorted(expected)}"
        )
    if normalised["schema"] != PUBLIC_MANIFEST_SCHEMA:
        raise PublicManifestError(f"schema must be {PUBLIC_MANIFEST_SCHEMA!r}")

    code = normalised["code"]
    if not isinstance(code, dict) or set(code) != {"revision", "digest"}:
        raise PublicManifestError("code fields must be exactly revision and digest")
    _require_text(code["revision"], location="code.revision")
    _require_digest(code["digest"], location="code.digest")

    tools = normalised["tools"]
    if not isinstance(tools, dict) or not tools:
        raise PublicManifestError("tools must be a non-empty object")
    for name, descriptor in tools.items():
        _require_safe_name(name, location="tools key")
        if not isinstance(descriptor, dict) or set(descriptor) != {"version", "digest"}:
            raise PublicManifestError(
                f"tools.{name} fields must be exactly version and digest"
            )
        _require_text(descriptor["version"], location=f"tools.{name}.version")
        _require_digest(descriptor["digest"], location=f"tools.{name}.digest")

    references = normalised["public_references"]
    if not isinstance(references, dict) or not references:
        raise PublicManifestError("public_references must be a non-empty object")
    for name, version in references.items():
        _require_safe_name(name, location="public_references key")
        _require_text(version, location=f"public_references.{name}")

    if not isinstance(normalised["settings"], dict):
        raise PublicManifestError("settings must be an object")
    methods = normalised["aggregate_methods"]
    if not isinstance(methods, list) or not methods:
        raise PublicManifestError("aggregate_methods must be a non-empty array")
    for index, method in enumerate(methods):
        _require_text(method, location=f"aggregate_methods[{index}]")

    allowed_digests = {"$.code.digest"}
    allowed_digests.update(f"$.tools.{name}.digest" for name in tools)
    _scan_public_value(
        normalised,
        location="$",
        allowed_digest_locations=allowed_digests,
        controlled_tokens=_controlled_tokens(controlled_values),
    )
    return normalised


def build_public_manifest(
    *,
    code_revision: str,
    code_digest: str,
    tools: Mapping[str, Mapping[str, str]],
    public_references: Mapping[str, str],
    settings: Mapping[str, Any],
    aggregate_methods: Sequence[str],
    controlled_values: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Build the allowlisted public view and run the leak checks."""

    manifest = {
        "schema": PUBLIC_MANIFEST_SCHEMA,
        "code": {"revision": code_revision, "digest": code_digest},
        "tools": tools,
        "public_references": public_references,
        "settings": settings,
        "aggregate_methods": aggregate_methods,
    }
    return validate_public_manifest(manifest, controlled_values=controlled_values)


def validate_private_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the private manifest schema without reading any referenced path."""

    normalised = _normalise_json(manifest)
    if not isinstance(normalised, dict):
        raise ProvenanceError("private manifest must be an object")
    expected = {"schema", "controlled_inputs", "stage_records"}
    if set(normalised) != expected:
        raise ProvenanceError(
            f"private manifest fields must be exactly {sorted(expected)}"
        )
    if normalised["schema"] != PRIVATE_MANIFEST_SCHEMA:
        raise ProvenanceError(f"schema must be {PRIVATE_MANIFEST_SCHEMA!r}")

    controlled_inputs = normalised["controlled_inputs"]
    if not isinstance(controlled_inputs, dict) or not controlled_inputs:
        raise ProvenanceError("controlled_inputs must be a non-empty object")
    for name, descriptor in controlled_inputs.items():
        _require_safe_name(name, location="controlled_inputs key")
        if not isinstance(descriptor, dict) or set(descriptor) != {"path", "digest"}:
            raise ProvenanceError(
                f"controlled_inputs.{name} fields must be exactly path and digest"
            )
        _require_text(descriptor["path"], location=f"controlled_inputs.{name}.path")
        _require_digest(
            descriptor["digest"], location=f"controlled_inputs.{name}.digest"
        )

    stage_records = normalised["stage_records"]
    if not isinstance(stage_records, dict) or not stage_records:
        raise ProvenanceError("stage_records must be a non-empty digest object")
    _digest_map(stage_records, location="stage_records")
    return normalised


def build_private_manifest(
    *,
    controlled_inputs: Mapping[str, Mapping[str, str]],
    stage_records: Mapping[str, str],
) -> dict[str, Any]:
    """Build the private-only index of controlled sources and stage records."""

    return validate_private_manifest(
        {
            "schema": PRIVATE_MANIFEST_SCHEMA,
            "controlled_inputs": controlled_inputs,
            "stage_records": stage_records,
        }
    )


def private_manifest_sensitive_values(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """Extract private paths, basenames, and hashes for public leak screening."""

    validated = validate_private_manifest(manifest)
    values: list[str] = []
    for descriptor in validated["controlled_inputs"].values():
        values.extend((descriptor["path"], descriptor["digest"]))
    return _controlled_tokens(values)


__all__ = [
    "MAX_STAGE_RECORD_BYTES",
    "PRIVATE_MANIFEST_SCHEMA",
    "PUBLIC_MANIFEST_SCHEMA",
    "STAGE_SCHEMA",
    "ProvenanceError",
    "PublicManifestError",
    "ResumeValidationError",
    "StageDigests",
    "StageRecord",
    "build_private_manifest",
    "build_public_manifest",
    "canonical_json_bytes",
    "load_stage_record",
    "private_manifest_sensitive_values",
    "resume_is_valid",
    "semantic_digest",
    "validate_private_manifest",
    "validate_public_manifest",
    "validate_resume",
    "write_stage_record",
]
