"""Tests for ``engine.rothc.periods`` (agricultural-year and cycle summaries).

Every synthetic parameter record, forcing series, and balance value in this
file is a PLACEHOLDER (plainly unreal numbers with repeated digits), used only
to test aggregation, reconciliation against ``run_rothc``, C5.5 ``NO_COVERAGE``,
G4 missing propagation, G1 purity, and G5 caller validation.

Run from the repository root: ``py -3.12 -m pytest engine/rothc/test_periods.py``.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

from contracts.carbon_balance import CarbonBalance, FlowSeries, StepValue, StockSeries
from contracts.carbon_forcing import CarbonForcing
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import YearMonth
from contracts.results.models import Missing as ResultMissing
from engine.rothc import periods as periods_module
from engine.rothc.entry import (
    FLOW_QUANTITIES,
    FORCING_QUANTITIES,
    INPUT_PARAMETERS,
    PARAMETERS,
    POOL_QUANTITIES,
    STOCK_UNIT,
    run_rothc,
)
from engine.rothc.periods import (
    POOL_KEYS,
    RothcPeriodSummary,
    summarize_rothc_ag_years,
    summarize_rothc_cycles,
)
from engine.rothc.pools import MONTHS_PER_YEAR

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
FORCING_EXAMPLE = (
    ROOT / "contracts" / "carbon_forcing" / "examples" / "PLACEHOLDER_carbon_forcing.json"
)
MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
ORIGINS = ("test_origin_a", "test_origin_b")
DEGREE = f"{MARK}_degree"

PLACEHOLDER_PARAMS: dict[str, tuple[float, str]] = {
    "dpm_rate_constant": (0.22, "yr-1"),
    "rpm_rate_constant": (0.044, "yr-1"),
    "bio_rate_constant": (0.066, "yr-1"),
    "hum_rate_constant": (0.022, "yr-1"),
    "temperature_maximum": (44.4, "dimensionless"),
    "temperature_exponent_scale": (99.9, DEGREE),
    "temperature_offset": (22.2, DEGREE),
    "tsmd_intercept": (66.6, "mm"),
    "tsmd_clay_coefficient": (1.33, "mm %-1"),
    "tsmd_clay_squared_coefficient": (0.011, "mm %-2"),
    "tsmd_reference_depth": (55.5, "cm"),
    "moisture_threshold": (0.44, "dimensionless"),
    "moisture_minimum": (0.22, "dimensionless"),
    "pan_factor": (0.77, "dimensionless"),
    "cover_vegetated": (0.66, "dimensionless"),
    "cover_bare": (1.0, "dimensionless"),
    "partition_scale": (1.11, "dimensionless"),
    "partition_intercept": (2.22, "dimensionless"),
    "partition_clay_coefficient": (3.33, "dimensionless"),
    "partition_clay_decay": (0.44, "%-1"),
    "bio_share": (0.44, "dimensionless"),
    "iom_coefficient": (0.044, "dimensionless"),
    "iom_exponent": (1.11, "dimensionless"),
    "bare_tsmd_divisor": (2.22, "dimensionless"),
}


def _unmark(item: Any) -> Any:
    if isinstance(item, str):
        return item.replace(MARK, UNMARKED)
    if isinstance(item, dict):
        return {_unmark(k): _unmark(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_unmark(v) for v in item]
    return item


def _record(parameter_id: str, value: float, unit: str, scope: dict) -> dict:
    return {
        "id": parameter_id,
        "scope": scope,
        "value": value,
        "unit": unit,
        "range": None,
        "range_missing_reason": f"{MARK}: no range in this test",
        "citation": {
            "reference": f"{MARK} reference. This is not a publication.",
            "locator": f"{MARK} locator",
        },
        "transcribed_by": f"{MARK}_person_one",
        "checked_by": f"{MARK}_person_two",
    }


def _catalogue() -> dict[str, dict]:
    records = {
        f"records/{name}.json": _record(PARAMETERS[name][0], value, unit, {})
        for name, (value, unit) in PLACEHOLDER_PARAMS.items()
    }
    records[f"records/ratio_{ORIGINS[0]}.json"] = _record(
        INPUT_PARAMETERS["input_dpm_rpm_ratio"],
        1.55,
        "dimensionless",
        {"crop": ORIGINS[0]},
    )
    for name, share in (
        ("input_dpm_fraction", 0.44),
        ("input_rpm_fraction", 0.44),
        ("input_hum_fraction", 0.12),
    ):
        records[f"records/{name}_{ORIGINS[1]}.json"] = _record(
            INPUT_PARAMETERS[name],
            share,
            "dimensionless",
            {"crop": ORIGINS[1]},
        )
    return _unmark(records)


def _series_header(quantity: str, unit: str, **extra: Any) -> dict:
    return {
        "quantity": quantity,
        "unit": unit,
        "provenance": "DERIVED",
        "source": f"{MARK}: example data, no real source",
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: no range"},
        **extra,
    }


def _month_at(start: YearMonth, offset: int) -> YearMonth:
    index = start.year * MONTHS_PER_YEAR + (start.month - 1) + offset
    return YearMonth(year=index // MONTHS_PER_YEAR, month=index % MONTHS_PER_YEAR + 1)


def _monthly_series(
    start: YearMonth,
    count: int,
    quantity: str,
    unit: str,
    values: list[float | dict],
    **extra: Any,
) -> dict:
    items = []
    for offset in range(count):
        ym = _month_at(start, offset)
        val = values[offset % len(values)]
        item: dict[str, Any] = {"year": ym.year, "month": ym.month}
        if isinstance(val, dict):
            item.update(val)
        else:
            item["value"] = val
        items.append(item)
    return {
        **_series_header(quantity, unit),
        **extra,
        "start": {"year": items[0]["year"], "month": items[0]["month"]},
        "end": {"year": items[-1]["year"], "month": items[-1]["month"]},
        "months": items,
    }


def _build_forcing(
    start: YearMonth,
    month_count: int,
    *,
    rainfall_override: dict[int, dict] | None = None,
    carbon_unit: str = STOCK_UNIT,
) -> CarbonForcing:
    data = json.loads(FORCING_EXAMPLE.read_text(encoding="utf-8"))
    end = _month_at(start, month_count - 1)
    data["horizon"] = {
        "start": {"year": start.year, "month": start.month},
        "end": {"year": end.year, "month": end.month},
    }
    q = {name: qty for name, (_, qty) in FORCING_QUANTITIES.items()}
    rainfall_vals: list[float | dict] = [
        22.2 + (i % 5) for i in range(month_count)
    ]
    if rainfall_override:
        for idx, missing_spec in rainfall_override.items():
            rainfall_vals[idx] = {"value": None, **missing_spec}
    data["climate"] = [
        _monthly_series(start, month_count, q["rainfall"], "mm", rainfall_vals),
        _monthly_series(
            start,
            month_count,
            q["pan_evaporation"],
            "mm",
            [44.4 + (i % 4) for i in range(month_count)],
        ),
        _monthly_series(
            start,
            month_count,
            q["temperature"],
            _unmark(DEGREE),
            [11.1 + (i % 3) for i in range(month_count)],
        ),
    ]
    data["annual_climate"] = []
    data["annual_carbon_inputs"] = []
    data["soil_cover"] = [
        _monthly_series(
            start,
            month_count,
            q["soil_cover"],
            "dimensionless",
            [float(i % 2) for i in range(month_count)],
        ),
    ]
    data["carbon_inputs"] = [
        _monthly_series(
            start,
            month_count,
            "placeholder_input_a",
            carbon_unit,
            [0.33 + 0.11 * (i % 3) for i in range(month_count)],
            origin=ORIGINS[0],
        ),
        _monthly_series(
            start,
            month_count,
            "placeholder_input_b",
            carbon_unit,
            [0.22 * (i % 2) for i in range(month_count)],
            origin=ORIGINS[1],
        ),
    ]
    data["soil_properties"] = [
        {**_series_header(q["clay_content"], "%"), "value": 33.3},
    ]
    data["soil_depth"] = {
        "value": 55.5,
        "unit": "cm",
        "provenance": "DECLARED",
        "source": f"{MARK}: example data, no real source",
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: no range"},
    }
    data["starting_state"] = [
        {
            **_series_header(q[name], STOCK_UNIT),
            "provenance": "DECLARED",
            "value": 9.99 * (pos + 1),
        }
        for pos, name in enumerate(
            ("dpm_pool", "rpm_pool", "bio_pool", "hum_pool", "iom_pool")
        )
    ]
    return CarbonForcing.model_validate(data)


def _assert_all_missing(summary: RothcPeriodSummary, reason: str, *words: str) -> None:
    candidates = [
        summary.total_stock,
        summary.carbon_input_sum,
        summary.co2_sum,
        *(summary.pool_stocks[k] for k in POOL_KEYS),
    ]
    for item in candidates:
        assert isinstance(item, ResultMissing), item
        assert item.reason == reason, item
        for word in words:
            assert word in (item.detail or ""), item.detail


# --- Agricultural-year summaries and reconciliation with run_rothc ----------


def test_ag_years_reconcile_with_run_rothc_for_full_non_january_years() -> None:
    start = YearMonth(year=2001, month=7)
    balance = run_rothc(_build_forcing(start, 24), parameters=_catalogue())
    summaries = summarize_rothc_ag_years(balance, ag_year_start=start)

    assert len(summaries) == 2
    assert [s.period_label for s in summaries] == ["ag_year_2001", "ag_year_2002"]
    assert summaries[0].start == YearMonth(year=2001, month=7)
    assert summaries[0].end == YearMonth(year=2002, month=6)
    assert summaries[1].start == YearMonth(year=2002, month=7)
    assert summaries[1].end == YearMonth(year=2003, month=6)

    pools_by_qty = {s.quantity: s for s in balance.pools}
    flows_by_qty = {s.quantity: s for s in balance.flows}
    cin_steps = flows_by_qty[FLOW_QUANTITIES["carbon_input"]].steps
    co2_steps = flows_by_qty[FLOW_QUANTITIES["co2"]].steps

    prev_stock = balance.total_stock.initial.value
    assert isinstance(prev_stock, float)

    for year_idx, summary in enumerate(summaries):
        lo = year_idx * MONTHS_PER_YEAR
        hi = lo + MONTHS_PER_YEAR
        expected_total = balance.total_stock.steps[hi - 1].value
        assert isinstance(expected_total, float)
        assert summary.total_stock == pytest.approx(expected_total)

        assert tuple(summary.pool_stocks.keys()) == POOL_KEYS
        for pool in POOL_KEYS:
            expected_pool = pools_by_qty[POOL_QUANTITIES[pool]].steps[hi - 1].value
            assert isinstance(expected_pool, float)
            assert summary.pool_stocks[pool] == pytest.approx(expected_pool)

        assert summary.total_stock == pytest.approx(
            math.fsum(float(v) for v in summary.pool_stocks.values())
        )

        expected_cin = math.fsum(float(s.value) for s in cin_steps[lo:hi])
        expected_co2 = math.fsum(float(s.value) for s in co2_steps[lo:hi])
        assert summary.carbon_input_sum == pytest.approx(expected_cin)
        assert summary.co2_sum == pytest.approx(expected_co2)

        # Mass balance over the agricultural year: stocks_out + co2 == stocks_in + inputs.
        assert float(summary.total_stock) + float(summary.co2_sum) == pytest.approx(
            prev_stock + float(summary.carbon_input_sum)
        )
        prev_stock = float(summary.total_stock)


def test_ag_years_incomplete_leading_and_trailing_years_emit_no_coverage() -> None:
    # 2001-01 .. 2003-09 (33 months), with ag_year starting in July (month 7):
    # - 2001-01..2001-06 -> incomplete ag_year_2000 (6 months)
    # - 2001-07..2002-06 -> complete ag_year_2001 (12 months)
    # - 2002-07..2003-06 -> complete ag_year_2002 (12 months)
    # - 2003-07..2003-09 -> incomplete ag_year_2003 (3 months)
    horizon_start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(horizon_start, 33), parameters=_catalogue())
    summaries = summarize_rothc_ag_years(
        balance, ag_year_start=YearMonth(year=2001, month=7)
    )

    assert [s.period_label for s in summaries] == [
        "ag_year_2000",
        "ag_year_2001",
        "ag_year_2002",
        "ag_year_2003",
    ]
    assert summaries[0].start == YearMonth(year=2001, month=1)
    assert summaries[0].end == YearMonth(year=2001, month=6)
    _assert_all_missing(summaries[0], "NO_COVERAGE", "C5.5", "6 of 12")

    assert isinstance(summaries[1].total_stock, float)
    assert isinstance(summaries[2].total_stock, float)
    assert summaries[1].start == YearMonth(year=2001, month=7)
    assert summaries[1].end == YearMonth(year=2002, month=6)
    assert summaries[2].start == YearMonth(year=2002, month=7)
    assert summaries[2].end == YearMonth(year=2003, month=6)

    assert summaries[3].start == YearMonth(year=2003, month=7)
    assert summaries[3].end == YearMonth(year=2003, month=9)
    _assert_all_missing(summaries[3], "NO_COVERAGE", "C5.5", "3 of 12")


def test_ag_years_short_horizon_under_twelve_months_emits_no_coverage() -> None:
    start = YearMonth(year=2001, month=7)
    balance = run_rothc(_build_forcing(start, 5), parameters=_catalogue())
    summaries = summarize_rothc_ag_years(balance, ag_year_start=start)

    assert len(summaries) == 1
    assert summaries[0].period_label == "ag_year_2001"
    assert summaries[0].start == YearMonth(year=2001, month=7)
    assert summaries[0].end == YearMonth(year=2001, month=11)
    _assert_all_missing(summaries[0], "NO_COVERAGE", "5 of 12")


# --- Missing-step propagation (G4, never zero) ------------------------------


def test_ag_years_missing_monthly_step_propagates_missing_never_zero() -> None:
    start = YearMonth(year=2001, month=7)
    # Year 1 (months 0..11) is complete; month 14 (2002-09, inside Year 2) lacks rainfall.
    forcing = _build_forcing(
        start,
        24,
        rainfall_override={
            14: {"missing": {"reason": "NO_COVERAGE", "detail": f"{MARK}: no rain"}}
        },
    )
    balance = run_rothc(forcing, parameters=_catalogue())
    summaries = summarize_rothc_ag_years(balance, ag_year_start=start)

    assert len(summaries) == 2
    assert isinstance(summaries[0].total_stock, float)
    assert all(isinstance(v, float) for v in summaries[0].pool_stocks.values())
    assert isinstance(summaries[0].carbon_input_sum, float)
    assert isinstance(summaries[0].co2_sum, float)

    # Month 14 fails inside run_rothc with MISSING_INPUT naming rainfall / NO_COVERAGE.
    _assert_all_missing(summaries[1], "MISSING_INPUT", "2002-09", "NO_COVERAGE")


def test_ag_years_not_computable_at_start_propagates_original_reason() -> None:
    start = YearMonth(year=2001, month=1)
    params = _catalogue()
    params["records/bio_share.json"]["value"] = 1.5
    balance = run_rothc(_build_forcing(start, 12), parameters=params)
    summaries = summarize_rothc_ag_years(balance, ag_year_start=start)

    assert len(summaries) == 1
    _assert_all_missing(summaries[0], "NOT_COMPUTABLE", "2001-01", "bio_share")


def test_synthetic_missing_step_inside_year_propagates_original_reason() -> None:
    start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(start, 12), parameters=_catalogue())
    # Replace step 4 (2001-05) in carbon_input flow with Missing(reason="NO_COVERAGE").
    dumped = balance.model_dump()
    for flow in dumped["flows"]:
        if flow["quantity"] == FLOW_QUANTITIES["carbon_input"]:
            flow["steps"][4] = {
                "start": {"year": 2001, "month": 5},
                "end": {"year": 2001, "month": 5},
                "value": None,
                "missing": {"reason": "NO_COVERAGE", "detail": f"{MARK}: gap"},
            }
    mutated = CarbonBalance.model_validate(dumped)
    summaries = summarize_rothc_ag_years(mutated, ag_year_start=start)

    assert len(summaries) == 1
    assert isinstance(summaries[0].total_stock, float)
    assert isinstance(summaries[0].co2_sum, float)
    assert isinstance(summaries[0].carbon_input_sum, ResultMissing)
    assert summaries[0].carbon_input_sum.reason == "NO_COVERAGE"
    assert "2001-05" in (summaries[0].carbon_input_sum.detail or "")


# --- Multi-year rotation cycles ---------------------------------------------


def test_cycles_aggregate_full_blocks_and_reconcile_with_ag_years() -> None:
    start = YearMonth(year=2001, month=7)
    balance = run_rothc(_build_forcing(start, 48), parameters=_catalogue())
    ag_years = summarize_rothc_ag_years(balance, ag_year_start=start)
    cycles = summarize_rothc_cycles(balance, ag_year_start=start, cycle_years=2)

    assert len(cycles) == 2
    assert [c.period_label for c in cycles] == ["cycle_1", "cycle_2"]
    assert cycles[0].start == YearMonth(year=2001, month=7)
    assert cycles[0].end == YearMonth(year=2003, month=6)
    assert cycles[1].start == YearMonth(year=2003, month=7)
    assert cycles[1].end == YearMonth(year=2005, month=6)

    # Cycle 1 reconciles with ag_years[0:2]; Cycle 2 reconciles with ag_years[2:4].
    for cycle_idx, cycle in enumerate(cycles):
        pair = ag_years[cycle_idx * 2 : cycle_idx * 2 + 2]
        assert cycle.total_stock == pytest.approx(pair[-1].total_stock)
        for pool in POOL_KEYS:
            assert cycle.pool_stocks[pool] == pytest.approx(pair[-1].pool_stocks[pool])
        assert cycle.carbon_input_sum == pytest.approx(
            math.fsum(float(y.carbon_input_sum) for y in pair)
        )
        assert cycle.co2_sum == pytest.approx(
            math.fsum(float(y.co2_sum) for y in pair)
        )

    # Mass balance over the first cycle from initial_state.
    initial = float(balance.total_stock.initial.value)  # type: ignore[arg-type]
    assert float(cycles[0].total_stock) + float(cycles[0].co2_sum) == pytest.approx(
        initial + float(cycles[0].carbon_input_sum)
    )


def test_cycles_with_cycle_years_one_match_ag_years() -> None:
    start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(start, 24), parameters=_catalogue())
    ag_years = summarize_rothc_ag_years(balance, ag_year_start=start)
    cycles = summarize_rothc_cycles(balance, ag_year_start=start, cycle_years=1)

    assert len(cycles) == len(ag_years) == 2
    for year_summary, cycle_summary in zip(ag_years, cycles, strict=True):
        assert cycle_summary.start == year_summary.start
        assert cycle_summary.end == year_summary.end
        assert cycle_summary.total_stock == year_summary.total_stock
        assert cycle_summary.pool_stocks == year_summary.pool_stocks
        assert cycle_summary.carbon_input_sum == year_summary.carbon_input_sum
        assert cycle_summary.co2_sum == year_summary.co2_sum


def test_cycles_partial_tail_emits_no_coverage() -> None:
    # 60 months = 5 full agricultural years; cycle_years=3 -> 1 full cycle + 24-month partial tail.
    start = YearMonth(year=2001, month=7)
    balance = run_rothc(_build_forcing(start, 60), parameters=_catalogue())
    cycles = summarize_rothc_cycles(balance, ag_year_start=start, cycle_years=3)

    assert len(cycles) == 2
    assert cycles[0].period_label == "cycle_1"
    assert cycles[0].start == YearMonth(year=2001, month=7)
    assert cycles[0].end == YearMonth(year=2004, month=6)
    assert isinstance(cycles[0].total_stock, float)

    assert cycles[1].period_label == "cycle_2"
    assert cycles[1].start == YearMonth(year=2004, month=7)
    assert cycles[1].end == YearMonth(year=2006, month=6)
    _assert_all_missing(cycles[1], "NO_COVERAGE", "24 of 36")


def test_cycles_leading_incomplete_and_partial_tail_with_extra_months() -> None:
    # 2001-01 .. 2004-09 (45 months), ag_year_start month=7, cycle_years=2:
    # - 2001-01..2001-06 (6m): leading incomplete ag_year_2000 -> NO_COVERAGE
    # - 2001-07..2003-06 (24m): complete cycle_1
    # - 2003-07..2004-09 (15m: 1 full ag year + 3 trailing months): partial tail cycle_2 -> NO_COVERAGE
    horizon_start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(horizon_start, 45), parameters=_catalogue())
    cycles = summarize_rothc_cycles(
        balance, ag_year_start=YearMonth(year=2001, month=7), cycle_years=2
    )

    assert len(cycles) == 3
    assert cycles[0].start == YearMonth(year=2001, month=1)
    assert cycles[0].end == YearMonth(year=2001, month=6)
    _assert_all_missing(cycles[0], "NO_COVERAGE", "6 of 24")

    assert cycles[1].period_label == "cycle_1"
    assert cycles[1].start == YearMonth(year=2001, month=7)
    assert cycles[1].end == YearMonth(year=2003, month=6)
    assert isinstance(cycles[1].total_stock, float)

    assert cycles[2].period_label == "cycle_2"
    assert cycles[2].start == YearMonth(year=2003, month=7)
    assert cycles[2].end == YearMonth(year=2004, month=9)
    _assert_all_missing(cycles[2], "NO_COVERAGE", "15 of 24")


def test_cycles_missing_step_inside_second_cycle_propagates_missing() -> None:
    start = YearMonth(year=2001, month=7)
    # Month 30 lies inside cycle 2 (months 24..47).
    forcing = _build_forcing(
        start,
        48,
        rainfall_override={
            30: {"missing": {"reason": "SOURCE_UNAVAILABLE", "detail": f"{MARK}: outage"}}
        },
    )
    balance = run_rothc(forcing, parameters=_catalogue())
    cycles = summarize_rothc_cycles(balance, ag_year_start=start, cycle_years=2)

    assert len(cycles) == 2
    assert isinstance(cycles[0].total_stock, float)
    assert isinstance(cycles[0].carbon_input_sum, float)
    _assert_all_missing(cycles[1], "MISSING_INPUT", "2004-01", "SOURCE_UNAVAILABLE")


# --- G1 purity, module hygiene, and G5 caller validation --------------------


def test_g1_purity_determinism_and_immutability() -> None:
    start = YearMonth(year=2001, month=7)
    balance = run_rothc(_build_forcing(start, 24), parameters=_catalogue())
    snapshot = balance.model_dump(mode="json")

    years_a = summarize_rothc_ag_years(balance, ag_year_start=start)
    years_b = summarize_rothc_ag_years(balance, ag_year_start=start)
    assert years_a == years_b

    cycles_a = summarize_rothc_cycles(balance, ag_year_start=start, cycle_years=2)
    cycles_b = summarize_rothc_cycles(balance, ag_year_start=start, cycle_years=2)
    assert cycles_a == cycles_b
    assert balance.model_dump(mode="json") == snapshot

    with pytest.raises(dataclasses.FrozenInstanceError):
        years_a[0].total_stock = 0.0  # type: ignore[misc]


def test_g1_periods_module_holds_no_domain_constants_or_io_imports() -> None:
    source = Path(periods_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            assert top in sys.stdlib_module_names or name.startswith(
                ("contracts.", "engine.")
            ), name
            assert top not in ("os", "io", "pathlib", "socket", "time", "random")

    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1, 0.0, 1.0}, numbers


def test_signatures_have_keyword_only_parameters_and_no_defaults() -> None:
    sig_years = inspect.signature(summarize_rothc_ag_years).parameters
    assert list(sig_years) == ["balance", "ag_year_start"]
    assert sig_years["ag_year_start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert all(p.default is inspect.Parameter.empty for p in sig_years.values())

    sig_cycles = inspect.signature(summarize_rothc_cycles).parameters
    assert list(sig_cycles) == ["balance", "ag_year_start", "cycle_years"]
    assert sig_cycles["ag_year_start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig_cycles["cycle_years"].kind is inspect.Parameter.KEYWORD_ONLY
    assert all(p.default is inspect.Parameter.empty for p in sig_cycles.values())


@pytest.mark.parametrize("bad_balance", [None, {}, "balance", 123])
def test_g5_wrong_balance_type_raises_type_error(bad_balance: Any) -> None:
    start = YearMonth(year=2001, month=1)
    with pytest.raises(TypeError, match="balance"):
        summarize_rothc_ag_years(bad_balance, ag_year_start=start)
    with pytest.raises(TypeError, match="balance"):
        summarize_rothc_cycles(bad_balance, ag_year_start=start, cycle_years=1)


@pytest.mark.parametrize("bad_start", [None, 7, {"year": 2001, "month": 7}, "2001-07"])
def test_g5_wrong_ag_year_start_type_raises_type_error(bad_start: Any) -> None:
    start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(start, 12), parameters=_catalogue())
    with pytest.raises(TypeError, match="ag_year_start"):
        summarize_rothc_ag_years(balance, ag_year_start=bad_start)
    with pytest.raises(TypeError, match="ag_year_start"):
        summarize_rothc_cycles(balance, ag_year_start=bad_start, cycle_years=1)


@pytest.mark.parametrize("bad_cycle_years", [True, False, 1.0, 2.5, "2", None])
def test_g5_wrong_cycle_years_type_raises_type_error(bad_cycle_years: Any) -> None:
    start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(start, 12), parameters=_catalogue())
    with pytest.raises(TypeError, match="cycle_years"):
        summarize_rothc_cycles(
            balance, ag_year_start=start, cycle_years=bad_cycle_years
        )


@pytest.mark.parametrize("bad_cycle_years", [0, -1, -5])
def test_g5_non_positive_cycle_years_raises_value_error(bad_cycle_years: int) -> None:
    start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(start, 12), parameters=_catalogue())
    with pytest.raises(ValueError, match="cycle_years"):
        summarize_rothc_cycles(
            balance, ag_year_start=start, cycle_years=bad_cycle_years
        )


def test_g5_non_rothc_or_non_monthly_balance_raises_value_error() -> None:
    start = YearMonth(year=2001, month=1)
    balance = run_rothc(_build_forcing(start, 12), parameters=_catalogue())

    # Wrong carbon_model.
    dumped_amg = balance.model_dump()
    dumped_amg["carbon_model"] = "amg"
    for item in dumped_amg["soil_carbon_trend"]:
        item["carbon_model"] = "amg"
    amg_balance = CarbonBalance.model_validate(dumped_amg)
    with pytest.raises(ValueError, match="carbon_model"):
        summarize_rothc_ag_years(amg_balance, ag_year_start=start)

    # Annual (non-monthly) step.
    annual_step = StepValue(
        start=YearMonth(year=2001, month=1),
        end=YearMonth(year=2001, month=12),
        value=99.9,
    )
    annual_balance = CarbonBalance(
        contract="carbon_balance",
        example_data=True,
        case_id=balance.case_id,
        field_id=balance.field_id,
        rotation_id=balance.rotation_id,
        carbon_model="rothc",
        variant=balance.variant,
        horizon=balance.horizon,
        soil_depth=balance.soil_depth,
        total_stock=StockSeries(
            quantity=POOL_QUANTITIES["total"],
            unit=STOCK_UNIT,
            provenance="SIMULATED",
            source=f"{MARK}: annual test",
            range_missing=InputMissing(reason="NOT_AVAILABLE", detail=f"{MARK}: none"),
            initial=Value(
                value=99.9,
                unit=STOCK_UNIT,
                provenance="DECLARED",
                source=f"{MARK}: annual test",
                range_missing=InputMissing(
                    reason="NOT_AVAILABLE", detail=f"{MARK}: none"
                ),
            ),
            steps=[annual_step],
        ),
        pools=[],
        flows=[],
        soil_carbon_trend=balance.soil_carbon_trend,
    )
    with pytest.raises(ValueError, match="monthly"):
        summarize_rothc_ag_years(annual_balance, ag_year_start=start)

    # Missing expected pool series on a monthly RothC balance.
    dumped_missing_pool = balance.model_dump()
    dumped_missing_pool["pools"] = dumped_missing_pool["pools"][:-1]
    missing_pool_balance = CarbonBalance.model_validate(dumped_missing_pool)
    with pytest.raises(ValueError, match="pool"):
        summarize_rothc_ag_years(missing_pool_balance, ag_year_start=start)

    # Missing expected flow series on a monthly RothC balance.
    dumped_missing_flow = balance.model_dump()
    dumped_missing_flow["flows"] = dumped_missing_flow["flows"][:-1]
    missing_flow_balance = CarbonBalance.model_validate(dumped_missing_flow)
    with pytest.raises(ValueError, match="flow"):
        summarize_rothc_ag_years(missing_flow_balance, ag_year_start=start)
