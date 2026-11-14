# Development blueprint

How this repository is built during the event: who owns what, how each developer runs several AI coding sessions in parallel, what "done" means, and in which order the pieces land.

This is a working document. It can change at any checkpoint; it never changes silently.

## 1. Ground rules

1. **Everything here is written during the event window.** No code, data files or parameter files are copied from earlier work or from private repositories.
2. **English only** in code, documents and interface text.
3. **Licence:** Apache-2.0. Dependencies must have an OSI-approved licence, recorded when they are added.
4. **Public from the first commit.** A leak cannot be undone: no secrets, no private data, no data from real producers, no company or product names.
5. **Attributions on the spot.** Every dataset, library, table or publication goes into `ATTRIBUTIONS.md` when it is first used, with name, URL, licence and citation.
6. **AI use is declared.** Every merged unit gets one line in `AI_USE_LOG.md`, and every AI-assisted commit carries a co-author trailer.
7. **No number without a source.** A value shown in the interface carries its source or an explicit "assumption" mark. A missing value travels as missing, with its reason. It is never zero by default.
8. **A test defines "done".** A function without its acceptance test is not finished, even if it works.

## 2. People and lanes

Five people. Three write code by orchestrating AI sessions across four lanes; two review science and never write code. The roles below are roles, not headcount: one developer can hold two of them, and then runs each lane with its own sessions and its own clone of the repository.

| Person | Role | Lane | Owns (folders) | Main responsibility |
|---|---|---|---|---|
| **Gustavo** | Lead developer | L0 Core | `contracts/`, `params/` (structure), `engine/erosion/`, `validation/` | Contracts and conventions, erosion engine, validation harness, integration authority |
| **Gustavo** | Engines developer | L1 Engines | `engine/calendar/`, `engine/water/`, `engine/residues/`, `engine/amg/` | Rotation calendar, water balance, residue ledger, AMG carbon |
| **Enzo** | Platform developer | L2a Platform: data and service | `adapters/`, `api/`, CI and deploy | Data adapters, API, pipeline and deploy |
| **Martín** | Interface developer | L2b Platform: decision and carbon | `decision/`, `engine/rothc/`, `demo/` | Decision layer, RothC, saved case |
| **Martín** | Interface developer | L3 Interface | `web/` | Multi-field map, rotation editor, results, printable sheet, demo path |
| **Adrian** and **Leonardo** | Science reviewers | — | `docs/VALIDATION.md`, review of `params/` and expected values | Calibration, uncertainty ranges, test design, validation, plan adaptation |

**Wherever this document names a role, it means that person:** lead developer and engines developer, Gustavo; platform developer, Enzo; interface developer, Martín; science reviewers, Adrian and Leonardo.

**Lane L2 is split in two sub-lanes.** L2a, data and service, belongs to Enzo, the platform developer. L2b, decision and carbon, belongs to Martín, the interface developer, together with L3. Both use branches named `l2/<unit>`. Each sub-lane has its own acceptance limit (section 3.2). In the work packages of section 8, an L2 unit belongs to the sub-lane that owns its folder. The platform developer still decides technical matters for everyone: structure, dependencies and deploy. If L3 together with L2b is too much for one developer, `engine/rothc/` moves to L2a: Martín says so at a checkpoint and the move is written here. It is not carried silently.

**One lane, one set of folders.** Nobody edits another lane's folder. A contract changes only at a checkpoint, with notice to everyone.

### Decision rights

| Decision | Who decides |
|---|---|
| Scientific: method, parameter, what is claimed and with which word | Science reviewers; the lead developer breaks ties |
| Data: source, unit, fallback | Science reviewers |
| Technical: structure, dependencies, deploy | Platform developer |
| Integration: what enters `main` and when | Lead developer |
| Delivery: what is submitted and when | Interface developer |
| Scope: what is cut | Everyone at the checkpoint; no agreement in 5 minutes, the lead developer decides |

## 3. How one developer orchestrates several sessions

Each developer is an orchestrator. The developer plans, briefs, reads diffs and merges. The sessions write code.

### 3.1 Session types

