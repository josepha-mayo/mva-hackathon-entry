"""Report gated-dataset access without printing credentials or downloading data."""

from __future__ import annotations

import sys

from huggingface_hub import HfApi, get_hf_file_metadata, hf_hub_url

DATASET_ID = "SageBio/mva-hackathon-2026-data"
GATED_PROBE_FILE = "WGS_EX2312012_HGWCNDSX7.vcf.gz"


def main() -> int:
    api = HfApi()
    try:
        api.whoami()
    except Exception as exc:
        print(f"NO-GO: Hugging Face authentication unavailable ({type(exc).__name__}).")
        return 2

    # Repository filenames can be visible even when gated payload access is
    # denied. Probe metadata for a controlled payload using the saved token;
    # this performs a HEAD request and cannot start a large download.
    try:
        url = hf_hub_url(DATASET_ID, GATED_PROBE_FILE, repo_type="dataset")
        get_hf_file_metadata(url, token=True)
    except Exception as exc:
        print(
            "NO-GO: Hugging Face authentication works, but gated payload access is unavailable "
            f"({type(exc).__name__})."
        )
        return 3

    print("GO: authenticated gated-file metadata access is available; no payload was downloaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
