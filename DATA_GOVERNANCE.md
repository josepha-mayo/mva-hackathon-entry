# Controlled-data governance

The dataset belongs to a real child. Winning never outranks that trust.

## Storage boundary

- Keep controlled source data outside this repository.
- Set `MVA_PRIVATE_ROOT` to one explicit, local, non-synced directory outside the public checkout.
- Fail closed until an elevated storage preflight confirms encryption protection, recovery readiness, restrictive access, safe local spill paths, and sufficient capacity. Keep the resulting account, path, hardware, and volume receipts in the private operations record, never in this repository.
- Do not place controlled files in Git, Git LFS, GitHub, Hugging Face repositories, OneDrive, Dropbox, notebooks, paste services, issue attachments, or chat messages.
- Do not copy controlled data into `outputs/`; only public submission artifacts belong there.
- Derived files that retain individual-level genotypes, phenotypes, read slices, sample identifiers, or re-identification risk remain controlled even if smaller than the originals.
- Do not send controlled content to hosted LLMs, APIs, or third-party services unless organizers explicitly confirm the agreement permits it and the required safeguards are in place.
- Hub metadata labels the dataset CC BY 4.0, but the gated agreement prohibits redistribution and requires deletion. Treat the restrictive gate/Data Transfer Agreement as controlling for source and derived individual-level data until the organizers clarify.

## Minimum necessary download

1. Pass `storage_preflight.py` and verify gated access.
2. Fetch the phenotype, VCF, and index at the pinned dataset revision into private atomic staging; preserve the private hash/provenance manifest there.
3. Run variant-level analysis and determine whether raw reads are necessary.
4. Download FASTQs only for explicit read-level validation gaps and only after the full-mode 650 GiB preflight passes.

## Container boundary

- Never put controlled files in an image build context, `COPY` instruction, named volume, Docker socket mount, or writable container layer.
- Use digest-pinned images with `--rm --network none --read-only --log-driver none --cap-drop ALL --security-opt no-new-privileges`.
- Bind only explicit private input/reference/run/temp directories. Inputs and references are read-only; all sort/temp work stays below `MVA_PRIVATE_ROOT`.
- Do not mount the public repository, user profile, credentials, or broad drive roots.
- Use internal generic filenames so logs do not repeat sample-specific source names.

For the first controlled pass, prefer native tools and keep Docker/WSL entirely out of the data path unless every backing and spill location has passed the same private review. Redirect process-scoped `TEMP`, `TMP`, Hugging Face, XDG, Python, Numba, joblib, plotting, sorting, and tool caches into explicit access-restricted subdirectories under the approved private root. Disable content indexing there before ingestion. Treat operating-system pagefiles and crash dumps as controlled-data spill risks when evaluating host encryption.

## Public-output review

Before a commit or submission:

```powershell
python scripts/privacy_gate.py .
git status --short
git diff --cached --stat
```

Public outputs may include the ranked challenge answer, code, methods, and aggregate/allowed evidence, but never the gated source files or unauthorized identifying detail. Cite public participant work if it influenced a hypothesis.

The two final Track 1 release surfaces are fail-closed. Their exact paths and
states live in `release/release-artifacts.json`, and the privacy gate recognizes
no alternate manifest location, role, path, or extension. A `planned` entry has
a null digest and grants no exception; if its artifact already exists, the gate
remains NO-GO. A `released` entry must bind the exact bytes with a lowercase
SHA-256 and pass its role-specific schema: the submission must be one primary
pair row in the frozen CSV order, while the report must be non-empty,
placeholder-free strict UTF-8 Markdown. Even then, only the
biological-identifier and coordinate checks are quarantined for that exact path
and digest. Credential,
controlled-payload, phenotype-bundle, operational-receipt, path, size, and magic
checks remain active. Copies, malformed declarations, surplus artifacts, and
staged or historical blobs without their corresponding manifest fail closed.

## Deletion

Challenge close is currently scheduled for 2026-10-24 23:59 UTC. The rules require deletion within 30 days from all local and remote environments and email confirmation to the organizers. Two official pages currently name different confirmation addresses (`RarediseaserealkidMVAhackathon2026@synapse.org` and `MVAHackathon2026@synapse.org`); obtain written clarification or notify both. Before deletion, resolve and verify every exact target path; do not use broad recursive globs or home/workspace roots.

Deletion checklist:

- local controlled-data root;
- package/tool caches containing gated artifacts;
- cloud instances and attached volumes;
- notebook runtimes and uploaded files;
- backup/sync locations;
- temporary directories and read slices;
- derived individual-level artifacts.

Keep only the public, allowed submission repository and reports.
