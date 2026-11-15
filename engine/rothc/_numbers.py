"""Checks shared by the modules of ``engine/rothc/``. PROPOSED.

How an argument is read: a number, or a ``Missing`` of the contract models
with its reason (``contracts/CONVENTIONS.md`` C3). A missing argument makes
the result ``MISSING_INPUT`` and the detail names it (C3.3); an argument
that is not a finite number, or that lies outside what a quantity can be,
makes it ``NOT_COMPUTABLE``. Nothing is clipped, filled or defaulted.

This module holds no number of the method. The only numbers in it are the
bounds zero and one of a fraction, which are what the word "fraction" means.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

# The two existing ``Missing`` shapes of the contracts (question 24 of
# contracts/inputs/README.md). Either is accepted as an argument; a result is
# always the one of contracts/results/models.py.
MISSING_SHAPES = (InputMissing, ResultMissing)

# PROPOSED. Reason code of a result that is not computed because two unit
# strings that must be the same text are not. The code for "a unit the engine
# does not accept" is not decided: Q11 of contracts/ENTRYPOINTS.md. The same
# choice as engine/amg/, engine/erosion/ and engine/water/.
REASON_UNIT_NOT_ACCEPTED = "NOT_COMPUTABLE"

Number = int | float
NumberOrMissing = int | float | InputMissing | ResultMissing


def is_missing(item: object) -> bool:
    return isinstance(item, MISSING_SHAPES)


def is_number(item: object) -> bool:
    return isinstance(item, (int, float)) and not isinstance(item, bool)


def check_types(numbers: Mapping[str, object]) -> None:
    """An argument that is neither a number nor a ``Missing`` is a defect of the caller."""
    for name, item in numbers.items():
        if is_missing(item) or is_number(item):
            continue
        raise TypeError(
            f"{name}: expected a number, or a Missing of the contract models with "
            f"its reason; got {type(item).__name__}. A missing value is never "
            "passed as None"
        )


def check_text(name: str, item: object) -> None:
    if not isinstance(item, str):
        raise TypeError(f"{name}: expected text, got {type(item).__name__}")


def check_mapping(name: str, item: object) -> None:
    if not isinstance(item, Mapping):
        raise TypeError(f"{name}: expected a mapping, got {type(item).__name__}")
    for key in item:
        if not isinstance(key, str):
            raise TypeError(f"{name}: every key is text, got {type(key).__name__}")


def describe_missing(name: str, missing: InputMissing | ResultMissing) -> str:
    text = f"{name} is missing, reason {missing.reason}"
    if missing.detail is not None:
        text += f": {missing.detail}"
    return text


def finite(item: Number) -> float | None:
    """The number as a float, or ``None`` when it is not a finite number."""
    try:
        number = float(item)
    except OverflowError:  # an integer too large to be a float
        return None
    return number if math.isfinite(number) else None


# How ``run`` of pools.py opens the detail of a month that is not computed:
# "month <position>: <the rest>". The summary below reads that opening and
# nothing else of a detail.
_MONTH_OPENING = "month "
_MONTH_CLOSING = ": "


def _month_and_rest(detail: str | None) -> tuple[int | None, str | None]:
    """The month a detail names at its opening, and the detail after it.

    ``(None, detail)`` for a detail that does not open with "month <digits>: ".
    """
    if detail is None or not detail.startswith(_MONTH_OPENING):
        return None, detail
    head, closing, rest = detail.partition(_MONTH_CLOSING)
    position = head[len(_MONTH_OPENING) :]
    if not closing or not position.isdecimal():
        return None, detail
    return int(position), rest


def _series_and_index(name: str) -> tuple[str, int] | None:
    """``("stocks", 3)`` for the argument name "stocks[3]"; ``None`` without an index."""
    series, opening, index = name.rpartition("[")
    if not opening or not series or not index.endswith("]"):
        return None
    index = index[:-1]
    return (series, int(index)) if index.isdecimal() else None


def _runs(names: list[str]) -> list[str]:
    """The names as runs, in the order in which each run starts.

    A run is one series at consecutive indexes: "from stocks[3] to stocks[7]"
    stands for stocks[3], stocks[4], … stocks[7], every one of them in
    ``names``. An index that is not in ``names`` ends the run, so a run never
    spans an argument that is present. A name without an index is a run of its
    own and is written as it is: the names between two of them are not known
    to a reader, so none is left out.
    """
    runs: list[list[str]] = []
    # Per series: the index of its last name so far, and the run that holds it.
    latest: dict[str, tuple[int, list[str]]] = {}
    for name in names:
        found = _series_and_index(name)
        if found is None:
            runs.append([name])
            continue
        series, index = found
        previous = latest.get(series)
        if previous is not None and index == previous[0] + 1:
            run = previous[1]
            run.append(name)
        else:
            run = [name]
            runs.append(run)
        latest[series] = (index, run)
    return [
        f"from {run[0]} to {run[-1]}" if len(run) > 1 else run[0] for run in runs
    ]


def _group_detail(
    members: list[tuple[str, InputMissing | ResultMissing]],
) -> str:
    """The detail of one group: one argument as it always was, several as a summary."""
    if len(members) == 1:
        return describe_missing(*members[0])
    names = [name for name, _ in members]
    shared = members[0][1]
    summary = (
        f"{len(members)} arguments are missing ({', '.join(_runs(names))}), "
        f"reason {shared.reason}"
    )
    months = [_month_and_rest(item.detail)[0] for _, item in members]
    if months[0] is not None and min(months) != max(months):
        rest = _month_and_rest(shared.detail)[1]
        return (
            f"{summary}, each detail naming a month from {min(months)} to "
            f"{max(months)} and otherwise the same: {rest}"
        )
    if shared.detail is not None:
        summary += f": {shared.detail}"
    return summary


def _absent_detail(missing_items: list[tuple[str, InputMissing | ResultMissing]]) -> str:
    """The detail of a missing-input refusal: every missing argument, once.

    The missing arguments are put in groups. Two belong to one group when
    they carry the same reason and the same detail, or details that differ
    only in the month they name at their opening ("month <position>: …", as
    ``run`` of pools.py writes it). A group of one is written as it always
    was: its name, its reason, its detail. A group of more than one is
    written once: how many they are, which they are (``_runs``), the reason,
    and the detail they share; when their months differ, the lowest and the
    highest month named stand for them. The groups follow one another in the
    order of their first argument.

    So the length of the detail follows the number of groups and of runs,
    not the number of arguments, and every missing argument can still be
    found in it (G4 of contracts/ENTRYPOINTS.md). No reason and no value
    changes; when no two arguments share a group the detail is the one of
    before, character for character.
    """
    groups: dict[tuple, list[tuple[str, InputMissing | ResultMissing]]] = {}
    for name, item in missing_items:
        month, rest = _month_and_rest(item.detail)
        groups.setdefault((item.reason, month is not None, rest), []).append(
            (name, item)
        )
    return "; ".join(_group_detail(members) for members in groups.values())


def numbers_or_missing(
    numbers: Mapping[str, NumberOrMissing],
) -> dict[str, float] | ResultMissing:
    """Every argument as a finite float, or the reason why nothing is computed.

    A missing argument comes first (C3.3): ``MISSING_INPUT``. The detail
    names every missing argument with its reason: one by one, or, for
    arguments that share a reason and a detail, as one group written once
    (``_absent_detail``). Then an argument that is not a finite number:
    ``NOT_COMPUTABLE``, each named.
    """
    missing_items = [(name, item) for name, item in numbers.items() if is_missing(item)]
    if missing_items:
        return ResultMissing(reason="MISSING_INPUT", detail=_absent_detail(missing_items))
    values = {name: finite(item) for name, item in numbers.items()}
    not_finite = [name for name, value in values.items() if value is None]
    if not_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in not_finite),
        )
    return values


def outside(
    values: Mapping[str, float],
    names: Iterable[str],
    holds: Callable[[float], bool],
    what: str,
) -> ResultMissing | None:
    """``NOT_COMPUTABLE`` naming every argument of ``names`` for which ``holds`` fails."""
    failing = [name for name in names if not holds(values[name])]
    if not failing:
        return None
    return ResultMissing(
        reason="NOT_COMPUTABLE",
        detail="; ".join(f"{name} {what}" for name in failing),
    )


def is_fraction(value: float) -> bool:
    """Zero to one, both included: what a fraction can be."""
    return 0 <= value <= 1


def is_not_negative(value: float) -> bool:
    return value >= 0


def is_positive(value: float) -> bool:
    return value > 0


def units_differ(names_and_units: Mapping[str, str], how: str) -> ResultMissing | None:
    """``REASON_UNIT_NOT_ACCEPTED`` when the unit strings given are not all the same text."""
    if len(set(names_and_units.values())) <= 1:
        return None
    listed = " and ".join(
        f"{name} is in '{unit}'" for name, unit in names_and_units.items()
    )
    return ResultMissing(
        reason=REASON_UNIT_NOT_ACCEPTED,
        detail=f"{listed}: the units are {how} as given and need one unit",
    )


def unit_is_not(
    name: str, unit: str, expected: str, how: str
) -> ResultMissing | None:
    """``REASON_UNIT_NOT_ACCEPTED`` when one unit string is not the expected text."""
    if unit == expected:
        return None
    return ResultMissing(
        reason=REASON_UNIT_NOT_ACCEPTED,
        detail=(
            f"{name} is in '{unit}'; expected '{expected}', {how}: "
            "nothing is converted"
        ),
    )


def no_finite_result(function: str, what: str) -> ResultMissing:
    """The inputs are present and the form gives no finite real number."""
    return ResultMissing(
        reason="NOT_COMPUTABLE",
        detail=f"{function}: {what} is not a finite real number for these arguments",
    )


def real(number: float) -> float:
    """The result of one step of a form, when it is a finite real number."""
    if isinstance(number, complex) or not math.isfinite(number):
        raise ArithmeticError
    return number
