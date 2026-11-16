# Validation fixtures

Signed files that hold the expected values of a check of `docs/VALIDATION.md` together with the inputs and constants the check needs, read by the test of that check. Unit `l0/validation-h2-e3-ready` (issue #225).

> **Status: PROPOSED.** The paths, the field lists and the skip rule below were written by a builder session (blueprint, section 3.7). They take effect only when a person approves the pull request. The expected values and the tolerances are those of decision D124 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886937443), amended for two H2 steps by [D138 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887623727). This README holds no value of a source: the values are in the signed files, checked against the source by the person who signs.
>
> **Five signed fixtures are indexed here** (`checked_by` filled under D34, D66):
>
> - `e3_ah703_tables.json` (`#238`, `[E3]`), `h2_example18.json` (`#239`, `[H2]`), and `h1_fao56_example37.json` (`#455`, `[H1]`, [D228](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893079768)), each with `checked_by` filled (and parameter records signed where applicable, D34, D66). All three checks run and pass.
> - `fao56_example35_surface_layer.json` (`#515`): signed FAO-56 Chapter 7, Example 35 (corrected February 2006 edition) surface-layer fixture (`checked_by: gbarbozamar`), with `early_wetting_option`, `full_precision_interpolation`, `half_digit_criterion` (half-last-digit comparison), and `surface_only_scope` accepted by `gbarbozamar` after seeing the comparison results (`results_seen_before_acceptance: true`, `retroactive_preregistration: false`, `full_ep3_reproduction: false`). `engine/water/evaporation/surface_layer.py` `step` itself remains unchanged pending L1 integration review.
> - `h10_grahmann2022_runoff.json` (`[H10]`): signed numeric transcription of Grahmann et al. (2022), Table 5 (`2017`–`2019`, `checked_by: gbarbozamar`, `transcribed_by: AI session, 2026-11-15`) and `year_basis_checked_by: "gbarbozamar"` signed per [D262](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6905528847) under explicit `evidence_limit` (no raw event timestamps), while `[H10]` is formally **`not evaluated in this release (D262)`** (`BLOCKED_NOT_EVALUATED`) because plot-specific rain-gauge series, 2017–early-2018 dates, and plot HSG/CN/hydraulic records are unavailable.

| File | Check | Test that reads it |
|---|---|---|
| `h1_fao56_example37.json` | [H1]: the ten-day stressed soil water balance against FAO-56 Chapter 8, EXAMPLE 37 | `engine/water/balance/test_bucket.py::test_h1_public_reference_case` |
| `h2_example18.json` | [H2]: the daily reference evapotranspiration against FAO-56 Chapter 4, EXAMPLE 18 | `engine/water/et0/test_h2.py::test_h2_worked_example_18_of_fao_56` |
| `e3_ah703_tables.json` | [E3]: `LS` against AH703 Table 4-2 and `m` against the Moderate column of Table 4-5 | `engine/erosion/test_ls.py::test_e3_slope_length_and_steepness_against_published_values` |
| `fao56_example35_surface_layer.json` | FAO-56 Chapter 7, Example 35 (corrected Feb 2006): surface-layer evaporation (`#515`; `results_seen_before_acceptance: true`, `surface_only_scope`, `full_ep3_reproduction: false`) | `engine/water/evaporation/test_surface_layer.py::test_fao56_chapter_7_worked_example` |
| `h10_grahmann2022_runoff.json` | [H10]: Grahmann et al. (2022) Table 5 yearly runoff & rainfall (`2017`–`2019`) and D230 criteria (`checked_by` & `year_basis_checked_by: gbarbozamar` per D262; `[H10]` `not evaluated in this release`) | `validation/test_h10_fixture_gate.py` (fixture & gate checks; `validation/test_h10_runoff.py` tests `validation/h10_runoff.py` on hand-made values) |

## Skip rule (`h1_fao56_example37.json`, `h2_example18.json`, `e3_ah703_tables.json`)

A test **skips**, with a reason that names its file and every part that is not signed, when:

- the file is absent; or
- the `checked_by` of the file is empty or missing; or
- a parameter record the file carries (the constants and bounds of H2, the unit length of E3) is absent or has an empty `checked_by`.

Once everything is signed the test **runs**. From then on a malformed file, a value outside its tolerance, or a tolerance that is not the one of D124 (or of D138, for its two H2 steps) is a **failure**, never a skip.

