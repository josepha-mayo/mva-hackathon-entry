# Exact public-source research review

Reviewed 22–23 October 2026 by Codex in the user-authorized repository audit.

The new reference parser, invented test fixtures and two literature cards
contain public reference biology and published research. They contain no
downloaded challenge data, private clinical record or credential. The case
labels discussed in the cards were already present in the public entry;
their discussion does not independently confirm those calls or their phase.

The unchanged privacy scanner conservatively flags biological words and
short strings. In the reference code its findings are format labels,
standard nuclear-code table rows, cleavage residues and invented peptide
fixtures. In the literature cards they are public gene, variant and source
names. These findings are retained, not hidden through string rewriting.
The content was reviewed under the public-code, methods and allowed-evidence
scope in [data governance](../DATA_GOVERNANCE.md).

[The exact review record](../release/research-supplement-review.json) binds
each reviewed source's bytes and unchanged scanner diagnostics. Run:

```text
python scripts/check_research_supplement.py .
python -m unittest tests.test_reference_audit tests.test_research_supplement -v
```

The comparison fails for byte drift, diagnostic drift, duplicate or escaping
paths, and any non-identifier finding, even if it is prelisted. Its output is
an exact-review comparison, not a privacy allowance or release approval. It
neither changes the five fixed release roles nor substitutes an alternative
release manifest. The frozen policy and signed baseline are unchanged.

The all-history privacy gate remains **NO-GO**, including historical unbound
report edits and identifier findings. This review does not clear history,
adopt the prepared operator statements, countersign an attestation, or cover
a new final report. It grants no biological or clinical advancement. A test
pass proves specified software behavior only.

The last completed all-history scan was at the prior public checkout.
Subsequent long-running attempts were interrupted and produced no completed
result. The current exact-file content review is separate; no whole-tree or
all-history clearance is inferred from it.
