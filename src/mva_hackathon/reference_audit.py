"""Public-reference arithmetic, independent of participant genotype inference.

Only a single complete, contiguous CDS and exon map are supported. Reference
translation must agree with both its annotation and an independent FASTA.
This module does not predict pathogenicity, splicing, expression or rescue.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


class ReferenceAuditError(ValueError):
    """The input is unsupported, inconsistent or outside this audit's scope."""


# Standard nuclear code, in T/C/A/G order at each codon position.
_BASES = "TCAG"
_AMINO_ACIDS = (
    "FFLLSSSSYY**CC*W"
    "LLLLPPPPHHQQRRRR"
    "IIIMTTTTNNKKSSRR"
    "VVVVAAAADDEEGGGG"
)
_CODONS = {
    a + b + c: aa
    for (a, b, c), aa in zip(
        ((a, b, c) for a in _BASES for b in _BASES for c in _BASES),
        _AMINO_ACIDS,
    )
}
_PROTEIN = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]+")
MAX_SOURCE_BYTES = 1024 * 1024


def _decode(raw: bytes, label: str) -> str:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ReferenceAuditError(f"{label} must be 1..{MAX_SOURCE_BYTES} bytes")
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ReferenceAuditError(f"{label} must be ASCII") from exc


def _peptide(protein: str, position: int) -> dict[str, Any] | None:
    if not 1 <= position <= len(protein):
        return None
    start = 0
    for i, aa in enumerate(protein):
        if (aa in "KR" and (i + 1 == len(protein) or protein[i + 1] != "P")) or i + 1 == len(protein):
            end = i + 1
            if start < position <= end:
                return {"start": start + 1, "end": end, "sequence": protein[start:end], "length": end - start}
            start = end
    raise AssertionError("peptide map did not cover the protein")


