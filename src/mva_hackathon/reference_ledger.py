"""Fail-closed reference/proprietary-source ledger for Track 1."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

SCHEMA_VERSION = "mva.track1-reference-ledger/v1"
MAX_LEDGER_BYTES = 1024 * 1024
SLOTS = frozenset({f"S{number}" for number in range(1, 7)})
SCOPES = frozenset({"public", "proprietary"})
_SAFE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FLOATING_RELEASE = re.compile(
    r"^(?:latest|current|head|main|master|trunk|rolling|unversioned|unknown|n/?a)$",
    re.IGNORECASE,
)
_PRIVATE_PATH = re.compile(r"(?:^[A-Za-z]:[\\/]|\\|file:/{1,3}|(?:^|/)users/)", re.IGNORECASE)


class ReferenceLedgerError(ValueError):
    """Raised when a reference ledger is ambiguous, unsafe, or non-reproducible."""


def _text(value: Any, field: str, *, minimum: int = 1, maximum: int = 2_000) -> str:
    if not isinstance(value, str):
        raise ReferenceLedgerError(f"{field}: expected text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not minimum <= len(normalized) <= maximum or _CONTROL.search(normalized):
        raise ReferenceLedgerError(
            f"{field}: expected {minimum} to {maximum} printable characters"
        )
    if _PRIVATE_PATH.search(normalized):
        raise ReferenceLedgerError(f"{field}: local paths are forbidden")
    return normalized


def _identifier(value: Any, field: str) -> str:
    value = _text(value, field, maximum=128)
    if not _SAFE_ID.fullmatch(value):
        raise ReferenceLedgerError(f"{field}: expected a lower-case opaque identifier")
    return value


def _date(value: Any, field: str) -> str:
    value = _text(value, field, maximum=10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ReferenceLedgerError(f"{field}: expected YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ReferenceLedgerError(f"{field}: expected canonical YYYY-MM-DD")
    return value


def _timestamp(value: Any) -> str:
    value = _text(value, "retrieved_at_utc", maximum=35)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReferenceLedgerError("retrieved_at_utc: expected ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ReferenceLedgerError("retrieved_at_utc: UTC offset is required")
    return value


def _https_url(value: Any, field: str) -> str:
    value = _text(value, field, maximum=2_048)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ReferenceLedgerError(
            f"{field}: expected an HTTPS URL without credentials, query, or fragment"
        )
    return value


def _sequence(value: Any, field: str, *, identifiers: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ReferenceLedgerError(f"{field}: expected a non-empty array")
    converted = tuple(
        _identifier(item, f"{field}[{index}]")
        if identifiers
        else _text(item, f"{field}[{index}]", maximum=1_000)
        for index, item in enumerate(value)
    )
    if len(set(converted)) != len(converted):
        raise ReferenceLedgerError(f"{field}: duplicate values are forbidden")
    return converted


@dataclass(frozen=True)
class ReferenceResource:
    resource_id: str
    name: str
    source_scope: str
    release: str
    release_date: str
    retrieved_at_utc: str
    source_url: str
    license_id: str
    license_url: str
    sha256: str | None
    immutable_revision: str | None
    purpose: str
    use_mode: str
    hosted_api_used: bool
    challenge_controlled: bool
    model_slots: Sequence[str]
    redistribution_notes: str
    attribution_notes: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_id", _identifier(self.resource_id, "resource_id"))
        object.__setattr__(self, "name", _text(self.name, "name", maximum=256))
        if self.source_scope not in SCOPES:
            raise ReferenceLedgerError(f"source_scope: expected one of {sorted(SCOPES)}")
        release = _text(self.release, "release", maximum=256)
        if _FLOATING_RELEASE.fullmatch(release):
            raise ReferenceLedgerError("release: floating labels such as latest are forbidden")
        object.__setattr__(self, "release", release)
        object.__setattr__(self, "release_date", _date(self.release_date, "release_date"))
        object.__setattr__(self, "retrieved_at_utc", _timestamp(self.retrieved_at_utc))
        object.__setattr__(self, "source_url", _https_url(self.source_url, "source_url"))
        object.__setattr__(self, "license_id", _text(self.license_id, "license_id", maximum=128))
        object.__setattr__(self, "license_url", _https_url(self.license_url, "license_url"))

        if self.sha256 is not None:
            if not isinstance(self.sha256, str) or not _HEX_SHA256.fullmatch(self.sha256):
                raise ReferenceLedgerError("sha256: expected a lower-case SHA-256 digest or null")
        if self.immutable_revision is not None:
            object.__setattr__(
                self,
                "immutable_revision",
                _text(self.immutable_revision, "immutable_revision", maximum=256),
            )
            if _FLOATING_RELEASE.fullmatch(self.immutable_revision):
                raise ReferenceLedgerError("immutable_revision: floating labels are forbidden")
        if self.sha256 is None and self.immutable_revision is None:
            raise ReferenceLedgerError("at least one of sha256 or immutable_revision is required")

        object.__setattr__(self, "purpose", _text(self.purpose, "purpose", minimum=20))
        if self.use_mode != "local_offline":
            raise ReferenceLedgerError("use_mode must be local_offline")
        if self.hosted_api_used is not False:
            raise ReferenceLedgerError("hosted_api_used must be false")
        if self.challenge_controlled is not False:
            raise ReferenceLedgerError("challenge-controlled inputs cannot enter the reference ledger")
        slots = _sequence(self.model_slots, "model_slots")
        if any(slot not in SLOTS for slot in slots):
            raise ReferenceLedgerError(f"model_slots: expected only {sorted(SLOTS)}")
        object.__setattr__(self, "model_slots", slots)
        object.__setattr__(
            self,
            "redistribution_notes",
            _text(self.redistribution_notes, "redistribution_notes", minimum=10),
        )
        object.__setattr__(
            self,
            "attribution_notes",
            _text(self.attribution_notes, "attribution_notes", minimum=10),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "ReferenceResource":
        if not isinstance(value, Mapping):
            raise ReferenceLedgerError("resource must be an object")
        fields = {
            "resource_id", "name", "source_scope", "release", "release_date",
            "retrieved_at_utc", "source_url", "license_id", "license_url", "sha256",
            "immutable_revision", "purpose", "use_mode", "hosted_api_used",
            "challenge_controlled", "model_slots", "redistribution_notes",
            "attribution_notes",
        }
        if set(value) != fields:
            raise ReferenceLedgerError(f"resource fields must be exactly {sorted(fields)}")
        return cls(**{field: value[field] for field in fields})

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "source_scope": self.source_scope,
            "release": self.release,
            "release_date": self.release_date,
            "retrieved_at_utc": self.retrieved_at_utc,
            "source_url": self.source_url,
            "license_id": self.license_id,
            "license_url": self.license_url,
            "sha256": self.sha256,
            "immutable_revision": self.immutable_revision,
            "purpose": self.purpose,
            "use_mode": self.use_mode,
            "hosted_api_used": self.hosted_api_used,
            "challenge_controlled": self.challenge_controlled,
            "model_slots": list(self.model_slots),
            "redistribution_notes": self.redistribution_notes,
            "attribution_notes": self.attribution_notes,
        }


@dataclass(frozen=True)
class ReferenceLedger:
    ledger_id: str
    champion_public_only: bool
    resources: Sequence[ReferenceResource]
    schema: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema != SCHEMA_VERSION:
            raise ReferenceLedgerError(f"schema must be {SCHEMA_VERSION}")
        object.__setattr__(self, "ledger_id", _identifier(self.ledger_id, "ledger_id"))
        if self.champion_public_only is not True:
            raise ReferenceLedgerError("champion_public_only must be true")
        if isinstance(self.resources, (str, bytes)) or not isinstance(self.resources, Sequence):
            raise ReferenceLedgerError("resources: expected an array")
        resources = tuple(
            item if isinstance(item, ReferenceResource) else ReferenceResource.from_dict(item)
            for item in self.resources
        )
        if not resources:
            raise ReferenceLedgerError("resources: at least one locked resource is required")
        identifiers = [item.resource_id for item in resources]
        if len(set(identifiers)) != len(identifiers):
            raise ReferenceLedgerError("resources: duplicate resource_id values are forbidden")
        if any(item.source_scope != "public" for item in resources):
            raise ReferenceLedgerError("champion ledger cannot contain proprietary resources")
        object.__setattr__(self, "resources", resources)

    @classmethod
    def from_dict(cls, value: Any) -> "ReferenceLedger":
        if not isinstance(value, Mapping):
            raise ReferenceLedgerError("ledger must be an object")
        if set(value) != {"schema", "ledger_id", "champion_public_only", "resources"}:
            raise ReferenceLedgerError("ledger fields are invalid")
        return cls(
            schema=value["schema"],
            ledger_id=value["ledger_id"],
            champion_public_only=value["champion_public_only"],
            resources=value["resources"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "ledger_id": self.ledger_id,
            "champion_public_only": self.champion_public_only,
            "resources": [resource.to_dict() for resource in self.resources],
        }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReferenceLedgerError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_reference_ledger(path: str | Path) -> ReferenceLedger:
    payload = Path(path).read_bytes()
    if len(payload) > MAX_LEDGER_BYTES:
        raise ReferenceLedgerError("reference ledger exceeds 1 MiB")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceLedgerError("reference ledger is not strict UTF-8 JSON") from exc
    return ReferenceLedger.from_dict(value)


__all__ = [
    "ReferenceLedger", "ReferenceLedgerError", "ReferenceResource",
    "SCHEMA_VERSION", "load_reference_ledger",
]
