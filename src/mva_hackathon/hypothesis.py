"""Weakest-link hypothesis-strength contract.

A precise experimental hypothesis is not a medicine. Pair-program strength
cannot exceed the weakest required link, including unmeasured RNA. A story
with no kill-rule cannot pass. An isogenic missense experiment can still be
labeled work to run when phase is unresolved. Analog-allele, homolog-allele,
ortholog-allele, paralog-allele, mouse-allele, yeast-allele, nearby-allele,
AlphaFold, FoldX, AlphaMissense, geometry ranking, coordinate geometry,
docking, complementation, in-silico, pathogenicity-score, ESM, REVEL, MAVE,
frequency, conservation, ClinVar, official-label, software, software-catalog,
database, ontology, literature, cell-free, ectopic, unmatched,
imposed-stress, or false-rescue wording cannot upgrade a
link to observed.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from mva_hackathon.provenance import (
    ProvenanceError,
    receipt_sha256,
    receipt_sha256_ok,
)
from mva_hackathon.program_gates import (
    ANALOG_PHRASES,
    CLAIM_BOUNDARY as GATE_CLAIM,
    EVIDENCE_SCHEMA,
    EXPOSURE_SCHEMA,
    OVERCLAIM_PHRASES,
    PROGRAM_SCHEMA,
    ProgramGateError,
    _identifier,
    _mapping,
    claim_blob_matches,
    normalize_claim_joined,
    normalize_claim_text,
)


SCHEMA = "mva-track2-hypothesis-strength/v1"
STRENGTHS = ("unsupported", "experiment_to_run", "conditional_ex_vivo")
HYPOTHESIS_ROLES = (
    "confirmation",
    "pair",
    "transcript",
    "stability",
    "probe",
    "endpoint",
    "falsifier",
    "alternative",
    "positive_control",
    "negative_control",
    "multiplicity",
    "counterscreen",
    "other",
)
PAIR_PROGRAM_ROLES = (
    "confirmation",
    "pair",
    "transcript",
    "stability",
    "probe",
)
GATE_BIND_ROLES = {
    "confirmation": "confirmation",
    "pair": "phase",
    "transcript": "transcript",
    "stability": "hypomorph",
    "probe": "exposure",
    "endpoint": "concordance",
    # An observed control result must come from a passing exposure gate; a
    # control observed without the exposure record cannot stand.
    "positive_control": "exposure",
    "negative_control": "exposure",
}
GATE_BIND_SCHEMAS = {
    "confirmation": PROGRAM_SCHEMA,
    "phase": PROGRAM_SCHEMA,
    "transcript": PROGRAM_SCHEMA,
    "hypomorph": PROGRAM_SCHEMA,
    "exposure": EXPOSURE_SCHEMA,
    "concordance": PROGRAM_SCHEMA,
}
IDENTITY_BIND_ROLES = {
    key: GATE_BIND_ROLES[key] for key in ("confirmation", "pair", "transcript")
}
CONTROL_ROLES = ("positive_control", "negative_control")
LINEAGE_FINGERPRINT_GATES = ("concordance",)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
STATUS_TO_STRENGTH = {
    "observed": "conditional_ex_vivo",
    "inferred": "experiment_to_run",
    "hypothesis": "experiment_to_run",
    "planned_experiment": "experiment_to_run",
    "synthetic_test": "experiment_to_run",
    "unknown": "unsupported",
}
FALSE_RESCUE_PHRASES = (
    "upregulation is rescue",
    "heat-shock family rescued",
    "organ size means checkpoint",
    "chaperone restored checkpoint",
    "this is target engagement",
    "bulk aneuploidy is rescue",
    "lower aneuploidy is rescue",
    "selection is generation",
    "arrest is rescue",
    "death masking is rescue",
)
CONTROL_FAIL_PHRASES = (
    "positive control failed",
    "negative control failed",
    "control failed",
)
# A kill rule is only testable when it is conditional on a named endpoint;
# a falsifier that merely restates the claim is not a kill rule.
FALSIFIER_CONDITIONAL_PHRASES = (
    "if",
    "when",
    "unless",
)
FALSIFIER_KILL_PHRASES = (
    "stops",
    "stop",
    "fails",
    "fail",
    "does not",
    "no rescue",
    "is dead",
    "refutes",
    "refuted",
    "not rescued",
)
# Masquerade families the competing-explanation links must collectively name
# so the stated alternatives actually cover the known false-rescue mechanisms.
MASQUERADE_TERMS = (
    "cytostasis",
    "selection",
    "pruning",
    "masking",
    "aneuploid",
    "drift",
    "batch",
    "overgrowth",
    "dilution",
    "competing risk",
    "toxicity",
    "interference",
    "promiscuous",
    "fluorescence",
    "autofluorescence",
    "aggregation",
    "reactive",
    "pan-assay",
)
# Repurposing screens are confounded by promiscuous/interference artifacts
# (membrane disruption, phospholipidosis, autofluorescence, aggregators) —
# at least one competing explanation must name that family.
INTERFERENCE_TERMS = (
    "interference",
    "promiscuous",
    "fluorescence",
    "autofluorescence",
    "aggregation",
    "reactive",
    "pan-assay",
)
# A named interference alternative is not enough — the program must also
# predeclare an orthogonal counterscreen assay that actively tests for
# promiscuous/artifact activity (orthogonal binding, allele-independent
# counterscreen, physicochemical artifact panel).
COUNTERSCREEN_TERMS = (
    "counterscreen",
    "counter-screen",
    "orthogonal",
    "secondary assay",
    "allele-independent",
    "independent assay",
    "artifact panel",
)
# A kill rule only discriminates rescue from masquerade when it names both a
# measured endpoint and at least one confounder family.
FALSIFIER_ENDPOINT_TERMS = (
    "rna",
    "transcript",
    "correction",
    "generation",
    "division",
    "daughter",
    "abundance",
    "checkpoint",
    "lineage",
    "segregation",
    "endpoint",
    "exposure",
)
# Controls only control when they run under the same protocol as the arms.
CONTROL_PARITY_PHRASES = (
    "same imaging",
    "same protocol",
    "same exposure",
    "matched protocol",
    "identical protocol",
    "same assay",
    "same conditions",
)
# The exact-correction anchor is isogenic/exact-corrected — a wild-type row
# alone is a secondary reference and cannot stand in for the correction row.
EXACT_CONTROL_PHRASES = (
    "exact",
    "corrected",
    "isogenic",
)
BASELINE_CONTROL_PHRASES = (
    "vehicle",
    "untreated",
    "unexposed",
    "baseline",
    "mock",
)
MINIMUM_MASQUERADE_COVERAGE = 2
# Role-content floors: each declared link must name the scientific content
# the gate can actually measure, not just occupy the role.
ENDPOINT_DIRECTION_TERMS = (
    "increase",
    "increases",
    "decrease",
    "decreases",
    "raises",
    "lowers",
    "fewer",
    "more",
    "higher",
    "lower",
    "restores",
    "reverses",
    "reduces",
)
ENDPOINT_COMPARATOR_TERMS = (
    "versus",
    "relative to",
    "compared",
    "against",
)
# The rescue endpoint must be a lineage-tracked quantity — a non-lineage
# endpoint cannot distinguish rescue from selection or cytostasis.
ENDPOINT_LINEAGE_TERMS = (
    "generation",
    "division",
    "daughter",
    "segregation",
    "lineage",
)
PAIR_CONFIGURATION_TERMS = (
    "trans",
    "cis",
    "compound heterozygous",
    "biallelic",
    "homozygous",
)
PREDECLARATION_TERMS = (
    "predeclared",
    "pre-registered",
    "registered",
    "precommitted",
    "precommitted",
)
STABILITY_PROPERTY_TERMS = (
    "abundance",
    "half life",
    "stability",
    "folding",
    "aggregation",
    "localization",
    "activity",
)
TRANSCRIPT_MEASURAND_TERMS = (
    "rna",
    "transcript",
    "expression",
    "depleted",
    "expressed",
    "splicing",
    "mrna",
)
PROBE_MECHANISM_TERMS = (
    "chaperone",
    "readthrough",
    "stabilizer",
    "corrector",
    "potentiator",
    "splice",
    "modifier",
    "small molecule",
)
# Each declaration role must name the links it depends on via a `watches`
# field — a falsifier watches the endpoint it kills, an alternative watches
# the measurement it masquerades, an endpoint is read under a probe arm,
# controls watch the endpoint they bound, a counterscreen watches the probe
# it screens, and the multiplicity rule watches the family it controls.
WATCH_TARGETS = {
    # The evidence chain is a DAG: each link watches the evidence it
    # depends on — phase depends on confirmation, transcript on phase,
    # stability on transcript, probe on stability, endpoint on probe,
    # and every derived declaration watches what it governs.
    "pair": frozenset({"confirmation"}),
    "transcript": frozenset({"pair"}),
    "stability": frozenset({"transcript"}),
    "probe": frozenset({"stability"}),
    "endpoint": frozenset({"probe"}),
    "falsifier": frozenset({"endpoint"}),
    "alternative": frozenset(
        {"endpoint", "positive_control", "negative_control"}
    ),
    "positive_control": frozenset({"endpoint"}),
    "negative_control": frozenset({"endpoint"}),
    "counterscreen": frozenset({"probe"}),
    "multiplicity": frozenset({"probe", "endpoint"}),
}
# A predeclared error-control rule needs a numeric bound (alpha / FDR level).
# A multi-candidate rescue program must predeclare its error-control rule —
# how it handles multiple comparisons across probes and endpoints.
MULTIPLICITY_TERMS = (
    "bonferroni",
    "benjamini",
    "fdr",
    "false discovery",
    "familywise",
    "hierarchical",
    "gatekeeping",
    "multiplicity",
    "hochberg",
    "holm",
)
CLAIM_BOUNDARY = (
    "Hypothesis-strength software contract only; weakest link wins; "
    "a precise experimental hypothesis is not a treatment, dose, or cure."
)


class HypothesisStrengthError(ProgramGateError):
    """Raised when a hypothesis declaration violates its contract."""


def _rank(strength: str) -> int:
    try:
        return STRENGTHS.index(strength)
    except ValueError as exc:
        raise HypothesisStrengthError("strength is not in the allowed vocabulary") from exc


def _watch_graph_has_cycle(
    link_watches: list[tuple[str, str, tuple[str, ...]]],
) -> bool:
    edges: dict[str, list[str]] = {}
    for link_id, _, watches in link_watches:
        edges.setdefault(link_id, []).extend(watches)
    visiting: set[str] = set()
    visited: set[str] = set()

    def walks_back(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for target in edges.get(node, []):
            if walks_back(target):
                return True
        visiting.discard(node)
        visited.add(node)
        return False

    return any(walks_back(link_id) for link_id, _, _ in link_watches)


def _min_strength(values: list[str]) -> str:
    if not values:
        return "unsupported"
    return min(values, key=_rank)


def _max_strength(values: list[str]) -> str:
    if not values:
        return "unsupported"
    return max(values, key=_rank)


_NORMALIZED_ANALOG_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in ANALOG_PHRASES
)
_NORMALIZED_FALSE_RESCUE_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in FALSE_RESCUE_PHRASES
)
_NORMALIZED_OVERCLAIM_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in OVERCLAIM_PHRASES
)
_NORMALIZED_CONTROL_FAIL_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in CONTROL_FAIL_PHRASES
)
_JOINED_ANALOG_PHRASES = tuple(
    normalize_claim_joined(phrase) for phrase in ANALOG_PHRASES
)
_JOINED_FALSE_RESCUE_PHRASES = tuple(
    normalize_claim_joined(phrase) for phrase in FALSE_RESCUE_PHRASES
)
_JOINED_OVERCLAIM_PHRASES = tuple(
    normalize_claim_joined(phrase) for phrase in OVERCLAIM_PHRASES
)
_JOINED_CONTROL_FAIL_PHRASES = tuple(
    normalize_claim_joined(phrase) for phrase in CONTROL_FAIL_PHRASES
)
# A kill rule must name a measurable boundary — a predeclared threshold or
# reference level — not merely a stop word.
FALSIFIER_BOUNDARY_TERMS = (
    "baseline",
    "wild-type range",
    "threshold",
    "at least",
    "no more",
    "within",
    "fold",
    "percent",
    "background",
    "untreated",
)
_NORMALIZED_FALSIFIER_CONDITIONAL_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in FALSIFIER_CONDITIONAL_PHRASES
)
_NORMALIZED_FALSIFIER_BOUNDARY_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in FALSIFIER_BOUNDARY_TERMS
)
# A falsifiable kill rule carries an explicit number or percent — the stop
# condition must be quantitative, not just bounded.
_NUMERIC_BOUND = re.compile(r"\d|%")
_NORMALIZED_INTERFERENCE_TERMS = tuple(
    normalize_claim_text(term) for term in INTERFERENCE_TERMS
)
_NORMALIZED_MULTIPLICITY_TERMS = tuple(
    normalize_claim_text(term) for term in MULTIPLICITY_TERMS
)
_NORMALIZED_COUNTERSCREEN_TERMS = tuple(
    normalize_claim_text(term) for term in COUNTERSCREEN_TERMS
)
_NORMALIZED_FALSIFIER_KILL_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in FALSIFIER_KILL_PHRASES
)
_NORMALIZED_MASQUERADE_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in MASQUERADE_TERMS
)
_NORMALIZED_FALSIFIER_ENDPOINT_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in FALSIFIER_ENDPOINT_TERMS
)
_NORMALIZED_CONTROL_PARITY_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in CONTROL_PARITY_PHRASES
)
_NORMALIZED_EXACT_CONTROL_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in EXACT_CONTROL_PHRASES
)
_NORMALIZED_BASELINE_CONTROL_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in BASELINE_CONTROL_PHRASES
)
_NORMALIZED_ENDPOINT_DIRECTION_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in ENDPOINT_DIRECTION_TERMS
)
_NORMALIZED_ENDPOINT_COMPARATOR_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in ENDPOINT_COMPARATOR_TERMS
)
_NORMALIZED_ENDPOINT_LINEAGE_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in ENDPOINT_LINEAGE_TERMS
)
_NORMALIZED_PAIR_CONFIGURATION_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in PAIR_CONFIGURATION_TERMS
)
_NORMALIZED_PREDECLARATION_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in PREDECLARATION_TERMS
)
_NORMALIZED_STABILITY_PROPERTY_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in STABILITY_PROPERTY_TERMS
)
_NORMALIZED_TRANSCRIPT_MEASURAND_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in TRANSCRIPT_MEASURAND_TERMS
)
_NORMALIZED_PROBE_MECHANISM_TERMS = tuple(
    normalize_claim_text(phrase) for phrase in PROBE_MECHANISM_TERMS
)
# Word-boundary forms of the comparator markers: 'wild-type' normalizes to
# 'wild type', and 'correct' alone must not ride inside 'uncorrected'.
_NORMALIZED_CONTROL_ARM_MARKERS = (
    "correct",
    "corrected",
    "correction",
    "isogenic",
    "wild type",
)
# Explicit negations — a comparator labelled 'uncorrected' or 'non-isogenic'
# is the opposite of an exact-correction floor even though the bare marker
# word is present.
_NEGATED_CONTROL_ARM_MARKERS = (
    "uncorrected",
    "noncorrected",
    "non corrected",
    "not corrected",
    "nonisogenic",
    "non isogenic",
    "not isogenic",
    "non wild type",
    "not wild type",
)


def _term_in(spaced: str, term: str) -> bool:
    """Word-boundary containment so short terms cannot ride inside words."""
    return f" {term} " in f" {spaced} "


def _link_blobs(item: Mapping[str, Any]) -> tuple[str, str]:
    # Floor terms must live in the statement itself — supports can describe
    # what a link backs, but cannot donate the required vocabulary.
    # does_not_support is a disclaimer field — content there is negated by
    # construction, so it can neither donate required floor terms nor act as
    # an affirmative claim; it is intentionally excluded from the blob.
    raw = str(item.get("statement", ""))
    return normalize_claim_text(raw), normalize_claim_joined(raw)


def _link_full_blobs(item: Mapping[str, Any]) -> tuple[str, str]:
    # Banned-wording checks scan statement + supports together: an affirmative
    # analog/medicine/overclaim phrase parked in supports is still a claim.
    raw = f"{item.get('statement', '')} {item.get('supports', '')}"
    return normalize_claim_text(raw), normalize_claim_joined(raw)


def _receipt_or_raise(payload: Mapping[str, Any]) -> str:
    """Compute a receipt digest; a non-canonical payload fails closed."""

    try:
        return receipt_sha256(payload)
    except ProvenanceError as exc:
        raise HypothesisStrengthError(
            "payload cannot be canonicalized for a receipt digest"
        ) from exc


def _bounded_magnitude(value: Any) -> float | None:
    """Return a finite bound in [1e-9, 1e6] or None — fail closed, never raise."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(parsed) or not 1e-9 <= parsed <= 1e6:
        return None
    return parsed


