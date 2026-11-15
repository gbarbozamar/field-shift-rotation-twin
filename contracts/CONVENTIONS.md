# Conventions sheet

Shared conventions that every contract, engine, adapter and screen in this repository follows. All other contracts depend on this sheet.

## How to read this sheet

- This sheet was written by a builder session (blueprint section 3.7). The items marked `PROPOSED` are proposals of the session. The items marked `DECIDED` hold decisions of a person, transcribed by the session. Nothing here is in force until a person approves the pull request. It is a science-class change, so it also needs a science reviewer.
- Every convention has an identifier (`C<section>.<item>`) and exactly one status, given on its `Status:` line:
  - `PROPOSED`: the session proposes it. A person accepts it or corrects it in the pull request.
  - `DECIDED`: a person decided it. The status line names who decided and when, and says whether acceptance by a science reviewer is pending.
  - `OPEN`: nobody has decided it. The item states the question a person has to answer and, where useful, the options.
- A decision can leave a part for a person to supply. That part is listed inside the item as a sub-point marked `OPEN`, with its question, or as `CITATION NEEDED`. The status of the item is the one on its `Status:` line.
- To review, answer per identifier: accept, correct, or (for `OPEN`) decide.
- The numbers in this sheet are only labels: item numbers, month numbers, exponents in unit strings and the date of a decision. The sheet contains no parameter value, threshold, uncertainty range or expected value. Those are supplied by people and live in the parameter catalogue, the test plan and the validation files.
- Field names given here say what travels with a value. The exact shape of each contract is fixed by its schema and its accepted example, which are separate units.
- Where a source would have to be cited, the text says `CITATION NEEDED`. A person supplies the citation.
- Three decisions of 15 November 2026 are restated as notes where they apply, each with the link to its comment on issue #77: D148 under C1.2, D147 under C1.5 and D141 under C5.5. A note changes no `Status:` line, no identifier, no unit string, no reason code and no label of this sheet.

## 1. Unit and direction of each indicator

### C1.1 Indicator list, identifiers and vocabulary

Status: PROPOSED

- The product reports three indicators per rotation, the ones named in the README: soil loss, exposure to water deficit, and the trend of soil carbon. Their identifiers are `soil_loss`, `water_deficit_exposure` and `soil_carbon_trend`.
- Identifiers are lower case with underscores. They are the same in every contract, file and screen. Display names shown to the user are interface text and are not fixed here.
- Every indicator value carries its unit as a string, written exactly as in this sheet. A consumer checks the unit it receives and never assumes it.
- In unit strings, `t` is the metric tonne, `ha` is the hectare, `yr` is one agricultural year (section 5), `month` is one calendar month, `t C` is tonnes of carbon, and `dimensionless` marks a value that has no unit.
- Every indicator has a direction, one of `lower_is_better` or `higher_is_better`. The direction says which way is preferable when two rotations are compared. It is not a threshold and it does not say when a difference matters; that is decided only by the test plan.
- Every indicator value follows sections 2, 3 and 4: it carries its uncertainty range, or it is missing with a reason, and it carries a provenance label.

### C1.2 Soil loss

Status: PROPOSED

| Aspect | Convention |
|---|---|
| Identifier | `soil_loss` |
| Quantity | Mass of soil lost per unit of field area per unit of time |
| Unit | `t ha-1 yr-1` |
| Time basis | One value per agricultural year. Where a contract asks for a monthly breakdown, one value per calendar month in `t ha-1 month-1`; the monthly values of an agricultural year add up to its annual value |
| Direction | `lower_is_better` |

The method that produces the value is not defined here. Its description and its source belong to the method documentation: CITATION NEEDED.

