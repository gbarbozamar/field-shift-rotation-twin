"""The rate modifying factors of RothC: temperature (a), moisture (b), cover (c). PROPOSED.

Every form below is the person-transcribed model description of issue #176
("RothC -- Model Description", February 2024, Rothamsted Research; transcribed
by Martin on 14 November 2026, checked by the lead developer on 15 November
2026 under D63 and D134; the values are in force per D34). **No session read a
RothC source and no value of the method is written in this module**: every
constant is an argument with no default.

::

    temperature modifier (p. 9)
        a = maximum / (1 + exp(exponent_scale / (temperature + offset)))
        T = average monthly air temperature
    clay partitioning (section 1.7, p. 13)
        x = scale * (intercept + clay_coefficient * exp(-clay_decay * clay))
        x / (x + 1) of what decomposes goes to CO2, 1 / (x + 1) to BIO + HUM
    maximum TSMD (pp. 10-12), for the 0-23 cm layer, scaled to another depth
        max = -(tsmd_intercept + clay_coefficient * clay
                - clay_squared_coefficient * clay^2) * depth / reference_depth
        TSMD: total soil moisture deficit, zero at field capacity, negative
    water balance, one month (pp. 10-12)
        deficit' = clamp(deficit - (pan_factor * pan_evaporation - rainfall),
                         max, 0)   (max TSMD <= deficit' <= field capacity)
        the deficit accumulates in the months with pan_factor * pan > rainfall
        and the soil wets up in the others; it starts at field capacity
        (zero) on the first month
    moisture modifier (p. 12)
        b = 1.0                                     if deficit >  threshold * max
        b = minimum + (1 - minimum) * (max - deficit) / (max - threshold * max)
                                                  otherwise
    soil cover factor (p. 13)
        c = vegetated_factor when the soil is vegetated, bare_factor when bare
    rate modifying factor
        abc = a * b * c

Which value a constant may take is OPEN in README.md of this folder: only
what a form cannot carry is refused (a negative rate modifier, a fraction
outside zero to one, a deficit outside its maximum and field capacity).
Nothing is clipped, filled or replaced by zero.

Unit strings are compared as text and nothing is converted (C1.1): the
temperature with the two temperature constants; the rainfall with the pan
evaporation, the deficit and the TSMD intercept; the clay content with the
clay unit inside the unit of each clay constant; the soil depth with the
reference depth.

Pure functions: no file, no network, no clock, no argument is changed. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason.
"""

from __future__ import annotations

import math

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_text,
    check_types,
    finite,
    is_fraction,
    is_not_negative,
    is_positive,
    no_finite_result,
    numbers_or_missing,
    outside,
    real,
    unit_is_not,
    units_differ,
)

__all__ = [
    "advance_deficit",
    "bare_soil_deficit",
    "clay_partition",
    "cover_modifier",
    "maximum_tsmd",
    "moisture_modifier",
    "rate_modifying_factor",
    "temperature_modifier",
]


def temperature_modifier(
    *,
    temperature: NumberOrMissing,
    temperature_unit: str,
    maximum: NumberOrMissing,
    exponent_scale: NumberOrMissing,
    exponent_scale_unit: str,
    offset: NumberOrMissing,
    offset_unit: str,
) -> float | ResultMissing:
    """The temperature rate modifier ``a``. PROPOSED form (module docstring).

    - ``temperature``: the average monthly air temperature (the description
      says air temperature, not soil).
    - ``maximum``: the numerator of the form (the value it approaches as the
      temperature grows without bound).
    - ``exponent_scale`` and ``offset``: the other two constants of the form;
      their units are the unit of ``temperature``.

    Returns ``a``, or ``MISSING_INPUT`` (an argument is missing; the detail
    names each) or ``NOT_COMPUTABLE`` (a value is not finite; the unit
    strings differ; the temperature sits exactly at ``-offset``, where the
    form divides by zero; the exponential overflows).

    Raises ``TypeError`` for an argument of another type.
    """
    check_types(
        {
            "temperature": temperature,
            "maximum": maximum,
            "exponent_scale": exponent_scale,
            "offset": offset,
        }
    )
    check_text("temperature_unit", temperature_unit)
    check_text("exponent_scale_unit", exponent_scale_unit)
    check_text("offset_unit", offset_unit)
    values = numbers_or_missing(
        {
            "temperature": temperature,
            "maximum": maximum,
            "exponent_scale": exponent_scale,
            "offset": offset,
        }
    )
    if isinstance(values, ResultMissing):
        return values
    differ = units_differ(
        {
            "temperature_unit": temperature_unit,
            "exponent_scale_unit": exponent_scale_unit,
            "offset_unit": offset_unit,
        },
        "added and divided together",
    )
    if differ is not None:
        return differ
    try:
        denominator = real(values["temperature"] + values["offset"])
        inner = real(values["exponent_scale"] / denominator)
        modifier = real(values["maximum"] / (1 + math.exp(inner)))
    except (ArithmeticError, ValueError, ZeroDivisionError, OverflowError):
        return no_finite_result(
            "temperature_modifier", "the temperature rate modifier"
        )
    return modifier


