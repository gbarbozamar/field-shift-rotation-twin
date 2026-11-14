# Data adapters

Sub-lane L2a. One module per data source. Network calls happen only here, and never during tests.

Two sources today:

- NASA POWER, daily values of one point (`power.py`). It implements `ClimateSource` of `ports.py`, the seam with `api/`.
- The accepted soil-and-slope contract example (`example_soil_slope.py`). It implements `SoilSlopeSource` of `ports.py`.

## The seam (`ports.py`)

Unit `l2/engine-runner` owned both sides of the seam and made exactly these changes (**PROPOSED**), updating every implementation, stand-in, fake and test:

1. **A source describes itself without a call.** `ClimateSource` and `SoilSlopeSource` have two read-only attributes, `source_id` and `contract`: the values the source writes as `SourceInfo.id` and `SourceInfo.contract`. The route uses them for the `sources` entry when it does not call the climate source (no period configured).
2. **`retrieved_at` carries its time zone.** `SourceInfo` rejects a `retrieved_at` that is not a datetime with a time zone (`ValueError`).
3. **`missing_reason` is enforced.** It is typed as the C3.2 `ReasonCode` of `contracts.inputs.common`; `SourceInfo` requires it when `state == "unavailable"`, forbids it with any other state, and rejects a code outside C3.2.
4. **`SoilSlopeSource` and `SoilSlopeResult` live here**, next to the climate ones. `api/ports.py` re-exports them.

The payload aliases are the contract models: `ClimatePayload` is `contracts.inputs.SiteClimate`, `SoilSlopePayload` is `contracts.inputs.SiteSoilSlope`. Contract models are imported only as `contracts.inputs` (and `contracts.results`), never by a short name.

