"""Entry point EP1 of contracts/ENTRYPOINTS.md: ``compute_soil_loss``.

Unit l0/erosion-ep1-c-r (issue #173), on the mechanical form of #125 and the
argument ``parameters`` of #154, revised after the review of PR #187. The
function lays out the agricultural years of the climate record (decision D47
of issue #77) and their months. It takes the parameter catalogue as the
keyword argument ``parameters`` (Q3, D46, D56).

``compute_soil_loss`` follows the route of the first release
(docs/METHODS.md M1.2; decisions D69 and D84 of issue #77, USER-G):

- the annual value of every covered year is ``equation.annual_soil_loss`` of
  the mean annual level of ``R`` (the variation between years is deferred),
  ``K``, ``LS`` through ``engine/erosion/ls.py``, ``C`` as the single declared
  value of its whole-factor record, and ``P``;
- a monthly value is ``R`` of the month (the level times the climatological
  fraction of the month, ``engine/erosion/r_factor/climatology.py``, from
  twelve records) times ``K``, ``LS``, ``C`` and ``P``. The licence of the
  climatology is settled (D101); until the twelve records exist, every month
  is missing, naming them.

``compute_soil_loss_daily_index`` keeps the daily-index route available, off
the main path: ``R`` through the daily erosivity index of ``r_factor/`` and
``C`` of each year through ``engine/erosion/c_factor/`` (D45, PC-1) from the
crop and the last harvest of each day of the rotation repeated over the years
of the record (D47, ``engine/calendar/repeat.py``, unit l1/calendar-repeat-d47).
The runner never calls it. See SOIL_LOSS.md in this folder.

Status: PROPOSED (blueprint section 3.7): the parameter identifiers and their
scope, the monthly value of the main route, the crop and the residue of a
day, the soil-loss ratio of a month, the reading of a unit string, the order
of the checks, the reason of each value and the format of every ``detail``.

Pure functions (G1): no file, no network, no clock, no environment variable,
and the arguments are not changed. ``load_folder`` is never called. The only
integers are those of month arithmetic, listed in SOIL_LOSS.md.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol, get_args

from contracts.inputs.common import Value
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    PROVENANCE_OF_SOIL_LOSS,
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_SOIL_LOSS_MONTHLY,
    AnnualSoilLoss,
    Missing,
    MonthlySoilLoss,
    SoilLossResults,
)
from engine.calendar.repeat import (
    RepeatedComponent,
    RepeatedRotation,
    repeat_over_record,
)
from engine.erosion import c_factor, ls, r_factor
from engine.erosion._parameters import Parameter, ParameterReader, scope_text
from engine.erosion.equation import AcceptedUnits, Factor, annual_soil_loss

__all__ = ["compute_soil_loss", "compute_soil_loss_daily_index"]

# The identifier of the indicator, read from the results model (C1.1).
(INDICATOR,) = get_args(AnnualSoilLoss.model_fields["indicator"].annotation)

# The quantity identifier of daily precipitation (decision D23 of issue #77),
# the only climate series the soil-loss method reads (docs/METHODS.md M1.2).
PRECIPITATION = "precipitation"

# --- parameters: PROPOSED identifiers and scope (SOIL_LOSS.md) ---------------

# The scope of every record that holds for the field and the method: the
# empty scope, "no restriction stated" (params/README.md). PROPOSED; the
# scope words are OPEN.
SCOPE: dict[str, str] = {}

# The scope of a record that holds on a day with no crop, as engine/water/
# reads it (EXPOSURE.md). PROPOSED.
NO_CROP_SCOPE: dict[str, str] = {"management": "no_crop"}

# The scope key of a record that holds for one crop of the calendar.
CROP_KEY = "crop"

# R (docs/METHODS.md M1.2), with the identifiers of engine/erosion/r_factor/
# README.md: the mean annual level, and the exponent and threshold of the
# daily erosivity index.
R_ID = "rusle_r_factor"
R_EXPONENT_ID = "rusle_r_daily_index_exponent"
R_THRESHOLD_ID = "rusle_r_daily_index_threshold"
R_IDS: tuple[str, ...] = (R_ID, R_EXPONENT_ID, R_THRESHOLD_ID)

# K and P: one record each.
K_ID = "rusle_k_factor"
P_ID = "rusle_p_factor"

# The whole-factor record of C: on the main route C is this single declared
# value (docs/METHODS.md M1.2; D69, D84, D101, USER-G), PROPOSED to stay so
# because a C computed through c_factor/ needs the crop of each day of the
# record and D47 repetition is not built (OPEN 12 and 28 of SOIL_LOSS.md). Not
# read on the daily-index route, which computes C through c_factor/.
C_ID = "rusle_c_factor"

# The twelve monthly erosivity values of the climatology at the point (D69,
# D84), one record per calendar month, January first (C5.1). The scope keys of
# params/README.md have no month, so the month is in the identifier
# (PROPOSED; OPEN 11 of SOIL_LOSS.md).
MONTH_WORDS: tuple[str, ...] = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
MONTHLY_EROSIVITY_PREFIX = "rusle_r_monthly_erosivity_"
MONTHLY_EROSIVITY_IDS: tuple[str, ...] = tuple(
    f"{MONTHLY_EROSIVITY_PREFIX}{word}" for word in MONTH_WORDS
)

# The coefficients of c_factor/ that hold for the field and the method, with
# the identifiers of engine/erosion/c_factor/README.md.
FALL_HEIGHT_COEFFICIENT_ID = "rusle2_canopy_fall_height_coefficient"
# The coefficient b of S1 Eq. 6.6 per percent of cover (decision PC-1).
SURFACE_COVER_B_PER_PERCENT_ID = "rusle2_surface_cover_b_per_percent"
MASS_COVER_COEFFICIENT_ID = "rusle2_residue_mass_cover_coefficient"
C_SITE_IDS: tuple[str, ...] = (
    FALL_HEIGHT_COEFFICIENT_ID,
    SURFACE_COVER_B_PER_PERCENT_ID,
    MASS_COVER_COEFFICIENT_ID,
)

# The inputs of c_factor/ read by crop. The canopy of a day: scope of its crop,
# or NO_CROP_SCOPE. The residue of a day: scope of the crop of the last
# harvest before it; the decay coefficient keeps the identifier of
# c_factor/README.md, its residue type named by that crop (PROPOSED).
CANOPY_COVER_ID = "rusle2_canopy_cover"
FALL_HEIGHT_ID = "rusle2_canopy_fall_height"
RESIDUE_MASS_ID = "rusle2_residue_mass_at_harvest"
DECAY_COEFFICIENT_ID = "rusle2_residue_decay_coefficient"
CANOPY_IDS: tuple[str, ...] = (CANOPY_COVER_ID, FALL_HEIGHT_ID)
RESIDUE_IDS: tuple[str, ...] = (RESIDUE_MASS_ID, DECAY_COEFFICIENT_ID)
CROP_PARAMETER_IDS: tuple[str, ...] = (*CANOPY_IDS, *RESIDUE_IDS)

# The coefficients of ls.py, by its argument name, with the identifiers that
# engine/erosion/LS.md proposes.
S_COEFFICIENTS: dict[str, str] = {
    "a1": "rusle_s_below_break_sine_coefficient",
    "a2": "rusle_s_below_break_constant",
    "a3": "rusle_s_at_or_above_break_sine_coefficient",
    "a4": "rusle_s_at_or_above_break_constant_subtracted",
}
S_BREAK_ID = "rusle_s_break_slope"
LAMBDA_UNIT_ID = "rusle_l_unit_length"
L_COEFFICIENTS: dict[str, str] = {
    "b1": "rusle_l_beta_sine_divisor",
    "b2": "rusle_l_beta_denominator_sine_coefficient",
    "b3": "rusle_l_beta_denominator_sine_exponent",
    "b4": "rusle_l_beta_denominator_constant",
}
LS_IDS: tuple[str, ...] = (
    *S_COEFFICIENTS.values(),
    S_BREAK_ID,
    LAMBDA_UNIT_ID,
    *L_COEFFICIENTS.values(),
)

# The main route (compute_soil_loss): every identifier the annual value reads,
# all with the empty scope; the monthly values also read MONTHLY_EROSIVITY_IDS.
PARAMETER_IDS: tuple[str, ...] = (R_ID, K_ID, *LS_IDS, C_ID, P_ID)

# The daily-index route (compute_soil_loss_daily_index), off the main path:
# every identifier read with the empty scope. The identifiers read by crop are
# CROP_PARAMETER_IDS.
DAILY_ROUTE_PARAMETER_IDS: tuple[str, ...] = (
    *R_IDS,
    K_ID,
    *LS_IDS,
    *C_SITE_IDS,
    P_ID,
)

# --- units ------------------------------------------------------------------

# The unit string the product accepts for each factor: R and K as decision
# D11 of issue #77 writes them (docs/METHODS.md M1.7); LS, C and P have no
# unit (M1.7), written "dimensionless" (contracts/CONVENTIONS.md C1.1).
DIMENSIONLESS = "dimensionless"
ACCEPTED_UNITS = AcceptedUnits(
    r=r_factor.R_UNIT,
    k="t ha h ha-1 MJ-1 mm-1",
    ls=DIMENSIONLESS,
    c=DIMENSIONLESS,
    p=DIMENSIONLESS,
)

# The reason of a unit the engine does not accept: the code ls.py proposes
# (Q11 of contracts/ENTRYPOINTS.md is not decided).
UNIT_NOT_ACCEPTED = ls.REASON_UNIT_NOT_ACCEPTED

# The unit of the time since a harvest: days of the daily series, the unit
# string of CQ1 in contracts/CLIMATE_QUANTITIES.md ("mm day-1"). PROPOSED.
DAY = "day"

# The unit whose inverse b of S1 Eq. 6.6 carries: percent of cover (PC-1).
PERCENT = "percent"

# How the inverse of a unit string is written on a coefficient record:
# "<unit>-1" for a unit of one word, "(<unit>)-1" for any unit. PROPOSED.
INVERSE_SUFFIX = "-1"
OPEN_BRACKET = "("
CLOSE_BRACKET = ")"

# Month arithmetic (C5.1, C5.3): twelve months to a year, months and days
# counted from one.
_MONTHS_IN_A_YEAR = 12
_FIRST = 1
_ONE_DAY = dt.timedelta(days=_FIRST)

# C of one agricultural year is rotation_c over its twelve months, divided by
# this number of years (M1.5). PROPOSED.
_ONE_AGRICULTURAL_YEAR = 1

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
MONTHLY_NOT_FORMED = (
    "a monthly value of soil loss is not formed on the daily-index route: "
    "docs/METHODS.md M1.1 and M1.5 give the annual product, and how R by month "
    "(M1.2, engine/erosion/r_factor/) and the soil-loss ratio of the month make a "
    "monthly value is not decided (OPEN 20 of engine/erosion/SOIL_LOSS.md)"
)
CLIMATOLOGY_PART = (
    "the climatological monthly fraction of R of docs/METHODS.md M1.2 (decisions "
    "D69, D84 and D101 of issue #77, USER-G; engine/erosion/r_factor/climatology.py)"
)
DECLARED_C = (
    "C is the single declared value of the record "
    f"'{C_ID}' (DECLARED; docs/METHODS.md M1.2, decisions D69, D84 and D101 of "
    "issue #77, USER-G): C computed through engine/erosion/c_factor/ from the "
    "rotation repeated over the years of the record (D47, engine/calendar/repeat.py) "
    "is on the daily-index route, and whether the main route switches to it is "
    "not decided (OPEN 28 of engine/erosion/SOIL_LOSS.md)"
)
RANGE_NOT_BUILT = (
    "how an uncertainty range passes through the product of docs/METHODS.md M1.1 "
    "is not built (C2.3; OPEN 5 of engine/erosion/EQUATION.md)"
)
INDEX_PART = (
    "the daily erosivity index of docs/METHODS.md M1.2 (engine/erosion/r_factor/), "
    "whose monthly fractions and yearly ratios R and C need"
)
LEVEL_PART = (
    "the mean annual level of R of docs/METHODS.md M1.2 (engine/erosion/r_factor/)"
)
CANOPY_PART = (
    "the canopy sub-factor of docs/METHODS.md M1.5 (decision D45 of issue #77; "
    "engine/erosion/c_factor/)"
)
SURFACE_PART = (
    "the surface-cover sub-factor of S1 Eq. 6.6 per percent of cover, "
    "docs/METHODS.md M1.5 (decisions D45 and PC-1; engine/erosion/c_factor/)"
)
RESIDUE_PART = (
    "the surface residue cover, with residue decay by residue type, of "
    "docs/METHODS.md M1.5 (decision D45 of issue #77; engine/erosion/c_factor/)"
)
OUTSIDE_RECORD = (
    "the day lies outside the agricultural years of the climate record over which "
    "the rotation is repeated (decision D47 of issue #77; engine/calendar/repeat.py)"
)
BEFORE_FIRST_CYCLE = (
    "the day lies before the first cycle of the rotation repeated over the years of "
    "the climate record (decision D47 of issue #77; engine/calendar/repeat.py), so "
    "the calendar does not describe it: nothing is laid out before the first cycle "
    "(OPEN 2 of engine/erosion/SOIL_LOSS.md)"
)
NO_HARVEST_BEFORE = (
    "no component of the rotation, repeated over the years of the climate record "
    "from its first agricultural year (decision D47 of issue #77; "
    "engine/calendar/repeat.py), ends before the day, so the residue on the surface "
    "is not known: the residue left before the record begins is not laid out "
    "(OPEN 2 of engine/erosion/SOIL_LOSS.md; the residue ledger, Q12 of "
    "contracts/ENTRYPOINTS.md)"
)
TOLERANCE_NOT_SUPPLIED = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "EP1 supplies no tolerance for the sum of the erosivity fractions (OPEN 9 "
        "of engine/erosion/c_factor/README.md); it only drives fractions_add_up, "
        "which EP1 does not read"
    ),
)


# --- checks of the caller (G5) ----------------------------------------------


def _check_types(
    calendar: object, climate: object, soil_slope: object, parameters: object
) -> None:
    for name, argument, model in (
        ("calendar", calendar, RotationCalendar),
        ("climate", climate, SiteClimate),
        ("soil_slope", soil_slope, SiteSoilSlope),
    ):
        if not isinstance(argument, model):
            raise TypeError(
                f"{name}: expected {model.__name__}, got {type(argument).__name__} (G5)"
            )
    if not isinstance(parameters, dict):
        raise TypeError(
            f"parameters: expected dict[str, dict], got {type(parameters).__name__} (G5)"
        )
    for key, record in parameters.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise TypeError(
                "parameters: expected dict[str, dict], got an item keyed by "
                f"{type(key).__name__} holding {type(record).__name__} (G5)"
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


def _days_of(year: int, month: int) -> Iterator[dt.date]:
    day = _first_day(year, month)
    last = _last_day(year, month)
    while day <= last:
        yield day
        day += _ONE_DAY


def _covers(series: DailySeries, first: dt.date, last: dt.date) -> bool:
    return series.start_date <= first and last <= series.end_date


def _month_label(year: int, month: int) -> str:
    return _first_day(year, month).strftime("%Y-%m")


# --- unit strings (PROPOSED) --------------------------------------------------


def _per_unit(unit: str) -> str | None:
    """The unit whose inverse the unit string is, or ``None``. PROPOSED.

    ``"<u>-1"`` gives ``<u>`` when ``<u>`` is one word (no space, no
    bracket); ``"(<u>)-1"`` gives ``<u>`` for any ``<u>`` that is not empty.
    Any other string is not read.
    """
    if not unit.endswith(INVERSE_SUFFIX):
        return None
    base = unit.removesuffix(INVERSE_SUFFIX)
    if base.startswith(OPEN_BRACKET) and base.endswith(CLOSE_BRACKET):
        inner = base.removeprefix(OPEN_BRACKET).removesuffix(CLOSE_BRACKET)
        return inner if inner.strip() else None
    if not base or any(mark in base for mark in (" ", OPEN_BRACKET, CLOSE_BRACKET)):
        return None
    return base


def _inverse_not_read(what: str, unit: str) -> str:
    return (
        f"the unit '{unit}' of {what} is not read as the inverse of a unit: it is "
        f"written '<unit>{INVERSE_SUFFIX}' for a unit of one word or "
        f"'{OPEN_BRACKET}<unit>{CLOSE_BRACKET}{INVERSE_SUFFIX}' (OPEN 21 of "
        "engine/erosion/SOIL_LOSS.md)"
    )


def _not_dimensionless(what: str, unit: str) -> str:
    return (
        f"the unit '{unit}' of {what} is not '{DIMENSIONLESS}': c_factor/ reads it as "
        "a fraction from zero to one (OPEN 3 of engine/erosion/c_factor/README.md)"
    )


# --- the factors read from one record ----------------------------------------


@dataclass(frozen=True)
class _Problem:
    """Why a value is not computed: a reason code and a text for ``detail``."""

    reason: str
    text: str


def _factor(parameter: Parameter, accepted: str, extra: str | None = None) -> Factor:
    """A factor read from one record.

    A missing factor keeps the unit it would have, the accepted one (C3.1).
    ``extra`` is added to the detail of a missing factor.
    """
    if isinstance(parameter.value, Missing):
        missing = parameter.value
        if extra is not None:
            missing = Missing(
                reason=missing.reason, detail=f"{missing.detail}; {extra}"
            )
        return Factor(value=missing, unit=accepted)
    assert parameter.unit is not None  # a record was read
    return Factor(value=parameter.value, unit=parameter.unit)


def _combined(problems: list[_Problem], prefix: str) -> Missing:
    """One ``Missing`` for several problems, each named once, in order.

    ``MISSING_INPUT`` when any problem is an input that is missing (C3.3);
    otherwise the reason of the first problem.
    """
    texts = list(dict.fromkeys(problem.text for problem in problems))
    reasons = [problem.reason for problem in problems]
    reason = "MISSING_INPUT" if "MISSING_INPUT" in reasons else next(iter(reasons))
    return Missing(reason=reason, detail=f"{prefix}: {'; '.join(texts)}")


def _missing_record(parameter: Parameter, part: str) -> _Problem | None:
    if isinstance(parameter.value, Missing):
        assert parameter.value.detail is not None
        return _Problem("MISSING_INPUT", f"{parameter.value.detail}; needed by {part}")
    return None


# --- LS -------------------------------------------------------------------------


def _slope_unit(unit: str) -> ls.SlopeUnit | None:
    """The ``SlopeUnit`` whose value is the unit string, or ``None``. PROPOSED."""
    return next((item for item in ls.SlopeUnit if item.value == unit), None)


def _unit_not_read(what: str, unit: str) -> str:
    accepted = ", ".join(f"'{item.value}'" for item in ls.SlopeUnit)
    return (
        f"the unit '{unit}' of {what} is not one that engine/erosion/ls.py reads as a "
        f"slope (SlopeUnit: {accepted}; question 18 of contracts/inputs/README.md, "
        "OPEN 1 of engine/erosion/LS.md)"
    )


def _input_missing(name: str, value: Value) -> str:
    assert value.missing is not None
    why = f"{name} is missing in the soil-and-slope data, reason {value.missing.reason}"
    if value.missing.detail is not None:
        why = f"{why}: {value.missing.detail}"
    return why


def _ls_factor(soil_slope: SiteSoilSlope, reader: ParameterReader) -> Factor:
    """``LS = L * S`` through ls.py, or why it is missing.

    Every input and every coefficient is looked at first. Any that is missing
    gives ``MISSING_INPUT`` naming each one (C3.3, G4); then a slope unit that
    cannot be read gives ``UNIT_NOT_ACCEPTED``; only then ls.py is called, and
    a ``Missing`` it returns is the factor's.
    """
    slope = soil_slope.slope_steepness
    length = soil_slope.slope_length
    read = {pid: reader.read(pid, SCOPE) for pid in LS_IDS}

    absent = [
        _input_missing(name, value)
        for name, value in (("slope_steepness", slope), ("slope_length", length))
        if value.missing is not None
    ]
    absent += [
        parameter.value.detail
        for parameter in read.values()
        if isinstance(parameter.value, Missing)
    ]
    if absent:
        return Factor(
            value=Missing(reason="MISSING_INPUT", detail="; ".join(absent)),
            unit=ACCEPTED_UNITS.ls,
        )

    s_break = read[S_BREAK_ID]
    assert s_break.unit is not None and slope.value is not None
    slope_unit = _slope_unit(slope.unit)
    s_break_unit = _slope_unit(s_break.unit)
    not_read = []
    if slope_unit is None:
        not_read.append(_unit_not_read("slope_steepness", slope.unit))
    if s_break_unit is None:
        not_read.append(_unit_not_read(f"parameter '{S_BREAK_ID}'", s_break.unit))
    if slope_unit is None or s_break_unit is None:
        return Factor(
            value=Missing(reason=UNIT_NOT_ACCEPTED, detail="; ".join(not_read)),
            unit=ACCEPTED_UNITS.ls,
        )

    lambda_unit = read[LAMBDA_UNIT_ID]
    assert lambda_unit.unit is not None and length.value is not None
    steepness = ls.slope_steepness_factor(
        slope_steepness=slope.value,
        slope_unit=slope_unit,
        s_break=s_break.value,
        s_break_unit=s_break_unit,
        **{name: read[pid].value for name, pid in S_COEFFICIENTS.items()},
    )
    length_factor = ls.slope_length_factor(
        slope_length=length.value,
        slope_length_unit=length.unit,
        lambda_unit=lambda_unit.value,
        lambda_unit_unit=lambda_unit.unit,
        slope_steepness=slope.value,
        slope_unit=slope_unit,
        **{name: read[pid].value for name, pid in L_COEFFICIENTS.items()},
    )
    for part in (steepness, length_factor):
        if isinstance(part, Missing):
            return Factor(value=part, unit=ACCEPTED_UNITS.ls)
    product = length_factor * steepness
    if not math.isfinite(product):
        return Factor(
            value=Missing(
                reason="NOT_COMPUTABLE",
                detail="LS: the product of L and S is not a finite number",
            ),
            unit=ACCEPTED_UNITS.ls,
        )
    return Factor(value=product, unit=ACCEPTED_UNITS.ls)


# --- R: through r_factor/ (M1.2) -------------------------------------------------

R_FACTOR = "engine/erosion/r_factor/"

YearMonth = tuple[int, int]
ByYear = dict[int, dict[YearMonth, float | Missing]]


@dataclass(frozen=True)
class _Erosivity:
    """What r_factor/ gives for the record: monthly fractions and R by month.

    Each is the table of ``r_factor.r_factor_parts`` or one ``Missing`` that
    names what is missing.
    """

    fractions: ByYear | Missing
    r_by_month: ByYear | Missing


def _erosivity(
    series: DailySeries, start_month: int, reader: ParameterReader
) -> _Erosivity:
    """The steps of M1.2 through ``r_factor.r_factor_parts``.

    A record of the exponent or the threshold that cannot be read makes the
    fractions and R missing; a record of the level that cannot be read makes R
    missing and leaves the fractions. Each names the records by id and scope
    and the part of M1.2 that needs them.
    """
    level = reader.read(R_ID, SCOPE)
    exponent = reader.read(R_EXPONENT_ID, SCOPE)
    threshold = reader.read(R_THRESHOLD_ID, SCOPE)
    index_problems = [
        problem
        for problem in (
            _missing_record(exponent, INDEX_PART),
            _missing_record(threshold, INDEX_PART),
        )
        if problem is not None
    ]
    level_problem = _missing_record(level, LEVEL_PART)
    r_problems = index_problems + ([level_problem] if level_problem else [])
    r_missing = _combined(r_problems, "R by month") if r_problems else None
    if index_problems:
        assert r_missing is not None
        return _Erosivity(
            fractions=_combined(index_problems, "the monthly erosivity fractions"),
            r_by_month=r_missing,
        )
    assert threshold.unit is not None
    parts = r_factor.r_factor_parts(
        series=series,
        exponent=exponent.value,
        threshold=threshold.value,
        threshold_unit=threshold.unit,
        start_month=start_month,
        mean_annual_r=level.value,
        mean_annual_r_unit=level.unit if level.unit is not None else r_factor.R_UNIT,
    )
    return _Erosivity(
        fractions=parts.monthly_fractions,
        r_by_month=r_missing if r_missing is not None else parts.r_by_year_and_month,
    )


def _year_table(
    table: ByYear | Missing, ag_year: int, start_month: int, what: str, where: str
) -> dict[YearMonth, float] | Missing:
    """The twelve numbers of one agricultural year of a table of r_factor/.

    Every month that is not a number is named, never dropped: a missing month
    once per reason and detail; a month the table does not hold, or that
    holds something other than a number, as ``NOT_COMPUTABLE``. The reason is
    the one the named months share, otherwise ``MISSING_INPUT``.
    """
    if isinstance(table, Missing):
        return table
    months = table.get(ag_year)
    if months is None:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"{where} gives no {what} for agricultural year {ag_year}",
        )
    groups: dict[tuple[str, str | None], list[str]] = {}
    numbers: dict[YearMonth, float] = {}
    for year, month in _months_of(ag_year, start_month):
        value = months.get((year, month))
        if isinstance(value, Missing):
            key: tuple[str, str | None] = (value.reason, value.detail)
        elif value is None:
            key = ("NOT_COMPUTABLE", f"{where} holds no value for the month")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            key = (
                "NOT_COMPUTABLE",
                f"{where} holds a {type(value).__name__} for the month, not a number",
            )
        else:
            numbers[(year, month)] = float(value)
            continue
        groups.setdefault(key, []).append(_month_label(year, month))
    if groups:
        reasons = list(dict.fromkeys(reason for reason, _ in groups))
        reason = next(iter(reasons)) if len(reasons) == _FIRST else "MISSING_INPUT"
        texts = [
            f"{', '.join(labels)} ({code}: {detail})"
            for (code, detail), labels in groups.items()
        ]
        return Missing(
            reason=reason,
            detail=(
                f"{what} of {where} is missing for agricultural year {ag_year} in the "
                f"month(s) {'; '.join(texts)}"
            ),
        )
    return numbers


def _r_of_year(erosivity: _Erosivity, ag_year: int, start_month: int) -> Factor:
    """R of one agricultural year: the sum of its twelve values of R by month."""
    months = _year_table(
        erosivity.r_by_month, ag_year, start_month, "R by month", R_FACTOR
    )
    if isinstance(months, Missing):
        return Factor(value=months, unit=ACCEPTED_UNITS.r)
    total = sum(months.values())
    if not math.isfinite(total):
        return Factor(
            value=Missing(
                reason="NOT_COMPUTABLE",
                detail=f"R of agricultural year {ag_year} is not a finite number",
            ),
            unit=ACCEPTED_UNITS.r,
        )
    return Factor(value=total, unit=ACCEPTED_UNITS.r)


# --- C: through c_factor/ (M1.5, D45) --------------------------------------------


def _earliest(component: RepeatedComponent) -> dt.date:
    """The first day a component can cover: its start, else its cycle's start."""
    return component.start if component.start is not None else component.calendar_start


