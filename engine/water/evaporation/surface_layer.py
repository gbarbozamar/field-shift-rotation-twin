"""Soil evaporation by the FAO-56 dual crop coefficient (decision D44 of #77).

Status: PROPOSED (blueprint section 3.7). The behaviour is described in
engine/water/evaporation/README.md and takes effect only when people approve
it. The form of every equation is PROPOSED: a builder session wrote it
without the method's text in front of it, and a person confirms it against
FAO-56 chapter 7 (CITATION NEEDED).

D44 writes actual evapotranspiration as ``ETa = (Ks * Kcb + Ke) * ET0``. This
module computes ``Ke``, the evaporation coefficient, from the daily balance
of the surface soil layer. Each intermediate quantity is its own function:

- ``total_evaporable_water``: the most water the surface layer can lose to
  evaporation, from its water contents and depth;
- ``evaporation_reduction_coefficient``: the reduction coefficient from the
  depletion of the surface layer (stage 1 and stage 2 of drying);
- ``climate_adjusted_upper_limit``: the climate term of the upper limit of
  the crop coefficient;
- ``upper_limit_of_crop_coefficient``: the upper limit itself;
- ``cover_fraction_from_basal_coefficient``: the fraction of the soil the
  crop covers, from the basal coefficient;
- ``exposed_and_wetted_fraction``: the fraction of the soil that is both
  exposed and wetted;
- ``evaporation_coefficient``: ``Ke`` itself;
- ``step``: one day of the balance of the surface layer;
- ``run_surface_layer``: ``step`` over consecutive days.

The balance of the surface layer is kept as a depletion ``De``, the water
missing from the layer against its full state. Within a day, with ``P``
precipitation, ``RO`` runoff, ``DPe`` the water that passes below the layer
and ``E`` evaporation,

    De_end - De_start = -(P - RO) + DPe + E / few

where ``few`` is the exposed and wetted fraction, so that ``E / few`` is the
depth evaporated from that fraction. The system is rain-fed: there is no
irrigation term.

The module holds no constant of the method and no unit string. Every
constant is an argument with no default. Depths of water share one unit,
chosen by the caller; the module converts nothing.

Pure functions: no file, no network, no clock, no global state. They do not
change their arguments, and the same arguments give the same result.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Sequence

from contracts.results.models import Missing

Number = float | Missing


# ---------------------------------------------------------------------------
# Checks. A defect of the caller raises; a missing value never does.


def _is_number(value: object) -> bool:
    """True for an ``int`` or a ``float``; a boolean is not a number here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _real(name: str, value: object) -> float:
    """Return ``value`` as a finite float, or raise for a defect of the caller."""
    if not _is_number(value):
        raise TypeError(f"{name} must be a number, not {type(value).__name__}")
    try:
        finite = math.isfinite(value)
    except OverflowError:  # an integer too large to be a float
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _non_negative(name: str, value: object) -> float:
    value = _real(name, value)
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _fraction(name: str, value: object) -> float:
    value = _non_negative(name, value)
    if value > 1:
        raise ValueError(f"{name} must not be greater than one")
    return value


def _missing_operands(
    inputs: dict[str, object], constants: dict[str, object]
) -> Missing | None:
    """A ``Missing`` naming every missing operand, or ``None`` if none is.

    Inputs are named ``input '<name>'`` and constants ``constant '<name>'``,
    each with its own reason (C3.3). A value that is neither a number nor a
    ``Missing`` raises ``TypeError``.
    """
    names = []
    for kind, operands in (("input", inputs), ("constant", constants)):
        for name, value in operands.items():
            if isinstance(value, Missing):
                names.append(f"{kind} '{name}' ({value.reason})")
            elif not _is_number(value):
                raise TypeError(
                    f"{name} must be a number or Missing, not {type(value).__name__}"
                )
    if not names:
        return None
    return Missing(reason="MISSING_INPUT", detail=", ".join(names))


def _not_computable(detail: str) -> Missing:
    return Missing(reason="NOT_COMPUTABLE", detail=detail)


# ---------------------------------------------------------------------------
# Intermediate quantities.


