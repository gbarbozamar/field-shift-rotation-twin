"""Tests for Rev13 Carbon Model Trajectory Comparator, Dependence Guard & Continuity Checker.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
Uses synthetic placeholder numbers only (no real scientific parameters or thresholds).
"""

from __future__ import annotations

import ast
import copy
import json
import math
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from contracts.carbon_balance import CarbonBalance
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import YearMonth
from contracts.results.models import TREND_COMPUTATIONS
from contracts.results.models import Missing as ResultMissing
from engine.amg.model_comparison import (
    DUPLICATE_C_INPUT_REASON,
    MISSING_PERIOD_REASON,
    STOCK_CONTINUITY_BREAK_REASON,
    STRUCTURAL_DEPENDENCY_VIOLATION,
    TRAJECTORY_MODEL_IDS,
    CarbonInputRecord,
    CarbonTrajectorySummary,
    HomologyProtocol,
    StockPeriod,
    check_stock_continuity,
    compare_carbon_trajectories,
    summarize_trajectory,
    validate_ensemble_weights,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_BALANCE_PATH = (
    REPO_ROOT
    / "contracts"
    / "carbon_balance"
    / "examples"
    / "PLACEHOLDER_carbon_balance.json"
)

_SOURCE = "PLACEHOLDER: synthetic trajectory fixture"
_NO_RANGE = {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER: no uncertainty range"}
_UNIT = "t C ha-1"
_TREND_UNIT = "t C ha-1 yr-1"


def _ym(year: int, month: int) -> YearMonth:
    return YearMonth(year=year, month=month)


def _matched_homology() -> HomologyProtocol:
    return HomologyProtocol(
        depth_cm=20.0,
        bulk_density_basis="equivalent_soil_mass",
        boundary_condition="closed_topsoil_0_20cm",
        initialization_protocol="common_total_soc_model_spinup",
    )


def _make_annual_balance(
    *,
    carbon_model: str = "amg",
    variant: str = "amg_a",
    initial: float | None = 40.0,
    steps_values: tuple[float | None, ...] = (41.0, 42.0),
    c_inputs: tuple[float | None, ...] = (2.2, 2.2),
    mean_over_cycles_missing: bool = False,
) -> CarbonBalance:
    years = (2021, 2022)[: len(steps_values)]
    initial_dict: dict[str, Any]
    if initial is None:
        initial_dict = {
            "value": None,
            "unit": _UNIT,
            "missing": {
                "reason": "MISSING_INPUT",
                "detail": "PLACEHOLDER: missing soc",
            },
        }
    else:
        initial_dict = {
            "value": initial,
            "unit": _UNIT,
            "provenance": "DERIVED",
            "source": _SOURCE,
            "range_missing": _NO_RANGE,
        }

    step_dicts = []
    flow_dicts = []
    for year, stock_val, cin_val in zip(years, steps_values, c_inputs, strict=True):
        s_item: dict[str, Any] = {
            "start": {"year": year, "month": 1},
            "end": {"year": year, "month": 12},
            "value": stock_val,
        }
        if stock_val is None:
            s_item["missing"] = {
                "reason": "MISSING_INPUT",
                "detail": f"PLACEHOLDER: missing step {year}",
            }
        step_dicts.append(s_item)

        f_item: dict[str, Any] = {
            "start": {"year": year, "month": 1},
            "end": {"year": year, "month": 12},
            "value": cin_val,
        }
        if cin_val is None:
            f_item["missing"] = {
                "reason": "MISSING_INPUT",
                "detail": f"PLACEHOLDER: missing input {year}",
            }
        flow_dicts.append(f_item)

    any_stock_present = any(v is not None for v in steps_values)
    total_header: dict[str, Any] = {
        "quantity": "soil_organic_carbon",
        "unit": _UNIT,
        "initial": initial_dict,
        "steps": step_dicts,
    }
    if any_stock_present:
        total_header.update(
            {
                "provenance": "SIMULATED",
                "source": _SOURCE,
                "range_missing": _NO_RANGE,
            }
        )

    any_flow_present = any(v is not None for v in c_inputs)
    flow_qty = "rothc_carbon_input" if carbon_model == "rothc" else "amg_humified_input"
    flow_header: dict[str, Any] = {
        "quantity": flow_qty,
        "unit": _UNIT,
        "steps": flow_dicts,
    }
    if any_flow_present:
        flow_header.update(
            {
                "provenance": "DERIVED",
                "source": _SOURCE,
                "range_missing": _NO_RANGE,
            }
        )

    trends = []
    for comp in TREND_COMPUTATIONS:
        if comp == "mean_over_cycles" and mean_over_cycles_missing:
            trends.append(
                {
                    "indicator": "soil_carbon_trend",
                    "direction": "higher_is_better",
                    "value": None,
                    "unit": _TREND_UNIT,
                    "carbon_model": carbon_model,
                    "computation": comp,
                    "missing": {
                        "reason": "NOT_APPLICABLE",
                        "detail": "PLACEHOLDER: no cycle boundary",
                    },
                }
            )
        else:
            trend_val = (
                (steps_values[-1] - initial) / len(steps_values)
                if initial is not None and steps_values[-1] is not None
                else None
            )
            if trend_val is None:
                trends.append(
                    {
                        "indicator": "soil_carbon_trend",
                        "direction": "higher_is_better",
                        "value": None,
                        "unit": _TREND_UNIT,
                        "carbon_model": carbon_model,
                        "computation": comp,
                        "missing": {
                            "reason": "MISSING_INPUT",
                            "detail": "PLACEHOLDER: missing stock",
                        },
                    }
                )
            else:
                trends.append(
                    {
                        "indicator": "soil_carbon_trend",
                        "direction": "higher_is_better",
                        "value": trend_val,
                        "unit": _TREND_UNIT,
                        "carbon_model": carbon_model,
                        "computation": comp,
                        "provenance": "SIMULATED",
                        "source": _SOURCE,
                        "range_missing": _NO_RANGE,
                    }
                )

    payload = {
        "contract": "carbon_balance",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "rotation_id": "PLACEHOLDER-rotation",
        "carbon_model": carbon_model,
        "variant": variant,
        "horizon": {
            "start": {"year": years[0], "month": 1},
            "end": {"year": years[-1], "month": 12},
        },
        "soil_depth": {
            "value": 20.0,
            "unit": "cm",
            "provenance": "DECLARED",
            "source": _SOURCE,
            "range_missing": _NO_RANGE,
        },
        "total_stock": total_header,
        "pools": [],
        "flows": [flow_header],
        "soil_carbon_trend": trends,
    }
    return CarbonBalance.model_validate(payload)


def _make_monthly_balance(
    *,
    carbon_model: str = "amg",
    variant: str = "amg_m",
    initial: float = 40.0,
    monthly_end_stocks: tuple[float | None, ...] = (40.1, 40.2, 40.3),
    monthly_c_inputs: tuple[float | None, ...] = (0.0, 0.5, 0.0),
) -> CarbonBalance:
    step_dicts = []
    flow_dicts = []
    for idx, (stock_val, cin_val) in enumerate(
        zip(monthly_end_stocks, monthly_c_inputs, strict=True), start=1
    ):
        year = 2021 + (idx - 1) // 12
        month = ((idx - 1) % 12) + 1
        s_item: dict[str, Any] = {
            "start": {"year": year, "month": month},
            "end": {"year": year, "month": month},
            "value": stock_val,
        }
        if stock_val is None:
            s_item["missing"] = {
                "reason": "NO_COVERAGE",
                "detail": f"PLACEHOLDER: missing {year:04d}-{month:02d}",
            }
        step_dicts.append(s_item)

        f_item: dict[str, Any] = {
            "start": {"year": year, "month": month},
            "end": {"year": year, "month": month},
            "value": cin_val,
        }
        if cin_val is None:
            f_item["missing"] = {
                "reason": "NO_COVERAGE",
                "detail": f"PLACEHOLDER: missing input {year:04d}-{month:02d}",
            }
        flow_dicts.append(f_item)

    last_year = 2021 + (len(monthly_end_stocks) - 1) // 12
    last_month = ((len(monthly_end_stocks) - 1) % 12) + 1
    flow_qty = "rothc_carbon_input" if carbon_model == "rothc" else "amg_humified_input"

    trends = [
        {
            "indicator": "soil_carbon_trend",
            "direction": "higher_is_better",
            "value": (
                (monthly_end_stocks[-1] - initial)
                if monthly_end_stocks[-1] is not None
                else None
            ),
            "unit": _TREND_UNIT,
            "carbon_model": carbon_model,
            "computation": comp,
            **(
                {
                    "provenance": "SIMULATED",
                    "source": _SOURCE,
                    "range_missing": _NO_RANGE,
                }
                if monthly_end_stocks[-1] is not None
                else {
                    "missing": {
                        "reason": "NO_COVERAGE",
                        "detail": "PLACEHOLDER: end missing",
                    }
                }
            ),
        }
        for comp in TREND_COMPUTATIONS
    ]

    payload = {
        "contract": "carbon_balance",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "rotation_id": "PLACEHOLDER-rotation",
        "carbon_model": carbon_model,
        "variant": variant,
        "horizon": {
            "start": {"year": 2021, "month": 1},
            "end": {"year": last_year, "month": last_month},
        },
        "soil_depth": {
            "value": 20.0,
            "unit": "cm",
            "provenance": "DECLARED",
            "source": _SOURCE,
            "range_missing": _NO_RANGE,
        },
        "total_stock": {
            "quantity": "soil_organic_carbon",
            "unit": _UNIT,
            "provenance": "SIMULATED",
            "source": _SOURCE,
            "range_missing": _NO_RANGE,
            "initial": {
                "value": initial,
                "unit": _UNIT,
                "provenance": "DERIVED",
                "source": _SOURCE,
                "range_missing": _NO_RANGE,
            },
            "steps": step_dicts,
        },
        "pools": [],
        "flows": [
            {
                "quantity": flow_qty,
                "unit": _UNIT,
                "provenance": "DERIVED",
                "source": _SOURCE,
                "range_missing": _NO_RANGE,
                "steps": flow_dicts,
            }
        ],
        "soil_carbon_trend": trends,
    }
    return CarbonBalance.model_validate(payload)


# --- Law 1: Side-by-side comparison and default_averaged=False ----------------


def test_default_comparison_returns_all_available_side_by_side_without_averaging() -> (
    None
):
    amg_a = _make_annual_balance(
        carbon_model="amg", variant="amg_a", initial=40.0, steps_values=(41.0, 42.0)
    )
    amg_m = _make_monthly_balance(
        carbon_model="amg",
        variant="amg_m",
        initial=40.0,
        monthly_end_stocks=(40.5, 41.2, 42.4),
    )
    rothc = _make_monthly_balance(
        carbon_model="rothc",
        variant="rothc_26_3",
        initial=40.0,
        monthly_end_stocks=(39.9, 39.8, 39.7),
    )

    result = compare_carbon_trajectories([rothc, amg_a, amg_m])

    assert result.default_averaged is False
    assert result.weighted_ensemble is None
    assert result.ensemble_validation is None
    assert result.available_models == ("amg_a", "amg_m", "rothc")
    assert set(result.separate_trajectories) == {"amg_a", "amg_m", "rothc"}
    assert result.separate_trajectories["amg_a"].end_stock == pytest.approx(42.0)
    assert result.separate_trajectories["amg_m"].end_stock == pytest.approx(42.4)
    assert result.separate_trajectories["rothc"].end_stock == pytest.approx(39.7)
    assert result.missing_models == {}


def test_partial_comparison_preserves_missing_models_as_typed_missing() -> None:
    amg_a = _make_annual_balance(
        carbon_model="amg", variant="amg_a", mean_over_cycles_missing=True
    )

    result = compare_carbon_trajectories({"amg_a": amg_a})

    assert result.default_averaged is False
    assert result.available_models == ("amg_a",)
    assert set(result.missing_models) == {"amg_m", "rothc"}
    assert isinstance(result.missing_models["amg_m"], ResultMissing)
    assert result.missing_models["amg_m"].reason == "NOT_AVAILABLE"
    assert isinstance(result.missing_models["rothc"], ResultMissing)
    assert isinstance(
        result.separate_trajectories["amg_a"].trends["mean_over_cycles"],
        ResultMissing,
    )


def test_accepts_placeholder_contract_example_balance() -> None:
    raw = json.loads(PLACEHOLDER_BALANCE_PATH.read_text(encoding="utf-8"))
    raw["variant"] = "amg_a"
    balance = CarbonBalance.model_validate(raw)

    result = compare_carbon_trajectories([balance])

    assert result.default_averaged is False
    summary = result.separate_trajectories["amg_a"]
    assert summary.initial_stock == pytest.approx(777.7)
    assert summary.end_stock == pytest.approx(799.9)
    assert isinstance(summary.soil_depth_cm, InputMissing)
    assert summary.soil_depth_cm.reason == "NOT_DECLARED"
    assert isinstance(summary.trends["mean_over_cycles"], ResultMissing)


# --- Law 2: Structural dependency & homology guard ---------------------------


@pytest.mark.parametrize(
    "weights",
    [
        {"amg_a": 1 / 3, "amg_m": 1 / 3, "rothc": 1 / 3},
        {"amg_a": 0.5, "amg_m": 0.5},
        {"amg_a": 0.4, "amg_m": 0.2, "rothc": 0.4},
        {"amg_a": 1.0, "amg_m": 1.0, "rothc": 1.0},
    ],
)
def test_refuses_independent_or_equal_amg_a_amg_m_weights_by_default(
    weights: dict[str, float],
) -> None:
    with pytest.raises(ValueError, match=STRUCTURAL_DEPENDENCY_VIOLATION):
        validate_ensemble_weights(weights)


@pytest.mark.parametrize(
    ("dep_handled", "hom_verified", "indep_proven"),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
        (False, False, True),
        (False, True, False),
        (True, False, False),
    ],
)
def test_refuses_amg_a_and_amg_m_unless_all_three_rev13_conditions_hold(
    dep_handled: bool, hom_verified: bool, indep_proven: bool
) -> None:
    protocols = {
        "amg_a": _matched_homology(),
        "amg_m": _matched_homology(),
        "rothc": _matched_homology(),
    }
    with pytest.raises(ValueError, match=STRUCTURAL_DEPENDENCY_VIOLATION):
        validate_ensemble_weights(
            {"amg_a": 0.25, "amg_m": 0.25, "rothc": 0.5},
            amg_dependence_handled=dep_handled,
            homology_verified=hom_verified,
            independent_validation_proven=indep_proven,
            homology_protocols=protocols,
        )


@pytest.mark.parametrize(
    ("field_name", "override_value"),
    [
        ("depth_cm", 30.0),
        ("bulk_density_basis", "fixed_depth"),
        ("boundary_condition", "open_profile_0_30cm"),
        ("initialization_protocol", "empirical_pool_fractionation"),
    ],
)
def test_refuses_mismatched_homology_fields(
    field_name: str, override_value: float | str
) -> None:
    base = _matched_homology()
    mismatched_kwargs: dict[str, Any] = {
        "depth_cm": base.depth_cm,
        "bulk_density_basis": base.bulk_density_basis,
        "boundary_condition": base.boundary_condition,
        "initialization_protocol": base.initialization_protocol,
        field_name: override_value,
    }
    protocols = {
        "amg_a": base,
        "amg_m": HomologyProtocol(**mismatched_kwargs),
        "rothc": base,
    }

    with pytest.raises(ValueError, match=STRUCTURAL_DEPENDENCY_VIOLATION):
        validate_ensemble_weights(
            {"amg_a": 0.25, "amg_m": 0.25, "rothc": 0.5},
            amg_dependence_handled=True,
            homology_verified=True,
            independent_validation_proven=True,
            homology_protocols=protocols,
        )


def test_allows_amg_a_amg_m_rothc_when_all_rev13_conditions_and_homology_match() -> (
    None
):
    protocols = {
        "amg_a": _matched_homology(),
        "amg_m": _matched_homology(),
        "rothc": _matched_homology(),
    }
    validated = validate_ensemble_weights(
        {"amg_a": 0.25, "amg_m": 0.25, "rothc": 0.5},
        amg_dependence_handled=True,
        homology_verified=True,
        independent_validation_proven=True,
        homology_protocols=protocols,
    )

    assert validated.valid is True
    assert validated.active_models == ("amg_a", "amg_m", "rothc")
    assert validated.matched_homology == _matched_homology()
    assert validated.normalized_weights["rothc"] == pytest.approx(0.5)


def test_allows_amg_a_and_rothc_when_amg_m_has_zero_or_no_weight() -> None:
    validated = validate_ensemble_weights({"amg_a": 0.5, "amg_m": 0.0, "rothc": 0.5})
    assert validated.active_models == ("amg_a", "rothc")

    validated_two = validate_ensemble_weights({"amg_a": 0.5, "rothc": 0.5})
    assert validated_two.active_models == ("amg_a", "rothc")


def test_compare_carbon_trajectories_enforces_guard_and_computes_explicit_ensemble() -> (
    None
):
    amg_a = _make_annual_balance(
        carbon_model="amg", variant="amg_a", initial=40.0, steps_values=(41.0, 42.0)
    )
    amg_m = _make_monthly_balance(
        carbon_model="amg",
        variant="amg_m",
        initial=40.0,
        monthly_end_stocks=(40.5, 41.0, 42.0),
    )
    rothc = _make_monthly_balance(
        carbon_model="rothc",
        variant="rothc_26_3",
        initial=40.0,
        monthly_end_stocks=(40.1, 40.2, 40.0),
    )

    with pytest.raises(ValueError, match=STRUCTURAL_DEPENDENCY_VIOLATION):
        compare_carbon_trajectories(
            [amg_a, amg_m, rothc],
            weights={"amg_a": 1 / 3, "amg_m": 1 / 3, "rothc": 1 / 3},
        )

    protocols = {m: _matched_homology() for m in TRAJECTORY_MODEL_IDS}
    res = compare_carbon_trajectories(
        [amg_a, amg_m, rothc],
        weights={"amg_a": 0.25, "amg_m": 0.25, "rothc": 0.5},
        amg_dependence_handled=True,
        homology_verified=True,
        independent_validation_proven=True,
        homology_protocols=protocols,
    )
    assert res.default_averaged is False
    assert res.weighted_ensemble is not None
    assert res.weighted_ensemble.end_stock == pytest.approx(
        0.25 * 42.0 + 0.25 * 42.0 + 0.5 * 40.0
    )


def test_weighted_ensemble_preserves_missing_never_zero() -> None:
    amg_a = _make_annual_balance(
        carbon_model="amg",
        variant="amg_a",
        initial=40.0,
        steps_values=(41.0, None),
    )
    rothc = _make_monthly_balance(
        carbon_model="rothc",
        variant="rothc_26_3",
        initial=40.0,
        monthly_end_stocks=(40.1, 40.2, 40.3),
    )

    res = compare_carbon_trajectories(
        [amg_a, rothc], weights={"amg_a": 0.5, "rothc": 0.5}
    )
    assert res.weighted_ensemble is not None
    assert isinstance(res.weighted_ensemble.end_stock, ResultMissing)
    assert res.weighted_ensemble.end_stock.reason == "MISSING_INPUT"


# --- Law 3: Monthly-annual-cycle continuity & duplicate_c_input --------------


def test_continuity_passes_for_contiguous_adjacent_periods() -> None:
    periods = [
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2021, 1),
            start_stock=40.0,
            end_stock=40.25,
            c_input=0.5,
            granularity="monthly",
        ),
        StockPeriod(
            start=_ym(2021, 2),
            end=_ym(2021, 2),
            start_stock=40.25,
            end_stock=40.10,
            c_input=0.0,
            granularity="monthly",
        ),
        StockPeriod(
            start=_ym(2021, 3),
            end=_ym(2021, 3),
            start_stock=40.10,
            end_stock=40.10 + 1e-8,
            c_input=0.0,
            granularity="monthly",
        ),
    ]

    report = check_stock_continuity(periods, tolerance=1e-6)

    assert report.is_continuous is True
    assert report.all_periods_present is True
    assert report.duplicate_c_input_detected is False
    assert report.passed is True
    assert report.checked_transitions == 2
    assert report.reasons == ()


