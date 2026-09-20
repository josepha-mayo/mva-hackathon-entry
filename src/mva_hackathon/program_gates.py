"""Fail-closed program gates for phase, hypomorph eligibility, and replication.

These gates consume identifier-free community handoffs. They do not call
phase, do not measure protein function, and do not assert efficacy. A ticked
boolean cannot advance a program when nested contracts have not passed, and
concordance is counted from lineage tables rather than believed from a tick.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from mva_hackathon.provenance import receipt_sha256, receipt_sha256_ok

from mva_hackathon.allele_confirmation import (
    DEFAULT_EXPECTED_N_FILES,
    PINNED_FASTQ_NAME_DIGEST,
    SCHEMA as KMER_SCHEMA,
)
from mva_hackathon.allocation_inference import (
    assess_constrained_randomization_inference,
)
from mva_hackathon.clone_safety import LINEAGE_COUNTS_SCHEMA, SCHEMA as CLONE_SAFETY_SCHEMA
from mva_hackathon.exposure_gate import (
    SCHEMA as EXPOSURE_SCHEMA,
    ExposureGateError,
    assess_exposure_execution_binding,
)
from mva_hackathon.lineage import (
    MINIMUM_EDIT_EVENTS,
    default_completion_band,
    lineage_source_fingerprint,
)
from mva_hackathon.phase_monte_carlo import (
    MINIMUM_PHASE_FLOOR,
    assess_phase_split,
)


PHASE_SCHEMA = "mva.community-phase-record/v1"
SCORECARD_SCHEMA = "mva.community-allele-function-scorecard/v1"
REPLICATION_SCHEMA = "mva.community-replication-decision/v1"
BLINDED_SCHEMA = "mva.community-blinded-count-table/v2"
PROGRAM_SCHEMA = "mva-track2-program-gates/v1"
COMPETING_RISK_RATIO = 1.25
DAUGHTERS_PER_DIVISION = 2
MAX_DAUGHTERS_PER_DIVISION = 4
MINIMUM_CLONES_PER_EVENT = 2
# Input-size ceilings — a toolkit file can declare far more rows than any
# real experiment; iterating an attacker-bounded list must stay cheap.
MAX_GATE_ROWS = 500_000
MAX_GATE_ITEMS = 10_000
PHASE_DECISIONS = ("trans_confirmed", "cis_confirmed", "unresolved")
LINKAGE_CALLS = ("trans", "cis", "unresolved")
PHASE_METHODS = (
    "molecule_spanning",
    "parental",
    "computational",
    "rna",
    "unlabeled",
)
PHASE_METHOD_STOP_REASONS = frozenset(
    {
        "computational_phase_not_molecule",
        "rna_phase_not_genomic",
        "phase_method_required",
    }
)
PHASE_SPECIMENS = (
    "assay_matched",
    "parental",
    "unmatched",
    "unlabeled",
)
PHASE_SPECIMEN_STOP_REASONS = frozenset(
    {
        "unmatched_phase_specimen",
        "phase_specimen_required",
    }
)
CONFIRMATION_SCHEMA = "mva.community-confirmation-record/v1"
CONFIRMATION_STATUSES = (
    "both_alleles_observed",
    "alternate_not_observed",
    "reference_not_observed",
    "neither_observed",
    "insufficient_observations",
    "incomplete_inputs",
    "malformed_allele",
)
CONFIRMATION_PRODUCERS = ("kmer_layout", "synthetic_handoff", "unlinked")
LIBRARY_MOLECULES = ("genomic", "rna", "unlabeled")
LIBRARY_MOLECULE_STOP_REASONS = frozenset(
    {"rna_not_genomic", "library_molecule_required"}
)
CONFIRMATION_SPECIMENS = (
    "assay_matched",
    "unmatched",
    "unlabeled",
)
CONFIRMATION_SPECIMEN_STOP_REASONS = frozenset(
    {
        "unmatched_confirmation_specimen",
        "confirmation_specimen_required",
    }
)
TRANSCRIPT_SCHEMA = "mva.community-transcript-record/v1"
STOP_RNA_STATES = ("deplete", "persist", "truncated_product", "not_assessable")
MISSENSE_RNA_STATES = ("expressed", "not_expressed", "not_assessable")
TRANSCRIPT_STATUSES = (
    "stop_depleted_missense_expressed",
    "missense_not_expressed",
    "truncated_product_revises_model",
    "stop_transcript_persists",
    "transcript_not_measured",
)
TRANSCRIPT_METHODS = (
    "allele_specific",
    "computational",
    "protein_surrogate",
    "unlabeled",
)
TRANSCRIPT_METHOD_STOP_REASONS = frozenset(
    {
        "computational_transcript_not_assay",
        "protein_not_transcript",
        "transcript_method_required",
    }
)
TRANSCRIPT_SPECIMENS = (
    "assay_matched",
    "unmatched",
    "unlabeled",
)
TRANSCRIPT_SPECIMEN_STOP_REASONS = frozenset(
    {
        "unmatched_transcript_specimen",
        "transcript_specimen_required",
    }
)
SITE_DECISIONS = ("hold", "advance", "stop")
STATUSES = ("pass", "stop", "not_assessable", "hold")
GENOTYPE_CLASSES = (
    "wt",
    "missense",
    "stop",
    "missense_carrier",
    "missense_at_abundance",
    "compound",
    "exact_corrected",
    "recreated_missense",
)
STABILITY_ENDPOINTS = ("abundance", "half_life")
FUNCTION_IDENTITY_ENDPOINTS = (
    "abundance",
    "half_life",
    "localization",
    "checkpoint",
    "first_division_error",
)
# The carrier dose-control and function-at-abundance comparisons only make
# sense on function axes: a heterozygote is *expected* to differ on abundance
# (one WT allele), so a stability-endpoint difference is the definition of a
# carrier, not dominant interference. Dominant interference — and a protein
# that stays broken when its abundance is normalized — are function readouts.
FUNCTION_AXES_ENDPOINTS = ("localization", "checkpoint", "first_division_error")
PD_ENDPOINTS = ("chaperone_pd", "aneuploidy_stress")
ALLELE_SPECIFICITIES = ("exact", "analog", "homolog", "nearby")
ASSAY_CLASSES = (
    "wet",
    "computational_structure",
    "computational_pathogenicity",
    "unlabeled",
)
COMPUTATIONAL_ASSAY_CLASSES = ("computational_structure", "computational_pathogenicity")
CONDITION_CLASSES = ("basal", "imposed_extrinsic_stress", "unlabeled")
SYSTEM_CLASSES = ("cellular", "cell_free_biophysical", "unlabeled")
EXPRESSION_CLASSES = ("endogenous", "ectopic", "unlabeled")
FUNCTION_SPECIMENS = ("assay_matched", "unmatched", "unlabeled")
FUNCTION_SPECIMEN_STOP_REASONS = frozenset(
    {
        "unmatched_not_assay_matched_defect",
        "specimen_class_required",
        "recreation_unmatched_not_assay_matched",
        "recreation_specimen_class_required",
        "unmatched_correction_not_assay_matched",
        "unlabeled_correction_specimen_class",
    }
)
IDENTITY_KEY_FIELDS = ("edit_event_id", "clone_id", "run_id")
IDENTITY_FIELDS = (
    "opportunities",
    "detected_divisions",
    "event_positive_divisions",
    "event_negative_divisions",
    "event_positive_daughters_followed",
    "event_positive_daughters_reproduced",
    "event_positive_daughters_died",
    "event_negative_daughters_followed",
    "event_negative_daughters_reproduced",
    "event_negative_daughters_died",
    "pre_division_death",
    "no_division",
    "dropout_censored",
)
OPTIONAL_IDENTITY_FIELDS = (
    "event_positive_daughter_slots",
    "event_negative_daughter_slots",
    "event_positive_multipolar_divisions",
)
HYPOTHESIS_SCHEMA = "mva-track2-hypothesis-strength/v1"
CLAIM_BOUNDARY = (
    "Program-gate software contract only; filled templates are not wet-lab "
    "results; a boolean tick is not a pass; this is not efficacy evidence."
)


class ProgramGateError(ValueError):
    """Raised when a program-gate input violates its contract."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProgramGateError(f"{label} must be an object")
    return value


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ProgramGateError(f"{field} must be a boolean")
    return value


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProgramGateError(f"{field} must be non-empty text")
    return value


def _kmer_nested_ok(payload: Mapping[str, Any]) -> tuple[bool, str]:
    nested = payload.get("kmer_confirmation")
    if not isinstance(nested, Mapping) or nested.get("schema") != KMER_SCHEMA:
        return False, "kmer_producer_missing"
    if _bool(
        nested.get("incomplete_inputs"), "kmer_confirmation.incomplete_inputs"
    ):
        return False, "kmer_inputs_incomplete"
    if nested.get("reverse_complement_counted") is not True:
        return False, "strands_not_counted"
    alleles = nested.get("alleles")
    if not isinstance(alleles, list) or len(alleles) < 2:
        return False, "need_two_kmer_alleles"
    if len(alleles) > MAX_GATE_ITEMS:
        return False, "too_many_kmer_alleles"
    for row in alleles:
        if not isinstance(row, Mapping) or row.get("status") != "both_alleles_observed":
            return False, "kmer_alleles_not_both_observed"
        by_k = row.get("by_k")
        if not isinstance(by_k, list):
            return False, "kmer_k_not_both_observed"
        statuses = {
            item.get("k"): item.get("status")
            for item in by_k
            if isinstance(item, Mapping)
        }
        if statuses.get(31) != "both_alleles_observed" or statuses.get(51) != "both_alleles_observed":
            return False, "kmer_k_not_both_observed"
    layout = payload.get("layout")
    if not isinstance(layout, Mapping):
        nested_layout = nested.get("layout") if isinstance(nested, Mapping) else None
        layout = nested_layout if isinstance(nested_layout, Mapping) else None
    if not isinstance(layout, Mapping):
        return False, "kmer_layout_missing"
    if layout.get("incomplete") is not False:
        return False, "layout_incomplete"
    n_files = layout.get("n_files")
    expected = layout.get("expected_n_files", DEFAULT_EXPECTED_N_FILES)
    if (
        not isinstance(n_files, int)
        or isinstance(n_files, bool)
        or not isinstance(expected, int)
        or isinstance(expected, bool)
        or expected < DEFAULT_EXPECTED_N_FILES
        or n_files != expected
    ):
        return False, "layout_file_count"
    digest = layout.get("name_digest")
    pinned = payload.get("layout_digest")
    if digest is not None and digest != pinned:
        return False, "layout_digest_mismatch"
    return True, "confirmation_floors_met"


