# Cover-management factor `C` from its sub-factors

Unit `l0/erosion-c-subfactors`, brief in issue #157. Status: `PROPOSED` (blueprint section 3.7): it takes effect only when a person approves the pull request.

`docs/METHODS.md` M1.5, with decision D45 of issue #77: the soil-loss ratio of a period comes from two sub-factors of source S1, **canopy cover** and **surface residue cover with residue decay by residue type**. The other sub-factors of S1 (surface roughness, soil biomass, soil consolidation, prior land use) are set to one as a declared limit of the method. `C` for a rotation weights the soil-loss ratio of each month by the fraction of annual erosivity of the month.

This folder builds those pieces as pure functions, so that a later unit can compute `C` for each period instead of taking it as a value from the parameter catalogue. It is not an entry point of `contracts/ENTRYPOINTS.md`, it does not read the parameter catalogue (that belongs to EP1, issue #154), and it does not change EP1.

## The forms

Every form is `PROPOSED`. **Its source is to be confirmed by a person against S1.** The session that wrote this unit did not read S1 and wrote no number of S1 anywhere: not in the code, a default, a test, a comment or this file.

| Function | Form | Module |
|---|---|---|
| `canopy_subfactor` | `CC = 1 - canopy_cover * exp(-fall_height_coefficient * fall_height)` | `subfactors.py` |
| `surface_cover_subfactor` | `SC = exp(-surface_cover_coefficient * surface_residue_cover)` | `subfactors.py` |
| `soil_loss_ratio` | `SLR = CC * SC`; the four other sub-factors stand at one and are named in the result | `subfactors.py` |
| `residue_cover_from_mass` | `cover = 1 - exp(-mass_cover_coefficient * residue_mass)` | `residue.py` |
| `residue_mass_after_decay` | `mass_after = residue_mass * exp(-decay_coefficients[residue_type] * elapsed_time)` | `residue.py` |
| `residue_mass_over_time` | the decay step applied step after step, one mass per step | `residue.py` |
| `rotation_c` | `C = sum over months of (erosivity_fraction * SLR) / number_of_years` (M1.5) | `rotation.py` |

`canopy_cover` and `surface_residue_cover` are fractions of the soil, zero to one. `fall_height` is the height from which drops fall from the canopy.

## Signatures

Every argument is passed by name and none has a default. A number argument is a number or a `Missing` of the contract models (either shape, `contracts.inputs.common.Missing` or `contracts.results.models.Missing`); a result that is not computed is always the `Missing` of `contracts/results/models.py`.

```python
canopy_subfactor(*, canopy_cover, fall_height, fall_height_unit,
                 fall_height_coefficient, fall_height_coefficient_per_unit) -> float | Missing
surface_cover_subfactor(*, surface_residue_cover, surface_cover_coefficient) -> float | Missing
soil_loss_ratio(*, canopy, surface_cover) -> SoilLossRatio
residue_cover_from_mass(*, residue_mass, residue_mass_unit,
                        mass_cover_coefficient, mass_cover_coefficient_per_unit) -> float | Missing
residue_mass_after_decay(*, residue_mass, residue_type, decay_coefficients,
                         decay_coefficient_per_unit, elapsed_time, elapsed_time_unit) -> float | Missing
residue_mass_over_time(*, initial_residue_mass, residue_type, decay_coefficients,
                       decay_coefficient_per_unit, step_durations, elapsed_time_unit) -> tuple[float, ...] | Missing
rotation_c(*, months, number_of_years, fraction_sum_tolerance) -> RotationC
```

- `SoilLossRatio`: `value` (the product, or `Missing`), `canopy` and `surface_cover` (as passed in), `set_to_one` (always the four sub-factors of D45: `surface_roughness`, `soil_biomass`, `soil_consolidation`, `prior_land_use`) and `limit` (where the limit is declared: D45, M1.5). The limit travels also when `value` is missing.
- `MonthOfRotation`: `label` (text, used only to name the month in a detail), `erosivity_fraction`, `soil_loss_ratio` (a `SoilLossRatio`).
- `RotationC`: `value` (`C`, or `Missing`), `fraction_sum`, `expected_fraction_sum` (the number of years), `fractions_add_up` (`True`, `False`, or `Missing`), `set_to_one` and `limit`.
- `decay_coefficients` maps a residue type (text) to its coefficient. All coefficients of one mapping share one time unit, `decay_coefficient_per_unit`.

## Units

The functions convert no unit. Where a constant multiplies an input that has a unit, the caller states both unit strings and they must be the same text, as in `engine/erosion/ls.py`:

| Function | Unit string of the input | Must equal |
|---|---|---|
| `canopy_subfactor` | `fall_height_unit` | `fall_height_coefficient_per_unit`: the length whose inverse is the unit of the coefficient |
| `residue_cover_from_mass` | `residue_mass_unit` | `mass_cover_coefficient_per_unit`: the mass-per-area unit whose inverse is the unit of the coefficient |
| `residue_mass_after_decay`, `residue_mass_over_time` | `elapsed_time_unit` | `decay_coefficient_per_unit`: the time unit whose inverse is the unit of every coefficient |

When they differ the result is `NOT_COMPUTABLE` (the reason code of a unit that is not accepted is Q11 of `contracts/ENTRYPOINTS.md`, OPEN; the same choice as `ls.py`), and the detail names both.

## When a result is not computed

In this order; the first that applies is returned. Nothing is clipped, filled, normalised or replaced by zero.

1. **`MISSING_INPUT`**: an argument is missing. The detail names every missing argument, with its own reason code and detail (C3.3). For decay, a residue type that `decay_coefficients` does not hold is missing and named; so is a coefficient held as a `Missing`. For `rotation_c`, every month whose fraction or ratio is missing is named by position and label.
2. **`NOT_COMPUTABLE`**: an argument is not a finite number ("not a number", an infinity, an integer too large for a float); then an argument outside what the quantity can be: a cover fraction or an erosivity fraction outside zero to one, a negative fall height or residue mass, a negative `fall_height_coefficient`, `surface_cover_coefficient` or `mass_cover_coefficient` (PROPOSED: each would put a sub-factor or the cover outside zero to one), and for decay a negative elapsed time or decay coefficient (each of which would add mass); then unit strings that differ; then a form that gives no finite real number (an overflow).
3. `rotation_c` only: no month, or a number of years not above zero, is `NOT_COMPUTABLE`. An erosivity fraction outside zero to one makes both `value` and `fraction_sum` `NOT_COMPUTABLE`, naming every such month.

A `TypeError` is raised for an argument of another type (`None`, text, a boolean, a list in place of a number), so a `None` is never read as a value.

`rotation_c` never normalises the fractions. It computes `C` from them as given, and reports `fraction_sum`, `expected_fraction_sum` and `fractions_add_up` (whether the two differ by no more than `fraction_sum_tolerance`). A missing or negative tolerance withholds only `fractions_add_up`; `C` does not need it.

## Constants a person has to transcribe

One row per constant. A person fills the parameter catalogue (`params/records/`) from this table and signs `transcribed_by`; a second person checks each value against S1 and signs `checked_by` (D34 of issue #77, `params/README.md`). **The column "Value" stays empty: a session writes no value.** The identifiers are `PROPOSED`.

| Constant | Proposed parameter identifier | What it is | Unit | Equation of S1 | Value |
|---|---|---|---|---|---|
| `fall_height_coefficient` | `rusle2_canopy_fall_height_coefficient` | Multiplies the fall height in the exponent of the canopy sub-factor | One over a length, the length stated as `fall_height_coefficient_per_unit` | OPEN: the session did not read S1 | |
| `surface_cover_coefficient` | `rusle2_surface_cover_coefficient` | Multiplies the surface residue cover (a fraction) in the exponent of the surface-cover sub-factor | None if the cover is a fraction; OPEN 3 if S1 writes the cover in percent | OPEN: the session did not read S1 | |
| `mass_cover_coefficient` | `rusle2_residue_mass_cover_coefficient` | Multiplies the residue mass in the exponent of the mass-cover relation | One over a mass per area, the unit stated as `mass_cover_coefficient_per_unit` | OPEN: the session did not read S1 | |
| `decay_coefficients` | `rusle2_residue_decay_coefficient` | The decay coefficient of one residue type: one record per residue type, told apart by its scope (OPEN 5) | One over a time, the time stated as `decay_coefficient_per_unit` | OPEN: the session did not read S1 | |

Not a constant of S1, and so not in this table: `fraction_sum_tolerance` of `rotation_c` (OPEN 9).

## PROPOSED cases

Each case is a test function of `test_c_factor.py`; a test checks that this list and the file agree. Every constant in the tests is a PLACEHOLDER (repeated digits, or zero and one where the arithmetic is done by hand). No case holds an expected value of the science.

### Each sub-factor

| Case | What it shows |
|---|---|
| `test_canopy_subfactor_follows_the_proposed_form` | `CC` equals the form written a second time in the test, over a grid of covers and heights |
| `test_canopy_subfactor_is_one_without_canopy` | With no canopy, `CC` is exactly one, for any height and coefficient |
| `test_more_canopy_cover_never_raises_the_canopy_subfactor` | Over a grid of covers, `CC` never rises as the canopy cover grows |
| `test_surface_cover_subfactor_follows_the_proposed_form` | `SC` equals the form written a second time in the test |
| `test_surface_cover_subfactor_is_one_without_residue` | With no residue cover, `SC` is exactly one, for any coefficient |
| `test_more_residue_cover_never_raises_the_surface_cover_subfactor` | Over a grid of covers, `SC` never rises as the residue cover grows |

### Soil-loss ratio

| Case | What it shows |
|---|---|
| `test_soil_loss_ratio_is_the_product_of_its_subfactors` | `value` is `CC * SC`; the two sub-factors are kept in the result |
| `test_soil_loss_ratio_records_the_subfactors_set_to_one` | `set_to_one` names the four sub-factors of D45 and `limit` names D45, also when `value` is missing |
| `test_more_canopy_or_residue_never_raises_the_soil_loss_ratio` | Through both sub-factors, more canopy or more residue cover never raises the ratio (PLACEHOLDER constants) |

### Mass-cover relation and decay

| Case | What it shows |
|---|---|
| `test_residue_cover_follows_the_proposed_form` | The cover equals the form written a second time in the test |
| `test_residue_cover_is_zero_without_residue_and_grows_with_mass` | No mass gives no cover; more mass never gives less cover; the cover stays within zero to one |
| `test_decay_step_follows_the_proposed_form` | The decayed mass equals the form written a second time in the test |
| `test_decay_never_adds_mass_and_never_makes_it_negative` | Over a grid of masses, times and coefficients, the mass after a step is between zero and the mass before |
| `test_decay_chooses_the_coefficient_of_the_residue_type` | Two residue types give two masses; the coefficient of another type does not move the result |
| `test_residue_type_without_decay_coefficient_gives_missing_that_names_it` | A residue type the mapping does not hold, or holds as a `Missing`, gives `MISSING_INPUT` naming the type; also over time; both `Missing` shapes |
| `test_negative_decay_coefficient_or_elapsed_time_is_refused` | Either would add mass: `NOT_COMPUTABLE`, naming it |
| `test_mass_over_time_equals_steps_applied_one_after_another` | The series equals the step function applied in turn, and never rises |
| `test_mass_over_time_missing_step_makes_the_series_missing_and_names_the_step` | A missing or negative step length makes the whole series missing, naming the step |
| `test_mass_over_time_without_steps_checks_the_initial_mass` | No step gives an empty series, but a missing or negative initial mass is still reported |

### Rotation `C`

| Case | What it shows |
|---|---|
| `test_rotation_c_weights_each_month_by_its_erosivity_fraction` | `C` is worked out by hand from the fractions and ratios; moving erosivity to the month with the higher ratio raises `C`; a month with no erosivity does not count |
| `test_rotation_c_divides_by_the_number_of_years` | Over two years, `C` is the sum divided by two, and fractions that add up to two are reported as adding up |
| `test_rotation_c_missing_fraction_or_ratio_gives_missing_never_zero` | A missing fraction, ratio or number of years makes `C` `MISSING_INPUT`, naming the part and the month; both `Missing` shapes |
| `test_rotation_c_reports_fractions_that_do_not_add_up_without_normalising` | Fractions that do not add up to the number of years are reported (`fractions_add_up` is `False`, the sum is given) and `C` is computed from them as given, not normalised |
| `test_rotation_c_fractions_that_add_up_within_the_tolerance_are_reported_as_such` | A sum within the PLACEHOLDER tolerance on either side adds up; beyond it, it does not; with a tolerance of zero an exact sum adds up |
| `test_rotation_c_erosivity_fraction_outside_zero_to_one_is_not_computed` | A fraction below zero or above one (-0.4, 1.4, or by a hair) makes `C` and `fraction_sum` `NOT_COMPUTABLE`, naming that month and no other; also when the fractions add up; zero and one are accepted |
| `test_rotation_c_records_the_subfactors_set_to_one` | The result names the four sub-factors of D45 and the limit |
| `test_rotation_c_without_months_or_with_no_years_is_not_computed` | No month, or zero or fewer years: `NOT_COMPUTABLE` |
| `test_rotation_c_missing_tolerance_leaves_c_and_withholds_only_the_check` | A missing or negative tolerance withholds `fractions_add_up` only |

### Arguments outside what a quantity can be

| Case | What it shows |
|---|---|
| `test_cover_fraction_outside_zero_to_one_is_not_computed` | A canopy or residue cover below zero or above one, even by a hair, is `NOT_COMPUTABLE` naming it; zero and one are accepted |
| `test_negative_mass_or_height_is_not_computed` | A negative fall height or residue mass is `NOT_COMPUTABLE` naming it, in every function that takes one |
| `test_negative_coefficient_is_refused_and_named` | A negative `fall_height_coefficient`, `surface_cover_coefficient` or `mass_cover_coefficient`, even by a hair, is `NOT_COMPUTABLE` naming it; zero is accepted (PROPOSED) |
| `test_with_coefficients_not_negative_each_result_stays_within_zero_to_one` | With coefficients that are not negative, `CC`, `SC` and the residue cover stay within zero to one over a grid of inputs |
| `test_argument_that_is_not_finite_is_not_computed` | "Not a number", an infinity or an integer too large for a float, as any number argument of any function: `NOT_COMPUTABLE` naming it |
| `test_months_and_years_that_are_not_finite_are_not_computed` | The same for a month's fraction, a ratio built by hand, the number of years and a decay coefficient. A ratio that is not finite and passed through `soil_loss_ratio` arrives missing, so `C` is `MISSING_INPUT` naming the month |
| `test_missing_argument_gives_missing_input_that_names_it` | A missing number argument of any function gives `MISSING_INPUT`, naming it with its reason; both `Missing` shapes |
| `test_units_that_differ_are_not_computed` | Each pair of unit strings that must agree: `NOT_COMPUTABLE` naming both |
| `test_form_without_a_finite_result_is_not_computed` | Finite arguments whose product (soil-loss ratio) or sum (rotation `C`) overflows: `NOT_COMPUTABLE`, nothing raised. With coefficients that are not negative the three exponential forms cannot overflow |
| `test_argument_of_another_type_raises_type_error` | `None`, text, a boolean or a list as a number argument raises `TypeError` naming it |
| `test_structured_argument_of_another_type_raises_type_error` | The same for the mapping, the residue type, the steps, the months, the ratio of a month, the number of years and a unit string |

### No constant of the method

| Case | What it shows |
|---|---|
| `test_every_argument_is_passed_by_name_and_none_has_a_default` | Every public function takes keyword arguments only, without a default |
| `test_the_modules_hold_no_number_but_zero_and_one` | The modules of this folder write no number but zero and one (the bounds of a fraction and the `1 -` of two forms) |
| `test_readme_lists_every_constant_with_an_empty_value` | The table of constants has one row per constant, a well-formed and distinct identifier, and an empty value |
| `test_readme_lists_the_cases_of_this_file` | This list and `test_c_factor.py` name the same cases |

### Waiting for a person

Each is **skipped**, and its skip reason says what it waits for: the constants as records of the parameter catalogue, and the inputs, published result and tolerance of a worked example of S1, transcribed by a person and checked by a second person (D34).

| Case | What it shows |
|---|---|
| `test_s1_worked_example_of_the_canopy_subfactor` | The canopy sub-factor against a worked example of S1 |
| `test_s1_worked_example_of_the_surface_cover_subfactor` | The surface-cover sub-factor against a worked example of S1 |
| `test_s1_worked_example_of_the_mass_cover_relation` | The mass-cover relation against a worked example of S1 |
| `test_s1_worked_example_of_residue_decay` | Residue decay against a worked example of S1 |
| `test_s1_worked_example_of_rotation_c` | `C` of a rotation against a worked example of S1 |

## OPEN

Each item is a question a person has to answer; the role that answers it is named. None is answered by this unit.

1. **Are the forms the ones of S1?** Every form above is `PROPOSED`, written without reading S1. In particular: whether the canopy sub-factor of S1 is an exponential of the fall height of this shape; whether the surface-cover sub-factor depends on the cover alone once roughness is set to one; whether the mass-cover relation and the decay are single exponentials; and the locator of each equation in S1. For the science reviewers. **AI pre-check finding (F09, F10, F12, 14 November 2026; an AI reading of the source, not a person's check under D34; details in `docs/SCIENCE_DECISIONS.md`):** S1 p. 138 (PDF 163) Eq. 6.2 takes the **effective** canopy cover, defined at p. 140 (PDF 165) Eq. 6.5 as the canopy cover times one minus the ground cover beneath it; `canopy_subfactor` takes the canopy cover itself. S1 pp. 140 to 141 (PDF 165 to 166) Eq. 6.6 has a roughness term next to the cover, with the cover in percent and the coefficient in percent to the minus one; `surface_cover_subfactor` takes a fraction and has no roughness term. A documented transformation of the inputs (an effective cover, a composite coefficient) could reconcile either form; none is documented today. The mass-cover relation (Eq. 10.1, p. 241, PDF 266) matches in form. The choice is P16 of the validation package, for the lead developer.
2. **Does S1 adjust decay for weather?** The decay step here depends on the residue type and the elapsed time only. If S1 makes the rate depend on temperature or moisture, the form changes and needs inputs this unit does not take. For the science reviewers. **AI pre-check finding (F13, F14, 14 November 2026; an AI reading of the source, not a person's check under D34; details in `docs/SCIENCE_DECISIONS.md`):** yes. S1 pp. 248 to 249 (PDF 273 to 274) Eq. 10.3 to 10.6 multiply the decay coefficient by a daily moisture and temperature factor, with a step of one day. S1 p. 250 (PDF 275) also calibrates against a daily climate disaggregated from monthly means, which is not the same forcing as the observed daily precipitation of D23: using observed days is a further choice of scope. The constant-rate form here is a simplification of S1. The choice is P17, for the lead developer.
3. **Fraction or percent?** The covers are taken as fractions, zero to one. If S1 writes a coefficient for a cover in percent, the caller converts, or the form changes. For the science reviewers. **AI pre-check finding (F10, 14 November 2026; an AI reading of the source, not a person's check under D34; details in `docs/SCIENCE_DECISIONS.md`):** S1 Eq. 6.6 writes the cover in percent and its coefficient in percent to the minus one; a published coefficient is not to be loaded as the coefficient of this form without the conversion being decided (P16).
4. **The units of each constant and input.** This unit compares unit strings and converts nothing (`docs/METHODS.md` M1.7 says the engine converts at the edge). Which unit strings the catalogue records carry is for the science reviewers; who converts, for the lead developer.
5. **Which constants depend on the residue type or the crop?** Only the decay coefficient is chosen by residue type here, as D45 says. If S1 makes the mass-cover coefficient depend on the residue type too, it becomes a mapping like the decay coefficients. How a record names its residue type (the scope keys of `params/README.md`) is for the lead developer; the dependence is for the science reviewers.
6. **Which values may a constant take?** PROPOSED after the review of PR #162: every constant must be zero or more. A negative decay coefficient would add mass (brief); a negative `surface_cover_coefficient` would give a surface-cover sub-factor above one, a negative `mass_cover_coefficient` a cover outside zero to one, and a negative `fall_height_coefficient` a canopy sub-factor that can fall below zero. Each is refused with `NOT_COMPUTABLE`, naming it. Still open: whether zero is a valid value, and any upper bound (a bound is a value, so a person supplies it). For the science reviewers.
7. **Which values may a sub-factor, a soil-loss ratio or an erosivity fraction take?** PROPOSED after the review of PR #162: an erosivity fraction outside zero to one is refused (`NOT_COMPUTABLE`, naming the month), with the same check as a cover fraction. Still open: `soil_loss_ratio` multiplies any two finite numbers and does not check that each sub-factor is within zero to one. With the checks above, the sub-factors computed by this folder are within zero to one; one built elsewhere is not checked. For the lead developer.
8. **What M1.5 expects of the fractions.** Read here: each year's fractions add up to one, so over the rotation they add up to the number of years. Not checked: that each year adds up to one on its own, and that the rotation has twelve months per year. For the lead developer and the science reviewers.
9. **The tolerance of the fraction sum, and what follows when the fractions do not add up.** The tolerance is an argument (no value here; not a constant of S1). Proposed: `C` is still computed and the mismatch reported, not withheld; the alternative is to make `C` `NOT_COMPUTABLE` or `CONTROL_FAILED`. For the lead developer; the tolerance itself for the science reviewers (or the test plan contract, if it is a threshold).
10. **The source of each input.** Residue cover or mass at sowing, canopy cover and fall height by stage, the residue type of each crop: OPEN in M1.5. Whether the residue mass comes from the residue ledger is Q12 of `contracts/ENTRYPOINTS.md` (EP4 is OPEN). For the lead developer and the science reviewers.
11. **Range and provenance.** The functions return bare numbers. How an uncertainty range passes through these forms is a method (C2.2); by C4.3 the label would be `DERIVED`. Proposed: the caller that builds an indicator value does it. For the science reviewers (range) and the lead developer.
12. **Reason codes.** A unit that is not accepted gets `NOT_COMPUTABLE` (Q11 of `contracts/ENTRYPOINTS.md`); so does a value outside what a quantity can be, and a non-finite number. A non-positive number of years is `NOT_COMPUTABLE`. For the lead developer.
13. **May these functions raise `TypeError`?** As in `ls.py` (OPEN 10 of `engine/erosion/LS.md`, Q7 of `contracts/ENTRYPOINTS.md`). For the platform developer.
14. **The proposed identifiers.** The table above proposes four, with the prefix `rusle2_` (S1 is the RUSLE2 science documentation) and the names of the sub-factors set to one (`SET_TO_ONE`). For the lead developer, who owns `params/`.
15. **The text on the limits of the method.** `DECLARED_LIMIT` is a pointer to D45 and M1.5, not that text; the text is the separate unit named in M1.1, written by people.
16. **Seven sub-factors, four named.** **AI pre-check finding (F11, 14 November 2026; an AI reading of the source, not a person's check under D34; details in `docs/SCIENCE_DECISIONS.md`):** S1 p. 138 (PDF 163) Eq. 6.1 multiplies **seven** daily sub-factors: canopy, ground cover, roughness, ridge height, soil biomass, soil consolidation and antecedent soil moisture. D45 keeps canopy and ground cover and names four set to one (roughness, soil biomass, consolidation, prior land use). Ridge height and antecedent moisture are not named, and prior land use is the RUSLE1 name of what S1 splits into soil biomass and consolidation. Whether the list of `SET_TO_ONE` is completed is for the lead developer; this unit does not change it.
17. **Daily integration or monthly weighting.** **AI pre-check finding (F15, 14 November 2026; an AI reading of the source, not a person's check under D34; details in `docs/SCIENCE_DECISIONS.md`):** S1 computes the sub-factors daily and integrates by summing daily values (S1 p. 9, PDF 34). `rotation_c` weights a monthly soil-loss ratio by the monthly erosivity fraction (M1.5). Decision USER-L of the lead developer accepts the classical daily route of RUSLE2 in stages, explicitly partial while components stay simplified; whether the monthly weighting is declared as such a stage, or the integration becomes daily, is for the lead developer.

## Not verified

- **The forms and every constant against S1.** The session did not read S1, by rule.
- **The worked examples of S1.** The five tests are skipped until a person transcribes them.
- **Use by the rest of the engine.** No caller exists yet: EP1 (`soil_loss.py`) still takes `C` from the catalogue, and is changed on another branch (#154) at the same time.
- **The names scan of CI.** The list of forbidden names is a secret of the repository.
- **Lint in CI.** The CI workflow runs ruff on `api/`, `adapters/` and `ci/` only; the session ran ruff on this folder.