def audit_public_reference(
    genbank: bytes,
    fasta: bytes,
    changes: list[tuple[int, str]],
    *,
    expected_version: str,
    expected_genbank_sha256: str,
) -> dict[str, Any]:
    """Validate references, then map hypothetical single-base substitutions.

    Changes use one-based coding positions. Each is applied independently to
    the reference, never as a phased haplotype. Ideal trypsin cleavage assumes
    no missed cleavages; it establishes no analytical assay performance.
    """
    text = _decode(genbank, "GenBank")
    protein_text = _decode(fasta, "FASTA")
    digest = hashlib.sha256(genbank).hexdigest()
    if not isinstance(expected_genbank_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_genbank_sha256):
        raise ReferenceAuditError("an expected SHA-256 is required")
    if digest != expected_genbank_sha256:
        raise ReferenceAuditError("GenBank bytes differ from the expected source digest")
    versions = re.findall(r"^VERSION\s+(\S+)\s*$", text, re.M)
    if versions != [expected_version]:
        raise ReferenceAuditError("reference version is missing, ambiguous or unexpected")
    if (any(value != "1" for value in re.findall(r"/transl_table=(\d+)", text))
            or any(value != "1" for value in re.findall(r"/codon_start=(\d+)", text))
            or "/transl_except=" in text):
        raise ReferenceAuditError("only an unmodified standard-code CDS starting at codon base one is supported")
    cds_fields = re.findall(r"^     CDS\s+(.+)$", text, re.M)
    if len(cds_fields) != 1 or not re.fullmatch(r"\d+\.\.\d+", cds_fields[0]):
        raise ReferenceAuditError("only one complete contiguous CDS is supported")
    cds_start, cds_end = map(int, cds_fields[0].split(".."))
    origins = re.findall(r"^ORIGIN\s*\n([\s\S]*?)^//\s*$", text, re.M)
    if len(origins) != 1 or not re.fullmatch(r"[acgtACGT0-9\s]+", origins[0]):
        raise ReferenceAuditError("one unambiguous DNA origin is required")
    sequence = re.sub(r"[0-9\s]", "", origins[0]).upper()
    if not 1 <= cds_start <= cds_end <= len(sequence):
        raise ReferenceAuditError("CDS lies outside the transcript")
    exon_fields = re.findall(r"^     exon\s+(.+)$", text, re.M)
    if not exon_fields or any(not re.fullmatch(r"\d+\.\.\d+", s) for s in exon_fields):
        raise ReferenceAuditError("complete contiguous exon coordinates are required")
    exons = [tuple(map(int, s.split(".."))) for s in exon_fields]
    if (any(start > end for start, end in exons) or exons[0][0] != 1
            or exons[-1][1] != len(sequence)
            or any(a[1] + 1 != b[0] for a, b in zip(exons, exons[1:]))):
        raise ReferenceAuditError("exons must partition the transcript in order")
    cds = sequence[cds_start - 1:cds_end]
    if len(cds) < 6 or len(cds) % 3 or cds[:3] != "ATG":
        raise ReferenceAuditError("CDS must have a complete standard start and codon frame")
    translation = "".join(_CODONS[cds[i:i + 3]] for i in range(0, len(cds), 3))
    if translation[-1] != "*" or "*" in translation[:-1]:
        raise ReferenceAuditError("CDS must have one terminal stop and no internal stops")
    protein = translation[:-1]
    annotations = re.findall(r'/translation="([^"]+)"', text)
    if len(annotations) != 1 or "".join(annotations[0].split()) != protein:
        raise ReferenceAuditError("CDS translation disagrees with protein annotation")
    lines = protein_text.splitlines()
    if not lines or not lines[0].startswith(">") or any(s.startswith(">") for s in lines[1:]):
        raise ReferenceAuditError("exactly one FASTA record is required")
    other_protein = "".join(lines[1:])
    if not _PROTEIN.fullmatch(other_protein) or other_protein != protein:
        raise ReferenceAuditError("independent protein reference disagrees with CDS translation")
    if not isinstance(changes, list) or not changes:
        raise ReferenceAuditError("at least one hypothetical substitution is required")
    rows, seen = [], set()
    for change in changes:
        if not isinstance(change, (tuple, list)) or len(change) != 2:
            raise ReferenceAuditError("a change must contain a position and alternate base")
        position, alt = change
        if (type(position) is not int or not 1 <= position <= len(cds) - 3
                or not isinstance(alt, str) or alt not in ("A", "C", "G", "T")):
            raise ReferenceAuditError("substitution must address a coding base before the native stop")
        if (position, alt) in seen or cds[position - 1] == alt:
            raise ReferenceAuditError("duplicate or unchanged substitution")
        seen.add((position, alt))
        index = position - 1
        codon_start = index // 3 * 3
        codon = cds[codon_start:codon_start + 3]
        changed = codon[:index % 3] + alt + codon[index % 3 + 1:]
        aa_position = index // 3 + 1
        aa = _CODONS[changed]
        variant_protein = protein[:aa_position - 1] if aa == "*" else protein[:aa_position - 1] + aa + protein[aa_position:]
        transcript_position = cds_start + index
        exon_index = next(i for i, (start, end) in enumerate(exons) if start <= transcript_position <= end)
        codon_end = cds_start + codon_start + 2
        rows.append({
            "coding_position": position, "reference_base": cds[index], "alternate_base": alt,
            "reference_codon": codon, "alternate_codon": changed,
            "amino_acid_position": aa_position, "reference_amino_acid": protein[aa_position - 1], "alternate_amino_acid": aa,
            "transcript_position": transcript_position, "exon_number": exon_index + 1,
            "exon_position": transcript_position - exons[exon_index][0] + 1,
            "last_exon": exon_index + 1 == len(exons),
            "downstream_junction_offsets_from_codon_end": [end - codon_end for _, end in exons[:-1] if end > codon_end],
            "reference_tryptic_peptide": _peptide(protein, aa_position),
            "alternate_tryptic_peptide": _peptide(variant_protein, aa_position),
        })
    return {
        "schema": "mva.public-reference-audit/v1", "reference_version": expected_version,
        "genbank_sha256": digest, "fasta_sha256": hashlib.sha256(fasta).hexdigest(),
        "transcript_length": len(sequence), "protein_length": len(protein), "exon_count": len(exons),
        "cds_bounds": [cds_start, cds_end], "translation_concordant": True, "changes": rows,
        "claim_boundary": "Public-reference arithmetic for independent hypothetical substitutions only. Not sample confirmation, phase, splicing, pathogenicity, peptide detectability, drug response or clinical benefit.",
    }
