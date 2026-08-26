#!/usr/bin/env python3
"""Fail-closed public-development adapter for a pinned Phen2Gene checkout.

The script contains no benchmark data and has no calibration, held-out, patient,
upload, or submission mode. It writes aggregate receipts only. The official
knowledge-base bundle and Phenopacket archive must be acquired separately from
their official release URLs and are never copied into this repository.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


CONFIG_SCHEMA = "mva-phen2gene-development-contract/v1"
RESULT_SCHEMA = "mva-phen2gene-development-receipt/v1"


class AdapterInputError(ValueError):
    """Raised when a pin, split, or development input fails closed."""


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def split_for_identifier(identifier: str, salt_segments: Sequence[str]) -> str:
    if len(salt_segments) != 4:
        raise AdapterInputError("split salt must contain four segments")
    normalized = [
        segment.upper() if index < 2 else segment
        for index, segment in enumerate(salt_segments)
    ]
    salt = "-".join(normalized)
    digest = hashlib.sha256(f"{salt}:{identifier}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10_000
    if bucket < 6_000:
        return "development"
    if bucket < 8_000:
        return "calibration"
    return "test"


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _rank_metrics(ranks: Sequence[Optional[int]]) -> Dict[str, float]:
    numeric = [math.inf if rank is None else rank for rank in ranks]
    count = len(numeric)
    return {
        "top1": sum(rank <= 1 for rank in numeric) / count,
        "top3": sum(rank <= 3 for rank in numeric) / count,
        "top5": sum(rank <= 5 for rank in numeric) / count,
        "top10": sum(rank <= 10 for rank in numeric) / count,
        "mrr": sum(0.0 if math.isinf(rank) else 1.0 / rank for rank in numeric)
        / count,
    }


def summarize_ranks(
    ranks: Sequence[Optional[int]], *, seed: int, replicates: int
) -> Dict[str, Any]:
    if not ranks:
        raise AdapterInputError("at least one rank is required")
    if replicates < 100:
        raise AdapterInputError("bootstrap_replicates must be at least 100")
    point = _rank_metrics(ranks)
    generator = random.Random(seed)
    bootstrap: Dict[str, List[float]] = {name: [] for name in point}
    for _ in range(replicates):
        sample = [ranks[generator.randrange(len(ranks))] for _ in ranks]
        sampled = _rank_metrics(sample)
        for name, value in sampled.items():
            bootstrap[name].append(value)
    result: Dict[str, Any] = {
        name: {
            "point": round(value, 6),
            "ci95": [
                round(_percentile(bootstrap[name], 0.025), 6),
                round(_percentile(bootstrap[name], 0.975), 6),
            ],
        }
        for name, value in point.items()
    }
    finite = [rank for rank in ranks if rank is not None]
    result["median_rank_finite_truths"] = (
        statistics.median(finite) if finite else None
    )
    return result


def packet_hpo(packet: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    positive: List[str] = []
    negative: List[str] = []
    for feature in packet.get("phenotypicFeatures", []):
        term = feature.get("type", {}).get("id", "")
        if not isinstance(term, str) or not term.startswith("HP:"):
            continue
        (negative if feature.get("excluded") is True else positive).append(term)
    return sorted(set(positive)), sorted(set(negative))


def knowledge_tree_receipt(root: Path) -> Dict[str, Any]:
    if not root.is_dir():
        raise AdapterInputError("knowledge-base directory does not exist")
    for required in ("Knowledgebase", "weights", "skewness"):
        if not (root / required).is_dir():
            raise AdapterInputError(f"knowledge-base directory is missing {required}")

    files: List[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AdapterInputError("symbolic links are forbidden in the knowledge tree")
        if path.is_file():
            files.append(path)
    files.sort(key=lambda path: path.relative_to(root).as_posix())

    tree_digest = hashlib.sha256()
    total_bytes = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        digest = sha256_file(path)
        tree_digest.update(relative.encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(str(size).encode("ascii"))
        tree_digest.update(b"\0")
        tree_digest.update(digest.encode("ascii"))
        tree_digest.update(b"\n")
        total_bytes += size
    return {
        "file_count": len(files),
        "uncompressed_bytes": total_bytes,
        "tree_sha256": tree_digest.hexdigest(),
    }


def _checked_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterInputError("could not read a required JSON input") from exc
    if not isinstance(value, dict):
        raise AdapterInputError("JSON input must contain an object")
    return value


def _validate_config(config: Dict[str, Any]) -> None:
    if config.get("schema") != CONFIG_SCHEMA:
        raise AdapterInputError("unexpected adapter config schema")
    if not str(config.get("scope", "")).startswith("public development only"):
        raise AdapterInputError("config scope is not development only")
    public_input = config.get("public_input", {})
    segments = public_input.get("split_salt_segments")
    if not isinstance(segments, list) or not all(
        isinstance(segment, str) and segment for segment in segments
    ):
        raise AdapterInputError("split salt segments are malformed")
    if segments != ["mva", "pps", "0.1.27", "v1"]:
        raise AdapterInputError("split salt segments changed")
    if public_input.get("uppercase_first_two_salt_segments") is not True:
        raise AdapterInputError("split salt normalization changed")
    bounds = [
        public_input.get("development_basis_points"),
        public_input.get("calibration_basis_points"),
        public_input.get("test_basis_points"),
    ]
    if bounds != [6000, 2000, 2000] or sum(bounds) != 10_000:
        raise AdapterInputError("the sealed split proportions changed")
    evaluation = config.get("evaluation", {})
    if evaluation.get("candidate_gene_list") is not None:
        raise AdapterInputError("candidate-gene restriction must remain disabled")
    if evaluation.get("negative_hpo_policy") != (
        "omit excluded terms because Phen2Gene accepts positive terms only"
    ):
        raise AdapterInputError("negative phenotype policy changed")


def _git_text(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise AdapterInputError("official source checkout is not a readable Git repo")
    return completed.stdout.strip()


def _load_official_module(repo: Path):
    module_path = repo / "phen2gene.py"
    if not module_path.is_file():
        raise AdapterInputError("official source entry point is missing")
    spec = importlib.util.spec_from_file_location("mva_pinned_phen2gene", module_path)
    if spec is None or spec.loader is None:
        raise AdapterInputError("could not load the official source entry point")
    module = importlib.util.module_from_spec(spec)
    old_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        sys.dont_write_bytecode = old_flag
    if not callable(getattr(module, "results", None)):
        raise AdapterInputError("official source has no callable results API")
    return module


def _validate_static_inputs(
    *,
    config: Dict[str, Any],
    config_path: Path,
    repo: Path,
    kb_archive: Path,
    kb: Path,
    phenopacket_archive: Path,
    selector_path: Path,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    _validate_config(config)
    official = config["official_source"]
    observed_commit = _git_text(repo, "rev-parse", "HEAD")
    if observed_commit != official["commit"]:
        raise AdapterInputError("official source commit does not match the pin")
    observed_tree = _git_text(repo, "rev-parse", "HEAD^{tree}")
    if observed_tree != official["tree"]:
        raise AdapterInputError("official source tree does not match the pin")
    if _git_text(repo, "status", "--porcelain"):
        raise AdapterInputError("official source checkout is dirty")

    knowledge = config["knowledge_base"]
    if kb_archive.stat().st_size != knowledge["asset_bytes"]:
        raise AdapterInputError("knowledge-base archive byte count does not match")
    if sha256_file(kb_archive) != knowledge["asset_sha256"]:
        raise AdapterInputError("knowledge-base archive digest does not match")
    tree = knowledge_tree_receipt(kb)
    expected_tree = {
        "file_count": knowledge["file_count"],
        "uncompressed_bytes": knowledge["uncompressed_bytes"],
        "tree_sha256": knowledge["tree_sha256"],
    }
    if tree != expected_tree:
        raise AdapterInputError("knowledge-base tree receipt does not match")

    public_input = config["public_input"]
    if phenopacket_archive.stat().st_size != public_input["archive_bytes"]:
        raise AdapterInputError("public Phenopacket archive byte count does not match")
    if sha256_file(phenopacket_archive) != public_input["archive_sha256"]:
        raise AdapterInputError("public Phenopacket archive digest does not match")
    if sha256_file(selector_path) != public_input["selector_sha256"]:
        raise AdapterInputError("development selector digest does not match")

    selector = _checked_json(selector_path)
    if selector.get("split") != "development_smoke":
        raise AdapterInputError("selector is not the development smoke")
    cases = selector.get("cases")
    if not isinstance(cases, list) or len(cases) != public_input["case_count"]:
        raise AdapterInputError("development selector case count does not match")

    identifiers: List[str] = []
    archive_paths: List[str] = []
    for case in cases:
        if not isinstance(case, dict):
            raise AdapterInputError("development selector case is malformed")
        try:
            identifier = case["hgnc_id"]
            archive_path = case["archive_path"]
            truth_gene = case["truth_gene"]
        except KeyError as exc:
            raise AdapterInputError("development selector case lacks a required field") from exc
        if not all(isinstance(value, str) and value for value in (
            identifier, archive_path, truth_gene
        )):
            raise AdapterInputError("development selector case field is malformed")
        identifiers.append(identifier)
        archive_paths.append(archive_path)
        observed_split = split_for_identifier(
            identifier, public_input["split_salt_segments"]
        )
        if observed_split != "development":
            raise AdapterInputError("split guard rejected a nondevelopment identifier")
    if len(set(identifiers)) != public_input["unique_gene_count"]:
        raise AdapterInputError("development selector gene count does not match")
    if len(set(archive_paths)) != len(cases):
        raise AdapterInputError("development selector archive paths are not unique")

    pins = {
        "config_sha256": sha256_file(config_path),
        "source_commit": observed_commit,
        "source_tree": observed_tree,
        "knowledge_archive_sha256": knowledge["asset_sha256"],
        "knowledge_tree_sha256": tree["tree_sha256"],
        "phenopacket_archive_sha256": public_input["archive_sha256"],
        "selector_sha256": public_input["selector_sha256"],
    }
    return selector, tree, pins


def run_development_baseline(
    *,
    config_path: Path,
    repo: Path,
    kb_archive: Path,
    kb: Path,
    phenopacket_archive: Path,
    selector_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    """Run the sealed public development comparator and write one aggregate receipt."""

    paths = [
        config_path,
        repo,
        kb_archive,
        kb,
        phenopacket_archive,
        selector_path,
        output_path,
    ]
    (
        config_path,
        repo,
        kb_archive,
        kb,
        phenopacket_archive,
        selector_path,
        output_path,
    ) = [path.resolve() for path in paths]
    if output_path.exists():
        raise AdapterInputError("refusing to overwrite an existing output")

    started = time.perf_counter()
    config = _checked_json(config_path)
    selector, tree, pins = _validate_static_inputs(
        config=config,
        config_path=config_path,
        repo=repo,
        kb_archive=kb_archive,
        kb=kb,
        phenopacket_archive=phenopacket_archive,
        selector_path=selector_path,
    )
    evaluation = config["evaluation"]
    official_module = _load_official_module(repo)

    case_receipts: List[Dict[str, Any]] = []
    old_cwd = Path.cwd()
    os.chdir(repo)
    try:
        with zipfile.ZipFile(phenopacket_archive) as archive:
            for case in selector["cases"]:
                try:
                    packet = json.loads(archive.read(case["archive_path"]))
                except (KeyError, json.JSONDecodeError) as exc:
                    raise AdapterInputError(
                        "selected public development entry could not be read"
                    ) from exc
                positive, negative = packet_hpo(packet)
                if len(positive) < evaluation["minimum_positive_hpo_terms"]:
                    raise AdapterInputError(
                        "development case has too few positive phenotype terms"
                    )
                gene_dict, diagnostic_text, observed_weight_model = (
                    official_module.results(
                        str(kb),
                        manuals=positive,
                        weight_model=evaluation["weight_model"],
                        verbosity=True,
                        cl=False,
                    )
                )
                if observed_weight_model != evaluation["weight_model"]:
                    raise AdapterInputError("official API changed the weight model")
                truth_gene = case["truth_gene"]
                ranked_symbols = list(gene_dict.keys())
                official_rank = (
                    ranked_symbols.index(truth_gene) + 1
                    if truth_gene in gene_dict
                    else None
                )
                truth_score = (
                    float(gene_dict[truth_gene][1])
                    if truth_gene in gene_dict
                    else None
                )
                tie_min_rank = None
                tie_max_rank = None
                if truth_score is not None:
                    scores = [float(value[1]) for value in gene_dict.values()]
                    tie_min_rank = 1 + sum(score > truth_score for score in scores)
                    tie_max_rank = sum(score >= truth_score for score in scores)
                case_receipts.append(
                    {
                        "official_rank": official_rank,
                        "tie_min_rank": tie_min_rank,
                        "tie_max_rank": tie_max_rank,
                        "candidate_count": len(gene_dict),
                        "positive_hpo_input_count": len(positive),
                        "negative_hpo_omitted_count": len(negative),
                        "diagnostic_text_sha256": hashlib.sha256(
                            str(diagnostic_text).encode("utf-8")
                        ).hexdigest(),
                    }
                )
    finally:
        os.chdir(old_cwd)

    official_ranks = [case["official_rank"] for case in case_receipts]
    tie_end_ranks = [case["tie_max_rank"] for case in case_receipts]
    seed = evaluation["bootstrap_seed"]
    replicates = evaluation["bootstrap_replicates"]
    candidate_counts = [case["candidate_count"] for case in case_receipts]
    positive_counts = [case["positive_hpo_input_count"] for case in case_receipts]
    negative_counts = [case["negative_hpo_omitted_count"] for case in case_receipts]
    receipt_digest = hashlib.sha256(
        json.dumps(
            case_receipts, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

    core = {
        "configuration": {
            "scope": config["scope"],
            "weight_model": evaluation["weight_model"],
            "candidate_gene_list": None,
            "negative_hpo_policy": evaluation["negative_hpo_policy"],
            "bootstrap_seed": seed,
            "bootstrap_replicates": replicates,
            "rank_semantics": evaluation["rank_semantics"],
        },
        "pins": pins,
        "knowledge_tree": tree,
        "case_count": len(case_receipts),
        "unique_gene_count": config["public_input"]["unique_gene_count"],
        "truth_present": sum(rank is not None for rank in official_ranks),
        "truth_absent": sum(rank is None for rank in official_ranks),
        "truth_universe_recall": round(
            sum(rank is not None for rank in official_ranks) / len(official_ranks), 6
        ),
        "candidate_count_range": [min(candidate_counts), max(candidate_counts)],
        "positive_hpo_input_count_range": [min(positive_counts), max(positive_counts)],
        "cases_with_negative_hpo_omitted": sum(count > 0 for count in negative_counts),
        "negative_hpo_terms_omitted": sum(negative_counts),
        "official_metrics": summarize_ranks(
            official_ranks, seed=seed, replicates=replicates
        ),
        "pessimistic_tie_metrics": summarize_ranks(
            tie_end_ranks, seed=seed, replicates=replicates
        ),
        "case_receipt_sha256": receipt_digest,
    }
    core_sha256 = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    result = {
        "schema": RESULT_SCHEMA,
        "status": "development_only_complete",
        "safety": {
            "development_entries_read": len(case_receipts),
            "calibration_cases_read": 0,
            "heldout_test_cases_read": 0,
            "controlled_patient_files_read": 0,
            "network_required_during_inference": False,
            "case_identifiers_written": 0,
        },
        "official_sources": {
            "phen2gene": config["official_source"],
            "knowledge_base": config["knowledge_base"],
            "phenopacket_store": {
                key: value
                for key, value in config["public_input"].items()
                if key not in {
                    "selector_sha256",
                    "split_salt_segments",
                    "uppercase_first_two_salt_segments",
                    "development_basis_points",
                    "calibration_basis_points",
                    "test_basis_points",
                }
            },
        },
        "core_sha256": core_sha256,
        **core,
        "runtime": {
            "python": sys.version.split()[0],
            "seconds": round(time.perf_counter() - started, 3),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the sealed public Phen2Gene development comparator."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--kb-archive", required=True, type=Path)
    parser.add_argument("--kb", required=True, type=Path)
    parser.add_argument("--phenopacket-archive", required=True, type=Path)
    parser.add_argument("--selector", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _parser().parse_args(argv)
    result = run_development_baseline(
        config_path=args.config,
        repo=args.repo,
        kb_archive=args.kb_archive,
        kb=args.kb,
        phenopacket_archive=args.phenopacket_archive,
        selector_path=args.selector,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "case_count": result["case_count"],
                "truth_universe_recall": result["truth_universe_recall"],
                "top10": result["official_metrics"]["top10"],
                "mrr": result["official_metrics"]["mrr"],
                "core_sha256": result["core_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
