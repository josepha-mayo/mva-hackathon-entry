# Track 2 allele-confirmation contract

Status: synthetic software contract plus a private-root runner. This document names no subject-specific gene, allele, or medicine.

The earlier incomplete prefix scan is not treated as confirmation. This contract exists so a later complete local read check can fail closed instead of over-calling two sparse k-mer counts.

## What it does

- Builds centered reference and alternate k-mers of length 31 and 51 from caller-supplied flanks.
- Counts those k-mers in FASTQ streams on both strands. A reverse-complement-only observation still counts.
- Labels each allele as both observed, alternate missing, reference missing, neither observed, insufficient, incomplete inputs, or malformed.

A call is `both_alleles_observed` only when **every** requested k-mer size sees at least eight reference counts and eight alternate counts, every FASTQ parsed to a complete record boundary, and the lane set is complete:

- default expected file count is 8
- filenames that carry mate tokens must pair
- fewer than 8 files, unpaired mates, unlabeled mates on a multi-file set, a truncated last record, or a filename-digest mismatch all force `incomplete_inputs`

The nested community confirmation record also requires `library_molecule=genomic` and `confirmation_specimen=assay_matched`. An RNA or RNA-derived library, or an unlabeled library class, cannot pass even when those k-mer and layout floors are complete. Genomic DNA from an unmatched genotype line cannot stand in. `producer=synthetic_handoff` still does not require a FASTQ stream; it does require the genomic library class and an assay-matched specimen.

The private runner can require `--pinned-layout`. That checks a SHA-256 of sorted lowercase filenames from the pinned gated listing without storing those names in this public tree.

The private runner streams records. It does not load an 85 GB read list into memory.

## What it refuses to do

- Call variants.
- Infer phase.
- Treat two or three alternate observations as confirmation.
- Treat a truncated five-file download as confirmation even if k-mers look abundant.
- Treat an RNA or RNA-derived library as genomic confirmation even if k-mer floors are complete.
- Treat genomic DNA from an unmatched genotype line as the confirmed assay line.
- Run on files inside the public repository.
- Write read sequences into the public tree.

## How to run

Public tests use in-memory synthetic reads:

```powershell
python -m unittest tests.test_allele_confirmation -v
```

A later private run, after `MVA_PRIVATE_ROOT` is set, must keep the allele-flank config and FASTQs outside this checkout:

```powershell
python scripts/confirm_alleles_from_fastq.py --fastq-dir <private-fastq-dir> --output <private-layout.json> --layout-only --pinned-layout
python scripts/confirm_alleles_from_fastq.py --config <private-config.json> --fastq-dir <private-fastq-dir> --output <private-output.json> --expected-n-files 8 --pinned-layout
```

Write the output outside the public tree. Do not commit it.

## Local disk hunt (2026-08-29)

A machine-local hunt on this operator workstation found:

- `MVA_PRIVATE_ROOT` unset
- no directory with exactly eight FASTQ files
- one co-located VCF-plus-FASTQ directory whose FASTQ count is five (a truncated set)

That truncated set cannot confirm. Filenames, sample ids, and directory paths from the hunt were not copied into this tree. Confirmation still waits on an operator-supplied complete eight-lane private root outside the public checkout. Do not download the gated payload into this repository to manufacture that root.

## Claim boundary

Centered k-mer presence check only. Not a variant caller, not phase, not pathogenicity, and not efficacy.