| Session | What it does | Rule |
|---|---|---|
| **Builder** | Implements exactly one unit | One session, one unit, one branch, one worktree |
| **Verifier** | Runs the acceptance test and reads the diff against the brief | Fresh session that did not write the code; read-only |
| **Scout** (optional) | Reads public documentation of a data service or library and reports | Read-only; never chooses a source or a dependency |

### 3.2 Parallelism limits

- Up to **three builders in flight** per developer, always on disjoint files.
- **No new unit is launched while two units of the lane wait for acceptance.** The two sub-lanes of L2 count separately: units of L2a that wait do not stop L2b, and units of L2b that wait do not stop L2a.
- Nothing runs unattended against `main`. Nothing runs overnight.
- Each developer reads their remaining quota at every checkpoint and reports it.

### 3.3 Unit of work

A unit takes 20 to 45 minutes, lives in one folder and has one acceptance test known before it starts. If a unit needs two folders, it is two units with a seam between them.

Flow of a unit:

1. The developer opens an issue with the brief (section 9) and the label of the lane.
2. `git worktree add ../wt-<unit> -b <lane>/<unit>` and a new builder session inside that worktree.
3. The builder works against the contract example, not against another lane's unfinished code.
4. A verifier session runs the test and reviews the diff.
5. The developer reads the diff, opens the pull request and links the issue.
6. CI passes. The **consumer of the seam** approves. Science-class changes also need a science reviewer.
7. Squash merge. One line in `AI_USE_LOG.md`. The worktree is removed.

### 3.4 Session hygiene

- Sessions run in a **clean profile and a clean folder**: no private repositories open or mounted, no connectors to company systems, no inherited memory or instructions, no keys in the environment.
- A session that has read private or proprietary code is **never** used to write code for this repository.
- The context given to a session is the brief, the contract, its example, the acceptance test and public citations. Internal planning notes are not pasted into sessions.
- Sessions do not read source code of third-party repositories.

### 3.5 Never delegated to a session

- A threshold.
- The choice of a data source or of a dependency.
- What is claimed in the interface or in the submission, and with which word.
- Pushing to `main`, deploying, cutting scope, submitting.

Who transcribes a value from its source into `params/` or `docs/VALIDATION.md` is decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622). An AI session may transcribe a value, a unit, a range, an expected result or a citation from a published source, and one person checks it against that source. The transcription is valid only if it carries the full reference, the locator (page, table, equation or example number, or URL with anchor), the verbatim text it comes from, and the date it was read. The person who checks opens the source at the locator, checks every number, and signs the check. A value written by an AI session from memory, without a source opened and quoted, is still a defect.

### 3.6 Three classes of change

| Class | Examples | Who writes it | Who accepts it |
|---|---|---|---|
| **Science** | Parameters, thresholds, ranges, expected values, equations, units, citations | A value is transcribed from its source as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says (section 3.5), and one person checks it against the source | A science reviewer |
| **Logic with a known answer** | Calendar, matrix, decision, routes | A person designs the cases first; a builder implements | Lane owner and the consumer of the seam |
| **Interface and glue** | Screens, wiring, pipeline | Builder | Folder owner; someone who did not build it looks at the screen with real data |

### 3.7 Proposals by a session

For conventions, definitions, contract field lists and the design of test cases, a builder may write a proposal instead of waiting for a person to write them first.

- Every proposed item is marked `PROPOSED`. Anything the builder cannot responsibly propose is marked `OPEN`, with the question a person has to answer.
- A proposal takes effect only when a person approves the pull request. Science-class proposals also need a science reviewer.
- This never covers the list in section 3.5. Parameter values, thresholds, ranges, expected test values and citations are supplied by people. Where one is needed, the builder writes `OPEN` or `CITATION NEEDED` and stops there.

## 4. Repository layout

| Folder | Content | Owner |
|---|---|---|
| `contracts/` | Schemas and accepted examples of every contract; conventions sheet | Lead |
| `params/` | Crop and rotation parameters, each with its citation | Lead (structure); science reviewers accept values |
| `engine/` | Pure functions and their tests, one subfolder per engine | Lead, Engines; RothC is L2b |
| `adapters/` | One module per data source | Platform (L2a) |
| `decision/` | Limits, counts by year, paired differences, state, tipping, measurement priority | Interface developer (L2b) |
| `api/` | HTTP routes | Platform (L2a) |
| `web/` | Frontend | Interface |
| `validation/` | Expected values with source, protocol runs, results including failures | Lead; science reviewers |
| `demo/` | Demonstration cases and their cache; opens without a backend | Interface developer (L2b) |
| `docs/` | Method, limits, validation, this blueprint | Shared |

