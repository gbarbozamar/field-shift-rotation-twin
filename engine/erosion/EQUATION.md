# Annual soil-loss product

`engine/erosion/equation.py`: the product of the five factors of `docs/METHODS.md` M1.1, with a unit guard. Unit `l0/erosion-equation` (issue #72), first unit of the erosion engine in blueprint section 8, Block 1.

**[E8] and [E9] are decided.** [D226 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893024804) says what each one checks: E8, the unit guard, is cases EQ6, EQ8 and EQ10 of `engine/erosion/test_equation.py`; E9, the invariants, is cases EQ1 to EQ5 and EQ7. The entries [E8](../../docs/VALIDATION.md#e8) and [E9](../../docs/VALIDATION.md#e9) of `docs/VALIDATION.md` were written by [#367](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/367). In the third (`9410a92`, #405) and fourth (`df43899`, #463) recorded runs of the suite, their cases ran and passed: 154 results of E8 and 218 of E9 in `validation/results/` (alongside passing [E0], [E2] and [E3] checks in Run #4; [E1a] and [E1b] are not evaluated in this release under D254, and [E7] has no pass rule under D252). Their logic is DECIDED under D161; acceptance by a science reviewer is pending. The questions D226 leaves open are still in [OPEN](#open). See [Relation to entries E8 and E9](#relation-to-entries-e8-and-e9-of-the-validation-protocol).

## How to read this file

- This file, the module and its test were written by a builder session (blueprint section 3.7). Everything marked `PROPOSED` is a proposal of the session and takes effect only when a person approves the pull request. It is a science-class change (blueprint section 3.6), so it also needs a science reviewer.
- `OPEN` marks what the session could not responsibly propose. Each item under [OPEN](#open) is a question with the role that answers it.
- This file, the module and the test hold **no parameter value, no unit of the method, no threshold, no expected value of the science and no citation**. Every number and every unit string in the test is a `PLACEHOLDER` and means nothing.
- Identifiers such as C3.3, G4, Q11 and M1.7 refer to `contracts/CONVENTIONS.md`, `contracts/ENTRYPOINTS.md` and `docs/METHODS.md`.

## What the module holds

Status: PROPOSED

```text
annual_soil_loss(
    *,
    r: Factor,
    k: Factor,
    ls: Factor,
    c: Factor,
    p: Factor,
    accepted_units: AcceptedUnits,
    unit_guard_reason: ReasonCode,
) -> float | Missing
```

| Name | What it is |
|---|---|
| `annual_soil_loss` | The one function. It multiplies the five factors of M1.1 and nothing else |
| `Factor` | A frozen dataclass of this module: `value` (a number, or a `Missing` with the reason the factor has no number) and `unit` (the unit string the factor arrives in, kept when the value is missing, C3.1) |
| `AcceptedUnits` | A frozen dataclass of this module with five fields, `r`, `k`, `ls`, `c`, `p`: the one unit string the product accepts for each factor |
| `Missing`, `ReasonCode` | Existing contract model and vocabulary: file `contracts/results/models.py`, imported as `contracts.results.models`. The module defines no `Missing` of its own |
| `FACTOR_NAMES` | The five names in the order M1.1 writes the product |

- Every argument is keyword-only and none has a default. No field of `AcceptedUnits` or `Factor` has a default.
- The function is pure: no file, no network, no clock, no global state. It does not change its arguments, and the same arguments give the same result.
- It is not the entry point `compute_soil_loss` (EP1) and it is not called by the route. It computes no factor and reads no parameter.

## What the function returns

Status: PROPOSED. The column "Asked by" says where each row comes from. A row marked "this unit" is a reading or a choice of the session that no document states in these words: a person accepts or corrects it.

| Case | Result | Asked by |
|---|---|---|
| Every factor is a finite number in its accepted unit string | The product, a `float`. The factors are multiplied in the order of M1.1, whatever the order of the arguments | M1.1; brief |
| A factor is zero and the other four are finite numbers in their accepted units | Zero, as the product gives it | Brief |
| A factor has no number (`Factor.value` is a `Missing`) | `Missing`, reason `MISSING_INPUT`. `detail` names every missing factor, each with its own reason code and its own detail. Never zero | C3.1, C3.3; G4; brief |
| A factor is in a unit string that is not the accepted one for that factor | `Missing`, reason `unit_guard_reason`, the code the caller supplies. `detail` names every such factor, with the unit string received and the one accepted. No factor is multiplied | C1.1; G4, G5; brief. The reason code is not decided (Q11), so it is an argument |
| A factor is not a finite number ("not a number", or infinite) | `Missing`, reason `NOT_COMPUTABLE`. `detail` names every such factor. No factor is multiplied | Brief ("is not multiplied"). The reason code is a reading of G4 by this unit: see OPEN 3 |
| Every factor is finite and the product is not (it is beyond the largest float) | `Missing`, reason `NOT_COMPUTABLE` | This unit: see OPEN 3. Without it the function would return infinity, which no results model accepts |
| More than one of the three cases above at once | The first that applies, in this order: missing factor, unit, not finite. `detail` covers that case only | This unit: see OPEN 7 |
| An argument is not of the type the signature names: a factor that is not a `Factor`; a value that is neither a number nor the `Missing` of `contracts/results/models.py` (a boolean, text, `None` and the `Missing` of `contracts/inputs/common.py` are none of them); a unit that is not a string; `accepted_units` that is not an `AcceptedUnits` | `TypeError` | This unit, after G5 and the answer to Q7 in issue #18, which are written for entry points: see OPEN 8 |
| `unit_guard_reason` is not a reason code of C3.2 | `ValueError`, also when no unit is wrong | This unit: see OPEN 8 |

What the unit guard is and is not:

- Unit strings are compared exactly as written (C1.1): no change of case, no removal of spaces, no conversion.
- The function does not know what a unit string means. It does not check that the accepted unit strings, multiplied, give the unit of the result.
- The function attaches no unit to the product. The product is in the unit of convention C1.2 only if the accepted unit strings, written by a person, make it so (M1.7).

Not done by this function, because no document asks for it (brief: "do not add a rule"):

- A negative factor is multiplied like any other number (OPEN 4).
- An empty unit string is compared like any other string (OPEN 9).
- A whole number (`int`) is accepted as the number of a factor and multiplied as a float.

## PROPOSED cases

Status: PROPOSED (blueprint section 3.7). The codes are the ones in the names of the tests of `engine/erosion/test_equation.py`. Run with `python -m pytest engine/erosion/test_equation.py` from the repository root.

Every number is a `PLACEHOLDER` chosen so that each product is exact and can be checked by hand; every unit string contains the word `PLACEHOLDER`. No case holds an expected value of the science.

| Code | What it checks | Line of the brief |
|---|---|---|
| EQ1a | The product of five different primes is their product, a `float` (worked by hand in the test file) | Product of five factors |
| EQ1b | The same with fractions that are exact in a float | Product of five factors |
| EQ1c | Whole numbers give the same product as floats | — |
| EQ1d | Setting any one factor to one divides the product by that factor: every factor takes part | Product of five factors |
| EQ2a | Any one factor equal to zero gives zero, as a `float`, not a `Missing` | Zero gives zero |
| EQ2b | Every factor equal to zero gives zero | Zero gives zero |
| EQ3 | Multiplying any one factor by a number multiplies the result by that number, for each factor, three numbers and two sets of factors | Multiplying one factor |
| EQ4a | The five named factors given in each of their possible orders give the same product | Order of the factors |
| EQ4b | The same for a result that is missing: missing factors, units and non-finite factors give the same `Missing`, with the same `detail`, in every order | Order of the factors |
| EQ4c | The order in which the fields of `AcceptedUnits` are given does not matter | Order of the factors |
| EQ5a | Any one factor missing, with each reason code of C3.2: the result is a `Missing` with reason `MISSING_INPUT`; `detail` names that factor and no other, and carries the reason code and the detail of the factor | Missing factor |
| EQ5b | The same for a missing factor that has no detail | Missing factor |
| EQ5c | Two factors missing: both are named, in the order of M1.1 | Missing factor |
| EQ5d | All five missing: all five are named | Missing factor |
| EQ5e | A zero factor next to a missing factor gives a missing result, not zero | Missing factor, "never zero" |
| EQ6a | Any one factor in another unit string, with each reason code of C3.2 as `unit_guard_reason`: the result is a `Missing` with that reason; `detail` names that factor and no other, and both unit strings | Unit guard |
| EQ6b | A unit string that differs only in case or in a space is not accepted | Unit guard |
| EQ6c | The accepted unit of one factor is not accepted for another factor: two factors with their unit strings swapped are both named | Unit guard |
| EQ6d | The same factors are multiplied or not according to `accepted_units` alone: nothing in the module accepts a unit | Unit guard; "no default" |
| EQ6e | A zero factor next to a factor in another unit gives a missing result, not zero | Unit guard |
| EQ6f | A factor that is zero and in another unit is not multiplied | Unit guard |
| EQ7a | Any one factor that is "not a number", plus infinity or minus infinity: the result is a `Missing` with reason `NOT_COMPUTABLE` that names that factor and no other | Not a finite number |
| EQ7b | A zero factor next to a non-finite factor gives a missing result, not zero | Not a finite number |
| EQ7c | A whole number too large to be a float is not multiplied | Not a finite number |
| EQ7d | Finite factors whose product is beyond the largest float give a `Missing` with reason `NOT_COMPUTABLE` | — (this unit) |
| EQ8a | A missing factor and a factor in another unit: reported as `MISSING_INPUT`, naming the missing factor only | — (this unit) |
| EQ8b | A factor in another unit and a non-finite factor: reported with `unit_guard_reason`, naming the factor in another unit only | — (this unit) |
| EQ8c | A missing factor whose unit string is not the accepted one: reported as `MISSING_INPUT` | — (this unit) |
| EQ9a | An argument that is not a `Factor` (a bare number, `None`, a tuple, a bare `Missing`) raises `TypeError` naming the argument | — (this unit) |
| EQ9b | A value that is neither a number nor the `Missing` of the results contract (`None`, text, a boolean, the `Missing` of the input contracts) raises `TypeError` | — (this unit) |
| EQ9c | A unit, or an accepted unit, that is not a string raises `TypeError` | — (this unit) |
| EQ9d | `accepted_units` given as a dictionary raises `TypeError` | — (this unit) |
| EQ9e | A `unit_guard_reason` outside C3.2 raises `ValueError`, also when every unit is the accepted one | — (this unit) |
| EQ10a | Every argument of the function is keyword-only and has no default | "No default" |
| EQ10b | Leaving any argument out raises `TypeError` | "No default" |
| EQ10c | No field of `AcceptedUnits` or `Factor` has a default | "No default" |
| EQ11a | The arguments are unchanged after a call and a second call gives the same result | Pure function |
| EQ11b | `equation.py` contains no number at all | "No real number" |
| EQ11c | `equation.py` contains none of the unit strings that `contracts/results/models.py` names for the indicators | "No real unit string" |
| EQ11d | `equation.py` imports only the standard modules `__future__`, `math`, `dataclasses` and `typing`, and `contracts.results.models` | Pure function; import path |
| EQ11e | Every unit string of the test contains the word `PLACEHOLDER`, and the five accepted ones differ from each other | "No real unit string" |

Not tested, on purpose: a negative factor (OPEN 4), an empty unit string (OPEN 9), and how a range passes through the product (OPEN 5).

## Relation to entries E8 and E9 of the validation protocol

`docs/VALIDATION.md` gives E8 the wording "unit guard [E8]" and E9 the wording "invariants [E9]", both gating this unit.

**Decided by [D226 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893024804)** (15 November 2026, taken by the orchestrating AI session under the delegation of D161, before any result on real data was seen): "E8 is cases EQ6, EQ8 and EQ10 of `engine/erosion/test_equation.py`; E9 is cases EQ1 to EQ5 and EQ7." D226 names these cases as the definition and changes no case. The entries [E8](../../docs/VALIDATION.md#e8) and [E9](../../docs/VALIDATION.md#e9) of `docs/VALIDATION.md`, written by [#367](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/367), give each its definition, its test functions and its status: logic DECIDED under D161, acceptance by a science reviewer pending. Both entries ran and passed all 154 (E8) and 218 (E9) cases in Run #3 (`9410a92`, #405) and Run #4 (`df43899`, #463) in `validation/results/`. D226 leaves open the accepted unit strings (OPEN 1), the reason code of the guard (OPEN 2, Q11) and a negative factor (OPEN 4).

*As first written, before D226:* In both entries the definition, the expected value, the tolerance and the source are `OPEN`, and the status is `not defined`. The science reviewers own that file.

- Cases EQ6a to EQ6f, with EQ8 and EQ10, are the design this unit proposes for what "unit guard" checks.
- Cases EQ1 to EQ5 and EQ7 are the design this unit proposes for what "invariants" checks.
- EQ9 and EQ11 belong to neither wording: they check the brief (types, purity, no number and no unit in the module).

*As first written, before D226 (superseded by D226 and #367):* These cases did not yet define E8 or E9, and this unit had not edited `docs/VALIDATION.md` or written records under `validation/`. Since D226 and #367, `docs/VALIDATION.md` lists these cases as the tests of E8 and E9 and their outcomes are recorded in `validation/results/` (Runs #3 and #4), while acceptance by a science reviewer remains pending. Neither entry holds an expected value from this unit: every number in the test is a placeholder.

## OPEN

Each item is a question a person can answer. The role that answers it is named at the end of the item.

1. **Which unit string is the accepted one for each of the five factors?** M1.7 says the unit strings of `R` and `K` are `OPEN` until a person writes them in the parameter catalogue with their source; `docs/METHODS.md` gives no unit string for `LS`, `C` and `P` either. The function takes all five from its caller and holds none. It also does not check that the five accepted units, multiplied, give the unit of the result that C1.2 fixes: a person checks that when the strings are written. For the science reviewers (decision rights: data, unit); the lead developer for where in `params/` they are stored.

2. **Which reason code does the unit guard use?** This is Q11 of `contracts/ENTRYPOINTS.md`, not decided. Until it is, the code is the argument `unit_guard_reason`, with no default, and the function accepts any code of C3.2. When it is decided, the argument can become a fixed code. For the lead developer.

3. **Is a factor that is not a finite number a missing result or a defect?** The brief says it "is not multiplied" and does not say what is returned. The module returns a `Missing` with reason `NOT_COMPUTABLE`, reading the row of G4 "the inputs are present and the method does not cover the case", so that the engine never raises for it (G5). The other reading is that such a number can only come from a defect inside the engine, since the contract models reject it, and the function should raise. The same question holds for a product that is not finite although every factor is. A product that rounds to zero although no factor is zero is not looked at. For the lead developer.

4. **What is a negative factor?** A defect of the caller, a missing value, or a number like any other? The brief leaves it open. The module adds no rule: a negative factor is multiplied, and no test covers it. For the science reviewers (whether a negative factor has a meaning in the method); the lead developer for what the engine then does.

5. **How does an uncertainty range pass through the product?** Out of scope of this unit and not implemented: `Factor` carries no range and the result is a bare number. Which meaning a range has is `OPEN` in C2.3, and who gives a value its range is Q6 of `contracts/ENTRYPOINTS.md`. Until it is answered, the caller that turns this product into a value of the results contract has to say why it has no range (C2.2). For the science reviewers.

6. **Is `Factor` the right shape for a factor, and which `Missing` does it carry?** `Factor` is a small type of this module, not a contract: a number or a `Missing`, and a unit string. The contract value of `contracts/inputs/common.py` was not used because it asks every value for a range, a provenance label and a source, which are out of scope here (OPEN 5, OPEN 10), and because it cannot hold a number that is not finite, which the brief asks this function to answer. The missing part is the `Missing` of `contracts/results/models.py`, the one the table of types of `contracts/ENTRYPOINTS.md` names for the erosion engine; a factor read from an input contract carries the other `Missing` (`contracts/inputs/common.py`) and its caller has to rewrite it. One shared value shape is question 24 of `contracts/inputs/README.md` and question 19 of `contracts/results/README.md`. For the lead developer.

7. **Which reason is reported when more than one applies, and with which words?** The module reports a missing factor before a unit that is not accepted, and that before a number that is not finite; `detail` lists the factors of the reported case only. The text of `detail` is developer text in English, written by the session. For the lead developer.

8. **May a function inside an engine raise for a defect of its caller?** G5 and the answer to Q7 in issue #18 allow `TypeError` and `ValueError` to an entry point, for two named defects. This function is not an entry point; it raises `TypeError` for an argument of the wrong type and `ValueError` for a `unit_guard_reason` outside C3.2. Every exception that leaves an engine is answered `500` by the route (issue #18), so `compute_soil_loss` has to call this function in a way that cannot raise. Also proposed here without a document asking: a boolean is not a number, and a whole number is. For the lead developer.

9. **Is an empty unit string a defect of the caller?** The module compares it like any other string, so an empty accepted unit accepts a factor whose unit is empty. For the lead developer.

10. **Who turns the product into a value of the results contract?** `AnnualSoilLoss` (`contracts/results/models.py`) needs the unit of C1.2, the label `DERIVED` (C4.6), a source or the assumption mark, and a range or the reason it has none. What `source` holds for a computed indicator is question 11 of `contracts/results/README.md`. That belongs to the entry point `compute_soil_loss`, out of scope here. For the lead developer.

11. **How do the accepted unit strings reach the function at run time?** They are written in the parameter catalogue (M1.7), and how values of the catalogue reach an engine is Q3 of `contracts/ENTRYPOINTS.md`. For the lead developer and the platform developer.

12. **What do E8 and E9 mean?** **Answered by [D226](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893024804):** E8 is cases EQ6, EQ8 and EQ10, E9 is cases EQ1 to EQ5 and EQ7 (the entries in `docs/VALIDATION.md`, [#367](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/367)). Still open: acceptance by a science reviewer, and OPEN 1, 2 and 4, which D226 leaves open. *As first written:* See the section above. For the science reviewers.

## Not covered by this unit

- Computing `R`, `K`, `LS`, `C` or `P`. In particular the function does not set `P` to its default of M1.6: the caller supplies `p` like every other factor.
- The entry point `compute_soil_loss`, the monthly breakdown, reading the parameter catalogue and writing validation records.
- Arithmetic limits of floats beyond the two cases named above. The factors are multiplied in the order of M1.1, so the same five named factors always give the same product; exchanging the numbers of two factors can change the last digit of a product that is not exact.
