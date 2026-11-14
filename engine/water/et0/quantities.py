"""The inputs of the reference evapotranspiration, with the unit each must arrive in.

Status: PROPOSED (blueprint section 3.7).

The identifiers and unit strings of the five climate quantities are those of
contracts/CLIMATE_QUANTITIES.md (CQ2 to CQ6; decisions D25 to D27 and D35 of
issue #77). They are transcribed from that file, not chosen here, and the
tests check them against its summary table. A series in another unit string
is not converted: every value read from it is missing (the unit guard).

The unit strings of latitude and elevation are not decided (question 25 of
contracts/inputs/README.md): the caller supplies them in
``PointUnits``. The reason code of the unit guard is not decided either
(question Q11 of contracts/ENTRYPOINTS.md): the caller supplies it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from contracts.results.models import Missing, ReasonCode

from .equations import Quantity, check_operands

# CQ2 to CQ6 of contracts/CLIMATE_QUANTITIES.md: identifier -> unit string.
TEMPERATURE_MAX = "air_temperature_max_2m"  # CQ2, D35
TEMPERATURE_MIN = "air_temperature_min_2m"  # CQ3, D35
DEW_POINT = "dew_point_temperature_2m"  # CQ4, D25
WIND_SPEED_2M = "wind_speed_2m"  # CQ5, D26
SOLAR_RADIATION = "solar_radiation"  # CQ6, D27

ACCEPTED_UNITS: dict[str, str] = {
    TEMPERATURE_MAX: "degC",
    TEMPERATURE_MIN: "degC",
    DEW_POINT: "degC",
    WIND_SPEED_2M: "m s-1",
    SOLAR_RADIATION: "MJ m-2 day-1",
}

# The five quantities, in the order a missing day names them.
CLIMATE_QUANTITIES: tuple[str, ...] = tuple(ACCEPTED_UNITS)


@dataclass(frozen=True)
class InputValue:
    """One value as it arrives: a number or missing with its reason, and its unit string.

    The unit string is kept when the value is missing (C3.1).
    """

    value: float | Missing
    unit: str


@dataclass(frozen=True)
class PointUnits:
    """The unit strings the point of the series must arrive in (D9, D18).

    Supplied by the caller, no default. ``latitude_decimal_degrees`` is the
    unit string that means decimal degrees, which Eq. 22 converts to radians.
    ``elevation`` is the unit string in which the elevation enters Eq. 7 and
    Eq. 37.
    """

    latitude_decimal_degrees: str
    elevation: str


def check_reason_code(unit_guard_reason: object) -> None:
    """Raise ``ValueError`` unless the argument is a reason code of C3.2."""
    if unit_guard_reason not in get_args(ReasonCode):
        raise ValueError(
            "argument 'unit_guard_reason' must be a reason code of convention C3.2"
        )


def read_input(
    name: str,
    item: InputValue,
    accepted_unit: str,
    unit_guard_reason: ReasonCode,
) -> Quantity:
    """The number of ``item``, or why there is none.

    - The value is missing: reason ``MISSING_INPUT``; ``detail`` names ``name``.
    - The unit string is not ``accepted_unit``: reason ``unit_guard_reason``;
      ``detail`` names ``name`` and both unit strings. Nothing is converted.
    - The value is not a finite number: reason ``NOT_COMPUTABLE``.

    The first that applies, in that order, is returned. Unit strings are
    compared exactly as written. Raises ``TypeError`` for an argument of the
    wrong type and ``ValueError`` for a reason code outside C3.2.
    """
    if not isinstance(item, InputValue):
        raise TypeError(
            f"input '{name}' must be an InputValue, not {type(item).__name__}"
        )
    if not isinstance(item.unit, str):
        raise TypeError(f"the unit of input '{name}' must be a string")
    if not isinstance(accepted_unit, str):
        raise TypeError(f"the accepted unit of input '{name}' must be a string")
    check_reason_code(unit_guard_reason)
    if isinstance(item.value, Missing):
        return check_operands({f"input '{name}'": item.value})
    if item.unit != accepted_unit:
        check_operands(
            {f"input '{name}'": item.value}
        )  # raises for a value of the wrong type
        return Missing(
            reason=unit_guard_reason,
            detail=(
                f"input '{name}' is in the unit '{item.unit}', "
                f"not in the accepted unit '{accepted_unit}'"
            ),
        )
    absent = check_operands({f"input '{name}'": item.value})
    if absent is not None:
        return absent
    return float(item.value)
