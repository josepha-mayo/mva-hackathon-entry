from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mva_hackathon.reproducibility import (  # noqa: E402
    MANIFEST_PATH,
    validate_manifest_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify every byte in the receipt-bound Track 2 evidence chain."
    )
    parser.add_argument("root", nargs="?", default=Path.cwd(), type=Path)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    manifest_path = root.joinpath(*MANIFEST_PATH.parts)
    try:
        manifest_data = manifest_path.read_bytes()
    except OSError as exc:
        parser.error(f"cannot read {MANIFEST_PATH.as_posix()}: {exc}")

    def load_artifact(path: PurePosixPath) -> bytes | None:
        try:
            return root.joinpath(*path.parts).read_bytes()
        except OSError:
            return None

    issues = validate_manifest_bytes(manifest_data, load_artifact)
    if issues:
        for issue in issues:
            print(f"NO-GO: {issue}")
        return 1
    print("GO: Track 2 report, pitch, code, tests, configuration, and receipt match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
