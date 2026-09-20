"""Centered k-mer allele confirmation for private FASTQ streams.

This is a presence check against caller-supplied alleles. It is not a
variant caller, not a phasing method, and not evidence of pathogenicity or
efficacy. Real challenge files must stay under a private root; public tests
use in-memory synthetic reads only.

Production confirmation streams records and never materializes an 85 GB
read list. A truncated five-file download cannot confirm even if k-mers
look abundant. Both strands are counted; a reverse-complement-only
observation is still an observation. A filename digest can refuse a
random eight-file set without storing gated names in this tree.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "mva-track2-allele-confirmation/v1"
K_SIZES = (31, 51)
MINIMUM_OBSERVATIONS = 8
DEFAULT_EXPECTED_N_FILES = 8
# SHA-256 of sorted lowercase FASTQ filenames from the pinned gated listing.
# Filenames themselves are not stored in this public tree.
PINNED_DATASET_REVISION = "f534cb0c1a607110c6dad0194299bd3dd62df542"
PINNED_FASTQ_NAME_DIGEST = (
    "a8790de945507c2a3784349bdae404710fd38e0fb8fc2f05100ca059f704334a"
)
CLAIM_BOUNDARY = (
    "Centered k-mer presence check only; not a variant caller, not phase, "
    "not pathogenicity, and not efficacy."
)
STATUSES = (
    "both_alleles_observed",
    "alternate_not_observed",
    "reference_not_observed",
    "neither_observed",
    "insufficient_observations",
    "incomplete_inputs",
    "malformed_allele",
)
MATE_TOKEN_RE = re.compile(r"(?i)(?:^|[._-])(r[12])(?:[._-]|$)")


class AlleleConfirmationError(ValueError):
    """Raised when the confirmation contract is malformed."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AlleleConfirmationError(f"{field} must be non-empty text")
    return value


def _bases(value: object, field: str) -> str:
    text = _text(value, field).upper()
    if any(base not in "ACGT" for base in text):
        raise AlleleConfirmationError(f"{field} must contain only A, C, G, or T")
    return text


_COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence: str) -> str:
    """Return the reverse complement of an ACGT sequence."""

    if not isinstance(sequence, str):
        raise AlleleConfirmationError("reads must be text")
    return sequence.upper().translate(_COMPLEMENT)[::-1]


def centered_kmers(
    *,
    flank_left: str,
    ref: str,
    alt: str,
    flank_right: str,
    k: int,
) -> tuple[str, str]:
    """Return unique-length centered reference and alternate k-mers."""

    if k not in K_SIZES or k % 2 == 0:
        raise AlleleConfirmationError("k must be a supported odd size")
    left = _bases(flank_left, "flank_left")
    right = _bases(flank_right, "flank_right")
    ref_base = _bases(ref, "ref")
    alt_base = _bases(alt, "alt")
    if len(ref_base) != 1 or len(alt_base) != 1:
        raise AlleleConfirmationError("only single-base substitutions are supported")
    if ref_base == alt_base:
        raise AlleleConfirmationError("ref and alt must differ")
    side = k // 2
    if len(left) < side or len(right) < side:
        raise AlleleConfirmationError("flanks are shorter than the requested k-mer")
    ref_kmer = left[-side:] + ref_base + right[:side]
    alt_kmer = left[-side:] + alt_base + right[:side]
    if ref_kmer == alt_kmer:
        raise AlleleConfirmationError("reference and alternate k-mers are not distinct")
    if ref_kmer == reverse_complement(alt_kmer):
        raise AlleleConfirmationError(
            "reference and alternate k-mers are reverse-complement equivalent"
        )
    return ref_kmer, alt_kmer


def count_kmers(sequences: Iterable[str], kmers: Sequence[str]) -> dict[str, int]:
    """Count whole-read occurrences of each k-mer on both strands."""

    wanted = tuple(kmers)
    counts = {kmer: 0 for kmer in wanted}
    for sequence in sequences:
        if not isinstance(sequence, str):
            raise AlleleConfirmationError("reads must be text")
        _accumulate_counts(sequence, counts)
    return counts


def _accumulate_counts(sequence: str, counts: dict[str, int]) -> None:
    upper = sequence.upper()
    rc = reverse_complement(upper)
    for kmer in counts:
        if kmer in upper or kmer in rc:
            counts[kmer] += 1


def _mate_stem(name: str) -> tuple[str, str] | None:
    match = MATE_TOKEN_RE.search(name)
    if match is None:
        return None
    token = match.group(1).lower()
    stem = (name[: match.start(1)] + "rx" + name[match.end(1) :]).lower()
    return stem, token


