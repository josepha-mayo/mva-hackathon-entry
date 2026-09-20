# Coordinate-only geometry reproducer

Status: living Phase-2 software surface; identifier-free; not part of the frozen attempt-1 packet and not biological validation.

## Purpose

`src/mva_hackathon/coordinate_geometry.py` computes deterministic distances, local-neighborhood membership, overlap, and polar-atom proximity from one caller-supplied PDB coordinate model. The command-line wrapper records the input content SHA-256 and a caller-safe basename, never an absolute input path.

The engine is case-agnostic and uses only the Python standard library. It accepts an integer target residue, one or more integer comparator residues, one chain, and explicit distance and sequence-separation thresholds. Comparator order is canonicalized. Multiple coordinate models, unbalanced model boundaries, alternate locations, non-unit occupancy, insertion codes, a selected chain resumed after a terminator, missing requested residues, duplicate comparator residues, invalid thresholds, and path-like source names fail closed.

## Synthetic exact-byte demonstration

The checked fixture contains invented SYN residues only:

```powershell
python scripts/run_coordinate_geometry.py `
  --pdb templates/community/coordinate_model.synthetic.pdb `
  --chain A `
  --target 10 `
  --comparators 20 30 `
  --source-name coordinate_model.synthetic.pdb `
  --ca-shell 6 `
  --sidechain-contact 1.5 `
  --polar-proximity 1.5
```

The canonical output is `reports/TRACK2_COORDINATE_GEOMETRY_SYNTHETIC.json`. Its byte-for-byte canonical rendering is a unit test. Supplying `--output` refuses to overwrite an existing receipt.

## Interpretation boundary

This is coordinate bookkeeping, not structural prediction. It does not calculate solvent accessibility, free-energy change, mutant relaxation, dynamics, docking, pathogenicity, target engagement, efficacy, safety, or clinical benefit. The B-factor column is reported without assuming whether it represents an experimental B-factor or a predicted-model confidence score.

Overlap uses absolute residue identifiers after the declared sequence-separation filter. A zero overlap can reflect the chosen threshold, residue numbering, or different local membership; it does not establish equivalent or different chemistry. A nearby or overlapping comparator may change the order of wet experiments but cannot transfer another residue's phenotype or make a candidate eligible. Geometry ranking is a separate stop-early pipeline gate before confirmation; marking it `used_as_function`, claiming an analog or nearby residue as exact, or substituting FoldX, AlphaMissense, an in-silico pathogenicity score, ESM, REVEL, or MAVE cannot open confirmation.

Filled case-specific receipts stay outside the public living tree until the exact bytes receive release review and are deliberately bound into a future reproducibility manifest. The generic engine and its synthetic fixture do not authorize that publication, a freeze, or a submission.
