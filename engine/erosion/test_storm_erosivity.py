"""Tests for ``engine/erosion/storm_erosivity.py``.

Covers sub-hourly storm event separation, Brown-Foster style unit kinetic
energy and ``EI30`` calculation, optional multiplicative climatology anchoring,
zero hardcoded domain defaults (AST hygiene), strict ``Missing`` propagation on
``None`` intervals and continuity gaps (C3.1, C3.3, G4), ``uruguay_calibrated``
governance (``EXPLORATORY_UNVALIDATED`` and refusal of
``official_uruguay_calibrated`` / ``EROSION_NORMATIVA``), G1 purity/determinism,
and G5 strict ``TypeError`` / ``ValueError`` checks.

Every constant, timestamp, and precipitation sequence in this file is
synthetic ``PLACEHOLDER`` test data chosen for exact arithmetic verification.
"""

from __future__ import annotations

import ast
import builtins
import copy
import dataclasses
import datetime as dt
import inspect
import math
import os
import socket
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion import storm_erosivity
from engine.erosion.storm_erosivity import (
    CALIBRATION_LABEL_EXPLORATORY,
    CALIBRATION_LABEL_OFFICIAL,
    EI30_UNIT,
    METHOD_STATUS_CALIBRATED,
    METHOD_STATUS_EXPLORATORY,
    PROVENANCE_DERIVED,
    StormErosivityConfig,
    StormErosivitySummary,
    StormEventErosivity,
    StormInterval,
    anchor_erosivity,
    compute_storm_erosivity,
    resolve_erosivity_label,
    unit_kinetic_energy,
)

# Synthetic PLACEHOLDER configuration values (never real calibrated science constants).
PLACEHOLDER_STEP_MINUTES = 30
PLACEHOLDER_DRY_GAP_INTERVALS = 2
PLACEHOLDER_MIN_DEPTH_MM = 10.0
PLACEHOLDER_KE_E_MAX = 0.25
PLACEHOLDER_KE_A = 0.5
PLACEHOLDER_KE_B = 0.04
PLACEHOLDER_ANCHOR_FACTOR = 1.25
PLACEHOLDER_SOURCE = "PLACEHOLDER: synthetic climatology anchor source"

T0 = dt.datetime(2024, 1, 1, 0, 0, tzinfo=dt.UTC)


def _config(
    *,
    step_minutes: int = PLACEHOLDER_STEP_MINUTES,
    min_dry_gap_intervals: int = PLACEHOLDER_DRY_GAP_INTERVALS,
    min_event_depth_mm: float = PLACEHOLDER_MIN_DEPTH_MM,
    ke_e_max: float = PLACEHOLDER_KE_E_MAX,
    ke_a: float = PLACEHOLDER_KE_A,
    ke_b: float = PLACEHOLDER_KE_B,
    ke_c: float | None = None,
    official_climatology_anchor_factor: float
    | ResultMissing
    | InputMissing
    | None = None,
    uruguay_calibrated: bool = False,
    bias_correction_source: str | None = None,
) -> StormErosivityConfig:
    return StormErosivityConfig(
        step_minutes=step_minutes,
        min_dry_gap_intervals=min_dry_gap_intervals,
        min_event_depth_mm=min_event_depth_mm,
        ke_e_max=ke_e_max,
        ke_a=ke_a,
        ke_b=ke_b,
        ke_c=ke_c,
        official_climatology_anchor_factor=official_climatology_anchor_factor,
        uruguay_calibrated=uruguay_calibrated,
        bias_correction_source=bias_correction_source,
    )


def _series(
    values: list[
        float | None | tuple[float | None, ResultMissing | InputMissing | None]
    ],
    *,
    start: dt.datetime = T0,
    step_minutes: int = PLACEHOLDER_STEP_MINUTES,
) -> list[StormInterval]:
    step = dt.timedelta(minutes=step_minutes)
    out: list[StormInterval] = []
    for idx, entry in enumerate(values):
        ts = start + idx * step
        if isinstance(entry, tuple):
            val, miss = entry
            out.append(StormInterval(timestamp=ts, precipitation_mm=val, missing=miss))
        else:
            out.append(StormInterval(timestamp=ts, precipitation_mm=entry))
    return out


