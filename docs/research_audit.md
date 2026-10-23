# Corrections to the historical timing and verification claims

Research supplement · 23 October 2026 · unsigned

The signed baseline preserves particular bytes and configured results. A
new audit found material defects in the assurances attached to some of those
results. **Do not use its lineage timing, neutral-selection or power labels
as a complete observation/safety certificate.** No biological result or
current submission clearance follows from the historical signature.

## Fixed-horizon daughter outcomes need an explicit observation plan

The preserved counterexamples can be reproduced with invented records:

```sh
python scripts/demo_legacy_lineage_timing.py
python scripts/demo_legacy_verification_power.py
```

The old report defines daughter reproduction within 48 hours, but
`src/mva_hackathon/lineage.py` counts reproduction labels regardless of their
timestamps. Its daughter vocabulary also lacks a fully observed, surviving
non-reproducer at the horizon. A constructed comparison passes the old
lineage and clone checks when vehicle daughters reproduce at six hours and
treatment daughters at 72 hours. Those late events do not belong in the
stated within-48-hour numerator.

The old `followup_hours_ratio` uses mother-attempt duration. It can therefore
mark a faster division as inadequate follow-up even when daughter histories
are equivalent. The old lock timestamp is parsed without being ordered after
the data. The count exporter includes daughter fates while exporting a latest
endpoint derived only from mother completion times.

The new [fixed-horizon assessor](../src/mva_hackathon/fixed_horizon.py) is an
explicitly limited correction of the timing/accounting question:

- Declare one prespecified postdivision horizon and all expected daughters.
- Record observation coverage separately from first reproduction or death.
- Retain continuously observed survivors without reproduction at the horizon.
- Keep missing or gapped observations in the denominator as unresolved bounds.
- Validate protocol-before-exposure, observation and adjudication-lock ordering.
- Retain planned horizon ends separately from latest recorded observations.

Genuine early terminal events can resolve the endpoint before the horizon;
unequal event times alone are not invalid follow-up. A first event after the
horizon is not an on-time reproduction. The bounds are descriptive missing-
outcome bounds, not confidence intervals or a censoring-adjusted estimator.
The example's 48 hours is inherited from the historical proposal, not a
qualified biological choice for a future study.

```sh
python scripts/assess_fixed_horizon.py --input templates/community/fixed_horizon.synthetic.json
python -m unittest tests.test_fixed_horizon -v
```

Sixteen semantic counterexample tests passed. This assessor does **not**
replace the full lineage/exposure/clone pipeline. It has no verified daughter
genotypes, error-positive/negative strata, clone identity or exposure binding.
It always returns `advancement_granted=false`. An old record without an
explicit timing plan cannot inherit its assurance. Any integrated replacement
needs an independently reviewed contract and a new operating-characteristic
study; a table of counts cannot supply the missing information.

## The old power assumptions do not describe the simulated daughters

`assay_power.py` says daughters are fully resolved, but its default builder
creates one reproduced and one not-followed daughter per completed division.
A captured invented replicate has 1,296 founders and 2,592 daughters, half
not followed, yet the old analyzer records a clean hit. This is a discrepancy
between the documented assumption and simulated records. It does not measure
a loss of biological power or provide a replacement estimate.

Keep the original configured receipts as historical outputs. Withdraw the
fully-resolved-daughter claim and any reading of that certificate as pricing
the complete fixed-horizon/clone-safety decision. A future simulation must
include the actual required observation process, competing outcomes and joint
decision. Existing focused lineage, power and supply tests still pass,
showing that the old tests did not cover these semantic failures.

## An external timestamp requires cryptographic verification

The historical `verify_all.py` timestamp helper compares JSON metadata and
requires a token of sufficient byte length. It accepts a constructed
non-DER text blob with matching JSON digest. It does not perform the OpenSSL
token/chain verification described in its opening text.

The actual historical token independently verifies. The new
[chain verifier](../src/mva_hackathon/timestamp_chain.py) parses the real
response, authenticates embedded certificates against independently pinned
PEM-file digests, verifies the signature and manifest imprint with OpenSSL,
then checks the claimed serial/time against the verified response. Pins were
checked against the [official FreeTSA page](https://freetsa.org/index_en.php)
on 23 October 2026. An arbitrary embedded root is not trusted. No new timestamp
or network request is made by this verifier; revocation status is not checked.

```sh
python scripts/verify_timestamp_chain.py .
python -m unittest tests.test_timestamp_chain -v
```

The verifier discovers OpenSSL on PATH or at Git for Windows' standard
bundled location; another installation can be supplied with `--openssl`. Missing OpenSSL is a
failure, not a metadata-only fallback. Six tests passed, covering the actual
response, a fabricated token, signature tampering, a changed manifest with
rewritten metadata, a false claimed timestamp and a cross-platform executable-
discovery guard. This verifies only the
old frozen manifest under the pinned chain and verifier conditions. It does
not sign new research or validate its scientific claims.

The original signed sources and receipt remain unchanged so the audit is
reproducible. These additions and the current manuscript are independently
scoped, unsigned research; the all-history privacy gate remains separate.

## Historical exposure thresholds do not rank the new medicines

The preserved exposure gate still calls concentrations above 5 micromolar
`nontranslational_high` and permits advancement only within its ≤2-micromolar
contract. These are historical probe-specific rules, not a universal clinical
ceiling. Do not use them to reject the 100-micromolar nominal PBA literature
condition or qualify a new neural profile. The [exposure-time audit](exposure_time_audit.md)
uses source-matched adult total AUC and clearly labeled assumptions instead;
neither this arithmetic nor the separate candidate ledger grants exposure
qualification. Frozen thresholds, baseline bytes and signatures are unchanged.
