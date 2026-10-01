from __future__ import annotations

import copy
import dataclasses
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import mva_hackathon.generation_selection as generation_selection
from mva_hackathon.generation_selection import (
    BIOLOGICAL_FLAGS,
    ESTIMANDS,
    AnalysisThresholds,
    ArmAuditCounts,
    ArmParameters,
    GenerationSelectionError,
    Heterogeneity,
    MeasurementParameters,
    ObservedAggregateStudy,
    ObservedRun,
    SharedCalibrationCounts,
    StableRng,
    StudyDesign,
    analyze_observed_study,
    load_and_run_benchmark,
    run_benchmark,
    simulate_aggregate_study,
)
from run_generation_selection_benchmark import benchmark_exit_code


CONFIG = ROOT / "configs" / "track2-generation-selection-benchmark.json"


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _objects(config: dict | None = None) -> tuple:
    value = _config() if config is None else config
    return (
        StudyDesign(**value["design"]),
        Heterogeneity(**value["heterogeneity"]),
        ArmParameters(**value["vehicle"]),
        MeasurementParameters(**value["shared_measurement"]),
        MeasurementParameters(**value["vehicle_measurement"]),
        AnalysisThresholds(**value["thresholds"]),
    )


def _simulate(
    *,
    scenario_name: str = "fewer_new_errors_strong",
    seed: int = 19,
    config: dict | None = None,
):
    value = _config() if config is None else config
    design, heterogeneity, vehicle, shared, vehicle_measurement, _ = _objects(value)
    scenario = next(
        row for row in value["scenarios"] if row["name"] == scenario_name
    )
    return simulate_aggregate_study(
        design=design,
        heterogeneity=heterogeneity,
        vehicle=vehicle,
        treatment=ArmParameters(**scenario["treatment"]),
        shared_measurement=shared,
        vehicle_measurement=vehicle_measurement,
        treatment_measurement=MeasurementParameters(
            **scenario["treatment_measurement"]
        ),
        seed=seed,
    )


def _perfect_calibration() -> SharedCalibrationCounts:
    return SharedCalibrationCounts(
        reference_errors=1000,
        detected_reference_errors=1000,
        reference_nonerrors=1000,
        false_positive_reference_nonerrors=0,
        reference_divisions=1000,
        detected_reference_divisions=1000,
    )


def _balanced_audits() -> dict[str, ArmAuditCounts]:
    audit = ArmAuditCounts(
        reference_errors=1000,
        detected_reference_errors=900,
        reference_nonerrors=2000,
        false_positive_reference_nonerrors=10,
        reference_divisions=1000,
        detected_reference_divisions=950,
    )
    return {"vehicle": audit, "treatment": audit}


def _fixed_cohort_study(
    *,
    treatment_divisions: int = 850,
    treatment_event_divisions: tuple[int, ...] | None = None,
    treatment_event_positive_daughters: tuple[int, ...] | None = None,
) -> tuple[
    ObservedAggregateStudy, StudyDesign, AnalysisThresholds
]:
    """Deterministic first-attempt aggregates with three edit-event units."""

    config = _config()
    design = StudyDesign(
        edit_events=3,
        clones_per_edit_event=1,
        runs_per_clone=1,
        observation_opportunities_per_run=1000,
        shared_event_reference_errors=1000,
        shared_event_reference_nonerrors=1000,
        shared_division_reference_events=1000,
        arm_event_audit_errors=1000,
        arm_event_audit_nonerrors=2000,
        arm_division_audit_events=1000,
    )
    thresholds = dataclasses.replace(
        AnalysisThresholds(**config["thresholds"]),
        minimum_event_positive_followed_per_edit_event=20,
    )
    runs: list[ObservedRun] = []
    for event in range(1, 4):
        runs.append(
            ObservedRun(
                arm="vehicle",
                edit_event_id=event,
                clone_id=event,
                run_id=1,
                opportunities=1000,
                detected_divisions=850,
                event_positive_divisions=68,
                event_negative_divisions=782,
                event_positive_daughters_followed=136,
                event_positive_daughters_reproduced=82,
                event_positive_daughters_died=20,
                event_negative_daughters_followed=1564,
                event_negative_daughters_reproduced=1220,
                event_negative_daughters_died=78,
            )
        )
        event_treatment_divisions = (
            treatment_divisions
            if treatment_event_divisions is None
            else treatment_event_divisions[event - 1]
        )
        treatment_positive = 26 if event_treatment_divisions == 850 else 15
        treatment_negative = event_treatment_divisions - treatment_positive
        event_positive_reproduced = (
            round(1.2 * treatment_positive)
            if treatment_event_positive_daughters is None
            else treatment_event_positive_daughters[event - 1]
        )
        runs.append(
            ObservedRun(
                arm="treatment",
                edit_event_id=event,
                clone_id=event,
                run_id=1,
                opportunities=1000,
                detected_divisions=event_treatment_divisions,
                event_positive_divisions=treatment_positive,
                event_negative_divisions=treatment_negative,
                event_positive_daughters_followed=2 * treatment_positive,
                event_positive_daughters_reproduced=event_positive_reproduced,
                event_positive_daughters_died=round(0.3 * treatment_positive),
                event_negative_daughters_followed=2 * treatment_negative,
                event_negative_daughters_reproduced=round(
                    1.56 * treatment_negative
                ),
                event_negative_daughters_died=round(0.1 * treatment_negative),
            )
        )
    return (
        ObservedAggregateStudy(
            runs=tuple(runs),
            shared_calibration=_perfect_calibration(),
            arm_audits=_balanced_audits(),
        ),
        design,
        thresholds,
    )


