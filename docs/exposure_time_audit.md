# Exposure over time: reproduce the arithmetic before choosing a profile

Public aggregate observations and declared assumptions · 23 October 2026.

This executed analysis tests an exposure argument. It does not simulate drug response, the child's pharmacokinetics or neural delivery. Its [inputs](../configs/published-exposure-inputs.json) distinguish the reported analyte, formulation, source cohort and interval. The [implementation](../src/mva_hackathon/published_exposure.py) runs offline:

```sh
python scripts/compare_published_exposure.py --output exposure-result.json
python -m unittest tests.test_published_exposure -v
```

## A peak comparison was insufficient

Diaz et al.'s adult UCD crossover study reported parent-PBA total-plasma AUC over 24 hours after each 14-day treatment period. Forty-four participants completed the study; formulations delivered equivalent PBA amounts at maintenance treatment. The following are aggregate exposure summaries, not the ammonia efficacy endpoint, raw individual profiles or pediatric MVA predictions. [Primary study](https://doi.org/10.1002/hep.26058)

| Formulation | Reported parent-PBA AUC, microgram·h/mL | Converted total plasma AUC, micromolar·h | Illustrative fixed-fraction free plasma AUC, micromolar·h |
|---|---|---|---|
| Glycerol phenylbutyrate | 433 | 2637 | 53–501 |
| Sodium phenylbutyrate | 508 | 3094 | 62–588 |

Conversion uses the parent free-acid molecular weight, 164.2011 g/mol: multiply microgram·h/mL by 1000/MW. Do not substitute the sodium salt, intact prodrug or phenylacetate. The last column multiplies by an **external in-vitro** free fraction of 0.02–0.19 from the label's 81–98% binding range. It is a sensitivity range, **not measured free AUC, a confidence interval or a patient bound**; binding can vary with concentration/time. [Label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=900e7dc0-9afe-4f50-80de-90567bb78519)

Hirata et al.'s relevant neural condition was nominal 100 micromolar PBA during 14 days of induction. A hypothetical **maintained** 100 micromolar condition integrates to 2400 micromolar·h over one day. That rectangle was not measured in the culture. Total adult plasma integrals are similar in magnitude, so a large total daily exposure mismatch cannot be asserted from these values. Free culture drug and free plasma drug can differ substantially; intracellular and neural exposure remain unknown. [Neural primary](https://doi.org/10.1038/s41598-020-70362-x)

Under fixed plasma-binding assumptions, equality with that assumed free-medium integral occurs at medium free fractions approximately **0.022–0.209** for glycerol PBA and **0.026–0.245** for sodium PBA. These are mathematical sensitivity values, not measured medium binding, a selection rule or a passing interval. Matching AUC would still leave peaks, troughs, temporal pharmacodynamics, tissue access and useful function unresolved. No 14-day human equivalence is claimed.

## Elamipretide gives a concrete temporal warning

FDA Table 7 reports matched healthy-volunteer summaries after seven days: mean Cmax 1370 ng/mL and AUC over the 24-hour interval 3850 ng·h/mL, n=5. Holding that peak for 24 hours would produce 32,880 ng·h/mL, **8.54 times** reported AUC. The rectangle is invented; no curve is reconstructed. This warns against using a plasma peak as a sustained culture profile. It neither ranks the medicines nor measures a neural exposure. [FDA primary review, printed page 26](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2025/215244Orig1s000IntegratedR.pdf)

## Scope correction for the old software gate

The preserved `exposure_gate.py` permits only its historical ≤2 micromolar window; values above 5 micromolar can be labeled `nontranslational_high`. Those frozen thresholds are an old probe-specific software contract, **not a universal clinical ceiling or evidence excluding the 100 micromolar nominal PBA literature condition**. The community pipeline still calls that gate; do not feed a new neural profile through it and call the result a drug judgment. This analysis leaves the old thresholds and signed release unchanged. Candidate-specific plausibility labels elsewhere also do not qualify an exposure bridge.

The useful next measurements are the actual free-medium/intracellular time course and function under a defensible drug-specific profile. Neither a favorable rectangle nor a software pass can supply them. Eleven focused tests and independent source/code review support this arithmetic artifact only.
