"""Service-connected trivial comparators runner (unit W4-04, PROPOSED, blueprint section 3.7).

Bridges service inputs (``ResultsTable``, ``RotationCalendar``s, monthly
erosivity, daily precipitation, daily reference evapotranspiration, and the
parameter catalogue) to the three trivial comparators:

- ``D0`` (``validation/trivial_comparator.py``): ``compare_with_decision``;
- ``E0`` (``validation/trivial_comparator_erosion.py``): via the ``#399`` bridge
  ``flags_by_rotation_from_calendars``, ``year_shares``, and
  ``compare_with_soil_loss``;
- ``H0`` (``validation/trivial_comparator_water.py``): building daily
  ``WaterDay`` series from ``live_crop_over_record`` and ``basal_crop_coefficient``
  (``by_stage``) and running ``compare_with_full_indicator``.

Rules:

- Pure function (G1): no file, no clock, no network, no environment variable,
  and no argument is mutated.
- Holds no threshold, no tolerance, and no parameter value (G7).
- Preserves typed ``Missing`` cleanly whenever calendars, monthly erosivity,
  daily precipitation, daily ET0, or living-crop flags cannot evaluate a side.
  Never fills missing days and never fabricates thresholds or parameters.
- Strict G5 validation: raises ``TypeError`` on wrong argument types (including
  ``None`` in place of a typed ``Missing`` or mapping, or ``datetime.datetime``
  in place of ``datetime.date``) and ``ValueError`` on blank identifiers,
  malformed month keys, or mismatched ``case_id`` / ``field_id`` / ``rotation_id``.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from dataclasses import dataclass

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.results.models import Missing, ResultsTable
from engine.erosion.r_factor._checks import ag_year_of
from engine.erosion.r_factor.climatology import CALENDAR_MONTHS
from engine.water._parameters import Catalogue
from engine.water.exposure import (
    BASAL_CROP_COEFFICIENT,
    CROP_KEY,
    NO_CROP_ON_THE_DAY,
    STAGE_KEY,
    STAGES,
)
from engine.water.exposure import (
    INDICATOR as WATER_INDICATOR,
)
from engine.water.living_crop import (
    START_MONTH_UNKNOWN,
    live_crop_over_record,
)
from engine.water.stages import by_stage
from validation.trivial_comparator import (
    ComparisonItem,
    TrivialOrder,
    compare_with_decision,
)
from validation.trivial_comparator_erosion import (
    SOIL_LOSS,
    ErosionComparison,
    ErosionOrder,
    Flag,
    YearShare,
    compare_with_soil_loss,
    erosion_orders,
    flags_by_rotation_from_calendars,
    year_shares,
)
from validation.trivial_comparator_erosion import (
    Outcome as ErosionOutcome,
)
from validation.trivial_comparator_water import (
    WaterComparisonItem,
    WaterDay,
    WaterOrder,
    compare_with_full_indicator,
)

__all__ = [
    "DailySeriesInput",
    "MonthlyErosivityInput",
    "ServiceComparatorsReport",
    "run_service_comparators",
]

_ONE = 1
_ONE_DAY = dt.timedelta(days=_ONE)
_MISSING_TYPES = (Missing, InputMissing)

AnyMissing = Missing | InputMissing
MonthlyErosivityInput = Mapping[int, float | AnyMissing] | AnyMissing
DailySeriesInput = Mapping[dt.date, float | AnyMissing] | AnyMissing


@dataclass(frozen=True)
class ServiceComparatorsReport:
    """Immutable combined report of D0, E0, and H0 from service inputs.

    ``d0`` holds the decision comparator report (``compare_with_decision``).
    ``e0`` holds the erosion comparator report (``compare_with_soil_loss``), or
    a typed ``Missing`` when E0 as a whole cannot be evaluated.
    ``h0`` holds the water comparator report (``compare_with_full_indicator``),
    or a typed ``Missing`` when H0 as a whole cannot be evaluated.
    ``e0_year_shares`` holds the ``YearShare`` records when E0 runs, or the
    same ``Missing`` as ``e0``.
    ``e0_missing_by_scenario`` and ``h0_missing_by_scenario`` preserve the
    first typed ``Missing`` encountered per scenario when individual scenarios
    cannot evaluate a trivial comparator side.
    """

    case_id: str
    field_id: str
    d0: tuple[ComparisonItem, ...]
    e0: tuple[ErosionComparison, ...] | Missing
    h0: tuple[WaterComparisonItem, ...] | Missing
    e0_year_shares: tuple[YearShare, ...] | Missing = ()
    e0_missing_by_scenario: tuple[tuple[str, Missing], ...] = ()
    h0_missing_by_scenario: tuple[tuple[str, Missing], ...] = ()


def _as_result_missing(missing: AnyMissing) -> Missing:
    if isinstance(missing, Missing):
        return missing
    return Missing(reason=missing.reason, detail=missing.detail)


def _check_date_key(name: str, value: object) -> dt.date:
    if isinstance(value, dt.datetime) or not isinstance(value, dt.date):
        raise TypeError(
            f"{name}: every key must be datetime.date, got {type(value).__name__} (G5)"
        )
    return value


def _check_number_or_missing(
    name: str, key_repr: str, value: object
) -> float | Missing:
    if isinstance(value, _MISSING_TYPES):
        return _as_result_missing(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{name}[{key_repr}]: expected float or Missing, got {type(value).__name__} (G5)"
        )
    number = float(value)
    if not math.isfinite(number):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"{name}[{key_repr}] is not a finite number",
        )
    return number


def _check_table(table: object) -> ResultsTable:
    if not isinstance(table, ResultsTable):
        raise TypeError(
            f"table: expected ResultsTable, got {type(table).__name__} (G5)"
        )
    return table


def _check_calendars(
    calendars: object, table: ResultsTable
) -> dict[tuple[str, str], RotationCalendar]:
    if not isinstance(calendars, Mapping):
        raise TypeError(
            "calendars: expected Mapping[tuple[str, str], RotationCalendar], "
            f"got {type(calendars).__name__} (G5)"
        )
    checked: dict[tuple[str, str], RotationCalendar] = {}
    for key, calendar in calendars.items():
        if not isinstance(key, tuple) or len(key) != len((0, 1)):
            raise TypeError(
                "calendars: every key must be a (rotation_id, scenario_id) pair, "
                f"got {key!r} (G5)"
            )
        rotation_id, scenario_id = key
        if not isinstance(rotation_id, str) or not isinstance(scenario_id, str):
            raise TypeError(
                "calendars: rotation_id and scenario_id must be text, "
                f"got ({type(rotation_id).__name__}, {type(scenario_id).__name__}) (G5)"
            )
        if not rotation_id.strip() or not scenario_id.strip():
            raise ValueError(
                "calendars: rotation_id and scenario_id must be non-empty text (G5)"
            )
        if not isinstance(calendar, RotationCalendar):
            raise TypeError(
                f"calendars[{key!r}]: expected RotationCalendar, "
                f"got {type(calendar).__name__} (G5)"
            )
        if calendar.case_id != table.case_id or calendar.field_id != table.field_id:
            raise ValueError(
                f"calendars[{key!r}]: case_id/field_id ({calendar.case_id!r}, "
                f"{calendar.field_id!r}) do not match table ({table.case_id!r}, "
                f"{table.field_id!r}) (G5)"
            )
        if calendar.rotation_id != rotation_id:
            raise ValueError(
                f"calendars[{key!r}]: calendar.rotation_id ({calendar.rotation_id!r}) "
                f"does not match key rotation_id ({rotation_id!r}) (G5)"
            )
        checked[(rotation_id, scenario_id)] = calendar
    return checked


def _check_parameters(parameters: object) -> dict[str, dict]:
    if not isinstance(parameters, dict):
        raise TypeError(
            "parameters: expected dict[str, dict], "
            f"got {type(parameters).__name__} (G5)"
        )
    for key, record in parameters.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise TypeError(
                "parameters: expected dict[str, dict]: every key must be str "
                "and every value must be dict (G5)"
            )
    return parameters


def _check_erosivity(
    monthly_erosivity: object,
) -> dict[int, float | Missing] | Missing:
    if isinstance(monthly_erosivity, _MISSING_TYPES):
        return _as_result_missing(monthly_erosivity)
    if not isinstance(monthly_erosivity, Mapping):
        raise TypeError(
            "monthly_erosivity: expected Mapping[int, float | Missing] or Missing, "
            f"got {type(monthly_erosivity).__name__} (G5)"
        )
    for key in monthly_erosivity:
        if isinstance(key, bool) or not isinstance(key, int):
            raise TypeError(
                f"monthly_erosivity: every key must be an integer month, got {key!r} (G5)"
            )
    if set(monthly_erosivity) != set(CALENDAR_MONTHS):
        raise ValueError(
            "monthly_erosivity: expected exactly the twelve calendar months 1 to 12 "
            "(C5.1); a missing month must carry a typed Missing (G5)"
        )
    checked: dict[int, float | Missing] = {}
    for month in CALENDAR_MONTHS:
        val = monthly_erosivity[month]
        if isinstance(val, _MISSING_TYPES):
            checked[month] = _as_result_missing(val)
        elif isinstance(val, bool) or not isinstance(val, (int, float)):
            raise TypeError(
                f"monthly_erosivity[{month}]: expected float or Missing, "
                f"got {type(val).__name__} (G5)"
            )
        else:
            checked[month] = float(val)
    return checked


def _check_daily_series(
    name: str, series: object
) -> dict[dt.date, float | Missing] | Missing:
    if isinstance(series, _MISSING_TYPES):
        return _as_result_missing(series)
    if not isinstance(series, Mapping):
        raise TypeError(
            f"{name}: expected Mapping[datetime.date, float | Missing] or Missing, "
            f"got {type(series).__name__} (G5)"
        )
    checked: dict[dt.date, float | Missing] = {}
    for raw_day, raw_value in series.items():
        day = _check_date_key(name, raw_day)
        checked[day] = _check_number_or_missing(name, day.isoformat(), raw_value)
    return checked


def _resolve_window(
    calendars: Mapping[tuple[str, str], RotationCalendar],
    precip: dict[dt.date, float | Missing] | Missing,
    et0: dict[dt.date, float | Missing] | Missing,
) -> tuple[dt.date, dt.date] | None:
    if isinstance(precip, dict) and precip:
        return min(precip), max(precip)
    if isinstance(et0, dict) and et0:
        return min(et0), max(et0)
    if calendars:
        return (
            min(cal.start_date for cal in calendars.values()),
            max(cal.end_date for cal in calendars.values()),
        )
    return None


def _scenario_start_months(
    calendars: Mapping[tuple[str, str], RotationCalendar],
) -> dict[str, int | Missing]:
    by_scenario: dict[str, list[int | None]] = {}
    for (_, scenario_id), cal in calendars.items():
        by_scenario.setdefault(scenario_id, []).append(cal.ag_year_start.month)
    resolved: dict[str, int | Missing] = {}
    for scenario_id, months in sorted(by_scenario.items()):
        if any(month is None for month in months):
            resolved[scenario_id] = Missing(
                reason="MISSING_INPUT", detail=START_MONTH_UNKNOWN
            )
        elif len(set(months)) > _ONE:
            resolved[scenario_id] = Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"scenario '{scenario_id}': calendars do not share one "
                    f"ag_year_start.month ({sorted(set(months))})"
                ),
            )
        else:
            resolved[scenario_id] = int(months[0])
    return resolved


def _first_missing_share_by_scenario(
    shares: tuple[YearShare, ...],
) -> dict[str, Missing]:
    found: dict[str, Missing] = {}
    for item in shares:
        if item.missing is not None and item.scenario_id not in found:
            found[item.scenario_id] = item.missing
    return found


def _evaluate_e0(
    table: ResultsTable,
    calendars: Mapping[tuple[str, str], RotationCalendar],
    living_flags: Mapping[tuple[str, str], Mapping[dt.date, Flag]],
    erosivity: dict[int, float | Missing] | Missing,
    scenario_months: Mapping[str, int | Missing],
) -> tuple[
    tuple[ErosionComparison, ...] | Missing,
    tuple[YearShare, ...] | Missing,
    tuple[tuple[str, Missing], ...],
]:
    if isinstance(erosivity, Missing):
        return erosivity, erosivity, ()

    valid_scenarios = {s: m for s, m in scenario_months.items() if isinstance(m, int)}
    invalid_scenarios = {
        s: m for s, m in scenario_months.items() if isinstance(m, Missing)
    }
    if not valid_scenarios:
        first_scenario = min(invalid_scenarios)
        first_missing = invalid_scenarios[first_scenario]
        return (
            first_missing,
            first_missing,
            tuple(sorted(invalid_scenarios.items())),
        )

    if not invalid_scenarios and len(set(valid_scenarios.values())) == _ONE:
        shared_month = next(iter(valid_scenarios.values()))
        shares = year_shares(living_flags, erosivity, start_month=shared_month)
        comparisons = compare_with_soil_loss(
            living_flags, erosivity, table, start_month=shared_month
        )
        missing_shares = _first_missing_share_by_scenario(shares)
        missing_by_scenario: list[tuple[str, Missing]] = []
        for item in comparisons:
            if item.scenario_id in missing_shares:
                missing_by_scenario.append(
                    (item.scenario_id, missing_shares[item.scenario_id])
                )
            elif item.scenario_id not in valid_scenarios:
                missing_by_scenario.append(
                    (
                        item.scenario_id,
                        Missing(
                            reason="MISSING_INPUT",
                            detail=f"no calendar was provided for scenario '{item.scenario_id}'",
                        ),
                    )
                )
        return comparisons, shares, tuple(sorted(missing_by_scenario))

    # Mixed scenario start months or partially missing start months: isolate per scenario.
    from validation.trivial_comparator import trivial_orders

    full_by_scenario = {
        item.scenario_id: item
        for item in trivial_orders(table)
        if item.indicator == SOIL_LOSS
    }
    all_scenarios = sorted(set(scenario_months) | set(full_by_scenario))
    comparisons_list: list[ErosionComparison] = []
    shares_list: list[YearShare] = []
    missing_list: list[tuple[str, Missing]] = []

    for scenario_id in all_scenarios:
        if scenario_id in invalid_scenarios:
            missing = invalid_scenarios[scenario_id]
            theirs = full_by_scenario.get(scenario_id)
            full_reason = (
                f"the table holds no '{SOIL_LOSS}' of scenario '{scenario_id}'"
                if theirs is None
                else theirs.reason
            )
            full_order = None if theirs is None else theirs.order
            outcome: ErosionOutcome = (
                "no order from either"
                if full_order is None
                else "no order from the trivial comparator"
            )
            comparisons_list.append(
                ErosionComparison(
                    scenario_id=scenario_id,
                    trivial=ErosionOrder(
                        scenario_id, None, None, missing.detail or missing.reason
                    ),
                    full=theirs,
                    full_reason=full_reason,
                    outcome=outcome,
                    trivial_rotations_ordered=0,
                    full_rotations_ordered=len(full_order or ()),
                )
            )
            missing_list.append((scenario_id, missing))
        elif scenario_id in valid_scenarios:
            sm = valid_scenarios[scenario_id]
            living_s = {k: v for k, v in living_flags.items() if k[1] == scenario_id}
            shares_s = year_shares(living_s, erosivity, start_month=sm)
            shares_list.extend(shares_s)
            rows_s = [r for r in table.rows if r.scenario_id == scenario_id]
            if rows_s:
                sub_table = ResultsTable(
                    case_id=table.case_id, field_id=table.field_id, rows=rows_s
                )
                (comp_s,) = compare_with_soil_loss(
                    living_s, erosivity, sub_table, start_month=sm
                )
            else:
                (ours,) = erosion_orders(living_s, erosivity, start_month=sm)
                full_reason = (
                    f"the table holds no '{SOIL_LOSS}' of scenario '{scenario_id}'"
                )
                outcome = (
                    "no order from either"
                    if ours.order is None
                    else "no order from the full method"
                )
                comp_s = ErosionComparison(
                    scenario_id=scenario_id,
                    trivial=ours,
                    full=None,
                    full_reason=full_reason,
                    outcome=outcome,
                    trivial_rotations_ordered=len(ours.order or ()),
                    full_rotations_ordered=0,
                )
            comparisons_list.append(comp_s)
            missing_s = _first_missing_share_by_scenario(shares_s)
            if scenario_id in missing_s:
                missing_list.append((scenario_id, missing_s[scenario_id]))
        else:
            theirs = full_by_scenario[scenario_id]
            outcome = (
                "no order from either"
                if theirs.order is None
                else "no order from the trivial comparator"
            )
            comparisons_list.append(
                ErosionComparison(
                    scenario_id=scenario_id,
                    trivial=ErosionOrder(
                        scenario_id,
                        None,
                        None,
                        f"the flags of a living crop hold no rotation of scenario '{scenario_id}'",
                    ),
                    full=theirs,
                    full_reason=theirs.reason,
                    outcome=outcome,
                    trivial_rotations_ordered=0,
                    full_rotations_ordered=len(theirs.order or ()),
                )
            )
            missing_list.append(
                (
                    scenario_id,
                    Missing(
                        reason="MISSING_INPUT",
                        detail=f"no calendar was provided for scenario '{scenario_id}'",
                    ),
                )
            )

    return tuple(comparisons_list), tuple(shares_list), tuple(sorted(missing_list))


def _combine_whole_missing(first: Missing, second: Missing) -> Missing:
    d1 = first.detail or first.reason
    d2 = second.detail or second.reason
    return Missing(reason=first.reason, detail=f"{d1}; {d2}")


def _evaluate_h0(
    table: ResultsTable,
    calendars: Mapping[tuple[str, str], RotationCalendar],
    living_flags: Mapping[tuple[str, str], Mapping[dt.date, Flag]],
    precip: dict[dt.date, float | Missing] | Missing,
    et0: dict[dt.date, float | Missing] | Missing,
    parameters: dict[str, dict],
    record_start: dt.date,
    record_end: dt.date,
    scenario_months: Mapping[str, int | Missing],
) -> tuple[tuple[WaterComparisonItem, ...] | Missing, tuple[tuple[str, Missing], ...]]:
    if isinstance(precip, Missing) and isinstance(et0, Missing):
        combined = _combine_whole_missing(precip, et0)
        return combined, ()
    if isinstance(precip, Missing):
        return precip, ()
    if isinstance(et0, Missing):
        return et0, ()
    if not precip:
        return (
            Missing(
                reason="NO_COVERAGE",
                detail="daily_precipitation is empty: no day is covered",
            ),
            (),
        )
    if not et0:
        return (
            Missing(
                reason="NO_COVERAGE",
                detail="daily_et0 is empty: no day is covered",
            ),
            (),
        )

    valid_scenarios = {s: m for s, m in scenario_months.items() if isinstance(m, int)}
    invalid_scenarios = {
        s: m for s, m in scenario_months.items() if isinstance(m, Missing)
    }
    if not valid_scenarios:
        first_scenario = min(invalid_scenarios)
        return invalid_scenarios[first_scenario], tuple(
            sorted(invalid_scenarios.items())
        )

    catalogue = Catalogue(parameters)
    water_series: dict[tuple[str, str, int], tuple[WaterDay, ...]] = {}
    total_days = (record_end - record_start).days + _ONE

    for (rotation_id, scenario_id), calendar in sorted(calendars.items()):
        if scenario_id not in valid_scenarios:
            continue
        start_month = valid_scenarios[scenario_id]
        flags = living_flags[(rotation_id, scenario_id)]
        over = (
            live_crop_over_record(
                calendar, record_start, record_end, parameters=parameters
            )
            if calendar.feasibility.feasible
            else None
        )
        by_year: dict[int, list[WaterDay]] = {}
        for offset in range(total_days):
            day = record_start + dt.timedelta(days=offset)
            ag_year = ag_year_of((day.year, day.month), start_month)
            precip_day = precip.get(day)
            if precip_day is None:
                precip_day = Missing(
                    reason="NO_COVERAGE",
                    detail=f"daily_precipitation does not cover {day.isoformat()}",
                )

            flag = flags[day]
            if isinstance(flag, _MISSING_TYPES):
                demanded: float | Missing = _as_result_missing(flag)
            elif flag is False:
                demanded = Missing(
                    reason=NO_CROP_ON_THE_DAY,
                    detail="no living crop on the day",
                )
            else:
                if over is None:
                    demanded = Missing(
                        reason="NOT_COMPUTABLE",
                        detail="living-crop flag is True without a feasible calendar",
                    )
                else:
                    comp = over.component(day)
                    if isinstance(comp, Missing):
                        demanded = comp
                    elif comp is None:
                        demanded = Missing(
                            reason=NO_CROP_ON_THE_DAY,
                            detail="no living crop on the day",
                        )
                    else:
                        live = over.live_days(comp, day)
                        if isinstance(live, Missing):
                            demanded = live
                        elif not live.is_live(day):
                            demanded = Missing(
                                reason=NO_CROP_ON_THE_DAY,
                                detail="no living crop on the day",
                            )
                        else:
                            stage_day = live.stages[day]
                            kcb = by_stage(
                                stage_day,
                                *(
                                    catalogue.value(
                                        BASAL_CROP_COEFFICIENT,
                                        ((CROP_KEY, comp.crop_id), (STAGE_KEY, stage)),
                                        day,
                                    )
                                    for stage in STAGES
                                ),
                            )
                            et0_day = et0.get(day)
                            if isinstance(kcb, Missing):
                                demanded = kcb
                            elif et0_day is None:
                                demanded = Missing(
                                    reason="NO_COVERAGE",
                                    detail=f"daily_et0 does not cover {day.isoformat()}",
                                )
                            elif isinstance(et0_day, Missing):
                                demanded = et0_day
                            else:
                                product = kcb * et0_day
                                if not math.isfinite(product):
                                    demanded = Missing(
                                        reason="NOT_COMPUTABLE",
                                        detail=f"demanded transpiration on {day.isoformat()} is not finite",
                                    )
                                else:
                                    demanded = product

            by_year.setdefault(ag_year, []).append(
                WaterDay(
                    date=day,
                    precipitation=precip_day,
                    transpiration_demanded=demanded,
                )
            )
        for ag_year, days_of_year in sorted(by_year.items()):
            water_series[(rotation_id, scenario_id, ag_year)] = tuple(days_of_year)

    raw_items = compare_with_full_indicator(water_series, table)
    items_by_scenario = {item.scenario_id: item for item in raw_items}
    missing_by_scenario: dict[str, Missing] = {}

    for scenario_id, missing in invalid_scenarios.items():
        missing_by_scenario[scenario_id] = missing
        existing = items_by_scenario.get(scenario_id)
        if existing is not None:
            items_by_scenario[scenario_id] = WaterComparisonItem(
                scenario_id=scenario_id,
                trivial=WaterOrder(
                    scenario_id, (), None, None, missing.detail or missing.reason
                ),
                full=existing.full,
                outcome=existing.outcome,
                rotations_ordered=0,
                rotations_ordered_full=existing.rotations_ordered_full,
            )
        else:
            items_by_scenario[scenario_id] = WaterComparisonItem(
                scenario_id=scenario_id,
                trivial=WaterOrder(
                    scenario_id, (), None, None, missing.detail or missing.reason
                ),
                full=TrivialOrder(
                    scenario_id,
                    WATER_INDICATOR,
                    None,
                    None,
                    None,
                    f"the table holds no row of '{WATER_INDICATOR}' in scenario '{scenario_id}'",
                ),
                outcome="no order from either",
                rotations_ordered=0,
                rotations_ordered_full=0,
            )

    for scenario_id, item in items_by_scenario.items():
        if scenario_id in missing_by_scenario:
            continue
        for year_ratio in item.trivial.years:
            if year_ratio.missing is not None:
                missing_by_scenario[scenario_id] = year_ratio.missing
                break
        else:
            if scenario_id not in valid_scenarios:
                missing_by_scenario[scenario_id] = Missing(
                    reason="MISSING_INPUT",
                    detail=f"no calendar was provided for scenario '{scenario_id}'",
                )

    ordered_items = tuple(
        items_by_scenario[scenario_id] for scenario_id in sorted(items_by_scenario)
    )
    return ordered_items, tuple(sorted(missing_by_scenario.items()))


def run_service_comparators(
    table: ResultsTable,
    calendars: Mapping[tuple[str, str], RotationCalendar],
    monthly_erosivity: MonthlyErosivityInput,
    daily_precipitation: DailySeriesInput,
    daily_et0: DailySeriesInput,
    parameters: dict[str, dict],
) -> ServiceComparatorsReport:
    """Run D0, E0, and H0 comparators from service-layer inputs.

    Validates all arguments up front (G5), evaluates D0 from ``table``, builds
    daily living-crop flags via ``flags_by_rotation_from_calendars`` for E0 and
    H0, and preserves typed ``Missing`` cleanly whenever any comparator or
    scenario side cannot be evaluated.
    """
    checked_table = _check_table(table)
    checked_calendars = _check_calendars(calendars, checked_table)
    checked_erosivity = _check_erosivity(monthly_erosivity)
    checked_precip = _check_daily_series("daily_precipitation", daily_precipitation)
    checked_et0 = _check_daily_series("daily_et0", daily_et0)
    checked_parameters = _check_parameters(parameters)

    d0_report = compare_with_decision(checked_table)

    if not checked_calendars:
        no_cal = Missing(
            reason="MISSING_INPUT",
            detail="calendars holds no rotation calendar",
        )
        return ServiceComparatorsReport(
            case_id=checked_table.case_id,
            field_id=checked_table.field_id,
            d0=d0_report,
            e0=no_cal,
            h0=no_cal,
            e0_year_shares=no_cal,
        )

    window = _resolve_window(checked_calendars, checked_precip, checked_et0)
    assert window is not None  # checked_calendars is non-empty
    record_start, record_end = window

    living_flags = flags_by_rotation_from_calendars(
        checked_calendars,
        start_date=record_start,
        end_date=record_end,
        parameters=checked_parameters,
    )
    scenario_months = _scenario_start_months(checked_calendars)

    e0_report, e0_shares, e0_missing = _evaluate_e0(
        checked_table,
        checked_calendars,
        living_flags,
        checked_erosivity,
        scenario_months,
    )
    h0_report, h0_missing = _evaluate_h0(
        checked_table,
        checked_calendars,
        living_flags,
        checked_precip,
        checked_et0,
        checked_parameters,
        record_start,
        record_end,
        scenario_months,
    )

    return ServiceComparatorsReport(
        case_id=checked_table.case_id,
        field_id=checked_table.field_id,
        d0=d0_report,
        e0=e0_report,
        h0=h0_report,
        e0_year_shares=e0_shares,
        e0_missing_by_scenario=e0_missing,
        h0_missing_by_scenario=h0_missing,
    )
