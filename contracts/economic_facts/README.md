# Economic facts contract

**The example is example data.** Every number in `examples/PLACEHOLDER_economic_facts.json` is invented for illustration and comes from no source: no market, no producer, no survey. Every `crop_id` carries the word PLACEHOLDER and the file says `"example_data": true`. The numbers are not parameters and no engine, test threshold or screen may take them as such.

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the lead developer, as owner of `contracts/`, and the interface developer, who collects these facts from the user.

This folder holds Pydantic models and one example of the "economic facts" contract: the economic facts a producer declares for one field.

| Contract | Producer → consumers | Model | Example |
|---|---|---|---|
| Economic facts | Interface (what the user declares) → the classification of kinds of year and the margin engine of later units | `economic_facts.EconomicFacts` | `examples/PLACEHOLDER_economic_facts.json` |

A builder session of lane L2 landed it here (unit `l2/contracts-economic-facts`). Identifiers such as C3.1 below refer to `contracts/CONVENTIONS.md`.

Acceptance test, from the repository root:

```bash
uv run pytest contracts/economic_facts/
```

Models and pure validation only. No network calls, no parameter values, no thresholds, no citations, **no margin computation**. The models import the base model, `Value` and the non-blank text from `contracts/inputs/common.py`, as `contracts.inputs.common`, so a value, its range, its `missing` part and its provenance follow the same rules as every other input contract.

## Layout

| Path | Content |
|---|---|
| `economic_facts.py` | `EconomicFacts`, the three crop models, `YieldByYear`, `MarginByYear`, `KINDS_OF_YEAR` and the unit strings |
| `examples/PLACEHOLDER_economic_facts.json` | The example: one crop of each kind |
| `test_examples.py` | The acceptance test |

## Field list

All PROPOSED. Every model rejects unknown members and does not coerce types: a number written as text is rejected. No member listed as required has a default.

### `EconomicFacts`: the facts of one field

| Field | Type | Rule |
|---|---|---|
| `contract` | `"economic_facts"` | Required |
| `example_data` | true or false | Required. True for example data |
| `case_id` | text | Required, not blank. The identifier the other contracts use |
| `field_id` | text | Required, not blank. The identifier the other contracts use |
| `currency` | `"USD"` | Required. The only currency for now (OPEN, question 2) |
| `crops` | list of crops | Required, **at least one crop**. `crop_id` is unique in the list |

### A crop: one of three kinds, told apart by `kind`

`crops` is a discriminated union on `kind` (PROPOSED: chosen over one model with a validator, because each kind then rejects the members of the other kinds by the same rule that rejects any unknown member, and a consumer gets a typed model per kind). A `kind` that is not one of the three is rejected. `crop_id` is required and not blank in every kind; it is text, as in `contracts/rotation_definition/`.

| `kind` | Required members | Rejected members |
|---|---|---|
| `grain` | `crop_id`, `price`, `cost`, `yield` | `declared_margin` |
| `cover` | `crop_id`, `cost` | `price`, `yield`, `declared_margin` |
| `declared_margin` | `crop_id`, `declared_margin` | `price`, `cost`, `yield` |

### The values and their units

Each value is a `Value` of `contracts/inputs/common.py`: a number with its unit, its range or `range_missing` (C2.2), its provenance and its source (C4.1, C4.2); or null with a `missing` part and its reason (C3.1), the unit kept. A fact the user did not give is missing `NOT_DECLARED`, never zero. In the example every present value is `DECLARED`, with source `"user"` and `range_missing` `NOT_DECLARED`.

| Member | Unit, exactly | Sign |
|---|---|---|
| `price` | `USD t-1` | Not negative |
| `cost` | `USD ha-1` | Not negative |
| `yield.<kind of year>` | `t ha-1` | Not negative |
| `declared_margin.<kind of year>` | `USD ha-1 yr-1` | Any: a declared margin may be negative |

The sign rule applies to the number of a present value and to the low bound of its range (PROPOSED; OPEN, question 4).

**Provenance (PROPOSED).** Every present value of this contract is declared by the user: its provenance is `DECLARED`, and any other label is rejected.

**Time basis (PROPOSED).** `cost` (grain and cover) is per hectare for one crop cycle, that is one sowing of that crop; a grain `yield` is per hectare for that cycle. A `declared_margin` is per hectare and agricultural year. The margin engine of a later unit adds the cycles that fall in one agricultural year. The unit strings stay as above.

**`crop_id`.** Not blank, with no leading or trailing white space; unique in the list, compared after removing surrounding white space.

**`yield` in Python.** `yield` is a Python keyword, so `GrainCrop` names the member `yield_`. The model takes either `yield` or `yield_` on the way in and always writes `yield`.

### Kinds of year

`yield` and `declared_margin` each hold exactly one value for each kind of year of `KINDS_OF_YEAR = ("el_nino", "neutral", "la_nina")`, a module constant that later units import. A kind of year left out, or one not in the list, is rejected.

## PROPOSED cases

Every case below is a change to the example, made in memory. The invalid ones must be rejected; the test also checks that each is rejected for the stated reason, both as Python data and as JSON text. The identifiers are the test identifiers in `test_examples.py`.

### Rejected: the record

