# Track 1 packaging and scorer checklist

Status: **GO for the synthetic packaging contract; NO-GO for any claim of a
perfect real-case score or for upload.** This red-team review used only the
frozen public Space source, organizer templates, and synthetic placeholders. It
did not inspect an answer key, controlled input, or subject-derived output.

## Frozen evidence used

- Public Space revision recorded by the project:
  `d27c33953ecb0cfd7fa316c7cd93ff0ffb05cc1d`.
- `evaluation.py` SHA-256:
  `6d18b581e65a45e1ccc120071d588e740c2e42e983ff50704c60a40232b19180`.
- Track 1 submit-tab SHA-256:
  `d3733ec736388870f2519df600ee2bf64d1331100bccea924797c93683b83278`.
- CSV template SHA-256:
  `7b3ed41c091d34fb6c5622d049c7a3f46124211fc7ec02947e69daef8752755a`.
- Methods workbook SHA-256:
  `e160c3b12dff23584660de42fb13095ac1d592c991fff92714e6f7f6678249b4`.

These hashes establish the audit input, not the source that will necessarily be
live at submission time. Refresh and re-pin the official source before upload.

## One paired row versus insurance rows

For a final entry targeting both 100 rank points and F-max 1.000, submit one
primary paired row when the selected hypothesis is a compound pair.

Synthetic scorer cases establish the asymmetry:

| Submission shape | Rank points | Best F-max |
|---|---:|---:|
| Correct pair only at rank 1 | 100 | 1.000 |
| Correct pair rank 1, false pair below it | 100 | 1.000 |
| False pair rank 1, correct pair rank 2 | 50 | 0.667 |
| Two correct alleles as separate single rows | 50 | 1.000 |

A lower insurance row is metric-neutral only when the top pair is already
correct and has a distinct higher EPCR, because the threshold can exclude every
lower row. If the top row is wrong, no lower row can restore both perfect
metrics: the correct pair is no longer rank 1, and false alleles above its
threshold remain in the F-max union. `finding_type` is informational in the
published evaluator and does not remove a secondary row from scoring.

Insurance rows therefore add formatting, disclosure, and qualitative-review
risk without improving the chance of a perfect score. Use an alternative row
only as an explicitly predeclared model submission that knowingly trades the
perfect-score objective for coverage, never as an unreported hedge.

## EPCR semantics for unresolved phase

The organizer accepts `0 < epcr <= 1` and uses EPCR only to sort rows and define
thresholds. A one-row submission receives the same automated score for every
valid EPCR value.

An unresolved-phase pair has no defensible calibrated causal probability from
phase status alone. Unless a frozen held-out calibration supplies a probability,
treat EPCR as an **ordinal submission confidence**, disclose that interpretation
in the report, and do not use `1.0`. For a one-row unresolved-phase hypothesis,
the conservative project convention is the fixed two-significant-digit sentinel
`0.50`. It means “the sole rank-1 hypothesis required by the submission
contract,” not a 50% posterior probability. Avoid spurious precision. If a
validated calibration exists later, replace the sentinel with its frozen value
and describe the calibration population and limitations.

## Exact CSV contract

Use the organizer template's exact 12-column order:

```csv
proband_id,chrom_1,pos_1,ref_1,alt_1,chrom_2,pos_2,ref_2,alt_2,epcr,finding_type,notes
PROBAND01,chr1,100000,A,T,chr1,200000,G,C,0.50,primary,Synthetic placeholder; uncalibrated rank-1 pair; phase unresolved
```

The example coordinates and alleles are invented placeholders from the public
template contract; they are not a proposed finding.

Required conventions:

- UTF-8 without a byte-order mark; standard CSV quoting; one header row.
- `proband_id` exactly `PROBAND01`.
- GRCh38, the one-based VCF position field, and the exact chromosome,
  position, reference, and alternate
  representation present in the supplied VCF. Chromosome strings are compared
  literally; use its exact `chr` convention. Do not substitute an equivalent
  normalized representation at packaging time.
- Fill all four second-allele fields for a pair. Leave all four blank for a
  single-allele row. Pair order is score-invariant; use deterministic genomic
  order for reproducible bytes.
- Upper-case sequence alleles, integer positions, `primary` for the champion,
  and an optional concise note that does not begin with `=`, `+`, `-`, or `@`.
- At most ten rows. If any multirow model is intentionally submitted, use
  unique, strictly decreasing EPCR values and place every secondary after every
  primary.

## Official upload fields and artifacts

The Track 1 form requires:

- a signed-in Hugging Face account with an unused submission slot;
- optional Team / Display Name, otherwise the account display slug is used;
- a public GitHub URL beginning with `https://github.com/`;
- one predictions file with a `.csv` suffix;
- one methods report with a `.pdf` or `.md` suffix.

The report should answer every Track 1 workbook field, even though individual
questions are described as voluntary:

1. Team name.
2. Model number, one through six.
3. Detailed model or approach description.
4. Whether the CSV is automated output or manually curated.
5. Details of downstream manual review.
6. Public-only versus proprietary data use.
7. Detailed public data sources.
8. Detailed proprietary data sources, or `None`.
9. Ability to emit compound-heterozygous pairs versus singles only.
10. Handling of secondary or incidental findings.
11. Runtime and cost estimate.
12. Method abstract of at most 500 words, including method, strengths, and
    limitations.

Before authorization to upload, the project package additionally needs:

- the exact CSV and report frozen by byte digest;
- a sanitized public repository at a pinned commit;
- the matching method configuration, reference ledger, evidence ledger,
  calibration identity or explicit uncalibrated declaration, and runtime/tool
  provenance;
- a local strict-parser and scorer receipt plus a successful full test run;
- a privacy-gate receipt covering worktree, index, and reachable history;
- a verified upload order that starts with the predeclared champion and does
  not waste quota on byte-identical outputs;
- refreshed official rules/source and explicit user authorization for the
  actual publication and submission actions.

The public submit service stores leaderboard metadata and the uploaded report,
but its published code does not preserve the prediction CSV bytes or their
digest. Retain the exact authorized CSV and its freeze receipt independently.

## Final GO / NO-GO gate

- **GO:** exact synthetic schema, pair representation, EPCR bounds, scorer
  behavior, one-row strategy, and local validation are covered by tests.
- **GO with disclosure:** an unresolved-phase pair may be submitted as a
  research hypothesis using ordinal EPCR semantics; it may not be described as
  confirmed trans or as a calibrated probability.
- **NO-GO:** `epcr=1.0` for an unresolved, uncalibrated pair; separate single
  rows for a proposed compound pair; ties; or “secondary” insurance assumed to
  be excluded from scoring.
- **NO-GO:** claim of a real 100/1.000 result before the official service returns
  it. The hidden answer was not accessed in this audit.
- **NO-GO:** upload, publication, or quota use until the final controlled result,
  report fields, freeze, current contract, privacy receipt, and explicit user
  authorization all pass.
