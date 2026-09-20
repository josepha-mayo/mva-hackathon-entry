from __future__ import annotations

import dataclasses
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mva_hackathon.lineage import (
    ADVERSARIAL_CASES,
    CLAIM_BOUNDARY,
    FORBIDDEN_ANALYST_KEYS,
    SCHEMA,
    CompletionBand,
    LineageError,
    _three_events,
    analyze_lineage_study,
    balanced_event_counts,
    build_adversarial_fixture,
    evaluate_fixture,
    export_first_attempt_aggregates,
    lineage_source_fingerprint,
    lineage_study_from_counts,
    map_lineage_counts_to_observed_runs,
    parse_lineage_study,
    run_adversarial_suite,
    simulate_noisy_clean_generation,
)
from mva_hackathon.exposure_gate import assess_exposure_execution_binding
from mva_hackathon.save_path import passing_exposure, passing_power


class LineageContractTests(unittest.TestCase):
    def test_export_has_no_truth_and_separates_pre_division_death(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        exported = export_first_attempt_aggregates(study)
        self.assertEqual(exported["schema"], "mva-track2-lineage-counts/v1")
        self.assertEqual(exported["lock_state"], "locked")
        self.assertTrue(exported["blinded"])
        self.assertGreater(sum(row["pre_division_death"] for row in exported["runs"]), 0)
        self.assertEqual(
            sum(row["opportunities"] for row in exported["runs"]),
            len(study.founders),
        )
        walked: list[str] = []

        def collect(node: object) -> None:
            if isinstance(node, dict):
                walked.extend(node)
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)

        collect(exported)
        self.assertTrue(FORBIDDEN_ANALYST_KEYS.isdisjoint(walked))

    def test_export_preserves_founder_derived_exposure_context(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        exported = export_first_attempt_aggregates(study)
        self.assertEqual(exported["study_id"], study.study_id)
        for row in exported["runs"]:
            self.assertTrue(row["batch_id"].startswith("syn-"))
            self.assertTrue(row["functional_execution_id"].startswith("syn-"))
            self.assertTrue(row["exposure_support_record_id"].startswith("syn-"))
            self.assertTrue(row["exposure_profile_id"].startswith("profile-"))
            self.assertTrue(row["exposure_probe_id"].startswith("syn-"))
            self.assertTrue(row["exposure_started_at"].endswith("Z"))
            self.assertIsNotNone(row["endpoint_recorded_at"])

    def test_realized_allocation_round_trips_through_parser_and_exporter(self) -> None:
        vehicle = balanced_event_counts(
            completed_error=8,
            completed_no_error=28,
            no_division=0,
            death_before_completion=0,
        )
        treatment = balanced_event_counts(
            completed_error=4,
            completed_no_error=32,
            no_division=0,
            death_before_completion=0,
        )
        study = lineage_study_from_counts(
            study_id="syn-save-path-lineage",
            per_event={
                f"syn-event-{index}": {
                    "vehicle": dict(vehicle),
                    "treatment": dict(treatment),
                }
                for index in (1, 2, 3)
            },
            attempt_hours_by_arm={"vehicle": 24.0, "treatment": 24.0},
        )
        # This allocation contract needs six biological pairs per exact
        # context. Spread the otherwise identical synthetic founders over six
        # clones while retaining their founder identities and outcomes.
        study = dataclasses.replace(
            study,
            founders=tuple(
                dataclasses.replace(
                    founder,
                    run_id=(
                        f"syn-run-{founder.edit_event_id.rsplit('-', 1)[-1]}"
                    ),
                    batch_id="syn-batch-a",
                    clone_id=(
                        f"syn-clone-{founder.edit_event_id.rsplit('-', 1)[-1]}-"
                        f"{(int(founder.founder_id.rsplit('-', 1)[-1]) - 1) % 6 + 1}"
                    ),
                    functional_execution_id=(
                        f"syn-functional-"
                        f"{founder.edit_event_id.rsplit('-', 1)[-1]}-"
                        f"{(int(founder.founder_id.rsplit('-', 1)[-1]) - 1) % 6 + 1}-"
                        f"{'member-a' if founder.arm == 'vehicle' else 'member-b'}"
                    ),
                )
                for founder in study.founders
            ),
        )
        legacy_export = export_first_attempt_aggregates(study)
        exposure_input = json.loads(json.dumps(legacy_export, allow_nan=False))
        plan = passing_power()
        exposure = passing_exposure(exposure_input, plan)
        allocation = exposure["preexposure_allocation"]
        assignment_index = {
            row["functional_execution_id"]: row for row in allocation["assignments"]
        }
        assignment_by_context_arm = {
            (
                row["edit_event_id"],
                row["clone_id"],
                row["functional_assay_run_id"],
                row["arm"],
            ): row
            for row in allocation["assignments"]
        }
        founders = tuple(
            dataclasses.replace(
                founder,
                functional_execution_id=assignment_by_context_arm[
                    (
                        founder.edit_event_id,
                        founder.clone_id,
                        founder.run_id,
                        founder.arm,
                    )
                ]["functional_execution_id"],
                allocation_block_id=assignment_by_context_arm[
                    (
                        founder.edit_event_id,
                        founder.clone_id,
                        founder.run_id,
                        founder.arm,
                    )
                ]["allocation_block_id"],
                functional_assay_plate_id=assignment_by_context_arm[
                    (
                        founder.edit_event_id,
                        founder.clone_id,
                        founder.run_id,
                        founder.arm,
                    )
                ]["functional_assay_plate_id"],
                plate_row=assignment_by_context_arm[
                    (
                        founder.edit_event_id,
                        founder.clone_id,
                        founder.run_id,
                        founder.arm,
                    )
                ]["plate_row"],
                plate_column=assignment_by_context_arm[
                    (
                        founder.edit_event_id,
                        founder.clone_id,
                        founder.run_id,
                        founder.arm,
                    )
                ]["plate_column"],
                dosing_order=assignment_by_context_arm[
                    (
                        founder.edit_event_id,
                        founder.clone_id,
                        founder.run_id,
                        founder.arm,
                    )
                ]["dosing_order"],
                acquisition_order=assignment_by_context_arm[
                    (
                        founder.edit_event_id,
                        founder.clone_id,
                        founder.run_id,
                        founder.arm,
                    )
                ]["acquisition_order"],
            )
            for founder in study.founders
        )
        allocated_study = dataclasses.replace(
            study,
            founders=founders,
            allocation_id=allocation["allocation_id"],
        )
        allocated_payload = json.loads(json.dumps(dataclasses.asdict(allocated_study), allow_nan=False))
        for field in ("allocation_block_id", "functional_assay_plate_id"):
            with self.subTest(invalid_identifier=field):
                invalid_payload = json.loads(json.dumps(allocated_payload, allow_nan=False))
                invalid_payload["founders"][0][field] = "Syn-invalid-allocation"
                with self.assertRaisesRegex(LineageError, "lowercase opaque"):
                    parse_lineage_study(invalid_payload)
        parsed = parse_lineage_study(allocated_payload)
        exported = export_first_attempt_aggregates(parsed)

        self.assertEqual(exported["allocation_id"], allocation["allocation_id"])
        for row in exported["runs"]:
            assignment = assignment_index[row["functional_execution_id"]]
            for field in (
                "allocation_block_id",
                "functional_assay_plate_id",
                "plate_row",
                "plate_column",
                "dosing_order",
                "acquisition_order",
            ):
                self.assertEqual(row[field], assignment[field])
        binding = assess_exposure_execution_binding(exposure, exported, plan)
        self.assertEqual(binding["status"], "pass", binding)
        self.assertEqual(binding["reason"], "exposure_execution_linked")

        schema = json.loads(
            (ROOT / "schemas" / "track2_lineage_counts.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        self.assertFalse(list(validator.iter_errors(legacy_export)))
        self.assertFalse(list(validator.iter_errors(exported)))
        partial = json.loads(json.dumps(exported, allow_nan=False))
        partial["runs"][0].pop("plate_row")
        self.assertTrue(list(validator.iter_errors(partial)))
        newline_id = json.loads(json.dumps(exported, allow_nan=False))
        newline_id["allocation_id"] += "\n"
        self.assertTrue(list(validator.iter_errors(newline_id)))

        expected_fingerprint = lineage_source_fingerprint(exported)
        reordered = json.loads(json.dumps(exported, allow_nan=False))
        reordered["runs"].reverse()
        self.assertEqual(
            expected_fingerprint, lineage_source_fingerprint(reordered)
        )
        for field in ("allocation_block_id", "functional_assay_plate_id"):
            invalid_fingerprint = json.loads(json.dumps(exported, allow_nan=False))
            invalid_fingerprint["runs"][0][field] = "Syn-invalid-allocation"
            with self.assertRaisesRegex(LineageError, "lowercase opaque"):
                lineage_source_fingerprint(invalid_fingerprint)
        changed_root = json.loads(json.dumps(exported, allow_nan=False))
        changed_root["allocation_id"] = "allocation-" + "b" * 64
        self.assertNotEqual(
            expected_fingerprint, lineage_source_fingerprint(changed_root)
        )
        for field in (
            "allocation_block_id",
            "functional_assay_plate_id",
            "plate_row",
            "plate_column",
            "dosing_order",
            "acquisition_order",
        ):
            changed = json.loads(json.dumps(exported, allow_nan=False))
            if isinstance(changed["runs"][0][field], int):
                changed["runs"][0][field] += 1
            else:
                changed["runs"][0][field] = f"syn-mutated-{field}"
            self.assertNotEqual(
                expected_fingerprint,
                lineage_source_fingerprint(changed),
                field,
            )

    def test_allocation_root_and_realized_tuple_are_all_or_none(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        payload = json.loads(json.dumps(dataclasses.asdict(study), allow_nan=False))
        payload.pop("allocation_id")
        payload["allocation_id"] = "allocation-" + "a" * 64
        with self.assertRaisesRegex(LineageError, "supplied together"):
            parse_lineage_study(payload)

        payload = json.loads(json.dumps(dataclasses.asdict(study), allow_nan=False))
        payload.pop("allocation_id")
        founder = payload["founders"][0]
        for field in (
            "allocation_block_id",
            "functional_assay_plate_id",
            "plate_row",
            "plate_column",
            "dosing_order",
            "acquisition_order",
        ):
            founder.pop(field)
        founder["allocation_block_id"] = "syn-block-partial"
        with self.assertRaisesRegex(LineageError, "missing or surplus"):
            parse_lineage_study(payload)

    def test_allocation_identifier_and_fingerprint_shapes_fail_closed(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        legacy_payload = json.loads(json.dumps(dataclasses.asdict(study), allow_nan=False))
        legacy_payload.pop("allocation_id")
        for founder in legacy_payload["founders"]:
            for field in (
                "allocation_block_id",
                "functional_assay_plate_id",
                "plate_row",
                "plate_column",
                "dosing_order",
                "acquisition_order",
            ):
                founder.pop(field)
        self.assertIsNone(parse_lineage_study(legacy_payload).allocation_id)

        payload = json.loads(json.dumps(dataclasses.asdict(study), allow_nan=False))
        payload["allocation_id"] = "allocation-declared"
        with self.assertRaisesRegex(LineageError, "lowercase SHA-256"):
            parse_lineage_study(payload)

        explicit_null_payload = json.loads(json.dumps(dataclasses.asdict(study), allow_nan=False))
        explicit_null_payload["allocation_id"] = None
        with self.assertRaisesRegex(LineageError, "allocation_id"):
            parse_lineage_study(explicit_null_payload)

        export = export_first_attempt_aggregates(study)
        explicit_null = dict(export)
        explicit_null["allocation_id"] = None
        with self.assertRaisesRegex(LineageError, "allocation_id"):
            lineage_source_fingerprint(explicit_null)

        partial = json.loads(json.dumps(export, allow_nan=False))
        partial["runs"][0]["plate_row"] = 1
        with self.assertRaisesRegex(LineageError, "root allocation_id"):
            lineage_source_fingerprint(partial)

    def test_export_rejects_aggregate_that_merges_exposure_contexts(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        first = study.founders[0]
        same_group = next(
            row
            for row in study.founders[1:]
            if (
                row.arm,
                row.edit_event_id,
                row.clone_id,
                row.run_id,
            )
            == (
                first.arm,
                first.edit_event_id,
                first.clone_id,
                first.run_id,
            )
        )
        founders = tuple(
            row.__class__(
                **{
                    **row.__dict__,
                    "functional_execution_id": "syn-functional-unrelated",
                }
            )
            if row.founder_id == same_group.founder_id
            else row
            for row in study.founders
        )
        broken = study.__class__(
            schema=study.schema,
            study_id=study.study_id,
            blinded=study.blinded,
            lock_state=study.lock_state,
            unblinded_at=study.unblinded_at,
            adjudication_locked_at=study.adjudication_locked_at,
            completion_band=study.completion_band,
            founders=founders,
            daughters=study.daughters,
        )
        with self.assertRaisesRegex(LineageError, "multiple exposure contexts"):
            export_first_attempt_aggregates(broken)

    def test_analyzer_signature_is_truth_blind(self) -> None:
        parameters = inspect.signature(analyze_lineage_study).parameters
        self.assertEqual(list(parameters), ["study"])
        self.assertTrue(FORBIDDEN_ANALYST_KEYS)

    def test_surplus_truth_keys_fail_closed(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        payload = {
            "schema": study.schema,
            "study_id": study.study_id,
            "blinded": study.blinded,
            "lock_state": study.lock_state,
            "unblinded_at": study.unblinded_at,
            "adjudication_locked_at": study.adjudication_locked_at,
            "completion_band": {
                "relative_lower": study.completion_band.relative_lower,
                "relative_upper": study.completion_band.relative_upper,
                "absolute_drop_max": study.completion_band.absolute_drop_max,
            },
            "founders": [],
            "daughters": [],
            "generator_truth": {"hidden": True},
        }
        with self.assertRaisesRegex(LineageError, "forbidden truth"):
            parse_lineage_study(payload)

    def test_loose_software_completion_band_is_rejected(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        payload = {
            "schema": study.schema,
            "study_id": study.study_id,
            "blinded": study.blinded,
            "lock_state": study.lock_state,
            "unblinded_at": study.unblinded_at,
            "adjudication_locked_at": study.adjudication_locked_at,
            "completion_band": {
                "relative_lower": 0.80,
                "relative_upper": 1.25,
                "absolute_drop_max": 0.20,
            },
            "founders": [
                {
                    "founder_id": row.founder_id,
                    "arm": row.arm,
                    "edit_event_id": row.edit_event_id,
                    "clone_id": row.clone_id,
                    "run_id": row.run_id,
                    "field_id": row.field_id,
                    "batch_id": row.batch_id,
                    "functional_execution_id": row.functional_execution_id,
                    "exposure_support_record_id": row.exposure_support_record_id,
                    "exposure_profile_id": row.exposure_profile_id,
                    "exposure_probe_id": row.exposure_probe_id,
                    "enrolled_at": row.enrolled_at,
                    "exposure_started_at": row.exposure_started_at,
                    "first_attempt_started_at": row.first_attempt_started_at,
                    "first_attempt_ended_at": row.first_attempt_ended_at,
                    "first_attempt_outcome": row.first_attempt_outcome,
                    "censor_reason": row.censor_reason,
                }
                for row in study.founders
            ],
            "daughters": [
                {
                    "daughter_id": row.daughter_id,
                    "founder_id": row.founder_id,
                    "observed_at": row.observed_at,
                    "outcome": row.outcome,
                }
                for row in study.daughters
            ],
        }
        with self.assertRaisesRegex(LineageError, "relative_lower"):
            parse_lineage_study(payload)

    def test_band_laxer_than_default_is_rejected(self) -> None:
        # A band inside the schema bounds but looser than the protocol
        # default (0.95/1.10/0.05) would relax the pediatric test.
        with self.assertRaisesRegex(LineageError, "laxer than the protocol"):
            CompletionBand(
                relative_lower=0.90,
                relative_upper=1.10,
                absolute_drop_max=0.05,
            )
        with self.assertRaisesRegex(LineageError, "laxer than the protocol"):
            CompletionBand(
                relative_lower=0.95,
                relative_upper=1.15,
                absolute_drop_max=0.05,
            )
        with self.assertRaisesRegex(LineageError, "laxer than the protocol"):
            CompletionBand(
                relative_lower=0.95,
                relative_upper=1.10,
                absolute_drop_max=0.10,
            )
        # Narrower-than-default is allowed.
        CompletionBand(
            relative_lower=0.97, relative_upper=1.05, absolute_drop_max=0.02
        )

    def test_source_fingerprint_is_order_invariant_and_complete(self) -> None:
        exported = export_first_attempt_aggregates(
            build_adversarial_fixture("clean_generation")
        )
        expected = lineage_source_fingerprint(exported)
        reordered = json.loads(json.dumps(exported, allow_nan=False))
        reordered["runs"].reverse()
        self.assertEqual(expected, lineage_source_fingerprint(reordered))
        mutations = (
            ("root", "study_id"),
            ("row", "event_positive_daughters_died"),
            ("row", "event_negative_daughters_reproduced"),
            ("row", "exposure_support_record_id"),
        )
        for scope, field in mutations:
            with self.subTest(field=field):
                changed = json.loads(json.dumps(exported, allow_nan=False))
                if scope == "root":
                    changed[field] = "syn-different-study"
                elif isinstance(changed["runs"][0][field], int):
                    changed["runs"][0][field] += 1
                else:
                    changed["runs"][0][field] = "syn-different-context"
                self.assertNotEqual(expected, lineage_source_fingerprint(changed))

    def test_clone_cannot_span_edit_events(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        founders = list(study.founders)
        first = founders[0]
        second = next(
            row
            for row in founders
            if row.edit_event_id != first.edit_event_id and row.arm == first.arm
        )
        broken = []
        for row in founders:
            clone_id = first.clone_id if row.founder_id == second.founder_id else row.clone_id
            broken.append(
                row.__class__(
                    **{**row.__dict__, "clone_id": clone_id}
                )
            )
        with self.assertRaisesRegex(LineageError, "nest inside one edit event"):
            study.__class__(
                schema=study.schema,
                study_id=study.study_id,
                blinded=study.blinded,
                lock_state=study.lock_state,
                unblinded_at=study.unblinded_at,
                adjudication_locked_at=study.adjudication_locked_at,
                completion_band=study.completion_band,
                founders=tuple(broken),
                daughters=study.daughters,
            )

    def test_pre_division_death_cannot_have_daughters(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        parent = next(
            row
            for row in study.founders
            if row.first_attempt_outcome == "death_before_completion"
        )
        with self.assertRaisesRegex(LineageError, "only allowed after a completed division"):
            study.__class__(
                schema=study.schema,
                study_id=study.study_id,
                blinded=study.blinded,
                lock_state=study.lock_state,
                unblinded_at=study.unblinded_at,
                adjudication_locked_at=study.adjudication_locked_at,
                completion_band=study.completion_band,
                founders=study.founders,
                daughters=study.daughters
                + (
                    study.daughters[0].__class__(
                        daughter_id="syn-illegal-child",
                        founder_id=parent.founder_id,
                        observed_at=study.daughters[0].observed_at,
                        outcome="reproduced",
                    ),
                ),
            )

    def _multipolar_study(self, recorded_daughters: int = 3):
        study = build_adversarial_fixture("clean_generation")
        parent = next(
            row
            for row in study.founders
            if row.first_attempt_outcome == "completed_error"
        )
        multipolar = dataclasses.replace(parent, division_class="multipolar")
        founders = tuple(
            multipolar if row.founder_id == parent.founder_id else row
            for row in study.founders
        )
        daughters = list(study.daughters)
        observed_at = next(
            child.observed_at
            for child in daughters
            if child.founder_id == parent.founder_id
        )
        for index in range(3, recorded_daughters + 1):
            daughters.append(
                study.daughters[0].__class__(
                    daughter_id=f"{parent.founder_id}-d{index}",
                    founder_id=parent.founder_id,
                    observed_at=observed_at,
                    outcome="reproduced",
                )
            )
        return dataclasses.replace(
            study, founders=founders, daughters=tuple(daughters)
        ), parent

    def test_multipolar_division_exports_declared_daughter_slots(self) -> None:
        study, parent = self._multipolar_study()
        exported = export_first_attempt_aggregates(study)
        row = next(
            item
            for item in exported["runs"]
            if item["arm"] == parent.arm
            and item["clone_id"] == parent.clone_id
        )
        self.assertEqual(
            row["event_positive_daughter_slots"],
            2 * row["event_positive_divisions"] + 1,
        )
        schema = json.loads(
            (ROOT / "schemas" / "track2_lineage_counts.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(
            list(Draft202012Validator(schema).iter_errors(exported))
        )

    def test_multipolar_claim_with_two_daughters_fails_closed(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        parent = next(
            row
            for row in study.founders
            if row.first_attempt_outcome == "completed_error"
        )
        multipolar = dataclasses.replace(parent, division_class="multipolar")
        founders = tuple(
            multipolar if row.founder_id == parent.founder_id else row
            for row in study.founders
        )
        with self.assertRaisesRegex(LineageError, "multipolar"):
            dataclasses.replace(study, founders=founders)

    def test_multipolar_on_non_error_outcome_fails_closed(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        parent = next(
            row
            for row in study.founders
            if row.first_attempt_outcome == "completed_no_error"
        )
        with self.assertRaisesRegex(LineageError, "segregation errors"):
            dataclasses.replace(parent, division_class="multipolar")

    def test_bipolar_division_with_three_daughters_fails_closed(self) -> None:
        study = build_adversarial_fixture("clean_generation")
        parent = next(
            row
            for row in study.founders
            if row.first_attempt_outcome == "completed_error"
        )
        observed_at = next(
            child.observed_at
            for child in study.daughters
            if child.founder_id == parent.founder_id
        )
        extra = study.daughters[0].__class__(
            daughter_id=f"{parent.founder_id}-d3",
            founder_id=parent.founder_id,
            observed_at=observed_at,
            outcome="reproduced",
        )
        with self.assertRaisesRegex(LineageError, "more than two"):
            dataclasses.replace(
                study, daughters=study.daughters + (extra,)
            )

    def test_declared_slots_shift_source_fingerprint(self) -> None:
        study, parent = self._multipolar_study()
        exported = export_first_attempt_aggregates(study)
        tampered = json.loads(json.dumps(exported, allow_nan=False))
        row = next(
            item
            for item in tampered["runs"]
            if item["arm"] == parent.arm
            and item["clone_id"] == parent.clone_id
        )
        row["event_positive_daughter_slots"] = (
            2 * row["event_positive_divisions"]
        )
        self.assertNotEqual(
            lineage_source_fingerprint(exported),
            lineage_source_fingerprint(tampered),
        )


class LineageLoadingTests(unittest.TestCase):
    def test_duplicate_json_keys_fail_closed(self) -> None:
        from mva_hackathon.lineage import load_lineage_study

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.json"
            path.write_text(
                '{"lock_state": "unlocked", "lock_state": "locked"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(LineageError, "duplicate key"):
                load_lineage_study(path)

    def test_nonfinite_json_number_fails_closed(self) -> None:
        from mva_hackathon.lineage import load_lineage_study

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.json"
            path.write_text('{"ratio": 1e400}', encoding="utf-8")
            with self.assertRaisesRegex(LineageError, "non-finite"):
                load_lineage_study(path)


class LineageAnalysisTests(unittest.TestCase):
    def test_clean_generation_is_concordant_under_pediatric_band(self) -> None:
        analysis = analyze_lineage_study(build_adversarial_fixture("clean_generation"))
        self.assertTrue(analysis["status"]["clean_generation_signal"])
        self.assertTrue(analysis["status"]["pre_division_death_separated"])
        self.assertTrue(analysis["status"]["pediatric_completion_equivalent"])
        self.assertEqual(
            analysis["interpretation"],
            "generation_reduction_without_detected_configured_confound",
        )
        self.assertNotIn("generator_truth", analysis)
        self.assertEqual(analysis["claim_boundary"], CLAIM_BOUNDARY)
        self.assertTrue(analysis["synthetic_only"])

    def test_cytostasis_is_not_rescue(self) -> None:
        analysis = analyze_lineage_study(build_adversarial_fixture("cytostasis"))
        self.assertTrue(analysis["flags"]["cytostasis"])
        self.assertFalse(analysis["status"]["clean_generation_signal"])

    def test_adversarial_suite_passes(self) -> None:
        receipt = run_adversarial_suite()
        self.assertEqual(receipt["schema"], SCHEMA)
        self.assertTrue(receipt["all_passed"], receipt["cases"])
        self.assertGreaterEqual(receipt["n_cases"], len(ADVERSARIAL_CASES))

    def test_each_named_fixture_matches_evaluator_only_expectations(self) -> None:
        for name in (*ADVERSARIAL_CASES, "enroll_after_exposure"):
            with self.subTest(name=name):
                result = evaluate_fixture(name)
                self.assertTrue(result["passed"], result)

    def test_analyzer_output_round_trips_json_without_truth(self) -> None:
        analysis = analyze_lineage_study(build_adversarial_fixture("pruning_only"))
        encoded = json.dumps(analysis, allow_nan=False)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["flags"]["error_daughter_pruning"], True)
        self.assertFalse(any(key in decoded for key in FORBIDDEN_ANALYST_KEYS))

    def test_noisy_replicates_remain_synthetic_only(self) -> None:
        first = analyze_lineage_study(simulate_noisy_clean_generation(7))
        second = analyze_lineage_study(simulate_noisy_clean_generation(7))
        self.assertEqual(first["n_founders"], second["n_founders"])
        self.assertTrue(first["synthetic_only"])
        self.assertEqual(first["claim_boundary"], CLAIM_BOUNDARY)

    def test_competing_risks_cannot_be_mapped_into_aggregate_runs(self) -> None:
        exported = export_first_attempt_aggregates(
            build_adversarial_fixture("clean_generation")
        )
        with self.assertRaisesRegex(LineageError, "competing-risk"):
            map_lineage_counts_to_observed_runs(exported, id_map={})

    def test_completed_only_counts_map_when_ids_are_declared(self) -> None:
        completed = balanced_event_counts(
            completed_error=8,
            completed_no_error=28,
            no_division=0,
            death_before_completion=0,
        )
        study = lineage_study_from_counts(
            study_id="syn-completed-only",
            per_event={
                f"syn-event-{index}": {"vehicle": dict(completed), "treatment": dict(completed)}
                for index in (1, 2, 3)
            },
        )
        exported = export_first_attempt_aggregates(study)
        id_map = {
            "syn-event-1": 1,
            "syn-event-2": 2,
            "syn-event-3": 3,
            "syn-clone-syn-event-1-1": 1,
            "syn-clone-syn-event-1-2": 2,
            "syn-clone-syn-event-2-1": 3,
            "syn-clone-syn-event-2-2": 4,
            "syn-clone-syn-event-3-1": 5,
            "syn-clone-syn-event-3-2": 6,
            "syn-run-1": 1,
        }
        mapped = map_lineage_counts_to_observed_runs(exported, id_map=id_map)
        self.assertEqual(len(mapped), 12)
        self.assertEqual(mapped[0].edit_event_id, 1)
        self.assertEqual(
            mapped[0].event_positive_divisions + mapped[0].event_negative_divisions,
            mapped[0].detected_divisions,
        )

    def test_fractional_counts_cannot_map_into_aggregate_runs(self) -> None:
        completed = balanced_event_counts(
            completed_error=8,
            completed_no_error=28,
            no_division=0,
            death_before_completion=0,
        )
        study = lineage_study_from_counts(
            study_id="syn-fractional-map",
            per_event={
                f"syn-event-{index}": {"vehicle": dict(completed), "treatment": dict(completed)}
                for index in (1, 2, 3)
            },
        )
        exported = export_first_attempt_aggregates(study)
        id_map = {
            "syn-event-1": 1,
            "syn-event-2": 2,
            "syn-event-3": 3,
            "syn-clone-syn-event-1-1": 1,
            "syn-clone-syn-event-1-2": 2,
            "syn-clone-syn-event-2-1": 3,
            "syn-clone-syn-event-2-2": 4,
            "syn-clone-syn-event-3-1": 5,
            "syn-clone-syn-event-3-2": 6,
            "syn-run-1": 1,
        }
        for field, value in (("opportunities", 2.9), ("detected_divisions", True)):
            tampered = json.loads(json.dumps(exported, allow_nan=False))
            tampered["runs"][0][field] = value
            with self.assertRaisesRegex(LineageError, "non-negative integer"):
                map_lineage_counts_to_observed_runs(tampered, id_map=id_map)

    def test_duplicate_rows_cannot_map_into_aggregate_runs(self) -> None:
        completed = balanced_event_counts(
            completed_error=8,
            completed_no_error=28,
            no_division=0,
            death_before_completion=0,
        )
        study = lineage_study_from_counts(
            study_id="syn-duplicate-map",
            per_event={
                f"syn-event-{index}": {"vehicle": dict(completed), "treatment": dict(completed)}
                for index in (1, 2, 3)
            },
        )
        exported = export_first_attempt_aggregates(study)
        tampered = json.loads(json.dumps(exported, allow_nan=False))
        tampered["runs"].append(dict(tampered["runs"][0]))
        id_map = {
            "syn-event-1": 1,
            "syn-event-2": 2,
            "syn-event-3": 3,
            "syn-clone-syn-event-1-1": 1,
            "syn-clone-syn-event-1-2": 2,
            "syn-clone-syn-event-2-1": 3,
            "syn-clone-syn-event-2-2": 4,
            "syn-clone-syn-event-3-1": 5,
            "syn-clone-syn-event-3-2": 6,
            "syn-run-1": 1,
        }
        with self.assertRaisesRegex(LineageError, "duplicate"):
            map_lineage_counts_to_observed_runs(tampered, id_map=id_map)

    def test_unlocked_counts_cannot_map_into_aggregate_runs(self) -> None:
        exported = export_first_attempt_aggregates(
            lineage_study_from_counts(
                study_id="syn-unlocked-map",
                per_event={
                    f"syn-event-{index}": {
                        "vehicle": balanced_event_counts(
                            completed_error=8,
                            completed_no_error=28,
                            no_division=0,
                            death_before_completion=0,
                        ),
                        "treatment": balanced_event_counts(
                            completed_error=8,
                            completed_no_error=28,
                            no_division=0,
                            death_before_completion=0,
                        ),
                    }
                    for index in (1, 2, 3)
                },
                lock_state="unlocked",
            )
        )
        self.assertEqual(exported["lock_state"], "unlocked")
        with self.assertRaisesRegex(LineageError, "unlocked"):
            map_lineage_counts_to_observed_runs(
                exported,
                id_map={
                    "syn-event-1": 1,
                    "syn-event-2": 2,
                    "syn-event-3": 3,
                    "syn-clone-syn-event-1-1": 1,
                    "syn-clone-syn-event-1-2": 2,
                    "syn-clone-syn-event-2-1": 3,
                    "syn-clone-syn-event-2-2": 4,
                    "syn-clone-syn-event-3-1": 5,
                    "syn-clone-syn-event-3-2": 6,
                    "syn-run-1": 1,
                },
            )

    def test_unblinded_counts_cannot_map_into_aggregate_runs(self) -> None:
        exported = export_first_attempt_aggregates(
            lineage_study_from_counts(
                study_id="syn-unblinded-map",
                per_event={
                    f"syn-event-{index}": {
                        "vehicle": balanced_event_counts(
                            completed_error=8,
                            completed_no_error=28,
                            no_division=0,
                            death_before_completion=0,
                        ),
                        "treatment": balanced_event_counts(
                            completed_error=8,
                            completed_no_error=28,
                            no_division=0,
                            death_before_completion=0,
                        ),
                    }
                    for index in (1, 2, 3)
                },
                blinded=False,
            )
        )
        self.assertFalse(exported["blinded"])
        with self.assertRaisesRegex(LineageError, "unblinded"):
            map_lineage_counts_to_observed_runs(
                exported,
                id_map={
                    "syn-event-1": 1,
                    "syn-event-2": 2,
                    "syn-event-3": 3,
                    "syn-clone-syn-event-1-1": 1,
                    "syn-clone-syn-event-1-2": 2,
                    "syn-clone-syn-event-2-1": 3,
                    "syn-clone-syn-event-2-2": 4,
                    "syn-clone-syn-event-3-1": 5,
                    "syn-clone-syn-event-3-2": 6,
                    "syn-run-1": 1,
                },
            )


class LineageAdversarialRegressionTests(unittest.TestCase):
    def test_zero_error_clone_cannot_hide_single_clone_reduction(self) -> None:
        vehicle = balanced_event_counts(completed_error=4, completed_no_error=16)
        treatment = balanced_event_counts(completed_error=1, completed_no_error=19)
        base = lineage_study_from_counts(
            study_id="syn-null-clone",
            per_event=_three_events(vehicle, treatment),
        )
        founders = []
        no_error_serial: dict[tuple[str, str], int] = {}
        for row in base.founders:
            key = (row.edit_event_id, row.arm)
            if row.first_attempt_outcome == "completed_error":
                clone_index = 1
            else:
                no_error_serial[key] = no_error_serial.get(key, 0) + 1
                # clone-1 takes the first eight non-error founders so its
                # completion share stays at the 0.60 boundary
                clone_index = 1 if no_error_serial[key] <= 8 else 2
            clone_id = f"syn-clone-{row.edit_event_id}-{clone_index}"
            founders.append(
                dataclasses.replace(
                    row,
                    clone_id=clone_id,
                    functional_execution_id=(
                        f"syn-functional-{row.edit_event_id}-{clone_index}-{row.arm}"
                    ),
                )
            )
        study = dataclasses.replace(base, founders=tuple(founders))
        analysis = analyze_lineage_study(study)
        self.assertTrue(analysis["flags"]["single_clone_effect"])
        self.assertFalse(analysis["status"]["clean_generation_signal"])

    def test_pediatric_band_rejects_per_event_drop_cancellation(self) -> None:
        drop_vehicle = balanced_event_counts(
            completed_error=8, completed_no_error=40, no_division=2
        )
        drop_treatment = balanced_event_counts(
            completed_error=8, completed_no_error=37, no_division=5
        )
        rise_vehicle = balanced_event_counts(
            completed_error=8, completed_no_error=37, no_division=5
        )
        rise_treatment = balanced_event_counts(
            completed_error=8, completed_no_error=40, no_division=2
        )
        per_event: dict[str, dict[str, dict[str, int]]] = {}
        for index in range(1, 9):
            if index % 2:
                per_event[f"syn-event-{index}"] = {
                    "vehicle": dict(drop_vehicle),
                    "treatment": dict(drop_treatment),
                }
            else:
                per_event[f"syn-event-{index}"] = {
                    "vehicle": dict(rise_vehicle),
                    "treatment": dict(rise_treatment),
                }
        study = lineage_study_from_counts(
            study_id="syn-canceling-drops", per_event=per_event
        )
        analysis = analyze_lineage_study(study)
        self.assertTrue(analysis["status"]["measurement_valid"])
        self.assertFalse(analysis["status"]["pediatric_completion_equivalent"])

    def test_bool_and_noninteger_counts_fail_closed(self) -> None:
        counts = balanced_event_counts(
            completed_error=8, completed_no_error=28
        )
        for bad in (True, 1.5, "3", -2):
            with self.subTest(bad=bad):
                forged = dict(counts)
                forged["completed_error"] = bad
                with self.assertRaises(LineageError):
                    lineage_study_from_counts(
                        study_id="syn-bad-count",
                        per_event=_three_events(forged, counts),
                    )

    def test_arm_mismatched_clone_ids_cannot_hide_single_clone_drive(self) -> None:
        vehicle = balanced_event_counts(completed_error=8, completed_no_error=28)
        treatment = balanced_event_counts(completed_error=2, completed_no_error=34)
        base = lineage_study_from_counts(
            study_id="syn-mismatched-clones",
            per_event=_three_events(vehicle, treatment),
        )
        founders = []
        for row in base.founders:
            prefix = "trt" if row.arm == "treatment" else "veh"
            clone_id = f"{prefix}-{row.edit_event_id}-{row.clone_id.rsplit('-', 1)[-1]}"
            founders.append(
                dataclasses.replace(
                    row,
                    clone_id=clone_id,
                    functional_execution_id=(
                        f"syn-functional-{clone_id}-{row.arm}"
                    ),
                )
            )
        study = dataclasses.replace(base, founders=tuple(founders))
        analysis = analyze_lineage_study(study)
        self.assertTrue(analysis["flags"]["single_clone_effect"])
        self.assertFalse(analysis["status"]["clean_generation_signal"])

    def test_per_event_death_spike_cannot_hide_in_pooled_mean(self) -> None:
        calm_vehicle = balanced_event_counts(
            completed_error=8,
            completed_no_error=40,
            no_division=1,
            death_before_completion=1,
        )
        calm_treatment = balanced_event_counts(
            completed_error=8,
            completed_no_error=38,
            no_division=1,
            death_before_completion=3,
        )
        hot_treatment = balanced_event_counts(
            completed_error=8,
            completed_no_error=31,
            no_division=1,
            death_before_completion=10,
        )
        per_event = {
            "syn-event-1": {
                "vehicle": dict(calm_vehicle),
                "treatment": dict(hot_treatment),
            }
        }
        for index in range(2, 9):
            per_event[f"syn-event-{index}"] = {
                "vehicle": dict(calm_vehicle),
                "treatment": dict(calm_treatment),
            }
        study = lineage_study_from_counts(
            study_id="syn-spiked-death", per_event=per_event
        )
        analysis = analyze_lineage_study(study)
        self.assertTrue(analysis["flags"]["general_toxicity"])
        self.assertFalse(analysis["status"]["clean_generation_signal"])

    def test_bool_daughter_plan_counts_fail_closed(self) -> None:
        counts = balanced_event_counts(completed_error=8, completed_no_error=28)
        plan = {
            f"syn-event-{index}": {
                "vehicle": {"error_reproduced": True},
                "treatment": {"error_reproduced": 1},
            }
            for index in (1, 2, 3)
        }
        with self.assertRaises(LineageError):
            lineage_study_from_counts(
                study_id="syn-bad-plan",
                per_event=_three_events(counts, counts),
                daughter_plan=plan,
            )


class LineageScriptSmokeTests(unittest.TestCase):
    def test_suite_receipt_can_be_written_once(self) -> None:
        receipt = run_adversarial_suite()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lineage-receipt.json"
            path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(loaded["all_passed"])


if __name__ == "__main__":
    unittest.main()
