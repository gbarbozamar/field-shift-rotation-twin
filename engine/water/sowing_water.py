"""Descriptive water available at the sowing of each crop (decisions D50 and D106).

Status: ``PROPOSED`` (blueprint section 3.7). Implements the descriptive measure
of ``contracts/CONVENTIONS.md`` (section C1.4, decisions D50 and D106 of issue
#77): **water available at the sowing of the next crop**, reported in ``mm``,
one value per sowing, descriptive only (no threshold, no weight in the
decision).

This module reuses the input validation, chain preparation, and continuous
daily water balance (``_run_chain``) of ``engine.water.exposure`` together with
``engine.calendar.repeat.repeat_over_record`` over the precipitation record
span (decisions D23, D44, D47, D109, D141, D188, D189). No water physics is
re-implemented here and no parameters are invented.

PROPOSED choices
----------------
1. **Entering-day column storage vs end-of-sowing-day storage.** Each sowing
   reports the column water storage *entering* the sowing day:
   ``initial_storage`` when the sowing falls on the first day of the
   precipitation record, otherwise ``balance.storage_end`` of the day before the
   sowing from the continuous daily balance (or ``Missing`` if that carried
   storage is missing). End-of-sowing-day ``storage_end`` is not used because
   D50/D106 ask for the water left by the preceding fallow or crop for the
   next crop at sowing, before sowing-day inflows and outflows act.
2. **Column storage vs root-zone share.** Reports total column water storage
   (the state carried across days in ``engine.water.balance``) rather than
   multiplying by ``initial_root_depth / column_depth`` or subtracting an
   unparameterized wilting threshold.
3. **Unit string ``"mm"``.** Decision D106 specifies ``mm``; ``contracts/CONVENTIONS.md``
   (C1.1, C1.4) does not yet fix the unit string or contract identifier.
4. **Occurrences reported.** Every ``RepeatedComponent`` laid out by
   ``repeat_over_record`` over ``[record.start_date, record.end_date]`` whose
   ``start`` date is declared is reported, in cycle-by-cycle calendar order
   (including ``LEAD_IN = -1`` when present). An occurrence whose sowing date
   lies outside ``[record.start_date, record.end_date]`` (for example, a D141
   crossing component sown before the record, or a late-cycle component sown
   after the record ends) receives ``Missing(reason="NO_COVERAGE", ...)`` and
   never borrows day-1 storage (``engine/water/EXPOSURE.md`` OPEN 39).
5. **Precedence of early and common missing reasons (matching EP3).**
   ``_check_types`` and ``_check_same_field`` run first (G5). When
   ``ag_year_start.month`` or the daily ``precipitation`` series is missing so
   the repetition cannot be laid out, one sentinel item with
   ``sowing_date=None`` and ``reason="MISSING_INPUT"`` is returned. Otherwise
   infeasible calendars and mixed time zones produce ``NOT_COMPUTABLE`` across
   occurrences, out-of-record sowings produce ``NO_COVERAGE``, unaccepted input
   units produce ``MISSING_INPUT``, and carried storage gaps report ``Missing``
   with the underlying cause.

OPEN questions (for science reviewers and lead developer)
---------------------------------------------------------
- **Balance state (C1.4, ``engine/water/balance/README.md`` OPEN 8):** whether
  D50/D106 should report entering-day column ``storage_start`` (previous day's
  ``storage_end``), end-of-sowing-day ``storage_end``, or the root-zone share.
- **Contract identifier and unit string (C1.4, ``EXPOSURE.md`` OPEN 16):** the
  identifier, unit string, and results-contract field for descriptive measures
  remain open.
- **Undated sowings and termination comparison (C1.4, D4, D50):** whether
  components without a declared start date should be omitted (as here) or
  emitted with ``sowing_date=None``, and how cover-crop termination dates are
  compared.

Pure function (G1): no file I/O, no network, no clock, no environment variables,
and the arguments are not mutated.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import Missing
from engine.calendar.repeat import RepeatedRotation, repeat_over_record
from engine.water import balance, exposure
from engine.water._parameters import Catalogue

__all__ = [
    "SowingAvailableWater",
    "UNIT_SOWING_AVAILABLE_WATER",
    "compute_sowing_available_water",
]

# PROPOSED unit string per D106 ("in mm"); unit string in C1.1/C1.4 is OPEN.
UNIT_SOWING_AVAILABLE_WATER = "mm"


@dataclass(frozen=True)
class SowingAvailableWater:
    """Column water storage entering one repeated sowing occurrence (D50, D106)."""

    component_id: str
    crop_id: str
    cycle_index: int
    sowing_date: dt.date | None
    value: float | Missing
    unit: str


def _sentinel_missing(missing: Missing) -> SowingAvailableWater:
    return SowingAvailableWater(
        component_id="",
        crop_id="",
        cycle_index=0,
        sowing_date=None,
        value=missing,
        unit=UNIT_SOWING_AVAILABLE_WATER,
    )


def _units_not_accepted(problems: list[str]) -> Missing:
    return Missing(
        reason="MISSING_INPUT",
        detail=(
            "sowing_available_water is not computed: an input arrives in a unit "
            "string the water engine does not accept, and nothing is converted "
            "(C1.1); the reason code for that case is not decided (Q11 of "
            "contracts/ENTRYPOINTS.md), and MISSING_INPUT is PROPOSED: "
            + "; ".join(problems)
        ),
    )


def _outside_record(sowing_date: dt.date, record: DailySeries) -> Missing:
    return Missing(
        reason="NO_COVERAGE",
        detail=(
            f"sowing date {sowing_date.isoformat()} lies outside the climate "
            f"precipitation record ({record.start_date.isoformat()} to "
            f"{record.end_date.isoformat()}) (C5.5, decision D141; "
            "engine/water/EXPOSURE.md OPEN 39)"
        ),
    )


def _day_one_storage(
    sowing_date: dt.date,
    catalogue: Catalogue,
    chain_by_day: dict[dt.date, exposure.ChainDay],
) -> float | Missing:
    """Column storage entering day 1 of the record (``initial_storage``)."""
    day_one = chain_by_day.get(sowing_date)
    if day_one is not None and not isinstance(day_one.balance.storage_start, Missing):
        return day_one.balance.storage_start

    initial = exposure._site(catalogue, exposure.INITIAL_STORAGE, sowing_date)
    if isinstance(initial, Missing):
        return initial

    capacity = exposure._site(catalogue, exposure.COLUMN_CAPACITY, sowing_date)
    column_depth = exposure._site(catalogue, exposure.COLUMN_DEPTH, sowing_date)
    column_missing = [
        item for item in (capacity, column_depth) if isinstance(item, Missing)
    ]
    if column_missing:
        return Missing(
            reason="MISSING_INPUT",
            detail="the column of the balance: "
            + "; ".join(
                item.detail for item in column_missing if item.detail is not None
            ),
        )

    try:
        validated = balance.step(
            initial,
            balance.DayInput(
                date=sowing_date,
                precipitation=0.0,
                runoff=0.0,
                reference_evapotranspiration=0.0,
                evaporation_coefficient=0.0,
                crop=None,
            ),
            capacity=capacity,
            column_depth=column_depth,
        )
    except ValueError as error:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"the daily balance refuses a value: {error}",
        )
    return validated.storage_start


def _carried_storage_missing(
    sowing_date: dt.date,
    prev_day: dt.date,
    carried: Missing,
    catalogue: Catalogue,
    notes: exposure._Notes,
) -> Missing:
    extra = [
        *(
            f"parameter MISSING_INPUT: {item}"
            for item in catalogue.problems_until(prev_day)
        ),
        *(f"chain {item}" for item in notes.until(prev_day)),
    ]
    why = carried.detail if carried.detail is not None else carried.reason
    base = (
        f"column water storage entering sowing date {sowing_date.isoformat()} "
        f"(end of {prev_day.isoformat()}) is not computed ({carried.reason}: {why})"
    )
    detail = f"{base}; " + "; ".join(extra) if extra else base
    return Missing(reason=carried.reason, detail=detail)


def _storage_entering_sowing(
    sowing_date: dt.date,
    record: DailySeries,
    present: list[str],
    by_quantity: dict[str, DailySeries],
    catalogue: Catalogue,
    chain_by_day: dict[dt.date, exposure.ChainDay],
    notes: exposure._Notes,
) -> float | Missing:
    if sowing_date == record.start_date:
        return _day_one_storage(sowing_date, catalogue, chain_by_day)

    prev_day = sowing_date - exposure._ONE_DAY
    prev_chain = chain_by_day.get(prev_day)
    if prev_chain is None:
        not_covering = [
            name for name in present if by_quantity[name].start_date > prev_day
        ]
        names = (
            ", ".join(f"'{name}'" for name in not_covering)
            if not_covering
            else f"'{exposure.PRECIPITATION}'"
        )
        return Missing(
            reason="NO_COVERAGE",
            detail=(
                f"the daily series {names} do not cover {prev_day.isoformat()}, "
                f"the day before sowing date {sowing_date.isoformat()}, so carried "
                "column storage is not computed (C5.5)"
            ),
        )

    carried = prev_chain.balance.storage_end
    if isinstance(carried, Missing):
        return _carried_storage_missing(sowing_date, prev_day, carried, catalogue, notes)
    return carried


def compute_sowing_available_water(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    parameters: dict[str, dict],
) -> list[SowingAvailableWater]:
    """Column water storage entering each repeated sowing occurrence (D50, D106).

    Validates inputs identically to ``engine.water.compute_water_deficit_exposure``,
    repeats ``calendar`` over the climate ``precipitation`` record span via
    ``repeat_over_record``, and runs ``engine.water.exposure._run_chain`` once.
    """
    exposure._check_types(calendar, climate, soil_slope, parameters)
    exposure._check_same_field(calendar, climate, soil_slope)

    if calendar.ag_year_start.month is None:
        return [
            _sentinel_missing(
                Missing(reason="MISSING_INPUT", detail=exposure.START_MONTH_MISSING)
            )
        ]

    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in exposure.DAILY_INPUTS
    }
    record = by_quantity.get(exposure.PRECIPITATION)
    if record is None:
        return [
            _sentinel_missing(
                Missing(reason="MISSING_INPUT", detail=exposure.RECORD_MISSING)
            )
        ]

    repeated = repeat_over_record(calendar, record.start_date, record.end_date)
    if isinstance(repeated, Missing) or not isinstance(repeated, RepeatedRotation):
        missing = (
            repeated
            if isinstance(repeated, Missing)
            else Missing(reason="MISSING_INPUT", detail=exposure.REPETITION_NOT_LAID_OUT)
        )
        return [_sentinel_missing(missing)]

    sowings = [comp for comp in repeated.components if comp.start is not None]
    if not sowings:
        return []

    present = [name for name in exposure.DAILY_INPUTS if name in by_quantity]
    if not calendar.feasibility.feasible:
        common: Missing | None = Missing(
            reason="NOT_COMPUTABLE", detail=exposure.INFEASIBLE
        )
    elif exposure._mixed_time_zones([by_quantity[name] for name in present]):
        common = Missing(reason="NOT_COMPUTABLE", detail=exposure.MIXED_TIME_ZONES)
    else:
        common = None
    units = exposure._unit_problems(climate, by_quantity) if common is None else []

    catalogue = Catalogue(parameters)
    notes = exposure._Notes()
    chain_by_day: dict[dt.date, exposure.ChainDay] = {}
    if common is None and not units:
        chain = exposure._run_chain(
            calendar,
            climate,
            catalogue,
            by_quantity,
            exposure._chain_days(record, present, by_quantity),
            notes,
        )
        chain_by_day = {item.date: item for item in chain}

    results: list[SowingAvailableWater] = []
    for comp in sowings:
        sowing_date = comp.start
        assert sowing_date is not None
        if common is not None:
            value: float | Missing = common
        elif sowing_date < record.start_date or sowing_date > record.end_date:
            value = _outside_record(sowing_date, record)
        elif units:
            value = _units_not_accepted(units)
        else:
            value = _storage_entering_sowing(
                sowing_date,
                record,
                present,
                by_quantity,
                catalogue,
                chain_by_day,
                notes,
            )
        results.append(
            SowingAvailableWater(
                component_id=comp.component_id,
                crop_id=comp.crop_id,
                cycle_index=comp.cycle,
                sowing_date=sowing_date,
                value=value,
                unit=UNIT_SOWING_AVAILABLE_WATER,
            )
        )
    return results