def clay_partition(
    *,
    clay_content: NumberOrMissing,
    clay_content_unit: str,
    scale: NumberOrMissing,
    intercept: NumberOrMissing,
    clay_coefficient: NumberOrMissing,
    clay_decay: NumberOrMissing,
    clay_decay_unit: str,
) -> float | ResultMissing:
    """The clay partitioning ratio ``x``. PROPOSED form (module docstring).

    ``x / (x + 1)`` of what decomposes goes to CO2 and ``1 / (x + 1)`` to
    BIO + HUM; that split is the caller's (``pools.step``), which holds the
    share of the formed BIO + HUM that goes to BIO.

    - ``clay_content``: the clay content of the soil, zero or more.
    - ``scale``, ``intercept``, ``clay_coefficient``: dimensionless constants.
    - ``clay_decay``: per the unit of the clay content, its record unit
      written ``X-1``; ``clay_decay_unit`` is ``X``, the unit of the clay
      content itself.

    Returns ``x``, or ``MISSING_INPUT`` (an argument is missing) or
    ``NOT_COMPUTABLE`` (a value is not finite; a negative clay content; the
    unit of ``clay_decay`` is not the unit of the clay content per ``X-1``;
    the form gives a ratio that is not positive, which the split could not
    carry).

    Raises ``TypeError`` for an argument of another type.
    """
    check_types(
        {
            "clay_content": clay_content,
            "scale": scale,
            "intercept": intercept,
            "clay_coefficient": clay_coefficient,
            "clay_decay": clay_decay,
        }
    )
    check_text("clay_content_unit", clay_content_unit)
    check_text("clay_decay_unit", clay_decay_unit)
    values = numbers_or_missing(
        {
            "clay_content": clay_content,
            "scale": scale,
            "intercept": intercept,
            "clay_coefficient": clay_coefficient,
            "clay_decay": clay_decay,
        }
    )
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, ("clay_content",), is_not_negative, "is negative")
    if refused is not None:
        return refused
    differ = unit_is_not(
        "clay_decay_unit",
        clay_decay_unit,
        clay_content_unit,
        "the clay decay constant is per the unit of the clay content",
    )
    if differ is not None:
        return differ
    try:
        ratio = real(
            values["scale"]
            * (
                values["intercept"]
                + values["clay_coefficient"]
                * math.exp(-values["clay_decay"] * values["clay_content"])
            )
        )
        real(ratio + 1)  # the split divides by x + 1
    except (ArithmeticError, ValueError, OverflowError):
        return no_finite_result("clay_partition", "the partitioning ratio")
    if not is_positive(ratio):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "clay_partition: the partitioning ratio is not positive for these "
                "arguments, so the share that goes to CO2 could not be built"
            ),
        )
    return ratio