# =============================================================================
# Configuration discipline: zero defaults, zero magic numbers
# =============================================================================


def test_config_and_entrypoints_have_no_hardcoded_domain_defaults():
    """Every StormErosivityConfig field and function config arg has no default."""
    for field in dataclasses.fields(StormErosivityConfig):
        assert field.default is dataclasses.MISSING, field.name
        assert field.default_factory is dataclasses.MISSING, field.name

    with pytest.raises(TypeError):
        StormErosivityConfig()  # type: ignore[call-arg]

    for fn in (compute_storm_erosivity, unit_kinetic_energy, anchor_erosivity):
        sig = inspect.signature(fn)
        cfg_param = sig.parameters["config"]
        assert cfg_param.kind is inspect.Parameter.KEYWORD_ONLY
        assert cfg_param.default is inspect.Parameter.empty


def test_module_contains_no_domain_magic_numbers():
    """AST scan permits only 0, 1, and definitional 30-min I30 window constant."""
    tree = ast.parse(Path(storm_erosivity.__file__).read_text(encoding="utf-8"))
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1, 30}, numbers


# =============================================================================
# Core EI30 physics & storm separation by hand
# =============================================================================


def test_single_storm_by_hand_matches_ke_energy_i30_and_anchoring():
    """Exact by-hand verification of unit KE, E, I30, EI30, and anchoring."""
    cfg = _config(
        official_climatology_anchor_factor=PLACEHOLDER_ANCHOR_FACTOR,
        bias_correction_source=PLACEHOLDER_SOURCE,
    )
    intervals = _series([0.0, 10.0, 20.0, 0.0, 0.0])
    summary = compute_storm_erosivity(intervals, config=cfg)

    assert isinstance(summary, StormErosivitySummary)
    assert summary.ei30_unit == EI30_UNIT
    assert summary.method_status == METHOD_STATUS_EXPLORATORY
    assert summary.calibration_label == CALIBRATION_LABEL_EXPLORATORY
    assert summary.uruguay_calibrated is False
    assert summary.provenance == PROVENANCE_DERIVED
    assert summary.interval_count == 5
    assert summary.missing_interval_count == 0
    assert summary.continuity_gaps == ()
    assert len(summary.events) == 1

    ev = summary.events[0]
    assert isinstance(ev, StormEventErosivity)
    assert ev.event_index == 1
    assert ev.start_time == T0 + dt.timedelta(minutes=30)
    assert ev.end_time == T0 + dt.timedelta(minutes=60)
    assert ev.interval_count == 2
    assert ev.total_depth_mm == pytest.approx(30.0)
    assert ev.provenance == PROVENANCE_DERIVED
    assert ev.has_missing_intervals is False
    assert ev.broken_by_continuity_gap is False

    # 30-min step: I_1 = 20 mm/h, I_2 = 40 mm/h, I30 = 40 mm/h.
    e1 = PLACEHOLDER_KE_E_MAX * (
        1.0 - PLACEHOLDER_KE_A * math.exp(-PLACEHOLDER_KE_B * 20.0)
    )
    e2 = PLACEHOLDER_KE_E_MAX * (
        1.0 - PLACEHOLDER_KE_A * math.exp(-PLACEHOLDER_KE_B * 40.0)
    )
    expected_energy = e1 * 10.0 + e2 * 20.0
    expected_i30 = 40.0
    expected_ei30 = expected_energy * expected_i30
    expected_anchored = expected_ei30 * PLACEHOLDER_ANCHOR_FACTOR

    assert unit_kinetic_energy(20.0, config=cfg) == pytest.approx(e1)
    assert unit_kinetic_energy(40.0, config=cfg) == pytest.approx(e2)
    assert ev.total_energy_mj_ha == pytest.approx(expected_energy)
    assert ev.i30_mm_h == pytest.approx(expected_i30)
    assert ev.ei30 == pytest.approx(expected_ei30)
    assert ev.anchored_ei30 == pytest.approx(expected_anchored)
    assert summary.total_ei30 == pytest.approx(expected_ei30)
    assert summary.anchored_total_ei30 == pytest.approx(expected_anchored)


