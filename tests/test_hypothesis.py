from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.hypothesis import (
    CLAIM_BOUNDARY,
    SCHEMA,
    HypothesisStrengthError,
    assess_hypothesis_strength,
    mark_pair_program_observed,
)
from mva_hackathon.program_gates import EXPOSURE_SCHEMA, PROGRAM_SCHEMA
from mva_hackathon.provenance import receipt_sha256


ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = ROOT / "templates" / "community"


def _evidence() -> dict:
    return json.loads(
        (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
            encoding="utf-8"
        )
    )


class HypothesisStrengthTests(unittest.TestCase):
    def test_community_table_is_work_to_run_not_a_child_claim(self) -> None:
        result = assess_hypothesis_strength(_evidence())
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "weakest_link_respected")
        self.assertEqual(result["pair_strength"], "unsupported")
        self.assertEqual(result["transcript_strength"], "unsupported")
        self.assertEqual(result["stability_strength"], "experiment_to_run")
        self.assertEqual(result["isogenic_probe_strength"], "experiment_to_run")
        self.assertEqual(result["child_claim_strength"], "unsupported")
        self.assertEqual(result["declared_overall_strength"], "experiment_to_run")
        self.assertEqual(result["falsifier_ids"], ["syn-link-falsifier"])
        self.assertEqual(result["alternative_ids"], ["syn-link-alternative"])
        self.assertEqual(
            result["control_ids"],
            ["syn-link-positive-control", "syn-link-negative-control"],
        )
        self.assertEqual(result["failed_control_ids"], [])
        self.assertEqual(result["falsified_ids"], [])
        self.assertEqual(result["unbound_roles"], [])
        self.assertFalse(result["declared_probe_is_medicine"])

    def test_conditional_ex_vivo_cannot_be_declared_while_phase_is_unknown(self) -> None:
        payload = _evidence()
        payload["declared_overall_strength"] = "conditional_ex_vivo"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "declared_overstrong")
        self.assertEqual(result["program_effect"], "stop")

    def test_medicine_declaration_stops(self) -> None:
        payload = _evidence()
        payload["declared_probe_is_medicine"] = True
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "medicine_claim")

    def test_analog_allele_cannot_count_as_exact_function(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["link_id"] == "syn-link-missense-stability":
                link["status"] = "observed"
                link["supports"] = "analog allele proves the exact synthetic allele"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "analog_as_exact")
        self.assertIn("syn-link-missense-stability", result["analog_ids"])

    def test_nearby_and_homolog_allele_wording_cannot_count_as_exact(self) -> None:
        for phrase in (
            "nearby allele proves the exact synthetic allele",
            "homolog allele proves the exact synthetic allele",
            "ortholog allele proves the exact synthetic allele",
            "ortholog proves mutant function",
            "paralog allele proves the exact synthetic allele",
            "mouse allele proves the exact synthetic allele",
            "yeast allele proves the exact synthetic allele",
            "rat allele proves the exact synthetic allele",
            "drosophila allele proves the exact synthetic allele",
            "fly allele proves the exact synthetic allele",
            "zebrafish allele proves the exact synthetic allele",
            "xenopus allele proves the exact synthetic allele",
            "c. elegans allele proves the exact synthetic allele",
            "c elegans allele proves the exact synthetic allele",
            "c-elegans allele proves the exact synthetic allele",
            "celegans allele proves the exact synthetic allele",
            "worm allele proves the exact synthetic allele",
            "alphafold proves the exact synthetic allele",
            "alpha-fold proves the exact synthetic allele",
            "alpha fold proves the exact synthetic allele",
            "foldx proves mutant function",
            "geometry proves the exact synthetic allele",
            "coordinate proves the exact synthetic allele",
            "alphamissense proves the exact synthetic allele",
            "alpha-missense proves the exact synthetic allele",
            "alpha missense proves the exact synthetic allele",
            "docking proves the exact synthetic allele",
            "complementation proves mutant function",
            "nearby polymorphism proves the exact synthetic allele",
            "in silico proves the exact synthetic allele",
            "insilico proves the exact synthetic allele",
            "pathogenicity score proves the exact synthetic allele",
            "esm proves the exact synthetic allele",
            "esm1b proves the exact synthetic allele",
            "revel proves the exact synthetic allele",
            "mave proves the exact synthetic allele",
            "frequency proves the exact synthetic allele",
            "conservation proves the exact synthetic allele",
            "clinvar proves the exact synthetic allele",
            "label proves the exact synthetic allele",
            "catalog proves the exact synthetic allele",
            "software proves the exact synthetic allele",
            "database proves the exact synthetic allele",
            "ontology proves the exact synthetic allele",
            "literature proves the exact synthetic allele",
            "cell-free proves the exact synthetic allele",
            "cell free proves the exact synthetic allele",
            "cellfree proves the exact synthetic allele",
            "thermal shift proves the exact synthetic allele",
            "thermal-shift proves the exact synthetic allele",
            "purified-protein proves the exact synthetic allele",
            "purified protein proves the exact synthetic allele",
            "ectopic proves the exact synthetic allele",
            "unmatched proves the exact synthetic allele",
            "unmatched-line proves the exact synthetic allele",
            "unmatched line proves the exact synthetic allele",
            "unmatched genotype proves the exact synthetic allele",
            "unmatched genotype line proves the exact synthetic allele",
            "unmatched-genotype proves the exact synthetic allele",
            "imposed-stress proves the exact synthetic allele",
            "imposed stress proves the exact synthetic allele",
            "imposed extrinsic stress proves the exact synthetic allele",
            "imposed-extrinsic-stress proves the exact synthetic allele",
            "rna-seq proves the exact synthetic allele",
            "rna seq proves the exact synthetic allele",
            "rnaseq proves the exact synthetic allele",
            "rna-seq phase proves the exact synthetic allele",
            "rna seq phase proves the exact synthetic allele",
            "computational haplotype proves the exact synthetic allele",
            "ranking proves the exact synthetic allele",
            "predictor proves the exact synthetic allele",
            "unlabeled proves the exact synthetic allele",
            "transgene proves the exact synthetic allele",
            "overexpression proves the exact synthetic allele",
            "over-expression proves the exact synthetic allele",
            "over expression proves the exact synthetic allele",
            "computational proves the exact synthetic allele",
            "in-silico proves the exact synthetic allele",
            "cdna proves the exact synthetic allele",
            "transient proves the exact synthetic allele",
            "transient transfection proves the exact synthetic allele",
            "biophysical proves the exact synthetic allele",
            "protein-surrogate proves the exact synthetic allele",
            "protein surrogate proves the exact synthetic allele",
        ):
            with self.subTest(phrase=phrase):
                payload = _evidence()
                for link in payload["links"]:
                    if link["link_id"] == "syn-link-missense-stability":
                        link["status"] = "observed"
                        link["supports"] = phrase
                result = assess_hypothesis_strength(payload)
                self.assertEqual(result["status"], "stop")
                self.assertEqual(result["reason"], "analog_as_exact")
                self.assertIn("syn-link-missense-stability", result["analog_ids"])

    def test_heat_shock_upregulation_is_not_checkpoint_rescue(self) -> None:
        payload = _evidence()
        payload["links"].append(
            {
                "link_id": "syn-link-false-rescue",
                "hypothesis_role": "probe",
                "statement": "Heat-shock family transcripts rose after aneuploidy.",
                "status": "observed",
                "supports": "upregulation is rescue",
                "does_not_support": "nothing",
            }
        )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "false_rescue_mechanism")

    def test_target_engagement_wording_is_not_checkpoint_rescue(self) -> None:
        payload = _evidence()
        payload["links"].append(
            {
                "link_id": "syn-link-pd-engagement",
                "hypothesis_role": "probe",
                "statement": "Heat-shock family transcripts rose after aneuploidy.",
                "status": "observed",
                "supports": "this is target engagement",
                "does_not_support": "nothing",
            }
        )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "false_rescue_mechanism")

    def test_missing_role_fails_closed(self) -> None:
        payload = _evidence()
        del payload["links"][0]["hypothesis_role"]
        with self.assertRaisesRegex(HypothesisStrengthError, "hypothesis_role"):
            assess_hypothesis_strength(payload)

    def test_unmeasured_rna_cannot_make_a_child_claim(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "transcript":
                link["status"] = "unknown"
        result = assess_hypothesis_strength(
            payload,
            **_nested_gates(hypomorph="pass", exposure="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "declared_overstrong")
        self.assertEqual(result["transcript_strength"], "unsupported")
        self.assertEqual(result["child_claim_strength"], "unsupported")

    def test_missing_falsifier_stops(self) -> None:
        payload = _evidence()
        payload["links"] = [
            link for link in payload["links"] if link["hypothesis_role"] != "falsifier"
        ]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "no_falsifier")

    def test_observed_falsifier_kills_the_lead(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["status"] = "observed"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "hypothesis_falsified")
        self.assertEqual(result["falsified_ids"], ["syn-link-falsifier"])

    def test_lower_bulk_aneuploidy_is_not_rescue(self) -> None:
        payload = _evidence()
        payload["links"].append(
            {
                "link_id": "syn-link-bulk-aneuploidy",
                "hypothesis_role": "endpoint",
                "statement": "The treated culture had fewer aneuploid cells.",
                "status": "observed",
                "supports": "lower aneuploidy is rescue",
                "does_not_support": "nothing",
            }
        )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "false_rescue_mechanism")
        self.assertIn("syn-link-bulk-aneuploidy", result["false_rescue_ids"])

    def test_hyphenated_blocked_phrases_cannot_evade_detection(self) -> None:
        cases = (
            ("organ-size restored after the probe", "observed_overclaim"),
            ("arrest-is-rescue", "false_rescue_mechanism"),
            ("death  masking   is   rescue", "false_rescue_mechanism"),
            ("mouse-allele proves the exact synthetic allele", "analog_as_exact"),
            ("positive-control failed", "control_failed"),
        )
        for statement, expected_reason in cases:
            with self.subTest(statement=statement):
                payload = _evidence()
                payload["links"].append(
                    {
                        "link_id": "syn-link-evasion",
                        "hypothesis_role": (
                            "positive_control"
                            if expected_reason == "control_failed"
                            else "endpoint"
                        ),
                        "statement": statement,
                        "status": "observed",
                        "supports": "a synthetic measurement",
                        "does_not_support": "a child's claim",
                    }
                )
                result = assess_hypothesis_strength(payload)
                self.assertEqual(result["status"], "stop")
                self.assertEqual(result["reason"], expected_reason)

    def test_outcome_claim_phrases_in_observed_links_stop(self) -> None:
        statements = (
            "The corrected genotype is a cure and the child benefits.",
            "This medicine rescues the disease in the model.",
            "We recommend this treatment for the child.",
            "The compound shows therapeutic benefit.",
            "The regimen is safe and effective.",
        )
        for statement in statements:
            with self.subTest(statement=statement):
                payload = _evidence()
                payload["links"].append(
                    {
                        "link_id": "syn-link-outcome",
                        "hypothesis_role": "endpoint",
                        "statement": statement,
                        "status": "observed",
                        "supports": "a synthetic measurement",
                        "does_not_support": "a child's claim",
                    }
                )
                result = assess_hypothesis_strength(payload)
                self.assertEqual(result["status"], "stop", statement)
                self.assertEqual(result["reason"], "observed_overclaim")

    def test_pair_program_observed_without_nested_identity_stops(self) -> None:
        result = assess_hypothesis_strength(mark_pair_program_observed(_evidence()))
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertEqual(result["child_claim_strength"], "conditional_ex_vivo")
        self.assertEqual(result["transcript_strength"], "conditional_ex_vivo")
        self.assertIn("confirmation", result["unbound_roles"])
        self.assertIn("pair", result["unbound_roles"])
        self.assertIn("transcript", result["unbound_roles"])


def _stamp_receipt(receipt: dict) -> dict:
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    return receipt


def _nested_gates(
    *,
    confirmation: str = "pass",
    phase: str = "pass",
    transcript: str = "pass",
    hypomorph: str | None = None,
    exposure: str | None = None,
    concordance: str | None = None,
) -> dict:
    payload = {
        "confirmation": {
            "schema": PROGRAM_SCHEMA,
            "gate": "confirmation",
            "program_effect": confirmation,
            "status": confirmation,
            "reason": "fixture",
        },
        "phase": {
            "schema": PROGRAM_SCHEMA,
            "gate": "phase",
            "program_effect": phase,
            "status": phase,
            "reason": "fixture",
        },
        "transcript": {
            "schema": PROGRAM_SCHEMA,
            "gate": "transcript",
            "program_effect": transcript,
            "status": transcript,
            "reason": "fixture",
        },
    }
    if hypomorph is not None:
        payload["hypomorph"] = {
            "schema": PROGRAM_SCHEMA,
            "gate": "hypomorph",
            "program_effect": hypomorph,
            "status": hypomorph,
            "reason": "fixture",
        }
    if exposure is not None:
        payload["exposure"] = {
            "schema": EXPOSURE_SCHEMA,
            "program_effect": exposure,
            "status": exposure,
            "reason": "fixture",
        }
    if concordance is not None:
        payload["concordance"] = {
            "schema": PROGRAM_SCHEMA,
            "gate": "concordance",
            "program_effect": concordance,
            "status": concordance,
            "source_fingerprint": "a" * 64,
            "reason": "fixture",
        }
    return {name: _stamp_receipt(receipt) for name, receipt in payload.items()}


class HypothesisBindingTests(unittest.TestCase):
    def test_observed_identity_without_gate_pass_stops(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            **_nested_gates(confirmation="hold"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("confirmation", result["unbound_roles"])

    def test_observed_stability_and_probe_cannot_omit_assay_objects(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            **_nested_gates(),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("stability", result["unbound_roles"])
        self.assertIn("probe", result["unbound_roles"])

    def test_status_tick_cannot_bind_as_nested_pass(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            confirmation={
                "schema": PROGRAM_SCHEMA,
                "gate": "confirmation",
                "status": "pass",
            },
            phase={
                "schema": PROGRAM_SCHEMA,
                "gate": "phase",
                "program_effect": "pass",
            },
            transcript={
                "schema": PROGRAM_SCHEMA,
                "gate": "transcript",
                "program_effect": "pass",
            },
            hypomorph={
                "schema": PROGRAM_SCHEMA,
                "gate": "hypomorph",
                "program_effect": "pass",
            },
            exposure={"schema": EXPOSURE_SCHEMA, "program_effect": "pass"},
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("confirmation", result["unbound_roles"])

    def test_schema_less_pass_object_cannot_bind(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            confirmation={"gate": "confirmation", "program_effect": "pass"},
            phase={
                "schema": PROGRAM_SCHEMA,
                "gate": "phase",
                "program_effect": "pass",
            },
            transcript={
                "schema": PROGRAM_SCHEMA,
                "gate": "transcript",
                "program_effect": "pass",
            },
            hypomorph={
                "schema": PROGRAM_SCHEMA,
                "gate": "hypomorph",
                "program_effect": "pass",
            },
            exposure={"schema": EXPOSURE_SCHEMA, "program_effect": "pass"},
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("confirmation", result["unbound_roles"])

    def test_missing_alternative_stops(self) -> None:
        payload = _evidence()
        payload["links"] = [
            link for link in payload["links"] if link["hypothesis_role"] != "alternative"
        ]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "no_alternative")

    def test_observed_alternative_is_not_excluded(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "alternative":
                link["status"] = "observed"
        result = assess_hypothesis_strength(
            payload,
            **_nested_gates(hypomorph="pass", exposure="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_not_excluded")
        self.assertEqual(result["alternative_observed_ids"], ["syn-link-alternative"])

    def test_link_fields_cannot_be_empty(self) -> None:
        payload = _evidence()
        payload["links"][0]["supports"] = ""
        with self.assertRaises(HypothesisStrengthError):
            assess_hypothesis_strength(payload)
        payload = _evidence()
        payload["links"][0]["statement"] = "   "
        with self.assertRaises(HypothesisStrengthError):
            assess_hypothesis_strength(payload)
        payload = _evidence()
        del payload["links"][0]["does_not_support"]
        with self.assertRaises(HypothesisStrengthError):
            assess_hypothesis_strength(payload)

    def test_inferred_falsifier_kills_the_lead(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["status"] = "inferred"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "hypothesis_falsified")
        self.assertEqual(result["falsified_ids"], ["syn-link-falsifier"])

    def test_vocabulary_must_be_the_canonical_status_set(self) -> None:
        payload = _evidence()
        payload["status_vocabulary"] = ["observed", "unknown"]
        with self.assertRaises(HypothesisStrengthError):
            assess_hypothesis_strength(payload)
        payload = _evidence()
        payload["status_vocabulary"].append("observed")
        with self.assertRaises(HypothesisStrengthError):
            assess_hypothesis_strength(payload)

    def test_inferred_alternative_is_not_excluded(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "alternative":
                link["status"] = "inferred"
        result = assess_hypothesis_strength(
            payload,
            **_nested_gates(hypomorph="pass", exposure="pass", concordance="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_not_excluded")

    def test_missing_controls_stop(self) -> None:
        payload = _evidence()
        payload["links"] = [
            link
            for link in payload["links"]
            if link["hypothesis_role"] not in {"positive_control", "negative_control"}
        ]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "no_controls")

    def test_failed_positive_control_stops(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "positive_control":
                link["status"] = "observed"
                link["supports"] = "positive control failed"
        result = assess_hypothesis_strength(
            payload,
            **_nested_gates(hypomorph="pass", exposure="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "control_failed")
        self.assertEqual(result["failed_control_ids"], ["syn-link-positive-control"])

    def test_unconditional_falsifier_is_not_a_kill_rule(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "The chaperone-style pair program rests on a predeclared "
                    "synthetic kill rule."
                )
                link["supports"] = "a predeclared kill rule"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "untestable_falsifier")

    def test_single_family_alternative_ignores_masquerade(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "alternative":
                link["statement"] = (
                    "An apparent generation drop is competing cytostasis "
                    "rather than fewer new segregation errors."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_ignores_masquerade")

    def test_positive_control_must_be_the_exact_correction_row(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "positive_control":
                link["statement"] = (
                    "A treated culture row must keep checkpoint function "
                    "under the same imaging protocol."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "positive_control_not_exact")

    def test_negative_control_must_be_a_baseline_row(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "negative_control":
                link["statement"] = (
                    "Probe-treated wild-genotype rows must keep the "
                    "predeclared error rate under the same imaging protocol."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "negative_control_not_baseline")

    def test_falsifier_without_endpoint_is_untestable(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "If the probe arm fails or cytostasis rises, the "
                    "chaperone-style pair program stops."
                )
                link["supports"] = "a predeclared kill rule"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_ignores_endpoint")

    def test_falsifier_without_confounder_is_not_a_kill_rule(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "If missense RNA is absent or exact correction does not "
                    "reverse the defect, the chaperone-style pair program stops."
                )
                link["supports"] = "a predeclared kill rule"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_ignores_masquerade")

    def test_controls_must_run_under_the_same_protocol(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "negative_control":
                link["statement"] = (
                    "Vehicle-treated compound-genotype rows must keep the "
                    "predeclared error rate."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "controls_not_protocol_matched")

    def test_hypothesis_without_endpoint_is_untestable(self) -> None:
        payload = _evidence()
        payload["links"] = [
            link
            for link in payload["links"]
            if link["hypothesis_role"] != "endpoint"
        ]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "no_endpoint")

    def test_falsifier_must_be_predeclared(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "If missense RNA is absent, exact correction does not "
                    "return the endpoint to within 2-fold of baseline, "
                    "competing cytostasis or clone selection rises, batch "
                    "drift or probe interference or "
                    "aggregation accounts for the gain, or error-line "
                    "daughters become fitter, the chaperone-style pair "
                    "program stops."
                )
                link["supports"] = "a kill rule for the probe hypothesis"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_not_predeclared")

    def test_statement_uniqueness_is_required_across_links(self) -> None:
        payload = _evidence()
        payload["links"][1]["statement"] = payload["links"][0]["statement"]
        with self.assertRaisesRegex(
            HypothesisStrengthError, "statements must be distinct"
        ):
            assess_hypothesis_strength(payload)

    def test_token_set_permutations_are_not_distinct_statements(self) -> None:
        payload = _evidence()
        base = payload["links"][0]["statement"].split()
        payload["links"][1]["statement"] = " ".join(reversed(base))
        with self.assertRaisesRegex(
            HypothesisStrengthError, "token-set permutations"
        ):
            assess_hypothesis_strength(payload)

    def test_supports_cannot_donate_floor_terms(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = "The experimental condition is considered."
                link["supports"] = (
                    "if isogenic rna stops selection predeclared 50 fold "
                    "threshold exact corrected"
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "untestable_falsifier")

    def test_endpoint_without_direction_is_not_a_measurement(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["statement"] = (
                    "The synthetic compound genotype is studied alongside "
                    "the exact-corrected row."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_without_direction")

    def test_pair_without_allelic_configuration_is_not_a_pair(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "pair":
                link["statement"] = (
                    "The two synthetic alleles co-occur in a real genome."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "pair_without_configuration")

    def test_stability_without_measurable_property_is_not_an_assay(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "stability":
                link["statement"] = (
                    "The missense synthetic allele affects the full-length "
                    "product somehow."
                )
                link["supports"] = "an assay on the exact synthetic allele"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "stability_without_property")

    def test_transcript_without_measurand_is_not_an_assay(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "transcript":
                link["statement"] = (
                    "The tested cells show the expected molecular phenotype."
                )
                link["supports"] = "nothing until a record is filled"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "transcript_without_measurand")

    def test_probe_without_mechanism_is_not_a_probe(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "probe":
                link["statement"] = (
                    "A compound can raise functional product from the "
                    "missense allele under an exposure gate."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "probe_without_mechanism")

    def test_duplicate_link_ids_are_rejected(self) -> None:
        payload = _evidence()
        payload["links"].append(dict(payload["links"][0]))
        with self.assertRaises(HypothesisStrengthError):
            assess_hypothesis_strength(payload)

    def test_alternative_must_explain_the_measured_endpoint(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "alternative":
                link["statement"] = (
                    "An apparent signal is competing cytostasis or clone "
                    "selection rather than a real effect."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_ignores_endpoint")

    def test_alternative_must_be_killable_by_the_falsifier(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "alternative":
                link["statement"] = (
                    "An apparent generation drop is clone selection or "
                    "toxicity rather than fewer new segregation "
                    "errors; dye interference is also suspected."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_not_killable")

    def test_endpoint_must_compare_against_the_exact_correction(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["statement"] = (
                    "The synthetic compound genotype increases first-division "
                    "errors versus a treated row."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_without_exact_comparator")

    def test_falsifier_must_watch_the_exact_correction(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "Under the predeclared rule: if missense RNA is "
                    "absent, the defect persists, competing cytostasis "
                    "rises, clone selection wins, batch drift or dye "
                    "interference accounts for the gain, or error-line "
                    "daughters become fitter, the chaperone-style pair "
                    "program stops."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_ignores_correction")

    def test_kill_word_riding_inside_a_longer_word_is_not_a_kill_rule(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "If the cell stopsign rna, cytostasis is predeclared."
                )
                link["supports"] = "a predeclared kill rule"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "untestable_falsifier")

    def test_blank_alternative_cannot_ride_on_sibling_coverage(self) -> None:
        payload = _evidence()
        payload["links"].append(
            {
                "link_id": "syn-link-other-risk",
                "hypothesis_role": "alternative",
                "statement": "Some other unnamed mechanism could explain it.",
                "status": "planned_experiment",
                "supports": "a predeclared competing explanation",
                "does_not_support": "a completed mechanism or a medicine claim",
            }
        )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_ignores_masquerade")

    def test_confusable_cyrillic_still_counts_as_masquerade(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "alternative":
                link["statement"] = (
                    "An apparent generation drop is competing cytostasis, "
                    "clone selection, or \u0442oxicity rather than fewer new "
                    "segregation errors."
                )
        result = assess_hypothesis_strength(payload)
        self.assertNotEqual(result["reason"], "alternative_ignores_masquerade")

    def test_control_parity_cannot_drift_to_a_different_link(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "positive_control":
                link["statement"] = (
                    "Wild-type and exact-corrected rows must keep checkpoint "
                    "function."
                )
        payload["links"].append(
            {
                "link_id": "syn-link-parity-drift",
                "hypothesis_role": "positive_control",
                "statement": (
                    "Assay rows run under the same imaging protocol."
                ),
                "status": "planned_experiment",
                "supports": "a predeclared positive control",
                "does_not_support": "a completed control result",
            }
        )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "positive_control_not_exact")

    def test_underdeclared_strength_stops(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        payload["declared_overall_strength"] = "experiment_to_run"
        result = assess_hypothesis_strength(
            payload, **_nested_gates(hypomorph="pass", exposure="pass")
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "declared_understrong")

    def test_observed_control_must_bind_to_exposure_gate(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "positive_control":
                link["status"] = "observed"
        result = assess_hypothesis_strength(
            payload, **_nested_gates(exposure="hold")
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")

    def test_contradictions_report_before_wording_findings(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["status"] = "observed"
                link["statement"] = (
                    "If rescued, generation-limit errors return to baseline "
                    "in the treated synthetic compound genotype and rescue "
                    "has been achieved."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "hypothesis_falsified")

    def test_non_kill_falsifier_blob_cannot_supply_masquerade(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "If the synthetic compound genotype does not exceed the "
                    "exact-corrected endpoint, the program stops."
                )
        payload["links"].append(
            {
                "link_id": "syn-link-falsifier-donor",
                "hypothesis_role": "falsifier",
                "statement": (
                    "Predeclared: cytostasis and selection on the endpoint "
                    "are noted risks."
                ),
                "status": "planned_experiment",
                "supports": "a predeclared falsification rule",
                "does_not_support": "a falsified hypothesis",
            }
        )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_ignores_masquerade")

    def test_kill_rule_must_name_a_measurable_boundary(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "If the synthetic compound genotype does not improve on "
                    "the exact-corrected endpoint amid cytostasis, clone "
                    "selection, batch drift, or dye interference, the "
                    "predeclared program stops."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_without_boundary")

    def test_wild_type_alone_is_not_an_exact_control(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "positive_control":
                link["statement"] = (
                    "Wild-type rows must keep checkpoint function under the "
                    "same imaging protocol."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "positive_control_not_exact")

    def test_endpoint_cannot_compare_to_wild_type_only(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["statement"] = (
                    "The synthetic compound genotype increases first-division "
                    "segregation errors versus the wild-type row."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_without_exact_comparator")

    def test_unknown_falsifier_cannot_populate_a_kill_rule(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["status"] = "unknown"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "untestable_falsifier")

    def test_kill_rule_must_carry_a_numeric_bound(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "Under the predeclared rule: if missense RNA is "
                    "absent, exact correction does not return the endpoint "
                    "to baseline, competing cytostasis or clone selection "
                    "rises, batch drift or probe interference or "
                    "aggregation accounts for the gain, or "
                    "error-line daughters become fitter, the "
                    "chaperone-style pair program stops."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_without_numeric_bound")

    def test_missing_multiplicity_rule_stops(self) -> None:
        payload = _evidence()
        payload["links"] = [
            link
            for link in payload["links"]
            if link["hypothesis_role"] != "multiplicity"
        ]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "no_multiplicity")

    def test_multiplicity_link_must_name_a_rule(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "multiplicity":
                link["statement"] = "Several probes will be tested."
                link["supports"] = "a note about the probe panel"
                link["does_not_support"] = "a completed statistical result"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "multiplicity_without_rule")

    def test_alternatives_must_cover_interference_artifacts(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "alternative":
                link["statement"] = (
                    "An apparent generation drop is competing cytostasis or "
                    "clone selection rather than fewer new errors on the "
                    "endpoint."
                )
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "Under the predeclared rule: if missense RNA is "
                    "absent, exact correction does not return the endpoint "
                    "to within 2-fold of baseline, competing cytostasis or "
                    "clone selection accounts for the gain, or error-line "
                    "daughters become fitter, the chaperone-style pair "
                    "program stops."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_ignores_interference")

    def test_missing_counterscreen_stops(self) -> None:
        payload = _evidence()
        payload["links"] = [
            link
            for link in payload["links"]
            if link["hypothesis_role"] != "counterscreen"
        ]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "no_counterscreen")

    def test_counterscreen_must_name_orthogonal_assay_and_family(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "counterscreen":
                link["statement"] = (
                    "A secondary readout will be recorded for each probe."
                )
                link["supports"] = "a planned secondary readout"
                link["does_not_support"] = "a completed secondary result"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "counterscreen_without_assay")

    def test_commitment_links_cannot_claim_observed(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "multiplicity":
                link["status"] = "observed"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "commitment_claimed_observed")

        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "counterscreen":
                link["status"] = "inferred"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "commitment_claimed_observed")

    def test_falsifier_must_watch_an_endpoint_link(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                del link["watches"]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_watch_unresolved")

        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["watches"] = ["syn-link-positive-control"]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_watch_unresolved")

    def test_kill_bound_must_be_anchored_to_an_endpoint_bound(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = (
                    "Under the predeclared rule: if missense RNA is "
                    "absent, exact correction does not return the endpoint "
                    "to within 7-fold of baseline, competing cytostasis "
                    "or clone selection rises, batch drift or probe "
                    "interference or aggregation accounts for "
                    "the gain, or error-line daughters become fitter, the "
                    "chaperone-style pair program stops."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_bound_unanchored")

    def test_watch_graph_is_required_beyond_the_falsifier(self) -> None:
        for role in ("alternative", "positive_control", "negative_control"):
            with self.subTest(role=role):
                payload = _evidence()
                for link in payload["links"]:
                    if link["hypothesis_role"] == role:
                        link.pop("watches", None)
                result = assess_hypothesis_strength(payload)
                self.assertEqual(result["status"], "stop")
                self.assertEqual(result["reason"], "watch_unresolved")

        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["watches"] = ["syn-link-falsifier"]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "watch_unresolved")

    def test_multiplicity_rule_needs_a_numeric_level(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "multiplicity":
                link["statement"] = (
                    "A predeclared hierarchical gatekeeping rule controls "
                    "familywise error across candidate probes."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "multiplicity_without_alpha")

    def test_endpoint_must_carry_a_spec_object(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                del link["spec"]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_without_spec")

    def test_endpoint_comparator_must_be_a_correction_arm(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["spec"]["control_arm"] = "vehicle-treated"
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_without_spec")

        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["spec"]["blinded"] = False
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_without_spec")

    def test_kill_bound_must_equal_the_watched_endpoint_bound(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["bound"] = 7.0
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "falsifier_bound_unequal")

    def test_watch_graph_must_be_acyclic(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["watches"] = ["syn-link-probe", "syn-link-falsifier"]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "watch_cycle")

    def test_evidence_chain_must_be_wired(self) -> None:
        for role, expected in (
            ("pair", "watch_unresolved"),
            ("transcript", "watch_unresolved"),
            ("stability", "watch_unresolved"),
            ("probe", "watch_unresolved"),
        ):
            with self.subTest(role=role):
                payload = _evidence()
                for link in payload["links"]:
                    if link["hypothesis_role"] == role:
                        link.pop("watches", None)
                result = assess_hypothesis_strength(payload)
                self.assertEqual(result["status"], "stop")
                self.assertEqual(result["reason"], expected)

    def test_every_endpoint_must_be_killed_and_controlled(self) -> None:
        extra = {
            "link_id": "syn-link-segregation-2",
            "hypothesis_role": "endpoint",
            "statement": (
                "A second lineage outcome: the treated compound genotype "
                "increases first-division segregation errors versus the "
                "exact-corrected row at a predeclared 3-fold bound."
            ),
            "status": "planned_experiment",
            "supports": "second endpoint",
            "does_not_support": "child claim",
            "watches": ["syn-link-probe"],
            "spec": {
                "measurement": "second-division segregation error rate",
                "control_arm": "exact-corrected",
                "treatment_arm": "probe-treated compound genotype",
                "rescue_bound": 3.0,
            },
        }
        payload = _evidence()
        payload["links"].append(dict(extra))
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_unkilled")

        payload = _evidence()
        payload["links"].append(dict(extra))
        for link in payload["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["watches"].append("syn-link-segregation-2")
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_uncontrolled")

    def test_every_probe_must_be_counterscreened(self) -> None:
        payload = _evidence()
        payload["links"].append(
            {
                "link_id": "syn-link-probe-2",
                "hypothesis_role": "probe",
                "statement": (
                    "A second synthetic chaperone-family probe is "
                    "declared for the participant-specific pair program."
                ),
                "status": "hypothesis",
                "supports": "second candidate probe",
                "does_not_support": "child claim",
                "watches": ["syn-link-missense-stability"],
            }
        )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "probe_unscreened")

    def test_multiplicity_must_cover_the_whole_family(self) -> None:
        payload = _evidence()
        payload["links"].append(
            {
                "link_id": "syn-link-probe-2",
                "hypothesis_role": "probe",
                "statement": (
                    "A second synthetic chaperone-family probe is "
                    "declared for the participant-specific pair program."
                ),
                "status": "hypothesis",
                "supports": "second candidate probe",
                "does_not_support": "child claim",
                "watches": ["syn-link-missense-stability"],
            }
        )
        for link in payload["links"]:
            if link["hypothesis_role"] == "counterscreen":
                link["watches"] = ["syn-link-probe", "syn-link-probe-2"]
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(
            result["reason"], "multiplicity_family_uncovered"
        )

    def test_endpoint_must_be_lineage_tracked(self) -> None:
        payload = _evidence()
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["statement"] = (
                    "The synthetic compound genotype increases checkpoint "
                    "activity versus the exact-corrected row."
                )
        result = assess_hypothesis_strength(payload)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "endpoint_not_lineage_tracked")

    def test_observed_stability_without_hypomorph_pass_stops(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            **_nested_gates(hypomorph="hold", exposure="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("stability", result["unbound_roles"])

    def test_observed_probe_without_exposure_pass_stops(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            **_nested_gates(hypomorph="pass", exposure="hold"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("probe", result["unbound_roles"])

    def test_observed_pair_program_with_all_gates_can_pass(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            **_nested_gates(hypomorph="pass", exposure="pass", concordance="pass"),
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["unbound_roles"], [])

    def test_observed_endpoint_cannot_omit_concordance(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["status"] = "observed"
        result = assess_hypothesis_strength(
            payload,
            **_nested_gates(hypomorph="pass", exposure="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("endpoint", result["unbound_roles"])

    def test_observed_endpoint_without_concordance_pass_stops(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["status"] = "observed"
        result = assess_hypothesis_strength(
            payload,
            **_nested_gates(hypomorph="pass", exposure="pass", concordance="hold"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("endpoint", result["unbound_roles"])

    def test_forged_concordance_without_fingerprint_cannot_bind(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["status"] = "observed"
        gates = _nested_gates(hypomorph="pass", exposure="pass", concordance="pass")
        gates["concordance"].pop("source_fingerprint")
        result = assess_hypothesis_strength(payload, **gates)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("endpoint", result["unbound_roles"])

    def test_mismatched_clone_safety_fingerprint_cannot_bind(self) -> None:
        payload = mark_pair_program_observed(_evidence())
        for link in payload["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["status"] = "observed"
        result = assess_hypothesis_strength(
            payload,
            clone_safety=_stamp_receipt(
                {
                    "schema": "mva-track2-clone-safety/v1",
                    "clone_safety_stop": False,
                    "program_effect": "pass",
                    "status": "pass",
                    "source_fingerprint": "b" * 64,
                    "reason": "fixture",
                }
            ),
            **_nested_gates(hypomorph="pass", exposure="pass", concordance="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_without_gate")
        self.assertIn("endpoint", result["unbound_roles"])

    def test_clone_safety_stop_auto_fails_the_alternative(self) -> None:
        result = assess_hypothesis_strength(
            mark_pair_program_observed(_evidence()),
            clone_safety={"schema": "mva-track2-clone-safety/v1", "clone_safety_stop": True, "program_effect": "stop"},
            **_nested_gates(hypomorph="pass", exposure="pass", concordance="pass"),
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "alternative_not_excluded")
        self.assertIn("syn-auto-competing-toxicity", result["alternative_observed_ids"])

    def test_nested_gate_status_effect_divergence_stops(self) -> None:
        from mva_hackathon.hypothesis import _nested_effect

        self.assertEqual(
            _nested_effect({"status": "stop", "program_effect": "pass"}), "stop"
        )
        self.assertEqual(
            _nested_effect({"status": "pass", "program_effect": "stop"}), "stop"
        )
        self.assertEqual(
            _nested_effect(
                _stamp_receipt(
                    {
                        "status": "pass",
                        "program_effect": "pass",
                        "schema": "mva-test/v1",
                        "reason": "ok",
                    }
                )
            ),
            "pass",
        )
        # A pass claim without a valid self-integrity digest cannot bind.
        self.assertEqual(
            _nested_effect({"status": "pass", "program_effect": "pass"}), "stop"
        )
        # Nor can a minimal fabricated mapping with a digest but no receipt
        # surface (schema) — a real gate receipt always declares one.
        self.assertEqual(
            _nested_effect(
                _stamp_receipt({"status": "pass", "program_effect": "pass"})
            ),
            "stop",
        )
        tampered = _stamp_receipt({"status": "pass", "program_effect": "pass"})
        tampered["reason"] = "mutated post-hoc"
        self.assertEqual(_nested_effect(tampered), "stop")
        self.assertEqual(
            _nested_effect(
                {"status": "not_assessable", "program_effect": "hold"}
            ),
            "hold",
        )
        self.assertEqual(
            _nested_effect(
                {"status": "not_assessable", "program_effect": "pass"}
            ),
            "stop",
        )
        self.assertIsNone(_nested_effect({"status": "pass"}))
        self.assertIsNone(_nested_effect(None))


if __name__ == "__main__":
    unittest.main()
