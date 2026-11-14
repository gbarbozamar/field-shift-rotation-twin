"""Entry point EP1 of contracts/ENTRYPOINTS.md: ``compute_soil_loss``.

Mechanical form only (issue #115). The function lays out the agricultural
years of the climate record (decision D47 of issue #77) and their months, and
returns a ``SoilLossResults`` in which every annual and monthly value is
missing with the reason that applies. It computes no factor, reads no
parameter and returns no number. See SOIL_LOSS.md in this folder.

Status: PROPOSED (blueprint section 3.7): the order of the checks, the reason
of each value and the format of every ``detail``.

Pure function (G1): no file, no network, no clock, no environment variable,
and the arguments are not changed. The only integers are those of month
arithmetic, listed in SOIL_LOSS.md.
"""

from __future__ import annotations

import datetime as dt
from typing import get_args

from contracts.inputs.common import Value
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_SOIL_LOSS_MONTHLY,
    AnnualSoilLoss,
    Missing,
    MonthlySoilLoss,
    SoilLossResults,
)

__all__ = ["compute_soil_loss"]

# The identifier of the indicator, read from the results model (C1.1).
(INDICATOR,) = get_args(AnnualSoilLoss.model_fields["indicator"].annotation)

# The quantity identifier of daily precipitation (decision D23 of issue #77),
# the only climate series the soil-loss method reads (docs/METHODS.md M1.2).
PRECIPITATION = "precipitation"

# The five factors of docs/METHODS.md M1.1, in its order.
FACTORS: tuple[str, ...] = ("R", "K", "LS", "C", "P")

# Month arithmetic (C5.1, C5.3): twelve months to a year, months and days
# counted from one.
_MONTHS_IN_A_YEAR = 12
_FIRST = 1
_ONE_DAY = dt.timedelta(days=_FIRST)

# --- detail texts: PROPOSED, English for developers -------------------------

START_MONTH_MISSING = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the agricultural years cannot be laid out (EP1, Q4)"
)
PRECIPITATION_MISSING = (
    f"the climate record has no daily series with quantity '{PRECIPITATION}' "
    "(decision D23 of issue #77), so the agricultural years of the record cannot "
    "be laid out (decision D47 of issue #77; G4, third row)"
)
INFEASIBLE = (
    "the rotation calendar is infeasible (feasibility.feasible is false), so no "
    "value that depends on it is computed (G4, first row)"
)

# Per factor: (reason code of C3.2, why), for what holds whatever the
# arguments. A slope input that is missing is added to LS by _slope_items.
_FACTOR_ITEMS: dict[str, tuple[tuple[str, str], ...]] = {
    "R": (
        (
            "MISSING_INPUT",
            "the mean annual level is carried by no input contract "
            "(question 10 of contracts/inputs/README.md)",
        ),
        (
            "NOT_AVAILABLE",
            "the monthly erosivity fraction is a unit that is not built "
            "(blueprint section 8, Block 1)",
        ),
    ),
    "K": (
        (
            "MISSING_INPUT",
            "carried by no input contract (question 16 of "
            "contracts/inputs/README.md); its source is decided (decisions D10 and "
            "D48 of issue #77), not its path",
        ),
    ),
    "LS": (
        (
            "MISSING_INPUT",
            "the parameters are not passed to the entry point yet (decision D46 of "
            "issue #77, waiting for the platform developer's agreement)",
        ),
        (
            "MISSING_INPUT",
            "the unit of slope_steepness and slope_length is not mapped to "
            "SlopeUnit of engine/erosion/ls.py (question 18 of "
            "contracts/inputs/README.md, OPEN 1 of engine/erosion/LS.md)",
        ),
    ),
    "C": (
        (
            "MISSING_INPUT",
            "the calendar carries no period for cover management "
            "(engine/calendar/README.md P7)",
        ),
        (
            "NOT_AVAILABLE",
            "the cover-management unit is not built (docs/METHODS.md M1.5, "
            "decision D45 of issue #77, blueprint section 8, Block 2)",
        ),
    ),
    "P": (
        (
            "MISSING_INPUT",
            "the support practice is not among the arguments of EP1 "
            "(docs/METHODS.md M1.6, question 4 of contracts/inputs/README.md, "
            "decision D4 of issue #77)",
        ),
    ),
}


# --- checks of the caller (G5) ----------------------------------------------


def _check_types(calendar: object, climate: object, soil_slope: object) -> None:
    for name, argument, model in (
        ("calendar", calendar, RotationCalendar),
        ("climate", climate, SiteClimate),
        ("soil_slope", soil_slope, SiteSoilSlope),
    ):
        if not isinstance(argument, model):
            raise TypeError(
                f"{name}: expected {model.__name__}, got {type(argument).__name__} (G5)"
            )


def _check_same_field(
    calendar: RotationCalendar, climate: SiteClimate, soil_slope: SiteSoilSlope
) -> None:
    """``ValueError`` when the three arguments do not name one field (G5).

    The message names the identifier fields that differ, never their values.
    """
    differing = [
        field
        for field in ("case_id", "field_id")
        if getattr(climate, field) != getattr(calendar, field)
        or getattr(soil_slope, field) != getattr(calendar, field)
    ]
    if differing:
        raise ValueError(
            f"the arguments calendar, climate and soil_slope name different "
            f"{' and '.join(differing)} (G5)"
        )


# --- agricultural years and months (C5.3, D47) -------------------------------


def _month_at(index: int) -> tuple[int, int]:
    """Calendar year and month of a position on one line of months."""
    year, offset = divmod(index, _MONTHS_IN_A_YEAR)
    return year, offset + _FIRST


