# Contract "ResidueLedger"

Unit `l1/residue-ledger-ep4`, brief in issue #220. Status: `PROPOSED` (blueprint section 3.7). It takes effect only when a person approves the pull request. Producer: Engines (`engine/residues/`, EP4 `build_residue_ledger`). Consumer: Platform, sub-lane L2a, which fills `CarbonForcing.annual_carbon_inputs` and `CarbonForcing.carbon_inputs` from it. **It needs the approval of the lead developer and a heads-up to the platform developer.**

**Current status on `main` (`b107d7a`):** EP4 `build_residue_ledger` (`engine/residues/ledger.py`, `#235`, `#306` `da23c2c` for D194, `#334` `421d347` for D221, `#503` `69ee58e` mass-conservation and G1–G7 tests; reconciled as `PROPOSED` in `contracts/ENTRYPOINTS.md`) is live and wired into `api/engines.py` and `api/carbon_forcing.py`, which copy `annual_carbon_inputs` (`#242`) into `CarbonForcing.annual_carbon_inputs` and `monthly_carbon_inputs` (`#350` `09e2a47`) into `CarbonForcing.carbon_inputs` unchanged. `params/records/residues/` holds 6 signed residue records (`rusle2_residue_yield_ratio` and `rusle2_crop_yield` for `soybean`, `wheat`, `maize`); the remaining 5 EP4 crop parameters (`residue_carbon_fraction`, `residue_removed_fraction`, `root_mass_at_harvest`, `root_carbon_fraction`, `rhizodeposit_carbon`), as well as AMG and RothC parameters, still wait for a person's signature (D34, D66). The contract remains `PROPOSED` until formal acceptance.

What the residue engine returns for one rotation of one field. Blueprint section 5, as EP4 of `contracts/ENTRYPOINTS.md` quotes it, asks for biomass and carbon closure, export and retention, and roots and cover kept apart. The ledger holds them per component of the rotation and per agricultural year (C5.3):

