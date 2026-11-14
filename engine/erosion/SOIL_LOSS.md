# Soil-loss entry point

Entry point EP1 of `contracts/ENTRYPOINTS.md`, `compute_soil_loss`, in `engine/erosion/soil_loss.py`, exported by `engine/erosion/__init__.py`. The lookup of a parameter is in the private module `engine/erosion/_parameters.py`.

- Unit `l0/erosion-entrypoint` (issue #115, merged as #125): the mechanical form. It lays out the agricultural years of the climate record and their months.
- Unit `l0/erosion-ep1-parameters` (issue #154, merged as #158): the argument `parameters` (D46, D56), and the factors the code then built could compute from it.
- Unit `l0/erosion-ep1-c-r` (issue #173): `R` computed through `engine/erosion/r_factor/` (M1.2) and `C` through `engine/erosion/c_factor/` (M1.5, D45), every constant read from `parameters`.

> **Status: PROPOSED** (blueprint section 3.7). The parameter identifiers and their scope, the crop and the residue of a day, the soil-loss ratio of a month, `C` by agricultural year, the reading of a unit string, the order of the checks, the reason code of each value, the format of every `detail`, the source text of a computed value and the test cases below were written by builder sessions. They take effect only when a person approves the pull request. Items under [OPEN](#open) need an answer from a person.

**This unit holds no parameter value.** No coefficient, no default and no stand-in number: not in the code, not in a test, not in this file. `params/records/` stays empty, so every real run still returns every annual value missing, each with the parameters it lacks named by id and scope. A number appears only when a person has transcribed and checked every record listed under [Parameters EP1 reads](#parameters-ep1-reads) (decision D34 of issue #77). With a real calendar, whose dates lie after the climate record, `C` stays missing as well until the rotation is repeated over the years of the record (OPEN 2).

Acceptance test, from the repository root:

```bash
py -3.12 -m pytest engine/erosion/ validation/
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

As EP1 is written in `contracts/ENTRYPOINTS.md` (#144): `parameters` is the catalogue as `params.catalogue.load_folder` returns it, passed by keyword (G3, D56). It has **no default**: a call without it raises `TypeError`. It is keyword-only, so a call that passes it by position also raises `TypeError`. Unchanged by this unit.

The function never calls `load_folder` or anything else that reads a file (G1). It calls the pure functions `params.catalogue.identity` and `params.catalogue.read_value` on the records it was given, and the pure functions of `r_factor/`, `c_factor/`, `ls.py` and `equation.py`, and does not change `parameters`.

## Decisions this unit applies

Decisions of the lead developer, recorded in issue #77. They are cited, not reopened.

| Decision | What this unit does with it |
|---|---|
| D46, D56 (Q3) | The argument `parameters`, by keyword. A parameter without a record makes the value that needs it missing with `MISSING_INPUT`, the parameter named by id and scope in `detail` |
| D47, agricultural years (Q5) | Every agricultural year of the climate record, cut by the start month of the case. The record is the daily series with quantity `precipitation`: every agricultural year (C5.3) that has at least one day between that series' `start_date` and `end_date` is laid out, identified by the calendar year in which it begins |
| D47, rotation repeated over the years | **Not implemented.** `C` reads the crop and the last harvest of each day from the calendar's dates; a day outside them makes `C` of its year missing, naming D47 (OPEN 2) |
| D23, source of daily precipitation | The quantity identifier `precipitation`, the only climate series the soil-loss method reads (`docs/METHODS.md` M1.2) |
| D11, unit strings of `R` and `K` (M1.7) | The accepted unit strings of the unit guard of `equation.py`: `R` in `MJ mm ha-1 h-1 yr-1` (`r_factor.R_UNIT`), `K` in `t ha h ha-1 MJ-1 mm-1`. `LS`, `C` and `P` have no unit (M1.7), written `dimensionless` (C1.1) |
| D45, sub-factors of `C` | Applied through `c_factor/`: canopy cover, and surface residue cover with residue decay by residue type. The other sub-factors stand at one, as `c_factor/` records in every soil-loss ratio |
| D7, start month required (Q4) | Decided, not implemented on `main`: EP1 keeps its single `Missing` for a missing start month (OPEN 7) |
| D12 and D31, meaning of `NOT_AVAILABLE` | Used only for a part that is not built: a monthly value of soil loss, the propagation of a range through the product, and the tolerance of the sum of the erosivity fractions that EP1 does not supply |
| D10, D48, source of `K` | Not applied: `K` comes from the soil data through the platform adapters later. Until then `K` is read from the catalogue (OPEN 13) |

## Parameters EP1 reads

Every record is looked up by its `id` and **exactly** the scope below, through `params.catalogue.identity` (case and spacing ignored, as the catalogue compares them). Identifiers are those `LS.md`, `r_factor/README.md` and `c_factor/README.md` propose where they propose one; the others are proposed here. All are `PROPOSED`; the scopes are `PROPOSED` (OPEN 3, OPEN 22).

The scope column says how a record is looked up:

- `site`: the empty scope `{}`. One record for the field and the method.
- `crop or no crop`: `{"crop": "<crop_id>"}`, the `crop_id` of the calendar component that covers the day; on a day no component covers, `{"management": "no_crop"}` (as `engine/water/EXPOSURE.md` reads it).
- `crop of the last harvest`: `{"crop": "<crop_id>"}`, the `crop_id` of the component whose end date is the last one before the day.

| Argument | Identifier | Scope | Factor | What the record holds | Unit of the record |
|---|---|---|---|---|---|
| `mean_annual_r` | `rusle_r_factor` | site | `R` | The mean annual level of `R` at the field (M1.2) | Must be `MJ mm ha-1 h-1 yr-1` (D11), or `r_factor/` refuses it |
| `exponent` | `rusle_r_daily_index_exponent` | site | `R`, `C` | The exponent of the daily erosivity index (M1.2) | Not checked: an exponent |
| `threshold` | `rusle_r_daily_index_threshold` | site | `R`, `C` | The daily precipitation at or below which a day adds nothing to the index | Must be `mm day-1`, or `r_factor/` refuses it |
| `K` | `rusle_k_factor` | site | `K` | `K` of the soil of the field (M1.3) | Must be the accepted string of D11, or the unit guard stops the product |
| `a1` | `rusle_s_below_break_sine_coefficient` | site | `LS` | See `LS.md` | Not checked (OPEN 4 of `LS.md`) |
| `a2` | `rusle_s_below_break_constant` | site | `LS` | See `LS.md` | Not checked |
| `a3` | `rusle_s_at_or_above_break_sine_coefficient` | site | `LS` | See `LS.md` | Not checked |
| `a4` | `rusle_s_at_or_above_break_constant_subtracted` | site | `LS` | See `LS.md` | Not checked |
| `s_break` | `rusle_s_break_slope` | site | `LS` | The break slope | Must be read as a `SlopeUnit` (below) |
| `lambda_unit` | `rusle_l_unit_length` | site | `LS` | The unit length | Must be the unit string of `slope_length`; `ls.py` checks it |
| `b1` | `rusle_l_beta_sine_divisor` | site | `LS` | See `LS.md` | Not checked |
| `b2` | `rusle_l_beta_denominator_sine_coefficient` | site | `LS` | See `LS.md` | Not checked |
| `b3` | `rusle_l_beta_denominator_sine_exponent` | site | `LS` | See `LS.md` | Not checked |
| `b4` | `rusle_l_beta_denominator_constant` | site | `LS` | See `LS.md` | Not checked |
| `fall_height_coefficient` | `rusle2_canopy_fall_height_coefficient` | site | `C` | Multiplies the fall height in the canopy sub-factor | The inverse of the unit of the fall height (below) |
| `surface_cover_coefficient` | `rusle2_surface_cover_coefficient` | site | `C` | Multiplies the surface residue cover in the surface-cover sub-factor | Must be `dimensionless` |
| `mass_cover_coefficient` | `rusle2_residue_mass_cover_coefficient` | site | `C` | Multiplies the residue mass in the mass-cover relation | The inverse of the unit of the residue mass (below) |
| `canopy_cover` | `rusle2_canopy_cover` | crop or no crop | `C` | The fraction of the soil under the canopy, zero to one | Must be `dimensionless` |
| `fall_height` | `rusle2_canopy_fall_height` | crop or no crop | `C` | The fall height of drops from the canopy | Any; it must be the unit whose inverse the coefficient carries |
| `residue_mass` | `rusle2_residue_mass_at_harvest` | crop of the last harvest | `C` | The residue mass a crop leaves on the surface at the end date of its component | Any; it must be the unit whose inverse the mass-cover coefficient carries |
| `decay_coefficients` | `rusle2_residue_decay_coefficient` | crop of the last harvest | `C` | The decay coefficient of the residue type of that crop | The inverse of `day` (below) |
| `P` | `rusle_p_factor` | site | `P` | `P` of the field (M1.6) | Must be `dimensionless` |

Changes to this table made by this unit (#173):

- `rusle_r_factor` now holds the **mean annual level** of `R` that `r_factor/` multiplies by the monthly fractions and the yearly ratios. It was read as the whole factor before; its unit is unchanged.
- Added for `R`: `rusle_r_daily_index_exponent`, `rusle_r_daily_index_threshold` (the identifiers of `r_factor/README.md`).
- Added for `C`, site: `rusle2_canopy_fall_height_coefficient`, `rusle2_surface_cover_coefficient`, `rusle2_residue_mass_cover_coefficient` (the identifiers of `c_factor/README.md`).
- Added for `C`, by crop: `rusle2_canopy_cover`, `rusle2_canopy_fall_height`, `rusle2_residue_mass_at_harvest` (new identifiers, PROPOSED) and `rusle2_residue_decay_coefficient` (the identifier of `c_factor/README.md`, its residue type named by the scope key `crop`, OPEN 23).
- **No longer read:** `rusle_c_factor`, the whole-factor record of `C`. A catalogue that holds it gives the same result as one without it. It does not stay as an override (PROPOSED, OPEN 12).
- Not read: the two constants of the control regression of `r_factor/` (`rusle_r_monthly_control_coefficient`, `rusle_r_monthly_control_exponent`); EP1 does not run the control (OPEN 26).

### Reading a unit string (PROPOSED)

- **A slope.** `ls.py` needs the unit of `slope_steepness` and of `s_break` as a `SlopeUnit`. A unit string is read as the `SlopeUnit` whose value is that exact string (`percent`, `ratio`, `angle_degrees`, `angle_radians`); any other string is not read, and `LS` is missing with `ls.REASON_UNIT_NOT_ACCEPTED`. OPEN 4.
- **The inverse of a unit.** `c_factor/` takes, next to each coefficient, the unit whose inverse is the coefficient's unit, and compares it with the unit of the input the coefficient multiplies. A record carries one unit string, so EP1 reads that unit from it: `<u>-1` gives `<u>` when `<u>` is one word (no space, no bracket), for example `day-1` gives `day`; `(<u>)-1` gives `<u>` for any `<u>` that is not blank. Any other string is not read, and `C` is missing with `ls.REASON_UNIT_NOT_ACCEPTED`. OPEN 21.
- **A fraction.** `c_factor/` reads the canopy cover and the residue cover as fractions from zero to one. The canopy-cover record and the surface-cover coefficient must carry `dimensionless`; any other string is not read. OPEN 21.
- **Time since a harvest** is counted in days of the daily series, unit string `day` (the unit string of `mm day-1`, CQ1). OPEN 21.

## What the function does, in order

1. **Types (G5).** `calendar`, `climate` or `soil_slope` that is not an instance of its model, or `parameters` that is not a `dict` whose keys are `str` and whose items are `dict`, raises `TypeError` naming the argument.
2. **One field (G5).** When `climate` or `soil_slope` names another `case_id` or `field_id` than `calendar`, `ValueError`, naming the identifier fields that differ, never their values.
3. **Start month (EP1, Q4).** When `calendar.ag_year_start.month` is missing: one `Missing`, reason `MISSING_INPUT`, `detail` names the start month.
4. **Precipitation series (G4, third row; D47).** When `climate.daily_series` has no item with quantity `precipitation`: one `Missing`, reason `MISSING_INPUT`, `detail` names `precipitation`.
5. **Years and months (C5.3, D47).** From the agricultural year that holds the series' `start_date` to the one that holds its `end_date`, each with its twelve calendar months starting at `calendar.ag_year_start.month` in calendar year `ag_year`.
6. **When the calendar is feasible**, once for the call: the steps of M1.2 through `r_factor/` (below), `K`, `LS` and `P`. Then, for each agricultural year the series covers, `R` and `C` of that year.
7. **Reason or number of each value**, the first row that applies:

| Situation | Annual value | Monthly value | Convention |
|---|---|---|---|
| The calendar is infeasible | `NOT_COMPUTABLE` | `NOT_COMPUTABLE` | G4, first row |
| The series does not cover the year (or the month) from its first day to its last | `NO_COVERAGE` | `NO_COVERAGE` (PROPOSED: C5.5 speaks of yearly values) | C5.5, OPEN 5 |
| Every other value | `equation.annual_soil_loss` of `R` and `C` of the year and of `K`, `LS`, `P`: a number only when all five are present, otherwise its `Missing` | `NOT_AVAILABLE`: a monthly value of soil loss is not formed (OPEN 20) | G4; D12, D31 |

Every value keeps `indicator`, `direction` and `unit` (C3.1), taken from `contracts/results/models.py`.

## The factors

Each factor is an `equation.Factor`: a number with the unit string it arrives in, or the `Missing` of `contracts/results/models.py` with the unit string it would have (the accepted one).

### `R` through `r_factor/` (M1.2)

1. The records of the level, the exponent and the threshold are read. When the exponent or the threshold cannot be read, the monthly erosivity fractions are missing (`MISSING_INPUT`, `the monthly erosivity fractions: ...`), and so is `R` (`R by month: ...`); each names the record by id and scope and adds `needed by the daily erosivity index of docs/METHODS.md M1.2 (engine/erosion/r_factor/), whose monthly fractions and yearly ratios R and C need`. A level that cannot be read makes `R` missing the same way (`needed by the mean annual level of R ...`) and leaves the fractions.
2. Otherwise `r_factor.r_factor_parts(series=<the precipitation series>, exponent, threshold, threshold_unit=<unit of the threshold record>, start_month, mean_annual_r, mean_annual_r_unit=<unit of the level record>)`. Every refusal is `r_factor/`'s: a series or a threshold not in `mm day-1`, a level not in `MJ mm ha-1 h-1 yr-1`, a missing day (that day, its month and its agricultural year missing, never zero rain), a year without an erosive day (its fractions `NOT_COMPUTABLE`), and so on (`r_factor/README.md`).
3. `R` of a covered agricultural year is the **sum of its twelve values of `R` by month** (`r_by_year_and_month`), unit `MJ mm ha-1 h-1 yr-1`. When a month is missing, `R` of the year is missing: the months are named, grouped by reason and detail; the reason is that of the months when they share one, otherwise `MISSING_INPUT`. A sum that is not finite is `NOT_COMPUTABLE`.

`R` therefore changes from year to year by the yearly ratio of `r_factor/`, whose mean is taken over the years of the record whose annual sum is a number (`r_factor/` OPEN 6).

### `C` through `c_factor/` (M1.5, D45)

`C` is computed for each covered agricultural year on its own, over its twelve months, with one year (PROPOSED, OPEN 25).

1. **Crop of a day** (PROPOSED, as `engine/water/`): the `crop_id` of the one component of the calendar whose dates cover the day; `{"management": "no_crop"}` when no component can cover it. Not known (`MISSING_INPUT`) for a day outside the dates of the calendar (naming D47, OPEN 2) and when a component with a missing date could cover the day; `NOT_COMPUTABLE` when two dated components cover it. The periods of a component are not read (OPEN 22).
2. **Residue of a day** (PROPOSED, OPEN 23): the residue left by the **last harvest before the day**, the component whose end date is the last one before the day. Not known (`MISSING_INPUT`) for a day outside the calendar, when a component without an end date could have ended before the day, and when no component ends before the day (the residue left before the calendar begins needs D47 or the residue ledger, Q12); `NOT_COMPUTABLE` when two components end on that last date. Older residue is not added.
3. **Every problem is gathered first**: the monthly erosivity fractions of the year (missing in step 1 of `R`, or for a month of the year), the crop and the residue of every day of the year (each text once, with the number of days and the first day), and every record of the table that cannot be read (named by id and scope, with `needed by <the part of M1.5 that needs it>`). Any problem makes `C` missing: `C of agricultural year <Y> is not computed: <problem>; <problem>; ...`, reason `MISSING_INPUT` (C3.3), or the reason of the first problem when none is an input that is missing. Then the unit strings (above): any that is not read makes `C` missing with `ls.REASON_UNIT_NOT_ACCEPTED`, naming each.
4. **The soil-loss ratio of each day**, through `c_factor/`:
   - `canopy_subfactor(canopy_cover, fall_height, fall_height_unit, fall_height_coefficient, fall_height_coefficient_per_unit)` with the records of the crop of the day;
   - `residue_mass_after_decay(residue_mass, residue_type=<crop of the last harvest>, decay_coefficients={<that crop>: <its record>}, decay_coefficient_per_unit, elapsed_time=<days since the end date of that component>, elapsed_time_unit="day")`;
   - `residue_cover_from_mass(...)` of that mass, then `surface_cover_subfactor(...)` of that cover;
   - `soil_loss_ratio(canopy=..., surface_cover=...)`.

   The first refusal of a day (a cover outside zero to one, units that differ, a form without a finite result) makes `C` missing with the reason `c_factor/` gives: `C of agricultural year <Y> is not computed: on <date>, <function> of engine/erosion/c_factor/ ...: <its detail>`.
5. **The soil-loss ratio of a month** is the mean of the ratios of its days (PROPOSED, OPEN 24). It is passed to `rotation_c` as a `c_factor.SoilLossRatio` whose `canopy` and `surface_cover` are the means of the two sub-factors over the days, with `SET_TO_ONE` and `DECLARED_LIMIT`.
6. **`rotation_c`** over the twelve months of the year, each with its erosivity fraction from `r_factor/` (month labelled `YYYY-MM`), `number_of_years=1`, and `fraction_sum_tolerance` missing with `NOT_AVAILABLE` (EP1 supplies none, OPEN 27; it only drives `fractions_add_up`, which EP1 does not read). A `Missing` it returns is `C`'s, with its reason; otherwise `C` is its value, `dimensionless`.

### `K`, `P` and `LS`

| Factor | How it is obtained | When it is missing |
|---|---|---|
| `K`, `P` | The value of one record, read with `read_value`; its unit is the record's `unit` | See [a parameter that cannot be read](#a-parameter-that-cannot-be-read) |
| `LS` | `ls.slope_length_factor(...) * ls.slope_steepness_factor(...)`, from `soil_slope.slope_steepness`, `soil_slope.slope_length` and the ten records of `LS.md`; unit `dimensionless` | First, `MISSING_INPUT` naming every slope input that is missing in `SiteSoilSlope` (with its own reason and detail) and every coefficient that cannot be read. Then `ls.REASON_UNIT_NOT_ACCEPTED` for a slope unit that is not read as a `SlopeUnit`. Then the `Missing` that `ls.py` returns (units of the length that differ, a form without a finite real result). Then `NOT_COMPUTABLE` if `L * S` is not finite |

### A parameter that cannot be read

Always reason `MISSING_INPUT` (G4, the two rows for a parameter). The detail names the parameter as `parameter '<id>' with scope <scope>`, the scope written as JSON with sorted keys (`{}`, `{"crop": "<crop_id>"}`, `{"management": "no_crop"}`):

| Situation | `detail` |
|---|---|
| A record anywhere in `parameters` without a well-formed `id` and `scope` (only in a catalogue that `check_catalogue` rejects, G3). It cannot be compared, so it could be a record of this parameter: it is reported, not skipped (F3c of `params/README.md`). PROPOSED, OPEN 18 | `parameter '<id>' with scope <scope> cannot be looked up: the record(s) '<key>', ... have no well-formed 'id' and 'scope', ...` |
| No record with that id and scope | `parameter '<id>' with scope <scope> has no record in parameters (D56)` |
| More than one such record (only in a catalogue that `check_catalogue` rejects, G3) | `parameter '<id>' with scope <scope> has more than one record in parameters, which params.catalogue.check_catalogue rejects (G3)` |
| `read_value` refuses the record (malformed, or a placeholder) | `the record of parameter '<id>' with scope <scope> is refused by params.catalogue.read_value: <its message>` |
| The record has `"value": null` | `the record of parameter '<id>' with scope <scope> has no value: <value_missing_reason of the record>` |

A record with another scope, wider or narrower, is not read (question 5 of `params/README.md`, OPEN 3). Each id and scope is looked up once per call.

### The annual product

`equation.annual_soil_loss(r=..., k=..., ls=..., c=..., p=..., accepted_units=ACCEPTED_UNITS, unit_guard_reason=ls.REASON_UNIT_NOT_ACCEPTED)`, as `EQUATION.md` describes it: `MISSING_INPUT` naming every missing factor (`factor '<name>' is missing (reason <CODE>: <detail>)`); then the unit guard; then `NOT_COMPUTABLE` for a product that is not finite. The factor names are those of `equation.FACTOR_NAMES`: `r`, `k`, `ls`, `c`, `p`.

A number is returned as an `AnnualSoilLoss` with:

- `provenance` `DERIVED` (C4.6);
- `source`: `derived by engine.erosion.compute_soil_loss with the product of docs/METHODS.md M1.1: R of the agricultural year as the sum of R by month of engine/erosion/r_factor/ ... ; parameter records read: '<id>' with scope <scope>, ...`, naming the method of each factor and every record read for that year with its scope (PROPOSED; question 11 of `contracts/results/README.md`, OPEN 14);
- no `range`, and `range_missing` with reason `NOT_AVAILABLE`: how a range passes through the product is not built (C2.3, OPEN 5 of `EQUATION.md`).

## Numbers in the modules

`soil_loss.py` holds two integers, `12` and `1`, and no other number. `_parameters.py` holds one, the `1` of "more than one record". A test reads both modules and fails on any other number, and on any format specification in an f-string of `soil_loss.py`.

| Integer | Where | Why |
|---|---|---|
| `12` | `soil_loss.py`, `_MONTHS_IN_A_YEAR` | Twelve calendar months to a year and to an agricultural year (C5.1, C5.3) |
| `1` | `soil_loss.py`, `_FIRST` | Months and days are counted from one (C5.1); "more than one" component on a day or on the last harvest date; one reason shared by every missing month |
| `1` | `soil_loss.py`, `_ONE_AGRICULTURAL_YEAR` | `C` of one agricultural year is `rotation_c` over one year (OPEN 25) |
| `1` | `_parameters.py` | More than one record with one id and scope |

The test file builds its PLACEHOLDER numbers as `PLACEHOLDER_BASE` plus the position in the list of identifiers, a base plainly unreal, far above any value a factor or a coefficient of RUSLE takes. The records whose forms need a number of a certain size to give any result (the exponent and the threshold of the daily index, the coefficients of `c_factor/`, and the crop records: a canopy cover is a fraction) carry repeated digits (`1.11`, `0.555`), as `engine/water/test_exposure.py` does. The daily precipitation of a computable series repeats `RAIN`, repeated digits and zero, plainly not weather. None is a value of the method. Every record carries the word PLACEHOLDER in its citation, persons and reasons, and is passed as an in-memory copy in which the word is replaced by `UNMARKED_TEST_ONLY`, as `params/test_layout.py` does (question 12 of `params/README.md`); that copy passes `check_catalogue`.

The expected soil loss of a computable run is computed again in the test, day by day, from the PROPOSED forms of `r_factor/README.md` and `c_factor/README.md` and the calendar the test built, without calling the module.

## PROPOSED cases

The identifier is the name of the test function in `test_soil_loss.py` without `test_`, with hyphens. A test checks that this list and the test functions agree.

A *computable* run, in the cases below, has every input that EP1 needs: a precipitation series in `mm day-1` with every day present, a calendar of the same field with the two PLACEHOLDER crops in every agricultural year and one harvest before the record begins, soil data with a slope in `percent`, and a complete PLACEHOLDER catalogue.

### Cases of #125, kept

| Case | What it checks |
|---|---|
| `examples-with-several-agricultural-years-load-into-soil-loss-results` | From the examples, with a `precipitation` series spanning several agricultural years: one `AnnualSoilLoss` per agricultural year of D47 and twelve consecutive `MonthlySoilLoss` per year; indicator, direction and unit from the constants of `contracts/results/models.py`; the round trip through `model_dump(mode="json")` loads back equal |
| `start-month-missing-returns-one-missing-input` | A missing start month: one `Missing`, reason `MISSING_INPUT`, detail names the start month |
| `infeasible-calendar-makes-every-value-not-computable` | An infeasible calendar: every value `NOT_COMPUTABLE`, with an empty catalogue and with a computable run, also for years the series does not cover |
| `year-or-month-not-covered-by-precipitation-is-no-coverage` | Years and months the series does not cover are `NO_COVERAGE`; a covered year is `MISSING_INPUT` (empty catalogue); a covered month is `NOT_AVAILABLE`, also inside a year that is not covered whole |
| `series-one-day-short-at-each-end-leaves-first-and-last-not-covered` | The first and last agricultural years, and the first and last months, are `NO_COVERAGE`; every year between is `MISSING_INPUT` and every month between `NOT_AVAILABLE` |
| `calendar-dates-outside-the-record-keep-the-years-of-the-record` | A calendar moved past the record: the years are those of the record (D47). Changed by #173: since `C` reads the calendar, the moved calendar leaves `C` missing in every year, naming D47, where the same calendar on the record gives a number; the results are no longer equal |
| `no-precipitation-series-returns-one-missing-input` | No `precipitation` series: one `Missing`, reason `MISSING_INPUT`, detail names `precipitation` |
| `missing-slope-input-is-named-in-the-ls-factor` | In a computable run, `slope_steepness`, `slope_length` or both missing in `SiteSoilSlope`: the year is `MISSING_INPUT`, only factor `ls` is named, with each missing input and its own reason |
| `arguments-of-another-case-or-field-raise-value-error` | `case_id` or `field_id` of `climate` or `soil_slope` differs from the calendar: `ValueError` naming the field (G5) |
| `argument-that-is-not-its-model-raises-type-error` | `calendar`, `climate` or `soil_slope` given as a dictionary or as another model: `TypeError` naming the argument (G5) |

### The argument `parameters` (#154), kept

| Case | What it checks |
|---|---|
| `parameters-missing-positional-or-not-a-dict-raises-type-error` | `parameters` left out, passed by position, or not a `dict` (`None`, a list, a tuple, text, a list of pairs), or a `dict` with an item that is not a `dict` or a key that is not `str`: `TypeError` (G3, G5) |
| `empty-catalogue-names-every-parameter-and-keeps-every-year` | `{}` in an otherwise computable run: every agricultural year of D47 is present and `MISSING_INPUT`; the detail names the five factors; every site identifier with `scope {}` and D56; in the part of `R`, the three records of `R` with M1.2, `r_factor/`, the daily index and the mean annual level; in the part of `C`, the fractions, the three site coefficients, the canopy records of each crop and of no crop, and the residue records of each crop, each with its scope, with M1.5, D45, `c_factor/`, the canopy sub-factor and the residue cover; never `rusle_c_factor`; every month is `NOT_AVAILABLE` naming M1.2 |
| `full-catalogue-gives-the-product-of-equation-py` | A computable run over a series that does not cover its first and last years: each covered year's value equals the soil loss computed again in the test (`R` from the daily index, fractions and ratios; `C` from the daily ratio of each day of the calendar, averaged by month and weighted by the fractions; `K`, `LS` from `ls.py`, `P`); it equals `equation.annual_soil_loss` of those factors; it carries `DERIVED`, a source naming `r_factor/`, `c_factor/` and every record read with its scope, no range and `range_missing` `NOT_AVAILABLE`; years not covered stay `NO_COVERAGE`; months stay missing; the result loads back equal |
| `ls-is-computed-through-ls-py-from-the-catalogue` | With the break slope above the slope and at the slope, and each `LS` record changed in turn: the value equals the soil loss computed again with the changed numbers |
| `removing-any-one-record-makes-the-year-missing-and-names-it` | For each site identifier: without its record every year is `MISSING_INPUT`, and the detail names that identifier with `scope {}` and no other identifier |
| `record-with-null-value-repeats-its-reason` | A record of the level of `R`, of `s_break`, of the fall-height coefficient or of the residue mass of a crop with `"value": null` (the catalogue still passes `check_catalogue`): `MISSING_INPUT`, the parameter named with its scope and its reason repeated (G4) |
| `record-that-read-value-refuses-is-missing-input` | A record still marked PLACEHOLDER, and a record without `unit`: `MISSING_INPUT`, naming the parameter and the refusal of `read_value` |
| `only-a-record-with-the-empty-scope-is-read` | A record of `P` with a `management` scope instead of `{}`: not read, `MISSING_INPUT` naming `P` with `scope {}` (OPEN 3) |
| `two-records-with-one-identity-are-missing-input` | Two records of the surface-cover coefficient with one id and scope: `MISSING_INPUT`, saying there is more than one |
| `record-that-cannot-be-compared-is-reported-not-skipped` | A record with `id` null, `scope` null, or an `id` that starts with a digit: every parameter is `MISSING_INPUT` and its detail names that record by its key; never "has no record" (F3c of `params/README.md`) |
| `slope-unit-that-ls-py-cannot-read-is-not-computed` | A `slope_steepness` unit, or an `s_break` record unit, that is no `SlopeUnit` value: `LS` missing with `ls.REASON_UNIT_NOT_ACCEPTED`, naming which |
| `factor-in-another-unit-is-stopped-by-the-unit-guard` | A `K` record in another unit string than D11's: the year is missing with the unit-guard reason, naming factor `k` (changed by #173 from `R`, which `r_factor/` now checks) |
| `no-value-is-a-number-unless-every-factor-is-present` | Over the cases with an empty catalogue, with one record left out, with a full catalogue but a slope unit that is not read, without the residue record of a crop, with a series without an erosive day: no value is a number, none is zero, every value has a `missing` part with a code of C3.2 and carries no range, source or provenance |
| `arguments-unchanged-and-second-call-equal` | With an empty catalogue and with a computable run: the arguments, `parameters` included, equal a deep copy taken before the call, and a second call gives an equal result (G1) |

### `R` through `r_factor/` and `C` through `c_factor/` (#173)

| Case | What it checks |
|---|---|
| `chain-example-climate-gives-r-and-c-through-r-factor-and-c-factor` | The chain example climate (`contracts/inputs/examples/PLACEHOLDER_chain_site_climate.json`), the chain soil data, a computable calendar of the same field and a complete catalogue: the one covered year equals the soil loss computed again in the test; with one year its ratio is one, each fraction is the share of the month's days in the year, and `R` equals the level |
| `removing-any-one-crop-record-makes-c-missing-and-names-it-with-its-scope` | For each crop record (canopy cover and fall height of each crop and of no crop; residue mass and decay coefficient of each crop): without it every year is `MISSING_INPUT`, only factor `c` is named, and the detail names the record with its scope and the part of M1.5 that needs it, and no other crop identifier |
| `crop-without-residue-type-or-canopy-record-leaves-c-missing-and-names-it` | One crop without a decay coefficient (no residue type) and the other without a canopy cover: `C` is `MISSING_INPUT`, never zero, and names both records with their crops |
| `year-without-an-erosive-day-leaves-r-and-c-missing-for-that-year` | A year whose every day lies at the threshold, between computable years: that year is missing, with `R` and `C` both missing and naming the year without an erosive day; every other year is a number above or below zero, not zero |
| `missing-day-in-the-series-makes-its-year-missing-and-no-other` | A day without data: its year is `MISSING_INPUT`, `R` and `C` missing, naming its month; the other years are numbers (OPEN 1) |
| `day-outside-the-calendar-or-before-the-first-harvest-leaves-c-missing` | A calendar that begins on the first day of the record (no harvest before it), one that ends a year early (days outside the calendar, naming D47), and one whose last component has no end date: only the years with such days are missing, with `C` naming the problem and the number of days; the other years are numbers |
| `unit-strings-of-c-records-that-are-not-read-are-not-computed` | A canopy cover that is not `dimensionless`, a decay coefficient whose unit is not read as an inverse, a surface-cover coefficient that is not `dimensionless`, and a fall-height coefficient whose unit is the inverse of another length: `C` missing with `ls.REASON_UNIT_NOT_ACCEPTED`, naming the record and its scope, or the refusal of `canopy_subfactor` |
| `value-c-factor-refuses-is-not-computed-and-names-the-day` | A canopy cover above one: `C` is `NOT_COMPUTABLE`, naming the day, `canopy_subfactor` and its refusal |
| `r-level-threshold-or-series-in-another-unit-is-refused-by-r-factor` | A level of `R`, a threshold or a series in another unit string: `R` missing (and `C`, when the fractions need it), naming the unit; no other factor is named |
| `whole-factor-record-of-c-is-not-read` | A catalogue that also holds `rusle_c_factor` gives the same result as one without it, and the source does not name it (OPEN 12) |
| `per-unit-reads-only-the-proposed-inverse-forms` | `day-1`, `m-1`, `(kg m-2)-1` and `(m)-1` are read; `day`, `kg m-2-1`, `-1`, `()-1`, `( )-1`, `m-2`, a trailing space and an unclosed bracket are not (OPEN 21) |

### The modules

| Case | What it checks |
|---|---|
| `modules-import-only-allowed-modules-and-hold-only-counting-integers` | `soil_loss.py` imports only the standard library, `contracts.inputs.*`, `contracts.results.models` and `engine.erosion` (`c_factor`, `ls`, `r_factor`, `equation`, `_parameters`); `_parameters.py` only the standard library, `contracts.results.models` and `params.catalogue`; neither names `load_folder`, `check_folder`, `check_layout`, `open` or `read_text` (G1); the numbers are those of the table above; no format specification in an f-string |
| `package-exposes-compute-soil-loss-with-parameters-by-keyword-and-no-default` | `from engine.erosion import compute_soil_loss` works; its parameters are `calendar`, `climate`, `soil_slope`, `parameters`; `parameters` is keyword-only and has no default |
| `soil-loss-md-lists-every-parameter-identifier` | The table [Parameters EP1 reads](#parameters-ep1-reads) lists exactly the identifiers the module reads, site and crop, and the section names `rusle_c_factor` as no longer read |
| `proposed-cases-match-soil-loss-md` | This list and the test functions agree |

## Changes outside this folder that this unit needs

`validation/test_chain_examples.py`, case CH06, and its row in `validation/README.md` are updated in this unit, at the orchestrator's request (lane L0). CH06 used to expect `R` and `C` read as whole-factor records. It now asserts two things with a complete PLACEHOLDER catalogue (its site records, with numbers of a usable size for the daily index and the coefficients of `c_factor/`, and crop records):

- through the runner, on the calendar EP2 builds from the rotation definition example (2027 and 2028, after the record of 2001 and 2002), each covered year is missing with only factor `c` named, for the days outside the calendar (D47, OPEN 2), so `R`, `K`, `LS` and `P` are computed;
- EP1 on the same calendar laid on the record gives a number equal to `equation.py` of `R` and `C` computed again in the test from the PROPOSED forms of `r_factor/` and `c_factor/`.

CH05 and CH07 are unchanged and pass: `PARAMETER_IDS` is every identifier read with the empty scope, and `C_ID` stays as the name of the record that is no longer read. Nothing else outside `engine/erosion/` is changed.

## OPEN

Each item is a question a person has to answer, with the role that answers it. None is answered by this unit.

1. **Days missing inside the `precipitation` series.** Now applied through `r_factor/`: a missing day makes its month and its agricultural year missing (`MISSING_INPUT`), and that year is left out of the mean of the yearly ratios (OPEN 1 of `r_factor/README.md`). Whether this is the wanted rule (C3.4 leaves the gap-filling method OPEN). For the science reviewers.
2. **Repeating the rotation over the years of the record (D47).** Not implemented. `C` reads the crop and the last harvest of each day from the calendar's own dates; a day outside them makes `C` of its year missing, naming D47. With a real calendar, whose dates lie after the record (2001 to 2024, D29), every year is missing. How the rotation is laid onto the years of the record changes `_crop_scope` and `_last_harvest` in `soil_loss.py` and nothing else; `engine/water/` waits for the same answer. For the lead developer.
3. **Scope of the site records: `{}`.** The smallest form: one record per identifier, "no restriction stated". `R`, `K` and `P` belong to a field, so the empty scope says one value for every field. The scope words are question 4 of `params/README.md`; which record is read when one has the empty scope and another names a crop is question 5. This unit reads only the exact scopes of the table. For the lead developer, who owns `params/`.
4. **Reading a slope unit.** A unit string is read as the `SlopeUnit` whose value is that exact string. The unit strings of a slope in the input contract are question 18 of `contracts/inputs/README.md`; the unit of the break slope is OPEN 1 and 8 of `LS.md`. The reason code of a unit not read is `ls.REASON_UNIT_NOT_ACCEPTED` (Q11). For the science reviewers (the units), the lead developer (the reading and the code).
5. **Months not covered by the series.** C5.5 speaks of yearly values; this unit also writes `NO_COVERAGE` for a month. For the lead developer.
6. **Precedence of the reasons.** Infeasible calendar, then coverage, then the factors; of the two single `Missing`, the start month before the series; inside `LS`, missing inputs before a unit not read before the result of `ls.py`; inside `C`, every missing input (fractions, crop and residue of each day, records) before a unit string not read before the first refusal of `c_factor/`, day by day in order; a `C` with problems of several kinds is `MISSING_INPUT` when any is a missing input. For the lead developer.
7. **With the calendar engine of today, EP1 may always return one `Missing`.** If the calendar engine writes the start month as missing until the rotation definition carries it (D7, D8), the erosion module is `not_available` through the route. Whether the return type of EP1 changes after D7 is not said by issue #77. For the lead developer and the platform developer.
8. **The day boundaries of an agricultural year.** Years, months and the days since a harvest are cut on the dates of the series and of the calendar, in the series' time zone (C6.1, C6.2), not on the local day at the field (C6.5). For the science reviewers.
9. **Where the identifier `precipitation` lives.** Written once in `soil_loss.py`. Whether contracts should export the quantity identifiers as constants. For the lead developer and the platform developer.
10. **Example data (Q16).** The inputs carry `example_data`; `SoilLossResults` has no field for it. A number computed from example soil data carries no mark of it. For the lead developer and the platform developer.
11. **The variation between years.** Now built: `R` of a year carries the yearly ratio of `r_factor/`, and `C` of a year its fractions and the calendar of that year. The ratio's mean is over the years of the record whose annual sum is a number, so `R` of one year depends on which other years the record holds (OPEN 6 of `r_factor/README.md`). For the science reviewers.
12. **The whole-factor records of `C` and `R`.** PROPOSED: `rusle_c_factor` is no longer read, and stays no override: one number for the rotation would bypass the channel by which rotations differ (M1.1). `rusle_r_factor` is read as the mean annual level, so a whole `R` has no record. The alternative is to keep `rusle_c_factor` (and a new identifier for a whole `R`) as an override that, when present, replaces the computed factor, with its source in the value's `source`. For the lead developer and the science reviewers.
13. **`K` from the catalogue.** D48 brings `K` from the soil data through the platform adapters (D10). Until a field carries it, `K` is read from a catalogue record. When it arrives in `SiteSoilSlope` (question 16 of `contracts/inputs/README.md`), which one wins is for the lead developer and the platform developer.
14. **The source text of a computed value.** Question 11 of `contracts/results/README.md`. The text names the method of each factor and every record read for that year with its scope, not their citations. For the lead developer.
15. **The units of the coefficient records of `LS`, and of the exponent of the daily index.** Not checked (OPEN 4 of `LS.md`). For the science reviewers.
16. **`P` under no-till.** M1.6 says `P` is one by default under no-till. This unit writes no default: `P` is read from a record like the other factors. For the lead developer and the science reviewers.
17. **`ls.py` has no `LS` function.** It returns `S` and `L`; the product `L * S` is written in `soil_loss.py`, with a finiteness check. Whether `ls.py` should offer it is for the lead developer (not changed here, as the brief says).
18. **A record that `read_value` refuses, or that cannot be compared.** G4 has rows for a parameter without a record and for a record with `"value": null`. A refused record (malformed or a placeholder), two records with one identity, and a record without a well-formed `id` and `scope` are possible only in a catalogue that `check_catalogue` rejects (G3); each is answered with `MISSING_INPUT` too, naming the parameter. A record that cannot be compared is reported, not skipped (F3c of `params/README.md`): PROPOSED, it makes **every** parameter missing, because it could be a record of any of them. For the lead developer and the platform developer.
19. **Who reads `detail`.** The format above is for developers. If the interface shows it, its wording belongs to the strings file of `web/` and to people. For the interface developer and the lead developer.
20. **Monthly values of soil loss.** C1.2 allows a monthly breakdown whose months add up to the year. `R` by month and the soil-loss ratio of each month now exist, but M1.1 and M1.5 give only the annual product; how a monthly value is formed (for example `R` of the month times `K`, `LS`, the ratio of the month and `P`) is not decided, so every covered month stays `NOT_AVAILABLE`. For the lead developer and the science reviewers.
21. **Unit strings of the records of `C`.** The inverse of a unit written `<u>-1` or `(<u>)-1`; the canopy cover and the surface-cover coefficient in `dimensionless` (fractions, not percent: OPEN 3 of `c_factor/README.md`); the time since a harvest in `day`. Which unit strings the records carry is for the science reviewers (OPEN 4 of `c_factor/README.md`); the reading, for the lead developer.
22. **Crop of a day, and stage.** The canopy records are read by the crop of the day, or `{"management": "no_crop"}`, as `engine/water/` does. On a day with no crop the canopy cover and fall height are still read from records (no zero is written). The periods of a component (`CalendarPeriod`, "for cover management by period") are not read: M1.5 asks for canopy cover and fall height "by stage", and whether a period's `period_type` becomes the scope key `stage` is for the lead developer (the scope) and the science reviewers (the stages).
23. **Residue on the surface.** PROPOSED: the residue of a day is that of the last harvest (the end date of a component) before it, its mass read by that crop, decayed from the end date with the decay coefficient of that crop's residue type. The residue type is named by the scope key `crop` (`params/README.md` has no key for a residue type, question 4). Older residue is not added, and the residue before the first harvest of the calendar is not known. M1.5 names "the residue cover at sowing" as the most sensitive input and asks for the result at more than one level; neither is applied (one call is one scenario). Whether the residue comes from the residue ledger instead is Q12 of `contracts/ENTRYPOINTS.md`. For the lead developer and the science reviewers.
24. **The soil-loss ratio of a month.** PROPOSED: the mean of the daily ratios over the days of the month. The alternatives are to weight each day by its erosivity, or to take the ratio of one day of the month. For the science reviewers.
25. **`C` by agricultural year.** PROPOSED: `rotation_c` over the twelve months of each agricultural year with one year, so `C` changes from year to year and a year whose fractions are missing leaves only that year missing. M1.5 divides by "the number of years of the rotation", which would give one `C` over all the years of the record. For the lead developer and the science reviewers.
26. **The control regression of M1.2.** `r_factor/` offers the control and its comparison with the fractions as a report. EP1 does not run it, so its two constants are not read and no comparison reaches the result. Whether and where it is reported is for the lead developer and the science reviewers (OPEN 8 of `r_factor/README.md`).
27. **The tolerance of the sum of the fractions.** EP1 passes it to `rotation_c` as missing (`NOT_AVAILABLE`), because no person has supplied it (OPEN 9 of `c_factor/README.md`); `C` does not need it. For the lead developer and the science reviewers.