def _latest(component: RepeatedComponent) -> dt.date:
    """The last day a component can cover: its end, else the day before the
    next cycle starts (point 7 of engine/calendar/repeat.py)."""
    return component.end if component.end is not None else component.cycle_last_day


def _crop_scope(repeated: RepeatedRotation, day: dt.date) -> dict[str, str] | _Problem:
    """The scope of the canopy records of a day. PROPOSED, as engine/water/.

    The crop of the one dated component of the repeated rotation (D47) that
    covers the day; ``NO_CROP_SCOPE`` when no component can cover it; a
    problem when the day lies outside the years of the record or before the
    first cycle, when two components cover it, or when a component with a
    missing date could cover it (within its cycle, point 7 of
    engine/calendar/repeat.py).
    """
    if not repeated.first_day <= day <= repeated.last_day:
        return _Problem("MISSING_INPUT", OUTSIDE_RECORD)
    if day < repeated.described_from:
        return _Problem("MISSING_INPUT", BEFORE_FIRST_CYCLE)
    covering = [
        component
        for component in repeated.components
        if component.start is not None
        and component.end is not None
        and component.start <= day <= component.end
    ]
    if len(covering) > _FIRST:
        names = ", ".join(repr(c.component_id) for c in covering)
        return _Problem(
            "NOT_COMPUTABLE",
            f"the components {names} of the rotation calendar cover the same day",
        )
    if covering:
        (component,) = covering
        return {CROP_KEY: component.crop_id}
    undated = [
        component.component_id
        for component in repeated.components
        if (component.start is None or component.end is None)
        and _earliest(component) <= day <= _latest(component)
    ]
    if undated:
        names = ", ".join(repr(name) for name in dict.fromkeys(undated))
        return _Problem(
            "MISSING_INPUT",
            f"the component(s) {names} of the rotation calendar have a missing date, "
            "so whether they cover the day is not known",
        )
    return dict(NO_CROP_SCOPE)


