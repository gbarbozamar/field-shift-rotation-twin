"""Checks shared by the modules of this package. PROPOSED (blueprint section 3.7).

Nothing here is a value of the method: these helpers check the types of the
arguments, turn constants into finite floats or a ``Missing`` with its reason,
and combine the missing parts of a result (section 3 of
``contracts/CONVENTIONS.md``). ``README.md`` in this folder says what is
PROPOSED and what is OPEN.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import DailySeries
from contracts.results.models import Missing as ResultMissing

# PROPOSED. Reason code of a result that is not computed because a unit string
# is not the one accepted. The code for "a unit the engine does not accept" is
# not decided: Q11 of contracts/ENTRYPOINTS.md. Same choice as
# engine/erosion/ls.py.
REASON_UNIT_NOT_ACCEPTED = "NOT_COMPUTABLE"

# The two existing ``Missing`` shapes of the contracts. Either is accepted for a
# constant; a result is always the one of contracts/results/models.py.
MISSING = (InputMissing, ResultMissing)

YearMonth = tuple[int, int]


class NotFiniteReal(ArithmeticError):
    """A step of a form gave a complex number, an infinity or "not a number"."""


def check_constant_types(numbers: dict[str, object]) -> None:
    """An argument that is neither a number nor a ``Missing`` is a defect of the caller."""
    for name, item in numbers.items():
        if isinstance(item, MISSING):
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(
                f"{name}: expected a number, or a Missing of the contract models "
                f"with its reason; got {type(item).__name__}. A missing value is "
                "never passed as None"
            )


def check_text(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected text, got {type(value).__name__}")


def check_start_month(start_month: object) -> int:
    """The start month of the agricultural year (C5.4): an integer, January is 1 (C5.1)."""
    if isinstance(start_month, bool) or not isinstance(start_month, int):
        raise TypeError(
            f"start_month: expected an integer month number, got {type(start_month).__name__}"
        )
    if not 1 <= start_month <= 12:
        raise ValueError("start_month: a month number runs from 1 to 12 (C5.1)")
    return start_month


def finite(item: int | float) -> float | None:
    """The number as a float, or ``None`` when it is not a finite number."""
    try:
        number = float(item)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def constants_or_missing(
    numbers: dict[str, object],
) -> dict[str, float] | ResultMissing:
    """Every constant as a finite float, or the reason why nothing is computed.

    A missing constant comes first (C3.3): ``MISSING_INPUT``, naming every
    missing constant with its own reason. Then a constant that is not a finite
    number: ``NOT_COMPUTABLE``, named likewise.
    """
    absent = [
        describe_missing(name, item)
        for name, item in numbers.items()
        if isinstance(item, MISSING)
    ]
    if absent:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(absent))
    values = {name: finite(item) for name, item in numbers.items()}
    not_finite = [name for name, value in values.items() if value is None]
    if not_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in not_finite),
        )
    return values


def real(number: object) -> float:
    """The result of one step of a form, when it is a finite real number."""
    if isinstance(number, complex) or not math.isfinite(number):
        raise NotFiniteReal
    return float(number)


def describe_missing(name: str, missing: InputMissing | ResultMissing) -> str:
    text = f"{name} is missing, reason {missing.reason}"
    if missing.detail is not None:
        text += f": {missing.detail}"
    return text


def missing_input(name: str, missing: InputMissing | ResultMissing) -> ResultMissing:
    """C3.3: a result that needs a missing input is missing, and names it."""
    return ResultMissing(reason="MISSING_INPUT", detail=describe_missing(name, missing))


def combine_missing(parts: dict[str, object]) -> ResultMissing | None:
    """The ``Missing`` of a result built from ``parts``, or ``None`` when none is missing.

    PROPOSED. When every missing part is ``NO_COVERAGE`` (the extent of the
    series, C5.5), the result is ``NO_COVERAGE`` too. Otherwise it is
    ``MISSING_INPUT`` and names every missing part with its reason (C3.3).
    """
    missing = {name: item for name, item in parts.items() if isinstance(item, MISSING)}
    if not missing:
        return None
    text = "; ".join(describe_missing(name, item) for name, item in missing.items())
    if all(item.reason == "NO_COVERAGE" for item in missing.values()):
        return ResultMissing(reason="NO_COVERAGE", detail=text)
    return ResultMissing(reason="MISSING_INPUT", detail=text)


def check_mapping(name: str, value: object, key_check, what_keys: str) -> None:
    """A table produced by this package: a dict of numbers or ``Missing``, or one ``Missing``."""
    if isinstance(value, ResultMissing):
        return
    if not isinstance(value, Mapping):
        raise TypeError(
            f"{name}: expected a dict, or a Missing of contracts/results/models.py; "
            f"got {type(value).__name__}"
        )
    for key, item in value.items():
        if not key_check(key):
            raise TypeError(f"{name}: every key is {what_keys}; got {key!r}")
        if isinstance(item, ResultMissing):
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(
                f"{name}: every item is a number or a Missing of "
                f"contracts/results/models.py; got {type(item).__name__} for {key!r}"
            )


def is_date(key: object) -> bool:
    return isinstance(key, dt.date) and not isinstance(key, dt.datetime)


def is_year_month(key: object) -> bool:
    return (
        isinstance(key, tuple)
        and len(key) == 2
        and all(isinstance(part, int) and not isinstance(part, bool) for part in key)
        and 1 <= key[1] <= 12
    )


def is_year(key: object) -> bool:
    return isinstance(key, int) and not isinstance(key, bool)


def months_of_ag_year(ag_year: int, start_month: int) -> list[YearMonth]:
    """The twelve calendar months of an agricultural year, in order (C5.3)."""
    months = []
    year, month = ag_year, start_month
    for _ in range(12):
        months.append((year, month))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return months


def ag_year_of(year_month: YearMonth, start_month: int) -> int:
    """The agricultural year a calendar month belongs to: the year it begins in (C5.3)."""
    year, month = year_month
    return year if month >= start_month else year - 1


def label(year_month: YearMonth) -> str:
    year, month = year_month
    return f"{year:04d}-{month:02d}"


def check_series(series: object) -> None:
    if not isinstance(series, DailySeries):
        raise TypeError(
            "series: expected the DailySeries of contracts/inputs/site_climate.py, "
            f"got {type(series).__name__}"
        )


def check_fraction_table(name: str, table: object) -> None:
    if isinstance(table, ResultMissing):
        return
    if not isinstance(table, dict):
        raise TypeError(
            f"{name}: expected the dict that monthly_fractions returns, or a Missing; "
            f"got {type(table).__name__}"
        )
    for ag_year, months in table.items():
        if not is_year(ag_year):
            raise TypeError(
                f"{name}: every key is an agricultural year; got {ag_year!r}"
            )
        check_mapping(
            f"{name}[{ag_year}]", months, is_year_month, "a (year, month) pair"
        )
        if isinstance(months, ResultMissing):
            raise TypeError(f"{name}[{ag_year}]: expected a dict of months")
