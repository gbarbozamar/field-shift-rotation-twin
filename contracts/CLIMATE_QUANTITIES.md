# Climate quantities

The closed list of climate quantities that travel in the contract "Site data: climate" (`contracts/inputs/site_climate.py`): for each one its identifier, what it is, its unit string, its measurement height where one applies, its provenance label, and which engine and method need it.

Status of the file: **PROPOSED** (blueprint section 3.7). Nothing here is in force until people approve the pull request: a science reviewer, because sources, units and methods are science-class and data decisions, and the platform developer, whose adapter writes these identifiers and unit strings. The lead developer and the engines developer are the consumers.

The entries marked `DECIDED` record decisions of the lead developer of 14 November 2026, D23 to D32 of issue #77 (the comment "Decisions of 14 November 2026 on the climate quantities"). They are science class: a science reviewer may still review them.

## How to read this file

- This file was written by builder sessions. It proposes identifiers, unit strings and a provenance label. It chooses no data source, no product and no variable of a source, and it names no method that the repository does not already name. The choices recorded as `DECIDED` are the lead developer's, transcribed from issue #77.
- Every quantity has an identifier of this file (`CQ1`, `CQ1b`, `CQ2` to `CQ6`) and exactly one status, given on its `Status:` line:
  - `DECIDED`: a person decided the source parameter, the identifier and the unit string. The `Status:` line names who, when and which decision.
  - `PROPOSED`: the session proposes the identifier, the unit string, the height and the label. A person accepts or corrects them in the pull request.
  - `OPEN`: the session cannot responsibly propose which quantity travels. The entry gives the candidates, so that the question is concrete, and names the question a person has to answer.
