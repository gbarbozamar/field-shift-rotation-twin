# Results contracts

The two contracts that the engines emit and that the decision layer and the interface consume (blueprint section 5):

| Contract | Producer → consumer | Model | Example |
|---|---|---|---|
| Results per rotation | Lead, Engines → Platform, Interface | `ResultsPerRotation` | `examples/PLACEHOLDER_results_per_rotation.json` |
| Results table | Lead, Engines → Platform | `ResultsTable` | `examples/PLACEHOLDER_results_table.json` |

> **Status: PROPOSED.** The field lists, the examples and the test cases below were written by a builder session (blueprint section 3.7). They take effect only when people approve the pull request: the lane owner, and the consumers of these contracts (the platform developer and the interface developer). Items under `OPEN` need an answer from a person.

The models follow `contracts/CONVENTIONS.md`, whatever the status of each convention. Identifiers such as C3.1 below refer to that sheet.

**The examples are placeholders.** Every number in them is illustrative and means nothing. They were written by hand; no engine produced them. Every identifier, source and detail in them carries the word PLACEHOLDER. The years and the start month of the agricultural year in the examples are arbitrary; they are not a proposal for any case.

## Layout

| Path | Content |
|---|---|
| `models.py` | The Pydantic models and their validation. No value, no threshold, no computation, no file access, no network call |
| `examples/` | One hand-written placeholder example per contract |
| `test_examples.py` | The acceptance test: each example loads into its model, and each invalid variant is rejected |

Run the test from the repository root:

```bash
python -m pytest contracts/results/
```

Environment: Python 3.12, Pydantic 2 and pytest, as declared in the root `pyproject.toml`. This unit adds no dependency.

Load a document from JSON text with `ResultsPerRotation.model_validate_json(text)` or `ResultsTable.model_validate_json(text)`. Write one with `model_dump_json()`. Do not write with `exclude_none=True`: it drops `"value": null`, and a document without the `value` field is rejected.

## One indicator value (PROPOSED)

Every value of an indicator travels as the same item, `IndicatorValue`, wherever it appears in the two contracts. Each place adds the fields that say what the value refers to (an agricultural year, a month, a carbon model).

A number:

```json
{
  "indicator": "soil_loss",
  "direction": "lower_is_better",
  "value": 12.0,
  "unit": "t ha-1 yr-1",
  "range": {"low": 6.0, "high": 18.0, "kind": "PLACEHOLDER_range_kind"},
  "provenance": "DERIVED",
  "source": "PLACEHOLDER source: written by hand, not the output of an engine"
}
```

A missing value:

```json
{
  "indicator": "soil_loss",
  "direction": "lower_is_better",
  "value": null,
  "unit": "t ha-1 yr-1",
  "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER detail"}
}
```

| Field | Required | Rule | Convention |
|---|---|---|---|
| `indicator` | yes | `soil_loss`, `water_deficit_exposure` or `soil_carbon_trend` | C1.1 |
| `direction` | yes | `lower_is_better` or `higher_is_better`, and the one the sheet gives for the indicator | C1.1, C1.2, C1.3, C1.5 |
| `value` | yes | A finite number, or `null`. The field is always written; a missing value is `"value": null`, never an absent field | C3.1 |
| `unit` | yes | Exactly the unit string of the sheet for the indicator. Also required when the value is missing | C1.1, C3.1 |
| `range` | with a number, unless `range_missing` | An object with `low`, `high` and `kind` | C2.1 |
| `range.low`, `range.high` | yes | Finite numbers, absolute, in the unit of the value. `low` ≤ `value` ≤ `high`. Both or neither | C2.1 |
| `range.kind` | yes | Non-blank text that names what the range represents. The closed list is `OPEN` | C2.1, C2.3 |
| `range_missing` | with a number that has no range | An object like `missing`: why there is no range | C2.2 |
| `missing` | when `value` is `null` | An object with `reason` and an optional `detail` | C3.1 |
| `missing.reason` | yes | One of the eight reason codes | C3.2 |
| `missing.detail` | no | Non-blank English text. Required with `MISSING_INPUT`: it names the missing input | C3.1, C3.2 |
| `provenance` | with a number | `DECLARED`, `OBSERVED`, `DERIVED` or `SIMULATED`. Always `DERIVED` for `soil_loss` | C4.1, C4.6 |
| `source` | with a number, unless `assumption` | Non-blank text: the reference to the source of the value | C4.2 |
| `assumption` | no | `true` marks an assumption and takes the place of `source`. Default `false` | C4.2 |

