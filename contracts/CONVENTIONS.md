# Conventions sheet

Shared conventions that every contract, engine, adapter and screen in this repository follows. All other contracts depend on this sheet.

## How to read this sheet

- This sheet is a **proposal written by a builder session** (blueprint section 3.7). Nothing here is in force until a person approves the pull request. It is a science-class change, so it also needs a science reviewer.
- Every convention has an identifier (`C<section>.<item>`) and exactly one status:
  - `PROPOSED`: the session proposes it. A person accepts it or corrects it in the pull request.
  - `OPEN`: the session cannot responsibly propose it. The item states the question a person has to answer and, where useful, the options.
- To review, answer per identifier: accept, correct, or (for `OPEN`) decide.
- The numbers in this sheet are only labels: item numbers, month numbers and exponents in unit strings. The sheet contains no parameter value, threshold, uncertainty range or expected value. Those are supplied by people and live in the parameter catalogue, the test plan and the validation files.
- Field names given here say what travels with a value. The exact shape of each contract is fixed by its schema and its accepted example, which are separate units.
- Where a source would have to be cited, the text says `CITATION NEEDED`. A person supplies the citation.

## 1. Unit and direction of each indicator

### C1.1 Indicator list, identifiers and vocabulary

Status: PROPOSED

- The product reports three indicators per rotation, the ones named in the README: soil loss, exposure to water deficit, and the trend of soil carbon. Their identifiers are `soil_loss`, `water_deficit_exposure` and `soil_carbon_trend`.
- Identifiers are lower case with underscores. They are the same in every contract, file and screen. Display names shown to the user are interface text and are not fixed here.
- Every indicator value carries its unit as a string, written exactly as in this sheet. A consumer checks the unit it receives and never assumes it.
- In unit strings, `t` is the metric tonne, `ha` is the hectare, `yr` is one agricultural year (section 5), `month` is one calendar month, `days` is a count of days, and `t C` is tonnes of carbon.
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
| Sign | Never negative |
| Direction | `lower_is_better` |

The method that produces the value is not defined here. Its description and its source belong to the method documentation: CITATION NEEDED.

### C1.3 Exposure to water deficit: identifier, time basis and direction

Status: PROPOSED

| Aspect | Convention |
|---|---|
| Identifier | `water_deficit_exposure` |
| Unit | `days yr-1`, and `days month-1` for a monthly breakdown. This unit holds only if the definition decided under C1.4 is a count of days. If the definition is another kind of quantity, the unit follows that definition and this row is corrected with it |
| Time basis | One value per agricultural year. Where a contract asks for a monthly breakdown, one value per calendar month |
| Sign | Never negative |
| Direction | `lower_is_better` |

No threshold appears in this sheet or in any engine. The threshold that the definition needs lives only in the test plan.

### C1.4 Exposure to water deficit: scientific definition

Status: OPEN

Question for the science reviewers: **what exactly is counted or measured as "exposure to water deficit"?** The answer has to state:

1. Which quantity is compared with the threshold, or accumulated. Options:
   - (a) a count of days on which a state of the daily water balance is below a threshold held in the test plan;
   - (b) the same count, restricted to periods that matter for the crop in the ground;
   - (c) an accumulated shortfall of water over the period, expressed as a depth of water;
   - (d) a dimensionless ratio between water supplied and water demanded over the period.
2. Which state of the water balance is used (for example the water stored in the soil, or the gap between demand and supply).
3. Whether days without a crop in the ground count.
4. The unit that follows from the answer, so that C1.3 can be confirmed or corrected.
5. The source of the definition: CITATION NEEDED.

Until this is answered, no engine reports `water_deficit_exposure` as anything but missing.

### C1.5 Trend of soil carbon: identifier, unit, time basis and direction

Status: PROPOSED

| Aspect | Convention |
|---|---|
| Identifier | `soil_carbon_trend` |
| Quantity | Mean change per year of the stock of soil organic carbon per unit of field area |
| Unit | `t C ha-1 yr-1` |
| Time basis | One value per rotation and per carbon model, over the simulation horizon that both carbon models share. Stocks by month, year and rotation are not this indicator; they travel in the carbon balance contract |
| Sign | Signed. Positive means the stock increases; negative means it decreases |
| Direction | `higher_is_better` |

