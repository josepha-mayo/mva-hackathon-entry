"""Plan or fetch the minimum gated artifacts into an explicit private root.

The default mode is read-only and prints a metadata plan. ``--apply`` is
required before any download starts. Raw FASTQs are intentionally unsupported
here; add them only after variant-level analysis establishes a concrete need.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from huggingface_hub import get_hf_file_metadata, hf_hub_download, hf_hub_url
from storage_preflight import preflight

DATASET_ID = "SageBio/mva-hackathon-2026-data"
DATASET_REVISION = "f534cb0c1a607110c6dad0194299bd3dd62df542"
MINIMUM_FILES = (
    ("public dataset card", "README.md"),
    ("controlled clinical phenotype", "Challenge_Clinical_Phenotype_1.docx"),
    ("controlled compressed VCF", "WGS_EX2312012_HGWCNDSX7.vcf.gz"),
    ("controlled VCF index", "WGS_EX2312012_HGWCNDSX7.vcf.gz.tbi"),
)


def format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.2f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def private_root(value: str | None) -> Path:
    if not value:
        raise ValueError("set MVA_PRIVATE_ROOT or pass --root")
    root = Path(value).expanduser().resolve()
    public_repo = Path(__file__).resolve().parents[1]
    if root == public_repo or root.is_relative_to(public_repo):
        raise ValueError("private root must be outside the public repository")
    if root == Path(root.anchor):
        raise ValueError("private root cannot be a drive/filesystem root")
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.environ.get("MVA_PRIVATE_ROOT"))
    parser.add_argument("--apply", action="store_true", help="perform the planned download")
    args = parser.parse_args()

    try:
        root = private_root(args.root)
    except ValueError as exc:
        print(f"NO-GO: {exc}")
        return 2

    storage = preflight(root, "minimal")
    if not storage.ok:
        print("NO-GO: controlled-storage preflight failed; no Hub payload request was made.")
        for issue in storage.issues:
            print(f"- {issue}")
        return 4

    total = 0
    for role, filename in MINIMUM_FILES:
        try:
            url = hf_hub_url(
                DATASET_ID, filename, repo_type="dataset", revision=DATASET_REVISION,
            )
            metadata = get_hf_file_metadata(url, token=True)
        except Exception as exc:
            print(f"NO-GO: cannot access {role} ({type(exc).__name__}).")
            return 3
        if metadata.commit_hash != DATASET_REVISION:
            print(f"NO-GO: {role} resolved to an unexpected dataset revision.")
            return 5
        size = metadata.size
        if size is not None:
            total += size
        print(f"- {role}: {format_bytes(size)}")
    print(f"Pinned minimum plan: 4 artifacts, {format_bytes(total)}")

    if not args.apply:
        print("PLAN ONLY: storage and gated metadata checks passed; no payload was downloaded.")
        return 0

    incoming = root / "incoming_ro"
    final = incoming / DATASET_REVISION
    staging = incoming / f".staging-{uuid.uuid4()}"
    cache = root / "hf_home"
    if final.exists():
        print("NO-GO: the pinned minimum artifact set already exists; refusing to overwrite it.")
        return 6
    incoming.mkdir(exist_ok=True)
    staging.mkdir()
    cache.mkdir(exist_ok=True)

    manifest: dict[str, object] = {
        "dataset": DATASET_ID,
        "revision": DATASET_REVISION,
        "downloaded_at_utc": datetime.now(UTC).isoformat(),
        "artifacts": [],
    }
    try:
        for role, filename in MINIMUM_FILES:
            downloaded = Path(
                hf_hub_download(
                    DATASET_ID,
                    filename=filename,
                    repo_type="dataset",
                    revision=DATASET_REVISION,
                    local_dir=staging,
                    cache_dir=cache,
                    token=True,
                )
            )
            if not downloaded.resolve().is_relative_to(staging.resolve()):
                raise RuntimeError("download escaped the private staging directory")
            artifact = {
                "role": role,
                "path": downloaded.relative_to(staging).as_posix(),
                "size": downloaded.stat().st_size,
                "sha256": sha256(downloaded),
            }
            cast_artifacts = manifest["artifacts"]
            assert isinstance(cast_artifacts, list)
            cast_artifacts.append(artifact)
            print(f"downloaded and hashed: {role}")
        (staging / "provenance.private.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
        )
        staging.replace(final)
    except Exception as exc:
        print(
            "NO-GO: minimum download did not complete atomically; the private staging "
            f"directory was preserved for controlled cleanup ({type(exc).__name__})."
        )
        return 7

    print("GO: pinned minimum artifact set was atomically promoted inside the private root.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
