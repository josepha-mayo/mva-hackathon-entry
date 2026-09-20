"""Verify that a real nested lab path can open and that false stories cannot.

This is a method simulator, not a biological simulator of checkpoint rescue.
It copies identifier-free community fixtures, fills only synthetic lab
objects, and asks whether the stop-early pipeline would advance. It does not
administer a medicine and does not raise a survival percentage.
"""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mva_hackathon.allele_confirmation import PINNED_FASTQ_NAME_DIGEST, SCHEMA as KMER_SCHEMA
from mva_hackathon.arm_allocation import (
    ASSIGNMENT_ALGORITHMS,
    ASSIGNMENT_MANIFEST_SCHEMA,
    ASSIGNMENT_METHODS,
    PLAN_SCHEMA,
    RANDOMIZATION_ENTROPY_AUTHENTICITY,
    RANDOMIZATION_GENERATOR,
    enumerate_admissible_assignment_vectors,
    make_allocation_analysis_plan_sha256,
    make_assignment_input_commitment,
    make_preexposure_allocation_id,
    make_seed_commitment,
    replay_seeded_assignment,
)
from mva_hackathon.community_pipeline import run_community_pipeline
from mva_hackathon.exposure_gate import make_exposure_profile_id
from mva_hackathon.hypothesis import mark_pair_program_observed
from mva_hackathon.lineage import (
    CLAIM_BOUNDARY as LINEAGE_CLAIM_BOUNDARY,
    FORBIDDEN_ANALYST_KEYS,
)
from mva_hackathon.structure_ranking import assess_structure_ranking
from mva_hackathon.tempdir import TemporaryDirectory


SCHEMA = "mva-track2-save-path-simulation/v2"
# The false-path matrix is a declared contract: exactly one true path and
# exactly this many adversarial variants must be exercised each run.
EXPECTED_TRUE_PATHS = 1
EXPECTED_FALSE_PATHS = 126
CLAIM_BOUNDARY = (
    "Save-path software simulation only; nested objects are synthetic; a "
    "reachable advance is not a rescued child; this is not efficacy evidence."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
COMMUNITY = REPO_ROOT / "templates" / "community"
# Function axes used by the carrier dose-control and function-at-abundance
# discriminators — mirrors program_gates.FUNCTION_AXES_ENDPOINTS.
FUNCTION_AXES = ("localization", "checkpoint", "first_division_error")
PIPELINE_FILES = (
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

MANIFEST_MEMBER_FIELDS = (
    "functional_execution_id",
    "edit_event_id",
    "clone_id",
    "culture_batch_id",
    "functional_assay_run_id",
    "allocation_block_id",
    "functional_assay_plate_id",
    "plate_row",
    "plate_column",
    "dosing_order",
    "acquisition_order",
)

# This fixed value belongs only to the transparent synthetic positive-control
# fixture. It is explicitly recorded as unattested entropy and is not a model
# for a real experiment, which must use a future independent entropy source.
SYNTHETIC_FIXTURE_SEED_HEX = (
    "0000000000000000000000000000000000000000000000000000000000000a6c"
)
SYNTHETIC_RESEAL_SEED_HEX = (
    "0000000000000000000000000000000000000000000000000000000000000001"
)

ARM_DEPENDENT_LINEAGE_FIELDS = (
    "exposure_support_record_id",
    "exposure_profile_id",
    "exposure_probe_id",
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


class SavePathError(ValueError):
    """Raised when the save-path fixtures cannot be assembled."""


def _relabel_unattested_synthetic_fixture_to_seed(
    *,
    exposure: dict[str, Any],
    lineage: dict[str, Any],
    seed_reveal_hex: str = SYNTHETIC_RESEAL_SEED_HEX,
) -> dict[str, Any]:
    """Replay one fixed synthetic seed and move arm-dependent fixture payloads.

    This is confined to synthetic software controls. It does not search seeds.
    Instead, it accepts the vector selected by one declared unattested seed and
    moves the already synthetic treatment/vehicle payloads within each pair so
    the fixture remains internally consistent after a plan digest changes. It
    must never be applied to observed data or a real allocation.
    """

    if exposure.get("schema") != "mva.community-measured-exposure-table/v1":
        raise SavePathError("synthetic reseal requires the exposure-table schema")
    if exposure.get("privacy_class") != "synthetic":
        raise SavePathError("synthetic reseal rejects non-synthetic exposure")
    if lineage.get("schema") != "mva-track2-lineage-counts/v1":
        raise SavePathError("synthetic reseal requires the lineage-count schema")
    if lineage.get("synthetic_only") is not True:
        raise SavePathError("synthetic reseal rejects non-synthetic lineage")
    allocation = exposure.get("preexposure_allocation")
    if not isinstance(allocation, dict):
        raise SavePathError("synthetic reseal requires an allocation object")
    randomization = allocation.get("randomization")
    if not isinstance(randomization, dict):
        raise SavePathError("synthetic reseal requires randomization metadata")
    if (
        randomization.get("entropy_authenticity")
        != RANDOMIZATION_ENTROPY_AUTHENTICITY
    ):
        raise SavePathError("synthetic reseal requires unattested synthetic entropy")
    seed_commitment_record = randomization.get("seed_commitment_record")
    if not isinstance(seed_commitment_record, dict):
        raise SavePathError("synthetic reseal requires a seed commitment record")
    replay = replay_seeded_assignment(
        assignment_manifest=allocation["assignment_manifest"],
        assignment_input_commitment_sha256=(
            allocation["assignment_input_commitment_sha256"]
        ),
        seed_reveal_hex=seed_reveal_hex,
    )
    treatment_ids = {
        str(item["treatment_execution_id"])
        for item in replay["selected_vector"]
    }
    assignments = allocation.get("assignments")
    if not isinstance(assignments, list):
        raise SavePathError("synthetic reseal requires allocation assignments")
    assignment_ids = {
        str(item.get("functional_execution_id")) for item in assignments
    }
    if not treatment_ids < assignment_ids:
        raise SavePathError("synthetic reseal selected an invalid treatment set")

    runs = lineage.get("runs")
    if not isinstance(runs, list) or not runs:
        raise SavePathError("synthetic reseal requires lineage runs")
    if {str(row.get("functional_execution_id")) for row in runs} != assignment_ids:
        raise SavePathError("synthetic reseal lineage does not match the manifest")
    by_pair: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in runs:
        key = (
            str(row.get("edit_event_id")),
            str(row.get("clone_id")),
            str(row.get("run_id")),
        )
        by_pair.setdefault(key, []).append(row)
    pair_plans: list[tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]] = []
    for pair_rows in by_pair.values():
        source_by_arm = {str(row.get("arm")): row for row in pair_rows}
        if len(pair_rows) != 2 or set(source_by_arm) != {"vehicle", "treatment"}:
            raise SavePathError("synthetic reseal requires complete paired arms")
        payload_by_arm = {
            arm: {
                field: source[field] for field in ARM_DEPENDENT_LINEAGE_FIELDS
            }
            for arm, source in source_by_arm.items()
        }
        pair_plans.append((pair_rows, payload_by_arm))

    measurement_records = {
        str(row.get("measurement_execution_id")): row
        for row in exposure.get("rows", [])
        if isinstance(row, dict) and row.get("measurement_execution_id")
    }
    control_records = {
        str(row.get("control_execution_id")): row
        for row in exposure.get("vehicle_controls", [])
        if isinstance(row, dict) and row.get("control_execution_id")
    }
    for pair_rows, payload_by_arm in pair_plans:
        for row in pair_rows:
            arm = (
                "treatment"
                if str(row.get("functional_execution_id")) in treatment_ids
                else "vehicle"
            )
            # The post-reseal support pointer is the swapped payload's, not
            # the row's current value — the swap moves the record id with
            # the arm.
            record_id = str(payload_by_arm[arm].get("exposure_support_record_id"))
            records = (
                measurement_records if arm == "treatment" else control_records
            )
            if record_id not in records:
                raise SavePathError("synthetic reseal support record is missing")

    # Every check passed — commit the reseal. No mutation may precede this
    # point: a caller that catches the error must not observe half-moved
    # declared data.
    for assignment in assignments:
        execution_id = str(assignment.get("functional_execution_id"))
        assignment["arm"] = (
            "treatment" if execution_id in treatment_ids else "vehicle"
        )
    for pair_rows, payload_by_arm in pair_plans:
        for row in pair_rows:
            execution_id = str(row.get("functional_execution_id"))
            arm = "treatment" if execution_id in treatment_ids else "vehicle"
            row["arm"] = arm
            for field, value in payload_by_arm[arm].items():
                row[field] = value
    for row in (*measurement_records.values(), *control_records.values()):
        row["supports_functional_execution_ids"] = []
    for row in runs:
        record_id = str(row.get("exposure_support_record_id"))
        records = measurement_records if row["arm"] == "treatment" else control_records
        records[record_id]["supports_functional_execution_ids"].append(
            str(row["functional_execution_id"])
        )
    for row in (*measurement_records.values(), *control_records.values()):
        row["supports_functional_execution_ids"].sort()

    randomization["seed_reveal_hex"] = seed_reveal_hex
    randomization["seed_commitment_sha256"] = make_seed_commitment(
        seed_reveal_hex,
        assignment_input_commitment_sha256=(
            allocation["assignment_input_commitment_sha256"]
        ),
    )
    seed_commitment_record["digest_sha256"] = (
        randomization["seed_commitment_sha256"]
    )
    randomization["entropy_authenticity"] = RANDOMIZATION_ENTROPY_AUTHENTICITY
    for field in (
        "admissible_space_count",
        "admissible_space_sha256",
        "selected_vector_sha256",
    ):
        randomization[field] = replay[field]
    allocation_id = make_preexposure_allocation_id(allocation)
    allocation["allocation_id"] = allocation_id
    allocation["commitment"]["plan_sha256"] = allocation_id.removeprefix(
        "allocation-"
    )
    lineage["allocation_id"] = allocation_id
    return replay


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SavePathError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise SavePathError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise SavePathError(f"non-finite JSON number: {value}")
    return parsed


def _json_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
            parse_float=_finite_float,
        )
    except RecursionError as exc:
        raise SavePathError("JSON payload is nested too deeply") from exc
    except (OverflowError, MemoryError) as exc:
        raise SavePathError(
            "JSON payload contains an out-of-range or oversized value"
        ) from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _copy_toolkit(folder: Path) -> Path:
    dest = folder / "community"
    dest.mkdir()
    for name in PIPELINE_FILES:
        source = COMMUNITY / name
        if not source.is_file():
            raise SavePathError(f"community toolkit is missing {name}")
        shutil.copy(source, dest / name)
    return dest


def _ticked_kmer_confirmation() -> dict[str, Any]:
    allele = {
        "status": "both_alleles_observed",
        "by_k": [
            {"k": 31, "status": "both_alleles_observed"},
            {"k": 51, "status": "both_alleles_observed"},
        ],
    }
    return {
        "schema": KMER_SCHEMA,
        "incomplete_inputs": False,
        "reverse_complement_counted": True,
        "alleles": [allele, dict(allele)],
    }


def passing_confirmation() -> dict[str, Any]:
    return {
        "schema": "mva.community-confirmation-record/v1",
        "privacy_class": "synthetic",
        "purpose": "Complete synthetic confirmation floors for save-path tests. library_molecule genomic means genomic DNA; an RNA or RNA-derived library cannot confirm genomic genotype. confirmation_specimen assay_matched means DNA from the confirmed genotype line; an unmatched line cannot stand in.",
        "specimen_identity_resolved": True,
        "second_aliquot": True,
        "layout_complete": True,
        "both_strands_counted": True,
        "allele_1_status": "both_alleles_observed",
        "allele_2_status": "both_alleles_observed",
        "declared_status": "both_alleles_observed",
        "producer": "synthetic_handoff",
        "library_molecule": "genomic",
        "confirmation_specimen": "assay_matched",
    }


def passing_power() -> dict[str, Any]:
    return {
        "schema": "mva.community-assay-power/v1",
        "privacy_class": "synthetic",
        "purpose": (
            "Locked synthetic imaging-power plan matching three edit events, "
            "six clones, and 36 opportunities per clone. A locked plan is not a "
            "completed study and is not efficacy evidence."
        ),
        "locked": True,
        "n_edit_events": 3,
        "n_clones_per_event": 6,
        "n_opportunities": 36,
        "locked_vehicle_error_rate": 12 / 36,
        "locked_treatment_error_rate": 4 / 36,
        "locked_vehicle_completion_rate": 1.0,
        "locked_treatment_completion_rate": 1.0,
        "minimum_detection": 0.8,
        "remaining_population_doublings": 8,
        "endpoint_class": "generation",
        "success_rule": "generation_drop",
    }


def passing_transcript() -> dict[str, Any]:
    return {
        "schema": "mva.community-transcript-record/v1",
        "privacy_class": "synthetic",
        "purpose": "Complete synthetic transcript fate for save-path tests. transcript_method allele_specific means an allele-specific RNA assay; a computational predictor or protein-surrogate row cannot stand in. transcript_specimen assay_matched means RNA from the confirmed genotype line; an unmatched line cannot stand in.",
        "stop_allele_rna": "deplete",
        "missense_allele_rna": "expressed",
        "declared_status": "stop_depleted_missense_expressed",
        "transcript_method": "allele_specific",
        "transcript_specimen": "assay_matched",
    }


def passing_lineage(*, competing: bool = False) -> dict[str, Any]:
    death = 1 if competing else 0
    no_division = 1 if competing else 0
    opportunities = 38 if competing else 36
    treatment_profile = {
        "nominal_uM": 1.0,
        "unbound_medium_uM": 0.71,
        "intracellular_parent": 0.33,
        "time_hours": 24,
        "pulse_vs_constant": "constant",
        "washout": False,
        "measurement_class": "culture_measured",
    }
    treatment_profile_id = make_exposure_profile_id(
        treatment_profile, "syn-probe-a"
    )
    runs: list[dict[str, Any]] = []
    for index in range(1, 4):
        for clone in range(1, 7):
            for arm, positive, member in (
                ("vehicle", 12, "member-a"),
                ("treatment", 4, "member-b"),
            ):
                positive_followed = (
                    positive
                    if competing and arm == "treatment"
                    else 2 * positive
                )
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
                            treatment_profile_id
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
                        "event_positive_daughters_followed": positive_followed,
                        "event_positive_daughters_reproduced": (
                            positive_followed // 2
                        ),
                        # Fully resolved fates: observed daughters either
                        # reproduce or die — no censored gap in the nominal
                        # fixture. Reproduction rate stays 0.5 on both arms.
                        "event_positive_daughters_died": (
                            positive_followed - positive_followed // 2
                        ),
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
        "privacy_class": "synthetic",
        "purpose": "Aligned synthetic lineage counts for save-path tests.",
        "study_id": "syn-save-path-lineage",
        "synthetic_only": True,
        "lock_state": "locked",
        "blinded": True,
        "forbidden_keys_absent": sorted(FORBIDDEN_ANALYST_KEYS),
        "claim_boundary": LINEAGE_CLAIM_BOUNDARY,
        "runs": runs,
    }