def maximum_tsmd(
    *,
    clay_content: NumberOrMissing,
    clay_content_unit: str,
    depth: NumberOrMissing,
    depth_unit: str,
    intercept: NumberOrMissing,
    intercept_unit: str,
    clay_coefficient: NumberOrMissing,
    clay_coefficient_unit: str,
    clay_squared_coefficient: NumberOrMissing,
    clay_squared_coefficient_unit: str,
    reference_depth: NumberOrMissing,
    reference_depth_unit: str,
) -> float | ResultMissing:
    """The maximum total soil moisture deficit. PROPOSED form (module docstring).

    The form is printed for the sampling layer of the reference depth; the
    deficit of another depth is scaled by ``depth / reference_depth``.

    - ``clay_content``: zero or more, in ``clay_content_unit``.
    - ``depth``: the depth of the layer the deficit is tracked over.
    - ``intercept``: the deficit of the reference layer without clay, in the
      unit of the water quantities (``intercept_unit``).
    - ``clay_coefficient``: per the unit of the clay content, so its unit is
      the intercept unit, the clay unit and ``-1``, written
      ``'<intercept unit> <clay unit>-1'``.
    - ``clay_squared_coefficient``: as ``clay_coefficient``, per the clay
      content squared, written ``'<intercept unit> <clay unit>-2'``; the form
      subtracts its term.
    - ``reference_depth``: in the unit of ``depth``.

    Returns the maximum deficit, a negative number (zero is field capacity),
    or ``MISSING_INPUT`` / ``NOT_COMPUTABLE`` (not finite; a clay content
    that is negative; a depth or reference depth that is not positive, since
    a soil layer has a thickness; unit strings that do not follow the
    relations above; a maximum deficit the form does not make negative).

    Raises ``TypeError`` for an argument of another type.
    """
    check_types(
        {
            "clay_content": clay_content,
            "depth": depth,
            "intercept": intercept,
            "clay_coefficient": clay_coefficient,
            "clay_squared_coefficient": clay_squared_coefficient,
            "reference_depth": reference_depth,
        }
    )
    for name, unit in (
        ("clay_content_unit", clay_content_unit),
        ("depth_unit", depth_unit),
        ("intercept_unit", intercept_unit),
        ("clay_coefficient_unit", clay_coefficient_unit),
        ("clay_squared_coefficient_unit", clay_squared_coefficient_unit),
        ("reference_depth_unit", reference_depth_unit),
    ):
        check_text(name, unit)
    values = numbers_or_missing(
        {
            "clay_content": clay_content,
            "depth": depth,
            "intercept": intercept,
            "clay_coefficient": clay_coefficient,
            "clay_squared_coefficient": clay_squared_coefficient,
            "reference_depth": reference_depth,
        }
    )
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, ("clay_content",), is_not_negative, "is negative")
    if refused is None:
        refused = outside(
            values,
            ("depth", "reference_depth"),
            is_positive,
            "is not positive",
        )
    if refused is not None:
        return refused
    problems = [
        problem
        for problem in (
            unit_is_not(
                "depth_unit",
                depth_unit,
                reference_depth_unit,
                "the soil depth is divided by the reference depth",
            ),
            unit_is_not(
                "clay_coefficient_unit",
                clay_coefficient_unit,
                f"{intercept_unit} {clay_content_unit}-1",
                "the clay coefficient multiplies the clay content and adds to the "
                "intercept",
            ),
            unit_is_not(
                "clay_squared_coefficient_unit",
                clay_squared_coefficient_unit,
                f"{intercept_unit} {clay_content_unit}-2",
                "the squared clay coefficient multiplies the squared clay content "
                "and its term is subtracted",
            ),
        )
        if problem is not None
    ]
    if problems:
        return problems[0]
    if values["reference_depth"] == 0:
        return no_finite_result("maximum_tsmd", "the maximum deficit")
    try:
        of_reference_layer = real(
            values["intercept"]
            + values["clay_coefficient"] * values["clay_content"]
            - values["clay_squared_coefficient"]
            * values["clay_content"]
            * values["clay_content"]
        )
        maximum = real(-of_reference_layer * values["depth"] / values["reference_depth"])
    except (ArithmeticError, ValueError, OverflowError):
        return no_finite_result("maximum_tsmd", "the maximum deficit")
    if not is_not_negative(-maximum):  # the deficit cannot be positive
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "maximum_tsmd: the maximum deficit is not negative for these "
                "arguments, and a soil moisture deficit lies below field capacity"
            ),
        )
    return maximum


