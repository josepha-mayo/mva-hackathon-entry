# MVA Hackathon 2026 entry

Reproducible, privacy-first work for Sage Bionetworks' **Rare Disease, Real Kid: The MVA Hackathon 2026**.

## For judges — 30-second read

**One-sentence method claim:** exact correction supplies the participant-specific cellular positive control that a repurposed medicine must match, while lineage tracking prevents selection or cytostasis from masquerading as rescue.

| What it is | Where | One-command verify |
|---|---|---|
| A fail-closed decision contract for a BUB1B-associated MVA rescue hypothesis: it orders laboratory spend and refuses advancement on missing identity, function, exposure, or lineage provenance | [Judge package](reports/TRACK2_JUDGE_PACKAGE.md) — worked example, precedent table, candidate card, pipeline map | `python scripts/run_save_path_simulation.py` |
| 126 configured false-rescue scenarios blocked from advancing; the one constructed complete path still opens | [Save-path suite](tests/test_save_path.py) | `python -m unittest tests.test_save_path -q` |
| Frozen attempt-1 judged report and reproducible synthetic benchmark | links below | `python scripts/verify_track2_reproducibility.py .` |

Suggested reading order: [TRACK2_JUDGE_PACKAGE.md](reports/TRACK2_JUDGE_PACKAGE.md) → [the judged report](reports/josephmayo_track2_report.md) → [community toolkit](templates/community/README.md) → [external case replay](reports/TRACK2_EXTERNAL_CASE_REPLAY.md).

Why this is not just a test suite: the software is the executable form of a predeclared experiment contract. Its estimands, gate ordering, and identity checks decide which laboratory records are admissible and which culture spend may be declared next — a test suite checks code; this contract decides whether a proposed rescue measurement is even allowed to be interpreted. The save-path replay demonstrates the contract is non-vacuous (one constructed path advances) and the submission GO checker refuses self-certification — it reports NO-GO until five external attestation artifacts exist; the current bundle lives under [attestation/](attestation/) with a real Ed25519 detached signature and a FreeTSA RFC 3161 timestamp token. Commands below are PowerShell; all `python` invocations are shell-agnostic and `$env:MVA_PRIVATE_ROOT` reads as `$MVA_PRIVATE_ROOT` under bash.

## Verified status snapshot (updated 2026-09-19; public portal facts last live-checked 2026-09-01)

