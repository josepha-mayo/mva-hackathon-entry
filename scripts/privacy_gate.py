"""Fail closed when controlled data or credentials appear in a public tree.

The gate inspects the working tree, staged Git blobs that differ from disk, and
every reachable historical Git blob. It is deliberately conservative: opaque
archives and binary documents require an explicit offline review before they
can be added to the public repository.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import os
import re
import stat
import subprocess
import sys
import unicodedata
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.submission import SubmissionError, load_predictions_bytes
from mva_hackathon.candidate_ledger import (
    CandidateLedgerError,
    load_sample_stewardship_plan,
    validate_candidate_release_bundle_bytes,
    validate_candidate_release_ledger_bytes,
)
from mva_hackathon.reproducibility import (
    MANIFEST_PATH as TRACK2_REPRODUCIBILITY_MANIFEST_PATH,
    validate_manifest_bytes as validate_track2_reproducibility_manifest,
)
from mva_hackathon.program_gates import _CLAIM_CONFUSABLES

MAX_PUBLIC_BYTES = 10 * 1024 * 1024

RELEASE_MANIFEST_PATH = PurePosixPath("release/release-artifacts.json")
RELEASE_MANIFEST_SCHEMA = "mva-public-release-quarantine/v3"
NEXT_RELEASE_MANIFEST_SCHEMA = "mva-public-release-quarantine/v4"
RELEASE_ARTIFACT_PATHS = {
    "track1_submission_csv": PurePosixPath(
        "submissions/track1/josephmayo_track1_bub1b_pair.csv"
    ),
    "track1_methods_report": PurePosixPath("reports/josephmayo_track1_report.md"),
    "track2_repositioning_report": PurePosixPath(
        "reports/josephmayo_track2_report.md"
    ),
    "track2_pitch_script": PurePosixPath(
        "reports/josephmayo_track2_pitch_script.md"
    ),
    "track2_reproducibility_manifest": TRACK2_REPRODUCIBILITY_MANIFEST_PATH,
    "track2_candidate_evidence_ledger": PurePosixPath(
        "release/track2-candidate-ledger.json"
    ),
    "track2_candidate_ranking_receipt": PurePosixPath(
        "release/track2-candidate-ranking.json"
    ),
}
FROZEN_V3_RELEASE_ROLES = frozenset(
    {
        "track1_submission_csv",
        "track1_methods_report",
        "track2_repositioning_report",
        "track2_pitch_script",
        "track2_reproducibility_manifest",
    }
)
RELEASE_MANIFEST_SCHEMA_ARTIFACT_PATHS = {
    "mva-public-release-quarantine/v1": {
        role: path
        for role, path in RELEASE_ARTIFACT_PATHS.items()
        if role in {"track1_submission_csv", "track1_methods_report"}
    },
    "mva-public-release-quarantine/v2": {
        role: path
        for role, path in RELEASE_ARTIFACT_PATHS.items()
        if role
        in {
            "track1_submission_csv",
            "track1_methods_report",
            "track2_repositioning_report",
        }
    },
    RELEASE_MANIFEST_SCHEMA: {
        role: path
        for role, path in RELEASE_ARTIFACT_PATHS.items()
        if role in FROZEN_V3_RELEASE_ROLES
    },
    NEXT_RELEASE_MANIFEST_SCHEMA: RELEASE_ARTIFACT_PATHS,
}
RELEASE_MANIFEST_TOP_LEVEL_KEYS = frozenset({"schema", "artifacts"})
RELEASE_MANIFEST_ARTIFACT_KEYS = frozenset(
    {"role", "path", "status", "sha256"}
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
CANDIDATE_REPORT_DIGEST_PATTERNS = {
    "track2_candidate_evidence_ledger": re.compile(
        r"(?m)^\*\*Candidate evidence ledger SHA-256:\*\* "
        r"`([0-9a-f]{64})`\s*$"
    ),
    "track2_candidate_ranking_receipt": re.compile(
        r"(?m)^\*\*Candidate ranking receipt SHA-256:\*\* "
        r"`([0-9a-f]{64})`\s*$"
    ),
}


@dataclass(frozen=True)
class ReleaseAllowance:
    """One path-specific publication exception bound to exact approved bytes."""

    role: str
    sha256: str

FORBIDDEN_SUFFIXES = {
    ".bam", ".bai", ".bcf", ".bed", ".bim", ".crai", ".cram", ".csi",
    ".dcm", ".dicom", ".fam", ".fastq", ".feather", ".fq", ".gvcf",
    ".gzi", ".h5", ".h5ad", ".hdf5", ".mt", ".parquet", ".ped",
    ".pgen", ".psam", ".pvar", ".sam", ".tbi", ".vcf",
}
FORBIDDEN_ENDINGS = (
    ".fastq.gz", ".fq.gz", ".g.vcf.gz", ".gvcf.gz", ".vcf.gz", ".vcf.bgz",
    ".phenopacket.json",
)
OPAQUE_ENDINGS = (
    ".7z", ".arrow", ".bgz", ".bz2", ".db", ".docx", ".duckdb", ".gz",
    ".joblib", ".jpeg", ".jpg", ".ods", ".parquet", ".pdf", ".pickle",
    ".pkl", ".png", ".rar", ".sqlite", ".sqlite3", ".tar", ".tar.gz",
    ".tgz", ".tif", ".tiff", ".webp", ".xls", ".xlsm", ".xlsx", ".xz",
    ".zip", ".zst",
)
FORBIDDEN_NAMES = {
    ".env", "credentials", "credentials.json", "id_ed25519", "id_rsa",
    "stored_tokens", "token",
}
SENSITIVE_DIR_NAMES = {"controlled", "data", "private"}

SECRET_PATTERNS = {
    "Hugging Face token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9_]{20,}\b"),
    "AWS access-key id": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
CONTROLLED_TEXT_PATTERNS = {
    "VCF payload marker": re.compile(r"(?m)^##fileformat=VCFv"),
    "SAM payload marker": re.compile(r"(?m)^@(?:HD|SQ|RG|PG)\t"),
    "FASTQ payload shape": re.compile(
        r"\A@[^\r\n]+\r?\n[ACGTNacgtn]+\r?\n\+[^\r\n]*\r?\n[!-~]+\r?\n"
    ),
    "Git LFS pointer": re.compile(
        r"\Aversion https://git-lfs\.github\.com/spec/v1\r?\noid sha256:[0-9a-f]{64}\r?\n"
    ),
}
HPO_PATTERN = re.compile(r"\bHP:\s*\d{7}\b", re.IGNORECASE)

# Publication-specific checks inspect every text file except this policy's own
# source.  The source necessarily contains the receipt phrases and identifier
# shapes that it rejects; keeping the exception path-based and one-file-wide
# prevents a similarly named file elsewhere from bypassing review.  Raw data,
# credential, size, magic-signature, and path checks still apply to this file.
PUBLICATION_POLICY_PATH_ALLOWLIST = frozenset(
    {PurePosixPath("scripts/privacy_gate.py")}
)
OPERATIONAL_RECEIPT_PATH_ALLOWLIST = frozenset(
    {PurePosixPath("scripts/storage_preflight.py")}
)

# Uppercase token literals this policy source necessarily contains (constant
# names and allowlist entries). When the policy file itself is scanned, only
# these identifiers are exempt; any other identifier still flags, so a planted
# identifier cannot hide inside the exemption.
POLICY_SOURCE_SELF_TOKENS = frozenset(
    {
        "A0", "A1", "A-Z0", "A-Z0-", "ALPHA", "ARMS", "B10", "B11", "B12",
        "B13",
        "B14",
        "BCF", "BLE001", "BUB1B", "BUB1B-", "BUBR1", "CLASSIFICATIONS",
        "COMMANDS", "CRAM", "E402", "END", "ENDMDL", "ESTIMANDS", "G418",
        "GO", "GPT-5", "HMAC-SHA256", "L737", "METHODS", "MITOCHONDRIAL",
        "MVA", "N1002K", "NFD", "NFKC", "NO-GO", "OXT", "PARTITIONS",
        "PATH", "PMC7610696", "PPS", "PRIORITIES", "PYTHONPATH", "R32",
        "R40", "R42", "R43", "R44", "REPLICATION", "ROLES", "SCHEMA",
        "SEED", "SHA-256-", "SP0", "STAGES", "STATUSES", "STRENGTHS",
        "SWE-2", "TER", "TG487",
    }
)
# Receipt labels the operational preflight source legitimately contains in its
# own command strings. Other receipt-phrase labels still apply to that file.
OPERATIONAL_RECEIPT_SELF_LABELS = frozenset(
    {"machine/storage receipt", "machine-local absolute path"}
)


def _re_compile_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets covered by each re.compile(...) call."""

    spans: list[tuple[int, int]] = []
    for match in re.finditer(
        r"re\.(?:compile|search|match|fullmatch|sub|finditer|findall|split)\(",
        text,
    ):
        depth = 0
        index = match.end() - 1
        while index < len(text):
            char = text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    spans.append((match.end() - 1, index + 1))
                    break
            index += 1
    return spans


