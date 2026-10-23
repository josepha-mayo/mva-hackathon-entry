"""Invented reference fixtures; no participant or therapeutic results."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mva_hackathon.reference_audit import ReferenceAuditError, audit_public_reference


GB = b'''LOCUS       SYNTHETIC 18 bp
VERSION     SYNTHETIC.1
FEATURES             Location/Qualifiers
     exon            1..6
     CDS             1..18
                     /translation="MLNAK"
     exon            7..12
     exon            13..18
ORIGIN
        1 atgttaaatgctaaataa
//
'''
FASTA = b'>independent invented protein\nMLNAK\n'


class ReferenceAuditTests(unittest.TestCase):
    def audit(self, gb=GB, fasta=FASTA, changes=None, **overrides):
        kwargs = {"expected_version": "SYNTHETIC.1", "expected_genbank_sha256": hashlib.sha256(gb).hexdigest()}
        kwargs.update(overrides)
        return audit_public_reference(gb, fasta, changes if changes is not None else [(5, "G"), (9, "G")], **kwargs)

    def test_codon_and_exon_arithmetic_independently_specified(self):
        result = self.audit()
        stop, missense = result["changes"]
        self.assertEqual((stop["reference_codon"], stop["alternate_codon"]), ("TTA", "TGA"))
        self.assertEqual((stop["amino_acid_position"], stop["exon_number"], stop["exon_position"]), (2, 1, 5))
        self.assertEqual(stop["downstream_junction_offsets_from_codon_end"], [6])
        self.assertEqual((missense["reference_codon"], missense["alternate_codon"]), ("AAT", "AAG"))
        self.assertEqual(missense["transcript_position"], 9)
        self.assertIsNone(stop["alternate_tryptic_peptide"])

    def test_substitutions_are_independent_and_change_cleavage(self):
        result = self.audit()
        missense = result["changes"][1]
        self.assertEqual(missense["reference_tryptic_peptide"]["sequence"], "MLNAK")
        self.assertEqual(missense["alternate_tryptic_peptide"]["sequence"], "MLK")
        self.assertEqual(missense, self.audit(changes=[(9, "G")])["changes"][0])

    def test_version_and_digest_cannot_drift_silently(self):
        for kwargs in ({"expected_version": "SYNTHETIC.2"}, {"expected_genbank_sha256": "0" * 64}, {"expected_genbank_sha256": "bad"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ReferenceAuditError):
                self.audit(**kwargs)

    def test_proline_prevents_the_new_tryptic_cut(self):
        gb = GB.replace(b'atgttaaatgctaaataa', b'atgttaaatcctaaataa').replace(b'MLNAK', b'MLNPK')
        result = self.audit(gb, FASTA.replace(b'MLNAK', b'MLNPK'), [(9, 'G')])
        self.assertEqual(result['changes'][0]['alternate_tryptic_peptide']['sequence'], 'MLKPK')

    def test_nonstandard_translation_cannot_be_silently_reinterpreted(self):
        for qualifier in (b'/transl_table=2', b'/codon_start=2', b'/transl_except=(pos:4..6,aa:Leu)'):
            gb = GB.replace(b'ORIGIN', b'                     ' + qualifier + b'\nORIGIN')
            with self.assertRaises(ReferenceAuditError): self.audit(gb)

    def test_independent_protein_and_annotation_both_required(self):
        for gb, fasta in ((GB, FASTA.replace(b"MLNAK", b"MLKAK")),
                          (GB.replace(b'MLNAK', b'MLKAK'), FASTA),
                          (GB, FASTA + b'>second\nMLNAK\n')):
            with self.assertRaises(ReferenceAuditError): self.audit(gb, fasta)

    def test_unsupported_coordinates_and_missing_exon_coverage_fail(self):
        for old, new in ((b'CDS             1..18', b'CDS             join(1..6,7..18)'),
                         (b'exon            7..12', b'exon            8..12'),
                         (b'exon            13..18', b'exon            13..17'),
                         (b'CDS             1..18', b'CDS             1..21')):
            with self.assertRaises(ReferenceAuditError): self.audit(GB.replace(old, new))

    def test_ambiguous_bases_frame_and_stop_rejected(self):
        for old, new in ((b'atgttaaatgctaaataa', b'atgntaaatgctaaataa'),
                         (b'1..18\n                     /translation', b'1..17\n                     /translation'),
                         (b'atgttaaatgctaaataa', b'atgtgaaatgctaaataa'),
                         (b'atgttaaatgctaaataa', b'atgttaaatgctaaatac')):
            with self.assertRaises(ReferenceAuditError): self.audit(GB.replace(old, new))

    def test_invalid_duplicate_unchanged_and_terminal_stop_changes(self):
        for changes in ([], [(True, "G")], [(0, "G")], [(19, "G")], [(16, "G")],
                        [(5, "g")], [(5, "N")], [(5, "T")], [(5, "G"), (5, "G")], ["5:G"]):
            with self.subTest(changes=changes), self.assertRaises(ReferenceAuditError): self.audit(changes=changes)

    def test_cds_offset_uses_transcript_coordinates(self):
        # A two-base untranslated prefix shifts transcript and exon positions.
        gb = GB.replace(b'1..6', b'1..8').replace(b'7..12', b'9..14').replace(b'13..18', b'15..20')
        gb = gb.replace(b'CDS             1..18', b'CDS             3..20').replace(b'atgtt', b'ccatgtt')
        row = self.audit(gb)["changes"][0]
        self.assertEqual((row["transcript_position"], row["exon_position"]), (7, 7))
        self.assertEqual(row["downstream_junction_offsets_from_codon_end"], [6])

    def test_cli_executes_and_rejects_mismatched_reference(self):
        script = Path(__file__).resolve().parents[1] / "scripts/audit_public_reference.py"
        with tempfile.TemporaryDirectory() as directory:
            gb, fa = Path(directory) / 'reference.gb', Path(directory) / 'protein.txt'
            gb.write_bytes(GB); fa.write_bytes(FASTA)
            command = [sys.executable, '-B', str(script), '--genbank', str(gb), '--fasta', str(fa),
                       '--expected-version', 'SYNTHETIC.1', '--expected-sha256', hashlib.sha256(GB).hexdigest(), '--change', '9:G']
            good = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            fa.write_bytes(FASTA.replace(b'MLNAK', b'MLKAK'))
            bad = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2, bad.stderr)
            self.assertEqual(bad.stdout, '')


if __name__ == '__main__':
    unittest.main()
