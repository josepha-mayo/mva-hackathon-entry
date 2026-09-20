from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.sample_stewardship import (  # noqa: E402
    A0_PHENOTYPE_EVIDENCE_FIELDS,
    A0_PHENOTYPE_VALIDITY_REQUIREMENTS,
    A0_SHARED_EVIDENCE_FIELDS,
    A0_SHARED_VALIDITY_REQUIREMENTS,
    A1_EVIDENCE_FIELDS,
    A1_NO_HIT_REQUIREMENTS,
    CLAIM_BOUNDARY,
    CONTEXT_ID_FIELDS,
    CONTEXT_VALIDITY_REQUIREMENTS,
    HELD_OUT_EVIDENCE_FIELDS,
    LINEAGE_INTRINSIC_VALIDITY_REQUIREMENTS,
    NATIVE_LINEAGE_EVIDENCE_FIELDS,
    REPLICATION_EVIDENCE_FIELDS,
    RESULT_SCHEMA,
    SampleStewardshipError,
    assay_contract_sha256,
    assess_sample_stewardship,
    completion_receipt_sha256,
    make_completion_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = json.loads(
    (ROOT / "templates" / "track2_sample_stewardship.synthetic.json").read_text(
        encoding="utf-8"
    )
)
SCHEMA = json.loads(
    (ROOT / "schemas" / "track2_sample_stewardship.schema.json").read_text(
        encoding="utf-8"
    )
)
PROMOTION_EVIDENCE = {
    "analytic_transfer_result_sha256": "a" * 64,
    "site2_blinding_state": "blinded",
    "site2_blinding_id": "syn-blinding-site2-targeted",
    "site2_blinding_evidence_sha256": "b" * 64,
    "discovery_event_family_ids": ["syn-event-discovery-one"],
    "replication_event_family_ids": ["syn-event-replication-one"],
    "discovery_site_id": "syn-site-discovery-targeted",
    "replication_site_id": "syn-site-replication-targeted",
}


def _phenotype_promotion(**overrides: object) -> dict:
    evidence = copy.deepcopy(PROMOTION_EVIDENCE)
    evidence["analytic_transfer_result_sha256"] = "b" * 64
    evidence["site2_blinding_evidence_sha256"] = "c" * 64
    evidence["site2_blinding_id"] = "syn-blinding-site2-phenotype"
    evidence["discovery_event_family_ids"] = ["syn-event-discovery-phenotype"]
    evidence["replication_event_family_ids"] = ["syn-event-replication-phenotype"]
    evidence["discovery_site_id"] = "syn-site-discovery-phenotype"
    evidence["replication_site_id"] = "syn-site-replication-phenotype"
    evidence.update(overrides)
    return evidence


def _assay(plan: dict, assay_id: str) -> dict:
    return next(item for item in plan["assays"] if item["assay_id"] == assay_id)


def _receipt_id(assay_id: str) -> str:
    return "syn-completion-" + assay_id.removeprefix("syn-")


def _complete(
    plan: dict,
    assay_id: str,
    outcome: str = "positive",
    *,
    promotion_evidence: dict | None = None,
) -> None:
    plan["completed"][assay_id] = make_completion_receipt(
        _assay(plan, assay_id),
        outcome,
        _receipt_id(assay_id),
        promotion_evidence=promotion_evidence,
    )


def _complete_targeted_to_replication(plan: dict) -> None:
    for assay_id in (
        "syn-a0-targeted",
        "syn-a1-targeted-bridge",
        "syn-tier-b-targeted-context",
        "syn-tier-b-targeted-lineage",
        "syn-held-out-targeted",
    ):
        _complete(plan, assay_id)


class SampleStewardshipTests(unittest.TestCase):
    def test_template_passes_json_schema(self) -> None:
        Draft202012Validator.check_schema(SCHEMA)
        errors = list(Draft202012Validator(SCHEMA).iter_errors(TEMPLATE))
        self.assertEqual(errors, [])

    def test_schema_rejects_stage_partition_swap(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["partition"] = "participant_held_out"
        errors = list(Draft202012Validator(SCHEMA).iter_errors(plan))
        self.assertTrue(errors)

    def test_template_returns_both_nondominated_a0_lanes(self) -> None:
        result = assess_sample_stewardship(TEMPLATE)
        expected = ["syn-a0-phenotype", "syn-a0-targeted"]
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["selection_rule"], "vector_dominance_not_scalar_voi")
        self.assertEqual(result["eligible_ids"], expected)
        self.assertEqual(result["nondominated_ids"], expected)
        self.assertTrue(result["lane_paths_separate"])
        self.assertTrue(result["a0_correction_core_required"])
        self.assertTrue(result["a0_correction_core_evidence_bound"])
        self.assertTrue(result["a1_lineage_reservation_enforced"])
        self.assertTrue(result["context_evidence_identities_bound"])
        self.assertTrue(result["held_out_freeze_and_blinding_bound"])
        self.assertTrue(result["replication_independence_identities_bound"])
        self.assertTrue(result["replication_site_identities_bound"])
        self.assertTrue(result["native_lineage_identities_bound"])
        self.assertTrue(result["a1_bridge_identities_bound"])
        self.assertTrue(result["replication_event_family_identities_bound"])
        self.assertTrue(result["analytic_transfer_fingerprint_bound"])
        self.assertTrue(result["analytic_transfer_excludes_all_assay_contracts"])
        self.assertTrue(result["replication_site2_blinding_identity_bound"])
        self.assertTrue(result["replication_site2_blinding_evidence_bound"])
        self.assertTrue(result["held_out_replication_estimand_equivalence_bound"])
        self.assertTrue(result["held_out_replication_exposure_equivalence_bound"])

    def test_participant_partition_requires_declared_consent(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        del _assay(plan, "syn-a1-targeted-bridge")["consent_state"]
        with self.assertRaisesRegex(SampleStewardshipError, "consent_state"):
            assess_sample_stewardship(plan)

    def test_withdrawn_consent_cannot_consume_participant_partition(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["consent_state"] = "withdrawn"
        with self.assertRaisesRegex(SampleStewardshipError, "consent_state"):
            assess_sample_stewardship(plan)

    def test_renewable_partition_cannot_claim_participant_consent(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["consent_state"] = "consented"
        with self.assertRaisesRegex(SampleStewardshipError, "not_applicable"):
            assess_sample_stewardship(plan)

    def test_a0_cannot_create_participant_no_hit(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["outcome_actions"][
            "negative"
        ] = "participant_branch_no_hit"
        with self.assertRaisesRegex(SampleStewardshipError, "A0 results"):
            assess_sample_stewardship(plan)

    def test_a0_cannot_open_a1_without_correction_core(self) -> None:
        for requirement in sorted(A0_SHARED_VALIDITY_REQUIREMENTS):
            with self.subTest(requirement=requirement):
                plan = copy.deepcopy(TEMPLATE)
                _assay(plan, "syn-a0-targeted")["validity_requirements"].remove(
                    requirement
                )
                with self.assertRaisesRegex(
                    SampleStewardshipError, "A0 correction core is missing"
                ):
                    assess_sample_stewardship(plan)

    def test_phenotypic_a0_cannot_unblind_without_correction_signature(self) -> None:
        extra = A0_PHENOTYPE_VALIDITY_REQUIREMENTS - A0_SHARED_VALIDITY_REQUIREMENTS
        self.assertEqual(extra, {"correction_signature_separation"})
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-phenotype")["validity_requirements"].remove(
            "correction_signature_separation"
        )
        with self.assertRaisesRegex(
            SampleStewardshipError, "phenotypic A0 cannot unblind a screen"
        ):
            assess_sample_stewardship(plan)

    def test_v4_bytes_are_not_silently_reinterpreted_as_v5(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v4"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v5_bytes_are_not_silently_reinterpreted_as_v6(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v5"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v6_bytes_are_not_silently_reinterpreted_as_v7(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v6"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v7_bytes_are_not_silently_reinterpreted_as_v8(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v7"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v8_bytes_are_not_silently_reinterpreted_as_v9(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v8"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v9_bytes_are_not_silently_reinterpreted_as_v10(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v9"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v10_bytes_are_not_silently_reinterpreted_as_v11(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v10"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v11_bytes_are_not_silently_reinterpreted_as_v12(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v11"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v12_bytes_are_not_silently_reinterpreted_as_v13(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v12"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v13_bytes_are_not_silently_reinterpreted_as_v14(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v13"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v14_bytes_are_not_silently_reinterpreted_as_v15(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v14"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v15_bytes_are_not_silently_reinterpreted_as_v16(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v15"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_v16_bytes_are_not_silently_reinterpreted_as_v17(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["schema"] = "mva.track2-sample-stewardship/v16"
        with self.assertRaisesRegex(SampleStewardshipError, "schema must be"):
            assess_sample_stewardship(plan)

    def test_a0_must_bind_opaque_correction_core_evidence(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        del _assay(plan, "syn-a0-targeted")["correction_core"]
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "must bind opaque correction-core evidence"
        ):
            assess_sample_stewardship(plan)

    def test_a0_correction_core_requires_every_evidence_identity(self) -> None:
        for field in A0_SHARED_EVIDENCE_FIELDS:
            with self.subTest(field=field):
                plan = copy.deepcopy(TEMPLATE)
                del _assay(plan, "syn-a0-targeted")["correction_core"][field]
                with self.assertRaisesRegex(
                    SampleStewardshipError, "must contain exactly"
                ):
                    assess_sample_stewardship(plan)

    def test_phenotypic_a0_requires_signature_evidence_identity(self) -> None:
        extra = set(A0_PHENOTYPE_EVIDENCE_FIELDS) - set(A0_SHARED_EVIDENCE_FIELDS)
        self.assertEqual(extra, {"correction_signature_separation_id"})
        plan = copy.deepcopy(TEMPLATE)
        del _assay(plan, "syn-a0-phenotype")["correction_core"][
            "correction_signature_separation_id"
        ]
        with self.assertRaisesRegex(SampleStewardshipError, "must contain exactly"):
            assess_sample_stewardship(plan)

    def test_targeted_a0_cannot_declare_phenotype_signature_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["correction_core"][
            "correction_signature_separation_id"
        ] = "syn-a0-targeted-signature"
        with self.assertRaisesRegex(SampleStewardshipError, "must contain exactly"):
            assess_sample_stewardship(plan)

    def test_a0_correction_core_ids_must_be_unique(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        core = _assay(plan, "syn-a0-targeted")["correction_core"]
        core["same_background_recreation_id"] = core["same_background_correction_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_a0_lanes_cannot_share_correction_core_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        targeted = _assay(plan, "syn-a0-targeted")["correction_core"]
        phenotype = _assay(plan, "syn-a0-phenotype")["correction_core"]
        phenotype["locked_function_id"] = targeted["locked_function_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_context_qualification_ids_must_be_unique(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        context = _assay(plan, "syn-tier-b-targeted-context")["context_qualification"]
        context["receipt_identity_id"] = context["postnatal_lineage_rationale_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_context_lanes_cannot_share_evidence_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        targeted = _assay(plan, "syn-tier-b-targeted-context")["context_qualification"]
        phenotype = _assay(plan, "syn-tier-b-phenotype-context")["context_qualification"]
        phenotype["receipt_identity_id"] = targeted["receipt_identity_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_context_cannot_reuse_a0_correction_core_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        locked = _assay(plan, "syn-a0-targeted")["correction_core"]["locked_function_id"]
        _assay(plan, "syn-tier-b-targeted-context")["context_qualification"][
            "receipt_identity_id"
        ] = locked
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_non_a0_cannot_carry_correction_core(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["correction_core"] = dict(
            _assay(plan, "syn-a0-targeted")["correction_core"]
        )
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "correction_core is restricted to A0"
        ):
            assess_sample_stewardship(plan)

    def test_correction_core_identity_is_bound_into_completion_receipt(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        receipt = make_completion_receipt(
            _assay(plan, "syn-a0-targeted"),
            "positive",
            "syn-completion-a0-targeted",
        )
        _assay(plan, "syn-a0-targeted")["correction_core"][
            "locked_function_id"
        ] = "syn-a0-targeted-locked-function-tampered"
        plan["completed"]["syn-a0-targeted"] = receipt
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay contract digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_root_a1_without_positive_a0_ancestor_is_rejected(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["prerequisites"] = []
        with self.assertRaisesRegex(SampleStewardshipError, "direct A0 predecessor"):
            assess_sample_stewardship(plan)

    def test_a0_must_remain_a_root_assay(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["prerequisites"] = [
            "syn-a0-phenotype"
        ]
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(SampleStewardshipError, "A0 must be a root"):
            assess_sample_stewardship(plan)

    def test_cross_lane_prerequisite_is_rejected(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["prerequisites"] = [
            "syn-a0-phenotype"
        ]
        with self.assertRaisesRegex(SampleStewardshipError, "crosses discovery lanes"):
            assess_sample_stewardship(plan)

    def test_a0_positive_cannot_jump_to_replication(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["outcome_actions"][
            "positive"
        ] = "independent_replication"
        with self.assertRaisesRegex(SampleStewardshipError, "A0 positive"):
            assess_sample_stewardship(plan)

    def test_a0_negative_cannot_jump_to_replication(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["outcome_actions"][
            "negative"
        ] = "independent_replication"
        with self.assertRaisesRegex(SampleStewardshipError, "A0 results"):
            assess_sample_stewardship(plan)

    def test_a1_negative_cannot_evade_valid_no_hit(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["outcome_actions"][
            "negative"
        ] = "reject_condition"
        with self.assertRaisesRegex(SampleStewardshipError, "A1 negative"):
            assess_sample_stewardship(plan)

    def test_a1_no_hit_requires_measured_exposure_and_controls(self) -> None:
        self.assertEqual(
            A1_NO_HIT_REQUIREMENTS,
            {
                "measured_exposure",
                "valid_controls",
                "participant_context",
                "locked_function",
                "short_term_viability_completion",
            },
        )
        for requirement in sorted(A1_NO_HIT_REQUIREMENTS):
            with self.subTest(requirement=requirement):
                plan = copy.deepcopy(TEMPLATE)
                _assay(plan, "syn-a1-targeted-bridge")[
                    "validity_requirements"
                ].remove(requirement)
                with self.assertRaisesRegex(SampleStewardshipError, "no-hit basis"):
                    assess_sample_stewardship(plan)

    def test_a1_must_bind_opaque_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        del _assay(plan, "syn-a1-targeted-bridge")["a1_lock"]
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "must bind opaque bridge evidence"
        ):
            assess_sample_stewardship(plan)

    def test_a1_lock_requires_every_evidence_identity(self) -> None:
        for field in A1_EVIDENCE_FIELDS:
            with self.subTest(field=field):
                plan = copy.deepcopy(TEMPLATE)
                del _assay(plan, "syn-a1-targeted-bridge")["a1_lock"][field]
                with self.assertRaisesRegex(
                    SampleStewardshipError, "must contain exactly"
                ):
                    assess_sample_stewardship(plan)

    def test_a1_lock_ids_must_be_unique(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        lock = _assay(plan, "syn-a1-targeted-bridge")["a1_lock"]
        lock["short_term_viability_id"] = lock["measured_exposure_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_a1_cannot_reuse_a0_or_later_identity(self) -> None:
        sources = {
            "a0": _assay(TEMPLATE, "syn-a0-targeted")["correction_core"][
                "locked_function_id"
            ],
            "context": _assay(TEMPLATE, "syn-tier-b-targeted-context")[
                "context_qualification"
            ]["receipt_identity_id"],
            "lineage": _assay(TEMPLATE, "syn-tier-b-targeted-lineage")[
                "lineage_lock"
            ]["native_fidelity_id"],
            "held_out": _assay(TEMPLATE, "syn-held-out-targeted")["held_out_lock"][
                "blinded_execution_id"
            ],
            "replication_lock": _assay(TEMPLATE, "syn-replication-targeted")[
                "replication_lock"
            ]["frozen_protocol_id"],
        }
        for label, identifier in sources.items():
            with self.subTest(source=label):
                plan = copy.deepcopy(TEMPLATE)
                _assay(plan, "syn-a1-targeted-bridge")["a1_lock"][
                    "measured_exposure_id"
                ] = identifier
                with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
                    assess_sample_stewardship(plan)

    def test_a1_lanes_cannot_share_lock_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        shared = _assay(plan, "syn-a1-targeted-bridge")["a1_lock"][
            "locked_function_id"
        ]
        _assay(plan, "syn-a1-phenotype-bridge")["a1_lock"][
            "locked_function_id"
        ] = shared
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_non_a1_cannot_carry_a1_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["a1_lock"] = dict(
            _assay(plan, "syn-a1-targeted-bridge")["a1_lock"]
        )
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "a1_lock is restricted to A1"
        ):
            assess_sample_stewardship(plan)

    def test_a1_lock_identity_is_bound_into_completion_receipt(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-targeted")
        receipt = make_completion_receipt(
            _assay(plan, "syn-a1-targeted-bridge"),
            "positive",
            _receipt_id("syn-a1-targeted-bridge"),
        )
        _assay(plan, "syn-a1-targeted-bridge")["a1_lock"][
            "short_term_viability_id"
        ] = "syn-a1-targeted-viability-tampered"
        plan["completed"]["syn-a1-targeted-bridge"] = receipt
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay contract digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_a1_cannot_reuse_replication_site_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["a1_lock"][
            "participant_context_id"
        ] = PROMOTION_EVIDENCE["discovery_site_id"]
        _complete_targeted_to_replication(plan)
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            _complete(
                plan,
                "syn-replication-targeted",
                promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
            )
            assess_sample_stewardship(plan)

    def test_invalid_result_must_hold(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["outcome_actions"][
            "invalid"
        ] = "stop_unsafe"
        with self.assertRaisesRegex(SampleStewardshipError, "hold_invalid"):
            assess_sample_stewardship(plan)

    def test_context_qualification_requires_a1_ancestor(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        keeper_context = copy.deepcopy(_assay(plan, "syn-tier-b-targeted-context"))
        keeper_context["assay_id"] = "syn-tier-b-targeted-context-keeper"
        keeper_context["prerequisites"] = ["syn-a1-targeted-bridge"]
        keeper_context["context_qualification"] = {
            key: f"{value}-keeper" if str(key).endswith("_id") else value
            for key, value in keeper_context["context_qualification"].items()
        }
        keeper_lineage = copy.deepcopy(_assay(plan, "syn-tier-b-targeted-lineage"))
        keeper_lineage["assay_id"] = "syn-tier-b-targeted-lineage-keeper"
        keeper_lineage["prerequisites"] = ["syn-tier-b-targeted-context-keeper"]
        keeper_lineage["lineage_lock"] = {
            key: f"{value}-keeper" for key, value in keeper_lineage["lineage_lock"].items()
        }
        plan["assays"].extend([keeper_context, keeper_lineage])
        _assay(plan, "syn-tier-b-targeted-context")["prerequisites"] = [
            "syn-a0-targeted"
        ]
        with self.assertRaisesRegex(SampleStewardshipError, "direct A1 predecessor"):
            assess_sample_stewardship(plan)

    def test_context_qualification_requires_every_validity_axis(self) -> None:
        for requirement in sorted(CONTEXT_VALIDITY_REQUIREMENTS):
            with self.subTest(requirement=requirement):
                plan = copy.deepcopy(TEMPLATE)
                _assay(plan, "syn-tier-b-targeted-context")[
                    "validity_requirements"
                ].remove(requirement)
                with self.assertRaisesRegex(
                    SampleStewardshipError, "context qualification is missing"
                ):
                    assess_sample_stewardship(plan)

    def test_context_qualification_requires_every_opaque_identity(self) -> None:
        for field in CONTEXT_ID_FIELDS:
            with self.subTest(field=field):
                plan = copy.deepcopy(TEMPLATE)
                del _assay(plan, "syn-tier-b-targeted-context")[
                    "context_qualification"
                ][field]
                with self.assertRaisesRegex(SampleStewardshipError, "contain exactly"):
                    assess_sample_stewardship(plan)

        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-tier-b-targeted-context")["context_qualification"][
            "receipt_identity_id"
        ] = "participant-real-context"
        with self.assertRaisesRegex(SampleStewardshipError, "opaque syn-"):
            assess_sample_stewardship(plan)

    def test_native_lineage_requires_context_qualified_ancestor(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-tier-b-targeted-lineage")["prerequisites"] = [
            "syn-a1-targeted-bridge"
        ]
        with self.assertRaisesRegex(
            SampleStewardshipError, "direct context-qualified predecessor"
        ):
            assess_sample_stewardship(plan)

    def test_held_out_cannot_skip_native_lineage(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-held-out-targeted")["prerequisites"] = [
            "syn-tier-b-targeted-context"
        ]
        with self.assertRaisesRegex(
            SampleStewardshipError, "direct native-lineage predecessor"
        ):
            assess_sample_stewardship(plan)

    def test_held_out_requires_freeze_and_blinding_axes(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-held-out-targeted")["validity_requirements"].remove(
            "blinded_execution"
        )
        with self.assertRaisesRegex(SampleStewardshipError, "held-out contract is missing"):
            assess_sample_stewardship(plan)

    def test_held_out_must_bind_opaque_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        del _assay(plan, "syn-held-out-targeted")["held_out_lock"]
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "must bind opaque freeze and blinding evidence"
        ):
            assess_sample_stewardship(plan)

    def test_held_out_lock_ids_must_be_unique(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        lock = _assay(plan, "syn-held-out-targeted")["held_out_lock"]
        lock["frozen_margin_id"] = lock["frozen_endpoint_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_held_out_cannot_reuse_a0_or_context_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        locked = _assay(plan, "syn-a0-targeted")["correction_core"]["locked_function_id"]
        _assay(plan, "syn-held-out-targeted")["held_out_lock"][
            "blinded_execution_id"
        ] = locked
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_non_held_out_cannot_carry_held_out_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["held_out_lock"] = dict(
            _assay(plan, "syn-held-out-targeted")["held_out_lock"]
        )
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "held_out_lock is restricted to held-out"
        ):
            assess_sample_stewardship(plan)

    def test_held_out_lock_requires_every_evidence_identity(self) -> None:
        for field in HELD_OUT_EVIDENCE_FIELDS:
            with self.subTest(field=field):
                plan = copy.deepcopy(TEMPLATE)
                del _assay(plan, "syn-held-out-targeted")["held_out_lock"][field]
                with self.assertRaisesRegex(
                    SampleStewardshipError, "must contain exactly"
                ):
                    assess_sample_stewardship(plan)

    def test_held_out_cannot_reuse_context_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        context_id = _assay(plan, "syn-tier-b-targeted-context")[
            "context_qualification"
        ]["receipt_identity_id"]
        _assay(plan, "syn-held-out-targeted")["held_out_lock"][
            "frozen_margin_id"
        ] = context_id
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_held_out_lanes_cannot_share_lock_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        shared = _assay(plan, "syn-held-out-targeted")["held_out_lock"][
            "frozen_endpoint_id"
        ]
        _assay(plan, "syn-held-out-phenotype")["held_out_lock"][
            "frozen_endpoint_id"
        ] = shared
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_held_out_lock_identity_is_bound_into_completion_receipt(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        for assay_id in (
            "syn-a0-targeted",
            "syn-a1-targeted-bridge",
            "syn-tier-b-targeted-context",
            "syn-tier-b-targeted-lineage",
        ):
            _complete(plan, assay_id)
        receipt = make_completion_receipt(
            _assay(plan, "syn-held-out-targeted"),
            "positive",
            _receipt_id("syn-held-out-targeted"),
        )
        tampered = "syn-held-out-targeted-frozen-endpoint-tampered"
        _assay(plan, "syn-held-out-targeted")["held_out_lock"][
            "frozen_endpoint_id"
        ] = tampered
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_endpoint_id"
        ] = tampered
        plan["completed"]["syn-held-out-targeted"] = receipt
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay contract digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_replication_must_bind_opaque_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        del _assay(plan, "syn-replication-targeted")["replication_lock"]
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "must bind opaque freeze and transfer evidence"
        ):
            assess_sample_stewardship(plan)

    def test_replication_lock_requires_every_evidence_identity(self) -> None:
        for field in REPLICATION_EVIDENCE_FIELDS:
            with self.subTest(field=field):
                plan = copy.deepcopy(TEMPLATE)
                del _assay(plan, "syn-replication-targeted")["replication_lock"][field]
                with self.assertRaisesRegex(
                    SampleStewardshipError, "must contain exactly"
                ):
                    assess_sample_stewardship(plan)

    def test_replication_lock_ids_must_be_unique(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        lock = _assay(plan, "syn-replication-targeted")["replication_lock"]
        lock["frozen_margin_id"] = lock["frozen_endpoint_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_replication_cannot_reuse_a0_or_held_out_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        locked = _assay(plan, "syn-a0-targeted")["correction_core"]["locked_function_id"]
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_exposure_id"
        ] = locked
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_replication_cannot_reuse_held_out_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        held = _assay(plan, "syn-held-out-targeted")["held_out_lock"][
            "blinded_execution_id"
        ]
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "common_reference_transfer_qc_id"
        ] = held
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_replication_cannot_reuse_context_or_held_out_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        context_id = _assay(plan, "syn-tier-b-targeted-context")[
            "context_qualification"
        ]["receipt_identity_id"]
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_analysis_id"
        ] = context_id
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_replication_lanes_cannot_share_lock_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        shared = _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_protocol_id"
        ]
        _assay(plan, "syn-replication-phenotype")["replication_lock"][
            "frozen_protocol_id"
        ] = shared
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_non_replication_cannot_carry_replication_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["replication_lock"] = dict(
            _assay(plan, "syn-replication-targeted")["replication_lock"]
        )
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "replication_lock is restricted to replication"
        ):
            assess_sample_stewardship(plan)

    def test_replication_lock_identity_is_bound_into_completion_receipt(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete_targeted_to_replication(plan)
        receipt = make_completion_receipt(
            _assay(plan, "syn-replication-targeted"),
            "positive",
            _receipt_id("syn-replication-targeted"),
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_protocol_id"
        ] = "syn-replication-targeted-frozen-protocol-tampered"
        plan["completed"]["syn-replication-targeted"] = receipt
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay contract digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_tier_b_positive_cannot_route_back_to_a1(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-tier-b-targeted-context")["outcome_actions"][
            "positive"
        ] = "advance_to_a1"
        with self.assertRaisesRegex(SampleStewardshipError, "context positive"):
            assess_sample_stewardship(plan)

    def test_discovery_cannot_spend_held_out_partition(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")[
            "partition"
        ] = "participant_held_out"
        with self.assertRaisesRegex(SampleStewardshipError, "cannot consume"):
            assess_sample_stewardship(plan)

    def test_assay_cannot_exceed_partition_budget(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a1-targeted-bridge")["consumption"][
            "viable_cell_equivalents"
        ] = 1000001
        with self.assertRaisesRegex(SampleStewardshipError, "exceeds"):
            assess_sample_stewardship(plan)

    def test_public_ids_are_opaque(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["assay_id"] = "participant-real-id"
        with self.assertRaisesRegex(SampleStewardshipError, "opaque syn-"):
            assess_sample_stewardship(plan)

    def test_replication_requires_biological_and_transfer_independence(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-replication-targeted")[
            "independence_requirements"
        ].remove("nonoverlapping_edit_event_families")
        with self.assertRaisesRegex(SampleStewardshipError, "replication is missing"):
            assess_sample_stewardship(plan)

    def test_targeted_positive_opens_only_targeted_a1(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-targeted")
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-a1-targeted-bridge", result["eligible_ids"])
        self.assertNotIn("syn-a1-phenotype-bridge", result["eligible_ids"])

    def test_phenotype_positive_opens_only_phenotype_a1(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-phenotype")
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-a1-phenotype-bridge", result["eligible_ids"])
        self.assertNotIn("syn-a1-targeted-bridge", result["eligible_ids"])

    def test_both_positive_a0_lanes_reserve_one_a1_on_scarce_budget(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-targeted")
        _complete(plan, "syn-a0-phenotype")
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-a1-targeted-bridge", result["eligible_ids"])
        self.assertNotIn("syn-a1-phenotype-bridge", result["eligible_ids"])
        self.assertEqual(
            result["resource_blocked"]["syn-a1-phenotype-bridge"],
            [
                "viable_cell_equivalents",
                "population_doublings",
                "edit_event_families",
            ],
        )
        self.assertTrue(result["a1_lineage_reservation_enforced"])

    def test_completed_a1_does_not_unlock_second_lane_on_scarce_budget(self) -> None:
        for outcome in ("positive", "negative"):
            with self.subTest(outcome=outcome):
                plan = copy.deepcopy(TEMPLATE)
                _complete(plan, "syn-a0-targeted")
                _complete(plan, "syn-a0-phenotype")
                _complete(plan, "syn-a1-targeted-bridge", outcome)
                result = assess_sample_stewardship(plan)
                self.assertNotIn("syn-a1-phenotype-bridge", result["eligible_ids"])
                self.assertEqual(
                    result["resource_blocked"]["syn-a1-phenotype-bridge"],
                    ["edit_event_families"],
                )

    def test_two_full_discovery_paths_can_keep_both_a1s(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        budget = plan["inventory"]["participant_discovery"]
        budget["viable_cell_equivalents"] = 1_500_000
        budget["population_doublings"] = 10
        budget["edit_event_families"] = 6
        _complete(plan, "syn-a0-targeted")
        _complete(plan, "syn-a0-phenotype")
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-a1-targeted-bridge", result["eligible_ids"])
        self.assertIn("syn-a1-phenotype-bridge", result["eligible_ids"])

    def test_a1_requires_native_lineage_successor(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        drop = {
            "syn-tier-b-targeted-lineage",
            "syn-held-out-targeted",
            "syn-replication-targeted",
        }
        plan["assays"] = [
            assay for assay in plan["assays"] if assay["assay_id"] not in drop
        ]
        with self.assertRaisesRegex(
            SampleStewardshipError, "native-lineage successor"
        ):
            assess_sample_stewardship(plan)

    def test_native_lineage_must_bind_opaque_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        del _assay(plan, "syn-tier-b-targeted-lineage")["lineage_lock"]
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "must bind opaque lineage evidence"
        ):
            assess_sample_stewardship(plan)

    def test_lineage_lock_requires_every_evidence_identity(self) -> None:
        for field in NATIVE_LINEAGE_EVIDENCE_FIELDS:
            with self.subTest(field=field):
                plan = copy.deepcopy(TEMPLATE)
                del _assay(plan, "syn-tier-b-targeted-lineage")["lineage_lock"][field]
                with self.assertRaisesRegex(
                    SampleStewardshipError, "must contain exactly"
                ):
                    assess_sample_stewardship(plan)

    def test_lineage_lock_ids_must_be_unique(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        lock = _assay(plan, "syn-tier-b-targeted-lineage")["lineage_lock"]
        lock["clone_safety_id"] = lock["native_fidelity_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_lineage_cannot_reuse_a0_or_context_identity(self) -> None:
        sources = {
            "a0": _assay(TEMPLATE, "syn-a0-targeted")["correction_core"][
                "locked_function_id"
            ],
            "context": _assay(TEMPLATE, "syn-tier-b-targeted-context")[
                "context_qualification"
            ]["receipt_identity_id"],
            "held_out": _assay(TEMPLATE, "syn-held-out-targeted")["held_out_lock"][
                "blinded_execution_id"
            ],
            "replication_lock": _assay(TEMPLATE, "syn-replication-targeted")[
                "replication_lock"
            ]["frozen_protocol_id"],
        }
        for label, identifier in sources.items():
            with self.subTest(source=label):
                plan = copy.deepcopy(TEMPLATE)
                _assay(plan, "syn-tier-b-targeted-lineage")["lineage_lock"][
                    "native_fidelity_id"
                ] = identifier
                with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
                    assess_sample_stewardship(plan)

    def test_lineage_lanes_cannot_share_lock_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        shared = _assay(plan, "syn-tier-b-targeted-lineage")["lineage_lock"][
            "clone_safety_id"
        ]
        _assay(plan, "syn-tier-b-phenotype-lineage")["lineage_lock"][
            "clone_safety_id"
        ] = shared
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_non_lineage_cannot_carry_lineage_lock(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-tier-b-targeted-context")["lineage_lock"] = dict(
            _assay(plan, "syn-tier-b-targeted-lineage")["lineage_lock"]
        )
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(
            SampleStewardshipError, "lineage_lock is restricted to native-lineage"
        ):
            assess_sample_stewardship(plan)

    def test_lineage_lock_identity_is_bound_into_completion_receipt(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        for assay_id in (
            "syn-a0-targeted",
            "syn-a1-targeted-bridge",
            "syn-tier-b-targeted-context",
        ):
            _complete(plan, assay_id)
        receipt = make_completion_receipt(
            _assay(plan, "syn-tier-b-targeted-lineage"),
            "positive",
            _receipt_id("syn-tier-b-targeted-lineage"),
        )
        _assay(plan, "syn-tier-b-targeted-lineage")["lineage_lock"][
            "clone_safety_id"
        ] = "syn-lineage-targeted-clone-safety-tampered"
        plan["completed"]["syn-tier-b-targeted-lineage"] = receipt
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay contract digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_positive_context_receipt_opens_native_lineage(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        for assay_id in (
            "syn-a0-targeted",
            "syn-a1-targeted-bridge",
            "syn-tier-b-targeted-context",
        ):
            _complete(plan, assay_id)
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-tier-b-targeted-lineage", result["eligible_ids"])
        self.assertTrue(result["context_qualification_required"])

    def test_completed_history_cannot_skip_prerequisite(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a1-targeted-bridge")
        with self.assertRaisesRegex(SampleStewardshipError, "skips prerequisites"):
            assess_sample_stewardship(plan)

    def test_prerequisite_cycle_fails_closed(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        # A0 must stay a root. Cycle later stages while keeping a direct A0
        # predecessor so the A0 root rule is not the first failure.
        _assay(plan, "syn-a1-targeted-bridge")["prerequisites"] = [
            "syn-a0-targeted",
            "syn-tier-b-targeted-context",
        ]
        with self.assertRaisesRegex(SampleStewardshipError, "prerequisite cycle"):
            assess_sample_stewardship(plan)

    def test_legacy_scalar_completion_is_rejected(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        plan["completed"] = {"syn-a0-targeted": "positive"}
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(plan)))
        with self.assertRaisesRegex(SampleStewardshipError, "must be an object"):
            assess_sample_stewardship(plan)

    def test_completion_receipt_binds_exact_resource_debit(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-targeted")
        plan["completed"]["syn-a0-targeted"]["resource_debit"][
            "rna_aliquots"
        ] = 0
        with self.assertRaisesRegex(SampleStewardshipError, "resource debit"):
            assess_sample_stewardship(plan)

    def test_completion_receipt_binds_immutable_assay_contract(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-targeted")
        _assay(plan, "syn-a0-targeted")["validity_requirements"].append(
            "post_receipt_mutation"
        )
        with self.assertRaisesRegex(SampleStewardshipError, "contract digest mismatch"):
            assess_sample_stewardship(plan)

    def test_completion_receipt_self_digest_detects_tampering(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-targeted")
        plan["completed"]["syn-a0-targeted"][
            "receipt_id"
        ] = "syn-completion-tampered"
        with self.assertRaisesRegex(SampleStewardshipError, "receipt digest mismatch"):
            assess_sample_stewardship(plan)

    def test_duplicate_completion_receipt_identity_is_rejected(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(plan, "syn-a0-targeted")
        _complete(plan, "syn-a0-phenotype")
        duplicate = plan["completed"]["syn-a0-targeted"]["receipt_id"]
        phenotype = plan["completed"]["syn-a0-phenotype"]
        phenotype["receipt_id"] = duplicate
        phenotype["receipt_sha256"] = completion_receipt_sha256(phenotype)
        with self.assertRaisesRegex(SampleStewardshipError, "duplicate completion"):
            assess_sample_stewardship(plan)

    def test_cumulative_completed_debits_cannot_overdraw_partition(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["consumption"]["rna_aliquots"] = 60
        _assay(plan, "syn-a0-phenotype")["consumption"]["rna_aliquots"] = 60
        _complete(plan, "syn-a0-targeted")
        _complete(plan, "syn-a0-phenotype")
        with self.assertRaisesRegex(SampleStewardshipError, "cumulatively exceed"):
            assess_sample_stewardship(plan)

    def test_remaining_inventory_blocks_unaffordable_eligible_assay(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-a0-targeted")["consumption"]["rna_aliquots"] = 90
        _assay(plan, "syn-a0-phenotype")["consumption"]["rna_aliquots"] = 20
        _complete(plan, "syn-a0-targeted")
        result = assess_sample_stewardship(plan)
        self.assertNotIn("syn-a0-phenotype", result["eligible_ids"])
        self.assertEqual(result["resource_blocked"]["syn-a0-phenotype"], ["rna_aliquots"])
        self.assertEqual(
            result["remaining_inventory"]["renewable_nonparticipant"][
                "rna_aliquots"
            ],
            10,
        )

    def test_dominance_requires_same_branch_decision_contract(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        extra = copy.deepcopy(_assay(plan, "syn-a0-targeted"))
        extra["assay_id"] = "syn-a0-targeted-extra-decision"
        extra["decision_changes"].append("second_targeted_decision")
        extra["consumption"] = {axis: 0 for axis in extra["consumption"]}
        extra["correction_core"] = {
            key: f"{value}-extra-decision"
            for key, value in extra["correction_core"].items()
        }
        plan["assays"].append(extra)
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-a0-targeted", result["nondominated_ids"])
        self.assertIn("syn-a0-targeted-extra-decision", result["nondominated_ids"])

    def test_dominance_requires_same_stage_even_with_same_partition_and_decision(
        self,
    ) -> None:
        plan = copy.deepcopy(TEMPLATE)
        context = _assay(plan, "syn-tier-b-targeted-context")
        extra_a1 = copy.deepcopy(_assay(plan, "syn-a1-targeted-bridge"))
        extra_a1["assay_id"] = "syn-a1-targeted-alternative"
        extra_a1["decision_changes"] = list(context["decision_changes"])
        extra_a1["consumption"] = {axis: 0 for axis in extra_a1["consumption"]}
        extra_a1["a1_lock"] = {
            key: f"{value}-alt" for key, value in extra_a1["a1_lock"].items()
        }
        extra_context = copy.deepcopy(context)
        extra_context["assay_id"] = "syn-tier-b-targeted-context-alt"
        extra_context["prerequisites"] = ["syn-a1-targeted-alternative"]
        extra_context["context_qualification"] = {
            key: f"{value}-alt" if str(key).endswith("_id") else value
            for key, value in extra_context["context_qualification"].items()
        }
        extra_lineage = copy.deepcopy(_assay(plan, "syn-tier-b-targeted-lineage"))
        extra_lineage["assay_id"] = "syn-tier-b-targeted-lineage-alt"
        extra_lineage["prerequisites"] = ["syn-tier-b-targeted-context-alt"]
        extra_lineage["consumption"] = {
            axis: 0 for axis in extra_lineage["consumption"]
        }
        extra_lineage["lineage_lock"] = {
            key: f"{value}-alt" for key, value in extra_lineage["lineage_lock"].items()
        }
        plan["assays"].extend([extra_a1, extra_context, extra_lineage])
        _complete(plan, "syn-a0-targeted")
        _complete(plan, "syn-a1-targeted-bridge")
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-a1-targeted-alternative", result["nondominated_ids"])
        self.assertIn("syn-tier-b-targeted-context", result["nondominated_ids"])

    def test_positive_replication_requires_promotion_evidence(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        with self.assertRaisesRegex(SampleStewardshipError, "promotion_evidence"):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
            )

    def test_promotion_evidence_requires_fingerprint_blinding_and_disjoint_events(
        self,
    ) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        mutations = (
            ("analytic_transfer_result_sha256", "bad", "lowercase SHA-256"),
            ("site2_blinding_state", "unblinded", "must be blinded"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                evidence = copy.deepcopy(PROMOTION_EVIDENCE)
                evidence[field] = value
                with self.assertRaisesRegex(SampleStewardshipError, message):
                    make_completion_receipt(
                        replication,
                        "positive",
                        "syn-completion-replication-targeted",
                        promotion_evidence=evidence,
                    )

        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        evidence["replication_event_family_ids"] = list(
            evidence["discovery_event_family_ids"]
        )
        with self.assertRaisesRegex(SampleStewardshipError, "overlap"):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=evidence,
            )

        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        evidence["discovery_site_id"] = evidence["discovery_event_family_ids"][0]
        with self.assertRaisesRegex(SampleStewardshipError, "overlap event families"):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=evidence,
            )

    def test_promotion_evidence_requires_distinct_site_identities(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        del evidence["replication_site_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "must contain exactly"):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=evidence,
            )
        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        evidence["replication_site_id"] = evidence["discovery_site_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "must differ"):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=evidence,
            )

    def test_replication_sites_cannot_reuse_a0_or_held_out_identity(self) -> None:
        sources = {
            "a0": _assay(TEMPLATE, "syn-a0-targeted")["correction_core"][
                "locked_function_id"
            ],
            "context": _assay(TEMPLATE, "syn-tier-b-targeted-context")[
                "context_qualification"
            ]["receipt_identity_id"],
            "held_out": _assay(TEMPLATE, "syn-held-out-targeted")["held_out_lock"][
                "blinded_execution_id"
            ],
            "replication_lock": _assay(TEMPLATE, "syn-replication-targeted")[
                "replication_lock"
            ]["frozen_protocol_id"],
        }
        for label, identifier in sources.items():
            with self.subTest(source=label):
                plan = copy.deepcopy(TEMPLATE)
                evidence = copy.deepcopy(PROMOTION_EVIDENCE)
                evidence["discovery_site_id"] = identifier
                plan["completed"]["syn-replication-targeted"] = (
                    make_completion_receipt(
                        _assay(plan, "syn-replication-targeted"),
                        "positive",
                        _receipt_id("syn-replication-targeted"),
                        promotion_evidence=evidence,
                    )
                )
                with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
                    assess_sample_stewardship(plan)

    def test_replication_lanes_cannot_share_site_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(
            plan,
            "syn-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        shared = copy.deepcopy(PROMOTION_EVIDENCE)
        shared["discovery_event_family_ids"] = ["syn-event-discovery-phenotype"]
        shared["replication_event_family_ids"] = ["syn-event-replication-phenotype"]
        plan["completed"]["syn-replication-phenotype"] = make_completion_receipt(
            _assay(plan, "syn-replication-phenotype"),
            "positive",
            _receipt_id("syn-replication-phenotype"),
            promotion_evidence=shared,
        )
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_site_identity_is_bound_into_completion_receipt(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        original = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        tampered_evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        tampered_evidence["discovery_site_id"] = "syn-site-discovery-tampered"
        changed = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=tampered_evidence,
        )
        self.assertNotEqual(original["receipt_sha256"], changed["receipt_sha256"])
        plan = copy.deepcopy(TEMPLATE)
        tampered = copy.deepcopy(original)
        tampered["promotion_evidence"]["discovery_site_id"] = (
            "syn-site-discovery-tampered"
        )
        plan["completed"]["syn-replication-targeted"] = tampered
        with self.assertRaisesRegex(
            SampleStewardshipError, "completion receipt digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_replication_event_families_cannot_reuse_a0_or_lock_identity(self) -> None:
        sources = {
            "a0": _assay(TEMPLATE, "syn-a0-targeted")["correction_core"][
                "locked_function_id"
            ],
            "a1": _assay(TEMPLATE, "syn-a1-targeted-bridge")["a1_lock"][
                "locked_function_id"
            ],
            "context": _assay(TEMPLATE, "syn-tier-b-targeted-context")[
                "context_qualification"
            ]["receipt_identity_id"],
            "lineage": _assay(TEMPLATE, "syn-tier-b-targeted-lineage")[
                "lineage_lock"
            ]["clone_safety_id"],
            "held_out": _assay(TEMPLATE, "syn-held-out-targeted")["held_out_lock"][
                "blinded_execution_id"
            ],
            "replication_lock": _assay(TEMPLATE, "syn-replication-targeted")[
                "replication_lock"
            ]["frozen_protocol_id"],
        }
        for label, identifier in sources.items():
            with self.subTest(source=label):
                plan = copy.deepcopy(TEMPLATE)
                evidence = copy.deepcopy(PROMOTION_EVIDENCE)
                evidence["discovery_event_family_ids"] = [identifier]
                plan["completed"]["syn-replication-targeted"] = (
                    make_completion_receipt(
                        _assay(plan, "syn-replication-targeted"),
                        "positive",
                        _receipt_id("syn-replication-targeted"),
                        promotion_evidence=evidence,
                    )
                )
                with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
                    assess_sample_stewardship(plan)

    def test_replication_lanes_cannot_share_event_family_identities(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(
            plan,
            "syn-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        shared = copy.deepcopy(PROMOTION_EVIDENCE)
        shared["discovery_site_id"] = "syn-site-discovery-phenotype"
        shared["replication_site_id"] = "syn-site-replication-phenotype"
        plan["completed"]["syn-replication-phenotype"] = make_completion_receipt(
            _assay(plan, "syn-replication-phenotype"),
            "positive",
            _receipt_id("syn-replication-phenotype"),
            promotion_evidence=shared,
        )
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_event_family_identity_is_bound_into_completion_receipt(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        original = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        tampered_evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        tampered_evidence["discovery_event_family_ids"] = [
            "syn-event-discovery-tampered"
        ]
        changed = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=tampered_evidence,
        )
        self.assertNotEqual(original["receipt_sha256"], changed["receipt_sha256"])
        plan = copy.deepcopy(TEMPLATE)
        tampered = copy.deepcopy(original)
        tampered["promotion_evidence"]["discovery_event_family_ids"] = [
            "syn-event-discovery-tampered"
        ]
        plan["completed"]["syn-replication-targeted"] = tampered
        with self.assertRaisesRegex(
            SampleStewardshipError, "completion receipt digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_analytic_transfer_cannot_be_the_assay_contract_digest(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        evidence["analytic_transfer_result_sha256"] = assay_contract_sha256(
            replication
        )
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay-contract digest"
        ):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=evidence,
            )
        plan = copy.deepcopy(TEMPLATE)
        valid = copy.deepcopy(PROMOTION_EVIDENCE)
        forged = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=valid,
        )
        forged["promotion_evidence"]["analytic_transfer_result_sha256"] = (
            assay_contract_sha256(replication)
        )
        forged["receipt_sha256"] = completion_receipt_sha256(forged)
        plan["completed"]["syn-replication-targeted"] = forged
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay-contract digest"
        ):
            assess_sample_stewardship(plan)

    def test_replication_lanes_cannot_share_analytic_transfer_fingerprint(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(
            plan,
            "syn-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        shared = copy.deepcopy(PROMOTION_EVIDENCE)
        shared["discovery_site_id"] = "syn-site-discovery-phenotype"
        shared["replication_site_id"] = "syn-site-replication-phenotype"
        shared["discovery_event_family_ids"] = ["syn-event-discovery-phenotype"]
        shared["replication_event_family_ids"] = ["syn-event-replication-phenotype"]
        shared["site2_blinding_id"] = "syn-blinding-site2-phenotype"
        plan["completed"]["syn-replication-phenotype"] = make_completion_receipt(
            _assay(plan, "syn-replication-phenotype"),
            "positive",
            _receipt_id("syn-replication-phenotype"),
            promotion_evidence=shared,
        )
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_replication_cannot_use_another_assay_contract_as_transfer(
        self,
    ) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(
            plan,
            "syn-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        borrowed = copy.deepcopy(PROMOTION_EVIDENCE)
        borrowed["discovery_site_id"] = "syn-site-discovery-phenotype"
        borrowed["replication_site_id"] = "syn-site-replication-phenotype"
        borrowed["discovery_event_family_ids"] = ["syn-event-discovery-phenotype"]
        borrowed["replication_event_family_ids"] = ["syn-event-replication-phenotype"]
        borrowed["site2_blinding_id"] = "syn-blinding-site2-phenotype"
        borrowed["analytic_transfer_result_sha256"] = assay_contract_sha256(
            _assay(plan, "syn-replication-targeted")
        )
        plan["completed"]["syn-replication-phenotype"] = make_completion_receipt(
            _assay(plan, "syn-replication-phenotype"),
            "positive",
            _receipt_id("syn-replication-phenotype"),
            promotion_evidence=borrowed,
        )
        with self.assertRaisesRegex(
            SampleStewardshipError, "assay-contract digest"
        ):
            assess_sample_stewardship(plan)

    def test_site2_blinding_cannot_pass_as_a_state_label(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        del evidence["site2_blinding_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "must contain exactly"):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=evidence,
            )
        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        evidence["site2_blinding_id"] = evidence["discovery_site_id"]
        with self.assertRaisesRegex(SampleStewardshipError, "overlaps site"):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=evidence,
            )

    def test_replication_lanes_cannot_share_site2_blinding_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete(
            plan,
            "syn-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        shared = _phenotype_promotion(
            analytic_transfer_result_sha256="a" * 64,
            site2_blinding_id=PROMOTION_EVIDENCE["site2_blinding_id"],
        )
        plan["completed"]["syn-replication-phenotype"] = make_completion_receipt(
            _assay(plan, "syn-replication-phenotype"),
            "positive",
            _receipt_id("syn-replication-phenotype"),
            promotion_evidence=shared,
        )
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_site2_blinding_identity_is_bound_into_completion_receipt(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        original = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        tampered_evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        tampered_evidence["site2_blinding_id"] = "syn-blinding-site2-tampered"
        changed = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=tampered_evidence,
        )
        self.assertNotEqual(original["receipt_sha256"], changed["receipt_sha256"])
        plan = copy.deepcopy(TEMPLATE)
        tampered = copy.deepcopy(original)
        tampered["promotion_evidence"]["site2_blinding_id"] = (
            "syn-blinding-site2-tampered"
        )
        plan["completed"]["syn-replication-targeted"] = tampered
        with self.assertRaisesRegex(
            SampleStewardshipError, "completion receipt digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_site2_blinding_evidence_sha_is_distinct_and_receipt_bound(self) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        original = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        changed_evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        changed_evidence["site2_blinding_evidence_sha256"] = "c" * 64
        changed = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=changed_evidence,
        )
        self.assertNotEqual(original["receipt_sha256"], changed["receipt_sha256"])

        reused = copy.deepcopy(PROMOTION_EVIDENCE)
        reused["site2_blinding_evidence_sha256"] = reused[
            "analytic_transfer_result_sha256"
        ]
        with self.assertRaisesRegex(
            SampleStewardshipError, "must identify distinct receipts"
        ):
            make_completion_receipt(
                replication,
                "positive",
                "syn-completion-replication-targeted",
                promotion_evidence=reused,
            )

        tampered_plan = copy.deepcopy(TEMPLATE)
        tampered = copy.deepcopy(original)
        tampered["promotion_evidence"]["site2_blinding_evidence_sha256"] = "c" * 64
        tampered_plan["completed"]["syn-replication-targeted"] = tampered
        with self.assertRaisesRegex(
            SampleStewardshipError, "completion receipt digest mismatch"
        ):
            assess_sample_stewardship(tampered_plan)

    def test_site2_blinding_cannot_reuse_a0_or_lock_identity(self) -> None:
        borrowed = _assay(TEMPLATE, "syn-a0-targeted")["correction_core"][
            "locked_function_id"
        ]
        plan = copy.deepcopy(TEMPLATE)
        evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        evidence["site2_blinding_id"] = borrowed
        plan["completed"]["syn-replication-targeted"] = make_completion_receipt(
            _assay(plan, "syn-replication-targeted"),
            "positive",
            _receipt_id("syn-replication-targeted"),
            promotion_evidence=evidence,
        )
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_analytic_transfer_fingerprint_is_bound_into_completion_receipt(
        self,
    ) -> None:
        replication = _assay(TEMPLATE, "syn-replication-targeted")
        original = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        tampered_evidence = copy.deepcopy(PROMOTION_EVIDENCE)
        tampered_evidence["analytic_transfer_result_sha256"] = "c" * 64
        changed = make_completion_receipt(
            replication,
            "positive",
            "syn-completion-replication-targeted",
            promotion_evidence=tampered_evidence,
        )
        self.assertNotEqual(original["receipt_sha256"], changed["receipt_sha256"])
        plan = copy.deepcopy(TEMPLATE)
        tampered = copy.deepcopy(original)
        tampered["promotion_evidence"]["analytic_transfer_result_sha256"] = "c" * 64
        plan["completed"]["syn-replication-targeted"] = tampered
        with self.assertRaisesRegex(
            SampleStewardshipError, "completion receipt digest mismatch"
        ):
            assess_sample_stewardship(plan)

    def test_runtime_rejects_forged_positive_replication_without_evidence(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete_targeted_to_replication(plan)
        assay = _assay(plan, "syn-replication-targeted")
        forged = make_completion_receipt(
            assay,
            "negative",
            "syn-completion-replication-targeted",
        )
        forged["outcome"] = "positive"
        forged["outcome_action"] = "independent_replication"
        forged["receipt_sha256"] = completion_receipt_sha256(forged)
        plan["completed"]["syn-replication-targeted"] = forged
        with self.assertRaisesRegex(SampleStewardshipError, "promotion_evidence"):
            assess_sample_stewardship(plan)

    def test_full_targeted_path_binds_replication_promotion_evidence(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _complete_targeted_to_replication(plan)
        _complete(
            plan,
            "syn-replication-targeted",
            promotion_evidence=copy.deepcopy(PROMOTION_EVIDENCE),
        )
        result = assess_sample_stewardship(plan)
        self.assertTrue(result["replication_promotion_evidence_bound"])
        self.assertTrue(result["replication_site_identities_bound"])
        self.assertTrue(result["replication_event_family_identities_bound"])
        self.assertTrue(result["analytic_transfer_fingerprint_bound"])
        self.assertTrue(result["analytic_transfer_excludes_all_assay_contracts"])
        self.assertTrue(result["replication_site2_blinding_identity_bound"])
        self.assertTrue(result["held_out_replication_estimand_equivalence_bound"])
        self.assertTrue(result["held_out_replication_exposure_equivalence_bound"])
        self.assertIn(
            "syn-replication-targeted", result["completed_receipt_ids"]
        )

    def test_same_lane_replication_cannot_freeze_a_different_endpoint(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_endpoint_id"
        ] = "syn-replication-targeted-frozen-endpoint"
        with self.assertRaisesRegex(
            SampleStewardshipError, "must match same-lane held-out frozen estimand"
        ):
            assess_sample_stewardship(plan)

    def test_same_lane_replication_cannot_freeze_a_different_margin(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_margin_id"
        ] = "syn-replication-targeted-frozen-margin"
        with self.assertRaisesRegex(
            SampleStewardshipError, "must match same-lane held-out frozen estimand"
        ):
            assess_sample_stewardship(plan)

    def test_same_lane_replication_cannot_freeze_a_different_exposure(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_exposure_id"
        ] = "syn-replication-targeted-frozen-exposure"
        with self.assertRaisesRegex(
            SampleStewardshipError, "must match same-lane held-out frozen estimand"
        ):
            assess_sample_stewardship(plan)

    def test_replication_cannot_borrow_other_lane_frozen_endpoint(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        borrowed = _assay(plan, "syn-held-out-phenotype")["held_out_lock"][
            "frozen_endpoint_id"
        ]
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_endpoint_id"
        ] = borrowed
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_shared_estimand_cannot_reuse_a0_identity(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        borrowed = _assay(plan, "syn-a0-targeted")["correction_core"][
            "locked_function_id"
        ]
        _assay(plan, "syn-held-out-targeted")["held_out_lock"][
            "frozen_endpoint_id"
        ] = borrowed
        _assay(plan, "syn-replication-targeted")["replication_lock"][
            "frozen_endpoint_id"
        ] = borrowed
        with self.assertRaisesRegex(SampleStewardshipError, "reuses"):
            assess_sample_stewardship(plan)

    def test_immortalized_culture_cannot_qualify_context(self) -> None:
        plan = copy.deepcopy(TEMPLATE)
        _assay(plan, "syn-tier-b-targeted-context")["context_qualification"][
            "transformation_state"
        ] = "immortalized_or_transformed"
        with self.assertRaisesRegex(
            SampleStewardshipError, "cannot qualify postnatal nontransformed"
        ):
            assess_sample_stewardship(plan)

    def test_lineage_intrinsic_context_does_not_require_organoid_architecture(
        self,
    ) -> None:
        plan = copy.deepcopy(TEMPLATE)
        assay = _assay(plan, "syn-tier-b-targeted-context")
        assay["validity_requirements"] = sorted(
            LINEAGE_INTRINSIC_VALIDITY_REQUIREMENTS
        )
        assay["context_qualification"][
            "mitotic_context_class"
        ] = "lineage_intrinsic_mitotic"
        result = assess_sample_stewardship(plan)
        self.assertIn("syn-a0-targeted", result["eligible_ids"])
        self.assertNotIn("syn-tier-b-targeted-context", result["eligible_ids"])

    def test_epithelial_context_cannot_declare_lineage_intrinsic_validity(
        self,
    ) -> None:
        plan = copy.deepcopy(TEMPLATE)
        assay = _assay(plan, "syn-tier-b-targeted-context")
        assay["validity_requirements"].append("lineage_intrinsic_mitotic_context")
        with self.assertRaisesRegex(
            SampleStewardshipError, "cannot declare lineage_intrinsic_mitotic_context"
        ):
            assess_sample_stewardship(plan)


if __name__ == "__main__":
    unittest.main()
