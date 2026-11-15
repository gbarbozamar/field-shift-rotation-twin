# Water balance, one layer

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the lead developer, who owns lane L1 and decided the method (D44 of issue #77), and a science reviewer, because the order of the flows within a day and the form of the stress coefficient are science-class (blueprint section 3.6).

Status on `main` (15 November 2026): EP3 is built. `compute_water_deficit_exposure` is `engine/water/exposure.py` (#135, chained to runoff and `Ke` by #165); it imports this module and runs its balance day by day, with the `evaporation_coefficient` (`Ke`) of the surface-layer balance of `engine/water/evaporation/` (#151, brief #149), and `engine.water.daily_reference_evapotranspiration` is public beside EP3 (D256, #396; exercised on D128 rotations in `engine/water/test_d128_chain_invariants.py`, #459). In `params/records/water/`, 100 water records are signed (45 in #262, 43 for site, `soybean` and `no_crop` in #417, and 12 for `wheat` and `maize` in #446), including `column_capacity`, `column_depth`, `initial_storage`, and the `soybean` and `no_crop` records so the `soybean` with winter fallow rotation runs with the shipped catalogue, while 10 `wheat` and `maize` records still await signature (#433); signed means checked against the source (D34), not a validation of the method. `[H1]` (`test_h1_public_reference_case`, FAO-56 Chapter 8, Example 37; D228, tolerance D124) now runs on its signed fixture `validation/fixtures/h1_fao56_example37.json` (#455) and passed in the fourth recorded validation run (#463), with science-reviewer acceptance pending; `[H7]` (`test_h7_mass_closure_numeric_criterion`, D227) also runs and passes (#463), while `[H8]` (`test_h8_invariants_numeric_criteria`, D227) remains skipped. The sentences below that call EP3 or the surface-layer balance a later unit, or describe all water records as unsigned or `[H1]`/`[H7]` as skipped, describe the state when this folder landed; open science questions below remain open.

This folder holds the daily, continuous water balance of D44 in its **fallback form**: one column per field, one layer, the single bucket of FAO-56, rain-fed, no water table, no lateral exchange, never reset between crops or years. It is an internal part of the water engine; the entry point `compute_water_deficit_exposure` (EP3 of `contracts/ENTRYPOINTS.md`) is a later unit and is not here.

**The module holds no parameter value.** Capacity, column depth, initial storage, crop coefficients, root depths and readily available fractions are arguments with no default. The test enforces that `bucket.py` contains no number other than zero and one. Every number in `test_bucket.py` is a PLACEHOLDER, plainly not real; none comes from FAO-56 or any other source.

Acceptance test, from the repository root:

```bash
python -m pytest engine/water/balance/
```

Identifiers such as C3.2 refer to `contracts/CONVENTIONS.md`; EP3 and G1 to G7 refer to `contracts/ENTRYPOINTS.md`; H1, H7, H8 refer to `docs/VALIDATION.md`; D44 to D50 are decisions of the lead developer in issue #77.

## Layout

| Path | Content |
|---|---|
| `__init__.py` | Exports the public names below |
| `bucket.py` | `step`, `run_balance`, `stress_coefficient` and the records `CropDay`, `DayInput`, `DayResult` |
| `test_bucket.py` | The acceptance test |

`engine/water/__init__.py` is an empty file of zero bytes, so that `engine.water.balance` is one import path. The only contract model used is `Missing`, imported as `contracts.results.models.Missing` (the class EP3 names, not the one of `contracts/inputs/common.py`).

## Functions

```text
step(storage_start, day, *, capacity, column_depth) -> DayResult
run_balance(days, *, initial_storage, capacity, column_depth) -> list[DayResult]
stress_coefficient(depletion, available_capacity, readily_available_fraction) -> float
```

- `step` moves the balance of the column forward by one day.
- `run_balance` applies `step` to a sequence of consecutive days, carrying the storage at the end of each day to the start of the next.
- `stress_coefficient` is the form of the stress coefficient (PROPOSED, CITATION NEEDED).

All three are pure (G1): no file, no network, no clock, no global state; they do not change their arguments.

### Inputs

| Argument | What it is |
|---|---|
| `capacity` | The most water the column holds above its empty state, as a depth of water. Greater than zero |
| `column_depth` | The depth of soil the column covers, in the length unit of the root depths. Greater than zero |
| `initial_storage` / `storage_start` | Water in the column at the start of the first day / of this day, between zero and `capacity`, or `Missing` |
| `DayInput.date` | The day (C5.2). `run_balance` requires consecutive dates |
| `DayInput.precipitation`, `.runoff`, `.reference_evapotranspiration` | Depths of water over the day, or `Missing`. Runoff is an input in this unit |
| `DayInput.evaporation_coefficient` | The `Ke` of D44, supplied per day by the caller in this unit, or `Missing` |
| `DayInput.crop` | `None` on a day with no crop; a `CropDay`; or `Missing` when the crop of the day is not known |
| `CropDay.transpiration_coefficient` | The `Kcb` of D44 |
| `CropDay.root_depth` | Depth of the root zone that day, greater than zero, not greater than `column_depth` |
| `CropDay.readily_available_fraction` | The readily available fraction of D44, between zero and one |

Depths of water share one unit and lengths of soil share one unit, both chosen by the caller. The module converts nothing and holds no unit string.

### Output

One `DayResult` per day, with: `storage_start`, `storage_end`, the five flows `precipitation`, `runoff`, `evaporation`, `transpiration`, `drainage`, the demands `evaporation_demanded` and `transpiration_demanded`, `root_zone_depletion`, `stress_coefficient`, and the shortfalls `runoff_shortfall`, `evaporation_shortfall`, `transpiration_shortfall` (the part of a flow that was asked for and not supplied). Every quantity is a number or a `Missing` with its reason (C3.1).

## PROPOSED rules

These are the rules `bucket.py` implements. Each is PROPOSED; R1 to R3 restate D44 and the brief of issue #114, R4 to R9 are choices of this session that a person accepts or corrects.

| Rule | Statement |
|---|---|
| R1 | Mass closure every day: `storage_end − storage_start = P − Q − E − T − D` (D44) |
| R2 | The storage is never clipped. A flow that asks for more water than there is gets limited, and the part not supplied is recorded in its shortfall (D44, brief #114). Water above the capacity leaves as drainage |
| R3 | `ETa = (Ks · Kcb + Ke) · ET0` (D44): evaporation demanded is `Ke · ET0`; transpiration demanded is `Kcb · ET0`; transpiration asked is `Ks` times that |
| R4 | **One layer means the water is spread evenly over the column.** The root zone holds the share `root_depth / column_depth` of the column's water and of its capacity. So growing roots reach water already in the column and add none; sowing and harvest change no storage. See OPEN 1 |
| R5 | Order within a day: runoff leaves from the precipitation; the rest enters the column; evaporation is taken from the column; transpiration from what is then left in the root zone; drainage last, of what exceeds the capacity. See OPEN 2 |
| R6 | Runoff is limited to the precipitation of the same day. See OPEN 3 |
| R7 | The stress coefficient uses the depletion of the root zone at the **start** of the day. Form: one while depletion `Dr` is not above the readily available water `RAW = p · TAW`; otherwise `(TAW − Dr) / (TAW − RAW)`. `TAW` is the root zone's share of the capacity. Form PROPOSED, source CITATION NEEDED |
| R8 | A day with no crop: transpiration is zero; demanded transpiration, depletion, stress coefficient and transpiration shortfall are missing with reason `NOT_APPLICABLE` (C3.2); evaporation goes on |
| R9 | A missing input of a day, or a missing storage at its start, makes every quantity of that day missing with reason `MISSING_INPUT` and a detail naming the input and its own reason code (C3.3). The storage of the following days is then not known, so every later day is missing too, with a detail naming the first cause. Nothing is filled in (C3.4 is not decided) |
| R10 | Caller defects raise: `TypeError` for a wrong type; `ValueError` for a negative or non-finite number, a capacity or column depth of zero, a storage outside zero to capacity, a root depth of zero or above the column depth, a fraction above one, or days that are not consecutive. A missing value never raises |

A consequence of R4 and R7 that the reviewers should see: with the water spread evenly, the depletion of the root zone and its capacity scale with the same share, so **the stress coefficient does not depend on the root depth**. Root depth acts only through the water the root zone can give in a day (the limit of R2). The FAO-56 single bucket, as the session understands its structure, carries the depletion of the root zone from day to day while the root zone grows, which treats the newly reached soil as full; that gives a different answer. Which one is wanted is OPEN 1.

## PROPOSED cases

The identifier of a case is the name of its test function in `test_bucket.py` without `test_`, written with hyphens. Every input value is a PLACEHOLDER. Tolerances are of floating-point rounding only (a small multiple of machine epsilon times the size of the terms); they are not the tolerance of H7, which is OPEN.

### Mass closure (H7 structure)

| Case | What is checked |
|---|---|
| `mass-closure-every-day-on-a-long-series` | On a PLACEHOLDER series of twenty years (crops and fallow in turn, dry and wet days, storms that overfill the column, demands above the water there, runoff above the precipitation), `ΔS = P − Q − E − T − D` every day to floating-point precision |
| `the-long-series-reaches-every-branch-of-the-step` | That series has days with drainage, an empty column, limited runoff, limited evaporation, limited transpiration, a stress coefficient strictly between zero and one, and days with no crop, so closure is checked where it can break |
| `mass-closure-from-other-initial-states-and-series` | Closure on three more series, from an empty and from a full column |
| `balance-is-never-reset-between-days-crops-or-years` | Each day starts with the storage the day before ended with; two runs chained by their storage give exactly the days of one run |

### Bounds and limited outflows (D44 mass rule)

| Case | What is checked |
|---|---|
| `storage-never-below-zero-nor-above-capacity` | On the long series, every storage lies between zero and the capacity and every flow is not negative |
| `evaporation-asking-more-than-there-is-is-limited-and-recorded` | Evaporation is limited to the water there; the column ends at exactly zero; the shortfall is the difference |
| `transpiration-is-limited-to-the-water-of-the-root-zone` | Transpiration is limited to the root zone's share of the water; the shortfall is recorded |
| `runoff-asking-more-than-the-precipitation-is-limited-and-recorded` | Runoff is limited to the precipitation; the storage does not change; the shortfall is recorded |
| `flows-supplied-in-full-have-no-shortfall` | Shortfalls are zero when every flow is supplied |
| `limited-flows-on-the-long-series-add-up` | Evaporation plus its shortfall is the demand, every day |

### Drainage

| Case | What is checked |
|---|---|
| `water-above-capacity-leaves-as-drainage` | The excess over capacity is the drainage; the storage ends at the capacity |
| `no-drainage-below-capacity` | No drainage while the column is not full |
| `drainage-comes-after-the-outflows-of-the-day` | Evaporation of the day is taken before the excess drains (R5) |

### Days with no crop

| Case | What is checked |
|---|---|
| `a-day-with-no-crop-has-no-transpiration-and-keeps-evaporation` | Transpiration zero, evaporation `Ke · ET0`, and the crop quantities missing with `NOT_APPLICABLE` |

### Root zone, sowing and harvest (H8 structure)

| Case | What is checked |
|---|---|
| `growing-the-root-zone-adds-no-water` | Days with no flow and a growing root zone keep the storage exactly |
| `growing-the-root-zone-gives-access-to-water-already-there` | From the same storage, a deeper root zone can transpire more on a day whose demand exceeds the water there |
| `sowing-and-harvest-keep-the-stored-water` | Fallow, sowing, growth, harvest and a new sowing, with no flow, keep the storage exactly |

### Stress coefficient (form PROPOSED, source CITATION NEEDED)

| Case | What is checked |
|---|---|
| `actual-transpiration-is-demanded-times-stress-when-water-suffices` | Actual transpiration equals the stress coefficient times the demanded transpiration, at several depletions |
| `actual-transpiration-is-demanded-times-stress-on-the-long-series` | The same every crop day of the long series, transpiration plus its shortfall where the water ran out |
| `stress-coefficient-is-one-up-to-the-readily-available-water` | One while depletion is not above `RAW` |
| `stress-coefficient-falls-linearly-to-zero-beyond-it` | `(TAW − Dr) / (TAW − RAW)` beyond `RAW`, zero at `TAW` |
| `stress-coefficient-is-bounded-and-does-not-rise-with-depletion` | Between zero and one, never rising as depletion grows, for fractions zero, one and between |
| `stress-follows-the-depletion-of-the-root-zone-at-the-start-of-the-day` | The depletion and the coefficient of a day are those of its starting storage (R7) |
| `stress-coefficient-on-the-long-series-stays-within-bounds` | Between zero and one every crop day of the long series |

### Missing in, missing out (C3.1, C3.3)

| Case | What is checked |
|---|---|
| `a-missing-input-gives-missing-outputs-that-day-and-after` | For each daily input in turn, a missing value on one day makes that day and every later day wholly missing, `MISSING_INPUT`, with the date and the input's reason in the detail; earlier days are untouched; no day is dropped |
| `the-detail-names-the-missing-input` | The detail names each missing input and its reason |
| `a-missing-initial-storage-gives-every-day-missing` | A missing initial storage makes every day missing, naming it |
| `a-missing-storage-at-the-start-of-a-step-gives-a-missing-day` | `step` carries the detail of a missing starting storage |
| `missing-is-never-zero` | No missing quantity is written as zero |

### Caller defects, purity, no values

| Case | What is checked |
|---|---|
| `invalid-column-raises-value-error` | Capacity or column depth zero, negative or not finite |
| `initial-storage-outside-the-column-raises-value-error` | Negative, above the capacity, or not a number |
| `invalid-day-raises-value-error` | Negative daily inputs or coefficients; root depth zero or above the column; fraction above one |
| `wrong-types-raise-type-error` | A text or a boolean for a number, a text for a crop or a day |
| `days-that-are-not-consecutive-raise-value-error` | A gap, a step back, a repeated day |
| `an-empty-sequence-gives-no-days` | No day in, no day out |
| `same-arguments-give-the-same-result-and-are-not-changed` | G1 |
| `the-module-holds-no-number-other-than-zero-and-one` | `bucket.py` holds no parameter value |

### Skipped, waiting for people

| Case | What it waits for |
|---|---|
| `h1-public-reference-case` | H1: originally skipped waiting for the public reference case. **On `main`:** the signed fixture `validation/fixtures/h1_fao56_example37.json` (FAO-56 Chapter 8, Example 37; D228, tolerance D124) landed in `#455` (`checked_by` filled); `[H1]` ran and passed in the fourth recorded validation run (`#463`), with science-reviewer acceptance pending |
| `h7-mass-closure-numeric-criterion` | H7: originally skipped waiting for the closure check definition and tolerance. **On `main`:** defined by D227 (`docs/VALIDATION.md` H7) and now runs and passes (`#463`) |
| `h8-invariants-numeric-criteria` | H8: remains skipped on `main`; D227 defines `[H8]` as the 19 invariant test items listed in `docs/VALIDATION.md` H8, leaving whether to remove this placeholder test to the lead developer |

## OPEN

Each question names the role that answers it.

1. **How does the one layer meet a growing root zone?** R4 spreads the water evenly over a column of fixed depth, so root growth reaches water already there and adds none, and the stress coefficient does not depend on root depth. The alternative is the FAO-56 single bucket in which the root zone is the bucket and its depletion is carried while it grows (newly reached soil counted as full), which needs a store below the root zone to keep R1 exact. Which is wanted, and with which source? *Science reviewers; lead developer (D44).*
2. **Order of the flows within a day (R5)** and whether the stress coefficient uses the depletion at the start of the day (R7). *Science reviewers.*
3. **Runoff above the precipitation of the day (R6).** Limited to that precipitation, as here, or another rule? With the Curve Number unit runoff is computed from precipitation and this case may not arise. *Science reviewers.*
4. **Source of the form of the stress coefficient (R7).** CITATION NEEDED; a person confirms the form against the source of D44 and records it in `ATTRIBUTIONS.md`. *Science reviewers.*
5. **Initial states to compare.** The water module specification asks that at least two initial states be compared. Which ones (for example an empty and a full column, or a spin-up), and how a result reports the difference? `initial_storage` is an argument with no default. *Science reviewers.*
6. **Where evaporation is taken from.** In this unit evaporation comes from the whole column, with `Ke` given per day by the caller. The surface-layer balance of D44 that computes `Ke` and limits evaporation to the surface layer is a later unit. *Lead developer (lane L1 plan).* **Built:** `engine/water/evaporation/` computes `Ke` from the surface-layer balance (#151, brief #149), and EP3 (#135, chained by #165) gives it to this balance day by day; this module still takes `Ke` per day as an argument.
7. **The single-coefficient fallback.** D44 says the engine falls back to the single crop coefficient and one layer when the dual-coefficient parameters do not arrive. How a single `Kc` maps onto the two coefficients here (for example `Kcb = Kc`, `Ke = 0`), and how the result says that the fallback was used, is not decided. *Science reviewers; lead developer.*
8. **Which quantities feed the indicator.** C1.4 leaves open which quantities are "water transpired" and "water demanded" (for example `transpiration` and `transpiration_demanded`, or the stressed demand), which state the descriptive measures use, and whether days with no crop count. "Water available at the sowing of the next crop" (D50) can be read from `storage_end`, or from the root zone's share of it, once a person says which. *Science reviewers.*
9. **Gaps in a daily series.** R9 stops the balance at the first missing day, since no gap is filled until C3.4 supplies a method. Whether the balance may restart after a gap, and from which state, is not decided. *Science reviewers.*
10. **Root depth on a crop day must be greater than zero (R10).** Whether a crop with no root zone yet (sowing day) is allowed and what it transpires. *Science reviewers.*
11. **Which soil properties give `capacity` and `column_depth`** (D49: the table by soil group of the national soil map), how they arrive (D46, parameter catalogue, not agreed), and in which units. *Lead developer; platform developer (D46); science reviewers (D49).* **On `main`:** D46 and D56 landed in EP3 (`engine/water/exposure.py`), and `column_capacity`, `column_depth`, and `initial_storage` site records are signed in `params/records/water/` (`#417`); how soil properties generalize across other sites remains open.
12. **Daily output of the balance.** EP3 returns only the indicator list; no contract carries the daily series of `DayResult` (Q10 b of `contracts/ENTRYPOINTS.md`). *Lead developer; platform developer.*

## Not in this unit

Reference evapotranspiration (`engine/water/et0/`, another unit); the dual-coefficient split and the surface-layer evaporation balance; runoff by the Curve Number; several layers; the entry point `compute_water_deficit_exposure`; the indicator and the descriptive measures of C1.4 and D50; reading the parameter catalogue (D46).
