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

### C1.3 Exposure to water deficit: identifier, unit, time basis and direction

Status: PROPOSED

The direction and the absence of a unit below are not proposals of the session. The lead developer stated them on 14 November 2026 as a consequence of the decision recorded under C1.4: with a ratio of water transpired to water demanded, higher is better and the value has no unit. Acceptance by a science reviewer is pending. The rest of this item is proposed by the session.

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

Still to be supplied by a person:

- `OPEN`: the definition of the critical period per crop. Question for the science reviewers: **which period of each crop is its critical period?**
- `OPEN`: the state of the water balance that the ratio and the descriptive measures use. Question for the science reviewers: **which quantities of the daily water balance are "water transpired" and "water demanded", and which state of the balance do the descriptive measures use?**
- `OPEN`: days without a crop in the ground. Question for the science reviewers: **do days without a crop in the ground count?**
- The source of the measure: CITATION NEEDED.

While the definition is incomplete (critical period, state of the balance), no engine reports `water_deficit_exposure` as anything but missing, with its reason.

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