def test_ke_c_additive_parameter_and_unanchored_mode():
    """ke_c shifts unit KE linearly; None anchor leaves anchored fields as None."""
    cfg_base = _config(ke_c=None, official_climatology_anchor_factor=None)
    cfg_zero = _config(ke_c=0.0, official_climatology_anchor_factor=None)
    cfg_shifted = _config(ke_c=0.03, official_climatology_anchor_factor=None)

    assert unit_kinetic_energy(25.0, config=cfg_base) == pytest.approx(
        unit_kinetic_energy(25.0, config=cfg_zero)
    )
    assert unit_kinetic_energy(25.0, config=cfg_shifted) == pytest.approx(
        unit_kinetic_energy(25.0, config=cfg_base) + 0.03
    )

    summary = compute_storm_erosivity(_series([12.0, 0.0, 0.0]), config=cfg_base)
    assert len(summary.events) == 1
    assert summary.events[0].anchored_ei30 is None
    assert summary.anchored_total_ei30 is None


def test_storm_separation_merges_short_dry_pause_and_separates_full_gap():
    """A dry pause shorter than min_dry_gap_intervals stays in one storm; >= separates."""
    cfg = _config(min_dry_gap_intervals=2, min_event_depth_mm=10.0)
    # Storm 1: [10.0, 0.0, 10.0] (only 1 dry interval inside -> 1 storm, depth 20)
    # Gap: [0.0, 0.0] (2 dry intervals -> closes Storm 1)
    # Sub-threshold rain: [4.0, 0.0, 0.0] (depth 4 < 10 -> ignored)
    # Storm 2: [15.0] (at end of series, depth 15 >= 10 -> Storm 2)
    intervals = _series([10.0, 0.0, 10.0, 0.0, 0.0, 4.0, 0.0, 0.0, 15.0])
    summary = compute_storm_erosivity(intervals, config=cfg)

    assert len(summary.events) == 2
    ev1, ev2 = summary.events
    assert ev1.event_index == 1
    assert ev1.interval_count == 3
    assert ev1.total_depth_mm == pytest.approx(20.0)
    assert ev1.i30_mm_h == pytest.approx(20.0)

    assert ev2.event_index == 2
    assert ev2.interval_count == 1
    assert ev2.total_depth_mm == pytest.approx(15.0)
    assert ev2.i30_mm_h == pytest.approx(30.0)

    assert isinstance(ev1.ei30, float) and isinstance(ev2.ei30, float)
    assert summary.total_ei30 == pytest.approx(ev1.ei30 + ev2.ei30)


def test_min_event_depth_boundary_inclusive_and_dry_series_is_zero():
    """Exact min_event_depth_mm qualifies; dry/sub-threshold series sums to 0.0."""
    cfg = _config(min_event_depth_mm=10.0)
    exact = compute_storm_erosivity(_series([10.0, 0.0, 0.0]), config=cfg)
    assert len(exact.events) == 1
    assert isinstance(exact.total_ei30, float) and exact.total_ei30 > 0.0

    sub = compute_storm_erosivity(_series([9.99, 0.0, 0.0]), config=cfg)
    assert sub.events == ()
    assert sub.total_ei30 == 0.0
    assert sub.provenance == PROVENANCE_DERIVED

    dry = compute_storm_erosivity(_series([0.0, 0.0, 0.0]), config=cfg)
    assert dry.events == ()
    assert dry.total_ei30 == 0.0


def test_sub_30min_step_computes_rolling_30min_i30():
    """15-min intervals sum 2 consecutive steps for I30; single 15-min storm pads dry."""
    cfg = _config(step_minutes=15, min_dry_gap_intervals=2, min_event_depth_mm=5.0)
    # 15-min storm: 4.0, 6.0, 2.0 mm -> max 30-min depth = 10.0 mm -> I30 = 20.0 mm/h.
    intervals = _series([4.0, 6.0, 2.0, 0.0, 0.0], step_minutes=15)
    summary = compute_storm_erosivity(intervals, config=cfg)
    assert len(summary.events) == 1
    assert summary.events[0].i30_mm_h == pytest.approx(20.0)

    # Single 15-min pulse of 6.0 mm -> 6.0 mm in 30-min window -> I30 = 12.0 mm/h.
    short_summary = compute_storm_erosivity(
        _series([6.0, 0.0, 0.0], step_minutes=15), config=cfg
    )
    assert len(short_summary.events) == 1
    assert short_summary.events[0].i30_mm_h == pytest.approx(12.0)