Each value names the carbon model that produced it. Values from different models are never averaged or merged into one value by an engine.

### C1.6 Trend of soil carbon: what the trend is computed over

Status: OPEN

Questions for the science reviewers:

1. **To which soil depth does the stock refer?** The depth is a parameter value and is supplied by a person. Both carbon models must refer to the same depth.
2. **How is the trend computed from the simulated stocks?** Options:
   - (a) the stock at the end of the horizon minus the stock at the start, divided by the length of the horizon;
   - (b) the slope of a line fitted to the yearly stocks over the horizon;
   - (c) the mean change over whole rotation cycles only, leaving out an incomplete last cycle.
3. **Which horizon?** The length of the horizon is a value supplied by a person and belongs to the carbon forcing contract, not to this sheet.
4. The source of the chosen computation: CITATION NEEDED.

## 2. How an uncertainty range travels with a value

### C2.1 The range travels inside the value

Status: PROPOSED

- A value and its uncertainty range travel together as one item. The range is never sent in a separate table, in a note or as text after the number.
- The range is a pair of bounds, `low` and `high`, in the same unit as the value. The bounds are absolute quantities, not a percentage of the value and not a distance from it.
- `low` is not greater than the value, and the value is not greater than `high`. An item that breaks this order is invalid.
- The range carries a label, `kind`, that names what the range represents. The list of allowed labels is decided under C2.3.
- The two bounds travel together or not at all.

### C2.2 A value without a range says so

Status: PROPOSED

- When no range is available, the range is absent and carries a reason, using the reason codes of C3.2. An absent range is never written as two bounds equal to the value.
- No engine, adapter or session invents, widens, narrows or makes symmetric a range. The numbers behind a range come from the science reviewers through the parameter catalogue and the test plan.
- A value that is missing (section 3) has no range.

### C2.3 What a range represents

Status: OPEN

Question for the science reviewers: **what does the range around a reported value mean, and may more than one meaning be used?** Options:

- (a) the lowest and highest result obtained when the uncertain inputs are set to the bounds recorded in the parameter catalogue;
- (b) the spread of the result across the years of the climate record;
- (c) a statistical interval at a level stated in the test plan;
- (d) more than one of these, each range carrying its `kind` label so that they are never confused.

The answer fixes the list of allowed `kind` labels. Any level or bound it needs is a value supplied by a person. The source of the method: CITATION NEEDED.

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

- A result that needs a missing input is itself missing, with reason `MISSING_INPUT`. Nothing is filled in, interpolated or replaced by a default without a decision under C3.4.
- The interface shows a missing value as missing, with its reason. It never shows a blank or a zero in its place.

### C3.4 Gaps inside a series that is aggregated

Status: OPEN

Question for the science reviewers: **may a monthly or yearly value be computed from a daily series that has missing days?** Options:

- (a) never: one missing day makes the aggregate missing;
- (b) yes, up to a tolerance; the tolerance is a threshold supplied by a person and lives only in the test plan;
- (c) yes, after filling the gaps with a method chosen by a person; the filled values are then labelled under section 4 and the method needs its source: CITATION NEEDED.

Until this is answered, C3.3 applies and the aggregate is missing.

## 4. Provenance label per value

### C4.1 The four labels

Status: PROPOSED

Every value that is not missing carries exactly one of four labels, written in upper case exactly as below.

| Label | Meaning |
|---|---|
| `DECLARED` | Stated by the user for this case, for example the rotation and its management |
| `OBSERVED` | Taken from a measurement or from an observational data source, unchanged except for a change of unit |
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

### C4.4 Data products that are themselves modelled

Status: OPEN

Question for the science reviewers: **which label does a value carry when it is retrieved from a data source whose values come from a model or a retrieval algorithm rather than from a direct measurement at the field?** This concerns gridded climate, precipitation, soil and terrain products. Options:

- (a) `OBSERVED`, with the product named as the source;
- (b) `SIMULATED`;
- (c) decided per source and recorded next to each adapter.

The answer also fixes the word the interface uses for these values, which is a decision people keep (blueprint section 3.5).

### C4.5 Parameters from the catalogue and assumptions

Status: OPEN

Question for the science reviewers and the lead developer: **which label does a parameter value taken from the parameter catalogue carry, and which label does an assumption carry?** Options:

- (a) `DECLARED`, read as declared by the project, with the citation as source;
- (b) `DERIVED`;
- (c) no provenance label: parameters and assumptions carry only their source or the "assumption" mark, and the four labels apply to case data and results only.

### C4.6 Label of the soil-loss indicator

Status: OPEN

Question for the science reviewers: **is the soil loss computed by an annual equation `DERIVED` or `SIMULATED`?** Under C4.3 it would be `DERIVED` unless one of its inputs is `SIMULATED`. The answer decides the word shown next to the value in the interface.

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

- An agricultural year is twelve consecutive calendar months beginning at the start month decided under C5.4.
- An agricultural year is identified by the calendar year in which it begins, in a field named `ag_year`. A bare `year` always means the calendar year.
- Months inside an agricultural year keep their calendar numbers. There is no second numbering of months counted from the start of the agricultural year.

### C5.4 Start month of the agricultural year

Status: OPEN

Question for the science reviewers: **in which calendar month does the agricultural year begin?** Options:

- (a) one start month for the whole project;
- (b) a start month per region or hemisphere, recorded with the case;
- (c) a start month taken from the rotation the user declares.

The start month is a value supplied by a person. Its source, if it follows a published convention: CITATION NEEDED.

### C5.5 Incomplete agricultural years

Status: PROPOSED

An agricultural year that the data series does not cover from its first day to its last is not reported as a full year. Its yearly values are missing with reason `NO_COVERAGE`, unless a decision under C3.4 allows otherwise.

## 6. Time zone of every daily series

### C6.1 Every daily series states its time zone

Status: PROPOSED

- Every daily series carries one explicit `time_zone` for the whole series. No series has an implied time zone.
- A day is the interval from midnight to the next midnight in the time zone of the series, and it is labelled with its date in that time zone (C5.2).
- Months and agricultural years group the days of a series by those dates.

### C6.2 Series from the NASA POWER adapter

Status: PROPOSED

Daily series delivered by the NASA POWER adapter, meteorology and precipitation, are in UTC (blueprint section 8; decision of the lead developer). Their `time_zone` is the string `UTC`.

How the service itself defines the day of its daily values is checked by a person against the public documentation of the service when the adapter is built: CITATION NEEDED.

### C6.3 Series produced by an engine

Status: PROPOSED

- A daily series produced by an engine has the time zone of the daily series that drives it.
- An engine does not move a daily series to another time zone.
- An engine never combines daily series that have different time zones. In that case its result is missing with reason `NOT_COMPUTABLE`.

### C6.4 Daily series from any other source

Status: OPEN

The time zone of a daily series from any source other than the NASA POWER adapter is not defined until a person chooses that source. Question for the science reviewers, asked again for each new source: **in which time zone are the days of this series defined, and, if it is not UTC, is the series converted, by whom and with which method?** Until it is answered, that series is not combined with any other daily series.

### C6.5 A day in UTC is not the local day at the field

Status: OPEN

Question for the science reviewers: **is it acceptable that daily processes at the field are driven by days defined in UTC, which do not line up with the local day?** Options:

- (a) accept it and state it as a limit in the method documentation;
- (b) require the adapter to deliver days defined in local time where the source allows it.

This does not reopen C6.2; it asks how the consequence is handled and described.

## Not covered by this sheet

- Any indicator other than the three in C1.1.
- Parameter values, thresholds, uncertainty ranges as numbers and expected test values. They are supplied by people in the parameter catalogue, the test plan and the validation files.
- Schemas and examples of contracts.
- The numbering of the years inside a rotation, which belongs to the rotation definition contract.
