"""Assess explicitly declared first-event follow-up; never grants advancement."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mva_hackathon.fixed_horizon import FollowupError, assess_fixed_horizon_followup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = assess_fixed_horizon_followup(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, FollowupError) as exc:
        print(json.dumps({"timing_and_accounting_qualified": False, "advancement_granted": False,
                          "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["timing_and_accounting_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