def total_evaporable_water(
    field_capacity_water_content: Number,
    wilting_point_water_content: Number,
    surface_layer_depth: Number,
    *,
    wilting_point_weight: Number,
    unit_factor: Number,
) -> Number:
    """Total evaporable water of the surface layer.

    Form PROPOSED, source CITATION NEEDED (FAO-56 chapter 7, equation OPEN):

        TEW = unit_factor * (theta_FC - wilting_point_weight * theta_WP) * Ze

    with ``theta_FC`` and ``theta_WP`` the water contents at field capacity
    and at wilting point, and ``Ze`` the depth of the surface layer.
    ``wilting_point_weight`` is the weight the method gives the wilting
    point; ``unit_factor`` turns a water content times a depth into a depth
    of water in the caller's unit. Both are constants a person transcribes.

    A result below zero is not computed (``NOT_COMPUTABLE``): it would be a
    layer that holds less than nothing.
    """
    missing = _missing_operands(
        {
            "field_capacity_water_content": field_capacity_water_content,
            "wilting_point_water_content": wilting_point_water_content,
            "surface_layer_depth": surface_layer_depth,
        },
        {"wilting_point_weight": wilting_point_weight, "unit_factor": unit_factor},
    )
    if missing is not None:
        return missing
    theta_fc = _non_negative(
        "field_capacity_water_content", field_capacity_water_content
    )
    theta_wp = _non_negative("wilting_point_water_content", wilting_point_water_content)
    depth = _non_negative("surface_layer_depth", surface_layer_depth)
    weight = _non_negative("wilting_point_weight", wilting_point_weight)
    factor = _non_negative("unit_factor", unit_factor)
    value = factor * (theta_fc - weight * theta_wp) * depth
    if not math.isfinite(value):
        return _not_computable("total evaporable water is not a finite number")
    if value < 0:
        return _not_computable(
            "total evaporable water would be below zero: the weighted wilting "
            "point water content exceeds the field capacity water content"
        )
    return value


def _check_evaporable_water(
    total_evaporable_water: float, readily_evaporable_water: float
) -> tuple[float, float]:
    tew = _non_negative("total_evaporable_water", total_evaporable_water)
    rew = _non_negative("readily_evaporable_water", readily_evaporable_water)
    if tew == 0:
        raise ValueError("total_evaporable_water must be greater than zero")
    if rew > tew:
        raise ValueError(
            "readily_evaporable_water must not be greater than total_evaporable_water"
        )
    return tew, rew


def evaporation_reduction_coefficient(
    depletion: Number,
    *,
    total_evaporable_water: Number,
    readily_evaporable_water: Number,
) -> Number:
    """Evaporation reduction coefficient ``Kr`` from the surface-layer depletion.

    Form PROPOSED, source CITATION NEEDED (FAO-56 chapter 7, equation OPEN).
    With ``De`` the depletion, ``TEW`` the total and ``REW`` the readily
    evaporable water:

    - stage 1, ``De <= REW``: ``Kr`` is one (evaporation limited by energy);
    - stage 2, ``De > REW``: ``Kr = (TEW - De) / (TEW - REW)``, falling from
      one at ``De = REW`` to zero at ``De = TEW``.

    ``depletion`` lies between zero and ``TEW``; ``TEW`` is greater than zero
    and ``REW`` lies between zero and ``TEW``.
    """
    missing = _missing_operands(
        {"depletion": depletion},
        {
            "total_evaporable_water": total_evaporable_water,
            "readily_evaporable_water": readily_evaporable_water,
        },
    )
    if missing is not None:
        return missing
    tew, rew = _check_evaporable_water(total_evaporable_water, readily_evaporable_water)
    de = _non_negative("depletion", depletion)
    if de > tew:
        raise ValueError("depletion must not be greater than total_evaporable_water")
    if de <= rew:
        return 1.0
    return (tew - de) / (tew - rew)


