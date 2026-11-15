# Validation fixtures

Signed files that hold the expected values of a check of `docs/VALIDATION.md` together with the inputs and constants the check needs, read by the test of that check. Unit `l0/validation-h2-e3-ready` (issue #225).

> **Status: PROPOSED.** The paths, the field lists and the skip rule below were written by a builder session (blueprint, section 3.7). They take effect only when a person approves the pull request. The expected values and the tolerances are those of decision D124 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886937443); this folder holds no value of a source.
>
> **This folder holds no fixture yet.** The two signed files arrive in their own commit, after the lead developer signs them (D34, D66). Until then both tests skip.

| File | Check | Test that reads it |
|---|---|---|
| `h2_example18.json` | [H2]: the daily reference evapotranspiration against FAO-56 Chapter 4, EXAMPLE 18 | `engine/water/et0/test_h2.py::test_h2_worked_example_18_of_fao_56` |
| `e3_ah703_tables.json` | [E3]: `LS` against AH703 Table 4-2 and `m` against the Moderate column of Table 4-5 | `engine/erosion/test_ls.py::test_e3_slope_length_and_steepness_against_published_values` |

## Skip rule (both files)

A test **skips**, with a reason that names its file and every part that is not signed, when:

- the file is absent; or
- the `checked_by` of the file is empty or missing; or
- a parameter record the file carries (the constants and bounds of H2, the unit length of E3) is absent or has an empty `checked_by`.

Once everything is signed the test **runs**. From then on a malformed file, a value outside its tolerance, or a tolerance that is not the one of D124 is a **failure**, never a skip.

Each test also has cases that write a PLACEHOLDER fixture to a temporary folder (`tmp_path`) and show that the loader and the comparison run and pass, and that a value outside its tolerance fails. Those PLACEHOLDER numbers are made up or computed by the engine itself; none is a value of a source.

## Common fields

These fields are in both files, as the scientific-integration session writes them. The tests read `checked_by` only; the others are for the person who checks.

| Field | Type | Meaning |
|---|---|---|
| `test` | text | The test that reads the file |
| `source` | object | `reference`, and in H2 also `locator`, `url` and `read` (the date the source was read) |
| `transcribed_by` | text | Who transcribed the values (D34) |
| `checked_by` | text | **The signature.** The person who checked every value of the file against the source (D34, D66). Empty means not signed |
| `tolerance_rule` | text | The rule of D124 in words |
| `tolerance_decided_by` | text | Who fixed the tolerance, and where it is recorded (D124) |

Any other field, such as `also_needed` or `not_printed_by_the_example`, is free text for the person who checks and is not read.

A **parameter record** below is a record in the format of `params/README.md` ("Record format"), checked with `params.catalogue.check_record` once signed. Records that the scientific-integration session prepared in that format are copied in unchanged.

## `h2_example18.json`

| Field | Type | Meaning |
|---|---|---|
| `inputs` | object | Exactly the eight inputs of `reference_evapotranspiration_day`, each an entry (below): `day_of_year`, `elevation`, `temperature_max`, `temperature_min`, `actual_vapour_pressure` (the row of Eq. 17), `wind_speed_2m` (the row of Eq. 47), `solar_radiation` (the row of Eq. 35), and the latitude as **one** of `latitude_radians` or `latitude_degrees`. A latitude in degrees is converted by FAO-56 Eq. 22 (degrees times pi over 180), a definition, not a value of the example |
| `steps` | object | The rows the example prints, one entry per field of `Et0Steps` it prints. Must include `reference_evapotranspiration`. A name that is not a field of `Et0Steps` fails. A step the example does not print is left out and not compared |
| `tolerance` | object | `{step: absolute tolerance}`, one per step, in the unit of the step. D124: half a unit of the last digit of `printed`; `soil_heat_flux` exactly, so `0`. The test recomputes each from `printed` and fails if the file says otherwise |
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

## OPEN

1. ~~The validation store reports these files.~~ `DECIDED` (option A, chosen by the orchestrator session for the lead developer): `validation/records.py` leaves `fixtures/` directly below the root alone, as it leaves `examples/` (case S36 of `validation/test_layout.py`). *Lead developer.*
2. **Two formats for an expected value.** The store of `validation/README.md` keeps one expected value per record with its citation; these fixtures keep a whole worked example or table per file, with a signature for the file. Whether both stay, or the fixtures are later split into store records, is not decided. *Lead developer; science reviewers.*
3. **Which value of reference evapotranspiration.** D124 fixes it as the one of the Eq. 6 line of the example. The test cannot tell, from the file alone, that the row given is that line without writing the value here; the person who signs checks it.
