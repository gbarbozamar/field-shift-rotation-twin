# Field Shift Rotation Twin

Open-source prototype built during the NASA Space Apps Challenge 2026, for the challenge "Field Shift: Adapting Farms with NASA Data".

> Working description, to be revised by the team.

The tool compares crop rotations for a field against the observed climate record. It combines NASA Earth data with local soil information and reports, for each rotation, soil loss, exposure to water deficit and the trend of soil carbon, with their uncertainty. When the data cannot separate two options, the answer is "not resolved" together with what to measure first.

## Who owns what

| Person | Lane | Builds | Folders |
|---|---|---|---|
| **Gustavo** | L0 Core | Contracts and conventions, erosion engine, validation harness, integration into `main` | `contracts/`, `params/`, `engine/erosion/`, `validation/` |
| **Gustavo** | L1 Engines | Rotation calendar, daily water balance, residue ledger, AMG soil carbon | `engine/calendar/`, `engine/water/`, `engine/residues/`, `engine/amg/` |
| **Enzo** | L2a Platform: data and service | Data adapters, API, CI and deploy | `adapters/`, `api/` |
| **Martín** | L2b Platform: decision and carbon | Decision layer, RothC soil carbon, saved case | `decision/`, `engine/rothc/`, `demo/` |
| **Martín** | L3 Interface | Multi-field map, rotation editor, results, printable sheet, demo path | `web/` |
| **Adrian** and **Leonardo** | Science review, no code | Calibration, uncertainty ranges, test design, validation, plan adaptation | `docs/VALIDATION.md`; review of values |

Gustavo is the lead developer and decides what enters `main`. Enzo is the platform developer and decides structure, dependencies and deploy for everyone. Martín is the interface developer and decides what is delivered and when. One lane, one set of folders: nobody edits another lane's folder.

## Status

Bootstrap. This repository holds the licence, the working rules and the development blueprint. There is no engine code yet.

## How we work

New to the repository? Start with [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md): access, a clean place to work, and the first steps of each lane.

Then read [docs/DEVELOPMENT_BLUEPRINT.md](docs/DEVELOPMENT_BLUEPRINT.md) before opening a branch. In short:

- English only, in code, documents and interface text.
- Every piece lands with its acceptance test.
- Every dataset, library, table and publication is recorded in [ATTRIBUTIONS.md](ATTRIBUTIONS.md) when it is first used.
- Every AI-assisted unit is recorded in [AI_USE_LOG.md](AI_USE_LOG.md).
- No secrets, no private data, no data from real producers.

## Lanes by role

The same table by role, as the blueprint names them.

Three developers write code across four lanes (the platform lane is split in two sub-lanes), each orchestrating several AI coding sessions in parallel. A developer can own more than one lane. Two science reviewers validate and never write code.

| Lane | Owner (role) | What it builds | Folders |
|---|---|---|---|
| L0 Core | Lead developer (Gustavo) | Contracts and conventions, erosion engine, validation harness, integration into `main` | `contracts/`, `params/`, `engine/erosion/`, `validation/` |
| L1 Engines | Engines developer (Gustavo) | Rotation calendar, daily water balance, residue ledger, AMG soil carbon | `engine/calendar/`, `engine/water/`, `engine/residues/`, `engine/amg/` |
| L2a Platform: data and service | Platform developer (Enzo) | Data adapters, API, CI and deploy | `adapters/`, `api/` |
| L2b Platform: decision and carbon | Interface developer (Martín) | Decision layer, RothC soil carbon, saved case | `decision/`, `engine/rothc/`, `demo/` |
| L3 Interface | Interface developer (Martín) | Multi-field map, rotation editor, results, printable sheet, demo path | `web/` |
| Science review | Science reviewers (Adrian and Leonardo) | Calibration, uncertainty ranges, test design, validation, plan adaptation | `docs/VALIDATION.md`; review of values |

One lane, one set of folders: nobody edits another lane's folder.

## AI use

AI coding assistants are used and declared: see [AI_USE_LOG.md](AI_USE_LOG.md). The product itself does not call a language model.

## Disclaimer

This is a research prototype made for a hackathon. It is not agronomic advice and it does not replace a professional soil-use plan. It is not affiliated with, nor endorsed by, NASA or any data provider.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
