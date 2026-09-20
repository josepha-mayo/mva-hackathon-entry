from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.allele_confirmation import (
    CLAIM_BOUNDARY,
    DEFAULT_EXPECTED_N_FILES,
    MINIMUM_OBSERVATIONS,
    PINNED_FASTQ_NAME_DIGEST,
    SCHEMA,
    AlleleConfirmationError,
    FastqSequenceStream,
    assess_fastq_layout,
    classify_counts,
    confirm_alleles,
    confirm_from_fastq_paths,
    gzip_fastq,
    iter_fastq_sequences,
    reverse_complement,
)


FLANK_LEFT = "ACGTACGTACGTACGTACGTACGTA"
FLANK_RIGHT = "TGCATGCATGCATGCATGCATGCAT"
ALLELE = {
    "allele_id": "syn-allele-1",
    "flank_left": FLANK_LEFT,
    "ref": "A",
    "alt": "C",
    "flank_right": FLANK_RIGHT,
}
LANES = ("a", "b", "c", "d")
MATES = ("r1", "r2")


def _read(base: str) -> str:
    return FLANK_LEFT + base + FLANK_RIGHT


def _write_gzip(folder: Path, name: str, records: list[tuple[str, str]]) -> Path:
    path = folder / name
    path.write_bytes(gzip_fastq(records))
    return path


def _confirming_records() -> list[tuple[str, str]]:
    records = []
    for index in range(MINIMUM_OBSERVATIONS):
        records.append((f"syn-ref-{index}", _read("A")))
        records.append((f"syn-alt-{index}", _read("C")))
    return records


