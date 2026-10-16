from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

import mva_hackathon  # noqa: E402
from mva_hackathon.reproducibility import (  # noqa: E402
    MANIFEST_PATH,
    validate_manifest_bytes,
)

if not Path(mva_hackathon.__file__).resolve().is_relative_to(
    SOURCE_ROOT.resolve()
):
    raise SystemExit(
        "mva_hackathon resolved outside the repository source root; "
        "refusing to verify with a shadowed package"
    )


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(arguments, 127, "", "git unavailable")


def _verify_git_provenance(root: Path, manifest_data: bytes) -> list[str]:
    """Independently verify the receipt's commit and clean-worktree claims.

    ``validate_manifest_bytes`` only checks that the receipt's declared values
    are internally consistent. These checks confirm the declared commit really
    exists in this repository's history and that no tracked file has been
    modified since checkout.
    """

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"non-finite JSON number {value!r}")
        return parsed

    def strict_object(pairs: list) -> dict:
        result: dict = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = item
        return result

    try:
        manifest = json.loads(
            manifest_data,
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (ValueError, UnicodeDecodeError):
        return []
    declared = manifest.get("source_commit") if isinstance(manifest, dict) else None
    if not isinstance(declared, str):
        return []

    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return [
            "cannot verify manifest source_commit: verification root is not "
            "inside a git worktree"
        ]

    issues: list[str] = []
    exists = _git(root, "cat-file", "-e", f"{declared}^{{commit}}")
    if exists.returncode != 0:
        issues.append(
            "manifest source_commit does not resolve to a commit in this repository"
        )
    else:
        head = _git(root, "rev-parse", "HEAD")
        if head.returncode == 0:
            ancestor = _git(
                root, "merge-base", "--is-ancestor", declared, head.stdout.strip()
            )
            if ancestor.returncode != 0:
                issues.append(
                    "manifest source_commit is not an ancestor of the checked-out HEAD"
                )
        else:
            issues.append("cannot read git HEAD to anchor manifest source_commit")

    status = _git(root, "status", "--porcelain")
    if status.returncode != 0:
        issues.append("cannot check worktree cleanliness")
    elif status.stdout.strip():
        issues.append(
            "worktree has modifications or untracked files; the receipt's "
            "clean-worktree claim cannot be reproduced at verification time"
        )
    flags = _git(root, "ls-files", "-v")
    if flags.returncode != 0:
        issues.append("cannot check index assume-unchanged/skip-worktree flags")
    elif any(
        line[:1].islower() or line.startswith("S") for line in flags.stdout.splitlines()
    ):
        issues.append(
            "index carries assume-unchanged or skip-worktree flags; "
            "worktree bytes cannot be trusted against the receipt"
        )
    return issues


# Frozen commands whose committed receipts --reexecute regenerates and diffs.
# Provenance fields legitimately differ between minting commit and verify-time
# HEAD, so the comparison strips them and compares the result payload only.
_REEXECUTE_COMMANDS: list[tuple[PurePosixPath, list[str]]] = [
    (
        PurePosixPath("reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json"),
        [
            "scripts/run_generation_selection_benchmark.py",
            "--config",
            "configs/track2-generation-selection-benchmark.json",
        ],
    ),
    (
        PurePosixPath("reports/TRACK2_SEED_SENSITIVITY.json"),
        [
            "scripts/run_seed_sensitivity.py",
            "--config",
            "configs/track2-seed-sensitivity.json",
        ],
    ),
    (
        PurePosixPath("reports/TRACK2_SAVE_PATH_MATRIX.json"),
        ["scripts/run_save_path_simulation.py"],
    ),
    (
        PurePosixPath("reports/TRACK2_LINEAGE_ADVERSARIAL.json"),
        ["scripts/run_lineage_adversarial_benchmark.py"],
    ),
]

_VOLATILE_KEYS = {"runtime_receipt", "receipt_sha256", "generated_at"}


def _strip_volatile(node: object) -> object:
    if isinstance(node, dict):
        return {
            key: _strip_volatile(value)
            for key, value in node.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(node, list):
        return [_strip_volatile(item) for item in node]
    return node


def _diff_keys(a: object, b: object, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        diffs = []
        for key in sorted(set(a) | set(b)):
            diffs.extend(_diff_keys(a.get(key), b.get(key), f"{path}.{key}"))
        return diffs
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path} (length {len(a)} != {len(b)})"]
        diffs = []
        for index, (x, y) in enumerate(zip(a, b)):
            diffs.extend(_diff_keys(x, y, f"{path}[{index}]"))
            if len(diffs) > 10:
                return diffs + [f"{path}[...] (further diffs truncated)"]
        return diffs
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def _reexecute(root: Path) -> list[str]:
    """Re-run the frozen commands and diff regenerated receipts against the
    committed ones. This converts "self-consistent bytes" into "verified
    computation" — the trust-boundary gap reviewers flagged."""
    issues: list[str] = []
    for receipt_path, command in _REEXECUTE_COMMANDS:
        committed_path = root.joinpath(*receipt_path.parts)
        try:
            committed = json.loads(committed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"{receipt_path.as_posix()}: cannot load committed receipt ({exc})")
            continue
        with tempfile.TemporaryDirectory(prefix="mva-reexec-") as tmp:
            output_path = Path(tmp) / "receipt.json"
            run = subprocess.run(
                [
                    sys.executable,
                    str(root.joinpath(command[0])),
                    *command[1:],
                    "--output",
                    str(output_path),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if run.returncode != 0:
                issues.append(
                    f"{receipt_path.as_posix()}: frozen command failed "
                    f"(exit {run.returncode}): {run.stderr.strip()[-400:]}"
                )
                continue
            try:
                fresh = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                issues.append(f"{receipt_path.as_posix()}: cannot load regenerated receipt ({exc})")
                continue
        diffs = _diff_keys(_strip_volatile(committed), _strip_volatile(fresh))
        if diffs:
            issues.append(
                f"{receipt_path.as_posix()}: regenerated receipt diverges "
                f"({len(diffs)} diff(s); first: {diffs[0]})"
            )
        else:
            print(f"re-executed: {receipt_path.as_posix()} — payload identical")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify every byte in the receipt-bound Track 2 evidence chain."
    )
    parser.add_argument("root", nargs="?", default=Path.cwd(), type=Path)
    parser.add_argument(
        "--reexecute",
        action="store_true",
        help="also re-run the frozen benchmark/save-path commands and diff "
        "the regenerated receipts against the committed ones (slow)",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    manifest_path = root.joinpath(*MANIFEST_PATH.parts)
    if manifest_path.is_symlink() or os.path.isjunction(manifest_path):
        parser.error(f"{MANIFEST_PATH.as_posix()} is a link, not a regular file")
    try:
        # Bounded reads — a hostile manifest or artifact is rejected before
        # it can exhaust memory.
        with manifest_path.open("rb") as handle:
            manifest_data = handle.read(16 * 1024 * 1024 + 1)
        if len(manifest_data) > 16 * 1024 * 1024:
            parser.error(f"{MANIFEST_PATH.as_posix()} exceeds the byte ceiling")
    except OSError as exc:
        parser.error(f"cannot read {MANIFEST_PATH.as_posix()}: {exc}")

    def load_artifact(path: PurePosixPath) -> bytes | None:
        try:
            target = root.joinpath(*path.parts)
            if target.is_symlink() or os.path.isjunction(target):
                return None
            resolved = target.resolve()
            if resolved != root and not resolved.is_relative_to(root):
                return None
            with resolved.open("rb") as handle:
                return handle.read(256 * 1024 * 1024 + 1)
        except (OSError, RuntimeError, ValueError):
            return None

    issues = validate_manifest_bytes(manifest_data, load_artifact)
    issues += _verify_git_provenance(root, manifest_data)
    if arguments.reexecute and not issues:
        issues += _reexecute(root)
    if issues:
        for issue in issues:
            print(f"NO-GO: {issue}")
        return 1
    print("GO: Track 2 report, pitch, code, tests, configuration, and receipt match")
    print(
        "scope: digest, receipt, and provenance validation only; the frozen "
        "commands were not re-executed"
        if not arguments.reexecute
        else "scope: digest, receipt, provenance, and re-execution of the "
        "frozen commands"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