def _nested_effect(
    nested: Mapping[str, Any] | None,
    *,
    expected_schema: str | None = None,
    expected_gate: str | None = None,
) -> str | None:
    if not isinstance(nested, Mapping):
        return None
    effect = nested.get("program_effect")
    status = nested.get("status")
    if (
        effect in {"pass", "hold", "stop"}
        and status in {"pass", "hold", "stop"}
        and status != effect
    ):
        return "stop"
    # A pass effect must be backed by a pass status — a nested receipt that
    # declares effect=pass while its status is absent or not_assessable is a
    # fabricated pass, treated as a hard stop rather than a soft hold.
    if effect == "pass" and status != "pass":
        return "stop"
    # A pass claim must carry a valid self-integrity digest — a receipt that
    # was mutated after computation, or a fabricated receipt missing its
    # digest, cannot back an observed claim. A malformed receipt whose digest
    # cannot even be computed fails closed the same way.
    if effect == "pass":
        try:
            digest_ok = receipt_sha256_ok(nested)
        except ProvenanceError:
            digest_ok = False
        if not digest_ok:
            return "stop"
    # A pass must also carry the minimal receipt surface — a fabricated
    # minimal mapping with a valid self-digest cannot stand in for a real
    # gate receipt. "schema" is universal across gate receipts; "gate" is
    # required only when one is expected (the exposure receipt names none).
    if effect == "pass":
        required = {"schema"}
        if expected_gate is not None:
            required = required | {"gate"}
        if not required.issubset(nested):
            return "stop"
    if effect == "pass":
        if expected_schema is not None and nested.get("schema") != expected_schema:
            return "hold"
        if expected_gate is not None and nested.get("gate") != expected_gate:
            return "hold"
        return "pass"
    if effect in {"hold", "stop"}:
        return str(effect)
    return None


