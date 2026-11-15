# Contract: carbon forcing

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until a person approves the pull request.

| Contract | Producer → consumers | Model | Example |
|---|---|---|---|
| `CarbonForcing` | Platform (L2a) → Engines (AMG, `engine/amg/`), Platform (L2b, RothC, `engine/rothc/`) | `models.CarbonForcing` | `examples/PLACEHOLDER_carbon_forcing.json` |

Purpose, from blueprint section 5: **the same inputs, climate and horizon for both carbon models.** One document per rotation of one field; the same object is given to `run_amg` (EP5) and to `run_rothc` (EP6) of `contracts/ENTRYPOINTS.md`.

**Decision D65 of issue #77** (lead developer, 14 November 2026): EP5 and EP6 keep the same arguments (`forcing` and `parameters`), and **the monthly soil-cover series and the starting state of the soil carbon travel inside this contract**, not as separate arguments. They are the parts `soil_cover` and `starting_state` below. Their fields are PROPOSED; which cover quantity and which pools they hold, with which identifiers and units, stay [OPEN](#open) (items 8 and 9).

This contract fixes **structure only**: which parts exist, what shape each takes, how an absence travels. It names no quantity a carbon model needs, no unit, no soil depth, no horizon, no cover category, no carbon pool and no rule for making a month or an agricultural year from the daily record. Each of those is under [OPEN](#open), with who answers it.

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
- `SoilProperty` of `site_soil_slope.py`: a `Value` with a `quantity` identifier. `StartingStateValue` has the same shape.
- `_SeriesItem` and `_SeriesHeader` of `site_climate.py`, for the annual series: an item that holds a number or a `missing` part, never both and never neither, and the header rules of `MonthlySeries`. Both are private names there; they are imported so the rules stay in one place, and lane L0 may make them public later.

Every model rejects unknown fields and does not coerce types: a number or a month written as text is rejected.

**Quantity identifiers** follow the pattern of `contracts/inputs/` (`QuantityId` of `common.py`, C1.1): lower case letters, digits and underscores, starting with a letter (`^[a-z][a-z0-9_]*$`). The same pattern is used for `origin`. The vocabulary of both is OPEN; the example uses `placeholder_…` identifiers.

## Fields (`models.py`)

All PROPOSED.

| Field | Type | Rule |
|---|---|---|
| `contract` | `"carbon_forcing"` | Required. Names the document, as the `contract` field of the input contracts does |
| `example_data` | true or false | Required |
| `case_id`, `field_id`, `rotation_id` | text | Required, not empty. As in `contracts/results/`, so a carbon balance can be matched to its rotation. The field identity contract (decision D19 of issue #77) will replace `field_id` when it exists |
| `horizon` | `ForcingHorizon` | Required. `start` and `end`, each a `YearMonth` (`year`, `month` 1 to 12, C5.1), inclusive. The end is not before the start. Its value is OPEN (C1.6) |
| `soil_depth` | `Value` | Required. A number with its unit, or missing with its reason, keeping its unit. Both models refer to this one depth (C1.6). Its value and unit are OPEN |
| `climate` | list of `ClimateSeries` | The shape of `MonthlySeries`, unchanged. Each series runs over exactly the months of the horizon: `start` and `end` equal those of `horizon`, one item per month, in order, no gap, no duplicate. A `quantity` appears at most once in the list. A month without data stays in the series, missing with its reason, never zero |
| `carbon_inputs` | list of `CarbonInputSeries` | As `climate`, and each series also carries `origin`: an identifier of what it is taken from (for example the residue ledger). `origin` is not the data reference of C4.2, which stays in `source` |
| `annual_climate` | list of `AnnualSeries` | Required key; an empty list is allowed. The header of `MonthlySeries` (quantity, unit kept when values are missing, provenance, source or assumption mark, `range_missing`), then `first_ag_year`, `last_ag_year` (inclusive) and `years`: one `AnnualValue` (`ag_year`, then a number or missing with its reason) per agricultural year from first to last, in order, no gap, no duplicate. `ag_year` is the calendar year in which the agricultural year begins (C5.3). A `quantity` appears at most once in the list |
| `annual_carbon_inputs` | list of `AnnualCarbonInputSeries` | As `annual_climate`, and each series also carries `origin`, as `carbon_inputs` does |
| `soil_properties` | list of `SoilProperty` | As `SiteSoilSlope.soil_properties`. A `quantity` appears at most once in the list |
| `soil_cover` | list of `SoilCoverSeries` | Required key; an empty list is allowed. The monthly soil-cover series (D65). The shape of `MonthlySeries`, unchanged, with the rules of `climate`: each series runs over exactly the months of the horizon, one item per month, a month without data stays in the series missing with its reason, never zero, and a `quantity` appears at most once in the list. Which cover quantity, how cover is written as a number and in which unit are OPEN (item 8) |
| `starting_state` | list of `StartingStateValue` | Required key; an empty list is allowed. The starting state of the soil carbon (D65): each item is a `Value` with a `quantity` identifier, as a soil property is: a number with its unit, provenance, source or assumption mark and range (or the reason it has none), or missing with its reason, keeping its unit. A `quantity` appears at most once in the list. PROPOSED: it is the state at the beginning of the first month of the horizon. Which pools, identifiers and units are OPEN (item 9) |

A `quantity` identifier is unique within each list; the same identifier may appear in two different lists (PROPOSED).

**Annual series and the horizon.** When at least one annual series is present, the horizon is a whole number of agricultural years: its number of months is a multiple of 12 (C5.3: twelve consecutive months from the start month). Every annual series then runs from `first_ag_year` equal to the year of `horizon.start` to `last_ag_year` equal to the calendar year in which the last agricultural year of the horizon begins. With no annual series there is no such rule: the horizon may be any months. The model takes `horizon.start` as the first month of an agricultural year; it cannot check that against the start month of the case (C5.4), which the forcing does not carry.

How an annual value is made from the monthly values or from the daily record, and what a year with missing months becomes, are OPEN (item 8). C5.5 says only that an agricultural year the data does not cover in full is not reported as a full year: its yearly value is missing with reason `NO_COVERAGE`.

Each monthly series repeats `start` and `end`, which must equal the horizon. That is the shape of `MonthlySeries` reused as it is; the repetition lets a consumer read a series on its own.

An empty `soil_cover` or `starting_state` names no value, so it carries no reason. A carbon engine that needs a quantity the list does not hold answers by G4 of `contracts/ENTRYPOINTS.md`: the result is missing with reason `MISSING_INPUT`, and `detail` names the quantity. The same holds for `climate` and `soil_properties`.

## Left out, and why

- **The state at the end of the horizon.** Whether a carbon engine also returns its final state, inside `CarbonBalance`, is the rest of Q14 (a) of `contracts/ENTRYPOINTS.md`. Blueprint section 5 names a `ModelState` contract ("same starting soil carbon across models"); whether it later takes over the shape of `starting_state` is OPEN (item 9).
- **Any parameter of one model.** Model parameters come from the parameter catalogue of `params/`, passed to the engines by the runner (decision D46 of issue #77), not in the forcing.

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
| `contract-left-out` | No `contract` |
| `contract-of-another-document` | `contract` names another document |
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
| `annual-climate-left-out` | No `annual_climate` key |
| `annual-carbon-inputs-left-out` | No `annual_carbon_inputs` key |
| `annual-year-gap` | An annual series skips an agricultural year |
| `annual-duplicate-year` | An agricultural year appears twice in an annual series |
| `annual-year-out-of-order` | Two agricultural years of an annual series are swapped |
| `annual-series-one-year-short` | An annual series keeps its years and its `last_ag_year` is one year later |
| `annual-series-ends-before-it-starts` | `last_ag_year` is before `first_ag_year` |
| `annual-series-beyond-horizon` | An annual series, consistent in itself, runs one agricultural year past the horizon |
| `annual-carbon-inputs-not-the-horizon-years` | An annual carbon-input series, consistent in itself, is shifted by one agricultural year |
| `annual-series-with-horizon-not-whole-years` | The horizon and the monthly series lose one month (eleven months) while annual series are present |
| `duplicate-annual-quantity` | Two annual climate series share one `quantity` |
| `annual-missing-year-without-reason` | A missing agricultural year loses its `missing` part (C3.1) |
| `annual-missing-year-written-as-zero` | A missing agricultural year keeps its `missing` part and its value is zero (C3.1) |
| `annual-year-written-as-text` | An `ag_year` written as text |
| `annual-carbon-inputs-origin-left-out` | An annual series of carbon inputs without `origin` |
| `soil-cover-left-out` | No `soil_cover` key |
| `starting-state-left-out` | No `starting_state` key |
| `unknown-field-in-soil-cover` | A part the contract does not name, in a soil-cover series |
| `unknown-field-in-starting-state` | A part the contract does not name, in a starting value |
| `soil-cover-shorter-than-horizon` | A soil-cover series, consistent in itself, ends one month before the horizon |
| `soil-cover-one-month-short` | A soil-cover series loses its last month and keeps its `end` |
| `duplicate-soil-cover-quantity` | Two soil-cover series share one `quantity` |
| `soil-cover-without-unit` | A soil-cover series has no `unit` (C1.1) |
| `soil-cover-value-written-as-text` | A soil-cover value written as text |
| `soil-cover-missing-month-without-reason` | A missing soil-cover month loses its `missing` part (C3.1) |
| `soil-cover-missing-month-written-as-zero` | A missing soil-cover month keeps its `missing` part and its value is zero (C3.1) |
| `duplicate-starting-state-quantity` | Two starting values share one `quantity` |
| `starting-state-quantity-left-out` | A starting value without `quantity` |
| `starting-state-quantity-not-an-identifier` | The `quantity` of a starting value in upper case |
| `starting-state-number-written-as-text` | A starting value written as text |
| `starting-state-without-source` | A present starting value loses its `source` and has no assumption mark (C4.2) |
| `missing-starting-state-written-as-zero` | The missing starting value keeps its `missing` part and its value is zero (C3.1) |
| `missing-starting-state-without-reason` | The missing starting value loses its `missing` part (C3.1) |
| `missing-starting-state-without-unit` | The missing starting value loses its unit (C3.1) |

### Accepted

| Case | The variant |
|---|---|
| `series-all-months-missing-keeps-unit` | Every month of a series is missing; the series keeps its unit and carries no provenance, source or range reason |
| `zero-is-a-real-value` | A month holds zero with no `missing` part |
| `empty-lists` | No monthly climate series, no monthly carbon input series, no soil property |
| `empty-annual-lists-with-horizon-not-whole-years` | A horizon of four months with its monthly series, and both annual lists empty |
| `empty-annual-lists-with-whole-year-horizon` | Both annual lists empty, horizon of twelve months |
| `same-quantity-in-two-lists` | A carbon input series uses the `quantity` of a climate series |
| `empty-soil-cover-and-starting-state` | No soil-cover series and no starting value |
| `soil-cover-all-months-missing-keeps-unit` | Every month of the soil-cover series is missing; the series keeps its unit and carries no provenance, source or range reason |
| `soil-cover-zero-is-a-real-value` | A soil-cover month holds zero with no `missing` part |

## OPEN

Each item is a question a person has to answer. Until then the model keeps the generic shape above.

1. **Which climate quantities does each carbon model need, by month, with which identifier and unit?** For the science reviewers; the AMG lane (L1) and the RothC lane (L2b) as consumers. Input for RothC: the interface developer transcribed the nine data the RothC users guide of 2014 requires (pp. 6-8) on [#176](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/176#issuecomment-6884985528), with his reading as consumer, not a decision, of where each lives: monthly rainfall, open-pan evaporation and mean air temperature in `climate`; plant residues and farmyard manure in `carbon_inputs`, with two origins; clay content in `soil_properties`; soil cover, bare or vegetated per month, in `soil_cover` (item 8); the depth of the soil layer sampled in `soil_depth`; the decomposability ratio of incoming plant material is model guidance, not forcing data. No identifier, unit or category is taken from that list until a person decides it.
2. **How is a monthly value made from the daily record of `SiteClimate` (sum, mean or other, per quantity), and what does a month with missing days become?** C3.4 decides that gaps may be filled by a method a person chooses; the method is OPEN there. For the science reviewers.
3. **Which soil depth, in which unit, and which horizon?** The OPEN item of C1.6. Also whether the horizon must start and end on agricultural-year boundaries when no annual series is present, and whether `horizon.start` must be the start month of the case (C5.3, C5.4). Related and decided: the agricultural years a result lists are every agricultural year of the climate record, 2001-01-01 to 2024-12-31 (D29 of #77), cut by the start month of the case (D47 of #77, `contracts/ENTRYPOINTS.md` Q5); whether the forcing horizon must equal those years is not decided. For the science reviewers.
4. **Q14 of `contracts/ENTRYPOINTS.md`, as far as it touches this contract.** (a) Does the starting soil carbon (`ModelState`) travel beside the forcing or in it? **Decided by D65 of #77: in it** (`starting_state`); what it holds is item 9. (b) Do the carbon engines take `ResidueLedger` as an argument, or does `carbon_inputs` hold what comes from it, and which identifiers can `origin` take? (c) Nothing in this contract depends on who computes `soil_carbon_trend`. (d) The contract now carries both monthly and annual series (`annual_climate`, `annual_carbon_inputs`); which one each variant of AMG reads, and how each result is labelled, is for the lead developer. For the lead developer, the interface developer and the platform developer.
5. **Which soil properties do both models share, with which identifier and unit?** For the science reviewers.
6. **The producer function.** **Built on `main`: `api/carbon_forcing.py`, `build_carbon_forcing`, since #219 (lane L2a, D118 to D123), with #242, #350, #371 and #431 (`9f6c2a7`).** The runner (`api/engines.py`) calls it once per phase, when a configured carbon engine (EP5 or EP6) is built, from the phase's `RotationCalendar`, the `SiteClimate`, the `SiteSoilSlope`, the residue ledger of EP4, the daily FAO-56 reference evapotranspiration of D44 that the runner computes, and the monthly live-crop counts for `soil_cover` (`live_crop_months_for_forcing` via `engine.water.living_crop.live_crop_by_day`, #423, `f389980`); EP5 and EP6 receive the same forcing (D65). What it writes, as `api/README.md` ("The producer of CarbonForcing") states in full:
   - the horizon: the whole agricultural years of the climate record, cut by the calendar's start month (D47, D29);
   - `annual_climate`: `mean_temperature` (D118) and `water_balance` (D181, #371: precipitation minus ET0 over each agricultural year, in `m`);
   - `annual_carbon_inputs`: the series of the residue ledger, copied unchanged (#242, D147); without a ledger, one all-missing series per crop (D122);
   - `climate` (monthly rainfall, potential evapotranspiration and mean temperature, D220), `soil_depth` (20 `cm`, D180) and `carbon_inputs` (the monthly series of the ledger, D221), all by #350;
   - `soil_cover` (D222, #431, `9f6c2a7`, brief #373): one `SoilCoverSeries` (`soil_cover_state`, unit `dimensionless`). The runner counts each month's days with a live crop using `engine.water.living_crop.live_crop_by_day` (#423, `f389980`) on the phase's repeated calendar over the record period (with the catalogue unchanged and no climate value read), and `api/carbon_forcing.py` (`soil_cover_series`) writes `1.0` when more than half of the month's days have a living crop and `0.0` otherwise, including the fallow under residue (an exact tie is `0.0`); months with a day whose live status is not known keep that day's reason (`C3.3`, `C3.4`), months with no count are `NO_COVERAGE`, and when no counts are passed every month is `NOT_AVAILABLE` (never zero);
   - `soil_properties` (D120; `soil_cn_ratio`, D193) and `starting_state` (`soil_organic_carbon`, D121): copied unchanged from the site file when it carries them (and `soil_organic_carbon` is in the stock unit; another unit is `NOT_COMPUTABLE`), otherwise missing with the decision named. EP6 derives its pools from that total by the inverse mode of D218 (#339).
   **Still open:** The site values of the starting carbon and the soil properties enter the site file only once a person has signed them, so today those parts are missing. Nothing here means that AMG or RothC gives a number: their records wait for a person's signature (D34, D66). *As first written:* Where in `adapters/` or `api/` the forcing is built from `SiteClimate`, `SiteSoilSlope` and the residue ledger, and when it is called. Also what `soil_cover` and `starting_state` are built from, and by whom. For the platform developer, in a later unit.
7. **How is an annual value made from the monthly values or from the daily record (per quantity), and what does an agricultural year with missing months become?** C5.5 decides only that a year the data does not cover in full is missing with reason `NO_COVERAGE`. Which annual quantities each model needs, with which identifier and unit, is part of the same question. For the science reviewers.
8. **The monthly soil-cover series (for example vegetated or bare, which the rate modifiers of RothC use).** Raised by the interface developer as RothC consumer on the pull request of this contract. **Where it lives is decided by D65 of #77: inside the forcing**, not as an argument of EP6; this unit PROPOSES a list of its own, `soil_cover`, in the shape of `MonthlySeries`. The interface developer reads the RothC guide as asking whether the soil is bare or vegetated in each month ([#176](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/176#issuecomment-6884985528), item 6 of the nine data; see item 1). That reading is a category per month; the numeric shape here holds it only once a person decides how a category is written as a number, or replaces the shape (second point below). Still OPEN:
   - which cover categories or quantity, with which identifier: for the science reviewers; the interface developer for RothC, the lead developer for AMG;
   - how cover is written as a number (for example a fraction, or one number per category) and in which unit, or whether it needs a shape other than a number (a category per month), which would change `SoilCoverSeries`: for the same roles;
   - whether AMG reads it at all: for the lead developer.
9. **The starting state of the soil carbon (`starting_state`, D65 of #77).** Still OPEN:
   - which pools or quantities it holds (one total stock shared by both models, the pools of each model, or both), with which identifiers and units, and for which soil depth (C1.6): for the science reviewers; the interface developer for RothC, the lead developer for AMG;
   - how it is obtained (measured, declared, or computed before the horizon) and with which provenance label: for the science reviewers;
   - whether it is the state at the beginning of the first month of the horizon, as PROPOSED here, or needs a date of its own: for the lead developer and the interface developer;
   - whether the `ModelState` contract of blueprint section 5 later takes over the shape of `StartingStateValue`, and whether a model also returns its final state (Q14 (a) of `contracts/ENTRYPOINTS.md`): for the lead developer.
