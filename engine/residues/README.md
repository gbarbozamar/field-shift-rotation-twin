# Residue engine (EP4)

Unit `l1/residue-ledger-ep4`, brief in issue #220. It answers Q13 of `contracts/ENTRYPOINTS.md` as a candidate for the lead developer. Status: `PROPOSED` (blueprint section 3.7). It takes effect only when a person approves the pull request. Items under [OPEN](#open) need an answer from a person.

Why it exists: under D122 of #77, the annual carbon inputs of AMG (EP5) are `NOT_AVAILABLE` while EP4 is not built. This engine computes them, so that the platform can fill `CarbonForcing.annual_carbon_inputs`.

No value of the method is written here or in the code. Every number comes from a record of the parameter catalogue, signed later by the lead developer (D34). The tests use plainly unreal PLACEHOLDER numbers.

## Signature

```text
build_residue_ledger(
    rotation: RotationDefinition,      # contracts/rotation_definition/
    calendar: RotationCalendar,        # contracts/inputs/rotation_calendar.py, from EP2
    climate: SiteClimate,              # contracts/inputs/site_climate.py, from the adapters
    *,
    parameters: dict[str, dict],       # the catalogue as loaded (Q3, D46, D56)
) -> ResidueLedger                     # contracts/residue_ledger/
```

Why each argument is needed:

- `rotation`: the `purpose` and the declared `management.residue` of each component. The calendar does not carry them, and they are the declared inputs that keep a cover crop apart and decide export.
- `calendar`: the components, their crops and their harvest (end) dates, and the feasibility.
- `climate`: only the period of the record, which gives the agricultural years (D47). No series value is read.
- `parameters`: the records below.

It raises only `TypeError` (an argument not of its type) and `ValueError` (the three arguments name different `case_id` or `field_id`), as G5 allows. Everything else is missing with its reason (G4).

## What it computes

1. **The agricultural years.** The record is the days every daily series of `climate` covers (latest start, earliest end). The years are every whole agricultural year of the record (C5.3, C5.5), cut by `calendar.ag_year_start.month`. These are the years `api/carbon_forcing.py` gives `CarbonForcing.horizon`. No daily series gives `years_missing` `MISSING_INPUT`. Series that share no day, or no whole year, give `NO_COVERAGE`. No start month gives `MISSING_INPUT`.
2. **The rotation over the record.** `engine.calendar.repeat_over_record(calendar, record_start, record_end)`, the helper of EP1 (D47). Each component in each cycle is one entry. A component in a cycle has its harvest on its end date in that cycle, in the agricultural year of that date.
3. **One entry, for a `grain` component.** Every record is read with scope `{"crop": <crop_id>}`:
   - `aboveground_mass_produced = rusle2_residue_yield_ratio × rusle2_crop_yield` (D129 (c));
   - `aboveground_mass_exported = aboveground_mass_produced × residue_removed_fraction` when the component declares its residue `removed`. It is `0` (a value, not a stand-in) when it declares `left_on_surface` or `incorporated`. It is `MISSING_INPUT` when the residue is not declared;
   - `aboveground_mass_retained = aboveground_mass_produced − aboveground_mass_exported`;
   - `aboveground_carbon_produced` and `aboveground_carbon_exported` are their masses × `residue_carbon_fraction`, and `aboveground_carbon_retained = produced − exported`. So mass and carbon close by construction;
   - `root_mass = root_mass_at_harvest`, `root_carbon = root_mass_at_harvest × root_carbon_fraction`;
   - `rhizodeposit_carbon = rhizodeposit_carbon`.
