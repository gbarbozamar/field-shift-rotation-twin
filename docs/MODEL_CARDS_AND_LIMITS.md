# Model Cards and Declared Limits

**Snapshot:** repository state `49504ac` (`main`).

**Scope:** standardized technical model cards, verification status, parameter readiness, and declared limits for every engine entry point (`EP1`–`EP6`), the platform runner and climate classification (`api/`, `adapters/`, `kinds_of_year/`), the table decision layer (`decision/`), and the plant/economics evaluation layer (`economics/`, `api/plant.py`).

> **Strict grounding notice:** Every file path, function signature, parameter count, validation code, and decision reference below reflects only what is present on `main` (`49504ac`). No parameter value is invented, and no water or soil-carbon output is simulated here. Where design choices or contract items await formal sign-off, they are marked **`PROPOSED`** or **`OPEN`** (blueprint §3.7).

---

## Contents & Legend

- **Statuses:**
  - **`DECIDED`** — settled in issue `#77` (or contract conventions) by a person with authority for that lane.
  - **`PROPOSED`** — implemented and tested by an engineering unit under blueprint §3.7; takes formal effect on human PR review/approval.
  - **`OPEN`** — unresolved scientific, parameter, or contract question requiring human judgment.
  - **`CITATION NEEDED`** — modelling assumption recorded for human literature/source verification.
- **Entry-Point Numbering Note:** In [ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md), `EP1`–`EP6` are `compute_soil_loss` (`EP1`), `build_rotation_calendar` (`EP2`), `compute_water_deficit_exposure` (`EP3`), `build_residue_ledger` (`EP4`), `run_amg` (`EP5`), and `run_rothc` (`EP6`), alongside two unnumbered public L1 helpers (`daily_reference_evapotranspiration` and `live_crop_by_day`). Platform orchestration (`api/`, `adapters/`) and climate year classification (`kinds_of_year/`) are documented in Card 7 immediately after `EP6`.
- **Parameter Catalogue Snapshot (`49504ac`):**
  - `params/records/` holds **132 signed JSON records**: **26** root erosion records, **6** shared residue/yield records in `params/records/residues/`, and **100** water records in `params/records/water/` (`45` from `#262`, `43` from `#417`, `12` from `#446`).
  - `params/withdrawn/computed_c/` holds **61 withdrawn** signed computed-`C` records moved out of the deployed catalogue under `D148`/`D158`/`D164`.
  - **`params/drafts/` does not exist on `main` (`49504ac`).** Unsigned parameter values reside outside the repository until person-checked and signed (`D34`, `D66`); parameter identifiers and unit expectations are documented in engine READMEs and [params/README.md](../params/README.md).
- **Validation Snapshot (`49504ac`):** Four protocol runs are recorded in `validation/runs/`. The latest, [run-20261115T170110Z-df43899.json](../validation/runs/run-20261115T170110Z-df43899.json), records **498** protocol-store results (**497** passed, **1** skipped `[H8]`) and **6,507** full-suite pytest passes (**16** skipped, **3** xfailed). Active test codes in [VALIDATION.md](VALIDATION.md) are `[E0, E1a, E1b, E2, E3, E7, E8, E9]`, `[H0, H1, H2, H5, H7, H8, H10]`, `[D0, D1, D2, D3, D4, D5, D6, D7, D10, D12]`, plus uncoded context checks (`EP4` Paysandu context; `AMG` vs. `LEELP1` exploratory contrast). Codes `E4`–`E6`, `E10`–`E11`, `H3`–`H4`, `H6`, `H9`, `H11`–`H12`, and `W0` do not exist in [VALIDATION.md](VALIDATION.md).

---

## Card 1 — `EP1`: Soil Loss (`engine/erosion/`)

- **Status:** **`PROPOSED`** ([ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md); [SOIL_LOSS.md](../engine/erosion/SOIL_LOSS.md)). Lane: `L1` (engine) / `L0` (computed `C` main-route switch & catalogue withdrawal).
- **Primary Module:** `engine/erosion/soil_loss.py` (`ls.py`, `equation.py`, `r_factor/`, `c_factor/`, `_parameters.py`).

### Purpose
Estimates sheet and rill water erosion (`soil_loss`) per agricultural year and per calendar month (`t ha-1 yr-1` and `t ha-1 month-1`) using RUSLE (`A = R * K * LS * C * P`).

### Contract Inputs & Outputs
- **Entry Point (`PROPOSED`):**
  ```python
  compute_soil_loss(
      calendar: RotationCalendar,
      climate: SiteClimate,
      soil_slope: SiteSoilSlope,
      *,
      parameters: dict[str, dict],
  ) -> SoilLossResults | Missing
  ```
  - Off-main-path sibling with identical signature: `compute_soil_loss_daily_index` (reads daily precipitation erosivity index and daily residue/canopy `c_factor/`, `PROPOSED`).
- **Inputs read:**
  - `calendar`: `ag_year_start` (`month`, `day`), `feasibility`, `components` (for computed `C`), `case_id`, `field_id`, `rotation_id`.
  - `climate`: `precipitation` daily series (`mm day-1`), used solely to determine agricultural-year and calendar-month `NO_COVERAGE` boundaries on the main route (`M1.2` daily precipitation values are not read on the main route).
  - `soil_slope`: `slope_steepness` (`%` / `degrees`) and `slope_length` (`m`); `rusle_k_factor` in `soil_properties` is not read by `EP1` today (read from `parameters`).
  - `parameters`: keyword-only `dict[str, dict]`, no default (`G3`).
- **Outputs:**
  - `SoilLossResults`: one `AnnualSoilLoss` per agricultural year (`ag_year`, `t ha-1 yr-1`, direction `lower_is_better`) and 12 consecutive `MonthlySoilLoss` items per year (`t ha-1 month-1`), summing to the annual value when computable (`C1.2`).
  - Provenance on main route fallback: `DECLARED` when using `rusle_c_factor` (`C4.6`), `DERIVED` (`C4.3`) when computed from sub-factors; `range_missing` `NOT_AVAILABLE` (`Q6`).
  - Returns bare `Missing(reason="MISSING_INPUT")` if `ag_year_start` or daily `precipitation` series is missing (`Q4`). Returns `NOT_COMPUTABLE` on all items if calendar is infeasible (`G4`). Raises `TypeError` on non-model arguments or bad `parameters`; `ValueError` on `case_id`/`field_id` mismatch (`G5`).

### Scientific Basis & Decisions (`#77`)
- **Method (`M1.1`–`M1.8` in [METHODS.md](METHODS.md)):**
  - **Main route (`D69`, `D84`, `D101`, `D129`):** Annual `R` is the mean annual `rusle_r_factor` (`USER-G`); monthly `R` splits the annual value using 12 climatological monthly erosivity fractions (`D84`, `D101`, GloREDa); `LS` follows AH703 Table 4-1 / Renard et al. (1997) with slope-break piecewise exponent (`D68`, `ls.py`); `K` uses the Uruguayan mixed-model class mean (`D70`, `D100`, `D112`); `P` is read from `parameters` (no hardcoded no-till default `1` in code).
  - **Computed `C` vs. Fallback (`D125`, `D129`, `D148`, `D158`, `D164`, `D213`):** Main route attempts computed `C` from crop canopy series (`day_<N>`), no-crop canopy records (`D143`), residue mass/decay, `rusle2_residue_yield_ratio`, `rusle2_crop_yield`, and unit conversion (`D129`). When any computed-`C` record is missing (including the deployed `49504ac` catalogue after `D158`/`D164`), it falls back to declared `rusle_c_factor` (`D125`), yielding **`2.365 t ha-1 yr-1`** across phases for both La Estanzuela demonstration rotations (`D146`, `D148`, `D213`), with all 67 computed-`C` records still verified together in memory.
  - **Required D148 Label (carries on real values in Plant answer per `D250`):**
    `"based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)"`.
  - **Off-main-path daily index (`PC-1`–`PC-3`, `PC-7`):** Uses `r_factor/` daily threshold/exponent and `c_factor/` daily ratio (`S1` Eq. 6.5–6.6), averaged by month (`PC-3`), omitting the `M1.2` control regression (`PC-7`).

