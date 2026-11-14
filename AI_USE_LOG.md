# AI use log

One line per merged unit. Every AI-assisted commit also carries a co-author trailer.

| Date (UTC-3) | Lane | Unit or files | Tool | What the AI did | Reviewed by a person |
|---|---|---|---|---|---|
| 2026-11-14 | Bootstrap | `README.md`, `NOTICE`, `ATTRIBUTIONS.md`, `AI_USE_LOG.md`, `.gitignore`, `docs/DEVELOPMENT_BLUEPRINT.md` | Claude Code (Anthropic) | Drafted the working rules and the development blueprint from the team's planning notes. Wrote no engine, adapter, interface or test code | Pending team review |
| 2026-11-14 | Bootstrap | `docs/DEVELOPMENT_BLUEPRINT.md` | Claude Code (Anthropic) | Added the units and rules that four planning sessions reported as missing: parameter catalogue layout, uncertainty in the conventions, engine entry points, Platform examples, strings and shared value display moved to Block 0, CP1 seam unit | Pending team review |
| 2026-11-14 | Bootstrap | `docs/GETTING_STARTED.md`, `README.md` | Claude Code (Anthropic) | Wrote the onboarding steps for the platform and interface developers from the blueprint and from the reports of the lane planning sessions | Pending team review |

Rules:

- No generated images, video or voice in the submission.
- A parameter value, a threshold, an expected test value or a citation produced by an AI session is a defect: a person supplies it.
- The product does not call a language model.
