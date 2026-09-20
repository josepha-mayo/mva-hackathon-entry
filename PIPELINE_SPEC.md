# CPU-only, privacy-first analysis specification

Status: design and public/synthetic validation are GO. Controlled-data execution is NO-GO until registration, storage, and hosted-processing policy gates pass.

## Public execution envelope

- The workflow must remain CPU-capable and must record its declared resource envelope with each private run.
- No controlled execution begins until account access, secure local storage, spill-path containment, and action-time authorization pass privately.
- Host, volume, path, encryption, access-control, and capacity receipts are deliberately excluded from this public specification.

## Private layout after approval

```text
${MVA_PRIVATE_ROOT}/
  incoming_ro\
  refs_ro\
  hf_home\
  runs\<run_uuid>\
    work\
    results\
    logs\
    tmp\
  export_quarantine\
  deletion_manifest\
```

Private provenance records controlled filenames, hashes, phenotype, commands, and evidence. Public provenance contains only code revision, digest-pinned tool versions, public-reference versions, sanitized settings, and permitted aggregate methods. Controlled-file hashes are not published automatically because they can act as linkage identifiers.

## Stage contract

Every stage writes an atomic private `stage.json` with input/config/tool digests, exact command, UTC start/end, exit code, semantic validations, and output digests. A success marker is created only after validation. Resume is allowed only when every upstream digest still matches.

No stage may send controlled content to a network service. Analysis containers run with the network disabled and receive only explicit bind mounts. The public repository is never mounted into a controlled-data container.

## Minimum-first path

1. **Ingest:** pin dataset revision; hash privately; validate BGZF/TBI; require exactly one sample without logging its original name.
2. **Reference QC:** inspect VCF reference/contig declarations before choosing a FASTA. Require exact contig-length/reference compatibility; never silently substitute a different GRCh38 bundle.
3. **VCF QC:** require valid random query, `GT`, zero malformed records, zero REF mismatches, and no duplicate normalized allele keys. Treat Ti/Tv, het/hom, PASS fraction, and counts as review signals rather than universal thresholds.
4. **Normalization:** partition literal small variants from symbolic SV/BND records; normalize/decompose only the literal branch with `bcftools norm --check-ref e --keep-sum AD`; demand idempotence and genotype/AD conservation.
5. **Offline annotation:** retain all transcripts, then reconcile claims on the genomic allele plus MANE transcript. Cross-check shortlisted consequences with an independent engine; preserve disagreements.
6. **Phenotype-blind rank:** freeze and hash before loading HPO data. Generate dominant, homozygous recessive, compound-heterozygous, X-linked/PAR-aware, and mitochondrial models with explicit reason codes and no hard-coded gene.
7. **Phenotype-aware rerank:** rerank the same candidate universe offline. Withhold the diagnosis label in the primary run; perform leave-one-HPO-out sensitivity and positive/negative-feature review.
8. **Blind-spot ledger:** explicitly mark SV/BND, CNV, mobile elements, repeats, mitochondrial/heteroplasmy, low-VAF mosaicism, chromosome-level aneuploidy, difficult regions, noncoding/regulatory, UPD/methylation, and RNA effects as assessed, unsupported, not assessable, or candidate found.
9. **Export quarantine:** permit only the final at-most-ten-row CSV, sanitized report, public tool/reference manifest, and public code. A future Track 2 candidate-ledger release is a two-file atomic evidence surface: canonical public-only ledger plus its exact deterministic ranking, with matching v4 status, fixed paths, digest-rechecked scan bytes, and exact ledger/ranking digest lines in any released report. No automatic Git add, commit, upload, or publication step exists.

## Optional read-level path

FASTQs are downloaded only when the VCF analysis leaves a concrete validation gap and the full storage gate passes. Validate hashes, gzip integrity, R1/R2 counts/identifiers, read groups, and FastQC before alignment. Use BWA-MEM2 against the exact selected reference, then fixmate, coordinate sort, duplicate marking, `samtools quickcheck`, coverage/contamination QC, CPU DeepVariant, and an algorithmically different pileup/read-count check.

A candidate is “read-supported” only if the normalized supplied call, independent caller, and direct read evidence agree. Report depth, allele counts/balance, strand support, mapping/base quality, clipping, and read-position bias without read names or sequences. Discordance is a causal-claim NO-GO.

Centered k-mer confirmation streams private FASTQ records and requires the full paired eight-file lane set. A truncated five-file download cannot confirm. Confirmation is a presence check, not a variant call, not phase, and not pathogenicity.

A measured-exposure table can pass the exposure gate only when unbound medium and intracellular parent are both reported in the conservative window under an explicit finite positive exposure duration and contact pattern. A pulse also requires explicit washout. Nominal bath concentration alone cannot pass. A single pulse measurement cannot stand in for a post-washout concentration-time profile.