def test_continuity_detects_end_stock_start_stock_mismatch() -> None:
    periods = [
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2021, 12),
            start_stock=40.0,
            end_stock=41.2,
            c_input=2.0,
            granularity="annual",
        ),
        StockPeriod(
            start=_ym(2022, 1),
            end=_ym(2022, 12),
            start_stock=41.9,
            end_stock=42.5,
            c_input=2.0,
            granularity="annual",
        ),
    ]

    report = check_stock_continuity(periods, tolerance=1e-6)

    assert report.is_continuous is False
    assert report.passed is False
    assert STOCK_CONTINUITY_BREAK_REASON in report.reasons
    assert len(report.continuity_breaks) == 1
    brk = report.continuity_breaks[0]
    assert brk.end_stock == pytest.approx(41.2)
    assert brk.next_start_stock == pytest.approx(41.9)
    assert brk.difference == pytest.approx(0.7)


def test_continuity_detects_duplicate_c_input_across_overlapping_periods_and_ids() -> (
    None
):
    overlapping = [
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2021, 1),
            start_stock=40.0,
            end_stock=40.5,
            c_input=1.2,
            c_input_id="harvest_2021_01",
            granularity="monthly",
        ),
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2021, 12),
            start_stock=40.5,
            end_stock=41.5,
            c_input=1.2,
            c_input_id="harvest_2021_01",
            granularity="annual",
        ),
    ]

    report = check_stock_continuity(overlapping)

    assert report.duplicate_c_input_detected is True
    assert report.passed is False
    assert DUPLICATE_C_INPUT_REASON in report.reasons
    assert len(report.duplicate_c_inputs) >= 1

    records_report = check_stock_continuity(
        [
            StockPeriod(
                start=_ym(2021, 1),
                end=_ym(2021, 12),
                start_stock=40.0,
                end_stock=41.0,
            )
        ],
        c_input_records=[
            CarbonInputRecord(
                start=_ym(2021, 4),
                end=_ym(2021, 4),
                amount=1.8,
                scale="monthly",
            ),
            CarbonInputRecord(
                start=_ym(2021, 1),
                end=_ym(2021, 12),
                amount=1.8,
                scale="annual",
            ),
        ],
    )
    assert records_report.duplicate_c_input_detected is True
    assert DUPLICATE_C_INPUT_REASON in records_report.reasons