@dataclass(frozen=True)
class UpperLimitClimateConstants:
    """Constants of the climate term of the upper limit of the crop coefficient.

    None has a default and none has a value in this repository: a person
    transcribes them from FAO-56 chapter 7 (README, "Constants a person has to
    transcribe"). Each is a number or a ``Missing``.

    - ``base``: the term the climate adjustment is added to.
    - ``wind_coefficient``, ``reference_wind_speed``: the weight of the wind
      speed at 2 m and the wind speed at which its term is zero.
    - ``humidity_coefficient``, ``reference_minimum_relative_humidity``: the
      weight of the minimum relative humidity and the humidity at which its
      term is zero.
    - ``reference_crop_height``, ``height_exponent``: the crop height the
      adjustment is scaled by, and the exponent of that scaling.
    """

    base: Number
    wind_coefficient: Number
    reference_wind_speed: Number
    humidity_coefficient: Number
    reference_minimum_relative_humidity: Number
    reference_crop_height: Number
    height_exponent: Number


def climate_adjusted_upper_limit(
    wind_speed_2m: Number,
    minimum_relative_humidity: Number,
    crop_height: Number,
    *,
    constants: UpperLimitClimateConstants,
) -> Number:
    """Climate term of the upper limit of the crop coefficient.

    Form PROPOSED, source CITATION NEEDED (FAO-56 chapter 7, equation OPEN):

        base + [wind_coefficient * (u2 - reference_wind_speed)
                - humidity_coefficient * (RHmin - reference_minimum_relative_humidity)]
               * (h / reference_crop_height) ** height_exponent

    with ``u2`` the wind speed at 2 m, ``RHmin`` the minimum relative humidity
    and ``h`` the crop height, each in the unit the constants are written in.
    Arithmetic with no finite real result gives ``NOT_COMPUTABLE``.
    """
    if not isinstance(constants, UpperLimitClimateConstants):
        raise TypeError(
            "constants must be UpperLimitClimateConstants, "
            f"not {type(constants).__name__}"
        )
    names = (
        "base",
        "wind_coefficient",
        "reference_wind_speed",
        "humidity_coefficient",
        "reference_minimum_relative_humidity",
        "reference_crop_height",
        "height_exponent",
    )
    missing = _missing_operands(
        {
            "wind_speed_2m": wind_speed_2m,
            "minimum_relative_humidity": minimum_relative_humidity,
            "crop_height": crop_height,
        },
        {name: getattr(constants, name) for name in names},
    )
    if missing is not None:
        return missing
    u2 = _non_negative("wind_speed_2m", wind_speed_2m)
    rh_min = _non_negative("minimum_relative_humidity", minimum_relative_humidity)
    height = _non_negative("crop_height", crop_height)
    c = {name: _real(name, getattr(constants, name)) for name in names}
    if c["reference_crop_height"] <= 0:
        raise ValueError("reference_crop_height must be greater than zero")
    try:
        scale = (height / c["reference_crop_height"]) ** c["height_exponent"]
        value = (
            c["base"]
            + (
                c["wind_coefficient"] * (u2 - c["reference_wind_speed"])
                - c["humidity_coefficient"]
                * (rh_min - c["reference_minimum_relative_humidity"])
            )
            * scale
        )
    except (ZeroDivisionError, OverflowError):
        return _not_computable("climate term of the upper limit has no finite value")
    if isinstance(value, complex) or not math.isfinite(value):
        return _not_computable("climate term of the upper limit has no finite value")
    return value


def upper_limit_of_crop_coefficient(
    basal_crop_coefficient: Number,
    climate_adjusted_upper_limit: Number,
    *,
    margin_above_basal: Number,
) -> Number:
    """Upper limit ``Kc_max`` of the crop coefficient on a day.

    Form PROPOSED, source CITATION NEEDED (FAO-56 chapter 7, equation OPEN):
    the larger of the climate term (``climate_adjusted_upper_limit``) and the
    basal coefficient plus ``margin_above_basal``. So ``Kc_max`` is never
    below ``Kcb``.
    """
    missing = _missing_operands(
        {
            "basal_crop_coefficient": basal_crop_coefficient,
            "climate_adjusted_upper_limit": climate_adjusted_upper_limit,
        },
        {"margin_above_basal": margin_above_basal},
    )
    if missing is not None:
        return missing
    kcb = _non_negative("basal_crop_coefficient", basal_crop_coefficient)
    climate = _real("climate_adjusted_upper_limit", climate_adjusted_upper_limit)
    margin = _non_negative("margin_above_basal", margin_above_basal)
    return max(climate, kcb + margin)


