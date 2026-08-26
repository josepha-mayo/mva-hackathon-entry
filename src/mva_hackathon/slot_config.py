"""Strict loader for the six predeclared qualitative Track 1 slot configs."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping


SLOT_SCHEMA = "mva.track1-slot-config/v1"
PLAN_SCHEMA = "mva.track1-slot-plan/v1"

METHODS = (
    "full-public-auto",
    "minus-phenotype",
    "novel-gene-mask",
    "exomiser-baseline",
    "vcf-only",
    "no-comphet-pairing",
)

EXPECTED_VARIANTS: Mapping[str, tuple[str, str, str, str, str]] = {
    "full-public-auto": (
        "enabled",
        "enabled",
        "integrated_public_auto",
        "full_prespecified_local_evidence",
        "enabled",
    ),
    "minus-phenotype": (
        "disabled",
        "enabled",
        "integrated_public_auto",
        "full_prespecified_local_evidence",
        "enabled",
    ),
    "novel-gene-mask": (
        "enabled_with_gene_links_masked",
        "masked",
        "integrated_public_auto",
        "full_prespecified_local_evidence",
        "enabled",
    ),
    "exomiser-baseline": (
        "enabled",
        "enabled",
        "exomiser_baseline",
        "supplied_vcf_only",
        "enabled",
    ),
    "vcf-only": (
        "enabled",
        "enabled",
        "integrated_public_auto",
        "supplied_vcf_only",
        "enabled",
    ),
    "no-comphet-pairing": (
        "enabled",
        "enabled",
        "integrated_public_auto",
        "full_prespecified_local_evidence",
        "disabled",
    ),
}


class SlotConfigError(ValueError):
    """Raised when a qualitative slot config is unsafe or ambiguous."""


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SlotConfigError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _one_of(value: Any, allowed: set[str], *, field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SlotConfigError(f"{field}: expected one of {sorted(allowed)}")
    return value


@dataclass(frozen=True)
class SlotConfig:
    slot: int
    method_id: str
    scientific_question: str
    phenotype_mode: Literal["enabled", "disabled", "enabled_with_gene_links_masked"]
    gene_disease_knowledge: Literal["enabled", "masked"]
    ranking_backend: Literal["integrated_public_auto", "exomiser_baseline"]
    input_evidence: Literal[
        "full_prespecified_local_evidence", "supplied_vcf_only"
    ]
    compound_heterozygous_pairing: Literal["enabled", "disabled"]
    resource_scope: str = "public_offline_only"
    execution_mode: str = "fully_automated"
    manual_candidate_injection: bool = False
    network_access: str = "disabled"
    leaderboard_adaptation: str = "prohibited"
    tool_lock_policy: str = "version_and_digest_required_before_execution"
    schema: str = SLOT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SLOT_SCHEMA:
            raise SlotConfigError(f"schema must be {SLOT_SCHEMA!r}")
        if isinstance(self.slot, bool) or not isinstance(self.slot, int) or not 1 <= self.slot <= 6:
            raise SlotConfigError("slot must be an integer from 1 through 6")
        if self.method_id not in METHODS:
            raise SlotConfigError(f"method_id: expected one of {list(METHODS)}")
        if METHODS[self.slot - 1] != self.method_id:
            raise SlotConfigError("method_id is assigned to the wrong predeclared slot")
        if not isinstance(self.scientific_question, str):
            raise SlotConfigError("scientific_question must contain 20 to 500 characters")
        question = unicodedata.normalize("NFC", self.scientific_question).strip()
        if not 20 <= len(question) <= 500 or _CONTROL_CHARACTERS.search(question):
            raise SlotConfigError("scientific_question must contain 20 to 500 characters")
        object.__setattr__(self, "scientific_question", question)

        _one_of(
            self.phenotype_mode,
            {"enabled", "disabled", "enabled_with_gene_links_masked"},
            field="phenotype_mode",
        )
        _one_of(
            self.gene_disease_knowledge,
            {"enabled", "masked"},
            field="gene_disease_knowledge",
        )
        _one_of(
            self.ranking_backend,
            {"integrated_public_auto", "exomiser_baseline"},
            field="ranking_backend",
        )
        _one_of(
            self.input_evidence,
            {"full_prespecified_local_evidence", "supplied_vcf_only"},
            field="input_evidence",
        )
        _one_of(
            self.compound_heterozygous_pairing,
            {"enabled", "disabled"},
            field="compound_heterozygous_pairing",
        )

        shared = {
            "resource_scope": (self.resource_scope, "public_offline_only"),
            "execution_mode": (self.execution_mode, "fully_automated"),
            "network_access": (self.network_access, "disabled"),
            "leaderboard_adaptation": (self.leaderboard_adaptation, "prohibited"),
            "tool_lock_policy": (
                self.tool_lock_policy,
                "version_and_digest_required_before_execution",
            ),
        }
        for field, (actual, expected) in shared.items():
            if actual != expected:
                raise SlotConfigError(f"{field} must be {expected!r}")
        if self.manual_candidate_injection is not False:
            raise SlotConfigError("manual_candidate_injection must be false")

        variant = (
            self.phenotype_mode,
            self.gene_disease_knowledge,
            self.ranking_backend,
            self.input_evidence,
            self.compound_heterozygous_pairing,
        )
        if variant != EXPECTED_VARIANTS[self.method_id]:
            raise SlotConfigError(
                f"{self.method_id}: settings do not match the predeclared ablation"
            )

    @classmethod
    def from_dict(cls, value: Any) -> "SlotConfig":
        if not isinstance(value, Mapping):
            raise SlotConfigError("slot config must be an object")
        expected = {
            "schema",
            "slot",
            "method_id",
            "scientific_question",
            "resource_scope",
            "execution_mode",
            "phenotype_mode",
            "gene_disease_knowledge",
            "ranking_backend",
            "input_evidence",
            "compound_heterozygous_pairing",
            "manual_candidate_injection",
            "network_access",
            "leaderboard_adaptation",
            "tool_lock_policy",
        }
        if set(value) != expected:
            raise SlotConfigError(f"slot config fields must be exactly {sorted(expected)}")
        return cls(**{key: value[key] for key in expected})


def load_slot_config(path: str | Path) -> SlotConfig:
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"), object_pairs_hook=_strict_object
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SlotConfigError("slot config is not readable UTF-8 JSON") from exc
    return SlotConfig.from_dict(value)


def load_slot_plan(path: str | Path) -> tuple[SlotConfig, ...]:
    """Load the fixed six-slot plan and every referenced config fail-closed."""

    source = Path(path).resolve()
    try:
        value = json.loads(
            source.read_text(encoding="utf-8"), object_pairs_hook=_strict_object
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SlotConfigError("slot plan is not readable UTF-8 JSON") from exc
    expected = {"schema", "policy", "config_files"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SlotConfigError(f"slot plan fields must be exactly {sorted(expected)}")
    if value["schema"] != PLAN_SCHEMA:
        raise SlotConfigError(f"slot plan schema must be {PLAN_SCHEMA!r}")
    if value["policy"] != {
        "frozen_before_first_submission": True,
        "adaptive_leaderboard_revision_prohibited": True,
    }:
        raise SlotConfigError("slot plan policy must prohibit adaptive leaderboard revision")
    filenames = value["config_files"]
    if not isinstance(filenames, list) or len(filenames) != 6:
        raise SlotConfigError("slot plan must name exactly six config files")
    if any(not isinstance(filename, str) for filename in filenames):
        raise SlotConfigError("slot plan config filenames must be strings")
    if len(set(filenames)) != len(filenames):
        raise SlotConfigError("slot plan contains duplicate config filenames")

    result: list[SlotConfig] = []
    for filename in filenames:
        if Path(filename).name != filename:
            raise SlotConfigError("slot plan contains an unsafe config filename")
        unresolved = source.parent / filename
        candidate = unresolved.resolve()
        if candidate.parent != source.parent or unresolved.is_symlink():
            raise SlotConfigError("slot config path escapes its plan directory")
        result.append(load_slot_config(candidate))
    if tuple(config.method_id for config in result) != METHODS:
        raise SlotConfigError("slot plan method order is not the predeclared six-slot order")
    return tuple(result)