def assess_confirmation_gate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Orthogonal confirmation cannot be ticked. Incomplete inputs cannot pass.

    A declared both-alleles-observed call is a stop when layout, identity,
    aliquot, strand, allele floors, or genomic-library class are not met.
    An RNA or RNA-derived library cannot confirm genomic genotype. Unlabeled
    library class cannot stand in. Genomic DNA from an unmatched genotype
    line cannot stand in for the confirmed assay line. Unlabeled confirmation
    specimen cannot stand in. This is not a variant caller and not a child's
    confirmation.
    """

    payload = _mapping(record, "confirmation record")
    if payload.get("schema") != CONFIRMATION_SCHEMA:
        raise ProgramGateError("confirmation gate accepts the community confirmation record only")
    declared = payload.get("declared_status")
    if declared not in CONFIRMATION_STATUSES:
        raise ProgramGateError("declared_status is not in the allowed vocabulary")
    identity = _bool(payload.get("specimen_identity_resolved"), "specimen_identity_resolved")
    aliquot = _bool(payload.get("second_aliquot"), "second_aliquot")
    layout = _bool(payload.get("layout_complete"), "layout_complete")
    strands = _bool(payload.get("both_strands_counted"), "both_strands_counted")
    producer = payload.get("producer", "unlinked")
    if producer not in CONFIRMATION_PRODUCERS:
        raise ProgramGateError("confirmation producer is not in the allowed vocabulary")
    library_molecule = payload.get("library_molecule", "unlabeled")
    if library_molecule not in LIBRARY_MOLECULES:
        raise ProgramGateError("library_molecule is not in the allowed vocabulary")
    confirmation_specimen = payload.get("confirmation_specimen", "unlabeled")
    if confirmation_specimen not in CONFIRMATION_SPECIMENS:
        raise ProgramGateError("confirmation_specimen is not in the allowed vocabulary")
    allele_1 = payload.get("allele_1_status")
    allele_2 = payload.get("allele_2_status")
    if allele_1 not in CONFIRMATION_STATUSES or allele_2 not in CONFIRMATION_STATUSES:
        raise ProgramGateError("allele confirmation status is not in the allowed vocabulary")

    if not layout:
        computed = "incomplete_inputs"
        reason = "layout_incomplete"
    elif not identity:
        computed = "incomplete_inputs"
        reason = "identity_unresolved"
    elif not aliquot:
        computed = "incomplete_inputs"
        reason = "second_aliquot_missing"
    elif not strands:
        computed = "incomplete_inputs"
        reason = "strands_not_counted"
    elif allele_1 != "both_alleles_observed" or allele_2 != "both_alleles_observed":
        computed = "insufficient_observations"
        reason = "alleles_not_both_observed"
    elif producer == "unlinked":
        computed = "incomplete_inputs"
        reason = "producer_unlinked"
    elif producer == "kmer_layout":
        if payload.get("layout_digest") != PINNED_FASTQ_NAME_DIGEST:
            computed = "incomplete_inputs"
            reason = "layout_digest_mismatch"
        else:
            nested_ok, nested_reason = _kmer_nested_ok(payload)
            if nested_ok:
                computed = "both_alleles_observed"
                reason = nested_reason
            else:
                computed = "incomplete_inputs"
                reason = nested_reason
    else:
        computed = "both_alleles_observed"
        reason = "confirmation_floors_met"

    if computed == "both_alleles_observed":
        if library_molecule == "rna":
            computed = "incomplete_inputs"
            reason = "rna_not_genomic"
        elif library_molecule == "unlabeled":
            computed = "incomplete_inputs"
            reason = "library_molecule_required"

    if computed == "both_alleles_observed":
        if confirmation_specimen == "unmatched":
            computed = "incomplete_inputs"
            reason = "unmatched_confirmation_specimen"
        elif confirmation_specimen == "unlabeled":
            computed = "incomplete_inputs"
            reason = "confirmation_specimen_required"

    if declared == "both_alleles_observed" and computed != "both_alleles_observed":
        status = "stop"
        effect = "stop"
        if (
            reason not in LIBRARY_MOLECULE_STOP_REASONS
            and reason not in CONFIRMATION_SPECIMEN_STOP_REASONS
        ):
            reason = "declared_overstrong"
    elif computed == "both_alleles_observed" and declared == "both_alleles_observed":
        status = "pass"
        effect = "pass"
    else:
        status = "not_assessable"
        effect = "hold"
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "confirmation",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "declared_status": declared,
        "computed_status": computed,
        "declared_overridden": computed != declared,
        "status": status,
        "program_effect": effect,
        "reason": reason,
        "specimen_identity_resolved": identity,
        "second_aliquot": aliquot,
        "layout_complete": layout,
        "both_strands_counted": strands,
        "producer": producer,
        "library_molecule": library_molecule,
        "confirmation_specimen": confirmation_specimen,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def assess_phase_gate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Override a trans call when molecule floors or linkage agreement fail.

    Cis stops the pair story only when independent guide configurations agree
    on cis. A trans tick without recorded, agreeing haplotype linkage cannot
    pass. A computational haplotype caller or an RNA-seq phase cannot stand in
    for spanning molecules or parental genotypes. Unlabeled phase method
    cannot stand in. Spanning molecules from an unmatched genotype line
    cannot stand in for the confirmed assay line. Unlabeled phase specimen
    cannot stand in. Parental genotypes may still pass when the specimen is
    parental.
    """

    payload = _mapping(record, "phase record")
    if payload.get("schema") != PHASE_SCHEMA:
        raise ProgramGateError("phase gate accepts the community phase record only")
    declared = payload.get("decision")
    if declared not in PHASE_DECISIONS:
        raise ProgramGateError("phase decision is not in the allowed vocabulary")
    phase_method = payload.get("phase_method", "unlabeled")
    if phase_method not in PHASE_METHODS:
        raise ProgramGateError("phase_method is not in the allowed vocabulary")
    phase_specimen = payload.get("phase_specimen", "unlabeled")
    if phase_specimen not in PHASE_SPECIMENS:
        raise ProgramGateError("phase_specimen is not in the allowed vocabulary")
    counts = _mapping(payload.get("molecule_counts"), "molecule_counts")
    minimum = counts.get("minimum_full_span_per_haplotype")
    hap_a = counts.get("haplotype_a_full_span")
    hap_b = counts.get("haplotype_b_full_span")
    if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (minimum, hap_a, hap_b)):
        raise ProgramGateError("molecule counts must be non-negative integers")
    if minimum < MINIMUM_PHASE_FLOOR:
        raise ProgramGateError(
            "molecule floor cannot drop below the declared protocol floor"
        )
    guides = payload.get("guide_configurations")
    config_ids: list[str] = []
    linkage_calls: list[str] = []
    guide_spans: list[int] = []
    strand_balances: list[float] = []
    if isinstance(guides, list) and len(guides) > MAX_GATE_ITEMS:
        guides = []
    if isinstance(guides, list):
        for item in guides:
            if not isinstance(item, Mapping):
                config_ids = []
                linkage_calls = []
                guide_spans = []
                strand_balances = []
                break
            config_id = item.get("config_id")
            linkage = item.get("linkage_call")
            span = item.get("full_span_molecules")
            strand = item.get("strand_balance")
            if not isinstance(config_id, str) or not config_id:
                config_ids = []
                linkage_calls = []
                guide_spans = []
                strand_balances = []
                break
            if not isinstance(span, int) or isinstance(span, bool) or span < 0:
                config_ids = []
                linkage_calls = []
                guide_spans = []
                strand_balances = []
                break
            if isinstance(strand, bool) or not isinstance(strand, (int, float)):
                config_ids = []
                linkage_calls = []
                guide_spans = []
                strand_balances = []
                break
            config_ids.append(config_id)
            guide_spans.append(span)
            strand_balances.append(float(strand))
            if linkage not in LINKAGE_CALLS:
                linkage_calls.append("")
            else:
                linkage_calls.append(str(linkage))
    unique_linkage = {call for call in linkage_calls if call}
    if len(config_ids) < 2:
        computed = "unresolved"
        reason = "need_two_guide_configurations"
    elif len(set(config_ids)) < 2:
        computed = "unresolved"
        reason = "duplicate_guide_configurations"
    elif len(linkage_calls) != len(config_ids) or any(call == "" for call in linkage_calls):
        computed = "unresolved"
        reason = "linkage_not_recorded"
    elif hap_a < minimum or hap_b < minimum:
        computed = "unresolved"
        reason = "allelic_dropout_floor"
    elif any(span < minimum for span in guide_spans):
        computed = "unresolved"
        reason = "guide_span_floor"
    elif unique_linkage == {"cis"}:
        computed = "cis_confirmed"
        reason = "linkage_agreed_cis"
    elif unique_linkage == {"trans"} and declared == "trans_confirmed":
        split = assess_phase_split(hap_a, hap_b, minimum, strand_balances)
        if split["strand_ok"] and split["dropout_rejected"]:
            computed = "trans_confirmed"
            reason = "linkage_agreed_trans"
        else:
            computed = "unresolved"
            reason = str(split["reason"])
    elif unique_linkage == {"trans"}:
        computed = "unresolved"
        reason = "declared_linkage_mismatch"
    else:
        computed = "unresolved"
        reason = "linkage_disagreement"

    if computed == "trans_confirmed":
        if phase_method == "computational":
            computed = "unresolved"
            reason = "computational_phase_not_molecule"
        elif phase_method == "rna":
            computed = "unresolved"
            reason = "rna_phase_not_genomic"
        elif phase_method == "unlabeled":
            computed = "unresolved"
            reason = "phase_method_required"

    if computed == "trans_confirmed":
        if phase_specimen == "unmatched":
            computed = "unresolved"
            reason = "unmatched_phase_specimen"
        elif phase_specimen == "unlabeled":
            computed = "unresolved"
            reason = "phase_specimen_required"
        elif phase_method == "parental" and phase_specimen != "parental":
            computed = "unresolved"
            reason = "unmatched_phase_specimen"
        elif phase_method == "molecule_spanning" and phase_specimen != "assay_matched":
            computed = "unresolved"
            reason = "unmatched_phase_specimen"

    if computed == "cis_confirmed":
        status = "stop"
        program = "stop"
    elif computed == "trans_confirmed":
        status = "pass"
        program = "pass"
    elif reason in PHASE_METHOD_STOP_REASONS or reason in PHASE_SPECIMEN_STOP_REASONS:
        status = "stop"
        program = "stop"
    else:
        status = "not_assessable"
        program = "hold"
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "phase",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "declared_decision": declared,
        "computed_decision": computed,
        "declared_overridden": computed != declared,
        "status": status,
        "program_effect": program,
        "reason": reason,
        "haplotype_a_full_span": hap_a,
        "haplotype_b_full_span": hap_b,
        "minimum_full_span_per_haplotype": minimum,
        "linkage_calls": linkage_calls,
        "guide_spans": guide_spans,
        "phase_method": phase_method,
        "phase_specimen": phase_specimen,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def assess_transcript_gate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Stop-class RNA fate must be measured before a missense abundance assay.

    Depleted stop transcript plus expressed missense can open the missense
    protein assays. An unmeasured transcript cannot. A computational NMD
    predictor or a protein-surrogate row cannot stand in for allele-specific
    RNA. Unlabeled transcript method cannot stand in. Allele-specific RNA
    from an unmatched genotype line cannot stand in for the confirmed assay
    line. Unlabeled transcript specimen cannot stand in. This is not a ddPCR
    result and not efficacy evidence.
    """

    payload = _mapping(record, "transcript record")
    if payload.get("schema") != TRANSCRIPT_SCHEMA:
        raise ProgramGateError("transcript gate accepts the community transcript record only")
    declared = payload.get("declared_status")
    if declared not in TRANSCRIPT_STATUSES:
        raise ProgramGateError("declared_status is not in the allowed vocabulary")
    stop_rna = payload.get("stop_allele_rna")
    missense_rna = payload.get("missense_allele_rna")
    if stop_rna not in STOP_RNA_STATES:
        raise ProgramGateError("stop_allele_rna is not in the allowed vocabulary")
    if missense_rna not in MISSENSE_RNA_STATES:
        raise ProgramGateError("missense_allele_rna is not in the allowed vocabulary")
    transcript_method = payload.get("transcript_method", "unlabeled")
    if transcript_method not in TRANSCRIPT_METHODS:
        raise ProgramGateError("transcript_method is not in the allowed vocabulary")
    transcript_specimen = payload.get("transcript_specimen", "unlabeled")
    if transcript_specimen not in TRANSCRIPT_SPECIMENS:
        raise ProgramGateError("transcript_specimen is not in the allowed vocabulary")

    if stop_rna == "not_assessable" or missense_rna == "not_assessable":
        computed = "transcript_not_measured"
        reason = "transcript_not_measured"
    elif missense_rna == "not_expressed":
        computed = "missense_not_expressed"
        reason = "missense_not_expressed"
    elif stop_rna == "truncated_product":
        computed = "truncated_product_revises_model"
        reason = "truncated_product_revises_model"
    elif stop_rna == "persist":
        computed = "stop_transcript_persists"
        reason = "stop_transcript_persists"
    else:
        computed = "stop_depleted_missense_expressed"
        reason = "stop_depleted_missense_expressed"

    if computed == "stop_depleted_missense_expressed":
        if transcript_method == "computational":
            computed = "transcript_not_measured"
            reason = "computational_transcript_not_assay"
        elif transcript_method == "protein_surrogate":
            computed = "transcript_not_measured"
            reason = "protein_not_transcript"
        elif transcript_method == "unlabeled":
            computed = "transcript_not_measured"
            reason = "transcript_method_required"

    if computed == "stop_depleted_missense_expressed":
        if transcript_specimen == "unmatched":
            computed = "transcript_not_measured"
            reason = "unmatched_transcript_specimen"
        elif transcript_specimen == "unlabeled":
            computed = "transcript_not_measured"
            reason = "transcript_specimen_required"

    if declared == "stop_depleted_missense_expressed" and computed != declared:
        status = "stop"
        effect = "stop"
        if (
            reason not in TRANSCRIPT_METHOD_STOP_REASONS
            and reason not in TRANSCRIPT_SPECIMEN_STOP_REASONS
        ):
            reason = "declared_overstrong"
    elif computed == "stop_depleted_missense_expressed" and declared == computed:
        status = "pass"
        effect = "pass"
    elif computed == "missense_not_expressed":
        status = "stop"
        effect = "stop"
    else:
        status = "not_assessable"
        effect = "hold"
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "transcript",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "declared_status": declared,
        "computed_status": computed,
        "declared_overridden": computed != declared,
        "status": status,
        "program_effect": effect,
        "reason": reason,
        "stop_allele_rna": stop_rna,
        "missense_allele_rna": missense_rna,
        "transcript_method": transcript_method,
        "transcript_specimen": transcript_specimen,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def _row_by_class(rows: list[Any], genotype_class: str) -> Mapping[str, Any]:
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("genotype_class") == genotype_class
    ]
    if len(matches) != 1:
        raise ProgramGateError(f"scorecard must contain exactly one {genotype_class} row")
    return matches[0]


def _endpoint_assessment(row: Mapping[str, Any], endpoint: str) -> Mapping[str, Any]:
    assessments = row.get("assessments")
    if not isinstance(assessments, list):
        raise ProgramGateError("assessments must be a list")
    matches = [
        item
        for item in assessments
        if isinstance(item, Mapping) and item.get("endpoint") == endpoint
    ]
    if len(matches) != 1:
        raise ProgramGateError(f"row is missing endpoint {endpoint}")
    return matches[0]


def _endpoint_status(row: Mapping[str, Any], endpoint: str) -> str:
    status = _endpoint_assessment(row, endpoint).get("assessment_status")
    if status not in {"positive", "negative", "not_assessable"}:
        raise ProgramGateError("assessment_status is not in the allowed vocabulary")
    return str(status)


def _optional_endpoint_status(row: Mapping[str, Any], endpoint: str) -> str | None:
    assessments = row.get("assessments")
    if not isinstance(assessments, list):
        return None
    matches = [
        item
        for item in assessments
        if isinstance(item, Mapping) and item.get("endpoint") == endpoint
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ProgramGateError(f"row has duplicate endpoint {endpoint}")
    status = matches[0].get("assessment_status")
    if status not in {"positive", "negative", "not_assessable"}:
        raise ProgramGateError("assessment_status is not in the allowed vocabulary")
    return str(status)


def _assay_class(item: Mapping[str, Any]) -> str:
    assay_class = item.get("assay_class", "unlabeled")
    if assay_class not in ASSAY_CLASSES:
        raise ProgramGateError("assay_class is not in the allowed vocabulary")
    return str(assay_class)


def _condition_class(item: Mapping[str, Any]) -> str:
    condition_class = item.get("condition_class", "unlabeled")
    if condition_class not in CONDITION_CLASSES:
        raise ProgramGateError("condition_class is not in the allowed vocabulary")
    return str(condition_class)


def _system_class(item: Mapping[str, Any]) -> str:
    system_class = item.get("system_class", "unlabeled")
    if system_class not in SYSTEM_CLASSES:
        raise ProgramGateError("system_class is not in the allowed vocabulary")
    return str(system_class)


def _expression_class(item: Mapping[str, Any]) -> str:
    expression_class = item.get("expression_class", "unlabeled")
    if expression_class not in EXPRESSION_CLASSES:
        raise ProgramGateError("expression_class is not in the allowed vocabulary")
    return str(expression_class)


def _specimen_class(item: Mapping[str, Any]) -> str:
    specimen_class = item.get("specimen_class", "unlabeled")
    if specimen_class not in FUNCTION_SPECIMENS:
        raise ProgramGateError("specimen_class is not in the allowed vocabulary")
    return str(specimen_class)


def _basal_cellular_matched(item: Mapping[str, Any]) -> bool:
    """All five assay classes carry the interpretable wet/basal/cellular
    /endogenous/assay-matched labels. Anything else cannot be read as a
    basal cellular endpoint call."""
    return (
        _assay_class(item) == "wet"
        and _condition_class(item) == "basal"
        and _system_class(item) == "cellular"
        and _expression_class(item) == "endogenous"
        and _specimen_class(item) == "assay_matched"
    )


def _abundance_row_interpretable(item: Mapping[str, Any]) -> bool:
    """The abundance-normalized construct is a titrated-expression assay:
    wet, basal, cellular, assay-matched, with a *declared* expression class
    (ectopic titration or endogenous activation both normalize abundance —
    only the unlabeled case is uninterpretable)."""
    return (
        _assay_class(item) == "wet"
        and _condition_class(item) == "basal"
        and _system_class(item) == "cellular"
        and _expression_class(item) in ("endogenous", "ectopic")
        and _specimen_class(item) == "assay_matched"
    )


def _specimen_problems(
    row: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """A positive function call must come from the confirmed assay line."""

    unmatched: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(row, endpoint) != "positive":
            continue
        specimen_class = _specimen_class(_endpoint_assessment(row, endpoint))
        if specimen_class == "unmatched":
            unmatched.append(str(endpoint))
        elif specimen_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return unmatched, unlabeled


def _condition_problems(
    row: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """A positive function call must declare basal versus imposed stress."""

    imposed: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(row, endpoint) != "positive":
            continue
        condition_class = _condition_class(_endpoint_assessment(row, endpoint))
        if condition_class == "imposed_extrinsic_stress":
            imposed.append(str(endpoint))
        elif condition_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return imposed, unlabeled


def _system_problems(
    row: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """A positive function call must be cellular, not cell-free biophysical."""

    cell_free: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(row, endpoint) != "positive":
            continue
        system_class = _system_class(_endpoint_assessment(row, endpoint))
        if system_class == "cell_free_biophysical":
            cell_free.append(str(endpoint))
        elif system_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return cell_free, unlabeled


def _expression_problems(
    row: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """A positive function call must be endogenous, not an ectopic transgene."""

    ectopic: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(row, endpoint) != "positive":
            continue
        expression_class = _expression_class(_endpoint_assessment(row, endpoint))
        if expression_class == "ectopic":
            ectopic.append(str(endpoint))
        elif expression_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return ectopic, unlabeled


def _positive_assay_problems(
    row: Mapping[str, Any], endpoints: tuple[str, ...]
) -> tuple[list[str], list[str]]:
    computational: list[str] = []
    unlabeled: list[str] = []
    assessments = row.get("assessments")
    if not isinstance(assessments, list):
        raise ProgramGateError("assessments must be a list")
    by_endpoint = {
        item.get("endpoint"): item
        for item in assessments
        if isinstance(item, Mapping)
    }
    for endpoint in endpoints:
        item = by_endpoint.get(endpoint)
        if not isinstance(item, Mapping):
            continue
        if item.get("assessment_status") != "positive":
            continue
        assay_class = _assay_class(item)
        if assay_class in COMPUTATIONAL_ASSAY_CLASSES:
            computational.append(str(endpoint))
        elif assay_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return computational, unlabeled


def _reversal_assay_problems(
    missense: Mapping[str, Any],
    corrected: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """A predicted correction cannot reverse a wet missense defect."""

    computational: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(missense, endpoint) != "positive":
            continue
        if _endpoint_status(corrected, endpoint) != "negative":
            continue
        assay_class = _assay_class(_endpoint_assessment(corrected, endpoint))
        if assay_class in COMPUTATIONAL_ASSAY_CLASSES:
            computational.append(str(endpoint))
        elif assay_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return computational, unlabeled


def _reversal_system_problems(
    missense: Mapping[str, Any],
    corrected: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """A cell-free correction cannot reverse a cellular missense defect."""

    cell_free: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(missense, endpoint) != "positive":
            continue
        if _endpoint_status(corrected, endpoint) != "negative":
            continue
        system_class = _system_class(_endpoint_assessment(corrected, endpoint))
        if system_class == "cell_free_biophysical":
            cell_free.append(str(endpoint))
        elif system_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return cell_free, unlabeled


def _reversal_condition_problems(
    missense: Mapping[str, Any],
    corrected: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """An imposed-stress correction cannot reverse a basal missense defect."""

    imposed: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(missense, endpoint) != "positive":
            continue
        if _endpoint_status(corrected, endpoint) != "negative":
            continue
        condition_class = _condition_class(_endpoint_assessment(corrected, endpoint))
        if condition_class == "imposed_extrinsic_stress":
            imposed.append(str(endpoint))
        elif condition_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return imposed, unlabeled


def _reversal_expression_problems(
    missense: Mapping[str, Any],
    corrected: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """An ectopic WT construct cannot reverse an endogenous missense defect."""

    ectopic: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(missense, endpoint) != "positive":
            continue
        if _endpoint_status(corrected, endpoint) != "negative":
            continue
        expression_class = _expression_class(_endpoint_assessment(corrected, endpoint))
        if expression_class == "ectopic":
            ectopic.append(str(endpoint))
        elif expression_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return ectopic, unlabeled


def _reversal_specimen_problems(
    missense: Mapping[str, Any],
    corrected: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """An unmatched-line correction cannot reverse an assay-matched missense defect."""

    unmatched: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(missense, endpoint) != "positive":
            continue
        if _endpoint_status(corrected, endpoint) != "negative":
            continue
        specimen_class = _specimen_class(_endpoint_assessment(corrected, endpoint))
        if specimen_class == "unmatched":
            unmatched.append(str(endpoint))
        elif specimen_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return unmatched, unlabeled


def _restoration_problems(
    missense: Mapping[str, Any],
    recreated: Mapping[str, Any],
    endpoints: tuple[str, ...],
) -> tuple[list[str], list[str], list[str]]:
    """Putting the missense back must restore every wet-positive defect."""

    failed: list[str] = []
    computational: list[str] = []
    unlabeled: list[str] = []
    for endpoint in endpoints:
        if _endpoint_status(missense, endpoint) != "positive":
            continue
        if _endpoint_status(recreated, endpoint) != "positive":
            failed.append(str(endpoint))
            continue
        assay_class = _assay_class(_endpoint_assessment(recreated, endpoint))
        if assay_class in COMPUTATIONAL_ASSAY_CLASSES:
            computational.append(str(endpoint))
        elif assay_class == "unlabeled":
            unlabeled.append(str(endpoint))
    return failed, computational, unlabeled


def assess_hypomorph_gate(scorecard: Mapping[str, Any]) -> dict[str, Any]:
    """A chaperone probe is eligible only after an exact missense stability defect.

    Analog, homolog, or nearby alleles cannot stand in for the exact missense.
    Exact correction must reverse every missense-positive function endpoint
    in a wet cellular basal endogenous assay. Reciprocal recreation must
    restore those same endpoints in a wet cellular assay. A computational,
    unlabeled, or cell-free corrected or recreated row cannot stand in. An
    imposed-stress or unlabeled correction cannot reverse a basal missense
    defect. An ectopic WT cDNA or unlabeled correction cannot reverse an
    endogenous missense defect. An unmatched-line or unlabeled correction
    cannot reverse an assay-matched missense defect. A missense-positive function call must be
    basal, not confined to imposed extrinsic stress. Unlabeled condition
    class cannot stand in. A missense-positive function call must be
    cellular. A cell-free biophysical row labeled wet cannot make a probe
    eligible. Unlabeled system class cannot stand in. A missense-positive
    function call must be endogenous. An ectopic transgene, cDNA, or
    overexpression row cannot make a probe eligible. Unlabeled expression
    class cannot stand in. A missense-positive function call must come from
    the confirmed assay line.     An unmatched genotype line cannot make a probe
    eligible. Unlabeled specimen class cannot stand in. An analog, homolog,
    or nearby recreation cannot restore an exact missense defect. Unlabeled
    recreation allele specificity cannot stand in. An analog, homolog,
    or nearby correction cannot reverse an exact missense defect. Unlabeled
    correction allele specificity cannot stand in. Checkpoint-ready is
    required later for
    replication advance, not for isogenic probe eligibility. Chaperone or
    stress-marker PD is not target engagement. Disease mitotic failure is
    not imposed extrinsic stress. Purified-protein thermal shift is not a
    cellular hypomorph and cannot satisfy genetic reversal. A missense-carrier
    function defect the truncation-carrier dose control does not share is
    dominant interference, not dose loss — stabilizing an interfering product
    is contraindicated, so the path stops. A carrier defect without a measured
    dose comparator, or a carrier defect call that is not a fully labeled
    basal cellular assay, cannot be interpreted and the path holds. A carrier
    defect the truncation carrier also shows is dose-consistent and does not
    by itself exclude the stabilization rationale.
    """

    payload = _mapping(scorecard, "scorecard")
    if payload.get("schema") != SCORECARD_SCHEMA:
        raise ProgramGateError("hypomorph gate accepts the community scorecard only")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ProgramGateError("scorecard has no rows")
    if len(rows) > MAX_GATE_ROWS:
        raise ProgramGateError("scorecard exceeds the row ceiling")
    classes = {row.get("genotype_class") for row in rows if isinstance(row, Mapping)}
    missing = [name for name in GENOTYPE_CLASSES if name not in classes]
    if missing:
        raise ProgramGateError("scorecard is missing a required genotype class")

    missense = _row_by_class(rows, "missense")
    wildtype = _row_by_class(rows, "wt")
    compound = _row_by_class(rows, "compound")
    corrected = _row_by_class(rows, "exact_corrected")
    recreated = _row_by_class(rows, "recreated_missense")
    stop_carrier = _row_by_class(rows, "stop")
    missense_carrier = _row_by_class(rows, "missense_carrier")
    abundance_row = _row_by_class(rows, "missense_at_abundance")
    specificity = missense.get("allele_specificity")
    if specificity not in ALLELE_SPECIFICITIES:
        raise ProgramGateError("missense allele_specificity is required")
    recreation_specificity = recreated.get("allele_specificity", "unlabeled")
    if (
        recreation_specificity not in ALLELE_SPECIFICITIES
        and recreation_specificity != "unlabeled"
    ):
        raise ProgramGateError("recreation allele_specificity is not in the allowed vocabulary")
    unlabeled_recreation_specificity = recreation_specificity == "unlabeled"
    correction_specificity = corrected.get("allele_specificity", "unlabeled")
    if (
        correction_specificity not in ALLELE_SPECIFICITIES
        and correction_specificity != "unlabeled"
    ):
        raise ProgramGateError("correction allele_specificity is not in the allowed vocabulary")
    analog_correction = correction_specificity in {"analog", "homolog", "nearby"}
    unlabeled_correction_specificity = correction_specificity == "unlabeled"
    missense_stability = {
        endpoint: _endpoint_status(missense, endpoint) for endpoint in STABILITY_ENDPOINTS
    }
    wt_stability = {
        endpoint: _endpoint_status(wildtype, endpoint) for endpoint in STABILITY_ENDPOINTS
    }
    compound_stability = {
        endpoint: _endpoint_status(compound, endpoint) for endpoint in STABILITY_ENDPOINTS
    }
    checkpoint = _endpoint_status(missense, "checkpoint")
    pd_positive = any(
        _optional_endpoint_status(missense, endpoint) == "positive" for endpoint in PD_ENDPOINTS
    )

    wt_positive = any(status == "positive" for status in wt_stability.values())
    missense_positive = any(status == "positive" for status in missense_stability.values())
    missense_all_negative = all(status == "negative" for status in missense_stability.values())
    missense_all_unknown = all(
        status == "not_assessable" for status in missense_stability.values()
    )
    reversal_failed = []
    for endpoint in FUNCTION_IDENTITY_ENDPOINTS:
        if _endpoint_status(missense, endpoint) != "positive":
            continue
        if _endpoint_status(corrected, endpoint) != "negative":
            reversal_failed.append(endpoint)
    computational_positive, unlabeled_positive = _positive_assay_problems(
        missense, FUNCTION_IDENTITY_ENDPOINTS
    )
    computational_correction, unlabeled_correction = _reversal_assay_problems(
        missense, corrected, FUNCTION_IDENTITY_ENDPOINTS
    )
    cell_free_correction, unlabeled_correction_system = _reversal_system_problems(
        missense, corrected, FUNCTION_IDENTITY_ENDPOINTS
    )
    imposed_correction, unlabeled_correction_condition = _reversal_condition_problems(
        missense, corrected, FUNCTION_IDENTITY_ENDPOINTS
    )
    ectopic_correction, unlabeled_correction_expression = _reversal_expression_problems(
        missense, corrected, FUNCTION_IDENTITY_ENDPOINTS
    )
    unmatched_correction, unlabeled_correction_specimen = _reversal_specimen_problems(
        missense, corrected, FUNCTION_IDENTITY_ENDPOINTS
    )
    (
        restoration_failed,
        computational_recreation,
        unlabeled_recreation,
    ) = _restoration_problems(missense, recreated, FUNCTION_IDENTITY_ENDPOINTS)
    missense_imposed, unlabeled_condition = _condition_problems(
        missense, FUNCTION_IDENTITY_ENDPOINTS
    )
    missense_positive_endpoints = tuple(
        endpoint
        for endpoint in FUNCTION_IDENTITY_ENDPOINTS
        if _endpoint_status(missense, endpoint) == "positive"
    )
    # The carrier dose control must be *informative* on every function axis:
    # a stub row that never produced a basal cellular call cannot exclude
    # dominant interference, and an unlabeled negative is as uninterpretable
    # as an unlabeled positive. Only a matched negative (carrier normal) or
    # a matched positive resolved against the stop carrier discharges it.
    carrier_assay_uninterpretable = []
    dominant_interference = []
    carrier_dose_unmeasured = []
    for endpoint in FUNCTION_AXES_ENDPOINTS:
        carrier_item = _endpoint_assessment(missense_carrier, endpoint)
        carrier_status = _endpoint_status(missense_carrier, endpoint)
        if carrier_status not in ("positive", "negative"):
            carrier_dose_unmeasured.append(endpoint)
        elif not _basal_cellular_matched(carrier_item):
            carrier_assay_uninterpretable.append(endpoint)
        elif carrier_status == "negative":
            continue
        else:
            stop_item = _endpoint_assessment(stop_carrier, endpoint)
            stop_status = _endpoint_status(stop_carrier, endpoint)
            if stop_status == "negative" and _basal_cellular_matched(stop_item):
                dominant_interference.append(endpoint)
            elif stop_status == "positive" and _basal_cellular_matched(stop_item):
                continue
            else:
                carrier_dose_unmeasured.append(endpoint)
    # Function-when-abundant discriminator (Suijkerbuijk 2010): a
    # destabilized allele is only stabilization-eligible if it is functional
    # when its abundance is normalized. The row must show abundance
    # normalized (defect not supported on the abundance endpoint) and no
    # persisting function defect on the basal cellular axes. An allele that
    # stays defective at normalized abundance is qualitatively broken —
    # raising its abundance cannot rescue it.
    abundance_exact = abundance_row.get("allele_specificity") == "exact"
    abundance_normalized = (
        _endpoint_status(abundance_row, "abundance") == "negative"
        and _abundance_row_interpretable(
            _endpoint_assessment(abundance_row, "abundance")
        )
    )
    abundance_defective = []
    abundance_unresolved = []
    for endpoint in FUNCTION_AXES_ENDPOINTS:
        item = _endpoint_assessment(abundance_row, endpoint)
        status = _endpoint_status(abundance_row, endpoint)
        if status == "positive" and _abundance_row_interpretable(item):
            abundance_defective.append(endpoint)
        elif status == "negative" and _abundance_row_interpretable(item):
            continue
        else:
            abundance_unresolved.append(endpoint)
    if not abundance_exact:
        abundance_unresolved = list(FUNCTION_AXES_ENDPOINTS)
    recreation_imposed, unlabeled_recreation_condition = _condition_problems(
        recreated, missense_positive_endpoints
    )
    missense_cell_free, unlabeled_system = _system_problems(
        missense, FUNCTION_IDENTITY_ENDPOINTS
    )
    recreation_cell_free, unlabeled_recreation_system = _system_problems(
        recreated, missense_positive_endpoints
    )
    missense_ectopic, unlabeled_expression = _expression_problems(
        missense, FUNCTION_IDENTITY_ENDPOINTS
    )
    recreation_ectopic, unlabeled_recreation_expression = _expression_problems(
        recreated, missense_positive_endpoints
    )
    missense_unmatched, unlabeled_specimen = _specimen_problems(
        missense, FUNCTION_IDENTITY_ENDPOINTS
    )
    recreation_unmatched, unlabeled_recreation_specimen = _specimen_problems(
        recreated, missense_positive_endpoints
    )

    if specificity != "exact":
        status = "stop"
        reason = "analog_as_exact_function"
        eligible = False
    elif recreation_specificity in {"analog", "homolog", "nearby"}:
        status = "stop"
        reason = "analog_as_exact_function"
        eligible = False
    elif computational_positive:
        status = "stop"
        reason = "computational_not_assay"
        eligible = False
    elif unlabeled_positive:
        status = "not_assessable"
        reason = "assay_class_required"
        eligible = False
    elif computational_correction:
        status = "stop"
        reason = "computational_correction_not_assay"
        eligible = False
    elif unlabeled_correction:
        status = "stop"
        reason = "unlabeled_correction_not_assay"
        eligible = False
    elif cell_free_correction:
        status = "stop"
        reason = "cell_free_correction_not_cellular"
        eligible = False
    elif unlabeled_correction_system:
        status = "stop"
        reason = "unlabeled_correction_system_class"
        eligible = False
    elif imposed_correction:
        status = "stop"
        reason = "imposed_stress_correction_not_basal"
        eligible = False
    elif unlabeled_correction_condition:
        status = "stop"
        reason = "unlabeled_correction_condition_class"
        eligible = False
    elif ectopic_correction:
        status = "stop"
        reason = "ectopic_correction_not_endogenous"
        eligible = False
    elif unlabeled_correction_expression:
        status = "stop"
        reason = "unlabeled_correction_expression_class"
        eligible = False
    elif unmatched_correction:
        status = "stop"
        reason = "unmatched_correction_not_assay_matched"
        eligible = False
    elif unlabeled_correction_specimen:
        status = "stop"
        reason = "unlabeled_correction_specimen_class"
        eligible = False
    elif analog_correction:
        status = "stop"
        reason = "analog_correction_not_exact"
        eligible = False
    elif unlabeled_correction_specificity:
        status = "stop"
        reason = "correction_specificity_required"
        eligible = False
    elif reversal_failed:
        status = "stop"
        reason = "correction_did_not_reverse_defect"
        eligible = False
    elif computational_recreation:
        status = "stop"
        reason = "computational_recreation_not_assay"
        eligible = False
    elif unlabeled_recreation:
        status = "stop"
        reason = "unlabeled_recreation_not_assay"
        eligible = False
    elif restoration_failed:
        status = "stop"
        reason = "recreation_did_not_restore_defect"
        eligible = False
    elif missense_imposed:
        status = "stop"
        reason = "imposed_stress_not_basal_defect"
        eligible = False
    elif unlabeled_condition:
        status = "stop"
        reason = "condition_class_required"
        eligible = False
    elif recreation_imposed:
        status = "stop"
        reason = "recreation_imposed_stress_not_basal"
        eligible = False
    elif unlabeled_recreation_condition:
        status = "stop"
        reason = "recreation_condition_class_required"
        eligible = False
    elif missense_cell_free:
        status = "stop"
        reason = "cell_free_not_cellular_defect"
        eligible = False
    elif unlabeled_system:
        status = "stop"
        reason = "system_class_required"
        eligible = False
    elif recreation_cell_free:
        status = "stop"
        reason = "recreation_cell_free_not_cellular"
        eligible = False
    elif unlabeled_recreation_system:
        status = "stop"
        reason = "recreation_system_class_required"
        eligible = False
    elif missense_ectopic:
        status = "stop"
        reason = "ectopic_not_endogenous_defect"
        eligible = False
    elif unlabeled_expression:
        status = "stop"
        reason = "expression_class_required"
        eligible = False
    elif recreation_ectopic:
        status = "stop"
        reason = "recreation_ectopic_not_endogenous"
        eligible = False
    elif unlabeled_recreation_expression:
        status = "stop"
        reason = "recreation_expression_class_required"
        eligible = False
    elif missense_unmatched:
        status = "stop"
        reason = "unmatched_not_assay_matched_defect"
        eligible = False
    elif unlabeled_specimen:
        status = "stop"
        reason = "specimen_class_required"
        eligible = False
    elif recreation_unmatched:
        status = "stop"
        reason = "recreation_unmatched_not_assay_matched"
        eligible = False
    elif unlabeled_recreation_specimen:
        status = "stop"
        reason = "recreation_specimen_class_required"
        eligible = False
    elif unlabeled_recreation_specificity:
        status = "stop"
        reason = "recreation_specificity_required"
        eligible = False
    elif wt_positive:
        status = "stop"
        reason = "wildtype_stability_positive"
        eligible = False
    elif missense_all_unknown:
        status = "not_assessable"
        reason = "missense_stability_not_assessable"
        eligible = False
    elif missense_all_negative:
        status = "stop"
        reason = "no_missense_stability_defect"
        eligible = False
    # The carrier dose control and the function-at-abundance discriminator
    # only qualify a live stabilization claim — they must not rewrite a
    # terminal falsification above into a resubmittable hold.
    elif missense_positive and dominant_interference:
        status = "stop"
        reason = "dominant_interference_possible"
        eligible = False
    elif missense_positive and abundance_defective:
        status = "stop"
        reason = "missense_defective_when_abundant"
        eligible = False
    elif missense_positive and carrier_assay_uninterpretable:
        status = "not_assessable"
        reason = "carrier_assay_class_required"
        eligible = False
    elif missense_positive and carrier_dose_unmeasured:
        status = "not_assessable"
        reason = "carrier_dose_control_required"
        eligible = False
    elif missense_positive and not abundance_normalized:
        status = "not_assessable"
        reason = "abundance_normalization_required"
        eligible = False
    elif missense_positive and abundance_unresolved:
        status = "not_assessable"
        reason = "function_at_abundance_required"
        eligible = False
    elif missense_positive:
        status = "pass"
        reason = "missense_stability_defect"
        eligible = True
    else:
        status = "not_assessable"
        reason = "missense_stability_not_assessable"
        eligible = False

    qualifier_reasons = {
        "carrier_dose_control_required",
        "carrier_assay_class_required",
        "abundance_normalization_required",
        "function_at_abundance_required",
    }
    if (
        not eligible
        and any(value == "positive" for value in compound_stability.values())
        and status != "stop"
        and reason not in qualifier_reasons
    ):
        reason = "compound_cannot_replace_missense"

    checkpoint_ready = eligible and checkpoint == "positive"
    effect = "pass" if eligible else ("stop" if status == "stop" else "hold")
    if eligible and pd_positive and not checkpoint_ready:
        status = "not_assessable"
        reason = "pd_not_checkpoint"
        effect = "hold"
    elif eligible and checkpoint == "negative":
        status = "stop"
        reason = "no_checkpoint_defect"
        effect = "stop"
        eligible = False
        checkpoint_ready = False
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "hypomorph",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": effect,
        "probe_eligible": eligible,
        "checkpoint_ready": checkpoint_ready,
        "allele_specificity": specificity,
        "pharmacodynamic_not_target": pd_positive,
        "reversal_failed_endpoints": reversal_failed,
        "computational_positive_endpoints": computational_positive,
        "unlabeled_positive_endpoints": unlabeled_positive,
        "computational_correction_endpoints": computational_correction,
        "unlabeled_correction_endpoints": unlabeled_correction,
        "cell_free_correction_endpoints": cell_free_correction,
        "unlabeled_correction_system_endpoints": unlabeled_correction_system,
        "imposed_stress_correction_endpoints": imposed_correction,
        "unlabeled_correction_condition_endpoints": unlabeled_correction_condition,
        "ectopic_correction_endpoints": ectopic_correction,
        "unlabeled_correction_expression_endpoints": unlabeled_correction_expression,
        "unmatched_correction_endpoints": unmatched_correction,
        "unlabeled_correction_specimen_endpoints": unlabeled_correction_specimen,
        "correction_allele_specificity": correction_specificity,
        "recreation_allele_specificity": recreation_specificity,
        "restoration_failed_endpoints": restoration_failed,
        "computational_recreation_endpoints": computational_recreation,
        "unlabeled_recreation_endpoints": unlabeled_recreation,
        "imposed_stress_endpoints": missense_imposed,
        "unlabeled_condition_endpoints": unlabeled_condition,
        "recreation_imposed_stress_endpoints": recreation_imposed,
        "unlabeled_recreation_condition_endpoints": unlabeled_recreation_condition,
        "cell_free_endpoints": missense_cell_free,
        "unlabeled_system_endpoints": unlabeled_system,
        "recreation_cell_free_endpoints": recreation_cell_free,
        "unlabeled_recreation_system_endpoints": unlabeled_recreation_system,
        "ectopic_expression_endpoints": missense_ectopic,
        "unlabeled_expression_endpoints": unlabeled_expression,
        "recreation_ectopic_endpoints": recreation_ectopic,
        "unlabeled_recreation_expression_endpoints": unlabeled_recreation_expression,
        "unmatched_specimen_endpoints": missense_unmatched,
        "unlabeled_specimen_endpoints": unlabeled_specimen,
        "recreation_unmatched_specimen_endpoints": recreation_unmatched,
        "unlabeled_recreation_specimen_endpoints": unlabeled_recreation_specimen,
        "reason": reason,
        "missense_stability": missense_stability,
        "wildtype_stability": wt_stability,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def _nonneg(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProgramGateError(f"{field} must be a non-negative integer")
    return value


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _empty_arm_counts() -> dict[str, int]:
    return {
        "opportunities": 0,
        "detected_divisions": 0,
        "event_positive_divisions": 0,
        "pre_division_death": 0,
        "no_division": 0,
        "dropout_censored": 0,
    }


def _competing_increase(vehicle: float | None, treatment: float | None) -> bool:
    if treatment is None:
        return False
    if vehicle is None or vehicle == 0:
        return treatment > 0
    return treatment > COMPETING_RISK_RATIO * vehicle


def _score_arm_pair(
    vehicle: Mapping[str, int], treatment: Mapping[str, int]
) -> dict[str, Any]:
    """Score one vehicle/treatment pair. Cytostasis is a competing risk."""

    v_div = _ratio(vehicle["event_positive_divisions"], vehicle["detected_divisions"])
    t_div = _ratio(
        treatment["event_positive_divisions"], treatment["detected_divisions"]
    )
    v_found = _ratio(vehicle["event_positive_divisions"], vehicle["opportunities"])
    t_found = _ratio(
        treatment["event_positive_divisions"], treatment["opportunities"]
    )
    v_comp = _ratio(vehicle["detected_divisions"], vehicle["opportunities"])
    t_comp = _ratio(treatment["detected_divisions"], treatment["opportunities"])
    generation_division = v_div is not None and t_div is not None and t_div < v_div
    generation_founder = (
        v_found is not None and t_found is not None and t_found < v_found
    )
    band = default_completion_band()
    pediatric = False
    if v_comp is not None and t_comp is not None and v_comp > 0:
        relative = t_comp / v_comp
        pediatric = (
            band.relative_lower <= relative <= band.relative_upper
            and (v_comp - t_comp) <= band.absolute_drop_max
        )
    competing = False
    for key in ("pre_division_death", "dropout_censored", "no_division"):
        competing = competing or _competing_increase(
            _ratio(vehicle[key], vehicle["opportunities"]),
            _ratio(treatment[key], treatment["opportunities"]),
        )
    if v_div is None or t_div is None or v_found is None or t_found is None:
        status = "not_assessable"
        reason = "insufficient_completions"
    elif competing:
        status = "stop"
        reason = "competing_toxicity"
    elif not pediatric:
        status = "hold"
        reason = "pediatric_band"
    elif not (generation_division and generation_founder):
        status = "hold"
        reason = "endpoints_not_concordant"
    else:
        status = "pass"
        reason = "concordant_generation"
    return {
        "status": status,
        "reason": reason,
        "generation_division": generation_division,
        "generation_founder": generation_founder,
        "pediatric_equivalent": pediatric,
        "competing_toxicity": competing,
        "vehicle_error_division": v_div,
        "treatment_error_division": t_div,
        "vehicle_error_founder": v_found,
        "treatment_error_founder": t_found,
    }


def _unavailable_concordance(reason: str) -> dict[str, Any]:
    band = default_completion_band()
    return {
        "schema": PROGRAM_SCHEMA,
        "gate": "concordance",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": "not_assessable",
        "program_effect": "hold",
        "reason": reason,
        "endpoints_concordant": False,
        "n_edit_events": 0,
        "minimum_edit_events": MINIMUM_EDIT_EVENTS,
        "minimum_clones_per_event": MINIMUM_CLONES_PER_EVENT,
        "completion_band": {
            "relative_lower": band.relative_lower,
            "relative_upper": band.relative_upper,
            "absolute_drop_max": band.absolute_drop_max,
        },
        "competing_risk_ratio": COMPETING_RISK_RATIO,
        "daughters_per_division": DAUGHTERS_PER_DIVISION,
        "events": [],
    }


def _assert_row_conservation(item: Mapping[str, Any]) -> None:
    """Refuse count rows that cannot exist as first-attempt lineage."""

    opportunities = _nonneg(item.get("opportunities"), "opportunities")
    detected = _nonneg(item.get("detected_divisions"), "detected_divisions")
    positive = _nonneg(
        item.get("event_positive_divisions"), "event_positive_divisions"
    )
    death = _nonneg(item.get("pre_division_death", 0), "pre_division_death")
    dropout = _nonneg(item.get("dropout_censored", 0), "dropout_censored")
    no_division = _nonneg(item.get("no_division", 0), "no_division")
    if positive > detected:
        raise ProgramGateError("positive divisions exceed detected divisions")
    if detected + death + no_division + dropout != opportunities:
        raise ProgramGateError("first-attempt outcomes must partition opportunities")
    negative = _nonneg(
        item.get("event_negative_divisions"), "event_negative_divisions"
    )
    if negative + positive != detected:
        raise ProgramGateError("positive and negative divisions must sum to detected divisions")
    multipolar_raw = item.get("event_positive_multipolar_divisions")
    multipolar = 0
    if multipolar_raw is not None:
        multipolar = _nonneg(
            multipolar_raw, "event_positive_multipolar_divisions"
        )
        if multipolar > positive:
            raise ProgramGateError(
                "multipolar divisions cannot exceed event-positive divisions"
            )
    for label, divisions in (("positive", positive), ("negative", negative)):
        followed_n = _nonneg(
            item.get(f"event_{label}_daughters_followed"),
            f"event_{label}_daughters_followed",
        )
        reproduced_n = _nonneg(
            item.get(f"event_{label}_daughters_reproduced"),
            f"event_{label}_daughters_reproduced",
        )
        died_n = _nonneg(
            item.get(f"event_{label}_daughters_died"),
            f"event_{label}_daughters_died",
        )
        bound = multipolar if label == "positive" else 0
        slots_field = f"event_{label}_daughter_slots"
        slots_raw = item.get(slots_field)
        if slots_raw is None:
            if bound:
                raise ProgramGateError(
                    "declared multipolar divisions require declared daughter slots"
                )
            slots = DAUGHTERS_PER_DIVISION * divisions
        else:
            slots = _nonneg(slots_raw, slots_field)
            if slots < DAUGHTERS_PER_DIVISION * divisions + bound:
                raise ProgramGateError(
                    f"{label} daughter slots cannot be fewer than two per division"
                )
            if label == "negative" and slots > DAUGHTERS_PER_DIVISION * divisions:
                raise ProgramGateError(
                    "clean divisions cannot produce more than two daughters"
                )
            if slots > DAUGHTERS_PER_DIVISION * divisions + 2 * bound:
                raise ProgramGateError(
                    f"{label} daughter slots exceed the multipolar bound"
                )
        if followed_n > slots:
            raise ProgramGateError(
                f"followed {label} daughters exceed the declared daughter slots"
            )
        if reproduced_n + died_n > followed_n:
            raise ProgramGateError(
                f"{label} daughters reproduced or died exceed followed daughters"
            )


def assess_endpoint_concordance(export: Mapping[str, Any]) -> dict[str, Any]:
    """Compute co-primary generation concordance from lineage counts.

    A tick is not enough. Both error-per-completed-division and
    error-bearing-completion-per-enrolled-founder must fall, completion must
    stay inside the pediatric band, and at least three edit events are required.
    A hero clone cannot pool a discordant clone into a pass. Increased
    no-division is competing cytostasis, not rescue. Count rows that cannot
    exist as first-attempt lineage fail closed.
    """

    payload = _mapping(export, "lineage counts")
    if payload.get("schema") != LINEAGE_COUNTS_SCHEMA:
        raise ProgramGateError("concordance accepts lineage-count exports only")
    if payload.get("lock_state") != "locked":
        return _unavailable_concordance("counts_not_locked")
    if payload.get("blinded") is not True:
        return _unavailable_concordance("counts_not_blinded")
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ProgramGateError("lineage-count export has no runs")
    if len(runs) > 500_000:
        raise ProgramGateError("lineage-count export exceeds the run ceiling")
    grouped: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    pair_seen: set[tuple[str, str, str]] = set()
    for row in runs:
        item = _mapping(row, "count row")
        arm = item.get("arm")
        if arm not in {"vehicle", "treatment"}:
            raise ProgramGateError("arm must be vehicle or treatment")
        event_id = _identifier(item.get("edit_event_id"), "edit_event_id")
        clone_id = _identifier(item.get("clone_id"), "clone_id")
        run_id = _identifier(item.get("run_id"), "run_id")
        key = (event_id, clone_id, run_id, str(arm))
        if key in seen:
            raise ProgramGateError("duplicate count row")
        seen.add(key)
        pair_key = (event_id, clone_id, str(arm))
        if pair_key in pair_seen:
            raise ProgramGateError(
                "a clone arm cannot be split across multiple runs"
            )
        pair_seen.add(pair_key)
        _assert_row_conservation(item)
        bucket = grouped.setdefault(event_id, {}).setdefault(
            clone_id, {}
        ).setdefault(str(arm), _empty_arm_counts())
        for field in _empty_arm_counts():
            bucket[field] += _nonneg(item.get(field, 0), field)

    band = default_completion_band()
    events = []
    for event_id in sorted(grouped):
        by_clone = grouped[event_id]
        clones = []
        pooled = {arm: _empty_arm_counts() for arm in ("vehicle", "treatment")}
        for clone_id in sorted(by_clone):
            by_arm = by_clone[clone_id]
            for arm, counts in by_arm.items():
                for field, value in counts.items():
                    pooled[arm][field] += value
            if "vehicle" not in by_arm or "treatment" not in by_arm:
                clones.append(
                    {
                        "clone_id": clone_id,
                        "status": "not_assessable",
                        "reason": "missing_arm",
                        "generation_division": False,
                        "generation_founder": False,
                        "pediatric_equivalent": False,
                        "competing_toxicity": False,
                    }
                )
                continue
            scored = _score_arm_pair(by_arm["vehicle"], by_arm["treatment"])
            scored["clone_id"] = clone_id
            clones.append(scored)
        clone_statuses = {item["status"] for item in clones}
        if len(by_clone) < MINIMUM_CLONES_PER_EVENT:
            status = "not_assessable"
            reason = "insufficient_clones"
        elif "stop" in clone_statuses:
            status = "stop"
            reason = "competing_toxicity"
        elif "not_assessable" in clone_statuses or "hold" in clone_statuses:
            status = "hold"
            reason = next(
                item["reason"]
                for item in clones
                if item["status"] in {"hold", "not_assessable"}
            )
        else:
            status = "pass"
            reason = "concordant_generation"
        pooled_score = None
        if "vehicle" in pooled and "treatment" in pooled:
            pooled_score = _score_arm_pair(pooled["vehicle"], pooled["treatment"])
        events.append(
            {
                "edit_event_id": event_id,
                "status": status,
                "reason": reason,
                "n_clones": len(by_clone),
                "minimum_clones_per_event": MINIMUM_CLONES_PER_EVENT,
                "generation_division": all(
                    item.get("generation_division") for item in clones
                ),
                "generation_founder": all(
                    item.get("generation_founder") for item in clones
                ),
                "pediatric_equivalent": all(
                    item.get("pediatric_equivalent") for item in clones
                ),
                "competing_toxicity": any(
                    item.get("competing_toxicity") for item in clones
                ),
                "pooled_would_pass": bool(
                    pooled_score is not None and pooled_score["status"] == "pass"
                ),
                "clones": clones,
            }
        )

    statuses = {item["status"] for item in events}
    if len(grouped) < MINIMUM_EDIT_EVENTS:
        overall = "not_assessable"
        reason = "insufficient_edit_events"
        effect = "hold"
        concordant = False
    elif "stop" in statuses:
        overall = "stop"
        reason = "competing_toxicity"
        effect = "stop"
        concordant = False
    elif "not_assessable" in statuses or "hold" in statuses:
        overall = "hold"
        reason = next(
            item["reason"]
            for item in events
            if item["status"] in {"hold", "not_assessable"}
        )
        effect = "hold"
        concordant = False
    else:
        overall = "pass"
        reason = "concordant_generation"
        effect = "pass"
        concordant = True
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "concordance",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": overall,
        "program_effect": effect,
        "reason": reason,
        "endpoints_concordant": concordant,
        "n_edit_events": len(grouped),
        "minimum_edit_events": MINIMUM_EDIT_EVENTS,
        "minimum_clones_per_event": MINIMUM_CLONES_PER_EVENT,
        "completion_band": {
            "relative_lower": band.relative_lower,
            "relative_upper": band.relative_upper,
            "absolute_drop_max": band.absolute_drop_max,
        },
        "competing_risk_ratio": COMPETING_RISK_RATIO,
        "daughters_per_division": DAUGHTERS_PER_DIVISION,
        "source_fingerprint": lineage_source_fingerprint(export),
        "events": events,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def _mappable_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str) and value:
        token = value.rsplit("-", 1)[-1]
        if token.isdigit():
            number = int(token)
            if number > 0:
                return number
    return None


def assess_count_table_identity(
    lineage: Mapping[str, Any],
    blinded: Mapping[str, Any],
    exposure_table: Mapping[str, Any],
    assay_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """A pretty imaging table cannot disagree with the lineage counts.

    Mapped arm, event, clone, and run keys must match. Every shared count field
    must be equal. Competing-risk labels on the lineage table forbid treating
    the blinded aggregate rows as a rescue claim. Only then is the exposure-
    execution and vehicle-control binding evaluated.
    """

    from mva_hackathon.generation_selection import (
        GenerationSelectionError,
        ObservedRun,
    )

    export = _mapping(lineage, "lineage counts")
    table = _mapping(blinded, "blinded count table")
    if export.get("schema") != LINEAGE_COUNTS_SCHEMA:
        raise ProgramGateError("count identity accepts lineage-count exports only")
    if table.get("schema") != BLINDED_SCHEMA:
        raise ProgramGateError("count identity accepts the community blinded table only")
    lineage_runs = export.get("runs")
    blinded_runs = table.get("runs")
    if not isinstance(lineage_runs, list) or not lineage_runs:
        raise ProgramGateError("lineage counts have no runs")
    if len(lineage_runs) > 500_000:
        raise ProgramGateError("lineage counts exceed the run ceiling")
    if not isinstance(blinded_runs, list) or not blinded_runs:
        raise ProgramGateError("blinded table has no runs")
    if len(blinded_runs) > 500_000:
        raise ProgramGateError("blinded table exceeds the run ceiling")

    blinded_index: dict[tuple[str, int, int, int], Any] = {}
    for raw in blinded_runs:
        item = _mapping(raw, "blinded row")
        for field in IDENTITY_KEY_FIELDS:
            if field not in item:
                raise ProgramGateError("blinded row is missing an identity key")
            value = item[field]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ProgramGateError(
                    "blinded identity keys must be positive integers"
                )
        for field in IDENTITY_FIELDS:
            if field not in item:
                raise ProgramGateError("blinded row is missing a shared count")
            value = item[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProgramGateError(
                    "blinded shared counts must be non-negative integers"
                )
        try:
            observed = ObservedRun(
                arm=str(item["arm"]),
                edit_event_id=item["edit_event_id"],
                clone_id=item["clone_id"],
                run_id=item["run_id"],
                opportunities=int(item["opportunities"]),
                detected_divisions=int(item["detected_divisions"]),
                event_positive_divisions=int(item["event_positive_divisions"]),
                event_negative_divisions=int(item["event_negative_divisions"]),
                event_positive_daughters_followed=int(
                    item["event_positive_daughters_followed"]
                ),
                event_positive_daughters_reproduced=int(
                    item["event_positive_daughters_reproduced"]
                ),
                event_positive_daughters_died=int(item["event_positive_daughters_died"]),
                event_negative_daughters_followed=int(
                    item["event_negative_daughters_followed"]
                ),
                event_negative_daughters_reproduced=int(
                    item["event_negative_daughters_reproduced"]
                ),
                event_negative_daughters_died=int(item["event_negative_daughters_died"]),
                event_positive_daughter_slots=item.get(
                    "event_positive_daughter_slots"
                ),
                event_negative_daughter_slots=item.get(
                    "event_negative_daughter_slots"
                ),
                event_positive_multipolar_divisions=item.get(
                    "event_positive_multipolar_divisions"
                ),
                pre_division_death=int(item["pre_division_death"]),
                no_division=int(item["no_division"]),
                dropout_censored=int(item["dropout_censored"]),
            )
        except (GenerationSelectionError, KeyError, TypeError, ValueError) as exc:
            raise ProgramGateError("blinded row is not a valid observed run") from exc
        key = (
            observed.arm,
            observed.edit_event_id,
            observed.clone_id,
            observed.run_id,
        )
        if key in blinded_index:
            raise ProgramGateError("blinded table has duplicate rows")
        blinded_index[key] = observed

    lineage_index: dict[tuple[str, int, int, int], Mapping[str, Any]] = {}
    # String identifiers map to their trailing integer. Clone and run labels
    # legitimately restart per edit event, so their collision scope is the
    # mapped event; edit events themselves are global. Two distinct raw
    # strings landing on the same integer within a scope would merge
    # different events/clones/runs in the blinded index.
    raw_identity: dict[object, object] = {}
    competing = False
    unmapped = 0
    missing_shared_counts = False
    for raw in lineage_runs:
        item = _mapping(raw, "lineage row")
        row_complete = True
        for field in IDENTITY_FIELDS:
            if field not in item:
                missing_shared_counts = True
                row_complete = False
                continue
            value = item[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProgramGateError(
                    "lineage shared counts must be non-negative integers"
                )
        for name in ("pre_division_death", "no_division", "dropout_censored"):
            value = item.get(name, 0)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ProgramGateError(
                    "lineage competing-risk counts must be non-negative integers"
                )
            competing = competing or value > 0
        if row_complete:
            _assert_row_conservation(item)
        arm = item.get("arm")
        event = _mappable_int(item.get("edit_event_id"))
        clone = _mappable_int(item.get("clone_id"))
        run = _mappable_int(item.get("run_id"))
        if event is None or clone is None or run is None or arm not in {"vehicle", "treatment"}:
            unmapped += 1
            continue
        for scope, mapped, raw_value, label in (
            ("event", event, item.get("edit_event_id"), "edit_event_id"),
            (("clone", event), clone, item.get("clone_id"), "clone_id"),
            (("run", event), run, item.get("run_id"), "run_id"),
        ):
            identity_key = (scope, mapped)
            prior = raw_identity.get(identity_key)
            if prior is None:
                raw_identity[identity_key] = raw_value
            elif prior != raw_value:
                raise ProgramGateError(
                    f"ambiguous {label}: distinct identifiers share the "
                    f"trailing integer {mapped}"
                )
        key = (str(arm), event, clone, run)
        if key in lineage_index:
            raise ProgramGateError("lineage counts have duplicate mapped rows")
        lineage_index[key] = item

    mismatched = False
    if missing_shared_counts or unmapped or set(lineage_index) != set(blinded_index):
        mismatched = True
    else:
        for key, item in lineage_index.items():
            observed = blinded_index[key]
            for field in IDENTITY_FIELDS:
                if item[field] != int(getattr(observed, field)):
                    mismatched = True
            for field in OPTIONAL_IDENTITY_FIELDS:
                declared = item.get(field)
                blinded_value = getattr(observed, field)
                if declared is None and blinded_value is None:
                    continue
                if (
                    not isinstance(declared, int)
                    or isinstance(declared, bool)
                    or blinded_value is None
                    or declared != blinded_value
                ):
                    mismatched = True

    binding = {
        "status": "not_assessable",
        "reason": "earlier_count_identity_block",
        "exposure_execution_linked": False,
        "linked_assay_fingerprint": None,
    }
    allocation_inference = {
        "status": "not_assessable",
        "program_effect": "hold",
        "reason": "earlier_count_or_binding_block",
        "advancement_blocked": True,
        "endpoints": [],
    }
    if not mismatched and not competing:
        try:
            binding = assess_exposure_execution_binding(
                exposure_table,
                export,
                assay_plan,
            )
        except ExposureGateError as exc:
            raise ProgramGateError("exposure-assay binding is malformed") from exc
        if binding.get("status") == "pass":
            allocation_inference = assess_constrained_randomization_inference(
                export,
                exposure_table,
            )

    if mismatched:
        status = "hold"
        reason = "count_tables_inconsistent"
        effect = "hold"
        aligned = False
    elif competing:
        status = "hold"
        reason = "competing_risk_present"
        effect = "hold"
        aligned = False
    elif binding.get("status") != "pass":
        status = "hold"
        reason = str(binding.get("reason") or "exposure_assay_source_mismatch")
        effect = "hold"
        aligned = True
    elif allocation_inference.get("status") != "pass":
        inference_status = allocation_inference.get("status")
        status = "stop" if inference_status == "stop" else "hold"
        reason = str(
            allocation_inference.get("reason")
            or "allocation_inference_not_assessable"
        )
        effect = "stop" if status == "stop" else "hold"
        aligned = True
    else:
        status = "pass"
        reason = "count_tables_aligned"
        effect = "pass"
        aligned = True
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "count_identity",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": effect,
        "reason": reason,
        "tables_aligned": aligned,
        "exposure_execution_linked": bool(
            binding.get("exposure_execution_linked")
        ),
        "exposure_binding_reason": binding.get("reason"),
        "linked_assay_fingerprint": binding.get("linked_assay_fingerprint"),
        "allocation_inference_status": allocation_inference.get("status"),
        "allocation_inference_reason": allocation_inference.get("reason"),
        "allocation_inference": allocation_inference,
        "competing_risk_present": competing,
        "n_lineage_rows": len(lineage_runs),
        "n_blinded_rows": len(blinded_runs),
        "source_fingerprint": lineage_source_fingerprint(export),
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def assess_replication_decision(
    payload: Mapping[str, Any],
    *,
    clone_safety: Mapping[str, Any] | None = None,
    exposure: Mapping[str, Any] | None = None,
    concordance: Mapping[str, Any] | None = None,
    hypomorph: Mapping[str, Any] | None = None,
    hypothesis: Mapping[str, Any] | None = None,
    confirmation: Mapping[str, Any] | None = None,
    phase: Mapping[str, Any] | None = None,
    transcript: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Advance only when nested contracts passed and computed endpoints agree.

    A ticked endpoints_concordant boolean cannot override a computed miss, and
    a computed pass cannot override a site that still declared discordant.
    Stability-only probe eligibility cannot advance. Analog or unrepaired
    missense identity cannot advance. A child claim weaker than conditional
    ex-vivo cannot advance.
    """

    record = _mapping(payload, "replication decision")
    if record.get("schema") != REPLICATION_SCHEMA:
        raise ProgramGateError("replication gate accepts the community decision record only")
    site_id = _identifier(record.get("site_id"), "site_id")
    originating_raw = record.get("originating_site_id")
    if originating_raw is None:
        originating_site_id = None
        independent_site = False
        independent_reason = "independent_site_unproven"
    else:
        originating_site_id = _identifier(originating_raw, "originating_site_id")
        if originating_site_id == site_id:
            independent_site = False
            independent_reason = "same_site"
        else:
            independent_site = True
            independent_reason = "independent_site"
    declared = _bool(record.get("endpoints_concordant"), "endpoints_concordant")
    flagged_stop = _bool(record.get("clone_safety_stop"), "clone_safety_stop")
    flagged_exposure = _bool(record.get("exposure_gate_passed"), "exposure_gate_passed")

    clone_status = None
    exposure_status = None
    concordance_status = None
    hypomorph_status = None
    hypothesis_status = None
    hypo = None
    computed = None
    checkpoint_ready = False
    allele_specificity = None
    child_claim = None
    clone_fingerprint = None
    concordance_fingerprint = None
    clone_stop = flagged_stop
    exposure_passed = flagged_exposure
    confirmation_status = None
    phase_status = None
    transcript_status = None
    confirmation_effect = None
    phase_effect = None
    transcript_effect = None
    if clone_safety is not None:
        safety = _mapping(clone_safety, "clone_safety")
        if safety.get("schema") != CLONE_SAFETY_SCHEMA:
            raise ProgramGateError("clone-safety object has the wrong schema")
        clone_status = safety.get("status")
        nested_clone_stop = _bool(
            safety.get("clone_safety_stop"), "clone_safety.clone_safety_stop"
        )
        clone_stop = flagged_stop or nested_clone_stop
        clone_fingerprint = safety.get("source_fingerprint")
    if exposure is not None:
        measured = _mapping(exposure, "exposure")
        if measured.get("schema") != EXPOSURE_SCHEMA:
            raise ProgramGateError("exposure object has the wrong schema")
        exposure_status = measured.get("status")
        nested_exposure_passed = _bool(
            measured.get("exposure_gate_passed"),
            "exposure.exposure_gate_passed",
        )
        exposure_passed = flagged_exposure and nested_exposure_passed
    if concordance is not None:
        conc = _mapping(concordance, "concordance")
        if conc.get("schema") != PROGRAM_SCHEMA or conc.get("gate") != "concordance":
            raise ProgramGateError("concordance object has the wrong schema")
        concordance_status = conc.get("status")
        computed = _bool(
            conc.get("endpoints_concordant"), "concordance.endpoints_concordant"
        )
        concordance_fingerprint = conc.get("source_fingerprint")
    if hypomorph is not None:
        hypo = _mapping(hypomorph, "hypomorph")
        if hypo.get("schema") != PROGRAM_SCHEMA or hypo.get("gate") != "hypomorph":
            raise ProgramGateError("hypomorph object has the wrong schema")
        hypomorph_status = hypo.get("status")
        checkpoint_ready = _bool(
            hypo.get("checkpoint_ready"), "hypomorph.checkpoint_ready"
        )
        allele_specificity = hypo.get("allele_specificity")
    if hypothesis is not None:
        claimed = _mapping(hypothesis, "hypothesis")
        if claimed.get("schema") != HYPOTHESIS_SCHEMA:
            raise ProgramGateError("hypothesis object has the wrong schema")
        hypothesis_status = claimed.get("status")
        child_claim = claimed.get("child_claim_strength")
    if confirmation is not None:
        conf = _mapping(confirmation, "confirmation")
        if conf.get("schema") != PROGRAM_SCHEMA or conf.get("gate") != "confirmation":
            raise ProgramGateError("confirmation object has the wrong schema")
        confirmation_status = conf.get("status")
        confirmation_effect = conf.get("program_effect")
    if phase is not None:
        phased = _mapping(phase, "phase")
        if phased.get("schema") != PROGRAM_SCHEMA or phased.get("gate") != "phase":
            raise ProgramGateError("phase object has the wrong schema")
        phase_status = phased.get("status")
        phase_effect = phased.get("program_effect")
    if transcript is not None:
        rna = _mapping(transcript, "transcript")
        if rna.get("schema") != PROGRAM_SCHEMA or rna.get("gate") != "transcript":
            raise ProgramGateError("transcript object has the wrong schema")
        transcript_status = rna.get("status")
        transcript_effect = rna.get("program_effect")

    # Every supplied nested receipt must carry a valid self-integrity digest —
    # a fabricated receipt can claim program_effect=pass, so an
    # internally-inconsistent one must not be trusted at all.
    for label, receipt in (
        ("clone_safety", clone_safety),
        ("exposure", exposure),
        ("concordance", concordance),
        ("hypomorph", hypomorph),
        ("hypothesis", hypothesis),
        ("confirmation", confirmation),
        ("phase", phase),
        ("transcript", transcript),
    ):
        if receipt is not None and not receipt_sha256_ok(receipt):
            raise ProgramGateError(
                f"{label} receipt self-integrity digest is invalid"
            )

    if clone_stop or exposure_status == "stop":
        decision = "stop"
        reason = "clone_safety_stop" if clone_stop else "exposure_stop"
    elif concordance_status == "stop":
        decision = "stop"
        reason = "competing_toxicity"
    elif hypomorph_status == "stop":
        decision = "stop"
        reason = str(hypo.get("reason") or "hypomorph_stop")
    elif hypomorph is not None and not _bool(
        hypo.get("probe_eligible"), "hypomorph.probe_eligible"
    ):
        decision = "hold"
        reason = "hypomorph_not_passed"
    elif hypomorph is not None and (
        hypomorph_status != "pass" or not checkpoint_ready
    ):
        decision = "hold"
        reason = "checkpoint_not_ready"
    elif hypothesis_status == "stop":
        decision = "stop"
        reason = str(claimed.get("reason") or "hypothesis_stop")
    elif confirmation_effect == "stop" or confirmation_status == "stop":
        decision = "stop"
        reason = "confirmation_stop"
    elif phase_effect == "stop" or phase_status == "stop":
        decision = "stop"
        reason = "phase_stop"
    elif transcript_effect == "stop" or transcript_status == "stop":
        decision = "stop"
        reason = "transcript_stop"
    elif not declared:
        decision = "hold"
        reason = "declared_discordant" if computed is True else "endpoints_not_concordant"
    elif concordance is None or clone_status != "pass" or exposure_status != "pass":
        decision = "hold"
        reason = "insufficient_gate_objects"
    elif concordance_status != "pass" or computed is not True:
        decision = "hold"
        reason = "computed_not_concordant"
    elif clone_fingerprint != concordance_fingerprint or not isinstance(
        clone_fingerprint, str
    ):
        decision = "hold"
        reason = "clone_safety_source_mismatch"
    elif not independent_site:
        decision = "hold"
        reason = independent_reason
    elif not exposure_passed:
        decision = "hold"
        reason = "exposure_not_passed"
    elif hypomorph is None or hypothesis is None or confirmation is None or phase is None or transcript is None:
        decision = "hold"
        reason = "insufficient_gate_objects"
    elif confirmation_effect != "pass" or confirmation_status != "pass":
        decision = "hold"
        reason = "confirmation_not_passed"
    elif phase_effect != "pass" or phase_status != "pass":
        decision = "hold"
        reason = "phase_not_passed"
    elif transcript_effect != "pass" or transcript_status != "pass":
        decision = "hold"
        reason = "transcript_not_passed"
    elif child_claim != "conditional_ex_vivo":
        decision = "hold"
        reason = "child_claim_too_weak"
    else:
        decision = "advance"
        reason = "gates_concordant"

    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "replication",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "site_id": site_id,
        "originating_site_id": originating_site_id,
        "independent_site": independent_site,
        "status": "pass" if decision == "advance" else decision,
        "decision": decision,
        "program_effect": decision,
        "reason": reason,
        "endpoints_concordant": declared and computed is True,
        "declared_endpoints_concordant": declared,
        "computed_endpoints_concordant": computed,
        "clone_safety_status": clone_status,
        "exposure_status": exposure_status,
        "concordance_status": concordance_status,
        "hypomorph_status": hypomorph_status,
        "hypothesis_status": hypothesis_status,
        "confirmation_status": confirmation_status,
        "phase_status": phase_status,
        "transcript_status": transcript_status,
        "checkpoint_ready": checkpoint_ready,
        "allele_specificity": allele_specificity,
        "child_claim_strength": child_claim,
        "clone_safety_stop": clone_stop,
        "exposure_gate_passed": exposure_passed,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


