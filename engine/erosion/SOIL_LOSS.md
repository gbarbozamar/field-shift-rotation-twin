# Soil-loss entry point

Entry point EP1 of `contracts/ENTRYPOINTS.md`, `compute_soil_loss`, in `engine/erosion/soil_loss.py`, exported by `engine/erosion/__init__.py`. The lookup of a parameter is in the private module `engine/erosion/_parameters.py`.

- Unit `l0/erosion-entrypoint` (issue #115, merged as #125): the mechanical form. It lays out the agricultural years of the climate record and their months.
- Unit `l0/erosion-ep1-parameters` (issue #154): the argument `parameters` (D46, D56), and the factors the code already built can compute from it.

> **Status: PROPOSED** (blueprint section 3.7). The parameter identifiers and their scope, the reading of a slope unit, the order of the checks, the reason code of each value, the format of every `detail`, the source text of a computed value and the test cases below were written by builder sessions. They take effect only when a person approves the pull request. Items under [OPEN](#open) need an answer from a person.

**This unit holds no parameter value.** No coefficient, no default and no stand-in number: not in the code, not in a test, not in this file. `params/records/` stays empty, so every real run still returns every annual value missing, each with the parameters it lacks named by id and scope. A number appears only when a person has transcribed and checked every record listed under [Parameters EP1 reads](#parameters-ep1-reads) (decision D34 of issue #77).

Acceptance test, from the repository root:

```bash
py -3.12 -m pytest engine/erosion/
```

## Signature

```text
compute_soil_loss(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    parameters: dict[str, dict],
) -> SoilLossResults | Missing
```

As EP1 is written in `contracts/ENTRYPOINTS.md` (#144): `parameters` is the catalogue as `params.catalogue.load_folder` returns it, passed by keyword (G3, D56). It has **no default**: a call without it raises `TypeError`. It is keyword-only, so a call that passes it by position also raises `TypeError`.

The function never calls `load_folder` or anything else that reads a file (G1). It calls the pure functions `params.catalogue.identity` and `params.catalogue.read_value` on the records it was given, and does not change `parameters`.

## Decisions this unit applies

Decisions of the lead developer, recorded in issue #77. They are cited, not reopened.

| Decision | What this unit does with it |
|---|---|
| D46, D56 (Q3) | The argument `parameters`, by keyword. A parameter without a record makes the value that needs it missing with `MISSING_INPUT`, the parameter named by id and scope in `detail` |
| D47, agricultural years (Q5) | Every agricultural year of the climate record, cut by the start month of the case. The record is the daily series with quantity `precipitation`: every agricultural year (C5.3) that has at least one day between that series' `start_date` and `end_date` is laid out, identified by the calendar year in which it begins |
| D47, rotation repeated over the years | **Not implemented.** No factor read here depends on the calendar's dates: OPEN 2 |
| D23, source of daily precipitation | The quantity identifier `precipitation`, the only climate series the soil-loss method reads (`docs/METHODS.md` M1.2) |
| D11, unit strings of `R` and `K` (M1.7) | The accepted unit strings of the unit guard of `equation.py`: `R` in `MJ mm ha-1 h-1 yr-1`, `K` in `t ha h ha-1 MJ-1 mm-1`. `LS`, `C` and `P` have no unit (M1.7), written `dimensionless` (C1.1) |
| D45, sub-factors of `C` | Not built here. Named in the detail of a missing `C` as the method that would compute it |
| D7, start month required (Q4) | Decided, not implemented on `main`: EP1 keeps its single `Missing` for a missing start month (OPEN 7) |
| D12 and D31, meaning of `NOT_AVAILABLE` | Used only for a part that is not built: the monthly erosivity fraction of M1.2, and the propagation of a range through the product |
| D10, D48, source of `K` | Not applied: `K` comes from the soil data through the platform adapters later. Until then `K` is read from the catalogue (OPEN 13) |

## Parameters EP1 reads

Every record is looked up by its `id` and **exactly** the scope below, through `params.catalogue.identity` (case and spacing ignored, as the catalogue compares them). The identifiers of `LS` are those `engine/erosion/LS.md` proposes; the others are proposed here. All are `PROPOSED`; the scope is `PROPOSED` and is OPEN 3.

| Argument | Identifier | Scope | Factor | What the record holds | Unit of the record |
|---|---|---|---|---|---|
| `R` | `rusle_r_factor` | `{}` | `R` | The mean annual level of `R` at the field (M1.2) | Must be the accepted string of D11, or the unit guard stops the product |
| `K` | `rusle_k_factor` | `{}` | `K` | `K` of the soil of the field (M1.3) | As `R` |
| `a1` | `rusle_s_below_break_sine_coefficient` | `{}` | `LS` | See `LS.md` | Not checked (OPEN 4 of `LS.md`) |
| `a2` | `rusle_s_below_break_constant` | `{}` | `LS` | See `LS.md` | Not checked |
| `a3` | `rusle_s_at_or_above_break_sine_coefficient` | `{}` | `LS` | See `LS.md` | Not checked |
| `a4` | `rusle_s_at_or_above_break_constant_subtracted` | `{}` | `LS` | See `LS.md` | Not checked |
| `s_break` | `rusle_s_break_slope` | `{}` | `LS` | The break slope | Must be read as a `SlopeUnit` (below) |
| `lambda_unit` | `rusle_l_unit_length` | `{}` | `LS` | The unit length | Must be the unit string of `slope_length`; `ls.py` checks it |
| `b1` | `rusle_l_beta_sine_divisor` | `{}` | `LS` | See `LS.md` | Not checked |
| `b2` | `rusle_l_beta_denominator_sine_coefficient` | `{}` | `LS` | See `LS.md` | Not checked |
| `b3` | `rusle_l_beta_denominator_sine_exponent` | `{}` | `LS` | See `LS.md` | Not checked |
| `b4` | `rusle_l_beta_denominator_constant` | `{}` | `LS` | See `LS.md` | Not checked |
| `C` | `rusle_c_factor` | `{}` | `C` | One `C` for the rotation (OPEN 12) | Must be `dimensionless` |
| `P` | `rusle_p_factor` | `{}` | `P` | `P` of the field (M1.6) | Must be `dimensionless` |

### Reading a slope unit (PROPOSED)

`ls.py` needs the unit of `slope_steepness` and of `s_break` as a `SlopeUnit`. The unit strings of a slope are OPEN (question 18 of `contracts/inputs/README.md`). This unit reads a unit string as the `SlopeUnit` whose value is that exact string (`percent`, `ratio`, `angle_degrees`, `angle_radians`); any other string is not read, and `LS` is missing with `ls.REASON_UNIT_NOT_ACCEPTED`. OPEN 4.

## What the function does, in order

1. **Types (G5).** `calendar`, `climate` or `soil_slope` that is not an instance of its model, or `parameters` that is not a `dict` whose keys are `str` and whose items are `dict`, raises `TypeError` naming the argument.
2. **One field (G5).** When `climate` or `soil_slope` names another `case_id` or `field_id` than `calendar`, `ValueError`, naming the identifier fields that differ, never their values.
3. **Start month (EP1, Q4).** When `calendar.ag_year_start.month` is missing: one `Missing`, reason `MISSING_INPUT`, `detail` names the start month.
4. **Precipitation series (G4, third row; D47).** When `climate.daily_series` has no item with quantity `precipitation`: one `Missing`, reason `MISSING_INPUT`, `detail` names `precipitation`.
5. **Years and months (C5.3, D47).** From the agricultural year that holds the series' `start_date` to the one that holds its `end_date`, each with its twelve calendar months starting at `calendar.ag_year_start.month` in calendar year `ag_year`.
6. **The factors**, once for the call, when the calendar is feasible (below).
7. **Reason or number of each value**, the first row that applies:

| Situation | Annual value | Monthly value | Convention |
|---|---|---|---|
| The calendar is infeasible | `NOT_COMPUTABLE` | `NOT_COMPUTABLE` | G4, first row |
| The series does not cover the year (or the month) from its first day to its last | `NO_COVERAGE` | `NO_COVERAGE` (PROPOSED: C5.5 speaks of yearly values) | C5.5, OPEN 5 |
| Every other value | `equation.annual_soil_loss` of the five factors: a number only when all five are present, otherwise its `Missing` | `NOT_AVAILABLE`: the monthly erosivity fraction of M1.2 is not built | G4; D12, D31 |

Every value keeps `indicator`, `direction` and `unit` (C3.1), taken from `contracts/results/models.py`.

## The factors

Each factor is an `equation.Factor`: a number with the unit string it arrives in, or the `Missing` of `contracts/results/models.py` with the unit string it would have (the accepted one).

| Factor | How it is obtained | When it is missing |
|---|---|---|
| `R` | The value of one record, read with `read_value`; its unit is the record's `unit` | See [a parameter that cannot be read](#a-parameter-that-cannot-be-read), and the detail adds that the daily erosivity index of M1.2, which gives the monthly fraction of `R` and its variation between years, is not built |
| `K`, `P` | The same | See [a parameter that cannot be read](#a-parameter-that-cannot-be-read) |
| `C` | The same | The same, and the detail adds that the method that would compute `C`, the sub-factor equations of M1.5 (D45), is not built |
| `LS` | `ls.slope_length_factor(...) * ls.slope_steepness_factor(...)`, from `soil_slope.slope_steepness`, `soil_slope.slope_length` and the ten records of `LS.md`; unit `dimensionless` | First, `MISSING_INPUT` naming every slope input that is missing in `SiteSoilSlope` (with its own reason and detail) and every coefficient that cannot be read. Then `ls.REASON_UNIT_NOT_ACCEPTED` for a slope unit that is not read as a `SlopeUnit`. Then the `Missing` that `ls.py` returns (units of the length that differ, a form without a finite real result). Then `NOT_COMPUTABLE` if `L * S` is not finite |

### A parameter that cannot be read

Always reason `MISSING_INPUT` (G4, the two rows for a parameter). The detail names the parameter as `parameter '<id>' with scope {}`:

| Situation | `detail` |
|---|---|
| A record anywhere in `parameters` without a well-formed `id` and `scope` (only in a catalogue that `check_catalogue` rejects, G3). It cannot be compared, so it could be a record of this parameter: it is reported, not skipped (F3c of `params/README.md`). PROPOSED, OPEN 18 | `parameter '<id>' with scope {} cannot be looked up: the record(s) '<key>', ... have no well-formed 'id' and 'scope', ...` |
| No record with that id and scope | `parameter '<id>' with scope {} has no record in parameters (D56)` |
| More than one such record (only in a catalogue that `check_catalogue` rejects, G3) | `parameter '<id>' with scope {} has more than one record in parameters, which params.catalogue.check_catalogue rejects (G3)` |
| `read_value` refuses the record (malformed, or a placeholder) | `the record of parameter '<id>' with scope {} is refused by params.catalogue.read_value: <its message>` |
| The record has `"value": null` | `the record of parameter '<id>' with scope {} has no value: <value_missing_reason of the record>` |

A record with another scope, wider or narrower, is not read (question 5 of `params/README.md`, OPEN 3).

### The annual product

`equation.annual_soil_loss(r=..., k=..., ls=..., c=..., p=..., accepted_units=ACCEPTED_UNITS, unit_guard_reason=ls.REASON_UNIT_NOT_ACCEPTED)`, as `EQUATION.md` describes it: `MISSING_INPUT` naming every missing factor (`factor '<name>' is missing (reason <CODE>: <detail>)`); then the unit guard; then `NOT_COMPUTABLE` for a product that is not finite. The factor names are those of `equation.FACTOR_NAMES`: `r`, `k`, `ls`, `c`, `p`.

A number is returned as an `AnnualSoilLoss` with:

- `provenance` `DERIVED` (C4.6);
- `source`: `derived by engine.erosion.compute_soil_loss with the product of docs/METHODS.md M1.1: ...`, naming every record read with its scope (PROPOSED; question 11 of `contracts/results/README.md`, OPEN 14);
- no `range`, and `range_missing` with reason `NOT_AVAILABLE`: how a range passes through the product is not built (C2.3, OPEN 5 of `EQUATION.md`);
- the same number for every agricultural year that is covered: nothing read here changes between years (OPEN 11).

## Numbers in the modules

`soil_loss.py` holds two integers, both for month arithmetic, and no other number. `_parameters.py` holds one, the `1` of "more than one record". A test reads both modules and fails on any other number, and on any format specification in an f-string of `soil_loss.py`.

| Integer | Where | Why |
|---|---|---|
| `12` | `soil_loss.py`, `_MONTHS_IN_A_YEAR` | Twelve calendar months to a year and to an agricultural year (C5.1, C5.3) |
| `1` | `soil_loss.py`, `_FIRST` | Months and days are counted from one (C5.1) |
| `1` | `_parameters.py` | More than one record with one id and scope |

The test file builds its PLACEHOLDER numbers as `PLACEHOLDER_BASE` plus the position in the list of identifiers. The base is plainly unreal, far above any value a factor or a coefficient of RUSLE takes, so that no test number lands on a published coefficient. The test adds `1` to a number to change it, and uses the integers of month arithmetic. It writes no value of the method. Its records carry the word PLACEHOLDER in their citation, persons and reasons, and are passed as an in-memory copy in which the word is replaced by `UNMARKED_TEST_ONLY`, as `params/test_layout.py` does (question 12 of `params/README.md`); that copy passes `check_catalogue`. The unit strings of the `R`, `K`, `C` and `P` records are read from `ACCEPTED_UNITS` of the module, not written in the test.

## PROPOSED cases

The identifier is the name of the test function in `test_soil_loss.py` without `test_`, with hyphens. A test checks that this list and the test functions agree.

### Cases of #125, kept

| Case | What it checks |
|---|---|
| `examples-with-several-agricultural-years-load-into-soil-loss-results` | From the examples, with a `precipitation` series spanning several agricultural years: one `AnnualSoilLoss` per agricultural year of D47 and twelve consecutive `MonthlySoilLoss` per year; indicator, direction and unit from the constants of `contracts/results/models.py`; the round trip through `model_dump(mode="json")` loads back equal |
| `start-month-missing-returns-one-missing-input` | A missing start month: one `Missing`, reason `MISSING_INPUT`, detail names the start month |
| `infeasible-calendar-makes-every-value-not-computable` | An infeasible calendar: every value `NOT_COMPUTABLE`, with an empty catalogue and with a full one, also for years the series does not cover |
| `year-or-month-not-covered-by-precipitation-is-no-coverage` | Years and months the series does not cover are `NO_COVERAGE`; a covered year is `MISSING_INPUT` (empty catalogue); a covered month is `NOT_AVAILABLE`, also inside a year that is not covered whole |
| `series-one-day-short-at-each-end-leaves-first-and-last-not-covered` | The first and last agricultural years, and the first and last months, are `NO_COVERAGE`; every year between is `MISSING_INPUT` and every month between `NOT_AVAILABLE` |
| `calendar-dates-outside-the-record-keep-the-years-of-the-record` | A calendar moved past the record: the years are those of the record, and the result equals the one with the example calendar (D47) |
| `no-precipitation-series-returns-one-missing-input` | No `precipitation` series: one `Missing`, reason `MISSING_INPUT`, detail names `precipitation` |
| `missing-slope-input-is-named-in-the-ls-factor` | With a full catalogue, `slope_steepness`, `slope_length` or both missing in `SiteSoilSlope`: the year is `MISSING_INPUT`, only factor `ls` is named, with each missing input and its own reason |
| `arguments-of-another-case-or-field-raise-value-error` | `case_id` or `field_id` of `climate` or `soil_slope` differs from the calendar: `ValueError` naming the field (G5) |
| `argument-that-is-not-its-model-raises-type-error` | `calendar`, `climate` or `soil_slope` given as a dictionary or as another model: `TypeError` naming the argument (G5) |

### The argument `parameters` (#154)

| Case | What it checks |
|---|---|
| `parameters-missing-positional-or-not-a-dict-raises-type-error` | `parameters` left out, passed by position, or not a `dict` (`None`, a list, a tuple, text, a list of pairs), or a `dict` with an item that is not a `dict` or a key that is not `str`: `TypeError` (G3, G5) |
| `empty-catalogue-names-every-parameter-and-keeps-every-year` | `{}`: every agricultural year of D47 is present and `MISSING_INPUT`; the detail names the five factors and every identifier of the table with `scope {}` and D56, M1.2 and its daily erosivity index for `R`, and M1.5 and D45 for `C`; every month is `NOT_AVAILABLE` naming M1.2 |
| `full-catalogue-gives-the-product-of-equation-py` | Every record present: each covered year's value equals `equation.annual_soil_loss` of the record values and of `LS` from `ls.py`; it carries `DERIVED`, a source naming every identifier, no range and `range_missing` `NOT_AVAILABLE`; years not covered stay `NO_COVERAGE`; months stay missing; the result loads back equal |
| `ls-is-computed-through-ls-py-from-the-catalogue` | With the break slope above the slope and at the slope, and each `LS` record changed in turn: the value equals the product with `LS` computed by `ls.py` from the changed numbers |
| `removing-any-one-record-makes-the-year-missing-and-names-it` | For each of the fourteen identifiers: without its record every year is `MISSING_INPUT`, and the detail names that identifier with `scope {}` and no other |
| `record-with-null-value-repeats-its-reason` | A record of `R`, of `s_break` or of `C` with `"value": null` (the catalogue still passes `check_catalogue`): `MISSING_INPUT`, the parameter named and its reason repeated (G4) |
| `record-that-read-value-refuses-is-missing-input` | A record still marked PLACEHOLDER, and a record without `unit`: `MISSING_INPUT`, naming the parameter and the refusal of `read_value` |
| `only-a-record-with-the-empty-scope-is-read` | A record of `P` with a `management` scope instead of `{}`: not read, `MISSING_INPUT` naming `P` with `scope {}` (OPEN 3) |
| `two-records-with-one-identity-are-missing-input` | Two records of `C` with one id and scope: `MISSING_INPUT`, saying there is more than one |
| `record-that-cannot-be-compared-is-reported-not-skipped` | A record with `id` null, `scope` null, or an `id` that starts with a digit: every parameter is `MISSING_INPUT` and its detail names that record by its key; never "has no record" (F3c of `params/README.md`) |
| `slope-unit-that-ls-py-cannot-read-is-not-computed` | A `slope_steepness` unit, or an `s_break` record unit, that is no `SlopeUnit` value: `LS` missing with `ls.REASON_UNIT_NOT_ACCEPTED`, naming which |
| `factor-in-another-unit-is-stopped-by-the-unit-guard` | An `R` record in another unit string than D11's: the year is missing with the unit-guard reason, naming factor `r` |
| `no-value-is-a-number-unless-every-factor-is-present` | Over the cases with an empty catalogue, with one record left out, and with a full catalogue but a slope unit that is not read: no value is a number, none is zero, every value has a `missing` part with a code of C3.2 and carries no range, source or provenance |
| `arguments-unchanged-and-second-call-equal` | With an empty and with a full catalogue: the arguments, `parameters` included, equal a deep copy taken before the call, and a second call gives an equal result (G1) |

### The modules

| Case | What it checks |
|---|---|
| `modules-import-only-allowed-modules-and-hold-only-counting-integers` | `soil_loss.py` imports only the standard library, `contracts.inputs.*`, `contracts.results.models` and `engine.erosion` (`ls`, `equation`, `_parameters`); `_parameters.py` only the standard library, `contracts.results.models` and `params.catalogue`; neither names `load_folder`, `check_folder`, `check_layout`, `open` or `read_text` (G1); the numbers are those of the table above; no format specification in an f-string |
| `package-exposes-compute-soil-loss-with-parameters-by-keyword-and-no-default` | `from engine.erosion import compute_soil_loss` works; its parameters are `calendar`, `climate`, `soil_slope`, `parameters`; `parameters` is keyword-only and has no default |
| `soil-loss-md-lists-every-parameter-identifier` | The table [Parameters EP1 reads](#parameters-ep1-reads) lists exactly the identifiers the module reads |
| `proposed-cases-match-soil-loss-md` | This list and the test functions agree |

## Changes outside this folder that this unit needs

The runner in `api/engines.py` calls EP1 with three keyword arguments. With this unit it raises `TypeError` until the platform developer's change passes `parameters` (the merge condition of issue #154). The tests of `api/` that break are listed in the report of the unit, for the platform developer. Nothing outside `engine/erosion/` is changed here.

## OPEN

Each item is a question a person has to answer, with the role that answers it. None is answered by this unit.

1. **Days missing inside the `precipitation` series.** G4 and C3.3 make a value computed from missing days `MISSING_INPUT`, and C3.4 leaves the gap-filling method OPEN. Nothing computed here reads the days: a covered year with missing days can carry a number. When the monthly erosivity fraction is built, it has to apply this rule. For the lead developer (when), the science reviewers (the method of C3.4).
2. **Repeating the rotation over the years of the record (D47).** Not implemented: nothing read here uses the calendar's components. It belongs to the cover-management unit (M1.5, D45). For the lead developer.
3. **Scope of every record: `{}`.** The smallest form: one record per identifier, "no restriction stated". `R`, `K` and `P` belong to a field, and `C` to a rotation, so the empty scope says one value for every field and every rotation. The scope words are question 4 of `params/README.md`; which record is read when one has the empty scope and another names a crop is question 5. This unit reads only the exact scope `{}`. For the lead developer, who owns `params/`.
4. **Reading a slope unit.** A unit string is read as the `SlopeUnit` whose value is that exact string. The unit strings of a slope in the input contract are question 18 of `contracts/inputs/README.md`; the unit of the break slope is OPEN 1 and 8 of `LS.md`. The reason code of a unit not read is `ls.REASON_UNIT_NOT_ACCEPTED` (Q11). For the science reviewers (the units), the lead developer (the reading and the code).
5. **Months not covered by the series.** C5.5 speaks of yearly values; this unit also writes `NO_COVERAGE` for a month. For the lead developer.
6. **Precedence of the reasons.** Infeasible calendar, then coverage, then the factors; of the two single `Missing`, the start month before the series; inside `LS`, missing inputs before a unit not read before the result of `ls.py`. For the lead developer.
7. **With the calendar engine of today, EP1 may always return one `Missing`.** If the calendar engine writes the start month as missing until the rotation definition carries it (D7, D8), the erosion module is `not_available` through the route. Whether the return type of EP1 changes after D7 is not said by issue #77. For the lead developer and the platform developer.
8. **The day boundaries of an agricultural year.** Years and months are cut on the dates of the series, in its time zone (C6.1, C6.2), not on the local day at the field (C6.5). For the science reviewers.
9. **Where the identifier `precipitation` lives.** Written once in `soil_loss.py`. Whether contracts should export the quantity identifiers as constants. For the lead developer and the platform developer.
10. **Example data (Q16).** The inputs carry `example_data`; `SoilLossResults` has no field for it. A number computed from example soil data carries no mark of it. For the lead developer and the platform developer.
11. **The same number for every agricultural year.** `R` is read as one mean annual level and nothing else read here changes between years, so every covered year gets the long-term product of M1.1. The variation between years of M1.2 is not built. Whether an annual value should stay missing until it is, instead of repeating the long-term product, is not said by the brief. For the lead developer and the science reviewers.
12. **`C` as one record.** D45 computes `C` from sub-factors by period (M1.5), which is not built; a single `C` record with the empty scope cannot tell rotations apart, which is the main channel of M1.1. Whether a `C` record may stand in until the sub-factor unit lands, and with which scope, is for the lead developer and the science reviewers.
13. **`K` from the catalogue.** D48 brings `K` from the soil data through the platform adapters (D10). Until a field carries it, `K` is read from a catalogue record. When it arrives in `SiteSoilSlope` (question 16 of `contracts/inputs/README.md`), which one wins is for the lead developer and the platform developer.
14. **The source text of a computed value.** Question 11 of `contracts/results/README.md`. The text names the method and every record read, not their citations. For the lead developer.
15. **The units of the coefficient records of `LS`.** `LS` is passed to the product as `dimensionless` (M1.7). The unit strings of `a1` to `a4` and `b1` to `b4` are not checked (OPEN 4 of `LS.md`). For the science reviewers.
16. **`P` under no-till.** M1.6 says `P` is one by default under no-till. This unit writes no default: `P` is read from a record like the other factors. For the lead developer and the science reviewers.
17. **`ls.py` has no `LS` function.** It returns `S` and `L`; the product `L * S` is written in `soil_loss.py`, with a finiteness check. Whether `ls.py` should offer it is for the lead developer (not changed here, as the brief says).
18. **A record that `read_value` refuses, or that cannot be compared.** G4 has rows for a parameter without a record and for a record with `"value": null`. A refused record (malformed or a placeholder), two records with one identity, and a record without a well-formed `id` and `scope` are possible only in a catalogue that `check_catalogue` rejects (G3); each is answered with `MISSING_INPUT` too, naming the parameter. A record that cannot be compared is reported, not skipped (F3c of `params/README.md`): PROPOSED, it makes **every** parameter missing, because it could be a record of any of them. The alternative is to report it only for a parameter that has no comparable record. For the lead developer and the platform developer.
19. **Who reads `detail`.** The format above is for developers. If the interface shows it, its wording belongs to the strings file of `web/` and to people. For the interface developer and the lead developer.