Rules across fields:

- An item holds a number or a `missing` part, never both and never neither (C3.1). A number next to a reason is rejected, zero included. A value of zero without a `missing` part is a value.
- A number has exactly one of `range` and `range_missing` (C2.2), a provenance label (C4.1), and exactly one of `source` and `assumption: true` (C4.2).
- A missing value has no range, no `range_missing` (C2.2), no provenance label (C4.1), no source and no assumption mark.
- A range whose two bounds equal the value is rejected: that is how an absent range must not be written (C2.2).
- A part that does not apply may be written as `null` or left out; both read the same. `value` and `unit` are never left out.
- Nothing is coerced: a number written as text, `true`, not-a-number and infinity are rejected. An integer is accepted as a number.
- Any unknown field is rejected, at every level, so a misspelt field name cannot pass unnoticed.

Units checked, exactly as the sheet writes them:

| Indicator | Unit | Direction |
|---|---|---|
| `soil_loss`, per agricultural year | `t ha-1 yr-1` | `lower_is_better` |
| `soil_loss`, per calendar month | `t ha-1 month-1` | `lower_is_better` |
| `water_deficit_exposure` | `dimensionless` | `higher_is_better` |
| `soil_carbon_trend` | `t C ha-1 yr-1` | `higher_is_better` |

## Results per rotation (PROPOSED)

`ResultsPerRotation`: everything the engines report for one rotation of one field.

| Field | Required | Content |
|---|---|---|
| `case_id` | yes | Identifier of the case. Non-blank text |
| `field_id` | yes | Identifier of the field. Non-blank text |
| `rotation_id` | yes | Identifier of the rotation. Non-blank text |
| `soil_loss.annual` | yes, at least one | One `IndicatorValue` per agricultural year, plus `ag_year` (integer). Unit `t ha-1 yr-1` |
| `soil_loss.monthly` | yes | The monthly breakdown: one `IndicatorValue` per calendar month, plus `year` (calendar year), `month` (1 to 12) and `ag_year`. Unit `t ha-1 month-1` |
| `water_deficit_exposure` | yes, at least one | `IndicatorValue` items, plus `time_basis` (`rotation` or `ag_year`) and `ag_year` (only with `time_basis: "ag_year"`) |
| `soil_carbon_trend` | yes, at least one | `IndicatorValue` items, plus `carbon_model` (non-blank text) and `computation` |

Rules:

- `annual` has each agricultural year once. `annual` and `monthly` cover the same agricultural years.
- Each agricultural year has twelve monthly values: twelve consecutive calendar months, the first of them in the calendar year that names the agricultural year (C5.3). Months keep their calendar numbers and travel with their calendar year (C5.1).
- All agricultural years of a document begin in the same calendar month (C5.4). The document does not carry that month; it is read from the months.
- A value that is not available is present as missing, with its reason. An agricultural year, a month, or a computation is never left out to say "not available".
- `water_deficit_exposure`: the time basis of this indicator is `OPEN` in the sheet (C1.3). Until it is decided the contract carries either one value for the whole rotation (`time_basis: "rotation"`) or one value per agricultural year (`time_basis: "ag_year"`), never a mix, and no agricultural year twice.
- `soil_carbon_trend`: one value per carbon model and per computation (C1.5). `computation` is one of `end_minus_start`, `fitted_slope`, `mean_over_cycles`: the three computations of C1.6, in its order, under identifiers proposed here. Every carbon model that appears carries each of the three once (C1.6); one that cannot be computed is there as missing. The default computation is `end_minus_start` (`DEFAULT_TREND_COMPUTATION`).
- Values of different carbon models are separate items. Nothing in the contract merges or averages them (C1.5).

## Results table (PROPOSED)

`ResultsTable`: the values of several rotations of one field side by side, for the decision layer. A long table: one row is one value.

