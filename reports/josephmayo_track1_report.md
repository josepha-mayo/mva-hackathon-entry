# Track 1 — an inheritance-, transcript-, and mechanism-aware causal-variant research hypothesis

**Participant:** Joseph Mayo
**Model:** Model 1 (S1), public-reference pair graph
**Status:** final public pre-submission report; no live score is claimed

## Abstract

We prioritized causal variants for the challenge proband with a deterministic, CPU-only workflow that keeps discovery, phenotype reranking, mechanism assessment, and manual interpretation separate. We normalized and consequence-annotated the supplied single-sample GRCh38 call set, then built same-gene biallelic candidates only when both heterozygous alleles affected at least one shared protein-coding transcript. Candidate records preserve phase as `trans_confirmed`, `cis_confirmed`, or `unresolved`; unresolved phase is never promoted to trans. Gene2Phenotype allelic requirements and mechanisms, exact allele-and-gene ClinVar matches, current gnomAD rarity, call quality, and diagnosis-name-blinded HPO similarity were retained as separate evidence axes rather than collapsed into a clinical probability.

The rank-1 hypothesis is a *BUB1B* pair on the MANE Select transcript NM_001211.6 / ENST00000287598.11: c.2210T>G p.(Leu737Ter) and c.3006T>G p.(Asn1002Lys). Both are high-quality heterozygous PASS calls. The first is a stop-gained, LoF-compatible allele with a two-star, two-submitter Pathogenic/Likely pathogenic **variant-level** ClinVar aggregate; the MVA-specific variant-condition record is one-star and its assertion is based on expected loss of function rather than a reported affected individual. The second is an ultra-rare missense VUS in the BUBR1 C-terminal domain; public sequence, structural, conservation, and disease-architecture evidence motivates testing a hypomorphic/stability hypothesis but does not prove mutant function. The pair is rank 1 in evidence-synthesis and pathogenic-anchor orderings across three independently extracted HPO sets. Phase remains unresolved because no parental genotypes or informative phase block are available.

Strengths are pair-level reasoning, shared-transcript and mechanism gates, diagnosis-label-independent phenotype sensitivity, exact provenance, and explicit negative evidence. Limitations are unresolved phase, no direct assay for p.Asn1002Lys, incomplete assessment of structural/noncoding causes, one challenge subject, and no calibrated EPCR model. The proposed EPCR value is therefore an uncalibrated ordering value in the required EPCR field, not a posterior probability. This is a research hypothesis requiring parental segregation, orthogonal molecular confirmation, and genetics-team interpretation; it is not a clinical diagnosis or treatment recommendation.

### Submission metadata

| Item | Declaration |
|---|---|
| Participant / display | Joseph Mayo / individual `josephmayo`; no team name |
| Model | Model 1 (S1) |
| CSV production | Deterministic pair ranking followed by manual evidence review and exact one-row packaging |
| Data classes | Organizer-provided controlled VCF and phenotype document; public reference resources; no proprietary or commercial database |
| Output capability | Single variants and compound-pair rows; this release proposes one primary pair and no secondary/incidental row |

### Thirty-second judge read

| Differentiator | Verified receipt | Boundary preserved |
|---|---|---|
| Fail-closed compound-pair graph | 9,862 protein-altering variants reduced to 1,182 pair-disease rows; shared transcript required; confirmed cis excluded | Unresolved phase is never promoted to trans |
| Diagnosis-label-blinded robustness | Independent HPO extractions had Jaccard 0.867; evidence and anchor ranks remained 1 across lexical, consensus, and union sets | Phenotype supports ranking but cannot create or delete a genotype pair |
| Allele-specific triangulation | Exact two-star, two-submitter variant-level P/LP stop aggregate (one-star for the MVA-specific condition record) plus ultra-rare missense; AlphaMissense 0.9229 is counterbalanced by an equivalent-protein ClinVar VUS, bounded PubMed and Europe PMC searches that found no exact-variant paper, and no human experimental structure at N1002 | The missense remains a VUS and its mechanism remains unproven |
| Reproducibility | 152 public package tests, seven private adapter regressions, nine public-evidence invariants, and 10,000 exact scorer comparisons | Component correctness is not clinical validation |

### Automation and manual-review contract

