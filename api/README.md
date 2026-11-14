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
- `rotation` must be a JSON object. Its contents are checked only by the
  `RotationValidator`.
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
- `result_missing` is non-null exactly when `result` is null (**PROPOSED**:
  the key is always present, `null` when there is a result).
- `outcome` (`derive_outcome`): `no_result` without a result; `complete` when
  every module is `available` and no source is `unavailable`; `partial`
  otherwise. When the "Results per rotation" contract model lands, "an
  indicator is missing" joins the rule for `partial`.
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

## Interfaces and their stand-ins

The route depends only on these interfaces. `create_app(cors_origins, *,
climate=None, soil_slope=None, engines=None, rotation_validator=None,
settings=None)` receives the implementations; `None` means the stand-in.

| Interface | Defined in | Stand-in (`api/standins.py`) | Stand-in behaviour | Replaced by |
|---|---|---|---|---|
| `ClimateSource` | `adapters/ports.py` | `ClimateUnavailable` | `data=None`, `unavailable`, `NOT_AVAILABLE` | The NASA POWER adapter (unit `l2/power-adapter`) |
| `SoilSlopeSource` | `api/ports.py` | `SoilSlopeNotLoaded` | `data=None`, `unavailable`, `NOT_AVAILABLE` | A loader of the accepted soil-and-slope example (`state="example"`), then the Block 2 adapters |
| `RotationEngines` | `api/ports.py` | `EnginesNotBuilt` | No calendar, no result (`NOT_AVAILABLE`), every module `not_available` | An implementation calling the engine entry points of `contracts/ENTRYPOINTS.md` |
| `RotationValidator` | `api/ports.py` | `AcceptAnyRotation` | Accepts any JSON object | Validation against the "Rotation definition" contract model |

Payload aliases in `api/ports.py`, one line each to change when the contract
models are merged: `RotationPayload`, `CalendarPayload`, `ResultsPayload`
(becomes `ResultsPerRotation`), `SoilSlopePayload` (becomes `SiteSoilSlope`),
and `ReasonCode` (becomes the C3.2 type of the contracts package).

`RunSettings(start_date, end_date)` carries what is not a client choice. It
has no default dates. Without a period the route does not call the climate
source and reports it `unavailable` / `NOT_AVAILABLE`.

## PROPOSED

- The shape of `site` (`SiteReference`).
- The error codes, their message templates, and the classification rule.
- The shapes of `api/ports.py`: `ModuleStatus`, `ModuleState`
  (`available | degraded | not_available`), `Missing`, `EnginesResult`,
  `SoilSlopeResult`, `ErrorDetail`, `RunSettings`.
- Contract identifiers `site_data_climate` and `site_data_soil_slope`.
- Source identifiers `climate_not_connected`, `soil_slope_not_loaded`, and
  `climate` for the entry reported when the climate source is not called.
- The module identifiers listed by the default app: `calendar`, `erosion`,
  `water`, `residues`, `amg`, `rothc` (one per engine folder). Replaced by
  the list of `contracts/ENTRYPOINTS.md`.
- `result_missing` always present as a key, `null` when there is a result.
- The test cases of `api/test_rotations.py` and `api/test_errors.py`.

## OPEN

- **Which years of the climate record are requested?** (science reviewers).
  Until answered, no period is configured and the climate is reported
  unavailable.
- **Which contract carries the identity of a field** (`case_id`, `field_id`),
  and so replaces `SiteReference`?
- **How is the point (latitude, longitude) chosen for a field?** (already
  OPEN in `adapters/ports.py`).
- **Which engine modules exist and with which identifiers?** (to be fixed in
  `contracts/ENTRYPOINTS.md`).