def test_monthly_annual_cycle_cross_scale_continuity_and_duplicate_c_input() -> None:
    monthly = [
        StockPeriod(
            start=_ym(2021, m),
            end=_ym(2021, m),
            start_stock=40.0 + (m - 1) * 0.1,
            end_stock=40.0 + m * 0.1,
            c_input=0.25 if m in (4, 10) else 0.0,
            granularity="monthly",
        )
        for m in range(1, 13)
    ] + [
        StockPeriod(
            start=_ym(2022, m),
            end=_ym(2022, m),
            start_stock=41.2 + (m - 1) * 0.1,
            end_stock=41.2 + m * 0.1,
            c_input=0.25 if m in (4, 10) else 0.0,
            granularity="monthly",
        )
        for m in range(1, 13)
    ]
    annual = [
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2021, 12),
            start_stock=40.0,
            end_stock=41.2,
            c_input=0.5,
            granularity="annual",
        ),
        StockPeriod(
            start=_ym(2022, 1),
            end=_ym(2022, 12),
            start_stock=41.2,
            end_stock=42.4,
            c_input=0.5,
            granularity="annual",
        ),
    ]
    cycles = [
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2022, 12),
            start_stock=40.0,
            end_stock=42.4,
            c_input=1.0,
            granularity="cycle",
        )
    ]

    ok = check_stock_continuity(
        monthly, annual_periods=annual, cycle_periods=cycles, tolerance=1e-9
    )
    assert ok.passed is True
    assert ok.is_continuous is True
    assert ok.duplicate_c_input_detected is False

    # Double-counted annual C input (1.0 instead of 0.5) is flagged
    double_annual = [
        annual[0],
        StockPeriod(
            start=_ym(2022, 1),
            end=_ym(2022, 12),
            start_stock=41.2,
            end_stock=42.4,
            c_input=1.0,
            granularity="annual",
        ),
    ]
    flagged = check_stock_continuity(monthly, annual_periods=double_annual)
    assert flagged.duplicate_c_input_detected is True
    assert DUPLICATE_C_INPUT_REASON in flagged.reasons


