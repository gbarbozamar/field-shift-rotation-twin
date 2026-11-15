# Contract: decision output

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until a person approves the pull request.

| Contract | Producer → consumer | Model | Example |
|---|---|---|---|
| Decision output | Platform, decision (L2b, `decision/`) → Interface (L3, the decision screens) | `models.DecisionOutput` | `examples/PLACEHOLDER_decision_output.json` |

Purpose, from blueprint section 5: **decision screens are built before the calculation exists.** One document per field: the declared limits, the counts by year against them, the paired differences between rotations, the state and the measurement priority (the `decision/` row of blueprint section 4). The tipping point is not here: it is the Block 2 unit [D3].

Source: the example, design choices and OPEN items the interface developer wrote in issue #96, as producer (L2b) and as consumer (L3). Landed by a lane L0 builder under decision D40 of issue #77, following #68. The fields that decisions D85 to D99 of issue #77 ask for were added by unit `l0/decision-output-d85-d99` (brief: issue #193); they are listed under "Fields added by D85 to D99", and the places where two of those decisions do not fit together as written are listed under OPEN (K1 to K3 and K7, as numbered in pull request #190, and K8 to K12). Decisions D151 to D156 of issue #77 (15 November 2026) resolve K1, K2, K4 to K7 and K12; what is left of K3, and K8 to K11, stay unresolved.

**The example is PLACEHOLDER data.** Its identifiers chain with the other examples of the repository: case `example-case`, field `example-field-1` and rotation `example-rotation-1`, as in the rotation definition example and the web example case. A decision compares at least two rotations, and no second rotation identifier exists in another example, so the second rotation is `example-rotation-2` (OPEN item 8). Its values are read off the results table example (`contracts/results/examples/PLACEHOLDER_results_table.json`), whose own identifiers are `PLACEHOLDER_case`, `PLACEHOLDER_field`, `PLACEHOLDER_rotation_a` and `PLACEHOLDER_rotation_b`; the test matches the two sets of identifiers in one table (`IDS_IN_THE_RESULTS_TABLE_EXAMPLE`). The scenario is that example's `PLACEHOLDER_scenario_one`, since no other example names a scenario. The rows not evaluated are the missing rows of that table, and the differences are second minus first of that table's pairs; the range of a difference follows D92 from that table's ranges (the soil-loss difference of 2001 is `[4.0 − 18.0, 12.0 − 6.0]`; the soil-carbon difference has none, since one side has none). The counts of the pair's cells and its coverage are read off those differences. Its state is placeholder data: the pair has one cell whose range crosses zero and one with no range, the case of K12, which D152 of issue #77 settles; the state the example writes is the one D152 gives such a pair. The limit (`7.0`) is the producer's illustrative number. The soil-loss tolerance of "equal" (`0.0`) is PLACEHOLDER, written only so that the example shows a count by the sign of the point value; it proposes no tolerance (D87 leaves it to the designer of the case). The `measure_first` item is the producer's, as written. It describes no real place, field or producer, and says `"example_data": true`.

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
| `counts_by_year` | list of `CountByYear` | One item per rotation, scenario, indicator, carbon model and computation (D94). An indicator that is counted is counted for every rotation of every scenario |
| `range_across_scenarios` | list of `RangeAcrossScenarios` | The summary of the counts over the scenarios (D96). One item per rotation, indicator, carbon model and computation; each summarises a count. May be empty |
| `paired_differences` | list of `PairedDifferenceItem` | A pair and a cell appear once |
| `equal_tolerances` | list of `EqualToleranceItem` | The tolerance of "equal" (D87). At most one item per indicator. Every indicator that has a count of a pair's cells has an item here |
| `pair_cell_counts` | list of `PairCellCount` | The counts of a pair's cells (D87, D99). One item per pair, scenario and indicator |
| `pair_states` | list of `PairState` | The state of each pair, its reason and its coverage (D85, D86, D88, D91, D97). One item per pair of rotations, in either order. May be empty |
| `state` | `State` | Required |
| `measure_first` | list of `MeasureFirstItem` | In rank order. May be empty |

Every `rotation_id` and `scenario_id` named in a count, a range, a difference, a count of a pair's cells or a state of a pair is one of `rotations` and `scenarios`.

### `LimitItem`: the limit of one indicator (D1)

