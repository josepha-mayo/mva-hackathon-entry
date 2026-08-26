# Track 1 official methods-form answers — pre-data draft

Pinned organizer template: Space commit `d27c33953ecb0cfd7fa316c7cd93ff0ffb05cc1d`; XLSX SHA-256 `e160c3b12dff23584660de42fb13095ac1d592c991fff92714e6f7f6678249b4`.

Status: exact organizer prompts are reproduced below for answer drafting. Bracketed values require the frozen controlled analysis or the final team name. Prepare one copy per submitted model; do not submit this Markdown file as a substitute for the official workbook.

## Team name

`[TEAM NAME]`

## Model number (fill out this form once per model/approach submitted; up to 6)

`S1 — full-public-auto` (`[replace with S2–S6 and that slot's single predeclared delta]`)

## Please describe your model/approach in detail.

The intended champion is a deterministic, CPU-capable, public-reference-only workflow. The implemented public scaffold currently validates schemas and submission semantics, records strict provenance, and conservatively enumerates a broad synthetic inheritance universe with explicit cis/trans/unresolved phase states. The remaining normalize, transcript annotation, mechanism/ploidy eligibility, phenotype reranking, calibration, and end-to-end ranking stages are not claimed complete until their executable artifacts and held-out results are frozen. The target method will validate the pinned single-sample GRCh38 VCF, freeze a diagnosis-label-blind universe before curated positive and negative HPO terms are loaded, and rerank without silently removing blind candidates. Its completeness ledger will distinguish `assessed`, `unsupported`, `not-assessable`, and `candidate-found` for structural, copy-number, repeat, mitochondrial, mosaic, noncoding, and other classes. Participant reports, leaderboard results, family communications, identity searches, and hosted APIs remain excluded from inputs and decisions. `[Replace this paragraph with the exact implemented pipeline, controlled result, validation evidence, and frozen artifact identifiers.]`

## Please state whether the submission file is the automated output of your computational approach (preferred), or if it has undergone downstream manual review and curation.

`[After the final freeze, state whether the CSV is the byte-identical direct output of the executable model and its slot-specific held-out calibration. Until that evidence exists, do not claim automated-output status.]` Manual review may not reorder candidates, edit EPCR values, or introduce coordinates.

## Please describe any downstream manual review in detail.

After automated output is frozen, review may annotate representation, transcript/mechanism coherence, phase uncertainty, callability, contradictory evidence, alternatives, limitations, and required clinical confirmation. Every action is logged. A discovered implementation defect invalidates the affected pre-submission freeze and requires a complete deterministic rerun; it is never repaired using leaderboard feedback.

## Please state whether your approach only used publicly available data (preferred) or if proprietary data was also used. If proprietary data were used, where possible, please also include a submission based only on publicly available data.

The method uses the organizer-provided controlled challenge inputs plus publicly available reference resources only. No proprietary reference, predictor, or hosted analysis service is used. `S1` is the public-reference champion; `S4` is the pinned public Exomiser baseline.

## Please describe any public data used in detail (e.g., reference panels, population databases, literature).

`[Insert the frozen reference ledger: resource name, release/version/date, checksum or immutable revision, license, retrieval URL, purpose, and model slots. Planned categories include GRCh38/reference transcripts, population frequency, clinical variation, gene-disease validity, ontology/phenotype, constraint/consequence, and public benchmark truth sets. Do not name a resource until its exact release and license are locked.]`

## Please describe any proprietary data used in detail.

None.

## Is your approach able to output proposed pairs of compound heterozygous candidate variants, or only single candidate variants?

The intended final method outputs both singles and explicit same-gene pairs. The current public component broadly enumerates two distinct heterozygous alleles within a gene/locus partition, excludes confirmed-cis pairs, and labels directly supported opposite haplotypes `trans-confirmed`; weaker evidence remains `unresolved`. It does **not yet** implement transcript compatibility, disease-mechanism eligibility, or sample-sex/ploidy-aware pair eligibility. Those gates and their tests are mandatory before a pair-level submission claim. S6 disables pair construction to measure its contribution once the final implementation is frozen.

## How did you handle secondary or incidental findings, if any? (See the finding_type column in your submission.)

No unrelated secondary coordinate is included in the public CSV while the organizer FAQ and published evaluator disagree about its scoring effect, and because this is a public hackathon artifact concerning a child. The analysis uses a conservative, predeclared ACMG-secondary-findings boundary and records only aggregate scope/limitations publicly. Any clinically relevant return would require appropriate consent, confirmation, and genetics-team governance outside this research submission.

## Please provide an estimate of run time and cost for your approach (if possible).

`[Insert measured wall time, CPU time, peak RAM, peak disk, reference/download size, human-review time, energy estimate, and actual incremental cost. Report VCF-only and FASTQ-validation paths separately. Host: CPU-only; no GPU result is implied.]`

## Provide a method abstract (up to 500 words). Please include strengths and limitations of your method as well as methodological detail.

We are developing a privacy-first, inheritance-aware workflow for one rare-disease genome. The implemented public scaffold provides strict submission validation, scorer-contract equivalence, synthetic inheritance enumeration, evidence/provenance schemas, and a leakage-resistant freeze mechanism; it is not yet biological ranking validation. The target design separates phenotype-blind discovery from phenotype-aware reranking, models compound heterozygosity at the pair level, retains unresolved phase honestly, and records structural and noncoding blind spots rather than equating a negative small-variant screen with genome-wide completeness. Final text may claim offline, digest-pinned, resumable end-to-end execution only after the exact run is reproduced and frozen. Participant reports, leaderboard results, family communications, identity searches, and hosted APIs are excluded from model inputs. `[Insert the implemented method, independently reproduced causal result, held-out validation, runtime, cost, and frozen identifiers; remove all planned claims that remain untested.]` Intended strengths are blinded discovery, explicit inheritance/phase states, causal ablations, negative-evidence visibility, offline portability, and auditable provenance. Limitations include one challenge subject, possible absence of parental/RNA/long-read data, short-read callability and phase limits, imperfect noncoding/structural interpretation, ancestry and knowledge-base bias, and no clinical confirmation. Any output is a research hypothesis for orthogonal validation and genetics-team interpretation, not a diagnosis or treatment recommendation.