class GenerationSelectionContractTests(unittest.TestCase):
    def test_config_is_strict_v3_and_has_no_oracle_invalid_list(self) -> None:
        config = _config()
        self.assertEqual(config["schema"], "mva-generation-selection-benchmark/v3")
        self.assertNotIn("invalid_estimands", json.dumps(config, allow_nan=False))
        self.assertGreaterEqual(config["design"]["edit_events"], 3)
        self.assertTrue(
            any(
                row["gate"] == "required"
                and "generation_reduction" in row["expected_flags"]
                for row in config["scenarios"]
            )
        )
        self.assertTrue(
            any(
                row["gate"] == "required"
                and "generation_reduction" not in row["expected_flags"]
                for row in config["scenarios"]
            )
        )

    def test_analyzer_signature_and_observed_schema_are_truth_blind(self) -> None:
        signature = inspect.signature(analyze_observed_study)
        self.assertEqual(list(signature.parameters), ["study", "design", "thresholds"])
        self.assertEqual(
            {field.name for field in dataclasses.fields(ObservedAggregateStudy)},
            {"runs", "shared_calibration", "arm_audits"},
        )
        observed_fields = {field.name for field in dataclasses.fields(ObservedRun)}
        self.assertFalse(any("true" in name or "latent" in name for name in observed_fields))
        self.assertNotIn("measurement", observed_fields)
        self.assertFalse(hasattr(generation_selection, "ObservedDivision"))
        self.assertFalse(hasattr(generation_selection, "simulate_observed_study"))

    def test_strict_config_rejects_oracle_fields_and_missing_scenario_classes(self) -> None:
        config = _config()
        config["invalid_estimands"] = []
        with self.assertRaises(GenerationSelectionError):
            run_benchmark(config)

        config = _config()
        for scenario in config["scenarios"]:
            scenario["expected_flags"] = [
                flag
                for flag in scenario["expected_flags"]
                if flag != "generation_reduction"
            ]
        with self.assertRaisesRegex(GenerationSelectionError, "required G"):
            run_benchmark(config)

        config = _config()
        config["scenarios"] = [
            row
            for row in config["scenarios"]
            if "generation_reduction" in row["expected_flags"]
        ]
        with self.assertRaisesRegex(GenerationSelectionError, "required non-G"):
            run_benchmark(config)

    def test_duplicate_json_keys_are_rejected_before_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(
                '{"schema":"mva-generation-selection-benchmark/v3","schema":"x"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(GenerationSelectionError, "duplicate"):
                load_and_run_benchmark(path)

    def test_near_vacuous_thresholds_are_rejected(self) -> None:
        base = _config()["thresholds"]
        vacuous = [
            {"generation_reduction_ratio": 0.999},
            {"selection_reduction_ratio": 0.99},
            {"division_reduction_ratio": 0.9999},
            {"selection_increase_ratio": 1.000001},
            {"toxicity_increase_ratio": 1.000001},
            {"event_false_positive_increase_ratio": 1.000001},
            {"division_equivalence_lower_ratio": 1e-9},
            {"division_equivalence_upper_ratio": 1e12},
            {"event_detection_bias_ratio": 0.01},
            {"division_detection_bias_ratio": 0.01},
            {"followup_bias_ratio": 0.01},
            {"confidence_multiplier": 1e-12},
            {"confidence_multiplier": 1.0},
            {"minimum_calibration_youden": 0.1},
            {"minimum_detected_divisions_per_edit_event": 9},
            {"minimum_event_positive_followed_per_edit_event": 5},
            {"minimum_event_negative_followed_per_edit_event": 5},
            {"minimum_posterior_separation": 0.19},
        ]
        for override in vacuous:
            with self.subTest(override=override):
                with self.assertRaises(GenerationSelectionError):
                    AnalysisThresholds(**{**base, **override})

    def test_design_and_replicate_resource_ceilings_are_enforced(self) -> None:
        config = _config()
        config["design"]["edit_events"] = 2_000_000
        with self.assertRaises(GenerationSelectionError):
            run_benchmark(config)

        config = _config()
        config["monte_carlo_replicates"] = 200_000
        with self.assertRaises(GenerationSelectionError):
            run_benchmark(config)

        config = _config()
        config["design"]["observation_opportunities_per_run"] = 1_000_000
        with self.assertRaises(GenerationSelectionError):
            run_benchmark(config)


class GenerationSelectionGeneratorTests(unittest.TestCase):
    def test_rng_and_aggregate_simulator_are_deterministic(self) -> None:
        first_rng = StableRng(42)
        second_rng = StableRng(42)
        self.assertEqual(
            [first_rng.random() for _ in range(20)],
            [second_rng.random() for _ in range(20)],
        )
        first = _simulate(seed=42)
        second = _simulate(seed=42)
        self.assertEqual(first, second)
        design, *_ = _objects()
        self.assertEqual(
            len(first.observed.runs),
            2
            * design.edit_events
            * design.clones_per_edit_event
            * design.runs_per_clone,
        )
        self.assertFalse(hasattr(first.observed, "truth"))

    def test_binomial_sampler_does_not_underflow_at_adversarial_counts(self) -> None:
        rng = StableRng(991)
        draws = [generation_selection._binomial(2000, 0.4, rng) for _ in range(20)]
        self.assertTrue(all(600 < draw < 1000 for draw in draws))
        self.assertAlmostEqual(sum(draws) / len(draws), 800, delta=35)

    def test_daughter_outcomes_and_first_attempt_labels_are_coherent(self) -> None:
        simulation = _simulate(seed=73)
        for run in simulation.observed.runs:
            self.assertEqual(
                run.event_positive_divisions + run.event_negative_divisions,
                run.detected_divisions,
            )
            self.assertLessEqual(run.detected_divisions, run.opportunities)
            for label in ("positive", "negative"):
                followed = getattr(run, f"event_{label}_daughters_followed")
                reproduced = getattr(run, f"event_{label}_daughters_reproduced")
                died = getattr(run, f"event_{label}_daughters_died")
                divisions = getattr(run, f"event_{label}_divisions")
                self.assertLessEqual(followed, 2 * divisions)
                self.assertLessEqual(reproduced + died, followed)

    def test_arm_well_and_treatment_heterogeneity_change_realized_truth(self) -> None:
        config = _config()
        full = _simulate(seed=91, config=config)
        config["heterogeneity"] = {
            "edit_event_sd": 0.0,
            "clone_sd": 0.0,
            "run_sd": 0.0,
            "arm_well_sd": 0.0,
            "edit_treatment_sd": 0.0,
            "clone_treatment_sd": 0.0,
        }
        homogeneous = _simulate(seed=91, config=config)
        self.assertNotEqual(full.truth.ratios, homogeneous.truth.ratios)
        self.assertEqual(set(full.truth.ratios), set(ESTIMANDS))

    def test_parameter_and_observed_count_invariants_fail_closed(self) -> None:
        with self.assertRaisesRegex(GenerationSelectionError, "below one"):
            ArmParameters(
                division_probability=0.8,
                new_error_probability=0.1,
                error_daughter_reproduction_probability=0.8,
                nonerror_daughter_reproduction_probability=0.7,
                error_daughter_death_probability=0.2,
                nonerror_daughter_death_probability=0.1,
            )
        with self.assertRaisesRegex(GenerationSelectionError, "partition"):
            ObservedRun(
                arm="vehicle",
                edit_event_id=1,
                clone_id=1,
                run_id=1,
                opportunities=100,
                detected_divisions=80,
                event_positive_divisions=10,
                event_negative_divisions=60,
                event_positive_daughters_followed=10,
                event_positive_daughters_reproduced=5,
                event_positive_daughters_died=1,
                event_negative_daughters_followed=20,
                event_negative_daughters_reproduced=10,
                event_negative_daughters_died=1,
            )


class GenerationSelectionAnalysisTests(unittest.TestCase):
    def test_edit_event_is_inferential_unit_not_clone_or_run(self) -> None:
        study, design, thresholds = _fixed_cohort_study()
        one_clone = analyze_observed_study(
            study, design=design, thresholds=thresholds
        )
        duplicated: list[ObservedRun] = []
        for run in study.runs:
            duplicated.append(run)
            duplicated.append(dataclasses.replace(run, clone_id=run.clone_id + 100))
        two_clone_design = dataclasses.replace(design, clones_per_edit_event=2)
        two_clone_study = dataclasses.replace(study, runs=tuple(duplicated))
        two_clones = analyze_observed_study(
            two_clone_study, design=two_clone_design, thresholds=thresholds
        )
        for estimand in ESTIMANDS:
            self.assertEqual(
                one_clone["estimates"][estimand],
                two_clones["estimates"][estimand],
            )

    def test_dual_generation_endpoints_concord_and_completion_gates_clean_claim(self) -> None:
        study, design, thresholds = _fixed_cohort_study(treatment_divisions=850)
        clean = analyze_observed_study(
            study, design=design, thresholds=thresholds
        )
        self.assertTrue(clean["flags"]["generation_reduction"])
        self.assertTrue(clean["status"]["conditional_generation_reduction"])
        self.assertTrue(
            clean["status"]["founder_error_bearing_completion_reduction"]
        )
        self.assertTrue(clean["status"]["division_completion_equivalent"])
        self.assertTrue(clean["status"]["clean_generation_signal"])

        shifted_study, shifted_design, shifted_thresholds = _fixed_cohort_study(
            treatment_divisions=500
        )
        shifted = analyze_observed_study(
            shifted_study,
            design=shifted_design,
            thresholds=shifted_thresholds,
        )
        self.assertTrue(shifted["flags"]["generation_reduction"])
        self.assertTrue(shifted["flags"]["cytostasis"])
        self.assertFalse(shifted["status"]["division_completion_equivalent"])
        self.assertFalse(shifted["status"]["clean_generation_signal"])
        self.assertEqual(
            shifted["interpretation"],
            "generation_signal_with_unresolved_competing_completion",
        )
        self.assertIn("no-completion/death", shifted["status"]["primary_cohort_outcome_model"])
        self.assertIn("not separable", shifted["status"]["primary_cohort_boundary"])

    def test_event_scoped_completion_drop_refuses_despite_balanced_others(
        self,
    ) -> None:
        """One edit event can collapse while the pooled completion ratio
        stays near one. The declared pediatric rule caps the per-event
        absolute drop at 0.05, so the analyzer must refuse the clean
        certificate even though the pooled point ratio is ~1.00."""
        study, design, thresholds = _fixed_cohort_study(
            treatment_event_divisions=(780, 880, 880)
        )
        result = analyze_observed_study(
            study, design=design, thresholds=thresholds
        )
        status = result["status"]
        self.assertTrue(result["flags"]["generation_reduction"])
        self.assertGreater(
            status["maximum_event_completion_drop"], 0.05
        )
        self.assertFalse(status["division_completion_equivalent"])
        self.assertFalse(status["clean_generation_signal"])
        self.assertEqual(
            result["interpretation"],
            "generation_signal_with_unresolved_competing_completion",
        )

    def test_completion_overshoot_breaching_upper_band_refuses_clean(
        self,
    ) -> None:
        """Hyper-completion is not equivalence: a treatment arm that
        completes more first divisions than vehicle must not certify a
        clean rescue even when the generation signal fires."""
        study, design, thresholds = _fixed_cohort_study(
            treatment_divisions=970
        )
        result = analyze_observed_study(
            study, design=design, thresholds=thresholds
        )
        status = result["status"]
        self.assertTrue(result["flags"]["generation_reduction"])
        self.assertLess(status["maximum_event_completion_drop"], 0.0)
        self.assertFalse(status["division_completion_equivalent"])
        self.assertFalse(status["clean_generation_signal"])

    def test_imprecise_selection_interval_cannot_certify_equivalence(
        self,
    ) -> None:
        """A reproduction-ratio point estimate near one with an interval
        spanning both pruning and preservation regimes is not evidence of
        neutral selection: the declared equivalence margin requires the
        interval itself to fit inside [2/3, 1.5]."""
        study, design, thresholds = _fixed_cohort_study(
            treatment_event_positive_daughters=(8, 16, 27)
        )
        result = analyze_observed_study(
            study, design=design, thresholds=thresholds
        )
        estimate = result["estimates"]["relative_error_daughter_reproduction"]
        self.assertTrue(estimate["estimable"])
        self.assertGreater(estimate["upper"], 1.5)
        self.assertFalse(result["status"]["selection_equivalent"])
        self.assertFalse(result["status"]["clean_generation_signal"])

    def test_selection_equivalence_margin_bounds_are_validated(self) -> None:
        base = _config()["thresholds"]
        vacuous = [
            {"selection_equivalence_lower_ratio": 0.4},
            {"selection_equivalence_lower_ratio": 0.8},
            {"selection_equivalence_upper_ratio": 0.9},
            {"selection_equivalence_upper_ratio": 1.2},
            {"selection_equivalence_upper_ratio": 2.5},
            {"maximum_event_completion_drop": 0.5},
        ]
        for override in vacuous:
            with self.subTest(override=override):
                with self.assertRaises(GenerationSelectionError):
                    AnalysisThresholds(**{**base, **override})

    def test_event_division_drop_schema_is_strict(self) -> None:
        config = _config()
        config["monte_carlo_replicates"] = 2
        config["scenarios"] = [
            row
            for row in config["scenarios"]
            if row["name"] == "event_scoped_completion_drop_rescue"
        ] + [
            row
            for row in config["scenarios"]
            if row["name"] == "no_change"
        ]
        malformed = [
            [{"edit_event": 1}],
            [{"edit_event": 1, "drop": 0.2}, {"edit_event": 1, "drop": 0.3}],
            [{"edit_event": 0, "drop": 0.2}],
            [{"edit_event": 99, "drop": 0.2}],
            [{"edit_event": 1, "drop": -0.1}],
            [{"edit_event": 1.5, "drop": 0.2}],
            {"edit_event": 1, "drop": 0.2},
            [],
        ]
        for bad in malformed:
            with self.subTest(bad=bad):
                config["scenarios"][0]["treatment_event_division_drops"] = bad
                with self.assertRaises(GenerationSelectionError):
                    run_benchmark(config)

    def test_rate_summaries_carry_monte_carlo_standard_errors(self) -> None:
        config = _config()
        config["monte_carlo_replicates"] = 4
        config["scenarios"] = [
            row
            for row in config["scenarios"]
            if row["name"] in ("no_change", "fewer_new_errors_strong")
        ]
        result = run_benchmark(config)
        for row in result["scenarios"]:
            for summary in row["component_detection"].values():
                self.assertIn("mcse", summary)
                self.assertIsNotNone(summary["mcse"])
                self.assertGreaterEqual(summary["mcse"], 0.0)
                self.assertLessEqual(summary["mcse"], 0.5)
            self.assertIn("mcse", row["clean_generation_signal"])
        self.assertIn(
            "fail_closed_scenarios_total", result["summary"]
        )
        self.assertIn(
            "asserted_scenarios_total", result["summary"]
        )

    def test_quiescent_followed_daughters_stay_in_the_accounted_cohort(
        self,
    ) -> None:
        """A daughter followed to the window end without an outcome is a
        resolved observation (alive, no division) — not unaccounted
        progeny. Excluding her from the reproduction denominator
        conditions the rate on decided fates (r/(r+d)) and biases the
        relative estimand wherever arms have different quiescent
        fractions."""
        config = _config()
        design = StudyDesign(
            edit_events=3,
            clones_per_edit_event=1,
            runs_per_clone=1,
            observation_opportunities_per_run=1000,
            shared_event_reference_errors=1000,
            shared_event_reference_nonerrors=1000,
            shared_division_reference_events=1000,
            arm_event_audit_errors=1000,
            arm_event_audit_nonerrors=2000,
            arm_division_audit_events=1000,
        )
        thresholds = dataclasses.replace(
            AnalysisThresholds(**config["thresholds"]),
            minimum_event_positive_followed_per_edit_event=20,
        )
        runs: list[ObservedRun] = []
        for event in range(1, 4):
            runs.append(
                ObservedRun(
                    arm="vehicle",
                    edit_event_id=event,
                    clone_id=event,
                    run_id=1,
                    opportunities=1000,
                    detected_divisions=550,
                    event_positive_divisions=50,
                    event_negative_divisions=500,
                    event_positive_daughters_followed=100,
                    event_positive_daughters_reproduced=60,
                    event_positive_daughters_died=10,
                    event_negative_daughters_followed=1000,
                    event_negative_daughters_reproduced=780,
                    event_negative_daughters_died=50,
                )
            )
            runs.append(
                ObservedRun(
                    arm="treatment",
                    edit_event_id=event,
                    clone_id=event,
                    run_id=1,
                    opportunities=1000,
                    detected_divisions=550,
                    event_positive_divisions=50,
                    event_negative_divisions=500,
                    event_positive_daughters_followed=100,
                    event_positive_daughters_reproduced=60,
                    event_positive_daughters_died=40,
                    event_negative_daughters_followed=1000,
                    event_negative_daughters_reproduced=780,
                    event_negative_daughters_died=50,
                )
            )
        study = ObservedAggregateStudy(
            runs=tuple(runs),
            shared_calibration=_perfect_calibration(),
            arm_audits=_balanced_audits(),
        )
        result = analyze_observed_study(
            study, design=design, thresholds=thresholds
        )
        estimate = result["estimates"]["relative_error_daughter_reproduction"]
        self.assertTrue(estimate["estimable"])
        # Marginal error-daughter reproduction is 0.60 in both arms; only
        # the quiescent fraction differs. Conditioning on decided fates
        # would shrink the ratio to ~0.70 and read a phantom pruning
        # effect from a pure survival difference.
        self.assertAlmostEqual(float(estimate["ratio"]), 1.0, delta=0.15)

    def test_weak_shared_calibration_and_low_information_fail_closed(self) -> None:
        study, design, thresholds = _fixed_cohort_study()
        weak = dataclasses.replace(
            study,
            shared_calibration=SharedCalibrationCounts(
                reference_errors=100,
                detected_reference_errors=55,
                reference_nonerrors=100,
                false_positive_reference_nonerrors=45,
                reference_divisions=100,
                detected_reference_divisions=95,
            ),
        )
        result = analyze_observed_study(
            weak, design=design, thresholds=thresholds
        )
        self.assertFalse(result["estimability"]["generation_rate"]["estimable"])
        self.assertFalse(
            result["estimability"]["relative_error_daughter_reproduction"][
                "estimable"
            ]
        )
        self.assertFalse(any(result["flags"][name] for name in BIOLOGICAL_FLAGS))

        too_strict = dataclasses.replace(
            thresholds, minimum_detected_divisions_per_edit_event=900
        )
        insufficient = analyze_observed_study(
            study, design=design, thresholds=too_strict
        )
        for estimand in ESTIMANDS:
            self.assertFalse(insufficient["estimability"][estimand]["estimable"])
        self.assertFalse(any(insufficient["flags"][name] for name in BIOLOGICAL_FLAGS))

    def test_observed_arm_qc_suppresses_truth_blind_biological_inference(self) -> None:
        study, design, thresholds = _fixed_cohort_study()
        biased = dataclasses.replace(
            study,
            arm_audits={
                "vehicle": ArmAuditCounts(100, 90, 1000, 5, 100, 95),
                "treatment": ArmAuditCounts(100, 50, 1000, 5, 100, 95),
            },
        )
        result = analyze_observed_study(
            biased, design=design, thresholds=thresholds
        )
        self.assertTrue(result["flags"]["event_detection_bias"])
        self.assertFalse(result["status"]["measurement_valid"])
        self.assertFalse(any(result["flags"][name] for name in BIOLOGICAL_FLAGS))
        for estimand in ESTIMANDS:
            self.assertFalse(result["estimates"][estimand]["estimable"])
            self.assertEqual(
                result["estimates"][estimand]["reason"],
                "arm-specific measurement QC failed",
            )

    def test_vehicle_inflated_baseline_is_also_measurement_drift(self) -> None:
        study, design, thresholds = _fixed_cohort_study()
        biased = dataclasses.replace(
            study,
            arm_audits={
                "vehicle": ArmAuditCounts(1000, 900, 1000, 100, 1000, 950),
                "treatment": ArmAuditCounts(1000, 900, 1000, 5, 1000, 950),
            },
        )
        result = analyze_observed_study(
            biased, design=design, thresholds=thresholds
        )
        self.assertTrue(result["flags"]["event_specificity_bias"])
        self.assertFalse(result["status"]["measurement_valid"])
        self.assertFalse(result["status"]["clean_generation_signal"])
        self.assertFalse(any(result["flags"][name] for name in BIOLOGICAL_FLAGS))

    def test_underpowered_arm_audit_cannot_certify_clean(self) -> None:
        study, design, thresholds = _fixed_cohort_study()
        weak = dataclasses.replace(
            study,
            arm_audits={
                "vehicle": ArmAuditCounts(1, 1, 1, 1, 1, 1),
                "treatment": ArmAuditCounts(1, 1, 1, 0, 1, 1),
            },
        )
        result = analyze_observed_study(
            weak, design=design, thresholds=thresholds
        )
        self.assertTrue(result["flags"]["arm_audit_underpowered"])
        self.assertFalse(result["status"]["measurement_valid"])
        self.assertFalse(result["status"]["clean_generation_signal"])
        self.assertEqual(result["interpretation"], "measurement_invalid")
        self.assertFalse(any(result["flags"][name] for name in BIOLOGICAL_FLAGS))

    def test_duplicate_and_missing_runs_are_rejected(self) -> None:
        study, design, thresholds = _fixed_cohort_study()
        duplicate = dataclasses.replace(study, runs=study.runs + (study.runs[0],))
        with self.assertRaisesRegex(GenerationSelectionError, "duplicate"):
            analyze_observed_study(
                duplicate, design=design, thresholds=thresholds
            )
        missing = dataclasses.replace(study, runs=study.runs[:-1])
        with self.assertRaisesRegex(GenerationSelectionError, "missing or surplus"):
            analyze_observed_study(missing, design=design, thresholds=thresholds)


class GenerationSelectionBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.smoke_config = _config()
        cls.smoke_config["monte_carlo_replicates"] = 8
        cls.smoke = run_benchmark(cls.smoke_config)

    def test_low_replicate_smoke_emits_wilson_gates_and_invalid_fractions(self) -> None:
        self.assertEqual(
            self.smoke["schema"], "mva-generation-selection-benchmark/v3"
        )
        self.assertEqual(
            self.smoke["total_simulated_vehicle_treatment_comparisons"],
            8 * len(self.smoke_config["scenarios"]),
        )
        for scenario in self.smoke["scenarios"]:
            for component in scenario["component_detection"].values():
                self.assertIn("wilson_lower", component)
                self.assertIn("wilson_upper", component)
            for estimand in scenario["estimands"].values():
                self.assertIn("invalid_fraction_wilson_upper", estimand)
                self.assertIn("coverage_wilson_lower", estimand)
            self.assertIn("measurement_invalid", scenario)
        event_bias = next(
            row for row in self.smoke["scenarios"]
            if row["name"] == "event_detection_bias"
        )
        self.assertEqual(
            event_bias["estimands"]["generation_rate"]["invalid_fraction"], 1.0
        )
        specificity_bias = next(
            row for row in self.smoke["scenarios"]
            if row["name"] == "event_specificity_bias"
        )
        self.assertGreater(
            specificity_bias["component_detection"]["event_specificity_bias"][
                "successes"
            ],
            0,
        )
        self.assertEqual(
            specificity_bias["estimands"]["generation_rate"]["invalid_fraction"],
            specificity_bias["measurement_invalid"]["rate"],
        )

    def test_local_alternative_power_grid_is_present_and_ordered_by_truth(self) -> None:
        curve = self.smoke["local_alternative_power_curve"]
        self.assertEqual(len(curve), 3)
        ratios = [row["mean_realized_generation_ratio"] for row in curve]
        self.assertEqual(ratios, sorted(ratios))
        self.assertTrue(
            all("generation_detection_wilson_lower" in row for row in curve)
        )

    def test_sparse_mixed_scenario_is_scored_only_as_fail_closed(self) -> None:
        mixed = next(
            row for row in self.smoke["scenarios"]
            if row["name"] == "mixed_generation_selection_cytostasis"
        )
        self.assertEqual(mixed["gate"], "fail_closed")
        self.assertEqual(mixed["expected_flags"], [])
        self.assertGreater(
            mixed["fail_closed_refusals"]["successes"], 0
        )
        refusals = sum(
            mixed["interpretation_counts"].get(name, 0)
            for name in (
                "insufficient_information",
                "generation_signal_incomplete_deconvolution",
            )
        )
        self.assertEqual(
            mixed["fail_closed_refusals"]["successes"], refusals
        )

    def test_low_replicate_wilson_uncertainty_cannot_claim_acceptance(self) -> None:
        self.assertFalse(self.smoke["summary"]["acceptance_passed"])
        self.assertEqual(benchmark_exit_code(self.smoke), 1)
        self.assertEqual(benchmark_exit_code({"summary": {"acceptance_passed": True}}), 0)

    def test_measurement_scope_and_external_calibration_boundary_are_explicit(self) -> None:
        calibration = self.smoke["calibration_design"]
        self.assertIn("reusable external", calibration["shared_panel_role"])
        self.assertIn("not regenerated", calibration["shared_panel_role"])
        self.assertIn("blinded", calibration["arm_drift_audits"])
        # Scenario calibration panels are drawn per scenario so Monte Carlo
        # error is decorrelated across the suite; a miscalibrated override
        # must visibly change that scenario's realized panel rates.
        realized = {
            row["name"]: tuple(
                row["representative_observed_analysis"]["calibration"][key]
                for key in (
                    "shared_event_sensitivity",
                    "shared_event_specificity",
                    "shared_division_detection",
                )
            )
            for row in self.smoke["scenarios"]
        }
        self.assertGreater(len(set(realized.values())), 1)
        miscalibrated = next(
            scenario for scenario in self.smoke_config["scenarios"]
            if scenario["name"] == "miscalibrated_shared_panel"
        )
        override = miscalibrated["shared_measurement"]
        observed = realized["miscalibrated_shared_panel"]
        self.assertAlmostEqual(
            observed[0], override["error_event_sensitivity"], delta=0.2
        )
        self.assertAlmostEqual(
            observed[2],
            override["division_detection_probability"],
            delta=0.2,
        )
        self.assertLess(
            observed[0], self.smoke_config["shared_measurement"][
                "error_event_sensitivity"
            ],
        )
        boundaries = " ".join(self.smoke["unmodeled_measurement_boundaries"])
        self.assertIn("label misclassification is not", boundaries)
        self.assertIn("not identifiable", boundaries)

    def test_boundary_scenario_requires_a_declared_clean_signal_bound(self) -> None:
        config = _config()
        boundary = next(
            scenario for scenario in config["scenarios"]
            if scenario["gate"] == "boundary"
        )
        self.assertIn(
            "maximum_clean_signal_wilson_upper", boundary
        )
        del boundary["maximum_clean_signal_wilson_upper"]
        with self.assertRaisesRegex(
            GenerationSelectionError, "maximum_clean_signal_wilson_upper"
        ):
            run_benchmark(config)

    def test_detection_floor_requires_an_unbounded_required_g_row(self) -> None:
        config = _config()
        config["monte_carlo_replicates"] = 1
        for scenario in config["scenarios"]:
            if (
                scenario["gate"] == "required"
                and "generation_reduction" in scenario["expected_flags"]
            ):
                scenario["maximum_clean_signal_wilson_upper"] = 0.5
        with self.assertRaisesRegex(
            GenerationSelectionError, "detection floor"
        ):
            run_benchmark(config)

    def test_clean_signal_bound_is_enforced_per_scenario(self) -> None:
        config = _config()
        config["monte_carlo_replicates"] = 4
        strong = next(
            scenario for scenario in config["scenarios"]
            if scenario["name"] == "fewer_new_errors_strong"
        )
        keep_floor = copy.deepcopy(strong)
        keep_floor["name"] = "fewer_new_errors_strong_unbounded_twin"
        config["scenarios"].append(keep_floor)
        strong["maximum_clean_signal_wilson_upper"] = 0.0
        receipt = run_benchmark(config)
        row = next(
            row for row in receipt["scenarios"]
            if row["name"] == "fewer_new_errors_strong"
        )
        self.assertEqual(row["clean_signal_wilson_upper_bound"], 0.0)
        self.assertFalse(row["passed"])
        twin = next(
            row for row in receipt["scenarios"]
            if row["name"] == "fewer_new_errors_strong_unbounded_twin"
        )
        self.assertIsNone(twin["clean_signal_wilson_upper_bound"])

    def test_benchmark_is_deterministic_and_truth_never_enters_analysis_payload(self) -> None:
        config = _config()
        config["monte_carlo_replicates"] = 2
        first = run_benchmark(copy.deepcopy(config))
        second = run_benchmark(copy.deepcopy(config))
        self.assertEqual(first, second)
        payload = json.dumps(
            [
                row["representative_observed_analysis"]
                for row in first["scenarios"]
            ]
        , allow_nan=False)
        self.assertNotIn("realized_truth", payload)
        self.assertNotIn("generator", payload)


if __name__ == "__main__":
    unittest.main()
