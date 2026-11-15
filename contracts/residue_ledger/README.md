# Contract "ResidueLedger"

Unit `l1/residue-ledger-ep4`, brief in issue #220. Status: `PROPOSED` (blueprint section 3.7). It takes effect only when a person approves the pull request. Producer: Engines (`engine/residues/`, EP4 `build_residue_ledger`). Consumer: Platform, sub-lane L2a, which fills `CarbonForcing.annual_carbon_inputs` from it. **It needs the approval of the lead developer and a heads-up to the platform developer.**

What the residue engine returns for one rotation of one field. Blueprint section 5, as EP4 of `contracts/ENTRYPOINTS.md` quotes it, asks for biomass and carbon closure, export and retention, and roots and cover kept apart. The ledger holds them per component of the rotation and per agricultural year (C5.3):

- `components`: one entry per component of the calendar in each cycle of the rotation repeated over the record (D47);
- `annual_carbon_inputs`: one series per crop, purpose and part that enters the soil, with one value per agricultural year. Each series is a `contracts.carbon_forcing.AnnualCarbonInputSeries`, so the platform copies it into the forcing unchanged.

This folder fixes structure only. It names no record and no value, and it fixes no unit: a producer states its units once, in `mass_unit` and `carbon_unit`. The model is `models.py`. The example is `examples/PLACEHOLDER_residue_ledger.json`, and its numbers mean nothing.

## Fields

| Field | Shape | Notes |
|---|---|---|
| `contract` | `"residue_ledger"` | |
| `example_data` | boolean | True when any input of the engine is example data |
| `case_id`, `field_id`, `rotation_id` | non-empty text | Those of the calendar |
| `first_ag_year`, `last_ag_year` | integer, or null | The agricultural years of the ledger, inclusive (C5.3). Null together, and only with `years_missing` |
| `years_missing` | `Missing` of `contracts/inputs/common.py`, or absent | Why no agricultural year could be laid out. With it, `components` and `annual_carbon_inputs` are empty |
| `mass_unit` | non-empty text | The unit of every mass value of the ledger |
| `carbon_unit` | non-empty text | The unit of every carbon value and of every series |
| `components` | list of `LedgerComponent` | See below |
| `annual_carbon_inputs` | list of `AnnualCarbonInputSeries` of `contracts/carbon_forcing/` | `quantity`, `unit`, `origin`, provenance, source or assumption mark, `range_missing`, and one value per agricultural year from `first_ag_year` to `last_ag_year`, each a number or missing with its reason |

`LedgerComponent`, one component of the calendar in one cycle:

| Field | Shape | Notes |
|---|---|---|
| `component_id`, `crop_id` | non-empty text | Those of the calendar |
| `cycle` | integer, zero or more | The cycle of the repeated rotation; the first is 0 |
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
- A component appears at most once per cycle.
- Every mass value is in `mass_unit` and every carbon value in `carbon_unit`, including a value that is missing (C3.1).
- `ag_year` is given exactly when the harvest date is given.
- No quantity identifier appears twice in `annual_carbon_inputs`. Every series runs from `first_ag_year` to `last_ag_year`, is in `carbon_unit`, and has as its `origin` the crop of a component of the ledger.
- Everything the shared parts already check. A value or a missing part, never both, never neither (C3.1). A present value carries a provenance label and a source or the assumption mark (C4.1, C4.2), and a range or the reason it has none (C2.2). Unknown fields are rejected and nothing is coerced.

The model does not check closure, that retained plus exported is produced, nor that a series value is the sum of the components of its year. Both are statements of the engine and not of the shape, as for `CarbonBalance`. The engine checks both in its tests (`engine/residues/test_ledger.py`).

## PROPOSED cases

Each case is a test function of `test_examples.py`. A test checks that this list and the file agree.

