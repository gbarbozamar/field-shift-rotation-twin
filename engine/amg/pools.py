"""The two pools of AMG, their step and a run over steps. PROPOSED.

Soil organic carbon is held in two pools: an active pool, which receives the
humified carbon inputs and mineralises at a rate coefficient, and a stable
pool, which does not change. The forms below are PROPOSED; **their source is
to be confirmed by a person**. The session that wrote this module read no
source of AMG and wrote no coefficient of the method here, in a default, a
test or a comment::

    humified input        I  = sum over origins of carbon_input * humification_coefficient
    initial state         S0 = stable_fraction * total_carbon,  A0 = total_carbon - S0
    one step, scheme "explicit"
        mineralised       M  = rate_coefficient * duration * A
        active pool       A' = A + I - M
    one step, scheme "exponential" (I spread evenly over the step)
        x  = rate_coefficient * duration
        active pool       A' = A * exp(-x) + I * (1 - exp(-x)) / x     (A' = A + I when x is zero)
        mineralised       M  = A + I - A'
    stable pool           S' = S
    mass balance          (A' + S') - (A + S) = I - M

Which of the two schemes is the form of the source, for the yearly step and
for a monthly step, is OPEN (README.md of this folder). Both take any step
length: a monthly step is the same function with a shorter ``duration``.

Every constant is an argument with no default. Carbon amounts (the pools, the
inputs, the mineralised carbon) share one unit chosen by the caller; this
module only adds, subtracts and multiplies them and converts nothing. The
rate coefficient and the step length carry unit strings that must be the same
text.

Pure functions: no file, no network, no clock, no argument is changed. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason: never zero, never a default, never "not a number".
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_mapping,
    check_text,
    check_types,
    describe_missing,
    finite,
    is_fraction,
    is_missing,
    is_not_negative,
    no_finite_result,
    numbers_or_missing,
    outside,
    real,
    units_differ,
)

__all__ = [
    "SCHEMES",
    "PoolState",
    "Run",
    "StepInput",
    "StepResult",
    "humified_input",
    "initial_state",
    "run",
    "step",
]

# PROPOSED identifiers of the two candidate schemes of one step (README.md).
SCHEMES: tuple[str, ...] = ("explicit", "exponential")


@dataclass(frozen=True)
class PoolState:
    """The carbon of the two pools at one moment, in the caller's carbon unit."""

    active: float
    stable: float

    @property
    def total(self) -> float:
        return self.active + self.stable


@dataclass(frozen=True)
class StepInput:
    """The inputs of one step of a run, each a number or a ``Missing``.

    - ``humified_input``: humified carbon entering the active pool over the
      step (``humified_input`` gives it), zero or more.
    - ``rate_coefficient``: the rate coefficient of the step
      (``rate_coefficient`` of modifiers.py gives it), zero or more.
    - ``duration``: the length of the step, zero or more.
    """

    humified_input: NumberOrMissing
    rate_coefficient: NumberOrMissing
    duration: NumberOrMissing


@dataclass(frozen=True)
class StepResult:
    """One step that was computed: where it started, what entered and left, where it ended."""

    start: PoolState
    humified_input: float
    mineralised: float
    duration: float
    end: PoolState


def humified_input(
    *,
    carbon_inputs: Mapping[str, NumberOrMissing],
    humification_coefficients: Mapping[str, NumberOrMissing],
) -> float | ResultMissing:
    """The humified carbon input of a step. PROPOSED form.

    ``I = sum over the origins of carbon_inputs of carbon_input * humification_coefficient``.

    - ``carbon_inputs``: carbon entering the soil over the step, by origin
      (for example a residue of one crop; the vocabulary of origins is OPEN
      in contracts/carbon_forcing/README.md). Each zero or more.
    - ``humification_coefficients``: the humification coefficient of each
      origin, a constant of the method and a fraction, zero to one. A
      coefficient of an origin that ``carbon_inputs`` does not hold is not
      used.

    Returns ``I``, or:

    - ``MISSING_INPUT`` when an input or a coefficient is missing, or when an
      origin of ``carbon_inputs`` has no coefficient; the detail names each.
    - ``NOT_COMPUTABLE`` when ``carbon_inputs`` is empty (a step without input
      is written with each origin at zero; PROPOSED, README.md OPEN), when a
      value is not finite, when an input is negative or a coefficient is
      outside zero to one (each named; nothing is clipped), or when the sum
      is not finite.

    Raises ``TypeError`` for an argument of another type.
    """
    check_mapping("carbon_inputs", carbon_inputs)
    check_mapping("humification_coefficients", humification_coefficients)
    inputs = {
        f"carbon input '{origin}'": item for origin, item in carbon_inputs.items()
    }
    check_types(inputs)
    check_types(
        {
            f"humification coefficient '{origin}'": item
            for origin, item in humification_coefficients.items()
        }
    )
    if not carbon_inputs:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="carbon_inputs is empty: no origin is given for the step",
        )
    without = [
        f"humification coefficient '{origin}' is not given"
        for origin in carbon_inputs
        if origin not in humification_coefficients
    ]
    if without:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(without))
    coefficients = {
        f"humification coefficient '{origin}'": humification_coefficients[origin]
        for origin in carbon_inputs
    }
    values = numbers_or_missing({**inputs, **coefficients})
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, inputs, is_not_negative, "is negative")
    if refused is None:
        refused = outside(values, coefficients, is_fraction, "is outside zero to one")
    if refused is not None:
        return refused
    total = math.fsum(
        values[f"carbon input '{origin}'"]
        * values[f"humification coefficient '{origin}'"]
        for origin in carbon_inputs
    )
    if finite(total) is None:
        return no_finite_result("humified_input", "the sum")
    return total


