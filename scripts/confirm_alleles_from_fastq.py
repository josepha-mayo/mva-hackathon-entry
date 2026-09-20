from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT / "src"))

from mva_hackathon.allele_confirmation import (  # noqa: E402
    AlleleConfirmationError,
    DEFAULT_EXPECTED_N_FILES,
    PINNED_FASTQ_NAME_DIGEST,
    assess_fastq_layout,
    confirm_from_fastq_paths,
)

FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AlleleConfirmationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise AlleleConfirmationError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise AlleleConfirmationError(f"non-finite JSON number: {value}")
    return parsed


def _outside_repo(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == SOURCE_ROOT or resolved.is_relative_to(SOURCE_ROOT):
        raise AlleleConfirmationError(
            "confirmation inputs must stay outside the public repository"
        )


def collect_fastq_files(directory: Path) -> list[Path]:
    files = []
    for path in directory.iterdir():
        if path.is_symlink():
            raise AlleleConfirmationError(
                f"symlinked FASTQ input is not accepted: {path.name}"
            )
        if not path.is_file():
            continue
        name = path.name.lower()
        if name.endswith(FASTQ_SUFFIXES):
            files.append(path)
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream private FASTQ paths for centered k-mer confirmation."
    )
    parser.add_argument("--config", type=Path)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--fastq", nargs="+", type=Path)
    sources.add_argument("--fastq-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--expected-n-files",
        type=int,
        default=DEFAULT_EXPECTED_N_FILES,
    )
    parser.add_argument(
        "--layout-only",
        action="store_true",
        help="Write lane-completeness only; do not count k-mers.",
    )
    parser.add_argument(
        "--pinned-layout",
        action="store_true",
        help="Require the pinned gated FASTQ filename digest without storing names.",
    )
    arguments = parser.parse_args()
    try:
        if arguments.fastq_dir is not None:
            _outside_repo(arguments.fastq_dir)
            if not arguments.fastq_dir.is_dir():
                raise AlleleConfirmationError("fastq directory is not a directory")
            fastq_paths = collect_fastq_files(arguments.fastq_dir)
            if not fastq_paths:
                raise AlleleConfirmationError("fastq directory contains no FASTQ files")
        else:
            fastq_paths = list(arguments.fastq)
            for fastq in fastq_paths:
                _outside_repo(fastq)
                if fastq.is_symlink():
                    raise AlleleConfirmationError(
                        f"symlinked FASTQ input is not accepted: {fastq.name}"
                    )
        _outside_repo(arguments.output)
        if arguments.output.is_symlink():
            raise AlleleConfirmationError(
                "symlinked output path is not accepted"
            )
        if arguments.output.exists():
            parser.error("output already exists; refusing to overwrite")
        expected_digest = (
            PINNED_FASTQ_NAME_DIGEST if arguments.pinned_layout else None
        )
        if arguments.layout_only:
            result = {
                "schema": "mva-track2-allele-confirmation/v1",
                "synthetic_only": False,
                "layout_only": True,
                "layout": assess_fastq_layout(
                    fastq_paths,
                    expected_n_files=arguments.expected_n_files,
                    expected_name_digest=expected_digest,
                ),
            }
        else:
            if arguments.config is None:
                parser.error("--config is required unless --layout-only")
            _outside_repo(arguments.config)
            payload = json.loads(
                arguments.config.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant,
                parse_float=_finite_float,
            )
            result = confirm_from_fastq_paths(
                payload["alleles"],
                fastq_paths,
                expected_n_files=arguments.expected_n_files,
                expected_name_digest=expected_digest,
                synthetic_only=False,
            )
    except (AlleleConfirmationError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - normalize unexpected bugs
        parser.error(f"unexpected error: {exc}")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    layout = result.get("layout", {})
    print(
        "allele confirmation: "
        f"files={layout.get('n_files', result.get('n_files'))}/"
        f"{layout.get('expected_n_files', arguments.expected_n_files)}; "
        f"incomplete={layout.get('incomplete', result.get('incomplete_inputs'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