Folders are created by the first unit that needs them.

### Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI, Pydantic, httpx |
| Computation | numpy in pure functions |
| Geometry | shapely, pyproj |
| Storage | Files (JSON cache and results). No database |
| Frontend | React, Vite, TypeScript, Tailwind, shadcn/ui, TanStack Query |
| Map and drawing | leaflet, terra-draw |
| Charts | Recharts |
| Explanation text | Deterministic templates. No language model in the product |
| Tests | pytest, against published or reference values |
| Deploy | Static frontend and one backend container, both on a public URL without login |

Only the platform developer adds a dependency, and records its licence at that moment.

**Provisional environment,** until the platform developer fixes the list: Python 3.12, pytest and Pydantic. A pull request that relies on it says so in its description.

## 5. Contracts first

Before engine code, each producer writes by hand an example of what it will emit and its consumer signs it. From then on everyone works against the example. Integrating means replacing an example with real data, one seam at a time.

| Contract | Producer → consumer | Purpose of the example |
|---|---|---|
| Rotation definition | Interface → Engines | What the user declares per component and which calendar rules are checked |
| Rotation calendar | Engines → Lead | The C factor can be computed before the calendar engine exists |
| Site data: climate | Platform → Lead, Engines, Interface | Engines do not wait for adapters |
| Site data: soil and slope | Platform → Lead, Engines, Interface | Same |
| Results table | Lead, Engines → Platform | The decision is tested with hand-made tables |
| Results per rotation | Lead, Engines → Platform, Interface | Monthly breakdown; unit and direction of each indicator |
| Decision output | Platform → Interface | Decision screens are built before the calculation exists |
| Test plan | Science reviewers → Engines, Platform | The single file read by the matrix and the decision. No thresholds elsewhere |
| Saved case | Platform → Interface | What is stored per case, with date and citation; opens offline |
| `ResidueLedger` | Engines → Lead, Platform, Interface | Biomass and carbon closure; export and retention; roots and cover kept apart |
| `CarbonForcing` | Platform → Engines, Platform (RothC) | Same inputs, climate and horizon for both carbon models |
| `ModelState` | Engines, Platform → Lead | Same starting soil carbon across models; no resets between crops |
| `CarbonBalance` | Engines, Platform → Interface | Month, year and rotation; each model labelled; typed absences |
| Engine entry points | Lead, Engines → Platform | The route calls engines through agreed signatures |

Where this table says Platform: site data and `CarbonForcing` come from L2a; decision output, saved case and the RothC side of the carbon contracts come from L2b.

**Conventions sheet** (`contracts/CONVENTIONS.md`, first unit of the lead): unit and direction of each indicator; how an uncertainty range travels with a value; how a missing value and its reason travel; provenance label per value (`DECLARED`, `OBSERVED`, `DERIVED`, `SIMULATED`); numbering of months and agricultural years; time zone of every daily series.

**Engine entry points** (`contracts/ENTRYPOINTS.md`): the name, arguments and return type of the one public function of each engine. The engine's lane and the platform developer agree on it before Block 1, so the route is built against signatures and not against unfinished engines.

### Open decision

Section 2 says nobody edits another lane's folder, and this section says each producer writes its own example. Until the lead developer decides otherwise: the producer writes the example by hand in the issue, an L0 builder lands it under `contracts/`, and the consumer approves the pull request.

## 6. Integration

- `main` can be shown at any time and deploys by itself.
- Nobody, person or session, pushes to `main` directly or rewrites its history after the bootstrap commit.
- Every merge passes CI: tests, frontend build, contract validation, secret scan, scan for company names and for personal names other than the first names of the team in section 2, dependency licences.
- `main` red: whoever broke it fixes or reverts within 15 minutes.
- Branch names: `l0/<unit>`, `l1/<unit>`, `l2/<unit>`, `l3/<unit>`.

## 7. Checkpoints

