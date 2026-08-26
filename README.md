# MVA Hackathon 2026 entry

Reproducible, privacy-first work for Sage Bionetworks' **Rare Disease, Real Kid: The MVA Hackathon 2026**.

## Current status (2026-08-26)

- Official challenge contract, scoring code, templates, and public leaderboard inspected.
- Registration, access, secure-storage, and machine receipts remain private operational records and are not published in this repository.
- Controlled-data processing occurs only in the separate local private root; gated source files and verbatim phenotype text are excluded from this tree.
- The public leaderboard is saturated: at the 2026-08-26 18:07 UTC refresh, all 24 displayed entries scored 100 rank points and F-max 1.000.
- Public participant outputs remain segregated landscape context and are not ranking inputs. Every answer-bearing release surface uses one fixed path and an exact-byte release digest.
- No submission has been made. Track 1 allows six attempts; Track 2 allows one final attempt.
- The local scorer matched all fields from the pinned official evaluator in 10,000 deterministic randomized synthetic cases.
- A 600-case synthetic inheritance component benchmark recovered all 500 positive truths and all 200 compound-pair truths, excluded every confirmed-cis pair, and intentionally retained 60 unresolved distractor pairs. This validates enumeration invariants only, not biological ranking.
- The Track 2 report nominates one exposure-gated ex-vivo screening hypothesis, not a treatment. Its v3 paired hierarchical fixed-cohort aggregate-count benchmark passed all 14 configured gates across 14,000 comparisons: strong-effect generation detection was 90.6%, the maximum false-generation 95% Wilson upper bound across required non-generation confounds was 0.564%, and the sparse mixed case failed closed 85.2% of the time. These are synthetic software-behavior measurements, not biological validation, treatment efficacy, or real-study power.

## Track 1 release surfaces

- [Proposed one-row prediction CSV](submissions/track1/josephmayo_track1_bub1b_pair.csv)
- [Methods and evidence report](reports/josephmayo_track1_report.md)
- [Exact-byte release manifest](release/release-artifacts.json)

The proposed causal pair is a research hypothesis, not a confirmed molecular diagnosis. Phase and the missense mechanism remain unresolved, and the report states the decisive confirmation path.

## Track 2 release surface

- [Drug-repositioning research report](reports/josephmayo_track2_report.md)
- [Three-minute pitch script and storyboard](reports/josephmayo_track2_pitch_script.md)
- [Generation-versus-selection benchmark receipt](reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json)
- [Receipt-bound benchmark configuration](configs/track2-generation-selection-benchmark.json)
- [Transitive reproducibility manifest](release/track2-reproducibility.json)

The single lead is arimoclomol strictly as an exposure-gated ex-vivo probe. The proposal advances only after trans phase, an exact missense-allele defect, a prespecified chaperone-response signal at a conservative nominal concentration with measured medium and intracellular exposure, functional chromosome-segregation improvement, and clone-safety gates. It is not medical advice and does not support administering any medicine.

## Win condition

Track 1 is now a reproducibility and qualitative-review contest, not merely a gene-identification contest. The entry must independently verify exact alleles, read support, transcript consequence, inheritance/phase uncertainty, genome-wide alternatives, and blind spots. Public participant reports and leaderboard outputs are segregated landscape context and are forbidden as pipeline inputs.

Track 2 is the larger differentiation opportunity. Candidate medicines remain research hypotheses only. Every proposal must include an exposure-realistic, genotype-matched validation gate and a cancer-safety failure criterion; nothing in this repository is medical advice.

## Safety boundary

Controlled genomic and clinical files live outside this repository under a dedicated path supplied through `MVA_PRIVATE_ROOT`. See [DATA_GOVERNANCE.md](DATA_GOVERNANCE.md). The privacy gate blocks common genomic/raw-read formats, credentials, and oversized accidental additions.

Account-specific access records and machine-specific storage verdicts must remain in a private operations record outside this public tree.

## Local checks

```powershell
python -m unittest discover -s tests -v
python scripts/check_access.py
python scripts/privacy_gate.py .
python scripts/verify_track2_reproducibility.py .
python scripts/create_track2_reproducibility_manifest.py . --source-commit <40-hex>
python scripts/storage_preflight.py --root $env:MVA_PRIVATE_ROOT --mode minimal
python scripts/fetch_minimum.py --root $env:MVA_PRIVATE_ROOT
python scripts/differential_score_check.py --official-evaluation <pinned-space-checkout>\evaluation.py --expected-commit d27c33953ecb0cfd7fa316c7cd93ff0ffb05cc1d --cases 10000
python scripts/run_generation_selection_benchmark.py --config configs/track2-generation-selection-benchmark.json --output local_dev/track2-generation-selection.json
```

