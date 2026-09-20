"""Stop-early runner for the identifier-free community toolkit.

Later gates are not evaluated after an earlier stop or hold. Synthetic
fixtures are not a child's result and are not efficacy evidence.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from mva_hackathon.assay_power import assess_assay_power
from mva_hackathon.clone_safety import assess_clone_safety
from mva_hackathon.exposure_gate import assess_exposure_gate
from mva_hackathon.hypothesis import assess_hypothesis_strength
from mva_hackathon.next_experiment import assess_next_experiment
from mva_hackathon.provenance import receipt_sha256
from mva_hackathon.program_gates import (
    CLAIM_BOUNDARY as GATE_CLAIM,
    assess_confirmation_gate,
    assess_count_table_identity,
    assess_endpoint_concordance,
    assess_evidence_links,
    assess_family_worksheet,
    assess_hypomorph_gate,
    assess_phase_gate,
    assess_replication_decision,
    assess_transcript_gate,
)
from mva_hackathon.structure_ranking import (
    CLAIM_BOUNDARY as RANKING_CLAIM,
    SCHEMA as RANKING_SCHEMA,
    StructureRankingError,
    assess_structure_ranking,
)


SCHEMA = "mva-track2-community-pipeline/v1"
CLAIM_BOUNDARY = (
    "Stop-early community pipeline only; synthetic fixtures are not a child's "
    "result; later gates do not run after an earlier fail; this is not "
    "efficacy evidence."
)
PHASE_FILE = "phase_record.synthetic.json"
CONFIRMATION_FILE = "confirmation_record.synthetic.json"
TRANSCRIPT_FILE = "transcript_record.synthetic.json"
SCORECARD_FILE = "allele_function_scorecard.synthetic.json"
EXPOSURE_FILE = "measured_exposure_table.synthetic.json"
LINEAGE_FILE = "lineage_count_table.synthetic.json"
BLINDED_FILE = "blinded_count_table.synthetic.json"
REPLICATION_FILE = "replication_decision.synthetic.json"
EVIDENCE_FILE = "observed_inferred_unknown.synthetic.json"
FAMILY_FILE = "family_plain_language.synthetic.md"
CAUSAL_FILE = "causal_chain_worksheet.synthetic.json"
POWER_FILE = "assay_power.synthetic.json"
RANKING_FILE = "structure_ranking.synthetic.json"
# A toolkit artifact far larger than any legitimate fixture is a
# denial-of-service surface, not evidence.
MAX_TOOLKIT_FILE_BYTES = 16 * 1024 * 1024


class CommunityPipelineError(ValueError):
    """Raised when the community toolkit layout is unusable."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CommunityPipelineError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CommunityPipelineError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise CommunityPipelineError(f"non-finite JSON number: {value}")
    return parsed


def _load_json(path: Path) -> dict[str, Any]:
    try:
        # Bounded read — a stat-then-read pair both races a file swap and
        # materializes an oversized file before the limit is applied.
        with path.open("rb") as handle:
            raw = handle.read(MAX_TOOLKIT_FILE_BYTES + 1)
        if len(raw) > MAX_TOOLKIT_FILE_BYTES:
            raise CommunityPipelineError(f"{path.name} exceeds the file size limit")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
            parse_float=_finite_float,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise CommunityPipelineError(f"cannot read {path.name}") from exc
    except RecursionError as exc:
        raise CommunityPipelineError(
            f"{path.name} JSON nesting exceeds the parser limit"
        ) from exc
    except CommunityPipelineError:
        raise
    except (ValueError, OverflowError, MemoryError) as exc:
        raise CommunityPipelineError(
            f"{path.name} contains an out-of-range value"
        ) from exc
    if not isinstance(payload, dict):
        raise CommunityPipelineError(f"{path.name} must be an object")
    return payload


def _effect(result: dict[str, Any]) -> str:
    effect = result.get("program_effect")
    status = result.get("status")
    if (
        effect in {"pass", "hold", "stop"}
        and status in {"pass", "hold", "stop"}
        and status != effect
    ):
        return "stop"
    if effect == "pass" and status != "pass":
        # A pass effect must dual-declare status="pass" — a missing status
        # cannot accompany a pass effect.
        return "stop"
    if effect == "advance":
        return "pass" if status == "pass" else "stop"
    if effect in {"pass", "hold", "stop"}:
        return str(effect)
    if status == "stop":
        return "stop"
    return "hold"


def _skipped(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "skipped": True,
        "status": "not_assessable",
        "program_effect": "hold",
        "reason": reason,
    }


