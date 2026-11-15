# economics: the simple margin of a rotation

Status: **PROPOSED** (blueprint section 3.7). Built by unit `l2/economics-margin`.

`economics/margin.py` holds one public pure function, `compute_rotation_margin`, that gives the simple margin per hectare and agricultural year of one rotation in each kind of year (`el_nino`, `neutral`, `la_nina`) and on the average of the record, from the economic facts the producer declares (`contracts/economic_facts/`). A missing fact gives a missing margin with its reason, never zero.

No network call, no parameter value, no price forecast, no price on lost soil, no discounting. The rules below are arithmetic on what the user declares, not parameters.

Acceptance test, from the repository root:

```bash
uv run pytest economics/
```

Every number in `test_margin.py` is invented test data, from no source.

## Signature (PROPOSED)

```python
def compute_rotation_margin(
    years: Sequence[Sequence[str]],
    facts: EconomicFacts,
    year_counts: Mapping[str, int] | None,
) -> RotationMargin
```

- `years`: one entry per agricultural year of one cycle of the rotation, each entry the `crop_id`s sown in that agricultural year, for example `[["wheat", "soybean_second"], ["sorghum", "cover"]]`.
- `facts`: an `EconomicFacts` of `contracts.economic_facts`.
- `year_counts`: how many agricultural years of the record fall in each kind of year (a later unit supplies them; never a constant in the code). `None` means not known.
- `RotationMargin` (frozen dataclass): `by_kind`, one `MarginResult` per kind of `KINDS_OF_YEAR`; `average`, a `MarginResult`.
- `MarginResult` (frozen dataclass): `value` (float or `None`), `unit` (`"USD ha-1 yr-1"`), `reason` (a `ReasonCode` of `contracts/inputs/common.py`, C3.2, or `None`), `detail` (text or `None`). Exactly one of `value` and `reason` is set.

## Rules (PROPOSED)

