# api/ — backend routes (lane L2 Platform)

FastAPI application. Run with `uv run uvicorn api.main:app --reload` from the
repository root; tests with `uv run pytest api/`.

Everything this unit designed is marked **PROPOSED** (blueprint section 3.7)
and takes effect only when a person approves the pull request. Questions a
person has to answer are marked **OPEN**.

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
  `complete` is **not reachable yet**.
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
| `SOIL_SLOPE_EXAMPLE_FILE` | Path of the accepted soil-and-slope contract example, served by `ExampleSoilSlopeSource` with state `example` | The soil-and-slope source is the stand-in |

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

### Running locally with settings

```bash
cp adapters/examples/PLACEHOLDER_power_settings.json <a folder outside git>/power_settings.json
# replace every placeholder with the values the people who own them decided
POWER_SETTINGS_FILE=<that folder>/power_settings.json \
CLIMATE_CACHE_DIR=<a folder for the cache> \
CLIMATE_START_DATE=<first day> CLIMATE_END_DATE=<last day> \
SOIL_SLOPE_EXAMPLE_FILE=<the accepted example> \
uv run uvicorn api.main:app --reload
```

Started with the template unchanged, the server starts but every climate
request fails (`https://power.invalid/` never resolves): the template is a
shape, not a configuration. `compose.yaml` lists the variables as comments;
none is switched on.

## Interfaces and their implementations

The route depends only on these interfaces. `create_app(cors_origins, *,
climate=None, soil_slope=None, engines=None, rotation_validator=None,
settings=None)` receives the implementations; `None` means the default.

| Interface | Defined in | Default | Default behaviour | Still to come |
|---|---|---|---|---|
| `ClimateSource` | `adapters/ports.py` | Stand-in `ClimateUnavailable` | `data=None`, `unavailable`, `NOT_AVAILABLE` | The NASA POWER adapter (`adapters/power.py`) is wired by `POWER_SETTINGS_FILE` (see Configuration); its settings are OPEN in `adapters/README.md` |
| `SoilSlopeSource` | `adapters/ports.py` (re-exported by `api/ports.py`) | Stand-in `SoilSlopeNotLoaded` | `data=None`, `unavailable`, `NOT_AVAILABLE` | `adapters.example_soil_slope.ExampleSoilSlopeSource(path)` is wired by `SOIL_SLOPE_EXAMPLE_FILE`: which file is the accepted example is a person's decision. Then the Block 2 adapters |
| `RotationEngines` | `api/ports.py` | **Real:** `EntryPointEngines(discover_engine_functions(), carbon_models=DEFAULT_CARBON_MODELS)` (`api/engines.py`) | Calls the engine functions found; today none is, so every module is `not_available` and there is no result | Nothing in `api/`: each engine is picked up when its lane lands it |
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
  name that exists and is not callable is a `TypeError`. Today all three are
  `None`.
- `load_rotation` turns the request item into the argument of EP2 (decision
  Q9); by default `RotationDefinition.model_validate`, so EP2 receives a model
  instance, unchanged.
- `carbon_models`: the identifiers of the carbon models. The argument has no
  default beyond the empty tuple. The app built by `create_app` passes
  `DEFAULT_CARBON_MODELS = ("amg", "rothc")`, the identifiers decided by the
  lead developer (issue #18, 17:29 UTC; decision D1 of #77; question 7 of
  `contracts/results/README.md`), defined once in `api/engines.py`. With all
  three engine functions present, the default app therefore assembles a
  `ResultsPerRotation` whose `soil_carbon_trend` holds six missing rows.

Call order (accepted in issue 18):

1. EP2 first: `build_rotation_calendar(load_rotation(rotation))`.
2. EP1 and EP3 with the keyword arguments `calendar`, `climate`, `soil_slope`
   (G3), also when the calendar is infeasible (G4).
3. `ResultsPerRotation`: `case_id`, `field_id`, `rotation_id` from the
   calendar; `soil_loss` from EP1 and `water_deficit_exposure` from EP3,
   unchanged; `soil_carbon_trend` written by the runner.

The runner computes nothing scientific, converts no unit, fills no gap and
never builds a number. It catches nothing an engine raises (G5, Q7): the route
answers `500` `INTERNAL_ERROR` with the CORS headers and no exception text. An
engine that returns something other than the type its signature names
(`RotationCalendar`; `SoilLossResults` or the results `Missing`; a `list` of
`WaterDeficitExposure`) is a defect: `TypeError`, so also `500`.

### What the runner writes when something is absent (PROPOSED, every row)

A typed absence, never a stand-in value, never an invented identifier.
Whenever `result` is `None`, the calendar that was built is still returned.
The rows are checked in this order; the first that applies decides
`result_missing`.

