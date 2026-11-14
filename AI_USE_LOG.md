# AI use log

One line per merged unit. Every AI-assisted commit also carries a co-author trailer.

| Date (UTC-3) | Lane | Unit or files | Tool | What the AI did | Reviewed by a person |
|---|---|---|---|---|---|
| 2026-11-14 | Bootstrap | `README.md`, `NOTICE`, `ATTRIBUTIONS.md`, `AI_USE_LOG.md`, `.gitignore`, `docs/DEVELOPMENT_BLUEPRINT.md` | Claude Code (Anthropic) | Drafted the working rules and the development blueprint from the team's planning notes. Wrote no engine, adapter, interface or test code | Pending team review |

Rules:

- No generated images, video or voice in the submission.
- A parameter value, a threshold, an expected test value or a citation produced by an AI session is a defect: a person supplies it.
- The product does not call a language model.