Each test also has cases that write a PLACEHOLDER fixture to a temporary folder (`tmp_path`) and show that the loader and the comparison run and pass, and that a value outside its tolerance fails. Those PLACEHOLDER numbers are made up or computed by the engine itself; none is a value of a source.

## Common fields (`h1_fao56_example37.json`, `h2_example18.json`, `e3_ah703_tables.json`)

These fields appear in `h1_fao56_example37.json`, `h2_example18.json`, and `e3_ah703_tables.json`, as the scientific-integration session writes them. The tests read `checked_by` only; the others are for the person who checks. (See the sections below for `fao56_example35_surface_layer.json` and `h10_grahmann2022_runoff.json`.)

| Field | Type | Meaning |
|---|---|---|
| `test` | text | The test that reads the file |
| `source` | object | `reference`, and in H1 and H2 also `locator`, `url` and `read` (the date the source was read) |
| `transcribed_by` | text | Who transcribed the values (D34) |
| `checked_by` | text | **The signature.** The person who checked every value of the file against the source (D34, D66). Empty means not signed |
| `tolerance_rule` | text | The rule of D124 in words |
| `tolerance_decided_by` | text | Who fixed the tolerance, and where it is recorded (D124) |

Any other field, such as `also_needed` or `not_printed_by_the_example`, is free text for the person who checks and is not read.

A **parameter record** below is a record in the format of `params/README.md` ("Record format"), checked with `params.catalogue.check_record` once signed. Records that the scientific-integration session prepared in that format are copied in unchanged.

## `h1_fao56_example37.json`

Read by `engine/water/balance/test_bucket.py::test_h1_public_reference_case` (via `h1_load_case` and `run_h1`). Carries no parameter records.

| Field | Type | Meaning |
|---|---|---|
| `inputs` | object | Exactly the six inputs (`H1_INPUTS`): `reference_evapotranspiration`, `crop_coefficient`, `root_depth`, `depletion_fraction`, `total_available_water`, and `initial_depletion` |
| `rows` | list | Non-empty ordered list of daily objects, one per day with `day` equal to `1, 2, 3 ...` in order (the ten days of Example 37) and exactly the three entries (`H1_COLUMNS`): `stress_coefficient`, `adjusted_crop_evapotranspiration`, and `depletion_end` |
| `tolerance` | object | `{column: absolute tolerance}`, one entry per column in `H1_COLUMNS`, in the unit of the column. D124 / [D228](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893079768): half a unit of the last digit of `printed`. The test recomputes each from `printed` (`h1_half_unit`) across every day and fails if the file says otherwise |

An **entry** of `inputs` or a column of `rows`:

| Field | Type | Meaning |
|---|---|---|
| `value` | number | Finite number. In `rows` (and in `inputs` when `printed` is given) it must equal `float(printed)` |
| `printed` | text | Required in every column of `rows`; optional in `inputs`. The number as printed by the example (`PRINTED`: optional minus sign, digits, optional point and decimals), so that its decimal digits give the tolerance |
| `unit`, `locator`, `verbatim`, `note` | text | For the person who checks; not read |

The top-level metadata fields `status`, `path_in_repository`, `printed_but_not_read`, `notes_of_the_table`, `readings_of_d228`, and `human_check_record` are unread metadata for the human checker.

What the test does with the file: following D228, it builds daily `DayInput` records with zero precipitation, zero runoff, zero `evaporation_coefficient` (`Ke = 0`), and `CropDay` from `crop_coefficient`, `root_depth`, and `depletion_fraction`; calls `run_balance` with `initial_storage = total_available_water - initial_depletion`, `capacity = total_available_water`, and `column_depth = root_depth`; computes `stress_coefficient`, `adjusted_crop_evapotranspiration` (`transpiration + evaporation`), and `depletion_end` (`capacity - storage_end`) for each day; and compares each against `rows` within the D124/D228 half-last-digit tolerance (`h1_half_unit`). Any `Missing` output fails the test.

## `h2_example18.json`

