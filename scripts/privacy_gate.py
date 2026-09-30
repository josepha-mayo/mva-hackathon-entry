"""Fail closed when controlled data or credentials appear in a public tree.

The gate inspects the working tree, staged Git blobs that differ from disk, and
every reachable historical Git blob. It is deliberately conservative: opaque
archives and binary documents require an explicit offline review before they
can be added to the public repository.
"""

from __future__ import annotations

import argparse
import base64
import codecs
import hashlib
import html
import io
import json
import math
import os
import re
import stat
import subprocess
import sys
import tokenize
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
    ".dcm", ".dicom", ".fa", ".faa", ".fam", ".fasta", ".fastq",
    ".feather", ".ffn", ".fq", ".frn", ".fna", ".gvcf",
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
    # Distinctive prefixes run boundary-free: one glued word character must
    # not launder a recoverable credential (``xghp_…`` still contains the
    # whole token). ``sk-`` stays anchored — it collides with ordinary
    # hyphenated words too often.
    "Hugging Face token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "GitHub token": re.compile(r"gh[opsu]_[A-Za-z0-9_]{20,}\b"),
    "AWS access-key id": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
CONTROLLED_TEXT_PATTERNS = {
    "VCF payload marker": re.compile(r"(?m)^##fileformat=VCFv"),
    "SAM payload marker": re.compile(r"(?m)^@(?:HD|SQ|RG|PG)[\t ]"),
    "FASTQ payload shape": re.compile(
        r"(?m)^@[^\r\n]+\r?\n[ACGTNacgtn]+\r?\n\+[^\r\n]*\r?\n[!-~]+\r?\n"
    ),
    "FASTA payload shape": re.compile(
        r"(?m)^>[^\r\n]*\r?\n(?:[ACGTUNacgtun]{20,}|[ACGTUNacgtun ]{20,})\r?\n"
    ),
    "uuencode payload marker": re.compile(r"(?m)^begin\s+\d{3}\s+\S+"),
    "Git LFS pointer": re.compile(
        r"\Aversion https://git-lfs\.github\.com/spec/v1\r?\noid sha256:[0-9a-f]{64}\r?\n"
    ),
}
HPO_PATTERN = re.compile(r"HP[\s:_-]+\d{7}\b", re.IGNORECASE)

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
        "A0", "A1", "A-Z0", "A-Z0-", "A9-0", "ALPHA", "ARMS", "B10", "B11",
        "B12", "B13", "B14", "BAM", "BCF", "BLE001", "BUB1B", "BUB1B-",
        "BUBR1", "CEBONAQ01", "CLASSIFICATIONS", "COMMANDS", "CRAM", "E402",
        "FV8", "SI8", "QC9",
        "END", "ENDMDL", "ESTIMANDS", "G418", "GO", "GPT-5", "HMAC-SHA256",
        "L737", "METHODS", "MITOCHONDRIAL", "MVA", "N1002K", "NFD", "NFKC",
        "NO-GO", "OXT", "PARTITIONS", "PATH", "PK", "PMC7610696", "PPS",
        "PRIORITIES", "PYTHONPATH", "R32", "R40", "R42", "R43", "R44",
        "RCV", "REPLICATION", "ROLES", "SCHEMA", "SCV", "SEED", "SHA-256-",
        "SP0", "STAGES", "STATUSES", "STRENGTHS", "SWE-2", "TER", "TG487",
        "UTF-16LE", "UTF-32LE", "EL23-FTU", "OHO1O", "AZ271606",
        "NM271606", "VCV", "Z0-9", "omim600123",
    }
)
# Receipt labels the operational preflight source legitimately contains in its
# own command strings. Other receipt-phrase labels still apply to that file.
OPERATIONAL_RECEIPT_SELF_LABELS = frozenset(
    {"machine/storage receipt", "machine-local absolute path"}
)