def initial_state(
    *,
    total_carbon: NumberOrMissing,
    stable_fraction: NumberOrMissing,
) -> PoolState | ResultMissing:
    """The two pools at the start of a run. PROPOSED form.

    ``stable = stable_fraction * total_carbon``; ``active = total_carbon - stable``.

    - ``total_carbon``: the soil organic carbon at the start, zero or more,
      in the caller's carbon unit (to which soil depth it refers is OPEN in
      C1.6).
    - ``stable_fraction``: the share of it in the stable pool, a fraction,
      zero to one. A constant of the method or a value of the site: OPEN.

    Returns the ``PoolState``, or ``MISSING_INPUT`` (an argument is missing)
    or ``NOT_COMPUTABLE`` (not finite, a negative carbon, a fraction outside
    zero to one; each named).
    """
    numbers = {"total_carbon": total_carbon, "stable_fraction": stable_fraction}
    check_types(numbers)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, ("total_carbon",), is_not_negative, "is negative")
    if refused is None:
        refused = outside(
            values, ("stable_fraction",), is_fraction, "is outside zero to one"
        )
    if refused is not None:
        return refused
    stable = values["stable_fraction"] * values["total_carbon"]
    return PoolState(active=values["total_carbon"] - stable, stable=stable)


def _check_state(state: object) -> None:
    if is_missing(state):
        return
    if not isinstance(state, PoolState):
        raise TypeError(
            "state: expected a PoolState, or a Missing of the contract models with "
            f"its reason; got {type(state).__name__}"
        )
    check_types({"state.active": state.active, "state.stable": state.stable})


def _check_scheme(scheme: object) -> None:
    check_text("scheme", scheme)
    if scheme not in SCHEMES:
        raise ValueError(
            f"scheme: expected one of {', '.join(SCHEMES)}; got '{scheme}'"
        )


def step(
    *,
    state: PoolState | ResultMissing,
    humified_input: NumberOrMissing,
    rate_coefficient: NumberOrMissing,
    rate_coefficient_per_unit: str,
    duration: NumberOrMissing,
    duration_unit: str,
    scheme: str,
) -> StepResult | ResultMissing:
    """One step of the carbon balance. PROPOSED forms (module docstring).

    - ``state``: the pools at the start of the step, or a ``Missing``.
    - ``humified_input``: humified carbon entering the active pool over the
      step, zero or more.
    - ``rate_coefficient``: zero or more, per ``rate_coefficient_per_unit``.
    - ``duration``: the step length, zero or more, in ``duration_unit``. The
      two unit strings must be the same text: nothing is converted.
    - ``scheme``: ``"explicit"`` or ``"exponential"``, no default (OPEN).

    Returns a ``StepResult``, or the ``Missing`` of the results contract:

    1. ``MISSING_INPUT`` when the state or an argument is missing; the detail
       names each with its reason.
    2. ``NOT_COMPUTABLE`` when a value is not finite; then when a pool, the
       input, the rate coefficient or the duration is negative (each named;
       nothing is clipped); then when the unit strings differ; then, for the
       explicit scheme, when ``rate_coefficient * duration`` is above one: it
       is the fraction of the active pool mineralised in the step, and above
       one more carbon would leave the pool than it holds (PROPOSED); then
       when the form gives no finite real number.

    Raises ``TypeError`` for an argument of another type and ``ValueError``
    for a scheme that is not one of ``SCHEMES``.
    """
    _check_state(state)
    numbers = {
        "humified_input": humified_input,
        "rate_coefficient": rate_coefficient,
        "duration": duration,
    }
    check_types(numbers)
    check_text("rate_coefficient_per_unit", rate_coefficient_per_unit)
    check_text("duration_unit", duration_unit)
    _check_scheme(scheme)

    if is_missing(state):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=describe_missing("the state at the start of the step", state),
        )
    numbers = {"state.active": state.active, "state.stable": state.stable, **numbers}
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, values.keys(), is_not_negative, "is negative")
    if refused is not None:
        return refused
    differ = units_differ(
        {
            "rate_coefficient_per_unit": rate_coefficient_per_unit,
            "duration_unit": duration_unit,
        },
        "multiplied together",
    )
    if differ is not None:
        return differ

    active = values["state.active"]
    stable = values["state.stable"]
    inflow = values["humified_input"]
    try:
        x = real(values["rate_coefficient"] * values["duration"])
        if scheme == "explicit":
            if x > 1:
                return ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        "step, scheme explicit: rate_coefficient * duration is above "
                        "one, so more carbon would be mineralised than the active "
                        "pool holds"
                    ),
                )
            mineralised = real(x * active)
            active_end = real(active + inflow - mineralised)
        else:
            spread = -math.expm1(-x) / x if x > 0 else 1
            active_end = real(active * math.exp(-x) + inflow * spread)
            mineralised = real(active + inflow - active_end)
        real(active_end + stable)
    except (ArithmeticError, ValueError):
        return no_finite_result("step", "the new active pool")
    return StepResult(
        start=PoolState(active=active, stable=stable),
        humified_input=inflow,
        mineralised=mineralised,
        duration=values["duration"],
        end=PoolState(active=active_end, stable=stable),
    )