EVIDENCE_SCHEMA = "mva.community-observed-inferred-unknown/v1"
FAMILY_BLANKS = ("[result]", "[next gate]", "[what this does not mean]")
OVERCLAIM_PHRASES = (
    "in trans in a real",
    "clinical benefit",
    "treatment success",
    "administer",
    "organ size restored",
    "brain size restored",
    "recovered brain size",
    "checkpoint rescued",
    "will save",
    "give this medicine",
    "is a cure",
    "cures",
    "cured",
    "curative",
    "rescues",
    "rescued the",
    "is rescued",
    "rescue achieved",
    "we recommend this treatment",
    "we recommend this medicine",
    "recommend this treatment",
    "recommend this medicine",
    "recommend the medicine",
    "recommend the drug",
    "recommend the treatment",
    "recommended treatment",
    "recommended medicine",
    "medicine recommendation",
    "treatment recommendation",
    "prescribe",
    "dose recommendation",
    "dosage",
    "child benefits",
    "benefits the child",
    "benefit the child",
    "the child will be",
    "patient benefits",
    "patient benefit",
    "therapeutic benefit",
    "therapeutic effect",
    "clinical efficacy",
    "treatment works",
    "drug works",
    "medicine works",
    "safe and effective",
    "proven treatment",
    "effective treatment",
    "ready for clinical",
    "clinic ready",
    "lifesaving",
    "life saving",
    "save the child",
    "saves the child",
    "give the medicine",
    "give the drug",
    "give the child",
)
ANALOG_PHRASES = (
    "analog allele proves",
    "homolog allele proves",
    "homolog proves mutant",
    "ortholog allele proves",
    "ortholog proves mutant",
    "paralog allele proves",
    "mouse allele proves",
    "yeast allele proves",
    "rat allele proves",
    "drosophila allele proves",
    "fly allele proves",
    "zebrafish allele proves",
    "xenopus allele proves",
    "c. elegans allele proves",
    "c elegans allele proves",
    "c-elegans allele proves",
    "celegans allele proves",
    "worm allele proves",
    "nearby allele proves",
    "nearby polymorphism proves",
    "structure proves mutant function",
    "alphafold proves",
    "alpha-fold proves",
    "alpha fold proves",
    "foldx proves",
    "alphamissense proves",
    "alpha-missense proves",
    "alpha missense proves",
    "geometry proves",
    "coordinate proves",
    "docking proves",
    "complementation proves",
    "in silico proves",
    "in-silico proves",
    "insilico proves",
    "pathogenicity score proves",
    "esm proves",
    "esm1b proves",
    "revel proves",
    "mave proves",
    "frequency proves",
    "conservation proves",
    "clinvar proves",
    "label proves",
    "catalog proves",
    "software proves",
    "database proves",
    "ontology proves",
    "literature proves",
    "cell-free proves",
    "cell free proves",
    "cellfree proves",
    "thermal shift proves",
    "thermal-shift proves",
    "purified-protein proves",
    "purified protein proves",
    "ectopic proves",
    "unmatched proves",
    "unmatched-line proves",
    "unmatched line proves",
    "unmatched genotype proves",
    "unmatched genotype line proves",
    "unmatched-genotype proves",
    "imposed-stress proves",
    "imposed stress proves",
    "imposed extrinsic stress proves",
    "imposed-extrinsic-stress proves",
    "rna-seq proves",
    "rna seq proves",
    "rnaseq proves",
    "rna-seq phase proves",
    "rna seq phase proves",
    "computational haplotype proves",
    "ranking proves",
    "predictor proves",
    "unlabeled proves",
    "transgene proves",
    "overexpression proves",
    "over-expression proves",
    "over expression proves",
    "computational proves",
    "cdna proves",
    "transient proves",
    "transient transfection proves",
    "biophysical proves",
    "protein-surrogate proves",
    "protein surrogate proves",
)


