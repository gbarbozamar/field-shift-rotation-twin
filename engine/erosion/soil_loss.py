"""Entry point EP1 of contracts/ENTRYPOINTS.md: ``compute_soil_loss``.

Unit l0/erosion-ep1-parameters (issue #154), on the mechanical form of #125.
The function lays out the agricultural years of the climate record (decision
D47 of issue #77) and their months. It takes the parameter catalogue as the
keyword argument ``parameters`` (Q3, D46, D56) and computes the factors of
RUSLE that the code already built can compute:

- ``LS`` through ``engine/erosion/ls.py``, from the slope of ``soil_slope``
  and coefficients read from ``parameters``;
- ``R``, ``K``, ``C`` and ``P`` from one record each of ``parameters``.

The annual soil loss of an agricultural year is ``equation.annual_soil_loss``
of the five factors, a number only where every factor is present. Every
monthly value is missing: the monthly erosivity fraction of M1.2 is not built.
See SOIL_LOSS.md in this folder.

Status: PROPOSED (blueprint section 3.7): the parameter identifiers and their
scope, the order of the checks, the reason of each value, the reading of a
slope unit and the format of every ``detail``.

Pure function (G1): no file, no network, no clock, no environment variable,
and the arguments are not changed. ``load_folder`` is never called. The only
integers are those of month arithmetic, listed in SOIL_LOSS.md.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import get_args

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
from engine.erosion import ls
from engine.erosion._parameters import Parameter, read_parameter, scope_text
from engine.erosion.equation import AcceptedUnits, Factor, annual_soil_loss

__all__ = ["compute_soil_loss"]

# The identifier of the indicator, read from the results model (C1.1).
(INDICATOR,) = get_args(AnnualSoilLoss.model_fields["indicator"].annotation)

# The quantity identifier of daily precipitation (decision D23 of issue #77),
# the only climate series the soil-loss method reads (docs/METHODS.md M1.2).
PRECIPITATION = "precipitation"

# --- parameters: PROPOSED identifiers and scope (SOIL_LOSS.md) ---------------

# The scope of every record EP1 reads: the empty scope, "no restriction
# stated" (params/README.md). PROPOSED; the scope words are OPEN.
SCOPE: dict[str, str] = {}

# R, K, C and P: one record each.
R_ID = "rusle_r_factor"
K_ID = "rusle_k_factor"
C_ID = "rusle_c_factor"
P_ID = "rusle_p_factor"

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
PARAMETER_IDS: tuple[str, ...] = (R_ID, K_ID, *LS_IDS, C_ID, P_ID)

# --- units ------------------------------------------------------------------

# The unit string the product accepts for each factor: R and K as decision
# D11 of issue #77 writes them (docs/METHODS.md M1.7); LS, C and P have no
# unit (M1.7), written "dimensionless" (contracts/CONVENTIONS.md C1.1).
DIMENSIONLESS = "dimensionless"
ACCEPTED_UNITS = AcceptedUnits(
    r="MJ mm ha-1 h-1 yr-1",
    k="t ha h ha-1 MJ-1 mm-1",
    ls=DIMENSIONLESS,
    c=DIMENSIONLESS,
    p=DIMENSIONLESS,
)

# The reason of a unit the engine does not accept: the code ls.py proposes
# (Q11 of contracts/ENTRYPOINTS.md is not decided).
UNIT_NOT_ACCEPTED = ls.REASON_UNIT_NOT_ACCEPTED

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
MONTHLY_NOT_BUILT = (
    "a monthly value needs the fraction of the annual erosivity that falls in the "
    "month, from the daily erosivity index of docs/METHODS.md M1.2, which is not "
    "built (blueprint section 8, Block 1)"
)
R_NOT_BUILT = (
    "the daily erosivity index of docs/METHODS.md M1.2, which gives the monthly "
    "fraction of R and its variation between years, is not built (blueprint "
    "section 8, Block 1)"
)
C_NOT_BUILT = (
    "the method that would compute C, the sub-factor equations of docs/METHODS.md "
    "M1.5 (decision D45 of issue #77), is not built"
)
RANGE_NOT_BUILT = (
    "how an uncertainty range passes through the product of docs/METHODS.md M1.1 "
    "is not built (C2.3; OPEN 5 of engine/erosion/EQUATION.md)"
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


def _covers(series: DailySeries, first: dt.date, last: dt.date) -> bool:
    return series.start_date <= first and last <= series.end_date


# --- the factors --------------------------------------------------------------


@dataclass(frozen=True)
class _Factors:
    """The five factors of M1.1 as ``equation.py`` takes them."""

    r: Factor
    k: Factor
    ls: Factor
    c: Factor
    p: Factor


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


def _ls_factor(soil_slope: SiteSoilSlope, parameters: dict[str, dict]) -> Factor:
    """``LS = L * S`` through ls.py, or why it is missing.

    Every input and every coefficient is looked at first. Any that is missing
    gives ``MISSING_INPUT`` naming each one (C3.3, G4); then a slope unit that
    cannot be read gives ``UNIT_NOT_ACCEPTED``; only then ls.py is called, and
    a ``Missing`` it returns is the factor's.
    """
    slope = soil_slope.slope_steepness
    length = soil_slope.slope_length
    read = {pid: read_parameter(parameters, pid, SCOPE) for pid in LS_IDS}

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


def _factors(soil_slope: SiteSoilSlope, parameters: dict[str, dict]) -> _Factors:
    def record(pid: str) -> Parameter:
        return read_parameter(parameters, pid, SCOPE)

    return _Factors(
        r=_factor(record(R_ID), ACCEPTED_UNITS.r, extra=R_NOT_BUILT),
        k=_factor(record(K_ID), ACCEPTED_UNITS.k),
        ls=_ls_factor(soil_slope, parameters),
        c=_factor(record(C_ID), ACCEPTED_UNITS.c, extra=C_NOT_BUILT),
        p=_factor(record(P_ID), ACCEPTED_UNITS.p),
    )


def _annual_product(factors: _Factors) -> float | Missing:
    return annual_soil_loss(
        r=factors.r,
        k=factors.k,
        ls=factors.ls,
        c=factors.c,
        p=factors.p,
        accepted_units=ACCEPTED_UNITS,
        unit_guard_reason=UNIT_NOT_ACCEPTED,
    )


def _source() -> str:
    """The source of a computed annual value. PROPOSED (question 11 of
    contracts/results/README.md is OPEN)."""
    scope = scope_text(SCOPE)
    return (
        "derived by engine.erosion.compute_soil_loss with the product of "
        "docs/METHODS.md M1.1: R, K, C and P from the parameter records "
        f"'{R_ID}', '{K_ID}', '{C_ID}' and '{P_ID}' with scope {scope}; LS from "
        "engine/erosion/ls.py with the slope of the soil-and-slope data and the "
        f"parameter records {', '.join(repr(pid) for pid in LS_IDS)} with scope {scope}"
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


def _annual(ag_year: int, outcome: float | Missing) -> AnnualSoilLoss:
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
        source=_source(),
        range_missing=Missing(reason="NOT_AVAILABLE", detail=RANGE_NOT_BUILT),
        **common,
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
    *,
    parameters: dict[str, dict],
) -> SoilLossResults | Missing:
    """Soil loss of one rotation of one field (EP1).

    ``parameters`` is the catalogue as ``params.catalogue.load_folder`` returns
    it, passed by keyword and with no default (Q3, D46, D56).

    Returns one ``Missing`` (reason ``MISSING_INPUT``) when the agricultural
    years cannot be laid out: the start month is missing, or the record has no
    daily ``precipitation`` series. Otherwise a ``SoilLossResults`` with every
    agricultural year of the record (D47) and its twelve months:

    - an infeasible calendar: every value ``NOT_COMPUTABLE``;
    - a year or month the series does not cover: ``NO_COVERAGE`` (C5.5);
    - every other month: ``NOT_AVAILABLE``, the monthly fraction of M1.2 is
      not built;
    - every other year: ``equation.annual_soil_loss`` of the five factors, a
      number (``DERIVED``, with its source and the reason it has no range)
      only when all five are present, otherwise its ``Missing``.

    Raises ``TypeError`` for an argument that is not of its type and
    ``ValueError`` when the arguments name different fields (G5).
    """
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

    infeasible: Missing | None = None
    if not calendar.feasibility.feasible:
        infeasible = Missing(reason="NOT_COMPUTABLE", detail=INFEASIBLE)
        product: float | Missing = infeasible
    else:
        product = _annual_product(_factors(soil_slope, parameters))
    monthly_not_built = Missing(reason="NOT_AVAILABLE", detail=MONTHLY_NOT_BUILT)

    def outcome_of(
        first: dt.date, last: dt.date, what: str, otherwise: float | Missing
    ) -> float | Missing:
        if infeasible is not None:
            return infeasible
        if not _covers(series, first, last):
            return _not_covered(what)
        return otherwise

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
                outcome_of(
                    _first_day(*_month_at(first_index)),
                    _last_day(*_month_at(last_index)),
                    f"agricultural year {ag_year}",
                    product,
                ),
            )
        )
        for year, month in _months_of(ag_year, start_month):
            missing = outcome_of(
                _first_day(year, month),
                _last_day(year, month),
                f"the month {_first_day(year, month).strftime('%Y-%m')}",
                monthly_not_built,
            )
            assert isinstance(missing, Missing)
            monthly.append(_monthly(ag_year, year, month, missing))

    return SoilLossResults(annual=annual, monthly=monthly)
