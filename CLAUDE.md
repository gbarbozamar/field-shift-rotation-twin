# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Hackathon prototype (NASA Space Apps 2026, "Field Shift") that compares crop rotations for a field against the observed climate record: soil loss, water-deficit exposure and soil-carbon trend, each with uncertainty. When the data cannot separate two options, the answer is "not resolved" plus what to measure first. The product never calls a language model; explanation text comes from deterministic templates.

The specification is `docs/DEVELOPMENT_BLUEPRINT.md` (read it in full before building anything) and `docs/GETTING_STARTED.md`. Who holds which lane is in `README.md`. Folders are created by the first unit that needs them.

## Commands

Python 3.12, managed with uv. One `pyproject.toml` and `uv.lock` at the repository root, edited only by L2a (platform). Run everything from the repository root.

```bash
uv sync                                  # install, including the dev group
uv run pytest                            # all tests
uv run pytest api/test_cors.py::test_preflight_from_allowed_origin   # one test
uv run ruff check api/ && uv run ruff format --check api/            # lint (scope to your lane's folders)
uv run uvicorn api.main:app --reload     # backend on http://localhost:8000
docker compose watch                     # backend in a container; edits to api/ reload it
uv run pip-licenses --with-system --format=json | uv run python -m ci.licences   # licence check
FORBIDDEN_NAMES="$(cat <list>)" uv run python -m ci.names_scan                   # names scan
```

Tests live next to the code they check (`params/test_layout.py`, `validation/test_layout.py`, `api/test_*.py`); `params/` and `validation/` use the standard library only. Docs written before uv existed say `python -m pytest <folder>/`, which still works.

`compose.yaml` syncs `api/` into the container and rebuilds on `pyproject.toml` or `uv.lock` changes. Add a new backend folder (e.g. `adapters/`) to its watch list when it is created.

## Platform decisions (L2a)

