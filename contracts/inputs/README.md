# Input contracts: rotation calendar and site data

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until a person approves the pull request.

This folder holds a Pydantic model and one example for three contracts of blueprint section 5:

| Contract | Producer → consumer | Model | Example |
|---|---|---|---|
| Rotation calendar | Engines → Lead | `rotation_calendar.RotationCalendar` | `examples/PLACEHOLDER_rotation_calendar.json` |
| Site data: climate | Platform (L2a) → Lead, Engines, Interface | `site_climate.SiteClimate` | `examples/PLACEHOLDER_site_climate.json` |
| Site data: soil and slope | Platform (L2a) → Lead, Engines, Interface | `site_soil_slope.SiteSoilSlope` | `examples/PLACEHOLDER_site_soil_slope.json` |

### The chain set (PROPOSED, unit l0/chain-examples, issue #168)

Two more examples, one per site-data contract, for one purpose: to let the whole chain run on example data, rotation definition → EP2 → EP1 and EP3 → `ResultsPerRotation`, through the runner of `api/engines.py` (test: `validation/test_chain_examples.py`).

| Contract | Example |
|---|---|
| Site data: climate | `examples/PLACEHOLDER_chain_site_climate.json` |
| Site data: soil and slope | `examples/PLACEHOLDER_chain_site_soil_slope.json` |

Why they exist: the examples above name `PLACEHOLDER-case` / `PLACEHOLDER-field`, while the rotation definition example (`contracts/rotation_definition/examples/`, signed by its producer) names `example-case` / `example-field-1`. The runner calls EP1 and EP3 only when every input names the calendar's case and field, so no run on the examples above ever reached them. The climate example above also covers five days, too few for one agricultural year, so even a run with matching identifiers came back `NO_COVERAGE`. The examples above stay unchanged, because tests of other lanes read them.

What the chain set holds:

