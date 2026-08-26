# Organizer clarification queue

Prepared for a public discussion or direct organizer question. Do not post or email without the user's approval.

1. **Track 1 ties and qualitative judging.** At the 2026-08-26 14:19 UTC snapshot, all 20 displayed entries had 100 rank points and F-max 1.000. The leaderboard source has no contractual deterministic tie-break beyond repository-list order, while the timeline mentions qualitative review and the methods template mentions Innovation and Scalability. What criteria and weights determine final Track 1 placement among perfect scores, and which submitted model/report is qualitatively reviewed?
2. **Secondary findings.** The FAQ says secondary findings do not affect automated scoring, but the published evaluator includes every row in rank/F-max thresholding and treats `finding_type` as informational. Which behavior is authoritative?
3. **Exact submission retention.** The public handler stores score metadata and the report but not the uploaded prediction CSV, its digest, scorer revision, or ground-truth revision. Will organizers preserve or rerun the exact CSV another way, and should entrants pin it in their GitHub repository?
4. **Controlled data and hosted services.** May gated VCF/read/phenotype content be processed by hosted LLM/API or commercial cloud services under the agreement, and what contractual safeguards are required? Until answered, this project treats hosted processing as NO-GO.
5. **Dataset license conflict.** Hub metadata says CC BY 4.0, while the access gate prohibits redistribution and requires deletion. Please confirm that the restrictive gate/Data Transfer Agreement controls the source dataset and CC BY applies only to participant outputs.
6. **Derived artifacts.** Rules allow public derived outputs but also require deletion of derived datasets. Please define which variant summaries, annotations, read slices, aggregate statistics, and trained artifacts are permitted publicly.
7. **Deletion email.** The Rules tab names `RarediseaserealkidMVAhackathon2026@synapse.org`; the access form names `MVAHackathon2026@synapse.org`. Which address is authoritative?
8. **Track 2 unit of enforcement.** Rules say one Track 2 submission per team; source code enforces one per Hugging Face user. How will duplicates across a team be identified?
9. **Track 2 drug eligibility.** Must a candidate be currently marketed in a named jurisdiction, or is any medicine with historical/current regulatory approval eligible? Are combinations allowed when every component is approved?
10. **Pitch-video scope.** The general rules say each team submission includes a three-minute video, while the Track 1 UI requires only CSV, report, and GitHub URL. Is video required only for Track 2?

Relevant existing discussions:

- Hosted LLM/API data-use question: <https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/discussions/2>
- GitHub visibility/content question: <https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/discussions/4>
- Experimental/combination drug question: <https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/discussions/5>