**Status.** The mechanics are built and tested: the request, the file cache of the first response, the failure handling and the mapping into the contract "Site data: climate". Every decision that belongs to a person is a setting with **no default**, listed under [OPEN](#open). Nothing here has been run against the real service. A person makes the first real request.

## What it does

Given a `ClimateRequest` (case, field, one point, a period), `PowerClimateSource.get_climate`:

1. builds the query from the request and the settings only;
2. if the first response to this query is stored, maps it and returns `state="cached"` without contacting the source;
3. otherwise asks the service; on a usable response, stores it, maps it and returns `state="fresh"`;

`data` is a `SiteClimate` **instance**: the mapper's document is loaded into the model. A document that does not load is an unusable response: `unavailable`, `SOURCE_UNAVAILABLE`, a `detail` that does not echo the body, and nothing stored. A stored entry that no longer loads is treated like one that cannot be mapped (below).
4. on any failure, returns `data=None`, `state="unavailable"`, `missing_reason="SOURCE_UNAVAILABLE"` and a `detail` in plain English. Nothing is stored, so the next call tries again.

It never raises because of the source. It raises only for a programming error: invalid settings, an impossible request (end before start, a coordinate out of range), or a clock that returns a time without a time zone.

## How to construct it

```python
import json
import httpx
from adapters.cache import FileCache
from adapters.power import PowerClimateSource, PowerSettings

with open("power_settings.json") as handle:  # written by a person
    settings = PowerSettings.from_mapping(json.load(handle))

source = PowerClimateSource(
    settings,
    FileCache("<folder for the cache>"),  # or any other ResponseCache
    httpx.Client(),
)
result = source.get_climate(request)
```

The three parts are replaceable:

- **Settings** come from configuration (`PowerSettings.from_mapping`, for example a parsed JSON file). A missing or unknown key is an error naming it.
- **The cache** is any object with the `ResponseCache` protocol (`get(key)`, `put(key, entry)`). `FileCache` is the one implementation. A host that does not keep files gets another implementation, not a rewrite.
- **The HTTP client** is injected. Tests pass `httpx.Client(transport=httpx.MockTransport(...))`.

An optional keyword `now` supplies the clock (default: the system clock in UTC). Tests fix it.

The shape of the settings file is committed as a template:
[`examples/PLACEHOLDER_power_settings.json`](examples/PLACEHOLDER_power_settings.json).
**Every value in it is a placeholder** (including the provenance label and the
reason codes, which only have to be members of their closed lists so that the
file loads); it is never a usable configuration, and its base URL under
`https://power.invalid/` never resolves. A person copies it outside the
repository and writes the values decided under OPEN. `test_settings_file.py`
loads it with `PowerSettings.from_mapping`, so the documented shape cannot
drift from the code. The running app reads the file named by
`POWER_SETTINGS_FILE` (see `api/README.md`, "Configuration").

## Settings

`PowerSettings` and `ParameterSpec` are frozen dataclasses. **No field has a default.** Construction without one is an error naming it; an empty or invalid value is an error naming it.

| Setting | Meaning | Checked at construction | Decided by |
|---|---|---|---|
| `base_url` | Endpoint of the daily point API | https URL, no query, no fragment | Science reviewers confirm; the scout report documents the path |
| `community` | The `community` argument | non-empty text | Science reviewers |
| `parameters` | One `ParameterSpec` per requested variable | at least one; no source parameter and no quantity twice | Science reviewers |
| `ParameterSpec.source_parameter` | The source's parameter code | one code, no spaces or commas | Science reviewers |
| `ParameterSpec.quantity` | Quantity identifier in the contract | lower case with underscores (C1.1) | Science reviewers, lead developer |
| `ParameterSpec.unit` | Unit string written in the contract | non-empty text | Science reviewers |
| `ParameterSpec.provenance` | `DECLARED`, `OBSERVED`, `DERIVED` or `SIMULATED` | one of the four (C4.1) | Science reviewers |
| `optional_arguments` | Optional arguments of the service to send (`units`, `site-elevation`, `wind-elevation`, `wind-surface`); an empty mapping sends none | only those four names; `user` and the arguments the adapter builds are refused | Science reviewers |
| `point` | How the point of the series is written: `latitude_unit`, `longitude_unit`, `elevation_unit` (unit strings) and `provenance` (one of the four labels). The numbers come from the response | mapping, all four required | Science reviewers (`contracts/inputs/README.md`, questions 25 and 26) |
| `fill_value` | The number the source uses for "no data" | finite number | Scout report; science reviewers confirm |
| `fill_reason` | C3.2 code a fill value or an absent day becomes | a C3.2 code | Science reviewers |
| `range_missing_reason` | C3.2 code written in `range_missing` | a C3.2 code | Lead developer |
| `attribution` | Reference to the `ATTRIBUTIONS.md` entry | non-empty text | A person writes the entry |
| `source_id` | Stable identifier of this source, written as `source` of each series and as `id` in `SourceInfo` | non-empty text | Platform developer |
| `timeout_seconds` | Request timeout | finite, greater than zero | Platform developer |

The time standard is **not** a setting. Series from this adapter are UTC (C6.2): the query always carries `time-standard=UTC` and every series says `time_zone: "UTC"`.

## The query

Built from the request and the settings only, always in this order:

| Argument | Value |
|---|---|
| `parameters` | the configured source codes, **sorted**, joined by commas |
| `community` | `community` |
| `latitude`, `longitude` | the request's coordinates, as the shortest decimal text that reads back as the same number |
| `start`, `end` | the request's dates, `YYYYMMDD` |
| `format` | `JSON` |
| `time-standard` | `UTC` |
| then | `optional_arguments`, sorted by name |

No user identifier, no `user` argument, no header that carries a name, no key. `SourceInfo.request` is this query.

## The cache (`cache.py`)

- **Key:** SHA-256 hex digest of the canonical JSON (sorted keys, no whitespace) of `{source_id, base_url, query}`. The adapter derives it; `FileCache` refuses any key that is not 64 lower-case hex characters, so no caller-supplied text reaches a file name.
- **One file per key:** `<folder>/<key>.json`, holding `body` (the response body as received, as text), `query` and `retrieved_at` (ISO 8601, UTC).
- **First response wins.** `put` on a key with a readable entry keeps that entry and returns it.
- **Atomic write:** a temporary file (`.<key>.<random>.tmp`) in the same folder, flushed and synced, then renamed over the entry. A failed write removes its temporary file.
- **A corrupt or unreadable entry** (truncated, not JSON, not UTF-8, wrong fields, time without zone) is absent; the next successful fetch replaces it.
- The folder is passed in and created on first write. Nothing is written elsewhere.
- **Only a usable response is stored:** it must parse and map completely before it is written.

## Failures

Every row returns `data=None`, `state="unavailable"`, `missing_reason="SOURCE_UNAVAILABLE"`, stores nothing and does not raise. The `detail` never echoes the response body.

| Failure | `detail` |
|---|---|
| Timeout (connect, read, write, pool) | the source did not answer in time |
| Connection or other transport error | the source could not be reached |
| Any other request error of the client | the request to the source failed |
| Status other than 2xx (including 422, 429, 500, 503, 404, and 3xx: the default client does not follow redirects) | the source answered with HTTP status *n* |
| Body that is not JSON, or JSON with `NaN` or `Infinity` | the response body is not JSON |
| JSON object with no `properties` and a non-empty `messages` list | the source answered with an error message instead of data |
| JSON without the expected layout: not an object, no `properties.parameter`, a configured parameter absent, a value that is not a finite number, a date key that is not a strict `YYYYMMDD` calendar date, a `header.fill_value` other than the configured one | the response does not have the expected layout: *what is wrong* |

Two further cases, not failures of the source:

| Case | Result |
|---|---|
| The response is usable but the cache cannot write it (`OSError`) | `state="fresh"` with the data and a `detail` saying it was not stored; the next call asks the source again |
| A stored entry parses but cannot be mapped (the file was changed by hand) | `state="unavailable"`, `SOURCE_UNAVAILABLE`, and a `detail` saying so; the entry is kept, the source is not asked |

## The mapping (`power_mapping.py`)

`to_site_climate(raw, request, settings) -> dict` is a pure function. It returns a JSON-ready document in the shape of `SiteClimate` (`contracts/inputs/site_climate.py`, on `main` as a proposal); `PowerClimateSource` loads it into that model and returns the instance:

- `contract: "site_data_climate"`, `example_data: false`, `case_id`, `field_id` from the request, `monthly_series: []` (aggregation belongs to the engines).
- One daily series per `ParameterSpec`, in the configured order, with `quantity`, `unit`, `provenance`, `source` (= `source_id`), `range_missing: {reason: range_missing_reason, detail}`, `time_zone: "UTC"`, `start_date`, `end_date`, `days`.
- Every `missing` and `range_missing` part the mapper writes carries a non-empty English `detail`. Without it, a legal setting such as `MISSING_INPUT` (for which C3.2 asks a detail) gave a document that does not load. A test maps a response with every code of C3.2 as `fill_reason` and as `range_missing_reason` and loads each document into `SiteClimate`: all sixteen load, so no code is refused at construction of `PowerSettings`.
- Every day from `start_date` to `end_date` appears once, in order. A day whose value equals `fill_value`, or that the response does not contain, is `{"date", "value": null, "missing": {"reason": fill_reason, "detail"}}`; the two cases have different `detail` texts. Zero is a real value and is never produced for a missing day.
- A series whose days are all missing carries no `provenance`, no `source` and no `range_missing` (C2.2, C4.1).
- Days in the response outside the requested period are not reported.
- No unit conversion.

### The point of the series

Decisions D9 and D18 of issue #77: the record carries the point its series are valid for, and it is what the response of the source reports, never the point of the request. The response is a GeoJSON feature; `geometry.coordinates` holds longitude, latitude and elevation, in that order.

- Each of the three becomes a value with its unit string (`point` settings), the label of `point.provenance`, the source `source_id`, and `range_missing` with `range_missing_reason` and a detail.
- A part the response does not report, or that is not a finite number, is missing with `fill_reason` and a detail. A response without `geometry` gives three missing values; the series are still mapped.
- An elevation equal to the fill value is missing; a real zero stays zero.
- No unit is converted and no bound is checked.

### Drop-in check

`test_power_mapping.py::test_drop_in_against_the_contract_model` loads the mapper's output into `SiteClimate` through JSON. It is an ordinary test now that `contracts/inputs/` is on `main`.

## The soil-and-slope example (`example_soil_slope.py`)

`ExampleSoilSlopeSource(path, *, source_id="soil_slope_example")` implements `SoilSlopeSource`:

- `path` is required and has **no default**. Which file is "the accepted example" is a person's decision, so the running app serves it only when `SOIL_SLOPE_EXAMPLE_FILE` names the file (`api/README.md`, "Configuration"). Tests use `contracts/inputs/examples/PLACEHOLDER_site_soil_slope.json`.
- Each call reads the file and loads it into `SiteSoilSlope`, with `state="example"` and no `retrieved_at`. The route shows it as `sources[].state == "example"` next to the result (decision Q16).
- **The example serves any field (decision D38 of #77).** The document returned carries the `case_id` and `field_id` of the request: a new model instance, validated again, with those two fields replaced. Everything else is the file's, unchanged; `example_data` stays true; the file is never written. The engine runner still compares identifiers (D14); with this source they always match, so "site data of another field" is reached only by a source that does not rewrite.
- A file that is absent or cannot be read, that does not load into the model, or whose `example_data` is false gives `data=None`, `unavailable`, `NOT_AVAILABLE` and a `detail`. It never raises for the file. Requested identifiers the model refuses (blank text) give the same answer with their own `detail` (PROPOSED).
- `contract` is read from the `contract` field of `SiteSoilSlope`.

## Tests

```bash
uv run pytest adapters/
```

No network: `httpx.MockTransport` for the service, `tmp_path` for the cache, a fixed clock. Fake responses are built in the layout of the scout report, with placeholder parameter codes, placeholder numbers (1.0, 2.0, 3.0), a placeholder fill value and dates in the year 1900. `_fakes.py` holds the shared builders; it is not used at run time.

## PROPOSED

Designed by the builder sessions; a person accepts or corrects them in the pull request.

Unit `l2/runner-partial`:

- How the example source writes the identifiers of the request (a new instance validated again), and the answer `unavailable` / `NOT_AVAILABLE` with the detail "the requested case_id or field_id is refused by the contract model SiteSoilSlope" for identifiers the model refuses.
- The new test cases in `test_example_soil_slope.py`.

Unit `l2/app-config`:

- The template `examples/PLACEHOLDER_power_settings.json` and `test_settings_file.py`.

Unit `l2/engine-runner`:

- The four seam changes listed under "The seam".
- A mapped document that does not load into `SiteClimate` is unusable (`SOURCE_UNAVAILABLE`, nothing stored).
- The `detail` texts the mapper writes in `range_missing` ("the source gives no uncertainty range for this series").
- `ExampleSoilSlopeSource`: the source identifier `soil_slope_example`, the reason `NOT_AVAILABLE` and the `detail` texts of its three failures, reading the file on each call.
- The test cases in `test_ports.py` and `test_example_soil_slope.py`, and the new cases in `test_power.py` and `test_power_mapping.py`.

Unit `l2/power-adapter`:

1. The structure: `PowerSettings` with no defaults, `ParameterSpec`, `PowerSettings.from_mapping`, the injected `ResponseCache`, `httpx.Client` and clock.
2. The cache layout above: key, one JSON file per key with `body`, `query`, `retrieved_at`; first response wins; atomic write; corrupt entry treated as absent; only usable responses stored.
3. The query: parameter codes sorted (so the configured order does not change the query or the cache key); coordinates as shortest round-trip decimal text; `format=JSON` sent explicitly; argument order as in the table.
4. `optional_arguments`: a required setting (may be empty) limited to `units`, `site-elevation`, `wind-elevation`, `wind-surface`, so that a reviewers' choice on those arguments arrives as configuration. Not in the plan's settings table; added so that the service default (for example of `units`) is never a hidden decision.
5. The failure-to-reason mapping: every failure in the table is `SOURCE_UNAVAILABLE`, including an error payload (decided: D16).
6. What counts as an error payload: a JSON object without `properties` and with a non-empty `messages` list. A response that has the data layout is used whatever its `messages` say (see OPEN 13).
7. A response whose `header.fill_value` differs from the configured `fill_value` is unusable; a response without `header` or without `header.fill_value` is accepted.
8. A value that is not a finite number (text, null, true/false, infinity) makes the whole response unusable rather than one missing day.
9. Days outside the requested period are ignored.
10. One `fill_reason` for both a fill value and an absent day, with two different `detail` texts (decided: D36, `NO_COVERAGE`).
11. A cache write that fails still returns the fresh data, with a `detail`.
12. A stored entry that cannot be mapped returns `unavailable` and is kept.
13. `base_url` must be https.
14. `SourceInfo` of an unavailable result still carries `time_zone`, `request` and `attribution`.
15. The test cases in `test_cache.py`, `test_power.py`, `test_power_mapping.py`.
16. Concurrency: two processes asking for the same key at the same moment may both fetch; the cache keeps one entry (the last rename of the two simultaneous first writers). Not designed further.

### The point of the series

- Decided (D51): a response that reports no point, or only part of one, is still usable: the missing parts are written as missing with `fill_reason`.
- PROPOSED: one reason code (`fill_reason`) covers a part that is not reported and a part reported as the fill value, with two different details.
- Decided (D52): one provenance label for the three values (`point.provenance`).

## Decided

Decisions of issue #77 that settle what earlier units left PROPOSED or OPEN here.

| Decision | What it settles |
|---|---|
| D12 | A part of `ResultsPerRotation` whose engine is not built: the not-built form (written by the runner, `api/README.md`) |
| D13 | The module identifiers are the six engine folder names |
| D14 | The runner compares `case_id` and `field_id` before any engine is called |
| D16 | An error payload of the climate service is `SOURCE_UNAVAILABLE` (was OPEN 12) |
| D17, D43 | One recorded real response may be committed; it is, under `docs/evidence/` (was OPEN 11) |
| D18, D9 | The point of the series travels in "Site data: climate", from the response of the source (was OPEN 18) |
| D19 | Field identity is a new contract; `SiteReference` stays until it is on `main` |
| D20, D37 | The platform developer writes the adapter settings, from accepted values |
| D23 to D35 | The seven series, the community and the period 2001-01-01 to 2024-12-31, as recorded in #77 and `contracts/CLIMATE_QUANTITIES.md` (were OPEN 1, 2 and 5; OPEN 8 for the route of precipitation) |
| D31 | `range_missing_reason`: `NO_COVERAGE` (was OPEN 9) |
| D36 | `fill_reason`: `NO_COVERAGE`, for a fill value and for an absent day (was OPEN 6) |
| D38 | The soil-and-slope example source serves any field, under the identifiers of the request (was OPEN 20; unit `l2/runner-partial`) |
| D51, D52 | A response without a point is usable; one provenance label for the three values of the point |

## OPEN

Each item is a question a person answers. Until then the setting has no value and the adapter is not constructed for real. The numbers of the earlier list are kept, so references to them stay valid; the decided ones are in [Decided](#decided).

**The settings file is not written in this unit.** The values of D23 to D35 are accepted (D37), but `point` is a required setting and its three unit strings and its provenance label are not decided (questions 25, 26 and 28 of `contracts/inputs/README.md`). For the science reviewers, or the lead developer as for D23 to D35. Until then `POWER_SETTINGS_FILE` stays unset.

- OPEN 3: **Does the unit of each source parameter, in the chosen community, equal the configured unit string?** The adapter does not convert. A person checks it against the service. For the science reviewers.
- OPEN 4: **Which optional arguments are sent, if any (`units`, `site-elevation`, `wind-elevation`, `wind-surface`)?** (`optional_arguments`; empty sends none and the service defaults apply.) For the science reviewers.
- OPEN 7: **How does the service bound a UTC day for each variable?** The scout report did not find it stated (NOT FOUND); daily extremes are described for the local solar day. For the science reviewers, citation needed (C6.2).
- OPEN 8: **Which IMERG run does the value of a given day come from?** D23 takes precipitation from NASA POWER; which run of the product a day's value is, and whether it can change later, is not stated here. For the science reviewers.
- OPEN 10: **How does a field polygon become one point?** `ClimateRequest` carries one point; how it is chosen is OPEN in `ports.py`. For the science reviewers (D41, D48).
- OPEN 13: **What does an error payload of the service look like, and does a non-empty `messages` list on a response with data mean the data is unusable?** The scout report documents `messages: []` and the status codes, not their content. For the platform developer, after a first real request.
- OPEN 14: **Does the deploy host keep files between restarts?** D42: a persistent volume is mounted for the cache and its path becomes `CLIMATE_CACHE_DIR`; the path is posted by the lead developer. For the platform developer to set.
- OPEN 15: **What is the base URL?** The scout report documents the path `/api/temporal/daily/point` and that the specification is served from the service's host; a person confirms the full URL. (`base_url`.) For the science reviewers and the platform developer.
- OPEN 16: **What are `attribution`, `source_id` and `timeout_seconds`?** The `ATTRIBUTIONS.md` data row for NASA POWER is written by a person when the data is first used for real. For the platform developer.
- OPEN 17: **What does the adapter do on status 429 (too many requests)?** Today it is one failure like any other; the next call tries again. No retry and no back-off. For the platform developer.
- OPEN 19: **Which file holds the demonstration values of soil and slope?** A person supplies them; the PLACEHOLDER file is for testing the pipeline only (#77), its numbers mean nothing and the engines may reject its units. D48 and D49 bring soil, slope and available water from public data through adapters of this lane, once the elevation model, the polygon-to-point rule and the licence of D49 are settled. For the science reviewers, the lead developer and the platform developer.
- **D46, the argument `parameters`:** agreed by the platform developer, waiting for `contracts/ENTRYPOINTS.md` to state it. No adapter change.