def test_missing_periods_preserve_typed_missing_and_never_coerce_to_zero() -> None:
    missing_feb = InputMissing(reason="NO_COVERAGE", detail="PLACEHOLDER: gap in Feb")
    periods = [
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2021, 1),
            start_stock=40.0,
            end_stock=40.1,
            c_input=0.0,
            granularity="monthly",
        ),
        StockPeriod(
            start=_ym(2021, 2),
            end=_ym(2021, 2),
            start_stock=missing_feb,
            end_stock=missing_feb,
            c_input=missing_feb,
            granularity="monthly",
        ),
        StockPeriod(
            start=_ym(2021, 3),
            end=_ym(2021, 3),
            start_stock=40.1,
            end_stock=40.2,
            c_input=0.0,
            granularity="monthly",
        ),
    ]

    report = check_stock_continuity(periods)

    assert report.all_periods_present is False
    assert MISSING_PERIOD_REASON in report.reasons
    assert report.continuity_breaks == ()
    assert len(report.missing_periods) == 3
    for mp in report.missing_periods:
        assert mp.missing is missing_feb
        assert mp.missing != 0

    # Omitted period (timeline gap) also yields typed Missing (NO_COVERAGE), never 0
    gapped = [periods[0], periods[2]]
    gap_report = check_stock_continuity(gapped)
    assert gap_report.is_continuous is False
    assert gap_report.all_periods_present is False
    assert len(gap_report.timeline_gaps) == 1
    assert gap_report.timeline_gaps[0] == (_ym(2021, 2), _ym(2021, 2))
    assert isinstance(gap_report.missing_periods[0].missing, ResultMissing)
    assert gap_report.missing_periods[0].missing.reason == "NO_COVERAGE"


