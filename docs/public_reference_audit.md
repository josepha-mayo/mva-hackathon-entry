# Check the reference before interpreting an assay

The reference-audit runner checks one public transcript record against an
independently obtained protein sequence, then computes hypothetical single-
base substitutions. It performs no network requests and reads no challenge
data. Supply public reference files acquired directly from their providers.

```text
python scripts/audit_public_reference.py --help
python -m unittest tests.test_reference_audit -v
```

Required arguments are `--genbank`, `--fasta`, `--expected-version`,
`--expected-sha256`, and one or more `--change` values of the form
`coding-position:alternate-base`. The version and exact source digest must
match. Each substitution is computed independently; a list is not a phased
haplotype. Output is written to standard output. A parsing or concordance
failure returns exit code 2 and produces no result on standard output.

The runner accepts a single complete contiguous CDS in the standard nuclear
code. Its translation must match both the annotated translation and the
independent FASTA. Ordered exon coordinates must partition the transcript.
Unsupported partial, joined, nonstandard-code or recoded CDS records are
rejected rather than approximated.

The result contains coding and transcript coordinates, exon membership,
reference and alternate codons, translated residues, downstream-junction
offsets and the ideal tryptic peptide spanning the substituted position.
Trypsin is modeled as cleavage after lysine or arginine unless followed by
proline, with no missed cleavages. A premature stop yields a truncated
hypothetical protein, with no peptide at the replaced residue.

For the public references checked during this audit, the proposed missense
substitution creates a cleavage site: the spanning reference peptide is
34 residues long, while the alternate spanning peptide is three residues.
The proposed stop maps to an upstream exon and changes a leucine codon to
an opal stop. Exact reference identities, source hashes and full results are
recorded in the accompanying research review; no sample call or phase is
established by these calculations.

## Why this changes the first experiment

An altered peptide signal can reflect digestion or analytical response
instead of protein amount. Qualify invariant peptides, recovery and an
orthogonal full-length assay. If two alleles supply full-length protein,
their combined invariant signal cannot identify each allele's contribution.

Likewise, the amino acid inserted by a suppressor matters. Two reagents that
decode the same stop can make different proteins. A nearby exon junction
supports a transcript-fate hypothesis; only qualified RNA measurements can
establish expression and splicing.

The computation establishes neither proteome uniqueness, peptide
detectability, mutant protein function, pathogenicity, a medicine response
nor clinical benefit. It is a research supplement outside the frozen signed
release, not an automatic advancement gate.
