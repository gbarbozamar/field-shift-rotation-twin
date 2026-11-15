"""Entry point EP3 of contracts/ENTRYPOINTS.md: ``compute_water_deficit_exposure``.

Unit ``l1/water-ep3-parameters`` (issue #153), after the mechanical form of
issue #134. The entry point takes the parameter catalogue as the keyword
argument ``parameters`` (decisions D46 and D56 of issue #77, as
contracts/ENTRYPOINTS.md states them). For every day of the climate record it
chains the four internal parts of the water engine (decision D44):

1. the reference evapotranspiration of ``engine/water/et0/``;
2. the runoff by the Curve Number of ``engine/water/runoff/``;
3. the evaporation coefficient ``Ke`` from the surface-layer balance of
   ``engine/water/evaporation/``;
4. the one-layer daily balance of ``engine/water/balance/``.

Every constant and parameter of those parts is read from ``parameters`` by
its ``id`` and ``scope`` (``engine/water/_parameters.py``). Unit
``l1/water-ep3-identifiers`` (issue #191) reads every parameter of the
drafted water records: the basal crop coefficient by crop and stage, the
maximum root depth, the layer of the total evaporable water (D77, D78) and
the bounds of D82 (PC-4). Unit ``l1/water-crop-stages`` (issue #206) places
the four FAO-56 growth stages inside each crop period of the calendar from
stage lengths read by crop (``engine/water/stages.py``), and takes the basal
crop coefficient and the root depth of each crop day from its stage (D78); a
crop period whose stage lengths are missing keeps the behaviour of D79: its
days are missing with the reason. Unit ``l1/water-fallow-residue`` (issue
#217) builds the fallow day of decisions D110, D111, D115 and D116: on a day
with no crop the fallow is weed-free (no crop reaches the balance), the
surface layer takes the cover and wetted fractions of a day with no crop, and
its total evaporable water is reduced by the residue cover of the fallow,
read by the crop sown after it (``engine/water/fallow.py``). Unit
``l1/water-stage-tail-d135`` (issue #224) applies D135 and D136: the stages
are cut at the harvest when their lengths run past it, and the days after the
end of the late stage up to the harvest (the tail) are days with no living
crop, which take that fallow day unchanged. Unit
``l1/water-ep3-repeat-d47`` (issue #253) reads the crop, the stage, the
fallow and the tail of each day from the rotation repeated over the
agricultural years of the record by ``engine.calendar.repeat_over_record``
(D47, D109), as EP1 and EP4 do: a calendar whose dates lie outside the
record runs on the years of the record, a calendar moved by
``phase_calendar`` (D132) runs unchanged, and a component that starts before
the record and ends inside it is present from the first day of the record
with its declared dates (D141). No rule of the repetition is written in this
folder. Unit ``l1/water-open30-d`` builds decision D185 of issue #77, which
closes OPEN 30: when the total evaporable water of
a day (reduced on a fallow day, D110) is below the depletion the surface
layer carries, the depletion is kept and only the limit changes; the layer
starts the day at its limit, so it evaporates nothing, and the infiltration
refills the part above the limit first (``_layer_start``). The daily chain is
then reduced to one ``WaterDeficitExposure`` per agricultural year of the
record (D47). Unit ``l1/water-indicator-d157`` (issue #264) builds decision
D157: a year whose daily balance was computed on every day carries the ratio
of water transpired (the transpiration of the daily balance) to water
demanded (its demanded transpiration: the basal crop coefficient times the
reference evapotranspiration), each summed over the days of the year with a
living crop (D105, D106, D136). Its ``source`` starts with the label "whole
cycle, not critical period" (D105, D162). A year with no day with a living
crop is ``NOT_APPLICABLE``; any other year is missing with the reason that
applies. See EXPOSURE.md in this folder.

Status: PROPOSED (blueprint section 3.7): the order of the checks, the
reason of each item, the identifier and scope of each parameter, how the
crop of a day is read from the calendar, the provenance label, the source
text and the reason of the missing range of a value, and the format of every
``detail``.

Pure function (G1): no file, no network, no clock, no environment variable,
and the arguments are not changed. The only numbers are the one of month and
day arithmetic and the zero the demanded sum is compared with, listed in
EXPOSURE.md.
"""

from __future__ import annotations

import datetime as dt
import inspect
import math
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import get_args, get_type_hints

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.rotation_calendar import CalendarComponent, RotationCalendar
from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    UNIT_WATER_DEFICIT_EXPOSURE,
    Missing,
    ReasonCode,
    WaterDeficitExposure,
)
from engine.calendar.repeat import (
    RepeatedComponent,
    RepeatedRotation,
    repeat_over_record,
)
from engine.water import balance, evaporation, fallow
from engine.water._parameters import Catalogue, Scope, check_parameters
from engine.water.et0 import Et0Bounds, Et0Constants, PointUnits
from engine.water.et0 import (
    reference_evapotranspiration_from_climate_with_bounds as et0_days,
)
from engine.water.et0.quantities import (
    ACCEPTED_UNITS,
    CLIMATE_QUANTITIES,
    WIND_SPEED_2M,
)
from engine.water.runoff import (
    PRECIPITATION,
    PRECIPITATION_UNIT,
    CurveNumberConstants,
    PrecipitationValue,
    RunoffDayInput,
    RunoffDayResult,
    runoff_day,
)
from engine.water.stages import (
    STAGE_LENGTH_PARAMETERS,
    PlacedStages,
    by_stage,
    place_stages,
)

__all__ = ["compute_water_deficit_exposure"]

# The identifier of the indicator, read from the results model (C1.1).
(INDICATOR,) = get_args(WaterDeficitExposure.model_fields["indicator"].annotation)

# Every daily series the water chain reads: precipitation (decision D23; the
# series that marks the record, as in EP1, so that EP1 and EP3 list the same
# years, D47), then the five inputs of the reference evapotranspiration.
DAILY_INPUTS: tuple[str, ...] = (PRECIPITATION, *CLIMATE_QUANTITIES)

# The unit string each daily series must arrive in, transcribed by the parts
# from contracts/CLIMATE_QUANTITIES.md (CQ1 to CQ6), not chosen here.
ACCEPTED_DAILY_UNITS: dict[str, str] = {
    PRECIPITATION: PRECIPITATION_UNIT,
    **ACCEPTED_UNITS,
}

# The unit strings of the point of the series: those decision D55 of issue
# #77 sets for the climate adapter (latitude in decimal degrees, unit string
# `degree`; elevation in metres, unit string `m`). PROPOSED: the reference
# evapotranspiration accepts the point in the units the adapter delivers.
POINT_UNITS = PointUnits(latitude_decimal_degrees="degree", elevation="m")
POINT_VALUES: tuple[str, ...] = ("latitude", "elevation")  # longitude is not read

# The reason code the units guards of the parts are given. It is never
# emitted: the entry point checks every unit string before the chain runs,
# and a year whose inputs arrive in another unit string is answered without
# the chain (Q11 of contracts/ENTRYPOINTS.md is not decided). PROPOSED.
_UNIT_GUARD_REASON: ReasonCode = "MISSING_INPUT"

# --- parameter identifiers and scopes: PROPOSED -------------------------------
#
# Scope of a parameter of the site or of the method: the empty scope.
SITE: Scope = ()
# Scope of a parameter of a crop: the crop identifier of the calendar.
CROP_KEY = "crop"
# Scope of a parameter of a day on which the calendar places no crop.
NO_CROP: Scope = (("management", "no_crop"),)

# The reference evapotranspiration: the identifier of each constant is the
# one of the table of engine/water/et0/README.md, ``<group>.<field>``, with
# the dot written as an underscore (a record id holds no dot).
_ET0_GROUPS: dict[str, type] = get_type_hints(Et0Constants)
ET0_PARAMETERS: dict[str, tuple[str, ...]] = {
    group: tuple(item.name for item in fields(_ET0_GROUPS[group]))
    for group in (item.name for item in fields(Et0Constants))
}

# The two bounds of decision D82 (PC-4) the reference evapotranspiration
# applies, by the field of Et0Bounds and of its class. The identifiers are
# those of the drafted records (PROPOSED there), not the ones et0 README OPEN
# 19 proposes (`relative_shortwave_bound_upper_bound`,
# `wind_speed_bound_lower_bound`): the drafts name each bound after the
# equation it belongs to.
_BOUND_GROUPS: dict[str, type] = get_type_hints(Et0Bounds)
ET0_BOUND_PARAMETERS: dict[str, dict[str, str]] = {
    "relative_shortwave_bound": {
        "upper_bound": "net_longwave_relative_shortwave_maximum"
    },
    "wind_speed_bound": {"lower_bound": "penman_monteith_minimum_wind_speed"},
}