- "The field is divided in as many parts as the rotation has years, so every year there is a bit of everything": the margin per hectare and year is the sum of the margins of every crop cycle of every entry of `years`, divided by `len(years)`.
- Grain crop cycle in kind `t`: `price * yield[t] - cost`.
- Cover crop cycle, any kind: `- cost`.
- Declared-margin crop in kind `t`: `declared_margin[t]`, added once per occurrence in `years`.
- A needed value that is missing makes that kind's margin missing, reason `MISSING_INPUT`, with a detail naming the `crop_id`, the member, the kind of year and the reason the input carries (for example `NOT_DECLARED`). Every missing input of the kind is listed.
- A `crop_id` in `years` that is not in `facts.crops`: missing `MISSING_INPUT`, the detail names it.
- Average: `sum over kinds of margin[t] * year_counts[t] / sum(year_counts)`. Missing `NOT_AVAILABLE` when `year_counts` is `None` (the kinds of year of the record are not classified); the three per-kind margins are still computed. Missing `MISSING_INPUT` when the margin of a kind with a count above zero is missing, the detail naming the kind. A kind with count 0 does not enter the average, so its missing margin does not make the average missing.
- When `year_counts` is `None` and a kind is also missing, the average says `NOT_AVAILABLE` (the counts are checked first).
- A `year_counts` mapping whose every count is `None` (what `kinds_of_year.count_kinds` gives when a year of the record is missing) gives the average missing `NO_COVERAGE`, with a detail saying that at least one agricultural year of the record has no kind of year, so the years of each kind are not counted (PROPOSED, S-027: the classification's only missing reason is `NO_COVERAGE`). The three per-kind margins are still computed. `year_counts=None` keeps `NOT_AVAILABLE`. A mapping with some counts `None` and some integers is a `ValueError` ("counts are either all known or all None"), checked after the key checks.
- `ValueError` on structural misuse, which is not a missing fact: `years` empty, or a text instead of a list; an entry empty (a bare fallow year has no declared fact; the option easiest to undo), or a text instead of a list of `crop_id`s; an item of an entry that is not a text (an int, `None`, a list); an entry that holds a declared-margin crop together with any other crop; `year_counts` with a key not in `KINDS_OF_YEAR`, a kind left out, a count that is negative, not an integral number (any `numbers.Integral` is accepted, such as a numpy integer), or a boolean, or every count zero.
- `RotationMargin.by_kind` is a read-only mapping: the result cannot be changed after it is computed.

## OPEN

1. **Uncertainty range of the margin (C2).** Not computed. The declared values carry `range_missing` today; how a range on a price, cost or yield travels into the margin is for the lead developer. No range is made up.
2. **Currency.** The contract accepts `USD` only and the unit is `USD ha-1 yr-1`; other currencies are question 2 of `contracts/economic_facts/README.md`.
3. **Mapping from a rotation definition or a calendar onto `years`.** Not this unit (a later unit, S-018). Whether a `crop_id` of the facts must match one of the rotation definition is question 7 of the contract.
4. **Fallow years.** An empty entry is refused; whether a fallow year should count as a year of zero cost, or carry a declared cost, is for the interface developer.
5. **A declared-margin crop with another crop in the same year.** Refused (PROPOSED, the option easiest to undo). A declared margin is per hectare and agricultural year, so it already covers the whole year; adding a grain or cover cycle to the same year would count that year twice over, or would need a rule for splitting the year that nobody has decided. Whether a pasture can share a year with another crop, and how, is for the interface developer.
6. **`MarginResult` is not the contract `Value` shape.** It carries no provenance (a computed margin would be `DERIVED`, C4.1), no source and no `range` or `range_missing` (C2.2). The service route (S-018) converts it into the contract shape; until then it stays an internal result.

# economics: soil loss against the declared limit

Status: **PROPOSED** (blueprint section 3.7). Built by unit `l2/soil-loss-limit`.

`economics/limit.py` holds one public pure function, `assess_limit`, that says for one rotation whether its soil loss meets the soil-loss limit the user declared for the field, in the two ways of the objective: on the average of the record, and in every kind of year (`el_nino`, `neutral`, `la_nina`). It lists the kinds of year in which the limit is not met. Erosion is a limit, not a cost.

The limit is always a declared input: no limit value, default or constant is in the code. No limit declared gives "not resolved" with its reason. Every number in `test_limit.py` is invented test data, from no source.

## Signature (PROPOSED)

```python
Verdict = Literal["meets", "does_not_meet", "not_resolved"]

def assess_limit(
    limit: Value,
    average: SoilLossLevel,
    by_kind: Mapping[str, SoilLossLevel],
    *,
    kinds_in_record: Collection[str] | None = None,
) -> LimitAssessment
```

- `limit`: a `contracts.inputs.common.Value` in `"t ha-1 yr-1"` (`UNIT_SOIL_LOSS_ANNUAL`, C1.2), which may be missing with its reason (for example `NOT_DECLARED`).
- `SoilLossLevel` (a `typing.Protocol`): any object with `value` (float or `None`), `reason` (a `ReasonCode` or `None`) and `detail` (text or `None`), such as the mean by kind of year of `kinds_of_year/aggregate.py` (not imported here). Its unit is the caller's job; an object that has a `unit` attribute must say `"t ha-1 yr-1"`.
- `by_kind`: one level for each kind of `KINDS_OF_YEAR`.
- `LimitCheck` (frozen dataclass): `verdict`, `reason`, `detail`; `reason` and `detail` are set exactly when the verdict is `not_resolved`.
- `LimitAssessment` (frozen dataclass): `limit` (the declared value, or `None` when it is missing, never 0), `unit`, `on_average`, `every_kind`, `by_kind` (a read-only mapping, one `LimitCheck` per kind in `KINDS_OF_YEAR` order), `kinds_not_met` and `kinds_not_resolved` (tuples of kinds, in `KINDS_OF_YEAR` order), `kinds_not_in_record` (see below, `()` by default).

## Rules (PROPOSED)

- `meets` when the soil loss is at or below the limit; `does_not_meet` when it is above. The values are compared as given, without rounding.
- Limit missing: every check is `not_resolved`, reason `MISSING_INPUT`, detail "the soil-loss limit of the field is not declared (<its reason>)"; `limit` is `None`, `kinds_not_met` is empty and `kinds_not_resolved` holds every kind.
- A soil-loss level missing (its `value` is `None`): that check is `not_resolved`, reason `MISSING_INPUT`, the detail naming the level (on average, or the kind of year) and the reason and detail it carries.
- `on_average` uses `average` only; it is not built from the kinds.
- `every_kind`: `does_not_meet` when any kind does not meet the limit, even if another kind is not resolved (one failing kind is enough); otherwise `not_resolved` when any kind is not resolved, the detail naming those kinds; otherwise `meets`.
- A kind with no year in the record arrives missing `NO_COVERAGE`: it is `not_resolved` like any missing level (the option easiest to undo).
- A limit of 0 is a declared limit like any other, not a missing one.
- Kinds of year with no year in the record (unit `l2/review-whole-2`, PROPOSED): the optional keyword-only `kinds_in_record` (a collection of kinds, a subset of `KINDS_OF_YEAR`, else `ValueError`; one text is refused) names the kinds that have at least one year in the record, for example the kinds with a count above zero in `kinds_of_year.count_kinds`. `None` (the default) keeps every kind in `every_kind`, exactly as before, so a kind missing `NO_COVERAGE` leaves `every_kind` not resolved. When it is given, a kind not in it keeps its `by_kind` check (whatever its level gives), but is left out of `every_kind`, `kinds_not_met` and `kinds_not_resolved`, and is listed in the new field `LimitAssessment.kinds_not_in_record` (in `KINDS_OF_YEAR` order, `()` by default); the detail of `every_kind`, when it has one, ends "left out, no year in the record: <kinds>". When `every_kind` is `meets` or `does_not_meet`, its `LimitCheck` carries no detail even with left-out kinds, so the caller (the route, S-018) must show `kinds_not_in_record` next to `every_kind`. A left-out kind whose level has a value contradicts "no year in the record" and is refused with `ValueError` naming the kind (PROPOSED, code review of S-028; it replaces the earlier rule that kept such a kind left out). An empty `kinds_in_record` makes `every_kind` not resolved with reason `NO_COVERAGE`, detail "no kind of year is in the record, ...". With a missing limit, `kinds_not_resolved` holds only the kinds in the record; the missing limit comes first, so a missing limit with an empty `kinds_in_record` keeps `every_kind` not resolved with reason `MISSING_INPUT` (the limit is not declared), its detail ending with the left-out kinds. Refused with `ValueError`: a `Mapping` passed as `kinds_in_record` (such as the dict of counts `count_kinds` returns, which would otherwise be read as its keys: pass the kinds with at least one year instead), a text or bytes, any object that is not a `Collection` (an integer, a generator, an iterator), and a collection holding an element that cannot be a kind (an unhashable one, such as a list).
- `ValueError` on structural misuse: `by_kind` without exactly the keys of `KINDS_OF_YEAR`; a negative limit; a limit (present or missing) in another unit; a missing limit without its missing part (only possible for a `Value` built without validation); a level whose `unit` attribute is not `"t ha-1 yr-1"`; a level whose `value` is not `None` and is not a finite real number (a boolean, a text, NaN or infinity), the message naming the level; a level with both a `value` and a `reason` (C3.1). Every check runs before any comparison, so misuse is refused even when the limit is missing.
- `LimitCheck` refuses a verdict outside `Verdict` and a reason outside `ReasonCode` (C3.2) with `ValueError`.
- Inputs are not mutated; the results are frozen.

## OPEN

1. **Uncertainty.** The limit's `range` and the levels' ranges are not used: a level whose range straddles the limit is judged on its value only. How a range turns into "not resolved" is for the lead developer.
2. **A level with `value` `None` and no `reason`.** Treated as missing, its detail saying "no reason given"; whether that should be a `ValueError` is open.
3. **A negative soil-loss level.** Not refused; whether a soil-loss level can be negative is for the erosion lane.

# economics: the rotation to plant

Status: **PROPOSED** (blueprint section 3.7). Built by unit `l2/decision-rule` (S-015).

`economics/decide.py` holds one public pure function, `choose_rotation`, that answers "What should I plant?" for the rotations given (the story speaks of three to five): the most margin per hectare and year among the rotations that meet the soil-loss limit under the chosen strictness, what meeting the limit costs against the best rotation that does not meet it, the case where none meets, and "not resolved" when the data cannot separate the answer. Erosion is a limit, not a cost: it never enters the margin.

No network call, no parameter value, no limit, price or threshold, and no numeric literal in the module. Every number in `test_decide.py` is invented test data, from no source; every expected answer there is PROPOSED.

## Signature (PROPOSED)

```python
Strictness = Literal["on_average", "every_kind"]
Answer = Literal["chosen", "none_meets", "not_resolved"]
OptionState = Literal["chosen", "meets", "does_not_meet", "not_resolved"]

def choose_rotation(
    options: Sequence[RotationOption],
    strictness: Strictness,
) -> Decision
```

- `RotationOption` (frozen dataclass): `rotation_id`, `margin` (a `MarginResult`, the margin to rank by: the caller picks the average or a kind of year), `limit` (a `LimitAssessment` of `assess_limit`).
- `OptionVerdict` (frozen dataclass): `rotation_id`, `state`, `margin`, `limit_check` (the `LimitCheck` of the strictness).
- `LimitCost` (frozen dataclass): `value` (float or `None`), `against` (the `rotation_id` of the best rotation that does not meet the limit, or `None`), `costs_nothing`, `reason` (a `ReasonCode` of C3.2 or `None`), `detail`, `unit` (`"USD ha-1 yr-1"`).
- `Decision` (frozen dataclass): `answer`, `strictness`, `chosen` (a `rotation_id` or `None`), `reason`, `detail`, `tied` (the rotations the data cannot separate, else `()`), `options` (one `OptionVerdict` per option, in input order), `limit_cost`.

## Rules (PROPOSED)

- The check of an option is `limit.on_average` or `limit.every_kind` by the strictness.
- Candidates are the options whose check is `meets`, ranked by `margin.value`, larger is better, compared as given without rounding.
- `not_resolved` (`chosen` `None`), checked in this order:
  1. a candidate whose margin is missing: reason `MISSING_INPUT`, the detail naming it and the reason and detail its margin carries;
  2. an option whose check is `not_resolved` and whose margin is missing or at or above the best candidate margin (it could be the answer): reason `MISSING_INPUT`, the detail naming it, saying why it blocks (its margin is missing, with the reason it carries, or its margin is at least the best candidate's, both values named) and giving its check's detail. One with a known margin below the best candidate does not change the answer and does not block it;
  3. two or more candidates sharing the best margin exactly: reason `NOT_COMPUTABLE` (no new reason code is added to C3.2), `tied` listing them in input order, the detail saying the data cannot separate them.
- No candidate and some option `not_resolved`: `not_resolved`, reason `MISSING_INPUT`, the detail naming those options.
- No candidate and none `not_resolved`: `none_meets`, `chosen` `None`, reason `NOT_APPLICABLE`. The detail is true under the strictness: `on_average` "every rotation loses more soil than the limit on average"; `every_kind` "every rotation loses more soil than the limit in at least one kind of year", followed by each rotation with its kinds not met (`kinds_not_met`).
- `chosen`: the single best candidate. Its state is `chosen`; the other candidates are `meets`; the rest carry their check's verdict.
- `LimitCost`, only when the answer is `chosen`. If any option whose check is `does_not_meet` has a missing margin: `value` `None`, `against` `None`, `costs_nothing` False, reason `MISSING_INPUT`, the detail naming every such option and the reason its margin carries (that margin could be the largest, so no lower bound is given; fix round 1). Otherwise, among the options whose check is `does_not_meet`, the best one (the first in input order on an exact tie). If its margin is above the chosen margin: `value` is its margin minus the chosen margin, `against` its id. Otherwise (none, or none with more margin): `value` `None`, `costs_nothing` True, `against` `None` (meeting the limit costs nothing here). Never a default zero.
- When the answer is not `chosen`, `LimitCost` has `value` `None` and `costs_nothing` False: reason `NOT_APPLICABLE` for `none_meets`, `NOT_COMPUTABLE` for `not_resolved`, with a detail saying why.
- `options` may be any iterable (a generator too); it is read once into a tuple first.
- `ValueError` on structural misuse, before any comparison: a strictness outside `Strictness`; no option (also an empty generator); a `rotation_id` that is not a non-empty text; a duplicate `rotation_id`; options whose `LimitAssessment`s were judged against different limits (`limit.limit` or `limit.unit` differ; two missing limits, `None`, count as the same); a margin whose unit is not `"USD ha-1 yr-1"`; a margin value that is a boolean, not a real number, NaN or infinite. The count of options is not refused (the route, S-018, checks it).
- `LimitCost` refuses inconsistent fields with `ValueError`: a `value` is set exactly with `against`, and never with `costs_nothing`, `reason` or `detail`; `costs_nothing` excludes `reason` and `detail`; a missing value with `costs_nothing` False needs a `reason` and a `detail`; a reason outside C3.2; another unit.
- `Decision` refuses inconsistent fields with `ValueError`: `chosen` is set exactly when the answer is `chosen`; `reason` and `detail` are set exactly when it is not; `tied` is non-empty only when the answer is `not_resolved`; an answer, strictness or reason outside its set.
- Inputs are not mutated; the results are frozen.

## OPEN

1. **A range on the margin.** `MarginResult` carries no range, so the rule of `decision/` ("a difference whose range touches or crosses zero is not separated") cannot be applied; only an exact tie or a missing value is unseparable. Once a margin carries a range, two candidates whose difference range touches zero should be `not_resolved` too.
2. **A cost of the limit when a non-meeting margin is missing.** Fix round 1 (PROPOSED): any missing margin among the rotations that do not meet the limit makes the cost missing (`MISSING_INPUT`), even when a known one already beats the chosen rotation, because the missing one could be larger and a lower bound would travel unmarked. Whether a lower bound, marked as such, would be more useful is for the lead developer.
3. **Reason codes.** `NOT_COMPUTABLE` for an exact tie and `NOT_APPLICABLE` for `none_meets` reuse C3.2 codes; whether a dedicated code is wanted is for the lead developer.
4. **Which margin ranks.** The caller picks the average or a kind of year; the rule for "every kind" strictness does not change the margin used.

# economics: the tipping price of soybean

Status: **PROPOSED** (blueprint section 3.7). Built by unit `l2/tipping-price` (S-016).

`economics/tipping.py` holds one public pure function, `find_tipping_price`, that says at which soybean price the answer of `choose_rotation` changes: the nearest price above today's declared price and the nearest below, inside a price range the user declares, each with the rotation (or the answer) that takes over and how far today's price is from it, in percent. A tipping price, never a forecast. Where no price in the declared range changes the answer, it says exactly that.

No network call, no price, range or threshold in the code: today's price comes from the declared facts and the range is declared by the user. The engines are reused, never copied. Every number in `test_tipping.py` is invented test data, from no source; every expected value there is worked out by hand in a comment and is PROPOSED.

`decision/functions.py` has a `tipping_point` of its own; it is not used here. It brackets between the admitted values of one uncertain input over the scenario ids of a `ResultsTable`, not over a price, and that module is being rewritten (issue #304), so this module does not import `decision/`.

## Signature (PROPOSED)

```python
Direction = Literal["up", "down"]
MARGINS_OF = ("average", *KINDS_OF_YEAR)

def find_tipping_price(
    options: Sequence[TippingOption],
    facts: EconomicFacts,
    year_counts: Mapping[str, int | None] | None,
    soybean_crop_ids: Collection[str],
    price_range: PriceRange,
    strictness: Strictness,
    margin_of: str = "average",
) -> TippingPrice
```

- `TippingOption` (frozen dataclass): `rotation_id`, `years` (as `compute_rotation_margin` takes them), `limit` (a `LimitAssessment`; the limit does not depend on the price).
- `PriceRange` (frozen dataclass): `low`, `high` (stored as floats), `unit` (`"USD t-1"`). Declared by the user.
- `TippingPoint` (frozen dataclass): `direction`, `price` (float or `None`), `unit`, `takes_over` (the `rotation_id` chosen just past the price, or `None` when the answer there is `none_meets` or `not_resolved`), `answer_after` (the `Decision.answer` just past the price, or `None` when `price` is `None`), `distance_percent`, `reason`, `detail`.
- `TippingPrice` (frozen dataclass): `today` (float or `None`), `unit`, `price_range`, `decision` (the `Decision` at today's price), `up`, `down`, `reason`, `detail` (set when both points are missing for one shared cause: today's price missing or outside the range).
- `margin_of`: the margin the ranking reads, `"average"` or one kind of `KINDS_OF_YEAR`.

## Rules (PROPOSED)

- The decision at today's price: `compute_rotation_margin` on `facts` as declared (no copy), the margin of `margin_of`, then `choose_rotation` with the options' limits.
- The margin at the two ends of the range: a copy of `facts` (through `model_dump` and `model_validate`; the input is never changed) in which every crop of `soybean_crop_ids` has price `low` (or `high`), a value with provenance `"DECLARED"` (what `GrainCrop.price` admits for a present value) whose source says it is a price tried by the search, then `compute_rotation_margin` and the margin of `margin_of`. These are the only two engine runs on a copy. The margin at any other price comes from each rotation's line (intercept plus slope times price), and the answer there from `choose_rotation` on those margins and the options' limits.
- Today's price: the price of the named crops in `facts`. Every named crop must be a grain crop present in the facts; their present prices must be equal (one soybean price is asked). If any named crop has no price, today's price is missing: `today` `None`, `up` and `down` missing `MISSING_INPUT` with a detail naming the crop and the reason its price carries; `reason` and `detail` of the result say the same.
- Today's price outside `[low, high]`: not a `ValueError`; `up` and `down` missing `NOT_APPLICABLE`, the detail saying today's price is outside the declared range.
- The margin of each rotation is linear in `p` (price times yield minus cost, summed and averaged): its slope and intercept come from two evaluations at `low` and `high`, without rounding or tolerance. A margin missing at either end is missing for a reason other than the soybean price, so it is missing at every price (PROPOSED, fix round 1): that rotation gets no line, and its missing `MarginResult` travels unchanged into `choose_rotation` at every price, whose own rules say whether it blocks the answer. A rotation that meets the limit with a missing margin makes the answer `not_resolved` at every price (so no price in the range changes it); one that does not meet the limit does not block the search (only the cost of the limit goes missing).
- Breakpoints: the prices strictly inside `(low, high)` where two rotations' margin lines cross. The answer is constant between breakpoints.
- A change of answer is a change of `(answer, chosen, tied)` against the decision at today's price.
- Up (PROPOSED, fix round 1): the edges are today's price, then the breakpoints strictly above it in increasing order, then `high`. For each interval between two consecutive edges, from today outwards, `choose_rotation` is evaluated at its middle; the first interval whose answer differs gives the tipping point, its edge nearer today. So when the answer right next to today differs from today's (today's price is on a crossing and today's answer is a tie), the tipping point is today itself, distance 0. Down: symmetric, with the breakpoints strictly below today in decreasing order, then `low`. No breakpoint is compared with today for equality, so a float breakpoint that falls a few ulps on either side of today gives the same answer. The answer is never evaluated at a breakpoint itself, where an exact tie is `not_resolved` by design. Today at `high` (or `low`) has nothing beyond it in that direction.
- No breakpoint changes the answer in a direction: `price` `None`, reason `NOT_APPLICABLE`, detail `"no price in this range changes the answer"` followed by the range, for example `(100.0 to 800.0 USD t-1)`. Never a default zero.
- `distance_percent = (price - today) / today * 100`, negative below today. Today's price zero: `None`, reason `NOT_COMPUTABLE` (the price stays set).
- The decision at today's price need not be `chosen`: the tipping points are computed the same way and say what `choose_rotation` says past each breakpoint. The limit does not depend on the price, so `none_meets` stays `none_meets`.
- `ValueError` on structural misuse: `soybean_crop_ids` empty, a text, not iterable (such as `None` or a number), or holding an item that is not a text (an unhashable item included, checked before any hashing); a named crop not in the facts, or not a grain crop (a cover or declared-margin crop); named crops with different present prices; `margin_of` not in `MARGINS_OF`; `price_range` not a `PriceRange`; a `PriceRange` with `low >= high`, a negative or non-finite bound, a boolean or a non-number, or another unit. `options`, `year_counts` and `strictness` are checked by `compute_rotation_margin` and `choose_rotation`.
- Inputs are not mutated; the results are frozen.

## OPEN

1. **`answer_after` when there is no tipping price.** The brief types it `Answer`; here it is `None` whenever `price` is `None` (nothing lies past a price that does not exist). Whether it should carry today's answer instead is for the interface developer.
2. **A range on the margin.** As for `choose_rotation`, no range travels, so a breakpoint is exact; a range on prices or yields would make the tipping price a range too.
3. **One named crop with a price and another without.** Today's price is missing (PROPOSED); whether the present one should be used is for the interface developer.
4. **The cost of the limit at the tipping price.** Not computed (out of scope).
5. **Near-coincident crossings.** Three or more lines that cross at one real price give float breakpoints a few ulps apart; near-coincident crossings may report a `not_resolved` interval between them. No tolerance is invented; a tolerance is a person's choice.

# economics: the answer of "What should I plant?"

Status: **PROPOSED** (blueprint section 3.7). Built by unit `l2/plant-rules-to-economics` (S-030, point 2 of the platform review of PR 310).

`economics/plant.py` holds the rules that decide which crops and years count in each margin and mean of the answer of `POST /api/plant/run`, behind one public entry function. The route `api/plant.py` only gathers the request and the engine runs and hands them over; it imports the moved names back, so `from api.plant import ...` keeps working. The module imports contracts, `economics/` and `kinds_of_year/` only, never `api/`, `adapters/` or `engine/` (checked by `test_plant.py`). Every answer of the route is the same as before the move.

## Signature (PROPOSED)

```python
def assemble_answer(
    request: PlantRequest,
    runs: Sequence[EngineRun],
    *,
    classified: Classified,
    record: Mapping[str, Any],
    rain_stress: Mapping[str, Any] | None,
    sources: list[dict[str, Any]],
    example_data: bool,
) -> PlantAnswer
```

- `EngineRun` (a `typing.Protocol`): any object with `result` (a `ResultsPerRotation` or `None`) and `result_missing` (an object with `reason` and `detail`, or `None`). `api.ports.EnginesResult` is one, without conversion.
- `classified`: what `classify_years(record, record_years, why, start_month, rotations)` gives. `record_years` is the first and last whole agricultural year of the record as the caller computed them, or `None` with `why` the text of why they are not known (the route reads them from its settings).
- `rain_stress`: the rain-stress echo already as JSON-ready data, or `None`; `sources`: the source rows of the answer as JSON-ready data. Both are copied unchanged.
- The answer is checked with `check_answer_against_request`; a failure raises.
- Also public, for the route's tests: `Classified`, `CycleYears`, `cycle_years`, `soil_loss_means`. `_ag_year_of` follows C5.3 of `contracts/CONVENTIONS.md` and is checked against `api.phases.ag_year_of`.

The rules themselves (`cycle_years`, `soil_loss_means`, `classify_years`) are written in their docstrings, with their PROPOSED and OPEN notes, moved unchanged from `api/plant.py`. `assemble_answer` is not exported from `economics/__init__.py` (PROPOSED: importing the package does not load the plant answer).