Exposure passing and assay provenance are separate decisions. Once realized lineage counts exist, count identity requires every measured-exposure row to carry a canonical semantic profile id and unique measurement-execution id, then requires each treatment execution to resolve exactly once to an eligible measured execution through that recomputed profile digest, founder-derived support-record anchor, explicit support relation, assay run, culture batch, and actual timing. All declared supports must be consumed, one unstratified treatment analysis cannot mix semantic profiles, and the paired vehicle must resolve to a distinct control record with a matched endpoint. Repeated measurement executions of the same profile across batches remain valid. This check cannot be credited at the earlier exposure gate because it needs downstream result rows. It detects inconsistent declared provenance and cross-run file collage, not physical chain of custody or biological efficacy.

When functional executions are planned, the v3 allocation contract distinguishes treatment application at the functional-execution well, randomization and analysis at the biological pair, and biological replication at the clone/edit-event level. Every reserved execution receives one unique well, dosing order, and acquisition order. Each event x clone x run pair contains one treatment and one vehicle execution in the same declared plate, batch, run, block, **exact row**, and coarse position strata. Every plate x batch x run x event context requires at least six pairs and identical per-arm plate-column distributions. Before any seed commitment, every retained context vector must preserve at least 75% of its centered arm-indicator information after the frozen context-specific dosing/acquisition linear, squared, and cross-product nuisance adjustment; the exact joint support must contain 64 to 1,000,000 vectors. A separate pre-reveal input record holds the v4 digest over the canonical manifest, exact support ordering, support count and digest, assignment algorithm, generator, and selection rule. A separate seed record holds the experiment-bound v3 commitment. The required order is lock, input record, seed record, reveal, selected-vector record, final-plan record, then exposure, and all four record ids differ. An accepted raw 256-bit draw indexes the canonical support directly; the incomplete modulo bucket is rejected without synthesized redraw. The revealed seed, support, selected index, and selected vector must replay exactly. Allocation and inference floating reductions use the digest-bound `explicit_left_to_right_binary64_v1` algorithm. Realized allocation fields are preserved by the lineage exporter and checked against the plan when result rows exist. Count identity then requires both raw generation endpoints to fall and both equal-pair-weighted one-sided randomization p-values to be at most 0.05. Exactness is conditional on rejection acceptance and limited to the global Fisher sharp null of no effect on any execution under the declared uniform assignment model; it does not cover a weak zero-average-effect null. The genuine uniform pre-outcome draw, consistency, no interference/carryover/cross-well contamination, fixed-manifest/no-exclusion, and arm-blinded ascertainment assumptions are not software-attested. Lineage/exposure classification disagreement fails closed. Current `not_attested` entropy allows a conditional synthetic pass only; non-synthetic inference requires authenticated randomization and otherwise remains HOLD. The private fixed-seed synthetic relabel helper rejects non-synthetic data, performs no seed search, and must never reseal observed or real results. These are declared-design and conditional-inference checks, not proof of entropy honesty, physical placement, dosing, chain of custody, rescue, or efficacy. See `reports/TRACK2_RANDOMIZATION_CONTRACT.md`.

A content-addressed method receipt is an internal software-integrity checkpoint. Matching hashes show that the current validator saw the same bytes; they do not supply external authentication, tamper-proof storage, proof that a record existed before exposure, or proof of physical execution. A root checkpoint with no parent cannot authenticate a historical method delta. Hardened v2 receipts set external child benefit and competition prize outcomes to `not_established`; legacy `child_help` and `prize_help` booleans are rejected.

Short-read phasing must not be overstated. A within-gene pair is `trans_confirmed`, `cis_confirmed`, or `unresolved`; unresolved pairs remain eligible with an explicit phase penalty.

## Initial tool lock targets

- bcftools/samtools/htslib 1.24
- BWA-MEM2 2.3
- DeepVariant CPU 1.10.0
- Ensembl VEP 115, offline cache
- Exomiser 15.1.0 with `2602_hg38` and `2602_phenotype`
- mosdepth 0.3.14
- FastQC, MultiQC, VerifyBamID2, bam-readcount, and WhatsHap at tested OCI digests

Tags are insufficient: every executed image must be locked by OCI digest and its tool-reported version recorded. Large images/references are not pulled until separately authorized.

## Promotion gates

