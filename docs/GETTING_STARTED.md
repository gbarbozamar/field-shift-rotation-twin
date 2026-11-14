# Getting started

For the developers who join a lane. Read this first, then [DEVELOPMENT_BLUEPRINT.md](DEVELOPMENT_BLUEPRINT.md).

- [All developers](#all-developers)
- [Platform developer (sub-lane L2a)](#platform-developer-sub-lane-l2a)
- [Interface developer (lane L3 and sub-lane L2b)](#interface-developer-lane-l3-and-sub-lane-l2b)

## All developers

### 1. Access

The repository is public: you can read and clone it now. To push branches you need write access. Send your GitHub username to the repository owner and accept the invitation. Until then you can work from a fork and open pull requests from it.

### 2. A clean place to work

AI sessions that write code for this repository run in a clean environment (blueprint, section 3.4):

- an operating-system profile or machine with **no private or proprietary repositories** open or mounted;
- **no connectors** to mail, chat, hosting, databases or company systems attached to the session;
- no inherited memory or instructions from other projects;
- no keys or tokens in the environment.

A session that has read private or proprietary code is never used here.

### 3. One clone per lane

```bash
git clone https://github.com/gbarbozamar/field-shift-rotation-twin.git fsrt-<lane>
```

Use a commit email that is not a company address, for example your GitHub no-reply address:

```bash
git config user.email "<id>+<username>@users.noreply.github.com"
```

### 4. Plan before building

Start one AI session in your clone with the prompt below. It reads the blueprint and returns the units of your lane as briefs, plus the list of things a person has to supply. It writes nothing.

```text
You are a clean planning session for lane <LANE> of the repository in this folder.

Read README.md, docs/GETTING_STARTED.md and docs/DEVELOPMENT_BLUEPRINT.md in full. They are the only specification you have.

Then do this, and stop:
1. List the Block 0 and Block 1 units of lane <LANE> from section 8 of the blueprint.
2. For each unit, write a brief in the exact format of section 9.
3. For each unit, list what a person must supply or decide before a builder can start: parameter values, thresholds, expected test values, citations, wording, and choices of data source, dependency or hosting. Do not invent or choose any of these.
4. Name the seams with other lanes: which contract example each unit consumes or emits, and which lane is on the other side.
5. Propose which units can run in parallel on disjoint files, and which must wait.

Do not write code, tests or data files, do not create branches, do not commit, push or deploy. Work only inside this folder. English only.
```

### 5. Build, one unit at a time

Follow section 3.3 of the blueprint. In short:

1. Open an issue with the brief and the label of your lane.
2. `git worktree add ../wt-<unit> -b <lane>/<unit>` and a **new** builder session inside that worktree.
3. A second, fresh session verifies: it runs the acceptance test and reads the diff. It does not edit.
4. You read the diff, open the pull request and link the issue.
5. CI passes, the consumer of the seam approves, then squash merge.
6. Add one line to `AI_USE_LOG.md`, and a row to `ATTRIBUTIONS.md` for anything new you used.

Limits: at most three builders in flight; no new unit while two of yours wait for acceptance; nothing runs unattended against `main`.

### 6. What you never hand to a session

Parameter values, thresholds, ranges, expected test values, citations, the choice of a data source or a dependency, the wording of a claim, pushing to `main`, deploying. If a session produces one of these, discard it.

## Platform developer (sub-lane L2a)

You own `adapters/`, `api/`, CI and deploy: sub-lane L2a, data and service. The other half of the platform lane, L2b (`decision/`, `engine/rothc/`, `demo/`), belongs to the interface developer. You also decide technical matters for everyone: structure, dependencies, deploy.

### Decide first, because every lane waits for it

| Decision | Notes |
|---|---|
| Allowed dependency list, with version and licence | Include what the stack table does not name: the ASGI server, the container base image, the scan tools, the schema validator and the frontend test runner |
| Python version, Node version, package manager | — |
| Where the Python dependency manifest lives | The repository root belongs to no lane; say who edits it |
| Schema format | JSON Schema files or Pydantic models. Agree with the lead developer |
| CI host and the tool for each of the six checks | Tests, frontend build, contract validation, secret scan, names scan, dependency licences |
| Where the list of forbidden names is kept | **Not in the repository.** In plain text it would itself be the leak; keep it in the CI host's secret storage |
| Whether a check passes or is skipped while `web/` or `contracts/` do not exist yet | — |

### Your Block 0 units

1. Hand-written examples of the contracts you produce: site data (climate; soil and slope). Every number marked illustrative. The decision output example is written by L2b.
2. Backend skeleton with one liveness route and a passing test.
3. CI with all six checks, each shown to fail on a planted case that a person designs.
4. Container definition and deploy configuration. **A person performs the deploy.**

### Inputs only you or a science reviewer can supply

- Deploy target, its account, the public URL, and whether the host keeps files between restarts (the cache is file-based).
- The frontend origin allowed to call the backend. Agree with the interface developer.
- Credentials: only in the host's settings, never in the repository.
- Liveness route path and response; path, method and error format of the route for one rotation.
- For the NASA POWER adapter (science reviewers decide the data questions): endpoint and parameters with units, years of record, how UTC is requested, how the source's fill value becomes "missing with reason", whether IMERG precipitation comes through POWER or directly, a test point that is not a real producer's field with expected values checked by a second person, and whether a recorded response may be committed.

### Seams to agree early

- **Engine entry points** with the lead developer (`contracts/ENTRYPOINTS.md`), before Block 1.
- **Frontend build command and origin** with the interface developer.
- **Contract validation command** that CI runs, with the lead developer.

## Interface developer (lane L3 and sub-lane L2b)

You own `web/` (lane L3) and `decision/`, `engine/rothc/` and `demo/` (sub-lane L2b, decision and carbon). You also decide what is delivered and when. Run each of the two with its own sessions and its own clone, and branch as `l3/<unit>` and `l2/<unit>`.

### Sub-lane L2b: decision and carbon

First units, from section 8 of the blueprint:

1. Block 0: the hand-written example of the decision output, which your own screens consume.
2. Block 1: decision functions on hand-made tables.
3. Block 2: tipping point, measurement priority and measurement input; RothC with common forcings; the thin matrix through the decision.
4. Block 3: RothC by month, year and cycle; the saved case.

Inputs a person supplies: the definitions of the decision tests in `docs/VALIDATION.md`, the test plan with its thresholds, the hand-made tables with their expected outputs, the exact wording of each state, the paired-difference method with its citation, and how a missing cell is treated. The science reviewers decide what is claimed.

Seams: the results table from the lead developer and the engines lane; `CarbonForcing` from L2a; the engine entry points in `contracts/ENTRYPOINTS.md`.

### Lane L3: interface

### Your Block 0 units

1. Frontend skeleton and static deploy. Nothing else in `web/` can start before it merges.
2. All strings in one English file.
3. Shared display of a value: unit, provenance label and source, or "missing" with its reason.
4. Multi-field identity screen on example data.

Units 2 to 4 need the conventions sheet from the lead developer.

### Inputs only you or a science reviewer can supply

| Input | Notes |
|---|---|
| Static hosting target, its account, public URL, base path, and how it handles client-side routes | A person deploys, or the Platform pipeline does. A session never deploys |
| Frontend dependency list | Goes through the platform developer, who records each licence |
| Map base layer | Provider, URL template, attribution text, terms of use and limits for a public demo. A layer that needs a key cannot be used from a public static frontend |
| Wording sheet | Every label, title and button, the disclaimer, the example-data label, the "assumption" mark, the display names of the four provenance labels and the phrasing of a missing value. What the interface claims is decided by the science reviewers |
| Example data | Synthetic field names and geometries written by a person, always shown under a visible example-data label. Never a real producer's field |
| What makes up the "identity" of a field, and which contract carries it | Agree with the lead developer |
| Rotation definition example | You are the producer of this contract. Write it by hand; the engines lane signs it |
| Scope of Block 1 | Whether a field boundary can be drawn, and whether the rotation ribbon is display-only or editable |

### Check before you depend on it

Confirm with the platform developer how each interface library is distributed. If a library works by copying its component source files into the repository, that has to be reconciled with the rule against copying code from other repositories, and attributed.

### Rules that bite in the interface

- No number without its source or an explicit "assumption" mark.
- A missing value is shown as missing, with its reason. Never as zero or blank.
- Example data is labelled as example data on every screen that shows it.
- No user-visible text outside the strings file.
- No generated images, video or voice in the demonstration.
