"""Audit two independently obtained public reference files; performs no fetch."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mva_hackathon.reference_audit import ReferenceAuditError, audit_public_reference


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genbank", type=Path, required=True)
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--change", action="append", required=True, help="one-based coding position:alternate base; repeat for independent substitutions")
    args = parser.parse_args()
    try:
        changes = []
        for value in args.change:
            position, alt = value.split(":")
            changes.append((int(position), alt))
        # Bound reads before parsing; do not materialize oversized files.
        from mva_hackathon.reference_audit import MAX_SOURCE_BYTES
        with args.genbank.open("rb") as handle:
            genbank = handle.read(MAX_SOURCE_BYTES + 1)
        with args.fasta.open("rb") as handle:
            fasta = handle.read(MAX_SOURCE_BYTES + 1)
        result = audit_public_reference(genbank, fasta, changes,
            expected_version=args.expected_version, expected_genbank_sha256=args.expected_sha256)
    except (OSError, ValueError, ReferenceAuditError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
