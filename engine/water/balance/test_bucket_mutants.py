"""Mutant-killing tests for engine/water/balance/bucket.py.

Every value in this file is a PLACEHOLDER chosen solely to exercise boundary,
clamping, floating-point association, missing-detail, and input-validation
paths. None comes from any source or represents a real physical parameter.
"""

from __future__ import annotations

import datetime

import pytest

from contracts.results.models import Missing
from engine.water.balance import CropDay, DayInput, run_balance, step

START = datetime.date(2001, 1, 1)  # PLACEHOLDER
CAPACITY = 50.0  # PLACEHOLDER
COLUMN_DEPTH = 4.0  # PLACEHOLDER


def _day(
    offset: int = 0,
    *,
    p: float | Missing = 0.0,
    q: float | Missing = 0.0,
    et0: float | Missing = 0.0,
    ke: float | Missing = 0.0,
    crop: CropDay | None | Missing = None,
) -> DayInput:
    return DayInput(
        date=START + datetime.timedelta(days=offset),
        precipitation=p,
        runoff=q,
        reference_evapotranspiration=et0,
        evaporation_coefficient=ke,
        crop=crop,
    )


def test_step_missing_storage_without_detail_omits_none_suffix():
    # Kills mutant replacing `if storage_start.detail is not None:` with `if True:`.
    result = step(
        Missing(reason="NO_COVERAGE"),
        _day(),
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )
    assert isinstance(result.storage_end, Missing)
    assert result.storage_end.reason == "MISSING_INPUT"
    assert result.storage_end.detail == "storage at the start of the day"


def test_run_balance_preserves_original_missing_cause_without_nesting():
    # Kills mutant overwriting `cause` on subsequent missing days (`if cause is None:`).
    days = [
        _day(0, p=1.0),
        _day(1, p=Missing(reason="NO_COVERAGE")),
        _day(2, p=1.0),
        _day(3, p=1.0),
    ]
    results = run_balance(
        days,
        initial_storage=10.0,  # PLACEHOLDER
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )
    expected_cause = f"input of {days[1].date.isoformat()}: precipitation (NO_COVERAGE)"
    for idx in (2, 3):
        detail = results[idx].storage_end.detail
        assert detail == (
            f"storage at the start of the day: storage after {days[idx - 1].date.isoformat()}, "
            f"missing since: {expected_cause}"
        )


def test_step_rejects_datetime_subclass_as_date():
    # Kills mutant dropping `isinstance(day.date, datetime.datetime)` check.
    bad_day = DayInput(
        date=datetime.datetime(2001, 1, 1, 12, 0),  # type: ignore[arg-type]  # PLACEHOLDER
        precipitation=0.0,
        runoff=0.0,
        reference_evapotranspiration=0.0,
        evaporation_coefficient=0.0,
        crop=None,
    )
    with pytest.raises(TypeError, match="datetime.date"):
        step(10.0, bad_day, capacity=CAPACITY, column_depth=COLUMN_DEPTH)


def test_inflow_subtracts_runoff_from_precipitation_before_adding_storage():
    # Kills mutant changing `storage_start + (precipitation - runoff)` to
    # `storage_start + precipitation - runoff` (catastrophic cancellation).
    tiny_storage = 1e-10  # PLACEHOLDER
    huge_precip = 1e10  # PLACEHOLDER
    result = step(
        tiny_storage,
        _day(p=huge_precip, q=huge_precip),
        capacity=1.0,  # PLACEHOLDER
        column_depth=1.0,  # PLACEHOLDER
    )
    assert result.storage_end == pytest.approx(tiny_storage, rel=1e-12, abs=0.0)


def test_huge_integer_raises_value_error_not_overflow_error():
    # Kills mutant removing `except OverflowError:` in `_check_number`.
    with pytest.raises(ValueError, match="finite"):
        step(
            10**400,  # PLACEHOLDER
            _day(),
            capacity=CAPACITY,
            column_depth=COLUMN_DEPTH,
        )


@pytest.mark.parametrize("empty_seq", ["", b""])
def test_run_balance_rejects_empty_str_or_bytes(empty_seq):
    # Kills mutant removing `isinstance(days, (str, bytes))` guard.
    with pytest.raises(TypeError, match="sequence"):
        run_balance(
            empty_seq,  # type: ignore[arg-type]
            initial_storage=10.0,  # PLACEHOLDER
            capacity=CAPACITY,
            column_depth=COLUMN_DEPTH,
        )


def test_crop_with_zero_transpiration_coefficient_is_allowed():
    # Kills mutant rejecting `transpiration_coefficient == 0.0`.
    c = CropDay(
        transpiration_coefficient=0.0,  # PLACEHOLDER
        root_depth=2.0,  # PLACEHOLDER
        readily_available_fraction=0.5,  # PLACEHOLDER
    )
    result = step(
        25.0,  # PLACEHOLDER
        _day(et0=5.0, crop=c),
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )
    assert result.transpiration_demanded == 0.0
    assert result.transpiration == 0.0
    assert result.transpiration_shortfall == 0.0
    assert result.stress_coefficient == 1.0
