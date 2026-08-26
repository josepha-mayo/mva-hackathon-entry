"""Fail closed when controlled data or credentials appear in a public tree.

The gate inspects the working tree, staged Git blobs that differ from disk, and
every reachable historical Git blob. It is deliberately conservative: opaque
archives and binary documents require an explicit offline review before they
can be added to the public repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.submission import SubmissionError, load_predictions_bytes

MAX_PUBLIC_BYTES = 10 * 1024 * 1024

RELEASE_MANIFEST_PATH = PurePosixPath("release/release-artifacts.json")
RELEASE_MANIFEST_SCHEMA = "mva-public-release-quarantine/v1"
RELEASE_ARTIFACT_PATHS = {
    "track1_submission_csv": PurePosixPath(
        "submissions/track1/josephmayo_track1_bub1b_pair.csv"
    ),
    "track1_methods_report": PurePosixPath("reports/josephmayo_track1_report.md"),
}
RELEASE_MANIFEST_TOP_LEVEL_KEYS = frozenset({"schema", "artifacts"})
RELEASE_MANIFEST_ARTIFACT_KEYS = frozenset(
    {"role", "path", "status", "sha256"}
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

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
HPO_PATTERN = re.compile(r"\bHP:\d{7}\b")

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

# These are public interface or implementation tokens, not biological claims.
# Synthetic biological fixtures are separately admitted only through the SYN
# namespace, making an accidental real-looking identifier fail closed.
PUBLIC_TECHNICAL_IDENTIFIER_ALLOWLIST = frozenset(
    {
        "BOM", "BWA-MEM2", "CC-BY-4", "CC0-1", "COPY", "GT", "HEAD",
        "ISO-8601", "MT", "NFC", "NTFS", "PAR1", "PAR2", "PROBAND01",
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", "SHA-256", "SHA256",
        "TEMP", "TMP", "UTF-8",
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
        r"(?<![A-Za-z0-9_])(?:c|g|m|n|p|r)\."
        r"(?:[A-Z][a-z]{2}|[-*?0-9])[^\s`,;)]*\d[^\s`,;)]*"
    ),
    "dbSNP-like identifier": re.compile(r"\brs\d{3,}\b", re.IGNORECASE),
    "genomic coordinate": re.compile(
        r"\b(?:chr)?(?:[1-9]|1\d|2[0-2]|X|Y|M|MT):\d{4,}\b",
        re.IGNORECASE,
    ),
}
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
        PurePosixPath(".venv"),
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


RELEASE_ROLE_VALIDATORS: dict[str, Callable[[bytes], list[str]]] = {
    "track1_submission_csv": _validate_track1_release_csv,
    "track1_methods_report": _validate_track1_release_report,
}


def _validate_release_manifest(
    manifest_data: bytes | None,
    load_artifact: Callable[[PurePosixPath], bytes | None],
    source: str,
) -> tuple[dict[PurePosixPath, str], list[str]]:
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
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            details.append("manifest is not strict duplicate-free UTF-8 JSON")
        else:
            if not isinstance(manifest, dict):
                details.append("manifest root must be an object")
            elif set(manifest) != RELEASE_MANIFEST_TOP_LEVEL_KEYS:
                details.append("manifest root has missing or surplus keys")
            elif manifest.get("schema") != RELEASE_MANIFEST_SCHEMA:
                details.append("manifest schema is not the supported fixed version")
            elif not isinstance(manifest.get("artifacts"), list):
                details.append("manifest artifacts must be a list")
            else:
                artifacts = manifest["artifacts"]
                if len(artifacts) != len(RELEASE_ARTIFACT_PATHS):
                    details.append("manifest must declare exactly the fixed release artifacts")

                seen_roles: set[str] = set()
                seen_paths: set[str] = set()
                provisional: dict[PurePosixPath, str] = {}
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
                    if not isinstance(role, str) or role not in RELEASE_ARTIFACT_PATHS:
                        details.append(f"{label} has an unknown release role")
                        continue
                    if role in seen_roles:
                        details.append(f"{label} duplicates a release role")
                    seen_roles.add(role)

                    expected_path = RELEASE_ARTIFACT_PATHS[role]
                    if not isinstance(path_text, str) or path_text != expected_path.as_posix():
                        details.append(f"{label} does not use the role's fixed path and extension")
                        continue
                    if path_text in seen_paths:
                        details.append(f"{label} duplicates a release path")
                    seen_paths.add(path_text)

                    if status not in {"planned", "released"}:
                        details.append(f"{label} status must be planned or released")
                        continue
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
                    validation_issues = RELEASE_ROLE_VALIDATORS[role](artifact_data)
                    if validation_issues:
                        details.extend(f"{label}: {issue}" for issue in validation_issues)
                        continue
                    provisional[expected_path] = role

                missing_roles = set(RELEASE_ARTIFACT_PATHS) - seen_roles
                if missing_roles:
                    details.append("manifest is missing one or more fixed release roles")

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
    if identifier in PUBLIC_PATH_TECHNICAL_IDENTIFIER_ALLOWLIST.get(relative, frozenset()):
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
) -> list[str]:
    if relative in PUBLICATION_POLICY_PATH_ALLOWLIST:
        return []

    issues: list[str] = []
    prefix = f"{source}: {relative.as_posix()}"
    if not allow_released_biology:
        identifiers: set[str] = set()
        identifiers.update(QUOTED_UPPER_IDENTIFIER_PATTERN.findall(text))
        identifiers.update(GENE_LIKE_TOKEN_PATTERN.findall(text))
        for pattern in BIOLOGICAL_CONTEXT_PATTERNS:
            identifiers.update(pattern.findall(text))
        for identifier in sorted(identifiers):
            if not _public_identifier_allowed(identifier, relative):
                issues.append(
                    f"non-synthetic biological identifier {identifier!r}: {prefix}"
                )

        for label, pattern in EXACT_BIOLOGICAL_IDENTIFIER_PATTERNS.items():
            if pattern.search(text):
                issues.append(f"{label}: {prefix}")
    if relative not in OPERATIONAL_RECEIPT_PATH_ALLOWLIST:
        for label, pattern in OPERATIONAL_RECEIPT_PATTERNS.items():
            if pattern.search(text):
                issues.append(f"{label}: {prefix}")
    return issues


def _inspect_bytes(
    relative: PurePosixPath,
    data: bytes,
    source: str,
    *,
    released_role: str | None = None,
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

    text = data.decode("utf-8", errors="ignore")
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            issues.append(f"{label} pattern: {prefix}")
    for label, pattern in CONTROLLED_TEXT_PATTERNS.items():
        if pattern.search(text):
            issues.append(f"{label}: {prefix}")
    if len(set(HPO_PATTERN.findall(text))) >= 3:
        issues.append(f"possible subject phenotype bundle (3+ HPO terms): {prefix}")
    issues.extend(
        _inspect_publication_text(
            relative,
            text,
            source,
            allow_released_biology=released_role is not None,
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


def _git_findings(root: Path) -> list[str]:
    if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return []

    issues: list[str] = []

    def load_index_artifact(relative: PurePosixPath) -> bytes | None:
        return _git_file(root, f":{relative.as_posix()}")

    index_manifest = load_index_artifact(RELEASE_MANIFEST_PATH)
    index_allowances, index_manifest_issues = _validate_release_manifest(
        index_manifest,
        load_index_artifact,
        "Git index",
    )
    issues.extend(index_manifest_issues)

    indexed = _git(root, "ls-files", "--cached", "-z")
    if indexed.returncode == 0:
        for raw_path in filter(None, indexed.stdout.split(b"\x00")):
            path_text = raw_path.decode("utf-8", errors="surrogateescape")
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
                    released_role=index_allowances.get(relative),
                )
            )

    commits = _git(root, "rev-list", "--all")
    seen_history_blobs: set[tuple[str, str, str | None]] = set()
    if commits.returncode == 0:
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
            )
            issues.extend(commit_issues)

            tree = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit)
            if tree.returncode != 0:
                continue
            for raw_entry in filter(None, tree.stdout.split(b"\x00")):
                fields = raw_entry.split(b"\t", 1)
                if len(fields) != 2:
                    continue
                metadata = fields[0].split()
                if len(metadata) != 3 or metadata[1] != b"blob":
                    continue
                object_id = metadata[2].decode("ascii", errors="ignore")
                path_text = fields[1].decode("utf-8", errors="surrogateescape")
                relative = PurePosixPath(path_text)
                role = commit_allowances.get(relative)
                path_object_role = (path_text, object_id, role)
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
                            released_role=role,
                        )
                    )
    return issues


def findings(root: Path, *, include_git: bool = True) -> list[str]:
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
                    released_role=working_allowances.get(relative),
                )
            )
    if include_git:
        issues.extend(_git_findings(root))
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument(
        "--no-git", action="store_true",
        help="scan only files on disk (unsafe for pre-publication review)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    issues = findings(root, include_git=not args.no_git)
    if issues:
        print("NO-GO: privacy gate failed")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("GO: privacy gate passed (working tree, Git index, and reachable history)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