`fetch_minimum.py` is plan-only unless `--apply` is supplied. It refuses to make even a gated payload request unless storage passes the encryption, ACL, volume, path, and free-space checks; pins the dataset revision; uses private staging/cache paths; and intentionally omits the eight raw FASTQ files.

## Deterministic synthetic pipeline demonstration

Phase 1 includes one end-to-end, network-free CLI that exercises a declared Track 1 slot without controlled or participant-derived content. The checked-in miniature JSON bundle uses only `SYN`-namespaced labels and invented allele, phenotype, and annotation values. A raw VCF fixture is intentionally not included because the public privacy gate blocks both VCF filenames and VCF payload markers.

```powershell
python scripts/run_synthetic_pipeline.py `
  --slot-config configs/track1_slots/01-full-public-auto.json `
  --synthetic-bundle fixtures/synthetic-miniature-bundle.json `
  --output-dir local_dev/synthetic-slot-1
```

The output directory must not already exist. The CLI atomically writes exactly four artifacts:

- `submission.csv`: at most ten rows in the strict challenge schema, re-read by the existing submission validator.
- `evidence-ledger.json`: public-safe synthetic evidence rows plus an explicit not-assessable biological-validation gap, checked by the existing ledger validator.
- `provenance-runtime.json`: the existing public-provenance schema with the slot, offline boundary, engine digest/version, Python runtime, and deterministic-content policy. Timestamps and durations are omitted.
- `report-input.json`: sanitized counts, score components, slot settings, supported software claims, and scientific limitations for downstream report drafting.

The six predeclared configs can each be supplied unchanged. The demonstration applies their phenotype, gene-knowledge, evidence-scope, backend, and compound-pairing switches. The baseline backend is explicitly a synthetic surrogate branch; it does not execute Exomiser. EPCR values are strictly decreasing synthetic ordinals, not calibrated probabilities. This path validates schema composition, deterministic ranking behavior, artifact lineage, and fail-closed privacy boundaries only. It does **not** validate biological causality, diagnostic accuracy, real phenotype fit, read support, transcript consequence, or performance on controlled challenge data, and it does not upload or submit anything.

## Synthetic mechanism-contract checks

`mva_hackathon.mechanism` is a patient-agnostic, file-free component that
composes the validated inheritance candidates. It evaluates consequences only
on transcripts shared by both alleles, keeps unresolved phase out of the strict
pair lane, requires exact variant and gene agreement for pathogenic anchors,
and reports disease-condition relevance as a separate observation. Exact
priority ties receive a shared rank interval and midrank; an identifier affects
display order only.

The adapter boundary fails closed on undeclared evidence-confidence labels. A
multiallelic genotype such as the synthetic `1/2` test case is rejected unless
the target alternate and the allele represented by every depth are supplied
explicitly. These synthetic tests validate software invariants only. They do
not validate transcript annotations, disease relevance, biological causality,
diagnostic accuracy, or EPCR calibration.

## Official sources

- Challenge Space: <https://sagebio-rare-disease-real-kid-mva-hackathon-2026.hf.space/>
- Hugging Face Space repository: <https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026>
- Gated dataset: <https://huggingface.co/datasets/SageBio/mva-hackathon-2026-data>
- Official Space source commit audited initially: `d27c33953ecb0cfd7fa316c7cd93ff0ffb05cc1d`
- Official gated-dataset revision audited initially: `f534cb0c1a607110c6dad0194299bd3dd62df542`

## Attribution

The challenge scoring behavior is reimplemented from SageBio's public Space source, licensed CC BY 4.0. Public participant reports are used only as attributed landscape evidence and will not replace independent analysis of the gated data.

> This work was made possible through the Hackathon, organized by Sage Bionetworks in partnership with the MVA Society, Hugging Face, and BEACON (The Benchmarking, Evaluation, and Assessment Consortium for Science), with prize sponsorship from AWS and Anthropic. We are deeply grateful to the child and their family who generously contributed their data and their story to advance research into this rare disease. We acknowledge their trust in making this Hackathon possible.
