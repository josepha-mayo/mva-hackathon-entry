# A faithful division

An experimental decision method for **Rare Disease, Real Kid: MVA 2026**.

The practical goal is to find a measurable way to improve chromosome
segregation while preserving healthy divisions and checking abnormal-clone
fitness. A fall in the number of abnormal cells alone cannot establish that.
No benefit to the child has been demonstrated.

## Start with the experiment

The proposed rescue route depends on an unresolved question: **where is
functional checkpoint protein being lost?** Low input, loss before assembly,
clearance after assembly, and protein that remains defective when abundant
can demand different experiments. A folding hypothesis must survive that
comparison before it earns a drug screen.

[The functional-supply experiment card](docs/functional_supply.md) turns this
question into competing predictions and a small, staged assay design. Its
executable counterexamples show three distinct mechanisms with the same
tenfold fall in bulk protein, and identical turnover curves with different
functional output. These are invented examples, not measurements in the child.

[The mechanism comparison](docs/mechanism_comparison.md) adds the measured
choices between delivery, maintenance and persistent functional damage,
matched-carrier correction controls, a distinct stop-restoration comparator,
and a variant-specific protein-measurement trap. It is a research supplement
outside the frozen signed release.

```sh
python scripts/demo_functional_supply.py
python -m unittest tests.test_functional_supply -v
```

Next, [the existing refusal demo](reports/TRACK2_DEMO_TRANSCRIPT.md) tests
whether a proposed functional improvement could instead be explained by
stopped divisions or selective daughter loss:

```sh
python scripts/demo_contract.py
```

The contribution is a linked set of decisions: establish the causal genotype,
locate a functional bottleneck, test an exposure-qualified rescue hypothesis,
then distinguish fewer new errors from selective loss of damaged cells.
Negative results retire hypotheses before scarce material is spent.

## What has actually been established

| Evidence | Supported conclusion | Remaining gap |
|---|---|---|
| Signed report and reproducible synthetic benchmarks | A checkable experiment contract and software behavior on configured scenarios | Exact-genotype biology and drug response |
| 126 configured unsafe paths blocked; one constructed complete path opens | The declared software gate is non-vacuous | Real assay calibration and independent replication |
| New functional-supply counterexamples | Bulk amount and turnover alone can be insufficient to identify mechanism or function | Qualified native measurements and independent input/recovery estimates |
| Historical Track 1 score recorded as 100 points | A previous automated result reported in the project record | Fresh authenticated portal verification |

The functional-supply supplement is a **research candidate outside the signed
release**. The frozen report remains the auditable baseline. No wet-lab result,
treatment recommendation, or new submission is established by these demos.

Read [JUDGES.md](JUDGES.md) for the frozen claims-to-evidence map, then the
[signed report](reports/josephmayo_track2_report.md) for its conditional probe
and alternatives. The public repository and its working supplements must not
be confused with the latest uploaded portal entry.

## Deadline and submission state

The official close is **24 October 2026 at 23:59 UTC** (**25 October at
00:59 WAT**). Current requirements are a PDF or Markdown report, repository,
and a three-minute YouTube/Vimeo pitch; the panel reviews the latest of at most
three Track 2 submissions. [Official challenge](https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026).

Requirements were checked against official source commit
`60e1c30e337ce6fe01813040dbe49979eb8c50aa` on 22 October. Live authenticated inspection on 22 October showed 1 of 3 Track 2 submissions
used and 2 remaining. No new submission was made in this audit. Final video
hosting still requires verification.

## Track 1 release surfaces

- [Proposed one-row prediction CSV](submissions/track1/josephmayo_track1_bub1b_pair.csv)
- [Methods and evidence report](reports/josephmayo_track1_report.md)
- [Exact-byte release manifest](release/release-artifacts.json)

The proposed causal pair is a research hypothesis, not a confirmed molecular diagnosis. Phase and the missense mechanism remain unresolved, and the report states the decisive confirmation path.

## Track 2 frozen signed surface

- [Drug-repositioning research report](reports/josephmayo_track2_report.md)
- [Three-minute pitch script and storyboard](reports/josephmayo_track2_pitch_script.md)
- [Generation-versus-selection benchmark receipt](reports/TRACK2_GENERATION_SELECTION_BENCHMARK.json)
- [Receipt-bound benchmark configuration](configs/track2-generation-selection-benchmark.json)
- [Predeclared five-seed sensitivity receipt](reports/TRACK2_SEED_SENSITIVITY.json) and [sweep configuration](configs/track2-seed-sensitivity.json)
- [Transitive reproducibility manifest](release/track2-reproducibility.json)

These files remain frozen and reproducible. Their signatures cover their recorded bytes; living research supplements do not replace them. Current portal status must be verified separately.

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