- `components`: one entry per component of the calendar in each cycle of the rotation repeated over the record (D47);
- `annual_carbon_inputs`: one series per crop, purpose and part that enters the soil, with one value per agricultural year. Each series is a `contracts.carbon_forcing.AnnualCarbonInputSeries`, so the platform copies it into the forcing unchanged.
- `monthly_carbon_inputs`: one series per origin of D194, with one value per calendar month of the agricultural years of the ledger, for the monthly carbon inputs of RothC ([D221 of #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6892470314)). Each series is a `contracts.carbon_forcing.CarbonInputSeries`, the shape of `CarbonForcing.carbon_inputs`.

This folder fixes structure only. It names no record and no value, and it fixes no unit: a producer states its units once, in `mass_unit` and `carbon_unit` for the components and in `carbon_input_unit` for the series. The model is `models.py`. The example is `examples/PLACEHOLDER_residue_ledger.json`, and its numbers mean nothing.

## Fields

| Field | Shape | Notes |
|---|---|---|
| `contract` | `"residue_ledger"` | |
| `example_data` | boolean | True when any input of the engine is example data |
| `case_id`, `field_id`, `rotation_id` | non-empty text | Those of the calendar |
| `first_ag_year`, `last_ag_year` | integer, or null | The agricultural years of the ledger, inclusive (C5.3). Null together, and only with `years_missing` |
| `years_missing` | `Missing` of `contracts/inputs/common.py`, or absent | Why no agricultural year could be laid out. With it, `components`, `annual_carbon_inputs` and `monthly_carbon_inputs` are empty |
| `mass_unit` | non-empty text | The unit of every mass value of the ledger |
| `carbon_unit` | non-empty text | The unit of every carbon value of the components |
| `carbon_input_unit` | non-empty text | The unit of every series of `annual_carbon_inputs` and of `monthly_carbon_inputs`. It may differ from `carbon_unit`: EP4 writes its entries in `kg C ha-1` and its series in `t C ha-1` (D147 of #77) |
| `components` | list of `LedgerComponent` | See below |
| `annual_carbon_inputs` | list of `AnnualCarbonInputSeries` of `contracts/carbon_forcing/` | `quantity`, `unit`, `origin`, provenance, source or assumption mark, `range_missing`, and one value per agricultural year from `first_ag_year` to `last_ag_year`, each a number or missing with its reason |
| `monthly_carbon_inputs` | list of `CarbonInputSeries` of `contracts/carbon_forcing/` | D221: one series per origin (`<crop>_aboveground`, `<crop>_belowground`; D194). `quantity` is the origin followed by `_carbon_input` (PROPOSED), `unit` is `carbon_input_unit`, `origin`, provenance, source or assumption mark, `range_missing`, `start`, `end`, and one value per calendar month of the agricultural years `first_ag_year` to `last_ag_year`, each a number or missing with its reason. A month without an input is an explicit zero |

`LedgerComponent`, one component of the calendar in one cycle:

| Field | Shape | Notes |
|---|---|---|
| `component_id`, `crop_id` | non-empty text | Those of the calendar |
| `cycle` | integer, -1 or more | The cycle of the repeated rotation: the first is 0; -1 is the lead-in of D141 (`engine/calendar/repeat.py` point 13), admitted by D160 of #77 |
| `purpose` | `grain`, `cover` or `pasture`, or `NotGiven` | Copied from the rotation definition. It keeps a cover crop apart from a grain crop |
| `residue_management` | `left_on_surface`, `incorporated` or `removed`, or `NotGiven` | The declared `management.residue` of the rotation definition, copied |
| `harvest` | `DateValue` of `contracts/inputs/common.py` | The end date of the component in this cycle, or missing with its reason |
| `ag_year` | integer, or null | The agricultural year the harvest falls in. Null exactly when the harvest date is missing |
| `aboveground_mass_produced`, `aboveground_mass_exported`, `aboveground_mass_retained` | `Value` in `mass_unit` | The aboveground residue at harvest, the part taken off the field and the part left on it |
| `aboveground_carbon_produced`, `aboveground_carbon_exported`, `aboveground_carbon_retained` | `Value` in `carbon_unit` | The carbon of the same three amounts |
| `root_mass` | `Value` in `mass_unit` | Roots, apart from the aboveground residue |
| `root_carbon` | `Value` in `carbon_unit` | The carbon of the roots |
| `rhizodeposit_carbon` | `Value` in `carbon_unit` | The carbon of the rhizodeposits |

`NotGiven` holds only a `missing` part, the same form as `MissingManagementField` of the rotation definition (D39 of #77): the key stays, so a consumer knows what is missing (C3.1).

## Rules the model checks

- The years are given, or `years_missing` is given, never both and never neither. Without years the ledger lists no component and no series. `first_ag_year` is not after `last_ag_year`.
- `cycle` is -1 or more. -1 is the lead-in of D141, the cycle before the first; nothing lower is a cycle (D160 of #77).
- A component appears at most once per cycle, the lead-in included.
- Every mass value is in `mass_unit` and every carbon value in `carbon_unit`, including a value that is missing (C3.1).
- `ag_year` is given exactly when the harvest date is given.
- No quantity identifier appears twice in `annual_carbon_inputs`. Every series runs from `first_ag_year` to `last_ag_year` and is in `carbon_input_unit`.
- The `origin` of a series follows the part at the end of its quantity (D194 of #77, https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890256765): `<crop>_aboveground` for `aboveground_carbon_retained`, and `<crop>_belowground` for `root_carbon` and `rhizodeposit_carbon`, where `<crop>` is the crop of a component of the ledger. The plain crop word is not an origin of a ledger series. A quantity that does not end in one of those three parts is rejected, because its origin cannot be checked. The rule is `ORIGIN_GROUP_OF_PART` and `series_origin` in `models.py`; EP4 writes its origins with `series_origin`.
- `monthly_carbon_inputs` ([D221 of #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6892470314)): one series for every origin of `annual_carbon_inputs` and for no other, so a ledger with annual series and no monthly ones is rejected; the origin is `<crop>_aboveground` or `<crop>_belowground` for a crop of a component of the ledger; the quantity is the origin followed by `_carbon_input` (`monthly_quantity` in `models.py`); the unit is `carbon_input_unit`; every series starts in the same month, in `first_ag_year`, and holds twelve months for each agricultural year of the ledger. The start month itself is not a field of the ledger: it is `ag_year_start.month` of the rotation calendar, which the ledger does not copy. What the ledger holds bounds it, and the model checks that bound: every dated harvest falls in one of the twelve months of its `ag_year` counted from the start month of the series (C5.3). A ledger whose harvests are all undated, or a start month that differs from the calendar's but still holds every harvest in its year, passes; the exact month is checked by EP4's tests against `calendar.ag_year_start` (`test_monthly_series_use_the_origins_of_d194` in `engine/residues/test_ledger.py`). Adding the start month as a field would change the shape the platform reads, which is for the lead developer (OPEN 7).
- Everything the shared parts already check. A value or a missing part, never both, never neither (C3.1). A present value carries a provenance label and a source or the assumption mark (C4.1, C4.2), and a range or the reason it has none (C2.2). Unknown fields are rejected and nothing is coerced.

The model does not check closure, that retained plus exported is produced, nor that a series value is the sum of the components of its year, nor that the months of an agricultural year add up to the annual series of that year and origin. Both are statements of the engine and not of the shape, as for `CarbonBalance`. The engine checks both in its tests (`engine/residues/test_ledger.py`).

## PROPOSED cases

Each case is a test function of `test_examples.py`. A test checks that this list and the file agree.

| Case | What it shows |
|---|---|
| `test_example_loads` | The PLACEHOLDER example loads, with its series in their own unit |
| `test_example_round_trips_through_json` | `model_dump(mode="json")` loads back into an equal model |
| `test_example_closes_mass_and_carbon` | In the example, retained plus exported is produced, for mass and for carbon |
| `test_every_value_missing_loads` | A ledger in which every value is missing with its reason is valid |
| `test_ledger_without_years_loads` | No years, with the reason, and no component or series (annual or monthly); a monthly series without years is rejected |
| `test_monthly_series_follow_d221` | D221: the example's monthly series, one per origin of D194, twelve months a year, explicit zeros, a missing month with its reason |
| `test_monthly_series_rules_are_checked` | An origin twice, the plain crop word, a crop that no component has, a quantity that is not the origin with `_carbon_input`, a unit other than `carbon_input_unit`, a month short, another first year, series that start in different months |
| `test_monthly_series_cover_the_origins_of_the_annual_series` | The example's monthly origins are its annual origins; a monthly series fewer, no monthly series beside annual ones, and a monthly origin without an annual series are rejected; no series of either kind loads |
| `test_monthly_start_month_is_bounded_by_the_harvests` | Series laid out from month 1 or month 5 hold the example's harvests of 1 May in their `ag_year` and load; from month 6, or with an `ag_year` a year before its harvest, they are rejected |
| `test_years_and_their_missing_reason_together_are_rejected` | Years and `years_missing` together |
| `test_ledger_without_years_or_reason_is_rejected` | One year bound alone; no years and no reason |
| `test_ledger_without_years_listing_components_is_rejected` | No years, but components listed |
| `test_years_out_of_order_are_rejected` | `first_ag_year` after `last_ag_year` |
| `test_component_twice_in_one_cycle_is_rejected` | One component twice in one cycle |
| `test_lead_in_cycle_is_admitted_and_nothing_lower` | An entry of cycle -1, the lead-in of D141, loads and round-trips; a component twice in cycle -1, and a cycle of -2, are rejected |
| `test_value_in_another_unit_than_the_ledger_is_rejected` | A mass or a carbon value in another unit than the ledger states |
| `test_agricultural_year_without_harvest_date_is_rejected` | `ag_year` without a harvest date, or a harvest date without `ag_year` |
| `test_unknown_purpose_or_residue_word_is_rejected` | A word outside the closed lists of the rotation definition |
| `test_series_rules_are_checked` | A repeated quantity, other years, a unit other than `carbon_input_unit` (also `carbon_unit` when the two differ), an origin whose crop is no crop of the ledger |
| `test_series_origin_follows_the_part_group` | D194: `<crop>_belowground` on a root or rhizodeposit series and `<crop>_aboveground` on the retained aboveground series load; the plain crop word, the other group, and a crop that no component has are rejected, and so is a quantity that does not end in a part |
| `test_missing_value_without_reason_or_with_a_number_is_rejected` | A value without a number or a reason, or with both |
| `test_unknown_field_is_rejected` | A field the model does not have |
| `test_readme_lists_the_cases_of_this_file` | This list and the file name the same cases |

## How it maps onto `AnnualCarbonInputSeries`

The ledger's series already have the shape, the agricultural years and the unit of the forcing's series, so the platform copies them. It does no arithmetic. The platform wired `annual_carbon_inputs` in #242 and `monthly_carbon_inputs` in #350 (`09e2a47`):

- `annual_carbon_inputs[i]` → `CarbonForcing.annual_carbon_inputs[i]`, unchanged (`model_dump(mode="json")`, or the same object).
- `first_ag_year` to `last_ag_year` are the whole agricultural years of the climate record, the years `api/carbon_forcing.py` gives the forcing's `horizon` (`whole_ag_years`).
- `unit` is `carbon_input_unit`. EP4 writes `t C ha-1`, the unit AMG requires for a carbon input (D147 of #77): it divides its sums in `kg C ha-1` by 1000, the SI definition of the prefixes. The runner and AMG convert nothing.
- `origin` is `<crop>_aboveground` for the retained aboveground carbon and `<crop>_belowground` for root and rhizodeposit carbon (D194 of #77). AMG reads its humification coefficient by `origin` under the scope key `crop` (`engine/amg/entry.py`, `ORIGIN_SCOPE_KEY`), so it reads one coefficient for each group: D194 gives `h_AG` to the first and `h_BG` to the second (AMGv2 parameters v2.0, https://doi.org/10.57745/MEQQIX). This contract writes no record.
- `quantity` is `<crop>_<purpose>_<part>`. `<part>` is `aboveground_carbon_retained`, `root_carbon` or `rhizodeposit_carbon`. AMG sums every series of `annual_carbon_inputs`, each with the coefficient of its origin.
- `monthly_carbon_inputs[i]` → `CarbonForcing.carbon_inputs[i]`, unchanged, as D221 says ("the platform copies it into `carbon_inputs` unchanged"). Wired on `main` (`#350`, `09e2a47`): `api/engines.py` and `api/carbon_forcing.py` copy it unchanged, and RothC (EP6, `engine/rothc/entry.py`) reads `carbon_inputs` by `origin`. The horizon of the forcing must then start in the start month of `first_ag_year`, as the series do.

What the platform still decides is in `engine/residues/README.md`, under "For the platform".

## OPEN

Each item is a question a person answers; the role is named.

1. **Acceptance of the shape.** The field list above, the names, one entry per component and cycle, the flat value fields, and series per crop, purpose and part. For the lead developer, and the platform developer as consumer.
2. **Whether the forcing takes the ledger or only its series** (Q14 (b) of `contracts/ENTRYPOINTS.md`). Here only the series reach `CarbonForcing`, and the components stay in the ledger. For the lead developer and the platform developer.
3. **The vocabulary of `origin` and of `quantity`** (OPEN 4 of `contracts/carbon_forcing/README.md`). Answered for the origin of a ledger series by D194 of #77: `<crop>_aboveground` and `<crop>_belowground` (see "Rules the model checks"). Still open: the vocabulary of `quantity` (crop, purpose and part here); whether a `cover` or `pasture` series takes the same groups (D194 names grain crops only; today their values are `NOT_COMPUTABLE`); and whether the crop named in the origin must be the crop named in the quantity (the model checks only that it is a crop of the ledger). For the lead developer and the science reviewers.
4. **Closure checked by the model.** It is not checked here, so no tolerance is written. For the lead developer.
5. **Ranges.** Every computed value carries `range_missing` with reason `NOT_AVAILABLE` (Q6 of `contracts/ENTRYPOINTS.md`, C2.3). For the science reviewers.
6. **Private names imported.** None directly: `AnnualCarbonInputSeries` brings `_SeriesHeader` and `_SeriesItem` of `contracts/inputs/site_climate.py` with it, as in `contracts/carbon_forcing/`.
7. **The monthly series of D221.** Answered by D221 of #77: the carbon of a component enters in the calendar month of its harvest, and every other month is zero. **Built on `main` (`#350`, `09e2a47`):** `api/engines.py` and `api/carbon_forcing.py` copy `monthly_carbon_inputs` unchanged into `CarbonForcing.carbon_inputs`. Still open, as D221 states: roots spread over the months of crop growth (an option not taken); the quantity identifier `<origin>_carbon_input` (PROPOSED here); formal acceptance of copying these series into `CarbonForcing.carbon_inputs`; whether the ledger states the start month of the agricultural year as a field, so the model checks the month itself and not only the bound the harvests give (see "Rules the model checks"). For the lead developer and the platform developer.
