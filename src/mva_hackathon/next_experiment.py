"""Dependency-order chooser for the next wet measurement.

Identity gates come first. A probe, imaging, or replication arm cannot be
the next spend while confirmation, phase, or transcript is still open.
This is not a numerical value-of-information model.  It does not choose a
medicine and does not raise a survival percentage.

The ``steps`` input is caller-declared: this module orders a supplied
step list; it cannot prove a step really passed. Authoritative step
status comes only from the canonical pipeline, which recomputes each
gate from its own bound artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mva_hackathon.provenance import receipt_sha256


SCHEMA = "mva-track2-next-experiment/v1"
WORKSHEET_SCHEMA = "mva.community-causal-chain-worksheet/v1"
IDENTITY_STEPS = ("confirmation", "phase", "transcript")
LATER_STEPS = (
    "hypomorph",
    "exposure",
    "count_identity",
    "assay_power",
    "clone_safety",
    "concordance",
    "replication",
)
STEP_ORDER = IDENTITY_STEPS + LATER_STEPS
NON_GATE_STEPS = (
    "evidence",
    "family",
    "structure_ranking",
    "hypothesis",
    "next_experiment",
)
KNOWN_STEP_NAMES = frozenset(STEP_ORDER) | frozenset(NON_GATE_STEPS)
PROBE_GATE_IDS = (
    "syn-gate-isogenic",
    "syn-gate-stability",
    "syn-gate-exposure",
    "syn-gate-segregation",
    "syn-gate-generation",
    "syn-gate-oncology",
    "syn-gate-replication",
)
IDENTITY_GATE_IDS = {
    "syn-gate-confirm": "confirmation",
    "syn-gate-phase": "phase",
    "syn-gate-transcript": "transcript",
}
STEP_TO_GATE = {
    "confirmation": "syn-gate-confirm",
    "phase": "syn-gate-phase",
    "transcript": "syn-gate-transcript",
    "hypomorph": "syn-gate-stability",
    "exposure": "syn-gate-exposure",
    "count_identity": "syn-gate-segregation",
    "assay_power": "syn-gate-generation",
    "clone_safety": "syn-gate-oncology",
    "concordance": "syn-gate-generation",
    "replication": "syn-gate-replication",
}
ALLOWED_GATE_IDS = frozenset(IDENTITY_GATE_IDS) | frozenset(PROBE_GATE_IDS)
CLAIM_BOUNDARY = (
    "Next-experiment software contract only; the chooser ranks the next wet "
    "measurement; it is not a treatment, dose, or survival percentage."
)


class NextExperimentError(ValueError):
    """Raised when a next-experiment worksheet is unusable."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NextExperimentError(f"{label} must be an object")
    return value


def _recommended_step(steps: Sequence[Mapping[str, Any]]) -> str:
    effects = {
        str(item.get("name")): item.get("program_effect")
        for item in steps
        if not item.get("skipped")
    }
    for name in IDENTITY_STEPS:
        if effects.get(name) != "pass":
            return name
    for name in LATER_STEPS:
        if effects.get(name) != "pass":
            return name
    return "replication"


def _declared_step(declared: str, recommended_step: str) -> str | None:
    if declared == "syn-gate-isogenic":
        return "hypomorph"
    if declared == "syn-gate-generation" and recommended_step in {
        "assay_power",
        "concordance",
    }:
        return recommended_step
    if declared in IDENTITY_GATE_IDS:
        return IDENTITY_GATE_IDS[declared]
    for step, gate_id in STEP_TO_GATE.items():
        if gate_id == declared:
            return step
    return None