- Official challenge contract, scoring code, and templates inspected. Track 1 has a public Rank-Points / F-max leaderboard. Track 2 has no live leaderboard: JSON is stored under a private `track2/` folder and is never rendered or auto-scored. The panel reviews only the latest of three qualitative uploads.
- Registration, access, secure-storage, and machine receipts remain private operational records and are not published in this repository.
- Controlled-data processing occurs only in the separate local private root; gated source files and verbatim phenotype text are excluded from this tree.
- Track 1 official automated score is at the scoring ceiling: 100.0 rank points and F-max 1.000. Do not spend another Track 1 attempt unless the contract changes or a demonstrably stronger qualitative package is ready.
- Public participant outputs remain segregated landscape context and are not ranking inputs. Every answer-bearing release surface uses one fixed path and an exact-byte release digest.
- Track 1 allows six attempts per registered participant; only the best automated score is displayed. Track 2 allows three submissions per team; organizers review only the latest Track 2 entry. Team records: Track 2 attempt 1 has been submitted; attempts 2 and 3 have not. This repository does not publish a live portal remaining-attempt counter.
- The local scorer matched all fields from the pinned official evaluator in 10,000 deterministic randomized synthetic cases.
- A 600-case synthetic inheritance component benchmark recovered all 500 positive truths and all 200 compound-pair truths, excluded every confirmed-cis pair, and intentionally retained 60 unresolved distractor pairs. This validates enumeration invariants only, not biological ranking.
- The Track 2 living draft now proposes a correction-trained **two-lane** discovery program, not a treatment: a small targeted mechanism lane plus a phenotype lane drawn from the current marketed/available subset of an approved-medicine collection through a qualified screening partner. Its v3 paired hierarchical fixed-cohort aggregate-count benchmark passed all 22 configured gates across 22,000 comparisons: strong-effect generation was flagged in 90.5% of comparisons and produced a clean advanceable signal in 65.5% under the enforced pediatric completion band; the same rescue contaminated by moderate cytostasis produced zero clean signals; a true rescue pushed just outside the completion-band edge produced one clean signal in 1,000; a marginal-preserving selective-follow-up attack on the follow-up audit produced a bounded 260/1,000 clean false-advance rate (declared ceiling 40%), quantifying a disclosed residual hole; and a zero-division degenerate arm was refused in 1,000/1,000 comparisons. The maximum false-generation 95% Wilson upper bound across required non-generation confounds was 0.564%, and a predeclared five-seed sensitivity sweep passed 5/5 supplementary seeds with a seed-invariant false-generation ceiling. These are synthetic software-behavior measurements, not biological validation, treatment efficacy, or real-study power.
- Phase 2 adds a separate timestamped lineage/competing-risk contract, a fail-closed Track 2 candidate evidence ledger, an A0 to A1 scarce-material contract, and the living method surfaces listed below. Nested identity and function gates refuse RNA as genomic confirmation, unmatched-line DNA/RNA/phase/function as assay-matched evidence, computational transcript or phase as molecule-level identity, analog or computational missense as an exact wet defect, unlabeled or analog recreation as exact restoration, analog, unmatched-line, ectopic, cell-free, imposed-stress, or computational correction as genetic reversal, geometry ranking or a computational predictor as a functional assay, a public software catalog or official medicine label as positive exact-allele, checkpoint, direct-target, or human-PD ledger evidence or as a lead or conditional-hold row, a public software catalog as a pharmacologic ranking role, a public database or ontology record as a pharmacologic ranking role or lead-advancement row, a derived_evidence row that inherits a catalog, label, database, or ontology parent as those same roles, a mechanistic-control or no-go ledger row as a remaining conditional probe, a challenger or comparator as the active lead, two labeled leads, a synthetic fixture labeled as public evidence, a public source labeled as synthetic, a parked comparator-only ledger row as a promote decision, a demoted ledger row as a remaining conditional probe, an oncology-stop, unassessed-oncology, unassessed-exposure, expired-eligibility, or nontranslational-high row as a remaining conditional probe, a mixed-or-unsafe functional hit as a remaining conditional probe, a no-go or exclude row as anything other than rejected, literature proof wording as exact-allele function, absent or unassessed pediatric information as displacement-eligible or as an active lead, and observed identity, stability, probe, or endpoint labels that omit nested confirmation, phase, transcript, hypomorph, exposure, or concordance objects. Reciprocal recreation is required. Geometry ranking runs in the stop-early pipeline before confirmation. Sample stewardship v17 and candidate ledger v7 fail closed on both discovery lanes, cumulative sample debits, context qualification, and blinded independent replication. The identifier-free search protocol is `track2-candidate-search-v3`; `searched_on` remains 2026-09-01 and that axis bump is not a completed literature refresh. A signal confined to a renewable 2-D surrogate remains `mechanism_only`; it cannot become a child-relevant claim. The living code, tests, templates, and selected methods reports are **not** part of the frozen attempt-1 judged packet or its v3 aggregate receipt. None authorizes a new Track 2 upload. Operator confirmation on 2026-08-29: keep iterating through the close date; do not submit without the exact authorization phrase.

## Track 1 release surfaces

- [Proposed one-row prediction CSV](submissions/track1/josephmayo_track1_bub1b_pair.csv)
- [Methods and evidence report](reports/josephmayo_track1_report.md)
- [Exact-byte release manifest](release/release-artifacts.json)

The proposed causal pair is a research hypothesis, not a confirmed molecular diagnosis. Phase and the missense mechanism remain unresolved, and the report states the decisive confirmation path.

## Track 2 frozen attempt-1 judged surface

- [Drug-repositioning research report](reports/josephmayo_track2_report.md)
- [Three-minute pitch script and storyboard](reports/josephmayo_track2_pitch_script.md)
- [Generation-versus-selection benchmark receipt](reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json)
- [Receipt-bound benchmark configuration](configs/track2-generation-selection-benchmark.json)
- [Predeclared five-seed sensitivity receipt](reports/TRACK2_SEED_SENSITIVITY.json) and [sweep configuration](configs/track2-seed-sensitivity.json)
- [Transitive reproducibility manifest](release/track2-reproducibility.json)

These are the currently judged attempt-1 surfaces. They remain frozen and reproducible; living Phase-2 files below do not silently replace them.

## Track 2 living Phase-2 research surface (not uploaded or judged)

