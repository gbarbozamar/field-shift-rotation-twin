"""The three trend measures of ``soil_carbon_trend`` (contracts/CONVENTIONS.md C1.6).

C1.6 (DECIDED) asks for three computations of the trend of soil carbon, and
the user chooses which to see; the default is end minus start over the
horizon:

- ``end_minus_start``: the stock at the end of the horizon minus the stock at
  its start, divided by the length of the horizon;
- ``fitted_slope``: the slope of a line fitted to the stock over time;
- ``mean_over_cycles``: the mean change over whole rotation cycles.

The identifiers are those of ``TrendComputation`` in
contracts/results/models.py. How each is read here is PROPOSED, and the
source of each is CITATION NEEDED (C1.6):

- the change is divided by elapsed time, because C1.5 makes the indicator a
  change per year;
- the fitted line is an ordinary least-squares line through every point;
- the mean over cycles is the mean, over the whole cycles given, of the
  change of the stock over the cycle divided by the length of the cycle.

The horizon and the soil depth are OPEN in C1.6: they are values a person
supplies. Here the horizon is the series the caller passes: from its first
point to its last. Each measure is in the caller's carbon unit per the time
unit of ``times``; the unit of C1.5, ``t C ha-1 yr-1``, is reached only when
the stocks are in tonnes of carbon per hectare and the times in years.
Nothing is converted here.

Pure functions: no file, no network, no clock, no argument is changed. A
measure that is not computed is the ``Missing`` of contracts/results/models.py
with its reason: never zero, never a default, never "not a number".
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_types,
    finite,
    is_missing,
    no_finite_result,
    numbers_or_missing,
)
from .pools import Run

__all__ = [
    "TrendMeasures",
    "end_minus_start",
    "fitted_slope",
    "mean_over_cycles",
    "trend_measures",
]


def _check_series(stocks: object, times: object) -> None:
    for name, series in (("stocks", stocks), ("times", times)):
        if isinstance(series, (str, bytes)) or not isinstance(series, Sequence):
            raise TypeError(f"{name}: expected a sequence, got {type(series).__name__}")
    if len(stocks) != len(times):
        raise ValueError(
            f"stocks and times must have one item each per point: {len(stocks)} and {len(times)}"
        )
    check_types({f"stocks[{i}]": item for i, item in enumerate(stocks)})
    check_types({f"times[{i}]": item for i, item in enumerate(times)})


def _points(
    stocks: Sequence[NumberOrMissing],
    times: Sequence[NumberOrMissing],
    positions: Sequence[int],
) -> tuple[list[float], list[float]] | ResultMissing:
    """The stocks and times at ``positions`` as finite floats, or why not.

    The times at those positions must rise strictly: a series in time order.
    """
    numbers: dict[str, NumberOrMissing] = {}
    for i in positions:
        numbers[f"stocks[{i}]"] = stocks[i]
        numbers[f"times[{i}]"] = times[i]
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    at_stock = [values[f"stocks[{i}]"] for i in positions]
    at_time = [values[f"times[{i}]"] for i in positions]
    not_rising = [
        f"times[{positions[j + 1]}] is not after times[{positions[j]}]"
        for j in range(len(positions) - 1)
        if not at_time[j + 1] > at_time[j]
    ]
    if not_rising:
        return ResultMissing(reason="NOT_COMPUTABLE", detail="; ".join(not_rising))
    return at_stock, at_time


def _too_short(stocks: Sequence[object], function: str) -> ResultMissing | None:
    if len(stocks) <= 1:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"{function}: the series has fewer than two points, so it spans no time",
        )
    return None


def _finite_or_missing(function: str, value: float) -> float | ResultMissing:
    if finite(value) is None:
        return no_finite_result(function, "the measure")
    return value


def end_minus_start(
    *,
    stocks: Sequence[NumberOrMissing],
    times: Sequence[NumberOrMissing],
) -> float | ResultMissing:
    """The stock at the last point minus the stock at the first, over the time between them.

    Needs only the first and the last point. Returns the measure, or
    ``MISSING_INPUT`` (one of the two stocks or times is missing, named),
    or ``NOT_COMPUTABLE`` (fewer than two points, a value that is not finite,
    a last time not after the first).

    Raises ``TypeError`` for an argument of another type and ``ValueError``
    when ``stocks`` and ``times`` differ in length.
    """
    _check_series(stocks, times)
    short = _too_short(stocks, "end_minus_start")
    if short is not None:
        return short
    points = _points(stocks, times, (0, len(stocks) - 1))
    if isinstance(points, ResultMissing):
        return points
    (first, last), (start, end) = points
    return _finite_or_missing("end_minus_start", (last - first) / (end - start))


def fitted_slope(
    *,
    stocks: Sequence[NumberOrMissing],
    times: Sequence[NumberOrMissing],
) -> float | ResultMissing:
    """The slope of the ordinary least-squares line of stock on time, through every point.

    Returns the slope, or ``MISSING_INPUT`` (a stock or a time is missing,
    each named), or ``NOT_COMPUTABLE`` (fewer than two points, a value that
    is not finite, times that do not rise strictly).

    Raises as ``end_minus_start``.
    """
    _check_series(stocks, times)
    short = _too_short(stocks, "fitted_slope")
    if short is not None:
        return short
    points = _points(stocks, times, range(len(stocks)))
    if isinstance(points, ResultMissing):
        return points
    at_stock, at_time = points
    count = len(at_time)
    mean_time = math.fsum(at_time) / count
    mean_stock = math.fsum(at_stock) / count
    across = math.fsum(
        (t - mean_time) * (s - mean_stock)
        for t, s in zip(at_time, at_stock, strict=True)
    )
    spread = math.fsum((t - mean_time) * (t - mean_time) for t in at_time)
    try:
        return _finite_or_missing("fitted_slope", across / spread)
    except ZeroDivisionError:
        return no_finite_result("fitted_slope", "the measure")


def mean_over_cycles(
    *,
    stocks: Sequence[NumberOrMissing],
    times: Sequence[NumberOrMissing],
    cycle_boundaries: Sequence[int] | ResultMissing,
) -> float | ResultMissing:
    """The mean, over whole rotation cycles, of the change per unit time of each cycle.

    - ``cycle_boundaries``: the positions in ``stocks`` where each whole
      cycle starts and the last one ends, rising strictly; two positions make
      one cycle. Which cycles are whole is the caller's (it knows the
      rotation); a ``Missing`` gives ``MISSING_INPUT``.

    Returns the measure, or ``MISSING_INPUT`` (the boundaries, or a stock or
    time at a boundary, is missing; each named), or ``NOT_COMPUTABLE``
    (fewer than two boundaries, so no whole cycle; a position outside the
    series or not after the one before; a value that is not finite; times at
    the boundaries that do not rise strictly).

    Raises ``TypeError`` for an argument of another type and ``ValueError``
    when ``stocks`` and ``times`` differ in length.
    """
    _check_series(stocks, times)
    if is_missing(cycle_boundaries):
        detail = f"cycle_boundaries is missing, reason {cycle_boundaries.reason}"
        if cycle_boundaries.detail is not None:
            detail += f": {cycle_boundaries.detail}"
        return ResultMissing(reason="MISSING_INPUT", detail=detail)
    if isinstance(cycle_boundaries, (str, bytes)) or not isinstance(
        cycle_boundaries, Sequence
    ):
        raise TypeError(
            "cycle_boundaries: expected a sequence of positions, or a Missing; got "
            f"{type(cycle_boundaries).__name__}"
        )
    for item in cycle_boundaries:
        if isinstance(item, bool) or not isinstance(item, int):
            raise TypeError(
                f"cycle_boundaries: every position is an integer, got {type(item).__name__}"
            )
    if len(cycle_boundaries) <= 1:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="mean_over_cycles: fewer than two cycle boundaries, so no whole cycle",
        )
    wrong = [
        f"cycle boundary {position} is outside the series"
        for position in cycle_boundaries
        if not 0 <= position < len(stocks)
    ] + [
        f"cycle boundary {cycle_boundaries[j + 1]} is not after {cycle_boundaries[j]}"
        for j in range(len(cycle_boundaries) - 1)
        if not cycle_boundaries[j + 1] > cycle_boundaries[j]
    ]
    if wrong:
        return ResultMissing(reason="NOT_COMPUTABLE", detail="; ".join(wrong))
    points = _points(stocks, times, cycle_boundaries)
    if isinstance(points, ResultMissing):
        return points
    at_stock, at_time = points
    changes = [
        (at_stock[j + 1] - at_stock[j]) / (at_time[j + 1] - at_time[j])
        for j in range(len(at_stock) - 1)
    ]
    return _finite_or_missing("mean_over_cycles", math.fsum(changes) / len(changes))


@dataclass(frozen=True)
class TrendMeasures:
    """The three measures of C1.6 for one run.

    - ``values``: one item per identifier of ``TREND_COMPUTATIONS``, in its
      order: the measure, or the ``Missing`` of the results contract.
    - ``time_unit``: the time unit the measures are per, the run's
      ``duration_unit``.
    """

    values: Mapping[str, float | ResultMissing]
    time_unit: str


def trend_measures(
    *,
    run: Run,
    cycle_boundaries: Sequence[int] | ResultMissing,
) -> TrendMeasures:
    """All three measures of C1.6 from the total stocks of a run over its elapsed time.

    The series is ``run.total_stocks()`` over ``run.elapsed_times()``: the
    initial state and the end of every step. ``cycle_boundaries`` are
    positions in that series (``mean_over_cycles``). Every measure is present
    in the result; one that is not computed is missing with its reason.
    """
    if not isinstance(run, Run):
        raise TypeError(f"run: expected a Run, got {type(run).__name__}")
    stocks = run.total_stocks()
    times = run.elapsed_times()
    values = {
        "end_minus_start": end_minus_start(stocks=stocks, times=times),
        "fitted_slope": fitted_slope(stocks=stocks, times=times),
        "mean_over_cycles": mean_over_cycles(
            stocks=stocks, times=times, cycle_boundaries=cycle_boundaries
        ),
    }
    return TrendMeasures(values=values, time_unit=run.duration_unit)
