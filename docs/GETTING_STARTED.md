# Getting started

For the developers who join a lane. Read this first, then [DEVELOPMENT_BLUEPRINT.md](DEVELOPMENT_BLUEPRINT.md).

To run the tool from a clean clone, with each command and the output it gives, see [WALKTHROUGH.md](WALKTHROUGH.md).

- [Current repository orientation](#current-repository-orientation)
- [All developers](#all-developers)
- [Enzo: platform developer (sub-lane L2a)](#enzo-platform-developer-sub-lane-l2a)
- [Martín: interface developer (lane L3 and sub-lane L2b)](#martín-interface-developer-lane-l3-and-sub-lane-l2b)

Gustavo, the lead developer, owns lanes L0 Core and L1 Engines. Adrian and Leonardo are the science reviewers.

## Current repository orientation

Block 0 bootstrap is complete on `main`: contracts, backend routes, engines, frontend, CI checks, and the initial signed parameter catalogue are in place (see [README.md](../README.md) for current module status and known limits).

### Key entry points

- [docs/WALKTHROUGH.md](WALKTHROUGH.md) — step-by-step clean-clone instructions for installing dependencies, running tests, starting the backend, and exercising the interface.
- [docs/METHODS.md](METHODS.md) — scientific methods, citations, and `DECIDED` / `PROPOSED` / `OPEN` status (holds no parameter values).
- [docs/VALIDATION.md](VALIDATION.md) — validation protocol, recorded test runs, and check statuses (`[E*]`, `[H*]`, `[D*]`).
- [params/records/](../params/records/README.md) — signed parameter catalogue loaded at service start-up, holding `132` signed JSON records (`26` erosion records at the top level, `100` in `water/`, and `6` in `residues/`).
- [contracts/CONVENTIONS.md](../contracts/CONVENTIONS.md) and [contracts/ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md) — shared units, provenance labels, missing-value rules, and engine entry-point signatures.
- [pyproject.toml](../pyproject.toml) and [web/package.json](../web/package.json) — Python (`>=3.12,<3.13`) and frontend (`Node 22` / `npm`) dependency manifests.

### Verified commands

Run from the repository root unless noted:

- `py -3.12 -m pytest` (or `python -m pytest` on POSIX) — run Python tests in a Python 3.12 environment (`pyproject.toml` configures `pythonpath = ["."]`; e.g., `py -3.12 -m pytest contracts/ -q` or `py -3.12 -m pytest validation/ -q`).
- `uv sync` then `uv run pytest` (or `uv run --group dev pytest`) — create/sync `.venv` and run pytest using the `dev` dependency group in `pyproject.toml` (defined under `[dependency-groups]`, not `[project.optional-dependencies]`; if `uv` is not on `PATH`, use `py -3.12 -m uv` or `python -m uv`).
- `cd web && npm ci && npm test` — install frontend dependencies from [web/package-lock.json](../web/package-lock.json) and run the Vitest suite (`vitest run`; `npm run build` builds `dist/`).
- `py -3.12 -m ci.names_scan` (or `uv run python -m ci.names_scan`) — scan git-tracked files for forbidden names when `FORBIDDEN_NAMES` is set (exits `0` with a notice when unset).

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
6. Add one line to [AI_USE_LOG.md](../AI_USE_LOG.md), and a row to [ATTRIBUTIONS.md](../ATTRIBUTIONS.md) for anything new you used.

Limits: at most three builders in flight; no new unit in a lane while two units of that lane wait for acceptance, with L2a and L2b counted separately; nothing runs unattended against `main`.

### 6. What you never hand to a session

Parameter values, thresholds, ranges, expected test values, citations, the choice of a data source or a dependency, the wording of a claim, pushing to `main`, deploying. If a session produces one of these, discard it.

## Enzo: platform developer (sub-lane L2a)

You own `adapters/`, `api/`, CI and deploy: sub-lane L2a, data and service. The other half of the platform lane, L2b (`decision/`, `engine/rothc/`, `demo/`), belongs to Martín. You also decide technical matters for everyone: structure, dependencies, deploy.

### Decide first, because every lane waits for it

| Decision | Notes |
|---|---|
| Allowed dependency list, with version and licence | Include what the stack table does not name: the ASGI server, the container base image, the scan tools, the schema validator and the frontend test runner. **Landed:** recorded in [pyproject.toml](../pyproject.toml), [web/package.json](../web/package.json), [ci/allowed_licences.txt](../ci/allowed_licences.txt), [ci/allowed_frontend_licences.txt](../ci/allowed_frontend_licences.txt), and [ATTRIBUTIONS.md](../ATTRIBUTIONS.md) |
| Python version, Node version, package manager | **Decided:** Python `>=3.12,<3.13` with `uv` ([pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock)); Node 22 with `npm` ([.github/workflows/ci.yml](../.github/workflows/ci.yml), [web/package-lock.json](../web/package-lock.json)) |
| Where the Python dependency manifest lives | The repository root belongs to no lane; say who edits it. **Decided:** root [pyproject.toml](../pyproject.toml) and [uv.lock](../uv.lock), edited only by L2a |
| Schema format | JSON Schema files or Pydantic models. Agree with the lead developer. **Decided:** Pydantic models under [contracts/](../contracts/) |
| CI host and the tool for each of the six checks | Tests, frontend build, contract validation, secret scan, names scan, dependency licences. **Decided:** GitHub Actions ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) running `pytest` + `ruff`, `npm ci && npm test && npm run build`, `pytest contracts/`, `gitleaks`, `ci.names_scan`, and `pip-licenses` + [ci/licences.py](../ci/licences.py) + [ci/frontend_licences.py](../ci/frontend_licences.py) (plus `image-build`) |
| Where the list of forbidden names is kept | **Not in the repository.** In plain text it would itself be the leak; keep it in the CI host's secret storage (`FORBIDDEN_NAMES` GitHub Actions secret, read by [ci/names_scan.py](../ci/names_scan.py)) |
| Whether a check passes or is skipped while `web/` or `contracts/` do not exist yet | Both [web/](../web/) and [contracts/](../contracts/) exist on `main`, so `frontend-build` and `contract-validation` run on every CI run |

### Your Block 0 units

1. Hand-written examples of the contracts you produce: site data (climate; soil and slope). Every number marked illustrative. The decision output example is written by L2b.
2. Backend skeleton with one liveness route and a passing test.
3. CI with all six checks, each shown to fail on a planted case that a person designs.
4. Container definition and deploy configuration. **A person performs the deploy.**

*Status on `main`:* all four Block 0 units have landed (see [contracts/](../contracts/), [api/](../api/), [.github/workflows/ci.yml](../.github/workflows/ci.yml), [Dockerfile](../Dockerfile), and [compose.yaml](../compose.yaml)).

### Inputs only you or a science reviewer can supply

- Deploy target, its account, the public URL, and whether the host keeps files between restarts (the cache is file-based).
- The frontend origin allowed to call the backend. Agree with the interface developer.
- Credentials: only in the host's settings, never in the repository.
- Liveness route path and response; path, method and error format of the route for one rotation.
- For the NASA POWER adapter (science reviewers decide the data questions): endpoint and parameters with units, years of record, how UTC is requested, how the source's fill value becomes "missing with reason", whether IMERG precipitation comes through POWER or directly, a test point that is not a real producer's field with expected values checked by a second person, and whether a recorded response may be committed.

*Status on `main`:* public URLs (`GitHub Pages` and `Railway`), `CORS_ORIGINS`, route paths (`/health`, `POST /api/rotations/run`, and `PROPOSED` `POST /api/decisions/run` and `POST /api/plant/run`), and environment variables are documented in [README.md](../README.md) and [api/README.md](../api/README.md); NASA POWER settings are in [adapters/settings/nasa_power.json](../adapters/settings/nasa_power.json) (`POWER_SETTINGS_FILE`).

### Seams to agree early

- **Engine entry points** with Gustavo ([contracts/ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md)), before Block 1. *(Landed on `main`.)*
- **Frontend build command and origin** with Martín. *(Settled: `npm ci && npm test && npm run build` in [web/](../web/) and `CORS_ORIGINS`.)*
- **Contract validation command** that CI runs, with Gustavo. *(Settled: `pytest contracts/` in [.github/workflows/ci.yml](../.github/workflows/ci.yml).)*

## Martín: interface developer (lane L3 and sub-lane L2b)

You own `web/` (lane L3) and `decision/`, `engine/rothc/` and `demo/` (sub-lane L2b, decision and carbon). You also decide what is delivered and when. Run each of the two with its own sessions and its own clone, and branch as `l3/<unit>` and `l2/<unit>`.

### Sub-lane L2b: decision and carbon

First units, from section 8 of the blueprint:

1. Block 0: the hand-written example of the decision output, which your own screens consume.
2. Block 1: decision functions on hand-made tables.
3. Block 2: tipping point, measurement priority and measurement input; RothC with common forcings; the thin matrix through the decision.
4. Block 3: RothC by month, year and cycle; the saved case.

Inputs a person supplies: the definitions of the decision tests in [docs/VALIDATION.md](VALIDATION.md), the test plan with its thresholds, the hand-made tables with their expected outputs, the exact wording of each state, the paired-difference method with its citation, and how a missing cell is treated. The science reviewers decide what is claimed.

Seams: the results table from the lead developer and the engines lane; `CarbonForcing` from L2a; the engine entry points in [contracts/ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md).

*Status on `main`:* [decision/](../decision/), [engine/rothc/](../engine/rothc/), [demo/](../demo/), and [contracts/ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md) have landed, and [docs/VALIDATION.md](VALIDATION.md) holds the D-entry logic definitions (`OPEN` items and science-reviewer acceptance remain pending; RothC still returns `MISSING_INPUT` because its parameter records and site soil properties are not yet signed in [params/records/](../params/records/README.md)).

### Lane L3: interface

### Your Block 0 units

1. Frontend skeleton and static deploy. Nothing else in `web/` can start before it merges.
2. All strings in one English file.
3. Shared display of a value: unit, provenance label and source, or "missing" with its reason.
4. Multi-field identity screen on example data.

Units 2 to 4 need the conventions sheet from the lead developer.

*Status on `main`:* Block 0 units 1 to 4 ([web/](../web/), [.github/workflows/pages.yml](../.github/workflows/pages.yml)) and [contracts/CONVENTIONS.md](../contracts/CONVENTIONS.md) have landed on `main`.

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

*Status on `main`:* static hosting ([.github/workflows/pages.yml](../.github/workflows/pages.yml)), frontend dependencies ([web/package.json](../web/package.json)), synthetic example data ([web/src/data/](../web/src/data/)), and rotation definition examples ([contracts/rotation_definition/examples/](../contracts/rotation_definition/examples/)) are on `main`; science-reviewer acceptance remains open where marked in [README.md](../README.md) and [docs/VALIDATION.md](VALIDATION.md).

### Check before you depend on it

Confirm with the platform developer how each interface library is distributed. If a library works by copying its component source files into the repository, that has to be reconciled with the rule against copying code from other repositories, and attributed.

### Rules that bite in the interface

- No number without its source or an explicit "assumption" mark.
- A missing value is shown as missing, with its reason. Never as zero or blank.
- Example data is labelled as example data on every screen that shows it.
- No user-visible text outside the strings file.
- No generated images, video or voice in the demonstration.