def _is_pattern_definition_site(
    text: str, offset: int, spans: list[tuple[int, int]] | None = None
) -> bool:
    """True when a match sits inside a re.compile(...) call's parentheses.

    A receipt phrase planted on a line merely containing ``r"`` no longer
    qualifies — the match must fall inside an actual pattern argument.
    """

    if spans is None:
        spans = _re_compile_spans(text)
    return any(start <= offset < end for start, end in spans)

_SCAN_STRIP_CATEGORIES = frozenset({"Cf", "Cc", "Mn", "Me", "Cs"})
_SCAN_CONFUSABLES = {
    **_CLAIM_CONFUSABLES,
    **{
        ord(chr(codepoint).upper()): value.upper()
        for codepoint, value in _CLAIM_CONFUSABLES.items()
    },
}
_BASE64_RUN = re.compile(
    r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/=_-]{24,}={0,2}(?![A-Za-z0-9+/=_-])"
)


def _scan_fold(text: str) -> str:
    """Case-preserving NFKC + confusable fold for identifier detection."""

    folded = unicodedata.normalize("NFKC", text).translate(_SCAN_CONFUSABLES)
    return "".join(
        char
        for char in unicodedata.normalize("NFD", folded)
        if char == "\n" or unicodedata.category(char) not in _SCAN_STRIP_CATEGORIES
    )


