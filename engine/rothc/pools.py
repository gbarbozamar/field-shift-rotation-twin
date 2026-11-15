"""The five pools of RothC, their monthly step and a run over months. PROPOSED.

The forms are the person-transcribed model description of issue #176
("RothC -- Model Description", February 2024, Rothamsted Research; transcribed
by Martin on 14 November 2026, checked by the lead developer on 15 November
2026 under D63 and D134; in force per D34). **No session read a RothC source
and no value of the method is written in this module**: every constant is an
argument with no default.

Soil carbon is held in four active pools -- decomposable plant material
(DPM), resistant plant material (RPM), microbial biomass (BIO) and humified
organic matter (HUM) -- and one inert pool (IOM), which does not take part in
the turnover. One month of the balance, as the description prints it in its
worked example::

    additions          the carbon inputs of the month enter the pools they
                       feed (DPM, RPM, HUM for farmyard manure; DPM and RPM
                       for plant material), at the start of the month
    decomposition      each active pool becomes
                           pool' = (pool + addition) * exp(-k * abc / 12)
                       with k the rate constant of the pool per year and abc
                       the combined rate modifying factor of the month; the
                       material decomposed is the difference
    partitioning       of everything decomposed, x / (x + 1) leaves as CO2
                       and 1 / (x + 1) is formed as BIO + HUM, x the clay
                       partitioning ratio; the formed BIO + HUM enters BIO
                       and HUM in the shares bio_share and its complement
    inert pool         unchanged
    mass balance       stocks out + CO2 = stocks in + inputs

The rate constants are per year and the step is one month, so each step
divides by the twelve months of a year (``MONTHS_PER_YEAR``). Which month the
inputs of a month enter -- before the decomposition of that same month -- is
the reading of this folder of the description's flow of carbon (README.md,
OPEN): the worked example prints a month without inputs, so it does not
decide it.

Every constant is an argument with no default. Carbon amounts share one unit
chosen by the caller; this module only adds, subtracts and multiplies them
and converts nothing. Unit strings play no part here: the rate constants are
per year by the form above, and the entry point checks the unit of their
records.

Pure functions: no file, no network, no clock, no argument is changed. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason: never zero, never a default, never "not a number".
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_mapping,
    check_types,
    describe_missing,
    finite,
    is_fraction,
    is_missing,
    is_not_negative,
    is_positive,
    no_finite_result,
    numbers_or_missing,
    outside,
    real,
)

__all__ = [
    "MONTHS_PER_YEAR",
    "InputSplit",
    "MonthInput",
    "PoolState",
    "Run",
    "StepResult",
    "initial_state",
    "input_additions",
    "inert_organic_matter",
    "plant_fractions",
    "run",
    "step",
]

# The months of a year (C5.1), counted, never written as a number.
MONTHS_PER_YEAR = len(calendar.month_name[1:])

# The pools that take part in the turnover, in the order of the description.
ACTIVE_POOLS: tuple[str, ...] = ("dpm", "rpm", "bio", "hum")


@dataclass(frozen=True)
class PoolState:
    """The carbon of the five pools at one moment, in the caller's carbon unit.

    ``dpm``, ``rpm``, ``bio`` and ``hum`` are the active pools, ``iom`` the
    inert organic matter, which the step does not change.
    """

    dpm: float
    rpm: float
    bio: float
    hum: float
    iom: float

    @property
    def total(self) -> float:
        return math.fsum((self.dpm, self.rpm, self.bio, self.hum, self.iom))


@dataclass(frozen=True)
class InputSplit:
    """A split of carbon between the pools an input feeds.

    As the composition of one unit of incoming material (the shares sum to
    one) or as the additions of one month in the caller's carbon unit.
    """

    dpm: float
    rpm: float
    bio: float
    hum: float

    @property
    def total(self) -> float:
        return math.fsum((self.dpm, self.rpm, self.bio, self.hum))


def _check_split(name: str, split: object) -> None:
    if is_missing(split):
        return
    if not isinstance(split, InputSplit):
        raise TypeError(
            f"{name}: expected an InputSplit, or a Missing of the contract models "
            f"with its reason; got {type(split).__name__}"
        )
    check_types(
        {
            f"{name}.dpm": split.dpm,
            f"{name}.rpm": split.rpm,
            f"{name}.bio": split.bio,
            f"{name}.hum": split.hum,
        }
    )


def _check_state(state: object) -> None:
    if is_missing(state):
        return
    if not isinstance(state, PoolState):
        raise TypeError(
            "state: expected a PoolState, or a Missing of the contract models with "
            f"its reason; got {type(state).__name__}"
        )
    check_types(
        {
            "state.dpm": state.dpm,
            "state.rpm": state.rpm,
            "state.bio": state.bio,
            "state.hum": state.hum,
            "state.iom": state.iom,
        }
    )


def initial_state(
    *,
    dpm: NumberOrMissing,
    rpm: NumberOrMissing,
    bio: NumberOrMissing,
    hum: NumberOrMissing,
    iom: NumberOrMissing,
) -> PoolState | ResultMissing:
    """The five pools at the start of a run.

    Each argument is a stock, zero or more, in the caller's carbon unit; the
    inert pool is the value the run carries through unchanged. Where the
    inert pool has no measured value the caller computes it from the total
    organic carbon with the description's form (the entry point does, from
    two constants of the catalogue).

    Returns the ``PoolState``, or ``MISSING_INPUT`` (a pool is missing, each
    named) or ``NOT_COMPUTABLE`` (a value is not finite or negative).
    """
    numbers = {"dpm": dpm, "rpm": rpm, "bio": bio, "hum": hum, "iom": iom}
    check_types(numbers)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, values.keys(), is_not_negative, "is negative")
    if refused is not None:
        return refused
    return PoolState(**values)


def inert_organic_matter(
    *,
    total_organic_carbon: NumberOrMissing,
    coefficient: NumberOrMissing,
    exponent: NumberOrMissing,
) -> float | ResultMissing:
    """The inert pool from the total organic carbon. PROPOSED form (p. 16).

    ``IOM = coefficient * TOC^exponent``, both stocks in the caller's carbon
    unit, so the constant and the exponent carry no unit. The description
    gives this form for a soil without radiocarbon data and its own measured
    inert pool; the caller reads a measured inert pool when it has one.

    Returns the inert stock, or ``MISSING_INPUT`` / ``NOT_COMPUTABLE``
    (not finite; a negative total organic carbon; a form that gives no
    finite positive stock).

    Raises ``TypeError`` for an argument of another type.
    """
    numbers = {
        "total_organic_carbon": total_organic_carbon,
        "coefficient": coefficient,
        "exponent": exponent,
    }
    check_types(numbers)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values, ("total_organic_carbon",), is_not_negative, "is negative"
    )
    if refused is not None:
        return refused
    try:
        stock = real(values["coefficient"] * values["total_organic_carbon"] ** values["exponent"])
    except (ArithmeticError, ValueError, OverflowError):
        return no_finite_result("inert_organic_matter", "the inert stock")
    if not is_not_negative(stock):
        return no_finite_result("inert_organic_matter", "the inert stock")
    return stock


def plant_fractions(*, dpm_rpm_ratio: NumberOrMissing) -> InputSplit | ResultMissing:
    """The composition of incoming plant material from its DPM:RPM ratio.

    The description gives the decomposability of plant material as the ratio
    of DPM to RPM; the shares follow from it: ``dpm = r / (1 + r)`` and
    ``rpm = 1 / (1 + r)``, and no part of plant material enters HUM. (For
    the printed classes the shares are the printed percentages: a ratio of
    the crops class gives the printed shares of that class.)

    Returns the ``InputSplit``, or ``MISSING_INPUT`` / ``NOT_COMPUTABLE``
    (not finite; a negative ratio; a ratio of exactly minus one, where the
    form divides by zero).

    Raises ``TypeError`` for an argument of another type.
    """
    check_types({"dpm_rpm_ratio": dpm_rpm_ratio})
    values = numbers_or_missing({"dpm_rpm_ratio": dpm_rpm_ratio})
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, ("dpm_rpm_ratio",), is_not_negative, "is negative")
    if refused is not None:
        return refused
    try:
        total = real(values["dpm_rpm_ratio"] + 1)
        dpm = real(values["dpm_rpm_ratio"] / total)
        rpm = real(1 / total)
    except (ArithmeticError, ValueError, ZeroDivisionError):
        return no_finite_result("plant_fractions", "the shares of the material")
    return InputSplit(dpm=dpm, rpm=rpm, bio=0.0, hum=0.0)


def input_additions(
    *,
    carbon_inputs: Mapping[str, NumberOrMissing],
    compositions: Mapping[str, InputSplit | ResultMissing],
) -> InputSplit | ResultMissing:
    """The additions of one month, split between the pools each input feeds.

    - ``carbon_inputs``: the carbon entering the soil over the month, by
      input (for example the residues of one crop; the vocabulary of origins
      is OPEN in contracts/carbon_forcing/README.md). Each zero or more,
      also zero: a month without input of one origin is written with that
      origin at zero, as the worked example's first month is.
    - ``compositions``: the composition of each input, as ``InputSplit``
      shares that sum to one (``plant_fractions`` gives the composition of
      plant material; farmyard manure is given by three shares of its own).

    Returns the ``InputSplit`` of the additions, or:

    - ``MISSING_INPUT`` when an input or a composition is missing, or an
      input has no composition; the detail names each.
    - ``NOT_COMPUTABLE`` when ``carbon_inputs`` is empty (no input is given
      for the month; a month without input is written as an input at zero),
      when a value is not finite, when an input is negative, when the shares
      of a composition are negative or do not sum to one, or when a sum is
      not finite.

    Raises ``TypeError`` for an argument of another type.
    """
    check_mapping("carbon_inputs", carbon_inputs)
    check_mapping("compositions", compositions)
    for key, composition in compositions.items():
        _check_split(f"compositions[{key!r}]", composition)
    check_types({f"carbon input '{key}'": item for key, item in carbon_inputs.items()})
    if not carbon_inputs:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "carbon_inputs is empty: no carbon input is given for the month, and "
                "a month without input is written as an input of zero, never by "
                "omission (the carbon inputs stay missing until EP4 exists: D122)"
            ),
        )
    without = [
        f"the composition of carbon input '{key}' is not given"
        for key in carbon_inputs
        if key not in compositions
    ]
    if without:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(without))
    numbers: dict[str, NumberOrMissing] = {
        f"carbon input '{key}'": item for key, item in carbon_inputs.items()
    }
    for key, composition in compositions.items():
        if key not in carbon_inputs:
            continue
        if is_missing(composition):
            numbers[f"composition of '{key}'"] = composition
            continue
        numbers[f"composition of '{key}'.dpm"] = composition.dpm
        numbers[f"composition of '{key}'.rpm"] = composition.rpm
        numbers[f"composition of '{key}'.bio"] = composition.bio
        numbers[f"composition of '{key}'.hum"] = composition.hum
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values,
        [f"carbon input '{key}'" for key in carbon_inputs],
        is_not_negative,
        "is negative",
    )
    if refused is not None:
        return refused
    for key, composition in compositions.items():
        if key not in carbon_inputs or is_missing(composition):
            continue
        names = [
            f"composition of '{key}'.{pool}"
            for pool in ("dpm", "rpm", "bio", "hum")
        ]
        refused = outside(values, names, is_not_negative, "is negative")
        if refused is not None:
            return refused
        total = math.fsum(values[name] for name in names)
        # The shares must sum to one; the precision allowed is that of the
        # arithmetic that adds them (a few rounding steps of one), no more.
        if not math.isclose(
            total, 1.0, rel_tol=len(names) * math.ulp(1.0), abs_tol=0.0
        ):
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"the shares of the composition of carbon input '{key}' sum to "
                    f"{total}, not to one"
                ),
            )
    additions = {
        pool: math.fsum(
            values[f"carbon input '{key}'"] * getattr(compositions[key], pool)
            for key in carbon_inputs
            if not is_missing(compositions[key])
        )
        for pool in ("dpm", "rpm", "bio", "hum")
    }
    if any(finite(additions[pool]) is None for pool in additions):
        return no_finite_result("input_additions", "the additions")
    return InputSplit(**additions)


@dataclass(frozen=True)
class MonthInput:
    """The inputs of one month of a run, each a number or a ``Missing``.

    - ``additions``: the carbon inputs of the month split between the pools
      they feed (``input_additions`` gives them).
    - ``rate_modifying_factor``: the combined factor ``abc`` of the month
      (the product of the modifiers of ``modifiers.py``), zero or more.
    """

    additions: InputSplit | ResultMissing
    rate_modifying_factor: NumberOrMissing


@dataclass(frozen=True)
class StepResult:
    """One month that was computed: where it started, what entered and left, where it ended."""

    start: PoolState
    additions: InputSplit
    co2: float  # the carbon lost as CO2 over the month
    duration: float  # the length of the month in years: one over MONTHS_PER_YEAR
    end: PoolState


def _check_rate_constants(rate_constants: object) -> None:
    if not isinstance(rate_constants, Mapping):
        raise TypeError(
            "rate_constants: expected a mapping from pool name to number or Missing, "
            f"got {type(rate_constants).__name__}"
        )
    if set(rate_constants) != set(ACTIVE_POOLS):
        raise TypeError(
            "rate_constants: holds every active pool once, keyed "
            f"{', '.join(ACTIVE_POOLS)}; got {sorted(rate_constants)}"
        )
    check_types({f"rate_constants[{pool}]": rate_constants[pool] for pool in ACTIVE_POOLS})


def step(
    *,
    state: PoolState | ResultMissing,
    additions: InputSplit | ResultMissing,
    rate_modifying_factor: NumberOrMissing,
    rate_constants: Mapping[str, NumberOrMissing],
    partition_ratio: NumberOrMissing,
    bio_share: NumberOrMissing,
) -> StepResult | ResultMissing:
    """One month of the carbon balance. PROPOSED form (module docstring).

    - ``state``: the pools at the start of the month, or a ``Missing``.
    - ``additions``: the carbon inputs of the month (``input_additions``).
    - ``rate_modifying_factor``: ``abc`` of the month, zero or more.
    - ``rate_constants``: the decomposition rate constant of each active
      pool, per year, zero or more.
    - ``partition_ratio``: the clay partitioning ratio ``x``, positive.
    - ``bio_share``: the share of the formed BIO + HUM that enters BIO, a
      fraction; its complement enters HUM.

    Returns a ``StepResult``, or the ``Missing`` of the results contract:

    1. ``MISSING_INPUT`` when the state or an argument is missing; the
       detail names each with its reason.
    2. ``NOT_COMPUTABLE`` when a value is not finite; then when a pool, an
       addition, the factor, a rate constant or the partitioning ratio is
       negative, when the bio share is outside zero to one, or when the
       partitioning ratio is not positive (each named; nothing is clipped);
       then when the form gives no finite real number.

    Raises ``TypeError`` for an argument of another type.
    """
    _check_state(state)
    _check_split("additions", additions)
    _check_rate_constants(rate_constants)
    check_types(
        {
            "rate_modifying_factor": rate_modifying_factor,
            "partition_ratio": partition_ratio,
            "bio_share": bio_share,
        }
    )
    if is_missing(state):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=describe_missing("the state at the start of the month", state),
        )
    if is_missing(additions):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=describe_missing("the additions of the month", additions),
        )
    numbers = {
        "state.dpm": state.dpm,
        "state.rpm": state.rpm,
        "state.bio": state.bio,
        "state.hum": state.hum,
        "state.iom": state.iom,
        "additions.dpm": additions.dpm,
        "additions.rpm": additions.rpm,
        "additions.bio": additions.bio,
        "additions.hum": additions.hum,
        "rate_modifying_factor": rate_modifying_factor,
        **{f"rate_constants[{pool}]": rate_constants[pool] for pool in ACTIVE_POOLS},
        "partition_ratio": partition_ratio,
        "bio_share": bio_share,
    }
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values,
        [
            *(f"state.{pool}" for pool in (*ACTIVE_POOLS, "iom")),
            *(f"additions.{pool}" for pool in ACTIVE_POOLS),
            "rate_modifying_factor",
            *(f"rate_constants[{pool}]" for pool in ACTIVE_POOLS),
        ],
        is_not_negative,
        "is negative",
    )
    if refused is None:
        refused = outside(values, ("bio_share",), is_fraction, "is outside zero to one")
    if refused is None:
        refused = outside(
            values, ("partition_ratio",), is_positive, "is not positive"
        )
    if refused is not None:
        return refused
    factor = values["rate_modifying_factor"]
    with_input = {pool: values[f"state.{pool}"] + values[f"additions.{pool}"]
                  for pool in ACTIVE_POOLS}
    try:
        decayed = {
            pool: real(
                with_input[pool]
                * math.exp(
                    -values[f"rate_constants[{pool}]"] * factor / MONTHS_PER_YEAR
                )
            )
            for pool in ACTIVE_POOLS
        }
        decomposed = {
            pool: real(with_input[pool] - decayed[pool]) for pool in ACTIVE_POOLS
        }
        total_decomposed = real(math.fsum(decomposed.values()))
        formed = real(total_decomposed / real(values["partition_ratio"] + 1))
        co2 = real(total_decomposed - formed)
        bio_gain = real(values["bio_share"] * formed)
        hum_gain = real(formed - bio_gain)
        end = PoolState(
            dpm=decayed["dpm"],
            rpm=decayed["rpm"],
            bio=real(decayed["bio"] + bio_gain),
            hum=real(decayed["hum"] + hum_gain),
            iom=values["state.iom"],
        )
        real(end.total + co2)  # the mass balance must be a finite number
    except (ArithmeticError, ValueError, ZeroDivisionError, OverflowError):
        return no_finite_result("step", "the pools at the end of the month")
    return StepResult(
        start=PoolState(
            dpm=values["state.dpm"],
            rpm=values["state.rpm"],
            bio=values["state.bio"],
            hum=values["state.hum"],
            iom=values["state.iom"],
        ),
        additions=InputSplit(
            dpm=values["additions.dpm"],
            rpm=values["additions.rpm"],
            bio=values["additions.bio"],
            hum=values["additions.hum"],
        ),
        co2=co2,
        duration=1 / MONTHS_PER_YEAR,
        end=end,
    )


@dataclass(frozen=True)
class Run:
    """A run over the months of the horizon.

    - ``initial_state``: as passed in, a ``PoolState`` or a ``Missing``.
    - ``steps``: one item per month input, in order: a ``StepResult`` or the
      ``Missing`` of the results contract with its reason. Once a month is
      missing, every later month is missing too (C3.3).
    - ``duration_unit``: the time unit of every month and so of
      ``elapsed_times``; the step divides the per-year rate constants by the
      months of a year, so the unit is a year.
    """

    initial_state: PoolState | ResultMissing
    steps: tuple[StepResult | ResultMissing, ...]
    duration_unit: str

    def total_stocks(self) -> tuple[float | ResultMissing, ...]:
        """The total carbon at the start and at the end of each month; ``len(steps) + 1`` items."""
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

        The first time is zero. The time at the end of a month is the sum of
        the lengths of the months so far; at and after a missing month it is
        that month's ``Missing``.
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
    months: Sequence[MonthInput],
    rate_constants: Mapping[str, NumberOrMissing],
    partition_ratio: NumberOrMissing,
    bio_share: NumberOrMissing,
) -> Run:
    """Apply ``step`` to each month input in turn, from ``initial_state``.

    The constants of the turnover (rate constants, partitioning ratio, bio
    share) are those of the whole run. The state at the end of a month is
    the state at the start of the next; it is never reset. When a month is
    not computed, it is the ``Missing`` that ``step`` returns, and every
    later month is ``MISSING_INPUT`` naming the first month that is missing
    (counted from zero) and its reason. When the initial state is missing,
    every month is ``MISSING_INPUT`` naming it. No month is ever written as
    zero.

    Raises ``TypeError`` for an argument of another type.
    """
    _check_state(initial_state)
    if isinstance(months, (str, bytes)) or not isinstance(months, Sequence):
        raise TypeError(
            f"months: expected a sequence of MonthInput, got {type(months).__name__}"
        )
    for position, item in enumerate(months):
        if not isinstance(item, MonthInput):
            raise TypeError(
                f"months[{position}]: expected a MonthInput, got {type(item).__name__}"
            )
        _check_split(f"months[{position}].additions", item.additions)
        check_types(
            {f"months[{position}].rate_modifying_factor": item.rate_modifying_factor}
        )
    _check_rate_constants(rate_constants)
    check_types({"partition_ratio": partition_ratio, "bio_share": bio_share})

    results: list[StepResult | ResultMissing] = []
    state: PoolState | ResultMissing = initial_state
    first_failure: str | None = (
        describe_missing("the initial state", initial_state)
        if is_missing(initial_state)
        else None
    )
    for position, item in enumerate(months):
        if first_failure is not None:
            results.append(
                ResultMissing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"month {position}: the state at its start is missing; "
                        f"{first_failure}"
                    ),
                )
            )
            continue
        result = step(
            state=state,
            additions=item.additions,
            rate_modifying_factor=item.rate_modifying_factor,
            rate_constants=rate_constants,
            partition_ratio=partition_ratio,
            bio_share=bio_share,
        )
        if is_missing(result):
            first_failure = f"month {position} is missing, reason {result.reason}"
            if result.detail is not None:
                first_failure += f": {result.detail}"
            results.append(
                ResultMissing(
                    reason=result.reason, detail=f"month {position}: {result.detail}"
                )
                if result.detail is not None
                else result
            )
            continue
        results.append(result)
        state = result.end
    return Run(
        initial_state=initial_state,
        steps=tuple(results),
        duration_unit="yr",
    )
