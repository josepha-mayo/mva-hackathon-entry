"""Deterministic, offline, synthetic-only Track 1 pipeline demonstration.

This module is deliberately narrower than a biological analysis pipeline.  It
accepts only a miniature JSON bundle whose identifiers are visibly synthetic,
uses the existing inheritance candidate generator, and exercises the declared
six-slot configuration semantics with a documented surrogate score.  It never
opens controlled data, contacts a service, or claims that the resulting rank is
biologically meaningful.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evidence_ledger import (
    EvidenceEntry,
    EvidenceLedger,
    load_evidence_ledger,
    validate_evidence_ledger,
)
from .inheritance import (
    AlleleRecord,
    InheritanceCandidate,
    InheritanceInputError,
    InheritanceModel,
    PhaseState,
    VariantKey,
    generate_inheritance_candidates,
)
from .provenance import (
    build_public_manifest,
    canonical_json_bytes,
    semantic_digest,
    validate_public_manifest,
)
from .slot_config import SlotConfig, load_slot_config
from .submission import REQUIRED_FIELDS, load_predictions


BUNDLE_SCHEMA = "mva.synthetic-miniature-bundle/v1"
REPORT_SCHEMA = "mva.synthetic-report-input/v1"
ENGINE_VERSION = "1.0.0"
MAX_BUNDLE_BYTES = 1024 * 1024
MAX_SYNTHETIC_ALLELES = 20
OUTPUT_FILENAMES = (
    "submission.csv",
    "evidence-ledger.json",
    "provenance-runtime.json",
    "report-input.json",
)

_SYNTHETIC_ID = re.compile(r"^syn[a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SYNTHETIC_GENE = re.compile(r"^SYN[A-Z0-9][A-Z0-9._-]*$")
_SYNTHETIC_PHENOTYPE = re.compile(r"^SYNPHENO[0-9]+$")


class SyntheticPipelineError(ValueError):
    """Raised when the synthetic-only pipeline contract is violated."""


@dataclass(frozen=True)
class SyntheticAnnotation:
    """Integer-only synthetic score inputs; none are biological evidence."""

    quality: int
    consequence: int
    orthogonal: int
    gene_disease: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class SyntheticAllele:
    allele_id: str
    record: AlleleRecord
    annotation: SyntheticAnnotation

    def to_dict(self) -> dict[str, Any]:
        return {
            "allele_id": self.allele_id,
            "gene": self.record.gene,
            "chrom": self.record.chrom,
            "pos": self.record.pos,
            "ref": self.record.ref,
            "alt": self.record.alt,
            "zygosity": self.record.zygosity.value,
            "phase_set": self.record.phase_set,
            "haplotype": self.record.haplotype,
            "annotation": self.annotation.to_dict(),
        }


@dataclass(frozen=True)
class SyntheticBundle:
    fixture_id: str
    alleles: tuple[SyntheticAllele, ...]
    phenotype_terms: tuple[str, ...]
    gene_similarity: Mapping[str, int]
    fixture_class: str = "synthetic_only"
    schema: str = BUNDLE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fixture_class": self.fixture_class,
            "fixture_id": self.fixture_id,
            "alleles": [allele.to_dict() for allele in self.alleles],
            "phenotype": {
                "terms": list(self.phenotype_terms),
                "gene_similarity": dict(sorted(self.gene_similarity.items())),
            },
        }


@dataclass(frozen=True)
class RankedSyntheticCandidate:
    rank: int
    candidate: InheritanceCandidate
    raw_score: int
    epcr: str
    components: Mapping[str, int]

    @property
    def candidate_id(self) -> str:
        return f"syn-candidate-{self.rank:03d}"


@dataclass(frozen=True)
class PipelineRun:
    output_dir: Path
    ranked_rows: int
    generated_candidates: int
    eligible_candidates: int

    @property
    def artifacts(self) -> tuple[Path, ...]:
        return tuple(self.output_dir / name for name in OUTPUT_FILENAMES)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SyntheticPipelineError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _exact_fields(value: Any, expected: set[str], *, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SyntheticPipelineError(
            f"{location}: fields must be exactly {sorted(expected)}"
        )
    return value


def _synthetic_id(value: Any, *, location: str) -> str:
    if not isinstance(value, str):
        raise SyntheticPipelineError(f"{location}: expected a synthetic identifier")
    normalized = value.strip().lower()
    if len(normalized) > 128 or _SYNTHETIC_ID.fullmatch(normalized) is None:
        raise SyntheticPipelineError(
            f"{location}: identifier must use the lower-case syn namespace"
        )
    return normalized


def _score(value: Any, *, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise SyntheticPipelineError(f"{location}: expected an integer from 0 through 100")
    return value


def _optional_synthetic_token(value: Any, *, location: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip().casefold().startswith("syn"):
        raise SyntheticPipelineError(f"{location}: non-null values must use the syn namespace")
    return value.strip().lower()


def _parse_annotation(value: Any, *, location: str) -> SyntheticAnnotation:
    source = _exact_fields(
        value,
        {"quality", "consequence", "orthogonal", "gene_disease"},
        location=location,
    )
    return SyntheticAnnotation(
        quality=_score(source["quality"], location=f"{location}.quality"),
        consequence=_score(
            source["consequence"], location=f"{location}.consequence"
        ),
        orthogonal=_score(source["orthogonal"], location=f"{location}.orthogonal"),
        gene_disease=_score(
            source["gene_disease"], location=f"{location}.gene_disease"
        ),
    )


def _parse_allele(value: Any, *, index: int) -> SyntheticAllele:
    location = f"alleles[{index}]"
    source = _exact_fields(
        value,
        {
            "allele_id",
            "gene",
            "chrom",
            "pos",
            "ref",
            "alt",
            "zygosity",
            "phase_set",
            "haplotype",
            "annotation",
        },
        location=location,
    )
    allele_id = _synthetic_id(source["allele_id"], location=f"{location}.allele_id")
    phase_set = _optional_synthetic_token(
        source["phase_set"], location=f"{location}.phase_set"
    )
    haplotype = _optional_synthetic_token(
        source["haplotype"], location=f"{location}.haplotype"
    )
    try:
        record = AlleleRecord(
            gene=source["gene"],
            chrom=source["chrom"],
            pos=source["pos"],
            ref=source["ref"],
            alt=source["alt"],
            zygosity=source["zygosity"],
            phase_set=phase_set,
            haplotype=haplotype,
        )
    except (InheritanceInputError, TypeError) as exc:
        raise SyntheticPipelineError(f"{location}: {exc}") from exc
    if _SYNTHETIC_GENE.fullmatch(record.gene) is None:
        raise SyntheticPipelineError(
            f"{location}.gene: every gene label must use the upper-case SYN namespace"
        )
    return SyntheticAllele(
        allele_id=allele_id,
        record=record,
        annotation=_parse_annotation(
            source["annotation"], location=f"{location}.annotation"
        ),
    )


def load_synthetic_bundle(path: str | Path) -> SyntheticBundle:
    """Load a strict miniature bundle and reject anything not visibly synthetic."""

    source_path = Path(path)
    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        raise SyntheticPipelineError("synthetic bundle is not readable") from exc
    if len(payload) > MAX_BUNDLE_BYTES:
        raise SyntheticPipelineError("synthetic bundle exceeds the 1 MiB limit")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except SyntheticPipelineError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyntheticPipelineError("synthetic bundle is not valid UTF-8 JSON") from exc

    source = _exact_fields(
        value,
        {"schema", "fixture_class", "fixture_id", "alleles", "phenotype"},
        location="bundle",
    )
    if source["schema"] != BUNDLE_SCHEMA:
        raise SyntheticPipelineError(f"bundle.schema must be {BUNDLE_SCHEMA!r}")
    if source["fixture_class"] != "synthetic_only":
        raise SyntheticPipelineError("bundle.fixture_class must be 'synthetic_only'")
    fixture_id = _synthetic_id(source["fixture_id"], location="bundle.fixture_id")

    raw_alleles = source["alleles"]
    if not isinstance(raw_alleles, list) or not 2 <= len(raw_alleles) <= MAX_SYNTHETIC_ALLELES:
        raise SyntheticPipelineError(
            f"bundle.alleles must contain 2 through {MAX_SYNTHETIC_ALLELES} records"
        )
    alleles = tuple(_parse_allele(item, index=index) for index, item in enumerate(raw_alleles))
    allele_ids = [allele.allele_id for allele in alleles]
    if len(set(allele_ids)) != len(allele_ids):
        raise SyntheticPipelineError("bundle.alleles contains duplicate allele_id values")
    variant_keys = [allele.record.variant_key for allele in alleles]
    if len(set(variant_keys)) != len(variant_keys):
        raise SyntheticPipelineError("bundle.alleles contains duplicate variant keys")

    phenotype = _exact_fields(
        source["phenotype"], {"terms", "gene_similarity"}, location="bundle.phenotype"
    )
    raw_terms = phenotype["terms"]
    if not isinstance(raw_terms, list) or not 1 <= len(raw_terms) <= 10:
        raise SyntheticPipelineError("bundle.phenotype.terms must contain 1 through 10 labels")
    terms: list[str] = []
    for index, raw_term in enumerate(raw_terms):
        if not isinstance(raw_term, str):
            raise SyntheticPipelineError(
                f"bundle.phenotype.terms[{index}]: expected text"
            )
        term = raw_term.strip().upper()
        if _SYNTHETIC_PHENOTYPE.fullmatch(term) is None:
            raise SyntheticPipelineError(
                f"bundle.phenotype.terms[{index}]: label must match SYNPHENO plus digits"
            )
        terms.append(term)
    if len(set(terms)) != len(terms):
        raise SyntheticPipelineError("bundle.phenotype.terms contains duplicate labels")

    raw_similarity = phenotype["gene_similarity"]
    if not isinstance(raw_similarity, Mapping):
        raise SyntheticPipelineError("bundle.phenotype.gene_similarity must be an object")
    genes = {allele.record.gene for allele in alleles}
    if set(raw_similarity) != genes:
        raise SyntheticPipelineError(
            "bundle.phenotype.gene_similarity must contain exactly the synthetic gene labels"
        )
    gene_similarity = {
        gene: _score(raw_similarity[gene], location=f"bundle.phenotype.gene_similarity.{gene}")
        for gene in sorted(genes)
    }
    return SyntheticBundle(
        fixture_id=fixture_id,
        alleles=alleles,
        phenotype_terms=tuple(terms),
        gene_similarity=gene_similarity,
    )


def _integer_mean(values: Sequence[int]) -> int:
    return sum(values) // len(values)


def _model_bonus(candidate: InheritanceCandidate) -> int:
    if candidate.model is InheritanceModel.COMPOUND_HETEROZYGOUS:
        return 30 if candidate.phase_state is PhaseState.TRANS_CONFIRMED else 5
    return {
        InheritanceModel.HOMOZYGOUS_RECESSIVE: 20,
        InheritanceModel.DOMINANT: 0,
        InheritanceModel.X_LINKED: 10,
        InheritanceModel.MITOCHONDRIAL: 5,
    }[candidate.model]


def _candidate_components(
    candidate: InheritanceCandidate,
    *,
    config: SlotConfig,
    annotations: Mapping[VariantKey, SyntheticAnnotation],
    gene_similarity: Mapping[str, int],
) -> dict[str, int]:
    candidate_annotations = [annotations[key] for key in candidate.variant_keys]
    quality = _integer_mean([item.quality for item in candidate_annotations])
    consequence = _integer_mean([item.consequence for item in candidate_annotations])
    orthogonal = (
        _integer_mean([item.orthogonal for item in candidate_annotations])
        if config.input_evidence == "full_prespecified_local_evidence"
        else 0
    )
    # The fixture contains only a gene-linked phenotype signal.  It is therefore
    # removed for both the no-phenotype and novel-gene-mask ablations.
    phenotype = gene_similarity[candidate.gene] if config.phenotype_mode == "enabled" else 0
    gene_disease = (
        _integer_mean([item.gene_disease for item in candidate_annotations])
        if config.gene_disease_knowledge == "enabled"
        else 0
    )
    return {
        "quality": quality,
        "consequence": consequence,
        "orthogonal": orthogonal,
        "phenotype": phenotype,
        "gene_disease": gene_disease,
        "inheritance_bonus": _model_bonus(candidate),
    }


def _raw_score(config: SlotConfig, components: Mapping[str, int]) -> int:
    if config.ranking_backend == "integrated_public_auto":
        return (
            2 * components["quality"]
            + 3 * components["consequence"]
            + 2 * components["orthogonal"]
            + 2 * components["phenotype"]
            + components["gene_disease"]
            + components["inheritance_bonus"]
        )
    # This is intentionally a small deterministic surrogate branch.  It does
    # not invoke or imitate the biological validity of Exomiser.
    return (
        components["quality"]
        + 4 * components["consequence"]
        + 3 * components["phenotype"]
        + 2 * components["gene_disease"]
        + components["inheritance_bonus"]
    )


def _epcr(rank: int) -> str:
    millionths = 1_000_000 - (rank - 1) * 50_000
    return f"{millionths // 1_000_000}.{millionths % 1_000_000:06d}"


def rank_synthetic_candidates(
    bundle: SyntheticBundle, config: SlotConfig
) -> tuple[tuple[RankedSyntheticCandidate, ...], int, int]:
    """Apply declared slot switches to a deterministic synthetic surrogate."""

    generated = generate_inheritance_candidates(
        synthetic_allele.record for synthetic_allele in bundle.alleles
    )
    eligible = tuple(
        candidate
        for candidate in generated
        if not (
            config.compound_heterozygous_pairing == "disabled"
            and candidate.model is InheritanceModel.COMPOUND_HETEROZYGOUS
        )
    )
    if not eligible:
        raise SyntheticPipelineError("synthetic bundle generated no eligible candidates")

    annotations = {
        synthetic_allele.record.variant_key: synthetic_allele.annotation
        for synthetic_allele in bundle.alleles
    }
    scored: list[tuple[int, InheritanceCandidate, Mapping[str, int]]] = []
    for candidate in eligible:
        components = _candidate_components(
            candidate,
            config=config,
            annotations=annotations,
            gene_similarity=bundle.gene_similarity,
        )
        scored.append((_raw_score(config, components), candidate, components))
    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].model.value,
            item[1].gene,
            item[1].variant_keys,
            item[1].phase_state.value if item[1].phase_state else "",
        )
    )
    ranked = tuple(
        RankedSyntheticCandidate(
            rank=rank,
            candidate=candidate,
            raw_score=raw_score,
            epcr=_epcr(rank),
            components=dict(components),
        )
        for rank, (raw_score, candidate, components) in enumerate(scored[:10], start=1)
    )
    return ranked, len(generated), len(eligible)


def _submission_bytes(ranked: Sequence[RankedSyntheticCandidate]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=REQUIRED_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in ranked:
        variants = item.candidate.variant_keys
        first = variants[0]
        second = variants[1] if len(variants) == 2 else None
        writer.writerow(
            {
                "proband_id": "PROBAND01",
                "chrom_1": first[0],
                "pos_1": first[1],
                "ref_1": first[2],
                "alt_1": first[3],
                "chrom_2": second[0] if second else "",
                "pos_2": second[1] if second else "",
                "ref_2": second[2] if second else "",
                "alt_2": second[3] if second else "",
                "epcr": item.epcr,
                "finding_type": "primary",
                "notes": (
                    f"Synthetic software-only rank; candidate={item.candidate_id}; "
                    f"model={item.candidate.model.value}; raw_synthetic_score={item.raw_score}."
                ),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _engine_digest() -> str:
    # Universal-newline decoding makes this source digest independent of a
    # checkout's LF/CRLF policy while still changing with executable text.
    source = Path(__file__).read_text(encoding="utf-8").encode("utf-8")
    return _sha256_bytes(source)


def _slot_value(config: SlotConfig) -> dict[str, Any]:
    return asdict(config)


def _evidence_ledger(
    *,
    bundle: SyntheticBundle,
    config: SlotConfig,
    ranked: Sequence[RankedSyntheticCandidate],
    submission_digest: str,
    engine_digest: str,
    run_digest: str,
    config_digest: str,
) -> EvidenceLedger:
    entries: list[EvidenceEntry] = []
    phase = (
        "phenotype_aware_rerank"
        if config.phenotype_mode == "enabled"
        else "phenotype_blind_discovery"
    )
    for item in ranked:
        phase_state = (
            item.candidate.phase_state.value
            if item.candidate.phase_state is not None
            else "not_applicable"
        )
        counterevidence = (
            ["The supplied synthetic phase labels do not resolve this pair."]
            if item.candidate.phase_state is PhaseState.UNRESOLVED
            else []
        )
        entries.append(
            EvidenceEntry(
                evidence_id=f"syn-ranking-{item.rank:03d}",
                model_slot=config.slot,
                claim=(
                    "The deterministic synthetic scoring rule emitted this row "
                    "at the recorded rank."
                ),
                allele_or_pair_id=item.candidate_id,
                evidence_type="synthetic-ranking",
                privacy_class="synthetic",
                phase=phase,
                phase_state=phase_state,
                direction="supports",
                assessment_status="positive",
                method_id=config.method_id,
                source_class="synthetic_fixture",
                source_identifier=bundle.fixture_id,
                source_version="synthetic-miniature-v1",
                source_url=None,
                tool_name="mva-synthetic-pipeline",
                tool_version=ENGINE_VERSION,
                tool_digest=engine_digest,
                run_digest=run_digest,
                config_digest=config_digest,
                result=f"rank-{item.rank}",
                unit="synthetic ordinal position",
                independent_replication="not_attempted",
                uncertainty=(
                    "This rank demonstrates deterministic software behavior only "
                    "and has no biological calibration."
                ),
                counterevidence=counterevidence,
                decision_effect="promote" if item.rank == 1 else "retain",
                artifact_path="submission.csv",
                artifact_sha256=submission_digest,
                manual_action=None,
                reviewer=None,
                reviewed_at=None,
                not_assessable_reason=None,
                limitations=(
                    "Synthetic annotations and phenotype labels are not evidence "
                    "about any person or disease.",
                ),
            )
        )
    entries.append(
        EvidenceEntry(
            evidence_id="syn-gap-biological-validation",
            model_slot=config.slot,
            claim=(
                "Biological and read-level validation are outside this miniature "
                "synthetic exercise."
            ),
            allele_or_pair_id=None,
            evidence_type="biological-validation",
            privacy_class="synthetic",
            phase="orthogonal_validation",
            phase_state="not_assessable",
            direction="neutral",
            assessment_status="not_assessable",
            method_id=config.method_id,
            source_class="synthetic_fixture",
            source_identifier=bundle.fixture_id,
            source_version="synthetic-miniature-v1",
            source_url=None,
            tool_name="mva-synthetic-pipeline",
            tool_version=ENGINE_VERSION,
            tool_digest=engine_digest,
            run_digest=run_digest,
            config_digest=config_digest,
            result=None,
            unit=None,
            independent_replication="not_assessable",
            uncertainty=(
                "No conclusion about a real case can be inferred from absent "
                "real modalities."
            ),
            counterevidence=(),
            decision_effect="defer",
            artifact_path=None,
            artifact_sha256=None,
            manual_action="Do not convert this missing modality into negative evidence.",
            reviewer=None,
            reviewed_at=None,
            not_assessable_reason=(
                "The fixture intentionally contains no reads, real annotations, "
                "or clinical observations."
            ),
            limitations=(
                "The software demonstration does not establish biological or diagnostic validity.",
            ),
        )
    )
    ledger = EvidenceLedger(
        ledger_id=f"syn-slot-{config.slot}-pipeline-ledger",
        purpose=(
            "Record deterministic synthetic ranking observations and explicit scientific gaps "
            f"for predeclared Track 1 slot {config.slot}."
        ),
        entries=entries,
    )
    return validate_evidence_ledger(ledger, public_only=True)


def _provenance_manifest(
    *, bundle: SyntheticBundle, config: SlotConfig, engine_digest: str
) -> dict[str, Any]:
    runtime_version = ".".join(str(part) for part in sys.version_info[:3])
    backend_label = (
        "synthetic-integrated-surrogate"
        if config.ranking_backend == "integrated_public_auto"
        else "synthetic-exomiser-surrogate"
    )
    return build_public_manifest(
        code_revision=f"phase1-synthetic-pipeline-{ENGINE_VERSION}",
        code_digest=engine_digest,
        tools={
            "mva-synthetic-pipeline": {
                "version": ENGINE_VERSION,
                "digest": engine_digest,
            }
        },
        public_references={
            "synthetic-fixture-contract": "synthetic-miniature-v1",
        },
        settings={
            "bundle_id": bundle.fixture_id,
            "fixture_class": bundle.fixture_class,
            "slot": config.slot,
            "method_id": config.method_id,
            "ranking_backend_requested": config.ranking_backend,
            "ranking_engine": backend_label,
            "network_access": config.network_access,
            "hosted_services_used": False,
            "manual_candidate_injection": config.manual_candidate_injection,
            "runtime": {
                "implementation": sys.implementation.name,
                "python_version": runtime_version,
                "byteorder": sys.byteorder,
            },
            "determinism": {
                "timestamps_omitted": True,
                "randomness_used": False,
                "stable_tie_break": True,
            },
        },
        aggregate_methods=(
            "strict synthetic namespace and schema validation",
            "deterministic inheritance candidate enumeration",
            "declared slot-aware synthetic surrogate ranking",
            "strict challenge CSV preflight",
        ),
    )


def _report_summary(
    *,
    bundle: SyntheticBundle,
    config: SlotConfig,
    ranked: Sequence[RankedSyntheticCandidate],
    generated_count: int,
    eligible_count: int,
    evidence_count: int,
) -> dict[str, Any]:
    backend_label = (
        "synthetic-integrated-surrogate"
        if config.ranking_backend == "integrated_public_auto"
        else "synthetic-exomiser-surrogate"
    )
    limitations = [
        "The miniature inputs are invented and contain no controlled or "
        "participant-derived content.",
        "Ranks and EPCR values are deterministic synthetic ordinals, not calibrated probabilities.",
        "No biological causality, diagnostic validity, or performance on "
        "challenge data was evaluated.",
        "No reads, transcript engine, public disease resource, hosted service, "
        "or external ranking executable was used.",
    ]
    if config.ranking_backend == "exomiser_baseline":
        limitations.append(
            "The baseline slot exercises a synthetic surrogate formula; it is "
            "not an Exomiser execution."
        )
    return {
        "schema": REPORT_SCHEMA,
        "scope": "synthetic-software-demonstration",
        "fixture": {
            "fixture_id": bundle.fixture_id,
            "fixture_class": bundle.fixture_class,
            "phenotype_labels": len(bundle.phenotype_terms),
        },
        "slot": {
            "number": config.slot,
            "method_id": config.method_id,
            "scientific_question": config.scientific_question,
            "phenotype_mode": config.phenotype_mode,
            "gene_disease_knowledge": config.gene_disease_knowledge,
            "ranking_backend_requested": config.ranking_backend,
            "ranking_engine": backend_label,
            "input_evidence": config.input_evidence,
            "compound_heterozygous_pairing": config.compound_heterozygous_pairing,
        },
        "execution": {
            "network_access": "disabled",
            "hosted_services_used": False,
            "controlled_content_used": False,
            "timestamps_in_content": False,
            "randomness_used": False,
        },
        "counts": {
            "synthetic_alleles": len(bundle.alleles),
            "generated_candidates": generated_count,
            "eligible_candidates": eligible_count,
            "ranked_rows": len(ranked),
            "evidence_entries": evidence_count,
            "not_assessable_entries": 1,
        },
        "ranking": [
            {
                "rank": item.rank,
                "candidate_id": item.candidate_id,
                "inheritance_model": item.candidate.model.value,
                "phase_state": (
                    item.candidate.phase_state.value
                    if item.candidate.phase_state is not None
                    else "not_applicable"
                ),
                "epcr": item.epcr,
                "raw_synthetic_score": item.raw_score,
                "score_components": dict(item.components),
            }
            for item in ranked
        ],
        "supported_claims": [
            "The strict local validators accepted this synthetic-only transformation.",
            "The declared slot switches were applied by the documented surrogate score.",
            "Repeated runs with identical code, inputs, config, and runtime "
            "produce identical bytes.",
        ],
        "limitations": limitations,
    }


def _validate_report(value: Any, *, expected_rows: int) -> Mapping[str, Any]:
    source = _exact_fields(
        value,
        {
            "schema",
            "scope",
            "fixture",
            "slot",
            "execution",
            "counts",
            "ranking",
            "supported_claims",
            "limitations",
        },
        location="report",
    )
    if source["schema"] != REPORT_SCHEMA or source["scope"] != "synthetic-software-demonstration":
        raise SyntheticPipelineError("report schema or scope is invalid")
    ranking = source["ranking"]
    if not isinstance(ranking, list) or len(ranking) != expected_rows:
        raise SyntheticPipelineError("report ranking does not match the validated CSV")
    counts = source["counts"]
    if not isinstance(counts, Mapping) or counts.get("ranked_rows") != expected_rows:
        raise SyntheticPipelineError("report ranked_rows does not match the validated CSV")
    execution = source["execution"]
    if not isinstance(execution, Mapping) or execution.get("network_access") != "disabled":
        raise SyntheticPipelineError("report must record disabled network access")
    if execution.get("controlled_content_used") is not False:
        raise SyntheticPipelineError("report must record synthetic-only content")
    return source


def _stage_and_validate(output_dir: Path, payloads: Mapping[str, bytes]) -> None:
    if output_dir.exists():
        raise SyntheticPipelineError("output directory already exists; overwrite is prohibited")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    try:
        for name in OUTPUT_FILENAMES:
            (staged / name).write_bytes(payloads[name])

        predictions = load_predictions(staged / "submission.csv")
        ledger = load_evidence_ledger(staged / "evidence-ledger.json", public_only=True)
        observed_submission_digest = _sha256_bytes(payloads["submission.csv"])
        for entry in ledger.entries:
            if (
                entry.artifact_path == "submission.csv"
                and entry.artifact_sha256 != observed_submission_digest
            ):
                raise SyntheticPipelineError("evidence ledger submission digest mismatch")

        provenance_value = json.loads(
            (staged / "provenance-runtime.json").read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
        validate_public_manifest(provenance_value)
        report_value = json.loads(
            (staged / "report-input.json").read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
        _validate_report(report_value, expected_rows=len(predictions))
        if {path.name for path in staged.iterdir()} != set(OUTPUT_FILENAMES):
            raise SyntheticPipelineError("staging directory contains an unexpected artifact")
        os.replace(staged, output_dir)
    finally:
        if staged.exists():
            # ``staged`` is created above, is a direct child of the chosen
            # output parent, and never points at user-provided existing data.
            shutil.rmtree(staged)


def run_synthetic_pipeline(
    *, slot_config: str | Path, synthetic_bundle: str | Path, output_dir: str | Path
) -> PipelineRun:
    """Build and atomically publish the four deterministic synthetic artifacts."""

    config = load_slot_config(slot_config)
    bundle = load_synthetic_bundle(synthetic_bundle)
    ranked, generated_count, eligible_count = rank_synthetic_candidates(bundle, config)
    submission = _submission_bytes(ranked)
    submission_digest = _sha256_bytes(submission)
    engine_digest = _engine_digest()
    config_digest = semantic_digest(_slot_value(config))
    run_digest = semantic_digest(
        {
            "engine_version": ENGINE_VERSION,
            "slot_config": _slot_value(config),
            "synthetic_bundle": bundle.to_dict(),
        }
    )
    ledger = _evidence_ledger(
        bundle=bundle,
        config=config,
        ranked=ranked,
        submission_digest=submission_digest,
        engine_digest=engine_digest,
        run_digest=run_digest,
        config_digest=config_digest,
    )
    provenance = _provenance_manifest(
        bundle=bundle, config=config, engine_digest=engine_digest
    )
    report = _report_summary(
        bundle=bundle,
        config=config,
        ranked=ranked,
        generated_count=generated_count,
        eligible_count=eligible_count,
        evidence_count=len(ledger.entries),
    )
    payloads = {
        "submission.csv": submission,
        "evidence-ledger.json": canonical_json_bytes(ledger.to_dict()) + b"\n",
        "provenance-runtime.json": canonical_json_bytes(provenance) + b"\n",
        "report-input.json": canonical_json_bytes(report) + b"\n",
    }
    destination = Path(output_dir).resolve()
    _stage_and_validate(destination, payloads)
    return PipelineRun(
        output_dir=destination,
        ranked_rows=len(ranked),
        generated_candidates=generated_count,
        eligible_candidates=eligible_count,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic synthetic-only Track 1 demonstration artifacts."
    )
    parser.add_argument("--slot-config", type=Path, required=True)
    parser.add_argument("--synthetic-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_synthetic_pipeline(
            slot_config=args.slot_config,
            synthetic_bundle=args.synthetic_bundle,
            output_dir=args.output_dir,
        )
    except (ValueError, OSError) as exc:
        parser.exit(2, f"NO-GO: synthetic pipeline failed: {exc}\n")
    print(
        "GO: deterministic synthetic software-demonstration artifacts written "
        f"({result.ranked_rows} rows); no biological validation or submission performed"
    )
    return 0


__all__ = [
    "BUNDLE_SCHEMA",
    "ENGINE_VERSION",
    "MAX_BUNDLE_BYTES",
    "OUTPUT_FILENAMES",
    "REPORT_SCHEMA",
    "PipelineRun",
    "RankedSyntheticCandidate",
    "SyntheticAllele",
    "SyntheticAnnotation",
    "SyntheticBundle",
    "SyntheticPipelineError",
    "load_synthetic_bundle",
    "main",
    "rank_synthetic_candidates",
    "run_synthetic_pipeline",
]