_CLAIM_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "і": "i",
        "ј": "j",
        "ѕ": "s",
        "һ": "h",
        "ԁ": "d",
        "ԍ": "g",
        "ո": "n",
        "ν": "v",
        "τ": "t",
        "υ": "u",
        "ω": "w",
        "α": "a",
        "β": "b",
        "ε": "e",
        "η": "n",
        "κ": "k",
        "μ": "u",
        "π": "n",
        "χ": "x",
        "м": "m",
        "т": "t",
        "н": "h",
        "в": "b",
        "к": "k",
        "з": "3",
        "и": "u",
        "г": "r",
        "д": "g",
        "л": "n",
        "п": "n",
        "ф": "o",
        "ι": "i",
        "ο": "o",
        "ρ": "p",
        "γ": "y",
        "σ": "o",
    }
)
_CLAIM_STRIP_CATEGORIES = frozenset({"Cf", "Cc", "Mn", "Me", "Cs"})


def _claim_fold(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).lower()
    text = text.translate(_CLAIM_CONFUSABLES)
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) not in _CLAIM_STRIP_CATEGORIES
    )


def normalize_claim_text(value: object) -> str:
    """Lowercase claim text with punctuation and whitespace collapsed.

    Compatibility folds fullwidth and styled forms, common lookalike letters
    map to their ASCII forms, combining marks and zero-width or control
    characters are removed, and every remaining non-alphanumeric run becomes
    one space, so "organ-size restored" and "organ, size restored" cannot
    evade "organ size restored".
    """

    return " ".join(re.sub(r"[^a-z0-9]+", " ", _claim_fold(value)).split())


