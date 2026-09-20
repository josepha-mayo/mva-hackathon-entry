from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.candidate_ledger import (
    ADVANCEMENT_STATES,
    ARCHITECTURE_LINEAGE_STATES,
    ASSESSMENT_STATUSES,
    CLAIM_BOUNDARY,
    DECISION_EFFECTS,
    DIRECTIONS,
    DISCOVERY_LANES,
    EXPOSURE_CLASSES,
    FULL_PHENOCOPY_PRE_REPLICATION_GATE_NAMES,
    FUNCTIONAL_HIT_STATES,
    HELD_OUT_CONFIRMATION_GATE_NAMES,
    HELD_OUT_CONFIRMATION_STATES,
    INDEPENDENT_REPLICATION_STATES,
    MITOTIC_CONTEXT_CLASSES,
    ONCOLOGY_RISKS,
    NO_HIT_BASES,
    PARENT_SOURCE_CLASSES,
    PEDIATRIC_INFORMATION_STATES,
    PRIVACY_CLASSES,
    PROGRAM_GATES,
    REGULATORY_ELIGIBILITY_STATES,
    RESCUE_GATE_STATES,
    ROLES,
    SAMPLE_STEWARDSHIP_PROMOTION_FIELDS,
    SCREEN_CONTEXTS,
    SITE2_BLINDING_STATES,
    SOURCE_CLASSES,
    THERAPEUTIC_CONTEXTS,
    TRANSFORMATION_STATES,
    TRANSLATION_STATES,
    CandidateEntry,
    CandidateLedgerError,
    ReplicationDesign,
    RescueGates,
    SampleStewardshipPromotion,
    SearchProtocol,
    canonical_candidate_ledger_bytes,
    canonical_candidate_ranking_bytes,
    load_candidate_ledger,
    load_sample_stewardship_plan,
    load_sample_stewardship_plan_bytes,
    rank_candidates as rank_candidates_engine,
    sample_stewardship_plan_sha256,
    validate_candidate_release_bundle_bytes,
    validate_candidate_release_ledger_bytes,
    validate_candidate_ledger as validate_candidate_ledger_engine,
)
from mva_hackathon.sample_stewardship import make_completion_receipt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "track2_candidate_ledger.synthetic.json"
SAMPLE_TEMPLATE = ROOT / "templates" / "track2_sample_stewardship.synthetic.json"
SCHEMA = ROOT / "schemas" / "track2_candidate_ledger.schema.json"
PROTOCOL = ROOT / "configs" / "track2-candidate-search-protocol.json"
RELEASE_SCRIPT = ROOT / "scripts" / "render_candidate_release_bundle.py"
RANK_SCRIPT = ROOT / "scripts" / "rank_candidate_ledger.py"
ANALYTIC_TRANSFER_RECEIPT = "a" * 64
SITE2_BLINDING_RECEIPT = "b" * 64
PHENOTYPE_TRANSFER_RECEIPT = "b" * 64
PHENOTYPE_SITE2_RECEIPT = "c" * 64


def _lane_prefix(lane: str) -> str:
    if lane == "targeted_hypothesis":
        return "targeted"
    return "phenotype"


def _promotion_evidence(lane: str) -> dict[str, object]:
    if lane == "targeted_hypothesis":
        return {
            "analytic_transfer_result_sha256": ANALYTIC_TRANSFER_RECEIPT,
            "site2_blinding_state": "blinded",
            "site2_blinding_id": "syn-blinding-site2-targeted",
            "site2_blinding_evidence_sha256": SITE2_BLINDING_RECEIPT,
            "discovery_event_family_ids": ["syn-event-discovery-one"],
            "replication_event_family_ids": ["syn-event-replication-one"],
            "discovery_site_id": "syn-site-discovery-targeted",
            "replication_site_id": "syn-site-replication-targeted",
        }
    return {
        "analytic_transfer_result_sha256": PHENOTYPE_TRANSFER_RECEIPT,
        "site2_blinding_state": "blinded",
        "site2_blinding_id": "syn-blinding-site2-phenotype",
        "site2_blinding_evidence_sha256": PHENOTYPE_SITE2_RECEIPT,
        "discovery_event_family_ids": ["syn-event-discovery-phenotype"],
        "replication_event_family_ids": ["syn-event-replication-phenotype"],
        "discovery_site_id": "syn-site-discovery-phenotype",
        "replication_site_id": "syn-site-replication-phenotype",
    }


def _align_context_assay(
    plan: dict[str, object],
    lane: str,
    mitotic_context_class: str | None,
    transformation_state: str | None,
) -> None:
    if mitotic_context_class is None and transformation_state is None:
        return
    prefix = _lane_prefix(lane)
    assay_id = f"syn-tier-b-{prefix}-context"
    assay = next(
        item for item in plan["assays"] if item["assay_id"] == assay_id  # type: ignore[index]
    )
    context = assay["context_qualification"]
    if mitotic_context_class is not None and mitotic_context_class != context.get(
        "mitotic_context_class"
    ):
        context["mitotic_context_class"] = mitotic_context_class
        requirements = list(assay["validity_requirements"])
        if mitotic_context_class == "lineage_intrinsic_mitotic":
            requirements = [
                "lineage_intrinsic_mitotic_context"
                if item == "architecture_preserving_context"
                else item
                for item in requirements
            ]
        elif mitotic_context_class == "epithelial_architecture_dependent":
            requirements = [
                "architecture_preserving_context"
                if item == "lineage_intrinsic_mitotic_context"
                else item
                for item in requirements
            ]
        assay["validity_requirements"] = requirements
    if transformation_state is not None and transformation_state != context.get(
        "transformation_state"
    ):
        context["transformation_state"] = transformation_state


def _complete_sample_lane(
    lane: str,
    *,
    mitotic_context_class: str | None = None,
    transformation_state: str | None = None,
) -> dict[str, object]:
    plan = json.loads(SAMPLE_TEMPLATE.read_text(encoding="utf-8"))
    _align_context_assay(plan, lane, mitotic_context_class, transformation_state)
    prefix = _lane_prefix(lane)
    assays = {item["assay_id"]: item for item in plan["assays"]}
    for assay_id in (
        f"syn-a0-{prefix}",
        f"syn-a1-{prefix}-bridge",
        f"syn-tier-b-{prefix}-context",
        f"syn-tier-b-{prefix}-lineage",
        f"syn-held-out-{prefix}",
    ):
        plan["completed"][assay_id] = make_completion_receipt(
            assays[assay_id],
            "positive",
            "syn-completion-" + assay_id.removeprefix("syn-"),
        )
    replication_id = f"syn-replication-{prefix}"
    plan["completed"][replication_id] = make_completion_receipt(
        assays[replication_id],
        "positive",
        "syn-completion-" + replication_id.removeprefix("syn-"),
        promotion_evidence=_promotion_evidence(lane),
    )
    return plan


def bind_sample_promotion(entry: dict[str, object]) -> dict[str, object]:
    lane = str(entry["discovery_lane"])
    plan = _complete_sample_lane(
        lane,
        mitotic_context_class=str(entry["mitotic_context_class"]),
        transformation_state=str(entry["transformation_state"]),
    )
    prefix = _lane_prefix(lane)
    held_id = f"syn-held-out-{prefix}"
    replication_id = f"syn-replication-{prefix}"
    held_assay = next(
        item for item in plan["assays"] if item["assay_id"] == held_id
    )
    replication_assay = next(
        item for item in plan["assays"] if item["assay_id"] == replication_id
    )
    lock = held_assay["held_out_lock"]
    replication_lock = replication_assay["replication_lock"]
    evidence = _promotion_evidence(lane)
    design = entry["replication_design"]
    design["discovery_site_id"] = evidence["discovery_site_id"]
    design["replication_site_id"] = evidence["replication_site_id"]
    design["discovery_edit_event_family_ids"] = list(
        evidence["discovery_event_family_ids"]  # type: ignore[arg-type]
    )
    design["replication_edit_event_family_ids"] = list(
        evidence["replication_event_family_ids"]  # type: ignore[arg-type]
    )
    design["frozen_exposure_identity_id"] = lock["frozen_exposure_id"]
    design["frozen_endpoint_identity_id"] = lock["frozen_endpoint_id"]
    design["frozen_margin_identity_id"] = lock["frozen_margin_id"]
    design["frozen_protocol_identity_id"] = replication_lock[
        "frozen_protocol_id"
    ]
    design["frozen_analysis_identity_id"] = replication_lock[
        "frozen_analysis_id"
    ]
    design["analytic_transfer_result_sha256"] = evidence[
        "analytic_transfer_result_sha256"
    ]
    design["site2_blinding_state"] = "blinded"
    design["site2_blinding_evidence_sha256"] = evidence[
        "site2_blinding_evidence_sha256"
    ]
    held_receipt = plan["completed"][held_id]
    replication_receipt = plan["completed"][replication_id]
    entry["sample_stewardship_promotion"] = {
        "held_out_assay_id": held_id,
        "replication_assay_id": replication_id,
        "held_out_receipt_id": held_receipt["receipt_id"],
        "replication_receipt_id": replication_receipt["receipt_id"],
        "held_out_receipt_sha256": held_receipt["receipt_sha256"],
        "replication_receipt_sha256": replication_receipt["receipt_sha256"],
        "sample_plan_sha256": sample_stewardship_plan_sha256(plan),
    }
    return plan


def _promotion_matches_lane(promotion: object, lane: str) -> bool:
    if not isinstance(promotion, dict):
        return False
    held_id = str(promotion.get("held_out_assay_id", ""))
    expected = f"syn-held-out-{_lane_prefix(lane)}"
    return held_id == expected


def _bound_sample_plan(candidate: object) -> dict[str, object] | None:
    if not isinstance(candidate, dict):
        return None
    plan = None
    for entry in candidate.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("functional_hit_state") != "replicated_full_phenocopy":
            continue
        lane = str(entry.get("discovery_lane"))
        if _promotion_matches_lane(entry.get("sample_stewardship_promotion"), lane):
            plan = _complete_sample_lane(lane)
        else:
            plan = bind_sample_promotion(entry)
    return plan


def validate_candidate_ledger(
    value: object,
    *,
    public_only: bool = False,
    sample_plan: dict[str, object] | None = None,
):
    if sample_plan is None:
        sample_plan = _bound_sample_plan(value)
    return validate_candidate_ledger_engine(
        value, public_only=public_only, sample_plan=sample_plan
    )


def rank_candidates(
    value: object,
    *,
    sample_plan: dict[str, object] | None = None,
):
    if sample_plan is None:
        sample_plan = _bound_sample_plan(value)
    return rank_candidates_engine(value, sample_plan=sample_plan)