| Field | Required | Content |
|---|---|---|
| `case_id` | yes | Identifier of the case. Non-blank text |
| `field_id` | yes | Identifier of the field. Non-blank text |
| `rows` | yes, at least one | The rows |

A row is an `IndicatorValue` plus:

| Field | Required | Content |
|---|---|---|
| `rotation_id` | yes | The rotation the value belongs to |
| `scenario_id` | yes | The run the value comes from: one set of values of the uncertain inputs. Non-blank text. What a scenario holds is not described in this contract (`OPEN`) |
| `time_basis` | yes | `ag_year` or `rotation` |
| `ag_year` | with `time_basis: "ag_year"` | The agricultural year (C5.3). Not allowed with `time_basis: "rotation"` |
| `carbon_model` | for `soil_carbon_trend` only | The carbon model that produced the value |
| `computation` | for `soil_carbon_trend` only | The computation that produced the value |

Rules:

- `soil_loss` rows are per agricultural year, in `t ha-1 yr-1`. The monthly breakdown is not in the table; it travels in results per rotation.
- `soil_carbon_trend` rows are per rotation and name their carbon model and computation. The table does not have to carry all three computations.
- `water_deficit_exposure` rows use one time basis in the whole table, either of the two.
- The **cell** of a row is what it measures whatever the rotation: `scenario_id`, `indicator`, `time_basis`, `ag_year`, `carbon_model`, `computation`. Rows of two rotations with the same cell are a pair.
- A rotation has each cell once, and every rotation of the table has the same cells. A value that is not available is a row with a missing value and its reason, not an absent row.

## PROPOSED cases

Each code is tested in `test_examples.py`. An invalid variant is one of the two examples with one thing changed, in memory; unless a case says otherwise it is applied to both examples. A variant must be rejected for one reason only, and the test checks that it is the expected one. No case contains an expected value of the science.

The eight variants the brief asks for are U1, P1, M1, M3, R1, I1, I2 and X1.

### Accepted

| Code | Case |
|---|---|
| A1 | Each example file loads into its model, from JSON text and from parsed JSON, with the same result |
| A2 | A loaded model written back as JSON loads again unchanged |
| A3 | A value of zero, with its range, provenance and source, is accepted and stays the number zero: it is not a missing mark |
| A4 | A part that does not apply (`range`, `range_missing`, `missing`, `provenance`, `source`) may be `null` or left out and reads the same; the `detail` of a reason may be left out |
| A5 | The assumption mark takes the place of the source |
| A6 | `water_deficit_exposure` can be carried as a number, in `dimensionless`. The examples never do (E2); see `OPEN` 3 |
| A7 | `water_deficit_exposure` can be carried per agricultural year instead of per rotation |
| A8 | A table with a single rotation is accepted |

### The examples

| Code | Case |
|---|---|
| E1 | `examples/` holds exactly the two files, both named `PLACEHOLDER_…`. Every text in them that is not a word of a closed list carries the word PLACEHOLDER, and so does the source of every number |
| E2 | Both examples show `water_deficit_exposure` missing, with its reason, in `dimensionless`, and never as a number |
| E3 | Both examples name the carbon model and the computation of every `soil_carbon_trend` value, show two carbon models, and show the default computation for each |
| E4 | Both examples show a number with a range, a number without a range and its reason, a missing value, and all three indicators |

### The models against the conventions sheet

These cases read `contracts/CONVENTIONS.md` and fail if the sheet and the models stop agreeing.

| Code | Case |
|---|---|
| C1 | The identifier, the unit strings and the direction of each indicator are those of C1.2, C1.3 and C1.5; the lists of indicators and directions are those of C1.1 |
| C2 | The reason codes are those of the table of C3.2, in its order |
| C3 | The provenance labels are those of the table of C4.1, in its order; the label of soil loss is the one of C4.6 |
| C4 | There are three trend computations and the default is the first of C1.6 |

### Rejected: one value