- Track 1: exact normalized pair, independent evidence, honest phase state, complete counter-search/blind-spot ledger, frozen candidate files before the first upload, and local scorer/privacy checks.
- Track 2: verified genotype/mechanism, current regulatory eligibility, clinically reachable unbound exposure, target engagement, fewer new errors per completed mitosis and per enrolled founder under a pediatric completion band, viability/cell-cycle counterscreens, no selective survival/expansion of aneuploid or transformed cells, and a fail-closed lineage contract that can reject clone, field, dropout, leakage, and allocation artifacts. The nested observed-label clone-safety v2 gate requires at least eight followed daughters per arm and label stratum and stops a higher treatment-to-vehicle event-positive daughter reproduction rate above `1.25`, a disproportionate event-positive-versus-event-negative reproduction ratio above `1.25`, or an event-negative daughter death ratio above `2.0`, including the corresponding unbounded zero-control cases. Those finite thresholds are software heuristics, not powered biological or clinical boundaries, and observed-label misclassification remains possible. Nested identity and function gates refuse RNA as genomic confirmation, unmatched-line DNA/RNA/phase/function as assay-matched evidence, computational or protein-surrogate transcript as allele-specific RNA, computational or RNA-seq phase as spanning-molecule trans, analog or computational missense as an exact wet defect, unlabeled or analog recreation as exact restoration, analog, unmatched-line, ectopic, cell-free, imposed-stress, or computational correction as genetic reversal of an exact endogenous assay-matched missense, and geometry ranking or a computational predictor as a functional assay. Reciprocal recreation is required. Geometry ranking runs in the stop-early community pipeline after family copy and before confirmation; `used_as_function`, analog claimed-as-exact, unlabeled exact-role, FoldX/AlphaMissense, out-of-range features, and duplicate or extra ranking roles cannot open confirmation. A `public_software` ledger source cannot mint positive exact-allele, checkpoint, direct-target, or human-PD evidence, cannot occupy lead or conditional-hold advancement, and cannot occupy a pharmacologic ranking role. A `public_database` or `public_ontology` source cannot occupy those same pharmacologic roles or lead-advancement states. A `derived_evidence` row must name a non-derived parent source and inherits that parent's occupancy and mint bans; literature-derived or manual-review parents remain eligible. An `official_label` source cannot mint those same positive causal axes or occupy those same advancement states; a labeled indication or labeled PK estimate is not exact-allele function. Official-label comparator and mechanistic-control rows remain eligible. Decision-effect `promote` requires `active_lead` or `conditional_hold`; a parked comparator-only row cannot claim promotion. Lead or conditional-hold advancement cannot carry `demote` or `exclude`. Conditional hold and active lead require a pharmacologic ranking role; a mechanistic-control or no-go row cannot occupy the probe queue. Active lead requires role `lead`; a challenger or comparator cannot hide as the active medicine. A ledger may have at most one role `lead`. A `synthetic_fixture` row cannot be labeled public or controlled. A public catalog, label, database, ontology, or literature row cannot be labeled synthetic or controlled. Oncology-stop, unassessed-oncology, expired-eligibility, or nontranslational-high rows cannot occupy conditional hold or active lead. A `mixed_or_unsafe` functional hit cannot occupy those same advancement states. Role `no_go` and decision-effect `exclude` require advancement `rejected`. Declared search protocol `track2-candidate-search-v3` (`searched_on` remains 2026-09-01) excludes analog, nearby, or species-model records as exact function; computational predictor or ranking as an assay; unmatched or ectopic specimen as an endogenous assay; population frequency, conservation, or ClinVar as exact function; a public software catalog as causal evidence; software proof wording as exact function; cell-free, ectopic, or unmatched proof wording as exact function; imposed-stress proof wording as exact function; ranking or predictor proof wording as exact function; unlabeled, transgene, or overexpression proof wording as exact function; mixed-or-unsafe functional hits as displacement-eligible; computational or cDNA proof wording as exact function; valid no-hits as displacement-eligible; an official medicine label as causal evidence; a public database or ontology record as a pharmacologic candidate; a derived_evidence row that does not inherit its parent source occupancy; a mechanistic-control or no-go row as a conditional probe; a challenger or comparator as the active lead; two labeled leads; a source-class privacy mismatch; an oncology-stop, unassessed-oncology, unassessed-exposure, expired, nontranslational, exclude, or no-go row as a remaining conditional probe; a mixed-or-unsafe functional hit as a remaining conditional probe; a public literature record as exact function; and absent or unassessed pediatric information as displacement-eligible or as an active lead; and immortalized or reprogrammed cultures as displacement-eligible; and renewable isogenic A0 material as displacement-eligible. That axis bump is not a completed literature refresh. Candidate ledger v7 and sample stewardship v17 fail closed on both discovery lanes, cumulative partition debits, context-class or transformation mismatch, and independent replication that lacks unique site-2 blinding and analytic-transfer identities.
- Submission/publishing: current official source re-audited, exact artifacts preserved, public repository sanitized, and explicit user authorization at action time.

## Future public-freeze checklist

1. Record the verified AI provider, model, plan/tier, and relevant data-handling setting in the new bound methods report.
2. Commit the intended living surface and name one exact clean checkout that reproduces it; do not publish an uncommitted working-tree bundle as the source revision.
3. Generate a fresh content-addressed method receipt and reproducibility manifest from that committed checkout. Bind both endpoints if a historical delta is claimed.
4. If the judged report retains an exact candidate-ranking claim, stage the canonical public-only ledger/ranking pair, place their exact canonical digest lines in the report, and bind all three under the future v4 release manifest; otherwise remove that claim.
5. Run the full test suite, privacy gate, and frozen-package reproducibility verifier against the exact candidate bytes and preserve the results.
6. Re-read the authenticated portal attempt counter and exact report, repository, and video state. Upload only after the operator gives the attempt-specific authorization phrase; preparation is not authorization.
