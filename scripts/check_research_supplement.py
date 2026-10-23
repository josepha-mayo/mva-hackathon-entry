"""Check exact reviewed public-source bytes; never grants a privacy allowance.

The frozen privacy checker is called unchanged. Its identifier findings stay
visible and digest-bound. Any non-identifier finding fails this comparison.
This is not a substitute for the legacy all-history privacy/release gate.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json

from privacy_gate import _inspect_bytes

MANIFEST = "release/research-supplement-review.json"
SCHEMA = "mva-public-source-review/v1"
SOURCE_LABEL = "public-source-review"


def finding_digest(findings: list[str]) -> str:
    return hashlib.sha256(json.dumps(findings, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def check(root: Path, inspector=_inspect_bytes) -> dict:
    root = root.resolve()
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("legacy_policy_changed") is not False:
        raise ValueError("Unsupported review or changed legacy policy")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("No reviewed files")
    seen = set()
    count = 0
    for row in rows:
        relative = PurePosixPath(row["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative) or ":" in str(relative):
            raise ValueError("Review path escapes its repository")
        if str(relative) in seen:
            raise ValueError("Duplicate review path")
        seen.add(str(relative))
        source = root.joinpath(*relative.parts)
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError("Redirected review path")
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"Reviewed bytes changed: {relative}")
        findings = inspector(relative, raw, SOURCE_LABEL)
        # Credential, raw-payload, path, encoding and other findings cannot be
        # accepted by this public-vocabulary comparison, even if prelisted.
        if any(not item.startswith("non-synthetic biological identifier ") for item in findings):
            raise ValueError(f"Non-identifier finding requires separate review: {relative}")
        if len(findings) != row["identifier_finding_count"] or finding_digest(findings) != row["identifier_findings_sha256"]:
            raise ValueError(f"Reviewer diagnostic changed: {relative}")
        count += len(findings)
    return {"reviewed_files": len(rows), "retained_identifier_findings": count,
            "exact_reviewed_bytes_and_diagnostics_match": True,
            "privacy_allowance_granted": False, "clinical_advancement_granted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = check(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"match": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    print("MATCH: public-source review only; not a legacy privacy-gate pass, release adoption or biological result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
