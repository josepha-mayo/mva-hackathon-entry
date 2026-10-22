# MVA migration handoff: 22 October 2026

## Start here

This branch updates handoff documentation and private-bundle verification tooling only. It does not replace the public report, amend the frozen release, establish efficacy, or submit an entry. Main was verified at `3a94ab4666ca11c62951f7db33a9bd98d427f639` before this update. Keep this handoff branch separate until reviewed.

Read the existing [operator handoff](TRACK2_SESSION_HANDOFF.md) for the frozen-release chain and rebind procedure. Its historical test results are not new verification of this branch or the unsigned candidate. The old working-folder and signer details are historical: inspect the actual Codex environment, do not assume those files or keys are available, and never recreate a signing identity silently.

## Latest work and private transfer

The complete latest report is the unsigned age-resolved turnover review candidate dated 22 October. It retains the prior 14-change integration and native-turnover amendment, then adds one conditional diagnostic paragraph. Do not substitute this paragraph alone for the complete candidate or drop the earlier independent amendments.

The full candidate is supplied in the user's private Library attachment, `MVA_age_resolved_turnover_review_2026-10-22.zip`. Attach that existing file to the intended private Codex work session. Do not upload it to this public repository, an issue, a pull request, or a public website. Store extracted material outside the checkout in private task storage; a gitignored directory alone is not an access control. If the private attachment is unavailable, ask the user to attach it rather than retrieving participant material from unrelated sources.

Integrity identities:

- Complete archive: `dfe554cabde43b35832ae15a2047f83e6c3a15af34acdf2b3d54209c6a827436`
- Complete candidate report: `91eee59817e75b18761436e2f417e647d5a129e1ca82969e4698b4e2c2edaf03`
- Unchanged native-turnover source report: `66e18c920cf8e8c4c212b5cdb06a4464cb977cee042ae6fe1620b91209b337e5`
- Earlier integrated bundle: `c28fa3d1b03f2346d6186ccfc303cfa931b62ae577a665ef029c6768ef92555d`
- Earlier native-turnover bundle: `6b6f5468a3616cee793e4f083b4aa1971f0775ca75ecb26ce2110889039e5fbd`

From the checkout run:

```sh
python scripts/verify_mva_review_bundle.py /path/to/private/MVA_age_resolved_turnover_review_2026-10-22.zip
```

This standard-library-only helper verifies the exact archive, all nine manifest entries, source and candidate hashes, and byte-exact additive reconstruction without extracting or executing archive content. A pass means integrity only, not clinical validity, release approval, or submission readiness. Read the private decision note and independent review before any integration. The bundled reconstruction script is separately available for a private scratch-copy reproduction; do not execute it in or publish its outputs to this public checkout.

## Scientific interpretation to preserve

- Variant confirmation, phase, exact-allele behavior and drug response remain unresolved. No exact-genotype laboratory proof was produced.
- Arimoclomol remains a conditional research hypothesis. No administration, dosing, cure, or cancer-prevention claim is authorized.
- Keep the separate RNA/genetic modality track distinct from pharmacological advancement; neither is validated treatment.
- Gate 5 stays closed unless all existing prior criteria pass. Nothing in the new paragraph weakens any gate.
- An induced degron is a perturbation tool, not an arbiter of native protein half-life.
- The new discriminator is conditional: if qualified turnover methods disagree, test whether their protein-age mixtures differ. Long labeling is an age mixture, not a pure mature cohort.
- New-label accumulation reflects both synthesis and loss. Do not infer translation rate or maturation yield without independent nascent-input identification and qualified recovery. If these cannot be identified, report the mechanism unresolved.
- Other-protein literature supports experiment design, not an exact-allele mechanism or efficacy. Do not describe the amendment as a biological discovery.

## Resume plan for Codex

1. Inspect the current remote and any local changes before checkout or merge. Preserve main and the frozen release. Do not revive an obsolete working tree or discard another operator's changes.
2. Verify the private bundle and review its full candidate against the frozen report. Record a private integration diff and preserve every independent amendment. No automatic public replacement.
3. Re-run the repository's baseline checks in the actual selected environment. Install only the project's documented dependencies; inspect its current project instructions first.
4. If a release is explicitly authorized later, perform a fresh privacy review of the exact intended public bytes, regenerate every bound receipt/manifest in the documented order, obtain the appropriate signing/attestation authorization, and re-run the complete checks. Existing signatures do not cover the candidate.
5. Keep report, methods disclosure, demo and pitch synchronized only after the candidate has an approved coherent freeze. Do not imply historical green receipts apply to revised scientific prose.
6. Confirm current portal state and attempt-specific authorization separately before any future submission. This migration does not authorize final submission, video upload, or new Codex tasks/quota.

Baseline commands to inspect and re-run in the complete repository:

```sh
python scripts/verify_track2_reproducibility.py .
python scripts/verify_track2_reproducibility.py . --reexecute
python scripts/privacy_gate.py .
python scripts/verify_all.py .
python scripts/check_submission_go.py
python scripts/check_docs.py .
python scripts/demo_contract.py
python -m unittest discover -s tests
```

The original handoff documents clean-tree source anchors and the rebind recipe. Do not bypass checks, fabricate lost audits, or weaken privacy allowlists to make a changed candidate pass.

## Schedule and completion status

Planning context supplied for this handoff: recording is 23 October 2026; submission deadline is 24 October 2026 at 23:59 UTC (25 October at 00:59 WAT). Verify the official portal before relying on remaining time or upload rules.

Track 1 was historically reported submitted with 100 points; that is not a fresh portal verification. Track 2 remains pending in the supplied handoff context. No portal status was independently checked for this migration and no submission was made.

Existing demo location: https://sagebio-rare-disease-real-kid-mva-hackathon-2026.hf.space/ . Its current availability and scientific-copy parity were not checked in this migration.

## Verification performed for this handoff

The supplied archive and all nine manifest entries matched their recorded digests. The helper reconstructed the candidate byte-for-byte from its bundled unchanged source plus the one amendment. A deliberately modified archive was rejected. These are artifact-integrity checks only. The full repository test suite, release attestations and portal were not re-verified for this documentation/tooling update.