### Parameter Status (`49504ac`)
- **Signed in `params/records/` (32 erosion/shared records):**
  - **26** root erosion records (`scope {}`): `10` `LS` records (`rusle_ls_*` + `rusle_s_break_*`), `rusle_r_factor` (Colonia), `12` GloREDa monthly `rusle_r_monthly_erosivity_<month>`, `rusle_k_factor` (`T Brunosol`), `rusle_c_factor` (declared fallback `D125`), `rusle_p_factor`.
  - **6** shared records in `params/records/residues/`: `rusle2_crop_yield` and `rusle2_residue_yield_ratio` for `soybean`, `wheat`, `maize` (`D164`).
- **Withdrawn (`params/withdrawn/computed_c/`):** **61** signed computed-`C` records moved out of the deployed catalogue by `D148`/`D158`/`D164` (`D213`), keeping computed `C` inactive in the deployed service while testable in memory.
- **Outside catalogue:** User-declared soil-loss limits (`soil_loss_tolerance` / `DeclaredLimit`) are per-field user inputs, not catalogue records.

### Validation Status (`49504ac`)
- **Passing in [run-20261115T170110Z-df43899.json](../validation/runs/run-20261115T170110Z-df43899.json):**
  - `[E0]` (erosion trivial comparator logic & ordering rules, `D211`)
  - `[E2]` (order between systems logic & comparator, `D225`)
  - `[E3]` (`engine/erosion/ls.py` vs. AH703 **Tables 4-2 and 4-5**, `91` `LS` cells and `19` `m` values in signed fixture `e3_ah703_tables.json`, `D124`)
  - `[E8]` (`annual_soil_loss` unit guard — `EQ6`, `EQ8`, `EQ10`, `D226`)
  - `[E9]` (`annual_soil_loss` mathematical invariants — `EQ1`–`EQ5`, `EQ7`, `D226`)
- **Not evaluated / No result record in Run #4 (`df43899`):**
  - `[E1a]` (official national erosion program comparison) and `[E1b]` (published plot ratios): **`not evaluated in this release (D254)`** (no test and no result record).
  - `[E7]` (runoff-plot plausibility observation, `D252`/`D148`): **`2.365 t ha-1 yr-1`** (declared `C`) vs. **`0.392 t ha-1 yr-1`** measured on La Estanzuela plots in 2017–2019; reported as an observation with **no pass rule** and **no test / result record** (`137Cs` national-context citation recorded, not numerically asserted).
- **Not defined in `VALIDATION.md`:** `E4`–`E6`, `E10`–`E11`.

### Declared Non-Claims & Limits
- Deployed `EP1` uses declared `rusle_c_factor` (`D125`/`D213`), so **different crop rotations on the same field produce identical soil loss** (`2.365 t ha-1 yr-1` on the demo soil) and carry no inter-annual rainfall variation (`USER-G`, `D84`, `D101`).
- Computed `C` (`~24.4 t ha-1 yr-1` with withdrawn `C` records) and declared `C` (`2.365 t ha-1 yr-1`) both substantially exceed the Grahmann et al. (2022) La Estanzuela no-till measurement (`0.392 t ha-1 yr-1`, `[E7]`); `EP1` carries no uncertainty range (`Q6`).
- `soil_slope` example ([la_estanzuela_soil_slope.json](../data/demo/la_estanzuela_soil_slope.json)) uses Wischmeier plot geometry (`22.1 m`, `4.5 %`) paired with `T Brunosol` class mean `K` (`0.03`, `±1 SD` `0.019`–`0.041`), not a site-measured `K` (`D70`, `D112`), and carries `"example_data": true`.
- Unit checking on `LS` coefficients and daily-index exponent is not enforced (`OPEN 15`); `example_data` flag does not propagate into `SoilLossResults` (`OPEN 10`).

---

## Card 2 — `EP2`: Rotation Calendar (`engine/calendar/`)

- **Status:** **`PROPOSED`** ([ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md); [engine/calendar/README.md](../engine/calendar/README.md)). Lane: `L1`.
- **Primary Modules:** `engine/calendar/build.py`, `engine/calendar/repeat.py`.

### Purpose
Resolves a producer's `RotationDefinition` (month/day components) into concrete dated `RotationCalendar` cycles (`build_rotation_calendar`) and provides phase-shifting (`phase_calendar`, `list_phases`) and multi-year record repetition (`repeat_over_record`) for downstream engines.

### Contract Inputs & Outputs
- **Entry Point (`PROPOSED`):**
  ```python
  build_rotation_calendar(rotation: RotationDefinition) -> RotationCalendar
  ```
- **Additional Public Helpers (`engine/calendar/repeat.py`, `PROPOSED`):**
  - `repeat_over_record(calendar: RotationCalendar, record_start: IsoDate, record_end: IsoDate) -> RepeatedRotation | Missing`
  - `list_phases(calendar: RotationCalendar) -> list[int]`
  - `phase_calendar(calendar: RotationCalendar, p: int) -> RotationCalendar`
  - `components_crossing_phase(calendar: RotationCalendar, p: int) -> list[str]`
- **Inputs:** `RotationDefinition` (`case_id`, `field_id`, `rotation_id`, `components`, `ag_year_start`, optional `planting_windows` / `notes`). Takes **no `parameters`** (`D56`).
- **Outputs:** `RotationCalendar` with `start_date`, `end_date`, `ag_year_start` (copied from `rotation` `P6`), `components` (`start_date`, `end_date`, `crop_id`, `period_type`, or missing reasons `C3.2`), and `feasibility` (`feasible: bool`, `violations`).
- **Failure / Refusal behavior:** Raises `TypeError` if argument is not `RotationDefinition`; raises `NoValidCalendarForm` when `ag_year_start` is missing (`D7`, `D8`) or a component's start/end date is missing (`P1`–`P12`). No internal exception is swallowed; invalid rule combinations return `feasibility.feasible = False`.

### Scientific Basis & Decisions (`#77`)
- **`D8`, `P1`–`P12`:** Deterministic placement on concrete dates (`year` / month / day), validating `RULES` (`harvest_not_before_sowing`, `positions_number_the_components`).
- **`D47`, `D109`, `D132`:** Repeats one cycle over the entire climate record; exposes `N` phases (`phase_1`..`phase_N`) each starting in the first agricultural year of the record so downstream engines remain phase-agnostic (`D56`).
- **`D141` (amends `D133`) & `D188` part 2 (`#403`):** Every phase `0..N-1` runs without refusal; components crossing into phase `p`'s first agricultural year keep missing start/end dates (`NOT_COMPUTABLE`, naming `D141`), while `repeat_over_record` lays out a lead-in cycle whenever the first cycle starts after the first day of the record's agricultural years (`D188` part 2).

### Parameter Status (`49504ac`)
- Reads **0** parameter catalogue records.

### Validation Status (`49504ac`)
- Covered by unit tests (`engine/calendar/`) and runner chain tests (`CH01`–`CH07` in `validation/test_chain_examples.py`). No standalone `[E]/[H]/[D]` code in [VALIDATION.md](VALIDATION.md).

### Declared Non-Claims & Limits
- **No agronomic feasibility rules on `main` (`49504ac`):** Only `harvest_not_before_sowing` and `positions_number_the_components` are enforced (`OPEN 1`–`18`); overlapping components, minimum gaps, or agronomic sequence constraints are not checked.
- **`repeats` flag ignored in repetition (`OPEN`):** `repeat_over_record` repeats a rotation even if `RotationDefinition.repeats` is false.
- **Leap day handling (`OPEN`):** `29 February` maps to `28 February` in non-leap years.
- **Crossing multi-year components (`D190`):** A component spanning across two cycles (e.g., 24-month alfalfa) cannot be placed whole in phases where it crosses the start boundary and comes back `NOT_COMPUTABLE` (`phase_calendar`), making those phases uncomputable in `EP3` (`D190`).

---

## Card 3 — `EP3`: Water Deficit Exposure (`engine/water/`)

- **Status:** **`PROPOSED`** ([ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md); [EXPOSURE.md](../engine/water/EXPOSURE.md)). Lane: `L1`.
- **Primary Modules:** `engine/water/exposure.py`, `reference_et0.py`, `living_crop.py`, `stages.py`, `fallow.py`, `et0/`, `runoff/`, `evaporation/`, `balance/`.

### Purpose
Computes agricultural-year dimensionless water deficit exposure (`water_transpired / water_demanded` = `sum(T_actual) / sum(T_potential)` over living-crop days `D157`, where `1.0` means full demanded transpiration met) by chaining daily FAO-56 Penman-Monteith `ET0`, NEH-630 runoff, FAO-56 dual crop-coefficient surface-layer evaporation (with residue mulch reduction), and single-column soil water balance. Also exports daily `ET0` (`D256`) and daily living-crop state (`D222`) for `CarbonForcing`.

