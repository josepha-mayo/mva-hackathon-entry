# External false-rescue case replay (identifier-free method note)

Status: public method note. This file names no subject-specific gene, allele, or medicine. It does not authorize an upload, and it is not a reanalysis of any primary dataset.

## The published case

A 2026 fly neural-stem-cell checkpoint-depletion microcephaly model (public index: PubMed 41820377; see `reports/TRACK2_FALSE_RESCUE_LITERATURE.md`) reported that genetic interventions boosting mitochondrial chaperones, radical-oxygen scavengers, or apoptosis blockade **restored organ size and/or progeny counts without fully restoring the aneuploid stem-cell count**.

That outcome structure is the canonical false-rescue pattern this method exists to refuse: a bulk or organ-level improvement driven by coping, selection, or death-masking rather than by fewer new segregation errors.

## What was encoded — and what was not

The publication reports organ-level and population-count endpoints, not per-division error rates. This replay therefore encodes the **published outcome structure** as gate inputs — improved progeny survival with unchanged new-error generation — not the primary measurements. Two independent layers of the contract are exercised:

- **Wording layer:** the published claim-shape "organ size restored" is offered as support for "checkpoint rescued."
- **Measurement layer:** a lineage table is configured so the treated arm's error-line daughters survive and reproduce far more than vehicle, while the per-completed-division error rate is unchanged — the structure an apoptosis-blockade or coping intervention produces.

Both layers are real configured inputs run through the same gates and analyzer as every other scenario; nothing was special-cased.

## Layer 1 — evidence gate replay

The save-path scenario `organ_size_overclaim` appends an observed evidence link asserting "Organ size restored after the probe" in support of "checkpoint rescued." Verified suite outcome:

- `blocked_by`: `evidence`
- `reason`: `observed_overclaim`
- `program_effect`: `stop`

Because the evidence gate runs first in the pipeline (before confirmation, phase, transcript, hypomorph, exposure, count identity, assay power, clone safety, and concordance), the overclaim is refused before any downstream spend is declared. This is the intended ordering: a bulk-outcome claim cannot purchase interpretation rights it has not earned.

## Layer 2 — lineage-analyzer replay

The adversarial fixture `preservation` encodes the measurement structure directly: identical opportunity and completion counts across arms, identical per-division error rates, but sharply higher error-line daughter survival and reproduction under treatment — the signature of an intervention that rescues abnormal progeny rather than preventing new errors.

Verified analyzer output (`analyze_lineage_study` on `build_adversarial_fixture("preservation")`, 2026-09-19):

| Estimand | Treatment/vehicle ratio | Interval | Reading |
|---|---|---|---|
| `generation_rate` | 1.00 | [0.61, 1.63] | No reduction in new segregation errors per completed division |
| `founder_error_bearing_completion` | 1.00 | [0.61, 1.64] | No reduction per enrolled founder either — both co-primary endpoints flat |
| `division_completion` | 1.00 | [0.93, 1.07] | No cytostasis confound |
| `relative_error_daughter_reproduction` | 17.0 | [3.26, 88.8] | Error-line daughters reproduce far more under treatment — the preservation signature |
| `pre_division_death` | 1.00 | [0.27, 3.66] | Compatible with no death change |
| `dropout` | inestimable | `no_observed_events` | Honest zero-cell reporting, not a fabricated interval |

Result: biological flag `error_daughter_preservation` set; interpretation `mixed_components`; the case cannot report `generation_reduction_without_detected_configured_confound`. A pipeline receiving this table therefore cannot certify rescue even when no author phrases an overclaim — the measurement structure itself refuses it.

## What this demonstrates — and what it does not

This replay demonstrates that a **real, externally published false-rescue pattern** — not a scenario authored to fit the gates — is refused at two independent layers: the claim-wording layer stops the overclaim before spend, and the measurement layer flags the preservation mechanism even when reporting is honest.

It does not demonstrate that every external false-rescue story is covered, that the encoded structure reproduces the paper's primary data, or that any biological claim about the fly result is validated. The save-path matrix remains configured software cases; this replay adds one externally motivated case to the demonstrated coverage.

## Reproduce

```powershell
python scripts/run_save_path_simulation.py
python -c "import sys; sys.path.insert(0,'src'); from mva_hackathon.lineage import build_adversarial_fixture, analyze_lineage_study; r = analyze_lineage_study(build_adversarial_fixture('preservation')); print(r['interpretation'], [k for k,v in r['flags'].items() if v])"
```

All `python` invocations are shell-agnostic.