def _last_harvest(
    repeated: RepeatedRotation, day: dt.date
) -> RepeatedComponent | _Problem:
    """The component whose end date is the last one before the day. PROPOSED.

    Searched in the rotation repeated over the years of the record (D47). Its
    residue is the residue on the surface on the day. A problem when the day
    lies outside the years of the record, when a component without an end
    date could have ended before the day and after every known end before it,
    when no component ends before it, or when two components end on that
    last date.
    """
    if not repeated.first_day <= day <= repeated.last_day:
        return _Problem("MISSING_INPUT", OUTSIDE_RECORD)
    ended = [
        component
        for component in repeated.components
        if component.end is not None and component.end < day
    ]
    last = max((c.end for c in ended if c.end is not None), default=None)
    unknown = [
        component.component_id
        for component in repeated.components
        if component.end is None
        and _earliest(component) < day
        and (last is None or component.cycle_last_day >= last)
    ]
    if unknown:
        names = ", ".join(repr(name) for name in dict.fromkeys(unknown))
        return _Problem(
            "MISSING_INPUT",
            f"the component(s) {names} of the rotation calendar have no end date, so "
            "the last harvest before the day is not known",
        )
    if last is None:
        return _Problem("MISSING_INPUT", NO_HARVEST_BEFORE)
    at_last = [component for component in ended if component.end == last]
    if len(at_last) > _FIRST:
        names = ", ".join(repr(c.component_id) for c in at_last)
        return _Problem(
            "NOT_COMPUTABLE",
            f"the components {names} of the rotation calendar end on the same day, "
            "so the residue of the last harvest is not one crop's",
        )
    (component,) = at_last
    return component


