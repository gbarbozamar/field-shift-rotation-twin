# The AMG soil carbon model: core and entry point EP5

Units `l1/amg-core` (brief in issue #174: the core) and `l1/amg-ep5` (brief in issue #192: the entry point, section [EP5 run_amg](#ep5-run_amg)). Status: `PROPOSED` (blueprint section 3.7): it takes effect only when a person approves the pull request.

Decision D1 of issue #77 makes AMG one of the two carbon models. Unit `l1/amg-core` built the model core, as pure functions:

- the two pools and one step of the carbon balance: humified carbon inputs enter the active pool, the active pool mineralises at a rate coefficient, the stable pool does not change (`pools.py`);
- the rate coefficient as a potential rate times modifiers of soil and climate, each modifier its own function (`modifiers.py`);
- a run over a sequence of steps from an initial state (`pools.py`);
- the three trend measures of C1.6 for `soil_carbon_trend` (`trend.py`).

Unit `l1/amg-ep5` adds EP5, `run_amg(forcing, *, parameters) -> CarbonBalance` (`entry.py`), on that core; it is the only part of the folder that reads the parameter catalogue and builds contract models. The sections up to [OPEN](#open) describe the core as unit `l1/amg-core` wrote it; the sections from [EP5 run_amg](#ep5-run_amg) describe the entry point. The folder computes neither RothC nor the residue ledger.

## The forms

Every form is `PROPOSED`. **Its source is to be confirmed by a person.** The session that wrote this unit read no source of AMG (the carbon method is `OPEN` in `docs/METHODS.md`, "Not in this file yet") and wrote no value of the method anywhere: not in the code, a default, a test, a comment or this file.

| Function | Form | Module |
|---|---|---|
| `humified_input` | `I = sum over origins of carbon_input * humification_coefficient` | `pools.py` |
| `initial_state` | `stable = stable_fraction * total_carbon`; `active = total_carbon - stable` | `pools.py` |
| `step`, scheme `"explicit"` | `M = rate_coefficient * duration * A`; `A' = A + I - M`; `S' = S` | `pools.py` |
| `step`, scheme `"exponential"` | `x = rate_coefficient * duration`; `A' = A * exp(-x) + I * (1 - exp(-x)) / x` (`A' = A + I` when `x` is zero); `M = A + I - A'`; `S' = S` | `pools.py` |
| `run` | `step` applied to each step input in turn; the end of one step is the start of the next, never reset | `pools.py` |
| `rate_coefficient` | `k = potential_rate * product of the modifiers` | `modifiers.py` |
| `temperature_modifier` | `f_T = shape / (1 + (shape - 1) * exp(sensitivity * (reference_temperature - temperature)))` | `modifiers.py` |
| `moisture_modifier` | `f_W = 1 / (1 + shape * exp(-sensitivity * water_balance))` | `modifiers.py` |
| `clay_modifier` | `f_A = exp(-sensitivity * clay_content)` | `modifiers.py` |
| `carbonate_modifier` | `f_CaCO3 = 1 / (1 + sensitivity * carbonate_content)` | `modifiers.py` |
| `ph_modifier` | `f_pH = exp(-sensitivity * (ph - optimum_ph)^2)` | `modifiers.py` |
| `end_minus_start` | `(stock at the last point - stock at the first) / (last time - first time)` | `trend.py` |
| `fitted_slope` | slope of the ordinary least-squares line of stock on time, through every point | `trend.py` |
| `mean_over_cycles` | mean, over the whole cycles given, of `(stock at cycle end - stock at cycle start) / cycle length` | `trend.py` |
| `trend_measures` | the three above over a run's total stocks and elapsed times | `trend.py` |

`A` and `S` are the active and the stable pool at the start of a step, `A'` and `S'` at its end, `I` the humified input over the step and `M` the carbon mineralised over the step. Every step keeps the mass balance `(A' + S') - (A + S) = I - M`.

Two schemes of one step are offered because the session does not know which is the form of the source (OPEN 2). Both take any step length, so a monthly step is the same function with a shorter `duration`. Both have the same steady state for constant inputs, `A = I / (rate_coefficient * duration)`. Under uniform forcing the exponential scheme gives the same result for one long step as for that span cut into equal shorter steps; the explicit scheme does not.

## Signatures

Every argument of a public function is passed by name and none has a default. A number argument is a number or a `Missing` of the contract models (either shape, `contracts.inputs.common.Missing` or `contracts.results.models.Missing`); a result that is not computed is always the `Missing` of `contracts/results/models.py`. No new `Missing` shape is defined.

```python
humified_input(*, carbon_inputs, humification_coefficients) -> float | Missing
initial_state(*, total_carbon, stable_fraction) -> PoolState | Missing
step(*, state, humified_input, rate_coefficient, rate_coefficient_per_unit,
     duration, duration_unit, scheme) -> StepResult | Missing
run(*, initial_state, steps, rate_coefficient_per_unit, duration_unit, scheme) -> Run
rate_coefficient(*, potential_rate, modifiers) -> float | Missing
temperature_modifier(*, temperature, temperature_unit, reference_temperature,
                     reference_temperature_unit, shape_coefficient,
                     sensitivity_coefficient, sensitivity_coefficient_per_unit) -> float | Missing
moisture_modifier(*, water_balance, water_balance_unit, shape_coefficient,
                  sensitivity_coefficient, sensitivity_coefficient_per_unit) -> float | Missing
clay_modifier(*, clay_content, clay_content_unit, sensitivity_coefficient,
              sensitivity_coefficient_per_unit) -> float | Missing
carbonate_modifier(*, carbonate_content, carbonate_content_unit, sensitivity_coefficient,
                   sensitivity_coefficient_per_unit) -> float | Missing
ph_modifier(*, ph, optimum_ph, sensitivity_coefficient) -> float | Missing
end_minus_start(*, stocks, times) -> float | Missing
fitted_slope(*, stocks, times) -> float | Missing
mean_over_cycles(*, stocks, times, cycle_boundaries) -> float | Missing
trend_measures(*, run, cycle_boundaries) -> TrendMeasures
```

- `PoolState`: `active`, `stable` and the property `total`.
- `StepInput`: `humified_input`, `rate_coefficient`, `duration`, each a number or a `Missing`.
- `StepResult`: `start` and `end` (`PoolState`), `humified_input`, `mineralised`, `duration`.
- `Run`: `initial_state` (as passed in), `steps` (one `StepResult` or `Missing` per step input), `duration_unit`; `total_stocks()` gives the total carbon at the start and at the end of each step, `elapsed_times()` the time from the start of the run at each of those points (zero first).
- `TrendMeasures`: `values`, one item per identifier of `TREND_COMPUTATIONS` of `contracts/results/models.py` (`end_minus_start`, `fitted_slope`, `mean_over_cycles`), each a number or a `Missing`; `time_unit`, the run's `duration_unit`.
- `scheme` is `"explicit"` or `"exponential"` (`SCHEMES`).
- `modifiers`, `carbon_inputs` and `humification_coefficients` are mappings from a name (text) to a number or a `Missing`. The name of a modifier is used only in a detail.
- `cycle_boundaries` are positions in the series of stocks: where each whole cycle starts and where the last one ends, rising strictly. Which cycles are whole is the caller's, who knows the rotation. A `Missing` is accepted.

The functions return bare numbers. Building a `SoilCarbonTrend` of the results contract (with its provenance, its source or assumption mark, its range or the reason it has none) is left to EP5 or to whoever Q14 (c) names.

## Units

Nothing is converted. Carbon amounts (pools, inputs, mineralised carbon, stocks) share one unit chosen by the caller, and the functions only add, subtract and multiply them. Where a constant multiplies an input that has a unit, the caller states both unit strings and they must be the same text, as in `engine/erosion/c_factor/`:

| Function | Unit strings that must be the same text |
|---|---|
| `step`, `run` | `rate_coefficient_per_unit` (the time unit whose inverse is the unit of the rate coefficient) and `duration_unit` |
| `temperature_modifier` | `temperature_unit`, `reference_temperature_unit`, `sensitivity_coefficient_per_unit` |
| `moisture_modifier` | `water_balance_unit`, `sensitivity_coefficient_per_unit` |
| `clay_modifier` | `clay_content_unit`, `sensitivity_coefficient_per_unit` |
| `carbonate_modifier` | `carbonate_content_unit`, `sensitivity_coefficient_per_unit` |

When they differ the result is `NOT_COMPUTABLE` and the detail names each string (the reason code of a unit that is not accepted is Q11 of `contracts/ENTRYPOINTS.md`, OPEN; the same choice as `engine/erosion/`).

A trend measure is in the carbon unit per the time unit of `times` (for `trend_measures`, `TrendMeasures.time_unit`). The unit of C1.5, `t C ha-1 yr-1`, is reached only when the stocks are in tonnes of carbon per hectare and the times in years (OPEN 9).

## When a result is not computed

In this order; the first that applies is returned. Nothing is clipped, filled, normalised or replaced by zero.

1. **`MISSING_INPUT`**: an argument is missing. The detail names every missing argument with its own reason code and detail (C3.3). For `humified_input`, an origin of `carbon_inputs` without a humification coefficient is missing and named. For `rate_coefficient`, a modifier held as a `Missing` (also one a modifier function refused) is named. For `step`, a missing state is named.
2. **`NOT_COMPUTABLE`**:
   - an argument that is not a finite number ("not a number", an infinity, an integer too large for a float);
   - then a value outside what the quantity can be: a negative carbon input, pool, total carbon, rate coefficient, potential rate, modifier, step length, clay content or carbonate content; a humification coefficient or a stable fraction outside zero to one;
   - then unit strings that differ;
   - then, for the explicit scheme, `rate_coefficient * duration` above one: it is the fraction of the active pool mineralised in the step, and above one more carbon would leave the pool than it holds (PROPOSED, OPEN 3);
   - then a form that gives no finite real number, or a modifier that the form makes negative (PROPOSED, OPEN 5);
   - for `humified_input`, an empty `carbon_inputs` (PROPOSED, OPEN 6).
3. **A run**: once a step is missing, every later step is `MISSING_INPUT`, and its detail names the first missing step (counted from zero) with its reason. When the initial state is missing, every step is `MISSING_INPUT` naming it. The total stock and the elapsed time at and after a missing step are missing too.
4. **A trend measure** needs only the points it uses: `end_minus_start` the first and the last, `fitted_slope` every point, `mean_over_cycles` the points at the cycle boundaries. One of those that is missing gives `MISSING_INPUT` naming it (with the run's detail, so the first missing step is named). `NOT_COMPUTABLE` for: fewer than two points; times at the points used that do not rise strictly; fewer than two cycle boundaries (no whole cycle), a boundary outside the series or not after the one before; a value that is not finite.

A `TypeError` is raised for an argument of another type (`None`, text, a boolean, a list in place of a number; a state that is not a `PoolState`; a step that is not a `StepInput`), so a `None` is never read as a value. A `ValueError` is raised for a scheme that is not one of `SCHEMES`, and when `stocks` and `times` differ in length (OPEN 12).

## Constants a person has to transcribe

One row per constant. A person fills the parameter catalogue (`params/records/`) from this table and signs `transcribed_by`; a second person checks each value against the source and signs `checked_by` (D34 of issue #77, `params/README.md`). **The column "Value" stays empty: a session writes no value.** The identifiers are `PROPOSED`.

| Constant | Proposed parameter identifier | What it is | Unit | Source and equation | Value |
|---|---|---|---|---|---|
| `humified_input.humification_coefficients` | `amg_humification_coefficient` | The share of the carbon of an input that enters the active pool: one record per origin, told apart by its scope (OPEN 7) | None (a fraction, zero to one) | OPEN: the session read no source of AMG | |
| `initial_state.stable_fraction` | `amg_stable_fraction` | The share of the initial soil carbon held in the stable pool | None (a fraction, zero to one) | OPEN: the session read no source of AMG; whether it is a constant or a value of the site is OPEN 8 | |
| `rate_coefficient.potential_rate` | `amg_potential_mineralisation_rate` | The rate coefficient of the active pool before any modifier | One over a time, the time stated as `rate_coefficient_per_unit` | OPEN: the session read no source of AMG | |
| `temperature_modifier.reference_temperature` | `amg_temperature_reference` | The temperature at which the temperature modifier is one | A temperature, stated as `reference_temperature_unit` | OPEN: the session read no source of AMG | |
| `temperature_modifier.shape_coefficient` | `amg_temperature_shape` | The upper limit of the temperature modifier at high temperature, in the PROPOSED form | None | OPEN: the session read no source of AMG | |
| `temperature_modifier.sensitivity_coefficient` | `amg_temperature_sensitivity` | How fast the temperature modifier changes with temperature | One over a temperature, stated as `sensitivity_coefficient_per_unit` | OPEN: the session read no source of AMG | |
| `moisture_modifier.shape_coefficient` | `amg_moisture_shape` | Multiplies the exponential of the moisture modifier | None | OPEN: the session read no source of AMG | |
| `moisture_modifier.sensitivity_coefficient` | `amg_moisture_sensitivity` | How fast the moisture modifier changes with the water balance | One over a depth of water, stated as `sensitivity_coefficient_per_unit` | OPEN: the session read no source of AMG | |
| `clay_modifier.sensitivity_coefficient` | `amg_clay_sensitivity` | Multiplies the clay content in the exponent of the clay modifier | One over a content, stated as `sensitivity_coefficient_per_unit` | OPEN: the session read no source of AMG | |
| `carbonate_modifier.sensitivity_coefficient` | `amg_carbonate_sensitivity` | Multiplies the carbonate content in the carbonate modifier | One over a content, stated as `sensitivity_coefficient_per_unit` | OPEN: the session read no source of AMG | |
| `ph_modifier.optimum_ph` | `amg_ph_optimum` | The pH at which the pH modifier is one | None (pH) | OPEN: the session read no source of AMG | |
| `ph_modifier.sensitivity_coefficient` | `amg_ph_sensitivity` | How fast the pH modifier falls away from the optimum | None (one over a squared pH difference) | OPEN: the session read no source of AMG | |

Not constants of the method, and so not in this table: the step length and its unit, the scheme (OPEN 2), the horizon and the soil depth (C1.6, OPEN for the science reviewers) and the cycle boundaries.

## PROPOSED cases

Each case is a test function of `test_amg.py`; a test checks that this list and the file agree. Every constant in the tests is a PLACEHOLDER (repeated digits, or small whole numbers where the arithmetic is done by hand). No case holds an expected value of the science.

### Humified input and initial state

| Case | What it shows |
|---|---|
| `test_humified_input_is_the_sum_of_inputs_times_their_coefficients` | `I` equals the form written a second time in the test; a coefficient of an origin that is not an input is not used; an input of zero gives zero |
| `test_humified_input_without_a_coefficient_for_an_origin_is_missing_and_names_it` | An origin without a coefficient, or with a `Missing` one (both shapes), gives `MISSING_INPUT` naming it |
| `test_humified_input_coefficient_outside_zero_to_one_is_refused` | A humification coefficient below zero or above one, even by a hair, is `NOT_COMPUTABLE` naming it and no other; zero and one are accepted |
| `test_humified_input_negative_input_is_refused` | A negative carbon input is `NOT_COMPUTABLE` naming it |
| `test_humified_input_with_no_origin_is_not_computed` | An empty mapping of inputs is `NOT_COMPUTABLE`, never zero |
| `test_initial_state_splits_total_carbon_by_the_stable_fraction` | The two pools follow the form and add up to the total; fractions zero and one leave one pool empty |
| `test_initial_state_refuses_negative_carbon_or_fraction_outside_zero_to_one` | A negative total, or a stable fraction outside zero to one even by a hair, is `NOT_COMPUTABLE` naming it |

### One step

| Case | What it shows |
|---|---|
| `test_explicit_step_follows_the_proposed_form` | Mineralised carbon and the new active pool equal the explicit form written a second time in the test, also at a rate of zero and at `rate_coefficient * duration` of exactly one |
| `test_exponential_step_follows_the_proposed_form` | The new active pool and the mineralised carbon equal the exponential form written a second time in the test |
| `test_exponential_step_with_no_mineralisation_adds_the_input` | With a rate or a length of zero, the input is added and nothing is mineralised |
| `test_step_keeps_the_stable_pool` | In both schemes the stable pool is the same at the end of the step as at its start |
| `test_step_mass_balance_holds_for_each_scheme` | The change of total carbon equals humified input minus mineralised carbon, and the mineralised carbon is not negative |
| `test_explicit_step_refuses_more_mineralisation_than_the_active_pool_holds` | `rate_coefficient * duration` above one is `NOT_COMPUTABLE` in the explicit scheme; the exponential scheme keeps the pool not negative |
| `test_step_negative_value_is_refused_and_named` | A negative input, rate, length or pool is `NOT_COMPUTABLE` naming it, in both schemes |
| `test_step_units_that_differ_are_not_computed` | Different unit strings for the rate and the length: `NOT_COMPUTABLE` naming both |
| `test_step_missing_state_or_argument_gives_missing_input` | A missing state, input, rate or length gives `MISSING_INPUT` naming it with its reason; both shapes |
| `test_step_unknown_scheme_raises_value_error` | A scheme that is not one of `SCHEMES` raises `ValueError`, in `step` and in `run` |

### Modifiers and the rate coefficient

| Case | What it shows |
|---|---|
| `test_temperature_modifier_follows_the_proposed_form` | `f_T` equals the form written a second time in the test over a grid of temperatures |
| `test_temperature_modifier_is_one_at_the_reference_temperature` | At the reference temperature `f_T` is one, for any shape and sensitivity |
| `test_moisture_modifier_follows_the_proposed_form` | `f_W` equals the form written a second time in the test, for a negative, zero and positive water balance |
| `test_clay_modifier_follows_the_proposed_form` | `f_A` equals the form written a second time in the test; it is one without clay |
| `test_carbonate_modifier_follows_the_proposed_form` | `f_CaCO3` equals the form written a second time in the test; it is one without carbonate |
| `test_ph_modifier_follows_the_proposed_form` | `f_pH` equals the form written a second time in the test; it is one at the optimum |
| `test_modifier_negative_content_is_refused` | A negative clay or carbonate content is `NOT_COMPUTABLE` naming it |
| `test_modifier_that_the_form_makes_negative_or_not_finite_is_not_computed` | Arguments for which a form gives a negative modifier, a division by zero or an overflow: `NOT_COMPUTABLE`, nothing raised |
| `test_modifier_units_that_differ_are_not_computed` | Each unit string that must agree, changed alone: `NOT_COMPUTABLE` naming it |
| `test_rate_coefficient_is_the_potential_rate_times_the_modifiers` | `k` is the product; no modifier gives the potential rate; a modifier of zero gives zero; the five modifier functions feed it |
| `test_rate_coefficient_missing_or_negative_modifier_is_not_computed` | A missing potential rate or modifier gives `MISSING_INPUT` naming it (both shapes); a negative one `NOT_COMPUTABLE`; a modifier a function refused keeps `k` missing |

### A run over steps

| Case | What it shows |
|---|---|
| `test_run_equals_steps_applied_one_after_another` | The run equals `step` applied in turn, each start the end of the step before |
| `test_run_mass_balance_holds_at_every_step_over_a_long_series` | Over three thousand steps of varied PLACEHOLDER inputs, rates and lengths, each step keeps the mass balance, and so does the whole run, to floating-point precision, in both schemes |
| `test_run_with_zero_inputs_active_pool_only_decreases_and_stable_pool_does_not_change` | With no input the active pool falls at every step and stays not negative; the stable pool never changes |
| `test_run_with_constant_inputs_approaches_the_steady_state_of_the_form` | With constant inputs, from below and from above, the active pool comes ever closer to `I / (rate_coefficient * duration)` and ends there, in both schemes (structure only) |
| `test_exponential_steps_compose_under_uniform_forcing` | One long exponential step equals the same span cut into equal steps with the input spread evenly; the explicit scheme does not (the comparison of blueprint section 8, structure only) |
| `test_run_missing_step_input_makes_that_step_and_every_later_step_missing` | A missing input, rate or length at one step makes that step and every later one `MISSING_INPUT`, naming the step and the input; earlier steps are kept; stocks after it are missing; both shapes, both schemes |
| `test_run_refused_step_input_is_never_clipped` | A negative input or rate, or a length that is not a number, at one step makes it `NOT_COMPUTABLE` and every later step `MISSING_INPUT` naming it |
| `test_run_missing_initial_state_makes_every_step_missing` | A missing initial state, also one `initial_state` refused, makes every step and every stock missing, naming it |
| `test_run_elapsed_times_and_total_stocks` | The elapsed times are the running sums of the lengths from zero; the stocks are the initial total and the total at the end of each step |

### Trend measures of C1.6

| Case | What it shows |
|---|---|
| `test_end_minus_start_is_the_change_over_the_horizon_per_unit_time` | Worked by hand; a missing point between the ends does not stop it |
| `test_fitted_slope_recovers_the_slope_of_a_straight_line` | A straight line gives its own slope; a series worked by hand gives the least-squares slope |
| `test_mean_over_cycles_is_the_mean_change_per_unit_time_of_the_whole_cycles` | Worked by hand for equal and unequal cycles; points after the last whole cycle are not used |
| `test_trend_measures_name_the_three_computations_of_c16` | The measures of a run carry the three identifiers of `TREND_COMPUTATIONS` in order, the default of C1.6 among them, the run's time unit, and the values of the three functions |
| `test_trend_of_a_run_with_a_missing_step_is_missing_with_its_reason` | Every measure of a run with a missing step is `MISSING_INPUT`, naming the stock and the first missing step with its reason |
| `test_mean_over_cycles_without_whole_cycle_or_boundaries_is_missing_with_reason` | Missing boundaries give `MISSING_INPUT`; fewer than two boundaries, one outside the series or out of order, `NOT_COMPUTABLE`; the other measures are still computed |
| `test_trend_without_a_span_of_time_is_not_computed` | Fewer than two points, or times that do not rise strictly, are `NOT_COMPUTABLE`; series of different lengths raise `ValueError` |

### Arguments of every function

| Case | What it shows |
|---|---|
| `test_argument_that_is_not_finite_is_not_computed` | "Not a number", an infinity or an integer too large for a float, as any number argument of any function: `NOT_COMPUTABLE` naming it |
| `test_items_that_are_not_finite_are_not_computed` | The same for an item of a mapping, a pool of a state, a stock and a time |
| `test_missing_argument_gives_missing_input_that_names_it` | A missing number argument of any function gives `MISSING_INPUT` naming it with its reason; both shapes |
| `test_argument_of_another_type_raises_type_error` | `None`, text, a boolean or a list as a number argument raises `TypeError` naming it |
| `test_structured_argument_of_another_type_raises_type_error` | The same for a mapping, a state, the steps, a unit string, the scheme, a series, the cycle boundaries and the run |

### No constant of the method; the entry point

| Case | What it shows |
|---|---|
| `test_every_argument_is_passed_by_name_and_none_has_a_default` | Every public function takes keyword arguments only, without a default; no field of a result type has a default |
| `test_the_modules_hold_no_number_but_zero_and_one` | The modules of this folder write no number but zero and one |
| `test_entry_point_is_run_amg_of_entry_module` | `engine.amg.run_amg` is the function of `entry.py` (unit `l1/amg-ep5` changed this case, which stated that EP5 did not exist yet) |
| `test_readme_lists_every_constant_with_an_empty_value` | The table of constants has one row per constant, each an argument of its function, a well-formed and distinct identifier, and an empty value |
| `test_readme_lists_the_cases_of_this_file` | This list and `test_amg.py` name the same cases |

### Waiting for a person

Each is **skipped**, and its skip reason says what it waits for: the source of AMG chosen by a person, the constants as records of the parameter catalogue, and the inputs, published result and tolerance of a worked example, transcribed by a person and checked by a second person (D34).

| Case | What it shows |
|---|---|
| `test_published_worked_example_of_the_yearly_run` | A yearly run against a published worked example |
| `test_published_worked_example_of_the_rate_coefficient` | The rate coefficient and its modifiers against a published example |
| `test_published_comparison_of_the_yearly_and_monthly_variants` | The annual reference and the monthly adaptation of blueprint section 8 against each other on a published case |

## OPEN

Each item is a question a person has to answer; the role that answers it is named. None is answered by this unit.

1. **Which source is AMG here, and are the forms its forms?** The carbon method is `OPEN` in `docs/METHODS.md`. Candidate primary sources, named from the session's memory only, **not read and not checked; to be located and confirmed**: the article that first described AMG (Andriulo, Mary and Guérif, 1999, in *Agronomie*); an article on the stable pool of AMG (Saffih-Hdadi and Mary, 2008, in *Soil Biology and Biochemistry*); the article that described the version of AMG with the soil and climate modifiers (Clivot and others, 2019, in *Environmental Modelling & Software*). Each form above, and the locator of each equation, is to be confirmed against the chosen source. For the science lead.
2. **Which scheme is the step of the source, yearly and monthly?** The explicit step is the classic discrete form of a two-pool balance; the exponential step is the exact solution over a step with inputs spread evenly. Whether the source steps by year with one or the other, and what its monthly adaptation is (blueprint section 8), is not known. For the science lead.
3. **The explicit scheme above one.** `rate_coefficient * duration` above one is refused (PROPOSED: it would mineralise more carbon than the active pool holds). Whether the source bounds it, or whether the inputs of a step are mineralised in the same step, is not known. For the science lead.
4. **Which modifiers, and which inputs feed them?** Five are proposed: temperature, moisture, clay, carbonate, pH. Whether the source has each, whether it has others (for example one for the carbon to nitrogen ratio of the soil), and which temperature (air or soil, mean over which period) and which water balance (precipitation and irrigation less potential evapotranspiration, or another) feed them, is not known. Which modifiers `rate_coefficient` multiplies is the caller's: an empty mapping gives the potential rate. For the science lead.
5. **Which values may a constant or a modifier take?** Only what a form cannot carry is refused: a negative modifier (it would make the active pool grow by mineralisation), a negative potential rate, rate or content, a fraction outside zero to one. No bound is put on a sensitivity or a shape coefficient; a bound is a value, so a person supplies it. For the science lead.
6. **A step without carbon input.** An empty mapping of inputs is refused, so that "no input" is always written as an origin at zero and never arrives by omission. For the lead developer.
7. **The origins of the carbon inputs and their coefficients.** The vocabulary of origins is OPEN 4 of `contracts/carbon_forcing/README.md`; how a catalogue record names its origin (the scope keys of `params/README.md`) is for the lead developer; whether the humification coefficient depends on the crop, the organ or the product, for the science lead.
8. **The stable fraction: a constant of the method or a value of the site?** And whether the initial state comes from a measured stock or from a spin-up run. `ModelState` (blueprint section 5, Q14 (a)) would carry it. For the science lead and the lead developer.
9. **Units of the trend.** The measures are per the time unit of the run. The unit of C1.5 needs stocks in tonnes of carbon per hectare to the soil depth of C1.6 and times in years. Who converts (EP5, or the adapter of `CarbonForcing`) is for the lead developer; the depth and the horizon, for the science reviewers (C1.6).
10. **How each trend measure is read.** C1.6 names the three computations and not their method (CITATION NEEDED). Proposed here: each is a change per unit time; the fitted line is ordinary least squares through every point, the initial state included; the mean over cycles is the mean of the change per unit time of each whole cycle (for cycles of equal length, the same as the change over all whole cycles divided by their length). Whether the series has one point per step or one per year, for a monthly run, is also open. For the science reviewers.
11. **Who computes the trend values and builds the indicator values.** Q14 (c) of `contracts/ENTRYPOINTS.md`: each carbon engine or one shared function. These functions sit in `engine/amg/`; if one function is shared with RothC, it may move. Range and provenance of a value (C2.2, C4.3) are for the caller that builds a `SoilCarbonTrend`. For the lead developer and the interface developer.
12. **Raising for a caller defect.** These functions raise `TypeError` for an argument of another type and `ValueError` for an unknown scheme or series of different lengths, as G5 allows; whether they may is Q7 of `contracts/ENTRYPOINTS.md`. For the platform developer.
13. **Reason codes.** A unit that is not accepted, a value outside what a quantity can be and a non-finite number are `NOT_COMPUTABLE` (Q11 of `contracts/ENTRYPOINTS.md`). For the lead developer.
14. **The proposed identifiers.** The table of constants proposes twelve with the prefix `amg_`, and `SCHEMES` proposes `"explicit"` and `"exponential"`. For the lead developer, who owns `params/`.
15. **EP5.** Built by unit `l1/amg-ep5`: see [EP5 run_amg](#ep5-run_amg) and its own OPEN list. `ModelState` still does not exist.

## Not verified

- **The forms and every constant against a source of AMG.** The session read none, by rule.
- **The published worked examples.** The three tests are skipped until a person transcribes them.
- **The candidate sources of OPEN 1.** Named from memory; their titles, authors, years and journals are not checked.
- **The names scan of CI.** The list of forbidden names is a secret of the repository.
- **Lint in CI.** The CI workflow runs ruff on `api/`, `adapters/` and `ci/` only; the session ran ruff on this folder.

## EP5 run_amg

Unit `l1/amg-ep5`, brief in issue #192. Status: `PROPOSED`. The entry point EP5 of `contracts/ENTRYPOINTS.md`, in `entry.py`, exported by `engine/amg/__init__.py`:

```python
run_amg(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance
```

- `forcing`: `contracts.carbon_forcing.CarbonForcing` (#155, D62, D65).
- `parameters`: the catalogue as `params.catalogue.load_folder` returns it, after `check_catalogue` reported no problem (G3, D46, D56).
- Returns `contracts.carbon_balance.CarbonBalance` (PROPOSED by this unit, `contracts/carbon_balance/README.md`), carbon model `amg`, variant `amg_a`.
- Raises `TypeError` when `forcing` is not a `CarbonForcing`, or `parameters` is not a `dict` from text to `dict` (G5). Nothing else is raised for data. One argument carries the identifiers, so the `ValueError` of G5 does not arise.
- Pure (G1): reads records only with `params.catalogue.identity` and `params.catalogue.read_value`, changes no argument, reads no file, clock or environment.

### What it builds

Only **AMG-A**, the annual published reference that takes part in the selection (D80). AMG-M, the monthly variant, is experimental under D80 and is not built (EP5 OPEN 1).

1. **Steps.** One step per agricultural year of the horizon, from its first month (C5.3), each of length one `yr` (C1.1: one agricultural year). Months after the last whole agricultural year make one more step, which is not computed: its inputs are missing, reason `NOT_COMPUTABLE`, "not a whole agricultural year" (the core then reports the step `MISSING_INPUT` naming them).
2. **Initial state.** `initial_state(total_carbon, stable_fraction)` of the core: the starting soil carbon of the forcing and `amg_stable_fraction`.
3. **Each step.** `humified_input` of the core, over every series of `annual_carbon_inputs` (keyed by the series' quantity, each with the humification coefficient of its `origin`). `rate_coefficient` of the core: the potential rate times the five modifiers of the core (temperature and moisture of that agricultural year; clay, carbonate and pH of the soil). `run` of the core with scheme `explicit` (EP5 OPEN 3).
4. **Trend.** `trend_measures` of the core over the total stocks and elapsed times of the run. `mean_over_cycles` is given no cycle boundaries, because `CarbonForcing` carries no rotation cycle: it is always missing, `MISSING_INPUT`, naming that input, and also the first missing stock when there is one (EP5 OPEN 6).
5. **The balance.** `total_stock` (`soil_organic_carbon`), `pools` (`amg_active_pool`, `amg_stable_pool`) and `flows` (`amg_humified_input`, `amg_mineralised_carbon`), all in `t C ha-1`, one value per step; the three `SoilCarbonTrend` values in `t C ha-1 yr-1`. The initial stocks carry `DERIVED` (a fixed formula of declared values, C4.3); step values and trend values carry `SIMULATED` (C4.1). Each present value carries a source naming `engine.amg.run_amg`, the variant, the scheme, the forcing quantities and the parameter records read, and `range_missing` with reason `NOT_AVAILABLE` (no range is computed; Q6 of `contracts/ENTRYPOINTS.md`). `horizon`, `soil_depth`, `example_data` and the three identifiers are copied from the forcing.

### What it reads from the forcing

The identifiers are PROPOSED (`entry.FORCING_QUANTITIES`), for the producer of `CarbonForcing` (the platform developer) and the science reviewers. The vocabulary of the forcing is OPEN in `contracts/carbon_forcing/README.md`.

| Input of the core | Part of `CarbonForcing` | Quantity (PROPOSED) | Unit required |
|---|---|---|---|
| `initial_state.total_carbon` | `starting_state` | `soil_organic_carbon` | `t C ha-1` (C1.5 without `yr-1`); another unit is `NOT_COMPUTABLE`, nothing is converted |
| `humified_input.carbon_inputs` | `annual_carbon_inputs` | every series, by its own quantity; its `origin` chooses the coefficient | `t C ha-1` over the agricultural year, as above |
| `temperature_modifier.temperature` | `annual_climate` | `mean_temperature` | compared by the core with the unit of `amg_temperature_reference` and of `amg_temperature_sensitivity` |
| `moisture_modifier.water_balance` | `annual_climate` | `water_balance` | compared by the core with the unit of `amg_moisture_sensitivity` |
| `clay_modifier.clay_content` | `soil_properties` | `clay_content` | compared by the core with the unit of `amg_clay_sensitivity` |
| `carbonate_modifier.carbonate_content` | `soil_properties` | `carbonate_content` | compared by the core with the unit of `amg_carbonate_sensitivity` |
| `ph_modifier.ph` | `soil_properties` | `ph` | `dimensionless` (C1.1) |

Not read by AMG-A: `climate`, `carbon_inputs` and `soil_cover` (the monthly series). `soil_depth` is copied unchanged.

### What it reads from the parameter catalogue

The twelve parameters of the table [Constants a person has to transcribe](#constants-a-person-has-to-transcribe), with those identifiers, each found by its `id` and its `scope`, exactly, as in `engine/water/` (question 5 of `params/README.md`). Every scope is empty except that of `amg_humification_coefficient`: one record per origin, with the origin under the scope key `crop` (EP5 OPEN 4). How the unit of each record is used (`entry.PARAMETERS`; C1.1 writes "per X" as `X-1`):

| Parameters | Unit of the record |
|---|---|
| `amg_humification_coefficient`, `amg_stable_fraction`, `amg_temperature_shape`, `amg_moisture_shape`, `amg_ph_optimum`, `amg_ph_sensitivity` | `dimensionless`; another text is `NOT_COMPUTABLE` |
| `amg_potential_mineralisation_rate` | `X-1`; `X` goes to the core as the time unit of the rate, which must be `yr` |
| `amg_temperature_sensitivity`, `amg_moisture_sensitivity`, `amg_clay_sensitivity`, `amg_carbonate_sensitivity` | `X-1`; `X` goes to the core, which compares it with the unit of the input; a unit not written `X-1` is `NOT_COMPUTABLE` |
| `amg_temperature_reference` | goes to the core as it is |

### What it returns in each case

| Case | What the balance holds |
|---|---|
| Every input and parameter present | Every stock, pool, flow and step computed by the core; `end_minus_start` and `fitted_slope` computed; `mean_over_cycles` missing, `MISSING_INPUT`, naming the cycle boundaries |
| A parameter with no record (also: an empty catalogue) | The values that need it missing, `MISSING_INPUT`, the detail naming `parameter '<id>' with scope {...}: no record in parameters (D56)` |
| A record whose value is `null` | The same, the detail repeating the reason of the record |
| A record that `read_value` refuses (a placeholder, malformed), two records with one identity, or a record anywhere without a well-formed `id` and `scope` | The same, the detail saying why the record is not read |
| A unit of a record that is not accepted | `NOT_COMPUTABLE` for the parameter, so the values that need it are missing, naming it and its unit |
| A quantity the forcing does not carry | `MISSING_INPUT` naming the quantity and the part (G4, third row) |
| A value of the forcing that is missing | `MISSING_INPUT` with the reason of that value; for an annual value, that step and every later step (the core's `run`) |
| The starting carbon or a carbon input in another unit than `t C ha-1` | `NOT_COMPUTABLE`, naming the unit; nothing is converted |
| Months after the last whole agricultural year | One last step, not computed (step 1 of [What it builds](#what-it-builds)) |
| The forcing example of `contracts/carbon_forcing/` with an empty catalogue | Every value missing, `MISSING_INPUT`, each detail naming at least `amg_stable_fraction`, and the forcing quantities it lacks |

Once the initial state is missing, every step, stock, flow and trend value is missing and names it (the core's `run` and `trend_measures`).

### The runner

`api/engines.py` imports each engine by module path and function name, with `importlib.import_module` and `getattr`; `engine.amg` with `run_amg` resolves to this function (`test_the_runner_finds_run_amg_by_its_module_path_and_name`). But the runner does not import EP5 today. Its list `DISCOVERED` holds EP2, EP1 and EP3 only, and `EngineFunctions` has no field for EP5. It writes the carbon modules `residues`, `amg` and `rothc` as `not_available`, `NOT_AVAILABLE`, "no carbon engine is built yet", and `soil_carbon_trend` as missing, `NOT_AVAILABLE`, for each carbon model. Nothing in `api/` produces a `CarbonForcing`. So with this unit the running app returns the same response as before (EP5 OPEN 9 and 10).

## EP5 run_amg: PROPOSED cases

Each case is a test function of `test_entry.py`; a test checks that this list and the file agree. Every number in the tests is a PLACEHOLDER; computed numbers are compared with the core functions called a second time, or with the mass balance. The PLACEHOLDER records pass `check_catalogue` only in their in-memory copy with the word replaced, as in `engine/water/`.

| Case | What it shows |
|---|---|
| `test_example_forcing_and_empty_catalogue_give_every_value_missing_naming_parameters` | The forcing example and `{}`: a valid `CarbonBalance` in which every value is missing, `MISSING_INPUT`, naming a parameter with "no record in parameters (D56)" |
| `test_placeholder_catalogue_passes_check_catalogue_and_stocks_are_computed_by_the_core` | A PLACEHOLDER catalogue that passes `check_catalogue`: every stock, pool and flow equals the core's run built a second time by hand |
| `test_mass_balance_holds_at_every_step` | At every step and over the run, the change of total stock equals humified input minus mineralised carbon; total equals active plus stable; the stable pool does not change |
| `test_trend_values_are_those_of_the_core_and_mean_over_cycles_waits_for_its_input` | `end_minus_start` and `fitted_slope` equal the core functions, with unit, provenance, model and range reason; `mean_over_cycles` missing, naming the cycle input |
| `test_wrong_types_raise_type_error` | A forcing that is not a `CarbonForcing`, or a `parameters` that is not `dict[str, dict]`, raises `TypeError` |
| `test_the_runner_finds_run_amg_by_its_module_path_and_name` | `engine.amg` and `run_amg`, the module path and name of EP5, resolve to this function |
| `test_each_parameter_without_a_record_is_named` | Each of the twelve parameters removed alone: the trend and the last stock are missing, naming it |
| `test_a_record_without_a_value_is_named_with_its_reason` | A `null` value: `MISSING_INPUT` naming the parameter and repeating its reason; the initial stock, which does not need it, is computed |
| `test_a_placeholder_record_is_not_read` | A record that still carries the word PLACEHOLDER is not read, and is named |
| `test_a_unit_of_a_record_that_is_not_accepted_is_not_computed` | A dimensionless parameter in another unit; a sensitivity not written `X-1`; a rate per another time unit: each not computed, named |
| `test_each_quantity_the_forcing_lacks_is_named` | Each quantity of the forcing removed alone: `MISSING_INPUT` naming it and its part |
| `test_a_missing_climate_year_makes_that_step_and_every_later_step_missing` | A missing annual temperature: earlier steps kept; that step and every later one missing with the reason; trend missing |
| `test_starting_carbon_or_input_in_another_unit_is_not_computed` | The starting carbon or a carbon input in another unit: `NOT_COMPUTABLE`, nothing converted |
| `test_months_after_the_last_whole_agricultural_year_are_one_step_not_computed` | A horizon that ends inside an agricultural year: one last step, not computed, "not a whole agricultural year" |
| `test_two_inputs_of_one_origin_take_the_coefficient_of_that_origin` | Two series of one origin both use its coefficient; an origin without a record is named with its scope |
| `test_the_balance_names_the_forcing_and_the_variant` | Identifiers, model, variant, horizon, soil depth, units, provenance and series identifiers; the result reloads from JSON |
| `test_run_amg_is_pure` | The same arguments give the same result; neither argument is changed |
| `test_signature_of_the_entry_point` | `forcing` then `parameters`, the second keyword-only, no default |
| `test_entry_holds_no_value_of_the_method` | `entry.py` writes no number but zero and one |
| `test_readme_lists_the_cases_of_this_file` | This list and `test_entry.py` name the same cases |

## EP5 run_amg: OPEN

Each item is a question a person answers; the role is named. None is answered by this unit.

1. **AMG-M.** The monthly variant (blueprint section 8; experimental under D80, checked against AMG-A under uniform forcing, no carbon vote) is not built. Whether `run_amg` returns it too (a second balance, or a second function), how it is labelled, and which monthly series of the forcing it reads (Q14 (d)). For the lead developer.
2. **The forcing quantities.** `soil_organic_carbon`, `mean_temperature`, `water_balance`, `clay_content`, `carbonate_content`, `ph` (PROPOSED). Which temperature (air or soil, mean of what) and which water balance feed the modifiers (OPEN 4 of the core), and who makes the annual values from the daily record. For the platform developer, as producer of `CarbonForcing`, and the science reviewers.
3. **The scheme of the annual step.** `explicit` is used so that AMG-A can run (OPEN 2 of the core). For the science lead.
4. **The scope of a humification coefficient.** The origin is written under the scope key `crop`; `params/catalogue.py` has no key for an origin, and the vocabulary of origins is OPEN (OPEN 7 of the core; OPEN 4 of `contracts/carbon_forcing/README.md`). For the lead developer.
5. **Which modifiers.** All five of the core multiply the rate (OPEN 4 of the core). For the science lead.
6. **Cycle boundaries.** `mean_over_cycles` needs the whole rotation cycles. `CarbonForcing` carries no cycle length or boundaries, so it is always missing. Either the forcing gains them (a change of `contracts/carbon_forcing/`: the platform developer and the lead developer) or EP5 gains an argument (a change of `contracts/ENTRYPOINTS.md`: lane L0).
7. **Units.** The stocks and inputs must be in `t C ha-1` and the rate per `yr`; nothing is converted (OPEN 9 of the core). The unit string of a dimensionless record (`dimensionless`, C1.1) is also question 1 of `params/README.md`. For the lead developer.
8. **The carbon inputs per agricultural year.** An annual carbon input is read as the amount entering over that agricultural year, in `t C ha-1`. For the platform developer and the science reviewers.
9. **`contracts/ENTRYPOINTS.md`, for a later L0 unit.** EP5 should say: Status `PROPOSED`; return type `CarbonBalance` of `contracts/carbon_balance/models.py` (PROPOSED); signature `run_amg(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance` (`parameters` keyword-only, as the runner passes it); AMG-A only (D80), variant `amg_a`; `soil_carbon_trend` travels inside the balance (Q14 (c)); the row `soil_carbon_trend` of "From the entry points to one response" names EP5 and EP6. EP6 should name the same return type. For Q14 (a), the state at the end is the last step of each stock series.
10. **The runner (`api/engines.py`, platform developer).** To use EP5 it needs: an entry `EntryPoint("EP5", "amg", "engine.amg", "run_amg")` in its discovery and a field in `EngineFunctions`; a `CarbonForcing` for the request (no adapter builds one: a port and an adapter of lane L2a); a call `run_amg(forcing, parameters=...)` with the catalogue it already loads; a check that the result is a `CarbonBalance`; the module status of `amg` from the values of the balance; and copying `balance.soil_carbon_trend` into `ResultsPerRotation.soil_carbon_trend` in place of the missing values for `amg`, keeping `rothc` missing while EP6 is not built. Whether the response also carries the stocks (a new part of the response) is for the platform developer and the interface developer.
11. **The source text of a value** (question 11 of `contracts/results/README.md`). PROPOSED here: it names the engine, the variant, the scheme, the forcing quantities and the parameter records. For the lead developer.

## EP5 run_amg: not verified

- **Any value of AMG.** Every number in the tests is a PLACEHOLDER; `params/records/` is empty (D34).
- **Use by the runner.** The runner does not call EP5 (see [The runner](#the-runner)).
- **The names scan of CI** (the list is a secret) and **lint in CI** (ruff runs on `api/`, `adapters/` and `ci/` only; this session ran it on this folder and on `contracts/carbon_balance/`).
