"""Tests for ``validation/h5_soil_moisture.py`` (entry [H5], D107, D253).

Every storage series, capacity, date, and GWETROOT wetness series in this
file is synthetic PLACEHOLDER test data, plainly not real. No pass/fail
threshold or tolerance exists for [H5] (D253).
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import inspect
import math
from dataclasses import FrozenInstanceError, fields
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
from engine.water.root_zone_contrast import (
    ROOT_ZONE_WETNESS,
    ROOT_ZONE_WETNESS_UNIT,
    PairedWetnessDay,
    WetnessPairing,
)
from validation import h5_soil_moisture
from validation.h5_soil_moisture import (
    H5_STATUS,
    H5ContrastReport,
    build_h5_contrast_report,
    contrast_report_from_pairing,
)

PLACEHOLDER_CAPACITY_MM = 100.0  # PLACEHOLDER synthetic capacity


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
        time_zone="UTC",
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


# --- D253 contract structure: qualitative only, no pass/fail or tolerance ----


def test_report_has_no_pass_verdict_tolerance_or_threshold_fields():
    field_names = {item.name for item in fields(H5ContrastReport)}
    assert field_names == {
        "paired_days",
        "skipped_days",
        "mean_modelled_wetness",
        "mean_observed_wetness",
        "mean_bias",
        "same_direction_step_fraction",
        "status",
    }
    forbidden = ("pass", "verdict", "tolerance", "threshold")
    assert not any(word in name for name in field_names for word in forbidden)
    assert H5_STATUS == "QUALITATIVE_OBSERVATION_ONLY"


def test_report_rejects_non_qualitative_status_and_is_frozen():
    with pytest.raises(ValueError, match="QUALITATIVE_OBSERVATION_ONLY"):
        H5ContrastReport(
            paired_days=1,
            skipped_days=0,
            mean_modelled_wetness=0.5,
            mean_observed_wetness=0.5,
            mean_bias=0.0,
            same_direction_step_fraction=Missing(
                reason="NOT_COMPUTABLE", detail="single day"
            ),
            status="PASS",  # type: ignore[arg-type]
        )
    report = H5ContrastReport(
        paired_days=2,
        skipped_days=0,
        mean_modelled_wetness=0.5,
        mean_observed_wetness=0.4,
        mean_bias=0.1,
        same_direction_step_fraction=1.0,
    )
    assert report.status == "QUALITATIVE_OBSERVATION_ONLY"
    with pytest.raises(FrozenInstanceError):
        report.paired_days = 99  # type: ignore[misc]


def test_build_h5_contrast_report_capacity_mm_has_no_default():
    param = inspect.signature(build_h5_contrast_report).parameters["capacity_mm"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


# --- descriptive statistics and same-direction step counting -----------------


def test_full_overlap_summary_and_bias_sign():
    start = dt.date(2020, 6, 1)
    # Modelled wetness: [0.2, 0.6, 0.4, 0.8] -> mean 0.5
    # Observed wetness: [0.1, 0.5, 0.3, 0.7] -> mean 0.4
    # Bias (modelled - observed): +0.1 on every day -> mean +0.1
    # Steps: (+,+), (-,-), (+,+) -> 3/3 = 1.0
    storage = {
        dt.date(2020, 6, 1): 20.0,
        dt.date(2020, 6, 2): 60.0,
        dt.date(2020, 6, 3): 40.0,
        dt.date(2020, 6, 4): 80.0,
    }
    climate = _climate([_wetness_series(start, [0.1, 0.5, 0.3, 0.7])])
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.status == "QUALITATIVE_OBSERVATION_ONLY"
    assert report.paired_days == 4
    assert report.skipped_days == 0
    assert report.mean_modelled_wetness == pytest.approx(0.5)
    assert report.mean_observed_wetness == pytest.approx(0.4)
    assert report.mean_bias == pytest.approx(0.1)
    assert report.same_direction_step_fraction == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("modelled_wetness", "observed_wetness", "expected_fraction"),
    [
        # Step 1: +/+ (match), Step 2: -/- (match), Step 3: 0/0 (match) -> 3/3
        ([0.2, 0.5, 0.3, 0.3], [0.1, 0.4, 0.2, 0.2], 1.0),
        # Step 1: +/- (no), Step 2: -/+ (no), Step 3: 0/+ (no) -> 0/3
        ([0.2, 0.5, 0.3, 0.3], [0.6, 0.4, 0.7, 0.8], 0.0),
        # Step 1: +/+ (match), Step 2: -/0 (no), Step 3: +/+ (match), Step 4: -/- (match) -> 3/4
        ([0.2, 0.6, 0.4, 0.7, 0.5], [0.1, 0.3, 0.3, 0.6, 0.2], 0.75),
    ],
)
def test_same_direction_step_counting(
    modelled_wetness, observed_wetness, expected_fraction
):
    start = dt.date(2020, 7, 1)
    storage = {
        start + dt.timedelta(days=offset): val * PLACEHOLDER_CAPACITY_MM
        for offset, val in enumerate(modelled_wetness)
    }
    climate = _climate([_wetness_series(start, observed_wetness)])
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.paired_days == len(modelled_wetness)
    assert report.skipped_days == 0
    assert report.same_direction_step_fraction == pytest.approx(expected_fraction)


def test_step_counting_does_not_bridge_across_a_skipped_day():
    start = dt.date(2020, 8, 1)
    # Day 1 -> Day 2 (skipped missing day) -> Day 3 -> Day 4:
    # Only (Day 3 -> Day 4) is a consecutive daily step (-/- = 1/1 = 1.0).
    # Bridging Day 1 (0.2/0.8) -> Day 3 (0.7/0.5) would be +/- (0/2 = 0.5).
    storage = {
        dt.date(2020, 8, 1): 20.0,
        dt.date(2020, 8, 2): 40.0,
        dt.date(2020, 8, 3): 70.0,
        dt.date(2020, 8, 4): 50.0,
    }
    climate = _climate(
        [
            _wetness_series(
                start,
                [
                    0.8,
                    InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER gap"),
                    0.5,
                    0.2,
                ],
            )
        ]
    )
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.paired_days == 3
    assert report.skipped_days == 1
    assert report.same_direction_step_fraction == pytest.approx(1.0)


def test_single_paired_day_or_non_consecutive_days_give_not_computable_step_fraction():
    d1 = dt.date(2020, 8, 1)
    d3 = dt.date(2020, 8, 3)
    storage = {d1: 30.0, d3: 60.0}
    climate = _climate(
        [
            _wetness_series(
                d1,
                [
                    0.2,
                    InputsMissing(reason="SOURCE_UNAVAILABLE"),
                    0.5,
                ],
            )
        ]
    )
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.paired_days == 2
    assert report.skipped_days == 1
    assert report.mean_modelled_wetness == pytest.approx(0.45)
    assert report.mean_observed_wetness == pytest.approx(0.35)
    assert report.mean_bias == pytest.approx(0.1)
    assert isinstance(report.same_direction_step_fraction, Missing)
    assert report.same_direction_step_fraction.reason == "NOT_COMPUTABLE"


# --- missing series, wrong unit, coverage gaps, out-of-range, zero capacity --


def test_absent_cq7_series_returns_missing_input_on_all_metrics():
    storage = {dt.date(2020, 1, 1): 40.0, dt.date(2020, 1, 2): 50.0}
    report = build_h5_contrast_report(
        storage, _climate([]), capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.status == "QUALITATIVE_OBSERVATION_ONLY"
    assert report.paired_days == 0
    assert report.skipped_days == 2
    for value in (
        report.mean_modelled_wetness,
        report.mean_observed_wetness,
        report.mean_bias,
        report.same_direction_step_fraction,
    ):
        assert isinstance(value, Missing)
        assert value.reason == "MISSING_INPUT"
        assert ROOT_ZONE_WETNESS in (value.detail or "")


def test_wrong_unit_c1_1_returns_missing_input_without_conversion():
    start = dt.date(2020, 1, 1)
    storage = {start: 40.0, start + dt.timedelta(days=1): 50.0}
    climate = _climate([_wetness_series(start, [40.0, 50.0], unit="%")])
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.paired_days == 0
    assert report.skipped_days == 2
    for value in (
        report.mean_modelled_wetness,
        report.mean_observed_wetness,
        report.mean_bias,
        report.same_direction_step_fraction,
    ):
        assert isinstance(value, Missing)
        assert value.reason == "MISSING_INPUT"
        assert "%" in (value.detail or "")


def test_partial_coverage_skips_uncovered_days_and_reports_paired_overlap():
    storage = {
        dt.date(2020, 1, 1): 10.0,
        dt.date(2020, 1, 2): 20.0,
        dt.date(2020, 1, 3): 40.0,
        dt.date(2020, 1, 4): 60.0,
    }
    climate = _climate([_wetness_series(dt.date(2020, 1, 3), [0.3, 0.5])])
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.paired_days == 2
    assert report.skipped_days == 2
    assert report.mean_modelled_wetness == pytest.approx(0.5)
    assert report.mean_observed_wetness == pytest.approx(0.4)
    assert report.mean_bias == pytest.approx(0.1)
    assert report.same_direction_step_fraction == pytest.approx(1.0)


def test_disjoint_coverage_returns_no_coverage_on_all_metrics():
    storage = {dt.date(2020, 1, 1): 40.0, dt.date(2020, 1, 2): 50.0}
    climate = _climate([_wetness_series(dt.date(2020, 2, 1), [0.4, 0.5])])
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.paired_days == 0
    assert report.skipped_days == 4
    for value in (
        report.mean_modelled_wetness,
        report.mean_observed_wetness,
        report.mean_bias,
        report.same_direction_step_fraction,
    ):
        assert isinstance(value, Missing)
        assert value.reason == "NO_COVERAGE"


def test_empty_inputs_return_no_coverage():
    report = build_h5_contrast_report(
        {}, _climate([_wetness_series(dt.date(2020, 1, 1), [0.4])]), capacity_mm=100.0
    )
    assert report.paired_days == 0
    assert report.skipped_days == 1
    assert isinstance(report.mean_modelled_wetness, Missing)
    assert report.mean_modelled_wetness.reason == "NO_COVERAGE"

    empty_pairing = WetnessPairing(days=(), series_missing=None)
    empty_report = contrast_report_from_pairing(empty_pairing)
    assert empty_report.paired_days == 0
    assert empty_report.skipped_days == 0
    assert isinstance(empty_report.mean_modelled_wetness, Missing)
    assert empty_report.mean_modelled_wetness.reason == "NO_COVERAGE"


def test_out_of_range_observed_wetness_is_skipped_or_not_computable():
    start = dt.date(2020, 9, 1)
    storage = {
        dt.date(2020, 9, 1): 20.0,
        dt.date(2020, 9, 2): 50.0,
        dt.date(2020, 9, 3): 80.0,
    }
    climate = _climate([_wetness_series(start, [0.2, 1.2, 0.6])])
    report = build_h5_contrast_report(
        storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert report.paired_days == 2
    assert report.skipped_days == 1
    assert report.mean_modelled_wetness == pytest.approx(0.5)
    assert report.mean_observed_wetness == pytest.approx(0.4)
    assert isinstance(report.same_direction_step_fraction, Missing)
    assert report.same_direction_step_fraction.reason == "NOT_COMPUTABLE"

    all_bad = _climate([_wetness_series(start, [-0.1, 1.1, 2.0])])
    bad_report = build_h5_contrast_report(
        storage, all_bad, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert bad_report.paired_days == 0
    assert bad_report.skipped_days == 3
    assert isinstance(bad_report.mean_observed_wetness, Missing)
    assert bad_report.mean_observed_wetness.reason == "NOT_COMPUTABLE"


@pytest.mark.parametrize("bad_capacity", [0.0, -25.0, math.nan])
def test_zero_or_invalid_capacity_guard_returns_not_computable(bad_capacity):
    start = dt.date(2020, 10, 1)
    storage = {start: 20.0, start + dt.timedelta(days=1): 40.0}
    climate = _climate([_wetness_series(start, [0.2, 0.4])])
    report = build_h5_contrast_report(storage, climate, capacity_mm=bad_capacity)
    assert report.paired_days == 0
    assert report.skipped_days == 2
    for value in (
        report.mean_modelled_wetness,
        report.mean_observed_wetness,
        report.mean_bias,
        report.same_direction_step_fraction,
    ):
        assert isinstance(value, Missing)
        assert value.reason == "NOT_COMPUTABLE"


def test_missing_capacity_and_all_missing_overlap_return_missing_input():
    start = dt.date(2020, 10, 1)
    storage = {start: 20.0, start + dt.timedelta(days=1): 40.0}
    climate = _climate([_wetness_series(start, [0.2, 0.4])])
    cap_report = build_h5_contrast_report(
        storage, climate, capacity_mm=Missing(reason="NOT_DECLARED")
    )
    assert cap_report.paired_days == 0
    assert isinstance(cap_report.mean_modelled_wetness, Missing)
    assert cap_report.mean_modelled_wetness.reason == "MISSING_INPUT"

    all_missing_climate = _climate(
        [
            _wetness_series(
                start,
                [
                    InputsMissing(reason="NO_COVERAGE"),
                    InputsMissing(reason="NO_COVERAGE"),
                ],
            )
        ]
    )
    overlap_report = build_h5_contrast_report(
        storage, all_missing_climate, capacity_mm=PLACEHOLDER_CAPACITY_MM
    )
    assert overlap_report.paired_days == 0
    assert overlap_report.skipped_days == 2
    assert isinstance(overlap_report.mean_observed_wetness, Missing)
    assert overlap_report.mean_observed_wetness.reason == "MISSING_INPUT"


# --- G1 immutability & G5 TypeError checks -----------------------------------


def test_g1_does_not_mutate_inputs_and_g5_type_errors():
    start = dt.date(2020, 11, 1)
    storage = {start: 30.0, start + dt.timedelta(days=1): 50.0}
    climate = _climate([_wetness_series(start, [0.3, 0.5])])
    storage_before = copy.deepcopy(storage)
    climate_before = copy.deepcopy(climate)

    _ = build_h5_contrast_report(storage, climate, capacity_mm=PLACEHOLDER_CAPACITY_MM)
    assert storage == storage_before
    assert climate == climate_before

    with pytest.raises(TypeError):
        contrast_report_from_pairing("not-a-pairing")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        contrast_report_from_pairing(
            WetnessPairing(days=("bad",), series_missing=None)  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        build_h5_contrast_report(storage, "not-climate", capacity_mm=100.0)  # type: ignore[arg-type]

    # Unsorted PairedWetnessDay input is still ordered by date cleanly.
    unsorted = WetnessPairing(
        days=(
            PairedWetnessDay(dt.date(2020, 11, 2), 0.5, 0.6),
            PairedWetnessDay(dt.date(2020, 11, 1), 0.3, 0.4),
        ),
        series_missing=None,
    )
    assert contrast_report_from_pairing(
        unsorted
    ).same_direction_step_fraction == pytest.approx(1.0)


# --- AST check: no thresholds, no tolerance, no pass/fail, pure G1 -----------


def test_h5_module_has_no_thresholds_pass_fail_or_io_ast():
    source = Path(h5_soil_moisture.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
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
        "engine",
        "math",
        "statistics",
        "typing",
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
    # Only 0 and 1 (counters, sign helper, timedelta(days=1)); zero thresholds.
    assert numbers <= {0, 1}
    code_identifiers = {
        *(node.id for node in ast.walk(tree) if isinstance(node, ast.Name)),
        *(node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)),
        *(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        ),
    }
    forbidden_words = ("passed", "verdict", "tolerance", "threshold")
    assert not any(
        word in ident.lower() for ident in code_identifiers for word in forbidden_words
    )
