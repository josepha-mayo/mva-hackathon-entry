"""Verify the frozen response with OpenSSL and independently pinned certificates."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mva_hackathon.timestamp_chain import TimestampError, verify_timestamp_chain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--openssl")
    args = parser.parse_args()
    try:
        result = verify_timestamp_chain(args.root, args.openssl)
    except TimestampError as exc:
        print(json.dumps({"cryptographic_signature_and_pinned_chain_verified": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
