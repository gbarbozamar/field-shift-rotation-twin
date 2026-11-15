# `engine/water/runoff/`: daily runoff by the Curve Number method

The daily surface runoff of D44 of issue #77 ("runoff by the Curve Number"), as pure functions. Unit `l1/water-runoff-cn`, issue #148. It supplies the `runoff` that the one-layer balance of `engine/water/balance/` takes as a daily input in its `DayInput`. It is an internal part of the water engine: the route calls only the entry point EP3 of `contracts/ENTRYPOINTS.md`, which is not built by this unit.

Status: **PROPOSED** (blueprint section 3.7). Nothing here is in force until people approve the pull request: the lead developer, who owns lane L1 and decided the method (D44), and a science reviewer, because the forms of the equations are science class (blueprint section 3.6).

Status on `main` (15 November 2026): EP3 is built. `compute_water_deficit_exposure` is `engine/water/exposure.py` (#135, chained to runoff and `Ke` by #165); it imports this module and gives the balance of `engine/water/balance/` its daily runoff. It gives no water number with the catalogue of `params/records/` until the records the chain reads are signed. The sentences below that call EP3 not built describe the state when this folder landed.

Acceptance test, from the repository root:

```bash
python -m pytest engine/water/runoff/
```

Identifiers such as C3.2 refer to `contracts/CONVENTIONS.md`; EP3, G1 to G7 and Q11 refer to `contracts/ENTRYPOINTS.md`; CQ1 refers to `contracts/CLIMATE_QUANTITIES.md`; H1, H7, H8, H10 and E7 refer to `docs/VALIDATION.md`; S11 refers to the Sources of `docs/METHODS.md`; D-numbers are decisions in issue #77.

## What a reader must know first

- **This folder holds no constant of the method.** The initial-abstraction ratio, the two constants of the potential-retention formula and their unit factor are fields of `CurveNumberConstants`, with no default. The curve number of each day is an input. The only number the code writes is zero, and a test checks it. Every number in the test file is a PLACEHOLDER, plainly not real; none comes from any source.
- **The source of the forms is NRCS (2004), National Engineering Handbook Part 630, chapter 10** (S11 of `docs/METHODS.md`), by decision D82 of issue #77 (PC-6 of `docs/SCIENCE_DECISIONS.md`). See [Source of the forms](#source-of-the-forms).
- **Using these forms in a continuous daily balance is a declared adaptation** (D82, PC-6). See [Declared adaptation: continuous use](#declared-adaptation-continuous-use).
- **The forms of the equations are PROPOSED.** A builder session wrote them without the method's text in front of it. The AI pre-check found them to match S11; a person still confirms each form at its locator (D34, OPEN 1).
- **The table of curve numbers is not chosen.** D82 chooses the source of the forms, not the curve number of a soil, crop or cover (OPEN 3).
- **No state is carried from one day to the next.** Each day is computed from its own precipitation, its own curve number and the constants. So a missing day does not stop the days after it. This holds because this unit has no antecedent-moisture adjustment (OPEN 4); if one is added and it reads earlier days, this changes.
- The only contract model used is `Missing`, imported as `contracts.results.models.Missing` (the class the balance uses). No new missing shape is defined.

## Files

| File | What it holds |
|---|---|
| `__init__.py` | Exports the public names below |
| `curve_number.py` | `CurveNumberConstants`, `PrecipitationValue`, `RunoffDayInput`, `RunoffDayResult`, the identifier and unit string of the precipitation, and the functions below |
| `test_curve_number.py` | The acceptance test: the PROPOSED cases below |

## Functions

```text
potential_retention(curve_number, *, constants) -> float | Missing
initial_abstraction(retention, *, constants) -> float | Missing
runoff_depth(precipitation, curve_number, *, constants) -> float | Missing
runoff_day(day, *, constants, unit_guard_reason) -> RunoffDayResult
run_runoff(days, *, constants, unit_guard_reason) -> list[RunoffDayResult]
```

| Function | What it gives |
|---|---|
| `potential_retention` | The potential maximum retention `S` for a curve number, a depth of water in the depth unit of the precipitation |
| `initial_abstraction` | The initial abstraction `Ia` from the retention |
| `runoff_depth` | The runoff `Q` of one day from its precipitation (a depth, no unit string) and its curve number |
| `runoff_day` | `RunoffDayResult` of one day: `runoff`, `potential_retention`, `initial_abstraction`, with the unit guard on the precipitation |
| `run_runoff` | One `RunoffDayResult` per day of a sequence, in the order given |

All are pure (G1): no file, no network, no clock, no global state; they do not change their arguments, and the same arguments give the same result.

### Inputs

| Argument | What it is |
|---|---|
| `RunoffDayInput.date` | The day (C5.2) |
| `RunoffDayInput.precipitation` | A `PrecipitationValue`: the precipitation of the day (a number or `Missing`) and its unit string, kept when the value is missing (C3.1) |
| `RunoffDayInput.curve_number` | The curve number of the field that day, a number or `Missing`. Which curve number applies is not decided (OPEN 3) |
| `constants` | A `CurveNumberConstants`; each field a number or `Missing` |
| `unit_guard_reason` | The reason code (C3.2) of a precipitation in another unit string; supplied by the caller because Q11 is not decided |

The precipitation must arrive in the unit string of CQ1, `mm day-1` (`PRECIPITATION_UNIT`, transcribed from `contracts/CLIMATE_QUANTITIES.md`; a test checks it against that file's summary table). It is read as the depth of water of the day.

### Output

`RunoffDayResult` with `date`, `runoff`, `potential_retention` and `initial_abstraction`. Each is a number or a `Missing` with its reason, whose `detail` starts with the date of the day. `runoff` is a depth of water over the day in the depth unit of the precipitation, never below zero and never above the precipitation of the day, so it fits the `runoff` field of `engine.water.balance.DayInput` as it is (a test builds that `DayInput` and runs the balance on it, without changing `balance/`). A missing `runoff` given to the balance makes that balance day missing, naming `runoff`, by the balance's own rule R9.

## Source of the forms

Decision D82 of issue #77, PC-6 of `docs/SCIENCE_DECISIONS.md` (finding 8 of the AI pre-check, F42 to F44, question P18): the source of the forms F1 to F3 is

> S11 of `docs/METHODS.md`: USDA Natural Resources Conservation Service (2004). *National Engineering Handbook*, Part 630 Hydrology, Chapter 10: Estimation of Direct Runoff from Storm Rainfall (210-VI-NEH, July 2004).

The AI pre-check of 14 November 2026 read it (pp. 10-3 and 10-4, as S11 records) and found the forms built here to match it algebraically. That is not a person's check: a person opens S11 at its locator and confirms each form and which constant goes where (D34, OPEN 1). The row of S11 in `ATTRIBUTIONS.md` is not written by this unit (OPEN 1).

## Declared adaptation: continuous use

S11 estimates direct runoff from storm rainfall. This folder applies its forms to every day of a continuous daily balance: one runoff per day from that day's precipitation and curve number, fed to `engine/water/balance/` as its daily loss, with no state carried between days. The 2025 edition of Part 630 (Subpart H, section 630.113G, August 2025, as S11 records it) places using the method as a loss in continuous simulation outside its intended use. D82 (PC-6) admits that use and **declares it an adaptation**:

- No result of this folder is presented as a runoff S11 validates for daily continuous use.
- Whether the daily runoff of the balance agrees with observations is for the tests that name runoff (E7, H10; OPEN 8), not for S11.
- Nothing in the code changes with this declaration: the forms, the rules and the cases below are the same.

## PROPOSED forms and rules

Each form is PROPOSED; its source is S11 (D82, PC-6), and a person still checks each form at its locator (D34). The rules are choices of this session that a person accepts or corrects.

| Rule | Statement |
|---|---|
| F1 | Potential retention: `S = retention_unit_factor · (retention_numerator / CN − retention_offset)` |
| F2 | Initial abstraction: `Ia = initial_abstraction_ratio · S` |
| F3 | Runoff: `Q = 0` when `P ≤ Ia`; otherwise `Q = (P − Ia)² / (P − Ia + S)`. The code evaluates it as `(P − Ia) · ((P − Ia) / (P − Ia + S))`, the same expression |
| R1 | **Admissible curve number**, with no number of its own: greater than zero, and its retention by F1 is a finite number not below zero. Outside that, the retention is missing with `NOT_COMPUTABLE`, naming `curve_number`, and nothing is clipped. Whether the method states a narrower range is OPEN 2 |
| R2 | A negative precipitation, a negative initial-abstraction ratio, a non-finite operand, or an overflow gives `NOT_COMPUTABLE`, naming the operand; nothing is clipped. The constants of F1 have their own checks (R9) |
| R3 | **Runoff never above the precipitation.** With `S ≥ 0` (R1) and `Ia ≥ 0` (R2), F3 gives `0 ≤ Q ≤ P − Ia ≤ P`. The order of evaluation in F3 keeps this under floating-point rounding too: the ratio is not above one and `P − Ia` is not above `P`. The rule of the balance that limits runoff to the precipitation (its R6) therefore never acts on this runoff |
| R4 | Missing in, missing out (C3.1, C3.3): a missing precipitation, curve number or constant gives a missing runoff with `MISSING_INPUT`, and its `detail` names every missing operand with its own reason, through the quantity that needs it (for example `potential retention (MISSING_INPUT: input 'curve_number' (NOT_DECLARED))`). Never zero |
| R5 | The precipitation is needed only by the runoff: a missing precipitation leaves the retention and the initial abstraction of the day computed |
| R6 | Order of the checks of a day: moved to OPEN 12; kept in the code |
| R7 | No state from day to day: `run_runoff` is `runoff_day` applied to each day, in the order given; it neither sorts nor checks that the days are consecutive |
| R8 | Which caller defects raise: moved to OPEN 13; kept in the code |
| R9 | **A `retention_numerator` or a `retention_unit_factor` below zero or equal to zero** gives a missing retention with `NOT_COMPUTABLE`, whose `detail` names that constant (`constant '<name>' is below zero`, `constant '<name>' is zero`). A zero unit factor would otherwise give a retention of zero for every curve number, so the whole precipitation would run off silently; a zero or negative numerator would make the failure read as a curve number outside its range. PROPOSED; see OPEN 14 |
| R10 | The constants of F1 are checked before the curve number, so that the reason names the operand that failed. A missing or non-finite operand is still reported first (R4) |

## Constants a person has to transcribe

One row per field of `CurveNumberConstants`. The identifier is the field name, used by the code and in the `detail` of a missing result. The value column stays empty: a person fills it, with the full reference, the locator, the verbatim text and the date read, and one person checks it (D34). Until then the caller passes each constant as `Missing`, and every quantity that needs it is missing, naming it. The source is S11, chapter 10 (D82, PC-6); this session did not read it, so the locator of each constant is for the person who transcribes it.

| Identifier | What it is | Unit | Equation and source | Value |
|---|---|---|---|---|
| `initial_abstraction_ratio` | Ratio of the initial abstraction to the potential retention | None by the form of F2 (a ratio of two depths); a person confirms | F2; S11, chapter 10 (D82); locator OPEN | |
| `retention_numerator` | Number divided by the curve number in the retention formula | OPEN (read with the value in the source) | F1; S11, chapter 10 (D82); locator OPEN | |
| `retention_offset` | Number subtracted from that quotient | OPEN (read with the value in the source) | F1; S11, chapter 10 (D82); locator OPEN | |
| `retention_unit_factor` | Factor that turns the retention of the formula into the depth unit of the precipitation (`mm`, from CQ1) | OPEN: depth unit of the precipitation per depth unit in which the source writes F1 | F1; S11, chapter 10 (D82); locator OPEN | |

## PROPOSED cases

The identifier of a case is the name of its test function in `test_curve_number.py` without `test_`, written with hyphens. Every input value is a PLACEHOLDER. Tolerances are of floating-point rounding only.

### The forms (structure, PLACEHOLDER values)

| Case | What is checked |
|---|---|
| `runoff-follows-the-proposed-forms` | F1 to F3 written out again in the test give the same numbers |
| `runoff-is-zero-when-precipitation-does-not-exceed-the-initial-abstraction` | `Q = 0` for `P` of zero, below `Ia` and equal to `Ia`; `Q > 0` just above |
| `runoff-is-never-above-the-precipitation-of-the-day` | `0 ≤ Q ≤ P` over a grid of precipitations, curve numbers and ratios, the top of the admissible range included |
| `at-zero-retention-runoff-is-the-whole-precipitation-and-not-more` | Where `S = 0`, `Q` equals `P` and never exceeds it, from tiny to huge `P` |
| `runoff-grows-with-precipitation` | Non-decreasing in `P`, strictly increasing once positive |
| `runoff-grows-with-the-curve-number` | Non-decreasing in the curve number over the admissible range |

### Rejected, never clipped

| Case | What is checked |
|---|---|
| `a-curve-number-not-above-zero-is-not-computable` | Zero and negative curve numbers: retention `NOT_COMPUTABLE`, runoff missing, naming `curve_number` |
| `a-curve-number-whose-retention-is-below-zero-is-not-clipped` | Above the top of the range: missing, not the value at the top |
| `a-negative-precipitation-is-not-computable` | `NOT_COMPUTABLE`, naming the precipitation, in `runoff_depth` and `runoff_day` |
| `a-negative-initial-abstraction-ratio-is-not-computable` | `NOT_COMPUTABLE`, naming the ratio (R3) |
| `a-negative-retention-constant-is-not-computable-and-named` | A negative `retention_numerator` or `retention_unit_factor`: `NOT_COMPUTABLE`, naming that constant and not `curve_number` (R9) |
| `a-zero-retention-constant-is-not-computable-and-named` | A zero `retention_numerator` or `retention_unit_factor`: `NOT_COMPUTABLE`, naming that constant; the runoff is not the whole precipitation (R9) |
| `a-retention-constant-is-checked-before-the-curve-number` | With both a bad constant and a bad curve number, the constant is named (R10) |
| `a-negative-retention-given-to-the-initial-abstraction-is-not-computable` | `initial_abstraction` refuses a negative retention |
| `a-non-finite-input-or-constant-is-not-computable` | Infinite, minus infinite and not a number, for the precipitation, the curve number and every constant |
| `an-overflow-is-not-computable` | A retention or a denominator that overflows is `NOT_COMPUTABLE`, not zero |

### Missing in, missing out (C3.1, C3.3)

| Case | What is checked |
|---|---|
| `a-missing-precipitation-gives-a-missing-runoff-that-names-it` | `MISSING_INPUT`, naming the precipitation and its reason; the retention and the initial abstraction stay computed (R5) |
| `a-missing-curve-number-gives-a-missing-runoff-that-names-it` | `MISSING_INPUT`, naming `curve_number` and its reason |
| `a-missing-constant-gives-a-missing-runoff-that-names-it` | For each constant: `MISSING_INPUT`, naming it; also on a day that would give no runoff |
| `every-missing-operand-is-named` | Several missing operands are all named |
| `a-missing-operand-is-reported-before-a-non-finite-one` | Missing first |
| `missing-is-never-zero` | No missing result is zero |

### Unit of the precipitation

| Case | What is checked |
|---|---|
| `the-precipitation-unit-is-that-of-climate-quantities` | Identifier and unit string are those of the CQ1 row of `contracts/CLIMATE_QUANTITIES.md` |
| `a-precipitation-in-another-unit-is-not-converted` | Other unit strings, near spellings included, give the caller's reason code, naming both strings; also on a dry day |
| `the-unit-guard-order-missing-then-unit-then-non-finite` | The order of OPEN 12 |

### One day and a sequence of days

| Case | What is checked |
|---|---|
| `one-day-gives-its-runoff-retention-and-initial-abstraction` | `runoff_day` composes the three functions |
| `a-run-returns-one-result-per-day-in-order` | One result per day, same order, each equal to its own `runoff_day`; a reversed input gives the reversed output |
| `a-missing-day-does-not-stop-the-days-after-it` | Missing days are missing with their date; the days after them are computed (R7) |
| `an-empty-sequence-gives-no-days` | No day in, no day out |

### Integration with `engine/water/balance` (read only)

| Case | What is checked |
|---|---|
| `the-runoff-of-a-day-is-the-runoff-of-a-balance-day` | The `runoff` of a result builds a `DayInput`; the balance applies it unchanged, with no runoff shortfall, and closes its mass balance |
| `a-missing-runoff-makes-the-balance-day-missing-and-named` | A missing runoff makes the balance day missing, naming `runoff` |
| `a-run-of-runoff-feeds-a-run-of-the-balance` | Sixty days of runoff feed `run_balance`; no runoff shortfall on any day |

### Caller defects, purity, rules of the brief

| Case | What is checked |
|---|---|
| `wrong-types-raise-type-error` | The defects of OPEN 13 |
| `a-reason-code-outside-c32-raises-value-error` | The defects of OPEN 13 |
| `same-arguments-give-the-same-result-and-are-not-changed` | G1 |
| `the-module-holds-no-number-other-than-zero` | No constant of the method in the code |
| `no-constant-and-no-public-argument-has-a-default` | No default anywhere |
| `the-module-imports-nothing-that-reads-the-outside` | Only the standard library modules listed and `contracts.results.models` |
| `contract-models-are-imported-as-contracts-folder-module-and-no-missing-is-defined` | Import paths `contracts.<folder>.<module>`; no new missing class |
| `the-readme-lists-every-constant-once-with-an-empty-value` | The table above has one row per constant, every value empty |
| `every-case-is-listed-in-the-readme-and-the-readme-says-no-state-is-carried` | This list is complete, and the README says whether state is carried |

### Skipped, waiting for people

| Case | What it waits for |
|---|---|
| `public-worked-example` | A public worked example of the Curve Number method, transcribed and checked by a person under D34: its inputs (precipitation of the day, curve number), the constants of the table above, the printed runoff, and the tolerance set by the science reviewers. Source CITATION NEEDED. Skipped until `WORKED_EXAMPLE` is filled |
| `the-worked-example-says-what-it-waits-for` | The skip reason names inputs, constants, runoff, tolerance, D34 and CITATION NEEDED |

## OPEN

Each question names the role that answers it.

1. **Forms against their source.** The source is decided: S11, chapter 10 (D82, PC-6). Still open: a person's check that F1 to F3 match it (which constant goes where, whether the runoff equation is written with `P − Ia + S` or another equivalent denominator), at its locator, under D34; and the row of S11 in `ATTRIBUTIONS.md`. *Science reviewers; lead developer for the attribution.*
2. **Admissible range of the curve number.** R1 reads it from F1 alone (greater than zero, retention not below zero). Does the method state a narrower range, and is a value outside it rejected or flagged? *Science reviewers.*
3. **Which curve number applies on each day**: by hydrologic soil group, crop or cover, treatment and condition, and on fallow days and residue cover; where the table comes from; how the soil group is read from the site data (D49). D82 (PC-6) chooses the source of the forms and leaves the table of curve numbers not chosen. Out of scope of this unit. *Science reviewers; lead developer; platform developer for the parameter catalogue (D46, D56, #144).*
4. **Antecedent moisture.** Whether the curve number is adjusted by antecedent moisture or by the soil water of the balance, and with which form. Not built; if it reads earlier days or the balance's storage, the "no state" statement above and R7 change, and the order with the balance's day has to be decided. *Science reviewers; lead developer.*
5. **The value and unit of each constant** of the table above, transcribed under D34 and checked by one person; in particular the unit factor, which depends on the unit in which the source writes F1. *A person or a session under D34 (transcription); science reviewers (check).*
6. **Reason code of the unit guard** (Q11). The caller supplies it. *Lead developer.*
7. **A day whose precipitation is missing.** The runoff is missing and, by the balance's R9, every later balance day is missing too. Gap filling waits for C3.4. *Science reviewers.*
8. **Which test checks the runoff against observations.** E7 and H10 ("contrast case from published runoff plots") name runoff; whether they gate this unit, and H1, H7, H8 the balance with this runoff, is for the science reviewers. *Science reviewers.*
9. **Where the constants come from at run time.** D46 and D56 wait for the platform developer's approval in #144; the caller passes `CurveNumberConstants`. How the catalogue becomes that object is the unit of EP3. *Lead developer, with the platform developer.*
10. **Reading the precipitation from `SiteClimate`.** This unit takes the precipitation of each day as `PrecipitationValue`; a function that reads the `precipitation` series of a `SiteClimate` (with its time zone, C6) belongs with EP3 or a later unit. *Lead developer.* **Built** in EP3 (#135, chained by #165): `engine/water/exposure.py` reads the `precipitation` series of `SiteClimate` and gives this module each day's precipitation as a `PrecipitationValue`.
11. **What the result carries.** No contract carries the daily runoff (Q10 (b) of `contracts/ENTRYPOINTS.md`); no unit string, provenance label (C4.3: `DERIVED` from an `OBSERVED` series) or range is attached here. *Lead developer.*
12. **Order of the checks of a day (former R6).** Not asked by the brief; kept in the code and tested. A missing operand is reported first (`MISSING_INPUT`, naming every one); then a precipitation in another unit string (`unit_guard_reason`, naming both strings, compared exactly); then a non-finite or negative precipitation (`NOT_COMPUTABLE`). Within the retention, the constants of F1 come before the curve number (R10). Is this order wanted? *Lead developer.*
13. **Which caller defects raise (former R8).** Not asked by the brief; kept in the code and tested. `TypeError` for an operand that is neither a number nor `contracts.results.models.Missing` (a boolean, text, `None`, the `Missing` of `contracts/inputs/`), for constants, days or a precipitation of the wrong class, and for a date that is a `datetime`; `ValueError` for a reason code outside C3.2. A missing value never raises. G5 allows `TypeError` for an argument of the wrong type at an entry point; whether an internal unit may raise these, or should answer them by G4, is Q7 of `contracts/ENTRYPOINTS.md`. *Platform developer (Q7); lead developer.*
14. **Sign of the constants of F1 (R9).** PROPOSED: `retention_numerator` and `retention_unit_factor` must be greater than zero. A person confirms this against the source. `retention_offset` has no sign check of its own: a negative offset keeps the retention above zero for every curve number and breaks no guarantee of R3; whether the source allows it is for the same person. *Science reviewers.*

## Not in this unit

The curve number for each soil group, crop, cover or condition; the antecedent-moisture adjustment; the soil-evaporation layer (`engine/water/evaporation/`, another unit); any change to the balance or to EP3; reading the parameter catalogue.
