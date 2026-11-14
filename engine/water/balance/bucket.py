"""Daily water balance of one soil column, one layer (decision D44, fallback).

Status: PROPOSED (blueprint section 3.7). The behaviour is described in
engine/water/balance/README.md and takes effect only when people approve it.
The form of the stress coefficient is PROPOSED and its source is
CITATION NEEDED (see ``stress_coefficient``).

``step`` moves the balance forward by one day; ``run_balance`` applies it to
a sequence of consecutive days, carrying the storage from each day to the
next and never resetting it. The daily mass balance is

    storage_end - storage_start = P - Q - E - T - D

with P precipitation, Q runoff, E evaporation, T transpiration and
D drainage, all depths of water over the day.

The module holds no parameter value and no unit string. Capacity, column
depth, initial storage, crop coefficients, root depths and readily available
fractions are arguments with no default. Depths of water share one unit and
lengths of soil share one unit, both chosen by the caller; the module only
adds, subtracts, multiplies and divides them and converts nothing.

A pure function: no file, no network, no clock, no global state. It does not
change its arguments, and the same arguments give the same result.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Sequence

from contracts.results.models import Missing

# The inputs of one day that are a number or a missing value, in the order a
# detail text names them.
_DAY_NUMBERS: tuple[str, ...] = (
    "precipitation",
    "runoff",
    "reference_evapotranspiration",
    "evaporation_coefficient",
)


@dataclass(frozen=True)
class CropDay:
    """The crop in the ground on one day, as the caller supplies it.

    Every field is supplied by the caller and none has a default: the values
    come from the parameter catalogue and the calendar, never from this
    module.

    - ``transpiration_coefficient``: the coefficient that multiplies the
      reference evapotranspiration to give the demanded transpiration (the
      ``Kcb`` of D44).
    - ``root_depth``: depth of the root zone on that day, in the length unit
      of ``column_depth``; greater than zero and not greater than
      ``column_depth``.
    - ``readily_available_fraction``: the fraction of the water the root zone
      can hold that the crop takes without stress (the readily available
      fraction of D44), between zero and one.
    """

    transpiration_coefficient: float
    root_depth: float
    readily_available_fraction: float


@dataclass(frozen=True)
class DayInput:
    """The inputs of one day.

    ``date`` labels the day (C5.2). Every other field is a number or the
    ``Missing`` of contracts/results/models.py with its reason (C3.1).

    - ``precipitation``, ``runoff``: depths of water over the day. Runoff is
      an input in this unit (the Curve Number of D44 is a later unit).
    - ``reference_evapotranspiration``: depth of water over the day, from
      engine/water/et0/ (another unit).
    - ``evaporation_coefficient``: the coefficient that multiplies the
      reference evapotranspiration to give the demanded evaporation (the
      ``Ke`` of D44). Supplied per day by the caller in this unit; the
      surface-layer balance that computes it is a later unit.
    - ``crop``: the crop in the ground, ``None`` on a day with no crop, or a
      ``Missing`` when it is not known whether or which crop is there.
    """

    date: datetime.date
    precipitation: float | Missing
    runoff: float | Missing
    reference_evapotranspiration: float | Missing
    evaporation_coefficient: float | Missing
    crop: CropDay | None | Missing


@dataclass(frozen=True)
class DayResult:
    """The balance of one day.

    Every quantity is a number or a ``Missing`` with its reason (C3.1). On a
    day whose inputs are complete, the flows and storages are numbers and

        storage_end - storage_start
            = precipitation - runoff - evaporation - transpiration - drainage

    holds to the precision of floating point. Fields:

    - ``storage_start``, ``storage_end``: water in the column at the start
      and end of the day, never below zero nor above the capacity.
    - ``precipitation``, ``runoff``, ``evaporation``, ``transpiration``,
      ``drainage``: the flows of the day as applied to the column.
    - ``evaporation_demanded``: evaporation coefficient times reference
      evapotranspiration.
    - ``transpiration_demanded``: transpiration coefficient times reference
      evapotranspiration; ``NOT_APPLICABLE`` on a day with no crop.
    - ``root_zone_depletion``: water missing from the root zone at the start
      of the day, against what it can hold; ``NOT_APPLICABLE`` with no crop.
    - ``stress_coefficient``: the coefficient that multiplies the demanded
      transpiration; ``NOT_APPLICABLE`` on a day with no crop.
    - ``runoff_shortfall``, ``evaporation_shortfall``,
      ``transpiration_shortfall``: the part of each outflow that was asked
      for and not supplied, because there was not that much water. Zero when
      the flow was supplied in full. ``transpiration_shortfall`` is against
      the stressed demand (stress coefficient times demanded transpiration)
      and is ``NOT_APPLICABLE`` on a day with no crop.
    """

    date: datetime.date
    storage_start: float | Missing
    storage_end: float | Missing
    precipitation: float | Missing
    runoff: float | Missing
    evaporation: float | Missing
    transpiration: float | Missing
    drainage: float | Missing
    evaporation_demanded: float | Missing
    transpiration_demanded: float | Missing
    root_zone_depletion: float | Missing
    stress_coefficient: float | Missing
    runoff_shortfall: float | Missing
    evaporation_shortfall: float | Missing
    transpiration_shortfall: float | Missing


# Quantities of a ``DayResult`` other than its date, in field order.
RESULT_QUANTITIES: tuple[str, ...] = tuple(
    name for name in DayResult.__dataclass_fields__ if name != "date"
)


# ---------------------------------------------------------------------------
# Checks on the caller's arguments. A defect of the caller raises; a missing
# value never does.


def _is_number(value: object) -> bool:
    """True for an ``int`` or a ``float``; a boolean is not a number here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_number(name: str, value: object) -> float:
    """Return ``value`` as a float, or raise for a defect of the caller."""
    if not _is_number(value):
        raise TypeError(f"{name} must be a number, not {type(value).__name__}")
    try:
        finite = math.isfinite(value)
    except OverflowError:  # an integer too large to be a float
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite number")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return float(value)