# The runoff: the field names of CurveNumberConstants, as its README table.
RUNOFF_PARAMETERS: tuple[str, ...] = tuple(
    item.name for item in fields(CurveNumberConstants)
)

# The surface layer: the constants of its daily step (and its initial
# depletion), the climate term of the upper limit, written ``upper_limit_``
# and the field, as its README table, and the two constants of the cover
# fraction. The minimum relative humidity is read as a parameter of the site
# because no daily series carries it (OPEN in EXPOSURE.md).
#
# The total evaporable water is not read: it is computed from the surface
# layer by ``evaporation.total_evaporable_water`` (FAO-56 chapter 7, D77), so
# it is left out of the constants read by name.
TOTAL_EVAPORABLE_WATER = "total_evaporable_water"
SURFACE_LAYER_PARAMETERS: tuple[str, ...] = tuple(
    name
    for name, parameter in inspect.signature(
        evaporation.run_surface_layer
    ).parameters.items()
    if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    and name != TOTAL_EVAPORABLE_WATER
)
# The operands of the total evaporable water, by the argument of
# ``evaporation.total_evaporable_water`` each is passed as. The depth of the
# layer and the two constants carry the identifiers of the drafted records
# (D77); the two water contents of the layer are new identifiers (no record
# is drafted for them; the soil's hydraulic profile of D77 would give them).
TOTAL_EVAPORABLE_WATER_PARAMETERS: dict[str, str] = {
    "field_capacity_water_content": "field_capacity_water_content",
    "wilting_point_water_content": "wilting_point_water_content",
    "surface_layer_depth": "evaporation_layer_depth",
    "wilting_point_weight": "total_evaporable_water_wilting_point_weight",
    "unit_factor": "total_evaporable_water_unit_factor",
}
UPPER_LIMIT_FIELDS: tuple[str, ...] = tuple(
    item.name for item in fields(evaporation.UpperLimitClimateConstants)
)
UPPER_LIMIT_PREFIX = "upper_limit_"
INITIAL_DEPLETION = "initial_depletion"
MINIMUM_CROP_COEFFICIENT = "minimum_crop_coefficient"
MINIMUM_RELATIVE_HUMIDITY = "minimum_relative_humidity"

# The balance: its column.
COLUMN_CAPACITY = "column_capacity"
COLUMN_DEPTH = "column_depth"
INITIAL_STORAGE = "initial_storage"

# Per crop and growth stage, and per day with no crop: the basal crop
# coefficient of FAO-56 Table 17, one value per stage (D78). The stage words
# are those of the drafted records (PROPOSED; the words allowed under the
# scope key `stage` are question 4 of params/README.md, OPEN).
BASAL_CROP_COEFFICIENT = "basal_crop_coefficient"
STAGE_KEY = "stage"
STAGES: tuple[str, ...] = ("initial", "mid", "end")
# Per crop, and per day with no crop.
CROP_HEIGHT = "crop_height"
CURVE_NUMBER = "curve_number"
# Per crop only since unit #217: on a day with no crop the cover fraction is
# read, not computed from the basal coefficient (D110).
COVER_FRACTION_EXPONENT = "cover_fraction_exponent"
# Per crop only: the crop of a balance day (CropDay). The root depth of a
# crop day grows by stage (engine/water/stages.py, ``by_stage``) from the
# initial root depth to the maximum root depth (D78, provisional curves of
# FAO-56 Annex 8; the identifier of the initial depth is PROPOSED by unit
# #206, no record is drafted for it).
ROOT_DEPTH = "maximum_root_depth"
INITIAL_ROOT_DEPTH = "initial_root_depth"
READILY_AVAILABLE_FRACTION = "readily_available_fraction"

# Every parameter the chain reads, by the scope it is looked up with; the
# table "Parameters" of EXPOSURE.md lists the same, and a test checks it.
SITE_PARAMETERS: tuple[str, ...] = (
    *(f"{group}_{name}" for group, names in ET0_PARAMETERS.items() for name in names),
    *(name for names in ET0_BOUND_PARAMETERS.values() for name in names.values()),
    *RUNOFF_PARAMETERS,
    *SURFACE_LAYER_PARAMETERS,
    *TOTAL_EVAPORABLE_WATER_PARAMETERS.values(),
    *(f"{UPPER_LIMIT_PREFIX}{name}" for name in UPPER_LIMIT_FIELDS),
    MINIMUM_CROP_COEFFICIENT,
    MINIMUM_RELATIVE_HUMIDITY,
    COLUMN_CAPACITY,
    COLUMN_DEPTH,
    INITIAL_STORAGE,
)
# Looked up with the crop of the day and each stage of STAGES, or with
# NO_CROP on a day with no crop.
STAGE_PARAMETERS: tuple[str, ...] = (BASAL_CROP_COEFFICIENT,)
# Looked up with the crop of the day, or with NO_CROP on a day with no crop.
DAY_PARAMETERS: tuple[str, ...] = (
    CROP_HEIGHT,
    CURVE_NUMBER,
)
# Looked up with the crop of the day only: the exponent of the cover fraction,
# the crop of the balance, the initial root depth and the length of each
# growth stage (issue #206).
CROP_PARAMETERS: tuple[str, ...] = (
    COVER_FRACTION_EXPONENT,
    ROOT_DEPTH,
    READILY_AVAILABLE_FRACTION,
    INITIAL_ROOT_DEPTH,
    *STAGE_LENGTH_PARAMETERS.values(),
)

# --- a day with no crop: the fallow of D110, D111, D115, D116 (unit #217) ------
#
# Looked up with NO_CROP: the cover fraction and the wetted fraction of the
# surface layer on a fallow day (D110 gives `fc = 0` and `fw = 1`; the values
# are records, PROPOSED identifiers). The wetted fraction of a day with a crop
# keeps the record of the site.
COVER_FRACTION = "cover_fraction"
WETTED_FRACTION = "wetted_fraction"
FALLOW_PARAMETERS: tuple[str, ...] = (COVER_FRACTION, WETTED_FRACTION)
# Looked up with the empty scope on the first fallow day: the two constants of
# the reduction of the total evaporable water by an organic mulch (D110,
# FAO-56 chapter 11: "5 % for each 10 %" of the surface covered). PROPOSED.
MULCH_REDUCTION = "mulch_total_evaporable_water_reduction"
MULCH_COVER_INCREMENT = "mulch_cover_increment"
FALLOW_SITE_PARAMETERS: tuple[str, ...] = (MULCH_REDUCTION, MULCH_COVER_INCREMENT)
# Looked up with NO_CROP and the crop that follows the fallow: the surface
# residue cover of the fallow, one value per fallow (D110, D115), the one
# record both engines read (D116). PROPOSED: the identifier is the name of the
# argument of the surface-cover sub-factor of engine/erosion/c_factor/.
SURFACE_RESIDUE_COVER = "surface_residue_cover"
FALLOW_COVER_PARAMETERS: tuple[str, ...] = (SURFACE_RESIDUE_COVER,)


def fallow_scope(following: str) -> Scope:
    """The scope of the cover of a fallow: no crop, and the crop sown after it."""
    return (*NO_CROP, (CROP_KEY, following))


# Day and month arithmetic (C5.1, C5.3): months and days counted from one.
_FIRST = 1
_ONE_DAY = dt.timedelta(days=_FIRST)

# --- detail texts: PROPOSED, English for developers -------------------------

START_MONTH_MISSING = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the agricultural years cannot be laid out; one item for the "
    "whole rotation is returned in their place (EP3, Q4)"
)
RECORD_MISSING = (
    f"the climate record has no daily series with quantity '{PRECIPITATION}' "
    "(decision D23 of issue #77), so the agricultural years of the record cannot "
    "be laid out (decision D47 of issue #77; G4, third row); one item for the "
    "whole rotation is returned in their place"
)
INFEASIBLE = (
    "the rotation calendar is infeasible (feasibility.feasible is false), so no "
    "value that depends on it is computed (G4, first row)"
)
MIXED_TIME_ZONES = (
    "the daily series the water engine reads ("
    + ", ".join(f"'{name}'" for name in DAILY_INPUTS)
    + ") do not share one time zone, and an engine never combines them (C6.3; "
    "G4, sixth row)"
)
# What the definition of the indicator still leaves open after D157. The name
# is kept: validation/test_chain_examples.py (lane L0) reads this constant.
DEFINITION_INCOMPLETE = (
    "the definition of the indicator is still incomplete (C1.4): the critical "
    "period of each crop is not defined, so the ratio of water transpired to "
    "water demanded is taken over the whole cycle of each crop (decisions D105 "
    "and D157 of issue #77), and the state of the balance that the descriptive "
    "measures use is not defined"
)