def _re_compile_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets covered by each re.compile(...) call.

    Parentheses are matched on a string/comment-masked view — a ``)`` inside
    a pattern literal cannot end the call early, and an unbalanced ``(``
    inside one cannot stretch the call over an adjacent planted literal.
    """

    try:
        maskable = [
            token
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type in (tokenize.STRING, tokenize.COMMENT)
        ]
    except (tokenize.TokenError, SyntaxError, ValueError, IndentationError):
        return []
    masked = list(text)
    line_starts = [0]
    for newline in re.finditer(r"\n", text):
        line_starts.append(newline.end())
    for token in maskable:
        start = line_starts[token.start[0] - 1] + token.start[1]
        end = line_starts[token.end[0] - 1] + token.end[1]
        keep = "'\"\n" if token.type == tokenize.STRING else "\n"
        for index in range(start, end):
            if masked[index] not in keep:
                masked[index] = " "
    masked_text = "".join(masked)
    spans: list[tuple[int, int]] = []
    for match in re.finditer(
        r"re\.(?:compile|search|match|fullmatch|sub|finditer|findall|split)\(",
        masked_text,
    ):
        depth = 0
        index = match.end() - 1
        while index < len(masked_text):
            char = masked_text[index]
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

_SCAN_STRIP_CATEGORIES = frozenset({"Cf", "Cc", "Mn", "Me", "Cs", "Co", "Cn"})
_SCAN_CONFUSABLES = {
    **_CLAIM_CONFUSABLES,
    **{
        ord(chr(codepoint).upper()): value.upper()
        for codepoint, value in _CLAIM_CONFUSABLES.items()
    },
    # Additional lookalikes NFKC does not fold: lunate sigma, Greek omega
    # form, and Cherokee/Canadian-syllabics letters commonly used for
    # identifier lookalike attacks.
    ord("Ϲ"): "C", ord("ϲ"): "c", ord("Ѵ"): "V", ord("ѵ"): "v",
    ord("Ꭰ"): "D", ord("Ꮯ"): "C", ord("Ꮋ"): "H", ord("Ꮪ"): "S",
    ord("Ꭲ"): "T", ord("Ꮎ"): "N", ord("Ꮐ"): "G", ord("Ꮲ"): "P",
    ord("Ꮩ"): "V", ord("Ꮤ"): "T", ord("Ꮹ"): "W", ord("Ꮽ"): "W",
    ord("Ꮝ"): "S", ord("Ꭺ"): "A", ord("Ꮇ"): "M", ord("Ꭵ"): "V",
    ord("Ᏹ"): "Y", ord("Ꭹ"): "G", ord("Ꮮ"): "L", ord("Ꭴ"): "U",
    ord("Ꮓ"): "N", ord("Ꮠ"): "O", ord("Ꮭ"): "C", ord("Ꮿ"): "Y",
    ord("Ꮢ"): "R", ord("Ꮡ"): "T", ord("Ꮥ"): "H", ord("Ꮘ"): "P",
    ord("ᐯ"): "V", ord("ᑕ"): "T", ord("ᗷ"): "B", ord("ᗩ"): "A",
    ord("ᗪ"): "D", ord("ᗴ"): "E", ord("ᑎ"): "N", ord("ᗰ"): "M",
    ord("ᗩ"): "A", ord("ᖇ"): "R", ord("ᗯ"): "W", ord("ᑌ"): "U",
}
# Alphabetic blocks documented as confusable sources whose lookalikes the
# map above cannot exhaustively cover — Lisu, Deseret, Old Italic, and
# siblings. A folded character still inside one of these ranges was never
# mapped, and an English computational corpus has no legitimate use for
# any of them, so presence alone is evidence.
_EXOTIC_LOOKALIKE_RANGES = (
    (0x10400, 0x1044F),  # Deseret
    (0x10480, 0x104AF),  # Osmanya
    (0x10530, 0x1056F),  # Caucasian Albanian
    (0x10280, 0x1029F),  # Lycian
    (0x102A0, 0x102DF),  # Carian
    (0x10300, 0x1032F),  # Old Italic
    (0x10330, 0x1034F),  # Gothic
    (0x10350, 0x1037F),  # Old Permic
    (0x10380, 0x1039F),  # Ugaritic
    (0x10800, 0x1083F),  # Cypriot/Imperial Aramaic region
    (0x10900, 0x1091F),  # Phoenician
    (0x16A0, 0x16FF),    # Runic
    (0x1680, 0x169F),    # Ogham
    (0x1800, 0x18AF),    # Mongolian
    (0x1BC0, 0x1BFF),    # Batak
    (0x2C00, 0x2C5F),    # Glagolitic
    (0x2D30, 0x2D7F),    # Tifinagh
    (0xA500, 0xA63F),    # Vai
    (0xA6A0, 0xA6FF),    # Bamum
    (0xA900, 0xA92F),    # Kayah Li
    (0xA930, 0xA95F),    # Rejang
    (0xA4D0, 0xA4FF),    # Lisu
    (0x13A0, 0x13FF),    # Cherokee (unmapped members)
    (0xAB70, 0xABBF),    # Cherokee supplement
    (0x1400, 0x167F),    # Canadian syllabics (unmapped members)
)


def _exotic_lookalike(text: str) -> str | None:
    """First character sitting inside a lookalike-script block, or None.

    The check only runs on word-dominated text: a real lookalike attack
    embeds the exotic letter inside readable words, while a random carrier
    decode surfaces isolated block members inside symbol soup that no
    reader could mistake for an identifier."""

    non_space = [char for char in text if not char.isspace()]
    if not non_space:
        return None
    if sum(char.isalnum() for char in non_space) / len(non_space) < 0.6:
        return None
    for char in text:
        codepoint = ord(char)
        for lo, hi in _EXOTIC_LOOKALIKE_RANGES:
            if lo <= codepoint <= hi:
                return char
    return None
# Sixteen base64 characters is the floor: shorter runs can only carry an
# eleven-byte payload, below every accession shape the detectors check.
# Shorter runs still get an identifiers-only decode pass — a random six-byte
# decode cannot spell a real accession, so exact-pattern hits are decisive.
_BASE64_RUN = re.compile(
    r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/=_-]{16,}={0,2}(?![A-Za-z0-9+/=_-])"
)
_BASE64_SHORT_RUN = re.compile(
    r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/=_-]{8,15}={0,2}(?![A-Za-z0-9+/=_-])"
)
# A payload split by punctuation stays recoverable: fragments under the run
# floor join back into a whole token. Short runs of non-whitespace
# separators are tolerated between fragments (whitespace-joined fragments
# are already reassembled by the compacted view); the joined token must
# still reach the carrier floor before it is decoded.
_BASE64_SPLIT_RUN = re.compile(
    r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/=_-]{2,}"
    r"(?:[^A-Za-z0-9+/=_\s-]{1,8}[A-Za-z0-9+/=_-]{2,}){1,40}"
    r"(?![A-Za-z0-9+/=_-])"
)
# Hex fragments split by a non-hex separator reassemble the same way —
# ``5643.3035`` joins to a decodable byte run.
_HEX_SPLIT_RUN = re.compile(
    r"(?<![0-9a-fA-F])[0-9a-fA-F]{4,}"
    r"(?:[^0-9a-fA-F\s]{1,4}[0-9a-fA-F]{4,}){1,12}"
    r"(?![0-9a-fA-F])"
)
# A uuencode body stripped of its ``begin``/``end`` markers is a run of
# length-prefixed lines starting ``M`` — three or more consecutive ones
# are unambiguous.
_UUENCODE_BODY_RUN = re.compile(r"(?m)(?:^M[!-~]{20,61}\s*\r?\n){3,}")
# Other common carrier alphabets. Hex needs 24 chars (12 bytes); base32 uses
# the RFC 4648 alphabet with padding. ``=`` is not a boundary blocker: an
# INI-style ``key=<payload>`` must still surface the token.
_HEX_RUN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{24,}(?![0-9a-fA-F])")
_HEX_SHORT_RUN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{16,23}(?![0-9a-fA-F])")
_BASE32_RUN = re.compile(r"(?<![A-Z2-7])[A-Z2-7]{16,}={0,6}(?![A-Z2-7=])")
_BASE32_SHORT_RUN = re.compile(r"(?<![A-Z2-7])[A-Z2-7]{10,15}={0,6}(?![A-Z2-7=])")
# RFC 4648 base32hex alphabet (0-9A-V) and lowercase base32 are tried as
# variants of any uppercase-token candidate.
_BASE32HEX_RUN = re.compile(r"(?<![0-9A-V])[0-9A-V]{16,}={0,6}(?![0-9A-V=])")
# Ascii85/base85 runs lean on punctuation, so word-shaped tokens cannot be
# the only candidates — a contiguous alphabet run of 10+ is attempted, and
# only a decode that yields scannable content is reported (never flagged
# merely for failing).
_BASE85_RUN = re.compile(
    r"(?<![A-Za-z0-9!#$%&()*+\-;<=>?@^_`{|}~])"
    r"[A-Za-z0-9!#$%&()*+\-;<=>?@^_`{|}~]{10,}"
    r"(?![A-Za-z0-9!#$%&()*+\-;<=>?@^_`{|}~])"
)
# Uuencode blocks open with ``begin <mode> <name>`` and carry length-prefixed
# lines; the marker itself is the detection surface.
_UUENCODE_BLOCK = re.compile(
    r"begin\s+\d{3}\s+\S+\s*\n((?:[!-`]{1,61}\s*\n)+)"
)
# Base58 tokens (no 0/O/I/l alphabet) are rare in prose; a standalone
# medium-length run earns a decode attempt.
_BASE58_RUN = re.compile(
    r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{12,}(?![A-Za-z0-9])"
)
# Carrier chunk sizes for alignment retry: a merged-prose prefix realigns a
# payload at one of these offsets.
_CARRIER_ALIGNMENT = {"base64": 4, "hex": 2, "base32": 8}
# Weak binary evidence (NUL bytes, near-text decodes) is meaningful only
# for the carriers anyone actually hides bytes in. The base85/base58
# alphabets include ``(){}|`` and friends, so ordinary code tokens decode
# to ~50%-printable gibberish under them at coin-flip rates; those carriers
# get strict signatures and the embedded-identifier pass only.
_WEAK_EVIDENCE_CARRIERS = frozenset(
    {"base64", "hex", "base32", "base32hex", "base32lower", "uuencode"}
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
        "BOM", "BWA-MEM2", "Draft202012Validator", "GRCh37", "GRCh38", "HG19", "HG38", "CC-BY-4", "CC0-1", "COPY", "GT", "HEAD", "NAPRT", "SIRT2",
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
    PurePosixPath("scripts/run_seed_sensitivity.py"): frozenset({"E402"}),
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
    # The gate source names the artifact tokens it declares for other
    # paths — the same declarations apply here.
    PurePosixPath("scripts/privacy_gate.py"): frozenset(
        {"sample-v17", "gated5-sample-v17"}
    ),
    PurePosixPath("reports/TRACK2_ATTEMPT2_DELTA.md"): frozenset(
        {
            "HMAC-SHA256", "PYTHONPATH", "SHA-256-",
            "sample-v17", "gated5-sample-v17",
        }
    ),
    PurePosixPath("reports/TRACK2_METHOD_IMPROVEMENTS.md"): frozenset(
        {
            "BAM", "HMAC-SHA256", "PATH", "PYTHONPATH",
            "sample-v17", "gated5-sample-v17",
        }
    ),
    PurePosixPath("reports/TRACK2_RANDOMIZATION_CONTRACT.md"): frozenset(
        {"HMAC-SHA256", "PMC7610696"}
    ),
    PurePosixPath("COMPETITION_CONTRACT.md"): frozenset({"GPT-5", "SWE-2"}),
    PurePosixPath("reports/TRACK2_AI_LINE.md"): frozenset(
        {"GPT-5", "SWE-2", "sample-v17", "gated5-sample-v17"}
    ),
    PurePosixPath("reports/TRACK2_PROGRAM_GATES.md"): frozenset({"N1002K"}),
    PurePosixPath("reports/TRACK2_JUDGE_PACKAGE.md"): frozenset(
        {"BUB1B", "BUBR1"}
    ),
    PurePosixPath("README.md"): frozenset({"BUB1B", "BUB1B-"}),
    PurePosixPath("reports/TRACK2_SESSION_HANDOFF.md"): frozenset(
        {
            "B10", "B11", "B12", "B13", "B14", "BAM",
            "G418", "GPT-5", "L737", "MITOCHONDRIAL", "N1002K",
            "PATH", "PYTHONPATH",
            "R32", "R40", "R42", "R43", "R44", "TG487",
            # The gated5-sample-v17 package receipt is a named checkpoint
            # artifact, not a subject row.
            "sample-v17", "gated5-sample-v17",
        }
    ),
    PurePosixPath("reports/TRACK2_EXPOSURE_GATE.md"): frozenset({"G418"}),
    PurePosixPath("tests/test_exposure_gate.py"): frozenset({"G418"}),
    PurePosixPath("reports/PHASE2_SCALE_PLAN.md"): frozenset(
        {"GPT-5", "v17"}
    ),
    # The gate's own test file documents a synthetic accession fixture —
    # historical revisions wrote it inline, current revisions build it by
    # concatenation precisely so the literal never sits in source.
    PurePosixPath("tests/test_privacy_gate.py"): frozenset(
        {"omim" + "600123"}
    ),
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
    # The machine-generated benchmark receipt's JSON key/hash runs decode
    # under ascii85 to these gene-shaped tokens; rot13 shadows one of them.
    # The tokens exist only in the decoded-carrier view of this file.
    PurePosixPath("reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json"): frozenset(
        {"FV8", "SI8", "SP0"}
    ),
    # The Ed25519 detached-signature base64 payload reverses to a gene-shaped
    # token; the token exists only in the reversed view of this file.
    PurePosixPath("attestation/release-signature.asc"): frozenset({"QC9"}),
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
    "dbSNP-like identifier": re.compile(
        r"\brs(?:[\s\-_.:;,/#]*\d){3,}[a-z]*\b", re.IGNORECASE
    ),
    "ClinVar accession": re.compile(
        r"\b(?:VCV|RCV|SCV)(?:[\s\-_.:;,/#]*\d){6,}(?:\.\d+)?[a-z]*\b",
        re.IGNORECASE,
    ),
    # Bare role + code forms need an explicit id-marker, a real separator,
    # or a 2+ digit code — short codes like "participant A1" are the
    # declared material vocabulary, not identifiers. Quoting or assignment
    # punctuation (quotes, ``=``, ``;``, parentheses, Unicode dashes) counts
    # as a real separator, so a quoted or id-marker-assigned short code
    # still flags. The separator class is ``[^\w]`` — commas, emoji,
    # brackets, and exotic symbols all separate a role word from its code.
    # A leading ``-``/word char before the role is refused so CLI flags
    # and glued words do not fire, while hyphens *inside* the role word
    # itself are tolerated.
    "subject identifier": re.compile(
        r"(?i)(?<!\w)(?:p[-_.]?r[-_.]?o[-_.]?b[-_.]?a[-_.]?n[-_.]?d|"
        r"s[-_.]?u[-_.]?b[-_.]?j[-_.]?e[-_.]?c[-_.]?t|"
        r"d[-_.]?o[-_.]?n[-_.]?o[-_.]?r|"
        r"p[-_.]?a[-_.]?r[-_.]?t[-_.]?i[-_.]?c[-_.]?i[-_.]?p[-_.]?a[-_.]?n[-_.]?t|"
        r"p[-_.]?a[-_.]?t[-_.]?i[-_.]?e[-_.]?n[-_.]?t|"
        r"i[-_.]?n[-_.]?d[-_.]?i[-_.]?v[-_.]?i[-_.]?d[-_.]?u[-_.]?a[-_.]?l|"
        r"s[-_.]?p[-_.]?e[-_.]?c[-_.]?i[-_.]?m[-_.]?e[-_.]?n|"
        r"e[-_.]?n[-_.]?r[-_.]?o[-_.]?l[-_.]?l[-_.]?e[-_.]?e|"
        r"v[-_.]?o[-_.]?l[-_.]?u[-_.]?n[-_.]?t[-_.]?e[-_.]?e[-_.]?r|"
        r"t[-_.]?w[-_.]?i[-_.]?n|"
        r"s[-_.]?a[-_.]?m[-_.]?p[-_.]?l[-_.]?e|m[-_.]?o[-_.]?t[-_.]?h[-_.]?e[-_.]?r|"
        r"c[-_.]?h[-_.]?i[-_.]?l[-_.]?d)"
        r"s?(?:'s)?"
        r"[^\w]*"
        r"(?:"
        r"(?:id|no|num(?:ber)?|#)[^\w]*"
        r"[A-Za-z]{0,20}[-_.:/#\s]*\d[A-Za-z0-9\-_.:/#]*"
        r"|[^\w\s][^\w]*"
        r"[A-Za-z]{0,20}[-_.:/#\s]*\d[A-Za-z0-9\-_.:/#]*"
        r"|[A-Za-z]{0,20}\d{2,}[A-Za-z0-9-]*"
        r"|[A-Za-z]{1,20}[-_.:/#]+\d[A-Za-z0-9-]*"
        # ``_`` is a word character — the ``[^\w]*`` separator class never
        # crosses it, so a role word joined to its code by an underscore
        # needs the underscore folded into the code alternative itself.
        # The letter gap after ``_`` stays short: an identifier like a
        # ``size`` field is a variable name, while ``id``-style letter
        # prefixes followed by digits are subject assertions.
        r"|_[A-Za-z]{0,2}_?\d{2,}[A-Za-z0-9]*"
        r"|(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}"
        r")\b"
    ),
    # ``chr``-prefixed coordinates may carry separator-grouped digits; a
    # bare ``N:M`` needs five contiguous digits — file:line citations
    # (``file.py:772-951``) and reversed timestamps never reach that shape.
    "genomic coordinate": re.compile(
        r"\bchr(?:[1-9]|1\d|2[0-2]|X|Y|M|MT)\s*:(?:[\s\-_.;,/]*\d){4,}[a-z]*\b"
        r"|\b(?:[1-9]|1\d|2[0-2]|X|Y|M|MT)\s*:\s*\d{5,}[a-z]*\b",
        re.IGNORECASE,
    ),
    "RefSeq/Ensembl accession": re.compile(
        r"\b(?:N[MRXCGPW]_|X[MR]_|ENST|ENSP|ENSG)(?:[\s\-_.:;,/#]*\d){6,}(?:\.\d+)?[a-z]*\b",
        re.IGNORECASE,
    ),
    "HGNC/OMIM accession": re.compile(
        r"\b(?:HGNC|OMIM|MIM)[:#]?(?:[\s\-_.:;,/]*\d){4,}[a-z]*\b",
        re.IGNORECASE,
    ),
}
# Boundary-free strict-literal prefixes. These run on EVERY view — a word
# character glued to an accession defeats \b-anchored patterns in raw,
# decoded, and unescaped text alike, so the accession prefixes that cannot
# occur inside ordinary prose get no boundary requirement. ``rs``/``p.``
# shapes still stay off: they merge into ordinary words too often.
GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS = {
    "ClinVar accession": re.compile(
        r"(?:VCV|RCV|SCV)(?:[\s\-_.:;,/#]*\d){6,}(?:\.\d+)?", re.IGNORECASE
    ),
    "RefSeq/Ensembl accession": re.compile(
        r"(?:N[MRXCGPW]_|X[MR]_|ENST|ENSP|ENSG)(?:[\s\-_.:;,/#]*\d){6,}(?:\.\d+)?",
        re.IGNORECASE,
    ),
    "HGNC/OMIM accession": re.compile(
        r"(?:HGNC|OMIM|MIM)[:#](?:[\s\-_.;,/]*\d){4,}", re.IGNORECASE
    ),
    # A bare ``N:M`` coordinate needs no ``chr`` prefix to be suspicious —
    # one glued letter must not hide it. Bare hits require five contiguous
    # digits: separator-joined runs collide with file:line citations and
    # reversed datetimes, which a ``chr`` prefix never produces. A digit
    # immediately before the chromosome digit means the match is the tail
    # of a longer number (``sha256:1111…`` → ``6:1111…``), not a planted
    # coordinate.
    "genomic coordinate": re.compile(
        r"chr(?:[1-9]|1\d|2[0-2]|X|Y|M|MT)\s*:(?:[\s\-_.;,/]*\d){4,}"
        r"|(?<!\d)(?:[1-9]|1\d|2[0-2]|X|Y|M|MT)\s*:\s*\d{5,}",
        re.IGNORECASE,
    ),
    # Boundary-free coverage for the families the anchored EXACT set lets
    # one glued word character defeat. dbSNP needs six digits — a shorter
    # tail inside a word (``users`` plus a short counter) is prose, not a
    # planted rs id.
    "dbSNP-like identifier": re.compile(
        r"rs(?:[\s\-_.:;,/#]*\d){6,}", re.IGNORECASE
    ),
    # HGVS substitutions and protein changes keep their strict shape — a
    # lone transcript-position token inside a word is prose, but the same
    # position carrying a reference/alternate allele pair is a variant.
    "HGVS-like variant": re.compile(
        r"(?:c|g|m|n|r)\.\d+[ACGT]>[ACGT]"
        r"|p\.[A-Z][a-z]{2}\d+(?:[A-Z][a-z]{2}|Ter|\*)?"
    ),
}
# separators disappear, so only the strictest prefixes run here — with
# ``:``/``_``/``.`` gone the shapes are colon-less and underscore-less.
ALNUM_BIOLOGICAL_IDENTIFIER_PATTERNS = {
    "ClinVar accession": re.compile(
        r"(?:VCV|RCV|SCV)\d{6,}", re.IGNORECASE
    ),
    "RefSeq/Ensembl accession": re.compile(
        # Case-sensitive on the stripped view: real prefixes are uppercase,
        # while lowercase ``ng``+digits is everyday prose (``remaining
        # 14.85`` merges to ``ng1485``). A lowercase accession still flags
        # on the compacted view via the separator-tolerant GLUED pattern.
        r"(?:N[MRXCGPW]|X[MR]|ENST|ENSP|ENSG)\d{6,}"
    ),
    "HGNC/OMIM accession": re.compile(
        r"(?:HGNC|OMIM|MIM)\d{4,}", re.IGNORECASE
    ),
    "genomic coordinate": re.compile(
        r"chr(?:[1-9]|1\d|2[0-2]|X|Y|M|MT)\d{4,}", re.IGNORECASE
    ),
}
# A role word asserting a subject can also hide behind gluing: the compacted
# and alnum-stripped views drop word boundaries, so a boundary-free variant
# with the same discharge rules applies there. Bare short codes still need
# an id-marker or digit pair — the declared A0/A1 material vocabulary keeps
# its meaning.
SUBJECT_COMPACT_PATTERN = re.compile(
    r"(?i)(?:p[-_.]?r[-_.]?o[-_.]?b[-_.]?a[-_.]?n[-_.]?d|"
    r"s[-_.]?u[-_.]?b[-_.]?j[-_.]?e[-_.]?c[-_.]?t|d[-_.]?o[-_.]?n[-_.]?o[-_.]?r|"
    r"p[-_.]?a[-_.]?r[-_.]?t[-_.]?i[-_.]?c[-_.]?i[-_.]?p[-_.]?a[-_.]?n[-_.]?t|"
    r"p[-_.]?a[-_.]?t[-_.]?i[-_.]?e[-_.]?n[-_.]?t|"
    r"i[-_.]?n[-_.]?d[-_.]?i[-_.]?v[-_.]?i[-_.]?d[-_.]?u[-_.]?a[-_.]?l|"
    r"s[-_.]?p[-_.]?e[-_.]?c[-_.]?i[-_.]?m[-_.]?e[-_.]?n|"
    r"e[-_.]?n[-_.]?r[-_.]?o[-_.]?l[-_.]?l[-_.]?e[-_.]?e|"
    r"v[-_.]?o[-_.]?l[-_.]?u[-_.]?n[-_.]?t[-_.]?e[-_.]?e[-_.]?r|t[-_.]?w[-_.]?i[-_.]?n|"
    r"s[-_.]?a[-_.]?m[-_.]?p[-_.]?l[-_.]?e|m[-_.]?o[-_.]?t[-_.]?h[-_.]?e[-_.]?r|"
    r"c[-_.]?h[-_.]?i[-_.]?l[-_.]?d)"
    r"s?(?:id|no|num|number)?"
    # An underscore survives compaction, so it needs its own slot; the
    # letter gap after ``_`` stays short (``sample_size42`` is a variable
    # name) while the unprefixed gap covers gap-word prose merges.
    r"(?:_?[a-z]{0,2}|[a-z]{0,20})\d{2,}[a-z0-9]*"
)
# The portion of a subject-identifier match after the role word is the
# identifier itself; declared-synthetic labels (SYN-*, reviewed technical
# tokens) may stand there legitimately in fixtures.
_SUBJECT_IDENTIFIER_PORTION = re.compile(
    r"(?i)^(?:p-?r-?o-?b-?a-?n-?d|s-?u-?b-?j-?e-?c-?t|d-?o-?n-?o-?r|"
    r"p-?a-?r-?t-?i-?c-?i-?p-?a-?n-?t|p-?a-?t-?i-?e-?n-?t|"
    r"i-?n-?d-?i-?v-?i-?d-?u-?a-?l|s-?p-?e-?c-?i-?m-?e-?n|"
    r"e-?n-?r-?o-?l-?l-?e-?e|v-?o-?l-?u-?n-?t-?e-?e-?r|t-?w-?i-?n|"
    r"s-?a-?m-?p-?l-?e|m-?o-?t-?h-?e-?r|c-?h-?i-?l-?d)"
    r"(?:s(?![A-Za-z]))?(?:'s)?"
    r"[^\w]*"
)
# A plural ``s`` only counts when a real word boundary follows — under
# case-insensitivity ``s?`` would otherwise eat the leading letter of a
# glued namespace label (``participantSYN42`` → ``participant`` + ``SYN42``,
# where the ``S`` belongs to the label).
_SUBJECT_COMPACT_PORTION = re.compile(
    r"(?i)^(?:p-?r-?o-?b-?a-?n-?d|s-?u-?b-?j-?e-?c-?t|d-?o-?n-?o-?r|"
    r"p-?a-?r-?t-?i-?c-?i-?p-?a-?n-?t|p-?a-?t-?i-?e-?n-?t|"
    r"i-?n-?d-?i-?v-?i-?d-?u-?a-?l|s-?p-?e-?c-?i-?m-?e-?n|"
    r"e-?n-?r-?o-?l-?l-?e-?e|v-?o-?l-?u-?n-?t-?e-?e-?r|t-?w-?i-?n|"
    r"s-?a-?m-?p-?l-?e|m-?o-?t-?h-?e-?r|c-?h-?i-?l-?d)"
    r"(?:s(?![A-Za-z]))?"
    r"(?:id|no|num|number)?"
)
# A dischargeable merge tail is prose or field data — never a second role
# word: a declared label glued onto another role-word code still asserts
# that code, and a role word swallowed into a merge tail must not be eaten.
_SUBJECT_ROLE_WORDS = re.compile(
    r"(?i)proband|subject|donor|participant|patient|individual|"
    r"specimen|enrollee|volunteer|twin|sample|mother|child"
)
# A ``SYN`` label is the declared synthetic namespace — uppercase alphanumerics
# only. ``SYN`` glued onto a lowercase or role-word token is not a synthetic
# label, and ``SYN`` prefixed to an accession-shaped tail is a smuggle, not
# a namespace — the tail is vetted on every view: raw, rot13, and reversed,
# so ``SYN`` plus a transformed accession cannot pass.
_DECLARED_SYNTHETIC_TOKEN = re.compile(r"SYN[A-Z0-9_-]*\Z")
# An accession prefix fused to a digit run — either direction — is the
# payload shape, not a namespace label. Separators between the prefix and
# its digits count too: a ``SYN`` label glued to a separator-split InterPro
# accession rot13s into a readable ClinVar accession, so the vet tolerates
# the same separator class the GLUED patterns do. Requiring the digit
# adjacency keeps the letter pairs inside ordinary uppercase words from
# vetoing honest labels.
_ACCESSION_PREFIX_ADJACENT = re.compile(
    r"(?:VCV|RCV|SCV|N[MRXCGPW]_?|X[MR]_?|ENS[TPG]|HGNC|OMIM|MIM|CHR|HP:?|RS)"
    r"[\s\-_.:;,/#]*\d{4,}"
    r"|\d{4,}[\s\-_.:;,/#]*"
    r"(?:VCV|RCV|SCV|N[MRXCGPW]|X[MR]|ENS[TPG]|HGNC|OMIM|MIM|CHR|RS)",
    re.IGNORECASE,
)
# A bare accession prefix standing alone as a letter token — ``VCV`` beside
# a date-shaped token still assembles an accession under a transform. Only
# unambiguous prefixes are vetted here: two-letter RefSeq heads and the
# one/two-letter coordinate/phenotype prefixes live inside ordinary words
# too often.
_ACCESSION_PREFIX_IN_TOKEN = re.compile(
    r"(?:VCV|RCV|SCV|ENS[TPG]|HGNC|OMIM|MIM)", re.IGNORECASE
)
# A letter token that IS an accession field — a bare prefix or a prefix
# glued to digits — must not be excused by a field separator: a JSON pair
# like a dbSNP key beside its numeric value stores the identifier across
# two fields. ``chrN`` is exempt below three digits because a chromosome
# name is the ordinary genomics token, not an accession fragment.
_ACCESSION_FIELD_TOKEN = re.compile(
    r"(?:VCV|RCV|SCV|N[MRXCGPW]_?|X[MR]_?|ENS[TPG]|HGNC|OMIM|MIM|HP:?|RS)\d*"
    r"|CHR(?:\d{3,}|[XYM]\d+)",
    re.IGNORECASE,
)
# A long pure-hex token is digest material; a transform hit whose inverse
# lives entirely inside one is a coincidence (a hex tail rot13s into a
# dbSNP prefix shape). A shorter token still flags — real digests are 32+
# chars, so anything shorter was placed to be found.
_DIGEST_TOKEN = re.compile(r"[0-9a-fA-F]{32,}\Z")
# A whole letter token that *is* an accession prefix — bare or under a
# transform — is never merge noise: an InterPro head rot13s into a ClinVar
# head, and a reversed two-letter dbSNP head reads as itself. Two-letter
# heads and coordinate/phenotype prefixes are included here because this
# vet is a fullmatch, not a substring search — it only fires when the
# token is exactly the prefix.
_ACCESSION_PREFIX_TOKEN = re.compile(
    r"(?:VCV|RCV|SCV|N[MRXCGPW]_?|X[MR]_?|ENS[TPG]|HGNC|OMIM|MIM|CHR|HP:?|RS)\Z",
    re.IGNORECASE,
)


def _token_transforms(token: str) -> tuple[str, str, str]:
    return (token, codecs.decode(token, "rot_13"), token[::-1])


def _accession_field_token(token: str) -> bool:
    """The token is an accession field — a bare prefix or prefix+digits —
    under its own spelling or a transform. Field separators cannot excuse
    a real accession split across JSON cells."""

    return any(
        _ACCESSION_FIELD_TOKEN.fullmatch(view) is not None
        for view in _token_transforms(token)
    )


def _accession_prefix_token(token: str) -> bool:
    """The whole token is exactly an accession prefix under some transform —
    the shape a planted payload's letter part takes when separators hide
    its digits."""

    return any(
        _ACCESSION_PREFIX_TOKEN.fullmatch(view) is not None
        for view in _token_transforms(token)
    )


def _is_declared_synthetic_token(token: str) -> bool:
    if _DECLARED_SYNTHETIC_TOKEN.fullmatch(token) is None:
        return False
    rest = token[3:]
    # A role word in the tail vetoes the label only when it asserts a code
    # — a ``SYN`` label whose tail spells a role word plus digits smuggles
    # a subject code, while a compound name whose role word never meets a
    # digit stays a label.
    if re.search(
        r"(?i)(?:proband|subject|donor|participant|patient|individual|"
        r"specimen|enrollee|volunteer|twin|sample|mother|child)\w*\d",
        rest,
    ):
        return False
    views = (rest, codecs.decode(rest, "rot_13"), rest[::-1])
    return not any(
        _ACCESSION_PREFIX_ADJACENT.search(view) for view in views
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
# Suffix-retry candidates evaluate dozens of decodes per token, so the
# near-start window needs signatures that survive multiplied chance hits —
# the two-byte gzip head is pinned to the deflate form it always takes in
# practice.
NEAR_START_MAGIC_SIGNATURES = tuple(
    (b"\x1f\x8b\x08" if signature == b"\x1f\x8b" else signature, label)
    for signature, label in MAGIC_SIGNATURES
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
    if _is_declared_synthetic_token(identifier):
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


def _subject_identifier_hit(text: str, relative: PurePosixPath) -> bool:
    """A role word asserting a real subject is only discharged by the
    declared SYN namespace — technical tokens and shape exemptions must not
    turn a "subject <token>" assertion into an allowlisted one."""

    pattern = EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS["subject identifier"]
    for match in pattern.finditer(text):
        identifier = _SUBJECT_IDENTIFIER_PORTION.sub("", match.group(0))
        if (
            _public_identifier_allowed(match.group(0), relative)
            or _public_identifier_allowed(identifier, relative)
            or _is_declared_synthetic_token(identifier)
        ):
            continue
        # Sentence-final punctuation followed by whitespace is a boundary
        # a real assertion does not cross — ``sample identifiers.`` plus a
        # later heading number is prose, the same discharge the compacted
        # view's prose-gap rule applies. A colon stays assertion-shaped.
        if re.search(r"[.!?]\s", match.group(0)):
            continue
        # An allowlisted label glued onto lowercase prose is a merge
        # artifact, the same discharge the compacted view applies —
        # ``PROBAND01`` + ``enrolled``. An uppercase extension is a
        # different token; a role word in the tail reasserts a subject.
        if any(
            identifier.startswith(token)
            and identifier[len(token) :].isalpha()
            and identifier[len(token) :].islower()
            and not _SUBJECT_ROLE_WORDS.search(identifier[len(token) :])
            for token in PUBLIC_TECHNICAL_IDENTIFIER_ALLOWLIST
        ):
            continue
        return True
    return False


def _subject_compact_suppressed(
    match_text: str,
    relative: PurePosixPath,
    leading: tuple[str, int] | None = None,
) -> bool:
    """Compacted-view subject consult. Merged prose can glue an allowlisted
    label onto the following word — a ``subject`` mention, a declared
    label, and a verb become one merged token where the role word
    ``proband`` sits inside the declared label itself, and a declared-label
    CSV row merges onto its genotype fields where the leading raw token is
    the declared label. The match is discharged when the leading raw segment is an
    allowlisted/SYN token and the merge tail carries no role word of its
    own (a ``patient`` in the tail still asserts a subject), when the match
    or its identifier portion is allowlisted/SYN, or when it is an
    allowlisted label followed by a lowercase-prose tail (prose is not
    part of the label); an uppercase extension of a declared label is a
    different token and still flags."""

    if leading is not None:
        segment, covered = leading
        if covered <= len(match_text):
            tail = match_text[covered:]
            # A ``--``/``-`` + letters leading segment is a CLI flag name —
            # the digits that completed the match are the flag's value from
            # the next token (``--cases 10000`` merges to ``cases10000``).
            if (
                _public_identifier_allowed(segment, relative)
                or _is_declared_synthetic_token(segment)
                or (
                    re.fullmatch(r"--?[A-Za-z]+", segment)
                    # A flag literally named after a role word taking a
                    # numeric value is indistinguishable from the
                    # assertion; the CLI excuse only covers non-role flag
                    # names like ``--cases``.
                    and not _SUBJECT_ROLE_WORDS.search(segment)
                )
            ) and not _SUBJECT_ROLE_WORDS.search(tail):
                return True
    portion = _SUBJECT_COMPACT_PORTION.sub("", match_text)
    # Assignment punctuation between role and code (``participant = SYN42``)
    # is the same assertion as ``participant SYN42`` — the identifier
    # portion is the token after the non-word leader.
    portion_stripped = re.sub(r"^[\W_]+", "", portion)
    for candidate in (match_text, portion, portion_stripped):
        if _public_identifier_allowed(
            candidate, relative
        ) or _is_declared_synthetic_token(candidate):
            return True
        # A declared SYN label followed by a lowercase prose tail is a
        # merge artifact — ``SYN42`` + ``enrolled`` — the label itself is
        # the discharged part; an uppercase extension is a different token.
        syn_head = re.match(r"SYN[A-Z0-9_-]+", candidate)
        if (
            syn_head is not None
            and syn_head.end() < len(candidate)
            and candidate[syn_head.end() :].islower()
            and _is_declared_synthetic_token(syn_head.group(0))
            and not _SUBJECT_ROLE_WORDS.search(
                candidate[syn_head.end() :]
            )
        ):
            return True
        for token in (
            PUBLIC_TECHNICAL_IDENTIFIER_ALLOWLIST
            | PUBLIC_PATH_TECHNICAL_IDENTIFIER_ALLOWLIST.get(
                relative, frozenset()
            )
        ):
            tail = candidate[len(token) :]
            if (
                candidate.startswith(token)
                and tail.isalpha()
                and tail.islower()
                and not _SUBJECT_ROLE_WORDS.search(tail)
            ):
                return True
    return False


_IDENTIFIER_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)


def _transform_word_suppressed(
    match_text: str,
    inverse_fn: Callable[[str], str],
    source_text: str,
) -> bool:
    """A secret/controlled-pattern hit on a transformed view is excused
    only when its inverse sits inside an all-lowercase snake-phrase token —
    the shape an English identifier takes, like a test name whose
    ``stub_`` rot13s into a credential prefix. A token-shaped inverse —
    mixed case, digits, standalone — still flags: that is what a planted
    credential looks like. A glued ``xtub_…`` payload whose inverse spells
    lowercase words remains a bounded residual of this rule."""

    inverse = inverse_fn(match_text)
    if not inverse:
        return False
    start = 0
    while True:
        pos = source_text.find(inverse, start)
        if pos < 0:
            return False
        token = _raw_token_at(source_text, pos)
        if re.fullmatch(r"[a-z_]+", token):
            return True
        start = pos + 1


def _identifier_match_discharged(
    match_text: str,
    self_policy: bool,
    transform_context: tuple[str, Callable[[str], str], list] | None,
    relative: PurePosixPath,
) -> bool:
    """A policy-source file may name its own detection vocabulary — a
    documented accession in a comment is discharged on the self-token list
    — while a transform view keeps its own inverse-artifact rule."""

    if self_policy and match_text in POLICY_SOURCE_SELF_TOKENS:
        return True
    return _transform_artifact_suppressed(match_text, transform_context, relative)


def _source_view_maps(
    source_text: str,
) -> list[tuple[str, list[int] | None]]:
    """The source text plus its merged views, each paired with the map from
    a view position back to the raw position (``None`` for the raw view).
    Merged views are where a transform hit's inverse hides — scattered
    across separators the merge removed."""
    views: list[tuple[str, list[int] | None]] = [(source_text, None)]
    compacted = re.sub(r"[\s,]+", "", source_text)
    if compacted != source_text:
        views.append(
            (
                compacted,
                [
                    index
                    for index, char in enumerate(source_text)
                    if char not in " \t\n\r\x0b\x0c,"
                ],
            )
        )
    alnum = re.sub(r"[^0-9A-Za-z]+", "", source_text)
    if alnum != source_text and alnum != compacted:
        views.append(
            (
                alnum,
                [
                    index
                    for index, char in enumerate(source_text)
                    if char.isascii() and char.isalnum()
                ],
            )
        )
    return views


def _token_flags_identifier(
    token: str, self_policy: bool, relative: PurePosixPath
) -> bool:
    """Whether scanning ``token`` under the raw-view identifier rules would
    report an issue: every detector match inside it must itself survive the
    allowlist and the self-token discharge. Used only by the weak-family
    transform check — never by the strict families, where "not flag-shaped"
    is the default state of a smuggled payload."""

    patterns = (
        QUOTED_UPPER_IDENTIFIER_PATTERN,
        GENE_LIKE_TOKEN_PATTERN,
        *BIOLOGICAL_CONTEXT_PATTERNS,
        *EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.values(),
        *GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS.values(),
        *ALNUM_BIOLOGICAL_IDENTIFIER_PATTERNS.values(),
    )
    for pattern in patterns:
        for match in pattern.finditer(token):
            fragment = match.group(1) if match.lastindex else match.group(0)
            if _public_identifier_allowed(fragment, relative):
                continue
            if self_policy and fragment in POLICY_SOURCE_SELF_TOKENS:
                continue
            return True
    return False


def _raw_token_at(text: str, pos: int) -> str:
    """The maximal identifier-shaped raw token containing ``pos``."""

    lo = pos
    while lo > 0 and text[lo - 1] in _IDENTIFIER_CHARS:
        lo -= 1
    hi = pos + 1
    while hi < len(text) and text[hi] in _IDENTIFIER_CHARS:
        hi += 1
    return text[lo:hi]


def _raw_alnum_token_at(text: str, pos: int) -> str:
    """The maximal alphanumeric run containing ``pos`` — unlike
    ``_raw_token_at`` this splits on ``-``/``_`` too, so a hyphenated
    version or date token yields three runs. Merge analysis needs the
    separator-delimited unit:
    a hit whose letters sit in one run and whose digits sit in another is
    adjacency the view invented, while a single unbroken alnum run is the
    shape a planted payload takes."""

    lo = pos
    while lo > 0 and text[lo - 1].isascii() and text[lo - 1].isalnum():
        lo -= 1
    hi = pos + 1
    while hi < len(text) and text[hi].isascii() and text[hi].isalnum():
        hi += 1
    return text[lo:hi]


def _digit_leading_multi_letter(token: str) -> bool:
    """Digit-leading tokens carrying three or more letters are the shape a
    reversed or rot13'd accession leaves behind — the transform pushes the
    letter prefix to the tail. An innocent token (the ``Z`` of a timestamp
    reading back as a digit pair) has at most a letter or two."""

    # Two letters suffice for the veto: a digit-leading two-letter tail can
    # reverse into a short gene symbol — short gene names are real
    # identifiers too. A reversed timestamp fragment carries at most one
    # letter. Storage-size tails (``85GB``) are unit suffixes, not
    # reversed-letter payloads.
    if re.fullmatch(r"\d+(?:KB|MB|GB|TB|PB|KIB|MIB|GIB|TIB)", token):
        return False
    return token[:1].isdigit() and sum(char.isalpha() for char in token) >= 2


def _transform_artifact_suppressed(
    identifier: str,
    transform_context: tuple[str, Callable[[str], str], list] | None,
    relative: PurePosixPath,
    weak: bool = False,
) -> bool:
    """A token that only appears because the view was transformed: its
    inverse transform sits verbatim in the untransformed text by
    construction, so the hit is an artifact only when that source
    occurrence is *explained* — every raw token its chars came from is
    declared (pattern-definition material, a self-token, an allowlisted
    identifier) — or, for the weak generic families only, when the source
    token carries no identifier signal of its own. Strict accessions get
    no innocence path: "not flag-shaped on the raw view" is the default
    state of a smuggled payload — a reversed accession is digit-leading
    precisely because the transform hid it. Weak shapes keep a bounded
    innocence check because reversed timestamps and version tokens collide
    with the generic gene shape constantly — but a digit-leading
    multi-letter inverse still flags, since that is exactly what a
    reversed gene identifier looks like."""

    if transform_context is None:
        return False
    if len(transform_context) > 3:
        source_text, inverse_fn, source_spans, views = transform_context
    else:
        source_text, inverse_fn, source_spans = transform_context
        views = _source_view_maps(source_text)
    inverse = inverse_fn(identifier)
    if not inverse:
        return False
    self_policy = relative in PUBLICATION_POLICY_PATH_ALLOWLIST
    # The hit may live on a merged view of the transformed text, where its
    # inverse is scattered across separators — so the same merged views of
    # the source are searched too. Each view position maps back to a raw
    # position; the occurrence is explained when every raw token its chars
    # touch is declared material.
    for haystack, position_map in views:
        bounded = position_map is None
        start = 0
        while True:
            pos = haystack.find(inverse, start)
            if pos < 0:
                break
            raw_positions = [
                pos + i if bounded else position_map[pos + i]
                for i in range(len(inverse))
            ]
            distinct: dict[str, bool] = {}
            for rp in raw_positions:
                if self_policy and _is_pattern_definition_site(
                    source_text, rp, source_spans
                ):
                    continue
                token = _raw_token_at(source_text, rp)
                if token not in distinct:
                    distinct[token] = (
                        _public_identifier_allowed(token, relative)
                        or _is_declared_synthetic_token(token)
                        or (
                            self_policy
                            and token in POLICY_SOURCE_SELF_TOKENS
                        )
                    )
            if not distinct or all(distinct.values()):
                return True
            if bounded:
                original = _raw_token_at(source_text, pos)
            else:
                original = inverse
            candidates = {
                inverse,
                inverse.strip("-_"),
                original,
                original.strip("-_"),
            }
            if any(
                _public_identifier_allowed(candidate, relative)
                for candidate in candidates
            ) or (
                self_policy
                and any(
                    candidate in POLICY_SOURCE_SELF_TOKENS
                    for candidate in candidates
                )
            ):
                return True
            mid_token = raw_positions[0] > 0 and (
                source_text[raw_positions[0] - 1] in _IDENTIFIER_CHARS
            )
            if not weak and distinct:
                # A strict accession hit is explained only by merge
                # adjacency — the transformed or stripped view invented a
                # contiguity the source never had. Three independent
                # explanations, each checked against the raw positions:
                # (a) the hit's letters are a mid-word fragment of a longer
                #     letter run (an ``rs`` tail inside a plural noun, or
                #     letters inside a hyphenated version token) — an
                #     accession prefix planted mid-word is caught by the
                #     boundary-free raw scan, so a fragment here is always
                #     a merge artifact;
                # (b) the hit's digit positions span a real separator in
                #     the source (``-``, ``.``, ``/``, ``:``) — a date or
                #     version run that only reads as one number after
                #     merging;
                # (c) the raw span covering the whole hit carries a field
                #     separator (``:``, ``,``, ``;``, quotes, brackets) —
                #     a ``chrN`` key beside its numeric value merges into
                #     one coordinate-shaped run.
                #     Separators that the raw GLUED patterns already
                #     tolerate flag on the raw view regardless, so
                #     excusing them here never discharges a real payload.
                # A glued inverse inside one unbroken token — digit run
                # plus accession prefix in a single spelling — has no
                # separator and no unused letter, so a planted payload
                # still flags.
                letter_spans: dict[str, int] = {}
                digit_positions: list[int] = []
                letter_tokens: set[str] = set()
                digit_tokens: set[str] = set()
                for char, rp in zip(inverse, raw_positions):
                    token = _raw_alnum_token_at(source_text, rp)
                    if char.isalpha():
                        letter_tokens.add(token)
                        letter_spans[token] = letter_spans.get(token, 0) + 1
                    elif char.isdigit():
                        digit_tokens.add(token)
                        digit_positions.append(rp)
                merged = letter_tokens | digit_tokens
                fragment = any(
                    sum(char.isalpha() for char in token) > used
                    for token, used in letter_spans.items()
                )
                hit_span = source_text[
                    min(raw_positions) : max(raw_positions) + 1
                ]
                field_separated = bool(
                    re.search(r"[:,;'\"\(\)\[\]\{\}]", hit_span)
                )
                # A ``SYN``-prefixed container whose tail is not a declared
                # namespace label (its tail vets fail) is the namespace-
                # laundering shape — never let merge analysis discharge it.
                touched = {
                    _raw_token_at(source_text, rp) for rp in raw_positions
                }
                if any(
                    token[:3].upper() == "SYN"
                    and not _is_declared_synthetic_token(token)
                    for token in touched
                ):
                    start = pos + 1
                    continue
                # A hit whose inverse lives inside one long pure-hex token
                # is digest coincidence — hex letters rot13 into a dbSNP
                # prefix shape. Real digests are 32+ chars; anything
                # shorter was placed.
                container = _raw_alnum_token_at(source_text, raw_positions[0])
                if _DIGEST_TOKEN.fullmatch(container) and all(
                    _raw_alnum_token_at(source_text, rp) == container
                    for rp in raw_positions
                ):
                    return True
                clean_tokens = not any(
                    _ACCESSION_PREFIX_IN_TOKEN.search(token)
                    for token in letter_tokens
                ) and not any(
                    _token_flags_identifier(token, self_policy, relative)
                    for token in merged
                )
                # A ``chrN`` letter token is the canonical merge source:
                # a chromosome label beside a numeric field (``"chr4":`` +
                # a length, ``chrX,`` + a count) merges into coordinate
                # shape with every letter consumed — the field separator
                # and the accession vetoes still apply, and a literal
                # ``chrN:pos`` would flag on the raw view regardless.
                chr_label = any(
                    re.fullmatch(r"(?i)chr[0-9xym]{1,2}", token)
                    for token in letter_tokens
                )
                if (
                    field_separated
                    and clean_tokens
                    and (fragment or chr_label)
                    and not any(
                        _accession_field_token(token)
                        for token in letter_tokens
                    )
                ):
                    return True
                if (
                    clean_tokens
                    and letter_tokens
                    and digit_tokens
                    and letter_tokens.isdisjoint(digit_tokens)
                    and fragment
                    and not any(
                        _accession_prefix_token(token)
                        for token in letter_tokens
                    )
                ):
                    return True
            if (
                weak
                and mid_token
                and distinct
                and not any(
                    _token_flags_identifier(token, self_policy, relative)
                    for token in distinct
                )
            ):
                # Weak-family only: the inverse begins inside a larger
                # innocent token — the hit was assembled by token
                # adjacency, not a planted payload. Strict families never
                # reach this clause: "not flag-shaped on the raw view" is
                # the default state of a smuggled accession.
                return True
            if weak and not any(
                _digit_leading_multi_letter(token)
                or _token_flags_identifier(token, self_policy, relative)
                for token in distinct
            ):
                return True
            start = pos + 1
    return False


def _inspect_publication_text(
    relative: PurePosixPath,
    text: str,
    source: str,
    *,
    allow_released_biology: bool = False,
    view_label: str = "",
    transform_context: tuple[str, Callable[[str], str], list] | None = None,
) -> list[str]:
    self_policy = relative in PUBLICATION_POLICY_PATH_ALLOWLIST
    self_receipt = relative in OPERATIONAL_RECEIPT_PATH_ALLOWLIST

    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}{view_label}"
    exotic = _exotic_lookalike(text)
    if exotic is not None:
        issues.append(
            f"unmapped lookalike-script character {exotic!r} "
            f"(U+{ord(exotic):04X}): {prefix}"
        )
    if not allow_released_biology:
        identifiers: set[str] = set()
        identifiers.update(QUOTED_UPPER_IDENTIFIER_PATTERN.findall(text))
        identifiers.update(GENE_LIKE_TOKEN_PATTERN.findall(text))
        for pattern in BIOLOGICAL_CONTEXT_PATTERNS:
            identifiers.update(pattern.findall(text))
        for identifier in sorted(identifiers):
            if self_policy and identifier in POLICY_SOURCE_SELF_TOKENS:
                continue
            if _transform_artifact_suppressed(
                identifier, transform_context, relative, weak=True
            ):
                continue
            if not _public_identifier_allowed(identifier, relative):
                issues.append(
                    f"non-synthetic biological identifier {identifier!r}: {prefix}"
                )

        for label, pattern in EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
            # Subject-identifier assertions run unconditionally below — a
            # declared release-biology allowance covers accession and gene
            # text, never a real subject code.
            if label == "subject identifier":
                continue
            if any(
                not _identifier_match_discharged(
                    match.group(0), self_policy, transform_context, relative
                )
                for match in pattern.finditer(text)
            ):
                issues.append(f"{label}: {prefix}")
    # Glued characters cannot hide an identifier: the boundary-free
    # strict-literal set runs on every view, and two stripped views cover
    # merges — whitespace/commas removed, and everything non-alphanumeric
    # removed for the strictest prefixes. The fuzzy gene-like, context, and
    # lowercase-letter patterns stay off the merges because prose
    # collisions are too common there.
    compacted_view = re.sub(r"[\s,]+", "", text)
    alnum_view = re.sub(r"[^0-9A-Za-z]+", "", text)
    views = {compacted_view, alnum_view} - {text}
    # A hit on a merged view needs its own context: the match text is its
    # own inverse, and the merged-source position maps locate which raw
    # tokens its chars came from. Transform contexts (reversed/rot13) stay
    # in force for the transformed text's own merged views — they resolve
    # the inverse through the original source instead.
    merged_context = (
        # A merged view of a transformed text is the transform of the
        # merged source — separator-stripping commutes with reversal and
        # rot13 — so the transform context resolves the merged hit's
        # inverse through the original source unchanged.
        transform_context
        if transform_context is not None
        else (
            text,
            lambda value: value,
            _re_compile_spans(text) if self_policy else [],
            _source_view_maps(text),
        )
    )
    if not allow_released_biology:
        for label, pattern in GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
            if any(
                not _identifier_match_discharged(
                    match.group(0), self_policy, transform_context, relative
                )
                for match in pattern.finditer(text)
            ):
                issues.append(f"{label}: {prefix}")
        for view in views:
            for label, pattern in GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
                if any(
                    not _identifier_match_discharged(
                        match.group(0), self_policy, merged_context, relative
                    )
                    for match in pattern.finditer(view)
                ):
                    issues.append(f"{label} (compacted): {prefix}")
            for label, pattern in ALNUM_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
                if any(
                    not _identifier_match_discharged(
                        match.group(0), self_policy, merged_context, relative
                    )
                    for match in pattern.finditer(view)
                ):
                    issues.append(f"{label} (merged): {prefix}")
    if _subject_identifier_hit(text, relative):
        issues.append(f"subject identifier: {prefix}")
    # The whitespace/comma-compacted view still has punctuation boundaries
    # to keep a subject match bounded; the fully-merged alnum view removes
    # them all, so a role-word match there swallows the rest of the file
    # into one unbounded identifier — subject checks stay off it. The
    # compact scan runs even when compaction is a no-op: a separator-free
    # glued assertion (``SYN`` + role + code as a lone token) only exists
    # in boundary-free form.
    # Map each match start back to the raw text so the leading raw
    # token can be consulted — a declared label glued onto other
    # fields by the merge discharges, while a real glued assertion
    # (role word plus a short code) still flags. Both subject patterns
    # share this one discharge so a format variant cannot route around
    # it.
    compact_positions = [
        index
        for index, char in enumerate(text)
        if char not in " \t\n\r\x0b\x0c,"
    ]

    def _leading(match: re.Match[str]) -> tuple[str, int]:
        pos = compact_positions[match.start()]
        lo = pos
        while lo > 0 and text[lo - 1] in _IDENTIFIER_CHARS:
            lo -= 1
        hi = pos
        while hi < len(text) and text[hi] in _IDENTIFIER_CHARS:
            hi += 1
        return text[lo:hi], hi - pos

    def _spans_comma(match: re.Match[str]) -> bool:
        # A prose enumeration glued by compaction is excused only when
        # the comma separates two word phrases — a comma followed by
        # digits or a letter-digit code is a CSV subject field, which
        # must flag. The excused match's own digits must also form one
        # contiguous raw run: a role word whose code digits are split
        # across a space still asserts the joined code.
        first = compact_positions[match.start()]
        last = compact_positions[match.end() - 1]
        span = text[first : last + 1]
        comma = span.rfind(",")
        if comma < 0:
            return False
        rest = span[comma + 1 :].lstrip()
        if not (
            rest
            and rest[0].isalpha()
            and not any(char.isdigit() for char in rest)
        ):
            return False
        digit_runs = {
            _raw_alnum_token_at(text, compact_positions[pos])
            for pos in range(match.start(), match.end())
            if compacted_view[pos].isdigit()
        }
        return len(digit_runs) <= 1

    def _prose_gap(match: re.Match[str]) -> bool:
        # A glued assertion's connector between role word and code is at
        # most one word — a gap spanning two or more alphabetic words is a
        # running-prose merge (``participant must be at least 18``), which
        # compaction invented. A role word inside the gap means the tail
        # re-asserts a subject and the merge excuse does not apply.
        first = compact_positions[match.start()]
        last = compact_positions[match.end() - 1]
        span = text[first : last + 1]
        role_end = 0
        while role_end < len(span) and span[role_end].isalpha():
            role_end += 1
        # Intra-role separators in the dotted form (``p-a-t-i-e-n-t``)
        # interleave single letters with separators — a separator followed
        # by a whole word (``sample-stewardship``) is a hyphenated name,
        # not a dotted role, so only a lone letter continues the role.
        while role_end < len(span) and span[role_end] in "-_.":
            probe = role_end + 1
            while probe < len(span) and span[probe].isalpha():
                probe += 1
            if probe - (role_end + 1) != 1:
                break
            if probe < len(span) and span[probe] not in "-_.":
                break
            role_end = probe
        digit = next(
            (i for i, char in enumerate(span) if char.isdigit()), len(span)
        )
        gap = span[role_end:digit]
        # A comma in the gap is a prose enumeration — the merged digits
        # belong to a later list item (``specimen, unmatched-phase-…``),
        # never to the role word. Sentence-final punctuation followed by
        # whitespace is a boundary a real assertion does not cross.
        if "," in gap or re.search(r"[.!?]\s", gap):
            return True
        words = re.findall(r"[A-Za-z]+", gap)
        if len(words) < 2:
            return False
        # Identifier-scaffolding vocabulary (``id``, ``number``, ``code``)
        # keeps the assertion shape even spread over several words —
        # a role word + ``id``/``number`` + digits still asserts a code.
        if all(
            word.lower()
            in {
                "id", "no", "num", "number", "code", "identifier",
                "name", "named", "label", "tag", "ref", "record",
                "registration", "is", "was",
            }
            for word in words
        ):
            return False
        return not _SUBJECT_ROLE_WORDS.search(gap)

    hit = any(
        not _subject_compact_suppressed(
            match.group(0), relative, _leading(match)
        )
        for pattern in (
            EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS["subject identifier"],
            SUBJECT_COMPACT_PATTERN,
        )
        for match in pattern.finditer(compacted_view)
        if not _spans_comma(match) and not _prose_gap(match)
    )
    if hit:
        issues.append(f"subject identifier (compacted): {prefix}")
    pattern_spans = _re_compile_spans(text) if self_policy else []
    for label, pattern in OPERATIONAL_RECEIPT_PATTERNS.items():
        if self_receipt and label in OPERATIONAL_RECEIPT_SELF_LABELS:
            continue
        if self_policy and transform_context is None:
            if any(
                not _is_pattern_definition_site(text, match.start(), pattern_spans)
                for match in pattern.finditer(text)
            ):
                issues.append(f"{label}: {prefix}")
        elif transform_context is not None:
            if any(
                not _transform_artifact_suppressed(
                    match.group(0), transform_context, relative
                )
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
    r"={0,3}[A-Za-z]+={0,3}"
    r"|={0,3}[A-Z0-9_]+={0,3}"
    r"|={0,3}[a-z0-9_]+={0,3}"
    # Word-character tokens — snake/camel/UPPER_lower code merges — are
    # ambiguous with carrier alphabets; only the strong signatures and the
    # embedded-identifier pass get to speak for them.
    r"|={0,3}[A-Za-z0-9_]+={0,3}"
    r"|[0-9a-fA-F]+={0,3}"
    r"|[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)+={0,3}"
    r"|--?[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*={0,3}"
    # ``name=value`` code assignments — a mid-token ``=`` is not carrier
    # padding; the whole token is a keyword-argument shape.
    r"|[A-Za-z0-9_]+=[A-Za-z0-9_=.-]*"
    r"\Z"
)
# The path/expression shape (carrier-alphabet chars with at least one
# ``+``, ``.`` or ``/``) is checked as charset plus separator presence —
# the equivalent nested-quantifier pattern backtracks exponentially on long
# merged-prose tokens.
_BASE64_BENIGN_PATH_CHARS = re.compile(r"[A-Za-z0-9_+./-]*={0,3}\Z")


_CARRIER_ALPHABET_STRINGS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/_-=",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-",
    "0123456789ABCDEFabcdef",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",
    "0123456789ABCDEFGHIJKLMNOPQRSTUV",
    "abcdefghijklmnopqrstuvwxyz234567",
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz",
)


def _is_alphabet_documentation_token(token: str) -> bool:
    """The alphabet written out as documentation — contiguous ascending
    blocks (A-Z, a-z, 0-9) or a slice of a canonical carrier alphabet.
    Real encodings never produce this shape, so it is never a payload."""

    stripped = token.strip("=")
    if len(stripped) < 8:
        return False
    runs: list[str] = []
    run_start = 0
    for i in range(1, len(stripped)):
        if stripped[i] <= stripped[i - 1]:
            runs.append(stripped[run_start:i])
            run_start = i
    runs.append(stripped[run_start:])
    return all(
        len(run) >= 4 and ord(run[-1]) - ord(run[0]) + 1 == len(run)
        for run in runs
    ) or any(
        stripped in alphabet for alphabet in _CARRIER_ALPHABET_STRINGS
    )


def _is_benign_base64_token(token: str) -> bool:
    if _is_alphabet_documentation_token(token):
        return True
    return _BASE64_BENIGN_TOKEN.fullmatch(token) is not None or (
        _BASE64_BENIGN_PATH_CHARS.fullmatch(token) is not None
        and any(char in token for char in "+./")
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
        if not re.search(r"[\\%&]", out):
            break
        decoded = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda match: chr(int(match.group(1), 16)),
            out,
        )
        decoded = re.sub(
            r"\\U([0-9a-fA-F]{8})",
            lambda match: chr(int(match.group(1), 16)),
            decoded,
        )
        decoded = re.sub(
            r"\\u\{([0-9a-fA-F]{1,6})\}",
            lambda match: chr(int(match.group(1), 16)),
            decoded,
        )
        decoded = re.sub(
            r"\\x([0-9a-fA-F]{2})",
            lambda match: chr(int(match.group(1), 16)),
            decoded,
        )
        decoded = re.sub(
            r"\\([0-7]{3})",
            lambda match: chr(int(match.group(1), 8)),
            decoded,
        )
        decoded = re.sub(
            r"%u([0-9a-fA-F]{4})",
            lambda match: chr(int(match.group(1), 16)),
            decoded,
        )
        decoded = urllib.parse.unquote(decoded)
        decoded = html.unescape(decoded)
        if decoded == out:
            break
        out = decoded
    return out


def _b64_decode_token(token: str) -> bytes | None:
    """Padding-tolerant base64 decode; None when the token is not base64.

    Interior ``=`` padding smuggled mid-token is removed before decoding —
    otherwise one stray character would neutralize the whole token."""

    core = token.replace("=", "").translate(str.maketrans("-_", "+/"))
    if not core:
        return None
    core += "=" * (-len(core) % 4)
    try:
        return base64.b64decode(core, validate=True)
    except ValueError:
        return None


def _hex_decode_token(token: str) -> bytes | None:
    """Hex decode for tokens that sit inside the base64 alphabet."""

    try:
        return bytes.fromhex(token)
    except ValueError:
        return None


def _b32_decode_token(token: str) -> bytes | None:
    """Padding-tolerant base32 decode; None when the token is not base32."""

    core = token.rstrip("=")
    core += "=" * (-len(core) % 8)
    try:
        return base64.b32decode(core)
    except ValueError:
        return None


def _b32lower_decode_token(token: str) -> bytes | None:
    """Lowercase base32 (same alphabet, case-folded) decode."""

    core = token.rstrip("=").upper()
    if not re.fullmatch(r"[A-Z2-7]+", core):
        return None
    core += "=" * (-len(core) % 8)
    try:
        return base64.b32decode(core)
    except ValueError:
        return None


def _b32hex_decode_token(token: str) -> bytes | None:
    """Base32hex (0-9A-V alphabet) decode."""

    core = token.rstrip("=")
    if not re.fullmatch(r"[0-9A-V]+", core):
        return None
    core += "=" * (-len(core) % 8)
    try:
        return base64.b32hexdecode(core)
    except (ValueError, AttributeError):
        return None


def _b85_decode_token(token: str) -> bytes | None:
    """Base85 decode; None when the token is not decodable."""

    try:
        return base64.b85decode(token.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None


def _a85_decode_token(token: str) -> bytes | None:
    """Ascii85 decode of a bare body (no ``<~ ~>`` wrapper)."""

    try:
        return base64.a85decode(token.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None


_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58_decode_token(token: str) -> bytes | None:
    """Base58 decode (manual — the stdlib has no decoder)."""

    if not token or any(char not in _BASE58_ALPHABET for char in token):
        return None
    # The manual decode below is quadratic in token length (a big-int
    # multiply per character). Tokens beyond this bound cannot hide a
    # scannable identifier-sized payload and would otherwise allow a
    # memory-exhaustion denial of service inside the scanner itself.
    if len(token) > 131072:
        return None
    number = 0
    for char in token:
        number = number * 58 + _BASE58_ALPHABET.index(char)
    body = number.to_bytes(-(-number.bit_length() // 8), "big") if number else b""
    pad = len(token) - len(token.lstrip("1"))
    return b"\x00" * pad + body


def _uu_decode_block(block: str) -> bytes | None:
    """Uudecode a captured body (lines after the ``begin`` marker)."""

    import binascii

    out = bytearray()
    for line in block.splitlines():
        line = line.rstrip("\r\n")
        if not line or line == " ":
            break
        try:
            chunk = binascii.a2b_uu(line.encode("ascii"))
        except (ValueError, binascii.Error, UnicodeEncodeError):
            return None
        out.extend(chunk)
    return bytes(out) if out else None


def _decode_carrier(token: str, carrier: str) -> bytes | None:
    if carrier == "hex":
        return _hex_decode_token(token)
    if carrier == "base32":
        return _b32_decode_token(token)
    if carrier == "base32lower":
        return _b32lower_decode_token(token)
    if carrier == "base32hex":
        return _b32hex_decode_token(token)
    if carrier == "base85":
        return _b85_decode_token(token)
    if carrier == "ascii85":
        return _a85_decode_token(token)
    if carrier == "base58":
        return _b58_decode_token(token)
    return _b64_decode_token(token)


def _decode_utf16_or_32(decoded: bytes) -> str | None:
    """Decode alternating-NUL payloads — UTF-16/32LE/BE text in a carrier.

    A text token in UTF-16LE reads ``V\\x00C\\x00V\\x00`` — ASCII runs are all
    length one, the printability bar fails, and the identifier never
    surfaces. Structurally-dense NUL placement is the tell.
    """

    for codec, step, nul_positions in (
        ("utf-16-le", 2, (1,)),
        ("utf-16-be", 2, (0,)),
        ("utf-32-le", 4, (1, 2, 3)),
        ("utf-32-be", 4, (0, 1, 2)),
    ):
        if len(decoded) < 8 or len(decoded) % step:
            continue
        nul_hits = sum(
            1
            for index in range(len(decoded))
            if index % step in nul_positions and decoded[index] == 0
        )
        expected = len(decoded) * len(nul_positions) // step
        if expected and nul_hits / expected >= 0.9:
            try:
                text = decoded.decode(codec)
            except UnicodeDecodeError:
                continue
            printable = sum(
                1 for char in text if char.isprintable() or char in "\t\n\r"
            )
            if text and printable / len(text) >= 0.9:
                return text
    return None


def _decompress_payload(decoded: bytes) -> str | None:
    """Bounded decompress-and-rescan for magic-less compressed payloads.

    zlib/deflate and raw lzma streams carry no reliable magic, so the only
    honest detector is the decompression itself — a stream that inflates to
    printable text is scanned like any decoded view.
    """

    import lzma
    import zlib
    import bz2

    for decompress in (
        zlib.decompress,
        bz2.decompress,
        lzma.decompress,
        lambda blob: zlib.decompress(blob, wbits=-15),
    ):
        try:
            inflated = decompress(decoded)
        except Exception:
            continue
        if 0 < len(inflated) <= MAX_PUBLIC_BYTES:
            text = _printable_payload_text(inflated)
            if text is not None:
                return text
    return None


def _printable_fraction(decoded: bytes) -> float:
    if not decoded:
        return 0.0
    printable = sum(
        1 for byte in decoded if 0x20 <= byte <= 0x7E or byte in (0x09, 0x0A, 0x0D)
    )
    return printable / len(decoded)


def _longest_printable_run(decoded: bytes) -> int:
    """The longest stretch of printable bytes: a mostly-text payload with
    stray fillers still contains a readable word, while a chance gibberish
    decode that lands above the printable-fraction bar scatters its
    printable bytes into runs a few bytes long."""

    best = current = 0
    for byte in decoded:
        if 0x20 <= byte <= 0x7E or byte in (0x09, 0x0A, 0x0D):
            current += 1
            if current > best:
                best = current
        else:
            current = 0
    return best


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
    # Embedded evidence uses the strict (3+ byte) signature set: with every
    # carrier family attempting each token, a two-byte head like gzip's
    # ``\x1f\x8b`` appears in chance decodes several times per file.
    return any(
        signature in decoded
        for signature, _label in NEAR_START_MAGIC_SIGNATURES
        if any(byte > 0x7E or byte < 0x09 for byte in signature)
    )


_RESIDUAL_ENCODING = re.compile(
    r"\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{8}|\\u\{[0-9a-fA-F]{1,6}\}|"
    r"\\x[0-9a-fA-F]{2}|\\[0-7]{3}|%u[0-9a-fA-F]{4}|"
    r"%[0-9a-fA-F]{2}|&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]{1,31});"
)
# Material that can carry a deeper encoded layer. A printable decode only
# earns full recursion when it plausibly *is* another encoding — gibberish
# decodes of merged prose nearly always contain a stray alphabet run, so a
# bare pattern hit is not enough.
_RESIDUAL_CARRIER_RUNS = (
    _BASE64_RUN,
    _BASE64_SPLIT_RUN,
    _HEX_RUN,
    _BASE32_RUN,
    _BASE32HEX_RUN,
    _BASE85_RUN,
    _BASE58_RUN,
)
_RESIDUAL_LAYER_PATTERNS = _RESIDUAL_CARRIER_RUNS + (
    _UUENCODE_BLOCK,
    _RESIDUAL_ENCODING,
)


def _has_residual_layer(text: str) -> bool:
    return any(pattern.search(text) for pattern in _RESIDUAL_LAYER_PATTERNS)


def _earns_decode_recursion(text: str) -> bool:
    """Whether a printable decode plausibly carries a deeper layer: an
    explicit block marker or a cluster of escapes (a lone incidental escape
    does not), or a carrier run dominating the text — ``base64(base64(x))``
    decodes to a token that *is* its own carrier alphabet, while a gibberish
    decode of prose only ever has incidental runs."""

    if _UUENCODE_BLOCK.search(text):
        return True
    if len(_RESIDUAL_ENCODING.findall(text)) >= 2:
        return True
    stripped = text.strip()
    if not stripped:
        return False
    longest = 0
    for pattern in _RESIDUAL_CARRIER_RUNS:
        for match in pattern.finditer(text):
            longest = max(longest, len(match.group(0)))
    # A 16-char run already carries a twelve-byte payload — under the old
    # 24-char bar a nested accession token never earned inspection. A run
    # that dominates the text earns at 16; a run ≥40 earns outright —
    # padding a real nested token with prose cannot shrink its alphabet.
    return longest >= 16 and (
        longest * 2 >= len(stripped) or longest >= 40
    )


def _decode_candidates(haystack: str) -> list[tuple[str, str, bool, bool]]:
    """(normalized token, carrier, primary, short_only) decode candidates.

    A token can be a valid run in more than one encoding — hex, base32,
    base32hex, lowercase base32, and base58 alphabets all sit inside
    base64's — so each candidate names the carrier that produced it.
    ``primary`` marks the carrier whose own run pattern surfaced the token:
    a primary token that fails to decode is itself an anomaly worth
    flagging. ``short_only`` candidates sit below the carrier floor — their
    decodes are scanned for exact identifiers only, never treated as binary
    evidence. Punctuation-split fragments reassemble into a joined token.
    """

    candidates: list[tuple[str, str, bool, bool]] = []
    seen: set[tuple[str, str]] = set()

    def offer(token: str, carrier: str, primary: bool, short_only: bool = False) -> None:
        if (carrier, token) not in seen:
            seen.add((carrier, token))
            candidates.append((token, carrier, primary, short_only))

    def offer_variants(token: str, primary: bool) -> None:
        """Offer every carrier whose alphabet the token fully matches."""

        offer(token, "base64", primary)
        if _HEX_RUN.fullmatch(token):
            offer(token, "hex", False)
        if _BASE32_RUN.fullmatch(token):
            offer(token, "base32", False)
        if _BASE32HEX_RUN.fullmatch(token):
            offer(token, "base32hex", False)
        if re.fullmatch(r"[a-z2-7]+={0,6}", token):
            offer(token, "base32lower", False)
        if _BASE58_RUN.fullmatch(token):
            offer(token, "base58", False)

    for token in _BASE64_RUN.findall(haystack):
        offer_variants(token, True)
    for token in _BASE64_SHORT_RUN.findall(haystack):
        offer(token, "base64", False, short_only=True)
    for match in _BASE64_SPLIT_RUN.finditer(haystack):
        joined = re.sub(r"[^A-Za-z0-9+/=_-]+", "", match.group(0))
        if len(joined) >= 16:
            offer_variants(joined, False)
        elif len(joined) >= 8:
            offer(joined, "base64", False, short_only=True)
    for token in _HEX_RUN.findall(haystack):
        offer(token, "hex", True)
    for token in _HEX_SHORT_RUN.findall(haystack):
        offer(token, "hex", False, short_only=True)
    for match in _HEX_SPLIT_RUN.finditer(haystack):
        joined = re.sub(r"[^0-9a-fA-F]+", "", match.group(0))
        if len(joined) >= 24:
            offer(joined, "hex", False)
        elif len(joined) >= 16:
            offer(joined, "hex", False, short_only=True)
    for token in _BASE32_RUN.findall(haystack):
        offer(token, "base32", True)
    for token in _BASE32_SHORT_RUN.findall(haystack):
        offer(token, "base32", False, short_only=True)
    for token in _BASE32HEX_RUN.findall(haystack):
        offer(token, "base32hex", True)
    for token in _BASE85_RUN.findall(haystack):
        offer(token, "base85", False)
        offer(token, "ascii85", False)
    for token in _BASE58_RUN.findall(haystack):
        offer(token, "base58", True)
    for match in _UUENCODE_BLOCK.finditer(haystack):
        offer(match.group(1), "uuencode", True)
    for match in _UUENCODE_BODY_RUN.finditer(haystack):
        offer(match.group(0), "uuencode", False)
    return candidates


def _embedded_identifier_sweep(
    relative: PurePosixPath,
    text: str,
    source: str,
    *,
    allow_released_biology: bool,
    view_label: str,
) -> list[str]:
    """One identifiers-only decode round for a terminal layer. A nested
    carrier token that never earned full recursion — too short, or padded
    by prose — still gets decoded once and identifier-scanned, so a
    shallow ``base64(base64(accession))`` cannot hide under the recursion
    bar. Decode failures stay silent: a terminal layer owes an
    identifiers pass, not carrier forensics."""

    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}{view_label}"
    seen_texts: set[str] = set()
    haystacks = [text]
    folded = _scan_fold(text)
    if folded != text:
        haystacks.append(folded)
    for haystack in haystacks:
        for token, carrier, _primary, _short in _decode_candidates(haystack):
            if carrier == "uuencode":
                decoded = _uu_decode_block(token)
            else:
                try:
                    decoded = _decode_carrier(token, carrier)
                except (MemoryError, OverflowError, ValueError):
                    decoded = None
            if decoded is None:
                continue
            payload = _printable_payload_text(decoded)
            if payload is None:
                payload = _decode_utf16_or_32(decoded)
            if payload is None:
                payload = _decompress_payload(decoded)
            if payload is None:
                # Binary decodes still yield their printable runs — a
                # glued accession inside must surface.
                runs = re.findall(rb"[ -~]{3,}", decoded)
                joined = b" ".join(runs).decode("ascii", "ignore")
                for label, pattern in (
                    *EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                    *GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                    *ALNUM_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                ):
                    if pattern.search(joined):
                        issues.append(
                            f"{carrier}-embedded {label}: {prefix}"
                        )
                        break
                continue
            if payload in seen_texts:
                continue
            seen_texts.add(payload)
            issues.extend(
                _inspect_publication_text(
                    relative,
                    _scan_fold(payload),
                    source,
                    allow_released_biology=allow_released_biology,
                    view_label=view_label + f"({carrier}-embedded)",
                )
            )
    return issues


def _inspect_payload_text(
    relative: PurePosixPath,
    text: str,
    source: str,
    *,
    allow_released_biology: bool = False,
    view_label: str = "",
    _depth: int = 0,
    _terminal: bool = False,
) -> list[str]:
    """Full detector set for text payloads — file content, decoded carrier
    runs, unescaped text, and Git commit/tag messages. Secrets,
    controlled-payload markers, and phenotype bundles apply here just as they
    do to raw file text; a released artifact's declared biology allowance
    extends to payloads embedded inside it. Decoded views recurse so a
    payload cannot hide one layer under another. ``_terminal`` marks a
    decoded text with no carrier layer of its own: it gets the full
    text-level detector set and transforms but no further decode round."""

    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}{view_label}"
    folded = _scan_fold(text)
    # Escapes are decoded up front — a payload is still the payload when its
    # spaces arrive as ``\x20``. The unescaped view is itself a haystack for
    # the text-level scans below rather than a recursion, so a terminal
    # layer still gets inspected under it.
    unescaped = _unescape_text(text)
    unescaped_folded = _scan_fold(unescaped)
    secret_views = {text, folded, unescaped, unescaped_folded}
    for label, pattern in SECRET_PATTERNS.items():
        if any(pattern.search(view) for view in secret_views):
            issues.append(f"{label} pattern: {prefix}")
    for label, pattern in CONTROLLED_TEXT_PATTERNS.items():
        if any(pattern.search(view) for view in secret_views):
            issues.append(f"{label}: {prefix}")
    # Merged views defeat \b-anchored secret patterns: ``aW1hZ2Vz``
    # split as ``aW1h Z2Vz`` rejoins on the compacted view.
    for merged in {re.sub(r"[\s,]+", "", text), re.sub(r"[^0-9A-Za-z]+", "", text)} - secret_views:
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(merged):
                issues.append(f"{label} pattern (merged): {prefix}")
    if len(set(HPO_PATTERN.findall(folded))) >= 3 or len(
        set(HPO_PATTERN.findall(unescaped_folded))
    ) >= 3:
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
    if _terminal or _depth >= _PAYLOAD_MAX_DEPTH:
        # Fail closed rather than silently pass a payload nested deeper than
        # the recursion bound: residual carriers or escapes at the depth
        # limit mean a layer was never inspected. The text-level transform
        # scans still run — they inspect this layer, not a deeper one.
        if not _terminal and _has_residual_layer(text):
            issues.append(
                "nested encoding exceeds inspection depth: " + prefix
            )
        issues.extend(
            _embedded_identifier_sweep(
                relative,
                text,
                source,
                allow_released_biology=allow_released_biology,
                view_label=view_label,
            )
        )
        issues.extend(
            _transform_scan_issues(
                relative,
                text,
                folded,
                source,
                allow_released_biology=allow_released_biology,
                view_label=view_label,
            )
        )
        if unescaped != text:
            # A terminal layer still owes its unescaped form the full
            # text-level detector set — escapes are not a deeper carrier,
            # they are the same layer spelled differently.
            issues.extend(
                _inspect_publication_text(
                    relative,
                    unescaped_folded,
                    source,
                    allow_released_biology=allow_released_biology,
                    view_label=view_label + "(unescaped)",
                )
            )
            issues.extend(
                _transform_scan_issues(
                    relative,
                    unescaped,
                    unescaped_folded,
                    source,
                    allow_released_biology=allow_released_biology,
                    view_label=view_label + "(unescaped)",
                )
            )
        return issues

    seen: set[tuple[str, str]] = set()
    haystacks = [(text, False), (folded, False)]
    compact = re.sub(r"[\s,]+", "", text)
    if compact != text:
        haystacks.append((compact, True))
    compact_folded = re.sub(r"[\s,]+", "", folded)
    if compact_folded != folded and compact_folded != compact:
        haystacks.append((compact_folded, True))
    for haystack, compacted in haystacks:
        candidates = _decode_candidates(haystack)
        # A token may be offered twice under one carrier — a strong run and
        # a split-run for instance — and only one offer may carry the
        # primary flag. Decode work dedupes on (carrier, token) but the
        # did-not-decode flag must honour ANY primary offer, not just the
        # one that happened to be evaluated.
        primary_offer = {
            (carrier, token) for token, carrier, primary, _ in candidates if primary
        }
        for token, carrier, primary, short_only in candidates:
            if (carrier, token) in seen:
                continue
            seen.add((carrier, token))
            if carrier == "uuencode":
                decoded_uu = _uu_decode_block(token)
                if decoded_uu is None:
                    issues.append(
                        "uuencode block did not decode: " + prefix
                    )
                    continue
                decodes_uu = [(0, decoded_uu)]
            else:
                # Whatever length a merged-prose prefix has, one of the
                # carrier's chunk alignments re-aligns the payload — the
                # merge then decodes to a garbage prefix and the payload's
                # own magic or text surfaces inside the decode.
                align = 1 if short_only else _CARRIER_ALIGNMENT.get(carrier, 1)
                decodes_uu = []
                for offset in range(align):
                    try:
                        decoded = _decode_carrier(token[offset:], carrier)
                    except (MemoryError, OverflowError, ValueError):
                        decoded = None
                    if (
                        decoded is not None
                        and len(decoded) <= MAX_PUBLIC_BYTES
                    ):
                        decodes_uu.append((offset, decoded))
            if not decodes_uu:
                # A benign-shaped token never claimed to be a payload — its
                # alphabet match is coincidental (code identifiers, alphabet
                # documentation) — so a failed decode means nothing. Only a
                # real carrier lookalike that refuses to decode is anomalous.
                if (carrier, token) in primary_offer and not _is_benign_base64_token(token):
                    issues.append(
                        f"{carrier}-pattern token did not decode: {prefix}"
                    )
                continue
            recursed_texts: set[str] = set()
            binary_candidates: list[tuple[int, bytes]] = []
            for offset, decoded in decodes_uu:
                payload_text = _printable_payload_text(decoded)
                if payload_text is None:
                    payload_text = _decode_utf16_or_32(decoded)
                if payload_text is None:
                    payload_text = _decompress_payload(decoded)
                if payload_text is not None:
                    if payload_text not in recursed_texts:
                        recursed_texts.add(payload_text)
                        if short_only:
                            # Sub-floor tokens earn an identifiers-only pass:
                            # random short decodes cannot spell an accession.
                            issues.extend(
                                _inspect_publication_text(
                                    relative,
                                    payload_text,
                                    source,
                                    allow_released_biology=(
                                        allow_released_biology
                                    ),
                                    view_label=view_label
                                    + f"({carrier}-short)",
                                )
                            )
                        elif _earns_decode_recursion(payload_text):
                            issues.extend(
                                _inspect_payload_text(
                                    relative,
                                    payload_text,
                                    source,
                                    allow_released_biology=(
                                        allow_released_biology
                                    ),
                                    view_label=view_label + f"({carrier})",
                                    _depth=_depth + 1,
                                )
                            )
                        else:
                            # The decode is just text — no carrier run
                            # dominates it and no escape cluster remains —
                            # so the terminal detector set (secrets,
                            # controlled markers, identifiers, transforms)
                            # is the whole inspection and no decode round
                            # is spent re-deriving the same view.
                            issues.extend(
                                _inspect_payload_text(
                                    relative,
                                    payload_text,
                                    source,
                                    allow_released_biology=(
                                        allow_released_biology
                                    ),
                                    view_label=view_label + f"({carrier})",
                                    _terminal=True,
                                )
                            )
                    continue
                if short_only:
                    continue
                binary_candidates.append((offset, decoded))
            if not binary_candidates:
                continue
            # Binary-looking decodes: readable runs inside still take the
            # precise-identifier pass — joined with spaces so a smuggler's
            # non-printable gap-fillers cannot split an accession across
            # runs (prefix letters + control-byte pad + digits joins to an
            # accession hit).
            # Magic signatures are deliberate-payload evidence and override
            # token shape; the weaker NUL/near-text tripwires still consult
            # the benign shapes because constants, digests, and path tokens
            # decode to entropy-random gibberish by chance.
            run_labels: set[str] = set()
            for _offset, decoded in binary_candidates:
                runs = [
                    run.decode("ascii")
                    for run in re.findall(rb"[ -~]{3,}", decoded)
                ]
                # Boundary-free families apply too: ``xxVCV…`` inside a
                # binary decode defeats \b-anchored patterns but must not
                # pass — a glued accession is still the whole payload.
                # Subject assertions and credentials ride the same runs —
                # binary padding is a carrier, not an excuse.
                for run_text in [*runs, " ".join(runs)]:
                    for label, pattern in (
                        *EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                        *GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                        *ALNUM_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                        *SECRET_PATTERNS.items(),
                    ):
                        if pattern.search(run_text):
                            run_labels.add(label)
            for label in sorted(run_labels):
                issues.append(f"{carrier}-embedded {label}: {prefix}")
            benign = _is_benign_base64_token(token)
            binary_hit = False
            for offset, decoded in binary_candidates:
                fraction = _printable_fraction(decoded)
                # The strict signature set — every signature at least three
                # bytes — is safe to match anywhere in a decode, which is
                # where a prose merge or a smuggler's short prefix pushes a
                # real payload's magic.
                strong_hit = any(
                    signature in decoded
                    for signature, _label in NEAR_START_MAGIC_SIGNATURES
                )
                if not strong_hit and offset == 0 and not compacted:
                    # The un-compacted token edge is the payload's own
                    # start. Even here the strict signature set applies:
                    # every carrier family attempting every token makes the
                    # two-byte head a chance hit.
                    strong_hit = any(
                        decoded.startswith(signature)
                        for signature, _label in NEAR_START_MAGIC_SIGNATURES
                    )
                if strong_hit:
                    binary_hit = True
                    break
                if offset or len(decoded) < 16 or carrier not in _WEAK_EVIDENCE_CARRIERS:
                    # Weak evidence applies only at offset zero on a
                    # substantial decode from a common carrier: misaligned
                    # retries, short decodes, and exotic alphabets produce
                    # pure gibberish that trips the soft tripwires at
                    # coin-flip rates.
                    continue
                if benign:
                    # Benign-shaped tokens (code constants, alphabet
                    # documentation, kebab tokens) decode to the same
                    # low-entropy gibberish a magic-less binary blob does —
                    # byte statistics cannot tell them apart, so weak
                    # evidence stays off this class entirely. A deliberate
                    # structured payload still flags above via the strict
                    # signature set, which no benign shape exempts; and a
                    # textual payload never reaches this branch at all.
                    continue
                # The raw view keeps the \x00 and near-text tripwires: a
                # decode that is mostly printable but failed the text bar
                # is a carrier with non-printable fillers — but only when
                # its printable bytes form a readable stretch; a gibberish
                # decode scatters them. The compacted view glues prose/code
                # words into fake tokens whose decode is entropy-random —
                # compacted evidence beyond the strict signatures requires
                # NULs amid mostly-readable text (deliberate payload
                # shapes, not merge gibberish).
                if compacted:
                    binary_hit = b"\x00" in decoded and fraction >= 0.5
                else:
                    binary_hit = b"\x00" in decoded or (
                        fraction >= 0.5
                        and _longest_printable_run(decoded) >= 12
                    )
                if binary_hit:
                    break
            if binary_hit:
                issues.append(
                    f"{carrier}-embedded binary payload requiring "
                    f"offline review: {prefix}"
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
    issues.extend(
        _transform_scan_issues(
            relative,
            text,
            folded,
            source,
            allow_released_biology=allow_released_biology,
            view_label=view_label,
        )
    )
    return issues


def _transform_scan_issues(
    relative: PurePosixPath,
    text: str,
    folded: str,
    source: str,
    *,
    allow_released_biology: bool,
    view_label: str,
) -> list[str]:
    """Transformed plaintext scans: a reversed or rot13'd identifier reads
    cleanly to a human reviewer and rides any carrier. The untransformed
    text travels as the transform context so a hit that merely re-encodes a
    declared plaintext token (``PROBAND01`` → ``CEBONAQ01``) is suppressed
    while a genuinely smuggled payload still flags."""

    issues: list[str] = []
    source_spans = (
        _re_compile_spans(folded)
        if relative in PUBLICATION_POLICY_PATH_ALLOWLIST
        else []
    )
    source_views = _source_view_maps(folded)
    for transform_label, transformed, inverse_fn in (
        ("reversed", text[::-1], lambda s: s[::-1]),
        ("rot13", codecs.decode(text, "rot_13"), lambda s: codecs.decode(s, "rot_13")),
    ):
        if transformed != text:
            folded_transformed = _scan_fold(transformed)
            transform_prefix = f"{source}: {relative.as_posix()}{view_label}({transform_label})"
            for label, pattern in SECRET_PATTERNS.items():
                if any(
                    not _transform_word_suppressed(
                        match.group(0), inverse_fn, text
                    )
                    for match in pattern.finditer(transformed)
                ) or any(
                    not _transform_word_suppressed(
                        match.group(0), inverse_fn, folded
                    )
                    for match in pattern.finditer(folded_transformed)
                ):
                    issues.append(f"{label} pattern: {transform_prefix}")
            for label, pattern in CONTROLLED_TEXT_PATTERNS.items():
                if any(
                    not _transform_word_suppressed(
                        match.group(0), inverse_fn, text
                    )
                    for match in pattern.finditer(transformed)
                ) or any(
                    not _transform_word_suppressed(
                        match.group(0), inverse_fn, folded
                    )
                    for match in pattern.finditer(folded_transformed)
                ):
                    issues.append(f"{label}: {transform_prefix}")
            flagged_hpo = {
                match.group(0)
                for match in HPO_PATTERN.finditer(folded_transformed)
                if not _transform_word_suppressed(
                    match.group(0), inverse_fn, folded
                )
            }
            if len(flagged_hpo) >= 3:
                issues.append(
                    "possible subject phenotype bundle (3+ HPO terms): "
                    + transform_prefix
                )
            issues.extend(
                _inspect_publication_text(
                    relative,
                    folded_transformed,
                    source,
                    allow_released_biology=allow_released_biology,
                    view_label=view_label + f"({transform_label})",
                    transform_context=(
                        folded,
                        inverse_fn,
                        source_spans,
                        source_views,
                    ),
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
        # A token shaped like a credential does not stop being one because
        # it names a file — secrets ride path stems too, forwards or
        # transformed.
        stem_views = {folded, folded[::-1], codecs.decode(folded, "rot_13")}
        for label, pattern in SECRET_PATTERNS.items():
            if any(pattern.search(view) for view in stem_views):
                issues.append(f"{label} pattern in path: {prefix}")
        # A carrier-encoded identifier in a filename stem decodes to text;
        # every carrier gets an attempt, including punctuation-joined
        # fragments, since the path itself can carry the smuggle.
        for token, carrier, _primary, _short in _decode_candidates(folded):
            try:
                decoded = _decode_carrier(token, carrier)
            except (MemoryError, OverflowError, ValueError):
                decoded = None
            if decoded is None:
                continue
            payload = _printable_payload_text(decoded)
            if payload is None:
                payload = _decode_utf16_or_32(decoded)
            if payload is None:
                payload = _decompress_payload(decoded)
            if payload is None:
                # A filename carrying binary decodes still yields its
                # printable runs — a glued accession inside must surface.
                runs = re.findall(rb"[ -~]{3,}", decoded)
                joined = b" ".join(runs).decode("ascii", "ignore")
                for label, pattern in (
                    *EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                    *GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS.items(),
                ):
                    if pattern.search(joined):
                        issues.append(
                            f"{carrier}-embedded {label} in path: {prefix}"
                        )
                        break
                continue
            folded_payload = _scan_fold(payload)
            stem_identifiers = set(
                QUOTED_UPPER_IDENTIFIER_PATTERN.findall(folded_payload)
            )
            stem_identifiers.update(
                GENE_LIKE_TOKEN_PATTERN.findall(folded_payload)
            )
            for identifier in sorted(stem_identifiers):
                if not _public_identifier_allowed(identifier, relative):
                    issues.append(
                        f"{carrier}-embedded identifier {identifier!r} "
                        f"in path: {prefix}"
                    )
            for label, pattern in EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
                if pattern.search(folded_payload):
                    issues.append(
                        f"{carrier}-embedded {label} in path: {prefix}"
                    )
        # A stem can smuggle an identifier written backwards or rot13'd —
        # the transform view shows it in readable order and the inverse
        # must still be discharged in the raw stem.
        for transform_label, transformed, inverse_fn in (
            ("reversed", folded[::-1], lambda s: s[::-1]),
            (
                "rot13",
                codecs.decode(folded, "rot_13"),
                lambda s: codecs.decode(s, "rot_13"),
            ),
        ):
            if transformed == folded:
                continue
            context = (folded, inverse_fn, [], _source_view_maps(folded))
            gene_identifiers = set(
                QUOTED_UPPER_IDENTIFIER_PATTERN.findall(transformed)
            )
            gene_identifiers.update(
                GENE_LIKE_TOKEN_PATTERN.findall(transformed)
            )
            for identifier in sorted(gene_identifiers):
                if _public_identifier_allowed(identifier, relative):
                    continue
                if _transform_artifact_suppressed(
                    identifier, context, relative, weak=True
                ):
                    continue
                issues.append(
                    f"non-synthetic biological identifier {identifier!r} "
                    f"in path ({transform_label}): {prefix}"
                )
            for label, pattern in {
                **GLUED_BIOLOGICAL_IDENTIFIER_PATTERNS,
                **EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS,
            }.items():
                if label == "subject identifier":
                    continue
                for match in pattern.finditer(transformed):
                    identifier = match.group(0)
                    if _public_identifier_allowed(identifier, relative):
                        continue
                    if _transform_artifact_suppressed(
                        identifier, context, relative
                    ):
                        continue
                    issues.append(
                        f"{label} in path ({transform_label}): {prefix}"
                    )
                    break
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

    # A UTF-8 BOM must not defeat start-anchored payload-shape checks.
    data_check = data[3:] if data.startswith(b"\xef\xbb\xbf") else data

    for signature, label in MAGIC_SIGNATURES:
        if data_check.startswith(signature):
            issues.append(f"{label}: {prefix}")
            return issues

    if data_check.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff", b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data_check:
        issues.append(
            "non-UTF-8 encoded or binary content requiring offline review: "
            + prefix
        )
        return issues

    for signature, label in MAGIC_SIGNATURES:
        if any(byte > 0x7E or byte < 0x09 for byte in signature) and signature in data_check:
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

    try:
        text = data_check.decode("utf-8")
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
                issues.append(
                    f"staged blob could not be read: Git index: {relative.as_posix()}"
                )
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

    # Ref names and author/committer identities are publication surfaces too
    # — a branch named after an accession or a forged author field leaks
    # without ever touching a blob.
    ref_names = _git(root, "for-each-ref", "--format=%(refname)")
    if ref_names.returncode == 0:
        for line in ref_names.stdout.splitlines():
            try:
                text = line.decode("utf-8").strip()
            except UnicodeDecodeError:
                issues.append(
                    "non-UTF-8 Git ref name requiring offline review"
                )
                continue
            if text:
                issues.extend(
                    _inspect_payload_text(
                        PurePosixPath("<git-ref-name>"),
                        text,
                        "Git history",
                    )
                )
    identities = _git(
        root, "log", "--all", "--format=%an%x00%ae%x00%cn%x00%ce%x00--%x00"
    )
    if identities.returncode == 0:
        for field in identities.stdout.split(b"\x00"):
            field = field.strip()
            if not field or field == b"--":
                continue
            try:
                text = field.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(
                    "non-UTF-8 Git author/committer identity requiring "
                    "offline review"
                )
                continue
            issues.extend(
                _inspect_payload_text(
                    PurePosixPath("<git-identity>"),
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
