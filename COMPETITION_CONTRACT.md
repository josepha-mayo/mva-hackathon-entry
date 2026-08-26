# Competition contract snapshot

Verified against the rendered challenge Space and public source on **2026-08-26**. Dates are explicitly subject to change; refresh this document before any submission.

## Timeline

| UTC date | Milestone |
|---|---|
| 2026-08-24 | Launch; gated dataset available |
| 2026-08-25 | Submissions open |
| 2026-10-24 23:59 | Submissions close; Track 1 leaderboard freezes |
| 2026-10-24 through 2026-11-24 | Track 1 qualitative review and Track 2 panel judging |
| 2026-11-25 | Winners announced |

The close time is consistent across current official pages. The judging/announcement dates are not: the FAQ, Track 2 form, and Official Rules instead say judging takes approximately two to three months and that an exact announcement date will be posted later. Treat November 25 as provisional and refresh the Community page before planning around it.

## Eligibility and team rules

- Participants must be at least 18 and follow both Hugging Face terms and the hackathon rules.
- Each team member registers individually and accepts the rules.
- Teams are optional. A participant may enter either or both tracks.
- Track 1 gives each registered participant six submissions; only the best score is displayed.
- Track 2 accepts one final submission per team. One team member must submit it; duplicates are ignored.

## Track 1

Goal: rank the specific causal variant or compound-heterozygous pair for one proband using GRCh38 coordinates.

Required artifacts:

1. CSV with at most ten candidate rows.
2. PDF or Markdown methods report.
3. Public GitHub repository with documented, reproducible code.

Required CSV fields:

`proband_id,chrom_1,pos_1,ref_1,alt_1,chrom_2,pos_2,ref_2,alt_2,epcr,finding_type,notes`

Automated metrics:

- Rank points: full match at rank 1 = 100; ranks 2-3 = 50; ranks 4-5 = 25; ranks 6-10 = 10. One recovered allele of a true compound-heterozygous pair receives half credit.
- F-max: maximum individual-variant F1 over submitted EPCR thresholds.

Important source-code nuance: `finding_type` is informational in the published evaluator. Secondary rows participate in the same threshold sweep. Keep any secondary rows below the primary pair's EPCR so a clean threshold can still achieve F-max 1.000.

Additional evaluator constraints verified against the source:

- A compound-heterozygous answer must appear as one paired row for full rank credit; two correct single-variant rows receive only partial rank credit even though F-max can reach 1.000.
- EPCR is ordinal. Equal EPCR values enter a threshold together and can lower F-max; use distinct values.
- Chromosome strings and variant representations are matched literally. Normalize and use the gated VCF's exact `chr` representation.
- The platform does not retain the uploaded prediction CSV, its digest, scorer revision, or ground-truth revision. Preserve and publish the exact allowed CSV in the pinned GitHub commit.

## Track 2

Goal: characterize the variant mechanism and propose existing approved medicines for further investigation. These are hypotheses, not evidence that a medicine works.

Required artifacts:

1. PDF or Markdown report.
2. Public GitHub repository with documented, reproducible code.
3. Three-minute pitch video on YouTube or Vimeo.

Only one final submission is accepted. Judging weights:

- Scientific rigor: 35%
- Potential impact: 25%
- Innovation: 25%
- Scalability: 15%

The public Track 1 leaderboard is already saturated with perfect automated scores. Its displayed medal order is not a meaningful tie-break: source code sorts only on the two equal metrics and inherits repository-list order. The Track 1 qualitative tie-break/weighting is not published and requires organizer clarification.

## Data and privacy obligations

- Gated single-subject dataset, approximately 85 GB. The authenticated Hub manifest currently lists 13 repository files: eight FASTQs, one VCF, its index, one clinical DOCX, README, and `.gitattributes`.
- Public pages describe a VCF plus optional raw-alignment/read data and standardized HPO terms.
- Access is under WCG IRB protocol `#20252010` and a Data Transfer Agreement.
- No redistribution or recontact of the child, family, or MVA Society contacts.
- Controlled data must be deleted from every local/cloud/notebook/private-repository environment within 30 days after close, followed by deletion confirmation. There is an official-source discrepancy that must be resolved before deletion: the rendered Rules tab says `RarediseaserealkidMVAhackathon2026@synapse.org`, while the gated access attestation says `MVAHackathon2026@synapse.org`.
- Submissions, code, reports, and results are CC BY 4.0 and may be rerun and attributed publicly.
- A publication embargo runs from challenge close until the organizers post their summary report or preprint. Preliminary conference material requires prior written approval.

The gated form additionally requires Institution, City and Country, a date, and explicit checkbox attestations for age, deletion, no recontact, no redistribution, lawful/professional use, breach reporting, organizer reruns, CC BY attribution, organizer recontact, public result sharing, official rules, and publication citation/acknowledgment.

The dataset API currently labels the gate `auto`: after a logged-in user supplies those fields and personally accepts every binding attestation, access should be automatic rather than manually reviewed. This project must not accept those terms on the user's behalf without their explicit confirmation.

## Submission gate

No upload until all of the following are true:

- registration and gated access are verified for the submitting account;
- the exact current rules and leaderboard have been refreshed;
- every public artifact passes the privacy gate;
- Track 1 output reproduces the official scorer locally and independent read/VCF evidence supports the top row;
- Track 2 report has citation, exposure, contradiction, and cancer-safety audits;
- all intended Track 1 candidate files are frozen before the first submission, so the six-attempt allowance is not used as an adaptive hidden-answer probe;
- the user explicitly authorizes the actual upload/submission.
