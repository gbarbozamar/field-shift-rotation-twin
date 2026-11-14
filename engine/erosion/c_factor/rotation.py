"""Factor ``C`` of a rotation, weighted by the erosivity of each month. PROPOSED.

docs/METHODS.md M1.5: ``C`` for a rotation is the sum, over the months of the
rotation, of the fraction of annual erosivity of the month (M1.2) times the
soil-loss ratio of the month, divided by the number of years of the
rotation. Source: S1::

    C = sum over months m of (erosivity_fraction[m] * soil_loss_ratio[m]) / number_of_years

The fractions are an input here: they are computed by the unit of M1.2. They
are never normalised. Each year's fractions of annual erosivity add up to
one, so over a rotation of ``number_of_years`` years they are expected to add
up to ``number_of_years`` (PROPOSED reading of M1.5). The result reports the
sum, the expected sum and whether the two agree within a tolerance that the
caller supplies; it does not change any fraction, and it does not withhold
``C`` when they disagree (README.md of this folder, OPEN).

A pure function: no file, no network, no clock, no argument is changed. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason: never zero, never a default, never "not a number".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_text,
    check_types,
    describe_missing,
    finite,
    is_fraction,
    is_missing,
    numbers_or_missing,
    outside,
    real,
)
from .subfactors import DECLARED_LIMIT, SET_TO_ONE, SoilLossRatio

__all__ = [
    "MonthOfRotation",
    "RotationC",
    "rotation_c",
]


@dataclass(frozen=True)
class MonthOfRotation:
    """One month of the rotation.

    - ``label``: how the month is named in a ``detail``, for example its
      rotation year and month number. Text; not read otherwise.
    - ``erosivity_fraction``: the fraction of annual erosivity that falls in
      the month (M1.2), a number or a ``Missing``.
    - ``soil_loss_ratio``: the soil-loss ratio of the month, as returned by
      ``soil_loss_ratio``, which carries the sub-factors set to one.
    """

    label: str
    erosivity_fraction: NumberOrMissing
    soil_loss_ratio: SoilLossRatio


@dataclass(frozen=True)
class RotationC:
    """Factor ``C`` of a rotation, and the check of its erosivity fractions.

    - ``value``: ``C``, or the ``Missing`` of the results contract with its reason.
    - ``fraction_sum``: the sum of the erosivity fractions of all months, or
      a ``Missing`` when a fraction is missing, not a finite number, or
      outside zero to one. It is
      reported whether or not ``value`` is computed.
    - ``expected_fraction_sum``: the number of years of the rotation, or a
      ``Missing`` when that number is missing or not usable.
    - ``fractions_add_up``: ``True`` when ``fraction_sum`` and
      ``expected_fraction_sum`` differ by no more than the tolerance,
      ``False`` when they differ by more, or a ``Missing`` when one of the
      three is missing or not usable.
    - ``set_to_one`` and ``limit``: the sub-factors that stand at one in
      every soil-loss ratio of the rotation, and where that limit is
      declared (D45).
    """

    value: float | ResultMissing
    fraction_sum: float | ResultMissing
    expected_fraction_sum: float | ResultMissing
    fractions_add_up: bool | ResultMissing
    set_to_one: tuple[str, ...]
    limit: str


def _check_arguments(
    months: object,
    number_of_years: object,
    fraction_sum_tolerance: object,
) -> None:
    if isinstance(months, (str, bytes)) or not isinstance(months, Sequence):
        raise TypeError(
            f"months: expected a sequence of MonthOfRotation, got {type(months).__name__}"
        )
    for index, month in enumerate(months):
        if not isinstance(month, MonthOfRotation):
            raise TypeError(
                f"months[{index}]: expected a MonthOfRotation, "
                f"got {type(month).__name__}"
            )
        check_text(f"months[{index}].label", month.label)
        check_types({f"months[{index}].erosivity_fraction": month.erosivity_fraction})
        if not isinstance(month.soil_loss_ratio, SoilLossRatio):
            raise TypeError(
                f"months[{index}].soil_loss_ratio: expected a SoilLossRatio, "
                f"got {type(month.soil_loss_ratio).__name__}"
            )
        check_types(
            {f"months[{index}].soil_loss_ratio.value": month.soil_loss_ratio.value}
        )
    if not is_missing(number_of_years) and (
        isinstance(number_of_years, bool) or not isinstance(number_of_years, int)
    ):
        raise TypeError(
            "number_of_years: expected a whole number, or a Missing of the contract "
            f"models with its reason; got {type(number_of_years).__name__}"
        )
    check_types({"fraction_sum_tolerance": fraction_sum_tolerance})


def _expected_sum(
    number_of_years: int | InputMissing | ResultMissing,
) -> float | ResultMissing:
    if is_missing(number_of_years):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=describe_missing("number_of_years", number_of_years),
        )
    if number_of_years <= 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="number_of_years is not a whole number above zero",
        )
    years = finite(number_of_years)
    if years is None:
        return ResultMissing(
            reason="NOT_COMPUTABLE", detail="number_of_years is not a finite number"
        )
    return years


def _fractions_outside(values: dict[str, float]) -> ResultMissing | None:
    """``NOT_COMPUTABLE`` naming every month whose erosivity fraction is outside zero to one."""
    names = [name for name in values if name.startswith("erosivity_fraction of ")]
    return outside(values, names, is_fraction, "is outside zero to one")


def _fraction_sum(months: Sequence[MonthOfRotation]) -> float | ResultMissing:
    if not months:
        return ResultMissing(
            reason="NOT_COMPUTABLE", detail="the rotation has no month"
        )
    values = numbers_or_missing(
        {
            f"erosivity_fraction of {_month_name(index, month)}": (
                month.erosivity_fraction
            )
            for index, month in enumerate(months)
        }
    )
    if isinstance(values, ResultMissing):
        return values
    refused = _fractions_outside(values)
    if refused is not None:
        return refused
    try:
        return real(sum(values.values()))
    except ArithmeticError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="the sum of the erosivity fractions is not a finite number",
        )


def _fractions_add_up(
    fraction_sum: float | ResultMissing,
    expected: float | ResultMissing,
    tolerance: NumberOrMissing,
) -> bool | ResultMissing:
    parts: dict[str, NumberOrMissing] = {
        "the sum of the erosivity fractions": fraction_sum,
        "the expected sum (number_of_years)": expected,
        "fraction_sum_tolerance": tolerance,
    }
    values = numbers_or_missing(parts)
    if isinstance(values, ResultMissing):
        return values
    limit = values["fraction_sum_tolerance"]
    if limit < 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE", detail="fraction_sum_tolerance is negative"
        )
    difference = abs(
        values["the sum of the erosivity fractions"]
        - values["the expected sum (number_of_years)"]
    )
    return difference <= limit


def _month_name(index: int, month: MonthOfRotation) -> str:
    return f"month {index} '{month.label}'"


def _value(
    months: Sequence[MonthOfRotation],
    number_of_years: int | InputMissing | ResultMissing,
    expected: float | ResultMissing,
) -> float | ResultMissing:
    if not months:
        return ResultMissing(
            reason="NOT_COMPUTABLE", detail="the rotation has no month"
        )
    numbers: dict[str, NumberOrMissing] = {}
    for index, month in enumerate(months):
        name = _month_name(index, month)
        numbers[f"erosivity_fraction of {name}"] = month.erosivity_fraction
        numbers[f"soil_loss_ratio of {name}"] = month.soil_loss_ratio.value
    if is_missing(number_of_years):
        numbers["number_of_years"] = number_of_years
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = _fractions_outside(values)
    if refused is not None:
        return refused
    if isinstance(expected, ResultMissing):
        return expected
    try:
        total = 0.0
        for index, month in enumerate(months):
            name = _month_name(index, month)
            total = real(
                total
                + real(
                    values[f"erosivity_fraction of {name}"]
                    * values[f"soil_loss_ratio of {name}"]
                )
            )
        return real(total / expected)
    except ArithmeticError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="rotation_c: C is not a finite real number for these arguments",
        )


def rotation_c(
    *,
    months: Sequence[MonthOfRotation],
    number_of_years: int | InputMissing | ResultMissing,
    fraction_sum_tolerance: NumberOrMissing,
) -> RotationC:
    """Factor ``C`` of a rotation, as docs/METHODS.md M1.5 states it.

    Arguments, all by name and none with a default:

    - ``months``: every month of the rotation, in any order. A detail names
      a month by its position (from zero) and its label.
    - ``number_of_years``: the number of years of the rotation, a whole
      number above zero, or a ``Missing``.
    - ``fraction_sum_tolerance``: how far the sum of the fractions may be
      from ``number_of_years`` and still be reported as adding up; zero or
      more, supplied by a person (README.md, OPEN). It only drives
      ``fractions_add_up``: it never changes ``value``.

    ``value`` of the result is ``C``, or a ``Missing``:

    - ``MISSING_INPUT`` when the fraction or the soil-loss ratio of any
      month is missing, or the number of years is; the detail names every
      such month and part with its own reason. Never zero.
    - ``NOT_COMPUTABLE`` when there is no month, when the number of years is
      not above zero, when a fraction or a ratio is not a finite number, when
      a fraction is outside zero to one (the detail names every such month;
      nothing is clipped; PROPOSED), or when ``C`` is not a finite number.
      ``fraction_sum`` is then ``NOT_COMPUTABLE`` as well.

    The fractions are never normalised: when they do not add up to the
    number of years, ``C`` is still the formula of M1.5 on the fractions as
    given, and ``fractions_add_up`` is ``False``.

    Raises ``TypeError`` for an argument of another type.
    """
    _check_arguments(months, number_of_years, fraction_sum_tolerance)
    expected = _expected_sum(number_of_years)
    fraction_sum = _fraction_sum(months)
    return RotationC(
        value=_value(months, number_of_years, expected),
        fraction_sum=fraction_sum,
        expected_fraction_sum=expected,
        fractions_add_up=_fractions_add_up(
            fraction_sum, expected, fraction_sum_tolerance
        ),
        set_to_one=SET_TO_ONE,
        limit=DECLARED_LIMIT,
    )