def blinded_from_lineage(lineage: MappingLike) -> dict[str, Any]:
    runs = []
    for row in lineage["runs"]:
        entry = {
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
        runs.append(entry)
    return {
        "schema": "mva.community-blinded-count-table/v2",
        "privacy_class": "synthetic",
        "purpose": "Aligned synthetic blinded counts for save-path tests.",
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


MappingLike = dict[str, Any]


def passing_exposure(
    lineage: MappingLike,
    plan: MappingLike,
) -> dict[str, Any]:
    """Build and bind a balanced synthetic exposure/allocation fixture.

    The helper annotates the supplied synthetic lineage rows with the realized
    allocation tuple so the later count-identity gate can test exact plan versus
    realization equality.
    """

    treatment_rows = [
        row for row in lineage.get("runs", []) if row.get("arm") == "treatment"
    ]
    vehicle_rows = [
        row for row in lineage.get("runs", []) if row.get("arm") == "vehicle"
    ]
    if not treatment_rows or not vehicle_rows:
        raise SavePathError("passing exposure requires paired lineage rows")
    profile_rows: list[dict[str, Any]] = [
        {
            "nominal_uM": 0.2,
            "unbound_medium_uM": 0.14,
            "intracellular_parent": 0.08,
            "time_hours": 24,
            "pulse_vs_constant": "constant",
            "washout": False,
            "measurement_class": "culture_measured",
        },
        {
            "nominal_uM": 0.5,
            "unbound_medium_uM": 0.36,
            "intracellular_parent": 0.19,
            "time_hours": 24,
            "pulse_vs_constant": "constant",
            "washout": False,
            "measurement_class": "culture_measured",
        },
        {
            "nominal_uM": 1.0,
            "unbound_medium_uM": 0.71,
            "intracellular_parent": 0.33,
            "time_hours": 24,
            "pulse_vs_constant": "constant",
            "washout": False,
            "measurement_class": "culture_measured",
        },
        {
            "nominal_uM": 2.0,
            "unbound_medium_uM": 1.38,
            "intracellular_parent": 0.61,
            "time_hours": 24,
            "pulse_vs_constant": "constant",
            "washout": False,
            "measurement_class": "culture_measured",
        },
        {
            "nominal_uM": 1.0,
            "unbound_medium_uM": 0.68,
            "intracellular_parent": 0.21,
            "time_hours": 4,
            "pulse_vs_constant": "pulse",
            "washout": True,
            "measurement_class": "culture_measured",
        },
    ]
    for row in profile_rows:
        row["selection_agent"] = "aminoglycoside"
        row["selection_agent_cleared"] = True
        row["selection_clearance_method"] = "serial_passage_without_agent"
    selected_profile = treatment_rows[0].get("exposure_profile_id")
    selected_supports = {row.get("exposure_support_record_id") for row in treatment_rows}
    if selected_supports != {"syn-measurement-3"}:
        raise SavePathError("passing lineage has inconsistent measurement support")
    supports = sorted(
        str(row.get("functional_execution_id")) for row in treatment_rows
    )
    run_ids = sorted({str(row.get("run_id")) for row in treatment_rows})
    batches = {row.get("batch_id") for row in treatment_rows}
    starts = {row.get("exposure_started_at") for row in treatment_rows}
    endpoints = {row.get("endpoint_recorded_at") for row in treatment_rows}
    probes = {row.get("exposure_probe_id") for row in treatment_rows}
    if (
        len(batches) != 1
        or len(starts) != 1
        or len(endpoints) != 1
        or probes != {"syn-probe-a"}
    ):
        raise SavePathError("passing lineage has inconsistent exposure context")
    started_text = str(next(iter(starts)))
    started = datetime.fromisoformat(started_text.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    rows = []
    for index, row in enumerate(profile_rows, start=1):
        profile_id = make_exposure_profile_id(row, "syn-probe-a")
        linked = profile_id == selected_profile
        rows.append(
            {
                **row,
                "exposure_profile_id": profile_id,
                "measurement_execution_id": f"syn-measurement-{index}",
                "supports_functional_execution_ids": supports if linked else [],
                "functional_assay_run_ids": run_ids if linked else [],
                "culture_batch_id": (
                    next(iter(batches))
                    if linked
                    else "syn-batch-measurement-a"
                ),
                "sample_relation": "matched_parallel_culture" if linked else None,
                "exposure_started_at": started_text if linked else None,
                "measurement_sampled_at": (
                    (started + timedelta(hours=float(row["time_hours"])))
                    .isoformat()
                    .replace("+00:00", "Z")
                    if linked
                    else None
                ),
                "exposure_measurement_plate_id": (
                    "syn-measurement-plate-a" if linked else None
                ),
                "probe_lot_id": "syn-probe-lot-a" if linked else None,
            }
        )
    vehicle_supports = {row.get("exposure_support_record_id") for row in vehicle_rows}
    vehicle_profiles = {row.get("exposure_profile_id") for row in vehicle_rows}
    vehicle_probes = {row.get("exposure_probe_id") for row in vehicle_rows}
    vehicle_batches = {row.get("batch_id") for row in vehicle_rows}
    vehicle_starts = {row.get("exposure_started_at") for row in vehicle_rows}
    vehicle_endpoints = {row.get("endpoint_recorded_at") for row in vehicle_rows}
    if (
        vehicle_supports != {"syn-vehicle-control-record-a"}
        or len(vehicle_profiles) != 1
        or len(vehicle_probes) != 1
        or vehicle_batches != batches
        or vehicle_starts != starts
        or vehicle_endpoints != endpoints
    ):
        raise SavePathError("passing lineage has inconsistent vehicle context")
    vehicle_controls = [
        {
            "control_execution_id": next(iter(vehicle_supports)),
            "supports_functional_execution_ids": sorted(
                str(row.get("functional_execution_id")) for row in vehicle_rows
            ),
            "functional_assay_run_ids": sorted(
                {str(row.get("run_id")) for row in vehicle_rows}
            ),
            "culture_batch_id": next(iter(vehicle_batches)),
            "exposure_profile_id": next(iter(vehicle_profiles)),
            "control_probe_id": next(iter(vehicle_probes)),
            "exposure_started_at": next(iter(vehicle_starts)),
            "endpoint_recorded_at": next(iter(vehicle_endpoints)),
        }
    ]
    pair_index: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    for lineage_row in (*vehicle_rows, *treatment_rows):
        key = (
            str(lineage_row.get("edit_event_id")),
            str(lineage_row.get("clone_id")),
            str(lineage_row.get("run_id")),
        )
        arm = str(lineage_row.get("arm"))
        by_arm = pair_index.setdefault(key, {})
        if arm in by_arm:
            raise SavePathError("passing lineage has a duplicate allocation arm")
        by_arm[arm] = lineage_row
    if any(set(by_arm) != {"vehicle", "treatment"} for by_arm in pair_index.values()):
        raise SavePathError("passing lineage allocation is not paired")

    n_pairs = len(pair_index)
    pairs_by_context: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for pair_key in sorted(pair_index):
        event_id, _clone_id, run_id = pair_key
        pairs_by_context.setdefault((event_id, run_id), []).append(pair_key)
    if any(len(keys) != 6 for keys in pairs_by_context.values()):
        raise SavePathError(
            "passing allocation requires exactly six biological pairs per event-run"
        )
    n_columns = max(4 * n_pairs, 12)
    half = n_columns // 2
    interior_columns = range(2, n_columns)
    available_columns = {
        ("left", "odd"): [
            column for column in interior_columns if column <= half and column % 2
        ],
        ("left", "even"): [
            column
            for column in interior_columns
            if column <= half and column % 2 == 0
        ],
        ("right", "odd"): [
            column for column in interior_columns if column > half and column % 2
        ],
        ("right", "even"): [
            column
            for column in interior_columns
            if column > half and column % 2 == 0
        ],
    }
    assignments: list[dict[str, Any]] = []
    allocation_contexts = sorted(
        {(event_id, run_id) for event_id, _clone_id, run_id in pair_index}
    )
    side_by_context = {
        context: ("left" if index % 2 else "right")
        for index, context in enumerate(allocation_contexts, start=1)
    }
    parity_by_context = {
        context: ("odd" if index % 2 else "even")
        for index, context in enumerate(allocation_contexts, start=1)
    }
    columns_by_context: dict[tuple[str, str], tuple[int, int]] = {}
    for context in allocation_contexts:
        pool = available_columns[
            (side_by_context[context], parity_by_context[context])
        ]
        if len(pool) < 2:
            raise SavePathError("synthetic allocation plate has insufficient wells")
        columns_by_context[context] = (pool.pop(0), pool.pop(0))
    pair_ordinal_by_key = {
        pair_key: ordinal
        for context in allocation_contexts
        for ordinal, pair_key in enumerate(pairs_by_context[context], start=1)
    }
    context_index = {
        context: index
        for index, context in enumerate(allocation_contexts)
    }
    # Pair blocks are acquired in a non-affine order while the two members of
    # each pair remain adjacent. This keeps the prespecified quadratic nuisance
    # design identifiable instead of making acquisition a copy of dosing.
    # This arm-blind pair schedule was selected before label assignment by an
    # exhaustive check of the six-pair permutations. Under the frozen full
    # bivariate-quadratic nuisance basis, every one of the 20 locally balanced
    # arm vectors retains at least 90% of its unadjusted information. The
    # committed manifest, not this comment, is the reproducible source of truth.
    acquisition_rank_by_pair_ordinal = {1: 1, 2: 0, 3: 4, 4: 3, 5: 2, 6: 5}
    for pair_number, (key, by_arm) in enumerate(sorted(pair_index.items()), start=1):
        event_id, clone_id, run_id = key
        context = (event_id, run_id)
        pair_ordinal = pair_ordinal_by_key[key]
        position_row = pair_ordinal
        columns = columns_by_context[context]
        # The selected synthetic arm vector has three upper and three lower
        # members in every context. It is one of the 20 prespecified vectors
        # that pass the allocation-information floor; randomization inference
        # remains the gate.
        arm_order = (
            ("vehicle", "treatment")
            if pair_ordinal in {1, 3, 5}
            else ("treatment", "vehicle")
        )
        order_by_arm = {
            arm: 2 * pair_number - 1 + offset
            for offset, arm in enumerate(arm_order)
        }
        acquisition_base = 12 * context_index[context]
        acquisition_by_arm = {
            arm: (
                acquisition_base
                + 2 * acquisition_rank_by_pair_ordinal[pair_ordinal]
                + 1
                + offset
            )
            for offset, arm in enumerate(arm_order)
        }
        column_by_arm = dict(zip(arm_order, columns, strict=True))
        for arm in ("vehicle", "treatment"):
            lineage_row = by_arm[arm]
            assignments.append(
                {
                    "functional_execution_id": str(
                        lineage_row.get("functional_execution_id")
                    ),
                    "arm": arm,
                    "edit_event_id": event_id,
                    "clone_id": clone_id,
                    "culture_batch_id": str(lineage_row.get("batch_id")),
                    "functional_assay_run_id": run_id,
                    "allocation_block_id": f"syn-allocation-block-{pair_number}",
                    "functional_assay_plate_id": "syn-functional-plate-a",
                    "plate_row": position_row,
                    "plate_column": column_by_arm[arm],
                    "dosing_order": order_by_arm[arm],
                    "acquisition_order": acquisition_by_arm[arm],
                    "deviation_status": "none",
                }
            )
    all_starts = [
        datetime.fromisoformat(
            str(row.get("exposure_started_at")).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        for row in (*vehicle_rows, *treatment_rows)
    ]
    earliest_start = min(all_starts)
    locked_at = earliest_start - timedelta(hours=2)
    input_commitment_recorded_at = earliest_start - timedelta(
        hours=1, minutes=50
    )
    seed_committed_at = earliest_start - timedelta(hours=1, minutes=45)
    seed_revealed_at = earliest_start - timedelta(hours=1, minutes=30)
    randomization_recorded_at = earliest_start - timedelta(hours=1, minutes=15)
    recorded_at = earliest_start - timedelta(hours=1)
    assay_plan_encoded = json.dumps(
        plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    , allow_nan=False)
    assay_plan_sha256 = hashlib.sha256(
        assay_plan_encoded.encode("utf-8")
    ).hexdigest()
    plate_dimensions = [
        {
            "functional_assay_plate_id": "syn-functional-plate-a",
            "n_rows": max(4, max(len(keys) for keys in pairs_by_context.values())),
            "n_columns": n_columns,
        }
    ]
    assignment_by_execution = {
        item["functional_execution_id"]: item for item in assignments
    }
    pair_units = []
    for pair_number, (pair_key, by_arm) in enumerate(
        sorted(pair_index.items()), start=1
    ):
        del pair_key
        members = [
            assignment_by_execution[str(row["functional_execution_id"])]
            for row in by_arm.values()
        ]
        pair_units.append(
            {
                "pair_id": f"syn-pair-{pair_number}",
                "members": [
                    {field: member[field] for field in MANIFEST_MEMBER_FIELDS}
                    for member in sorted(
                        members,
                        key=lambda item: item["functional_execution_id"],
                    )
                ],
            }
        )
    assignment_manifest = {
        "schema": ASSIGNMENT_MANIFEST_SCHEMA,
        # Keep the committed manifest structurally independent from the
        # realized-plan copy. In-memory aliasing would let a caller mutate two
        # supposedly distinct contract surfaces with one list edit.
        "plate_dimensions": copy.deepcopy(plate_dimensions),
        "pair_units": pair_units,
    }
    analysis_plan_sha256 = make_allocation_analysis_plan_sha256()
    assignment_method = ASSIGNMENT_METHODS[0]
    assignment_algorithm = ASSIGNMENT_ALGORITHMS[0]
    input_commitment = make_assignment_input_commitment(
        study_id=str(lineage.get("study_id")),
        assay_plan_sha256=assay_plan_sha256,
        analysis_plan_sha256=analysis_plan_sha256,
        assignment_method=assignment_method,
        assignment_algorithm=assignment_algorithm,
        allocation_unit="functional_execution_well",
        assignment_manifest=assignment_manifest,
    )
    replay = replay_seeded_assignment(
        assignment_manifest=assignment_manifest,
        assignment_input_commitment_sha256=input_commitment,
        seed_reveal_hex=SYNTHETIC_FIXTURE_SEED_HEX,
    )
    seed_commitment = make_seed_commitment(
        SYNTHETIC_FIXTURE_SEED_HEX,
        assignment_input_commitment_sha256=input_commitment,
    )
    allocation: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "allocation_id": "allocation-pending",
        "lock_state": "locked",
        "locked_at": locked_at.isoformat().replace("+00:00", "Z"),
        "study_id": str(lineage.get("study_id")),
        "assay_plan_sha256": assay_plan_sha256,
        "analysis_plan_sha256": analysis_plan_sha256,
        "assignment_method": assignment_method,
        "assignment_algorithm": assignment_algorithm,
        "assignment_input_commitment_sha256": input_commitment,
        "assignment_input_commitment_record": {
            "mechanism": "append_only_registry",
            "record_id": "syn-input-commitment-record-a",
            "recorded_at": input_commitment_recorded_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "digest_sha256": input_commitment,
        },
        "assignment_manifest": assignment_manifest,
        "randomization": {
            "generator": RANDOMIZATION_GENERATOR,
            "seed_commitment_sha256": seed_commitment,
            "seed_commitment_record": {
                "mechanism": "append_only_registry",
                "record_id": "syn-seed-commitment-record-a",
                "recorded_at": seed_committed_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "digest_sha256": seed_commitment,
            },
            "seed_committed_at": seed_committed_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "seed_reveal_hex": SYNTHETIC_FIXTURE_SEED_HEX,
            "seed_revealed_at": seed_revealed_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "entropy_authenticity": RANDOMIZATION_ENTROPY_AUTHENTICITY,
            "record": {
                "mechanism": "append_only_registry",
                "record_id": "syn-randomization-record-a",
                "recorded_at": randomization_recorded_at.isoformat().replace(
                    "+00:00", "Z"
                ),
            },
            "admissible_space_count": replay["admissible_space_count"],
            "admissible_space_sha256": replay["admissible_space_sha256"],
            "selected_vector_sha256": replay["selected_vector_sha256"],
        },
        "allocation_unit": "functional_execution_well",
        "commitment": {
            "mechanism": "append_only_registry",
            "record_id": "syn-allocation-commitment-a",
            "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
            "plan_sha256": "pending",
        },
        "plate_dimensions": copy.deepcopy(plate_dimensions),
        "assignments": assignments,
    }
    exposure_payload = {
        "schema": "mva.community-measured-exposure-table/v1",
        "privacy_class": "synthetic",
        "purpose": "Synthetic exposure profiles with an explicit assay-execution support map.",
        "probe_id": "syn-probe-a",
        "endpoint_class": plan.get("endpoint_class"),
        "success_rule": plan.get("success_rule"),
        "note": (
            "Metadata linkage can detect file collage but does not prove physical "
            "sample identity, dosing accuracy, or efficacy."
        ),
        "preexposure_allocation": allocation,
        "vehicle_controls": vehicle_controls,
        "columns": [
            "nominal_uM",
            "unbound_medium_uM",
            "intracellular_parent",
            "time_hours",
            "pulse_vs_constant",
            "washout",
            "measurement_class",
            "exposure_profile_id",
            "measurement_execution_id",
            "supports_functional_execution_ids",
            "functional_assay_run_ids",
            "culture_batch_id",
            "sample_relation",
            "exposure_started_at",
            "measurement_sampled_at",
            "selection_agent",
            "selection_agent_cleared",
            "selection_clearance_method",
        ],
        "rows": rows,
    }
    _relabel_unattested_synthetic_fixture_to_seed(
        exposure=exposure_payload,
        lineage=lineage,
        seed_reveal_hex=SYNTHETIC_FIXTURE_SEED_HEX,
    )
    assignment_index = {
        item["functional_execution_id"]: item for item in assignments
    }
    for lineage_row in lineage.get("runs", []):
        assignment = assignment_index.get(lineage_row.get("functional_execution_id"))
        if assignment is None:
            raise SavePathError("passing lineage execution is absent from allocation")
        for field in (
            "allocation_block_id",
            "functional_assay_plate_id",
            "plate_row",
            "plate_column",
            "dosing_order",
            "acquisition_order",
        ):
            lineage_row[field] = assignment[field]

    return exposure_payload


def write_aligned_counts(dest: Path, *, competing: bool = False) -> None:
    lineage = passing_lineage(competing=competing)
    plan = _json_loads(
        (dest / "assay_power.synthetic.json").read_text(encoding="utf-8")
    )
    exposure = passing_exposure(lineage, plan)
    _write_json(dest / "lineage_count_table.synthetic.json", lineage)
    _write_json(dest / "blinded_count_table.synthetic.json", blinded_from_lineage(lineage))
    _write_json(
        dest / "measured_exposure_table.synthetic.json",
        exposure,
    )


def write_passing_confirmation(dest: Path) -> None:
    _write_json(dest / "confirmation_record.synthetic.json", passing_confirmation())


def write_passing_transcript(dest: Path) -> None:
    _write_json(dest / "transcript_record.synthetic.json", passing_transcript())


def write_passing_power(dest: Path) -> None:
    _write_json(dest / "assay_power.synthetic.json", passing_power())


def rebind_allocation_to_current_plan(dest: Path) -> None:
    """Reseal a synthetic plan mutation using one fixed unattested seed.

    This constructs software negative controls only. Arm-dependent synthetic
    payloads move within each biological pair to the vector selected by the
    fixed seed; no seed is searched. This is not an acceptable operation on
    observed data or a real experiment.
    """

    plan = _json_loads(
        (dest / "assay_power.synthetic.json").read_text(encoding="utf-8")
    )
    exposure_path = dest / "measured_exposure_table.synthetic.json"
    exposure = _json_loads(exposure_path.read_text(encoding="utf-8"))
    lineage_path = dest / "lineage_count_table.synthetic.json"
    lineage = _json_loads(lineage_path.read_text(encoding="utf-8"))
    allocation = exposure["preexposure_allocation"]
    plan_encoded = json.dumps(
        plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    , allow_nan=False)
    allocation["assay_plan_sha256"] = hashlib.sha256(
        plan_encoded.encode("utf-8")
    ).hexdigest()
    allocation["analysis_plan_sha256"] = (
        make_allocation_analysis_plan_sha256()
    )
    allocation["assignment_input_commitment_sha256"] = (
        make_assignment_input_commitment(
            study_id=allocation["study_id"],
            assay_plan_sha256=allocation["assay_plan_sha256"],
            analysis_plan_sha256=allocation["analysis_plan_sha256"],
            assignment_method=allocation["assignment_method"],
            assignment_algorithm=allocation["assignment_algorithm"],
            allocation_unit=allocation["allocation_unit"],
            assignment_manifest=allocation["assignment_manifest"],
        )
    )
    allocation["assignment_input_commitment_record"]["digest_sha256"] = (
        allocation["assignment_input_commitment_sha256"]
    )
    _relabel_unattested_synthetic_fixture_to_seed(
        exposure=exposure,
        lineage=lineage,
    )
    _write_json(exposure_path, exposure)
    _write_json(lineage_path, lineage)
    _write_json(
        dest / "blinded_count_table.synthetic.json",
        blinded_from_lineage(lineage),
    )


def tick_replication(dest: Path) -> None:
    path = dest / "replication_decision.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    payload["endpoints_concordant"] = True
    _write_json(path, payload)


def set_missense_checkpoint(dest: Path, status: str) -> None:
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


def set_missense_specificity(dest: Path, specificity: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] == "missense":
            row["allele_specificity"] = specificity
    _write_json(path, payload)


def set_corrected_specificity(dest: Path, specificity: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] == "exact_corrected":
            row["allele_specificity"] = specificity
    _write_json(path, payload)


def set_corrected_assay_class(dest: Path, assay_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "exact_corrected":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "negative":
                item["assay_class"] = assay_class
                if assay_class == "wet":
                    item["system_class"] = "cellular"
                    item["condition_class"] = "basal"
                    item["expression_class"] = "endogenous"
                    item["specimen_class"] = "assay_matched"
    _write_json(path, payload)


def set_corrected_system_class(dest: Path, system_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "exact_corrected":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "negative":
                item["system_class"] = system_class
    _write_json(path, payload)


def set_corrected_condition_class(dest: Path, condition_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "exact_corrected":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "negative":
                item["condition_class"] = condition_class
    _write_json(path, payload)


def set_corrected_expression_class(dest: Path, expression_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "exact_corrected":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "negative":
                item["expression_class"] = expression_class
    _write_json(path, payload)


def set_corrected_specimen_class(dest: Path, specimen_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "exact_corrected":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "negative":
                item["specimen_class"] = specimen_class
    _write_json(path, payload)


def set_recreated_status(
    dest: Path,
    endpoints: set[str],
    status: str,
    assay_class: str = "wet",
) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "recreated_missense":
            continue
        for item in row["assessments"]:
            if item["endpoint"] in endpoints:
                item["assessment_status"] = status
                item["assay_class"] = assay_class
                if status == "positive" and assay_class == "wet":
                    item["condition_class"] = "basal"
                    item["system_class"] = "cellular"
                    item["expression_class"] = "endogenous"
                    item["specimen_class"] = "assay_matched"
    _write_json(path, payload)


def set_missense_condition_class(dest: Path, condition_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "missense":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "positive":
                item["condition_class"] = condition_class
    _write_json(path, payload)


def set_missense_system_class(dest: Path, system_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "missense":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "positive":
                item["system_class"] = system_class
    _write_json(path, payload)


def set_missense_expression_class(dest: Path, expression_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "missense":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "positive":
                item["expression_class"] = expression_class
    _write_json(path, payload)


def set_missense_specimen_class(dest: Path, specimen_class: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != "missense":
            continue
        for item in row["assessments"]:
            if item.get("assessment_status") == "positive":
                item["specimen_class"] = specimen_class
    _write_json(path, payload)


def add_missense_pd(dest: Path, endpoint: str, status: str) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] == "missense":
            row["assessments"].append(
                {
                    "endpoint": endpoint,
                    "assessment_status": status,
                    "assay_class": "wet",
                }
            )
    _write_json(path, payload)


def set_carrier_endpoint(
    dest: Path, genotype_class: str, endpoint: str, status: str
) -> None:
    path = dest / "allele_function_scorecard.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["genotype_class"] != genotype_class:
            continue
        for item in row["assessments"]:
            if item["endpoint"] == endpoint:
                item["assessment_status"] = status
                item["assay_class"] = "wet"
                item["condition_class"] = "basal"
                item["system_class"] = "cellular"
                item["expression_class"] = "endogenous"
                item["specimen_class"] = "assay_matched"
    _write_json(path, payload)


def write_child_claim_ready(dest: Path) -> None:
    path = dest / "observed_inferred_unknown.synthetic.json"
    evidence = _json_loads(path.read_text(encoding="utf-8"))
    _write_json(path, mark_pair_program_observed(evidence))


def declare_next_gate(dest: Path, gate_id: str) -> None:
    path = dest / "causal_chain_worksheet.synthetic.json"
    payload = _json_loads(path.read_text(encoding="utf-8"))
    payload["declared_next_gate_id"] = gate_id
    _write_json(path, payload)


def _prepare_reachable(dest: Path) -> None:
    write_passing_confirmation(dest)
    write_passing_transcript(dest)
    write_passing_power(dest)
    write_aligned_counts(dest)
    tick_replication(dest)
    set_missense_checkpoint(dest, "positive")
    write_child_claim_ready(dest)


def _earliest_nonpass(result: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    for item in result.get("steps") or []:
        if not isinstance(item, dict) or item.get("skipped"):
            continue
        if item.get("program_effect") != "pass":
            return (
                str(item.get("name")),
                str(item.get("program_effect")),
                item.get("reason"),
            )
    return result.get("blocked_by"), result.get("decision"), result.get("block_reason")


def _scenario_result(
    name: str,
    kind: str,
    *,
    decision: str,
    blocked_by: str | None,
    block_reason: str | None,
    earliest_nonpass_gate: str | None = None,
    earliest_nonpass_effect: str | None = None,
    earliest_nonpass_reason: str | None = None,
) -> dict[str, Any]:
    opened = kind == "true_path" and decision == "advance" and blocked_by is None
    # A false path carrying an explicit blocker is never 'open', even if a
    # tampered upstream value lets it keep decision='advance' on the row.
    blocked_from_advancing = kind == "false_path" and (
        decision != "advance" or blocked_by is not None
    )
    return {
        "name": name,
        "kind": kind,
        "decision": decision,
        "blocked_by": blocked_by,
        "block_reason": block_reason,
        "earliest_nonpass_gate": earliest_nonpass_gate or blocked_by,
        "earliest_nonpass_effect": earliest_nonpass_effect,
        "earliest_nonpass_reason": earliest_nonpass_reason or block_reason,
        "opened": opened,
        "blocked_from_advancing": blocked_from_advancing,
    }


def _toolkit_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _run_mutated(name: str, kind: str, mutate) -> dict[str, Any]:
    with TemporaryDirectory() as folder:
        dest = _copy_toolkit(Path(folder))
        mutate(dest)
        digest = _toolkit_digest(dest)
        try:
            result = run_community_pipeline(dest)
        except Exception as exc:
            # A malformed toolkit must fail closed — a domain error raise is
            # a blocked outcome too, recorded with the error class so the
            # raise-path surface is covered as named scenarios.
            outcome = _scenario_result(
                name,
                kind,
                decision=f"error:{type(exc).__name__}",
                blocked_by=None,
                block_reason=f"raised:{type(exc).__name__}",
            )
            outcome["toolkit_digest"] = digest
            outcome["error_type"] = type(exc).__name__
            gc.collect()
            return outcome
    gate, effect, reason = _earliest_nonpass(result)
    outcome = _scenario_result(
        name,
        kind,
        decision=str(result["decision"]),
        blocked_by=result.get("blocked_by"),
        block_reason=result.get("block_reason"),
        earliest_nonpass_gate=gate,
        earliest_nonpass_effect=effect,
        earliest_nonpass_reason=reason,
    )
    outcome["toolkit_digest"] = digest
    gc.collect()
    return outcome


def run_save_path_suite() -> dict[str, Any]:
    """Run one reachable path and the false stories that must not open it."""

    ranking_table = _json_loads(
        (COMMUNITY / "structure_ranking.synthetic.json").read_text(encoding="utf-8")
    )
    ranking = assess_structure_ranking(ranking_table)

    def reachable(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")

    def incomplete_confirmation(dest: Path) -> None:
        return

    def cis_pair(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["decision"] = "cis_confirmed"
        for guide in payload["guide_configurations"]:
            guide["linkage_call"] = "cis"
        _write_json(path, payload)

    def linkage_missing(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for guide in payload["guide_configurations"]:
            guide.pop("linkage_call", None)
        _write_json(path, payload)

    def computational_phase(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["phase_method"] = "computational"
        _write_json(path, payload)

    def unmatched_phase_specimen(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["phase_specimen"] = "unmatched"
        _write_json(path, payload)

    def analog_as_function(dest: Path) -> None:
        _prepare_reachable(dest)
        set_missense_specificity(dest, "analog")

    def analog_correction(dest: Path) -> None:
        _prepare_reachable(dest)
        set_corrected_specificity(dest, "analog")

    def heat_shock_pd(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        write_aligned_counts(dest)
        tick_replication(dest)
        write_child_claim_ready(dest)
        add_missense_pd(dest, "chaperone_pd", "positive")

    def competing_risk(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        write_aligned_counts(dest, competing=True)
        tick_replication(dest)
        set_missense_checkpoint(dest, "positive")
        write_child_claim_ready(dest)

    def unlinked_confirmation(dest: Path) -> None:
        payload = passing_confirmation()
        payload["producer"] = "unlinked"
        _write_json(dest / "confirmation_record.synthetic.json", payload)

    def incomplete_transcript(dest: Path) -> None:
        write_passing_confirmation(dest)

    def computational_transcript(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "transcript_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["transcript_method"] = "computational"
        _write_json(path, payload)

    def unmatched_transcript_specimen(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "transcript_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["transcript_specimen"] = "unmatched"
        _write_json(path, payload)

    def probe_before_identity(dest: Path) -> None:
        path = dest / "causal_chain_worksheet.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["declared_next_gate_id"] = "syn-gate-replication"
        _write_json(path, payload)

    def later_identity_before_confirmation(dest: Path) -> None:
        path = dest / "causal_chain_worksheet.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["declared_next_gate_id"] = "syn-gate-phase"
        _write_json(path, payload)

    def imaging_before_assay(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        path = dest / "allele_function_scorecard.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assessment_status"] = "not_assessable"
        _write_json(path, payload)
        worksheet = dest / "causal_chain_worksheet.synthetic.json"
        declared = _json_loads(worksheet.read_text(encoding="utf-8"))
        declared["declared_next_gate_id"] = "syn-gate-replication"
        _write_json(worksheet, declared)

    def checkpoint_not_assayed(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        write_aligned_counts(dest)
        write_passing_power(dest)
        tick_replication(dest)

    def checkpoint_negative(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        set_missense_checkpoint(dest, "negative")

    def unmanufacturable_window(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "assay_power.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["remaining_population_doublings"] = 1
        _write_json(path, payload)
        rebind_allocation_to_current_plan(dest)

    def bulk_fraction_endpoint(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "assay_power.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["success_rule"] = "bulk_aneuploid_drop"
        _write_json(path, payload)
        exposure_path = dest / "measured_exposure_table.synthetic.json"
        exposure = _json_loads(exposure_path.read_text(encoding="utf-8"))
        exposure["success_rule"] = "bulk_aneuploid_drop"
        _write_json(exposure_path, exposure)
        rebind_allocation_to_current_plan(dest)

    def kmer_without_nest(dest: Path) -> None:
        payload = passing_confirmation()
        payload["producer"] = "kmer_layout"
        payload["layout_digest"] = PINNED_FASTQ_NAME_DIGEST
        _write_json(dest / "confirmation_record.synthetic.json", payload)

    def kmer_without_file_layout(dest: Path) -> None:
        payload = passing_confirmation()
        payload["producer"] = "kmer_layout"
        payload["layout_digest"] = PINNED_FASTQ_NAME_DIGEST
        payload["kmer_confirmation"] = _ticked_kmer_confirmation()
        payload["layout"] = {
            "n_files": 5,
            "expected_n_files": 8,
            "incomplete": True,
            "name_digest": PINNED_FASTQ_NAME_DIGEST,
            "reasons": ["fewer_files_than_expected"],
        }
        _write_json(dest / "confirmation_record.synthetic.json", payload)

    def rna_confirmation(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "confirmation_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["library_molecule"] = "rna"
        _write_json(path, payload)

    def unmatched_confirmation_specimen(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "confirmation_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["confirmation_specimen"] = "unmatched"
        _write_json(path, payload)

    def nontranslational_exposure(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["rows"].append(
            {
                "nominal_uM": 100.0,
                "unbound_medium_uM": 80.0,
                "intracellular_parent": 40.0,
                "time_hours": 24,
                "pulse_vs_constant": "constant",
                "washout": False,
                "measurement_class": "culture_measured",
            }
        )
        _write_json(path, payload)

    def missing_exposure_duration(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            row.pop("time_hours", None)
        _write_json(path, payload)

    def pulse_only_exposure(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["rows"] = [
            row for row in payload["rows"] if row.get("pulse_vs_constant") == "pulse"
        ]
        _write_json(path, payload)

    def aminoglycoside_carryover(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row.get("pulse_vs_constant") == "constant":
                row["selection_agent_cleared"] = False
        _write_json(path, payload)

    def selection_agent_unlabeled(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            row.pop("selection_agent", None)
            row.pop("selection_agent_cleared", None)
            row.pop("selection_clearance_method", None)
        _write_json(path, payload)

    def selection_batch_taint(dest: Path) -> None:
        # The linked row claims cleared aminoglycoside with a declared
        # method — but a sibling row sharing its culture_batch_id admits
        # the batch was never cleared. The antibiotic lives in the medium:
        # one honest sibling voids the clearance claim on every row in the
        # batch, the linked row loses its qualifying window, and the
        # count-identity gate reports the execution unsupported.
        _prepare_reachable(dest)
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row.get("pulse_vs_constant") == "pulse":
                row["culture_batch_id"] = "syn-batch-a"
                row["selection_agent"] = "aminoglycoside"
                row["selection_agent_cleared"] = False
                row["selection_clearance_method"] = None
        _write_json(path, payload)

    def discordant_exposure(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["rows"].append(
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.7,
                "intracellular_parent": 0.0,
                "time_hours": 24,
                "pulse_vs_constant": "constant",
                "washout": False,
                "measurement_class": "culture_measured",
            }
        )
        _write_json(path, payload)

    def exposure_assay_file_collage(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "lineage_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        treatment = next(row for row in payload["runs"] if row["arm"] == "treatment")
        treatment["functional_execution_id"] = "syn-functional-unrelated"
        _write_json(path, payload)

    def _commit_allocation_mutation(
        dest: Path, exposure: dict[str, Any]
    ) -> None:
        allocation = exposure["preexposure_allocation"]
        allocation["assignment_input_commitment_sha256"] = (
            make_assignment_input_commitment(
                study_id=allocation["study_id"],
                assay_plan_sha256=allocation["assay_plan_sha256"],
                assignment_method=allocation["assignment_method"],
                assignment_algorithm=allocation["assignment_algorithm"],
                functional_execution_ids=[
                    item["functional_execution_id"]
                    for item in allocation["assignments"]
                ],
            )
        )
        allocation_id = make_preexposure_allocation_id(allocation)
        allocation["allocation_id"] = allocation_id
        allocation["commitment"]["plan_sha256"] = allocation_id.removeprefix(
            "allocation-"
        )
        _write_json(dest / "measured_exposure_table.synthetic.json", exposure)

        lineage_path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(lineage_path.read_text(encoding="utf-8"))
        lineage["allocation_id"] = allocation_id
        assignment_index = {
            item["functional_execution_id"]: item
            for item in allocation["assignments"]
        }
        for row in lineage["runs"]:
            assignment = assignment_index[row["functional_execution_id"]]
            row["run_id"] = assignment["functional_assay_run_id"]
            row["batch_id"] = assignment["culture_batch_id"]
            for field in (
                "allocation_block_id",
                "functional_assay_plate_id",
                "plate_row",
                "plate_column",
                "dosing_order",
                "acquisition_order",
            ):
                row[field] = assignment[field]
        _write_json(lineage_path, lineage)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(lineage),
        )

    def arm_position_confounding(dest: Path) -> None:
        _prepare_reachable(dest)
        exposure_path = dest / "measured_exposure_table.synthetic.json"
        exposure = _json_loads(exposure_path.read_text(encoding="utf-8"))
        allocation = exposure["preexposure_allocation"]
        by_arm = {"vehicle": [], "treatment": []}
        for assignment in allocation["assignments"]:
            by_arm[assignment["arm"]].append(assignment)
        for index, assignment in enumerate(
            sorted(
                by_arm["vehicle"],
                key=lambda item: item["functional_execution_id"],
            ),
            start=1,
        ):
            assignment["plate_row"] = 1
            assignment["plate_column"] = index
        for index, assignment in enumerate(
            sorted(
                by_arm["treatment"],
                key=lambda item: item["functional_execution_id"],
            ),
            start=2,
        ):
            assignment["plate_row"] = 2
            assignment["plate_column"] = index
        _commit_allocation_mutation(dest, exposure)

    def arm_exact_column_gradient(dest: Path) -> None:
        _prepare_reachable(dest)
        exposure = _json_loads(
            (dest / "measured_exposure_table.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        allocation = exposure["preexposure_allocation"]
        allocation["plate_dimensions"][0]["n_rows"] = 32
        pairs: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for item in allocation["assignments"]:
            key = (
                item["edit_event_id"],
                item["clone_id"],
                item["functional_assay_run_id"],
            )
            pairs.setdefault(key, []).append(item)
        for plate_row, items in enumerate(
            (items for _key, items in sorted(pairs.items())), start=2
        ):
            for item in items:
                item["plate_row"] = plate_row
                item["plate_column"] = 2 if item["arm"] == "vehicle" else 8
        _commit_allocation_mutation(dest, exposure)

    def arm_row_half_interaction(dest: Path) -> None:
        _prepare_reachable(dest)
        exposure = _json_loads(
            (dest / "measured_exposure_table.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        allocation = exposure["preexposure_allocation"]
        allocation["plate_dimensions"][0]["n_rows"] = 32
        pairs: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for item in allocation["assignments"]:
            key = (
                item["edit_event_id"],
                item["clone_id"],
                item["functional_assay_run_id"],
            )
            pairs.setdefault(key, []).append(item)
        for pair_number, (key, items) in enumerate(sorted(pairs.items()), start=1):
            within_run = 1 if pair_number % 2 else 2
            for item in items:
                item["allocation_block_id"] = f"syn-interaction-{key[2]}"
                item["plate_row"] = pair_number + 1
                if within_run == 1:
                    item["plate_column"] = (
                        2 if item["arm"] == "vehicle" else 14
                    )
                else:
                    item["plate_column"] = (
                        16 if item["arm"] == "vehicle" else 4
                    )
        _commit_allocation_mutation(dest, exposure)

    def arm_event_order_alias(dest: Path) -> None:
        _prepare_reachable(dest)
        exposure = _json_loads(
            (dest / "measured_exposure_table.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        allocation = exposure["preexposure_allocation"]
        for row in exposure["rows"]:
            if row.get("supports_functional_execution_ids"):
                row["functional_assay_run_ids"] = ["syn-run-1"]
        for control in exposure["vehicle_controls"]:
            control["functional_assay_run_ids"] = ["syn-run-1"]
        pairs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in allocation["assignments"]:
            item["functional_assay_run_id"] = "syn-run-1"
            pairs.setdefault(
                (item["edit_event_id"], item["clone_id"]), []
            ).append(item)
        order = 0
        event_ids = sorted({event_id for event_id, _clone_id in pairs})
        for event_number, event_id in enumerate(event_ids):
            event_pairs = [
                items for key, items in sorted(pairs.items()) if key[0] == event_id
            ]
            for pair_number, items in enumerate(event_pairs):
                if event_number == 0:
                    first_arm = "vehicle"
                elif event_number == 1:
                    first_arm = "treatment"
                else:
                    first_arm = "vehicle" if pair_number == 0 else "treatment"
                second_arm = "treatment" if first_arm == "vehicle" else "vehicle"
                by_arm = {item["arm"]: item for item in items}
                for arm in (first_arm, second_arm):
                    order += 1
                    by_arm[arm]["dosing_order"] = order
                    by_arm[arm]["acquisition_order"] = order
        _commit_allocation_mutation(dest, exposure)

    def arm_local_quadratic_order_artifact(dest: Path) -> None:
        """Make the endpoint follow local order curvature, not treatment."""

        _prepare_reachable(dest)
        lineage_path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(lineage_path.read_text(encoding="utf-8"))
        by_context: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in lineage["runs"]:
            context = (
                row["functional_assay_plate_id"],
                row["batch_id"],
                row["run_id"],
                row["edit_event_id"],
            )
            by_context.setdefault(context, []).append(row)
        for context_number, (_context, rows_in_context) in enumerate(
            sorted(by_context.items()), start=1
        ):
            dosing_mean = sum(
                int(row["dosing_order"]) for row in rows_in_context
            ) / len(rows_in_context)
            acquisition_mean = sum(
                int(row["acquisition_order"]) for row in rows_in_context
            ) / len(rows_in_context)
            curves = {
                str(row["functional_execution_id"]): round(
                    (
                        (int(row["dosing_order"]) - dosing_mean) ** 2
                        + (int(row["acquisition_order"]) - acquisition_mean)
                        ** 2
                    )
                    / 2
                )
                for row in rows_in_context
            }
            curve_ceiling = max(curves.values())
            for row in rows_in_context:
                errors = curves[str(row["functional_execution_id"])]
                # The sign is fixed by arm-free context order, never by the
                # realized labels. Reversing every third context keeps this a
                # context-specific quadratic nuisance surface while making the
                # frozen synthetic schedule directionally treatment-favouring;
                # the exact residualized test must still reject the story.
                if context_number % 3 == 0:
                    errors = curve_ceiling - errors
                row["event_positive_divisions"] = errors
                row["event_negative_divisions"] = (
                    int(row["detected_divisions"]) - errors
                )
                row["event_positive_daughters_followed"] = 0
                row["event_positive_daughters_reproduced"] = 0
                row["event_positive_daughters_died"] = 0
                row["event_negative_daughters_followed"] = 0
                row["event_negative_daughters_reproduced"] = 0
                row["event_negative_daughters_died"] = 0
        _write_json(lineage_path, lineage)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(lineage),
        )

    def arm_local_order_interaction_artifact(dest: Path) -> None:
        """Make the endpoint follow dosing-by-acquisition order, not treatment."""

        _prepare_reachable(dest)
        lineage_path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(lineage_path.read_text(encoding="utf-8"))
        by_context: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in lineage["runs"]:
            context = (
                row["functional_assay_plate_id"],
                row["batch_id"],
                row["run_id"],
                row["edit_event_id"],
            )
            by_context.setdefault(context, []).append(row)
        for context_number, (_context, rows_in_context) in enumerate(
            sorted(by_context.items()), start=1
        ):
            dosing_mean = sum(
                int(row["dosing_order"]) for row in rows_in_context
            ) / len(rows_in_context)
            acquisition_mean = sum(
                int(row["acquisition_order"]) for row in rows_in_context
            ) / len(rows_in_context)
            interactions = {
                str(row["functional_execution_id"]): int(
                    round(
                        (int(row["dosing_order"]) - dosing_mean)
                        * (int(row["acquisition_order"]) - acquisition_mean)
                        + 3.75
                    )
                )
                for row in rows_in_context
            }
            interaction_ceiling = max(interactions.values())
            for row in rows_in_context:
                # For the committed six-pair synthetic schedule this shifted
                # cross-product is an integer in [0, 34]. It creates a raw
                # treatment-favouring contrast even though the outcome is a
                # function of arm-free order covariates only.
                errors = interactions[str(row["functional_execution_id"])]
                if context_number % 3 == 0:
                    errors = interaction_ceiling - errors
                row["event_positive_divisions"] = errors
                row["event_negative_divisions"] = (
                    int(row["detected_divisions"]) - errors
                )
                row["event_positive_daughters_followed"] = 0
                row["event_positive_daughters_reproduced"] = 0
                row["event_positive_daughters_died"] = 0
                # The interaction can leave as few as two negative divisions;
                # remove daughter follow-up payloads so this arm-free artifact
                # remains a valid observed-run fixture and reaches inference.
                row["event_negative_daughters_followed"] = 0
                row["event_negative_daughters_reproduced"] = 0
                row["event_negative_daughters_died"] = 0
        _write_json(lineage_path, lineage)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(lineage),
        )

    def ranking_cannot_open_checkpoint(dest: Path) -> None:
        # A forged checkpoint_ready claim in the ranking table must not open
        # the checkpoint — the scorecard gate still has to measure it.
        _prepare_reachable(dest)
        set_missense_checkpoint(dest, "negative")
        path = dest / "structure_ranking.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["checkpoint_ready"] = True
        _write_json(path, payload)

    def family_overclaim(dest: Path) -> None:
        path = dest / "family_plain_language.synthetic.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("not a cure.", "not a cure. Checkpoint rescued."),
            encoding="utf-8",
        )

    def dropout_compatible_phase(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        # haplotype_b strictly below the full-span floor — an at-floor count
        # would still meet the inclusive minimum and not exercise this family.
        payload["molecule_counts"]["minimum_full_span_per_haplotype"] = 8
        payload["molecule_counts"]["haplotype_a_full_span"] = 100
        payload["molecule_counts"]["haplotype_b_full_span"] = 4
        _write_json(path, payload)

    def strand_imbalance_phase(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["guide_configurations"][0]["strand_balance"] = 0.95
        _write_json(path, payload)

    def unlocked_power_plan(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "assay_power.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["locked"] = False
        _write_json(path, payload)
        rebind_allocation_to_current_plan(dest)

    def underpowered_plan(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "assay_power.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["n_opportunities"] = 1
        _write_json(path, payload)
        rebind_allocation_to_current_plan(dest)

    def missing_falsifier(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"] = [
            link for link in evidence["links"] if link["hypothesis_role"] != "falsifier"
        ]
        _write_json(path, evidence)

    def observed_falsifier(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["status"] = "observed"
        _write_json(path, evidence)

    def unmeasured_rna_child_claim(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "transcript":
                link["status"] = "unknown"
        _write_json(path, evidence)

    def bulk_aneuploidy_rescue(dest: Path) -> None:
        # Reach the hypothesis gate — a bulk-fraction endpoint appended to a
        # fully passing toolkit must still be blocked there.
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"].append(
            {
                "link_id": "syn-link-bulk-aneuploidy",
                "hypothesis_role": "endpoint",
                "statement": "The treated culture had fewer aneuploid cells.",
                "status": "observed",
                "supports": "lower aneuploidy is rescue",
                "does_not_support": "nothing",
            }
        )
        _write_json(path, evidence)

    def missing_alternative(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"] = [
            link for link in evidence["links"] if link["hypothesis_role"] != "alternative"
        ]
        _write_json(path, evidence)

    def observed_alternative(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "alternative":
                link["status"] = "observed"
        _write_json(path, evidence)

    def observed_without_gate(dest: Path) -> None:
        # Everything except the confirmation gate is ready — the block must
        # land on confirmation specifically, not on an earlier default gap.
        _prepare_reachable(dest)
        write_child_claim_ready(dest)
        (dest / "confirmation_record.synthetic.json").write_text(
            (COMMUNITY / "confirmation_record.synthetic.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )

    def missing_controls(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"] = [
            link
            for link in evidence["links"]
            if link["hypothesis_role"] not in {"positive_control", "negative_control"}
        ]
        _write_json(path, evidence)

    def control_failed(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "positive_control":
                link["status"] = "observed"
                link["supports"] = "positive control failed"
        _write_json(path, evidence)

    def observed_stability_without_assay(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "allele_function_scorecard.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assessment_status"] = "not_assessable"
        _write_json(path, payload)

    def pediatric_crash_plan(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "assay_power.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["locked_treatment_completion_rate"] = 0.5
        _write_json(path, payload)
        rebind_allocation_to_current_plan(dest)

    def observed_endpoint_without_concordance(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["status"] = "observed"
        _write_json(path, evidence)
        counts = dest / "lineage_count_table.synthetic.json"
        payload = _json_loads(counts.read_text(encoding="utf-8"))
        payload["lock_state"] = "unlocked"
        _write_json(counts, payload)

    def missing_multiplicity(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"] = [
            link for link in evidence["links"] if link["hypothesis_role"] != "multiplicity"
        ]
        _write_json(path, evidence)

    def missing_counterscreen(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"] = [
            link
            for link in evidence["links"]
            if link["hypothesis_role"] != "counterscreen"
        ]
        _write_json(path, evidence)

    def missing_evidence_chain(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"] = [
            link
            for link in evidence["links"]
            if link["hypothesis_role"] not in {"pair", "stability", "transcript"}
        ]
        _write_json(path, evidence)

    def supports_donation_falsifier(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = "The experimental condition is considered."
                link["supports"] = (
                    "if isogenic rna stops selection predeclared 50 fold "
                    "threshold exact corrected"
                )
        _write_json(path, evidence)

    def unwatched_falsifier(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "falsifier":
                link.pop("watches", None)
        _write_json(path, evidence)

    def unwatched_endpoint(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "endpoint":
                link.pop("watches", None)
        _write_json(path, evidence)

    def unwatched_alternative(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "alternative":
                link.pop("watches", None)
        _write_json(path, evidence)

    def unwatched_probe_chain(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "probe":
                link.pop("watches", None)
        _write_json(path, evidence)

    def watch_cycle(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["watches"] = ["syn-link-probe", "syn-link-falsifier"]
        _write_json(path, evidence)

    def endpoint_unkilled(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"].append(
            {
                "link_id": "syn-link-segregation-2",
                "hypothesis_role": "endpoint",
                "statement": (
                    "A second lineage outcome: the treated compound "
                    "genotype increases first-division segregation errors "
                    "versus the exact-corrected row at a predeclared "
                    "3-fold bound."
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
        )
        _write_json(path, evidence)

    def endpoint_uncontrolled(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"].append(
            {
                "link_id": "syn-link-segregation-2",
                "hypothesis_role": "endpoint",
                "statement": (
                    "A second lineage outcome: the treated compound "
                    "genotype increases first-division segregation errors "
                    "versus the exact-corrected row at a predeclared "
                    "3-fold bound."
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
        )
        evidence["links"].append(
            {
                "link_id": "syn-link-falsifier-2",
                "hypothesis_role": "falsifier",
                "statement": (
                    "Under the predeclared rule: if the second endpoint "
                    "does not return within 3-fold of the exact-corrected "
                    "baseline, or cytostasis, selection, death masking, "
                    "batch drift, or interference accounts for the gain, "
                    "the pair program stops."
                ),
                "status": "hypothesis",
                "supports": "second kill rule",
                "does_not_support": "child claim",
                "watches": ["syn-link-segregation-2"],
                "bound": 3.0,
            }
        )
        evidence["links"].append(
            {
                "link_id": "syn-link-positive-control-2",
                "hypothesis_role": "positive_control",
                "statement": (
                    "The exact-corrected row is the positive control on "
                    "the same protocol for the second endpoint."
                ),
                "status": "planned_experiment",
                "supports": "exact-correction comparator",
                "does_not_support": "child claim",
                "watches": ["syn-link-segregation-2"],
            }
        )
        _write_json(path, evidence)

    def probe_unscreened(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"].append(
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
        _write_json(path, evidence)

    def multiplicity_family_uncovered(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"].append(
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
        for link in evidence["links"]:
            if link["hypothesis_role"] == "counterscreen":
                link["watches"] = ["syn-link-probe", "syn-link-probe-2"]
        _write_json(path, evidence)

    def vacuous_second_endpoint(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"].append(
            {
                "link_id": "syn-link-segregation-2",
                "hypothesis_role": "endpoint",
                "statement": "A second outcome is recorded for the study.",
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
        )
        for link in evidence["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["watches"].append("syn-link-segregation-2")
            if link["hypothesis_role"] in {
                "positive_control",
                "negative_control",
            }:
                link["watches"].append("syn-link-segregation-2")
            if link["hypothesis_role"] == "multiplicity":
                link["watches"].append("syn-link-segregation-2")
        _write_json(path, evidence)

    def endpoint_wrong_comparator(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["spec"]["control_arm"] = "vehicle-treated"
        _write_json(path, evidence)

    def endpoint_unblinded(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "endpoint":
                link["spec"]["blinded"] = False
        _write_json(path, evidence)

    def endpoint_without_spec(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "endpoint":
                link.pop("spec", None)
        _write_json(path, evidence)

    def falsifier_bound_unequal(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["bound"] = 7.0
        _write_json(path, evidence)

    def multiplicity_without_alpha(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "multiplicity":
                link["statement"] = link["statement"].replace(
                    "alpha 0.05", "a familywise rule"
                )
        _write_json(path, evidence)

    def unanchored_kill_bound(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link["hypothesis_role"] == "falsifier":
                link["statement"] = link["statement"].replace("2-fold", "7-fold")
        _write_json(path, evidence)

    def fitter_error_daughters(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "lineage_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["runs"]:
            if row["arm"] == "treatment":
                # Fully resolved stratum (6+2 = 8 slots) with a 0.75
                # reproduction rate against the vehicle 0.5 — the 1.5x
                # fitness gain must stop at the ratio check.
                row["event_positive_daughters_reproduced"] = 6
                row["event_positive_daughters_died"] = 2
        _write_json(path, payload)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(payload),
        )

    def event_negative_daughter_viability(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "lineage_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["runs"]:
            row["event_negative_daughters_followed"] = 8
            if row["arm"] == "vehicle":
                row["event_negative_daughters_reproduced"] = 8
                row["event_negative_daughters_died"] = 0
            else:
                row["event_negative_daughters_reproduced"] = 0
                row["event_negative_daughters_died"] = 8
        _write_json(path, payload)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(payload),
        )

    def multipolar_daughters_unfollowed(dest: Path) -> None:
        # A declared multipolar division widens the slot obligation to 9;
        # only the bipolar default of 8 daughters is resolved, so the third
        # multipolar daughter is unaccounted — the completeness check must
        # hold rather than let an error daughter slip the follow-up net.
        _prepare_reachable(dest)
        path = dest / "lineage_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["runs"]:
            if row["arm"] == "treatment":
                row["event_positive_multipolar_divisions"] = 1
                row["event_positive_daughter_slots"] = (
                    2 * row["event_positive_divisions"] + 1
                )
        _write_json(path, payload)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(payload),
        )

    def censored_daughters_dilute(dest: Path) -> None:
        # Daughters reported as followed but never resolved to a terminal
        # fate are unaccounted progeny: they cannot satisfy the follow-up
        # obligation, and they must not dilute the reproduction rate. The
        # declared gap between followed and resolved is the censoring.
        _prepare_reachable(dest)
        path = dest / "lineage_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["runs"]:
            if row["arm"] == "treatment":
                # Ten daughters were observed (one multipolar division
                # declared, slots widened to 10) but only eight carry a
                # resolved fate — the censored two cannot satisfy the
                # completeness obligation.
                row["event_positive_daughters_followed"] = 10
                row["event_positive_multipolar_divisions"] = 1
                row["event_positive_daughter_slots"] = 10
        _write_json(path, payload)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(payload),
        )

    def computational_stability(dest: Path) -> None:
        _prepare_reachable(dest)
        path = dest / "allele_function_scorecard.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["genotype_class"] != "missense":
                continue
            for item in row["assessments"]:
                if item["endpoint"] in {"abundance", "half_life"}:
                    item["assay_class"] = "computational_structure"
        _write_json(path, payload)

    def computational_correction(dest: Path) -> None:
        _prepare_reachable(dest)
        set_corrected_assay_class(dest, "computational_structure")

    def failed_reciprocal_recreation(dest: Path) -> None:
        _prepare_reachable(dest)
        set_recreated_status(dest, {"abundance", "half_life"}, "negative")

    def imposed_extrinsic_stress(dest: Path) -> None:
        _prepare_reachable(dest)
        set_missense_condition_class(dest, "imposed_extrinsic_stress")

    def cell_free_biophysical(dest: Path) -> None:
        _prepare_reachable(dest)
        set_missense_system_class(dest, "cell_free_biophysical")

    def cell_free_correction(dest: Path) -> None:
        _prepare_reachable(dest)
        set_corrected_system_class(dest, "cell_free_biophysical")

    def imposed_stress_correction(dest: Path) -> None:
        _prepare_reachable(dest)
        set_corrected_condition_class(dest, "imposed_extrinsic_stress")

    def ectopic_expression(dest: Path) -> None:
        _prepare_reachable(dest)
        set_missense_expression_class(dest, "ectopic")

    def ectopic_correction(dest: Path) -> None:
        _prepare_reachable(dest)
        set_corrected_expression_class(dest, "ectopic")

    def unmatched_correction(dest: Path) -> None:
        _prepare_reachable(dest)
        set_corrected_specimen_class(dest, "unmatched")

    def unmatched_assay_specimen(dest: Path) -> None:
        _prepare_reachable(dest)
        set_missense_specimen_class(dest, "unmatched")

    def organ_size(dest: Path) -> None:
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        evidence["links"].append(
            {
                "link_id": "syn-link-organ-size",
                "hypothesis_role": "endpoint",
                "statement": "Organ size restored after the probe.",
                "status": "observed",
                "supports": "checkpoint rescued",
                "does_not_support": "nothing",
            }
        )
        _write_json(path, evidence)

    def predicted_stability_as_function(dest: Path) -> None:
        path = dest / "structure_ranking.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["used_as_function"] = True
        _write_json(path, payload)

    def blinded_table_tampered(dest: Path) -> None:
        # The blinded table is hand-edited without regenerating it from the
        # lineage counts — the two tables must disagree. Swapping the whole
        # per-arm count tuple between the two rows keeps each row internally
        # consistent (followed stays within two daughters per division) so
        # the disagreement surfaces at count_tables_inconsistent rather than
        # row validation.
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "blinded_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        runs = payload["runs"]
        vehicle_row = next(row for row in runs if row["arm"] == "vehicle")
        treatment_row = next(row for row in runs if row["arm"] == "treatment")
        for field in (
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
        ):
            vehicle_row[field], treatment_row[field] = (
                treatment_row[field],
                vehicle_row[field],
            )
        _write_json(path, payload)

    def blinded_row_dropped(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "blinded_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["runs"].pop()
        _write_json(path, payload)

    def single_flat_clone(dest: Path) -> None:
        # One clone's treatment arm matches its own vehicle arm — pooled
        # inference still clears, but the per-clone concordance gate must
        # refuse to let a flat clone ride on the others.
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(path.read_text(encoding="utf-8"))
        target_clone = "syn-clone-1-6"
        for row in lineage["runs"]:
            if row["clone_id"] == target_clone and row["arm"] == "treatment":
                row["event_positive_divisions"] = 12
                row["event_negative_divisions"] = 24
                row["event_positive_daughters_followed"] = 24
                row["event_positive_daughters_reproduced"] = 12
                row["event_positive_daughters_died"] = 12
        _write_json(path, lineage)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(lineage),
        )

    def replication_declared_discordant(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "replication_decision.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["endpoints_concordant"] = False
        _write_json(path, payload)

    def replication_same_site(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "replication_decision.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["originating_site_id"] = payload["site_id"]
        _write_json(path, payload)

    def replication_declared_exposure_failed(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "replication_decision.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["exposure_gate_passed"] = False
        _write_json(path, payload)

    def unknown_next_gate(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-bogus")

    def endpoint_negated_comparator(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "observed_inferred_unknown.synthetic.json"
        evidence = _json_loads(path.read_text(encoding="utf-8"))
        for link in evidence["links"]:
            if link.get("hypothesis_role") == "endpoint":
                link["spec"]["control_arm"] = "uncorrected isogenic arm"
        _write_json(path, evidence)

    def blinded_duplicate_keys(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "blinded_count_table.synthetic.json"
        text = path.read_text(encoding="utf-8")
        # Inject a duplicated key — the loader must reject, not last-win.
        text = text.replace(
            '"privacy_class": "synthetic",',
            '"privacy_class": "synthetic",\n  "privacy_class": "synthetic",',
            1,
        )
        path.write_text(text, encoding="utf-8")

    def blinded_negative_shared_count(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "blinded_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["runs"][0]["opportunities"] = -1
        _write_json(path, payload)

    def dropped_clone_caught_by_binding(dest: Path) -> None:
        # A whole clone's runs are dropped from the count tables while the
        # exposure table still references them. The realized lineage no longer
        # meets the locked plan's depth, but the exposure-execution binding —
        # which enumerates the committed run set — catches the shrinkage one
        # gate earlier: a quietly reduced realized set cannot slip through.
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(path.read_text(encoding="utf-8"))
        lineage["runs"] = [
            row
            for row in lineage["runs"]
            if row["clone_id"] != "syn-clone-1-6"
        ]
        _write_json(path, lineage)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(lineage),
        )

    def vehicle_baseline_missing(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["vehicle_controls"] = []
        _write_json(path, payload)

    def missense_not_expressed(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        path = dest / "transcript_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["missense_allele_rna"] = "not_expressed"
        _write_json(path, payload)

    def protein_not_transcript(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        path = dest / "transcript_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["transcript_method"] = "protein_surrogate"
        _write_json(path, payload)

    def stop_transcript_persists(dest: Path) -> None:
        write_passing_confirmation(dest)
        write_passing_transcript(dest)
        path = dest / "transcript_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["stop_allele_rna"] = "expressed"
        _write_json(path, payload)

    def linkage_disagreement(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["guide_configurations"][1]["linkage_call"] = "cis"
        _write_json(path, payload)

    def need_two_guide_configurations(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["guide_configurations"].pop()
        _write_json(path, payload)

    def guide_span_floor(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "phase_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["guide_configurations"][0]["full_span_molecules"] = 2
        _write_json(path, payload)

    def strands_not_counted(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "confirmation_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["both_strands_counted"] = False
        _write_json(path, payload)

    def identity_unresolved(dest: Path) -> None:
        write_passing_confirmation(dest)
        path = dest / "confirmation_record.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["specimen_identity_resolved"] = False
        _write_json(path, payload)

    def nominal_only_exposure(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            row["measurement_class"] = "nominal"
        _write_json(path, payload)

    def time_hours_nonpositive(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            row["time_hours"] = 0
        _write_json(path, payload)

    def clone_safety_under_followed(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(path.read_text(encoding="utf-8"))
        for row in lineage["runs"]:
            row["event_positive_daughters_followed"] = 0
            row["event_positive_daughters_reproduced"] = 0
            row["event_positive_daughters_died"] = 0
            row["event_negative_daughters_followed"] = 0
            row["event_negative_daughters_reproduced"] = 0
            row["event_negative_daughters_died"] = 0
        _write_json(path, lineage)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(lineage),
        )

    def clone_safety_selective_positive_followup(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(path.read_text(encoding="utf-8"))
        for row in lineage["runs"]:
            if row["arm"] == "treatment":
                row["event_positive_divisions"] = 6
                row["event_negative_divisions"] = 30
        _write_json(path, lineage)
        _write_json(
            dest / "blinded_count_table.synthetic.json",
            blinded_from_lineage(lineage),
        )

    def constant_window_sub_floor(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "measured_exposure_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            row["time_hours"] = 0.5
        _write_json(path, payload)

    def dominant_interference(dest: Path) -> None:
        # The missense carrier shows a checkpoint defect the truncation
        # carrier does not — dysfunction beyond one-allele dose loss, so
        # the mutant product plausibly interferes and stabilization is
        # contraindicated.
        _prepare_reachable(dest)
        set_carrier_endpoint(dest, "missense_carrier", "checkpoint", "positive")
        set_carrier_endpoint(dest, "stop", "checkpoint", "negative")

    def carrier_dose_unmeasured(dest: Path) -> None:
        # A carrier defect without the measured dose comparator cannot be
        # interpreted — hold, not a falsification.
        _prepare_reachable(dest)
        set_carrier_endpoint(dest, "missense_carrier", "checkpoint", "positive")

    def carrier_dose_stub(dest: Path) -> None:
        # The carrier row exists but never produced an interpretable call —
        # the dose control was never run, so dominant interference cannot be
        # excluded on any function axis. Hold, not a falsification.
        _prepare_reachable(dest)
        path = dest / "allele_function_scorecard.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["genotype_class"] == "missense_carrier":
                for item in row["assessments"]:
                    item["assessment_status"] = "not_assessable"
                    item["assay_class"] = "unlabeled"
                    for key in (
                        "condition_class",
                        "system_class",
                        "expression_class",
                        "specimen_class",
                    ):
                        item.pop(key, None)
        _write_json(path, payload)

    def missense_defective_when_abundant(dest: Path) -> None:
        # The allele stays checkpoint-defective when its abundance is
        # normalized — a qualitative defect that stabilization cannot
        # rescue. Hard stop.
        _prepare_reachable(dest)
        path = dest / "allele_function_scorecard.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["genotype_class"] == "missense_at_abundance":
                for item in row["assessments"]:
                    if item["endpoint"] == "checkpoint":
                        item["assessment_status"] = "positive"
        _write_json(path, payload)

    def function_at_abundance_unmeasured(dest: Path) -> None:
        # Abundance normalization was demonstrated but the function axes at
        # normalized abundance were never measured — the pivotal
        # discriminator is missing. Hold.
        _prepare_reachable(dest)
        path = dest / "allele_function_scorecard.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["genotype_class"] == "missense_at_abundance":
                for item in row["assessments"]:
                    if item["endpoint"] in FUNCTION_AXES:
                        item["assessment_status"] = "not_assessable"
                        item["assay_class"] = "unlabeled"
                        for key in (
                            "condition_class",
                            "system_class",
                            "expression_class",
                            "specimen_class",
                        ):
                            item.pop(key, None)
        _write_json(path, payload)

    def abundance_normalization_failed(dest: Path) -> None:
        # Titrated expression still cannot restore abundance — the
        # normalization premise itself is not demonstrated. Hold.
        _prepare_reachable(dest)
        path = dest / "allele_function_scorecard.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["genotype_class"] == "missense_at_abundance":
                for item in row["assessments"]:
                    if item["endpoint"] == "abundance":
                        item["assessment_status"] = "positive"
        _write_json(path, payload)

    def exposure_timing_mismatch(dest: Path) -> None:
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        path = dest / "lineage_count_table.synthetic.json"
        lineage = _json_loads(path.read_text(encoding="utf-8"))
        for row in lineage["runs"]:
            if row["arm"] == "treatment":
                row["endpoint_recorded_at"] = "2026-08-29T12:00:00Z"
                break
        _write_json(path, lineage)

    def composite_confirmation_plus_blinded(dest: Path) -> None:
        # Two independent defects at different depths — the earlier gate must
        # still report first, and the downstream tamper must not rescue it.
        _prepare_reachable(dest)
        declare_next_gate(dest, "syn-gate-replication")
        shutil.copy(
            COMMUNITY / "confirmation_record.synthetic.json",
            dest / "confirmation_record.synthetic.json",
        )
        path = dest / "blinded_count_table.synthetic.json"
        payload = _json_loads(path.read_text(encoding="utf-8"))
        payload["runs"][0]["detected_divisions"] += 1
        _write_json(path, payload)

    scenarios = [
        _run_mutated("reachable_save_path", "true_path", reachable),
        _run_mutated("incomplete_confirmation", "false_path", incomplete_confirmation),
        _run_mutated("cis_pair", "false_path", cis_pair),
        _run_mutated("linkage_not_recorded", "false_path", linkage_missing),
        _run_mutated("computational_phase", "false_path", computational_phase),
        _run_mutated(
            "unmatched_phase_specimen",
            "false_path",
            unmatched_phase_specimen,
        ),
        _run_mutated("analog_as_function", "false_path", analog_as_function),
        _run_mutated("analog_correction", "false_path", analog_correction),
        _run_mutated(
            "dominant_interference",
            "false_path",
            dominant_interference,
        ),
        _run_mutated(
            "carrier_dose_unmeasured",
            "false_path",
            carrier_dose_unmeasured,
        ),
        _run_mutated(
            "carrier_dose_stub",
            "false_path",
            carrier_dose_stub,
        ),
        _run_mutated(
            "missense_defective_when_abundant",
            "false_path",
            missense_defective_when_abundant,
        ),
        _run_mutated(
            "function_at_abundance_unmeasured",
            "false_path",
            function_at_abundance_unmeasured,
        ),
        _run_mutated(
            "abundance_normalization_failed",
            "false_path",
            abundance_normalization_failed,
        ),
        _run_mutated("heat_shock_pd", "false_path", heat_shock_pd),
        _run_mutated("competing_risk", "false_path", competing_risk),
        _run_mutated("organ_size_overclaim", "false_path", organ_size),
        _run_mutated("unlinked_confirmation", "false_path", unlinked_confirmation),
        _run_mutated("incomplete_transcript", "false_path", incomplete_transcript),
        _run_mutated("computational_transcript", "false_path", computational_transcript),
        _run_mutated(
            "unmatched_transcript_specimen",
            "false_path",
            unmatched_transcript_specimen,
        ),
        _run_mutated("computational_stability", "false_path", computational_stability),
        _run_mutated("computational_correction", "false_path", computational_correction),
        _run_mutated(
            "failed_reciprocal_recreation",
            "false_path",
            failed_reciprocal_recreation,
        ),
        _run_mutated(
            "imposed_extrinsic_stress",
            "false_path",
            imposed_extrinsic_stress,
        ),
        _run_mutated(
            "cell_free_biophysical",
            "false_path",
            cell_free_biophysical,
        ),
        _run_mutated(
            "cell_free_correction",
            "false_path",
            cell_free_correction,
        ),
        _run_mutated(
            "imposed_stress_correction",
            "false_path",
            imposed_stress_correction,
        ),
        _run_mutated(
            "ectopic_expression",
            "false_path",
            ectopic_expression,
        ),
        _run_mutated(
            "ectopic_correction",
            "false_path",
            ectopic_correction,
        ),
        _run_mutated(
            "unmatched_correction",
            "false_path",
            unmatched_correction,
        ),
        _run_mutated(
            "unmatched_assay_specimen",
            "false_path",
            unmatched_assay_specimen,
        ),
        _run_mutated("probe_before_identity", "false_path", probe_before_identity),
        _run_mutated(
            "later_identity_before_confirmation",
            "false_path",
            later_identity_before_confirmation,
        ),
        _run_mutated("imaging_before_assay", "false_path", imaging_before_assay),
        _run_mutated("checkpoint_not_assayed", "false_path", checkpoint_not_assayed),
        _run_mutated("checkpoint_negative", "false_path", checkpoint_negative),
        _run_mutated("unmanufacturable_window", "false_path", unmanufacturable_window),
        _run_mutated("bulk_fraction_endpoint", "false_path", bulk_fraction_endpoint),
        _run_mutated("kmer_without_nest", "false_path", kmer_without_nest),
        _run_mutated("kmer_without_file_layout", "false_path", kmer_without_file_layout),
        _run_mutated("rna_confirmation", "false_path", rna_confirmation),
        _run_mutated(
            "unmatched_confirmation_specimen",
            "false_path",
            unmatched_confirmation_specimen,
        ),
        _run_mutated("nontranslational_exposure", "false_path", nontranslational_exposure),
        _run_mutated("missing_exposure_duration", "false_path", missing_exposure_duration),
        _run_mutated("pulse_only_exposure", "false_path", pulse_only_exposure),
        _run_mutated(
            "aminoglycoside_carryover", "false_path", aminoglycoside_carryover
        ),
        _run_mutated(
            "selection_agent_unlabeled", "false_path", selection_agent_unlabeled
        ),
        _run_mutated(
            "selection_batch_taint", "false_path", selection_batch_taint
        ),
        _run_mutated("discordant_exposure", "false_path", discordant_exposure),
        _run_mutated(
            "exposure_assay_file_collage",
            "false_path",
            exposure_assay_file_collage,
        ),
        _run_mutated(
            "arm_position_confounding",
            "false_path",
            arm_position_confounding,
        ),
        _run_mutated(
            "arm_exact_column_gradient",
            "false_path",
            arm_exact_column_gradient,
        ),
        _run_mutated(
            "arm_row_half_interaction",
            "false_path",
            arm_row_half_interaction,
        ),
        _run_mutated(
            "arm_event_order_alias",
            "false_path",
            arm_event_order_alias,
        ),
        _run_mutated(
            "arm_local_quadratic_order_artifact",
            "false_path",
            arm_local_quadratic_order_artifact,
        ),
        _run_mutated(
            "arm_local_order_interaction_artifact",
            "false_path",
            arm_local_order_interaction_artifact,
        ),
        _run_mutated("family_overclaim", "false_path", family_overclaim),
        _run_mutated("dropout_compatible_phase", "false_path", dropout_compatible_phase),
        _run_mutated("strand_imbalance_phase", "false_path", strand_imbalance_phase),
        _run_mutated("unlocked_power_plan", "false_path", unlocked_power_plan),
        _run_mutated("underpowered_plan", "false_path", underpowered_plan),
        _run_mutated("missing_falsifier", "false_path", missing_falsifier),
        _run_mutated("observed_falsifier", "false_path", observed_falsifier),
        _run_mutated("unmeasured_rna_child_claim", "false_path", unmeasured_rna_child_claim),
        _run_mutated("bulk_aneuploidy_rescue", "false_path", bulk_aneuploidy_rescue),
        _run_mutated("missing_alternative", "false_path", missing_alternative),
        _run_mutated("observed_alternative", "false_path", observed_alternative),
        _run_mutated("observed_without_gate", "false_path", observed_without_gate),
        _run_mutated("missing_controls", "false_path", missing_controls),
        _run_mutated("control_failed", "false_path", control_failed),
        _run_mutated(
            "observed_stability_without_assay",
            "false_path",
            observed_stability_without_assay,
        ),
        _run_mutated("pediatric_crash_plan", "false_path", pediatric_crash_plan),
        _run_mutated(
            "observed_endpoint_without_concordance",
            "false_path",
            observed_endpoint_without_concordance,
        ),
        _run_mutated("missing_multiplicity", "false_path", missing_multiplicity),
        _run_mutated("missing_counterscreen", "false_path", missing_counterscreen),
        _run_mutated(
            "missing_evidence_chain", "false_path", missing_evidence_chain
        ),
        _run_mutated(
            "supports_donation_falsifier",
            "false_path",
            supports_donation_falsifier,
        ),
        _run_mutated("unwatched_falsifier", "false_path", unwatched_falsifier),
        _run_mutated("unwatched_endpoint", "false_path", unwatched_endpoint),
        _run_mutated("unwatched_alternative", "false_path", unwatched_alternative),
        _run_mutated(
            "multiplicity_without_alpha",
            "false_path",
            multiplicity_without_alpha,
        ),
        _run_mutated("unwatched_probe_chain", "false_path", unwatched_probe_chain),
        _run_mutated("watch_cycle", "false_path", watch_cycle),
        _run_mutated("endpoint_unkilled", "false_path", endpoint_unkilled),
        _run_mutated(
            "endpoint_uncontrolled", "false_path", endpoint_uncontrolled
        ),
        _run_mutated("probe_unscreened", "false_path", probe_unscreened),
        _run_mutated(
            "multiplicity_family_uncovered",
            "false_path",
            multiplicity_family_uncovered,
        ),
        _run_mutated(
            "vacuous_second_endpoint", "false_path", vacuous_second_endpoint
        ),
        _run_mutated(
            "endpoint_wrong_comparator",
            "false_path",
            endpoint_wrong_comparator,
        ),
        _run_mutated("endpoint_unblinded", "false_path", endpoint_unblinded),
        _run_mutated("endpoint_without_spec", "false_path", endpoint_without_spec),
        _run_mutated(
            "falsifier_bound_unequal",
            "false_path",
            falsifier_bound_unequal,
        ),
        _run_mutated("unanchored_kill_bound", "false_path", unanchored_kill_bound),
        _run_mutated("fitter_error_daughters", "false_path", fitter_error_daughters),
        _run_mutated(
            "event_negative_daughter_viability",
            "false_path",
            event_negative_daughter_viability,
        ),
        _run_mutated(
            "multipolar_daughters_unfollowed",
            "false_path",
            multipolar_daughters_unfollowed,
        ),
        _run_mutated(
            "censored_daughters_dilute",
            "false_path",
            censored_daughters_dilute,
        ),
        _run_mutated(
            "ranking_cannot_open_checkpoint",
            "false_path",
            ranking_cannot_open_checkpoint,
        ),
        _run_mutated(
            "predicted_stability_as_function",
            "false_path",
            predicted_stability_as_function,
        ),
        _run_mutated(
            "blinded_table_tampered",
            "false_path",
            blinded_table_tampered,
        ),
        _run_mutated(
            "blinded_row_dropped",
            "false_path",
            blinded_row_dropped,
        ),
        _run_mutated("single_flat_clone", "false_path", single_flat_clone),
        _run_mutated(
            "replication_declared_discordant",
            "false_path",
            replication_declared_discordant,
        ),
        _run_mutated(
            "replication_same_site",
            "false_path",
            replication_same_site,
        ),
        _run_mutated(
            "replication_declared_exposure_failed",
            "false_path",
            replication_declared_exposure_failed,
        ),
        _run_mutated("unknown_next_gate", "false_path", unknown_next_gate),
        _run_mutated(
            "endpoint_negated_comparator",
            "false_path",
            endpoint_negated_comparator,
        ),
        _run_mutated(
            "blinded_duplicate_keys",
            "false_path",
            blinded_duplicate_keys,
        ),
        _run_mutated(
            "blinded_negative_shared_count",
            "false_path",
            blinded_negative_shared_count,
        ),
        _run_mutated(
            "composite_confirmation_plus_blinded",
            "false_path",
            composite_confirmation_plus_blinded,
        ),
        _run_mutated(
            "dropped_clone_caught_by_binding",
            "false_path",
            dropped_clone_caught_by_binding,
        ),
        _run_mutated(
            "vehicle_baseline_missing",
            "false_path",
            vehicle_baseline_missing,
        ),
        _run_mutated(
            "missense_not_expressed",
            "false_path",
            missense_not_expressed,
        ),
        _run_mutated(
            "protein_not_transcript",
            "false_path",
            protein_not_transcript,
        ),
        _run_mutated(
            "stop_transcript_persists",
            "false_path",
            stop_transcript_persists,
        ),
        _run_mutated(
            "linkage_disagreement",
            "false_path",
            linkage_disagreement,
        ),
        _run_mutated(
            "need_two_guide_configurations",
            "false_path",
            need_two_guide_configurations,
        ),
        _run_mutated("guide_span_floor", "false_path", guide_span_floor),
        _run_mutated("strands_not_counted", "false_path", strands_not_counted),
        _run_mutated("identity_unresolved", "false_path", identity_unresolved),
        _run_mutated(
            "nominal_only_exposure",
            "false_path",
            nominal_only_exposure,
        ),
        _run_mutated(
            "time_hours_nonpositive",
            "false_path",
            time_hours_nonpositive,
        ),
        _run_mutated(
            "clone_safety_under_followed",
            "false_path",
            clone_safety_under_followed,
        ),
        _run_mutated(
            "clone_safety_selective_positive_followup",
            "false_path",
            clone_safety_selective_positive_followup,
        ),
        _run_mutated(
            "constant_window_sub_floor",
            "false_path",
            constant_window_sub_floor,
        ),
        _run_mutated(
            "exposure_timing_mismatch",
            "false_path",
            exposure_timing_mismatch,
        ),
    ]
    n_true = sum(1 for item in scenarios if item["kind"] == "true_path")
    n_true_opened = sum(1 for item in scenarios if item["opened"])
    n_false = sum(1 for item in scenarios if item["kind"] == "false_path")
    n_false_blocked = sum(
        1 for item in scenarios if item["blocked_from_advancing"]
    )
    # Cardinality is part of the contract: a silently dropped false scenario
    # must surface as a failure, not as a smaller denominator.
    if n_true != EXPECTED_TRUE_PATHS or n_false != EXPECTED_FALSE_PATHS:
        raise SavePathError(
            "save-path scenario cardinality drifted from the declared matrix"
        )
    # The pristine-toolkit digest is built directly rather than borrowed
    # from the sentinel scenario: if incomplete_confirmation ever stops
    # being a no-op mutation the check must fail loudly instead of quietly
    # re-anchoring the baseline to a mutated toolkit.
    with TemporaryDirectory() as folder:
        baseline_digest = _toolkit_digest(_copy_toolkit(Path(folder)))
    digested = [item for item in scenarios if "toolkit_digest" in item]
    baseline_names = {
        item["name"]
        for item in digested
        if item["toolkit_digest"] == baseline_digest
    }
    if (
        len({item["toolkit_digest"] for item in digested}) != len(digested)
        or baseline_names != {"incomplete_confirmation"}
    ):
        raise SavePathError("save-path scenarios must be distinct toolkits")
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "n_true_path": n_true,
        "n_true_path_opened": n_true_opened,
        "n_false_path": n_false,
        "n_false_paths_blocked_from_advancing": n_false_blocked,
        "save_path_reachable": n_true_opened == n_true and n_true > 0,
        "false_paths_blocked_from_advancing": n_false_blocked == n_false,
        # The suite only passes when the true path opens AND every false
        # path stays blocked — reachability alone is not success.
        "save_path_suite_passed": (
            n_true_opened == n_true
            and n_true > 0
            and n_false_blocked == n_false
            and n_false == EXPECTED_FALSE_PATHS
        ),
        "scenario_toolkits_distinct": True,
        "structure_ranking": {
            "assay_priority": ranking["assay_priority"],
            "checkpoint_ready": ranking["checkpoint_ready"],
            "reason": ranking["reason"],
        },
        "scenarios": scenarios,
    }


__all__ = [
    "CLAIM_BOUNDARY",
    "SCHEMA",
    "SavePathError",
    "passing_confirmation",
    "passing_exposure",
    "passing_power",
    "passing_transcript",
    "run_save_path_suite",
    "write_passing_confirmation",
    "write_passing_transcript",
]
