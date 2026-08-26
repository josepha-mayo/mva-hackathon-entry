"""Pure mechanism assessment for validated inheritance-pair candidates.

This module deliberately has no file readers, resource clients, phenotype
inputs, or calibrated ranking formula. It composes the sanitized inheritance
objects in :mod:`mva_hackathon.inheritance` and keeps transcript compatibility,
disease mechanism, phase, exact variant/gene evidence, and disease-condition
relevance as separate facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
from typing import Iterable

from .inheritance import (
    InheritanceCandidate,
    InheritanceModel,
    PhaseState,
    VariantKey,
)


LOF_CONSEQUENCES = frozenset(
    {
        "frameshift",
        "splice_acceptor",
        "splice_donor",
        "start_lost",
        "stop_gained",
    }
)
PROTEIN_ALTERING_CONSEQUENCES = LOF_CONSEQUENCES | {
    "inframe_deletion",
    "inframe_insertion",
    "missense",
    "stop_lost",
}

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_GENOTYPE = re.compile(r"^(\d+)([/|])(\d+)$")


class MechanismInputError(ValueError):
    """Raised when an assessment input cannot be interpreted safely."""


class RuleMechanism(str, Enum):
    LOSS_OF_FUNCTION = "loss_of_function"
    OTHER_OR_UNRESOLVED = "other_or_unresolved"


class EvidenceConfidence(str, Enum):
    DEFINITIVE = "definitive"
    STRONG = "strong"
    MODERATE = "moderate"
    LIMITED = "limited"
    UNSPECIFIED = "unspecified"


class ConditionRelevance(str, Enum):
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    NOT_ASSESSED = "not_assessed"
    CONFLICTING = "conflicting"


class MechanismFit(str, Enum):
    LOCUS_MISMATCH = "locus_mismatch"
    GENE_RULE_MISMATCH = "gene_rule_mismatch"
    NO_SHARED_TRANSCRIPT = "no_shared_transcript"
    DISEASE_RULE_REQUIRES_MANUAL_REVIEW = "disease_rule_requires_manual_review"
    STRICT_TWO_ALLELE_LOF_MATCH = "strict_two_allele_lof_match"
    ONE_LOF_PLUS_PROTEIN_ALTERING_HYPOMORPH_HYPOTHESIS = (
        "one_lof_plus_protein_altering_hypomorph_hypothesis"
    )
    TWO_PROTEIN_ALTERING_NONLOF_HYPOTHESIS = (
        "two_protein_altering_nonlof_hypothesis"
    )


def _validated_token(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise MechanismInputError(f"{field} must be a string")
    token = value.strip()
    if len(token) > 128 or not _TOKEN.fullmatch(token):
        raise MechanismInputError(f"{field} must be a short sanitized token")
    return token


def _validated_gene(value: str) -> str:
    return _validated_token(value, "gene").upper()


def _validated_variant_key(value: VariantKey) -> VariantKey:
    if not isinstance(value, tuple) or len(value) != 4:
        raise MechanismInputError("variant_key must be a four-part tuple")
    chrom, pos, ref, alt = value
    if not all(isinstance(item, str) and item for item in (chrom, ref, alt)):
        raise MechanismInputError("variant_key string fields cannot be blank")
    if isinstance(pos, bool) or not isinstance(pos, int) or pos < 1:
        raise MechanismInputError("variant_key position must be positive")
    return value


def parse_evidence_confidence(value: EvidenceConfidence | str) -> EvidenceConfidence:
    """Coerce only the declared confidence vocabulary; never assign a fallback."""

    if isinstance(value, EvidenceConfidence):
        return value
    if not isinstance(value, str):
        raise MechanismInputError("confidence must be an EvidenceConfidence value")
    try:
        return EvidenceConfidence(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in EvidenceConfidence)
        raise MechanismInputError(f"confidence must be one of: {allowed}") from exc


@dataclass(frozen=True)
class GenotypeDepthEvidence:
    """Explicit contract for a genotype and its allele-indexed depth vector.

    Standard biallelic ``0/1`` or ``1/0`` calls may omit ``ad_allele_indices``;
    the two depths then mean reference and alternate respectively. Any call
    involving allele index 2 or greater must declare both the target alternate
    and the allele index represented by every depth.
    """

    genotype: str
    allele_depths: tuple[int, ...]
    target_alt_index: int | None = None
    ad_allele_indices: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.genotype, str):
            raise MechanismInputError("genotype must be a string")
        match = _GENOTYPE.fullmatch(self.genotype.strip())
        if match is None:
            raise MechanismInputError("genotype must be a called diploid GT")
        genotype = self.genotype.strip()
        called_indices = (int(match.group(1)), int(match.group(3)))
        if called_indices[0] == called_indices[1]:
            raise MechanismInputError("genotype must contain two different alleles")

        if not isinstance(self.allele_depths, tuple) or not self.allele_depths:
            raise MechanismInputError("allele_depths must be a non-empty tuple")
        if any(
            isinstance(depth, bool) or not isinstance(depth, int) or depth < 0
            for depth in self.allele_depths
        ):
            raise MechanismInputError("allele_depths must contain non-negative integers")
        if sum(self.allele_depths) == 0:
            raise MechanismInputError("allele_depths must contain observed depth")

        multiallelic = max(called_indices) > 1
        target = self.target_alt_index
        indices = self.ad_allele_indices
        if multiallelic and (target is None or indices is None):
            raise MechanismInputError(
                "multiallelic GT requires target_alt_index and explicit AD allele indices"
            )
        if target is None:
            target = 1
        if isinstance(target, bool) or not isinstance(target, int) or target < 1:
            raise MechanismInputError("target_alt_index must be a positive integer")
        if target not in called_indices:
            raise MechanismInputError("target_alt_index must occur in the genotype")

        if indices is None:
            if len(self.allele_depths) != 2:
                raise MechanismInputError(
                    "implicit biallelic AD semantics require exactly two depths"
                )
            indices = (0, 1)
        if not isinstance(indices, tuple) or len(indices) != len(self.allele_depths):
            raise MechanismInputError("AD allele indices must align with allele_depths")
        if any(
            isinstance(index, bool) or not isinstance(index, int) or index < 0
            for index in indices
        ):
            raise MechanismInputError("AD allele indices must be non-negative integers")
        if len(set(indices)) != len(indices):
            raise MechanismInputError("AD allele indices cannot repeat")
        if not set(called_indices) <= set(indices):
            raise MechanismInputError("AD allele indices must cover every called allele")
        if target not in indices:
            raise MechanismInputError("AD allele indices must contain target_alt_index")

        object.__setattr__(self, "genotype", genotype)
        object.__setattr__(self, "target_alt_index", target)
        object.__setattr__(self, "ad_allele_indices", indices)

    @property
    def target_depth(self) -> int:
        assert self.ad_allele_indices is not None
        assert self.target_alt_index is not None
        index = self.ad_allele_indices.index(self.target_alt_index)
        return self.allele_depths[index]

    @property
    def target_fraction_of_all_depth(self) -> float:
        """Return an explicitly named all-depth fraction, not an ambiguous AB."""

        return self.target_depth / sum(self.allele_depths)


@dataclass(frozen=True)
class TranscriptEffect:
    transcript: str
    consequences: frozenset[str]

    def __post_init__(self) -> None:
        transcript = _validated_token(self.transcript, "transcript")
        if not isinstance(self.consequences, frozenset) or not self.consequences:
            raise MechanismInputError("consequences must be a non-empty frozenset")
        consequences = frozenset(
            item.strip().lower() if isinstance(item, str) else ""
            for item in self.consequences
        )
        unknown = consequences - PROTEIN_ALTERING_CONSEQUENCES
        if "" in consequences or unknown:
            invalid = {"<invalid>"} if "" in consequences else set()
            unknown_text = ", ".join(sorted(unknown | invalid))
            raise MechanismInputError(f"unsupported protein consequence: {unknown_text}")
        object.__setattr__(self, "transcript", transcript)
        object.__setattr__(self, "consequences", consequences)

    @property
    def has_lof(self) -> bool:
        return bool(self.consequences & LOF_CONSEQUENCES)


@dataclass(frozen=True)
class AlleleTranscriptEffects:
    variant_key: VariantKey
    effects: tuple[TranscriptEffect, ...]

    def __post_init__(self) -> None:
        variant_key = _validated_variant_key(self.variant_key)
        if not isinstance(self.effects, tuple) or not self.effects:
            raise MechanismInputError("effects must be a non-empty tuple")
        if any(not isinstance(effect, TranscriptEffect) for effect in self.effects):
            raise MechanismInputError("effects must contain TranscriptEffect values")
        ordered = tuple(sorted(self.effects, key=lambda item: item.transcript))
        transcripts = [effect.transcript for effect in ordered]
        if len(set(transcripts)) != len(transcripts):
            raise MechanismInputError("an allele cannot repeat a transcript")
        object.__setattr__(self, "variant_key", variant_key)
        object.__setattr__(self, "effects", ordered)

    @property
    def by_transcript(self) -> dict[str, TranscriptEffect]:
        return {effect.transcript: effect for effect in self.effects}


@dataclass(frozen=True)
class DiseaseMechanismRule:
    rule_id: str
    gene: str
    mechanism: RuleMechanism
    confidence: EvidenceConfidence = EvidenceConfidence.UNSPECIFIED

    def __post_init__(self) -> None:
        rule_id = _validated_token(self.rule_id, "rule_id")
        gene = _validated_gene(self.gene)
        try:
            mechanism = (
                self.mechanism
                if isinstance(self.mechanism, RuleMechanism)
                else RuleMechanism(self.mechanism)
            )
        except (TypeError, ValueError) as exc:
            raise MechanismInputError("mechanism is not recognized") from exc
        confidence = parse_evidence_confidence(self.confidence)
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "gene", gene)
        object.__setattr__(self, "mechanism", mechanism)
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class VariantGeneEvidence:
    """Exact variant/gene evidence with no implied disease-condition match."""

    evidence_id: str
    variant_key: VariantKey
    gene: str
    strict_pathogenic: bool
    review_stars: int
    conflicting: bool = False

    def __post_init__(self) -> None:
        evidence_id = _validated_token(self.evidence_id, "evidence_id")
        variant_key = _validated_variant_key(self.variant_key)
        gene = _validated_gene(self.gene)
        if not isinstance(self.strict_pathogenic, bool) or not isinstance(
            self.conflicting, bool
        ):
            raise MechanismInputError("pathogenic and conflict flags must be booleans")
        if isinstance(self.review_stars, bool) or not isinstance(self.review_stars, int):
            raise MechanismInputError("review_stars must be an integer")
        if not 0 <= self.review_stars <= 4:
            raise MechanismInputError("review_stars must be between zero and four")
        if self.strict_pathogenic and self.conflicting:
            raise MechanismInputError("strict pathogenic evidence cannot be conflicting")
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "variant_key", variant_key)
        object.__setattr__(self, "gene", gene)


@dataclass(frozen=True)
class DiseaseConditionEvidence:
    """A separate assessment of whether evidence concerns the declared rule."""

    evidence_id: str
    rule_id: str
    relevance: ConditionRelevance

    def __post_init__(self) -> None:
        evidence_id = _validated_token(self.evidence_id, "evidence_id")
        rule_id = _validated_token(self.rule_id, "rule_id")
        try:
            relevance = (
                self.relevance
                if isinstance(self.relevance, ConditionRelevance)
                else ConditionRelevance(self.relevance)
            )
        except (TypeError, ValueError) as exc:
            raise MechanismInputError("condition relevance is not recognized") from exc
        if relevance in {ConditionRelevance.NOT_ASSESSED, ConditionRelevance.CONFLICTING}:
            raise MechanismInputError(
                "condition evidence rows must be matched or mismatched observations"
            )
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "relevance", relevance)


@dataclass(frozen=True)
class MechanismAssessment:
    gene: str
    rule_id: str
    variant_keys: tuple[VariantKey, VariantKey]
    phase_state: PhaseState
    shared_transcripts: tuple[str, ...]
    supporting_transcripts: tuple[str, ...]
    fit: MechanismFit
    strict_pathogenic_anchor_count: int
    condition_relevance: ConditionRelevance
    eligible_for_strict_pair_lane: bool


_FIT_PRIORITY = {
    MechanismFit.STRICT_TWO_ALLELE_LOF_MATCH: 3,
    MechanismFit.ONE_LOF_PLUS_PROTEIN_ALTERING_HYPOMORPH_HYPOTHESIS: 2,
    MechanismFit.TWO_PROTEIN_ALTERING_NONLOF_HYPOTHESIS: 1,
}


def _gene_matched_anchor_count(
    candidate: InheritanceCandidate,
    evidence: Iterable[VariantGeneEvidence],
) -> int:
    candidate_keys = set(candidate.variant_keys)
    anchored_keys: set[VariantKey] = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, VariantGeneEvidence):
            raise MechanismInputError(f"evidence {index} must be VariantGeneEvidence")
        if (
            item.gene == candidate.gene
            and item.variant_key in candidate_keys
            and item.strict_pathogenic
            and not item.conflicting
        ):
            anchored_keys.add(item.variant_key)
    return len(anchored_keys)


def _condition_relevance(
    rule: DiseaseMechanismRule,
    rows: Iterable[DiseaseConditionEvidence],
) -> ConditionRelevance:
    observations: set[ConditionRelevance] = set()
    identifiers: set[str] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, DiseaseConditionEvidence):
            raise MechanismInputError(
                f"condition evidence {index} must be DiseaseConditionEvidence"
            )
        if item.evidence_id in identifiers:
            raise MechanismInputError("condition evidence identifiers must be unique")
        identifiers.add(item.evidence_id)
        if item.rule_id == rule.rule_id:
            observations.add(item.relevance)
    if not observations:
        return ConditionRelevance.NOT_ASSESSED
    if len(observations) > 1:
        return ConditionRelevance.CONFLICTING
    return next(iter(observations))


def _base_assessment(
    candidate: InheritanceCandidate,
    rule: DiseaseMechanismRule,
    fit: MechanismFit,
    condition_relevance: ConditionRelevance,
    *,
    shared: tuple[str, ...] = (),
    supporting: tuple[str, ...] = (),
    anchor_count: int = 0,
) -> MechanismAssessment:
    phase = candidate.phase_state
    if phase not in {PhaseState.TRANS_CONFIRMED, PhaseState.UNRESOLVED}:
        raise MechanismInputError("compound candidate phase must be trans_confirmed or unresolved")
    keys = candidate.variant_keys
    if len(keys) != 2:
        raise MechanismInputError("mechanism assessment requires exactly two alleles")
    eligible = (
        fit is MechanismFit.STRICT_TWO_ALLELE_LOF_MATCH
        and phase is PhaseState.TRANS_CONFIRMED
    )
    return MechanismAssessment(
        gene=candidate.gene,
        rule_id=rule.rule_id,
        variant_keys=(keys[0], keys[1]),
        phase_state=phase,
        shared_transcripts=shared,
        supporting_transcripts=supporting,
        fit=fit,
        strict_pathogenic_anchor_count=anchor_count,
        condition_relevance=condition_relevance,
        eligible_for_strict_pair_lane=eligible,
    )


def assess_mechanism_pair(
    candidate: InheritanceCandidate,
    effects: Iterable[AlleleTranscriptEffects],
    rule: DiseaseMechanismRule,
    evidence: Iterable[VariantGeneEvidence] = (),
    condition_evidence: Iterable[DiseaseConditionEvidence] = (),
) -> MechanismAssessment:
    """Assess one validated compound candidate without phenotype information.

    LoF state is evaluated only on transcripts present for both alleles. A LoF
    consequence on a different transcript cannot upgrade the pair. Exact
    variant/gene anchors and disease-condition relevance remain independent.
    """

    if not isinstance(candidate, InheritanceCandidate):
        raise MechanismInputError("candidate must be an InheritanceCandidate")
    if candidate.model is not InheritanceModel.COMPOUND_HETEROZYGOUS:
        raise MechanismInputError("candidate must use the compound-heterozygous model")
    if not isinstance(rule, DiseaseMechanismRule):
        raise MechanismInputError("rule must be a DiseaseMechanismRule")

    anchor_count = _gene_matched_anchor_count(candidate, evidence)
    condition = _condition_relevance(rule, condition_evidence)
    if rule.gene != candidate.gene:
        return _base_assessment(
            candidate,
            rule,
            MechanismFit.GENE_RULE_MISMATCH,
            condition,
            anchor_count=anchor_count,
        )

    first, second = candidate.alleles
    if first.chrom != second.chrom:
        return _base_assessment(
            candidate,
            rule,
            MechanismFit.LOCUS_MISMATCH,
            condition,
            anchor_count=anchor_count,
        )

    effect_rows = tuple(effects)
    if any(not isinstance(row, AlleleTranscriptEffects) for row in effect_rows):
        raise MechanismInputError("effects must contain AlleleTranscriptEffects values")
    by_key: dict[VariantKey, AlleleTranscriptEffects] = {}
    for row in effect_rows:
        if row.variant_key in by_key:
            raise MechanismInputError("effects cannot repeat a variant_key")
        by_key[row.variant_key] = row
    expected = set(candidate.variant_keys)
    if set(by_key) != expected:
        raise MechanismInputError("effects must cover exactly the candidate alleles")

    first_effects = by_key[first.variant_key].by_transcript
    second_effects = by_key[second.variant_key].by_transcript
    shared = tuple(sorted(set(first_effects) & set(second_effects)))
    if not shared:
        return _base_assessment(
            candidate,
            rule,
            MechanismFit.NO_SHARED_TRANSCRIPT,
            condition,
            anchor_count=anchor_count,
        )
    if rule.mechanism is not RuleMechanism.LOSS_OF_FUNCTION:
        return _base_assessment(
            candidate,
            rule,
            MechanismFit.DISEASE_RULE_REQUIRES_MANUAL_REVIEW,
            condition,
            shared=shared,
            anchor_count=anchor_count,
        )

    per_transcript: dict[str, MechanismFit] = {}
    for transcript in shared:
        lof_count = int(first_effects[transcript].has_lof) + int(
            second_effects[transcript].has_lof
        )
        if lof_count == 2:
            fit = MechanismFit.STRICT_TWO_ALLELE_LOF_MATCH
        elif lof_count == 1:
            fit = MechanismFit.ONE_LOF_PLUS_PROTEIN_ALTERING_HYPOMORPH_HYPOTHESIS
        else:
            fit = MechanismFit.TWO_PROTEIN_ALTERING_NONLOF_HYPOTHESIS
        per_transcript[transcript] = fit

    best_fit = max(per_transcript.values(), key=_FIT_PRIORITY.__getitem__)
    supporting = tuple(
        transcript for transcript in shared if per_transcript[transcript] is best_fit
    )
    return _base_assessment(
        candidate,
        rule,
        best_fit,
        condition,
        shared=shared,
        supporting=supporting,
        anchor_count=anchor_count,
    )


@dataclass(frozen=True)
class ScoredAssessment:
    assessment_id: str
    priority_key: tuple[int, ...]
    assessment: MechanismAssessment

    def __post_init__(self) -> None:
        assessment_id = _validated_token(self.assessment_id, "assessment_id")
        if not isinstance(self.priority_key, tuple) or not self.priority_key:
            raise MechanismInputError("priority_key must be a non-empty tuple")
        if any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in self.priority_key
        ):
            raise MechanismInputError("priority_key values must be integers")
        if not isinstance(self.assessment, MechanismAssessment):
            raise MechanismInputError("assessment must be a MechanismAssessment")
        object.__setattr__(self, "assessment_id", assessment_id)


@dataclass(frozen=True)
class RankedAssessment:
    assessment_id: str
    priority_key: tuple[int, ...]
    rank_interval: tuple[int, int]
    midrank: float
    tie_size: int
    assessment: MechanismAssessment


def rank_assessments(rows: Iterable[ScoredAssessment]) -> tuple[RankedAssessment, ...]:
    """Rank higher integer priority keys first while preserving exact ties.

    Identifiers determine only deterministic display order inside a tie; they
    do not change the shared rank interval or midrank.
    """

    materialized = tuple(rows)
    if any(not isinstance(row, ScoredAssessment) for row in materialized):
        raise MechanismInputError("rows must contain ScoredAssessment values")
    identifiers = [row.assessment_id for row in materialized]
    if len(set(identifiers)) != len(identifiers):
        raise MechanismInputError("assessment_id values must be unique")
    key_lengths = {len(row.priority_key) for row in materialized}
    if len(key_lengths) > 1:
        raise MechanismInputError("priority_key tuples must have one common length")

    ordered = sorted(
        materialized,
        key=lambda row: (tuple(-value for value in row.priority_key), row.assessment_id),
    )
    ranked: list[RankedAssessment] = []
    first_rank = 1
    for priority_key, group_rows in groupby(ordered, key=lambda row: row.priority_key):
        tied = tuple(group_rows)
        last_rank = first_rank + len(tied) - 1
        midrank = (first_rank + last_rank) / 2.0
        for row in tied:
            ranked.append(
                RankedAssessment(
                    assessment_id=row.assessment_id,
                    priority_key=priority_key,
                    rank_interval=(first_rank, last_rank),
                    midrank=midrank,
                    tie_size=len(tied),
                    assessment=row.assessment,
                )
            )
        first_rank = last_rank + 1
    return tuple(ranked)


__all__ = [
    "AlleleTranscriptEffects",
    "ConditionRelevance",
    "DiseaseConditionEvidence",
    "DiseaseMechanismRule",
    "EvidenceConfidence",
    "GenotypeDepthEvidence",
    "LOF_CONSEQUENCES",
    "MechanismAssessment",
    "MechanismFit",
    "MechanismInputError",
    "PROTEIN_ALTERING_CONSEQUENCES",
    "RankedAssessment",
    "RuleMechanism",
    "ScoredAssessment",
    "TranscriptEffect",
    "VariantGeneEvidence",
    "assess_mechanism_pair",
    "parse_evidence_confidence",
    "rank_assessments",
]
