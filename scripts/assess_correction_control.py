#!/usr/bin/env python3
"""Print a standalone correction-control receipt; never sign or publish it."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mva_hackathon.correction_control import CorrectionControlError, assess_missense_correction_control


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = assess_missense_correction_control(
            json.loads(args.plan.read_text(encoding="utf-8")),
            json.loads(args.evidence.read_text(encoding="utf-8")),
        )
    except (CorrectionControlError, OSError, ValueError) as exc:
        print(json.dumps({"assessment_scope": "correction_control_only", "legacy_pipeline_eligible": False,
                          "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "contract_satisfied" else 1


if __name__ == "__main__":
    raise SystemExit(main())