4. **A `cover` or `pasture` component.** All nine values are `NOT_COMPUTABLE`. D129 (c) computes the residue from a yield, which these purposes do not have, and no method is decided for them (OPEN 5).
5. **The annual series.** One series for each crop and purpose of the entries, and each part that enters the soil (`aboveground_carbon_retained`, `root_carbon`, `rhizodeposit_carbon`). The value of an agricultural year is the sum of that part over the entries of that crop and purpose harvested in that year, converted from `kg C ha-1` to `t C ha-1` by dividing by `KG_PER_TONNE` (1 t = 1000 kg, the SI definition of the prefixes; D147 of #77). A year with no such harvest is `0` (OPEN 6). The value of a year is `MISSING_INPUT`, naming each cause, when:
   - a value it sums is missing;
   - an entry of that crop and purpose has no harvest date and could be harvested in that year (between its start, or the cycle's start, and the day before the next cycle, point 7 of `engine/calendar/repeat.py`);
   - the year begins before the first cycle (nothing is laid out before it, point 6 of `repeat.py`);
   - a calendar component has no component in the rotation definition.

   A crop whose `crop_id` is not a quantity identifier (`^[a-z][a-z0-9_]*$`) gets no series. Its entries are still listed. The same holds for `crop_origins` in `api/carbon_forcing.py`.

An **infeasible calendar** makes every value of every entry and every year of every series `NOT_COMPUTABLE`, naming the rules it breaks (G4). The entries are still laid out.

Labels: a computed value is `DERIVED` (C4.3), with a source naming `engine.residues.build_residue_ledger`, the formula and the records, and `range_missing` `NOT_AVAILABLE` (Q6). A missing input propagates as `MISSING_INPUT`, naming each missing operand with its own reason and detail (C3.3).

## Records

The first two identifiers are those #218 fixed (PR #229); the other five are `PROPOSED`. Each is read by crop, with scope `{"crop": <crop_id>}` (scope key of `params/README.md`), found by `id` and `scope` exactly (question 5 of `params/README.md`). Units are SI, as the orchestrating session of #220 set them: `kg ha-1` of dry matter for a mass and `kg C ha-1` for carbon, the unit the yield records arrive in. No record is converted. A record in another unit is `NOT_COMPUTABLE`, naming it (OPEN 3). Only the annual series are converted, to `t C ha-1` (D147).

| Name in the code | `id` | Scope | Unit | Bounds | What it is |
|---|---|---|---|---|---|
| `rusle2_residue_yield_ratio` | `rusle2_residue_yield_ratio` | `crop` | `dimensionless` | not negative | Mass of aboveground residue at harvest per mass of yield (D129 (c); AH703 Table 5-1). The record #218 (PR #229) reads for the computed `C` |
| `rusle2_crop_yield` | `rusle2_crop_yield` | `crop` | `kg ha-1` | not negative | Yield per area, dry matter (D129 (c): a Uruguayan yield with a published source). The record #218 (PR #229) reads for the computed `C` (OPEN 2) |
| `residue_carbon_fraction` | `residue_carbon_fraction` | `crop` | `dimensionless` | 0 to 1 | Carbon per mass of aboveground residue |
| `residue_removed_fraction` | `residue_removed_fraction` | `crop` | `dimensionless` | 0 to 1 | Share of the aboveground residue taken off the field. Read only for a component that declares `removed` |
| `root_mass_at_harvest` | `root_mass_at_harvest` | `crop` | `kg ha-1` | not negative | Roots per area at harvest, dry matter |
| `root_carbon_fraction` | `root_carbon_fraction` | `crop` | `dimensionless` | 0 to 1 | Carbon per mass of roots |
| `rhizodeposit_carbon` | `rhizodeposit_carbon` | `crop` | `kg C ha-1` | not negative | Carbon of rhizodeposits per area over the component |

What a lookup gives: the number. Or `MISSING_INPUT` naming the record by `id` and scope, and why: no record (D56), a `null` value (with the reason of the record repeated), a record that `read_value` refuses (a placeholder, malformed), two records with one `id` and scope, or a record without a well-formed `id` and `scope` anywhere in the catalogue (F3c). Or `NOT_COMPUTABLE` for another unit or a number outside its bounds (PROPOSED).

No partition form, for example a root-to-shoot ratio, is used: roots and rhizodeposits are records of their own (OPEN 4).

## For the platform

What the platform developer needs to wire the ledger into `CarbonForcing` (`api/`, `contracts/carbon_forcing/`). This unit touches neither. The platform wired EP4 into the runner in #242.

1. **Call it** in the runner before EP5, by name (done in #242): `engine.residues.build_residue_ledger(rotation=..., calendar=..., climate=..., parameters=...)`. Pass the validated `RotationDefinition` of the request, the calendar EP2 returned (also when infeasible), the same `SiteClimate` and the same catalogue as EP1, EP3 and EP5. Like `discover_engine_functions()`, it can be looked up by module and function name.
2. **Copy the series.** Each series is already an `AnnualCarbonInputSeries`, with the forcing's agricultural years, and loads into `CarbonForcing.annual_carbon_inputs` unchanged. Under D147 of #77, EP4 writes the series in `t C ha-1`, the unit AMG requires (`STOCK_UNIT` of `api/carbon_forcing.py` and `engine/amg/entry.py`). The ledger states it in `carbon_input_unit`. The runner and AMG convert nothing. The ledger's components stay in `kg ha-1` and `kg C ha-1` (`mass_unit`, `carbon_unit`). The years are the whole agricultural years of the record, computed as `whole_ag_years` does and from the same period as `record_period`. The `origin` follows D194 of #77 (https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890256765): `<crop_id>_aboveground` for the series of the retained aboveground carbon, and `<crop_id>_belowground` for the series of root carbon and of rhizodeposit carbon (`series_origin` of `contracts/residue_ledger/models.py`, which the ledger contract checks).
3. **What changes from today.** Today the runner writes one series per crop with `quantity` equal to the crop and every year `NOT_AVAILABLE` (D122). With the ledger there are up to three series per crop and purpose: `<crop>_<purpose>_aboveground_carbon_retained`, `<crop>_<purpose>_root_carbon` and `<crop>_<purpose>_rhizodeposit_carbon`. AMG sums them all, each with the humification coefficient of its `origin`: by D194, one coefficient for the aboveground origin of a crop (`h_AG`) and one for its belowground origin (`h_BG`), each a record of `amg_humification_coefficient` under the scope `{"crop": "<crop_id>_aboveground"}` or `{"crop": "<crop_id>_belowground"}`. This unit writes no record: they are the unit of the carbon records (D194, D195, D197), after a person's signature. A record under the plain crop word is not read for these series.
4. **When the ledger has no years** (`years_missing` set, no series), the forcing could not be built either: same start month, same record. Keep writing the series as missing, with the ledger's `years_missing` as the reason, or keep the D122 text.
5. **A missing value travels.** A year that is missing in any series makes that year of AMG missing. So until the records are signed, AMG keeps its values missing, now with `MISSING_INPUT` naming the records (instead of `NOT_AVAILABLE`). A cover or pasture crop gets its own series (`<crop>_cover_...`, `<crop>_pasture_...`), whose entries are all `NOT_COMPUTABLE` (OPEN 5). In those series:
   - a year in which such a component is harvested is `MISSING_INPUT`, and its detail names the component and repeats its `NOT_COMPUTABLE` reason;
   - so is a year in which an undated harvest could fall; a cover crop's harvest date is often missing as `NOT_APPLICABLE`, so this can be every year of its cycles;
   - a year with no such harvest is `0.0`.

   Whether to copy those series or leave them out is the platform developer's and the lead developer's call. Leaving one out would make AMG run without that crop's carbon, so the choice must be stated in the module detail.
6. **The ledger itself** (the components, with closure) is not in `CarbonForcing` or in the response. Whether the response carries it is Q14 (b) and Q15 of `contracts/ENTRYPOINTS.md`.
7. **The module state.** Done in #242: `api/engines.py` discovers EP4 (`RESIDUES` is in `DISCOVERED`) and reports the `residues` module from the ledger. The tripwire test of `api/test_engines.py` that expected EP4 not to exist changed with it.
8. **D109 phases.** EP4 lays out the same phase as EP1, the one that starts with the calendar's first year, so the ledger and EP1 agree. A phase argument would reach EP4 the same way as EP1.
9. **The monthly carbon inputs for RothC** ([D221 of #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6892470314), unit `l1/residues-monthly-inputs-d221`). The ledger now also holds `monthly_carbon_inputs`: one `CarbonInputSeries` per origin of D194 (`<crop_id>_aboveground`, `<crop_id>_belowground`), quantity `<origin>_carbon_input` (PROPOSED), in `t C ha-1` (D147), over every calendar month of the agricultural years of the ledger, starting in the start month of `first_ag_year`. All the carbon of a component (retained aboveground, roots, rhizodeposits) enters in the calendar month of its harvest; every other month is an explicit zero; a month that may hold a harvest it cannot read is `MISSING_INPUT`, never zero. The parts of one origin are summed, and so are the purposes of one crop, because the origin names the crop only. D221 says the platform copies these series into `CarbonForcing.carbon_inputs` unchanged; this unit does not wire it (`api/` is the platform's). The forcing's horizon then has to start in the same month as these series.

## PROPOSED cases

Each case is a test in `test_ledger.py`. All numbers are PLACEHOLDER numbers; no case contains an expected value of the science. A test checks that this list and the file agree.

| Case | What it shows |
|---|---|
| `test_placeholder_catalogue_is_well_formed_once_unmarked` | The test catalogue passes `check_catalogue` once unmarked, and is refused while marked |
| `test_two_crop_calendar_gives_ledger_with_carbon_recomputed` | Two crops over three years: every mass and carbon value, and every year of every series, recomputed in the test from the same records |
| `test_mass_and_carbon_close_retained_plus_exported_equals_produced` | Retained plus exported equals produced, for mass and for carbon |
| `test_roots_and_aboveground_residue_stay_apart` | Without the root records only the roots are missing; the aboveground values and series do not change; roots have their own series |
| `test_missing_ratio_yield_or_carbon_fraction_names_itself` | A missing ratio, yield or carbon fraction gives `MISSING_INPUT` naming the record and its crop, propagates, and leaves the other crop alone |
| `test_null_record_repeats_its_reason` | A record with `"value": null` is named with its reason |
| `test_infeasible_calendar_gives_not_computable` | Every value and every year is `NOT_COMPUTABLE`, naming the rule |
| `test_cover_component_is_kept_apart_and_not_computed` | A cover component has its own series and its entries have `NOT_COMPUTABLE` values; the grain crop is unaffected |
| `test_residue_not_declared_leaves_export_and_retention_missing` | The produced residue is computed; export and retention are `MISSING_INPUT` |
| `test_residue_kept_on_the_field_exports_nothing` | `left_on_surface` and `incorporated` export nothing and do not read the removed fraction |
| `test_record_in_another_unit_or_outside_its_bounds_is_not_computable` | Another unit, a fraction above one, a negative carbon: `NOT_COMPUTABLE` naming the record |
| `test_marked_or_malformed_record_is_missing_input_naming_why` | A PLACEHOLDER record and a record without an identity are named |
| `test_years_are_the_whole_agricultural_years_of_the_record` | A record that does not start on the start month: only whole years |
| `test_first_year_before_the_first_cycle_is_missing` | A first year that begins before the first cycle is `MISSING_INPUT`; the others are computed |
| `test_component_starting_before_the_start_month_gives_a_lead_in_entry` | A first component that starts before the start month: the cycle before the first is written as cycle -1 (the lead-in of D141), its harvests fall in the first agricultural year, and that year is their value, not missing |
| `test_undated_harvest_leaves_the_years_it_may_fall_in_missing` | A component without an end date: its entries have no year and its crop's years are missing, naming it |
| `test_year_without_a_harvest_of_a_crop_is_zero` | A two-year cycle: the year without a harvest of a crop is zero, the other one is its value |
| `test_ledger_without_years_says_why` | No daily series (`MISSING_INPUT`) or no whole year (`NO_COVERAGE`): no years, no entries |
| `test_series_load_into_carbon_forcing_unchanged` | The series load unchanged into a `CarbonForcing` whose horizon is those years, in the unit AMG requires (`STOCK_UNIT` of `engine/amg/entry.py`, D147); the components stay in `kg C ha-1` |
| `test_series_origin_is_the_part_group` | D194: per crop and purpose, the origin of the retained aboveground series is `<crop>_aboveground` and that of the root and rhizodeposit series `<crop>_belowground`; every other field of every series is what the previous rule (origin = crop, written in the test) gives |
| `test_amg_reads_one_coefficient_per_origin_group` | Through EP5 (`run_amg`) on a forcing whose series are the ledger's: the humified input of each year is the sum of each series times the PLACEHOLDER coefficient of its origin group, recomputed; records under the plain crop word, also in the catalogue, give another number and are not read |
| `test_amg_without_the_group_records_names_them_and_not_the_crop` | With records under the plain crop word only, EP5's humified input is `MISSING_INPUT` and names the `<crop>_aboveground` / `<crop>_belowground` scopes, never the plain crop |
| `test_monthly_series_use_the_origins_of_d194` | D221: one monthly series per origin of D194, quantity `<origin>_carbon_input`, in `t C ha-1`, twelve months a year from the start month; the same origins as the annual series |
| `test_harvest_month_carries_the_whole_component_and_other_months_are_zero` | Each month recomputed from the entries: the harvest month holds the carbon of the component (the parts of its origin), every other month is an explicit zero |
| `test_two_harvests_in_one_month_add_up` | Two components of one crop harvested in one calendar month: the month holds their sum |
| `test_missing_component_gives_missing_months_never_zero` | Without the root records, the harvest months of the belowground series are `MISSING_INPUT` naming the part; an undated harvest makes the months it may fall in missing; never zero |
| `test_monthly_sum_equals_the_annual_series` | For each origin and agricultural year, the twelve months add up to the annual series of that origin; a missing annual value has a missing month |
| `test_series_are_in_tonnes_hand_checked` | One PLACEHOLDER record checked by hand: 3.33 `kg C ha-1` in the entry is 0.00333 `t C ha-1` in each year of its series (D147) |
| `test_ledger_round_trips_and_arguments_are_not_changed` | The same result twice, a JSON round trip, and arguments unchanged (G1) |
| `test_wrong_argument_types_and_other_field_raise` | `TypeError` for a wrong type, `ValueError` for another `field_id` (G5) |
| `test_signature_is_the_one_of_entrypoints` | The argument names and the keyword-only `parameters` |
| `test_records_have_the_units_of_the_readme` | The records use the three units, and each identifier is in this file |
| `test_readme_lists_the_cases_of_this_file` | This list and the file name the same cases |

## OPEN

Each item is a question a person answers; the role is named.

1. **The identifiers shared with #218: settled, a note only.** `rusle2_residue_yield_ratio` and `rusle2_crop_yield` (scope `crop`; `dimensionless` and `kg ha-1`) are the two records of D129 (c), with the identifiers fixed by #218 (`l0/erosion-c-main-route`, PR #229). The ledger and the computed `C` read the same records. No question is left here.
2. **One yield record, two units.** #218 needs the residue mass in `lb acre-1` (the unit of α, with a cited conversion record). This engine reads the yield in `kg ha-1`, as the records will arrive, and converts nothing. #218 converts it with its own record `mass_per_area_kg_ha_to_lb_acre`, which this engine does not read. Also open: whether every yield record is dry matter (the record has no field that says so; the unit string cannot), and whether the ratio of AH703 Table 5-1 is mass per mass. If it is not, `dimensionless` does not hold and a conversion record is needed. CITATION NEEDED. For the lead developer and the science reviewers.
3. **Units and bounds.** The conversion question is closed by **D147** of #77 (https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649). EP4 converts, and its annual series are in `t C ha-1`. The conversion is the SI definition of the prefixes, 1 t = 1000 kg (`KG_PER_TONNE` in `_parameters.py`): a definition, so it has no record. The components of the ledger stay in `kg ha-1` (dry matter) and `kg C ha-1`. No record is converted, and a record in another unit is `NOT_COMPUTABLE` (as in `engine/amg/`; the reason code for a unit is Q11). Still open:
   - C1.1 lists `t` and `t C`, not `kg`, so the `kg` unit strings of the entries need C1.1 to accept them;
   - a fraction outside zero to one, or a negative mass, ratio or carbon, is `NOT_COMPUTABLE` (PROPOSED).

   For the lead developer.
4. **Roots and rhizodeposits.** Here they are records of their own, by crop, independent of the yield. A partition form, for example a root-to-shoot ratio or a share of the aboveground carbon, would be a record value with a cited source. CITATION NEEDED. Whether the roots of a crop are counted at harvest and in full, and whether rhizodeposits are given as carbon, are for the science reviewers.
5. **Cover crops and pastures.** No method is decided for their residue, so their values are `NOT_COMPUTABLE`. The calendar also does not say whether a cover crop's end date is its termination. For the lead developer and the science reviewers.
6. **When a residue enters the soil.** Here the whole carbon of a component enters in the agricultural year of its harvest. That covers the aboveground residue, the roots and the rhizodeposits. A year without a harvest of that crop and purpose is zero, a value and not a stand-in, so that AMG receives "no input" as a value (OPEN 6 of `engine/amg/README.md`). Spreading the input over the months of the component, or over the next year, is not done. For the lead developer and the science reviewers.
7. **Export when `removed` is declared.** The share removed is the record `residue_removed_fraction` by crop. "Removed" is not read as "all of it". `left_on_surface` and `incorporated` both retain everything, and the ledger copies the word, so a carbon model could tell them apart later. For the lead developer.
8. **The period of the record** is the days every daily series covers, as the platform reads it for the forcing. EP1 reads its `precipitation` series (Q5: which series marks the record for each engine). For the lead developer and the platform developer.
9. **Records scoped by crop only.** A crop sown as grain in one rotation and as a cover in another shares its records, but only `grain` components read them. Whether a scope key `management` or `stage` is needed is question 5 of `params/README.md`. For the lead developer.
10. **The types table and summary row of `contracts/ENTRYPOINTS.md`.** The row of `"ResidueLedger"` in "Types used in the signatures" and the EP4 row of the summary still say `OPEN`. The brief let this unit change only the EP4 section and Q13, so a one-line follow-up updates them. For the lead developer.
11. **The origin of the per-crop series the platform writes when there is no ledger series** (unit `l1/residues-origin-split-d194`, D194). When EP4 is not built, or the ledger has no years, `api/carbon_forcing.py` (`carbon_input_series`, with `crop_origins`) writes one series per crop with `origin` = the crop, every year missing. Those series keep the plain crop as origin. It is harmless while every value is missing, because AMG reads no coefficient that changes a missing input into a number; it is left to the platform developer, who owns that file. For the platform developer.
12. **Cover and pasture series and D194.** EP4 writes the same origin groups for a `cover` or `pasture` series (`<crop>_aboveground`, `<crop>_belowground`), because the rule follows the part, not the purpose. D194 gives coefficients for grain crops only (soybean, wheat, maize), and those series are `NOT_COMPUTABLE` today (OPEN 5). Whether a cover or a pasture takes the same two groups, and which coefficients, is for the lead developer and the science reviewers.
13. **The monthly series of D221.** As D221 states it: roots and rhizodeposits enter in the harvest month too; spreading roots over the months of crop growth is an option D221 did not take (it needs the sowing month of each cycle). Also open: the quantity identifier `<origin>_carbon_input` (PROPOSED); a month before the first described day of the record is missing (the same rule as the annual series, by month); and the copy into `CarbonForcing.carbon_inputs`, which is the platform's. For the lead developer and the platform developer.
