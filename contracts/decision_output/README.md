# Contract: decision output

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until a person approves the pull request.

| Contract | Producer → consumer | Model | Example |
|---|---|---|---|
| Decision output | Platform, decision (L2b, `decision/`) → Interface (L3, the decision screens) | `models.DecisionOutput` | `examples/PLACEHOLDER_decision_output.json` |

Purpose, from blueprint section 5: **decision screens are built before the calculation exists.** One document per field: the declared limits, the counts by year against them, the paired differences between rotations, the state and the measurement priority (the `decision/` row of blueprint section 4). The tipping point is not here: it is the Block 2 unit [D3].

Source: the example, design choices and OPEN items the interface developer wrote in issue #96, as producer (L2b) and as consumer (L3). Landed by a lane L0 builder under decision D40 of issue #77, following #68.

**The example is PLACEHOLDER data.** It is read off the results table example (`contracts/results/examples/PLACEHOLDER_results_table.json`): the same case, field, rotations and scenario; its rows not evaluated are the missing rows of that table, and its differences are second minus first of that table's pairs. The limit (`7.0`) is the producer's illustrative number. The `measure_first` item is the producer's, as written. It describes no real place, field or producer, and says `"example_data": true`.

Acceptance test, from the repository root:

```bash
uv run pytest contracts/decision_output/
```

Models and pure validation only. No network calls, no thresholds, no state wording, no citations.

## Shared parts, reused

Imported, not copied:

- From `contracts/inputs/common.py`: `Value` (a number with its unit, provenance, source or assumption mark, and `range` or `range_missing`; or `null` with its `missing` part, keeping its unit: C2.1, C2.2, C3.1, C4.1, C4.2), `Missing` (a reason code of C3.2 and an optional `detail`; `MISSING_INPUT` needs a `detail`), `Range`, `NonEmptyStr` and `ContractModel` (unknown fields rejected, no type coercion).
- From `contracts/results/models.py`: the indicator identifiers (`IndicatorId`, C1.1), their units (`UNITS_OF`, C1.2, C1.3, C1.5), the time bases (`TimeBasis`), the carbon models (`CarbonModel`: only `amg` and `rothc`, D1 of #77) and the trend computations (`TrendComputation`, C1.6).

The cell rules of `ResultsTableRow` (soil loss one value per agricultural year; soil carbon trend one value per rotation with its carbon model and computation; only soil carbon trend names a model) are a method of that class, not a shared function, so `models.py` repeats them in `_check_cell` with the same convention codes. If lane L0 makes them a shared function, this folder imports it.

## Fields (`models.py`)

All PROPOSED.

### `DecisionOutput`

| Field | Type | Rule |
|---|---|---|
| `contract` | `"decision_output"` | Required. Names the document |
| `example_data` | true or false | Required |
| `case_id`, `field_id` | text | Required, not blank. As in `contracts/results/` |
| `rotations` | list of text | The `rotation_id` values of the rotations compared, as in `ResultsTable`. At least two; none twice |
| `scenarios` | list of text | The `scenario_id` values the document covers, as in `ResultsTable`. At least one; none twice |
| `limits` | list of `LimitItem` | At most one item per indicator. Every indicator that has a count has an item here |
| `counts_by_year` | list of `CountByYear` | One item per rotation, scenario and indicator. An indicator that is counted is counted for every rotation of every scenario |
| `paired_differences` | list of `PairedDifferenceItem` | A pair and a cell appear once |
| `state` | `State` | Required |
| `measure_first` | list of `MeasureFirstItem` | In rank order. May be empty |

Every `rotation_id` and `scenario_id` named in a count or a difference is one of `rotations` and `scenarios`.

### `LimitItem`: the limit of one indicator (D1)

| Field | Type | Rule |
|---|---|---|
| `indicator` | indicator identifier | C1.1 |
| `limit` | `Value` | The unit of the indicator in the results table (soil loss: `t ha-1 yr-1`). A limit that holds a number carries the label `DECLARED` (C4.1, C4.5; as `DeclaredLimit` of `decision/functions.py`), its source, and its `range` or `range_missing`. A limit that is not declared is `null` with its `missing` part and keeps its unit (C3.1, D60 of #77) |

The preferred side of a limit is not a field: it is the `direction` of the indicator (C1.1), which `decision/functions.py` reads from the rows. Whether a value equal to the limit counts as within is OPEN (D1); the document carries the counts, not the rule.

### `CountByYear`: counts against the limit (D1)

| Field | Type | Rule |
|---|---|---|
| `rotation_id`, `scenario_id` | text | Listed in `rotations` and `scenarios` |
| `indicator` | indicator identifier | Has an item in `limits` |
| `years_evaluated` | integer, 0 or more | Rows that held a value and were judged against the limit |
| `years_within_limits` | integer, 0 or more, or `null` | Not more than `years_evaluated`. `null` exactly when the limit of the indicator is missing; then `years_evaluated` is 0 (D60: nothing is judged) |
| `not_evaluated` | list of `NotEvaluated` | Required; may be empty. Each row of the results table that was not evaluated: `time_basis`, `ag_year`, `carbon_model`, `computation` (the rest of its cell, under the cell rules) and `missing` with its reason. A row appears once |

A row without a value never counts as within or outside and never as zero (C3.1, D6).

### `PairedDifferenceItem`: one difference (D2)

| Field | Type | Rule |
|---|---|---|
| `pair` | two texts | Two different `rotation_id` values, listed in `rotations`. The difference is the second minus the first |
| `scenario_id`, `indicator`, `time_basis`, `ag_year`, `carbon_model`, `computation` | as in `ResultsTableRow` | The cell of the results table the difference comes from, under the cell rules. A difference is never taken across cells (D2) |
| `difference` | `Value` | In the unit of the indicator in the results table. When a side of the pair holds no value it is `null` with its `missing` part (C3.3; D2 gives `MISSING_INPUT` naming the side). A difference that holds a number carries its `range` or `range_missing`: today every range of a difference is missing, with its reason (D2) |
| `method` | text | The paired-difference method. OPEN (issue #96, OPEN 2); the example keeps the producer's `OPEN: ...` text |

### `State` (D7)

| Field | Type | Rule |
|---|---|---|
| `value` | text or `null` | The state. Its names and wording are OPEN (issue #96, OPEN 1), so any non-blank text is accepted for now; the example keeps the producer's `OPEN: ...` text |
| `missing` | `Missing` | Present exactly when `value` is `null`: a state the decision layer cannot give carries its reason (C3.1) |
| `indicators_not_resolved` | list of indicator identifiers | The indicators the data do not separate (D7). None twice; may be empty |
| `reasons` | list of text | Texts from deterministic templates. Their wording is for people |

### `MeasureFirstItem` (D4)

| Field | Type | Rule |
|---|---|---|
| `rank` | integer, 1 or more | Inputs that tie share a rank (D4). The list is in rank order |
| `what`, `why` | text | Not blank. Qualitative: no monetary value, no other field (#96) |

## The three points of D40

Decision D40 of issue #77 asks the landing to state three points, for the interface developer to accept as producer and as consumer.

1. **Rotations are referenced by `rotation_id`**, the identifier of `contracts/results/` (`ResultsPerRotation.rotation_id`, `ResultsTableRow.rotation_id`), not by free labels such as `current` and `alternative-1`. `rotations` lists them, and a count names its rotation in `rotation_id`. The model cannot tell a label from an identifier (both are text); the rule binds the producer, which copies the identifiers from the results table it reads.
2. **Scenarios appear.** PROPOSED: the document lists the `scenario_id` values it covers in `scenarios`, and every count and every paired difference carries its `scenario_id`. Why: in `ResultsTable` a cell includes `scenario_id`, and D2 pairs rows only within one cell, so a difference without its scenario cannot be traced to its rows; a count of agricultural years over two scenarios would count each year twice. The state stays one per document: how it relates to the scenarios belongs with the tipping point (D3, Block 2) and is OPEN (item 5).
3. **`limit` has the value shape of C2.1**: one item carrying the number, the unit, the provenance, the source and `range` or `range_missing`, the shape `difference` already has. Both are `Value` of `contracts/inputs/`.

## Differences from the producer's example

For the interface developer, to accept or to contest. There are six differences from the example of issue #96. The test holds the example of issue #96 as written, applies these six differences, checks that the result is valid, and checks that leaving out any one of differences 2 to 6 makes it invalid.

### 1. Rotations by `rotation_id`, and the key of a count is `rotation_id`

D40 point 1. The example uses the identifiers of the results table example (`PLACEHOLDER_rotation_a`, `PLACEHOLDER_rotation_b`) in place of `current` and `alternative-1`, and a count names its rotation in `rotation_id` (the key in `contracts/results/`) in place of `rotation`. The case and field identifiers are those of the same example (`PLACEHOLDER_case`, `PLACEHOLDER_field`) in place of `example-case` and `example-field-1`, so the example can be checked against it. The old key is the rejected case `count-with-producer-key-rotation`.

### 2. Scenarios

D40 point 2: `scenarios` at the top, and `scenario_id` on every count and every difference. Why: above, under "The three points of D40".

### 3. `limit` in the value shape of C2.1

D40 point 3. Issue #96 writes:

```json
{ "indicator": "soil_loss", "limit": { "value": 7.0, "unit": "t ha-1 yr-1" },
  "provenance": "DECLARED", "source": "user" }
```

The landed example writes:

```json
{ "indicator": "soil_loss",
  "limit": { "value": 7.0, "unit": "t ha-1 yr-1",
             "range_missing": { "reason": "NOT_DECLARED", "detail": "..." },
             "provenance": "DECLARED", "source": "user" } }
```

The provenance and the source move inside `limit`, and the limit gives its range or the reason it has none (C2.2), as `difference` does. The reason in the example is placeholder. A limit that is not declared is a missing value with its reason, kept in the list (C3.1, D60): the example shows one for `water_deficit_exposure`. The shape of the issue is the rejected case `limit-in-the-producer-shape`.

### 4. A count lists its rows not evaluated

D1 says a row with a missing value is "reported as not evaluated, with its reason", and D60 of #77 says an indicator with no declared limit appears with every row "not evaluated". Issue #96 has no place for those rows. A count carries `not_evaluated`, each item naming its row and its reason. The example uses it for the missing soil-loss year and for `water_deficit_exposure`, reported missing `NOT_AVAILABLE` for both rotations (C1.4, D61 of #77), as the producer's design choice asks; the issue did not show those rows in its example. When the limit is missing, `years_within_limits` is `null` and no row is evaluated (D60).

### 5. A difference names its cell

D2 (written after #96, merged in #138) computes a difference only between the two rows of one cell, never across cells. The difference of issue #96 has no agricultural year: one soil-loss difference for the whole pair, which would be a summary across years. The landed difference names its cell (`scenario_id`, `time_basis`, `ag_year`, `carbon_model`, `computation`), as `PairedDifference` of `decision/functions.py` does. Whether the document also carries a summary over agricultural years, and by which method, is the paired-difference method of issue #96, OPEN 2. The shape of the issue is the rejected case `difference-across-years`.

### 6. The state names the indicators not resolved

D7: "the state is 'not resolved' and names the indicators that are not resolved". `state` carries `indicators_not_resolved`, as `PairState` of `decision/functions.py` does. The state may also be `null` with its `missing` part (C3.1), for a state the decision layer cannot give; the issue's shape, a text `value` with `reasons`, stays valid.

**Unchanged:** `contract`, `example_data`, `case_id`, `field_id`, `pair`, `difference`, `method`, `value` and `reasons` of the state, `years_evaluated`, `years_within_limits`, `measure_first` with `rank`, `what` and `why`.

## PROPOSED cases

Every case below is a change to the example. The rejected ones must be rejected for the stated reason; the identifiers are the test identifiers in `test_examples.py`.

### Rejected

| Case | The variant |
|---|---|
| `unknown-field` | A part the contract does not name, at the top level |
| `contract-left-out` | No `contract` |
| `contract-of-another-document` | `contract` names another document |
| `example-data-left-out` | No `example_data` |
| `case-id-blank` | `case_id` is blank |
| `one-rotation` | `rotations` holds one rotation |
| `rotation-listed-twice` | A rotation is listed twice |
| `scenarios-left-out` | No `scenarios` |
| `no-scenario` | `scenarios` is empty |
| `limit-in-the-producer-shape` | The limit in the shape of issue #96: provenance and source beside `limit` (difference 3) |
| `limit-without-range-or-reason` | A limit with a number loses `range_missing` (C2.2) |
| `limit-without-source` | A limit with a number loses its source (C4.2) |
| `limit-not-declared` | A limit carries the label `OBSERVED` |
| `limit-in-another-unit` | The soil-loss limit is in the monthly unit (C1.1) |
| `limit-written-as-text` | The number of a limit written as text |
| `missing-limit-written-as-zero` | The missing limit keeps its `missing` part and its value is zero (C3.1) |
| `missing-limit-without-reason` | The missing limit loses its `missing` part (C3.1) |
| `two-limits-of-one-indicator` | Two limits of one indicator |
| `counted-indicator-without-limit-item` | An indicator is counted and has no item in `limits` (C3.1, D60) |
| `count-names-rotation-not-listed` | A count names a rotation not in `rotations` |
| `count-names-scenario-not-listed` | The counts name a scenario not in `scenarios` |
| `count-with-producer-key-rotation` | A count carries the key `rotation` of issue #96 (difference 1) |
| `count-without-scenario` | A count has no `scenario_id` |
| `count-without-not-evaluated` | A count has no `not_evaluated` |
| `within-greater-than-evaluated` | `years_within_limits` is greater than `years_evaluated` |
| `negative-count` | `years_evaluated` is negative |
| `count-written-as-text` | `years_evaluated` written as text |
| `within-null-with-a-declared-limit` | `years_within_limits` is null although the limit is declared |
| `within-counted-without-a-limit` | `years_within_limits` is given for an indicator without a declared limit (D60) |
| `evaluated-without-a-limit` | `years_evaluated` is not zero for an indicator without a declared limit (D60) |
| `count-repeated` | Two counts of one rotation, scenario and indicator |
| `rotation-left-out-of-counts` | A counted indicator is not counted for one rotation |
| `uncounted-rotation` | A third rotation is listed and not counted |
| `not-evaluated-without-reason` | A row not evaluated loses its `missing` part |
| `not-evaluated-soil-loss-per-rotation` | A soil-loss row not evaluated has the time basis `rotation` (C1.2) |
| `not-evaluated-row-twice` | A row not evaluated is listed twice |
| `difference-pair-of-one-rotation` | A pair holds one rotation twice |
| `difference-pair-of-three` | A pair holds three rotations |
| `difference-names-rotation-not-listed` | A pair names a rotation not in `rotations` |
| `difference-without-scenario` | A difference has no `scenario_id` |
| `difference-across-years` | A soil-loss difference without `time_basis` and `ag_year`, as in issue #96 (difference 5) |
| `difference-soil-loss-without-year` | A soil-loss difference keeps `time_basis` `ag_year` and has no `ag_year` (C5.3) |
| `difference-carbon-without-model` | A carbon difference has no `carbon_model` (C1.5) |
| `difference-carbon-model-not-decided` | A carbon difference names a model other than `amg` or `rothc` (D1 of #77) |
| `difference-model-on-soil-loss` | A soil-loss difference names a carbon model |
| `difference-in-another-unit` | A soil-loss difference is in the monthly unit (C1.1) |
| `difference-without-range-or-reason` | A difference with a number loses `range_missing` (C2.2) |
| `difference-without-provenance` | A difference with a number loses its label (C4.1) |
| `missing-difference-written-as-zero` | A missing difference keeps its `missing` part and its value is zero (C3.1) |
| `missing-difference-without-reason` | A missing difference loses its `missing` part (C3.1) |
| `difference-repeated` | The same pair and cell twice |
| `difference-without-method` | A difference has no `method` |
| `state-without-value-or-reason` | The state is null with no `missing` part (C3.1) |
| `state-with-value-and-reason` | The state holds a value and a `missing` part (C3.1) |
| `state-without-indicators-not-resolved` | The state has no `indicators_not_resolved` (difference 6) |
| `state-names-unknown-indicator` | `indicators_not_resolved` names an identifier that is not an indicator (C1.1) |
| `state-names-indicator-twice` | `indicators_not_resolved` names one indicator twice |
| `measure-first-rank-zero` | A rank of zero |
| `measure-first-out-of-rank-order` | The items are not in rank order |
| `measure-first-with-monetary-value` | An item carries a value of information (#96: no monetary value) |
| `measure-first-blank-why` | An item with a blank `why` |

### Accepted

| Case | The variant |
|---|---|
| `declared-water-limit` | A limit of `water_deficit_exposure` with a number; the water counts give `years_within_limits` 0 with no row evaluated |
| `tied-ranks` | Two inputs share rank 1 and the next is rank 3 (D4: ties share a rank) |
| `resolved-without-priority` | No indicator not resolved, and an empty `measure_first` |
| `state-not-given` | The state is null with its reason |
| `no-counts-no-differences` | No limit, no count and no difference |
| `swapped-pair` | The same cell with the pair swapped, and the sign of the difference flipped |
| `example-data-false` | `example_data` is false |

The model does not check what it cannot see: that `rotations` are the identifiers of the results table, that counts and differences equal what the decision functions compute, that a priority list is given only when the state is not resolved (D4), or that the state agrees with `indicators_not_resolved`. Those are duties of the producer, tested in `decision/`. For the example alone, `test_examples.py` checks that its identifiers, its rows not evaluated and its differences agree with the results table example.

## OPEN

Each item is a question a person has to answer. Until then the model keeps the shape above.

1. **The exact state names and their wording.** Issue #96, OPEN 1; D7. Until then `state.value` is any non-blank text, and `decision/functions.py` uses the placeholder constant `NOT_RESOLVED`. For the science reviewers.
2. **The paired-difference method, its range and its citation.** Issue #96, OPEN 2; D2. Includes whether the document also carries a difference summarised over agricultural years, and by which method (difference 5). For the science reviewers.
3. **Whether counts also reference an official tolerance, as information.** Issue #96, OPEN 3. The source of a soil-loss tolerance is OPEN in #77 (D10). If one enters, PROPOSED: it travels as its own item with its own source and provenance, never as an edit of the user's declared limit (the producer's design choice). For the science reviewers.
4. **Equality at the limit.** D1: whether a value equal to the limit counts as within. The counts carry the result, not the rule; whether the document should also say which setting produced them is for the producer and the science reviewers.
5. **The state and the scenarios.** PROPOSED here: one state per document. Whether the state is given per scenario, or per pair of rotations when there are more than two (`PairState` of `decision/functions.py` is per pair), goes with the tipping point (D3) and the thin matrix of Block 2. For the interface developer as producer and consumer, and the lead developer.
6. **Which reason a row carries when it holds a value and its indicator has no declared limit.** D60 says it is "not evaluated", with its reason; no code of C3.2 is decided for that case (`NOT_DECLARED` is a candidate). The example does not need it: every water row is missing on its own. For the lead developer.
7. **Counts of indicators that are not annual.** A count of `soil_carbon_trend` counts rows (one per carbon model and computation), not agricultural years, under the names `years_evaluated` and `years_within_limits` of issue #96. Whether those names stay, and how the two carbon models are counted when they disagree (D7), is for the interface developer and the science reviewers.

## Notes for the producer

Read on `main` while landing this contract; nothing here changes `decision/`.

- `limit_counts` of `decision/functions.py` counts per rotation and indicator over every scenario of the table. With one scenario it agrees with this contract; with more, this contract counts per scenario (D40 point 2).
- For an indicator without a declared limit, `limit_counts` reports `evaluated` as the number of rows that hold a value. D60 of #77, decided after, says every row is "not evaluated". This contract follows D60: `years_evaluated` is 0 and `years_within_limits` is `null`.
- `pair_state` returns a state per pair of rotations; this contract has one `state` per document (OPEN item 5).
