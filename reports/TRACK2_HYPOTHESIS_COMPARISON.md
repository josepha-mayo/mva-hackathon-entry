# Track 2 — competing rescue hypothesis comparison

Selection rule: `tied_no_lead`
Lead hypothesis: `None`
Passing hypotheses: `['chaperone_pair', 'proteostasis_stabilizer']`

| hypothesis | status | reason | child_claim | work_ceiling | falsifiers | alternatives | controls |
|---|---|---|---|---|---|---|---|
| chaperone_pair | pass | weakest_link_respected | unsupported | experiment_to_run | 1 | 1 | 2 |
| proteostasis_stabilizer | pass | weakest_link_respected | unsupported | experiment_to_run | 1 | 2 | 2 |

Both hypotheses share the same rescue method (exact correction as positive control, lineage-tracked endpoint, predeclared numeric kill rule, interference counterscreen, multiplicity rule) but assert different mechanisms: functional rescue via a chaperone-style probe versus abundance rescue via a proteostasis stabilizer.

A pass is a method-specification check on synthetic fixtures — not evidence that either mechanism is biologically true.

- `chaperone_pair` fixture sha256: `c074b6ad0707650b7592d991f2c9eb25d3d91e3a7699dc3d435953671cf306b7`
- `proteostasis_stabilizer` fixture sha256: `3a2e5cfc8ed6c930582df0071884dd3a011cd2088ef9cb3ed6f2cf708058a595`
