"""Uniform-forcing substep runner and annual-vs-substep comparison for AMG. PROPOSED.

Unit ``l1/amg-monthly-uniform-check`` (blueprint section 8, Block 3 ``L1 Engines``,
and decision D80 of ``docs/SCIENCE_DECISIONS.md``): checks a sub-annual (for
example, monthly) run against the 1-step-per-year reference under uniform
forcing. Built directly on ``engine.amg.pools`` without duplicating step
physics or writing any constant of AMG anywhere.

Under uniform forcing over ``years`` agricultural years (``annual_humified_input``,
``rate_coefficient``, ``annual_duration``), each year of the annual reference is
one ``StepInput(annual_humified_input, rate_coefficient, annual_duration)`` and
each of the ``substeps_per_year * years`` uniform substeps is::

    StepInput(
        humified_input=annual_humified_input / substeps_per_year,
        rate_coefficient=rate_coefficient,
        duration=annual_duration / substeps_per_year,
    )

Every argument is passed by name with no default. Nothing is clipped, filled, or
defaulted: a ``Missing`` argument propagates via ``pools.run`` (G4), and a
structural or type defect raises ``TypeError`` or ``ValueError`` (G5). Pure
functions (G1): no file, no network, no clock, no argument is changed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_text,
    check_types,
    describe_missing,
    finite,
    is_missing,
    no_finite_result,
)
from .pools import (
    PoolState,
    Run,
    StepInput,
    StepResult,
    _check_scheme,
    _check_state,
    run,
)

__all__ = [
    "UniformComparison",
    "compare_annual_and_substeps_uniform",
    "run_uniform_substeps",
]


@dataclass(frozen=True)
class UniformComparison:
    """Comparison of a 1-step-per-year ``Run`` and a uniform-substep ``Run``.

    - ``annual_run``: the annual reference run (``years`` steps).
    - ``monthly_run``: the substep run (``substeps_per_year * years`` steps).
    - ``active_difference``: ``monthly_end.active - annual_end.active`` at the
      end of the horizon, or ``MISSING_INPUT`` naming any missing final step.
    - ``total_difference``: ``monthly_end.total - annual_end.total`` at the end
      of the horizon, or ``MISSING_INPUT`` naming any missing final step.
    - ``scheme``: step scheme used for both runs (one of ``SCHEMES``).
    - ``substeps_per_year``: number of equal substeps per year.
    """

    annual_run: Run
    monthly_run: Run
    active_difference: float | ResultMissing
    total_difference: float | ResultMissing
    scheme: str
    substeps_per_year: int


def _check_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}: expected an integer, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{name}: expected an integer >= 1, got {value}")
    return value


def _check_uniform_arguments(
    *,
    initial_state: object,
    annual_humified_input: object,
    rate_coefficient: object,
    rate_coefficient_per_unit: object,
    annual_duration: object,
    duration_unit: object,
    years: object,
    substeps_per_year: object,
    scheme: object,
) -> tuple[int, int]:
    _check_state(initial_state)
    check_types(
        {
            "annual_humified_input": annual_humified_input,
            "rate_coefficient": rate_coefficient,
            "annual_duration": annual_duration,
        }
    )
    check_text("rate_coefficient_per_unit", rate_coefficient_per_unit)
    check_text("duration_unit", duration_unit)
    checked_years = _check_positive_int("years", years)
    checked_substeps = _check_positive_int("substeps_per_year", substeps_per_year)
    _check_scheme(scheme)
    return checked_years, checked_substeps


def _scale_for_substep(
    value: NumberOrMissing, substeps_per_year: int, name: str
) -> NumberOrMissing:
    """Scale a finite annual input or duration by ``substeps_per_year``.

    A ``Missing`` or non-finite value is returned unchanged so ``pools.run``
    preserves the exact ``MISSING_INPUT`` or ``NOT_COMPUTABLE`` reason and
    argument name.
    """
    if is_missing(value):
        return value
    number = finite(value)
    if number is None:
        return value
    try:
        scaled = number / substeps_per_year
    except OverflowError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"{name}: substeps_per_year is too large to scale a finite float",
        )
    if finite(scaled) is None:
        return no_finite_result("run_uniform_substeps", name)
    return scaled


def _difference(
    annual_last: StepResult | ResultMissing,
    monthly_last: StepResult | ResultMissing,
    read: Callable[[PoolState], float],
    what: str,
) -> float | ResultMissing:
    missing = [
        describe_missing(label, item)
        for label, item in (
            ("annual_run final step", annual_last),
            ("monthly_run final step", monthly_last),
        )
        if is_missing(item)
    ]
    if missing:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(missing))
    diff = read(monthly_last.end) - read(annual_last.end)
    if finite(diff) is None:
        return no_finite_result("compare_annual_and_substeps_uniform", what)
    return diff


def run_uniform_substeps(
    *,
    initial_state: PoolState | ResultMissing,
    annual_humified_input: NumberOrMissing,
    rate_coefficient: NumberOrMissing,
    rate_coefficient_per_unit: str,
    annual_duration: NumberOrMissing,
    duration_unit: str,
    years: int,
    substeps_per_year: int,
    scheme: str,
) -> Run:
    """Run AMG over ``years`` with ``substeps_per_year`` equal substeps per year.

    Builds ``substeps_per_year * years`` uniform ``StepInput`` items with
    ``annual_humified_input / substeps_per_year``, the same ``rate_coefficient``,
    and ``annual_duration / substeps_per_year``, then delegates to ``pools.run``.

    Raises ``TypeError`` for arguments of another type and ``ValueError`` for
    an unknown ``scheme`` (not in ``SCHEMES``) or ``years`` / ``substeps_per_year``
    below one.
    """
    checked_years, checked_substeps = _check_uniform_arguments(
        initial_state=initial_state,
        annual_humified_input=annual_humified_input,
        rate_coefficient=rate_coefficient,
        rate_coefficient_per_unit=rate_coefficient_per_unit,
        annual_duration=annual_duration,
        duration_unit=duration_unit,
        years=years,
        substeps_per_year=substeps_per_year,
        scheme=scheme,
    )
    substep_input = _scale_for_substep(
        annual_humified_input, checked_substeps, "annual_humified_input"
    )
    substep_duration = _scale_for_substep(
        annual_duration, checked_substeps, "annual_duration"
    )
    steps = [
        StepInput(
            humified_input=substep_input,
            rate_coefficient=rate_coefficient,
            duration=substep_duration,
        )
    ] * (checked_years * checked_substeps)
    return run(
        initial_state=initial_state,
        steps=steps,
        rate_coefficient_per_unit=rate_coefficient_per_unit,
        duration_unit=duration_unit,
        scheme=scheme,
    )


def compare_annual_and_substeps_uniform(
    *,
    initial_state: PoolState | ResultMissing,
    annual_humified_input: NumberOrMissing,
    rate_coefficient: NumberOrMissing,
    rate_coefficient_per_unit: str,
    annual_duration: NumberOrMissing,
    duration_unit: str,
    years: int,
    substeps_per_year: int,
    scheme: str,
) -> UniformComparison:
    """Compare a 1-step-per-year ``Run`` and a uniform-substep ``Run`` over ``years``.

    Builds the ``years``-step annual ``StepInput`` list and runs both the annual
    reference and ``run_uniform_substeps`` via ``pools.run`` using ``scheme``
    (one of ``SCHEMES``). Returns a ``UniformComparison`` holding both runs and
    the final ``active_difference`` and ``total_difference`` (``monthly - annual``).

    Raises ``TypeError`` for arguments of another type and ``ValueError`` for
    an unknown ``scheme`` or ``years`` / ``substeps_per_year`` below one.
    """
    checked_years, checked_substeps = _check_uniform_arguments(
        initial_state=initial_state,
        annual_humified_input=annual_humified_input,
        rate_coefficient=rate_coefficient,
        rate_coefficient_per_unit=rate_coefficient_per_unit,
        annual_duration=annual_duration,
        duration_unit=duration_unit,
        years=years,
        substeps_per_year=substeps_per_year,
        scheme=scheme,
    )
    annual_steps = [
        StepInput(
            humified_input=annual_humified_input,
            rate_coefficient=rate_coefficient,
            duration=annual_duration,
        )
    ] * checked_years
    annual_run = run(
        initial_state=initial_state,
        steps=annual_steps,
        rate_coefficient_per_unit=rate_coefficient_per_unit,
        duration_unit=duration_unit,
        scheme=scheme,
    )
    monthly_run = run_uniform_substeps(
        initial_state=initial_state,
        annual_humified_input=annual_humified_input,
        rate_coefficient=rate_coefficient,
        rate_coefficient_per_unit=rate_coefficient_per_unit,
        annual_duration=annual_duration,
        duration_unit=duration_unit,
        years=checked_years,
        substeps_per_year=checked_substeps,
        scheme=scheme,
    )
    annual_last = annual_run.steps[-1]
    monthly_last = monthly_run.steps[-1]
    return UniformComparison(
        annual_run=annual_run,
        monthly_run=monthly_run,
        active_difference=_difference(
            annual_last,
            monthly_last,
            lambda state: state.active,
            "active_difference",
        ),
        total_difference=_difference(
            annual_last,
            monthly_last,
            lambda state: state.total,
            "total_difference",
        ),
        scheme=scheme,
        substeps_per_year=checked_substeps,
    )
