# Rainfall erosivity factor R by year and month

Unit `l0/erosion-r-factor` (issue #161): the factor `R` of `docs/METHODS.md` M1.2, in `engine/erosion/r_factor/`.

> **Status: PROPOSED** (blueprint section 3.7). The forms, the signatures, the handling of missing values and units, the parameter identifiers and the test cases below were written by a builder session. They take effect only when a person approves the pull request. This is a science-class change: it also needs a science reviewer. Items under [OPEN](#open) need an answer from a person.

**This unit holds no constant of the method.** Not in the code, not as a default, not in a test, not in this file. The exponent and threshold of the daily index, the coefficients of the control regression and the mean annual level of `R` are arguments without a default; the caller reads each from the parameter catalogue, where it was transcribed from its source and checked by a person (issue #77, D34). The session read none of the sources S4 to S8 and wrote no number of the method from memory. (On `main` `b8a3ea4`: `params/records/` holds `32` signed erosion and residue records out of `132` total signed records, including `rusle_r_factor` for Colonia under D83 and the twelve `rusle_r_monthly_erosivity_<month>` records under D84 and D101 since `#203`; the daily-index and control-regression constants have no records in `params/records/`.)

Acceptance test, from the repository root:

```bash
python -m pytest engine/erosion/r_factor/
```

## The forms

M1.2 builds `R` from two parts: the **mean annual level** at the field, from the published national values (S4) interpolated to the field, and the **fraction of the annual erosivity in each month and the variation between years**, from a daily erosivity index of the power-law family (S5, S6), used **in relative terms only** (S8 is the reason). The regression of `R` on monthly precipitation (S7) is the control.

Every form below is `PROPOSED`, its source to be confirmed by a person: S5 and S6 for the index, S7 as S4 gives it for the control. `P` is the daily precipitation of the series (CQ1 of `contracts/CLIMATE_QUANTITIES.md`, `mm day-1`).

```text
index(day)       = P(day) ** exponent          when P(day) >  threshold
index(day)       = 0                            when P(day) <= threshold
sum(month)       = sum of index(day) over the days of the calendar month
sum(ag_year)     = sum of sum(month) over the twelve months of the agricultural year
fraction(month)  = sum(month) / sum(ag_year of the month)
ratio(ag_year)   = sum(ag_year) / mean of sum(ag_year) over the years whose sum is a number
R(year, month)   = mean_annual_r * fraction(month) * ratio(ag_year)

control(month)   = coefficient * P(month) ** exponent      P(month): the sum of the daily P of the month
control fraction = control(month) / sum of control(month) over its agricultural year
difference       = fraction(month) - control fraction(month)          reported, never applied
```

- The index never gives the level of `R`: only its fractions and ratios are used, and the level is the input `mean_annual_r`.
- The twelve values of `R(year, month)` of a year add up to `mean_annual_r * ratio(ag_year)`; over the years where every value is defined, their annual totals average to `mean_annual_r`.
- The comparison with the control is a report. Nothing corrects a fraction of the index, and no level of agreement is judged: that would be a threshold, which a person supplies.

## Functions

Every argument is passed by name and none has a default. Each step is its own function, so a later unit (the rotation `C` of #157, EP1 of #158) can take the table it needs.

| Function | Module | Takes | Returns |
|---|---|---|---|
| `checked_daily_precipitation` | `erosivity.py` | `series: DailySeries` | `{date: float \| Missing}` or one `Missing` |
| `daily_erosivity_index` | `erosivity.py` | `series`, `exponent`, `threshold`, `threshold_unit` | `{date: float \| Missing}` or one `Missing` |
| `monthly_sums` | `erosivity.py` | `daily` (either table above) | `{(year, month): float \| Missing}` or one `Missing` |
| `annual_sums` | `erosivity.py` | `monthly`, `start_month` | `{ag_year: float \| Missing}` or one `Missing` |
| `monthly_fractions` | `erosivity.py` | `monthly`, `start_month` | `{ag_year: {(year, month): float \| Missing}}` or one `Missing` |
| `yearly_ratios` | `erosivity.py` | `annual` (what `annual_sums` returns) | `{ag_year: float \| Missing}` or one `Missing` |
| `r_by_year_and_month` | `erosivity.py` | `mean_annual_r`, `mean_annual_r_unit`, `monthly_fractions`, `yearly_ratios` | `{ag_year: {(year, month): float \| Missing}}` or one `Missing` |
| `r_factor_parts` | `erosivity.py` | `series`, `exponent`, `threshold`, `threshold_unit`, `start_month`, `mean_annual_r`, `mean_annual_r_unit` | `RFactorParts`: every table above, each kept even when a later one is missing |
| `control_monthly_erosivity` | `control.py` | `series`, `coefficient`, `exponent` | `{(year, month): float \| Missing}` or one `Missing`; pass it to `monthly_fractions` for the control fractions |
| `compare_monthly_fractions` | `control.py` | `index_fractions`, `control_fractions` | `{ag_year: {(year, month): FractionComparison}}` or one `Missing` |

- `Missing` as a result is always `contracts.results.models.Missing`. A constant may also arrive as `contracts.inputs.common.Missing`. This unit defines no `Missing` shape.
- Months are keyed by the calendar `(year, month)` (C5.1); years by the agricultural year `ag_year` they begin in (C5.3), with `start_month` the start month of the case (C5.4). `start_month=1` gives calendar years.
- Pure functions (`contracts/ENTRYPOINTS.md` G1): no file, no network, no clock, no argument changed. They do not read the parameter catalogue: the caller does. They are parts of the erosion engine, not its entry point.
- Also public: `PRECIPITATION_UNIT` (`mm day-1`, CQ1, D23), `R_UNIT` (`MJ mm ha-1 h-1 yr-1`, M1.7, D11) and `REASON_UNIT_NOT_ACCEPTED` (`NOT_COMPUTABLE`, as in `ls.py`; Q11 of `contracts/ENTRYPOINTS.md`). These are unit strings and a reason code that the repository already decided or proposed, not constants of the method.

## Units

- The series must carry the unit string `mm day-1` (CQ1). Any other unit string gives `REASON_UNIT_NOT_ACCEPTED` and nothing is converted.
- The threshold carries a unit string, which must be `mm day-1`; it is compared with the daily precipitation as given.
- The mean annual level carries a unit string, which must be `MJ mm ha-1 h-1 yr-1` (D11); otherwise `REASON_UNIT_NOT_ACCEPTED`.
- The index, its sums, the fractions and the ratios have no unit string here: they are used in relative terms only. The unit string of a monthly value of `R` and of the control is OPEN (OPEN 9).

## When a value is not computed

A value that is not computed is a `Missing` with its reason (section 3 of `contracts/CONVENTIONS.md`). Never zero, never a default, never "not a number". All `PROPOSED`.

| Situation | Result | Basis |
|---|---|---|
| A constant (exponent, threshold, coefficient, level) is a `Missing` | The whole table of that step is one `MISSING_INPUT`, naming every missing constant with its reason | C3.3 |
| A constant is not a finite number | One `NOT_COMPUTABLE`, naming it | As `ls.py` |
| The series, the threshold or the level is in another unit | One `REASON_UNIT_NOT_ACCEPTED`, naming both units | C1.1; Q11 |
| A day of the series is missing | That day is `MISSING_INPUT`, naming the date and the reason of the series. **Never zero rain** | C3.1, C3.3 |
| A day is negative or not finite | That day is `NOT_COMPUTABLE`, naming the date. Never clipped to zero | Brief of #161 |
| A month holds a missing day | The month is `MISSING_INPUT`, naming each missing day | C3.3; no gap filled until C3.4 has a method |
| A month is cut by the extent of the series | The month is `NO_COVERAGE` | By analogy with C5.5 |
| An agricultural year has a month that is absent or `NO_COVERAGE` | The year is `NO_COVERAGE`, and so are its fractions, its ratio and its values of `R` | C5.5 |
| An agricultural year has a month missing for another reason | The year is `MISSING_INPUT`, and so are its fractions, its ratio and its values of `R` | C3.3 |
| The annual sum of a year is zero (no erosive day) | Its twelve fractions are `NOT_COMPUTABLE`: not zero, not split equally. Its values of `R` are therefore missing | Brief of #161; OPEN 5 |
| The mean annual sum over the years with a sum is zero | Every ratio that would divide by it is `NOT_COMPUTABLE` | No ratio is defined |
| The level of `R` is missing | `r_by_year_and_month` is one `MISSING_INPUT` naming `mean_annual_r`; in `RFactorParts` the fractions and the ratios are still returned | Brief of #161 |
| A month of `R` or of the comparison has a missing part | `NO_COVERAGE` when every missing part is, else `MISSING_INPUT` naming each | C3.3, C5.5 |
| A step gives no finite real number (overflow, division by zero) | `NOT_COMPUTABLE`, naming the day, month or year | As `ls.py` |
| An argument of another type (`None`, text, a boolean); a start month that is not an integer from 1 to 12 | `TypeError`, or `ValueError` for the month | G5; Q7 |

### A missing day: `PROPOSED`

**A missing day makes that day, its month and its agricultural year missing.** The other months of the year keep their sums, and the other years keep their fractions, ratios and values of `R`. The mean of the yearly ratios is taken over the years whose sum is a number, so a missing year is left out of it. No gap is filled: C3.4 allows filling with a method a person chooses, and that method is still `OPEN`. This choice is OPEN 1 for the science reviewers.

## Constants a person has to transcribe

One row per constant. A person fills the parameter catalogue (`params/records/`) from this table, citing the full reference, the locator, the verbatim text and the date read, and a second person checks it against the source (issue #77, D34). **The column "Value" stays empty in this file: a session writes no value.**

The identifiers are `PROPOSED`, with the prefix `rusle_` of `LS.md`; M1.2 proposes none. `rusle_r_factor` is the identifier that EP1 (#158) proposes for `R`.

| Constant | Proposed parameter identifier | What it is | Unit | Source and equation | Value |
|---|---|---|---|---|---|
| `exponent` of `daily_erosivity_index` | `rusle_r_daily_index_exponent` | The exponent of daily precipitation in the daily erosivity index | None: it is an exponent | S5 or S6: a person says which, with the equation number. OPEN | |
| `threshold` of `daily_erosivity_index` | `rusle_r_daily_index_threshold` | The daily precipitation at or below which a day adds nothing to the index | `mm day-1`, the unit of the series | S5 or S6: a person says which, with the equation number. OPEN | |
| `coefficient` of `control_monthly_erosivity` | `rusle_r_monthly_control_coefficient` | Multiplies the power of monthly precipitation in the control regression | OPEN: the unit of the control (OPEN 9) | S7 as S4 gives it, with the equation number. OPEN | |
| `exponent` of `control_monthly_erosivity` | `rusle_r_monthly_control_exponent` | The exponent of monthly precipitation in the control regression | None: it is an exponent | S7 as S4 gives it, with the equation number. OPEN | |
| `mean_annual_r` of `r_by_year_and_month` | `rusle_r_factor` | The mean annual level of `R` at the field, from the published national values interpolated to the field | `MJ mm ha-1 h-1 yr-1` (D11) | S4; the interpolation to the field is a later unit. OPEN | |

Catalogue status on `main` (`b8a3ea4`): `params/records/` holds `132` signed records in total (`32` signed erosion and residue records — `26` top-level erosion records, including `rusle_r_factor` in `params/records/rusle_r_factor.colonia.json` for Colonia under D83 and the twelve `rusle_r_monthly_erosivity_<month>` records committed and signed in `#203` — plus `6` in `params/records/residues/`, alongside `100` in `params/records/water/`). The two daily-index constants (`rusle_r_daily_index_exponent`, `rusle_r_daily_index_threshold`) have no record in `params/records/` while S5 and S6 remain behind paywalls, and the two control-regression constants (`rusle_r_monthly_control_coefficient`, `rusle_r_monthly_control_exponent`) have no record and stay out of the first-release route (PC-7).

## PROPOSED cases

Each case is a test function of `test_r_factor.py`; a test checks that this list and the file agree. Every constant in the tests is a PLACEHOLDER: small whole numbers chosen so that the arithmetic is done by hand. No case holds an expected value of the science.

### The daily index

| Case | What it shows |
|---|---|
| `test_index_day_at_or_below_the_threshold_adds_nothing` | Days of zero, below and exactly at the threshold give zero; the nearest number above it gives more |
| `test_index_grows_with_precipitation_above_the_threshold` | Above the threshold the index rises strictly with precipitation (structure only) |
| `test_index_by_hand_with_placeholder_constants` | With a PLACEHOLDER exponent of two, the index is the square, worked out by hand |
| `test_index_missing_day_stays_missing_and_is_never_zero_rain` | A missing day is `MISSING_INPUT` naming its date and reason; the dry day beside it is zero |
| `test_index_negative_or_non_finite_precipitation_is_not_clipped` | A negative or infinite day is `NOT_COMPUTABLE`, never clipped, in the precipitation and in the index |
| `test_index_missing_or_non_finite_constant_gives_missing_naming_it` | A missing exponent or threshold, of either `Missing` shape, gives `MISSING_INPUT` naming it; a constant that is not finite gives `NOT_COMPUTABLE` |
| `test_index_unit_other_than_mm_per_day_is_not_converted` | A series or a threshold in another unit string gives `REASON_UNIT_NOT_ACCEPTED`; nothing is converted |
| `test_index_result_that_is_not_finite_is_not_computed` | An index that overflows is `NOT_COMPUTABLE` for that day |

### Monthly and annual sums

| Case | What it shows |
|---|---|
| `test_monthly_sums_add_the_days_of_each_month` | Each calendar month is the sum of its days |
| `test_monthly_sum_with_a_missing_day_is_missing_input_naming_the_day` | A month with a missing day is `MISSING_INPUT` naming it; the other month is a number |
| `test_monthly_sum_of_a_partly_covered_month_is_no_coverage` | Months cut by the extent of the series are `NO_COVERAGE` |
| `test_a_missing_table_is_missing_input_that_names_it` | A `Missing` in place of a whole table, at every step, gives `MISSING_INPUT` naming that argument |
| `test_annual_sums_follow_the_start_month` | Calendar years with start month 1; agricultural years with another start month, the years cut by the extent `NO_COVERAGE` |
| `test_annual_sum_of_an_incomplete_year_is_no_coverage` | A year the series does not cover in full is `NO_COVERAGE`, naming the months (C5.5) |
| `test_annual_sum_with_a_missing_month_is_missing_input` | A year with a missing month is `MISSING_INPUT` naming it |

### Monthly fractions

| Case | What it shows |
|---|---|
| `test_monthly_fractions_of_a_year_add_up_to_one` | Twelve fractions per year, adding up to one within floating point, for two start months |
| `test_a_year_without_an_erosive_day_has_no_fraction` | A year whose days never pass the threshold has twelve `NOT_COMPUTABLE` fractions: not zero, not split equally |
| `test_fractions_of_a_missing_year_carry_the_reason` | The fractions of a `NO_COVERAGE` year are `NO_COVERAGE`; those of a year with a missing day are `MISSING_INPUT` |
| `test_a_missing_day_makes_its_month_and_its_year_missing_and_no_other` | The choice of the section "A missing day", end to end through `r_factor_parts` |

### Yearly ratios

| Case | What it shows |
|---|---|
| `test_yearly_ratios_average_to_one_over_the_years_where_they_are_defined` | Four different years whose ratios average to one |
| `test_a_missing_year_has_a_missing_ratio_and_is_left_out_of_the_mean` | A missing year keeps its reason and is left out of the mean, so the others still average to one |
| `test_yearly_ratios_with_a_zero_mean_are_not_computed` | A record without an erosive day has no ratio; one dry year beside an erosive one has a real ratio of zero |

### R by year and month

| Case | What it shows |
|---|---|
| `test_r_is_the_level_times_the_fraction_times_the_ratio` | The product, by hand |
| `test_r_of_a_year_adds_up_to_level_times_ratio_and_averages_to_the_level` | The months of a year add up to the level times the ratio; the annual totals average to the level |
| `test_a_missing_level_makes_r_missing_and_keeps_fractions_and_ratios` | A missing level, of either shape, makes `R` `MISSING_INPUT` naming `mean_annual_r`, while the fractions and ratios are returned; a level that is not finite is `NOT_COMPUTABLE` |
| `test_a_level_in_another_unit_is_not_converted` | A level in another unit string gives `REASON_UNIT_NOT_ACCEPTED` |
| `test_r_of_a_month_with_a_missing_fraction_or_ratio_is_missing` | A missing fraction or ratio, or a year absent from the ratios, makes that month missing with the right reason |

### The control regression

| Case | What it shows |
|---|---|
| `test_control_is_the_coefficient_times_a_power_of_monthly_precipitation` | The control of each month, by hand |
| `test_control_missing_or_non_finite_coefficient_gives_missing_naming_it` | Missing, non-finite and unit cases of the control |
| `test_control_month_with_a_missing_day_or_cut_by_the_extent_is_missing` | The months of the control follow the rules of `monthly_sums` |
| `test_the_comparison_reports_both_fractions_and_changes_neither` | The control fractions add up to one; the report holds both fractions and their difference; the index fractions are unchanged |
| `test_a_month_missing_in_either_table_has_a_missing_difference` | A month missing in, or absent from, either table has a missing difference with the right reason |

### Defects of the caller and no constant in the modules

| Case | What it shows |
|---|---|
| `test_every_argument_is_passed_by_name_and_none_has_a_default` | Every public function takes keyword arguments only, none with a default |
| `test_an_argument_of_another_type_raises_type_error` | `None`, text, a boolean or a list in place of a constant, a series or a table raises `TypeError` naming it |
| `test_a_start_month_outside_one_to_twelve_is_refused` | `ValueError` for 0 and 13; `TypeError` for a float, a boolean or text |
| `test_the_modules_hold_no_number_but_calendar_ones` | The modules write only 0, 1, 2 and 12: the zero of "adds nothing" and of a zero sum, and month arithmetic |
| `test_readme_lists_every_constant_with_an_empty_value` | The table of constants has the five constants, distinct well-formed identifiers and an empty value in each row |
| `test_readme_lists_the_cases_of_this_file` | This list and `test_r_factor.py` name the same cases |

### Waiting for a person

Each is **skipped**, and its reason says what it waits for: the inputs, the expected results and the tolerance, transcribed with the locator and checked by a person (D34). No entry of `docs/VALIDATION.md` names this unit (OPEN 12).

| Case | What it shows |
|---|---|
| `test_s5_daily_index_against_a_worked_example` | The daily index against a worked example of S5, if it has one |
| `test_s6_daily_index_against_a_worked_example` | The daily index against a worked example of S6, if it has one |
| `test_s7_control_regression_against_a_worked_example` | The control against a worked example of S7 as S4 gives it |
| `test_s4_r_by_month_against_published_values` | `R` by month against the level, and the monthly distribution if S4 publishes one, at one place |

## Climatological monthly fraction (D69)

Decision D69 of issue #77 (14 November 2026): while S5 and S6 stay behind paywalls, the first release takes the **monthly erosivity of a published climatology** (D69 names GloREDa, Panagos et al. 2023, Zenodo record 8036998), and **the fraction of a month is that month's value over the sum of the twelve**. Decision USER-G of the lead developer (the same day, recorded in `docs/SCIENCE_DECISIONS.md`) defers the variation between years: the same twelve fractions hold for every agricultural year. D69 declares that limit: the climatology gives a climatological fraction, not the variation between years that M1.2 asks for.

**Update on `main` (`b8a3ea4`; D84, D101, #187, #203):** When this unit was written, the licence of the climatology was still open under D69 and no monthly value was in the repository. Decision [D101](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885772469) (14 November 2026) settled the licence as Creative Commons Attribution 4.0 International (`CC BY 4.0`) for Zenodo record 8036998 (recording the conflicting ESDAC copy conditions without applying them to the Zenodo copy). Unit `l0/first-number` (`#203`) committed the twelve signed monthly records `rusle_r_monthly_erosivity_<month>` at the demonstration point La Estanzuela (D84) in `params/records/` with scope `{}`. Unit `l0/erosion-ep1-c-r` (`#187`) wired `climatology.py` into EP1 (`compute_soil_loss`), so monthly soil-loss values on the main route are now computed from those twelve records rather than staying `NOT_AVAILABLE` (monthly values stay `NOT_AVAILABLE` only on `compute_soil_loss_daily_index`, off the main path).

```text
fraction(month)  = E(month) / (E(1) + ... + E(12))          E: published monthly erosivity at the point
R(year, month)   = mean_annual_r * fraction(month)            the same for every agricultural year
```

| Function | Module | Takes | Returns |
|---|---|---|---|
| `climatological_monthly_fractions` | `climatology.py` | `monthly_erosivity`: the twelve calendar months, each a number or a `Missing` | `{month: float \| Missing}` adding up to one, or one `Missing` |
| `climatological_r_by_year_and_month` | `climatology.py` | `mean_annual_r`, `mean_annual_r_unit`, `fractions`, `ag_years`, `start_month` | `{ag_year: {(year, month): float \| Missing}}`, the shape of `r_by_year_and_month`, or one `Missing` |

`PROPOSED` handling, in the style of the rest of this package: a missing month makes every fraction one `MISSING_INPUT` naming it (the sum of the twelve is not defined); a month below zero or not finite is `NOT_COMPUTABLE`, never clipped; twelve months adding up to zero are `NOT_COMPUTABLE`, never split equally; a level in another unit than `R_UNIT` is `REASON_UNIT_NOT_ACCEPTED`. The monthly values carry one unit because they come in one table; the fraction has none, so no unit string is checked for them.

| Input a person supplies | Proposed identifier | Unit | Source | Value |
|---|---|---|---|---|
| The twelve monthly erosivity values at the point | Committed in `#203` as `rusle_r_monthly_erosivity_<month>` with scope `{}` (`SOIL_LOSS.md` OPEN 11 keeps open whether `params/` adds a `month` scope key or an adapter supplies them) | OPEN: as the climatology prints it (`#203` uses one shared string across the twelve records) | D69, D84, D101: GloREDa (Zenodo record 8036998, `CC BY 4.0`); La Estanzuela cell records committed in `params/records/` (`#203`) | |

Cases, in `test_climatology.py` (a test checks that this list and that file agree; every number in it is a PLACEHOLDER):

| Case | What it shows |
|---|---|
| `test_fractions_are_each_month_over_the_sum_of_twelve` | Each fraction is its month over the sum, by hand; the twelve add up to one |
| `test_a_missing_month_makes_every_fraction_missing_and_names_it` | A missing month, of either shape, gives one `MISSING_INPUT` naming it; no month is filled |
| `test_negative_non_finite_or_zero_sum_months_are_not_computed` | A negative or infinite month, or twelve zeros, give `NOT_COMPUTABLE`; never clipped, never split equally |
| `test_r_is_the_level_times_the_fraction_and_repeats_every_year` | `R` is the level times the fraction of the calendar month; every year has the same twelve values, adding up to the level, keyed by the start month |
| `test_r_with_a_missing_or_foreign_level_or_missing_fractions` | A missing level or table gives `MISSING_INPUT`; a level in another unit gives `REASON_UNIT_NOT_ACCEPTED`; a missing fraction makes its month missing |
| `test_the_table_of_r_has_the_shape_of_the_daily_index_route` | The same keys as `r_by_year_and_month` for the same years and start month |
| `test_climatology_defects_of_the_caller_raise` | Keyword arguments only, no default; a month set other than 1 to 12 is `ValueError`; wrong types are `TypeError` |
| `test_climatology_module_holds_no_number_but_calendar_ones` | The module writes only 0, 1, 2 and 12 |
| `test_readme_lists_the_cases_of_test_climatology` | This list and `test_climatology.py` name the same cases |

Status of verification: since `#203` and `#187`, the twelve La Estanzuela GloREDa records are in `params/records/` and EP1 (`compute_soil_loss`) runs them through `climatology.py`, and in Run #4 (`df43899`, `#463`) all `24` recorded results of `[E0]` (whose comparator calls `climatological_monthly_fractions`) pass; whether the monthly layers are in the unit D11 implies for a month stays OPEN (OPEN 9), and acceptance by a science reviewer is pending.

## OPEN

Each item is a question a person has to answer, with the role that answers it. None is answered by this unit.

1. **What does a missing day make missing?** Proposed: that day, its month and its agricultural year; the year is left out of the mean of the ratios. The alternatives are to fill the gaps with a method under C3.4 (whose method is OPEN), or to accept a month with some missing days, which needs a count or share that a person supplies. For the science reviewers.
2. **Are the forms the published ones?** In particular: whether the index is `P ** exponent` above the threshold, or another member of the power-law family (for example one that subtracts the threshold); whether the threshold is compared with `>` (a day at the threshold adds nothing); and whether S5 or S6 is the source. For the science reviewers, against S5 and S6.
3. **Does the published index carry a multiplying coefficient, and does it change with the month or the season?** A constant one cancels in the fractions and the ratios, so the index here has none. One that changes with the month does not cancel, and would be a further argument with its own row in the table above. For the science reviewers.
4. **Which year is the year of the fractions and the ratios: the calendar year or the agricultural year of the case?** The functions take `start_month` and leave the choice to the caller; `start_month=1` gives calendar years. D47 lists agricultural years in the results. For the lead developer and the science reviewers.
5. **A year with no erosive day.** Its fractions are not defined, so its values of `R` are missing, although its yearly ratio is a real zero. Is that the wanted result, or is `R` of such a year zero? For the science reviewers.
6. **Over which years is the mean of the ratios taken?** Proposed: the years whose annual sum is a number, so missing and incomplete years are left out. The alternative is to require the whole record (D29, 2001 to 2024) and make every ratio missing otherwise. For the science reviewers.
7. **What is the form of the control regression, and on what does it run?** Proposed: `coefficient * P(month) ** exponent` on the monthly sum of daily precipitation, in millimetres. `docs/METHODS.md` says the equation of S7 was taken from S4 and the session read neither. If the published regression uses another quantity (for example an annual total, or an index built from monthly totals), the function changes. For the science reviewers. **AI pre-check finding (F16, 14 November 2026; not a person's check, D34):** S4, p. 92 (PDF page 2), prints two regressions of the **annual** `R`, Eq 1 on mean annual precipitation and Eq 2 on the modified Fournier index; neither is a power of the monthly precipitation, and pages 92 to 93 neither print the formula of the Fournier index nor prescribe a monthly distribution of `R` or applying the regressions month by month. Eq 2 prints a squared `P` after the Fournier term; the oddity is kept as printed and not corrected by inference. So the form of `control_monthly_erosivity` has no source among the pages read. Under D69 the monthly fraction of the first release comes from a published monthly climatology (section "Climatological monthly fraction (D69)"), and this control is not run by EP1. See `docs/SCIENCE_DECISIONS.md`, finding F16. **Decided (PC-7, 14 November 2026):** the control is marked without a source and stays out of the route of the first release.
8. **How is the comparison with the control reported to people?** The function returns both fractions and their difference per month. Whether a summary is shown, and from which difference the two are said to disagree, is a threshold that a person supplies. For the lead developer and the science reviewers; the interface developer if it is shown.
9. **Which unit strings do a monthly value of `R` and a value of the control carry?** The months of a year add up to an annual `R` in `MJ mm ha-1 h-1 yr-1`, but no unit string for a monthly value exists in the repository. For the science reviewers and the lead developer (C1.1).
10. **For which values do the forms hold?** No bound is written: a negative exponent, a negative threshold, a negative level or a negative coefficient is computed where the arithmetic allows. A bound is a threshold, which a person supplies. For the science reviewers.
11. **Which reason code does a unit that is not accepted get?** Q11 of `contracts/ENTRYPOINTS.md`. The package uses `NOT_COMPUTABLE`, in the one constant `REASON_UNIT_NOT_ACCEPTED`, as `ls.py` does. For the lead developer.
12. **Which validation entry gates this unit?** Blueprint section 8 lists "monthly erosivity fraction" for L0 without a validation code, and no entry of `docs/VALIDATION.md` names it. The four skipped tests wait for worked examples of S4 to S7. For the science reviewers.
13. **How is the national level interpolated to the field, and in which record does it travel?** Out of scope here: a later unit with the science reviewers. The table above proposes `rusle_r_factor`, the identifier of EP1 (#158); whether it is one record per region (scope key `region` of `params/README.md`) or per field is for the lead developer.
14. **Is the extent rule for a partial month the wanted one?** A month cut by the start or end of the series is `NO_COVERAGE`, by analogy with C5.5, which speaks of agricultural years. For the lead developer.
15. **Which series feeds the index?** The functions read any `DailySeries` in `mm day-1`, so `precipitation` (CQ1) and the control series `precipitation_reanalysis` (CQ1b) both pass. Which one the engine uses is decided by the caller, and nothing here checks the quantity identifier. For the lead developer.
16. **Who gives these values their range, provenance label and source?** The functions return bare numbers. How an uncertainty range passes through these forms is a method, which a person supplies (C2.2). By C4.3 the label would be `DERIVED`. Proposed: the caller that builds the indicator value. For the science reviewers and the lead developer.
17. **May these functions raise `TypeError` and `ValueError`?** They raise for an argument of the wrong type and for a start month outside 1 to 12, so that a `None` is never read as a value (G5; Q7 of `contracts/ENTRYPOINTS.md`). For the platform developer.
18. **Are the proposed parameter identifiers accepted?** Four new ones and `rusle_r_factor`. For the lead developer, who owns `params/`.

## Not verified

- **The forms and every constant against S4 to S7.** The session read none of the sources, by rule.
- **Use by the rest of the engine.** When this unit was written, EP1 (`#158`) and `c_factor/` (`#162`) were on separate branches; on `main` (`b8a3ea4`), `#187` wired EP1 to both `r_factor/` and `c_factor/`, `#229` wired main-route `C` to `climatological_monthly_fractions`, and `validation/trivial_comparator_erosion.py` (D211) also calls `climatological_monthly_fractions`. In Run #4 (`df43899`, `#463`), the recorded erosion validation checks pass (`[E0]` 24/24, `[E2]` 16/16, `[E3]` 1/1, `[E8]` 154/154, `[E9]` 218/218; `[E1a]` and `[E1b]` are not evaluated in this release under D254, and `[E7]` has no pass rule under D252), while the four worked-example tests in `test_r_factor.py` remain skipped and acceptance by a science reviewer remains pending.
- **The names scan of CI.** The list of forbidden names is a secret of the repository.
- **Lint in CI.** The CI workflow runs ruff on `api/`, `adapters/` and `ci/` only; the session ran ruff on its own files.
- **Real data.** No test reads a real series; the period of D29 and the IMERG series of D23 were not run through these functions.