def cover_fraction_from_basal_coefficient(
    basal_crop_coefficient: Number,
    *,
    minimum_crop_coefficient: Number,
    upper_limit: Number,
    exponent: Number,
) -> Number:
    """Fraction of the soil covered by the crop, from the basal coefficient.

    Form PROPOSED, source CITATION NEEDED (FAO-56 chapter 7, equation OPEN):

        fc = ((Kcb - Kc_min) / (Kc_max - Kc_min)) ** exponent

    The method writes the exponent from the crop height; how is OPEN, so the
    caller supplies the exponent. A ratio outside zero to one, an upper limit
    equal to the minimum, or arithmetic with no finite real result gives
    ``NOT_COMPUTABLE``: how the method treats those cases is OPEN, and the
    module does not clip. The cover fraction may also be supplied directly
    (observed); ``step`` takes it as an input.
    """
    missing = _missing_operands(
        {"basal_crop_coefficient": basal_crop_coefficient},
        {
            "minimum_crop_coefficient": minimum_crop_coefficient,
            "upper_limit": upper_limit,
            "exponent": exponent,
        },
    )
    if missing is not None:
        return missing
    kcb = _non_negative("basal_crop_coefficient", basal_crop_coefficient)
    kc_min = _non_negative("minimum_crop_coefficient", minimum_crop_coefficient)
    kc_max = _non_negative("upper_limit", upper_limit)
    power = _real("exponent", exponent)
    if kc_max == kc_min:
        return _not_computable("upper limit equals the minimum crop coefficient")
    ratio = (kcb - kc_min) / (kc_max - kc_min)
    if ratio < 0 or ratio > 1:
        return _not_computable(
            "the basal coefficient lies outside the minimum and the upper limit"
        )
    try:
        value = ratio**power
    except (ZeroDivisionError, OverflowError):
        return _not_computable("cover fraction has no finite value")
    if not math.isfinite(value):
        return _not_computable("cover fraction has no finite value")
    return value


def exposed_and_wetted_fraction(
    cover_fraction: Number, wetted_fraction: Number
) -> Number:
    """Fraction ``few`` of the soil that is both exposed and wetted.

    Form PROPOSED, source CITATION NEEDED (FAO-56 chapter 7, equation OPEN):
    ``few = min(1 - fc, fw)`` with ``fc`` the cover fraction and ``fw`` the
    fraction wetted by precipitation. Both lie between zero and one.
    """
    missing = _missing_operands(
        {"cover_fraction": cover_fraction}, {"wetted_fraction": wetted_fraction}
    )
    if missing is not None:
        return missing
    fc = _fraction("cover_fraction", cover_fraction)
    fw = _fraction("wetted_fraction", wetted_fraction)
    return min(1.0 - fc, fw)


def evaporation_coefficient(
    reduction_coefficient: Number,
    upper_limit: Number,
    basal_crop_coefficient: Number,
    exposed_and_wetted_fraction: Number,
) -> Number:
    """Evaporation coefficient ``Ke`` of the dual crop coefficient.

    Form PROPOSED, source CITATION NEEDED (FAO-56 chapter 7, equation OPEN):

        Ke = min(Kr * (Kc_max - Kcb), few * Kc_max)

    ``Kr`` and ``few`` lie between zero and one; ``Kc_max`` is not below
    ``Kcb``, which ``upper_limit_of_crop_coefficient`` guarantees.
    """
    missing = _missing_operands(
        {
            "reduction_coefficient": reduction_coefficient,
            "upper_limit": upper_limit,
            "basal_crop_coefficient": basal_crop_coefficient,
            "exposed_and_wetted_fraction": exposed_and_wetted_fraction,
        },
        {},
    )
    if missing is not None:
        return missing
    kr = _fraction("reduction_coefficient", reduction_coefficient)
    kc_max = _non_negative("upper_limit", upper_limit)
    kcb = _non_negative("basal_crop_coefficient", basal_crop_coefficient)
    few = _fraction("exposed_and_wetted_fraction", exposed_and_wetted_fraction)
    if kc_max < kcb:
        raise ValueError("upper_limit must not be below basal_crop_coefficient")
    return min(kr * (kc_max - kcb), few * kc_max)


# ---------------------------------------------------------------------------
# The daily balance of the surface layer.

