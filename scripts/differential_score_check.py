"""Differential-fuzz the local scorer against a pinned official evaluation.py."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.scoring import score_rows
from mva_hackathon.submission import Prediction, Variant


def load_official(path: Path) -> object:
    spec = importlib.util.spec_from_file_location("official_mva_evaluation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load official evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git_commit(path: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(path.parent), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def synthetic_variant(index: int) -> Variant:
    bases = (("A", "C"), ("C", "G"), ("G", "T"), ("T", "A"))
    ref, alt = bases[index % len(bases)]
    return (f"chr{1 + index % 22}", 10_000 + index * 17, ref, alt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-evaluation", type=Path, required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--cases", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20_260_826)
    args = parser.parse_args()

    path = args.official_evaluation.resolve()
    if not path.is_file():
        print("NO-GO: official evaluation.py was not found")
        return 2
    commit = git_commit(path)
    if args.expected_commit and commit != args.expected_commit:
        print("NO-GO: official evaluator checkout is not at the expected commit")
        return 3
    official = load_official(path)
    rng = random.Random(args.seed)
    universe = [synthetic_variant(index) for index in range(40)]

    fields = (
        "full_match_rank", "partial_match_rank", "rank_points", "f_max",
        "f_max_threshold", "n_predictions_at_f_max",
    )
    for case in range(args.cases):
        true_variants = frozenset(rng.sample(universe, rng.choice((1, 2))))
        local_rows: list[Prediction] = []
        official_unsorted: list[tuple[frozenset[Variant], float, str]] = []
        for source_row in range(1, rng.randint(1, 10) + 1):
            variants = frozenset(rng.sample(universe, rng.choice((1, 2))))
            epcr = rng.choice((0.1, 0.2, 0.4, 0.6, 0.8, 0.95))
            finding_type = rng.choice(("primary", "secondary"))
            local_rows.append(
                Prediction("PROBAND01", variants, epcr, finding_type, "synthetic", source_row)
            )
            official_unsorted.append((variants, epcr, finding_type))

        ordered = sorted(enumerate(official_unsorted), key=lambda item: (-item[1][1], item[0]))
        official_rows = [
            official.SubmissionRow(variants, epcr, rank, finding_type)
            for rank, (_, (variants, epcr, finding_type)) in enumerate(ordered, start=1)
        ]
        local_score = score_rows(local_rows, true_variants)
        official_score = official.score_proband("PROBAND01", official_rows, true_variants)

        for field in fields:
            left = getattr(local_score, field)
            right = getattr(official_score, field)
            if isinstance(left, float) or isinstance(right, float):
                if left is None or right is None:
                    equal = left is right
                else:
                    equal = abs(float(left) - float(right)) <= 1e-12
            else:
                equal = left == right
            if not equal:
                print(f"NO-GO: differential mismatch at case {case}, field {field}")
                return 4

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(
        f"GO: {args.cases} synthetic differential cases matched exactly; "
        f"seed={args.seed}; official_file_sha256={digest}; commit={commit or 'unavailable'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