Automated steps were normalization, consequence mapping, shared-transcript pairing, inheritance/mechanism gates, exact ClinVar joins, phenotype orderings, tie handling, and strict CSV validation. Manual review audited the computed rank-1 row, public sequence/structure/literature evidence and counterevidence, limitations, and final one-row packaging. Manual review did **not** create a calibrated probability, promote unresolved phase, reinterpret the VUS as P/LP, or use participant/leaderboard outputs as biological evidence. The CSV is therefore a deterministic computational ranking followed by bounded downstream curation, not untouched automated output.

## 1. Proposed hypothesis

| Field | Allele 1 | Allele 2 |
|---|---|---|
| GRCh38 | `chr15:40209701 T>G` | `chr15:40220612 T>G` |
| MANE Select | `NM_001211.6:c.2210T>G` | `NM_001211.6:c.3006T>G` |
| Protein | `p.(Leu737Ter)` | `p.(Asn1002Lys)` |
| Consequence | stop gained; LoF-compatible | missense; hypomorph hypothesis untested |
| Genotype | `0/1`, unphased | `0/1`, unphased |
| FILTER / GQ | PASS / 99 | PASS / 99 |
| AD / DP / alternate balance | 21,25 / 46 / 0.543 | 15,13 / 28 / 0.464 |
| Phase fields | no PGT, PID, or PS | no PGT, PID, or PS |

The calls are 10,911 bp apart. Ordinary short fragments cannot directly bridge that distance, and opposite-looking allele balances do not establish trans phase. The correct label is **biallelic candidate pair, phase unresolved**.

The planned one-row CSV is `submissions/track1/josephmayo_track1_bub1b_pair.csv`. It uses `0.50` as a disclosed, uncalibrated ordering value in the required EPCR field. With one row, every valid EPCR in `(0,1]` has identical automated-score behavior; `0.50` avoids implying calibration or confirmed phase. No insurance or secondary row is included.

## 2. Reproducible workflow

### 2.1 Input and annotation

The controlled dataset was pinned to Hugging Face revision `f534cb0c1a607110c6dad0194299bd3dd62df542`. The supplied VCF and phenotype document were processed locally on the HDD; FASTQ acquisition supported only the incomplete, non-confirmatory k-mer QC reported below. No controlled source file, read, verbatim phenotype text, sample hash, or private path was sent to a hosted inference service or released. The only individual-level public outputs are the organizer-required, fixed-path report and submission CSV, each protected by an exact-byte release manifest.

The supplied single-sample VCF was normalized and annotated against the GRCh38 primary assembly and Ensembl release 116. Protein-altering consequences were retained per transcript; a consequence on an unshared isoform cannot upgrade a pair.

### 2.2 Diagnosis-label-blinded phenotype model

Two independent extraction routes generated 14 positive HPO terms each, sharing 13 terms (Jaccard 0.867). The frozen sensitivity sets contained 13 consensus, 15 union, and two disputed terms; no explicit negative term was encoded. Gene names, syndrome names, cytogenetic labels, competitor reports, and leaderboard outputs were excluded from phenotype-model inputs.

Using HPO release `v2026-06-23`, phenotype-only *BUB1B* ranks were 30, 21, and 45 of 5,268 genes for the lexical, consensus, and union sets. The phenotype is supportive and robust, but it is not sufficient by itself and was never used to delete genotype candidates.

### 2.3 Pair graph and fail-closed mechanism gates

The normalized coding export produced 9,862 unique protein-altering variants and 9,948 gene-allele annotations. Requiring two distinct heterozygous alleles on one contig, at least one shared protein-coding transcript, a supported biallelic-autosomal disease rule, and no confirmed-cis phase produced:

- 1,182 pair-disease rows;
- 1,101 unique gene-variant pairs;
- 226 genes;
- 35 one-LoF-plus-protein-altering hypotheses, 956 two-non-LoF hypotheses, and 191 rules requiring manual mechanism review;
- six trans-confirmed rows and 1,176 unresolved rows.

The private adapter fails closed on multiallelic `1/2` genotypes without allele-specific AD semantics, unknown confidence labels, cross-contig pairs, disjoint transcripts, off-shared-transcript LoF effects, and cross-gene ClinVar anchors. Exact ties receive a common interval and midrank; identifiers affect display order only. ClinVar allele/gene anchoring and disease-condition relevance remain separate facts.

Across lexical, consensus, and union phenotype sets, *BUB1B* was uniquely:

| Ordering | Lexical | Consensus | Union |
|---|---:|---:|---:|
| Evidence synthesis | 1 | 1 | 1 |
| Pathogenic anchor | 1 | 1 | 1 |
| Phenotype first | 7 | 1 | 9 |
| Mechanism first | 5 | 5 | 5 |

The mechanism-first penalty is intentional: four phase-supported distractor rows sort ahead of an unresolved pair. *BUB1B* remains first when definitive gene-disease validity, the unique strict gene-matched pathogenic anchor, mechanism fit, phase, and phenotype are considered as explicit lexicographic axes.

## 3. Evidence for the pair

### 3.1 Shared transcript and disease rule

Both alleles have protein-coding consequences on 11 shared Ensembl transcripts, including MANE Select / Ensembl canonical `ENST00000287598.11` (`BUB1B-201`). MANE v1.5 maps it exactly to `NM_001211.6`, `NP_001202.5`, and UniProt `O60566`; all three protein sequences are identical and 1,050 amino acids long.

The dated Gene2Phenotype row `G2P00148` identifies *BUB1B*-related mosaic variegated aneuploidy syndrome as definitive, `biallelic_autosomal`, with absent gene product / inferred loss-of-function mechanism. p.(Leu737Ter) is LoF-compatible with that rule. p.(Asn1002Lys) does not directly satisfy it: the allele is retained only as a plausible partial-loss or protein-instability candidate.

### 3.2 Exact ClinVar and population evidence

Exact allele-key intersection against the pinned GRCh38 ClinVar file found six strict, nonconflicting PASS P/LP variants genome-wide. Only the *BUB1B* pair graph row contained a strict allele-and-gene matched anchor.

| Evidence | p.(Leu737Ter) | p.(Asn1002Lys) |
|---|---:|---:|
| Exact ClinVar | VCV000533901; variant-level P/LP; two submitters/two stars/no conflicts; MVA-specific RCV000641226 is Pathogenic/one submitter/one star | no exact record |
| gnomAD v4.1.1 total AC / AN | 120 / 1,614,020 | 1 / 1,614,226 |
| gnomAD total AF | 7.435e-5 | 6.195e-7 |
| Homozygotes | 0 | 0 |
| CADD | 38.0 | 26.4 |
| SpliceAI | 0.03 | 0.02 |
| Other missense evidence | not applicable | REVEL 0.472; PolyPhen max 0.997; phyloP 3.69 |

Population rarity is compatible with recessive disease but is not evidence of trans phase or pathogenicity. Exact ClinVar absence is not benign evidence.

ClinVar contains no exact c.3006T>G assertion. A different nucleotide substitution, `NM_001211.6:c.3006T>A`, encodes the identical p.(Asn1002Lys) protein change and is a single-submitter VUS (`VCV004600147.1`, last evaluated 2025-09-19). That is uncertainty-preserving context, not pathogenic or benign evidence.

### 3.3 Public functional context for p.(Asn1002Lys)

Residue N1002 lies within the UniProt protein-kinase domain (766–1050) and is conserved in mouse, rat, frog, and the homologous Drosophila BUBR1 kinase structures. No available human experimental PDB model contains atoms at N1002. AlphaFold DB v6 gives the wild-type residue pLDDT 91.06, relative solvent accessibility 0.142, and three short side-chain-to-backbone polar contacts; Drosophila structures 6JKK and 6JKM independently preserve the homologous Asn and the same three-contact topology. This supports a conserved wild-type motif and motivates—but does not validate—a mutant stability hypothesis.

The official 2023 AlphaMissense hg38 object was accepted only after its 642,961,469-byte size and published MD5 matched. It contains one exact O60566 N1002K row: score **0.9229**, class `likely_pathogenic`. The static catalogue uses `ENST00000287598.10`; current MANE v1.5 uses `.11`, but the exact genomic allele, UniProt accession, residue, and identical current protein sequence close that version gap. AlphaMissense is in-silico prioritization only—not a functional assay, phase result, segregation result, ACMG classification, or clinical conclusion.

Hanks et al. reported biallelic truncating-plus-missense *BUB1B* genotypes in MVA families. Suijkerbuijk et al. showed that patient missense alleles in or near the kinase domain can combine with truncating alleles to reduce BUBR1 abundance and checkpoint function. Those studies support the **allelic architecture**, not pathogenicity of this exact missense substitution.