@dataclass
class _DayGroups:
    """Problems of the days of a year, each text once, with its days counted."""

    days: dict[tuple[str, str], list[dt.date]] = field(default_factory=dict)

    def add(self, problem: _Problem, day: dt.date) -> None:
        self.days.setdefault((problem.reason, problem.text), []).append(day)

    def problems(self) -> list[_Problem]:
        return [
            _Problem(
                reason,
                f"{text} ({len(days)} day(s) of the year, the first on "
                f"{min(days).isoformat()})",
            )
            for (reason, text), days in self.days.items()
        ]


@dataclass(frozen=True)
class _DayInputs:
    """What the soil-loss ratio of one day is computed from."""

    crop_scope: dict[str, str]
    harvest: RepeatedComponent


def _scope_of_crop(crop_id: str) -> dict[str, str]:
    return {CROP_KEY: crop_id}


def _c_inputs(
    repeated: RepeatedRotation,
    ag_year: int,
    start_month: int,
    reader: ParameterReader,
) -> tuple[dict[dt.date, _DayInputs], list[_Problem]]:
    """The inputs of every day of an agricultural year, and every problem.

    A problem is a day whose crop or residue is not known, or a record of
    c_factor/ that cannot be read (named by id and scope, with the part of
    M1.5 that needs it), or a unit string that is not read.
    """
    problems: list[_Problem] = []
    groups = _DayGroups()
    inputs: dict[dt.date, _DayInputs] = {}
    parts = {
        FALL_HEIGHT_COEFFICIENT_ID: CANOPY_PART,
        SURFACE_COVER_B_PER_PERCENT_ID: SURFACE_PART,
        MASS_COVER_COEFFICIENT_ID: RESIDUE_PART,
    }
    for pid in C_SITE_IDS:
        problem = _missing_record(reader.read(pid, SCOPE), parts[pid])
        if problem is not None:
            problems.append(problem)
    for year, month in _months_of(ag_year, start_month):
        for day in _days_of(year, month):
            crop_scope = _crop_scope(repeated, day)
            harvest = _last_harvest(repeated, day)
            if isinstance(crop_scope, _Problem):
                groups.add(crop_scope, day)
            else:
                for pid in CANOPY_IDS:
                    problem = _missing_record(reader.read(pid, crop_scope), CANOPY_PART)
                    if problem is not None:
                        problems.append(problem)
            if isinstance(harvest, _Problem):
                groups.add(harvest, day)
            else:
                for pid in RESIDUE_IDS:
                    problem = _missing_record(
                        reader.read(pid, _scope_of_crop(harvest.crop_id)), RESIDUE_PART
                    )
                    if problem is not None:
                        problems.append(problem)
            if not isinstance(crop_scope, _Problem) and not isinstance(
                harvest, _Problem
            ):
                inputs[day] = _DayInputs(crop_scope=crop_scope, harvest=harvest)
    problems += groups.problems()
    if problems:
        return inputs, problems
    return inputs, _unit_problems(inputs, reader)


