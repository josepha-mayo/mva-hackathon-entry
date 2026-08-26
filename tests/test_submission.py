from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.scoring import score_rows
from mva_hackathon.submission import (
    REQUIRED_FIELDS,
    SubmissionError,
    load_predictions,
    load_predictions_bytes,
)


TRUE = frozenset(
    {
        ("chr7", 101_001, "A", "G"),
        ("chr7", 101_249, "C", "T"),
    }
)


class SubmissionTests(unittest.TestCase):
    def write_rows(self, rows: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False, encoding="utf-8")
        with handle:
            writer = csv.DictWriter(handle, fieldnames=REQUIRED_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def write_text(self, content: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False, encoding="utf-8")
        with handle:
            handle.write(content)
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def row(self, **updates: object) -> dict[str, object]:
        base: dict[str, object] = {
            "proband_id": "PROBAND01",
            "chrom_1": "chr7",
            "pos_1": 101_001,
            "ref_1": "A",
            "alt_1": "G",
            "chrom_2": "chr7",
            "pos_2": 101_249,
            "ref_2": "C",
            "alt_2": "T",
            "epcr": 0.99,
            "finding_type": "primary",
            "notes": "test fixture",
        }
        base.update(updates)
        return base

    def test_full_pair_rank_one_scores_perfectly(self) -> None:
        rows = load_predictions(self.write_rows([self.row()]))
        score = score_rows(rows, TRUE)
        self.assertEqual(score.rank_points, 100.0)
        self.assertEqual(score.f_max, 1.0)
        self.assertEqual(score.full_match_rank, 1)

    def test_required_header_order_matches_frozen_organizer_template(self) -> None:
        self.assertEqual(
            REQUIRED_FIELDS,
            (
                "proband_id",
                "chrom_1",
                "pos_1",
                "ref_1",
                "alt_1",
                "chrom_2",
                "pos_2",
                "ref_2",
                "alt_2",
                "epcr",
                "finding_type",
                "notes",
            ),
        )

    def test_single_pair_score_is_invariant_to_any_valid_epcr_value(self) -> None:
        results = []
        for epcr in (1.0, 0.5, 0.000001):
            score = score_rows(
                load_predictions(self.write_rows([self.row(epcr=epcr)])),
                TRUE,
            )
            results.append(
                (
                    score.full_match_rank,
                    score.rank_points,
                    score.f_max,
                    score.n_predictions_at_f_max,
                )
            )
            self.assertEqual(score.f_max_threshold, epcr)
        self.assertEqual(len(set(results)), 1)

    def test_lower_insurance_pair_is_neutral_only_when_true_pair_is_top(self) -> None:
        true_pair = self.row(epcr=0.5)
        lower_false_pair = self.row(
            chrom_1="chr1",
            pos_1=1,
            ref_1="A",
            alt_1="C",
            chrom_2="chr1",
            pos_2=2,
            ref_2="G",
            alt_2="T",
            epcr=0.4,
            finding_type="secondary",
        )

        score = score_rows(
            load_predictions(self.write_rows([true_pair, lower_false_pair])),
            TRUE,
        )

        self.assertEqual(score.rank_points, 100.0)
        self.assertEqual(score.f_max, 1.0)
        self.assertEqual(score.f_max_threshold, 0.5)
        self.assertEqual(score.n_predictions_at_f_max, 1)

    def test_insurance_cannot_restore_perfect_score_after_false_top_pair(self) -> None:
        false_pair = self.row(
            chrom_1="chr1",
            pos_1=1,
            ref_1="A",
            alt_1="C",
            chrom_2="chr1",
            pos_2=2,
            ref_2="G",
            alt_2="T",
            epcr=0.6,
        )
        lower_true_pair = self.row(epcr=0.5)

        score = score_rows(
            load_predictions(self.write_rows([false_pair, lower_true_pair])),
            TRUE,
        )

        self.assertEqual(score.full_match_rank, 2)
        self.assertEqual(score.rank_points, 50.0)
        self.assertAlmostEqual(score.f_max, 2 / 3)

    def test_compound_pair_order_does_not_matter(self) -> None:
        row = self.row(
            chrom_1="chr7", pos_1=101_249, ref_1="c", alt_1="t",
            chrom_2="chr7", pos_2=101_001, ref_2="a", alt_2="g",
        )
        rows = load_predictions(self.write_rows([row]))
        score = score_rows(rows, TRUE)
        self.assertEqual(score.rank_points, 100.0)
        self.assertEqual(score.f_max, 1.0)

    def test_single_true_allele_gets_half_rank_credit(self) -> None:
        row = self.row(chrom_2="", pos_2="", ref_2="", alt_2="")
        rows = load_predictions(self.write_rows([row]))
        score = score_rows(rows, TRUE)
        self.assertEqual(score.rank_points, 50.0)
        self.assertAlmostEqual(score.f_max, 2 / 3)

    def test_partial_second_allele_is_rejected(self) -> None:
        row = self.row(alt_2="")
        with self.assertRaisesRegex(SubmissionError, "all-or-none"):
            load_predictions(self.write_rows([row]))

    def test_epcr_must_already_be_ranked(self) -> None:
        first = self.row(epcr=0.5)
        second = self.row(
            chrom_1="chr1", pos_1=1, ref_1="A", alt_1="C",
            chrom_2="", pos_2="", ref_2="", alt_2="", epcr=0.8,
        )
        with self.assertRaisesRegex(SubmissionError, "strictly decreasing"):
            load_predictions(self.write_rows([first, second]))

    def test_epcr_ties_are_rejected(self) -> None:
        first = self.row(epcr=0.8)
        second = self.row(
            chrom_1="chr1", pos_1=1, ref_1="A", alt_1="C",
            chrom_2="", pos_2="", ref_2="", alt_2="", epcr=0.8,
        )
        with self.assertRaisesRegex(SubmissionError, "ties enter"):
            load_predictions(self.write_rows([first, second]))

    def test_utf8_bom_is_rejected(self) -> None:
        path = self.write_rows([self.row()])
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        with self.assertRaisesRegex(SubmissionError, "BOM"):
            load_predictions(path)

    def test_in_memory_validator_uses_the_same_contract(self) -> None:
        path = self.write_rows([self.row()])
        self.assertEqual(load_predictions_bytes(path.read_bytes()), load_predictions(path))

    def test_reordered_header_is_rejected(self) -> None:
        row = self.row()
        reordered = list(REQUIRED_FIELDS)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        values = [str(row[field]) for field in reordered]
        path = self.write_text(",".join(reordered) + "\n" + ",".join(values) + "\n")
        with self.assertRaisesRegex(SubmissionError, "header order"):
            load_predictions(path)

    def test_symbolic_ref_is_rejected(self) -> None:
        with self.assertRaisesRegex(SubmissionError, "REF must"):
            load_predictions(self.write_rows([self.row(ref_1="<DEL>")]))

    def test_out_of_contig_position_is_rejected(self) -> None:
        with self.assertRaisesRegex(SubmissionError, "exceeds the GRCh38"):
            load_predictions(self.write_rows([self.row(chrom_1="chrM", pos_1=16_570)]))

    def test_spreadsheet_formula_note_is_rejected(self) -> None:
        with self.assertRaisesRegex(SubmissionError, "spreadsheet-formula"):
            load_predictions(self.write_rows([self.row(notes="=HYPERLINK(\"https://example.test\")")]))

    def test_duplicate_header_is_rejected(self) -> None:
        header = list(REQUIRED_FIELDS)
        header[-1] = "epcr"
        path = self.write_text(",".join(header) + "\n")
        with self.assertRaisesRegex(SubmissionError, "duplicates"):
            load_predictions(path)

    def test_surplus_csv_field_is_rejected(self) -> None:
        row = self.row()
        values = [str(row[field]) for field in REQUIRED_FIELDS]
        path = self.write_text(",".join(REQUIRED_FIELDS) + "\n" + ",".join(values + ["extra"]) + "\n")
        with self.assertRaisesRegex(SubmissionError, "surplus"):
            load_predictions(path)

    def test_secondary_findings_must_be_last(self) -> None:
        first = self.row(epcr=0.9, finding_type="secondary")
        second = self.row(
            chrom_1="chr1", pos_1=1, ref_1="A", alt_1="C",
            chrom_2="", pos_2="", ref_2="", alt_2="", epcr=0.8,
            finding_type="primary",
        )
        with self.assertRaisesRegex(SubmissionError, "must precede"):
            load_predictions(self.write_rows([first, second]))

    def test_two_single_true_rows_do_not_get_full_rank_credit(self) -> None:
        first = self.row(chrom_2="", pos_2="", ref_2="", alt_2="", epcr=0.9)
        second = self.row(
            chrom_1="chr7", pos_1=101_249, ref_1="C", alt_1="T",
            chrom_2="", pos_2="", ref_2="", alt_2="", epcr=0.8,
        )
        rows = load_predictions(self.write_rows([first, second]))
        score = score_rows(rows, TRUE)
        self.assertEqual(score.rank_points, 50.0)
        self.assertEqual(score.f_max, 1.0)

    def test_false_row_above_true_pair_reduces_both_metrics(self) -> None:
        false = self.row(
            chrom_1="chr1", pos_1=1, ref_1="A", alt_1="C",
            chrom_2="", pos_2="", ref_2="", alt_2="", epcr=0.9,
        )
        true = self.row(epcr=0.8)
        rows = load_predictions(self.write_rows([false, true]))
        score = score_rows(rows, TRUE)
        self.assertEqual(score.rank_points, 50.0)
        self.assertEqual(score.full_match_rank, 2)
        self.assertEqual(score.f_max, 0.8)


if __name__ == "__main__":
    unittest.main()