def test_step_not_dividing_30min_returns_not_computable_i30():
    """60-min step cannot resolve 30-min I30 without disaggregation assumption."""
    cfg = _config(step_minutes=60, min_dry_gap_intervals=1, min_event_depth_mm=5.0)
    summary = compute_storm_erosivity(_series([20.0, 0.0], step_minutes=60), config=cfg)
    assert len(summary.events) == 1
    ev = summary.events[0]
    assert isinstance(ev.i30_mm_h, ResultMissing)
    assert ev.i30_mm_h.reason == "NOT_COMPUTABLE"
    assert isinstance(ev.ei30, ResultMissing)
    assert ev.ei30.reason == "NOT_COMPUTABLE"
    assert ev.provenance is None
    assert isinstance(summary.total_ei30, ResultMissing)
    assert summary.total_ei30.reason == "NOT_COMPUTABLE"


# =============================================================================
# Missing precipitation & continuity gap propagation (G4 / C3.1 / C3.3)
# =============================================================================


def test_empty_intervals_returns_no_coverage():
    """Empty interval sequence gives NO_COVERAGE and provenance=None."""
    summary = compute_storm_erosivity([], config=_config())
    assert summary.events == ()
    assert isinstance(summary.total_ei30, ResultMissing)
    assert summary.total_ei30.reason == "NO_COVERAGE"
    assert summary.provenance is None
    assert summary.interval_count == 0


def test_missing_interval_inside_active_storm_propagates_missing_input():
    """None inside an active storm propagates MISSING_INPUT (never filled with 0.0)."""
    cfg = _config(
        min_dry_gap_intervals=2,
        min_event_depth_mm=15.0,
        official_climatology_anchor_factor=PLACEHOLDER_ANCHOR_FACTOR,
        bias_correction_source=PLACEHOLDER_SOURCE,
    )
    # Observed depth is only 10.0 < 15.0, but second interval is None -> cannot drop!
    intervals = _series(
        [
            10.0,
            (None, InputMissing(reason="SOURCE_UNAVAILABLE", detail="gauge offline")),
            0.0,
            0.0,
        ]
    )
    summary = compute_storm_erosivity(intervals, config=cfg)

    assert len(summary.events) == 1
    ev = summary.events[0]
    assert ev.has_missing_intervals is True
    assert ev.provenance is None
    for field_val in (
        ev.total_depth_mm,
        ev.total_energy_mj_ha,
        ev.i30_mm_h,
        ev.ei30,
        ev.anchored_ei30,
    ):
        assert isinstance(field_val, ResultMissing)
        assert field_val.reason == "MISSING_INPUT"
        assert "gauge offline" in (field_val.detail or "")

    assert summary.missing_interval_count == 1
    assert isinstance(summary.total_ei30, ResultMissing)
    assert summary.total_ei30.reason == "MISSING_INPUT"
    assert isinstance(summary.anchored_total_ei30, ResultMissing)
    assert summary.anchored_total_ei30.reason == "MISSING_INPUT"
    assert summary.provenance is None


