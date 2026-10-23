"""Audit a local copy of the exact public NALL JCI workbook, without downloads."""

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.nall_source_data import SourceDataError, audit_workbook, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path, help="Downloaded JCI196137.sdval.xlsx")
    parser.add_argument("--output", type=Path, help="Save executed descriptive JSON")
    args = parser.parse_args()
    config_path = Path(__file__).resolve().parents[1] / "configs" / "nall-source-data.json"
    try:
        result = audit_workbook(args.workbook, load_config(config_path))
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, ValueError, KeyError) as exc:
        print(f"NALL source-data audit failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
