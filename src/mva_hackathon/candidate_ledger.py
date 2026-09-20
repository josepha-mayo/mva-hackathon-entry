"""Strict normalized Track 2 candidate evidence ledger.

The ledger keeps assessment availability independent from evidentiary
direction. ``negative`` means a declared method ran and returned a negative
result. ``not_assessable`` means no result can be inferred from the available
modality or evidence and therefore cannot silently become a negative.

Ranking is software and evidence-ledger behavior only. A shorter
causal-distance score does not automatically become the lead. A
``public_software`` or ``official_label`` source cannot mint positive
exact-allele, checkpoint, direct-target, or human-PD evidence, and cannot
occupy lead advancement. A ``public_software``, ``public_database``, or
``public_ontology`` source also cannot occupy a pharmacologic ranking role.
A database or ontology row is not a screened medicine; it may still record
causal axes on a mechanistic-control or no-go row. A ``derived_evidence``
row must name a non-derived ``parent_source_class`` and inherits that
parent's occupancy and mint bans; literature-derived or manual-review
parents remain eligible. Relabeling a catalog, label, database, or
ontology row as derived evidence is not a screened medicine. Conditional
hold and active lead require a pharmacologic ranking role; a mechanistic
control or no-go cannot occupy the probe queue. Active lead requires
role ``lead``; a challenger or comparator cannot hide as the active
medicine. A ledger may have at most one role ``lead``. A
``synthetic_fixture`` row cannot be labeled public or controlled. A public
catalog, label, database, ontology, or literature row cannot be labeled
synthetic or controlled. Decision-effect
``promote`` requires lead advancement; a parked comparator-only row cannot
claim promotion. Conditional hold cannot carry ``demote``. Oncology-stop,
expired-eligibility, or nontranslational-high rows cannot occupy
conditional hold or active lead. Role ``no_go`` and decision-effect
``exclude`` require advancement ``rejected``. A ``mixed_or_unsafe``
functional hit cannot occupy conditional hold or active lead and cannot
enter the screened displacement set; a parked comparator-only row may
still carry that label. A ``no_hit`` cannot occupy lead advancement and
cannot enter the screened displacement set; a parked comparator-only row
may still carry that valid negative. A rejected pharmacologic row cannot
enter the screened displacement set; role lead already cannot be rejected.
A not-assessable pharmacologic row cannot enter the screened displacement
set; comparator-only remaining references stay ranking-eligible. Unassessed
oncology risk or unassessed exposure cannot occupy conditional hold or
active lead. Ranking-only ineligibility (unassessed regulatory eligibility,
exploratory 5 µM exposure, or absent/unassessed pediatric information) may
still occupy conditional hold. An active lead still requires pediatric
information.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlsplit

from mva_hackathon.sample_stewardship import (
    SampleStewardshipError,
    assess_sample_stewardship,
)


SCHEMA_VERSION = "mva.track2-candidate-ledger/v7"
MAX_LEDGER_BYTES = 1024 * 1024
MAX_SAMPLE_PLAN_BYTES = 1024 * 1024
CLAIM_BOUNDARY = (
    "This output is software and evidence-ledger behavior only. "
    "Experimental priority is a manually declared test order, not an efficacy rank, "
    "and no active lead exists until every structured rescue gate passes, a "
    "full functional phenocopy is independently replicated, same-lane "
    "sample-stewardship held-out and replication completion receipts debit that "
    "claim, and the same-lane context-qualification mitotic class and "
    "transformation state match the candidate."
)
SAMPLE_STEWARDSHIP_PROMOTION_FIELDS = (
    "held_out_assay_id",
    "replication_assay_id",
    "held_out_receipt_id",
    "replication_receipt_id",
    "held_out_receipt_sha256",
    "replication_receipt_sha256",
    "sample_plan_sha256",
)

PRIVACY_CLASSES = frozenset({"public", "synthetic", "controlled"})
PUBLIC_PRIVACY_CLASSES = frozenset({"public", "synthetic"})
DIRECTIONS = frozenset({"supports", "contradicts", "neutral"})
ASSESSMENT_STATUSES = frozenset({"positive", "negative", "not_assessable"})
DECISION_EFFECTS = frozenset(
    {"promote", "demote", "exclude", "retain", "no_change", "defer"}
)
ROLES = frozenset(
    {"lead", "comparator", "challenger", "mechanistic_control", "no_go"}
)
PHARMACOLOGIC_RANKING_ROLES = frozenset({"lead", "comparator", "challenger"})
PROGRAM_GATES = frozenset(
    {
        "confirmation",
        "phase",
        "rna",
        "allelic_series",
        "stability",
        "exposure",
        "segregation",
        "oncology",
        "regulatory",
    }
)
ADVANCEMENT_STATES = frozenset(
    {
        "conditional_hold",
        "rejected",
        "comparator_only",
        "not_assessable",
        "active_lead",
    }
)
FUNCTIONAL_HIT_STATES = frozenset(
    {
        "not_tested",
        "no_hit",
        "full_phenocopy_pending_replication",
        "graded_partial_hit",
        "mechanism_discordant_hit",
        "mixed_or_unsafe",
        "replicated_full_phenocopy",
    }
)
SCREEN_CONTEXTS = frozenset(
    {
        "renewable_nonparticipant_a0",
        "minimal_participant_a1",
        "participant_lineage_tier_b",
    }
)
NO_HIT_BASES = frozenset(
    {
        "not_applicable",
        "valid_a0_negative",
        "valid_participant_negative",
        "insufficient_material",
        "failed_controls",
        "unmeasured_exposure",
        "screen_failure",
    }
)
VALID_NO_HIT_BASES = frozenset(
    {"valid_a0_negative", "valid_participant_negative"}
)
TRANSLATION_STATES = frozenset(
    {"mechanism_only", "context_qualified", "preclinical_replication_ready"}
)
DISCOVERY_LANES = frozenset(
    {"targeted_hypothesis", "correction_trained_phenotypic"}
)
SITE2_BLINDING_STATES = frozenset(
    {"not_attempted", "blinded", "unblinded", "not_applicable"}
)
THERAPEUTIC_CONTEXTS = frozenset(
    {
        "renewable_2d_surrogate",
        "postnatal_nontransformed_proliferative",
        "not_assessable",
    }
)
ARCHITECTURE_LINEAGE_STATES = frozenset(
    {
        "reduced_2d_surrogate",
        "architecture_preserving",
        "lineage_intrinsic_mitotic",
        "not_assessable",
    }
)
MITOTIC_CONTEXT_CLASSES = frozenset(
    {
        "epithelial_architecture_dependent",
        "lineage_intrinsic_mitotic",
        "not_assessable",
    }
)
QUALIFIED_MITOTIC_CONTEXT_CLASSES = frozenset(
    {"epithelial_architecture_dependent", "lineage_intrinsic_mitotic"}
)
TRANSFORMATION_STATES = frozenset(
    {
        "primary_finite",
        "renewable_nontransformed_isogenic",
        "immortalized_or_transformed",
        "reprogrammed",
        "not_assessable",
    }
)
TRANSFORMED_CULTURE_STATES = frozenset(
    {"immortalized_or_transformed", "reprogrammed"}
)
DISPLACEMENT_INELIGIBLE_TRANSFORMATION_STATES = frozenset(
    TRANSFORMED_CULTURE_STATES | {"renewable_nontransformed_isogenic"}
)
DISPLACEMENT_INELIGIBLE_FUNCTIONAL_HIT_STATES = frozenset(
    {"mixed_or_unsafe", "no_hit"}
)
DISPLACEMENT_INELIGIBLE_ADVANCEMENT_STATES = frozenset(
    {"rejected", "not_assessable"}
)
CONTEXT_QUALIFIED_TRANSLATION_STATES = frozenset(
    {"context_qualified", "preclinical_replication_ready"}
)
MITOTIC_CLASS_TO_ARCHITECTURE = {
    "epithelial_architecture_dependent": "architecture_preserving",
    "lineage_intrinsic_mitotic": "lineage_intrinsic_mitotic",
}
HELD_OUT_CONFIRMATION_STATES = frozenset(
    {"graded_partial_hit", "mechanism_discordant_hit"}
)
CORRECTION_TRAINED_FUNCTIONAL_HIT_STATES = frozenset(
    {
        "graded_partial_hit",
        "mechanism_discordant_hit",
        "full_phenocopy_pending_replication",
        "replicated_full_phenocopy",
    }
)
HELD_OUT_CONFIRMATION_GATE_NAMES = (
    "correction_rescue",
    "reciprocal_recreation",
    "branch_opened",
    "exposure_validity",
    "correction_like_function",
    "native_fidelity",
    "completion_equivalence",
    "clone_safety",
    "analysis_lock_and_multiplicity",
    "discovery_confirmation_separation",
    "matched_control_and_retained_domain_safety",
)
ADVANCING_DECISION_EFFECTS = frozenset({"promote", "retain"})
HELD_OUT_PROGRAM_GATES = frozenset(
    {"exposure", "segregation", "oncology", "regulatory"}
)
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
        "official_label",
    }
)
PARENT_SOURCE_CLASSES = frozenset(SOURCE_CLASSES - {"derived_evidence"})
SOFTWARE_CANNOT_MINT_POSITIVE_AXES = (
    "direct_target_evidence",
    "exact_allele_evidence",
    "checkpoint_evidence",
    "human_pd_evidence",
)
SOURCES_CANNOT_MINT_POSITIVE_AXES = frozenset({"public_software", "official_label"})
SOURCES_CANNOT_OCCUPY_LEAD_ADVANCEMENT = frozenset(
    {
        "public_software",
        "official_label",
        "public_database",
        "public_ontology",
    }
)
SOURCES_CANNOT_OCCUPY_PHARMACOLOGIC_ROLES = frozenset(
    {"public_software", "public_database", "public_ontology"}
)
SOURCES_REQUIRE_SYNTHETIC_PRIVACY = frozenset({"synthetic_fixture"})
SOURCES_REQUIRE_PUBLIC_PRIVACY = frozenset(
    {
        "public_software",
        "public_database",
        "public_ontology",
        "public_literature",
        "official_label",
    }
)
EXPOSURE_CLASSES = frozenset(
    {
        "leq_2um",
        "candidate_specific_plausible",
        "exploratory_5um",
        "nontranslational_high",
        "not_assessable",
    }
)
DISPLACEMENT_ELIGIBLE_EXPOSURE_CLASSES = frozenset(
    {"leq_2um", "candidate_specific_plausible"}
)
MAX_CANDIDATE_SPECIFIC_UM = 1_000.0
PEDIATRIC_INFORMATION_STATES = frozenset(
    {"present", "absent", "not_assessable"}
)
DISPLACEMENT_ELIGIBLE_PEDIATRIC_STATES = frozenset({"present"})
ONCOLOGY_RISKS = frozenset({"stop", "caution", "not_assessable"})
REGULATORY_ELIGIBILITY_STATES = frozenset(
    {"current", "mixed_or_restricted", "expired_or_absent", "not_assessable"}
)
DISPLACEMENT_ELIGIBLE_REGULATORY_STATES = frozenset(
    {"current", "mixed_or_restricted"}
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
RESCUE_GATE_STATES = frozenset(
    {"pass", "fail", "not_attempted", "not_applicable"}
)
RESCUE_GATE_NAMES = (
    "correction_rescue",
    "reciprocal_recreation",
    "branch_opened",
    "exposure_validity",
    "proximal_engagement",
    "correction_like_function",
    "native_fidelity",
    "completion_equivalence",
    "clone_safety",
    "analysis_lock_and_multiplicity",
    "discovery_confirmation_separation",
    "matched_control_and_retained_domain_safety",
    "therapeutic_context_and_architecture_lineage",
    "analytic_transfer_pass",
    "biological_replication_pass",
    "blinded_replication_execution",
    "independent_replication",
    "replication_provenance",
)
PENDING_REPLICATION_GATE_NAMES = frozenset(
    {
        "analytic_transfer_pass",
        "biological_replication_pass",
        "blinded_replication_execution",
        "independent_replication",
        "replication_provenance",
    }
)
FULL_PHENOCOPY_PRE_REPLICATION_GATE_NAMES = tuple(
    name for name in RESCUE_GATE_NAMES if name not in PENDING_REPLICATION_GATE_NAMES
)
LEAD_ADVANCEMENT_STATES = frozenset({"active_lead", "conditional_hold"})
ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT = "active_lead"

_SAFE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SHA256_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class CandidateLedgerError(ValueError):
    """Raised when a ledger violates its strict schema or semantics."""


def _text(
    value: Any,
    *,
    location: str,
    minimum: int = 1,
    maximum: int = 2_000,
) -> str:
    if not isinstance(value, str):
        raise CandidateLedgerError(f"{location}: expected text")
    value = unicodedata.normalize("NFC", value).strip()
    if not minimum <= len(value) <= maximum:
        raise CandidateLedgerError(
            f"{location}: length must be between {minimum} and {maximum} characters"
        )
    if _CONTROL_CHARACTERS.search(value):
        raise CandidateLedgerError(f"{location}: control characters are forbidden")
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
        raise CandidateLedgerError(
            f"{location}: expected a lower-case opaque identifier"
        )
    return value


def _optional_identifier(value: Any, *, location: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, location=location)


def _optional_sha256_fingerprint(value: Any, *, location: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _SHA256_FINGERPRINT.fullmatch(value) is None:
        raise CandidateLedgerError(
            f"{location}: expected null or a lower-case SHA-256 fingerprint"
        )
    return value


def _enum(value: Any, allowed: frozenset[str], *, location: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise CandidateLedgerError(f"{location}: expected one of {sorted(allowed)}")
    return value


def _url(value: Any, *, location: str) -> str | None:
    if value is None:
        return None
    value = _text(value, location=location, maximum=2_000)
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise CandidateLedgerError(
            f"{location}: expected an HTTPS URL without credentials"
        )
    if parts.fragment:
        raise CandidateLedgerError(f"{location}: URL fragments are forbidden")
    return value


def _date(value: Any, *, location: str) -> str:
    value = _text(value, location=location, maximum=10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CandidateLedgerError(f"{location}: expected YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise CandidateLedgerError(f"{location}: expected canonical YYYY-MM-DD")
    return value


def _result(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise CandidateLedgerError("result: expected a finite JSON scalar or null")


def _optional_finite_number(value: Any, *, location: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandidateLedgerError(f"{location}: expected a finite number or null")
    if isinstance(value, float) and not math.isfinite(value):
        raise CandidateLedgerError(f"{location}: expected a finite number or null")
    return value


def _validate_exposure_concentration(
    exposure_class: str,
    concentration_uM: int | float | None,
) -> None:
    if exposure_class == "not_assessable":
        if concentration_uM is not None:
            raise CandidateLedgerError(
                "not_assessable exposure requires null nominal_concentration_uM"
            )
        return
    if concentration_uM is None or concentration_uM <= 0:
        raise CandidateLedgerError(
            "assessed exposure requires positive nominal_concentration_uM"
        )
    if exposure_class == "leq_2um" and concentration_uM > 2:
        raise CandidateLedgerError(
            "leq_2um exposure requires nominal_concentration_uM no greater than 2"
        )
    if exposure_class == "exploratory_5um" and concentration_uM > 5:
        raise CandidateLedgerError(
            "exploratory_5um exposure requires nominal_concentration_uM no greater than 5"
        )
    if (
        exposure_class == "candidate_specific_plausible"
        and concentration_uM > MAX_CANDIDATE_SPECIFIC_UM
    ):
        raise CandidateLedgerError(
            "candidate_specific_plausible exposure exceeds the bounded 1000 uM ledger limit"
        )
    if exposure_class == "nontranslational_high" and concentration_uM <= 5:
        raise CandidateLedgerError(
            "nontranslational_high exposure requires nominal_concentration_uM above 5"
        )


def _causal_distance_score(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
        raise CandidateLedgerError(
            "causal_distance_score: expected an integer from 0 through 4"
        )
    return value


def _experimental_priority(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CandidateLedgerError(
            "experimental_priority: expected a positive integer or null"
        )
    return value


def _string_sequence(
    value: Any,
    *,
    location: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CandidateLedgerError(f"{location}: expected an array")
    if not value and not allow_empty:
        raise CandidateLedgerError(f"{location}: at least one item is required")
    result = tuple(
        _text(item, location=f"{location}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        raise CandidateLedgerError(f"{location}: duplicate items are forbidden")
    return result


def _identifier_sequence(
    value: Any,
    *,
    location: str,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CandidateLedgerError(f"{location}: expected an array")
    result = tuple(
        _identifier(item, location=f"{location}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        raise CandidateLedgerError(f"{location}: duplicate items are forbidden")
    return result


def _expected_causal_distance_score(
    direct_target_evidence: str,
    exact_allele_evidence: str,
    checkpoint_evidence: str,
    human_pd_evidence: str,
) -> int:
    return sum(
        1
        for status in (
            direct_target_evidence,
            exact_allele_evidence,
            checkpoint_evidence,
            human_pd_evidence,
        )
        if status == "positive"
    )


@dataclass(frozen=True)
class SearchProtocol:
    """Declared search axes for a candidate ledger, independent of ranking."""

    protocol_id: str
    searched_on: str
    query_axes: Sequence[str]
    exclusion_axes: Sequence[str]
    notes: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "protocol_id",
            _identifier(self.protocol_id, location="search_protocol.protocol_id"),
        )
        object.__setattr__(
            self,
            "searched_on",
            _date(self.searched_on, location="search_protocol.searched_on"),
        )
        object.__setattr__(
            self,
            "query_axes",
            _string_sequence(
                self.query_axes,
                location="search_protocol.query_axes",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "exclusion_axes",
            _string_sequence(
                self.exclusion_axes,
                location="search_protocol.exclusion_axes",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "notes",
            _text(self.notes, location="search_protocol.notes", minimum=10),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "searched_on": self.searched_on,
            "query_axes": list(self.query_axes),
            "exclusion_axes": list(self.exclusion_axes),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SearchProtocol":
        if not isinstance(value, Mapping):
            raise CandidateLedgerError("search_protocol must be an object")
        expected = set(cls.__dataclass_fields__)
        if set(value) != expected:
            raise CandidateLedgerError(
                f"search_protocol fields must be exactly {sorted(expected)}"
            )
        return cls(**{key: value[key] for key in expected})


@dataclass(frozen=True)
class ReplicationDesign:
    """Opaque, non-participant identifiers for a frozen replication plan."""

    discovery_site_id: str | None
    replication_site_id: str | None
    discovery_edit_event_family_ids: Sequence[str]
    replication_edit_event_family_ids: Sequence[str]
    frozen_protocol_identity_id: str | None
    frozen_exposure_identity_id: str | None
    frozen_endpoint_identity_id: str | None
    frozen_margin_identity_id: str | None
    frozen_analysis_identity_id: str | None
    analytic_transfer_result_sha256: str | None
    site2_blinding_state: str
    site2_blinding_evidence_sha256: str | None

    def __post_init__(self) -> None:
        for name in (
            "discovery_site_id",
            "replication_site_id",
            "frozen_protocol_identity_id",
            "frozen_exposure_identity_id",
            "frozen_endpoint_identity_id",
            "frozen_margin_identity_id",
            "frozen_analysis_identity_id",
        ):
            object.__setattr__(
                self,
                name,
                _optional_identifier(
                    getattr(self, name),
                    location=f"replication_design.{name}",
                ),
            )
        for name in (
            "discovery_edit_event_family_ids",
            "replication_edit_event_family_ids",
        ):
            object.__setattr__(
                self,
                name,
                _identifier_sequence(
                    getattr(self, name),
                    location=f"replication_design.{name}",
                ),
            )
        object.__setattr__(
            self,
            "analytic_transfer_result_sha256",
            _optional_sha256_fingerprint(
                self.analytic_transfer_result_sha256,
                location="replication_design.analytic_transfer_result_sha256",
            ),
        )
        object.__setattr__(
            self,
            "site2_blinding_state",
            _enum(
                self.site2_blinding_state,
                SITE2_BLINDING_STATES,
                location="replication_design.site2_blinding_state",
            ),
        )
        object.__setattr__(
            self,
            "site2_blinding_evidence_sha256",
            _optional_sha256_fingerprint(
                self.site2_blinding_evidence_sha256,
                location="replication_design.site2_blinding_evidence_sha256",
            ),
        )
        if (
            self.analytic_transfer_result_sha256 is not None
            and self.analytic_transfer_result_sha256
            == self.site2_blinding_evidence_sha256
        ):
            raise CandidateLedgerError(
                "replication_design analytic-transfer and site-2 blinding "
                "evidence fingerprints must identify distinct receipts"
            )

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        required_identifiers = (
            "discovery_site_id",
            "replication_site_id",
            "frozen_protocol_identity_id",
            "frozen_exposure_identity_id",
            "frozen_endpoint_identity_id",
            "frozen_margin_identity_id",
            "frozen_analysis_identity_id",
        )
        blockers.extend(
            f"{name}:missing"
            for name in required_identifiers
            if getattr(self, name) is None
        )
        if not self.discovery_edit_event_family_ids:
            blockers.append("discovery_edit_event_family_ids:missing")
        if not self.replication_edit_event_family_ids:
            blockers.append("replication_edit_event_family_ids:missing")
        if (
            self.discovery_site_id is not None
            and self.discovery_site_id == self.replication_site_id
        ):
            blockers.append("replication_site_id:not_independent")
        overlap = sorted(
            set(self.discovery_edit_event_family_ids)
            & set(self.replication_edit_event_family_ids)
        )
        if overlap:
            blockers.append("edit_event_family_ids:overlap")
        return tuple(blockers)

    @property
    def complete_and_independent(self) -> bool:
        return not self.blockers

    @property
    def replication_evidence_blockers(self) -> tuple[str, ...]:
        blockers = list(self.blockers)
        if self.analytic_transfer_result_sha256 is None:
            blockers.append("analytic_transfer_result_sha256:missing")
        if self.site2_blinding_state != "blinded":
            blockers.append(f"site2_blinding_state:{self.site2_blinding_state}")
        if self.site2_blinding_evidence_sha256 is None:
            blockers.append("site2_blinding_evidence_sha256:missing")
        return tuple(blockers)

    @property
    def receipt_bound_blinded_and_independent(self) -> bool:
        return not self.replication_evidence_blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "discovery_site_id": self.discovery_site_id,
            "replication_site_id": self.replication_site_id,
            "discovery_edit_event_family_ids": list(
                self.discovery_edit_event_family_ids
            ),
            "replication_edit_event_family_ids": list(
                self.replication_edit_event_family_ids
            ),
            "frozen_protocol_identity_id": self.frozen_protocol_identity_id,
            "frozen_exposure_identity_id": self.frozen_exposure_identity_id,
            "frozen_endpoint_identity_id": self.frozen_endpoint_identity_id,
            "frozen_margin_identity_id": self.frozen_margin_identity_id,
            "frozen_analysis_identity_id": self.frozen_analysis_identity_id,
            "analytic_transfer_result_sha256": (
                self.analytic_transfer_result_sha256
            ),
            "site2_blinding_state": self.site2_blinding_state,
            "site2_blinding_evidence_sha256": (
                self.site2_blinding_evidence_sha256
            ),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ReplicationDesign":
        if not isinstance(value, Mapping):
            raise CandidateLedgerError("replication_design must be an object")
        expected = set(cls.__dataclass_fields__)
        if set(value) != expected:
            raise CandidateLedgerError(
                f"replication_design fields must be exactly {sorted(expected)}"
            )
        return cls(**{key: value[key] for key in expected})


@dataclass(frozen=True)
class SampleStewardshipPromotion:
    """Bind a replicated phenocopy to sample held-out and replication receipts."""

    held_out_assay_id: str
    replication_assay_id: str
    held_out_receipt_id: str
    replication_receipt_id: str
    held_out_receipt_sha256: str
    replication_receipt_sha256: str
    sample_plan_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "held_out_assay_id",
            "replication_assay_id",
            "held_out_receipt_id",
            "replication_receipt_id",
        ):
            object.__setattr__(
                self,
                name,
                _identifier(getattr(self, name), location=name),
            )
        for name in (
            "held_out_receipt_sha256",
            "replication_receipt_sha256",
            "sample_plan_sha256",
        ):
            digest = getattr(self, name)
            if not isinstance(digest, str) or _SHA256_FINGERPRINT.fullmatch(digest) is None:
                raise CandidateLedgerError(
                    f"{name}: expected a lower-case SHA-256 fingerprint"
                )
        if self.held_out_assay_id == self.replication_assay_id:
            raise CandidateLedgerError(
                "sample_stewardship_promotion held-out and replication assay "
                "ids must differ"
            )
        if self.held_out_receipt_id == self.replication_receipt_id:
            raise CandidateLedgerError(
                "sample_stewardship_promotion held-out and replication receipt "
                "ids must differ"
            )
        if self.held_out_receipt_sha256 == self.replication_receipt_sha256:
            raise CandidateLedgerError(
                "sample_stewardship_promotion held-out and replication receipt "
                "digests must differ"
            )

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in SAMPLE_STEWARDSHIP_PROMOTION_FIELDS}

    @classmethod
    def from_dict(cls, value: Any) -> "SampleStewardshipPromotion":
        if not isinstance(value, Mapping):
            raise CandidateLedgerError(
                "sample_stewardship_promotion must be an object"
            )
        expected = set(SAMPLE_STEWARDSHIP_PROMOTION_FIELDS)
        if set(value) != expected:
            raise CandidateLedgerError(
                "sample_stewardship_promotion fields must be exactly "
                + str(sorted(expected))
            )
        return cls(**{key: value[key] for key in SAMPLE_STEWARDSHIP_PROMOTION_FIELDS})


def sample_stewardship_plan_sha256(plan: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 of a submitted sample-stewardship plan."""

    if not isinstance(plan, Mapping):
        raise CandidateLedgerError("sample_plan must be an object")
    try:
        encoded = json.dumps(
            plan,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise CandidateLedgerError(
            "sample_plan cannot be canonicalized to strict JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _assay_by_id(plan: Mapping[str, Any], assay_id: str) -> Mapping[str, Any]:
    assays = plan.get("assays")
    if isinstance(assays, (str, bytes)) or not isinstance(assays, Sequence):
        raise CandidateLedgerError("sample_plan.assays: expected an array")
    matches = [
        assay
        for assay in assays
        if isinstance(assay, Mapping) and assay.get("assay_id") == assay_id
    ]
    if len(matches) != 1:
        raise CandidateLedgerError(
            f"sample_plan must contain exactly one assay {assay_id}"
        )
    return matches[0]


def _positive_completion(plan: Mapping[str, Any], assay_id: str) -> Mapping[str, Any]:
    completed = plan.get("completed")
    if not isinstance(completed, Mapping):
        raise CandidateLedgerError("sample_plan.completed must be an object")
    receipt = completed.get(assay_id)
    if not isinstance(receipt, Mapping):
        raise CandidateLedgerError(
            f"sample_plan is missing a completion receipt for {assay_id}"
        )
    if receipt.get("outcome") != "positive":
        raise CandidateLedgerError(
            f"sample_plan completion for {assay_id} must be positive"
        )
    return receipt


def _assays_by_id(plan: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    assays = plan.get("assays")
    if isinstance(assays, (str, bytes)) or not isinstance(assays, Sequence):
        raise CandidateLedgerError("sample_plan.assays: expected an array")
    result: dict[str, Mapping[str, Any]] = {}
    for assay in assays:
        if not isinstance(assay, Mapping) or "assay_id" not in assay:
            raise CandidateLedgerError("sample_plan.assays entries must name assay_id")
        assay_id = assay["assay_id"]
        if assay_id in result:
            raise CandidateLedgerError(f"sample_plan has duplicate assay {assay_id}")
        result[str(assay_id)] = assay
    return result


def _ancestor_ids(
    assay_id: str, assays_by_id: Mapping[str, Mapping[str, Any]]
) -> tuple[str, ...]:
    found: list[str] = []
    stack = list(assays_by_id[assay_id].get("prerequisites") or [])
    seen: set[str] = set()
    while stack:
        node = str(stack.pop())
        if node in seen:
            continue
        seen.add(node)
        found.append(node)
        parent = assays_by_id.get(node)
        if parent is None:
            raise CandidateLedgerError(
                f"sample_plan prerequisite {node} is not a declared assay"
            )
        stack.extend(parent.get("prerequisites") or [])
    return tuple(found)


def _same_lane_context_assay(
    plan: Mapping[str, Any],
    *,
    held_out_assay_id: str,
    discovery_lane: str,
) -> Mapping[str, Any]:
    assays_by_id = _assays_by_id(plan)
    contexts = [
        assays_by_id[assay_id]
        for assay_id in _ancestor_ids(held_out_assay_id, assays_by_id)
        if assays_by_id[assay_id].get("context_qualification") is not None
        and assays_by_id[assay_id].get("discovery_lane") == discovery_lane
    ]
    if len(contexts) != 1:
        raise CandidateLedgerError(
            "replicated functional phenocopy requires exactly one same-lane "
            "context-qualification ancestor"
        )
    return contexts[0]


def _assert_sample_promotions(
    ledger: "CandidateLedger",
    sample_plan: Mapping[str, Any],
) -> None:
    if not isinstance(sample_plan, Mapping):
        raise CandidateLedgerError("sample_plan must be an object")
    plan_digest = sample_stewardship_plan_sha256(sample_plan)
    try:
        working = json.loads(
            json.dumps(sample_plan, ensure_ascii=True, allow_nan=False),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise CandidateLedgerError(
            "sample_plan cannot be round-tripped through strict JSON"
        ) from exc
    try:
        assess_sample_stewardship(working)
    except SampleStewardshipError as exc:
        raise CandidateLedgerError(
            f"sample-stewardship plan is invalid: {exc}"
        ) from exc

    seen_receipt_ids: set[str] = set()
    seen_receipt_digests: set[str] = set()
    for entry in ledger.entries:
        promotion = entry.sample_stewardship_promotion
        if promotion is None:
            continue
        effective_source = (
            entry.parent_source_class
            if entry.source_class == "derived_evidence"
            else entry.source_class
        )
        if working.get("synthetic_only") is True and (
            entry.privacy_class != "synthetic"
            or effective_source != "synthetic_fixture"
        ):
            raise CandidateLedgerError(
                "synthetic sample-stewardship evidence may bind only synthetic "
                "fixture candidate evidence"
            )
        if promotion.sample_plan_sha256 != plan_digest:
            raise CandidateLedgerError(
                "sample_stewardship_promotion.sample_plan_sha256 does not match "
                "the submitted sample plan"
            )
        held_assay = _assay_by_id(working, promotion.held_out_assay_id)
        replication_assay = _assay_by_id(working, promotion.replication_assay_id)
        if held_assay.get("stage") != "HELD_OUT":
            raise CandidateLedgerError(
                "sample_stewardship_promotion.held_out_assay_id must name a "
                "held-out assay"
            )
        if replication_assay.get("stage") != "REPLICATION":
            raise CandidateLedgerError(
                "sample_stewardship_promotion.replication_assay_id must name a "
                "replication assay"
            )
        if held_assay.get("discovery_lane") != entry.discovery_lane:
            raise CandidateLedgerError(
                "held-out assay discovery lane must match the candidate"
            )
        if replication_assay.get("discovery_lane") != entry.discovery_lane:
            raise CandidateLedgerError(
                "replication assay discovery lane must match the candidate"
            )
        held_receipt = _positive_completion(working, promotion.held_out_assay_id)
        replication_receipt = _positive_completion(
            working, promotion.replication_assay_id
        )
        if held_receipt.get("receipt_id") != promotion.held_out_receipt_id:
            raise CandidateLedgerError(
                "held-out receipt_id does not match the sample completion"
            )
        if replication_receipt.get("receipt_id") != promotion.replication_receipt_id:
            raise CandidateLedgerError(
                "replication receipt_id does not match the sample completion"
            )
        if held_receipt.get("receipt_sha256") != promotion.held_out_receipt_sha256:
            raise CandidateLedgerError(
                "held-out receipt digest does not match the sample completion"
            )
        if (
            replication_receipt.get("receipt_sha256")
            != promotion.replication_receipt_sha256
        ):
            raise CandidateLedgerError(
                "replication receipt digest does not match the sample completion"
            )
        for receipt_id in (
            promotion.held_out_receipt_id,
            promotion.replication_receipt_id,
        ):
            if receipt_id in seen_receipt_ids:
                raise CandidateLedgerError(
                    "sample completion receipts cannot promote two candidates"
                )
            seen_receipt_ids.add(receipt_id)
        for digest in (
            promotion.held_out_receipt_sha256,
            promotion.replication_receipt_sha256,
        ):
            if digest in seen_receipt_digests:
                raise CandidateLedgerError(
                    "sample completion receipts cannot promote two candidates"
                )
            seen_receipt_digests.add(digest)

        held_lock = held_assay.get("held_out_lock")
        replication_lock = replication_assay.get("replication_lock")
        if not isinstance(held_lock, Mapping) or not isinstance(
            replication_lock, Mapping
        ):
            raise CandidateLedgerError(
                "sample held-out and replication assays must carry freeze locks"
            )
        design = entry.replication_design
        for ledger_field, sample_field in (
            ("frozen_exposure_identity_id", "frozen_exposure_id"),
            ("frozen_endpoint_identity_id", "frozen_endpoint_id"),
            ("frozen_margin_identity_id", "frozen_margin_id"),
        ):
            ledger_value = getattr(design, ledger_field)
            held_value = held_lock.get(sample_field)
            replication_value = replication_lock.get(sample_field)
            if ledger_value != held_value or ledger_value != replication_value:
                raise CandidateLedgerError(
                    f"replication_design.{ledger_field} must match the same-lane "
                    "sample held-out and replication frozen estimand"
                )
        for ledger_field, sample_field in (
            ("frozen_protocol_identity_id", "frozen_protocol_id"),
            ("frozen_analysis_identity_id", "frozen_analysis_id"),
        ):
            if getattr(design, ledger_field) != replication_lock.get(sample_field):
                raise CandidateLedgerError(
                    f"replication_design.{ledger_field} must match the sample "
                    "replication freeze lock"
                )
        evidence = replication_receipt.get("promotion_evidence")
        if not isinstance(evidence, Mapping):
            raise CandidateLedgerError(
                "positive replication receipt requires promotion_evidence"
            )
        if design.discovery_site_id != evidence.get("discovery_site_id"):
            raise CandidateLedgerError(
                "replication_design.discovery_site_id must match sample "
                "promotion_evidence"
            )
        if design.replication_site_id != evidence.get("replication_site_id"):
            raise CandidateLedgerError(
                "replication_design.replication_site_id must match sample "
                "promotion_evidence"
            )
        if tuple(design.discovery_edit_event_family_ids) != tuple(
            evidence.get("discovery_event_family_ids") or ()
        ):
            raise CandidateLedgerError(
                "replication_design.discovery_edit_event_family_ids must match "
                "sample promotion_evidence"
            )
        if tuple(design.replication_edit_event_family_ids) != tuple(
            evidence.get("replication_event_family_ids") or ()
        ):
            raise CandidateLedgerError(
                "replication_design.replication_edit_event_family_ids must match "
                "sample promotion_evidence"
            )
        if design.analytic_transfer_result_sha256 != evidence.get(
            "analytic_transfer_result_sha256"
        ):
            raise CandidateLedgerError(
                "replication_design.analytic_transfer_result_sha256 must match "
                "sample promotion_evidence"
            )
        if evidence.get("site2_blinding_state") != "blinded":
            raise CandidateLedgerError(
                "sample promotion_evidence site-2 blinding must be blinded"
            )
        if design.site2_blinding_state != "blinded":
            raise CandidateLedgerError(
                "replication_design.site2_blinding_state must be blinded"
            )
        if design.site2_blinding_evidence_sha256 != evidence.get(
            "site2_blinding_evidence_sha256"
        ):
            raise CandidateLedgerError(
                "replication_design.site2_blinding_evidence_sha256 must match "
                "sample promotion_evidence"
            )
        context_assay = _same_lane_context_assay(
            working,
            held_out_assay_id=promotion.held_out_assay_id,
            discovery_lane=entry.discovery_lane,
        )
        _positive_completion(working, str(context_assay["assay_id"]))
        context = context_assay.get("context_qualification")
        if not isinstance(context, Mapping):
            raise CandidateLedgerError(
                "same-lane context-qualification ancestor must carry a context object"
            )
        if context.get("mitotic_context_class") != entry.mitotic_context_class:
            raise CandidateLedgerError(
                "sample context mitotic_context_class must match the candidate"
            )
        if context.get("transformation_state") != entry.transformation_state:
            raise CandidateLedgerError(
                "sample context transformation_state must match the candidate"
            )
        if (
            working.get("synthetic_only") is True
            and entry.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
        ):
            raise CandidateLedgerError(
                "synthetic-only sample-stewardship evidence cannot authorize "
                "a biologically interpreted active_lead"
            )


@dataclass(frozen=True)
class RescueGates:
    """Structured gates required before any functional advancement claim."""

    correction_rescue: str
    reciprocal_recreation: str
    branch_opened: str
    exposure_validity: str
    proximal_engagement: str
    correction_like_function: str
    native_fidelity: str
    completion_equivalence: str
    clone_safety: str
    analysis_lock_and_multiplicity: str
    discovery_confirmation_separation: str
    matched_control_and_retained_domain_safety: str
    therapeutic_context_and_architecture_lineage: str
    analytic_transfer_pass: str
    biological_replication_pass: str
    blinded_replication_execution: str
    independent_replication: str
    replication_provenance: str

    def __post_init__(self) -> None:
        for name in RESCUE_GATE_NAMES:
            object.__setattr__(
                self,
                name,
                _enum(
                    getattr(self, name),
                    RESCUE_GATE_STATES,
                    location=f"rescue_gates.{name}",
                ),
            )

    @property
    def all_pass(self) -> bool:
        return all(getattr(self, name) == "pass" for name in RESCUE_GATE_NAMES)

    def blockers(self) -> tuple[str, ...]:
        return tuple(
            f"{name}:{getattr(self, name)}"
            for name in RESCUE_GATE_NAMES
            if getattr(self, name) != "pass"
        )

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in RESCUE_GATE_NAMES}

    @classmethod
    def from_dict(cls, value: Any) -> "RescueGates":
        if not isinstance(value, Mapping):
            raise CandidateLedgerError("rescue_gates must be an object")
        expected = set(RESCUE_GATE_NAMES)
        if set(value) != expected:
            raise CandidateLedgerError(
                f"rescue_gates fields must be exactly {sorted(expected)}"
            )
        return cls(**{key: value[key] for key in RESCUE_GATE_NAMES})


@dataclass(frozen=True)
class CandidateEntry:
    """One normalized audit row for a Track 2 candidate, control, or gap."""

    candidate_id: str
    role: str
    experimental_priority: int | None
    program_gate: str
    claim: str
    privacy_class: Literal["public", "synthetic", "controlled"]
    direction: Literal["supports", "contradicts", "neutral"]
    assessment_status: Literal["positive", "negative", "not_assessable"]
    decision_effect: str
    advancement_state: str
    functional_hit_state: str
    screen_context: str
    no_hit_basis: str
    translation_state: str
    discovery_lane: str
    therapeutic_context: str
    architecture_lineage_state: str
    mitotic_context_class: str
    transformation_state: str
    rescue_gates: RescueGates
    replication_design: ReplicationDesign
    sample_stewardship_promotion: SampleStewardshipPromotion | None
    source_class: str
    source_identifier: str
    source_version: str | None
    source_url: str | None
    search_date: str
    model_system: str
    nominal_concentration_uM: int | float | None
    exposure_class: str
    direct_target_evidence: str
    exact_allele_evidence: str
    checkpoint_evidence: str
    human_pd_evidence: str
    pediatric_information: str
    oncology_risk: str
    regulatory_eligibility: str
    result: str | int | float | bool | None
    unit: str | None
    independent_replication: str
    uncertainty: str
    counterevidence: Sequence[str]
    limitations: Sequence[str]
    not_assessable_reason: str | None
    causal_distance_score: int
    parent_source_class: str | None = None
    parent_candidate_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _identifier(self.candidate_id, location="candidate_id"),
        )
        object.__setattr__(self, "role", _enum(self.role, ROLES, location="role"))
        object.__setattr__(
            self,
            "experimental_priority",
            _experimental_priority(self.experimental_priority),
        )
        object.__setattr__(
            self,
            "program_gate",
            _enum(self.program_gate, PROGRAM_GATES, location="program_gate"),
        )
        object.__setattr__(
            self, "claim", _text(self.claim, location="claim", minimum=10)
        )
        object.__setattr__(
            self,
            "privacy_class",
            _enum(self.privacy_class, PRIVACY_CLASSES, location="privacy_class"),
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
            self,
            "decision_effect",
            _enum(self.decision_effect, DECISION_EFFECTS, location="decision_effect"),
        )
        object.__setattr__(
            self,
            "advancement_state",
            _enum(
                self.advancement_state,
                ADVANCEMENT_STATES,
                location="advancement_state",
            ),
        )
        object.__setattr__(
            self,
            "functional_hit_state",
            _enum(
                self.functional_hit_state,
                FUNCTIONAL_HIT_STATES,
                location="functional_hit_state",
            ),
        )
        object.__setattr__(
            self,
            "screen_context",
            _enum(self.screen_context, SCREEN_CONTEXTS, location="screen_context"),
        )
        object.__setattr__(
            self,
            "no_hit_basis",
            _enum(self.no_hit_basis, NO_HIT_BASES, location="no_hit_basis"),
        )
        object.__setattr__(
            self,
            "translation_state",
            _enum(
                self.translation_state,
                TRANSLATION_STATES,
                location="translation_state",
            ),
        )
        object.__setattr__(
            self,
            "discovery_lane",
            _enum(self.discovery_lane, DISCOVERY_LANES, location="discovery_lane"),
        )
        object.__setattr__(
            self,
            "therapeutic_context",
            _enum(
                self.therapeutic_context,
                THERAPEUTIC_CONTEXTS,
                location="therapeutic_context",
            ),
        )
        object.__setattr__(
            self,
            "architecture_lineage_state",
            _enum(
                self.architecture_lineage_state,
                ARCHITECTURE_LINEAGE_STATES,
                location="architecture_lineage_state",
            ),
        )
        object.__setattr__(
            self,
            "mitotic_context_class",
            _enum(
                self.mitotic_context_class,
                MITOTIC_CONTEXT_CLASSES,
                location="mitotic_context_class",
            ),
        )
        object.__setattr__(
            self,
            "transformation_state",
            _enum(
                self.transformation_state,
                TRANSFORMATION_STATES,
                location="transformation_state",
            ),
        )
        rescue_gates = self.rescue_gates
        if not isinstance(rescue_gates, RescueGates):
            rescue_gates = RescueGates.from_dict(rescue_gates)
        object.__setattr__(self, "rescue_gates", rescue_gates)
        replication_design = self.replication_design
        if not isinstance(replication_design, ReplicationDesign):
            replication_design = ReplicationDesign.from_dict(replication_design)
        object.__setattr__(self, "replication_design", replication_design)
        promotion = self.sample_stewardship_promotion
        if promotion is None:
            object.__setattr__(self, "sample_stewardship_promotion", None)
        elif isinstance(promotion, SampleStewardshipPromotion):
            object.__setattr__(self, "sample_stewardship_promotion", promotion)
        else:
            object.__setattr__(
                self,
                "sample_stewardship_promotion",
                SampleStewardshipPromotion.from_dict(promotion),
            )
        object.__setattr__(
            self,
            "source_class",
            _enum(self.source_class, SOURCE_CLASSES, location="source_class"),
        )
        if self.parent_source_class is None:
            parent_source_class = None
        else:
            parent_source_class = _enum(
                self.parent_source_class,
                PARENT_SOURCE_CLASSES,
                location="parent_source_class",
            )
        object.__setattr__(self, "parent_source_class", parent_source_class)
        if self.source_class == "derived_evidence":
            if parent_source_class is None:
                raise CandidateLedgerError(
                    "derived_evidence requires parent_source_class"
                )
            if self.parent_candidate_id is None:
                raise CandidateLedgerError(
                    "derived_evidence requires parent_candidate_id"
                )
            effective_source = parent_source_class
        else:
            if parent_source_class is not None:
                raise CandidateLedgerError(
                    "parent_source_class is restricted to derived_evidence"
                )
            if self.parent_candidate_id is not None:
                raise CandidateLedgerError(
                    "parent_candidate_id is restricted to derived_evidence"
                )
            effective_source = self.source_class
        if self.parent_candidate_id is not None:
            object.__setattr__(
                self,
                "parent_candidate_id",
                _identifier(
                    self.parent_candidate_id, location="parent_candidate_id"
                ),
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
            self, "search_date", _date(self.search_date, location="search_date")
        )
        object.__setattr__(
            self,
            "model_system",
            _text(self.model_system, location="model_system", maximum=2_000),
        )
        object.__setattr__(
            self,
            "nominal_concentration_uM",
            _optional_finite_number(
                self.nominal_concentration_uM,
                location="nominal_concentration_uM",
            ),
        )
        object.__setattr__(
            self,
            "exposure_class",
            _enum(self.exposure_class, EXPOSURE_CLASSES, location="exposure_class"),
        )
        _validate_exposure_concentration(
            self.exposure_class,
            self.nominal_concentration_uM,
        )
        object.__setattr__(
            self,
            "direct_target_evidence",
            _enum(
                self.direct_target_evidence,
                ASSESSMENT_STATUSES,
                location="direct_target_evidence",
            ),
        )
        object.__setattr__(
            self,
            "exact_allele_evidence",
            _enum(
                self.exact_allele_evidence,
                ASSESSMENT_STATUSES,
                location="exact_allele_evidence",
            ),
        )
        object.__setattr__(
            self,
            "checkpoint_evidence",
            _enum(
                self.checkpoint_evidence,
                ASSESSMENT_STATUSES,
                location="checkpoint_evidence",
            ),
        )
        object.__setattr__(
            self,
            "human_pd_evidence",
            _enum(
                self.human_pd_evidence,
                ASSESSMENT_STATUSES,
                location="human_pd_evidence",
            ),
        )
        object.__setattr__(
            self,
            "pediatric_information",
            _enum(
                self.pediatric_information,
                PEDIATRIC_INFORMATION_STATES,
                location="pediatric_information",
            ),
        )
        object.__setattr__(
            self,
            "oncology_risk",
            _enum(self.oncology_risk, ONCOLOGY_RISKS, location="oncology_risk"),
        )
        object.__setattr__(
            self,
            "regulatory_eligibility",
            _enum(
                self.regulatory_eligibility,
                REGULATORY_ELIGIBILITY_STATES,
                location="regulatory_eligibility",
            ),
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
            "limitations",
            _string_sequence(
                self.limitations, location="limitations", allow_empty=False
            ),
        )
        object.__setattr__(
            self,
            "causal_distance_score",
            _causal_distance_score(self.causal_distance_score),
        )

        if effective_source.startswith("public_") and self.source_url is None:
            raise CandidateLedgerError("public source classes require source_url")
        if effective_source == "official_label" and self.source_url is None:
            raise CandidateLedgerError(
                "official_label source class requires source_url"
            )
        if effective_source in SOURCES_CANNOT_MINT_POSITIVE_AXES:
            minted = [
                axis
                for axis in SOFTWARE_CANNOT_MINT_POSITIVE_AXES
                if getattr(self, axis) == "positive"
            ]
            if minted:
                raise CandidateLedgerError(
                    f"{effective_source} cannot mint positive exact-allele, "
                    "checkpoint, direct-target, or human-PD evidence"
                )
        if (
            effective_source in SOURCES_CANNOT_OCCUPY_LEAD_ADVANCEMENT
            and (
                self.role == "lead"
                or self.advancement_state in LEAD_ADVANCEMENT_STATES
            )
        ):
            raise CandidateLedgerError(
                f"{effective_source} cannot occupy lead advancement"
            )
        if (
            effective_source in SOURCES_CANNOT_OCCUPY_PHARMACOLOGIC_ROLES
            and self.role in PHARMACOLOGIC_RANKING_ROLES
        ):
            raise CandidateLedgerError(
                f"{effective_source} cannot occupy a pharmacologic ranking role"
            )
        if (
            self.privacy_class in PUBLIC_PRIVACY_CLASSES
            and effective_source == "controlled_source"
        ):
            raise CandidateLedgerError(
                "public or synthetic entries cannot label a controlled source"
            )
        if (
            effective_source in SOURCES_REQUIRE_SYNTHETIC_PRIVACY
            and self.privacy_class != "synthetic"
        ):
            raise CandidateLedgerError(
                "synthetic_fixture requires privacy_class synthetic"
            )
        if (
            effective_source in SOURCES_REQUIRE_PUBLIC_PRIVACY
            and self.privacy_class != "public"
        ):
            raise CandidateLedgerError(
                f"{effective_source} requires privacy_class public"
            )
        if (
            self.advancement_state in LEAD_ADVANCEMENT_STATES
            and self.role not in PHARMACOLOGIC_RANKING_ROLES
        ):
            raise CandidateLedgerError(
                f"advancement_state {self.advancement_state} requires a "
                "pharmacologic role"
            )
        if (
            self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
            and self.role != "lead"
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires role lead"
            )
        if (
            self.role == "lead"
            and self.advancement_state not in LEAD_ADVANCEMENT_STATES
        ):
            raise CandidateLedgerError(
                "role lead requires advancement_state active_lead or conditional_hold"
            )
        if (
            self.experimental_priority is not None
            and self.role not in PHARMACOLOGIC_RANKING_ROLES
        ):
            raise CandidateLedgerError(
                "experimental_priority is restricted to pharmacologic rows"
            )
        if (
            self.decision_effect == "promote"
            and self.advancement_state not in LEAD_ADVANCEMENT_STATES
        ):
            raise CandidateLedgerError(
                "decision_effect promote requires advancement_state "
                "active_lead or conditional_hold"
            )
        if self.advancement_state in LEAD_ADVANCEMENT_STATES and (
            self.assessment_status != "positive"
            or self.direction != "supports"
            or self.decision_effect == "exclude"
        ):
            raise CandidateLedgerError(
                "conditional_hold or active_lead requires positive supporting "
                "evidence and cannot have decision_effect exclude"
            )
        if (
            self.advancement_state == "conditional_hold"
            and self.decision_effect == "demote"
        ):
            raise CandidateLedgerError(
                "advancement_state conditional_hold cannot have "
                "decision_effect demote"
            )

        def nonpassing_gates(names: Sequence[str]) -> tuple[str, ...]:
            return tuple(
                f"{name}:{getattr(self.rescue_gates, name)}"
                for name in names
                if getattr(self.rescue_gates, name) != "pass"
            )

        def require_replication_pending(state: str) -> None:
            if (
                self.independent_replication != "not_attempted"
                or self.rescue_gates.analytic_transfer_pass != "not_attempted"
                or self.rescue_gates.biological_replication_pass
                != "not_attempted"
                or self.rescue_gates.blinded_replication_execution
                != "not_attempted"
                or self.rescue_gates.independent_replication != "not_attempted"
                or self.rescue_gates.replication_provenance != "not_attempted"
                or self.replication_design.analytic_transfer_result_sha256
                is not None
                or self.replication_design.site2_blinding_state != "not_attempted"
                or self.replication_design.site2_blinding_evidence_sha256 is not None
            ):
                raise CandidateLedgerError(
                    f"functional_hit_state {state} requires unattempted "
                    "analytic transfer, biological replication, blinded "
                    "replication execution, independent replication, and "
                    "replication provenance with no result or blinding receipts"
                )

        if self.functional_hit_state == "no_hit":
            expected_no_hit_basis = (
                "valid_a0_negative"
                if self.screen_context == "renewable_nonparticipant_a0"
                else "valid_participant_negative"
            )
            if self.no_hit_basis != expected_no_hit_basis:
                raise CandidateLedgerError(
                    "functional_hit_state no_hit requires a context-matched valid "
                    "negative basis; insufficient material, failed controls, "
                    "unmeasured exposure, and screen failure are not no-hit evidence"
                )
            if (
                self.assessment_status != "negative"
                or self.direction != "contradicts"
                or self.decision_effect not in {"demote", "exclude", "no_change"}
                or self.advancement_state
                not in {"rejected", "comparator_only", "not_assessable"}
            ):
                raise CandidateLedgerError(
                    "functional_hit_state no_hit requires negative contradicting "
                    "evidence, a non-advancing decision, and no lead advancement"
                )
        elif self.no_hit_basis in VALID_NO_HIT_BASES:
            raise CandidateLedgerError(
                "valid no_hit_basis requires functional_hit_state no_hit"
            )
        elif (
            self.functional_hit_state in CORRECTION_TRAINED_FUNCTIONAL_HIT_STATES
            and self.no_hit_basis != "not_applicable"
        ):
            raise CandidateLedgerError(
                "functional hit states require no_hit_basis "
                "not_applicable"
            )
        if (
            self.functional_hit_state == "mixed_or_unsafe"
            and self.advancement_state in LEAD_ADVANCEMENT_STATES
        ):
            raise CandidateLedgerError(
                "functional_hit_state mixed_or_unsafe cannot occupy "
                "lead advancement"
            )

        if (
            self.therapeutic_context == "renewable_2d_surrogate"
            or self.architecture_lineage_state == "reduced_2d_surrogate"
        ) and self.translation_state != "mechanism_only":
            raise CandidateLedgerError(
                "2-D surrogate evidence requires translation_state mechanism_only"
            )
        if self.transformation_state in TRANSFORMED_CULTURE_STATES:
            if self.therapeutic_context == "postnatal_nontransformed_proliferative":
                raise CandidateLedgerError(
                    "immortalized or reprogrammed cultures cannot satisfy "
                    "postnatal nontransformed proliferative context"
                )
            if self.translation_state != "mechanism_only":
                raise CandidateLedgerError(
                    "immortalized or reprogrammed cultures require "
                    "translation_state mechanism_only"
                )
        if self.transformation_state == "renewable_nontransformed_isogenic" and (
            self.screen_context != "renewable_nonparticipant_a0"
            or self.translation_state != "mechanism_only"
        ):
            raise CandidateLedgerError(
                "renewable nontransformed isogenic material remains A0 "
                "mechanism_only and cannot mint participant context"
            )
        if (
            self.architecture_lineage_state == "architecture_preserving"
            and self.mitotic_context_class != "epithelial_architecture_dependent"
        ):
            raise CandidateLedgerError(
                "architecture_preserving requires mitotic_context_class "
                "epithelial_architecture_dependent"
            )
        if (
            self.architecture_lineage_state == "lineage_intrinsic_mitotic"
            and self.mitotic_context_class != "lineage_intrinsic_mitotic"
        ):
            raise CandidateLedgerError(
                "lineage_intrinsic_mitotic architecture requires matching "
                "mitotic_context_class"
            )
        if self.translation_state in CONTEXT_QUALIFIED_TRANSLATION_STATES and (
            self.screen_context == "renewable_nonparticipant_a0"
            or self.therapeutic_context
            != "postnatal_nontransformed_proliferative"
            or self.transformation_state != "primary_finite"
            or self.mitotic_context_class not in QUALIFIED_MITOTIC_CONTEXT_CLASSES
            or not self.architecture_matches_mitotic_class()
            or self.rescue_gates.therapeutic_context_and_architecture_lineage
            != "pass"
        ):
            raise CandidateLedgerError(
                "context-qualified translation requires participant-context, "
                "postnatal nontransformed primary-finite proliferative, "
                "lineage-matched architecture evidence and a passed "
                "therapeutic-context/architecture-lineage gate"
            )
        if (
            self.translation_state == "preclinical_replication_ready"
            and self.screen_context != "participant_lineage_tier_b"
        ):
            raise CandidateLedgerError(
                "preclinical_replication_ready requires participant_lineage_tier_b"
            )

        if self.functional_hit_state in CORRECTION_TRAINED_FUNCTIONAL_HIT_STATES:
            if self.advancement_state not in LEAD_ADVANCEMENT_STATES:
                raise CandidateLedgerError(
                    "functional hit states require "
                    "advancement_state conditional_hold or active_lead"
                )
            if (
                self.exact_allele_evidence != "positive"
                or self.checkpoint_evidence != "positive"
            ):
                raise CandidateLedgerError(
                    "functional hit states require positive "
                    "exact_allele_evidence and checkpoint_evidence"
                )
            if self.decision_effect not in ADVANCING_DECISION_EFFECTS:
                raise CandidateLedgerError(
                    "functional hit states require "
                    "decision_effect promote or retain"
                )
            if self.program_gate not in HELD_OUT_PROGRAM_GATES:
                raise CandidateLedgerError(
                    "functional hit states require an "
                    "exposure-or-later program_gate"
                )
            if not self.replication_design.complete_and_independent:
                raise CandidateLedgerError(
                    "functional hit states require a frozen, "
                    "different-site, nonoverlapping-edit-event replication design: "
                    + ", ".join(self.replication_design.blockers)
                )

        if self.functional_hit_state in HELD_OUT_CONFIRMATION_STATES:
            if self.advancement_state != "conditional_hold":
                raise CandidateLedgerError(
                    "held-out functional hit states require advancement_state "
                    "conditional_hold"
                )
            blockers = nonpassing_gates(HELD_OUT_CONFIRMATION_GATE_NAMES)
            if blockers:
                raise CandidateLedgerError(
                    "held-out functional hit states require passed causal-core "
                    "and validity gates: " + ", ".join(blockers)
                )
            require_replication_pending(self.functional_hit_state)

        if (
            self.functional_hit_state == "graded_partial_hit"
            and self.rescue_gates.proximal_engagement != "pass"
        ):
            raise CandidateLedgerError(
                "functional_hit_state graded_partial_hit requires "
                "proximal_engagement pass"
            )
        if (
            self.functional_hit_state == "mechanism_discordant_hit"
            and self.rescue_gates.proximal_engagement
            not in {"fail", "not_attempted"}
        ):
            raise CandidateLedgerError(
                "functional_hit_state mechanism_discordant_hit requires "
                "proximal_engagement fail or not_attempted"
            )

        if self.functional_hit_state == "full_phenocopy_pending_replication":
            if self.translation_state != "preclinical_replication_ready":
                raise CandidateLedgerError(
                    "full_phenocopy_pending_replication requires "
                    "translation_state preclinical_replication_ready"
                )
            if self.advancement_state != "conditional_hold":
                raise CandidateLedgerError(
                    "full_phenocopy_pending_replication requires "
                    "advancement_state conditional_hold"
                )
            blockers = nonpassing_gates(
                FULL_PHENOCOPY_PRE_REPLICATION_GATE_NAMES
            )
            if blockers:
                raise CandidateLedgerError(
                    "full_phenocopy_pending_replication requires all "
                    "pre-replication gates to pass: " + ", ".join(blockers)
                )
            require_replication_pending(self.functional_hit_state)

        if self.functional_hit_state == "replicated_full_phenocopy":
            if self.translation_state != "preclinical_replication_ready":
                raise CandidateLedgerError(
                    "replicated_full_phenocopy requires translation_state "
                    "preclinical_replication_ready"
                )
            if not self.rescue_gates.all_pass:
                raise CandidateLedgerError(
                    "replicated_full_phenocopy requires every structured "
                    "rescue gate to pass"
                )
            if self.independent_replication != "replicated":
                raise CandidateLedgerError(
                    "replicated_full_phenocopy requires replicated independent "
                    "evidence"
                )
            evidence_blockers = (
                self.replication_design.replication_evidence_blockers
            )
            if evidence_blockers:
                raise CandidateLedgerError(
                    "replicated_full_phenocopy requires receipt-bound analytic "
                    "transfer and blinded, independent site-2 evidence: "
                    + ", ".join(evidence_blockers)
                )

        analytic_state = self.rescue_gates.analytic_transfer_pass
        analytic_receipt = self.replication_design.analytic_transfer_result_sha256
        analytic_attempted = analytic_state in {"pass", "fail"}
        if analytic_attempted:
            if analytic_receipt is None or not self.replication_design.complete_and_independent:
                raise CandidateLedgerError(
                    "attempted analytic_transfer_pass requires a result SHA-256 "
                    "and a complete, independent frozen replication design"
                )
        elif analytic_receipt is not None:
            raise CandidateLedgerError(
                "unattempted or inapplicable analytic_transfer_pass requires a "
                "null analytic_transfer_result_sha256"
            )

        blinded_state = self.rescue_gates.blinded_replication_execution
        expected_site2_state = {
            "pass": "blinded",
            "fail": "unblinded",
            "not_attempted": "not_attempted",
            "not_applicable": "not_applicable",
        }[blinded_state]
        if self.replication_design.site2_blinding_state != expected_site2_state:
            raise CandidateLedgerError(
                "blinded_replication_execution is inconsistent with "
                "replication_design.site2_blinding_state"
            )
        blinded_receipt = self.replication_design.site2_blinding_evidence_sha256
        blinded_attempted = blinded_state in {"pass", "fail"}
        if blinded_attempted:
            if blinded_receipt is None or not self.replication_design.complete_and_independent:
                raise CandidateLedgerError(
                    "attempted blinded_replication_execution requires a site-2 "
                    "evidence SHA-256 and a complete, independent frozen "
                    "replication design"
                )
        elif blinded_receipt is not None:
            raise CandidateLedgerError(
                "unattempted or inapplicable blinded_replication_execution "
                "requires a null site2_blinding_evidence_sha256"
            )
        if blinded_state == "pass" and analytic_state != "pass":
            raise CandidateLedgerError(
                "blinded_replication_execution pass requires receipt-bound "
                "analytic_transfer_pass"
            )

        biological_state = self.rescue_gates.biological_replication_pass
        if biological_state in {"pass", "fail"} and (
            not self.replication_design.complete_and_independent
            or not analytic_attempted
            or not blinded_attempted
        ):
            raise CandidateLedgerError(
                "attempted biological_replication_pass requires receipt-bound "
                "analytic transfer, site-2 blinding evidence, and distinct sites "
                "and edit-event families"
            )
        if biological_state == "pass" and (
            analytic_state != "pass"
            or blinded_state != "pass"
            or not self.replication_design.receipt_bound_blinded_and_independent
        ):
            raise CandidateLedgerError(
                "biological_replication_pass pass requires passed receipt-bound "
                "analytic transfer and blinded, independent site-2 execution"
            )

        replication_gate_passed = (
            self.rescue_gates.independent_replication == "pass"
            or self.rescue_gates.replication_provenance == "pass"
            or self.independent_replication == "replicated"
        )
        if replication_gate_passed and (
            biological_state != "pass"
            or self.rescue_gates.independent_replication != "pass"
            or self.independent_replication != "replicated"
            or not self.replication_design.receipt_bound_blinded_and_independent
        ):
            raise CandidateLedgerError(
                "replicated independent/provenance status requires receipt-bound "
                "analytic transfer, blinded site-2 execution, biological "
                "replication pass, and consistent independent-replication states"
            )
        if (
            self.oncology_risk != "caution"
            and self.advancement_state in LEAD_ADVANCEMENT_STATES
        ):
            raise CandidateLedgerError(
                f"oncology_risk {self.oncology_risk} cannot occupy "
                "lead advancement"
            )
        if (
            self.regulatory_eligibility == "expired_or_absent"
            and self.advancement_state in LEAD_ADVANCEMENT_STATES
        ):
            raise CandidateLedgerError(
                "regulatory_eligibility expired_or_absent cannot occupy "
                "lead advancement"
            )
        if (
            self.exposure_class == "nontranslational_high"
            and self.advancement_state in LEAD_ADVANCEMENT_STATES
        ):
            raise CandidateLedgerError(
                "exposure_class nontranslational_high cannot occupy "
                "lead advancement"
            )
        if (
            self.exposure_class == "not_assessable"
            and self.advancement_state in LEAD_ADVANCEMENT_STATES
        ):
            raise CandidateLedgerError(
                "exposure_class not_assessable cannot occupy "
                "lead advancement"
            )
        if self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT and (
            self.exact_allele_evidence != "positive"
            or self.checkpoint_evidence != "positive"
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires positive "
                "exact_allele_evidence and checkpoint_evidence"
            )
        if (
            self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
            and self.functional_hit_state != "replicated_full_phenocopy"
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires functional_hit_state "
                "replicated_full_phenocopy"
            )
        if (
            self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
            and not self.rescue_gates.all_pass
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires every structured rescue gate to pass"
            )
        if (
            self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
            and self.independent_replication != "replicated"
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires replicated independent evidence"
            )
        if (
            self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
            and self.decision_effect not in {"promote", "retain"}
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires decision_effect promote or retain"
            )
        if self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT and (
            self.oncology_risk != "caution"
            or self.regulatory_eligibility
            not in DISPLACEMENT_ELIGIBLE_REGULATORY_STATES
            or self.exposure_class not in DISPLACEMENT_ELIGIBLE_EXPOSURE_CLASSES
            or self.pediatric_information
            not in DISPLACEMENT_ELIGIBLE_PEDIATRIC_STATES
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires passed oncology, "
                "regulatory, pediatric, and candidate-specific exposure screening"
            )
        if (
            self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
            and self.program_gate not in {"segregation", "oncology"}
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead cannot skip nested identity; "
                "program_gate must be segregation or oncology"
            )
        if self.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT and (
            self.translation_state != "preclinical_replication_ready"
            or self.screen_context != "participant_lineage_tier_b"
            or self.therapeutic_context
            != "postnatal_nontransformed_proliferative"
            or self.transformation_state != "primary_finite"
            or not self.architecture_matches_mitotic_class()
            or self.rescue_gates.therapeutic_context_and_architecture_lineage
            != "pass"
        ):
            raise CandidateLedgerError(
                "advancement_state active_lead requires correction-calibrated, "
                "preclinical-replication-ready evidence in a justified postnatal "
                "nontransformed primary-finite proliferative lineage-matched "
                "Tier B context"
            )
        if (
            self.role == "lead"
            and self.direct_target_evidence == "positive"
            and self.exact_allele_evidence != "positive"
        ):
            raise CandidateLedgerError(
                "lead direct_target_evidence cannot be positive without "
                "exact_allele_evidence"
            )
        if self.functional_hit_state == "replicated_full_phenocopy":
            if self.sample_stewardship_promotion is None:
                raise CandidateLedgerError(
                    "replicated_full_phenocopy requires sample-stewardship "
                    "held-out and replication completion receipts"
                )
        elif self.sample_stewardship_promotion is not None:
            raise CandidateLedgerError(
                "sample_stewardship_promotion is restricted to a replicated "
                "functional phenocopy"
            )

        expected_score = _expected_causal_distance_score(
            self.direct_target_evidence,
            self.exact_allele_evidence,
            self.checkpoint_evidence,
            self.human_pd_evidence,
        )
        if self.causal_distance_score != expected_score:
            raise CandidateLedgerError(
                "causal_distance_score must equal the count of positive "
                "direct_target, exact_allele, checkpoint, and human_pd axes"
            )

        if self.assessment_status == "not_assessable":
            if self.direction != "neutral":
                raise CandidateLedgerError(
                    "not_assessable evidence must have neutral direction"
                )
            if self.result is not None or self.unit is not None:
                raise CandidateLedgerError(
                    "not_assessable evidence cannot contain a result or unit"
                )
            if self.independent_replication != "not_assessable":
                raise CandidateLedgerError(
                    "not_assessable evidence requires not_assessable replication state"
                )
            if self.decision_effect not in {"defer", "no_change"}:
                raise CandidateLedgerError(
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
                raise CandidateLedgerError("assessed evidence requires a result")
            if self.not_assessable_reason is not None:
                raise CandidateLedgerError(
                    "assessed evidence must set not_assessable_reason to null"
                )
        if (
            self.role == "no_go"
            and self.advancement_state != "rejected"
        ):
            raise CandidateLedgerError(
                "role no_go requires advancement_state rejected"
            )
        if (
            self.decision_effect == "exclude"
            and self.advancement_state != "rejected"
        ):
            raise CandidateLedgerError(
                "decision_effect exclude requires advancement_state rejected"
            )

    def architecture_matches_mitotic_class(self) -> bool:
        """Return whether architecture state matches the declared mitotic class."""

        expected = MITOTIC_CLASS_TO_ARCHITECTURE.get(self.mitotic_context_class)
        return (
            expected is not None and self.architecture_lineage_state == expected
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "candidate_id": self.candidate_id,
            "role": self.role,
            "experimental_priority": self.experimental_priority,
            "program_gate": self.program_gate,
            "claim": self.claim,
            "privacy_class": self.privacy_class,
            "direction": self.direction,
            "assessment_status": self.assessment_status,
            "decision_effect": self.decision_effect,
            "advancement_state": self.advancement_state,
            "functional_hit_state": self.functional_hit_state,
            "screen_context": self.screen_context,
            "no_hit_basis": self.no_hit_basis,
            "translation_state": self.translation_state,
            "discovery_lane": self.discovery_lane,
            "therapeutic_context": self.therapeutic_context,
            "architecture_lineage_state": self.architecture_lineage_state,
            "mitotic_context_class": self.mitotic_context_class,
            "transformation_state": self.transformation_state,
            "rescue_gates": self.rescue_gates.to_dict(),
            "replication_design": self.replication_design.to_dict(),
            "sample_stewardship_promotion": (
                None
                if self.sample_stewardship_promotion is None
                else self.sample_stewardship_promotion.to_dict()
            ),
            "source_class": self.source_class,
            "source_identifier": self.source_identifier,
            "source_version": self.source_version,
            "source_url": self.source_url,
            "search_date": self.search_date,
            "model_system": self.model_system,
            "nominal_concentration_uM": self.nominal_concentration_uM,
            "exposure_class": self.exposure_class,
            "direct_target_evidence": self.direct_target_evidence,
            "exact_allele_evidence": self.exact_allele_evidence,
            "checkpoint_evidence": self.checkpoint_evidence,
            "human_pd_evidence": self.human_pd_evidence,
            "pediatric_information": self.pediatric_information,
            "oncology_risk": self.oncology_risk,
            "regulatory_eligibility": self.regulatory_eligibility,
            "result": self.result,
            "unit": self.unit,
            "independent_replication": self.independent_replication,
            "uncertainty": self.uncertainty,
            "counterevidence": list(self.counterevidence),
            "limitations": list(self.limitations),
            "not_assessable_reason": self.not_assessable_reason,
            "causal_distance_score": self.causal_distance_score,
        }
        if self.parent_source_class is not None:
            payload["parent_source_class"] = self.parent_source_class
        if self.parent_candidate_id is not None:
            payload["parent_candidate_id"] = self.parent_candidate_id
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "CandidateEntry":
        if not isinstance(value, Mapping):
            raise CandidateLedgerError("candidate entry must be an object")
        expected = set(cls.__dataclass_fields__)
        incoming = set(value)
        extra = incoming - expected
        missing = expected - incoming - {
            "parent_source_class",
            "parent_candidate_id",
        }
        if extra or missing:
            raise CandidateLedgerError(
                f"candidate entry fields must be exactly {sorted(expected)}"
            )
        payload = {key: value.get(key) for key in expected}
        return cls(**payload)


@dataclass(frozen=True)
class CandidateLedger:
    """A deterministic collection of normalized Track 2 candidate audit rows."""

    ledger_id: str
    purpose: str
    search_protocol: SearchProtocol
    entries: Sequence[CandidateEntry]
    schema: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema != SCHEMA_VERSION:
            raise CandidateLedgerError(f"schema must be {SCHEMA_VERSION!r}")
        object.__setattr__(
            self, "ledger_id", _identifier(self.ledger_id, location="ledger_id")
        )
        object.__setattr__(
            self, "purpose", _text(self.purpose, location="purpose", minimum=20)
        )
        protocol = self.search_protocol
        if not isinstance(protocol, SearchProtocol):
            protocol = SearchProtocol.from_dict(protocol)
        object.__setattr__(self, "search_protocol", protocol)
        if isinstance(self.entries, (str, bytes)) or not isinstance(
            self.entries, Sequence
        ):
            raise CandidateLedgerError("entries: expected an array")
        converted = tuple(
            entry
            if isinstance(entry, CandidateEntry)
            else CandidateEntry.from_dict(entry)
            for entry in self.entries
        )
        identifiers = [entry.candidate_id for entry in converted]
        if len(set(identifiers)) != len(identifiers):
            raise CandidateLedgerError(
                "entries: duplicate candidate_id values are forbidden"
            )
        converted = tuple(sorted(converted, key=lambda entry: entry.candidate_id))
        priorities = [
            entry.experimental_priority
            for entry in converted
            if entry.experimental_priority is not None
        ]
        if len(set(priorities)) != len(priorities):
            raise CandidateLedgerError(
                "entries: duplicate experimental_priority values are forbidden"
            )
        active_leads = [
            entry.candidate_id
            for entry in converted
            if entry.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
        ]
        if len(active_leads) > 1:
            raise CandidateLedgerError(
                "entries: at most one active_lead is allowed"
            )
        role_leads = [
            entry.candidate_id
            for entry in converted
            if entry.role == "lead"
        ]
        if len(role_leads) > 1:
            raise CandidateLedgerError(
                "entries: at most one role lead is allowed"
            )
        object.__setattr__(self, "entries", converted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "ledger_id": self.ledger_id,
            "purpose": self.purpose,
            "search_protocol": self.search_protocol.to_dict(),
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CandidateLedger":
        if not isinstance(value, Mapping):
            raise CandidateLedgerError("candidate ledger must be an object")
        expected = {"schema", "ledger_id", "purpose", "search_protocol", "entries"}
        if set(value) != expected:
            raise CandidateLedgerError(
                f"ledger fields must be exactly {sorted(expected)}"
            )
        return cls(
            schema=value["schema"],
            ledger_id=value["ledger_id"],
            purpose=value["purpose"],
            search_protocol=value["search_protocol"],
            entries=value["entries"],
        )


def validate_candidate_ledger(
    value: CandidateLedger | Mapping[str, Any],
    *,
    public_only: bool = False,
    sample_plan: Mapping[str, Any] | None = None,
) -> CandidateLedger:
    """Validate and return an immutable ledger, optionally public-only."""

    ledger = value if isinstance(value, CandidateLedger) else CandidateLedger.from_dict(value)
    has_promotion = any(
        entry.sample_stewardship_promotion is not None for entry in ledger.entries
    )
    if has_promotion and sample_plan is None:
        raise CandidateLedgerError(
            "sample-stewardship promotion requires a sample-stewardship plan"
        )
    if not has_promotion and sample_plan is not None:
        raise CandidateLedgerError(
            "sample-stewardship plan is unbound because the ledger has no promotion"
        )
    if sample_plan is not None:
        _assert_sample_promotions(ledger, sample_plan)
    if public_only:
        forbidden = sorted(
            {
                entry.privacy_class
                for entry in ledger.entries
                if entry.privacy_class not in PUBLIC_PRIVACY_CLASSES
            }
        )
        if forbidden:
            raise CandidateLedgerError(
                "public ledger contains forbidden privacy classes: "
                + ", ".join(forbidden)
            )
    parents_by_id = {
        entry.candidate_id: entry
        for entry in ledger.entries
        if entry.source_class != "derived_evidence"
    }
    for entry in ledger.entries:
        if entry.source_class != "derived_evidence":
            continue
        parent = parents_by_id.get(entry.parent_candidate_id)
        if parent is None or parent.source_class != entry.parent_source_class:
            raise CandidateLedgerError(
                "derived_evidence parent_candidate_id does not resolve to a "
                "non-derived ledger entry of the declared parent_source_class"
            )
    return ledger


def rank_candidates(
    value: CandidateLedger | Mapping[str, Any],
    *,
    sample_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose a test queue and fail-closed rescue gates without ranking efficacy.

    Experimental priority is explicit and role-independent. Exposure,
    regulatory, pediatric, oncology, transformed-culture, isogenic-A0,
    mixed-or-unsafe, valid-negative, rejected, and not-assessable
    screening can admit a conditional probe, but only a fully passed
    correction-calibrated rescue record can become an active lead.
    """

    ledger = validate_candidate_ledger(value, sample_plan=sample_plan)

    def screening_reasons(entry: CandidateEntry) -> list[str]:
        reasons: list[str] = []
        if entry.role not in PHARMACOLOGIC_RANKING_ROLES:
            reasons.append(f"non_pharmacologic_role:{entry.role}")
        if entry.oncology_risk != "caution":
            reasons.append(f"oncology_risk:{entry.oncology_risk}")
        if (
            entry.regulatory_eligibility
            not in DISPLACEMENT_ELIGIBLE_REGULATORY_STATES
        ):
            reasons.append(
                f"regulatory_eligibility:{entry.regulatory_eligibility}"
            )
        if entry.exposure_class not in DISPLACEMENT_ELIGIBLE_EXPOSURE_CLASSES:
            reasons.append(f"exposure_class:{entry.exposure_class}")
        if (
            entry.role in PHARMACOLOGIC_RANKING_ROLES
            and entry.pediatric_information
            not in DISPLACEMENT_ELIGIBLE_PEDIATRIC_STATES
        ):
            reasons.append(
                f"pediatric_information:{entry.pediatric_information}"
            )
        if (
            entry.role in PHARMACOLOGIC_RANKING_ROLES
            and entry.transformation_state
            in DISPLACEMENT_INELIGIBLE_TRANSFORMATION_STATES
        ):
            reasons.append(
                f"transformation_state:{entry.transformation_state}"
            )
        if (
            entry.role in PHARMACOLOGIC_RANKING_ROLES
            and entry.functional_hit_state
            in DISPLACEMENT_INELIGIBLE_FUNCTIONAL_HIT_STATES
        ):
            reasons.append(
                f"functional_hit_state:{entry.functional_hit_state}"
            )
        if (
            entry.role in PHARMACOLOGIC_RANKING_ROLES
            and entry.advancement_state
            in DISPLACEMENT_INELIGIBLE_ADVANCEMENT_STATES
        ):
            reasons.append(
                f"advancement_state:{entry.advancement_state}"
            )
        return reasons

    def evidence_reasons(entry: CandidateEntry) -> list[str]:
        reasons: list[str] = []
        if entry.assessment_status != "positive":
            reasons.append(f"assessment_status:{entry.assessment_status}")
        if entry.direction != "supports":
            reasons.append(f"direction:{entry.direction}")
        if entry.decision_effect == "exclude":
            reasons.append("decision_effect:exclude")
        if entry.decision_effect == "demote":
            reasons.append("decision_effect:demote")
        if entry.advancement_state not in LEAD_ADVANCEMENT_STATES:
            reasons.append(f"advancement_state:{entry.advancement_state}")
        return reasons

    screen_by_id = {
        entry.candidate_id: screening_reasons(entry) for entry in ledger.entries
    }
    evidence_by_id = {
        entry.candidate_id: evidence_reasons(entry) for entry in ledger.entries
    }

    def held_out_confirmation_eligible(entry: CandidateEntry) -> bool:
        """Admit only safe, exposed functional hits to blinded confirmation.

        ``correction_rescue`` and ``reciprocal_recreation`` enforce the
        exact-correction-before-drug causal contract. ``native_fidelity``
        represents both locked first-division estimands (gC and gE).
        ``branch_opened`` plus ``correction_like_function`` represents at
        least one pre-locked correction-like functional branch.
        Exposure validity and the no-harm boundary are represented by the
        symmetric screening checks plus completion and clone-safety gates.
        Proximal engagement is intentionally not required here because a
        mechanism-discordant functional hit can, by definition, fail or leave
        the proposed proximal chain unresolved.
        """

        return not held_out_confirmation_reasons(entry)

    def held_out_confirmation_reasons(entry: CandidateEntry) -> list[str]:
        reasons: list[str] = []
        if entry.functional_hit_state not in HELD_OUT_CONFIRMATION_STATES:
            reasons.append(f"functional_hit_state:{entry.functional_hit_state}")
        if entry.exact_allele_evidence != "positive":
            reasons.append(f"exact_allele_evidence:{entry.exact_allele_evidence}")
        if entry.checkpoint_evidence != "positive":
            reasons.append(f"checkpoint_evidence:{entry.checkpoint_evidence}")
        if entry.decision_effect not in ADVANCING_DECISION_EFFECTS:
            reasons.append(f"decision_effect:{entry.decision_effect}")
        if entry.program_gate not in HELD_OUT_PROGRAM_GATES:
            reasons.append(f"program_gate:{entry.program_gate}")
        reasons.extend(
            f"screening:{reason}" for reason in screen_by_id[entry.candidate_id]
        )
        reasons.extend(
            f"evidence:{reason}" for reason in evidence_by_id[entry.candidate_id]
        )
        reasons.extend(
            f"{name}:{getattr(entry.rescue_gates, name)}"
            for name in HELD_OUT_CONFIRMATION_GATE_NAMES
            if getattr(entry.rescue_gates, name) != "pass"
        )
        if entry.independent_replication != "not_attempted":
            reasons.append(
                f"independent_replication:{entry.independent_replication}"
            )
        if entry.rescue_gates.independent_replication != "not_attempted":
            reasons.append(
                "independent_replication_gate:"
                f"{entry.rescue_gates.independent_replication}"
            )
        if entry.rescue_gates.analytic_transfer_pass != "not_attempted":
            reasons.append(
                "analytic_transfer_pass:"
                f"{entry.rescue_gates.analytic_transfer_pass}"
            )
        if entry.rescue_gates.biological_replication_pass != "not_attempted":
            reasons.append(
                "biological_replication_pass:"
                f"{entry.rescue_gates.biological_replication_pass}"
            )
        if entry.rescue_gates.blinded_replication_execution != "not_attempted":
            reasons.append(
                "blinded_replication_execution:"
                f"{entry.rescue_gates.blinded_replication_execution}"
            )
        if entry.rescue_gates.replication_provenance != "not_attempted":
            reasons.append(
                "replication_provenance:"
                f"{entry.rescue_gates.replication_provenance}"
            )
        if (
            entry.functional_hit_state == "graded_partial_hit"
            and entry.rescue_gates.proximal_engagement != "pass"
        ):
            reasons.append(
                "proximal_engagement:"
                f"{entry.rescue_gates.proximal_engagement}"
            )
        if (
            entry.functional_hit_state == "mechanism_discordant_hit"
            and entry.rescue_gates.proximal_engagement
            not in {"fail", "not_attempted"}
        ):
            reasons.append(
                "proximal_engagement:"
                f"{entry.rescue_gates.proximal_engagement}"
            )
        return reasons

    screened = tuple(
        entry
        for entry in ledger.entries
        if entry.role in PHARMACOLOGIC_RANKING_ROLES
        and not screen_by_id[entry.candidate_id]
    )
    conditional = tuple(
        entry
        for entry in screened
        if entry.advancement_state == "conditional_hold"
        and not evidence_by_id[entry.candidate_id]
    )
    active_ids = sorted(
        entry.candidate_id
        for entry in ledger.entries
        if entry.advancement_state == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
    )
    score_groups: dict[int, list[str]] = {}
    for entry in ledger.entries:
        if entry.experimental_priority is None:
            continue
        score_groups.setdefault(entry.causal_distance_score, []).append(
            entry.candidate_id
        )
    equal_score_groups = [
        {
            "causal_distance_score": score,
            "candidate_ids": sorted(candidate_ids),
            "screened_candidate_ids": sorted(
                candidate_id
                for candidate_id in candidate_ids
                if not screen_by_id[candidate_id]
            ),
        }
        for score, candidate_ids in sorted(score_groups.items(), reverse=True)
        if len(candidate_ids) > 1
    ]
    priority_order = [
        entry.candidate_id
        for entry in sorted(
            (
                entry
                for entry in ledger.entries
                if entry.experimental_priority is not None
            ),
            key=lambda entry: (entry.experimental_priority or 0, entry.candidate_id),
        )
    ]
    candidate_gate_reasons = {
        entry.candidate_id: {
            "screening": screen_by_id[entry.candidate_id],
            "evidence": evidence_by_id[entry.candidate_id],
            "rescue": list(entry.rescue_gates.blockers()),
            "held_out_confirmation": held_out_confirmation_reasons(entry),
            "held_out_confirmation_eligible": held_out_confirmation_eligible(entry),
            "active_lead_eligible": (
                not screen_by_id[entry.candidate_id]
                and not evidence_by_id[entry.candidate_id]
                and entry.rescue_gates.all_pass
                and entry.independent_replication == "replicated"
                and entry.functional_hit_state == "replicated_full_phenocopy"
                and entry.advancement_state
                == ACTIVE_LEAD_FORBIDDEN_ADVANCEMENT
            ),
        }
        for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
    }
    return {
        "schema": ledger.schema,
        "n_entries": len(ledger.entries),
        "active_lead_id": active_ids[0] if active_ids else None,
        "exposure_regulatory_screened_ids": sorted(
            entry.candidate_id for entry in screened
        ),
        "conditional_probe_ids": sorted(
            entry.candidate_id for entry in conditional
        ),
        "held_out_confirmation_ids": sorted(
            entry.candidate_id
            for entry in ledger.entries
            if held_out_confirmation_eligible(entry)
        ),
        "functional_hit_states": {
            entry.candidate_id: entry.functional_hit_state
            for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
        },
        "discovery_lanes": {
            entry.candidate_id: entry.discovery_lane
            for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
        },
        "mitotic_context_classes": {
            entry.candidate_id: entry.mitotic_context_class
            for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
        },
        "transformation_states": {
            entry.candidate_id: entry.transformation_state
            for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
        },
        "replication_states": {
            entry.candidate_id: {
                "analytic_transfer_pass": entry.rescue_gates.analytic_transfer_pass,
                "biological_replication_pass": (
                    entry.rescue_gates.biological_replication_pass
                ),
                "blinded_replication_execution": (
                    entry.rescue_gates.blinded_replication_execution
                ),
            }
            for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
        },
        "replication_evidence": {
            entry.candidate_id: {
                "analytic_transfer_result_sha256": (
                    entry.replication_design.analytic_transfer_result_sha256
                ),
                "site2_blinding_state": (
                    entry.replication_design.site2_blinding_state
                ),
                "site2_blinding_evidence_sha256": (
                    entry.replication_design.site2_blinding_evidence_sha256
                ),
            }
            for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
        },
        "experimental_priority_order": priority_order,
        "equal_causal_score_groups": equal_score_groups,
        "candidate_gate_reasons": candidate_gate_reasons,
        "rejected_ids": sorted(
            entry.candidate_id
            for entry in ledger.entries
            if entry.advancement_state == "rejected"
        ),
        "sample_stewardship_promotion_bound": True,
        "sample_context_qualification_bound": True,
        # Promotion receipts bind only to a synthetic-only sample plan — no
        # ranking can attest external, non-synthetic rescue evidence.
        "synthetic_only": True,
        "external_evidence_attested": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateLedgerError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CandidateLedgerError(f"non-finite JSON constant is forbidden: {value}")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise CandidateLedgerError(f"non-finite JSON number is forbidden: {value}")
    return parsed


def load_sample_stewardship_plan_bytes(payload: bytes) -> dict[str, Any]:
    """Load and validate one strict synthetic sample-stewardship plan."""

    if not isinstance(payload, bytes):
        raise CandidateLedgerError("sample-stewardship plan payload must be bytes")
    if len(payload) > MAX_SAMPLE_PLAN_BYTES:
        raise CandidateLedgerError(
            "sample-stewardship plan exceeds the 1 MiB limit"
        )
    if payload.startswith(b"\xef\xbb\xbf"):
        raise CandidateLedgerError(
            "sample-stewardship plan must not contain a UTF-8 BOM"
        )
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except UnicodeDecodeError as exc:
        raise CandidateLedgerError(
            "sample-stewardship plan is not valid UTF-8"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CandidateLedgerError(
            "sample-stewardship plan is not valid JSON"
        ) from exc
    except RecursionError as exc:
        raise CandidateLedgerError(
            "sample-stewardship plan JSON is nested too deeply"
        ) from exc
    except (OverflowError, MemoryError) as exc:
        raise CandidateLedgerError(
            "sample-stewardship plan contains an out-of-range value"
        ) from exc
    if not isinstance(value, dict):
        raise CandidateLedgerError("sample-stewardship plan must be an object")
    try:
        assess_sample_stewardship(value)
    except SampleStewardshipError as exc:
        raise CandidateLedgerError(
            f"sample-stewardship plan is invalid: {exc}"
        ) from exc
    return value


def load_sample_stewardship_plan(path: str | Path) -> dict[str, Any]:
    """Load a strict plan without publishing or copying its contents."""

    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise CandidateLedgerError(
            f"cannot read sample-stewardship plan: {exc}"
        ) from exc
    return load_sample_stewardship_plan_bytes(payload)


def load_candidate_ledger_bytes(
    payload: bytes,
    *,
    public_only: bool = False,
    sample_plan: Mapping[str, Any] | None = None,
) -> CandidateLedger:
    """Load strict UTF-8 JSON bytes with duplicate, size, and privacy checks."""

    if not isinstance(payload, bytes):
        raise CandidateLedgerError("candidate ledger payload must be bytes")
    if len(payload) > MAX_LEDGER_BYTES:
        raise CandidateLedgerError("candidate ledger exceeds the 1 MiB limit")
    if payload.startswith(b"\xef\xbb\xbf"):
        raise CandidateLedgerError("candidate ledger must not contain a UTF-8 BOM")
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except UnicodeDecodeError as exc:
        raise CandidateLedgerError("candidate ledger is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise CandidateLedgerError("candidate ledger is not valid JSON") from exc
    except RecursionError as exc:
        raise CandidateLedgerError("candidate ledger JSON is nested too deeply") from exc
    except (OverflowError, MemoryError) as exc:
        raise CandidateLedgerError(
            "candidate ledger contains an out-of-range value"
        ) from exc
    return validate_candidate_ledger(
        value, public_only=public_only, sample_plan=sample_plan
    )


def load_candidate_ledger(
    path: str | Path,
    *,
    public_only: bool = False,
    sample_plan: Mapping[str, Any] | None = None,
) -> CandidateLedger:
    """Load UTF-8 JSON with duplicate-key, size, schema, and privacy checks."""

    source = Path(path)
    try:
        if source.stat().st_size > MAX_LEDGER_BYTES:
            raise CandidateLedgerError(
                "candidate ledger exceeds the 1 MiB limit"
            )
        payload = source.read_bytes()
    except OSError as exc:
        raise CandidateLedgerError(f"cannot read candidate ledger: {exc}") from exc
    return load_candidate_ledger_bytes(
        payload, public_only=public_only, sample_plan=sample_plan
    )


def canonical_candidate_ledger_bytes(
    value: CandidateLedger | Mapping[str, Any],
    *,
    public_only: bool = False,
    sample_plan: Mapping[str, Any] | None = None,
) -> bytes:
    """Render normalized ledger bytes for an exact release receipt."""

    ledger = validate_candidate_ledger(
        value, public_only=public_only, sample_plan=sample_plan
    )
    rendered = ledger.to_dict()
    rendered["entries"] = [
        entry.to_dict()
        for entry in sorted(ledger.entries, key=lambda item: item.candidate_id)
    ]
    return (
        json.dumps(
            rendered,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def canonical_candidate_ranking_bytes(
    value: CandidateLedger | Mapping[str, Any],
    *,
    sample_plan: Mapping[str, Any] | None = None,
) -> bytes:
    """Render the exact ranking implied by one validated ledger."""

    ledger = validate_candidate_ledger(value, sample_plan=sample_plan)
    return (
        json.dumps(
            rank_candidates(ledger, sample_plan=sample_plan),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def validate_candidate_release_ledger_bytes(
    payload: bytes,
    *,
    sample_plan: Mapping[str, Any] | None = None,
) -> CandidateLedger:
    """Require public-only content and the one canonical ledger rendering."""

    ledger = load_candidate_ledger_bytes(
        payload, public_only=True, sample_plan=sample_plan
    )
    expected = canonical_candidate_ledger_bytes(
        ledger, public_only=True, sample_plan=sample_plan
    )
    if payload != expected:
        raise CandidateLedgerError(
            "release candidate ledger is not the exact canonical rendering"
        )
    return ledger


def validate_candidate_release_bundle_bytes(
    ledger_payload: bytes,
    ranking_payload: bytes,
    *,
    sample_plan: Mapping[str, Any] | None = None,
) -> tuple[CandidateLedger, dict[str, Any]]:
    """Bind one canonical public ledger to its exact computed ranking bytes."""

    if not isinstance(ranking_payload, bytes):
        raise CandidateLedgerError("candidate ranking receipt must be bytes")
    if len(ranking_payload) > MAX_LEDGER_BYTES:
        raise CandidateLedgerError("candidate ranking receipt exceeds the 1 MiB limit")
    ledger = validate_candidate_release_ledger_bytes(
        ledger_payload, sample_plan=sample_plan
    )
    expected_ranking = canonical_candidate_ranking_bytes(
        ledger, sample_plan=sample_plan
    )
    if ranking_payload != expected_ranking:
        raise CandidateLedgerError(
            "candidate ranking receipt is not the exact ranking computed from the released ledger"
        )
    ranking = rank_candidates(ledger, sample_plan=sample_plan)
    return ledger, ranking
