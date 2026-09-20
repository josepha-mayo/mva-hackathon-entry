from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.coordinate_geometry import (
    CLAIM_BOUNDARY,
    SCHEMA,
    CoordinateGeometryError,
    analyze_coordinate_geometry,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "templates" / "community" / "coordinate_model.synthetic.pdb"
SCRIPT = ROOT / "scripts" / "run_coordinate_geometry.py"
RECEIPT = ROOT / "reports" / "TRACK2_COORDINATE_GEOMETRY_SYNTHETIC.json"


def _analyze(data: bytes | None = None, comparators: tuple[int, ...] = (20, 30)) -> dict:
    payload = FIXTURE.read_bytes() if data is None else data
    return analyze_coordinate_geometry(
        payload,
        source_name="coordinate_model.synthetic.pdb",
        chain_id="A",
        target_residue=10,
        comparator_residues=comparators,
        ca_shell_threshold_angstrom=6.0,
        sidechain_contact_threshold_angstrom=1.5,
        polar_proximity_threshold_angstrom=1.5,
        nonlocal_sequence_separation_minimum=3,
    )


class CoordinateGeometryTests(unittest.TestCase):
    def test_synthetic_geometry_is_deterministic_and_bounded(self) -> None:
        result = _analyze()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertTrue(result["coordinate_only"])
        self.assertFalse(result["checkpoint_ready"])
        self.assertFalse(result["probe_eligible"])
        self.assertEqual(
            result["input"]["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        )
        self.assertEqual(result["input"]["source_name"], FIXTURE.name)
        self.assertNotIn(str(FIXTURE.parent), json.dumps(result, allow_nan=False))

    def test_direct_distance_and_shared_contact_are_exact(self) -> None:
        result = _analyze()
        direct = {row["residue"]: row for row in result["direct_geometry_from_target"]}
        self.assertEqual(direct[20]["ca_distance_angstrom"], 3.0)
        self.assertEqual(direct[20]["minimum_heavy_atom_distance_angstrom"], 1.0)
        self.assertEqual(direct[30]["ca_distance_angstrom"], 10.0)
        overlap = {
            row["residue"]: row
            for row in result["neighborhood_overlap_with_target"]
        }
        self.assertEqual(
            overlap[20]["nonlocal_ca_shell_overlap"]["intersection"], [40]
        )
        self.assertEqual(
            overlap[20]["nonlocal_sidechain_contact_overlap"]["intersection"],
            [40],
        )

    def test_comparator_order_is_canonical(self) -> None:
        self.assertEqual(_analyze(comparators=(30, 20)), _analyze(comparators=(20, 30)))

    def test_checked_synthetic_receipt_is_exactly_reproducible(self) -> None:
        rendered = (json.dumps(_analyze(), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        self.assertEqual(RECEIPT.read_bytes(), rendered)

    def test_oversized_threshold_fails_controlled(self) -> None:
        with self.assertRaisesRegex(CoordinateGeometryError, "finite positive"):
            analyze_coordinate_geometry(
                FIXTURE.read_bytes(),
                source_name="coordinate_model.synthetic.pdb",
                chain_id="A",
                target_residue=10,
                comparator_residues=(20, 30),
                ca_shell_threshold_angstrom=10 ** 400,
                sidechain_contact_threshold_angstrom=1.5,
                polar_proximity_threshold_angstrom=1.5,
                nonlocal_sequence_separation_minimum=3,
            )

    def test_missing_residue_fails_closed(self) -> None:
        with self.assertRaisesRegex(CoordinateGeometryError, "absent"):
            analyze_coordinate_geometry(
                FIXTURE.read_bytes(),
                source_name=FIXTURE.name,
                chain_id="A",
                target_residue=10,
                comparator_residues=(999,),
            )

    def test_duplicate_or_target_comparator_fails_closed(self) -> None:
        for comparators in ((20, 20), (10, 20)):
            with self.subTest(comparators=comparators):
                with self.assertRaises(CoordinateGeometryError):
                    _analyze(comparators=comparators)

    def test_multiple_models_fail_closed(self) -> None:
        data = b"MODEL        1\n" + FIXTURE.read_bytes() + b"MODEL        2\nENDMDL\n"
        with self.assertRaisesRegex(CoordinateGeometryError, "at most one model"):
            _analyze(data=data)

    def test_altloc_nonunit_occupancy_and_resumed_segment_fail_closed(self) -> None:
        lines = FIXTURE.read_text(encoding="ascii").splitlines()

        alternate = lines.copy()
        alternate[5] = alternate[5][:16] + "B" + alternate[5][17:]
        with self.assertRaisesRegex(CoordinateGeometryError, "alternate locations"):
            _analyze(data=("\n".join(alternate) + "\n").encode("ascii"))

        partial = lines.copy()
        partial[5] = partial[5][:54] + "  0.50" + partial[5][60:]
        with self.assertRaisesRegex(CoordinateGeometryError, "unit occupancy"):
            _analyze(data=("\n".join(partial) + "\n").encode("ascii"))

        resumed = lines[:-2] + ["TER"] + [lines[0], "END"]
        with self.assertRaisesRegex(CoordinateGeometryError, "resumes after TER"):
            _analyze(data=("\n".join(resumed) + "\n").encode("ascii"))

    def test_overflowing_coordinate_field_fails_closed(self) -> None:
        lines = FIXTURE.read_text(encoding="ascii").splitlines()
        lines[5] = lines[5][:30] + "  1e309  " + lines[5][38:]
        with self.assertRaisesRegex(CoordinateGeometryError, "non-finite"):
            _analyze(data=("\n".join(lines) + "\n").encode("ascii"))

    def test_model_and_end_boundaries_fail_closed(self) -> None:
        fixture = FIXTURE.read_bytes()
        with self.assertRaisesRegex(CoordinateGeometryError, "missing its ENDMDL"):
            _analyze(data=b"MODEL        1\n" + fixture)
        with self.assertRaisesRegex(CoordinateGeometryError, "after ENDMDL"):
            _analyze(data=b"MODEL        1\nENDMDL\n" + fixture)
        with self.assertRaisesRegex(CoordinateGeometryError, "after END"):
            _analyze(data=b"END\n" + fixture)

    def test_insertion_code_and_path_like_source_name_fail_closed(self) -> None:
        lines = FIXTURE.read_text(encoding="ascii").splitlines()
        lines[0] = lines[0][:26] + "A" + lines[0][27:]
        with self.assertRaisesRegex(CoordinateGeometryError, "insertion code"):
            _analyze(data=("\n".join(lines) + "\n").encode("ascii"))
        with self.assertRaisesRegex(CoordinateGeometryError, "basename"):
            analyze_coordinate_geometry(
                FIXTURE.read_bytes(),
                source_name="private/path/model.pdb",
                chain_id="A",
                target_residue=10,
                comparator_residues=(20,),
            )

    def test_cli_emits_strict_json_and_refuses_overwrite(self) -> None:
        command = [
            sys.executable,
            str(SCRIPT),
            "--pdb",
            str(FIXTURE),
            "--chain",
            "A",
            "--target",
            "10",
            "--comparators",
            "20",
            "30",
            "--ca-shell",
            "6",
            "--sidechain-contact",
            "1.5",
            "--polar-proximity",
            "1.5",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema"], SCHEMA)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.json"
            output.write_text("already here\n", encoding="utf-8")
            refused = subprocess.run(
                [*command, "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("refusing to overwrite", refused.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "already here\n")


if __name__ == "__main__":
    unittest.main()
