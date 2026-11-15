# Validation protocol

**Skeleton, partly filled. The E and H entries are not defined yet, except [E3] and [H2]: each of the two has the decision D124 of the lead developer, a definition PROPOSED by an AI session, and a test that runs on a signed fixture. The D entries have their logic decided by the lead developer (14 November 2026); their OPEN items and their acceptance by a science reviewer are still pending.**

This file holds the acceptance tests that `docs/DEVELOPMENT_BLUEPRINT.md` refers to by codes in square brackets. It has one entry per code named in section 8 of the blueprint. No entry has a numeric value, threshold, numeric tolerance, expected value of the science, source or citation yet, with these exceptions: [E3] and [H2] state the tolerance of D124 (and of D138 for two steps of [H2]) and name their source, and their expected values are in the signed fixtures of `validation/fixtures/`, not in this file; and the plot check at the end of this file restates the figures and the source that D148 records.

## Owner

The science reviewers own this file (blueprint sections 2 and 10). Under section 3.6, the values of an entry are transcribed from their source as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says, and one person checks them against the source. Section 3.5 of the blueprint states D34. Under section 10, the science reviewers check each transcribed value against its source, as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says (one person checks it, stated in section 3.5 of the blueprint), and a science reviewer accepts the entry.

## Status of this skeleton

This skeleton is a proposal under blueprint section 3.7. It was laid out by an AI builder session and takes effect only when a person approves the pull request. It is a science-class change, so that pull request also needs a science reviewer.

The session supplied the layout and copied the blueprint's wording. It supplied no definition, value, tolerance, data source or citation.

