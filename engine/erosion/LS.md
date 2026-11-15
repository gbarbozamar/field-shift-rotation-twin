# Slope steepness and slope length factors

Unit `l0/erosion-ls` (issue #73): the factors `S` and `L` of `docs/METHODS.md` M1.4, in `engine/erosion/ls.py`.

> **Status: PROPOSED** (blueprint section 3.7). The signatures, the handling of units, the reason codes, the parameter identifiers and the test cases below were written by a builder session. They take effect only when a person approves the pull request. This is a science-class change: it also needs a science reviewer. Items under [OPEN](#open) need an answer from a person.

**This unit holds no coefficient.** Not in the code, not as a default, not in a test, not in this file. The equation forms come from issue #73, with letters in place of the coefficients; the forms are themselves `PROPOSED` there, until a science reviewer has checked them against sources S2 and S3 of `docs/METHODS.md`. The session read neither source and wrote no number of the method from memory.

**[E3] runs and passes.** Its fixture `validation/fixtures/e3_ah703_tables.json` is on `main`, signed (`checked_by` filled, for the file and for its unit-length record), since [#238](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/238). [D124 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886937443) fixed the check before any run: the 91 cells of AH703 Table 4-2, worked in feet, and the 19 Moderate values of `m` of Table 4-5, each within the tolerance D124 states. The test ran and passed in the three recorded runs of the suite, at commits `3ced36f`, `b831602` and `9410a92` (results `3ced36f-E3-test_e3_slope_length_and_steepness_against_published_values-001`, `b831602-E3-test_e3_slope_length_and_steepness_against_published_values-001` and `9410a92-E3-test_e3_slope_length_and_steepness_against_published_values-001` in `validation/results/`; the entry [E3](../../docs/VALIDATION.md#e3) of `docs/VALIDATION.md`). Acceptance by a science reviewer is pending.

Acceptance test, from the repository root:

```bash
python -m pytest engine/erosion/test_ls.py
```

## The forms

As issue #73 gives them. `theta` is the slope angle and `lambda` the slope length.

```text
S = a1 * sin(theta) + a2        when the slope is below the break slope s_break
S = a3 * sin(theta) - a4        when the slope is at the break slope or above it

L    = (lambda / lambda_unit) ** m
m    = beta / (1 + beta)
beta = (sin(theta) / b1) / (b2 * sin(theta) ** b3 + b4)
```

`docs/METHODS.md` M1.4 describes the exponent of the length factor as depending on the ratio of rill to interrill erosion. That `beta` is that ratio is the reading of the session: `PROPOSED`.

The module writes two numbers and no other: the `1` of `1 + beta`, which is part of the form above, and the hundred that the word "percent" means, used to read a slope given in percent. A test reads the module and fails on any other number.

## Signatures

Two public functions. Every argument is passed by name and none has a default.

```text
slope_steepness_factor(
    *,
    slope_steepness: float | Missing,
    slope_unit: SlopeUnit,
    s_break: float | Missing,
    s_break_unit: SlopeUnit,
    a1: float | Missing,
    a2: float | Missing,
    a3: float | Missing,
    a4: float | Missing,
) -> float | Missing

slope_length_factor(
    *,
    slope_length: float | Missing,
    slope_length_unit: str,
    lambda_unit: float | Missing,
    lambda_unit_unit: str,
    slope_steepness: float | Missing,
    slope_unit: SlopeUnit,
    b1: float | Missing,
    b2: float | Missing,
    b3: float | Missing,
    b4: float | Missing,
) -> float | Missing
```

- A number is a `float` (an `int` is accepted; a boolean is not).
- `Missing` as an argument is either of the two existing shapes: `contracts.inputs.common.Missing`, which is what the `missing` part of `SiteSoilSlope.slope_steepness` and `SiteSoilSlope.slope_length` is, or `contracts.results.models.Missing`. `Missing` as a result is always `contracts.results.models.Missing`, the one `contracts/ENTRYPOINTS.md` names. This unit defines no `Missing` shape.
- The caller passes `value` of the contract `Value` when it is a number, and its `missing` part when it is not.
- Both functions are pure (`contracts/ENTRYPOINTS.md` G1): no file, no network, no clock, no argument changed. They do not read the parameter catalogue: the caller does.
- They are parts of the erosion engine, not its entry point. The product of the factors and `compute_soil_loss` are other units.

Also public: the enumeration `SlopeUnit` and the constant `REASON_UNIT_NOT_ACCEPTED`, both described below.

## Units

The input contract leaves the unit of slope steepness and of slope length `OPEN` (question 18 of `contracts/inputs/README.md`). So the caller states them:

| Argument | What it says | How it is used |
|---|---|---|
| `slope_unit` | How the number of `slope_steepness` is read: `SlopeUnit.PERCENT`, `RATIO`, `ANGLE_DEGREES` or `ANGLE_RADIANS` | To obtain `sin(theta)` |
| `s_break_unit` | The same, for `s_break` | The slope and the break slope are compared as given, so the two must be the same `SlopeUnit`; nothing is converted |
| `slope_length_unit` | The unit string that the slope length carries (`Value.unit`) | The length is divided by the unit length as given, so the two strings must be the same text; no length is converted |
| `lambda_unit_unit` | The unit string that `lambda_unit` carries in the parameter catalogue | As above |

- `SlopeUnit` is a set of names for the caller of this module. It is not a vocabulary of unit strings for any contract.
- `PERCENT` and `RATIO` are read as rise over horizontal distance, that is the tangent of the slope angle: `PROPOSED`, see OPEN 2.
- When the two units of a pair differ, the factor is not computed (C1.1: a consumer checks the unit it receives). The reason code for that case is not decided (Q11 of `contracts/ENTRYPOINTS.md`); the module holds the proposed code in one constant, `REASON_UNIT_NOT_ACCEPTED`.

## When a factor is not computed

A factor that is not computed is a `Missing` with its reason. It is never zero, never a default and never "not a number" (section 3 of `contracts/CONVENTIONS.md`, G4 of `contracts/ENTRYPOINTS.md`). All `PROPOSED`.

| Situation | Result | Basis |
|---|---|---|
| The slope, the length or any coefficient is a `Missing` | `MISSING_INPUT`. `detail` names every missing argument, each with its own reason code and detail | C3.3, G4 |
| An argument is a number that is not finite ("not a number", an infinity, an integer too large for a float) | `NOT_COMPUTABLE`. `detail` names each one | Issue #73; reason code proposed, OPEN 9 |
| The two units of a pair differ | `REASON_UNIT_NOT_ACCEPTED`, which is `NOT_COMPUTABLE` today. `detail` gives both units | C1.1, G4; Q11 |
| The arguments are finite numbers and a step of the form gives no finite real number: a division by zero, an overflow, a negative number raised to a fractional power | `NOT_COMPUTABLE`. `detail` names the step (`S`, `beta`, `m` or `L`) | G4, last but one row |
| An argument is neither a number nor a `Missing` (`None`, text, a boolean), or a unit argument has another type | `TypeError` | G5; Q7 |

- A missing argument is reported before any other reason.
- Every coefficient is needed, also the two of the branch that the slope does not take: OPEN 11.
- The format of `detail` is: `<argument> is missing, reason <CODE>: <detail of the argument>`, items joined by `; `.

## Parameters a person has to transcribe

One row per coefficient. A person fills the parameter catalogue (`params/records/`) from this table and signs `transcribed_by`; a second person checks each value against the source and signs `checked_by` (`params/README.md`). **The column "Value" stays empty in this file: a session writes no value.**

The identifiers are `PROPOSED`. The proposed `scope` of every record is `{}`: see OPEN 5.

| Coefficient | Proposed parameter identifier | What it is | Unit it needs | Source | Value |
|---|---|---|---|---|---|
| `a1` | `rusle_s_below_break_sine_coefficient` | Multiplies `sin(theta)` in the form of `S` used below the break slope | The unit of `S`: OPEN 4. By the form, `sin(theta)` has no unit, so `a1` to `a4` share one unit | S2 or S3: a person says which, with its locator | |
| `a2` | `rusle_s_below_break_constant` | Added in the form of `S` used below the break slope | As `a1` | S2 or S3: a person says which, with its locator | |
| `a3` | `rusle_s_at_or_above_break_sine_coefficient` | Multiplies `sin(theta)` in the form of `S` used at the break slope and above it | As `a1` | S2 or S3: a person says which, with its locator | |
| `a4` | `rusle_s_at_or_above_break_constant_subtracted` | **Subtracted** in the form of `S` used at the break slope and above it. Transcribe it with the sign that makes `a3 * sin(theta) - a4` the published equation | As `a1` | S2 or S3: a person says which, with its locator | |
| `s_break` | `rusle_s_break_slope` | The slope that separates the two forms of `S`. A slope equal to it takes the second form: OPEN 3 | A slope, in the unit the source states. The record says which, and the caller passes it as `s_break_unit`; it must be the unit of the slope of the field: OPEN 1, OPEN 8 | S2 or S3: a person says which, with its locator | |
| `lambda_unit` | `rusle_l_unit_length` | The length that divides the slope length in the form of `L`: at this length `L` is one | A length, in the unit the source states. It must be the unit string of the slope length of the field: OPEN 1, OPEN 8 | S2 or S3: a person says which, with its locator | |
| `b1` | `rusle_l_beta_sine_divisor` | Divides `sin(theta)` in the numerator of `beta` | By the form, `beta` has no unit only if `b1 · b2` and `b1 · b4` have none. A person states the unit of each from the source: OPEN 4 | S2 or S3: a person says which, with its locator | |
| `b2` | `rusle_l_beta_denominator_sine_coefficient` | Multiplies the power of `sin(theta)` in the denominator of `beta` | As `b1` | S2 or S3: a person says which, with its locator | |
| `b3` | `rusle_l_beta_denominator_sine_exponent` | The exponent of `sin(theta)` in the denominator of `beta` | None: it is an exponent. A person confirms it from the source | S2 or S3: a person says which, with its locator | |
| `b4` | `rusle_l_beta_denominator_constant` | Added in the denominator of `beta` | As `b1` | S2 or S3: a person says which, with its locator | |

For the science reviewers: the ten coefficients above were transcribed from S2 by an AI session on 14 November 2026 under [D34](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) and are now records in `params/records/` (`rusle_s_*.json`, `rusle_l_*.json`). Each record cites its equation and page in the scanned copy of S2 (Eq. [4-3], p. 105; Eq. [4-4] and [4-5], p. 107; Appendix A, p. 325 for the unit length) and says it was checked by the lead developer against a crop of the source page on 14 November 2026; each is signed `checked_by` `gbarbozamar`. They are among the 26 records of [pull request #203](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/203) (merged 15 November 2026); an AI verifier compared the same pages and reported that every value it could open matched ([comment](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/203#issuecomment-6886548387)). The unit length 22.1 m was chosen over 72.6 ft by [D127](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886945455). S3 is not cited by any of the ten records, and no record of a check of S3 was found: `docs/METHODS.md` still marks it "located". The column "Source" of the table above, "S2 or S3: a person says which", is as it was written before the records existed; the records name S2. The status of S2 and what of it was checked are in `docs/METHODS.md`, sources table.

## PROPOSED cases

Each case is a test function of `test_ls.py`; a test checks that this list and the file agree. Every coefficient in the tests is a PLACEHOLDER: plainly not real numbers (repeated digits, or zero and one where the arithmetic is done by hand). No case holds an expected value of the science.

### The forms

| Case | What it shows |
|---|---|
| `test_steepness_below_the_break_slope_uses_the_first_form` | Far below the break slope and at the nearest number below it, `S` is the first form. In each of the four slope units |
| `test_steepness_at_or_above_the_break_slope_uses_the_second_form` | Exactly at the break slope, at the nearest number above it and far above it, `S` is the second form. In each of the four slope units |
| `test_steepness_by_hand_on_a_three_four_five_slope` | On a slope of rise three over run four, both forms give the number worked out by hand from the PLACEHOLDER coefficients |
| `test_steepness_each_form_reads_its_own_two_coefficients` | Below the break slope a change of `a1` or `a2` moves `S` and a change of `a3` or `a4` does not; above it, the reverse |
| `test_the_four_slope_units_describe_the_same_slope` | One slope written as percent, ratio, degrees and radians gives the same `S` and the same `L` |
| `test_length_factor_is_one_when_the_length_equals_the_unit_length` | `L` is exactly one when the slope length equals `lambda_unit`, for several slopes and in each slope unit |
| `test_length_factor_follows_the_three_forms` | `L` equals the three forms written a second time in the test, for several lengths and in each slope unit |
| `test_length_by_hand_on_a_three_four_five_slope` | With PLACEHOLDER coefficients that are zero and one, `beta`, `m` and `L` are worked out by hand for two cases |
| `test_length_every_coefficient_changes_the_result` | A change of `lambda_unit`, `b1`, `b2`, `b3` or `b4` moves `L`: none is ignored and none has a hidden value |

### Missing arguments

| Case | What it shows |
|---|---|
| `test_steepness_missing_argument_gives_missing_input_that_names_it` | A missing slope, break slope or coefficient gives `MISSING_INPUT` naming it and nothing else; on both sides of the break slope; for both `Missing` shapes. Never a number |
| `test_length_missing_argument_gives_missing_input_that_names_it` | The same for the length, the unit length, the slope and `b1` to `b4` |
| `test_missing_length_stays_missing_also_when_the_factor_would_be_one` | A missing unit length, or a missing length together with a missing unit length, is missing and not one |
| `test_several_missing_arguments_are_all_named_with_their_reasons` | Every missing argument is named, with its own reason code and detail; missing comes before "not finite" |

### Arguments and results that are not finite numbers

| Case | What it shows |
|---|---|
| `test_steepness_argument_that_is_not_finite_is_not_computed` | "Not a number" or an infinity as the slope, the break slope or a coefficient gives `NOT_COMPUTABLE` naming it |
| `test_length_argument_that_is_not_finite_is_not_computed` | The same for every numeric argument of the length factor |
| `test_integer_too_large_for_a_float_is_not_computed` | An integer that a float cannot hold is not computed and raises nothing |
| `test_steepness_that_overflows_is_not_computed` | Finite arguments whose `S` overflows give `NOT_COMPUTABLE`, not an infinity |
| `test_length_form_without_a_finite_real_result_is_not_computed` | A division by zero in `beta`, in `m` or in `L`, and a negative number raised to a fractional power, give `NOT_COMPUTABLE` naming the step; nothing is raised |

### Units

| Case | What it shows |
|---|---|
| `test_steepness_break_slope_in_another_unit_is_not_computed` | A break slope stated in another slope unit than the slope: not computed, both units named |
| `test_length_and_unit_length_in_different_units_are_not_computed` | A unit length whose unit string differs from that of the slope length: not computed, both units named |
| `test_a_missing_argument_is_reported_before_a_unit_that_differs` | A missing argument is reported first |

### Defects of the caller

| Case | What it shows |
|---|---|
| `test_steepness_argument_of_another_type_raises_type_error` | `None`, text, a boolean or a list in place of a number raises `TypeError` naming the argument |
| `test_length_argument_of_another_type_raises_type_error` | The same for the length factor |
| `test_unit_argument_of_another_type_raises_type_error` | A unit argument of another type raises `TypeError` naming it |

### No coefficient in the module

| Case | What it shows |
|---|---|
| `test_every_argument_is_passed_by_name_and_none_has_a_default` | Both functions take keyword arguments only, and no argument has a default |
| `test_every_coefficient_of_the_issue_is_an_argument` | The ten coefficients of issue #73 are arguments |
| `test_the_module_holds_no_number_but_those_of_the_forms` | `ls.py` writes two numbers only: the one of `1 + beta` and the hundred of "percent" |
| `test_ls_md_lists_every_coefficient_with_an_empty_value` | The table above has one row per coefficient, a well-formed and distinct identifier in each, and an empty value in each |
| `test_ls_md_lists_the_cases_of_this_file` | This list and `test_ls.py` name the same cases |

### Waiting for a person

| Case | What it shows |
|---|---|
| `test_e3_slope_length_and_steepness_against_published_values` | [E3] of `docs/VALIDATION.md` with decision D124 of issue #77: `LS = S * L` for the 91 cells of AH703 Table 4-2, worked in feet, and `m` for the 19 Moderate cells of Table 4-5, each within the tolerance of D124. Expected values and the unit length in feet come from the signed fixture `validation/fixtures/e3_ah703_tables.json` (format in `validation/fixtures/README.md`), the coefficients from the parameter catalogue. **Skipped** while the fixture is absent or unsigned, with a reason that names the file and what is not signed. On `main` the fixture is signed (#238) and the test runs and passes (OPEN 15) |
| `test_e3_absent_fixture_skips_naming_the_file_and_the_signature` | With no fixture, the skip reason names the file and the missing `checked_by` |
| `test_e3_unsigned_fixture_skips_naming_what_is_not_signed` | A PLACEHOLDER fixture with empty `checked_by`: the reason names the file's signature and the unit length's |
| `test_e3_unsigned_unit_length_alone_is_enough_to_skip` | A signed file whose unit-length record is not signed still skips |
| `test_e3_signed_placeholder_fixture_runs_and_passes` | A signed PLACEHOLDER fixture, written to a temporary folder, is read and every cell passes |
| `test_e3_value_outside_its_tolerance_fails` | One cell of each table moved out of its tolerance: exactly those two cells fail |
| `test_e3_a_tolerance_other_than_d124_fails` | A tolerance in the fixture that is not the one of D124 is reported |
| `test_e3_a_cell_count_other_than_d124_fails` | A table with another number of cells than D124 names fails |
| `test_e3_unit_length_in_another_unit_fails` | A unit length not in feet fails: D124 works Table 4-2 in feet |
| `test_e3_coefficients_are_read_by_the_identifiers_of_ls_md` | The identifiers the test reads from the catalogue are those of the table above, and the catalogue holds them |

## OPEN

Each item is a question a person has to answer. The role that answers it is named at the end. None is answered by this unit.

1. **In which unit do slope steepness and slope length arrive?** This is question 18 of `contracts/inputs/README.md`. Until it is answered the caller states the unit of each. When it is answered: which unit string of the contract is which `SlopeUnit`, and are the four names of `SlopeUnit` the right ones? For the science reviewers (the unit) and the lead developer (the names).
2. **Is a slope in percent, or as a ratio, the rise over the horizontal distance?** The module reads both as the tangent of the slope angle. If the source of the slope, or the source of `s_break`, defines them otherwise, the reading changes. For the science reviewers, and the platform developer as producer of the slope.
3. **Are the forms of issue #73 the published ones?** Issue #73 marks them `PROPOSED`. In particular: which form applies to a slope exactly equal to the break slope (here: the second); whether `a4` is subtracted; whether `beta` is the ratio of rill to interrill erosion of M1.4; and whether the sine in the three places is the sine of the same angle. For the science reviewers, against S2 and S3.
4. **Which unit do `S`, `L` and each coefficient have?** The functions return bare numbers and state no unit. By the form, `L` is a ratio of two lengths. Nothing in the repository gives the unit of `S`, and the session does not write one from memory. For the science reviewers.
5. **Do the sources give one set of coefficients, or several for different conditions?** The forms of issue #73 hold one set, and the proposed scope of every record is `{}`. If the sources give more than one set, or another form for some condition, a person says which applies and how a record tells them apart: the scope keys of `params/README.md` are `crop`, `stage`, `management`, `soil` and `region`. For the science reviewers; the lead developer for the scope key.
6. **For which slopes and lengths do the forms hold?** The functions compute for every finite number for which the arithmetic gives a finite real number. That includes a negative slope, a slope of zero, and a length of zero or below, where the arithmetic allows. No bound is written: a bound is a threshold, and a person supplies it. If the method has a domain, the cases outside it become `NOT_COMPUTABLE`. For the science reviewers.
7. **Which reason code does a unit that is not accepted get?** This is Q11 of `contracts/ENTRYPOINTS.md`. The module uses `NOT_COMPUTABLE`, in the one constant `REASON_UNIT_NOT_ACCEPTED`. For the lead developer.
8. **Who converts a unit, and where?** `docs/METHODS.md` M1.7 says the engine works in the International System and converts at the edge. This unit converts nothing: a break slope in another slope unit than the slope, and a unit length in another unit than the length, are refused. A conversion needs conversion factors, which are numbers with a source. For the lead developer.
9. **What is returned for a number that is not finite?** Issue #73 says it is not computed. Proposed: `NOT_COMPUTABLE`, naming the argument. A `Value` of the contract cannot hold such a number, so it can only come from a defect of the caller; the alternative is to raise. For the lead developer.
10. **May these functions raise `TypeError`?** G5 allows it to an entry point for an argument of the wrong type, and Q7 of `contracts/ENTRYPOINTS.md` asks whether an engine may raise at all. These functions are not entry points; they raise `TypeError` for an argument that is neither a number nor a `Missing`, so that a `None` is never read as a value. For the platform developer.
11. **Is a coefficient of the branch that the slope does not take needed?** Proposed: yes. Any missing coefficient gives a missing factor, as the acceptance case of issue #73 reads. The alternative, by the wording of C3.3 ("a result that needs a missing input"), is to compute `S` when only a coefficient of the other branch is missing. For the lead developer.
12. **In which shape does a coefficient reach the engine, and which `Missing` does it carry when it is missing?** This is Q3 of `contracts/ENTRYPOINTS.md` and question 24 of `contracts/inputs/README.md`. This unit takes each coefficient as a number or a `Missing`, accepts both existing `Missing` shapes and returns the one of the results contract. The `Missing` object of `params/catalogue.py` is a third shape and is not accepted: the caller translates it. For the lead developer and the platform developer.
13. **Who gives `S` and `L` their range, their provenance label and their source?** The functions return bare numbers. The uncertainty range of the slope, of the length and of each coefficient is not carried through: how a range passes through these forms is a method, and a person supplies it (C2.2). By C4.3 the label would be `DERIVED`. Proposed: the caller that builds the indicator value does it. For the science reviewers (the range) and the lead developer.
14. **Is the format of `detail` the wanted one?** It names each argument and repeats the reason code and the detail of a missing argument. For the lead developer, and the interface developer if the text is shown.
15. **What is [E3]?** **Answered by [D124](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886937443):** the 91 cells of AH703 Table 4-2, worked in feet, and the 19 Moderate values of `m` of Table 4-5, each within the tolerance D124 states; the definition is PROPOSED in the entry [E3](../../docs/VALIDATION.md#e3) of `docs/VALIDATION.md`. The signed fixture is on `main` since [#238](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/238), and the test runs and passes (the recorded runs at `3ced36f`, `b831602` and `9410a92`). Still open: acceptance of the definition by a science reviewer. *As first written:* Its definition, expected values, tolerance and source are `OPEN` in `docs/VALIDATION.md`. The test is skipped until they exist. For the science reviewers.
16. **Are the proposed parameter identifiers accepted?** The table above proposes ten, with the prefix `rusle_` and the empty scope. For the lead developer, who owns `params/`.

## Not verified

- **The forms and every coefficient against S2 and S3.** The session read neither source, by rule.
- **The names scan of CI.** The list of forbidden names is a secret of the repository and is not available to a session.
- **Use by the rest of the engine.** `engine/erosion/equation.py` is written by another session at the same time; this unit did not see it, so nothing shows yet that the two fit together.
- **Lint in CI.** The CI workflow runs ruff on `api/`, `adapters/` and `ci/` only, so it does not lint `engine/`. The session ran ruff on its own files.
