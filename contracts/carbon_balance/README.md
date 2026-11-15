# Contract "CarbonBalance"

Unit `l1/amg-ep5`, brief in issue #192. Status: `PROPOSED` (blueprint section 3.7). It takes effect only when a person approves the pull request. Producers: Engines (`engine/amg/`, EP5) and Platform, sub-lane L2b (`engine/rothc/`, EP6). Consumers: the runner (`api/`) and the interface. **It needs the acceptance of the platform developer and of the interface developer.**

**Current status on `main` (`b107d7a`):** Both producers, EP4, and the runner are built and wired on `main`: EP5 `run_amg` (`engine/amg/entry.py`, `#305` `78e1305` for D192–D199, `#330` `9551055` for D210), EP6 `run_rothc` (`engine/rothc/entry.py`, `#247` `eb1dd39`, `#339` `ea7d2bc` for D218–D224; `PROPOSED` in `contracts/ENTRYPOINTS.md` matching `engine/rothc/README.md`), EP4 `build_residue_ledger` (`engine/residues/ledger.py`, `#235`, `#306` D194, `#334` D221), and the runner `api/engines.py` / `api/carbon_forcing.py` (`#219` `a6575c5`, `#242`, `#282` `994978e`, `#350` `09e2a47`, `#371` `c605a74`, `#409` `8097065`, `#412` `2baae0a` for D256 `daily_reference_evapotranspiration`, and `#431` `9f6c2a7` for D222 monthly `soil_cover` via `#423` `f389980` `live_crop_by_day`), which passes one `CarbonForcing` to both engines and copies `soil_carbon_trend` unchanged into `ResultsPerRotation`. Outside `EP1`–`EP6` and `api/engines.py`, `engine/amg/monthly_entry.py` (`run_amg_monthly`, `#477`, `#467`) also returns `CarbonBalance` as a standalone `PROPOSED` experimental AMG-M helper (D80). `params/records/residues/` holds 6 signed residue records; the remaining 5 residue parameters and all AMG and RothC parameter records still wait for a person's signature (D34, D66), and the contract remains `PROPOSED` until formal acceptance.

What one carbon model returns for one rotation of one field (blueprint section 5): the carbon stocks over the horizon, the carbon flows of each step, and the three trend values of C1.6 for `soil_carbon_trend`. EP5 `run_amg` and EP6 `run_rothc` both return it (contracts/ENTRYPOINTS.md: "EP5 and EP6 also have the same return type").

This folder fixes structure only. It names no pool, no flow, no unit of a carbon model and no value. The model is `models.py`; the example is `examples/PLACEHOLDER_carbon_balance.json`, whose numbers mean nothing.

## Fields

