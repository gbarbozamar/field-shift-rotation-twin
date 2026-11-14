# Soil-loss entry point, mechanical form

Unit `l0/erosion-entrypoint` (issue #115): entry point EP1 of `contracts/ENTRYPOINTS.md`, `compute_soil_loss`, in `engine/erosion/soil_loss.py`, exported by `engine/erosion/__init__.py`.

> **Status: PROPOSED** (blueprint section 3.7). The order of the checks, the reason code of each value, the format of every `detail`, the reading of C5.5 for months and the test cases below were written by a builder session. They take effect only when a person approves the pull request. Items under [OPEN](#open) need an answer from a person.

**This unit computes nothing.** It lays out the agricultural years of the climate record and their months, and returns every annual and monthly value as missing with the reason that applies. It computes no factor, reads no parameter, calls neither `equation.py` nor `ls.py`, and returns no number. It holds no coefficient, no default and no stand-in number: not in the code, not in a test, not in this file.

Acceptance test, from the repository root:

```bash
py -3.12 -m pytest engine/erosion/test_soil_loss.py
```

## Signature

```text
compute_soil_loss(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
) -> SoilLossResults | Missing
```

As EP1 is written on `main`. The models are imported only as `contracts.inputs.<module>` and `contracts.results.models`; `Missing` is the one of `contracts/results/models.py`. The runner in `api/engines.py` finds the function as `engine.erosion.compute_soil_loss` and calls it with the three keyword arguments; nothing in `api/` changes.

The argument `parameters` of decision D46 of issue #77 is **not** added: it waits for the platform developer's agreement. Until then the entry point reads no parameter (G1), and every factor that needs one is missing with a detail that names D46.

## Decisions this unit applies

Decisions of the lead developer, recorded in issue #77. They are cited, not reopened.

| Decision | What this unit does with it |
|---|---|
| D47, agricultural years (Q5 of `contracts/ENTRYPOINTS.md`) | Every agricultural year of the climate record, cut by the start month of the case. The record is the daily series with quantity `precipitation`: every agricultural year (C5.3) that has at least one day between that series' `start_date` and `end_date` is laid out, identified by the calendar year in which it begins. The dates come from the series; the years of D29 are not written in code. The calendar's own dates do not choose the years: a calendar whose dates lie outside the record runs on the years of the record |
| D47, rotation repeated over the years | **Not implemented.** This unit computes no cover-management factor, so it has nothing to repeat. OPEN for the cover-management unit (OPEN 2) |
| D23, source of daily precipitation | The quantity identifier `precipitation`, the only climate series the soil-loss method reads (`docs/METHODS.md` M1.2). It is the one string of the climate vocabulary written in `soil_loss.py` |
| D46, parameters passed by the runner | Not applied yet: waiting for the platform developer's agreement. The signature stays `(calendar, climate, soil_slope)` |
| D7, start month required (Q4) | Decided, not implemented yet: on `main` the route has no check that rejects a request without a start month (`api/README.md` says such a request "will be invalid"), and `RotationCalendar` still accepts a missing start month. So EP1 keeps the answer it has on `main`: one `Missing`, see below and OPEN 7 |
| D12 and D31, meaning of `NOT_AVAILABLE` | Used only for a part that is not built: the monthly erosivity fraction of `R` and the cover-management unit of `C` |
| D4, D10, D45, D48 | Cited in the detail of `P`, `K`, `C` and `K` respectively, as the facts of each factor |

## What the function does, in order

1. **Types (G5).** An argument that is not an instance of its model raises `TypeError`, naming the argument.
2. **One field (G5).** When `climate` or `soil_slope` names another `case_id` or `field_id` than `calendar`, `ValueError`, naming the identifier fields that differ, never their values.
3. **Start month (EP1, Q4).** When `calendar.ag_year_start.month` is missing: one `Missing`, reason `MISSING_INPUT`, `detail` names the start month.
4. **Precipitation series (G4, third row; D47).** When `climate.daily_series` has no item with quantity `precipitation`: one `Missing`, reason `MISSING_INPUT`, `detail` names `precipitation`. The agricultural years cannot be laid out without it, and `SoilLossResults` needs at least one year.
5. **Years and months (C5.3, D47).** From the agricultural year that holds the series' `start_date` to the one that holds its `end_date`, each with its twelve calendar months starting at `calendar.ag_year_start.month` in calendar year `ag_year`.
6. **Reason of each value**, the first row that applies:

| Situation | Reason | Convention |
|---|---|---|
| The calendar is infeasible (`feasibility.feasible` is false) | `NOT_COMPUTABLE`, for every annual and monthly value | G4, first row |
| The `precipitation` series does not cover the agricultural year from its first day to its last | `NO_COVERAGE`, for the annual value | C5.5 |
| The `precipitation` series does not cover the calendar month from its first day to its last | `NO_COVERAGE`, for the monthly value (**PROPOSED**: C5.5 speaks of yearly values only) | C5.5, OPEN 5 |
| Every other value | `MISSING_INPUT`, with the factor detail below | C3.3, G4 second row |

Every value keeps `indicator`, `direction` and `unit` (C3.1), taken from `contracts/results/models.py`: the indicator identifier from the `Literal` of `AnnualSoilLoss.indicator`, the direction from `DIRECTION_OF`, the units from `UNIT_SOIL_LOSS_ANNUAL` and `UNIT_SOIL_LOSS_MONTHLY`. A missing value carries no provenance, no source, no range and no `range_missing` (the model forbids them).

A month of an agricultural year that is not covered whole can itself be covered: its value is then `MISSING_INPUT`, like the months of a full year.

## What each factor reports

The detail of every `MISSING_INPUT` value names each of the five factors of `docs/METHODS.md` M1.1 with its own reason code of C3.2 and why. The facts come from the brief of issue #115; the wording is the session's.

| Factor | Code | Why |
|---|---|---|
| `R` | `MISSING_INPUT` | The mean annual level is carried by no input contract (question 10 of `contracts/inputs/README.md`) |
| `R` | `NOT_AVAILABLE` | The monthly erosivity fraction is a unit that is not built (blueprint section 8, Block 1) |
| `K` | `MISSING_INPUT` | Carried by no input contract (question 16 of `contracts/inputs/README.md`); its source is decided (D10, D48), not its path |
| `LS` | `MISSING_INPUT` | The parameters are not passed to the entry point yet (D46, waiting for the platform developer's agreement) |
| `LS` | `MISSING_INPUT` | The unit of `slope_steepness` and `slope_length` is not mapped to `SlopeUnit` of `engine/erosion/ls.py` (question 18 of `contracts/inputs/README.md`, OPEN 1 of `LS.md`). The code is PROPOSED: OPEN 4 |
| `LS` | the input's own code | Only when `slope_steepness` or `slope_length` is itself missing in `SiteSoilSlope`: one item per missing input, with its reason code and its detail |
| `C` | `MISSING_INPUT` | The calendar carries no period for cover management (`engine/calendar/README.md` P7) |
| `C` | `NOT_AVAILABLE` | The cover-management unit is not built (`docs/METHODS.md` M1.5, D45, blueprint section 8, Block 2) |
| `P` | `MISSING_INPUT` | The support practice is not among the arguments of EP1 (`docs/METHODS.md` M1.6, question 4 of `contracts/inputs/README.md`, D4) |

### Format of `detail` (PROPOSED)

English, for developers.

- Factors: `soil loss needs the factors R, K, LS, C, P, none is available: <item>; <item>; ...`, with each item written `<factor> <CODE>: <why>`, in the order of the table above. A missing slope input is written `LS <CODE>: <name> is missing in the soil-and-slope data[: <detail of the input>]`.
- Infeasible calendar: one fixed text that says the calendar is infeasible and cites G4.
- Not covered: `the daily series 'precipitation' does not cover agricultural year <ag_year> from its first day to its last (C5.5)`, or `... the month <YYYY-MM> ...` for a month.
- The two single `Missing`: one fixed text each, naming the start month or `precipitation`.

## Numbers in the module

`soil_loss.py` holds two integers, both for month arithmetic, and no other number. A test reads the module and fails on any other number, and on any format specification in an f-string (where a width such as `04d` would hide one); the month in a detail is written with `strftime("%Y-%m")`:

| Integer | Where | Why |
|---|---|---|
| `12` | `_MONTHS_IN_A_YEAR` | Twelve calendar months to a year and to an agricultural year (C5.1, C5.3) |
| `1` | `_FIRST` | Months and days are counted from one (C5.1): the first day of a month, a step of one day, one month later, the year before the start month, and the last year of an inclusive range |

The test file uses the same two integers for the same arithmetic, the integer `2` to lay out a span of several agricultural years, `0` as a position counter, and list positions (`0`, `-1` and slices) to pick the first and last year or month. Its daily values repeat the items of the example series; it writes no value.

## PROPOSED cases

The identifier is the name of the test function in `test_soil_loss.py` without `test_`, with hyphens. A test checks that this list and the test functions agree.

| Case | What it checks |
|---|---|
| `examples-with-several-agricultural-years-load-into-soil-loss-results` | From the examples, with a `precipitation` series spanning several agricultural years: one `AnnualSoilLoss` per agricultural year of D47 and twelve consecutive `MonthlySoilLoss` per year, starting at `calendar.ag_year_start.month` in calendar year `ag_year`; indicator, direction and unit from the constants of `contracts/results/models.py`; the round trip through `model_dump(mode="json")` loads back equal |
| `start-month-missing-returns-one-missing-input` | A missing start month: one `Missing`, reason `MISSING_INPUT`, detail names the start month (EP1 as written on `main`) |
| `infeasible-calendar-makes-every-value-not-computable` | An infeasible calendar: every annual and monthly value missing, reason `NOT_COMPUTABLE` (G4, first row), also for years the series does not cover |
| `year-or-month-not-covered-by-precipitation-is-no-coverage` | A series that starts and ends inside agricultural years: those years are `NO_COVERAGE` (C5.5); each month the series does not cover is `NO_COVERAGE` and each month it covers is `MISSING_INPUT`, also inside a year that is not covered whole (PROPOSED) |
| `series-one-day-short-at-each-end-leaves-first-and-last-not-covered` | A series from one day after the first day of an agricultural year to one day before the last day of a later one: the first and last agricultural years, and the first and last months, are `NO_COVERAGE`; every year and month between is `MISSING_INPUT` (C5.5; the boundaries of `_covers` and of the last day of a month) |
| `calendar-dates-outside-the-record-keep-the-years-of-the-record` | A calendar moved past the last day of the record: the years are still those of the record, and the result equals the one with the example calendar (D47) |
| `no-precipitation-series-returns-one-missing-input` | No `precipitation` series: one `Missing`, reason `MISSING_INPUT`, detail names `precipitation` (G4, third row) |
| `every-other-value-is-missing-input-naming-each-factor` | Every other value is `MISSING_INPUT`; its detail names `R`, `K`, `LS`, `C` and `P`, each with the codes and the facts of the table above; `NOT_AVAILABLE` only for a part that is not built |
| `missing-slope-input-is-named-in-the-ls-item` | `slope_steepness`, `slope_length` or both missing in `SiteSoilSlope`: each is named in an `LS` item with its own reason; one that is present is not named |
| `no-value-is-a-number-and-none-is-zero` | Over every case above: no value is a number, none is zero, every value has a `missing` part with a code of C3.2, and every code in a factor detail is of C3.2 |
| `arguments-of-another-case-or-field-raise-value-error` | `case_id` or `field_id` of `climate` or `soil_slope` differs from the calendar: `ValueError` naming the field (G5) |
| `argument-that-is-not-its-model-raises-type-error` | An argument given as a dictionary, or as an instance of another model: `TypeError` naming the argument (G5) |
| `arguments-unchanged-and-second-call-equal` | The arguments are equal to a deep copy taken before the call, and a second call gives an equal result (G1) |
| `module-imports-only-allowed-modules-and-holds-only-month-integers` | `soil_loss.py` imports only the standard library, `contracts.inputs.*` and `contracts.results.models`, holds no number except `12` and `1`, and has no format specification in an f-string |
| `package-exposes-compute-soil-loss-with-exactly-three-parameters` | `from engine.erosion import compute_soil_loss` works and its parameters are exactly `calendar`, `climate`, `soil_slope` |
| `proposed-cases-match-soil-loss-md` | This list and the test functions agree |

## OPEN

Each item is a question a person has to answer, with the role that answers it. None is answered by this unit.

1. **Days missing inside the `precipitation` series.** G4 and C3.3 make a value computed from missing days `MISSING_INPUT`, and C3.4 leaves the gap-filling method OPEN. This unit computes nothing from the days, so it does not look at them: a covered year with missing days reports the factor detail, not the missing days. When the monthly erosivity fraction is built, it has to apply this rule. For the lead developer (when), the science reviewers (the method of C3.4).
2. **Repeating the rotation over the years of the record (D47).** Not implemented: nothing here uses the calendar's components. How the calendar's dates are laid onto each agricultural year belongs to the cover-management unit (`docs/METHODS.md` M1.5, D45). For the lead developer.
3. **The argument `parameters` (D46).** Not added. When the platform developer agrees, the signature and the runner change together, and the detail of `LS` (and of `R` and `C` once they are built) stops citing D46. For the platform developer, then the lead developer.
4. **Reason code for the slope unit that is not mapped.** The `LS` item uses `MISSING_INPUT`: the mapping is an input a person has to supply. Q11 of `contracts/ENTRYPOINTS.md` names `NOT_COMPUTABLE` and `CONTROL_FAILED` for a unit that is not accepted, which is a different case. For the lead developer.
5. **Months not covered by the series.** C5.5 speaks of yearly values. This unit also writes `NO_COVERAGE` for a month the series does not cover from its first day to its last, as the brief asks, and `MISSING_INPUT` for a covered month of a year that is not covered whole. For the lead developer.
6. **Precedence of the reasons.** Infeasible calendar first, then coverage, then the factors; and of the two single `Missing`, the start month before the series. The brief and the conventions imply this order but do not state it. For the lead developer.
7. **With the calendar engine of today, EP1 always returns one `Missing`.** `engine/calendar/README.md` P6: the calendar engine writes the start month as missing (`NOT_DECLARED`) until the rotation definition carries it (D8). Through the route, the erosion module is therefore `not_available`, `MISSING_INPUT`, with no `soil_loss`, until that unit lands. Whether the return type of EP1 changes after D7 is not said by issue #77. For the lead developer and the platform developer.
8. **The day boundaries of an agricultural year.** Years and months are cut on the dates of the series, in its time zone (C6.1; UTC for the NASA POWER adapter, C6.2), not on the local day at the field (C6.5). For the science reviewers.
9. **Where the identifier `precipitation` lives.** It is written once in `soil_loss.py`, from D23 and `contracts/CLIMATE_QUANTITIES.md`. Whether contracts should export the quantity identifiers as constants, so that an engine and an adapter cannot spell them differently. For the lead developer and the platform developer.
10. **Example data (Q16).** The inputs carry `example_data`; `SoilLossResults` has no field for it, so this unit cannot pass the mark on. For the lead developer and the platform developer.
11. **Who reads `detail`.** The format above is for developers. If the interface shows it, its wording belongs to the strings file of `web/` and to people (CLAUDE.md: the wording of claims). For the interface developer and the lead developer.