class CandidateLedgerTests(unittest.TestCase):
    def fixture(self) -> dict[str, object]:
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def plan_replication(self, entry: dict[str, object]) -> None:
        entry["replication_design"] = {
            "discovery_site_id": "site-discovery",
            "replication_site_id": "site-replication",
            "discovery_edit_event_family_ids": ["edit-family-discovery"],
            "replication_edit_event_family_ids": ["edit-family-held-out"],
            "frozen_protocol_identity_id": "frozen-protocol-v1",
            "frozen_exposure_identity_id": "frozen-exposure-v1",
            "frozen_endpoint_identity_id": "frozen-endpoint-v1",
            "frozen_margin_identity_id": "frozen-margin-v1",
            "frozen_analysis_identity_id": "frozen-analysis-v1",
            "analytic_transfer_result_sha256": None,
            "site2_blinding_state": "not_attempted",
            "site2_blinding_evidence_sha256": None,
        }

    def bind_replication_evidence(self, entry: dict[str, object]) -> None:
        self.plan_replication(entry)
        design = entry["replication_design"]
        design["analytic_transfer_result_sha256"] = (  # type: ignore[index]
            ANALYTIC_TRANSFER_RECEIPT
        )
        design["site2_blinding_state"] = "blinded"  # type: ignore[index]
        design["site2_blinding_evidence_sha256"] = (  # type: ignore[index]
            SITE2_BLINDING_RECEIPT
        )

    def assert_runtime_and_schema_reject(
        self,
        candidate: dict[str, object],
        message: str | None = None,
    ) -> None:
        context = (
            self.assertRaisesRegex(CandidateLedgerError, message)
            if message is not None
            else self.assertRaises(CandidateLedgerError)
        )
        with context:
            validate_candidate_ledger(candidate)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(candidate)))

    def pass_rescue_gates(self, entry: dict[str, object]) -> None:
        entry["rescue_gates"] = {
            name: "pass" for name in RescueGates.__dataclass_fields__
        }
        entry["independent_replication"] = "replicated"
        entry["decision_effect"] = "promote"
        entry["functional_hit_state"] = "replicated_full_phenocopy"
        entry["screen_context"] = "participant_lineage_tier_b"
        entry["translation_state"] = "preclinical_replication_ready"
        entry["discovery_lane"] = "correction_trained_phenotypic"
        entry["therapeutic_context"] = "postnatal_nontransformed_proliferative"
        entry["architecture_lineage_state"] = "architecture_preserving"
        entry["mitotic_context_class"] = "epithelial_architecture_dependent"
        entry["transformation_state"] = "primary_finite"
        entry["rescue_gates"][
            "therapeutic_context_and_architecture_lineage"
        ] = "pass"
        self.bind_replication_evidence(entry)
        bind_sample_promotion(entry)

    def promoted_conditional_fixture(
        self,
    ) -> tuple[dict[str, object], dict[str, object]]:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        self.pass_rescue_gates(entry)
        entry["advancement_state"] = "conditional_hold"
        return candidate, bind_sample_promotion(entry)

    def pass_held_out_confirmation_gates(self, entry: dict[str, object]) -> None:
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["decision_effect"] = "promote"
        entry["program_gate"] = "exposure"
        entry["advancement_state"] = "conditional_hold"
        entry["translation_state"] = "mechanism_only"
        entry["discovery_lane"] = "correction_trained_phenotypic"
        entry["independent_replication"] = "not_attempted"
        gates = entry["rescue_gates"]
        for name in HELD_OUT_CONFIRMATION_GATE_NAMES:
            gates[name] = "pass"  # type: ignore[index]
        gates["analytic_transfer_pass"] = "not_attempted"  # type: ignore[index]
        gates["biological_replication_pass"] = "not_attempted"  # type: ignore[index]
        gates["blinded_replication_execution"] = "not_attempted"  # type: ignore[index]
        gates["independent_replication"] = "not_attempted"  # type: ignore[index]
        gates["replication_provenance"] = "not_attempted"  # type: ignore[index]
        if entry["functional_hit_state"] == "graded_partial_hit":
            gates["proximal_engagement"] = "pass"  # type: ignore[index]
        elif entry["functional_hit_state"] == "mechanism_discordant_hit":
            gates["proximal_engagement"] = "fail"  # type: ignore[index]
        self.plan_replication(entry)

    def pass_pending_full_phenocopy_gates(
        self,
        entry: dict[str, object],
    ) -> None:
        entry["functional_hit_state"] = "full_phenocopy_pending_replication"
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["decision_effect"] = "promote"
        entry["program_gate"] = "exposure"
        entry["advancement_state"] = "conditional_hold"
        entry["screen_context"] = "participant_lineage_tier_b"
        entry["translation_state"] = "preclinical_replication_ready"
        entry["discovery_lane"] = "correction_trained_phenotypic"
        entry["therapeutic_context"] = "postnatal_nontransformed_proliferative"
        entry["architecture_lineage_state"] = "architecture_preserving"
        entry["mitotic_context_class"] = "epithelial_architecture_dependent"
        entry["transformation_state"] = "primary_finite"
        entry["independent_replication"] = "not_attempted"
        gates = entry["rescue_gates"]
        for name in FULL_PHENOCOPY_PRE_REPLICATION_GATE_NAMES:
            gates[name] = "pass"  # type: ignore[index]
        gates["analytic_transfer_pass"] = "not_attempted"  # type: ignore[index]
        gates["biological_replication_pass"] = "not_attempted"  # type: ignore[index]
        gates["blinded_replication_execution"] = "not_attempted"  # type: ignore[index]
        gates["independent_replication"] = "not_attempted"  # type: ignore[index]
        gates["replication_provenance"] = "not_attempted"  # type: ignore[index]
        self.plan_replication(entry)

    def test_synthetic_template_round_trips_through_public_gate(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            list(Draft202012Validator(schema).iter_errors(self.fixture())),
            [],
        )
        ledger = load_candidate_ledger(TEMPLATE, public_only=True)
        self.assertEqual(
            [entry.role for entry in ledger.entries],
            [
                "challenger",
                "comparator",
                "mechanistic_control",
                "challenger",
                "lead",
                "no_go",
            ],
        )
        self.assertEqual(validate_candidate_ledger(ledger, public_only=True), ledger)
        expected = self.fixture()
        expected["entries"] = sorted(  # type: ignore[index,assignment]
            expected["entries"],  # type: ignore[index]
            key=lambda entry: entry["candidate_id"],
        )
        self.assertEqual(ledger.to_dict(), expected)

    def test_v6_bytes_are_not_silently_reinterpreted_as_v7(self) -> None:
        candidate = self.fixture()
        candidate["schema"] = "mva.track2-candidate-ledger/v6"
        self.assert_runtime_and_schema_reject(candidate, "schema must be")

    def test_v5_bytes_are_not_silently_reinterpreted_as_v6(self) -> None:
        candidate = self.fixture()
        candidate["schema"] = "mva.track2-candidate-ledger/v5"
        self.assert_runtime_and_schema_reject(candidate, "schema must be")

    def test_v4_bytes_are_not_silently_reinterpreted_as_v6(self) -> None:
        candidate = self.fixture()
        candidate["schema"] = "mva.track2-candidate-ledger/v4"
        self.assert_runtime_and_schema_reject(candidate, "schema must be")

    def test_v3_bytes_are_not_silently_reinterpreted_as_v6(self) -> None:
        candidate = self.fixture()
        candidate["schema"] = "mva.track2-candidate-ledger/v3"
        self.assert_runtime_and_schema_reject(candidate, "schema must be")

    def test_normalized_audit_fields_are_all_mandatory(self) -> None:
        expected = {
            "candidate_id", "role", "experimental_priority", "program_gate", "claim", "privacy_class",
            "direction", "assessment_status", "decision_effect",
            "advancement_state", "functional_hit_state", "screen_context",
            "no_hit_basis", "translation_state", "discovery_lane",
            "therapeutic_context", "architecture_lineage_state",
            "mitotic_context_class", "transformation_state",
            "rescue_gates", "replication_design", "sample_stewardship_promotion",
            "source_class", "source_identifier",
            "source_version", "source_url", "search_date", "model_system",
            "nominal_concentration_uM", "exposure_class",
            "direct_target_evidence", "exact_allele_evidence",
            "checkpoint_evidence", "human_pd_evidence",
            "pediatric_information", "oncology_risk", "regulatory_eligibility",
            "result", "unit", "independent_replication", "uncertainty",
            "counterevidence", "limitations", "not_assessable_reason",
            "causal_distance_score", "parent_source_class",
            "parent_candidate_id",
        }
        self.assertEqual(set(CandidateEntry.__dataclass_fields__), expected)
        candidate = self.fixture()
        del candidate["entries"][0]["claim"]  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "fields must be exactly"):
            validate_candidate_ledger(candidate)
        protocol = self.fixture()
        del protocol["search_protocol"]["notes"]  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "fields must be exactly"):
            validate_candidate_ledger(protocol)

    def test_not_assessable_invariants_prevent_negative_inference(self) -> None:
        mutations = (
            ("direction", "supports", "neutral direction"),
            ("result", "absent", "cannot contain a result"),
            ("unit", "categorical", "cannot contain a result"),
            ("independent_replication", "not_attempted", "replication state"),
            ("decision_effect", "exclude", "cannot promote, demote, or exclude"),
            ("not_assessable_reason", None, "expected text"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][5][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(CandidateLedgerError, message):
                    validate_candidate_ledger(candidate)

    def test_assessed_status_requires_result_and_null_gap_reason(self) -> None:
        mutations = (
            ("result", None, "requires a result"),
            ("not_assessable_reason", "Not actually unavailable.", "must set"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][0][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(CandidateLedgerError, message):
                    validate_candidate_ledger(candidate)

    def test_functional_hit_state_is_required_and_strict(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)

        missing = self.fixture()
        del missing["entries"][0]["functional_hit_state"]  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "fields must be exactly"):
            validate_candidate_ledger(missing)
        self.assertTrue(list(validator.iter_errors(missing)))

        invalid = self.fixture()
        invalid["entries"][0]["functional_hit_state"] = "partial"  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "functional_hit_state"):
            validate_candidate_ledger(invalid)
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_causal_distance_score_mismatch_fails_closed(self) -> None:
        candidate = self.fixture()
        candidate["entries"][0]["causal_distance_score"] = 0  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "causal_distance_score"):
            validate_candidate_ledger(candidate)
        candidate = self.fixture()
        candidate["entries"][0]["causal_distance_score"] = 4  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "causal_distance_score"):
            validate_candidate_ledger(candidate)

    def test_active_lead_requires_exact_allele_and_checkpoint(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["advancement_state"] = "active_lead"
        with self.assertRaisesRegex(CandidateLedgerError, "exact_allele_evidence"):
            validate_candidate_ledger(candidate)

    def test_lead_direct_target_requires_exact_allele(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["direct_target_evidence"] = "positive"
        entry["causal_distance_score"] = 2
        with self.assertRaisesRegex(CandidateLedgerError, "direct_target_evidence"):
            validate_candidate_ledger(candidate)

    def test_active_lead_forbidden_when_oncology_stop(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        entry["oncology_risk"] = "stop"
        with self.assertRaisesRegex(CandidateLedgerError, "oncology_risk stop"):
            validate_candidate_ledger(candidate)

    def test_active_lead_cannot_skip_nested_identity(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        with self.assertRaisesRegex(CandidateLedgerError, "nested identity"):
            validate_candidate_ledger(candidate)

    def test_surplus_keys_duplicate_ids_and_duplicate_keys_rejected(self) -> None:
        duplicate = self.fixture()
        duplicate["entries"][1]["candidate_id"] = duplicate["entries"][0]["candidate_id"]  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "duplicate candidate_id"):
            validate_candidate_ledger(duplicate)
        surplus = self.fixture()
        surplus["entries"][0]["rank"] = 1  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "fields must be exactly"):
            validate_candidate_ledger(surplus)
        surplus_root = self.fixture()
        surplus_root["ranker_note"] = "extra"
        with self.assertRaisesRegex(CandidateLedgerError, "fields must be exactly"):
            validate_candidate_ledger(surplus_root)
        payload = (
            '{"schema":"mva.track2-candidate-ledger/v7",'
            '"ledger_id":"one","ledger_id":"two",'
            '"purpose":"A sufficiently long synthetic purpose.",'
            '"search_protocol":{"protocol_id":"synthetic-protocol",'
            '"searched_on":"2026-08-29","query_axes":["axis-a"],'
            '"exclusion_axes":["axis-b"],'
            '"notes":"Synthetic notes."},"entries":[]}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "ledger.json")
            path.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(CandidateLedgerError, "duplicate JSON key"):
                load_candidate_ledger(path)

    def test_rank_candidates_exposes_queue_ties_and_rescue_holds(self) -> None:
        ranking = rank_candidates(load_candidate_ledger(TEMPLATE, public_only=True))
        self.assertEqual(ranking["schema"], "mva.track2-candidate-ledger/v7")
        self.assertEqual(ranking["n_entries"], 6)
        self.assertIsNone(ranking["active_lead_id"])
        self.assertEqual(
            ranking["exposure_regulatory_screened_ids"],
            ["syn-comparator-gga", "syn-lead-chaperone-amplifier"],
        )
        self.assertEqual(
            ranking["conditional_probe_ids"],
            ["syn-lead-chaperone-amplifier"],
        )
        self.assertEqual(ranking["held_out_confirmation_ids"], [])
        self.assertEqual(
            ranking["functional_hit_states"],
            {
                "syn-challenger-nad-sirt": "not_tested",
                "syn-comparator-gga": "not_tested",
                "syn-control-proteasome": "not_tested",
                "syn-gap-exact-allele": "not_tested",
                "syn-lead-chaperone-amplifier": "not_tested",
                "syn-nogo-antimitotic": "not_tested",
            },
        )
        self.assertEqual(
            ranking["discovery_lanes"],
            {
                entry["candidate_id"]: entry["discovery_lane"]
                for entry in self.fixture()["entries"]  # type: ignore[index]
            },
        )
        self.assertEqual(
            ranking["replication_states"]["syn-lead-chaperone-amplifier"],
            {
                "analytic_transfer_pass": "not_attempted",
                "biological_replication_pass": "not_attempted",
                "blinded_replication_execution": "not_attempted",
            },
        )
        self.assertEqual(
            ranking["replication_evidence"]["syn-lead-chaperone-amplifier"],
            {
                "analytic_transfer_result_sha256": None,
                "site2_blinding_state": "not_attempted",
                "site2_blinding_evidence_sha256": None,
            },
        )
        self.assertEqual(
            ranking["experimental_priority_order"],
            [
                "syn-lead-chaperone-amplifier",
                "syn-challenger-nad-sirt",
                "syn-comparator-gga",
            ],
        )
        self.assertEqual(ranking["equal_causal_score_groups"], [])
        self.assertEqual(ranking["rejected_ids"], ["syn-nogo-antimitotic"])
        lead_reasons = ranking["candidate_gate_reasons"][
            "syn-lead-chaperone-amplifier"
        ]
        self.assertEqual(lead_reasons["screening"], [])
        self.assertEqual(lead_reasons["evidence"], [])
        self.assertIn("correction_rescue:not_attempted", lead_reasons["rescue"])
        self.assertIn(
            "correction_rescue:not_attempted",
            lead_reasons["held_out_confirmation"],
        )
        self.assertIn(
            "reciprocal_recreation:not_attempted",
            lead_reasons["held_out_confirmation"],
        )
        self.assertFalse(lead_reasons["held_out_confirmation_eligible"])
        self.assertFalse(lead_reasons["active_lead_eligible"])
        self.assertTrue(ranking["sample_stewardship_promotion_bound"])
        self.assertTrue(ranking["sample_context_qualification_bound"])
        self.assertEqual(ranking["claim_boundary"], CLAIM_BOUNDARY)

    def test_release_bundle_binds_canonical_ledger_to_exact_ranking(self) -> None:
        ledger = validate_candidate_ledger(self.fixture(), public_only=True)
        ledger_bytes = canonical_candidate_ledger_bytes(ledger, public_only=True)
        ranking_bytes = canonical_candidate_ranking_bytes(ledger)

        released_ledger, released_ranking = validate_candidate_release_bundle_bytes(
            ledger_bytes,
            ranking_bytes,
        )

        self.assertEqual(
            released_ledger.to_dict(),
            json.loads(ledger_bytes),
        )
        self.assertEqual(released_ranking, rank_candidates(released_ledger))
        self.assertEqual(validate_candidate_release_ledger_bytes(ledger_bytes), ledger)
        self.assertTrue(ledger_bytes.endswith(b"\n"))
        self.assertTrue(ranking_bytes.endswith(b"\n"))

    def test_release_bundle_rejects_noncanonical_or_stale_bytes(self) -> None:
        ledger = validate_candidate_ledger(self.fixture(), public_only=True)
        ledger_bytes = canonical_candidate_ledger_bytes(ledger, public_only=True)
        ranking_bytes = canonical_candidate_ranking_bytes(ledger)

        with self.assertRaisesRegex(CandidateLedgerError, "canonical rendering"):
            validate_candidate_release_bundle_bytes(
                ledger_bytes.replace(b"\n", b"\r\n"),
                ranking_bytes,
            )

        stale = json.loads(ranking_bytes)
        stale["conditional_probe_ids"] = []
        stale_bytes = (json.dumps(stale, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        with self.assertRaisesRegex(CandidateLedgerError, "exact ranking"):
            validate_candidate_release_bundle_bytes(ledger_bytes, stale_bytes)

    def test_canonical_ledger_is_entry_order_invariant(self) -> None:
        forward = self.fixture()
        reversed_rows = self.fixture()
        reversed_rows["entries"].reverse()  # type: ignore[union-attr]
        forward_bytes = canonical_candidate_ledger_bytes(forward, public_only=True)
        reversed_bytes = canonical_candidate_ledger_bytes(
            reversed_rows,
            public_only=True,
        )
        self.assertEqual(forward_bytes, reversed_bytes)

        noncanonical = (
            json.dumps(forward, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
        self.assertNotEqual(noncanonical, forward_bytes)
        with self.assertRaisesRegex(CandidateLedgerError, "canonical rendering"):
            validate_candidate_release_ledger_bytes(noncanonical)

    def test_release_bundle_rejects_controlled_evidence(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["source_class"] = "manual_review"
        entry["privacy_class"] = "controlled"
        ledger = validate_candidate_ledger(candidate)
        ledger_bytes = canonical_candidate_ledger_bytes(ledger)
        ranking_bytes = canonical_candidate_ranking_bytes(ledger)
        with self.assertRaisesRegex(CandidateLedgerError, "forbidden privacy classes"):
            validate_candidate_release_bundle_bytes(ledger_bytes, ranking_bytes)

    def test_release_stager_writes_new_exact_pair_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate-release"
            command = [
                sys.executable,
                str(RELEASE_SCRIPT),
                "--input",
                str(TEMPLATE),
                "--output-dir",
                str(output),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertFalse(summary["published"])
            ledger_bytes = (output / "track2-candidate-ledger.json").read_bytes()
            ranking_bytes = (output / "track2-candidate-ranking.json").read_bytes()
            validate_candidate_release_bundle_bytes(ledger_bytes, ranking_bytes)

            refused = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("refusing to overwrite", refused.stderr)

    def test_sample_plan_loader_is_strict(self) -> None:
        payload = SAMPLE_TEMPLATE.read_bytes()
        self.assertEqual(
            load_sample_stewardship_plan_bytes(payload),
            json.loads(payload),
        )
        for invalid, message in (
            (b"\xef\xbb\xbf" + payload, "UTF-8 BOM"),
            (b'{"schema": 1, "schema": 2}', "duplicate JSON key"),
            (b"[]", "must be an object"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(CandidateLedgerError, message):
                    load_sample_stewardship_plan_bytes(invalid)

    def test_promoted_ledger_clis_require_and_bind_sample_plan(self) -> None:
        candidate, plan = self.promoted_conditional_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.json"
            plan_path = root / "sample-plan.json"
            ledger_path.write_text(
                json.dumps(candidate, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            plan_path.write_text(
                json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )

            missing = subprocess.run(
                [sys.executable, str(RANK_SCRIPT), "--input", str(ledger_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("requires a sample-stewardship plan", missing.stderr)

            missing_release_output = root / "missing-plan-release"
            missing_release = subprocess.run(
                [
                    sys.executable,
                    str(RELEASE_SCRIPT),
                    "--input",
                    str(ledger_path),
                    "--output-dir",
                    str(missing_release_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(missing_release.returncode, 0)
            self.assertIn(
                "requires a sample-stewardship plan", missing_release.stderr
            )
            self.assertFalse(missing_release_output.exists())

            rank_command = [
                sys.executable,
                str(RANK_SCRIPT),
                "--input",
                str(ledger_path),
                "--sample-plan",
                str(plan_path),
                "--public-only",
            ]
            ranked = subprocess.run(
                rank_command,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ranked.returncode, 0, ranked.stderr)
            self.assertIsNone(json.loads(ranked.stdout)["active_lead_id"])

            output = root / "release"
            staged = subprocess.run(
                [
                    sys.executable,
                    str(RELEASE_SCRIPT),
                    "--input",
                    str(ledger_path),
                    "--sample-plan",
                    str(plan_path),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(staged.returncode, 0, staged.stderr)
            loaded_plan = load_sample_stewardship_plan(plan_path)
            validate_candidate_release_bundle_bytes(
                (output / "track2-candidate-ledger.json").read_bytes(),
                (output / "track2-candidate-ranking.json").read_bytes(),
                sample_plan=loaded_plan,
            )
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                ["track2-candidate-ledger.json", "track2-candidate-ranking.json"],
            )

            stale_plan = json.loads(json.dumps(plan, allow_nan=False))
            stale_plan["inventory"]["renewable_nonparticipant"][  # type: ignore[index]
                "dna_aliquots"
            ] += 1
            stale_path = root / "stale-plan.json"
            stale_path.write_text(
                json.dumps(stale_plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            stale = subprocess.run(
                [
                    sys.executable,
                    str(RANK_SCRIPT),
                    "--input",
                    str(ledger_path),
                    "--sample-plan",
                    str(stale_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("does not match the submitted sample plan", stale.stderr)

    def test_candidate_specific_screening_is_symmetric(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][1]  # type: ignore[index]
        entry["regulatory_eligibility"] = "mixed_or_restricted"
        entry["exposure_class"] = "candidate_specific_plausible"
        entry["pediatric_information"] = "present"
        entry["oncology_risk"] = "caution"
        ranking = rank_candidates(candidate)
        self.assertEqual(
            ranking["exposure_regulatory_screened_ids"],
            [
                "syn-challenger-nad-sirt",
                "syn-comparator-gga",
                "syn-lead-chaperone-amplifier",
            ],
        )
        self.assertEqual(
            ranking["conditional_probe_ids"],
            ["syn-challenger-nad-sirt", "syn-lead-chaperone-amplifier"],
        )
        self.assertIsNone(ranking["active_lead_id"])

    def test_screening_does_not_inherit_another_candidate_exposure_cutoff(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][1]  # type: ignore[index]
        entry["regulatory_eligibility"] = "current"
        entry["exposure_class"] = "candidate_specific_plausible"
        entry["pediatric_information"] = "present"
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-challenger-nad-sirt",
            ranking["exposure_regulatory_screened_ids"],
        )

        entry["exposure_class"] = "exploratory_5um"
        entry["nominal_concentration_uM"] = 5
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-challenger-nad-sirt",
            ranking["exposure_regulatory_screened_ids"],
        )

    def test_unassessed_oncology_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["oncology_risk"] = "not_assessable"
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )

    def test_unassessed_exposure_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["exposure_class"] = "not_assessable"
        comparator["nominal_concentration_uM"] = None
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )

    def test_absent_or_unassessed_pediatric_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        self.assertEqual(comparator["pediatric_information"], "present")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        for value in ("absent", "not_assessable"):
            with self.subTest(pediatric_information=value):
                comparator["pediatric_information"] = value
                ranking = rank_candidates(candidate)
                self.assertNotIn(
                    "syn-comparator-gga",
                    ranking["exposure_regulatory_screened_ids"],
                )
        comparator["pediatric_information"] = "present"
        challenger = candidate["entries"][1]  # type: ignore[index]
        self.assertEqual(challenger["advancement_state"], "conditional_hold")
        self.assertEqual(challenger["pediatric_information"], "not_assessable")
        validate_candidate_ledger(candidate)

    def test_immortalized_or_reprogrammed_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        self.assertEqual(comparator["transformation_state"], "not_assessable")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        for value in ("immortalized_or_transformed", "reprogrammed"):
            with self.subTest(transformation_state=value):
                comparator["transformation_state"] = value
                ranking = rank_candidates(candidate)
                self.assertNotIn(
                    "syn-comparator-gga",
                    ranking["exposure_regulatory_screened_ids"],
                )
        comparator["transformation_state"] = "not_assessable"
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")
        self.assertEqual(lead["transformation_state"], "not_assessable")
        validate_candidate_ledger(candidate)

    def test_isogenic_a0_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        self.assertEqual(comparator["transformation_state"], "not_assessable")
        self.assertEqual(comparator["screen_context"], "renewable_nonparticipant_a0")
        self.assertEqual(comparator["translation_state"], "mechanism_only")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["transformation_state"] = "renewable_nontransformed_isogenic"
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["transformation_state"] = "not_assessable"
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")
        self.assertEqual(lead["screen_context"], "renewable_nonparticipant_a0")
        self.assertEqual(lead["translation_state"], "mechanism_only")
        lead["transformation_state"] = "renewable_nontransformed_isogenic"
        validate_candidate_ledger(candidate)
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-lead-chaperone-amplifier",
            ranking["exposure_regulatory_screened_ids"],
        )
        self.assertEqual(lead["advancement_state"], "conditional_hold")

    def test_mixed_or_unsafe_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        self.assertEqual(comparator["functional_hit_state"], "not_tested")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["functional_hit_state"] = "mixed_or_unsafe"
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        validate_candidate_ledger(candidate)
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")
        self.assertEqual(lead["functional_hit_state"], "not_tested")

    def test_no_hit_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        self.assertEqual(comparator["functional_hit_state"], "not_tested")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["functional_hit_state"] = "no_hit"
        comparator["no_hit_basis"] = "valid_a0_negative"
        comparator["assessment_status"] = "negative"
        comparator["direction"] = "contradicts"
        comparator["decision_effect"] = "demote"
        comparator["result"] = "no_hit"
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        validate_candidate_ledger(candidate)
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")
        self.assertEqual(lead["functional_hit_state"], "not_tested")

    def test_rejected_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["advancement_state"] = "rejected"
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        validate_candidate_ledger(candidate)
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")

    def test_not_assessable_advancement_cannot_enter_screened_set(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        ranking = rank_candidates(candidate)
        self.assertIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        comparator["advancement_state"] = "not_assessable"
        ranking = rank_candidates(candidate)
        self.assertNotIn(
            "syn-comparator-gga",
            ranking["exposure_regulatory_screened_ids"],
        )
        validate_candidate_ledger(candidate)
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")

    def test_role_relabel_cannot_change_manual_queue_or_screening(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][1]  # type: ignore[index]
        entry["regulatory_eligibility"] = "current"
        entry["exposure_class"] = "candidate_specific_plausible"
        entry["pediatric_information"] = "present"
        challenger_ranking = rank_candidates(candidate)

        entry["role"] = "comparator"
        comparator_ranking = rank_candidates(candidate)

        self.assertEqual(
            comparator_ranking["experimental_priority_order"],
            challenger_ranking["experimental_priority_order"],
        )
        self.assertEqual(
            comparator_ranking["exposure_regulatory_screened_ids"],
            challenger_ranking["exposure_regulatory_screened_ids"],
        )

    def test_ineligible_incumbent_cannot_remain_conditional_probe(self) -> None:
        candidate = self.fixture()
        lead = candidate["entries"][0]  # type: ignore[index]
        lead["regulatory_eligibility"] = "expired_or_absent"
        self.assert_runtime_and_schema_reject(
            candidate,
            "regulatory_eligibility expired_or_absent cannot occupy "
            "lead advancement",
        )
        lead["regulatory_eligibility"] = "current"
        lead["exposure_class"] = "nontranslational_high"
        lead["nominal_concentration_uM"] = 10
        self.assert_runtime_and_schema_reject(
            candidate,
            "exposure_class nontranslational_high cannot occupy "
            "lead advancement",
        )
        lead["exposure_class"] = "leq_2um"
        lead["nominal_concentration_uM"] = 2
        lead["oncology_risk"] = "stop"
        self.assert_runtime_and_schema_reject(
            candidate,
            "oncology_risk stop cannot occupy lead advancement",
        )
        lead["oncology_risk"] = "not_assessable"
        self.assert_runtime_and_schema_reject(
            candidate,
            "oncology_risk not_assessable cannot occupy lead advancement",
        )

    def test_equal_causal_scores_are_visible_not_broken_by_role(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][1]  # type: ignore[index]
        entry["regulatory_eligibility"] = "current"
        entry["exposure_class"] = "candidate_specific_plausible"
        entry["pediatric_information"] = "present"
        entry["direct_target_evidence"] = "not_assessable"
        entry["causal_distance_score"] = 1
        ranking = rank_candidates(candidate)
        self.assertEqual(
            ranking["equal_causal_score_groups"],
            [{
                "causal_distance_score": 1,
                "candidate_ids": [
                    "syn-challenger-nad-sirt",
                    "syn-lead-chaperone-amplifier",
                ],
                "screened_candidate_ids": [
                    "syn-challenger-nad-sirt",
                    "syn-lead-chaperone-amplifier",
                ],
            }],
        )

    def test_equal_score_remains_visible_when_one_queued_row_fails_screening(self) -> None:
        candidate = self.fixture()
        challenger = candidate["entries"][1]  # type: ignore[index]
        challenger["direct_target_evidence"] = "not_assessable"
        challenger["causal_distance_score"] = 1
        ranking = rank_candidates(candidate)
        self.assertEqual(
            ranking["equal_causal_score_groups"],
            [{
                "causal_distance_score": 1,
                "candidate_ids": [
                    "syn-challenger-nad-sirt",
                    "syn-lead-chaperone-amplifier",
                ],
                "screened_candidate_ids": ["syn-lead-chaperone-amplifier"],
            }],
        )

    def test_duplicate_experimental_priority_fails_closed(self) -> None:
        candidate = self.fixture()
        candidate["entries"][1]["experimental_priority"] = 1  # type: ignore[index]
        with self.assertRaisesRegex(CandidateLedgerError, "duplicate experimental_priority"):
            validate_candidate_ledger(candidate)

    def test_adverse_or_excluded_row_cannot_remain_conditional(self) -> None:
        for field, value in (
            ("assessment_status", "negative"),
            ("direction", "contradicts"),
            ("decision_effect", "exclude"),
        ):
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][0][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(
                    CandidateLedgerError,
                    "positive supporting evidence",
                ):
                    validate_candidate_ledger(candidate)

    def test_json_schema_rejects_adverse_conditional_rows(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for field, value in (
            ("assessment_status", "negative"),
            ("direction", "contradicts"),
            ("decision_effect", "exclude"),
        ):
            with self.subTest(field=field):
                candidate = self.fixture()
                candidate["entries"][0][field] = value  # type: ignore[index]
                errors = list(validator.iter_errors(candidate))
                self.assertTrue(errors, f"schema accepted adverse {field}")

    def test_active_lead_requires_all_structured_rescue_gates(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        entry["decision_effect"] = "promote"
        entry["independent_replication"] = "replicated"
        entry["functional_hit_state"] = "replicated_full_phenocopy"
        entry["screen_context"] = "participant_lineage_tier_b"
        entry["translation_state"] = "preclinical_replication_ready"
        entry["discovery_lane"] = "correction_trained_phenotypic"
        entry["therapeutic_context"] = "postnatal_nontransformed_proliferative"
        entry["architecture_lineage_state"] = "architecture_preserving"
        entry["mitotic_context_class"] = "epithelial_architecture_dependent"
        entry["transformation_state"] = "primary_finite"
        entry["rescue_gates"][
            "therapeutic_context_and_architecture_lineage"
        ] = "pass"
        self.plan_replication(entry)
        with self.assertRaisesRegex(CandidateLedgerError, "every structured rescue"):
            validate_candidate_ledger(candidate)

        self.pass_rescue_gates(entry)
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "synthetic-only sample-stewardship evidence cannot authorize",
        ):
            validate_candidate_ledger(candidate)

    def test_only_replicated_full_phenocopy_may_be_active(self) -> None:
        for functional_hit_state in sorted(
            FUNCTIONAL_HIT_STATES - {"replicated_full_phenocopy"}
        ):
            with self.subTest(functional_hit_state=functional_hit_state):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["exact_allele_evidence"] = "positive"
                entry["checkpoint_evidence"] = "positive"
                entry["causal_distance_score"] = 3
                entry["program_gate"] = "segregation"
                entry["advancement_state"] = "active_lead"
                self.pass_rescue_gates(entry)
                entry["functional_hit_state"] = functional_hit_state
                self.assert_runtime_and_schema_reject(candidate)

    def test_graded_and_discordant_safe_hits_enter_held_out_confirmation(self) -> None:
        for functional_hit_state in sorted(HELD_OUT_CONFIRMATION_STATES):
            with self.subTest(functional_hit_state=functional_hit_state):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["functional_hit_state"] = functional_hit_state
                self.pass_held_out_confirmation_gates(entry)
                self.assertEqual(entry["translation_state"], "mechanism_only")
                self.assertEqual(entry["therapeutic_context"], "renewable_2d_surrogate")
                schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
                self.assertEqual(
                    list(Draft202012Validator(schema).iter_errors(candidate)),
                    [],
                )
                ranking = rank_candidates(candidate)
                self.assertEqual(
                    ranking["held_out_confirmation_ids"],
                    [entry["candidate_id"]],
                )
                reasons = ranking["candidate_gate_reasons"][entry["candidate_id"]]
                self.assertEqual(reasons["held_out_confirmation"], [])
                self.assertTrue(reasons["held_out_confirmation_eligible"])
                self.assertIsNone(ranking["active_lead_id"])

    def test_both_discovery_lanes_can_reach_meaningful_and_active_paths(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for discovery_lane in sorted(DISCOVERY_LANES):
            for path in (
                "graded",
                "full_pending",
                "replicated_full",
                "active",
            ):
                with self.subTest(discovery_lane=discovery_lane, path=path):
                    candidate = self.fixture()
                    entry = candidate["entries"][0]  # type: ignore[index]
                    if path == "graded":
                        entry["functional_hit_state"] = "graded_partial_hit"
                        self.pass_held_out_confirmation_gates(entry)
                    elif path == "full_pending":
                        self.pass_pending_full_phenocopy_gates(entry)
                    else:
                        entry["exact_allele_evidence"] = "positive"
                        entry["checkpoint_evidence"] = "positive"
                        entry["causal_distance_score"] = 3
                        entry["program_gate"] = (
                            "segregation" if path == "active" else "exposure"
                        )
                        if path == "active":
                            entry["advancement_state"] = "active_lead"
                        self.pass_rescue_gates(entry)
                    entry["discovery_lane"] = discovery_lane

                    if path == "active":
                        with self.assertRaisesRegex(
                            CandidateLedgerError,
                            "synthetic-only sample-stewardship evidence cannot authorize",
                        ):
                            validate_candidate_ledger(candidate)
                        self.assertEqual(
                            list(validator.iter_errors(candidate)), []
                        )
                        continue
                    validate_candidate_ledger(candidate)
                    self.assertEqual(list(validator.iter_errors(candidate)), [])
                    ranking = rank_candidates(candidate)
                    self.assertEqual(
                        ranking["discovery_lanes"][entry["candidate_id"]],
                        discovery_lane,
                    )
                    self.assertEqual(
                        ranking["held_out_confirmation_ids"],
                        [entry["candidate_id"]] if path == "graded" else [],
                    )
                    self.assertEqual(
                        ranking["active_lead_id"],
                        None,
                    )
                    if path in {"replicated_full", "active"}:
                        expected_analytic = (
                            ANALYTIC_TRANSFER_RECEIPT
                            if discovery_lane == "targeted_hypothesis"
                            else PHENOTYPE_TRANSFER_RECEIPT
                        )
                        expected_site2 = (
                            SITE2_BLINDING_RECEIPT
                            if discovery_lane == "targeted_hypothesis"
                            else PHENOTYPE_SITE2_RECEIPT
                        )
                        self.assertEqual(
                            ranking["replication_evidence"][entry["candidate_id"]],
                            {
                                "analytic_transfer_result_sha256": expected_analytic,
                                "site2_blinding_state": "blinded",
                                "site2_blinding_evidence_sha256": expected_site2,
                            },
                        )
                        self.assertTrue(
                            ranking["sample_stewardship_promotion_bound"]
                        )
                        self.assertTrue(
                            ranking["sample_context_qualification_bound"]
                        )

    def test_held_out_confirmation_fails_closed_on_each_nonnegotiable(self) -> None:
        for gate in HELD_OUT_CONFIRMATION_GATE_NAMES:
            with self.subTest(gate=gate):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["functional_hit_state"] = "graded_partial_hit"
                self.pass_held_out_confirmation_gates(entry)
                entry["rescue_gates"][gate] = "not_attempted"
                self.assert_runtime_and_schema_reject(
                    candidate,
                    "held-out functional hit states",
                )

        for field, value in (
            ("oncology_risk", "stop"),
            ("regulatory_eligibility", "expired_or_absent"),
            ("exposure_class", "nontranslational_high"),
        ):
            with self.subTest(screening_field=field):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["functional_hit_state"] = "mechanism_discordant_hit"
                self.pass_held_out_confirmation_gates(entry)
                entry[field] = value
                if field == "exposure_class":
                    entry["nominal_concentration_uM"] = 10
                self.assert_runtime_and_schema_reject(
                    candidate,
                    "cannot occupy lead advancement",
                )

        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["functional_hit_state"] = "mechanism_discordant_hit"
        self.pass_held_out_confirmation_gates(entry)
        entry["exposure_class"] = "exploratory_5um"
        entry["nominal_concentration_uM"] = 5
        self.assertEqual(
            rank_candidates(candidate)["held_out_confirmation_ids"],
            [],
        )

    def test_held_out_confirmation_requires_causal_and_advancing_evidence(self) -> None:
        mutations = (
            ("exact_allele_evidence", "negative"),
            ("checkpoint_evidence", "negative"),
            ("decision_effect", "defer"),
            ("decision_effect", "demote"),
            ("decision_effect", "no_change"),
            ("program_gate", "confirmation"),
            ("program_gate", "phase"),
            ("program_gate", "rna"),
            ("program_gate", "allelic_series"),
            ("program_gate", "stability"),
            ("no_hit_basis", "failed_controls"),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["functional_hit_state"] = "graded_partial_hit"
                self.pass_held_out_confirmation_gates(entry)
                entry[field] = value
                if field in {"exact_allele_evidence", "checkpoint_evidence"}:
                    entry["causal_distance_score"] = 2
                self.assert_runtime_and_schema_reject(candidate)

    def test_held_out_confirmation_rejects_replication_leakage_or_failure(self) -> None:
        mutations = (
            ("top", "independent_replication", "not_replicated"),
            ("top", "independent_replication", "replicated"),
            ("gate", "analytic_transfer_pass", "fail"),
            ("gate", "analytic_transfer_pass", "pass"),
            ("gate", "biological_replication_pass", "fail"),
            ("gate", "biological_replication_pass", "pass"),
            ("gate", "blinded_replication_execution", "fail"),
            ("gate", "blinded_replication_execution", "pass"),
            ("gate", "independent_replication", "fail"),
            ("gate", "independent_replication", "pass"),
            ("gate", "replication_provenance", "fail"),
            ("gate", "replication_provenance", "pass"),
        )
        for location, field, value in mutations:
            with self.subTest(location=location, field=field, value=value):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["functional_hit_state"] = "mechanism_discordant_hit"
                self.pass_held_out_confirmation_gates(entry)
                if location == "top":
                    entry[field] = value
                else:
                    entry["rescue_gates"][field] = value
                self.assert_runtime_and_schema_reject(candidate, "requires unattempted")

    def test_functional_hit_state_requires_state_consistent_proximal_engagement(self) -> None:
        for state, invalid_values in (
            ("graded_partial_hit", ("fail", "not_attempted", "not_applicable")),
            ("mechanism_discordant_hit", ("pass", "not_applicable")),
        ):
            for value in invalid_values:
                with self.subTest(state=state, value=value):
                    candidate = self.fixture()
                    entry = candidate["entries"][0]  # type: ignore[index]
                    entry["functional_hit_state"] = state
                    self.pass_held_out_confirmation_gates(entry)
                    entry["rescue_gates"]["proximal_engagement"] = value
                    self.assert_runtime_and_schema_reject(candidate)

    def test_replication_design_rejects_same_site_overlap_or_missing_lock(self) -> None:
        for mutation in ("same_site", "overlap"):
            with self.subTest(mutation=mutation):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["functional_hit_state"] = "graded_partial_hit"
                self.pass_held_out_confirmation_gates(entry)
                design = entry["replication_design"]
                if mutation == "same_site":
                    design["replication_site_id"] = design["discovery_site_id"]
                else:
                    design["replication_edit_event_family_ids"] = list(
                        design["discovery_edit_event_family_ids"]
                    )
                with self.assertRaisesRegex(
                    CandidateLedgerError,
                    "replication design",
                ):
                    validate_candidate_ledger(candidate)

        for field in (
            "frozen_protocol_identity_id",
            "frozen_exposure_identity_id",
            "frozen_endpoint_identity_id",
            "frozen_margin_identity_id",
            "frozen_analysis_identity_id",
        ):
            with self.subTest(missing_identity=field):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["functional_hit_state"] = "graded_partial_hit"
                self.pass_held_out_confirmation_gates(entry)
                entry["replication_design"][field] = None
                self.assert_runtime_and_schema_reject(candidate, "replication design")

    def test_pending_and_replicated_full_phenocopy_are_replication_consistent(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        self.pass_pending_full_phenocopy_gates(entry)
        validate_candidate_ledger(candidate)
        self.assertEqual(rank_candidates(candidate)["held_out_confirmation_ids"], [])

        for gate in FULL_PHENOCOPY_PRE_REPLICATION_GATE_NAMES:
            with self.subTest(pending_gate=gate):
                invalid = self.fixture()
                pending = invalid["entries"][0]  # type: ignore[index]
                self.pass_pending_full_phenocopy_gates(pending)
                pending["rescue_gates"][gate] = "not_attempted"
                self.assert_runtime_and_schema_reject(invalid)

        for location, field, value in (
            ("top", "independent_replication", "replicated"),
            ("top", "independent_replication", "not_replicated"),
            ("gate", "analytic_transfer_pass", "pass"),
            ("gate", "biological_replication_pass", "pass"),
            ("gate", "blinded_replication_execution", "pass"),
            ("gate", "independent_replication", "pass"),
            ("gate", "replication_provenance", "pass"),
        ):
            with self.subTest(location=location, field=field, value=value):
                invalid = self.fixture()
                pending = invalid["entries"][0]  # type: ignore[index]
                self.pass_pending_full_phenocopy_gates(pending)
                if location == "top":
                    pending[field] = value
                else:
                    pending["rescue_gates"][field] = value
                self.assert_runtime_and_schema_reject(invalid)

        replicated_candidate = self.fixture()
        replicated = replicated_candidate["entries"][0]  # type: ignore[index]
        replicated["exact_allele_evidence"] = "positive"
        replicated["checkpoint_evidence"] = "positive"
        replicated["causal_distance_score"] = 3
        replicated["program_gate"] = "exposure"
        self.pass_rescue_gates(replicated)
        validate_candidate_ledger(replicated_candidate)
        self.assertIsNone(rank_candidates(replicated_candidate)["active_lead_id"])

        for gate in RescueGates.__dataclass_fields__:
            with self.subTest(replicated_gate=gate):
                invalid = json.loads(json.dumps(replicated_candidate, allow_nan=False))
                invalid["entries"][0]["rescue_gates"][gate] = "fail"
                self.assert_runtime_and_schema_reject(invalid)

    def test_blinded_replication_execution_is_stage_consistent(self) -> None:
        missing = self.fixture()
        del missing["entries"][0]["rescue_gates"][  # type: ignore[index]
            "blinded_replication_execution"
        ]
        self.assert_runtime_and_schema_reject(missing, "rescue_gates fields")

        for state in ("graded_partial_hit", "full_phenocopy_pending_replication"):
            for value in ("pass", "fail", "not_applicable"):
                with self.subTest(stage=state, value=value):
                    candidate = self.fixture()
                    entry = candidate["entries"][0]  # type: ignore[index]
                    if state == "graded_partial_hit":
                        entry["functional_hit_state"] = state
                        self.pass_held_out_confirmation_gates(entry)
                    else:
                        self.pass_pending_full_phenocopy_gates(entry)
                    entry["rescue_gates"]["blinded_replication_execution"] = value
                    self.assert_runtime_and_schema_reject(
                        candidate,
                        "requires unattempted",
                    )

        for advancement_state in ("conditional_hold", "active_lead"):
            for value in ("not_attempted", "fail", "not_applicable"):
                with self.subTest(stage=advancement_state, value=value):
                    candidate = self.fixture()
                    entry = candidate["entries"][0]  # type: ignore[index]
                    entry["exact_allele_evidence"] = "positive"
                    entry["checkpoint_evidence"] = "positive"
                    entry["causal_distance_score"] = 3
                    entry["program_gate"] = (
                        "segregation"
                        if advancement_state == "active_lead"
                        else "exposure"
                    )
                    entry["advancement_state"] = advancement_state
                    self.pass_rescue_gates(entry)
                    entry["rescue_gates"]["blinded_replication_execution"] = value
                    self.assert_runtime_and_schema_reject(candidate)

    def test_replication_receipt_fields_are_required_and_strict(self) -> None:
        for field in (
            "analytic_transfer_result_sha256",
            "site2_blinding_state",
            "site2_blinding_evidence_sha256",
        ):
            with self.subTest(missing_field=field):
                candidate = self.fixture()
                del candidate["entries"][0]["replication_design"][field]  # type: ignore[index]
                self.assert_runtime_and_schema_reject(
                    candidate,
                    "replication_design fields",
                )

        for field in (
            "analytic_transfer_result_sha256",
            "site2_blinding_evidence_sha256",
        ):
            for value in ("a" * 63, "A" * 64, "g" * 64, ""):
                with self.subTest(malformed_field=field, value=value):
                    candidate = self.fixture()
                    entry = candidate["entries"][0]  # type: ignore[index]
                    entry["exact_allele_evidence"] = "positive"
                    entry["checkpoint_evidence"] = "positive"
                    entry["causal_distance_score"] = 3
                    entry["program_gate"] = "segregation"
                    entry["advancement_state"] = "active_lead"
                    self.pass_rescue_gates(entry)
                    entry["replication_design"][field] = value
                    self.assert_runtime_and_schema_reject(candidate, "SHA-256")

        candidate = self.fixture()
        candidate["entries"][0]["replication_design"][  # type: ignore[index]
            "site2_blinding_state"
        ] = "masked"
        self.assert_runtime_and_schema_reject(candidate, "site2_blinding_state")

    def test_replication_passes_require_distinct_bound_receipts(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        self.bind_replication_evidence(entry)
        for gate in (
            "analytic_transfer_pass",
            "biological_replication_pass",
            "blinded_replication_execution",
            "independent_replication",
            "replication_provenance",
        ):
            entry["rescue_gates"][gate] = "pass"
        entry["independent_replication"] = "replicated"
        validate_candidate_ledger(candidate)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(candidate)), [])

        schema_rejected_mutations = (
            ("design", "analytic_transfer_result_sha256", None),
            ("design", "site2_blinding_evidence_sha256", None),
            ("design", "site2_blinding_state", "unblinded"),
            ("gate", "analytic_transfer_pass", "fail"),
            ("top", "independent_replication", "not_attempted"),
        )
        for location, field, value in schema_rejected_mutations:
            with self.subTest(location=location, field=field, value=value):
                invalid = json.loads(json.dumps(candidate, allow_nan=False))
                if location == "design":
                    invalid["entries"][0]["replication_design"][field] = value
                elif location == "gate":
                    invalid["entries"][0]["rescue_gates"][field] = value
                else:
                    invalid["entries"][0][field] = value
                self.assert_runtime_and_schema_reject(invalid)

        runtime_only_mutations = (
            "same_site",
            "overlapping_edit_families",
            "reused_receipt",
        )
        for mutation in runtime_only_mutations:
            with self.subTest(cross_field_mutation=mutation):
                invalid = json.loads(json.dumps(candidate, allow_nan=False))
                design = invalid["entries"][0]["replication_design"]
                if mutation == "same_site":
                    design["replication_site_id"] = design["discovery_site_id"]
                elif mutation == "overlapping_edit_families":
                    design["replication_edit_event_family_ids"] = list(
                        design["discovery_edit_event_family_ids"]
                    )
                else:
                    design["site2_blinding_evidence_sha256"] = design[
                        "analytic_transfer_result_sha256"
                    ]
                with self.assertRaises(CandidateLedgerError):
                    validate_candidate_ledger(invalid)
                self.assertEqual(list(validator.iter_errors(invalid)), [])

    def test_unblinded_site2_evidence_records_failure_but_cannot_advance(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        self.plan_replication(entry)
        entry["replication_design"]["analytic_transfer_result_sha256"] = (  # type: ignore[index]
            ANALYTIC_TRANSFER_RECEIPT
        )
        entry["replication_design"]["site2_blinding_state"] = "unblinded"  # type: ignore[index]
        entry["replication_design"]["site2_blinding_evidence_sha256"] = (  # type: ignore[index]
            SITE2_BLINDING_RECEIPT
        )
        entry["rescue_gates"]["analytic_transfer_pass"] = "pass"
        entry["rescue_gates"]["blinded_replication_execution"] = "fail"
        entry["rescue_gates"]["biological_replication_pass"] = "fail"
        entry["rescue_gates"]["independent_replication"] = "fail"
        entry["rescue_gates"]["replication_provenance"] = "fail"
        entry["independent_replication"] = "not_replicated"
        validate_candidate_ledger(candidate)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            list(Draft202012Validator(schema).iter_errors(candidate)),
            [],
        )
        ranking = rank_candidates(candidate)
        self.assertIsNone(ranking["active_lead_id"])
        self.assertEqual(ranking["held_out_confirmation_ids"], [])

        invalid = json.loads(json.dumps(candidate, allow_nan=False))
        invalid["entries"][0]["rescue_gates"][
            "blinded_replication_execution"
        ] = "pass"
        self.assert_runtime_and_schema_reject(invalid)

    def test_no_hit_requires_context_matched_valid_negative_basis(self) -> None:
        for context, basis in (
            ("renewable_nonparticipant_a0", "valid_a0_negative"),
            ("minimal_participant_a1", "valid_participant_negative"),
            ("participant_lineage_tier_b", "valid_participant_negative"),
        ):
            with self.subTest(context=context):
                candidate = self.fixture()
                entry = candidate["entries"][2]  # type: ignore[index]
                entry["functional_hit_state"] = "no_hit"
                entry["screen_context"] = context
                entry["no_hit_basis"] = basis
                entry["assessment_status"] = "negative"
                entry["direction"] = "contradicts"
                entry["decision_effect"] = "demote"
                entry["result"] = "no_hit"
                validate_candidate_ledger(candidate)
                schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
                self.assertEqual(
                    list(Draft202012Validator(schema).iter_errors(candidate)),
                    [],
                )

        for basis in (
            "valid_a0_negative",
            "insufficient_material",
            "failed_controls",
            "unmeasured_exposure",
            "screen_failure",
        ):
            with self.subTest(invalid_participant_basis=basis):
                candidate = self.fixture()
                entry = candidate["entries"][2]  # type: ignore[index]
                entry["functional_hit_state"] = "no_hit"
                entry["screen_context"] = "participant_lineage_tier_b"
                entry["no_hit_basis"] = basis
                entry["assessment_status"] = "negative"
                entry["direction"] = "contradicts"
                entry["decision_effect"] = "demote"
                entry["result"] = "no_hit"
                self.assert_runtime_and_schema_reject(candidate, "no_hit")

    def test_active_lead_rejects_2d_or_unqualified_translation_context(self) -> None:
        mutations = (
            ("translation_state", "mechanism_only"),
            ("screen_context", "renewable_nonparticipant_a0"),
            ("therapeutic_context", "renewable_2d_surrogate"),
            ("architecture_lineage_state", "reduced_2d_surrogate"),
            ("therapeutic_context_and_architecture_lineage", "fail"),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["exact_allele_evidence"] = "positive"
                entry["checkpoint_evidence"] = "positive"
                entry["causal_distance_score"] = 3
                entry["program_gate"] = "segregation"
                entry["advancement_state"] = "active_lead"
                self.pass_rescue_gates(entry)
                if field == "therapeutic_context_and_architecture_lineage":
                    entry["rescue_gates"][field] = value
                else:
                    entry[field] = value
                self.assert_runtime_and_schema_reject(candidate)

    def test_active_lead_cannot_defer_or_demote(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for decision_effect in ("defer", "demote", "no_change"):
            with self.subTest(decision_effect=decision_effect):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["exact_allele_evidence"] = "positive"
                entry["checkpoint_evidence"] = "positive"
                entry["causal_distance_score"] = 3
                entry["program_gate"] = "segregation"
                entry["advancement_state"] = "active_lead"
                self.pass_rescue_gates(entry)
                entry["decision_effect"] = decision_effect
                with self.assertRaisesRegex(
                    CandidateLedgerError,
                    "decision_effect promote or retain",
                ):
                    validate_candidate_ledger(candidate)
                self.assertTrue(list(validator.iter_errors(candidate)))

    def test_exposure_class_and_nominal_concentration_are_cross_checked(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        mutations = (
            ("leq_2um", None),
            ("leq_2um", -1),
            ("leq_2um", 0),
            ("leq_2um", 3),
            ("candidate_specific_plausible", 999999),
            ("not_assessable", 1),
            ("nontranslational_high", 5),
        )
        for exposure_class, concentration in mutations:
            with self.subTest(
                exposure_class=exposure_class,
                concentration=concentration,
            ):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["exposure_class"] = exposure_class
                entry["nominal_concentration_uM"] = concentration
                with self.assertRaises(CandidateLedgerError):
                    validate_candidate_ledger(candidate)
                self.assertTrue(list(validator.iter_errors(candidate)))

    def test_active_lead_requires_complete_screening(self) -> None:
        for field, value in (
            ("oncology_risk", "not_assessable"),
            ("regulatory_eligibility", "not_assessable"),
            ("exposure_class", "not_assessable"),
            ("pediatric_information", "not_assessable"),
            ("pediatric_information", "absent"),
        ):
            with self.subTest(field=field, value=value):
                candidate = self.fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["exact_allele_evidence"] = "positive"
                entry["checkpoint_evidence"] = "positive"
                entry["causal_distance_score"] = 3
                entry["program_gate"] = "segregation"
                entry["advancement_state"] = "active_lead"
                entry[field] = value
                if field == "exposure_class":
                    entry["nominal_concentration_uM"] = None
                self.pass_rescue_gates(entry)
                expected = (
                    "oncology_risk not_assessable cannot occupy lead advancement"
                    if field == "oncology_risk"
                    else "exposure_class not_assessable cannot occupy lead advancement"
                    if field == "exposure_class"
                    else "passed oncology, regulatory, pediatric, and candidate-specific exposure"
                )
                with self.assertRaisesRegex(CandidateLedgerError, expected):
                    validate_candidate_ledger(candidate)

    def test_public_gate_rejects_controlled_class_and_source_mismatch(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["source_class"] = "manual_review"
        entry["privacy_class"] = "controlled"
        validate_candidate_ledger(candidate)
        with self.assertRaisesRegex(CandidateLedgerError, "forbidden privacy classes"):
            validate_candidate_ledger(candidate, public_only=True)
        entry["privacy_class"] = "synthetic"
        entry["source_class"] = "controlled_source"
        with self.assertRaisesRegex(CandidateLedgerError, "cannot label a controlled source"):
            validate_candidate_ledger(candidate)

    def test_public_software_cannot_mint_positive_causal_axes(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["source_class"] = "public_software"
        entry["source_url"] = "https://example.org/software-catalog"
        entry["privacy_class"] = "public"
        self.assert_runtime_and_schema_reject(
            candidate,
            "public_software cannot mint positive exact-allele",
        )
        entry["human_pd_evidence"] = "not_assessable"
        entry["causal_distance_score"] = 0
        self.assert_runtime_and_schema_reject(
            candidate,
            "public_software cannot occupy lead advancement",
        )
        entry["role"] = "mechanistic_control"
        entry["experimental_priority"] = None
        entry["advancement_state"] = "comparator_only"
        validate_candidate_ledger(candidate)
        for axis in (
            "direct_target_evidence",
            "exact_allele_evidence",
            "checkpoint_evidence",
            "human_pd_evidence",
        ):
            with self.subTest(axis=axis):
                minted = self.fixture()
                row = minted["entries"][0]  # type: ignore[index]
                row["source_class"] = "public_software"
                row["source_url"] = "https://example.org/software-catalog"
                row["privacy_class"] = "public"
                row["human_pd_evidence"] = "not_assessable"
                row["causal_distance_score"] = 0
                row["role"] = "mechanistic_control"
                row["experimental_priority"] = None
                row["advancement_state"] = "comparator_only"
                row[axis] = "positive"
                row["causal_distance_score"] = 1
                self.assert_runtime_and_schema_reject(
                    minted,
                    "public_software cannot mint positive exact-allele",
                )

    def test_official_label_cannot_mint_positive_causal_axes(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["source_class"] = "official_label"
        entry["source_url"] = "https://example.org/official-label"
        entry["privacy_class"] = "public"
        self.assert_runtime_and_schema_reject(
            candidate,
            "official_label cannot mint positive exact-allele",
        )
        entry["human_pd_evidence"] = "not_assessable"
        entry["causal_distance_score"] = 0
        self.assert_runtime_and_schema_reject(
            candidate,
            "official_label cannot occupy lead advancement",
        )
        entry["role"] = "mechanistic_control"
        entry["experimental_priority"] = None
        entry["advancement_state"] = "comparator_only"
        validate_candidate_ledger(candidate)
        for axis in (
            "direct_target_evidence",
            "exact_allele_evidence",
            "checkpoint_evidence",
            "human_pd_evidence",
        ):
            with self.subTest(axis=axis):
                minted = self.fixture()
                row = minted["entries"][0]  # type: ignore[index]
                row["source_class"] = "official_label"
                row["source_url"] = "https://example.org/official-label"
                row["privacy_class"] = "public"
                row["human_pd_evidence"] = "not_assessable"
                row["causal_distance_score"] = 0
                row["role"] = "mechanistic_control"
                row["experimental_priority"] = None
                row["advancement_state"] = "comparator_only"
                row[axis] = "positive"
                row["causal_distance_score"] = 1
                self.assert_runtime_and_schema_reject(
                    minted,
                    "official_label cannot mint positive exact-allele",
                )

    def test_catalog_and_label_cannot_occupy_challenger_conditional_hold(self) -> None:
        for source_class, source_url in (
            ("public_software", "https://example.org/software-catalog"),
            ("official_label", "https://example.org/official-label"),
            ("public_database", "https://example.org/public-database"),
            ("public_ontology", "https://example.org/public-ontology"),
        ):
            with self.subTest(source_class=source_class):
                candidate = self.fixture()
                entry = candidate["entries"][1]  # type: ignore[index]
                self.assertEqual(entry["role"], "challenger")
                self.assertEqual(entry["advancement_state"], "conditional_hold")
                entry["source_class"] = source_class
                entry["source_url"] = source_url
                entry["privacy_class"] = "public"
                entry["direct_target_evidence"] = "not_assessable"
                entry["human_pd_evidence"] = "not_assessable"
                entry["causal_distance_score"] = 0
                self.assert_runtime_and_schema_reject(
                    candidate,
                    f"{source_class} cannot occupy lead advancement",
                )
                entry["advancement_state"] = "comparator_only"
                if source_class in {
                    "public_software",
                    "public_database",
                    "public_ontology",
                }:
                    entry["role"] = "comparator"
                    self.assert_runtime_and_schema_reject(
                        candidate,
                        f"{source_class} cannot occupy a pharmacologic ranking role",
                    )
                    entry["role"] = "mechanistic_control"
                    entry["experimental_priority"] = None
                else:
                    entry["role"] = "comparator"
                validate_candidate_ledger(candidate)

    def test_catalog_sources_cannot_occupy_pharmacologic_ranking_role(self) -> None:
        for source_class, source_url in (
            ("public_software", "https://example.org/software-catalog"),
            ("public_database", "https://example.org/public-database"),
            ("public_ontology", "https://example.org/public-ontology"),
        ):
            for role in ("comparator", "challenger"):
                with self.subTest(source_class=source_class, role=role):
                    candidate = self.fixture()
                    entry = candidate["entries"][2]  # type: ignore[index]
                    self.assertEqual(entry["role"], "comparator")
                    self.assertEqual(entry["advancement_state"], "comparator_only")
                    entry["source_class"] = source_class
                    entry["source_url"] = source_url
                    entry["privacy_class"] = "public"
                    entry["role"] = role
                    self.assert_runtime_and_schema_reject(
                        candidate,
                        f"{source_class} cannot occupy a pharmacologic ranking role",
                    )
                    entry["role"] = "mechanistic_control"
                    entry["experimental_priority"] = None
                    validate_candidate_ledger(candidate)

    def test_database_and_ontology_may_mint_causal_axes_on_controls(self) -> None:
        for source_class, source_url in (
            ("public_database", "https://example.org/public-database"),
            ("public_ontology", "https://example.org/public-ontology"),
        ):
            with self.subTest(source_class=source_class):
                candidate = self.fixture()
                entry = candidate["entries"][2]  # type: ignore[index]
                entry["source_class"] = source_class
                entry["source_url"] = source_url
                entry["privacy_class"] = "public"
                entry["role"] = "mechanistic_control"
                entry["experimental_priority"] = None
                entry["advancement_state"] = "comparator_only"
                entry["exact_allele_evidence"] = "positive"
                entry["causal_distance_score"] = 1
                validate_candidate_ledger(candidate)

    def test_derived_evidence_inherits_parent_source_occupancy(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["source_class"] = "derived_evidence"
        self.assert_runtime_and_schema_reject(
            candidate,
            "derived_evidence requires parent_source_class",
        )
        entry["parent_source_class"] = "derived_evidence"
        self.assert_runtime_and_schema_reject(candidate, "parent_source_class")
        entry["parent_source_class"] = "public_software"
        entry["parent_candidate_id"] = "syn-parent-public-software"
        entry["source_url"] = "https://example.org/software-catalog"
        entry["privacy_class"] = "public"
        self.assert_runtime_and_schema_reject(
            candidate,
            "public_software cannot mint positive exact-allele",
        )
        entry["human_pd_evidence"] = "not_assessable"
        entry["causal_distance_score"] = 0
        self.assert_runtime_and_schema_reject(
            candidate,
            "public_software cannot occupy lead advancement",
        )
        entry["role"] = "mechanistic_control"
        entry["experimental_priority"] = None
        entry["advancement_state"] = "comparator_only"
        software_parent = json.loads(json.dumps(candidate["entries"][3], allow_nan=False))
        software_parent["candidate_id"] = "syn-parent-public-software"
        software_parent["source_class"] = "public_software"
        software_parent["source_url"] = "https://example.org/software-catalog"
        software_parent["privacy_class"] = "public"
        candidate["entries"].append(software_parent)  # type: ignore[union-attr]
        validate_candidate_ledger(candidate)
        entry["exact_allele_evidence"] = "positive"
        entry["causal_distance_score"] = 1
        self.assert_runtime_and_schema_reject(
            candidate,
            "public_software cannot mint positive exact-allele",
        )

        def add_parent(candidate: dict[str, object], source_class: str) -> None:
            parent = json.loads(json.dumps(candidate["entries"][3], allow_nan=False))  # type: ignore[index]
            parent["candidate_id"] = f"syn-parent-{source_class}"
            parent["source_class"] = source_class
            parent["source_url"] = f"https://example.org/{source_class.replace('_', '-')}"
            parent["privacy_class"] = "public"
            candidate["entries"].append(parent)  # type: ignore[union-attr]

        literature = self.fixture()
        lead = literature["entries"][0]  # type: ignore[index]
        lead["source_class"] = "derived_evidence"
        lead["parent_source_class"] = "public_literature"
        lead["parent_candidate_id"] = "syn-parent-public_literature"
        lead["source_url"] = "https://example.org/public-literature"
        lead["privacy_class"] = "public"
        add_parent(literature, "public_literature")
        validate_candidate_ledger(literature)

        database = self.fixture()
        parked = database["entries"][2]  # type: ignore[index]
        parked["source_class"] = "derived_evidence"
        parked["parent_source_class"] = "public_database"
        parked["parent_candidate_id"] = "syn-parent-public_database"
        parked["source_url"] = "https://example.org/public-database"
        parked["privacy_class"] = "public"
        parked["role"] = "mechanistic_control"
        parked["experimental_priority"] = None
        parked["advancement_state"] = "comparator_only"
        parked["exact_allele_evidence"] = "positive"
        parked["causal_distance_score"] = 1
        add_parent(database, "public_database")
        validate_candidate_ledger(database)
        parked["role"] = "comparator"
        parked["experimental_priority"] = 3
        self.assert_runtime_and_schema_reject(
            database,
            "public_database cannot occupy a pharmacologic ranking role",
        )

        labeled = self.fixture()
        row = labeled["entries"][0]  # type: ignore[index]
        row["source_class"] = "derived_evidence"
        row["parent_source_class"] = "official_label"
        row["parent_candidate_id"] = "syn-parent-official_label"
        row["source_url"] = "https://example.org/official-label"
        row["privacy_class"] = "public"
        row["human_pd_evidence"] = "not_assessable"
        row["causal_distance_score"] = 0
        self.assert_runtime_and_schema_reject(
            labeled,
            "official_label cannot occupy lead advancement",
        )
        row["role"] = "comparator"
        row["advancement_state"] = "comparator_only"
        add_parent(labeled, "official_label")
        validate_candidate_ledger(labeled)

        mismatched = self.fixture()
        extra = mismatched["entries"][2]  # type: ignore[index]
        extra["parent_source_class"] = "public_literature"
        extra["source_url"] = "https://example.org/public-literature"
        self.assert_runtime_and_schema_reject(
            mismatched,
            "parent_source_class is restricted to derived_evidence",
        )

    def test_source_class_requires_matching_privacy_class(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(entry["source_class"], "synthetic_fixture")
        entry["privacy_class"] = "public"
        self.assert_runtime_and_schema_reject(
            candidate,
            "synthetic_fixture requires privacy_class synthetic",
        )
        entry["privacy_class"] = "synthetic"
        validate_candidate_ledger(candidate)

        literature = self.fixture()
        row = literature["entries"][0]  # type: ignore[index]
        row["source_class"] = "public_literature"
        row["source_url"] = "https://example.org/public-literature"
        self.assert_runtime_and_schema_reject(
            literature,
            "public_literature requires privacy_class public",
        )
        row["privacy_class"] = "public"
        validate_candidate_ledger(literature)

        derived = self.fixture()
        child = derived["entries"][0]  # type: ignore[index]
        child["source_class"] = "derived_evidence"
        child["parent_source_class"] = "synthetic_fixture"
        child["parent_candidate_id"] = "syn-gap-exact-allele"
        child["privacy_class"] = "public"
        self.assert_runtime_and_schema_reject(
            derived,
            "synthetic_fixture requires privacy_class synthetic",
        )
        child["privacy_class"] = "synthetic"
        validate_candidate_ledger(derived)

    def test_derived_evidence_requires_a_realized_parent_class(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][2]  # type: ignore[index]
        entry["source_class"] = "derived_evidence"
        entry["parent_source_class"] = "public_literature"
        entry["parent_candidate_id"] = "syn-missing-parent"
        entry["source_url"] = "https://example.org/public-literature"
        entry["privacy_class"] = "public"
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "derived_evidence parent_candidate_id does not resolve",
        ):
            validate_candidate_ledger(candidate)

    def test_derived_evidence_parent_class_mismatch_rejected(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][2]  # type: ignore[index]
        entry["source_class"] = "derived_evidence"
        entry["parent_source_class"] = "public_literature"
        # The parent exists but its class does not match the declaration.
        entry["parent_candidate_id"] = "syn-gap-exact-allele"
        entry["source_url"] = "https://example.org/public-literature"
        entry["privacy_class"] = "public"
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "derived_evidence parent_candidate_id does not resolve",
        ):
            validate_candidate_ledger(candidate)

    def test_conditional_hold_requires_pharmacologic_role(self) -> None:
        candidate = self.fixture()
        control = candidate["entries"][3]  # type: ignore[index]
        self.assertEqual(control["role"], "mechanistic_control")
        self.assertEqual(control["advancement_state"], "comparator_only")
        control["advancement_state"] = "conditional_hold"
        self.assert_runtime_and_schema_reject(
            candidate,
            "advancement_state conditional_hold requires a pharmacologic role",
        )
        control["advancement_state"] = "comparator_only"
        validate_candidate_ledger(candidate)

        nogo = self.fixture()
        excluded = nogo["entries"][4]  # type: ignore[index]
        self.assertEqual(excluded["role"], "no_go")
        excluded["decision_effect"] = "defer"
        excluded["advancement_state"] = "conditional_hold"
        self.assert_runtime_and_schema_reject(
            nogo,
            "advancement_state conditional_hold requires a pharmacologic role",
        )

    def test_no_go_requires_rejected(self) -> None:
        candidate = self.fixture()
        excluded = candidate["entries"][4]  # type: ignore[index]
        self.assertEqual(excluded["role"], "no_go")
        excluded["decision_effect"] = "retain"
        excluded["advancement_state"] = "comparator_only"
        self.assert_runtime_and_schema_reject(
            candidate,
            "role no_go requires advancement_state rejected",
        )

    def test_unassessed_exposure_cannot_occupy_lead_advancement(self) -> None:
        candidate = self.fixture()
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")
        lead["exposure_class"] = "not_assessable"
        lead["nominal_concentration_uM"] = None
        self.assert_runtime_and_schema_reject(
            candidate,
            "exposure_class not_assessable cannot occupy lead advancement",
        )
        lead["exposure_class"] = "leq_2um"
        lead["nominal_concentration_uM"] = 2
        validate_candidate_ledger(candidate)
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        comparator["exposure_class"] = "not_assessable"
        comparator["nominal_concentration_uM"] = None
        validate_candidate_ledger(candidate)

    def test_mixed_or_unsafe_cannot_occupy_lead_advancement(self) -> None:
        candidate = self.fixture()
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["advancement_state"], "conditional_hold")
        lead["functional_hit_state"] = "mixed_or_unsafe"
        self.assert_runtime_and_schema_reject(
            candidate,
            "functional_hit_state mixed_or_unsafe cannot occupy "
            "lead advancement",
        )
        lead["functional_hit_state"] = "not_tested"
        validate_candidate_ledger(candidate)
        control = candidate["entries"][3]  # type: ignore[index]
        self.assertEqual(control["advancement_state"], "comparator_only")
        control["functional_hit_state"] = "mixed_or_unsafe"
        validate_candidate_ledger(candidate)

    def test_exclude_requires_rejected(self) -> None:
        candidate = self.fixture()
        comparator = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(comparator["role"], "comparator")
        self.assertEqual(comparator["advancement_state"], "comparator_only")
        comparator["decision_effect"] = "exclude"
        self.assert_runtime_and_schema_reject(
            candidate,
            "decision_effect exclude requires advancement_state rejected",
        )

    def test_active_lead_requires_role_lead(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        entry["mitotic_context_class"] = "lineage_intrinsic_mitotic"
        entry["architecture_lineage_state"] = "lineage_intrinsic_mitotic"
        entry["transformation_state"] = "primary_finite"
        plan = bind_sample_promotion(entry)
        entry["role"] = "challenger"
        self.assert_runtime_and_schema_reject(
            candidate,
            "advancement_state active_lead requires role lead",
        )
        entry["role"] = "lead"
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "synthetic-only sample-stewardship evidence cannot authorize",
        ):
            validate_candidate_ledger(candidate, sample_plan=plan)

    def test_ledger_allows_at_most_one_role_lead(self) -> None:
        candidate = self.fixture()
        lead = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(lead["role"], "lead")
        duplicate = json.loads(json.dumps(lead, allow_nan=False))
        duplicate["candidate_id"] = "syn-second-labeled-lead"
        duplicate["experimental_priority"] = 9
        duplicate["source_identifier"] = "synthetic-fixture-second-lead"
        entries = candidate["entries"]
        assert isinstance(entries, list)
        entries.append(duplicate)
        self.assert_runtime_and_schema_reject(
            candidate,
            "entries: at most one role lead is allowed",
        )
        entries.pop()
        validate_candidate_ledger(candidate)

    def test_promote_requires_lead_advancement(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][2]  # type: ignore[index]
        self.assertEqual(entry["advancement_state"], "comparator_only")
        entry["decision_effect"] = "promote"
        self.assert_runtime_and_schema_reject(
            candidate,
            "decision_effect promote requires advancement_state "
            "active_lead or conditional_hold",
        )
        entry["decision_effect"] = "retain"
        validate_candidate_ledger(candidate)

    def test_lead_advancement_cannot_demote(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        self.assertEqual(entry["advancement_state"], "conditional_hold")
        self.assertEqual(entry["decision_effect"], "defer")
        entry["decision_effect"] = "demote"
        self.assert_runtime_and_schema_reject(
            candidate,
            "advancement_state conditional_hold cannot have "
            "decision_effect demote",
        )
        entry["decision_effect"] = "defer"
        validate_candidate_ledger(candidate)
        ranking = rank_candidates(candidate)
        self.assertIn(entry["candidate_id"], ranking["conditional_probe_ids"])

    def test_json_schema_enums_match_runtime_validator(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        properties = schema["$defs"]["candidateEntry"]["properties"]
        expected = {
            "privacy_class": PRIVACY_CLASSES,
            "role": ROLES,
            "program_gate": PROGRAM_GATES,
            "direction": DIRECTIONS,
            "assessment_status": ASSESSMENT_STATUSES,
            "decision_effect": DECISION_EFFECTS,
            "advancement_state": ADVANCEMENT_STATES,
            "functional_hit_state": FUNCTIONAL_HIT_STATES,
            "screen_context": SCREEN_CONTEXTS,
            "no_hit_basis": NO_HIT_BASES,
            "translation_state": TRANSLATION_STATES,
            "discovery_lane": DISCOVERY_LANES,
            "therapeutic_context": THERAPEUTIC_CONTEXTS,
            "architecture_lineage_state": ARCHITECTURE_LINEAGE_STATES,
            "mitotic_context_class": MITOTIC_CONTEXT_CLASSES,
            "transformation_state": TRANSFORMATION_STATES,
            "source_class": SOURCE_CLASSES,
            "exposure_class": EXPOSURE_CLASSES,
            "pediatric_information": PEDIATRIC_INFORMATION_STATES,
            "oncology_risk": ONCOLOGY_RISKS,
            "regulatory_eligibility": REGULATORY_ELIGIBILITY_STATES,
            "independent_replication": INDEPENDENT_REPLICATION_STATES,
            "direct_target_evidence": ASSESSMENT_STATUSES,
            "exact_allele_evidence": ASSESSMENT_STATUSES,
            "checkpoint_evidence": ASSESSMENT_STATUSES,
            "human_pd_evidence": ASSESSMENT_STATUSES,
        }
        for field, values in expected.items():
            with self.subTest(field=field):
                enum_values = properties[field].get("enum")
                if enum_values is None:
                    enum_values = schema["$defs"]["axisAssessment"]["enum"]
                self.assertEqual(set(enum_values), values)
        self.assertEqual(
            set(schema["$defs"]["parentSourceClass"]["enum"]),
            PARENT_SOURCE_CLASSES,
        )
        self.assertIn("parent_source_class", properties)
        self.assertNotIn(
            "parent_source_class",
            schema["$defs"]["candidateEntry"]["required"],
        )
        rescue_properties = schema["$defs"]["rescueGates"]["properties"]
        self.assertEqual(set(rescue_properties), set(RescueGates.__dataclass_fields__))
        self.assertEqual(
            set(schema["$defs"]["rescueGates"]["required"]),
            set(RescueGates.__dataclass_fields__),
        )
        self.assertEqual(
            set(schema["$defs"]["site2BlindingState"]["enum"]),
            SITE2_BLINDING_STATES,
        )
        replication_properties = schema["$defs"]["replicationDesign"]["properties"]
        self.assertEqual(
            set(replication_properties),
            set(ReplicationDesign.__dataclass_fields__),
        )
        self.assertEqual(
            set(schema["$defs"]["sampleStewardshipPromotion"]["properties"]),
            set(SampleStewardshipPromotion.__dataclass_fields__),
        )
        self.assertEqual(
            set(schema["$defs"]["sampleStewardshipPromotion"]["required"]),
            set(SAMPLE_STEWARDSHIP_PROMOTION_FIELDS),
        )
        for field in rescue_properties:
            with self.subTest(rescue_gate=field):
                self.assertEqual(
                    set(schema["$defs"]["rescueGateState"]["enum"]),
                    RESCUE_GATE_STATES,
                )

    def test_declared_search_protocol_round_trips(self) -> None:
        payload = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        protocol = SearchProtocol.from_dict(payload)
        self.assertEqual(protocol.to_dict(), payload)
        self.assertEqual(protocol.protocol_id, "track2-candidate-search-v3")
        self.assertEqual(protocol.searched_on, "2026-09-10")
        self.assertIn("its own clinically plausible", protocol.notes)
        self.assertIn("jurisdiction-specific", protocol.notes)
        self.assertIn("not a completed search", protocol.notes)
        self.assertIn("exact-correction-and-reciprocal-recreation", protocol.query_axes)
        self.assertIn("assay-matched-endogenous-wet-function", protocol.query_axes)
        self.assertIn(
            "analog-nearby-or-species-model-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "computational-predictor-or-ranking-as-assay",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "unmatched-or-ectopic-specimen-as-endogenous-assay",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "frequency-conservation-or-clinvar-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "public-software-catalog-as-causal-evidence",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "official-label-as-causal-evidence",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "public-database-or-ontology-as-pharmacologic-candidate",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "derived-evidence-inherits-parent-source-occupancy",
            protocol.exclusion_axes,
        )
        self.assertIn("inherits its parent source occupancy", protocol.notes)
        self.assertIn("cannot occupy conditional hold", protocol.notes)
        self.assertIn("must have role lead", protocol.notes)
        self.assertIn("at most one role lead", protocol.notes)
        self.assertIn("synthetic fixture cannot be public", protocol.notes)
        self.assertIn(
            "control-or-no-go-as-conditional-probe",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "challenger-or-comparator-as-active-lead",
            protocol.exclusion_axes,
        )
        self.assertIn("duplicate-role-lead", protocol.exclusion_axes)
        self.assertIn("source-privacy-class-mismatch", protocol.exclusion_axes)
        self.assertIn(
            "excluded-unsafe-row-as-conditional-probe",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "mixed-or-unsafe-as-conditional-probe",
            protocol.exclusion_axes,
        )
        self.assertIn("exclude and no-go", protocol.notes)
        self.assertIn("mixed-unsafe", protocol.notes)
        self.assertIn(
            "unassessed-oncology-as-conditional-probe",
            protocol.exclusion_axes,
        )
        self.assertIn("unassessed-oncology", protocol.notes)
        self.assertIn(
            "unassessed-exposure-as-conditional-probe",
            protocol.exclusion_axes,
        )
        self.assertIn("unassessed-oncology/exposure", protocol.notes)
        self.assertIn(
            "pediatric-absent-or-unassessed-as-displacement",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "public-literature-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn("literature records cannot stand in", protocol.notes)
        self.assertIn(
            "public-software-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn("catalog, software", protocol.notes)
        self.assertIn(
            "immortalized-or-reprogrammed-as-displacement",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "cell-free-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "imposed-stress-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn("cell-free, or imposed-stress assays cannot stand in", protocol.notes)
        self.assertIn(
            "isogenic-a0-as-displacement",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "ranking-or-predictor-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn("predictor/ranking records cannot stand in", protocol.notes)
        self.assertIn(
            "unlabeled-or-transgene-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "mixed-or-unsafe-as-displacement",
            protocol.exclusion_axes,
        )
        self.assertIn("mixed-unsafe", protocol.notes)
        self.assertIn(
            "computational-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "no-hit-as-displacement",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "rejected-as-displacement",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "not-assessable-advancement-as-displacement",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "transient-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "biophysical-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "thermal-shift-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "purified-protein-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "protein-surrogate-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "unmatched-line-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "rna-seq-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn(
            "computational-haplotype-as-exact-function",
            protocol.exclusion_axes,
        )
        self.assertIn("exclude and no-go must be rejected", protocol.notes)
        self.assertLessEqual(len(protocol.notes), 2000)

    def test_lineage_intrinsic_context_can_be_replication_ready_not_active(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "conditional_hold"
        self.pass_rescue_gates(entry)
        entry["mitotic_context_class"] = "lineage_intrinsic_mitotic"
        entry["architecture_lineage_state"] = "lineage_intrinsic_mitotic"
        entry["transformation_state"] = "primary_finite"
        plan = bind_sample_promotion(entry)
        validate_candidate_ledger(candidate, sample_plan=plan)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(candidate)), [])
        ranking = rank_candidates(candidate, sample_plan=plan)
        self.assertIsNone(ranking["active_lead_id"])
        self.assertEqual(
            ranking["mitotic_context_classes"][entry["candidate_id"]],
            "lineage_intrinsic_mitotic",
        )

    def test_epithelial_context_cannot_use_lineage_intrinsic_architecture(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "conditional_hold"
        self.pass_rescue_gates(entry)
        entry["mitotic_context_class"] = "epithelial_architecture_dependent"
        entry["architecture_lineage_state"] = "lineage_intrinsic_mitotic"
        self.assert_runtime_and_schema_reject(candidate, "lineage_intrinsic_mitotic")

    def test_immortalized_culture_cannot_qualify_postnatal_context(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["transformation_state"] = "immortalized_or_transformed"
        entry["therapeutic_context"] = "postnatal_nontransformed_proliferative"
        self.assert_runtime_and_schema_reject(
            candidate, "immortalized or reprogrammed"
        )

    def test_reprogrammed_culture_remains_mechanism_only(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        entry["transformation_state"] = "reprogrammed"
        self.assert_runtime_and_schema_reject(
            candidate, "immortalized or reprogrammed"
        )

    def test_replicated_full_without_sample_plan_fails_closed(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        entry["sample_stewardship_promotion"] = None
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "sample-stewardship held-out and replication completion receipts",
        ):
            validate_candidate_ledger_engine(candidate)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(candidate)))

    def test_replicated_full_promotion_without_plan_fails_closed(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        bind_sample_promotion(entry)
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "sample-stewardship promotion requires a sample-stewardship plan",
        ):
            validate_candidate_ledger_engine(candidate)

    def test_wrong_lane_sample_receipts_cannot_promote(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        entry["discovery_lane"] = "targeted_hypothesis"
        plan = bind_sample_promotion(entry)
        entry["discovery_lane"] = "correction_trained_phenotypic"
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "discovery lane must match the candidate",
        ):
            validate_candidate_ledger_engine(candidate, sample_plan=plan)

    def test_ledger_frozen_estimand_must_match_sample_lock(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        plan = bind_sample_promotion(entry)
        entry["replication_design"]["frozen_endpoint_identity_id"] = (
            "syn-forged-endpoint"
        )
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "frozen estimand",
        ):
            validate_candidate_ledger_engine(candidate, sample_plan=plan)

    def test_replication_protocol_analysis_and_site2_receipt_are_cross_bound(
        self,
    ) -> None:
        for field, forged, message in (
            (
                "frozen_protocol_identity_id",
                "syn-forged-protocol",
                "sample replication freeze lock",
            ),
            (
                "frozen_analysis_identity_id",
                "syn-forged-analysis",
                "sample replication freeze lock",
            ),
            (
                "site2_blinding_evidence_sha256",
                "d" * 64,
                "must match sample promotion_evidence",
            ),
        ):
            with self.subTest(field=field):
                candidate, plan = self.promoted_conditional_fixture()
                entry = candidate["entries"][0]  # type: ignore[index]
                entry["replication_design"][field] = forged
                with self.assertRaisesRegex(CandidateLedgerError, message):
                    validate_candidate_ledger_engine(candidate, sample_plan=plan)

    def test_synthetic_plan_cannot_back_public_or_active_candidate_evidence(self) -> None:
        candidate, plan = self.promoted_conditional_fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["source_class"] = "manual_review"
        entry["privacy_class"] = "public"
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "may bind only synthetic fixture candidate evidence",
        ):
            validate_candidate_ledger_engine(candidate, sample_plan=plan)

        candidate, plan = self.promoted_conditional_fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "cannot authorize a biologically interpreted active_lead",
        ):
            validate_candidate_ledger_engine(candidate, sample_plan=plan)

    def test_plan_without_ledger_promotion_is_rejected_as_unbound(self) -> None:
        plan = json.loads(SAMPLE_TEMPLATE.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(CandidateLedgerError, "plan is unbound"):
            validate_candidate_ledger_engine(self.fixture(), sample_plan=plan)

    def test_constructed_ledger_promotion_without_plan_fails_closed(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "conditional_hold"
        self.pass_rescue_gates(entry)
        plan = bind_sample_promotion(entry)
        ledger = validate_candidate_ledger_engine(candidate, sample_plan=plan)
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "sample-stewardship promotion requires a sample-stewardship plan",
        ):
            validate_candidate_ledger_engine(ledger)
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "sample-stewardship promotion requires a sample-stewardship plan",
        ):
            rank_candidates_engine(ledger)

    def test_sample_context_must_match_ledger_mitotic_class(self) -> None:
        candidate = self.fixture()
        entry = candidate["entries"][0]  # type: ignore[index]
        entry["exact_allele_evidence"] = "positive"
        entry["checkpoint_evidence"] = "positive"
        entry["causal_distance_score"] = 3
        entry["program_gate"] = "segregation"
        entry["advancement_state"] = "active_lead"
        self.pass_rescue_gates(entry)
        plan = _complete_sample_lane(str(entry["discovery_lane"]))
        entry["mitotic_context_class"] = "lineage_intrinsic_mitotic"
        entry["architecture_lineage_state"] = "lineage_intrinsic_mitotic"
        with self.assertRaisesRegex(
            CandidateLedgerError,
            "sample context mitotic_context_class must match the candidate",
        ):
            validate_candidate_ledger_engine(candidate, sample_plan=plan)


if __name__ == "__main__":
    unittest.main()