def assess_next_experiment(
    worksheet: Mapping[str, Any],
    steps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return one next measurement. Probe-before-identity is a stop.

    An unrecognized declared gate cannot stand in for identity-first order.
    Declaring an already-passed earlier gate holds; it cannot stand in for
    the recommended next spend. The shared generation gate names assay
    power or concordance according to the recommended spend.
    """

    record = _mapping(worksheet, "causal-chain worksheet")
    if record.get("schema") != WORKSHEET_SCHEMA:
        raise NextExperimentError("next-experiment accepts the causal-chain worksheet only")
    declared = record.get("declared_next_gate_id")
    if not isinstance(declared, str) or not declared:
        raise NextExperimentError("declared_next_gate_id is required")
    # A worksheet must carry a bounded gate plan, and the declared next gate
    # must be part of it — a bare schema+declaration is not a chain.
    gates = record.get("gates")
    if not isinstance(gates, list) or not gates or len(gates) > 64:
        raise NextExperimentError(
            "worksheet must declare a bounded gate plan"
        )
    gate_ids: set[str] = set()
    orders: set[int] = set()
    for gate in gates:
        if not isinstance(gate, Mapping):
            raise NextExperimentError("worksheet gate entries must be objects")
        gate_id = gate.get("gate_id")
        if not isinstance(gate_id, str) or not gate_id or gate_id in gate_ids:
            raise NextExperimentError(
                "worksheet gate ids must be non-empty and unique"
            )
        # Every planned gate must name a real gate — a plan padded with
        # invented ids is not a coherent causal chain.
        if gate_id not in ALLOWED_GATE_IDS:
            raise NextExperimentError(
                "worksheet gate plan contains an unrecognized gate id"
            )
        gate_ids.add(gate_id)
        order = gate.get("order")
        if (
            not isinstance(order, int)
            or isinstance(order, bool)
            or order < 1
            or order in orders
        ):
            raise NextExperimentError(
                "worksheet gate orders must be positive and unique"
            )
        orders.add(order)
    # A recognized gate id that is absent from the worksheet's own plan is an
    # incoherent worksheet; an unrecognized id falls through to the existing
    # unknown_next_gate stop rather than a contract error.
    if declared in ALLOWED_GATE_IDS and declared not in gate_ids:
        raise NextExperimentError(
            "declared next gate is not in the worksheet gate plan"
        )
    seen_names: set[str] = set()
    for item in steps:
        if not isinstance(item, Mapping):
            raise NextExperimentError("steps must contain gate result objects")
        name = item.get("name")
        if not isinstance(name, str) or name not in KNOWN_STEP_NAMES:
            raise NextExperimentError("step name must be a canonical gate name")
        if name in seen_names:
            raise NextExperimentError("steps must not repeat a gate name")
        seen_names.add(name)
        if item.get("program_effect") not in {"pass", "hold", "stop"}:
            raise NextExperimentError(
                "program_effect must be one of pass, hold, or stop"
            )
        step_status = item.get("status")
        if (
            step_status in {"pass", "hold", "stop"}
            and step_status != item.get("program_effect")
        ):
            raise NextExperimentError(
                "status and program_effect cannot disagree on a step"
            )
        # A declared pass must be backed by a pass status — a caller cannot
        # mark a step passed while its status says not_assessable or is
        # absent; that would let a skipped prerequisite advance.
        if item.get("program_effect") == "pass" and step_status != "pass":
            raise NextExperimentError(
                "a pass program_effect requires a pass status"
            )
        if not isinstance(item.get("skipped", False), bool):
            raise NextExperimentError("skipped must be a boolean")
    recommended_step = _recommended_step(steps)
    recommended_gate = STEP_TO_GATE[recommended_step]
    effects = {
        str(item.get("name")): item.get("program_effect")
        for item in steps
        if not item.get("skipped")
    }
    identity_ok = all(effects.get(name) == "pass" for name in IDENTITY_STEPS)
    declared_step = _declared_step(declared, recommended_step)
    recommended_index = (
        STEP_ORDER.index(recommended_step) if recommended_step in STEP_ORDER else None
    )
    declared_index = (
        STEP_ORDER.index(declared_step) if declared_step in STEP_ORDER else None
    )
    skip_ahead = (
        recommended_index is not None
        and declared_index is not None
        and declared_index > recommended_index
    )
    stale_earlier = (
        recommended_index is not None
        and declared_index is not None
        and declared_index < recommended_index
    )
    if declared not in ALLOWED_GATE_IDS or declared_step is None:
        status = "stop"
        effect = "stop"
        reason = "unknown_next_gate"
    elif declared in PROBE_GATE_IDS and not identity_ok:
        status = "stop"
        effect = "stop"
        reason = "probe_before_identity"
    elif recommended_step in IDENTITY_STEPS and declared in PROBE_GATE_IDS:
        status = "stop"
        effect = "stop"
        reason = "probe_before_identity"
    elif skip_ahead and recommended_step in IDENTITY_STEPS and declared_step in IDENTITY_STEPS:
        status = "stop"
        effect = "stop"
        reason = "later_identity_before_confirmation"
    elif skip_ahead and recommended_step in ("hypomorph", "exposure"):
        status = "stop"
        effect = "stop"
        reason = "imaging_before_assay"
    elif skip_ahead:
        status = "stop"
        effect = "stop"
        reason = "skip_ahead_of_recommended"
    elif stale_earlier:
        status = "hold"
        effect = "hold"
        reason = "stale_declared_gate"
    else:
        status = "pass"
        effect = "pass"
        reason = "identity_first"
    owner = "clinical_genetics"
    handoff = None
    for gate in gates:
        if gate.get("gate_id") == recommended_gate:
            owner = str(gate.get("owner_lab") or owner)
            handoff = gate.get("handoff")
            break
    result = {
        "schema": SCHEMA,
        "gate": "next_experiment",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": effect,
        "advisory_only": True,
        "reason": reason,
        "recommended_step": recommended_step,
        "recommended_gate_id": recommended_gate,
        "declared_next_gate_id": declared,
        "owner_lab": owner,
        "handoff": handoff,
        "identity_complete": identity_ok,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


__all__ = [
    "ALLOWED_GATE_IDS",
    "CLAIM_BOUNDARY",
    "IDENTITY_GATE_IDS",
    "PROBE_GATE_IDS",
    "SCHEMA",
    "STEP_ORDER",
    "NextExperimentError",
    "assess_next_experiment",
]