| Situation | `result` | `result_missing` | Modules |
|---|---|---|---|
| EP2 not built | `None` | `NOT_AVAILABLE`, detail names `engine.calendar.build_rotation_calendar` | `calendar` `not_available` / `NOT_AVAILABLE`; `erosion`, `water` `not_available` / `MISSING_INPUT` naming the calendar (see the precedence rule below) |
| Climate or soil-and-slope data is `None` | `None` | `MISSING_INPUT`, detail names the input(s) (`climate`, `soil_slope`). EP1 and EP3 are **not** called: their arguments are model instances (G3) | `calendar` as it ran; `erosion`, `water` `not_available` / `MISSING_INPUT` |
| Climate or soil-and-slope data carry another `case_id` or `field_id` than the calendar | `None` | `MISSING_INPUT`, detail starts "site data of another field than the calendar" and names the input(s) and the identifier field(s) that differ, never their values. EP1 and EP3 are **not** called: they would raise `ValueError` (G5) | `calendar` as it ran; `erosion`, `water` `not_available` / `MISSING_INPUT` |
| EP1 or EP3 not built (the other is still called) | `None` | `NOT_AVAILABLE`, detail names the engine(s) | that module `not_available` / `NOT_AVAILABLE`; the other from its output |
| EP1 returns a bare `Missing` (Q4) | `None` | its reason and detail, copied | `erosion` `not_available` with that reason and detail |
| No carbon model identifier configured (an explicit `carbon_models=()`; not the app's default) | `None` | `NOT_AVAILABLE`, detail says the carbon model identifiers are not configured | `residues`, `amg`, `rothc` `not_available` / `NOT_AVAILABLE` |
| Carbon model identifiers configured (the app's default `amg`, `rothc`; no carbon engine is built, always true today) | `ResultsPerRotation` | `null` | For each identifier, the three computations of C1.6 as missing `SoilCarbonTrend` items, reason `NOT_AVAILABLE`, with the identifier, direction and unit of `contracts/results/models.py` (C3.1). `residues`, `amg`, `rothc` `not_available` / `NOT_AVAILABLE` |

**Precedence rule (PROPOSED):** a module whose function is not built is
`not_available` / `NOT_AVAILABLE` whatever else is absent; `MISSING_INPUT` is
written only for a module that is built and was not called because an input
is missing. So in the default app (nothing built) every module is
`NOT_AVAILABLE`.

### Module states (PROPOSED)

Identifiers `calendar`, `erosion`, `water`, `residues`, `amg`, `rothc`, one per
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
`SoilLossResults` and of a `ResultsPerRotation`. `EnginesResult` carries
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
- The module identifiers and the module-state rules, the counting function,
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

## OPEN

- **Which years of the climate record are requested?** (science reviewers).
  Until answered, no period is configured and the climate is reported
  unavailable.
- **Which contract carries the identity of a field** (`case_id`, `field_id`),
  and so replaces `SiteReference`?
- **How is the point (latitude, longitude) chosen for a field?** (already
  OPEN in `adapters/ports.py`).
- **The results contract cannot express two answers the runner needs**
  (lead developer, as owner of `contracts/results/`; platform developer for
  the response). Where the model makes the answer impossible the runner
  returns no result with a typed absence instead:
  1. `ResultsPerRotation` has no missing form for a whole `soil_loss`, so
     "the erosion engine is not built" (and a bare `Missing` from EP1, Q4)
     cannot be written inside a result.
  2. A missing `water_deficit_exposure` item needs its `time_basis` (and an
     `ag_year` for the `ag_year` basis), which is the water engine's choice
     (C1.3), so "the water engine is not built" cannot be written inside a
     result without inventing it.

  A third case of the plan, "carbon not built" without model identifiers, is
  settled by the decision on the identifiers (`amg`, `rothc`); it remains
  only for an explicit `carbon_models=()`.

  Should `ResultsPerRotation` gain a missing form for each, or is a response
  without a result the intended answer?
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
- **May the accepted soil-and-slope example stand in for any field at the
  first checkpoint (blueprint section 7)?** (lead developer). The example
  carries its own `case_id` and `field_id`; today the runner answers site data
  of another field with a typed absence (`MISSING_INPUT`, `200`) instead of
  the engines' `ValueError` (`500`). So with `SOIL_SLOPE_EXAMPLE_FILE` set,
  the engines run only for the field the example names. If the example may
  stand in for any field: does the source rewrite the identifiers to the
  requested field, or do the engines stop comparing them? Neither is
  implemented. (The rotation definition example and the site-data examples
  also carry different identifiers.)
- **Which values go into the settings?** `POWER_SETTINGS_FILE` (every OPEN of
  `adapters/README.md`), `CLIMATE_START_DATE` and `CLIMATE_END_DATE` (science
  reviewers), `SOIL_SLOPE_EXAMPLE_FILE` (lead developer and platform
  developer), `CLIMATE_CACHE_DIR` and whether the host keeps it between
  restarts (platform developer). Until set, each piece stays an absence.

### No echo of submitted values in a rotation error

PROPOSED. The texts of the rotation errors come from the contract model, and a
model may write a submitted value into its own message (for example the
identifier of a component). `RotationDefinitionValidator` replaces any message
that repeats a submitted value of three characters or more with one fixed text;
the `path` and the `code` of the detail still say where the problem is and of
which kind. A message that only names a field of the contract is kept.