def advance_deficit(
    *,
    deficit: NumberOrMissing,
    maximum: NumberOrMissing,
    maximum_unit: str,
    rainfall: NumberOrMissing,
    rainfall_unit: str,
    pan_evaporation: NumberOrMissing,
    pan_evaporation_unit: str,
    pan_factor: NumberOrMissing,
) -> float | ResultMissing:
    """One month of the water balance: the deficit after the month. PROPOSED form.

    The deficit is a negative number that grows in magnitude by
    ``pan_factor * pan_evaporation - rainfall`` in the months the demand
    exceeds the rain, shrinks in the others, and is held between the maximum
    deficit and field capacity (zero): the soil can be no drier than its
    maximum deficit and no wetter than field capacity. ``pan_factor`` is the
    share of open-pan evaporation the model uses internally; when pan
    evaporation is unavailable the caller stands the potential
    evapotranspiration divided by that share in its place, as the
    description transcribes.

    Returns the new deficit, or ``MISSING_INPUT`` / ``NOT_COMPUTABLE``
    (not finite; a negative rainfall, pan evaporation or pan factor; a pan
    factor outside zero to one; a maximum deficit that is not negative; a
    starting deficit outside the maximum deficit and field capacity; unit
    strings that differ).

    Raises ``TypeError`` for an argument of another type.
    """
    check_types(
        {
            "deficit": deficit,
            "maximum": maximum,
            "rainfall": rainfall,
            "pan_evaporation": pan_evaporation,
            "pan_factor": pan_factor,
        }
    )
    check_text("rainfall_unit", rainfall_unit)
    check_text("pan_evaporation_unit", pan_evaporation_unit)
    check_text("maximum_unit", maximum_unit)
    values = numbers_or_missing(
        {
            "deficit": deficit,
            "maximum": maximum,
            "rainfall": rainfall,
            "pan_evaporation": pan_evaporation,
            "pan_factor": pan_factor,
        }
    )
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values,
        ("rainfall", "pan_evaporation"),
        is_not_negative,
        "is negative",
    )
    if refused is None:
        refused = outside(values, ("pan_factor",), is_fraction, "is outside zero to one")
    if refused is not None:
        return refused
    differ = units_differ(
        {
            "rainfall_unit": rainfall_unit,
            "pan_evaporation_unit": pan_evaporation_unit,
            "maximum_unit": maximum_unit,
        },
        "subtracted from each other",
    )
    if differ is not None:
        return differ
    maximum_deficit = values["maximum"]
    if maximum_deficit > 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "advance_deficit: the maximum deficit is not negative, and a soil "
                "moisture deficit lies below field capacity"
            ),
        )
    if not maximum_deficit <= values["deficit"] <= 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "advance_deficit: the deficit at the start of the month lies outside "
                "the maximum deficit and field capacity (zero)"
            ),
        )
    try:
        change = real(
            values["pan_factor"] * values["pan_evaporation"] - values["rainfall"]
        )
        moved = real(values["deficit"] - change)
        # Held at the maximum deficit and at field capacity: clamped, because
        # the description says the deficit is "held at the max" until the soil
        # wets up and the soil can be no wetter than field capacity.
        new_deficit = real(min(max(moved, maximum_deficit), 0))
    except (ArithmeticError, ValueError, OverflowError):
        return no_finite_result("advance_deficit", "the new deficit")
    if finite(new_deficit) is None:
        return no_finite_result("advance_deficit", "the new deficit")
    return new_deficit