def test_missing_interval_during_incomplete_trailing_dry_gap_corrupts_storm():
    """A None before min_dry_gap_intervals completes still affects the active storm."""
    cfg = _config(min_dry_gap_intervals=3, min_event_depth_mm=10.0)
    # Only 1 dry interval after wet pulse when None arrives -> storm still active.
    intervals = _series([20.0, 0.0, None, 0.0, 0.0, 0.0, 15.0, 0.0, 0.0, 0.0])
    summary = compute_storm_erosivity(intervals, config=cfg)

    assert len(summary.events) == 2
    assert summary.events[0].has_missing_intervals is True
    assert isinstance(summary.events[0].ei30, ResultMissing)
    assert summary.events[0].ei30.reason == "MISSING_INPUT"
    # Second storm after 3 observed dry intervals is cleanly computed.
    assert summary.events[1].has_missing_intervals is False
    assert isinstance(summary.events[1].ei30, float)
    # Summary total remains MISSING_INPUT because the series had a missing interval.
    assert isinstance(summary.total_ei30, ResultMissing)
    assert summary.total_ei30.reason == "MISSING_INPUT"


def test_continuity_gap_breaks_active_storm_and_records_gap():
    """A timestamp jump > step_minutes never merges storms and flags MISSING_INPUT."""
    cfg = _config(step_minutes=30, min_dry_gap_intervals=4, min_event_depth_mm=10.0)
    step = dt.timedelta(minutes=30)
    intervals = [
        StormInterval(timestamp=T0, precipitation_mm=15.0),
        StormInterval(timestamp=T0 + step, precipitation_mm=15.0),
        # Skip T0 + 2*step (1-hour jump -> continuity gap!)
        StormInterval(timestamp=T0 + 3 * step, precipitation_mm=20.0),
        StormInterval(timestamp=T0 + 4 * step, precipitation_mm=0.0),
        StormInterval(timestamp=T0 + 5 * step, precipitation_mm=0.0),
        StormInterval(timestamp=T0 + 6 * step, precipitation_mm=0.0),
        StormInterval(timestamp=T0 + 7 * step, precipitation_mm=0.0),
    ]
    summary = compute_storm_erosivity(intervals, config=cfg)

    assert summary.continuity_gaps == ((T0 + step, T0 + 3 * step),)
    assert len(summary.events) == 2
    broken, clean = summary.events
    assert broken.broken_by_continuity_gap is True
    assert isinstance(broken.ei30, ResultMissing)
    assert broken.ei30.reason == "MISSING_INPUT"
    assert broken.provenance is None

    assert clean.broken_by_continuity_gap is False
    assert isinstance(clean.ei30, float)
    assert isinstance(summary.total_ei30, ResultMissing)
    assert summary.total_ei30.reason == "MISSING_INPUT"


def test_negative_or_non_finite_precipitation_is_not_clipped():
    """Negative or NaN/inf precipitation produces NOT_COMPUTABLE, never 0.0."""
    cfg = _config(min_event_depth_mm=5.0)
    for bad in (-1.5, math.nan, math.inf):
        summary = compute_storm_erosivity(_series([10.0, bad, 0.0, 0.0]), config=cfg)
        assert len(summary.events) == 1
        assert isinstance(summary.events[0].ei30, ResultMissing)
        assert summary.events[0].ei30.reason == "NOT_COMPUTABLE"
        assert isinstance(summary.total_ei30, ResultMissing)
        assert summary.total_ei30.reason == "NOT_COMPUTABLE"


def test_missing_anchor_factor_propagates_to_anchored_outputs_only():
    """Missing anchor factor leaves unanchored EI30 computable and marks anchored Missing."""
    missing_anchor = InputMissing(reason="NOT_DECLARED", detail="anchor pending")
    cfg = _config(official_climatology_anchor_factor=missing_anchor)
    summary = compute_storm_erosivity(_series([15.0, 0.0, 0.0]), config=cfg)

    assert isinstance(summary.events[0].ei30, float)
    assert isinstance(summary.events[0].anchored_ei30, ResultMissing)
    assert summary.events[0].anchored_ei30.reason == "MISSING_INPUT"
    assert isinstance(summary.total_ei30, float)
    assert isinstance(summary.anchored_total_ei30, ResultMissing)
    assert summary.anchored_total_ei30.reason == "MISSING_INPUT"


# =============================================================================
# Uruguay calibration governance & label refusal
# =============================================================================


