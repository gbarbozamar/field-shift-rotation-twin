# Contract: carbon forcing

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until a person approves the pull request.

| Contract | Producer → consumers | Model | Example |
|---|---|---|---|
| `CarbonForcing` | Platform (L2a) → Engines (AMG, `engine/amg/`), Platform (L2b, RothC, `engine/rothc/`) | `models.CarbonForcing` | `examples/PLACEHOLDER_carbon_forcing.json` |

Purpose, from blueprint section 5: **the same inputs, climate and horizon for both carbon models.** One document per rotation of one field; the same object is given to `run_amg` (EP5) and to `run_rothc` (EP6) of `contracts/ENTRYPOINTS.md`.

This contract fixes **structure only**: which parts exist, what shape each takes, how an absence travels. It names no quantity a carbon model needs, no unit, no soil depth, no horizon and no rule for making a month from the daily record. Each of those is under [OPEN](#open), with who answers it.

**The example is PLACEHOLDER data.** Every number, identifier, unit string and source string in it is illustrative. It describes no real place, field or producer, and says `"example_data": true`. Its identifiers are those of the input examples (`PLACEHOLDER-case`, `PLACEHOLDER-field`, `PLACEHOLDER-rotation`), since a forcing is built from those inputs.

Acceptance test, from the repository root:

```bash
uv run pytest contracts/carbon_forcing/
```

Models and pure validation only. No network calls, no parameter values, no thresholds, no citations.

## Shared parts, reused

The model imports, and does not copy, the shared parts of `contracts/inputs/` (see `contracts/inputs/README.md` for their rules):

- `Value` and `Missing` of `common.py`: a number with its unit, provenance, source or assumption mark and range (or the reason it has none); or missing with its reason, keeping its unit (C1.1, C2, C3, C4).
- `MonthlySeries` and `YearMonth` of `site_climate.py`: a series with a `quantity` identifier, its unit once for the series (kept when values are missing), provenance, source or assumption mark, `range_missing`, a `start` and `end` month, and one item per calendar month with its `year` (C5.1), each a number or missing with its reason.
- `SoilProperty` of `site_soil_slope.py`: a `Value` with a `quantity` identifier.

Every model rejects unknown fields and does not coerce types: a number or a month written as text is rejected.

**Quantity identifiers** follow the pattern of `contracts/inputs/` (`QuantityId` of `common.py`, C1.1): lower case letters, digits and underscores, starting with a letter (`^[a-z][a-z0-9_]*$`). The same pattern is used for `origin`. The vocabulary of both is OPEN; the example uses `placeholder_…` identifiers.

## Fields (`models.py`)

All PROPOSED.

| Field | Type | Rule |
|---|---|---|
| `example_data` | true or false | Required |
| `case_id`, `field_id`, `rotation_id` | text | Required, not empty. As in `contracts/results/`, so a carbon balance can be matched to its rotation. The field identity contract (decision D19 of issue #77) will replace `field_id` when it exists |
| `horizon` | `ForcingHorizon` | Required. `start` and `end`, each a `YearMonth` (`year`, `month` 1 to 12, C5.1), inclusive. The end is not before the start. Its value is OPEN (C1.6) |
| `soil_depth` | `Value` | Required. A number with its unit, or missing with its reason, keeping its unit. Both models refer to this one depth (C1.6). Its value and unit are OPEN |
| `climate` | list of `ClimateSeries` | The shape of `MonthlySeries`, unchanged. Each series runs over exactly the months of the horizon: `start` and `end` equal those of `horizon`, one item per month, in order, no gap, no duplicate. A `quantity` appears at most once in the list. A month without data stays in the series, missing with its reason, never zero |
| `carbon_inputs` | list of `CarbonInputSeries` | As `climate`, and each series also carries `origin`: an identifier of what it is taken from (for example the residue ledger). `origin` is not the data reference of C4.2, which stays in `source` |
| `soil_properties` | list of `SoilProperty` | As `SiteSoilSlope.soil_properties`. A `quantity` appears at most once in the list |

A `quantity` identifier is unique within each list; the same identifier may appear in two different lists (PROPOSED).

Each monthly series repeats `start` and `end`, which must equal the horizon. That is the shape of `MonthlySeries` reused as it is; the repetition lets a consumer read a series on its own.

## Left out, and why

- **The starting soil carbon.** It belongs to `ModelState` ("same starting soil carbon across models", blueprint section 5). Whether it is an argument of the carbon engines, part of what they return, or both is Q14 (a) of `contracts/ENTRYPOINTS.md`.
- **Any annual aggregate.** Whether the annual reference of AMG (blueprint section 8) takes its own annual forcing or aggregates the monthly one is Q14 (d). Until it is answered, the forcing holds monthly series only.
- **Any parameter of one model.** Model parameters come from the parameter catalogue of `params/`, passed to the engines by the runner (decision D46 of issue #77), not in the forcing.
- **A `contract` discriminator** such as the `contract` field of the input contracts. Not in the field list of this unit; proposed under OPEN.

## PROPOSED cases

Every case below is a change to the example. The invalid ones must be rejected for the stated reason; the identifiers are the test identifiers in `test_examples.py`.

**Limit of the case "a missing month written as zero".** Zero is a real value of a series. What the model rejects is an item that holds a number together with a `missing` part, an item that holds neither, and a month left out. Keeping a gap from becoming a bare zero is the duty of the producer and has to be tested there.

### Rejected

| Case | The variant |
|---|---|
| `unknown-field` | A part the contract does not name, at the top level |
| `unknown-field-in-series` | A part the contract does not name, in a climate series |
| `number-written-as-text` | A monthly value written as text |
| `soil-depth-number-written-as-text` | The soil depth written as text |
| `month-written-as-text` | A month of the horizon written as text |
| `example-data-left-out` | No `example_data` |
| `horizon-left-out` | No `horizon` |
| `soil-depth-left-out` | No `soil_depth` |
| `series-one-month-short` | A series loses its last month and keeps its `end` |
| `series-shorter-than-horizon` | A series, consistent in itself, ends one month before the horizon |
| `carbon-inputs-shorter-than-horizon` | The same for a series of carbon inputs |
| `duplicate-month` | A month appears twice in a series |
| `month-out-of-order` | Two months of a series are swapped |
| `duplicate-climate-quantity` | Two climate series share one `quantity` |
| `duplicate-soil-property-quantity` | Two soil properties share one `quantity` |
| `quantity-not-an-identifier` | A `quantity` in upper case |
| `origin-left-out` | A series of carbon inputs without `origin` |
| `missing-month-written-as-zero` | A missing month keeps its `missing` part and its value is zero (C3.1) |
| `missing-month-without-reason` | A missing month loses its `missing` part (C3.1) |
| `missing-soil-depth-written-as-zero` | The missing soil depth keeps its `missing` part and its value is zero (C3.1) |
| `missing-soil-depth-without-unit` | The missing soil depth loses its unit (C3.1) |
| `series-without-unit` | A series has no `unit` (C1.1) |
| `horizon-ends-before-it-starts` | The end of the horizon is before its start |

### Accepted

| Case | The variant |
|---|---|
| `series-all-months-missing-keeps-unit` | Every month of a series is missing; the series keeps its unit and carries no provenance, source or range reason |
| `zero-is-a-real-value` | A month holds zero with no `missing` part |
| `empty-lists` | No climate series, no carbon input series, no soil property |
| `same-quantity-in-two-lists` | A carbon input series uses the `quantity` of a climate series |

## OPEN

Each item is a question a person has to answer. Until then the model keeps the generic shape above.

1. **Which climate quantities does each carbon model need, by month, with which identifier and unit?** For the science reviewers; the AMG lane (L1) and the RothC lane (L2b) as consumers.
2. **How is a monthly value made from the daily record of `SiteClimate` (sum, mean or other, per quantity), and what does a month with missing days become?** C3.4 decides that gaps may be filled by a method a person chooses; the method is OPEN there. For the science reviewers.
3. **Which soil depth, in which unit, and which horizon?** The OPEN item of C1.6. Also whether the horizon must start and end on agricultural-year boundaries (C5.3, C5.4). For the science reviewers.
4. **Q14 of `contracts/ENTRYPOINTS.md`, as far as it touches this contract.** (a) Does the starting soil carbon (`ModelState`) travel beside the forcing or in it? (b) Do the carbon engines take `ResidueLedger` as an argument, or does `carbon_inputs` hold what comes from it, and which identifiers can `origin` take? (c) Nothing in this contract depends on who computes `soil_carbon_trend`. (d) Does the annual variant of AMG need an annual forcing, or does it aggregate the monthly one? For the lead developer, the interface developer and the platform developer.
5. **Which soil properties do both models share, with which identifier and unit?** For the science reviewers.
6. **The producer function.** Where in `adapters/` or `api/` the forcing is built from `SiteClimate`, `SiteSoilSlope` and the residue ledger, and when it is called. For the platform developer, in a later unit.
7. **Does the document carry a `contract` discriminator** (`"contract": "carbon_forcing"`), as the input contracts do? For the platform developer.