**What the demonstration shows (D148).** Decision of [issue #77, D148](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6888128333), 15 November 2026, which amends D145 and D146: "The computed `C` is withdrawn from the demonstration. Its per-rotation values are not shown, neither as absolute values nor as a comparison. Its code (#229) and its signed records (#237) stay in the repository as a documented, not validated capability." By the same decision the headline soil loss is the declared-`C` figure of D125, shown with the label that D148 words. The figure and the wording of that label are a value and interface text, so they are not repeated in this sheet: they are in D148, and the check behind the decision is the entry at the end of `docs/VALIDATION.md`. The identifier, the unit, the time basis and the direction of the table above do not change.

### C1.3 Exposure to water deficit: identifier, unit, time basis and direction

Status: PROPOSED

The direction and the absence of a unit below are not proposals of the session. The lead developer stated them on 14 November 2026 as a consequence of the decision recorded under C1.4: with a ratio of water transpired to water demanded, higher is better and the value has no unit. Acceptance by a science reviewer is pending. The quantity and the critical period restate the decision recorded under C1.4. The identifier and the unit string are proposed by the session. The time basis for a rotation is not decided, as its row says.

| Aspect | Convention |
|---|---|
| Identifier | `water_deficit_exposure` |
| Quantity | The ratio between water transpired and water demanded over the critical period of the crop (C1.4) |
| Unit | None: the value has no unit (lead developer, as stated above). Proposed by the session: its unit string is `dimensionless`, and it is never left empty |
| Time basis | The critical period of the crop (C1.4). `OPEN`: how the values of the crops of a rotation give one value per agricultural year or per rotation, and whether a monthly breakdown exists for this indicator, is not decided. Question for the science reviewers: **on which time basis is the ratio reported for a rotation?** |
| Direction | `higher_is_better` (lead developer, as stated above) |

No threshold appears in this sheet. Thresholds live only in the test plan (blueprint section 5).

### C1.4 Exposure to water deficit: scientific definition

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

- One measure decides: the ratio between water transpired and water demanded over the critical period of the crop.
- The other three measures (days below a threshold, days below a threshold in the critical period, accumulated shortfall as a depth of water) are computed from the same daily balance and reported as descriptive only: no threshold, no weight in the decision.
- A fourth descriptive measure (its unit and time basis are in D106, below): **water available at the sowing of the next crop**, descriptive only, with no threshold and no weight in the decision, like the other three (decided by the lead developer on 14 November 2026, [issue #77, D50](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346), at the request of a science reviewer; acceptance by a science reviewer pending). Comparing termination dates of a cover crop waits for the termination date to travel in the rotation definition (D4 of issue #77).

Decided on 14 November 2026 by the lead developer, in the comments of issue #77 on the water axis. They are science decisions taken by the lead developer as scientific lead; a science reviewer may still review them. Each is restated as the decision says it:

- **Window of the ratio (D105).** Decision of [issue #77, D105](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886058061): "The whole cycle of each crop, from sowing to harvest, with the declared dates of D72", "labelled in the same line 'whole cycle, not critical period'". "The critical period replaces it once growth stages travel in the calendar."
- **Days without a crop (D106).** Decision of [issue #77, D106](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886058061): "They do not enter the ratio: potential transpiration is zero on a day without a crop. They stay in the daily balance, which never resets (D44), so a fallow acts through the water left for the next crop. That effect is reported by the descriptive measure of D50, water available at the sowing of the next crop: in mm, one value per sowing, with no threshold and no weight in the decision."
- **Soil-moisture index (D107).** Decision of [issue #77, D107](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886058061): "Yes, as context and contrast, never as a deciding measure." Source for the event: "NASA POWER `GWETROOT` (root-zone soil wetness of MERRA-2, 0 to 1, a reanalysis, not an observation), through the climate API already used." Uses: "a regional context per agricultural year, and a qualitative contrast of the timing of wetting and drying in the balance of the actual rotation (H5). It is never converted to mm, never used as an initial state and never put into the alternative rotations." The depth that D107 left open is closed by D114 (below).
- **How `GWETROOT` is shown (D113).** Decision of [issue #77, D113](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886369099): "As the percentile of the day of the year within its own series, 2001 to 2024", read as "drier or wetter than usual". "The raw value from 0 to 1 is not shown. Still context and contrast only (D107)."
- **What `GWETROOT` is, and its depth (D114).** Decision of [issue #77, D114](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886369099): "Relative saturation of the root zone, 0 to 100 cm, from MERRA-2, a reanalysis on a ½° × ⅝° grid." "It is a fraction of porosity, not plant-available water: the screen never calls it 'available water'. The OPEN of D107 on the depth is closed."

The quantity `GWETROOT` as a climate series is in `contracts/CLIMATE_QUANTITIES.md` (`CQ7`).

Still to be supplied by a person:

- `OPEN`: whether the field `termination` that the rotation definition now carries (`contracts/rotation_definition/`) is what D50 waits for. Question for the lead developer: **can termination dates be compared now?**
- `OPEN`: the definition of the critical period per crop. D105 uses the whole cycle until growth stages travel in the calendar and does not define the critical period. Question for the science reviewers: **which period of each crop is its critical period?**
- `OPEN`: the state of the water balance that the ratio and the descriptive measures use. Question for the science reviewers: **which quantities of the daily water balance are "water transpired" and "water demanded", and which state of the balance do the descriptive measures use?**
- `OPEN`: the identifier of the water available at the sowing of the next crop. D106 gives its unit (mm) and its time basis (one value per sowing); no decision gives an identifier or a unit string for it.
- The source of the measure: CITATION NEEDED.

While the definition is incomplete (critical period, state of the balance), no engine reports `water_deficit_exposure` as anything but missing, with its reason. See the first clash below.

- **Phases and the one-input sweep (D117).** Decision of [issue #77, D117](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6886636603), 15 November 2026: "The phases are nested inside each value of the input. The state at a value of the input is the state over all the phases at that value, read as D74 reads a set of scenarios: a robust preference only if it is one in every phase, otherwise 'Not robust across scenarios' (D88). The tipping point of D3 is the bracket between adjacent values where that state changes. A phase is not an uncertain input: it repeats the comparison over how each crop falls on the historical years, the person knows the phase of the field, and it never enters the priority list of D4." It is a logic decision of the lead developer and answers the question that the comment recording D109 left open: how the phases of D109 combine with the one-input sweep of D3 as D103 reads it. See also Q5 in `contracts/ENTRYPOINTS.md`.

`OPEN`, clashes between texts. They are not from a decision of issue #77: they were found by the session that wrote this section, between this file and the decisions. Neither is resolved here; a person decides:

1. **The window of the ratio.** D105: "The whole cycle of each crop, from sowing to harvest, with the declared dates of D72". Section C1.3 of this file, rows "Quantity" and "Time basis": "over the critical period of the crop (C1.4)", "The critical period of the crop (C1.4)". C1.3 is outside this unit and is not changed. Question for the lead developer: **does C1.3 now read "whole cycle" until growth stages travel in the calendar?**
2. **When the indicator may be a number.** The paragraph above: "no engine reports `water_deficit_exposure` as anything but missing, with its reason" while the critical period and the state of the balance are not defined. D105 gives the window of the ratio for the event and D79 gives the summary ("sum of actual over sum of potential transpiration over the supported windows"), but no decision says that the critical period and the state of the balance are no longer needed for a number. Question for the lead developer: **may an engine report the ratio over the whole cycle, with the state of the balance still open?**

### C1.5 Trend of soil carbon: identifier, unit, time basis and direction

Status: PROPOSED

| Aspect | Convention |
|---|---|
| Identifier | `soil_carbon_trend` |
| Quantity | Change per year of the stock of soil carbon per unit of field area, obtained by one of the three computations of C1.6. The default, and the one used to compare rotations when the user has not chosen, is end minus start over the horizon (C1.6) |
| Unit | `t C ha-1 yr-1` |
| Time basis | One value per rotation, per carbon model and per computation, over the simulation horizon that both carbon models share. Stocks by month, year and rotation are not this indicator; they travel in the carbon balance contract |
| Sign | Signed. Positive means the stock increases; negative means it decreases |
| Direction | `higher_is_better` |

Each value names the carbon model and the computation that produced it. Values from different models are never averaged or merged into one value by an engine.

**Unit of the carbon inputs (D147).** The carbon inputs are not this indicator; the note is here because it fixes a unit string that travels between two contracts. Decision of [issue #77, D147](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887951649), 15 November 2026: the residue ledger engine (EP4 of `contracts/ENTRYPOINTS.md`) converts. "The annual carbon-input series that EP4 writes for `CarbonForcing.annual_carbon_inputs` are in **`t C ha-1`**", obtained from the ledger's `kg C ha-1` "by the SI definition of the prefixes". "That is a definition, not a value of the method, so it needs no catalogue record. The masses and the carbon of the ledger itself stay in `kg ha-1`. The runner and AMG do no arithmetic on them". The vocabulary of C1.1 lists `t` and does not list `kg`: whether C1.1 accepts the `kg` unit strings of the ledger stays `OPEN` in `engine/residues/README.md` (OPEN 3) and in EP4 of `contracts/ENTRYPOINTS.md`, and this note does not add them to C1.1.

### C1.6 Trend of soil carbon: what the trend is computed over

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

- All three computations are produced, and the user chooses which to see:
  - end minus start over the horizon;
  - slope of a fitted line;
  - mean change over whole rotation cycles.
- The default, and the one used to compare rotations when the user has not chosen, is end minus start over the horizon.

Still to be supplied by a person:

- `OPEN`: the soil depth and the horizon. They are values; they live in the parameter catalogue and in the carbon forcing contract, not in this sheet. Questions for the science reviewers: **to which soil depth does the stock refer, and over which horizon is the trend computed?** Both carbon models must refer to the same soil depth.
- The source of each computation: CITATION NEEDED.

## 2. How an uncertainty range travels with a value

### C2.1 The range travels inside the value

Status: PROPOSED

- A value and its uncertainty range travel together as one item. The range is never sent in a separate table, in a note or as text after the number.
- The range is a pair of bounds, `low` and `high`, in the same unit as the value. The bounds are absolute quantities, not a percentage of the value and not a distance from it.
- `low` is not greater than the value, and the value is not greater than `high`. An item that breaks this order is invalid.
- The range carries a label, `kind`, that names what the range represents. The list of allowed labels is still to be supplied (C2.3).
- The two bounds travel together or not at all.

### C2.2 A value without a range says so

Status: PROPOSED

- When no range is available, the range is absent and carries a reason, using the reason codes of C3.2. An absent range is never written as two bounds equal to the value.
- No engine, adapter or session invents, widens, narrows or makes symmetric a range. The numbers behind a range come from the science reviewers through the parameter catalogue and the test plan.
- A value that is missing (section 3) has no range.

### C2.3 What a range represents

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

More than one meaning is allowed. Every range carries its `kind` label so that they are never confused.

Still to be supplied by a person:

- `OPEN`: the closed list of `kind` labels. Question for the science reviewers: **which meanings of a range are allowed, and what is the label of each?**
- Any level or bound that a meaning needs is a value supplied by a person.
- The source of the method behind each meaning: CITATION NEEDED.

## 3. How a missing value and its reason travel

### C3.1 Missing is explicit and never a number

Status: PROPOSED

- A missing value travels as an empty value (null) together with a `missing` part that holds a `reason` code and an optional free-text `detail` in English.
- A missing value is never written as zero, as an empty string, as "not a number" or as any agreed stand-in number.
- An item holds either a number or a `missing` part. It never holds both and it never holds neither.
- A missing value keeps its identifier and its unit, so a consumer knows what is missing.

### C3.2 Reason codes

Status: PROPOSED

| Code | Meaning |
|---|---|
| `NOT_DECLARED` | The user was asked for the value and did not give it |
| `SOURCE_UNAVAILABLE` | The data source did not answer and there is no cached response |
| `NO_COVERAGE` | The data source has no data for this place or this period |
| `MISSING_INPUT` | The value is computed from an input that is itself missing; `detail` names that input |
| `NOT_COMPUTABLE` | The inputs are present but the method cannot produce a value for this case, for example an infeasible calendar or a case outside what the method covers |
| `CONTROL_FAILED` | A control on the module failed and the value is withheld |
| `NOT_AVAILABLE` | The module that would produce the value is not built or not enabled |
| `NOT_APPLICABLE` | The quantity has no meaning for this case |

The list is closed. A new code is a contract change and is added only at a checkpoint.

### C3.3 Missing values propagate

Status: PROPOSED

- A result that needs a missing input is itself missing, with reason `MISSING_INPUT`. Nothing is filled in, interpolated or replaced by a default, except by the gap filling decided under C3.4. Until a person supplies the method that C3.4 asks for, no gap is filled.
- The interface shows a missing value as missing, with its reason. It never shows a blank or a zero in its place.

### C3.4 Gaps inside a series that is aggregated

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

A monthly or yearly value may be computed from a daily series that has missing days, after filling the gaps with a method chosen by a person. The filled values are labelled as filled.

Still to be supplied by a person:

- `OPEN`: the gap-filling method. Question for the science reviewers: **with which method are the gaps of a daily series filled?**
- The source of the method: CITATION NEEDED.

## 4. Provenance label per value

### C4.1 The four labels

Status: PROPOSED

Every value that is not missing carries exactly one of four labels, written in upper case exactly as below.

| Label | Meaning |
|---|---|
| `DECLARED` | Stated by the user for this case, for example the rotation and its management; or declared by the project, for a parameter from the catalogue or an assumption (C4.5) |
| `OBSERVED` | Taken from a measurement or from an observational data source, unchanged except for a change of unit. This includes a data product that is itself modelled (C4.4) |
| `DERIVED` | Computed from other values by a fixed formula or by aggregation, without running a model through time |
| `SIMULATED` | Produced by running a model through time steps |

A missing value carries no provenance label; its reason code takes that place.

### C4.2 The label is not the source

Status: PROPOSED

- The label says what kind of value it is. It does not replace the source. Besides its label, every value carries a reference to its source or the explicit "assumption" mark required by ground rule 7 of the blueprint.
- The label is not a grade of quality. No label is treated as more reliable than another by an engine or by the decision layer.

### C4.3 Label of a value computed from other values

Status: PROPOSED

- A change of unit alone keeps the label of the input.
- A value aggregated or computed by a fixed formula from inputs that are `DECLARED`, `OBSERVED` or `DERIVED` is `DERIVED`.
- A value that depends on at least one `SIMULATED` input is `SIMULATED`.
- The label of the soil-loss indicator is fixed by C4.6.

### C4.4 Data products that are themselves modelled

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

A value taken from a data product that is itself modelled carries the label `OBSERVED`, with the product named as the source.

### C4.5 Parameters from the catalogue and assumptions

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

A parameter from the catalogue, and an assumption, carry the label `DECLARED`, read as declared by the project, with the citation as source.

### C4.6 Label of the soil-loss indicator

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

The soil-loss indicator carries the label `DERIVED`.

## 5. Numbering of months and agricultural years

### C5.1 Calendar months

Status: PROPOSED

- Calendar months are integers. January is month 1 and December is month 12.
- Month names and abbreviations do not travel in contracts; they are interface text.
- A month number always travels with its calendar year, in a field named `year`.

### C5.2 Dates

Status: PROPOSED

- A date is written `YYYY-MM-DD`: four-digit year, two-digit month, two-digit day, in the Gregorian calendar.
- Contracts carry dates, not day-of-year numbers.

### C5.3 Agricultural years

Status: PROPOSED

- An agricultural year is twelve consecutive calendar months beginning at the start month of the case (C5.4).
- An agricultural year is identified by the calendar year in which it begins, in a field named `ag_year`. A bare `year` always means the calendar year.
- Months inside an agricultural year keep their calendar numbers. There is no second numbering of months counted from the start of the agricultural year.

### C5.4 Start month of the agricultural year

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

- The start month is a value per case, to be determined by remote sensing by the science reviewers.
- Until that exists: a month declared by a person per case, marked provisional, and replaced when the determination from imagery is available.

Still to be supplied by a person:

- `OPEN`: the provisional month of each case. Question for the person who declares the case: **in which calendar month does the agricultural year of this case begin, provisionally?**
- `OPEN`: the remote-sensing method. Question for the science reviewers: **with which method is the start month determined from imagery?** The source of that method: CITATION NEEDED.

### C5.5 Incomplete agricultural years

Status: PROPOSED

An agricultural year that the data series does not cover from its first day to its last is not reported as a full year. Its yearly values are missing with reason `NO_COVERAGE`.

This item is about the extent of the series only: a year that begins before the first day of the series or ends after its last day. Days missing inside the series are covered by C3.3 and C3.4.

**A crop component that crosses the first day of the record (D133, D141).** Decision of [issue #77, D141](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887747713), 15 November 2026, which amends [D133](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6887062652): "Each phase is laid out as the first one already is. A component that starts before the first agricultural year of the record and ends inside it keeps its declared dates. The part before the record falls outside the record and is not described, exactly as `repeat_over_record` treats the first phase (D47). Inside the record, the component is present from the first day of the record and is computed normally. No date is moved and no value is guessed: the convention is the one the first phase already uses, now applied to every phase. Where an engine cannot compute a quantity because it would need the part before the record (for example, a state carried in from it), that quantity stays missing with its reason (C3.2), as for the first phase. Science class: a science reviewer may still review it." D141 names no reason code, and this note adds none to C3.2. The phases themselves, and how a phase reaches an engine (D109, D132), are under Q5 of `contracts/ENTRYPOINTS.md`.

## 6. Time zone of every daily series

### C6.1 Every daily series states its time zone

Status: PROPOSED

- Every daily series carries one explicit `time_zone` for the whole series. No series has an implied time zone.
- A day is the interval from midnight to the next midnight in the time zone of the series, and it is labelled with its date in that time zone (C5.2).
- Months and agricultural years group the days of a series by those dates.

### C6.2 Series from the NASA POWER adapter

Status: PROPOSED

A daily series delivered by the NASA POWER adapter is delivered in UTC (blueprint section 8; decision of the lead developer). Its `time_zone` is the string `UTC`.

This sheet does not say which series that adapter delivers. Whether IMERG precipitation comes through NASA POWER or directly is left to the science reviewers (`docs/GETTING_STARTED.md`).

How the service itself defines the day of its daily values, and how UTC is requested, is checked by a person against the public documentation of the service when the adapter is built: CITATION NEEDED.

### C6.3 Series produced by an engine

Status: PROPOSED

- A daily series produced by an engine has the time zone of the daily series that drives it.
- An engine does not move a daily series to another time zone.
- An engine never combines daily series that have different time zones. In that case its result is missing with reason `NOT_COMPUTABLE`.

### C6.4 Daily series from any other source

Status: OPEN

The time zone of a daily series from any source other than the NASA POWER adapter is not defined until a person chooses that source. Question for the science reviewers, asked again for each new source: **in which time zone are the days of this series defined, and, if it is not UTC, is the series converted, by whom and with which method?** Until it is answered, that series is not combined with any other daily series.

### C6.5 A day in UTC is not the local day at the field

Status: DECIDED (lead developer, 14 November 2026; acceptance by a science reviewer pending)

Daily processes at the field are driven by days defined in UTC, which do not line up with the local day. This is accepted and stated as a limit in the method documentation.

## Not covered by this sheet

- Any indicator other than the three in C1.1.
- Parameter values, thresholds, uncertainty ranges as numbers and expected test values. They are supplied by people in the parameter catalogue, the test plan and the validation files.
- Schemas and examples of contracts.
- The numbering of the years inside a rotation, which belongs to the rotation definition contract.
