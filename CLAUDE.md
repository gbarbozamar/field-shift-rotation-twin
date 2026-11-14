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
```

Tests live next to the code they check (`params/test_layout.py`, `validation/test_layout.py`, `api/test_*.py`); `params/` and `validation/` use the standard library only. Docs written before uv existed say `python -m pytest <folder>/`, which still works.

`compose.yaml` syncs `api/` into the container and rebuilds on `pyproject.toml` or `uv.lock` changes. Add a new backend folder (e.g. `adapters/`) to its watch list when it is created.

## Platform decisions (L2a)

- Stack: FastAPI served by uvicorn; Pydantic models are the schema format; httpx, numpy, shapely, pyproj; pytest and ruff. Frontend: Node 22 LTS, npm (`package-lock.json` committed, `npm ci` in CI), Vitest; the rest of the frontend stack is in blueprint §4.
- CI: GitHub Actions running the six checks (tests, frontend build, contract validation, secret scan with gitleaks, names scan, dependency licences with pip-licenses and license-checker). A check whose folder does not exist yet is skipped with a notice. The forbidden-names list lives in a GitHub Actions secret, never in the repository.
- API: `api/main.py` builds the app with `create_app(cors_origins)`. `GET /health` → `{"status": "ok"}` is the liveness route.
- CORS: allowed origins come from the `CORS_ORIGINS` environment variable (comma-separated). Unset or empty means no cross-origin access. Compose sets `http://localhost:5173` (Vite dev server); the production origin is set in the host's settings at deploy.
- Deploy: a static frontend and one backend container, both public without login. The frontend is proposed for GitHub Pages through the platform pipeline: base path `/field-shift-rotation-twin/`, hash routing, built with `npm ci && npm run build` in `web/` into `web/dist/`. The backend host is not chosen yet. Deploys are performed by a person, never a session.
- Not yet agreed with the interface lane: whether API routes live under an `/api` prefix (for the Vite dev proxy), the path, method and error format of the route for one rotation (the CP1 seam), and a compose service serving `web/dist/` once `web/` exists.
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
