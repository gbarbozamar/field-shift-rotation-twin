# Calendar engine

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the engines developer, who owns the folder, and the lead developer, as consumer of the rotation calendar.

This folder holds entry point EP2 of `contracts/ENTRYPOINTS.md`:

```text
build_rotation_calendar(rotation: RotationDefinition) -> RotationCalendar
```

It takes one rotation definition (`contracts/rotation_definition/`) and returns its rotation calendar (`contracts/inputs/`), with the result of a feasibility check. It is a pure function (rule G1): no file, no network, no clock; it does not change its argument, and the same argument gives the same result.

**The function invents no date.** Every date of the calendar it returns is a date the definition gives. It also holds no crop list, no threshold, no parameter value and no citation.

**No agronomic calendar rule is checked.** The repository defines none (no sowing window, no minimum interval, no crop sequence), so this engine has none. `feasible: true` means only that the two rules under [PROPOSED rules](#proposed-rules) hold. It says nothing about whether the rotation can be grown. See OPEN, question 1.

Acceptance test, from the repository root:

```bash
python -m pytest engine/calendar/
```

Identifiers such as C3.2 refer to `contracts/CONVENTIONS.md`; EP2, G1 to G7 and Q1 to Q16 refer to `contracts/ENTRYPOINTS.md`.

## Layout

| Path | Content |
|---|---|
| `__init__.py` | Exports `build_rotation_calendar` and the exception `NoValidCalendarForm` |
| `build.py` | The entry point: how a definition becomes a calendar |
| `rules.py` | The feasibility check: the mechanism, and the rules with their identifiers |
| `test_calendar.py` | The acceptance test |

`engine/__init__.py` is an empty file, so that `engine.calendar` is one import path (answer to Q1 in issue #18). The contract models are imported only as `contracts.rotation_definition.<module>` and `contracts.inputs.<module>`.

## What the function returns

| Field of the rotation calendar | Where it comes from |
|---|---|
| `contract` | The text `rotation_calendar` |
| `example_data`, `case_id`, `field_id`, `rotation_id` | The definition, unchanged |
| `ag_year_start` | `ag_year_start` of the definition, copied field by field (P6; D8 of issue #77) |
| `start_date`, `end_date` | The earliest and the latest date placed in the calendar (P4) |
| `feasibility` | The feasibility check (see [PROPOSED rules](#proposed-rules)) |
| `components` | One per component of the definition, in the order of its list (P8) |
| `components[].component_id`, `crop_id` | The component of the definition, unchanged |
| `components[].start` | `sowing` of the component, carried (P1) |
| `components[].end` | `harvest` of the component, carried (P1, P2) |
| `components[].periods` | Empty (P7) |

Not carried, because the rotation calendar has no field for them: `label`, `repeats`, `position` and `purpose`.

## Repetition over the record (`repeat.py`)

`build_rotation_calendar` (EP2) places each component once, and its signature is unchanged (D56). The rotation is repeated over the agricultural years of the climate record after EP2, by `engine/calendar/repeat.py`. That module is a helper of the engines, not an entry point. `repeat_over_record` lays the calendar over the record for EP1, EP3 and EP4, and `phase_calendar` and `list_phases` give the calendar of each phase that the runner moves. **Its rules are in the docstring of `repeat.py`, numbered points 1 to 13, and are not repeated here.** The decisions it builds, in the words its docstring quotes:

- [D47](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346) of issue #77: "a result lists every agricultural year of the climate record, cut by the start month of the case, with the rotation repeated over them". Points 1 to 5 and 7: the years, how a date moves, the length of a cycle, the first and the last cycle, a missing date.
- [D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713): "A component that starts before the first agricultural year of the record and ends inside it keeps its declared dates." Points 11 and 13, for every phase (points 8 to 12 are the phases of D109 and D132).
- [D188](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889974874), part (2), built in [#403](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/403): "the cycle before the first is laid out whenever the first cycle starts after the first day of the record's years, not only when one of its components ends inside them". Points 6 and 13: the cycle before the first (index -1), so every day of the record's years is described.

The questions the repetition leaves are under OPEN at the end of that docstring; Q5 of `contracts/ENTRYPOINTS.md` keeps "how the rotation is repeated" open.

## PROPOSED choices

EP2 does not say how a definition becomes a calendar. For each point below the engine takes the option that invents nothing. Each is a proposal for a person to accept or correct, and each has its question under [OPEN](#open).

**P1. The start of a component is its sowing date and the end is its harvest date.** Each date is carried as the definition gives it: the same date, with the same provenance label, source and assumption mark. Nothing is computed from it. OPEN, questions 2 and 12.

**P2. A date the definition gives as missing is missing in the calendar, with the same reason code and the same detail.** When the harvest is missing, the end of the component is missing; no end is computed. EP2 says a date that cannot be placed has reason `NOT_DECLARED` "when the user did not give what the date needs, otherwise the code of G4 that applies". The engine keeps the code of the definition instead: for `NOT_DECLARED` the two readings agree, and for the other seven codes the engine keeps what the user said. The example of the definition has two such dates: the harvests of the cover crop and the pasture, both `NOT_APPLICABLE`. OPEN, questions 3 and 4.

**P3. A missing date breaks no rule.** Whether a calendar with a missing date can be feasible is question 8 of `contracts/inputs/README.md`, and it is not answered. OPEN, question 9.

**P4. The calendar runs from the earliest to the latest date placed in it.** The definition carries no first and no last day (question 10 of `contracts/rotation_definition/README.md`), and the rotation calendar cannot hold either as missing. These two are the only dates that are in the argument and that satisfy the rule of the model that every date of a component lies inside the calendar. Consequence: when the component that comes last has no end, the calendar ends on the latest date that is known, which is not the end of that component. For the example of the definition, `end_date` is the sowing date of its last component, a pasture that is not harvested. OPEN, question 5.

**P5. `repeats` is not used.** Every component is placed once, at the dates the definition gives, whether `repeats` is true or false. To place a second cycle the engine would have to choose the length of a cycle, move dates and make new component identifiers; none of that is decided. The calendar has no field that says the rotation repeats, so a consumer of the calendar cannot see it. OPEN, question 7.

*Note added after D47, D141 and D188:* P5 still holds for EP2. The repetition over the years of the climate record is done after EP2, by `repeat.py`, whatever `repeats` says: its docstring lists under OPEN (point 3) that "a rotation declared as not repeating is repeated all the same, as D47 says". See [Repetition over the record](#repetition-over-the-record-repeatpy).

**P6. The start month of the agricultural year is copied from the definition.** Decided by D7 and D8 of issue #77: the start month is a required part of the rotation definition, with its provisional mark, and the calendar engine copies it into the calendar. What is PROPOSED here is only how: the engine copies `month`, `provisional`, `provenance`, `source` and `assumption` of the definition's `ag_year_start` into the calendar's `AgYearStart`, each unchanged; nothing is converted or invented. The definition never carries a missing month (D7), so the `missing` part of the calendar's start month stays empty and the engine never writes one. The two models have the same field names and rules, except that the calendar's model also allows a missing month. OPEN, question 6.

**P7. `periods` is empty for every component.** What a period for cover management is, and which types exist, depends on `docs/METHODS.md` M1.5, which is OPEN. Out of scope of this unit. OPEN, question 8.

**P8. The components are listed in the order of the list of the definition.** `position` is not used to order them and is not carried. OPEN, question 11.

**P9. `example_data` is carried from the definition.**

**P10. A date that breaks the rule `harvest_not_before_sowing` is not placed.** The model of the calendar rejects a component that ends before it starts. For such a component both dates are missing in the calendar, with reason `NOT_COMPUTABLE` (EP2: "otherwise the code of G4 that applies"), and the violation names the component. OPEN, question 13.

**P11. The exception `NoValidCalendarForm`.** See [No valid form](#no-valid-form). OPEN, question 14.

**P12. What the engine raises for a caller defect.** `TypeError` when the argument is not an instance of `RotationDefinition` (G5; accepted in issue #18, answer to Q7). The `ValueError` of G5 is for two arguments that name different fields; EP2 has one argument, so the engine never raises it.

## The feasibility check

The mechanism, in `rules.py`:

- A rule (`CalendarRule`) has an identifier and one function. The function reads the rotation definition and returns the places where the rotation breaks the rule.
- Each place (`Finding`) names the components it concerns, or none when the rule concerns the rotation as a whole, and can carry a detail in English.
- `RULES` is the list of rules the entry point checks, in order.
- Every finding becomes one `RuleViolation` of the calendar: the identifier of the rule, the components and the detail. A rotation with no finding is feasible.
- A violation changes nothing else: the calendar is laid out in the same way, except for P10.

A rule is added by writing its function and adding one `CalendarRule` to `RULES`. A person decides the rule and its identifier first.

A rule reads the rotation definition and nothing else. Whether a rule needs site data is part (b) of Q8 and is not decided.

## PROPOSED rules

Both rules, and both identifiers, are proposals. Each repeats a rule that the model of the rotation definition contract states and checks when a definition is loaded.

| Identifier | The rule | Stated in | Names |
|---|---|---|---|
| `harvest_not_before_sowing` | The harvest of a component is not before its sowing. Checked only when both dates are present | `contracts/rotation_definition/README.md`, field `harvest` | The component |
| `positions_number_the_components` | The `position` values are the numbers from 1 to the number of components, none repeated and none skipped | `contracts/rotation_definition/README.md`, field `components` | No component: the rotation as a whole |

**A definition that the route loaded cannot break either rule.** The model rejects both when it loads the definition, and the route answers `422` before any engine is called (issue #18, answer to Q9). A `RotationDefinition` can break them only if it is changed after it was loaded: the models do not check a value that is assigned later. In that case the engine returns a valid calendar with `feasible` false and the violation named, and does not raise.

The contracts state no rule that a loaded definition can break. The test shows the mechanism on a loaded definition with a rule that exists only in the test (case `rule-planted-by-the-test-names-the-rule-and-the-component`).

The third rule of the definition model, that no two components share a `component_id`, is not a rule here: see N3 below.

## No valid form

Cases where the `RotationCalendar` model has no valid form. The engine does not bend the model and invents nothing: it raises `NoValidCalendarForm`. The exception is not a `TypeError` or a `ValueError`, so it is not taken for one of the caller defects of G5. As issue #18 stands, the route answers any exception of an engine with `500` `INTERNAL_ERROR`.

| | The case | Why there is no valid form |
|---|---|---|
| N1 | The definition gives no date: every sowing and every harvest is missing | `start_date` and `end_date` are required and cannot be missing (EP2, Q8). D21 of issue #77 makes this unreachable through the route: the definition model requires at least one present sowing or harvest date, so such a definition does not load and the route answers `422` before any engine is called. A loaded definition reaches it only if it is changed after loading |
| N2 | The definition has no component | The same. D21 also makes this unreachable through the route: a definition with no component has no present date, so the model rejects it (question 9 of `contracts/rotation_definition/README.md`, settled as a consequence of D21). Reached only by changing a loaded definition |
| N3 | Two components share one `component_id` | The calendar rejects two components with one identifier. A loaded definition cannot be in this state; only one changed after loading |

A case of N1 also follows from P10: when the only dates of a definition are the two dates of a component whose harvest is before its sowing, nothing can be placed. That state, too, comes only from a definition changed after loading.

OPEN, question 14.

## PROPOSED cases

The identifier of a case is the name of its test function in `test_calendar.py` without `test_`, written with hyphens. Every date and identifier in the test comes from the PLACEHOLDER example of `contracts/rotation_definition/` or is computed from it.

### The accepted example

| Case | What is checked |
|---|---|
| `example-definition-gives-a-calendar-that-loads-into-its-model` | The example of `contracts/rotation_definition/` goes in; a `RotationCalendar` comes out, and it loads into the model again after being written as JSON. Identifiers, crops and components are those of the definition |
| `example-data-flag-is-carried` | `example_data` false in the definition is false in the calendar |

### Dates

| Case | What is checked |
|---|---|
| `declared-dates-are-carried-unchanged` | Start is the sowing and end is the harvest, with date, label, source, assumption mark and `missing` part equal (P1) |
| `no-date-is-invented` | Every date in the calendar, `start_date` and `end_date` included, is a date of the definition |
| `missing-harvest-stays-missing-with-its-reason` | The harvest of the example that is `NOT_APPLICABLE` gives an end that is missing with the same reason and detail (P2) |
| `missing-date-keeps-its-reason-code` | A sowing or a harvest that is missing with each of the eight codes of C3.2 is missing in the calendar with the same code and detail (P2) |
| `date-with-assumption-mark-keeps-it` | A date with the assumption mark and no source keeps both |
| `calendar-runs-from-the-earliest-to-the-latest-declared-date` | `start_date` and `end_date` of the example (P4) |

### What the definition does not carry

| Case | What is checked |
|---|---|
| `start-month-of-the-agricultural-year-is-copied-from-the-definition` | `ag_year_start` of the calendar is an `AgYearStart` of `contracts.inputs` with the month, the provisional mark, the provenance label, the source and the assumption mark of the definition, and no `missing` part (P6, D8). Checked on the example and on three variants of it: the assumption mark with no source, `provisional` false (not a proposal to allow it: question 28 of `contracts/rotation_definition/README.md`), and the next month of the year |
| `periods-are-empty` | Every component of the example (three) has an empty list of periods (P7) |
| `repeats-changes-nothing` | The calendar is the same with `repeats` true and false, with each component once (P5) |
| `components-keep-the-order-of-the-definition-list` | A definition listed in another order gives a calendar in that order (P8) |

### Feasibility

| Case | What is checked |
|---|---|
| `rotation-that-breaks-no-rule-is-feasible-with-no-violation` | The example: `feasible` true and no violation |
| `harvest-before-sowing-gives-an-infeasible-calendar-not-an-exception` | A definition changed after loading so that a harvest is before its sowing: a valid calendar, `feasible` false, the rule and the component named, both dates of that component missing with `NOT_COMPUTABLE`, the other component placed (P10) |
| `positions-not-numbered-from-one-give-an-infeasible-calendar-not-an-exception` | A definition changed after loading so that two positions are equal: a valid calendar, `feasible` false, the rule named, no component named |
| `two-rules-broken-are-both-named` | Both rules broken: two violations, in the order of `RULES` |
| `rule-planted-by-the-test-names-the-rule-and-the-component` | The mechanism on a loaded definition: rules that exist only in the test give a valid calendar with `feasible` false, each violation with its rule, its components and its detail; a rule with no finding gives no violation; the components are laid out as without the rules |
| `no-rule-while-the-question-is-open` | Four variants that break nothing **only** until a person decides: overlapping components, a harvest on the day of sowing, dates that do not follow the positions, one date missing. No case here is a proposal to allow what it shows (OPEN, questions 9 and 10) |

### Caller defects and the pure function

| Case | What is checked |
|---|---|
| `value-that-is-not-a-rotation-definition-raises-type-error` | A dictionary, JSON text, nothing, the model class, a rotation calendar and one component each raise `TypeError` (G5) |
| `argument-is-not-changed` | The definition is equal before and after the call (G1) |
| `argument-is-not-changed-when-a-rule-is-broken` | The same when the calendar is infeasible |
| `same-argument-gives-the-same-result` | Two calls with one definition, and a call with the example loaded again, give equal calendars |
| `changing-the-result-does-not-change-the-argument` | The calendar shares nothing with the definition |
| `engine-modules-import-nothing-that-reads-a-file-the-network-or-the-clock` | The modules of this folder import only the contract models, `dataclasses`, `collections.abc` and each other |
| `contract-models-are-imported-through-the-contracts-path` | The classes the engine takes and returns are the ones of `contracts.rotation_definition.…` and `contracts.inputs.…`; the `missing` part of the calendar is the one of `contracts/inputs/common.py` |

### No valid form

| Case | What is checked |
|---|---|
| `definition-with-no-date-is-rejected-when-loaded` | A definition whose every sowing and harvest is missing does not load: the model rejects it under D21, so N1 cannot come from the route |
| `definition-with-no-component-is-rejected-when-loaded` | A definition with no component does not load (D21), so N2 cannot come from the route |
| `definition-with-no-date-has-no-valid-calendar` | A loaded definition changed afterwards so that every sowing and harvest is missing: N1 raises `NoValidCalendarForm` |
| `definition-with-no-component-has-no-valid-calendar` | A loaded definition changed afterwards so that it has no component: N2 raises `NoValidCalendarForm` |
| `two-components-with-one-identifier-have-no-valid-calendar` | N3 raises `NoValidCalendarForm` |
| `only-dates-that-cannot-be-placed-have-no-valid-calendar` | The example reduced to its first component (so its position stays valid), whose harvest is changed after loading to fall before its sowing: nothing can be placed (N1 through P10), and `NoValidCalendarForm` is raised |
| `no-valid-form-is-not-one-of-the-caller-defects` | `NoValidCalendarForm` is not a `TypeError` or a `ValueError` |

### This file and the test

| Case | What is checked |
|---|---|
| `readme-lists-the-cases` | The cases in these tables are the test functions, none missing and none extra |
| `readme-lists-the-rules` | The identifiers under "PROPOSED rules" are the ones of `RULES`, in order |

## OPEN

Each item is a question a person has to answer. The role that answers it is named at the end of the item. Until then the engine does what the item says it does today.

1. **Which calendar rules exist, what is the identifier of each, and where does each live?** No agronomic rule is implemented: no sowing window, no minimum interval between components, no crop sequence. `feasible: true` therefore says nothing agronomic. Also: the README of the rotation definition says that a rule, once decided, goes into its model, where a rotation that breaks it does not load (`422`); EP2 says a rotation that breaks a calendar rule gives a calendar with `feasible` false (`200`). Which rules go where? This is question 5 of `contracts/inputs/README.md` and question 13 of `contracts/rotation_definition/README.md`. For the engines developer and the science reviewers; the interface developer for where a rule lives.
2. **Are the sowing date and the harvest date the first and the last day of a calendar component?** Both ends of a component are inclusive in the calendar. Today: start is the sowing date, end is the harvest date (P1). For the engines developer; the science reviewers for what occupies the field on those days.
3. **What ends a component that is not harvested?** The example has one: a cover crop with harvest `NOT_APPLICABLE`. Today its end is missing (P2), so the calendar does not say until when it occupies the field. A termination date is part of question 3 of issue #60 (management details). For the engines developer and the interface developer.
4. **Which reason code does the calendar give to a date that the definition gives as missing with a code other than `NOT_DECLARED`?** Today: the code and the detail of the definition, unchanged (P2). EP2 can be read as asking for a code of G4, which would be `MISSING_INPUT` with a detail that names the date. For the lead developer, as owner of `contracts/ENTRYPOINTS.md`, and the interface developer.
5. **What are the first and the last day of a calendar, and where do they come from?** Part (a) of Q8, question 10 of `contracts/rotation_definition/README.md` and question 6 of `contracts/inputs/README.md`. Today: the earliest and the latest date placed (P4), which is not the span of a cycle and not the years of the climate record. For the lead developer, as owner of lane L1, and the interface developer.
6. **The start month of the agricultural year.** Where it comes from is decided: D7 and D8 of issue #77 put it in the rotation definition, required, with its provisional mark, and the engine copies it (P6). Still open: may the start month be declared not provisional (question 28 of `contracts/rotation_definition/README.md`)? The engine copies the mark as the definition gives it either way. For the lead developer and the science reviewers; the person who declares the case for the month itself.
7. **What does one cycle mean when `repeats` is true?** How long a cycle is, how its dates are moved onto later years, what the `component_id` of a component placed a second time is, and how the calendar says that a rotation repeats: questions 11 and 12 of `contracts/rotation_definition/README.md`, question 6 of `contracts/inputs/README.md`. Today `repeats` is not used (P5). For the engines developer and the interface developer; the lead developer as consumer of the calendar.
   *Status after D47, D141 and D188:* for the repetition over the record, the docstring of `repeat.py` gives how long a cycle is (point 3), how a date is moved onto a later year (point 2), how the cycles are laid out (points 4 to 6, and 13 for the cycle before the first), and the identifier of a component placed again: it keeps the calendar's `component_id` and carries the index of its cycle (`RepeatedComponent.cycle`, the lead-in -1). See [Repetition over the record](#repetition-over-the-record-repeatpy). Still open: how the calendar itself says that a rotation repeats, since `repeats` does not reach it (OPEN of `repeat.py`, point 3), and questions 11 and 12 of `contracts/rotation_definition/README.md`.
8. **What does `periods` hold?** Question 2 of `contracts/inputs/README.md`; it depends on `docs/METHODS.md` M1.5. Today it is empty (P7). For the science reviewers and the lead developer.
9. **Can a calendar with a missing date be feasible?** Question 8 of `contracts/inputs/README.md`. Today a missing date breaks no rule (P3). For the engines developer.
10. **Overlap, order and length of components.** Can two components overlap in time; do the dates have to follow the positions; can a component be harvested on the day it is sown; can a rotation have no component? Questions 6 to 9 of `contracts/rotation_definition/README.md` and question 1 of `contracts/inputs/README.md`. Today the engine has no rule for any of them. For the engines developer and the science reviewers.
11. **In which order does the calendar list its components, and does it carry what the user declared per component?** `position`, `purpose` and `label` are not in the calendar; question 4 of `contracts/inputs/README.md` asks the same. Today: the order of the list of the definition (P8). For the engines developer and the lead developer.
12. **Which provenance label and source does a date of the calendar carry?** Today: those of the definition, unchanged (P1). The example of the rotation calendar labels the end of a component `DERIVED`, as a date computed by the engine; this engine computes none. Questions 15 and 17 of `contracts/rotation_definition/README.md`. For the lead developer.
13. **What does the calendar hold for a component that breaks a rule and cannot be placed?** Today, for a harvest before its sowing: both dates missing with `NOT_COMPUTABLE` (P10). For the lead developer.
14. **What does EP2 return when the calendar has no valid form?** Cases N1 to N3. EP2 says the function always returns a `RotationCalendar` and raises only for a caller defect; for these cases the model has no valid instance. D21 of issue #77 made a definition without a present date an invalid request: N1 and N2 are now rejected when the definition is loaded, and the route answers `422` without calling the engine, as it already did for N3. All three can now arise only from a definition changed after loading (question 15). Today the engine raises `NoValidCalendarForm` for them, which the route would answer with `500`. Still open: is raising the right answer for such a state, and is the name `NoValidCalendarForm` part of what `engine.calendar` exports? For the lead developer; the platform developer for the answer of the route.
15. **Does the engine check again what the model of the definition already checks?** G3 says an argument is already validated. Today the engine checks the three rules of the definition model again, so that a definition changed after loading gives an infeasible calendar or `NoValidCalendarForm` and not an error of the calendar model. Any other state that the definition model would reject is not handled. For the lead developer and the platform developer.
16. **Does any calendar rule need site data?** Part (b) of Q8. Today a rule reads the rotation definition only. For the lead developer and the science reviewers.
17. **The import path.** The engine recognises a `RotationDefinition` only when its class was loaded as `contracts.rotation_definition.rotation_definition`. `contracts/__init__.py` does not exist yet (Q1, answered in issue #18 and not landed), and the tests of the contract folders still load the same files under other names. An instance built from a class loaded under another name raises `TypeError`. For the platform developer and the lead developer.
18. **The crop vocabulary.** `crop_id` is carried as any text (question 1 of issue #60). For the engines developer; the lead developer for a list in `params/`.
