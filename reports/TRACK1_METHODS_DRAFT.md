# Track 1 methods report — pre-data draft

Status: structure and methods are prepared from public/synthetic evidence. Bracketed fields require controlled local results. No causal claim is made yet.

## Abstract (500-word limit)

We are developing a privacy-first, inheritance-aware workflow for one rare-disease genome. The implemented public scaffold currently covers submission/scorer semantics, conservative synthetic inheritance enumeration, evidence and provenance validation, and leakage-resistant artifact freezing; it is not yet an end-to-end biological ranker. The target design separates phenotype-blind discovery from phenotype-aware reranking, models compound heterozygosity at the pair level, retains unresolved phase honestly, and records structural/noncoding blind spots rather than equating a negative small-variant screen with genome-wide completeness. Claims that every stage is offline, digest-pinned, resumable, and byte-reproducible must be supported by a completed frozen run before submission. [Replace this abstract with the exact implemented method, independently reproduced result, held-out validation metrics, runtime, and cost after controlled analysis.]

## 1. Scope, ethics, and reproducibility boundary

- One real child; outputs are research hypotheses, not diagnosis, medical advice, or treatment recommendations.
- No recontact or attempted identification.
- Controlled files, subject-level derivatives, read images, phenotype details, and private hashes remain outside Git and hosted services.
- Public code uses only synthetic fixtures. Controlled processing is local and network-disabled.
- Participant reports, leaderboard outputs, family communications, identity searches, and public-consensus coordinates are excluded from every model input and candidate-selection decision. They remain segregated landscape context outside the submission branch.
- All intended submission files and rationales are frozen before the first upload; leaderboard match feedback is never used for revision.

## 2. Inputs and provenance

Record privately:

- dataset revision and controlled source hashes;
- VCF header/reference/contig declarations and one-sample check;
- exact reference, annotation, ontology, population-frequency, disease, and transcript releases;
- source-code commit, OCI image digests, tool-reported versions, configuration digest, commands, stage start/end, semantic checks, and output digests.

Public provenance contains only the code revision/digest, tool image versions/digests, public-reference versions, sanitized settings, and aggregate method names. It cannot contain controlled paths, filenames, hashes, commands, phenotype, or sample identifiers.

## 3. Target automated pipeline and implementation boundary

Sections 3.1–3.7 specify the required final pipeline. At this draft stage, only the public/synthetic components explicitly demonstrated in Section 9 are implemented and tested. Planned normalization, annotation, biological ranking, transcript/mechanism/ploidy eligibility, phenotype reranking, and calibration must not be described as completed until an executable end-to-end run and held-out evidence are frozen.

### 3.1 Ingest and reference QC

Verify BGZF/TBI integrity and random access; require exactly one expected sample without logging its source name. Select GRCh38 FASTA only after matching VCF reference/contig metadata. Zero REF mismatches is a fatal gate; allele swapping is not used as a repair.

### 3.2 Normalization

Partition literal small variants from symbolic SV/BND records. Decompose and left-normalize only literal alleles against the exact FASTA while conserving genotype/AD information and retaining an original-to-normalized map. Require normalization idempotence, zero duplicate normalized allele keys, and preserved sample/genotype identity.

### 3.3 Offline annotation

Retain every transcript initially; add MANE/canonical/APPRIS/HGVS, ClinVar, population frequency, LoF, missense, splice, constraint, and region-quality evidence. Cross-check shortlisted gene and broad Sequence Ontology consequence with an independent engine. Preserve disagreements rather than silently selecting the favorable annotation.

### 3.4 Phenotype-blind inheritance universe

The current public component deterministically enumerates dominant, homozygous-recessive, same-gene pair, locus-partition, and mitochondrial candidate states from sanitized records. Confirmed-cis pairs are excluded. Pairs are labelled `trans_confirmed` or `unresolved`; statistical expectation is never promoted to confirmed phase. This is deliberately a broad candidate-universe component: it does not yet use transcript compatibility, disease mechanism, or sample-sex/ploidy context, so it cannot by itself support a biologically eligible compound-pair claim.

The final pipeline must add and test those eligibility gates, preserve every inclusion/exclusion reason, and only then describe sex-chromosome inheritance models or transcript/mechanism-compatible pairs as implemented.

Freeze and hash the blind universe before phenotype is loaded. Report a diagnosis-label-blinded run, synthetic inheritance recovery, and sensitivity to filtering thresholds.

### 3.5 Phenotype-aware rerank

