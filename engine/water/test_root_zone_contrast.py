"""Tests for ``engine/water/root_zone_contrast.py``.

Covers CQ7 (GWETROOT) unit guard (C1.1), ``[0, 1]`` observed wetness bounds,
``storage / capacity_mm`` calculation with zero-capacity and missing-input
guards, daily pairing against ``SiteClimate``, G1 immutability, G5 ``TypeError``
checks, and no-threshold AST inspection.

Every storage series, capacity, date, and wetness value here is synthetic
PLACEHOLDER test data, plainly not real.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import inspect
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import (
    ClimatePoint,
    DailySeries,
    DailyValue,
    SiteClimate,
)
from contracts.results.models import Missing
from engine.water import root_zone_contrast
from engine.water.root_zone_contrast import (
    ROOT_ZONE_WETNESS,
    ROOT_ZONE_WETNESS_UNIT,
    PairedWetnessDay,
    WetnessPairing,
    compute_daily_relative_wetness,
    compute_day_relative_wetness,
    pair_root_zone_wetness,
    read_observed_root_zone_wetness,
)

PLACEHOLDER_CAPACITY_MM = 120.0  # PLACEHOLDER synthetic capacity


def _point() -> ClimatePoint:
    range_missing = InputsMissing(
        reason="NOT_AVAILABLE",
        detail="PLACEHOLDER: synthetic test point has no range",
    )
    return ClimatePoint(
        latitude=Value(
            value=1.11,
            unit="degree",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        longitude=Value(
            value=2.22,
            unit="degree",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        elevation=Value(
            value=3.33,
            unit="m",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
    )


def _wetness_series(
    start: dt.date,
    values: list[float | InputsMissing],
    *,
    quantity: str = ROOT_ZONE_WETNESS,
    unit: str = ROOT_ZONE_WETNESS_UNIT,
    time_zone: str = "UTC",
) -> DailySeries:
    end = start + dt.timedelta(days=len(values) - 1)
    days = []
    for offset, item in enumerate(values):
        day = start + dt.timedelta(days=offset)
        if isinstance(item, InputsMissing):
            days.append(DailyValue(date=day, value=None, missing=item))
        else:
            days.append(DailyValue(date=day, value=item, missing=None))
    has_present = any(not isinstance(item, InputsMissing) for item in values)
    return DailySeries(
        quantity=quantity,
        unit=unit,
        time_zone=time_zone,
        start_date=start,
        end_date=end,
        provenance="OBSERVED" if has_present else None,
        source="PLACEHOLDER synthetic GWETROOT series" if has_present else None,
        range_missing=(
            InputsMissing(
                reason="NO_COVERAGE",
                detail="PLACEHOLDER synthetic series has no range",
            )
            if has_present
            else None
        ),
        days=days,
    )


def _climate(series: list[DailySeries]) -> SiteClimate:
    return SiteClimate(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_point(),
        daily_series=series,
        monthly_series=[],
    )


# --- constants and zero-default signature checks -----------------------------


def test_cq7_proposed_constants():
    assert ROOT_ZONE_WETNESS == "soil_wetness_root_zone"
    assert ROOT_ZONE_WETNESS_UNIT == "dimensionless"


@pytest.mark.parametrize(
    "fn",
    [
        compute_day_relative_wetness,
        compute_daily_relative_wetness,
        pair_root_zone_wetness,
    ],
)
def test_capacity_mm_is_keyword_only_with_no_default(fn):
    param = inspect.signature(fn).parameters["capacity_mm"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_omitting_capacity_mm_raises_type_error():
    day = dt.date(2020, 1, 1)
    climate = _climate([_wetness_series(day, [0.5])])
    with pytest.raises(TypeError):
        compute_day_relative_wetness(60.0)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        compute_daily_relative_wetness({day: 60.0})  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        pair_root_zone_wetness({day: 60.0}, climate)  # type: ignore[call-arg]


# --- daily relative wetness computation --------------------------------------


@pytest.mark.parametrize(
    ("storage", "capacity", "expected"),
    [
        (0.0, 100.0, 0.0),
        (25, 100, 0.25),
        (60.0, 120.0, 0.5),
        (120.0, 120.0, 1.0),
    ],
)
def test_compute_day_relative_wetness_valid_values(storage, capacity, expected):
    result = compute_day_relative_wetness(storage, capacity_mm=capacity)
    assert isinstance(result, float)
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "bad_capacity",
    [0, 0.0, -0.0, -10.0, math.nan, math.inf, -math.inf, 10**400],
)
def test_zero_negative_or_non_finite_capacity_returns_not_computable(bad_capacity):
    result = compute_day_relative_wetness(50.0, capacity_mm=bad_capacity)
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "capacity_mm" in (result.detail or "")


def test_missing_capacity_returns_missing_input():
    cap_missing = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER missing capacity")
    result = compute_day_relative_wetness(50.0, capacity_mm=cap_missing)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert "capacity_mm" in (result.detail or "")
    assert "NOT_DECLARED" in (result.detail or "")


def test_missing_storage_returns_missing_input():
    storage_missing = Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER upstream")
    result = compute_day_relative_wetness(
        storage_missing, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert "storage_mm" in (result.detail or "")
    assert "NOT_COMPUTABLE" in (result.detail or "")


@pytest.mark.parametrize("bad_storage", [math.nan, math.inf, -math.inf, 10**400])
def test_non_finite_storage_returns_not_computable(bad_storage):
    result = compute_day_relative_wetness(
        bad_storage, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"


def test_overflow_ratio_returns_not_computable():
    result = compute_day_relative_wetness(1e308, capacity_mm=1e-308)
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"


def test_compute_daily_relative_wetness_sorts_dates_and_preserves_missing_days():
    d1 = dt.date(2020, 3, 1)
    d2 = dt.date(2020, 3, 2)
    d3 = dt.date(2020, 3, 3)
    storage = {
        d3: 90.0,
        d1: 30.0,
        d2: Missing(reason="MISSING_INPUT", detail="PLACEHOLDER gap"),
    }
    result = compute_daily_relative_wetness(
        storage, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert list(result) == [d1, d2, d3]
    assert result[d1] == pytest.approx(0.25)
    assert isinstance(result[d2], Missing)
    assert result[d2].reason == "MISSING_INPUT"
    assert result[d3] == pytest.approx(0.75)


def test_compute_daily_relative_wetness_zero_capacity_marks_all_days_not_computable():
    d1 = dt.date(2020, 3, 1)
    d2 = dt.date(2020, 3, 2)
    result = compute_daily_relative_wetness({d1: 10.0, d2: 20.0}, capacity_mm=0.0)
    assert all(
        isinstance(v, Missing) and v.reason == "NOT_COMPUTABLE" for v in result.values()
    )


def test_compute_daily_relative_wetness_empty_mapping():
    assert compute_daily_relative_wetness({}, capacity_mm=PLACEHOLDER_CAPACITY_MM) == {}


# --- reading observed CQ7 wetness from SiteClimate --------------------------


def test_read_observed_root_zone_wetness_accepts_bounds_zero_and_one():
    start = dt.date(2020, 4, 1)
    climate = _climate([_wetness_series(start, [0.0, 0.42, 1.0])])
    observed = read_observed_root_zone_wetness(climate)
    assert isinstance(observed, dict)
    assert observed == {
        dt.date(2020, 4, 1): 0.0,
        dt.date(2020, 4, 2): 0.42,
        dt.date(2020, 4, 3): 1.0,
    }


def test_read_observed_root_zone_wetness_missing_series():
    other = _wetness_series(
        dt.date(2020, 4, 1),
        [5.0, 6.0],
        quantity="precipitation",
        unit="mm day-1",
    )
    climate = _climate([other])
    result = read_observed_root_zone_wetness(climate)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert ROOT_ZONE_WETNESS in (result.detail or "")


@pytest.mark.parametrize(
    "wrong_unit",
    ["%", "mm", "1", "Dimensionless", " dimensionless", "dimensionless "],
)
def test_read_observed_root_zone_wetness_wrong_unit_c1_1(wrong_unit):
    climate = _climate(
        [_wetness_series(dt.date(2020, 4, 1), [0.5, 0.6], unit=wrong_unit)]
    )
    result = read_observed_root_zone_wetness(climate)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert wrong_unit in (result.detail or "")
    assert ROOT_ZONE_WETNESS_UNIT in (result.detail or "")


def test_read_observed_root_zone_wetness_empty_unit_via_model_construct():
    bad_series = DailySeries.model_construct(
        quantity=ROOT_ZONE_WETNESS,
        unit="",
        time_zone="UTC",
        start_date=dt.date(2020, 4, 1),
        end_date=dt.date(2020, 4, 1),
        provenance="OBSERVED",
        source="PLACEHOLDER",
        range_missing=InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER"),
        days=[DailyValue(date=dt.date(2020, 4, 1), value=0.5, missing=None)],
    )
    climate = _climate([bad_series])
    result = read_observed_root_zone_wetness(climate)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert "C1.1" in (result.detail or "")


@pytest.mark.parametrize(
    "bad_value", [-0.0001, -1.0, 1.0001, 2.5, math.nan, math.inf, -math.inf]
)
def test_read_observed_root_zone_wetness_out_of_bounds_or_non_finite(bad_value):
    start = dt.date(2020, 4, 1)
    bad_series = DailySeries.model_construct(
        quantity=ROOT_ZONE_WETNESS,
        unit=ROOT_ZONE_WETNESS_UNIT,
        time_zone="UTC",
        start_date=start,
        end_date=dt.date(2020, 4, 3),
        provenance="OBSERVED",
        source="PLACEHOLDER",
        range_missing=InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER"),
        days=[
            DailyValue.model_construct(
                date=dt.date(2020, 4, 1), value=0.2, missing=None
            ),
            DailyValue.model_construct(
                date=dt.date(2020, 4, 2), value=bad_value, missing=None
            ),
            DailyValue.model_construct(
                date=dt.date(2020, 4, 3), value=0.8, missing=None
            ),
        ],
    )
    observed = read_observed_root_zone_wetness(_climate([bad_series]))
    assert isinstance(observed, dict)
    assert observed[dt.date(2020, 4, 1)] == 0.2
    assert isinstance(observed[dt.date(2020, 4, 2)], Missing)
    assert observed[dt.date(2020, 4, 2)].reason == "NOT_COMPUTABLE"
    assert observed[dt.date(2020, 4, 3)] == 0.8


def test_read_observed_root_zone_wetness_missing_day_in_series():
    start = dt.date(2020, 4, 1)
    climate = _climate(
        [
            _wetness_series(
                start,
                [
                    0.3,
                    InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER gap"),
                    0.7,
                ],
            )
        ]
    )
    observed = read_observed_root_zone_wetness(climate)
    assert isinstance(observed, dict)
    assert observed[dt.date(2020, 4, 1)] == 0.3
    mid = observed[dt.date(2020, 4, 2)]
    assert isinstance(mid, Missing)
    assert mid.reason == "MISSING_INPUT"
    assert "NO_COVERAGE" in (mid.detail or "")
    assert observed[dt.date(2020, 4, 3)] == 0.7


# --- pairing modelled and observed wetness -----------------------------------


def test_pair_root_zone_wetness_partial_coverage_and_immutability():
    d1 = dt.date(2020, 5, 1)
    d2 = dt.date(2020, 5, 2)
    d3 = dt.date(2020, 5, 3)
    storage = {d1: 30.0, d2: 60.0}
    climate = _climate([_wetness_series(d2, [0.55, 0.75])])
    storage_before = copy.deepcopy(storage)
    climate_before = copy.deepcopy(climate)

    pairing = pair_root_zone_wetness(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert storage == storage_before
    assert climate == climate_before
    assert isinstance(pairing, WetnessPairing)
    assert pairing.series_missing is None
    assert [d.date for d in pairing.days] == [d1, d2, d3]

    day1, day2, day3 = pairing.days
    assert isinstance(day1, PairedWetnessDay)
    assert day1.modelled_wetness == pytest.approx(0.25)
    assert isinstance(day1.observed_wetness, Missing)
    assert day1.observed_wetness.reason == "NO_COVERAGE"

    assert day2.modelled_wetness == pytest.approx(0.5)
    assert day2.observed_wetness == pytest.approx(0.55)

    assert isinstance(day3.modelled_wetness, Missing)
    assert day3.modelled_wetness.reason == "NO_COVERAGE"
    assert day3.observed_wetness == pytest.approx(0.75)

    with pytest.raises(FrozenInstanceError):
        day2.modelled_wetness = 0.0  # type: ignore[misc]


def test_pair_root_zone_wetness_absent_cq7_records_series_missing():
    d1 = dt.date(2020, 5, 1)
    pairing = pair_root_zone_wetness(
        {d1: 60.0}, _climate([]), capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert isinstance(pairing.series_missing, Missing)
    assert pairing.series_missing.reason == "MISSING_INPUT"
    assert len(pairing.days) == 1
    assert pairing.days[0].modelled_wetness == pytest.approx(0.5)
    assert pairing.days[0].observed_wetness == pairing.series_missing


# --- G5: caller TypeError checks ---------------------------------------------


@pytest.mark.parametrize(
    "bad", [True, False, "100", None, [], {}, InputsMissing(reason="NOT_DECLARED")]
)
def test_wrong_types_raise_type_error(bad):
    d1 = dt.date(2020, 1, 1)
    climate = _climate([])
    with pytest.raises(TypeError):
        compute_day_relative_wetness(bad, capacity_mm=PLACEHOLDER_CAPACITY_MM)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compute_day_relative_wetness(10.0, capacity_mm=bad)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compute_daily_relative_wetness({d1: bad}, capacity_mm=PLACEHOLDER_CAPACITY_MM)  # type: ignore[dict-item]
    with pytest.raises(TypeError):
        pair_root_zone_wetness({d1: 10.0}, climate, capacity_mm=bad)  # type: ignore[arg-type]


def test_non_mapping_or_datetime_key_raises_type_error():
    with pytest.raises(TypeError):
        compute_daily_relative_wetness([(dt.date(2020, 1, 1), 10.0)], capacity_mm=100.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compute_daily_relative_wetness(
            {dt.datetime(2020, 1, 1, 0, 0): 10.0},  # type: ignore[dict-item]
            capacity_mm=100.0,
        )
    with pytest.raises(TypeError):
        read_observed_root_zone_wetness("not-climate")  # type: ignore[arg-type]


def test_wrong_daily_value_type_inside_climate_raises_type_error():
    bad_series = DailySeries.model_construct(
        quantity=ROOT_ZONE_WETNESS,
        unit=ROOT_ZONE_WETNESS_UNIT,
        time_zone="UTC",
        start_date=dt.date(2020, 1, 1),
        end_date=dt.date(2020, 1, 1),
        provenance="OBSERVED",
        source="PLACEHOLDER",
        range_missing=InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER"),
        days=[
            DailyValue.model_construct(
                date=dt.date(2020, 1, 1), value=True, missing=None
            )
        ],
    )
    with pytest.raises(TypeError):
        read_observed_root_zone_wetness(_climate([bad_series]))


# --- AST check: pure function, zero thresholds/defaults ----------------------


def test_module_has_no_thresholds_io_or_forbidden_names():
    tree = ast.parse(Path(root_zone_contrast.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "collections",
        "contracts",
        "dataclasses",
        "datetime",
        "math",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {"open", "input", "eval", "exec"}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not attributes & {"today", "now", "utcnow"}
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float)
    }
    # Only 0 (zero-capacity guard and lower wetness bound) and 1 (upper wetness bound).
    assert numbers <= {0, 1}
