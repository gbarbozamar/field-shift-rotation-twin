# Data adapters

Sub-lane L2a. One module per data source. Network calls happen only here, and never during tests.

Today there is one adapter: NASA POWER, daily values of one point (`power.py`). It implements `ClimateSource` of `ports.py`, the seam with `api/`. `ports.py` is not edited by this unit.

**Status.** The mechanics are built and tested: the request, the file cache of the first response, the failure handling and the mapping into the contract "Site data: climate". Every decision that belongs to a person is a setting with **no default**, listed under [OPEN](#open). Nothing here has been run against the real service. A person makes the first real request.

## What it does

Given a `ClimateRequest` (case, field, one point, a period), `PowerClimateSource.get_climate`:

1. builds the query from the request and the settings only;
2. if the first response to this query is stored, maps it and returns `state="cached"` without contacting the source;
3. otherwise asks the service; on a usable response, stores it, maps it and returns `state="fresh"`;
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

No settings file is committed: every value in it is a decision listed under OPEN.

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

`to_site_climate(raw, request, settings) -> dict` is a pure function. It returns a JSON-ready document in the shape of `SiteClimate` (proposed in `contracts/inputs/`, not merged yet):

- `contract: "site_data_climate"`, `example_data: false`, `case_id`, `field_id` from the request, `monthly_series: []` (aggregation belongs to the engines).
- One daily series per `ParameterSpec`, in the configured order, with `quantity`, `unit`, `provenance`, `source` (= `source_id`), `range_missing: {reason: range_missing_reason}`, `time_zone: "UTC"`, `start_date`, `end_date`, `days`.
- Every day from `start_date` to `end_date` appears once, in order. A day whose value equals `fill_value`, or that the response does not contain, is `{"date", "value": null, "missing": {"reason": fill_reason, "detail"}}`; the two cases have different `detail` texts. Zero is a real value and is never produced for a missing day.
- A series whose days are all missing carries no `provenance`, no `source` and no `range_missing` (C2.2, C4.1).
- Days in the response outside the requested period are not reported.
- No unit conversion.

### Drop-in check

`test_power_mapping.py::test_drop_in_against_the_contract_model` loads the mapper's output into `SiteClimate` through JSON. It uses `pytest.importorskip("contracts.inputs")`: it is **skipped today** and starts running, unchanged, the day `contracts/inputs/` is merged. It was run once by hand against the files of the unmerged branch, outside this worktree, and passed.

## Tests

```bash
uv run pytest adapters/
```

No network: `httpx.MockTransport` for the service, `tmp_path` for the cache, a fixed clock. Fake responses are built in the layout of the scout report, with placeholder parameter codes, placeholder numbers (1.0, 2.0, 3.0), a placeholder fill value and dates in the year 1900. `_fakes.py` holds the shared builders; it is not used at run time.

## PROPOSED

Designed by the builder session; a person accepts or corrects them in the pull request.

1. The structure: `PowerSettings` with no defaults, `ParameterSpec`, `PowerSettings.from_mapping`, the injected `ResponseCache`, `httpx.Client` and clock.
2. The cache layout above: key, one JSON file per key with `body`, `query`, `retrieved_at`; first response wins; atomic write; corrupt entry treated as absent; only usable responses stored.
3. The query: parameter codes sorted (so the configured order does not change the query or the cache key); coordinates as shortest round-trip decimal text; `format=JSON` sent explicitly; argument order as in the table.
4. `optional_arguments`: a required setting (may be empty) limited to `units`, `site-elevation`, `wind-elevation`, `wind-surface`, so that a reviewers' choice on those arguments arrives as configuration. Not in the plan's settings table; added so that the service default (for example of `units`) is never a hidden decision.
5. The failure-to-reason mapping: every failure in the table is `SOURCE_UNAVAILABLE`, including an error payload (see OPEN 12).
6. What counts as an error payload: a JSON object without `properties` and with a non-empty `messages` list. A response that has the data layout is used whatever its `messages` say (see OPEN 13).
7. A response whose `header.fill_value` differs from the configured `fill_value` is unusable; a response without `header` or without `header.fill_value` is accepted.
8. A value that is not a finite number (text, null, true/false, infinity) makes the whole response unusable rather than one missing day.
9. Days outside the requested period are ignored.
10. One `fill_reason` for both a fill value and an absent day, with two different `detail` texts.
11. A cache write that fails still returns the fresh data, with a `detail`.
12. A stored entry that cannot be mapped returns `unavailable` and is kept.
13. `base_url` must be https.
14. `SourceInfo` of an unavailable result still carries `time_zone`, `request` and `attribution`.
15. The test cases in `test_cache.py`, `test_power.py`, `test_power_mapping.py`.
16. Concurrency: two processes asking for the same key at the same moment may both fetch; the cache keeps one entry (the last rename of the two simultaneous first writers). Not designed further.

## OPEN

Each item is a question a person answers. Until then the setting has no value and the adapter is not constructed for real.

1. **Which parameters are requested, and with which quantity identifier, unit string and provenance label each?** (`parameters`.) For the science reviewers; quantity identifiers with the lead developer. The scout report lists candidates and does not choose.
2. **Which community?** (`community`.) It fixes the units of some parameters and which parameters are offered. For the science reviewers.
3. **Does the unit of each source parameter, in the chosen community, equal the configured unit string?** The adapter does not convert. A person checks it against the service. For the science reviewers.
4. **Which optional arguments are sent, if any (`units`, `site-elevation`, `wind-elevation`, `wind-surface`)?** (`optional_arguments`; empty sends none and the service defaults apply.) For the science reviewers.
5. **Which years of record does a case request?** The service documents a first allowed date; the period is chosen by the caller. For the science reviewers and the lead developer.
6. **Which fill value, and which reason code does it become?** The scout report quotes `-999`; a person confirms. Should the reason differ for a gap inside the record, a day before a source starts and a day after the latest available day? Today one `fill_reason` covers all, and an absent day too. For the science reviewers.
7. **How does the service bound a UTC day for each variable?** The scout report did not find it stated (NOT FOUND); daily extremes are described for the local solar day. For the science reviewers, citation needed (C6.2).
8. **Does IMERG precipitation come through this service or directly from its own source?** For the science reviewers.
9. **Which reason code goes in `range_missing`?** (`range_missing_reason`.) For the lead developer.
10. **How does a field polygon become one point?** `ClimateRequest` carries one point; how it is chosen is OPEN in `ports.py`. For the lead developer and the science reviewers.
11. **May a recorded real response be committed (for a test or for `demo/`)?** None is. For the platform developer and the lead developer.
12. **Is an error payload from the service `SOURCE_UNAVAILABLE`, or another reason?** C3.2 is closed and says "did not answer". Proposed: `SOURCE_UNAVAILABLE`. For the lead developer.
13. **What does an error payload of the service look like, and does a non-empty `messages` list on a response with data mean the data is unusable?** The scout report documents `messages: []` and the status codes, not their content. For the platform developer, after a first real request.
14. **Does the deploy host keep files between restarts?** If not, `FileCache` loses its entries on restart and another `ResponseCache` is needed. For the platform developer.
15. **What is the base URL?** The scout report documents the path `/api/temporal/daily/point` and that the specification is served from the service's host; a person confirms the full URL. (`base_url`.) For the science reviewers and the platform developer.
16. **What are `attribution`, `source_id` and `timeout_seconds`?** The `ATTRIBUTIONS.md` data row for NASA POWER is written by a person when the data is first used for real. For the platform developer.
17. **What does the adapter do on status 429 (too many requests)?** Today it is one failure like any other; the next call tries again. No retry and no back-off. For the platform developer.
18. **Should the place the source answered for (grid cell, elevation in the response) travel with the data?** The contract has no field for it (contracts/inputs OPEN 21). For the platform developer and the lead developer.
