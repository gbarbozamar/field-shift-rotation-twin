"""Kind of each agricultural year from the Oceanic Nino Index record. PROPOSED.

Pure functions. The threshold and the minimum run of consecutive overlapping
seasons are read from the record (transcribed from the quoted definition text),
never written here.

D240 (2) of issue #77: the threshold is applied to the one-decimal values
printed in the v6 table, as CPC applies it, and not to the two-decimal values
of ``oni.ascii.txt``. D258: those printed values come from the record itself.
Each season of the record carries ``printed``, the value as the v6 table
prints it, next to ``anom``, the two-decimal value of the file, and the
threshold is compared with ``printed`` as given. This module holds no
rounding rule: no fixed rule on the file values reproduces what CPC prints.
A season whose ``printed`` value is missing is a missing input, never a value
rounded here and never zero.
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
# C3.2: "MISSING_INPUT | The value is computed from an input that is itself
# missing; `detail` names that input": here, the printed value of a season (D258).
_MISSING_INPUT: ReasonCode = "MISSING_INPUT"


@dataclass(frozen=True)
class KindOfYear:
    """The kind of one agricultural year, or missing with its reason."""

    kind: str | None
    missing_reason: ReasonCode | None
    detail: str | None
    season: str | None
    season_year: int | None

    def __post_init__(self) -> None:
        # PROPOSED (S-027 F5), as MarginResult: a kind or a reason, never both
        # or neither.
        if (self.kind is None) == (self.missing_reason is None):
            raise ValueError(
                "a kind of year holds a kind or a missing_reason, never both or neither"
            )
        # PROPOSED (S-027 R2): a present kind is one of KINDS_OF_YEAR and, as
        # classify_agricultural_years builds it, carries no missing detail.
        if self.kind is not None and self.kind not in KINDS_OF_YEAR:
            raise ValueError(f"a kind of year is one of KINDS_OF_YEAR {KINDS_OF_YEAR}")
        if self.kind is not None and self.detail is not None:
            raise ValueError("a present kind of year carries no missing detail")


def _is_int(value: object) -> bool:
    """An int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_real(value: object) -> bool:
    """A finite int or float that is not a bool."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _check_years(first_year: int, last_year: int) -> None:
    # PROPOSED (S-027 F3): checked like start_month; a bool or a float is not
    # a year.
    for name, value in (("first_year", first_year), ("last_year", last_year)):
        if not _is_int(value):
            raise ValueError(f"{name} must be an integer")


def _check_month(start_month: int) -> None:
    if not _is_int(start_month) or not 1 <= start_month <= 12:
        raise ValueError("start_month must be an integer from 1 to 12")


def _check_rule(record: Mapping[str, Any]) -> tuple[float, int]:
    """The threshold and run length of the record, checked."""
    threshold = record.get("threshold")
    if not _is_finite_real(threshold) or threshold <= 0:
        raise ValueError("record field 'threshold' must be a finite number > 0")
    run_length = record.get("min_consecutive_seasons")
    if not _is_int(run_length) or run_length < 1:
        raise ValueError(
            "record field 'min_consecutive_seasons' must be an integer >= 1"
        )
    return float(threshold), run_length


def _season_map(record: Mapping[str, Any]) -> dict[int, float | None]:
    """Season ordinal -> the printed value (D258), every row checked (PROPOSED, S-027 F2).

    The value of a season is its ``printed`` field, the value as the v6 table
    prints it, taken as given. A row without ``printed``, or with ``printed``
    null, maps to ``None``: its printed value is missing (D258), and it is
    never rounded from ``anom`` or read as zero.

    A ValueError naming the row index and the field when the record has no
    ``seasons`` list, a row is not a mapping or lacks ``season``, ``year`` or
    ``anom``, the season is unknown, the year is not an int (a bool is
    refused), the anom, or a printed value that is given, is not a finite
    real number (a bool, NaN or an infinity is refused; None for the anom
    too), or a (season, year) row is duplicated.
    """
    rows = record.get("seasons")
    if not isinstance(rows, list):
        # ValueError, not TypeError: one exception type for every structural
        # misuse of the record (README.md).
        raise ValueError("record field 'seasons' must be a list of rows")  # noqa: TRY004
    values: dict[int, float | None] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"seasons row {index}: a row is a mapping")  # noqa: TRY004
        for field in ("season", "year", "anom"):
            if field not in row:
                raise ValueError(f"seasons row {index}: field {field!r} is missing")
        season, year, anom = row["season"], row["year"], row["anom"]
        if not isinstance(season, str) or season not in SEASONS:
            raise ValueError(
                f"seasons row {index}: unknown season name {season!r} in field 'season'"
            )
        if not _is_int(year):
            raise ValueError(f"seasons row {index}: field 'year' must be an integer")
        if not _is_finite_real(anom):
            raise ValueError(
                f"seasons row {index}: field 'anom' must be a finite real number"
            )
        printed = row.get("printed")
        if printed is not None and not _is_finite_real(printed):
            raise ValueError(
                f"seasons row {index}: field 'printed' must be a finite real number, "
                "or absent when the printed value is missing"
            )
        position = _ordinal(season, year)
        if position in values:
            raise ValueError(f"seasons row {index}: duplicated season {season} {year}")
        values[position] = None if printed is None else float(printed)
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
    values: Mapping[int, float | None],
    position: int,
    threshold: float,
    run_length: int,
) -> str | None:
    """el_nino, la_nina or neutral for the season at ``position``.

    ``values`` are the printed values of the record (D258), so the threshold
    is met on the values the v6 table prints (D240). None when a season
    needed to judge it is not in the record or has no printed value.
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
    whose printed value, as the v6 table prints it and the record carries it
    (D240, D258), meets ``+threshold`` (``-threshold``); "met" is read as at
    or beyond the threshold (PROPOSED). The kind of the year is the episode
    state of its deciding season. A year that cannot be judged is missing:
    ``MISSING_INPUT`` when a season it needs has no printed value (D258),
    naming the seasons, else ``NO_COVERAGE`` (outside the record, or a gap).
    """
    _check_years(first_year, last_year)
    if first_year > last_year:
        raise ValueError("first_year must not be after last_year")
    _check_month(start_month)
    threshold, run_length = _check_rule(record)
    values = _season_map(record)

    result: dict[int, KindOfYear] = {}
    for ag_year in range(first_year, last_year + 1):
        season, season_year = deciding_season(ag_year, start_month)
        position = _ordinal(season, season_year)
        reason: ReasonCode | None = None
        detail = None
        if position not in values:
            kind, reason = None, _NO_COVERAGE
            detail = f"season {season} {season_year} is not in the record"
        else:
            kind = _episode_state(values, position, threshold, run_length)
        if kind is None and reason is None:
            unprinted = _unprinted(values, position, run_length)
            if unprinted:
                reason = _MISSING_INPUT
                detail = (
                    f"the printed value of the v6 table (D258) is missing for "
                    f"{', '.join(unprinted)}, needed to judge season {season} "
                    f"{season_year}; it is not rounded from the file value"
                )
            else:
                reason = _NO_COVERAGE
                detail = (
                    f"a season needed to judge the run of season {season} "
                    f"{season_year} is not in the record (outside its span or a "
                    "gap in it)"
                )
        result[ag_year] = KindOfYear(
            kind=kind,
            missing_reason=reason,
            detail=detail,
            season=season,
            season_year=season_year,
        )
    return result


def _unprinted(
    values: Mapping[int, float | None], position: int, run_length: int
) -> list[str]:
    """The seasons in the record, near ``position``, whose printed value is missing.

    Near: every season a run through ``position`` can hold, from
    ``run_length - 1`` seasons before it to ``run_length - 1`` after it.
    """
    found = []
    for near in range(position - run_length + 1, position + run_length):
        if near in values and values[near] is None:
            year, index = divmod(near, len(SEASONS))
            found.append(f"{SEASONS[index]} {year}")
    return found


def count_kinds(classified: Mapping[int, KindOfYear]) -> dict[str, int | None]:
    """Number of years of each kind; every count None when any year is missing."""
    if any(item.kind is None for item in classified.values()):
        return {kind: None for kind in KINDS_OF_YEAR}
    return {
        kind: sum(1 for item in classified.values() if item.kind == kind)
        for kind in KINDS_OF_YEAR
    }
