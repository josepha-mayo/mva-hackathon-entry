"""Print synthetic experiment-design counterexamples as reproducible JSON."""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.functional_supply import demonstration


if __name__ == "__main__":
    result = demonstration()
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    raise SystemExit(0 if result["all_counterexamples_reproduced"] else 1)