def _unit_problems(
    inputs: dict[dt.date, _DayInputs], reader: ParameterReader
) -> list[_Problem]:
    """Unit strings of the records of c_factor/ that are not read. PROPOSED."""
    texts: list[str] = []
    surface = reader.read(SURFACE_COVER_B_PER_PERCENT_ID, SCOPE)
    assert surface.unit is not None
    if _per_unit(surface.unit) != PERCENT:
        texts.append(
            f"the unit '{surface.unit}' of parameter '{SURFACE_COVER_B_PER_PERCENT_ID}' "
            f"is not '{PERCENT}{INVERSE_SUFFIX}': b of S1 Eq. 6.6 multiplies the cover "
            "in percent (decision PC-1)"
        )
    for pid in (FALL_HEIGHT_COEFFICIENT_ID, MASS_COVER_COEFFICIENT_ID):
        unit = reader.read(pid, SCOPE).unit
        assert unit is not None
        if _per_unit(unit) is None:
            texts.append(_inverse_not_read(f"parameter '{pid}' with scope {{}}", unit))
    crop_scopes = {
        scope_text(item.crop_scope): item.crop_scope for item in inputs.values()
    }
    for text, scope in crop_scopes.items():
        unit = reader.read(CANOPY_COVER_ID, scope).unit
        assert unit is not None
        if unit != DIMENSIONLESS:
            texts.append(
                _not_dimensionless(
                    f"parameter '{CANOPY_COVER_ID}' with scope {text}", unit
                )
            )
    crops = dict.fromkeys(item.harvest.crop_id for item in inputs.values())
    for crop_id in crops:
        scope = _scope_of_crop(crop_id)
        unit = reader.read(DECAY_COEFFICIENT_ID, scope).unit
        assert unit is not None
        if _per_unit(unit) is None:
            texts.append(
                _inverse_not_read(
                    f"parameter '{DECAY_COEFFICIENT_ID}' with scope {scope_text(scope)}",
                    unit,
                )
            )
    return [_Problem(UNIT_NOT_ACCEPTED, text) for text in dict.fromkeys(texts)]


def _number(parameter: Parameter) -> float:
    assert isinstance(parameter.value, float)
    return parameter.value


def _unit(parameter: Parameter) -> str:
    assert parameter.unit is not None
    return parameter.unit


def _inverse_of(parameter: Parameter) -> str:
    """The unit whose inverse is the unit of a record checked by ``_unit_problems``."""
    per_unit = _per_unit(_unit(parameter))
    assert per_unit is not None
    return per_unit


@dataclass(frozen=True)
class _DayRatio:
    """The soil-loss ratio of one day and its two sub-factors."""

    ratio: float
    canopy: float
    surface_cover: float


