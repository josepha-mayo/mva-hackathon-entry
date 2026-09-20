from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.reproducibility import (  # noqa: E402
    ARTIFACT_PATHS,
    COMMANDS,
    MANIFEST_PATH,
    MAX_ARTIFACT_BYTES,
    SCHEMA,
    validate_manifest_bytes,
)

COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError("root is not a readable Git worktree")
    return completed.stdout.strip()


def _git_blob(root: Path, commit: str, relative: PurePosixPath) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative.as_posix()}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"cannot resolve {relative.as_posix()} at {commit}: not committed"
        )
    return completed.stdout


def build_manifest(root: Path, source_commit: str) -> bytes:
    """Build and validate a byte-level manifest without writing it."""

    # Normalize once: containment checks compare resolve()d targets against
    # this root, so an 8.3/alias/unresolved root would report every artifact
    # as escaping.
    root = root.resolve()
    if COMMIT_PATTERN.fullmatch(source_commit) is None:
        raise ValueError("source commit must be lowercase 40-character Git hex")
    if _git_head(root) != source_commit:
        raise ValueError("source commit must equal the current Git HEAD")

    def read_artifact(relative_path: PurePosixPath) -> bytes:
        target = root.joinpath(*relative_path.parts)
        try:
            if target.is_symlink() or os.path.isjunction(target):
                raise ValueError(
                    f"cannot bind {relative_path.as_posix()}: must be a regular file"
                )
            resolved = target.resolve()
            if resolved != root and not resolved.is_relative_to(root):
                raise ValueError(
                    f"cannot bind {relative_path.as_posix()}: escapes the root"
                )
            with resolved.open("rb") as handle:
                data = handle.read(MAX_ARTIFACT_BYTES + 1)
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                f"cannot bind {relative_path.as_posix()}: {exc}"
            ) from exc
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError(
                f"cannot bind {relative_path.as_posix()}: exceeds the byte ceiling"
            )
        return data

    artifacts: list[dict[str, str]] = []
    for role, relative_path in ARTIFACT_PATHS.items():
        data = read_artifact(relative_path)
        # The recorded digest must equal what a fresh checkout of source_commit
        # produces anywhere. A clean worktree is not byte-identical: autocrlf
        # checkout converts LF blobs to CRLF working bytes, which git reports
        # clean while the raw bytes differ from every LF checkout. Compare
        # against the committed blob so a non-normalized checkout fails here,
        # at mint time, instead of failing verification on another machine.
        # benchmark_receipt is the only self-referential artifact: it embeds
        # git_source_commit == source_commit and is committed in a follow-up
        # commit, so its working bytes cannot match a blob at source_commit.
        # Its anchor is the git_source_commit cross-check in
        # validate_manifest_bytes, not blob equality.
        if role != "benchmark_receipt" and data != _git_blob(
            root, source_commit, relative_path
        ):
            raise ValueError(
                f"cannot bind {relative_path.as_posix()}: working-tree bytes "
                "differ from the committed blob (checkout normalization, e.g. CRLF)"
            )
        artifacts.append(
            {
                "role": role,
                "path": relative_path.as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    manifest = {
        "schema": SCHEMA,
        "source_commit": source_commit,
        "commands": COMMANDS,
        "artifacts": artifacts,
    }
    encoded = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()

    # Re-read each artifact from disk for validation rather than trusting the
    # in-memory copy — a file swapped between the initial read and this check
    # is caught instead of being silently bound.
    def load_artifact(path: PurePosixPath) -> bytes | None:
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
            return None

    issues = validate_manifest_bytes(encoded, load_artifact)
    if issues:
        raise ValueError("manifest validation failed: " + "; ".join(issues))
    return encoded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the fixed Track 2 byte-level reproducibility manifest."
    )
    parser.add_argument("root", nargs="?", default=Path.cwd(), type=Path)
    parser.add_argument("--source-commit", required=True)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    output_path = root.joinpath(*MANIFEST_PATH.parts)
    try:
        manifest = build_manifest(root, arguments.source_commit)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("xb") as stream:
            stream.write(manifest)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - normalize unexpected bugs
        parser.error(f"unexpected error: {exc}")
    print(f"created {MANIFEST_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
