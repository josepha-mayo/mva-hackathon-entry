"""Parser, source-identity and numerical checks; fixtures are synthetic tests."""

from io import BytesIO
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.nall_source_data import (
    SOURCE_SHA256, SourceDataError, _read_sheet, _series,
    audit_workbook, describe, load_config,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "nall-source-data.json"


def fixture_archive(sheet_xml: str) -> BytesIO:
    """A tiny invented package exercises XML parsing, not scientific inference."""
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="example" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    data.seek(0)
    return data


class NallSourceDataTests(unittest.TestCase):
    def test_sample_SD_and_arithmetic_SEM_are_distinct(self):
        result = describe([1.0, 2.0, 3.0])
        self.assertEqual(result["mean_seconds"], 2)
        self.assertEqual(result["sample_SD_seconds"], 1)
        self.assertAlmostEqual(result["arithmetic_SEM_seconds"], 1 / math.sqrt(3))
        for values in ([1], [1, float("nan")], [1, float("inf")], [1, True], [1, 0], [1, -1], [1, "2"]):
            with self.subTest(values=values), self.assertRaises(SourceDataError):
                describe(values)

    def test_blank_cells_are_not_imputed_or_paired(self):
        cells = {"B2": "condition", "B3": 1.0, "B4": None, "B6": 3.0}
        values, addresses = _series(cells, "B", "condition", 2)
        self.assertEqual(values, [1.0, 3.0])
        self.assertEqual(addresses, ["B3", "B6"])
        with self.assertRaises(SourceDataError):
            _series(cells, "B", "condition", 3)
        with self.assertRaises(SourceDataError):
            _series(cells, "C", "condition", 2)

    def test_invalid_observations_are_rejected(self):
        for invalid in ("2", {"formula": True}, {"unsupported_type": "e"}, float("nan"), 0, -1):
            with self.subTest(invalid=invalid), self.assertRaises(SourceDataError):
                _series({"B2": "condition", "B3": invalid}, "B", "condition", 1)

    def test_duplicate_cell_and_missing_sheet_fail(self):
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        xml = f'<worksheet {ns}><sheetData><row r="3"><c r="B3"><v>1</v></c><c r="B3"><v>2</v></c></row></sheetData></worksheet>'
        with ZipFile(fixture_archive(xml)) as archive:
            with self.assertRaises(SourceDataError):
                _read_sheet(archive, "example")
            with self.assertRaises(SourceDataError):
                _read_sheet(archive, "missing")

    def test_formula_and_typed_string_are_not_accepted_as_cached_numbers(self):
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        for content in ('<f>1+1</f><v>2</v>', '<v>NaN</v>', '<v>bad</v>'):
            xml = f'<worksheet {ns}><sheetData><row r="2"><c r="B2" t="inlineStr"><is><t>condition</t></is></c></row><row r="3"><c r="B3">{content}</c></row></sheetData></worksheet>'
            with ZipFile(fixture_archive(xml)) as archive:
                with self.subTest(content=content), self.assertRaises(SourceDataError):
                    cells, _ = _read_sheet(archive, "example")
                    _series(cells, "B", "condition", 1)

    def test_altered_source_checksum_fails_before_extraction(self):
        config = load_config(CONFIG)
        with tempfile.TemporaryDirectory() as temporary:
            workbook = Path(temporary) / "altered.xlsx"
            workbook.write_bytes(b"not the published source workbook")
            with self.assertRaisesRegex(SourceDataError, "SHA-256 mismatch"):
                audit_workbook(workbook, config)

    def test_config_cannot_change_source_hash_or_ROI_schema(self):
        original = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(original["source"]["sha256"], SOURCE_SHA256)
        for change in ("hash", "count"):
            modified = json.loads(json.dumps(original))
            if change == "hash":
                modified["source"]["sha256"] = "0" * 64
            else:
                modified["targets"][0]["groups"][0]["expected_n"] = 90
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "config.json"
                path.write_text(json.dumps(modified), encoding="utf-8")
                with self.assertRaises(SourceDataError):
                    load_config(path)


if __name__ == "__main__":
    unittest.main()
