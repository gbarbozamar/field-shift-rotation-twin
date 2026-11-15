# kinds_of_year

PROPOSED (unit `l2/kinds-of-year`, brief S-012). Classifies each agricultural year of a period as one of the kinds of year of `contracts.economic_facts.KINDS_OF_YEAR` (`el_nino`, `neutral`, `la_nina`) from the Oceanic Nino Index (ONI), or leaves it missing with its reason (`NO_COVERAGE`, C3.2: "The data source has no data for this place or this period"). Pure functions; no network. Not wired into the service or the margin engine yet.

| File | What it holds |
|---|---|
| `records/oni_v6.json` | The transcribed record: reference, both URLs, locator, date read, the verbatim definition text, the threshold and run length taken from it, and the ANOM column of `oni.ascii.txt` for DJF 2000 to NDJ 2025 |
| `classify.py` | `classify_agricultural_years`, `count_kinds`, `deciding_season`, `KindOfYear`, `SEASONS` |
| `aggregate.py` | `mean_by_kind`, `series_from_results`, `YearValue`, `KindMean`, `MeansByKind` (see below) |
| `__init__.py` | Exports the above and `load_record(path=None)` |
| `test_kinds_of_year.py` | Acceptance test: `uv run pytest kinds_of_year/` |
| `test_aggregate.py` | Acceptance test of the means by kind of year |

## Source

NOAA Climate Prediction Center, Oceanic Nino Index based on ERSST version 6:

- Table page and definition: https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/
- Values: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt (column `ANOM`)
- Read on 2026-11-15. The page says: "ONI values may change up to two months after the initial "real time" value is posted."

The brief named ONI version 5 at `https://origin.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php`. On 2026-11-15 that host did not resolve; the same path on `www.cpc.ncep.noaa.gov` says the page has moved to the ERSST version 6 table, and the values of `oni.ascii.txt` match the version 6 table, not the version 5 one. The record is therefore labelled version 6 (PROPOSED, reported).

## The rule, quoted verbatim from the table page

> Warm (red) and cold (blue) periods based on a threshold of +/- 0.5oC for the Oceanic Niño Index (ONI) [3 month running mean of ERSST.v6 SST anomalies in the Niño 3.4 region (5oN-5oS, 120o-170oW)], based on centered 30-year base periods updated every 5 years. For historical purposes, periods of below and above normal SSTs are colored in blue and red when the threshold is met for a minimum of 5 consecutive overlapping seasons.

The record's `threshold` and `min_consecutive_seasons` are taken from this text, and the test reads them back out of the text so they cannot drift. The code holds no threshold or run length.

## How a year is classified (PROPOSED)

- A season is in an El Nino (La Nina) episode when it belongs to a run of at least `min_consecutive_seasons` consecutive overlapping seasons whose ANOM is at or above `+threshold` (at or below `-threshold`). "Met" is read as at or beyond the threshold, on the two-decimal ANOM of the data file.
- Agricultural year Y begins at the declared start month of calendar year Y (C5.3). The season that decides it is the three-month season centred on the month six months after the start month (R6 of the loop decisions; for start month 7 that is DJF of Y+1). Its episode state is the kind of the year: `el_nino`, `la_nina`, else `neutral`. The season used is in the result.
- A year whose deciding season, or a season needed to judge its run, is not in the record is missing `NO_COVERAGE` with a detail (C3.2, C5.5). Nothing is guessed.
- The record is checked when classifying: `threshold` a finite number > 0, `min_consecutive_seasons` an integer >= 1, `seasons` a list, every row a mapping with `season` (one of `SEASONS`), `year` (an int, not a bool) and `anom` (a finite real number, not a bool or `None`), no duplicated (season, year) row; otherwise `ValueError` naming the field, or the row index and the field. `start_month` must be an integer 1..12, and `first_year` and `last_year` integers (a bool or a float is refused), with `first_year` not after `last_year`.
- `KindOfYear` holds exactly one of `kind` and `missing_reason`; a present `kind` is one of `KINDS_OF_YEAR` and carries no `detail`. Building one otherwise is a `ValueError` (PROPOSED, S-027).
- `count_kinds` gives the number of years of each kind, or `None` for every kind when any year is missing.

## Signature

`checked_by` is `UNSIGNED_AI_PRECHECK`: a session transcribed and cross-checked the values, no person has compared them with the source yet. It stays until a person does.

## Means by kind of year (PROPOSED, unit `l2/by-kind-of-year`, brief S-013)

`aggregate.py` turns a per-agricultural-year series of one indicator (soil loss in `t ha-1 yr-1`, or water-deficit exposure, dimensionless, on the time basis `ag_year`) into the mean of each kind of year and the mean of the whole record. Aggregation only, no new science. The types are new and PROPOSED; the results contract is not edited.

- `YearValue(value, reason, detail)`: one year, a finite number (not a bool) or a reason code of C3.2, exactly one of the two.
- `KindMean(value, unit, n_years, ag_years, reason, detail)`: one mean or missing with its reason. `n_years` and `ag_years` (sorted) name only the years whose values entered it, also when it is missing; zero is never a stand-in.
- `MeansByKind(indicator, unit, by_kind, record, unclassified_years)`: `by_kind` holds every kind of `KINDS_OF_YEAR` in that order, read-only.
- `mean_by_kind(indicator, unit, series, kinds)`: the arithmetic mean of the values of the years of each kind, no weighting, and of all years of the series (`record`).
  - A kind with no year of the series: missing `NO_COVERAGE`, detail "no agricultural year of the record is <kind>", `n_years` 0.
  - A group with a year whose value is missing: missing `MISSING_INPUT`, the detail names each such year and the reason it carries. The same for the record.
  - A year whose `KindOfYear` is missing, or that is not in `kinds`, enters the record mean, enters no kind mean and is listed in `unclassified_years`. The kind means are still given, because their years are known: **the consumer decides** whether a kind mean is usable while some years are unclassified.
  - A year of `kinds` absent from the series is ignored. An empty series, a non-integer year, an entry that is not a `YearValue` or `KindOfYear`, or a blank indicator or unit is a `ValueError`. Inputs are not mutated.
- `series_from_results(items)`: a series from `AnnualSoilLoss` or `WaterDeficitExposure` items of `contracts.results`, the value, or the reason and detail of `missing`, copied unchanged. A water-deficit exposure on the time basis `rotation`, another item type (for example `MonthlySoilLoss`), mixed indicators or units, a repeated agricultural year or an empty sequence is a `ValueError`.
- Test: `kinds_of_year/test_aggregate.py`, invented series, expected means written as arithmetic.

## OPEN

- Which index to use: the moved page says that per NWS Public Information Statement 26-05 the Relative Oceanic Niño Index (RONI) is used for official monitoring and prediction. This unit uses the ONI as the brief asked; whether to switch to RONI is for a person.
- Whether CPC applies the threshold to the one-decimal table values or the two-decimal file values (a few seasons differ, for example ANOM 0.45 is 0.5 in the table).
- Which season, or which rule over the year, should decide an agricultural year (the centred season is a PROPOSED choice, easiest to undo).
- The terms of use of the source: none found on the page.