### 3.4 Evidence-to-Phase-2 bridge

The biologically differentiated hypothesis is **not** that p.(Asn1002Lys) abolishes BUBR1 kinase catalysis. Human BUBR1 showed no detectable catalytic activity in vitro; catalytic activity was reported for Drosophila BUBR1 and cannot be assumed for human BUBR1. The narrower hypothesis is that N1002 participates in a conserved C-terminal structural motif: its wild-type contact topology is reproduced computationally and retained in experimental homolog structures 6JKK/6JKM. That supports the motif—not the mutant effect. Because tested MVA-domain missense alleles can lower BUBR1 abundance, p.(Asn1002Lys) enters Phase 2 as an untested stability/abundance hypothesis with predeclared alternatives.

| Phase-2 gate | Evidence now | Decision rule |
|---|---|---|
| Pair configuration | Phase unresolved | Establish trans; cis rejects this recessive-pair hypothesis |
| Allele-resolved transcript state | Stop-allele decay and missense-allele expression are predicted, not measured | Quantify allele-specific RNA at both sites relative to genomic DNA, with and without a validated NMD perturbation. The specific NMD-mediated-null model is supported by depletion and NMD rescue of the stop-bearing transcript, together with detectable N1002K-bearing transcript; otherwise revise the dosage model before interpreting protein assays |
| Exact-allele abundance | Class-level evidence only | Compare WT/N1002K abundance and cycloheximide half-life at matched expression |
| Assay validity and comparator | No exact N1002K assay exists | Use isogenic WT, N1002K, and the MVA-associated human p.Leu1012Pro benchmark allele—modeled as mouse p.Leu1002Pro by Sieben et al.—with matched integration/expression, blinded biological replicates, and a predeclared primary endpoint. If WT and comparator controls do not separate in the expected direction, classify the run as uninterpretable rather than as evidence for or against N1002K |
| Disease-relevant function | No exact-allele assay | At matched abundance, test localization, checkpoint response, and chromosome-segregation errors |
| Falsifiable branch | Structural/predictor evidence only | Low abundance with matched-level rescue supports a stability hypomorph; normal abundance with defective function supports a non-abundance defect; WT-like abundance and function fail to support the exact-allele mechanism |

**No allele-specific Phase-2 mechanism advances unless phase and at least one exact-allele molecular or cellular defect are demonstrated.**

| Segregation × exact-allele result | Reproducible N1002K defect in predeclared assays | WT-like in predeclared assays |
|---|---|---|
| **Trans established** | The submitted pair mechanism is materially strengthened; proceed to orthogonal causal assays | Trans configuration is established, but the tested missense mechanism is unsupported; revisit alternative mechanisms or second alleles |
| **Cis established** | The submitted recessive pair is rejected; any allele effect is a separate observation | Both the submitted pair and tested exact-allele mechanism are unsupported |

A negative result in these bounded assays does not classify the missense as benign; it falsifies the tested mechanism.

### 3.5 Incomplete raw-read k-mer check

Five incomplete FASTQ prefixes totaling 17.03 GB compressed and 217,961,960 readable records were scanned only as partial QC. Unique centered allele-1 k-mers showed alternate/reference counts of 2/6 at k=31 and 2/5 at k=51; allele 2 showed 0/4 and 0/2. Because every input prefix was incomplete and the alternate allele was not observed for allele 2, this result is inconclusive, received zero ranking weight, and is not presented as variant confirmation.

Exact centered 31-mers and 51-mers for each reference and alternate allele occur once or zero times, respectively, in the GRCh38 primary assembly, making them suitable for a narrow raw-read check. This check is not a caller, does not replace complete alignment-based analysis or orthogonal confirmation, does not estimate mapping bias, and cannot establish phase.

## 4. Validation

- The public package has 152 passing unit tests covering the official CSV contract, scorer behavior, provenance, privacy, inheritance, transcript/mechanism gates, confidence vocabularies, disease-condition separation, and exact tie intervals.
- A frozen 10,000-case differential fuzz suite matches the public official evaluator for every score field.
- The corrected private pair adapter passes seven targeted regression tests and reproduces the rank-1 pair across all three phenotype sets.
- A public-only sequence/structure/literature pipeline passes nine substantive invariant tests; no private or controlled input enters it.
- The official Phen2Gene code at commit `47ab30af0751ff4d2060e9bf241c0a758cd0d7a3` with its 1.1.0 January-2021 knowledge base was run only as a historical development comparator: 64 public development cases, Top-10 16/64 = 0.250 (95% bootstrap CI 0.141–0.359), MRR 0.141 (0.071–0.228), and truth-universe recall 54/64 = 0.844. Calibration cases read: 0; held-out cases read: 0; controlled patient files read: 0. It is not the champion and does not calibrate EPCR.

