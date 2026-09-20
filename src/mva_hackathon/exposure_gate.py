"""Exposure-gate contract: nominal bath concentration is not cell exposure.

A program can advance only when unbound medium and intracellular parent are
both reported, both greater than zero, and inside the conservative window.
A measured zero inside the cell cannot pass. Exploratory rows may exist
beside that window. A nontranslational high concentration is a stop.
This is not a human dose, not pharmacokinetics in a person, and not
efficacy evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from mva_hackathon.provenance import receipt_sha256

from mva_hackathon.arm_allocation import (
    ArmAllocationError,
    assess_preexposure_allocation,
    skipped_preexposure_allocation,
)


SCHEMA = "mva-track2-exposure-gate/v2"
TABLE_SCHEMA = "mva.community-measured-exposure-table/v1"
ADVANCE_MAX_UM = 2.0
EXPLORATORY_MAX_UM = 5.0
NONTRANSLATIONAL_UM = 50.0
MIN_CONSTANT_WINDOW_HOURS = 1.0
STATUSES = ("pass", "stop", "not_assessable")
ROW_CLASSES = (
    "leq_2um",
    "exploratory_5um",
    "nontranslational_high",
    "aminoglycoside_carryover",
    "not_assessable",
)
MEASUREMENT_CLASSES = ("culture_measured", "label_estimate")
TIME_PROFILE_CLASSES = ("constant", "pulse")
SAMPLE_RELATIONS = ("same_plate", "matched_parallel_culture")
SELECTION_AGENT_CLASSES = ("none", "aminoglycoside", "non_aminoglycoside")
# How a selection agent was demonstrated absent from the assay window.
# A bare boolean is a checkbox, not evidence — a clearance claim is
# honored only alongside a declared method.
SELECTION_CLEARANCE_METHODS = (
    "serial_passage_without_agent",
    "documented_media_exchange",
)
BINDING_SCHEMA = "mva-track2-exposure-assay-binding/v2"
LINEAGE_COUNTS_SCHEMA = "mva-track2-lineage-counts/v1"
ASSAY_PLAN_SCHEMA = "mva.community-assay-power/v1"
CLAIM_BOUNDARY = (
    "Exposure-gate software contract only; nominal bath concentration is "
    "not cell exposure; a declared contact pattern is not a measured "
    "concentration-time profile; this is not a human dose and not efficacy evidence."
)
BINDING_CLAIM_BOUNDARY = (
    "Exposure-to-assay metadata consistency only; a matched execution record "
    "does not prove physical sample identity, dosing accuracy, target engagement, "
    "efficacy, or benefit to a person."
)
REQUIRED_COLUMNS = (
    "nominal_uM",
    "unbound_medium_uM",
    "intracellular_parent",
    "time_hours",
    "pulse_vs_constant",
    "washout",
    "selection_agent",
    "selection_agent_cleared",
    "selection_clearance_method",
)


class ExposureGateError(ValueError):
    """Raised when an exposure table violates its contract."""


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ExposureGateError(f"{field} must be a non-empty identifier")
    if not value.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise ExposureGateError(f"{field} contains unsupported characters")
    if not value[0].isalpha():
        raise ExposureGateError(f"{field} must start with a letter")
    return value


def _allocation_context_identifier(value: object, field: str) -> str:
    result = _identifier(value, field)
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", result) is None:
        raise ExposureGateError(f"{field} must be a lowercase opaque identifier")
    return result


def _identifier_list(
    value: object,
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ExposureGateError(f"{field} must be an identifier array")
    parsed = tuple(_identifier(item, field) for item in value)
    if len(set(parsed)) != len(parsed):
        raise ExposureGateError(f"{field} contains duplicate identifiers")
    return tuple(sorted(parsed))


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ExposureGateError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExposureGateError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExposureGateError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _profile_payload(row: Mapping[str, Any], probe_id: object) -> dict[str, Any]:
    """Return normalized semantic fields for one measured exposure profile."""

    probe = _identifier(probe_id, "probe_id")
    nominal = _number(row.get("nominal_uM"), "nominal_uM")
    unbound = _number(
        row.get("unbound_medium_uM"), "unbound_medium_uM", allow_null=True
    )
    intracellular = _number(
        row.get("intracellular_parent"), "intracellular_parent", allow_null=True
    )
    duration = _number(row.get("time_hours"), "time_hours", allow_null=True)
    pattern = row.get("pulse_vs_constant")
    if pattern not in TIME_PROFILE_CLASSES:
        raise ExposureGateError("pulse_vs_constant is not in the allowed vocabulary")
    washout = row.get("washout")
    if washout is not None and not isinstance(washout, bool):
        raise ExposureGateError("washout must be a boolean or null")
    measurement_class = row.get("measurement_class")
    if measurement_class not in MEASUREMENT_CLASSES:
        raise ExposureGateError("measurement_class is not in the allowed vocabulary")
    return {
        "schema": "mva-track2-exposure-profile/v1",
        "probe_id": probe,
        "nominal_uM": nominal,
        "unbound_medium_uM": unbound,
        "intracellular_parent": intracellular,
        "time_hours": duration,
        "pulse_vs_constant": pattern,
        "washout": washout,
        "measurement_class": measurement_class,
    }


def make_exposure_profile_id(row: Mapping[str, Any], probe_id: object) -> str:
    """Digest semantic profile fields rather than raw JSON bytes."""

    payload = _profile_payload(row, probe_id)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return "profile-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def exposure_execution_fingerprint(
    row: Mapping[str, Any],
    probe_id: object,
) -> str:
    """Canonical fingerprint for one measured execution and its declared supports."""

    profile_id = _identifier(row.get("exposure_profile_id"), "exposure_profile_id")
    measurement_execution = _identifier(
        row.get("measurement_execution_id"), "measurement_execution_id"
    )
    supports = _identifier_list(
        row.get("supports_functional_execution_ids", []),
        "supports_functional_execution_ids",
        allow_empty=True,
    )
    run_ids = _identifier_list(
        row.get("functional_assay_run_ids", []),
        "functional_assay_run_ids",
        allow_empty=True,
    )
    batch_value = row.get("culture_batch_id")
    batch_id = None if batch_value is None else _identifier(batch_value, "culture_batch_id")
    relation_value = row.get("sample_relation")
    if relation_value is None:
        relation = None
    elif relation_value not in SAMPLE_RELATIONS:
        raise ExposureGateError("sample_relation is not in the allowed vocabulary")
    else:
        relation = str(relation_value)
    started_value = row.get("exposure_started_at")
    sampled_value = row.get("measurement_sampled_at")
    started = None if started_value is None else _utc(started_value, "exposure_started_at")
    sampled = None if sampled_value is None else _utc(sampled_value, "measurement_sampled_at")
    if supports and (
        batch_id is None
        or relation is None
        or started is None
        or sampled is None
        or not run_ids
    ):
        raise ExposureGateError("linked exposure execution is missing context")
    if not supports and (run_ids or relation is not None):
        raise ExposureGateError(
            "unlinked exposure execution cannot declare functional assay context"
        )
    if started is not None and sampled is not None and sampled < started:
        raise ExposureGateError("measurement cannot precede exposure")
    optional_ids = {}
    for field in ("exposure_measurement_plate_id", "probe_lot_id"):
        value = row.get(field)
        optional_ids[field] = None if value is None else _identifier(value, field)
    payload = {
        "schema": BINDING_SCHEMA,
        "profile": _profile_payload(row, probe_id),
        "exposure_profile_id": profile_id,
        "measurement_execution_id": measurement_execution,
        "supports_functional_execution_ids": supports,
        "functional_assay_run_ids": run_ids,
        "culture_batch_id": batch_id,
        "sample_relation": relation,
        "exposure_started_at": None if started is None else started.isoformat(),
        "measurement_sampled_at": None if sampled is None else sampled.isoformat(),
        # Declared selection history binds into the fingerprint: flipping
        # a clearance claim after the fact changes the identity of the
        # record and fails binding rather than silently upgrading a row.
        "selection_agent": row.get("selection_agent"),
        "selection_agent_cleared": row.get("selection_agent_cleared"),
        "selection_clearance_method": row.get("selection_clearance_method"),
        **optional_ids,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _number(value: object, field: str, *, allow_null: bool = False) -> float | None:
    if value is None:
        if allow_null:
            return None
        raise ExposureGateError(f"{field} is required")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExposureGateError(f"{field} must be a number")
    if not math.isfinite(value):
        raise ExposureGateError(f"{field} must be finite")
    if value < 0:
        raise ExposureGateError(f"{field} must be non-negative")
    return float(value)


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExposureGateError(f"{field} must be a positive integer")
    return value


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _realized_allocation_tuple(row: Mapping[str, Any]) -> dict[str, Any] | None:
    fields = (
        "allocation_block_id",
        "functional_assay_plate_id",
        "plate_row",
        "plate_column",
        "dosing_order",
        "acquisition_order",
    )
    if any(row.get(field) is None for field in fields):
        return None
    return {
        "allocation_block_id": _allocation_context_identifier(
            row.get("allocation_block_id"), "allocation_block_id"
        ),
        "functional_assay_plate_id": _allocation_context_identifier(
            row.get("functional_assay_plate_id"), "functional_assay_plate_id"
        ),
        "plate_row": _positive_int(row.get("plate_row"), "plate_row"),
        "plate_column": _positive_int(row.get("plate_column"), "plate_column"),
        "dosing_order": _positive_int(row.get("dosing_order"), "dosing_order"),
        "acquisition_order": _positive_int(
            row.get("acquisition_order"), "acquisition_order"
        ),
    }


def _time_profile(
    row: Mapping[str, Any],
) -> tuple[float | None, str, bool | None, str]:
    """Classify whether one scalar exposure row defines an advancing window.

    The v1 community table has no concentration-time series. A pulse row is
    therefore supportive only: one measured point during a pulse cannot stand
    in for the post-washout profile. A positive-duration constant row can
    represent the bounded culture window used by this software contract.
    """

    time_hours = _number(row.get("time_hours"), "time_hours", allow_null=True)
    profile_value = row.get("pulse_vs_constant")
    profile = profile_value if isinstance(profile_value, str) else "unlabeled"
    washout_value = row.get("washout")
    washout = washout_value if isinstance(washout_value, bool) else None
    if time_hours is None:
        reason = "time_hours_missing"
    elif time_hours <= 0:
        reason = "time_hours_nonpositive"
    elif profile not in TIME_PROFILE_CLASSES:
        reason = "time_profile_invalid"
    elif washout_value is not None and washout is None:
        reason = "washout_invalid"
    elif profile == "pulse" and washout is None:
        reason = "washout_missing"
    elif profile == "pulse" and not washout:
        reason = "pulse_without_washout"
    elif profile == "pulse":
        reason = "pulse_support_only"
    elif time_hours < MIN_CONSTANT_WINDOW_HOURS:
        # A sub-window "constant" exposure is physically indistinguishable
        # from a measurement taken at the instant dosing began — it cannot
        # represent the bounded culture window the contract requires.
        reason = "time_hours_below_window"
    else:
        reason = "constant_window"
    return time_hours, profile, washout, reason


def _classify(nominal: float, unbound: float | None, intracellular: float | None) -> str:
    if nominal <= 0:
        return "not_assessable"
    values = [nominal]
    if unbound is not None:
        values.append(unbound)
    if intracellular is not None:
        values.append(intracellular)
    if any(item >= NONTRANSLATIONAL_UM for item in values):
        return "nontranslational_high"
    if (
        unbound is None
        or intracellular is None
        or unbound <= 0
        or intracellular <= 0
    ):
        return "not_assessable"
    peak = max(nominal, unbound, intracellular)
    if peak <= ADVANCE_MAX_UM:
        return "leq_2um"
    if peak <= EXPLORATORY_MAX_UM:
        return "exploratory_5um"
    return "nontranslational_high"


def assess_exposure_gate(table: Mapping[str, Any]) -> dict[str, Any]:
    """Pass only when a complete conservative-window row exists."""

    if not isinstance(table, Mapping):
        raise ExposureGateError("exposure table must be an object")
    if table.get("schema") != TABLE_SCHEMA:
        raise ExposureGateError("exposure-gate accepts the measured-exposure table only")
    rows = table.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ExposureGateError("exposure table has no rows")
    if len(rows) > 10_000:
        raise ExposureGateError("exposure table exceeds the row ceiling")
    columns = table.get("columns")
    if columns is not None:
        if (
            isinstance(columns, (str, bytes))
            or not isinstance(columns, Sequence)
            or not columns
            or any(not isinstance(name, str) for name in columns)
        ):
            raise ExposureGateError(
                "exposure table columns must be a non-empty sequence of strings"
            )
        missing = [name for name in REQUIRED_COLUMNS if name not in columns]
        if missing:
            raise ExposureGateError("exposure table is missing required columns")

    classified = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ExposureGateError("exposure row must be an object")
        nominal = _number(row.get("nominal_uM"), "nominal_uM")
        unbound = _number(
            row.get("unbound_medium_uM"), "unbound_medium_uM", allow_null=True
        )
        intracellular = _number(
            row.get("intracellular_parent"), "intracellular_parent", allow_null=True
        )
        measurement_class = row.get("measurement_class", "unlabeled")
        if measurement_class not in MEASUREMENT_CLASSES:
            raise ExposureGateError(
                "measurement_class is not in the allowed vocabulary"
            )
        selection_agent = row.get("selection_agent")
        if selection_agent is None:
            selection_agent = "unlabeled"
        elif selection_agent not in SELECTION_AGENT_CLASSES:
            raise ExposureGateError(
                "selection_agent is not in the allowed vocabulary"
            )
        selection_cleared = row.get("selection_agent_cleared")
        if selection_cleared is not None and not isinstance(selection_cleared, bool):
            raise ExposureGateError(
                "selection_agent_cleared must be a boolean or null"
            )
        clearance_method = row.get("selection_clearance_method")
        if clearance_method is not None and (
            clearance_method not in SELECTION_CLEARANCE_METHODS
        ):
            raise ExposureGateError(
                "selection_clearance_method is not in the allowed vocabulary"
            )
        culture_batch = row.get("culture_batch_id")
        if culture_batch is not None:
            culture_batch = _identifier(culture_batch, "culture_batch_id")
        concentration_class = _classify(nominal, unbound, intracellular)
        try:
            time_hours, time_profile, washout, time_profile_reason = _time_profile(row)
        except ExposureGateError:
            if concentration_class != "nontranslational_high":
                raise
            time_hours = None
            time_profile = "unlabeled"
            washout = None
            time_profile_reason = "time_profile_invalid"
        row_class = concentration_class
        selection_reason = None
        if row_class == "leq_2um" and measurement_class != "culture_measured":
            row_class = "not_assessable"
        elif row_class == "leq_2um" and time_profile_reason != "constant_window":
            row_class = "not_assessable"
        elif row_class == "leq_2um":
            # A clone-selection antibiotic left in the assay window is a
            # direct confound: aminoglycosides (G418/neomycin) are the
            # canonical readthrough agents and can themselves induce the
            # claimed suppression phenotype; other selection agents still
            # stress cells. An undocumented agent cannot be excluded, and
            # a clearance claim without a declared method is a checkbox,
            # not evidence.
            verified_clearance = (
                selection_cleared is True
                and clearance_method in SELECTION_CLEARANCE_METHODS
            )
            if selection_agent == "unlabeled":
                row_class = "not_assessable"
                selection_reason = "selection_agent_unlabeled"
            elif selection_agent in {"aminoglycoside", "non_aminoglycoside"} and (
                selection_cleared is True
                and clearance_method not in SELECTION_CLEARANCE_METHODS
            ):
                row_class = (
                    "aminoglycoside_carryover"
                    if selection_agent == "aminoglycoside"
                    else "not_assessable"
                )
                selection_reason = "selection_clearance_method_unverified"
            elif selection_agent == "aminoglycoside" and not verified_clearance:
                row_class = "aminoglycoside_carryover"
                selection_reason = "aminoglycoside_carryover"
            elif (
                selection_agent == "non_aminoglycoside"
                and not verified_clearance
            ):
                row_class = "not_assessable"
                selection_reason = "selection_agent_carryover"
        classified.append(
            {
                "index": index,
                "nominal_uM": nominal,
                "unbound_medium_uM": unbound,
                "intracellular_parent": intracellular,
                "measurement_class": measurement_class,
                "time_hours": time_hours,
                "pulse_vs_constant": time_profile,
                "washout": washout,
                "time_profile_reason": time_profile_reason,
                "time_profile_assessable": time_profile_reason == "constant_window",
                "concentration_class": concentration_class,
                "selection_agent": selection_agent,
                "selection_agent_cleared": selection_cleared,
                "selection_clearance_method": clearance_method,
                "culture_batch_id": culture_batch,
                "selection_reason": selection_reason,
                "row_class": row_class,
            }
        )

    # Selection-agent history is a property of the culture, not of a row:
    # every row linked to the same culture_batch_id shares one medium
    # history. Conflicting declarations inside a batch mean the history
    # is unreliable, and a batch is cleared only when every member row
    # agrees it was cleared with a declared method — a single uncleared
    # sibling taints the batch. Only otherwise-qualifying rows are
    # downgraded; rows already failing on other grounds keep their own
    # reason.
    batches: dict[str, list[dict[str, Any]]] = {}
    for item in classified:
        batch_id = item["culture_batch_id"]
        if batch_id is not None:
            batches.setdefault(batch_id, []).append(item)
    if batches:
        # Batch declaration is all-or-none: a table that names the culture
        # for some rows but leaves others unlabeled is hiding structure —
        # every measured row came from a culture, and an unlabeled sibling
        # could otherwise opt out of batch consistency entirely.
        partial = [
            item for item in classified if item["culture_batch_id"] is None
        ]
        if partial:
            for item in classified:
                if item["row_class"] == "leq_2um":
                    item["row_class"] = "not_assessable"
                    item["selection_reason"] = "culture_batch_partially_declared"
    for batch_rows in batches.values():
        agents = {item["selection_agent"] for item in batch_rows}
        # A row that declares no clearance asserts no method — nulls are
        # absences, not conflicting claims.
        methods = {
            item["selection_clearance_method"]
            for item in batch_rows
            if item["selection_clearance_method"] is not None
        }
        cleared_all = all(
            item["selection_agent_cleared"] is True
            and item["selection_clearance_method"] in SELECTION_CLEARANCE_METHODS
            for item in batch_rows
        )
        if len(agents) > 1 or len(methods) > 1:
            for item in batch_rows:
                if item["row_class"] == "leq_2um":
                    item["row_class"] = "not_assessable"
                    item["selection_reason"] = (
                        "selection_agent_inconsistent_within_batch"
                    )
            continue
        agent = next(iter(agents))
        if agent == "aminoglycoside" and not cleared_all:
            for item in batch_rows:
                if item["row_class"] == "leq_2um":
                    item["row_class"] = "aminoglycoside_carryover"
                    item["selection_reason"] = "aminoglycoside_carryover"
        elif agent == "non_aminoglycoside" and not cleared_all:
            for item in batch_rows:
                if item["row_class"] == "leq_2um":
                    item["row_class"] = "not_assessable"
                    item["selection_reason"] = "selection_agent_carryover"

    classes = {item["row_class"] for item in classified}
    zero_cell = any(
        item["unbound_medium_uM"] is not None
        and item["intracellular_parent"] is not None
        and (item["unbound_medium_uM"] <= 0 or item["intracellular_parent"] <= 0)
        for item in classified
    )
    if "nontranslational_high" in classes:
        overall = "stop"
        reason = "nontranslational_high"
    elif "leq_2um" in classes and zero_cell:
        # A measured row reporting zero intracellular or zero unbound-medium
        # exposure cannot coexist with a qualifying window row — the
        # measurements contradict each other and neither is certified.
        overall = "not_assessable"
        reason = "exposure_discordant"
    elif "leq_2um" in classes:
        overall = "pass"
        reason = "conservative_window_measured"
    else:
        overall = "not_assessable"
        if all(
            item["unbound_medium_uM"] is None or item["intracellular_parent"] is None
            for item in classified
        ):
            reason = "nominal_only"
        elif zero_cell:
            reason = "zero_cell_exposure"
        elif any(
            item["selection_reason"] == "aminoglycoside_carryover"
            for item in classified
        ):
            reason = "aminoglycoside_carryover"
        elif any(
            item["selection_reason"] == "culture_batch_partially_declared"
            for item in classified
        ):
            # A partially batched table defeats the per-batch consistency
            # checks entirely — the coverage defect outranks per-batch
            # content findings.
            reason = "culture_batch_partially_declared"
        elif any(
            item["selection_reason"] == "selection_agent_carryover"
            for item in classified
        ):
            reason = "selection_agent_carryover"
        elif any(
            item["selection_reason"]
            == "selection_agent_inconsistent_within_batch"
            for item in classified
        ):
            reason = "selection_agent_inconsistent_within_batch"
        elif any(
            item["selection_reason"] == "selection_clearance_method_unverified"
            for item in classified
        ):
            reason = "selection_clearance_method_unverified"
        elif any(
            item["selection_reason"] == "selection_agent_unlabeled"
            for item in classified
        ):
            reason = "selection_agent_unlabeled"
        elif any(item["measurement_class"] != "culture_measured" for item in classified):
            reason = "label_estimate_not_culture"
        elif any(item["time_profile_reason"] == "time_hours_missing" for item in classified):
            reason = "time_hours_missing"
        elif any(item["time_profile_reason"] == "time_hours_nonpositive" for item in classified):
            reason = "time_hours_nonpositive"
        elif all(
            item["concentration_class"] != "leq_2um"
            or item["time_profile_reason"] == "pulse_support_only"
            for item in classified
        ) and any(
            item["concentration_class"] == "leq_2um"
            and item["time_profile_reason"] == "pulse_support_only"
            for item in classified
        ):
            reason = "pulse_only_not_advancing"
        elif any(item["time_profile_reason"] != "constant_window" for item in classified):
            reason = "time_profile_not_advancing"
        else:
            reason = "no_conservative_window_row"
    if overall == "pass":
        vehicle_controls = table.get("vehicle_controls")
        if not isinstance(vehicle_controls, list) or not vehicle_controls:
            # A pass without a recorded vehicle baseline cannot distinguish
            # rescue from drift or cytotoxicity — it is not assessable.
            overall = "not_assessable"
            reason = "vehicle_baseline_missing"
        try:
            allocation = assess_preexposure_allocation(table)
        except ArmAllocationError as exc:
            raise ExposureGateError("preexposure allocation is malformed") from exc
        if allocation["status"] != "pass" or allocation.get(
            "allocation_verified"
        ) is not True:
            # A no-op pass (no planned functional executions) cannot back an
            # exposure gate pass — the treatment rows must be allocated and
            # verified, or the gate is not assessable.
            overall = "not_assessable"
            reason = (
                "allocation_not_verified"
                if allocation["status"] == "pass"
                else str(allocation["reason"])
            )
    elif overall == "stop":
        allocation = skipped_preexposure_allocation(
            "nontranslational_high_precedence"
        )
    else:
        allocation = skipped_preexposure_allocation(
            "exposure_concentration_not_passed"
        )
    result = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "advance_max_uM": ADVANCE_MAX_UM,
        "exploratory_max_uM": EXPLORATORY_MAX_UM,
        "nontranslational_uM": NONTRANSLATIONAL_UM,
        "status": overall,
        "program_effect": (
            "pass" if overall == "pass" else ("stop" if overall == "stop" else "hold")
        ),
        "exposure_gate_passed": overall == "pass",
        "advancement_blocked": overall != "pass",
        "reason": reason,
        "preexposure_allocation": allocation,
        "n_rows": len(classified),
        "rows": classified,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def _binding_result(
    *,
    status: str,
    reason: str,
    n_treatment_rows: int,
    n_linked_rows: int,
    linked_assay_fingerprint: str | None = None,
    execution_fingerprints: Sequence[str] = (),
) -> dict[str, Any]:
    passed = status == "pass"
    result = {
        "schema": BINDING_SCHEMA,
        "synthetic_only": True,
        "claim_boundary": BINDING_CLAIM_BOUNDARY,
        "status": status,
        "program_effect": "pass" if passed else "hold",
        "reason": reason,
        "exposure_execution_linked": passed,
        "n_treatment_rows": n_treatment_rows,
        "n_linked_rows": n_linked_rows,
        "linked_assay_fingerprint": linked_assay_fingerprint,
        "exposure_execution_fingerprints": sorted(execution_fingerprints),
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def assess_exposure_execution_binding(
    table: Mapping[str, Any],
    lineage: Mapping[str, Any],
    assay_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Require every treatment result to resolve to one eligible exposure execution.

    This is intentionally evaluated with count identity rather than the earlier
    exposure gate. Realized treatment rows are required, so crediting this as a
    pre-imaging exposure kill would overstate the saved lab spend.
    """

    if not isinstance(table, Mapping) or table.get("schema") != TABLE_SCHEMA:
        raise ExposureGateError("binding accepts the measured-exposure table only")
    if not isinstance(lineage, Mapping) or lineage.get("schema") != LINEAGE_COUNTS_SCHEMA:
        raise ExposureGateError("binding accepts lineage-count exports only")
    if not isinstance(assay_plan, Mapping) or assay_plan.get("schema") != ASSAY_PLAN_SCHEMA:
        raise ExposureGateError("binding accepts the community assay plan only")
    exposure = assess_exposure_gate(table)
    runs = lineage.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ExposureGateError("lineage-count export has no runs")
    treatment_rows = [
        row for row in runs if isinstance(row, Mapping) and row.get("arm") == "treatment"
    ]
    if not treatment_rows:
        raise ExposureGateError("lineage-count export has no treatment rows")
    if exposure.get("status") != "pass":
        return _binding_result(
            status="hold",
            reason="exposure_not_passed",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )

    study_value = lineage.get("study_id")
    if study_value is None:
        return _binding_result(
            status="hold",
            reason="exposure_assay_context_missing",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )
    study_id = _identifier(study_value, "study_id")

    endpoint = assay_plan.get("endpoint_class")
    success_rule = assay_plan.get("success_rule")
    declared_endpoint = table.get("endpoint_class")
    declared_success_rule = table.get("success_rule")
    if not all(
        isinstance(value, str) and value
        for value in (endpoint, success_rule, declared_endpoint, declared_success_rule)
    ):
        return _binding_result(
            status="hold",
            reason="exposure_assay_context_missing",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )
    if endpoint != declared_endpoint or success_rule != declared_success_rule:
        return _binding_result(
            status="hold",
            reason="exposure_assay_context_mismatch",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )

    allocation_result = exposure.get("preexposure_allocation")
    raw_allocation = table.get("preexposure_allocation")
    if (
        not isinstance(allocation_result, Mapping)
        or allocation_result.get("allocation_verified") is not True
        or not isinstance(raw_allocation, Mapping)
    ):
        return _binding_result(
            status="hold",
            reason="exposure_assay_context_missing",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )
    allocation_id = allocation_result.get("allocation_id")
    lineage_allocation_id = lineage.get("allocation_id")
    if (
        not isinstance(allocation_id, str)
        or lineage_allocation_id != allocation_id
        or raw_allocation.get("study_id") != study_id
        or raw_allocation.get("assay_plan_sha256") != _canonical_sha256(assay_plan)
    ):
        return _binding_result(
            status="hold",
            reason="exposure_assay_context_mismatch",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )
    allocation_assignments = allocation_result.get("assignments")
    if not isinstance(allocation_assignments, list) or not allocation_assignments:
        return _binding_result(
            status="hold",
            reason="exposure_assay_context_missing",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )
    allocation_index = {
        str(item.get("functional_execution_id")): item
        for item in allocation_assignments
        if isinstance(item, Mapping)
    }
    if len(allocation_index) != len(allocation_assignments):
        raise ExposureGateError("allocation assignments cannot be indexed")

    raw_rows = table.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) != len(exposure["rows"]):
        raise ExposureGateError("measured-exposure rows cannot be aligned")
    probe_id = table.get("probe_id")
    probe = _identifier(probe_id, "probe_id")
    support_index: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    measurement_ids: set[str] = set()
    measurement_rows: dict[str, Mapping[str, Any]] = {}
    measurement_fingerprints: dict[str, str] = {}
    profile_mismatch = False
    for raw, classified in zip(raw_rows, exposure["rows"], strict=True):
        if not isinstance(raw, Mapping):
            raise ExposureGateError("exposure row must be an object")
        profile_id = _identifier(
            raw.get("exposure_profile_id"), "exposure_profile_id"
        )
        expected_profile = make_exposure_profile_id(raw, probe)
        if profile_id != expected_profile:
            profile_mismatch = True
        measurement_id = _identifier(
            raw.get("measurement_execution_id"), "measurement_execution_id"
        )
        if measurement_id in measurement_ids:
            raise ExposureGateError("duplicate measurement_execution_id")
        measurement_ids.add(measurement_id)
        measurement_rows[measurement_id] = raw
        measurement_fingerprints[measurement_id] = exposure_execution_fingerprint(
            raw, probe
        )
        supports = _identifier_list(
            raw.get("supports_functional_execution_ids", []),
            "supports_functional_execution_ids",
            allow_empty=True,
        )
        for functional_id in supports:
            if functional_id in support_index:
                raise ExposureGateError("functional execution has multiple exposure supports")
            support_index[functional_id] = (raw, classified)
    if profile_mismatch:
        return _binding_result(
            status="hold",
            reason="exposure_profile_mismatch",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
            execution_fingerprints=tuple(measurement_fingerprints.values()),
        )

    raw_controls = table.get("vehicle_controls")
    if not isinstance(raw_controls, list) or not raw_controls:
        return _binding_result(
            status="hold",
            reason="exposure_execution_missing",
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=0,
        )
    control_ids: set[str] = set()
    vehicle_support_index: dict[
        str, tuple[Mapping[str, Any], Mapping[str, Any], str]
    ] = {}
    control_records_by_id: dict[str, Mapping[str, Any]] = {}
    for raw_control in raw_controls:
        if not isinstance(raw_control, Mapping):
            raise ExposureGateError("vehicle control record must be an object")
        required_control = (
            raw_control.get("control_execution_id"),
            raw_control.get("exposure_profile_id"),
            raw_control.get("control_probe_id"),
            raw_control.get("culture_batch_id"),
            raw_control.get("exposure_started_at"),
            raw_control.get("endpoint_recorded_at"),
        )
        if any(value is None for value in required_control):
            return _binding_result(
                status="hold",
                reason="exposure_execution_missing",
                n_treatment_rows=len(treatment_rows),
                n_linked_rows=0,
            )
        control_id = _identifier(required_control[0], "control_execution_id")
        if control_id in control_ids:
            raise ExposureGateError("duplicate control_execution_id")
        control_ids.add(control_id)
        control_profile = _identifier(
            required_control[1], "exposure_profile_id"
        )
        control_probe = _identifier(required_control[2], "control_probe_id")
        control_batch = _identifier(required_control[3], "culture_batch_id")
        control_started = _utc(required_control[4], "exposure_started_at")
        control_endpoint = _utc(required_control[5], "endpoint_recorded_at")
        if control_endpoint <= control_started:
            return _binding_result(
                status="hold",
                reason="exposure_timing_mismatch",
                n_treatment_rows=len(treatment_rows),
                n_linked_rows=0,
            )
        control_supports = _identifier_list(
            raw_control.get("supports_functional_execution_ids", []),
            "supports_functional_execution_ids",
        )
        control_runs = _identifier_list(
            raw_control.get("functional_assay_run_ids", []),
            "functional_assay_run_ids",
        )
        normalized_control = {
            "control_execution_id": control_id,
            "exposure_profile_id": control_profile,
            "control_probe_id": control_probe,
            "culture_batch_id": control_batch,
            "supports_functional_execution_ids": control_supports,
            "functional_assay_run_ids": control_runs,
            "exposure_started_at": control_started.isoformat(),
            "endpoint_recorded_at": control_endpoint.isoformat(),
        }
        control_records_by_id[control_id] = normalized_control
        control_encoded = json.dumps(
            normalized_control,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
        control_fingerprint = hashlib.sha256(
            control_encoded.encode("utf-8")
        ).hexdigest()
        for functional_id in control_supports:
            if functional_id in vehicle_support_index:
                raise ExposureGateError(
                    "vehicle functional execution has multiple control supports"
                )
            vehicle_support_index[functional_id] = (
                raw_control,
                normalized_control,
                control_fingerprint,
            )

    vehicle_index: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for raw in runs:
        if not isinstance(raw, Mapping) or raw.get("arm") != "vehicle":
            continue
        key = (
            str(raw.get("edit_event_id")),
            str(raw.get("clone_id")),
            str(raw.get("run_id")),
        )
        if key in vehicle_index:
            raise ExposureGateError("lineage has duplicate vehicle rows")
        vehicle_index[key] = raw

    linked_payload = []
    missing = False
    mismatch = False
    unqualified = False
    timing_mismatch = False
    treatment_functional_ids: set[str] = set()
    treatment_profile_ids: set[str] = set()
    observed_vehicle_ids: set[str] = set()
    selected_measurement_ids: set[str] = set()
    selected_control_fingerprints: set[str] = set()
    observed_measurement_runs: dict[str, set[str]] = {}
    observed_control_runs: dict[str, set[str]] = {}
    for raw in treatment_rows:
        functional_value = raw.get("functional_execution_id")
        support_record_value = raw.get("exposure_support_record_id")
        profile_value = raw.get("exposure_profile_id")
        probe_value = raw.get("exposure_probe_id")
        batch_value = raw.get("batch_id")
        started_value = raw.get("exposure_started_at")
        endpoint_value = raw.get("endpoint_recorded_at")
        enrolled_value = raw.get("latest_enrolled_at")
        if any(
            value is None
            for value in (
                functional_value,
                support_record_value,
                profile_value,
                probe_value,
                batch_value,
                started_value,
                endpoint_value,
                enrolled_value,
            )
        ):
            missing = True
            continue
        functional_id = _identifier(functional_value, "functional_execution_id")
        support_record_id = _identifier(
            support_record_value, "exposure_support_record_id"
        )
        profile_id = _identifier(profile_value, "exposure_profile_id")
        row_probe = _identifier(probe_value, "exposure_probe_id")
        batch_id = _identifier(batch_value, "batch_id")
        run_id = _identifier(raw.get("run_id"), "run_id")
        started = _utc(started_value, "exposure_started_at")
        endpoint_recorded = _utc(endpoint_value, "endpoint_recorded_at")
        enrolled = _utc(enrolled_value, "latest_enrolled_at")
        if enrolled > started:
            timing_mismatch = True
        realized_allocation = _realized_allocation_tuple(raw)
        planned_allocation = allocation_index.get(functional_id)
        if realized_allocation is None:
            missing = True
        elif planned_allocation is None:
            mismatch = True
        elif (
            planned_allocation.get("arm") != "treatment"
            or planned_allocation.get("edit_event_id") != raw.get("edit_event_id")
            or planned_allocation.get("clone_id") != raw.get("clone_id")
            or planned_allocation.get("culture_batch_id") != batch_id
            or planned_allocation.get("functional_assay_run_id") != run_id
            or any(
                planned_allocation.get(field) != value
                for field, value in realized_allocation.items()
            )
        ):
            mismatch = True
        if functional_id in treatment_functional_ids:
            mismatch = True
            continue
        treatment_functional_ids.add(functional_id)
        treatment_profile_ids.add(profile_id)
        supported = support_index.get(functional_id)
        if supported is None:
            mismatch = True
            continue
        exposure_row, classified = supported
        measurement_id = _identifier(
            exposure_row.get("measurement_execution_id"),
            "measurement_execution_id",
        )
        selected_measurement_ids.add(measurement_id)
        observed_measurement_runs.setdefault(measurement_id, set()).add(run_id)
        if classified.get("row_class") != "leq_2um":
            unqualified = True
            continue
        support_runs = _identifier_list(
            exposure_row.get("functional_assay_run_ids", []),
            "functional_assay_run_ids",
            allow_empty=True,
        )
        exposure_batch = exposure_row.get("culture_batch_id")
        exposure_started = exposure_row.get("exposure_started_at")
        sampled_at = exposure_row.get("measurement_sampled_at")
        if any(value is None for value in (exposure_batch, exposure_started, sampled_at)):
            missing = True
            continue
        sampled = _utc(sampled_at, "measurement_sampled_at")
        measured_started = _utc(exposure_started, "exposure_started_at")
        duration = _number(exposure_row.get("time_hours"), "time_hours")
        try:
            expected_sample = measured_started + timedelta(hours=float(duration))
        except (OverflowError, ValueError) as exc:
            raise ExposureGateError(
                "time_hours cannot be converted to an exposure duration"
            ) from exc
        if sampled != expected_sample or sampled > endpoint_recorded:
            timing_mismatch = True
        if (
            profile_id != exposure_row.get("exposure_profile_id")
            or support_record_id != measurement_id
            or row_probe != probe
            or batch_id != exposure_batch
            or run_id not in support_runs
            or started != measured_started
        ):
            mismatch = True
        key = (
            str(raw.get("edit_event_id")),
            str(raw.get("clone_id")),
            run_id,
        )
        vehicle = vehicle_index.get(key)
        if vehicle is None:
            mismatch = True
        else:
            vehicle_context = (
                vehicle.get("functional_execution_id"),
                vehicle.get("exposure_support_record_id"),
                vehicle.get("exposure_profile_id"),
                vehicle.get("exposure_probe_id"),
                vehicle.get("batch_id"),
                vehicle.get("exposure_started_at"),
                vehicle.get("endpoint_recorded_at"),
                vehicle.get("latest_enrolled_at"),
            )
            if any(value is None for value in vehicle_context):
                missing = True
            else:
                vehicle_functional = _identifier(
                    vehicle_context[0], "functional_execution_id"
                )
                vehicle_support_record = _identifier(
                    vehicle_context[1], "exposure_support_record_id"
                )
                vehicle_profile = _identifier(
                    vehicle_context[2], "exposure_profile_id"
                )
                vehicle_probe = _identifier(vehicle_context[3], "exposure_probe_id")
                vehicle_batch = _identifier(vehicle_context[4], "batch_id")
                vehicle_started = _utc(vehicle_context[5], "exposure_started_at")
                vehicle_endpoint = _utc(vehicle_context[6], "endpoint_recorded_at")
                vehicle_enrolled = _utc(vehicle_context[7], "latest_enrolled_at")
                if vehicle_enrolled > vehicle_started:
                    timing_mismatch = True
                realized_vehicle_allocation = _realized_allocation_tuple(vehicle)
                planned_vehicle_allocation = allocation_index.get(vehicle_functional)
                if realized_vehicle_allocation is None:
                    missing = True
                elif planned_vehicle_allocation is None:
                    mismatch = True
                elif (
                    planned_vehicle_allocation.get("arm") != "vehicle"
                    or planned_vehicle_allocation.get("edit_event_id")
                    != vehicle.get("edit_event_id")
                    or planned_vehicle_allocation.get("clone_id")
                    != vehicle.get("clone_id")
                    or planned_vehicle_allocation.get("culture_batch_id")
                    != vehicle_batch
                    or planned_vehicle_allocation.get("functional_assay_run_id")
                    != run_id
                    or any(
                        planned_vehicle_allocation.get(field) != value
                        for field, value in realized_vehicle_allocation.items()
                    )
                ):
                    mismatch = True
                control_support = vehicle_support_index.get(vehicle_functional)
                if vehicle_functional in observed_vehicle_ids:
                    mismatch = True
                observed_vehicle_ids.add(vehicle_functional)
                if control_support is None:
                    mismatch = True
                else:
                    _, normalized_control, control_fingerprint = control_support
                    selected_control_fingerprints.add(control_fingerprint)
                    control_id = str(normalized_control["control_execution_id"])
                    observed_control_runs.setdefault(control_id, set()).add(run_id)
                    if (
                        vehicle_support_record
                        != normalized_control["control_execution_id"]
                        or vehicle_profile
                        != normalized_control["exposure_profile_id"]
                        or vehicle_probe != normalized_control["control_probe_id"]
                        or vehicle_batch != normalized_control["culture_batch_id"]
                        or run_id
                        not in normalized_control["functional_assay_run_ids"]
                        or vehicle_started.isoformat()
                        != normalized_control["exposure_started_at"]
                        or vehicle_endpoint.isoformat()
                        != normalized_control["endpoint_recorded_at"]
                    ):
                        mismatch = True
                if (
                    vehicle_batch != batch_id
                    or vehicle_started != started
                    or vehicle_endpoint != endpoint_recorded
                    or vehicle_functional == functional_id
                    or vehicle_profile == profile_id
                    or vehicle_probe == row_probe
                ):
                    mismatch = True
        linked_payload.append(
            {
                "edit_event_id": str(raw.get("edit_event_id")),
                "clone_id": str(raw.get("clone_id")),
                "run_id": run_id,
                "batch_id": batch_id,
                "functional_execution_id": functional_id,
                "exposure_support_record_id": support_record_id,
                "exposure_profile_id": profile_id,
                "measurement_execution_id": measurement_id,
                "allocation_id": allocation_id,
                "realized_allocation": realized_allocation,
                "vehicle_functional_execution_id": (
                    None if vehicle is None else vehicle.get("functional_execution_id")
                ),
            }
        )

    lineage_vehicle_id_list: list[str] = []
    for vehicle in vehicle_index.values():
        value = vehicle.get("functional_execution_id")
        if value is None:
            missing = True
            continue
        lineage_vehicle_id_list.append(
            _identifier(value, "functional_execution_id")
        )
    lineage_vehicle_ids = set(lineage_vehicle_id_list)
    for measurement_id, observed_runs in observed_measurement_runs.items():
        declared_runs = set(
            _identifier_list(
                measurement_rows[measurement_id].get("functional_assay_run_ids", []),
                "functional_assay_run_ids",
            )
        )
        if declared_runs != observed_runs:
            mismatch = True
    for control_id, observed_runs in observed_control_runs.items():
        declared_runs = set(control_records_by_id[control_id]["functional_assay_run_ids"])
        if declared_runs != observed_runs:
            mismatch = True
    if (
        set(support_index) != treatment_functional_ids
        or set(vehicle_support_index) != observed_vehicle_ids
        or lineage_vehicle_ids != observed_vehicle_ids
        or len(lineage_vehicle_id_list) != len(lineage_vehicle_ids)
        or not treatment_functional_ids.isdisjoint(observed_vehicle_ids)
        or not measurement_ids.isdisjoint(control_ids)
        or len(treatment_profile_ids) != 1
    ):
        mismatch = True

    execution_fingerprints = tuple(
        measurement_fingerprints[item] for item in sorted(selected_measurement_ids)
    )
    n_linked = len(linked_payload)
    if missing:
        reason = "exposure_execution_missing"
    elif unqualified:
        reason = "linked_exposure_not_qualified"
    elif timing_mismatch:
        reason = "exposure_timing_mismatch"
    elif mismatch or n_linked != len(treatment_rows):
        reason = "exposure_assay_source_mismatch"
    else:
        reason = "exposure_execution_linked"
    if reason != "exposure_execution_linked":
        return _binding_result(
            status="hold",
            reason=reason,
            n_treatment_rows=len(treatment_rows),
            n_linked_rows=n_linked,
            execution_fingerprints=execution_fingerprints,
        )

    linked_record = {
        "schema": BINDING_SCHEMA,
        "study_id": study_id,
        "allocation_id": allocation_id,
        "endpoint_class": endpoint,
        "success_rule": success_rule,
        "treatment_rows": sorted(
            linked_payload,
            key=lambda item: (
                item["edit_event_id"],
                item["clone_id"],
                item["run_id"],
            ),
        ),
        "exposure_execution_fingerprints": sorted(execution_fingerprints),
        "vehicle_control_fingerprints": sorted(selected_control_fingerprints),
    }
    encoded = json.dumps(
        linked_record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    linked_fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return _binding_result(
        status="pass",
        reason=reason,
        n_treatment_rows=len(treatment_rows),
        n_linked_rows=n_linked,
        linked_assay_fingerprint=linked_fingerprint,
        execution_fingerprints=execution_fingerprints,
    )


__all__ = [
    "ADVANCE_MAX_UM",
    "BINDING_CLAIM_BOUNDARY",
    "BINDING_SCHEMA",
    "CLAIM_BOUNDARY",
    "EXPLORATORY_MAX_UM",
    "NONTRANSLATIONAL_UM",
    "SCHEMA",
    "SAMPLE_RELATIONS",
    "STATUSES",
    "TIME_PROFILE_CLASSES",
    "ExposureGateError",
    "assess_exposure_execution_binding",
    "assess_exposure_gate",
    "exposure_execution_fingerprint",
    "make_exposure_profile_id",
]
