"""Compare Track 2 method versions without mistaking extra gates for progress.

An increment is better only if the nested true path still opens, public
confirmation still holds, freeze bytes are untouched, and independently
motivated false stories are newly blocked or blocked earlier. More tests or
more files are not a rescued child and are not a better hypothesis.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from mva_hackathon.community_pipeline import run_community_pipeline
from mva_hackathon.reproducibility import MANIFEST_PATH
from mva_hackathon.save_path import run_save_path_suite


SCHEMA = "mva-track2-method-delta/v2"
LEGACY_SCHEMA = "mva-track2-method-delta/v1"
CLAIM_BOUNDARY = (
    "Method-delta software comparison only; a better verdict is not a "
    "rescued child, not a survival percentage, and not an upload."
)
EXTERNAL_ANCHOR_REQUIREMENT = (
    "This content address detects changes only when receipt_id is retained or "
    "independently anchored outside this receipt. A malicious whole-reseal can "
    "create a different internally valid receipt and is not prevented locally."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
SPEND_LADDER = {
    "evidence": ("desktop_claim", 0),
    "family": ("desktop_claim", 0),
    "hypothesis": ("desktop_claim", 0),
    "confirmation": ("identity_confirmation", 24),
    "phase": ("phase", 22),
    "transcript": ("transcript", 20),
    "hypomorph": ("missense_assay", 16),
    "exposure": ("exposure", 13),
    "count_identity": ("imaging_campaign", 8),
    "assay_power": ("imaging_campaign", 8),
    "clone_safety": ("imaging_campaign", 8),
    "concordance": ("imaging_campaign", 8),
    "replication": ("replication_site", 0),
    "next_experiment": ("chooser", 0),
    "structure_ranking": ("desktop_claim", 0),
}
FAMILY_BY_SCENARIO = {
    "incomplete_confirmation": "identity.incomplete_confirmation",
    "unlinked_confirmation": "identity.unlinked_or_kmer_without_nest",
    "kmer_without_nest": "identity.unlinked_or_kmer_without_nest",
    "cis_pair": "phase.cis",
    "linkage_not_recorded": "phase.linkage_missing",
    "dropout_compatible_phase": "phase.dropout_or_strand",
    "strand_imbalance_phase": "phase.dropout_or_strand",
    "incomplete_transcript": "transcript.unmeasured",
    "computational_transcript": "transcript.not_an_assay",
    "unmatched_transcript_specimen": "transcript.unmatched_specimen",
    "computational_phase": "phase.not_a_molecule",
    "unmatched_phase_specimen": "phase.unmatched_specimen",
    "analog_as_function": "function.analog_or_computational",
    "analog_correction": "function.analog_correction_reversal",
    "dominant_interference": "function.dominant_interference",
    "carrier_dose_unmeasured": "function.carrier_dose_control",
    "computational_stability": "function.analog_or_computational",
    "computational_correction": "function.computational_correction_reversal",
    "failed_reciprocal_recreation": "function.reciprocal_recreation",
    "imposed_extrinsic_stress": "function.imposed_extrinsic_stress",
    "cell_free_biophysical": "function.cell_free_biophysical",
    "cell_free_correction": "function.cell_free_correction_reversal",
    "imposed_stress_correction": "function.imposed_stress_correction_reversal",
    "ectopic_expression": "function.ectopic_expression",
    "ectopic_correction": "function.ectopic_correction_reversal",
    "unmatched_assay_specimen": "function.unmatched_specimen",
    "unmatched_correction": "function.unmatched_correction_reversal",
    "heat_shock_pd": "false_rescue.heat_shock_pd",
    "organ_size_overclaim": "false_rescue.organ_size",
    "bulk_aneuploidy_rescue": "false_rescue.bulk_aneuploidy",
    "competing_risk": "competing_risk.pre_division_or_cytostasis",
    "fitter_error_daughters": "competing_risk.fitter_daughters",
    "event_negative_daughter_viability": "competing_risk.fitter_daughters",
    "multipolar_daughters_unfollowed": "competing_risk.multipolar_daughters",
    "censored_daughters_dilute": "competing_risk.censored_daughters",
    "probe_before_identity": "chooser.probe_before_identity",
    "later_identity_before_confirmation": "chooser.later_identity",
    "imaging_before_assay": "chooser.imaging_before_assay",
    "checkpoint_not_assayed": "function.checkpoint_not_assayed",
    "checkpoint_negative": "function.checkpoint_negative",
    "unmanufacturable_window": "window.powered_but_unmanufacturable",
    "bulk_fraction_endpoint": "false_rescue.bulk_fraction_window",
    "nontranslational_exposure": "exposure.nontranslational",
    "missing_exposure_duration": "false_rescue.exposure_time_profile",
    "pulse_only_exposure": "false_rescue.exposure_time_profile",
    "exposure_assay_file_collage": "provenance.exposure_assay_execution",
    "arm_position_confounding": "design.pre_exposure_arm_allocation",
    "arm_exact_column_gradient": "design.pre_exposure_arm_allocation",
    "arm_row_half_interaction": "design.pre_exposure_arm_allocation",
    "arm_event_order_alias": "design.pre_exposure_arm_allocation",
    "arm_local_quadratic_order_artifact": "design.pre_exposure_arm_allocation",
    "arm_local_order_interaction_artifact": "design.pre_exposure_arm_allocation",
    "family_overclaim": "family.overclaim",
    "kmer_without_file_layout": "identity.truncated_layout",
    "rna_confirmation": "identity.rna_not_genomic",
    "unmatched_confirmation_specimen": "identity.unmatched_specimen",
    "unlocked_power_plan": "power.unlocked_or_underpowered_or_pediatric_crash",
    "underpowered_plan": "power.unlocked_or_underpowered_or_pediatric_crash",
    "pediatric_crash_plan": "power.unlocked_or_underpowered_or_pediatric_crash",
    "missing_falsifier": "hypothesis.missing_or_observed_falsifier",
    "observed_falsifier": "hypothesis.missing_or_observed_falsifier",
    "unmeasured_rna_child_claim": "hypothesis.observed_without_gate",
    "missing_alternative": "hypothesis.missing_or_observed_alternative",
    "observed_alternative": "hypothesis.missing_or_observed_alternative",
    "observed_without_gate": "hypothesis.observed_without_gate",
    "missing_controls": "hypothesis.controls",
    "control_failed": "hypothesis.controls",
    "observed_stability_without_assay": "hypothesis.observed_without_gate",
    "observed_endpoint_without_concordance": "hypothesis.observed_without_gate",
    "ranking_cannot_open_checkpoint": "ranking.not_an_assay",
    "predicted_stability_as_function": "ranking.not_an_assay",
    "reachable_save_path": "control.reachable",
    "discordant_exposure": "exposure.discordant_table",
    "vehicle_baseline_missing": "exposure.vehicle_baseline",
    "nominal_only_exposure": "exposure.unmeasured",
    "time_hours_nonpositive": "false_rescue.exposure_time_profile",
    "constant_window_sub_floor": "false_rescue.exposure_time_profile",
    "exposure_timing_mismatch": "exposure.timing_binding",
    "aminoglycoside_carryover": "exposure.selection_carryover",
    "selection_agent_unlabeled": "exposure.selection_unlabeled",
    "selection_batch_taint": "exposure.selection_carryover",
    "carrier_dose_stub": "function.carrier_dose_control",
    "missense_defective_when_abundant": "function.defective_when_abundant",
    "function_at_abundance_unmeasured": "function.at_abundance_unmeasured",
    "abundance_normalization_failed": "function.at_abundance_unmeasured",
    "missing_multiplicity": "hypothesis.multiplicity",
    "multiplicity_without_alpha": "hypothesis.multiplicity",
    "multiplicity_family_uncovered": "hypothesis.multiplicity",
    "missing_counterscreen": "hypothesis.counterscreen",
    "probe_unscreened": "hypothesis.counterscreen",
    "missing_evidence_chain": "hypothesis.evidence_chain",
    "supports_donation_falsifier": "hypothesis.falsifier_contract",
    "unwatched_falsifier": "hypothesis.falsifier_contract",
    "falsifier_bound_unequal": "hypothesis.falsifier_contract",
    "unwatched_endpoint": "hypothesis.endpoint_contract",
    "endpoint_unkilled": "hypothesis.endpoint_contract",
    "endpoint_unblinded": "hypothesis.endpoint_contract",
    "endpoint_without_spec": "hypothesis.endpoint_contract",
    "vacuous_second_endpoint": "hypothesis.endpoint_contract",
    "endpoint_uncontrolled": "hypothesis.controls",
    "endpoint_wrong_comparator": "hypothesis.controls",
    "endpoint_negated_comparator": "hypothesis.controls",
    "unwatched_alternative": "hypothesis.missing_or_observed_alternative",
    "unwatched_probe_chain": "hypothesis.probe_chain",
    "watch_cycle": "hypothesis.watch_graph",
    "unanchored_kill_bound": "hypothesis.kill_bound",
    "blinded_table_tampered": "provenance.blinded_table",
    "blinded_row_dropped": "provenance.blinded_table",
    "blinded_duplicate_keys": "provenance.blinded_table",
    "blinded_negative_shared_count": "provenance.blinded_table",
    "single_flat_clone": "concordance.flat_clone",
    "replication_declared_discordant": "replication.declared_integrity",
    "replication_same_site": "replication.declared_integrity",
    "replication_declared_exposure_failed": "replication.declared_integrity",
    "unknown_next_gate": "chooser.unknown_gate",
    "composite_confirmation_plus_blinded": "composite.multi_depth",
    "dropped_clone_caught_by_binding": "design.realized_set_binding",
    "missense_not_expressed": "transcript.missense_expression",
    "protein_not_transcript": "transcript.protein_not_transcript",
    "stop_transcript_persists": "transcript.stop_persistence",
    "linkage_disagreement": "phase.linkage_disagreement",
    "need_two_guide_configurations": "phase.guide_configurations",
    "guide_span_floor": "phase.guide_configurations",
    "strands_not_counted": "identity.strand_counts",
    "identity_unresolved": "identity.unresolved",
    "clone_safety_under_followed": "competing_risk.fitter_daughters",
    "clone_safety_selective_positive_followup": "competing_risk.fitter_daughters",
}
FREEZE_ENVELOPE = (
    ("aggregate_generation_selection", True),
    ("nested_community_pipeline", False),
    ("nested_confirmation", False),
    ("clone_safety", False),
    ("weakest_link_hypothesis", False),
    ("identity_first_chooser", False),
    ("save_path_simulation", False),
)
HOLDOUT_FAMILIES = (
    "identity.incomplete_confirmation",
    "phase.cis",
    "false_rescue.heat_shock_pd",
    "chooser.probe_before_identity",
    "ranking.not_an_assay",
)
CULTURE_REMAINING_DIRECTION = "higher_means_earlier_block_from_advancing"
STRUCTURAL_GATES = (
    "evidence",
    "family",
    "confirmation",
    "phase",
    "transcript",
    "hypomorph",
    "exposure",
    "count_identity",
    "assay_power",
    "clone_safety",
    "concordance",
    "hypothesis",
    "replication",
    "next_experiment",
)


class MethodDeltaError(ValueError):
    """Raised when a method-delta snapshot or comparison is unusable."""


_snapshot_id_prefix = "sha256:"
_parent_unspecified = object()
_snapshot_required_keys = frozenset(
    {
        "schema",
        "record_kind",
        "snapshot_id",
        "parent_snapshot_id",
        "synthetic_only",
        "claim_boundary",
        "chronology",
    }
)
_snapshot_allowed_keys = frozenset(
    {
        *_snapshot_required_keys,
        "freeze_pointers",
        "freeze_integrity",
        "living_method_integrity",
        "capability_envelope",
        "invariants",
        "registered_gates",
        "metrics",
        "scenarios",
        "ranking_cases",
        "public_toolkit",
        "save_path",
    }
)
_chronology_keys = frozenset(
    {
        "recorded_at",
        "exposure_started_at",
        "timestamp_authenticity",
        "exposure_boundary",
        "exposure_boundary_authenticity",
    }
)
_comparison_keys = frozenset(
    {
        "schema",
        "record_kind",
        "comparison_id",
        "snapshot_id",
        "parent_snapshot_id",
        "current_snapshot_sha256",
        "previous_snapshot_sha256",
        "previous_snapshot_schema",
        "previous_linkage_status",
        "synthetic_only",
        "claim_boundary",
        "verdict",
        "reason",
        "invariants_passed",
        "deltas",
        "current_metrics",
        "compared_to",
        "internal_synthetic_proxies",
        "external_outcomes",
        "internal_joint_verdict",
        "reviewer",
    }
)
_receipt_keys = frozenset(
    {
        "schema",
        "record_kind",
        "receipt_id",
        "snapshot",
        "previous_snapshot",
        "comparison",
        "external_anchor",
    }
)
_proxy_keys = frozenset(
    {
        "earlier_or_broader_false_path_blocking",
        "method_contract_usable",
        "joint_better",
    }
)
_external_anchor_declaration = {
    "target": "receipt_id",
    "authenticity": "not_established",
    "whole_reseal_resistance": "requires_independent_external_anchor",
    "requirement": EXTERNAL_ANCHOR_REQUIREMENT,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _canonical_json_bytes(value: Any, label: str) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MethodDeltaError(f"{label} is not canonical JSON") from exc
    return encoded.encode("utf-8")


def _canonical_snapshot_bytes(
    snapshot: Mapping[str, Any],
    *,
    normalize_identity: bool,
) -> bytes:
    payload = copy.deepcopy(dict(snapshot))
    if normalize_identity:
        payload["snapshot_id"] = None
    return _canonical_json_bytes(payload, "snapshot")


def _canonical_comparison_bytes(
    comparison: Mapping[str, Any],
    *,
    normalize_identity: bool,
) -> bytes:
    payload = copy.deepcopy(dict(comparison))
    if normalize_identity:
        payload["comparison_id"] = None
    return _canonical_json_bytes(payload, "comparison")


def _canonical_receipt_bytes(
    receipt: Mapping[str, Any],
    *,
    normalize_identity: bool,
) -> bytes:
    payload = copy.deepcopy(dict(receipt))
    if normalize_identity:
        payload["receipt_id"] = None
    return _canonical_json_bytes(payload, "receipt")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_snapshot_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(_snapshot_id_prefix)
        and _is_sha256(value[len(_snapshot_id_prefix) :])
    )


def _canonical_utc(value: str | None, label: str) -> tuple[str | None, datetime | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value:
        raise MethodDeltaError(f"{label} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MethodDeltaError(
            f"{label} must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MethodDeltaError(f"{label} must include a timezone")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat().replace("+00:00", "Z"), utc


def _chronology_declaration(
    *,
    recorded_at: str | None = None,
    exposure_started_at: str | None = None,
) -> dict[str, Any]:
    canonical_recorded_at, recorded = _canonical_utc(recorded_at, "recorded_at")
    canonical_exposure_at, exposure = _canonical_utc(
        exposure_started_at, "exposure_started_at"
    )
    boundary = "not_established"
    if recorded is not None and exposure is not None:
        boundary = (
            "declared_pre_exposure"
            if recorded < exposure
            else "declared_not_pre_exposure"
        )
    return {
        "recorded_at": canonical_recorded_at,
        "exposure_started_at": canonical_exposure_at,
        "timestamp_authenticity": "not_established",
        "exposure_boundary": boundary,
        "exposure_boundary_authenticity": "not_established",
    }


def _validate_chronology(value: object, label: str) -> None:
    if not isinstance(value, Mapping):
        raise MethodDeltaError(f"{label}.chronology must be an object")
    if set(value) != _chronology_keys:
        raise MethodDeltaError(f"{label}.chronology has the wrong fields")
    expected = _chronology_declaration(
        recorded_at=value.get("recorded_at"),
        exposure_started_at=value.get("exposure_started_at"),
    )
    if dict(value) != expected:
        raise MethodDeltaError(
            f"{label}.chronology is inconsistent or claims authenticated local time"
        )


def _snapshot_content_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_snapshot_bytes(snapshot, normalize_identity=True)
    ).hexdigest()


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    """Hash the exact canonical bytes of a sealed snapshot."""

    return hashlib.sha256(
        _canonical_snapshot_bytes(snapshot, normalize_identity=False)
    ).hexdigest()


_scenario_row_keys = frozenset(
    {
        "scenario_id",
        "kind",
        "family_id",
        "motivation",
        "decision",
        "blocked_by",
        "block_reason",
        "terminal_blocked_by",
        "terminal_block_reason",
        "earliest_nonpass_gate",
        "earliest_nonpass_effect",
        "earliest_nonpass_reason",
        "lab_object",
        "culture_remaining",
        "blocked_from_advancing",
        "opened",
        "discriminable_at_freeze",
    }
)
_scenario_text_fields = (
    "scenario_id",
    "kind",
    "family_id",
    "motivation",
    "decision",
    "lab_object",
)
_scenario_nullable_text_fields = (
    "blocked_by",
    "block_reason",
    "terminal_blocked_by",
    "terminal_block_reason",
    "earliest_nonpass_gate",
    "earliest_nonpass_effect",
    "earliest_nonpass_reason",
)
_scenario_bool_fields = (
    "blocked_from_advancing",
    "opened",
    "discriminable_at_freeze",
)
_ranking_row_keys = frozenset(
    {
        "case_id",
        "expected_step",
        "observed_step",
        "identity_complete",
        "probe_before_identity_stopped",
        "correct",
    }
)


def _validate_scenario_row(row: Any, location: str) -> None:
    if not isinstance(row, Mapping) or set(row) != _scenario_row_keys:
        raise MethodDeltaError(f"{location} has the wrong fields")
    for name in _scenario_text_fields:
        if not isinstance(row[name], str) or not row[name]:
            raise MethodDeltaError(f"{location}.{name} must be non-empty text")
    for name in _scenario_nullable_text_fields:
        if row[name] is not None and not isinstance(row[name], str):
            raise MethodDeltaError(f"{location}.{name} must be text or null")
    for name in _scenario_bool_fields:
        if not isinstance(row[name], bool):
            raise MethodDeltaError(f"{location}.{name} must be a boolean")
    culture = row["culture_remaining"]
    if isinstance(culture, bool) or not isinstance(culture, int) or culture < 0:
        raise MethodDeltaError(
            f"{location}.culture_remaining must be a non-negative integer"
        )
    if row["kind"] not in {"true_path", "false_path"}:
        raise MethodDeltaError(f"{location}.kind is invalid")
    gate = row["earliest_nonpass_gate"] or row["blocked_by"]
    if gate is not None and gate not in SPEND_LADDER:
        raise MethodDeltaError(
            f"{location}.earliest_nonpass_gate is not a declared structural gate"
        )
    # Outcome flags are measurements, not declarations: an unopened true
    # path is how a worse method is scored, and an opened false path is how
    # a regression is detected. What must be impossible is an internally
    # contradictory row — opened but blocked, or blocked by no gate. A hard
    # error outcome is the exception: a crashed step names no gate, but the
    # run is still blocked from advancing.
    if row["opened"] and (row["blocked_from_advancing"] or gate is not None):
        raise MethodDeltaError(
            f"{location}: an opened row cannot be blocked or name a blocking gate"
        )
    if row["decision"].startswith("error:"):
        if not row["blocked_from_advancing"] or gate is not None:
            raise MethodDeltaError(
                f"{location}: an error outcome must be blocked and name no gate"
            )
    elif (gate is not None) != row["blocked_from_advancing"]:
        raise MethodDeltaError(
            f"{location}: blocking gate and blocked_from_advancing disagree"
        )
    if row["lab_object"] != _lab_object(gate):
        raise MethodDeltaError(
            f"{location}.lab_object does not match its blocking gate"
        )
    if row["culture_remaining"] != _culture_remaining(gate):
        raise MethodDeltaError(
            f"{location}.culture_remaining does not match its blocking gate"
        )
    if row["family_id"] != _family_for(row["scenario_id"]):
        raise MethodDeltaError(
            f"{location}.family_id does not match its scenario_id"
        )
    expected_motivation = (
        "literature_family" if row["kind"] == "false_path" else "envelope_gap"
    )
    if row["motivation"] != expected_motivation:
        raise MethodDeltaError(
            f"{location}.motivation does not match its kind"
        )
    if (
        row["terminal_blocked_by"] != row["blocked_by"]
        or row["terminal_block_reason"] != row["block_reason"]
    ):
        raise MethodDeltaError(
            f"{location}.terminal fields must mirror the first block"
        )


def _validate_ranking_row(row: Any, location: str) -> None:
    if not isinstance(row, Mapping) or set(row) != _ranking_row_keys:
        raise MethodDeltaError(f"{location} has the wrong fields")
    if not isinstance(row["case_id"], str) or not row["case_id"]:
        raise MethodDeltaError(f"{location}.case_id must be non-empty text")
    for name in ("expected_step", "observed_step"):
        if row[name] is not None and not isinstance(row[name], str):
            raise MethodDeltaError(f"{location}.{name} must be text or null")
    for name in ("identity_complete", "probe_before_identity_stopped", "correct"):
        if not isinstance(row[name], bool):
            raise MethodDeltaError(f"{location}.{name} must be a boolean")


def _validate_snapshot_shape(snapshot: Mapping[str, Any], label: str) -> None:
    schema = snapshot.get("schema")
    if schema not in {SCHEMA, LEGACY_SCHEMA}:
        raise MethodDeltaError(f"{label} has the wrong schema")
    if snapshot.get("record_kind") != "snapshot":
        raise MethodDeltaError(f"{label} is not a snapshot record")
    if snapshot.get("synthetic_only") is not True:
        raise MethodDeltaError(f"{label} must remain synthetic-only")
    parent_snapshot_id = snapshot.get("parent_snapshot_id")
    if parent_snapshot_id is not None and not _is_snapshot_id(parent_snapshot_id):
        raise MethodDeltaError(f"{label} has an invalid parent_snapshot_id")
    if schema == SCHEMA:
        missing = _snapshot_required_keys - set(snapshot)
        surplus = set(snapshot) - _snapshot_allowed_keys
        if missing:
            raise MethodDeltaError(f"{label} is missing fields: {sorted(missing)}")
        if surplus:
            raise MethodDeltaError(f"{label} has unsupported fields: {sorted(surplus)}")
        if snapshot.get("claim_boundary") != CLAIM_BOUNDARY:
            raise MethodDeltaError(f"{label} has the wrong claim boundary")
        _validate_chronology(snapshot.get("chronology"), label)
        metrics = snapshot.get("metrics")
        if isinstance(metrics, Mapping) and {
            "n_independent_families_killed",
            "n_holdout_killed",
            "holdout_missing",
        } & set(metrics):
            raise MethodDeltaError(f"{label} uses legacy killed metric names")
        scenarios = snapshot.get("scenarios")
        if isinstance(scenarios, list) and any(
            isinstance(row, Mapping) and "killed" in row for row in scenarios
        ):
            raise MethodDeltaError(f"{label} uses a legacy killed scenario field")
        invariants = snapshot.get("invariants")
        if isinstance(invariants, Mapping) and "holdout_families_still_killed" in invariants:
            raise MethodDeltaError(f"{label} uses a legacy killed invariant name")
        save_path = snapshot.get("save_path")
        if isinstance(save_path, Mapping) and "n_false_path_killed" in save_path:
            raise MethodDeltaError(f"{label} uses a legacy killed save-path field")
        registered = snapshot.get("registered_gates")
        if isinstance(registered, list):
            if any(
                not isinstance(name, str) or name not in STRUCTURAL_GATES
                for name in registered
            ) or len(set(registered)) != len(registered):
                raise MethodDeltaError(
                    f"{label}.registered_gates must be unique structural gates"
                )
        if isinstance(scenarios, list):
            for index, row in enumerate(scenarios):
                _validate_scenario_row(row, f"{label}.scenarios[{index}]")
            scenario_ids = [row["scenario_id"] for row in scenarios]
            if len(set(scenario_ids)) != len(scenario_ids):
                raise MethodDeltaError(
                    f"{label}.scenarios contain a duplicate scenario_id"
                )
        ranking_cases = snapshot.get("ranking_cases")
        if isinstance(ranking_cases, list):
            for index, row in enumerate(ranking_cases):
                _validate_ranking_row(row, f"{label}.ranking_cases[{index}]")
            case_ids = [row["case_id"] for row in ranking_cases]
            if len(set(case_ids)) != len(case_ids):
                raise MethodDeltaError(
                    f"{label}.ranking_cases contain a duplicate case_id"
                )
        if metrics is not None:
            if not isinstance(metrics, Mapping):
                raise MethodDeltaError(f"{label} metrics must be an object")
            if not isinstance(scenarios, list) or not isinstance(ranking_cases, list):
                raise MethodDeltaError(
                    f"{label} declares metrics without verifiable scenario and "
                    "ranking rows"
                )
            if _metrics(scenarios, ranking_cases) != dict(metrics):
                raise MethodDeltaError(
                    f"{label} metrics do not match the scenario and ranking rows"
                )


def seal_snapshot(
    snapshot: Mapping[str, Any],
    *,
    parent_snapshot_id: str | None | object = _parent_unspecified,
) -> dict[str, Any]:
    """Return a snapshot whose id binds all content except the id itself."""

    if not isinstance(snapshot, Mapping):
        raise MethodDeltaError("snapshot must be an object")
    payload = copy.deepcopy(dict(snapshot))
    if payload.get("schema") != SCHEMA:
        raise MethodDeltaError("only v2 snapshots can be sealed")
    existing_id = payload.get("snapshot_id")
    if existing_id is not None:
        validate_snapshot(payload)
        if (
            parent_snapshot_id is _parent_unspecified
            or parent_snapshot_id == payload.get("parent_snapshot_id")
        ):
            return copy.deepcopy(payload)
    if parent_snapshot_id is not _parent_unspecified:
        payload["parent_snapshot_id"] = parent_snapshot_id
    else:
        payload.setdefault("parent_snapshot_id", None)
    payload.setdefault("chronology", _chronology_declaration())
    payload["snapshot_id"] = None
    _validate_snapshot_shape(payload, "snapshot")
    payload["snapshot_id"] = (
        _snapshot_id_prefix + _snapshot_content_sha256(payload)
    )
    validate_snapshot(payload)
    return copy.deepcopy(payload)


def validate_snapshot(
    snapshot: Mapping[str, Any],
    *,
    label: str = "snapshot",
) -> str:
    """Validate a sealed snapshot and return its exact canonical-byte digest."""

    if not isinstance(snapshot, Mapping):
        raise MethodDeltaError(f"{label} must be an object")
    payload = copy.deepcopy(dict(snapshot))
    _validate_snapshot_shape(payload, label)
    snapshot_id = payload.get("snapshot_id")
    if not _is_snapshot_id(snapshot_id):
        raise MethodDeltaError(f"{label} has an invalid snapshot_id")
    expected_id = _snapshot_id_prefix + _snapshot_content_sha256(payload)
    if snapshot_id != expected_id:
        raise MethodDeltaError(f"{label} snapshot_id does not match its content")
    return snapshot_sha256(payload)


def _comparison_content_sha256(comparison: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_comparison_bytes(comparison, normalize_identity=True)
    ).hexdigest()


def comparison_sha256(comparison: Mapping[str, Any]) -> str:
    """Hash the exact canonical bytes of a sealed comparison."""

    return hashlib.sha256(
        _canonical_comparison_bytes(comparison, normalize_identity=False)
    ).hexdigest()


def _validate_comparison_shape(comparison: Mapping[str, Any], label: str) -> None:
    if set(comparison) != _comparison_keys:
        raise MethodDeltaError(f"{label} has the wrong fields")
    if comparison.get("schema") != SCHEMA:
        raise MethodDeltaError(f"{label} has the wrong schema")
    if comparison.get("record_kind") != "comparison":
        raise MethodDeltaError(f"{label} is not a comparison record")
    if comparison.get("synthetic_only") is not True:
        raise MethodDeltaError(f"{label} must remain synthetic-only")
    if comparison.get("claim_boundary") != CLAIM_BOUNDARY:
        raise MethodDeltaError(f"{label} has the wrong claim boundary")
    if not _is_snapshot_id(comparison.get("snapshot_id")):
        raise MethodDeltaError(f"{label} has an invalid snapshot_id")
    parent_id = comparison.get("parent_snapshot_id")
    if parent_id is not None and not _is_snapshot_id(parent_id):
        raise MethodDeltaError(f"{label} has an invalid parent_snapshot_id")
    if not _is_sha256(comparison.get("current_snapshot_sha256")):
        raise MethodDeltaError(f"{label} has an invalid current_snapshot_sha256")
    previous_digest = comparison.get("previous_snapshot_sha256")
    previous_schema = comparison.get("previous_snapshot_schema")
    linkage_status = comparison.get("previous_linkage_status")
    if parent_id is None:
        if previous_digest is not None or previous_schema is not None:
            raise MethodDeltaError(f"{label} root comparison claims a previous snapshot")
        if linkage_status != "not_applicable":
            raise MethodDeltaError(f"{label} root linkage status is invalid")
    else:
        if not _is_sha256(previous_digest):
            raise MethodDeltaError(f"{label} has an invalid previous_snapshot_sha256")
        if previous_schema not in {SCHEMA, LEGACY_SCHEMA}:
            raise MethodDeltaError(f"{label} has an invalid previous_snapshot_schema")
        expected_status = (
            "legacy_snapshot_content_only"
            if previous_schema == LEGACY_SCHEMA
            else "immediate_snapshot_supplied_and_bound"
        )
        if linkage_status != expected_status:
            raise MethodDeltaError(f"{label} previous linkage status is invalid")
    proxies = comparison.get("internal_synthetic_proxies")
    if not isinstance(proxies, Mapping) or set(proxies) != _proxy_keys:
        raise MethodDeltaError(f"{label} has invalid internal synthetic proxies")
    if any(not isinstance(value, bool) for value in proxies.values()):
        raise MethodDeltaError(f"{label} synthetic proxy values must be booleans")
    if comparison.get("external_outcomes") != {
        "child_benefit": "not_established",
        "competition_prize": "not_established",
    }:
        raise MethodDeltaError(f"{label} makes an unsupported external outcome claim")
    verdicts = {"better", "worse", "complex_not_better", "invalid"}
    if comparison.get("verdict") not in verdicts:
        raise MethodDeltaError(f"{label} has an invalid verdict")
    if comparison.get("internal_joint_verdict") not in verdicts:
        raise MethodDeltaError(f"{label} has an invalid internal joint verdict")
    if comparison.get("compared_to") not in {
        "freeze_envelope",
        "previous_snapshot",
    }:
        raise MethodDeltaError(f"{label} has an invalid comparison target")
    deltas = comparison.get("deltas")
    if not isinstance(deltas, Mapping) or set(deltas) != {
        "n_independent_families_blocked_from_advancing",
        "mean_culture_remaining",
        "ranking_accuracy",
        "n_true_opened",
    }:
        raise MethodDeltaError(f"{label} has invalid delta fields")
    current_metrics = comparison.get("current_metrics")
    if not isinstance(current_metrics, Mapping) or {
        "n_independent_families_killed",
        "n_holdout_killed",
        "holdout_missing",
    } & set(current_metrics):
        raise MethodDeltaError(f"{label} has invalid or legacy current metrics")
    if not isinstance(comparison.get("reviewer"), Mapping):
        raise MethodDeltaError(f"{label} reviewer must be an object")


def _seal_comparison(comparison: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(comparison))
    payload["comparison_id"] = None
    payload["comparison_id"] = (
        _snapshot_id_prefix + _comparison_content_sha256(payload)
    )
    validate_comparison(payload)
    return copy.deepcopy(payload)


def validate_comparison(
    comparison: Mapping[str, Any],
    *,
    label: str = "comparison",
) -> str:
    if not isinstance(comparison, Mapping):
        raise MethodDeltaError(f"{label} must be an object")
    payload = copy.deepcopy(dict(comparison))
    _validate_comparison_shape(payload, label)
    comparison_id = payload.get("comparison_id")
    if not _is_snapshot_id(comparison_id):
        raise MethodDeltaError(f"{label} has an invalid comparison_id")
    expected_id = _snapshot_id_prefix + _comparison_content_sha256(payload)
    if comparison_id != expected_id:
        raise MethodDeltaError(f"{label} comparison_id does not match its content")
    return comparison_sha256(payload)


def _lab_object(gate: str | None) -> str:
    if not gate:
        return "desktop_claim"
    return SPEND_LADDER.get(gate, ("desktop_claim", 0))[0]


def _culture_remaining(gate: str | None) -> int:
    if not gate:
        return 0
    return SPEND_LADDER.get(gate, ("desktop_claim", 0))[1]


def _family_for(name: str) -> str:
    return FAMILY_BY_SCENARIO.get(name, f"other.{name}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MethodDeltaError(f"freeze manifest contains duplicate key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise MethodDeltaError(f"freeze manifest contains non-finite number: {value}")


def _finite_manifest_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise MethodDeltaError(f"freeze manifest contains non-finite number: {value}")
    return parsed


def freeze_pointers(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Read freeze hashes only. Do not open bound report text."""

    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    manifest_path = root / Path(MANIFEST_PATH)
    try:
        # Bounded read — stat-then-read races a swap and materializes an
        # oversized file before any limit could apply.
        with manifest_path.open("rb") as handle:
            raw = handle.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise MethodDeltaError("freeze manifest exceeds the byte ceiling")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
            parse_float=_finite_manifest_float,
        )
    except RecursionError as exc:
        raise MethodDeltaError("freeze manifest JSON is nested too deeply") from exc
    except (OverflowError, MemoryError) as exc:
        raise MethodDeltaError(
            "freeze manifest contains an out-of-range or oversized value"
        ) from exc
    artifacts = []
    n_checked = 0
    manifest_artifacts = payload.get("artifacts")
    passed = isinstance(manifest_artifacts, list) and bool(manifest_artifacts)
    if not isinstance(manifest_artifacts, list):
        manifest_artifacts = []
    root_resolved = root.resolve()
    seen_paths: set[str] = set()
    for item in manifest_artifacts:
        if not isinstance(item, Mapping):
            passed = False
            continue
        relative = str(item.get("path") or "")
        expected = str(item.get("sha256") or "")
        pure = PurePosixPath(relative)
        confined = (
            bool(relative)
            and not pure.is_absolute()
            and ".." not in pure.parts
            and "\\" not in relative
            and ":" not in relative
        )
        path = root / relative
        n_checked += 1
        if relative in seen_paths:
            passed = False
        seen_paths.add(relative)
        actual = ""
        if confined and path.is_file() and not path.is_symlink():
            resolved = path.resolve()
            if resolved != root_resolved and resolved.is_relative_to(root_resolved):
                actual = _sha256(path)
        match = bool(expected) and actual == expected
        if not match:
            passed = False
        artifacts.append(
            {
                "path": relative,
                "role": item.get("role"),
                "sha256": expected,
                "matched": match,
            }
        )
    return {
        "source_commit": payload.get("source_commit"),
        "n_artifacts_checked": n_checked,
        "passed": passed,
        "artifacts": artifacts,
    }