# --- G1 purity, G5 type/domain checks, immutability --------------------------


def test_g5_type_and_domain_guards() -> None:
    with pytest.raises(TypeError):
        compare_carbon_trajectories("not-a-sequence")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        compare_carbon_trajectories([])
    with pytest.raises(TypeError):
        validate_ensemble_weights({"amg_a": True})  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        validate_ensemble_weights({"amg_a": math.nan})
    with pytest.raises(ValueError):
        validate_ensemble_weights({"unknown_model": 1.0})
    with pytest.raises(ValueError):
        validate_ensemble_weights({"amg_a": 0.4, "rothc": 0.4})
    with pytest.raises(TypeError):
        validate_ensemble_weights(
            {"amg_a": 0.5, "rothc": 0.5},
            amg_dependence_handled="yes",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        StockPeriod(
            start=_ym(2021, 1),
            end=_ym(2021, 1),
            start_stock=None,  # type: ignore[arg-type]
            end_stock=40.0,
        )
    with pytest.raises(ValueError):
        HomologyProtocol(
            depth_cm=-20.0,
            bulk_density_basis="equivalent_soil_mass",
            boundary_condition="closed",
            initialization_protocol="spinup",
        )


def test_g1_purity_immutability_and_inputs_not_mutated() -> None:
    amg_a = _make_annual_balance(carbon_model="amg", variant="amg_a")
    rothc = _make_monthly_balance(carbon_model="rothc", variant="rothc_26_3")
    snapshot_a = copy.deepcopy(amg_a.model_dump())
    snapshot_r = copy.deepcopy(rothc.model_dump())

    summary_a = summarize_trajectory(amg_a)
    result = compare_carbon_trajectories([amg_a, rothc])

    assert amg_a.model_dump() == snapshot_a
    assert rothc.model_dump() == snapshot_r
    assert isinstance(summary_a, CarbonTrajectorySummary)

    with pytest.raises(FrozenInstanceError):
        result.default_averaged = True  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.separate_trajectories["amg_a"] = summary_a  # type: ignore[index]


def test_module_imports_only_stdlib_and_contracts() -> None:
    source = (REPO_ROOT / "engine" / "amg" / "model_comparison.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    allowed_stdlib = {
        "__future__",
        "calendar",
        "collections",
        "dataclasses",
        "math",
        "types",
        "typing",
    }
    assert imported_roots <= (allowed_stdlib | {"contracts"})
