from __future__ import annotations

import argparse
import hashlib
import json
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


def build_manifest(root: Path, source_commit: str) -> bytes:
    """Build and validate a byte-level manifest without writing it."""

    if COMMIT_PATTERN.fullmatch(source_commit) is None:
        raise ValueError("source commit must be lowercase 40-character Git hex")
    if _git_head(root) != source_commit:
        raise ValueError("source commit must equal the current Git HEAD")

    artifacts: list[dict[str, str]] = []
    artifact_bytes: dict[PurePosixPath, bytes] = {}
    for role, relative_path in ARTIFACT_PATHS.items():
        path = root.joinpath(*relative_path.parts)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ValueError(
                f"cannot bind {relative_path.as_posix()}: {exc}"
            ) from exc
        artifact_bytes[relative_path] = data
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
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    issues = validate_manifest_bytes(encoded, artifact_bytes.get)
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
    print(f"created {MANIFEST_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
