"""Daily surface runoff by the Curve Number method (decision D44 of issue #77).

Status: PROPOSED (blueprint section 3.7). The behaviour is described in
engine/water/runoff/README.md and takes effect only when people approve it.
The form of every equation is PROPOSED; a person confirms it against its
source, which is CITATION NEEDED.

The module holds no constant of the method. The initial-abstraction ratio,
the constants of the potential-retention formula and their unit factor are
fields of ``CurveNumberConstants``, supplied by the caller with no default.
The curve number of each day is an input the caller supplies with the day.
Until a person transcribes a constant (decision D34), the caller passes it as
the ``Missing`` of contracts/results/models.py, and every quantity that needs
it is missing with reason ``MISSING_INPUT``, naming the constant.

The only number the code writes is zero. The method carries no state from
one day to the next in this unit (no antecedent-moisture adjustment), so
each day is computed from its own inputs only.

Pure functions: no file, no network, no clock, no global state. They do not
change their arguments, and the same arguments give the same result.
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import get_args

from contracts.results.models import Missing, ReasonCode

# A number, or missing with its reason (C3.1).
Quantity = float | Missing

# CQ1 of contracts/CLIMATE_QUANTITIES.md (decision D23): the identifier of
# daily precipitation and the unit string it must arrive in. Transcribed from
# that file, not chosen here; a test checks them against its summary table.
PRECIPITATION = "precipitation"
PRECIPITATION_UNIT = "mm day-1"


@dataclass(frozen=True)
class CurveNumberConstants:
    """The constants of the Curve Number method, supplied by the caller.

    No field has a default and this class holds no value. Each field is a
    number or a ``Missing`` with its reason. The identifier of a constant is
    its field name; it is the identifier of the README table "Constants a
    person has to transcribe" and of the ``detail`` of a missing result.

    - ``initial_abstraction_ratio``: the ratio of the initial abstraction to
      the potential retention (``initial_abstraction``).
    - ``retention_numerator``: the number divided by the curve number in the
      potential-retention formula (``potential_retention``).
    - ``retention_offset``: the number subtracted from that quotient.
    - ``retention_unit_factor``: the factor that turns the retention of the
      formula into the depth unit of the precipitation.
    """

    initial_abstraction_ratio: Quantity
    retention_numerator: Quantity
    retention_offset: Quantity
    retention_unit_factor: Quantity


@dataclass(frozen=True)
class PrecipitationValue:
    """The precipitation of one day as it arrives: a number or missing, and its unit string.

    The unit string is kept when the value is missing (C3.1).
    """

    value: Quantity
    unit: str


@dataclass(frozen=True)
class RunoffDayInput:
    """The inputs of one day.

    - ``date``: the day (C5.2).
    - ``precipitation``: the precipitation of the day with its unit string.
    - ``curve_number``: the curve number of the field on that day, a number or
      a ``Missing`` with its reason. Which curve number applies to which soil
      group, crop, cover and condition is not decided (README, OPEN).
    """

    date: datetime.date
    precipitation: PrecipitationValue
    curve_number: Quantity


@dataclass(frozen=True)
class RunoffDayResult:
    """The runoff of one day and the two quantities it is computed from.

    Each is a number or a ``Missing`` with its reason (C3.1). ``runoff`` is a
    depth of water over the day, in the depth unit of the precipitation; it is
    never negative and never above the precipitation of the day.
    ``potential_retention`` and ``initial_abstraction`` are depths in that
    same unit.
    """

    date: datetime.date
    runoff: Quantity
    potential_retention: Quantity
    initial_abstraction: Quantity


# ---------------------------------------------------------------------------
# Operands. A value of the wrong type is a defect of the caller and raises
# TypeError; a missing or non-finite value never raises.


def _check_type(name: str, value: object) -> None:
    if isinstance(value, Missing):
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{name} must be a number or the Missing of "
            f"contracts.results.models, not {type(value).__name__}"
        )


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large to be a float
        return False


def _named(name: str, missing: Missing) -> str:
    """``name`` with the reason, and the detail if any, of its missing value."""
    if missing.detail is None:
        return f"{name} ({missing.reason})"
    return f"{name} ({missing.reason}: {missing.detail})"


def _absent(operands: dict[str, object]) -> Missing | None:
    """Why the operands cannot be used, or ``None`` when every one is a finite number.

    Every missing operand is named, with its own reason, under reason
    ``MISSING_INPUT`` (C3.3). Otherwise every non-finite operand is named under
    reason ``NOT_COMPUTABLE``. A missing operand is reported before a
    non-finite one. Raises ``TypeError`` for an operand of the wrong type.
    """
    for name, value in operands.items():
        _check_type(name, value)
    missing = [
        _named(name, value)
        for name, value in operands.items()
        if isinstance(value, Missing)
    ]
    if missing:
        return Missing(reason="MISSING_INPUT", detail=", ".join(missing))
    not_finite = [name for name, value in operands.items() if not _is_finite(value)]
    if not_finite:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="not a finite number: " + ", ".join(not_finite),
        )
    return None


def _not_computable(detail: str) -> Missing:
    return Missing(reason="NOT_COMPUTABLE", detail=detail)


def _check_constants(constants: object) -> CurveNumberConstants:
    if not isinstance(constants, CurveNumberConstants):
        raise TypeError(
            f"constants must be a CurveNumberConstants, not {type(constants).__name__}"
        )
    return constants


def _check_reason_code(unit_guard_reason: object) -> None:
    if unit_guard_reason not in get_args(ReasonCode):
        raise ValueError(
            "argument 'unit_guard_reason' must be a reason code of convention C3.2"
        )


# ---------------------------------------------------------------------------
# The equations. Each form is PROPOSED; its source is CITATION NEEDED.


def potential_retention(
    curve_number: Quantity, *, constants: CurveNumberConstants
) -> Quantity:
    """The potential maximum retention for a curve number.

    Form (PROPOSED, source CITATION NEEDED)::

        S = retention_unit_factor * (retention_numerator / CN - retention_offset)

    ``S`` is a depth of water in the depth unit of the precipitation.

    - A missing curve number or constant: ``MISSING_INPUT``, naming each.
    - A non-finite one: ``NOT_COMPUTABLE``, naming each.
    - A curve number outside its admissible range: ``NOT_COMPUTABLE``. PROPOSED
      reading of the admissible range, with no number of its own: the curve
      number is greater than zero and the retention it gives is a finite
      number not below zero (README, OPEN). Nothing is clipped.
    """
    constants = _check_constants(constants)
    absent = _absent(
        {
            "input 'curve_number'": curve_number,
            "constant 'retention_numerator'": constants.retention_numerator,
            "constant 'retention_offset'": constants.retention_offset,
            "constant 'retention_unit_factor'": constants.retention_unit_factor,
        }
    )
    if absent is not None:
        return absent
    if curve_number <= 0:
        return _not_computable(
            "input 'curve_number' is outside its admissible range: "
            "it is not greater than zero"
        )
    retention = constants.retention_unit_factor * (
        constants.retention_numerator / curve_number - constants.retention_offset
    )
    if not _is_finite(retention):
        return _not_computable(
            "the potential retention of input 'curve_number' is not a finite number"
        )
    if retention < 0:
        return _not_computable(
            "input 'curve_number' is outside its admissible range: "
            "its potential retention is below zero"
        )
    return float(retention)


def initial_abstraction(
    retention: Quantity, *, constants: CurveNumberConstants
) -> Quantity:
    """The initial abstraction: the precipitation of the day that gives no runoff.

    Form (PROPOSED, source CITATION NEEDED)::

        Ia = initial_abstraction_ratio * S

    - A missing retention or ratio: ``MISSING_INPUT``, naming each.
    - A non-finite one: ``NOT_COMPUTABLE``.
    - A retention or a ratio below zero: ``NOT_COMPUTABLE``. A negative ratio
      would let the runoff exceed the precipitation of the day (README,
      rule R3).
    """
    constants = _check_constants(constants)
    absent = _absent(
        {
            "potential retention": retention,
            "constant 'initial_abstraction_ratio'": (
                constants.initial_abstraction_ratio
            ),
        }
    )
    if absent is not None:
        return absent
    if retention < 0:
        return _not_computable("the potential retention is below zero")
    if constants.initial_abstraction_ratio < 0:
        return _not_computable("constant 'initial_abstraction_ratio' is below zero")
    abstraction = constants.initial_abstraction_ratio * retention
    if not _is_finite(abstraction):
        return _not_computable("the initial abstraction is not a finite number")
    return float(abstraction)


def _runoff(
    precipitation: Quantity, retention: Quantity, abstraction: Quantity
) -> Quantity:
    """The runoff equation applied to a precipitation, a retention and an initial abstraction.

    ``retention`` and ``abstraction`` come from ``potential_retention`` and
    ``initial_abstraction``, so each is missing or a finite number not below
    zero. The initial abstraction is computed from the retention, so it is
    named only when the retention is not missing itself.
    """
    _check_type(f"input '{PRECIPITATION}'", precipitation)
    names = []
    if isinstance(precipitation, Missing):
        names.append(_named(f"input '{PRECIPITATION}'", precipitation))
    if isinstance(retention, Missing):
        names.append(_named("potential retention", retention))
    elif isinstance(abstraction, Missing):
        names.append(_named("initial abstraction", abstraction))
    if names:
        return Missing(reason="MISSING_INPUT", detail=", ".join(names))
    if not _is_finite(precipitation):
        return _not_computable(f"not a finite number: input '{PRECIPITATION}'")
    if precipitation < 0:
        return _not_computable(f"below zero: input '{PRECIPITATION}'")
    if precipitation <= abstraction:
        return 0.0
    excess = precipitation - abstraction
    denominator = excess + retention
    if not _is_finite(denominator):
        return _not_computable("the runoff is not a finite number")
    return float(excess * (excess / denominator))


def runoff_depth(
    precipitation: Quantity,
    curve_number: Quantity,
    *,
    constants: CurveNumberConstants,
) -> Quantity:
    """The runoff of one day from its precipitation and its curve number.

    ``precipitation`` is a depth of water over the day, in the depth unit the
    retention formula gives (``retention_unit_factor``); this function holds
    no unit string (``runoff_day`` applies the unit guard). Form (PROPOSED,
    source CITATION NEEDED), with ``S`` from ``potential_retention`` and
    ``Ia`` from ``initial_abstraction``::

        Q = 0                                  when P <= Ia
        Q = (P - Ia) ** 2 / (P - Ia + S)       otherwise

    The code evaluates the second line as ``(P - Ia) * ((P - Ia) / (P - Ia +
    S))``, the same expression written so that ``Q`` stays not above ``P``
    under floating-point rounding too (README, rule R3).

    - A missing precipitation, curve number or constant: ``MISSING_INPUT``;
      the ``detail`` names each, with its reason, through the quantity that
      needs it.
    - A non-finite or negative precipitation: ``NOT_COMPUTABLE``. Nothing is
      clipped.
    - A curve number or constant that ``potential_retention`` or
      ``initial_abstraction`` cannot use: ``MISSING_INPUT``, naming that
      quantity and its reason.
    """
    constants = _check_constants(constants)
    retention = potential_retention(curve_number, constants=constants)
    abstraction = initial_abstraction(retention, constants=constants)
    return _runoff(precipitation, retention, abstraction)


# ---------------------------------------------------------------------------
# One day and a sequence of days.


def _check_precipitation(item: object) -> PrecipitationValue:
    if not isinstance(item, PrecipitationValue):
        raise TypeError(
            f"precipitation must be a PrecipitationValue, not {type(item).__name__}"
        )
    if not isinstance(item.unit, str):
        raise TypeError("the unit of the precipitation must be a string")
    _check_type(f"input '{PRECIPITATION}'", item.value)
    return item


def _check_day(day: object) -> RunoffDayInput:
    if not isinstance(day, RunoffDayInput):
        raise TypeError(f"a day must be a RunoffDayInput, not {type(day).__name__}")
    if not isinstance(day.date, datetime.date) or isinstance(
        day.date, datetime.datetime
    ):
        raise TypeError("date must be a datetime.date")
    _check_precipitation(day.precipitation)
    _check_type("input 'curve_number'", day.curve_number)
    return day


def _dated(quantity: Quantity, date: datetime.date) -> Quantity:
    """A missing quantity with the date of its day at the start of its detail."""
    if not isinstance(quantity, Missing):
        return quantity
    if quantity.detail is None:
        return Missing(reason=quantity.reason, detail=date.isoformat())
    return Missing(
        reason=quantity.reason, detail=f"{date.isoformat()}: {quantity.detail}"
    )


def runoff_day(
    day: RunoffDayInput,
    *,
    constants: CurveNumberConstants,
    unit_guard_reason: ReasonCode,
) -> RunoffDayResult:
    """The runoff of one day.

    ``constants`` holds the constants of the method; ``unit_guard_reason`` is
    the reason code of a precipitation in another unit string, supplied by the
    caller because it is not decided (Q11 of contracts/ENTRYPOINTS.md). Both
    have no default.

    Each quantity of the result is a number or missing with its reason, and
    its ``detail`` starts with the date of the day. The precipitation is
    needed only by the runoff: a missing precipitation leaves the retention
    and the initial abstraction computed.

    The precipitation must arrive in the unit string ``PRECIPITATION_UNIT``
    of contracts/CLIMATE_QUANTITIES.md. In another unit string it is not
    converted: the runoff is missing with ``unit_guard_reason``, naming both
    unit strings. A missing operand is reported before the unit, and the unit
    before a non-finite or negative precipitation. Raises ``TypeError`` for an argument
    of the wrong type and ``ValueError`` for a reason code outside C3.2.
    """
    constants = _check_constants(constants)
    _check_reason_code(unit_guard_reason)
    day = _check_day(day)
    retention = potential_retention(day.curve_number, constants=constants)
    abstraction = initial_abstraction(retention, constants=constants)
    precipitation = day.precipitation
    runoff = _runoff(precipitation.value, retention, abstraction)
    in_another_unit = (
        not isinstance(precipitation.value, Missing)
        and precipitation.unit != PRECIPITATION_UNIT
    )
    # The unit guard: a precipitation in another unit string is not converted.
    # A missing operand is reported before the unit, the unit before a
    # precipitation that is not a finite number or below zero.
    if in_another_unit and not (
        isinstance(runoff, Missing) and runoff.reason == "MISSING_INPUT"
    ):
        runoff = Missing(
            reason=unit_guard_reason,
            detail=(
                f"input '{PRECIPITATION}' is in the unit '{precipitation.unit}', "
                f"not in the accepted unit '{PRECIPITATION_UNIT}'"
            ),
        )
    return RunoffDayResult(
        date=day.date,
        runoff=_dated(runoff, day.date),
        potential_retention=_dated(retention, day.date),
        initial_abstraction=_dated(abstraction, day.date),
    )


def run_runoff(
    days: Sequence[RunoffDayInput],
    *,
    constants: CurveNumberConstants,
    unit_guard_reason: ReasonCode,
) -> list[RunoffDayResult]:
    """The runoff of every day of a sequence, one result per day, in the same order.

    No state is carried from one day to the next, so a missing day leaves
    the days after it computed. The order of the days is kept as given; this
    function neither sorts nor checks that the days are consecutive. Raises
    ``TypeError`` for an argument of the wrong type and ``ValueError`` for a
    reason code outside C3.2.
    """
    constants = _check_constants(constants)
    _check_reason_code(unit_guard_reason)
    if isinstance(days, (str, bytes)) or not isinstance(days, Sequence):
        raise TypeError("days must be a sequence of RunoffDayInput")
    for day in days:
        _check_day(day)
    return [
        runoff_day(day, constants=constants, unit_guard_reason=unit_guard_reason)
        for day in days
    ]