# The inputs of one day that are a number or a missing value, in the order a
# detail text names them.
_DAY_NUMBERS: tuple[str, ...] = (
    "precipitation",
    "runoff",
    "reference_evapotranspiration",
    "basal_crop_coefficient",
    "cover_fraction",
    "climate_adjusted_upper_limit",
)

_CONSTANTS: tuple[str, ...] = (
    "total_evaporable_water",
    "readily_evaporable_water",
    "wetted_fraction",
    "margin_above_basal",
)


@dataclass(frozen=True)
class DayInput:
    """The inputs of one day.

    ``date`` labels the day (C5.2). Every other field is a number or the
    ``Missing`` of contracts/results/models.py with its reason (C3.1). None
    has a default, also on a day with no crop.

    - ``precipitation``, ``runoff``: depths of water over the day. Runoff is
      an input (engine/water/runoff/ is another unit). No irrigation: the
      system is rain-fed.
    - ``reference_evapotranspiration``: depth of water over the day, from
      engine/water/et0/.
    - ``basal_crop_coefficient``: the ``Kcb`` of the day, also on a day with
      no crop (its value on bare soil is the caller's).
    - ``cover_fraction``: the fraction of the soil the crop covers, between
      zero and one, also on a day with no crop; observed, or from
      ``cover_fraction_from_basal_coefficient``.
    - ``climate_adjusted_upper_limit``: the climate term of the upper limit
      of the crop coefficient, from ``climate_adjusted_upper_limit``.
    """

    date: datetime.date
    precipitation: Number
    runoff: Number
    reference_evapotranspiration: Number
    basal_crop_coefficient: Number
    cover_fraction: Number
    climate_adjusted_upper_limit: Number


@dataclass(frozen=True)
class DayResult:
    """One day of the balance of the surface layer.

    Every quantity is a number or a ``Missing`` with its reason (C3.1). On a
    day whose inputs are complete,

        depletion_end - depletion_start
            = -infiltration + deep_percolation + evaporation_from_exposed_fraction

    holds to the precision of floating point. Fields:

    - ``depletion_start``, ``depletion_end``: water missing from the surface
      layer at the start and end of the day, never below zero nor above the
      total evaporable water.
    - ``precipitation``, ``runoff``: as applied; ``infiltration`` is
      precipitation less runoff.
    - ``deep_percolation``: water that passes below the surface layer because
      it entered a layer already full.
    - ``reduction_coefficient``: ``Kr``, from the depletion at the start of
      the day.
    - ``upper_limit``: ``Kc_max`` of the day.
    - ``exposed_and_wetted_fraction``: ``few`` of the day.
    - ``evaporation_coefficient``: ``Ke`` of the day, the value for the
      ``evaporation_coefficient`` of the DayInput of engine/water/balance.
    - ``evaporation_demanded``: ``Ke`` times the reference evapotranspiration.
    - ``evaporation``: what the surface layer supplied, over the whole field.
    - ``evaporation_from_exposed_fraction``: the same water as a depth over
      the exposed and wetted fraction, the term of the balance.
    - ``evaporation_shortfall``: demanded less supplied; zero when the layer
      held enough water.
    - ``runoff_shortfall``: runoff asked for above the precipitation of the
      day, not applied.
    """

    date: datetime.date
    depletion_start: Number
    depletion_end: Number
    precipitation: Number
    runoff: Number
    infiltration: Number
    deep_percolation: Number
    reduction_coefficient: Number
    upper_limit: Number
    exposed_and_wetted_fraction: Number
    evaporation_coefficient: Number
    evaporation_demanded: Number
    evaporation: Number
    evaporation_from_exposed_fraction: Number
    evaporation_shortfall: Number
    runoff_shortfall: Number


# Quantities of a ``DayResult`` other than its date, in field order.
RESULT_QUANTITIES: tuple[str, ...] = tuple(
    name for name in DayResult.__dataclass_fields__ if name != "date"
)


def _missing_day(date: datetime.date, missing: Missing) -> DayResult:
    return DayResult(date=date, **{name: missing for name in RESULT_QUANTITIES})


