"""Deterministic, case-agnostic geometry from one PDB coordinate model.

The engine reports distances and neighborhood overlap only. It does not model
mutations, calculate free energy, infer pathogenicity, rank medicines, or
replace an exact-allele functional assay. Output records a caller-safe source
name and a content digest, never an absolute input path.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA = "mva-track2-coordinate-geometry/v1"
SCRIPT_VERSION = "1.0.0"
CLAIM_BOUNDARY = (
    "One static coordinate model can prioritize experiments only; distances "
    "and contact overlap are not mutant structure, energetics, function, "
    "pathogenicity, target engagement, efficacy, safety, or clinical benefit."
)

_BACKBONE_ATOMS = frozenset({"N", "CA", "C", "O", "OXT"})
_POLAR_ELEMENTS = frozenset({"N", "O", "S"})
MAX_PDB_BYTES = 64 * 1024 * 1024


class CoordinateGeometryError(ValueError):
    """Raised when coordinate input or analysis parameters fail closed."""


@dataclass(frozen=True, slots=True)
class Atom:
    name: str
    element: str
    coord: tuple[float, float, float]
    b_factor: float


@dataclass(frozen=True, slots=True)
class Residue:
    name: str
    atoms: tuple[Atom, ...]


def _finite_positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoordinateGeometryError(f"{label} must be a finite positive number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise CoordinateGeometryError(
            f"{label} must be a finite positive number"
        ) from exc
    if not math.isfinite(result) or result <= 0:
        raise CoordinateGeometryError(f"{label} must be a finite positive number")
    return result


def _residue_number(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CoordinateGeometryError(f"{label} must be an integer residue number")
    return value


def _source_name(value: str) -> str:
    if not isinstance(value, str):
        raise CoordinateGeometryError("source_name must be a string")
    if value != value.strip() or not value or len(value) > 160:
        raise CoordinateGeometryError(
            "source_name must be non-empty, trimmed, and at most 160 characters"
        )
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise CoordinateGeometryError("source_name must be a basename, not a path")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CoordinateGeometryError("source_name must not contain control characters")
    return value


def _element_from_atom_name(atom_name: str) -> str:
    letters = "".join(character for character in atom_name if character.isalpha())
    if not letters:
        raise CoordinateGeometryError("atom name does not contain an element letter")
    return letters[0].upper()


def _parse_float(field: str, label: str) -> float:
    try:
        value = float(field)
    except (ValueError, OverflowError) as exc:
        raise CoordinateGeometryError(f"invalid {label} field in PDB input") from exc
    if not math.isfinite(value):
        raise CoordinateGeometryError(f"non-finite {label} field in PDB input")
    return value


def parse_single_model_pdb(data: bytes, chain_id: str) -> dict[int, Residue]:
    """Parse one integer-numbered chain from strict-enough PDB ATOM records.

    Multiple models, alternate locations, non-unit occupancy, insertion codes,
    and repeated selected-chain segments fail closed. The deliberately narrow
    contract prevents silent coordinate selection or segment merging.
    """

    if not isinstance(data, bytes) or not data:
        raise CoordinateGeometryError("PDB input must be non-empty bytes")
    # Byte ceiling before decode — an unbounded PDB can exhaust memory.
    if len(data) > MAX_PDB_BYTES:
        raise CoordinateGeometryError(
            f"PDB input exceeds the {MAX_PDB_BYTES // (1024 * 1024)} MiB ceiling"
        )
    if not isinstance(chain_id, str) or len(chain_id) != 1 or chain_id.isspace():
        raise CoordinateGeometryError("chain_id must be one visible character")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CoordinateGeometryError("PDB input must be ASCII") from exc

    model_count = 0
    model_closed = False
    file_ended = False
    saw_atom_record = False
    selected_chain_seen = False
    selected_chain_terminated = False
    provisional: dict[int, dict[str, object]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("MODEL "):
            model_count += 1
            if model_count > 1:
                raise CoordinateGeometryError("PDB input must contain at most one model")
            if saw_atom_record:
                raise CoordinateGeometryError(
                    "MODEL record occurs after coordinate records"
                )
            continue
        if line.startswith("ENDMDL"):
            if model_count != 1 or model_closed:
                raise CoordinateGeometryError("unbalanced ENDMDL record")
            model_closed = True
            continue
        if line.startswith("END"):
            file_ended = True
            continue
        if line.startswith("TER"):
            terminator_chain = line[21:22] if len(line) >= 22 else ""
            if selected_chain_seen and terminator_chain in {"", " ", chain_id}:
                selected_chain_terminated = True
            continue
        if not line.startswith("ATOM  "):
            continue
        saw_atom_record = True
        if model_closed:
            raise CoordinateGeometryError("ATOM record occurs after ENDMDL")
        if file_ended:
            raise CoordinateGeometryError("ATOM record occurs after END")
        if len(line) < 66:
            raise CoordinateGeometryError(
                f"ATOM record {line_number} is too short for fixed-width PDB fields"
            )
        if line[21:22] != chain_id:
            continue
        if selected_chain_terminated:
            raise CoordinateGeometryError(
                "selected chain resumes after TER; multiple segments are ambiguous"
            )
        selected_chain_seen = True
        insertion_code = line[26:27].strip()
        if insertion_code:
            raise CoordinateGeometryError(
                "selected chain contains an insertion code; integer residue ids are ambiguous"
            )
        alternate_location = line[16:17].strip()
        if alternate_location:
            raise CoordinateGeometryError(
                "selected chain contains alternate locations; coordinate choice is ambiguous"
            )
        try:
            residue_number = int(line[22:26])
        except ValueError as exc:
            raise CoordinateGeometryError(
                f"invalid residue number in ATOM record {line_number}"
            ) from exc
        residue_name = line[17:20].strip()
        atom_name = line[12:16].strip()
        if not residue_name or not atom_name:
            raise CoordinateGeometryError(
                f"missing residue or atom name in ATOM record {line_number}"
            )
        element_field = line[76:78].strip().upper() if len(line) >= 78 else ""
        element = element_field or _element_from_atom_name(atom_name)
        if not element.isalpha() or len(element) > 2:
            raise CoordinateGeometryError(
                f"invalid element in ATOM record {line_number}"
            )
        atom = Atom(
            name=atom_name,
            element=element,
            coord=(
                _parse_float(line[30:38], "x coordinate"),
                _parse_float(line[38:46], "y coordinate"),
                _parse_float(line[46:54], "z coordinate"),
            ),
            b_factor=_parse_float(line[60:66], "B-factor"),
        )
        occupancy = _parse_float(line[54:60], "occupancy")
        if not math.isclose(occupancy, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise CoordinateGeometryError(
                "selected chain requires unit occupancy for every accepted atom"
            )

        residue_entry = provisional.setdefault(
            residue_number,
            {"name": residue_name, "atoms": {}},
        )
        if residue_entry["name"] != residue_name:
            raise CoordinateGeometryError(
                f"residue {residue_number} has inconsistent residue names"
            )
        atom_entries = residue_entry["atoms"]
        assert isinstance(atom_entries, dict)
        existing = atom_entries.get(atom_name)
        if existing is not None:
            raise CoordinateGeometryError(
                f"duplicate atom {atom_name} at residue {residue_number}"
            )
        atom_entries[atom_name] = atom

    if model_count == 1 and not model_closed:
        raise CoordinateGeometryError("MODEL record is missing its ENDMDL record")

    if not provisional:
        raise CoordinateGeometryError(f"selected chain {chain_id!r} has no ATOM records")

    residues: dict[int, Residue] = {}
    for residue_number, entry in provisional.items():
        atom_entries = entry["atoms"]
        assert isinstance(atom_entries, dict)
        atoms = tuple(
            atom_entries[name]
            for name in sorted(atom_entries)
        )
        residues[residue_number] = Residue(str(entry["name"]), atoms)
    return residues


def _atom_by_name(residue: Residue, name: str) -> Atom:
    for atom in residue.atoms:
        if atom.name == name:
            return atom
    raise CoordinateGeometryError(f"residue {residue.name} lacks atom {name}")


def _heavy_atoms(residue: Residue) -> tuple[Atom, ...]:
    atoms = tuple(atom for atom in residue.atoms if atom.element != "H")
    if not atoms:
        raise CoordinateGeometryError(f"residue {residue.name} has no heavy atoms")
    return atoms


def _sidechain_atoms(residue: Residue) -> tuple[Atom, ...]:
    return tuple(
        atom
        for atom in _heavy_atoms(residue)
        if atom.name not in _BACKBONE_ATOMS
    )


def _distance(left: Atom, right: Atom) -> float:
    return math.dist(left.coord, right.coord)


def _minimum_distance(left: Iterable[Atom], right: Iterable[Atom]) -> float:
    left_atoms = tuple(left)
    right_atoms = tuple(right)
    if not left_atoms or not right_atoms:
        raise CoordinateGeometryError("minimum distance requires two non-empty atom sets")
    return min(
        _distance(left_atom, right_atom)
        for left_atom in left_atoms
        for right_atom in right_atoms
    )


def _ca_shell(
    residues: dict[int, Residue], residue_number: int, threshold: float
) -> set[int]:
    target = _atom_by_name(residues[residue_number], "CA")
    return {
        other_number
        for other_number, other_residue in residues.items()
        if other_number != residue_number
        and _distance(target, _atom_by_name(other_residue, "CA")) <= threshold
    }


def _sidechain_contacts(
    residues: dict[int, Residue], residue_number: int, threshold: float
) -> set[int]:
    target_atoms = _sidechain_atoms(residues[residue_number])
    if not target_atoms:
        return set()
    return {
        other_number
        for other_number, other_residue in residues.items()
        if other_number != residue_number
        and _minimum_distance(target_atoms, _heavy_atoms(other_residue)) <= threshold
    }


def _nonlocal_members(
    members: set[int], residue_number: int, minimum_separation: int
) -> set[int]:
    return {
        member
        for member in members
        if abs(member - residue_number) >= minimum_separation
    }


def _jaccard(left: set[int], right: set[int]) -> dict[str, object]:
    union = left | right
    intersection = left & right
    return {
        "intersection": sorted(intersection),
        "intersection_count": len(intersection),
        "union_count": len(union),
        "jaccard": round(len(intersection) / len(union), 6) if union else None,
    }


def _polar_proximities(
    residues: dict[int, Residue], residue_number: int, threshold: float
) -> list[dict[str, object]]:
    target_atoms = tuple(
        atom
        for atom in _sidechain_atoms(residues[residue_number])
        if atom.element in _POLAR_ELEMENTS
    )
    rows: list[dict[str, object]] = []
    for other_number, other_residue in residues.items():
        if other_number == residue_number:
            continue
        for target_atom in target_atoms:
            for other_atom in _heavy_atoms(other_residue):
                if other_atom.element not in _POLAR_ELEMENTS:
                    continue
                atom_distance = _distance(target_atom, other_atom)
                if atom_distance <= threshold:
                    rows.append(
                        {
                            "target_atom": target_atom.name,
                            "other_residue": other_number,
                            "other_residue_name": other_residue.name,
                            "other_atom": other_atom.name,
                            "distance_angstrom": round(atom_distance, 3),
                        }
                    )
    return sorted(
        rows,
        key=lambda row: (
            row["distance_angstrom"],
            row["other_residue"],
            row["target_atom"],
            row["other_atom"],
        ),
    )


def analyze_coordinate_geometry(
    pdb_bytes: bytes,
    *,
    source_name: str,
    chain_id: str,
    target_residue: int,
    comparator_residues: Iterable[int],
    ca_shell_threshold_angstrom: float = 10.0,
    sidechain_contact_threshold_angstrom: float = 4.5,
    polar_proximity_threshold_angstrom: float = 3.6,
    nonlocal_sequence_separation_minimum: int = 3,
) -> dict[str, object]:
    """Return deterministic geometry with an explicit non-functional boundary."""

    safe_source_name = _source_name(source_name)
    target = _residue_number(target_residue, "target_residue")
    comparators = tuple(
        sorted(
            _residue_number(value, "comparator_residue")
            for value in comparator_residues
        )
    )
    if not comparators:
        raise CoordinateGeometryError("at least one comparator residue is required")
    if len(set(comparators)) != len(comparators):
        raise CoordinateGeometryError("comparator residues must be unique")
    if target in comparators:
        raise CoordinateGeometryError("target residue cannot also be a comparator")
    if (
        isinstance(nonlocal_sequence_separation_minimum, bool)
        or not isinstance(nonlocal_sequence_separation_minimum, int)
        or nonlocal_sequence_separation_minimum < 1
    ):
        raise CoordinateGeometryError(
            "nonlocal_sequence_separation_minimum must be a positive integer"
        )
    ca_threshold = _finite_positive(
        ca_shell_threshold_angstrom, "ca_shell_threshold_angstrom"
    )
    contact_threshold = _finite_positive(
        sidechain_contact_threshold_angstrom,
        "sidechain_contact_threshold_angstrom",
    )
    polar_threshold = _finite_positive(
        polar_proximity_threshold_angstrom,
        "polar_proximity_threshold_angstrom",
    )
    # Biophysical ceilings: a threshold that swallows the whole chain makes
    # every residue a neighbor and forces jaccard=1.0 for every comparator —
    # a fabricated overlap claim.
    if ca_threshold > 30.0:
        raise CoordinateGeometryError(
            "ca_shell_threshold_angstrom exceeds a plausible neighborhood radius"
        )
    if contact_threshold > 10.0:
        raise CoordinateGeometryError(
            "sidechain_contact_threshold_angstrom exceeds a plausible contact radius"
        )
    if polar_threshold > 10.0:
        raise CoordinateGeometryError(
            "polar_proximity_threshold_angstrom exceeds a plausible contact radius"
        )

    residues = parse_single_model_pdb(pdb_bytes, chain_id)
    requested = {target, *comparators}
    missing = sorted(requested - residues.keys())
    if missing:
        raise CoordinateGeometryError(
            f"requested residues are absent from chain {chain_id}: {missing}"
        )
    for number in requested:
        _atom_by_name(residues[number], "CA")

    ca_shells = {
        number: _ca_shell(residues, number, ca_threshold)
        for number in requested
    }
    sidechain_sets = {
        number: _sidechain_contacts(residues, number, contact_threshold)
        for number in requested
    }
    nonlocal_ca_shells = {
        number: _nonlocal_members(
            members, number, nonlocal_sequence_separation_minimum
        )
        for number, members in ca_shells.items()
    }
    nonlocal_sidechain_sets = {
        number: _nonlocal_members(
            members, number, nonlocal_sequence_separation_minimum
        )
        for number, members in sidechain_sets.items()
    }

    target_record = residues[target]
    target_ca = _atom_by_name(target_record, "CA")
    direct_geometry: list[dict[str, object]] = []
    comparisons: list[dict[str, object]] = []
    for number in comparators:
        comparator = residues[number]
        direct_geometry.append(
            {
                "residue": number,
                "residue_name": comparator.name,
                "ca_distance_angstrom": round(
                    _distance(target_ca, _atom_by_name(comparator, "CA")), 3
                ),
                "minimum_heavy_atom_distance_angstrom": round(
                    _minimum_distance(
                        _heavy_atoms(target_record), _heavy_atoms(comparator)
                    ),
                    3,
                ),
            }
        )
        comparisons.append(
            {
                "residue": number,
                "residue_name": comparator.name,
                "nonlocal_ca_shell_overlap": _jaccard(
                    nonlocal_ca_shells[target], nonlocal_ca_shells[number]
                ),
                "nonlocal_sidechain_contact_overlap": _jaccard(
                    nonlocal_sidechain_sets[target],
                    nonlocal_sidechain_sets[number],
                ),
            }
        )

    summaries: list[dict[str, object]] = []
    for number in sorted(requested):
        residue = residues[number]
        b_factors = [atom.b_factor for atom in residue.atoms]
        summaries.append(
            {
                "residue": number,
                "residue_name": residue.name,
                "mean_b_factor_field": round(sum(b_factors) / len(b_factors), 3),
                "ca_shell_residues": sorted(ca_shells[number]),
                "nonlocal_ca_shell_residues": sorted(nonlocal_ca_shells[number]),
                "sidechain_contact_residues": sorted(sidechain_sets[number]),
                "nonlocal_sidechain_contact_residues": sorted(
                    nonlocal_sidechain_sets[number]
                ),
            }
        )

    return {
        "schema": SCHEMA,
        "script_version": SCRIPT_VERSION,
        "coordinate_only": True,
        "checkpoint_ready": False,
        "probe_eligible": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "input": {
            "source_name": safe_source_name,
            "sha256": hashlib.sha256(pdb_bytes).hexdigest(),
            "chain": chain_id,
            "scope": "one caller-supplied PDB model; selected ATOM chain",
        },
        "parameters": {
            "target_residue": target,
            "comparator_residues": list(comparators),
            "ca_shell_threshold_angstrom": ca_threshold,
            "sidechain_contact_threshold_angstrom": contact_threshold,
            "polar_proximity_threshold_angstrom": polar_threshold,
            "nonlocal_sequence_separation_minimum": (
                nonlocal_sequence_separation_minimum
            ),
        },
        "direct_geometry_from_target": direct_geometry,
        "residue_summaries": summaries,
        "neighborhood_overlap_with_target": comparisons,
        "target_polar_atom_proximities": _polar_proximities(
            residues, target, polar_threshold
        ),
        "interpretation_boundary": [
            "The B-factor field is reported without assuming whether it is an experimental B-factor or a predicted-model confidence score.",
            "Neighborhood overlap compares absolute residue identifiers after the declared sequence-separation filter.",
            "A close or overlapping neighborhood can prioritize an experiment but cannot transfer another residue's phenotype.",
            CLAIM_BOUNDARY,
        ],
    }


def analyze_coordinate_geometry_file(
    pdb_path: Path,
    *,
    source_name: str | None = None,
    chain_id: str,
    target_residue: int,
    comparator_residues: Iterable[int],
    ca_shell_threshold_angstrom: float = 10.0,
    sidechain_contact_threshold_angstrom: float = 4.5,
    polar_proximity_threshold_angstrom: float = 3.6,
    nonlocal_sequence_separation_minimum: int = 3,
) -> dict[str, object]:
    try:
        data = pdb_path.read_bytes()
    except OSError as exc:
        raise CoordinateGeometryError(f"cannot read PDB input: {exc}") from exc
    return analyze_coordinate_geometry(
        data,
        source_name=source_name if source_name is not None else pdb_path.name,
        chain_id=chain_id,
        target_residue=target_residue,
        comparator_residues=comparator_residues,
        ca_shell_threshold_angstrom=ca_shell_threshold_angstrom,
        sidechain_contact_threshold_angstrom=sidechain_contact_threshold_angstrom,
        polar_proximity_threshold_angstrom=polar_proximity_threshold_angstrom,
        nonlocal_sequence_separation_minimum=(
            nonlocal_sequence_separation_minimum
        ),
    )


__all__ = [
    "CLAIM_BOUNDARY",
    "SCHEMA",
    "SCRIPT_VERSION",
    "CoordinateGeometryError",
    "analyze_coordinate_geometry",
    "analyze_coordinate_geometry_file",
    "parse_single_model_pdb",
]