# --- the indicator: the ratio of D157 -----------------------------------------
#
# The label of the window (D105), written verbatim at the start of the
# ``source`` of every value (D162): the results contract has no field for it.
WINDOW_LABEL = "whole cycle, not critical period"
# PROPOSED (C4.1, C4.3): the ratio is read from a daily balance that is run
# through time steps, so it carries the label of a simulated value.
PROVENANCE = "SIMULATED"
# PROPOSED: the reason of the missing range, as EP1 gives it for its value.
RANGE_NOT_BUILT = (
    "no uncertainty range is computed: one call is one scenario, and how a range "
    "passes through the daily water balance is not built (C2.3, Q6 of "
    "contracts/ENTRYPOINTS.md, OPEN 44 of engine/water/EXPOSURE.md)"
)
# The reason the daily balance gives a crop quantity on a day with no crop.
NO_CROP_ON_THE_DAY = "NOT_APPLICABLE"
# The demanded sum of a year must lie above this for the ratio to exist.
_ZERO = 0
CROP_UNKNOWN = (
    "the crop of the day is not known: the day lies before the first cycle of "
    "the rotation repeated over the agricultural years of the climate record "
    "(decisions D47 and D109 of issue #77, engine/calendar/repeat.py), and no "
    "component of the cycle before it has an end date inside the record "
    "(decision D141), so the calendar does not describe the day: nothing is "
    "laid out before the first cycle (point 6 of engine/calendar/repeat.py, "
    "OPEN 5 of engine/water/EXPOSURE.md)"
)
CROP_DATES_MISSING = (
    "the crop of the day is not known: a component of the calendar has a "
    "missing date, so the days it covers are not known, within its cycle of "
    "the rotation repeated over the record (point 7 of "
    "engine/calendar/repeat.py)"
)
REPETITION_NOT_LAID_OUT = (
    "engine/calendar/repeat.py did not repeat the calendar over the years of "
    "the record although its start month is known (D47)"
)
REPETITION_OTHER_YEARS = (
    "engine/calendar/repeat.py laid out other agricultural years than EP3 did "
    "from the same record and start month (D47)"
)
STAGE_UNKNOWN = (
    "the growth stage of the day is not known: the calendar carries no growth "
    "stage and a stage length of the crop has no value in parameters (the "
    "parameters are named in their own item, issue #206), so neither the basal "
    "crop coefficient of the day (one value per stage, FAO-56 Table 17, "
    "decision D78 of issue #77) nor its root depth (the root growth of FAO-56 "
    "Annex 8, D78) can be taken, and missing stages stay missing (decision D79 "
    "of issue #77)"
)
CROPS_OVERLAP = (
    "two components of the calendar cover the day, and the water chain takes "
    "one crop per day"
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
    check_parameters(parameters)


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


# --- agricultural years (C5.3, D47) -------------------------------------------


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - _FIRST


def _first_day(ag_year: int, start_month: int) -> dt.date:
    return dt.date(ag_year, start_month, _FIRST)


def _last_day(ag_year: int, start_month: int) -> dt.date:
    return _first_day(ag_year + _FIRST, start_month) - _ONE_DAY


def _covers(series: DailySeries, first: dt.date, last: dt.date) -> bool:
    return series.start_date <= first and last <= series.end_date


def _mixed_time_zones(series: list[DailySeries]) -> bool:
    """More than one time zone among the series (C6.3); the list is not empty."""
    time_zones = {item.time_zone for item in series}
    return time_zones != {min(time_zones)}


def _days(first: dt.date, last: dt.date) -> list[dt.date]:
    days = []
    day = first
    while day <= last:
        days.append(day)
        day += _ONE_DAY
    return days


# --- small conversions ---------------------------------------------------------


def _as_results_missing(missing: InputsMissing) -> Missing:
    """The same reason and detail, in the ``Missing`` of contracts/results/models.py."""
    return Missing(reason=missing.reason, detail=missing.detail)


def _series_values(series: DailySeries | None) -> dict[dt.date, float | Missing]:
    """The number, or the missing value, of each day of one series."""
    if series is None:
        return {}
    return {
        day.date: (
            day.value if day.missing is None else _as_results_missing(day.missing)
        )
        for day in series.days
    }


def _day_value(
    values: dict[dt.date, float | Missing], name: str, present: bool, day: dt.date
) -> float | Missing:
    if day in values:
        return values[day]
    why = (
        f"the daily series '{name}' does not cover this day"
        if present
        else f"the climate record has no daily series '{name}'"
    )
    return Missing(reason="MISSING_INPUT", detail=why)


def _unit_problems(
    climate: SiteClimate, by_quantity: dict[str, DailySeries]
) -> list[str]:
    """Every series, and every value of the point, in a unit string the parts do not accept.

    Nothing is converted (C1.1). A value of the point that is missing is not
    checked: the reference evapotranspiration reports it with its own reason.
    """
    problems = [
        f"the daily series '{name}' is in the unit '{series.unit}', not in the "
        f"accepted unit '{ACCEPTED_DAILY_UNITS[name]}'"
        for name, series in by_quantity.items()
        if series.unit != ACCEPTED_DAILY_UNITS[name]
    ]
    accepted = {
        "latitude": POINT_UNITS.latitude_decimal_degrees,
        "elevation": POINT_UNITS.elevation,
    }
    for name in POINT_VALUES:
        value = getattr(climate.point, name)
        if value.missing is None and value.unit != accepted[name]:
            problems.append(
                f"the {name} of the point of the climate record is in the unit "
                f"'{value.unit}', not in the accepted unit '{accepted[name]}' "
                "(decision D55 of issue #77)"
            )
    return problems


# --- the rotation over the record, and the crop of each day ---------------------


def _over_record(calendar: RotationCalendar, record: DailySeries) -> RepeatedRotation:
    """The calendar repeated over the agricultural years of the record.

    The repetition is ``engine.calendar.repeat_over_record`` (D47, D109), on
    the dates of the ``precipitation`` series, the series that marks the
    record for EP1 too; no rule of it is written here, and it is called once,
    with the record as it is. A calendar moved by ``phase_calendar`` (D132)
    is repeated like any other. Nothing is laid out past the record: a cycle
    that does not fit whole is cut at its end (D109), so a component sown
    after the last day of the record's years is not known here.

    Raises ``ValueError``, as EP1 does, if the helper does not lay out the
    agricultural years this entry point lists from the same record and start
    month.
    """
    start_month = calendar.ag_year_start.month
    repeated = repeat_over_record(calendar, record.start_date, record.end_date)
    if not isinstance(repeated, RepeatedRotation):
        raise ValueError(REPETITION_NOT_LAID_OUT)
    years = range(
        _ag_year_of(record.start_date, start_month),
        _ag_year_of(record.end_date, start_month) + _FIRST,
    )
    if repeated.ag_years != tuple(years):
        raise ValueError(REPETITION_OTHER_YEARS)
    return repeated


def _earliest(component: RepeatedComponent) -> dt.date:
    """The first day a component can cover: its start, else its cycle's start
    (point 7 of engine/calendar/repeat.py)."""
    return component.start if component.start is not None else component.calendar_start


def _latest(component: RepeatedComponent) -> dt.date:
    """The last day a component can cover: its end, else the day before the
    next cycle starts (point 7 of engine/calendar/repeat.py)."""
    return component.end if component.end is not None else component.cycle_last_day


def _why_dates_are_missing(components: list[CalendarComponent]) -> dict[str, str]:
    """For each component with a missing date, which date and the reason the
    calendar gives for it (C3.2), as one text."""
    texts: dict[str, str] = {}
    for component in components:
        reasons: dict[str, list[str]] = {}
        for edge, value in (("start", component.start), ("end", component.end)):
            if value.date is not None:
                continue
            why = "no reason given"
            if value.missing is not None:
                why = value.missing.reason
                if value.missing.detail is not None:
                    why = f"{why}: {value.missing.detail}"
            reasons.setdefault(why, []).append(edge)
        if reasons:
            texts[component.component_id] = "; ".join(
                f"{' and '.join(edges)} date {why}" for why, edges in reasons.items()
            )
    return texts


def _component_of_day(
    calendar: RotationCalendar, repeated: RepeatedRotation
) -> Callable[[dt.date], RepeatedComponent | None | Missing]:
    """The component on the field on a day, ``None`` for a day with no crop, or why it is not known.

    PROPOSED, as EP1 reads it (``_covering`` of engine/erosion/soil_loss.py).
    The day is a day of the record, so it lies inside the agricultural years
    the rotation is repeated over (D47). It takes the one component of the
    repeated rotation whose dates cover it, in whichever cycle; a component
    that starts before the record and ends inside it is one of them, with its
    declared dates (the lead-in of ``repeat_over_record``, D141), so it is
    present from the first day of the record. No component when none can
    cover the day. Not known (``MISSING_INPUT``) for a day before the first
    cycle that the lead-in does not describe, and for a day a component with
    a missing date could cover, within its cycle (the detail names the
    component and repeats the reason the calendar gives for the date, so a
    crossing component ``phase_calendar`` could not place names D141). Two
    components on one day are not computed (``NOT_COMPUTABLE``).
    """
    dated = [
        component
        for component in repeated.components
        if component.start is not None and component.end is not None
    ]
    undated = [
        component
        for component in repeated.components
        if component.start is None or component.end is None
    ]
    why = _why_dates_are_missing(calendar.components)

    def component_of(day: dt.date) -> RepeatedComponent | None | Missing:
        if day < repeated.described_from:
            return Missing(reason="MISSING_INPUT", detail=CROP_UNKNOWN)
        covering = [item for item in dated if item.start <= day <= item.end]
        if len(covering) == _FIRST:
            (only,) = covering
            return only
        if covering:
            return Missing(reason="NOT_COMPUTABLE", detail=CROPS_OVERLAP)
        possible = dict.fromkeys(
            item.component_id
            for item in undated
            if _earliest(item) <= day <= _latest(item)
        )
        if possible:
            names = ", ".join(
                f"component {name!r} ({why.get(name, 'a date is missing')})"
                for name in possible
            )
            return Missing(
                reason="MISSING_INPUT", detail=f"{CROP_DATES_MISSING}: {names}"
            )
        return None

    return component_of


def _following_crop(
    repeated: RepeatedRotation,
) -> Callable[[dt.date], str | Missing]:
    """The crop sown after a fallow day (``fallow.following_crop``), read from
    the rotation repeated over the record (``_over_record``).

    A component with a start date is a sowing. One without a start date can
    be sown from the start of its cycle to its last possible day (point 7 of
    engine/calendar/repeat.py); ``fallow.following_crop`` answers a fallow it
    could follow as not known. Only the components the helper lays out are
    read: the fallow after the last sowing laid out, whose next sowing lies
    after the record, has no following crop (``MISSING_INPUT``, OPEN 41 of
    EXPOSURE.md). No component is placed here.
    """
    return fallow.following_crop(
        [
            (component.start, component.crop_id)
            for component in repeated.components
            if component.start is not None
        ],
        [
            (component.calendar_start, _latest(component), component.component_id)
            for component in repeated.components
            if component.start is None
        ],
    )


@dataclass(frozen=True)
class Growth:
    """The basal crop coefficient and the root depth of one day with a crop,
    each taken from the growth stage of the day."""

    basal_crop_coefficient: float
    root_depth: float


def _growth_of_day(
    catalogue: Catalogue,
) -> Callable[[dt.date, RepeatedComponent], Growth | Missing | None]:
    """The basal crop coefficient and root depth of a day with a crop, or why they are not known.

    PROPOSED (issues #206 and #253). The day lies in the period of the one
    dated component of the repeated rotation that carries the crop
    (``_component_of_day`` gives a component only then). The four stage
    lengths of the crop are read by crop (``STAGE_LENGTH_PARAMETERS``) once
    per component and cycle, on the first day of it the chain meets, and the
    stages are placed from the start of the component, its sowing
    (``stages.place_stages``), with the dates the repetition gives it. A
    component that starts before the record (D141) keeps its declared sowing,
    so its first day in the record is the day of its stages counted from that
    sowing; nothing of the days before the record is computed.

    - a stage length with no value: every day of the period is
      ``MISSING_INPUT`` with STAGE_UNKNOWN (D79), and the missing records are
      named by the catalogue (D56);
    - stages that cannot be placed: ``NOT_COMPUTABLE``, as ``place_stages``
      says why (a stage length that is not a whole number of days);
    - a day of the tail, after the end of the late stage and up to the
      harvest (D135, D136): ``None``, a day with no living crop, which the
      chain treats as a day with no crop. Stages that run past the harvest
      are cut there by ``place_stages``.

    Otherwise the basal crop coefficient of the day is ``stages.by_stage`` of
    the three records of FAO-56 Table 17 (D78), and the root depth is
    ``stages.by_stage`` of ``initial_root_depth`` at the initial value and
    ``maximum_root_depth`` at the mid and end values (D78, provisional
    curves). A record the stage of the day needs that is missing makes the
    day ``MISSING_INPUT``, naming it.
    """
    placed: dict[tuple[int, str], PlacedStages | Missing] = {}

    def growth(day: dt.date, component: RepeatedComponent) -> Growth | Missing | None:
        scope: Scope = ((CROP_KEY, component.crop_id),)
        key = (component.cycle, component.component_id)
        if key not in placed:
            lengths = {
                stage: catalogue.value(parameter_id, scope, day)
                for stage, parameter_id in STAGE_LENGTH_PARAMETERS.items()
            }
            numbers = {
                stage: value
                for stage, value in lengths.items()
                if not isinstance(value, Missing)
            }
            placed[key] = (
                place_stages(
                    component.start,
                    component.end,
                    numbers,
                    what=f"component '{component.component_id}'",
                )
                if len(numbers) == len(lengths)
                else Missing(reason="MISSING_INPUT", detail=STAGE_UNKNOWN)
            )
        stages = placed[key]
        if isinstance(stages, Missing):
            return stages
        if day in stages.tail:
            # After maturity: no living crop (D136).
            return None
        stage_day = stages[day]
        kcb = by_stage(
            stage_day,
            *(
                catalogue.value(
                    BASAL_CROP_COEFFICIENT, (*scope, (STAGE_KEY, stage)), day
                )
                for stage in STAGES
            ),
        )
        maximum = catalogue.value(ROOT_DEPTH, scope, day)
        root_depth = by_stage(
            stage_day,
            catalogue.value(INITIAL_ROOT_DEPTH, scope, day),
            maximum,
            maximum,
        )
        absent = [item for item in (kcb, root_depth) if isinstance(item, Missing)]
        if absent:
            return Missing(
                reason="MISSING_INPUT",
                detail="; ".join(item.detail for item in absent),
            )
        return Growth(basal_crop_coefficient=kcb, root_depth=root_depth)

    return growth


# --- the daily chain -----------------------------------------------------------


@dataclass(frozen=True)
class ChainDay:
    """One day of the chain: what each part gave, each a number or missing."""

    date: dt.date
    precipitation: float | Missing
    reference_evapotranspiration: float | Missing
    runoff: RunoffDayResult
    surface_layer: evaporation.DayResult
    # The depletion of the surface layer carried to the next day: the
    # depletion at the end of the day, plus the part above the total
    # evaporable water of the day that the infiltration has not refilled yet
    # (``_layer_start``; decision D185 of issue #77).
    surface_depletion_carried: float | Missing
    balance: balance.DayResult


class _Notes:
    """Problems of the chain that are not a parameter, each with the first day it was met."""

    def __init__(self) -> None:
        self._first: dict[str, dt.date] = {}

    def note(self, missing: Missing, day: dt.date) -> None:
        text = f"{missing.reason}: {missing.detail}"
        self._first.setdefault(text, day)

    def until(self, last: dt.date) -> list[str]:
        return [text for text, day in self._first.items() if day <= last]


def _guarded(
    what: str,
    notes: _Notes,
    day: dt.date,
    function: Callable[..., object],
    *args,
    **kwargs,
) -> object:
    """Call a part; a value it refuses (``ValueError``) is a missing value, not an error.

    The parts raise ``ValueError`` for a number outside what they accept (a
    negative depth, a root depth below the column, ...). Here that number
    comes from the catalogue or the climate record, not from a defect of the
    caller of EP3, so it is answered by G4: ``NOT_COMPUTABLE`` (the method
    does not cover the case), naming the part and its message. PROPOSED.
    """
    try:
        return function(*args, **kwargs)
    except ValueError as error:
        missing = Missing(
            reason="NOT_COMPUTABLE", detail=f"{what} refuses a value: {error}"
        )
        notes.note(missing, day)
        return missing


def _missing_result(
    result_type: type, quantities: tuple[str, ...], day: dt.date, missing: Missing
):
    return result_type(date=day, **{name: missing for name in quantities})


class _State:
    """The state a part carries from one day to the next, and what made it unknown.

    As ``run_balance`` and ``run_surface_layer`` carry it: once the state at
    the end of a day is missing, every later day starts from a missing state
    whose detail names the first cause.
    """

    def __init__(self, initial: float | Missing, name: str) -> None:
        self.name = name
        self.cause: str | None = None
        if isinstance(initial, Missing):
            self.cause = f"initial {name} ({initial.reason})"
            initial = Missing(
                reason="MISSING_INPUT", detail=f"missing since: {self.cause}"
            )
        self.value: float | Missing = initial

    def carry(self, end: float | Missing, day: dt.date) -> None:
        if isinstance(end, Missing):
            if self.cause is None:
                self.cause = end.detail
            self.value = Missing(
                reason="MISSING_INPUT",
                detail=f"{self.name} after {day.isoformat()}, missing since: {self.cause}",
            )
        else:
            self.value = end


def _site(catalogue: Catalogue, parameter_id: str, day: dt.date) -> float | Missing:
    return catalogue.value(parameter_id, SITE, day)


def _total_evaporable_water(
    catalogue: Catalogue, notes: _Notes, start: dt.date
) -> float | Missing:
    """The total evaporable water of the surface layer, computed from its operands.

    The operands are read from the catalogue (TOTAL_EVAPORABLE_WATER_PARAMETERS)
    and passed to ``evaporation.total_evaporable_water``. A missing operand is
    named by the catalogue. A value the part does not compute (below zero, not
    finite) or refuses (a negative operand) is ``NOT_COMPUTABLE`` and is noted,
    because no parameter names it. PROPOSED.
    """
    operands = {
        argument: _site(catalogue, parameter_id, start)
        for argument, parameter_id in TOTAL_EVAPORABLE_WATER_PARAMETERS.items()
    }
    what = "the total evaporable water"
    try:
        value = evaporation.total_evaporable_water(**operands)
    except ValueError as error:
        value = Missing(
            reason="NOT_COMPUTABLE", detail=f"{what} refuses a value: {error}"
        )
    if isinstance(value, Missing) and value.reason == "NOT_COMPUTABLE":
        notes.note(
            Missing(reason=value.reason, detail=f"{what}: {value.detail}"), start
        )
    return value


@dataclass(frozen=True)
class FallowSurface:
    """What the surface layer takes on a fallow day (D110), each a number or missing."""

    cover_fraction: float | Missing
    wetted_fraction: float | Missing
    total_evaporable_water: float | Missing
    readily_evaporable_water: float | Missing


def _fallow_surface(
    catalogue: Catalogue,
    notes: _Notes,
    day: dt.date,
    following: str | Missing,
    total_evaporable_water: float | Missing,
    readily_evaporable_water: float | Missing,
) -> FallowSurface:
    """The cover fraction, wetted fraction and evaporable waters of a fallow day.

    PROPOSED (unit #217, choices 18 to 21 of EXPOSURE.md). D110: on a fallow
    day ``fc`` and ``fw`` are the records of a day with no crop; the total
    evaporable water is reduced by the surface residue cover of the fallow
    (``fallow.mulched_total_evaporable_water``), read by the crop that
    follows the fallow; the readily evaporable water is not above it. A
    missing record is named by the catalogue (D56); a fallow with no crop
    after it, or a reduction the method does not compute, is a ``chain``
    item.
    """
    if isinstance(following, Missing):
        notes.note(following, day)
        cover: float | Missing = following
    else:
        cover = catalogue.value(SURFACE_RESIDUE_COVER, fallow_scope(following), day)
    total = fallow.mulched_total_evaporable_water(
        total_evaporable_water,
        cover,
        reduction_per_increment=_site(catalogue, MULCH_REDUCTION, day),
        cover_increment=_site(catalogue, MULCH_COVER_INCREMENT, day),
    )
    if isinstance(total, Missing) and total.reason == "NOT_COMPUTABLE":
        notes.note(total, day)
    return FallowSurface(
        cover_fraction=catalogue.value(COVER_FRACTION, NO_CROP, day),
        wetted_fraction=catalogue.value(WETTED_FRACTION, NO_CROP, day),
        total_evaporable_water=total,
        readily_evaporable_water=fallow.readily_evaporable_water_not_above(
            readily_evaporable_water, total
        ),
    )


@dataclass(frozen=True)
class LayerStart:
    """How the surface-layer step of a day starts (``_layer_start``)."""

    # The depletion the step starts from, within the total of the day.
    depletion: float | Missing
    # The precipitation the step is given: the precipitation of the day, less
    # the infiltration that refilled the part of the depletion above the total.
    precipitation: float | Missing
    # The part of the depletion above the total that the infiltration of the
    # day leaves; ``None`` when the depletion carried in is within the total.
    above: float | None


def _layer_start(
    depletion: float | Missing,
    total: float | Missing,
    layer_total: float | Missing,
    precipitation: float | Missing,
    runoff: float | Missing,
) -> LayerStart:
    """The start of the surface-layer step when the total may be below the depletion.

    Decision D185 of issue #77, which closes OPEN 30. The
    depletion of the surface layer is the evaporation accumulated since the
    layer was last wetted (FAO-56 chapter 7, Eq. 77); its total evaporable
    water, the limit at which evaporation stops (Eq. 78), is lower on a fallow
    day than on a day with a crop (D110). When the depletion carried into a
    day is above the total of the day, it is kept: the step starts at the
    total, its limit, so the layer evaporates nothing that day (``Kr`` is
    zero, or no room is left when the readily evaporable water equals the
    total), and on a day with no crop the column is given no evaporation
    either (``_column_evaporation_coefficient``); the infiltration of the day (the precipitation less the runoff the
    step applies, never more than the precipitation) refills the part above
    the total first, and only what is left of it is given to the step. What
    the infiltration has not refilled is carried to the next day on top of
    the depletion at the end of the day. No water is created or removed in the
    surface layer: across the change, the change of the carried depletion is
    the evaporation less the infiltration plus the percolation. When the total
    rises again (a day with a crop after a fallow), the depletion is kept as
    it is. The precipitation of the column balance is not changed.

    The rule applies only to a depletion within ``layer_total``, the total
    evaporable water of the layer before any residue (the one of a day with
    a crop): the chain never carries more than that, so a depletion above it
    can only come from the record ``initial_depletion``, and it is passed to
    the step unchanged, which refuses it (``NOT_COMPUTABLE``, choice 12), as
    before this unit.
    """
    if (
        isinstance(depletion, Missing)
        or isinstance(total, Missing)
        or isinstance(layer_total, Missing)
        or depletion <= total
        or depletion > layer_total
    ):
        return LayerStart(depletion=depletion, precipitation=precipitation, above=None)
    above = depletion - total
    if isinstance(precipitation, Missing) or isinstance(runoff, Missing):
        # The step answers the missing input of the day.
        return LayerStart(depletion=total, precipitation=precipitation, above=above)
    infiltration = precipitation - min(runoff, precipitation)
    refill = min(above, infiltration)
    return LayerStart(
        depletion=total, precipitation=precipitation - refill, above=above - refill
    )


def _column_evaporation_coefficient(
    surface: evaporation.DayResult,
    start: LayerStart,
    total: float | Missing,
    no_crop: bool,
) -> float | Missing:
    """The evaporation coefficient the column balance is given (D185).

    As the surface layer gives it (choice 10), except on a day with no crop
    whose step starts at the total of the day, the depletion carried in
    being at or above it. D185: while the depletion is at or above the
    reduced total, ``Kr`` is zero, since under the residue the layer has no
    evaporable water left. When the readily evaporable water equals the
    reduced total, which D110 allows ("REW not above TEW"), the stage-1 rule
    of the step gives ``Kr`` of one at that depletion, so its ``Ke`` is above
    zero although the layer has no room and supplies nothing. On such a day
    the column is given the coefficient of the evaporation the layer
    supplied, ``Ke`` times the supplied over the demanded evaporation: none
    while the layer stays at its limit, whatever the readily evaporable
    water; and, on a day a rain refills the part above the total and more,
    the evaporation the layer supplies that day (D185: "evaporation resumes
    when the depletion falls below it").
    """
    coefficient = surface.evaporation_coefficient
    operands = (
        coefficient,
        surface.evaporation,
        surface.evaporation_demanded,
        start.depletion,
        total,
    )
    if not no_crop or any(isinstance(operand, Missing) for operand in operands):
        return coefficient
    if start.depletion < total or surface.evaporation >= surface.evaporation_demanded:
        return coefficient
    return coefficient * surface.evaporation / surface.evaporation_demanded


def _run_chain(
    calendar: RotationCalendar,
    climate: SiteClimate,
    catalogue: Catalogue,
    by_quantity: dict[str, DailySeries],
    days: list[dt.date],
    notes: _Notes,
) -> list[ChainDay]:
    """ET0, runoff, ``Ke`` and the balance of every day of ``days``, in order."""
    if not days:
        return []
    start = min(days)

    # 1. The reference evapotranspiration of every day of the record.
    et0_constants = Et0Constants(
        **{
            group: _ET0_GROUPS[group](
                **{name: _site(catalogue, f"{group}_{name}", start) for name in names}
            )
            for group, names in ET0_PARAMETERS.items()
        }
    )
    et0_bounds = Et0Bounds(
        **{
            group: _BOUND_GROUPS[group](
                **{
                    field: _site(catalogue, parameter_id, start)
                    for field, parameter_id in names.items()
                }
            )
            for group, names in ET0_BOUND_PARAMETERS.items()
        }
    )
    et0_by_day = {
        item.date: item.value
        for item in et0_days(
            climate,
            point_units=POINT_UNITS,
            constants=et0_constants,
            bounds=et0_bounds,
            unit_guard_reason=_UNIT_GUARD_REASON,
        )
    }

    # The constants of the other parts, read once.
    runoff_constants = CurveNumberConstants(
        **{name: _site(catalogue, name, start) for name in RUNOFF_PARAMETERS}
    )
    surface_constants = {
        name: _site(catalogue, name, start)
        for name in SURFACE_LAYER_PARAMETERS
        if name != INITIAL_DEPLETION
    }
    surface_constants[TOTAL_EVAPORABLE_WATER] = _total_evaporable_water(
        catalogue, notes, start
    )
    upper_limit_constants = evaporation.UpperLimitClimateConstants(
        **{
            name: _site(catalogue, f"{UPPER_LIMIT_PREFIX}{name}", start)
            for name in UPPER_LIMIT_FIELDS
        }
    )
    minimum_crop_coefficient = _site(catalogue, MINIMUM_CROP_COEFFICIENT, start)
    minimum_relative_humidity = _site(catalogue, MINIMUM_RELATIVE_HUMIDITY, start)
    capacity = _site(catalogue, COLUMN_CAPACITY, start)
    column_depth = _site(catalogue, COLUMN_DEPTH, start)
    depletion = _State(_site(catalogue, INITIAL_DEPLETION, start), "depletion")
    storage = _State(_site(catalogue, INITIAL_STORAGE, start), "storage")
    column_missing = [
        item for item in (capacity, column_depth) if isinstance(item, Missing)
    ]

    precipitation_series = by_quantity.get(PRECIPITATION)
    precipitation_values = _series_values(precipitation_series)
    wind_values = _series_values(by_quantity.get(WIND_SPEED_2M))
    # The rotation over the years of the record (D47, D109, D132, D141).
    repeated = _over_record(calendar, by_quantity[PRECIPITATION])
    component_of = _component_of_day(calendar, repeated)
    growth_of = _growth_of_day(catalogue)
    following_of = _following_crop(repeated)

    chain: list[ChainDay] = []
    for day in days:
        precipitation = _day_value(precipitation_values, PRECIPITATION, True, day)
        wind = _day_value(wind_values, WIND_SPEED_2M, WIND_SPEED_2M in by_quantity, day)
        et0 = et0_by_day.get(
            day,
            Missing(
                reason="MISSING_INPUT",
                detail="no input of the reference evapotranspiration covers this day",
            ),
        )

        # The crop of the day and its parameters.
        covering = component_of(day)
        crop_day: balance.CropDay | None | Missing
        fallow_surface: FallowSurface | None = None
        if isinstance(covering, Missing):
            notes.note(covering, day)
            kcb = height = exponent = curve_number = crop_day = covering
        else:
            crop = None if covering is None else covering.crop_id
            scope: Scope = NO_CROP if crop is None else ((CROP_KEY, crop),)
            height = catalogue.value(CROP_HEIGHT, scope, day)
            curve_number = catalogue.value(CURVE_NUMBER, scope, day)
            growth: Growth | Missing | None = None
            if covering is not None:
                exponent = catalogue.value(COVER_FRACTION_EXPONENT, scope, day)
                # Every record of the crop is read, so that one that is
                # missing is named (D56).
                for stage in STAGES:
                    catalogue.value(
                        BASAL_CROP_COEFFICIENT, (*scope, (STAGE_KEY, stage)), day
                    )
                for parameter_id in CROP_PARAMETERS:
                    catalogue.value(parameter_id, scope, day)
                fraction = catalogue.value(READILY_AVAILABLE_FRACTION, scope, day)
                growth = growth_of(day, covering)
                if growth is None:
                    # A day of the tail, after the late stage and up to the
                    # harvest (D135, D136): no living crop, so it is a day
                    # with no crop from here on, with the records of one.
                    scope = NO_CROP
                    height = catalogue.value(CROP_HEIGHT, scope, day)
                    curve_number = catalogue.value(CURVE_NUMBER, scope, day)
            if growth is None:
                # A fallow day (unit #217), or a day of the tail (D136).
                # Weed-free (D111): no crop reaches the balance, so nothing
                # is transpired and no potential transpiration enters the
                # ratio (D106); the day stays in the balance (D44, D50). The
                # surface layer takes the cover, the wetting and the
                # evaporable waters of D110.
                kcb = catalogue.value(BASAL_CROP_COEFFICIENT, scope, day)
                crop_day = None
                exponent = None
                fallow_surface = _fallow_surface(
                    catalogue,
                    notes,
                    day,
                    following_of(day),
                    surface_constants[TOTAL_EVAPORABLE_WATER],
                    surface_constants["readily_evaporable_water"],
                )
            elif isinstance(growth, Missing):
                # A record that is missing is named by the catalogue; a
                # stage not known (D79) or not placed is noted.
                if growth.detail == STAGE_UNKNOWN or growth.reason != "MISSING_INPUT":
                    notes.note(growth, day)
                kcb = crop_day = growth
            else:
                kcb = growth.basal_crop_coefficient
                crop_day = (
                    Missing(reason="MISSING_INPUT", detail=fraction.detail)
                    if isinstance(fraction, Missing)
                    else balance.CropDay(
                        transpiration_coefficient=kcb,
                        root_depth=growth.root_depth,
                        readily_available_fraction=fraction,
                    )
                )

        # 2. Runoff by the Curve Number.
        runoff = runoff_day(
            RunoffDayInput(
                date=day,
                precipitation=PrecipitationValue(
                    value=precipitation, unit=PRECIPITATION_UNIT
                ),
                curve_number=curve_number,
            ),
            constants=runoff_constants,
            unit_guard_reason=_UNIT_GUARD_REASON,
        )

        # 3. Ke from the surface layer: the climate term, the upper limit and
        # the cover fraction of the day, then the daily step.
        climate_term = _guarded(
            "the climate term of the upper limit",
            notes,
            day,
            evaporation.climate_adjusted_upper_limit,
            wind,
            minimum_relative_humidity,
            height,
            constants=upper_limit_constants,
        )
        day_constants = surface_constants
        if fallow_surface is None:
            upper_limit = _guarded(
                "the upper limit of the crop coefficient",
                notes,
                day,
                evaporation.upper_limit_of_crop_coefficient,
                kcb,
                climate_term,
                margin_above_basal=surface_constants["margin_above_basal"],
            )
            cover_fraction = _guarded(
                "the cover fraction",
                notes,
                day,
                evaporation.cover_fraction_from_basal_coefficient,
                kcb,
                minimum_crop_coefficient=minimum_crop_coefficient,
                upper_limit=upper_limit,
                exponent=exponent,
            )
        else:
            # D110: fc and fw of a day with no crop, and the reduced
            # evaporable waters, in place of those of a day with a crop.
            cover_fraction = fallow_surface.cover_fraction
            day_constants = {
                **surface_constants,
                TOTAL_EVAPORABLE_WATER: fallow_surface.total_evaporable_water,
                "readily_evaporable_water": fallow_surface.readily_evaporable_water,
                "wetted_fraction": fallow_surface.wetted_fraction,
            }
        # D185 (OPEN 30): a depletion above the total of the day is
        # kept; the step starts at the total and the infiltration refills the
        # part above it first (``_layer_start``).
        layer_start = _layer_start(
            depletion.value,
            day_constants[TOTAL_EVAPORABLE_WATER],
            surface_constants[TOTAL_EVAPORABLE_WATER],
            precipitation,
            runoff.runoff,
        )
        surface = _guarded(
            "the surface-layer balance",
            notes,
            day,
            evaporation.step,
            layer_start.depletion,
            evaporation.DayInput(
                date=day,
                precipitation=layer_start.precipitation,
                runoff=runoff.runoff,
                reference_evapotranspiration=et0,
                basal_crop_coefficient=kcb,
                cover_fraction=cover_fraction,
                climate_adjusted_upper_limit=climate_term,
            ),
            **day_constants,
        )
        if isinstance(surface, Missing):
            surface = _missing_result(
                evaporation.DayResult, evaporation.RESULT_QUANTITIES, day, surface
            )
        carried = surface.depletion_end
        if layer_start.above is not None and not isinstance(carried, Missing):
            carried = carried + layer_start.above
        depletion.carry(carried, day)

        # 4. The daily balance of the column.
        balance_day = balance.DayInput(
            date=day,
            precipitation=precipitation,
            runoff=runoff.runoff,
            reference_evapotranspiration=et0,
            # D185: none from a day with no crop whose surface layer stays at
            # its limit, whatever the readily evaporable water.
            evaporation_coefficient=_column_evaporation_coefficient(
                surface,
                layer_start,
                day_constants[TOTAL_EVAPORABLE_WATER],
                fallow_surface is not None,
            ),
            crop=crop_day,
        )
        if column_missing:
            result: object = Missing(
                reason="MISSING_INPUT",
                detail="the column of the balance: "
                + "; ".join(item.detail for item in column_missing),
            )
        else:
            result = _guarded(
                "the daily balance",
                notes,
                day,
                balance.step,
                storage.value,
                balance_day,
                capacity=capacity,
                column_depth=column_depth,
            )
        if isinstance(result, Missing):
            result = _missing_result(
                balance.DayResult, balance.RESULT_QUANTITIES, day, result
            )
        storage.carry(result.storage_end, day)

        chain.append(
            ChainDay(
                date=day,
                precipitation=precipitation,
                reference_evapotranspiration=et0,
                runoff=runoff,
                surface_layer=surface,
                surface_depletion_carried=depletion.value,
                balance=result,
            )
        )
    return chain


# --- what each yearly item reports --------------------------------------------


def _input_items(
    absent: list[str],
    missing_days: dict[str, list[dt.date]],
    first: dt.date,
    last: dt.date,
    ag_year: int,
) -> list[str]:
    items = [
        f"input MISSING_INPUT: the climate record has no daily series '{name}' "
        "(G4, third row)"
        for name in absent
    ]
    for name, days in missing_days.items():
        held = [day for day in days if first <= day <= last]
        if held:
            items.append(
                f"input MISSING_INPUT: the daily series '{name}' holds {len(held)} "
                f"day(s) without a value in agricultural year {ag_year}, the first on "
                f"{min(held).isoformat()}, and no gap is filled (G4, fourth row, C3.4)"
            )
    return items


def _point_items(climate: SiteClimate) -> list[str]:
    """An item for each value of the point the reference evapotranspiration
    reads that is missing, with its own reason and detail."""
    items = []
    for name in POINT_VALUES:
        value = getattr(climate.point, name)
        if value.missing is not None:
            why = f"the {name} of the point of the climate record is missing"
            if value.missing.detail is not None:
                why = f"{why}: {value.missing.detail}"
            items.append(f"input {value.missing.reason}: {why}")
    return items


def _not_covered(names: list[str], ag_year: int) -> Missing:
    return Missing(
        reason="NO_COVERAGE",
        detail=(
            "the daily series "
            + ", ".join(f"'{name}'" for name in names)
            + f" do not cover agricultural year {ag_year} from its first day to its "
            "last (C5.5)"
        ),
    )


def _units_not_accepted(problems: list[str]) -> Missing:
    return Missing(
        reason="MISSING_INPUT",
        detail=(
            f"{INDICATOR} is not computed: an input arrives in a unit string the "
            "water engine does not accept, and nothing is converted (C1.1); the "
            "reason code for that case is not decided (Q11 of "
            "contracts/ENTRYPOINTS.md), and MISSING_INPUT is PROPOSED: "
            + "; ".join(problems)
        ),
    )


def _no_living_crop(ag_year: int) -> Missing:
    return Missing(
        reason="NOT_APPLICABLE",
        detail=(
            f"{INDICATOR} does not apply to agricultural year {ag_year}: the daily "
            "water balance was computed on every day of the year, and no day of the "
            "year has a living crop (a day with no crop and a day of the tail after "
            "maturity do not enter the ratio: decisions D106, D136 and D157 of issue "
            "#77)"
        ),
    )


def _nothing_demanded(ag_year: int, days: int) -> Missing:
    return Missing(
        reason="NOT_COMPUTABLE",
        detail=(
            f"{INDICATOR} is not computed for agricultural year {ag_year}: the water "
            "demanded (the basal crop coefficient times the reference "
            f"evapotranspiration), summed over its {days} day(s) with a living crop, "
            "is not above zero, so the ratio of decision D157 of issue #77 has no "
            "denominator (reason code PROPOSED, OPEN 43 of engine/water/EXPOSURE.md)"
        ),
    )


def _not_a_number(ag_year: int, what: str, day: dt.date, missing: Missing) -> Missing:
    """A crop quantity of a computed day that is not a number: the year keeps
    the reason of that day, and no value is put in its place."""
    return Missing(
        reason=missing.reason,
        detail=(
            f"{INDICATOR} is not computed for agricultural year {ag_year}: the {what} "
            f"of the daily water balance has no value on {day.isoformat()} "
            f"({missing.reason}: {missing.detail})"
        ),
    )


def _source(ag_year: int, living: list[ChainDay]) -> str:
    """The source of a value. PROPOSED (D162 gives the label and its place; the
    rest says what the value is computed from, as EP1 does for soil loss)."""
    first, *_ = living
    *_, last = living
    return (
        f"{WINDOW_LABEL} (decisions D105 and D162 of issue #77); simulated by "
        "engine.water.compute_water_deficit_exposure as decision D157 states it: "
        "the transpiration of the daily water balance over its demanded "
        "transpiration (the basal crop coefficient times the reference "
        f"evapotranspiration), each summed over the {len(living)} day(s) with a "
        f"living crop of agricultural year {ag_year}, the first on "
        f"{first.date.isoformat()} and the last on {last.date.isoformat()}; days "
        "with no crop and the tail after maturity are left out (D106, D136); the "
        "daily balance runs on the daily series of the climate record, on the "
        "rotation calendar repeated over the record (D47) and on the parameter "
        "records listed in engine/water/EXPOSURE.md"
    )


def _computed(ag_year: int, year: list[ChainDay]) -> WaterDeficitExposure:
    """The value of a year whose daily balance was computed on every day (D157).

    Water transpired is ``transpiration`` of the daily balance and water
    demanded is its ``transpiration_demanded`` (the basal crop coefficient
    times the reference evapotranspiration); neither is recomputed here. A
    day with a living crop is a day on which the balance was given a crop, so
    its demanded transpiration is a number; on a fallow day and on a day of
    the tail after maturity the balance was given none and answers
    ``NOT_APPLICABLE`` (D106, D136), and the day is left out. The days are
    those of the agricultural year, so a cycle that crosses its start gives
    its days to each year (D157, D47).

    The value is the sum of the first over the sum of the second. Not a
    number, and never zero in its place: a year with no day with a living
    crop is ``NOT_APPLICABLE`` (D157); a demanded sum that is not above zero
    is ``NOT_COMPUTABLE`` (PROPOSED), as is a ratio that is not finite.
    """
    living: list[ChainDay] = []
    for day in year:
        demanded = day.balance.transpiration_demanded
        if not isinstance(demanded, Missing):
            living.append(day)
        elif demanded.reason != NO_CROP_ON_THE_DAY:
            return _for_ag_year(
                ag_year,
                _not_a_number(ag_year, "demanded transpiration", day.date, demanded),
            )
    if not living:
        return _for_ag_year(ag_year, _no_living_crop(ag_year))
    for day in living:
        transpired = day.balance.transpiration
        if isinstance(transpired, Missing):
            return _for_ag_year(
                ag_year, _not_a_number(ag_year, "transpiration", day.date, transpired)
            )
    water_demanded = math.fsum(day.balance.transpiration_demanded for day in living)
    water_transpired = math.fsum(day.balance.transpiration for day in living)
    if not water_demanded > _ZERO:
        return _for_ag_year(ag_year, _nothing_demanded(ag_year, len(living)))
    value = water_transpired / water_demanded
    if not math.isfinite(value):
        return _for_ag_year(ag_year, _nothing_demanded(ag_year, len(living)))
    return WaterDeficitExposure(
        indicator=INDICATOR,
        direction=DIRECTION_OF[INDICATOR],
        value=value,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        provenance=PROVENANCE,
        source=_source(ag_year, living),
        range_missing=Missing(reason="NOT_AVAILABLE", detail=RANGE_NOT_BUILT),
        time_basis="ag_year",
        ag_year=ag_year,
    )


def _chain_missing(
    ag_year: int, missing_days: list[ChainDay], items: list[str]
) -> Missing:
    first, *_ = missing_days
    cause = first.balance.storage_end
    return Missing(
        reason=cause.reason,
        detail=(
            f"{INDICATOR} is not computed for agricultural year {ag_year}: the daily "
            f"water balance has no value on {len(missing_days)} day(s) of the year, "
            f"the first on {first.date.isoformat()} ({cause.reason}: {cause.detail}); "
            + "; ".join([*items, f"indicator: {DEFINITION_INCOMPLETE}"])
        ),
    )


def _for_rotation(missing: Missing) -> WaterDeficitExposure:
    return WaterDeficitExposure(
        indicator=INDICATOR,
        direction=DIRECTION_OF[INDICATOR],
        value=None,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        missing=missing,
        time_basis="rotation",
    )


def _for_ag_year(ag_year: int, missing: Missing) -> WaterDeficitExposure:
    return WaterDeficitExposure(
        indicator=INDICATOR,
        direction=DIRECTION_OF[INDICATOR],
        value=None,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        missing=missing,
        time_basis="ag_year",
        ag_year=ag_year,
    )


# --- the entry point ----------------------------------------------------------


def _chain_days(
    record: DailySeries, present: list[str], by_quantity: dict[str, DailySeries]
) -> list[dt.date]:
    """The days the chain runs on: from the first day every series read covers,
    to the last day of the record. PROPOSED (EXPOSURE.md)."""
    first = max(by_quantity[name].start_date for name in present)
    return _days(first, record.end_date)


def compute_water_deficit_exposure(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    parameters: dict[str, dict],
) -> list[WaterDeficitExposure]:
    """Exposure to water deficit of one rotation of one field (EP3).

    ``parameters`` is the parameter catalogue as loaded by the runner (Q3,
    D46, D56), passed by keyword, with no default.

    Returns a list that is never empty:

    - one item on the time basis ``rotation``, reason ``MISSING_INPUT``, when
      the agricultural years cannot be laid out: the start month is missing,
      or the record has no daily ``precipitation`` series (D163);
    - otherwise one item per agricultural year of the record (D47), on the
      time basis ``ag_year``. A year is missing with the first reason that
      applies: ``NOT_COMPUTABLE`` for an infeasible calendar, then
      ``NOT_COMPUTABLE`` for series in different time zones (C6.3), then
      ``NO_COVERAGE`` for a year a series does not cover (C5.5), then
      ``MISSING_INPUT`` when an input arrives in a unit string the parts do
      not accept (Q11), then the reason of the first day of the year on which
      the daily chain has no value (naming the inputs and the parameters,
      by ``id`` and ``scope``, that are missing up to the end of the year).
      A year whose daily balance was computed on every day carries the ratio
      of decision D157 (``_computed``): a number with the label "whole cycle,
      not critical period" at the start of its ``source`` (D105, D162), its
      provenance label and the reason it has no range; or ``NOT_APPLICABLE``
      when no day of the year has a living crop; or ``NOT_COMPUTABLE`` when
      nothing was demanded on its days with a living crop.

    The crop of each day of the chain is read from the calendar repeated over
    the agricultural years of the record by
    ``engine.calendar.repeat_over_record`` (D47, D109), so a calendar whose
    dates lie outside the record, and a calendar moved by ``phase_calendar``
    (D132, D141), run as they are.

    Raises ``TypeError`` for an argument that is not its type (G3) and
    ``ValueError`` when the arguments name different fields (G5), or, as EP1
    does, when the helper lays out other agricultural years than this
    function lists from the same record and start month.
    """
    _check_types(calendar, climate, soil_slope, parameters)
    _check_same_field(calendar, climate, soil_slope)

    start_month = calendar.ag_year_start.month
    if start_month is None:
        return [
            _for_rotation(Missing(reason="MISSING_INPUT", detail=START_MONTH_MISSING))
        ]

    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in DAILY_INPUTS
    }
    record = by_quantity.get(PRECIPITATION)
    if record is None:
        return [_for_rotation(Missing(reason="MISSING_INPUT", detail=RECORD_MISSING))]

    present = [name for name in DAILY_INPUTS if name in by_quantity]
    absent = [name for name in DAILY_INPUTS if name not in by_quantity]
    if not calendar.feasibility.feasible:
        common: Missing | None = Missing(reason="NOT_COMPUTABLE", detail=INFEASIBLE)
    elif _mixed_time_zones([by_quantity[name] for name in present]):
        common = Missing(reason="NOT_COMPUTABLE", detail=MIXED_TIME_ZONES)
    else:
        common = None
    units = _unit_problems(climate, by_quantity) if common is None else []
    missing_days = {
        name: [day.date for day in by_quantity[name].days if day.missing is not None]
        for name in present
    }

    catalogue = Catalogue(parameters)
    notes = _Notes()
    chain_by_day: dict[dt.date, ChainDay] = {}
    if common is None and not units:
        chain = _run_chain(
            calendar,
            climate,
            catalogue,
            by_quantity,
            _chain_days(record, present, by_quantity),
            notes,
        )
        chain_by_day = {item.date: item for item in chain}

    result: list[WaterDeficitExposure] = []
    first_ag_year = _ag_year_of(record.start_date, start_month)
    last_ag_year = _ag_year_of(record.end_date, start_month)
    for ag_year in range(first_ag_year, last_ag_year + _FIRST):
        if common is not None:
            result.append(_for_ag_year(ag_year, common))
            continue
        first = _first_day(ag_year, start_month)
        last = _last_day(ag_year, start_month)
        not_covering = [
            name for name in present if not _covers(by_quantity[name], first, last)
        ]
        if not_covering:
            result.append(_for_ag_year(ag_year, _not_covered(not_covering, ag_year)))
            continue
        if units:
            result.append(_for_ag_year(ag_year, _units_not_accepted(units)))
            continue
        year = [chain_by_day[day] for day in _days(first, last)]
        not_computed = [
            item for item in year if isinstance(item.balance.storage_end, Missing)
        ]
        if not not_computed:
            result.append(_computed(ag_year, year))
            continue
        items = (
            _input_items(absent, missing_days, first, last, ag_year)
            + _point_items(climate)
            + [
                f"parameter MISSING_INPUT: {item}"
                for item in catalogue.problems_until(last)
            ]
            + [f"chain {item}" for item in notes.until(last)]
        )
        result.append(
            _for_ag_year(ag_year, _chain_missing(ag_year, not_computed, items))
        )
    return result
