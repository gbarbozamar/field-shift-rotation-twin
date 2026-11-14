# AI use log

One line per merged unit. Every AI-assisted commit also carries a co-author trailer.

| Date (UTC-3) | Lane | Unit or files | Tool | What the AI did | Reviewed by a person |
|---|---|---|---|---|---|
| 2026-11-14 | Bootstrap | `README.md`, `NOTICE`, `ATTRIBUTIONS.md`, `AI_USE_LOG.md`, `.gitignore`, `docs/DEVELOPMENT_BLUEPRINT.md` | Claude Code (Anthropic) | Drafted the working rules and the development blueprint from the team's planning notes. Wrote no engine, adapter, interface or test code | Pending team review |
| 2026-11-14 | Bootstrap | `docs/DEVELOPMENT_BLUEPRINT.md` | Claude Code (Anthropic) | Added the units and rules that four planning sessions reported as missing: parameter catalogue layout, uncertainty in the conventions, engine entry points, Platform examples, strings and shared value display moved to Block 0, CP1 seam unit | Pending team review |
| 2026-11-14 | Bootstrap | `docs/GETTING_STARTED.md`, `README.md` | Claude Code (Anthropic) | Wrote the onboarding steps for the platform and interface developers from the blueprint and from the reports of the lane planning sessions | Pending team review |
| 2026-11-14 | Bootstrap | `docs/DEVELOPMENT_BLUEPRINT.md` | Claude Code (Anthropic) | Recorded two decisions of the lead developer: a session may propose conventions and test-case designs for a person to approve, and the provisional environment | Pending team review |
| 2026-11-14 | Bootstrap | `README.md`, `docs/DEVELOPMENT_BLUEPRINT.md`, `docs/GETTING_STARTED.md` | Claude Code (Anthropic) | Recorded the lead developer's split of lane L2 into two sub-lanes and their owners | Pending team review |
| 2026-11-14 | Bootstrap | `README.md`, `docs/DEVELOPMENT_BLUEPRINT.md`, `docs/GETTING_STARTED.md` | Claude Code (Anthropic) | Named the owner of each lane, as the lead developer asked | Pending team review |
| 2026-11-14 | L0 | `l0/validation-layout` (#9): `validation/` | Claude Code (Anthropic) | A builder session wrote the validation store layout, the record check and its tests as a proposal; a separate verifier ran and probed it; the builder fixed the defects found | Merged by the lead developer; the proposed format and cases still wait for approval |
| 2026-11-14 | L0 | `l0/params-layout` (#14): `params/` | Claude Code (Anthropic) | A builder session wrote the parameter catalogue layout, the record check and its tests as a proposal; a separate verifier ran and probed it | Merged by the lead developer; the verifier's remarks and the proposed format still wait for a decision |
| 2026-11-14 | L0 | Acceptance limit per sub-lane (#23): `docs/DEVELOPMENT_BLUEPRINT.md`, `docs/GETTING_STARTED.md` | Claude Code (Anthropic) | An AI session wrote the rule that the limit of units waiting for acceptance counts per lane, with L2a and L2b separately, as the lead developer dictated | Merged on the lead developer's instruction; an AI session ran the merge command; no second reviewer |

Rules:

- No generated images, video or voice in the submission.
- A parameter value, a threshold, an expected test value or a citation produced by an AI session is a defect: a person supplies it.
- The product does not call a language model.