| Case | The variant |
|---|---|
| `contract-of-another-name` | `contract` is `"field_identity"` |
| `example-data-as-text` | `example_data` is the text `"true"` |
| `case-id-blank` | `case_id` is only white space |
| `field-id-blank` | `field_id` is empty |
| `unknown-member-of-the-record` | The record carries a `margin`: no margin travels in this contract |
| `currency-other-than-usd` | `currency` is `"EUR"` |
| `record-without-a-crop` | `crops` is an empty list |
| `two-crops-share-one-identifier` | The cover crop has the `crop_id` of the grain crop |
| `crop-id-blank` | A `crop_id` is only white space |
| `crop-id-with-surrounding-white-space` | The cover crop's `crop_id` is the grain crop's with a space before and after |

### Rejected: units

| Case | The variant |
|---|---|
| `price-in-another-unit` | The price is in `USD kg-1` |
| `cost-in-another-unit` | The grain cost is in `USD/ha` |
| `cover-cost-in-another-unit` | The cover cost is in `USD ha-1 yr-1` |
| `yield-in-another-unit` | A yield is in `kg ha-1` |
| `declared-margin-in-another-unit` | A declared margin is in `USD ha-1` |

### Rejected: kinds of year

| Case | The variant |
|---|---|
| `yield-without-one-kind-of-year` | The yield has no `la_nina` |
| `yield-under-a-kind-of-year-not-in-the-list` | The yield has a `dry` member |
| `declared-margin-without-one-kind-of-year` | The declared margin has no `neutral` |

### Rejected: missing and provenance

| Case | The variant |
|---|---|
| `value-null-without-missing-part` | The price is null with no `missing` part (C3.1) |
| `value-present-without-provenance` | The price has a number and no provenance (C4.1) |
| `price-with-provenance-other-than-declared` | The price is labelled `OBSERVED`: every present value here is declared by the user |

### Rejected: signs

| Case | The variant |
|---|---|
| `price-negative` | The price is negative |
| `yield-negative` | A yield is negative |
| `cost-negative` | The grain cost is negative |
| `cover-cost-negative` | The cover cost is negative |
| `price-range-below-zero` | The price carries a range whose low bound is negative |

### Rejected: members by kind of crop

| Case | The variant |
|---|---|
| `grain-without-price` | The grain crop has no `price` |
| `grain-without-yield` | The grain crop has no `yield` |
| `grain-with-a-declared-margin` | The grain crop carries a `declared_margin` |
| `declared-margin-crop-with-a-price` | The pasture carries a `price` |
| `declared-margin-crop-with-a-yield` | The pasture carries a `yield` |
| `declared-margin-crop-with-a-cost` | The pasture carries a `cost`: its margin is read as net of cost (OPEN, question 5) |
| `cover-with-a-price` | The cover crop carries a `price` |
| `cover-with-a-yield` | The cover crop carries a `yield` |
| `cover-with-a-declared-margin` | The cover crop carries a `declared_margin` |
| `crop-kind-not-in-the-list` | A crop's `kind` is `"forage"` |

### Accepted

| Case | The variant |
|---|---|
| `accepted-price-missing-not-declared` | The price is null, missing `NOT_DECLARED`, its unit kept: a missing input is typed with its reason, never zero |
| `accepted-yield-in-one-kind-of-year-missing-not-declared` | The `la_nina` yield is missing `NOT_DECLARED` |
| `accepted-negative-declared-margin` | The `la_nina` declared margin is negative |
| `accepted-not-example-data` | `example_data` is false |
| `accepted-one-crop` | The record holds only the grain crop |
| `accepted-zero-price` | The price is zero: not negative, so accepted |
| `accepted-value-with-a-range` | The price carries a range instead of `range_missing` (C2.1); the range `kind` is a placeholder (C2.3 is OPEN) |

### Checked without a case of their own

- No required member can be left out: the test leaves out each member of the record, of each kind of crop, and each kind of year of `yield` and of `declared_margin`, in turn, and each variant is rejected at that member.
- The example holds exactly the members listed above, one crop of each kind, and `PLACEHOLDER` in every `crop_id`.
- The example dumped with `model_dump(mode="json")` validates back into an equal model.
- `GrainCrop` built with `yield_=` in Python is accepted and its JSON dump writes `yield`.
- `KINDS_OF_YEAR` is `("el_nino", "neutral", "la_nina")` and is the member list of `YieldByYear` and of `MarginByYear`.

## OPEN

Each item is a question a person has to answer.

1. **How is a year assigned to a kind of year?** The contract names `el_nino`, `neutral` and `la_nina` and nothing else: which index, which threshold and which source classify a year are not decided here. CITATION NEEDED. For the science reviewers.
2. **Other currencies.** `currency` accepts `"USD"` only, and the unit strings are written in `USD`. C1.1 lists `t`, `ha` and `yr` and does not list a currency; whether C1.1 gains `USD` (and others) is for the lead developer.
3. **Which crop's price is swept for the tipping price.** Not in this contract: it belongs to the route request of a later unit. For the platform developer.
4. **Signs and ranges.** A present price, cost or yield is rejected when negative, and so is a range of one whose low bound is negative; zero is accepted. Whether a zero price or yield is meaningful, and whether the non-negative rule on range bounds stands, is for the lead developer.
5. **Does a pasture carry a cost?** A `declared_margin` crop carries its margin only and rejects a `cost`, read as a margin net of cost. For the interface developer.
6. **Which `source` text marks a value the user declared?** The example writes `"user"`, as the brief of this unit proposes. For the lead developer.
7. **Relationship to the saved case and to the rotation definition.** Whether `crop_id` here must match a `crop_id` of the rotation definition of the same field is not checked. For the lead developer.