- A `PROPOSED` or `DECIDED` quantity can still leave a part for a person to supply. That part is a sub-point marked `OPEN` that points to its question. Questions are listed once, under [OPEN](#open), as `O1` to `O14`, each with the role that answers it. A question that a decision answers keeps its number and is marked `DECIDED` with its decision; what the decision leaves open stays `OPEN`.
- Rules that hold for every quantity are `R1` to `R7`. They are all `PROPOSED`.
- **Facts about the NASA POWER service come only from the scout report in issue #15**, written as "(#15, section N)". Text in "double quotes" after such a reference is quoted from that report, which quotes the public documentation as read on 14 November 2026. `NOT FOUND` is the report's own mark: the scout did not find it on the pages it read. The scout requested no data. Nothing about the service is stated here from memory: what #15 does not say is `OPEN`.
- **What the service answered to one documented request comes only from decision D32 of issue #77**, written as "(D32)". The request and the raw response are committed in `docs/evidence/nasa-power-2026-11-14/` ([The documented request](#the-documented-request)).
- **Facts about the worked FAO-56 example come only from the scout report in issue #13**, written as "(#13, section N)", and only to list which inputs a daily reference evapotranspiration of that kind needs. That report reproduces no value and no equation, and neither does this file.
- A source parameter appears here only as #15 documents it. Its presence is not a choice: which parameters are requested is decided by the science reviewers (`adapters/README.md`, OPEN 1). For the quantities marked `DECIDED`, the parameter was chosen by the lead developer (D23 to D27 of issue #77).
- The numbers in this file are labels or quotations: item numbers, exponents in unit strings, heights that are part of the description of a quantity as the two reports give them, and dates and limits inside quotations of #15. The file contains no parameter value, threshold, uncertainty range or expected value, and an engine reads no number from it.
- Where a source would have to be cited, the text says `CITATION NEEDED`. A person supplies the citation.
- Conventions such as C4.4 refer to `contracts/CONVENTIONS.md`; EP3 and Q10 to `contracts/ENTRYPOINTS.md`; M1.2 to `docs/METHODS.md`.

## What puts a quantity in the list

A quantity is in the list only if an engine needs it for a method that `docs/METHODS.md` or blueprint section 8 names. Three needs exist today:

| Need | Engine | Method, and where it is named | What it reads |
|---|---|---|---|
| N1 | `engine/erosion/` | The monthly fraction of the annual erosivity and its variation between years, from a daily erosivity index computed from daily precipitation (M1.2; blueprint section 8, Block 1: "monthly erosivity fraction") | Daily precipitation |
| N2 | `engine/water/et0/` | "reference evapotranspiration against a worked FAO-56 example [H2]" (blueprint section 8, Block 1) | The inputs of the daily worked example, as #13 lists them (table below) |
| N3 | Lane L1 Engines; the blueprint names no folder | "Frost and heat-day counts per month from NASA POWER daily minimum and maximum temperature" (blueprint section 8, gated extras) | Daily minimum and maximum temperature |

Limits of this reading:

- The method of the reference evapotranspiration is not in `docs/METHODS.md` yet ("Not in this file yet": `OPEN`, for the lead developer). N2 rests on the blueprint wording and on #13, which identifies the daily worked example as EXAMPLE 18. Whether that example is the one of [H2] is `OPEN` in `docs/VALIDATION.md` (H2, "Definition: OPEN"). If a person names another method or another example, `CQ2` to `CQ6` are revised: O8.
- The method of the daily water balance (`engine/water/balance/`, blueprint section 8, Blocks 1 and 2) is not named anywhere. It adds no quantity to this list. When a person names it, the list is revised: O8.
- N3 is a gated extra. It adds no quantity that N2 does not already need.

Inputs of the daily worked example, as #13 reports them (section 3, "Given" list and introductory sentence; section 5):

| Input, as #13 prints it | Unit as printed | Where it is in this file |
|---|---|---|
| Maximum air temperature | °C | `CQ2` |
| Minimum air temperature | °C | `CQ3` |
| Maximum relative humidity, minimum relative humidity | % | `CQ4`, `DECIDED` as dew point (D25); the route of the method from dew point is `OPEN` (O2) |
| Wind speed measured at a stated height, converted to the height the equation uses | km/h | `CQ5`, `DECIDED` at 2 m (D26) |
| Actual hours of sunshine, from which solar radiation is estimated | hours | `CQ6`, `DECIDED` as solar radiation (D27) |
| The date | | The `date` of each day of a series (C5.2). Not a quantity |
| Latitude and altitude of the station | degrees and minutes; m above sea level | The point of the series in the climate contract (D9, D18): [Latitude and elevation](#latitude-and-elevation) |

## Rules for every quantity

Status of R1 to R7: PROPOSED

### R1 The list is closed

- The quantities of this file are the only values that `quantity` of a daily series of `SiteClimate` takes, and the only values that `ParameterSpec.quantity` of the NASA POWER adapter takes. A new quantity is a contract change and is added only at a checkpoint.
- Every quantity here is a daily series. No monthly quantity is proposed: `monthly_series` stays empty, as the adapter already writes it, and an engine aggregates what it needs ([Not in the list](#not-in-the-list-and-why)).
- A quantity that no named method needs is not in the list.

### R2 Identifiers

- An identifier is lower case with underscores (C1.1) and matches the pattern the adapter and the model accept for `quantity`: a lower-case letter, then lower-case letters, digits and underscores.
- It names the physical quantity, then the statistic of the day where the quantity is not a mean or a total (`_max`, `_min`), then the height where one applies (R3). It never repeats the parameter code of a source.
- Identifiers with a height contain a digit. The pattern accepts it; C1.1 says "lower case with underscores" and does not mention digits. A person accepts or corrects this reading.

### R3 Measurement height

- Where a height above the ground applies, it is the last part of the identifier, written as the number of metres and the letter `m` (`_2m`, `_10m`). One identifier is one quantity at one height.
- Reason: a daily series has no field for a height, and the same quantity at two heights must never travel under one name. If the model gains a height field instead, the suffix is dropped: a person decides (the lead developer, with the platform developer).
- The heights written here are those that #15 quotes in the description of each source parameter. A height that a method needs and a height at which a source gives a value are two different facts: O1.

### R4 Unit strings

- A unit string is written in the notation of C1.1: symbols separated by one space, a negative exponent for "per".
- C1.1 defines the symbols of the three indicators only. This file adds the symbols it uses: `mm` (millimetre of water depth), `day` (one day of the series, C6.1), `degC` (degree Celsius), `%` (per cent), `m` (metre), `s` (second), `g` (gram), `kg` (kilogram), `MJ` (megajoule), `W` (watt), `kWh` (kilowatt-hour). Whether C1.1 takes them in is for the lead developer.
- The unit string of a quantity is the text a person writes in `ParameterSpec.unit`. The adapter does not convert. Each proposed string is the session's writing of the Daily "Metric Units" that #15 reports for the source parameter; a person checks that the unit the service returns, in the chosen community, is that unit (`adapters/README.md`, OPEN 2 and 3). For the `DECIDED` quantities the lead developer wrote the unit string (D23 to D27), and D32 records the unit label of each requested parameter in the response ([The documented request](#the-documented-request)).
- A consumer checks the unit string it receives and never assumes it (C1.1).

### R5 Provenance label

- Every quantity of this list is taken from a data source and carries the label `OBSERVED`, also when the data product is itself modelled (C4.4; decided by the lead developer, acceptance by a science reviewer pending). The label is stated once per series.
- The label is not the source (C4.2). C4.4 asks for "the product named as the source". What the `source` text of a series holds is question 22 of `contracts/inputs/README.md`; what it holds when one series is fed by more than one product is O12.

### R6 Time

- Every quantity is one value per day. The day and the time zone follow section 6 of the conventions sheet: a series of the NASA POWER adapter says `time_zone: "UTC"` (C6.2); a series from any other source has no defined time zone until a person answers C6.4.
- How the service bounds a UTC day for each variable is `NOT FOUND` in #15 (section 4) and is already `OPEN` in `adapters/README.md` (OPEN 7). It is not repeated per quantity.

### R7 Missing days and the range

- A day without data stays in its series as missing, with its reason (C3.1; `fill_reason` of the adapter). Zero is a value.
- No quantity of this list carries an uncertainty range today. The series states the reason once, in `range_missing` (C2.2). The reason code is `NO_COVERAGE` (O6, decided by D31 of issue #77, which replaces D15).

## Summary

The entries below are the list; this table repeats them. The status of a quantity is the one on its `Status:` line.

| Id | Identifier | What it is | Unit string | Height | Label | Needed by | Source parameter, as #15 documents it | Status |
|---|---|---|---|---|---|---|---|---|
| `CQ1` | `precipitation` | Total precipitation at the surface during the day | `mm day-1` | none | `OBSERVED` | N1 | `IMERG_PRECTOT` of NASA POWER, through the platform adapter (D23) | DECIDED (D23) |
| `CQ1b` | `precipitation_reanalysis` | Control series of total precipitation at the surface during the day, beside `CQ1`; not a fallback | `mm day-1` | none | `OBSERVED` | Control of `CQ1` (D24) | `PRECTOTCORR` (D24) | DECIDED (D24) |
| `CQ2` | `air_temperature_max_2m` | Highest air temperature of the day | `degC` | 2 m | `OBSERVED` | N2, N3 | `T2M_MAX`, "Degrees Celsius (C)" | DECIDED (D35) |
| `CQ3` | `air_temperature_min_2m` | Lowest air temperature of the day | `degC` | 2 m | `OBSERVED` | N2, N3 | `T2M_MIN`, "Degrees Celsius (C)" | DECIDED (D35) |
| `CQ4` | `dew_point_temperature_2m` | Humidity of the air, as dew point | `degC` | 2 m | `OBSERVED` | N2 | `T2MDEW` (D25) | DECIDED (D25) |
| `CQ5` | `wind_speed_2m` | Mean wind speed of the day | `m s-1` | 2 m | `OBSERVED` | N2 | `WS2M` (D26) | DECIDED (D26) |
| `CQ6` | `solar_radiation` | Radiation input of the reference evapotranspiration | `MJ m-2 day-1` (community AG, D28) | none | `OBSERVED` | N2 | `ALLSKY_SFC_SW_DWN` (D27) | DECIDED (D27) |

Five quantities are decided (`CQ1`, `CQ1b`, `CQ4`, `CQ5`, `CQ6`) and two are proposed (`CQ2`, `CQ3`). None is open. The candidates that were not chosen (`relative_humidity_2m`, `specific_humidity_2m`, `wind_speed_10m`) do not enter the list.

## The quantities

### CQ1 Daily precipitation

Status: DECIDED — decided by the lead developer on 14 November 2026, issue #77, D23

| Aspect | Entry |
|---|---|
| Identifier | `precipitation` (D23). The placeholder example of `contracts/inputs/` already uses it |
| What it is | The total precipitation at the surface during the day of the series (C6.1), as a depth of water |
| Unit string | `mm day-1` (D23) |
| Measurement height | None applies |
| Provenance label | `OBSERVED` (R5) |
| Needed by | `engine/erosion/`, N1: the daily erosivity index of M1.2, used in relative terms only, for the share of each month in the annual total and the ratio between years. M1.2 also names a control of the monthly fraction that reads monthly precipitation; proposed here: the engine aggregates it from this series (R1). M1.2: "Daily precipitation comes from the platform adapter (blueprint section 8: IMERG precipitation)" |
| Also expected to read it | `engine/water/balance/` (blueprint section 8). Its method is not named yet, so this is not what puts the quantity in the list: O8 |
| Source parameter | **`IMERG_PRECTOT`** of NASA POWER, through the platform adapter (D23; O4 (a)). A second series, `PRECTOTCORR`, travels beside it as a control series under its own identifier: `CQ1b` (D24) |

The candidates as they were put to the lead developer, as #15 describes them (section 3; Parameter Dictionary, Daily tab):

| Parameter | Description | Unit on the Daily tab | Source and dates listed | Communities listed | Tags |
|---|---|---|---|---|---|
| `IMERG_PRECTOT` | "The average IMERG total precipitation at the surface of the earth." | "Millimeter per Day (mm/day)"; "Ingested directly from the source provider; no computation required." | "GPM IMERG, 0.1 x 0.1 Degrees, Start 1998/01/01, End 2029/12/31" | RE, SB, AG | "Core Parameter" |
| `PRECTOTCORR` | "The average MERRA-2 bias corrected total precipitation at the surface of the earth." | "Millimeter per Day (mm/day)"; "The data is summed from the previous temporal level." | "GMAO GEOS-IT, 0.5 x 0.625 Degrees, Start 2020/01/01, End 2026/11/11"; "GMAO MERRA-2, 0.5 x 0.625 Degrees, Start 1981/01/01, End 2026/09/30"; "NASA Earth Exchange Global Daily Downscaled Projections, 0.25 x 0.25 Degrees, 2015/01/01 to 2100/12/31" | RE, SB, AG | "Core Parameter", "Near Real Time (NRT)" |
| `PRECTOT` | "The average HYDROSCS total precipitation at the surface of the earth." | "Millimeter per Day (mm/day)"; "The data is summed from the previous temporal level." | "Hydrometeorological forcing for SERVIR Climate Services, 0.05 x 0.05 Degrees, Start 2001/12/31, End 2029/12/31" | RE, SB, AG, HY | status tag "Reviewing" |

What #15 says that bears on the choice, without choosing:

- IMERG and time: "IMERG is available at the daily temporal level in UTC only. The time series will include both Late and Final Run data within a few months of NRT; end the analysis 3.5 months behind NRT when assessing trends." (#15, section 3). `NOT FOUND`: which run a given day comes from in the response.
- IMERG and its unit: the Meteorological page gives `IMERG_PRECTOT` as "mm", "Daily sum from half-hourly"; the dictionary gives "Millimeter per Day (mm/day)" and calls it "The average IMERG total precipitation" (#15, section 3, inconsistency 3).
- IMERG and its first date: "June 1, 1998", "Start: 1998/01/01", "2001 – NRT" and "reprocessed back to 2000" all appear in the documentation (#15, section 3, inconsistency 1).
- IMERG and the community: the dictionary lists `IMERG_PRECTOT` at daily level under RE, SB and AG, not HY (#15, section 3, inconsistency 6). `NOT FOUND`: whether the community `ag` accepts it at daily level beyond the dictionary listing.
- `PRECTOT`: the scout's reading is that in the current dictionary this code is not MERRA-2 uncorrected precipitation; it is described as HYDROSCS precipitation and carries the status tag "Reviewing" (#15, section 3).
- `PRECTOTCORR`: its description names MERRA-2, and its Daily tab lists three sources with different periods. `NOT FOUND`: which of them supplies a given date (#15, section 5).

What the documented request shows (D32): the community `ag` accepts `IMERG_PRECTOT` at daily level ("ten daily values returned"); the response labels its unit `mm/day`; the header says `"time_standard": "UTC"`. Still not settled by one request: which IMERG run (Late or Final) a given day comes from, and whether the daily IMERG value is a depth summed over the UTC day (D32).

Parts left for a person:

- `DECIDED` (D23): the series comes from `IMERG_PRECTOT` of NASA POWER, through the platform adapter. O4.
- `OPEN`: whether the daily value of `IMERG_PRECTOT` is a depth summed over the UTC day, which the unit string `mm day-1` assumes. D32: "the unit `mm/day` is consistent with it", and one request does not settle it. O5.
- `DECIDED` (D24): no fallback. `PRECTOTCORR` is a control series that travels beside the main one under its own identifier `precipitation_reanalysis` (`CQ1b`); the main series stays `precipitation`. O4.
- `OPEN`: which IMERG run (Late or Final) a given day comes from (D32). O4.

### CQ1b Daily precipitation, control series

Status: DECIDED — decided by the lead developer on 14 November 2026, issue #77, D24

| Aspect | Entry |
|---|---|
| Identifier | `precipitation_reanalysis` (D24) |
| What it is | The total precipitation at the surface during the day of the series (C6.1), as a depth of water, from `PRECTOTCORR`: a control series that travels beside `CQ1`. "It is not a fallback: the main series stays `precipitation`" (D24) |
| Unit string | `mm day-1` (D24) |
| Measurement height | None applies, as for `CQ1` |
| Provenance label | `OBSERVED` (D24; R5) |
| Needed by | A control of `CQ1` (D24). D24 names no engine and no method that reads it |
| Source parameter | **`PRECTOTCORR`** (D24), as #15 describes it in the table of `CQ1` |

What D32 shows: the response labels the unit of `PRECTOTCORR` `mm/day`. Still not settled by one request: which underlying product supplies a given day of `PRECTOTCORR` (D32). O4, O12.

### CQ2 Daily maximum air temperature

Status: DECIDED (decided by the lead developer on 14 November 2026, issue #77, D35)

| Aspect | Entry |
|---|---|
| Identifier | `air_temperature_max_2m` |
| What it is | The highest air temperature of the day of the series |
| Unit string | `degC` |
| Measurement height | 2 m above the surface, as the description of the source parameter says |
| Provenance label | `OBSERVED` (R5) |
| Needed by | `engine/water/et0/`, N2: "Maximum air temperature" is in the "Given" list of the daily worked example (#13, section 3). Also N3 |
| Source parameter | `T2M_MAX`, "Temperature at 2 Meters Maximum": "The maximum hourly air (dry bulb) temperature at 2 meters above the surface of the earth in the period of interest." Daily unit "Degrees Celsius (C)" (#15, section 2). It is the only parameter #15 documents for this quantity. The science reviewers confirm it (`adapters/README.md`, OPEN 1) |

What #15 says about it:

- "Daily maximum and minimum temperatures are obtained from the 24 hourly temperature values, not an average of those values." and "Daily extremes preserve the highest (or lowest) hourly value within the local-time day instead of a mean" (#15, section 2). The adapter requests UTC. How a UTC day is bounded is `NOT FOUND` (R6).
- Sources listed on the Daily tab: "GMAO GEOS-IT; Hydrometeorological forcing for SERVIR Climate Services; GMAO MERRA-2; NASA Earth Exchange Global Daily Downscaled Projections". `NOT FOUND`: which of them supplies a given date in a plain daily point request (#15, section 5). O12.

### CQ3 Daily minimum air temperature

Status: DECIDED (decided by the lead developer on 14 November 2026, issue #77, D35)

| Aspect | Entry |
|---|---|
| Identifier | `air_temperature_min_2m` |
| What it is | The lowest air temperature of the day of the series |
| Unit string | `degC` |
| Measurement height | 2 m above the surface, as the description of the source parameter says |
| Provenance label | `OBSERVED` (R5) |
| Needed by | `engine/water/et0/`, N2: "Minimum air temperature" is in the "Given" list of the daily worked example (#13, section 3). Also N3 |
| Source parameter | `T2M_MIN`, "Temperature at 2 Meters Minimum": "The minimum hourly air (dry bulb) temperature at 2 meters above the surface of the earth in the period of interest." Daily unit "Degrees Celsius (C)" (#15, section 2). It is the only parameter #15 documents for this quantity. The science reviewers confirm it (`adapters/README.md`, OPEN 1) |

The two notes of `CQ2` hold for `CQ3` as well: the same statements on daily extremes and the same four sources.

### CQ4 Air humidity

Status: DECIDED — decided by the lead developer on 14 November 2026, issue #77, D25

| Aspect | Entry |
|---|---|
| Identifier | `dew_point_temperature_2m` (D25) |
| What it is | The humidity of the air, as the dew/frost point temperature at 2 m above the surface (the description of `T2MDEW`, as #15 quotes it below) |
| Unit string | `degC` (D25) |
| Measurement height | 2 m, as the description of the source parameter says |
| Provenance label | `OBSERVED` (R5) |
| Needed by | `engine/water/et0/`, N2 |
| Source parameter | **`T2MDEW`** (D25) |

`OPEN`: the route of the reference evapotranspiration method from dew point, read in the method's text. "The scout report #13 does not report it" (D25). A person supplies it. O2.

What D32 shows: the response labels the unit of `T2MDEW` `C`.

What follows is the text that put the question; it is kept as the record of the choice.

Why it was `OPEN`: the worked example and the source do not offer the same quantity, and choosing between the forms of humidity is choosing a variable of a source and a route of the method.

- What the method of N2 reads (#13, sections 3 to 5): the daily worked example is given maximum and minimum relative humidity, in %, and derives the actual vapour pressure from them (the case "For RHmax and RHmin"). Another example of the same text is given the actual vapour pressure directly, and one estimates humidity when only the two temperatures are recorded. #13 does not report whether the text has a route from dew point or from specific humidity.
- What the source offers (#15, section 2): the three parameters below. The report marks as `NOT FOUND` any daily minimum or maximum relative humidity parameter: a dictionary search for "Humidity" listed only relative humidity at 2 m, specific humidity at 2 m and at 10 m, and variants of a set based on hours. Also `NOT FOUND`: how `RH2M` and `T2MDEW` are derived from the model fields.

Candidates. The identifier and the unit string of each were proposed for the case that it is chosen; D25 chose `dew_point_temperature_2m`:

| Candidate identifier | Unit string | Source parameter, as #15 documents it (section 2) |
|---|---|---|
| `relative_humidity_2m` | `%` | `RH2M`, "Relative Humidity at 2 Meters": "The ratio of vapor pressure to the saturation vapor pressure with respect to a plane surface of pure water, expressed in percent." Daily unit "Percentage (%)". Communities RE, SB, AG, HY |
| `dew_point_temperature_2m` | `degC` | `T2MDEW`, "Dew/Frost Point at 2 Meters": "The dew/frost point temperature at 2 meters above the surface of the earth." Daily unit "Degrees Celsius (C)". Communities RE, SB, AG, HY |
| `specific_humidity_2m` | `g kg-1` | `QV2M`, "Specific Humidity at 2 Meters": "The ratio of the mass of water vapor to the total mass of air at 2 meters." "Grams per Kilogram (g/kg)" (the report notes: source unit; community list not captured) |

Whatever is chosen: measurement height 2 m, label `OBSERVED` (R5), needed by `engine/water/et0/` (N2).

Question: O2.

### CQ5 Wind speed

Status: DECIDED — decided by the lead developer on 14 November 2026, issue #77, D26

| Aspect | Entry |
|---|---|
| Identifier | `wind_speed_2m` (D26) |
| What it is | The mean wind speed of the day at 2 m |
| Unit string | `m s-1` (D26) |
| Measurement height | 2 m (D26). "No height conversion in the engine" (D26) |
| Provenance label | `OBSERVED` (R5) |
| Needed by | `engine/water/et0/`, N2 |
| Source parameter | **`WS2M`** (D26) |

What D32 shows: the response labels the unit of `WS2M` `m/s`.

What follows is the text that put the question; it is kept as the record of the choice.

Why it was `OPEN`: the source gives wind speed at more than one height, the equation of the method uses one height, and which series travels depends on who converts.

- What the method of N2 reads (#13, section 5): the equation defines its wind term as wind speed at 2 m height. Wind measured at another height is adjusted with a wind profile relationship that the text gives "for measurements above a short grassed surface". The daily worked example is given wind at another height and converts it in its first block.
- What the source offers (#15, section 2): the two parameters below; "The wind speed is at 2 m, 10 m, and 50 m above the average elevation of the grid"; wind is available "at elevations of 10 meters and 50 meters above the Earth's surface. Wind data products at 2-meter elevation are also available through the Agroclimatology community." (the dictionary lists `WS2M` under all four communities); a 50 m parameter and maximum, minimum and range variants exist (entries not opened by the scout).
- A custom height can be requested with the optional argument `wind-elevation`: "Wind Elevation values in Meters are required to be between 10m and 300m." The report adds that the corrected wind speed is computed from the 50 m wind speed with a power law and a surface-roughness exponent per surface type (#15, section 2).
- Both dictionary entries carry the warning: "Wind speed is provided from an average of a large area and may not represent a point location due to surface properties, elevation changes, and local weather phenomena."
- #15 does not report how the service obtains the 2 m wind speed.

Candidates. The identifier of each was proposed for the case that it is chosen; D26 chose `wind_speed_2m`:

| Candidate identifier | Unit string | Height | Source parameter, as #15 documents it (section 2) |
|---|---|---|---|
| `wind_speed_2m` | `m s-1` | 2 m | `WS2M`, "Wind Speed at 2 Meters": "The average of wind speed at 2 meters above the surface of the earth." Daily unit "Meter per Second (m/s)". Sources listed: GEOS-IT; MERRA-2. Communities RE, SB, AG, HY |
| `wind_speed_10m` | `m s-1` | 10 m | `WS10M`, "Wind Speed at 10 Meters": "The average of wind speed at 10 meters above the surface of the earth." Daily unit "Meter per Second (m/s)". Sources listed: GEOS-IT; SERVIR hydrometeorological forcing; MERRA-2; NASA Earth Exchange projections. Communities RE, SB, AG, HY |

Whatever is chosen: label `OBSERVED` (R5), needed by `engine/water/et0/` (N2). The adapter does not convert a height: if the series travels at a height other than the one the method uses, the engine converts, with a method and parameters that a person supplies.

Question: O1.

### CQ6 Radiation

Status: DECIDED — decided by the lead developer on 14 November 2026, issue #77, D27

| Aspect | Entry |
|---|---|
| Identifier | `solar_radiation` (D27) |
| What it is | Solar radiation that reaches a horizontal surface at the ground during the day, under the sky as it was |
| Unit string | `MJ m-2 day-1` (D27), in the community AG (D28) |
| Measurement height | None applies |
| Provenance label | `OBSERVED` (R5) |
| Needed by | `engine/water/et0/`, N2. "The engine derives net radiation; it needs latitude and elevation, which travel with the series (D9, D18)" (D27) |
| Source parameter | **`ALLSKY_SFC_SW_DWN`** (D27) |

What D32 shows: the response labels the unit of `ALLSKY_SFC_SW_DWN` `MJ/m^2/day`; "the "per Hour" wording of the dictionary does not appear in the response".

What follows is the text that put the question; it is kept as the record of the choice.

Why it was `OPEN`: the worked example and the source start from different quantities, the source has more than one radiation parameter, and the unit of the one that #15 opened depends on the community.

- What the method of N2 reads (#13, sections 3 to 5): in the daily worked example solar radiation is not measured. It is estimated from the actual hours of sunshine; extraterrestrial radiation, daylight hours, clear-sky, net shortwave, net longwave and net radiation are derived. Another example of the same text is given measured solar radiation, and the title of one says it determines solar radiation from temperature data.
- What the source offers (#15, section 2): the parameter below; "The POWER solar values are the downward solar radiation reaching the Earth's surface for all-sky conditions. ... POWER data does not provide net radiation"; the dictionary also lists Clear Sky Surface Shortwave Downward Irradiance and Top-Of-Atmosphere Shortwave Downward Irradiance (entries not opened by the scout, codes not read). #15 reports nothing about a sunshine-duration parameter.

Candidate. The identifier was proposed for the case that this quantity is chosen; D27 chose it:

| Candidate identifier | What it is | Source parameter, as #15 documents it (sections 1 and 2) |
|---|---|---|
| `solar_radiation` | Solar radiation that reaches a horizontal surface at the ground during the day, under the sky as it was | `ALLSKY_SFC_SW_DWN`, "All Sky Surface Shortwave Downward Irradiance": "The total solar irradiance incident (direct plus diffuse) on a horizontal plane at the surface of the earth under all sky conditions. An alternative term for the total solar irradiance is the "Global Horizontal Irradiance" or GHI." Communities RE, SB, AG, HY |

Unit string: `DECIDED`, `MJ m-2 day-1` (D27), with the community AG (D28). It was `OPEN` because the Daily unit of this parameter differs by community (#15, section 1), so the string follows the choice of community (`adapters/README.md`, OPEN 2):

| Community | Daily "Metric Units", as #15 quotes them | Unit string proposed if that community is chosen |
|---|---|---|
| Agroclimatology (AG), Hydrology (HY) | "Megajoule per Square Meter per Hour (MJ/m^2/day)". The report notes that the label says "per Hour" in words and "/day" in the symbol | `MJ m-2 day-1`, if a person confirms that the symbol and not the words is right |
| Infrastructure (SB) | "Watts per Square Meter (W m-2)" | `W m-2` |
| Energy (RE) | "Kilowatt-Hours per Square Meter per Day (kW-hr/m^2/day)" | `kWh m-2 day-1` |

Which unit the method needs is not in #13. The lead developer decided the unit with the community (D27, D28).

No height applies, label `OBSERVED` (R5), needed by `engine/water/et0/` (N2).

What #15 says that bears on the choice, without choosing:

- Sources listed on the Daily tab: "CERES FLASHFlux; SERVIR hydrometeorological forcing; NASA Earth Exchange projections; SRB; CERES SYN1deg" (#15, section 2). The solar record starts later than the meteorological one, and the joining of two of its sources "can introduce a step discontinuity that is not a physical climate signal" (#15, section 5). O7, O12.
- "Why is solar data missing from the daily products? Solar data is typically missing because the satellite observational data is missing and irretrievable." (#15, section 6).

Question: O3.

## Latitude and elevation

They are not series and they are not in the list. They are here because the method of N2 needs them; when this section was first written no contract carried them (D9, D18 and D27 below).

- What the method reads (#13, sections 3 to 5): the daily worked example is given the latitude and the altitude of the station, with the date, as site data. Atmospheric pressure, extraterrestrial radiation and daylight hours are among the quantities it derives, and the symbol list of the equation for extraterrestrial radiation includes the latitude. Which input feeds which equation is read by a person in the source.
- Where they are today: the request for climate carries `latitude` and `longitude` of one point (`adapters/ports.py`, `ClimateRequest`). `SiteClimate` and `SiteSoilSlope` carry no place (`contracts/inputs/README.md`, question 21), and the entry point of the water engine receives only the calendar and those two records (EP3). Nothing carries an elevation.
- What the source says (#15, sections 1 and 5): the JSON response holds `geometry: {type: "Point", coordinates: ["Longitude","Latitude","Elevation"]}`; the optional argument `site-elevation` is a "Custom site elevation in meters for atmospheric pressure correction. If omitted, MERRA-2 elevation is used."; and "The POWER data, including the elevation value, represent average values over their original source spatial resolution."

Decided since, in issue #77 (this file adds no field for them):

- D9: they travel in the "Site data: climate" contract, as "the point the series is valid for (latitude, longitude, elevation), with its provenance label and source. The signature of the water entry point does not change".
- D18: that point is "taken from what the response of the source reports (the platform developer's point in #18, unit #94). No further field".
- D27: the engine derives net radiation and "needs latitude and elevation, which travel with the series (D9, D18)".

No identifier, unit or label is proposed for them in this list: they are single values of a place, not series, and their fields belong to the model of the climate contract. Question: O9.

## Not in the list, and why

| What | Why it is not in the list | Question |
|---|---|---|
| Mean air temperature of the day | In the daily worked example it is derived, not given (#13, section 5). #15 documents a parameter for it, `T2M`: "The average air (dry bulb) temperature at 2 meters above the surface of the earth.", and leaves to a person whether the mean comes from it or from the two extremes (#15, decision 5). `DECIDED` (D30): derived by the engine, the mean from the daily maximum and minimum; not requested as a series | O10 |
| Atmospheric pressure at the surface | In the daily worked example it is derived, not given (#13, section 5). #15: "Surface Pressure" is listed in the dictionary (entry not opened by the scout, code not read). `DECIDED` (D30): derived by the engine from elevation; not requested as a series | O10 |
| Net radiation, clear-sky radiation, extraterrestrial radiation, daylight hours | Derived by the engine in the worked example (#13, section 5). "POWER data does not provide net radiation" (#15, section 2). D27: "The engine derives net radiation" | O3 |
| Reference evapotranspiration and the daily water balance | Results of the engines, not site data (`contracts/inputs/README.md`) | Q10 (b) of `contracts/ENTRYPOINTS.md` |
| Monthly precipitation, the monthly fraction of erosivity | Computed by the erosion engine from `precipitation` (M1.2; the adapter writes `monthly_series: []`). A value aggregated from an `OBSERVED` series is `DERIVED` (C4.3). Proposed here: no monthly quantity travels | Questions 10 and 11 of `contracts/inputs/README.md` |
| Mean annual level of rainfall erosivity at the field | M1.2 takes it from published national values, not from a daily climate series. Where it travels is not a matter of this list | Question 10 of `contracts/inputs/README.md` |
| Snow precipitation, probability of liquid precipitation, count of precipitation retrievals | #15 lists parameters for them (section 3). No method named in `docs/METHODS.md` or in blueprint section 8 needs them | None |
| Soil and terrain quantities | Out of scope of this unit. They belong to "Site data: soil and slope" | Questions 16 to 19 of `contracts/inputs/README.md` |

## What a person writes in the adapter settings

This file writes no settings. Once a person has answered the questions, each chosen quantity becomes one `ParameterSpec` of `PowerSettings` (`adapters/README.md`):

| Setting | Comes from |
|---|---|
| `quantity` | The identifier of this file |
| `unit` | The unit string of this file, after a person has checked it against the service (R4) |
| `provenance` | `OBSERVED` (R5) |
| `source_parameter` | The parameter the science reviewers choose. This file only repeats what #15 documents. For the `DECIDED` quantities, the parameter of the decision (D23 to D27) |

#15 quotes a limit that the list stays under whatever is chosen: "A maximum of 20 parameters can currently be requested in one submission for a single point." (#15, section 7).

The comment of issue #77 with D23 to D32 lists, under "What changes in the repository", for the platform developer: "the settings of the adapter (D20), now that the values are accepted: community `ag`; the six parameters with their identifiers, units and label; `range_missing` reason `NO_COVERAGE`; the period of D29". The comment does not list the six parameters by name; the documented request of D32 asked for seven. D35 settles it: the quantities of the settings are the seven of D23 to D27 and D35 (`precipitation`, `precipitation_reanalysis`, `air_temperature_max_2m`, `air_temperature_min_2m`, `dew_point_temperature_2m`, `wind_speed_2m`, `solar_radiation`); "six" in that comment is a miscount.

## The documented request

Decided by the lead developer on 14 November 2026, issue #77, D32.

D32 answers whether the documentation is checked against the service before the settings are written (O14, O5): "**Done**". The recorded response may be committed under D17.

- Who and when: made by the orchestrating AI session on the lead developer's instruction, on 14 November 2026 at about 18:10 UTC (D32). The time recorded with the request is in the evidence file.
- Where: a made-up point in the ocean that is no producer's field (D32), longitude `-50`, latitude `-35`.
- What: one `GET` of the daily point endpoint for the parameters `IMERG_PRECTOT`, `PRECTOTCORR`, `T2M_MAX`, `T2M_MIN`, `T2MDEW`, `WS2M`, `ALLSKY_SFC_SW_DWN`, community `ag`, from `20240101` to `20240110`, format `JSON`, time standard `utc`. Answer `200`.
- Evidence: the exact URL, the time and the raw response are in [`docs/evidence/nasa-power-2026-11-14/`](../docs/evidence/nasa-power-2026-11-14/README.md).

What it settles of the questions #15 left open, as D32 writes it:

| Point | What the response shows |
|---|---|
| Does `ag` accept `IMERG_PRECTOT` at daily level? | Yes: ten daily values returned |
| Unit of each parameter, as the response labels it | `IMERG_PRECTOT` and `PRECTOTCORR`: `mm/day`; `T2M_MAX`, `T2M_MIN`, `T2MDEW`: `C`; `WS2M`: `m/s`; `ALLSKY_SFC_SW_DWN`: `MJ/m^2/day` (the "per Hour" wording of the dictionary does not appear in the response) |
| Fill value | `"fill_value": -999.0` in the header; none of the seventy values was the fill value |
| Time standard | `"time_standard": "UTC"` in the header |
| Sources | header `sources`: `MERRA2`, `SYN1DEG`, `IMERG`, `POWER`; there is no source per value |
| Point of the series | `geometry.coordinates` `[-50.0, -35.0, 0.0]`: the elevation reported for an ocean cell is `0.0` |

Still not settled by one request (D32): which IMERG run (Late or Final) a given day comes from; whether the daily IMERG value is a depth summed over the UTC day (the unit `mm/day` is consistent with it); which underlying product supplies a given day of `PRECTOTCORR`. They stay `OPEN` in O4 and O5.

## OPEN

Each item is a question a person can answer. The role that answers it is named at the end of the item. Decision rights are those of blueprint section 2: the science reviewers decide method, source, unit and fallback; the platform developer decides technical matters; the lead developer decides what enters `main` and owns `contracts/`.

**O1. At which height does the wind speed series travel, and which height does the method need?** #13 reports that the equation of the worked example uses wind speed at 2 m and that the example converts a measurement taken at another height. #15 documents `WS2M` and `WS10M`, mentions a 50 m parameter, and quotes a custom height that must be "between 10m and 300m". If the series travels at a height other than the one the method uses: who converts, with which method and which parameters? The adapter does not convert. And if the custom height of the service is used, is the value still labelled `OBSERVED`? For the science reviewers. The conversion method: CITATION NEEDED.

**O1 DECIDED** (lead developer, 14 November 2026, issue #77, D26): **`WS2M`**, identifier `wind_speed_2m`, unit `m s-1`, at 2 m. "No height conversion in the engine." See `CQ5`.

**O2. Does humidity travel as relative humidity or as dew point?** #15 also documents specific humidity (`QV2M`). The daily worked example is given the maximum and the minimum relative humidity of the day; #15 found no daily maximum or minimum relative humidity parameter. So also: by which route of the method does the engine get the actual vapour pressure from the form that is chosen? #13 does not report a route from dew point or from specific humidity; a person reads it in the source. For the science reviewers.

**O2 DECIDED** in part (lead developer, 14 November 2026, issue #77, D25): **dew point**, `T2MDEW`, identifier `dew_point_temperature_2m`, unit `degC`. See `CQ4`.

**O2 OPEN** (what D25 leaves): by which route of the reference evapotranspiration method does the engine get what it needs from dew point? It is read in the method's text; the scout report #13 does not report it (D25). "Still to be supplied by a person" (D25); for the science reviewers, as this item said. Issue #77 (comment with D23 to D32): the reference evapotranspiration unit of the engines lane "can start once the route from dew point (D25) is confirmed in the method's text".

**O3. Which radiation quantity travels, and in which unit?** The daily worked example starts from hours of sunshine; #15 documents the all-sky shortwave irradiance at the surface (`ALLSKY_SFC_SW_DWN`), lists clear-sky and top-of-atmosphere parameters without their codes, says the service provides no net radiation, and reports nothing on sunshine duration. Is `ALLSKY_SFC_SW_DWN` the solar radiation that the method takes as measured, and are the remaining radiation terms derived by the engine? Its unit follows the community (O11). For the science reviewers.

**O3 DECIDED** (lead developer, 14 November 2026, issue #77, D27): **`ALLSKY_SFC_SW_DWN`**, identifier `solar_radiation`, unit `MJ m-2 day-1` (community AG, D28). "The engine derives net radiation; it needs latitude and elevation, which travel with the series (D9, D18)." See `CQ6`.

**O4. Where does daily precipitation come from, and does it come through the NASA POWER adapter?** Four parts. (a) Which product: `IMERG_PRECTOT`, `PRECTOTCORR` or `PRECTOT` of that service, or precipitation taken directly from its own source. Blueprint section 8 and M1.2 say IMERG precipitation; C6.2 leaves to the science reviewers whether it comes through NASA POWER or directly (`adapters/README.md`, OPEN 8). (b) If it comes through the adapter, the series is UTC (C6.2). If it comes directly, C6.4 applies: in which time zone are its days defined, and is it converted, by whom and with which method? Until that is answered the series is not combined with any other daily series (C6.4), so the water engine cannot use it together with `CQ2` to `CQ6`. (c) Is a fallback between products allowed, and how is it labelled, given that one record holds one series per quantity? (d) If it comes directly, a second adapter is a new unit. For the science reviewers; the platform developer for (d).

**O4 DECIDED** (lead developer, 14 November 2026, issue #77, D23 and D24):

- (a) D23: **`IMERG_PRECTOT`** of NASA POWER, through the platform adapter. Identifier `precipitation`, unit `mm day-1`. See `CQ1`.
- (b) It comes through the adapter, so the series is UTC (C6.2). D32: the header of the response says `"time_standard": "UTC"`.
- (c) D24: a second series, **`PRECTOTCORR` as a control series**, "travelling beside the main one with its own identifier `precipitation_reanalysis`, unit `mm day-1`, label `OBSERVED`. It is not a fallback: the main series stays `precipitation`". See `CQ1b`.
- (d) It does not come directly, so no second adapter is needed for it.

**O4 OPEN** (what D32 lists as not settled by one request): which IMERG run (Late or Final) a given day comes from; which underlying product supplies a given day of `PRECTOTCORR` (see also O12). For the science reviewers, as this item said.

**O5. Is the daily value of the chosen precipitation parameter a depth summed over the UTC day?** The unit string `mm day-1` assumes it. The documentation is inconsistent for `IMERG_PRECTOT` ("mm", "Daily sum from half-hourly" against "Millimeter per Day (mm/day)" and "The average IMERG total precipitation"), and #15 did not find what the service returns for it under each time standard (#15, section 3; decision 2). For the science reviewers, who may confirm it with one real request or with the team of the service.

**O5, what D32 settles** (lead developer, 14 November 2026, issue #77, D32): the response labels the unit of `IMERG_PRECTOT` `mm/day`, and its header says `"time_standard": "UTC"`.

**O5 OPEN** (what D32 lists as not settled by one request): whether the daily IMERG value is a depth summed over the UTC day; "the unit `mm/day` is consistent with it" (D32). For the science reviewers, as this item said.

**O6. Which reason code states "no range" on a series?** A series with at least one number must carry `range_missing` with a code of C3.2 (C2.2). Since pull request #86 the adapter writes `range_missing: {reason: range_missing_reason, detail}`, with the fixed English `detail` "the source gives no uncertainty range for this series", so each of the eight codes of C3.2 gives a document that the model loads, `MISSING_INPUT` included (`adapters/test_power_mapping.py::test_every_reason_code_gives_a_document_that_loads`). Before #86 the adapter wrote no `detail` and `MISSING_INPUT` could not be configured. The placeholder examples use `NOT_AVAILABLE`, which C3.2 defines as "The module that would produce the value is not built or not enabled". No code of the closed list says "the source gives no range for this quantity". The options were: one of the eight codes, read as covering this case, with the `detail` of the adapter saying the rest; or a new code, which is a contract change at a checkpoint (C3.2). The same question is OPEN 9 of `adapters/README.md`.

**O6 DECIDED** (lead developer, 14 November 2026, issue #77, D31): the code is **`NO_COVERAGE`**, with the fixed `detail` the adapter already writes. **D31 replaces D15**, which this item recorded before (#97) with the code `NOT_AVAILABLE`: the lead developer chose `NO_COVERAGE` so that `NOT_AVAILABLE` keeps one meaning, the module not built (C3.2, D12). Rule R7 states the same code.

**O7. Which years of record does a case request?** Until it is answered no period is configured and the climate source is not called (`api/README.md`). What #15 documents: the first allowed date of a request, `start` "Must be >= 19810101."; the solar sources begin later (the first of them, SRB, is given the start "January 1, 1984"); the first date of IMERG is given inconsistently (`CQ1`); recent days are later replaced ("it is recommended to end the analysis 2 months behind NRT when assessing climate trends"; for IMERG "end the analysis 3.5 months behind NRT when assessing trends"). So also: is the period the same for every quantity, and what happens to the agricultural years that one quantity covers and another does not (C5.5)? For the science reviewers and the lead developer.

**O7 DECIDED** (lead developer, 14 November 2026, issue #77, D29): **from 2001-01-01 to 2024-12-31.** D29 answers the years of record that the comment of 18:02 UTC of issue #77 left for the science reviewers (`adapters/README.md`, OPEN 5).

**O7 OPEN** (what D29 leaves):

- How a field polygon becomes one point. "How a field polygon becomes one point stays with them" (D29), the science reviewers (`adapters/README.md`, OPEN 10).
- D29 gives one period for a case and names no quantity. As this item asked, and not answered by D29: is the period the same for every quantity, and what happens to the agricultural years that one quantity covers and another does not (C5.5)? For the science reviewers and the lead developer.

**O8. Which method does the water engine implement, and does it need a quantity that is not in this list?** `docs/METHODS.md` names neither the method of the reference evapotranspiration nor the method of the daily water balance. `CQ2` to `CQ6` follow the inputs of the daily worked example as #13 lists them. Is that example the one of [H2], and is its method the method of `engine/water/et0/`? Does the water balance read anything besides `precipitation` and what the reference evapotranspiration reads? For the lead developer, who names the methods in `docs/METHODS.md`; the science reviewers, who accept them and define [H2].

**O9. How do latitude and elevation reach an engine?** Three parts. (a) The worked example needs both and no contract carries them: are they fields of a contract (which one) or further arguments of EP3? This is Q10 (a) of `contracts/ENTRYPOINTS.md` and question 21 of `contracts/inputs/README.md`. (b) Which elevation: the one of the field, declared by the user or taken from the terrain data, or the one the climate source answers with, which #15 says is an average over the grid cell of the source? (c) Is `site-elevation` sent to the service (`adapters/README.md`, OPEN 4)? For the science reviewers, for (b) and (c); the platform developer and the lead developer, for (a). Decided since, in issue #77: D9, D18 and D27 ([Latitude and elevation](#latitude-and-elevation)). This item is kept as it was asked; which of its parts those decisions answer is not transcribed by this unit.

**O10. Are the mean air temperature and the atmospheric pressure delivered as series, or derived by the engine?** In the daily worked example both are derived (#13, section 5). #15 documents `T2M` and lists "Surface Pressure" without its code (#15, decision 5). If either is delivered it enters this list with an identifier, a unit string and a height. For the science reviewers.

**O10 DECIDED** (lead developer, 14 November 2026, issue #77, D30): **derived by the engine** (mean from the daily maximum and minimum; pressure from elevation), not requested as series. Neither enters this list.

**O11. Which community?** It fixes the unit of `ALLSKY_SFC_SW_DWN` and which parameters are offered (#15, section 1; decision 4). For the temperature, humidity, wind and precipitation entries the scout opened, "the Daily metric unit was the same in every community listed". This is OPEN 2 of `adapters/README.md`; it is repeated here because the unit string of `CQ6` cannot be written without it. For the science reviewers.

**O11 DECIDED** (lead developer, 14 November 2026, issue #77, D28): **`ag`** (Agroclimatology). With it, the unit string of `CQ6` is `MJ m-2 day-1` (D27).

**O12. Which underlying product is acceptable for each quantity and period, and what does `source` name?** #15 lists several products per parameter and did not find which one supplies a given date, nor a per-day source field in the response (#15, section 5; decision 6). May a series cross a change of product? C4.4 asks for the product to be named as the source: what is written when one series holds more than one product? For the science reviewers; the lead developer for the format of `source` (`contracts/inputs/README.md`, question 22). What D32 shows, without answering it: header `sources`: `MERRA2`, `SYN1DEG`, `IMERG`, `POWER`; "there is no source per value".

**O13. Do the height suffix and the new unit symbols stand?** R2 to R4 put the height in the identifier and add unit symbols that C1.1 does not list, among them `%` for a quantity that could also be written as a fraction. Accept, or correct: a height field in the model, other symbols, an addition to C1.1. For the lead developer, who owns `contracts/`, and the platform developer, whose adapter writes both.

**O14. Should the documentation be checked against the service before the settings are written?** #15 reports several points as `NOT FOUND` or inconsistent and says they could be settled "by a person making one documented request or by reading the `/configuration` and Manager API outputs, which this scout did not call" (#15, decision 10). The points that touch this list: which parameters the chosen community accepts at daily level; the unit and aggregation of `IMERG_PRECTOT`; the unit label of `ALLSKY_SFC_SW_DWN` under AG and HY; the codes of the radiation and pressure parameters whose entries were not opened. A session never calls the real service. For the science reviewers and the platform developer.

**O14 DECIDED** (lead developer, 14 November 2026, issue #77, D32): **Done.** One documented request was made by the orchestrating AI session on the lead developer's instruction; the recorded response may be committed under D17. What it settles and what it does not: [The documented request](#the-documented-request). Of the points listed in this item: the community `ag` accepts `IMERG_PRECTOT` at daily level; the unit label of `IMERG_PRECTOT` is `mm/day` and its aggregation stays `OPEN` (O5); the unit label of `ALLSKY_SFC_SW_DWN` under `ag` is `MJ/m^2/day`. The request asked for no clear-sky, top-of-atmosphere or pressure parameter, so their codes are not read.

### Questions of other files that this list depends on

They are not repeated here. Each one has to be answered before a real series is written.

| Question | Where | For |
|---|---|---|
| Which parameters are requested, with which identifier, unit string and label each | `adapters/README.md`, OPEN 1; `contracts/inputs/README.md`, question 9 | Science reviewers; identifiers with the lead developer and the platform developer |
| Whether the unit of each source parameter, in the chosen community, equals the configured unit string | `adapters/README.md`, OPEN 3 | Science reviewers |
| Which optional arguments are sent (`units`, `site-elevation`, `wind-elevation`, `wind-surface`) | `adapters/README.md`, OPEN 4 | Science reviewers |
| Which fill value, and which reason code a fill value or an absent day becomes | `adapters/README.md`, OPEN 6 | Science reviewers |
| How the service bounds a UTC day for each variable. CITATION NEEDED (C6.2) | `adapters/README.md`, OPEN 7 | Science reviewers |
| How a field polygon becomes one point (O7) | `adapters/README.md`, OPEN 10 | Science reviewers (D29 of issue #77: it "stays with them"); before D29 this row named the lead developer and the science reviewers |
| The time zone of a daily series from a source other than the NASA POWER adapter | C6.4; `contracts/inputs/README.md`, question 12 | Science reviewers |
| The gap-filling method, and how a filled day is labelled | C3.4; `contracts/inputs/README.md`, question 13 | Science reviewers and the lead developer |
| Whether a daily value ever carries an uncertainty range | `contracts/inputs/README.md`, question 14 | Science reviewers |
| Which reason code an engine uses for an input in a unit it does not accept | `contracts/ENTRYPOINTS.md`, Q11 | Lead developer |

## Not covered by this file

- The adapter, its settings and any settings file.
- The method of the water balance and of the reference evapotranspiration, and any equation, coefficient or parameter of either.
- Soil and terrain quantities.
- Any engine.
- The entry for the data in `ATTRIBUTIONS.md`: a person writes it when the data is first used for real (`adapters/README.md`, OPEN 16). The row for the response committed as evidence under D17 and D32 is already there.