Public participant submissions and leaderboard results were segregated landscape context. They were not ranking features, labels, calibration data, or validation truth.

## 5. Counterevidence and remaining blind spots

1. **Phase is unresolved.** If the alleles are in cis, this recessive explanation collapses to a carrier finding. Parental targeted genotyping is the decisive next test.
2. **The missense remains a VUS.** No exact ClinVar assertion, patient segregation, protein-abundance assay, spindle-checkpoint assay, or allele-specific functional experiment is available.
3. **Formal mechanism tension is preserved.** G2P specifies absent gene product, while p.(Asn1002Lys) is a missense allele rather than an absent-gene-product allele; any abundance or functional loss remains unproven.
4. **No cytogenetic confirmation was used.** The phenotype document did not supply a karyotype, premature-chromatid-separation result, or quantitative aneuploidy assay.
5. **Variant-class completeness is limited.** The small-variant VCF path does not exclude exon-level CNV, structural variation, mobile-element insertion, repeat expansion, regulatory variation, mitochondrial heteroplasmy, low-level mosaicism, UPD, methylation, or RNA effects. The FASTQ acquisition and narrow read check must not be misdescribed as a completed genome-wide SV/CNV analysis.
6. **One subject and biased knowledge sources.** Population databases, HPO annotations, ClinVar assertions, and disease resources have ancestry and ascertainment limitations.

## 6. Scalability: demonstrated versus unmeasured

The public inheritance, pair-composition, scoring, provenance, and reference-ledger components are patient-agnostic and deterministic. In a 600-case synthetic contract benchmark they recovered 500/500 positive truths and 200/200 compound-pair truths, leaked zero confirmed-cis pairs, and intentionally retained 60 unresolved distractors rather than converting uncertainty into false trans evidence. After annotation, the challenge coding export is 14.185 MB and the ranking path is CPU-only with public references.

This demonstrates software portability, deterministic artifact lineage, and batch-contract correctness. It does **not** measure multi-patient clinical accuracy, ancestry robustness, production throughput, or prospective diagnostic yield; annotation and reference acquisition remain the dominant costs. A valid larger evaluation requires diagnosis-blinded, patient-disjoint cases and prespecified promotion metrics.

## 7. Runtime, compute, and cost

The workflow ran locally on a CPU-only Windows host; no GPU or paid hosted inference was used. Direct incremental paid-service spend was **US$0**, excluding electricity, existing hardware, and storage. The controlled manifest contains 84.668 GB of FASTQs, a 315.154 MB VCF, and a 2.343 MB index. The completed consequence BCF is 251.254 MB; the coding export is 14.185 MB. Repeat Phen2Gene development baselines took 43.216 and 26.471 seconds. Reference acquisition and the optional raw-read path dominate elapsed time and storage; no unmeasured wall time is presented as a benchmark.

## 8. Clinical confirmation path

The shortest decisive sequence is:

1. confirm both alleles by an orthogonal clinical assay;
2. genotype both parents, or use validated long-range phasing, to establish trans versus cis;
3. review the pair under current ACMG/AMP guidance with a clinical molecular geneticist;
4. test p.(Asn1002Lys) using BUBR1 abundance/stability and spindle-assembly-checkpoint function in an appropriate assay;
5. obtain cytogenetic evidence if clinically indicated.

No treatment decision follows from this research submission.

## 9. Public resources

