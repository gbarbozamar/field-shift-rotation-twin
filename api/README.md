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
| `CORS_ORIGINS` | `https://gbarbozamar.github.io` | D42 |

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
settings=None)` receives the implementations; `None` means the default.

| Interface | Defined in | Default | Default behaviour | Still to come |
|---|---|---|---|---|
| `ClimateSource` | `adapters/ports.py` | Stand-in `ClimateUnavailable` | `data=None`, `unavailable`, `NOT_AVAILABLE` | The NASA POWER adapter (`adapters/power.py`) is wired by `POWER_SETTINGS_FILE` (see Configuration); its settings are OPEN in `adapters/README.md` |
| `SoilSlopeSource` | `adapters/ports.py` (re-exported by `api/ports.py`) | Stand-in `SoilSlopeNotLoaded` | `data=None`, `unavailable`, `NOT_AVAILABLE` | `adapters.example_soil_slope.ExampleSoilSlopeSource(path)` is wired by `SOIL_SLOPE_EXAMPLE_FILE` and serves the example for any field (D38). Then the adapters of soil and slope from public data (D48, D49) |
| `RotationEngines` | `api/ports.py` | **Real:** `EntryPointEngines(discover_engine_functions(), carbon_models=DEFAULT_CARBON_MODELS)` (`api/engines.py`) | Calls the engine functions found; a soil-loss or water engine that is not found gives its part in the not-built form (D12) | Nothing in `api/`: each engine is picked up when its lane lands it |
| `RotationValidator` | `api/ports.py` | **Real:** `RotationDefinitionValidator` (`api/rotation_validator.py`) | Loads `rotation` into `RotationDefinition`, one `ErrorDetail` per error | — |

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
carbon_models=())` implements `RotationEngines`.

- `EngineFunctions(build_rotation_calendar, compute_soil_loss,
  compute_water_deficit_exposure)`: each an injected callable, `None` when the
  engine is not built.
- `discover_engine_functions()` imports each one by the module path and name
  of `contracts/ENTRYPOINTS.md`: `engine.calendar.build_rotation_calendar`
  (EP2), `engine.erosion.compute_soil_loss` (EP1),
  `engine.water.compute_water_deficit_exposure` (EP3). A module (or a package
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
  default beyond the empty tuple. The app built by `create_app` passes
  `DEFAULT_CARBON_MODELS = ("amg", "rothc")`, the identifiers decided by the
  lead developer (issue #18, 17:29 UTC; decision D1 of #77; question 7 of
  `contracts/results/README.md`), defined once in `api/engines.py`. With the
  calendar engine present and the inputs there, the default app therefore
  assembles a `ResultsPerRotation` whose `soil_carbon_trend` holds six missing
  rows.

Call order (accepted in issue 18):

1. EP2 first: `build_rotation_calendar(load_rotation(rotation))`.
2. EP1 and EP3 with the keyword arguments `calendar`, `climate`, `soil_slope`
   (G3), also when the calendar is infeasible (G4).
3. `ResultsPerRotation`: `case_id`, `field_id`, `rotation_id` from the
   calendar; `soil_loss` from EP1 and `water_deficit_exposure` from EP3,
   unchanged, or in the not-built form when that engine is not built (D12);
   `soil_carbon_trend` written by the runner.

The runner computes nothing scientific, converts no unit, fills no gap and
never builds a number. It catches nothing an engine raises (G5, Q7): the route
answers `500` `INTERNAL_ERROR` with the CORS headers and no exception text. An
engine that returns something other than the type its signature names
(`RotationCalendar`; `SoilLossResults` or the results `Missing`; a `list` of
`WaterDeficitExposure`) is a defect: `TypeError`, so also `500`. That includes
a built engine that returns the not-built form of its own part: D12 allows
that form only for an engine that is not built.

### A part whose engine is not built (D12)

| Part | Its engine is built | Its engine is not built |
|---|---|---|
| `soil_loss` | What EP1 returns, unchanged | `SoilLossNotBuilt`, reason `NOT_AVAILABLE` |
| `water_deficit_exposure` | What EP3 returns, unchanged | `WaterDeficitExposureNotBuilt`, reason `NOT_AVAILABLE` |
| `soil_carbon_trend` | (no carbon engine exists) | The six missing rows (`amg`, `rothc`, three computations each, `NOT_AVAILABLE`), not `SoilCarbonTrendNotBuilt`: the rows say which models are absent (platform developer, on #100) |

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
| Carbon model identifiers configured (the app's default `amg`, `rothc`; no carbon engine is built, always true today) | `ResultsPerRotation` | `null` | For each identifier, the three computations of C1.6 as missing `SoilCarbonTrend` items, reason `NOT_AVAILABLE`, with the identifier, direction and unit of `contracts/results/models.py` (C3.1). `residues`, `amg`, `rothc` `not_available` / `NOT_AVAILABLE` |

**Precedence rule (PROPOSED):** a module whose function is not built is
`not_available` / `NOT_AVAILABLE` whatever else is absent; `MISSING_INPUT` is
written only for a module that is built and was not called because an input
is missing. So in the default app (nothing built) every module is
`NOT_AVAILABLE`.

### Module states (PROPOSED)

Identifiers (decided, D13) `calendar`, `erosion`, `water`, `residues`, `amg`, `rothc`, one per
entry of `contracts/ENTRYPOINTS.md`, always all six, in that order.

- Function absent: `not_available` / `NOT_AVAILABLE`.
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
- Unit `l2/runner-partial`: `part_not_built` and its detail text; counting a
  not-built part as one missing value; the order of the checks when an input
  is absent and an engine is not built (still `MISSING_INPUT`, no result);
  a built engine that returns the not-built form is a `TypeError`; the test
  cases of sections 12 and 13 of `api/test_engines.py` and the plain-path
  test of `api/test_config.py`. The outcome of the case "only EP3 built"
  is `no_result` in the test, because the PLACEHOLDER water output holds no
  present value and no number is written in a test to change that.

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

## OPEN

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
- **D46, the argument `parameters`** (the parameter catalogue passed to EP1
  and EP3): agreed by the platform developer, waiting for
  `contracts/ENTRYPOINTS.md` to state it. Nothing changes in the runner
  before that.
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