- Stack: FastAPI served by uvicorn; Pydantic models are the schema format; httpx, numpy, shapely, pyproj; pytest and ruff. Frontend: Node 22 LTS, npm (`package-lock.json` committed, `npm ci` in CI), Vitest; the rest of the frontend stack is in blueprint §4.
- CI: `.github/workflows/ci.yml` runs seven jobs: the six checks `tests` (all pytest, plus ruff on `api/`, `adapters/`, `ci/`), `frontend-build` (`npm ci && npm run build` in `web/`; fails if `web/package.json` is missing), `contract-validation`, `secret-scan` (gitleaks over the whole history), `names-scan` and `dependency-licences` (Python with `ci/licences.py`, then the frontend with `ci/frontend_licences.py`, which reads `web/package-lock.json`), plus `image-build`, which builds the `Dockerfile`, starts the image with no configuration and waits for `GET /health` to answer `200` (nothing is pushed). `contract-validation` runs `uv run pytest contracts/` (every folder under `contracts/` ships a test that loads its examples into its models).
- `ci/` holds the check scripts and `ci/test_planted_cases.py`, which shows each check failing on a case planted at run time in a temporary folder (the secret-scan cases need docker). Nothing planted is committed. `ci/allowed_licences.txt` is the Python licence allowlist, with licences written exactly as package metadata reports them; `ci/allowed_frontend_licences.txt` is the npm one, SPDX identifiers as the lockfile records them (PROPOSED). A new dependency with another licence fails CI until the platform developer adds it.
- The forbidden-names list lives in the GitHub Actions secret `FORBIDDEN_NAMES` (one name per line), never in the repository. The scan reports file and line, never the name; without the secret it is skipped with a notice.
- API (`api/`, see `api/README.md`): `create_app(cors_origins, *, climate, soil_slope, engines, rotation_validator, settings)` builds the app. `GET /health` → `{"status": "ok"}` stays at the root; every product route lives under `/api`. `POST /api/rotations/run` is synchronous: a valid request always answers `200` with `outcome`, `result`, `modules` and `sources`, and absences are typed with a reason code of `contracts/CONVENTIONS.md` C3.2, never zero. `4xx`/`5xx` use one shape on every route, `{"error": {"code", "message", "details"}}` (`api/errors.py`).
- Interfaces, not implementations: the route imports only `adapters/ports.py` and `api/ports.py`; implementations are passed into `create_app`. `adapters/ports.py` is the seam between `api/` and `adapters/` (`ClimateSource`, `SoilSlopeSource`, `SourceInfo`): change it only with both sides in the same pull request. Add a real implementation by passing it in, never by editing the route.
- Engine runner (`api/engines.py`): `EntryPointEngines` implements `RotationEngines` on the entry points of `contracts/ENTRYPOINTS.md`. `discover_engine_functions()` imports each engine by its exact module and function name (`engine.calendar.build_rotation_calendar`, `engine.erosion.compute_soil_loss`, `engine.water.compute_water_deficit_exposure`); one that does not exist is "not built". When a lane lands an engine under that name it is picked up with no change in `api/`. Order: calendar first, then erosion and water with its result, also for an infeasible calendar; the runner assembles `ResultsPerRotation`, writes carbon rows (`amg`, `rothc`) as missing `NOT_AVAILABLE`, computes nothing scientific, and does not catch what an engine raises (the route answers `500`). Where the results model has no form for an absence (soil loss or water engine not built), `result` is `null` with `result_missing` and the module states.
- The request's `rotation` is loaded into `contracts.rotation_definition.RotationDefinition` by `RotationDefinitionValidator`; an invalid one is `422` `ROTATION_INVALID` and no source or engine is called. Error details never repeat a submitted value. Still stand-ins in `api/standins.py`: the climate source and the soil-and-slope source of the default app (`ExampleSoilSlopeSource` exists in `adapters/` but is not wired: which file is the accepted example is a person's decision).
- Import contract models only as `contracts.<folder>` from the repository root (never `inputs`, `results`): the same class under two names is two classes. Serialise contract models with `model_dump(mode="json")`, never `exclude_none=True`.
- Adapters (`adapters/`, see `adapters/README.md`): `PowerClimateSource(settings, cache, client)` implements `ClimateSource` for NASA POWER. `FileCache` keeps the first response per query (key: SHA-256 of the canonical query) and never overwrites it. A source failure is a result (`unavailable`, `SOURCE_UNAVAILABLE`), never an exception, and is never cached. `PowerSettings` has **no defaults**: parameters, units, community, provenance labels, fill value and reason codes are decisions of people that arrive as configuration. Tests use `httpx.MockTransport` and placeholders; a session never calls the real service.
- Configuration (`api/config.py`, PROPOSED): the running app is `build_app(load_config(os.environ))`. Variables: `CORS_ORIGINS`, `POWER_SETTINGS_FILE` (adapter settings JSON; template `adapters/examples/PLACEHOLDER_power_settings.json`, placeholders only), `CLIMATE_CACHE_DIR` (required with it), `CLIMATE_START_DATE` and `CLIMATE_END_DATE` (`YYYY-MM-DD`, both or neither), `SOIL_SLOPE_EXAMPLE_FILE`. None has a default; blank is unset. Not configured is a typed absence (the stand-ins, no period); configured wrongly raises `ConfigError` naming the variable and the server does not start. `create_app` (in `api/app.py`, re-exported by `api/main.py`) stays the way tests inject fakes.
- CORS: allowed origins come from the `CORS_ORIGINS` environment variable (comma-separated). Unset or empty means no cross-origin access. Compose sets `http://localhost:5173` (Vite dev server); the production origin is set in the host's settings at deploy.
- Deploy: a static frontend and one backend container, both public without login. The frontend: `.github/workflows/pages.yml` publishes `web/dist/` to GitHub Pages on every push to `main` (or by hand, `workflow_dispatch`): base path `/field-shift-rotation-twin/`, hash routing, built with `npm ci && npm run build` in `web/`, with `VITE_API_URL` (a workflow-level value, public, not a secret) set to the backend address. The backend: Railway builds the `Dockerfile` and redeploys on every push to `main`; public address `https://api-production-86e398f8.up.railway.app`. A session never triggers a deploy.
- Not yet agreed or built: the shape of `site` (PROPOSED in `api/rotations.py` as `SiteReference`), the years of climate record requested (no default: without it the climate source is not called), the NASA POWER settings (proposed by lane L0 in #75, for the science reviewers), the point of the series in `SiteClimate` (one pull request with lane L0, model and mapper together), and a compose service serving `web/dist/` once `web/` exists.
- Every library or container image gets a row in `ATTRIBUTIONS.md` (version, URL, licence) when added; only L2a adds dependencies.

## Architecture: lanes, contracts, seams

- **Lanes own folders; never edit another lane's folder.** L0 Core: `contracts/`, `params/`, `engine/erosion/`, `validation/`. L1 Engines: `engine/calendar/`, `engine/water/` (`et0/`, `balance/`), `engine/residues/`, `engine/amg/`. L2a Platform, data and service: `adapters/`, `api/`, CI, deploy, the root Python manifest. L2b Platform, decision and carbon: `decision/`, `engine/rothc/`, `demo/`. L3 Interface: `web/`. Both L2 sub-lanes branch as `l2/<unit>` and count their acceptance limits separately.
- **Contracts first.** Every seam between lanes has a schema plus a hand-written example under `contracts/` (rotation definition, calendar, site data, results, decision output, test plan, saved case, `ResidueLedger`, `CarbonForcing`, `ModelState`, `CarbonBalance`; full table in blueprint §5). Build against the accepted example, not against another lane's unfinished code. Site data and `CarbonForcing` come from L2a; decision output, saved case and the RothC side of the carbon contracts from L2b.
- `contracts/CONVENTIONS.md`: units and direction of each indicator, how uncertainty ranges and missing values (with reason) travel, provenance labels `DECLARED` / `OBSERVED` / `DERIVED` / `SIMULATED`, month and agricultural-year numbering, time zone of daily series.
- `contracts/ENTRYPOINTS.md`: the one public function signature per engine; the API route calls engines only through these.
- `params/` and `validation/` hold record formats and checks only, with placeholder examples; no real values yet.
- Engines are pure functions. Network calls only in `adapters/` (NASA POWER, GPM IMERG, soil and terrain), with the first response cached per case. Thresholds live only in the test plan contract. `demo/` saved cases must open without a backend.

## Rules a session must follow

- **One unit, one branch, one worktree:** `git worktree add ../wt-<unit> -b <lane>/<unit>`, branch names `l0/…`, `l1/…`, `l2/…`, `l3/…`. Never push to `main`, never deploy. Squash-merged PRs only.
- **Never produce** parameter values, thresholds, ranges, expected test values, citations, data-source or dependency choices, or the wording of claims. If one is needed, write `OPEN` or `CITATION NEEDED` and stop; a person supplies it. Never edit expected values in an acceptance test.
- Sessions may propose conventions, contract field lists and test-case designs, marked `PROPOSED`; they take effect only when a person approves the PR (blueprint §3.7).
- Do not add dependencies unless you are working for L2a and the platform developer asked. Do not read or copy code from other repositories.
- A missing value stays missing with its reason; never default to zero or blank. Every displayed number carries its source or an explicit "assumption" mark. Example data is synthetic and labelled as example data on every screen; never use a real producer's field.
- In `web/`, all user-visible text lives in the single English strings file.
- English only everywhere. No secrets, private data, or company/product/personal names in code or data (CI scans for them). No generated images, video or voice.
- A unit is done only with its acceptance test. Validation codes like `[E3]`, `[H2]`, `[D1]` refer to `docs/VALIDATION.md` (written by science reviewers).
- Record every new dataset, library, table or publication in `ATTRIBUTIONS.md` when first used, and add one line per merged unit to `AI_USE_LOG.md`. AI-assisted commits carry a co-author trailer. Commit email must be a non-company address (e.g. GitHub no-reply).