def _day_ratio(
    day: dt.date, inputs: _DayInputs, reader: ParameterReader
) -> _DayRatio | _Problem:
    """The soil-loss ratio of one day, through c_factor/, or the first refusal.

    In order (decision PC-1): the residue mass of the last harvest after its
    decay, its cover, the surface-cover sub-factor of S1 Eq. 6.6 per percent
    of cover, the effective canopy cover of S1 Eq. 6.5 over that cover, the
    canopy sub-factor of that effective cover, and their product.
    """
    harvest = inputs.harvest
    residue_scope = _scope_of_crop(harvest.crop_id)
    residue_text = scope_text(residue_scope)
    crop_text = scope_text(inputs.crop_scope)
    mass = reader.read(RESIDUE_MASS_ID, residue_scope)
    decay = reader.read(DECAY_COEFFICIENT_ID, residue_scope)
    mass_coefficient = reader.read(MASS_COVER_COEFFICIENT_ID, SCOPE)
    fall_coefficient = reader.read(FALL_HEIGHT_COEFFICIENT_ID, SCOPE)
    fall_height = reader.read(FALL_HEIGHT_ID, inputs.crop_scope)
    assert harvest.end is not None

    after_decay = c_factor.residue_mass_after_decay(
        residue_mass=_number(mass),
        residue_type=harvest.crop_id,
        decay_coefficients={harvest.crop_id: _number(decay)},
        decay_coefficient_per_unit=_inverse_of(decay),
        elapsed_time=(day - harvest.end).days,
        elapsed_time_unit=DAY,
    )
    if isinstance(after_decay, Missing):
        return _refused(day, "residue_mass_after_decay", residue_text, after_decay)
    cover = c_factor.residue_cover_from_mass(
        residue_mass=after_decay,
        residue_mass_unit=_unit(mass),
        mass_cover_coefficient=_number(mass_coefficient),
        mass_cover_coefficient_per_unit=_inverse_of(mass_coefficient),
    )
    if isinstance(cover, Missing):
        return _refused(day, "residue_cover_from_mass", residue_text, cover)
    surface_cover = c_factor.surface_cover_subfactor_percent(
        surface_residue_cover=cover,
        surface_cover_coefficient_per_percent=_number(
            reader.read(SURFACE_COVER_B_PER_PERCENT_ID, SCOPE)
        ),
    )
    if isinstance(surface_cover, Missing):
        return _refused(day, "surface_cover_subfactor_percent", None, surface_cover)
    effective = c_factor.effective_canopy_cover(
        canopy_cover=_number(reader.read(CANOPY_COVER_ID, inputs.crop_scope)),
        ground_cover=cover,
    )
    if isinstance(effective, Missing):
        return _refused(day, "effective_canopy_cover", crop_text, effective)
    canopy = c_factor.canopy_subfactor(
        canopy_cover=effective,
        fall_height=_number(fall_height),
        fall_height_unit=_unit(fall_height),
        fall_height_coefficient=_number(fall_coefficient),
        fall_height_coefficient_per_unit=_inverse_of(fall_coefficient),
    )
    if isinstance(canopy, Missing):
        return _refused(day, "canopy_subfactor", crop_text, canopy)
    ratio = c_factor.soil_loss_ratio(canopy=canopy, surface_cover=surface_cover)
    if isinstance(ratio.value, Missing):
        return _refused(day, "soil_loss_ratio", None, ratio.value)
    return _DayRatio(ratio=ratio.value, canopy=canopy, surface_cover=surface_cover)


