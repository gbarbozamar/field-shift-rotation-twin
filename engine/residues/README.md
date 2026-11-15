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
5. **The annual series.** One series for each crop and purpose of the entries, and each part that enters the soil (`aboveground_carbon_retained`, `root_carbon`, `rhizodeposit_carbon`). The value of an agricultural year is the sum of that part over the entries of that crop and purpose harvested in that year. A year with no such harvest is `0` (OPEN 6). The value of a year is `MISSING_INPUT`, naming each cause, when:
   - a value it sums is missing;
   - an entry of that crop and purpose has no harvest date and could be harvested in that year (between its start, or the cycle's start, and the day before the next cycle, point 7 of `engine/calendar/repeat.py`);
   - the year begins before the first cycle (nothing is laid out before it, point 6 of `repeat.py`);
   - a calendar component has no component in the rotation definition.

   A crop whose `crop_id` is not a quantity identifier (`^[a-z][a-z0-9_]*$`) gets no series. Its entries are still listed. The same holds for `crop_origins` in `api/carbon_forcing.py`.

An **infeasible calendar** makes every value of every entry and every year of every series `NOT_COMPUTABLE`, naming the rules it breaks (G4). The entries are still laid out.

Labels: a computed value is `DERIVED` (C4.3), with a source naming `engine.residues.build_residue_ledger`, the formula and the records, and `range_missing` `NOT_AVAILABLE` (Q6). A missing input propagates as `MISSING_INPUT`, naming each missing operand with its own reason and detail (C3.3).

## Records

The first two identifiers are those #218 fixed (PR #229); the other five are `PROPOSED`. Each is read by crop, with scope `{"crop": <crop_id>}` (scope key of `params/README.md`), found by `id` and `scope` exactly (question 5 of `params/README.md`). Units are SI, as the orchestrating session of #220 set them: `kg ha-1` of dry matter for a mass and `kg C ha-1` for carbon, the unit the yield records arrive in. Nothing is converted. A record in another unit is `NOT_COMPUTABLE`, naming it (OPEN 3).

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

What the platform developer needs to wire the ledger into `CarbonForcing` (`api/`, `contracts/carbon_forcing/`). This unit touches neither.

1. **Call it** in the runner before EP5, by name: `engine.residues.build_residue_ledger(rotation=..., calendar=..., climate=..., parameters=...)`. Pass the validated `RotationDefinition` of the request, the calendar EP2 returned (also when infeasible), the same `SiteClimate` and the same catalogue as EP1, EP3 and EP5. Like `discover_engine_functions()`, it can be looked up by module and function name.
2. **Copy the series, but mind the unit.** Each series is already an `AnnualCarbonInputSeries`, with the forcing's agricultural years, and loads into `CarbonForcing.annual_carbon_inputs` unchanged. **It is in `kg C ha-1`, and AMG requires `t C ha-1` (`STOCK_UNIT` of `api/carbon_forcing.py`, `engine/amg/entry.py`) and converts nothing.** Copied as it is, AMG answers `NOT_COMPUTABLE` naming the unit. Someone converts it, and who is OPEN 3 (the platform, AMG, or the ledger writing a second unit). The years are the whole agricultural years of the record, computed as `whole_ag_years` does and from the same period as `record_period`. The `origin` is the crop.
3. **What changes from today.** Today the runner writes one series per crop with `quantity` equal to the crop and every year `NOT_AVAILABLE` (D122). With the ledger there are up to three series per crop and purpose: `<crop>_<purpose>_aboveground_carbon_retained`, `<crop>_<purpose>_root_carbon` and `<crop>_<purpose>_rhizodeposit_carbon`. AMG sums them all, each with the humification coefficient of its `origin`.
4. **When the ledger has no years** (`years_missing` set, no series), the forcing could not be built either: same start month, same record. Keep writing the series as missing, with the ledger's `years_missing` as the reason, or keep the D122 text.
5. **A missing value travels.** A year that is missing in any series makes that year of AMG missing. So until the records are signed, AMG keeps its values missing, now with `MISSING_INPUT` naming the records (instead of `NOT_AVAILABLE`). A cover or pasture crop gets its own series (`<crop>_cover_...`, `<crop>_pasture_...`), whose entries are all `NOT_COMPUTABLE` (OPEN 5). In those series:
   - a year in which such a component is harvested is `MISSING_INPUT`, and its detail names the component and repeats its `NOT_COMPUTABLE` reason;
   - so is a year in which an undated harvest could fall; a cover crop's harvest date is often missing as `NOT_APPLICABLE`, so this can be every year of its cycles;
   - a year with no such harvest is `0.0`.

   Whether to copy those series or leave them out is the platform developer's and the lead developer's call. Leaving one out would make AMG run without that crop's carbon, so the choice must be stated in the module detail.
6. **The ledger itself** (the components, with closure) is not in `CarbonForcing` or in the response. Whether the response carries it is Q14 (b) and Q15 of `contracts/ENTRYPOINTS.md`.
7. **The module state.** `api/engines.py` names EP4 (`RESIDUES`) but does not discover it, and reports the `residues` module as not built. With this unit merged the function exists, so the runner can discover it like the others and report its state. Until it does, nothing in the response changes. **One test of `api/` fails once this unit lands:** `api/test_engines.py::test_the_carbon_engines_written_not_built_do_not_exist_yet[EP4]` checks on purpose that EP4 does not exist ("When one lands, this fails: the runner must then discover and call it"). This unit may not touch `api/`, so the change to that test, or the runner change it asks for, lands with or right after this unit, from lane L2a.
8. **D109 phases.** EP4 lays out the same phase as EP1, the one that starts with the calendar's first year, so the ledger and EP1 agree. A phase argument would reach EP4 the same way as EP1.

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
| `test_undated_harvest_leaves_the_years_it_may_fall_in_missing` | A component without an end date: its entries have no year and its crop's years are missing, naming it |
| `test_year_without_a_harvest_of_a_crop_is_zero` | A two-year cycle: the year without a harvest of a crop is zero, the other one is its value |
| `test_ledger_without_years_says_why` | No daily series (`MISSING_INPUT`) or no whole year (`NO_COVERAGE`): no years, no entries |
| `test_series_load_into_carbon_forcing_unchanged` | The series load unchanged into a `CarbonForcing` whose horizon is those years; their unit is the ledger's, not the one AMG requires |
| `test_ledger_round_trips_and_arguments_are_not_changed` | The same result twice, a JSON round trip, and arguments unchanged (G1) |
| `test_wrong_argument_types_and_other_field_raise` | `TypeError` for a wrong type, `ValueError` for another `field_id` (G5) |
| `test_signature_is_the_one_of_entrypoints` | The argument names and the keyword-only `parameters` |
| `test_records_have_the_units_of_the_readme` | The records use the three units, and each identifier is in this file |
| `test_readme_lists_the_cases_of_this_file` | This list and the file name the same cases |

## OPEN

Each item is a question a person answers; the role is named.

1. **The identifiers shared with #218: settled, a note only.** `rusle2_residue_yield_ratio` and `rusle2_crop_yield` (scope `crop`; `dimensionless` and `kg ha-1`) are the two records of D129 (c), with the identifiers fixed by #218 (`l0/erosion-c-main-route`, PR #229). The ledger and the computed `C` read the same records. No question is left here.
2. **One yield record, two units.** #218 needs the residue mass in `lb acre-1` (the unit of α, with a cited conversion record). This engine reads the yield in `kg ha-1`, as the records will arrive, and converts nothing. #218 converts it with its own record `mass_per_area_kg_ha_to_lb_acre`, which this engine does not read. Also open: whether every yield record is dry matter (the record has no field that says so; the unit string cannot), and whether the ratio of AH703 Table 5-1 is mass per mass. If it is not, `dimensionless` does not hold and a conversion record is needed. CITATION NEEDED. For the lead developer and the science reviewers.
3. **Units and bounds.** The ledger is in `kg ha-1` (dry matter) and `kg C ha-1`, as the orchestrating session of #220 set them. Nothing is converted, and another unit is `NOT_COMPUTABLE` (as in `engine/amg/`; the reason code for a unit is Q11). Two consequences: C1.1 lists `t` and `t C`, not `kg`, so the unit strings need C1.1 to accept them; and AMG requires `t C ha-1` for a carbon input, so the series do not reach AMG without a conversion. Who converts, and with which record (a unit change, not a value of the method, but still a number in code), is for the lead developer and the platform developer. A fraction outside zero to one, or a negative mass, ratio or carbon, is `NOT_COMPUTABLE`. Both rules are PROPOSED. For the lead developer.
4. **Roots and rhizodeposits.** Here they are records of their own, by crop, independent of the yield. A partition form, for example a root-to-shoot ratio or a share of the aboveground carbon, would be a record value with a cited source. CITATION NEEDED. Whether the roots of a crop are counted at harvest and in full, and whether rhizodeposits are given as carbon, are for the science reviewers.
5. **Cover crops and pastures.** No method is decided for their residue, so their values are `NOT_COMPUTABLE`. The calendar also does not say whether a cover crop's end date is its termination. For the lead developer and the science reviewers.
6. **When a residue enters the soil.** Here the whole carbon of a component enters in the agricultural year of its harvest. That covers the aboveground residue, the roots and the rhizodeposits. A year without a harvest of that crop and purpose is zero, a value and not a stand-in, so that AMG receives "no input" as a value (OPEN 6 of `engine/amg/README.md`). Spreading the input over the months of the component, or over the next year, is not done. For the lead developer and the science reviewers.
7. **Export when `removed` is declared.** The share removed is the record `residue_removed_fraction` by crop. "Removed" is not read as "all of it". `left_on_surface` and `incorporated` both retain everything, and the ledger copies the word, so a carbon model could tell them apart later. For the lead developer.
8. **The period of the record** is the days every daily series covers, as the platform reads it for the forcing. EP1 reads its `precipitation` series (Q5: which series marks the record for each engine). For the lead developer and the platform developer.
9. **Records scoped by crop only.** A crop sown as grain in one rotation and as a cover in another shares its records, but only `grain` components read them. Whether a scope key `management` or `stage` is needed is question 5 of `params/README.md`. For the lead developer.
10. **The types table and summary row of `contracts/ENTRYPOINTS.md`.** The row of `"ResidueLedger"` in "Types used in the signatures" and the EP4 row of the summary still say `OPEN`. The brief let this unit change only the EP4 section and Q13, so a one-line follow-up updates them. For the lead developer.