@dataclass(frozen=True)
class Run:
    """A run over a sequence of steps.

    - ``initial_state``: as passed in, a ``PoolState`` or a ``Missing``.
    - ``steps``: one item per step input, in order: a ``StepResult`` or the
      ``Missing`` of the results contract with its reason. Once a step is
      missing, every later step is missing too (C3.3).
    - ``duration_unit``: the unit of every step length, and so of
      ``elapsed_times``.
    """

    initial_state: PoolState | ResultMissing
    steps: tuple[StepResult | ResultMissing, ...]
    duration_unit: str

    def total_stocks(self) -> tuple[float | ResultMissing, ...]:
        """The total carbon at the start and at the end of each step; ``len(steps) + 1`` items."""
        first = (
            self.initial_state
            if is_missing(self.initial_state)
            else self.initial_state.total
        )
        return (first,) + tuple(
            item if is_missing(item) else item.end.total for item in self.steps
        )

    def elapsed_times(self) -> tuple[float | ResultMissing, ...]:
        """The time from the start of the run at each item of ``total_stocks``.

        The first time is zero. The time at the end of a step is the sum of the
        lengths of the steps so far; at and after a missing step it is that
        step's ``Missing``.
        """
        times: list[float | ResultMissing] = [0.0]
        lengths: list[float] = []
        for item in self.steps:
            if is_missing(item) or is_missing(times[-1]):
                times.append(times[-1] if is_missing(times[-1]) else item)
                continue
            lengths.append(item.duration)
            times.append(math.fsum(lengths))
        return tuple(times)


def run(
    *,
    initial_state: PoolState | ResultMissing,
    steps: Sequence[StepInput],
    rate_coefficient_per_unit: str,
    duration_unit: str,
    scheme: str,
) -> Run:
    """Apply ``step`` to each step input in turn, from ``initial_state``.

    The state at the end of a step is the state at the start of the next; it
    is never reset. When a step is not computed, it is the ``Missing`` that
    ``step`` returns, and every later step is ``MISSING_INPUT`` naming the
    first step that is missing (counted from zero) and its reason. When the
    initial state is missing, every step is ``MISSING_INPUT`` naming it. No
    step is ever written as zero.

    Raises ``TypeError`` for an argument of another type and ``ValueError``
    for a scheme that is not one of ``SCHEMES``.
    """
    _check_state(initial_state)
    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise TypeError(
            f"steps: expected a sequence of StepInput, got {type(steps).__name__}"
        )
    for position, item in enumerate(steps):
        if not isinstance(item, StepInput):
            raise TypeError(
                f"steps[{position}]: expected a StepInput, got {type(item).__name__}"
            )
        check_types(
            {
                f"steps[{position}].humified_input": item.humified_input,
                f"steps[{position}].rate_coefficient": item.rate_coefficient,
                f"steps[{position}].duration": item.duration,
            }
        )
    check_text("rate_coefficient_per_unit", rate_coefficient_per_unit)
    check_text("duration_unit", duration_unit)
    _check_scheme(scheme)

    results: list[StepResult | ResultMissing] = []
    state: PoolState | ResultMissing = initial_state
    first_failure: str | None = (
        describe_missing("the initial state", initial_state)
        if is_missing(initial_state)
        else None
    )
    for position, item in enumerate(steps):
        if first_failure is not None:
            results.append(
                ResultMissing(
                    reason="MISSING_INPUT",
                    detail=f"step {position}: the state at its start is missing; {first_failure}",
                )
            )
            continue
        result = step(
            state=state,
            humified_input=item.humified_input,
            rate_coefficient=item.rate_coefficient,
            rate_coefficient_per_unit=rate_coefficient_per_unit,
            duration=item.duration,
            duration_unit=duration_unit,
            scheme=scheme,
        )
        if is_missing(result):
            first_failure = f"step {position} is missing, reason {result.reason}"
            if result.detail is not None:
                first_failure += f": {result.detail}"
            results.append(
                ResultMissing(
                    reason=result.reason, detail=f"step {position}: {result.detail}"
                )
                if result.detail is not None
                else result
            )
            continue
        results.append(result)
        state = result.end
    return Run(
        initial_state=initial_state, steps=tuple(results), duration_unit=duration_unit
    )
