from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.community_pipeline import (
    CLAIM_BOUNDARY,
    MAX_TOOLKIT_FILE_BYTES,
    SCHEMA,
    CommunityPipelineError,
    run_community_pipeline,
)
from mva_hackathon.hypothesis import mark_pair_program_observed
from mva_hackathon.program_gates import assess_evidence_links, assess_family_worksheet
from mva_hackathon.save_path import (
    declare_next_gate,
    passing_exposure,
    write_passing_confirmation,
    write_passing_transcript,
)


ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = ROOT / "templates" / "community"
REQUIRED = (
    "phase_record.synthetic.json",
    "confirmation_record.synthetic.json",
    "transcript_record.synthetic.json",
    "allele_function_scorecard.synthetic.json",
    "measured_exposure_table.synthetic.json",
    "lineage_count_table.synthetic.json",
    "blinded_count_table.synthetic.json",
    "replication_decision.synthetic.json",
    "observed_inferred_unknown.synthetic.json",
    "family_plain_language.synthetic.md",
    "causal_chain_worksheet.synthetic.json",
    "assay_power.synthetic.json",
    "structure_ranking.synthetic.json",
)


def _copy_toolkit(folder: Path) -> Path:
    dest = folder / "community"
    dest.mkdir()
    for name in REQUIRED:
        shutil.copy(COMMUNITY / name, dest / name)
    return dest