Ten minutes, standing. One shared demonstration on the public URL by someone who did not build what is shown. Then: what is in, what is missing, what is cut; quota used per developer; units waiting for acceptance.

| Checkpoint | When | Must be true on the public URL |
|---|---|---|
| **CP0** | Saturday, first public deploy (planned 11:00) | Skeleton deployed. Contracts and examples in `main`. CI active |
| **CP1** | Saturday 14:00 | One rotation runs end to end with real NASA POWER and GPM IMERG data. Checked by someone who did not build it |
| **CP2** | Saturday 19:00 | Three rotations with soil loss and water-deficit exposure from real data. A thin real matrix went through the decision and returned a state |
| **CP3** | Saturday 23:00 | Decision state from real data. The saved case opens as the entry point. Everyone leaves by 23:30 |
| **CP4** | Sunday 12:00 | **Feature freeze** |
| **CP5** | Sunday 18:00 | **Code freeze.** Only fixes that keep the demonstration working |

At CP1 climate is real. Soil and slope can still come from the accepted example, shown as example data, because their adapter lands in Block 2.

If CP1 fails, Core, Engines and the platform route stop everything else until it passes. Interface and the decision layer continue.

## 8. Work packages

Units are listed in landing order. Codes in brackets are acceptance tests of the validation protocol (`docs/VALIDATION.md`, written by the science reviewers).

### Block 0 — bootstrap, until CP0

| Lane | Units | Parallel sessions |
|---|---|---|
| L0 Core | Conventions sheet · contract schemas with hand-written examples · validation harness layout (where an expected value and its citation live) · parameter catalogue layout in `params/` (how a value, its range and its citation are stored; no values) | 2 builders, 1 verifier |
| L1 Engines | Calendar example signed by Core · rotation definition agreed with Interface | 1 builder |
| L2 Platform | Hand-written examples of the contracts Platform produces: site data (climate; soil and slope) and decision output · backend skeleton · CI with all scans · public deploy of `main` | 2 builders, 1 verifier |
| L3 Interface | Frontend skeleton and static deploy · all strings in one English file · shared display of a value (unit, provenance and source, or missing with its reason) · multi-field identity screen on example data | 2 builders |

### Block 1 — one rotation end to end, until CP1

| Lane | Units | Parallel sessions |
|---|---|---|
| L0 Core | Engine entry points agreed with Platform · slope length and steepness equations [E3] · monthly erosivity fraction · annual soil-loss equation with unit guard [E8] and invariants [E9] | 3 builders, 1 verifier |
| L1 Engines | Calendar engine with feasibility check (an infeasible calendar returns no ranking) · reference evapotranspiration against a worked FAO-56 example [H2], in `engine/water/et0/` · water balance skeleton, in `engine/water/balance/` | 3 builders, 1 verifier |
| L2 Platform | NASA POWER adapter, meteorology and IMERG precipitation, in UTC, first response cached per case · route for one rotation · decision functions on hand-made tables [D1, D2, D5, D6, D7] | 3 builders, 1 verifier |
| L3 Interface | Entry screen · map · site sheet (three units) · rotation ribbon · replace the examples with the Platform route for one rotation (the CP1 seam) | 2 builders, 1 verifier |

### Block 2 — two clocks and the decision, until CP2

| Lane | Units | Parallel sessions |
|---|---|---|
| L0 Core | Cover-management factor by period with its sub-factors · plausibility against published plot ratios [E1b] · order between systems [E2] | 2 builders, 1 verifier |
| L1 Engines | Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1] · residue ledger · thin matrix: one field, three rotations, all years, one uncertain input | 3 builders, 1 verifier |
| L2 Platform | Soil and terrain adapters with unit guard · tipping point, measurement priority and measurement input [D3, D4, D10, D12] · RothC with common forcings · thin matrix through the decision | 3 builders, 1 verifier |
| L3 Interface | The two clocks (soil loss and water) on examples, then on real data · cards with ranges · result per model with availability states | 2 builders, 1 verifier |

A person, not a session, runs the same rotations in the official national erosion program for the comparison [E1a].

### Block 3 — the full decision on real data, until CP3

