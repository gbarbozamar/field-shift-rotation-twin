# `engine/water/evaporation/`: surface-layer balance and `Ke`

Soil evaporation by the FAO-56 dual crop coefficient (decision D44 of issue #77, which places it in FAO-56 chapters 7 and 8). Unit `l1/water-evaporation-ke`, issue #149. D44 writes actual evapotranspiration as `ETa = (Ks · Kcb + Ke) · ET0`. This folder computes `Ke`, the evaporation coefficient, day by day, from the daily balance of the surface soil layer. Its output is what `engine/water/balance/` (#116) takes as the `evaporation_coefficient` of its `DayInput`. It is an internal part of the water engine; the route calls only EP3 of `contracts/ENTRYPOINTS.md`.

Status: **PROPOSED** (blueprint section 3.7). Nothing here is in force until people approve the pull request: the lead developer, who owns lane L1 and decided the method (D44), and a science reviewer, because the forms of the equations and the order of the flows within a day are science-class (blueprint section 3.6).

## What a reader must know first

- **This folder holds no constant of the method.** The depth of the surface layer, the readily and total evaporable water, the minimum crop coefficient, the climate adjustment of the upper limit and its constants, the margin above the basal coefficient, the wetted fraction and every exponent are arguments with no default. A test checks that `surface_layer.py` holds no number other than zero and one; another checks that no public function, input record or constants record has a default. Every number in `test_surface_layer.py` is a PLACEHOLDER, plainly not real, and none comes from FAO-56 or any other source.
- **The forms of the equations are PROPOSED.** A builder session wrote each form in the docstring of its function, without the method's text in front of it. A person checks every form against FAO-56 chapter 7 and confirms its source (OPEN 1).
- **Equation numbers are OPEN.** Issue #13 reports only the reference evapotranspiration chapters (2 to 4) and gives no equation of chapter 7, and no other source was read by this session.
- The citation of the method is CITATION NEEDED: a person composes it, with its row in `ATTRIBUTIONS.md`.
- **The balance of the surface layer leaves out the transpiration drawn from it (`Tew`).** That is a declared limit of the method, by decision D82 of issue #77 (PC-5), with the scope written in [Declared limit: `Tew` left out](#declared-limit-tew-left-out).

Acceptance test, from the repository root:

```bash
python -m pytest engine/water/evaporation/
```

Identifiers such as C3.2 refer to `contracts/CONVENTIONS.md`; G1 to G7 to `contracts/ENTRYPOINTS.md`; D34, D44, D46, D56, D77, D78, D82 to decisions on issue #77.

## Declared limit: `Tew` left out

Decision D82 of issue #77, PC-5 of `docs/SCIENCE_DECISIONS.md` (finding 6 of the AI pre-check, F52; recorded in M2.2 of `docs/METHODS.md`). The pre-check reports that the balance of the surface layer in FAO-56 chapter 7, Eq. 77, carries `Tew`, the transpiration drawn from the exposed and wetted fraction of the surface layer, and that the manual allows leaving it out in some cases. The daily step of this folder has no `Tew` term. The lead developer chose to keep it that way and to **declare the omission as a limit of the method**, with this scope:

- **What is left out.** The depletion of the surface layer (`depletion_start`, `depletion_end`) is not raised by any transpiration of the crop. The transpiration of the crop is still taken, as before, from the root-zone column of `engine/water/balance/`; only the account of the surface layer leaves it out. No input, constant or output of this folder carries `Tew`.
- **Rain-fed.** The balance has no irrigation term (D44): the water entering the surface layer is the precipitation less the runoff.
- **Where it weighs most.** With the 0.10 m evaporation layer of D77 (USER-AG) and the shallow roots of the early season (D78), the surface layer is a large share of the early root zone. That is where a crop draws most of its water from the surface layer, and so where leaving `Tew` out weighs most.
- **Which way it goes (PROPOSED, read from the forms, not measured).** On a day the crop would transpire from the surface layer, leaving `Tew` out keeps the depletion lower than Eq. 77 would. `Kr` never rises with the depletion (R4 and the case `reduction-coefficient-falls-linearly-to-zero-in-stage-two`), so `Kr`, and the evaporation asked of the layer, stay at or above what Eq. 77 would give. No size of the effect is claimed.
- **Applies to** every day of every rotation. On a day with no crop there is no transpiration to leave out. Because it weighs most while roots are shallow, it need not weigh the same in every rotation; whether it changes a comparison is not tested (OPEN 4).

The cases in which FAO-56 allows the omission are not transcribed here (OPEN 4).

## Files

| File | What it holds |
|---|---|
| `__init__.py` | Exports the public names below |
| `surface_layer.py` | The intermediate quantities, `step`, `run_surface_layer`, and the records `DayInput`, `DayResult`, `UpperLimitClimateConstants` |
| `test_surface_layer.py` | The PROPOSED cases below |

The only contract model used is `Missing`, imported as `contracts.results.models.Missing`, the class `engine/water/balance/` uses. No new missing shape is defined.

## Functions

Each function returns a number, or a `Missing` with its reason (C3.1). All are pure (G1): no file, no network, no clock, no global state; they do not change their arguments.

| Function | Quantity | Form (PROPOSED) | FAO-56 equation |
|---|---|---|---|
| `total_evaporable_water` | Total evaporable water `TEW` of the surface layer | `unit_factor · (θFC − wilting_point_weight · θWP) · Ze` | OPEN |
| `evaporation_reduction_coefficient` | Reduction coefficient `Kr` from the depletion `De` | one while `De ≤ REW` (stage 1); `(TEW − De) / (TEW − REW)` beyond (stage 2) | OPEN |
| `climate_adjusted_upper_limit` | Climate term of the upper limit of the crop coefficient | `base + [wind_coefficient · (u2 − reference_wind_speed) − humidity_coefficient · (RHmin − reference_minimum_relative_humidity)] · (h / reference_crop_height) ^ height_exponent` | OPEN |
| `upper_limit_of_crop_coefficient` | Upper limit `Kc_max` | `max(climate term, Kcb + margin_above_basal)` | OPEN |
| `cover_fraction_from_basal_coefficient` | Cover fraction `fc` from `Kcb`, when it is not observed | `((Kcb − Kc_min) / (Kc_max − Kc_min)) ^ exponent` | OPEN |
| `exposed_and_wetted_fraction` | Exposed and wetted fraction `few` | `min(1 − fc, fw)` | OPEN |
| `evaporation_coefficient` | `Ke` | `min(Kr · (Kc_max − Kcb), few · Kc_max)` | OPEN |
| `step` | One day of the surface-layer balance | rules R1 to R6 below | OPEN |
| `run_surface_layer` | `step` over consecutive days, never resetting the depletion | | |

```text
step(depletion_start, day, *, total_evaporable_water, readily_evaporable_water,
     wetted_fraction, margin_above_basal) -> DayResult
run_surface_layer(days, *, initial_depletion, total_evaporable_water,
     readily_evaporable_water, wetted_fraction, margin_above_basal) -> list[DayResult]
```

### Inputs of a day (`DayInput`)

None has a default, also on a day with no crop.

| Field | What it is |
|---|---|
| `date` | The day (C5.2); `run_surface_layer` requires consecutive dates |
| `precipitation`, `runoff` | Depths of water over the day. Runoff is an input (engine/water/runoff/ is another unit). No irrigation: rain-fed |
| `reference_evapotranspiration` | Depth of water over the day, from engine/water/et0/ |
| `basal_crop_coefficient` | `Kcb` of the day, including a day with no crop |
| `cover_fraction` | `fc` of the day, between zero and one, including a day with no crop; observed or from `cover_fraction_from_basal_coefficient` |
| `climate_adjusted_upper_limit` | The climate term of the day, from `climate_adjusted_upper_limit` |

Each is a number or a `Missing`. Depths of water share one unit chosen by the caller; the module converts nothing and holds no unit string.

### Output of a day (`DayResult`)

`depletion_start`, `depletion_end`, `precipitation`, `runoff`, `infiltration`, `deep_percolation`, `reduction_coefficient`, `upper_limit`, `exposed_and_wetted_fraction`, `evaporation_coefficient` (`Ke`, for the balance), `evaporation_demanded` (`Ke · ET0`), `evaporation` (supplied, over the whole field), `evaporation_from_exposed_fraction` (the same water as a depth over `few`), `evaporation_shortfall`, `runoff_shortfall`. Every quantity is a number or a `Missing` with its reason.

## PROPOSED rules

Each rule is PROPOSED. R1 restates the brief of #149 and D44; the others are choices of this session that a person accepts or corrects.

| Rule | Statement |
|---|---|
| R1 | Mass closure of the surface layer every day, in depletion form: `De_end − De_start = −(P − RO) + DPe + E / few` |
| R2 | The depletion stays between zero and `TEW` and is never clipped. Evaporation that asks for more than the layer holds is limited (the layer ends at exactly `TEW`) and the part not supplied is `evaporation_shortfall`. Runoff above the precipitation of the day is limited to it and the difference is `runoff_shortfall`, as R6 of `engine/water/balance/` does |
| R3 | Order within a day: runoff leaves from the precipitation; the rest infiltrates and refills the layer; what exceeds the depletion at the start of the day passes below the layer (`DPe`); then evaporation is taken from the exposed and wetted fraction |
| R4 | `Kr` follows the depletion at the **start** of the day, before that day's rain. See OPEN 3 |
| R5 | When `few` is zero, `Ke` is zero by its form, nothing is demanded and the depletion does not change by evaporation |
| R6 | A missing input of a day, a missing constant, or a missing depletion at the start makes every quantity of that day missing with reason `MISSING_INPUT` and a detail naming each missing operand and its own reason (C3.3). The depletion of later days is then unknown, so every later day is missing too, with a detail naming the first cause. Nothing is filled in (C3.4 is not decided) |
| R7 | Caller defects raise: `TypeError` for a wrong type (a boolean is not a number); `ValueError` for a non-finite number, a negative depth or coefficient, `TEW` of zero, `REW` above `TEW`, a fraction above one, a depletion outside zero to `TEW`, a reference crop height of zero, or days that are not consecutive. A missing value never raises |
| R8 | The intermediate functions do not clip. A result with no finite real value, a `TEW` below zero, or a cover-fraction ratio outside zero to one gives `NOT_COMPUTABLE` (C3.2) with a detail. How the method treats those cases is OPEN 6 |

## Constants a person has to transcribe

One row per constant. The value is empty: a person transcribes it from FAO-56 chapter 7 with its reference, locator, verbatim text and date read, and a second person checks it (D34). Units follow the unit the caller's depths and climate quantities are in; where the method writes its own unit, the person records it.

| Proposed identifier | What it is | Unit | FAO-56 equation | Value |
|---|---|---|---|---|
| `surface_layer_depth` | Depth of the surface soil layer that dries by evaporation (`Ze`) | length | OPEN | |
| `wilting_point_weight` | Weight of the wilting-point water content in the total evaporable water | none | OPEN | |
| `unit_factor` | Factor that turns a water content times a depth into a depth of water | depth of water per length | OPEN | |
| `total_evaporable_water` | Total evaporable water `TEW`, when supplied directly rather than computed | depth of water | OPEN | |
| `readily_evaporable_water` | Readily evaporable water `REW`, the end of stage 1 | depth of water | OPEN | |
| `upper_limit.base` | The term the climate adjustment of `Kc_max` is added to | none | OPEN | |
| `upper_limit.wind_coefficient` | Weight of the wind speed at 2 m in the adjustment | per wind speed | OPEN | |
| `upper_limit.reference_wind_speed` | Wind speed at which the wind term is zero | wind speed | OPEN | |
| `upper_limit.humidity_coefficient` | Weight of the minimum relative humidity in the adjustment | per percent | OPEN | |
| `upper_limit.reference_minimum_relative_humidity` | Minimum relative humidity at which the humidity term is zero | percent | OPEN | |
| `upper_limit.reference_crop_height` | Crop height the adjustment is scaled by | length | OPEN | |
| `upper_limit.height_exponent` | Exponent of the crop-height scaling | none | OPEN | |
| `margin_above_basal` | Amount `Kc_max` lies at least above `Kcb` | none | OPEN | |
| `minimum_crop_coefficient` | `Kc_min`, the coefficient of dry bare soil in the cover-fraction equation | none | OPEN | |
| `cover_fraction_exponent` | Exponent of the cover-fraction equation (the method writes it from the crop height; how is OPEN 5) | none | OPEN | |
| `wetted_fraction` | `fw`, the fraction of the surface wetted by precipitation | none | OPEN | |

## PROPOSED cases

The identifier of a case is the name of its test function without `test_`, with hyphens. Every input is a PLACEHOLDER. Tolerances are floating-point rounding only (a small multiple of machine epsilon times the size of the terms); they are not a tolerance of the method.

### Intermediate quantities

| Case | What is checked |
|---|---|
| `total-evaporable-water-follows-its-form` | The PROPOSED form, with placeholders |
| `total-evaporable-water-below-zero-is-not-computable` | A weighted wilting point above field capacity gives `NOT_COMPUTABLE` |
| `total-evaporable-water-names-missing-operands` | Missing input and constant, each named with its reason |
| `reduction-coefficient-is-one-in-stage-one` | `Kr = 1` from zero depletion up to `REW` included |
| `reduction-coefficient-falls-linearly-to-zero-in-stage-two` | The linear form beyond `REW`, zero at `TEW`, bounded, never rising with depletion |
| `reduction-coefficient-with-equal-evaporable-waters-stays-in-stage-one` | `REW = TEW` gives no division by zero |
| `reduction-coefficient-rejects-caller-defects` | Depletion above `TEW`, `REW` above `TEW`, `TEW` of zero |
| `reduction-coefficient-missing-operand-is-missing` | Named with reasons |
| `climate-term-of-the-upper-limit-follows-its-form` | The PROPOSED form, with placeholders |
| `climate-term-names-a-missing-constant` | A missing constant is named |
| `climate-term-with-no-finite-value-is-not-computable` | Zero height with a negative exponent |
| `climate-term-rejects-caller-defects` | Zero reference height, wrong constants type, negative wind |
| `upper-limit-is-the-larger-of-climate-term-and-basal-plus-margin` | Both branches; never below `Kcb` |
| `upper-limit-missing-operand-is-missing` | Named with its reason |
| `cover-fraction-follows-its-form` | The PROPOSED form, with placeholders |
| `cover-fraction-outside-its-domain-is-not-computable` | Ratio below zero, above one, equal limits |
| `cover-fraction-missing-exponent-is-missing` | Named |
| `exposed-and-wetted-fraction-is-the-smaller-of-exposed-and-wetted` | Both branches, full cover, defects, missing |
| `evaporation-coefficient-is-the-smaller-of-its-two-limits` | Both branches, full cover gives zero, `Kc_max` below `Kcb` raises, missing |

### The daily step and its bounds

| Case | What is checked |
|---|---|
| `the-daily-step-combines-the-intermediate-quantities` | `step` gives the values of the intermediate functions and the depletion they imply |
| `rain-refills-the-layer-and-the-excess-passes-below-it` | Deep percolation is the infiltration above the depletion; the layer ends full |
| `runoff-above-the-precipitation-is-limited-and-recorded` | Runoff limited to the precipitation; shortfall recorded; the layer is unchanged |
| `the-reduction-coefficient-follows-the-depletion-at-the-start-of-the-day` | R4 |
| `evaporation-asking-more-than-the-layer-holds-is-limited-and-recorded` | The layer ends at exactly `TEW`; supplied plus shortfall is the demand |
| `a-demand-that-nearly-fills-the-layer-never-ends-above-it` | Regression found by the verifier of #151: a demand that nearly fills the room left once ended one rounding step above `TEW`, and the next day raised. The depletion stays within `TEW`, the shortfall is not negative, and supplied never exceeds demanded |
| `demands-near-the-room-left-keep-every-bound` | Randomized: the first day's demand is set within a few rounding steps of the room left; bounds, shortfall and closure hold on both days |
| `evaporation-supplied-in-full-has-no-shortfall` | Shortfalls are zero |
| `full-cover-evaporates-nothing-and-keeps-the-depletion` | R5 |
| `mass-closure-every-day-on-a-long-series` | R1 every day of three twenty-year PLACEHOLDER series, from an empty and a full layer |
| `the-long-series-reaches-every-branch-of-the-step` | That series has deep percolation, limited evaporation, limited runoff, full cover, stage 1, stage 2 and a full depletion |
| `depletion-never-below-zero-nor-above-total-evaporable-water` | Bounds, flows not negative, supplied plus shortfall is the demand, every day |
| `the-depletion-is-carried-from-day-to-day-and-never-reset` | Two runs chained by their depletion give exactly one run |

### Stages of drying (structure only)

| Case | What is checked |
|---|---|
| `drying-goes-through-stage-one-then-stage-two` | On dry days with constant demand: stage 1 first, with `Kr = 1` and constant evaporation; then stage 2, with `Kr` and evaporation never rising; no return; never above `TEW` |
| `rain-after-stage-two-returns-the-layer-to-stage-one` | A storm refills the layer and the next day is in stage 1 |

### Missing in, missing out; a day with no crop

| Case | What is checked |
|---|---|
| `a-missing-input-gives-missing-outputs-that-day-and-after` | For each of the six daily inputs: that day and every later day wholly missing, `MISSING_INPUT`, naming the input, its reason and the date; earlier days untouched; no day dropped |
| `a-missing-constant-gives-every-day-missing` | Named with its reason |
| `a-missing-initial-depletion-gives-every-day-missing` | Named with its reason |
| `missing-is-never-zero` | No missing quantity is a number |
| `a-day-with-no-crop-takes-its-basal-coefficient-and-cover-as-inputs` | The result follows the `Kcb` and `fc` the caller gives for that day; closure holds |
| `no-input-or-constant-has-a-default` | No field of `DayInput` or `UpperLimitClimateConstants`, and no parameter of a public function, has a default |

### Integration with `engine/water/balance/`

| Case | What is checked |
|---|---|
| `the-result-is-the-evaporation-coefficient-of-the-balance-day-input` | A `DayInput` of the balance built with `evaporation_coefficient = Ke` runs, and its demanded evaporation is `Ke · ET0`. `balance/` is not changed |
| `a-missing-result-passes-to-the-balance-as-missing` | A missing `Ke` makes the balance day missing, naming it |

### Caller defects, purity, no values

| Case | What is checked |
|---|---|
| `invalid-constants-raise-value-error` | `TEW` zero, negative or infinite; `REW` above `TEW`; `fw` above one; negative margin |
| `initial-depletion-outside-the-layer-raises-value-error` | Negative or above `TEW` |
| `invalid-day-raises` | Negative precipitation, cover above one, a text or a boolean for a number, a value that is not a day |
| `days-that-are-not-consecutive-raise-value-error` | A gap, a step back, a repeated day |
| `an-empty-sequence-gives-no-days` | No day in, no day out |
| `same-arguments-give-the-same-result-and-are-not-changed` | G1 |
| `the-module-holds-no-number-other-than-zero-and-one` | `surface_layer.py` holds no constant of the method |

### Skipped, waiting for people

| Case | What it waits for |
|---|---|
| `fao56-chapter-7-worked-example` | The worked example of FAO-56 chapter 7 on soil evaporation (example number OPEN): its inputs, intermediate results (`Kr`, `Kc_max`, `few`, `Ke`, the depletion of each day), final value and tolerance, transcribed from the manual with reference, locator, verbatim text and date read, and checked by a person (D34) |

## OPEN

Each question names the role that answers it.

1. **The forms and their source.** Every form in the table of functions, and the equation numbers, are to be checked against FAO-56 chapter 7 and cited (CITATION NEEDED). *Science reviewers; lead developer (D44).*
2. **Which `Ke` goes to the balance when the surface layer runs short.** `evaporation_coefficient` is `Ke` of the method. On a day with `evaporation_shortfall > 0` the balance, taking that `Ke`, asks for `Ke · ET0`, more than the surface layer supplied, and takes it from the whole column. Pass `Ke` as here, pass `evaporation / ET0` (undefined when `ET0` is zero), or have the balance take the evaporation itself? This changes `balance/` or EP3, out of this unit. *Lead developer; science reviewers.*
3. **Order within a day (R3) and the depletion `Kr` follows (R4).** Here `Kr` uses the depletion before the day's rain, so a storm on a dry day does not raise that day's `Kr`. *Science reviewers.*
4. **Transpiration from the surface layer.** Decided by D82 (PC-5): `Tew` is left out and the omission is a declared limit ([Declared limit: `Tew` left out](#declared-limit-tew-left-out)). Still open: the cases in which FAO-56 allows the omission, read at the locator of Eq. 77 and checked by a person (D34); whether the full Eq. 77 is built later (the other option of finding 6), which would need the transpiration split between the surface layer and the rest of the root zone, and so a change to `balance/` or EP3; and whether the omission changes a comparison of rotations, for instance in a sensitivity run. *Science reviewers; lead developer.*
5. **How the cover-fraction exponent follows the crop height**, and whether `fc` comes observed or from `Kcb`. The caller supplies the exponent and the cover fraction. *Science reviewers; lead developer.*
6. **Limits the method may set** on `fc`, on `1 − fc`, on a `Kcb` below `Kc_min`, or on `TEW` (R8). The module clips nothing and reports `NOT_COMPUTABLE` instead. *Science reviewers.*
7. **Where the minimum relative humidity, crop height and wind speed of the climate term come from.** `contracts/CLIMATE_QUANTITIES.md` carries the dew point and air temperatures, not a minimum relative humidity; the crop height of a day is not in the calendar. *Lead developer; platform developer; science reviewers.*
8. **Which soil properties give `TEW`, `REW` and `Ze`** (D49 covers the available water of the root zone, not the surface layer), how they arrive (D46 and D56 wait for the platform developer's approval in #144), and in which units. *Lead developer; platform developer (D46); science reviewers.*
9. **The initial depletion.** `initial_depletion` has no default; which states to start from and compare is not decided, as for the balance's initial storage. *Science reviewers.*
10. **Gaps in a daily series.** R6 stops the balance at the first missing day; whether it may restart and from which state is not decided (C3.4). *Science reviewers.*
11. **Runoff above the precipitation (R2).** Mirrors R6 of `balance/`; with the Curve Number unit runoff comes from precipitation and the case may not arise. *Science reviewers.*
12. **The fallback of D44.** When the surface-layer values do not arrive, D44 says the engine falls back to the single coefficient and one layer and says so in the result. How the caller detects that from the missing constants here, and what `Ke` becomes, is not decided. *Lead developer; science reviewers.*

## Not in this unit

The basal crop coefficients and their curve by stage (`Kcb` is a daily input); runoff (`engine/water/runoff/`); changing the balance or EP3, and the transpiration split inside the balance; several layers below the surface; reading the parameter catalogue (D46, D56).
