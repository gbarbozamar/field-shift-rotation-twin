# Plant answer contract

**The examples are example data.** Both files under `examples/` say `"example_data": true` and their names start with `PLACEHOLDER_`. The site (latitude 1.0, longitude 2.0) is not a field. The economic facts are the example of `contracts/economic_facts/`. The soil-loss levels, the soil-loss limit (6.0 t ha-1 yr-1), the rain-stress factor (1.2), the soybean price range (200 to 600 USD t-1) and the period (agricultural years 2015 to 2024, start month 7) are example data, chosen to show the shapes and taken from no source and no engine. No engine, test threshold or screen may take them as values.

Status: **PROPOSED** (blueprint section 3.7), unit `l2/plant-answer-contract` (brief S-018a). Nothing here is in force until people approve the pull request.

This folder holds the Pydantic models of the request and of the answer of "What should I plant?" (one field, three to five rotations), one example of each, and the acceptance test. The route (S-018, `api/plant.py`) and the screen (S-019, `web/`) are built against it.

| Contract | Producer → consumer | Model | Example |
|---|---|---|---|
| Plant request | Interface (what the user declares) → the route | `plant_answer.PlantRequest` | `examples/PLACEHOLDER_plant_request.json` |
| Plant answer | The route → the interface | `plant_answer.PlantAnswer` | `examples/PLACEHOLDER_plant_answer.json` |

Acceptance test, from the repository root:

```bash
uv run pytest contracts/plant_answer/
```

