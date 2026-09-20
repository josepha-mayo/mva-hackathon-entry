"""Report GO/NO-GO for each submission blocker.

This checker verifies every blocker that is machine-checkable and prints the
exact evidence artifact required for each blocker that is not. A green run of
this script is a *necessary* condition for submission, never sufficient on its
own — human authorization and external attestation are judgment calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.reproducibility import (  # noqa: E402
    MANIFEST_PATH,
    MAX_ARTIFACT_BYTES,
    validate_manifest_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# External evidence the package cannot produce for itself. Each tuple is
# (id, relative path, what the artifact must attest).
REQUIRED_ATTESTATION = (
    (
        "signature",
        "attestation/release-signature.asc",
        "a detached signature over release/release-artifacts.json bytes",
    ),
    (
        "timestamp",
        "attestation/timestamp-proof.json",
        "an external timestamp/registry receipt binding the release manifest digest",
    ),
    (
        "authorization",
        "attestation/operator-authorization.md",
        "the named operator's explicit authorization to freeze and submit",
    ),
    (
        "participant_data",
        "attestation/participant-data-authorization.md",
        "authorization + data-handling status for participant-derived material",
    ),
    (
        "privacy_review",
        "attestation/privacy-review.md",
        "signed offline review of the privacy-gate findings",
    ),
)


def _check(label: str, ok: bool, detail: str) -> dict:
    return {"item": label, "go": bool(ok), "detail": detail}


class _MalformedJson(ValueError):
    pass


def _reject_duplicate_keys(pairs: list) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise _MalformedJson(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _MalformedJson(f"non-finite JSON number: {value}")


def _git_clean(root: Path) -> dict:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return _check("git_worktree", False, f"cannot run git: {exc}")
    if completed.returncode != 0:
        return _check("git_worktree", False, "root is not a readable Git worktree")
    dirty = [line for line in completed.stdout.splitlines() if line.strip()]
    return _check(
        "git_worktree",
        not dirty,
        "clean" if not dirty else f"{len(dirty)} uncommitted path(s)",
    )


def _reproducibility_manifest(root: Path) -> dict:
    manifest_path = root.joinpath(*MANIFEST_PATH.parts)
    if not manifest_path.is_file():
        return _check("reproducibility_manifest", False, f"{MANIFEST_PATH.as_posix()} missing")
    try:
        if manifest_path.stat().st_size > 16 * 1024 * 1024:
            return _check("reproducibility_manifest", False, "exceeds the byte ceiling")
        with manifest_path.open("rb") as handle:
            data = handle.read(16 * 1024 * 1024 + 1)
    except OSError as exc:
        return _check("reproducibility_manifest", False, f"unreadable: {exc}")

    def load_artifact(path):
        try:
            target = root.joinpath(*path.parts)
            if target.is_symlink() or os.path.isjunction(target):
                return None
            resolved = target.resolve()
            if resolved != root and not resolved.is_relative_to(root):
                return None
            with resolved.open("rb") as handle:
                return handle.read(MAX_ARTIFACT_BYTES + 1)
        except (OSError, RuntimeError, ValueError):
            # resolve() raises RuntimeError on a symlink loop; a NUL byte in a
            # component raises ValueError — both mean "unreadable".
            return None

    issues = validate_manifest_bytes(data, load_artifact)
    return _check(
        "reproducibility_manifest",
        not issues,
        "all bound digests match" if not issues else "; ".join(issues[:3]),
    )


def _release_manifest(root: Path) -> dict:
    """Every released artifact's recorded digest must match on-disk bytes.

    The release manifest is what the signature and timestamp attestations
    bind — a stale digest inside it would be signed into evidence.
    """

    manifest_path = root / "release" / "release-artifacts.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return _check("release_manifest", False, "release/release-artifacts.json missing")
    try:
        with manifest_path.open("rb") as handle:
            data = handle.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024:
            return _check("release_manifest", False, "exceeds the byte ceiling")
        manifest = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, json.JSONDecodeError, UnicodeError, RecursionError, _MalformedJson) as exc:
        return _check("release_manifest", False, f"unreadable: {exc}")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), list):
        return _check("release_manifest", False, "malformed release manifest")
    if manifest.get("schema") not in {
        "mva-public-release-quarantine/v1",
        "mva-public-release-quarantine/v2",
        "mva-public-release-quarantine/v3",
        "mva-public-release-quarantine/v4",
    }:
        return _check("release_manifest", False, "unknown release manifest schema")

    stale: list[str] = []
    released = 0
    for entry in manifest["artifacts"]:
        if not isinstance(entry, dict):
            stale.append("non-object artifact entry")
            continue
        status = entry.get("status")
        if status == "planned":
            # "planned" must mean nothing exists to verify — a null digest
            # and no file on disk. A present file demoted to "planned" would
            # otherwise escape every digest check below.
            role = entry.get("role")
            relative = entry.get("path")
            path_ok = (
                isinstance(relative, str)
                and "\\" not in relative
                and "\x00" not in relative
                and all(
                    part not in {"", ".", ".."} and ":" not in part
                    for part in relative.split("/")
                )
            )
            if (
                entry.get("sha256") is not None
                or not path_ok
                or root.joinpath(*relative.split("/")).exists()
            ):
                stale.append(str(role))
            continue
        if status != "released":
            stale.append(str(entry.get("role")))
            continue
        released += 1
        role = entry.get("role")
        recorded = entry.get("sha256")
        relative = entry.get("path")
        if (
            not isinstance(role, str)
            or not isinstance(recorded, str)
            or not isinstance(relative, str)
            or "\\" in relative
            or "\x00" in relative
            or any(
                part in {"", ".", ".."} or ":" in part
                for part in relative.split("/")
            )
        ):
            stale.append(str(role))
            continue
        target = root.joinpath(*relative.split("/"))
        try:
            if target.is_symlink() or os.path.isjunction(target):
                stale.append(role)
                continue
            resolved = target.resolve()
            if resolved != root and not resolved.is_relative_to(root):
                stale.append(role)
                continue
            with resolved.open("rb") as handle:
                data = handle.read(MAX_ARTIFACT_BYTES + 1)
        except (OSError, RuntimeError, ValueError):
            # RuntimeError: symlink loop in resolve(); ValueError: embedded NUL
            # in a path component — both mean "unreadable".
            stale.append(role)
            continue
        if len(data) > MAX_ARTIFACT_BYTES or hashlib.sha256(data).hexdigest() != recorded:
            stale.append(role)
    if released == 0:
        return _check("release_manifest", False, "no released artifacts declared")
    return _check(
        "release_manifest",
        not stale,
        f"{released} released artifact digest(s) verified"
        if not stale
        else "stale or unreadable: " + ", ".join(stale[:5]),
    )


def _attestation(root: Path) -> list[dict]:
    checks = []
    for label, relative, description in REQUIRED_ATTESTATION:
        path = root / relative
        present = path.is_file() and not path.is_symlink()
        checks.append(
            _check(
                f"attestation:{label}",
                present,
                f"{relative} present" if present else f"missing — requires {description}",
            )
        )
    return checks


def _privacy_gate(root: Path) -> dict:
    """Actually execute the privacy gate — a signed attestation over stale
    or never-computed findings must not count."""
    script = root / "scripts" / "privacy_gate.py"
    if not script.is_file():
        return _check("privacy_gate", False, "scripts/privacy_gate.py missing")
    try:
        completed = subprocess.run(
            [sys.executable, str(script), "."],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _check("privacy_gate", False, f"cannot run privacy gate: {exc}")
    if completed.returncode == 0:
        return _check("privacy_gate", True, "privacy gate passed")
    findings = [
        line for line in completed.stdout.splitlines() if line.strip().startswith("-")
    ]
    detail = findings[0] if findings else completed.stdout.strip().splitlines()[-1:]
    return _check(
        "privacy_gate",
        False,
        f"exit {completed.returncode}: "
        + (detail[0] if isinstance(detail, list) and detail else str(detail)),
    )


def _ai_disclosure(root: Path) -> dict:
    """The judged report's methods section must record provider, plan/tier,
    and data-handling for every materially contributing AI assistant —
    Cursor, Codex, and Devin per the competition contract."""
    report = root / "reports" / "josephmayo_track2_report.md"
    try:
        text = report.read_text(encoding="utf-8")
    except OSError as exc:
        return _check("ai_disclosure", False, f"report unreadable: {exc}")
    required = (
        "Cursor",
        "Ultra",
        "Grok 4.6",
        "privacy mode",
        "Codex",
        "ChatGPT Pro",
        "GPT-5.6 Sol",
        "Devin",
        "SWE-2 Max",
        "data-handling",
    )
    missing = [token for token in required if token not in text]
    return _check(
        "ai_disclosure",
        not missing,
        "provider/plan/data-handling fields present for Cursor, Codex, Devin"
        if not missing
        else "missing disclosure fields: " + ", ".join(missing),
    )


def _doc_consistency(root: Path) -> dict:
    """Judge-facing documents must state the same save-path lattice size the
    code declares — a stale scenario count is a credibility finding."""
    source = root / "src" / "mva_hackathon" / "save_path.py"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        return _check("doc_consistency", False, f"save_path.py unreadable: {exc}")

    match = re.search(r"EXPECTED_FALSE_PATHS\s*=\s*(\d+)", text)
    if match is None:
        return _check(
            "doc_consistency",
            False,
            "EXPECTED_FALSE_PATHS not found in save_path.py",
        )
    n = int(match.group(1))
    needle = f"{n}/{n}"
    stale: list[str] = []
    for relative in (
        "reports/TRACK2_PROGRAM_GATES.md",
        "reports/TRACK2_JUDGE_RUBRIC.md",
        "templates/community/README.md",
    ):
        try:
            doc = (root / relative).read_text(encoding="utf-8")
        except OSError:
            stale.append(f"{relative} unreadable")
            continue
        if needle not in doc:
            stale.append(relative)
    return _check(
        "doc_consistency",
        not stale,
        f"save-path totals consistent ({needle})"
        if not stale
        else f"docs missing current {needle} claim: " + ", ".join(stale),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=REPO_ROOT, type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable checklist instead of the text table",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve()

    checks = [
        _git_clean(root),
        _reproducibility_manifest(root),
        _release_manifest(root),
        _privacy_gate(root),
        _ai_disclosure(root),
        _doc_consistency(root),
        *_attestation(root),
    ]
    overall = all(check["go"] for check in checks)
    if arguments.json:
        print(
            json.dumps(
                {"schema": "mva-submission-go-check/v1", "go": overall, "checks": checks},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for check in checks:
            mark = "GO" if check["go"] else "NO-GO"
            print(f"[{mark:>5}] {check['item']}: {check['detail']}")
        print(
            "overall: GO" if overall else "overall: NO-GO — external blockers remain"
        )
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
