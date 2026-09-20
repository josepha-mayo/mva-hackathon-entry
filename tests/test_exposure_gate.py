from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.exposure_gate import (
    ADVANCE_MAX_UM,
    CLAIM_BOUNDARY,
    SCHEMA,
    ExposureGateError,
    assess_exposure_gate,
    make_exposure_profile_id,
)


ROOT = Path(__file__).resolve().parents[1]
COMMUNITY_TABLE = (
    ROOT / "templates" / "community" / "measured_exposure_table.synthetic.json"
)


def _table(rows: list[dict[str, object]]) -> dict[str, object]:
    filled = []
    for row in rows:
        item = dict(row)
        item.setdefault("measurement_class", "culture_measured")
        item.setdefault("time_hours", 24)
        item.setdefault("pulse_vs_constant", "constant")
        item.setdefault("washout", False)
        item.setdefault("selection_agent", "none")
        item.setdefault("selection_agent_cleared", None)
        item.setdefault("selection_clearance_method", None)
        filled.append(item)
    return {
        "schema": "mva.community-measured-exposure-table/v1",
        "privacy_class": "synthetic",
        "purpose": "Synthetic exposure rows for software tests.",
        "probe_id": "syn-probe-a",
        "note": "synthetic",
        "columns": [
            "nominal_uM",
            "unbound_medium_uM",
            "intracellular_parent",
            "time_hours",
            "pulse_vs_constant",
            "washout",
            "measurement_class",
            "selection_agent",
            "selection_agent_cleared",
            "selection_clearance_method",
        ],
        "rows": filled,
    }


def _allocated_table() -> dict[str, object]:
    """Community template: a verified allocation and vehicle baseline."""
    return json.loads(COMMUNITY_TABLE.read_text(encoding="utf-8"))


