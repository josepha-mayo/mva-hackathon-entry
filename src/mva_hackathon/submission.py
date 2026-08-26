"""Strict Track 1 CSV parsing and preflight validation."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

Variant = tuple[str, int, str, str]

REQUIRED_FIELDS = (
    "proband_id",
    "chrom_1",
    "pos_1",
    "ref_1",
    "alt_1",
    "chrom_2",
    "pos_2",
    "ref_2",
    "alt_2",
    "epcr",
    "finding_type",
    "notes",
)

_CHROMOSOMES = {f"chr{i}" for i in range(1, 23)} | {"chrX", "chrY", "chrM"}
_GRCH38_LENGTHS = {
    "chr1": 248_956_422, "chr2": 242_193_529, "chr3": 198_295_559,
    "chr4": 190_214_555, "chr5": 181_538_259, "chr6": 170_805_979,
    "chr7": 159_345_973, "chr8": 145_138_636, "chr9": 138_394_717,
    "chr10": 133_797_422, "chr11": 135_086_622, "chr12": 133_275_309,
    "chr13": 114_364_328, "chr14": 107_043_718, "chr15": 101_991_189,
    "chr16": 90_338_345, "chr17": 83_257_441, "chr18": 80_373_285,
    "chr19": 58_617_616, "chr20": 64_444_167, "chr21": 46_709_983,
    "chr22": 50_818_468, "chrX": 156_040_895, "chrY": 57_227_415,
    "chrM": 16_569,
}
_REF_ALLELE = re.compile(r"^[ACGTN]+$", re.IGNORECASE)
_ALT_ALLELE = re.compile(r"^(?:[ACGTN]+|\*|<[A-Z0-9:_-]+>)$", re.IGNORECASE)
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SubmissionError(ValueError):
    """Raised when a Track 1 file would be rejected or is strategically unsafe."""


@dataclass(frozen=True)
class Prediction:
    proband_id: str
    variants: frozenset[Variant]
    epcr: float
    finding_type: str
    notes: str
    source_row: int


def _variant(chrom: str, pos: str, ref: str, alt: str, *, row: int) -> Variant:
    chrom = chrom.strip()
    ref = ref.strip().upper()
    alt = alt.strip().upper()
    if chrom not in _CHROMOSOMES:
        raise SubmissionError(f"row {row}: chromosome must be GRCh38-style chr1..chr22/chrX/chrY/chrM")
    try:
        position = int(pos)
    except ValueError as exc:
        raise SubmissionError(f"row {row}: position is not an integer") from exc
    if position < 1:
        raise SubmissionError(f"row {row}: position must be positive")
    if position > _GRCH38_LENGTHS[chrom]:
        raise SubmissionError(f"row {row}: position exceeds the GRCh38 {chrom} length")
    if not _REF_ALLELE.fullmatch(ref):
        raise SubmissionError(f"row {row}: REF must be a non-empty A/C/G/T/N sequence")
    if not _ALT_ALLELE.fullmatch(alt):
        raise SubmissionError(f"row {row}: ALT must be a sequence, *, or symbolic VCF allele")
    if ref == alt:
        raise SubmissionError(f"row {row}: REF and ALT cannot be identical")
    return (chrom, position, ref, alt)


def load_predictions_bytes(data: bytes) -> list[Prediction]:
    """Validate an in-memory Track 1 CSV using the canonical parser."""

    if data[:3] == b"\xef\xbb\xbf":
        raise SubmissionError("UTF-8 BOM is unsafe: the official scorer treats it as part of the first header")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SubmissionError("submission CSV must be strict UTF-8") from exc

    predictions: list[Prediction] = []
    seen: set[frozenset[Variant]] = set()
    previous_epcr: float | None = None
    secondary_started = False

    with io.StringIO(text, newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SubmissionError("missing CSV header")
        missing = [field for field in REQUIRED_FIELDS if field not in reader.fieldnames]
        unknown = [field for field in reader.fieldnames if field not in REQUIRED_FIELDS]
        duplicates = sorted({field for field in reader.fieldnames if reader.fieldnames.count(field) > 1})
        if missing or unknown or duplicates:
            raise SubmissionError(
                f"schema mismatch; missing={missing}, unknown={unknown}, duplicates={duplicates}"
            )
        if tuple(reader.fieldnames) != REQUIRED_FIELDS:
            raise SubmissionError("schema mismatch; header order differs from the frozen organizer template")

        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise SubmissionError(f"row {row_number}: surplus CSV fields")
            if len(predictions) >= 10:
                raise SubmissionError("at most 10 candidate rows are accepted")
            proband_id = (row["proband_id"] or "").strip()
            if proband_id != "PROBAND01":
                raise SubmissionError(f"row {row_number}: only PROBAND01 is accepted")

            first = _variant(
                row["chrom_1"] or "",
                row["pos_1"] or "",
                row["ref_1"] or "",
                row["alt_1"] or "",
                row=row_number,
            )

            second_values = [
                (row["chrom_2"] or "").strip(),
                (row["pos_2"] or "").strip(),
                (row["ref_2"] or "").strip(),
                (row["alt_2"] or "").strip(),
            ]
            if any(second_values) and not all(second_values):
                raise SubmissionError(f"row {row_number}: compound-het second allele fields are all-or-none")
            second = _variant(*second_values, row=row_number) if all(second_values) else None
            if second == first:
                raise SubmissionError(f"row {row_number}: a pair cannot repeat the same allele")
            variants = frozenset((first, second)) if second else frozenset((first,))
            if variants in seen:
                raise SubmissionError(f"row {row_number}: duplicate candidate")
            seen.add(variants)

            try:
                epcr = float((row["epcr"] or "").strip())
            except ValueError as exc:
                raise SubmissionError(f"row {row_number}: EPCR is not numeric") from exc
            if not 0 < epcr <= 1:
                raise SubmissionError(f"row {row_number}: EPCR must be in (0, 1]")
            if previous_epcr is not None and epcr >= previous_epcr:
                raise SubmissionError(
                    f"row {row_number}: EPCR must be strictly decreasing; ties enter the F-max threshold together"
                )
            previous_epcr = epcr

            finding_type = (row["finding_type"] or "").strip().lower()
            if finding_type not in {"primary", "secondary"}:
                raise SubmissionError(f"row {row_number}: finding_type must be primary or secondary")
            if finding_type == "secondary":
                secondary_started = True
            elif secondary_started:
                raise SubmissionError(
                    f"row {row_number}: primary candidates must precede every secondary finding"
                )

            notes = (row["notes"] or "").strip()
            if len(notes) > 1_000:
                raise SubmissionError(f"row {row_number}: notes exceed the 1000-character project limit")
            if _CONTROL_CHARACTERS.search(notes):
                raise SubmissionError(f"row {row_number}: notes contain control characters")
            if notes.startswith(("=", "+", "-", "@")):
                raise SubmissionError(f"row {row_number}: notes begin with a spreadsheet-formula character")

            predictions.append(
                Prediction(
                    proband_id=proband_id,
                    variants=variants,
                    epcr=epcr,
                    finding_type=finding_type,
                    notes=notes,
                    source_row=row_number,
                )
            )

    if not predictions:
        raise SubmissionError("no prediction rows found")
    return predictions


def load_predictions(path: str | Path) -> list[Prediction]:
    """Load one-proband predictions and enforce the live challenge schema."""

    return load_predictions_bytes(Path(path).read_bytes())