def _ranking_result(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return assess_structure_ranking(payload)
    except StructureRankingError:
        return {
            "schema": RANKING_SCHEMA,
            "gate": "structure_ranking",
            "synthetic_only": True,
            "claim_boundary": RANKING_CLAIM,
            "status": "not_assessable",
            "program_effect": "hold",
            "reason": "ranking_table_unusable",
            "checkpoint_ready": False,
            "probe_eligible": False,
        }


def _step(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "skipped": False,
        "status": result.get("status"),
        "program_effect": _effect(result),
        "reason": result.get("reason"),
        "result": result,
    }


def run_community_pipeline(community: str | Path) -> dict[str, Any]:
    """Run toolkit gates in order and stop spending after the first fail."""

    root = Path(community)
    if not root.is_dir():
        raise CommunityPipelineError("community directory is required")
    required = (
        PHASE_FILE,
        CONFIRMATION_FILE,
        TRANSCRIPT_FILE,
        SCORECARD_FILE,
        EXPOSURE_FILE,
        LINEAGE_FILE,
        BLINDED_FILE,
        REPLICATION_FILE,
        EVIDENCE_FILE,
        FAMILY_FILE,
        CAUSAL_FILE,
        POWER_FILE,
        RANKING_FILE,
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise CommunityPipelineError("community toolkit is missing required files")

    steps: list[dict[str, Any]] = []
    blocked_by = None
    block_reason = None

    def continue_ok() -> bool:
        return blocked_by is None

    def block(step: dict[str, Any]) -> None:
        nonlocal blocked_by, block_reason
        if blocked_by is None and step["program_effect"] != "pass":
            blocked_by = step["name"]
            block_reason = step["reason"]

    evidence_payload = _load_json(root / EVIDENCE_FILE)
    evidence = assess_evidence_links(evidence_payload)
    step = _step("evidence", evidence)
    steps.append(step)
    block(step)

    family_path = root / FAMILY_FILE
    try:
        if family_path.stat().st_size > MAX_TOOLKIT_FILE_BYTES:
            raise CommunityPipelineError(
                f"{FAMILY_FILE} exceeds the file size limit"
            )
        family_text = family_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CommunityPipelineError(f"cannot read {FAMILY_FILE}") from exc
    family = assess_family_worksheet(family_text)
    step = _step("family", family)
    steps.append(step)
    block(step)

    if continue_ok():
        step = _step(
            "structure_ranking",
            _ranking_result(_load_json(root / RANKING_FILE)),
        )
    else:
        step = _skipped("structure_ranking", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        step = _step(
            "confirmation",
            assess_confirmation_gate(_load_json(root / CONFIRMATION_FILE)),
        )
    else:
        step = _skipped("confirmation", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        step = _step("phase", assess_phase_gate(_load_json(root / PHASE_FILE)))
    else:
        step = _skipped("phase", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        step = _step(
            "transcript",
            assess_transcript_gate(_load_json(root / TRANSCRIPT_FILE)),
        )
    else:
        step = _skipped("transcript", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        step = _step(
            "hypomorph", assess_hypomorph_gate(_load_json(root / SCORECARD_FILE))
        )
    else:
        step = _skipped("hypomorph", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        step = _step("exposure", assess_exposure_gate(_load_json(root / EXPOSURE_FILE)))
    else:
        step = _skipped("exposure", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    def _gate_payload(name: str) -> dict[str, Any]:
        item = next(row for row in steps if row["name"] == name)
        if item.get("skipped"):
            return {
                "gate": name,
                "status": "not_assessable",
                "program_effect": "hold",
            }
        payload = dict(item["result"])
        payload["program_effect"] = item["program_effect"]
        return payload

    lineage = None
    if continue_ok():
        lineage = _load_json(root / LINEAGE_FILE)
        step = _step(
            "count_identity",
            assess_count_table_identity(
                lineage,
                _load_json(root / BLINDED_FILE),
                _load_json(root / EXPOSURE_FILE),
                _load_json(root / POWER_FILE),
            ),
        )
    else:
        step = _skipped("count_identity", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        if lineage is None:
            lineage = _load_json(root / LINEAGE_FILE)
        step = _step(
            "assay_power",
            assess_assay_power(_load_json(root / POWER_FILE), lineage),
        )
    else:
        step = _skipped("assay_power", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        if lineage is None:
            lineage = _load_json(root / LINEAGE_FILE)
        step = _step("clone_safety", assess_clone_safety(lineage))
    else:
        step = _skipped("clone_safety", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    if continue_ok():
        if lineage is None:
            lineage = _load_json(root / LINEAGE_FILE)
        step = _step("concordance", assess_endpoint_concordance(lineage))
    else:
        step = _skipped("concordance", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    early_block = blocked_by in {"evidence", "family", "structure_ranking"}
    if not early_block:
        step = _step(
            "hypothesis",
            assess_hypothesis_strength(
                evidence_payload,
                confirmation=_gate_payload("confirmation"),
                phase=_gate_payload("phase"),
                transcript=_gate_payload("transcript"),
                hypomorph=_gate_payload("hypomorph"),
                exposure=_gate_payload("exposure"),
                concordance=_gate_payload("concordance"),
                clone_safety=_gate_payload("clone_safety"),
            ),
        )
        # The hypothesis receipt must be bound to the evidence table that was
        # actually loaded — a receipt farmed on different links is a stop.
        if step.get("result", {}).get("evidence_sha256") != receipt_sha256(
            evidence_payload
        ):
            step["program_effect"] = "stop"
            step["status"] = "stop"
            step["reason"] = "hypothesis_evidence_mismatch"
        steps.append(step)
        if step["program_effect"] == "stop":
            prior = next((row for row in steps if row["name"] == blocked_by), None)
            if blocked_by is None or prior is None or prior.get("program_effect") != "stop":
                blocked_by = step["name"]
                block_reason = step["reason"]
        else:
            block(step)
    else:
        step = _skipped("hypothesis", "earlier_gate_blocked")
        steps.append(step)
        block(step)

    if continue_ok():
        clone_result = next(item["result"] for item in steps if item["name"] == "clone_safety")
        exposure_result = next(item["result"] for item in steps if item["name"] == "exposure")
        concordance_result = next(
            item["result"] for item in steps if item["name"] == "concordance"
        )
        hypomorph_result = next(item["result"] for item in steps if item["name"] == "hypomorph")
        hypothesis_result = next(item["result"] for item in steps if item["name"] == "hypothesis")
        confirmation_result = next(item["result"] for item in steps if item["name"] == "confirmation")
        phase_result = next(item["result"] for item in steps if item["name"] == "phase")
        transcript_result = next(item["result"] for item in steps if item["name"] == "transcript")
        step = _step(
            "replication",
            assess_replication_decision(
                _load_json(root / REPLICATION_FILE),
                clone_safety=clone_result,
                exposure=exposure_result,
                concordance=concordance_result,
                hypomorph=hypomorph_result,
                hypothesis=hypothesis_result,
                confirmation=confirmation_result,
                phase=phase_result,
                transcript=transcript_result,
            ),
        )
    else:
        step = _skipped("replication", "earlier_gate_blocked")
    steps.append(step)
    block(step)

    # next_experiment still runs after a hold — recommending the next spend
    # is its purpose — but not after a hard stop.
    if not any(
        item["program_effect"] == "stop" and not item["skipped"]
        for item in steps
    ):
        step = _step(
            "next_experiment",
            assess_next_experiment(_load_json(root / CAUSAL_FILE), steps),
        )
    else:
        step = _skipped("next_experiment", "earlier_gate_blocked")
    steps.append(step)
    if step["program_effect"] == "stop":
        prior = next((row for row in steps if row["name"] == blocked_by), None)
        if blocked_by is None or prior is None or prior.get("program_effect") != "stop":
            blocked_by = step["name"]
            block_reason = step["reason"]
    else:
        block(step)

    effects = [item["program_effect"] for item in steps if not item["skipped"]]
    if "stop" in effects:
        decision = "stop"
    elif any(effect != "pass" for effect in effects) or any(item["skipped"] for item in steps):
        decision = "hold"
    else:
        decision = "advance"
    if decision == "advance":
        hypothesis_step = next(item for item in steps if item["name"] == "hypothesis")
        hypomorph_step = next(item for item in steps if item["name"] == "hypomorph")
        child = (hypothesis_step.get("result") or {}).get("child_claim_strength")
        ready = bool((hypomorph_step.get("result") or {}).get("checkpoint_ready"))
        if child != "conditional_ex_vivo":
            decision = "hold"
            blocked_by = "hypothesis"
            block_reason = "child_claim_too_weak"
        elif not ready:
            decision = "hold"
            blocked_by = "hypomorph"
            block_reason = "checkpoint_not_ready"
    result = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "gate_claim_boundary": GATE_CLAIM,
        "decision": decision,
        "blocked_by": blocked_by,
        "block_reason": block_reason,
        "n_steps": len(steps),
        "n_skipped": sum(1 for item in steps if item["skipped"]),
        "steps": steps,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


__all__ = [
    "CLAIM_BOUNDARY",
    "SCHEMA",
    "CommunityPipelineError",
    "run_community_pipeline",
]