# These are public interface or implementation tokens, not biological claims.
# Synthetic biological fixtures are separately admitted only through the SYN
# namespace, making an accidental real-looking identifier fail closed.
PUBLIC_TECHNICAL_IDENTIFIER_ALLOWLIST = frozenset(
    {
        "BOM", "BWA-MEM2", "CC-BY-4", "CC0-1", "COPY", "GT", "HEAD",
        "ISO-8601", "MT", "NFC", "NTFS", "PAR1", "PAR2", "PROBAND01",
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", "SHA-256", "SHA256",
        "TEMP", "TMP", "UTF-8", "UTF-16", "UTF-32",
    }
)
# These two uppercase split-salt labels are technical only in the frozen public
# development contract and its adapter test. The same tokens elsewhere remain
# subject to the biological-identifier detector.
PUBLIC_PATH_TECHNICAL_IDENTIFIER_ALLOWLIST = {
    PurePosixPath("configs/phen2gene-development-baseline.json"): frozenset(
        {"MVA", "PPS"}
    ),
    PurePosixPath("tests/test_phen2gene_development.py"): frozenset(
        {"MVA", "PPS"}
    ),
    PurePosixPath("scripts/run_generation_selection_benchmark.py"): frozenset(
        {"E402"}
    ),
    PurePosixPath("src/mva_hackathon/generation_selection.py"): frozenset(
        {"ARM_NAMES", "CLASSIFICATIONS", "COMPONENT_FLAGS", "ESTIMANDS", "SCHEMA"}
    ),
    PurePosixPath("src/mva_hackathon/lineage.py"): frozenset(
        {"ARM_NAMES", "CORE_ESTIMANDS", "ESTIMANDS", "FINGERPRINT_KEYS", "QC_FLAGS", "SCHEMA"}
    ),
    PurePosixPath("scripts/run_lineage_adversarial_benchmark.py"): frozenset(
        {"E402"}
    ),
    PurePosixPath("scripts/export_lineage_counts.py"): frozenset({"E402"}),
    PurePosixPath("src/mva_hackathon/candidate_ledger.py"): frozenset(
        {"REPLICATION"}
    ),
    PurePosixPath("scripts/rank_candidate_ledger.py"): frozenset({"E402"}),
    PurePosixPath("scripts/render_candidate_release_bundle.py"): frozenset(
        {"E402"}
    ),
    PurePosixPath("src/mva_hackathon/allele_confirmation.py"): frozenset(
        {
            "PINNED_DATASET_REVISION",
            "PINNED_FASTQ_NAME_DIGEST",
            "DEFAULT_EXPECTED_N_FILES",
            "K_SIZES",
            "MINIMUM_OBSERVATIONS",
            "SCHEMA",
            "STATUSES",
        }
    ),
    PurePosixPath("src/mva_hackathon/clone_safety.py"): frozenset(
        {"ARMS", "DEATH_RATIO_STOP", "SCHEMA", "STATUSES"}
    ),
    PurePosixPath("src/mva_hackathon/arm_allocation.py"): frozenset(
        {
            "ALLOCATION_UNIT",
            "ARMS",
            "ASSIGNMENT_ALGORITHMS",
            "ASSIGNMENT_KEYS",
            "ASSIGNMENT_METHODS",
            "CLAIM_BOUNDARY",
            "COMMITMENT_KEYS",
            "COMMITMENT_MECHANISMS",
            "PLAN_HASH_KEYS",
            "PLAN_SCHEMA",
            "PLATE_KEYS",
            "ROOT_KEYS",
            "SCHEMA",
            "TABLE_SCHEMA",
        }
    ),
    PurePosixPath("src/mva_hackathon/allocation_inference.py"): frozenset(
        {"ALPHA", "SCHEMA"}
    ),
    PurePosixPath("reports/TRACK2_ATTEMPT2_DELTA.md"): frozenset(
        {"HMAC-SHA256", "PYTHONPATH", "SHA-256-"}
    ),
    PurePosixPath("reports/TRACK2_METHOD_IMPROVEMENTS.md"): frozenset(
        {"HMAC-SHA256", "PATH", "PYTHONPATH"}
    ),
    PurePosixPath("reports/TRACK2_RANDOMIZATION_CONTRACT.md"): frozenset(
        {"HMAC-SHA256", "PMC7610696"}
    ),
    PurePosixPath("COMPETITION_CONTRACT.md"): frozenset({"GPT-5", "SWE-2"}),
    PurePosixPath("reports/TRACK2_AI_LINE.md"): frozenset({"GPT-5", "SWE-2"}),
    PurePosixPath("reports/TRACK2_PROGRAM_GATES.md"): frozenset({"N1002K"}),
    PurePosixPath("reports/TRACK2_JUDGE_PACKAGE.md"): frozenset(
        {"BUB1B", "BUBR1"}
    ),
    PurePosixPath("README.md"): frozenset({"BUB1B", "BUB1B-"}),
    PurePosixPath("reports/TRACK2_SESSION_HANDOFF.md"): frozenset(
        {
            "B10", "B11", "B12", "B13", "B14",
            "G418", "GPT-5", "L737", "MITOCHONDRIAL", "N1002K",
            "PATH", "PYTHONPATH",
            "R32", "R40", "R42", "R43", "R44", "TG487",
        }
    ),
    PurePosixPath("reports/TRACK2_EXPOSURE_GATE.md"): frozenset({"G418"}),
    PurePosixPath("tests/test_exposure_gate.py"): frozenset({"G418"}),
    PurePosixPath("reports/PHASE2_SCALE_PLAN.md"): frozenset({"GPT-5"}),
    PurePosixPath("scripts/assess_clone_safety.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/exposure_gate.py"): frozenset(
        {
            "ASSAY_PLAN_SCHEMA",
            "BINDING_CLAIM_BOUNDARY",
            "BINDING_SCHEMA",
            "G418",
            "LINEAGE_COUNTS_SCHEMA",
            "MEASUREMENT_CLASSES",
            "ROW_CLASSES",
            "SAMPLE_RELATIONS",
            "SCHEMA",
            "STATUSES",
            "TIME_PROFILE_CLASSES",
        }
    ),
    PurePosixPath("scripts/assess_exposure_gate.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/program_gates.py"): frozenset(
        {
            "ASSAY_CLASSES",
            "COMPUTATIONAL_ASSAY_CLASSES",
            "CONFIRMATION_PRODUCERS",
            "CONFIRMATION_SCHEMA",
            "CONFIRMATION_STATUSES",
            "DEFAULT_EXPECTED_N_FILES",
            "GENOTYPE_CLASSES",
            "IDENTITY_FIELDS",
            "KMER_SCHEMA",
            "HYPOTHESIS_SCHEMA",
            "LINEAGE_COUNTS_SCHEMA",
            "LIBRARY_MOLECULES",
            "CONFIRMATION_SPECIMENS",
            "LINKAGE_CALLS",
            "MINIMUM_CLONES_PER_EVENT",
            "MISSENSE_RNA_STATES",
            "NFD",
            "NFKC",
            "PD_ENDPOINTS",
            "PHASE_DECISIONS",
            "PHASE_METHODS",
            "PHASE_SPECIMENS",
            "PHASE_SCHEMA",
            "PINNED_FASTQ_NAME_DIGEST",
            "PROGRAM_SCHEMA",
            "CONDITION_CLASSES",
            "SYSTEM_CLASSES",
            "EXPRESSION_CLASSES",
            "FUNCTION_SPECIMENS",
            "SCHEMA",
            "SITE_DECISIONS",
            "STATUSES",
            "STOP_RNA_STATES",
            "TRANSCRIPT_METHODS",
            "TRANSCRIPT_SPECIMENS",
            "TRANSCRIPT_SCHEMA",
            "TRANSCRIPT_STATUSES",
        }
    ),
    PurePosixPath("scripts/assess_program_gates.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/hypothesis.py"): frozenset(
        {
            "EVIDENCE_SCHEMA",
            "EXPOSURE_SCHEMA",
            "HYPOTHESIS_ROLES",
            "IDENTITY_BIND_ROLES",
            "GATE_BIND_ROLES",
            "GATE_BIND_SCHEMAS",
            "PAIR_PROGRAM_ROLES",
            "PROGRAM_SCHEMA",
            "CONTROL_ROLES",
            "CONTROL_FAIL_PHRASES",
            "SCHEMA",
            "STATUS_TO_STRENGTH",
            "STRENGTHS",
        }
    ),
    PurePosixPath("scripts/assess_hypothesis_strength.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/community_pipeline.py"): frozenset(
        {"SCHEMA"}
    ),
    PurePosixPath("scripts/run_community_gates.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/structure_ranking.py"): frozenset(
        {"METHODS", "PRIORITIES", "ROLES", "SCHEMA"}
    ),
    PurePosixPath("scripts/assess_structure_ranking.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/coordinate_geometry.py"): frozenset(
        {
            "CLAIM_BOUNDARY",
            "END",
            "ENDMDL",
            "OXT",
            "SCHEMA",
            "SCRIPT_VERSION",
            "TER",
        }
    ),
    PurePosixPath("scripts/run_coordinate_geometry.py"): frozenset({"E402"}),
    PurePosixPath("tests/test_coordinate_geometry.py"): frozenset(
        {"END", "ENDMDL", "TER"}
    ),
    PurePosixPath("src/mva_hackathon/hypothesis_compare.py"): frozenset(
        {"SCHEMA"}
    ),
    PurePosixPath("tests/test_reproducibility.py"): frozenset({"NO-GO"}),
    PurePosixPath("src/mva_hackathon/next_experiment.py"): frozenset(
        {
            "IDENTITY_GATE_IDS",
            "IDENTITY_STEPS",
            "LATER_STEPS",
            "PROBE_GATE_IDS",
            "SCHEMA",
            "STEP_ORDER",
            "STEP_TO_GATE",
            "WORKSHEET_SCHEMA",
        }
    ),
    PurePosixPath("scripts/assess_next_experiment.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("scripts/assess_sample_stewardship.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("tests/test_sample_stewardship.py"): frozenset({"E402"}),
    PurePosixPath("src/mva_hackathon/sample_stewardship.py"): frozenset(
        {
            "A0",
            "A1",
            "PARTITIONS",
            "REPLICATION",
            "SCHEMA",
            "STAGES",
            "MITOTIC_CONTEXT_CLASSES",
            "TRANSFORMATION_STATES",
        }
    ),
    PurePosixPath("schemas/track2_sample_stewardship.schema.json"): frozenset(
        {"A0", "A1", "REPLICATION"}
    ),
    PurePosixPath("templates/track2_sample_stewardship.synthetic.json"): frozenset(
        {"A0", "A1", "REPLICATION"}
    ),
    PurePosixPath("src/mva_hackathon/phase_monte_carlo.py"): frozenset(
        {
            "CIS_TAIL",
            "DROPOUT_MAJORITY",
            "N_SIMS",
            "SCHEMA",
            "SEED",
            "STRAND_HIGH",
            "STRAND_LOW",
        }
    ),
    PurePosixPath("src/mva_hackathon/culture_window.py"): frozenset(
        {
            "BULK_DROP",
            "COPING_DEATH_ANEUPLOID",
            "COPING_DEATH_EUPLOID",
            "ERROR_ON_DIVISION",
            "GENERATION_DROP",
            "MAX_FALSE_RESCUE",
            "N_SIMS",
            "SCHEMA",
            "SEED",
            "START_ANEUPLOID",
            "START_EUPLOID",
            "VEHICLE_DEATH_ANEUPLOID",
            "VEHICLE_DEATH_EUPLOID",
        }
    ),
    PurePosixPath("src/mva_hackathon/assay_power.py"): frozenset(
        {
            "ENDPOINT_CLASSES",
            "MINIMUM_CLONES",
            "MINIMUM_EVENTS",
            "MINIMUM_OPPORTUNITIES",
            "N_SIMS",
            "PLAN_SCHEMA",
            "SCHEMA",
            "SEED",
            "SUCCESS_RULES",
        }
    ),
    PurePosixPath("scripts/assess_assay_power.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/method_delta.py"): frozenset(
        {
            "CLAIM_BOUNDARY",
            "CULTURE_REMAINING_DIRECTION",
            "FAMILY_BY_SCENARIO",
            "FREEZE_ENVELOPE",
            "HOLDOUT_FAMILIES",
            "REPO_ROOT",
            "SCHEMA",
            "SPEND_LADDER",
            "STRUCTURAL_GATES",
        }
    ),
    PurePosixPath("scripts/assess_method_delta.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/save_path.py"): frozenset(
        {"PIPELINE_FILES", "SCHEMA"}
    ),
    PurePosixPath("scripts/run_save_path_simulation.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("src/mva_hackathon/reproducibility.py"): frozenset(
        {"ARTIFACT_PATHS", "COMMANDS", "MANIFEST_PATH", "SCHEMA"}
    ),
    PurePosixPath("scripts/verify_track2_reproducibility.py"): frozenset(
        {"E402", "GO", "NO-GO"}
    ),
    PurePosixPath("scripts/create_track2_reproducibility_manifest.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("scripts/check_submission_go.py"): frozenset(
        {"E402", "GO", "GPT-5", "NO-GO", "SWE-2"}
    ),
    PurePosixPath("scripts/compare_hypotheses.py"): frozenset({"E402"}),
    PurePosixPath("scripts/confirm_alleles_from_fastq.py"): frozenset(
        {"BLE001", "E402"}
    ),
    PurePosixPath("reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json"): frozenset(
        {"SP0"}
    ),
}
QUOTED_UPPER_IDENTIFIER_PATTERN = re.compile(
    r"[`'\"]([A-Z][A-Z0-9-]{1,15})[`'\"]"
)
GENE_LIKE_TOKEN_PATTERN = re.compile(
    r"\b(?=[A-Z0-9-]{3,16}\b)(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)"
    r"[A-Z][A-Z0-9-]*\b"
)
BIOLOGICAL_CONTEXT_PATTERNS = (
    re.compile(
        r"(?i:\b(?:candidate|causal|diagnostic|disease|target)\s+)"
        r"(?:gene|protein|variant|allele|hypothesis)\s+[`'\"]?"
        r"([A-Z][A-Z0-9-]{1,15})\b"
    ),
    re.compile(
        r"[`'\"]?([A-Z][A-Z0-9-]{1,15})[`'\"]?\s+"
        r"(?i:gene|protein|hypothesis)\b"
    ),
)
EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS = {
    "HGVS-like variant": re.compile(
        r"(?<![A-Za-z0-9_])(?:c|g|m|n|p|r)\s*\.\s*"
        r"(?:[A-Za-z][a-z]{2}|[-*?0-9])[^\s`,;)]*\d[^\s`,;)]*"
    ),
    "dbSNP-like identifier": re.compile(r"\brs\s*\d{3,}[a-z]*\b", re.IGNORECASE),
    "ClinVar accession": re.compile(
        r"\b(?:VCV|RCV|SCV)\s*\d{6,}(?:\.\d+)?[a-z]*\b", re.IGNORECASE
    ),
    "subject identifier": re.compile(
        r"(?i)\b(?:proband|subject|donor|participant|patient)"
        r"[\s_.:/#-]*"
        r"(?:"
        r"(?:id|no|num(?:ber)?|#)[\s_.:/#-]*[A-Za-z]{0,3}\d[A-Za-z0-9-]*"
        r"|[-_:/#][\s_.:/#-]*[A-Za-z]{0,3}\d[A-Za-z0-9-]*"
        r"|[A-Za-z]{0,3}\d{2,}[A-Za-z0-9-]*"
        r"|(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}"
        r")\b"
    ),
    "genomic coordinate": re.compile(
        r"\b(?:chr)?(?:[1-9]|1\d|2[0-2]|X|Y|M|MT)\s*:\s*\d{4,}[a-z]*\b",
        re.IGNORECASE,
    ),
    "RefSeq/Ensembl accession": re.compile(
        r"\b(?:N[MRXCGPW]_|X[MR]_|ENST|ENSP|ENSG)\s*\d{3,}(?:\.\d+)?[a-z]*\b",
        re.IGNORECASE,
    ),
    "HGNC/OMIM accession": re.compile(
        r"\b(?:HGNC|OMIM|MIM)[:#]?\s*\d{4,}[a-z]*\b",
        re.IGNORECASE,
    ),
}
# The portion of a subject-identifier match after the role word is the
# identifier itself; declared-synthetic labels (SYN-*, reviewed technical
# tokens) may stand there legitimately in fixtures.
_SUBJECT_IDENTIFIER_PORTION = re.compile(
    r"(?i)^(?:proband|subject|donor|participant|patient)[\s_.:/#-]*"
)
OPERATIONAL_RECEIPT_PATTERNS = {
    "registration/access receipt": re.compile(
        r"\b(?:official\s+)?registration\s+(?:is\s+|was\s+)?"
        r"(?:complete|completed|submitted)\b|"
        r"\byou\s+have\s+been\s+granted\s+access\b|"
        r"\bsigned-in\s+browser\b.{0,100}\b(?:access|granted)\b|"
        r"\bgated-file\s+metadata\b.{0,100}"
        r"\b(?:confirm(?:s|ed)?|received|returned\s+go|verified)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "personal registration field": re.compile(
        r"(?im)^\s*(?:[-*]\s*)?(?:city(?:\s+and\s+country)?|institution)\s*:"
    ),
    "machine/storage receipt": re.compile(
        r"\b(?:verified\s+live\s+state|host\s+boundary\s+verified|"
        r"Get-BitLockerVolume|tpmtool\s+getdeviceinformation|"
        r"ProtectionStatus\s*=|XTS-AES-\d+|active\s+key\s+protectors?|"
        r"private\s+root\s+now\s+exists|current\s+storage\s+gate\s+fails)\b|"
        r"\b\d+(?:\.\d+)?\s+GiB\s+(?:RAM|free)\b",
        re.IGNORECASE,
    ),
    "machine-local absolute path": re.compile(r"(?<![A-Za-z0-9_])[A-Z]:\\", re.IGNORECASE),
}

MAGIC_SIGNATURES = (
    (b"\x1f\x8b", "gzip/BGZF payload"),
    (b"PK\x03\x04", "ZIP/Office payload"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip payload"),
    (b"Rar!\x1a\x07", "RAR payload"),
    (b"BZh", "bzip2 payload"),
    (b"\xfd7zXZ\x00", "xz payload"),
    (b"\x28\xb5\x2f\xfd", "zstd payload"),
    (b"CRAM", "CRAM payload"),
    (b"BAM\x01", "BAM payload"),
    (b"BCF", "BCF payload"),
    (b"PAR1", "Parquet payload"),
    (b"SQLite format 3\x00", "SQLite payload"),
    (b"%PDF-", "PDF payload requiring metadata/text review"),
    (b"\x89PNG\r\n\x1a\n", "PNG payload requiring metadata review"),
    (b"\xff\xd8\xff", "JPEG payload requiring metadata review"),
)

# These directories are local repository/tooling state rather than public-tree
# content. Their names are the complete directory allowlist; everything else,
# including hidden and ignored directories, is traversed.
NON_PUBLIC_ROOT_DIRECTORY_ALLOWLIST = frozenset(
    {
        PurePosixPath(".git"), PurePosixPath(".mypy_cache"),
        PurePosixPath(".pytest_cache"), PurePosixPath(".ruff_cache"),
        PurePosixPath(".venv"), PurePosixPath("local_dev"),
        PurePosixPath("work"),
    }
)
GENERATED_DIRECTORY_NAME_ALLOWLIST = frozenset({"__pycache__"})


def _path_issue(relative: PurePosixPath) -> str | None:
    lowered = relative.as_posix().lower()
    name = relative.name.lower()
    suffix = relative.suffix.lower()
    if any(part.lower() in SENSITIVE_DIR_NAMES for part in relative.parts[:-1]):
        return "controlled-data directory"
    if suffix in FORBIDDEN_SUFFIXES or lowered.endswith(FORBIDDEN_ENDINGS):
        return "controlled/genomic file type"
    if lowered.endswith(OPAQUE_ENDINGS):
        return "opaque archive/document/image requiring offline review"
    if name in FORBIDDEN_NAMES or name.startswith(".env."):
        return "credential-like filename"
    return None


class _DuplicateJsonKey(ValueError):
    pass


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey("duplicate JSON object key")
        result[key] = value
    return result


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number: {value}")
    return parsed


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _validate_track1_release_csv(data: bytes) -> list[str]:
    try:
        predictions = load_predictions_bytes(data)
    except (OSError, SubmissionError) as exc:
        return [f"Track 1 schema validation failed ({exc})"]
    if len(predictions) != 1:
        return ["Track 1 release must contain exactly one candidate row"]
    prediction = predictions[0]
    if len(prediction.variants) != 2:
        return ["Track 1 release row must contain exactly one variant pair"]
    if prediction.finding_type != "primary":
        return ["Track 1 release row must be a primary finding"]
    return []


def _validate_track1_release_report(data: bytes) -> list[str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return ["Track 1 report must not contain a UTF-8 BOM"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["Track 1 report must be strict UTF-8 Markdown"]
    if not text.strip():
        return ["Track 1 report must not be empty"]
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        return ["Track 1 report contains a disallowed control character"]
    if re.search(
        r"<!--\s*(?:[A-Z][A-Z0-9]*_)+[A-Z0-9]+\s*-->|"
        r"(?i:\b(?:TODO|TBD|PLACEHOLDER)\b)",
        text,
    ):
        return ["Track 1 report contains an unresolved placeholder marker"]
    return []


def _validate_track2_release_report(data: bytes) -> list[str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return ["Track 2 report must not contain a UTF-8 BOM"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["Track 2 report must be strict UTF-8 Markdown"]
    if not text.strip():
        return ["Track 2 report must not be empty"]
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        return ["Track 2 report contains a disallowed control character"]
    if re.search(
        r"<!--\s*(?:[A-Z][A-Z0-9]*_)+[A-Z0-9]+\s*-->|"
        r"(?i:\b(?:TODO|TBD|PLACEHOLDER)\b)",
        text,
    ):
        return ["Track 2 report contains an unresolved placeholder marker"]
    required_sections = (
        r"(?m)^## Executive decision\s*$",
        r"(?m)^## (?:\d+\. )?Falsification and decision table\s*$",
        r"(?m)^## (?:\d+\. )?Limitations\s*$",
        r"(?m)^## References\s*$",
    )
    if any(re.search(pattern, text) is None for pattern in required_sections):
        return ["Track 2 report is missing one or more required sections"]
    return []


def _validate_track2_pitch_script(data: bytes) -> list[str]:
    issues = _validate_track2_release_report(data)
    if issues and "missing one or more required sections" not in issues[0]:
        return issues
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["Track 2 pitch must be strict UTF-8 Markdown"]
    required_markers = (
        "# Three-minute Track 2 pitch",
        "**Target runtime:**",
        "**Claim boundary:**",
        "## 0:00–0:22",
        "## 2:31–2:58",
    )
    if any(marker not in text for marker in required_markers):
        return ["Track 2 pitch is missing the frozen runtime or claim boundary"]
    return []


def _ledger_payload_has_promotion(data: bytes) -> bool:
    """Sniff whether ledger bytes carry a promotion; parse failures defer to
    the strict validator, which reports the real error."""

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return True
    if not isinstance(value, dict):
        return True
    entries = value.get("entries")
    if not isinstance(entries, list):
        return True
    return any(
        isinstance(entry, dict)
        and entry.get("sample_stewardship_promotion") is not None
        for entry in entries
    )


def _validate_candidate_release_ledger(
    data: bytes,
    sample_plan: Mapping[str, object] | None = None,
) -> list[str]:
    try:
        validate_candidate_release_ledger_bytes(
            data,
            sample_plan=sample_plan if _ledger_payload_has_promotion(data) else None,
        )
    except CandidateLedgerError as exc:
        return [f"candidate release ledger failed ({exc})"]
    return []


def _validate_candidate_report_digest_bindings(
    report_data: bytes,
    expected_digests: dict[str, str] | None,
) -> list[str]:
    """Bind a released Track 2 narrative to the exact released candidate pair."""

    try:
        text = report_data.decode("utf-8")
    except UnicodeDecodeError:
        return ["Track 2 report candidate digest bindings require strict UTF-8"]

    observed: dict[str, str] = {}
    issues: list[str] = []
    for role, pattern in CANDIDATE_REPORT_DIGEST_PATTERNS.items():
        matches = pattern.findall(text)
        if len(matches) > 1:
            issues.append(f"Track 2 report repeats the {role} digest binding")
        elif matches:
            observed[role] = matches[0]

    if expected_digests is None:
        if observed:
            issues.append(
                "Track 2 report declares candidate digests while the candidate pair is not released"
            )
        return issues

    for role, expected in expected_digests.items():
        actual = observed.get(role)
        if actual is None:
            issues.append(f"Track 2 report is missing the {role} digest binding")
        elif actual != expected:
            issues.append(f"Track 2 report has a stale {role} digest binding")
    return issues


RELEASE_ROLE_VALIDATORS: dict[str, Callable[[bytes], list[str]]] = {
    "track1_submission_csv": _validate_track1_release_csv,
    "track1_methods_report": _validate_track1_release_report,
    "track2_repositioning_report": _validate_track2_release_report,
    "track2_pitch_script": _validate_track2_pitch_script,
    "track2_reproducibility_manifest": lambda _data: [],
    "track2_candidate_ranking_receipt": lambda _data: [],
}
RELEASE_BIOLOGY_ROLES = frozenset(
    {
        "track1_submission_csv",
        "track1_methods_report",
        "track2_repositioning_report",
        "track2_pitch_script",
        "track2_candidate_evidence_ledger",
        "track2_candidate_ranking_receipt",
    }
)


def _validate_release_manifest(
    manifest_data: bytes | None,
    load_artifact: Callable[[PurePosixPath], bytes | None],
    source: str,
    sample_plan: Mapping[str, object] | None = None,
    *,
    deep_manifest_validation: bool = True,
) -> tuple[dict[PurePosixPath, ReleaseAllowance], list[str]]:
    """Return digest-bound release allowances, or none if any declaration is invalid."""

    details: list[str] = []
    if manifest_data is None:
        if any(load_artifact(path) is not None for path in RELEASE_ARTIFACT_PATHS.values()):
            details.append("fixed release artifact exists without the required manifest")
    elif len(manifest_data) > MAX_PUBLIC_BYTES:
        details.append("manifest exceeds the public size limit")
    elif manifest_data.startswith(b"\xef\xbb\xbf"):
        details.append("manifest must not contain a UTF-8 BOM")
    else:
        try:
            manifest_text = manifest_data.decode("utf-8")
            manifest = json.loads(
                manifest_text,
                object_pairs_hook=_strict_json_object,
                parse_constant=_reject_json_constant,
                parse_float=_finite_json_float,
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            details.append("manifest is not strict duplicate-free UTF-8 JSON")
        else:
            if not isinstance(manifest, dict):
                details.append("manifest root must be an object")
            elif set(manifest) != RELEASE_MANIFEST_TOP_LEVEL_KEYS:
                details.append("manifest root has missing or surplus keys")
            elif manifest.get("schema") not in RELEASE_MANIFEST_SCHEMA_ARTIFACT_PATHS:
                details.append("manifest schema is not the supported fixed version")
            elif not isinstance(manifest.get("artifacts"), list):
                details.append("manifest artifacts must be a list")
            else:
                schema_artifact_paths = RELEASE_MANIFEST_SCHEMA_ARTIFACT_PATHS[
                    manifest["schema"]
                ]
                inactive_fixed_paths = (
                    set(RELEASE_ARTIFACT_PATHS.values())
                    - set(schema_artifact_paths.values())
                )
                for inactive_path in sorted(
                    inactive_fixed_paths,
                    key=lambda path: path.as_posix(),
                ):
                    if load_artifact(inactive_path) is not None:
                        details.append(
                            "fixed artifact exists but is not declared by the active manifest schema: "
                            + inactive_path.as_posix()
                        )
                artifacts = manifest["artifacts"]
                if len(artifacts) != len(schema_artifact_paths):
                    details.append("manifest must declare exactly the fixed release artifacts")

                seen_roles: set[str] = set()
                seen_paths: set[str] = set()
                role_statuses: dict[str, str] = {}
                provisional: dict[PurePosixPath, ReleaseAllowance] = {}
                digest_checked_artifacts: dict[str, bytes] = {}
                for index, entry in enumerate(artifacts, start=1):
                    label = f"artifact {index}"
                    if not isinstance(entry, dict):
                        details.append(f"{label} must be an object")
                        continue
                    if set(entry) != RELEASE_MANIFEST_ARTIFACT_KEYS:
                        details.append(f"{label} has missing or surplus keys")
                        continue

                    role = entry.get("role")
                    path_text = entry.get("path")
                    status = entry.get("status")
                    digest = entry.get("sha256")
                    if not isinstance(role, str) or role not in schema_artifact_paths:
                        details.append(f"{label} has an unknown release role")
                        continue
                    if role in seen_roles:
                        details.append(f"{label} duplicates a release role")
                    seen_roles.add(role)

                    expected_path = schema_artifact_paths[role]
                    if not isinstance(path_text, str) or path_text != expected_path.as_posix():
                        details.append(f"{label} does not use the role's fixed path and extension")
                        continue
                    if path_text in seen_paths:
                        details.append(f"{label} duplicates a release path")
                    seen_paths.add(path_text)

                    if status not in {"planned", "released"}:
                        details.append(f"{label} status must be planned or released")
                        continue
                    role_statuses[role] = status
                    if status == "planned":
                        if digest is not None:
                            details.append(f"{label} planned state must use a null digest")
                        elif load_artifact(expected_path) is not None:
                            details.append(
                                f"{label} planned artifact exists but is not digest-bound for release"
                            )
                        continue
                    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
                        details.append(f"{label} released state requires a lowercase SHA-256")
                        continue

                    artifact_data = load_artifact(expected_path)
                    if artifact_data is None:
                        details.append(f"{label} released artifact is missing or unreadable")
                        continue
                    if len(artifact_data) > MAX_PUBLIC_BYTES:
                        details.append(f"{label} released artifact exceeds the public size limit")
                        continue
                    if hashlib.sha256(artifact_data).hexdigest() != digest:
                        details.append(f"{label} digest does not match the exact artifact bytes")
                        continue
                    digest_checked_artifacts[role] = artifact_data
                    if role == "track2_reproducibility_manifest":
                        # Deep validation binds the *current* artifact-role
                        # map; historical manifests were minted under older
                        # role sets, so it runs only for working-tree/index
                        # passes. History keeps the digest binding itself as
                        # the evidence that this exact manifest existed.
                        validation_issues = (
                            validate_track2_reproducibility_manifest(
                                artifact_data,
                                load_artifact,
                            )
                            if deep_manifest_validation
                            else []
                        )
                    elif role == "track2_candidate_evidence_ledger":
                        validation_issues = _validate_candidate_release_ledger(
                            artifact_data,
                            sample_plan,
                        )
                    else:
                        validation_issues = RELEASE_ROLE_VALIDATORS[role](artifact_data)
                    if validation_issues:
                        details.extend(f"{label}: {issue}" for issue in validation_issues)
                        continue
                    provisional[expected_path] = ReleaseAllowance(
                        role=role,
                        sha256=digest,
                    )

                missing_roles = set(schema_artifact_paths) - seen_roles
                if missing_roles:
                    details.append("manifest is missing one or more fixed release roles")

                if manifest["schema"] == NEXT_RELEASE_MANIFEST_SCHEMA:
                    ledger_role = "track2_candidate_evidence_ledger"
                    ranking_role = "track2_candidate_ranking_receipt"
                    report_role = "track2_repositioning_report"
                    ledger_status = role_statuses.get(ledger_role)
                    ranking_status = role_statuses.get(ranking_role)
                    if ledger_status != ranking_status:
                        details.append(
                            "candidate ledger and ranking receipt must share one release status"
                        )
                    elif ledger_status == "released":
                        ledger_data = digest_checked_artifacts.get(ledger_role)
                        ranking_data = digest_checked_artifacts.get(ranking_role)
                        if ledger_data is not None and ranking_data is not None:
                            try:
                                validate_candidate_release_bundle_bytes(
                                    ledger_data,
                                    ranking_data,
                                    sample_plan=(
                                        sample_plan
                                        if _ledger_payload_has_promotion(ledger_data)
                                        else None
                                    ),
                                )
                            except CandidateLedgerError as exc:
                                details.append(
                                    f"candidate release bundle failed ({exc})"
                                )
                    if role_statuses.get(report_role) == "released":
                        report_data = digest_checked_artifacts.get(report_role)
                        if report_data is not None:
                            expected_digests = None
                            if ledger_status == ranking_status == "released":
                                ledger_data = digest_checked_artifacts.get(ledger_role)
                                ranking_data = digest_checked_artifacts.get(ranking_role)
                                if ledger_data is not None and ranking_data is not None:
                                    expected_digests = {
                                        ledger_role: hashlib.sha256(ledger_data).hexdigest(),
                                        ranking_role: hashlib.sha256(ranking_data).hexdigest(),
                                    }
                            details.extend(
                                _validate_candidate_report_digest_bindings(
                                    report_data,
                                    expected_digests,
                                )
                            )

    if details:
        prefix = f"release manifest violation: {source}: {RELEASE_MANIFEST_PATH.as_posix()}"
        return {}, [f"{prefix}: {detail}" for detail in details]
    if manifest_data is None:
        return {}, []
    return provisional, []


def _public_identifier_allowed(identifier: str, relative: PurePosixPath) -> bool:
    if identifier.startswith("SYN"):
        return True
    if identifier in PUBLIC_TECHNICAL_IDENTIFIER_ALLOWLIST:
        return True
    if identifier in PUBLIC_PATH_TECHNICAL_IDENTIFIER_ALLOWLIST.get(
        relative, frozenset()
    ):
        return True
    if re.fullmatch(r"(?:[A-Z0-9]-[A-Z0-9]){2,}", identifier):
        return True
    return len(identifier) <= 8 and set(identifier) <= set("ACGTN")


def _inspect_publication_text(
    relative: PurePosixPath,
    text: str,
    source: str,
    *,
    allow_released_biology: bool = False,
    view_label: str = "",
) -> list[str]:
    self_policy = relative in PUBLICATION_POLICY_PATH_ALLOWLIST
    self_receipt = relative in OPERATIONAL_RECEIPT_PATH_ALLOWLIST

    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}{view_label}"
    if not allow_released_biology:
        identifiers: set[str] = set()
        identifiers.update(QUOTED_UPPER_IDENTIFIER_PATTERN.findall(text))
        identifiers.update(GENE_LIKE_TOKEN_PATTERN.findall(text))
        for pattern in BIOLOGICAL_CONTEXT_PATTERNS:
            identifiers.update(pattern.findall(text))
        for identifier in sorted(identifiers):
            if self_policy and identifier in POLICY_SOURCE_SELF_TOKENS:
                continue
            if not _public_identifier_allowed(identifier, relative):
                issues.append(
                    f"non-synthetic biological identifier {identifier!r}: {prefix}"
                )

        for label, pattern in EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
            if label == "subject identifier":
                for match in pattern.finditer(text):
                    identifier = _SUBJECT_IDENTIFIER_PORTION.sub(
                        "", match.group(0)
                    )
                    # A role word asserting a real subject can only be
                    # discharged by the declared SYN namespace — technical
                    # tokens and shape exemptions must not turn a
                    # "subject <token>" assertion into an allowlisted one.
                    if not (
                        _public_identifier_allowed(match.group(0), relative)
                        or identifier.startswith("SYN")
                    ):
                        issues.append(f"{label}: {prefix}")
                        break
            elif pattern.search(text):
                issues.append(f"{label}: {prefix}")
    pattern_spans = _re_compile_spans(text) if self_policy else []
    for label, pattern in OPERATIONAL_RECEIPT_PATTERNS.items():
        if self_receipt and label in OPERATIONAL_RECEIPT_SELF_LABELS:
            continue
        if self_policy:
            if any(
                not _is_pattern_definition_site(text, match.start(), pattern_spans)
                for match in pattern.finditer(text)
            ):
                issues.append(f"{label}: {prefix}")
        elif pattern.search(text):
            issues.append(f"{label}: {prefix}")
    return issues


_PAYLOAD_MAX_DEPTH = 3

# Token shapes that explain a long base64-alphabet run without an embedded
# payload: alphabetic runs and UPPER_SNAKE constants (with ``=`` edges picked
# up by whitespace-compacted code merges), hex digests, kebab-case
# identifiers, and path/expression tokens with clean ``+``/``.``/``/``
# separators. A decode from one of these is entropy-random gibberish, so
# binary payload evidence is suppressed for them — but any predominantly
# printable decode is still scanned for identifiers.
_BASE64_BENIGN_TOKEN = re.compile(
    r"(?:[A-Za-z0-9_-]*[+./][A-Za-z0-9_-]*)+={0,3}"
    r"|={0,3}[A-Za-z]+={0,3}"
    r"|={0,3}[A-Z0-9_]+={0,3}"
    r"|[0-9a-fA-F]+={0,3}"
    r"|[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)+={0,3}"
    r"\Z"
)


def _unescape_text(text: str) -> str:
    """Decode consumer-layer escapes to a fixed point (bounded iterations).

    JSON ``\\uXXXX``, URL ``%XX``, and HTML entities all decode to ordinary
    text at read time, and each layer can wrap another — ``%2556`` decodes to
    ``%56`` which decodes to ``V``. Three passes cover double-encoded
    payloads; a fourth would only matter to deliberately deeper nesting.
    """

    out = text
    for _ in range(3):
        if "\\u" not in out and "%" not in out and "&" not in out:
            break
        decoded = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda match: chr(int(match.group(1), 16)),
            out,
        )
        decoded = urllib.parse.unquote(decoded)
        decoded = html.unescape(decoded)
        if decoded == out:
            break
        out = decoded
    return out


def _b64_decode_token(token: str) -> bytes | None:
    """Padding-tolerant base64 decode; None when the token is not base64."""

    core = token.strip("=").translate(str.maketrans("-_", "+/"))
    if not core:
        return None
    core += "=" * (-len(core) % 4)
    try:
        return base64.b64decode(core, validate=True)
    except ValueError:
        return None


def _printable_fraction(decoded: bytes) -> float:
    if not decoded:
        return 0.0
    printable = sum(
        1 for byte in decoded if 0x20 <= byte <= 0x7E or byte in (0x09, 0x0A, 0x0D)
    )
    return printable / len(decoded)


def _printable_payload_text(decoded: bytes) -> str | None:
    """Decode bytes to predominantly-printable text, or None.

    Valid UTF-8 is measured per character so non-ASCII text (``é``) does not
    masquerade as binary; invalid UTF-8 falls back to the ASCII byte count.
    """

    if not decoded or len(decoded) > MAX_PUBLIC_BYTES:
        return None
    try:
        text = decoded.decode("utf-8")
    except UnicodeDecodeError:
        if _printable_fraction(decoded) < 0.9:
            return None
        return decoded.decode("utf-8", errors="ignore")
    printable = sum(1 for char in text if char.isprintable() or char in "\t\n\r")
    if not text or printable / len(text) < 0.9:
        return None
    return text


def _has_magic_signature(decoded: bytes) -> bool:
    return any(
        signature in decoded
        for signature, _label in MAGIC_SIGNATURES
        if any(byte > 0x7E or byte < 0x09 for byte in signature)
    )


def _inspect_payload_text(
    relative: PurePosixPath,
    text: str,
    source: str,
    *,
    allow_released_biology: bool = False,
    view_label: str = "",
    _depth: int = 0,
) -> list[str]:
    """Full detector set for text payloads — file content, decoded base64
    runs, unescaped text, and Git commit/tag messages. Secrets,
    controlled-payload markers, and phenotype bundles apply here just as they
    do to raw file text; a released artifact's declared biology allowance
    extends to payloads embedded inside it. Decoded views recurse so a
    payload cannot hide one layer under another."""

    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}{view_label}"
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            issues.append(f"{label} pattern: {prefix}")
    for label, pattern in CONTROLLED_TEXT_PATTERNS.items():
        if pattern.search(text):
            issues.append(f"{label}: {prefix}")
    folded = _scan_fold(text)
    if len(set(HPO_PATTERN.findall(folded))) >= 3:
        issues.append(
            "possible subject phenotype bundle (3+ HPO terms): " + prefix
        )
    issues.extend(
        _inspect_publication_text(
            relative,
            folded,
            source,
            allow_released_biology=allow_released_biology,
            view_label=view_label,
        )
    )
    if _depth >= _PAYLOAD_MAX_DEPTH:
        return issues

    seen_tokens: set[str] = set()
    haystacks = [(text, False)]
    compact = re.sub(r"[\s,]+", "", text)
    if compact != text:
        haystacks.append((compact, True))
    for haystack, compacted in haystacks:
        for token in _BASE64_RUN.findall(haystack):
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            decoded = _b64_decode_token(token)
            if decoded is None or len(decoded) > MAX_PUBLIC_BYTES:
                continue
            payload_text = _printable_payload_text(decoded)
            if payload_text is not None:
                issues.extend(
                    _inspect_payload_text(
                        relative,
                        payload_text,
                        source,
                        allow_released_biology=allow_released_biology,
                        view_label=view_label + "(base64)",
                        _depth=_depth + 1,
                    )
                )
                continue
            # Binary-looking decode: readable runs inside still take the
            # precise-identifier pass, and the payload itself flags only when
            # the token lacks a benign source shape — constants, digests, and
            # path tokens decode to entropy-random gibberish by chance.
            run_labels: set[str] = set()
            for run in re.findall(rb"[ -~]{6,}", decoded):
                run_text = run.decode("ascii")
                for label, pattern in EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
                    if pattern.search(run_text):
                        run_labels.add(label)
            for label in sorted(run_labels):
                issues.append(f"base64-embedded {label}: {prefix}")
            if _BASE64_BENIGN_TOKEN.fullmatch(token):
                continue
            # The raw view keeps the \x00 and embedded-magic tripwires. The
            # compacted view glues prose/code words into fake tokens whose
            # decode is entropy-random — a two-byte magic appears mid-decode
            # by chance, so compacted evidence requires the decode to begin
            # with a magic signature or to carry NULs amid mostly-readable
            # text (a deliberate payload shape, not merge gibberish).
            if compacted:
                binary_hit = (
                    any(
                        decoded.startswith(signature)
                        for signature, _label in MAGIC_SIGNATURES
                    )
                    or (
                        b"\x00" in decoded
                        and _printable_fraction(decoded) >= 0.5
                    )
                )
            else:
                binary_hit = _has_magic_signature(decoded) or b"\x00" in decoded
            if binary_hit:
                issues.append(
                    "base64-embedded binary payload requiring offline review: "
                    + prefix
                )

    unescaped = _unescape_text(text)
    if unescaped != text:
        issues.extend(
            _inspect_payload_text(
                relative,
                unescaped,
                source,
                allow_released_biology=allow_released_biology,
                view_label=view_label + "(unescaped)",
                _depth=_depth + 1,
            )
        )
    return issues


def _inspect_path_identifiers(
    relative: PurePosixPath,
    source: str,
) -> list[str]:
    """Identifier shapes carried by the path itself. Content scanning never
    sees a file named ``brca1-summary.md`` or ``nm_accession.txt``; path type
    checks only cover suffixes and directory names, so every stem is folded
    and scanned like text."""

    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}"
    stems = [relative.stem] + [PurePosixPath(part).stem for part in relative.parts[:-1]]
    for stem in stems:
        folded = _scan_fold(_unescape_text(stem))
        identifiers = set(QUOTED_UPPER_IDENTIFIER_PATTERN.findall(folded))
        identifiers.update(GENE_LIKE_TOKEN_PATTERN.findall(folded))
        for pattern in BIOLOGICAL_CONTEXT_PATTERNS:
            identifiers.update(pattern.findall(folded))
        for identifier in sorted(identifiers):
            if not _public_identifier_allowed(identifier, relative):
                issues.append(
                    f"non-synthetic biological identifier {identifier!r} "
                    f"in path: {prefix}"
                )
        for label, pattern in EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
            if pattern.search(folded):
                issues.append(f"{label} in path: {prefix}")
    return issues


def _inspect_bytes(
    relative: PurePosixPath,
    data: bytes,
    source: str,
    *,
    release_allowance: ReleaseAllowance | None = None,
) -> list[str]:
    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}"
    path_problem = _path_issue(relative)
    if path_problem:
        issues.append(f"{path_problem}: {prefix}")

    if len(data) > MAX_PUBLIC_BYTES:
        issues.append(f"unexpected file larger than 10 MiB: {prefix}")
        return issues

    for signature, label in MAGIC_SIGNATURES:
        if data.startswith(signature):
            issues.append(f"{label}: {prefix}")
            return issues

    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff", b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data:
        issues.append(
            "non-UTF-8 encoded or binary content requiring offline review: "
            + prefix
        )
        return issues

    for signature, label in MAGIC_SIGNATURES:
        if any(byte > 0x7E or byte < 0x09 for byte in signature) and signature in data:
            issues.append(f"embedded {label} signature: {prefix}")
            return issues

    released_role: str | None = None
    if release_allowance is not None:
        observed_digest = hashlib.sha256(data).hexdigest()
        if observed_digest != release_allowance.sha256:
            issues.append(
                "digest-bound release artifact changed after manifest validation: "
                + prefix
            )
        else:
            released_role = release_allowance.role

    if released_role is None:
        issues.extend(_inspect_path_identifiers(relative, source))

    # A UTF-8 BOM must not defeat start-anchored payload-shape checks.
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        issues.append(
            "non-UTF-8 encoded or binary content requiring offline review: "
            + prefix
        )
        return issues
    issues.extend(
        _inspect_payload_text(
            relative,
            text,
            source,
            allow_released_biology=released_role in RELEASE_BIOLOGY_ROLES,
        )
    )
    return issues


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False,
    )


def _git_file(root: Path, revision_path: str) -> bytes | None:
    result = _git(root, "show", revision_path)
    return result.stdout if result.returncode == 0 else None


def _is_reparse_point(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _git_findings(
    root: Path,
    sample_plan: Mapping[str, object] | None = None,
) -> list[str]:
    if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return [
            "Git history unavailable inside a non-work-tree; reachable "
            "history cannot be verified"
        ]

    issues: list[str] = []

    def load_index_artifact(relative: PurePosixPath) -> bytes | None:
        return _git_file(root, f":{relative.as_posix()}")

    index_manifest = load_index_artifact(RELEASE_MANIFEST_PATH)
    index_allowances, index_manifest_issues = _validate_release_manifest(
        index_manifest,
        load_index_artifact,
        "Git index",
        sample_plan=sample_plan,
    )
    issues.extend(index_manifest_issues)

    indexed = _git(root, "ls-files", "--cached", "-z")
    if indexed.returncode != 0:
        issues.append("Git index enumeration failed; staged blobs cannot be verified")
    else:
        for raw_path in filter(None, indexed.stdout.split(b"\x00")):
            try:
                path_text = raw_path.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(
                    "non-UTF-8 path in Git index requiring offline review"
                )
                continue
            relative = PurePosixPath(path_text)
            size_result = _git(root, "cat-file", "-s", f":{path_text}")
            try:
                indexed_size = int(size_result.stdout.strip())
            except ValueError:
                indexed_size = -1
            if indexed_size > MAX_PUBLIC_BYTES:
                issues.append(f"unexpected file larger than 10 MiB: Git index: {relative.as_posix()}")
                path_problem = _path_issue(relative)
                if path_problem:
                    issues.append(f"{path_problem}: Git index: {relative.as_posix()}")
                continue
            blob_data = load_index_artifact(relative)
            if blob_data is None:
                continue
            issues.extend(
                _inspect_bytes(
                    relative,
                    blob_data,
                    "Git index",
                    release_allowance=index_allowances.get(relative),
                )
            )

    final_index_manifest = load_index_artifact(RELEASE_MANIFEST_PATH)
    final_index_allowances, final_index_manifest_issues = _validate_release_manifest(
        final_index_manifest,
        load_index_artifact,
        "Git index final snapshot",
        sample_plan=sample_plan,
    )
    issues.extend(final_index_manifest_issues)
    if (
        final_index_manifest != index_manifest
        or final_index_allowances != index_allowances
    ):
        issues.append("release manifest or released artifact changed during scan: Git index")

    log_messages = _git(root, "log", "--all", "--format=%B%x00")
    if log_messages.returncode == 0:
        for message in log_messages.stdout.split(b"\x00"):
            if not message:
                continue
            try:
                text = message.decode("utf-8").strip()
            except UnicodeDecodeError:
                issues.append(
                    "non-UTF-8 Git commit message requiring offline review"
                )
                continue
            if text:
                issues.extend(
                    _inspect_payload_text(
                        PurePosixPath("<git-commit-message>"),
                        text,
                        "Git history",
                    )
                )

    tag_contents = _git(
        root, "tag", "--list", "--format=%(refname:short)%00%(contents)"
    )
    if tag_contents.returncode == 0:
        for entry in tag_contents.stdout.split(b"\x00"):
            if not entry:
                continue
            try:
                text = entry.decode("utf-8").strip()
            except UnicodeDecodeError:
                issues.append(
                    "non-UTF-8 Git tag message requiring offline review"
                )
                continue
            if text:
                issues.extend(
                    _inspect_payload_text(
                        PurePosixPath("<git-tag-message>"),
                        text,
                        "Git history",
                    )
                )

    commits = _git(root, "rev-list", "--all")
    seen_history_blobs: set[tuple[str, str, str | None]] = set()
    if commits.returncode != 0:
        issues.append(
            "Git history enumeration failed; reachable history cannot be verified"
        )
    else:
        for raw_commit in filter(None, commits.stdout.splitlines()):
            commit = raw_commit.decode("ascii", errors="ignore")
            if not commit:
                continue

            def load_history_artifact(relative: PurePosixPath) -> bytes | None:
                return _git_file(root, f"{commit}:{relative.as_posix()}")

            history_manifest = load_history_artifact(RELEASE_MANIFEST_PATH)
            commit_allowances, commit_issues = _validate_release_manifest(
                history_manifest,
                load_history_artifact,
                f"Git history commit {commit[:12]}",
                sample_plan=sample_plan,
                deep_manifest_validation=False,
            )
            issues.extend(commit_issues)

            tree = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit)
            if tree.returncode != 0:
                issues.append(
                    f"Git history tree unreadable at commit {commit[:12]}; "
                    "reachable blobs cannot be verified"
                )
                continue
            for raw_entry in filter(None, tree.stdout.split(b"\x00")):
                fields = raw_entry.split(b"\t", 1)
                if len(fields) != 2:
                    continue
                metadata = fields[0].split()
                if len(metadata) != 3 or metadata[1] != b"blob":
                    continue
                object_id = metadata[2].decode("ascii", errors="ignore")
                try:
                    path_text = fields[1].decode("utf-8")
                except UnicodeDecodeError:
                    issues.append(
                        "non-UTF-8 path in Git history requiring offline review"
                    )
                    continue
                relative = PurePosixPath(path_text)
                allowance = commit_allowances.get(relative)
                path_object_role = (path_text, object_id, allowance)
                if path_object_role in seen_history_blobs:
                    continue
                seen_history_blobs.add(path_object_role)

                path_problem = _path_issue(relative)
                if path_problem:
                    issues.append(f"{path_problem}: Git history: {relative.as_posix()}")
                size_result = _git(root, "cat-file", "-s", object_id)
                try:
                    history_size = int(size_result.stdout.strip())
                except ValueError:
                    history_size = -1
                if history_size > MAX_PUBLIC_BYTES:
                    issues.append(
                        f"unexpected file larger than 10 MiB: Git history: {relative.as_posix()}"
                    )
                    continue
                blob = _git(root, "cat-file", "-p", object_id)
                if blob.returncode == 0:
                    issues.extend(
                        _inspect_bytes(
                            relative,
                            blob.stdout,
                            "Git history",
                            release_allowance=allowance,
                        )
                    )
    return issues


def findings(
    root: Path,
    *,
    include_git: bool = True,
    sample_plan: Mapping[str, object] | None = None,
) -> list[str]:
    issues: list[str] = []

    def load_working_artifact(relative: PurePosixPath) -> bytes | None:
        path = root.joinpath(*relative.parts)
        if not path.is_file() or _is_reparse_point(path):
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    working_manifest = load_working_artifact(RELEASE_MANIFEST_PATH)
    working_allowances, working_manifest_issues = _validate_release_manifest(
        working_manifest,
        load_working_artifact,
        "working tree",
        sample_plan=sample_plan,
    )
    issues.extend(working_manifest_issues)

    for directory, dirnames, filenames in os.walk(root):
        safe_dirs: list[str] = []
        for name in dirnames:
            candidate = Path(directory, name)
            candidate_relative = PurePosixPath(candidate.relative_to(root).as_posix())
            if (
                candidate_relative in NON_PUBLIC_ROOT_DIRECTORY_ALLOWLIST
                or name in GENERATED_DIRECTORY_NAME_ALLOWLIST
            ):
                continue
            if _is_reparse_point(candidate):
                relative = candidate.relative_to(root).as_posix()
                issues.append(f"symlink/junction/reparse directory: working tree: {relative}")
                continue
            safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for filename in filenames:
            path = Path(directory, filename)
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if _is_reparse_point(path):
                issues.append(
                    f"symlink/junction/reparse file: working tree: {relative.as_posix()}"
                )
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                issues.append(f"unreadable file: working tree: {relative.as_posix()} ({exc})")
                continue
            if size > MAX_PUBLIC_BYTES:
                issues.append(f"unexpected file larger than 10 MiB: working tree: {relative.as_posix()}")
                path_problem = _path_issue(relative)
                if path_problem:
                    issues.append(f"{path_problem}: working tree: {relative.as_posix()}")
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                issues.append(f"unreadable file: working tree: {relative.as_posix()} ({exc})")
                continue
            issues.extend(
                _inspect_bytes(
                    relative,
                    data,
                    "working tree",
                    release_allowance=working_allowances.get(relative),
                )
            )
    final_working_manifest = load_working_artifact(RELEASE_MANIFEST_PATH)
    final_working_allowances, final_working_manifest_issues = _validate_release_manifest(
        final_working_manifest,
        load_working_artifact,
        "working tree final snapshot",
        sample_plan=sample_plan,
    )
    issues.extend(final_working_manifest_issues)
    if (
        final_working_manifest != working_manifest
        or final_working_allowances != working_allowances
    ):
        issues.append("release manifest or released artifact changed during scan: working tree")
    if include_git:
        issues.extend(_git_findings(root, sample_plan=sample_plan))
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument(
        "--no-git", action="store_true",
        help="scan only files on disk (unsafe for pre-publication review)",
    )
    parser.add_argument(
        "--sample-plan",
        type=Path,
        help=(
            "strict local sample-stewardship plan required to validate a "
            "released candidate pair that carries a sample promotion; the "
            "plan is validated but never scanned or copied"
        ),
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        sample_plan = (
            None
            if args.sample_plan is None
            else load_sample_stewardship_plan(args.sample_plan)
        )
    except CandidateLedgerError as exc:
        parser.error(str(exc))
    issues = findings(
        root, include_git=not args.no_git, sample_plan=sample_plan
    )
    if issues:
        print("NO-GO: privacy gate failed")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("GO: privacy gate passed (working tree, Git index, and reachable history)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
