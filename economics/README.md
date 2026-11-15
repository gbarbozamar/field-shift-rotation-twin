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
) -> LimitAssessment
```

- `limit`: a `contracts.inputs.common.Value` in `"t ha-1 yr-1"` (`UNIT_SOIL_LOSS_ANNUAL`, C1.2), which may be missing with its reason (for example `NOT_DECLARED`).
- `SoilLossLevel` (a `typing.Protocol`): any object with `value` (float or `None`), `reason` (a `ReasonCode` or `None`) and `detail` (text or `None`), such as the mean by kind of year of `kinds_of_year/aggregate.py` (not imported here). Its unit is the caller's job; an object that has a `unit` attribute must say `"t ha-1 yr-1"`.
- `by_kind`: one level for each kind of `KINDS_OF_YEAR`.
- `LimitCheck` (frozen dataclass): `verdict`, `reason`, `detail`; `reason` and `detail` are set exactly when the verdict is `not_resolved`.
- `LimitAssessment` (frozen dataclass): `limit` (the declared value, or `None` when it is missing, never 0), `unit`, `on_average`, `every_kind`, `by_kind` (a read-only mapping, one `LimitCheck` per kind in `KINDS_OF_YEAR` order), `kinds_not_met` and `kinds_not_resolved` (tuples of kinds, in `KINDS_OF_YEAR` order).

## Rules (PROPOSED)

- `meets` when the soil loss is at or below the limit; `does_not_meet` when it is above. The values are compared as given, without rounding.
- Limit missing: every check is `not_resolved`, reason `MISSING_INPUT`, detail "the soil-loss limit of the field is not declared (<its reason>)"; `limit` is `None`, `kinds_not_met` is empty and `kinds_not_resolved` holds every kind.
- A soil-loss level missing (its `value` is `None`): that check is `not_resolved`, reason `MISSING_INPUT`, the detail naming the level (on average, or the kind of year) and the reason and detail it carries.
- `on_average` uses `average` only; it is not built from the kinds.
- `every_kind`: `does_not_meet` when any kind does not meet the limit, even if another kind is not resolved (one failing kind is enough); otherwise `not_resolved` when any kind is not resolved, the detail naming those kinds; otherwise `meets`.
- A kind with no year in the record arrives missing `NO_COVERAGE`: it is `not_resolved` like any missing level (the option easiest to undo).
- A limit of 0 is a declared limit like any other, not a missing one.
- `ValueError` on structural misuse: `by_kind` without exactly the keys of `KINDS_OF_YEAR`; a negative limit; a limit (present or missing) in another unit; a missing limit without its missing part (only possible for a `Value` built without validation); a level whose `unit` attribute is not `"t ha-1 yr-1"`; a level whose `value` is not `None` and is not a finite real number (a boolean, a text, NaN or infinity), the message naming the level; a level with both a `value` and a `reason` (C3.1). Every check runs before any comparison, so misuse is refused even when the limit is missing.
- `LimitCheck` refuses a verdict outside `Verdict` and a reason outside `ReasonCode` (C3.2) with `ValueError`.
- Inputs are not mutated; the results are frozen.

## OPEN

1. **Uncertainty.** The limit's `range` and the levels' ranges are not used: a level whose range straddles the limit is judged on its value only. How a range turns into "not resolved" is for the lead developer.
2. **A level with `value` `None` and no `reason`.** Treated as missing, its detail saying "no reason given"; whether that should be a `ValueError` is open.
3. **A negative soil-loss level.** Not refused; whether a soil-loss level can be negative is for the erosion lane.
