"""Side-by-side gating of competing rescue hypotheses.

Each hypothesis table is assessed independently by
``assess_hypothesis_strength``; the comparison never relaxes a floor and
never promotes a weaker record. The lead is the passing hypothesis whose
participant-claim strength is strictly highest — a tie is reported as no
lead rather than an arbitrary pick.

Hypothesis-comparison software contract only; a precise experimental
hypothesis is not a treatment, dose, or cure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mva_hackathon.hypothesis import (
    STRENGTHS,
    HypothesisStrengthError,
    assess_hypothesis_strength,
)
from mva_hackathon.provenance import receipt_sha256

SCHEMA = "mva-track2-hypothesis-comparison/v1"
CLAIM_BOUNDARY = (
    "Hypothesis-comparison software contract only; a precise experimental "
    "hypothesis is not a treatment, dose, or cure."
)


class HypothesisComparisonError(HypothesisStrengthError):
    """Raised when a hypothesis comparison violates its contract."""


def compare_hypotheses(
    hypotheses: Mapping[str, Mapping[str, Any]],
    *,
    nested_gates: Mapping[str, Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Gate each named hypothesis and report a descriptive comparison."""

    if not isinstance(hypotheses, Mapping) or len(hypotheses) < 2:
        raise HypothesisComparisonError(
            "hypothesis comparison requires at least two named tables"
        )
    if len(hypotheses) > 64:
        raise HypothesisComparisonError("hypothesis comparison is bounded to 64 tables")
    names = list(hypotheses)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise HypothesisComparisonError("hypothesis names must be non-empty strings")
    if len({name.casefold() for name in names}) != len(names):
        raise HypothesisComparisonError("hypothesis names must be unique")
    gates = dict(nested_gates or {})
    rows: dict[str, dict[str, Any]] = {}
    for name in names:
        result = assess_hypothesis_strength(hypotheses[name], **gates)
        rows[name] = {
            "status": result["status"],
            "reason": result["reason"],
            "program_effect": result["program_effect"],
            "child_claim_strength": result["child_claim_strength"],
            "work_ceiling": result["work_ceiling"],
            "falsifier_count": len(result["falsifier_ids"]),
            "alternative_count": len(result["alternative_ids"]),
            "control_count": len(result["control_ids"]),
        }
    passing = [
        name for name, row in rows.items() if row["status"] == "pass"
    ]
    if not passing:
        lead = None
        selection = "no_surviving_hypothesis"
    else:
        ranks = {
            name: STRENGTHS.index(str(rows[name]["child_claim_strength"]))
            for name in passing
            if str(rows[name]["child_claim_strength"]) in STRENGTHS
        }
        if len(ranks) != len(passing):
            raise HypothesisComparisonError(
                "a passing hypothesis produced an unknown claim strength"
            )
        best_rank = max(ranks.values())
        best = [name for name in passing if ranks[name] == best_rank]
        if len(best) == 1:
            lead = best[0]
            selection = "lead_by_claim_strength"
        else:
            lead = None
            selection = "tied_no_lead"
    result = {
        "schema": SCHEMA,
        "gate": "hypothesis_comparison",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": "pass" if passing else "stop",
        "program_effect": "pass" if passing else "stop",
        "reason": selection,
        "hypotheses": rows,
        "passing_hypotheses": passing,
        "lead_hypothesis": lead,
        "selection_rule": selection,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


__all__ = [
    "CLAIM_BOUNDARY",
    "SCHEMA",
    "HypothesisComparisonError",
    "compare_hypotheses",
]
