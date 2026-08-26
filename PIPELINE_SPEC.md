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
9. **Export quarantine:** permit only the final at-most-ten-row CSV, sanitized report, public tool/reference manifest, and public code. No automatic Git add, commit, upload, or publication step exists.

## Optional read-level path

FASTQs are downloaded only when the VCF analysis leaves a concrete validation gap and the full storage gate passes. Validate hashes, gzip integrity, R1/R2 counts/identifiers, read groups, and FastQC before alignment. Use BWA-MEM2 against the exact selected reference, then fixmate, coordinate sort, duplicate marking, `samtools quickcheck`, coverage/contamination QC, CPU DeepVariant, and an algorithmically different pileup/read-count check.

A candidate is “read-supported” only if the normalized supplied call, independent caller, and direct read evidence agree. Report depth, allele counts/balance, strand support, mapping/base quality, clipping, and read-position bias without read names or sequences. Discordance is a causal-claim NO-GO.

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
- Track 2: verified genotype/mechanism, current regulatory eligibility, clinically reachable unbound exposure, target engagement, fewer missegregations per completed mitosis, viability/cell-cycle counterscreens, and no selective survival/expansion of aneuploid or transformed cells.
- Submission/publishing: current official source re-audited, exact artifacts preserved, public repository sanitized, and explicit user authorization at action time.