### Contract Inputs & Outputs
- **Entry Point (`PROPOSED`):**
  ```python
  compute_water_deficit_exposure(
      calendar: RotationCalendar,
      climate: SiteClimate,
      soil_slope: SiteSoilSlope,
      *,
      parameters: dict[str, dict],
  ) -> list[WaterDeficitExposure]
  ```
- **Beside `EP3` (Public Helpers):**
  - `engine.water.daily_reference_evapotranspiration(climate: SiteClimate, *, parameters: dict[str, dict]) -> dict[date, float | Missing]` (`D256`, **`DECIDED` interface / `PROPOSED` implementation**).
  - `engine.water.living_crop.live_crop_by_day(calendar: RotationCalendar, record_start: date, record_end: date, *, parameters: Mapping[str, dict]) -> dict[date, bool | Missing]` (`D222`, `PROPOSED`).
- **Inputs:**
  - `calendar`: repeated via `repeat_over_record` (`D47`); `soil_slope` is checked for `case_id`/`field_id` parity only (`soil_slope` physical fields are not read by `EP3` on `49504ac`, `OPEN 7`).
  - `climate`: daily `precipitation`, `air_temperature_max_2m`, `air_temperature_min_2m`, `dew_point_2m`, `wind_speed_2m`, `solar_radiation` (`CQ1`–`CQ7`).
  - `parameters`: keyword-only `dict[str, dict]`.
- **Outputs:**
  - `list[WaterDeficitExposure]` on `time_basis="ag_year"` (`dimensionless`, `higher_is_better` per `DIRECTION_OF` / `C1.3`), or a single `rotation`-basis `Missing` item if `ag_year_start` or `precipitation` is absent (`OPEN 2`).
  - Provenance: `SIMULATED` (`D215`, `C4.1`); `range_missing`: `NOT_AVAILABLE` (`D216`).
  - **Required D162/D215 Source Label Prefix:** starts verbatim with `"whole cycle, not critical period"` (`WINDOW_LABEL`, `D105`, `D162`), followed by the D157/D215 method clauses; does not list individual parameter record IDs or crop IDs (`OPEN 44`).

### Scientific Basis & Decisions (`#77`)
- **ET0 (`D44`, `D82`, `D256`, `PC-4`):** FAO-56 Penman-Monteith daily step with temperature/radiation bounds (`Et0Bounds`), `dew_point_2m` for actual vapour pressure (`D25`), and `elevation` fallback if atmospheric pressure is derived (`D30`, `M2.1`). `Tew` (`PC-6`) omitted as an unneeded control parameter.
- **Runoff (`M2.2`):** Adapted NEH 630 ch. 10 Curve Number without USDA 5-day antecedent moisture class switching (`PC-5`, `D124`–`D126` context).
- **Stages, Crops, & Tails (`D78`, `D79`, `D135`–`D137`, `D188`, `D190`):** Four FAO-56 Table 11 stage lengths (`initial`, `development`, `mid`, `late`) are placed from sowing and **truncated at harvest** (`D135`); days after late stage up to harvest run as fallow/tail (`D136`); root depth grows linearly over development (`OPEN 27`, `CITATION NEEDED` vs. Annex 8 Eqs. 8-1 to 8-3).
- **Fallow Mulch & Evaporation (`D106`, `D110`, `D111`, `D115`, `D185`, `D186`):** Surface residue cover reduces `TEW` by `5 %` per `10 %` cover (`D186`), keeping depletion across transitions (`D185`). No `Kcb` climatic adjustment (`FAO-56` Eq. 70) is implemented (`OPEN 4`, blocked on daily `RH_min` in `OPEN 3`).
- **Initial States & Restart (`D44`, `D189`):** Chain starts on the first day covered by all climate series from `initial_storage` and `initial_depletion` without pre-record spin-up (`D189`). Any refused/missing day turns `NOT_COMPUTABLE`/`MISSING_INPUT` and **never restarts** the balance for subsequent days (`OPEN 10`, `OPEN 41`). Zero annual demand yields `NOT_COMPUTABLE` (`D214`).

### Parameter Status (`49504ac`)
- **Signed in `params/records/water/` (`100` records total):**
  - `45` from `#262` (FAO-56 `et0/` constants & bounds + `Kcb` tables).
  - `43` from `#417` (site initial states, `minimum_relative_humidity`, `column_capacity`, `column_depth`, `field_capacity_water_content`, `wilting_point_water_content`, mulch reduction/increment, `soybean` stage lengths & parameters, `no_crop` parameters).
  - `12` from `#446` (`wheat` and `maize` `T1`–`T6` / `M1`–`M6`: `initial_root_depth`, `maximum_root_depth`, `readily_available_fraction`, `crop_height`, `cover_fraction_exponent`, `curve_number`).
- **Unsigned / Pending (`10` records in `#433`):** `wheat` and `maize` remain **`MISSING_INPUT`** on `49504ac` because `4` `fao56_stage_length_*` records for `wheat` + `4` for `maize` (`8`) and `2` `surface_residue_cover` fallow records before `wheat` and `maize` await signature (`#433`).

### Validation Status (`49504ac`)
- **Passing in [run-20261115T170110Z-df43899.json](../validation/runs/run-20261115T170110Z-df43899.json):**
  - `[H0]` (water trivial comparator logic & ordering rules, `D212`)
  - `[H1]` (`engine/water/balance/` `run_balance` vs. FAO-56 Ch. 8 Ex. 37 signed fixture `h1_fao56_example37.json`, `D228`)
  - `[H2]` (`engine/water/et0/` `reference_evapotranspiration_day` vs. FAO-56 Example 18 signed fixture `h2_example18.json`, `D124`/`D138`)
  - `[H7]` (daily balance mass closure `ΔS = P − Q − E − T − D`, `D227`)
