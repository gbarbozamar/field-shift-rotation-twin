"""Kind of each agricultural year from the Oceanic Nino Index record. PROPOSED.

Pure functions. The threshold and the minimum run of consecutive overlapping
seasons are read from the record (transcribed from the quoted definition text),
never written here.

D240 (2) of issue #77: the threshold is applied to the one-decimal values
printed in the v6 table, as CPC applies it, and not to the two-decimal values
of ``oni.ascii.txt``. So each anomaly of the record is first written as the
table prints it, with ``TABLE_DECIMALS`` decimals (``table_value``), and the
threshold is compared with that value.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import ReasonCode

EL_NINO, NEUTRAL, LA_NINA = KINDS_OF_YEAR

# D240 (2): the decimals of the values printed in the v6 table, to which the
# threshold is applied.
TABLE_DECIMALS = 1

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


def table_value(anom: float) -> Decimal:
    """An anomaly as the v6 table prints it: ``TABLE_DECIMALS`` decimals (D240).

    The number is read as it is written (``repr`` of the float, so 0.45 is
    0.45 and not its binary neighbour), then rounded half away from zero:
    0.45 is 0.5 and -0.46 is -0.5, while 0.44 is 0.4. How the table rounds a
    value that ends in 5 is not printed with it (README.md, OPEN).
    """
    quantum = Decimal(1).scaleb(-TABLE_DECIMALS)
    return Decimal(repr(float(anom))).quantize(quantum, rounding=ROUND_HALF_UP)


def _season_map(record: Mapping[str, Any]) -> dict[int, float]:
    """Season ordinal -> ANOM, every row checked (PROPOSED, S-027 F2).

    A ValueError naming the row index and the field when the record has no
    ``seasons`` list, a row is not a mapping or lacks ``season``, ``year`` or
    ``anom``, the season is unknown, the year is not an int (a bool is
    refused), the anom is not a finite real number (a bool, None, NaN or an
    infinity is refused), or a (season, year) row is duplicated.
    """
    rows = record.get("seasons")
    if not isinstance(rows, list):
        # ValueError, not TypeError: one exception type for every structural
        # misuse of the record (README.md).
        raise ValueError("record field 'seasons' must be a list of rows")  # noqa: TRY004
    values: dict[int, float] = {}
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
        position = _ordinal(season, year)
        if position in values:
            raise ValueError(f"seasons row {index}: duplicated season {season} {year}")
        values[position] = float(anom)
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
    values: Mapping[int, Decimal], position: int, threshold: Decimal, run_length: int
) -> str | None:
    """el_nino, la_nina or neutral for the season at ``position``.

    ``values`` are the table values of the record (``table_value``), so the
    threshold is met on the one-decimal values (D240). None when the seasons
    needed to judge it are not in the record.
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
    whose anomaly, as the v6 table prints it with one decimal (``table_value``,
    D240), meets ``+threshold`` (``-threshold``); "met" is read as at or
    beyond the threshold (PROPOSED). The kind of the year is the episode state
    of its deciding season; a year that cannot be judged from the record is
    missing ``NO_COVERAGE``.
    """
    _check_years(first_year, last_year)
    if first_year > last_year:
        raise ValueError("first_year must not be after last_year")
    _check_month(start_month)
    rule_threshold, run_length = _check_rule(record)
    threshold = Decimal(repr(rule_threshold))
    values = {
        position: table_value(anom) for position, anom in _season_map(record).items()
    }

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
                else f"a season needed to judge the run of season {season} "
                f"{season_year} is not in the record (outside its span or a gap "
                "in it)"
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
