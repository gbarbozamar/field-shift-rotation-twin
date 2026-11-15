# Walkthrough: from a clean clone to a first answer

What to type, in order, and what you should see: clone, install, run the tests, start the backend without Docker, send the example rotation, read the answer, build and open the interface.

**Checked against commit `3ced36f1bf7a57dbef47c3a60e144c48d2e576e9` of `main`, on 15 November 2026.** Every command below was run, in this order, in a fresh `git clone` of the public repository at that commit, and every output shown is the output seen then. A second fresh clone, made later that day at `2e5caf99086080a36a13d5972b493708258393a9` (which changes only documentation files after `3ced36f`), was taken through this page from top to bottom and gave the same outputs. `main` keeps moving: on a later commit the counts and some texts will differ. A step marked **not run when this page was written** is given as the repository documents it and was not run.

The commands are written for a POSIX shell (bash); the `NAME=value command` form sets a variable for one command. They come from `CLAUDE.md`, `api/README.md`, `web/README.md` and `.github/workflows/ci.yml`.

## What you need

- `git`.
- Python 3.12 (`pyproject.toml` requires `>=3.12,<3.13`) and [uv](https://docs.astral.sh/uv/). CI installs uv 0.12.2.
- Node.js and npm for the interface. CI uses Node 22.
- A network connection for the clone and the two installs (`uv sync`, `npm ci`). No other step that was run needs the network, and none calls the public climate service.
- Docker is **not** needed. The steps that use it are marked as not run.

## 1. Clone

```bash
git clone https://github.com/gbarbozamar/field-shift-rotation-twin.git
cd field-shift-rotation-twin
```

Run everything below from this folder (the repository root) unless a step says `cd web`.

## 2. Install the backend

```bash
uv sync
```

uv creates `.venv` from `uv.lock`, the development tools included, and lists each package it installs, ending with lines such as `+ uvicorn==0.54.0`.

## 3. Run the tests

```bash
uv run pytest
```

Seen at the checked commit, on a machine where the Docker command is installed but Docker itself was not running:

```text
1 failed, 4763 passed, 17 skipped, 7 warnings
```

The one failure is `ci/test_planted_cases.py::test_secret_scan_passes_on_a_clean_folder`. It runs the secret scanner in a Docker container, and with Docker installed but not running the container cannot start. On a machine without the Docker command, that case and its pair are skipped instead (the test says so: "docker is not available on this machine"). Every other test passed. The run took between ten and fifteen minutes.

The contract check that CI runs on its own (check 3 of `.github/workflows/ci.yml`):

```bash
uv run pytest contracts/
```

```text
930 passed, 1 warning
```

## 4. Start the backend (no Docker)

```bash
CORS_ORIGINS=http://localhost:5173 uv run uvicorn api.main:app --reload
```

`CORS_ORIGINS` lets the interface of step 6 (served on port 5173) call this backend (`CLAUDE.md`, "CORS"). Without it the backend allows no cross-origin call. The terminal ends with:

```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

This backend runs with **no climate source and no soil file configured** (configuration A below). Leave it running and use a second terminal.

Check that it answers, with the request CI makes:

```bash
curl --silent --output /dev/null --write-out '%{http_code}' http://localhost:8000/health
```

```text
200
```

The body of `GET /health` is `{"status":"ok"}`. The interactive page of the backend, `http://localhost:8000/docs`, opens and lists the two routes, `GET /health` and `POST /api/rotations/run`.

## 5. Build the interface

In a second terminal, from the repository root:

```bash
cd web
npm ci
npm test
npm run build
```

Seen at the checked commit:

- `npm ci` ends with `found 0 vulnerabilities`;
- `npm test`: `Test Files  14 passed (14)`, `Tests  170 passed (170)`;
- `npm run build` writes `dist/` and ends with `✓ built in` and a time.

## 6. Open the interface and send the example rotation

Still in `web`:

```bash
npm run dev
```

```text
➜  Local:   http://localhost:5173/field-shift-rotation-twin/
```

Open that address (the path `/field-shift-rotation-twin/` is part of it). On the very first load the page can stay blank while the dev server prepares its files; reload it. Then:

1. The first screen, **Case**, shows "Example case · 3 fields" under the label "Example data — synthetic, not a real field". Click **North field** (identifier `example-field-1`), then **Open field**.
2. The **Fields** screen opens. Below the list of fields, press the button **Live data — NASA POWER through the platform route**. It sends the example rotation of the repository (`contracts/rotation_definition/examples/PLACEHOLDER_rotation_definition.json`, copied into `web/src/data/`) to `POST /api/rotations/run` of the backend of step 4, with the point that stands for the field. Despite its label, the button calls only your local backend; whether the backend then asks the climate service depends on its configuration.
3. Under the button you see the answer:

```text
Illustrative rotation

no_result

Illustrative rotation: missing input: input not available: climate (site data: climate); soil_slope (site data: soil and slope)
```

Everything else on the Fields screen (Site data, Rotation timeline, Two clocks, Results, Decision) is **example data written by hand**, labelled "Example data — synthetic, not a real field" on screen. It is not the answer of your backend; only the lines under the button are.

## 7. Read the answer

The backend answered HTTP `200` with this JSON (the browser's network panel shows it). The parts that matter:

| Field | Value seen |
|---|---|
| `outcome` | `no_result` |
| `result` | `null` |
| `result_missing` | reason `MISSING_INPUT`, detail "input not available: climate (site data: climate); soil_slope (site data: soil and slope)" |
| `calendar` | the rotation laid out: three components, start month 7, `feasible: true` |
| `sources` | climate `climate_not_connected`, `unavailable`, `NOT_AVAILABLE`, "the climate record period is not configured"; soil and slope `soil_slope_not_loaded`, `unavailable`, `NOT_AVAILABLE`, "no soil and slope source is loaded yet" |
| `scenarios` | one item, `phase_1`, first agricultural year 2027, with the same answer |

The three indicators and their modules:

| Indicator | Module | State and reason seen |
|---|---|---|
| Soil loss | `erosion` | `not_available`, `MISSING_INPUT` (climate and soil absent) |
| Water-deficit exposure | `water` | `not_available`, `MISSING_INPUT` (climate and soil absent) |
| Soil-carbon trend | `residues`, `amg` | `not_available`, `MISSING_INPUT` (climate and soil absent) |
| Soil-carbon trend | `rothc` | `not_available`, `NOT_AVAILABLE`, "the runner does not call this engine yet: engine.rothc.run_rothc" |

No indicator carries a number: each is missing with its reason, never zero. The `calendar` module is `available`.

## 8. The three configurations

The backend reads its configuration from environment variables at start-up (`CLAUDE.md`, "Configuration"; table in `api/README.md`). None has a default. Stop the backend of step 4 (Ctrl+C) before starting it again with another configuration.

### A. Nothing configured (step 4)

No climate source, no soil file. The answer is the one of step 7: `no_result`, climate and soil both missing. This is what the backend gives anywhere, without network.

### B. The demonstration soil file, no climate source

```bash
CORS_ORIGINS=http://localhost:5173 SOIL_SLOPE_EXAMPLE_FILE=data/demo/la_estanzuela_soil_slope.json uv run uvicorn api.main:app --reload
```

`SOIL_SLOPE_EXAMPLE_FILE` serves that soil-and-slope file for any field (`CLAUDE.md`). Press the button of step 6 again. Seen: HTTP `200` and

```text
Illustrative rotation: missing input: input not available: climate (site data: climate)
```

The soil source is now listed with state `example`; the climate is still `climate_not_connected`, `NOT_AVAILABLE`. Without a climate record no indicator can be computed, so every module except `calendar` keeps the states of step 7, now naming only the climate.

### C. The climate source and the demonstration soil file switched on: not run when this page was written

This is the configuration that computes the indicators. From `api/README.md`, "Running locally with settings", with the period of D29 (2001-01-01 to 2024-12-31) and the demonstration soil file:

```bash
POWER_SETTINGS_FILE=adapters/settings/nasa_power.json \
CLIMATE_CACHE_DIR=<a folder for the cache, outside git> \
CLIMATE_START_DATE=2001-01-01 CLIMATE_END_DATE=2024-12-31 \
SOIL_SLOPE_EXAMPLE_FILE=data/demo/la_estanzuela_soil_slope.json \
uv run uvicorn api.main:app --reload
```

Add `CORS_ORIGINS=http://localhost:5173` to use it from the interface. **It needs the network:** on the first request of a place it calls the public NASA POWER service, then keeps the answer in the cache folder. **Not run when this page was written:** a session of this project never calls the public climate service (`CLAUDE.md`), so its answer is not shown here and no number of it was seen. Without the network, `CLAUDE.md` says a failure of the climate source is a result (`unavailable`, `SOURCE_UNAVAILABLE`), never an error. That case was not run either.

What the repository does hold is one real response of the climate service, recorded on 14 November 2026 and committed under decisions D17 and D32 of issue #77: `docs/evidence/nasa-power-2026-11-14/` (`request.txt`, `response.json`, and a `README.md` that explains them). It is the raw answer of the service for ten days at a made-up point in the ocean (longitude -50, latitude -35), with the units, fill value and time standard the service reports. It is **not** an answer of this backend, and it carries no soil-loss figure.

The soil-loss figure of the demonstration is not on this page as a result of a run. Decision D148 of issue #77 sets it as "the declared-`C` figure (D125, 2.365 t ha-1 yr-1 at La Estanzuela)", shown with this label, verbatim:

> based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)

**Not seen in the runs of this page.** D158 adds that with the declared `C` the figure is the same for both rotations of D128: "in the demonstration, erosion does not separate the rotations". The check against the measured plots is the entry "EP1: plausibility against the La Estanzuela runoff plots (2017–2019)" of `docs/VALIDATION.md`.

### The whole app with Docker: not run when this page was written

`CLAUDE.md` documents `docker compose watch`: the backend on port 8000 and the interface on `http://localhost:5173/field-shift-rotation-twin/`, both reloading on edits. That stack has the real climate source switched on. To start it without the climate service, `CLAUDE.md` gives:

```bash
POWER_SETTINGS_FILE= CLIMATE_START_DATE= CLIMATE_END_DATE= docker compose up
```

**Not run when this page was written:** Docker was not used.

## 9. The deployed service

The interface is published at `https://gbarbozamar.github.io/field-shift-rotation-twin/`; the public address of the backend is in `CLAUDE.md`, "Deploy". A plain `GET` of each answered `200` when this page was written, and `GET /health` of the backend answered `{"status":"ok"}`. No rotation was sent to the deployed service from this page.

## Limits of the answer, at the checked commit

- **Without a climate record nothing is computed.** In configurations A and B every indicator is missing with `MISSING_INPUT`; the answer is `no_result`.
- **RothC is not called by the runner** at this commit: its rows and its module say "the runner does not call this engine yet: engine.rothc.run_rothc", whatever the configuration.
- **The soil-loss figure, when it appears, carries the label of D148** quoted above, and it is the same for both rotations of D128 (D158).
- **Example data is example data.** The fields, the rotation and most of the Fields screen are synthetic, and the screen labels them so. The demonstration soil-and-slope file is marked `example_data: true`, and the backend refuses to start with one that is not (`api/README.md`).
