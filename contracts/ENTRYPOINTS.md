# Engine entry points

The one public function of each engine: where it lives, its name, its arguments and what it returns (blueprint section 5). The route `POST /api/rotations/run` calls the engines only through these functions, so it can be built against signatures and not against unfinished engines.

## How to read this file

- This file was written by a builder session (blueprint section 3.7). Nothing here is in force until people approve the pull request: `PROPOSED` entries, signatures, and rules remain unapproved until maintainer sign-off (the lead developer, who owns lanes L0 and L1; the platform developer, who builds the route against these signatures; and the interface developer, who approves the entry of `engine/rothc/`, sub-lane L2b) and science-reviewer sign-off where science class applies.
- There is one entry per engine folder named in blueprint section 2. Every entry has an identifier (`EP1` to `EP6`) and exactly one status, given on its `Status:` line:
  - `PROPOSED`: the session proposes the module path, the function name, the arguments and the return type. A person accepts or corrects them in the pull request.
  - `OPEN`: the session cannot responsibly propose the signature. The entry gives a candidate, so that the question is concrete, and names the questions a person has to answer.
- A `PROPOSED` entry can still depend on a question. Questions are listed once, under [OPEN](#open), as `Q1` to `Q16`, each with the role that answers it.
- Three questions were answered by the lead developer on 14 November 2026 (issue #77): Q4, Q8 as far as the start month of the agricultural year goes, and Q10 as far as latitude and elevation go. Each keeps its number and its text, and carries the answer under it, marked `DECIDED`. They are a person's decisions, transcribed by a builder session. Issue #77 says of them: where they are science class, a science reviewer still has to accept them. No model and no route changed with these answers: each change is its own later unit, and until it lands the models behave as this file describes them. Q5 was answered the same day (issue #77, D47) and is recorded the same way. So is Q3 (D46, with the platform developer's conditions of D56). Its answer changes the signatures of EP1 and EP3 in this file before any engine or the runner changes.
- Later decisions of issue #77 are stated where they apply, each with the link to its comment: [D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713) (a crop component that starts before the first agricultural year of the record and ends inside it), [D147](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649) (the unit of the carbon inputs that EP4 writes for AMG) and [D148](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333) (the computed `C` is withdrawn from the demonstration; under D158 and D164, `#274` moved the 61 computed-`C` records to `params/withdrawn/computed_c/` while keeping the 6 shared residue yield/ratio records in `params/records/residues/`, and the computed-`C` code in `engine/erosion/` remains a documented, unvalidated capability). With D141 come [D132 and D133](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652), which it builds on and amends. [D157](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888807199) (the water indicator), with [D162 and D163](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889471148) (taken by the orchestrating AI session under the delegation of D161), is stated in EP3 and built on `main` since #296. On `main` at `b107d7a`, also built and wired are: [D181](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889843938) (annual water balance in `CarbonForcing.annual_climate`, `#371`, consuming `D256` daily ET0 since `#412`), [D188](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889974874) part 2 (lead-in cycle when the first cycle starts after the first day of the record's years, `#403`), [D194](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890256765) (aboveground/belowground origin split in EP4 `#306`, plus D221 monthly `carbon_inputs` in `#334` and `#350`), D192/D193/D199 (AMGv2 in EP5 `#305`), and EP6 in the runner (`#282`, `#409`, `#431`). Outside `EP1`–`EP6`, `D229` (H10 calendar-year runoff bridge `engine/water/yearly_runoff.py` `#501`, with signed H10 numeric fixture `validation/fixtures/h10_grahmann2022_runoff.json` in `#516`, while Curve Number and soil-profile records for the H10 plot run remain unsigned) and `D240`/`D258` (ONI v6 year-kind classification in `kinds_of_year/` `#422` for `POST /api/plant/run` `#427`, with signed `kinds_of_year/records/oni_v6.json` in `#510`) are also landed on `main` (`b107d7a`).
- General rules that hold for every entry are `G1` to `G7`. They are all `PROPOSED`.
- When this file was first written no engine existed. On `main` (`b107d7a`) the folder `engine/` holds `calendar/`, `erosion/`, `water/`, `residues/`, `amg/` and `rothc/`, and the runner finds EP1 to EP6 by the module path and the function name given here (`DISCOVERED` in `api/engines.py`). Standalone `PROPOSED` optional helpers outside `EP1`–`EP6` are listed under [Standalone non-EP engine helpers](#standalone-non-ep-engine-helpers-proposed-not-in-ep1ep6). This file contains no code. A signature is written as text, in the notation of Python type hints.
- This file contains no method, equation, unit, parameter value, threshold or citation. The repository names no soil-loss method and this file names none.
- Conventions such as C3.2 refer to `contracts/CONVENTIONS.md`. "Question 10 of `contracts/inputs/README.md`" refers to the numbered `OPEN` list of that file.

## Types used in the signatures

Every type in a signature is one of the rows below. Nothing else is used.

| Name in a signature | What it is |
|---|---|
| `RotationCalendar` | Existing model: file `contracts/inputs/rotation_calendar.py`, class `RotationCalendar` |
| `SiteClimate` | Existing model: file `contracts/inputs/site_climate.py`, class `SiteClimate` |
| `SiteSoilSlope` | Existing model: file `contracts/inputs/site_soil_slope.py`, class `SiteSoilSlope` |
| `SoilLossResults` | Existing model: file `contracts/results/models.py`, class `SoilLossResults` |
| `WaterDeficitExposure` | Existing model: file `contracts/results/models.py`, class `WaterDeficitExposure` |
| `Missing` | Existing model: file `contracts/results/models.py`, class `Missing`. Not the class of the same name in `contracts/inputs/common.py` |
| `list[...]`, `A \| B` | Built-in: a list, and "one of the two types" |
| `dict[str, dict]` (only as `parameters`) | The parameter catalogue as loaded (Q3, D46, D56): the first value that `params.catalogue.load_folder` returns for the folder `params/records/`, that is every record of the catalogue, each a dictionary in the record format of `params/README.md`, keyed by the path of its file relative to `params/records/`. PROPOSED |
| `RotationDefinition` (`"Rotation definition"`) | `PROPOSED` model: file `contracts/rotation_definition/rotation_definition.py`, class `RotationDefinition` (#68, #129; blueprint section 5 name `"Rotation definition"`). Consumed by EP2 (`engine/calendar/build.py`) and EP4 (`engine/residues/ledger.py`) on `main`. Remains `PROPOSED` until formal pull-request approval (blueprint section 3.7); `crop_id` still accepts any non-blank text (D2) |
| `ResidueLedger` (`"ResidueLedger"`) | `PROPOSED` model: file `contracts/residue_ledger/models.py`, class `ResidueLedger` (#235, D194 #306, D221 #334; blueprint section 5 name `"ResidueLedger"`). Returned by EP4 (`engine/residues/ledger.py`) and consumed by `api/engines.py` / `api/carbon_forcing.py` (#242, #350). Remains `PROPOSED` until formal pull-request approval (blueprint section 3.7) |
| `"CarbonForcing"` | PROPOSED model: file `contracts/carbon_forcing/models.py`, class `CarbonForcing` (#155, accepted into `contracts/` by D62 of #77). It also carries the monthly soil-cover series (`soil_cover`) and the starting state of the soil carbon (`starting_state`): both travel inside the forcing, not as separate arguments (D65 of #77). Its values (quantities, units, depth, horizon, aggregation, cover, starting pools) are `OPEN` in `contracts/carbon_forcing/README.md` |
| `CarbonBalance` | PROPOSED model: file `contracts/carbon_balance/models.py`, class `CarbonBalance` (#199, #205). What one carbon model returns for one rotation of one field: the stocks, the flows of each step and the three values of `soil_carbon_trend`, all inside it. Returned by EP5 and EP6 on `main` (`b107d7a`). Its pools, flows, identifiers and units are `OPEN` in `contracts/carbon_balance/README.md`, and the contract remains `PROPOSED` until formal acceptance |

A name in double quotes is the blueprint name of a contract, not a class: its model, its file and its example are a separate unit. The models of `contracts/inputs/` and `contracts/results/` are themselves proposals; a signature follows them as they are in `main` and changes when they change.

## Rules for every entry point

Status of G1 to G7: PROPOSED

### G1 A pure function

An entry point receives data and returns data. It makes no network call, reads and writes no file, reads no environment variable and no clock, and does not change its arguments. The same arguments give the same result. Adapters fetch; the route passes what they return.

The values of the parameter catalogue reach an entry point as the argument `parameters`, loaded by the runner (Q3, D46). An entry point may call the pure functions of `params.catalogue` that read a record it was given (`read_value`, `read_range`, `identity`). It never calls `load_folder` or anything else that reads a file. PROPOSED.

### G2 One call is one rotation of one field

One call computes one rotation of one field from one set of inputs. Comparing rotations, repeating a call per scenario and building a results table are done by the caller (Q6, Q15).

Each phase of a rotation is such a scenario (D109). The caller makes one run per phase, each on the calendar of that phase (D132: "For a rotation whose cycle lasts N years, the runner makes N runs"; see Q5).

### G3 Arguments and return value are model instances

- Every argument is an instance of the model the signature names, already validated. An entry point does not receive a dictionary or JSON text. The one exception is `parameters` (Q3, D56). It is the catalogue as `params.catalogue.load_folder` returns it, which is a dictionary, and the runner passes it only after `params.catalogue.check_catalogue` has reported no problem for it. What the runner does when the check reports a problem is the platform developer's (Q3).
- The route passes arguments by name.
- The return value is an instance of the type the signature names and is valid for its model.

### G4 What a function returns when it cannot compute

A function that cannot compute a value returns that value as missing, with its reason, as section 3 of the conventions sheet defines it. It never returns zero, a blank or a stand-in number in its place, and it never leaves the value out. It fills nothing in (C3.3).

| Situation | What is returned | Convention |
|---|---|---|
| The calendar is infeasible (`RotationCalendar.feasibility.feasible` is false) | Every value that depends on the calendar is missing, reason `NOT_COMPUTABLE` | C3.2 |
| An input value that the computation needs is missing | The result is missing, reason `MISSING_INPUT`; `detail` names the input | C3.3 |
| A quantity that the computation needs has no item in `daily_series`, `monthly_series` or `soil_properties` | The same: `MISSING_INPUT`; `detail` names the quantity. The sheet does not name this case; this reading is proposed here | C3.3 |
| A daily series has days that are missing | A value computed from those days is missing, reason `MISSING_INPUT`. No gap is filled until a person supplies the method that C3.4 asks for | C3.3, C3.4 |
| The series does not cover an agricultural year from its first day to its last | The yearly values of that year are missing, reason `NO_COVERAGE` | C5.5 |
| Two daily series that must be combined have different time zones | The result is missing, reason `NOT_COMPUTABLE` | C6.3 |
| The inputs are present and the method does not cover the case | The result is missing, reason `NOT_COMPUTABLE` | C3.2 |
| An input is in a unit that the engine does not accept | The result is missing. The reason code is not decided: Q11 | C1.1 |
| A parameter that the computation needs has no record in `parameters` | The result is missing, reason `MISSING_INPUT`; `detail` names the parameter by its `id` and the `scope` looked for (D56). PROPOSED | C3.3 |
| The record of a parameter has `"value": null` (or `"range": null`) with its reason | A result that needs that value (or that range) is missing, reason `MISSING_INPUT`; `detail` names the parameter and repeats the reason of the record. PROPOSED | C3.3 |

A missing value keeps its indicator identifier, its direction and its unit (C3.1).

**A component that crosses the first day of the record (D133, D141).** Decision of [issue #77, D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713), which amends [D133](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652): "Where an engine cannot compute a quantity because it would need the part before the record (for example, a state carried in from it), that quantity stays missing with its reason (C3.2), as for the first phase." D141 names no reason code, and this note adds no row to the table: the rows above apply as they are. The whole decision is quoted under Q5.

### G5 Errors an engine may still raise

An engine raises nothing for a missing value, an infeasible calendar, an absent quantity, a period that is not covered, a unit it does not accept or example data. Those are answered by G4, so that a valid request can always be answered `200` (platform decision in issue #18).

An entry point may raise only for a defect of its caller:

- `TypeError`: an argument is not an instance of the type the signature names.
- `ValueError`: two arguments of one call name different `case_id` or `field_id`, so they do not describe the same field.

Any other exception is a defect of the engine and no part of this contract. What the route answers in either case is decided in issue #18 and is not repeated here.

### G6 Results follow the results models

An indicator value is returned as the models of `contracts/results/models.py` define it: with its unit, its direction, its provenance label, its source or assumption mark, and its range or the reason it has none. This file adds no rule to those models. Open points of those models that an engine meets before it can return a number are listed under [Questions of other files](#questions-of-other-files-that-these-signatures-depend-on).

### G7 No thresholds

No entry point takes the test plan or any threshold. Thresholds are read by the matrix and the decision (blueprint section 5), which are not engines.

## Entries

The summary repeats the entries below; the status of an entry is the one on its `Status:` line.

| Entry | Engine folder | Lane | Function | Status |
|---|---|---|---|---|
| EP1 | `engine/erosion/` | L0 Core | `compute_soil_loss` | PROPOSED |
| EP2 | `engine/calendar/` | L1 Engines | `build_rotation_calendar` | PROPOSED |
| EP3 | `engine/water/` | L1 Engines | `compute_water_deficit_exposure` | PROPOSED |
| EP4 | `engine/residues/` | L1 Engines | `build_residue_ledger` | PROPOSED |
| EP5 | `engine/amg/` | L1 Engines | `run_amg` | PROPOSED |
| EP6 | `engine/rothc/` | L2b Platform: decision and carbon | `run_rothc` | PROPOSED |

Module paths are written from the repository root. Whether that is the import path is Q1. Every `PROPOSED` entry (`EP1`–`EP6`) is implemented on `main` (`b107d7a`) and discovered by `api/engines.py` (`DISCOVERED`), and **remains unapproved until maintainer and science-reviewer sign-off under blueprint section 3.7**. Standalone optional engine helpers outside `EP1`–`EP6` are listed under [Standalone non-EP engine helpers](#standalone-non-ep-engine-helpers-proposed-not-in-ep1ep6).

### EP1 `engine/erosion/`

Status: PROPOSED

| Aspect | Entry |
|---|---|
| Lane | L0 Core (lead developer) |
| Module path | `engine.erosion` (file `engine/erosion/__init__.py`) |
| Function name | `compute_soil_loss` |
| Argument `calendar` | `RotationCalendar` (`contracts/inputs/rotation_calendar.py`). The value returned by EP2 |
| Argument `climate` | `SiteClimate` (`contracts/inputs/site_climate.py`). From the adapters |
| Argument `soil_slope` | `SiteSoilSlope` (`contracts/inputs/site_soil_slope.py`). From the adapters, or the accepted example while blueprint section 7 allows it |
| Argument `parameters` | `dict[str, dict]`: the parameter catalogue as loaded by the runner, passed by keyword like the other arguments (Q3, D46, D56). PROPOSED |
| Return type | `SoilLossResults`, or `Missing` (both in `contracts/results/models.py`) |

```text
compute_soil_loss(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    parameters: dict[str, dict],
) -> SoilLossResults | Missing
```

Why these arguments: blueprint section 8 lists for this engine slope length and slope steepness, which are fields of `SiteSoilSlope`; a monthly erosivity fraction, which is read or derived from one of the series of `SiteClimate` (question 10 of `contracts/inputs/README.md`); and cover management by period, which are the dated periods of `RotationCalendar`.

What it returns: a `SoilLossResults`, with one annual value per agricultural year and the twelve monthly values of each. It goes unchanged into the field `soil_loss` of `ResultsPerRotation`.

When it cannot compute:

- G4 applies to every annual and monthly value. Every agricultural year and each of its twelve months is present; a value that is not computed is missing with its reason.
- When the agricultural years themselves cannot be laid out, because the start month in `calendar.ag_year_start` is missing, the function returns one `Missing` with reason `MISSING_INPUT` and a `detail` that names the start month. `SoilLossResults` cannot say this: it needs at least one agricultural year with its number and twelve dated months. This is Q4.
  - **This point no longer applies once the decision on Q4 is in force.** `DECIDED` by the lead developer on 14 November 2026 (issue #77, D7): the start month is a required part of the request; a request without it is an invalid request, and the route answers it as such and calls no engine. The case "no start month" no longer reaches an engine. The text above is kept to show what was proposed.
  - Not changed yet: `RotationCalendar` still accepts a start month that is missing with its reason, and the signature of this entry is left as it was written. Issue #77 does not say whether the return type changes.

Phases and the first day of the record (D132, D141):

- By [D132](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652), EP1 is called on the calendar of a phase, a `RotationCalendar` that the runner moved: "EP1, EP3 and EP5 receive the moved `RotationCalendar`; their signatures do not change (D56)." The signature above is unchanged.
- EP1 lays a feasible calendar over the agricultural years of the record with `repeat_over_record` of `engine/calendar/repeat.py` (`_soil_loss` in `engine/erosion/soil_loss.py`), and it does the same with the calendar of a phase. By [D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713) and pull request #243, that helper also lays out the cycle before the first when one of its components ends inside the record (and since D188 part 2, #403, whenever the first cycle starts after the first day of the record's years; see EP2), so such a component is present from the first day of the record.
- EP1 fills nothing in for a day that the repeated calendar does not describe, nor for a day with no harvest before it in the repeated calendar: it names each as a problem with reason `MISSING_INPUT` (`engine/erosion/soil_loss.py`), as the sentence of D141 quoted under G4 asks. What the value of the year then is, and what stays open about the residue left before the record, is in `engine/erosion/SOIL_LOSS.md`.

The computed `C` and the demonstration (D148). Decision of [issue #77, D148](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333), which amends D145 and D146: "The computed `C` is withdrawn from the demonstration. Its per-rotation values are not shown, neither as absolute values nor as a comparison. Its code (#229) and its signed records (#237) stay in the repository as a documented, not validated capability." Under [D158](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889049425) and [D164](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889521276), `#274` moved the 61 computed-`C`-only records out of `params/records/` into `params/withdrawn/computed_c/` (leaving the 6 shared residue yield/ratio records in `params/records/residues/` for EP4), so EP1 takes its declared-`C` fallback (D125) and the computed-`C` code in `engine/erosion/` stays in the repository as a documented, unvalidated capability (`engine/erosion/SOIL_LOSS.md`). The decision changes neither this signature nor the shape of `SoilLossResults`: `engine/erosion/SOIL_LOSS.md` records it with the words "This note changes no code". The check behind it is the entry `[E7]` at the end of `docs/VALIDATION.md`, whose result D148 gives as "not passed" for the computed `C` (recorded as an observation without pass rule under D252). Which value of `soil_loss` a screen shows, and with which label, is in D148 and is not defined by this file.

Depends on: Q3 (parameters; answered: see the question), Q4 (answered: see the question), Q5 (which agricultural years; answered: see the question), Q11 (unit), Q12 (residue ledger).

### EP2 `engine/calendar/`

Status: PROPOSED

| Aspect | Entry |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.calendar` (file `engine/calendar/__init__.py`) |
| Function name | `build_rotation_calendar` |
| Argument `rotation` | `RotationDefinition` (`contracts/rotation_definition/rotation_definition.py`, `PROPOSED`, #68, #129; blueprint section 5 name `"Rotation definition"`), producer Interface. The item `rotation` of the request body, validated by the route (issue #18) |
| Return type | `RotationCalendar` (`contracts/inputs/rotation_calendar.py`) |

```text
build_rotation_calendar(rotation: RotationDefinition) -> RotationCalendar
```

What it returns: always a `RotationCalendar`, feasible or not. It is the argument `calendar` of EP1, EP3 and EP4.

When it cannot compute:

- A rotation that breaks a calendar rule gives a calendar with `feasibility.feasible` false and at least one `RuleViolation`. The function does not raise. An engine that receives that calendar answers by G4.
- A date that cannot be placed is a `DateValue` with `date` null and its `missing` part: reason `NOT_DECLARED` when the user did not give what the date needs, otherwise the code of G4 that applies. No date is invented.
- A start month of the agricultural year that was not declared is an `AgYearStart` with `month` null and its `missing` part.
  - **This point no longer applies once the decision on Q4 is in force.** `DECIDED` by the lead developer on 14 November 2026 (issue #77, D7): a request without the start month is an invalid request, and the route answers it as such and calls no engine. The text above is kept to show what was proposed.
  - `DECIDED` on the same day (issue #77, D8): the start month travels in the rotation definition, with its provisional mark, and the calendar engine copies it into the calendar.
  - Changed on `main` since this point was written: the rotation definition carries the start month, required and never missing (`ag_year_start` of `contracts/rotation_definition/rotation_definition.py`), and the calendar engine copies it into the calendar (`_copy_start_month` of `engine/calendar/build.py`), both by #129 (`fc6d2e2`). Not changed: `RotationCalendar` still accepts a start month that is missing with its reason (`AgYearStart` of `contracts/inputs/rotation_calendar.py`).
- `RotationCalendar` has no missing state for `case_id`, `field_id`, `rotation_id`, `start_date` and `end_date`. The function can return a valid calendar only if its arguments give all five. With the single argument above, the rotation definition has to carry them: Q8.

**Phases (D109, D132, D141).** EP2 and its signature do not change. By [D132](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652): "The phase rule lives in one place: `engine/calendar` provides `phase_calendar(calendar, p) -> RotationCalendar` and `list_phases(calendar)` (unit #221), and the runner calls them without computing anything scientific." The two are helpers in `engine/calendar/repeat.py`, not entry points. Their form is PROPOSED in the docstring of that module, and this file gives them no status. As they are on `main`:

- `list_phases(calendar)` returns the phases `0` to `N - 1`, where `N` is the whole number of years of one cycle of the calendar. A one-year rotation has one phase (D109).
- `phase_calendar(calendar, p)` returns a valid `RotationCalendar`, moved so that year `p` of the calendar comes first. Phase `0` returns the calendar unchanged. It raises `ValueError` when `p` is not one of `list_phases(calendar)`, and for a phase above `0` when the start month is missing.
- By [D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713), which amends D133, a component of a year before `p` that has a date in year `p` or later keeps its declared dates, moved one cycle with the other components of its year, when it lies whole in one cycle. `repeat_over_record` also lays out the cycle before the first (index `-1`, pull request #243) when one of its components has an end date on or after the first day of the record's years, and since D188 part 2 (#403) whenever the first cycle starts after the first day of the record's years. So that component is present from the first day of the record, in every phase and in the first alike; the part before that day is outside the record.
- `OPEN` in that docstring (point 11), for the lead developer and the science reviewers: a crossing component that cannot lie whole in one cycle. D141 says it "keeps its declared dates". On `main` its start and its end are missing with reason `NOT_COMPUTABLE` and a detail that names D141, so its days read as missing, never as days with no crop.
- `components_crossing_phase(calendar, p)` returns the `component_id` of each component of the two points above. It is empty for phase `0`.
- No phase raises for a crossing component.

Depends on: Q8 (answered for the start month: see the question). Whether a calendar with a missing date can be feasible is question 8 of `contracts/inputs/README.md`.

### EP3 `engine/water/`

Status: PROPOSED

| Aspect | Entry |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.water` (file `engine/water/__init__.py`) |
| Function name | `compute_water_deficit_exposure` |
| Argument `calendar` | `RotationCalendar` (`contracts/inputs/rotation_calendar.py`). The value returned by EP2 |
| Argument `climate` | `SiteClimate` (`contracts/inputs/site_climate.py`). From the adapters |
| Argument `soil_slope` | `SiteSoilSlope` (`contracts/inputs/site_soil_slope.py`). From the adapters, or the accepted example while blueprint section 7 allows it |
| Argument `parameters` | `dict[str, dict]`: the parameter catalogue as loaded by the runner, passed by keyword like the other arguments (Q3, D46, D56). PROPOSED |
| Return type | `list[WaterDeficitExposure]` (`contracts/results/models.py`) |

```text
compute_water_deficit_exposure(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    parameters: dict[str, dict],
) -> list[WaterDeficitExposure]
```

**One function, not two.** Blueprint section 8 places the reference evapotranspiration in `engine/water/et0/` and the water balance in `engine/water/balance/`. The proposal is that the route sees one function, in `engine/water/`, and that the two subfolders are internal parts that it calls. Reasons:

- Blueprint section 2 names `engine/water/` as one engine folder, and section 5 asks for one public function per engine.
- No contract of blueprint section 5 carries the reference evapotranspiration or the daily water balance (`contracts/inputs/README.md` says they are results of the engines, not site data). A second public function would have no agreed type to return.
- The route needs the indicator, not the intermediate series.

The lead developer confirms or corrects this: Q2.

Why these arguments: the indicator is defined over the critical period of the crop (C1.4), and until that is defined "over the days with a living crop (D105, D106, D136)" ([D157](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888807199)), within "the whole cycle of each crop, from sowing to harvest" (D105); either needs the calendar; the balance is daily (C1.4), which needs the daily series of `SiteClimate`; soil data reaches the engines lane through `SiteSoilSlope` (blueprint section 5). Which series and which soil properties the engine reads are questions 9 and 16 of `contracts/inputs/README.md`.

What it returns: a list with at least one `WaterDeficitExposure`, all on one time basis. It goes unchanged into the field `water_deficit_exposure` of `ResultsPerRotation`, which checks those two rules; a bare list is not checked by any model.

When it cannot compute:

- **When an item is a number (D157).** Decided by [D157 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888807199), which amends D61: "EP3 reports `water_deficit_exposure` as a number when the daily balance was computed on every day of the agricultural year." "A year with no day with a living crop is `NOT_APPLICABLE`." "Every value carries the label "whole cycle, not critical period" (D105)." "This amends D61: `NOT_AVAILABLE` no longer applies to a year the chain computed." The ratio and its two quantities are in C1.4. Where the label travels is decided by [D162](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889471148) (under the delegation of D161): "In the `source` text of each water value, written by EP3, verbatim. No contract change." The results models reject a `source` on a missing value (`contracts/results/models.py`), so the label can travel only on a value that is a number, never on a year that is missing or `NOT_APPLICABLE`.
- **Built (unit `l1/water-indicator-d157`, #296).** On `main`, `compute_water_deficit_exposure` (`_computed` in `engine/water/exposure.py`) gives a year whose daily balance was computed on every day the ratio of D157 as a number: the sum of `transpiration` of the daily balance over the sum of its `transpiration_demanded`, over the days of the year with a living crop. Its `source` starts with the label "whole cycle, not critical period" (`WINDOW_LABEL`, D105, D162), its provenance is `SIMULATED` (PROPOSED), and it has no range, with reason `NOT_AVAILABLE`. A year with no day with a living crop is `NOT_APPLICABLE`; a year whose demanded sum is not above zero, or whose ratio is not finite, is `NOT_COMPUTABLE` (PROPOSED); a year with a crop quantity of the balance (demanded transpiration or transpiration) missing on one of its days keeps the reason of that day. With the signed water records in `params/records/water/` (45 records in #262, 43 soybean and site records in #417 under D200 to D209, and 12 wheat and maize records in #446; 100 water records in total), EP3 computes a numeric value for rotations whose crops have all required records (such as soybean with winter fallow of D128); a rotation whose crops still lack signed records (such as wheat and maize stage lengths and residue cover) stays missing with the first reason that applies (the docstring of `compute_water_deficit_exposure`): `NOT_COMPUTABLE` for an infeasible calendar or for series in different time zones (C6.3), `NO_COVERAGE` for a year a series does not cover (C5.5), `MISSING_INPUT` for an input in a unit string the parts do not accept, otherwise the reason of the first day of the year on which the daily chain has no value. Every item is in the unit `dimensionless`.
- Otherwise G4 applies to every item. D157: "a year the chain cannot compute keeps its own reason."
- The list is never empty and an agricultural year is never left out.
- The time basis of the items is one value per agricultural year (D47), decided by D157 (C1.3). The signature does not change. On `main` EP3 writes one item per agricultural year, on the time basis `ag_year`, and one item on the time basis `rotation` only when the agricultural years cannot be laid out (the start month is missing, or the record has no daily `precipitation` series; docstring of `compute_water_deficit_exposure`). [D163](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889471148) (under the delegation of D161) keeps both: "Both time bases stay for this release, and no new reason code is created. D157 fixes `ag_year` for every value EP3 computes. EP3 keeps `rotation` only for the single item it returns when no agricultural year can be laid out". Built so on `main` (#296; docstring of `compute_water_deficit_exposure`, which cites D163).
- On `main` the signature is `compute_water_deficit_exposure(calendar, climate, soil_slope, *, parameters)`: `parameters` is keyword-only, as in `run_amg`. The route passes every argument by name (G3), so the call is the same. Separately, under D229 and D230, `engine/water/yearly_runoff.py` (`compute_calendar_year_runoff`, `#501`) provides a standalone `PROPOSED` non-EP validation bridge over EP3's daily chain for `[H10]` (paired with the signed H10 numeric fixture `validation/fixtures/h10_grahmann2022_runoff.json` in `#516` `b107d7a`, while Curve Number and soil-profile records for the H10 plot run remain unsigned).

Phases (D132, D141): by [D132](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652), EP3 is called on the calendar of a phase, a `RotationCalendar` that the runner moved, and this signature does not change (D56). How EP3 lays that calendar over the record, and so how [D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713) reads in this engine, is not described in this section: it is the text of the unit that builds it (`engine/water/EXPOSURE.md`, OPEN 5). D147 and D148 do not concern this entry.

Depends on: Q2, Q3 (parameters; answered: see the question), Q5 (which agricultural years; answered: see the question), Q10 (inputs and outputs of the water engine; answered for latitude and elevation: they arrive in `climate`, and this signature does not change), Q11 (unit).

### Beside EP3: `daily_reference_evapotranspiration` (D256)

Status: PROPOSED

Decided by D256 of issue #77: the daily FAO-56 reference evapotranspiration that the runner needs for the carbon forcing (D220, D181) comes from this public function of lane L1, `engine.water.daily_reference_evapotranspiration`, found by name as the entry points are. It is not a numbered entry point: it returns a series that the runner passes on, not an indicator. It is the one exception D256 makes to "one public function per engine" (the proposal of EP3 above, Q2, and the section "Not covered by this file").

| Aspect | Entry |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.water` (file `engine/water/__init__.py`; the function is in `engine/water/reference_et0.py`) |
| Function name | `daily_reference_evapotranspiration` |
| Argument `climate` | `SiteClimate` (`contracts/inputs/site_climate.py`). The same object EP3 receives |
| Argument `parameters` | `dict[str, dict]`: the parameter catalogue as loaded by the runner, keyword-only, no default (Q3, D46, D56) |
| Return type | `dict[datetime.date, float \| Missing]`: one item per day of the climate record, in date order; `Missing` is the one of `contracts/results/models.py` |

```text
daily_reference_evapotranspiration(
    climate: SiteClimate,
    *,
    parameters: dict[str, dict],
) -> dict[date, float | Missing]
```

What it returns: the daily FAO-56 reference evapotranspiration of D44, in mm per day, exactly the series EP3 runs its daily chain on (D44, D256). It makes the call EP3 makes, with EP3's own identifiers of the constants and of the two bounds of D82, its catalogue reader, point units and unit-guard reason; no constant is written in it. A day without a value is `Missing` with the reason EP3's chain gives that day; a constant or bound without a record makes every day `MISSING_INPUT`, naming it by `id` and scope. A climate with no daily series gives an empty mapping. Raises `TypeError` for an argument that is not its type (G5). `engine/water/test_reference_et0.py` checks, on the PLACEHOLDER chain and both rotations of D128, that the series equals day by day the one EP3 uses.

Built and pending from D256: the runner (`api/engines.py`, #412) discovers and calls `engine.water.daily_reference_evapotranspiration` by name (`REFERENCE_ET0`) and no longer rebuilds ET0 from private names. EP3 still builds its own call (`_run_chain` of `engine/water/exposure.py`) instead of calling this function; switching EP3 waits for a later pull request. Separately, for D222 (#423, #431), the runner also discovers lane L1's public live-crop rule `engine.water.living_crop.live_crop_by_day` by name (`LIVE_CROP`) to build RothC's monthly `soil_cover` in `CarbonForcing`.

### EP4 `engine/residues/`

Status: PROPOSED

Built by unit `l1/residue-ledger-ep4` (brief #220), at the lead developer's request, so that AMG gets carbon inputs (D122 of #77). Everything in this entry is PROPOSED, for the lead developer's approval. The platform developer consumes the result. The forms and the records are in `engine/residues/README.md`.

| Aspect | Entry |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.residues` (file `engine/residues/__init__.py`; the function is in `engine/residues/ledger.py` and is exported from the package) |
| Function name | `build_residue_ledger` |
| Argument `rotation` | `RotationDefinition` (`contracts/rotation_definition/rotation_definition.py`): the item `rotation` of the request, as the route validates it. It gives each component's `purpose` and declared `management.residue`, which the calendar does not carry |
| Argument `calendar` | `RotationCalendar` (`contracts/inputs/rotation_calendar.py`). The value returned by EP2, feasible or not |
| Argument `climate` | `SiteClimate` (`contracts/inputs/site_climate.py`). Only the period of its daily series is read, for the agricultural years (D47) |
| Argument `parameters` | `dict[str, dict]`: the parameter catalogue as loaded by the runner (Q3, D46, D56). Keyword-only, as in `run_amg` |
| Return type | `ResidueLedger` (`contracts/residue_ledger/models.py`, PROPOSED) |

```text
build_residue_ledger(
    rotation: RotationDefinition,
    calendar: RotationCalendar,
    climate: SiteClimate,
    *,
    parameters: dict[str, dict],
) -> ResidueLedger
```

What it returns: a `ResidueLedger` with one entry per component of the calendar in each cycle of the rotation repeated over the record (D47, `engine.calendar.repeat_over_record`, as EP1). Each entry holds the aboveground residue at harvest produced, exported and retained, as mass and as carbon, and apart from it the roots and the rhizodeposits. For a `grain` component:

- the residue = `rusle2_residue_yield_ratio` × `rusle2_crop_yield` (D129 (c));
- the carbon = the mass × `residue_carbon_fraction`;
- the export = the residue × `residue_removed_fraction` when the component declares `removed`, and nothing when it declares `left_on_surface` or `incorporated`;
- the roots = `root_mass_at_harvest` with `root_carbon_fraction`;
- the rhizodeposits = `rhizodeposit_carbon`.

Every record is read by crop. The ledger also holds, per crop, purpose and part that enters the soil, one `AnnualCarbonInputSeries` over the whole agricultural years of the record. These are the series the platform copies unchanged into `CarbonForcing.annual_carbon_inputs`. Under [D147 of #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649) they are in `t C ha-1`, the unit AMG requires: EP4 converts its sums from the ledger's `kg C ha-1` by the SI definition 1 t = 1000 kg, a definition that needs no record. The components of the ledger stay in `kg ha-1` and `kg C ha-1`. D147 also says: "The runner and AMG do no arithmetic on them (as the EP4 brief asked)."

The `origin` of each series follows [D194 of #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890256765) (taken under the delegation of D161), built in #306: `<crop_id>_aboveground` for the series of the retained aboveground carbon and `<crop_id>_belowground` for the series of root carbon and of rhizodeposit carbon (`series_origin` and `ORIGIN_GROUP_OF_PART` in `contracts/residue_ledger/models.py`, which the ledger contract checks; `_series` in `engine/residues/ledger.py`). EP5 reads one humification coefficient per origin, so each crop meets one coefficient for its aboveground input and one for its belowground input. No such humification-coefficient record is in `params/records/` on `main`: D194 states the coefficients (`h_AG` and `h_BG` of the AMGv2 dataset for soybean, wheat and maize), and the records that carry them, signed by a person (D34, D66), are not there yet (meanwhile `params/records/residues/` holds 6 signed yield/ratio records from `#237`/`#274` under D164, while the remaining 5 EP4 residue parameter records still await signature; `#334`/`#361` also added D221 `monthly_carbon_inputs`, wired by `#350`, and `#503` added mass-conservation and G1–G7 tests).

When it cannot compute (G4):

- An infeasible calendar makes every value `NOT_COMPUTABLE`.
- A record that is not in `parameters` makes the values that need it `MISSING_INPUT`, naming it by `id` and scope (D56). So does a record with a `null` value, whose reason is repeated.
- A component whose purpose is `cover` or `pasture` has every value `NOT_COMPUTABLE`: D129 (c) needs a yield.
- When no agricultural year can be laid out, the ledger carries `years_missing` with its reason and lists nothing.

It raises only `TypeError` for an argument that is not of its type, and `ValueError` when the three arguments name different `case_id` or `field_id` (G5).

Still `OPEN` (`engine/residues/README.md`, OPEN; `contracts/residue_ledger/README.md`, OPEN):

- the dry-matter basis of the yield, and the `kg` unit strings, which C1.1 does not list;
- how roots, rhizodeposits, cover crops and pastures are computed;
- when a residue enters the soil;
- the acceptance of the contract's shape;
- whether a carbon engine takes the ledger itself (Q14 (b)).

The runner calls EP4 and copies its series into `CarbonForcing` (lane L2a, #242).

Phases (D132, D141): the runner calls EP4 once per phase, by keyword, on the calendar of that phase, after EP1 and EP3 and before EP5 (`_run_phase` in `api/engines.py`). EP4 lays that calendar over the record with the same helper as EP1, `repeat_over_record`, so the cycle before the first that [D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713) asks for is laid out for both in the same way (see EP2).

### EP5 `engine/amg/`

Status: PROPOSED

| Aspect | Entry |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.amg` (file `engine/amg/__init__.py`; the function is in `engine/amg/entry.py` and is exported from the package) |
| Function name | `run_amg` |
| Argument `forcing` | `"CarbonForcing"`: contract of blueprint section 5, producer Platform (L2a); PROPOSED model `contracts/carbon_forcing/models.py`, class `CarbonForcing` (#155, D62). The same object for EP5 and EP6. It carries the monthly soil-cover series and the starting state of the soil carbon (D65) |
| Argument `parameters` | `dict[str, dict]`: the parameter catalogue as loaded by the runner, passed by keyword (Q3, D46, D56; given to this entry by D65). In `run_amg` it is keyword-only. PROPOSED |
| Return type | `CarbonBalance` (`contracts/carbon_balance/models.py`, PROPOSED, #199 and #205). The same type for EP5 and EP6 |

```text
run_amg(
    forcing: "CarbonForcing",
    *,
    parameters: dict[str, dict],
) -> CarbonBalance
```

The `*` is the signature as built in `engine/amg/entry.py`. EP1 and EP3 are written here without it; the route passes every argument by name (G3), so both forms accept the same call. On `main` `compute_soil_loss`, `compute_water_deficit_exposure`, `build_residue_ledger`, `run_amg` and `run_rothc` all take `parameters` keyword-only.

**Status of the function.** `engine.amg.run_amg` exists (#199, #205; `engine/amg/README.md`, section "EP5 run_amg"). It runs **AMG-A only**, the annual reference that takes part in the selection (D80 of issue #77), with `carbon_model` `amg` (D1) and `variant` `amg_a` (the label is PROPOSED: `contracts/carbon_balance/README.md`, OPEN 2). AMG-M, the monthly variant, is experimental under D80, casts no carbon vote, and is not part of `EP1`–`EP6` or wired into `api/engines.py` (a standalone `PROPOSED` helper `run_amg_monthly` now exists in `engine/amg/monthly_entry.py`, `#477`, `#467`; see [Standalone non-EP engine helpers](#standalone-non-ep-engine-helpers-proposed-not-in-ep1ep6)). The runner in `api/engines.py` calls EP5 (#219; `_run_phase`), on the forcing that `api/carbon_forcing.py` builds.

**AMGv2 as printed (D192, D193, D199; #305).** [D192 of #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890256765) (taken under the delegation of D161): "EP5 computes AMGv2 as printed in Clivot et al. (2019)". On `main` the rate coefficient of `run_amg` multiplies the six modifiers of the source (`MODIFIERS` in `engine/amg/entry.py`: temperature, moisture, clay, carbonate, pH and C:N ratio), the temperature modifier is zero at or below zero (the cut of S8), and the yearly step is the exact exponential solution (`SCHEME = "exponential"`). The soil C:N ratio is read from `CarbonForcing.soil_properties` as the quantity `soil_cn_ratio` (`FORCING_QUANTITIES`; D193), and the three constants of the C:N modifier are records (`amg_cn_ratio_sensitivity`, `amg_cn_ratio_optimum`, `amg_cn_ratio_minimum`; D192, [D199](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890371514)). The `variant` label stays `amg_a` (`VARIANT`; its vocabulary is OPEN). No value of AMG exists with the catalogue of `params/records/` until its records are signed: until then the values are missing with their reasons (G4).

**Arguments decided** (decided by the lead developer on 14 November 2026, issue #77, D65): EP5 and EP6 keep the same arguments, and both take `parameters`, as EP1 and EP3 do (D46, D56). The monthly soil-cover series and the starting state travel inside `"CarbonForcing"`, not as separate arguments. G1, G3 and the two rows of G4 for a parameter apply to `parameters` here as they do for EP1 and EP3. The fields that carry the two inputs are PROPOSED in `contracts/carbon_forcing/` (`soil_cover`, `starting_state`); which quantities, pools and units they hold stays `OPEN` there.

What it returns: a `CarbonBalance`: the total soil carbon, the pools and the flows of each step, and the three values of `soil_carbon_trend` for this model, all inside it (PROPOSED: the state at the end of the horizon is the last step of each stock series, and no separate state is returned). Its horizon, soil depth, `example_data` and identifiers are those of the forcing.

Why it is `PROPOSED` and no longer `OPEN`: the return type now exists as a PROPOSED model, so the signature is a proposal that a person accepts or corrects in the pull request. What stays `OPEN` is under Q14: whether the residue ledger is an argument (Q14 (b)), and the second variant (Q14 (d)). The acceptance of the shape of `CarbonBalance` is OPEN 1 of `contracts/carbon_balance/README.md`.

When it cannot compute: it returns a `CarbonBalance` in which every value that is not computed is missing with its reason (G4), and each of the three computations of C1.6 is present for this model, one that is not computed being missing with its reason. Values of the two carbon models are never merged (C1.5). `run_amg` raises only `TypeError`, when `forcing` is not a `CarbonForcing` or `parameters` is not a `dict[str, dict]` (G5); no `ValueError` of G5 arises, because the one argument that carries identifiers is `forcing`.

Carbon inputs and phases (D147, D132):

- By [D147](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649): "The annual carbon-input series that EP4 writes for `CarbonForcing.annual_carbon_inputs` are in **`t C ha-1`**", and "The runner and AMG do no arithmetic on them". `run_amg` accepts a carbon-input series in that unit only and converts nothing: a number of a series in another unit is not read and becomes missing with reason `NOT_COMPUTABLE` (`engine/amg/entry.py`). That reason is the code as built, not a rule of this file: which reason code an input in a unit that the engine does not accept takes stays open (G4, Q11).
- [D132](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652) names EP5 among the entry points that receive the moved calendar. `run_amg` has no calendar argument. On `main` the runner builds one `CarbonForcing` per phase from the calendar of that phase (`api/carbon_forcing.py`, including the [D181](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889843938) annual water balance `P + IW - ET0` in `m` built in `#371` using daily `ET0` from `D256` `#412`) and calls `run_amg` once per phase (`_run_phase` in `api/engines.py`). The signature above is unchanged.

### EP6 `engine/rothc/`

Status: PROPOSED

| Aspect | Entry |
|---|---|
| Lane | L2b Platform: decision and carbon (interface developer) |
| Module path | `engine.rothc` (file `engine/rothc/__init__.py`) |
| Function name | `run_rothc` |
| Argument `forcing` | `"CarbonForcing"`: contract of blueprint section 5, producer Platform (L2a); PROPOSED model `contracts/carbon_forcing/models.py`, class `CarbonForcing` (#155, D62). The same object for EP5 and EP6. It carries the monthly soil-cover series and the starting state of the soil carbon (D65) |
| Argument `parameters` | `dict[str, dict]`: the parameter catalogue as loaded by the runner, passed by keyword (Q3, D46, D56; given to this entry by D65). Keyword-only in `run_rothc`, as in `run_amg`. PROPOSED |
| Return type | `CarbonBalance` (`contracts/carbon_balance/models.py`, PROPOSED, #199 and #205). The same type for EP5 and EP6, with `carbon_model` `rothc` (D1) |

```text
run_rothc(
    forcing: "CarbonForcing",
    *,
    parameters: dict[str, dict],
) -> CarbonBalance
```

**Arguments decided** (issue #77, D65), as for EP5: EP5 and EP6 have the same arguments, so that both carbon models receive the same inputs (blueprint section 5) and the route calls them in the same way. The soil-cover series and the starting state that the RothC brief (#176) proposed as two further arguments of this entry travel inside `"CarbonForcing"` instead.

Return type, PROPOSED: `CarbonBalance`, the same as EP5, so that the runner reads both in the same way (`contracts/carbon_balance/README.md`). The contract takes a step list that may be annual or monthly, and `test_monthly_steps_load_for_the_other_carbon_model` in `contracts/carbon_balance/` shows that shape loading.

**Status on `main` (`b107d7a`, matching `engine/rothc/README.md`).** `engine.rothc.run_rothc(forcing, *, parameters)` exists in `engine/rothc/entry.py` (#247, extended in #339 for D218–D219 equilibrium spin-up and D223–D224): it returns a `CarbonBalance` of carbon model `rothc`, variant `rothc_26_3` (`VARIANT`, PROPOSED; D64 names "RothC-26.3"), with monthly steps. The runner discovers it by this module path and function name (`ROTHC` in `DISCOVERED`, `api/engines.py`) and calls it after EP5, on the same `CarbonForcing` object (with D221 monthly `carbon_inputs` wired in `#350` and D222 monthly `soil_cover` wired in `#431`), with the catalogue by keyword, only when `rothc` is a configured carbon model (#282, #409, `_run_phase`). Its rows of `soil_carbon_trend` are copied after those of EP5. No value of RothC exists with the catalogue of `params/records/` until its records are signed. Everything in this entry remains `PROPOSED` and unapproved until maintainer (interface developer, lead developer, and platform developer) and science-reviewer sign-off under blueprint section 3.7; its `variant` vocabulary, pool/flow identifiers and units, `CarbonBalance` shape acceptance (`contracts/carbon_balance/README.md`, OPEN 1–3), `D149`/`D150`, and unsigned `rothc_*` parameter records remain `OPEN`.

When it cannot compute: as EP5.

### Standalone non-EP engine helpers (`PROPOSED`, not in `EP1`–`EP6`)

The `EP1`–`EP6` summary table above lists only the six numbered entry points discovered by `api/engines.py` (`DISCOVERED`). Outside `EP1`–`EP6` (and alongside `daily_reference_evapotranspiration` of D256 above), the following standalone `PROPOSED` helpers exist on `main` (`b107d7a`) and remain unapproved until maintainer and science-reviewer sign-off under blueprint section 3.7:

- **`engine/water/frost_heat.py` — `count_monthly_frost_and_heat_days` (`#478`):** `count_monthly_frost_and_heat_days(climate: SiteClimate, *, frost_threshold_deg_c: float | int | Missing, heat_threshold_deg_c: float | int | Missing) -> list[MonthlyFrostHeatCount]` (blueprint section 8 gated extras; `contracts/CLIMATE_QUANTITIES.md` Need N3). Pure standalone helper (`G1`, `G4`, `G5`); **not** exported in `engine/water/__init__.py` and **not** wired into EP3 or `api/engines.py`. Boundary equality (`<=` / `>=` vs `<` / `>`) remains `OPEN` for science-reviewer confirmation.
- **`engine/amg/monthly_entry.py` — `run_amg_monthly` (`#477`, `#467`):** `run_amg_monthly(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance` (experimental monthly AMG-M variant `amg_m` under D80, stepping monthly over `CarbonForcing.climate` and `CarbonForcing.carbon_inputs` with the exact exponential scheme). Pure standalone helper (`G1`, `G4`, `G5`); **not** in `EP1`–`EP6`, **not** discovered by `api/engines.py`, and casts no carbon vote under D80.
- **`engine/water/yearly_runoff.py` — `compute_calendar_year_runoff` (`#501`):** `PROPOSED` calendar-year surface runoff bridge over EP3's daily chain for validation check `[H10]` (`D229`, `D230`), paired with the signed H10 numeric fixture `validation/fixtures/h10_grahmann2022_runoff.json` (`#516`, `b107d7a`); **not** in `EP1`–`EP6` and **not** wired into `api/engines.py` (Curve Number and soil-profile records for the H10 plot run remain unsigned).

## From the entry points to one response

The route itself is not defined here. This section only says which entry point gives each part of `ResultsPerRotation` (`contracts/results/models.py`), so that what is not covered can be seen.

| Part of `ResultsPerRotation` | Comes from |
|---|---|
| `case_id`, `field_id`, `rotation_id` | The `RotationCalendar` returned by EP2 carries the same three |
| `soil_loss` | EP1, unchanged when it returns a `SoilLossResults`. For the other case see Q4, now answered: that case no longer reaches an engine. While EP1 is not built: the part is wholly missing, reason `NOT_AVAILABLE` only (D12; the form is PROPOSED, `PartNotBuilt` in `contracts/results/models.py`, question 21 of `contracts/results/README.md`) |
| `water_deficit_exposure` | EP3, unchanged. While EP3 is not built: the part is wholly missing, reason `NOT_AVAILABLE` only (D12; the form is PROPOSED, as for `soil_loss`) |
| `soil_carbon_trend` | EP5 and EP6, PROPOSED: the list `soil_carbon_trend` of the `CarbonBalance` each returns, copied unchanged, one balance after the other (see the mapping below). While no carbon engine is built: the part is wholly missing, reason `NOT_AVAILABLE` only (D12; the form is PROPOSED, `SoilCarbonTrendNotBuilt` in `contracts/results/models.py`). On `main` the runner calls EP5 and then EP6, each when its carbon model is configured, and copies the three rows of the balance of EP5, then those of EP6 (`carbon_trend` in `api/engines.py`; #219, #282). A configured model whose engine is not built gets its three rows missing `NOT_AVAILABLE`, naming its engine function, as long as EP4 or the other carbon engine is built; only when EP4, EP5 and EP6 are all not built do the rows carry the detail "no carbon engine is built yet", which names no function, three rows for each configured model (`carbon_trend` and `missing_carbon_trend` in `api/engines.py`). A configured model whose engine is built but not called, because the forcing cannot be laid out, gets its three rows missing with the forcing's own reason (`_run_phase`) |

- EP2 is called first. EP1, EP3 and EP4 take its result, also when the calendar is infeasible: the engine, not its caller, writes the missing values and their reason.
- No entry point returns a `ResultsTable` or a whole `ResultsPerRotation`: Q15.
- **Phases (D109, D132, D141).** By [D132](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652): "For a rotation whose cycle lasts N years, the runner makes N runs. Phase p lays the calendar's year p on the first agricultural year of the record." On `main` EP2 is called once. Then EP1, EP3, EP4 and EP5 are called once per phase, with the same site data and the same `parameters`: EP1, EP3 and EP4 on the calendar of that phase, and EP5 on a `CarbonForcing` built from that calendar (see EP5; `_run_phase` in `api/engines.py`). The first phase runs on the calendar of EP2 unchanged. Every other phase runs on what `phase_calendar` returns (see EP2), which the runner checks and uses as returned. By [D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713) the runner refuses no phase (`api/phases.py`). An infeasible calendar runs once. Since #282 EP6 runs in each phase too, after EP5 and on the same `CarbonForcing` object (see EP6). The `scenario_id` of a phase and the shape of the response per phase are the platform's, PROPOSED in `api/phases.py` and `api/README.md` (D132: "The shape of the response per phase is PROPOSED in the platform pull request, for the interface developer to accept"). This file does not define them.
- **Carbon inputs (D147).** The runner copies the annual carbon-input series of the `ResidueLedger` of EP4 unchanged into `CarbonForcing.annual_carbon_inputs`, which EP5 reads, and converts no unit: by [D147](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649) EP4 writes them in `t C ha-1`. The ledger itself is not in the response.
- **The computed `C` (D148).** [D148](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333) withdraws the computed `C` from the demonstration (see EP1), and under D158/D164 (`#274`) the 61 computed-`C`-only records sit in `params/withdrawn/computed_c/` while the 6 shared yield/ratio records remain in `params/records/residues/`. It changes no part of the shape of `ResultsPerRotation` and no row of the table above.
- **Reconciled on `main` (`b107d7a`).** On `main` (`b107d7a`), `EP1`–`EP6` are all built and wired in `api/engines.py`, and the `"Not built"` rows in the table above describe only the typed absence fallback when an engine is absent. The summary table, the `Types used in the signatures` rows for `RotationDefinition` and `ResidueLedger`, the EP2 `rotation` argument, and the EP4 and EP6 status lines have been reconciled with `main` (`b107d7a`), while keeping `PROPOSED` governance status until maintainer and science-reviewer sign-off under blueprint section 3.7. Outside `EP1`–`EP6`, `D229`/`D230` (`engine/water/yearly_runoff.py` and signed H10 fixture `validation/fixtures/h10_grahmann2022_runoff.json` in `#516`) and `D240`/`D258` (`kinds_of_year/` `#422`, `POST /api/plant/run` `#427`, and signed `kinds_of_year/records/oni_v6.json` in `#510`) are also landed on `main` (`b107d7a`).

### Mapping of `soil_carbon_trend`, PROPOSED

Restates what `contracts/carbon_balance/README.md` (OPEN 5) and `contracts/results/models.py` already say, for the platform developer to accept or correct. It adds no rule to either.

1. **Where the values come from.** Each carbon entry point returns the three values of `soil_carbon_trend` for its own model inside its `CarbonBalance` (`end_minus_start`, `fitted_slope` and `mean_over_cycles`, each naming `carbon_model`; C1.5, C1.6). The balance already checks that it carries the three once each and that all name its model.
2. **How they reach the response.** The part `soil_carbon_trend` of `ResultsPerRotation` is the list of the balance of EP5 (`carbon_model` `amg`) followed by the list of the balance of EP6 (`carbon_model` `rothc`). Each item is copied as it is: its value, unit, direction, provenance, source or assumption mark, range or reason, and its missing part. Nothing is added, summed, averaged, converted or reordered inside a list, and the items of the two models are never merged (C1.5). `ResultsPerRotation` already checks that each model present carries the three computations once.
3. **A balance with missing values.** A balance whose values are not computed still carries the three items, each missing with its reason (G4). They are copied like any other item. The part is then present, not wholly missing: the wholly missing form is only for an engine that is not built (D12).
4. **A carbon engine that is not built.** On `main` both carbon engines are built and the runner calls them (#219, #282), so this case arises only for an engine tree without one of them. The runner then writes, for a configured model whose engine is not built, its three computations missing with `NOT_AVAILABLE`, naming its engine function, as long as EP4 or the other carbon engine is built; only when EP4, EP5 and EP6 are all not built, three rows for each configured model with the detail "no carbon engine is built yet" (`carbon_trend` and `missing_carbon_trend` in `api/engines.py`). PROPOSED: when EP5 is built and EP6 is not, the part keeps the three items of `amg` from its balance and the three items of `rothc` missing `NOT_AVAILABLE`, as today. A model is never left out of the list without a typed absence (G4). When neither is built the part is as today, or the wholly missing form of D12; which of the two is item 4 of "Still `OPEN` for the mapping" in Q15.
5. **Who does it.** The runner, a function of lane L2a that is not one of the engines (Q15 (a)); no engine, and no model of `contracts/`, changes for it.
6. **Identifiers.** `amg` and `rothc` are the two values of `CarbonModel` in `contracts/results/models.py` (D1), and each balance names its own in `carbon_model`; the identifiers the runner is configured with are those of question 7 of `contracts/results/README.md`.

What this mapping needs before the runner can use it is listed as items 1 to 4 under "Still `OPEN` for the mapping" in Q15.

## OPEN

Each item is a question a person can answer. The role that answers it is named at the end of the item.

**Q1. Which import path do the route and the engines use for the contract models and for the engine functions?** `contracts/` has no `__init__.py`. The verifier of the input contracts found that under pytest the two contract packages load as top-level `inputs` and `results`, not as `contracts.inputs` and `contracts.results`. This unit does not fix that and takes no side: it names every model by file and class, and writes the module path of an engine from the repository root. The answer matters for G5: a model file loaded under two names gives two different classes, and an argument built from one is not an instance of the other. The same question holds for `engine/`: whether it is a package and how the route imports from it. For the platform developer.

**Q2. Does the route see one function for `engine/water/`, or two?** EP3 proposes one, with its reasons. If it is two, the function of `engine/water/et0/` needs a return type, and no contract of blueprint section 5 carries the reference evapotranspiration. For the lead developer.

**Q3. How do the values of the parameter catalogue reach an engine?** G1 says an engine reads no file, and no contract of blueprint section 5 carries parameters, so no signature here has an argument for them. Either the engines import the catalogue as code, and a person says that this is allowed under G1; or every entry point that needs parameters gains an argument, and its type has to be defined as a new contract. The session lists this case as decision 2 of issue #58 asks, without breaking the rule. For the lead developer, who owns the structure of `params/`, and the platform developer.

- `DECIDED` (decided by the lead developer on 14 November 2026, [issue #77, D46](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346); agreed by the platform developer in [issue #18](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/18#issuecomment-6882360229) on two conditions, both accepted as [D56](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882499943)): **the runner loads the catalogue and passes it to the entry point as an argument `parameters`**, so the engines stay pure (G1).
- What D56 fixes, written in this file:
  - the name is `parameters`, passed by keyword (G3);
  - its type is the catalogue of `params/` as loaded (see the table of types);
  - a parameter that is not in the catalogue makes the value that needs it missing with `MISSING_INPUT`, the parameter named in `detail` (G4);
  - the argument is added to EP1 and EP3 only; EP2 keeps `build_rotation_calendar(rotation)`.
- `PROPOSED` by the session that wrote this answer, for the platform developer's approval:
  - the type: the dictionary that `params.catalogue.load_folder` returns, unchanged;
  - an entry point finds a record by its `id` and its `scope` (`params.catalogue.identity`), never by the path of its file, as `params/README.md` says;
  - an entry point reads a value with `params.catalogue.read_value` and a range with `params.catalogue.read_range`, and rewrites the `Missing` of `params/catalogue.py` as the `Missing` of `contracts/results/models.py`;
  - the runner passes the catalogue only after `params.catalogue.check_catalogue` reports no problem for it;
  - the two rows of G4 for a parameter.
- Still `OPEN`:
  - What the runner does when the catalogue has a problem (a malformed record, a duplicate, a placeholder): it could answer an error or pass no catalogue. For the platform developer.
  - Which record an engine reads when one record has the empty scope and another names a crop. This is question 5 of `params/README.md`. For the lead developer.
  - Whether the catalogue later becomes a model class of its own, so that G3 needs no exception. For the lead developer and the platform developer.
  - The candidates of EP4, EP5 and EP6 did not have the argument when this was written. On `main` each takes it by keyword: EP4 `build_residue_ledger` since #235 (`259f5aa`), EP5 `run_amg` since #199 (`a728b8d`), EP6 `run_rothc` since #247 (`eb1dd39`).
- Changed on `main` since this point was written: EP1 `compute_soil_loss` takes `parameters` by keyword since #158 (`67adc0a`), EP3 `compute_water_deficit_exposure` since #165 (`6b961e5`), and the runner in `api/engines.py` passes the catalogue to both, always, since #172 (`9ec3223`).

**Q4. What does EP1 return when the agricultural years cannot be laid out?** `RotationCalendar` accepts a start month that is missing with its reason. `SoilLossResults` needs at least one agricultural year with its number, and twelve dated months for each, so it has no valid form for that case. EP1 proposes to return a `Missing` in its place. The field `soil_loss` of `ResultsPerRotation` cannot hold a `Missing`, so the route has no valid `ResultsPerRotation` for that request. The options are: `SoilLossResults` gains a wholly missing form (a change of the model, a new L0 unit); or a request without a start month is not a valid request; or the response of the route is not a bare `ResultsPerRotation`. For the lead developer; the platform developer for the response.

- `DECIDED` (decided by the lead developer on 14 November 2026, issue #77, D7): **the start month is a required part of the request.** It follows convention C5.4: a person declares it per case, marked provisional. A request without it is an invalid request: the route answers it as such and calls no engine. The case "no start month" no longer reaches an engine.
- What this makes out of date in this file: the point of EP1 on a missing start month, the point of EP2 on a start month that was not declared, and "the other case" of `soil_loss` in [From the entry points to one response](#from-the-entry-points-to-one-response). Each is marked where it stands.
- Changed on `main` since this point was written: the rotation definition carries the start month, required and never missing, and the calendar engine copies it into the calendar (Q8; both by #129, `fc6d2e2`). Not changed: `RotationCalendar` still accepts a start month that is missing with its reason (`AgYearStart` of `contracts/inputs/rotation_calendar.py`), and the signature of EP1 is left as it was written. Issue #77 does not say whether the return type of EP1 changes.

**Q5. Which agricultural years does a result list?** The years covered by the calendar (`start_date` to `end_date`), the years of the climate record, or only those in both? EP1 and EP3 must list the same years for one rotation, and no model checks that. This follows from question 6 of `contracts/inputs/README.md`. For the lead developer.

- `DECIDED` (decided by the lead developer on 14 November 2026, [issue #77, D47](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346)): **every agricultural year of the climate record, cut by the start month of the case**, with the rotation repeated over them. The record runs from 2001-01-01 to 2024-12-31 (D29). A calendar whose own dates lie outside the record still runs on the years of the record. So the calendar's `start_date` and `end_date` do not choose the years, and EP1 and EP3 list the same years: those of the record.
- `DECIDED` (decided by the lead developer on 14 November 2026, [issue #77, D109](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886058061); a science decision taken by the lead developer as scientific lead, which a science reviewer may still review): **how the rotation is repeated over the years of the record.** "Each phase of a rotation is a scenario. The rotation runs once per phase, each phase starting in the first agricultural year of the record (2001, D29, D47); cycles repeat; a cycle that does not fit whole is cut at the end of the record. Each phase has its own `scenario_id`, so D74 asks for robustness in every phase, and D96 summarises across them. A one-year rotation has one phase." This answers the part that the previous `OPEN` bullet of this question left to the lead developer and the science reviewers.
- `DECIDED` (decided by the lead developer on 15 November 2026, [issue #77, D117](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886636603); a logic decision of the lead developer): **how the phases of D109 combine with the one-input sweep of D3 as D103 reads it.** "The phases are nested inside each value of the input. The state at a value of the input is the state over all the phases at that value, read as D74 reads a set of scenarios: a robust preference only if it is one in every phase, otherwise 'Not robust across scenarios' (D88). The tipping point of D3 is the bracket between adjacent values where that state changes. A phase is not an uncertain input: it repeats the comparison over how each crop falls on the historical years, the person knows the phase of the field, and it never enters the priority list of D4." It answers the question that the comment recording D109 left open: how the phases of D109 combine with the one-input sweep of D3 as D103 reads it.
- `DECIDED` (decided by the lead developer on 15 November 2026, [issue #77, D132](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652)): **how a phase of D109 reaches the engines.** "(b), a calendar the runner moves. For a rotation whose cycle lasts N years, the runner makes N runs. Phase p lays the calendar's year p on the first agricultural year of the record. EP1, EP3 and EP5 receive the moved `RotationCalendar`; their signatures do not change (D56). The phase rule lives in one place: `engine/calendar` provides `phase_calendar(calendar, p) -> RotationCalendar` and `list_phases(calendar)` (unit #221), and the runner calls them without computing anything scientific. Each phase carries its own `scenario_id` (D109). The shape of the response per phase is PROPOSED in the platform pull request, for the interface developer to accept."
- `DECIDED` in the same comment ([issue #77, D133](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652)), and **amended by D141, next**: a crop component that starts before the first agricultural year of the record and ends inside it, once a phase is laid out. "No rule in this release. The days of such a component that fall before the record are not filled. The days inside the record that depend on the part before it are missing with their reason (C3.2), never guessed. The engines and the runner name the case instead of choosing a convention."
- `DECIDED` (decided by the lead developer on 15 November 2026, [issue #77, D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713); it amends D133): "Each phase is laid out as the first one already is. A component that starts before the first agricultural year of the record and ends inside it keeps its declared dates. The part before the record falls outside the record and is not described, exactly as `repeat_over_record` treats the first phase (D47). Inside the record, the component is present from the first day of the record and is computed normally. No date is moved and no value is guessed: the convention is the one the first phase already uses, now applied to every phase. Where an engine cannot compute a quantity because it would need the part before the record (for example, a state carried in from it), that quantity stays missing with its reason (C3.2), as for the first phase. Science class: a science reviewer may still review it."
- Changed on `main` for D109, D132 and D141, after the point "Not changed yet, for D109" below was written:
  - the runner makes one run per phase and refuses no phase (`api/phases.py` and `api/engines.py`, lane L2a, #227 and #245);
  - `phase_calendar`, `list_phases` and `components_crossing_phase` are in `engine/calendar/repeat.py` (lane L1, unit #221, pull requests #228 and #243), where `repeat_over_record` also lays out the cycle before the first (see EP2);
  - no signature and no model of `contracts/` changed with them;
  - the part of that point on the water engine is the text of its own unit (see EP3).
- Still `OPEN`. This question is not from a decision of issue #77: the session that wrote this section found it between D47, D29 and D109. **What "the first agricultural year of the record" is when the start month of the case is not January.** D47 cuts the years of the record by the start month, and the record begins on 2001-01-01 (D29), so the first agricultural year may not be covered from its first day (C5.5, reason `NO_COVERAGE`, in the next bullets). D109 says "the first agricultural year of the record (2001, ...)" and does not say whether that year is the first one the record covers whole. For the lead developer.
- Not changed yet, for D109: `engine/water/EXPOSURE.md` (OPEN 5), `_crop_of_day` in the water engine (lane L1) and the runner, which builds one call per phase (platform developer): the comment that records D109 names them as follow-ups. No engine, route or model changed with this text. Q6 below says "one call is one scenario"; D109 makes each phase one.
- Still `OPEN`: which daily series marks the record for each engine, when the series of one record do not cover the same days. Issue #77 does not say. Issue #115 proposes the `precipitation` series for EP1. For the lead developer.
- Not changed yet: no model, engine or route changed with this answer. An agricultural year that the record does not cover from its first day to its last stays missing with reason `NO_COVERAGE` (C5.5).

**Q6. How does a scenario reach an engine, and who gives a value its range?** `scenario_id` is in the rows of `ResultsTable` and not in `ResultsPerRotation`, and no signature here has a scenario argument. Proposed: one call is one scenario; the caller builds one set of arguments per scenario and writes `scenario_id` when it builds the table rows. This holds only if a scenario changes nothing but the arguments of the entry points; a scenario that changes a parameter falls under Q3. Also: with one call per scenario, an engine has nothing to compute a range from, so every number it returns carries `range_missing` and its reason. Is that intended, and which reason code does it use? What a scenario holds is question 9 of `contracts/results/README.md`. For the lead developer; the science reviewers for what a scenario and a range are.

**Q7. May an engine raise for the two caller defects of G5?** The alternative is that an engine never raises and answers these with missing values too. For the platform developer.

**Q8. What does the calendar engine receive besides the rotation definition?** Two parts. (a) `RotationCalendar` needs `case_id`, `field_id`, `rotation_id`, the start month of the agricultural year (C5.4) and the first and last date of the calendar. Does the "Rotation definition" contract carry all of them? If not, each one that it does not carry is a further argument of EP2, and the route has to be told where it comes from in a request `{ "site", "rotation" }`. (b) Does any calendar rule need site data, for example the climate record? If so EP2 gains the argument `climate: SiteClimate`. For the lead developer, as owner of lane L1, and the interface developer, as producer of the rotation definition.

- `DECIDED` for the start month of part (a) (decided by the lead developer on 14 November 2026, issue #77, D8): the start month travels **in the rotation definition**, with its provisional mark. The calendar engine copies it into the calendar.
- Changed on `main` since this point was written: the rotation definition carries the start month (`ag_year_start`, required, never missing, with its provisional mark), and the calendar engine copies it into the calendar (`_copy_start_month` of `engine/calendar/build.py`), both by #129 (`fc6d2e2`).
- Still `OPEN`, to be supplied by people: **the provisional month of each case** (convention C5.4). For the person who declares the case.
- Still `OPEN`, not answered by issue #77: the rest of part (a), and part (b). For the same roles as before.

**Q9. Is the argument of EP2 the request item itself?** Issue #18 says `rotation` in the request body is one item of the "Rotation definition" contract, unchanged. EP2 assumes the route passes that item as it is, loaded into its model. For the platform developer and the interface developer.

**Q10. Do the inputs and the output of EP3 cover what the water engine needs and gives?** Two parts. (a) Inputs: do `SiteClimate` and `SiteSoilSlope` carry everything the methods of the water engine need? Neither carries anything about the place of the field (question 21 of `contracts/inputs/README.md`). If something is missing, it is a field of a contract or a further argument. For the science reviewers, who decide the method and its inputs, and the platform developer, who produces the site data. (b) Outputs: EP3 returns the indicator only. The reference evapotranspiration, the daily balance and the three descriptive measures of C1.4 have no contract, so the route cannot pass them on. Does the interface need any of them? If so, a contract is needed first and the return type of EP3 changes. For the lead developer and the interface developer.

- `DECIDED` for latitude and elevation, in part (a) (decided by the lead developer on 14 November 2026, issue #77, D9): they reach the water engine **in the "Site data: climate" contract**: the point the series is valid for (latitude, longitude, elevation), with its provenance label and source. The signature of the water entry point does not change.
- Changed on `main` since this point was written: `SiteClimate` carries `point` (latitude, longitude, elevation; required, each value a number or missing with its reason; `ClimatePoint` of `contracts/inputs/site_climate.py`), and the NASA POWER adapter fills it (`adapters/power_mapping.py`), both by #101 (`85bb969`). The daily reference evapotranspiration reads latitude and elevation from it (`engine/water/et0/daily.py`).
- Still `OPEN`, not answered by issue #77: whether the two models carry everything else the methods of the water engine need (the rest of part (a)), and part (b). For the same roles as before.

**Q11. Which reason code does an engine use for an input in a unit it does not accept?** C1.1 says a consumer checks the unit it receives. G5 proposes that the engine does not raise. `NOT_COMPUTABLE` and `CONTROL_FAILED` are the two codes of C3.2 that could apply. For the lead developer.

**Q12. Does the erosion engine consume the residue ledger?** Blueprint section 5 names the lead lane as a consumer of `ResidueLedger`. If the erosion engine is that consumer, EP1 gains the argument `residues: "ResidueLedger"` and EP4 is called before EP1. For the lead developer.

**Q13. What is the residue ledger computed from, and what is its contract?** Historically, EP4 was `OPEN` until the `ResidueLedger` contract existed and a person named its inputs (`contracts/residue_ledger/` and `engine/residues/` are now built on `main` as `PROPOSED`; formal acceptance remains pending). The contract lets every value be missing with its reason. For the lead developer, as owner of lane L1; the science reviewers for what the ledger is computed from.

- `PROPOSED` by unit `l1/residue-ledger-ep4` (brief #220, at the lead developer's request after D122 of #77), for the lead developer's approval:
  - the contract `contracts/residue_ledger/`;
  - the signature of EP4 above: `rotation`, `calendar`, `climate` and keyword-only `parameters`, returning `ResidueLedger`;
  - the residue at harvest from the records of D129 (c) (`rusle2_residue_yield_ratio` × `rusle2_crop_yield`, by crop), with the identifiers #218 fixed (PR #229);
  - five more records by crop: `residue_carbon_fraction`, `residue_removed_fraction`, `root_mass_at_harvest`, `root_carbon_fraction`, `rhizodeposit_carbon`.

  No site datum other than the period of the record and no result of another engine is read. EP4 takes `parameters`, which answers for EP4 the last bullet of Q3 ("whether they gain it").
- Still `OPEN`:
  - the dry-matter basis of the yield and whether the ratio is mass per mass (OPEN 2; CITATION NEEDED); who converts to the `t C ha-1` of AMG is decided by [D147](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649) (EP4 does);
  - how roots and rhizodeposits are computed, and any partition form, which would be a record with a cited source (OPEN 4; CITATION NEEDED);
  - a method for cover crops and pastures (OPEN 5);
  - when a residue enters the soil, and the zero of a year without a harvest (OPEN 6);
  - the acceptance of the contract's shape (`contracts/residue_ledger/README.md`, OPEN 1).

  For the lead developer and the science reviewers.

**Q14. What do the two carbon entry points receive and return?** EP5 and EP6 were `OPEN` until the `ModelState` and `CarbonBalance` contracts existed. `CarbonForcing` is PROPOSED in `contracts/carbon_forcing/` (#155, D62) and `CarbonBalance` in `contracts/carbon_balance/` (#199, #205); EP5 is `PROPOSED` and `run_amg` exists; `run_rothc` exists since #247 and the runner calls it since #282, and EP6 is now `PROPOSED` on its `Status:` line and in the summary table, matching `engine/rothc/README.md` (remaining unapproved until maintainer and science-reviewer sign-off under blueprint section 3.7; see EP6). Four parts. (a) `ModelState`: is it an argument (the starting state, the same for both models), part of what is returned, or both? (b) The residue ledger: does a carbon engine take `ResidueLedger` as an argument, or does `CarbonForcing` already hold what comes from it? `CarbonForcing` has `carbon_inputs` and `annual_carbon_inputs`, each series with an `origin`, whose identifiers D194 fixes (`<crop_id>_aboveground` and `<crop_id>_belowground`, built in #306; `contracts/carbon_forcing/README.md`, OPEN 4, still asks it). (c) The indicator: who computes the three values of `soil_carbon_trend` per model (C1.6): each carbon engine, which then returns `list[SoilCarbonTrend]` (`contracts/results/models.py`) next to the balance, or one function shared by both models, and in which folder does it live? (d) The two variants of AMG in blueprint section 8: does the one function return both, and how is each labelled? `CarbonForcing` now carries both monthly series and annual series (`annual_climate`, `annual_carbon_inputs`), at the lead developer's request on #155; which one each variant reads stays part of this question (`contracts/carbon_forcing/README.md`, OPEN 4). For the lead developer (EP5), the interface developer (EP6) and the platform developer, as producer of `CarbonForcing`.

- `DECIDED` for the starting state in part (a) (decided by the lead developer on 14 November 2026, issue #77, D65): **the starting state is not an argument of its own; it travels inside `CarbonForcing`**, the same object for both models. D65 also gives EP5 and EP6 the argument `parameters` and places the monthly soil-cover series (`contracts/carbon_forcing/README.md`, OPEN 8) inside `CarbonForcing`. The fields are PROPOSED: `starting_state` and `soil_cover` of `contracts/carbon_forcing/models.py`.
- Still `OPEN` in part (a): whether the state at the end of the horizon is also returned, inside `"CarbonBalance"`; which pools the starting state holds, with which identifiers and units, and how it is obtained (`contracts/carbon_forcing/README.md`, OPEN 9); and whether the `ModelState` contract of blueprint section 5 later takes over the shape of `starting_state`. For the same roles as before; the science reviewers for the pools and units.
- `PROPOSED` for part (a), second half (#199, #205; `contracts/carbon_balance/README.md`, OPEN 4): the state at the end of the horizon is the last step of each stock series of `CarbonBalance`, and no separate `ModelState` is returned. Not decided by a person: whether the `ModelState` contract of blueprint section 5 takes this over.
- `PROPOSED` for part (c) (`contracts/carbon_balance/README.md`, OPEN 5; `engine/amg/README.md`): each carbon engine computes the three values of `soil_carbon_trend` for its own model and returns them inside its `CarbonBalance`, in the field `soil_carbon_trend` (a list of `SoilCarbonTrend`), so no function shared by the two models is needed. EP5 does it (`engine.amg.trend`). The runner copying them into `ResultsPerRotation` is the mapping in [From the entry points to one response](#from-the-entry-points-to-one-response). Not decided by a person.
- `PROPOSED` for part (d) as far as AMG goes: `run_amg` returns AMG-A only, as a `CarbonBalance` with `variant` `amg_a`; AMG-M is experimental and casts no carbon vote (D80) and is not built. Still `OPEN`: whether AMG-M is later a second `CarbonBalance` with another variant or a second function, the vocabulary of `variant` (`run_rothc` writes `rothc_26_3`, PROPOSED in `engine/rothc/entry.py` after D64's "RothC-26.3"), and which monthly or annual series of `CarbonForcing` each variant reads (`contracts/carbon_balance/README.md`, OPEN 2).
- `DECIDED` for the unit of the carbon inputs in part (b) (decided by the lead developer on 15 November 2026, [issue #77, D147](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649)): **EP4 converts.** "The annual carbon-input series that EP4 writes for `CarbonForcing.annual_carbon_inputs` are in **`t C ha-1`**, obtained from the ledger's `kg C ha-1` by the SI definition of the prefixes (1 t = 1000 kg). That is a definition, not a value of the method, so it needs no catalogue record. The masses and the carbon of the ledger itself stay in `kg ha-1`. The runner and AMG do no arithmetic on them (as the EP4 brief asked)." Built in `engine/residues/` (#235) and in the runner (#242, #245). It does not answer whether the ledger is an argument, next.
- Still `OPEN` in part (b), not answered by D65 or by #199: whether `ResidueLedger` is an argument of a carbon engine. `run_amg` takes none, and neither does `run_rothc`; `run_amg` reads the annual carbon inputs of `CarbonForcing` (`annual_carbon_inputs`), by origin, whose identifiers D194 fixes (`<crop_id>_aboveground`, `<crop_id>_belowground`; #306).
- Still `OPEN`: the pools, flows, identifiers and units of `CarbonBalance` (`contracts/carbon_balance/README.md`, OPEN 3), and its acceptance by the platform developer and the interface developer (OPEN 1).

**Q15. Who builds what no entry point returns?** Three parts. (a) `ResultsPerRotation` is put together from the results of EP1 and EP3 and the carbon values: by the route, or by a function that is not one of the six engines? (b) `ResultsTable`: which code builds it from several calls, and in which folder? (c) While an engine is not built, who writes its values as missing with reason `NOT_AVAILABLE` (C3.2)? For `soil_carbon_trend` that also needs the identifiers of the carbon models, which are question 7 of `contracts/results/README.md`. For the platform developer and the lead developer.

- `DECIDED` for the form of part (c) (decided by the lead developer on 14 November 2026, decision D12, recorded in [issue #18](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/18#issuecomment-6881785241) and [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6881787420)): while an engine is not built, its whole part of `ResultsPerRotation` (`soil_loss`, `water_deficit_exposure` or `soil_carbon_trend`) may be wholly missing, **only with reason `NOT_AVAILABLE`**. A built engine keeps the present form and G4.
- PROPOSED, not decided: the shape of a wholly missing part (`PartNotBuilt` in `contracts/results/models.py`; question 21 of `contracts/results/README.md`), for the platform developer and the interface developer to accept or rename.
- Not answered by D12: which code writes the wholly missing part, and parts (a) and (b). On `main` the runner in `api/engines.py` (lane L2a) writes it: a soil-loss or water engine that is not built gives its part in the not-built form (`part_not_built`) and the result is still returned; the carbon rows are those of the balances of EP5 and EP6, or missing `NOT_AVAILABLE` for a configured model whose engine is not built (`carbon_trend`; for `amg` when EP4 is built and EP5 is not, `_run_phase` writes those rows itself, naming EP5), or missing with the forcing's own reason for a configured model whose engine was not called because the forcing cannot be laid out (`missing_carbon_trend` in `_run_phase`).
- What #180, #199 and #205 change for part (a): the carbon values now have a producer and a place. Each carbon engine returns them inside its `CarbonBalance` (Q14 (c)), so the code that puts `ResultsPerRotation` together has them in hand, and no function other than the six engines has to compute them. The mapping from the balances to the part `soil_carbon_trend` is `PROPOSED` in [From the entry points to one response](#from-the-entry-points-to-one-response). Who puts the part together stays the runner, as today: not decided for the carbon part by a person. Part (b) is not changed by them.
- Still `OPEN` for the mapping, each for the platform developer unless said otherwise:
  1. Acceptance of `CarbonForcing` construction: on `main` (`b107d7a`), `api/carbon_forcing.py` (`build_carbon_forcing`, `#219`, `#242`, `#350`, `#371`, `#412`, `#431`) builds `CarbonForcing` and `api/engines.py` calls EP5 and EP6 (`#219`, `#282`), remaining `PROPOSED` until formal pull-request approval.
  2. How the runner checks that the forcing and the calendar describe the same rotation of the same field (`case_id`, `field_id`, `rotation_id`). G5 cannot do it: a carbon entry point has one argument that carries them, so it has nothing to compare.
  3. What the part holds when EP5 is built and EP6 is not (or the reverse): the proposal is the three items of the built model from its balance and the three items of the other missing `NOT_AVAILABLE`, as the runner writes them today. For the platform developer and the lead developer.
  4. What the part is when neither carbon engine is built: the items missing `NOT_AVAILABLE` of each configured model, as today, or the wholly missing form of D12 (`SoilCarbonTrendNotBuilt`, question 21 of `contracts/results/README.md`). For the platform developer and the interface developer.

**Q16. Where does a result say that it was computed from example data?** The three input models carry `example_data`. `ResultsPerRotation` and `ResultsTable` do not, so an engine cannot pass the mark on. Blueprint section 7 lets soil and slope come from the accepted example at the first checkpoint, shown as example data. Either the results models gain the mark, or the route carries it next to the result. For the lead developer and the platform developer.

### Questions of other files that these signatures depend on

They are not repeated here. An engine meets each of them before it can return a number.

| Question | Where |
|---|---|
| The closed list of `kind` labels of a range | C2.3; question 1 of `contracts/results/README.md` |
| The time basis of `water_deficit_exposure`: decided by D157 and D163, and built in EP3 (#296; see EP3); a value that is a number waits for signed records, not for code; still open only whether a monthly breakdown exists | C1.3; question 2 of `contracts/results/README.md` |
| The reason code for a definition that is not decided yet: amended by D157, and closed with the unit that builds D157 (D163); that unit is merged (#296), and the examples of `contracts/results/` that use `NOT_AVAILABLE` with a detail are not yet brought in line, as D163 asks | Question 4 of `contracts/results/README.md` |
| The identifiers of the carbon models | Question 7 of `contracts/results/README.md` |
| What `source` holds for a computed indicator | Question 11 of `contracts/results/README.md` |
| Which daily and monthly quantities and which soil properties exist, with which identifiers and units | Questions 9, 10, 16 and 18 of `contracts/inputs/README.md` |
| One shared value shape for every contract. Today `Missing` and `Range` exist twice, in `contracts/inputs/common.py` and in `contracts/results/models.py`, so an engine reads one and writes the other | Question 24 of `contracts/inputs/README.md`; question 19 of `contracts/results/README.md` |

## Not covered by this file

- The route, its request and response bodies and its error format (issue #18).
- Adapters, and how site data and `CarbonForcing` are produced.
- Decision functions: they are not engines.
- The functions inside an engine. Only the one function of each entry is public.
- Any method, equation, variable, unit, parameter value or threshold.
