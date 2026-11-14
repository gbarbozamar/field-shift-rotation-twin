# Water entry point, mechanical form

Unit `l1/water-entrypoint` (issue #134): entry point EP3 of `contracts/ENTRYPOINTS.md`, `compute_water_deficit_exposure`, in `engine/water/exposure.py`, exported by `engine/water/__init__.py`. It follows the precedent of EP1 (`engine/erosion/soil_loss.py`, `engine/erosion/SOIL_LOSS.md`, issue #115).

> **Status: PROPOSED** (blueprint section 3.7). The order of the checks, the reason code of each item, the time basis of each case, the format of every `detail`, the choices under [PROPOSED choices](#proposed-choices) and the test cases below were written by a builder session. They take effect only when a person approves the pull request. Items under [OPEN](#open) need an answer from a person.

**This unit computes nothing.** It lays out the agricultural years of the climate record and returns one item per year, each missing with the reason that applies. It returns no number. It holds no coefficient, no default and no stand-in number: not in the code, not in a test, not in this file. `engine/water/et0/` and `engine/water/balance/` are imported, not changed.

Acceptance test, from the repository root:

```bash
py -3.12 -m pytest engine/water/
```

## Signature

```text
compute_water_deficit_exposure(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
) -> list[WaterDeficitExposure]
```

As EP3 is written on `main`. The models are imported only as `contracts.inputs.<module>` and `contracts.results.models`; `Missing` is the one of `contracts/results/models.py`; no new missing shape is defined. The runner in `api/engines.py` finds the function as `engine.water.compute_water_deficit_exposure` and calls it with the three keyword arguments; nothing in `api/` changes.

The argument `parameters` of decision D46 of issue #77 is **not** added. D56 accepted the platform developer's conditions, the first of which is that `contracts/ENTRYPOINTS.md` states the argument before any engine uses it; that lane L0 pull request has not landed. Until then the entry point reads no parameter (G1), and every value that needs one is missing with a detail that names D46.

## What it returns

Always a list with at least one item, and no item is a number. Every item keeps `indicator`, `direction` and `unit` (C3.1), read from `contracts/results/models.py`: the identifier from the `Literal` of `WaterDeficitExposure.indicator`, the direction from `DIRECTION_OF`, the unit from `UNIT_WATER_DEFICIT_EXPOSURE`. A missing item carries no provenance, no source, no range and no `range_missing` (the model forbids them).

| Case | What is returned |
|---|---|
| `calendar.ag_year_start.month` is missing | One item, `time_basis: "rotation"`, reason `MISSING_INPUT`, detail names the start month (PROPOSED, see below) |
| `climate.daily_series` has no `precipitation` series | One item, `time_basis: "rotation"`, reason `MISSING_INPUT`, detail names `precipitation` (PROPOSED) |
| Otherwise | One item per agricultural year of the record (D47), `time_basis: "ag_year"`, with its `ag_year`, each missing with the first reason of the table below |

Reason of each yearly item, the first row that applies:

| Situation | Reason | Convention |
|---|---|---|
| The calendar is infeasible (`feasibility.feasible` is false) | `NOT_COMPUTABLE`, every year | G4, first row |
| The daily series the water engine reads that are present do not share one time zone | `NOT_COMPUTABLE`, every year | C6.3; G4, sixth row |
| A series the water engine reads that is present does not cover the year from its first day to its last | `NO_COVERAGE`; detail names each such series | C5.5 |
| Every other year | `MISSING_INPUT`; detail names every input that is missing and what each part needs (below) | C3.3; G4, second to fourth rows; D56 |

The daily series the water engine reads are `precipitation` (D23; the precipitation of each day of the balance) and the five inputs of the reference evapotranspiration, whose identifiers are read from `CLIMATE_QUANTITIES` of `engine/water/et0/quantities.py` (D25 to D27, D35).

### Format of `detail` (PROPOSED)

English, for developers. A `MISSING_INPUT` yearly item reads `water_deficit_exposure needs the reference evapotranspiration, the daily water balance and the definition of the indicator, and none is available: <item>; <item>; ...`, each item written `<part> <CODE>: <why>`, in this order:

| Part | Code | Why | When |
|---|---|---|---|
| `input` | `MISSING_INPUT` | The climate record has no daily series `<name>` | One item per absent series (G4, third row) |
| `input` | `MISSING_INPUT` | The daily series `<name>` holds `<n>` day(s) without a value in the year, the first on `<date>`; no gap is filled | One item per series with days held missing in the year (G4, fourth row; C3.4) |
| `ET0` | `MISSING_INPUT` | The constants of `engine/water/et0/constants.py` (the groups of `Et0Constants`, read from the class) are not passed (D46 not in force; D56) | Always |
| `ET0` | `MISSING_INPUT` | The reason code of the unit guard is not decided (Q11) | Always |
| `ET0` | `MISSING_INPUT` | The unit strings of the point (`PointUnits`) are not among the arguments of EP3 (D55 sets them for the climate adapter) | Always |
| `ET0` | the value's own code | `latitude` or `elevation` is missing in the point of the climate record, with its own detail | One item per missing value; longitude is not read, as in `engine/water/et0/daily.py` |
| `balance` | `MISSING_INPUT` | The column (the keyword arguments of `run_balance`, read from its signature) is not passed (D46, D49; OPEN 5 and 11 of `engine/water/balance/README.md`) | Always |
| `balance` | `MISSING_INPUT` | The crop of each day (the fields of `CropDay`, read from the class) needs crop parameters that are not passed (D46), and how the rotation is repeated over the years is not decided (Q5) | Always |
| `balance` | `NOT_AVAILABLE` | The daily runoff by the Curve Number (D44) is a unit that is not built | Always |
| `balance` | `NOT_AVAILABLE` | The daily evaporation coefficient from the surface-layer balance (D44) is a unit that is not built; the single-coefficient fallback is not mapped (OPEN 7 of the balance README) | Always |
| `indicator` | written `(reason code OPEN: question 4 of contracts/results/README.md)` | The critical period of each crop, and which quantities of the balance are water transpired and water demanded, are not defined (C1.4) | Always |

`NOT_AVAILABLE` appears only for a unit that is not built, the one meaning D12 and D31 keep for it. The other details are one fixed text each (infeasible calendar, time zones, start month, `precipitation` absent), and `the daily series '<name>', ... do not cover agricultural year <ag_year> from its first day to its last (C5.5)` for a year not covered.

## PROPOSED choices

Where EP3, the brief and the precedent do not settle something, the option that invents nothing. Each is a proposal; the question is under [OPEN](#open).

1. **Time basis.** C1.3 leaves it `OPEN`. The brief and D47 ask for an item per agricultural year of the record, so yearly items carry `time_basis: "ag_year"`. When the years cannot be laid out, the model's other basis, `rotation`, carries one item: a list of one item is the only valid form, since the list is never empty and `ResultsPerRotation` does not accept an empty one. OPEN 1, OPEN 2.
2. **No start month.** EP1 returns one `Missing`; EP3 cannot, because its return type is a list. It returns one item on the time basis `rotation`, `MISSING_INPUT`, naming the start month, until the rotation definition v2 (#129) carries it. Today's calendar engine writes the start month as missing (`NOT_DECLARED`), so this is what the route sees with the real calendar engine. OPEN 2.
3. **ET0 and the balance are not called.** Running the reference evapotranspiration needs a reason code for its unit guard (Q11, not decided) and `PointUnits`, neither among the arguments of EP3; passing them would mean choosing them here. With every constant missing, every day's value would be missing anyway. The balance cannot be called at all: `capacity` and `column_depth` must be numbers greater than zero (rule R10 of the balance README) and are not passed. So the entry point reads from the two parts what they need (constant groups, climate quantities, keyword arguments of `run_balance`, fields of `CropDay`) and names it, so the names cannot drift from the parts. OPEN 3.
4. **The series that marks the record** is `precipitation`, as in EP1 (#115), so that EP1 and EP3 list the same years, as D47 requires. Q5 leaves this `OPEN`. OPEN 4.
5. **Coverage of the other five series.** A year that a present input of the reference evapotranspiration does not cover is `NO_COVERAGE` like a year `precipitation` does not cover (C5.5 speaks of "the data series"); an absent series is `MISSING_INPUT` (G4, third row). OPEN 4.
6. **Precedence**: infeasible calendar, then time zones, then coverage, then missing inputs and parameters; of the two single items, the start month before the series, as in EP1. OPEN 5.
7. **The yearly reason is `MISSING_INPUT`.** The parameters are inputs that are absent (C3.3, and D56 asks for `MISSING_INPUT` naming an absent parameter). The definition gap of C1.4 is named as an item, with its code left `OPEN` (question 4 of `contracts/results/README.md`): EP3 notes that the examples use `NOT_AVAILABLE`, but D12 and D31 keep that code for a module that is not built. OPEN 6.
8. **Units of the daily series are not checked.** The reason code for a unit the engine does not accept is Q11, not decided; checking would mean choosing it. OPEN 7.

## Numbers in the module

`exposure.py` holds one integer, `1` (`_FIRST`): days and months are counted from one (C5.1), the year before the start month, one day earlier, one year later, and the last year of an inclusive range. A test reads the module and fails on any other number and on any format specification in an f-string. The test file uses `1` for the same arithmetic, `0` as a position counter, `2` to lay out a span of several agricultural years, and list positions to pick the first and last year; its daily values repeat the items of the example series; it writes no value.

## PROPOSED cases

The identifier is the name of the test function in `test_exposure.py` without `test_`, with hyphens. A test checks that this list and the test functions agree.

| Case | What it checks |
|---|---|
| `examples-as-they-are-load-and-every-item-is-missing` | The three examples of `contracts/inputs/examples/`, unchanged: the result loads into `WaterDeficitExposure` (round trip through `model_dump(mode="json")` and JSON text), lists the agricultural years of the example `precipitation` series on the time basis `ag_year`, and every item is missing with a code of C3.2 |
| `several-agricultural-years-load-into-results-per-rotation` | The six series over several agricultural years: one item per year of D47, in order; the list loads as the `water_deficit_exposure` part of the example `ResultsPerRotation` |
| `every-covered-year-is-missing-input-naming-each-part` | A covered year with no gap is `MISSING_INPUT`; its items name, in order, the ET0 constant groups (D46), the unit-guard code (Q11), `PointUnits`, the column of `run_balance`, the fields of `CropDay`, the Curve Number and the surface layer (`NOT_AVAILABLE`), and the indicator with its code `OPEN` (C1.4) |
| `infeasible-calendar-makes-every-item-not-computable` | An infeasible calendar: every item `NOT_COMPUTABLE` (G4, first row), also for a year the series does not cover |
| `year-not-covered-by-a-series-is-no-coverage` | A record that starts and ends inside agricultural years: those years are `NO_COVERAGE` (C5.5). Each input of ET0 shorter than the record makes its last year `NO_COVERAGE`, naming it and not `precipitation` |
| `series-one-day-short-at-each-end-leaves-first-and-last-not-covered` | Series one day short at each end: first and last years `NO_COVERAGE`, the years between `MISSING_INPUT`; the exact span covers every year |
| `absent-daily-series-is-missing-input-naming-it` | Each input of ET0 removed in turn: every year `MISSING_INPUT`, its first item names that series and no other |
| `days-held-missing-are-missing-input-naming-the-series` | Days held missing inside a covered year: one `input` item per series, naming it, the year, and a first day inside the year |
| `missing-point-value-is-named-in-an-et0-item` | `latitude`, `elevation` or both missing in the point: each named in an `ET0` item with its own code and detail; a missing `longitude` is not named |
| `series-in-different-time-zones-make-every-item-not-computable` | Series in two time zones: every item `NOT_COMPUTABLE` (C6.3) |
| `start-month-missing-returns-one-item-for-the-rotation` | A missing start month: one item on the time basis `rotation`, `MISSING_INPUT`, naming the start month |
| `no-precipitation-series-returns-one-item-for-the-rotation` | No `precipitation` series: one item on the time basis `rotation`, `MISSING_INPUT`, naming `precipitation` |
| `calendar-dates-outside-the-record-keep-the-years-of-the-record` | A calendar moved past the last day of the record gives the same result as the example calendar (D47) |
| `the-list-is-never-empty-and-no-item-is-a-number` | Over one result of each situation above: the list is never empty; no item is a number or zero; every item has a code of C3.2, no provenance and no range; one time basis per list; no agricultural year twice |
| `arguments-of-another-case-or-field-raise-value-error` | `case_id` or `field_id` of `climate` or `soil_slope` differs from the calendar: `ValueError` naming the field (G5) |
| `argument-that-is-not-its-model-raises-type-error` | An argument given as a dictionary, or as an instance of another model: `TypeError` naming the argument (G5) |
| `arguments-unchanged-and-second-call-equal` | The arguments equal a deep copy taken before the call, and a second call gives an equal result (G1) |
| `module-imports-only-allowed-modules-and-holds-only-the-integer-one` | `exposure.py` imports only the standard library, `contracts.inputs.*`, `contracts.results.models`, `engine.water.et0` and `engine.water.balance`; holds no number but `1`; has no format specification in an f-string |
| `package-exposes-compute-water-deficit-exposure-with-exactly-three-parameters` | `from engine.water import compute_water_deficit_exposure` works; its parameters are exactly `calendar`, `climate`, `soil_slope`, with no default |
| `runner-discovers-the-entry-point` | `discover_engine_functions()` of `api/engines.py` finds this function |
| `route-answers-with-a-water-part-that-loads-into-results-per-rotation` | In process, no network: `POST /api/rotations/run` with the example rotation, the example climate and the example soil and slope, EP2 replaced by the example calendar (which carries a start month) and the discovered EP1 and EP3: `200`, the result loads into `ResultsPerRotation`, its water part is what EP3 returns, and the water module is `not_available` with the reason of its first item |
| `proposed-cases-match-exposure-md` | This list and the test functions agree |

## What the route answers in process (14 November 2026, this branch)

With the default app's engines (all three discovered), the example rotation definition, a climate source that serves the example climate under the calendar's identifiers, and the example soil and slope: `200`, outcome `no_result`, `result: null`, `result_missing` `MISSING_INPUT` from EP1 (the start month is missing). The water module reads `not_available`, `MISSING_INPUT`, "1 of 1 values are missing": EP3 ran and returned its one `rotation` item. With the example climate under its own identifiers, the runner calls neither EP1 nor EP3 (site data of another field). With the example calendar in place of EP2, the result loads and the water part is one item, agricultural year 2000, `NO_COVERAGE`. The last case is the test above.

## OPEN

Each item is a question a person has to answer, with the role that answers it. None is answered by this unit.

1. **Time basis of the indicator (C1.3).** Yearly items are on `ag_year` because D47 and the brief ask for every agricultural year. Whether that is the basis, or one value per rotation, or a monthly breakdown. *Science reviewers.*
2. **What EP3 returns when the years cannot be laid out.** One item on the basis `rotation` (choice 2). After D7 and #129 the missing start month should no longer reach an engine; whether the `precipitation` case keeps this form. *Lead developer; platform developer for the response.*
3. **When ET0 and the balance are called.** Once `parameters` (D46, D56) and the unit-guard code (Q11) arrive, how the catalogue becomes `Et0Constants`, `PointUnits`, the column and the `CropDay` of each day, and how the calendar is laid onto the years of the record (Q5). *Lead developer, with the platform developer's agreement on the argument.*
4. **Which series marks the record and which series decide coverage** (Q5, still open). `precipitation` here, as in EP1; the five inputs of ET0 also decide coverage when present. *Lead developer.*
5. **Precedence of the reasons** (choice 6). *Lead developer.*
6. **Reason code for the incomplete definition of C1.4** (question 4 of `contracts/results/README.md`). Today it is named as an item with its code `OPEN`, under the reason `MISSING_INPUT` that the absent parameters give. When the parameters arrive, the definition gap alone will decide the code. *Lead developer.*
7. **Units of the daily series** (Q11). Not checked here; when ET0 runs, its unit guard answers with the code of Q11. Which unit string `precipitation` must arrive in for the balance is not written in `engine/water/balance/` (it holds no unit string). *Lead developer; science reviewers.*
8. **The three descriptive measures of C1.4 and the fourth of D50** (water available at the sowing of the next crop). `WaterDeficitExposure` and `ResultsPerRotation` have no field for them, so EP3 cannot return them (Q10 b). *Lead developer; interface developer.*
9. **The dual coefficient and the surface-layer evaporation, runoff by the Curve Number, several layers.** Units not built (D44); named `NOT_AVAILABLE` in the detail. *Lead developer (lane L1 plan).*
10. **Example data (Q16).** The inputs carry `example_data`; `WaterDeficitExposure` has no field for it. *Lead developer; platform developer.*
11. **Day boundaries.** Years are cut on the dates of the series, in its time zone (C6.1; UTC for the NASA POWER adapter), not on the local day at the field (C6.5). *Science reviewers.*
12. **Where the identifier `precipitation` lives.** Written once in `exposure.py` (D23), as in `soil_loss.py`. Whether contracts should export quantity identifiers. *Lead developer; platform developer.*
13. **Who reads `detail`.** The format is for developers. If the interface shows it, its wording belongs to the strings file of `web/` and to people. *Interface developer; lead developer.*