def test_uncalibrated_output_carries_exploratory_status_and_refuses_official_labels():
    """uruguay_calibrated=False enforces EXPLORATORY_UNVALIDATED and rejects official labels."""
    cfg = _config(uruguay_calibrated=False, bias_correction_source=None)
    summary = compute_storm_erosivity(_series([15.0, 0.0, 0.0]), config=cfg)

    assert summary.method_status == METHOD_STATUS_EXPLORATORY
    assert summary.calibration_label == CALIBRATION_LABEL_EXPLORATORY
    assert summary.events[0].method_status == METHOD_STATUS_EXPLORATORY

    for forbidden in (
        "official_uruguay_calibrated",
        "EROSION_NORMATIVA",
        "erosion_normativa",
    ):
        with pytest.raises(ValueError, match="uruguay_calibrated is False"):
            resolve_erosivity_label(summary, requested_label=forbidden)

        with pytest.raises(ValueError, match="uruguay_calibrated=False"):
            _config(uruguay_calibrated=False, bias_correction_source=forbidden)

    assert (
        resolve_erosivity_label(summary, requested_label="exploratory_unvalidated")
        == "exploratory_unvalidated"
    )


def test_calibrated_mode_requires_source_and_permits_official_labels():
    """uruguay_calibrated=True requires bias_correction_source and emits calibrated status."""
    with pytest.raises(ValueError, match="bias_correction_source"):
        _config(uruguay_calibrated=True, bias_correction_source=None)

    cfg = _config(
        uruguay_calibrated=True,
        official_climatology_anchor_factor=PLACEHOLDER_ANCHOR_FACTOR,
        bias_correction_source=PLACEHOLDER_SOURCE,
    )
    summary = compute_storm_erosivity(_series([15.0, 0.0, 0.0]), config=cfg)
    assert summary.method_status == METHOD_STATUS_CALIBRATED
    assert summary.calibration_label == CALIBRATION_LABEL_OFFICIAL
    assert (
        resolve_erosivity_label(summary, requested_label="official_uruguay_calibrated")
        == "official_uruguay_calibrated"
    )
    assert (
        resolve_erosivity_label(summary, requested_label="EROSION_NORMATIVA")
        == "EROSION_NORMATIVA"
    )


# =============================================================================
# G1 purity, immutability, determinism, and G5 strict errors
# =============================================================================


def test_g1_purity_immutability_and_determinism(monkeypatch: pytest.MonkeyPatch):
    """Pure execution: no file/network/env/clock calls, no mutation, deterministic."""

    def _forbid(what: str):
        def _raiser(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError(f"G1 violation: {what} called")

        return _raiser

    cfg = _config(
        official_climatology_anchor_factor=PLACEHOLDER_ANCHOR_FACTOR,
        bias_correction_source=PLACEHOLDER_SOURCE,
    )
    intervals = _series([0.0, 12.0, 18.0, 0.0, 0.0, 14.0])
    snapshot = copy.deepcopy(intervals)

    with monkeypatch.context() as mp:
        mp.setattr(builtins, "open", _forbid("builtins.open"))
        mp.setattr(Path, "open", _forbid("Path.open"))
        mp.setattr(Path, "read_text", _forbid("Path.read_text"))
        mp.setattr(socket, "socket", _forbid("socket.socket"))
        mp.setattr(os, "getenv", _forbid("os.getenv"))
        mp.setattr(time, "time", _forbid("time.time"))
        mp.setattr(time, "monotonic", _forbid("time.monotonic"))
        res1 = compute_storm_erosivity(intervals, config=cfg)
        res2 = compute_storm_erosivity(intervals, config=cfg)

    assert intervals == snapshot
    assert res1 == res2

    tree = ast.parse(Path(storm_erosivity.__file__).read_text(encoding="utf-8"))
    forbidden_names = {"today", "utcnow", "now", "environ", "getenv", "open"}
    used_names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Attribute, ast.Name))
    }
    assert used_names.isdisjoint(forbidden_names)

    with pytest.raises(FrozenInstanceError):
        cfg.ke_a = 0.1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        res1.uruguay_calibrated = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"step_minutes": True},
        {"step_minutes": 30.0},
        {"min_dry_gap_intervals": False},
        {"min_event_depth_mm": True},
        {"min_event_depth_mm": "10"},
        {"ke_e_max": None},
        {"ke_a": "0.5"},
        {"ke_b": False},
        {"ke_c": True},
        {"official_climatology_anchor_factor": True},
        {"official_climatology_anchor_factor": "1.2"},
        {"uruguay_calibrated": 1},
        {"uruguay_calibrated": "false"},
        {"bias_correction_source": 123},
    ],
)
def test_g5_config_strict_type_errors(kwargs: dict[str, Any]):
    with pytest.raises(TypeError):
        _config(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"step_minutes": 0},
        {"step_minutes": -30},
        {"min_dry_gap_intervals": 0},
        {"min_event_depth_mm": -0.1},
        {"min_event_depth_mm": math.nan},
        {"ke_e_max": -1.0},
        {"ke_a": -0.1},
        {"ke_b": -0.1},
        {"ke_c": math.inf},
        {
            "official_climatology_anchor_factor": 0.0,
            "bias_correction_source": PLACEHOLDER_SOURCE,
        },
        {
            "official_climatology_anchor_factor": -1.0,
            "bias_correction_source": PLACEHOLDER_SOURCE,
        },
        {"official_climatology_anchor_factor": 1.2, "bias_correction_source": None},
        {"bias_correction_source": "   "},
    ],
)
def test_g5_config_value_errors(kwargs: dict[str, Any]):
    with pytest.raises(ValueError):
        _config(**kwargs)