| Field | Type | Rule |
|---|---|---|
| `indicator` | indicator identifier | C1.1 |
| `limit` | `Value` | The unit of the indicator in the results table (soil loss: `t ha-1 yr-1`). A limit that holds a number carries the label `DECLARED` (C4.1, C4.5; as `DeclaredLimit` of `decision/functions.py`), its source, and its `range` or `range_missing`. A limit that is not declared is `null` with its `missing` part and keeps its unit (C3.1, D60 of #77) |

The preferred side of a limit is not a field: it is the `direction` of the indicator (C1.1), which `decision/functions.py` reads from the rows. A value equal to the limit counts as within (D90); the document carries the counts, not the rule. The limit is the one the user declares, and the count of years within it is descriptive; admissibility is decided only by D74 against a verified T, never by this limit, and a T never edits it (D89). Admissibility has no field in this document yet (OPEN 3).

### `CountByYear`: counts against the limit (D1, D94, D95)

| Field | Type | Rule |
|---|---|---|
| `rotation_id`, `scenario_id` | text | Listed in `rotations` and `scenarios` |
| `indicator` | indicator identifier | Has an item in `limits`. Not `soil_carbon_trend`: it is one value per rotation (C1.5), and an indicator whose time basis is not `ag_year` has no count of years (D95) |
| `carbon_model`, `computation` | as in `ResultsTableRow`, or absent | PROPOSED (D94): part of the key of a count. Under the cell rules only `soil_carbon_trend` names them, and by D95 that indicator has no count, so today both are always absent (OPEN, K11) |
| `years_evaluated` | integer, 0 or more | Rows that held a value and were judged against the limit. Only rows whose `time_basis` is `ag_year` are counted (D95) |
| `years_within_limits` | integer, 0 or more, or `null` | Not more than `years_evaluated`. `null` exactly when the limit of the indicator is missing; then `years_evaluated` is 0 (D60: nothing is judged) |
| `not_evaluated` | list of `NotEvaluated` | Required; may be empty. Each row of the results table that was not evaluated: `time_basis`, `ag_year`, `carbon_model`, `computation` (the rest of its cell, under the cell rules) and `missing` with its reason. A row appears once. Its `time_basis` is `ag_year` (D95) |

A row without a value never counts as within or outside and never as zero (C3.1, D6). Nothing is counted across scenarios or across carbon models (D94). An indicator on another time basis (the water ratio when it is per rotation) has no count: it is judged only by the admissibility of D74, once per scenario and carbon model, and a limit a user declares for it is not used in the counts (D95).

### `RangeAcrossScenarios`: the counts summarised over scenarios (D96)

PROPOSED. D96: "Only the range, from minimum to maximum, of the years within the limit across the admitted scenarios, naming the scenario of the minimum. No mean, share or percentage of scenarios." How the screen shows it is for the interface developer (D96).

| Field | Type | Rule |
|---|---|---|
| `rotation_id` | text | Listed in `rotations` |
| `indicator`, `carbon_model`, `computation` | as in `CountByYear` | With `rotation_id`, the key of a count without its scenario (D94). At least one count in `counts_by_year` has that key |
| `minimum`, `maximum` | integer, 0 or more, or `null` | Years within the limit; `minimum` not more than `maximum` |
| `scenario_of_the_minimum` | text or `null` | Listed in `scenarios`; its count of that key gives `years_within_limits` equal to `minimum` |
| `missing` | `Missing` | The three parts above are given together, or all three are `null` with this part (C3.1), for example when the limit is not declared and no year is judged (D60) |

No other part is accepted: a mean or a share of scenarios is rejected (cases `range-with-a-mean`, `range-with-a-share-of-scenarios`). Which scenarios are admitted (D74) is not in the document, so the model does not check that the range is taken over them (OPEN 9).

### `PairedDifferenceItem`: one difference (D2)

| Field | Type | Rule |
|---|---|---|
| `pair` | two texts | Two different `rotation_id` values, listed in `rotations`. The difference is the second minus the first |
| `scenario_id`, `indicator`, `time_basis`, `ag_year`, `carbon_model`, `computation` | as in `ResultsTableRow` | The cell of the results table the difference comes from, under the cell rules. A difference is never taken across cells (D2) |
| `difference` | `Value` | In the unit of the indicator in the results table. When a side of the pair holds no value it is `null` with its `missing` part (C3.3; D2 gives `MISSING_INPUT` naming the side). A difference that holds a number carries its `range` or `range_missing`. By D92 the range of B − A is `[b_low − a_high, b_high − a_low]`, and both ranges carry the same `kind` (C2.3); if either range is missing or the kinds differ, the range of the difference is missing with its reason. The model checks the shape, not the arithmetic; `test_examples.py` checks the arithmetic for the example |
| `method` | text | The paired-difference method. OPEN (issue #96, OPEN 2); the example keeps the producer's `OPEN: ...` text |

### `EqualToleranceItem`: the tolerance of "equal" (D87)

PROPOSED. D87: "'Equal' uses the tolerance set by the designer of the case."

| Field | Type | Rule |
|---|---|---|
| `indicator` | indicator identifier | C1.1 |
| `tolerance` | `Value` | In the unit of the indicator in the results table. A tolerance that holds a number carries the label `DECLARED`, its source and its `range` or `range_missing`, as a limit does. A tolerance not set is `null` with its `missing` part and keeps its unit (C3.1) |

### `PairCellCount`: the counts of a pair's cells (D87, D99)

PROPOSED. For each pair, scenario and indicator, read in the direction of each row (C1.1), the difference being the second rotation minus the first. It is a count of D2's differences: it never resolves a pair, and no statistic or p-value is attached (D87). D99: "Two counts, shown apart and never added."

| Field | Type | Rule |
|---|---|---|
| `pair` | two texts | Two different `rotation_id` values, listed in `rotations`. Second minus first |
| `scenario_id` | text | Listed in `scenarios` |
| `indicator` | indicator identifier | Has an item in `equal_tolerances` |
| `by_difference_range` | `strict_improvement`, `deterioration`, `not_separated`: integers, 0 or more | The cells whose difference has a range, classed by that range, by D93 and D98 (D99). A cell whose difference has no range is not counted here |
| `by_sign_of_point_value` | `better`, `worse`, `equal`, `missing_side`: integers, 0 or more; or `null` | Every cell of the pair, scenario and indicator, by the sign of the point value, labelled as such (D99): better, worse or equal, and cells with a missing side (D87). "Equal" uses the tolerance (D87). A cell without a range appears only here (D99). `null` with `by_sign_of_point_value_missing` when it cannot be given; always so when the tolerance of the indicator is missing |
| `by_sign_of_point_value_missing` | `Missing` | Present exactly when `by_sign_of_point_value` is `null` (C3.1) |

The model checks that the count by range holds no more cells than the count by sign holds with a value on both sides, since every cell is in the second count (D99). There is no total and no sum of the two counts (case `pair-count-with-a-total`). The counts follow D87's key (pair, scenario, indicator), so for `soil_carbon_trend` they hold the cells of both carbon models (OPEN, K10).

### `PairState`: the state of a pair (D85, D86, D88, D91, D97)

PROPOSED. One state per pair of rotations, across the scenarios (D74: "in every admitted scenario").

| Field | Type | Rule |
|---|---|---|
| `pair` | two texts | Two different `rotation_id` values, listed in `rotations`. A pair has one state, in either order |
| `value` | one of the state names, or `null` | The names of D88, with the name D97 adds: `Identical`, `Not separated: uncertainty missing`, `Not separated: within uncertainty` (D97), `Not robust across scenarios`, `Robust preference`. Each name says why (D88). `null` when the pair is not evaluated: no paired difference holds a value, and the pair has no state (D85). "Not evaluated", which D88 lists first, is that absence, not a value (D151 of issue #77, which resolves K1) |
| `missing` | `Missing` | Present exactly when `value` is `null` (C3.1). A pair whose `coverage` compares no cell has no state (D85) |
| `reason` | one of the reasons of D86, or absent | D86: "A state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74). The names are those of D88." So `Identical` goes with `identical rows`, `Not separated: uncertainty missing` with `a difference without its range`, and `Not robust across scenarios` with `not robust across the admitted scenarios`. A robust preference and a pair not evaluated carry none |
| `reason_missing` | `Missing` | In place of `reason`, never with it, for a state that is not a robust preference when no reason is given (C3.1). D86 writes no reason for `Not separated: within uncertainty`, so that state carries this part (OPEN, K3) |
| `preferred_rotation_id` | text or absent | PROPOSED: the rotation a `Robust preference` prefers, one of the pair; absent for every other state (OPEN 10) |
| `coverage` | `cells_compared`, `cells_of_the_pair`: integers, 0 or more | "k of N" (D91): the cells of the pair with a value on both sides, over which dominance is judged (D59), out of all the cells of the pair. `cells_compared` not more than `cells_of_the_pair`. No minimum coverage is set (D91) |

Which state a pair takes (D74, D92, D93, D98) is the producer's duty, tested in `decision/`. The model checks only what the table above says.

### `State` (D7)

| Field | Type | Rule |
|---|---|---|
| `value` | text or `null` | The state of the document. The state names of D88 and D97 are those of a pair (`PairState`); how the document's one state relates to the states of its pairs is OPEN (item 5), so any non-blank text is accepted for now; the example keeps the producer's `OPEN: ...` text |
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

D40 point 1. The example uses the rotation identifiers `example-rotation-1` (that of the rotation definition example) and `example-rotation-2` in place of `current` and `alternative-1`, and a count names its rotation in `rotation_id` (the key in `contracts/results/`) in place of `rotation`. The case and field identifiers are the producer's (`example-case`, `example-field-1`), which are also those of the rotation definition example and the web example case. The old key is the rejected case `count-with-producer-key-rotation`.

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

D1 says a row with a missing value is "reported as not evaluated, with its reason", and D60 of #77 says an indicator with no declared limit appears with every row "not evaluated". Issue #96 has no place for those rows. A count carries `not_evaluated`, each item naming its row and its reason. The example uses it for the missing soil-loss year. When the limit is missing, `years_within_limits` is `null` and no row is evaluated (D60). (Before D95 the example also counted `water_deficit_exposure`, reported missing `NOT_AVAILABLE` for both rotations; that indicator is per rotation in the results table example, so by D95 it has no count of years, and those counts left the example. Its missing limit stays in `limits`.)

### 5. A difference names its cell

D2 (written after #96, merged in #138) computes a difference only between the two rows of one cell, never across cells. The difference of issue #96 has no agricultural year: one soil-loss difference for the whole pair, which would be a summary across years. The landed difference names its cell (`scenario_id`, `time_basis`, `ag_year`, `carbon_model`, `computation`), as `PairedDifference` of `decision/functions.py` does. Whether the document also carries a summary over agricultural years, and by which method, is the paired-difference method of issue #96, OPEN 2. The shape of the issue is the rejected case `difference-across-years`.

### 6. The state names the indicators not resolved

D7: "the state is 'not resolved' and names the indicators that are not resolved". `state` carries `indicators_not_resolved`, as `PairState` of `decision/functions.py` does. The state may also be `null` with its `missing` part (C3.1), for a state the decision layer cannot give; the issue's shape, a text `value` with `reasons`, stays valid.

**Unchanged:** `contract`, `example_data`, `case_id`, `field_id`, `pair`, `difference`, `method`, `value` and `reasons` of the state, `years_evaluated`, `years_within_limits`, `measure_first` with `rank`, `what` and `why`.

The fields below were added after issue #96 by decisions of the lead developer, not as differences from the producer's example. The test adds them to the producer's example, empty, after applying the six differences.

## Fields added by D85 to D99

All PROPOSED, for the interface developer to accept as producer and as consumer (follow-ups of D85 to D91, D94 to D96 and D97 to D99 on issue #77). Each restates its decision; none adds a rule.

| Field | Decision | What it carries |
|---|---|---|
| `pair_states[].value` (`PairState`) | D88, D97 | One of the five state names: the four of D88 after "Not evaluated", and "Not separated: within uncertainty" of D97 |
| `pair_states[].value` `null` with `missing` | D85, D151 | A pair in which no paired difference holds a value is "not evaluated", with no state (D151 resolves K1) |
| `pair_states[].reason`, `reason_missing` | D86 | The reason of every state that is not a robust preference, named as D88 names the state; missable with its reason (K3), which softens D86 (OPEN 13) |
| `pair_states[].preferred_rotation_id` | D74 ("robust preference"), PROPOSED here | Which rotation a robust preference prefers; an added rule that no decision asks for (OPEN 10) |
| `pair_states[].coverage` | D91, with D59 | "k of N": cells compared, out of the cells of the pair |
| `pair_cell_counts[]` (`PairCellCount`) | D87, D99 | Per pair, scenario and indicator: `by_difference_range` (strict improvement, deterioration, not separated; D93, D98) and `by_sign_of_point_value` (better, worse, equal, missing side), shown apart and never added (K8, K9, K10) |
| `equal_tolerances[]` (`EqualToleranceItem`) | D87 | The tolerance of "equal" set by the designer of the case, missable with its reason |
| `counts_by_year[].carbon_model`, `computation` | D94 | Part of the key of a count; nothing is counted across scenarios or carbon models (K11) |
| `counts_by_year[]` over `ag_year` rows only | D95 | A row not evaluated is an `ag_year` row; `soil_carbon_trend` has no count (K11) |
| `range_across_scenarios[]` (`RangeAcrossScenarios`) | D96 | Minimum and maximum of the years within the limit across scenarios, and the scenario of the minimum; nothing else; missable with its reason |
| The range of `paired_differences[].difference` | D92 | Worst-case interval arithmetic, same `kind`, else missing (the example now carries one) |

D90 (a value equal to the limit counts as within) and D89 (the user's limit and the verified T live apart) change no field: they are restated under `LimitItem`. D93 and D98 change no field: they say how a cell with a range is classed, which the producer computes; D99 makes that class a count.

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
| `counted-indicator-without-limit-item` | Soil loss is counted and its item in `limits` is removed (C3.1, D60) |
| `count-names-rotation-not-listed` | A count names a rotation not in `rotations` |
| `count-names-scenario-not-listed` | The counts name a scenario not in `scenarios` |
| `count-with-producer-key-rotation` | A count carries the key `rotation` of issue #96 (difference 1) |
| `count-without-scenario` | A count has no `scenario_id` |
| `count-without-not-evaluated` | A count has no `not_evaluated` |
| `within-greater-than-evaluated` | `years_within_limits` is greater than `years_evaluated` |
| `negative-count` | `years_evaluated` is negative |
| `count-written-as-text` | `years_evaluated` written as text |
| `within-null-with-a-declared-limit` | `years_within_limits` is null although the limit is declared |
| `within-counted-without-a-limit` | The soil-loss limit is not declared and a count still gives `years_within_limits` (D60) |
| `evaluated-without-a-limit` | The soil-loss limit is not declared, `years_within_limits` is null and `years_evaluated` is not zero (D60) |
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
| `difference-without-range-or-reason` | A difference with a number loses its `range` and has no `range_missing` (C2.2) |
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
| `count-of-water-per-rotation` | Counts of `water_deficit_exposure` whose rows not evaluated have the time basis `rotation` (D95) |
| `count-of-soil-carbon-trend` | A count of `soil_carbon_trend`, naming its carbon model and computation (D95, C1.5) |
| `count-names-carbon-model-on-soil-loss` | A soil-loss count names a carbon model (D94 under the cell rules) |
| `range-minimum-greater-than-maximum` | A range across scenarios whose minimum is greater than its maximum (D96) |
| `range-without-minimum` | A range across scenarios loses its minimum and keeps its maximum and scenario (D96) |
| `range-without-value-or-reason` | A range across scenarios with no minimum, maximum or scenario, and no `missing` part (C3.1) |
| `range-with-value-and-reason` | A range across scenarios holds a range and a `missing` part (C3.1) |
| `range-scenario-of-minimum-not-listed` | The scenario of the minimum is not in `scenarios` |
| `range-minimum-not-that-of-its-scenario` | The scenario named as that of the minimum counts more years within the limit than the minimum (D96) |
| `range-of-an-uncounted-indicator` | A range across scenarios of an indicator that has no count (D96) |
| `range-names-rotation-not-listed` | A range across scenarios names a rotation not in `rotations` |
| `range-repeated` | Two ranges of one rotation and indicator |
| `range-with-a-mean` | A range across scenarios carries a mean (D96: no mean) |
| `range-with-a-share-of-scenarios` | A range across scenarios carries a share of scenarios (D96: no share or percentage) |
| `tolerance-not-declared` | A tolerance of "equal" carries the label `OBSERVED` (D87: set by the designer of the case) |
| `tolerance-in-another-unit` | The soil-loss tolerance is in the monthly unit (C1.1) |
| `two-tolerances-of-one-indicator` | Two tolerances of one indicator |
| `pair-count-without-tolerance-item` | A count of a pair's cells of soil loss and no tolerance item of soil loss (D87, C3.1) |
| `pair-count-by-sign-without-a-tolerance` | The soil-carbon count by the sign of the point value is given although its tolerance is missing (D87) |
| `pair-count-by-sign-without-value-or-reason` | The count by the sign of the point value is null with no reason (C3.1) |
| `pair-count-by-sign-with-value-and-reason` | The count by the sign of the point value is given with a reason (C3.1) |
| `pair-count-without-range-count` | A count of a pair's cells has no `by_difference_range` (D99) |
| `pair-count-range-count-negative` | A count by range is negative |
| `pair-count-more-ranges-than-values` | The count by range holds more cells than the count by sign holds with a value (D99) |
| `pair-count-with-a-total` | A count of a pair's cells carries a total (D99: never added) |
| `pair-count-with-a-p-value` | A count of a pair's cells carries a p-value (D87) |
| `pair-count-of-one-rotation` | A count of a pair's cells holds one rotation twice |
| `pair-count-names-rotation-not-listed` | A count of a pair's cells names a rotation not in `rotations` |
| `pair-count-without-scenario` | A count of a pair's cells has no `scenario_id` (D87) |
| `pair-count-repeated` | Two counts of one pair, scenario and indicator |
| `pair-state-unknown-name` | A state of a pair named `not resolved`, which is not a name of D88 or D97 |
| `pair-state-not-evaluated-as-a-name` | A state of a pair named `Not evaluated` (D85 and D151: no state) |
| `pair-state-without-value-or-reason` | A state of a pair is null with no `missing` part (D85, C3.1) |
| `pair-state-with-value-and-missing` | A state of a pair holds a name and a `missing` part (C3.1) |
| `pair-state-with-nothing-compared` | A state of a pair holds a name while its coverage compares no cell (D85) |
| `not-evaluated-pair-with-a-reason` | A pair not evaluated carries a reason of D86 (D85: no state) |
| `pair-state-without-its-reason` | `Not separated: uncertainty missing` with neither `reason` nor `reason_missing` (D86) |
| `pair-state-with-reason-of-another-state` | `Not separated: uncertainty missing` with the reason `identical rows` (D86) |
| `pair-state-with-reason-and-reason-missing` | A state carries `reason` and `reason_missing` (C3.1) |
| `within-uncertainty-with-a-reason-of-d86` | `Not separated: within uncertainty` with the reason `a difference without its range` (D86, D97) |
| `robust-preference-with-a-reason` | A robust preference carries a reason (D86) |
| `robust-preference-without-preferred-rotation` | A robust preference names no preferred rotation |
| `preferred-rotation-outside-the-pair` | A robust preference prefers a rotation outside its pair |
| `preferred-rotation-without-robust-preference` | A state that is not a robust preference names a preferred rotation |
| `coverage-compared-greater-than-cells` | `cells_compared` is greater than `cells_of_the_pair` (D91) |
| `coverage-left-out` | A state of a pair has no `coverage` (D91) |
| `coverage-as-a-share` | The coverage is a share, not "k of N" (D91) |
| `pair-state-names-rotation-not-listed` | A state of a pair names a rotation not in `rotations` |
| `pair-state-of-one-rotation` | A state of a pair holds one rotation twice |
| `pair-state-repeated-swapped` | Two states of one pair, the second with the pair swapped |

### Accepted

| Case | The variant |
|---|---|
| `declared-water-limit` | A limit of `water_deficit_exposure` with a number; that indicator is per rotation in the example, so it has no count (D95) |
| `tied-ranks` | Two inputs share rank 1 and the next is rank 3 (D4: ties share a rank) |
| `resolved-without-priority` | No indicator not resolved, and an empty `measure_first` |
| `state-not-given` | The state is null with its reason |
| `no-counts-no-differences` | No limit, count, range, difference, tolerance, count of a pair's cells or state of a pair |
| `swapped-pair` | The same cell with the pair swapped, and the sign of the difference flipped |
| `example-data-false` | `example_data` is false |
| `soil-loss-limit-not-declared` | The soil-loss limit is missing: no row is evaluated, the year with a value is listed not evaluated, and the ranges across scenarios are missing with their reason (D60, D96) |
| `range-over-two-scenarios` | A second scenario counts one year within the limit: the range is 0 to 1, its minimum in scenario one (D96) |
| `no-range-across-scenarios` | No range across scenarios |
| `pair-count-not-given-by-sign` | The soil-loss count by the sign of the point value is missing with its reason |
| `not-evaluated-pair` | No cell compared, and the pair has no state, with its reason (D85) |
| `identical-with-its-reason` | `Identical`, with `identical rows` (D86, D88) |
| `not-robust-with-its-reason` | `Not robust across scenarios`, with `not robust across the admitted scenarios` (D86, D88) |
| `within-uncertainty-with-reason-missing` | `Not separated: within uncertainty`, with `reason_missing` (D97; K3) |
| `uncertainty-missing-with-reason-missing` | `Not separated: uncertainty missing`, with `reason_missing` in place of its reason (C3.1) |
| `robust-preference` | `Robust preference` of `example-rotation-2`, with no reason |
| `no-pair-state` | No state of a pair |

The model does not check what it cannot see: that `rotations` are the identifiers of the results table, that counts, ranges, differences, counts of a pair's cells, coverages and states equal what the decision functions compute (including the arithmetic of D92 and the classes of D93 and D98), that a priority list is given only when the state is not resolved (D4), or that the state agrees with `indicators_not_resolved`. Those are duties of the producer, tested in `decision/`. For the example alone, `test_examples.py` checks that its identifiers (through the matching table), its rows not evaluated, its differences and their ranges (D92) agree with the results table example, that its counts of the pair's cells and its coverage agree with its differences, and that its ranges across scenarios are those of its counts.

## OPEN

Each item is a question a person has to answer. Until then the model keeps the shape above.

1. **The state names.** Decided for the state of a pair by D88 (science decision of the lead developer; a science reviewer may still review the wording), with the name D97 adds: `PairState.value` accepts only those. The document's one `state.value` stays any non-blank text until item 5 is settled, and `decision/functions.py` still uses the placeholder constant `NOT_RESOLVED`. D151 decides that "Not evaluated" is the absence of a state, not a state name (K1).
2. **The paired-difference method and its citation.** Issue #96, OPEN 2; D2. The range of a difference is decided by D92 (interval arithmetic, worst case; a science reviewer may still review it). Still open: the citation of the method, and whether the document also carries a difference summarised over agricultural years, and by which method (difference 5). For the science reviewers.
3. **Admissibility and an official tolerance.** Issue #96, OPEN 3. D89 decides that they live apart: admissibility is decided only by D74 (mean erosion at or below a verified T, with its source), and the count of years within the user's limit is descriptive. The document has no field for admissibility or for T yet, and the source of T is OPEN in #77 (D10). If they enter, PROPOSED: they travel as their own items with their own source and provenance, never as an edit of the user's declared limit. For the lead developer and the interface developer.
4. **Equality at the limit.** Decided by D90: a value equal to the limit counts as within. The counts carry the result, not the rule; whether the document should also say which setting produced them is for the producer.
5. **The document's state, the pair states and the scenarios.** D85 to D88 give a state to each pair, across the scenarios (`pair_states`). The document still carries one `state` (D7, with `indicators_not_resolved`). Whether that one state stays, and how it relates to the states of the pairs, goes with the tipping point (D3) and the thin matrix of Block 2. For the interface developer as producer and consumer, and the lead developer.
6. **Which reason a row carries when it holds a value and its indicator has no declared limit.** D60 says it is "not evaluated", with its reason; no code of C3.2 is decided for that case (`NOT_DECLARED` is a candidate, used by the case `soil-loss-limit-not-declared`). For the lead developer.
7. **Counts of indicators that are not annual.** Settled by D95: years are counted only over `ag_year` rows, and an indicator on another time basis has no count. What remains is K11.
8. **The identifier of a second example rotation.** The examples chain on `example-case`, `example-field-1` and `example-rotation-1`; a decision needs two rotations, and `example-rotation-2` is introduced here without a rotation definition example of its own. The results table example still uses `PLACEHOLDER_…` identifiers. Whether those examples move to the chained identifiers, and which one defines the second rotation, is for the lead developer as owner of `contracts/`.
9. **Which scenarios are admitted.** D96 summarises "across the admitted scenarios", and D74 decides admissibility; the document names no admitted scenario, so the model cannot check that a range is taken over them, and a reader cannot see which they are. Whether a field lists them, and where (D96 allows "only the range ... naming the scenario of the minimum"), is for the lead developer and the interface developer.
10. **Which rotation a robust preference prefers.** `preferred_rotation_id` is PROPOSED here: D74 speaks of a "robust preference" and D93 classes a cell by the difference second minus first, but no decision names the field. **The rule that a robust preference must name its preferred rotation, one of its pair, and that no other state may name one, is a rule added by this contract: no decision asks for it.** It needs the interface developer's explicit acceptance, as producer and consumer, before it takes effect. The alternative is that the order of the pair says it (the second rotation preferred), with no field.
11. **Several scenarios at the minimum.** D96 names "the scenario of the minimum", one scenario. When several scenarios share the minimum, which is named is not decided; the field holds one. For the lead developer.
12. **The reason code of `reason_missing`.** No code of C3.2 says "no decision writes a reason for this state" (K3); the cases use `NOT_AVAILABLE` as a placeholder. For the lead developer.
13. **`reason_missing` softens D86.** D86: "A state that is not a robust preference carries its reason". This contract accepts, for every such state, `reason_missing` in place of `reason` (case `uncertainty-missing-with-reason-missing`), following the brief's "Keep every value missable with its reason". That lets a state that D86 gives a reason to travel without one, which D86 as written does not allow. Whether `reason_missing` stays for every state that is not a robust preference, only for `Not separated: within uncertainty` (K3), or not at all, is for the lead developer.

### Clashes between decisions

Each item quotes two or more decisions of #77 that do not fit, or may not fit, together as written. Decisions D151 to D156 of #77 ([comment](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819), 15 November 2026) resolve K1, K2, K4 to K7 and K12, as each item says below; what is left of K3, and K8 to K11, are not resolved. K1 to K7 are numbered as in pull request #190 (which lists them for `docs/VALIDATION.md`); only those that touch a field of this contract are repeated in full. K8 to K12 continue that numbering and are new here. For the lead developer.

- **K1 (D85 and D88): is "Not evaluated" a state?** RESOLVED by D151: it is the absence of a state, and "Not evaluated" is the label shown for that absence. This contract already carries it that way and does not change. The item as it was written: D85: "The pair is "not evaluated", with no state, consistent with D6 (a missing value does not enter the state) and with the wording of D1." D88: ""Not evaluated" (D85) · "Identical" · "Not separated: uncertainty missing" · "Not robust across scenarios" · "Robust preference" (D74)." D86 lists no reason for it. **In this contract**, as the brief of issue #193 asks ("a "not evaluated" pair with no state (D85)"): `value` is `null` with its `missing` part, and the text `Not evaluated` is rejected as a value (case `pair-state-not-evaluated-as-a-name`). If the lead developer decides that it is a state, it joins the state names and the case turns accepted.
- **K2 (D92 with D85, D86 and D88): which state comes first when the conditions of two hold?** RESOLVED by D152: a pair takes one state, the first that applies, read in one scenario in the order "Robust preference"; "Identical"; "Not separated: uncertainty missing"; "Not separated: within uncertainty"; otherwise "Not robust across scenarios". Over a set of scenarios or phases the state is the one D103 and D117 give. The model does not check that order: it still accepts any state name, and applying the order is the producer's. The item as it was written: D85: "`identical_rows` is true only when at least one difference holds a value and every difference is equal to zero". D92: "if either range is missing or the kinds differ, the range of the difference is missing with its reason, and D86 / D88 give that pair the state "Not separated: uncertainty missing"". Example from #190: every difference equal to zero and every range missing. **In this contract** a pair carries one state; which one is the producer's, and the model accepts any name. The example's pair is a case of K12, below.
- **K3 (D93 and D97 with D86): the reason of "Not separated: within uncertainty".** D97 settles the name that K3 of #190 asked for: ""Not separated: within uncertainty" when the range exists and touches or crosses zero (D93). This adds a name to D88, not a rule". Still open: D86 writes no reason for that state ("A state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74). The names are those of D88"), and D93 still reads "a pair whose only cells are not separated is "Not separated: uncertainty missing" or not robust (D86, D88)". **In this contract** that state carries `reason_missing` and none of D86's three reasons (case `within-uncertainty-with-a-reason-of-d86`).
- **K4, K5 and K6 (D93 with D74, D95 and D94)** are about the separation rule: whether one strictly improving cell is needed in the whole pair or in each indicator and scenario (K4), whether an indicator that is not per agricultural year enters it cell by cell (K5), and whether it is applied per carbon model (K6). They change which state the producer gives, not a field of this contract. See pull request #190. RESOLVED by D153 (one strictly improving cell in each admitted scenario, in any indicator), D154 (such an indicator enters the separation rule cell by cell; D95 applies to the counts of D1 only) and D155 (the rule is applied per carbon model). No field of this contract changes.
- **K7 (D59 and D91 with D93): which cells the coverage compares.** RESOLVED by D156: dominance is read by the two values, and the coverage counts the cells with a value on both sides, with or without a range, as this contract already does. The item as it was written: D59: "Dominance is judged only on the cells that have a value on both sides." D91: "The output carries the coverage: cells compared, out of the cells of the pair ("k of N")." D93 classes a cell by the range of its difference, so a cell with a value on both sides and no range is compared by D59 and cannot be classed by D93. **In this contract** `cells_compared` counts the cells with a value on both sides (D59).
- **K8 (D93 with D98 and D99): a range that touches zero on the side that is not worse.** D93: "a range that touches or crosses zero is "not separated" for that cell." D98: "A cell is non-deteriorating only when the whole range of its difference lies on the side of zero that is not worse, zero included (consistent with D90). A cell whose range crosses zero is not separated and blocks a robust preference." D99: "Where the difference has a range: strict improvement, deterioration and not separated, by D93 and D98." Such a cell is "not separated" by D93 and non-deteriorating by D98, which does not block a robust preference, while a cell that crosses zero does. Question: in the count of D99, is such a cell "not separated" (so that the class mixes cells that block and cells that do not), or another class? **In this contract** the count has the three classes of D99.
- **K9 (D87 and D99): "equal" by a tolerance or by the sign.** D87: ""Equal" uses the tolerance set by the designer of the case". D99: "And by the sign of the point value, labelled as such." Question: does the second count of D99 keep the tolerance of D87 for "equal", or is it the sign alone? Neither decision says whether a difference exactly at the tolerance is equal. **In this contract** the count by the sign carries D87's tolerance (`equal_tolerances`), and is missing when the tolerance is.
- **K10 (D87 and D94): the cells of the two carbon models in one count.** D87: "For each pair, scenario and indicator, the count of paired cells where the second rotation is better, worse or equal, and of cells with a missing side". D94: "One count per rotation, scenario, indicator, carbon model and computation. Nothing is counted across scenarios or across carbon models." D94 answers how the counts of D1 are keyed, but its second sentence reads as general. Question: is a count of D87 for `soil_carbon_trend` also split by carbon model and computation? **In this contract** it follows D87's key, so it holds the cells of AMG and RothC together.
- **K11 (D94 and D95): the carbon model in a count of years.** D94 adds `carbon_model` and `computation` to the key of a count of D1. D95: "Years are counted only over rows whose `time_basis` is `ag_year`. An indicator on another time basis has no count of years". The only indicator that names a carbon model, the soil carbon trend, is one value per rotation (C1.5), so under D95 it has no count, and the two fields of D94 can never be filled. Question: do the fields stay (for a carbon indicator per agricultural year in future), or does one decision give way? **In this contract** both fields are present (D94) and a count of `soil_carbon_trend` is rejected (D95; case `count-of-soil-carbon-trend`).
- **K12 (D92 and D97): a pair with one cell whose range crosses zero and one cell with no range.** RESOLVED by D152: in its order "Not separated: uncertainty missing" comes before "Not separated: within uncertainty", so such a pair takes the first, with the reason `a difference without its range`, unless every difference is zero ("Identical" comes before both). The model still accepts either name. The item as it was written: D92: "if either range is missing or the kinds differ, the range of the difference is missing with its reason, and D86 / D88 give that pair the state "Not separated: uncertainty missing"". D97: ""Not separated: uncertainty missing" when the range of a difference is missing (D92). "Not separated: within uncertainty" when the range exists and touches or crosses zero (D93)." D97 answers the question "How is a pair named when every difference has a range but the ranges touch or cross zero?", which does not cover a pair with cells of both kinds, while its two names, read cell by cell, each fit one of the cells. Question: which state, and which reason, does such a pair take? The example's pair is such a pair: its soil-loss difference of 2001 has the range `[-14.0, 6.0]`, which crosses zero, and its soil-carbon difference (AMG) has no range. **In this contract** the example writes `Not separated: uncertainty missing` with the reason `a difference without its range`, as placeholder data that takes no position on K12; the model accepts either name for it.

## Notes for the producer

Read on `main` while landing this contract and its D85 to D99 fields; nothing here changes `decision/`, whose functions the interface developer adapts (follow-ups of D85 to D99 for sub-lane L2b). `decision/` does not import this contract, so no test of `decision/` changes.

- `limit_counts` of `decision/functions.py` counts per rotation and indicator over every scenario of the table. This contract counts per rotation, scenario, indicator, carbon model and computation (D40 point 2, D94).
- `limit_counts` counts a row on the time basis `rotation` as one year evaluated. This contract counts only `ag_year` rows, and has no count for an indicator on another time basis (D95).
- For an indicator without a declared limit, `limit_counts` reports `evaluated` as the number of rows that hold a value. D60 of #77, decided after, says every row is "not evaluated". This contract follows D60: `years_evaluated` is 0 and `years_within_limits` is `null`.
- `pair_state` returns `NOT_RESOLVED` with `identical_rows=True` when every difference is missing. This contract gives that pair no state, with its reason (D85), and names the states as D88 and D97 do, each not robust one with its reason (D86).
- `paired_difference` gives no range. This contract carries the range of D92, and `pair_cell_counts` counts by that range and by the sign of the point value (D99), with the tolerance of "equal" (D87) and the coverage (D91).
- Nothing in `decision/` gives the range across scenarios of D96 yet.
- `pair_state` returns a state per pair of rotations, as `pair_states` now does; this contract still also has one `state` per document (OPEN item 5).