def fastq_name_digest(paths: Sequence[Path]) -> str:
    """Return SHA-256 of sorted lowercase filenames. Names are not stored."""

    names = "\n".join(sorted(path.name.lower() for path in paths))
    return hashlib.sha256(names.encode("utf-8")).hexdigest()


def assess_fastq_layout(
    paths: Sequence[Path],
    *,
    expected_n_files: int = DEFAULT_EXPECTED_N_FILES,
    expected_name_digest: str | None = None,
) -> dict[str, Any]:
    """Require the full paired lane set before confirmation can pass."""

    if (
        isinstance(expected_n_files, bool)
        or not isinstance(expected_n_files, int)
        or expected_n_files < DEFAULT_EXPECTED_N_FILES
    ):
        raise AlleleConfirmationError(
            "expected file count cannot drop below the declared lane floor "
            f"of {DEFAULT_EXPECTED_N_FILES} (paired lanes)"
        )
    if not paths:
        raise AlleleConfirmationError("at least one FASTQ path is required")
    names = [path.name for path in paths]
    n_files = len(names)
    reasons: list[str] = []
    if n_files < expected_n_files:
        reasons.append("fewer_files_than_expected")
    elif n_files > expected_n_files:
        reasons.append("more_files_than_expected")

    mates: dict[str, dict[str, int]] = {}
    unlabeled = 0
    for name in names:
        parsed = _mate_stem(name)
        if parsed is None:
            unlabeled += 1
            continue
        stem, token = parsed
        bucket = mates.setdefault(stem, {"r1": 0, "r2": 0})
        bucket[token] += 1

    unpaired = 0
    duplicate_mates = 0
    paired_stems = 0
    for bucket in mates.values():
        if bucket["r1"] > 1 or bucket["r2"] > 1:
            duplicate_mates += 1
        if bucket["r1"] == 1 and bucket["r2"] == 1:
            paired_stems += 1
        elif bucket["r1"] or bucket["r2"]:
            unpaired += 1

    if unlabeled:
        reasons.append("unlabeled_mates")
    if unpaired:
        reasons.append("unpaired_mates")
    if duplicate_mates:
        reasons.append("duplicate_mates")
    if expected_n_files > 1 and mates and paired_stems * 2 != n_files - unlabeled:
        if "unpaired_mates" not in reasons and unpaired:
            reasons.append("unpaired_mates")

    digest = fastq_name_digest(paths)
    if expected_name_digest is not None and digest != expected_name_digest:
        reasons.append("name_digest_mismatch")

    reasons = list(dict.fromkeys(reasons))
    return {
        "n_files": n_files,
        "expected_n_files": expected_n_files,
        "paired_stems": paired_stems,
        "unpaired_stems": unpaired,
        "unlabeled_files": unlabeled,
        "name_digest": digest,
        "incomplete": bool(reasons),
        "reasons": reasons,
    }


_IUPAC = re.compile(r"[ACGTRYSWKMBDHVNacgtryswkmbdhvn]+")


def _readline_ascii(handle: Any) -> str | None:
    line = handle.readline()
    if line == b"":
        return None
    return line.decode("ascii").rstrip("\r\n")