def _check_column(capacity: object, column_depth: object) -> tuple[float, float]:
    capacity = _check_number("capacity", capacity)
    column_depth = _check_number("column_depth", column_depth)
    if capacity == 0:
        raise ValueError("capacity must be greater than zero")
    if column_depth == 0:
        raise ValueError("column_depth must be greater than zero")
    return capacity, column_depth


def _check_storage(name: str, value: object, capacity: float) -> float | Missing:
    if isinstance(value, Missing):
        return value
    value = _check_number(name, value)
    if value > capacity:
        raise ValueError(f"{name} must not be greater than capacity")
    return value


def _check_crop(crop: object, column_depth: float) -> CropDay | None | Missing:
    if crop is None or isinstance(crop, Missing):
        return crop
    if not isinstance(crop, CropDay):
        raise TypeError(
            f"crop must be a CropDay, None or Missing, not {type(crop).__name__}"
        )
    _check_number("transpiration_coefficient", crop.transpiration_coefficient)
    root_depth = _check_number("root_depth", crop.root_depth)
    fraction = _check_number(
        "readily_available_fraction", crop.readily_available_fraction
    )
    if root_depth == 0:
        raise ValueError("root_depth of a crop must be greater than zero")
    if root_depth > column_depth:
        raise ValueError("root_depth must not be greater than column_depth")
    if fraction > 1:
        raise ValueError("readily_available_fraction must not be greater than one")
    return crop


def _check_day(day: object, column_depth: float) -> None:
    if not isinstance(day, DayInput):
        raise TypeError(f"a day must be a DayInput, not {type(day).__name__}")
    if not isinstance(day.date, datetime.date) or isinstance(
        day.date, datetime.datetime
    ):
        raise TypeError("date must be a datetime.date")
    for name in _DAY_NUMBERS:
        value = getattr(day, name)
        if not isinstance(value, Missing):
            _check_number(name, value)
    _check_crop(day.crop, column_depth)


# ---------------------------------------------------------------------------
# The stress coefficient.


