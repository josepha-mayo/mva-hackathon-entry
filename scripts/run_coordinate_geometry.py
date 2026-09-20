from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.coordinate_geometry import (  # noqa: E402
    CoordinateGeometryError,
    analyze_coordinate_geometry_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compute deterministic, coordinate-only distances and neighborhood "
            "overlap without treating geometry as function or efficacy."
        )
    )
    parser.add_argument("--pdb", required=True, type=Path)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--target", required=True, type=int)
    parser.add_argument("--comparators", required=True, nargs="+", type=int)
    parser.add_argument("--source-name")
    parser.add_argument("--ca-shell", type=float, default=10.0)
    parser.add_argument("--sidechain-contact", type=float, default=4.5)
    parser.add_argument("--polar-proximity", type=float, default=3.6)
    parser.add_argument("--nonlocal-separation", type=int, default=3)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    try:
        result = analyze_coordinate_geometry_file(
            arguments.pdb,
            source_name=arguments.source_name,
            chain_id=arguments.chain,
            target_residue=arguments.target,
            comparator_residues=arguments.comparators,
            ca_shell_threshold_angstrom=arguments.ca_shell,
            sidechain_contact_threshold_angstrom=arguments.sidechain_contact,
            polar_proximity_threshold_angstrom=arguments.polar_proximity,
            nonlocal_sequence_separation_minimum=arguments.nonlocal_separation,
        )
    except CoordinateGeometryError as exc:
        parser.error(str(exc))

    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is not None:
        if os.path.lexists(arguments.output):
            parser.error("output already exists; refusing to overwrite")
        target = arguments.output.absolute()
        for ancestor in (target, *target.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                parser.error("output path resolves through a link")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
