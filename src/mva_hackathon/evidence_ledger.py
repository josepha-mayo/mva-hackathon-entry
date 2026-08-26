"""Strict normalized qualitative-evidence ledger for Track 1.

The ledger keeps assessment availability independent from evidentiary
direction. ``negative`` means a declared method ran and returned a negative
result. ``not_assessable`` means no result can be inferred from the available
modality or evidence and therefore cannot silently become a negative.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlsplit


SCHEMA_VERSION = "mva.track1-evidence-ledger/v1"
MAX_LEDGER_BYTES = 1024 * 1024

PRIVACY_CLASSES = frozenset({"public", "synthetic", "controlled"})
PUBLIC_PRIVACY_CLASSES = frozenset({"public", "synthetic"})
PHASES = frozenset(
    {
        "ingest_qc",
        "phenotype_blind_discovery",
        "phenotype_aware_rerank",
        "completeness_audit",
        "orthogonal_validation",
        "manual_review",
        "submission_freeze",
    }
)
DIRECTIONS = frozenset({"supports", "contradicts", "neutral"})
ASSESSMENT_STATUSES = frozenset({"positive", "negative", "not_assessable"})
SOURCE_CLASSES = frozenset(
    {
        "public_database",
        "public_literature",
        "public_ontology",
        "public_software",
        "synthetic_fixture",
        "controlled_source",
        "derived_evidence",
        "manual_review",
    }
)
INDEPENDENT_REPLICATION_STATES = frozenset(
    {
        "replicated",
        "not_replicated",
        "not_attempted",
        "not_applicable",
        "not_assessable",
    }
)
DECISION_EFFECTS = frozenset(
    {"promote", "demote", "exclude", "retain", "no_change", "defer"}
)
PHASE_STATES = frozenset(
    {
        "trans_confirmed",
        "cis_confirmed",
        "unresolved",
        "not_applicable",
        "not_assessable",
    }
)

_SAFE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class EvidenceLedgerError(ValueError):
    """Raised when a ledger violates its strict schema or semantics."""


def _text(
    value: Any,
    *,
    location: str,
    minimum: int = 1,
    maximum: int = 2_000,
) -> str:
    if not isinstance(value, str):
        raise EvidenceLedgerError(f"{location}: expected text")
    value = unicodedata.normalize("NFC", value).strip()
    if not minimum <= len(value) <= maximum:
        raise EvidenceLedgerError(
            f"{location}: length must be between {minimum} and {maximum} characters"
        )
    if _CONTROL_CHARACTERS.search(value):
        raise EvidenceLedgerError(f"{location}: control characters are forbidden")
    return value


def _optional_text(
    value: Any,
    *,
    location: str,
    minimum: int = 1,
    maximum: int = 2_000,
) -> str | None:
    if value is None:
        return None
    return _text(value, location=location, minimum=minimum, maximum=maximum)


def _identifier(value: Any, *, location: str) -> str:
    value = _text(value, location=location, maximum=128)
    if _SAFE_ID.fullmatch(value) is None:
        raise EvidenceLedgerError(
            f"{location}: expected a lower-case opaque identifier"
        )
    return value


def _optional_identifier(value: Any, *, location: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, location=location)


def _enum(value: Any, allowed: frozenset[str], *, location: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise EvidenceLedgerError(f"{location}: expected one of {sorted(allowed)}")
    return value


def _digest(value: Any, *, location: str, optional: bool = True) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise EvidenceLedgerError(
            f"{location}: expected lower-case sha256 followed by 64 hex characters"
        )
    return value


def _url(value: Any, *, location: str) -> str | None:
    if value is None:
        return None
    value = _text(value, location=location, maximum=2_000)
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise EvidenceLedgerError(
            f"{location}: expected an HTTPS URL without credentials"
        )
    if parts.fragment:
        raise EvidenceLedgerError(f"{location}: URL fragments are forbidden")
    return value


def _relative_artifact_path(value: Any) -> str | None:
    if value is None:
        return None
    value = _text(value, location="artifact_path", maximum=500)
    if "\\" in value:
        raise EvidenceLedgerError(
            "artifact_path: use a portable relative POSIX path"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise EvidenceLedgerError(
            "artifact_path: path must be relative and non-traversing"
        )
    if not path.parts or any(not part for part in path.parts):
        raise EvidenceLedgerError("artifact_path: invalid relative path")
    return path.as_posix()


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    value = _text(value, location="reviewed_at", maximum=64)
    if not value.endswith("Z"):
        raise EvidenceLedgerError(
            "reviewed_at: timestamp must be UTC and end in Z"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceLedgerError(
            "reviewed_at: invalid ISO-8601 timestamp"
        ) from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise EvidenceLedgerError("reviewed_at: timestamp must be UTC")
    return value


def _result(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise EvidenceLedgerError("result: expected a finite JSON scalar or null")


def _string_sequence(
    value: Any,
    *,
    location: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EvidenceLedgerError(f"{location}: expected an array")
    if not value and not allow_empty:
        raise EvidenceLedgerError(f"{location}: at least one item is required")
    result = tuple(
        _text(item, location=f"{location}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        raise EvidenceLedgerError(f"{location}: duplicate items are forbidden")
    return result


@dataclass(frozen=True)
class EvidenceEntry:
    """One normalized audit row for an observation, negative, or evidence gap."""

    evidence_id: str
    model_slot: int | None
    claim: str
    allele_or_pair_id: str | None
    evidence_type: str
    privacy_class: Literal["public", "synthetic", "controlled"]
    phase: str
    phase_state: str
    direction: Literal["supports", "contradicts", "neutral"]
    assessment_status: Literal["positive", "negative", "not_assessable"]
    method_id: str
    source_class: str
    source_identifier: str
    source_version: str | None
    source_url: str | None
    tool_name: str | None
    tool_version: str | None
    tool_digest: str | None
    run_digest: str | None
    config_digest: str | None
    result: str | int | float | bool | None
    unit: str | None
    independent_replication: str
    uncertainty: str
    counterevidence: Sequence[str]
    decision_effect: str
    artifact_path: str | None
    artifact_sha256: str | None
    manual_action: str | None
    reviewer: str | None
    reviewed_at: str | None
    not_assessable_reason: str | None
    limitations: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evidence_id", _identifier(self.evidence_id, location="evidence_id")
        )
        if self.model_slot is not None and (
            isinstance(self.model_slot, bool)
            or not isinstance(self.model_slot, int)
            or not 1 <= self.model_slot <= 6
        ):
            raise EvidenceLedgerError(
                "model_slot: expected null or an integer from 1 through 6"
            )
        object.__setattr__(
            self, "claim", _text(self.claim, location="claim", minimum=10)
        )
        object.__setattr__(
            self,
            "allele_or_pair_id",
            _optional_identifier(
                self.allele_or_pair_id, location="allele_or_pair_id"
            ),
        )
        object.__setattr__(
            self,
            "evidence_type",
            _identifier(self.evidence_type, location="evidence_type"),
        )
        object.__setattr__(
            self,
            "privacy_class",
            _enum(self.privacy_class, PRIVACY_CLASSES, location="privacy_class"),
        )
        object.__setattr__(
            self, "phase", _enum(self.phase, PHASES, location="phase")
        )
        object.__setattr__(
            self,
            "phase_state",
            _enum(self.phase_state, PHASE_STATES, location="phase_state"),
        )
        object.__setattr__(
            self,
            "direction",
            _enum(self.direction, DIRECTIONS, location="direction"),
        )
        object.__setattr__(
            self,
            "assessment_status",
            _enum(
                self.assessment_status,
                ASSESSMENT_STATUSES,
                location="assessment_status",
            ),
        )
        object.__setattr__(
            self, "method_id", _identifier(self.method_id, location="method_id")
        )
        object.__setattr__(
            self,
            "source_class",
            _enum(self.source_class, SOURCE_CLASSES, location="source_class"),
        )
        object.__setattr__(
            self,
            "source_identifier",
            _identifier(self.source_identifier, location="source_identifier"),
        )
        object.__setattr__(
            self,
            "source_version",
            _optional_text(
                self.source_version, location="source_version", maximum=200
            ),
        )
        object.__setattr__(
            self, "source_url", _url(self.source_url, location="source_url")
        )
        object.__setattr__(
            self,
            "tool_name",
            _optional_identifier(self.tool_name, location="tool_name"),
        )
        object.__setattr__(
            self,
            "tool_version",
            _optional_text(self.tool_version, location="tool_version", maximum=200),
        )
        object.__setattr__(
            self,
            "tool_digest",
            _digest(self.tool_digest, location="tool_digest"),
        )
        object.__setattr__(
            self, "run_digest", _digest(self.run_digest, location="run_digest")
        )
        object.__setattr__(
            self,
            "config_digest",
            _digest(self.config_digest, location="config_digest"),
        )
        object.__setattr__(self, "result", _result(self.result))
        object.__setattr__(
            self, "unit", _optional_text(self.unit, location="unit", maximum=100)
        )
        object.__setattr__(
            self,
            "independent_replication",
            _enum(
                self.independent_replication,
                INDEPENDENT_REPLICATION_STATES,
                location="independent_replication",
            ),
        )
        object.__setattr__(
            self,
            "uncertainty",
            _text(self.uncertainty, location="uncertainty", minimum=10),
        )
        object.__setattr__(
            self,
            "counterevidence",
            _string_sequence(
                self.counterevidence, location="counterevidence", allow_empty=True
            ),
        )
        object.__setattr__(
            self,
            "decision_effect",
            _enum(self.decision_effect, DECISION_EFFECTS, location="decision_effect"),
        )
        object.__setattr__(
            self, "artifact_path", _relative_artifact_path(self.artifact_path)
        )
        object.__setattr__(
            self,
            "artifact_sha256",
            _digest(self.artifact_sha256, location="artifact_sha256"),
        )
        object.__setattr__(
            self,
            "manual_action",
            _optional_text(
                self.manual_action, location="manual_action", minimum=10
            ),
        )
        object.__setattr__(
            self,
            "reviewer",
            _optional_identifier(self.reviewer, location="reviewer"),
        )
        object.__setattr__(self, "reviewed_at", _timestamp(self.reviewed_at))
        object.__setattr__(
            self,
            "limitations",
            _string_sequence(
                self.limitations, location="limitations", allow_empty=False
            ),
        )

        tool_nulls = (
            self.tool_name is None,
            self.tool_version is None,
            self.tool_digest is None,
        )
        if tool_nulls.count(True) not in {0, 3}:
            raise EvidenceLedgerError(
                "tool_name, tool_version, and tool_digest must be all null or all populated"
            )
        if (self.run_digest is None) != (self.config_digest is None):
            raise EvidenceLedgerError(
                "run_digest and config_digest must be both null or both populated"
            )
        if (self.artifact_path is None) != (self.artifact_sha256 is None):
            raise EvidenceLedgerError(
                "artifact_path and artifact_sha256 must be both null or both populated"
            )
        if (self.reviewer is None) != (self.reviewed_at is None):
            raise EvidenceLedgerError(
                "reviewer and reviewed_at must be both null or both populated"
            )
        if self.source_class.startswith("public_") and self.source_url is None:
            raise EvidenceLedgerError("public source classes require source_url")
        if (
            self.privacy_class in PUBLIC_PRIVACY_CLASSES
            and self.source_class == "controlled_source"
        ):
            raise EvidenceLedgerError(
                "public or synthetic entries cannot label a controlled source"
            )

        if self.assessment_status == "not_assessable":
            if self.direction != "neutral":
                raise EvidenceLedgerError(
                    "not_assessable evidence must have neutral direction"
                )
            if self.result is not None or self.unit is not None:
                raise EvidenceLedgerError(
                    "not_assessable evidence cannot contain a result or unit"
                )
            if self.independent_replication != "not_assessable":
                raise EvidenceLedgerError(
                    "not_assessable evidence requires not_assessable replication state"
                )
            if self.phase_state not in {"not_assessable", "not_applicable"}:
                raise EvidenceLedgerError(
                    "not_assessable evidence requires a non-assertive phase_state"
                )
            if self.decision_effect not in {"defer", "no_change"}:
                raise EvidenceLedgerError(
                    "not_assessable evidence cannot promote, demote, or exclude"
                )
            object.__setattr__(
                self,
                "not_assessable_reason",
                _text(
                    self.not_assessable_reason,
                    location="not_assessable_reason",
                    minimum=10,
                ),
            )
        else:
            if self.result is None:
                raise EvidenceLedgerError("assessed evidence requires a result")
            if self.not_assessable_reason is not None:
                raise EvidenceLedgerError(
                    "assessed evidence must set not_assessable_reason to null"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "model_slot": self.model_slot,
            "claim": self.claim,
            "allele_or_pair_id": self.allele_or_pair_id,
            "evidence_type": self.evidence_type,
            "privacy_class": self.privacy_class,
            "phase": self.phase,
            "phase_state": self.phase_state,
            "direction": self.direction,
            "assessment_status": self.assessment_status,
            "method_id": self.method_id,
            "source_class": self.source_class,
            "source_identifier": self.source_identifier,
            "source_version": self.source_version,
            "source_url": self.source_url,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "tool_digest": self.tool_digest,
            "run_digest": self.run_digest,
            "config_digest": self.config_digest,
            "result": self.result,
            "unit": self.unit,
            "independent_replication": self.independent_replication,
            "uncertainty": self.uncertainty,
            "counterevidence": list(self.counterevidence),
            "decision_effect": self.decision_effect,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "manual_action": self.manual_action,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "not_assessable_reason": self.not_assessable_reason,
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "EvidenceEntry":
        if not isinstance(value, Mapping):
            raise EvidenceLedgerError("evidence entry must be an object")
        expected = set(cls.__dataclass_fields__)
        if set(value) != expected:
            raise EvidenceLedgerError(
                f"evidence entry fields must be exactly {sorted(expected)}"
            )
        return cls(**{key: value[key] for key in expected})


@dataclass(frozen=True)
class EvidenceLedger:
    """A deterministic collection of normalized qualitative audit rows."""

    ledger_id: str
    purpose: str
    entries: Sequence[EvidenceEntry]
    schema: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema != SCHEMA_VERSION:
            raise EvidenceLedgerError(f"schema must be {SCHEMA_VERSION!r}")
        object.__setattr__(
            self, "ledger_id", _identifier(self.ledger_id, location="ledger_id")
        )
        object.__setattr__(
            self, "purpose", _text(self.purpose, location="purpose", minimum=20)
        )
        if isinstance(self.entries, (str, bytes)) or not isinstance(
            self.entries, Sequence
        ):
            raise EvidenceLedgerError("entries: expected an array")
        converted = tuple(
            entry
            if isinstance(entry, EvidenceEntry)
            else EvidenceEntry.from_dict(entry)
            for entry in self.entries
        )
        identifiers = [entry.evidence_id for entry in converted]
        if len(set(identifiers)) != len(identifiers):
            raise EvidenceLedgerError(
                "entries: duplicate evidence_id values are forbidden"
            )
        object.__setattr__(self, "entries", converted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "ledger_id": self.ledger_id,
            "purpose": self.purpose,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "EvidenceLedger":
        if not isinstance(value, Mapping):
            raise EvidenceLedgerError("evidence ledger must be an object")
        expected = {"schema", "ledger_id", "purpose", "entries"}
        if set(value) != expected:
            raise EvidenceLedgerError(
                f"ledger fields must be exactly {sorted(expected)}"
            )
        return cls(
            schema=value["schema"],
            ledger_id=value["ledger_id"],
            purpose=value["purpose"],
            entries=value["entries"],
        )


def validate_evidence_ledger(
    value: EvidenceLedger | Mapping[str, Any],
    *,
    public_only: bool = False,
) -> EvidenceLedger:
    """Validate and return an immutable ledger, optionally public-only."""

    ledger = (
        value if isinstance(value, EvidenceLedger) else EvidenceLedger.from_dict(value)
    )
    if public_only:
        forbidden = sorted(
            {
                entry.privacy_class
                for entry in ledger.entries
                if entry.privacy_class not in PUBLIC_PRIVACY_CLASSES
            }
        )
        if forbidden:
            raise EvidenceLedgerError(
                "public ledger contains forbidden privacy classes: "
                + ", ".join(forbidden)
            )
    return ledger


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceLedgerError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_evidence_ledger(
    path: str | Path, *, public_only: bool = False
) -> EvidenceLedger:
    """Load UTF-8 JSON with duplicate-key, size, schema, and privacy checks."""

    source = Path(path)
    payload = source.read_bytes()
    if len(payload) > MAX_LEDGER_BYTES:
        raise EvidenceLedgerError("evidence ledger exceeds the 1 MiB limit")
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_strict_object)
    except UnicodeDecodeError as exc:
        raise EvidenceLedgerError("evidence ledger is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceLedgerError("evidence ledger is not valid JSON") from exc
    return validate_evidence_ledger(value, public_only=public_only)