| Field | Shape | Notes |
|---|---|---|
| `contract` | `"carbon_balance"` | As `"carbon_forcing"` |
| `example_data` | boolean | Copied from the forcing by the engine |
| `case_id`, `field_id`, `rotation_id` | non-empty text | Those of the forcing |
| `carbon_model` | `"amg"` or `"rothc"` | `CarbonModel` of `contracts/results/models.py` (D1 of #77) |
| `variant` | identifier (lower case, underscores) | PROPOSED label of the variant (Q14 (d)); vocabulary OPEN 2 |
| `horizon` | `ForcingHorizon` of `contracts/carbon_forcing/` | The horizon of the forcing, unchanged |
| `soil_depth` | `Value` of `contracts/inputs/common.py` | The soil depth of the forcing, unchanged: the depth the stocks refer to (C1.6) |
| `total_stock` | `StockSeries` | The total soil carbon of the model |
| `pools` | list of `StockSeries` | The pools of the model, one series each; identifiers and units OPEN 3 |
| `flows` | list of `FlowSeries` | The flows of each step (for example carbon entering, carbon mineralised); identifiers and units OPEN 3 |
| `soil_carbon_trend` | list of `SoilCarbonTrend` of `contracts/results/models.py` | The three computations of C1.6, once each, all naming `carbon_model` |

`StockSeries` and `FlowSeries` carry the header of a monthly series of `contracts/inputs/site_climate.py`, unchanged: `quantity`, `unit` (kept when values are missing), `provenance`, `source` or `assumption`, `range_missing`. Then:

- `FlowSeries.steps`: one `StepValue` per step, in order, with no gap and no overlap. A `StepValue` is a number or missing with its reason (the series item of `SiteClimate`), with `start` and `end`, the first and last month of the step, inclusive (C5.1). An annual step covers twelve months (one agricultural year, C5.3); a monthly step covers one month. For a flow, the value is the amount over the step.
- `StockSeries` adds `initial`, the stock at the start of the horizon, a `Value` with its own provenance, source and range (or reason), in the unit of the series. Each value of `steps` is the stock at the end of that step.

## Rules the model checks

- Every series (total, pools, flows) has the same steps as `total_stock`, and they run from the first month of the horizon to its last.
- No quantity identifier appears twice among `total_stock`, `pools` and `flows`.
- `initial` is in the unit of its series.
- `soil_carbon_trend` carries `end_minus_start`, `fitted_slope` and `mean_over_cycles` once each, every one naming the `carbon_model` of the balance: values of two models are never merged (C1.5). Each value follows `SoilCarbonTrend`: unit `t C ha-1 yr-1`, direction `higher_is_better`, a number with provenance, source and range (or reason), or missing with its reason.
- Everything the shared parts already check: a value or a missing part, never both, never neither (C3.1); a present value carries a provenance label and a source or the assumption mark (C4.1, C4.2) and a range or the reason it has none (C2.2); unknown fields are rejected and nothing is coerced.

Not checked here, because it is a statement of a model and not of the shape: that the total is the sum of the pools, and that the change of a stock over a step equals what entered minus what left (mass balance). The AMG engine checks both in its tests.

## PROPOSED cases

Each case is a test function of `test_examples.py`; a test checks that this list and the file agree.

| Case | What it shows |
|---|---|
| `test_example_loads` | The PLACEHOLDER example loads |
| `test_example_round_trips_through_json` | `model_dump(mode="json")` loads back into an equal model |
| `test_monthly_steps_load_for_the_other_carbon_model` | One step per month and carbon model `rothc`: the shape of EP6 loads |
| `test_every_value_missing_loads` | A balance in which every value is missing with its reason is valid |
| `test_steps_that_do_not_cover_the_horizon_are_rejected` | Steps that stop before the end of the horizon |
| `test_steps_with_a_gap_are_rejected` | A month between two steps |
| `test_series_with_other_steps_than_the_total_are_rejected` | A pool with other steps than the total |
| `test_step_that_ends_before_it_starts_is_rejected` | A step whose end is before its start |
| `test_repeated_quantity_is_rejected` | A flow with the identifier of a pool |
| `test_initial_in_another_unit_is_rejected` | An initial stock in another unit than its series |
| `test_trend_without_each_computation_once_is_rejected` | A computation absent, or one given twice |
| `test_trend_of_another_carbon_model_is_rejected` | A trend value naming the other model |
| `test_trend_in_another_unit_is_rejected` | A trend value not in `t C ha-1 yr-1` |
| `test_missing_step_without_reason_or_with_a_number_is_rejected` | A step without a value or a reason, or with both |
| `test_present_values_without_provenance_or_range_reason_are_rejected` | A series with values and no provenance, or no reason for the absent range |
| `test_unknown_field_and_unknown_carbon_model_are_rejected` | An unknown field; a carbon model that is not `amg` or `rothc` |
| `test_series_without_steps_is_rejected` | A series with no step |
| `test_readme_lists_the_cases_of_this_file` | This list and the file name the same cases |

## OPEN

Each item is a question a person answers; the role is named.

1. **Acceptance of the shape.** The field list above, the names `total_stock`, `pools`, `flows`, `StepValue` and its `start` and `end`, and the choice of one step list for annual and monthly models. For the platform developer (the runner consumes it) and the interface developer (the interface consumes it; EP6 produces it).
2. **The vocabulary of `variant`** (Q14 (d) of contracts/ENTRYPOINTS.md). `engine/amg/` writes `amg_a` for AMG-A, the annual reference of D80. Whether AMG-M, which is experimental and casts no carbon vote (D80), is a second `CarbonBalance` with another variant, and what RothC writes (for example for standard RothC, the reference of D80). **On `main`:** `engine/rothc/entry.py` (`#247`, `eb1dd39`) writes `rothc_26_3` (`PROPOSED`); the vocabulary and AMG-M remain OPEN. For the lead developer and the interface developer.
3. **Identifiers and units of pools and flows.** Each producer names its own. `engine/amg/` proposes `amg_active_pool`, `amg_stable_pool`, `amg_humified_input` and `amg_mineralised_carbon`, and `soil_organic_carbon` for the total, in `t C ha-1` (engine/amg/README.md). **On `main`:** `engine/rothc/entry.py` (`#247`, `eb1dd39`) also proposes `soil_organic_carbon` for `total_stock`, pools `rothc_dpm_pool`, `rothc_rpm_pool`, `rothc_bio_pool`, `rothc_hum_pool` and `rothc_iom_pool`, and flows `rothc_carbon_input` and `rothc_co2_carbon`, all in `t C ha-1`. Whether the total of both models shares one identifier by rule, and whether the interface needs a fixed list, remain OPEN. For the lead developer, the interface developer and the science reviewers.
4. **The state at the end of the horizon** (the rest of Q14 (a)). Here it is the last step of each stock series; no separate `ModelState` is returned. Whether the `ModelState` contract of blueprint section 5 takes this over. For the lead developer.
5. **Where `soil_carbon_trend` travels** (Q14 (c)). **Built on `main`:** `api/engines.py` calls EP5 (`#219`, `a6575c5`) and EP6 (`#282`, `994978e`; `#409`, `8097065`) and copies each `CarbonBalance.soil_carbon_trend` unchanged into `ResultsPerRotation.soil_carbon_trend` (writing missing rows when an engine is not configured or cannot run). *As first written:* Here each engine computes the three values and returns them inside its balance; the runner would copy them into `ResultsPerRotation.soil_carbon_trend`, which already requires the three computations per model. For the lead developer and the platform developer.
6. **Ranges.** A computed value carries `range_missing` with reason `NOT_AVAILABLE` today (Q6 of contracts/ENTRYPOINTS.md, C2.3). For the science reviewers.
7. **The residue ledger** (Q14 (b)). Not part of this contract. For the lead developer.
8. **Private names imported.** `_SeriesHeader` and `_SeriesItem` of `contracts/inputs/site_climate.py`, as `contracts/carbon_forcing/` does. Lane L0 may make them public.