class ExposureGateTests(unittest.TestCase):
    def test_community_table_passes_conservative_window(self) -> None:
        table = json.loads(COMMUNITY_TABLE.read_text(encoding="utf-8"))
        result = assess_exposure_gate(table)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["exposure_gate_passed"])
        self.assertFalse(result["advancement_blocked"])
        self.assertTrue(
            all(item["nominal_uM"] <= ADVANCE_MAX_UM for item in result["rows"])
        )

    def test_nominal_only_cannot_pass(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": None,
                        "intracellular_parent": None,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["exposure_gate_passed"])
        self.assertTrue(result["advancement_blocked"])
        self.assertEqual(result["reason"], "nominal_only")

    def test_exploratory_only_cannot_advance(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 5.0,
                        "unbound_medium_uM": 4.1,
                        "intracellular_parent": 3.2,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["rows"][0]["row_class"], "exploratory_5um")
        self.assertEqual(result["reason"], "no_conservative_window_row")

    def test_zero_nominal_cannot_pass(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 0.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["exposure_gate_passed"])
        self.assertTrue(result["advancement_blocked"])
        self.assertEqual(result["rows"][0]["row_class"], "not_assessable")

    def test_zero_intracellular_cannot_pass(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.0,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["exposure_gate_passed"])
        self.assertEqual(result["reason"], "zero_cell_exposure")
        self.assertEqual(result["rows"][0]["row_class"], "not_assessable")

    def test_measured_zero_beside_a_qualifying_row_is_discordant(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.0,
                    },
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.8,
                        "intracellular_parent": 0.5,
                    },
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "exposure_discordant")
        self.assertFalse(result["exposure_gate_passed"])

    def test_nontranslational_concentration_stops(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                    },
                    {
                        "nominal_uM": 100.0,
                        "unbound_medium_uM": 80.0,
                        "intracellular_parent": 40.0,
                    },
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertTrue(result["advancement_blocked"])
        self.assertEqual(result["reason"], "nontranslational_high")

    def test_nontranslational_stop_has_priority_over_missing_schedule(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 100.0,
                        "unbound_medium_uM": 80.0,
                        "intracellular_parent": 40.0,
                        "time_hours": "unknown",
                        "pulse_vs_constant": 7,
                        "washout": "unknown",
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "stop")
        self.assertEqual(result["reason"], "nontranslational_high")

    def test_label_estimate_cannot_pass_as_culture_exposure(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "measurement_class": "label_estimate",
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "label_estimate_not_culture")

    def test_missing_duration_cannot_pass_a_measured_low_row(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "time_hours": None,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "time_hours_missing")
        self.assertEqual(result["rows"][0]["concentration_class"], "leq_2um")
        self.assertEqual(result["rows"][0]["row_class"], "not_assessable")
        self.assertFalse(result["rows"][0]["time_profile_assessable"])

    def test_nonpositive_duration_cannot_pass(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "time_hours": 0,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "time_hours_nonpositive")

    def test_sub_floor_constant_window_is_not_a_window(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "time_hours": 0.5,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "time_profile_not_advancing")
        self.assertEqual(
            result["rows"][0]["time_profile_reason"], "time_hours_below_window"
        )

    def test_pulse_only_is_supportive_not_an_advancing_window(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "time_hours": 4,
                        "pulse_vs_constant": "pulse",
                        "washout": True,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "pulse_only_not_advancing")
        self.assertEqual(result["rows"][0]["time_profile_reason"], "pulse_support_only")

    def test_pulse_support_can_sit_beside_a_complete_constant_window(self) -> None:
        table = _allocated_table()
        # Turn the unbound measurement row into a washed-out pulse reading;
        # the bound execution rows keep the verified allocation intact.
        table["rows"][0].update(
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.6,
                "intracellular_parent": 0.2,
                "time_hours": 4,
                "pulse_vs_constant": "pulse",
                "washout": True,
            }
        )
        result = assess_exposure_gate(table)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "conservative_window_measured")
        self.assertEqual(result["rows"][0]["row_class"], "not_assessable")

    def test_pulse_without_washout_or_unknown_profile_cannot_pass(self) -> None:
        pulse_without_washout = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "time_hours": 4,
                        "pulse_vs_constant": "pulse",
                        "washout": False,
                    }
                ]
            )
        )
        self.assertEqual(pulse_without_washout["status"], "not_assessable")
        self.assertEqual(pulse_without_washout["reason"], "time_profile_not_advancing")

        invalid_profile = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "pulse_vs_constant": "unknown",
                    }
                ]
            )
        )
        self.assertEqual(invalid_profile["status"], "not_assessable")
        self.assertEqual(invalid_profile["reason"], "time_profile_not_advancing")

        missing_pulse_washout = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "pulse_vs_constant": "pulse",
                        "washout": None,
                    }
                ]
            )
        )
        self.assertEqual(missing_pulse_washout["status"], "not_assessable")
        self.assertEqual(missing_pulse_washout["reason"], "time_profile_not_advancing")

    def test_constant_contact_can_declare_a_later_washout(self) -> None:
        table = _allocated_table()
        table["rows"][0]["washout"] = True
        result = assess_exposure_gate(table)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["rows"][0]["time_profile_reason"], "constant_window")

    def test_constant_contact_does_not_require_a_row_level_washout_value(self) -> None:
        table = _allocated_table()
        table["rows"][0]["washout"] = None
        result = assess_exposure_gate(table)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["rows"][0]["time_profile_reason"], "constant_window")

    def test_nonfinite_duration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ExposureGateError, "time_hours must be finite"):
            assess_exposure_gate(
                _table(
                    [
                        {
                            "nominal_uM": 1.0,
                            "unbound_medium_uM": 0.7,
                            "intracellular_parent": 0.3,
                            "time_hours": float("nan"),
                        }
                    ]
                )
            )

    def test_declared_columns_must_include_time_profile_fields(self) -> None:
        table = _table(
            [
                {
                    "nominal_uM": 1.0,
                    "unbound_medium_uM": 0.7,
                    "intracellular_parent": 0.3,
                }
            ]
        )
        table["columns"] = [
            "nominal_uM",
            "unbound_medium_uM",
            "intracellular_parent",
        ]
        with self.assertRaisesRegex(ExposureGateError, "missing required columns"):
            assess_exposure_gate(table)

    def test_columns_must_be_a_sequence_of_strings(self) -> None:
        table = _table(
            [
                {
                    "nominal_uM": 1.0,
                    "unbound_medium_uM": 0.7,
                    "intracellular_parent": 0.3,
                }
            ]
        )
        for bad in (
            "nominal_uM,unbound_medium_uM,intracellular_parent,time_hours,"
            "pulse_vs_constant,washout,measurement_class",
            [],
            ["nominal_uM", 7],
        ):
            with self.subTest(bad=bad):
                table["columns"] = bad
                with self.assertRaisesRegex(ExposureGateError, "columns"):
                    assess_exposure_gate(table)

    def test_nonboolean_washout_cannot_pass_a_constant_row(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "washout": 1,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["exposure_gate_passed"])
        self.assertEqual(
            result["rows"][0]["time_profile_reason"], "washout_invalid"
        )

    def test_profile_id_is_semantic_and_independent_of_json_key_order(self) -> None:
        row = {
            "nominal_uM": 1.0,
            "unbound_medium_uM": 0.7,
            "intracellular_parent": 0.3,
            "time_hours": 24,
            "pulse_vs_constant": "constant",
            "washout": False,
            "measurement_class": "culture_measured",
        }
        reversed_row = dict(reversed(list(row.items())))
        self.assertEqual(
            make_exposure_profile_id(row, "syn-probe-a"),
            make_exposure_profile_id(reversed_row, "syn-probe-a"),
        )
        changed = {**row, "time_hours": 12}
        self.assertNotEqual(
            make_exposure_profile_id(row, "syn-probe-a"),
            make_exposure_profile_id(changed, "syn-probe-a"),
        )

    def test_measured_window_without_vehicle_baseline_cannot_pass(self) -> None:
        # A qualifying constant-window row with no recorded vehicle control
        # cannot separate rescue from drift — the gate must not certify it.
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["exposure_gate_passed"])
        self.assertIn(
            result["reason"],
            {
                "vehicle_baseline_missing",
                "allocation_not_verified",
                "no_planned_functional_executions",
            },
        )

    def test_vacuous_allocation_cannot_back_a_gate_pass(self) -> None:
        table = _allocated_table()
        # Strip every functional-execution link so no allocation is required:
        # the resulting no-op pass must not certify the exposure gate.
        for row in table["rows"]:
            row["supports_functional_execution_ids"] = []
            row["functional_assay_run_ids"] = []
        for control in table["vehicle_controls"]:
            control["supports_functional_execution_ids"] = []
            control["functional_assay_run_ids"] = []
        result = assess_exposure_gate(table)
        self.assertEqual(result["status"], "not_assessable")
        self.assertFalse(result["exposure_gate_passed"])
        self.assertEqual(result["reason"], "no_planned_functional_executions")

    def test_aminoglycoside_without_clearance_is_carryover(self) -> None:
        # G418/neomycin are canonical readthrough agents: an uncleared
        # aminoglycoside in the assay window can itself induce the claimed
        # suppression phenotype, so the row cannot qualify.
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "selection_agent": "aminoglycoside",
                        "selection_agent_cleared": False,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "aminoglycoside_carryover")
        self.assertEqual(result["rows"][0]["row_class"], "aminoglycoside_carryover")

    def test_aminoglycoside_null_clearance_is_carryover(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "selection_agent": "aminoglycoside",
                        "selection_agent_cleared": None,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "aminoglycoside_carryover")

    def test_cleared_aminoglycoside_can_still_pass(self) -> None:
        table = _allocated_table()
        for row in table["rows"]:
            row["selection_agent"] = "aminoglycoside"
            row["selection_agent_cleared"] = True
        result = assess_exposure_gate(table)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["exposure_gate_passed"])

    def test_unlabeled_selection_agent_cannot_qualify(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "selection_agent": None,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "selection_agent_unlabeled")

    def test_non_aminoglycoside_carryover_holds(self) -> None:
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "selection_agent": "non_aminoglycoside",
                        "selection_agent_cleared": False,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "selection_agent_carryover")

    def test_selection_agent_vocabulary_is_closed(self) -> None:
        with self.assertRaisesRegex(ExposureGateError, "selection_agent"):
            assess_exposure_gate(
                _table(
                    [
                        {
                            "nominal_uM": 1.0,
                            "unbound_medium_uM": 0.7,
                            "intracellular_parent": 0.3,
                            "selection_agent": "g418-ish",
                        }
                    ]
                )
            )

    def test_cleared_without_method_is_unverified(self) -> None:
        # A bare cleared=true checkbox carries no evidence — the aminoglycoside
        # carryover channel must engage until a declared method backs it.
        result = assess_exposure_gate(
            _table(
                [
                    {
                        "nominal_uM": 1.0,
                        "unbound_medium_uM": 0.7,
                        "intracellular_parent": 0.3,
                        "selection_agent": "aminoglycoside",
                        "selection_agent_cleared": True,
                    }
                ]
            )
        )
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "selection_clearance_method_unverified"
        )
        self.assertEqual(
            result["rows"][0]["row_class"], "aminoglycoside_carryover"
        )

    def test_clearance_method_vocabulary_is_closed(self) -> None:
        with self.assertRaisesRegex(ExposureGateError, "selection_clearance_method"):
            assess_exposure_gate(
                _table(
                    [
                        {
                            "nominal_uM": 1.0,
                            "unbound_medium_uM": 0.7,
                            "intracellular_parent": 0.3,
                            "selection_agent": "aminoglycoside",
                            "selection_agent_cleared": True,
                            "selection_clearance_method": "washed_a_bit",
                        }
                    ]
                )
            )

    def test_cleared_with_declared_method_passes(self) -> None:
        result = assess_exposure_gate(
            _allocated_table()
        )
        self.assertEqual(result["status"], "pass")

    def test_uncleared_sibling_taints_whole_batch(self) -> None:
        # The antibiotic lives in the culture, not the row: one uncleared
        # declaration inside a shared culture_batch_id downgrades every
        # qualifying sibling, including ones that claim clearance.
        rows = [
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.7,
                "intracellular_parent": 0.3,
                "selection_agent": "aminoglycoside",
                "selection_agent_cleared": True,
                "selection_clearance_method": "serial_passage_without_agent",
                "culture_batch_id": "syn-batch-x",
            },
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.7,
                "intracellular_parent": 0.3,
                "selection_agent": "aminoglycoside",
                "selection_agent_cleared": False,
                "culture_batch_id": "syn-batch-x",
            },
        ]
        result = assess_exposure_gate(_table(rows))
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "aminoglycoside_carryover")
        self.assertTrue(
            all(
                row["row_class"] == "aminoglycoside_carryover"
                for row in result["rows"]
            )
        )

    def test_inconsistent_agent_within_batch_fails(self) -> None:
        # One row says the culture never saw an antibiotic; its sibling says
        # aminoglycoside. A batch has one history — conflicting declarations
        # mean the reporting is unreliable.
        rows = [
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.7,
                "intracellular_parent": 0.3,
                "selection_agent": "none",
                "culture_batch_id": "syn-batch-y",
            },
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.7,
                "intracellular_parent": 0.3,
                "selection_agent": "aminoglycoside",
                "selection_agent_cleared": True,
                "selection_clearance_method": "documented_media_exchange",
                "culture_batch_id": "syn-batch-y",
            },
        ]
        result = assess_exposure_gate(_table(rows))
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(
            result["reason"], "selection_agent_inconsistent_within_batch"
        )

    def test_partial_batch_declaration_fails_closed(self) -> None:
        # One row declares a culture batch; its sibling declares none. Batch
        # consistency checks cannot cover the unbatched row, so the table is
        # hiding structure — no row may qualify.
        rows = [
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.7,
                "intracellular_parent": 0.3,
                "selection_agent": "none",
                "culture_batch_id": "syn-batch-z",
            },
            {
                "nominal_uM": 1.0,
                "unbound_medium_uM": 0.7,
                "intracellular_parent": 0.3,
                "selection_agent": "none",
            },
        ]
        result = assess_exposure_gate(_table(rows))
        self.assertEqual(result["status"], "not_assessable")
        self.assertEqual(result["reason"], "culture_batch_partially_declared")

    def test_different_batches_do_not_cross_taint(self) -> None:
        # A dirty row in a separate culture is legitimately separate data:
        # it is flagged in its own row_class while the clean batch's
        # qualifying row still passes the gate.
        table = _allocated_table()
        clean = table["rows"][0]
        clean["culture_batch_id"] = "syn-batch-clean"
        dirty = table["rows"][1]
        dirty["culture_batch_id"] = "syn-batch-dirty"
        dirty["selection_agent_cleared"] = False
        dirty["selection_clearance_method"] = None
        result = assess_exposure_gate(table)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["rows"][0]["row_class"], "leq_2um")
        self.assertEqual(
            result["rows"][1]["row_class"], "aminoglycoside_carryover"
        )

    def test_unknown_measurement_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ExposureGateError, "measurement_class"):
            assess_exposure_gate(
                _table(
                    [
                        {
                            "nominal_uM": 1.0,
                            "unbound_medium_uM": 0.7,
                            "intracellular_parent": 0.3,
                            "measurement_class": "probably_measured",
                        }
                    ]
                )
            )

    def test_wrong_schema_fails_closed(self) -> None:
        with self.assertRaisesRegex(ExposureGateError, "measured-exposure"):
            assess_exposure_gate({"schema": "mva-track2-clone-safety/v1", "rows": []})

    def test_exposure_gate_report_does_not_use_software_proves(self) -> None:
        text = (ROOT / "reports" / "TRACK2_EXPOSURE_GATE.md").read_text(encoding="utf-8")
        self.assertNotIn("software proves", text.lower())


if __name__ == "__main__":
    unittest.main()
