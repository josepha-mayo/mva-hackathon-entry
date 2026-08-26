"""Phenotype-blind inheritance candidate generation for Track 1.

The module deliberately accepts only sanitized, sample-free allele records.  It
does not read files, consult gene/phenotype databases, or carry any proband
identifier.  Candidate generation is therefore a deterministic transformation
that can be exercised entirely with public or synthetic fixtures.

GRCh38 pseudoautosomal intervals are inclusive.  An allele whose reference
span crosses a PAR boundary is rejected instead of being assigned an
overconfident inheritance model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Iterable, TypeAlias, TypeVar


VariantKey: TypeAlias = tuple[str, int, str, str]


class InheritanceInputError(ValueError):
    """Raised when an allele record is not safe to model deterministically."""


class Zygosity(str, Enum):
    HETEROZYGOUS = "heterozygous"
    HOMOZYGOUS = "homozygous"
    HEMIZYGOUS = "hemizygous"
    HETEROPLASMIC = "heteroplasmic"
    HOMOPLASMIC = "homoplasmic"


class PhaseState(str, Enum):
    TRANS_CONFIRMED = "trans_confirmed"
    CIS_CONFIRMED = "cis_confirmed"
    UNRESOLVED = "unresolved"


class InheritanceModel(str, Enum):
    COMPOUND_HETEROZYGOUS = "compound_heterozygous"
    HOMOZYGOUS_RECESSIVE = "homozygous_recessive"
    DOMINANT = "dominant"
    X_LINKED = "x_linked"
    MITOCHONDRIAL = "mitochondrial"


class LocusClass(str, Enum):
    AUTOSOMAL = "autosomal"
    PSEUDOAUTOSOMAL = "pseudoautosomal"
    X_NONPAR = "x_nonpar"
    Y_NONPAR = "y_nonpar"
    MITOCHONDRIAL = "mitochondrial"


class ReasonCode(str, Enum):
    AUTOSOMAL_LOCUS = "autosomal_locus"
    PSEUDOAUTOSOMAL_LOCUS = "pseudoautosomal_locus"
    X_NONPAR_LOCUS = "x_nonpar_locus"
    MITOCHONDRIAL_LOCUS = "mitochondrial_locus"
    SAME_GENE = "same_gene"
    TWO_HETEROZYGOUS_ALLELES = "two_heterozygous_alleles"
    HETEROZYGOUS_ALLELE = "heterozygous_allele"
    HOMOZYGOUS_ALLELE = "homozygous_allele"
    HEMIZYGOUS_ALLELE = "hemizygous_allele"
    HETEROPLASMIC_ALLELE = "heteroplasmic_allele"
    HOMOPLASMIC_ALLELE = "homoplasmic_allele"
    PHASE_TRANS_CONFIRMED = "phase_trans_confirmed"
    PHASE_UNRESOLVED = "phase_unresolved"


# (chromosome, interval name, first base, last base), all 1-based and inclusive.
GRCH38_PAR_INTERVALS: tuple[tuple[str, str, int, int], ...] = (
    ("chrX", "PAR1", 10_001, 2_781_479),
    ("chrX", "PAR2", 155_701_383, 156_030_895),
    ("chrY", "PAR1", 10_001, 2_781_479),
    ("chrY", "PAR2", 56_887_903, 57_217_415),
)

_GRCH38_LENGTHS = {
    "chr1": 248_956_422,
    "chr2": 242_193_529,
    "chr3": 198_295_559,
    "chr4": 190_214_555,
    "chr5": 181_538_259,
    "chr6": 170_805_979,
    "chr7": 159_345_973,
    "chr8": 145_138_636,
    "chr9": 138_394_717,
    "chr10": 133_797_422,
    "chr11": 135_086_622,
    "chr12": 133_275_309,
    "chr13": 114_364_328,
    "chr14": 107_043_718,
    "chr15": 101_991_189,
    "chr16": 90_338_345,
    "chr17": 83_257_441,
    "chr18": 80_373_285,
    "chr19": 58_617_616,
    "chr20": 64_444_167,
    "chr21": 46_709_983,
    "chr22": 50_818_468,
    "chrX": 156_040_895,
    "chrY": 57_227_415,
    "chrM": 16_569,
}
_GENE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
_REF = re.compile(r"^[ACGTN]+$")
_ALT = re.compile(r"^(?:[ACGTN]+|\*|<[A-Z0-9:_-]+>)$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MODEL_ORDER = {
    InheritanceModel.COMPOUND_HETEROZYGOUS: 0,
    InheritanceModel.HOMOZYGOUS_RECESSIVE: 1,
    InheritanceModel.DOMINANT: 2,
    InheritanceModel.X_LINKED: 3,
    InheritanceModel.MITOCHONDRIAL: 4,
}
_CHROM_ORDER = {
    **{f"chr{number}": number for number in range(1, 23)},
    "chrX": 23,
    "chrY": 24,
    "chrM": 25,
}

_EnumT = TypeVar("_EnumT", bound=Enum)


def _coerce_enum(value: _EnumT | str, enum_type: type[_EnumT], field: str) -> _EnumT:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise InheritanceInputError(f"{field} must be a {enum_type.__name__} value")
    try:
        return enum_type(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise InheritanceInputError(f"{field} must be one of: {allowed}") from exc


def _normalize_chromosome(value: str) -> str:
    if not isinstance(value, str):
        raise InheritanceInputError("chrom must be a string")
    token = value.strip()
    if token.lower().startswith("chr"):
        token = token[3:]
    if token.upper() in {"M", "MT"}:
        chrom = "chrM"
    elif token.upper() in {"X", "Y"}:
        chrom = f"chr{token.upper()}"
    elif token.isdigit() and 1 <= int(token) <= 22:
        chrom = f"chr{int(token)}"
    else:
        raise InheritanceInputError("chrom must identify GRCh38 chr1..chr22, chrX, chrY, or chrM")
    return chrom


def _normalize_optional_token(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InheritanceInputError(f"{field} must be a string or None")
    token = value.strip()
    if not token:
        raise InheritanceInputError(f"{field} cannot be blank; use None when unknown")
    if len(token) > 128 or _CONTROL.search(token):
        raise InheritanceInputError(f"{field} must be a short printable token")
    return token


@dataclass(frozen=True)
class AlleleRecord:
    """A sanitized allele with only fields needed for inheritance modeling.

    ``phase_set`` identifies a block in which haplotype labels are comparable.
    Two alleles are confirmed trans/cis only when both fields are present, their
    phase sets match, and their haplotype labels differ/match respectively.
    Any weaker evidence is intentionally unresolved.
    """

    gene: str
    chrom: str
    pos: int
    ref: str
    alt: str
    zygosity: Zygosity
    phase_set: str | None = None
    haplotype: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.gene, str):
            raise InheritanceInputError("gene must be a string")
        gene = self.gene.strip().upper()
        if not _GENE.fullmatch(gene):
            raise InheritanceInputError("gene must be a non-empty sanitized gene symbol")
        chrom = _normalize_chromosome(self.chrom)
        if isinstance(self.pos, bool) or not isinstance(self.pos, int):
            raise InheritanceInputError("pos must be an integer")
        if self.pos < 1:
            raise InheritanceInputError("pos must be positive")
        if not isinstance(self.ref, str) or not isinstance(self.alt, str):
            raise InheritanceInputError("ref and alt must be strings")
        ref = self.ref.strip().upper()
        alt = self.alt.strip().upper()
        if not _REF.fullmatch(ref):
            raise InheritanceInputError("ref must be a non-empty A/C/G/T/N sequence")
        if not _ALT.fullmatch(alt):
            raise InheritanceInputError("alt must be a sequence, *, or symbolic VCF allele")
        if ref == alt:
            raise InheritanceInputError("ref and alt cannot be identical")
        if self.pos + len(ref) - 1 > _GRCH38_LENGTHS[chrom]:
            raise InheritanceInputError(f"reference allele exceeds the GRCh38 {chrom} length")

        zygosity = _coerce_enum(self.zygosity, Zygosity, "zygosity")
        phase_set = _normalize_optional_token(self.phase_set, "phase_set")
        haplotype = _normalize_optional_token(self.haplotype, "haplotype")
        if haplotype is not None and phase_set is None:
            raise InheritanceInputError("haplotype requires a phase_set")

        object.__setattr__(self, "gene", gene)
        object.__setattr__(self, "chrom", chrom)
        object.__setattr__(self, "ref", ref)
        object.__setattr__(self, "alt", alt)
        object.__setattr__(self, "zygosity", zygosity)
        object.__setattr__(self, "phase_set", phase_set)
        object.__setattr__(self, "haplotype", haplotype)

    @property
    def variant_key(self) -> VariantKey:
        return (self.chrom, self.pos, self.ref, self.alt)


@dataclass(frozen=True)
class InheritanceCandidate:
    gene: str
    model: InheritanceModel
    alleles: tuple[AlleleRecord, ...]
    locus_class: LocusClass
    phase_state: PhaseState | None
    reason_codes: tuple[ReasonCode, ...]

    def __post_init__(self) -> None:
        model = _coerce_enum(self.model, InheritanceModel, "model")
        locus_class = _coerce_enum(self.locus_class, LocusClass, "locus_class")
        phase_state = (
            None
            if self.phase_state is None
            else _coerce_enum(self.phase_state, PhaseState, "phase_state")
        )
        if not isinstance(self.alleles, tuple) or not self.alleles:
            raise InheritanceInputError("candidate alleles must be a non-empty tuple")
        if any(not isinstance(allele, AlleleRecord) for allele in self.alleles):
            raise InheritanceInputError("candidate alleles must contain AlleleRecord values")
        alleles = tuple(sorted(self.alleles, key=_allele_sort_key))
        if len({allele.variant_key for allele in alleles}) != len(alleles):
            raise InheritanceInputError("candidate cannot repeat an allele")
        gene = self.gene.strip().upper() if isinstance(self.gene, str) else ""
        if not _GENE.fullmatch(gene) or any(allele.gene != gene for allele in alleles):
            raise InheritanceInputError("candidate gene must match every allele")

        if model is InheritanceModel.COMPOUND_HETEROZYGOUS:
            if len(alleles) != 2:
                raise InheritanceInputError("compound-heterozygous candidates require two alleles")
            if phase_state not in {PhaseState.TRANS_CONFIRMED, PhaseState.UNRESOLVED}:
                raise InheritanceInputError("compound candidate phase must be trans_confirmed or unresolved")
        else:
            if len(alleles) != 1:
                raise InheritanceInputError("non-compound candidates require one allele")
            if phase_state is not None:
                raise InheritanceInputError("single-allele candidates do not have a pair phase state")

        if not isinstance(self.reason_codes, tuple) or not self.reason_codes:
            raise InheritanceInputError("candidate reason_codes must be a non-empty tuple")
        reasons = tuple(
            _coerce_enum(reason, ReasonCode, "reason_code") for reason in self.reason_codes
        )
        if len(set(reasons)) != len(reasons):
            raise InheritanceInputError("candidate reason_codes cannot contain duplicates")

        object.__setattr__(self, "gene", gene)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "alleles", alleles)
        object.__setattr__(self, "locus_class", locus_class)
        object.__setattr__(self, "phase_state", phase_state)
        object.__setattr__(self, "reason_codes", reasons)

    @property
    def variant_keys(self) -> tuple[VariantKey, ...]:
        return tuple(allele.variant_key for allele in self.alleles)


def _allele_sort_key(allele: AlleleRecord) -> tuple[int, int, str, str, str]:
    return (_CHROM_ORDER[allele.chrom], allele.pos, allele.ref, allele.alt, allele.gene)


def _par_interval_name(allele: AlleleRecord) -> str | None:
    if allele.chrom not in {"chrX", "chrY"}:
        return None
    first = allele.pos
    last = allele.pos + len(allele.ref) - 1
    for chrom, name, interval_first, interval_last in GRCH38_PAR_INTERVALS:
        if chrom != allele.chrom:
            continue
        if interval_first <= first and last <= interval_last:
            return name
        if first <= interval_last and last >= interval_first:
            raise InheritanceInputError(
                f"{allele.variant_key!r} spans the GRCh38 {name} boundary"
            )
    return None


def classify_locus(allele: AlleleRecord) -> LocusClass:
    """Classify an allele without consulting sample sex or external state."""

    if not isinstance(allele, AlleleRecord):
        raise TypeError("allele must be an AlleleRecord")
    if allele.chrom == "chrM":
        return LocusClass.MITOCHONDRIAL
    if allele.chrom == "chrX":
        return LocusClass.PSEUDOAUTOSOMAL if _par_interval_name(allele) else LocusClass.X_NONPAR
    if allele.chrom == "chrY":
        return LocusClass.PSEUDOAUTOSOMAL if _par_interval_name(allele) else LocusClass.Y_NONPAR
    return LocusClass.AUTOSOMAL


def pair_phase_state(first: AlleleRecord, second: AlleleRecord) -> PhaseState:
    """Return only the phase supported directly by the two sanitized records."""

    if not isinstance(first, AlleleRecord) or not isinstance(second, AlleleRecord):
        raise TypeError("phase inputs must be AlleleRecord values")
    if (
        first.phase_set is None
        or second.phase_set is None
        or first.phase_set != second.phase_set
        or first.haplotype is None
        or second.haplotype is None
    ):
        return PhaseState.UNRESOLVED
    if first.haplotype == second.haplotype:
        return PhaseState.CIS_CONFIRMED
    return PhaseState.TRANS_CONFIRMED


def _merge_duplicate(first: AlleleRecord, second: AlleleRecord) -> AlleleRecord:
    if first.zygosity is not second.zygosity:
        raise InheritanceInputError(
            f"conflicting zygosity for duplicate {first.gene} {first.variant_key!r}"
        )
    if first.phase_set and second.phase_set and first.phase_set != second.phase_set:
        raise InheritanceInputError(
            f"conflicting phase_set for duplicate {first.gene} {first.variant_key!r}"
        )
    phase_set = first.phase_set or second.phase_set
    if first.haplotype and second.haplotype and first.haplotype != second.haplotype:
        raise InheritanceInputError(
            f"conflicting haplotype for duplicate {first.gene} {first.variant_key!r}"
        )
    haplotype = first.haplotype or second.haplotype
    return AlleleRecord(
        gene=first.gene,
        chrom=first.chrom,
        pos=first.pos,
        ref=first.ref,
        alt=first.alt,
        zygosity=first.zygosity,
        phase_set=phase_set,
        haplotype=haplotype,
    )


def _deduplicate(records: Iterable[AlleleRecord]) -> tuple[AlleleRecord, ...]:
    unique: dict[tuple[str, VariantKey], AlleleRecord] = {}
    for index, record in enumerate(records):
        if not isinstance(record, AlleleRecord):
            raise TypeError(f"record {index} must be an AlleleRecord")
        key = (record.gene, record.variant_key)
        prior = unique.get(key)
        unique[key] = record if prior is None else _merge_duplicate(prior, record)
    return tuple(sorted(unique.values(), key=lambda allele: (allele.gene, _allele_sort_key(allele))))


def _locus_partition(allele: AlleleRecord) -> tuple[LocusClass, str, str]:
    locus_class = classify_locus(allele)
    par_name = _par_interval_name(allele) if locus_class is LocusClass.PSEUDOAUTOSOMAL else ""
    return (locus_class, allele.chrom, par_name or "")


def _locus_reason(locus_class: LocusClass) -> ReasonCode:
    return {
        LocusClass.AUTOSOMAL: ReasonCode.AUTOSOMAL_LOCUS,
        LocusClass.PSEUDOAUTOSOMAL: ReasonCode.PSEUDOAUTOSOMAL_LOCUS,
        LocusClass.X_NONPAR: ReasonCode.X_NONPAR_LOCUS,
        LocusClass.MITOCHONDRIAL: ReasonCode.MITOCHONDRIAL_LOCUS,
    }[locus_class]


def _zygosity_reason(zygosity: Zygosity) -> ReasonCode:
    return {
        Zygosity.HETEROZYGOUS: ReasonCode.HETEROZYGOUS_ALLELE,
        Zygosity.HOMOZYGOUS: ReasonCode.HOMOZYGOUS_ALLELE,
        Zygosity.HEMIZYGOUS: ReasonCode.HEMIZYGOUS_ALLELE,
        Zygosity.HETEROPLASMIC: ReasonCode.HETEROPLASMIC_ALLELE,
        Zygosity.HOMOPLASMIC: ReasonCode.HOMOPLASMIC_ALLELE,
    }[zygosity]


def _single_candidate(allele: AlleleRecord) -> InheritanceCandidate | None:
    locus_class = classify_locus(allele)
    if locus_class in {LocusClass.AUTOSOMAL, LocusClass.PSEUDOAUTOSOMAL}:
        if allele.zygosity is Zygosity.HETEROZYGOUS:
            model = InheritanceModel.DOMINANT
        elif allele.zygosity is Zygosity.HOMOZYGOUS:
            model = InheritanceModel.HOMOZYGOUS_RECESSIVE
        else:
            return None
    elif locus_class is LocusClass.X_NONPAR:
        if allele.zygosity not in {
            Zygosity.HETEROZYGOUS,
            Zygosity.HOMOZYGOUS,
            Zygosity.HEMIZYGOUS,
        }:
            return None
        model = InheritanceModel.X_LINKED
    elif locus_class is LocusClass.MITOCHONDRIAL:
        model = InheritanceModel.MITOCHONDRIAL
    else:
        # Non-PAR Y candidates need a separate Y-linked model, outside this
        # engine's explicit Track 1 inheritance contract.
        return None
    return InheritanceCandidate(
        gene=allele.gene,
        model=model,
        alleles=(allele,),
        locus_class=locus_class,
        phase_state=None,
        reason_codes=(_locus_reason(locus_class), _zygosity_reason(allele.zygosity)),
    )


def _compound_candidates(records: tuple[AlleleRecord, ...]) -> list[InheritanceCandidate]:
    groups: dict[tuple[str, tuple[LocusClass, str, str]], list[AlleleRecord]] = {}
    for allele in records:
        if allele.zygosity is not Zygosity.HETEROZYGOUS:
            continue
        partition = _locus_partition(allele)
        if partition[0] not in {
            LocusClass.AUTOSOMAL,
            LocusClass.PSEUDOAUTOSOMAL,
            LocusClass.X_NONPAR,
        }:
            continue
        groups.setdefault((allele.gene, partition), []).append(allele)

    candidates: list[InheritanceCandidate] = []
    for (gene, partition), alleles in groups.items():
        for first, second in combinations(sorted(alleles, key=_allele_sort_key), 2):
            phase_state = pair_phase_state(first, second)
            if phase_state is PhaseState.CIS_CONFIRMED:
                continue
            phase_reason = (
                ReasonCode.PHASE_TRANS_CONFIRMED
                if phase_state is PhaseState.TRANS_CONFIRMED
                else ReasonCode.PHASE_UNRESOLVED
            )
            candidates.append(
                InheritanceCandidate(
                    gene=gene,
                    model=InheritanceModel.COMPOUND_HETEROZYGOUS,
                    alleles=(first, second),
                    locus_class=partition[0],
                    phase_state=phase_state,
                    reason_codes=(
                        _locus_reason(partition[0]),
                        ReasonCode.SAME_GENE,
                        ReasonCode.TWO_HETEROZYGOUS_ALLELES,
                        phase_reason,
                    ),
                )
            )
    return candidates


def _candidate_sort_key(candidate: InheritanceCandidate) -> tuple[object, ...]:
    return (
        candidate.gene,
        _MODEL_ORDER[candidate.model],
        tuple(_allele_sort_key(allele) for allele in candidate.alleles),
        candidate.phase_state.value if candidate.phase_state else "",
    )


def generate_inheritance_candidates(
    records: Iterable[AlleleRecord],
) -> tuple[InheritanceCandidate, ...]:
    """Generate a stable phenotype-blind candidate universe.

    Heterozygous autosomal/PAR alleles generate dominant candidates and are
    paired within the same gene and locus partition.  Homozygous autosomal/PAR
    alleles generate recessive candidates.  Non-PAR chrX and chrM records use
    their dedicated models.  Confirmed-cis compound pairs are never emitted;
    unresolved pairs remain eligible with an explicit reason code.
    """

    normalized = _deduplicate(records)
    candidates = _compound_candidates(normalized)
    candidates.extend(
        candidate
        for allele in normalized
        if (candidate := _single_candidate(allele)) is not None
    )
    return tuple(sorted(candidates, key=_candidate_sort_key))


__all__ = [
    "AlleleRecord",
    "GRCH38_PAR_INTERVALS",
    "InheritanceCandidate",
    "InheritanceInputError",
    "InheritanceModel",
    "LocusClass",
    "PhaseState",
    "ReasonCode",
    "VariantKey",
    "Zygosity",
    "classify_locus",
    "generate_inheritance_candidates",
    "pair_phase_state",
]
