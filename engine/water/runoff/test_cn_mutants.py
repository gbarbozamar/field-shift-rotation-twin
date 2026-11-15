"""Mutant-killing tests for engine/water/runoff/curve_number.py.

Every value in this file is a PLACEHOLDER chosen solely to exercise boundary,
overflow, missing-propagation, and input-validation paths. None comes from any
source or represents a real Curve Number parameter.
"""

from __future__ import annotations

import dataclasses
import datetime

import pytest

from contracts.results.models import Missing
from engine.water.runoff import (
    PRECIPITATION_UNIT,
    CurveNumberConstants,
    PrecipitationValue,
    RunoffDayInput,
    initial_abstraction,
    potential_retention,
    run_runoff,
    runoff_depth,
)

DAY = datetime.date(2001, 3, 5)  # PLACEHOLDER
GUARD = "NOT_COMPUTABLE"  # PLACEHOLDER
CONSTANTS = CurveNumberConstants(
    initial_abstraction_ratio=0.5,  # PLACEHOLDER
    retention_numerator=11.25,  # PLACEHOLDER
    retention_offset=0.375,  # PLACEHOLDER
    retention_unit_factor=3.0,  # PLACEHOLDER
)


def test_runoff_depth_does_not_repeat_initial_abstraction_when_retention_is_missing():
    # Kills mutant changing `elif isinstance(abstraction, Missing):` to `if`.
    result = runoff_depth(
        12.0,  # PLACEHOLDER
        Missing(reason="NOT_DECLARED"),
        constants=CONSTANTS,
    )
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert "potential retention" in result.detail
    assert "initial abstraction" not in result.detail


def test_initial_abstraction_overflow_is_not_computable():
    # Kills mutant removing `if not _is_finite(abstraction):` in `initial_abstraction`.
    result = initial_abstraction(
        1e300,  # PLACEHOLDER
        constants=dataclasses.replace(
            CONSTANTS,
            initial_abstraction_ratio=1e20,  # PLACEHOLDER
        ),
    )
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"


def test_huge_integer_returns_not_computable_instead_of_overflow_error():
    # Kills mutant removing `except OverflowError:` in `_is_finite`.
    result = potential_retention(10**400, constants=CONSTANTS)  # PLACEHOLDER
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "curve_number" in result.detail


@pytest.mark.parametrize("empty_seq", ["", b""])
def test_run_runoff_rejects_empty_str_or_bytes(empty_seq):
    # Kills mutant removing `isinstance(days, (str, bytes))` guard.
    with pytest.raises(TypeError, match="sequence"):
        run_runoff(
            empty_seq,  # type: ignore[arg-type]
            constants=CONSTANTS,
            unit_guard_reason=GUARD,
        )


def test_zero_retention_offset_is_computable():
    # Kills mutant adding `retention_offset` to the strictly-positive check.
    constants = dataclasses.replace(CONSTANTS, retention_offset=0.0)  # PLACEHOLDER
    retention = potential_retention(10.0, constants=constants)  # PLACEHOLDER
    assert retention == pytest.approx(3.0 * (11.25 / 10.0))  # PLACEHOLDER
    days = [
        RunoffDayInput(
            date=DAY,
            precipitation=PrecipitationValue(
                value=12.0, unit=PRECIPITATION_UNIT
            ),  # PLACEHOLDER
            curve_number=10.0,  # PLACEHOLDER
        )
    ]
    out = run_runoff(days, constants=constants, unit_guard_reason=GUARD)
    assert isinstance(out[0].runoff, float)