def _refused(
    day: dt.date, function: str, scope: str | None, missing: Missing
) -> _Problem:
    """The first refusal of c_factor/ on a day, named with the day and function."""
    records = "" if scope is None else f" with the records of scope {scope}"
    return _Problem(
        missing.reason,
        f"on {day.isoformat()}, {function} of engine/erosion/c_factor/{records}: "
        f"{missing.detail}",
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _c_of_year(
    repeated: RepeatedRotation,
    ag_year: int,
    start_month: int,
    erosivity: _Erosivity,
    reader: ParameterReader,
) -> Factor:
    """C of one agricultural year through c_factor/ (M1.5), or why it is missing.

    Every problem is gathered first: the monthly erosivity fractions of
    r_factor/, the crop and the residue of each day, the records of
    c_factor/ and their unit strings. Any problem makes C missing and names
    each. Otherwise the soil-loss ratio of each day, its mean over each month
    (PROPOSED), and ``c_factor.rotation_c`` over the twelve months with the
    fractions of the year and one year (PROPOSED).
    """
    prefix = f"C of agricultural year {ag_year} is not computed"
    fractions = _year_table(
        erosivity.fractions,
        ag_year,
        start_month,
        "the monthly erosivity fraction",
        R_FACTOR,
    )
    problems: list[_Problem] = []
    if isinstance(fractions, Missing):
        problems.append(
            _Problem(
                "MISSING_INPUT",
                f"the monthly erosivity fractions of M1.2 are missing "
                f"({fractions.reason}: {fractions.detail})",
            )
        )
    inputs, more = _c_inputs(repeated, ag_year, start_month, reader)
    problems += more
    if problems:
        return Factor(value=_combined(problems, prefix), unit=ACCEPTED_UNITS.c)
    assert not isinstance(fractions, Missing)

    months: list[c_factor.MonthOfRotation] = []
    for year, month in _months_of(ag_year, start_month):
        days: list[_DayRatio] = []
        for day in _days_of(year, month):
            outcome = _day_ratio(day, inputs[day], reader)
            if isinstance(outcome, _Problem):
                return Factor(
                    value=Missing(
                        reason=outcome.reason, detail=f"{prefix}: {outcome.text}"
                    ),
                    unit=ACCEPTED_UNITS.c,
                )
            days.append(outcome)
        months.append(
            c_factor.MonthOfRotation(
                label=_month_label(year, month),
                erosivity_fraction=fractions[(year, month)],
                soil_loss_ratio=c_factor.SoilLossRatio(
                    value=_mean([item.ratio for item in days]),
                    canopy=_mean([item.canopy for item in days]),
                    surface_cover=_mean([item.surface_cover for item in days]),
                    set_to_one=c_factor.SET_TO_ONE,
                    limit=c_factor.DECLARED_LIMIT,
                ),
            )
        )
    rotation = c_factor.rotation_c(
        months=months,
        number_of_years=_ONE_AGRICULTURAL_YEAR,
        fraction_sum_tolerance=TOLERANCE_NOT_SUPPLIED,
    )
    if isinstance(rotation.value, Missing):
        return Factor(
            value=Missing(
                reason=rotation.value.reason,
                detail=(
                    f"{prefix}: rotation_c of engine/erosion/c_factor/: "
                    f"{rotation.value.detail}"
                ),
            ),
            unit=ACCEPTED_UNITS.c,
        )
    return Factor(value=rotation.value, unit=ACCEPTED_UNITS.c)


# --- the annual product -----------------------------------------------------------


def _annual_product(
    r: Factor, k: Factor, ls_: Factor, c: Factor, p: Factor
) -> float | Missing:
    return annual_soil_loss(
        r=r,
        k=k,
        ls=ls_,
        c=c,
        p=p,
        accepted_units=ACCEPTED_UNITS,
        unit_guard_reason=UNIT_NOT_ACCEPTED,
    )


def _records_text(reader: ParameterReader) -> str:
    return ", ".join(
        f"'{pid}' with scope {scope}" for pid, scope in reader.records_read()
    )


def _daily_source(reader: ParameterReader) -> str:
    """The source of an annual value of the daily-index route. PROPOSED
    (question 11 of contracts/results/README.md is OPEN)."""
    return (
        "derived by engine.erosion.soil_loss.compute_soil_loss_daily_index (the "
        "daily-index route, off the main path) with the product of docs/METHODS.md "
        "M1.1: R of the agricultural year as the sum of R by month of "
        f"engine/erosion/r_factor/ (M1.2) from the daily series '{PRECIPITATION}'; "
        "C through engine/erosion/c_factor/ (M1.5, decisions D45 and PC-1) from the "
        "rotation calendar, weighted by the monthly erosivity fractions of "
        "r_factor/; LS from engine/erosion/ls.py with the slope of the "
        "soil-and-slope data; K and P from their records; parameter records read: "
        f"{_records_text(reader)}"
    )


def _main_source(reader: ParameterReader) -> str:
    """The source of an annual value of the main route. PROPOSED (question 11
    of contracts/results/README.md is OPEN)."""
    return (
        "derived by engine.erosion.compute_soil_loss with the product of "
        "docs/METHODS.md M1.1: R as the mean annual level of the record "
        f"'{R_ID}' for every agricultural year, the variation between years "
        f"deferred (USER-G, decision D69 of issue #77); {DECLARED_C}; LS from "
        "engine/erosion/ls.py with the slope of the soil-and-slope data; K and P "
        f"from their records; parameter records read: {_records_text(reader)}"
    )


def _monthly_source(annual_source: str, reader: ParameterReader) -> str:
    return (
        f"{annual_source}; the month: R of the month as the level times the "
        "climatological monthly fraction of docs/METHODS.md M1.2 "
        "(engine/erosion/r_factor/climatology.py, decisions D69 and D84 of issue "
        f"#77), times K, LS, C and P; records read for the month: "
        f"{_records_text(reader)}"
    )


# --- values -------------------------------------------------------------------


def _not_covered(what: str) -> Missing:
    return Missing(
        reason="NO_COVERAGE",
        detail=(
            f"the daily series '{PRECIPITATION}' does not cover {what} from its first "
            "day to its last (C5.5)"
        ),
    )


def _range_missing() -> Missing:
    return Missing(reason="NOT_AVAILABLE", detail=RANGE_NOT_BUILT)


def _annual(ag_year: int, outcome: float | Missing, source: str) -> AnnualSoilLoss:
    common = {
        "indicator": INDICATOR,
        "direction": DIRECTION_OF[INDICATOR],
        "unit": UNIT_SOIL_LOSS_ANNUAL,
        "ag_year": ag_year,
    }
    if isinstance(outcome, Missing):
        return AnnualSoilLoss(value=None, missing=outcome, **common)
    return AnnualSoilLoss(
        value=outcome,
        provenance=PROVENANCE_OF_SOIL_LOSS,
        source=source,
        range_missing=_range_missing(),
        **common,
    )


def _monthly(
    ag_year: int, year: int, month: int, outcome: float | Missing, source: str
) -> MonthlySoilLoss:
    common = {
        "indicator": INDICATOR,
        "direction": DIRECTION_OF[INDICATOR],
        "unit": UNIT_SOIL_LOSS_MONTHLY,
        "year": year,
        "month": month,
        "ag_year": ag_year,
    }
    if isinstance(outcome, Missing):
        return MonthlySoilLoss(value=None, missing=outcome, **common)
    return MonthlySoilLoss(
        value=outcome,
        provenance=PROVENANCE_OF_SOIL_LOSS,
        source=source,
        range_missing=_range_missing(),
        **common,
    )


# --- the two routes -------------------------------------------------------------


@dataclass(frozen=True)
class _Inputs:
    """What a route is built from, once the years can be laid out."""

    calendar: RotationCalendar
    series: DailySeries
    soil_slope: SiteSoilSlope
    start_month: int
    ag_years: tuple[int, ...]
    parameters: dict[str, dict]
    repeated: RepeatedRotation  # the rotation over the years of the record (D47)


class _Route(Protocol):
    def year(self, ag_year: int) -> tuple[float | Missing, str]: ...

    def month(
        self, ag_year: int, year: int, month: int
    ) -> tuple[float | Missing, str]: ...


@dataclass(frozen=True)
class _MainRoute:
    """The route of the first release (docs/METHODS.md M1.2; D69, D84, USER-G).

    The annual value is ``equation.annual_soil_loss`` of the mean annual level
    of R, K, LS, the declared C and P: the same for every covered year, the
    variation between years being deferred. A monthly value is R of the month
    (the level times the climatological fraction of the month) times K, LS, C
    and P, so the months of a year add up to it (C1.2).
    """

    product: float | Missing
    source: str
    numbers: tuple[float, ...]
    r_by_month: ByYear | Missing
    monthly_reader: ParameterReader
    start_month: int

    def year(self, ag_year: int) -> tuple[float | Missing, str]:
        return self.product, self.source

    def month(self, ag_year: int, year: int, month: int) -> tuple[float | Missing, str]:
        prefix = (
            f"the soil loss of the month {_month_label(year, month)} is not computed"
        )
        problems: list[_Problem] = []
        if isinstance(self.product, Missing):
            problems.append(
                _Problem(
                    self.product.reason,
                    f"its factors are those of the annual product: {self.product.detail}",
                )
            )
        r_month: float | Missing
        if isinstance(self.r_by_month, Missing):
            r_month = self.r_by_month
        else:
            cell = self.r_by_month.get(ag_year, {}).get((year, month))
            r_month = (
                cell
                if isinstance(cell, (float, Missing))
                else Missing(
                    reason="NOT_COMPUTABLE",
                    detail="engine/erosion/r_factor/climatology.py holds no number "
                    "for the month",
                )
            )
        if isinstance(r_month, Missing):
            problems.append(
                _Problem(
                    r_month.reason,
                    f"R of the month is missing ({r_month.reason}: {r_month.detail})",
                )
            )
        if problems:
            return _combined(problems, prefix), ""
        assert isinstance(r_month, float)
        value = r_month * math.prod(self.numbers)
        if not math.isfinite(value):
            return (
                Missing(
                    reason="NOT_COMPUTABLE",
                    detail=f"{prefix}: the product is not a finite number",
                ),
                "",
            )
        return value, _monthly_source(self.source, self.monthly_reader)


def _monthly_erosivity_table(
    level: Parameter, inputs: _Inputs, reader: ParameterReader
) -> ByYear | Missing:
    """R by month through ``climatological_r_by_year_and_month`` (D69, D84).

    The twelve records of the climatology, then their fractions, then the
    level times the fraction. A record that cannot be read makes every month
    missing, naming it by id and scope and the part of M1.2 that needs it;
    records in different unit strings are not read.
    """
    records = [reader.read(pid, SCOPE) for pid in MONTHLY_EROSIVITY_IDS]
    problems = [
        problem
        for problem in (_missing_record(item, CLIMATOLOGY_PART) for item in records)
        if problem is not None
    ]
    if problems:
        return _combined(problems, "R by month")
    units = list(dict.fromkeys(_unit(item) for item in records))
    if len(units) > _FIRST:
        return Missing(
            reason=UNIT_NOT_ACCEPTED,
            detail=(
                "R by month: the twelve records of the monthly erosivity carry "
                f"different unit strings ({', '.join(repr(u) for u in units)}), so "
                "their fractions are not defined (OPEN 11 of "
                "engine/erosion/SOIL_LOSS.md)"
            ),
        )
    month_numbers = range(_FIRST, _MONTHS_IN_A_YEAR + _FIRST)
    fractions = r_factor.climatological_monthly_fractions(
        monthly_erosivity=dict(zip(month_numbers, (_number(i) for i in records)))
    )
    if isinstance(level.value, Missing):
        return Missing(
            reason="MISSING_INPUT",
            detail=f"R by month: {level.value.detail}; needed by {LEVEL_PART}",
        )
    return r_factor.climatological_r_by_year_and_month(
        mean_annual_r=level.value,
        mean_annual_r_unit=_unit(level),
        fractions=fractions,
        ag_years=inputs.ag_years,
        start_month=inputs.start_month,
    )


def _main_route(inputs: _Inputs) -> _MainRoute:
    reader = ParameterReader(inputs.parameters)
    level = reader.read(R_ID, SCOPE)
    r = _factor(level, ACCEPTED_UNITS.r)
    k = _factor(reader.read(K_ID, SCOPE), ACCEPTED_UNITS.k)
    ls_ = _ls_factor(inputs.soil_slope, reader)
    c = _factor(reader.read(C_ID, SCOPE), ACCEPTED_UNITS.c, extra=DECLARED_C)
    p = _factor(reader.read(P_ID, SCOPE), ACCEPTED_UNITS.p)
    product = _annual_product(r, k, ls_, c, p)
    source = _main_source(reader)
    monthly_reader = ParameterReader(inputs.parameters)
    table = _monthly_erosivity_table(level, inputs, monthly_reader)
    numbers = tuple(
        factor.value
        for factor in (k, ls_, c, p)
        if not isinstance(factor.value, Missing)
    )
    return _MainRoute(
        product=product,
        source=source,
        numbers=numbers,
        r_by_month=table,
        monthly_reader=monthly_reader,
        start_month=inputs.start_month,
    )


@dataclass(frozen=True)
class _DailyRoute:
    """The daily-index route, off the main path (D69, D84, USER-G): R through
    the daily erosivity index of r_factor/, C through c_factor/."""

    inputs: _Inputs
    reader: ParameterReader
    erosivity: _Erosivity
    k: Factor
    ls: Factor
    p: Factor

    def year(self, ag_year: int) -> tuple[float | Missing, str]:
        reader = self.reader.fork()
        start_month = self.inputs.start_month
        r = _r_of_year(self.erosivity, ag_year, start_month)
        c = _c_of_year(
            self.inputs.repeated, ag_year, start_month, self.erosivity, reader
        )
        return _annual_product(r, self.k, self.ls, c, self.p), _daily_source(reader)

    def month(self, ag_year: int, year: int, month: int) -> tuple[float | Missing, str]:
        return Missing(reason="NOT_AVAILABLE", detail=MONTHLY_NOT_FORMED), ""


def _daily_route(inputs: _Inputs) -> _DailyRoute:
    reader = ParameterReader(inputs.parameters)
    erosivity = _erosivity(inputs.series, inputs.start_month, reader)
    return _DailyRoute(
        inputs=inputs,
        reader=reader,
        erosivity=erosivity,
        k=_factor(reader.read(K_ID, SCOPE), ACCEPTED_UNITS.k),
        ls=_ls_factor(inputs.soil_slope, reader),
        p=_factor(reader.read(P_ID, SCOPE), ACCEPTED_UNITS.p),
    )


def _soil_loss(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    parameters: dict[str, dict],
    route_of: Callable[[_Inputs], _Route],
) -> SoilLossResults | Missing:
    """The years and months of the record, each from the route or its reason."""
    _check_types(calendar, climate, soil_slope, parameters)
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

    first_ag_year = _ag_year_of(series.start_date, start_month)
    last_ag_year = _ag_year_of(series.end_date, start_month)
    ag_years = tuple(range(first_ag_year, last_ag_year + _FIRST))
    infeasible: Missing | None = None
    route: _Route | None = None
    if not calendar.feasibility.feasible:
        infeasible = Missing(reason="NOT_COMPUTABLE", detail=INFEASIBLE)
    else:
        repeated = repeat_over_record(calendar, series.start_date, series.end_date)
        assert isinstance(repeated, RepeatedRotation)  # the start month is known
        assert repeated.ag_years == ag_years
        route = route_of(
            _Inputs(
                calendar=calendar,
                series=series,
                soil_slope=soil_slope,
                start_month=start_month,
                ag_years=ag_years,
                parameters=parameters,
                repeated=repeated,
            )
        )

    annual: list[AnnualSoilLoss] = []
    monthly: list[MonthlySoilLoss] = []
    for ag_year in ag_years:
        first_index = _index_of(ag_year, start_month)
        last_index = first_index + _MONTHS_IN_A_YEAR - _FIRST
        first = _first_day(*_month_at(first_index))
        last = _last_day(*_month_at(last_index))
        source = ""
        if infeasible is not None:
            outcome: float | Missing = infeasible
        elif not _covers(series, first, last):
            outcome = _not_covered(f"agricultural year {ag_year}")
        else:
            assert route is not None
            outcome, source = route.year(ag_year)
        annual.append(_annual(ag_year, outcome, source))
        for year, month in _months_of(ag_year, start_month):
            month_source = ""
            if infeasible is not None:
                month_outcome: float | Missing = infeasible
            elif not _covers(series, _first_day(year, month), _last_day(year, month)):
                month_outcome = _not_covered(f"the month {_month_label(year, month)}")
            else:
                assert route is not None
                month_outcome, month_source = route.month(ag_year, year, month)
            monthly.append(_monthly(ag_year, year, month, month_outcome, month_source))

    return SoilLossResults(annual=annual, monthly=monthly)


# --- the entry point and the route off the main path ----------------------------


def compute_soil_loss(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    parameters: dict[str, dict],
) -> SoilLossResults | Missing:
    """Soil loss of one rotation of one field (EP1), on the route of the first
    release (docs/METHODS.md M1.2; decisions D69 and D84 of issue #77, USER-G).

    ``parameters`` is the catalogue as ``params.catalogue.load_folder`` returns
    it, passed by keyword and with no default (Q3, D46, D56).

    Returns one ``Missing`` (reason ``MISSING_INPUT``) when the agricultural
    years cannot be laid out: the start month is missing, or the record has no
    daily ``precipitation`` series. Otherwise a ``SoilLossResults`` with every
    agricultural year of the record (D47) and its twelve months:

    - an infeasible calendar: every value ``NOT_COMPUTABLE``;
    - a year or month the series does not cover: ``NO_COVERAGE`` (C5.5);
    - every other year: ``equation.annual_soil_loss`` of the mean annual level
      of R, K, LS, the declared C and P, the same number for every year
      (``DERIVED``, with its source and the reason it has no range) when all
      five are present, otherwise its ``Missing``;
    - every other month: R of the month (the level times the climatological
      fraction of the month) times K, LS, C and P, or its ``Missing``: until
      the twelve records of the climatology exist, ``MISSING_INPUT`` naming them.

    Raises ``TypeError`` for an argument that is not of its type and
    ``ValueError`` when the arguments name different fields (G5).
    """
    return _soil_loss(calendar, climate, soil_slope, parameters, _main_route)


def compute_soil_loss_daily_index(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    parameters: dict[str, dict],
) -> SoilLossResults | Missing:
    """Soil loss on the daily-index route, off the main path. PROPOSED.

    Kept available while the first release takes the climatology route (D69,
    D84, USER-G): R of each agricultural year through the daily erosivity
    index of ``r_factor/`` (fractions and yearly ratios), C of each year
    through ``c_factor/`` (D45, PC-1) from the calendar. The same arguments,
    checks and layout as ``compute_soil_loss``; every covered month is
    ``NOT_AVAILABLE``. The runner never calls it. See SOIL_LOSS.md.
    """
    return _soil_loss(calendar, climate, soil_slope, parameters, _daily_route)