class AlleleConfirmationTests(unittest.TestCase):
    def test_both_alleles_meet_the_observation_floor(self) -> None:
        sequences = [_read("A")] * MINIMUM_OBSERVATIONS + [_read("C")] * MINIMUM_OBSERVATIONS
        result = confirm_alleles([ALLELE], sequences)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["claim_boundary"], CLAIM_BOUNDARY)
        self.assertEqual(result["alleles"][0]["status"], "both_alleles_observed")
        self.assertTrue(result["reverse_complement_counted"])
        self.assertEqual(result["n_reads"], 2 * MINIMUM_OBSERVATIONS)

    def test_reverse_complement_reads_still_count(self) -> None:
        sequences = [reverse_complement(_read("A"))] * MINIMUM_OBSERVATIONS + [
            reverse_complement(_read("C"))
        ] * MINIMUM_OBSERVATIONS
        result = confirm_alleles([ALLELE], sequences)
        self.assertEqual(result["alleles"][0]["status"], "both_alleles_observed")
        self.assertTrue(result["reverse_complement_counted"])

    def test_sparse_alternate_is_insufficient_not_confirmation(self) -> None:
        sequences = [_read("A")] * MINIMUM_OBSERVATIONS + [_read("C")] * 2
        result = confirm_alleles([ALLELE], sequences)
        self.assertEqual(result["alleles"][0]["status"], "insufficient_observations")

    def test_missing_alternate_is_labeled(self) -> None:
        sequences = [_read("A")] * MINIMUM_OBSERVATIONS
        result = confirm_alleles([ALLELE], sequences)
        self.assertEqual(result["alleles"][0]["status"], "alternate_not_observed")

    def test_incomplete_inputs_dominate_counts(self) -> None:
        sequences = [_read("A")] * 20 + [_read("C")] * 20
        result = confirm_alleles([ALLELE], sequences, incomplete=True)
        self.assertEqual(result["alleles"][0]["status"], "incomplete_inputs")
        self.assertEqual(
            classify_counts(reference_count=20, alternate_count=20, incomplete=True),
            "incomplete_inputs",
        )

    def test_gzip_round_trip_and_truncated_tail(self) -> None:
        payload = gzip_fastq([("syn-read-1", _read("A")), ("syn-read-2", _read("C"))])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reads.bin"
            path.write_bytes(payload)
            sequences, incomplete = iter_fastq_sequences(path)
            self.assertEqual(len(sequences), 2)
            self.assertFalse(incomplete)
            import gzip as gzip_mod
            import io

            broken = io.BytesIO()
            with gzip_mod.GzipFile(fileobj=broken, mode="wb") as handle:
                handle.write(b"@syn-read-1\nACGT\n+\nIIII\n@syn-tail\nACGT\n")
            path.write_bytes(broken.getvalue())
            _, truncated = iter_fastq_sequences(path)
            self.assertTrue(truncated)

    def test_stream_does_not_slurp_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _write_gzip(Path(folder), "reads.bin", [("syn-read-1", _read("A"))])
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must stream")):
                stream = FastqSequenceStream(path)
                sequences = list(stream)
            self.assertEqual(sequences, [_read("A")])
            self.assertFalse(stream.incomplete)

    def test_truncated_five_file_set_cannot_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [
                _write_gzip(root, f"syn-partial-{index}.bin", _confirming_records())
                for index in range(5)
            ]
            result = confirm_from_fastq_paths(
                [ALLELE], paths, expected_n_files=DEFAULT_EXPECTED_N_FILES
            )
            self.assertTrue(result["incomplete_inputs"])
            self.assertEqual(result["alleles"][0]["status"], "incomplete_inputs")
            self.assertIn("fewer_files_than_expected", result["layout"]["reasons"])
            self.assertIn("unlabeled_mates", result["layout"]["reasons"])

    def test_unpaired_full_count_cannot_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = []
            for lane in LANES:
                paths.append(
                    _write_gzip(root, f"syn-lane-{lane}_r1_001.bin", _confirming_records())
                )
                if lane != "d":
                    paths.append(
                        _write_gzip(root, f"syn-lane-{lane}_r2_001.bin", [])
                    )
                else:
                    paths.append(
                        _write_gzip(root, f"syn-lane-{lane}_r1_extra.bin", [])
                    )
            result = confirm_from_fastq_paths([ALLELE], paths)
            self.assertEqual(result["n_files"], 8)
            self.assertTrue(result["incomplete_inputs"])
            self.assertIn("unpaired_mates", result["layout"]["reasons"])
            self.assertEqual(result["alleles"][0]["status"], "incomplete_inputs")

    def test_complete_paired_set_can_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = []
            for lane in LANES:
                for mate in MATES:
                    records = _confirming_records() if lane == "a" and mate == "r1" else []
                    paths.append(
                        _write_gzip(
                            root,
                            f"syn-lane-{lane}_{mate}_001.bin",
                            records,
                        )
                    )
            result = confirm_from_fastq_paths([ALLELE], paths)
            self.assertFalse(result["incomplete_inputs"])
            self.assertEqual(result["layout"]["paired_stems"], 4)
            self.assertEqual(result["alleles"][0]["status"], "both_alleles_observed")
            self.assertEqual(result["n_reads"], 2 * MINIMUM_OBSERVATIONS)

    def test_layout_names_do_not_need_file_payloads(self) -> None:
        paths = [
            Path(f"syn-lane-{lane}_{mate}_001.fastq.gz")
            for lane in LANES
            for mate in MATES
        ]
        layout = assess_fastq_layout(paths)
        self.assertEqual(layout["n_files"], 8)
        self.assertEqual(layout["paired_stems"], 4)
        self.assertFalse(layout["incomplete"])
        five = [Path(f"syn-partial-{index}.bin") for index in range(5)]
        truncated = assess_fastq_layout(five)
        self.assertTrue(truncated["incomplete"])
        self.assertIn("fewer_files_than_expected", truncated["reasons"])

    def test_wrong_filename_digest_cannot_confirm(self) -> None:
        paths = [
            Path(f"syn-lane-{lane}_{mate}_001.fastq.gz")
            for lane in LANES
            for mate in MATES
        ]
        layout = assess_fastq_layout(
            paths, expected_name_digest=PINNED_FASTQ_NAME_DIGEST
        )
        self.assertTrue(layout["incomplete"])
        self.assertIn("name_digest_mismatch", layout["reasons"])
        matching = assess_fastq_layout(
            paths, expected_name_digest=layout["name_digest"]
        )
        self.assertFalse(matching["incomplete"])

    def test_identical_ref_alt_fails_closed(self) -> None:
        bad = dict(ALLELE, alt="A")
        with self.assertRaisesRegex(AlleleConfirmationError, "must differ"):
            confirm_alleles([bad], [_read("A")])

    def test_ambiguous_read_counts_for_neither_allele(self) -> None:
        allele = {
            "allele_id": "syn-allele-ambiguous",
            "flank_left": "A" * 30,
            "ref": "A",
            "alt": "C",
            "flank_right": "A" * 30,
        }
        read = "A" * 25 + "C" + "A" * 51
        result = confirm_alleles([allele], [read] * MINIMUM_OBSERVATIONS)
        self.assertEqual(result["alleles"][0]["status"], "neither_observed")

    def test_one_read_is_at_most_one_observation(self) -> None:
        allele = {
            "allele_id": "syn-allele-homopolymer",
            "flank_left": "A" * 30,
            "ref": "A",
            "alt": "C",
            "flank_right": "A" * 30,
        }
        result = confirm_alleles([allele], ["A" * 200])
        self.assertEqual(result["alleles"][0]["by_k"][0]["reference_count"], 1)
        self.assertEqual(result["alleles"][0]["status"], "alternate_not_observed")

    def test_single_unlabeled_file_cannot_confirm(self) -> None:
        # A caller-declared single file must not drop the paired-lane guard.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = _write_gzip(root, "syn-unlabeled.bin", _confirming_records())
            with self.assertRaisesRegex(AlleleConfirmationError, "paired lanes"):
                confirm_from_fastq_paths([ALLELE], [path], expected_n_files=1)
            with self.assertRaisesRegex(AlleleConfirmationError, "paired lanes"):
                confirm_from_fastq_paths(
                    [ALLELE], [path], expected_n_files=1.5
                )
        layout = assess_fastq_layout(
            [Path("syn-unlabeled.fastq.gz")], expected_n_files=8
        )
        self.assertTrue(layout["incomplete"])
        self.assertIn("unlabeled_mates", layout["reasons"])

    def test_reverse_complement_equivalent_kmers_fail_closed(self) -> None:
        # A/T alleles inside RC-palindromic flanks produce RC-equal k-mers; the
        # locus cannot be classified by k-mer, so the definition is rejected.
        bad = {
            "allele_id": "syn-allele-rc",
            "flank_left": "A" * 25,
            "ref": "A",
            "alt": "T",
            "flank_right": "T" * 25,
        }
        with self.assertRaisesRegex(
            AlleleConfirmationError, "reverse-complement equivalent"
        ):
            confirm_alleles([bad], ["A" * 60])

    def test_minimum_below_floor_fails_closed(self) -> None:
        sequences = [_read("A")] * 20 + [_read("C")] * 20
        with self.assertRaisesRegex(AlleleConfirmationError, "observation floor"):
            confirm_alleles([ALLELE], sequences, minimum=0)
        with self.assertRaisesRegex(AlleleConfirmationError, "observation floor"):
            classify_counts(
                reference_count=20, alternate_count=20, incomplete=False, minimum=1
            )


if __name__ == "__main__":
    unittest.main()
