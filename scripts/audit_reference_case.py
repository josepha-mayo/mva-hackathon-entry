"""Reproduce the reported codon, exon and peptide checks on public references.

This narrow audit compares the annotated protein with an independently
obtained protein sequence and checks only the reported codons. It does not
translate the complete CDS, infer a sample genotype or predict assay success.
No network requests are made.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

MAX_BYTES = 1024 * 1024
REPORTED_CODONS = {"TTA": "L", "TGA": "*", "AAT": "N", "AAG": "K", "AAA": "K"}


def _read(path: Path) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("reference input is empty or exceeds the size limit")
    return raw


def _peptides(protein: str) -> list[dict]:
    pieces, start = [], 0
    for index, residue in enumerate(protein):
        cleavage = residue in ("K", "R") and (index + 1 == len(protein) or protein[index + 1] != "P")
        if cleavage or index + 1 == len(protein):
            pieces.append({"start": start + 1, "end": index + 1,
                           "sequence": protein[start:index + 1], "length": index + 1 - start})
            start = index + 1
    return pieces


def audit_case(record: bytes, independent_protein: bytes, version: str, digest: str) -> dict:
    if hashlib.sha256(record).hexdigest() != digest or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("source digest does not match")
    text = record.decode("ascii")
    if re.findall(r"^VERSION\s+(\S+)\s*$", text, re.M) != [version]:
        raise ValueError("reference version is missing, ambiguous or unexpected")
    if (any(v != "1" for v in re.findall(r"/transl_table=(\d+)", text))
            or any(v != "1" for v in re.findall(r"/codon_start=(\d+)", text)) or "/transl_except=" in text):
        raise ValueError("nonstandard translation is outside this narrow audit")
    cds_fields = re.findall(r"^     CDS\s+(.+)$", text, re.M)
    if len(cds_fields) != 1 or not re.fullmatch(r"\d+\.\.\d+", cds_fields[0]):
        raise ValueError("one complete contiguous CDS is required")
    start, end = map(int, cds_fields[0].split(".."))
    origins = re.findall(r"^ORIGIN\s*\n([\s\S]*?)^//\s*$", text, re.M)
    if len(origins) != 1 or not re.fullmatch(r"[acgtACGT0-9\s]+", origins[0]):
        raise ValueError("one unambiguous DNA origin is required")
    transcript = re.sub(r"[0-9\s]", "", origins[0]).upper()
    if not 1 <= start <= end <= len(transcript):
        raise ValueError("CDS bounds are invalid")
    cds = transcript[start - 1:end]
    annotations = re.findall(r'/translation="([^"]+)"', text)
    if len(annotations) != 1:
        raise ValueError("one annotated protein is required")
    protein = "".join(annotations[0].split())
    lines = independent_protein.decode("ascii").splitlines()
    if not lines or not lines[0].startswith(">") or any(s.startswith(">") for s in lines[1:]):
        raise ValueError("one independent protein record is required")
    if not protein or protein != "".join(lines[1:]) or not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", protein):
        raise ValueError("independent protein differs from the annotated protein")
    if len(cds) != 3 * (len(protein) + 1) or cds[:3] != "ATG" or cds[-3:] not in ("TAA", "TAG", "TGA"):
        raise ValueError("CDS length, start or terminal stop disagrees with the annotation")
    exon_fields = re.findall(r"^     exon\s+(.+)$", text, re.M)
    if not exon_fields or any(not re.fullmatch(r"\d+\.\.\d+", s) for s in exon_fields):
        raise ValueError("complete exon coordinates are required")
    exons = [tuple(map(int, s.split(".."))) for s in exon_fields]
    if (any(a > b for a, b in exons) or exons[0][0] != 1 or exons[-1][1] != len(transcript)
            or any(a[1] + 1 != b[0] for a, b in zip(exons, exons[1:]))):
        raise ValueError("exons must partition the transcript in order")
    rows = []
    for position, alternate, expected_codon in ((2210, "G", "TTA"), (3006, "G", "AAT"), (3006, "A", "AAT")):
        index = position - 1
        codon_index = index // 3 * 3
        reference_codon = cds[codon_index:codon_index + 3]
        if reference_codon != expected_codon:
            raise ValueError("reference does not have the reported case codon")
        aa_position = index // 3 + 1
        if protein[aa_position - 1] != REPORTED_CODONS[reference_codon]:
            raise ValueError("reported codon and annotated residue disagree")
        changed = reference_codon[:index % 3] + alternate + reference_codon[index % 3 + 1:]
        amino_acid = REPORTED_CODONS[changed]
        altered = protein[:aa_position - 1] if amino_acid == "*" else protein[:aa_position - 1] + amino_acid + protein[aa_position:]
        reference_piece = next(p for p in _peptides(protein) if p["start"] <= aa_position <= p["end"])
        variant_pieces = [p for p in _peptides(altered) if p["start"] <= reference_piece["end"] and p["end"] >= reference_piece["start"]]
        transcript_position = start + index
        exon_number = next(i for i, (a, b) in enumerate(exons, 1) if a <= transcript_position <= b)
        codon_end = start + codon_index + 2
        rows.append({"coding_position": position, "alternate_base": alternate,
            "reference_codon": reference_codon, "alternate_codon": changed,
            "amino_acid_position": aa_position, "alternate_amino_acid": amino_acid,
            "transcript_position": transcript_position, "exon_number": exon_number,
            "exon_position": transcript_position - exons[exon_number - 1][0] + 1,
            "downstream_junction_offsets_from_codon_end": [b - codon_end for _, b in exons[:-1] if b > codon_end],
            "reference_spanning_peptide": reference_piece,
            "variant_pieces_over_reference_span": variant_pieces})
    return {"schema": "mva.reported-reference-case/v1", "reference_version": version,
        "source_sha256": digest, "independent_protein_sha256": hashlib.sha256(independent_protein).hexdigest(),
        "annotated_protein_concordant": True, "full_cds_translation_checked": False,
        "protein_length": len(protein), "exon_count": len(exons), "cds_bounds": [start, end], "changes": rows,
        "claim_boundary": "Public-reference annotation concordance and reported-codon/coordinate/ideal-cleavage arithmetic only. Not full-CDS translation, sample confirmation, phase, splicing, detectability, drug response or clinical benefit."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--protein", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    try:
        result = audit_case(_read(args.record), _read(args.protein), args.expected_version, args.expected_sha256)
    except (OSError, ValueError, IndexError, KeyError, StopIteration) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