- [Timestamped lineage contract](reports/TRACK2_LINEAGE_CONTRACT.md)
- [Lineage adversarial receipt](reports/TRACK2_LINEAGE_ADVERSARIAL.json)
- [Allele-confirmation contract](reports/TRACK2_ALLELE_CONFIRMATION.md)
- [Clone-safety contract](reports/TRACK2_CLONE_SAFETY.md)
- [Exposure-gate contract](reports/TRACK2_EXPOSURE_GATE.md)
- [Program gates](reports/TRACK2_PROGRAM_GATES.md)
- [Hypothesis-strength contract](reports/TRACK2_HYPOTHESIS_STRENGTH.md)
- [Identifier-free research plan](reports/TRACK2_RESEARCH_PLAN.md)
- [False-rescue literature bound](reports/TRACK2_FALSE_RESCUE_LITERATURE.md)
- [External false-rescue case replay](reports/TRACK2_EXTERNAL_CASE_REPLAY.md)
- [Attempt-2 software delta](reports/TRACK2_ATTEMPT2_DELTA.md)
- [Phase 2 scale plan](reports/PHASE2_SCALE_PLAN.md)
- [Session handoff (continue; do not submit)](reports/TRACK2_SESSION_HANDOFF.md)
- [Judge package: worked example, precedent table, candidate card](reports/TRACK2_JUDGE_PACKAGE.md)
- [Judge self-score rubric](reports/TRACK2_JUDGE_RUBRIC.md)
- [Method-delta comparison](reports/TRACK2_METHOD_DELTA.md)
- [Coordinate-only geometry reproducer](reports/TRACK2_COORDINATE_GEOMETRY.md)
- [Synthetic coordinate-geometry receipt](reports/TRACK2_COORDINATE_GEOMETRY_SYNTHETIC.json)
- [Candidate-ledger future-release contract](reports/TRACK2_CANDIDATE_RELEASE_CONTRACT.md)
- [Scarce-sample stewardship contract](reports/TRACK2_SAMPLE_STEWARDSHIP.md)
- [AI / LLM methods line](reports/TRACK2_AI_LINE.md)
- [Candidate evidence-ledger template](templates/track2_candidate_ledger.synthetic.json)
- [Scarce-sample stewardship template](templates/track2_sample_stewardship.synthetic.json)
- [Candidate search protocol](configs/track2-candidate-search-protocol.json) (`track2-candidate-search-v3`; `searched_on` 2026-09-10 — the catalog-refresh pass found no primary wet assay; frequency, conservation, ClinVar, a public software catalog, software proof wording, and an official medicine label are exclusion axes, not hits)
- [Community handoff toolkit](templates/community/README.md)

Nicotinic acid and arimoclomol remain branch-conditional laboratory probes in the targeted lane; neither is a lead, treatment, dose recommendation, or reason to administer a medicine. The conditional NAPRT→NAD→SIRT2 challenger is retained in the private candidate ledger only — it is not part of the bound attempt report and has no exposure-gate eligibility. Analog, homolog, nearby, unmatched-line, ectopic, cell-free, imposed-stress, or computational correction cannot stand in for exact genetic reversal of an assay-matched missense defect. Unlabeled recreation cannot restore that defect. Before any phenotype screen, a renewable exact-genotype/corrected system must reproduce the correction-defined signature and assay separability. Only a valid participant A1 signal may spend resource-intensive native-lineage material. Advancement additionally requires measured exposure, matched-control safety, architecture/lineage qualification, clone safety, frozen confirmation, analytic transfer, and biologically independent replication. The plausible postnatal objective is reducing ongoing chromosome-missegregation or abnormal-clone risk, not reversing established prenatal injury.

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
python scripts/run_seed_sensitivity.py --config configs/track2-seed-sensitivity.json --output local_dev/track2-seed-sensitivity.json
python scripts/run_lineage_adversarial_benchmark.py --output local_dev/track2-lineage-adversarial.json
python scripts/export_lineage_counts.py --fixture clean_generation --output local_dev/track2-lineage-counts.json
python scripts/rank_candidate_ledger.py --input templates/track2_candidate_ledger.synthetic.json --public-only
python scripts/render_candidate_release_bundle.py --input templates/track2_candidate_ledger.synthetic.json --output-dir local_dev/candidate-release-synthetic
python scripts/assess_clone_safety.py --input templates/community/lineage_count_table.synthetic.json
python scripts/assess_exposure_gate.py --input templates/community/measured_exposure_table.synthetic.json
python scripts/assess_program_gates.py --replication templates/community/replication_decision.synthetic.json
python scripts/assess_program_gates.py --concordance templates/community/lineage_count_table.synthetic.json
python scripts/run_community_gates.py --community templates/community
python scripts/run_save_path_simulation.py
python scripts/assess_method_delta.py
python scripts/assess_next_experiment.py --worksheet templates/community/causal_chain_worksheet.synthetic.json
python scripts/assess_assay_power.py --plan templates/community/assay_power.synthetic.json
python scripts/assess_sample_stewardship.py --plan templates/track2_sample_stewardship.synthetic.json
python scripts/run_coordinate_geometry.py --pdb templates/community/coordinate_model.synthetic.pdb --chain A --target 10 --comparators 20 30 --source-name coordinate_model.synthetic.pdb --ca-shell 6 --sidechain-contact 1.5 --polar-proximity 1.5
python -m unittest tests.test_allele_confirmation tests.test_clone_safety tests.test_exposure_gate tests.test_program_gates tests.test_community_pipeline tests.test_lineage tests.test_save_path tests.test_structure_ranking tests.test_coordinate_geometry tests.test_next_experiment tests.test_phase_monte_carlo tests.test_assay_power -q
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