def normalize_claim_joined(value: object) -> str:
    """Claim text with every non-alphanumeric character removed outright.

    The joined variant catches characters inserted inside a phrase — for
    example "clinical\\u200bbenefit" or "clinβical benefit" — which the
    spaced variant would split apart.
    """

    return re.sub(r"[^a-z0-9]+", "", _claim_fold(value))


def claim_blob_matches(
    spaced: str,
    joined: str,
    spaced_phrases: tuple[str, ...],
    joined_phrases: tuple[str, ...],
) -> bool:
    """True when a banned phrase appears in either normalized variant."""

    return any(phrase in spaced for phrase in spaced_phrases) or any(
        phrase in joined for phrase in joined_phrases
    )


_NORMALIZED_OVERCLAIM_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in OVERCLAIM_PHRASES
)
_NORMALIZED_ANALOG_PHRASES = tuple(
    normalize_claim_text(phrase) for phrase in ANALOG_PHRASES
)
_JOINED_OVERCLAIM_PHRASES = tuple(
    normalize_claim_joined(phrase) for phrase in OVERCLAIM_PHRASES
)
_JOINED_ANALOG_PHRASES = tuple(
    normalize_claim_joined(phrase) for phrase in ANALOG_PHRASES
)


def assess_evidence_links(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stop when a non-observed link is labeled observed, or when observed overclaims.

    Analog, homolog, ortholog, paralog, mouse, yeast, rat, Drosophila,
    fly, zebrafish, Xenopus, C. elegans, nearby-allele, nearby-polymorphism, AlphaFold, FoldX, AlphaMissense,
    geometry ranking, coordinate geometry, docking, complementation, in-silico,
    pathogenicity-score, ESM, REVEL, MAVE, frequency, conservation, ClinVar,
    official-label, software, software-catalog, database, ontology, literature,
    cell-free, ectopic, unmatched, imposed-stress, ranking, predictor,
    unlabeled, transgene, overexpression, computational, cDNA, transient,
    biophysical, thermal-shift, purified-protein, protein-surrogate,
    unmatched-line, RNA-seq, or computational-haplotype proof wording
    cannot be labeled observed.
    """

    record = _mapping(payload, "evidence table")
    if record.get("schema") != EVIDENCE_SCHEMA:
        raise ProgramGateError("evidence gate accepts the community evidence table only")
    vocab = record.get("status_vocabulary")
    if not isinstance(vocab, list) or not vocab:
        raise ProgramGateError("status vocabulary is required")
    links = record.get("links")
    if not isinstance(links, list) or not links:
        raise ProgramGateError("evidence table has no links")
    if len(links) > 10_000:
        raise ProgramGateError("evidence table exceeds the link ceiling")
    overclaims = []
    for link in links:
        item = _mapping(link, "evidence link")
        link_id = _identifier(item.get("link_id"), "link_id")
        status = item.get("status")
        if status not in vocab:
            raise ProgramGateError("evidence status is not in the declared vocabulary")
        statement = normalize_claim_text(item.get("statement", ""))
        supports = normalize_claim_text(item.get("supports", ""))
        blob = f"{statement} {supports}"
        joined_blob = normalize_claim_joined(
            f"{item.get('statement', '')} {item.get('supports', '')}"
        )
        # Banned wording is scanned on statement + supports at every status —
        # an inferred or planned link cannot carry a claim an observed link
        # could not, and overclaim cannot hide in an unscanned field.
        if claim_blob_matches(
            blob,
            joined_blob,
            (*_NORMALIZED_OVERCLAIM_PHRASES, *_NORMALIZED_ANALOG_PHRASES),
            (*_JOINED_OVERCLAIM_PHRASES, *_JOINED_ANALOG_PHRASES),
        ):
            overclaims.append(link_id)
    if overclaims:
        status = "stop"
        reason = "observed_overclaim"
        effect = "stop"
    else:
        status = "pass"
        reason = "labels_consistent"
        effect = "pass"
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "evidence",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": effect,
        "reason": reason,
        "overclaim_ids": overclaims,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


def assess_family_worksheet(text: str) -> dict[str, Any]:
    """Public family copy must keep blanks and a no-treatment disclaimer.

    Analog, homolog, ortholog, paralog, mouse, yeast, rat, Drosophila,
    fly, zebrafish, Xenopus, C. elegans, nearby-allele, nearby-polymorphism, AlphaFold, FoldX, AlphaMissense,
    geometry ranking, coordinate geometry, docking, complementation, in-silico,
    pathogenicity-score, ESM, REVEL, MAVE, frequency, conservation, ClinVar,
    official-label, software, software-catalog, database, ontology, literature,
    cell-free, ectopic, unmatched, imposed-stress, ranking, predictor,
    unlabeled, transgene, overexpression, computational, cDNA, transient,
    biophysical, thermal-shift, purified-protein, protein-surrogate,
    unmatched-line, RNA-seq, or computational-haplotype proof wording
    is an overclaim, not exact-allele function.
    """

    if not isinstance(text, str) or not text.strip():
        raise ProgramGateError("family worksheet must be text")
    missing = [token for token in FAMILY_BLANKS if token not in text]
    lower = text.lower()
    if missing:
        status = "stop"
        reason = "missing_blanks"
        effect = "stop"
    elif "not a treatment" not in lower:
        status = "stop"
        reason = "missing_disclaimer"
        effect = "stop"
    elif "not a cure" not in lower:
        status = "stop"
        reason = "missing_disclaimer"
        effect = "stop"
    elif claim_blob_matches(
        normalize_claim_text(text),
        normalize_claim_joined(text),
        (*_NORMALIZED_OVERCLAIM_PHRASES, *_NORMALIZED_ANALOG_PHRASES),
        (*_JOINED_OVERCLAIM_PHRASES, *_JOINED_ANALOG_PHRASES),
    ):
        status = "stop"
        reason = "family_overclaim"
        effect = "stop"
    else:
        status = "pass"
        reason = "public_blanks_retained"
        effect = "pass"
    result = {
        "schema": PROGRAM_SCHEMA,
        "gate": "family",
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "status": status,
        "program_effect": effect,
        "reason": reason,
        "missing_blanks": missing,
    }
    result["receipt_sha256"] = receipt_sha256(result)
    return result


__all__ = [
    "ALLELE_SPECIFICITIES",
    "ANALOG_PHRASES",
    "CLAIM_BOUNDARY",
    "CONFIRMATION_SCHEMA",
    "EXPRESSION_CLASSES",
    "FUNCTION_SPECIMENS",
    "FUNCTION_IDENTITY_ENDPOINTS",
    "CONFIRMATION_SPECIMENS",
    "LIBRARY_MOLECULES",
    "HYPOTHESIS_SCHEMA",
    "MINIMUM_CLONES_PER_EVENT",
    "PD_ENDPOINTS",
    "PHASE_SPECIMENS",
    "PROGRAM_SCHEMA",
    "SITE_DECISIONS",
    "STATUSES",
    "TRANSCRIPT_METHODS",
    "ProgramGateError",
    "assess_confirmation_gate",
    "assess_count_table_identity",
    "assess_endpoint_concordance",
    "assess_evidence_links",
    "assess_family_worksheet",
    "assess_hypomorph_gate",
    "assess_phase_gate",
    "assess_replication_decision",
    "assess_transcript_gate",
]