def bare_soil_deficit(
    *,
    deficit_before: NumberOrMissing,
    advanced: NumberOrMissing,
    maximum: NumberOrMissing,
    cover_state: NumberOrMissing,
    divisor: NumberOrMissing,
) -> float | ResultMissing:
    """The bare-soil moisture deficit (BareSMD) of D223 of issue #77. PROPOSED form.

    D223: "in a bare month the deficit may not fall below the maximum deficit
    divided by [the divisor], unless it is already below it" (model
    description p. 10; users guide p. 11). The divisor is the record
    ``rothc_bare_tsmd_divisor``; no value of it is written here.

    - ``deficit_before``: the deficit at the start of the month.
    - ``advanced``: the deficit after the month as ``advance_deficit`` gives
      it (held at the maximum deficit and at field capacity).
    - ``maximum``: the maximum deficit, negative, the one ``advance_deficit``
      was given.
    - ``cover_state``: one (vegetated) or zero (bare), the encoding of
      ``cover_modifier``.
    - ``divisor``: the divisor of the maximum deficit, positive.

    In a vegetated month the result is ``advanced``. In a bare month it is
    ``advanced``, but never below the bare limit ``maximum / divisor``, or
    below ``deficit_before`` when that is already below the limit:
    ``max(advanced, min(maximum / divisor, deficit_before))``. A bare month
    that does not dry the soil (``advanced`` not below ``deficit_before``)
    cannot meet the limit, so it gives ``advanced`` without reading the
    divisor: a missing divisor is then not needed and not named.

    Returns the deficit, or ``MISSING_INPUT`` / ``NOT_COMPUTABLE`` (not
    finite; a divisor that is not positive; a cover state that is neither of
    the two).

    Raises ``TypeError`` for an argument of another type.
    """
    arguments = {
        "deficit_before": deficit_before,
        "advanced": advanced,
        "maximum": maximum,
        "cover_state": cover_state,
        "divisor": divisor,
    }
    check_types(arguments)
    first = numbers_or_missing(
        {name: arguments[name] for name in ("advanced", "cover_state")}
    )
    if isinstance(first, ResultMissing):
        return first
    state = first["cover_state"]
    if state == 1:
        return first["advanced"]
    if state != 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"bare_soil_deficit: the cover state {state} is neither of the two "
                "states of this encoding: zero (bare) or one (vegetated)"
            ),
        )
    before = numbers_or_missing({"deficit_before": deficit_before})
    if isinstance(before, ResultMissing):
        return before
    if not first["advanced"] < before["deficit_before"]:
        return first["advanced"]
    values = numbers_or_missing(
        {name: arguments[name] for name in ("maximum", "divisor")}
    )
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, ("divisor",), is_positive, "is not positive")
    if refused is not None:
        return refused
    try:
        limit = real(values["maximum"] / values["divisor"])
        result = real(max(first["advanced"], min(limit, before["deficit_before"])))
    except (ArithmeticError, ValueError, OverflowError):
        return no_finite_result("bare_soil_deficit", "the deficit")
    if finite(result) is None:
        return no_finite_result("bare_soil_deficit", "the deficit")
    return result


def moisture_modifier(
    *,
    deficit: NumberOrMissing,
    maximum: NumberOrMissing,
    threshold_fraction: NumberOrMissing,
    minimum: NumberOrMissing,
) -> float | ResultMissing:
    """The moisture rate modifier ``b``. PROPOSED form (module docstring).

    - ``deficit``: the accumulated TSMD at the start of the month (the
      description applies it to the month with that deficit), between the
      maximum deficit and field capacity (zero).
    - ``maximum``: the maximum TSMD, negative.
    - ``threshold_fraction``: the share of the maximum deficit at and above
      which the modifier is one (the description prints it as a fraction of
      the maximum deficit).
    - ``minimum``: the modifier at the maximum deficit.

    Returns ``b``, or ``MISSING_INPUT`` / ``NOT_COMPUTABLE`` (not finite; a
    threshold or minimum outside zero to one; a maximum deficit that is not
    negative; a deficit outside the maximum deficit and field capacity; a
    form that divides by zero, which happens when the threshold fraction is
    one).

    Raises ``TypeError`` for an argument of another type.
    """
    check_types(
        {
            "deficit": deficit,
            "maximum": maximum,
            "threshold_fraction": threshold_fraction,
            "minimum": minimum,
        }
    )
    values = numbers_or_missing(
        {
            "deficit": deficit,
            "maximum": maximum,
            "threshold_fraction": threshold_fraction,
            "minimum": minimum,
        }
    )
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values,
        ("threshold_fraction", "minimum"),
        is_fraction,
        "is outside zero to one",
    )
    if refused is not None:
        return refused
    maximum_deficit = values["maximum"]
    if maximum_deficit > 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "moisture_modifier: the maximum deficit is not negative, and a soil "
                "moisture deficit lies below field capacity"
            ),
        )
    if not maximum_deficit <= values["deficit"] <= 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "moisture_modifier: the deficit lies outside the maximum deficit and "
                "field capacity (zero)"
            ),
        )
    threshold = values["threshold_fraction"] * maximum_deficit
    if values["deficit"] > threshold:
        return 1.0
    try:
        spread = real(maximum_deficit - threshold)  # > 0: threshold < maximum deficit
        modifier = real(
            values["minimum"]
            + (1 - values["minimum"]) * (maximum_deficit - values["deficit"]) / spread
        )
    except (ArithmeticError, ValueError, ZeroDivisionError):
        return no_finite_result("moisture_modifier", "the moisture rate modifier")
    return modifier