| Code | Case |
|---|---|
| U1 | A value without a unit: the field absent, on a number and on a missing value |
| U2 | A unit that is `null` or empty |
| U3 | A unit not written exactly as in the sheet: another spelling, another letter case |
| U4 | The unit of another indicator |
| U5 | Annual soil loss in the monthly unit; monthly soil loss in the annual unit (per rotation only) |
| P1 | A value without a provenance label: the field absent, or `null` |
| P2 | A label that is not one of the four, or is in lower case |
| P3 | A missing value that carries a provenance label |
| P4 | Soil loss with a label other than `DERIVED` |
| P5 | A value with neither a source nor the assumption mark; with both; with a blank source; with an assumption mark that is not `true` or `false` |
| P6 | A missing value that carries a source |
| M1 | A missing value without a reason: no `missing` part; `missing` is `null`; `reason` absent, `null` or empty |
| M2 | A reason code that is not in the list, or is in lower case |
| M3 | A missing value written as zero next to a reason (`0` and `0.0`); any number next to a reason |
| M4 | A missing value written as an empty string, as the text `NA` or as not-a-number; an infinite value; a number written as text; `true` in place of a number |
| M5 | The `value` field left out, of a missing value and of a number. It is not read as missing |
| M6 | Reason `MISSING_INPUT` without a detail that names the input; a blank detail |
| M7 | A missing value that carries a range, or a reason for a missing range |
| R1 | A range without its kind: the field absent, `null` or empty |
| R2 | A range with one bound only; a bound written as text; an infinite bound |
| R3 | `low` above `high` |
| R4 | The value below `low`; the value above `high` |
| R5 | An absent range written as two bounds equal to the value |
| R6 | A number with no range and no reason for it, fields absent or `null` |
| R7 | A range together with a reason for a missing range |
| R8 | A range written as a list or as text |
| I1 | An indicator identifier that the conventions sheet does not define; one in upper case; a value without an identifier |
| I2 | A direction other than the two the sheet allows; one in upper case; a value without a direction |
| I3 | One of the two allowed directions on an indicator that has the other one, for each of the three indicators |
| I4 | A value of another indicator among the annual soil-loss values (per rotation only) |
| X1 | An unknown extra field: in the document, in a value, in a range, in a `missing` part, in the soil-loss part; a misspelt field name |

### Rejected: structure

| Code | Case |
|---|---|
| D1 | A document without `case_id`, with a blank `field_id`, with an identifier that is not text; results per rotation without `rotation_id`; a table row without `rotation_id` or `scenario_id`, or with a blank `scenario_id` |
| S1 | Month number 0 or 13; a month without its calendar year or without its agricultural year |
| S2 | An agricultural year written as text or with a fraction; an annual value without its agricultural year |
| S3 | An agricultural year with eleven monthly values; a calendar month given twice |
| S4 | Months that are not twelve consecutive calendar months; an agricultural year named after a calendar year it does not begin in |
| S5 | Agricultural years that begin in different calendar months |
| S6 | An annual value whose months are left out; months whose annual value is left out; no annual value at all; the monthly breakdown left out |
| S7 | An agricultural year given twice in `annual` |
| W1 | `water_deficit_exposure` on the time basis `rotation` with an agricultural year; on `ag_year` without one; with a time basis not in the list; without a time basis |
| W2 | Two values for the whole rotation; values on both time bases, per rotation and in the table; an agricultural year given twice; no value at all |
| K1 | A `soil_carbon_trend` value without its carbon model, with a blank one, or without its computation, per rotation and in the table |
| K2 | A computation that is not one of the three |
| K3 | A carbon model without one of the three computations, or with one of them twice; no carbon value at all (per rotation only) |
| T1 | The same cell of a rotation in two rows |
| T2 | A row left out for one rotation; rotations with different agricultural years or different scenarios; a table without rows |
| T3 | Soil loss for the whole rotation, or without its agricultural year; a carbon trend for one agricultural year |
| T4 | A soil-loss row that names a carbon model; a water row that names a computation |

### The list itself

| Code | Case |
|---|---|
| Z1 | The codes in this section are exactly the codes tested in `test_examples.py` |

## OPEN

Questions for a person. None is answered by this unit. Items 1 to 6 come from the conventions sheet; the rest are points where the sheet and the blueprint are silent and this unit proposed something.