| Field | Type | Meaning |
|---|---|---|
| `inputs` | object | Exactly the eight inputs of `reference_evapotranspiration_day`, each an entry (below): `day_of_year`, `elevation`, `temperature_max`, `temperature_min`, `actual_vapour_pressure` (the row of Eq. 17), `wind_speed_2m` (the row of Eq. 47), `solar_radiation` (the row of Eq. 35), and the latitude as **one** of `latitude_radians` or `latitude_degrees`. A latitude in degrees is converted by FAO-56 Eq. 22 (degrees times pi over 180), a definition, not a value of the example |
| `steps` | object | The rows the example prints, one entry per field of `Et0Steps` it prints. Must include `reference_evapotranspiration`. A name that is not a field of `Et0Steps` fails. A step the example does not print is left out and not compared |
| `tolerance` | object | `{step: absolute tolerance}`, one per step, in the unit of the step. D124: half a unit of the last digit of `printed`; `soil_heat_flux` exactly, so `0`. [D138 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887623727), which amends D124 after results were seen: **one** unit of the last digit of `printed` for `vapour_pressure_deficit` and `net_shortwave_radiation` only. The test recomputes each from `printed` and fails if the file says otherwise, so a fixture that widens any other step fails |
| `constants` | list | The 31 parameter records of `Et0Constants`, one per field, by the identifiers EP3 reads: `<field of Et0Constants>_<field of its class>`, as `ET0_PARAMETERS` of `engine/water/exposure.py` builds them (for example `net_longwave_stefan_boltzmann`). Each signed in its own `checked_by` |
| `bounds` | list | The two parameter records of D82, by the identifiers of `ET0_BOUND_PARAMETERS` of `engine/water/exposure.py`: `net_longwave_relative_shortwave_maximum` and `penman_monteith_minimum_wind_speed`. Each signed in its own `checked_by` |

An **entry** of `inputs` or `steps`:

| Field | Type | Meaning |
|---|---|---|
| `value` | number | The number. In `steps` it must equal the number written in `printed` |
| `printed` | text | Required in `steps`: the number exactly as the example prints it, digits and a point, so that its last digit gives the tolerance |
| `unit`, `verbatim`, `locator`, `note` | text | For the person who checks; not read |
| `candidates` | object | Free text; not read |

The other fields the drafts carry (`not_printed_by_the_example`, `printed_but_not_compared_by_the_test`, `also_needed`) are not read.

What the test does with the file: it builds `Et0Constants` and `Et0Bounds` from the records, runs `reference_evapotranspiration_day` on the inputs, and compares each step in `steps` with its tolerance. A step the engine does not compute (a `Missing`) fails.

## `e3_ah703_tables.json`

| Field | Type | Meaning |
|---|---|---|
| `table_4_2` | object | `locator`, `url`, `footnote` (text, not read) and `cells` |
| `table_4_2.cells` | list | Exactly the 91 cells of D124, each `{slope_percent, horizontal_length_ft, ls_expected, printed, check_sheet_row}`. No (slope, length) pair twice |
| `table_4_5_moderate_optional` | object | `locator`, `url`, `included` and `cells`. D124 includes the table, so `included` must be `true` |
| `table_4_5_moderate_optional.cells` | list | Exactly the 19 cells of D124, each `{slope_percent, m_expected_moderate, printed, check_sheet_row}`. No slope twice |
| `tolerance` | object | `{"ls": ..., "m": ...}`: the plus-or-minus of D124 for each table. The test fails if either is not the one of D124 |
| `length_unit` | object | `choice`: text, not read. `record`: the **parameter record** of the unit length, id `rusle_l_unit_length`, unit `ft` (D124 works Table 4-2 in feet), signed in its own `checked_by` |

In each cell, `printed` is the number exactly as the table prints it (digits, a point and decimals) and the expected value must equal it. `check_sheet_row` is for the person who checks; not read.

The draft of the scientific-integration session gives `length_unit.record` as the path of a separate record file. In this format the record itself is copied in, so that it is signed and checked with the file.

What the test does with the file: it reads `a1` to `a4`, `s_break` and `b1` to `b4` from the parameter catalogue (`params/records/`, empty scope) by the identifiers of the table in `engine/erosion/LS.md`, computes `LS = S * L` for each cell of Table 4-2 with `slope_steepness_factor` and `slope_length_factor` (slope in percent, length and unit length in feet), and `m` for each cell of Table 4-5 from `slope_length_factor` alone (at a length ten times the unit length, `L = 10 ** m`, so `m = log10(L)`). A coefficient absent from the catalogue fails the test once the fixture is signed.

