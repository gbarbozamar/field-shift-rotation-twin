# Rotation definition contract

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the engines developer, as consumer of the contract, and the interface developer, as its producer, who accepts or contests the [differences from the producer's example](#differences-from-the-producers-example).

This folder holds a Pydantic model and one example of the "Rotation definition" contract of blueprint section 5: what the user declares for one rotation on one field.

| Contract | Producer → consumer | Model | Example |
|---|---|---|---|
| Rotation definition | Interface → Engines | `rotation_definition.RotationDefinition` | `examples/PLACEHOLDER_rotation_definition.json` |

**Version 1.** The producer proposed the example, its design choices and five open questions in issue #60. A builder session of lane L0 landed it here, as the open decision of blueprint section 5 says.

**Version 2 (this version).** The producer proposed in issue #95 the start month of the agricultural year and the management fields per component, with a new full example. The lead developer decided around it in issue #77, on 14 November 2026:

- D7: the start month is a required part of the request; a request without it is invalid.
- D8: the start month travels in the rotation definition, with its provisional mark.
- D21: the definition carries at least one sowing or harvest date that is present.
- D39: the management fields of #95 are accepted as PROPOSED, with their closed lists; a management field that is not declared travels as an explicit `missing` part with its reason (C3.1), not as null.

A builder session of lane L0 landed version 2 here (unit `l0/rotation-definition-v2`, issue #118). The example of issue #95 is the source: its fields, its names and its design choices are kept, except where `contracts/CONVENTIONS.md` or a decision of issue #77 requires otherwise. Identifiers such as C3.1 below refer to that sheet.

The decisions are a person's, transcribed by builder sessions. Issue #77 says of them: where they are science class, a science reviewer still has to accept them. Of the decisions D2 to D8 of issue #77, only D2 (the crop list) is not yet in the model: its crops are not supplied yet.

**The example is PLACEHOLDER data.** Every date, identifier and text in it is illustrative. It describes no real place, no real field and no real producer, and it says `"example_data": true`. The crops are not crops: `crop_id` holds the word PLACEHOLDER, and so does the grazing intensity.

Acceptance test, from the repository root:

```bash
python -m pytest contracts/rotation_definition/
```

Models and pure validation only. No network calls, no parameter values, no thresholds, no citations, no crop list, no calendar rule. The models import nothing from `params/`, from `validation/` or from another contract folder.

## Layout

| Path | Content |
|---|---|
| `rotation_definition.py` | `RotationDefinition`, `AgYearStart`, `RotationComponent`, `Management`, `Grazing`, `Termination` and `MissingManagementField` |
| `common.py` | The date value, its `missing` part, the month number and the provenance label. They repeat `contracts/inputs/common.py`; see OPEN, question 19 |
| `examples/PLACEHOLDER_rotation_definition.json` | The example |
| `test_examples.py` | The acceptance test |

## Field list

All PROPOSED. Every model rejects unknown fields and does not coerce types: a number written as text is rejected. No field of the definition, of a component or of its management has a default: each one that the producer's example carries is required.

### `RotationDefinition`: one rotation on one field

| Field | Type | Rule |
|---|---|---|
| `contract` | `"rotation_definition"` | Required |
| `example_data` | true or false | Required. True for example data |
| `case_id`, `field_id`, `rotation_id` | text | Required, not blank |
| `label` | text | Required, not blank. Issue #60 does not describe it further; see OPEN, question 16 |
| `ag_year_start` | `AgYearStart` | Required, never missing, never null (D7, D8). Issue #95, change 1 |
| `repeats` | true or false | Required. True: the cycle starts over after the last component (issue #60) |
| `components` | list of `RotationComponent` | Required. `component_id` is unique in the list. The `position` values are the numbers from 1 to the number of components, none repeated and none skipped. **At least one component has a sowing or a harvest date that is present (D21)**, so a list with no component is rejected too |

### `AgYearStart`: the start month of the agricultural year

The calendar month in which the agricultural year of the case begins (C5.3, C5.4). Issue #95, change 1.

| Field | Type | Rule |
|---|---|---|
| `month` | integer 1 to 12 | Required, never null (C5.1, D7). Text, a number with a fraction or a value outside 1 to 12 is rejected |
| `provisional` | true or false | Required (C5.4). The model accepts false; see OPEN, question 28 |
| `provenance` | `DECLARED`, `OBSERVED`, `DERIVED` or `SIMULATED` | Required (C4.1) |
| `source` | text | Reference to the source (C4.2). The start month carries `source`, or `assumption: true`, or both |
| `assumption` | true or false | The explicit "assumption" mark (C4.2). False when left out |

```json
"ag_year_start": { "month": 7, "provisional": true, "provenance": "DECLARED", "source": "user" }
```

**Where it differs from `AgYearStart` of the rotation calendar** (`contracts/inputs/rotation_calendar.py`), which it mirrors:

| In the rotation calendar | In this definition | Why |
|---|---|---|
| `month` may be null, with a `missing` part and its reason | `month` is never null and there is no `missing` field: a start month with a `missing` part is rejected | D7: a request without the start month is invalid. The definition is that request, so its start month cannot be missing |
| `provisional` is required when the month is present and absent when it is missing | `provisional` is always required | Follows from the row above: the month is always present |
| `provenance` is required when the month is present | `provenance` is always required | The same |

Source or assumption mark, the four labels and the month numbers 1 to 12 are the same rules as in the calendar. The calendar engine copies the start month into the calendar (D8); that copy is a later unit of lane L1.

### `RotationComponent`: one component of the cycle

| Field | Type | Rule |
|---|---|---|
| `component_id` | text | Required, not blank |
| `position` | integer | Required. Numbers the components inside the cycle, from 1 (issue #60) |
| `crop_id` | text | Required, not blank. Any text is accepted. `DECIDED` (issue #77, D2): the values come from a closed list in `params/`. The model still accepts any text until that list lands as its own unit |
| `purpose` | `grain`, `cover` or `pasture` | Required. The closed list that issue #60 proposes. `DECIDED` (issue #77, D6): the list stays |
| `sowing` | `DateValue` | Required. Can be missing with its reason. `DECIDED` (issue #77, D3): an exact date |
| `harvest` | `DateValue` | Required. Can be missing with its reason. Not before `sowing`; checked only when both dates are present |
| `management` | `Management` | Required, never null (D4, D39). Issue #95, change 2 |

### `Management`: the management fields of one component

Accepted as PROPOSED by D39. Each of the three fields is required: it is either declared, in the form issue #95 gives it, or not declared, as a `MissingManagementField`. A null in its place is rejected (D39), and so is a field left out.

| Field | Declared form | Rule |
|---|---|---|
| `residue` | `left_on_surface`, `incorporated` or `removed` | What happens to the residues of the component (issue #95). The closed list of #95, unchanged. Written in lower case, as there |
| `grazing` | `Grazing`: `{ "intensity": text }` | Issue #95: present for pasture components. `intensity` is required, text that is not blank; free text until people define a measure (issue #95; see OPEN, question 27) |
| `termination` | `Termination`: `{ "date": YYYY-MM-DD, "method": ... }` | Issue #95: only for `purpose: "cover"`, when and how the cover crop ends. `date` is required, a valid date written as C5.2 says. `method` is required: `chemical`, `mechanical` or `frost`, the closed list of #95, unchanged |

The model does **not** check which purpose a management field belongs to: issue #95 describes it, but neither #95 nor #77 states it as a rule of the model (OPEN, questions 22 and 23).

### `MissingManagementField`: a management field that is not declared

PROPOSED form, for the producer and the engines developer to accept.

| Field | Type | Rule |
|---|---|---|
| `missing` | `Missing` | Required, never null. Nothing else: no declared field travels with it |

```json
"grazing": { "missing": { "reason": "NOT_DECLARED" } }
```

Why this form: C3.1 says a missing value travels with a `missing` part that holds its reason, keeps its identifier, and holds either its value or its `missing` part, never both and never neither. Here the key (`residue`, `grazing`, `termination`) is the identifier, and the object in its place holds the `missing` part. It is the same idea as a missing date in this folder (the `missing` part inside the item, issue #68), and the same as a part of `ResultsPerRotation` whose engine is not built (D12: an object that holds the `missing` part in place of the value, `contracts/results/`). A declared `residue` is a word, so the form cannot be "the declared fields set to null beside a `missing` part"; one form for the three fields keeps them alike. A missing part beside declared fields (for example a `termination` with its date, its method and a `missing` part) is rejected.

Any of the eight reason codes of C3.2 is accepted; the model does not say which code fits which field (OPEN, question 18).

### `DateValue`: a date, or missing with its reason

The shape issue #60 names: `date`, `missing`, `provenance`, `source`, `assumption`. Unchanged by version 2.

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

The two dates of a component and the start month carry a provenance label and a source, as in issues #60 and #95. Identifiers, the `example_data` flag, `label`, `repeats`, `position`, `crop_id`, `purpose` and the management fields carry none: issue #95 gives the management fields none, not even the termination date. This follows the line drawn in `contracts/inputs/README.md`; whether it is the right line for what the user declares is OPEN, question 15.

### Placeholders and decisions

The five questions of issue #60 and the start month are now answered by a person (issue #77). The first column describes the model as it is.

| In the model | For | Decision of issue #77 |
|---|---|---|
| `crop_id` accepts any text that is not blank | Question 1: the crop vocabulary | D2: a closed list in `params/`. The model still accepts any text until the crop list lands as its own unit |
| `sowing` and `harvest` are exact dates | Question 2: exact dates or windows | D3: exact dates, declared by the user |
| A component carries `management`: `residue`, `grazing`, `termination` | Question 3: management details | D4: in this contract, per component. D39: the fields of #95, with their closed lists; not declared is an explicit `missing` part. **In the model** |
| The definition has no `template_id`; components are always written out | Question 4: templates | D5: always explicit components |
| `purpose` is the list `grain` / `cover` / `pasture`, and a pasture component has no field of its own besides the management fields | Question 5: the `purpose` list | D6: the list stays; no separate pasture fields |
| `ag_year_start` is required and never missing | Question 10: the start month | D7, D8. **In the model** |
| At least one sowing or harvest date is present | Case N1 of `engine/calendar/README.md` | D21. **In the model** |

## PROPOSED cases

Every case below is a change to the example, made in memory. The invalid ones must be rejected; the test also checks that each is rejected for the stated reason. The identifiers are the test identifiers in `test_examples.py`. The cases added by version 2 are under the headings that name D7, D8, D21 and D39, and under "Accepted".

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
| `missing-part-beside-a-null-harvest` | `harvest` is null and the `missing` part sits in the component, as issues #60 and #95 wrote it (C3.1; see the differences below) |
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
| `positions-skip-a-number` | The positions of the three components are 1, 2 and 4 |
| `positions-start-at-zero` | The positions of the three components are 0, 1 and 2 |
| `definition-unknown-extra-field` | An unknown field at the top of the record |
| `definition-without-example-data-flag` | `example_data` is left out |
| `definition-without-repeats` | `repeats` is left out |
| `definition-with-another-contract-identifier` | `contract` names another contract |

### Rejected: at least one present date (D21)

| Case | The variant |
|---|---|
| `no-present-sowing-or-harvest-date` | Every sowing and harvest date of every component is missing with its reason (case N1 of `engine/calendar/README.md`) |
| `definition-without-components` | The list of components is empty, so no date is present. Before version 2 this case was accepted while question 9 was open |

### Rejected: the start month of the agricultural year (D7, D8)

| Case | The variant |
|---|---|
| `definition-without-start-month` | `ag_year_start` is left out (D7) |
| `start-month-null` | `ag_year_start` is null (D7) |
| `start-month-missing-with-its-reason` | `month` is null with a `missing` part and its reason, the shape the rotation calendar accepts (D7) |
| `start-month-zero` | `month` is 0 (C5.1) |
| `start-month-thirteen` | `month` is 13 (C5.1) |
| `start-month-written-as-text` | `month` is a number written as text |
| `start-month-without-provisional-mark` | `provisional` is left out (C5.4) |
| `start-month-provisional-mark-written-as-text` | `provisional` is the text `"true"` |
| `start-month-without-provenance-label` | `provenance` is left out (C4.1) |
| `start-month-provenance-label-outside-the-four` | `provenance` is not one of the four labels (C4.1) |
| `start-month-without-source-or-assumption-mark` | Neither `source` nor the assumption mark (C4.2) |
| `start-month-unknown-extra-field` | An unknown field inside `ag_year_start` |

### Rejected: the management fields (D4, D39)

| Case | The variant |
|---|---|
| `component-without-management` | A component has no `management` |
| `management-null` | `management` is null |
| `management-unknown-extra-field` | An unknown field inside `management` |
| `residue-outside-the-closed-list` | `residue` is a word outside `left_on_surface` / `incorporated` / `removed` |
| `residue-in-upper-case` | `residue` is written in upper case |
| `residue-not-declared-written-as-null` | `residue` is null (D39) |
| `residue-not-declared-left-out` | `residue` is left out (D39: not declared is explicit) |
| `grazing-not-declared-written-as-null` | `grazing` is null, as issue #95 wrote it (D39; see the differences below) |
| `termination-not-declared-written-as-null` | `termination` is null, as issue #95 wrote it (D39) |
| `termination-not-declared-left-out` | `termination` is left out (D39) |
| `not-declared-field-without-reason-code` | A field that is not declared has a `missing` part without `reason` (C3.1) |
| `not-declared-field-with-reason-code-not-in-the-sheet` | Its `reason` is a code that C3.2 does not define |
| `not-declared-field-missing-input-without-detail` | Reason `MISSING_INPUT` without the `detail` that names the input (C3.2) |
| `not-declared-field-with-its-missing-part-null` | The `missing` part itself is null |
| `termination-declared-together-with-a-missing-part` | A declared `termination` also carries a `missing` part (C3.1) |
| `termination-method-outside-the-closed-list` | `method` is not `chemical`, `mechanical` or `frost` |
| `termination-without-method` | A declared `termination` has no `method` |
| `termination-without-date` | A declared `termination` has no `date` |
| `termination-date-not-a-valid-date` | The termination date is `2028-02-30`, written as C5.2 says but not a date of the calendar |
| `termination-date-not-written-as-year-month-day` | The termination date is written day, month, year (C5.2) |
| `termination-date-null` | The termination date is null inside a declared `termination` |
| `termination-unknown-extra-field` | An unknown field inside `termination` |
| `grazing-without-intensity` | A declared `grazing` has no `intensity` |
| `grazing-intensity-blank` | `intensity` is only white space |
| `grazing-intensity-written-as-a-number` | `intensity` is a number |

### Accepted

These variants stay valid. They show shapes the example does not contain.

| Case | The variant |
|---|---|
| `accepted-sowing-not-declared` | The sowing date is missing with reason `NOT_DECLARED`: "not decided yet" travels as missing, never as an invented date (issue #60) |
| `accepted-date-with-assumption-mark-and-no-source` | A date carries `assumption: true` in place of `source` (C4.2) |
| `accepted-rotation-that-does-not-repeat` | `repeats` is false |
| `accepted-one-present-date-and-every-other-missing` | Only the harvest of the first component is present; every other date is missing with its reason (D21) |
| `accepted-only-one-sowing-date-present` | Only the sowing of the third component is present (D21: a sowing date counts as well as a harvest date) |
| `accepted-start-month-with-assumption-mark-and-no-source` | The start month carries `assumption: true` in place of `source` (C4.2) |
| `accepted-every-management-field-not-declared` | `residue`, `grazing` and `termination` are each not declared, as a `missing` part, on the components where the example declares them (D39) |
| `accepted-not-declared-field-with-a-detail` | A field that is not declared carries reason `NOT_APPLICABLE` and a `detail` |

### Accepted only while a question is open

The model does not reject these variants **only** until a person decides. No case here is a proposal to allow what it shows. When the question is answered with a rule, the model gains the rule and the case becomes a rejected one.

| Case | The variant | Question under OPEN |
|---|---|---|
| `accepted-while-open-crop-identifier-as-any-text` | `crop_id` is text taken from no list | 1. `DECIDED` (issue #77, D2): a closed list in `params/`. The model still accepts this variant until the crop list lands as its own unit |
| `accepted-while-open-overlapping-components` | The second component is sown before the first is harvested. Neither the conventions sheet nor the blueprint forbids or allows it | 6 |
| `accepted-while-open-components-not-listed-by-position` | The first component in the list has position 2 and the second has position 1, so neither the list nor the dates follow the positions | 7 |
| `accepted-while-open-harvest-on-the-day-of-sowing` | A component is harvested on the day it is sown | 8 |
| `accepted-while-open-start-month-not-provisional` | `provisional` is false | 28 |
| `accepted-while-open-start-month-with-another-provenance-label` | The start month is labelled `OBSERVED` | 15 |
| `accepted-while-open-termination-on-a-grain-component` | A `grain` component declares a `termination` | 22 |
| `accepted-while-open-cover-without-termination` | The `cover` component does not declare its `termination` | 22 |
| `accepted-while-open-cover-with-a-harvest-and-a-termination` | The `cover` component has a harvest date and a termination | 22 |
| `accepted-while-open-grazing-on-a-cover-component` | A `cover` component declares a `grazing` | 23 |
| `accepted-while-open-pasture-without-grazing` | The `pasture` component does not declare its `grazing` | 23 |
| `accepted-while-open-termination-before-its-sowing` | The termination date of the cover component is before its sowing date | 24 |

### Checked without a case of their own

- No field of the definition, of a component, of the start month (besides `source`, which may give way to the assumption mark) or of the management can be left out: the test leaves out each one in turn and each variant is rejected. Inside a declared `termination` and `grazing`, `date`, `method` and `intensity` are left out in turn too.
- The start month is accepted with each month from 1 to 12.
- A missing date, and each of the three management fields when not declared, is accepted with any of the eight reason codes of C3.2. The model does not say which code fits which date or field (OPEN, question 18).
- The reason codes and the provenance labels in `common.py` are the ones of the tables of C3.2 and C4.1, read from the sheet by the test.
- The closed lists of `residue` and of `termination.method` are exactly those of issue #95; the `purpose` list is that of issue #60.
- The example of issue #95, as the producer wrote it, is rejected exactly at the points of the two differences below, and it equals the landed example once those two changes are made.

## Differences from the producer's example

For the interface developer, to accept or to contest. There are two differences from the example of issue #95. The test holds the example of issue #95 as written and checks that there is no other.

### 1. A missing harvest carries its `missing` part inside `harvest`

Issue #95, like issue #60, writes the harvests of the second and third components as a null, with the `missing` part next to it, at the level of the component:

```json
"harvest": null,
"missing": { "reason": "NOT_APPLICABLE", "detail": "cover crop is terminated, not harvested" }
```

The landed example writes each as a date value that holds the null date and its `missing` part:

```json
"harvest": {
  "date": null,
  "missing": { "reason": "NOT_APPLICABLE", "detail": "cover crop is terminated, not harvested" }
}
```

Why: C3.1 says a missing value travels as an empty value together with a `missing` part, that one item holds either the value or the `missing` part, and that a missing value keeps its identifier, so a consumer knows what is missing. With the `missing` part in the component, nothing says which of the two dates it belongs to, and a component whose two dates are both missing could give only one reason. It is also the shape the producer names for dates (`date`, `missing`, `provenance`, `source`, `assumption`), and the shape of a missing date in `contracts/inputs/`. The producer accepted this change for version 1 (#68, and #18); the comment of the lead developer on issue #95 reads its return in #95 as a slip of the example, and D39 asks for the harvests of `c2` and `c3` in the accepted shape. The reason codes and the details are unchanged.

Consequences in the model: a component has no `missing` field, and `harvest` is never a bare null. The shape of the issue is the rejected case `missing-part-beside-a-null-harvest`.

### 2. A management field that is not declared is a `missing` part, not null

Issue #95 writes the management fields that are not declared for a component as null, "not declared for this component", and says the producer accepts either null or explicit missing parts:

```json
"management": { "residue": "left_on_surface", "grazing": null, "termination": null }
```

The landed example writes each as an object that holds its `missing` part, with reason `NOT_DECLARED`:

```json
"management": {
  "residue": "left_on_surface",
  "grazing": { "missing": { "reason": "NOT_DECLARED" } },
  "termination": { "missing": { "reason": "NOT_DECLARED" } }
}
```

Why: D39 of issue #77 decides that a management field that is not declared travels as an explicit `missing` part with its reason (C3.1), not as null. The form of the object is PROPOSED here ([`MissingManagementField`](#missingmanagementfield-a-management-field-that-is-not-declared)). The reason `NOT_DECLARED` is taken from the producer's own words, "not declared for this component", and from the table of change 2 of issue #95 ("Absent = missing `NOT_DECLARED`"); C3.2 defines it as "The user was asked for the value and did not give it". Whether another code fits better, for example `NOT_APPLICABLE` for the termination of a grain component, is OPEN, question 18. The changed fields are the grazing and the termination of `c1`, the grazing of `c2` and the termination of `c3`.

Consequences in the model: null in place of a management field is rejected (cases `grazing-not-declared-written-as-null`, `termination-not-declared-written-as-null`, `residue-not-declared-written-as-null`), and so is a field left out.

### Checked and kept

- **The start month** `{ "month": 7, "provisional": true, "provenance": "DECLARED", "source": "user" }` stays as the producer wrote it. The month 7 is illustrative: the provisional month of each case is still supplied by a person (C5.4).
- **The declared management fields** stay as the producer wrote them: `residue` `left_on_surface` on the three components, the termination of `c2` (`2028-08-15`, `chemical`) and the grazing of `c3` (`PLACEHOLDER_light`).
- **The reason code `NOT_APPLICABLE`** of the two missing harvests is one of the eight codes of C3.2, so it stays (OPEN, question 18).
- **The identifiers** `example-case`, `example-field-1`, `example-rotation-1`, `c1`, `c2` and `c3` stay as the producer wrote them. The examples of `contracts/inputs/` and `contracts/results/` put the word PLACEHOLDER in every identifier; the sheet does not ask for it, so this example was not changed. Here the word is in the file name, in the three `crop_id` values and in the grazing intensity.
- **The source `"user"`** stays. The format of `source` is not decided (OPEN, question 17).
- **The dates** stay. They are illustrative.

Not in issue #95 and added by the landing: the file name `PLACEHOLDER_rotation_definition.json`. The file is laid out over more lines than in the issue.

## OPEN

Each item is a question a person has to answer. The role that answers it is named at the end of the item. An item that a person has answered keeps its number and its question, and carries the answer under it, marked `DECIDED`.

### The five questions of issue #60

Copied from the issue. The lead developer answered the five on 14 November 2026 (issue #77, decisions D2 to D6; D39 for the management fields). Each question stays in place, followed by its answer and by the part a person still has to supply.

1. **Crop vocabulary**: where do `crop_id` values come from — a closed list in `params/`, or free text? The engines and the C-factor must recognise them. For the engines developer; the lead developer for a list in `params/`.
   - `DECIDED` (decided by the lead developer on 14 November 2026, issue #77, D2): **a closed list in `params/`**, which the interface shows and the engines recognise.
   - Still `OPEN`, to be supplied by people: **which crops are in the list?** For the lead developer, for the list in `params/`.
   - Not changed yet: `crop_id` accepts any text that is not blank. The crop list in `params/` is a later unit, once people supply the crops.
2. **Exact dates vs windows**: does the user declare exact sowing/harvest dates, or a window / relative rule that the calendar engine resolves into the exact dates of PR #54? For the engines developer, agreed with the interface developer.
   - `DECIDED` (decided by the lead developer on 14 November 2026, issue #77, D3): **exact dates**, declared by the user.
3. **Management details**: do residue handling, grazing or cover-crop termination travel in this contract, in a separate management contract, or stay out of the event core? For the engines developer, agreed with the interface developer.
   - `DECIDED` (decided by the lead developer on 14 November 2026, issue #77, D4): **in the rotation definition contract**, per component.
   - `DECIDED` (decided by the lead developer as consumer, issue #77, D39, on the producer's proposal of issue #95): **`residue`, `grazing` and `termination`, with their closed lists**, accepted as PROPOSED; a field that is not declared travels as an explicit `missing` part with its reason. In the model since version 2.
   - Still `OPEN`: what the model does not enforce about them, questions 22 to 27 below.
4. **Templates**: may the interface submit a `template_id` that the engines expand, or always inline components? (Affects whether the rotation ribbon is display-only or editable — an open L3 scope decision.) For the engines developer; the interface developer for the scope of the ribbon.
   - `DECIDED` (decided by the lead developer on 14 November 2026, issue #77, D5): **always explicit components.** If the interface offers templates, it expands them before sending.
5. **`purpose` list**: is `grain` / `cover` / `pasture` the right closed list, and do pasture components need extra fields (e.g. grazing), or is that out of the event core? For the engines developer, agreed with the interface developer.
   - `DECIDED` (decided by the lead developer on 14 November 2026, issue #77, D6): **`grain` / `cover` / `pasture` stays.** No separate pasture fields: what a pasture needs comes with the management fields of D4 (question 3).

### Rules the model does not enforce

Neither the briefs of these units, the conventions sheet nor issues #60, #95 and #77 ask for these rules, so the model has none of them. Each has an "accepted only while a question is open" case above.

6. **Can two components of one rotation overlap in time?** The conventions sheet and the blueprint do not say. `contracts/inputs/README.md` asks the same of the calendar (its question 1). For the engines developer and the science reviewers.
7. **Do the components have to be listed in the order of `position`, and do their dates have to follow that order?** The model checks only that the positions are the numbers from 1 to the number of components. For the engines developer and the interface developer.
8. **Can a component be harvested on the day it is sown?** The model rejects a harvest before the sowing and nothing else. For the engines developer.
9. **Can a rotation have no component?** For the engines developer and the interface developer.
   - Settled as a consequence of D21 (issue #77), not decided on its own: a definition must carry at least one present sowing or harvest date, and a definition without components carries none, so the model rejects it (case `definition-without-components`). If a person wants a rotation without components to be valid, D21 has to say so.

### What the calendar engine needs from this contract

10. **Which fields of the rotation calendar does the definition carry?** This is part (a) of question Q8 of `contracts/ENTRYPOINTS.md`. `RotationCalendar` (`contracts/inputs/rotation_calendar.py`) needs the fields below, and the entry point of the calendar engine (EP2) takes the definition as its only argument.

    | Field of the rotation calendar | In this definition |
    |---|---|
    | `example_data` | Carried |
    | `case_id` | Carried |
    | `field_id` | Carried |
    | `rotation_id` | Carried |
    | `ag_year_start`: the start month of the agricultural year (C5.4) | Carried since version 2 (D7, D8), never missing |
    | `start_date`: the first day the calendar is laid out for | Not carried |
    | `end_date`: the last day | Not carried |

    Each one that is not carried is either a new field of this contract or a further argument of EP2. For the lead developer, as owner of lane L1, and the interface developer.

    - `DECIDED` for the start month (decided by the lead developer on 14 November 2026, issue #77, D7 and D8): the start month is a required part of the request and travels **in the rotation definition**, with its provisional mark. The calendar engine copies it into the calendar. In the model since version 2; the copy into the calendar is a later unit of lane L1.
    - Still `OPEN`, to be supplied by people: **the provisional month of each case** (convention C5.4). For the person who declares the case.
    - Still `OPEN`, not answered by issue #77: `start_date` and `end_date`. (Issue #77, D21, records that the calendar engine already runs from the earliest to the latest declared date, P4 of `engine/calendar/README.md`.) For the lead developer, as owner of lane L1, and the interface developer.
11. **How long is one cycle, and how are the years inside a rotation numbered?** The conventions sheet leaves "the numbering of the years inside a rotation" to this contract. Issue #60 proposes `position`, which numbers components, not years. With `repeats: true` and exact dates, the definition does not say when the cycle starts over, nor how its dates are moved onto the years the calendar is laid out for (question 6 of `contracts/inputs/README.md`). D3 (exact dates) does not answer this. For the engines developer and the interface developer.
12. **Is a `component_id` of the rotation calendar the `component_id` of this definition?** The calendar rejects two components with one `component_id`, and a rotation that repeats places each component of the definition more than once. Question 4 of `contracts/inputs/README.md` asks the same from the other side. For the engines developer and the lead developer.
13. **Where do the calendar rules live, and what is the identifier of each?** Blueprint section 5 gives this contract "which calendar rules are checked", and `RuleViolation.rule` of the calendar is "the identifier of a rule of the rotation definition". Issues #60 and #95 say nothing of rules; their examples carry none, so the model carries none. For the engines developer and the interface developer.
14. **Is a time with no crop in the ground a component, or simply dates that no component covers?** The `purpose` list has no entry for it. Question 3 of `contracts/inputs/README.md` leaves it to this contract. For the engines developer and the interface developer.

### Provenance, source and what can be left out

15. **Does what the user declares besides dates carry a provenance label and a source?** C4.1 says every value that is not missing carries a label, and gives "the rotation and its management" as its example of `DECLARED`. In issues #60 and #95 only the dates and the start month carry one; `crop_id`, `purpose`, `position`, `repeats` and the management fields (the termination date included) do not. The model follows the issues. Also: the model accepts any of the four labels on a date and on the start month, not only `DECLARED` (case `accepted-while-open-start-month-with-another-provenance-label`). For the lead developer.
16. **What is `label`, and which fields may be left out?** Issue #60 carries `label` without a description. The model requires every field of the definition, of a component and of its management that the example carries, and gives none a default. For the interface developer.
17. **What is the format of `source`?** The example says `"user"`. The model takes any text that is not blank. Question 22 of `contracts/inputs/README.md` asks the same. For the lead developer.
18. **Which reason code does a date, or a management field that is not declared, carry in which case?** The example uses `NOT_APPLICABLE` for the harvest of a component that is not harvested, issue #60 names `NOT_DECLARED` for a date that is not decided yet, and the example uses `NOT_DECLARED` for every management field that is not declared, after the producer's words in issue #95. For a field that has no meaning for the component (a termination on a grain component, a grazing on a cover component) `NOT_APPLICABLE` may fit better. The model accepts any of the eight codes of C3.2 on either date and on each management field. For the engines developer and the interface developer.

### This folder and the other contract folders

19. **The shared shapes exist once more.** `common.py` of this folder defines the date value, the `missing` part, the month number, the provenance label, the reason codes and the base model again, with the same rules as `contracts/inputs/common.py`. It imports from no other contract folder because question Q1 of `contracts/ENTRYPOINTS.md` (the import path of the contract packages) is not marked answered there; `CLAUDE.md` now says to import contract models only as `contracts.<folder>`. The `missing` part now exists three times (`contracts/inputs/`, `contracts/results/` and here). When Q1 is answered, this folder should take the shapes from one shared place (question 24 of `contracts/inputs/README.md`). For the platform developer (Q1) and the lead developer (one shared place).
20. **Should this example and the example of the rotation calendar describe the same rotation?** They do not: the identifiers, the number of components and the dates differ, so the calendar example is not the calendar of this definition. For the engines developer.
21. **Is the item `rotation` of the request body this model, unchanged?** That is question Q9 of `contracts/ENTRYPOINTS.md`. `api/` loads the request's `rotation` into this model (`CLAUDE.md`, `RotationDefinitionValidator`), so the request item carries `contract`, `example_data`, `case_id`, `field_id` and now `ag_year_start` and `management` as well. For the platform developer and the interface developer.

### The management fields (version 2)

Issue #95 describes these; neither #95 nor #77 states them as rules of the model, so the model does not enforce them (brief of issue #118).

22. **Is `termination` only for `purpose: "cover"`?** Issue #95 says "Only for `purpose: "cover"`". The model accepts a declared termination on a grain or pasture component, a cover component without a declared termination, and a cover component with both a harvest date and a termination. Should the model reject any of these, and with which reason code is a termination not declared on a component it does not apply to? For the interface developer (producer) and the lead developer (consumer, lane L1).
23. **Is `grazing` only for pasture components, and must a pasture declare it?** Issue #95 says "Present for pasture components". The model accepts a declared grazing on a grain or cover component, and a pasture that does not declare its grazing. For the interface developer and the lead developer.
24. **Where may a termination date fall?** The model checks only that it is a valid date. It does not compare it with the sowing or the harvest of its component, nor with the sowing of the next component (case `accepted-while-open-termination-before-its-sowing`). Does the termination date count as a present date for D21? The model counts only sowing and harvest dates, as D21 says. For the engines developer and the lead developer.
25. **Can part of a termination be declared?** The model requires both `date` and `method` in a declared termination; a termination whose date is known but whose method is not (or the reverse) can only travel as wholly not declared. Should either part be missing on its own, with its reason? For the interface developer and the lead developer.
26. **The form of a field that is not declared.** The object `{ "missing": { ... } }` in place of the field is PROPOSED by this landing ([`MissingManagementField`](#missingmanagementfield-a-management-field-that-is-not-declared)); D39 decides only that it is an explicit `missing` part, not null. For the interface developer (producer) and the lead developer (consumer).
27. **A measure of grazing intensity.** `intensity` is free text until people define a measure (issue #95). Out of scope of this unit. For the lead developer and the science reviewers.

### The start month (version 2)

28. **May the start month be not provisional?** C5.4 says the start month is declared by a person, marked provisional, until the determination from imagery exists; issue #95 writes `provisional: true` "while it comes from a person and not from imagery". The model, like `AgYearStart` of the rotation calendar, accepts `provisional: false` (case `accepted-while-open-start-month-not-provisional`). Should the definition reject it while no imagery method exists? For the lead developer and the science reviewers.
29. **C5.1 and the start month.** C5.1 says "a month number always travels with its calendar year, in a field named `year`". The start month is a month that recurs every year and carries no year, as in `AgYearStart` of the rotation calendar. Does C5.1 need an exception for the start month, or does the start month carry something else? For the lead developer, who owns the conventions sheet.