def _check_constants(constants: dict[str, object]) -> Missing | None:
    """Check the constants of the balance; a ``Missing`` names those missing."""
    missing = _missing_operands({}, constants)
    if missing is not None:
        for name, value in constants.items():
            if not isinstance(value, Missing):
                _non_negative(name, value)
        return missing
    _check_evaporable_water(
        constants["total_evaporable_water"], constants["readily_evaporable_water"]
    )
    _fraction("wetted_fraction", constants["wetted_fraction"])
    _non_negative("margin_above_basal", constants["margin_above_basal"])
    return None


def _check_depletion(name: str, value: object, tew: object) -> Number:
    if isinstance(value, Missing):
        return value
    value = _non_negative(name, value)
    if _is_number(tew) and value > tew:
        raise ValueError(f"{name} must not be greater than total_evaporable_water")
    return value


def _check_day(day: object) -> None:
    if not isinstance(day, DayInput):
        raise TypeError(f"a day must be a DayInput, not {type(day).__name__}")
    if not isinstance(day.date, datetime.date) or isinstance(
        day.date, datetime.datetime
    ):
        raise TypeError("date must be a datetime.date")
    for name in _DAY_NUMBERS:
        value = getattr(day, name)
        if isinstance(value, Missing):
            continue
        if name == "cover_fraction":
            _fraction(name, value)
        elif name == "climate_adjusted_upper_limit":
            _real(name, value)
        else:
            _non_negative(name, value)


def step(
    depletion_start: Number,
    day: DayInput,
    *,
    total_evaporable_water: Number,
    readily_evaporable_water: Number,
    wetted_fraction: Number,
    margin_above_basal: Number,
) -> DayResult:
    """Move the balance of the surface layer forward by one day.

    ``depletion_start`` is the water missing from the surface layer at the
    start of the day, between zero and ``total_evaporable_water``, or a
    ``Missing``. The four constants are supplied by the caller with no
    default; each may be a ``Missing``.

    The order within the day is PROPOSED (README, "PROPOSED rules"):

    1. Runoff leaves from the precipitation of the day, limited to it; the
       rest infiltrates. Infiltration first refills the surface layer; what
       exceeds its depletion passes below it (deep percolation).
    2. ``Kr`` follows the depletion at the **start** of the day; ``Kc_max``,
       ``few`` and ``Ke`` follow from the inputs of the day.
    3. Evaporation demanded is ``Ke * ET0``. The depth it takes from the
       exposed and wetted fraction is limited to the water left in the
       layer; the part not supplied is the shortfall, never clipped silently.

    A missing input, constant or starting depletion gives a day whose
    quantities are all missing with reason ``MISSING_INPUT`` and a detail
    naming what is missing (C3.3). Raises ``TypeError`` or ``ValueError``
    only for a defect of the caller.
    """
    constants = {
        "total_evaporable_water": total_evaporable_water,
        "readily_evaporable_water": readily_evaporable_water,
        "wetted_fraction": wetted_fraction,
        "margin_above_basal": margin_above_basal,
    }
    missing_constants = _check_constants(constants)
    depletion_start = _check_depletion(
        "depletion_start", depletion_start, total_evaporable_water
    )
    _check_day(day)

    if missing_constants is not None:
        return _missing_day(day.date, missing_constants)
    if isinstance(depletion_start, Missing):
        detail = "depletion at the start of the day"
        if depletion_start.detail is not None:
            detail = f"{detail}: {depletion_start.detail}"
        return _missing_day(day.date, Missing(reason="MISSING_INPUT", detail=detail))
    missing_names = [
        f"{name} ({getattr(day, name).reason})"
        for name in _DAY_NUMBERS
        if isinstance(getattr(day, name), Missing)
    ]
    if missing_names:
        detail = f"input of {day.date.isoformat()}: " + ", ".join(missing_names)
        return _missing_day(day.date, Missing(reason="MISSING_INPUT", detail=detail))

    tew = float(total_evaporable_water)
    precipitation = float(day.precipitation)
    runoff_asked = float(day.runoff)
    et0 = float(day.reference_evapotranspiration)
    kcb = float(day.basal_crop_coefficient)

    # 1: runoff from the precipitation of the day, then infiltration, which
    # refills the layer; the excess passes below it.
    runoff = min(runoff_asked, precipitation)
    runoff_shortfall = runoff_asked - runoff
    infiltration = precipitation - runoff
    if infiltration > depletion_start:
        deep_percolation = infiltration - depletion_start
        after_inflow = 0.0
    else:
        deep_percolation = 0.0
        after_inflow = depletion_start - infiltration

    # 2: the coefficients of the day.
    kr = evaporation_reduction_coefficient(
        depletion_start,
        total_evaporable_water=tew,
        readily_evaporable_water=readily_evaporable_water,
    )
    kc_max = upper_limit_of_crop_coefficient(
        kcb, day.climate_adjusted_upper_limit, margin_above_basal=margin_above_basal
    )
    few = exposed_and_wetted_fraction(day.cover_fraction, wetted_fraction)
    ke = evaporation_coefficient(kr, kc_max, kcb, few)

    # 3: evaporation, limited to the water left in the layer.
    evaporation_demanded = ke * et0
    room = tew - after_inflow
    if few > 0:
        depth_demanded = evaporation_demanded / few
        if depth_demanded <= room:
            depth = depth_demanded
            evaporation = evaporation_demanded
            depletion_end = after_inflow + depth
        else:
            depth = room
            evaporation = few * room
            depletion_end = tew
    else:
        # No exposed and wetted soil: Ke is zero, so nothing is demanded.
        depth = 0.0
        evaporation = 0.0
        depletion_end = after_inflow
    evaporation_shortfall = evaporation_demanded - evaporation

    return DayResult(
        date=day.date,
        depletion_start=depletion_start,
        depletion_end=depletion_end,
        precipitation=precipitation,
        runoff=runoff,
        infiltration=infiltration,
        deep_percolation=deep_percolation,
        reduction_coefficient=kr,
        upper_limit=kc_max,
        exposed_and_wetted_fraction=few,
        evaporation_coefficient=ke,
        evaporation_demanded=evaporation_demanded,
        evaporation=evaporation,
        evaporation_from_exposed_fraction=depth,
        evaporation_shortfall=evaporation_shortfall,
        runoff_shortfall=runoff_shortfall,
    )


