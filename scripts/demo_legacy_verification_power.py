"""Reproduce two historical assurance defects using invented data only.

The actual historical timestamp is not alleged fabricated. No network,
timestamp request, source mutation or new power certificate is produced.
"""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    spec = importlib.util.spec_from_file_location("legacy_verify_all_audit", ROOT / "scripts/verify_all.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    with tempfile.TemporaryDirectory(prefix="mva-invented-proof-") as directory:
        scratch = Path(directory).resolve()
        assert scratch.is_relative_to(Path(tempfile.gettempdir()).resolve())
        (scratch / "attestation").mkdir()
        (scratch / "release").mkdir()
        manifest = (ROOT / "release/release-artifacts.json").read_bytes()
        (scratch / "release/release-artifacts.json").write_bytes(manifest)
        proof = {"tst": {"message_imprint": hashlib.sha256(manifest).hexdigest(),
            "time_stamp_utc": "1900-01-01T00:00:00Z", "serial_number": "syn-invented-serial"},
            "rfc3161_token_hex": (b"synthetic invalid timestamp response " * 8).hex()}
        (scratch / "attestation/timestamp-proof.json").write_bytes(json.dumps(proof).encode())
        fake_ok, _ = verifier._check_timestamp(scratch)

    import mva_hackathon.assay_power as power
    captured = []
    original_builder = power.lineage_study_from_counts

    def inspect_builder(*args, **kwargs):
        study = original_builder(*args, **kwargs)
        captured.append({"founders": len(study.founders), "daughters": len(study.daughters),
            "daughter_outcomes": dict(Counter(d.outcome for d in study.daughters))})
        return study

    power.lineage_study_from_counts = inspect_builder
    try:
        power._analyzer_clean_rate.cache_clear()
        hits = power._analyzer_clean_rate(n_events=3, n_clones=6, n_opportunities=36,
            vehicle_error=1/3, treatment_error=1/9, vehicle_completion=1.0,
            treatment_completion=1.0, death_rate=0.0, dropout_rate=0.0,
            concentration=None, n_sims=1, seed=power.SEED)
    finally:
        power.lineage_study_from_counts = original_builder
        power._analyzer_clean_rate.cache_clear()
    assert fake_ok
    assert captured and captured[0]["daughter_outcomes"]["not_followed"] * 2 == captured[0]["daughters"]
    print(json.dumps({"scope": "Invented audit counterexamples; no biological or replacement power estimate",
        "historical_timestamp_helper_accepts_non_der_blob": fake_ok,
        "actual_token_fabrication_not_inferred": True,
        "single_power_replicate": {"captured": captured, "clean_hits": hits},
        "full_power_certificate_not_reexecuted": True}, indent=2))


if __name__ == "__main__":
    main()
