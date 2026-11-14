# Water entry point

Unit `l1/water-ep3-parameters` (issue #153): entry point EP3 of `contracts/ENTRYPOINTS.md`, `compute_water_deficit_exposure`, in `engine/water/exposure.py`, exported by `engine/water/__init__.py`. It replaces the mechanical form of unit `l1/water-entrypoint` (issue #134). The lookup of a parameter lives in `engine/water/_parameters.py`.

> **Status: PROPOSED** (blueprint section 3.7). The order of the checks, the reason code of each item, the identifier and scope of each parameter, how the crop of a day is read from the calendar, the format of every `detail`, the choices under [PROPOSED choices](#proposed-choices) and the test cases below were written by a builder session. They take effect only when a person approves the pull request. Items under [OPEN](#open) need an answer from a person.

**What this unit does.** For every day of the climate record it chains the four internal parts of the water engine of D44: the reference evapotranspiration (`et0/`), the runoff by the Curve Number (`runoff/`), the evaporation coefficient `Ke` from the surface-layer balance (`evaporation/`) and the one-layer daily balance (`balance/`). Every constant and parameter of those parts is read from the argument `parameters` by its `id` and `scope`. The daily chain is reduced to one item per agricultural year of the record (D47).

**What it returns is never a number.** Convention C1.4 says that while the definition of the indicator is incomplete (the critical period, which quantities of the balance are water transpired and water demanded), no engine reports `water_deficit_exposure` as anything but missing. So a year whose daily balance was computed on every day is missing with `NOT_AVAILABLE` and a detail saying the definition is incomplete (D61); every other year is missing with the reason that applies. The four parts are called, not changed. This folder holds no parameter value: not in the code, not in this file. The numbers of the test file are PLACEHOLDER, plainly not real.

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
    *,
    parameters: dict[str, dict],
) -> list[WaterDeficitExposure]
```

As EP3 is written in `contracts/ENTRYPOINTS.md` since #144 (Q3, D46, D56). `parameters` is passed by keyword only and has no default (G3). It is the catalogue exactly as `params.catalogue.load_folder` returns it for `params/records/`: every record, keyed by the path of its file. The models are imported only as `contracts.inputs.<module>` and `contracts.results.models`; `Missing` is the one of `contracts/results/models.py`; no new missing shape is defined.

The entry point reads a record only through the pure readers of `params.catalogue`: `identity` to find it by `id` and `scope`, and `read_value` to read it (G1). It never calls `load_folder` and reads no file. `read_range` is not used: no range is computed, because one call is one scenario and no indicator value is a number (Q6).

`soil_slope` is checked (G3, G5) and not read: no part reads a soil property yet. The soil's available water of D49 is read as the parameter `column_capacity` when a record exists (OPEN 7).

## What it returns

Always a list with at least one item, and no item is a number. Every item keeps `indicator`, `direction` and `unit` (C3.1), read from `contracts/results/models.py`. A missing item carries no provenance, no source, no range and no `range_missing` (the model forbids them).

| Case | What is returned |
|---|---|
| `calendar.ag_year_start.month` is missing | One item, `time_basis: "rotation"`, reason `MISSING_INPUT`, detail names the start month |
| `climate.daily_series` has no `precipitation` series | One item, `time_basis: "rotation"`, reason `MISSING_INPUT`, detail names `precipitation` |
| Otherwise | One item per agricultural year of the `precipitation` series (D47), `time_basis: "ag_year"`, with its `ag_year`, each missing with the first reason of the table below |

Reason of each yearly item, the first row that applies:

| Situation | Reason | Convention |
|---|---|---|
| The calendar is infeasible (`feasibility.feasible` is false) | `NOT_COMPUTABLE`, every year; the chain does not run | G4, first row |
| The daily series the water engine reads that are present do not share one time zone | `NOT_COMPUTABLE`, every year; the chain does not run | C6.3; G4, sixth row |
| A series the water engine reads that is present does not cover the year from its first day to its last | `NO_COVERAGE`; detail names each such series | C5.5 |
| A series, or the latitude or elevation of the point, arrives in a unit string the parts do not accept | `MISSING_INPUT` (PROPOSED, Q11); detail names each one and both unit strings; the chain does not run | C1.1; G4, seventh row |
| The daily chain has no value on a day of the year (the storage at the end of a balance day is missing) | The reason of the first such day: `MISSING_INPUT`, or `NOT_COMPUTABLE` when a part refused a value; detail below | G4, second to fourth rows and the two rows of a parameter; C3.3 |
| The daily balance was computed on every day of the year | `NOT_AVAILABLE`, detail: the definition of the indicator is incomplete (C1.4) | D61 |

The daily series the water engine reads are `precipitation` (D23) and the five inputs of the reference evapotranspiration, read from `CLIMATE_QUANTITIES` of `engine/water/et0/quantities.py`. The unit string of each is the one the parts transcribed from `contracts/CLIMATE_QUANTITIES.md` (`PRECIPITATION_UNIT` of `runoff/`, `ACCEPTED_UNITS` of `et0/`). The point is accepted in the unit strings D55 sets for the climate adapter: `degree` for latitude, `m` for elevation.

### The daily chain

The chain runs from the first day that every series it reads covers to the last day of the `precipitation` series, one day after the other, never resetting a state (D44). For each day:

1. **Reference evapotranspiration**: `reference_evapotranspiration_from_climate` of `et0/`, with `Et0Constants` built from the catalogue, `PointUnits` of D55, and a unit-guard code that is never emitted (units are checked before the chain runs).
2. **Crop of the day** (PROPOSED): the crop identifier of the one component of the calendar whose dates cover the day; no crop when none does; not known (`MISSING_INPUT`, naming Q5) for a day outside the dates of the calendar; not known (`MISSING_INPUT`) when a component has a missing date and no dated component covers the day; `NOT_COMPUTABLE` when two components cover the day.
3. **Runoff**: `runoff_day` of `runoff/`, with the precipitation of the day, the curve number of the crop of the day (or of a day with no crop) and `CurveNumberConstants` from the catalogue.
4. **`Ke`**: the climate term of the upper limit (`climate_adjusted_upper_limit`, from the wind speed of the day, the minimum relative humidity and the crop height), the upper limit (`upper_limit_of_crop_coefficient`), the cover fraction (`cover_fraction_from_basal_coefficient`), then `step` of `evaporation/`, carrying the depletion of the surface layer from day to day.
5. **Balance**: `step` of `balance/`, with the precipitation, the runoff, the reference evapotranspiration, the `Ke` of the surface layer and the crop of the day (`CropDay` from the catalogue, `None` on a day with no crop), carrying the storage from day to day.

The entry point calls the daily `step` of the surface layer and of the balance, not `run_surface_layer` and `run_balance`, so that a value one part refuses on one day makes that day missing instead of raising for the whole record. Once the state at the end of a day is missing, every later day starts from a missing state that names the first cause, exactly as the two `run_` functions carry it.

### Format of `detail` (PROPOSED)

English, for developers. A year the chain did not compute reads `water_deficit_exposure is not computed for agricultural year <Y>: the daily water balance has no value on <n> day(s) of the year, the first on <date> (<code>: <detail of that day>); <item>; <item>; ...`. The items, in this order:

| Item | When |
|---|---|
| `input MISSING_INPUT: the climate record has no daily series '<name>' (G4, third row)` | One per absent series |
| `input MISSING_INPUT: the daily series '<name>' holds <n> day(s) without a value in agricultural year <Y>, the first on <date>, and no gap is filled (G4, fourth row, C3.4)` | One per series with days held missing in the year |
| `input <code>: the <latitude or elevation> of the point of the climate record is missing: <its detail>` | One per missing value of the point the reference evapotranspiration reads; longitude is not read |
| `parameter MISSING_INPUT: parameters with no record in parameters (D56), scope <scope>: '<id>', '<id>', ...` | One per scope, naming every parameter with no record that was first needed on or before the last day of the year |
| `parameter MISSING_INPUT: parameter '<id>' with scope <scope>: the record holds no value: <reason of the record>` | One per record whose value is `null` |
| `parameter MISSING_INPUT: parameter '<id>' with scope <scope>: the record is not read: <why>` | One per record that `read_value` refuses (its message), or per two records that share `id` and `scope` |
| `parameter MISSING_INPUT: parameters that cannot be looked up: the record(s) '<key>', ... have no well-formed 'id' and 'scope', so they cannot be compared and could be records of this parameter (F3c of params/README.md); ...`, then `parameter MISSING_INPUT: parameters that cannot be looked up, scope <scope>: '<id>', '<id>', ...` | When a record of `parameters` has no well-formed `id` and `scope`: the malformed records named once by their key, then the parameters grouped by scope, as above |
| `chain <code>: <detail>` | One per problem of the chain met on or before the last day of the year: a crop that is not known, two components on one day, a value a part refuses (`<part> refuses a value: <its message>`) |
| `indicator NOT_AVAILABLE: the definition of the indicator is incomplete (C1.4) ... (decision D61 of issue #77)` | Always, last |

A scope is written as JSON text with sorted keys: `{}`, `{"crop": "<crop identifier>"}`, `{"management": "no_crop"}`. The other details are one fixed text each: infeasible calendar, time zones, start month, `precipitation` absent, a year not covered (`the daily series '<name>', ... do not cover agricultural year <Y> from its first day to its last (C5.5)`), units not accepted (naming Q11 and each unit string), and a computed year (`... the daily water balance was computed on every day of the year, but the definition of the indicator is incomplete (C1.4) ... (decision D61 of issue #77)`).

## Parameters

PROPOSED: one identifier and one scope for each parameter the chain reads. Where a part's README table proposes an identifier it is used as it is; the identifiers of `et0/` and of the climate term of `evaporation/` are written there as `<group>.<field>`, and a record `id` holds no dot (`params/README.md`), so the dot is written as an underscore. The value of every row is a person's (D34); none is in this repository.

The scope column says how a parameter is looked up (PROPOSED; the words allowed under each scope key are question 4 of `params/README.md`, OPEN):

- `site`: the empty scope `{}`. One record for the field and the method.
- `crop or no crop`: `{"crop": "<crop_id>"}`, the `crop_id` of the calendar component of the day; on a day with no crop, `{"management": "no_crop"}`.
- `crop`: `{"crop": "<crop_id>"}` only; read on a day with a crop.

The lookup is exact: a record with the empty scope is never read in place of one that names a crop, nor the other way round (question 5 of `params/README.md`, OPEN).

| Identifier | Scope | Part | What it feeds |
|---|---|---|---|
| `atmospheric_pressure_sea_level_pressure` | site | `et0/` | `Et0Constants.atmospheric_pressure.sea_level_pressure` (README identifier `atmospheric_pressure.sea_level_pressure`) |
| `atmospheric_pressure_reference_temperature` | site | `et0/` | `Et0Constants.atmospheric_pressure.reference_temperature` (README identifier `atmospheric_pressure.reference_temperature`) |
| `atmospheric_pressure_lapse_rate` | site | `et0/` | `Et0Constants.atmospheric_pressure.lapse_rate` (README identifier `atmospheric_pressure.lapse_rate`) |
| `atmospheric_pressure_exponent` | site | `et0/` | `Et0Constants.atmospheric_pressure.exponent` (README identifier `atmospheric_pressure.exponent`) |
| `psychrometric_coefficient` | site | `et0/` | `Et0Constants.psychrometric.coefficient` (README identifier `psychrometric.coefficient`) |
| `saturation_vapour_pressure_scale` | site | `et0/` | `Et0Constants.saturation_vapour_pressure.scale` (README identifier `saturation_vapour_pressure.scale`) |
| `saturation_vapour_pressure_numerator` | site | `et0/` | `Et0Constants.saturation_vapour_pressure.numerator` (README identifier `saturation_vapour_pressure.numerator`) |
| `saturation_vapour_pressure_offset` | site | `et0/` | `Et0Constants.saturation_vapour_pressure.offset` (README identifier `saturation_vapour_pressure.offset`) |
| `slope_multiplier` | site | `et0/` | `Et0Constants.slope.multiplier` (README identifier `slope.multiplier`) |
| `inverse_relative_distance_offset` | site | `et0/` | `Et0Constants.inverse_relative_distance.offset` (README identifier `inverse_relative_distance.offset`) |
| `inverse_relative_distance_amplitude` | site | `et0/` | `Et0Constants.inverse_relative_distance.amplitude` (README identifier `inverse_relative_distance.amplitude`) |
| `inverse_relative_distance_days_in_year` | site | `et0/` | `Et0Constants.inverse_relative_distance.days_in_year` (README identifier `inverse_relative_distance.days_in_year`) |
| `solar_declination_amplitude` | site | `et0/` | `Et0Constants.solar_declination.amplitude` (README identifier `solar_declination.amplitude`) |
| `solar_declination_days_in_year` | site | `et0/` | `Et0Constants.solar_declination.days_in_year` (README identifier `solar_declination.days_in_year`) |
| `solar_declination_phase` | site | `et0/` | `Et0Constants.solar_declination.phase` (README identifier `solar_declination.phase`) |
| `extraterrestrial_radiation_time_factor` | site | `et0/` | `Et0Constants.extraterrestrial_radiation.time_factor` (README identifier `extraterrestrial_radiation.time_factor`) |
| `extraterrestrial_radiation_solar_constant` | site | `et0/` | `Et0Constants.extraterrestrial_radiation.solar_constant` (README identifier `extraterrestrial_radiation.solar_constant`) |
| `clear_sky_radiation_base` | site | `et0/` | `Et0Constants.clear_sky_radiation.base` (README identifier `clear_sky_radiation.base`) |
| `clear_sky_radiation_elevation_coefficient` | site | `et0/` | `Et0Constants.clear_sky_radiation.elevation_coefficient` (README identifier `clear_sky_radiation.elevation_coefficient`) |
| `net_shortwave_albedo` | site | `et0/` | `Et0Constants.net_shortwave.albedo` (README identifier `net_shortwave.albedo`) |
| `net_longwave_stefan_boltzmann` | site | `et0/` | `Et0Constants.net_longwave.stefan_boltzmann` (README identifier `net_longwave.stefan_boltzmann`) |
| `net_longwave_kelvin_offset` | site | `et0/` | `Et0Constants.net_longwave.kelvin_offset` (README identifier `net_longwave.kelvin_offset`) |
| `net_longwave_humidity_intercept` | site | `et0/` | `Et0Constants.net_longwave.humidity_intercept` (README identifier `net_longwave.humidity_intercept`) |
| `net_longwave_humidity_slope` | site | `et0/` | `Et0Constants.net_longwave.humidity_slope` (README identifier `net_longwave.humidity_slope`) |
| `net_longwave_cloudiness_multiplier` | site | `et0/` | `Et0Constants.net_longwave.cloudiness_multiplier` (README identifier `net_longwave.cloudiness_multiplier`) |
| `net_longwave_cloudiness_offset` | site | `et0/` | `Et0Constants.net_longwave.cloudiness_offset` (README identifier `net_longwave.cloudiness_offset`) |
| `soil_heat_flux_daily_value` | site | `et0/` | `Et0Constants.soil_heat_flux.daily_value` (README identifier `soil_heat_flux.daily_value`) |
| `penman_monteith_radiation_factor` | site | `et0/` | `Et0Constants.penman_monteith.radiation_factor` (README identifier `penman_monteith.radiation_factor`) |
| `penman_monteith_numerator_constant` | site | `et0/` | `Et0Constants.penman_monteith.numerator_constant` (README identifier `penman_monteith.numerator_constant`) |
| `penman_monteith_kelvin_offset` | site | `et0/` | `Et0Constants.penman_monteith.kelvin_offset` (README identifier `penman_monteith.kelvin_offset`) |
| `penman_monteith_denominator_constant` | site | `et0/` | `Et0Constants.penman_monteith.denominator_constant` (README identifier `penman_monteith.denominator_constant`) |
| `initial_abstraction_ratio` | site | `runoff/` | `CurveNumberConstants.initial_abstraction_ratio` |
| `retention_numerator` | site | `runoff/` | `CurveNumberConstants.retention_numerator` |
| `retention_offset` | site | `runoff/` | `CurveNumberConstants.retention_offset` |
| `retention_unit_factor` | site | `runoff/` | `CurveNumberConstants.retention_unit_factor` |
| `initial_depletion` | site | `evaporation/` | `initial_depletion` of the surface layer (the depletion at the start of the first day; the step itself takes `depletion_start`) |
| `total_evaporable_water` | site | `evaporation/` | `total_evaporable_water` of `evaporation.step`, read directly, not computed from the layer (PROPOSED) |
| `readily_evaporable_water` | site | `evaporation/` | `readily_evaporable_water` of `evaporation.step` |
| `wetted_fraction` | site | `evaporation/` | `wetted_fraction` of `evaporation.step` |
| `margin_above_basal` | site | `evaporation/` | `margin_above_basal` of `evaporation.step` and of `upper_limit_of_crop_coefficient` |
| `upper_limit_base` | site | `evaporation/` | `UpperLimitClimateConstants.base` (README identifier `upper_limit.base`) |
| `upper_limit_wind_coefficient` | site | `evaporation/` | `UpperLimitClimateConstants.wind_coefficient` (README identifier `upper_limit.wind_coefficient`) |
| `upper_limit_reference_wind_speed` | site | `evaporation/` | `UpperLimitClimateConstants.reference_wind_speed` (README identifier `upper_limit.reference_wind_speed`) |
| `upper_limit_humidity_coefficient` | site | `evaporation/` | `UpperLimitClimateConstants.humidity_coefficient` (README identifier `upper_limit.humidity_coefficient`) |
| `upper_limit_reference_minimum_relative_humidity` | site | `evaporation/` | `UpperLimitClimateConstants.reference_minimum_relative_humidity` (README identifier `upper_limit.reference_minimum_relative_humidity`) |
| `upper_limit_reference_crop_height` | site | `evaporation/` | `UpperLimitClimateConstants.reference_crop_height` (README identifier `upper_limit.reference_crop_height`) |
| `upper_limit_height_exponent` | site | `evaporation/` | `UpperLimitClimateConstants.height_exponent` (README identifier `upper_limit.height_exponent`) |
| `minimum_crop_coefficient` | site | `evaporation/` | `minimum_crop_coefficient` of `cover_fraction_from_basal_coefficient` |
| `minimum_relative_humidity` | site | `evaporation/` | `minimum_relative_humidity` of `climate_adjusted_upper_limit`: no daily series carries it (OPEN 3); new identifier, PROPOSED |
| `column_capacity` | site | `balance/` | `capacity` of `balance.step`: the soil's available water of D49, read if a record exists; new identifier, PROPOSED |
| `column_depth` | site | `balance/` | `column_depth` of `balance.step` |
| `initial_storage` | site | `balance/` | the storage at the start of the first day (`initial_storage` of `run_balance`) |
| `basal_crop_coefficient` | crop or no crop | `evaporation/`, `balance/` | `basal_crop_coefficient` of the surface layer and `CropDay.transpiration_coefficient` of the balance (the `Kcb` of D44) |
| `crop_height` | crop or no crop | `evaporation/` | `crop_height` of `climate_adjusted_upper_limit`; new identifier, PROPOSED |
| `cover_fraction_exponent` | crop or no crop | `evaporation/` | `exponent` of `cover_fraction_from_basal_coefficient` (README identifier `cover_fraction_exponent`) |
| `curve_number` | crop or no crop | `runoff/` | `RunoffDayInput.curve_number`; new identifier, PROPOSED (OPEN 3 of the runoff README) |
| `root_depth` | crop | `balance/` | `CropDay.root_depth` |
| `readily_available_fraction` | crop | `balance/` | `CropDay.readily_available_fraction` |

## PROPOSED choices

Where EP3, the brief, the conventions and the decisions do not settle something, the option that invents least. Each is a proposal; the question is under [OPEN](#open).

1. **Time basis.** Yearly items are on `ag_year` (D47); the two cases where the years cannot be laid out give one item on `rotation`, as in #134. OPEN 1, OPEN 2.
2. **Precedence**: infeasible calendar, time zones, coverage, units, then the chain. OPEN 12.
3. **Scope words and exact lookup**, as above. OPEN 6.
4. **New identifiers**: `minimum_relative_humidity`, `column_capacity`, `column_depth`, `initial_storage`, `crop_height`, `curve_number`, `basal_crop_coefficient`, `root_depth`, `readily_available_fraction`. Where a part has an argument of that name, the name is kept; `capacity` is written `column_capacity` so that it is not ambiguous in a catalogue shared with other engines. OPEN 6.
5. **Crop of a day from the calendar**, as in step 2 of the chain. Days outside the dates of the calendar have no known crop, because how the rotation is repeated over the years of the record is not decided (Q5). OPEN 5.
6. **Crop parameters are constant over a component.** The calendar carries no growth stage (its periods belong to the soil-loss method), and no part builds the curve of `Kcb` by stage or the growth of the root zone. So `basal_crop_coefficient`, `crop_height`, `cover_fraction_exponent`, `curve_number`, `root_depth` and `readily_available_fraction` are one value per crop. OPEN 4.
7. **The minimum relative humidity is a parameter of the site.** The climate term of the upper limit needs it every day, and no daily series carries it: humidity travels as dew point (D25). OPEN 3.
8. **`total_evaporable_water` is read directly**, not computed from the water contents and the depth of the surface layer (`total_evaporable_water` of `evaporation/`), because no soil property reaches the engine with an agreed identifier. OPEN 13.
9. **The cover fraction is computed from `Kcb`** (`cover_fraction_from_basal_coefficient`), not observed: no observed cover fraction reaches the engine. OPEN 4.
10. **`Ke` reaches the balance as the surface layer gives it**, also on a day the surface layer runs short (OPEN 2 of `evaporation/README.md`). OPEN 11.
11. **Units are checked before the chain runs.** A series or a value of the point in another unit string makes every covered year `MISSING_INPUT`, naming it and Q11; nothing is converted. Because of that check, the unit-guard code passed to `et0/` and `runoff/` (`MISSING_INPUT`) is never emitted. The unit strings of the parameter records are not checked. OPEN 8, OPEN 9.
12. **A value a part refuses is `NOT_COMPUTABLE`.** The parts raise `ValueError` for a number outside what they accept (a negative depth, a root depth below the column, a readily evaporable water above the total). That number comes from the catalogue or the climate record, not from a defect of the caller of EP3, so G5 does not let EP3 raise: the day is missing with `NOT_COMPUTABLE` (G4, "the method does not cover the case"), naming the part and its message, and later days start from a missing state. OPEN 10.
13. **The days of the chain** run from the first day every series it reads covers, to the last day of the `precipitation` series; `initial_storage` and `initial_depletion` are the states at the start of that day. A year before that day is `NO_COVERAGE` anyway, since a series does not cover its first day. OPEN 14.
14. **A record `read_value` refuses**, or two records with one `id` and `scope`, give `MISSING_INPUT` naming the parameter and why: the value the computation needs is not available to it (G4, second row). The runner passes only a catalogue that `check_catalogue` passed (G3), so this happens only if it does not. A record anywhere in `parameters` without a well-formed `id` and `scope` cannot be compared, so it could be a record of any parameter: it is reported, not skipped (F3c of `params/README.md`), and **every** parameter is `MISSING_INPUT`, naming it and the key of each such record, as EP1 does in `engine/erosion/_parameters.py` (#158).
15. **What a year needs.** A year is computed when the storage at the end of every one of its balance days is a number. A day with no crop counts like any other day; whether it counts for the indicator is C1.4 (OPEN).

## Numbers in the module

`exposure.py` and `_parameters.py` hold one integer, `1`: days and months are counted from one (C5.1), the year before the start month, one day earlier, one year later, the last year of an inclusive range, and the one component or record a lookup expects. A test reads both modules and fails on any other number and on any format specification in an f-string. Every number of the test file is a PLACEHOLDER chosen only so that every part accepts it and the chain gives a number every day. They are written with repeated digits (`2.22`, `0.555`), or as zero or one where a PROPOSED form needs the identity element; each zero is explained by a comment where it is written (for example, an albedo and a Stefan-Boltzmann constant of zero keep the net radiation above the soil heat flux, so the reference evapotranspiration stays above zero). None is a value of the method.

## PROPOSED cases

The identifier is the name of the test function in `test_exposure.py` without `test_`, with hyphens. A test checks that this list and the test functions agree. Every catalogue of a test is built in the record format of `params/README.md`, every record carrying the word PLACEHOLDER; the case passes the in-memory copy in which the word is replaced by `UNMARKED_TEST_ONLY`, which passes `check_catalogue`, as `params/test_layout.py` does (question 12 of `params/README.md`).

| Case | What it checks |
|---|---|
| `placeholder-catalogue-passes-check-catalogue-and-every-year-is-computed` | The test catalogue passes `check_catalogue` (and the marked copy does not); with it, three agricultural years are each computed on every day and missing with `NOT_AVAILABLE`, naming C1.4 and D61 |
| `the-chain-gives-a-number-every-day-from-each-part` | Every day of the record is a day of the chain, in order; each part gives a number every day; the runoff and `Ke` pass unchanged to the next part; the storage and the depletion are carried from day to day, never reset |
| `daily-balance-closes-its-mass-every-day` | `ΔS = P − Q − E − T − D` every day to floating-point precision, no flow below zero, the storage between zero and the capacity; the series has days with drainage, runoff, a crop and no crop |
| `crop-of-each-day-follows-the-calendar` | On a day a component covers, the balance takes that crop's `Kcb`; on a day none covers, there is no transpiration and the crop quantities are `NOT_APPLICABLE` |
| `empty-catalogue-makes-every-year-missing-input-naming-each-parameter-by-id-and-scope` | With `{}`: every agricultural year is `MISSING_INPUT`; its detail names every parameter of the site in scope `{}`, every parameter of a day with no crop in its scope, and the parameters of each crop that has appeared by the end of the year in that crop's scope, and no crop that has not; the list covers every year |
| `parameter-with-no-record-is-missing-input-naming-it-and-no-other` | For each parameter and each scope it is read with, removed alone: the years from the one that first needs it are `MISSING_INPUT` naming exactly that `id` and scope; the years before are computed |
| `record-with-null-value-is-missing-input-repeating-its-reason` | A record with `"value": null` and its reason (of the site, of a crop): `MISSING_INPUT`, naming the parameter and repeating the reason |
| `malformed-record-makes-every-parameter-missing-input-naming-it` | A record without an `id`, or without a `scope`: `check_catalogue` rejects the catalogue; every year is `MISSING_INPUT`, naming the record by its key and every parameter of the site as one that cannot be looked up, and no parameter as having no record |
| `record-that-read-value-refuses-is-missing-input-naming-why` | A record that carries the word PLACEHOLDER, a record whose two persons are the same, and two records with one `id` and scope: `MISSING_INPUT`, naming the parameter and why it is not read |
| `parameter-outside-what-a-part-accepts-is-not-computable-and-raises-nothing` | A root depth below the column: no exception; the year is `NOT_COMPUTABLE`, naming the balance and its message |
| `examples-as-they-are-load-and-every-item-is-missing` | The three examples of `contracts/inputs/examples/`, unchanged, with `{}`: the result loads, lists the agricultural years of the example `precipitation` series, and every item is missing with a code of C3.2 |
| `several-agricultural-years-load-into-results-per-rotation` | One item per year of D47, in order; the list loads as the `water_deficit_exposure` part of the example `ResultsPerRotation` |
| `infeasible-calendar-makes-every-item-not-computable` | With the test catalogue and with `{}`: every item `NOT_COMPUTABLE` (G4, first row), also for a year the series does not cover |
| `year-not-covered-by-a-series-is-no-coverage` | A record that starts and ends inside agricultural years: those years are `NO_COVERAGE` (C5.5) and the year between is computed. Each input of ET0 shorter than the record makes its last year `NO_COVERAGE`, naming it and not `precipitation` |
| `series-one-day-short-at-each-end-leaves-first-and-last-not-covered` | Series one day short at each end: first and last years `NO_COVERAGE`, the year between computed; the exact span computes every year |
| `absent-daily-series-is-missing-input-naming-it` | Each input of ET0 removed in turn: every year `MISSING_INPUT`, its first item names that series and no other |
| `days-held-missing-are-missing-input-naming-the-series` | One day held missing in every series: the year before is computed; the year of the day names each series, the year and the day; the year after is missing too and names the first cause (no gap is filled, the balance does not restart) |
| `missing-point-value-is-named-in-an-input-item` | `latitude`, `elevation` or both missing in the point: every year `MISSING_INPUT`, each named in an `input` item with its own code and detail; a missing `longitude` changes nothing |
| `series-in-different-time-zones-make-every-item-not-computable` | Series in two time zones: every item `NOT_COMPUTABLE` (C6.3) |
| `input-in-a-unit-not-accepted-is-missing-input-naming-it-and-q11` | Each series in another unit string, and the point in unit strings other than those of D55: every year `MISSING_INPUT`, naming it and Q11 |
| `start-month-missing-returns-one-item-for-the-rotation` | A missing start month: one item on the time basis `rotation`, `MISSING_INPUT`, naming the start month |
| `no-precipitation-series-returns-one-item-for-the-rotation` | No `precipitation` series: one item on the time basis `rotation`, `MISSING_INPUT`, naming `precipitation` |
| `calendar-dates-outside-the-record-keep-the-years-and-leave-the-crop-unknown` | A calendar moved past the last day of the record lists the same years (D47); every year is `MISSING_INPUT`, naming Q5 |
| `the-list-is-never-empty-and-no-item-is-a-number` | Over one result of each situation above: the list is never empty; no item is a number or zero; every item has a code of C3.2, no provenance and no range; one time basis per list; no agricultural year twice |
| `arguments-of-another-case-or-field-raise-value-error` | `case_id` or `field_id` of `climate` or `soil_slope` differs from the calendar: `ValueError` naming the field (G5) |
| `argument-that-is-not-its-model-raises-type-error` | A model argument given as a dictionary, or as an instance of another model: `TypeError` naming the argument (G5) |
| `parameters-missing-positional-or-not-a-dict-raises-type-error` | `parameters` left out, passed by position, or not a `dict[str, dict]` (a list, a tuple, JSON text, `None`, keys that are not text, values that are not records): `TypeError` (G3, G5) |
| `arguments-unchanged-and-second-call-equal` | With the test catalogue and with `{}`: the arguments equal a deep copy taken before the call, and a second call gives an equal result (G1) |
| `modules-import-only-allowed-modules-and-hold-only-the-integer-one` | `exposure.py` imports only the standard library, `contracts.inputs.*`, `contracts.results.models` and the four parts; `_parameters.py` only the standard library, `contracts.results.models` and the readers of `params.catalogue`; neither calls `load_folder`; neither holds a number but `1` or a format specification in an f-string |
| `package-exposes-the-entry-point-with-parameters-by-keyword-and-no-default` | `from engine.water import compute_water_deficit_exposure` works; its parameters are exactly `calendar`, `climate`, `soil_slope`, `parameters`, none with a default, `parameters` keyword-only |
| `parameter-identifiers-are-well-formed-and-unique` | Every identifier is a well-formed record `id` and appears once; those taken from the README tables of `et0/`, `runoff/` and `evaporation/` are in those tables |
| `parameter-table-matches-exposure-md` | The table [Parameters](#parameters) lists exactly the parameters the module reads, each with its scope |
| `runner-discovers-the-entry-point` | `discover_engine_functions()` of `api/engines.py` finds this function |
| `route-answers-with-a-water-part-when-the-runner-passes-parameters` | In process, no network: `POST /api/rotations/run` with the examples, EP2 replaced by the example calendar, EP1 not built, EP3 unwrapped and `EntryPointEngines(parameters={})`: `200`, the result loads into `ResultsPerRotation`, its water part is what EP3 returns, and the water module is `not_available` with the reason of its first item |
| `route-through-the-real-runner-passes-parameters-and-the-water-part-loads` | In process, no network, nothing wrapped or replaced: every engine `discover_engine_functions` finds, run by `EntryPointEngines(parameters=<the test catalogue>)`, with the example climate served under the identifiers of the request: `200`, the result loads into `ResultsPerRotation`, and its water part is what EP3 returns for the calendar of EP2 and that catalogue |
| `proposed-cases-match-exposure-md` | This list and the test functions agree |

## The runner and the tests outside this unit

The runner change of the platform developer (#160) is merged: `EntryPointEngines` in `api/engines.py` passes the loaded catalogue to EP1 and EP3 as `parameters=` when their signature takes it, and the app loads and checks the catalogue at start-up. So a request that reaches this EP3 through the route receives `parameters`, and `parameters` keeps no default, as the brief requires. The case `route-through-the-real-runner-passes-parameters-and-the-water-part-loads` runs that path with every discovered engine.

No test outside `engine/water/` fails on this branch: `py -3.12 -m pytest --ignore=ci` (Docker is absent on this machine, so `ci/` is left out).

## OPEN

Each item is a question a person has to answer, with the role that answers it. None is answered by this unit.

1. **Time basis of the indicator (C1.3).** Yearly items are on `ag_year` because D47 and the brief ask for every agricultural year. *Science reviewers.*
2. **What EP3 returns when the years cannot be laid out.** One item on the basis `rotation`. After D7 and #129 the missing start month should no longer reach an engine; whether the `precipitation` case keeps this form. *Lead developer; platform developer for the response.*
3. **The minimum relative humidity.** The climate term of the upper limit of `evaporation/` needs the minimum relative humidity of each day. No daily series carries it: humidity travels as dew point (D25, CQ4), and #15 found no daily minimum relative humidity at the source. It is read here as one parameter of the site (choice 7), which makes the climate term follow the wind speed of each day but not its humidity. The change the chain would need: either a daily quantity in `contracts/CLIMATE_QUANTITIES.md` with the adapter that fills it, or a route from the dew point and the maximum temperature to the minimum relative humidity, as a function of `et0/` or `evaporation/` with its form checked by a person. *Science reviewers (the route); lead developer; platform developer (a quantity).*
4. **The crop of each day beyond its identifier.** One value per crop for `Kcb`, crop height, the cover-fraction exponent, the curve number, the root depth and the readily available fraction (choice 6). The method has a curve of `Kcb` by growth stage, a growing root zone and a crop height that changes; the calendar carries no growth stage and no part builds those curves. The change the chain would need: growth stages in the calendar (or in the rotation definition) and a part that builds the daily `Kcb`, root depth and height from them. Also whether the cover fraction is observed instead (OPEN 5 of `evaporation/README.md`). *Science reviewers; lead developer (lane L1 plan).*
5. **How the rotation is repeated over the years of the record (Q5, still open).** A day outside the dates of the calendar has no known crop, so with a real calendar (whose dates lie after the record, D47) every year is `MISSING_INPUT` naming Q5. Once a person decides how the rotation is laid onto the years of the record, `_crop_of_day` in `exposure.py` changes and nothing else. *Lead developer; science reviewers.*
6. **Scope words and identifiers.** The words `crop` (with the `crop_id` of the calendar, whose vocabulary is OPEN), `management` and `no_crop`; whether a curve number also needs the soil group (the scope key `soil`) or the condition of the cover (OPEN 3 of `runoff/README.md`); and which record is read when one has the empty scope and another names a crop (question 5 of `params/README.md`). The new identifiers of choice 4. *Lead developer.*
7. **The soil's available water (D49) and the column.** `column_capacity` is the capacity of the column of `balance/`, read if a record exists, missing otherwise; D49 names the table by soil group of the national soil map, whose licence decides whether a record may be committed. Which soil property gives it, and the column depth, is OPEN 11 of `balance/README.md`. `soil_slope` is not read. *Lead developer; science reviewers.*
8. **Reason code of an input in a unit string not accepted (Q11).** `MISSING_INPUT` is PROPOSED here, as the merged form of #134 named the absence of that code a missing input. *Lead developer.*
9. **Unit strings of the parameter records.** A record carries a `unit`; the entry point does not check it, because the parts hold no unit string and checking would mean choosing one. A capacity in another depth unit than the precipitation (`mm day-1`) would be read silently. Which unit string each parameter must arrive in, and whether the entry point checks it. *Lead developer; science reviewers.*
10. **A value a part refuses (choice 12).** `NOT_COMPUTABLE` for that day, and the balance does not restart after it (as after a gap, C3.4). Whether a refused value should rather be caught when the catalogue is checked, and whether a negative reference evapotranspiration (possible with real constants on some days) is refused by the balance or allowed. *Lead developer; science reviewers.*
11. **Which `Ke` reaches the balance on a day the surface layer runs short** (OPEN 2 of `evaporation/README.md`). Passed as it is (choice 10). *Lead developer; science reviewers.*
12. **Precedence of the reasons** (choice 2). *Lead developer.*
13. **Total evaporable water read directly** (choice 8), or computed from the water contents of the surface layer once soil properties have agreed identifiers (OPEN 8 of `evaporation/README.md`). *Lead developer; science reviewers; platform developer.*
14. **Where the chain starts and which series marks the record** (Q5, still open). The years are those of the `precipitation` series, as in EP1; the chain starts on the first day every series it reads covers (choice 13), and `initial_storage` and `initial_depletion` are the states of that day. Which initial states to compare (OPEN 5 of `balance/README.md`, OPEN 9 of `evaporation/README.md`) and whether a spin-up is wanted. *Lead developer; science reviewers.*
15. **The fallback of D44.** When the dual-coefficient or surface-layer values do not arrive, D44 says the engine falls back to the single crop coefficient and one layer, and says so. The mapping is not decided (OPEN 7 of `balance/README.md`, OPEN 12 of `evaporation/README.md`), so here a missing parameter of the surface layer leaves the years missing, naming it. *Lead developer; science reviewers.*
16. **The three descriptive measures of C1.4 and the fourth of D50.** The chain computes the daily balance they would be read from, but `WaterDeficitExposure` and `ResultsPerRotation` have no field for them (Q10 b). *Lead developer; interface developer.*
17. **Changes of the parts that would simplify the chain, none needed now.** `run_balance` takes `capacity` and `column_depth` only as numbers, so the entry point writes the missing balance days itself when either has no record; `run_balance` and `run_surface_layer` raise for one refused day and lose the whole record, so the entry point calls the daily `step` and carries the state itself; `reference_evapotranspiration_from_climate` and `runoff_day` need a unit-guard code even when every unit is accepted. *Lead developer.*
18. **Example data (Q16).** The inputs carry `example_data`; `WaterDeficitExposure` has no field for it. *Lead developer; platform developer.*
19. **Day boundaries.** Years are cut on the dates of the series, in its time zone (C6.1; UTC for the NASA POWER adapter), not on the local day at the field (C6.5). *Science reviewers.*
20. **Who reads `detail`.** The format is for developers. With an empty catalogue a detail names some seventy parameters; if the interface shows it, its wording belongs to the strings file of `web/` and to people. *Interface developer; lead developer.*