1. **Kinds of range (C2.3).** The closed list of `kind` labels is not supplied. The models accept any non-blank text; the examples use `PLACEHOLDER_range_kind`. When the list exists, `kind` becomes a closed list and no engine can report a range before then.
2. **Time basis of `water_deficit_exposure` (C1.3).** Not decided. The contracts carry either one value per rotation or one per agricultural year. When it is decided, one of the two goes away. Whether this indicator has a monthly breakdown is part of the same question; today the contracts have none.
3. **`water_deficit_exposure` as a number (C1.4).** The sheet says no engine reports it as anything but missing while its definition is incomplete. The examples show it missing. The models do not enforce that rule: they accept a number in `dimensionless`, so that the decision layer can be tested with hand-made tables and the contract does not have to change when the definition is complete. Should the models reject a number until then?
4. **Reason code for "the definition is not decided yet".** No code of C3.2 says it. The examples use `NOT_AVAILABLE` with a detail. Is that the right code?
5. **Descriptive measures of water deficit (C1.4).** The three descriptive measures have no identifier and no unit in the sheet, so these contracts do not carry them. Do they travel here, and under which identifiers and units?
6. **Soil depth and horizon of the carbon trend (C1.6); start month of the agricultural year (C5.4); gap filling (C3.4).** These contracts do not repeat the soil depth, the horizon or the start month: a consumer reads them from the contract that owns them. They carry no mark for a value computed from a gap-filled series, because no gap is filled until the method is supplied. Does any of the four belong in a results document?
7. **Identifiers of the carbon models.** `carbon_model` is any non-blank text. Which identifiers do the two carbon models (and the two variants of one of them, if they are reported apart) have, and which contract fixes the list?
8. **Identifiers of the three computations.** `end_minus_start`, `fitted_slope` and `mean_over_cycles` are proposed here for the three computations of C1.6. Accept or rename.
9. **Scenarios.** `scenario_id` says which rows of the table come from the same run. Which contract says what a scenario is (which uncertain input, at which level): the test plan? Does the decision layer need the level of the uncertain input in the table itself?
10. **`case_id`, `field_id`, `rotation_id`.** Any non-blank text. Their format belongs to the rotation definition and saved case contracts. Are both `case_id` and `field_id` needed here? May one table hold more than one field?
11. **What `source` holds for a computed indicator.** The sheet asks for a reference to the source (C4.2). For a value an engine computed, is that the name of the engine and method, a link to the method documentation, or something else? Is the assumption mark ever right for an indicator?
12. **A missing value without a source.** Proposed: a missing value carries no source and no assumption mark. The sheet does not say.
13. **Bounds equal to the value.** Proposed: rejected, reading C2.2. This also rejects a range that truly has no width. Confirm.
14. **Completeness.** Proposed: every agricultural year has its twelve months, every carbon model its three computations, and every rotation of a table the same cells, with missing values written out. This makes documents longer and makes "left out" impossible. Confirm, or name what may be left out.
15. **Months add up to the year (C1.2).** The models do not check that the monthly values of an agricultural year add up to its annual value: the check needs a tolerance, which is a value a person supplies. Where does that check live?
16. **Label of monthly soil loss.** C4.6 fixes `DERIVED` for the soil-loss indicator. The models apply it to the monthly values too. Confirm.
17. **No bound on any number.** The models check no sign and no limit on any indicator value; the sheet states none. Invariants belong to the tests of the engines.
18. **`direction` in every value.** Proposed: each value carries the direction of its indicator, so one item is enough for a consumer. The alternative is to state it once per document.
19. **A shared value item for the other contracts.** Other contracts will carry values with range, missing reason and provenance. `IndicatorValue` is specific to the three indicators. Whether a common item is shared from one place is a decision for the lane owner.
20. **Repeated keys in a JSON file.** The models load JSON as Pydantic reads it: if a key is written twice in one object, the last one wins and no error is raised. A check for that would have to run before the model.

## Not covered

- Any computation, decision logic or threshold.
- Daily series and their time zone (section 6 of the sheet): these contracts carry no daily series.
- The carbon balance by month, year and rotation: it travels in the `CarbonBalance` contract (C1.5).
- Engine entry points (`contracts/ENTRYPOINTS.md`).