def _reject_duplicate_keys(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON float {value!r}")
    return parsed


def _json_loads(text: str) -> object:
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _passing_lineage(*, competing: bool = False) -> dict:
    death = 1 if competing else 0
    no_division = 1 if competing else 0
    opportunities = 38 if competing else 36
    profile_id = next(
        row["exposure_profile_id"]
        for row in _json_loads(
            (COMMUNITY / "measured_exposure_table.synthetic.json").read_text(
                encoding="utf-8"
            )
        )["rows"]
        if row["nominal_uM"] == 1.0 and row["pulse_vs_constant"] == "constant"
    )
    runs = []
    for index in range(1, 4):
        for clone in range(1, 7):
            for arm, positive, member in (
                ("vehicle", 12, "member-a"),
                ("treatment", 4, "member-b"),
            ):
                runs.append(
                    {
                        "arm": arm,
                        "edit_event_id": f"syn-event-{index}",
                        "clone_id": f"syn-clone-{index}-{clone}",
                        "run_id": f"syn-run-{index}",
                        "batch_id": "syn-batch-a",
                        "functional_execution_id": (
                            f"syn-functional-{index}-{clone}-{member}"
                        ),
                        "exposure_support_record_id": (
                            "syn-measurement-3"
                            if arm == "treatment"
                            else "syn-vehicle-control-record-a"
                        ),
                        "exposure_profile_id": (
                            profile_id
                            if arm == "treatment"
                            else "profile-vehicle-control"
                        ),
                        "exposure_probe_id": (
                            "syn-probe-a" if arm == "treatment" else "syn-vehicle-a"
                        ),
                        "exposure_started_at": "2026-08-29T01:00:00Z",
                        "endpoint_recorded_at": "2026-08-30T02:00:00Z",
                        "latest_enrolled_at": "2026-08-29T00:00:00Z",
                        "opportunities": opportunities,
                        "detected_divisions": 36,
                        "event_positive_divisions": positive,
                        "event_negative_divisions": 36 - positive,
                        "event_positive_daughters_followed": 2 * positive,
                        "event_positive_daughters_reproduced": positive,
                        # Fully resolved fates: no censored gap in the
                        # nominal fixture; reproduction rate stays 0.5.
                        "event_positive_daughters_died": positive,
                        "event_negative_daughters_followed": 8,
                        "event_negative_daughters_reproduced": 8,
                        "event_negative_daughters_died": 0,
                        "pre_division_death": death,
                        "no_division": no_division,
                        "dropout_censored": 0,
                    }
                )
    return {
        "schema": "mva-track2-lineage-counts/v1",
        "study_id": "syn-save-path-lineage",
        "synthetic_only": True,
        "lock_state": "locked",
        "blinded": True,
        "runs": runs,
    }


def _blinded_from_lineage(lineage: dict) -> dict:
    runs = []
    for row in lineage["runs"]:
        runs.append(
            {
                "arm": row["arm"],
                "edit_event_id": int(str(row["edit_event_id"]).rsplit("-", 1)[-1]),
                "clone_id": int(str(row["clone_id"]).rsplit("-", 1)[-1]),
                "run_id": int(str(row["run_id"]).rsplit("-", 1)[-1]),
                "opportunities": row["opportunities"],
                "detected_divisions": row["detected_divisions"],
                "event_positive_divisions": row["event_positive_divisions"],
                "event_negative_divisions": row["event_negative_divisions"],
                "event_positive_daughters_followed": row[
                    "event_positive_daughters_followed"
                ],
                "event_positive_daughters_reproduced": row[
                    "event_positive_daughters_reproduced"
                ],
                "event_positive_daughters_died": row.get(
                    "event_positive_daughters_died", 0
                ),
                "event_negative_daughters_followed": row.get(
                    "event_negative_daughters_followed", 0
                ),
                "event_negative_daughters_reproduced": row.get(
                    "event_negative_daughters_reproduced", 0
                ),
                "event_negative_daughters_died": row.get(
                    "event_negative_daughters_died", 0
                ),
                "event_positive_daughter_slots": row.get(
                    "event_positive_daughter_slots"
                ),
                "event_negative_daughter_slots": row.get(
                    "event_negative_daughter_slots"
                ),
                "event_positive_multipolar_divisions": row.get(
                    "event_positive_multipolar_divisions"
                ),
                "pre_division_death": row.get("pre_division_death", 0),
                "no_division": row.get("no_division", 0),
                "dropout_censored": row.get("dropout_censored", 0),
            }
        )
    return {
        "schema": "mva.community-blinded-count-table/v2",
        "privacy_class": "synthetic",
        "purpose": "Aligned synthetic blinded counts for identity tests.",
        "observed_run_fields": [
            "arm",
            "edit_event_id",
            "clone_id",
            "run_id",
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
            "event_positive_daughter_slots",
            "event_negative_daughter_slots",
            "event_positive_multipolar_divisions",
            "pre_division_death",
            "no_division",
            "dropout_censored",
        ],
        "runs": runs,
    }


def _tick_replication(dest: Path) -> None:
    path = dest / "replication_decision.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    payload["endpoints_concordant"] = True
    _write_json(path, payload)


def _set_missense_checkpoint(dest: Path, status: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] not in {"missense", "recreated_missense"}:
            continue
        for item in row["assessments"]:
            if item["endpoint"] == "checkpoint":
                item["assessment_status"] = status
                if status == "positive":
                    item["assay_class"] = "wet"
                    item["condition_class"] = "basal"
                    item["system_class"] = "cellular"
                    item["expression_class"] = "endogenous"
                    item["specimen_class"] = "assay_matched"
    _write_json(path, payload)


def _write_aligned_counts(dest: Path, *, competing: bool = False) -> dict:
    lineage = _passing_lineage(competing=competing)
    plan = _json_loads(
        (dest / "assay_power.synthetic.json").read_text(encoding="utf-8")
    )
    exposure = passing_exposure(lineage, plan)
    _write_json(dest / "lineage_count_table.synthetic.json", lineage)
    _write_json(dest / "blinded_count_table.synthetic.json", _blinded_from_lineage(lineage))
    _write_json(
        dest / "measured_exposure_table.synthetic.json",
        exposure,
    )
    return lineage


class CommunityPipelineTests(unittest.TestCase):
    def test_community_templates_hold_when_confirmation_is_incomplete(self) -> None:
        result = run_community_pipeline(COMMUNITY)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["blocked_by"], "confirmation")
        self.assertEqual(result["block_reason"], "layout_incomplete")
        skipped = {item["name"] for item in result["steps"] if item["skipped"]}
        self.assertEqual(
            skipped,
            {
                "phase",
                "transcript",
                "hypomorph",
                "exposure",
                "count_identity",
                "assay_power",
                "clone_safety",
                "concordance",
                "replication",
            },
        )
        ran = {item["name"]: item["program_effect"] for item in result["steps"] if not item["skipped"]}
        self.assertEqual(ran["hypothesis"], "pass")
        self.assertEqual(ran["family"], "pass")
        self.assertEqual(ran["structure_ranking"], "pass")
        self.assertEqual(ran["confirmation"], "hold")
        self.assertEqual(ran["next_experiment"], "pass")
        next_step = next(item for item in result["steps"] if item["name"] == "next_experiment")
        self.assertEqual(next_step["result"]["recommended_step"], "confirmation")

    def test_adequate_followup_still_holds_when_tables_disagree(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            write_passing_confirmation(dest)
            write_passing_transcript(dest)
            path = dest / "lineage_count_table.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            row = next(
                item for item in payload["runs"] if item["arm"] == "treatment"
            )
            row["event_positive_divisions"] = 5
            row["event_negative_divisions"] = 31
            row["event_positive_daughters_followed"] = 8
            row["event_positive_daughters_reproduced"] = 4
            path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["blocked_by"], "count_identity")
        self.assertEqual(result["block_reason"], "count_tables_inconsistent")
        skipped = {item["name"] for item in result["steps"] if item["skipped"]}
        self.assertEqual(skipped, {"assay_power", "clone_safety", "concordance", "replication"})

    def test_aligned_competing_risk_cannot_use_the_blinded_table_as_rescue(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            write_passing_confirmation(dest)
            write_passing_transcript(dest)
            _write_aligned_counts(dest, competing=True)
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["blocked_by"], "count_identity")
        self.assertEqual(result["block_reason"], "competing_risk_present")

    def test_cis_stops_and_skips_later_gates(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            write_passing_confirmation(dest)
            phase_path = dest / "phase_record.synthetic.json"
            payload = _json_loads(phase_path.read_text(encoding="utf-8"))
            payload["decision"] = "cis_confirmed"
            for guide in payload["guide_configurations"]:
                guide["linkage_call"] = "cis"
            phase_path.write_text(
                json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
            )
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["blocked_by"], "phase")
        skipped = {item["name"] for item in result["steps"] if item["skipped"]}
        self.assertGreaterEqual(
            skipped,
            {
                "transcript",
                "hypomorph",
                "exposure",
                "count_identity",
                "assay_power",
                "clone_safety",
                "concordance",
                "replication",
            },
        )
        ran = {item["name"] for item in result["steps"] if not item["skipped"]}
        self.assertIn("hypothesis", ran)

    def test_duplicate_json_keys_in_toolkit_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "observed_inferred_unknown.synthetic.json"
            raw = path.read_text(encoding="utf-8")
            path.write_text(
                raw.replace(
                    '"declared_probe_is_medicine"',
                    '"declared_probe_is_medicine": true, "declared_probe_is_medicine"',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CommunityPipelineError, "duplicate JSON key"):
                run_community_pipeline(dest)

    def test_nonfinite_json_number_in_toolkit_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "observed_inferred_unknown.synthetic.json"
            raw = path.read_text(encoding="utf-8")
            path.write_text(
                raw.replace(
                    '"declared_probe_is_medicine": false',
                    '"declared_probe_is_medicine": NaN',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CommunityPipelineError, "non-finite"):
                run_community_pipeline(dest)

    def test_oversized_toolkit_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "observed_inferred_unknown.synthetic.json"
            raw = _json_loads(path.read_text(encoding="utf-8"))
            raw["padding"] = "x" * (MAX_TOOLKIT_FILE_BYTES)
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(CommunityPipelineError, "size limit"):
                run_community_pipeline(dest)

    def test_deeply_nested_toolkit_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "observed_inferred_unknown.synthetic.json"
            depth = 1200
            path.write_text(
                '{"a":' * depth + "1" + "}" * depth, encoding="utf-8"
            )
            # Deep JSON may be rejected by the pipeline loader or by the gate
            # contract downstream — either way it fails closed.
            with self.assertRaises(ValueError):
                run_community_pipeline(dest)

    def test_observed_trans_overclaim_stops_the_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "observed_inferred_unknown.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            for link in payload["links"]:
                if link["link_id"] == "syn-link-phase":
                    link["statement"] = (
                        "The two synthetic alleles are in trans in a real genome."
                    )
                    link["status"] = "observed"
            path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["blocked_by"], "evidence")
        skipped = {item["name"] for item in result["steps"] if item["skipped"]}
        self.assertIn("phase", skipped)

    def test_inferred_link_carrying_overclaim_wording_stops_the_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "observed_inferred_unknown.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            for link in payload["links"]:
                if link["link_id"] == "syn-link-phase":
                    link["statement"] = (
                        "Trans configuration implies clinical benefit for the participant."
                    )
                    link["status"] = "inferred"
            path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["blocked_by"], "evidence")

    def test_negated_comparator_label_cannot_satisfy_endpoint_spec(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "observed_inferred_unknown.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            for link in payload["links"]:
                if link.get("hypothesis_role") == "endpoint":
                    link["spec"]["control_arm"] = "uncorrected isogenic arm"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["blocked_by"], "hypothesis")

    def test_evidence_and_family_unit_contracts(self) -> None:
        evidence = _json_loads(
            (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(assess_evidence_links(evidence)["status"], "pass")
        family = (COMMUNITY / "family_plain_language.synthetic.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(assess_family_worksheet(family)["status"], "pass")
        stripped = family.replace("[result]", "filled")
        self.assertEqual(assess_family_worksheet(stripped)["reason"], "missing_blanks")
        no_cure = family.replace("not a cure", "not a miracle")
        self.assertEqual(assess_family_worksheet(no_cure)["reason"], "missing_disclaimer")
        overclaim = family.replace("[what this means]", "[what this means]\norgan size restored")
        self.assertEqual(assess_family_worksheet(overclaim)["reason"], "family_overclaim")
        save_claim = family.replace("[what this means]", "[what this means]\nthis will save")
        self.assertEqual(assess_family_worksheet(save_claim)["reason"], "family_overclaim")
        nearby_claim = family.replace(
            "[result]",
            "[result]\nnearby polymorphism proves the exact allele",
        )
        self.assertEqual(assess_family_worksheet(nearby_claim)["reason"], "family_overclaim")
        ortholog_claim = family.replace(
            "[result]",
            "[result]\northolog allele proves the exact allele",
        )
        self.assertEqual(assess_family_worksheet(ortholog_claim)["reason"], "family_overclaim")
        paralog_claim = family.replace(
            "[result]",
            "[result]\nparalog allele proves the exact allele",
        )
        self.assertEqual(assess_family_worksheet(paralog_claim)["reason"], "family_overclaim")
        alphafold_claim = family.replace(
            "[result]",
            "[result]\nalphafold proves the exact allele",
        )
        self.assertEqual(assess_family_worksheet(alphafold_claim)["reason"], "family_overclaim")
        geometry_claim = family.replace(
            "[result]",
            "[result]\ngeometry proves the exact allele",
        )
        self.assertEqual(assess_family_worksheet(geometry_claim)["reason"], "family_overclaim")
        coordinate_claim = family.replace(
            "[result]",
            "[result]\ncoordinate proves the exact allele",
        )
        self.assertEqual(assess_family_worksheet(coordinate_claim)["reason"], "family_overclaim")
        complementation_claim = family.replace(
            "[result]",
            "[result]\ncomplementation proves the exact allele",
        )
        self.assertEqual(
            assess_family_worksheet(complementation_claim)["reason"], "family_overclaim"
        )
        for phrase in (
            "in silico proves the exact allele",
            "insilico proves the exact allele",
            "alpha-fold proves the exact allele",
            "alpha fold proves the exact allele",
            "alpha-missense proves the exact allele",
            "alpha missense proves the exact allele",
            "fly allele proves the exact allele",
            "zebrafish allele proves the exact allele",
            "xenopus allele proves the exact allele",
            "c. elegans allele proves the exact allele",
            "c elegans allele proves the exact allele",
            "c-elegans allele proves the exact allele",
            "celegans allele proves the exact allele",
            "worm allele proves the exact allele",
            "pathogenicity score proves the exact allele",
            "esm proves the exact allele",
            "esm1b proves the exact allele",
            "revel proves the exact allele",
            "mave proves the exact allele",
            "frequency proves the exact allele",
            "conservation proves the exact allele",
            "clinvar proves the exact allele",
            "label proves the exact allele",
            "catalog proves the exact allele",
            "software proves the exact allele",
            "database proves the exact allele",
            "ontology proves the exact allele",
            "literature proves the exact allele",
            "cell-free proves the exact allele",
            "cell free proves the exact allele",
            "cellfree proves the exact allele",
            "thermal shift proves the exact allele",
            "thermal-shift proves the exact allele",
            "purified-protein proves the exact allele",
            "purified protein proves the exact allele",
            "ectopic proves the exact allele",
            "unmatched proves the exact allele",
            "unmatched-line proves the exact allele",
            "unmatched line proves the exact allele",
            "unmatched genotype proves the exact allele",
            "unmatched genotype line proves the exact allele",
            "unmatched-genotype proves the exact allele",
            "imposed-stress proves the exact allele",
            "imposed stress proves the exact allele",
            "imposed extrinsic stress proves the exact allele",
            "imposed-extrinsic-stress proves the exact allele",
            "rna-seq proves the exact allele",
            "rna seq proves the exact allele",
            "rnaseq proves the exact allele",
            "rna-seq phase proves the exact allele",
            "rna seq phase proves the exact allele",
            "computational haplotype proves the exact allele",
            "ranking proves the exact allele",
            "predictor proves the exact allele",
            "unlabeled proves the exact allele",
            "transgene proves the exact allele",
            "overexpression proves the exact allele",
            "over-expression proves the exact allele",
            "over expression proves the exact allele",
            "computational proves the exact allele",
            "in-silico proves the exact allele",
            "cdna proves the exact allele",
            "transient proves the exact allele",
            "transient transfection proves the exact allele",
            "biophysical proves the exact allele",
            "protein-surrogate proves the exact allele",
            "protein surrogate proves the exact allele",
        ):
            predictor_claim = family.replace("[result]", f"[result]\n{phrase}")
            self.assertEqual(
                assess_family_worksheet(predictor_claim)["reason"], "family_overclaim"
            )

    def test_observed_organ_size_story_is_an_overclaim(self) -> None:
        evidence = _json_loads(
            (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        evidence["links"].append(
            {
                "link_id": "syn-link-organ-size",
                "statement": "Organ size restored after the probe.",
                "status": "observed",
                "supports": "checkpoint rescued",
                "does_not_support": "nothing",
            }
        )
        result = assess_evidence_links(evidence)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_overclaim")
        self.assertIn("syn-link-organ-size", result["overclaim_ids"])

    def test_hyphenated_blocked_phrases_cannot_evade_detection(self) -> None:
        for statement in (
            "Organ-size restored after the probe.",
            "Checkpoint-rescued cells under the probe.",
            "This will-save the experiment.",
        ):
            with self.subTest(statement=statement):
                evidence = _json_loads(
                    (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                        encoding="utf-8"
                    )
                )
                evidence["links"].append(
                    {
                        "link_id": "syn-link-evasion",
                        "statement": statement,
                        "status": "observed",
                        "supports": "a synthetic measurement",
                        "does_not_support": "a child's claim",
                    }
                )
                result = assess_evidence_links(evidence)
                self.assertEqual(result["status"], "stop")
                self.assertEqual(result["reason"], "observed_overclaim")
                self.assertIn("syn-link-evasion", result["overclaim_ids"])

        family = (COMMUNITY / "family_plain_language.synthetic.md").read_text(
            encoding="utf-8"
        )
        hyphenated = family.replace(
            "[result]", "[result]\norgan-size restored in the culture"
        )
        self.assertEqual(
            assess_family_worksheet(hyphenated)["reason"], "family_overclaim"
        )

    def test_punctuated_and_zero_width_phrases_cannot_evade_detection(self) -> None:
        for statement in (
            "Organ, size restored after the probe.",
            'Organ "size" restored after the probe.',
            "Org\u200ban size restored after the probe.",
            "Organ.size! Restored after the probe.",
            "This will \u201csave\u201d the experiment.",
            "A fullwidth ｏrgan size restored after the probe.",
            "We observed clinical\u200bbenefit in this model.",
            "Organ\u200bsize restored after the probe.",
            "Checkpoint\u00adrescued cells under the probe.",
        ):
            with self.subTest(statement=statement):
                evidence = _json_loads(
                    (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                        encoding="utf-8"
                    )
                )
                evidence["links"].append(
                    {
                        "link_id": "syn-link-evasion",
                        "statement": statement,
                        "status": "observed",
                        "supports": "a synthetic measurement",
                        "does_not_support": "a child's claim",
                    }
                )
                result = assess_evidence_links(evidence)
                self.assertEqual(result["status"], "stop")
                self.assertEqual(result["reason"], "observed_overclaim")
                self.assertIn("syn-link-evasion", result["overclaim_ids"])

        family = (COMMUNITY / "family_plain_language.synthetic.md").read_text(
            encoding="utf-8"
        )
        punctuated = family.replace(
            "[result]", "[result]\norgan, size restored in the culture"
        )
        self.assertEqual(
            assess_family_worksheet(punctuated)["reason"], "family_overclaim"
        )

    def test_observed_nearby_polymorphism_cannot_count_as_exact_function(self) -> None:
        evidence = _json_loads(
            (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        evidence["links"].append(
            {
                "link_id": "syn-link-nearby-polymorphism",
                "hypothesis_role": "stability",
                "statement": "A nearby polymorphism matches the missense class.",
                "status": "observed",
                "supports": "nearby polymorphism proves the exact synthetic allele",
                "does_not_support": "nothing",
            }
        )
        result = assess_evidence_links(evidence)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_overclaim")
        self.assertIn("syn-link-nearby-polymorphism", result["overclaim_ids"])

    def test_observed_ortholog_cannot_count_as_exact_function(self) -> None:
        evidence = _json_loads(
            (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        evidence["links"].append(
            {
                "link_id": "syn-link-ortholog",
                "hypothesis_role": "stability",
                "statement": "An ortholog allele matches the missense class.",
                "status": "observed",
                "supports": "ortholog allele proves the exact synthetic allele",
                "does_not_support": "nothing",
            }
        )
        result = assess_evidence_links(evidence)
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "observed_overclaim")
        self.assertIn("syn-link-ortholog", result["overclaim_ids"])

    def test_observed_paralog_model_or_structure_cannot_count_as_exact(self) -> None:
        for phrase, link_id in (
            ("paralog allele proves the exact synthetic allele", "syn-link-paralog"),
            ("mouse allele proves the exact synthetic allele", "syn-link-mouse"),
            ("yeast allele proves the exact synthetic allele", "syn-link-yeast"),
            ("rat allele proves the exact synthetic allele", "syn-link-rat"),
            ("drosophila allele proves the exact synthetic allele", "syn-link-drosophila"),
            ("fly allele proves the exact synthetic allele", "syn-link-fly"),
            ("zebrafish allele proves the exact synthetic allele", "syn-link-zebrafish"),
            ("xenopus allele proves the exact synthetic allele", "syn-link-xenopus"),
            ("c. elegans allele proves the exact synthetic allele", "syn-link-c-elegans"),
            ("c elegans allele proves the exact synthetic allele", "syn-link-c-elegans-space"),
            ("c-elegans allele proves the exact synthetic allele", "syn-link-c-elegans-hyphen"),
            ("celegans allele proves the exact synthetic allele", "syn-link-celegans"),
            ("worm allele proves the exact synthetic allele", "syn-link-worm"),
            ("alphafold proves the exact synthetic allele", "syn-link-alphafold"),
            ("alpha-fold proves the exact synthetic allele", "syn-link-alpha-fold"),
            ("alpha fold proves the exact synthetic allele", "syn-link-alpha-fold-space"),
            ("foldx proves mutant function", "syn-link-foldx"),
            ("geometry proves the exact synthetic allele", "syn-link-geometry"),
            ("coordinate proves the exact synthetic allele", "syn-link-coordinate"),
            ("alphamissense proves the exact synthetic allele", "syn-link-alphamissense"),
            ("alpha-missense proves the exact synthetic allele", "syn-link-alpha-missense"),
            ("alpha missense proves the exact synthetic allele", "syn-link-alpha-missense-space"),
            ("docking proves the exact synthetic allele", "syn-link-docking"),
            ("complementation proves mutant function", "syn-link-complementation"),
            ("in silico proves the exact synthetic allele", "syn-link-insilico"),
            ("insilico proves the exact synthetic allele", "syn-link-insilico-concat"),
            ("pathogenicity score proves the exact synthetic allele", "syn-link-pathogenicity"),
            ("esm proves the exact synthetic allele", "syn-link-esm"),
            ("esm1b proves the exact synthetic allele", "syn-link-esm1b"),
            ("revel proves the exact synthetic allele", "syn-link-revel"),
            ("mave proves the exact synthetic allele", "syn-link-mave"),
            ("frequency proves the exact synthetic allele", "syn-link-frequency"),
            ("conservation proves the exact synthetic allele", "syn-link-conservation"),
            ("clinvar proves the exact synthetic allele", "syn-link-clinvar"),
            ("label proves the exact synthetic allele", "syn-link-label"),
            ("catalog proves the exact synthetic allele", "syn-link-catalog"),
            ("software proves the exact synthetic allele", "syn-link-software"),
            ("database proves the exact synthetic allele", "syn-link-database"),
            ("ontology proves the exact synthetic allele", "syn-link-ontology"),
            ("literature proves the exact synthetic allele", "syn-link-literature"),
            ("cell-free proves the exact synthetic allele", "syn-link-cell-free"),
            ("cell free proves the exact synthetic allele", "syn-link-cell-free-space"),
            ("cellfree proves the exact synthetic allele", "syn-link-cellfree"),
            ("thermal shift proves the exact synthetic allele", "syn-link-thermal-shift"),
            ("thermal-shift proves the exact synthetic allele", "syn-link-thermal-shift-hyphen"),
            ("purified-protein proves the exact synthetic allele", "syn-link-purified-protein"),
            ("purified protein proves the exact synthetic allele", "syn-link-purified-protein-space"),
            ("ectopic proves the exact synthetic allele", "syn-link-ectopic"),
            ("unmatched proves the exact synthetic allele", "syn-link-unmatched"),
            ("unmatched-line proves the exact synthetic allele", "syn-link-unmatched-line"),
            ("unmatched line proves the exact synthetic allele", "syn-link-unmatched-line-space"),
            ("unmatched genotype proves the exact synthetic allele", "syn-link-unmatched-genotype"),
            ("unmatched genotype line proves the exact synthetic allele", "syn-link-unmatched-genotype-line"),
            ("unmatched-genotype proves the exact synthetic allele", "syn-link-unmatched-genotype-hyphen"),
            ("imposed-stress proves the exact synthetic allele", "syn-link-imposed-stress"),
            ("imposed stress proves the exact synthetic allele", "syn-link-imposed-stress-space"),
            ("imposed extrinsic stress proves the exact synthetic allele", "syn-link-imposed-extrinsic"),
            ("imposed-extrinsic-stress proves the exact synthetic allele", "syn-link-imposed-extrinsic-hyphen"),
            ("rna-seq proves the exact synthetic allele", "syn-link-rna-seq"),
            ("rna seq proves the exact synthetic allele", "syn-link-rna-seq-space"),
            ("rnaseq proves the exact synthetic allele", "syn-link-rnaseq"),
            ("rna-seq phase proves the exact synthetic allele", "syn-link-rna-seq-phase"),
            ("rna seq phase proves the exact synthetic allele", "syn-link-rna-seq-phase-space"),
            ("computational haplotype proves the exact synthetic allele", "syn-link-computational-haplotype"),
            ("ranking proves the exact synthetic allele", "syn-link-ranking"),
            ("predictor proves the exact synthetic allele", "syn-link-predictor"),
            ("unlabeled proves the exact synthetic allele", "syn-link-unlabeled"),
            ("transgene proves the exact synthetic allele", "syn-link-transgene"),
            ("overexpression proves the exact synthetic allele", "syn-link-overexpression"),
            ("over-expression proves the exact synthetic allele", "syn-link-over-expression"),
            ("over expression proves the exact synthetic allele", "syn-link-over-expression-space"),
            ("computational proves the exact synthetic allele", "syn-link-computational"),
            ("in-silico proves the exact synthetic allele", "syn-link-insilico-hyphen"),
            ("cdna proves the exact synthetic allele", "syn-link-cdna"),
            ("transient proves the exact synthetic allele", "syn-link-transient"),
            ("transient transfection proves the exact synthetic allele", "syn-link-transient-transfection"),
            ("biophysical proves the exact synthetic allele", "syn-link-biophysical"),
            ("protein-surrogate proves the exact synthetic allele", "syn-link-protein-surrogate"),
            ("protein surrogate proves the exact synthetic allele", "syn-link-protein-surrogate-space"),
        ):
            with self.subTest(phrase=phrase):
                evidence = _json_loads(
                    (COMMUNITY / "observed_inferred_unknown.synthetic.json").read_text(
                        encoding="utf-8"
                    )
                )
                evidence["links"].append(
                    {
                        "link_id": link_id,
                        "hypothesis_role": "stability",
                        "statement": "A non-exact allele or predicted structure matches the missense class.",
                        "status": "observed",
                        "supports": phrase,
                        "does_not_support": "nothing",
                    }
                )
                result = assess_evidence_links(evidence)
                self.assertEqual(result["status"], "stop")
                self.assertEqual(result["reason"], "observed_overclaim")
                self.assertIn(link_id, result["overclaim_ids"])

    def test_pretty_lineage_cannot_advance_without_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            write_passing_confirmation(dest)
            write_passing_transcript(dest)
            _write_aligned_counts(dest)
            _tick_replication(dest)
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["blocked_by"], "replication")
        self.assertEqual(result["block_reason"], "checkpoint_not_ready")
        self.assertEqual(result["n_skipped"], 0)

    def test_checkpoint_ready_still_holds_when_child_claim_is_weak(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            write_passing_confirmation(dest)
            write_passing_transcript(dest)
            _write_aligned_counts(dest)
            _tick_replication(dest)
            _set_missense_checkpoint(dest, "positive")
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["blocked_by"], "replication")
        self.assertEqual(result["block_reason"], "child_claim_too_weak")

    def test_function_identity_and_child_claim_can_advance_a_copy(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            write_passing_confirmation(dest)
            write_passing_transcript(dest)
            _write_aligned_counts(dest)
            _tick_replication(dest)
            _set_missense_checkpoint(dest, "positive")
            path = dest / "observed_inferred_unknown.synthetic.json"
            evidence = _json_loads(path.read_text(encoding="utf-8"))
            _write_json(path, mark_pair_program_observed(evidence))
            declare_next_gate(dest, "syn-gate-replication")
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "advance")
        self.assertIsNone(result["blocked_by"])
        self.assertEqual(result["n_skipped"], 0)

    def test_declared_confirmation_without_floors_stops(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "confirmation_record.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            payload["declared_status"] = "both_alleles_observed"
            _write_json(path, payload)
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["blocked_by"], "confirmation")
        self.assertEqual(result["block_reason"], "declared_overstrong")

    def test_probe_before_identity_stops_even_when_confirmation_holds(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "causal_chain_worksheet.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            payload["declared_next_gate_id"] = "syn-gate-replication"
            _write_json(path, payload)
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["blocked_by"], "next_experiment")
        self.assertEqual(result["block_reason"], "probe_before_identity")

    def test_predicted_stability_cannot_count_as_function(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "structure_ranking.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            payload["used_as_function"] = True
            _write_json(path, payload)
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "stop")
        self.assertEqual(result["blocked_by"], "structure_ranking")
        self.assertEqual(result["block_reason"], "ranking_is_not_an_assay")
        skipped = {item["name"] for item in result["steps"] if item["skipped"]}
        self.assertIn("confirmation", skipped)
        self.assertIn("hypothesis", skipped)

    def test_foldx_ranking_cannot_open_confirmation(self) -> None:
        for method in ("foldx_alphafold", "alphamissense"):
            with self.subTest(method=method):
                with tempfile.TemporaryDirectory() as folder:
                    dest = _copy_toolkit(Path(folder))
                    path = dest / "structure_ranking.synthetic.json"
                    payload = _json_loads(path.read_text(encoding="utf-8"))
                    payload["method"] = method
                    _write_json(path, payload)
                    result = run_community_pipeline(dest)
                self.assertEqual(result["decision"], "hold")
                self.assertEqual(result["blocked_by"], "structure_ranking")
                self.assertEqual(result["block_reason"], "method_cannot_replace_assay")
                skipped = {item["name"] for item in result["steps"] if item["skipped"]}
                self.assertIn("confirmation", skipped)

    def test_ranking_analog_claimed_as_exact_stops_pipeline(self) -> None:
        for role in ("analog_unstable", "nearby_benign"):
            with self.subTest(role=role):
                with tempfile.TemporaryDirectory() as folder:
                    dest = _copy_toolkit(Path(folder))
                    path = dest / "structure_ranking.synthetic.json"
                    payload = _json_loads(path.read_text(encoding="utf-8"))
                    for row in payload["residues"]:
                        if row["role"] == role:
                            row["claimed_as_exact"] = True
                    _write_json(path, payload)
                    result = run_community_pipeline(dest)
                self.assertEqual(result["decision"], "stop")
                self.assertEqual(result["blocked_by"], "structure_ranking")
                self.assertEqual(result["block_reason"], "analog_as_exact_function")
                skipped = {item["name"] for item in result["steps"] if item["skipped"]}
                self.assertIn("confirmation", skipped)

    def test_ranking_exact_unclaimed_cannot_open_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "structure_ranking.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            for row in payload["residues"]:
                if row["role"] == "exact":
                    row["claimed_as_exact"] = False
            _write_json(path, payload)
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["blocked_by"], "structure_ranking")
        self.assertEqual(result["block_reason"], "exact_claim_required")
        skipped = {item["name"] for item in result["steps"] if item["skipped"]}
        self.assertIn("confirmation", skipped)

    def test_ranking_out_of_range_features_cannot_open_confirmation(self) -> None:
        cases = (
            ("exact", "plddt", 900.0),
            ("exact", "rsa", 1.5),
            ("analog_unstable", "polar_contacts", -1),
            ("exact", "polar_contacts", 3.5),
        )
        for role, field, value in cases:
            with self.subTest(role=role, field=field, value=value):
                with tempfile.TemporaryDirectory() as folder:
                    dest = _copy_toolkit(Path(folder))
                    path = dest / "structure_ranking.synthetic.json"
                    payload = _json_loads(path.read_text(encoding="utf-8"))
                    for row in payload["residues"]:
                        if row["role"] == role:
                            row[field] = value
                    _write_json(path, payload)
                    result = run_community_pipeline(dest)
                self.assertEqual(result["decision"], "hold")
                self.assertEqual(result["blocked_by"], "structure_ranking")
                self.assertEqual(result["block_reason"], "ranking_features_unusable")
                skipped = {item["name"] for item in result["steps"] if item["skipped"]}
                self.assertIn("confirmation", skipped)

    def test_ranking_duplicate_residue_ids_cannot_open_confirmation(self) -> None:
        analog_id = next(
            row["residue_id"]
            for row in _json_loads(
                (COMMUNITY / "structure_ranking.synthetic.json").read_text(encoding="utf-8")
            )["residues"]
            if row["role"] == "analog_unstable"
        )
        for mutated_id in (analog_id, analog_id.upper()):
            with self.subTest(residue_id=mutated_id):
                with tempfile.TemporaryDirectory() as folder:
                    dest = _copy_toolkit(Path(folder))
                    path = dest / "structure_ranking.synthetic.json"
                    payload = _json_loads(path.read_text(encoding="utf-8"))
                    for row in payload["residues"]:
                        if row["role"] == "exact":
                            row["residue_id"] = mutated_id
                    _write_json(path, payload)
                    result = run_community_pipeline(dest)
                self.assertEqual(result["decision"], "hold")
                self.assertEqual(result["blocked_by"], "structure_ranking")
                self.assertEqual(result["block_reason"], "ranking_residue_ids_unusable")
                skipped = {item["name"] for item in result["steps"] if item["skipped"]}
                self.assertIn("confirmation", skipped)

    def test_ranking_extra_residue_cannot_open_confirmation(self) -> None:
        cases = (
            (True, "stop", "analog_as_exact_function"),
            (False, "hold", "ranking_table_unusable"),
        )
        for claimed, decision, reason in cases:
            with self.subTest(claimed_as_exact=claimed):
                with tempfile.TemporaryDirectory() as folder:
                    dest = _copy_toolkit(Path(folder))
                    path = dest / "structure_ranking.synthetic.json"
                    payload = _json_loads(path.read_text(encoding="utf-8"))
                    payload["residues"].append(
                        {
                            "residue_id": "syn-residue-extra",
                            "role": "extra",
                            "plddt": 90.0,
                            "rsa": 0.2,
                            "polar_contacts": 2,
                            "claimed_as_exact": claimed,
                        }
                    )
                    _write_json(path, payload)
                    result = run_community_pipeline(dest)
                self.assertEqual(result["decision"], decision)
                self.assertEqual(result["blocked_by"], "structure_ranking")
                self.assertEqual(result["block_reason"], reason)
                skipped = {item["name"] for item in result["steps"] if item["skipped"]}
                self.assertIn("confirmation", skipped)

    def test_ranking_missing_role_cannot_open_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            path = dest / "structure_ranking.synthetic.json"
            payload = _json_loads(path.read_text(encoding="utf-8"))
            payload["residues"] = [
                row for row in payload["residues"] if row["role"] != "nearby_benign"
            ]
            _write_json(path, payload)
            result = run_community_pipeline(dest)
        self.assertEqual(result["decision"], "hold")
        self.assertEqual(result["blocked_by"], "structure_ranking")
        self.assertEqual(result["block_reason"], "ranking_table_unusable")
        skipped = {item["name"] for item in result["steps"] if item["skipped"]}
        self.assertIn("confirmation", skipped)

    def test_ranking_malformed_table_cannot_open_confirmation(self) -> None:
        cases = (
            {"method": "not-a-method"},
            {"residues": []},
        )
        for mutation in cases:
            with self.subTest(mutation=str(mutation)):
                with tempfile.TemporaryDirectory() as folder:
                    dest = _copy_toolkit(Path(folder))
                    path = dest / "structure_ranking.synthetic.json"
                    payload = _json_loads(path.read_text(encoding="utf-8"))
                    payload.update(mutation)
                    _write_json(path, payload)
                    result = run_community_pipeline(dest)
                self.assertEqual(result["decision"], "hold")
                self.assertEqual(result["blocked_by"], "structure_ranking")
                self.assertEqual(result["block_reason"], "ranking_table_unusable")
                skipped = {item["name"] for item in result["steps"] if item["skipped"]}
                self.assertIn("confirmation", skipped)


class CommunityGateCliExitTests(unittest.TestCase):
    def test_hold_decision_returns_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dest = _copy_toolkit(Path(folder))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_community_gates.py"),
                    "--community",
                    str(dest),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("decision=", completed.stdout)

    def test_program_gate_hold_returns_nonzero_exit(self) -> None:
        replication = COMMUNITY / "replication_decision.synthetic.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "assess_program_gates.py"),
                "--replication",
                str(replication),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)

    def test_stewardship_no_eligible_ids_returns_nonzero_exit(self) -> None:
        plan_path = ROOT / "templates" / "track2_sample_stewardship.synthetic.json"
        plan = _json_loads(plan_path.read_text(encoding="utf-8"))
        for assay in plan["assays"]:
            assay["prerequisites"] = ["syn-never-completed"]
        with tempfile.TemporaryDirectory() as folder:
            blocked_plan = Path(folder) / "plan.json"
            blocked_plan.write_text(
                json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "assess_sample_stewardship.py"),
                    "--plan",
                    str(blocked_plan),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(completed.returncode, 0)


class CommunityEffectConsistencyTests(unittest.TestCase):
    def test_forged_status_effect_divergence_stops(self) -> None:
        from mva_hackathon.community_pipeline import _effect

        self.assertEqual(
            _effect({"status": "stop", "program_effect": "pass"}), "stop"
        )
        self.assertEqual(
            _effect({"status": "pass", "program_effect": "stop"}), "stop"
        )
        self.assertEqual(
            _effect({"status": "pass", "program_effect": "pass"}), "pass"
        )
        self.assertEqual(
            _effect({"status": "not_assessable", "program_effect": "hold"}),
            "hold",
        )
        self.assertEqual(
            _effect({"status": "not_assessable", "program_effect": "pass"}),
            "stop",
        )
        self.assertEqual(
            _effect({"status": "advance", "program_effect": "pass"}), "stop"
        )
        self.assertEqual(
            _effect({"status": "pass", "program_effect": "advance"}), "pass"
        )
        self.assertEqual(
            _effect({"status": "stop", "program_effect": "advance"}), "stop"
        )
        self.assertEqual(_effect({"status": "pass"}), "hold")
        self.assertEqual(_effect({"status": "stop"}), "stop")
        self.assertEqual(_effect({}), "hold")


if __name__ == "__main__":
    unittest.main()
