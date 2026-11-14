# Rotation definition contract

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the engines developer, as consumer of the contract, and the interface developer, as its producer, who accepts or contests the [differences from the producer's example](#differences-from-the-producers-example).

This folder holds a Pydantic model and one example of the "Rotation definition" contract of blueprint section 5: what the user declares for one rotation on one field.

| Contract | Producer → consumer | Model | Example |
|---|---|---|---|
| Rotation definition | Interface → Engines | `rotation_definition.RotationDefinition` | `examples/PLACEHOLDER_rotation_definition.json` |

The producer proposed the example, its design choices and five open questions in issue #60. A builder session of lane L0 landed it here, as the open decision of blueprint section 5 says. The example of the issue is the source: its fields, its names and its design choices are kept, except where `contracts/CONVENTIONS.md` requires otherwise. Identifiers such as C3.1 below refer to that sheet.

**The example is PLACEHOLDER data.** Every date and identifier in it is illustrative. It describes no real place, no real field and no real producer, and it says `"example_data": true`. The crops are not crops: `crop_id` holds the word PLACEHOLDER.

Acceptance test, from the repository root:

```bash
python -m pytest contracts/rotation_definition/
```

Models and pure validation only. No network calls, no parameter values, no thresholds, no citations, no crop list, no calendar rule. The models import nothing from `params/`, from `validation/` or from another contract folder.

## Layout

| Path | Content |
|---|---|
| `rotation_definition.py` | `RotationDefinition` and `RotationComponent` |
| `common.py` | The date value, its `missing` part and the provenance label. They repeat `contracts/inputs/common.py`; see OPEN, question 19 |
| `examples/PLACEHOLDER_rotation_definition.json` | The example |
| `test_examples.py` | The acceptance test |

## Field list

All PROPOSED. Every model rejects unknown fields and does not coerce types: a number written as text is rejected. No field of the definition or of a component has a default: each one that the producer's example carries is required.

### `RotationDefinition`: one rotation on one field

| Field | Type | Rule |
|---|---|---|
| `contract` | `"rotation_definition"` | Required |
| `example_data` | true or false | Required. True for example data |
| `case_id`, `field_id`, `rotation_id` | text | Required, not blank |
| `label` | text | Required, not blank. Issue #60 does not describe it further; see OPEN, question 16 |
| `repeats` | true or false | Required. True: the cycle starts over after the last component (issue #60) |
| `components` | list of `RotationComponent` | Required. `component_id` is unique in the list. The `position` values are the numbers from 1 to the number of components, none repeated and none skipped |

### `RotationComponent`: one component of the cycle

| Field | Type | Rule |
|---|---|---|
| `component_id` | text | Required, not blank |
| `position` | integer | Required. Numbers the components inside the cycle, from 1 (issue #60) |
| `crop_id` | text | Required, not blank. Any text is accepted |
| `purpose` | `grain`, `cover` or `pasture` | Required. The closed list that issue #60 proposes |
| `sowing` | `DateValue` | Required. Can be missing with its reason |
| `harvest` | `DateValue` | Required. Can be missing with its reason. Not before `sowing`; checked only when both dates are present |

### `DateValue`: a date, or missing with its reason

The shape issue #60 names: `date`, `missing`, `provenance`, `source`, `assumption`.

| Field | Type | Rule |
|---|---|---|
| `date` | `YYYY-MM-DD` or null | Required key. Null when missing (C3.1, C5.2). A day-of-year number or a date with a time is rejected |
| `missing` | `Missing` | Present exactly when `date` is null (C3.1) |
| `provenance` | `DECLARED`, `OBSERVED`, `DERIVED` or `SIMULATED` | Required when there is a date; absent when missing (C4.1) |
| `source` | text | Reference to the source (C4.2). A date carries `source`, or `assumption: true`, or both |
| `assumption` | true or false | The explicit "assumption" mark (C4.2). False when left out. Never true on a missing date |

A date that is present:

```json
{ "date": "2027-11-15", "provenance": "DECLARED", "source": "user" }
```

A date that is missing:

```json
{ "date": null, "missing": { "reason": "NOT_DECLARED" } }
```

### `Missing`

| Field | Type | Rule |
|---|---|---|
| `reason` | one of the eight codes of C3.2 | Required |
| `detail` | text | Optional, in English. Required with reason `MISSING_INPUT`, where it names the input (C3.2) |

### What carries no provenance label

Only the two dates of a component carry a provenance label and a source, as in issue #60. Identifiers, the `example_data` flag, `label`, `repeats`, `position`, `crop_id` and `purpose` carry none. This follows the line drawn in `contracts/inputs/README.md`; whether it is the right line for what the user declares is OPEN, question 15.

### Placeholders for open questions

The model answers none of the five questions of issue #60. Where it had to take a shape, the shape is a placeholder:

| In the model | Placeholder for |
|---|---|
| `crop_id` accepts any text that is not blank | Question 1: the crop vocabulary |
| `sowing` and `harvest` are exact dates, as in the example | Question 2: exact dates or windows |
| A component has no field for residue handling, grazing or termination | Question 3: management details |
| The definition has no `template_id`; components are always written out | Question 4: templates |
| `purpose` is the list `grain` / `cover` / `pasture`, and a pasture component has no field of its own | Question 5: the `purpose` list |

## PROPOSED cases

Every case below is a change to the example, made in memory. The invalid ones must be rejected; the test also checks that each is rejected for the stated reason. The identifiers are the test identifiers in `test_examples.py`.

### Rejected: a date and its missing part

| Case | The variant |
|---|---|
| `date-without-provenance-label` | A date has no `provenance` (C4.1) |
| `provenance-label-in-lower-case` | `provenance` is written in lower case (C4.1) |
| `provenance-label-outside-the-four` | `provenance` is not one of the four labels (C4.1) |
| `date-without-source-or-assumption-mark` | A date has neither `source` nor the assumption mark (C4.2) |
| `missing-date-without-reason` | A date is null and has no `missing` part (C3.1) |
| `missing-part-without-reason-code` | A `missing` part has no `reason` (C3.1) |
| `missing-date-with-reason-code-not-in-the-sheet` | `reason` is a code that C3.2 does not define |
| `missing-input-without-detail` | Reason `MISSING_INPUT` without the `detail` that names the input (C3.2) |
| `missing-date-with-provenance-label` | A missing date carries a provenance label (C4.1) |
| `missing-date-marked-as-assumption` | A missing date carries the assumption mark (the date value of `contracts/inputs/`, which issue #60 names) |
| `date-together-with-a-missing-part` | A date that is present also carries a `missing` part (C3.1) |
| `missing-part-beside-a-null-harvest` | `harvest` is null and the `missing` part sits in the component, as issue #60 wrote it (C3.1; see the differences below) |
| `missing-date-left-out` | `harvest` is left out instead of being sent as missing |
| `date-not-written-as-year-month-day` | A date is written day, month, year (C5.2) |
| `date-written-as-day-of-year` | A date is written as year and day of year (C5.2) |
| `date-with-a-time` | A date carries a time of day (C5.2) |
| `date-unknown-extra-field` | An unknown field inside a date |

### Rejected: a component

| Case | The variant |
|---|---|
| `harvest-before-its-sowing` | The harvest date of a component is before its sowing date |
| `purpose-outside-the-proposed-list` | `purpose` is not `grain`, `cover` or `pasture` |
| `component-without-crop-identifier` | A component has no `crop_id` |
| `crop-identifier-blank` | `crop_id` is only white space |
| `position-written-as-text` | `position` is a number written as text |
| `component-unknown-extra-field` | An unknown field inside a component |

### Rejected: the definition

| Case | The variant |
|---|---|
| `two-components-with-one-identifier` | Two components share one `component_id` |
| `positions-repeat-a-number` | Two components have the same `position` |
| `positions-skip-a-number` | The positions of two components are 1 and 3 |
| `positions-start-at-zero` | The positions of two components are 0 and 1 |
| `definition-unknown-extra-field` | An unknown field at the top of the record |
| `definition-without-example-data-flag` | `example_data` is left out |
| `definition-without-repeats` | `repeats` is left out |
| `definition-with-another-contract-identifier` | `contract` names another contract |

### Accepted

These variants stay valid. They show shapes that the example does not contain.

| Case | The variant |
|---|---|
| `accepted-sowing-not-declared` | The sowing date is missing with reason `NOT_DECLARED`: "not decided yet" travels as missing, never as an invented date (issue #60) |
| `accepted-date-with-assumption-mark-and-no-source` | A date carries `assumption: true` in place of `source` (C4.2) |
| `accepted-rotation-that-does-not-repeat` | `repeats` is false |

### Accepted only while a question is open

The model does not reject these variants **only** until a person decides. No case here is a proposal to allow what it shows. When the question is answered with a rule, the model gains the rule and the case becomes a rejected one.

| Case | The variant | Question under OPEN |
|---|---|---|
| `accepted-while-open-crop-identifier-as-any-text` | `crop_id` is text taken from no list | 1 |
| `accepted-while-open-overlapping-components` | The second component is sown before the first is harvested. Neither the conventions sheet nor the blueprint forbids or allows it | 6 |
| `accepted-while-open-components-not-listed-by-position` | The first component in the list has position 2 and the second has position 1, so neither the list nor the dates follow the positions | 7 |
| `accepted-while-open-harvest-on-the-day-of-sowing` | A component is harvested on the day it is sown | 8 |
| `accepted-while-open-definition-without-components` | The list of components is empty | 9 |

### Checked without a case of their own

- No field of the definition or of a component can be left out: the test leaves out each one in turn and each variant is rejected.
- A missing date is accepted with any of the eight reason codes of C3.2. The model does not say which code fits which date (OPEN, question 18).
- The reason codes and the provenance labels in `common.py` are the ones of the tables of C3.2 and C4.1, read from the sheet by the test.
- The example of issue #60, as the producer wrote it, is rejected, and it equals the landed example once the `missing` part is moved inside `harvest`.

## Differences from the producer's example

For the interface developer, to accept or to contest. There is one difference. The test holds the example of issue #60 as written and checks that there is no other.

### 1. A missing harvest carries its `missing` part inside `harvest`

Issue #60 writes the harvest of the second component as a null, with the `missing` part next to it, at the level of the component:

```json
"harvest": null,
"missing": { "reason": "NOT_APPLICABLE", "detail": "cover crop is terminated, not harvested" }
```

The landed example writes it as a date value that holds the null date and its `missing` part:

```json
"harvest": {
  "date": null,
  "missing": { "reason": "NOT_APPLICABLE", "detail": "cover crop is terminated, not harvested" }
}
```

Why: C3.1 says a missing value travels as an empty value together with a `missing` part, that one item holds either the value or the `missing` part, and that a missing value keeps its identifier, so a consumer knows what is missing. With the `missing` part in the component, nothing says which of the two dates it belongs to, and a component whose two dates are both missing could give only one reason. It is also the shape the issue itself names for dates (`date`, `missing`, `provenance`, `source`, `assumption`), and the shape of a missing date in `contracts/inputs/`. The reason code and the detail are unchanged.

Consequences in the model: a component has no `missing` field, and `harvest` is never a bare null. The shape of the issue is the rejected case `missing-part-beside-a-null-harvest`.

### Checked and kept

- **The reason code `NOT_APPLICABLE`** is one of the eight codes of C3.2, so it stays. The model does not decide whether it is the right code for a component that is not harvested (OPEN, question 18).
- **The identifiers** `example-case`, `example-field-1`, `example-rotation-1`, `c1` and `c2` stay as the producer wrote them. The examples of `contracts/inputs/` and `contracts/results/` put the word PLACEHOLDER in every identifier; the sheet does not ask for it, so this example was not changed. Here the word is in the file name and in both `crop_id` values.
- **The source `"user"`** stays. The format of `source` is not decided (OPEN, question 17).
- **The dates** stay. They are illustrative.

Not in issue #60 and added by the landing: the file name `PLACEHOLDER_rotation_definition.json`. The file is laid out over more lines than in the issue; its content is the same.

## OPEN

Each item is a question a person has to answer. The role that answers it is named at the end of the item.

### The five questions of issue #60

Copied from the issue. They stay open; the model answers none of them (see [Placeholders for open questions](#placeholders-for-open-questions)).

1. **Crop vocabulary**: where do `crop_id` values come from — a closed list in `params/`, or free text? The engines and the C-factor must recognise them. For the engines developer; the lead developer for a list in `params/`.
2. **Exact dates vs windows**: does the user declare exact sowing/harvest dates, or a window / relative rule that the calendar engine resolves into the exact dates of PR #54? For the engines developer, agreed with the interface developer.
3. **Management details**: do residue handling, grazing or cover-crop termination travel in this contract, in a separate management contract, or stay out of the event core? For the engines developer, agreed with the interface developer.
4. **Templates**: may the interface submit a `template_id` that the engines expand, or always inline components? (Affects whether the rotation ribbon is display-only or editable — an open L3 scope decision.) For the engines developer; the interface developer for the scope of the ribbon.
5. **`purpose` list**: is `grain` / `cover` / `pasture` the right closed list, and do pasture components need extra fields (e.g. grazing), or is that out of the event core? For the engines developer, agreed with the interface developer.

### Rules the model does not enforce

Neither the brief of this unit, the conventions sheet nor issue #60 asks for these rules, so the model has none of them. Each has an "accepted only while a question is open" case above.

6. **Can two components of one rotation overlap in time?** The conventions sheet and the blueprint do not say. `contracts/inputs/README.md` asks the same of the calendar (its question 1). For the engines developer and the science reviewers.
7. **Do the components have to be listed in the order of `position`, and do their dates have to follow that order?** The model checks only that the positions are the numbers from 1 to the number of components. For the engines developer and the interface developer.
8. **Can a component be harvested on the day it is sown?** The model rejects a harvest before the sowing and nothing else. For the engines developer.
9. **Can a rotation have no component?** The model accepts an empty list. For the engines developer and the interface developer.

### What the calendar engine needs from this contract

10. **Which fields of the rotation calendar does the definition carry?** This is part (a) of question Q8 of `contracts/ENTRYPOINTS.md`, and it is not decided here. `RotationCalendar` (`contracts/inputs/rotation_calendar.py`) needs the fields below, and the entry point of the calendar engine (EP2) takes the definition as its only argument.

    | Field of the rotation calendar | In this definition today |
    |---|---|
    | `example_data` | Carried |
    | `case_id` | Carried |
    | `field_id` | Carried |
    | `rotation_id` | Carried |
    | `ag_year_start`: the start month of the agricultural year (C5.4) | Not carried |
    | `start_date`: the first day the calendar is laid out for | Not carried |
    | `end_date`: the last day | Not carried |

    Each one that is not carried is either a new field of this contract or a further argument of EP2. For the lead developer, as owner of lane L1, and the interface developer.
11. **How long is one cycle, and how are the years inside a rotation numbered?** The conventions sheet leaves "the numbering of the years inside a rotation" to this contract. Issue #60 proposes `position`, which numbers components, not years. With `repeats: true` and exact dates, the definition does not say when the cycle starts over, nor how its dates are moved onto the years the calendar is laid out for (question 6 of `contracts/inputs/README.md`). This also depends on question 2. For the engines developer and the interface developer.
12. **Is a `component_id` of the rotation calendar the `component_id` of this definition?** The calendar rejects two components with one `component_id`, and a rotation that repeats places each component of the definition more than once. Question 4 of `contracts/inputs/README.md` asks the same from the other side. For the engines developer and the lead developer.
13. **Where do the calendar rules live, and what is the identifier of each?** Blueprint section 5 gives this contract "which calendar rules are checked", and `RuleViolation.rule` of the calendar is "the identifier of a rule of the rotation definition". Issue #60 says the definition declares intent and the calendar engine checks feasibility; its example carries no rule, so the model carries none. For the engines developer and the interface developer.
14. **Is a time with no crop in the ground a component, or simply dates that no component covers?** The `purpose` list has no entry for it. Question 3 of `contracts/inputs/README.md` leaves it to this contract. For the engines developer and the interface developer.

### Provenance, source and what can be left out

15. **Does what the user declares besides dates carry a provenance label and a source?** C4.1 says every value that is not missing carries a label, and gives "the rotation and its management" as its example of `DECLARED`. In issue #60 only the dates carry one; `crop_id`, `purpose`, `position` and `repeats` do not. The model follows the issue. Also: the model accepts any of the four labels on a date of the definition, not only `DECLARED`. For the lead developer.
16. **What is `label`, and which fields may be left out?** Issue #60 carries `label` without a description. The model requires every field of the definition and of a component that the example carries, and gives none a default. For the interface developer.
17. **What is the format of `source`?** The example says `"user"`. The model takes any text that is not blank. Question 22 of `contracts/inputs/README.md` asks the same. For the lead developer.
18. **Which reason code does a date carry in which case?** The example uses `NOT_APPLICABLE` for the harvest of a component that is not harvested, and issue #60 names `NOT_DECLARED` for a date that is not decided yet. The model accepts any of the eight codes of C3.2 on either date. What takes the place of the harvest of such a component depends on question 3. For the engines developer and the interface developer.

### This folder and the other contract folders

19. **The shared shapes exist once more.** `common.py` of this folder defines the date value, the `missing` part, the provenance label, the reason codes and the base model again, with the same rules as `contracts/inputs/common.py`. It imports from no other contract folder because question Q1 of `contracts/ENTRYPOINTS.md` (the import path of the contract packages) is not answered: the two existing folders load under different names, and a class loaded under two names is two classes. The `missing` part now exists three times (`contracts/inputs/`, `contracts/results/` and here). When Q1 is answered, this folder should take the shapes from one shared place (question 24 of `contracts/inputs/README.md`). For the platform developer (Q1) and the lead developer (one shared place).
20. **Should this example and the example of the rotation calendar describe the same rotation?** They do not: the identifiers, the number of components and the dates differ, so the calendar example is not the calendar of this definition. For the engines developer.
21. **Is the item `rotation` of the request body this model, unchanged?** That is question Q9 of `contracts/ENTRYPOINTS.md`. If it is, the request item carries `contract`, `example_data`, `case_id` and `field_id` as well. For the platform developer and the interface developer.