- **Partial pass / 1 skipped in Run #4 (`df43899`):**
  - **`[H8]`** (daily balance invariants `D227` — `19` passing invariant checks + **`1` skipped** `test_h8_invariants_numeric_criteria`, recorded as `not_evaluated` in Run #4).
- **Not run / No result record in Run #4 (`df43899`):**
  - `[H5]` (NASA POWER `GWETROOT` qualitative contrast, `D107`/`D253`): **no pass rule** and **`not run`** in this release (`CQ7` not wired; no result record).
  - `[H10]` (Grahmann et al. 2022 Table 5 yearly runoff contrast, `D229`/`D230`): comparator machinery (`validation/h10_runoff.py`) and synthetic tests exist, but **no signed fixture (`h10_grahmann2022_runoff.json` absent)** and **no `EP3` plot run** (no result record).
- **Not defined in `VALIDATION.md`:** `H3`, `H4`, `H6`, `H9`, `H11`, `H12`, `W0`.
- **Unverified on real demo run:** No simulated real water deficit exposure outputs are published or validated yet; D189 convergence check (empty vs. full initial state across phases) is not built (`OPEN 14`); REW×Ze sensitivity grid (`D102`) is not run (`OPEN 24`).

### Declared Non-Claims & Limits
- **Zero outputs for rotations with `wheat` or `maize` on `49504ac`:** Missing `#433` records force `MISSING_INPUT` from the first `wheat`/`maize` day onward (`balance` never restarts).
- **End-of-record fallow (`D187`, `OPEN 41`):** The final fallow/tail whose next sowing lies past the record end has no following crop and turns `MISSING_INPUT` for the remainder of the last agricultural year.
- **No `RH_min` daily series (`OPEN 3`) & no `Kcb` wind/humidity adjustment (`OPEN 4`):** Site-constant `minimum_relative_humidity` is used in `evaporation/`.
- **No per-crop output (`D217`):** Only one combined agricultural-year ratio is reported (`C1.3`); critical-period windows (`D191`: soybean R4–R6, maize R1 ± 15 d) and sowing-window soil-moisture descriptors (`D50`, `C1.4`) are not built (`OPEN 16`).
- **Alfalfa/perennial caveat (`D190`):** Multi-year perennials receive one stage cycle and behave as fallow thereafter (understating transpiration), and phases where they cross the start boundary fail (`OPEN 29`, `OPEN 40`).
- **No fallback to single-`Kc` (`D44`):** Missing dual-`Kc` or surface-layer parameters leave years missing (`OPEN 15`). Unit strings in water parameter records are not checked by `EP3` (`OPEN 9`).

---

## Card 4 — `EP4`: Residue Ledger (`engine/residues/`)

- **Status:** **`PROPOSED`** ([ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md); [engine/residues/README.md](../engine/residues/README.md)). Lane: `L1`.
- **Primary Module:** `engine/residues/ledger.py`.

### Purpose
Maintains residue mass and carbon accounting at harvest and monthly/annual carbon input series (`t C ha-1` for `CarbonForcing.annual_carbon_inputs` and `monthly_carbon_inputs`) partitioned into aboveground and belowground components by origin.

### Contract Inputs & Outputs
- **Entry Point (`PROPOSED`):**
  ```python
  build_residue_ledger(
      rotation: RotationDefinition,
      calendar: RotationCalendar,
      climate: SiteClimate,
      *,
      parameters: dict[str, dict],
  ) -> ResidueLedger
  ```
- **Inputs:**
  - `rotation`: read for component types (`grain`, `cover`, `pasture`), `crop_id`, and `repeats`.
  - `calendar`: `ag_year_start`, `feasibility`, components repeated via `repeat_over_record` (`D47`).
  - `climate`: `precipitation` series for agricultural-year bounds (`NO_COVERAGE` / whole-year horizon).
  - `parameters`: keyword-only `dict[str, dict]`.
- **Outputs:**
  - `ResidueLedger`: per-component residue `Value` items and per-origin `annual_carbon_inputs` + `monthly_carbon_inputs` in **`t C ha-1`** (`D147`, converted from `kg C ha-1` using `1 t = 1000 kg`), with explicit zero months when no harvest occurs in a covered month (`D221`).
  - Grain crops compute aboveground retained carbon from `rusle2_crop_yield`, `rusle2_residue_yield_ratio`, `residue_carbon_fraction`, and optional `residue_removed_fraction` (read only when a component declares `removed`), and belowground carbon directly from `root_mass_at_harvest`, `root_carbon_fraction`, and `rhizodeposit_carbon` (no root-to-shoot partition ratio is used, `OPEN 4`); **`cover` and `pasture` components yield `NOT_COMPUTABLE`** (`OPEN 5` of `engine/residues/README.md`).
  - Returns `years_missing` when `ag_year_start` or `precipitation` is absent; an infeasible calendar yields `NOT_COMPUTABLE` (`G4`). Raises `TypeError`/`ValueError` on type or `case_id`/`field_id` mismatches (`G5`).

### Scientific Basis & Decisions (`#77`)
- **`D129(c)`, `D164`:** Shares `rusle2_crop_yield` and `rusle2_residue_yield_ratio` with `EP1`.
- **`D147`:** `EP4` owns the unit conversion to `t C ha-1` so `api/carbon_forcing.py` and `EP5`/`EP6` perform zero arithmetic or unit conversions on inputs.
- **`D194`, `D221`:** Harvest carbon enters in the harvest month (no surface decay pool in `EP4` feeding RothC, consistent with RothC assumption `D224`); non-harvest covered months emit `0.0 t C ha-1`.

### Parameter Status (`49504ac`)
- Reads **7** crop-scoped (`{"crop": "<crop_id>"}`) parameter identifiers:
  - **Signed in `params/records/residues/` (6 records = 2 IDs × 3 crops):** `rusle2_crop_yield` (`kg ha-1`) and `rusle2_residue_yield_ratio` (`dimensionless`) for `soybean`, `wheat`, `maize` (`D164`).
  - **Unsigned / Absent from `params/records/` (5 IDs):** `residue_carbon_fraction`, `residue_removed_fraction`, `root_mass_at_harvest`, `root_carbon_fraction`, and `rhizodeposit_carbon` (listed in [engine/residues/README.md](../engine/residues/README.md)). Until signed, `EP4` carbon series remain **`MISSING_INPUT`** on `49504ac`.

### Validation Status (`49504ac`)
- Covered by unit tests (`engine/residues/`), shared-catalogue guard (`engine/erosion/test_records_shared_with_residues.py`), and uncoded context entry in [VALIDATION.md](VALIDATION.md) (`EP4: context for the annual carbon inputs` — Paysandu long-term residue reference context only; no numeric validation code assigned).

### Declared Non-Claims & Limits
- **Not surfaced directly in `/api/rotations/run` (`Q15`):** Only feeds `CarbonForcing` internally (`api/README.md` `OPEN`).
- **`cover` and `pasture` always `NOT_COMPUTABLE`:** No residue model is implemented for non-grain crops (`OPEN`), blocking real carbon runs on rotations containing cover crops or pastures unless omitted/handled downstream.
- **No surface-residue cover hand-off to `EP1` or `EP3` (`Q12`):** `D116` intends `EP4`/erosion to own surface cover later; today `EP3` reads static `surface_residue_cover` and `EP1` falls back to declared `C`.
- **Constant static yields (`rusle2_crop_yield`):** Residue carbon inputs do not respond to `EP3` water stress or inter-annual weather (`OPEN`).

---

## Card 5 — `EP5`: Soil Organic Carbon — AMG (`engine/amg/`)

- **Status:** **`PROPOSED`** ([ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md); [engine/amg/README.md](../engine/amg/README.md); [contracts/carbon_forcing/README.md](../contracts/carbon_forcing/README.md)). Lane: `L1` / `L0`.
- **Primary Modules:** `engine/amg/entry.py`, `core` (`pools.py`, `modifiers.py`, `trend.py`).

### Purpose
Simulates annual soil organic carbon stock dynamics (`t C ha-1`) over whole agricultural years using the **AMGv2** two-pool (`active`, `stable`) exponential model (`Clivot et al. 2019`), returning step stocks/flows and rotation trend summaries (`t C ha-1 yr-1`, `higher_is_better`).

### Contract Inputs & Outputs
- **Entry Point (`PROPOSED`):**
  ```python
  run_amg(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance
  ```
- **Inputs read from `CarbonForcing` (`FORCING_QUANTITIES`, `PROPOSED`):**
  - `starting_state`: `soil_organic_carbon` (`t C ha-1`; no unit conversion, else `NOT_COMPUTABLE`).
  - `annual_carbon_inputs`: every series by `origin` (`t C ha-1` over the agricultural year).
  - `annual_climate`: `mean_temperature` (`D118`), `water_balance` (`D181`, `m`, `P + IW - ET0` with `IW=0`).
  - `soil_properties`: `clay_content`, `carbonate_content`, `ph`, `soil_cn_ratio` (`D193`).
  - Ignored by AMG-A: monthly `climate`, `carbon_inputs`, `soil_cover`. `soil_depth` (`20 cm`, `D180`) is copied unchanged.
- **Outputs (`CarbonBalance`, `variant="amg_a"`, `carbon_model="amg"`):**
  - `total_stock` (`soil_organic_carbon`), `pools` (`amg_active_pool`, `amg_stable_pool`), `flows` (`amg_humified_input`, `amg_mineralised_carbon`), and 3 `SoilCarbonTrend` values (`end_minus_start`, `fitted_slope`, `mean_over_cycles`).
  - Initial pools carry `DERIVED` (`C4.3`); step values and trends carry `SIMULATED` (`C4.1`); `range_missing`: `NOT_AVAILABLE` (`Q6`).
  - **`mean_over_cycles` is always `MISSING_INPUT`** (`CarbonForcing` carries no cycle boundaries, `OPEN 6`).
  - Trailing months after the last whole agricultural year produce one trailing `NOT_COMPUTABLE` step (`OPEN 12`). Once `starting_state` or any annual step is missing, all subsequent steps and trends are missing (`G4`).
  - **Required D210/D192 Verbatim Method Label Prefix:**
    `"AMGv2 soil carbon model (Clivot et al. 2019, Environmental Modelling & Software 118:99-113, https://doi.org/10.1016/j.envsoft.2019.04.004), yearly step. Parameters: the defaults of the AMGv2 parameters dataset v2.0 (https://doi.org/10.57745/MEQQIX), for average French arable crop conditions, not calibrated for the country of this site. The FAO-56 reference evapotranspiration stands in for the potential evapotranspiration (Penman 1948) of the source. Mean annual temperature of the calibration sites: 9.9 to 13.5 °C (Clivot et al. 2019, Table 1)."`

### Scientific Basis & Decisions (`#77`)
- **Formulation (`D80`, `D192`, `D210`):** AMG-A (`Clivot et al. 2019`, Eq. 5 & S7–S13) with `exponential` integration scheme (`D192`) and **6** rate modifiers (`temperature`, `moisture`, `clay`, `carbonate`, `ph`, `soil_cn_ratio`, `D192`/`D193`). Below `0 °C` annual mean temperature, mineralisation is cut to zero (`S8`).
- **Moisture forcing (`D181`):** Uses `P - ET0` (`IW = 0`), declaring FAO-56 `ET0` as substitute for Penman (1948) PET; Clivot et al. (2019) calibration bounds are `-290` to `595 mm yr-1` (`api/carbon_forcing.py` flags out-of-range years in `source`, still computing).

### Parameter Status (`49504ac`)
- **0** AMG records in `params/records/` (`49504ac`).
- **15** `amg_*` parameter IDs specified in [engine/amg/README.md](../engine/amg/README.md) (`amg_stable_fraction`, `amg_potential_mineralisation_rate`, `amg_humification_coefficient` scoped by `crop=origin`, temperature/moisture/clay/carbonate/pH/C:N parameters) remain outside `params/records/` awaiting transcription verification/signature (`D34`, `D66`).
- **Site properties missing on demo (`D120`, `D121`, `D182`, `D193`):** [la_estanzuela_soil_slope.json](../data/demo/la_estanzuela_soil_slope.json) carries only `rusle_k_factor` (`clay_content`, `carbonate_content`, `ph`, `soil_cn_ratio`, and starting `soil_organic_carbon` in `t C ha-1` are absent).

### Validation Status (`49504ac`)
- Core tests (`engine/amg/test_amg.py`, `test_entry.py`, `test_runner_response.py`) use `PLACEHOLDER` numbers only (worked-example tests skipped in absence of signed constants).
- **`AMG against LEELP1 (exploratory contrast)` ([VALIDATION.md](VALIDATION.md), `D234`):** Exploratory runs of the project's AMG functions against `LEELP1` (`González-Sosa et al. 2024`) were executed outside the repository and reproduced read-only on `main` using unsigned AMGv2 defaults (`65%` and `40%` stable fractions), `ET0` standing in for PET, and post-hoc filtering; recorded strictly as an exploratory observation with no pass rule and **explicitly NOT a validation of the project**. Zero AMG outputs are reachable through the deployed service (`params/records/` holds `0` AMG records).

### Declared Non-Claims & Limits
- **`AMG-M` (monthly variant) is NOT built (`OPEN 1`).**
- **Zero AMG trend values are reachable in the deployed service today** because neither the `15` `amg_*` records nor `EP4` unsigned residue parameters nor `D120`/`D121`/`D193` site soil carbon properties exist in `params/records/` or the demo soil file.
- **No uncertainty range (`Q6`) and no `mean_over_cycles` (`OPEN 6`).**
- **Stock/flow time series not returned in `/api/rotations/run` (`api/README.md` `OPEN`):** Only the 3 `soil_carbon_trend` rows enter `ResultsPerRotation`.

---

## Card 6 — `EP6`: Soil Organic Carbon — RothC (`engine/rothc/`)

- **Status:** **`PROPOSED`** in `engine/rothc/` & `api/engines.py` (listed as **`OPEN`** in [ENTRYPOINTS.md](../contracts/ENTRYPOINTS.md) status row pending L0 update; [engine/rothc/README.md](../engine/rothc/README.md)). Lane: `L1` / `L2`.
- **Primary Modules:** `engine/rothc/entry.py`, `pools.py`, `modifiers.py`, `equilibrium.py`, `trend.py`.

### Purpose
Simulates monthly soil organic carbon turnover (`t C ha-1`) across five pools (`DPM`, `RPM`, `BIO`, `HUM`, `IOM`) using standard **RothC-26.3** (`1990` formulation, `D64`), with inverse equilibrium spin-up (`D218`/`D219`) when only starting total `SOC` is supplied, returning monthly series and three rotation trend summaries (`t C ha-1 yr-1`).

### Contract Inputs & Outputs
- **Entry Point:**
  ```python
  run_rothc(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance
  ```
- **Inputs read from `CarbonForcing` (`FORCING_QUANTITIES`, `PROPOSED`):**
  - `climate` (monthly, `D220`): `rainfall` (`mm`), `mean_temperature`, and `open_pan_evaporation` or fallback `potential_evapotranspiration` (converted internally via `rothc_pan_evaporation_factor`, `D80`).
  - `soil_properties`: `clay_content`.
  - `soil_cover` (`D222`): `soil_cover_state` (`dimensionless`: `1.0` vegetated, `0.0` bare).
  - `carbon_inputs` (`D221`): monthly series by `origin` (`t C ha-1`).
  - `starting_state`: either all 5 pools (`rothc_dpm_pool`, `rothc_rpm_pool`, `rothc_bio_pool`, `rothc_hum_pool`, `rothc_iom_pool`) as `DECLARED`, OR total `soil_organic_carbon` alone to trigger equilibrium initialisation (`D218`/`D219`).
  - `soil_depth` (`D180`, `20 cm`).
- **Outputs (`CarbonBalance`, `variant="rothc_26_3"`, `carbon_model="rothc"`):**
  - `total_stock` (`soil_organic_carbon`), `pools` (`rothc_dpm_pool`, `rothc_rpm_pool`, `rothc_bio_pool`, `rothc_hum_pool`, `rothc_iom_pool`), `flows` (`rothc_carbon_input`, `rothc_co2_carbon`), and 3 `SoilCarbonTrend` items (`end_minus_start`, `fitted_slope`, `mean_over_cycles`).
  - Initial equilibrium pools carry `DERIVED`; step and trend values carry `SIMULATED`; `range_missing` `NOT_AVAILABLE` (`Q6`). `mean_over_cycles` is always `MISSING_INPUT` (`OPEN 6`).
  - **Required D224 Verbatim Method Label Prefix:**
    `"RothC-26.3, the 1990 standard formulation (D64); monthly FAO-56 reference evapotranspiration as the evaporative demand instead of open-pan evaporation × 0.75 (an adaptation, D80); Rothamsted parameters, not calibrated for the country of this site; starting pools from an equilibrium initialisation convention, with no claim that the soil is at equilibrium (D80); inert pool from Falloon et al. (1998), \"a very rough approximation\"; surface residue under no-till entered as a soil input."`

### Scientific Basis & Decisions (`#77`)
- **Monthly Order (`D149`, `D150`):** Carbon inputs enter before decomposition of that month (`D149`), and moisture modifier follows the month's own TSMD water balance (`D150`).
- **Equilibrium Mode (`D218`, `D219`):** Sets `IOM` via Falloon et al. (1998) (`p. 16`), computes the analytic fixed point of the cycled horizon (matching a 10,000-year run), and scales inputs by `(SOC - IOM) / (SOC_sim - IOM)` (`GSOCseq` eq. 5.1). Requires `total_carbon` present with none of the 5 pools (`OPEN 14`) and nonzero cycle decomposition/inputs.
- **Bare-soil TSMD (`D223`) & PET Adaptation (`D80`, `D220`):** Applies bare-soil TSMD divisor (`BareSMD`) only on bare drying months (`OPEN 15`); divides monthly FAO-56 `ET0` by `rothc_pan_evaporation_factor` (`0.75`) when pan evaporation is absent.

### Parameter Status (`49504ac`)
- **0** RothC records in `params/records/` (`49504ac`).
- **24** global `rothc_*` constants (`PARAMETERS` in `engine/rothc/entry.py`) plus **4** origin-scoped `rothc_input_*` composition parameters (`INPUT_PARAMETERS`, scoped by `crop=origin`) are transcribed in [engine/rothc/README.md](../engine/rothc/README.md) (`D63`/`D134`) but remain outside `params/records/` awaiting signed record creation (`OPEN 8`).
- Radiocarbon inert-pool alternative is not built (`OPEN 5`).

### Validation Status (`49504ac`)
- Reference-case test (`engine/rothc/test_reference_case.py`) verifies RothC Model Description (Feb 2024) §2.2 Jan 1852 reference pools to within printed rounding bound **`1e-4`** (`OPEN 10` resolved: max gaps `DPM 6.29e-05`, `RPM 5.23e-05`, `BIO 5.3e-06`, `HUM 5.0e-06`) and fixed-point convergence against a 10,000-year forward run (`test_equilibrium.py`). Uses transcribed constants in test memory only; **no Uruguay/La Estanzuela RothC simulations or `[E]/[H]/[D]` codes exist.**

### Declared Non-Claims & Limits
- **Zero RothC values are reachable on `49504ac`:** Missing `params/records/` RothC records, unsigned `EP4` parameters, and missing `soil_organic_carbon`/`clay_content` leave every RothC output `MISSING_INPUT`.
- **Single-day gap propagation:** A single missing daily rain or `ET0` day makes that entire calendar month—and all later months, plus equilibrium initial pools—missing (`D220`, `engine/rothc/README.md`).
- **No surface-residue pool & fallow-as-bare (`D222`, `D224`):** Under no-till, harvest residue enters soil immediately in the harvest month, and fallow covered with dead residue is treated as bare (`0.0`, `Cover=1.0` only when >50% of days have a living crop).
- **Large missing-detail payload (`api/README.md` `OPEN`):** Because `fitted_slope` lists every missing monthly stock (`277` months on `2001`–`2024`), uncomputed `rothc` missing rows expand `/api/rotations/run` responses (~`550,085` chars detail in `fitted_slope`, growing example JSON from ~`2.47 MB` to ~`3.58 MB`).
- **Unbounded temperature modifier (`OPEN 4`):** Rises past `1` above ~`9.3 °C` without an upper cap.

---

## Card 7 — Runner, Adapters & Climate Kinds of Year (`api/`, `adapters/`, `kinds_of_year/`)

- **Status:** **`PROPOSED`** ([api/README.md](../api/README.md); [adapters/README.md](../adapters/README.md); [kinds_of_year/README.md](../kinds_of_year/README.md)). Lane: `L2a` / `L2`.
- **Primary Modules:** `api/engines.py`, `api/phases.py`, `api/carbon_forcing.py`, `api/rotations.py`, `api/decisions.py`, `api/results_table.py`, `api/decision_layer.py`, `api/config.py`; `adapters/power.py`, `adapters/example_soil_slope.py`, `adapters/soil_tables.py`; `kinds_of_year/classify.py`, `kinds_of_year/aggregate.py`.

### Purpose
Orchestrates validation, site climate/soil retrieval, `N`-phase calendar expansion, sequential execution of `EP2 → EP1 → EP3 → EP4 → EP5 → EP6` (`api/engines.py`), construction of shared `CarbonForcing` (`api/carbon_forcing.py`), multi-rotation `ResultsTable` pairing (`api/results_table.py`), and ENSO agricultural-year classification/aggregation (`kinds_of_year/`).

### Contract Inputs & Outputs
- **HTTP Routes (`api/`):**
  - `GET /health`
  - `POST /api/rotations/run` (1 rotation, returns `outcome` `complete | partial | no_result`, `scenarios[]` by phase, top-level `phase_1`, `modules` in fixed order `calendar, erosion, water, residues, amg, rothc`, `sources[]`).
  - `POST /api/decisions/run` (**exactly 2 rotations**, enforces shared `ag_year_start.month` per `D255`, builds `N × M` phase scenarios per `D172`, invokes `assemble_decision_output` lazily via `DiscoveredDecisionLayer`).
  - `POST /api/plant/run` (3–5 rotations, calls `economics.plant` + `kinds_of_year` + optional rain stress, see Card 9).
- **Climate Adapter (`adapters/power.py`):** Fetches 7 daily series (`CQ1`–`CQ7`, `2001-01-01` to `2024-12-31` per `D23`–`D35`) from NASA POWER (`AG` community), caching on disk (`CLIMATE_CACHE_DIR`), mapping fill values to missing `NO_COVERAGE` (`D31`, `D36`). Requires explicit `POWER_SETTINGS_FILE` and `CLIMATE_*` env vars (no defaults, `ConfigError` on misconfiguration).
- **Soil Adapters (`adapters/`):** `ExampleSoilSlopeSource` (`D38`, serves example soil under any requested `case_id`/`field_id`, marking source `state="example"`), `SoilTableSource` (`D48`/`D49`, JSON tables + field group mapping; no real national tables committed due to licence/open questions).
- **ENSO Classification (`kinds_of_year/`):**
  - `load_record(path)` (no default path, **no ONI file in repo**), `classify_agricultural_years(record, start_month, first_year, last_year) -> list[KindOfYear]` (`el_nino`, `neutral`, `la_nina` or `NO_COVERAGE`/`MISSING_INPUT`), `count_kinds`, `deciding_season`.
  - `mean_by_kind`, `series_from_results` (`aggregate.py`) compute arithmetic unweighted means (`MeansByKind`) on `ag_year` series without ranges (`OPEN`).

### Scientific Basis & Decisions (`#77`)
- **Phase Runner (`D109`, `D117`, `D132`, `D141`, `D255`):** `EP2` runs once; `EP1`, `EP3`, `EP4`, `EP5`, `EP6` run on each `phase_calendar` (`phase_1` = unmoved `EP2` calendar). Pairwise `ResultsTable` compares every `phase_i+phase_j` combination (`D172`), requiring identical start month (`D255`).
- **`CarbonForcing` Assembly (`D62`, `D65`, `D118`–`D123`, `D147`, `D180`–`D181`, `D193`, `D220`–`D222`, `D256`):**
  - Built once per phase and shared identically by `EP5` and `EP6` (`D65`).
  - Calls `daily_reference_evapotranspiration` (`D256`) once per request and `live_crop_by_day` (`D222`, `>50 %` live days = `1.0`, else `0.0`, `brief #373`) once per phase.
  - Converts no units and fills no missing days (`C3.3`/`C3.4`). Note: `crop_id` values failing quantity-identifier regex `^[a-z][a-z0-9_]*$` cannot form carbon-input series and are omitted with count noted in `amg` module detail (`api/README.md` `OPEN`).
- **ONI Classification (`D240`, `D258`):**
  - Uses NOAA CPC **ERSST.v6** `±0.5 °C` for **≥ 5** consecutive overlapping 3-month seasons (`D240 (1)`).
  - Applies threshold to the **`printed`** 1-decimal table value stored explicitly in the record—**never** rounding 2-decimal `oni.ascii.txt` `anom` in code (`D240 (2)`, `D258`: half-away-from-zero disagrees on 50 of 89 `.x5` entries 1950–2025). Missing `printed` raises `MISSING_INPUT` (`D258`).
  - Agricultural year `Y` is decided by the 3-month season centred 6 months after `start_month` (`D240 (3)`, e.g. `DJF` of `Y+1` for July start, `CITATION NEEDED`).

### Parameter Status (`49504ac`)
- `api/config.py` loads `params/records/` (**132** signed records) at app start-up when run as service; empty `{}` if omitted in `EntryPointEngines`.
- `adapters/settings/nasa_power.json` exists; template placeholders exist under `adapters/examples/`. No national soil-group tables are committed (`SoilTableSource` unpopulated).
- **`oni_v6` ONI record is NOT in the repository (`49504ac`):** Marked `UNSIGNED_AI_PRECHECK` elsewhere awaiting human verification of `printed` values against the CPC v6 table (`D240 (5)`, `D258`, `D34`, `D66`).

### Validation Status (`49504ac`)
- Tested by unit suites (`api/`, `adapters/`, `kinds_of_year/`), schema round-trip checks, and `validation/test_chain_examples.py` (`CH01`–`CH07` placeholder chain wiring).
- No deployed live NASA POWER call latency/timeout benchmark recorded yet (`api/README.md` `OPEN`).

### Declared Non-Claims & Limits
- **`outcome == "complete"` is unreachable on `49504ac`:** Because `EP4`, `EP5`, and `EP6` lack signed parameters and `D120`/`D121`/`D193` site soil properties, `soil_carbon_trend` rows are missing, capping `POST /api/rotations/run` at `partial` or `no_result`.
- **Two rotations only in `/api/decisions/run` (`api/README.md`):** Multi-rotation (`>2`) decision documents and stored run IDs (`#251`) are not implemented.
- **No uncertainty ranges in `MeansByKind` (`kinds_of_year/` `OPEN`):** Only arithmetic means are computed; ONI vs. NWS Relative ONI (`RONI`, NWS PIS 26-05) stays `OPEN` (`D240 (4)`).
- **2-month NWS revision window (`kinds_of_year/README.md`):** Recent CPC ONI values remain provisional for up to two months.

---

## Card 8 — Decision Layer (`decision/`)

- **Status:** **`DECIDED` scientific rules / `PROPOSED` Pydantic/service wiring** (`decision/functions.py` docstring; [contracts/decision_output/README.md](../contracts/decision_output/README.md)). Lane: `L2b`.
- **Primary Modules:** `decision/functions.py`, `decision/output.py`.

### Purpose
Evaluates one `ResultsTable` (rotations × scenarios × indicators) under bounded uncertainty and non-compensatory preference rules without inventing thresholds, weights, or tolerances, and assembles `DecisionOutput` for `POST /api/decisions/run`.

### Contract Inputs & Outputs
- **Core Pure Functions (`decision/functions.py`):**
  - `limit_counts(table, limits) -> dict[...]` (`D1`, `D94`, `D95`, `D96`)
  - `paired_difference`, `paired_differences(table) -> list[PairedDifference]` (`D2`, `D92`: `second - first`; range `[low_2 - high_1, high_2 - low_1]`)
  - `never_preferred_less`, `dominance(table)` (`D174`: `"by point value"`, `D99`)
  - `indicator_ranking(table, indicator)` (`D4` sensitivity)
  - `pair_state(table, first, second, ...)` (`D85`–`D99`, `D151`–`D156`, `D165`–`D176`)
  - `pair_counts(table, ...)` (`D87`, `D99`, `D169`: keyed by `(pair, scenario, indicator, carbon_model, computation)`)
  - `tipping_point(...)`, `measurement_priority(...)`, `recompute_with_measurement(...)`, `measurement_consistency(...)` (`D3`, `D4`, `D10`, `D12`)
- **Service Assembly (`decision/output.py`, `PROPOSED`):**
  ```python
  assemble_decision_output(table: ResultsTable, *, example_data: bool) -> DecisionOutput
  ```
- **Missingness & Types:** No missing value is coerced to `0` (`C3.1`). `NOT_DECLARED` is propagated whenever `DeclaredLimit` or `equal_tolerance` is absent (`D60`, `D87`).

### Scientific Basis & Decisions (`#77`)
- **Six State Labels (`D85`, `D88`, `D97`, `D151`):**
  - Absent state (`state=None`, label `"Not evaluated"` per `D151`) when no eligible paired cell has a value.
  - Five active states: `"Identical"`, `"Not separated: uncertainty missing"`, `"Not separated: within uncertainty"`, `"Not robust across scenarios"`, `"Robust preference"`.
- **Non-Deterioration & Blocking Rules (`D74`, `D93`, `D98`, `D165`):**
  - Cell classification (`D93`, `D167`): `"strict improvement"` (entire range on better side of `0`), `"deterioration"` (entire range on worse side), `"not separated"` (range touches or crosses `0`).
  - Blocking (`D98`, `D165`): A cell **does not block** robust preference if its entire range lies on the non-worse side of `0` (including touching `0` from the better side); crossing `0` or touching `0` from the worse side **blocks**.
- **Scenario & Carbon-Trend Rules (`D166`, `D169`, `D173`, `D175`):**
  - `pair_state` evaluates each scenario independently (`D166`, `D175`, preserving phase-nested uncertainty structure `D117`).
  - Only `end_minus_start` carbon trend enters `pair_state` (`D173`); `amg` and `rothc` counts are never pooled (`D169`).
- **Scenario Summaries (`D96`):** Only `minimum`, `maximum`, and `scenario_of_the_minimum` of years within limits—no mean, share, or percentage across scenarios.

### Parameter Status (`49504ac`)
- Holds **0** catalogue parameters (`0` is the only numeric rule boundary `D74`/`D93`/`D98`).
- In `POST /api/decisions/run` (`assemble_decision_output`), `limits`, `equal_tolerances`, and `UncertainInput` mappings are **all absent (`NOT_DECLARED`)** on `49504ac` because the route request carries no user limits, tolerances, or uncertainty sweep declarations (`decision/output.py` docstring).

### Validation Status (`49504ac`)
- **Implemented & Passing in [run-20261115T170110Z-df43899.json](../validation/runs/run-20261115T170110Z-df43899.json):** All 10 decision protocol codes `[D0]` (trivial point-mean comparator divergence vs. `decision/`), `[D1]` (limit counts), `[D2]` (paired differences & interval bounds), `[D3]` (tipping-point bracketing), `[D4]` (measurement priority), `[D5]` (non-separation under uncertainty), `[D6]` (missingness preservation), `[D7]` (state naming exactness), `[D10]` (recompute consistency), `[D12]` (measurement consistency). Note `[D0]`–`[D12]` fixtures use person-approved synthetic/table cases (`#223`), not field outcomes.

### Declared Non-Claims & Limits
- **`DecisionOutput.state` (overall document state) is `None`:** No rule exists yet aggregating multiple pair states into a single document-level verdict (`contracts/decision_output/README.md` `OPEN 5`).
- **`admissibility` vs. user `DeclaredLimit` (`D89`):** Admissibility against a verified soil-loss tolerance `T` has no field in `DecisionOutput` (`OPEN 3`).
- **`measure_first` is empty in `/api/decisions/run`:** Requires user/case `UncertainInput` parameter mappings not passed by `POST /api/decisions/run`.
- **No numerical resolution on `49504ac` routes:** With `EP1` emitting equal fallback `soil_loss` across rotations, missing `soil_loss` ranges (`range_missing`), and `EP3`–`EP6` returning missing/unvalidated outputs on demo inputs, pairs via `/api/decisions/run` cannot yield `"Robust preference"` on real demo runs.

---

## Card 9 — Plant & Economics (`economics/`, `api/plant.py`, `api/rain_stress.py`)

- **Status:** **`PROPOSED`** ([economics/README.md](../economics/README.md); [contracts/plant_answer/README.md](../contracts/plant_answer/README.md); `api/plant.py`; `api/rain_stress.py`). Lane: `L2`.
- **Primary Modules:** `economics/margin.py`, `economics/limit.py`, `economics/decide.py`, `economics/tipping.py`, `economics/plant.py`, `api/plant.py`, `api/rain_stress.py`.

### Purpose
Answers *"What should I plant?"* across 3–5 rotations for one field (`POST /api/plant/run`): computes deterministic simple rotation margins (`USD ha-1 yr-1`) by ENSO kind of year (`economic_facts`), checks `EP1` soil-loss means against a user-declared soil-loss limit (`on_average` and `every_kind`), selects the highest-margin compliant rotation (and limit cost against the best non-compliant option), computes linear soybean tipping prices within a declared price range, and optionally applies a rain-stress multiplier to `EP1` erosivity `R`.

### Contract Inputs & Outputs
- **Core Pure Functions (`economics/`, all `PROPOSED`):**
  1. `compute_rotation_margin(years: Sequence[Sequence[str]], facts: EconomicFacts, year_counts: Mapping[str, int | None] | None) -> RotationMargin`
  2. `assess_limit(limit: Value, average: SoilLossLevel, by_kind: Mapping[str, SoilLossLevel], *, kinds_in_record: Collection[str] | None = None) -> LimitAssessment`
  3. `choose_rotation(options: Sequence[RotationOption], strictness: Strictness) -> Decision` (`Strictness`: `"on_average" | "every_kind"`, `Answer`: `"chosen" | "none_meets" | "not_resolved"`)
  4. `find_tipping_price(options, facts, year_counts, soybean_crop_ids, price_range: PriceRange, strictness, margin_of="average") -> TippingPrice`
  5. `economics.plant.assemble_answer(...) -> PlantAnswer` (validated end-to-end by `check_answer_against_request`).
- **HTTP Route (`POST /api/plant/run`):** Consumes `PlantRequest` (`site`, `3`–`5` `RotationDefinition` items sharing `ag_year_start.month`, `economic_facts` in `USD`, `soil_loss_limit`, `questions`), returns `PlantAnswer`.
- **Mandatory Provenance, Labels & Limits (`D148`, `D243`, `D245`, `D249`, `D250`):**
  - Every present numeric field carries `DERIVED` (or `DECLARED` for echoed limits/prices) and `range` or `range_missing="NOT_AVAILABLE"` (`D249`).
  - `scope` (`D245` `R11`, exact): `"the most margin within the limit you declared; water and soil carbon are not part of this answer"`.
  - `declared_limits` (`D250`, exact): includes `"phase 1 only: only the first phase of each rotation enters this answer, a limit of this release (D250)"`.
  - Every non-example `soil_loss` mean carries the verbatim `D148` label (`D250`).

### Scientific Basis & Decisions (`#77`)
- **Equal-Area Rotation Margin (`D235`–`D251`):** Annual rotation margin averages all sown crop cycles in `years` divided by `len(years)` (`USD ha-1 yr-1`): grain `price * yield[kind] - cost`; cover `-cost`; declared-margin crop `declared_margin[kind]`. Weighted record average uses `year_counts` (never hardcoded climatology probabilities).
- **Non-Monetized Soil Erosion (`economics/limit.py`, `decide.py`):** Erosion is strictly a constraint (`meets` iff `soil_loss <= limit`), never priced or discounted inside margin. `choose_rotation` leaves the decision `not_resolved` on exact ties, missing candidate margins, or `not_resolved` options whose margin meets/exceeds the best candidate.
- **Exact Linear Tipping Search (`economics/tipping.py`):** Evaluates only `[low, high]` and linear crossings strictly inside `(low, high)` to find nearest `up` and `down` price/rotation switches (`%` distance from `today`), without tolerance or forecasts.
- **Heavier-Rain Stress Test (`api/rain_stress.py`, `R25`, `S-032`):**
  - **Switched OFF by default (`RAIN_STRESS_TEST != "on"`):** Declared `rain_stress_factor` is echoed with `applied=False`; `EP1` runs unscaled.
  - **Switched ON (`RAIN_STRESS_TEST=on`):** Multiplies only `rusle_r_factor` (`scope {}`) and its range bounds in a deep copy of `parameters`, labelled `"stress test"` (never `"forecast"`).

### Parameter Status (`49504ac`)
- **`economics/` holds 0 catalogue parameters and 0 price/yield/limit constants:** All economic facts (`USD` only), `soil_loss_limit`, `soybean_price_range`, and `rain_stress_factor` must be user-declared in `PlantRequest`.
- **`POST /api/plant/run` depends on `KINDS_OF_YEAR_RECORD_FILE` (`oni_v6`):** Because no ONI record is shipped on `main` (`49504ac`), unconfigured runs classify every year as missing `NOT_AVAILABLE`, making `margin.average`, kind-stratified `soil_loss`, and `every_kind` decision checks unresolved unless a person supplies a signed ONI file.

### Validation Status (`49504ac`)
- Verified via pure unit tests (`economics/test_margin.py`, `test_limit.py`, `test_decide.py`, `test_tipping.py`, `test_plant.py`), contract mirror/mutation tests (`contracts/plant_answer/test_examples.py`, `test_plant_answer_mutants.py` covering `D148`/`D245`/`D249`/`D250`/`D259`), and route tests (`api/test_plant.py`, `api/test_rain_stress.py`, `api/test_rain_stress_switch.py`). All economic test fixtures use **invented test data** (`README` notice); `PLACEHOLDER_plant_answer.json` is flagged `example_data: true`.

### Declared Non-Claims & Limits
- **Water & soil carbon are excluded (`D245`):** `PlantAnswer` ranks solely on margin and `EP1` soil loss.
- **Phase 1 only (`D250`):** Only `phase_1` (`phase 0`) of each rotation enters `PlantAnswer`, ignoring multi-phase shift variance.
- **Equal soil loss across rotations with deployed `EP1` (`D213`):** On `49504ac`, `EP1` uses declared `rusle_c_factor`, so all rotations on a site receive identical `soil_loss` in `POST /api/plant/run` (either all meet or none meets a given uniform limit).
- **No margin uncertainty ranges (`C2`, `economics/` `OPEN`):** `MarginResult`, `LimitCost`, and `TippingPoint` propagate no input uncertainty ranges (`range_missing: NOT_AVAILABLE`); `choose_rotation` therefore cannot apply the uncertainty non-separation band of `decision/` (`OPEN 1` of `decide.py`).
- **Unimplemented economics features:** `USD` currency only; empty fallow years in `years` refused (`ValueError`); declared-margin crops cannot share a year with another crop; no price/yield correlation across crops; `rain_stress_factor`'s own uncertainty is not propagated into `R` (`api/rain_stress.py`).

---

## Cross-Cutting Summary: Parameter & Validation Readiness (`main` @ `49504ac`)

| Component | Entry / Route | Status | Signed Records Used (`params/records/`) | Missing / Unsigned / External Dependencies | Validation Codes (`VALIDATION.md`) | Key Release Limit on `49504ac` |
|---|---|---|---|---|---|---|
| **`EP1` Erosion** | `engine.erosion.compute_soil_loss` | `PROPOSED` | `26` root (`LS`, `R`, `K`, `C`, `P`) + `6` shared (`residues/`) = `32` | `61` computed-`C` records in `params/withdrawn/computed_c/` | `[E0, E2, E3, E8, E9]` pass; `[E1a, E1b]` not evaluated (`D254`); `[E7]` observation only (no pass rule/test) | Declared-`C` fallback (`2.365` vs `0.392` measured t/ha/yr, no rotation contrast) |
| **`EP2` Calendar** | `engine.calendar.build_rotation_calendar` | `PROPOSED` | `0` | None | `CH01`–`CH07` chain + unit tests | No agronomic/overlap rules; multi-cycle perennials fail crossing phases (`D190`) |
| **`EP3` Water** | `engine.water.compute_water_deficit_exposure` (+ `D256`, `D222`) | `PROPOSED` | `100` (`45` `#262` + `43` `#417` + `12` `#446`) | `10` wheat/maize stage & cover records (`#433`) | `[H0, H1, H2, H7]` pass; `[H8]` `19` pass + `1` skipped (`test_h8_invariants_numeric_criteria`); `[H5]`/`[H10]` not run | `wheat`/`maize` missing; end-of-record fallow missing (`D187`); no `RH_min`/`Kcb` adj.; no `D189` spin-up convergence check run |
| **`EP4` Residues** | `engine.residues.build_residue_ledger` | `PROPOSED` | `6` (`rusle2_crop_yield`, `rusle2_residue_yield_ratio`) | `5` unsigned IDs (C/root fractions) | Paysandu context (uncoded) | Grain carbon series blocked until 5 IDs signed; `cover`/`pasture` `NOT_COMPUTABLE` |
| **`EP5` AMG** | `engine.amg.run_amg` | `PROPOSED` | `0` | `15` `amg_*` constants + `EP4` + site `SOC`/`clay`/`carb`/`pH`/`C:N` | `LEELP1` exploratory note (uncoded) | Zero computed values reachable; French arable calibration (`9.9`–`13.5 °C`), `AMG-M` unbuilt |
| **`EP6` RothC** | `engine.rothc.run_rothc` | `OPEN` (`ENTRYPOINTS.md`) / `PROPOSED` (code) | `0` | `24` `rothc_*` + `4` `rothc_input_*` constants + `EP4` + site `SOC`/`clay` | Reference case (`1e-4` tol) in unit tests | Zero computed values reachable; single missing climate day stalls rest of run; large `fitted_slope` error string |
| **Runner / Climate / Kinds** | `api/`, `adapters/`, `kinds_of_year/` | `PROPOSED` | Loads `params/records/` (`132`) | Signed `oni_v6` ONI file (`D240 (5)`), `POWER_SETTINGS_FILE`, soil tables (`D48`/`D49`) | Unit suites + `CH01`–`CH07` | `outcome="complete"` unreachable; `2`-month NWS ONI revision window; no deployed call benchmark |
| **Decision** | `decision/functions.py`, `output.py` | `DECIDED` (logic) / `PROPOSED` (assembly) | `0` | User `DeclaredLimit`, `equal_tolerances`, `UncertainInput` (`NOT_DECLARED` on route) | `[D0, D1, D2, D3, D4, D5, D6, D7, D10, D12]` | Document `state` always `None`; `measure_first` empty on route; no admissibility field (`D89`) |
| **Plant & Economics** | `economics/`, `api/plant.py`, `rain_stress.py` | `PROPOSED` | Scales `rusle_r_factor` if `RAIN_STRESS_TEST=on` | User `EconomicFacts` (`USD`), `soil_loss_limit`, price range, `oni_v6` file | Invented-data unit/route suites + `D249`/`D250` checks | Phase 1 only (`D250`); excludes water & carbon (`D245`); equal `EP1` loss across rotations; no margin ranges |