def stress_coefficient(
    depletion: float, available_capacity: float, readily_available_fraction: float
) -> float:
    """Stress coefficient from the depletion of the root zone.

    Form PROPOSED; source CITATION NEEDED (a person confirms it against the
    source of D44 and writes the citation). With ``TAW`` the water the root
    zone can hold (``available_capacity``), ``RAW`` the readily available
    part of it (``readily_available_fraction * TAW``) and ``Dr`` the
    depletion:

    - ``Dr <= RAW``: the coefficient is one (no stress);
    - otherwise: ``(TAW - Dr) / (TAW - RAW)``, which falls from one at
      ``Dr = RAW`` to zero at ``Dr = TAW``.

    The arguments are checked by the caller of this function: ``TAW`` is
    greater than zero, ``Dr`` lies between zero and ``TAW``, the fraction
    between zero and one.
    """
    readily_available = readily_available_fraction * available_capacity
    if depletion <= readily_available:
        return 1.0
    return (available_capacity - depletion) / (available_capacity - readily_available)


# ---------------------------------------------------------------------------
# One day.


def _missing_day(date: datetime.date, missing: Missing) -> DayResult:
    return DayResult(date=date, **{name: missing for name in RESULT_QUANTITIES})


def _missing_inputs(day: DayInput) -> list[str]:
    names = []
    for name in (*_DAY_NUMBERS, "crop"):
        value = getattr(day, name)
        if isinstance(value, Missing):
            names.append(f"{name} ({value.reason})")
    return names


def step(
    storage_start: float | Missing,
    day: DayInput,
    *,
    capacity: float,
    column_depth: float,
) -> DayResult:
    """Move the balance of the column forward by one day.

    ``storage_start`` is the water in the column at the start of the day, or
    a ``Missing`` with its reason. ``capacity`` is the most water the column
    holds above its empty state, as a depth of water; ``column_depth`` is the
    depth of soil the column covers, in the length unit of the root depths.
    Both are supplied by the caller, with no default.

    The order within the day is PROPOSED (README, "PROPOSED rules"):

    1. Runoff leaves from the precipitation of the day; it is limited to that
       precipitation.
    2. The rest of the precipitation enters the column.
    3. The stress coefficient follows the depletion of the root zone at the
       start of the day.
    4. Evaporation is limited to the water in the column; then transpiration
       is limited to the water left in the root zone.
    5. Water above the capacity leaves as drainage.

    The storage is never clipped: a flow that asks for more water than there
    is gets limited, and the part not supplied is recorded in its shortfall.

    A missing input of the day, or a missing ``storage_start``, gives a day
    whose quantities are all missing with reason ``MISSING_INPUT`` and a
    detail naming what is missing (C3.3). Raises ``TypeError`` or
    ``ValueError`` only for a defect of the caller.
    """
    capacity, column_depth = _check_column(capacity, column_depth)
    storage_start = _check_storage("storage_start", storage_start, capacity)
    _check_day(day, column_depth)

    missing_names = _missing_inputs(day)
    if isinstance(storage_start, Missing):
        detail = "storage at the start of the day"
        if storage_start.detail is not None:
            detail = f"{detail}: {storage_start.detail}"
        return _missing_day(day.date, Missing(reason="MISSING_INPUT", detail=detail))
    if missing_names:
        detail = f"input of {day.date.isoformat()}: " + ", ".join(missing_names)
        return _missing_day(day.date, Missing(reason="MISSING_INPUT", detail=detail))

    precipitation = float(day.precipitation)
    runoff_asked = float(day.runoff)
    et0 = float(day.reference_evapotranspiration)
    evaporation_coefficient = float(day.evaporation_coefficient)
    crop = day.crop

    # 1, 2: runoff from the precipitation of the day, then infiltration.
    runoff = min(runoff_asked, precipitation)
    runoff_shortfall = runoff_asked - runoff
    after_inflow = storage_start + (precipitation - runoff)

    # 3: stress from the depletion of the root zone at the start of the day.
    # One layer: the water is spread evenly over the column, so the root zone
    # holds the share root_depth / column_depth of the column's water and of
    # its capacity.
    not_applicable = Missing(reason="NOT_APPLICABLE", detail="no crop on this day")
    if crop is None:
        share = 0.0
        transpiration_demanded: float | Missing = not_applicable
        depletion: float | Missing = not_applicable
        ks: float | Missing = not_applicable
        transpiration_asked = 0.0
    else:
        share = float(crop.root_depth) / column_depth
        available_capacity = capacity * share
        depletion = (capacity - storage_start) * share
        ks = stress_coefficient(
            depletion, available_capacity, float(crop.readily_available_fraction)
        )
        transpiration_demanded = float(crop.transpiration_coefficient) * et0
        transpiration_asked = ks * transpiration_demanded

    # 4: evaporation from the column, then transpiration from the root zone.
    evaporation_demanded = evaporation_coefficient * et0
    evaporation = min(evaporation_demanded, after_inflow)
    evaporation_shortfall = evaporation_demanded - evaporation
    after_evaporation = after_inflow - evaporation
    transpiration = min(transpiration_asked, after_evaporation * share)
    transpiration_shortfall: float | Missing = (
        not_applicable if crop is None else transpiration_asked - transpiration
    )
    after_outflow = after_evaporation - transpiration

    # 5: water above the capacity leaves as drainage.
    if after_outflow > capacity:
        drainage = after_outflow - capacity
        storage_end = capacity
    else:
        drainage = 0.0
        storage_end = after_outflow

    return DayResult(
        date=day.date,
        storage_start=storage_start,
        storage_end=storage_end,
        precipitation=precipitation,
        runoff=runoff,
        evaporation=evaporation,
        transpiration=transpiration,
        drainage=drainage,
        evaporation_demanded=evaporation_demanded,
        transpiration_demanded=transpiration_demanded,
        root_zone_depletion=depletion,
        stress_coefficient=ks,
        runoff_shortfall=runoff_shortfall,
        evaporation_shortfall=evaporation_shortfall,
        transpiration_shortfall=transpiration_shortfall,
    )


