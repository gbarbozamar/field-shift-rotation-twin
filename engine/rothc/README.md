# The RothC soil carbon model: core and entry point EP6

Unit `l2/rothc-common-forcings` (brief in issue #176). Status: `PROPOSED` (blueprint section 3.7): it takes effect only when a person approves the pull request.

Decision D1 of issue #77 makes RothC one of the two carbon models. This folder holds the model core, as pure functions, and the entry point EP6, `run_rothc(forcing, *, parameters) -> CarbonBalance` (`entry.py`), over the common forcing `CarbonForcing` (#155, D62, D65). `entry.py` is the only part of the folder that reads the parameter catalogue and builds contract models.

**Source.** Every form below is the person-transcribed model description of issue #176: "RothC – A model for the turnover of carbon in soil. Model Description" (February 2024), Rothamsted Research — transcribed by Martín on 14 November 2026 and checked by the lead developer on 15 November 2026 under D63 and D134 (issue #77); **the values are in force per D34**. The session that wrote this folder read no RothC source (the official Fortran/Python/R code is Apache-2.0 and is **not copied**; the implementation is written from the transcribed description) and wrote no value of the method in the code, a default, a comment or this file's signatures — the table [Constants a person has to transcribe](#constants-a-person-has-to-transcribe) carries the transcribed values for the person who fills `params/records/`.

## The forms

Every form is PROPOSED with its locator in the description; its source is the transcription named above.

| Function | Form | Locator |
|---|---|---|
| `temperature_modifier` | `a = 47.91 / (1 + exp(106.06 / (T + 18.27)))`, `T` the average monthly air temperature | p. 9 |
| `maximum_tsmd` | `max TSMD (0–23 cm) = -(20.0 + 1.3·clay - 0.01·clay²)`; another depth scales by `depth / 23` | pp. 10–12 |
| `advance_deficit` | one month: `deficit' = clamp(deficit - (0.75·pan - rain), max, 0)`; the deficit accumulates in the months with `0.75·pan > rain` and starts at field capacity (zero) on the first month | pp. 10–12 |
| `moisture_modifier` | `b = 1.0` if `deficit > 0.444·max`; else `b = 0.2 + (1.0 - 0.2)·(max - deficit) / (max - 0.444·max)` | p. 12 |
| `cover_modifier` | `c = 0.6` vegetated, `1.0` bare | p. 13 |
| `rate_modifying_factor` | `abc = a·b·c` | — |
| `clay_partition` | `x = 1.67·(1.85 + 1.60·exp(-0.0786·clay))`; `x/(x+1)` of what decomposes leaves as CO₂, `1/(x+1)` is formed as BIO + HUM | §1.7, p. 13 |
| `plant_fractions` | from the DPM:RPM ratio `r` of the material: `dpm = r/(1+r)`, `rpm = 1/(1+r)` | p. 8 |
| `step` | each active pool becomes `(pool + addition)·exp(-k·abc/12)`; the decomposed material splits by the clay rule; the formed BIO + HUM enters BIO at 46 %, HUM at its complement | pp. 8–9, 13 |
| `inert_organic_matter` | `IOM = 0.049·TOC^1.139`, both `t C ha-1` (Falloon et al. 1998, as printed there); only when no radiocarbon data | p. 16 |
| `initial_state` | the five pools of `starting_state`, the inert pool from the form above when the forcing names no measured one | p. 16 |
| `run` | `step` applied to each month in turn; the end of one month is the start of the next, never reset | §2.2 |
| `end_minus_start`, `fitted_slope`, `mean_over_cycles` | the three computations of C1.6, read as in `engine/amg/trend.py` (CITATION NEEDED, C1.6) | — |

The inert pool (IOM) takes no part in the turnover: nothing enters it and nothing leaves it. The mass balance of a month is `stocks out + CO2 = stocks in + inputs`, exactly.

Two readings of the description are PROPOSED here because the transcribed text does not decide them; both are OPEN items below:

- the carbon inputs of a month enter the pools **before** the decomposition of that month (the worked example prints a month without inputs, so it cannot decide it; the description's flow of carbon reads that way);
- the moisture modifier of a month follows the water balance **of that month** (the deficit is advanced, then `b` is read from it).

## Signatures

Every argument of a public function is passed by name and none has a default. A number argument is a number or a `Missing` of the contract models (either shape, `contracts.inputs.common.Missing` or `contracts.results.models.Missing`); a result that is not computed is always the `Missing` of `contracts/results/models.py`. No new `Missing` shape is defined.

```python
temperature_modifier(*, temperature, temperature_unit, maximum, exponent_scale,
                     exponent_scale_unit, offset, offset_unit) -> float | Missing
clay_partition(*, clay_content, clay_content_unit, scale, intercept,
               clay_coefficient, clay_decay, clay_decay_unit) -> float | Missing
maximum_tsmd(*, clay_content, clay_content_unit, depth, depth_unit, intercept,
             intercept_unit, clay_coefficient, clay_coefficient_unit,
             clay_squared_coefficient, clay_squared_coefficient_unit,
             reference_depth, reference_depth_unit) -> float | Missing
advance_deficit(*, deficit, maximum, maximum_unit, rainfall, rainfall_unit,
               pan_evaporation, pan_evaporation_unit, pan_factor) -> float | Missing
moisture_modifier(*, deficit, maximum, threshold_fraction, minimum) -> float | Missing
cover_modifier(*, cover_state, vegetated_factor, bare_factor) -> float | Missing
rate_modifying_factor(*, temperature_factor, moisture_factor,
                      cover_factor) -> float | Missing
plant_fractions(*, dpm_rpm_ratio) -> InputSplit | Missing
inert_organic_matter(*, total_organic_carbon, coefficient, exponent) -> float | Missing
input_additions(*, carbon_inputs, compositions) -> InputSplit | Missing
initial_state(*, dpm, rpm, bio, hum, iom) -> PoolState | Missing
step(*, state, additions, rate_modifying_factor, rate_constants,
     partition_ratio, bio_share) -> StepResult | Missing
run(*, initial_state, months, rate_constants, partition_ratio,
    bio_share) -> Run
end_minus_start(*, stocks, times) -> float | Missing
fitted_slope(*, stocks, times) -> float | Missing
mean_over_cycles(*, stocks, times, cycle_boundaries) -> float | Missing
trend_measures(*, stocks, times, cycle_boundaries) -> TrendMeasures
run_rothc(forcing, *, parameters) -> CarbonBalance   # entry.py, EP6
```

- `PoolState`: `dpm`, `rpm`, `bio`, `hum`, `iom` and the property `total` (the five).
- `InputSplit`: `dpm`, `rpm`, `bio`, `hum` — the shares of one unit of incoming material (summing to one) or the additions of one month.
- `MonthInput`: `additions` (an `InputSplit` or a `Missing`) and `rate_modifying_factor` (the `abc` of the month).
- `StepResult`: `start` and `end` (`PoolState`), `additions`, `co2`, `duration` (one over `MONTHS_PER_YEAR`, in years).
- `Run`: `initial_state` (as passed in), `steps` (one `StepResult` or `Missing` per month input), `duration_unit` (`"yr"`); `total_stocks()` and `elapsed_times()` as in `engine/amg/pools.py`.
- `rate_constants` is a mapping keyed `dpm`, `rpm`, `bio`, `hum`, each per year.
- `carbon_inputs` and `compositions` are mappings from the quantity of an input to its amount and its composition; the composition of an input that has none is named.
- `cycle_boundaries` are positions in the series of stocks, as in `engine/amg/trend.py`. `CarbonForcing` carries no rotation cycle, so EP6 passes none and `mean_over_cycles` is always missing.

The functions return bare numbers. Building a `SoilCarbonTrend` of the results contract is left to EP6.

## Units

Nothing is converted. Carbon amounts (pools, inputs, CO2, stocks) share `t C ha-1` (C1.5 without `per year`), the times are in years, and the unit strings of the forcing are compared as text with the unit strings of the records (C1.1):

| Quantity | Unit required |
|---|---|
| rainfall, open-pan evaporation, potential evapotranspiration (`climate`) | `mm` (the unit of `rothc_tsmd_intercept`; any other text is `NOT_COMPUTABLE`) |
| mean air temperature (`climate`) | the unit of `rothc_temperature_exponent_scale` and `rothc_temperature_offset` (the example records use `degC`) |
| clay content (`soil_properties`) | the clay unit inside the unit of `rothc_tsmd_clay_coefficient` (`mm %-1`), of `rothc_tsmd_clay_squared_coefficient` (`mm %-2`) and of `rothc_partition_clay_decay` (`%-1`) — the example records use `%` |
| soil depth (the `soil_depth` of the forcing) | the unit of `rothc_tsmd_reference_depth` (the example record uses `cm`) |
| soil cover (`soil_cover`) | `dimensionless` (C1.1) |
| starting pools, carbon inputs | `t C ha-1`; another unit is `NOT_COMPUTABLE`, nothing is converted |

The rate constants are per `yr` (records written `yr-1`): the monthly step divides them by the twelve months of a year.

## Constants a person has to transcribe

One row per constant. The values are **transcribed by Martín from the February 2024 Model Description on 14 November 2026 and checked by the lead developer on 15 November 2026 (D63 under D134); they are in force per D34**. `params/records/` holds no RothC record yet: a person writes them from this table and signs `transcribed_by`; the records the acceptance test builds are in-memory copies of these values. The identifiers are `PROPOSED`. Where a row says "per origin", one record per origin of a carbon input is needed, the origin written under the scope key `crop`.

| Constant | Proposed parameter identifier | Value (transcribed, in force) | Unit | Locator |
|---|---|---|---|---|
| DPM rate constant | `rothc_dpm_rate_constant` | 10.0 | `yr-1` | pp. 8–9 |
| RPM rate constant | `rothc_rpm_rate_constant` | 0.3 | `yr-1` | pp. 8–9 |
| BIO rate constant | `rothc_bio_rate_constant` | 0.66 | `yr-1` | pp. 8–9 |
| HUM rate constant | `rothc_hum_rate_constant` | 0.02 | `yr-1` | pp. 8–9 |
| Temperature modifier numerator | `rothc_temperature_modifier_maximum` | 47.91 | `dimensionless` | p. 9 |
| Temperature exponent scale | `rothc_temperature_exponent_scale` | 106.06 | a temperature (`degC` in the example records) | p. 9 |
| Temperature offset | `rothc_temperature_offset` | 18.27 | as above (`degC`) | p. 9 |
| TSMD intercept (no clay) | `rothc_tsmd_intercept` | 20.0 | `mm` | pp. 10–12 |
| TSMD clay coefficient | `rothc_tsmd_clay_coefficient` | 1.3 | `mm %-1` | pp. 10–12 |
| TSMD squared clay coefficient | `rothc_tsmd_clay_squared_coefficient` | 0.01 | `mm %-2` | pp. 10–12 |
| TSMD reference depth | `rothc_tsmd_reference_depth` | 23.0 | `cm` | pp. 10–12 |
| Moisture threshold fraction | `rothc_moisture_threshold_fraction` | 0.444 | `dimensionless` | p. 12 |
| Moisture minimum factor | `rothc_moisture_minimum_factor` | 0.2 | `dimensionless` | p. 12 (the form prints `(1.0 - 0.2)`) |
| Pan evaporation factor | `rothc_pan_evaporation_factor` | 0.75 | `dimensionless` | pp. 10–12 (row 11 of the issue: PET / 0.75 stands in for pan) |
| Cover factor, vegetated | `rothc_cover_factor_vegetated` | 0.6 | `dimensionless` | p. 13 |
| Cover factor, bare | `rothc_cover_factor_bare` | 1.0 | `dimensionless` | p. 13 |
| Partition scale | `rothc_partition_scale` | 1.67 | `dimensionless` | §1.7, p. 13 |
| Partition intercept | `rothc_partition_intercept` | 1.85 | `dimensionless` | §1.7, p. 13 |
| Partition clay coefficient | `rothc_partition_clay_coefficient` | 1.60 | `dimensionless` | §1.7, p. 13 |
| Partition clay decay | `rothc_partition_clay_decay` | 0.0786 | `%-1` | §1.7, p. 13 |
| BIO share of the formed | `rothc_bio_share_of_formed` | 0.46 (HUM takes the complement, printed 54 %) | `dimensionless` | p. 8 |
| IOM coefficient | `rothc_iom_coefficient` | 0.049 | `dimensionless` | p. 16 (Falloon et al. 1998, as printed) |
| IOM exponent | `rothc_iom_exponent` | 1.139 | `dimensionless` | p. 16 |
| Plant-input DPM:RPM ratio, per origin (plant materials) | `rothc_input_dpm_rpm_ratio` | crops and improved grassland 1.44 (printed shares 59 %/41 %); unimproved grassland and scrub incl. Savanna 0.67; deciduous/tropical woodland 0.25 (printed shares 20 %/80 %) | `dimensionless` | p. 8 |
| Organic-amendment shares, per origin (farmyard manure) | `rothc_input_dpm_fraction`, `rothc_input_rpm_fraction`, `rothc_input_hum_fraction` | FYM: 0.49, 0.49, 0.02 | `dimensionless` | p. 8 |

Not constants of the method, and so not in this table: the horizon, the soil depth and the soil cover (values of the forcing), the step length (one month) and the cycle boundaries. The alternative inert pool of p. 16 (age 50 000 years, Δ14C −998.0) needs radiocarbon data the forcing does not carry and is not built.

## When a result is not computed

In this order; the first that applies is returned. Nothing is clipped, filled, normalised or replaced by zero.

1. **`MISSING_INPUT`**: an argument is missing. The detail names every missing argument with its own reason code and detail (C3.3). For `input_additions`, an input without a composition is missing and named.
2. **`NOT_COMPUTABLE`**: an argument that is not a finite number; then a value outside what the quantity can be (a negative stock, input, rate constant, rate modifier, rainfall, pan evaporation or clay content; a depth that is not positive; a fraction outside zero to one; a partition ratio that is not positive; a maximum deficit that is not negative; a deficit outside the maximum deficit and field capacity; a cover state that is neither zero nor one); then unit strings that differ; then a form that gives no finite real number. An empty `carbon_inputs` of a month is `NOT_COMPUTABLE`: a month without input is written as an input at zero, never by omission (as `engine/amg` chooses; D122).
3. **A run**: once a month is missing, every later month is `MISSING_INPUT`, and its detail names the first missing month (counted from zero) with its reason. When the initial state is missing, every month is `MISSING_INPUT` naming it.
4. **A trend measure** needs only the points it uses: `end_minus_start` the first and the last, `fitted_slope` every point, `mean_over_cycles` the points at the cycle boundaries. One of those that is missing gives `MISSING_INPUT` naming it. `NOT_COMPUTABLE` for: fewer than two points; times at the points used that do not rise strictly; fewer than two cycle boundaries, a boundary outside the series or not after the one before; a value that is not finite.

A `TypeError` is raised for an argument of another type (`None`, text, a boolean, a list in place of a number; a state that is not a `PoolState`; a month that is not a `MonthInput`; `rate_constants` without exactly the four active pools). A `ValueError` is raised when `stocks` and `times` differ in length.

## PROPOSED cases

Each case is a test function of `test_rothc.py`; a test checks that this list and the file agree. Every number in the tests of that file is a PLACEHOLDER, plainly unreal with repeated digits; each computed number is compared with the forms written a second time in the test, or with the mass balance. The person-transcribed values of the reference case live only in `test_reference_case.py` (next section).

### Initial state, inputs and the split of the material

| Case | What it shows |
|---|---|
| `test_initial_state_takes_the_five_pools` | The state carries the five stocks as given; the total is their sum |
| `test_initial_state_refuses_negative_stocks_and_names_them` | A negative pool is `NOT_COMPUTABLE` naming it and no other |
| `test_initial_state_missing_pool_is_named_with_its_reason` | A missing pool (both `Missing` shapes) gives `MISSING_INPUT` naming it with its reason |
| `test_plant_fractions_follow_the_ratio` | The shares are `r/(1+r)` and `1/(1+r)`, summing to one with no part to BIO or HUM; the printed classes give the printed shares |
| `test_plant_fractions_refuse_a_negative_ratio` | A negative ratio is `NOT_COMPUTABLE`; a ratio of exactly minus one gives no finite result |
| `test_inert_organic_matter_follows_the_form` | `IOM` equals `coefficient·TOC^exponent` written a second time; TOC zero gives zero |
| `test_input_additions_split_each_input_by_its_composition` | Each input enters the pools of its shares, in proportion; the additions sum to the inputs |
| `test_input_additions_without_a_composition_or_with_a_missing_one_name_it` | An input without a composition, or with a `Missing` one, gives `MISSING_INPUT` naming it |
| `test_input_additions_refuse_negative_inputs_and_shares_that_do_not_sum_to_one` | A negative input is `NOT_COMPUTABLE`; shares that sum to anything but one are refused; a share below zero is refused |
| `test_input_additions_with_no_input_is_not_computed` | An empty mapping is `NOT_COMPUTABLE`, never zero: a month without input is an input at zero |

### One month

| Case | What it shows |
|---|---|
| `test_step_follows_the_form` | Each active pool becomes `(pool + addition)·exp(-k·abc/12)`, the decomposed material splits by the clay rule, the formed BIO + HUM splits by the bio share; the inert pool does not change; the arithmetic is written a second time in the test |
| `test_step_keeps_the_mass_balance` | `stocks out + CO2 = stocks in + inputs`, and no pool is negative, over varied PLACEHOLDER arguments |
| `test_step_with_no_additions_and_no_factor_decays_the_pools_only` | With nothing entering and `abc` at zero the pools do not change; with `abc` above zero the pools fall and CO2 leaves |
| `test_step_refuses_negative_values_and_a_share_outside_zero_to_one` | A negative pool, addition, factor, rate constant or partition ratio, or a bio share outside zero to one: `NOT_COMPUTABLE` naming it |
| `test_step_missing_argument_gives_missing_input_that_names_it` | A missing state, additions, factor or constant gives `MISSING_INPUT` naming it with its reason; both shapes |
| `test_step_rate_constants_hold_the_four_active_pools` | `rate_constants` without exactly the four active pools raises `TypeError` |

### A run over months

| Case | What it shows |
|---|---|
| `test_run_equals_steps_applied_one_after_another` | The run equals `step` applied in turn, each start the end of the month before |
| `test_run_mass_balance_holds_at_every_month_over_a_long_series` | Over three thousand months of varied PLACEHOLDER inputs and factors, each month keeps the mass balance and the pools stay not negative |
| `test_run_missing_month_makes_that_month_and_every_later_month_missing` | A missing input or factor at one month makes that month and every later one `MISSING_INPUT`, naming the month and the input; earlier months are kept; stocks after it are missing; both shapes |
| `test_run_missing_initial_state_makes_every_month_missing` | A missing initial state, also one `initial_state` refused, makes every month and every stock missing, naming it |
| `test_run_elapsed_times_and_total_stocks` | The elapsed times are one over twelve of a year per month from zero; the stocks are the initial total and the total at the end of each month |

### The rate modifying factors

| Case | What it shows |
|---|---|
| `test_temperature_modifier_follows_the_form` | `a` equals the form written a second time over a grid of temperatures, at the PLACEHOLDER constants |
| `test_clay_partition_follows_the_form` | `x` equals the form written a second time; the doc instance of the description (23.4 % clay) is not asserted here — its value is the reference case's |
| `test_maximum_tsmd_follows_the_form` | The maximum deficit equals the form written a second time, scaled by the depth over the reference depth |
| `test_maximum_tsmd_refuses_a_depth_of_zero_or_a_clay_that_makes_no_deficit` | A reference depth or depth of zero, or a clay content whose form makes no negative deficit: `NOT_COMPUTABLE` |
| `test_advance_deficit_accumulates_and_holds_at_the_limits` | The deficit grows by `0.75·pan - rain` and is held at the maximum deficit and at field capacity; the accumulation starts from field capacity |
| `test_moisture_modifier_follows_the_form` | `b` is one above the threshold and follows the form below it, written a second time; `b` reaches the minimum at the maximum deficit |
| `test_cover_modifier_takes_one_of_the_two_states` | Zero gives the bare factor, one the vegetated factor; any other state is `NOT_COMPUTABLE` |
| `test_rate_modifying_factor_is_the_product` | `abc` is the product of the three; a missing factor names itself; a negative factor is refused |
| `test_modifier_negative_or_missing_value_is_not_computed` | A negative rainfall, pan evaporation, clay content, depth or pan factor, a pan factor outside zero to one, a deficit outside its limits: `NOT_COMPUTABLE` or `MISSING_INPUT`, each named |
| `test_modifier_units_that_differ_are_not_computed` | Each unit string that must agree, changed alone: `NOT_COMPUTABLE` naming it |

### Trend measures of C1.6

| Case | What it shows |
|---|---|
| `test_end_minus_start_is_the_change_over_the_horizon_per_unit_time` | Worked by hand; a missing point between the ends does not stop it |
| `test_fitted_slope_recovers_the_slope_of_a_straight_line` | A straight line gives its own slope |
| `test_mean_over_cycles_is_the_mean_change_per_unit_time_of_the_whole_cycles` | Worked by hand for equal cycles; points after the last whole cycle are not used |
| `test_trend_measures_name_the_three_computations_of_c16` | The measures carry the three identifiers of `TREND_COMPUTATIONS` in order, the run's time unit, and the values of the three functions |
| `test_trend_of_a_series_with_a_missing_point_is_missing_with_its_reason` | A missing point stops only the measures that use it: `fitted_slope` names the point; `mean_over_cycles` names it when it sits at a boundary; `end_minus_start` needs only the ends |
| `test_trend_without_a_span_of_time_is_not_computed` | Fewer than two points, or times that do not rise strictly, are `NOT_COMPUTABLE`; series of different lengths raise `ValueError` |

### Arguments of every function

| Case | What it shows |
|---|---|
| `test_argument_that_is_not_finite_is_not_computed` | "Not a number", an infinity or an integer too large for a float, as any number argument of any function: `NOT_COMPUTABLE` naming it |
| `test_items_that_are_not_finite_are_not_computed` | The same for an item of a mapping, a pool of a state, a stock and a time |
| `test_missing_argument_gives_missing_input_that_names_it` | A missing number argument of any function gives `MISSING_INPUT` naming it with its reason; both shapes |
| `test_argument_of_another_type_raises_type_error` | `None`, text, a boolean or a list as a number argument raises `TypeError` naming it |
| `test_structured_argument_of_another_type_raises_type_error` | The same for a mapping, a state, the months, a unit string, a series, the cycle boundaries and the additions |
| `test_every_argument_is_passed_by_name_and_none_has_a_default` | Every public function takes keyword arguments only, without a default; no field of a result type has a default |
| `test_the_modules_hold_no_number_but_zero_and_one` | The modules of this folder write no number but zero and one |
| `test_entry_point_is_run_rothc_of_entry_module` | `engine.rothc.run_rothc` is the function of `entry.py`; the runner's `EntryPoint("EP6", "rothc", "engine.rothc", "run_rothc")` resolves to it |
| `test_readme_lists_the_cases_of_this_file` | This list and `test_rothc.py` name the same cases |

## The reference case of section 2.2 (D64, D104 as amended by D130)

`test_reference_case.py` holds the acceptance case the persons chose and transcribed (issue #176; the worked example of section 2.2 of the February 2024 Model Description, pp. 20–22): Hoosfield, January 1852, the month after a 10 000-year equilibrium run, no plant input in January, the combined rate modifying factor **abc = 0.3561 an exact input** (D104: the individual `a`, `b`, `c` are not compared against the document). The expected pools are compared at the person-set tolerance **5 × 10⁻⁵ absolute** (the case designer, 14 November 2026: half of the last printed digit). The parameters are the transcribed values of the table above, as in-memory records.

| Case | What it shows |
|---|---|
| `test_reference_case_becomes_its_parts` | The acceptance test holds no number of its own: the four exponents, the split and the expected pools are the transcribed constants and stocks arranged as the transcribed form |
| `test_reference_case_january_bio_and_hum_within_the_tolerance` | BIO 0.6651 and HUM 25.8551 at the end of January, within 5 × 10⁻⁵ of the engine's step given abc |
| `test_reference_case_january_dpm_and_rpm_within_the_tolerance` | The printed DPM 0.1140 and RPM 4.4455 differ from a faithful computation by 6.29 × 10⁻⁵ and 5.23 × 10⁻⁵ because the printed table displays `start − truncated difference`; the case designer set the pool tolerance to 1 × 10⁻⁴ on that basis (15 Nov 2026), so all four pools compare as plain asserts |
| `test_reference_case_mass_balance_of_the_month` | `stocks out + CO2 = stocks in` (no input) over the month, to floating-point precision |
| `test_reference_case_run_through_the_entry_point` | The same month through `run_rothc` over a forcing that carries the starting pools, with `abc` reached by a temperature, a water balance and a cover state chosen so that their product is the transcribed 0.3561: the end pools are those of the core step |
| `test_reference_case_records_pass_check_catalogue` | The in-memory records of the transcribed values are well-formed and no two share an identity |
| `test_readme_lists_the_cases_of_this_file` | This list and `test_reference_case.py` name the same cases |

## EP6 run_rothc

Status: `PROPOSED`. The entry point EP6 of `contracts/ENTRYPOINTS.md`, in `entry.py`, exported by `engine/rothc/__init__.py`:

```python
run_rothc(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance
```

- `forcing`: `contracts.carbon_forcing.CarbonForcing` (#155, D62, D65). The same object EP5 receives.
- `parameters`: the catalogue as `params.catalogue.load_folder` returns it, after `check_catalogue` reported no problem (G3, D46, D56).
- Returns `contracts.carbon_balance.CarbonBalance`, carbon model `rothc` (D1), variant `rothc_26_3` (D64 names the 1990 standard formulation; the vocabulary of `variant` is OPEN).
- Raises `TypeError` when `forcing` is not a `CarbonForcing`, or `parameters` is not a `dict` from text to `dict` (G5). Nothing else is raised for data.
- Pure (G1): reads records only with `params.catalogue.identity` and `params.catalogue.read_value`, changes no argument, reads no file, clock or environment.

### What it builds

1. **Months.** One step per calendar month of the horizon, each of length one over twelve of a `yr`.
2. **Initial state.** The five pools of `starting_state`, by their PROPOSED quantities (`rothc_dpm_pool`, …). The inert pool: the measured one when the forcing names it; otherwise the p. 16 form from `soil_organic_carbon` (the total); neither there: `MISSING_INPUT` naming both.
3. **Each month.** `abc` from the forcing: `a` from `mean_temperature`; `b` from the water balance of `rainfall` and the open-pan evaporation — or, when the forcing carries no pan series, the potential evapotranspiration divided by the pan factor (row 11 of the issue) — over the maximum deficit from `clay_content`, the forcing's `soil_depth` and the TSMD constants; `c` from the cover state. The additions of the month: every series of `carbon_inputs`, split by the composition of its `origin` (`plant_fractions` for a ratio record; the three shares for an amendment). Then the core's `step`.
4. **Trend.** `trend_measures` over the total stocks and elapsed times of the run. `mean_over_cycles` is always missing, `MISSING_INPUT`, naming the cycle boundaries (the forcing carries none).
5. **The balance.** `total_stock` (`soil_organic_carbon`), `pools` (`rothc_dpm_pool`, `rothc_rpm_pool`, `rothc_bio_pool`, `rothc_hum_pool`, `rothc_iom_pool`) and `flows` (`rothc_carbon_input`, `rothc_co2_carbon`), all in `t C ha-1`, one value per month; the three `SoilCarbonTrend` values in `t C ha-1 yr-1`, each naming the carbon model `rothc` (never merged with AMG, C1.5). The initial stocks carry `DECLARED` (taken from `starting_state`) or `DERIVED` (the inert pool from the form; the total as the sum of the pools); step values and trend values carry `SIMULATED` (C4.1). Each present value carries a source naming `engine.rothc.run_rothc`, the variant, the forcing quantities and the parameter records read, and `range_missing` with reason `NOT_AVAILABLE` (Q6). `horizon`, `soil_depth`, `example_data` and the three identifiers are copied from the forcing.

### What it reads from the forcing

The identifiers are PROPOSED (`entry.FORCING_QUANTITIES`), for the producer of `CarbonForcing` (the platform developer) and the science reviewers; the vocabulary of the forcing is OPEN.

| Input of the core | Part of `CarbonForcing` | Quantity (PROPOSED) | Unit required |
|---|---|---|---|
| `initial_state` | `starting_state` | `rothc_dpm_pool`, `rothc_rpm_pool`, `rothc_bio_pool`, `rothc_hum_pool`, `rothc_iom_pool` | `t C ha-1`; another unit is `NOT_COMPUTABLE` |
| `inert_organic_matter.total_organic_carbon` | `starting_state` | `soil_organic_carbon` (only when the inert pool is absent) | `t C ha-1` |
| `input_additions.carbon_inputs` | `carbon_inputs` | every series, by its own quantity; its `origin` chooses the composition records | `t C ha-1` over the month |
| `temperature_modifier.temperature` | `climate` | `mean_temperature` | the unit of the two temperature records |
| `advance_deficit.rainfall` | `climate` | `rainfall` | the unit of `rothc_tsmd_intercept` |
| `advance_deficit.pan_evaporation` | `climate` | `open_pan_evaporation`, or `potential_evapotranspiration` over the pan factor when no pan series is given | as the rainfall |
| `maximum_tsmd.clay_content` | `soil_properties` | `clay_content` | the clay unit of the three clay records |
| `maximum_tsmd.depth` | the `soil_depth` of the forcing | — | the unit of `rothc_tsmd_reference_depth` |
| `cover_modifier.cover_state` | `soil_cover` | `soil_cover_state`: `1.0` vegetated, `0.0` bare (encoding PROPOSED) | `dimensionless` (C1.1) |

Not read by EP6: `annual_climate` and `annual_carbon_inputs` (RothC steps by calendar month, C5.1, not by agricultural year). `horizon` lays out the months.

### What it returns in each case

| Case | What the balance holds |
|---|---|
| Every input and parameter present | Every stock, pool, flow and month computed by the core; `end_minus_start` and `fitted_slope` computed; `mean_over_cycles` missing, `MISSING_INPUT`, naming the cycle boundaries |
| The forcing example with an empty catalogue | Every value missing, `MISSING_INPUT`: the example carries none of the five pools, so every value names the quantities the forcing lacks; a parameter without a record is named the same way (next row) |
| A parameter with no record (with a complete forcing) | The values that need it missing, `MISSING_INPUT`, the detail naming `parameter '<id>' with scope {...}: no record in parameters (D56)` |
| A record whose value is `null`, one that `read_value` refuses, two records with one identity, or a record without a well-formed `id` and `scope` | The same, the detail saying why the record is not read |
| A unit of a record that is not accepted | `NOT_COMPUTABLE` for the parameter, so the values that need it are missing, naming it and its unit |
| A quantity the forcing does not carry | `MISSING_INPUT` naming the quantity and the part (G4, third row) |
| A month of a series that is missing | That month and every later month missing with the reason of that value (the core's `run`); the trend missing |
| The starting pools or a carbon input in another unit than `t C ha-1` | `NOT_COMPUTABLE`, naming the unit; nothing is converted |
| No carbon-input series at all (the residues of EP4 not built, D122) | Every month missing: an empty `carbon_inputs` is `NOT_COMPUTABLE` naming it, never zero |
| The carbon inputs `NOT_AVAILABLE` in a month (D122) | That month and every later month missing, the detail repeating `NOT_AVAILABLE` |

Once the initial state is missing, every month, stock, flow and trend value is missing and names it.

## EP6 run_rothc: PROPOSED cases

Each case is a test function of `test_entry.py`; a test checks that this list and the file agree. Every number in the tests is a PLACEHOLDER, plainly unreal with repeated digits; computed numbers are compared with the core functions called a second time, or with the mass balance.

| Case | What it shows |
|---|---|
| `test_example_forcing_and_empty_catalogue_give_every_value_missing_naming_parameters` | The forcing example and `{}`: a valid `CarbonBalance` in which every value is missing, `MISSING_INPUT`, naming the quantities the example forcing lacks (it carries none of the five pools, so the initial state stops the run) |
| `test_placeholder_catalogue_passes_check_catalogue_and_stocks_are_computed_by_the_core` | A PLACEHOLDER catalogue that passes `check_catalogue`: every stock, pool and flow equals the core's run built a second time by hand |
| `test_mass_balance_holds_at_every_month` | At every month and over the run, the change of total stock equals the carbon input minus the CO2; the total equals the sum of the five pools; the inert pool does not change; no pool is negative |
| `test_pools_never_negative_over_a_long_horizon` | Over a long varied PLACEHOLDER run every pool and flow stays not negative |
| `test_trend_values_are_per_model_and_mean_over_cycles_waits_for_its_input` | The three computations of C1.6 for the carbon model `rothc` only, each naming it (never merged with AMG); `end_minus_start` and `fitted_slope` equal the core functions; `mean_over_cycles` missing, naming the cycle input |
| `test_wrong_types_raise_type_error` | A forcing that is not a `CarbonForcing`, or a `parameters` that is not `dict[str, dict]`, raises `TypeError` |
| `test_the_runner_finds_run_rothc_by_its_module_path_and_name` | `engine.rothc` and `run_rothc`, the module path and name of EP6 as the runner holds them, resolve to this function |
| `test_a_month_without_cover_data_makes_that_month_and_every_later_month_missing` | A missing cover month: that month and every later one missing, the detail repeating the reason; the trend missing |
| `test_a_soil_property_not_declared_is_named` | Clay `NOT_DECLARED`: every month missing, the detail repeating the reason |
| `test_carbon_inputs_not_available_are_named_with_their_reason` | Carbon-input months missing `NOT_AVAILABLE` (D122): that month and every later one missing, the detail repeating `NOT_AVAILABLE` |
| `test_carbon_inputs_left_out_entirely_are_never_zero` | No carbon-input series: every month missing, `NOT_COMPUTABLE` naming `carbon_inputs`, never zero |
| `test_starting_state_feeds_the_pools_it_names` | Each starting pool arrives in its series `initial`; a pool the starting state does not name is missing with its reason and every month names it |
| `test_starting_iom_derived_from_the_total_when_not_given` | Without `rothc_iom_pool` but with `soil_organic_carbon`: the inert pool is the p. 16 form, `DERIVED`; without both: missing, naming both |
| `test_each_parameter_without_a_record_is_named` | Each parameter removed alone: the trend and the last stock are missing, naming it |
| `test_a_record_without_a_value_is_named_with_its_reason` | A `null` value: `MISSING_INPUT` naming the parameter and repeating its reason |
| `test_a_unit_of_a_record_that_is_not_accepted_is_not_computed` | A dimensionless parameter in another unit; a rate constant per another time unit; a clay decay not written `X-1`: each not computed, named |
| `test_each_quantity_the_forcing_lacks_is_named` | Each quantity of the forcing removed alone: `MISSING_INPUT` naming it and its part |
| `test_a_quantity_in_a_unit_the_engine_does_not_accept_is_not_computed` | Rainfall, temperature, clay, cover, soil depth, a starting pool or a carbon input in another unit: `NOT_COMPUTABLE`, naming the unit; nothing is converted |
| `test_pet_stands_in_for_pan_evaporation` | No pan series: the PET series over the pan factor drives the water balance, and the run computes; a missing PET month makes that month missing |
| `test_two_inputs_of_one_origin_take_the_composition_of_that_origin` | Two series of one origin both use its composition records; an origin without records is named with its scope |
| `test_the_balance_names_the_forcing_and_the_variant` | Identifiers, model, variant, horizon, soil depth, units, provenance and series identifiers; the result reloads from JSON |
| `test_run_rothc_is_pure` | The same arguments give the same result; neither argument is changed |
| `test_signature_of_the_entry_point` | `forcing` then `parameters`, the second keyword-only, no default |
| `test_entry_holds_no_value_of_the_method` | `entry.py` writes no number but zero and one |
| `test_readme_lists_the_cases_of_this_file` | This list and `test_entry.py` name the same cases |

## OPEN

Each item is a question a person answers; the role that answers it is named. None is answered by this unit.

1. **The two readings of the step.** Whether the inputs of a month enter before the decomposition of that month, and whether the moisture modifier follows the water balance of its own month. The worked example prints a month without inputs and gives `abc` combined, so it decides neither. For the science lead.
2. **The forcing quantities and the cover encoding.** The identifiers of `FORCING_QUANTITIES` are PROPOSED; the soil-cover encoding (`1.0` vegetated, `0.0` bare, quantity `soil_cover_state`) is this folder's proposal for OPEN 8 of `contracts/carbon_forcing/README.md`. For the platform developer, as producer of `CarbonForcing`, and the science reviewers.
3. **Which values a constant may take.** Only what a form cannot carry is refused (see above). No upper bound is put on the clay content, the temperature, or any constant; a bound is a value, so a person supplies it. For the science lead.
4. **The temperature modifier above one.** The transcribed form rises through one near 9.3 °C and keeps rising; the description prints no bound. For the science lead.
5. **The inert pool by radiocarbon.** The p. 16 alternative (age 50 000 years, Δ14C −998.0) needs data the forcing does not carry and is not built. For the science reviewers.
6. **Cycle boundaries.** `mean_over_cycles` needs the whole rotation cycles; `CarbonForcing` carries none, so it is always missing. Either the forcing gains them or EP6 gains an argument (a change of `contracts/`, lane L0). For the lead developer.
7. **The scope key of an origin.** The composition records are scoped by the origin under the key `crop`, as `engine/amg/` chooses for its humification coefficient; the vocabulary of origins is OPEN 4 of the forcing README. For the lead developer.
8. **The record files.** `params/records/` holds no RothC record; the persons write them from the table above (D34: the table's values are transcribed and checked). Whether the split of the plant materials by land use is one record per origin or needs another scope key is for the person who writes them.
9. **The runner.** `api/engines.py` holds `EntryPoint("EP6", "rothc", "engine.rothc", "run_rothc")` but does not discover it; wiring the runner to call EP6 is a change of lane L2a, and the response of the running app does not change with this unit.
10. **RESOLVED by the case designer (15 November 2026): the pool tolerance is 1e-4.** The printed table displays `start − truncated difference` (the arithmetic is in `test_reference_case.py`), so a printed end value carries up to 5e-5 of the document's truncated intermediate plus 5e-5 of its own rounding — 1e-4 is the exact bound of the printed arithmetic. All four pools now compare as plain asserts (faithful gaps: DPM 6.29e-05, RPM 5.23e-05, BIO 5.3e-06, HUM 5.0e-06).

## Not verified

- **The forms against the source document.** The session read no RothC source, by rule; the forms are the person transcription of issue #176, checked under D63/D134.
- **The runner calling EP6.** The runner does not discover EP6 yet (OPEN 9). With this unit, `api/test_engines.py::test_the_carbon_engines_written_not_built_do_not_exist_yet[EP6]` fails, as that test's own comment prescribes ("when one lands, this fails: the runner must then discover and call it, a unit of lane L2a"); the runner unit removes it, and this folder does not touch `api/`.
- **The parameter records.** `params/records/` holds none; the tests build in-memory records from the transcribed values.
- **Lint.** No ruff is installed in this session's environment; CI lints `api/`, `adapters/` and `ci/` only, and this session checked imports and line lengths by hand against the practice of `engine/amg/`.
- **The names scan of CI** (the list of forbidden names is a secret).