def run_surface_layer(
    days: Sequence[DayInput],
    *,
    initial_depletion: Number,
    total_evaporable_water: Number,
    readily_evaporable_water: Number,
    wetted_fraction: Number,
    margin_above_basal: Number,
) -> list[DayResult]:
    """Run the balance of the surface layer over consecutive days.

    ``days`` holds one ``DayInput`` per day, in date order, with no day left
    out and none repeated. The depletion at the end of each day is the
    depletion at the start of the next; it is never reset. Which initial
    depletion to start from is OPEN (README); ``initial_depletion`` has no
    default.

    Once a day is missing, every later day is missing too, with reason
    ``MISSING_INPUT`` and a detail that names the first cause: the depletion
    is no longer known (C3.3). Nothing is filled in.

    Returns one ``DayResult`` per day, in the same order. Raises
    ``TypeError`` or ``ValueError`` only for a defect of the caller,
    including days that are not consecutive.
    """
    constants = {
        "total_evaporable_water": total_evaporable_water,
        "readily_evaporable_water": readily_evaporable_water,
        "wetted_fraction": wetted_fraction,
        "margin_above_basal": margin_above_basal,
    }
    _check_constants(constants)
    depletion: Number = _check_depletion(
        "initial_depletion", initial_depletion, total_evaporable_water
    )
    if isinstance(days, (str, bytes)) or not isinstance(days, Sequence):
        raise TypeError("days must be a sequence of DayInput")
    for index, day in enumerate(days):
        _check_day(day)
        if index > 0 and day.date != days[index - 1].date + datetime.timedelta(days=1):
            raise ValueError(
                f"days must be consecutive: day {index} does not follow day {index - 1}"
            )

    results: list[DayResult] = []
    cause: str | None = None
    if isinstance(depletion, Missing):
        cause = f"initial depletion ({depletion.reason})"
        depletion = Missing(reason="MISSING_INPUT", detail=f"missing since: {cause}")
    for day in days:
        result = step(depletion, day, **constants)
        results.append(result)
        if isinstance(result.depletion_end, Missing):
            if cause is None:
                cause = result.depletion_end.detail
            depletion = Missing(
                reason="MISSING_INPUT",
                detail=f"depletion after {day.date.isoformat()}, missing since: {cause}",
            )
        else:
            depletion = result.depletion_end
    return results