Curate positive and explicit negative HPO terms privately. Avoid ontology ancestor/descendant double counting and age-adjust absent tumor phenotypes. Rerank the same blind candidate universe; do not silently remove blind candidates. Run leave-one-HPO-out sensitivity and flag candidates driven by a single unusually specific term. Withhold the diagnosis label and near-synonyms in the primary run.

### 3.6 Completeness ledger

For each category, record `assessed`, `unsupported`, `not_assessable`, or `candidate_found`: supplied symbolic SV/BND, independent SV, CNV, mobile elements, repeat expansions, mitochondrial/heteroplasmic calls, low-VAF mosaicism, chromosome-level aneuploidy, difficult regions, noncoding/regulatory alleles, and UPD/methylation/RNA effects unavailable from WGS alone.

### 3.7 Optional read-level validation

Raw FASTQs are fetched only for a concrete validation gap. After hash, gzip, pairing, contamination, mapping, coverage, and read-group QC, align to the exact reference and call independently with CPU DeepVariant plus an algorithmically different pileup/read-count check. A shortlisted allele becomes read-supported only when the supplied normalized call, independent caller, and direct evidence agree. Discordance is a causal-claim NO-GO.

Report DP, AD, allele balance, forward/reverse support, mapping/base quality, clipping, and read-position bias without read names or sequences. Short reads cannot establish distant trans phase without a spanning chain; use `phase unresolved` when warranted.

## 4. Pair-level ranking and confidence

The target ranker will rank a biologically coherent allele pair as one candidate row. Its pair score must combine call quality, rarity, consequence/mechanism, gene-disease validity, phenotype likelihood, phase evidence, and orthogonal support. A strong single allele must trigger a deliberate search for a second coding, splice, regulatory, CNV/SV, or mobile-element allele in the same gene. No such biological ranking performance is claimed from the current enumeration-only benchmark.

Do not label an arbitrary rank score as EPCR probability. Either calibrate it on held-out public rare-disease cases or describe EPCR as an ordinal submission confidence. Use unique strictly decreasing EPCR values. Keep any secondary findings below every primary candidate because the published scorer includes them in rank/F-max despite conflicting FAQ prose.

## 5. Manual review

Manual review is blinded to leaderboard feedback and occurs only after automated output is frozen. Reviewers may annotate evidence quality, representation, transcript/mechanism coherence, phase, callability, alternatives, and limitations; they may not reorder candidates, edit EPCRs, or introduce a candidate. Any discovered implementation defect invalidates the affected freeze and requires a full pre-submission rerun, never a leaderboard-informed patch.

## 6. Public and proprietary resources

List every public/reference source with version, license, and access date. Disclose any proprietary predictor separately and run a public-only ablation. Never transmit subject-derived inputs to those services. [Insert exact resource table after reference lock.]

## 7. Incidental findings

Do not turn broad variant mining into unsolicited clinical reporting. Pending organizer clarification of the conflict between FAQ prose and evaluator behavior, publish no unrelated secondary coordinates in the Track 1 CSV. The methods report records the conservative ACMG-secondary-findings boundary, confirmation requirements, and what was not assessed without exposing child-specific findings.

## 8. Predeclared six-submission design

All six configurations, calibration identities, candidate outputs, reports, reference manifests, benchmark results, expected directions, and upload order are frozen before S1. They are never revised using match feedback:

| Slot | Predeclared method | Comparison / scientific question |
|---|---|---|
| S1 | `full-public-auto` | Champion: complete automated public-reference, HPO-aware, inheritance/phase-aware, independently validated workflow. |
| S2 | `minus-phenotype` | Set all HPO feature weights to zero: does genotype, rarity, consequence, and inheritance converge independently? |
| S3 | `novel-gene-mask` | Remove direct variant-disease and gene-disease priors: does the method survive an uncatalogued causal relationship? |
| S4 | `exomiser-baseline` | Pinned, unmodified Exomiser rank: baseline anchor rather than a single-delta S1 ablation. |
| S5 | `vcf-only` | Remove independent read, callability, CNV/SV, and orthogonal-call evidence: what does validation add? |
| S6 | `no-comphet-pairing` | Disable pair construction and rank alleles singly: is explicit compound-heterozygous reasoning necessary? |

The intended estimands are S1–S2 for phenotype contribution, S1–S3 for knowledge-prior contribution, S5–S4 for custom-backend lift on the shared VCF-only evidence envelope, S1–S5 for independent validation evidence, and S1–S6 for explicit pair construction. These comparisons require executable configuration equivalence checks; the labels alone are not evidence of a single causal delta.