- `case_id` and `field_id` exactly those of the rotation definition example, and `"example_data": true`.
- Climate: the six daily series that EP1 and EP3 read (`precipitation` and the five inputs of the reference evapotranspiration), each from 2001-07-01 to 2002-06-30, with no day missing and time zone `UTC`. That is agricultural year 2001 of the record of decision D47, laid out for the start month the rotation definition example declares (July). Every day of every series holds the same number, `1234.5`: plainly not weather. The unit strings are those of `contracts/CLIMATE_QUANTITIES.md` (CQ1 to CQ6), copied so that a unit guard does not stand in for the reason a value is missing; the numbers in them are not data. The point carries the illustrative numbers of the example above (1.0, 2.0, 3.0), its label and its source, but in the unit strings of decision D55 of issue #77: `degree` for latitude and longitude, `m` for elevation, the strings EP3 accepts. In a placeholder unit EP3 stopped every year at its unit guard. With those units the numbers name a point at sea, not a field and not a place the example describes; the source still says it is not a real place.
- Soil and slope: a slope length of `123456.25` and a slope steepness of `1234.5`, both plainly unreal, and no soil property. The steepness unit is `percent`, the string `engine/erosion/ls.py` reads as a slope (EP1's PROPOSED reading; question 18 is still open). The length unit is `example_length_unit`: it does not carry the word PLACEHOLDER because the parameter catalogue refuses that word in a record, and ls.py requires the unit-length record to carry exactly the slope length's unit string. It is not a real unit. Not the accepted soil-and-slope example of decision D38: which file holds the demonstration values is a person's decision.

The open questions this set raises are in `validation/README.md`, section "OPEN", "Chain of the examples".

Blueprint section 5 says the producer of a contract writes its example. No producer example exists yet, so a builder session proposed the models and the examples. The producers correct them: the engines lane for the rotation calendar, sub-lane L2a for the two site-data contracts. The consumers named above approve the pull request.

**The examples are PLACEHOLDER data.** Every number, date, identifier, unit string and source string in them is illustrative. They describe no real place, no real field and no real producer. The climate example carries a point because its model requires one (see [Site data: climate](#site-data-climate-site_climatepy)): the three numbers of that point are illustrative, in a placeholder unit, and they are not the coordinates of any field. The other two examples carry no coordinates. Each example says `"example_data": true`.

Acceptance test, from the repository root:

```bash
python -m pytest contracts/inputs/
```

Models and pure validation only. No network calls, no parameter values, no thresholds, no citations. The models do not import from `params/` or `validation/`.

## What is not decided here

The repository names no soil-loss method, no variable of the climate source and no soil or terrain source. The models assume none:

- A quantity that blueprint section 8 names has a field: slope length, slope steepness, the dated periods for cover management, daily series (the blueprint names precipitation).
- Everything else travels in a generic list, each item with a `quantity` identifier: `daily_series`, `monthly_series`, `soil_properties`.
- Every unit is a string that the item carries. No unit is fixed for site data; the examples say `PLACEHOLDER_unit`.

What a person has to decide is listed under [OPEN](#open).

## Shared parts (`common.py`)

All PROPOSED. They follow `contracts/CONVENTIONS.md`; the convention is named in brackets.

Every model rejects unknown fields and does not coerce types: a number written as text is rejected.

### `Value`: a number, or missing with its reason

| Field | Type | Rule |
|---|---|---|
| `value` | number or null | Required key. Null when missing. Finite: "not a number" is rejected (C3.1) |
| `unit` | text | Required, not empty. Kept when the value is missing (C1.1, C3.1) |
| `missing` | `Missing` | Present exactly when `value` is null (C3.1) |
| `provenance` | `DECLARED`, `OBSERVED`, `DERIVED` or `SIMULATED` | Required when there is a value; absent when missing (C4.1) |
| `source` | text | Reference to the source (C4.2). A value carries `source`, or `assumption: true`, or both |
| `assumption` | true or false | The explicit "assumption" mark (C4.2). False when left out. Never true on a missing value |
| `range` | `Range` | The uncertainty range (C2.1) |
| `range_missing` | `Missing` | Why there is no range (C2.2). A value carries exactly one of `range` and `range_missing`; a missing value carries neither |

### `Missing`

| Field | Type | Rule |
|---|---|---|
| `reason` | one of the eight codes of C3.2 | Required |
| `detail` | text | Optional. Required with reason `MISSING_INPUT`, where it names the input (C3.2) |

### `Range`

| Field | Type | Rule |
|---|---|---|
| `low`, `high` | number | Both required; `low` ≤ value ≤ `high` (C2.1) |
| `kind` | text | Required, not empty. The closed list of labels is OPEN in C2.3, so any text is accepted |

### `DateValue`: a date, or missing with its reason

`date` (`YYYY-MM-DD` or null, C5.2), `missing`, `provenance`, `source`, `assumption`, with the same rules as `Value`. A date has no unit and no range.

### What carries no provenance label

Identifiers, the `example_data` flag, the feasibility result and the first and last date or month that a calendar or a series covers describe the record. They are not values in the sense of sections 2 to 4 of the conventions and carry no unit, range or label. This line is drawn by the session: PROPOSED.

## Rotation calendar (`rotation_calendar.py`)

`RotationCalendar`: the dated calendar of one rotation on one field.

| Field | Type | Rule |
|---|---|---|
| `contract` | `"rotation_calendar"` | Required |
| `example_data` | true or false | Required. True for example data |
| `case_id`, `field_id`, `rotation_id` | text | Required, not empty |
| `ag_year_start` | `AgYearStart` | The start month of the agricultural year of the case (C5.4) |
| `start_date`, `end_date` | date | First and last day the calendar is laid out for, both inclusive. `end_date` is not before `start_date` |
| `feasibility` | `Feasibility` | Result of the feasibility check of the calendar engine |
| `components` | list of `CalendarComponent` | `component_id` is unique; every date of a component lies inside the calendar |

`AgYearStart`: `month` (1 to 12 or null, C5.1), `provisional` (true or false; required when there is a month, C5.4), `missing`, `provenance`, `source`, `assumption` with the rules of `Value`.

`Feasibility`: `feasible` (true or false) and `violations` (list of `RuleViolation`). A feasible calendar lists no violation; an infeasible one lists at least one.

`RuleViolation`: `rule` (text: identifier of a rule), `component_ids` (list; each names a component of this calendar; empty when the rule concerns the whole calendar), `detail` (optional text).

`CalendarComponent`:

| Field | Type | Rule |
|---|---|---|
| `component_id` | text | Required, not empty |
| `crop_id` | text | Required, not empty. What occupies the field during the component |
| `start`, `end` | `DateValue` | Both inclusive. `end` is not before `start` |
| `periods` | list of `CalendarPeriod` | May be empty. Every date of a period lies inside its component |

`CalendarPeriod`: `period_type` (text), `start` and `end` (`DateValue`, inclusive, `end` not before `start`). A period is the generic field for "cover management by period" of blueprint section 8.

Rules on dates are checked only between dates that are present. A missing date is accepted when it carries its reason.

## Site data: climate (`site_climate.py`)

`SiteClimate`: climate data of one field of one case.

| Field | Type | Rule |
|---|---|---|
| `contract` | `"site_data_climate"` | Required |
| `example_data` | true or false | Required |
| `case_id`, `field_id` | text | Required, not empty |
| `point` | `ClimatePoint` | Required. The point the series of the record are valid for |
| `daily_series` | list of `DailySeries` | Required key. `quantity` is unique in the list |
| `monthly_series` | list of `MonthlySeries` | Required key, may be empty. `quantity` is unique in the list |

### The point the series are valid for (`ClimatePoint`)

The lead developer decided that latitude, longitude and elevation travel in this contract, as the point the series is valid for, with provenance label and source (issue #77, decision D9, 14 November 2026). That is a person's decision. What follows is how a builder session wrote it into the model: the field names and the shape are **PROPOSED**.

| Field | Type | Rule |
|---|---|---|
| `latitude` | `Value` | Required key. Can be missing with its reason (while question 27 is open) |
| `longitude` | `Value` | Required key. Can be missing with its reason (while question 27 is open) |
| `elevation` | `Value` | Required key. Can be missing with its reason |

Each of the three is a `Value` of `common.py`, unchanged, with every rule of that shape:

- a number carries its unit string, its provenance label (one of the four of C4.1), its `source` or the assumption mark (C4.2), and a `range` or the reason it has none in `range_missing` (C2.2);
- a missing one is null with its `missing` part and reason (C3.1), keeps its unit, and carries no provenance label and no range;
- a number that is not finite, or written as text, is rejected.

A record without `point`, or a point without one of the three keys, is rejected: a value that is not known is sent as missing, not left out.

What the model does **not** fix, because a person has to choose it (see [OPEN](#open), questions 25 to 31):

- No unit string. `unit` is any text that is not empty; the document supplies it. No angle or length unit is written anywhere in the model.
- No datum and no vertical reference. The model has no field for either.
- No provenance label. Any of the four is accepted.
- No source. `source` is text, as for every other value of this contract (question 22).
- No bound. No range check on latitude or longitude and no limit on elevation.

One point holds for every series of the record. The model has no place for a second point (question 31).

Agreed with the platform developer in issue #18, for the adapter that fills this model: the adapter takes the point from what the response of the source reports for it, not from the request. The model cannot check where a number came from; that is tested in the adapter.

In the example the three values use the unit `PLACEHOLDER_unit`, the label `OBSERVED` and a placeholder source. Those are there so that the example loads. They are not a proposal of a unit, a label or a source for real data.

`DailySeries`:

| Field | Type | Rule |
|---|---|---|
| `quantity` | identifier | Lower case with underscores (C1.1) |
| `unit` | text | Required, not empty. One unit for the whole series |
| `time_zone` | text | Required, not empty (C6.1). `UTC` for a series of the NASA POWER adapter (C6.2) |
| `start_date`, `end_date` | date | Both inclusive |
| `provenance`, `source`, `assumption` | as in `Value` | Stated once; they hold for every day that is not missing. Required when at least one day has a number; `provenance` is absent when every day is missing |
| `range_missing` | `Missing` | Stated once (C2.2). Required when at least one day has a number. A daily value carries no range of its own |
| `days` | list of `DailyValue` | One item for every day from `start_date` to `end_date`, in order, none twice, none left out |

`DailyValue`: `date`, `value` (number or null), `missing`. Exactly one of a number and a `missing` part.

`MonthlySeries`: `quantity`, `unit`, `provenance`, `source`, `assumption`, `range_missing` as above; `start` and `end` (each `year` and `month`, inclusive); `months` (list of `MonthlyValue`: `year`, `month`, `value`, `missing`), one item for every month from `start` to `end`, in order. A month always travels with its calendar year (C5.1).

A day or a month without data stays in its series as missing, with its reason. It is not dropped.

Reference evapotranspiration and the daily water balance are results of the engines (blueprint section 8), not site data. They are not in this contract.

## Site data: soil and slope (`site_soil_slope.py`)

`SiteSoilSlope`: soil and slope data of one field of one case.

| Field | Type | Rule |
|---|---|---|
| `contract` | `"site_data_soil_slope"` | Required |
| `example_data` | true or false | Required |
| `case_id`, `field_id` | text | Required, not empty |
| `slope_length` | `Value` | Required. Can be missing with its reason |
| `slope_steepness` | `Value` | Required. Can be missing with its reason |
| `soil_properties` | list of `SoilProperty` | Required key, may be empty. `quantity` is unique in the list |

`SoilProperty`: a `Value` with a `quantity` identifier (lower case with underscores).

## PROPOSED cases

Every case below is a change to one example. The invalid ones must be rejected; the test also checks that each is rejected for the stated reason. The identifiers are the test identifiers in `test_examples.py`.

**Limit of the case "a missing day written as zero".** Zero is a real value of a daily series. A schema cannot tell an observed zero from a gap that an adapter filled with zero and sent without a `missing` part. What the models reject is: an item that holds a number together with a `missing` part, an item that holds neither, "not a number", and a day left out of the series. Keeping a gap from becoming a bare zero is the duty of the adapter and has to be tested there.

### Site data: climate, rejected

| Case | The variant |
|---|---|
| `daily-series-without-time-zone` | A daily series has no `time_zone` (C6.1) |
| `daily-series-with-empty-time-zone` | `time_zone` is empty text |
| `missing-day-written-as-zero` | A day keeps its `missing` part and its value is zero (C3.1) |
| `missing-day-written-as-not-a-number` | A day holds "not a number" in place of a `missing` part (C3.1) |
| `missing-day-dropped-from-the-series` | The day without data is left out of the list |
| `missing-day-without-reason` | A day holds null and no `missing` part |
| `missing-part-without-reason-code` | A `missing` part has no `reason` |
| `unknown-reason-code` | `reason` is not one of the codes of C3.2 |
| `series-without-unit` | A series has no `unit` |
| `series-without-provenance-label` | A series with numbers has no `provenance` (C4.1) |
| `series-without-source-or-assumption-mark` | A series with numbers has neither `source` nor the assumption mark (C4.2) |
| `series-without-range-and-without-its-reason` | A series with numbers has no `range_missing` (C2.2) |
| `all-missing-series-with-provenance-label` | A series whose days are all missing carries a provenance label (C4.1) |
| `days-out-of-order` | Two days are swapped |
| `days-stop-before-end-date` | The list ends before `end_date` |
| `date-not-written-as-year-month-day` | A date is written `2001-1-1` (C5.2) |
| `date-with-a-time` | A date carries a time of day |
| `month-thirteen` | A month number is 13 (C5.1) |
| `month-as-a-name` | A month is written as its name (C5.1) |
| `month-without-its-year` | A monthly item has no `year` (C5.1) |
| `month-dropped-from-the-series` | A month is left out of the list |
| `two-series-with-one-quantity` | Two daily series share one `quantity` |
| `quantity-identifier-not-lower-case` | A `quantity` starts with a capital letter (C1.1) |
| `climate-unknown-extra-field` | An unknown field at the top of the record |
| `day-unknown-extra-field` | An unknown field inside a day |
| `climate-without-example-data-flag` | `example_data` is left out |
| `climate-with-another-contract-identifier` | `contract` names another contract |

### Site data: climate, the point, rejected

Proposed by unit `l0/climate-point`. A row that names three cases holds the same variant for each value of the point; the test checks that the error names that value.

| Case | The variant |
|---|---|
| `climate-without-point` | The record has no `point` |
| `point-without-latitude`, `point-without-longitude`, `point-without-elevation` | The value is left out of the point instead of being sent as missing |
| `point-latitude-without-unit`, `point-longitude-without-unit`, `point-elevation-without-unit` | The value has no `unit` (C1.1) |
| `point-latitude-without-provenance-label`, `point-longitude-without-provenance-label`, `point-elevation-without-provenance-label` | The value has no `provenance` (C4.1) |
| `point-latitude-without-source-or-assumption-mark`, `point-longitude-without-source-or-assumption-mark`, `point-elevation-without-source-or-assumption-mark` | The value has neither `source` nor the assumption mark (C4.2) |
| `point-latitude-missing-without-reason`, `point-longitude-missing-without-reason`, `point-elevation-missing-without-reason` | The value is null, keeps its unit and has no `missing` part (C3.1) |
| `point-latitude-not-a-number`, `point-longitude-not-a-number`, `point-elevation-not-a-number` | The value is "not a number" (C3.1) |
| `point-latitude-infinite`, `point-longitude-infinite`, `point-elevation-infinite` | The value is infinite |
| `point-value-written-as-text` | The latitude is a number written as text |
| `point-unknown-extra-field` | An unknown field inside the point |

### Site data: soil and slope, rejected

| Case | The variant |
|---|---|
| `value-without-unit` | A value has no `unit` (C1.1) |
| `value-with-empty-unit` | `unit` is empty text |
| `value-without-provenance-label` | A value has no `provenance` (C4.1) |
| `provenance-label-outside-the-four` | `provenance` is not one of the four labels |
| `provenance-label-in-lower-case` | `provenance` is written in lower case |
| `value-without-source-or-assumption-mark` | A value has neither `source` nor the assumption mark (C4.2) |
| `missing-value-without-reason` | A value is null and has no `missing` part (C3.1) |
| `missing-value-written-as-zero` | An item keeps its `missing` part and its value is zero (C3.1) |
| `missing-value-with-provenance-label` | A missing value carries a provenance label (C4.1) |
| `missing-value-with-range` | A missing value carries `range_missing` (C2.2) |
| `missing-input-without-detail` | Reason `MISSING_INPUT` without the `detail` that names the input (C3.2) |
| `value-without-range-and-without-its-reason` | A value has neither `range` nor `range_missing` (C2.2) |
| `value-with-range-and-reason-for-no-range` | A value has both `range` and `range_missing` |
| `range-with-one-bound` | A range has `low` and no `high` (C2.1) |
| `range-that-does-not-hold-its-value` | `low` is greater than the value (C2.1) |
| `range-with-low-above-high` | `low` is greater than `high` |
| `range-without-kind` | A range has no `kind` (C2.1) |
| `value-written-as-text` | A number is written as text |
| `two-soil-properties-with-one-quantity` | Two soil properties share one `quantity` |
| `soil-without-slope-steepness` | `slope_steepness` is left out instead of being sent as missing |
| `soil-unknown-extra-field` | An unknown field at the top of the record |
| `value-unknown-extra-field` | An unknown field inside a value |

### Rotation calendar, rejected

| Case | The variant |
|---|---|
| `component-ends-before-it-starts` | The end date of a component is before its start date |
| `period-ends-before-it-starts` | The end date of a period is before its start date |
| `period-outside-its-component` | A period ends after its component |
| `component-outside-the-calendar` | A component ends after `end_date` of the calendar |
| `calendar-ends-before-it-starts` | `end_date` of the calendar is before `start_date` |
| `two-components-with-one-identifier` | Two components share one `component_id` |
| `component-without-crop-identifier` | A component has no `crop_id` |
| `date-without-provenance-label` | A date has no `provenance` (C4.1) |
| `missing-date-without-reason` | A date is null and has no `missing` part (C3.1) |
| `date-written-as-day-of-year` | A date is written as year and day of year (C5.2) |
| `start-month-without-provisional-mark` | The start month does not say whether it is provisional (C5.4) |
| `start-month-zero` | The start month is 0 (C5.1) |
| `start-month-without-provenance-label` | The start month has no `provenance` (C4.1) |
| `missing-start-month-without-reason` | The start month is null and has no `missing` part |
| `feasible-calendar-with-violations` | `feasible` is true and a violation is listed |
| `infeasible-calendar-without-violations` | `feasible` is false and no violation is listed |
| `violation-that-names-an-unknown-component` | A violation names a component that the calendar does not have |
| `calendar-unknown-extra-field` | An unknown field at the top of the record |
| `component-unknown-extra-field` | An unknown field inside a component |
| `calendar-without-example-data-flag` | `example_data` is left out |

### Accepted

These variants stay valid. They show shapes that the examples do not contain.

| Case | The variant |
|---|---|
| `accepted-missing-date-with-reason` | The end date of a component is missing, with its reason |
| `accepted-missing-start-month-with-reason` | The start month is missing with reason `NOT_DECLARED` |
| `accepted-infeasible-calendar-with-violation` | `feasible` is false and one violation names a component |
| `accepted-missing-slope-with-reason` | Slope length is missing with reason `NO_COVERAGE` and keeps its unit |
| `accepted-zero-as-a-value` | Slope steepness is zero with a range: zero is a value |
| `accepted-while-open-overlapping-components` | Two components of the same field overlap. Neither the conventions nor the blueprint forbid or allow it; see OPEN, question 1. The model does not reject it **only** until a person decides. This case is not a proposal to allow overlap |
| `accepted-missing-elevation-with-reason` | The elevation of the point is missing, with its reason, and keeps its unit |
| `accepted-while-open-missing-latitude-and-longitude-with-reason` | The latitude and the longitude of the point are missing, each with its reason. Whether a record may travel without them is not decided; see OPEN, question 27. The model does not reject it **only** until a person decides. This case is not a proposal to allow it |

## OPEN

Each item is a question a person has to answer. Until then the models keep the generic shape described above.

### Rotation calendar

1. **Can two components of the same field overlap in time?** The conventions and the blueprint do not say. If they cannot, the model gains the rule and the case `accepted-while-open-overlapping-components` becomes a rejected one. The same question holds for two periods of one component. For the engines developer and the science reviewers.
2. **What is a period for cover management, and which period types exist?** It depends on the soil-loss method, which the repository does not name. `period_type` accepts any text until then. For the science reviewers.
3. **Which identifiers can `crop_id` take, and is a time with no crop in the ground a component of its own or simply dates that no component covers?** The vocabulary belongs to the rotation definition and to the parameter catalogue. For the engines developer and the interface developer.
4. **Does the calendar repeat what the user declared per component (crop, management), or does the consumer read it from the rotation definition through `component_id`?** The rotation definition contract is not written yet. For the engines developer and the lead developer.
5. **Which calendar rules exist, and what is the identifier of each?** `rule` accepts any text. The rules belong to the rotation definition contract (blueprint section 5). For the engines developer and the interface developer.
6. **Is the calendar laid out over the real years of the climate record, and from which year?** The model takes any `start_date` and `end_date`. The numbering of the years inside a rotation belongs to the rotation definition contract (conventions, "Not covered by this sheet"). For the engines developer.
7. **In which calendar month does the agricultural year of each case begin, provisionally?** This is the OPEN point of C5.4. The month in the example is illustrative. For the person who declares the case.
8. **Can a calendar with a missing date be feasible?** The model does not link the two. For the engines developer.

### Site data: climate

9. **Which daily quantities does the climate contract deliver, with which identifier, from which source and in which unit?** The blueprint names precipitation and "meteorology"; the variables are not named anywhere. For the science reviewers (source and unit) and the platform developer (identifiers).
10. **Is erosivity delivered as site data, or does the erosion engine derive it from the daily precipitation series?** Blueprint section 8 names a "monthly erosivity fraction" and no source for it. `monthly_series` is the generic place for a monthly quantity if one is delivered; the example uses a placeholder quantity. For the science reviewers.
11. **Can a monthly quantity be a long-term mean per calendar month, without a year?** C5.1 says a month always travels with its year, so the model has no shape for it. For the lead developer.
12. **In which time zone is a daily series from a source other than the NASA POWER adapter defined?** This is C6.4. The model accepts any text in `time_zone` and does not stop two series of one record from having different time zones; C6.3 makes the engine answer missing in that case. For the science reviewers.
13. **How is a filled day labelled?** C3.4 says filled values are labelled as filled, and the method is OPEN there. A daily item has no such label yet, and one provenance label covers the whole series. For the science reviewers and the lead developer.
14. **Does a daily value ever carry an uncertainty range, and in which shape?** The proposal states the reason for the absent range once per series. For the science reviewers.
15. **Can two series of one record carry the same quantity from two sources?** The model rejects it. For the platform developer.

Questions on the point the series are valid for, added by unit `l0/climate-point`. They are numbered after the last question of this file, so that no number that another file refers to changes.

25. **In which unit does each of the three values travel, and to which datum does it refer?** Three unit strings (latitude, longitude, elevation), the horizontal reference of the two coordinates and the vertical reference of the elevation. The model fixes none of them and has no field for a datum: if the datum has to travel with the value, that is a further field. C1.1 lists no unit symbol for an angle or for a length, so the spelling of the unit strings is also an addition to C1.1 (the same kind of question as O13 of `contracts/CLIMATE_QUANTITIES.md`). For the science reviewers; the lead developer for the field and the addition to C1.1.
26. **Which provenance label do the three values carry?** One of the four of C4.1; the model accepts any. Whether one label holds for all three, and whether it changes when a value is not the one the source reports (for example an elevation declared by the user), is part of the question. For the science reviewers.
27. **Is a missing latitude or a missing longitude acceptable at all?** The shared `Value` shape lets each be missing with its reason, and the model adds no rule. If a record without them must not exist, the model gains the rule and the case `accepted-while-open-missing-latitude-and-longitude-with-reason` becomes a rejected one. A missing elevation is accepted: the brief of the unit asks for it. For the lead developer.
28. **Which elevation is it, when the source reports the average of a grid cell?** `contracts/CLIMATE_QUANTITIES.md` quotes the source: its data, "including the elevation value, represent average values over their original source spatial resolution". Is the elevation of the point that average, the elevation of the field declared by the user, or one taken from the terrain data? This is part (b) of O9 of that file. The same holds for the two coordinates: the adapter writes what the response reports for the point (agreed in issue #18), and whether that is the requested point or a point of the grid of the source is for a person to read in the source. For the science reviewers.
29. **Does the contract check a bound on any of the three values, and which?** The model checks none: neither the brief of the unit, nor the conventions sheet, nor issue #77 asks for one, and a bound depends on the unit of question 25. For the science reviewers (the bounds) and the lead developer (whether the contract checks them).
30. **Do the three values carry an uncertainty range, and which reason code states that they have none?** As every `Value`, each carries a `range` or a `range_missing` with a code of C3.2 (C2.2), so the adapter has to write one of the two. No code of the closed list says "the source gives no range for this value": this is O6 of `contracts/CLIMATE_QUANTITIES.md`, now also for the point. For the lead developer; the science reviewers if a range exists.
31. **Is one point enough for a record whose series come from more than one source?** The decision speaks of the point the series is valid for, and the model holds one point for every series of the record. If precipitation comes from another source than the rest (O4 of `contracts/CLIMATE_QUANTITIES.md`), the two sources may answer for different points. For the lead developer and the platform developer.

### Site data: soil and slope

16. **Which soil properties does the contract deliver, with which identifier, from which source and in which unit?** Blueprint section 8 names none. For the science reviewers (source and unit) and the platform developer (identifiers).
17. **Are soil properties given per depth layer, and with which depths?** The model has no depth and rejects two items with the same quantity. C1.6 leaves the soil depth OPEN. For the science reviewers.
18. **In which unit are slope length and slope steepness delivered, and from which source?** The fields exist because blueprint section 8 names both quantities. For the science reviewers.
19. **Is there one slope length and one slope steepness per field, or several (per part of the field, per cell)?** The model holds one of each. For the science reviewers and the lead developer.

### All three contracts

20. **Is a case one field or several?** The blueprint caches climate "per case" and speaks of a multi-field map. The models carry both `case_id` and `field_id` and one record describes one field. For the lead developer and the interface developer.
21. **Does site data repeat the place the source answered for (point, grid cell)?** The models carry no coordinates, so the examples cannot hold a real place. If a location is added, the example needs a way to stay free of real coordinates. For the platform developer and the lead developer.
    - `DECIDED` for the climate contract (decided by the lead developer on 14 November 2026, issue #77, D9): it carries the point the series is valid for (latitude, longitude, elevation), with its provenance label and source. The model has it as `point`; its example holds illustrative numbers in a placeholder unit, which are not the coordinates of any field.
    - Still `OPEN`: whether "Site data: soil and slope" carries a place, and whether the grid cell of the source travels besides the point. For the same roles as before. What a person still has to supply for the point itself is in questions 25 to 31.
22. **What is the format of `source`?** The model takes any text that is not empty. A person decides whether it is free text, a key of `ATTRIBUTIONS.md` or something else, and whether a record also carries the date on which the data was retrieved. For the lead developer.
23. **Which labels can `kind` of a range take?** This is the OPEN point of C2.3. For the science reviewers.
24. **Should the shared value shape (`Value`, `Missing`, `Range`) live in one place for every contract?** It is defined in this folder because the unit owns only this folder. Other contracts need the same shape and should not define a second one. For the lead developer.
