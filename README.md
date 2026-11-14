# Field Shift Rotation Twin

Open-source prototype built during the NASA Space Apps Challenge 2026, for the challenge "Field Shift: Adapting Farms with NASA Data".

> Working description, to be revised by the team.

The tool compares crop rotations for a field against the observed climate record. It combines NASA Earth data with local soil information and reports, for each rotation, soil loss, exposure to water deficit and the trend of soil carbon, with their uncertainty. When the data cannot separate two options, the answer is "not resolved" together with what to measure first.

## Status

Bootstrap. This repository holds the licence, the working rules and the development blueprint. There is no engine code yet.

## How we work

Read [docs/DEVELOPMENT_BLUEPRINT.md](docs/DEVELOPMENT_BLUEPRINT.md) before opening a branch. In short:

- English only, in code, documents and interface text.
- Every piece lands with its acceptance test.
- Every dataset, library, table and publication is recorded in [ATTRIBUTIONS.md](ATTRIBUTIONS.md) when it is first used.
- Every AI-assisted unit is recorded in [AI_USE_LOG.md](AI_USE_LOG.md).
- No secrets, no private data, no data from real producers.

## Lanes

Four developers write code, each orchestrating several AI coding sessions in parallel. Two science reviewers validate and never write code.

| Lane | Owner (role) | What it builds | Folders |
|---|---|---|---|
| L0 Core | Lead developer | Contracts and conventions, erosion engine, validation harness, integration into `main` | `contracts/`, `params/`, `engine/erosion/`, `validation/` |
| L1 Engines | Engines developer | Rotation calendar, daily water balance, residue ledger, AMG soil carbon | `engine/calendar/`, `engine/water/`, `engine/residues/`, `engine/amg/` |
| L2 Platform | Platform developer | Data adapters, decision layer, RothC soil carbon, API, saved case, CI and deploy | `adapters/`, `engine/rothc/`, `decision/`, `api/`, `demo/` |
| L3 Interface | Interface developer | Multi-field map, rotation editor, results, printable sheet, demo path | `web/` |
| Science review | Two science reviewers | Calibration, uncertainty ranges, test design, validation, plan adaptation | `docs/VALIDATION.md`; review of values |

One lane, one set of folders: nobody edits another lane's folder.

## AI use

AI coding assistants are used and declared: see [AI_USE_LOG.md](AI_USE_LOG.md). The product itself does not call a language model.

## Disclaimer

This is a research prototype made for a hackathon. It is not agronomic advice and it does not replace a professional soil-use plan. It is not affiliated with, nor endorsed by, NASA or any data provider.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