| Case | What it shows |
|---|---|
| `test_example_loads` | The PLACEHOLDER example loads |
| `test_example_round_trips_through_json` | `model_dump(mode="json")` loads back into an equal model |
| `test_example_closes_mass_and_carbon` | In the example, retained plus exported is produced, for mass and for carbon |
| `test_every_value_missing_loads` | A ledger in which every value is missing with its reason is valid |
| `test_ledger_without_years_loads` | No years, with the reason, and no component or series |
| `test_years_and_their_missing_reason_together_are_rejected` | Years and `years_missing` together |
| `test_ledger_without_years_or_reason_is_rejected` | One year bound alone; no years and no reason |
| `test_ledger_without_years_listing_components_is_rejected` | No years, but components listed |
| `test_years_out_of_order_are_rejected` | `first_ag_year` after `last_ag_year` |
| `test_component_twice_in_one_cycle_is_rejected` | One component twice in one cycle |
| `test_value_in_another_unit_than_the_ledger_is_rejected` | A mass or a carbon value in another unit than the ledger states |
| `test_agricultural_year_without_harvest_date_is_rejected` | `ag_year` without a harvest date, or a harvest date without `ag_year` |
| `test_unknown_purpose_or_residue_word_is_rejected` | A word outside the closed lists of the rotation definition |
| `test_series_rules_are_checked` | A repeated quantity, other years, another unit, an origin that is no crop of the ledger |
| `test_missing_value_without_reason_or_with_a_number_is_rejected` | A value without a number or a reason, or with both |
| `test_unknown_field_is_rejected` | A field the model does not have |
| `test_readme_lists_the_cases_of_this_file` | This list and the file name the same cases |

## How it maps onto `AnnualCarbonInputSeries`

The ledger's series already have the shape of the forcing's series and the forcing's agricultural years, so the platform copies them. Apart from the unit (below), it does no arithmetic:

- `annual_carbon_inputs[i]` → `CarbonForcing.annual_carbon_inputs[i]`, unchanged (`model_dump(mode="json")`, or the same object).
- `first_ag_year` to `last_ag_year` are the whole agricultural years of the climate record, the years `api/carbon_forcing.py` gives the forcing's `horizon` (`whole_ag_years`).
- `unit` is `carbon_unit`. EP4 writes `kg C ha-1`. AMG requires `t C ha-1` and converts nothing, so the copy is unchanged in shape but needs a conversion before AMG can use it (OPEN 3 of `engine/residues/README.md`).
- `origin` is the crop. AMG reads its humification coefficient by `origin` under the scope key `crop` (`engine/amg/entry.py`, `ORIGIN_SCOPE_KEY`).
- `quantity` is `<crop>_<purpose>_<part>`. `<part>` is `aboveground_carbon_retained`, `root_carbon` or `rhizodeposit_carbon`. AMG sums every series of `annual_carbon_inputs`, each with the coefficient of its origin.

What the platform still decides is in `engine/residues/README.md`, under "For the platform".

## OPEN

Each item is a question a person answers; the role is named.

1. **Acceptance of the shape.** The field list above, the names, one entry per component and cycle, the flat value fields, and series per crop, purpose and part. For the lead developer, and the platform developer as consumer.
2. **Whether the forcing takes the ledger or only its series** (Q14 (b) of `contracts/ENTRYPOINTS.md`). Here only the series reach `CarbonForcing`, and the components stay in the ledger. For the lead developer and the platform developer.
3. **The vocabulary of `origin` and of `quantity`** (OPEN 4 of `contracts/carbon_forcing/README.md`). Here the origin is the crop and the quantity names crop, purpose and part. If the humification coefficient of AMG differs by organ (aboveground, roots, rhizodeposits), the origin would need the part too. For the lead developer and the science reviewers.
4. **Closure checked by the model.** It is not checked here, so no tolerance is written. For the lead developer.
5. **Ranges.** Every computed value carries `range_missing` with reason `NOT_AVAILABLE` (Q6 of `contracts/ENTRYPOINTS.md`, C2.3). For the science reviewers.
6. **Private names imported.** None directly: `AnnualCarbonInputSeries` brings `_SeriesHeader` and `_SeriesItem` of `contracts/inputs/site_climate.py` with it, as in `contracts/carbon_forcing/`.
