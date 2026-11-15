# api/ — backend routes (lane L2 Platform)

FastAPI application. Run with `uv run uvicorn api.main:app --reload` from the
repository root; tests with `uv run pytest api/`.

Everything this unit designed is marked **PROPOSED** (blueprint section 3.7)
and takes effect only when a person approves the pull request. Questions a
person has to answer are marked **OPEN**. What a person has decided is listed
under [Decided](#decided), with its decision number of issue #77.

## Routes

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness. Unchanged, at the root |
| `POST /api/rotations/run` | One rotation for one field, end to end. Synchronous, JSON in and JSON out |
| `POST /api/decisions/run` | Two rotations of one field and the decision output of the pair (#268). Synchronous, JSON in and JSON out. **PROPOSED** |
| `POST /api/plant/run` | "What should I plant?": one field, three to five rotations, a `PlantAnswer` (`contracts/plant_answer/`). Synchronous. **PROPOSED** (`api/plant.py`) |

Every product route lives under `/api`.

## `POST /api/rotations/run`

Request body (`api/rotations.py`, unknown fields are errors):

```json
{
  "site": { "case_id": "...", "field_id": "...", "latitude": 0, "longitude": 0 },
  "rotation": { "...": "one item of the Rotation definition contract, unchanged" }
}
```

- `site` is `SiteReference`, **PROPOSED**: non-empty `case_id` and `field_id`,
  `latitude` in −90..90, `longitude` in −180..180. It is the only place that
  knows the shape of `site`.
- `rotation` must be a JSON object. Its contents are checked by the
  `RotationValidator`; the default one (`api/rotation_validator.py`) loads it
  into `contracts.rotation_definition.RotationDefinition`.
- No options, no custom headers, no query parameters.

What the route does, in order: validate the body; ask the `RotationValidator`;
get the climate (only when a record period is configured); get soil and
slope; run the engines; copy everything into the envelope. It caches nothing,
never builds a number and never changes `result` or `calendar`.

A valid request always answers `200`, also when nothing could be computed:

```json
{
  "outcome": "complete | partial | no_result",
  "calendar": null,
  "result": null,
  "result_missing": { "reason": "NOT_AVAILABLE", "detail": "..." },
  "modules": [ { "id": "...", "state": "not_available", "reason": "NOT_AVAILABLE", "detail": "..." } ],
  "sources": [ { "id": "...", "contract": "site_data_climate", "state": "unavailable",
                 "retrieved_at": null, "time_zone": null, "request": null,
                 "attribution": null, "missing_reason": "NOT_AVAILABLE", "detail": "..." } ]
}
```

- `sources` has one entry per source consulted, climate first, then soil and
  slope, copied from the `SourceInfo` each interface returned.
  `retrieved_at` is UTC, `YYYY-MM-DDTHH:MM:SSZ`; a `retrieved_at` without a
  time zone is treated as a defect.
- `modules` comes from the engines unchanged. `reason` is required unless
  `state` is `available`.
- `calendar` and `result` are the contract models `RotationCalendar` and
  `ResultsPerRotation`, serialised with `model_dump(mode="json")`, **never**
  with `exclude_none=True` (such a document does not load back, issue 18). A
  test loads the `result` of a response back into `ResultsPerRotation`.
- Example data is marked next to the result, not inside it (decision Q16):
  a source that is the accepted contract example has `sources[].state ==
  "example"`.
- The soil-table source (`SOIL_TABLE_FILES`, `SOIL_GROUPS_FILE`) reports
  `soil_tables` in `sources`: `example` when any of its files says
  `example_data: true`, otherwise `fresh` with `retrieved_at` (the files are
  read during the call); `request` holds `case_id`, `field_id` and, once
  found, the declared `soil_group`; `attribution` joins the `source` of each
  table that lists the group. An undeclared field is `unavailable` /
  `NOT_DECLARED`, a soil group no table lists `unavailable` / `NO_COVERAGE`;
  a group only some tables list is served with a `detail` saying how many
  tables do not list it; a file that is absent or
  malformed is `unavailable` / `NOT_AVAILABLE` (adapters/README.md,
  PROPOSED).
- `result_missing` is non-null exactly when `result` is null (**PROPOSED**:
  the key is always present, `null` when there is a result).
- `outcome` (`derive_outcome`, **PROPOSED**), from what `EnginesResult`
  carries (`values_present`, `values_missing`), without reading the result:
  - `no_result`: no result, **or** no value in it is present (an infeasible
    calendar ends here, as decided in issue 18);
  - `complete`: no value missing, every module `available`, no source
    `unavailable`;
  - `partial`: otherwise.

  While no carbon engine is built, `soil_carbon_trend` is always missing, so
  `complete` is **not reachable yet**. A part in the not-built form counts as
  one missing value (see "Counting" below), so with the calendar built, the
  inputs present and no other engine built there is a result with no present
  value: `no_result`. With one engine built that returns a present value:
  `partial`. The rule of the route is unchanged for this.
- An interface answer that breaks these rules (a module without a reason, an
  unavailable source without `missing_reason`, a result together with a
  reason for its absence) is a defect and answers `500`.
- `scenarios` (**PROPOSED**, D109): one item per phase of the rotation, in
  order, each `{scenario_id, first_ag_year, outcome, calendar, result,
  result_missing, modules}` (see "The phases of a rotation" below). The
  top-level `outcome`, `calendar`, `result`, `result_missing` and `modules`
  are those of `phase_1` (the calendar unchanged) and equal the first item;
  `sources` is written once, at the top, because every phase has the same
  inputs. There is always at least one item. Every non-null `result` loads
  into `ResultsPerRotation`.

## `POST /api/decisions/run` (PROPOSED, unit `l2/decision-route`)

The route issue #268 waits for: it serves a decision output document. Shape
from option 1 of the proposal the lead developer chose on 15 November 2026
(the decision on issue #77 that records it is cited in the pull request). The
interface developer accepts or corrects it as consumer. Code:
`api/decisions.py`, `api/results_table.py`, `api/decision_layer.py`.

Request body (unknown fields are errors):

```json
{
  "site": { "case_id": "...", "field_id": "...", "latitude": 0, "longitude": 0 },
  "rotations": [
    { "...": "one item of the Rotation definition contract, unchanged" },
    { "...": "a second item, same case_id and field_id, another rotation_id" }
  ]
}
```

- `site` is the `SiteReference` of `POST /api/rotations/run`.
- `rotations` holds **exactly two** items (PROPOSED: one pair). No limit, no
  tolerance of "equal" and no sweep are taken.

What the route does, in order: each rotation through the `RotationValidator`;
the identifiers checked (below); the climate and the soil and slope asked for
**once**, for the site; each rotation run through the same `RotationEngines`
as `POST /api/rotations/run`, on those same inputs; the results table built
from the runs; the decision layer asked for the document.

A valid request always answers `200`:

```json
{
  "decision": { "...": "DecisionOutput of contracts/decision_output/, every null kept" },
  "decision_missing": null,
  "scenarios": [
    { "scenario_id": "phase_1+phase_2",
      "phases": [ { "rotation_id": "...", "phase": "phase_1" },
                  { "rotation_id": "...", "phase": "phase_2" } ] }
  ],
  "rotations": [
    { "rotation_id": "...", "outcome": "partial", "result_missing": null,
      "modules": [ "... as in POST /api/rotations/run" ],
      "phases": [ { "scenario_id": "phase_1", "first_ag_year": 0, "outcome": "partial", "result_missing": null } ] }
  ],
  "sources": [ "... as in POST /api/rotations/run, written once" ]
}
```

- `decision` is the `DecisionOutput` of `contracts/decision_output/`,
  serialised with `model_dump(mode="json")`, every null kept, never
  `exclude_none`. `decision_missing` is non-null exactly when `decision` is
  null (the rule of `result` and `result_missing`).
- `rotations`: one item per rotation of the request, in order: the top-level
  `outcome`, `result_missing` and `modules` of its run (those of `phase_1`,
  as `POST /api/rotations/run` gives them) and how each phase ended. The
  calendar and the result are not repeated: that route serves them, and they
  weigh several MB per phase.
- `scenarios`: the legend of the scenarios of the results table, and so of
  the decision; empty when no table was built.
- `example_data` of the document is true when either rotation definition,
  the climate or the soil and slope says `example_data: true`: the mark each
  input carries itself, not the `state` of its source, as
  `api/carbon_forcing.py` marks the forcing.

**The results table (`api/results_table.py`; Q15 (b) of
`contracts/ENTRYPOINTS.md`, PROPOSED).** Built by the platform from the runs,
copying each value unchanged (indicator, direction, value, unit, range or
`range_missing`, `missing`, provenance, source, assumption mark): annual soil
loss per agricultural year (no monthly rows), water on its own time basis,
the soil carbon trend per rotation with its carbon model and computation.
Nothing is computed, converted, filled or left out.

- **Pairing the phases (D109, D132).** A one-year rotation has `phase_1`; a
  two-year rotation has `phase_1` and `phase_2`; every rotation of a table
  has the same cells, `scenario_id` included. **Every combination of one
  phase of each rotation is one scenario**, named by its phases in the order
  of the request joined by `+` (`phase_1+phase_2`). A pair of rotations of N
  and M phases has N × M scenarios. The rule is D172 of issue #77, which
  leaves the form of the name to this unit: PROPOSED here.
- **No table**, and so `decision` null with `decision_missing`, when: a phase
  of a rotation has no result (its reason is copied); a part is in the
  not-built form of D12 (`NOT_AVAILABLE`: `ResultsTable` has no form for it,
  `contracts/results/README.md` question 14); the runs of one scenario do not
  hold the same cells (`NOT_COMPUTABLE`). The detail names the rotation by its
  position in the request (`rotation 2 of the request`), never by an
  identifier the request carried.

**The decision layer (`api/decision_layer.py`, PROPOSED).** The producer of
the document is sub-lane L2b (`decision/`, `contracts/decision_output/README.md`).
The route depends on the interface `DecisionLayer` (in `api/ports.py`, with
the other interfaces), never on `decision/` itself. The default
implementation finds one function **by name**, as the runner finds an engine
(`import_named`, the rule of `_import_function`):

    decision.output.assemble_decision_output(table: ResultsTable, *, example_data: bool) -> DecisionOutput

Module path, name and signature are PROPOSED, for the interface developer to
accept or rename (one constant each). The default, `DiscoveredDecisionLayer`,
looks it up **on each request, never when the app starts**
(`create_app(..., decision_layer=None)`; tests inject their own): every merge
to `main` redeploys the service before CI ends, so nothing of `decision/` (nor
`contracts.decision_output`) is imported at start-up. Building the app adds
only `api.decisions`, `api.results_table` and `api.decision_layer` to what it
imports.

- The function is in `decision/output.py` (PROPOSED, unit
  `l2/decision-assembly-d198`, brief #315), so the route serves a document.
  Not found (a tree without it): `200`, `decision` null, `decision_missing`
  `NOT_AVAILABLE` naming the function.
- What it returns is checked by the route itself (`check_document`), whatever
  the implementation: a `DecisionOutput`, validated again, of the case and
  field of the table, with its rotations and scenarios, and the example mark
  it was given.
- **A decision layer that fails** (its module exists and does not import,
  the function raises, or what it returns does not pass the check) is a
  defect, as an engine that raises: `500` `INTERNAL_ERROR`, no error text in
  the answer, the error in the log. Only "not built" (the module or the
  function absent) is `NOT_AVAILABLE`. Start-up and the other routes are
  never affected, since nothing of it is imported before a request. PROPOSED.

**Invalid requests (`422`; nothing is called):**

| Case | `error.code` | `details[].path`, `code` |
|---|---|---|
| Not exactly two rotations; an item that is not an object; an unknown field (except one named `rotation`, which `api/errors.py` classes as `ROTATION_INVALID`) | `INVALID_REQUEST` | as validation gives them |
| Every validation error inside `site` | `SITE_INVALID` | `site...` |
| A problem the `RotationValidator` reports | `ROTATION_INVALID` | `rotations.<index>.<path>`, its code |
| A rotation whose `case_id` or `field_id` is not that of `site` | `ROTATION_INVALID` | `rotations.<index>.case_id` or `.field_id`, `not_the_site` (PROPOSED) |
| A `rotation_id` given twice | `ROTATION_INVALID` | `rotations.<index>.rotation_id` of the second, `repeated` (PROPOSED) |
| A rotation whose `ag_year_start.month` is not that of the first rotation (D255 of #77: a pair shares one start month) | `ROTATION_INVALID` | `rotations.<index>.ag_year_start.month`, `not_the_start_month` (PROPOSED) |

A message names the field, never the value the request carried.

**Defects (`500` `INTERNAL_ERROR`, CORS headers kept, no exception text):** an
engine that raises, an envelope that breaks the rules of
`POST /api/rotations/run`, a run whose result carries other identifiers than
its request. The decision layer is not among them (above).

**Cost.** Two runs, each `N` runs of EP1, EP3, EP4 and EP5 (one per phase),
sequential, plus the table and the decision; the climate is asked for once.
Measured in process on a laptop with other work running (not on the host):
3 to 10 s per phase. Whether a request fits the host's timeout is not
measured (OPEN below).

**OPEN for this route:**

- More than two rotations in one document: the decision output contract has
  one set of scenarios for all its rotations, so each pair would be read over
  the phases of the others too. Not decided.
- Limits, a tolerance of "equal" and the sweep of D3 in the request (they
  need the test plan contract and person-declared values).
- Saved cases and run identifiers (#251): the route stores nothing.
- The time of one request on the host, and its request timeout.
- Whether `ResultsTable` gains a wholly missing form (question 14 of
  `contracts/results/README.md`): until then a part not built gives no
  decision.

## `POST /api/plant/run` (PROPOSED, unit `l2/plant-route`)

The steps are in the docstring of `api/plant.py`. `api/app.py` finds
`api.plant.run_plant` by name on each request; absent, the route answers
`answer: null` with `answer_missing` `NOT_AVAILABLE`. Two points of the
platform review:

- **Heavier rain is off unless a person switches it on** (S-032, decision
  R25; review of #427 and point 3 of the review of #310). How rain enters
  erosion and how its uncertainty scales is a science choice, to be proposed
  to the erosion lane as an option of EP1; until it is one, `api/` never
  applies it silently. `create_app(..., rain_stress_switched_on=False)` is the
  default; `api.config` sets it from `RAIN_STRESS_TEST=on`. Below
  `create_app` (`run_plant`, `make_plant_router`, `stressed_run`) the switch
  is a required keyword. Switched off, a declared `rain_stress_factor` is
  echoed `applied: false` with `api.plant.NOT_SWITCHED_ON` in its detail (a
  sentence that names no server variable), the engines run unchanged and
  `engines_factory` (given or the default) is never called. No factor gives no
  echo; a missing factor gives its missing echo, switched on or off. Switched
  on, the engines are rebuilt on the catalogue whose erosivity
  `api/rain_stress.py` scales, as `stressed_run` describes.
- **The source row of the ONI record** has state `fresh`: the record is a
  file a person configured (`KINDS_OF_YEAR_RECORD_FILE`), read once at
  start-up, never fetched and no stored response reused, so not `cached`.
  `fresh` is the state the API already gives a file a person supplies
  (`adapters.soil_tables`); `retrieved_at` is null (no read time is kept).
  The record format has no example-data mark, so `example` is never inferred
  for it. No record configured: the row is `unavailable`, `NOT_AVAILABLE`.
  The example answer and OPEN 5 of `contracts/plant_answer/README.md` (lane
  L0) still write `cached`.

## Errors (`api/errors.py`)

One shape for every non-2xx response on every route:

```json
{ "error": { "code": "INVALID_REQUEST", "message": "<fixed English template>",
             "details": [ { "path": "rotation.x", "code": "...", "message": "..." } ] } }
```

| Case | Status | `error.code` |
|---|---|---|
| Body is not parseable JSON | 400 | `MALFORMED_JSON` |
| Envelope wrong: missing or unknown field, wrong type, wrong content type | 422 | `INVALID_REQUEST` |
| Every validation error lies inside `site` | 422 | `SITE_INVALID` |
| `rotation` is not an object, or the `RotationValidator` reports problems | 422 | `ROTATION_INVALID` |
| An interface or the route raises | 500 | `INTERNAL_ERROR` |
| Unknown route | 404 | `NOT_FOUND` |
| Wrong method (`Allow` header kept) | 405 | `METHOD_NOT_ALLOWED` |

- `message` is developer text; the interface shows its own strings keyed by
  `code`. The message templates are **PROPOSED**.
- The default `RotationValidator` gives one detail per validation error of
  `RotationDefinition`: `path` dotted and relative to the rotation (empty for
  an error of the whole object, which the route reports at `rotation`),
  `code` the error type, `message` the error text. Input, context and URL are
  never copied. A rotation that does not load answers `422`
  `ROTATION_INVALID` and no source or engine is called.
- `details[].path` is the dotted location without the leading `body`;
  `code` is the validation type; `message` its text. The submitted input is
  never echoed (`input`, `ctx` and `url` are dropped); for malformed JSON no
  details are sent.
- **PROPOSED** classification rule: an error lies inside `site` or `rotation`
  when its location starts with that field and it is not that field being
  missing (a missing field is an envelope error). Errors in both, or in the
  envelope, give `INVALID_REQUEST`.
- **PROPOSED**: a `RotationValidator` gives paths relative to the rotation
  (`components.0.crop`); the route prefixes `rotation.`.
- **PROPOSED**: any other `HTTPException` keeps its status; 400 maps to
  `MALFORMED_JSON`, other 4xx to `INVALID_REQUEST`, 5xx to `INTERNAL_ERROR`.
- Unexpected exceptions are caught inside the route, logged with `logging`,
  and answered `500` without exception text, so the CORS headers are kept.

## Configuration (`api/config.py`)

The app a server runs (`api.main:app`) is assembled from environment
variables: `app = build_app(load_config(os.environ))`. When the people who own
the decisions write the settings, the real data flows with no code change.

- `load_config(environ) -> AppConfig` reads only the mapping it is given,
  never `os.environ` itself. An empty or blank value counts as unset; values
  are stripped of surrounding whitespace.
- `build_app(config, *, client_factory=None) -> FastAPI` builds the sources
  the configuration names and calls `create_app` (now in `api/app.py`,
  re-exported by `api/main.py` with `parse_origins`). Engines and the rotation
  validator are the defaults of `create_app`. `create_app` keeps its signature
  and stays the way tests inject fakes.

**No variable has a default.** A piece that is **not configured** is a typed
absence (the app of today). A piece that is **configured wrongly** is a deploy
defect: `ConfigError`, whose message names the variable and what is wrong, so
the server refuses to start. A message never contains the content of a file,
only its path and the reason.

| Variable | Meaning | When unset |
|---|---|---|
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API from a browser | No cross-origin access (unchanged) |
| `POWER_SETTINGS_FILE` | Path of a JSON file with the NASA POWER adapter settings, loaded with `PowerSettings.from_mapping`. The template is `adapters/examples/PLACEHOLDER_power_settings.json` (placeholders only, never a usable configuration) | The climate source is the stand-in: `unavailable` / `NOT_AVAILABLE` |
| `CLIMATE_CACHE_DIR` | Folder of the `FileCache` of climate responses. Not created or checked at start-up beyond being non-empty: `FileCache` creates it on first write | Required when `POWER_SETTINGS_FILE` is set; alone it is ignored |
| `CLIMATE_START_DATE`, `CLIMATE_END_DATE` | The climate record period (`RunSettings`), `YYYY-MM-DD`, inclusive | No period: the climate source is not called (unchanged) |
| `SOIL_SLOPE_EXAMPLE_FILE` | Path of the accepted soil-and-slope contract example, served by `ExampleSoilSlopeSource` with state `example`, for any field: under the `case_id` and `field_id` of the request (D38) | The soil-and-slope source is the stand-in |
| `SOIL_TABLE_FILES` | Comma-separated paths of soil tables (soil properties by soil group, D48, D49), in order; served with `SOIL_GROUPS_FILE` by `adapters.soil_tables.SoilTableSource`. Template: `adapters/examples/PLACEHOLDER_soil_table.json` | Required with `SOIL_GROUPS_FILE`; together unset, no soil-table source |
| `SOIL_GROUPS_FILE` | Path of the soil-groups declaration: the soil group of each field of a case (`DECLARED`). Template: `adapters/examples/PLACEHOLDER_soil_groups.json` | Required with `SOIL_TABLE_FILES` |
| `KINDS_OF_YEAR_RECORD_FILE` | PROPOSED. Path of the ONI record `POST /api/plant/run` classifies the kinds of year on; read once at start-up (a JSON object with an `id` and `seasons`) and passed to `create_app`. `compose.yaml` passes it through from the host shell, blank by default, so it is unset unless a person sets it (PROPOSED, R35) | No record: every kind of year of a plant answer is missing `NOT_AVAILABLE` |
| `RAIN_STRESS_TEST` | PROPOSED (S-032, R25). Exactly `on` (after stripping spaces) switches the heavier-rain stress test of `POST /api/plant/run` on; any other non-blank value is a `ConfigError` naming the variable (never repeating the value). `compose.yaml` passes it through from the host shell, blank by default, so it is unset (off) unless a person sets it (PROPOSED, R35) | Off: a declared rain-stress factor is echoed `applied: false` with `NOT_SWITCHED_ON`, and the engines run unchanged |

Relative paths are resolved against the working directory of the server.

With `POWER_SETTINGS_FILE`, the climate source is
`PowerClimateSource(settings, FileCache(CLIMATE_CACHE_DIR), client)`. The
`httpx.Client` is made by `client_factory(settings)` (default: a plain
`httpx.Client` with the configured `timeout_seconds`) and closed when the app
shuts down (the FastAPI lifespan). Tests pass a factory that returns a client
on `httpx.MockTransport`.

### Start-up failures (`ConfigError`)

- `POWER_SETTINGS_FILE` set and the file does not exist, cannot be read as
  UTF-8 text, is not JSON (line and column given), or is rejected by
  `PowerSettings.from_mapping` (its message is passed on).
- `POWER_SETTINGS_FILE` set without `CLIMATE_CACHE_DIR`.
- Only one of `CLIMATE_START_DATE` and `CLIMATE_END_DATE` set; a date that is
  not `YYYY-MM-DD` or not a calendar date; the start after the end. A period
  of one day is accepted.
- `SOIL_SLOPE_EXAMPLE_FILE` set and the file does not exist, cannot be read,
  does not load into `SiteSoilSlope`, or has `example_data` false. This is an
  extra, earlier guard: `ExampleSoilSlopeSource` itself still answers
  `unavailable` for these when used directly.
- Only one of `SOIL_TABLE_FILES` and `SOIL_GROUPS_FILE` set; both set together
  with `SOIL_SLOPE_EXAMPLE_FILE` (one soil-and-slope source at a time); an
  empty item in `SOIL_TABLE_FILES` or one file named twice; a soil file that
  does not exist, cannot be read, is not JSON or is rejected by its loader
  (`load_soil_table`, `load_soil_groups`; the message names the variable, the
  path and the position of the problem, never the content); two tables that
  give the same quantity for one soil group. The source still answers
  `unavailable` for a file that breaks after start-up. PROPOSED.
- `KINDS_OF_YEAR_RECORD_FILE` set and the file does not exist, cannot be
  read, is not JSON, or is not a JSON object with an `id` and `seasons`.
  PROPOSED.
- `RAIN_STRESS_TEST` set to anything but `on` (after stripping spaces; `ON`,
  `yes`, `true` and `1` included); the message names the variable and never
  repeats the value. PROPOSED (S-032).
- The parameter catalogue in `params/records/` has any problem of
  `load_folder` or `check_catalogue` (not a variable; see "The parameter
  catalogue" under the engine runner). An empty catalogue starts.

A message writes the path plainly between single quotes (`'<path>'`), never
as a Python `repr`, which doubles every backslash of a Windows path (issue
#18). `api/test_config.py` checks it with a made-up path written with
backslashes, on any system.

### Variables of the deployed service

For a person to set on the host. The app reads them at start-up; a wrong value makes it refuse to start.

| Variable | Value | Where it comes from |
|---|---|---|
| `POWER_SETTINGS_FILE` | `adapters/settings/nasa_power.json` (relative to the working directory of the container, `/app`) | The settings file of the adapter (D20, D37) |
| `CLIMATE_CACHE_DIR` | The path of the persistent volume of the host | D42. Without a volume the cache is lost at every deploy and the first request of a case fetches again |
| `CLIMATE_START_DATE` | `2001-01-01` | D29 |
| `CLIMATE_END_DATE` | `2024-12-31` | D29 |
| `SOIL_SLOPE_EXAMPLE_FILE` | The accepted soil-and-slope example, once a person supplies its values | D38; the PLACEHOLDER file is for testing the pipeline only (#77) |
| `SOIL_TABLE_FILES`, `SOIL_GROUPS_FILE` | Unset. Set instead of `SOIL_SLOPE_EXAMPLE_FILE` once a person supplies the soil tables (`K` of S9, D48; available water, D49, if its licence allows) and the soil groups of the demonstration fields | D48, D49; OPEN in adapters/README.md |
| `CORS_ORIGINS` | `https://gbarbozamar.github.io` | D42 |
| `KINDS_OF_YEAR_RECORD_FILE` | Unset until a person signs the ONI record (D34, D66) | PROPOSED |
| `RAIN_STRESS_TEST` | Unset (off) unless a person decides to switch the heavier-rain stress test on; then `on` | S-032 (PROPOSED) |

With the first four set, the climate source is the NASA POWER adapter: the first request of a case fetches from the service and stores the response; later requests reuse it.

### Running locally with settings

```bash
POWER_SETTINGS_FILE=adapters/settings/nasa_power.json \
CLIMATE_CACHE_DIR=<a folder for the cache, outside git> \
CLIMATE_START_DATE=<first day> CLIMATE_END_DATE=<last day> \
SOIL_SLOPE_EXAMPLE_FILE=<the soil-and-slope example> \
uv run uvicorn api.main:app --reload
```

**This calls the real service** on the first request of a case. A session never does that; a person does. For a test without the network, copy `adapters/examples/PLACEHOLDER_power_settings.json`: started with it unchanged, the server starts but every climate request fails (`https://power.invalid/` never resolves). `compose.yaml` lists the variables as comments; none is switched on.

## Interfaces and their implementations

The route depends only on these interfaces. `create_app(cors_origins, *,
climate=None, soil_slope=None, engines=None, rotation_validator=None,
settings=None, parameters=None, decision_layer=None)` receives the
implementations; `None` means the default.

| Interface | Defined in | Default | Default behaviour | Still to come |
|---|---|---|---|---|
| `ClimateSource` | `adapters/ports.py` | Stand-in `ClimateUnavailable` | `data=None`, `unavailable`, `NOT_AVAILABLE` | The NASA POWER adapter (`adapters/power.py`) is wired by `POWER_SETTINGS_FILE` (see Configuration); its settings are OPEN in `adapters/README.md` |
| `SoilSlopeSource` | `adapters/ports.py` (re-exported by `api/ports.py`) | Stand-in `SoilSlopeNotLoaded` | `data=None`, `unavailable`, `NOT_AVAILABLE` | `adapters.example_soil_slope.ExampleSoilSlopeSource(path)` is wired by `SOIL_SLOPE_EXAMPLE_FILE` and serves the example for any field (D38); `adapters.soil_tables.SoilTableSource(table_paths, groups_path)` is wired by `SOIL_TABLE_FILES` and `SOIL_GROUPS_FILE` (soil by soil group, D48, D49; slope not built). Then slope from an elevation model (D48) |
| `RotationEngines` | `api/ports.py` | **Real:** `EntryPointEngines(discover_engine_functions(), carbon_models=DEFAULT_CARBON_MODELS)` (`api/engines.py`) | Calls the engine functions found; a soil-loss or water engine that is not found gives its part in the not-built form (D12) | Nothing in `api/`: each engine is picked up when its lane lands it |
| `RotationValidator` | `api/ports.py` | **Real:** `RotationDefinitionValidator` (`api/rotation_validator.py`) | Loads `rotation` into `RotationDefinition`, one `ErrorDetail` per error | — |
| `DecisionLayer` (PROPOSED) | `api/ports.py` | `DiscoveredDecisionLayer()` (`api/decision_layer.py`) | Looks `decision.output.assemble_decision_output` up on each request, calls it and checks what it returns; when it is absent or fails, a typed absence, `NOT_AVAILABLE` | Built in sub-lane L2b: `decision/output.py` (PROPOSED). Its counts name their carbon model and computation (D169, #331) |

The engine stand-in `EnginesNotBuilt` and the validator stand-in
`AcceptAnyRotation` are **removed**: no test needs them. The runner reports an
engine that is not built itself, and tests that need another validator pass
their own fake.

Payload types in `api/ports.py`, one line each: `CalendarPayload` is
`RotationCalendar`, `ResultsPayload` is `ResultsPerRotation`, `ReasonCode` is
the C3.2 list of `contracts/results/models.py`; `SoilSlopePayload` is
`SiteSoilSlope` (in `adapters/ports.py`). `RotationPayload` stays a mapping:
the request carries a JSON object, the validator checks it and the runner
loads it into `RotationDefinition` for EP2. `CLIMATE_CONTRACT` and
`SOIL_SLOPE_CONTRACT` are read from the `contract` field of the two site-data
models, so they cannot differ from them.

`RunSettings(start_date, end_date)` carries what is not a client choice. It
has no default dates. Without a period the route does not call the climate
source and reports it `unavailable` / `NOT_AVAILABLE`, under the source's own
`source_id` and `contract` (the route invents no identifier).

### Import path of the contract models

Contract models are imported only as `contracts.inputs`, `contracts.results`
and `contracts.rotation_definition`, never by the short names, and nothing is
imported from a `contracts/*/test_examples.py` module. `contracts/__init__.py`
was landed by lane L0 (#76). `api/test_packaging.py` checks that no contract
folder is loaded under a second name; it skips only if that file is ever
removed.

## The engine runner (`api/engines.py`)

`EntryPointEngines(functions, *, load_rotation=RotationDefinition.model_validate,
carbon_models=(), parameters=None)` implements `RotationEngines`.

- `EngineFunctions(build_rotation_calendar, compute_soil_loss,
  compute_water_deficit_exposure, build_residue_ledger, run_amg, run_rothc)`: each an
  injected callable, `None` when the engine is not built.
- `discover_engine_functions()` imports each one by the module path and name
  of `contracts/ENTRYPOINTS.md`: `engine.calendar.build_rotation_calendar`
  (EP2), `engine.erosion.compute_soil_loss` (EP1),
  `engine.water.compute_water_deficit_exposure` (EP3),
  `engine.residues.build_residue_ledger` (EP4, unit `l2/runner-residues`),
  `engine.amg.run_amg` (EP5, unit `l2/runner-amg`),
  `engine.rothc.run_rothc` (EP6, unit `l2/runner-ep6`). A module (or a package
  above it) or a function that does not exist gives `None`. Any other import
  error, including a module that imports something absent, propagates; a
  name that exists and is not callable is a `TypeError`. Engines land in the
  repository one by one, so which of the three is found changes over time;
  a test of "nothing is built" uses the fixture `engines_hidden` of
  `api/conftest.py` and never assumes which engines exist.
- `load_rotation` turns the request item into the argument of EP2 (decision
  Q9); by default `RotationDefinition.model_validate`, so EP2 receives a model
  instance, unchanged.
- `carbon_models`: the identifiers of the carbon models. The argument has no
  default beyond the empty tuple. Each must be one of the closed list of the
  results contract (`CarbonModel` of `contracts/results/models.py`, read as
  `CARBON_MODEL_IDS`); another is a `ValueError` at construction (PROPOSED). The app built by `create_app` passes
  `DEFAULT_CARBON_MODELS = ("amg", "rothc")`, the identifiers decided by the
  lead developer (issue #18, 17:29 UTC; decision D1 of #77; question 7 of
  `contracts/results/README.md`), defined once in `api/engines.py`. With the
  calendar engine present and the inputs there, the default app therefore
  assembles a `ResultsPerRotation` whose `soil_carbon_trend` holds six missing
  rows.
- `parameters`: the parameter catalogue (Q3, D46, D56 of issue #77), a
  `dict`; anything else is a `TypeError`. `None` is the empty catalogue `{}`
  and reads no file (PROPOSED). See "The parameter catalogue" below.

Call order (accepted in issue 18):

1. EP2 first: `build_rotation_calendar(load_rotation(rotation))`.
2. EP1 and EP3 with the keyword arguments `calendar`, `climate`, `soil_slope`
   (G3), also when the calendar is infeasible (G4), and `parameters`, always
   (below). EP2 never gets `parameters`.
3. EP4 `build_residue_ledger(rotation=..., calendar=..., climate=...,
   parameters=...)`, all by keyword, under the same conditions as EP1 and EP3
   (also for an infeasible calendar): `rotation` is what `load_rotation`
   returned (the object EP2 received), `calendar` the calendar of the phase,
   the same one EP1 gets (item 8 of "For the platform" in
   `engine/residues/README.md`), `climate` the same `SiteClimate`, and the
   same catalogue. Its series become `annual_carbon_inputs` of the forcing
   (below); the ledger itself is not in the response (OPEN).
4. EP5 `run_amg(forcing, parameters=...)` (D65), under the same conditions
   as EP1 and EP3 (calendar built, climate and soil-and-slope present and of
   the calendar's field), on the `CarbonForcing` built by
   `api.carbon_forcing.build_carbon_forcing` (below). When the forcing cannot
   be laid out, EP5 is not called (see the table of absences).
   Then EP6 `run_rothc(forcing, parameters=...)` (D65, unit `l2/runner-ep6`,
   PROPOSED) under the same conditions, on the **same forcing object** EP5
   received: the forcing of a phase is built once, when a configured carbon
   model has its engine built, and handed to both.
5. `ResultsPerRotation`: `case_id`, `field_id`, `rotation_id` from the
   calendar; `soil_loss` from EP1 and `water_deficit_exposure` from EP3,
   unchanged, or in the not-built form when that engine is not built (D12);
   `soil_carbon_trend` by the mapping below.

The runner computes nothing scientific, converts no unit, fills no gap and
never builds a number. It catches nothing an engine raises (G5, Q7): the route
answers `500` `INTERNAL_ERROR` with the CORS headers and no exception text. An
engine that returns something other than the type its signature names
(`RotationCalendar`; `SoilLossResults` or the results `Missing`; a `list` of
`WaterDeficitExposure`; `ResidueLedger`; `CarbonBalance`) is a defect:
`TypeError`, so also `500`. `contracts/residue_ledger/` is never imported at
module load: `residue_ledger_type()` imports it only once EP4 has answered
(PROPOSED), so the runner works whether or not that contract and EP4 are in
the repository; the tests replace that seam with a class of their own. A
`ResidueLedger` whose `case_id`, `field_id` or `rotation_id` differs from the
calendar is a `TypeError` too (`check_ledger`, PROPOSED), and so is a series
of the ledger whose agricultural years are not those of the forcing horizon. So is a `CarbonBalance` whose `case_id`, `field_id` or `rotation_id`
differs from the forcing, or whose `carbon_model` is not the model of the
engine that answered (`amg` for EP5, `rothc` for EP6): the forcing is
the runner's own, so the mismatch is the engine's (`check_balance`). That includes
a built engine that returns the not-built form of its own part: D12 allows
that form only for an engine that is not built.

### The phases of a rotation (`api/phases.py`; D109, D117, D141; PROPOSED)

Decision D109 of issue #77: each phase of a rotation is a scenario with its own
`scenario_id`, each phase starting in the first agricultural year of the
record; D117: phases are nested inside each value of an uncertain input (read
by the decision layer). The runner builds **option (b), a calendar the runner
moves** (D132; #18, 00:57 UTC): EP1, EP3 and EP5 keep their signatures (D56)
and get the calendar of each phase.

- **Who lays the phases out: lane L1.** `phase_calendar(calendar, p) ->
  RotationCalendar` and `list_phases(calendar) -> list[int]` in
  `engine/calendar/repeat.py` (#221, #228). `discover_engine_functions()`
  finds both by name (fields `phase_calendar` and `list_phases` of
  `EngineFunctions`), and `components_crossing_phase(calendar, p) ->
  list[str]` too, optional (field `components_crossing_phase`). The runner
  holds **no copy of their rules**, the crossing rule included.
- **Phase `p`** (0 … N−1, N = what `list_phases` gives), `scenario_id`
  `phase_{p+1}`, `first_ag_year` the agricultural year (C5.3) in which the
  phase's calendar starts (checked below). Phase 0 is the calendar of EP2 itself,
  unchanged (the same object; the route and CH07 of
  `validation/test_chain_examples.py` compare it) and is never asked of
  `phase_calendar`. Every other phase is what `phase_calendar` returns, used
  as returned.
- **What they return is checked:** `list_phases` any sequence equal to
  `0 … N−1`; `phase_calendar` a `RotationCalendar`, re-validated, that keeps
  everything but the dates: contract, example mark, identifiers, start
  month, feasibility, and the components as a multiset of (identifier, crop,
  period types); **a date missing in the EP2 calendar stays missing**
  (never filled), while a present date may come back missing (the phase
  rule may leave it missing with its reason); and, for `p ≥ 1`, its
  `start_date` falls in agricultural year `first + p` of the EP2 calendar,
  so no phase is misaligned or repeated (true of lane L1's rule, its point
  12). Anything else is a defect (`TypeError`, `500`). Whatever they raise propagates (`500`), **a `ValueError`
  included**: D141 gives a rule for every phase, so no phase is refused.
- **A component that crosses into a phase's first year (D141, amends
  D133: no phase is refused).** The phase is computed on the calendar
  `phase_calendar` returns, whatever form lane L1 gives it (today the D133
  form, the crossing date missing `NOT_COMPUTABLE`); the engines answer the
  days that depend on a missing date missing with their reason, never as
  days with no crop. When `components_crossing_phase` exists, the detail of
  the phase's `calendar` module gives how many components it names (a
  count, never an identifier) and that the phase runs on the calendar
  `phase_calendar` returned; it makes no claim on how the phase is laid
  out. Without that function no count is written. A date on 29 February
  that came back 28 February is counted in the same detail.
- **Running.** EP2 once. For each phase, EP1, EP3, EP4, EP5 and EP6 once on its
  calendar, with the same climate, soil-and-slope and `parameters` objects;
  every rule of the table below applies per phase. Nothing is cached across
  phases: a request costs `N` times the engines.
- **One phase only** (`scenarios` holds the top-level answer once): EP2 not
  built (`first_ag_year: null`), an input absent, site data of another field,
  an infeasible calendar (run once, unmoved), **the phase functions not
  found** (either of the two absent, for example an older engine tree: only
  `phase_1`, and the calendar module says the phases were not laid out), and
  a calendar without a start month (only `phase_1`, with a note on the
  calendar module naming how many phases `list_phases` gives that were not
  run). An implementation of `RotationEngines` that gives no phases gets
  `phase_1` from the route, `first_ag_year: null`.

### The parameter catalogue (`parameters`; Q3, D46, D56)

- **Where from:** the folder `params/records/` of the repository, which
  `contracts/ENTRYPOINTS.md` names. `api/config.py` finds it from the
  location of the `params` package (`PARAMETERS_FOLDER`), never from the
  working directory, so it is the same in tests, locally and in the
  container. It is not an environment variable.
- **When:** once, at start-up, in `load_config`: `params.catalogue.load_folder`,
  then `params.catalogue.check_catalogue` on what it returned. Never per
  request. `load_config(environ, *, parameters_folder=PARAMETERS_FOLDER)`;
  tests give another folder.
- **What refuses start-up (PROPOSED):** any problem reported by
  `load_folder` (a file that is not a `.json` record file, a file that cannot
  be read as a record, a folder that does not exist) or, when loading
  reported none, by `check_catalogue` (a malformed record, two records with
  the same `id` and `scope`, a placeholder). `ConfigError` names the folder
  between single quotes and lists the problems as those functions wrote
  them, one per line.
- **What does not:** an empty catalogue, today's state of `params/records/`
  (it holds only its `README.md`). The app starts and passes `{}`; an engine
  then answers `MISSING_INPUT` for each parameter it needs (D56; the
  engine's business, not the runner's).
- **What is passed:** exactly the dictionary `load_folder` returned, never
  edited, filled, defaulted or filtered, kept in `AppConfig.parameters`.
  `build_app` gives it to `create_app(..., parameters=...)`, which gives it
  to the default `EntryPointEngines`. `create_app` with `parameters=None`
  passes `{}`; with `engines` given, `parameters` is a `TypeError` (it
  would be ignored). The runner passes the same object, by keyword, on every
  call; it does not copy it per request, and it does not check it again: the
  check is the one of start-up.
- **Always passed:** EP1, EP3, EP5 and EP6 get `parameters=` by keyword on every
  call (EP5 since unit `l2/runner-amg`, EP6 since unit `l2/runner-ep6`, D65),
  as `contracts/ENTRYPOINTS.md` states (decided by the platform developer
  once both engines take it; unit `l2/runner-always-parameters`). The runner
  reads no signature and does not adapt: an engine function that does not
  take `parameters` raises `TypeError` and the route answers `500`, like any
  engine that does not follow its contract.

### A part whose engine is not built (D12)

| Part | Its engine is built | Its engine is not built |
|---|---|---|
| `soil_loss` | What EP1 returns, unchanged | `SoilLossNotBuilt`, reason `NOT_AVAILABLE` |
| `water_deficit_exposure` | What EP3 returns, unchanged | `WaterDeficitExposureNotBuilt`, reason `NOT_AVAILABLE` |
| `soil_carbon_trend` | `amg`: the three rows of the `CarbonBalance` of EP5, unchanged; `rothc`: the three rows of the `CarbonBalance` of EP6, unchanged (mapping below). A model whose engine is not built: its three rows missing `NOT_AVAILABLE`, naming its engine function | The six missing rows (`amg`, `rothc`, three computations each, `NOT_AVAILABLE`), not `SoilCarbonTrendNotBuilt`: the rows say which models are absent (platform developer, on #100) |

`part_not_built(model, entry point)` builds the part only through the
contract: the indicator from the model's own field, the direction and units
from `DIRECTION_OF` and `UNITS_OF`, the reason `REASON_OF_A_PART_NOT_BUILT`
of `contracts/results/models.py`. Its detail names the engine function, as
the module state does: "the module is not built yet:
engine.erosion.compute_soil_loss" (PROPOSED text). With both EP1 and EP3 not
built and the inputs present, the result holds two not-built parts and the
six carbon rows, the shape of `PLACEHOLDER_results_per_rotation_not_built.json`
except for carbon.

### What the runner writes when something is absent (PROPOSED, every row)

A typed absence, never a stand-in value, never an invented identifier.
Whenever `result` is `None`, the calendar that was built is still returned.
The rows are checked in this order; the first that applies decides
`result_missing`. **Order when several hold at once (PROPOSED):** the order
of the table. In particular, when an input is absent **and** an engine is
not built, the answer is still `result: null` with `MISSING_INPUT`: a result
is assembled only when every input the built engines need is present (see
OPEN).

| Situation | `result` | `result_missing` | Modules |
|---|---|---|---|
| EP2 not built | `None` | `NOT_AVAILABLE`, detail names `engine.calendar.build_rotation_calendar` | `calendar` `not_available` / `NOT_AVAILABLE`; `erosion`, `water` `not_available` / `MISSING_INPUT` naming the calendar (see the precedence rule below) |
| Climate or soil-and-slope data is `None` | `None` | `MISSING_INPUT`, detail names the input(s) (`climate`, `soil_slope`). EP1 and EP3 are **not** called: their arguments are model instances (G3) | `calendar` as it ran; `erosion`, `water` `not_available` / `MISSING_INPUT` |
| Climate or soil-and-slope data carry another `case_id` or `field_id` than the calendar | `None` | `MISSING_INPUT`, detail starts "site data of another field than the calendar" and names the input(s) and the identifier field(s) that differ, never their values. EP1 and EP3 are **not** called: they would raise `ValueError` (G5) | `calendar` as it ran; `erosion`, `water` `not_available` / `MISSING_INPUT` |
| EP1 or EP3 not built, or both (a built one is still called) | `ResultsPerRotation` with that part in the not-built form (D12) | `null` | that module `not_available` / `NOT_AVAILABLE`; the other from its output |
| EP1 returns a bare `Missing` (Q4), whether EP3 is built or not | `None` | its reason and detail, copied | `erosion` `not_available` with that reason and detail |
| No carbon model identifier configured (an explicit `carbon_models=()`; not the app's default) | `None` | `NOT_AVAILABLE`, detail says the carbon model identifiers are not configured | `residues`, `amg`, `rothc` `not_available` / `NOT_AVAILABLE` |
| Carbon model identifiers configured, EP4, EP5 and EP6 not built | `ResultsPerRotation` | `null` | For each identifier, the three computations of C1.6 as missing `SoilCarbonTrend` items, reason `NOT_AVAILABLE`, detail "no carbon engine is built yet", with the identifier, direction and unit of `contracts/results/models.py` (C3.1). `residues`, `amg`, `rothc` `not_available` / `NOT_AVAILABLE`, the same detail (the answer before EP5 existed, unchanged) |
| EP5 or EP6 built, the forcing cannot be laid out (no start month, no daily series, no whole agricultural year in the record) | `ResultsPerRotation` | `null` | Neither is called. The three rows of each built and configured model missing with the reason of the producer (`MISSING_INPUT` or `NO_COVERAGE`); its module `not_available` with it |
| EP5 built and called | `ResultsPerRotation` | `null` | The three `amg` rows of the balance, unchanged; `amg` state from their counts (`available`, `degraded` or `not_available`, as every module) |
| EP6 built and called (unit `l2/runner-ep6`, PROPOSED) | `ResultsPerRotation` | `null` | After the `amg` rows, the three `rothc` rows of its balance, unchanged; `rothc` state from their counts by the same rule (`module_status_of`). Nothing in them is shortened or rewritten by the runner |
| A carbon engine not built while another is | `ResultsPerRotation` | `null` | Its three rows missing `NOT_AVAILABLE` and its module `not_available` / `NOT_AVAILABLE`, both with the detail "the module is not built yet: <its engine function>" (for example `engine.rothc.run_rothc`) |

With EP5 built and `amg` not among the configured carbon models (for
example `carbon_models=("rothc",)`), EP5 is never called: the result has no
`amg` rows and `amg` is `not_available` / `NOT_AVAILABLE`, detail "the carbon
model 'amg' is not among the configured carbon models, so
engine.amg.run_amg is not called" (PROPOSED). In the same way, with EP6 built
and `rothc` not configured (`carbon_models=("amg",)`), EP6 is never called:
no `rothc` rows, and `rothc` is `not_available` / `NOT_AVAILABLE`, detail "the
carbon model 'rothc' is not among the configured carbon models, so
engine.rothc.run_rothc is not called" (PROPOSED, unit `l2/runner-ep6`). With
only `rothc` configured the forcing is still built and EP6 called. Whatever
the configured order, the rows are those of EP5, then those of EP6, three
each.

With EP5 or EP6 built, neither is called whenever EP1 and EP3 are not (EP2 not
built, an input absent, site data of another field): each built and
configured one is then `not_available` / `MISSING_INPUT` with the same detail
as `erosion` and `water`, and a carbon module whose engine is not built names
its engine function.

EP4 (unit `l2/runner-residues`, PROPOSED). Not built: every row above is
unchanged. Built: it is called whenever EP1 and EP3 are, and not called
whenever they are not; then `residues` is `not_available` / `MISSING_INPUT`
with the same detail. When it ran, `residues` takes its state from the
ledger: a ledger without agricultural years (`years_missing`) is
`not_available` with that reason and detail; otherwise every value of the
ledger is counted with the rule of every module (`ledger_values`: each
`Value` of each component, found by type rather than by field name, then
each yearly value of each series). A ledger with no value at all is
`not_available` / `NOT_AVAILABLE`, detail "the residue ledger holds no
component and no carbon-input series". With EP4 built and EP5 not built, `amg` is
`not_available` / `NOT_AVAILABLE` naming `engine.amg.run_amg`, and so are its
three rows (not "no carbon engine is built yet").

**Precedence rule (PROPOSED):** a module whose function is not built is
`not_available` / `NOT_AVAILABLE` whatever else is absent; `MISSING_INPUT` is
written only for a module that is built and was not called because an input
is missing. So in the default app (nothing built) every module is
`NOT_AVAILABLE`.

### The producer of `CarbonForcing` (`api/carbon_forcing.py`, PROPOSED)

`build_carbon_forcing(calendar, climate, soil_slope, *, carbon_inputs=None)
-> CarbonForcing | Missing` builds the one forcing of one rotation (L2a is the producer of the contract,
#155, D62) from what the runner already holds. It converts no unit, fills
no gap and computes only what a decision of #77 fixes: the yearly
`mean_temperature` of D118 from the daily mean of D30. Every quantity whose
definition, aggregation or source is not decided, or not yet usable, is
missing with its reason, never zero. It reads no file, calls no
network and never imports `engine/`; the identifiers below are those
`engine/amg/entry.py` reads (`FORCING_QUANTITIES`), and
`api/test_carbon_forcing.py` checks them against the engine when it is
importable. Every row is PROPOSED (platform developer, issue #18).

| Part | Value |
|---|---|
| `contract`, `example_data` | `"carbon_forcing"`; `example_data` true if the calendar, the climate or the soil and slope says so |
| `case_id`, `field_id`, `rotation_id` | From the calendar (the runner has already compared climate and soil with it, D14) |
| `horizon` | The whole agricultural years of the climate record (D47, D29), cut by the calendar's start month (`ag_year_start`): from the first month of the first whole agricultural year to the last month of the last one (C5.3, C5.5). The record's period is read from the document: the days every daily series covers (latest `start_date`, earliest `end_date`); monthly series are not read |
| `soil_depth` (D180) | 20 `cm`, provenance `DECLARED`, source naming D180 (the carbon benchmark depth of D71, written in `cm` because RothC compares it with the unit of `rothc_tsmd_reference_depth`); `range_missing` `NOT_AVAILABLE` (D180 states no range) |
| `annual_climate` `mean_temperature` (D118) | One item per agricultural year of the horizon: the arithmetic mean over the year of the daily mean temperatures of D30. D30 reads "Derived by the engine (mean from the daily maximum and minimum; pressure from elevation), not requested as series"; the daily mean is the arithmetic mean of `air_temperature_max_2m` and `air_temperature_min_2m` (CQ2, CQ3 of `contracts/CLIMATE_QUANTITIES.md`, found by quantity, never by position), the same form as `mean_temperature` of `engine/water/et0/equations.py`. A year with a day missing in either series is missing `MISSING_INPUT` naming the series, the day and its reason (never filled or partially averaged, C3.3, C3.4); a day absent from a series, `NO_COVERAGE`. An absent input series: every year `MISSING_INPUT`. Input units that differ: every year `NOT_COMPUTABLE`, unit `OPEN`, nothing converted. Otherwise the unit of the inputs; provenance `DERIVED` (C4.3); source naming D118, D30 and the source of each input series; `range_missing` with the reason the inputs carry (or `NOT_AVAILABLE` if they differ): no range is derived (C2.2) |
| `annual_climate` `water_balance` (D181) | One item per agricultural year of the horizon, in `m`: D181 of #77, P + IW − ET0, each summed over the agricultural year, divided by 1000 (`MM_PER_M`, the SI prefix: "mm / 1000"). P is the daily `precipitation` (CQ1, D23, the series EP1 and EP3 read; unit `mm day-1`, otherwise every year `NOT_COMPUTABLE`, nothing converted; absent, every year `MISSING_INPUT`). ET0 is the daily FAO-56 reference evapotranspiration of D44 that the runner passes (`reference_evapotranspiration`, since #350), declared as a substitute for the Penman (1948) PET of the source; IW = 0 (rainfed rotations), so no irrigation is read. A year with a day absent from either input is `NO_COVERAGE`, a day held missing keeps its reason; the year is never filled or partly summed (C3.3, C3.4). ET0 not passed: every year `NOT_AVAILABLE`; not computable at all: every year with that reason. Provenance `DERIVED`; `range_missing` `NOT_AVAILABLE`; the source names D181, the adaptation and IW = 0, and states the range of P − PET the source calibrated, −290 to 595 mm yr-1 (Clivot et al. 2019, p. 107, quoted by D181, `D181_CALIBRATED_RANGE_MM`): a year outside it keeps its number and the source names it as outside the calibrated range. The unit `m` is the one `engine/amg` compares with `amg_moisture_sensitivity` (`m-1`) |
| `annual_carbon_inputs`, EP4 built (unit `l2/runner-residues`) | The `annual_carbon_inputs` of the `ResidueLedger`, copied unchanged: the same series, in the same order (up to three per crop and purpose, `origin` the crop). **No unit is converted:** by D147 of issue #77 EP4 writes these series in `t C ha-1`, the unit `run_amg` requires (until it does, AMG answers `NOT_COMPUTABLE` naming the unit). The `amg` module detail says how many series were copied, in which unit, that the platform converts none and, only when a unit is not `t C ha-1`, that those series do not follow D147 (EP4 is to write `t C ha-1`), so AMG refuses them. A series with `NOT_COMPUTABLE` years (for example a cover or pasture crop, OPEN 5 of the ledger, or an infeasible calendar) is copied, never left out, since leaving it out would make AMG run without that crop's carbon; the detail gives their number and leaves the reasons to the series (PROPOSED). A ledger with years and no series: the detail says the ledger wrote no carbon-input series. The ledger applies the same identifier filter as the per-crop series, so the note on crops left out (next row) is written whatever the source of the series. A ledger without agricultural years (`years_missing`): the per-crop series of the next row, every year missing with the ledger's `years_missing` instead of the D122 text |
| `annual_carbon_inputs`, EP4 not built | One series per crop of the calendar, once each in order of first appearance, `origin` and `quantity` both the `crop_id` (`run_amg` looks the humification coefficient up under scope key `crop` = `origin`, `ORIGIN_SCOPE_KEY`). Every year missing `NOT_AVAILABLE`: the residue ledger (EP4) is not built (D122). Unit `t C ha-1`, the unit `run_amg` requires (`STOCK_UNIT`, derived from C1.5 as the engine derives it). A `crop_id` that is not a quantity identifier (`^[a-z][a-z0-9_]*$`) cannot be a series and is left out, never renamed; `CarbonForcing` has no field to say so, so the runner adds to the detail of the `amg` module "N crop(s) of the calendar could not be written as carbon-input series of the forcing: their crop_id is not a quantity identifier" (their number only, never the identifiers; `crops_left_out`). Why series and not an empty list: with no series `run_amg` answers `NOT_COMPUTABLE` ("no origin") for the humified input; with all-missing series it answers `MISSING_INPUT` naming the reason, the residue ledger |
| `soil_properties` (D120) | `clay_content`, `carbonate_content`, `ph`: copied from `SiteSoilSlope.soil_properties` only if an item with exactly that `quantity` is there (never converted, never renamed); otherwise missing `NOT_AVAILABLE`, unit `OPEN`, detail naming D120 (a person reads them from the D112 profile, under D34). Why `NOT_AVAILABLE` and not `NOT_DECLARED`: D120 keeps `NOT_DECLARED` for a property the profile does not print, which only the person reading it can know; until a person has read it, the platform only knows that no value has reached it, the meaning of `NOT_AVAILABLE` closest in C3.2. When the reading says "not printed", the soil file carries the item missing `NOT_DECLARED` and it is copied as it is |
| `starting_state` (D121) | `soil_organic_carbon` (PROPOSED source): the `SiteSoilSlope.soil_properties` item with exactly that quantity, copied unchanged only if its unit is `t C ha-1`, the stock unit `run_amg` requires. Another unit (for example a concentration) is never converted: missing `NOT_COMPUTABLE`, detail naming D121. Absent: missing `NOT_AVAILABLE`, detail naming D121 (a person reads it from the D112 profile, under D34) |
| `climate` (D220), for RothC | Three monthly series over the months of the horizon, no `open_pan_evaporation` (EP6 then takes PET over the pan factor). `rainfall`: the sum over the calendar month of the daily `precipitation` (CQ1, D23; unit `mm day-1`, otherwise every month `NOT_COMPUTABLE`), in `mm`. `potential_evapotranspiration`: the sum over the month of the daily FAO-56 reference evapotranspiration of D44 the runner passes (`reference_evapotranspiration`), in `mm`, its `source` saying that FAO-56 ET0 stands in for PET (D80); not passed: every month `NOT_AVAILABLE`; not computable at all: every month with that reason. `mean_temperature`: the mean over the month of the daily means of D30, in the unit of the daily series. A month with a day absent is `NO_COVERAGE`, a day held missing keeps its reason; the month is never filled (C3.3, C3.4). Provenance `DERIVED`, `range_missing` `NOT_AVAILABLE` |
| `carbon_inputs` (D221) | The `monthly_carbon_inputs` of the `ResidueLedger`, copied unchanged: the same series, in the same order (one per origin of D194, every month of the horizon, the explicit zeros of D221 written by EP4). No arithmetic and no unit converted (D147). EP4 not built, or a ledger without years: no series |
| `soil_cover` (D222), for RothC | One series, `soil_cover_state`, unit `dimensionless` (the identifier and unit `engine/rothc/entry.py` reads), over the months of the horizon: 1.0 when a living crop of the repeated calendar stands on more than half of the days of the month, 0.0 otherwise, including the fallow under residue. "Most days" is read as more than half (brief #373), so a month with exactly half of its days with a live crop is 0.0; the source text says so. The runner counts the days (`live_crop_months_for_forcing`): lane L1's public rule `engine.water.living_crop.live_crop_by_day` (D135, D136: the window of D157, the days on which EP3 asks transpiration), found by name like the entry points (`LIVE_CROP`, `EngineFunctions.live_crop_by_day`), called once per phase on the calendar of the phase EP3 reads, over the record period of the forcing (`record_period`), with the catalogue unchanged; only the dates of the record are read, never a climate value. It is not called when no forcing can be laid out. A month with a day whose live status is not known (for example a crop with no stage length) is missing with that day's reason, the day named; a month the answer does not hold in full is `NO_COVERAGE`. Not built: every month missing `NOT_AVAILABLE` naming the function, never zero; the producer called with no count writes every month `NOT_AVAILABLE`. An answer of another shape is a `TypeError` (`500`); what it raises propagates. Provenance `DERIVED`, `range_missing` `NOT_AVAILABLE`, the source names D222 and the tie rule. Tests: `api/test_soil_cover.py` |
| The daily reference evapotranspiration (runner) | Lane L1's public function `engine.water.daily_reference_evapotranspiration(climate, parameters=...)` (D256 of #77, listed in `contracts/ENTRYPOINTS.md` beside EP3, the series EP3 uses), found by name like the entry points (`REFERENCE_ET0`, `EngineFunctions.daily_reference_evapotranspiration`) and called once per request whenever a configured carbon engine is built (before the forcing is laid out, so it may be computed and then unused when the forcing turns out missing, for example with no whole agricultural year; no value is affected), with the catalogue unchanged. Its answer (date → number or `Missing`) is handed to the producer unchanged; an answer of another shape is a `TypeError` (`500`), what it raises propagates. Not built: one `Missing` `NOT_AVAILABLE` naming the function, so every month and year that needs it is missing with that reason. The runner imports no private name of `engine/water/`. PROPOSED; the producer imports nothing of `engine/` |
| Series headers | All-missing series carry no `provenance`, `source` or `range_missing` (the contract's rule) |

No forcing is built, and neither EP5 nor EP6 is called, when the calendar has no start
month (`MISSING_INPUT`, naming `ag_year_start` and its reason), when the
climate document has no daily series (`MISSING_INPUT`), or when the record
covers no whole agricultural year (`NO_COVERAGE`, C5.5).

### From a `CarbonBalance` to `soil_carbon_trend`

`carbon_trend(carbon_models, amg_rows, rothc_rows)` follows "From the entry
points to one response" of `contracts/ENTRYPOINTS.md` (#210; PROPOSED there,
not ours): the list of the balance of EP5 (`amg`), copied unchanged (or its
three rows missing when EP5 was not called), then the list of the balance of
EP6 (`rothc`) in the same way (unit `l2/runner-ep6`). A model whose engine is
not built has its three rows missing `NOT_AVAILABLE`, detail "the module is
not built yet: <its engine function>". That order holds whatever the order of
`carbon_models`; a model that is not configured has no rows. Values of the
two models are never merged (C1.5). With no carbon engine built the six rows
are as before, in the configured order. The balance itself (stocks and flows by
year) is not in the response (OPEN below).

### Module states (PROPOSED)

Identifiers (decided, D13) `calendar`, `erosion`, `water`, `residues`, `amg`, `rothc`, one per
entry of `contracts/ENTRYPOINTS.md`, always all six, in that order.

- Function absent: `not_available` / `NOT_AVAILABLE`.
- `residues`: from the ledger, as described under the absence table (unit
  `l2/runner-residues`).
- Function ran, no value of its output missing: `available`.
- Function ran, some values missing: `degraded`, reason of the first missing
  value (annual soil loss before monthly), detail `"<n> of <m> values are
  missing"`.
- Function ran, every value missing: `not_available` with that reason.
- `calendar`: `available` when `feasibility.feasible`; otherwise `degraded` /
  `NOT_COMPUTABLE`, detail giving the number of rule violations.

`count_values(values) -> ValueCount(present, missing, first_missing)` is the
one pure counting function over `IndicatorValue` items, with
`soil_loss_values` and `result_values` listing the values of a
`SoilLossResults` and of a `ResultsPerRotation`.

**Counting a not-built part (PROPOSED):** a part in the not-built form
contributes no present value and counts as **one** missing value, with its
own `missing` part as `first_missing` when it comes first. So
`values_missing` is never zero while a part is not built, and a result with
only not-built parts and the carbon rows has `values_present == 0`. `EnginesResult` carries
`values_present` and `values_missing` of the result; both are zero without a
result and not both zero with one (checked at construction).

## PROPOSED

- The shape of `site` (`SiteReference`).
- The error codes, their message templates, and the classification rule.
- The shapes of `api/ports.py`: `ModuleStatus`, `ModuleState`
  (`available | degraded | not_available`), `Missing`, `EnginesResult` (with
  `values_present` and `values_missing`), `ErrorDetail`, `RunSettings`.
- Source identifiers of the stand-ins `climate_not_connected` and
  `soil_slope_not_loaded`.
- `result_missing` always present as a key, `null` when there is a result.
- The engine runner: `EngineFunctions`, `discover_engine_functions` (what
  counts as "not built" and what propagates), `EntryPointEngines`, the
  `TypeError` for a wrong return type.
- Every row of the table "What the runner writes when something is absent",
  their order, and the precedence rule.
- The module-state rules (the identifiers are decided, D13), the counting function,
  and the detail texts of the runner.
- The outcome rule.
- `RotationDefinitionValidator`: one detail per validation error, path
  relative to the rotation, code and message as above.
- The detail of the missing carbon rows ("no carbon engine is built yet").
- Unit `l2/app-config`: the configuration (`api/config.py`): the variable
  names, `AppConfig`, `load_config` reading only its mapping, blank as unset,
  every `ConfigError` case and message, `build_app` and `client_factory`
  taking the settings, closing the client in the lifespan, the move of
  `create_app` to `api/app.py`.
- Unit `l2/app-config`: the row "site data of another field" of the runner
  table (its place after "data is `None`", the reason `MISSING_INPUT`, the
  detail text, `other_field_inputs`), and the test cases of
  `api/test_config.py` and section 11 of `api/test_engines.py`.
- The test cases of `api/test_rotations.py`, `api/test_errors.py`,
  `api/test_engines.py`, `api/test_rotation_validator.py`,
  `api/test_packaging.py`.
- Unit `l2/runner-parameters`: loading the parameter catalogue at start-up
  from `params/records/` (`PARAMETERS_FOLDER`, `load_parameters`,
  `load_config(..., parameters_folder=...)`, `AppConfig.parameters`); every
  problem of `load_folder` or `check_catalogue` is a `ConfigError` and an
  empty catalogue is not; the message text; `parameters=None` as the empty
  catalogue in `EntryPointEngines` and `create_app`; the `TypeError` for
  `parameters` beside `engines`; the test cases of section 14 of
  `api/test_engines.py` and of the catalogue section of `api/test_config.py`.
- Unit `l2/runner-partial`: `part_not_built` and its detail text; counting a
  not-built part as one missing value; the order of the checks when an input
  is absent and an engine is not built (still `MISSING_INPUT`, no result);
  a built engine that returns the not-built form is a `TypeError`; the test
  cases of sections 12 and 13 of `api/test_engines.py` and the plain-path
  test of `api/test_config.py`. The outcome of the case "only EP3 built"
  is `no_result` in the test, because the PLACEHOLDER water output holds no
  present value and no number is written in a test to change that.

- Unit `l2/runner-amg`, for the reviewers to confirm: **the record period is
  the intersection of the daily series** (latest `start_date`, earliest
  `end_date`). A consequence: a daily series that is shorter than the others
  shortens the horizon, even when it is a quantity AMG does not read (today
  the forcing reads no climate value at all).
- Unit `l2/runner-amg` after D118 to D122: the source of the starting carbon
  (a soil item `soil_organic_carbon` in `t C ha-1`, D121), the reasons and
  details of the table above, the `range_missing` and source of
  `mean_temperature`.
- Unit `l2/runner-amg`: `carbon_models` checked against `CarbonModel`; EP5
  called only when `amg` is configured; the note on crops left out in the
  `amg` detail; EP5 in discovery and in the call order; the producer
  `api/carbon_forcing.py` and every row of its table (the record period as
  the days every daily series covers, the horizon, the identifiers, the unit
  `OPEN`, one carbon-input series per crop with the crop as `origin` and
  `quantity`, a crop that is not an identifier left out, the detail texts);
  `check_balance`; the mapping `carbon_trend`; the rows of the absence table
  for EP5; the details of `residues` and `rothc` once EP5 is built; the test
  cases of `api/test_carbon_forcing.py` and section 15 of
  `api/test_engines.py`.

- Unit `l2/runner-residues`: EP4 in discovery and in the call order (after
  EP3, before EP5, per phase); the lazy import of `contracts.residue_ledger`
  through `residue_ledger_type`; `check_ledger` (type and identifiers);
  copying the ledger's series unchanged into `annual_carbon_inputs`, with
  the years check; copying `NOT_COMPUTABLE` series instead of leaving them
  out; the per-crop missing series with the ledger's `years_missing`; the
  state of `residues` counted on every value of the ledger (components,
  then series), and `NOT_AVAILABLE` for a ledger with no value; the
  notes in the `amg` detail; the `amg` rows naming EP5 when only EP4 is
  built; the test cases of `api/test_runner_residues.py`.

- Unit `l2/runner-ep6` (issue #278; D159: the lead developer took this lane
  for the night of 15 November 2026): EP6 in discovery and in the call order
  (after EP5, per phase); the forcing of a phase built once when a configured
  carbon model has its engine built, and the same object handed to EP5 and
  EP6; `check_balance` checking the carbon model of the engine that
  answered; the `rothc` rows of the balance copied unchanged after the `amg`
  rows; the state of `rothc` by `module_status_of`; the text
  `ROTHC_NOT_CONFIGURED`; a carbon engine not built named "not built" in its
  rows and module state (the text "the runner does not call this engine
  yet" of unit `l2/rothc-tripwire` is gone); the test cases of section 17 of
  `api/test_engines.py`.

- Unit `l2/soil-tables`: the variables `SOIL_TABLE_FILES` and
  `SOIL_GROUPS_FILE` (both or neither), `SoilTablesConfig`,
  `AppConfig.soil_tables`, the `ConfigError` for the example and the tables
  together (in `load_config` and again in `build_app`), loading and checking
  every soil file at start-up, the messages, and the test cases of the
  soil-table section of `api/test_config.py`.

## Decided

Decisions of issue #77 that settle what earlier units left PROPOSED or OPEN
here.

| Decision | What it settles |
|---|---|
| D12 | A part whose engine is not built: the not-built form (unit `l2/runner-partial`). Replaces the OPEN "The results contract cannot express two answers the runner needs" |
| D13 | The module identifiers are the six engine folder names: `calendar`, `erosion`, `water`, `residues`, `amg`, `rothc` |
| D14 | The runner compares `case_id` and `field_id` of the site data with the calendar's before any engine is called |
| D16 | An error payload of the climate service is `SOURCE_UNAVAILABLE` |
| D17, D43 | One recorded real response may be committed; it is, under `docs/evidence/` |
| D18, D9 | The point of the series travels in "Site data: climate", from the response of the source |
| D19 | Field identity is a new contract; `site` stays `SiteReference` until that contract is on `main` |
| D20, D37 | The platform developer writes the adapter settings, from accepted values |
| D23 to D35 | The seven series, the community, and the period 2001-01-01 to 2024-12-31. Replaces the OPEN "Which years of the climate record are requested?"; `CLIMATE_START_DATE` and `CLIMATE_END_DATE` take those dates once the host sets them |
| D31 | `range_missing` reason: `NO_COVERAGE` |
| D36 | `fill_reason`: `NO_COVERAGE`, for a fill value and for an absent day |
| D38 | The soil-and-slope example source serves any field, under the identifiers of the request (unit `l2/runner-partial`). Replaces the OPEN "May the accepted soil-and-slope example stand in for any field?" |
| D51, D52 | A response without a point is usable; one provenance label for the three values of the point |
| D55 | The unit strings and the label of the point; with it the settings file of the adapter is written (`adapters/settings/nasa_power.json`) |
| D29 | The climate record period of the deployed service: 2001-01-01 to 2024-12-31 |
| D147 | EP4 writes the annual carbon-input series of `CarbonForcing.annual_carbon_inputs` in `t C ha-1` (from the ledger's `kg C ha-1`, 1 t = 1000 kg); the runner and AMG do no arithmetic on them. Replaces the OPEN "who converts `kg C ha-1` to `t C ha-1`" (OPEN 3 of the ledger); the runner still converts nothing, and its `amg` note on a unit other than `t C ha-1` says the series do not follow D147 |
| D141 (amends D133) | Each phase is laid out as the first one is; no phase is refused (unit `l2/runner-d141`). Replaces the OPEN "a component that starts before the first agricultural year of a phase" and "drop the runner's copy of the phase rule" |
| D46, D56 (Q3 of `contracts/ENTRYPOINTS.md`) | The runner loads the parameter catalogue and passes it to EP1 and EP3 as the keyword argument `parameters`; EP2 does not change; a parameter not in the catalogue is the engine's `MISSING_INPUT` (unit `l2/runner-parameters`). What the runner does when the catalogue has a problem, left to the platform developer by Q3: start-up fails (PROPOSED above). Replaces the OPEN "D46, the argument `parameters`" |

## OPEN

- **The phases of D109** (`api/phases.py`):
  - whether EP3 repeats the calendar over the record itself (lane L1,
    `engine/water/EXPOSURE.md` OPEN 5); until it does, it sees one cycle of
    the moved calendar;
  - a summary over the phases (D74, D96): for the decision layer, not the
    route;
  - the cost: `N` runs of EP1, EP3, EP4, EP5 and EP6 per request;
  - for lanes L0 and L1: whether the D141 layout is expressible in the
    current `RotationCalendar` contract together with `repeat_over_record`
    (no component may start before `start_date`,
    `contracts/inputs/rotation_calendar.py`). The runner only uses what
    `phase_calendar` returns.

- **The inputs of AMG after D118 to D122.** Answered: `mean_temperature`
  (D118, built) and `water_balance` (D181 settles D119; built from the daily
  ET0 the runner gets from the public function of D256, table above). Still missing with their
  reason:
  - `clay_content`, `carbonate_content`, `ph` (D120) and the starting soil
    organic carbon (D121): read by a person from the D112 profile (D34) into
    the soil file; whether the profile gives organic carbon as a stock in
    `t C ha-1` (D121) is for that person;
  - the carbon inputs (D122): the residue ledger (EP4) is wired (unit
    `l2/runner-residues`); who converts its unit is decided (D147, table
    above). Whether `NOT_COMPUTABLE` series of a cover or pasture crop are
    copied (PROPOSED here: yes) is for the lead developer. The vocabulary of
    `origin` and of the carbon-input quantities stays Q14 (b).
- **The soil depth and its unit** (C1.6), for the science reviewers.
- **Whether the forcing horizon must equal the agricultural years of the
  record** (OPEN 3 of `contracts/carbon_forcing/README.md`); proposed here:
  yes.
- **Expose the `CarbonBalance` (stocks and flows by year) to the interface.**
  Not in the response of this unit, to keep its shape. For the platform
  developer and the interface developer.
- **RothC (EP6, `engine.rothc.run_rothc`)**: discovered and called on the
  forcing of EP5 since unit `l2/runner-ep6` (issue #278, D159), which
  replaced the "not called" text and test of unit `l2/rothc-tripwire`. For
  the platform developer to review when he is back (D159).
- **The size of the `rothc` rows.** The runner copies the rows of EP6 as they
  come (C3.2: a missing value keeps its reason and detail) and shortens
  nothing. With the example rotation, the demonstration soil file and a
  climate record of D29 (2001 to 2024, start month 7), the `fitted_slope` row
  of `rothc` carries a detail of 550,085 characters: it names each of the
  277 monthly stocks of the horizon as missing, each with the five starting
  pools it lacks. Since the top-level fields repeat `phase_1`, the response
  grows from 2,472,819 to 3,580,535 bytes (+45 %) and holds no new number.
  How long a detail may be, and whether the engine names the first missing
  stock and a count instead, is for the owner of `engine/rothc/` (the text
  is the engine's) and for the platform developer (the size of the
  response). Not changed in `api/`.
- **Whether the notes of the `amg` module apply to `rothc`.** The note on the
  carbon inputs copied from the ledger and the note on crops left out are
  written on `amg` only: EP6 does not read `annual_carbon_inputs`
  (`engine/rothc/README.md`, "Not read by EP6"). PROPOSED; for the platform
  developer.
- **Expose the residue ledger in the response** (components, closure):
  not done; Q14 (b) and Q15 of `contracts/ENTRYPOINTS.md`, for the lead
  developer and the interface developer.
- **Crops whose `crop_id` is not a quantity identifier** cannot be a
  carbon-input series, and `CarbonForcing` has no field to record that they
  were left out; today only the `amg` module detail says how many. Whether
  the contract gains such a field, or `origin` takes another vocabulary, is
  for lane L0 (contracts/carbon_forcing/, Q14 (b)).
- **The chain test of lane L0 compares the route with a runner without EP5.**
  `validation/test_chain_examples.py` CH07 builds `EngineFunctions` with EP2,
  EP1 and EP3 only, while the route discovers EP5 too, so the `amg` rows
  differ. Lane L0 adds `run_amg=found.run_amg` to its `run_chain`; unit
  `l2/runner-ep6` added `run_rothc=found.run_rothc` there in the same way.

- **With an input absent and no engine built, should the route already
  answer with three not-built parts** (the form of
  `contracts/results/examples/PLACEHOLDER_results_per_rotation_not_built.json`),
  since nothing would have been computed anyway? Today it answers
  `result: null` with `MISSING_INPUT` (PROPOSED order above). For the lead
  developer.
- **The first real call has not been made by the deployed app.** Nobody knows
  yet how long one request for 24 years of seven daily series takes, whether
  the service accepts that span in one request (the scout report found no
  published maximum), or whether it fits the host's request timeout. A person
  watches the first call. If it does not fit: split a prefetch of the site
  data from the run; no job polling. For the platform developer.
- **How is the point (latitude, longitude) chosen for a field?** (OPEN in
  `adapters/ports.py`; stays with the science reviewers, D41, D48.)
- **What the calendar engine gets beyond the rotation definition** (Q8 of
  `contracts/ENTRYPOINTS.md`; lead developer and interface developer).
  `RotationDefinition` carries no start month of the agricultural year and no
  first or last date of the calendar, which `RotationCalendar` needs. The
  runner passes the model on unchanged and adds nothing. Decided (issue #18):
  a rotation without the start month will be invalid (`422`, no engine
  called) once lane L0's model requires it; `RotationDefinitionValidator`
  then enforces it with no change here. Until then the runner keeps the
  defensive handling of a bare `Missing` from EP1 (Q4). The first and last
  dates of the calendar remain open.
- **Should the engines get a read-only view of the catalogue?** The runner
  passes the same `dict` to every call, so an engine that changed it would
  change it for every later request. `types.MappingProxyType` would prevent
  that, but the contract's type is `dict[str, dict]`, not a mapping, so the
  runner passes the dictionary itself. For the platform developer (and lane
  L0 for the contract's type).
- **Should `parameters` become a required argument of `EntryPointEngines`
  and `create_app`?** Today `None` means the empty catalogue, because a test
  of lane L1 (`engine/water/test_exposure.py`, on `main` and in #165) builds
  `EntryPointEngines` without it. For the platform developer.
- **Which file holds the demonstration values of soil and slope?** A person
  supplies them; the PLACEHOLDER file is for testing the pipeline only (#77).
  D48 and D49 bring soil, slope and available water from public data through
  adapters of this lane, once the elevation model, the polygon-to-point rule
  and the licence of D49 are settled.
- **Which values go into the other settings?** `CLIMATE_CACHE_DIR` is the
  Railway volume of D42 (its path posted by the lead developer).

### No echo of submitted values in a rotation error

PROPOSED. The texts of the rotation errors come from the contract model, and a
model may write a submitted value into its own message (for example the
identifier of a component). `RotationDefinitionValidator` replaces any message
that repeats a submitted value of three characters or more with one fixed text;
the `path` and the `code` of the detail still say where the problem is and of
which kind. A message that only names a field of the contract is kept.