Before submission, generate the write-once v2 freeze over real slot outputs, reports, calibration artifacts, public references, expected directions, and upload order. The library and synthetic tests exist, but no real freeze manifest or benchmark-fitted calibration is claimed yet. A public precommitment may use `SHA256(random 256-bit nonce || artifact bytes)` so a tiny candidate CSV cannot be brute-forced from its hash. If two scientifically independent ablations converge on identical CSV bytes, retain the convergence as offline robustness evidence and do not consume a redundant upload. Submitting fewer than six is allowed.

## 9. Validation and ablations

- **Completed:** differential fuzzing against the pinned official scorer: 10,000 synthetic cases, every score field identical.
- **Completed:** unit tests for exact schema, pair order, partial credit, EPCR ties/order, secondary ordering, UTF-8 BOM, CSV injection, duplicate headers, surplus fields, coordinate bounds, inheritance/phase/PAR component rules, atomic provenance, resume digests, public/private manifest leakage, and write-once submission freeze.
- **Completed component test:** deterministic 600-case synthetic inheritance enumeration; 500/500 positive-universe recovery, 200/200 compound-truth recovery, zero confirmed-cis leakage, and 60/260 emitted pairs intentionally labelled false because unresolved same-gene distractors are enumerable. This is not biological ranking validation.
- **Planned and required:** PhEval plus Phenopacket Store with gene-disjoint splits, HPO dropout/noise/negation, leave-one-HPO-out sensitivity, Top-1/5/10, MRR, median rank, and case-bootstrap 95% confidence intervals.
- **Planned and required:** a time-sliced novel-disease benchmark separating known-gene/known-disease, known-gene/new-disease, and novel-gene/new-disease cases.
- **Planned and required:** a pinned public analytical truth benchmark with stratified SNV/indel precision, recall, F1, genotype concordance, Mendelian error, and phase error where truth permits.
- **Planned and required:** compound-pair spike-ins with cis/trans/unresolved phase, dropout, distractors, difficult regions, and temporal masking; report pair Top-1/5/10, both-allele recall, false-pair rate, Brier score, ECE, and runtime.
- **Planned and required:** executable S1–S6 comparisons plus diagnosis-term withholding and leave-one-HPO-out sensitivity.

The 10,000-case differential suite establishes scorer-contract equivalence only; it is not biological validation.

## 10. Result and evidence table

Maintain a normalized long-form evidence ledger with one row per material claim/source and at least:

`evidence_id, candidate_id, model_slot, claim_type, claim, allele_or_pair_id, source_class, source_identifier, source_version_or_date, source_url, tool_and_version, tool_or_container_digest, run_id, config_digest, result, unit, direction, independent_replication, uncertainty_or_ci, counterevidence, decision_effect, phase_state, privacy_class, manual_action, artifact_path, artifact_sha256, reviewer, reviewed_at_utc`.

Allowed `direction` states are `supports`, `contradicts`, `neutral`, and `not-assessable`; absence of assessment never becomes negative evidence. The reviewer pivot includes:

`rank, candidate/pair, inheritance, phase, call/read support, max population AF, consequence consensus, phenotype robustness, counterevidence, blind spots, calibrated EPCR, decision, and model slots`.

For every final candidate row include:

`rank, exact GRCh38 allele(s), gene, transcript/HGVS, zygosity, phase state, DP/GQ/AD/allele balance, caller concordance, population frequency, consequence/NMD/splice evidence, ClinVar/ClinGen evidence, phenotype contribution, structural/noncoding evidence, ACMG/AMP evidence codes, contradictory evidence, blind-spot status, EPCR interpretation, and required clinical confirmation`.

The top causal row is promoted only after exact VCF representation, independent evidence, transcript/mechanism, genome-wide counter-search, and the completeness ledger are documented.

## 11. Runtime, compute, and cost

Report wall time, CPU/RAM, storage, human-review time, tool/reference download size, and actual incremental cost for VCF-only and FASTQ paths separately. This host is CPU-only; no GPU result is implied. [Insert measured values.]

## 12. Strengths, limitations, and clinical next steps

Strengths: pair-first inheritance modeling, blinded discovery, explicit phase uncertainty, broad blind-spot accounting, scorer compatibility, reproducible provenance, and leakage-resistant submission behavior.

Limitations: one subject, potentially absent parental/RNA/long-read data, phenotype specificity, imperfect difficult-region callability, database ancestry/ascertainment bias, annotation disagreement, and no clinical validation. Proposed next steps must be framed for clinicians/IRB: parental or long-read phasing, orthogonal molecular confirmation, RNA/minigene or protein/function assays, and genetics-team interpretation.