def test_g5_interval_and_series_type_and_value_errors():
    cfg = _config()

    with pytest.raises(TypeError):
        StormInterval(timestamp="2024-01-01T00:00:00Z", precipitation_mm=1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        StormInterval(timestamp=T0, precipitation_mm=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        StormInterval(timestamp=T0, precipitation_mm=None, missing="bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        StormInterval(
            timestamp=T0,
            precipitation_mm=1.0,
            missing=ResultMissing(reason="MISSING_INPUT", detail="conflict"),
        )

    for bad_intervals in ("bad", 123, None, [1.0]):
        with pytest.raises(TypeError):
            compute_storm_erosivity(bad_intervals, config=cfg)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        compute_storm_erosivity([], config="bad")  # type: ignore[arg-type]

    # Mixed timezone-aware and naive timestamps.
    with pytest.raises(ValueError, match="naive"):
        compute_storm_erosivity(
            [
                StormInterval(timestamp=T0, precipitation_mm=1.0),
                StormInterval(
                    timestamp=dt.datetime(2024, 1, 1, 0, 30), precipitation_mm=1.0
                ),
            ],
            config=cfg,
        )

    # Mixed time zones.
    tz_minus3 = dt.timezone(dt.timedelta(hours=-3))
    with pytest.raises(ValueError, match="time zones"):
        compute_storm_erosivity(
            [
                StormInterval(timestamp=T0, precipitation_mm=1.0),
                StormInterval(
                    timestamp=dt.datetime(2024, 1, 1, 0, 30, tzinfo=tz_minus3),
                    precipitation_mm=1.0,
                ),
            ],
            config=cfg,
        )

    # Duplicate or non-increasing timestamps.
    with pytest.raises(ValueError, match="strictly increasing"):
        compute_storm_erosivity(
            [
                StormInterval(timestamp=T0, precipitation_mm=1.0),
                StormInterval(timestamp=T0, precipitation_mm=1.0),
            ],
            config=cfg,
        )

    # Sub-step spacing smaller than step_minutes.
    with pytest.raises(ValueError, match="smaller than"):
        compute_storm_erosivity(
            [
                StormInterval(timestamp=T0, precipitation_mm=1.0),
                StormInterval(
                    timestamp=T0 + dt.timedelta(minutes=15), precipitation_mm=1.0
                ),
            ],
            config=cfg,
        )

    with pytest.raises(TypeError):
        unit_kinetic_energy(True, config=cfg)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        unit_kinetic_energy(-1.0, config=cfg)
    with pytest.raises(TypeError):
        resolve_erosivity_label("bad", requested_label="x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        resolve_erosivity_label(
            compute_storm_erosivity([], config=cfg), requested_label="  "
        )