- Sage Bionetworks, [Rare Disease, Real Kid: MVA Hackathon 2026](https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026), accessed 2026-08-26.
- Ensembl release 116, [GRCh38 annotation](https://ftp.ensembl.org/pub/release-116/), accessed 2026-08-26.
- Human Phenotype Ontology release `v2026-06-23`, [official releases](https://github.com/obophenotype/human-phenotype-ontology/releases/tag/v2026-06-23).
- EMBL-EBI, [Gene2Phenotype](https://www.ebi.ac.uk/gene2phenotype/), snapshot `all-20260826.csv`, SHA-256 `b3543dffad3e71ba1ec9f19996ac5549cbec1fa8000afd2338a142aa731d6a2a`.
- NCBI, [ClinVar VCV000533901](https://www.ncbi.nlm.nih.gov/clinvar/variation/533901/), [VCV004600147.1](https://www.ncbi.nlm.nih.gov/clinvar/variation/4600147/), and [GRCh38 VCF](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz), rolling snapshot header `fileDate=2026-08-22`, retrieved 2026-08-26, SHA-256 `d66b75c1cc433dd63471444fbf980fbc6ee07d6060f3b62b8f1910d52650933d`.
- gnomAD v4.1.1: [15-40209701-T-G](https://gnomad.broadinstitute.org/variant/15-40209701-T-G?dataset=gnomad_r4) and [15-40220612-T-G](https://gnomad.broadinstitute.org/variant/15-40220612-T-G?dataset=gnomad_r4), accessed 2026-08-26.
- NCBI/EMBL-EBI, [MANE v1.5](https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/release_1.5/).
- UniProt, [BUB1B_HUMAN O60566](https://www.uniprot.org/uniprotkb/O60566/entry), accessed 2026-08-26.
- AlphaFold DB, [AF-O60566-F1](https://alphafold.ebi.ac.uk/entry/O60566), model v6.
- AlphaMissense: Cheng et al., *Science* 2023, [doi:10.1126/science.adg7492](https://doi.org/10.1126/science.adg7492); official hg38 prediction object, MD5 `9fd167735f16a1b87da6eb3e4c25fcb5`, SHA-256 `0516cfd71c0767ac8f9c469252d429000e94e02c008b6e3a46d4b4646fcd3475`.
- Hanks et al., *Nature Genetics* 2004, [PMID 15475955](https://pubmed.ncbi.nlm.nih.gov/15475955/), doi:10.1038/ng1449.
- Suijkerbuijk et al., *Cancer Research* 2010, [PMID 20516114](https://pubmed.ncbi.nlm.nih.gov/20516114/), doi:10.1158/0008-5472.CAN-09-4319.
- Sieben et al., *Journal of Clinical Investigation* 2020, [PMID 31738183](https://pubmed.ncbi.nlm.nih.gov/31738183/), doi:10.1172/JCI126863.
- Breit et al., *PLOS ONE* 2015, [PMID 26658523](https://pubmed.ncbi.nlm.nih.gov/26658523/), doi:10.1371/journal.pone.0144673.
- Huang et al., *Cell Research* 2019, [PMID 31201382](https://pubmed.ncbi.nlm.nih.gov/31201382/), doi:10.1038/s41422-019-0178-z; experimental homolog structures [6JKK](https://www.rcsb.org/structure/6JKK) and [6JKM](https://www.rcsb.org/structure/6JKM).
- Zhao et al., Phen2Gene, *NAR Genomics and Bioinformatics* 2020, [doi:10.1093/nargab/lqaa032](https://doi.org/10.1093/nargab/lqaa032).

## 10. Dataset citation and required acknowledgement

Sage Bionetworks. *Rare Disease, Real Kid. The 2026 MVA Hackathon*. [Synapse project `syn76251147`](https://www.synapse.org/Synapse:syn76251147); controlled Hugging Face dataset `SageBio/mva-hackathon-2026-data`, snapshot `f534cb0c1a607110c6dad0194299bd3dd62df542`. Accessed 2026-08-26. The Synapse project did not expose a DOI association on the audit date; any later organizer-supplied formal citation supersedes this identifier-based citation.

> This work was made possible through the Hackathon, organized by Sage Bionetworks in partnership with the MVA Society, Hugging Face, and BEACON (The Benchmarking, Evaluation, and Assessment Consortium for Science), with prize sponsorship from AWS and Anthropic. We are deeply grateful to the child and their family who generously contributed their data and their story to advance research into this rare disease. We acknowledge their trust in making this Hackathon possible.

## 11. Interpretation boundary

The planned submission asserts one rank-1 **research candidate pair**. It does not assert confirmed compound heterozygosity, a confirmed molecular diagnosis, clinical validity, or treatment efficacy. The unresolved phase and unproven missense mechanism are central conclusions, not footnotes.