def _index_of(year: int, month: int) -> int:
    return year * _MONTHS_IN_A_YEAR + month - _FIRST


def _first_day(year: int, month: int) -> dt.date:
    return dt.date(year, month, _FIRST)


def _last_day(year: int, month: int) -> dt.date:
    return _first_day(*_month_at(_index_of(year, month) + _FIRST)) - _ONE_DAY


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - _FIRST


def _months_of(ag_year: int, start_month: int) -> list[tuple[int, int]]:
    first = _index_of(ag_year, start_month)
    return [_month_at(first + k) for k in range(_MONTHS_IN_A_YEAR)]


def _covers(series: DailySeries, first: dt.date, last: dt.date) -> bool:
    return series.start_date <= first and last <= series.end_date


# --- what each value reports --------------------------------------------------


def _slope_items(soil_slope: SiteSoilSlope) -> list[tuple[str, str]]:
    items = []
    for name in ("slope_steepness", "slope_length"):
        value: Value = getattr(soil_slope, name)
        if value.missing is not None:
            why = f"{name} is missing in the soil-and-slope data"
            if value.missing.detail is not None:
                why = f"{why}: {value.missing.detail}"
            items.append((value.missing.reason, why))
    return items


def _factors_detail(soil_slope: SiteSoilSlope) -> str:
    parts: list[str] = []
    for factor in FACTORS:
        items = list(_FACTOR_ITEMS[factor])
        if factor == "LS":
            items.extend(_slope_items(soil_slope))
        parts.extend(f"{factor} {code}: {why}" for code, why in items)
    return (
        f"soil loss needs the factors {', '.join(FACTORS)}, none is available: "
        + "; ".join(parts)
    )


def _not_covered(what: str) -> Missing:
    return Missing(
        reason="NO_COVERAGE",
        detail=(
            f"the daily series '{PRECIPITATION}' does not cover {what} from its first "
            "day to its last (C5.5)"
        ),
    )


def _annual(ag_year: int, missing: Missing) -> AnnualSoilLoss:
    return AnnualSoilLoss(
        indicator=INDICATOR,
        direction=DIRECTION_OF[INDICATOR],
        value=None,
        unit=UNIT_SOIL_LOSS_ANNUAL,
        missing=missing,
        ag_year=ag_year,
    )


def _monthly(ag_year: int, year: int, month: int, missing: Missing) -> MonthlySoilLoss:
    return MonthlySoilLoss(
        indicator=INDICATOR,
        direction=DIRECTION_OF[INDICATOR],
        value=None,
        unit=UNIT_SOIL_LOSS_MONTHLY,
        missing=missing,
        year=year,
        month=month,
        ag_year=ag_year,
    )


# --- the entry point ----------------------------------------------------------


def compute_soil_loss(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
) -> SoilLossResults | Missing:
    """Soil loss of one rotation of one field (EP1), in its mechanical form.

    Returns one ``Missing`` (reason ``MISSING_INPUT``) when the agricultural
    years cannot be laid out: the start month is missing, or the record has no
    daily ``precipitation`` series. Otherwise a ``SoilLossResults`` with every
    agricultural year of the record (D47) and its twelve months, each value
    missing with its reason: ``NOT_COMPUTABLE`` for an infeasible calendar,
    ``NO_COVERAGE`` for a year or month the series does not cover (C5.5),
    ``MISSING_INPUT`` naming the five factors for every other value.

    Raises ``TypeError`` for an argument that is not its model and
    ``ValueError`` when the arguments name different fields (G5).
    """
    _check_types(calendar, climate, soil_slope)
    _check_same_field(calendar, climate, soil_slope)

    start_month = calendar.ag_year_start.month
    if start_month is None:
        return Missing(reason="MISSING_INPUT", detail=START_MONTH_MISSING)

    series = next(
        (item for item in climate.daily_series if item.quantity == PRECIPITATION),
        None,
    )
    if series is None:
        return Missing(reason="MISSING_INPUT", detail=PRECIPITATION_MISSING)

    if not calendar.feasibility.feasible:
        infeasible: Missing | None = Missing(reason="NOT_COMPUTABLE", detail=INFEASIBLE)
    else:
        infeasible = None
    factors = Missing(reason="MISSING_INPUT", detail=_factors_detail(soil_slope))

    def missing_of(first: dt.date, last: dt.date, what: str) -> Missing:
        if infeasible is not None:
            return infeasible
        if not _covers(series, first, last):
            return _not_covered(what)
        return factors

    annual: list[AnnualSoilLoss] = []
    monthly: list[MonthlySoilLoss] = []
    first_ag_year = _ag_year_of(series.start_date, start_month)
    last_ag_year = _ag_year_of(series.end_date, start_month)
    for ag_year in range(first_ag_year, last_ag_year + _FIRST):
        first_index = _index_of(ag_year, start_month)
        last_index = first_index + _MONTHS_IN_A_YEAR - _FIRST
        annual.append(
            _annual(
                ag_year,
                missing_of(
                    _first_day(*_month_at(first_index)),
                    _last_day(*_month_at(last_index)),
                    f"agricultural year {ag_year}",
                ),
            )
        )
        for year, month in _months_of(ag_year, start_month):
            monthly.append(
                _monthly(
                    ag_year,
                    year,
                    month,
                    missing_of(
                        _first_day(year, month),
                        _last_day(year, month),
                        f"the month {year:04d}-{month:02d}",
                    ),
                )
            )

    return SoilLossResults(annual=annual, monthly=monthly)