Models and pure validation only: no network call, no parameter value, no computation. The contract imports contracts only (`contracts.inputs.common`, `contracts.economic_facts`, `contracts.rotation_definition`, `contracts.results.models`); a test checks that it imports neither `kinds_of_year` nor `api` (#387). The tests that read `kinds_of_year/` or `api/rain_stress.py` are skipped (`pytest.importorskip`) while those modules are not on `main`. The answer is the JSON form of the dataclasses of `economics/` (`decide.py`, `limit.py`, `margin.py`, `tipping.py`), `kinds_of_year/` (`aggregate.py`, `classify.py`) and `api/rain_stress.py`, field for field where it can be; it does not import them. The literals it needs (`Strictness`, `Answer`, `OptionState`, `Verdict`, `Direction`, `MARGINS_OF`, the unit `dimensionless`, the label `stress test`) are defined here, and the test checks with `typing.get_args` that they equal the originals, and that the field names of each mirrored model equal those of its dataclass.

## How the example answer was made

A scratch script (not committed) ran the real pure functions on the example request: `classify_agricultural_years` and `count_kinds` on the committed ONI record `kinds_of_year/records/oni_v6.json` for agricultural years 2015 to 2024 with start month 7; `mean_by_kind` on an example soil-loss series per agricultural year; `assess_limit` with the example limit and the kinds in the record; `compute_rotation_margin` on the example facts; `find_tipping_price` (which calls `choose_rotation`) with the example price range, strictness `on_average` and `margin_of` `average`; `rain_stress` on the example factor. Its output was pasted unchanged.

- **From the script (computed by the real functions, on example inputs):** every margin (for example 312.0, 222.0 and 193.8 USD ha-1 yr-1 on average), every soil-loss mean, `n_years` and `ag_years`, every limit check, the answer, the chosen rotation, the option states, the limit cost (90.0 USD ha-1 yr-1 against `example-rotation-soybean`), the tipping price (down: 375.26... USD t-1, -6.18... percent, the answer becomes not resolved; up: missing `NOT_APPLICABLE`), the rain-stress echo text, the kind of each year and the counts (4 `el_nino`, 2 `neutral`, 4 `la_nina`).
- **Example data (typed in the script, no source):** the soil loss per kind of year of each rotation (14.0, 11.0, 8.0; 6.5, 5.0, 4.0; 4.0, 3.0, 2.5 t ha-1 yr-1), the one soil-loss year left missing (2022 of `example-rotation-soybean-cover-pasture`, reason `MISSING_INPUT`), the limit, the factor, the price range, the period, which crops each rotation sows in each agricultural year, and the two source rows.
- The kinds of year come from the transcribed ONI record (reference and signature state in `kinds_of_year/README.md`; `checked_by` `UNSIGNED_AI_PRECHECK`).

The example answer shows one chosen rotation (`example-rotation-soybean-cover`), one that does not meet the limit (`example-rotation-soybean`), one not resolved because a soil-loss year is missing, missing values with their reasons, and a tipping price.

**The labels of D249 in the example (#387).** Added by hand after the script, no number changed: every present margin, soil-loss mean, limit cost, tipping price and tipping distance is `DERIVED`, with `range_missing` (`distance_range_missing` for the distance) `NOT_AVAILABLE` ("PLACEHOLDER: example data, no range is computed for this number"); every present margin carries the source "computed from the declared economic facts"; today's price carries the labels of the declared soybean price of the example request (`DECLARED`, `range_missing` `NOT_DECLARED`); each option's `limit` is the declared soil-loss limit `Value` of the example request; the soybean price range is `DECLARED` in both examples. The example's soil-loss means carry no D148 label: they are example data, not values of the erosion engine. `scope` and `declared_limits` are the texts below.

## Field list

All PROPOSED. Every model rejects unknown members and does not coerce types. No member has a default: each is written, `null` where it is absent; except the labels of D249 (`provenance`, `range`, `range_missing`, a margin's `source`, a soil loss's `label`), which are left out where they do not apply, as in `Value` of `contracts/inputs/common.py`.

### `PlantRequest`

| Field | Type | Rule |
|---|---|---|
| `contract` | `"plant_request"` | |
| `example_data` | bool | |
| `site` | `SiteReference`: `case_id`, `field_id`, `latitude` (-90 to 90), `longitude` (-180 to 180) | Copied as a contract model from `api/rotations.py` |
| `rotations` | 3 to 5 `RotationDefinition` | Distinct `rotation_id`; each of the field of the site (PROPOSED); every crop a rotation sows is declared in `economic_facts` (PROPOSED); every rotation has the same `ag_year_start.month`, so the answer holds one kinds-of-year record (PROPOSED) |
| `economic_facts` | `EconomicFacts` | Its `case_id` and `field_id` are those of the site |
| `soil_loss_limit` | `Value` in `t ha-1 yr-1` | `DECLARED` when present, not negative; may be missing with its reason |
| `questions` | `Questions` | See below |

### `Questions` (in the request, and echoed in the answer as applied)

| Field | Type | Rule |
|---|---|---|
| `soybean_crop_ids` | list of text | Not empty, distinct; in the request each is a grain crop of the facts and is sown by at least one rotation (PROPOSED); the named crops do not carry different declared prices, as `find_tipping_price` refuses that, while a missing price is allowed and gives a tipping price missing `MISSING_INPUT` (PROPOSED) |
| `soybean_price_range` | `low`, `high`, `unit`, `provenance` | `unit` is `USD t-1`; `0 <= low < high`; `provenance` is `DECLARED` (D249) |
| `margin_of` | `"average"`, `"el_nino"`, `"neutral"`, `"la_nina"` | `MARGINS_OF` of `economics/tipping.py`: the kind-of-year question |
| `rain_stress_factor` | `Value` in `dimensionless`, or null | null: no stress test. `DECLARED` and above zero when present; may be missing with its reason |
| `strictness` | `"on_average"` or `"every_kind"` | |

### `PlantAnswer`

| Field | Type | Mirrors |
|---|---|---|
| `contract` | `"plant_answer"` | |
| `example_data` | bool | |
| `case_id`, `field_id` | text | The site of the request |
| `questions` | `Questions` | As applied |
| `answer` | `"chosen"`, `"none_meets"`, `"not_resolved"` | `Decision.answer` |
| `chosen` | rotation id or null | Set exactly when the answer is `chosen` |
| `reason`, `detail` | reason code and text, or null | Set exactly when nothing is chosen |
| `tied` | list of rotation ids | Empty unless the answer is `not_resolved` |
| `options` | 3 to 5 `PlantOption`, in request order | Distinct ids |
| `limit_cost` | `value`, `against`, `costs_nothing`, `reason`, `detail`, `unit` | `LimitCost` |
| `tipping_price` | `today`, `unit`, `price_range`, `up`, `down`, `reason`, `detail` | `TippingPrice` without `decision` (the answer is the decision) |
| `rain_stress` | applied form, missing form, or null | `RainStress` / `RainStressMissing`; null when no factor was asked |
| `erosivity` | `"mean_annual"` | Which erosivity the soil-loss run used (S-026 may add `"per_year"`) |
| `kinds_of_year` | `source`, `start_month`, `years`, `counts` | `KindOfYear` per year and `count_kinds` |
| `sources` | list | The shape of `SourceOut` of `api/rotations.py` |
| `scope` | text | D245 (R11): exactly "the most margin within the limit you declared; water and soil carbon are not part of this answer" (`ANSWER_SCOPE`). The screen shows it in place of "Plant this rotation" |
| `declared_limits` | list of texts | The limits of this answer, declared; includes "phase 1 only: only the first phase of each rotation enters this answer, a limit of this release (D250)" (`PHASE_ONE_ONLY`; D250, point 2: only phase 1 enters the answer, and the answer says so) |

`PlantOption`: `rotation_id`; `state` (`"chosen"`, `"meets"`, `"does_not_meet"`, `"not_resolved"`); `margin` (`average`, `el_nino`, `neutral`, `la_nina`, each `value`, `unit` `USD ha-1 yr-1`, `reason`, `detail`: `MarginResult`); `soil_loss` (the same four keys, each `value`, `unit` `t ha-1 yr-1`, `n_years`, `ag_years`, `reason`, `detail`, `sources`, `assumption`: `KindMean`; `average` is `MeansByKind.record`); `limit` (`limit`, `unit`, `on_average`, `every_kind`, `by_kind`, `kinds_not_met`, `kinds_not_resolved`, `kinds_not_in_record`: `LimitAssessment`, each check `verdict`, `reason`, `detail`: `LimitCheck`; `limit` is the declared `Value` in `t ha-1 yr-1`, missing with its reason when the request's is); `limit_check` (the check of the strictness used).

Tipping point (`up`, `down`): `direction`, `price`, `takes_over`, `answer_after`, `distance_percent`, `reason`, `detail`, `unit` (`TippingPoint`), plus the labels of D249 of the price and of the distance.

Rain stress, applied form: `factor`, `declared` (the declared `Value`, unchanged), `detail`, `label` (`"stress test"`), `applied`. Missing form: `missing`, `detail`, `label`.

Kinds of year: `source` (the record id, `oni_v6`), `start_month`, `years` (each `ag_year`, `kind`, `missing_reason`, `detail`, `season`, `season_year`), `counts` (`el_nino`, `neutral`, `la_nina`: every count, or every count null when a year has no kind).

A value-or-missing follows C3 of `contracts/CONVENTIONS.md`: a number with its unit, or null with a reason code; never both, and never a zero standing for missing. Whether a `detail` must come with the reason follows the dataclass mirrored (PROPOSED, fix round 2): a margin (`MarginResult`) and a kind of year (`KindOfYear`) may carry a reason without a detail, and carry no detail when present; `KindMean` sets no rule on its detail; a limit check, a limit cost and a tipping point carry the reason and the detail together, as their dataclasses do. The answer does not reuse `Value` for these items because the dataclasses it mirrors carry no provenance label or range (PROPOSED).

**The labels of every number (D249 of #77, #387).** Each number of the answer carries what C4.1 and C2.2 ask of every value: when present, its `provenance` and either its `range` (C2.1, the value inside it) or `range_missing` with its reason, never both; when missing, none of them. These fields are added to the mirrored dataclasses (`D249_LABELS`; the test of the mirror adds them):

- a margin (`MarginOut`): `provenance` `DERIVED`, and `source` exactly "computed from the declared economic facts" (`MARGIN_SOURCE`, C4.2);
- a soil-loss mean (`SoilLossOut`): `provenance` `DERIVED` (C4.6 and D243, `PROVENANCE_OF_SOIL_LOSS` of `contracts/results/models.py`), and `label`: every real value (`example_data` false) carries exactly the label of D148 (D250, point 3), "based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)" (`D148_SOIL_LOSS_LABEL`); a missing value carries none;
- the limit cost (`LimitCostOut`) and each tipping price (`TippingPointOut.price`): `provenance` `DERIVED`;
- each tipping distance (`TippingPointOut.distance_percent`): its own labels `distance_provenance` `DERIVED`, and `distance_range` or `distance_range_missing` (`D249_DISTANCE_LABELS`, because the tipping point's `provenance`, `range` and `range_missing` are those of its price);
- today's price (`TippingPriceOut.today`): the labels of the declared soybean price (checked against the request);
- the soil-loss limit of each option (`LimitAssessmentOut.limit`): no bare number; the declared `Value` of the request, unchanged, which carries them (`DECLARED`), as the rain-stress factor's `declared`; `check_answer_against_request` checks that it equals the request's `soil_loss_limit`, labels included;
- the soybean price range (`PriceRange.low` and `PriceRange.high`, in the request and in the answer): `provenance` `DECLARED`, one label for both numbers, as a declared value asks (C4.1);
- the rain-stress factor: no copy; `declared` is the declared `Value`, which carries them (`DECLARED`).

**Soil loss needs a source or the mark (PROPOSED).** A present soil-loss mean (`SoilLossOut`) with an empty `sources` list and `assumption` false is refused (C4.2). This is stricter than `KindMean`, which allows it, so the route must give every present soil-loss mean its sources or the assumption mark.

### Rules of the answer (model validators)

- An item holds a value or a reason, never both; a missing value carries its reason (the detail as its dataclass has it, above).
- `chosen` is set exactly when the answer is `chosen`; `reason` and `detail` exactly when it is not; `tied` only when it is `not_resolved`.
- Option ids are distinct; `chosen` and `tied` name options; the state `chosen` is on the chosen rotation and on no other.
- Every option is judged against one limit; its `limit_check` is the check of `questions.strictness`; a state other than `chosen` is the verdict of that check; the chosen rotation meets the limit.
- `limit_cost`: a value exactly with `against`, another option than the chosen one; a value or `costs_nothing` only when a rotation is chosen.
- `tipping_price.price_range` is the question's range; `takes_over` names an option.
- `rain_stress` is null exactly when no factor was asked, the missing form when the factor is missing (same `missing` part), and the applied form carrying the declared factor otherwise.
- The kind counts are the years of each kind, or all null when a year has no kind.
- As `choose_rotation` (PROPOSED, fix round 2): `none_meets` only when every option is in state `does_not_meet`; `tied`, when not empty, holds at least two distinct options, each in state `meets`.
- As `assess_limit` (PROPOSED, fix round 2): `kinds_not_met` is exactly the kinds in the record (not in `kinds_not_in_record`) whose `by_kind` check is `does_not_meet`, and `kinds_not_resolved` those whose check is `not_resolved`, so the three lists are disjoint; the check of a kind not in the record is `not_resolved`; with `limit` missing (its `value` null) no check is resolved; `every_kind` is `does_not_meet` when a kind in the record does not meet, else `not_resolved` when one is not resolved or no kind is in the record, else `meets`.
- As `find_tipping_price` (PROPOSED, fix round 2): a shared `reason` (with its `detail`) is on both points, which have no price; with no shared reason `today` is present and inside `price_range`; a present tipping price is inside `price_range`; `up.price` is at or above `today` and `down.price` at or below it; `distance_percent` is not negative up and not positive down (0 allowed).
- `sources`: the text fields are plain text, as in `SourceOut` of `api/rotations.py`, and `retrieved_at` is written in UTC as `YYYY-MM-DDTHH:MM:SSZ`, as that model writes it (PROPOSED, fix round 2).
- D249, D245, D250 and D148 (#387): each number carries its labels (above); `scope` is `ANSWER_SCOPE`; `declared_limits` includes `PHASE_ONE_ONLY`; with `example_data` false, every present soil-loss mean carries the label of D148. These checks run after the others.

`check_answer_against_request(request, answer)` (PROPOSED) holds the checks that need both: the same field, the same questions, one option per rotation in request order, and every option judged against the declared limit (D249: the declared `Value` with its labels); and (PROPOSED, fix round 2) `example_data` true when the request's is, `tipping_price.today` equal to the declared price of the soybean crops (null when one of them has no price, as `find_tipping_price` reads it), and `kinds_of_year.start_month` equal to the rotations' `ag_year_start.month`; and (D249) a present `tipping_price.today` with the `provenance`, `range` and `range_missing` of the declared soybean price. It raises `ValueError`.

## PROPOSED cases

The identifiers are those of `test_examples.py`; each case is a change to an example, made in memory. A rejected case must fail for the stated reason, as Python data and as JSON text.

### Rejected: the request

| Case | The variant |
|---|---|
| `request-with-two-rotations` | Two rotations |
| `request-with-six-rotations` | Six rotations |
| `request-with-a-duplicate-rotation-id` | Two rotations share one id |
| `request-site-and-facts-of-different-fields` | The facts are of another field than the site |
| `request-rotation-of-another-field` | A rotation is of another field than the site |
| `request-price-range-low-not-below-high` | `low` equals `high` |
| `request-price-range-in-another-unit` | The range is in `USD kg-1` |
| `request-margin-of-not-in-margins-of` | `margin_of` is `"dry"` |
| `request-strictness-not-in-the-list` | `strictness` is `"most_years"` |
| `request-soybean-crop-ids-empty` | No soybean crop is named |
| `request-soybean-crop-ids-repeated` | A soybean crop is named twice |
| `request-soybean-crop-not-a-grain-crop` | The soybean crop is the pasture |
| `request-soybean-crop-sown-by-no-rotation` | The soybean crop is a second grain crop of the facts that no rotation sows |
| `request-rotation-sows-an-undeclared-crop` | A rotation sows a crop that the economic facts do not declare |
| `request-soil-loss-limit-in-another-unit` | The limit is in `t ha-1` |
| `request-soil-loss-limit-not-declared` | The limit is labelled `OBSERVED` |
| `request-rain-stress-factor-zero` | The factor is zero |
| `request-rain-stress-factor-with-a-unit` | The factor is in `mm` |
| `request-soybean-crops-with-different-prices` | Two named soybean crops carry the prices 400 and 410 (example numbers) |
| `request-rotations-with-different-start-months` | One rotation starts its agricultural year in month 8, the others in month 7 |

### Rejected: the answer

| Case | The variant |
|---|---|
| `answer-missing-margin-written-as-zero-with-a-reason` | A margin is 0 with a reason and a detail |
| `answer-value-with-a-reason` | A soil-loss mean has a value and a reason |
| `answer-missing-value-without-a-reason` | A margin is null without a reason |
| `answer-chosen-without-a-rotation` | The answer is `chosen` and `chosen` is null |
| `answer-reason-on-a-chosen-answer` | A chosen answer carries a reason |
| `answer-tied-on-a-chosen-answer` | A chosen answer lists tied rotations |
| `answer-two-options-in-state-chosen` | Two options are in state `chosen` |
| `answer-chosen-names-no-option` | `chosen` names a rotation that is not an option |
| `answer-option-state-not-its-limit-check` | An option's state is not the verdict of its check |
| `answer-limit-check-not-of-the-strictness` | The strictness echoed is not the one the checks were taken from |
| `answer-with-two-options` | Two options |
| `answer-with-a-duplicate-option-id` | Two options share one id |
| `answer-limit-cost-value-without-against` | The limit cost has a value and no `against` |
| `answer-limit-cost-against-the-chosen-rotation` | The limit cost is against the chosen rotation |
| `answer-tipping-point-missing-without-a-reason` | A missing tipping point has no reason |
| `answer-tipping-price-range-not-the-question` | The tipping price range is not the question's |
| `answer-rain-stress-not-the-declared-factor` | The echo's factor is not the declared one |
| `answer-rain-stress-echo-without-a-factor` | An echo when no factor was asked |
| `answer-erosivity-not-in-the-list` | `erosivity` is `"per_year"` (not yet in the list) |
| `answer-kind-counts-not-the-years` | A count is not the number of years of that kind |
| `answer-soil-loss-n-years-not-the-years` | `n_years` is not the number of `ag_years` |
| `answer-limit-kind-not-in-the-list` | `kinds_not_met` names `"dry"` |
| `answer-tied-with-one-rotation` | Not resolved with one tied rotation |
| `answer-tied-rotation-not-in-state-meets` | A tied rotation is in state `not_resolved` |
| `answer-none-meets-with-an-option-that-meets` | `none_meets` while an option is in state `meets` |
| `answer-kind-of-year-present-with-a-detail` | A year with a kind carries a missing detail |
| `answer-present-margin-with-a-detail` | A present margin carries a missing detail |
| `answer-tipping-up-below-today` | The up tipping price is below today's price |
| `answer-tipping-price-outside-the-range` | The down tipping price is below the low end of the range |
| `answer-tipping-distance-sign-not-the-direction` | The down distance is positive |
| `answer-tipping-today-missing-without-a-reason` | Today's price is null with no shared reason |
| `answer-tipping-shared-reason-not-on-both-points` | A shared reason while the down point has a price |
| `answer-limit-kinds-not-met-not-the-checks` | `kinds_not_met` leaves out a kind whose check does not meet |
| `answer-limit-kind-not-in-the-record-and-not-met` | A kind is both in `kinds_not_in_record` and in `kinds_not_met` |
| `answer-limit-kind-not-in-the-record-with-a-resolved-check` | A kind not in the record has a resolved check |
| `answer-limit-missing-with-a-resolved-check` | The limit is null and checks are resolved |
| `answer-limit-every-kind-not-the-kinds` | `every_kind` meets while a kind does not meet |
| `answer-margin-without-its-provenance` | A present margin has no `provenance` (D249) |
| `answer-margin-not-derived` | A margin is labelled `DECLARED` |
| `answer-margin-without-its-source` | A present margin has no `source` (C4.2) |
| `answer-margin-with-a-range-and-its-absence` | A margin carries a `range` and a `range_missing` |
| `answer-margin-outside-its-range` | A margin's range ends below the margin |
| `answer-missing-margin-with-a-provenance` | A missing margin keeps its `provenance` and `range_missing` |
| `answer-soil-loss-without-a-range-or-its-absence` | A soil-loss mean has neither `range` nor `range_missing` |
| `answer-soil-loss-not-of-c4-6` | A soil-loss mean is labelled `SIMULATED` |
| `answer-soil-loss-label-not-the-one-of-d148` | A soil-loss mean carries another label |
| `answer-real-soil-loss-without-the-label-of-d148` | `example_data` false, the soil-loss means without the label of D148 |
| `answer-limit-cost-without-its-provenance` | The limit cost has no `provenance` |
| `answer-tipping-point-not-derived` | The down tipping price is labelled `OBSERVED` |
| `answer-tipping-today-without-its-provenance` | Today's price has no `provenance` |
| `answer-distance-without-its-provenance` | The down tipping distance has no `distance_provenance` (D249) |
| `answer-distance-not-derived` | The down tipping distance is labelled `OBSERVED` |
| `answer-limit-without-its-labels` | An option's declared limit has no `provenance` and no `range_missing` |
| `answer-limit-not-declared` | An option's declared limit is labelled `OBSERVED` |
| `answer-price-range-without-its-provenance` | The question's soybean price range has no `provenance` |
| `answer-price-range-not-declared` | The tipping price range is labelled `OBSERVED` |
| `answer-scope-not-the-words-of-d245` | `scope` is "Plant this rotation" |
| `answer-without-the-limit-phase-one-only` | `declared_limits` is empty |

### Rejected: an answer to another request (`check_answer_against_request`)

| Case | The variant |
|---|---|
| `answer-options-not-in-request-order` | The options are in reverse order |
| `answer-of-another-field` | The answer is of another field |
| `answer-questions-not-those-of-the-request` | The echoed `margin_of` differs from the request |
| `answer-not-example-data-to-an-example-request` | The answer to an example request says `example_data` false (its soil-loss means labelled as D148 asks) |
| `answer-tipping-today-not-the-declared-price` | `tipping_price.today` is not the declared soybean price |
| `answer-start-month-not-the-rotations` | `kinds_of_year.start_month` is not the rotations' start month |
| `answer-tipping-today-labels-not-the-declared-price` | Today's price is labelled `OBSERVED`; the declared price is `DECLARED` |
| `answer-limit-labels-not-the-declared-limit` | Every option's limit has the declared value but `range_missing` `NOT_AVAILABLE`; the declared limit's is `NOT_DECLARED` |

### Accepted

| Case | The variant |
|---|---|
| `accepted-request-with-five-rotations` | Five rotations |
| `accepted-request-soil-loss-limit-missing` | The limit is missing `NOT_DECLARED` |
| `accepted-answer-not-resolved-with-tied` | Not resolved with two tied rotations, both in state `meets`, and a missing limit cost |
| `accepted-answer-none-meets` | `none_meets` with every option in state `does_not_meet` |
| `accepted-answer-margin-missing-without-a-detail` | A margin missing `MISSING_INPUT` with no detail, as `MarginResult` allows |
| `accepted-answer-kind-of-year-missing-without-a-detail` | A year missing `NO_COVERAGE` with no detail, as `KindOfYear` allows; every count null |
| `accepted-request-soybean-price-missing` | The soybean price is missing `NOT_DECLARED` |
| `accepted-answer-without-a-rain-stress-test` | No factor asked, no echo |
| `accepted-answer-rain-stress-factor-missing` | The factor is missing `NOT_DECLARED`, echoed in the missing form |
| `accepted-answer-not-example-data` | `example_data` is false (a real answer), every present soil-loss mean with the label of D148 |
| `accepted-answer-margin-with-a-range` | A margin with a range around it instead of `range_missing` |
| `accepted-answer-example-soil-loss-with-the-label-of-d148` | The example's soil-loss means carry the label of D148 |
| `accepted-answer-with-a-second-declared-limit` | `declared_limits` holds `PHASE_ONE_ONLY` and one more limit |

### Checked without a case of their own

- Both examples load, dump and load back unchanged, and the answer example answers the request example.
- Both examples say `example_data: true`; a test shows the check refuses `false`.
- The literals equal those of `economics/` and `api/rain_stress.py`; the mirrored models have the field names of their dataclasses, plus the labels of D249 (and `RainStressApplied`, `RainStressMissingOut`, `SourceOut` those of `RainStress`, `RainStressMissing` and `SourceOut` of `api/`; `SiteReference` that of `api/rotations.py`). The checks against `kinds_of_year/` and `api/rain_stress.py` are skipped while those modules are not on `main`.
- The contract imports neither `kinds_of_year` nor `api` (read from its source).
- The example answer says `scope` and `PHASE_ONE_ONLY`, never "Plant this rotation"; every present number in it carries its labels, and every present margin its source.
- `retrieved_at` is written in UTC with a `Z`, exactly as `SourceOut` of `api/rotations.py` writes it, and reads back.
- The answer example shows one chosen rotation, one that does not meet the limit, a missing value and a tipping price.

## OPEN

1. **Margin range.** A margin carries a `range` or `range_missing` (D249); how the route computes a range from the declared facts is OPEN, and the example gives `range_missing` `NOT_AVAILABLE`.
2. **Currency.** `USD` only, as in `contracts/economic_facts/` (its OPEN question 2).
3. **Dry-year label.** No kind of year is named "dry" here; the screen labels kinds.
4. **Per-year erosivity.** `erosivity` is `"mean_annual"` only; S-026 may add `"per_year"`.
5. **Source state of a transcribed record.** The ONI record is listed with state `"cached"` (PROPOSED): `SourceOut` has no state for a record read from the repository.
6. **One start month.** `kinds_of_year.start_month` is one month for the whole answer; rotations with different start months are not handled yet.
7. **Rotation years.** How the route turns a `RotationDefinition` into the crops of each agricultural year for `compute_rotation_margin` is the route's (S-018), not this contract's.
