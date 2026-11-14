# `engine/water/et0/`: daily reference evapotranspiration

The daily grass reference evapotranspiration by the FAO-56 Penman-Monteith method (decision D44 of issue #77), from the daily climate quantities of decisions D25 to D27 and D35 and the point of the series (D9, D18). Unit `l1/water-et0`, issue #113. It is an internal part of the water engine: the route calls only the entry point EP3 of `contracts/ENTRYPOINTS.md` (`engine.water.compute_water_deficit_exposure`), which is not built by this unit.

Status: **PROPOSED** (blueprint section 3.7). Nothing here is in force until people approve the pull request: the lead developer, who owns lane L1, and a science reviewer, because the forms of the equations are science class.

## What a reader must know first

- **This folder holds no constant of the method.** Every coefficient of every equation is an argument the caller supplies, grouped by equation in `constants.py`. No field has a default. The tests use numbers that are plainly not constants of the method, marked PLACEHOLDER. The values are transcribed by a person from the method's text and checked by a second person (D34), into the table [Constants a person has to transcribe](#constants-a-person-has-to-transcribe).
- **The forms of the equations are PROPOSED.** A builder session wrote each form in the docstring of its function in `equations.py`, without the method's text in front of it (the equations of FAO-56 are images; issue #13 reproduces none). A person checks every form against its equation before any number of this folder is used (OPEN 2).
- **Equation numbers** are those issue #13 reports (section 4). Where #13 gives none, the number is `OPEN`.
- The only mathematical constant the code uses is pi (`math.pi`, `math.tau` which is twice pi, `math.radians`). Means are taken with `statistics.fmean`; squares and fourth powers are written as products. The code holds no numeric literal, and a test checks it (`R1`).
- The citation of the method is `CITATION NEEDED`: a person composes it, with its row in `ATTRIBUTIONS.md` (OPEN 17).

## Files

| File | What it holds |
|---|---|
| `constants.py` | One frozen class per equation with its constants, and `Et0Constants` that groups them. No value, no default |
| `equations.py` | One function per intermediate quantity, each with its PROPOSED form and its rules for missing and non-finite operands |
| `quantities.py` | The identifiers and unit strings of the five climate inputs (transcribed from `contracts/CLIMATE_QUANTITIES.md`), `InputValue`, `PointUnits` and the unit guard `read_input` |
| `daily.py` | `reference_evapotranspiration_day` (all the steps of one day) and `reference_evapotranspiration_from_climate` (every day of a `SiteClimate`) |
| `test_equations.py`, `test_daily.py`, `test_rules.py` | The PROPOSED cases below |
| `test_h2.py` | [H2], written and skipped until its values exist |

`engine/water/__init__.py` is created by this unit as an empty file, only so that the package imports. The entry point EP3 that will live there is another unit.

## The functions

Each function returns a number, or the `Missing` of `contracts/results/models.py` with its reason (C3.1). No new missing shape is defined.

| Function | Quantity | FAO-56, as #13 reports it | Constants it takes |
|---|---|---|---|
| `atmospheric_pressure` | Atmospheric pressure from elevation (derived, D30) | Eq. 7 | `atmospheric_pressure.*` |
| `psychrometric_constant` | Psychrometric constant | Eq. 8 | `psychrometric.*` |
| `mean_temperature` | Mean air temperature of the day, from maximum and minimum (derived, D30) | No equation cited by Example 18; Eq. 9 sits under "Air temperature" | none |
| `saturation_vapour_pressure` | Saturation vapour pressure at a temperature | Eq. 11 | `saturation_vapour_pressure.*` |
| `mean_saturation_vapour_pressure` | Mean saturation vapour pressure of the day | Eq. 11 twice, then the mean (Eq. 12, named by Box 7) | `saturation_vapour_pressure.*` |
| `slope_of_saturation_vapour_pressure_curve` | Slope of the saturation vapour pressure curve | Eq. 13 | `saturation_vapour_pressure.*`, `slope.*` |
| `actual_vapour_pressure_from_dew_point` | Actual vapour pressure from dew point (D25) | `OPEN` (OPEN 1) | `saturation_vapour_pressure.*` |
| `vapour_pressure_deficit` | Vapour pressure deficit | Block of Example 18; Box 7 | none |
| `day_of_year` | Number of the day in its year, from the date | Example 18 reads it from Table 2.5 | none |
| `latitude_in_radians` | Latitude in radians, from decimal degrees | Eq. 22 | none |
| `inverse_relative_distance` | Inverse relative distance Earth-Sun | Eq. 23 | `inverse_relative_distance.*` |
| `solar_declination` | Solar declination | Eq. 24 | `solar_declination.*` |
| `sunset_hour_angle` | Sunset hour angle | Eq. 25 or 26 | none |
| `extraterrestrial_radiation` | Extraterrestrial radiation for daily periods | Eq. 21 | `extraterrestrial_radiation.*` |
| `clear_sky_solar_radiation` | Clear-sky solar radiation, case "When calibrated values for as and bs are not available" | Eq. 37 | `clear_sky_radiation.*` |
| `net_shortwave_radiation` | Net shortwave radiation | Eq. 38 | `net_shortwave.*` |
| `net_longwave_radiation` | Net longwave radiation | Eq. 39 | `net_longwave.*` |
| `net_radiation` | Net radiation | Eq. 40 | none |
| `soil_heat_flux_daily` | Soil heat flux of a daily period: the constant the caller supplies | Eq. 42, case "For day and ten-day periods" | `soil_heat_flux.*` |
| `reference_evapotranspiration` | Grass reference evapotranspiration | Eq. 6 | `penman_monteith.*` |

Not in this folder, because the decisions replace them: the wind conversion of Eq. 47 (wind arrives at 2 m, D26), the solar radiation from sunshine of Eq. 34 and Eq. 35 (solar radiation arrives as all-sky solar radiation, D27), and the actual vapour pressure from relative humidity of Eq. 17 (humidity arrives as dew point, D25).

Rules of every function (rule G4 of `contracts/ENTRYPOINTS.md`, section 3 of `contracts/CONVENTIONS.md`):

- A missing input or constant gives a missing result, reason `MISSING_INPUT`, whose `detail` names every missing operand, as `input '<name>'` or `constant '<identifier>'`, with its own reason. Never zero, never a default (C3.3).
- An operand that is not a finite number is not computed: reason `NOT_COMPUTABLE`, naming it. A missing operand is reported before a non-finite one.
- Arithmetic with no finite real result (division by zero, the arc cosine or the square root outside its domain, a power that is not real, an overflow) gives reason `NOT_COMPUTABLE`. This is arithmetic, not a limit of the method (OPEN 10).
- An operand that is neither a number nor that `Missing` raises `TypeError`: a defect of the caller (G5).

### The inputs

| Input | Identifier and unit string | Where they come from |
|---|---|---|
| Maximum air temperature | `air_temperature_max_2m`, `degC` | `CQ2` of `contracts/CLIMATE_QUANTITIES.md` (D35) |
| Minimum air temperature | `air_temperature_min_2m`, `degC` | `CQ3` (D35) |
| Dew point temperature | `dew_point_temperature_2m`, `degC` | `CQ4` (D25) |
| Wind speed at 2 m | `wind_speed_2m`, `m s-1` | `CQ5` (D26); no height conversion |
| Solar radiation | `solar_radiation`, `MJ m-2 day-1` | `CQ6` (D27) |
| Latitude | `climate.point.latitude`; unit string supplied by the caller in `PointUnits.latitude_decimal_degrees` | The point of the series in `SiteClimate` (D9, D18, #101); its unit is not decided (OPEN 12) |
| Elevation | `climate.point.elevation`; unit string supplied by the caller in `PointUnits.elevation` | The point of the series in `SiteClimate` (D9, D18, #101); its unit is not decided (OPEN 12) |

A test reads the summary table of `contracts/CLIMATE_QUANTITIES.md` and checks that the five unit strings in `quantities.py` are the ones written there (`Q1`). A value in another unit string is never converted: it is missing with the reason code the caller supplies, because the code is not decided (Q11 of `contracts/ENTRYPOINTS.md`).

### One day, and every day of a record

- `reference_evapotranspiration_day` takes the inputs of one day as numbers or missing values, including the **actual vapour pressure**, and returns `Et0Steps`: every intermediate quantity and the result, each a number or missing. A missing input makes missing only the steps that depend on it. Taking the actual vapour pressure as an input lets a worked example given another form of humidity enter the same steps ([H2]).
- `reference_evapotranspiration_from_climate` reads the five daily series of a `SiteClimate`, computes the actual vapour pressure from dew point (PROPOSED route, OPEN 1), and returns one `DailyReferenceEvapotranspiration` per day, in date order. Latitude and elevation are read from `climate.point`, the point the series are valid for (D9, D18), through the same unit guard; a value of the point that is missing keeps its reason. Longitude is not read: no equation of the method uses it (OPEN 13). The order of the steps follows the order in which Example 18 cites the equations (#13, section 4). The slope of the curve is evaluated at the mean temperature (PROPOSED, OPEN 2).

## Constants a person has to transcribe

One row per constant. The identifier is `<field of Et0Constants>.<field of its class>`, the name the code and the `detail` of a missing result use. The unit of each constant is read in the method's text together with its value, so it is `OPEN` here. The value column stays empty: a person fills it, with the full reference, the locator, the verbatim text and the date read, and a second person checks it (D34). Until then the caller passes each constant as missing, and every quantity that needs it is missing with its name.

| Identifier | What it is | Unit | FAO-56 equation | Value |
|---|---|---|---|---|
| `atmospheric_pressure.sea_level_pressure` | Pressure at sea level, the factor in front of the bracket | OPEN | Eq. 7 | |
| `atmospheric_pressure.reference_temperature` | Reference temperature of the bracket, written twice in it | OPEN | Eq. 7 | |
| `atmospheric_pressure.lapse_rate` | Rate at which temperature falls with elevation, multiplying the elevation | OPEN | Eq. 7 | |
| `atmospheric_pressure.exponent` | Exponent of the bracket | OPEN | Eq. 7 | |
| `psychrometric.coefficient` | Factor that multiplies the pressure (OPEN 6: one number, or the quantities it combines) | OPEN | Eq. 8 | |
| `saturation_vapour_pressure.scale` | Factor in front of the exponential | OPEN | Eq. 11 | |
| `saturation_vapour_pressure.numerator` | Factor that multiplies the temperature in the numerator of the exponent | OPEN | Eq. 11 | |
| `saturation_vapour_pressure.offset` | Temperature added in the denominator of the exponent; also in Eq. 13 | OPEN | Eq. 11 | |
| `slope.multiplier` | Factor in front of the slope expression | OPEN | Eq. 13 | |
| `inverse_relative_distance.offset` | Term to which the cosine term is added | OPEN | Eq. 23 | |
| `inverse_relative_distance.amplitude` | Factor of the cosine | OPEN | Eq. 23 | |
| `inverse_relative_distance.days_in_year` | Number of days that divides the day of the year inside the cosine | OPEN | Eq. 23 | |
| `solar_declination.amplitude` | Factor of the sine | OPEN | Eq. 24 | |
| `solar_declination.days_in_year` | Number of days that divides the day of the year inside the sine | OPEN | Eq. 24 | |
| `solar_declination.phase` | Angle subtracted inside the sine | OPEN | Eq. 24 | |
| `extraterrestrial_radiation.time_factor` | Time factor of the day that is divided by pi, in front of the equation | OPEN | Eq. 21 | |
| `extraterrestrial_radiation.solar_constant` | Solar constant | OPEN | Eq. 21 | |
| `clear_sky_radiation.base` | Term to which the elevation term is added | OPEN | Eq. 37 | |
| `clear_sky_radiation.elevation_coefficient` | Factor that multiplies the elevation | OPEN | Eq. 37 | |
| `net_shortwave.albedo` | Albedo of the grass reference crop | OPEN | Eq. 38 | |
| `net_longwave.stefan_boltzmann` | Stefan-Boltzmann constant | OPEN | Eq. 39 | |
| `net_longwave.kelvin_offset` | Offset that turns the daily maximum and minimum temperatures into absolute temperatures (OPEN 8) | OPEN | Eq. 39 | |
| `net_longwave.humidity_intercept` | Term of the humidity correction from which the vapour pressure term is subtracted | OPEN | Eq. 39 | |
| `net_longwave.humidity_slope` | Factor of the square root of the actual vapour pressure | OPEN | Eq. 39 | |
| `net_longwave.cloudiness_multiplier` | Factor of the relative shortwave radiation | OPEN | Eq. 39 | |
| `net_longwave.cloudiness_offset` | Term subtracted in the cloudiness correction | OPEN | Eq. 39 | |
| `soil_heat_flux.daily_value` | Soil heat flux of a daily period (OPEN 9) | OPEN | Eq. 42 | |
| `penman_monteith.radiation_factor` | Factor of the radiation term | OPEN | Eq. 6 | |
| `penman_monteith.numerator_constant` | Constant of the numerator divided by the absolute mean temperature | OPEN | Eq. 6 | |
| `penman_monteith.kelvin_offset` | Offset that turns the mean temperature into an absolute temperature (OPEN 8) | OPEN | Eq. 6 | |
| `penman_monteith.denominator_constant` | Constant of the denominator that multiplies the wind speed | OPEN | Eq. 6 | |

## PROPOSED cases

The acceptance test is `python -m pytest engine/water/et0/`. Every number in the tests is a PLACEHOLDER; the cases test structure, not the method. Codes match the names of the test functions.

Intermediate quantities (`test_equations.py`):

- `EQ1` Each intermediate quantity is a separate function, and with PLACEHOLDER operands it gives the result computed by hand next to the case. Every public function of `equations.py` has a case.
- `EQ2` A missing input gives a missing result, reason `MISSING_INPUT`, that names it and carries its reason; every missing input is named, not only the first.
- `EQ3` A missing constant gives a missing result, reason `MISSING_INPUT`, that names it by its identifier of the table above; for every constant of every function.
- `EQ4` A non-finite input or constant (infinite, minus infinite, not a number) is not computed: reason `NOT_COMPUTABLE`, naming it. A missing operand is reported before a non-finite one.
- `EQ5` Arithmetic without a finite real result (a power that is not real, a division by zero, an arc cosine or a square root outside its domain, an overflow, a denominator of zero) is missing with `NOT_COMPUTABLE`, not an exception.
- `EQ6` An operand of the wrong type (a boolean, text, `None`, the `Missing` of the input contracts) or constants of another equation raise `TypeError`.
- `EQ7` The day of the year is the ordinal day of the date's calendar year, leap years included; only a date is accepted.
- `EQ8` An input given as such keeps its missing value unchanged; a number is checked.

One day and the climate record (`test_daily.py`):

- `D1` Each step of one day is its function applied to the steps before it, and with PLACEHOLDER inputs no step is missing.
- `D2` A missing input makes missing only the steps that depend on it (one case per input); a missing constant of Eq. 6 makes missing only the result; with every constant missing, only the steps without a constant stay; a non-finite input is not computed; constants of the wrong type raise.
- `Q1` The identifiers and unit strings of the five inputs are those of the summary table of `contracts/CLIMATE_QUANTITIES.md`, and the five are the quantities of D25 to D27 and D35.
- `Q2` An input is read through the unit guard: missing is `MISSING_INPUT` and named; another unit string is not converted and gives the caller's reason code, naming both unit strings; strings are compared exactly; missing is reported before the unit; non-finite is `NOT_COMPUTABLE`; defects of the caller raise.
- `C1` Every day of a climate record is the composition of that day's own inputs, in date order; other quantities of the record are ignored.
- `C2` A quantity with no series makes every day missing, naming the quantity.
- `C3` A series in another unit string is not converted: every day is missing, naming the quantity, the reason code of the guard and the unit string.
- `C4` A day held as missing in a series makes only that day missing, carrying the reason of the series, and only the steps that depend on it.
- `C5` Series in different time zones are not combined: the result of every day is missing, `NOT_COMPUTABLE` (C6.3, G4).
- `C6` Latitude and elevation are read from the point of the record, and its longitude is not read. A latitude or an elevation missing in the point makes the dependent steps missing, names it and carries its reason; one in another unit string is not converted.
- `C7` A day that one series does not cover is missing, naming the series; the days are every day any of the five series covers, in order.
- `C8` Without any of the five series there is no day: the list is empty.
- `C9` The arguments are not changed and the same arguments give the same result.
- `C10` A defect of the caller raises: an argument of the wrong type, a record that is not a `SiteClimate`, a reason code outside C3.2.

Rules of the brief (`test_rules.py`):

- `R1` No module of this folder holds a number.
- `R2` No constant and no argument of a public function has a default.
- `R3` The modules import nothing that reads the outside (no file, network or clock), and contract models are imported only as `contracts.<folder>.<module>`.
- `R4` No module defines its own missing shape.
- `R5` The table [Constants a person has to transcribe](#constants-a-person-has-to-transcribe) has exactly one row per constant of `constants.py`, and every value is empty.
- `R6` Every case code of the tests is listed here, and the OPEN list holds the dew-point route of D25.

The worked example (`test_h2.py`):

- `H2` [H2] of `docs/VALIDATION.md`, written and skipped. It waits for: the inputs, intermediate results, final value of FAO-56 Chapter 4 EXAMPLE 18, transcribed from the manual and checked by a person (D34); the tolerance and the printed precision, set by the science reviewers; the constants of the table above; and a person's check of the forms. It enters the example's own rows for the actual vapour pressure (Eq. 17), the solar radiation (Eq. 35) and the wind speed at 2 m (Eq. 47), and checks every step this engine computes (OPEN 4). A second case checks that the skip reason says what it waits for.

## OPEN

Each item is a question a person answers; the role is at the end. Decision rights are those of blueprint section 2.

1. **The route from dew point to the actual vapour pressure (D25).** PROPOSED form: the saturation vapour pressure of Eq. 11 evaluated at the dew point temperature. D25 says the route is "still to be supplied by a person", read in the method's text; issue #13 does not report it, so its equation number is `OPEN`. Until a person confirms it, the actual vapour pressure, the deficit, the net longwave radiation and the result rest on this PROPOSED form. Science reviewers.
2. **Every form of every equation.** The forms in `equations.py` and `constants.py` were written by a builder session, not read from the method's text. A person reads each equation image of FAO-56 (Chapters 2 and 3, as #13, section 4, lists them) and checks the form, which constant goes where, and which temperature the slope of Eq. 13 is evaluated at (PROPOSED: the mean). Science reviewers.
3. **The value and the unit of each constant** of the table above, transcribed with the record D34 asks for and checked by a second person. Science reviewers (check); a person or a session under D34 (transcription).
4. **What [H2] checks.** Example 18 is given relative humidity, hours of sunshine and wind at another height; this engine takes dew point, solar radiation and wind at 2 m (D25 to D27). The PROPOSED test enters the example's rows of Eq. 17, Eq. 35 and Eq. 47 as inputs and checks the shared steps. It does not check the dew-point route of OPEN 1. Is that an acceptable definition of [H2], and is another example needed for the dew-point route? Science reviewers, who define [H2] (`docs/VALIDATION.md`, H2, "Definition: OPEN").
5. **Tolerance and printed precision of [H2].** The result row prints two precisions (#13, section 3); several rows have oddities a transcriber meets (comma decimal, the es row, the n/N denominator, two Kelvin offsets, last-digit rounding). Which precision is the expected value, the tolerance of each step, and how each oddity is recorded. Science reviewers.
6. **The psychrometric constant: one coefficient, or the physical quantities it combines.** The engine takes one coefficient that multiplies the pressure. If the science reviewers prefer the quantities of the definition, the class gains fields. Science reviewers.
7. **The day of the year.** The engine takes the ordinal day of the calendar year from the date of the series; Example 18 reads it from Table 2.5 (Annex 2, not opened by #13). A person checks that the two agree, leap years included. Science reviewers.
8. **The two absolute-temperature offsets.** Eq. 6 and Eq. 39 print them differently (#13, section 3), so the engine takes two separate constants. Which value each takes. Science reviewers.
9. **The soil heat flux of a daily period.** The engine takes it as a constant the caller supplies (Eq. 42, case "For day and ten-day periods"). #13 reports that the "Daily time step" paragraph says it may be ignored for 24-hour steps. How that is recorded as a value. Science reviewers.
10. **Limits the method may state, which this engine does not apply.** No rule beyond the brief, the decisions, the conventions sheet and `contracts/ENTRYPOINTS.md` is added. Not applied, and for a person to read in the method's text: whether it bounds the ratio of solar radiation to clear-sky solar radiation in Eq. 39; what it says for days without a sunset or a sunrise, where the sunset hour angle has no real value (the engine answers `NOT_COMPUTABLE`); whether a minimum temperature above the maximum, a dew point above the mean temperature (a negative deficit), or a negative wind speed or radiation is rejected. Science reviewers.
11. **Pi as a mathematical constant.** The code uses pi through `math.pi`, `math.tau` and `math.radians` (the conversion of Eq. 22 from decimal degrees). It reads them as mathematics, not as coefficients of the method; a person confirms that reading. Science reviewers.
12. **The unit strings of latitude and elevation, and which elevation.** They are not decided (question 25 of `contracts/inputs/README.md`; O9 (b) of `contracts/CLIMATE_QUANTITIES.md`). The caller supplies them in `PointUnits`; the latitude must be the unit string that means decimal degrees, because Eq. 22 converts from decimal degrees. Science reviewers; lead developer for C1.1.
13. **The point of the series in `SiteClimate`.** Since #101 the record carries `point` (D9, D18), and `reference_evapotranspiration_from_climate` reads its latitude and elevation. D51 accepts a response that reports no point, or only part of one; the engine answers each missing value of the point by G4, with its reason. Open: whether the elevation of the point, which the source reports as the average of its grid cell, is the elevation Eq. 7 and Eq. 37 should use (question 28 of `contracts/inputs/README.md`; O9 (b) of `contracts/CLIMATE_QUANTITIES.md`). Science reviewers.
14. **The reason code of the unit guard** (Q11 of `contracts/ENTRYPOINTS.md`). The caller supplies it. Lead developer.
15. **Where the constants come from at run time.** D46 of issue #77 (the runner loads the parameter catalogue and passes it to each entry point) is not agreed yet, and reading the catalogue is out of the scope of this unit. The caller passes `Et0Constants`. How the catalogue becomes `Et0Constants` is the unit of EP3. Lead developer, with the platform developer's agreement on D46.
16. **A day that one series does not cover, and a record without any of the five series.** PROPOSED: the input of that day is missing, `MISSING_INPUT`, naming the series; with no series the list of days is empty. `NO_COVERAGE` (C5.5) is for the yearly values of an agricultural year, which this folder does not compute. Lead developer.
17. **Citation and attribution of FAO-56.** `CITATION NEEDED`. Issue #13 lists what the contents page prints and the copyright notice; composing the citation and the row of `ATTRIBUTIONS.md` is a person's job, and deciding which terms govern reuse. Lead developer; science reviewers for the citation.
18. **What the result carries.** No contract carries the reference evapotranspiration (Q10 (b) of `contracts/ENTRYPOINTS.md`); this folder returns numbers or missing values, with no unit string, provenance label or uncertainty range attached. When the water engine reports it, its unit string, its label (C4.3 says a value computed from `OBSERVED` series is `DERIVED`) and the reason it has no range are set there. `example_data` of the record is not carried either. Lead developer.

## Not covered by this folder

- The water balance (`engine/water/balance/`, another unit) and the entry point `compute_water_deficit_exposure`.
- Reading the parameter catalogue, any adapter, any file.
- Choosing a quantity, a unit, a source or a method.
- Gap filling of a daily series (C3.4): no gap is filled.
