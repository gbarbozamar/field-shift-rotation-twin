# kinds_of_year

PROPOSED (unit `l2/kinds-of-year`, brief S-012; brought to `main` by brief #386 under [D240](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893552817)). Classifies each agricultural year of a period as one of the kinds of year of `contracts.economic_facts.KINDS_OF_YEAR` (`el_nino`, `neutral`, `la_nina`) from the Oceanic Nino Index (ONI), or leaves it missing with its reason (`NO_COVERAGE`, C3.2: "The data source has no data for this place or this period"; `MISSING_INPUT` for a season with no printed value, D258). Pure functions; no network. Not wired into the service or the margin engine yet.

**The ONI record is not in the repository.** It waits until a person checks it against the v6 table and signs it (D240 (5), D34, D66). The code reads a record only from the path a caller gives to `load_record(path)`; there is no default record, and nothing is read or loaded at import. The tests use hand-made records labelled example data, with no ONI value.

| File | What it holds |
|---|---|
| `classify.py` | `classify_agricultural_years`, `count_kinds`, `deciding_season`, `KindOfYear`, `SEASONS` |
| `aggregate.py` | `mean_by_kind`, `series_from_results`, `YearValue`, `KindMean`, `MeansByKind` (see below) |
| `__init__.py` | Exports the above and `load_record(path)`, which reads the record a caller names |
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

A record carries its `threshold` and `min_consecutive_seasons`, taken from this text (D240 (1)). The code holds no threshold or run length: it reads them from the record it is given. The checks of a record's own content (its members, its seasons, the rule read back from its quoted text) come with the signed record; the hand-made records of the tests carry the rule of D240 only so that the cases can be built.

## How a year is classified (PROPOSED)

- A season is in an El Nino (La Nina) episode when it belongs to a run of at least `min_consecutive_seasons` consecutive overlapping seasons whose value is at or above `+threshold` (at or below `-threshold`). "Met" is read as at or beyond the threshold.
- **D240 (2): the threshold is applied to the one-decimal values printed in the v6 table, as CPC applies it, and not to the two-decimal ANOM of `oni.ascii.txt`.**
- **[D258](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6895728653): those printed values come from the record, not from a rounding rule.** Each season of the record carries `printed`, the value as the v6 table prints it (one decimal), next to `anom`, the two-decimal value of `oni.ascii.txt`. The threshold reads `printed` as given; the code holds no rounding rule. No fixed rule on the file values reproduces the table: the verifier of #422 found that half away from zero disagrees with it on 50 of the 89 file values that end in 5 (1950-2025), and that half up disagrees too (D258).
- A season whose `printed` value is missing (the field left out, or null) is a missing input: a year that needs it is missing `MISSING_INPUT`, the detail naming the season. It is never rounded from `anom`, never neutral and never zero.
- D240 names five seasons of 2000-2025 where the two readings part (JJA 2000, MJJ 2002, JJA 2007, JAS 2021, AMJ 2023), changing the kind of a year for start months 1, 2, 11 and 12. The test reads each of them on hand-made pairs of file and printed values, with the sign the table prints for its episode; none is an ONI value.
- Agricultural year Y begins at the declared start month of calendar year Y (C5.3). The season that decides it is the three-month season centred on the month six months after the start month (D240 (3), R6 of #310, a modelling choice: CITATION NEEDED; for start month 7 that is DJF of Y+1). Its episode state is the kind of the year: `el_nino`, `la_nina`, else `neutral`. The season used is in the result.
- A year whose deciding season, or a season needed to judge its run, is not in the record is missing `NO_COVERAGE` with a detail (C3.2, C5.5); one that needs a season without a printed value is missing `MISSING_INPUT` (D258). Nothing is guessed.
- The record is checked when classifying: `threshold` a finite number > 0, `min_consecutive_seasons` an integer >= 1, `seasons` a list, every row a mapping with `season` (one of `SEASONS`), `year` (an int, not a bool), `anom` (a finite real number, not a bool or `None`) and, when given, `printed` (a finite real number, not a bool or a text; left out or null when missing), no duplicated (season, year) row; otherwise `ValueError` naming the field, or the row index and the field. `start_month` must be an integer 1..12, and `first_year` and `last_year` integers (a bool or a float is refused), with `first_year` not after `last_year`.
- `KindOfYear` holds exactly one of `kind` and `missing_reason`; a present `kind` is one of `KINDS_OF_YEAR` and carries no `detail`. Building one otherwise is a `ValueError` (PROPOSED, S-027).
- `count_kinds` gives the number of years of each kind, or `None` for every kind when any year is missing.

## Signature

The record transcribed on branch `l2/main-nico` carries `checked_by` `UNSIGNED_AI_PRECHECK`: a session transcribed and cross-checked the values, and no person has compared them with the source yet (D240 (5)). It does not carry `printed` yet. It is not brought to `main` until a person adds the printed values and signs it (D34, D66). **The person who signs it checks every printed value against the v6 table** (D258; the check sheet lists them), as well as the file values against `oni.ascii.txt`.

## Means by kind of year (PROPOSED, unit `l2/by-kind-of-year`, brief S-013)

`aggregate.py` turns a per-agricultural-year series of one indicator (soil loss in `t ha-1 yr-1`, or water-deficit exposure, dimensionless, on the time basis `ag_year`) into the mean of each kind of year and the mean of the whole record. Aggregation only, no new science. The types are new and PROPOSED; the results contract is not edited.

- `YearValue(value, reason, detail, source=None, assumption=False)`: one year, a finite number (not a bool) or a reason code of C3.2, exactly one of the two. `detail` belongs to a missing value only; `source` and `assumption` (C4.2) to a present value only. Otherwise `ValueError`.
- `KindMean(value, unit, n_years, ag_years, reason, detail, sources=(), assumption=False)`: one mean or missing with its reason. `n_years` and `ag_years` (sorted, unique ints) name only the years whose values entered it, also when it is missing; zero is never a stand-in, and a present mean needs at least one year. `sources` are the sorted unique sources of those years; `assumption` is true when any of them carries the assumption mark. A `KindMean` carries no range (OPEN below).
- `MeansByKind(indicator, unit, by_kind, record, unclassified_years)`: `by_kind` holds every kind of `KINDS_OF_YEAR` in that order, each a `KindMean` in `unit`, as is `record`; `unclassified_years` is a sorted tuple of unique int years. `by_kind` is stored as a plain dict copy, so `dataclasses.asdict` and `copy.deepcopy` work.
- `mean_by_kind(indicator, unit, series, kinds)`: the arithmetic mean of the values of the years of each kind, no weighting, and of all years of the series (`record`).
  - A kind with no year of the series: missing `NO_COVERAGE`, `n_years` 0, detail "no agricultural year of the record is <kind>". When some years are unclassified, the kind is unknown rather than absent, and the detail is "no agricultural year of the record is classified <kind>; agricultural year(s) <list> have no kind of year".
  - A group with a year whose value is missing: missing `MISSING_INPUT`, the detail names each such year with the reason and the detail it carries, for example `2003 (MISSING_INPUT: precipitation of June missing)`. The same for the record.
  - A year whose `KindOfYear` is missing, or that is not in `kinds`, enters the record mean, enters no kind mean and is listed in `unclassified_years`. The kind means are still given, because their years are known: **the consumer decides** whether a kind mean is usable while some years are unclassified.
  - A year of `kinds` absent from the series is ignored. An empty series, a non-integer year (in the series or in `kinds`; a bool is not a year), an entry that is not a `YearValue` or `KindOfYear`, or a blank indicator or unit is a `ValueError`. Inputs are not mutated.
- `series_from_results(items)`: a series from `AnnualSoilLoss` or `WaterDeficitExposure` items of `contracts.results`, the value with its `source` and `assumption` mark, or the reason and detail of `missing`, copied unchanged. A water-deficit exposure on the time basis `rotation`, another item type (for example `MonthlySoilLoss`), mixed indicators or units, a repeated agricultural year or an empty sequence is a `ValueError`.
- Test: `kinds_of_year/test_aggregate.py`, invented series, expected means written as arithmetic.

## OPEN

- Range of a mean by kind of year: not computed, CITATION NEEDED for the rule. Combining the uncertainty ranges of the years is a science choice, so `KindMean` carries no range.

- Which index to use (D240 (4), OPEN): the moved page says that per NWS Public Information Statement 26-05 the Relative Oceanic Niño Index (RONI) is used for official monitoring and prediction. This unit uses the ONI, as D240 (1) decides; switching to RONI is for a person.
- Which season, or which rule over the year, should decide an agricultural year (D240 (3): the centred season, a modelling choice, CITATION NEEDED).
- The record itself: not in the repository until a person checks and signs it (D240 (5), D34, D66). D240 also names the NWS disclaimer that the page links as its terms of use; `ATTRIBUTIONS.md` is not edited by this unit.
