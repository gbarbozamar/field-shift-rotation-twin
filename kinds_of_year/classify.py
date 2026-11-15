"""Kind of each agricultural year from the Oceanic Nino Index record. PROPOSED.

Pure functions. The threshold and the minimum run of consecutive overlapping
seasons are read from the record (transcribed from the quoted definition text),
never written here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import ReasonCode

EL_NINO, NEUTRAL, LA_NINA = KINDS_OF_YEAR

# The twelve overlapping three-month seasons of the data file, in file order.
# Season index i is centred on calendar month i + 1 (C5.1: January = 1) and is
# labelled with the calendar year of that centre month (DJF 2000 is
# December 1999 to February 2000).
SEASONS: tuple[str, ...] = (
    "DJF",
    "JFM",
    "FMA",
    "MAM",
    "AMJ",
    "MJJ",
    "JJA",
    "JAS",
    "ASO",
    "SON",
    "OND",
    "NDJ",
)

# C3.2: "NO_COVERAGE | The data source has no data for this place or this
# period" (and C5.5 for a year the series does not cover).
_NO_COVERAGE: ReasonCode = "NO_COVERAGE"


@dataclass(frozen=True)
class KindOfYear:
    """The kind of one agricultural year, or missing with its reason."""

    kind: str | None
    missing_reason: ReasonCode | None
    detail: str | None
    season: str | None
    season_year: int | None


def _check_month(start_month: int) -> None:
    if (
        isinstance(start_month, bool)
        or not isinstance(start_month, int)
        or not 1 <= start_month <= 12
    ):
        raise ValueError("start_month must be an integer from 1 to 12")


def _check_rule(record: Mapping[str, Any]) -> tuple[float, int]:
    """The threshold and run length of the record, checked."""
    threshold = record.get("threshold")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or threshold <= 0
    ):
        raise ValueError("record field 'threshold' must be a finite number > 0")
    run_length = record.get("min_consecutive_seasons")
    if (
        isinstance(run_length, bool)
        or not isinstance(run_length, int)
        or run_length < 1
    ):
        raise ValueError(
            "record field 'min_consecutive_seasons' must be an integer >= 1"
        )
    return float(threshold), run_length


def _season_map(record: Mapping[str, Any]) -> dict[int, float]:
    """Season ordinal -> ANOM; a duplicated or unknown season is a ValueError."""
    values: dict[int, float] = {}
    for index, row in enumerate(record["seasons"]):
        season, year = row["season"], row["year"]
        if season not in SEASONS:
            raise ValueError(f"seasons row {index}: unknown season name {season!r}")
        position = _ordinal(season, year)
        if position in values:
            raise ValueError(f"seasons row {index}: duplicated season {season} {year}")
        values[position] = float(row["anom"])
    return values


def deciding_season(ag_year: int, start_month: int) -> tuple[str, int]:
    """The season that decides agricultural year ``ag_year``. PROPOSED (R6).

    The three-month season centred on the month six months after
    ``start_month``; agricultural year Y begins at ``start_month`` of calendar
    year Y (C5.3).
    """
    _check_month(start_month)
    month = start_month + 6
    year = ag_year
    if month > 12:
        month -= 12
        year += 1
    return SEASONS[month - 1], year


def _ordinal(season: str, year: int) -> int:
    return year * 12 + SEASONS.index(season)


def _episode_state(
    values: Mapping[int, float], position: int, threshold: float, run_length: int
) -> str | None:
    """el_nino, la_nina or neutral for the season at ``position``.

    None when the seasons needed to judge it are not in the record.
    """
    anom = values.get(position)
    if anom is None:
        return None
    if anom >= threshold:
        kind, meets = EL_NINO, lambda v: v >= threshold
    elif anom <= -threshold:
        kind, meets = LA_NINA, lambda v: v <= -threshold
    else:
        return NEUTRAL
    undecided = False
    for start in range(position - run_length + 1, position + 1):
        window = [values.get(p) for p in range(start, start + run_length)]
        if all(v is not None and meets(v) for v in window):
            return kind
        if any(v is None for v in window) and not any(
            v is not None and not meets(v) for v in window
        ):
            undecided = True
    return None if undecided else NEUTRAL


def classify_agricultural_years(
    record: Mapping[str, Any], first_year: int, last_year: int, start_month: int
) -> dict[int, KindOfYear]:
    """Classify each agricultural year ``first_year``..``last_year``.

    A season is in an El Nino (La Nina) episode when it belongs to a run of at
    least ``record["min_consecutive_seasons"]`` consecutive overlapping seasons
    whose anomaly meets ``+threshold`` (``-threshold``); "met" is read as at or
    beyond the threshold (PROPOSED). The kind of the year is the episode state
    of its deciding season; a year that cannot be judged from the record is
    missing ``NO_COVERAGE``.
    """
    if first_year > last_year:
        raise ValueError("first_year must not be after last_year")
    _check_month(start_month)
    threshold, run_length = _check_rule(record)
    values = _season_map(record)

    result: dict[int, KindOfYear] = {}
    for ag_year in range(first_year, last_year + 1):
        season, season_year = deciding_season(ag_year, start_month)
        position = _ordinal(season, season_year)
        if position not in values:
            detail = f"season {season} {season_year} is not in the record"
            kind = None
        else:
            kind = _episode_state(values, position, threshold, run_length)
            detail = (
                None
                if kind is not None
                else f"the run of season {season} {season_year} reaches past the record"
            )
        result[ag_year] = KindOfYear(
            kind=kind,
            missing_reason=None if kind is not None else _NO_COVERAGE,
            detail=detail,
            season=season,
            season_year=season_year,
        )
    return result


def count_kinds(classified: Mapping[int, KindOfYear]) -> dict[str, int | None]:
    """Number of years of each kind; every count None when any year is missing."""
    if any(item.kind is None for item in classified.values()):
        return {kind: None for kind in KINDS_OF_YEAR}
    return {
        kind: sum(1 for item in classified.values() if item.kind == kind)
        for kind in KINDS_OF_YEAR
    }