# ---------------------------------------------------------------------------
# A sequence of days.


def run_balance(
    days: Sequence[DayInput],
    *,
    initial_storage: float | Missing,
    capacity: float,
    column_depth: float,
) -> list[DayResult]:
    """Run the balance over consecutive days, never resetting the storage.

    ``days`` holds one ``DayInput`` per day, in date order, with no day left
    out and none repeated. The storage at the end of each day is the storage
    at the start of the next, across crops, fallow days and years.
    ``initial_storage`` is the water in the column at the start of the first
    day, or a ``Missing`` with its reason; which initial states are compared
    is OPEN (README).

    Once a day is missing, every later day is missing too, with reason
    ``MISSING_INPUT`` and a detail that names the first missing day and its
    missing inputs: its storage at the end is not known, so no later storage
    is (C3.3). Nothing is filled in.

    Returns one ``DayResult`` per day, in the same order. Raises
    ``TypeError`` or ``ValueError`` only for a defect of the caller,
    including days that are not consecutive.
    """
    capacity, column_depth = _check_column(capacity, column_depth)
    storage: float | Missing = _check_storage(
        "initial_storage", initial_storage, capacity
    )
    if isinstance(days, (str, bytes)) or not isinstance(days, Sequence):
        raise TypeError("days must be a sequence of DayInput")
    for index, day in enumerate(days):
        _check_day(day, column_depth)
        if index > 0 and day.date != days[index - 1].date + datetime.timedelta(days=1):
            raise ValueError(
                f"days must be consecutive: day {index} does not follow day {index - 1}"
            )

    results: list[DayResult] = []
    # What made the storage unknown, named once and repeated in every later
    # detail so that the cause travels with each missing day.
    cause: str | None = None
    if isinstance(storage, Missing):
        cause = f"initial storage ({storage.reason})"
        storage = Missing(reason="MISSING_INPUT", detail=f"missing since: {cause}")
    for day in days:
        result = step(storage, day, capacity=capacity, column_depth=column_depth)
        results.append(result)
        if isinstance(result.storage_end, Missing):
            if cause is None:
                cause = result.storage_end.detail
            storage = Missing(
                reason="MISSING_INPUT",
                detail=f"storage after {day.date.isoformat()}, missing since: {cause}",
            )
        else:
            storage = result.storage_end
    return results