## `fao56_example35_surface_layer.json` (`#515`)

Signed surface-layer worked-example fixture for FAO-56 Chapter 7, Example 35 (corrected February 2006 edition), added in `#515`. By explicit user acceptance (`gbarbozamar`), the methodological choices `early_wetting_option` (`wetting_ordering: de_after_wetting`), `full_precision_interpolation`, `half_digit_criterion` (`ACCEPTED_AFTER_RESULTS`), and `surface_only_scope` apply strictly to the surface-layer comparison (`early_wetting_step`) read by `engine/water/evaporation/test_surface_layer.py::test_fao56_chapter_7_worked_example` and `engine/water/evaporation/test_early_wetting.py`. Acceptance was recorded **after** viewing the comparison results (`results_seen_before_acceptance: true`, `retroactive_preregistration: false`, `full_ep3_reproduction: false`), and `engine/water/evaporation/surface_layer.py` `step` remains unchanged pending L1 integration review (D185, dryland regression, and column balance).

## `h10_grahmann2022_runoff.json`

Verified by `validation/test_h10_fixture_gate.py`. Carries the published Table 5 annual runoff and rainfall values for 2017–2019 (Grahmann et al. 2022) and the D230 criteria (`pbias_bound_percent: 25`, `event_cap_mm: 100`), with numeric transcription signed (`status: "SIGNED_TRANSCRIPTION_BY_EXPLICIT_USER_AUTHORIZATION"`, `checked_by: "gbarbozamar"`, `transcribed_by: "AI session, 2026-11-15"`).

| Field | Type | Meaning |
|---|---|---|
| `status` | text | `"SIGNED_TRANSCRIPTION_BY_EXPLICIT_USER_AUTHORIZATION"` |
| `checked_by` | text | Person who signed the numeric transcription (`"gbarbozamar"`) |
| `transcribed_by` | text | Who transcribed the table (`"AI session, 2026-11-15"`) |
| `source` | object | `reference`, `url`, and `locator` (Table 5 and six Wischmeier plots) |
| `aggregation` | text | States six-plot annual average; do not mix with LEELP1 or demo soil |
| `year_basis` | text | `"calendar_year_PER_D230_TO_BE_CHECKED"` |
| `year_basis_checked_by` | text | **Separate gate.** Signed `"gbarbozamar"` under D262 for the `2017–2019` calendar-year basis (`evidence_limit`: no raw event timestamps); empty blocks evaluation |
| `rows` | list | Three annual entries (`2017`, `2018`, `2019`) with `year`, `runoff_mm`, `printed`, `rainfall_mm`, and `locator` |
| `criteria` | object | D230 criteria (`pbias_bound_percent`, `event_cap_mm`, `source`) |
| `signature_record` | text | Reference to the external acceptance record |
| `checked_scope` | text | States signed numeric and `2017-01-01`..`2019-12-31` calendar-year scope (`D262`, `evidence_limit`) while `[H10]` remains `not evaluated in this release (D262)` |

**Gate rule:** signing `checked_by` and `year_basis_checked_by` (D262) still does not make `[H10]` evaluable in this release. `validation/test_h10_fixture_gate.py` enforces that `[H10]` remains `not evaluated` (`BLOCKED_NOT_EVALUATED`) while plot-specific inputs (unavailable plot rain-gauge series, 2017–early-2018 management dates, and plot HSG/CN/hydraulic records per D262) and an actual EP3 plot run are absent, and also verifies in `tmp_path` that an empty `year_basis_checked_by` still blocks evaluation.

## OPEN

1. ~~The validation store reports these files.~~ `DECIDED` (option A, chosen by the orchestrator session for the lead developer): `validation/records.py` leaves `fixtures/` directly below the root alone, as it leaves `examples/` (case S36 of `validation/test_layout.py`). *Lead developer.*
2. **Two formats for an expected value.** The store of `validation/README.md` keeps one expected value per record with its citation; these fixtures keep a whole worked example or table per file, with a signature for the file. Whether both stay, or the fixtures are later split into store records, is not decided. *Lead developer; science reviewers.*
3. **Which value of reference evapotranspiration.** D124 fixes it as the one of the Eq. 6 line of the example. The test cannot tell, from the file alone, that the row given is that line without writing the value here; the person who signs checks it.