Later change (#138): an AI session proposed the definitions of the D entries as logic on hand-made results tables, and the lead developer approved that logic on 14 November 2026. That change wrote no value, threshold, tolerance, expected value of the science, data source or citation; those stay `OPEN` or `CITATION NEEDED` for the science reviewers.

Later change (`l0/validation-d74-d96`): an AI session wrote into entries D1, D2, D5 and D7 the lead developer's decisions D74 and D85 to D99 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77), each restated with a link to its comment. Where two of those decisions do not fit, or may not fit, together as written, the session chose neither: each such case is an OPEN item (K1 to K7, under entries D5 and D7) that quotes both texts for the lead developer. K3 was later resolved by D97. That change wrote no value, threshold, tolerance, expected value of the science, data source or citation.

Later change (`l0/validation-d151-d156`): an AI session wrote into entries D1, D5 and D7 the lead developer's decisions D151 to D156 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (15 November 2026), which resolve K1, K2 and K4 to K7, and into entries D3, D4 and D7 his decisions D103 and D117, which this file did not record yet. Each is restated with a link to its comment. That change wrote no value, threshold, tolerance, expected value of the science, data source or citation.

Later change (`l0/validation-d151-d156-fixes`, #273, and `l0/validation-k12-reading`): after the independent verifications of #263 and #273, an AI session pointed the readings that D151 to D154 change (D93, D88, D95 and D92) to those decisions, gave the dates of the lists and status lines that now hold decisions of 15 November 2026, and recorded that D152 answers K12. That last item is a reading of D152 by an AI session, to which the lead developer left it; it is stated in a [correction on issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889121826) and adds no rule. That change wrote no value, threshold, tolerance, expected value of the science, data source or citation.

Later change (`l0/validation-run-record`, issue #289): an AI session ran the test suite without `ci/` once, at commit `3ced36f`, on 15 November 2026, and recorded it: the run in `validation/runs/run-20261115T061340Z-3ced36f.json`, and in `validation/results/` one result for each test that is the check of a code of this file: the test the entry names ([E3], [H2]), the test that names the code in its skip reason ([H1], [H7], [H8]), and the tests under the heading of the code in `decision/test_decision.py` (D1 to D7, D10, D12). Of those 40 tests, 37 passed and 3 were skipped ([H1], [H7] and [H8], recorded as not evaluated with the reason the test prints); a code with no such test has no result. The notes of the run record hold what the record format has no place for: the summary of the whole suite; the 26 tests of the machinery of [E3] and [H2] (the skip rule, the reading of the fixture and the comparison), which passed and are not results, with the criterion; the structural cases that stand under [E8], [E9], [H7] and [H8], which ran and passed, and passing them does not make those entries pass; the skipped tests that stand under no code; and the plot check at the end of this file, whose status stays as its entry words it, per D148: "not passed" for the computed `C`, and "a known overestimate of the same order of magnitude" for the declared `C`. The tests under D1 to D7, D10 and D12 passed on the functions of `decision/` as they are at that commit; those functions do not yet follow D165, D166, D169 and D173 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889795335), so the record says what ran and does not say that the decided rule is built. That change also brought the status lines and the "Checked by" lines of [E3] and [H2] and the two sentences at the top of this file in line with that commit. It wrote no value, threshold, tolerance, expected value of the science, data source or citation.

## How an entry gets completed

- **Section 3.5.** A threshold is never delegated to a session. A value, a unit, a range, an expected result or a citation is transcribed under decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622), which section 3.5 of the blueprint states in full: a reference, a locator, the verbatim text and the date read travel with the transcription, and one person checks it against the source.
- **Section 3.6.** The content of an entry is a science-class change: the values are transcribed under decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622), one person checks them against the source, and a science reviewer accepts them.
- **Section 3.7.** For conventions, definitions, contract field lists and the design of test cases, a builder session may write a proposal. Every proposed item is marked `PROPOSED`, and anything the builder cannot responsibly propose is marked `OPEN`, with the question a person has to answer. A proposal takes effect only when a person approves the pull request. This never covers the list in section 3.5: where a parameter value, a threshold, a range, an expected test value or a citation is needed, the builder writes `OPEN` or `CITATION NEEDED` and stops there.
- **Section 10.** The science reviewers fix thresholds and uncertainty ranges before results are seen, and check each transcribed value against its source, as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says (one person checks it, stated in section 3.5 of the blueprint). Nobody approves their own values.

**A pull request that fills or changes an entry is labelled `science` and cannot merge without the approval of a science reviewer.**

## How to read an entry

Text in quotation marks is copied from section 8 of the blueprint without change, including the bracketed codes. A name of a method, a publication, a program or a data product inside a quotation is the blueprint's wording. It is not a source chosen by this file and it is not a citation.

| Field | Content | Question a person has to answer while it is open |
|---|---|---|
| What it checks | The blueprint's wording that carries the code | — |
| Lane, Block, Unit it gates | Where section 8 places the code | — |
| Class | Class of change under blueprint section 3.6; `PROPOSED` until a person confirms it | Is the proposed class right? |
| Definition | `OPEN` | What exactly is computed, compared or asserted, and on which inputs? |
| Expected value | `OPEN` | What result counts as correct? |
| Tolerance | `OPEN` | How far from the expected value may the result be and still pass? |
| Source | `CITATION NEEDED` | Which published or reference source gives the expected value? It is also recorded in `ATTRIBUTIONS.md` when first used. |
| Transcribed by | `OPEN` | Who transcribed the values from the source (D34)? |
| Checked by | `OPEN` | Which person checked the values against the source (D34)? |
| Status | `not defined` | — |

## Open questions about this file

- OPEN: the blueprint does not say what the first letter of a code stands for. Entries are grouped by that letter and the groups are not named.
- OPEN: several codes share one bracket in the blueprint. What each of those codes covers on its own is for the science reviewers to state; the entries say where this applies. Where the blueprint gives a code its own words inside a longer sentence, the entry quotes those words and gives the sentence as context.
- OPEN: which values the Status field can take after `not defined`, and who sets each.
- OPEN: whether an expected value and its citation are written in this file or kept in `validation/` with a pointer from here. The layout of `validation/` is a separate unit.
- Section 8 is the only source of the codes below. A code that section 8 does not name has no entry. If the protocol has more codes, the science reviewers add them. The one exception is the plot check at the end of this file, which has no code: [D148 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333) asks for it to be recorded here.
- OPEN, for the lead developer: **the tolerance of the plot check at the end of this file.** None was fixed before the run, and none is chosen here. For a run that follows, which ratio of the computed soil loss to the measured one counts as plausible? Options: (i) within a factor of 2 of the measured mean of 2017–2019; (ii) within the range of the measured plot-years, 71 to 1,478 kg/ha/yr; (iii) within a factor of 10.

## Codes in this file

- E: E0, E1a, E1b, E2, E3, E7, E8, E9
- H: H0, H1, H2, H5, H7, H8, H10
- D: D0, D1, D2, D3, D4, D5, D6, D7, D10, D12
- Plausibility check without a code in section 8: [EP1: plausibility against the La Estanzuela runoff plots (2017–2019)](#ep1-plausibility-against-the-la-estanzuela-runoff-plots-20172019)

## E codes

### E0

- What it checks (blueprint wording): "trivial comparators [E0, H0, D0]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the trivial comparator of the soil loss, and the statement of whether it gives the same order of the rotations as the full soil loss. PROPOSED by a research AI session; DECIDED under D161 by [D211](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6891173855), 15 November 2026
- Lane: L0 Core
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "trivial comparators [E0, H0, D0]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by a research AI session; logic DECIDED under D161 by [D211](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6891173855)): Input: the daily flags of a living crop of each rotation and scenario (built in the test from a hand-made rotation calendar over a hand-made record), twelve hand-made monthly erosivity values, and a hand-made `ResultsTable` of `soil_loss`; all labelled example data. For each rotation, scenario (each phase is a scenario, D109, D166) and agricultural year, the trivial comparator computes the erosivity-weighted share of the year without a living crop: the sum over the months of the climatological fraction of the month (M1.2, D69, D84; `climatological_monthly_fractions` of `engine/erosion/r_factor/`, called) times the share of the days of that month on which no living crop is on the field. Lower is better. It orders the rotations by the mean of that share over agricultural years. Why `C` alone: R, K and LS do not change with the rotation and P is one (M1.1, M1.6), so the order of the soil loss is the order of `C`. The share is the weighting of AH537 with a soil-loss ratio of one on a day with no crop (the continuous-fallow reference of factor C) and zero on a day with a crop; that ratio is a modelling choice, not stated by a source. The test checks that (a) on the hand-made inputs the comparator returns the order counted by hand, and (b) the report states, per scenario, whether that order equals the order of the full `soil_loss` values by their mean over agricultural years, read in the direction of the row (C1.1), ignoring ranges (the reading of D0, `trivial_orders` of `validation/trivial_comparator.py`). Ties, missing years and a single rotation give no order, with the reason, as in D0; nothing is filled and nothing is read as zero. The report also states how many rotations each side ordered. Pass: (a) and (b) hold.
- What it does not do: it is not a soil loss and is never shown as one; it reads none of the records of the computed `C` withdrawn by D148 and D158; it validates neither method.
- Known limit: with the single declared `C` of D125 the full method gives the same value to every rotation (D158), so until a `C` by rotation exists the report can only state that the full method gives no order. With two rotations an order has two outcomes, so the same order happens by chance half of the time (D211).
- OPEN, for the lead developer (listed with their options in `validation/trivial_comparator_erosion.py`): which days carry a living crop is an input of the comparator, because no public function of `engine/` gives the days EP3 counts for the window of D157 (D105, D106, D136); which agricultural years are read when the flags cover a year only in part; a scenario held on one side only.
- Test: `validation/test_trivial_comparator_erosion.py`, on example data written by hand: the order counted by hand; the weighting by erosivity changing the order against an even spread; a part of a month counted by its days; an equal and a different outcome; the tie of the full method (every rotation the same `soil_loss`); a day without a flag, a missing flag and a missing monthly erosivity, each a missing year; a tie of two mean shares; a single rotation; each scenario read on its own.
- Expected value: the outcome stated as logic in the definition. Any order that a test compares is read off the hand-made inputs by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: orders and counts are compared exactly.
- Source: Wischmeier and Smith (1978), USDA Agriculture Handbook 537, p. 17 (factor C relative to clean-tilled, continuous fallow) and pp. 20-21 (soil-loss ratios combined with the erosion-index distribution), as read by AI sessions
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED under D161 (D211); acceptance by a science reviewer pending

### E1a

- What it checks (blueprint wording): "A person, not a session, runs the same rotations in the official national erosion program for the comparison [E1a]."
- Lane: OPEN. The blueprint states this code in a sentence below the table of the block, not in the row of a lane
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: OPEN. The blueprint gives no builder unit for this code; it says a person, not a session, runs it
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E1b

- What it checks (blueprint wording): "plausibility against published plot ratios [E1b]"
- Lane: L0 Core
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "plausibility against published plot ratios [E1b]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E2

- What it checks (blueprint wording): "order between systems [E2]"
- Lane: L0 Core
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "order between systems [E2]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E3

- What it checks (blueprint wording): "slope length and steepness equations [E3]"
- Lane: L0 Core
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "slope length and steepness equations [E3]"
- Class (blueprint section 3.6): Science — PROPOSED
- Decision: [D124 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886937443), fixed before any run (section 10): AH703 Table 4-2, its 91 cells worked in feet with the unit length in feet that D124 names, plus or minus 0.005; and the 19 Moderate values of m of Table 4-5, plus or minus 0.005. The published numbers are not written in this file.
- Definition (PROPOSED by an AI session, unit l0/validation-h2-e3-ready, issue #225): for each of the 91 cells of Table 4-2, `LS = S * L` computed by `engine/erosion/ls.py` (slope in percent, slope length and unit length in feet) with the coefficients of the parameter catalogue (`params/records/`); for each of the 19 cells of Table 4-5, `m` read back from `L` (`m = log10(L)` at a length ten times the unit length). Each is compared with its expected value.
- Expected value: the cells of the two tables as D124 names them, in the signed fixture `validation/fixtures/e3_ah703_tables.json` (path PROPOSED; format in `validation/fixtures/README.md`). On `main` since #238, with its `checked_by` filled; the test read it in the recorded run (result `3ced36f-E3-test_e3_slope_length_and_steepness_against_published_values-001` in `validation/results/`).
- Tolerance: plus or minus 0.005 on `LS` and on `m` (D124). The test fails if the fixture states another.
- Source: named by D124 (AH703 Tables 4-2 and 4-5); the full reference and locators travel in the fixture (`source`, `locator`) and are checked by the person who signs.
- Transcribed by: the scientific-integration AI session (D34), in the fixture's `transcribed_by`.
- Checked by: the `checked_by` field of the signed fixture `validation/fixtures/e3_ah703_tables.json` and of the unit-length record it carries, both filled on `main` since #238 (D34, D66). The signature is in the fixture and is not repeated in this file.
- Test: `engine/erosion/test_ls.py::test_e3_slope_length_and_steepness_against_published_values`. **Skip rule:** it skips, naming the file and each missing signature, while the fixture is absent, its `checked_by` is empty, or its unit-length record is absent or unsigned. Once signed, a malformed fixture or a value outside its tolerance fails.
- Status: written; the signed fixture is on `main` (#238). In the run recorded at commit `3ced36f` (`validation/runs/run-20261115T061340Z-3ced36f.json`) the test ran and passed: result `3ced36f-E3-test_e3_slope_length_and_steepness_against_published_values-001` in `validation/results/`.

### E7

- What it checks (blueprint wording): "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L0 Core
- Block: "Block 3 — the full decision on real data, until CP3"
- Unit it gates: "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E8

- What it checks (blueprint wording): "unit guard [E8]"
- Context (blueprint wording): "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Lane: L0 Core
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E9

- What it checks (blueprint wording): "invariants [E9]"
- Context (blueprint wording): "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Lane: L0 Core
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

## H codes

### H0

- What it checks (blueprint wording): "trivial comparators [E0, H0, D0]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the trivial comparator of the water-deficit exposure, and the statement of whether it gives the same order as the full `water_deficit_exposure`. PROPOSED by a research AI session; DECIDED under D161 (D212 of issue #77, 15 November 2026)
- Lane: L0 Core
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "trivial comparators [E0, H0, D0]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by a research AI session; logic DECIDED under D161, D212 of issue #77, 15 November 2026): Input: hand-made daily series of precipitation and of demanded transpiration (the basal crop coefficient times the reference evapotranspiration, the denominator of D157), the days of living crop of a hand-made rotation calendar (D105, D106, D136), given as a demanded transpiration that is `NOT_APPLICABLE` on every other day, as the daily balance of EP3 gives it, and a hand-made `ResultsTable` of `water_deficit_exposure`; all labelled example data. For each rotation, scenario, phase and agricultural year, the trivial comparator computes the sum of precipitation over the sum of demanded transpiration, both over the same days with a living crop that D157 uses: a day counts when its demanded transpiration is a number, and a day with no crop or of the tail after maturity (demanded transpiration `NOT_APPLICABLE`) is left out, as EP3 does. It is not bounded at one. Higher is better. A year with no day with a living crop is `NOT_APPLICABLE` and a year whose demanded sum is not above zero is `NOT_COMPUTABLE`, as EP3 gives the full indicator; a missing precipitation or demand on a counted day makes the year missing with its reason, and nothing is filled or read as zero. It orders the rotations by the mean of that ratio over agricultural years. It keeps the window and the denominator of D157 and removes the daily soil water balance (storage carried between crops, runoff, soil evaporation and the stress coefficient): a different order says that the balance changes the order. Using precipitation as the supply is a modelling choice, not stated by a source. The test checks that (a) on the hand-made inputs the comparator returns the order counted by hand, and (b) the report states, per scenario and phase, whether that order equals the order of the full `water_deficit_exposure` values by their mean over agricultural years, read in the direction of the row (C1.1), ignoring ranges (the reading of D0, taken from `validation/trivial_comparator.py`). Ties, missing years, `NOT_APPLICABLE` years and a single rotation give no order, with the reason, as in D0. The report also states how many rotations were ordered. Pass: (a) and (b) hold. What it does not do: it is not a water-deficit exposure and is never shown as one; it carries the label "whole cycle, not critical period" (D157, D162) wherever it is reported; it validates neither method. Known limit: D212 was taken before any water value existed; the comparator reports nothing on real data until EP3 gives numbers with the signed water records and a run on real climate. With two rotations the same order happens by chance half of the time: a different order is informative, the same order is weak evidence (D212). OPEN for the lead developer, in `validation/trivial_comparator_water.py`: how a phase reaches the inputs (a `ResultsTableRow` has no field for it; a phase is read as its own `scenario_id`); a year the comparator computes and EP3 does not; two sides that order different sets of rotations.
- Expected value: the outcome stated as logic in the definition. Any ratio, mean or order that a test compares is read off the hand-made inputs by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: states and ranks are compared exactly; the means are compared as the stored values, as in D0.
- Source: D157 for the window and the denominator (decision of issue #77), as read by AI sessions
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED under D161 (D212); acceptance by a science reviewer pending

### H1

- What it checks (blueprint wording): "public reference case [H1]"
- Context (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Lane: L1 Engines
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H2

- What it checks (blueprint wording): "reference evapotranspiration against a worked FAO-56 example [H2]"
- Lane: L1 Engines
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "reference evapotranspiration against a worked FAO-56 example [H2], in `engine/water/et0/`"
- Class (blueprint section 3.6): Science — PROPOSED
- Decision: [D124 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886937443), fixed before any run (section 10): the expected reference evapotranspiration is the one of the Eq. 6 line of Example 18; the tolerance is half a unit of the last printed digit of each step, with the soil heat flux G compared exactly. The published numbers are not written in this file.
- Definition (PROPOSED by an AI session; the test already written, issue #225): `reference_evapotranspiration_day` of `engine/water/et0/` is run on the example's own rows for the actual vapour pressure (Eq. 17), the solar radiation (Eq. 35) and the wind speed at 2 m (Eq. 47), with the constants and the two bounds of D82 given as parameter records; every step the example prints is compared with the engine's step. Whether this is an acceptable definition of [H2] is OPEN in `engine/water/et0/README.md`.
- Expected value: the printed rows of the example and the reference evapotranspiration of D124, in the signed fixture `validation/fixtures/h2_example18.json` (path PROPOSED; format in `validation/fixtures/README.md`). On `main` since #239, with its `checked_by` and that of each constant and bound record filled; the test read it in the recorded run (result `3ced36f-H2-test_h2_worked_example_18_of_fao_56-001` in `validation/results/`).
- Tolerance: per step, half a unit of the last digit the example prints; the soil heat flux exactly (D124). The test recomputes each tolerance from the printed number and fails if the fixture states another.
- Amendment: [D138 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887623727), decided **after the results of a structural run were seen**, gives one unit of the last printed digit, instead of half a unit, to `vapour_pressure_deficit` and `net_shortwave_radiation` only, because in both the example's printed result disagrees with its own printed operands. Every other step keeps D124.
- Source: named by D124 (FAO-56, Example 18); the full reference and locators travel in the fixture (`source`, `locator`) and are checked by the person who signs.
- Transcribed by: the scientific-integration AI session (D34), in the fixture's `transcribed_by`.
- Checked by: the `checked_by` field of the signed fixture `validation/fixtures/h2_example18.json` and of each of the 31 constant and 2 bound records it carries, all filled on `main` since #239 (D34, D66). The signature is in the fixture and is not repeated in this file.
- Test: `engine/water/et0/test_h2.py::test_h2_worked_example_18_of_fao_56`. **Skip rule:** it skips, naming the file and each missing signature, while the fixture is absent, its `checked_by` is empty, or any constant or bound record is absent or unsigned. Once signed, a malformed fixture, a step the engine does not compute, or a step outside its tolerance fails.
- Status: written; the signed fixture is on `main` (#239). In the run recorded at commit `3ced36f` (`validation/runs/run-20261115T061340Z-3ced36f.json`) the test ran and passed: result `3ced36f-H2-test_h2_worked_example_18_of_fao_56-001` in `validation/results/`.

### H5

- What it checks (blueprint wording): "regional soil-moisture contrast with SMAP [H5]"
- Lane: L1 Engines
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "regional soil-moisture contrast with SMAP [H5]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H7

- What it checks (blueprint wording): "mass closure [H7]"
- Context (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Lane: L1 Engines
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H8

- What it checks (blueprint wording): "invariants [H8]"
- Context (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Lane: L1 Engines
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H10

- What it checks (blueprint wording): "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L0 Core
- Block: "Block 3 — the full decision on real data, until CP3"
- Unit it gates: "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

## D codes

Section 3.6 of the blueprint lists "decision" among its examples of the class "Logic with a known answer". The class proposed in the D entries is the class of the entry's own content. Whether the gated unit is of another class is OPEN.

### D0

- What it checks (blueprint wording): "trivial comparators [E0, H0, D0]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the trivial comparator of the decision, and the statement of whether it gives the same order as the full decision. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L0 Core
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "trivial comparators [E0, H0, D0]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. The trivial comparator orders the rotations, per indicator, by the mean over agricultural years of the values, read in the direction of each row (C1.1), ignoring ranges. The test checks that (a) on the hand-made table the comparator returns the order counted by hand, and (b) the report states, per indicator, whether the comparator's order equals the order of the full decision. Pass: (a) and (b) hold. OPEN for the science reviewers: which trivial comparator is used (the mean over agricultural years is the proposal the lead developer approved; under blueprint section 10 the science reviewers read the trivial comparators).
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D1

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: counts by year against a declared limit. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data and a declared limit per indicator. For each rotation, scenario, indicator, carbon model and computation (D94 below), years evaluated is the number of agricultural-year rows that hold a value, and years within the limit is the number of those on the preferred side of the limit, judged by the row's `direction` (C1.1). A row with a missing value is never counted as within or outside the limit: it is reported as not evaluated, with its reason (C3). Pass: both counts equal the counts made by hand on the table, and every missing row appears as not evaluated with its reason. A value equal to the limit counts as within (D90 below).
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 and 15 November 2026):
  - [D85](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): when no paired difference of a pair holds a value (every input missing), the pair is "not evaluated", with no state, consistent with D6 (a missing value does not enter the state) and with the wording of this entry. `identical_rows` is true only when at least one difference holds a value and every difference is equal to zero; a pair with a missing difference is never "identical". The state of a pair is entry D7.
  - [D89](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (science; a science reviewer may still review it): the limit a user declares and the verified T of D74 live separately. Admissibility is decided only by D74: mean erosion at or below a verified T, with its source. The count of years within a limit (this entry) is descriptive, against the limit the user declares (`DECLARED`), and is shown apart. An official tolerance never edits the user's limit, and the user's limit never decides admissibility.
  - [D90](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (science; a science reviewer may still review it): a value equal to the limit counts as within (inclusive), consistent with the wording of D74 ("at or below" T and "at or above" zero). The counting function keeps its required argument `equal_to_limit_counts_as_within`, with no default; callers pass `True`.
  - [D94](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885583300) (logic): one count per rotation, scenario, indicator, carbon model and computation. Nothing is counted across scenarios or across carbon models.
  - [D95](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885583300) (logic): years are counted only over rows whose `time_basis` is `ag_year`. An indicator on another time basis (the soil carbon trend; the water ratio when it is per rotation) has no count of years: it is judged only by the admissibility of D74 (D89), once per scenario and carbon model. A limit a user declares for such an indicator is not used in the counts. Read with D154 below: this applies to the counts of this entry only, and such an indicator still enters the separation rule of entry D7.
  - [D96](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885583300) (logic): the only summary of the counts over many scenarios (D75) is the range, from minimum to maximum, of the years within the limit across the admitted scenarios, naming the scenario of the minimum. No mean, share or percentage of scenarios. How the screen shows it is for the interface developer.
  - [D154](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (science; a science reviewer may still review it; 15 November 2026): D95 applies to the counts of this entry only. An indicator whose time basis is not the agricultural year has no count of years, and the limit a user declares for it is not used. Its cells still enter the separation rule of entry D7 (D74, D93), cell by cell, like any other indicator. Admissibility (D74, D89) is judged apart and replaces neither.
- OPEN (not decided by D74 or D85 to D96): which scenarios are "admitted" (D96 and D74 both say "admitted scenarios"; D74 states admissibility for erosion, net stock change and the water ratio, not for scenarios), and who admits them. For the lead developer.
- RESOLVED by [D154](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (it was OPEN as two decisions that may not fit as written): an indicator on another time basis enters the separation rule of entry D7 cell by cell (D93); D95's "judged only by the admissibility" applies to the counts of this entry. Both texts are quoted under entry D7, item K5.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 and 15 November 2026), with D85, D89, D90, D94 to D96 and D154 of #77; the OPEN items of this entry are for the lead developer and the science reviewers; acceptance by a science reviewer pending

### D2

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: paired differences between two rotations. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. A difference is computed only between the two rows of a pair, that is rows of two rotations with the same cell (`scenario_id`, `indicator`, `time_basis`, `ag_year`, `carbon_model`, `computation`), never across cells. It is the second rotation of the pair minus the first. Rows whose units differ are refused, with no conversion (C1.1). If either value is missing, the difference is missing with reason `MISSING_INPUT`, naming the missing side (C3.3). Swapping the two rotations changes only the sign. Pass: each of these properties holds on the table, and each computed difference equals the one written by hand. The range of a difference is D92 below. OPEN for the science reviewers: the paired-difference method (issue #96, OPEN 2), apart from the range of a difference, which D92 decides.
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 November 2026):
  - [D87](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): for each pair, scenario and indicator, the output shows the count of paired cells where the second rotation is better, worse or equal, and of cells with a missing side, read in the direction of each row (C1.1). It is a count of this entry's differences: it never resolves a pair, and no statistic or p-value is attached. "Equal" uses the tolerance set by the designer of the case. Amended by D99 below: once differences carry ranges (D92), the cells are counted in two counts, shown apart and never added.
  - [D99](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885771292) (science; a science reviewer may still review it), amending D87: two counts, shown apart and never added. Where the difference has a range: strict improvement, deterioration and not separated, by D93 and D98 (entry D7). And by the sign of the point value, labelled as such. A cell without a range appears only in the second count.
  - [D92](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885546548) (science; a science reviewer may still review it): the range of a paired difference is computed by interval arithmetic, worst case. For a pair with values A in `[a_low, a_high]` and B in `[b_low, b_high]`, the range of the difference B − A is `[b_low − a_high, b_high − a_low]`. It assumes no distribution and no independence between the two values. Both ranges must carry the same `kind` (C2.3); if either range is missing or the kinds differ, the range of the difference is missing with its reason, and D86 / D88 give that pair the state "Not separated: uncertainty missing" (entry D7). Which state such a pair takes when the condition of another state also holds is D152 (entry D7).
- OPEN (not decided by D87 or D94): the counts of D87 are keyed by pair, scenario and indicator; D94 keys the counts of entry D1 also by carbon model and computation. Whether the counts of D87 are also split by carbon model and computation is not decided. For the lead developer.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: OPEN: the numerical tolerance for comparing a computed difference with the one written by hand, set by the person who designs the case.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026), with D87, D92 and D99 of #77; the OPEN items of this entry are for the lead developer and the science reviewers; acceptance by a science reviewer pending

### D3

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the tipping point of an uncertain input. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data whose scenarios vary one uncertain input. If the state of the decision is the same for every scenario value of that input, no tipping point is reported, with that reason. If the state changes, the tipping point is reported as the bracket between the two adjacent scenario values where it changes, with the name and unit of the input; no value inside the bracket is interpolated. Pass: on tables built by hand with and without a change of state, the function reports no tipping point, or the bracket chosen by the designer of the table. OPEN for the science reviewers: whether, and by which method, a value inside the bracket may be interpolated.
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 and 15 November 2026):
  - [D103](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885929841), the part about this entry: in the one-input sweep, each value of the uncertain input is one admitted scenario, and the state of the pair is read in each single scenario; the tipping point is the bracket where that state changes.
  - [D117](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886636603) (logic): the phases of a rotation (D109: each phase is a scenario) are nested inside each value of the input. The state at a value of the input is the state over all the phases at that value, read as D74 reads a set of scenarios: a robust preference only if it is one in every phase, otherwise "Not robust across scenarios" (D88). The tipping point is the bracket between adjacent values where that state changes. A phase is not an uncertain input, and it never enters the priority list of entry D4.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026), with D103 and D117 of #77; the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D4

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the measurement priority ("measure first"). PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data whose scenarios vary several uncertain inputs. The priority is given only when the state is not resolved. An input whose scenario values never change the state ranks below an input whose values do. Inputs that tie share a rank. Each item is qualitative: rank, what to measure and why, with no monetary value (#96). Pass: on tables built by hand, the ranks equal the ones the designer of the table wrote, and a resolved state gives no priority list. OPEN for the science reviewers: the measure of how much an input moves the decision, which orders inputs that all change the state.
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 and 15 November 2026):
  - [D103](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885929841), the part about this entry: the base state is the state of the pair over the whole admitted scenario set: "Not robust across scenarios" (D88) when any member is not a robust preference (D74); the priority list is built from there.
  - [D117](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886636603) (logic), the part about this entry: a phase of a rotation is not an uncertain input, and it never enters the priority list.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026), with D103 and D117 of #77; the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D5

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: direction of each indicator and dominance between rotations. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. The decision reads the `direction` of each row and never assumes it. A rotation that is no worse than another in every cell and better in at least one is never preferred less than that other rotation. Dominance between two rotations is judged only over the cells where both rotations hold a value: a cell where either side is missing counts neither for nor against either rotation, consistent with D6, under which a missing value does not enter the state (DECIDED by the lead developer, 14 November 2026; [D59](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6883698940) of #77). Reordering the rows or the rotations of the table does not change the result. Pass: the three properties hold on tables built by hand, including one where one indicator is `lower_is_better` and another `higher_is_better`.
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 and 15 November 2026):
  - [D91](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): when dominance is judged only over cells with a value on both sides (D59), the output carries the coverage: cells compared, out of the cells of the pair ("k of N"). No minimum coverage is set: D74 already gives no integral winner while an engine is unavailable.
  - [D93](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885578537) (science; a science reviewer may still review it), the part about a single cell: read in the direction of the indicator (C1.1), a paired cell with a difference range is a "strict improvement" only when the whole range of the difference lies on the better side of zero; a "deterioration" only when the whole range lies on the worse side; a range that touches or crosses zero is "not separated" for that cell. D93 states this for the separation rule of entry D7 (D74); its follow-up names this entry among those that record it. The rest of D93 is in entry D7. Amended by [D98](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885771292) (entry D7): a cell is non-deteriorating only when the whole range of its difference lies on the side of zero that is not worse, zero included; a cell whose range crosses zero is not separated and blocks a robust preference; strict improvement stays as in D93.
  - [D156](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (logic; 15 November 2026): "no worse" and "better" in this entry are read by the two values. Dominance compares the point values over the cells that hold a value on both sides (D59), and its output is labelled "by point value", as D99 labels its second count. It is descriptive and never names a preference: the state of a pair is entry D7. The coverage "k of N" of D91 counts the cells with a value on both sides, with or without a range.
- Two decisions that might not fit as written; it was OPEN for the lead developer and is resolved by D156:
  - K7 (D59 and D91 with D93). RESOLVED by [D156](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819): "no worse" and "better" stay comparisons of the two values, and the coverage counts the cells with a value on both sides, with or without a range. The item as it was written: this entry judges dominance by cells that are "no worse" and "better", over the cells with a value on both sides (D59), and reports their coverage "k of N" (D91). D93 classes a cell by the range of its difference. D93 does not say whether "no worse" and "better" here are read as its "no deterioration" and "strict improvement", or stay comparisons of the two values. If they are read by range, a cell with a value on both sides but no range of its difference (D92: "if either range is missing or the kinds differ, the range of the difference is missing with its reason") is counted among the cells compared by D59 and D91 and yet cannot be classed by D93. D59 on #77: "Dominance is judged only on the cells that have a value on both sides." D93 on #77: "Read in the direction of the indicator (C1.1): "strict improvement" only when the whole range of the difference lies on the better side of zero; "deterioration" only when the whole range lies on the worse side; a range that touches or crosses zero is "not separated" for that cell." D98 sharpens this item without deciding it: it defines non-deterioration by range for "paired non-deterioration" in D74, the separation rule of entry D7, and says nothing of this entry. If "no worse" here is read as D98's non-deterioration, a cell whose range crosses zero is not "no worse", and a cell without a range cannot be judged. D98 on #77: "Non-deterioration must be shown. A cell is non-deteriorating only when the whole range of its difference lies on the side of zero that is not worse, zero included (consistent with D90)."
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 and 15 November 2026), with D59, D91, the cell part of D93 (amended by D98) and D156 of #77; K7 is resolved by D156; acceptance by a science reviewer pending

### D6

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: missing values and modules not built in the decision. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data with missing values. When every value of an indicator is missing, the decision gives no ranking for that indicator, with the reasons carried through. A missing value, or an indicator that is `NOT_AVAILABLE` (C3.2, D12 of #77), is never counted as zero, as within a limit, or as best or worst, and does not enter the state. The descriptive-only water measures (C1.4, and D50 of #77) never change the state. Pass: on tables built by hand, each of these properties holds, and changing a descriptive-only measure leaves the state unchanged.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D7

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the state "not resolved". PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. When the data cannot separate two rotations, the state is "not resolved" and names the indicators that are not resolved. Two rotations with identical rows are never resolved. A paired difference whose range is missing is never resolved. Pass: on tables built by hand, each of these properties holds. The rule that says when the data separate two rotations is D74 below, with D93 for a cell that carries a difference range (blueprint section 5 places this rule in the test plan; the follow-ups on #77 write D74 into this entry). The state names are those of D88 below, with the name D97 adds. "Not resolved", in the first sentence of this definition, is the wording of the blueprint and of this entry before D88; it is not one of the names of D88 (with D97). D86 answers the question "Does "not resolved" say why?" for every state that is not a robust preference. How the state treats the two carbon models when they disagree is decided by D155 below (it was OPEN for the science reviewers): the pair is not a robust preference.
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 and 15 November 2026):
  - [D74](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885437753) (science), the separation rule of this entry, as the follow-ups of [D85 to D91](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) and the comment of [D92](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885546548) record: paired scenarios and years, explicit trade-offs; scenario coverage is not a probability of success. A robust preference needs paired non-deterioration on every indicator in every admitted scenario with at least one strict improvement. No integral winner while erosion, dual-coefficient water, AMG or RothC is unavailable or has a failed control. Admissibility: mean erosion at or below a verified T; net stock change at or above zero in each of AMG and RothC over a common horizon; water ratio without a universal cut-off; no regulatory certification.
  - [D86](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): a state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74). The names are those of D88. With D97 those names include "Not separated: within uncertainty", for a pair whose difference ranges exist and touch or cross zero.
  - [D88](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (science; a science reviewer may still review the wording): the names of the states of a pair are "Not evaluated" (D85) · "Identical" · "Not separated: uncertainty missing" · "Not robust across scenarios" · "Robust preference" (D74). Each name says why. Amended by D97 below, which adds the name "Not separated: within uncertainty". Clarified by D151 below: "Not evaluated" is the label shown for the absence of a state, not a state name.
  - [D93](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885578537) (science; a science reviewer may still review it): read in the direction of the indicator (C1.1), a paired cell with a difference range is a "strict improvement" only when the whole range of the difference lies on the better side of zero; a "deterioration" only when the whole range lies on the worse side; a range that touches or crosses zero is "not separated" for that cell. A robust preference (D74) needs no deteriorating cell and at least one strictly improving cell, in every indicator and every admitted scenario; a cell that is not separated gives no strict improvement, and a pair whose only cells are not separated is "Not separated: uncertainty missing" or not robust (D86, D88). Amended by D98 below (non-deterioration must be shown); D97 below names the pair whose ranges touch or cross zero. Amended by D153 below: one strictly improving cell is needed in each admitted scenario, in any indicator, not in each indicator.
  - [D97](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885771292) (science; a science reviewer may still review it), on how a pair is named when every difference has a range but the ranges touch or cross zero: two names. "Not separated: uncertainty missing" when the range of a difference is missing (D92); "Not separated: within uncertainty" when the range exists and touches or crosses zero (D93). This adds a name to D88, not a rule.
  - [D98](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885771292) (science; a science reviewer may still review it), amending D93: non-deterioration ("paired non-deterioration" in D74) must be shown. A cell is non-deteriorating only when the whole range of its difference lies on the side of zero that is not worse, zero included (consistent with D90). A cell whose range crosses zero is not separated and blocks a robust preference. Strict improvement stays as in D93 (the whole range on the better side, not touching zero). With the worst-case ranges of D92, a robust preference will be rare; that is accepted.
  - [D151](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (logic; 15 November 2026): "Not evaluated" is the absence of a state. A pair in which no paired difference holds a value has no state (D85): its state is empty, with its reason. "Not evaluated" in D88 is the label shown for that absence, not a sixth state name; D86 lists no reason for it because the missing part carries the reason. This clarifies D88 and changes no rule.
  - [D152](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (logic; 15 November 2026): when the conditions of more than one state hold, a pair takes one state, the first that applies, read in one scenario in this order: "Robust preference"; "Identical" (D85); "Not separated: uncertainty missing" (a computed difference without its range, D92); "Not separated: within uncertainty" (D97); otherwise "Not robust across scenarios". The reason of D86 follows the state. The conditions that did not give the state are still shown: the indicators not resolved and the two counts of D99. Over a set of scenarios or phases the state is the one D103 and D117 give.
  - [D153](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (science; a science reviewer may still review it; 15 November 2026), amending the wording of D93 ("in every indicator"): a robust preference needs one strictly improving cell in each admitted scenario, in any indicator. In every admitted scenario, every cell with a difference range shows non-deterioration (D98) and at least one cell is a strict improvement (D93). One is not required in each indicator. The part about scenarios is already in D103 and D117. An indicator with no evaluated cell does not enter the state (D6, D59); the rule of D74 on an unavailable engine still applies.
  - [D154](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (science; a science reviewer may still review it; 15 November 2026): an indicator whose time basis is not the agricultural year enters this separation rule cell by cell, like any other indicator. D95 applies to the counts of entry D1 only. Admissibility (D74, D89) is judged apart and replaces neither.
  - [D155](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819) (science; a science reviewer may still review it; 15 November 2026): the separation rule of D93 is applied per carbon model. The cells of AMG and of RothC are separate cells and are never read together: each must show non-deterioration (D98), and a strict improvement in one model does not stand for the other. When the two models disagree, the pair is not a robust preference.
  - [D103](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885929841) and [D117](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886636603), the part about the state: the state of a pair is read in each single scenario; over a set of admitted scenarios, or over the phases of a rotation, the pair is a robust preference only if it is one in every member, otherwise "Not robust across scenarios" (D88). The rest of D103 and D117 is in entries D3 and D4.
  - Also recorded elsewhere and used here: D85 ("not evaluated", with no state, and when `identical_rows` is true) in entry D1; D92 (the range of a difference, and the state of a pair whose difference range is missing) and D99 (the two counts of the cells of a pair) in entry D2; D156 (dominance read by the two values) in entry D5.
- Decisions that do not fit, or may not fit, together as written. Each item quotes both texts from #77, without its bold. They were OPEN for the lead developer and all are resolved: K3 by D97, and K1, K2 and K4 to K7 by D151 to D156 (15 November 2026):
  - K1 (D85 and D88). RESOLVED by [D151](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819): "Not evaluated" is the absence of a state, and the label shown for it. The item as it was written: D85 gives the pair no state; D88 lists "Not evaluated" among the names of the states, and D86 lists no reason for it. D85: "The pair is "not evaluated", with no state, consistent with D6 (a missing value does not enter the state) and with the wording of D1." D88: ""Not evaluated" (D85) · "Identical" · "Not separated: uncertainty missing" · "Not robust across scenarios" · "Robust preference" (D74)." Question: is "Not evaluated" a state, or the absence of a state?
  - K2 (D92 with D85, D86 and D88). RESOLVED by [D152](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819): one state, the first that applies in the order D152 gives; over a set of scenarios or phases, the state D103 and D117 give. The item as it was written: no decision says which state a pair takes when the conditions of two states hold. Example: every difference of a pair holds a value equal to zero and the ranges of those differences are missing. By D85 and D88 the pair is "Identical"; by D92 it is "Not separated: uncertainty missing". A second example: one cell has no difference range and another cell is a deterioration (D93). D85: "`identical_rows` is true only when at least one difference holds a value and every difference is equal to zero". D92: "if either range is missing or the kinds differ, the range of the difference is missing with its reason, and D86 / D88 give that pair the state "Not separated: uncertainty missing"". D86: "A state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74)." D97 widens this item: a pair can now also meet the condition of "Not separated: within uncertainty". Examples: every difference of a pair is zero and every range exists and crosses zero ("Identical" by D85 and D88, "Not separated: within uncertainty" by D97); one cell has no range and another has a range that crosses zero ("Not separated: uncertainty missing" by D92, "Not separated: within uncertainty" by D97). D97: ""Not separated: uncertainty missing" when the range of a difference is missing (D92). "Not separated: within uncertainty" when the range exists and touches or crosses zero (D93)." Question: which state, and which reason, comes first?
  - K3 (D93 with D86, D88 and D92). RESOLVED by [D97](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885771292): such a pair is "Not separated: within uncertainty"; "Not separated: uncertainty missing" stays for a missing range (D92). The item as it was written: D93 leaves two states open for a pair whose cells all carry a difference range that touches or crosses zero, and none of D86's reasons is written for that case (the uncertainty is not missing and there may be one scenario only). D93: "a pair whose only cells are not separated is "Not separated: uncertainty missing" or not robust (D86, D88)." D86: "A state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74)." D92 gives "Not separated: uncertainty missing" to a pair whose difference range is missing. Question: which state and reason does such a pair take?
  - K4 (D93 and D74). RESOLVED by [D153](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819), with D103 and D117 for the part about scenarios: one strictly improving cell in each admitted scenario, in any indicator. The item as it was written: D74 can be read as one strict improvement over the whole pair; D93 can be read as one strictly improving cell in each indicator and each admitted scenario. D74: "A robust preference needs paired non-deterioration on every indicator in every admitted scenario with at least one strict improvement (USER-R)." D93: "A robust preference (D74) needs no deteriorating cell and at least one strictly improving cell, in every indicator and every admitted scenario". Question: is one strictly improving cell needed in the whole pair, or in each indicator and each admitted scenario?
  - K5 (D93 and D95, with D74). RESOLVED by [D154](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819): such a cell enters the separation rule, and D95 applies to the counts of entry D1 only. The item as it was written: D93 puts every indicator into the separation rule cell by cell; D95 says an indicator whose `time_basis` is not `ag_year` is judged only by admissibility; and D74 sets no universal cut-off for the water ratio, so a water ratio per rotation would have no judgement under D95 alone. D93: "A robust preference (D74) needs no deteriorating cell and at least one strictly improving cell, in every indicator and every admitted scenario". D95: "An indicator on another time basis has no count of years: it is judged only by the admissibility of D74 (D89), once per scenario and carbon model." D74: "water ratio without a universal cut-off". Question: does a cell of the soil carbon trend, or of a water ratio per rotation, enter the separation rule of D93, or does D95's "judged only by the admissibility" apply only to the counts of entry D1?
  - K6 (D93 and D94, with D74). RESOLVED by [D155](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888774819): D93 is applied per carbon model. The item as it was written: D94 keeps the two carbon models apart and D74 asks admissibility in each of them; D93 names indicators and scenarios but not carbon models, so the cells of AMG and RothC of one indicator could be read together (one strictly improving cell in either model satisfying the indicator). D94: "One count per rotation, scenario, indicator, carbon model and computation. Nothing is counted across scenarios or across carbon models." D74: "net stock change at or above zero in each of AMG and RothC over a common horizon". D93: "at least one strictly improving cell, in every indicator and every admitted scenario". Question: is D93 applied per carbon model? This is the OPEN item of the definition on carbon models that disagree.
  - K7 is under entry D5 (dominance and D93), where D156 resolves it.
- OPEN (not decided by D74, D85 to D99, D103, D117 or D151 to D156): which scenarios are "admitted" (D74, D86, D93 and D96), as under entry D1.
- OPEN (named as not decided in the comment of D151 to D156 on #77): which of the three computations of the soil carbon trend (`end_minus_start`, `fitted_slope`, `mean_over_cycles` in `contracts/results/`) enter the separation rule. For the lead developer.
- Not in this file: the clashes K8 to K12, which `contracts/decision_output/README.md` lists. K12 is answered by D152, in the reading of an AI session to which the lead developer left it ([correction on #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6889121826)): read in one scenario, a pair with one cell whose range crosses zero and one cell with no range takes "Not separated: uncertainty missing", which comes before "Not separated: within uncertainty" in the order of D152, unless every difference is zero ("Identical" comes before both); the reason of D86 follows the state. That README records the same reading. D151 to D156 do not decide K8 to K11.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 and 15 November 2026), with D74, D86, D88, D93, D97, D98, D103, D117 and D151 to D155 of #77; K1 to K6 are resolved (K3 by D97, the others by D151 to D155); the OPEN items of this entry (which scenarios are admitted; which computations of the soil carbon trend enter the rule) are for the lead developer; acceptance by a science reviewer pending

### D10

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the measurement input. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data and a value entered by the user for an input of the priority list. The value enters with label `OBSERVED` (C4.1), its unit, and its range or `range_missing` (C2). A blank value, or a value in a unit other than the expected one, is refused and never taken as zero (C3.1). The decision is recomputed with that input fixed at the measured value; no other input changes. Pass: on tables built by hand, each of these properties holds.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D12

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: consistency of tipping point, priority and measurement input. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data with a tipping point (D3) and a measured value (D10). A measured value on one side of the tipping point gives the state of that side. If the state becomes resolved after the measurement, the priority list is empty (D4). Pass: on tables built by hand, a value on each side of the bracket gives the state of that side, and the priority list empties when the state is resolved.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

## Plausibility check without a code in section 8

This entry has no bracketed code: the blueprint's section 8 does not name it. [D148 of issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333) asks for the check and its result to be recorded in this file. It is a science-class entry (blueprint section 3.6): the numbers below are restated from D148 and from the source, and a science reviewer has not accepted it.

The two context blocks of this section (soil loss measured with ¹³⁷Cs, and the carbon inputs of EP4) were added by unit `l0/validation-local-context` (brief #319). They record local measurements a science reviewer needs when judging plausibility. They are not checks, tolerances or expected values, and no value of them enters `params/records/`.

### EP1: plausibility against the La Estanzuela runoff plots (2017–2019)

- What it checks: the annual soil loss that EP1 (`compute_soil_loss`, main route, `docs/METHODS.md` M1.2) gives at the demonstration site, against the soil loss measured on the six Wischmeier runoff plots of La Estanzuela. It is not a check of the code (H2 and E3 cover the equations) and it is not a calibration: no value was fitted, calibrated or changed.
- Lane: L0 Core (EP1); the check was run by an AI session, read-only.
- Class (blueprint section 3.6): Science — PROPOSED
- Source: Grahmann, K., Rubio, V., Perez-Bidegain, M., Quincke, J.A. (2022). *Soil Use Legacy as Driving Factor for Soil Erosion under Conservation Agriculture*. Frontiers in Environmental Science 10:822967, https://doi.org/10.3389/fenvs.2022.822967, CC BY 4.0 (the plots of D100):
  - the yearly average soil losses of the six plots are 233, 805 and 139 kg/ha for 2017, 2018 and 2019 (pp. 1 and 8); their mean is the 0.392 t ha-1 yr-1 of D148;
  - the measured yearly rates of single plots range from 71 to 1,478 kg/ha/yr (p. 12; Figure 4, p. 10);
  - the crop sequence and its dates are in Table 1 (p. 4) and on p. 3, which says that all six plots were managed uniformly since 2015.
- Soil: the plots are a Vertic Argiudoll with K = 0.023 (pp. 1, 3 and 7). That is not the soil of the demonstration, the Brunosol éutrico típico of [D112](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886174765) (class "T Brunosol" of D100). The runoff experiment stays separate from the demonstration (D71), and D112 already says that the soil-loss number does not reproduce the plots.
- Definition: EP1 is run on the climate record of the site and on the rotation the plots had in 2017–2019, once with the declared `C` of D125 (the 26 records of #203) and once with the computed `C` of D129 and D142 to D145 (the records of #237). Its annual values are compared with the measured ones. The inputs of each run (the calendar dates the paper does not print, the cover crops that have no records, the commit of EP1 and the catalogues) are in the write-up of the check, which is not in this repository.
- **Tolerance: none was fixed before the run.** The result is therefore reported as an observation. No pass rule was chosen after the result was seen, and none is chosen in this file. Choosing a tolerance for the runs that follow is listed under OPEN above.
- Observed result, as D148 records it:
  - **Declared `C` (D125):** 2.365 t ha-1 yr-1 against 0.392 measured, a ratio of 6.0 (2.9 to 17.0 by year, which is 2.365 divided by each of the three printed yearly averages). That is above all 18 measured plot-years. D148 calls it the same order of magnitude, and close to the paper's own RUSLE estimate.
  - **Computed `C` (D129, D142 to D145):** about 24.4 t ha-1 yr-1 on average, a ratio of about 62 (18 to 180 by year in D148; the write-up's own table gives 176 for the highest year).
  - **Order of the years:** the computed `C` reverses it. Measured: 2018 > 2017 > 2019. Computed: 2017 > 2019 > 2018 (n = 3).
  - **Soil:** using the plot's K instead of the demonstration's explains at most a factor of 1.3.
  - **Ranking of treatments:** it cannot be tested with this experiment, because all six plots had the same rotation since 2015.
- Status, per D148: **not passed** for the computed `C`; a known overestimate of the same order of magnitude for the declared `C`. Since no tolerance was fixed, "not passed" is the wording of D148 and rests on the observed ratios above, not on a pass rule written in this file. This is not a validation of the model.
- Consequence ([D148](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333), which amends D145 and D146): the computed `C` is withdrawn from the demonstration; its per-rotation values are not shown, as absolute values or as a comparison. Its code (#229) and its signed records (#237) stay in the repository as a documented capability that is not validated. The headline soil loss is the declared-`C` figure of D125 (2.365 t ha-1 yr-1 at La Estanzuela), shown with the label D148 words: "based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)". EP1 was not calibrated or tuned before the deadline.
- After the event, per D148: temperature and moisture modifiers of residue decay, consolidated no-till subfactors, cover crops, and this same check kept as a regression test.
- Transcribed by: the AI session that ran the check (D34). The numbers of the source are restated here from D148 and from the pages cited above.
- Checked by: OPEN. D148 records the lead developer's acceptance of the recommendation, not a check of the numbers against the pages of the paper.
- Status: result observed and recorded (15 November 2026); no test is written; acceptance by a science reviewer pending.

**Context: soil loss measured with ¹³⁷Cs in the rotation experiment of La Estanzuela.** Not a check, a tolerance or an expected value.

- Source: Quincke, A., Tassano, M., González, J.M., Grahmann, K., Pérez-Bidegain, M., Ciganda, V., Evrard, O., Barolín, E., Cabrera, M. (2024). "Erosión del suelo: nuevos métodos de estudio en el 'viejo' experimento de rotaciones de La Estanzuela". *Revista INIA* N.º 77 (June 2024), pp. 47-50, https://www.inia.uy/sites/default/files/publications/2024-12/Revista-INIA-77-Junio-2024.pdf. Read in a copy of that issue.
- The experiment:
  - the crop-pasture rotation experiment "José L. Castro" of INIA La Estanzuela, installed in 1963 (p. 48);
  - plots of 25 × 200 m laid along the slope, slope 2.5 to 3.0 %, on "un brunosol éutrico típico franco arcillo limoso con propiedades vérticas (Vertic Argiudoll según el USDA Soil Taxonomy)" (p. 48);
  - two plots were sampled: continuous cropping (system 2, plot #5) and a rotation of two years of crops and one year of red-clover pasture (system 7, plot #1) (p. 48).
- Method:
  - ¹³⁷Cs inventories in layers of 2.5 cm at five points along each plot, at 40, 80, 120, 160 and 200 m from the top (pp. 48-49), against the inventory of an uneroded reference site of the station, 367 Bq/m² (p. 49);
  - the inventories are converted into rates of erosion or accumulation with the mass-balance model II of Walling et al. (2011) (p. 49).
- Period:
  - the ¹³⁷Cs fallout peaked in South America "entre 1964 y 1972" (p. 48);
  - the project quantified soil loss and accumulation "como consecuencia del proceso erosivo en casi 60 años de manejos contrastantes" (p. 48).
  - The rates are therefore averages over about six decades of management, past tillage included. They are not rates of the present practice.
- What the article prints, in Mg/ha/año (t ha-1 yr-1), all on p. 49:
  - mean erosion of the continuous-cropping plot: 8.0, "excluyendo el punto de acumulación";
  - mean erosion of the red-clover rotation plot: 4.4;
  - accumulation at the last point (200 m, near the foot of the slope): 37.9 and 12.4 respectively;
  - the four erosion points of the continuous-cropping plot "oscilan entre 4,0 y 11,7 Mg/ha/año". For the rotation plot the text prints no range; Cuadro 1 prints 2.4 as the lowest and 5.7 as the highest of its four erosion points.
- What it is not:
  - It is another experiment, on other plots, than the Wischmeier runoff plots of the check above and than the demonstration point. [D71](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885437753) makes the La Estanzuela station the base of the demonstration and keeps the runoff plots of Grahmann et al. (2022) and the long-term carbon experiment LEELP1 as separate experiments: "a contrast from one is never merged with the other".
  - It integrates about six decades and the past tillage of the plots. It is not a measurement under the no-till rotations of D128.
  - It does not check the rotations of D128, nor the declared-`C` figure of D125 with the label of [D148](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333), nor what [D213](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6892169953) says about erosion and the two rotations. No ratio with any value of an engine is computed here.
- Transcribed by an AI session (D34), from the pages cited, on 15 November 2026. Checked by: OPEN.

### EP4: context for the annual carbon inputs

- What it is:
  - carbon inputs of soybean and corn measured at a Uruguayan site;
  - a plausibility reference for the values EP4 will give once its records are signed (D197).
- What it is not:
  - an input of EP4: EP4 computes the inputs from yields and residue/yield ratios (D129, [D196](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890256765)) and from the records of [D197](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6890256765);
  - a check, a tolerance or an expected value.
- Lane: L0 Core (EP4). Class (blueprint section 3.6): Science — PROPOSED.
- Source: Mazzilli, S., Piñeiro, G., Kemanian, A. (2012). "Priming effects on soil organic carbon decomposition induced by high C:N crop inputs". *Agrociencia (Uruguay)* 16(3):191-198, https://doi.org/10.31285/AGRO.16.669. Read in a copy of the article.
- Site:
  - 10 km south of Paysandú (31° 21' S, 58° 02' W), a Typic Argiudol with 280 g kg−1 of clay in the first 0.3 m (p. 192);
  - continuous wheat from 1940 to 1970, from 1970 to 1993 a six-year crop–pasture rotation of three years of a mixed pasture (white clover, birdsfoot trefoil and tall fescue) and three years of crops, not cropped from 1993 until the experiment of 2007 (pp. 192-193);
  - no-till corn and soybean sown on 6 December 2007 and 28 November 2008 (p. 193).
- What the article prints:
  - Table 1, "Crop Production (Mg of C ha-1)", p. 194:
    - soybean 6.5 ± 0.4 aboveground and 0.9 ± 0.1 belowground;
    - corn 8.8 ± 0.1 aboveground and 1.9 ± 0.1 belowground.
    - Aboveground: "Grain is not included". Belowground: "In the first 30 cm of soil".
    - Table 1 does not print the period its values cover.
  - Text, p. 194: "Carbon inputs per year from corn were on average 4.4 and 0.9 Mg ha-1 for aboveground and belowground, respectively". The same paragraph says these were "approximately 1.2 and 0.5 Mg.ha-1 higher than those for soybean". **The article prints no per-year value for soybean, and none is written here.**
  - Abstract, p. 191: corn and soybean C inputs of "10.7 and 7.0 Mg ha-1". Reading of the transcriber, not printed: the corn total is the sum of the two corn values of Table 1 (8.8 + 1.9), and the per-year corn values of the text are about half of them, so Table 1 and the abstract read as totals over the two seasons. The soybean values of Table 1 add up to 7.4, not the 7.0 of the abstract, and the article does not say why.
  - Carbon concentration, Table 1, p. 194, in g g-1 (written here because the 0.44 and 0.40 of D197 are compared with it): soybean 0.50 ± 0.1 aboveground and 0.39 ± 0.04 belowground; corn 0.44 ± 0.1 aboveground and 0.37 ± 0.04 belowground.
- Limits the article states:
  - "Crop biomass production in both years was high in relation to that expected for rainfed crops in this region" (p. 194);
  - roots were measured at flowering with soil cores (p. 193);
  - the humification estimates ignore the inputs from rhizodeposition (p. 194). The measured inputs therefore have no rhizodeposit term, while EP4 writes one (D197).
- Other limits:
  - Another site and soil than the demonstration point (Paysandú, not La Estanzuela).
  - Two seasons only.
  - No value of EP4 is compared with it here: EP4 gives none while its records are unsigned.
- Transcribed by an AI session (D34), from the pages cited, on 15 November 2026. Checked by: OPEN.