| Lane | Units | Parallel sessions |
|---|---|---|
| L0 Core | Contrast case from published runoff plots: modelled next to measured [E7, H10] · model cards and limits text (written by people) | 2 builders, 1 verifier |
| L1 Engines | AMG annual reference and monthly adaptation, checked against each other under uniform forcing · bounded matrix | 2 builders, 1 verifier |
| L2 Platform | RothC by month, year and cycle · saved case with both carbon models and typed absences · bounded matrix through the decision | 2 builders, 1 verifier |
| L3 Interface | Robustness card · month, year and rotation views · an edit invalidates saved results · entry opens the saved case | 2 builders, 1 verifier |

### Block 4 — Sunday until CP4

| Lane | Units | Parallel sessions |
|---|---|---|
| L0 Core | Validation protocol run and recorded, **including what fails** · trivial comparators [E0, H0, D0] | 1 builder, 1 verifier |
| L1 Engines | Test plan run on both demonstration fields exactly as written · walkthrough from zero on a clean machine · regional soil-moisture contrast with SMAP [H5] | 2 builders, 1 verifier |
| L2 Platform | Tipping, priority and measurement input on real data · figure "average climate against real years" with Interface | 2 builders, 1 verifier |
| L3 Interface | "Measure first" with its field · named-years selector · printable sheet · polish only inside the demo path | 2 builders, 1 verifier |

### Block 5 — delivery, until CP5

Stable `main`, green tests, README, licences, consolidated AI log, tag of the delivered commit. The demonstration video or slides are recorded by people from the real interface: no generated images, video or voice.

### Gated extras

Started only when the core of the lane is accepted. If not reached, shown as "not available", never with sample values.

| Extra | Lane | Gate |
|---|---|---|
| Frost and heat-day counts per month from NASA POWER daily minimum and maximum temperature | L1 Engines | Core accepted at CP2 |
| Green-cover strip from Landsat and Sentinel-2 (HLS) or MODIS | L2 Platform, read by science reviewers | Sunday 10:00: does the series add evidence? |
| Simple budget | L2 Platform, L3 Interface | Core accepted at CP2; does not displace tests |

## 9. Brief for a builder session

Copy into the issue and into the first message of the session. Fill every field.

```text
UNIT: <lane>/<unit-name>
GOAL: <one sentence: what exists when this is done>
FOLDER YOU OWN: <single folder>   DO NOT TOUCH: everything else
CONTRACT: <path to schema and to the accepted example you consume or emit>
ACCEPTANCE TEST: <path and command; expected values are already in the file, do not change them>
INPUTS YOU MAY USE: <files, public documentation URLs>
OUT OF SCOPE: <what not to build>
RULES:
- English only. Pure functions; no network calls outside adapters/.
- Do not add dependencies. Ask if you think one is needed.
- Do not invent parameter values, thresholds, expected values or citations. If one is missing, stop and report it.
- A missing value stays missing, with its reason. Never default to zero.
- Do not read or copy code from other repositories.
- Commit on your branch only. Do not push to main.
REPORT WHEN DONE: what you built, test output, anything you could not verify.
```

Brief for a verifier session: the same header, plus "You did not write this code. Run the acceptance test, read the diff against the brief, and list every place where the code does something the brief did not ask for or skips something it asked for. Do not edit files."

## 10. Science review

The science reviewers do not write code. They:

- fix thresholds and uncertainty ranges **before** results are seen;
- check each transcribed value against its source as the second person;
- decide whether a calibration is defensible and how it is labelled;
- read the trivial comparators and say so when the simple version gives the same order;
- open issues labelled `science` when the plan has to adapt.

A pull request labelled `science` cannot merge without one reviewer approval. Nobody approves their own values.

## 11. When things go wrong

| Situation | Rule |
|---|---|
| A developer is stuck for more than 20 minutes | Says so. The backup of the lane steps in |
| A control fails | It is recorded as failed. The module is shown as degraded or not available |
| A source is down | Use the cached first response. A fallback source is a science decision |
| Two units wait for acceptance | No new unit in that lane until one is accepted. L2a and L2b count separately |
| L3 together with L2b is too much for the interface developer | Says so at a checkpoint. `engine/rothc/` moves to L2a and the change is written in section 2 |
| Quota of one developer runs out | Their open units are re-briefed to another developer's sessions at the next checkpoint |
| A session produces a value, threshold or citation | Discard it. A person supplies it |