def cover_modifier(
    *,
    cover_state: NumberOrMissing,
    vegetated_factor: NumberOrMissing,
    bare_factor: NumberOrMissing,
) -> float | ResultMissing:
    """The soil cover factor ``c``. PROPOSED form (module docstring).

    - ``cover_state``: the state of the soil cover of the month as a number:
      one when the soil is vegetated, zero when it is bare (an encoding
      PROPOSED by this folder; which cover quantity the forcing carries is
      OPEN in contracts/carbon_forcing/README.md, item 8).
    - ``vegetated_factor``, ``bare_factor``: the factor of each state, a
      fraction (the factor of bare soil the description prints as one).

    Returns ``c``, or ``MISSING_INPUT`` / ``NOT_COMPUTABLE`` (not finite; a
    factor outside zero to one; a cover state that is neither of the two).

    Raises ``TypeError`` for an argument of another type.
    """
    check_types(
        {
            "cover_state": cover_state,
            "vegetated_factor": vegetated_factor,
            "bare_factor": bare_factor,
        }
    )
    values = numbers_or_missing(
        {
            "cover_state": cover_state,
            "vegetated_factor": vegetated_factor,
            "bare_factor": bare_factor,
        }
    )
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values,
        ("vegetated_factor", "bare_factor"),
        is_fraction,
        "is outside zero to one",
    )
    if refused is not None:
        return refused
    state = values["cover_state"]
    if state == 0:
        return values["bare_factor"]
    if state == 1:
        return values["vegetated_factor"]
    return ResultMissing(
        reason="NOT_COMPUTABLE",
        detail=(
            f"cover_modifier: the cover state {state} is neither of the two states "
            "of this encoding: zero (bare) or one (vegetated)"
        ),
    )


def rate_modifying_factor(
    *,
    temperature_factor: NumberOrMissing,
    moisture_factor: NumberOrMissing,
    cover_factor: NumberOrMissing,
) -> float | ResultMissing:
    """The combined rate modifying factor ``abc = a * b * c``.

    Each factor is its own function's result; this one only multiplies, so a
    factor that another function refused can be passed on as it is.

    Returns ``abc``, or ``MISSING_INPUT`` (a factor is missing, named with
    its reason) or ``NOT_COMPUTABLE`` (a factor is not finite or negative:
    a rate modifier cannot speed decomposition up below zero).

    Raises ``TypeError`` for an argument of another type.
    """
    numbers = {
        "temperature_factor (a)": temperature_factor,
        "moisture_factor (b)": moisture_factor,
        "cover_factor (c)": cover_factor,
    }
    check_types(numbers)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, values.keys(), is_not_negative, "is negative")
    if refused is not None:
        return refused
    try:
        factor = real(math.prod(values.values()))
    except (ArithmeticError, ValueError, OverflowError):
        return no_finite_result("rate_modifying_factor", "the combined factor")
    if finite(factor) is None:
        return no_finite_result("rate_modifying_factor", "the combined factor")
    return factor