def mark_pair_program_observed(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Fill synthetic pair-program links as observed for save-path tests.

    Falsifier, alternative, and control links stay planned. This is not a
    child's result.
    """

    record = dict(payload)
    record["declared_overall_strength"] = "conditional_ex_vivo"
    links = []
    for raw in record.get("links", []):
        item = dict(raw)
        if item.get("hypothesis_role") in PAIR_PROGRAM_ROLES:
            item["status"] = "observed"
        if item.get("link_id") == "syn-link-phase":
            item["statement"] = (
                "Two distinct guide configurations support trans in this fixture."
            )
            item["supports"] = "a computed phase record in this fixture"
        if item.get("link_id") == "syn-link-transcript":
            item["statement"] = (
                "Stop-class RNA is depleted and missense RNA is expressed in this fixture."
            )
            item["supports"] = "a computed transcript record in this fixture"
        if item.get("link_id") == "syn-link-orthogonal-confirm":
            item["statement"] = (
                "Both synthetic alleles are confirmed on a second aliquot in this fixture."
            )
            item["supports"] = "a computed confirmation record in this fixture"
        links.append(item)
    record["links"] = links
    return record


def assess_hypothesis_strength(
    payload: Mapping[str, Any],
    *,
    confirmation: Mapping[str, Any] | None = None,
    phase: Mapping[str, Any] | None = None,
    transcript: Mapping[str, Any] | None = None,
    hypomorph: Mapping[str, Any] | None = None,
    exposure: Mapping[str, Any] | None = None,
    concordance: Mapping[str, Any] | None = None,
    clone_safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Score pair-program vs isogenic-probe strength from labeled links.

    Declaring conditional ex-vivo for the child when phase or RNA is unknown
    is a stop. A missing kill-rule, competing explanation, or control pair
    is a stop. A kill rule that is not conditional on a named endpoint is a
    stop. Competing explanations that do not collectively name at least two
    masquerade families (cytostasis, selection, masking, toxicity, and kin)
    are a stop. A positive control that is not the exact-correction or
    isogenic row, or a negative control that is not a vehicle/baseline row,
    is a stop. An observed identity, stability, probe, or endpoint label
    without a nested gate pass is a stop. Omitting those nested objects
    cannot stand in. A status tick or schema-less pass object cannot stand
    in for an assessor result. Declaring a medicine is a stop. Analog or
    false-rescue, in-silico, pathogenicity-score, ESM, REVEL, MAVE, frequency,
    conservation, or ClinVar wording cannot count as observed exact-allele or
    checkpoint rescue.
    """

    record = _mapping(payload, "hypothesis table")
    if record.get("schema") != EVIDENCE_SCHEMA:
        raise HypothesisStrengthError("hypothesis gate accepts the community evidence table only")
    declared = record.get("declared_overall_strength")
    if declared not in STRENGTHS:
        raise HypothesisStrengthError("declared_overall_strength is required")
    medicine = record.get("declared_probe_is_medicine")
    if not isinstance(medicine, bool):
        raise HypothesisStrengthError("declared_probe_is_medicine must be a boolean")
    vocab = record.get("status_vocabulary")
    if not isinstance(vocab, list) or not vocab:
        raise HypothesisStrengthError("status vocabulary is required")
    if len(vocab) != len(set(vocab)) or set(vocab) != set(STATUS_TO_STRENGTH):
        raise HypothesisStrengthError(
            "status vocabulary must be the canonical status set"
        )
    links = record.get("links")
    if not isinstance(links, list) or not links:
        raise HypothesisStrengthError("evidence table has no links")
    if len(links) > 10_000:
        raise HypothesisStrengthError("evidence table exceeds the link ceiling")

    by_role: dict[str, list[str]] = {role: [] for role in HYPOTHESIS_ROLES}
    analog_ids: list[str] = []
    false_rescue_ids: list[str] = []
    overclaim_ids: list[str] = []
    falsifier_ids: list[str] = []
    falsified_ids: list[str] = []
    alternative_ids: list[str] = []
    alternative_observed_ids: list[str] = []
    control_ids: list[str] = []
    failed_control_ids: list[str] = []
    falsifier_blobs: list[tuple[str, str]] = []
    declared_falsifier_blobs: list[tuple[str, str]] = []
    alternative_blobs: list[tuple[str, str]] = []
    positive_control_blobs: list[tuple[str, str]] = []
    negative_control_blobs: list[tuple[str, str]] = []
    endpoint_blobs: list[tuple[str, str]] = []
    pair_blobs: list[tuple[str, str]] = []
    stability_blobs: list[tuple[str, str]] = []
    transcript_blobs: list[tuple[str, str]] = []
    probe_blobs: list[tuple[str, str]] = []
    multiplicity_ids: list[str] = []
    multiplicity_blobs: list[tuple[str, str]] = []
    counterscreen_ids: list[str] = []
    counterscreen_blobs: list[tuple[str, str]] = []
    commitment_observed_ids: list[str] = []
    falsifier_watch_ids: list[tuple[str, ...]] = []
    endpoint_ids: set[str] = set()
    probe_ids: set[str] = set()
    role_by_id: dict[str, str] = {}
    link_watches: list[tuple[str, str, tuple[str, ...]]] = []
    endpoint_specs: dict[str, float] = {}
    endpoint_spec_bad: list[str] = []
    falsifier_bounds: list[tuple[str, float | None]] = []
    seen_link_ids: set[str] = set()
    seen_statements: set[str] = set()
    seen_token_sets: set[frozenset[str]] = set()
    observed_roles: set[str] = set()
    for raw in links:
        item = _mapping(raw, "evidence link")
        link_id = _identifier(item.get("link_id"), "link_id")
        if link_id in seen_link_ids:
            raise HypothesisStrengthError("evidence link ids must be unique")
        seen_link_ids.add(link_id)
        status = item.get("status")
        if status not in vocab or status not in STATUS_TO_STRENGTH:
            raise HypothesisStrengthError("evidence status is not in the allowed vocabulary")
        role = item.get("hypothesis_role")
        if role not in HYPOTHESIS_ROLES:
            raise HypothesisStrengthError("hypothesis_role is required")
        for field in ("statement", "supports", "does_not_support"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise HypothesisStrengthError(
                    f"evidence link requires a non-empty {field}"
                )
        blob, joined_blob = _link_blobs(item)
        full_blob, full_joined = _link_full_blobs(item)
        if claim_blob_matches(
            full_blob,
            full_joined,
            _NORMALIZED_ANALOG_PHRASES,
            _JOINED_ANALOG_PHRASES,
        ):
            analog_ids.append(link_id)
        if claim_blob_matches(
            full_blob,
            full_joined,
            _NORMALIZED_FALSE_RESCUE_PHRASES,
            _JOINED_FALSE_RESCUE_PHRASES,
        ):
            false_rescue_ids.append(link_id)
        # Banned claim wording is banned at every status — a cure or
        # dosage phrase cannot hide inside an inferred or planned link.
        if claim_blob_matches(
            full_blob,
            full_joined,
            _NORMALIZED_OVERCLAIM_PHRASES,
            _JOINED_OVERCLAIM_PHRASES,
        ):
            overclaim_ids.append(link_id)
        if blob in seen_statements:
            raise HypothesisStrengthError(
                "evidence link statements must be distinct"
            )
        seen_statements.add(blob)
        # A permutation of the same token pool is not a distinct statement.
        token_multiset = frozenset(blob.split())
        if token_multiset in seen_token_sets:
            raise HypothesisStrengthError(
                "evidence link statements must not be token-set permutations"
            )
        seen_token_sets.add(token_multiset)
        role_by_id[link_id] = str(role)
        watches = item.get("watches")
        link_watches.append(
            (
                link_id,
                str(role),
                tuple(watches) if isinstance(watches, (list, tuple)) else (),
            )
        )
        if role == "falsifier":
            falsifier_ids.append(link_id)
            falsifier_blobs.append((blob, joined_blob))
            falsifier_watch_ids.append(link_watches[-1][2])
            bound = item.get("bound")
            falsifier_bounds.append(
                (
                    link_id,
                    # A bound must be finite, positive, and within a
                    # biologically plausible range — a degenerate magnitude
                    # like 1e-300 or 1e300 cannot falsify anything.
                    _bounded_magnitude(bound),
                )
            )
            # An inferred kill condition is an unresolved threat; it blocks
            # exactly like an observed one until it is ruled out.
            if status in {"observed", "inferred"}:
                falsified_ids.append(link_id)
            # Only an articulated falsifier (hypothesis / planned / synthetic
            # test) can populate a kill rule — an 'unknown' falsifier is not
            # a declared stop condition.
            if status in {"hypothesis", "planned_experiment", "synthetic_test"}:
                declared_falsifier_blobs.append((blob, joined_blob))
        if role == "alternative":
            alternative_ids.append(link_id)
            alternative_blobs.append((blob, joined_blob))
            # An inferred competing explanation is an unexcluded threat; it
            # blocks exactly like an observed one until it is ruled out.
            if status in {"observed", "inferred"}:
                alternative_observed_ids.append(link_id)
        if role == "positive_control":
            positive_control_blobs.append((blob, joined_blob))
        if role == "negative_control":
            negative_control_blobs.append((blob, joined_blob))
        if role == "endpoint":
            endpoint_blobs.append((blob, joined_blob))
            endpoint_ids.add(link_id)
            spec = item.get("spec")
            spec_bound = (
                spec.get("rescue_bound") if isinstance(spec, Mapping) else None
            )
            spec_control = (
                normalize_claim_text(spec.get("control_arm"))
                if isinstance(spec, Mapping)
                else ""
            )
            if (
                not isinstance(spec, Mapping)
                or not isinstance(spec.get("measurement"), str)
                or not str(spec.get("measurement")).strip()
                or not isinstance(spec.get("control_arm"), str)
                or not str(spec.get("control_arm")).strip()
                # The comparator arm must be a correction/isogenic arm —
                # 'vehicle' or 'untreated' is not an exact-correction floor.
                or not any(
                    _term_in(spec_control, marker)
                    for marker in _NORMALIZED_CONTROL_ARM_MARKERS
                )
                or any(
                    _term_in(spec_control, marker)
                    for marker in _NEGATED_CONTROL_ARM_MARKERS
                )
                or not isinstance(spec.get("treatment_arm"), str)
                or not str(spec.get("treatment_arm")).strip()
                # The endpoint must be read blinded — an unblinded read of
                # a rescue endpoint invites scorer bias.
                or spec.get("blinded") is not True
                or _bounded_magnitude(spec_bound) is None
            ):
                endpoint_spec_bad.append(link_id)
            else:
                endpoint_specs[link_id] = _bounded_magnitude(spec_bound)
        if role == "pair":
            pair_blobs.append((blob, joined_blob))
        if role == "stability":
            stability_blobs.append((blob, joined_blob))
        if role == "transcript":
            transcript_blobs.append((blob, joined_blob))
        if role == "probe":
            probe_blobs.append((blob, joined_blob))
            probe_ids.add(link_id)
        if role == "multiplicity":
            multiplicity_ids.append(link_id)
            multiplicity_blobs.append((blob, joined_blob))
            # A multiplicity rule is a commitment, not a result — it cannot
            # be claimed observed or inferred, only declared.
            if status in {"observed", "inferred"}:
                commitment_observed_ids.append(link_id)
        if role == "counterscreen":
            counterscreen_ids.append(link_id)
            counterscreen_blobs.append((blob, joined_blob))
            if status in {"observed", "inferred"}:
                commitment_observed_ids.append(link_id)
        if role in CONTROL_ROLES:
            control_ids.append(link_id)
            if status == "observed" and claim_blob_matches(
                full_blob,
                full_joined,
                _NORMALIZED_CONTROL_FAIL_PHRASES,
                _JOINED_CONTROL_FAIL_PHRASES,
            ):
                failed_control_ids.append(link_id)
        if status == "observed":
            observed_roles.add(str(role))
        by_role[str(role)].append(STATUS_TO_STRENGTH[str(status)])

    endpoint_digit_set: set[str] = set()
    for spaced, _ in endpoint_blobs:
        endpoint_digit_set.update(re.findall(r"\d+", spaced))

    pair_strength = _min_strength(by_role["pair"])
    stability_strength = _min_strength(by_role["stability"])
    probe_link_strength = _min_strength(by_role["probe"])
    confirmation_strength = _min_strength(by_role["confirmation"])
    transcript_strength = _min_strength(by_role["transcript"])
    isogenic_probe_strength = _min_strength(
        [value for value in (stability_strength, probe_link_strength)]
    )
    pair_program_strength = _min_strength(
        [
            confirmation_strength,
            pair_strength,
            transcript_strength,
            stability_strength,
            probe_link_strength,
        ]
    )
    child_claim_strength = pair_program_strength
    work_ceiling = _max_strength([isogenic_probe_strength, pair_program_strength])
    nested_gates = {
        "confirmation": confirmation,
        "phase": phase,
        "transcript": transcript,
        "hypomorph": hypomorph,
        "exposure": exposure,
        "concordance": concordance,
    }
    supplied = {name: payload for name, payload in nested_gates.items() if payload is not None}
    unbound_roles: list[str] = []
    for role, gate_name in GATE_BIND_ROLES.items():
        if role not in observed_roles:
            continue
        nested = supplied.get(gate_name)
        bound = (
            _nested_effect(
                nested,
                expected_schema=GATE_BIND_SCHEMAS[gate_name],
                expected_gate=None if gate_name == "exposure" else gate_name,
            )
            == "pass"
        )
        if bound and gate_name in LINEAGE_FINGERPRINT_GATES:
            fingerprint = nested.get("source_fingerprint")
            if not _is_sha256(fingerprint):
                bound = False
            elif isinstance(clone_safety, Mapping):
                other = clone_safety.get("source_fingerprint")
                if isinstance(other, str) and other != fingerprint:
                    bound = False
        if not bound:
            unbound_roles.append(role)
    competing_toxicity = False
    if isinstance(clone_safety, Mapping) and (
        clone_safety.get("clone_safety_stop") is True
        or _nested_effect(clone_safety) == "stop"
    ):
        competing_toxicity = True
    if isinstance(concordance, Mapping) and concordance.get("reason") == "competing_toxicity":
        competing_toxicity = True
    if competing_toxicity and alternative_ids and not alternative_observed_ids:
        alternative_observed_ids.append("syn-auto-competing-toxicity")

    kill_blobs = [
        (spaced, joined)
        for spaced, joined in declared_falsifier_blobs
        if any(
            " " + conditional + " " in f" {spaced} "
            for conditional in _NORMALIZED_FALSIFIER_CONDITIONAL_PHRASES
        )
        and any(
            _term_in(spaced, kill)
            for kill in _NORMALIZED_FALSIFIER_KILL_PHRASES
        )
    ]
    kill_masquerade_set: set[str] = {
        term
        for term in _NORMALIZED_MASQUERADE_TERMS
        if any(_term_in(spaced, term) for spaced, _ in kill_blobs)
    }

    # Real contradictions surface before wording floors so an observed
    # kill-rule or unexcluded competing explanation is never masked by a
    # phrasing finding.
    if falsified_ids:
        status = "stop"
        reason = "hypothesis_falsified"
        effect = "stop"
    elif alternative_observed_ids:
        status = "stop"
        reason = "alternative_not_excluded"
        effect = "stop"
    elif failed_control_ids:
        status = "stop"
        reason = "control_failed"
        effect = "stop"
    elif commitment_observed_ids:
        status = "stop"
        reason = "commitment_claimed_observed"
        effect = "stop"
    elif medicine:
        status = "stop"
        reason = "medicine_claim"
        effect = "stop"
    elif analog_ids:
        status = "stop"
        reason = "analog_as_exact"
        effect = "stop"
    elif false_rescue_ids:
        status = "stop"
        reason = "false_rescue_mechanism"
        effect = "stop"
    elif overclaim_ids:
        status = "stop"
        reason = "observed_overclaim"
        effect = "stop"
    elif not falsifier_ids:
        status = "stop"
        reason = "no_falsifier"
        effect = "stop"
    elif not alternative_ids:
        status = "stop"
        reason = "no_alternative"
        effect = "stop"
    elif not by_role["positive_control"] or not by_role["negative_control"]:
        status = "stop"
        reason = "no_controls"
        effect = "stop"
    # A multi-candidate program must predeclare its error-control rule.
    elif not multiplicity_ids:
        status = "stop"
        reason = "no_multiplicity"
        effect = "stop"
    # And it must predeclare an orthogonal counterscreen for probe artifacts.
    elif not counterscreen_ids:
        status = "stop"
        reason = "no_counterscreen"
        effect = "stop"
    # The evidence chain must be declared even while unknown — a table that
    # omits confirmation, phase, transcript, stability, and probe links
    # entirely cannot hide behind a weak declared strength.
    elif any(not by_role[role] for role in PAIR_PROGRAM_ROLES):
        status = "stop"
        reason = "incomplete_evidence_chain"
        effect = "stop"
    elif not kill_blobs:
        status = "stop"
        reason = "untestable_falsifier"
        effect = "stop"
    # The remaining falsifier floors apply only to blobs that are actual
    # conditional kill rules — a non-kill falsifier blob cannot donate the
    # endpoint, masquerade, predeclaration, or correction terms the real
    # kill rule is missing.
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_FALSIFIER_ENDPOINT_TERMS
        )
        for spaced, _ in kill_blobs
    ):
        status = "stop"
        reason = "falsifier_ignores_endpoint"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_FALSIFIER_ENDPOINT_TERMS
        )
        and any(
            _term_in(spaced, term) for term in _NORMALIZED_MASQUERADE_TERMS
        )
        for spaced, _ in kill_blobs
    ):
        status = "stop"
        reason = "falsifier_ignores_masquerade"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, term) for term in _NORMALIZED_MASQUERADE_TERMS
        )
        for spaced, _ in alternative_blobs
    ) or (
        len(
            {
                term
                for term in _NORMALIZED_MASQUERADE_TERMS
                if any(
                    _term_in(spaced, term) for spaced, _ in alternative_blobs
                )
            }
        )
        < MINIMUM_MASQUERADE_COVERAGE
    ):
        status = "stop"
        reason = "alternative_ignores_masquerade"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_FALSIFIER_ENDPOINT_TERMS
        )
        for spaced, _ in alternative_blobs
    ):
        status = "stop"
        reason = "alternative_ignores_endpoint"
        effect = "stop"
    # Every masquerade family an alternative names must be covered by a kill
    # rule — a named confounder no falsifier can kill is still alive.
    elif not all(
        {
            term
            for term in _NORMALIZED_MASQUERADE_TERMS
            if _term_in(spaced, term)
        }
        <= kill_masquerade_set
        for spaced, _ in alternative_blobs
    ):
        status = "stop"
        reason = "alternative_not_killable"
        effect = "stop"
    elif not all(
        any(
            any(
                _term_in(spaced, phrase)
                for phrase in _NORMALIZED_CONTROL_PARITY_PHRASES
            )
            for spaced, _ in control_blobs
        )
        for control_blobs in (positive_control_blobs, negative_control_blobs)
    ):
        status = "stop"
        reason = "controls_not_protocol_matched"
        effect = "stop"
    # Each control arm must be self-contained: the role term and the protocol
    # parity term must live in the same link, so a parity declaration cannot
    # drift onto a control row it does not describe.
    elif not all(
        any(
            _term_in(spaced, phrase)
            for phrase in _NORMALIZED_EXACT_CONTROL_PHRASES
        )
        and any(
            _term_in(spaced, phrase)
            for phrase in _NORMALIZED_CONTROL_PARITY_PHRASES
        )
        for spaced, _ in positive_control_blobs
    ):
        status = "stop"
        reason = "positive_control_not_exact"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, phrase)
            for phrase in _NORMALIZED_BASELINE_CONTROL_PHRASES
        )
        and any(
            _term_in(spaced, phrase)
            for phrase in _NORMALIZED_CONTROL_PARITY_PHRASES
        )
        for spaced, _ in negative_control_blobs
    ):
        status = "stop"
        reason = "negative_control_not_baseline"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_PREDECLARATION_TERMS
        )
        for spaced, _ in kill_blobs
    ):
        status = "stop"
        reason = "falsifier_not_predeclared"
        effect = "stop"
    # The multiplicity link must name a predeclared error-control rule —
    # a bare 'multiplicity' word without a method is not a rule.
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_MULTIPLICITY_TERMS
        )
        and any(
            _term_in(spaced, term)
            for term in _NORMALIZED_PREDECLARATION_TERMS
        )
        for spaced, _ in multiplicity_blobs
    ):
        status = "stop"
        reason = "multiplicity_without_rule"
        effect = "stop"
    # A predeclared error-control rule needs its numeric level — a named
    # method without an alpha or FDR bound is not a stopping rule.
    elif not all(
        _NUMERIC_BOUND.search(spaced) for spaced, _ in multiplicity_blobs
    ):
        status = "stop"
        reason = "multiplicity_without_alpha"
        effect = "stop"
    # At least one competing explanation must name the interference /
    # promiscuous-compound family — repurposing screens are confounded by
    # assay artifacts, not only by biology.
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_INTERFERENCE_TERMS
        )
        for spaced, _ in alternative_blobs
    ):
        status = "stop"
        reason = "alternative_ignores_interference"
        effect = "stop"
    # The counterscreen must be a real orthogonal assay aimed at the
    # interference family, not a bare role filler.
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_COUNTERSCREEN_TERMS
        )
        and any(
            _term_in(spaced, term)
            for term in _NORMALIZED_INTERFERENCE_TERMS
        )
        for spaced, _ in counterscreen_blobs
    ):
        status = "stop"
        reason = "counterscreen_without_assay"
        effect = "stop"
    elif not endpoint_blobs:
        status = "stop"
        reason = "no_endpoint"
        effect = "stop"
    # A kill rule must watch a real endpoint link by id — a falsifier that
    # cannot name the measurement it kills is bound to nothing.
    elif any(
        not watches or any(watch not in endpoint_ids for watch in watches)
        for watches in falsifier_watch_ids
    ):
        status = "stop"
        reason = "falsifier_watch_unresolved"
        effect = "stop"
    # Every declaration role must watch the links it depends on — a
    # structural reference graph, not a bag of lexical statements.
    elif any(
        role in WATCH_TARGETS
        and (
            not watches
            or any(watch not in role_by_id for watch in watches)
            or not any(
                role_by_id.get(watch) in WATCH_TARGETS[role]
                for watch in watches
            )
        )
        for _, role, watches in link_watches
    ):
        status = "stop"
        reason = "watch_unresolved"
        effect = "stop"
    # The watch graph must be acyclic — a dependency loop means no link is
    # grounded in a base observation.
    elif _watch_graph_has_cycle(link_watches):
        status = "stop"
        reason = "watch_cycle"
        effect = "stop"
    # Reverse coverage: every endpoint must be killed by a falsifier and
    # bounded by both control arms; every probe must be counterscreened.
    elif any(
        not any(
            endpoint_id in watches for watches in falsifier_watch_ids
        )
        for endpoint_id in endpoint_ids
    ):
        status = "stop"
        reason = "endpoint_unkilled"
        effect = "stop"
    elif any(
        not any(
            endpoint_id in watches
            for _, role, watches in link_watches
            if role == "positive_control"
        )
        or not any(
            endpoint_id in watches
            for _, role, watches in link_watches
            if role == "negative_control"
        )
        for endpoint_id in endpoint_ids
    ):
        status = "stop"
        reason = "endpoint_uncontrolled"
        effect = "stop"
    elif any(
        not any(
            probe_id in watches
            for _, role, watches in link_watches
            if role == "counterscreen"
        )
        for probe_id in probe_ids
    ):
        status = "stop"
        reason = "probe_unscreened"
        effect = "stop"
    # The multiplicity rule must cover the entire family — every probe and
    # every endpoint — not just the members that happen to pass.
    elif any(
        any(
            member not in watches
            for member in probe_ids | endpoint_ids
        )
        or not (probe_ids | endpoint_ids)
        for _, role, watches in link_watches
        if role == "multiplicity"
    ) or not any(
        role == "multiplicity" for _, role, _ in link_watches
    ):
        status = "stop"
        reason = "multiplicity_family_uncovered"
        effect = "stop"
    elif endpoint_blobs and not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_ENDPOINT_DIRECTION_TERMS
        )
        and any(
            _term_in(spaced, term)
            for term in _NORMALIZED_ENDPOINT_COMPARATOR_TERMS
        )
        for spaced, _ in endpoint_blobs
    ):
        status = "stop"
        reason = "endpoint_without_direction"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_EXACT_CONTROL_PHRASES
        )
        for spaced, _ in endpoint_blobs
    ):
        status = "stop"
        reason = "endpoint_without_exact_comparator"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_ENDPOINT_LINEAGE_TERMS
        )
        for spaced, _ in endpoint_blobs
    ):
        status = "stop"
        reason = "endpoint_not_lineage_tracked"
        effect = "stop"
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_EXACT_CONTROL_PHRASES
        )
        for spaced, _ in kill_blobs
    ):
        status = "stop"
        reason = "falsifier_ignores_correction"
        effect = "stop"
    elif pair_blobs and not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_PAIR_CONFIGURATION_TERMS
        )
        for spaced, _ in pair_blobs
    ):
        status = "stop"
        reason = "pair_without_configuration"
        effect = "stop"
    elif stability_blobs and not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_STABILITY_PROPERTY_TERMS
        )
        for spaced, _ in stability_blobs
    ):
        status = "stop"
        reason = "stability_without_property"
        effect = "stop"
    elif transcript_blobs and not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_TRANSCRIPT_MEASURAND_TERMS
        )
        for spaced, _ in transcript_blobs
    ):
        status = "stop"
        reason = "transcript_without_measurand"
        effect = "stop"
    elif probe_blobs and not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_PROBE_MECHANISM_TERMS
        )
        for spaced, _ in probe_blobs
    ):
        status = "stop"
        reason = "probe_without_mechanism"
        effect = "stop"
    elif unbound_roles:
        status = "stop"
        reason = "observed_without_gate"
        effect = "stop"
    elif declared == "conditional_ex_vivo" and child_claim_strength != "conditional_ex_vivo":
        status = "stop"
        reason = "declared_overstrong"
        effect = "stop"
    elif _rank(declared) > _rank(work_ceiling):
        status = "stop"
        reason = "declared_overstrong"
        effect = "stop"
    # Under-declaration is a mismatch too: a payload cannot claim 'unsupported'
    # while its observed links imply a higher ceiling — the declaration must
    # match what the evidence actually supports.
    # Under-declaration is a mismatch too: the declaration may not fall below
    # the participant-claim level (child_claim_strength). The isogenic path
    # may legitimately outrank it via work_ceiling without forcing the
    # declaration upward.
    elif _rank(declared) < _rank(child_claim_strength):
        status = "stop"
        reason = "declared_understrong"
        effect = "stop"
    # Boundary check sits last: a kill rule that survives every other floor
    # must still name a measurable reference (baseline, threshold, fold...)
    # so the stop condition is quantitative, not a bare 'stops'.
    elif not all(
        any(
            _term_in(spaced, term)
            for term in _NORMALIZED_FALSIFIER_BOUNDARY_TERMS
        )
        for spaced, _ in kill_blobs
    ):
        status = "stop"
        reason = "falsifier_without_boundary"
        effect = "stop"
    # A qualitative boundary alone is not a kill rule: the stop condition
    # must carry an explicit numeric bound or percent so the threshold is
    # actually falsifiable.
    elif not all(
        _NUMERIC_BOUND.search(spaced) for spaced, _ in kill_blobs
    ):
        status = "stop"
        reason = "falsifier_without_numeric_bound"
        effect = "stop"
    # The kill bound must be anchored to a bound the endpoint declares —
    # a falsifier number that no endpoint measures is a floating threshold.
    elif not all(
        set(re.findall(r"\d+", spaced)) & endpoint_digit_set
        for spaced, _ in kill_blobs
    ):
        status = "stop"
        reason = "falsifier_bound_unanchored"
        effect = "stop"
    # And the declared bound must equal the watched endpoint's rescue_bound
    # by value — structural equality, not lexical overlap.
    elif endpoint_spec_bad:
        status = "stop"
        reason = "endpoint_without_spec"
        effect = "stop"
    elif not all(
        bound is not None
        and any(
            endpoint_specs.get(watch) == bound
            for watch in watches
        )
        for (_, bound), watches in zip(
            falsifier_bounds, falsifier_watch_ids, strict=True
        )
    ):
        status = "stop"
        reason = "falsifier_bound_unequal"
        effect = "stop"
    else:
        status = "pass"
        reason = "weakest_link_respected"
        effect = "pass"

    result = {
        "schema": SCHEMA,
        "gate": "hypothesis",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "gate_claim_boundary": GATE_CLAIM,
        # Binds this receipt to the exact evidence table it was computed on —
        # a hypothesis receipt farmed on different links cannot be replayed
        # against this payload downstream.
        "evidence_sha256": _receipt_or_raise(payload),
        "status": status,
        "program_effect": effect,
        "reason": reason,
        "declared_overall_strength": declared,
        "declared_probe_is_medicine": medicine,
        "confirmation_strength": confirmation_strength,
        "pair_strength": pair_strength,
        "transcript_strength": transcript_strength,
        "stability_strength": stability_strength,
        "probe_link_strength": probe_link_strength,
        "isogenic_probe_strength": isogenic_probe_strength,
        "pair_program_strength": pair_program_strength,
        "child_claim_strength": child_claim_strength,
        "work_ceiling": work_ceiling,
        "analog_ids": analog_ids,
        "false_rescue_ids": false_rescue_ids,
        "overclaim_ids": overclaim_ids,
        "falsifier_ids": falsifier_ids,
        "falsified_ids": falsified_ids,
        "alternative_ids": alternative_ids,
        "alternative_observed_ids": alternative_observed_ids,
        "control_ids": control_ids,
        "failed_control_ids": failed_control_ids,
        "unbound_roles": unbound_roles,
        "medicine_claim": medicine,
    }
    result["receipt_sha256"] = _receipt_or_raise(result)
    return result


__all__ = [
    "ANALOG_PHRASES",
    "CLAIM_BOUNDARY",
    "CONTROL_FAIL_PHRASES",
    "CONTROL_ROLES",
    "FALSE_RESCUE_PHRASES",
    "GATE_BIND_ROLES",
    "GATE_BIND_SCHEMAS",
    "HYPOTHESIS_ROLES",
    "IDENTITY_BIND_ROLES",
    "PAIR_PROGRAM_ROLES",
    "SCHEMA",
    "STRENGTHS",
    "HypothesisStrengthError",
    "assess_hypothesis_strength",
]