def living_method_pointers(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Bind the executable living method surface evaluated by this receipt."""

    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    patterns = (
        "src/mva_hackathon/*.py",
        "scripts/*.py",
        "tests/test_*.py",
        "schemas/*.json",
        "templates/community/*",
        "configs/*.json",
    )
    documents = (
        "COMPETITION_CONTRACT.md",
        "PIPELINE_SPEC.md",
        "README.md",
        "reports/TRACK2_AI_LINE.md",
        "reports/TRACK2_ATTEMPT2_DELTA.md",
        "reports/TRACK2_EXPOSURE_GATE.md",
        "reports/TRACK2_LINEAGE_CONTRACT.md",
        "reports/TRACK2_METHOD_DELTA.md",
        "reports/TRACK2_METHOD_IMPROVEMENTS.md",
        "reports/TRACK2_PROGRAM_GATES.md",
        "reports/TRACK2_RANDOMIZATION_CONTRACT.md",
    )
    if root.is_symlink() or os.path.isjunction(root):
        raise MethodDeltaError(
            "living method root must be a real directory"
        )
    paths = sorted(
        {
            path
            for pattern in patterns
            for path in root.glob(pattern)
            if path.is_file()
        }
        | {
            root / relative
            for relative in documents
            if (root / relative).is_file()
        },
        key=lambda path: path.relative_to(root).as_posix(),
    )
    artifacts = []
    paths_by_file_identity: dict[tuple[int, int], str] = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            details = path.stat()
        except OSError as exc:
            raise MethodDeltaError(
                f"cannot identify living method artifact: {relative}"
            ) from exc
        if path.is_symlink() or os.path.isjunction(path):
            raise MethodDeltaError(
                f"living method artifact is a symlink: {relative}"
            )
        if not path.resolve().is_relative_to(root.resolve()):
            raise MethodDeltaError(
                f"living method artifact escapes the root: {relative}"
            )
        identity = (details.st_dev, details.st_ino)
        existing = paths_by_file_identity.get(identity)
        if existing is not None:
            raise MethodDeltaError(
                "living method artifacts resolve to the same underlying file: "
                f"{existing} and {relative}"
            )
        paths_by_file_identity[identity] = relative
        artifacts.append({"path": relative, "sha256": _sha256(path)})
    encoded = json.dumps(
        artifacts, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    , allow_nan=False)
    return {
        "n_artifacts": len(artifacts),
        "bundle_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "artifacts": artifacts,
    }


def _scenario_row(item: Mapping[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or "")
    kind = str(item.get("kind") or "")
    if kind == "false_path" and name not in FAMILY_BY_SCENARIO:
        raise MethodDeltaError(
            f"false-path scenario {name!r} has no declared family"
        )
    gate = str(item.get("earliest_nonpass_gate") or item.get("blocked_by") or "")
    return {
        "scenario_id": name,
        "kind": kind,
        "family_id": _family_for(name),
        "motivation": "literature_family" if kind == "false_path" else "envelope_gap",
        "decision": item.get("decision"),
        "blocked_by": item.get("blocked_by"),
        "block_reason": item.get("block_reason"),
        "terminal_blocked_by": item.get("blocked_by"),
        "terminal_block_reason": item.get("block_reason"),
        "earliest_nonpass_gate": item.get("earliest_nonpass_gate") or item.get("blocked_by"),
        "earliest_nonpass_effect": item.get("earliest_nonpass_effect"),
        "earliest_nonpass_reason": item.get("earliest_nonpass_reason") or item.get("block_reason"),
        "lab_object": _lab_object(gate),
        "culture_remaining": _culture_remaining(gate),
        "blocked_from_advancing": bool(
            item.get("blocked_from_advancing", item.get("killed"))
        ),
        "opened": bool(item.get("opened")),
        "discriminable_at_freeze": False,
    }


def _ranking_cases(suite: Mapping[str, Any], community: Mapping[str, Any]) -> list[dict[str, Any]]:
    next_step = next(
        (
            item
            for item in community.get("steps", [])
            if isinstance(item, Mapping) and item.get("name") == "next_experiment"
        ),
        {},
    )
    public_step = (next_step.get("result") or {}).get("recommended_step")
    probe = next(
        (
            item
            for item in suite.get("scenarios", [])
            if isinstance(item, Mapping) and item.get("name") == "probe_before_identity"
        ),
        {},
    )
    return [
        {
            "case_id": "public_toolkit",
            "expected_step": "confirmation",
            "observed_step": public_step,
            "identity_complete": False,
            "probe_before_identity_stopped": False,
            "correct": public_step == "confirmation",
        },
        {
            "case_id": "probe_before_identity",
            "expected_step": "confirmation",
            "observed_step": "confirmation",
            "identity_complete": False,
            "probe_before_identity_stopped": probe.get("blocked_by") == "next_experiment",
            "correct": probe.get("blocked_by") == "next_experiment",
        },
    ]


def earliest_remaining_by_family(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    """Max remaining spend saved in each independently blocked family.

    Cloning a later block inside a family already blocked earlier cannot
    lower this number. Higher remaining means the family was first-blocked
    sooner on the spend ladder.
    """

    remaining: dict[str, int] = {}
    for row in rows:
        blocked = row.get("blocked_from_advancing")
        if blocked is None:
            # Explicit v1 compatibility for immutable legacy snapshots only.
            blocked = row.get("killed")
        if row.get("kind") != "false_path" or blocked is not True:
            continue
        if row.get("motivation") == "tautological":
            continue
        family_id = str(row.get("family_id") or "")
        if not family_id:
            continue
        value = int(row.get("culture_remaining") or 0)
        remaining[family_id] = max(remaining.get(family_id, 0), value)
    return remaining


def _metrics(rows: list[Mapping[str, Any]], ranking: list[Mapping[str, Any]]) -> dict[str, Any]:
    false_rows = [row for row in rows if row.get("kind") == "false_path"]
    family_remaining = earliest_remaining_by_family(rows)
    remaining = list(family_remaining.values())
    ranking_correct = sum(1 for row in ranking if row.get("correct"))
    ranking_n = len(ranking)
    first_blocks = {
        str(row.get("earliest_nonpass_gate"))
        for row in false_rows
        if row.get("blocked_from_advancing") and row.get("earliest_nonpass_gate")
    }
    unused = [name for name in STRUCTURAL_GATES if name not in first_blocks]
    holdout_blocked = [name for name in HOLDOUT_FAMILIES if name in family_remaining]
    return {
        "n_true_opened": sum(1 for row in rows if row.get("kind") == "true_path" and row.get("opened")),
        "n_true": sum(1 for row in rows if row.get("kind") == "true_path"),
        "n_independent_families_blocked_from_advancing": len(family_remaining),
        "n_false_families": len({str(row.get("family_id")) for row in false_rows}),
        "mean_culture_remaining": (
            sum(remaining) / len(remaining) if remaining else 0.0
        ),
        "culture_remaining_direction": CULTURE_REMAINING_DIRECTION,
        "ranking_accuracy": ranking_correct / ranking_n if ranking_n else 0.0,
        "ranking_identity_violations": sum(
            1
            for row in ranking
            if row.get("case_id") == "probe_before_identity"
            and not row.get("probe_before_identity_stopped")
        ),
        "n_unused_gates": len(unused),
        "unused_gates": unused,
        "n_tautological_scenarios": sum(
            1 for row in rows if row.get("motivation") == "tautological"
        ),
        "first_block_gates": sorted(first_blocks),
        "n_holdout_families_blocked_from_advancing": len(holdout_blocked),
        "n_holdout": len(HOLDOUT_FAMILIES),
        "holdout_families_not_blocked": [
            name for name in HOLDOUT_FAMILIES if name not in family_remaining
        ],
    }


def snapshot_method(
    repo_root: str | Path | None = None,
    *,
    parent_snapshot_id: str | None = None,
    recorded_at: str | None = None,
    exposure_started_at: str | None = None,
) -> dict[str, Any]:
    """Run the living suite and the public toolkit. Not a child's result."""

    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    suite = run_save_path_suite()
    community = run_community_pipeline(root / "templates" / "community")
    pointers = freeze_pointers(root)
    living_pointers = living_method_pointers(root)
    rows = [_scenario_row(item) for item in suite.get("scenarios", []) if isinstance(item, Mapping)]
    ranking = _ranking_cases(suite, community)
    metrics = _metrics(rows, ranking)
    next_step = next(
        (
            item
            for item in community.get("steps", [])
            if isinstance(item, Mapping) and item.get("name") == "next_experiment"
        ),
        {},
    )
    ranking_checkpoint = (suite.get("structure_ranking") or {}).get("checkpoint_ready") is False
    invariants = {
        "true_path_opens": bool(suite.get("save_path_reachable")),
        "public_confirmation_holds": (
            community.get("decision") == "hold"
            and community.get("blocked_by") == "confirmation"
        ),
        "freeze_bytes_untouched": bool(pointers.get("passed")),
        "no_medicine_claim": CLAIM_BOUNDARY.startswith("Method-delta"),
        "ranking_cannot_open_checkpoint": ranking_checkpoint,
        "identity_violations_zero": metrics["ranking_identity_violations"] == 0,
        "public_recommended_confirmation": (
            (next_step.get("result") or {}).get("recommended_step") == "confirmation"
        ),
        "holdout_families_still_blocked": not metrics.get(
            "holdout_families_not_blocked"
        ),
        "living_method_surface_bound": (
            living_pointers.get("n_artifacts", 0) > 0
            and bool(living_pointers.get("bundle_sha256"))
        ),
    }
    snapshot = {
        "schema": SCHEMA,
        "record_kind": "snapshot",
        "snapshot_id": None,
        "parent_snapshot_id": parent_snapshot_id,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "chronology": _chronology_declaration(
            recorded_at=recorded_at,
            exposure_started_at=exposure_started_at,
        ),
        "freeze_pointers": {
            "source_commit": pointers.get("source_commit"),
            "n_artifacts_checked": pointers.get("n_artifacts_checked"),
            "passed": pointers.get("passed"),
            "artifacts": [
                {
                    "path": item["path"],
                    "role": item["role"],
                    "sha256": item["sha256"],
                }
                for item in pointers.get("artifacts", [])
            ],
        },
        "freeze_integrity": {
            "passed": pointers.get("passed"),
            "n_artifacts_checked": pointers.get("n_artifacts_checked"),
        },
        "living_method_integrity": living_pointers,
        "capability_envelope": [
            {
                "method_family_id": name,
                "available_at_freeze": available,
            }
            for name, available in FREEZE_ENVELOPE
        ],
        "invariants": {
            key: {"passed": value, "detail": key if value else f"{key}_failed"}
            for key, value in invariants.items()
        },
        "registered_gates": list(STRUCTURAL_GATES),
        "metrics": metrics,
        "scenarios": rows,
        "ranking_cases": ranking,
        "public_toolkit": {
            "decision": community.get("decision"),
            "blocked_by": community.get("blocked_by"),
            "block_reason": community.get("block_reason"),
        },
        "save_path": {
            "n_true_path_opened": suite.get("n_true_path_opened"),
            "n_true_path": suite.get("n_true_path"),
            "n_false_paths_blocked_from_advancing": suite.get(
                "n_false_paths_blocked_from_advancing",
                suite.get("n_false_path_killed"),
            ),
            "n_false_path": suite.get("n_false_path"),
            "save_path_reachable": suite.get("save_path_reachable"),
            "structure_ranking_checkpoint_ready": (
                (suite.get("structure_ranking") or {}).get("checkpoint_ready")
            ),
        },
    }
    return seal_snapshot(snapshot, parent_snapshot_id=parent_snapshot_id)


REQUIRED_INVARIANTS = frozenset(
    {
        "true_path_opens",
        "public_confirmation_holds",
        "freeze_bytes_untouched",
        "no_medicine_claim",
        "ranking_cannot_open_checkpoint",
        "identity_violations_zero",
        "public_recommended_confirmation",
        "holdout_families_still_blocked",
        "living_method_surface_bound",
    }
)


def _strict_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _living_bundle_sha(artifacts: Any) -> str:
    encoded = json.dumps(
        artifacts, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    , allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _invariants_pass(snapshot: Mapping[str, Any]) -> bool:
    items = snapshot.get("invariants")
    if not isinstance(items, Mapping) or set(items) != REQUIRED_INVARIANTS:
        return False
    if not all(
        isinstance(row, Mapping) and row.get("passed") is True for row in items.values()
    ):
        return False
    # Cross-check every invariant that can be re-derived from the snapshot's own
    # sub-records, so a declared pass cannot outlive its evidence.
    save_path = snapshot.get("save_path")
    public_toolkit = snapshot.get("public_toolkit")
    freeze = snapshot.get("freeze_pointers")
    living = snapshot.get("living_method_integrity")
    metrics = snapshot.get("metrics")
    claim_boundary = snapshot.get("claim_boundary")
    scenarios = snapshot.get("scenarios")
    ranking_cases = snapshot.get("ranking_cases")
    derivable = {
        "true_path_opens": isinstance(scenarios, list)
        and any(
            isinstance(row, Mapping)
            and row.get("kind") == "true_path"
            and row.get("opened") is True
            for row in scenarios
        ),
        "public_confirmation_holds": isinstance(public_toolkit, Mapping)
        and public_toolkit.get("decision") == "hold"
        and public_toolkit.get("blocked_by") == "confirmation",
        "freeze_bytes_untouched": isinstance(freeze, Mapping)
        and freeze.get("passed") is True
        and _strict_positive_int(freeze.get("n_artifacts_checked"))
        and isinstance(freeze.get("artifacts"), list)
        and len(freeze["artifacts"]) == freeze["n_artifacts_checked"],
        "living_method_surface_bound": isinstance(living, Mapping)
        and _strict_positive_int(living.get("n_artifacts"))
        and isinstance(living.get("artifacts"), list)
        and living["n_artifacts"] == len(living["artifacts"])
        and isinstance(living.get("bundle_sha256"), str)
        and living["bundle_sha256"] == _living_bundle_sha(living["artifacts"]),
        "identity_violations_zero": isinstance(metrics, Mapping)
        and metrics.get("ranking_identity_violations") == 0
        and not isinstance(metrics.get("ranking_identity_violations"), bool),
        "holdout_families_still_blocked": isinstance(metrics, Mapping)
        and isinstance(metrics.get("holdout_families_not_blocked"), list)
        and not metrics["holdout_families_not_blocked"],
        "no_medicine_claim": isinstance(claim_boundary, str)
        and claim_boundary.startswith("Method-delta"),
        "public_recommended_confirmation": isinstance(ranking_cases, list)
        and any(
            isinstance(row, Mapping)
            and row.get("case_id") == "public_toolkit"
            and row.get("observed_step") == "confirmation"
            and row.get("correct") is True
            for row in ranking_cases
        ),
        "ranking_cannot_open_checkpoint": isinstance(save_path, Mapping)
        and save_path.get("structure_ranking_checkpoint_ready") is False
        and isinstance(scenarios, list)
        and any(
            isinstance(row, Mapping)
            and row.get("scenario_id") == "ranking_cannot_open_checkpoint"
            and row.get("blocked_from_advancing") is True
            and row.get("opened") is False
            for row in scenarios
        ),
    }
    return all(derivable.values())


def _blocked_from_advancing(row: Mapping[str, Any]) -> bool:
    if "blocked_from_advancing" in row:
        return row.get("blocked_from_advancing") is True
    return row.get("killed") is True


def _metric_value(
    metrics: Mapping[str, Any],
    current_name: str,
    legacy_name: str,
    default: Any = 0,
) -> Any:
    if current_name in metrics:
        return metrics.get(current_name)
    return metrics.get(legacy_name, default)


def _holdout_families_not_blocked(metrics: Mapping[str, Any]) -> list[Any]:
    value = _metric_value(
        metrics,
        "holdout_families_not_blocked",
        "holdout_missing",
        [],
    )
    return list(value) if isinstance(value, list) else []


def assess_reviewer_verdict(
    comparison: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Second opinion beside the numeric script. Not a panel score."""

    script = comparison.get("verdict")
    metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), Mapping) else {}
    families = {
        str(row.get("family_id"))
        for row in snapshot.get("scenarios") or []
        if isinstance(row, Mapping) and _blocked_from_advancing(row)
    }
    invariants = snapshot.get("invariants") if isinstance(snapshot.get("invariants"), Mapping) else {}
    checks = {
        "true_path_opens": (invariants.get("true_path_opens") or {}).get("passed") is True,
        "freeze_bytes_untouched": (invariants.get("freeze_bytes_untouched") or {}).get("passed") is True,
        "holdout_families_blocked": not _holdout_families_not_blocked(metrics),
        "false_rescue_or_window_family": any(
            name.startswith("false_rescue.") or name.startswith("window.") for name in families
        ),
        "script_usable": script in {"better", "complex_not_better", "worse", "invalid"},
    }
    remaining_delta = 0.0
    deltas = comparison.get("deltas")
    if comparison.get("compared_to") == "previous_snapshot":
        if not isinstance(deltas, Mapping):
            raise MethodDeltaError(
                "previous-snapshot comparison lacks a deltas object"
            )
        value = deltas.get("mean_culture_remaining")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise MethodDeltaError(
                "previous-snapshot comparison lacks a finite mean_culture_remaining"
            )
        remaining_delta = float(value)
    checks["mean_remaining_not_diluted"] = (
        comparison.get("compared_to") != "previous_snapshot" or remaining_delta >= -1e-9
    )
    if script == "invalid" or not checks["true_path_opens"] or not checks["freeze_bytes_untouched"]:
        reviewer = "invalid"
        reason = "invariants_failed"
    elif script == "worse":
        reviewer = "agree_worse"
        reason = str(comparison.get("reason") or "worse")
    elif (
        script == "better"
        and comparison.get("compared_to") == "previous_snapshot"
        and remaining_delta < -1e-9
        and checks["true_path_opens"]
        and checks["freeze_bytes_untouched"]
        and checks["holdout_families_blocked"]
    ):
        reviewer = "agree_complex"
        reason = "families_up_mean_diluted"
    elif script == "better" and all(
        checks[key]
        for key in (
            "true_path_opens",
            "freeze_bytes_untouched",
            "holdout_families_blocked",
            "false_rescue_or_window_family",
        )
    ):
        reviewer = "agree_better"
        reason = "script_and_reviewer_agree"
    elif script == "complex_not_better" and checks["true_path_opens"]:
        reviewer = "agree_complex"
        reason = str(comparison.get("reason") or "no_discrimination_gain")
    else:
        reviewer = "disagree"
        reason = "reviewer_rejected_script"
    return {
        "schema": "mva-track2-reviewer-verdict/v2",
        "synthetic_only": True,
        "claim_boundary": (
            "Reviewer-verdict software contract only; a second opinion is not "
            "a panel score, not a rescued child, and not an upload."
        ),
        "script_verdict": script,
        "reviewer_verdict": reviewer,
        "reason": reason,
        "checks": checks,
        "agreed": reviewer.startswith("agree"),
    }


def compare_method_delta(
    current: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Lexicographic internal verdict over sealed snapshots."""

    current_copy = copy.deepcopy(dict(current))
    previous_copy = None if previous is None else copy.deepcopy(dict(previous))
    validate_snapshot(current_copy, label="current snapshot")
    if current_copy.get("schema") != SCHEMA:
        raise MethodDeltaError("current snapshot must use the hardened v2 schema")
    previous_snapshot_sha256 = None
    previous_snapshot_schema = None
    if previous_copy is None:
        if current_copy.get("parent_snapshot_id") is not None:
            raise MethodDeltaError(
                "current snapshot has a parent but no previous snapshot was supplied"
            )
    else:
        previous_snapshot_sha256 = validate_snapshot(
            previous_copy, label="previous snapshot"
        )
        previous_snapshot_schema = previous_copy.get("schema")
        expected_parent_id = previous_copy.get("snapshot_id")
        current_parent_id = current_copy.get("parent_snapshot_id")
        if current_parent_id != expected_parent_id:
            raise MethodDeltaError(
                "current snapshot must be resealed with the supplied previous parent"
            )
    current_snapshot_sha256 = validate_snapshot(
        current_copy, label="current snapshot"
    )
    current_metrics = current_copy.get("metrics")
    if not isinstance(current_metrics, Mapping):
        raise MethodDeltaError("current snapshot has no metrics")
    current_families = int(
        _metric_value(
            current_metrics,
            "n_independent_families_blocked_from_advancing",
            "n_independent_families_killed",
        )
        or 0
    )
    if not _invariants_pass(current_copy):
        verdict = "invalid"
        reason = "invariants_failed"
    elif previous_copy is None:
        if int(current_metrics.get("n_true_opened") or 0) < 1:
            verdict = "worse"
            reason = "true_path_closed"
        elif current_families < 1:
            verdict = "complex_not_better"
            reason = "no_nested_families"
        else:
            verdict = "better"
            reason = "nested_method_beyond_freeze"
    else:
        previous_metrics = previous_copy.get("metrics")
        if not isinstance(previous_metrics, Mapping):
            raise MethodDeltaError("previous snapshot has no metrics")
        previous_families = int(
            _metric_value(
                previous_metrics,
                "n_independent_families_blocked_from_advancing",
                "n_independent_families_killed",
            )
            or 0
        )
        current_gates = set(current_copy.get("registered_gates") or [])
        previous_gates = set(previous_copy.get("registered_gates") or [])
        new_gates = sorted(current_gates - previous_gates)
        first_blocks = set(current_metrics.get("first_block_gates") or [])
        unused_new = [name for name in new_gates if name not in first_blocks]
        prev_remaining = float(previous_metrics.get("mean_culture_remaining") or 0.0)
        curr_remaining = float(current_metrics.get("mean_culture_remaining") or 0.0)
        families_up = current_families > previous_families
        earlier = curr_remaining > prev_remaining + 1e-9
        later = curr_remaining < prev_remaining - 1e-9
        ranking_up = float(current_metrics.get("ranking_accuracy") or 0.0) > float(
            previous_metrics.get("ranking_accuracy") or 0.0
        )
        true_closed = int(current_metrics.get("n_true_opened") or 0) < int(
            previous_metrics.get("n_true_opened") or 0
        )
        if true_closed:
            verdict = "worse"
            reason = "true_path_closed"
        elif unused_new:
            verdict = "worse"
            reason = "unused_new_gate"
        elif families_up or earlier:
            verdict = "better"
            reason = (
                "independent_families_blocked_from_advancing"
                if families_up
                else "earlier_block"
            )
        elif later:
            verdict = "worse"
            reason = "later_block"
        elif ranking_up:
            verdict = "complex_not_better"
            reason = "ranking_accuracy_only"
        else:
            verdict = "complex_not_better"
            reason = "no_discrimination_gain"
    earlier_or_broader_proxy = False
    method_contract_usable = (
        _invariants_pass(current_copy) and reason != "unused_new_gate"
    )
    if verdict == "invalid":
        method_contract_usable = False
    elif previous_copy is None:
        earlier_or_broader_proxy = (
            current_families >= 1
            and float(current_metrics.get("mean_culture_remaining") or 0.0) > 0.0
        )
    else:
        previous_metrics = previous_copy.get("metrics") or {}
        previous_families = int(
            _metric_value(
                previous_metrics,
                "n_independent_families_blocked_from_advancing",
                "n_independent_families_killed",
            )
            or 0
        )
        earlier_or_broader_proxy = reason in {
            "independent_families_blocked_from_advancing",
            "earlier_block",
        } or (
            current_families > previous_families
            or float(current_metrics.get("mean_culture_remaining") or 0.0)
            > float(previous_metrics.get("mean_culture_remaining") or 0.0)
            + 1e-9
        )
    joint_better = (
        verdict == "better" and earlier_or_broader_proxy and method_contract_usable
    )
    internal_joint_verdict = (
        "better"
        if joint_better
        else (
            "complex_not_better"
            if verdict == "better" and not earlier_or_broader_proxy
            else verdict
        )
    )
    previous_families_for_delta = 0
    if previous_copy is not None:
        previous_metrics = previous_copy.get("metrics") or {}
        previous_families_for_delta = int(
            _metric_value(
                previous_metrics,
                "n_independent_families_blocked_from_advancing",
                "n_independent_families_killed",
            )
            or 0
        )
    comparison = {
        "schema": SCHEMA,
        "record_kind": "comparison",
        "comparison_id": None,
        "snapshot_id": current_copy.get("snapshot_id"),
        "parent_snapshot_id": current_copy.get("parent_snapshot_id"),
        "current_snapshot_sha256": current_snapshot_sha256,
        "previous_snapshot_sha256": previous_snapshot_sha256,
        "previous_snapshot_schema": previous_snapshot_schema,
        "previous_linkage_status": (
            "not_applicable"
            if previous_copy is None
            else "legacy_snapshot_content_only"
            if previous_snapshot_schema == LEGACY_SCHEMA
            else "immediate_snapshot_supplied_and_bound"
        ),
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "verdict": internal_joint_verdict,
        "reason": reason,
        "invariants_passed": _invariants_pass(current_copy),
        "deltas": {
            "n_independent_families_blocked_from_advancing": (
                current_families - previous_families_for_delta
            ),
            "mean_culture_remaining": float(current_metrics.get("mean_culture_remaining") or 0.0)
            - (
                0.0
                if previous_copy is None
                else float((previous_copy.get("metrics") or {}).get("mean_culture_remaining") or 0.0)
            ),
            "ranking_accuracy": float(current_metrics.get("ranking_accuracy") or 0.0)
            - (
                0.0
                if previous_copy is None
                else float((previous_copy.get("metrics") or {}).get("ranking_accuracy") or 0.0)
            ),
            "n_true_opened": int(current_metrics.get("n_true_opened") or 0),
        },
        "current_metrics": copy.deepcopy(dict(current_metrics)),
        "compared_to": "freeze_envelope" if previous_copy is None else "previous_snapshot",
        "internal_synthetic_proxies": {
            "earlier_or_broader_false_path_blocking": earlier_or_broader_proxy,
            "method_contract_usable": method_contract_usable,
            "joint_better": joint_better,
        },
        "external_outcomes": {
            "child_benefit": "not_established",
            "competition_prize": "not_established",
        },
        "internal_joint_verdict": internal_joint_verdict,
        "reviewer": assess_reviewer_verdict(
            {
                "verdict": verdict,
                "reason": reason,
                "compared_to": "freeze_envelope" if previous_copy is None else "previous_snapshot",
                "deltas": {
                    "mean_culture_remaining": float(
                        current_metrics.get("mean_culture_remaining") or 0.0
                    )
                    - (
                        0.0
                        if previous_copy is None
                        else float((previous_copy.get("metrics") or {}).get("mean_culture_remaining") or 0.0)
                    ),
                },
            },
            current_copy,
        ),
    }
    return _seal_comparison(comparison)


def _receipt_content_sha256(receipt: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_receipt_bytes(receipt, normalize_identity=True)
    ).hexdigest()


def receipt_sha256(receipt: Mapping[str, Any]) -> str:
    """Hash the exact canonical bytes of a sealed complete receipt."""

    return hashlib.sha256(
        _canonical_receipt_bytes(receipt, normalize_identity=False)
    ).hexdigest()


def seal_method_delta_receipt(
    snapshot: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one content-addressed v2 receipt from sealed snapshot inputs."""

    snapshot_copy = copy.deepcopy(dict(snapshot))
    previous_copy = None if previous is None else copy.deepcopy(dict(previous))
    comparison = compare_method_delta(snapshot_copy, previous=previous_copy)
    receipt = {
        "schema": SCHEMA,
        "record_kind": "receipt",
        "receipt_id": None,
        "snapshot": snapshot_copy,
        "previous_snapshot": previous_copy,
        "comparison": comparison,
        "external_anchor": copy.deepcopy(_external_anchor_declaration),
    }
    receipt["receipt_id"] = _snapshot_id_prefix + _receipt_content_sha256(receipt)
    validate_method_delta_receipt(receipt, previous=previous_copy)
    return copy.deepcopy(receipt)


def validate_method_delta_receipt(
    receipt: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a complete v2 receipt and return a detached snapshot copy."""

    if not isinstance(receipt, Mapping):
        raise MethodDeltaError("method-delta receipt must be an object")
    payload = copy.deepcopy(dict(receipt))
    if payload.get("schema") == LEGACY_SCHEMA or (
        isinstance(payload.get("snapshot"), Mapping)
        and payload["snapshot"].get("schema") == LEGACY_SCHEMA
    ):
        raise MethodDeltaError(
            "legacy v1 wrappers are not authenticated receipts; validate only "
            "their embedded sealed snapshot as explicitly labeled legacy input"
        )
    if set(payload) != _receipt_keys:
        raise MethodDeltaError("method-delta receipt has the wrong fields")
    if payload.get("schema") != SCHEMA or payload.get("record_kind") != "receipt":
        raise MethodDeltaError("method-delta receipt has the wrong schema or kind")
    if payload.get("external_anchor") != _external_anchor_declaration:
        raise MethodDeltaError("method-delta receipt has an invalid anchor declaration")
    snapshot = payload.get("snapshot")
    embedded_previous = payload.get("previous_snapshot")
    comparison = payload.get("comparison")
    if not isinstance(snapshot, Mapping) or not isinstance(comparison, Mapping):
        raise MethodDeltaError("method-delta receipt lacks snapshot or comparison")
    if snapshot.get("schema") != SCHEMA:
        raise MethodDeltaError("receipt snapshot must use the hardened v2 schema")
    validate_snapshot(snapshot, label="receipt snapshot")
    validate_comparison(comparison, label="receipt comparison")

    parent_snapshot_id = snapshot.get("parent_snapshot_id")
    supplied_previous = None if previous is None else copy.deepcopy(dict(previous))
    if parent_snapshot_id is None:
        if embedded_previous is not None:
            raise MethodDeltaError("root receipt must not embed a previous snapshot")
        if supplied_previous is not None:
            raise MethodDeltaError("previous snapshot was supplied for a root receipt")
        previous_copy = None
    else:
        if not isinstance(embedded_previous, Mapping):
            raise MethodDeltaError(
                "linked receipt must embed the immediate previous snapshot"
            )
        previous_copy = copy.deepcopy(dict(embedded_previous))
        validate_snapshot(previous_copy, label="embedded previous snapshot")
        if previous_copy.get("snapshot_id") != parent_snapshot_id:
            raise MethodDeltaError(
                "embedded previous snapshot does not match parent_snapshot_id"
            )
        if supplied_previous is not None:
            validate_snapshot(supplied_previous, label="supplied previous snapshot")
            if _canonical_snapshot_bytes(
                supplied_previous, normalize_identity=False
            ) != _canonical_snapshot_bytes(previous_copy, normalize_identity=False):
                raise MethodDeltaError(
                    "supplied previous snapshot differs from embedded previous snapshot"
                )
    expected_comparison = compare_method_delta(
        snapshot,
        previous=previous_copy,
    )
    if _canonical_comparison_bytes(
        comparison, normalize_identity=False
    ) != _canonical_comparison_bytes(expected_comparison, normalize_identity=False):
        raise MethodDeltaError(
            "receipt comparison does not equal deterministic recomputation"
        )

    receipt_id = payload.get("receipt_id")
    if not _is_snapshot_id(receipt_id):
        raise MethodDeltaError("method-delta receipt has an invalid receipt_id")
    expected_receipt_id = _snapshot_id_prefix + _receipt_content_sha256(payload)
    if receipt_id != expected_receipt_id:
        raise MethodDeltaError("receipt_id does not match complete receipt content")
    return copy.deepcopy(dict(snapshot))


__all__ = [
    "CLAIM_BOUNDARY",
    "CULTURE_REMAINING_DIRECTION",
    "EXTERNAL_ANCHOR_REQUIREMENT",
    "FAMILY_BY_SCENARIO",
    "HOLDOUT_FAMILIES",
    "LEGACY_SCHEMA",
    "SCHEMA",
    "SPEND_LADDER",
    "MethodDeltaError",
    "assess_reviewer_verdict",
    "compare_method_delta",
    "comparison_sha256",
    "earliest_remaining_by_family",
    "freeze_pointers",
    "living_method_pointers",
    "receipt_sha256",
    "seal_method_delta_receipt",
    "seal_snapshot",
    "snapshot_sha256",
    "snapshot_method",
    "validate_method_delta_receipt",
    "validate_snapshot",
]
