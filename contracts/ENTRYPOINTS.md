# Engine entry points

The one public function of each engine: where it lives, its name, its arguments and what it returns (blueprint section 5). The route `POST /api/rotations/run` calls the engines only through these functions, so it can be built against signatures and not against unfinished engines.

## How to read this file

- This file was written by a builder session (blueprint section 3.7). Nothing here is in force until people approve the pull request: the lead developer, who owns lanes L0 and L1, and the platform developer, who builds the route against these signatures. The interface developer approves the entry of `engine/rothc/`, which belongs to sub-lane L2b.
- There is one entry per engine folder named in blueprint section 2. Every entry has an identifier (`EP1` to `EP6`) and exactly one status, given on its `Status:` line:
  - `PROPOSED`: the session proposes the module path, the function name, the arguments and the return type. A person accepts or corrects them in the pull request.
  - `OPEN`: the session cannot responsibly propose the signature. The entry gives a candidate, so that the question is concrete, and names the questions a person has to answer.
- A `PROPOSED` entry can still depend on a question. Questions are listed once, under [OPEN](#open), as `Q1` to `Q16`, each with the role that answers it.
- Three questions were answered by the lead developer on 14 November 2026 (issue #77): Q4, Q8 as far as the start month of the agricultural year goes, and Q10 as far as latitude and elevation go. Each keeps its number and its text, and carries the answer under it, marked `DECIDED`. They are a person's decisions, transcribed by a builder session. Issue #77 says of them: where they are science class, a science reviewer still has to accept them. No model and no route changed with these answers: each change is its own later unit, and until it lands the models behave as this file describes them. Q5 was answered the same day (issue #77, D47) and is recorded the same way. So is Q3 (D46, with the platform developer's conditions of D56). Its answer changes the signatures of EP1 and EP3 in this file before any engine or the runner changes.
- General rules that hold for every entry are `G1` to `G7`. They are all `PROPOSED`.
- No engine exists yet and the folder `engine/` does not exist. This file contains no code. A signature is written as text, in the notation of Python type hints.
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
| `"Rotation definition"` | Contract of blueprint section 5 that does not exist yet. `OPEN` |
| `"ResidueLedger"` | Contract of blueprint section 5 that does not exist yet. `OPEN` |
| `"CarbonForcing"` | PROPOSED model: file `contracts/carbon_forcing/models.py`, class `CarbonForcing` (#155, accepted into `contracts/` by D62 of #77). Its values (quantities, units, depth, horizon, aggregation) are `OPEN` in `contracts/carbon_forcing/README.md` |
| `"CarbonBalance"` | Contract of blueprint section 5 that does not exist yet. `OPEN` |

A name in double quotes is the blueprint name of a contract, not a class: its model, its file and its example are a separate unit. The models of `contracts/inputs/` and `contracts/results/` are themselves proposals; a signature follows them as they are in `main` and changes when they change.

## Rules for every entry point

Status of G1 to G7: PROPOSED

### G1 A pure function

An entry point receives data and returns data. It makes no network call, reads and writes no file, reads no environment variable and no clock, and does not change its arguments. The same arguments give the same result. Adapters fetch; the route passes what they return.

The values of the parameter catalogue reach an entry point as the argument `parameters`, loaded by the runner (Q3, D46). An entry point may call the pure functions of `params.catalogue` that read a record it was given (`read_value`, `read_range`, `identity`). It never calls `load_folder` or anything else that reads a file. PROPOSED.

### G2 One call is one rotation of one field

One call computes one rotation of one field from one set of inputs. Comparing rotations, repeating a call per scenario and building a results table are done by the caller (Q6, Q15).

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
| EP4 | `engine/residues/` | L1 Engines | `build_residue_ledger` | OPEN |
| EP5 | `engine/amg/` | L1 Engines | `run_amg` | OPEN |
| EP6 | `engine/rothc/` | L2b Platform: decision and carbon | `run_rothc` | OPEN |

Module paths are written from the repository root. Whether that is the import path is Q1.

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

Depends on: Q3 (parameters; answered: see the question), Q4 (answered: see the question), Q5 (which agricultural years; answered: see the question), Q11 (unit), Q12 (residue ledger).

### EP2 `engine/calendar/`

Status: PROPOSED

| Aspect | Entry |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.calendar` (file `engine/calendar/__init__.py`) |
| Function name | `build_rotation_calendar` |
| Argument `rotation` | `"Rotation definition"`: contract of blueprint section 5, producer Interface. It does not exist yet: `OPEN`. The item `rotation` of the request body, unchanged (issue #18) |
| Return type | `RotationCalendar` (`contracts/inputs/rotation_calendar.py`) |

```text
build_rotation_calendar(rotation: "Rotation definition") -> RotationCalendar
```

What it returns: always a `RotationCalendar`, feasible or not. It is the argument `calendar` of EP1, EP3 and EP4.

When it cannot compute:

- A rotation that breaks a calendar rule gives a calendar with `feasibility.feasible` false and at least one `RuleViolation`. The function does not raise. An engine that receives that calendar answers by G4.
- A date that cannot be placed is a `DateValue` with `date` null and its `missing` part: reason `NOT_DECLARED` when the user did not give what the date needs, otherwise the code of G4 that applies. No date is invented.
- A start month of the agricultural year that was not declared is an `AgYearStart` with `month` null and its `missing` part.
  - **This point no longer applies once the decision on Q4 is in force.** `DECIDED` by the lead developer on 14 November 2026 (issue #77, D7): a request without the start month is an invalid request, and the route answers it as such and calls no engine. The text above is kept to show what was proposed.
  - `DECIDED` on the same day (issue #77, D8): the start month travels in the rotation definition, with its provisional mark, and the calendar engine copies it into the calendar.
  - Not changed yet: the rotation definition does not carry the start month, and `RotationCalendar` still accepts a start month that is missing with its reason.
- `RotationCalendar` has no missing state for `case_id`, `field_id`, `rotation_id`, `start_date` and `end_date`. The function can return a valid calendar only if its arguments give all five. With the single argument above, the rotation definition has to carry them: Q8.

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

Why these arguments: the indicator is defined over the critical period of the crop (C1.4), which needs the calendar; the balance is daily (C1.4), which needs the daily series of `SiteClimate`; soil data reaches the engines lane through `SiteSoilSlope` (blueprint section 5). Which series and which soil properties the engine reads are questions 9 and 16 of `contracts/inputs/README.md`.

What it returns: a list with at least one `WaterDeficitExposure`, all on one time basis. It goes unchanged into the field `water_deficit_exposure` of `ResultsPerRotation`, which checks those two rules; a bare list is not checked by any model.

When it cannot compute:

- While the definition of the indicator is incomplete (C1.4), every item is missing, with its reason, in the unit `dimensionless`. The reason code for that case is question 4 of `contracts/results/README.md`; the examples use `NOT_AVAILABLE`.
- Otherwise G4 applies to every item.
- The list is never empty and an agricultural year is never left out.
- The time basis of the items is `OPEN` in C1.3. The signature is the same for either answer.

Depends on: Q2, Q3 (parameters; answered: see the question), Q5 (which agricultural years; answered: see the question), Q10 (inputs and outputs of the water engine; answered for latitude and elevation: they arrive in `climate`, and this signature does not change), Q11 (unit).

### EP4 `engine/residues/`

Status: OPEN

| Aspect | Candidate |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.residues` (file `engine/residues/__init__.py`) |
| Function name | `build_residue_ledger` |
| Argument `rotation` | `"Rotation definition"`: contract of blueprint section 5 that does not exist yet. `OPEN` |
| Argument `calendar` | `RotationCalendar` (`contracts/inputs/rotation_calendar.py`). The value returned by EP2 |
| Return type | `"ResidueLedger"`: contract of blueprint section 5, producer Engines. It does not exist yet: `OPEN` |

```text
build_residue_ledger(
    rotation: "Rotation definition",
    calendar: RotationCalendar,
) -> "ResidueLedger"
```

Why it is `OPEN`: the blueprint says what the ledger holds (biomass and carbon closure; export and retention; roots and cover kept apart) and not what it is computed from. The two arguments are a candidate only: what the user declares, and when. The session cannot say whether the ledger also needs site data, the result of another engine or values of the parameter catalogue. The question is Q13.

When it cannot compute: it returns a `"ResidueLedger"` in which every value that is not computed is missing with its reason (G4). For an infeasible calendar that reason is `NOT_COMPUTABLE`. This needs a `"ResidueLedger"` contract in which every value can be missing (C3.1); that is part of Q13.

### EP5 `engine/amg/`

Status: OPEN

| Aspect | Candidate |
|---|---|
| Lane | L1 Engines (lead developer) |
| Module path | `engine.amg` (file `engine/amg/__init__.py`) |
| Function name | `run_amg` |
| Argument `forcing` | `"CarbonForcing"`: contract of blueprint section 5, producer Platform (L2a); PROPOSED model `contracts/carbon_forcing/models.py`, class `CarbonForcing` (#155, D62). The same object for EP5 and EP6 |
| Return type | `"CarbonBalance"`: contract of blueprint section 5, producers Engines and Platform (L2b). It does not exist yet: `OPEN` |

```text
run_amg(forcing: "CarbonForcing") -> "CarbonBalance"
```

Why it is `OPEN`: both types are contracts that do not exist, and the candidate holds only what the table of blueprint section 5 states: `"CarbonForcing"` goes to both carbon models with the same inputs, climate and horizon, and each model produces a `"CarbonBalance"`. The candidate leaves out three things that the session cannot place: `ModelState`, the residue ledger, and the values of the indicator `soil_carbon_trend`. Blueprint section 8 also gives this engine two variants, an annual reference and a monthly adaptation. The questions are Q14.

When it cannot compute: it returns a `"CarbonBalance"` in which every value that is not computed is missing with its reason (G4); blueprint section 5 asks that contract for typed absences. Wherever the values of `soil_carbon_trend` travel (Q14), each of the three computations of C1.6 is present for this model, and one that is not computed is missing with its reason. Values of the two carbon models are never merged (C1.5).

### EP6 `engine/rothc/`

Status: OPEN

| Aspect | Candidate |
|---|---|
| Lane | L2b Platform: decision and carbon (interface developer) |
| Module path | `engine.rothc` (file `engine/rothc/__init__.py`) |
| Function name | `run_rothc` |
| Argument `forcing` | `"CarbonForcing"`: contract of blueprint section 5, producer Platform (L2a); PROPOSED model `contracts/carbon_forcing/models.py`, class `CarbonForcing` (#155, D62). The same object for EP5 and EP6 |
| Return type | `"CarbonBalance"`: contract of blueprint section 5, producers Engines and Platform (L2b). It does not exist yet: `OPEN` |

```text
run_rothc(forcing: "CarbonForcing") -> "CarbonBalance"
```

Why it is `OPEN`: for the same reasons as EP5. One point is proposed whatever the answers to Q14: EP5 and EP6 have the same arguments and the same return type, so that both carbon models receive the same inputs (blueprint section 5) and the route calls them in the same way.

When it cannot compute: as EP5.

## From the entry points to one response

The route itself is not defined here. This section only says which entry point gives each part of `ResultsPerRotation` (`contracts/results/models.py`), so that what is not covered can be seen.

| Part of `ResultsPerRotation` | Comes from |
|---|---|
| `case_id`, `field_id`, `rotation_id` | The `RotationCalendar` returned by EP2 carries the same three |
| `soil_loss` | EP1, unchanged when it returns a `SoilLossResults`. For the other case see Q4, now answered: that case no longer reaches an engine. While EP1 is not built: the part is wholly missing, reason `NOT_AVAILABLE` only (D12; the form is PROPOSED, `PartNotBuilt` in `contracts/results/models.py`, question 21 of `contracts/results/README.md`) |
| `water_deficit_exposure` | EP3, unchanged. While EP3 is not built: the part is wholly missing, reason `NOT_AVAILABLE` only (D12; the form is PROPOSED, as for `soil_loss`) |
| `soil_carbon_trend` | No entry point, as the candidates of EP5 and EP6 stand: Q14, Q15 |

- EP2 is called first. EP1, EP3 and EP4 take its result, also when the calendar is infeasible: the engine, not its caller, writes the missing values and their reason.
- No entry point returns a `ResultsTable` or a whole `ResultsPerRotation`: Q15.

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
  - The candidates of EP4, EP5 and EP6 do not have the argument. Whether they gain it is part of Q13 and Q14.
- Not changed yet: no engine and no runner uses the argument. The entry points of `engine/erosion/` (#125) and `engine/water/` and the runner in `api/engines.py` still take three arguments. D56 says this file states the argument first. Each engine and the runner change in their own later units, after the platform developer approves this one.

**Q4. What does EP1 return when the agricultural years cannot be laid out?** `RotationCalendar` accepts a start month that is missing with its reason. `SoilLossResults` needs at least one agricultural year with its number, and twelve dated months for each, so it has no valid form for that case. EP1 proposes to return a `Missing` in its place. The field `soil_loss` of `ResultsPerRotation` cannot hold a `Missing`, so the route has no valid `ResultsPerRotation` for that request. The options are: `SoilLossResults` gains a wholly missing form (a change of the model, a new L0 unit); or a request without a start month is not a valid request; or the response of the route is not a bare `ResultsPerRotation`. For the lead developer; the platform developer for the response.

- `DECIDED` (decided by the lead developer on 14 November 2026, issue #77, D7): **the start month is a required part of the request.** It follows convention C5.4: a person declares it per case, marked provisional. A request without it is an invalid request: the route answers it as such and calls no engine. The case "no start month" no longer reaches an engine.
- What this makes out of date in this file: the point of EP1 on a missing start month, the point of EP2 on a start month that was not declared, and "the other case" of `soil_loss` in [From the entry points to one response](#from-the-entry-points-to-one-response). Each is marked where it stands.
- Not changed yet: `RotationCalendar` still accepts a start month that is missing with its reason, the rotation definition does not carry the start month (Q8), and the signature of EP1 is left as it was written. Issue #77 does not say whether the return type of EP1 changes.

**Q5. Which agricultural years does a result list?** The years covered by the calendar (`start_date` to `end_date`), the years of the climate record, or only those in both? EP1 and EP3 must list the same years for one rotation, and no model checks that. This follows from question 6 of `contracts/inputs/README.md`. For the lead developer.

- `DECIDED` (decided by the lead developer on 14 November 2026, [issue #77, D47](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346)): **every agricultural year of the climate record, cut by the start month of the case**, with the rotation repeated over them. The record runs from 2001-01-01 to 2024-12-31 (D29). A calendar whose own dates lie outside the record still runs on the years of the record. So the calendar's `start_date` and `end_date` do not choose the years, and EP1 and EP3 list the same years: those of the record.
- Still `OPEN`, not answered by issue #77: **how the rotation is repeated over the years of the record**, that is, in which year of the record its first cycle starts and what happens to a cycle that does not fit whole. For the lead developer, as owner of lane L1, and the science reviewers.
- Still `OPEN`: which daily series marks the record for each engine, when the series of one record do not cover the same days. Issue #77 does not say. Issue #115 proposes the `precipitation` series for EP1. For the lead developer.
- Not changed yet: no model, engine or route changed with this answer. An agricultural year that the record does not cover from its first day to its last stays missing with reason `NO_COVERAGE` (C5.5).

**Q6. How does a scenario reach an engine, and who gives a value its range?** `scenario_id` is in the rows of `ResultsTable` and not in `ResultsPerRotation`, and no signature here has a scenario argument. Proposed: one call is one scenario; the caller builds one set of arguments per scenario and writes `scenario_id` when it builds the table rows. This holds only if a scenario changes nothing but the arguments of the entry points; a scenario that changes a parameter falls under Q3. Also: with one call per scenario, an engine has nothing to compute a range from, so every number it returns carries `range_missing` and its reason. Is that intended, and which reason code does it use? What a scenario holds is question 9 of `contracts/results/README.md`. For the lead developer; the science reviewers for what a scenario and a range are.

**Q7. May an engine raise for the two caller defects of G5?** The alternative is that an engine never raises and answers these with missing values too. For the platform developer.

**Q8. What does the calendar engine receive besides the rotation definition?** Two parts. (a) `RotationCalendar` needs `case_id`, `field_id`, `rotation_id`, the start month of the agricultural year (C5.4) and the first and last date of the calendar. Does the "Rotation definition" contract carry all of them? If not, each one that it does not carry is a further argument of EP2, and the route has to be told where it comes from in a request `{ "site", "rotation" }`. (b) Does any calendar rule need site data, for example the climate record? If so EP2 gains the argument `climate: SiteClimate`. For the lead developer, as owner of lane L1, and the interface developer, as producer of the rotation definition.

- `DECIDED` for the start month of part (a) (decided by the lead developer on 14 November 2026, issue #77, D8): the start month travels **in the rotation definition**, with its provisional mark. The calendar engine copies it into the calendar.
- Not changed yet: the rotation definition does not carry the start month. It gains it in a later unit, for the interface developer, who is its producer.
- Still `OPEN`, to be supplied by people: **the provisional month of each case** (convention C5.4). For the person who declares the case.
- Still `OPEN`, not answered by issue #77: the rest of part (a), and part (b). For the same roles as before.

**Q9. Is the argument of EP2 the request item itself?** Issue #18 says `rotation` in the request body is one item of the "Rotation definition" contract, unchanged. EP2 assumes the route passes that item as it is, loaded into its model. For the platform developer and the interface developer.

**Q10. Do the inputs and the output of EP3 cover what the water engine needs and gives?** Two parts. (a) Inputs: do `SiteClimate` and `SiteSoilSlope` carry everything the methods of the water engine need? Neither carries anything about the place of the field (question 21 of `contracts/inputs/README.md`). If something is missing, it is a field of a contract or a further argument. For the science reviewers, who decide the method and its inputs, and the platform developer, who produces the site data. (b) Outputs: EP3 returns the indicator only. The reference evapotranspiration, the daily balance and the three descriptive measures of C1.4 have no contract, so the route cannot pass them on. Does the interface need any of them? If so, a contract is needed first and the return type of EP3 changes. For the lead developer and the interface developer.

- `DECIDED` for latitude and elevation, in part (a) (decided by the lead developer on 14 November 2026, issue #77, D9): they reach the water engine **in the "Site data: climate" contract**: the point the series is valid for (latitude, longitude, elevation), with its provenance label and source. The signature of the water entry point does not change.
- Not changed yet: `SiteClimate` carries nothing about the place of the field. The climate contract gains the point in a later unit, which has to land together with the adapter that fills it, so it is agreed with the platform developer first.
- Still `OPEN`, not answered by issue #77: whether the two models carry everything else the methods of the water engine need (the rest of part (a)), and part (b). For the same roles as before.

**Q11. Which reason code does an engine use for an input in a unit it does not accept?** C1.1 says a consumer checks the unit it receives. G5 proposes that the engine does not raise. `NOT_COMPUTABLE` and `CONTROL_FAILED` are the two codes of C3.2 that could apply. For the lead developer.

**Q12. Does the erosion engine consume the residue ledger?** Blueprint section 5 names the lead lane as a consumer of `ResidueLedger`. If the erosion engine is that consumer, EP1 gains the argument `residues: "ResidueLedger"` and EP4 is called before EP1. For the lead developer.

**Q13. What is the residue ledger computed from, and what is its contract?** EP4 is `OPEN` until the `ResidueLedger` contract exists and a person says which inputs the ledger needs: what the user declares, the calendar, site data, the result of another engine, parameters. The contract has to let every value be missing with its reason. For the lead developer, as owner of lane L1; the science reviewers for what the ledger is computed from.

**Q14. What do the two carbon entry points receive and return?** EP5 and EP6 are `OPEN` until the `ModelState` and `CarbonBalance` contracts exist; `CarbonForcing` is PROPOSED in `contracts/carbon_forcing/` (#155, D62). Four parts. (a) `ModelState`: is it an argument (the starting state, the same for both models), part of what is returned, or both? (b) The residue ledger: does a carbon engine take `ResidueLedger` as an argument, or does `CarbonForcing` already hold what comes from it? `CarbonForcing` has `carbon_inputs` and `annual_carbon_inputs`, each series with an `origin` whose vocabulary is `OPEN` (`contracts/carbon_forcing/README.md`, OPEN 4). (c) The indicator: who computes the three values of `soil_carbon_trend` per model (C1.6): each carbon engine, which then returns `list[SoilCarbonTrend]` (`contracts/results/models.py`) next to the balance, or one function shared by both models, and in which folder does it live? (d) The two variants of AMG in blueprint section 8: does the one function return both, and how is each labelled? `CarbonForcing` now carries both monthly series and annual series (`annual_climate`, `annual_carbon_inputs`), at the lead developer's request on #155; which one each variant reads stays part of this question (`contracts/carbon_forcing/README.md`, OPEN 4). For the lead developer (EP5), the interface developer (EP6) and the platform developer, as producer of `CarbonForcing`.

**Q15. Who builds what no entry point returns?** Three parts. (a) `ResultsPerRotation` is put together from the results of EP1 and EP3 and the carbon values: by the route, or by a function that is not one of the six engines? (b) `ResultsTable`: which code builds it from several calls, and in which folder? (c) While an engine is not built, who writes its values as missing with reason `NOT_AVAILABLE` (C3.2)? For `soil_carbon_trend` that also needs the identifiers of the carbon models, which are question 7 of `contracts/results/README.md`. For the platform developer and the lead developer.

- `DECIDED` for the form of part (c) (decided by the lead developer on 14 November 2026, decision D12, recorded in [issue #18](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/18#issuecomment-6881785241) and [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6881787420)): while an engine is not built, its whole part of `ResultsPerRotation` (`soil_loss`, `water_deficit_exposure` or `soil_carbon_trend`) may be wholly missing, **only with reason `NOT_AVAILABLE`**. A built engine keeps the present form and G4.
- PROPOSED, not decided: the shape of a wholly missing part (`PartNotBuilt` in `contracts/results/models.py`; question 21 of `contracts/results/README.md`), for the platform developer and the interface developer to accept or rename.
- Not answered by D12: which code writes the wholly missing part (today the runner in `api/engines.py`, lane L2a, writes the carbon rows as missing values, and answers `result: null` when EP1 or EP3 is not built), and parts (a) and (b).

**Q16. Where does a result say that it was computed from example data?** The three input models carry `example_data`. `ResultsPerRotation` and `ResultsTable` do not, so an engine cannot pass the mark on. Blueprint section 7 lets soil and slope come from the accepted example at the first checkpoint, shown as example data. Either the results models gain the mark, or the route carries it next to the result. For the lead developer and the platform developer.

### Questions of other files that these signatures depend on

They are not repeated here. An engine meets each of them before it can return a number.

| Question | Where |
|---|---|
| The closed list of `kind` labels of a range | C2.3; question 1 of `contracts/results/README.md` |
| The time basis of `water_deficit_exposure` | C1.3; question 2 of `contracts/results/README.md` |
| The reason code for a definition that is not decided yet | Question 4 of `contracts/results/README.md` |
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