class FastqSequenceStream:
    """Yield sequences from a gzip or plain FASTQ without loading the file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.incomplete = False
        self.n_reads = 0

    def __iter__(self) -> Iterator[str]:
        self.incomplete = False
        self.n_reads = 0
        yielded = False
        with self.path.open("rb") as raw:
            magic = raw.read(2)
            raw.seek(0)
            gzip_handle = (
                gzip.GzipFile(fileobj=raw, mode="rb") if magic == b"\x1f\x8b" else None
            )
            handle: Any = gzip_handle if gzip_handle is not None else raw
            try:
                while True:
                    try:
                        header = _readline_ascii(handle)
                    except (EOFError, OSError, gzip.BadGzipFile):
                        if not yielded:
                            raise AlleleConfirmationError("gzip FASTQ is not readable")
                        self.incomplete = True
                        break
                    if header is None:
                        break
                    try:
                        sequence = _readline_ascii(handle)
                        plus = _readline_ascii(handle)
                        quality = _readline_ascii(handle)
                    except (EOFError, OSError, gzip.BadGzipFile):
                        self.incomplete = True
                        break
                    if sequence is None or plus is None or quality is None:
                        self.incomplete = True
                        break
                    if not header.startswith("@") or not plus.startswith("+"):
                        raise AlleleConfirmationError("FASTQ record is malformed")
                    if not sequence or not _IUPAC.fullmatch(sequence):
                        raise AlleleConfirmationError(
                            "FASTQ sequence is not IUPAC bases"
                        )
                    if len(quality) != len(sequence):
                        raise AlleleConfirmationError(
                            "FASTQ quality length does not match sequence"
                        )
                    yielded = True
                    self.n_reads += 1
                    yield sequence
            except UnicodeDecodeError as exc:
                raise AlleleConfirmationError("FASTQ is not ascii text") from exc
            finally:
                if gzip_handle is not None:
                    gzip_handle.close()


def iter_fastq_sequences(path: Path) -> tuple[list[str], bool]:
    """Parse a small FASTQ into a list. Use FastqSequenceStream for large files."""

    stream = FastqSequenceStream(path)
    sequences = list(stream)
    return sequences, stream.incomplete


def _require_minimum(minimum: int) -> int:
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or minimum < MINIMUM_OBSERVATIONS
    ):
        raise AlleleConfirmationError(
            "minimum cannot be below the declared observation floor"
        )
    return minimum


def _exclusive_allele_counts(
    sequences: Iterable[str],
    pairs: Sequence[tuple[str, str]],
) -> list[tuple[int, int]]:
    """Count reads that unambiguously support one allele per (allele, k) pair.

    A read containing both the reference and alternate k-mers of the same
    locus is ambiguous and counts for neither allele.
    """

    counts = [[0, 0] for _ in pairs]
    for sequence in sequences:
        if not isinstance(sequence, str):
            raise AlleleConfirmationError("reads must be text")
        upper = sequence.upper()
        rc = reverse_complement(upper)
        for index, (ref_kmer, alt_kmer) in enumerate(pairs):
            has_ref = ref_kmer in upper or ref_kmer in rc
            has_alt = alt_kmer in upper or alt_kmer in rc
            if has_ref != has_alt:
                counts[index][0 if has_ref else 1] += 1
    return [(ref, alt) for ref, alt in counts]


def classify_counts(
    *,
    reference_count: int,
    alternate_count: int,
    incomplete: bool,
    minimum: int = MINIMUM_OBSERVATIONS,
) -> str:
    minimum = _require_minimum(minimum)
    if incomplete:
        return "incomplete_inputs"
    if reference_count < 0 or alternate_count < 0:
        raise AlleleConfirmationError("counts must be non-negative")
    if reference_count == 0 and alternate_count == 0:
        return "neither_observed"
    if reference_count == 0:
        return "reference_not_observed"
    if alternate_count == 0:
        return "alternate_not_observed"
    if reference_count < minimum or alternate_count < minimum:
        return "insufficient_observations"
    return "both_alleles_observed"


def _allele_pairs(
    alleles: Sequence[Mapping[str, Any]],
    k_sizes: Sequence[int],
) -> list[tuple[str, str]]:
    """Reference/alternate k-mer pairs in (allele, k) order."""

    pairs = []
    for allele in alleles:
        for k in k_sizes:
            pairs.append(
                centered_kmers(
                    flank_left=allele["flank_left"],
                    ref=allele["ref"],
                    alt=allele["alt"],
                    flank_right=allele["flank_right"],
                    k=k,
                )
            )
    return pairs


def _allele_rows(
    alleles: Sequence[Mapping[str, Any]],
    pair_counts: Sequence[tuple[int, int]],
    *,
    incomplete: bool,
    k_sizes: Sequence[int],
    minimum: int,
) -> list[dict[str, Any]]:
    rows = []
    for index, allele in enumerate(alleles):
        allele_id = _text(allele.get("allele_id"), "allele_id")
        if not allele_id[0].isalpha() or not allele_id.replace("-", "").isalnum():
            raise AlleleConfirmationError("allele_id must be an opaque identifier")
        per_k = []
        statuses = []
        for offset, k in enumerate(k_sizes):
            reference_count, alternate_count = pair_counts[
                index * len(k_sizes) + offset
            ]
            status = classify_counts(
                reference_count=reference_count,
                alternate_count=alternate_count,
                incomplete=incomplete,
                minimum=minimum,
            )
            statuses.append(status)
            per_k.append(
                {
                    "k": k,
                    "reference_count": reference_count,
                    "alternate_count": alternate_count,
                    "status": status,
                }
            )
        rows.append(
            {
                "allele_id": allele_id,
                "by_k": per_k,
                "status": (
                    "incomplete_inputs"
                    if "incomplete_inputs" in statuses
                    else statuses[0]
                    if len(set(statuses)) == 1
                    else "insufficient_observations"
                ),
            }
        )
    return rows


def confirm_alleles(
    alleles: Sequence[Mapping[str, Any]],
    sequences: Iterable[str],
    *,
    incomplete: bool = False,
    k_sizes: Sequence[int] = K_SIZES,
    minimum: int = MINIMUM_OBSERVATIONS,
) -> dict[str, Any]:
    """Return a truth-free confirmation table for caller-supplied alleles."""

    if not alleles:
        raise AlleleConfirmationError("at least one allele is required")
    minimum = _require_minimum(minimum)
    materialized = list(sequences)
    pairs = _allele_pairs(alleles, k_sizes)
    pair_counts = _exclusive_allele_counts(materialized, pairs)
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "minimum_observations": minimum,
        "n_reads": len(materialized),
        "incomplete_inputs": incomplete,
        "reverse_complement_counted": True,
        "alleles": _allele_rows(
            alleles,
            pair_counts,
            incomplete=incomplete,
            k_sizes=k_sizes,
            minimum=minimum,
        ),
    }


def confirm_from_fastq_paths(
    alleles: Sequence[Mapping[str, Any]],
    paths: Sequence[Path],
    *,
    expected_n_files: int = DEFAULT_EXPECTED_N_FILES,
    expected_name_digest: str | None = None,
    k_sizes: Sequence[int] = K_SIZES,
    minimum: int = MINIMUM_OBSERVATIONS,
    synthetic_only: bool = True,
) -> dict[str, Any]:
    """Stream FASTQ paths and fail closed on an incomplete lane set."""

    if not alleles:
        raise AlleleConfirmationError("at least one allele is required")
    # A non-synthetic claim must be bound to a declared filename digest —
    # synthetic_only=False with no pinned names is an unattributed real-data
    # claim and cannot stand.
    if not synthetic_only and expected_name_digest is None:
        raise AlleleConfirmationError(
            "non-synthetic FASTQ confirmation requires a pinned name digest"
        )
    minimum = _require_minimum(minimum)
    layout = assess_fastq_layout(
        paths,
        expected_n_files=expected_n_files,
        expected_name_digest=expected_name_digest,
    )
    pairs = _allele_pairs(alleles, k_sizes)
    pair_counts = [[0, 0] for _ in pairs]
    n_reads = 0
    truncated = False
    for path in paths:
        stream = FastqSequenceStream(path)
        for sequence in stream:
            upper = sequence.upper()
            rc = reverse_complement(upper)
            for index, (ref_kmer, alt_kmer) in enumerate(pairs):
                has_ref = ref_kmer in upper or ref_kmer in rc
                has_alt = alt_kmer in upper or alt_kmer in rc
                if has_ref != has_alt:
                    pair_counts[index][0 if has_ref else 1] += 1
        n_reads += stream.n_reads
        truncated = truncated or stream.incomplete
    incomplete = layout["incomplete"] or truncated
    if truncated and "truncated_records" not in layout["reasons"]:
        layout = dict(layout)
        layout["reasons"] = list(layout["reasons"]) + ["truncated_records"]
        layout["incomplete"] = True
    return {
        "schema": SCHEMA,
        "synthetic_only": synthetic_only,
        "claim_boundary": CLAIM_BOUNDARY,
        "minimum_observations": minimum,
        "n_reads": n_reads,
        "n_files": layout["n_files"],
        "expected_n_files": expected_n_files,
        # The program gate enforces the pinned digest; this flag makes an
        # unpinned standalone call visible rather than silently loose.
        "name_digest_pinned": expected_name_digest is not None,
        "incomplete_inputs": incomplete,
        "reverse_complement_counted": True,
        "layout": layout,
        "alleles": _allele_rows(
            alleles,
            pair_counts,
            incomplete=incomplete,
            k_sizes=k_sizes,
            minimum=minimum,
        ),
    }


def gzip_fastq(records: Sequence[tuple[str, str]]) -> bytes:
    """Build an in-memory gzip FASTQ. Not a file format for the public tree."""

    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as handle:
        for name, sequence in records:
            quality = "I" * len(sequence)
            handle.write(f"@{name}\n{sequence}\n+\n{quality}\n".encode("ascii"))
    return buffer.getvalue()


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_EXPECTED_N_FILES",
    "FastqSequenceStream",
    "K_SIZES",
    "MINIMUM_OBSERVATIONS",
    "PINNED_DATASET_REVISION",
    "PINNED_FASTQ_NAME_DIGEST",
    "SCHEMA",
    "STATUSES",
    "AlleleConfirmationError",
    "assess_fastq_layout",
    "centered_kmers",
    "classify_counts",
    "confirm_alleles",
    "confirm_from_fastq_paths",
    "count_kmers",
    "fastq_name_digest",
    "gzip_fastq",
    "iter_fastq_sequences",
    "reverse_complement",
]
