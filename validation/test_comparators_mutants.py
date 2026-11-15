"""Mutant-killing tests for the validation comparators:
- ``validation/trivial_comparator.py``
- ``validation/trivial_comparator_erosion.py``
- ``validation/trivial_comparator_water.py``
- ``validation/order_between_systems.py``

Every table, daily series, and identifier here uses PLACEHOLDER test inputs
only and carries no real scientific value.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from contracts.results.models import Missing, Range, ResultsTable, ResultsTableRow
from validation import trivial_comparator
from validation.order_between_systems import compare_with_expected_order
from validation.trivial_comparator import (
    DecisionOrder,
    _order_one,
    compare_with_decision,
    decision_order,
    trivial_orders,
)
from validation.trivial_comparator_erosion import (
    compare_with_soil_loss,
    erosion_orders,
    year_shares,
)
from validation.trivial_comparator_water import (
    WaterDay,
    compare_with_full_indicator,
    water_orders,
    year_ratio,
)

CASE_ID = "PLACEHOLDER-case"
FIELD_ID = "PLACEHOLDER-field"
SOURCE = "PLACEHOLDER_source"
KIND = "PLACEHOLDER_kind"
NA = Missing(reason="NOT_APPLICABLE", detail="PLACEHOLDER: no crop on the day")


def _soil_row(
    rotation_id: str,
    scenario_id: str,
    ag_year: int,
    value: float | None,
    low: float | None = None,
    high: float | None = None,
    *,
    reason: str = "NO_COVERAGE",
) -> ResultsTableRow:
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=None,
            unit="t ha-1 yr-1",
            missing=Missing(reason=reason, detail="PLACEHOLDER missing"),
        )
    lo = value - 0.1 if low is None else low
    hi = value + 0.1 if high is None else high
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit="t ha-1 yr-1",
        range=Range(low=lo, high=hi, kind=KIND),
        provenance="DERIVED",
        source=SOURCE,
    )


def _water_row(
    rotation_id: str,
    scenario_id: str,
    ag_year: int | None,
    value: float | None,
    *,
    time_basis: str = "ag_year",
) -> ResultsTableRow:
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis=time_basis,
            ag_year=ag_year,
            indicator="water_deficit_exposure",
            direction="higher_is_better",
            value=None,
            unit="dimensionless",
            missing=Missing(reason="NO_COVERAGE", detail="PLACEHOLDER missing"),
        )
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis=time_basis,
        ag_year=ag_year,
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=value,
        unit="dimensionless",
        range=Range(low=value - 0.1, high=value + 0.1, kind=KIND),
        provenance="SIMULATED",
        source=SOURCE,
    )


def _table(rows: list[ResultsTableRow]) -> ResultsTable:
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


# === 1. validation/trivial_comparator.py =====================================


def test_d0_order_one_rejects_mixed_directions_and_mixed_time_bases():
    mixed_dir = [
        SimpleNamespace(
            rotation_id="A",
            direction="lower_is_better",
            time_basis="ag_year",
            ag_year=2020,
            value=1.0,
            missing=None,
        ),
        SimpleNamespace(
            rotation_id="B",
            direction="higher_is_better",
            time_basis="ag_year",
            ag_year=2020,
            value=2.0,
            missing=None,
        ),
    ]
    res_dir = _order_one("s1", "soil_loss", mixed_dir)
    assert res_dir.order is None
    assert res_dir.direction is None
    assert "direction" in res_dir.reason

    mixed_basis = [
        SimpleNamespace(
            rotation_id="A",
            direction="higher_is_better",
            time_basis="ag_year",
            ag_year=2020,
            value=1.0,
            missing=None,
        ),
        SimpleNamespace(
            rotation_id="B",
            direction="higher_is_better",
            time_basis="rotation",
            ag_year=None,
            value=2.0,
            missing=None,
        ),
    ]
    res_basis = _order_one("s1", "water_deficit_exposure", mixed_basis)
    assert res_basis.order is None
    assert "time basis" in res_basis.reason


def test_d0_water_on_rotation_time_basis_gives_no_trivial_order():
    table = _table(
        [
            _water_row("A", "s1", None, 0.8, time_basis="rotation"),
            _water_row("B", "s1", None, 0.4, time_basis="rotation"),
        ]
    )
    (order,) = trivial_orders(table)
    assert order.order is None
    assert order.means is None
    assert "time basis" in order.reason


def test_d0_partial_tie_among_three_rotations_gives_no_order():
    # A=1.0, B=2.0, C=2.0 (lower_is_better): not all tied, still must reject.
    rows_low = [
        _soil_row("A", "s1", 2020, 1.0),
        _soil_row("B", "s1", 2020, 2.0),
        _soil_row("C", "s1", 2020, 2.0),
    ]
    (order_low,) = trivial_orders(_table(rows_low))
    assert order_low.order is None
    assert order_low.means is not None
    assert "'B' and 'C'" in order_low.reason

    # A=2.0, B=2.0, C=1.0 (higher_is_better): partial tie must also reject.
    rows_high = [
        _water_row("A", "s1", 2020, 2.0),
        _water_row("B", "s1", 2020, 2.0),
        _water_row("C", "s1", 2020, 1.0),
    ]
    (order_high,) = trivial_orders(_table(rows_high))
    assert order_high.order is None
    assert "'A' and 'B'" in order_high.reason


def test_d0_exact_fraction_breaks_decimal_tie_for_higher_is_better():
    rows = [
        _water_row("A", "s1", 2020, 0.1),
        _water_row("A", "s1", 2021, 0.2),
        _water_row("B", "s1", 2020, 0.3),
        _water_row("B", "s1", 2021, 0.0),
    ]
    (order,) = trivial_orders(_table(rows))
    assert order.order == ("A", "B")
    assert order.reason is None


def test_d0_multiple_missing_years_are_listed_deterministically():
    rows = [
        _soil_row("B", "s1", 2021, None, reason="NOT_AVAILABLE"),
        _soil_row("A", "s1", 2020, None, reason="NO_COVERAGE"),
        _soil_row("A", "s1", 2021, 2.0),
        _soil_row("B", "s1", 2020, 3.0),
    ]
    (order,) = trivial_orders(_table(rows))
    assert order.order is None
    assert "'A' in 2020 (NO_COVERAGE); 'B' in 2021 (NOT_AVAILABLE)" in order.reason


def test_d0_decision_order_reports_not_evaluated_when_no_shared_year_has_values():
    rows = [
        _soil_row("A", "s1", 2020, 1.0),
        _soil_row("A", "s1", 2021, None),
        _soil_row("B", "s1", 2020, None),
        _soil_row("B", "s1", 2021, 2.0),
    ]
    table = _table(rows)
    dec = decision_order(table, "s1", "soil_loss")
    assert dec.order is None
    assert "no paired difference" in dec.reason
    assert "holds a value" in dec.reason


def test_d0_decision_order_rejects_intransitive_pairwise_cycle():
    # Each pair shares only one year with values on both sides:
    # 2020: A (1.0) beats C (10.0)
    # 2021: B (1.0) beats A (10.0)
    # 2022: C (1.0) beats B (10.0)
    rows = [
        _soil_row("A", "s1", 2020, 1.0, 0.9, 1.1),
        _soil_row("A", "s1", 2021, 10.0, 9.9, 10.1),
        _soil_row("A", "s1", 2022, None),
        _soil_row("B", "s1", 2020, None),
        _soil_row("B", "s1", 2021, 1.0, 0.9, 1.1),
        _soil_row("B", "s1", 2022, 10.0, 9.9, 10.1),
        _soil_row("C", "s1", 2020, 10.0, 9.9, 10.1),
        _soil_row("C", "s1", 2021, None),
        _soil_row("C", "s1", 2022, 1.0, 0.9, 1.1),
    ]
    dec = decision_order(_table(rows), "s1", "soil_loss")
    assert dec.order is None
    assert "do not form one order" in dec.reason


def test_d0_decision_order_names_multiple_computations_on_carbon_trend():
    rows = []
    for computation, a, b in (
        ("end_minus_start", (0.1, 0.0, 0.2), (0.15, 0.1, 0.2)),
        ("fitted_slope", (0.0, -0.1, 0.1), (0.3, 0.2, 0.4)),
    ):
        for rotation_id, (val, lo, hi) in (("A", a), ("B", b)):
            rows.append(
                ResultsTableRow(
                    rotation_id=rotation_id,
                    scenario_id="s1",
                    time_basis="rotation",
                    indicator="soil_carbon_trend",
                    direction="higher_is_better",
                    value=val,
                    unit="t C ha-1 yr-1",
                    carbon_model="amg",
                    computation=computation,
                    range=Range(low=lo, high=hi, kind=KIND),
                    provenance="SIMULATED",
                    source=SOURCE,
                )
            )
    dec = decision_order(_table(rows), "s1", "soil_carbon_trend")
    assert dec.order is None
    assert "2 carbon models and computations" in dec.reason


def test_d0_compare_with_decision_reports_different_outcome(monkeypatch):
    rows = [
        _soil_row("A", "s1", 2020, 1.0),
        _soil_row("B", "s1", 2020, 5.0),
    ]
    monkeypatch.setattr(
        trivial_comparator,
        "decision_order",
        lambda scenario, scenario_id, indicator: DecisionOrder(
            scenario_id, indicator, ("B", "A"), None
        ),
    )
    (item,) = compare_with_decision(_table(rows))
    assert item.trivial.order == ("A", "B")
    assert item.decision.order == ("B", "A")
    assert item.outcome == "different"


# === 2. validation/trivial_comparator_erosion.py =============================


def _day_flags(
    start: dt.date, end: dt.date, living_months: set[int]
) -> dict[dt.date, bool]:
    flags: dict[dt.date, bool] = {}
    cur = start
    while cur <= end:
        flags[cur] = cur.month in living_months
        cur += dt.timedelta(days=1)
    return flags


_EROSIVITY_WEIGHTED = {
    1: 30.0,
    2: 30.0,
    3: 20.0,
    4: 5.0,
    5: 2.0,
    6: 1.0,
    7: 1.0,
    8: 1.0,
    9: 2.0,
    10: 3.0,
    11: 2.0,
    12: 3.0,
}


def test_e0_unions_agricultural_years_across_rotations():
    # A covers ag_years 2020 and 2021; B covers only 2020.
    living = {
        ("A", "s1"): _day_flags(dt.date(2020, 7, 1), dt.date(2022, 6, 30), {1, 2, 3}),
        ("B", "s1"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {6, 7, 8}),
    }
    shares = {
        (s.rotation_id, s.ag_year): s
        for s in year_shares(living, _EROSIVITY_WEIGHTED, start_month=7)
    }
    assert shares[("B", 2021)].share is None
    assert shares[("B", 2021)].missing.reason == "NO_COVERAGE"
    (order,) = erosion_orders(living, _EROSIVITY_WEIGHTED, start_month=7)
    assert order.order is None
    assert "'B' in 2021 (NO_COVERAGE)" in order.reason


def test_e0_leap_year_february_uses_29_days():
    # Agricultural year 2023 (July 2023 - June 2024) contains Feb 2024 (29 days).
    erosivity = {m: (1.0 if m == 2 else 0.0) for m in range(1, 13)}
    days = _day_flags(dt.date(2023, 7, 1), dt.date(2024, 6, 30), set(range(1, 13)))
    # Mark first 14 days of Feb 2024 as bare (False).
    for d in range(1, 15):
        days[dt.date(2024, 2, d)] = False
    (share,) = year_shares({("A", "s1"): days}, erosivity, start_month=7)
    assert share.share == pytest.approx(14 / 29)
    assert share.share != pytest.approx(14 / 28)

    # Removing Feb 29 makes Feb 2024 incomplete -> NO_COVERAGE.
    del days[dt.date(2024, 2, 29)]
    (missing_leap,) = year_shares({("A", "s1"): days}, erosivity, start_month=7)
    assert missing_leap.share is None
    assert missing_leap.missing.reason == "NO_COVERAGE"


def test_e0_zero_total_erosivity_propagates_not_computable():
    zero_erosivity = {m: 0.0 for m in range(1, 13)}
    living = {
        ("A", "s1"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1, 2}),
        ("B", "s1"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {3, 4}),
    }
    shares = year_shares(living, zero_erosivity, start_month=7)
    assert all(s.share is None and s.missing.reason == "NOT_COMPUTABLE" for s in shares)
    (order,) = erosion_orders(living, zero_erosivity, start_month=7)
    assert order.order is None
    assert "NOT_COMPUTABLE" in order.reason


def test_e0_missing_flag_without_detail_falls_back_to_reason():
    living = {
        ("A", "s1"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1}),
    }
    living[("A", "s1")][dt.date(2020, 9, 1)] = Missing(
        reason="NOT_AVAILABLE", detail=None
    )
    (share,) = year_shares(living, _EROSIVITY_WEIGHTED, start_month=7)
    assert share.share is None
    assert share.missing.reason == "NOT_AVAILABLE"
    assert "NOT_AVAILABLE" in share.missing.detail


def test_e0_partial_tie_among_three_rotations_gives_no_order():
    living = {
        ("A", "s1"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1, 2, 3}),
        ("B", "s1"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1, 2, 3}),
        ("C", "s1"): _day_flags(
            dt.date(2020, 7, 1), dt.date(2021, 6, 30), set(range(1, 12))
        ),
    }
    (order,) = erosion_orders(living, _EROSIVITY_WEIGHTED, start_month=7)
    assert order.order is None
    assert order.means is not None
    assert "'A' and 'B'" in order.reason


def test_e0_exact_fraction_breaks_float_mean_tie():
    erosivity = {
        m: (1.0 if m == 1 else (1e-16 if m == 2 else 0.0)) for m in range(1, 13)
    }
    # Year 2020 (Jul 2020 - Jun 2021): all bare -> share = 1.0 for both A and B.
    # Year 2021 (Jul 2021 - Jun 2022): A has Feb bare -> share ~ 1e-16; B all living -> 0.0.
    a_days = _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), set())
    a_days.update(
        _day_flags(dt.date(2021, 7, 1), dt.date(2022, 6, 30), set(range(1, 13)) - {2})
    )
    b_days = _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), set())
    b_days.update(
        _day_flags(dt.date(2021, 7, 1), dt.date(2022, 6, 30), set(range(1, 13)))
    )

    (order,) = erosion_orders(
        {("A", "s1"): a_days, ("B", "s1"): b_days}, erosivity, start_month=7
    )
    assert order.order == ("B", "A")
    assert order.reason is None


def test_e0_compare_with_soil_loss_unmatched_scenarios_other_indicators_and_reverse_mismatch():
    living = {
        ("A", "only_flags"): _day_flags(
            dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1, 2, 3, 4}
        ),
        ("B", "only_flags"): _day_flags(
            dt.date(2020, 7, 1), dt.date(2021, 6, 30), {7, 8}
        ),
        ("A", "both"): _day_flags(
            dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1, 2, 3, 4}
        ),
        ("B", "both"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {7, 8}),
    }
    rows = [
        _soil_row("A", "both", 2020, 1.0),
        _soil_row("B", "both", 2020, 5.0),
        _soil_row("A", "only_table", 2020, 1.0),
        _soil_row("B", "only_table", 2020, 5.0),
        # Extra indicator in "both" and in a water-only scenario must be ignored.
        _water_row("A", "both", 2020, 0.9),
        _water_row("B", "both", 2020, 0.1),
        _water_row("A", "water_only", 2020, 0.9),
        _water_row("B", "water_only", 2020, 0.1),
    ]
    report = {
        item.scenario_id: item
        for item in compare_with_soil_loss(
            living, _EROSIVITY_WEIGHTED, _table(rows), start_month=7
        )
    }
    assert set(report) == {"both", "only_flags", "only_table"}
    assert report["both"].outcome == "equal"
    assert report["only_flags"].outcome == "no order from the full method"
    assert report["only_flags"].full is None
    assert (
        "holds no 'soil_loss' of scenario 'only_flags'"
        in report["only_flags"].full_reason
    )
    assert (
        report["only_flags"].trivial_rotations_ordered,
        report["only_flags"].full_rotations_ordered,
    ) == (2, 0)

    assert report["only_table"].outcome == "no order from the trivial comparator"
    assert report["only_table"].trivial.order is None
    assert (
        "hold no rotation of scenario 'only_table'"
        in report["only_table"].trivial.reason
    )
    assert (
        report["only_table"].trivial_rotations_ordered,
        report["only_table"].full_rotations_ordered,
    ) == (0, 2)

    # Reverse rotation mismatch: table holds C in addition to A, B.
    extra_table = _table(
        [
            _soil_row("A", "both", 2020, 1.0),
            _soil_row("B", "both", 2020, 5.0),
            _soil_row("C", "both", 2020, 3.0),
        ]
    )
    with pytest.raises(ValueError, match="same rotations"):
        compare_with_soil_loss(
            {k: v for k, v in living.items() if k[1] == "both"},
            _EROSIVITY_WEIGHTED,
            extra_table,
            start_month=7,
        )


def test_e0_compare_with_soil_loss_multiple_scenarios_independent():
    living = {
        ("A", "p1"): _day_flags(
            dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1, 2, 3, 4}
        ),
        ("B", "p1"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {7, 8}),
        ("A", "p2"): _day_flags(dt.date(2020, 7, 1), dt.date(2021, 6, 30), {7, 8}),
        ("B", "p2"): _day_flags(
            dt.date(2020, 7, 1), dt.date(2021, 6, 30), {1, 2, 3, 4}
        ),
    }
    rows = [
        _soil_row("A", "p1", 2020, 1.0),
        _soil_row("B", "p1", 2020, 5.0),
        _soil_row("A", "p2", 2020, 1.0),
        _soil_row("B", "p2", 2020, 5.0),
    ]
    report = {
        item.scenario_id: item
        for item in compare_with_soil_loss(
            living, _EROSIVITY_WEIGHTED, _table(rows), start_month=7
        )
    }
    assert report["p1"].outcome == "equal"
    assert report["p2"].outcome == "different"


# === 3. validation/trivial_comparator_water.py ===============================


def _wdays(
    entries: list[tuple[float | Missing, float | Missing]], year: int = 2020
) -> tuple[WaterDay, ...]:
    start = dt.date(year, 5, 1)
    return tuple(
        WaterDay(start + dt.timedelta(days=i), precip, demand)
        for i, (precip, demand) in enumerate(entries)
    )


def test_h0_year_ratio_empty_zero_precip_and_non_finite_cases():
    empty = year_ratio("A", "s1", 2020, ())
    assert empty.ratio is None
    assert empty.missing.reason == "NOT_APPLICABLE"
    assert empty.crop_days == 0

    zero_precip = year_ratio("A", "s1", 2020, _wdays([(0.0, 4.0), (0.0, 4.0)]))
    assert zero_precip.ratio == 0.0
    assert zero_precip.missing is None
    assert zero_precip.crop_days == 2

    cancelling_demand = year_ratio("A", "s1", 2020, _wdays([(3.0, -4.0), (2.0, 4.0)]))
    assert cancelling_demand.ratio is None
    assert cancelling_demand.missing.reason == "NOT_COMPUTABLE"
    assert cancelling_demand.crop_days == 2

    overflow = year_ratio("A", "s1", 2020, _wdays([(1e308, 1e-308)]))
    assert overflow.ratio is None
    assert overflow.missing.reason == "NOT_COMPUTABLE"
    assert overflow.crop_days == 1


def test_h0_year_ratio_checks_demanded_missing_before_precipitation_missing():
    # Day 1 has missing precipitation; Day 2 has missing demanded transpiration.
    # EP3 checks demanded transpiration missingness before precipitation missingness.
    rain_missing = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER rain")
    demand_missing = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER demand")
    ratio = year_ratio(
        "A",
        "s1",
        2020,
        _wdays([(rain_missing, 4.0), (2.0, demand_missing)]),
    )
    assert ratio.ratio is None
    assert ratio.missing.reason == "NOT_DECLARED"
    assert ratio.crop_days == 0


def test_h0_year_ratio_uses_fsum_to_avoid_catastrophic_cancellation():
    supplied_cancel = year_ratio(
        "A",
        "s1",
        2020,
        _wdays([(1e40, 1.0), (1e20, 1.0), (1.0, 1.0), (-1e40, 1.0), (-1e20, 1.0)]),
    )
    assert supplied_cancel.ratio == pytest.approx(1.0 / 5.0)

    demand_cancel = year_ratio(
        "A",
        "s1",
        2020,
        _wdays([(1.0, 1e40), (1.0, 1e20), (1.0, 1.0), (1.0, -1e40), (1.0, -1e20)]),
    )
    assert demand_cancel.ratio == pytest.approx(5.0)
    assert demand_cancel.missing is None


def test_h0_water_orders_empty_not_computable_and_partial_tie():
    assert water_orders({}) == ()

    series_nc = {
        ("A", "s1", 2020): _wdays([(2.0, 0.0)]),
        ("B", "s1", 2020): _wdays([(2.0, 4.0)]),
    }
    (order_nc,) = water_orders(series_nc)
    assert order_nc.order is None
    assert order_nc.means is None
    assert "NOT_COMPUTABLE" in order_nc.reason

    series_tie = {
        ("A", "s1", 2020): _wdays([(2.0, 4.0)]),
        ("B", "s1", 2020): _wdays([(2.0, 4.0)]),
        ("C", "s1", 2020): _wdays([(4.0, 4.0)]),
    }
    (order_tie,) = water_orders(series_tie)
    assert order_tie.order is None
    assert order_tie.means is not None
    assert "'A' and 'B'" in order_tie.reason


def test_h0_compare_with_full_indicator_unmatched_scenario_subset_both_none_and_soil_ignored():
    series = {
        ("A", "only_series", 2020): _wdays([(4.0, 4.0)]),
        ("B", "only_series", 2020): _wdays([(2.0, 4.0)]),
        ("A", "subset_mismatch", 2020): _wdays([(4.0, 4.0)]),
        ("B", "subset_mismatch", 2020): _wdays([(2.0, 4.0)]),
        ("A", "both_none", 2020): _wdays([(2.0, 4.0)]),
        ("B", "both_none", 2020): _wdays([(2.0, 4.0)]),
        ("A", "diff", 2020): _wdays([(1.0, 4.0)]),
        ("B", "diff", 2020): _wdays([(3.0, 4.0)]),
    }
    rows = [
        # subset_mismatch has A, B, C in table (A, B in series -> subset)
        _water_row("A", "subset_mismatch", 2020, 0.9),
        _water_row("B", "subset_mismatch", 2020, 0.7),
        _water_row("C", "subset_mismatch", 2020, 0.5),
        # both_none: trivial ties and full ties
        _water_row("A", "both_none", 2020, 0.6),
        _water_row("B", "both_none", 2020, 0.6),
        _water_row("C", "both_none", 2020, 0.6),
        # diff: trivial B, A; full A, B
        _water_row("A", "diff", 2020, 0.9),
        _water_row("B", "diff", 2020, 0.5),
        _water_row("C", "diff", 2020, 0.1),
        # soil_loss rows in same scenarios and in a soil_only scenario must be ignored
        _soil_row("A", "only_series", 2020, 1.0),
        _soil_row("B", "only_series", 2020, 2.0),
        _soil_row("C", "only_series", 2020, 3.0),
        _soil_row("A", "soil_only", 2020, 1.0),
        _soil_row("B", "soil_only", 2020, 2.0),
        _soil_row("C", "soil_only", 2020, 3.0),
    ]
    # Add missing water rows for remaining rotations/scenarios? Wait: ResultsTable
    # requires all rotations in a table to have the exact same cells, so let's build
    # separate minimal tables or include A, B, C uniformly per test scenario.
    # For clean ResultsTable cells, keep A, B, C consistent across scenarios:
    rows.extend(
        [
            _water_row("C", "diff", 2020, 0.1)
            for _ in ()  # already added above
        ]
    )
    # Use individual valid tables for subset_mismatch & only_series & both_none & diff
    t_only_series = _table(
        [
            _soil_row("A", "only_series", 2020, 1.0),
            _soil_row("B", "only_series", 2020, 2.0),
            _soil_row("A", "soil_only", 2020, 1.0),
            _soil_row("B", "soil_only", 2020, 2.0),
        ]
    )
    (item_os,) = compare_with_full_indicator(
        {k: v for k, v in series.items() if k[1] == "only_series"}, t_only_series
    )
    assert item_os.scenario_id == "only_series"
    assert item_os.outcome == "no order from the full indicator"
    assert item_os.full.order is None
    assert "holds no row of 'water_deficit_exposure'" in item_os.full.reason
    assert (item_os.rotations_ordered, item_os.rotations_ordered_full) == (2, 0)

    t_subset = _table(
        [
            _water_row("A", "subset_mismatch", 2020, 0.9),
            _water_row("B", "subset_mismatch", 2020, 0.7),
            _water_row("C", "subset_mismatch", 2020, 0.5),
        ]
    )
    (item_sub,) = compare_with_full_indicator(
        {k: v for k, v in series.items() if k[1] == "subset_mismatch"}, t_subset
    )
    assert item_sub.outcome == "not the same rotations"
    assert (item_sub.rotations_ordered, item_sub.rotations_ordered_full) == (2, 3)

    # Reverse subset: trivial has A, B, C; full has A, B.
    series_sup = {
        ("A", "sup", 2020): _wdays([(6.0, 4.0)]),
        ("B", "sup", 2020): _wdays([(4.0, 4.0)]),
        ("C", "sup", 2020): _wdays([(2.0, 4.0)]),
    }
    t_sub_full = _table(
        [
            _water_row("A", "sup", 2020, 0.9),
            _water_row("B", "sup", 2020, 0.7),
        ]
    )
    (item_sup,) = compare_with_full_indicator(series_sup, t_sub_full)
    assert item_sup.outcome == "not the same rotations"
    assert (item_sup.rotations_ordered, item_sup.rotations_ordered_full) == (3, 2)

    t_both_none = _table(
        [
            _water_row("A", "both_none", 2020, 0.6),
            _water_row("B", "both_none", 2020, 0.6),
        ]
    )
    (item_bn,) = compare_with_full_indicator(
        {k: v for k, v in series.items() if k[1] == "both_none"}, t_both_none
    )
    assert item_bn.outcome == "no order from either"
    assert (item_bn.rotations_ordered, item_bn.rotations_ordered_full) == (0, 0)

    t_diff = _table(
        [
            _water_row("A", "diff", 2020, 0.9),
            _water_row("B", "diff", 2020, 0.5),
        ]
    )
    (item_diff,) = compare_with_full_indicator(
        {k: v for k, v in series.items() if k[1] == "diff"}, t_diff
    )
    assert item_diff.outcome == "different"
    assert (item_diff.rotations_ordered, item_diff.rotations_ordered_full) == (2, 2)


# === 4. validation/order_between_systems.py ===================================


def test_e2_checked_expected_rejects_bytes_sets_dicts_none_elements_and_accepts_list():
    for bad in (b"", b"CAB", {"C", "A", "B"}, {"C": 1, "A": 2}, 123, ("C", None, "B")):
        with pytest.raises(TypeError, match="expected"):
            compare_with_expected_order(
                _table(
                    [_soil_row("A", "p1", 2020, 1.0), _soil_row("B", "p1", 2020, 2.0)]
                ),
                bad,
            )

    (item,) = compare_with_expected_order(
        _table([_soil_row("A", "p1", 2020, 1.0), _soil_row("B", "p1", 2020, 2.0)]),
        ["A", "B"],
    )
    assert item.expected == ("A", "B")
    assert item.outcome == "equal"


def test_e2_rotation_mismatch_takes_precedence_over_no_order_from_full_method():
    # Tie in soil_loss AND different rotation set in expected -> "not compared".
    tied_table = _table(
        [
            _soil_row("A", "p1", 2020, 2.0),
            _soil_row("B", "p1", 2020, 2.0),
        ]
    )
    (item_tie,) = compare_with_expected_order(tied_table, ("A", "C"))
    assert item_tie.outcome == "not compared"
    assert item_tie.rotations_ordered == 0

    # Single rotation in table AND two rotations in expected -> "not compared".
    single_table = _table([_soil_row("A", "p1", 2020, 2.0)])
    (item_single,) = compare_with_expected_order(single_table, ("A", "B"))
    assert item_single.outcome == "not compared"
    assert item_single.rotations_ordered == 0


def test_e2_multi_scenario_mixed_outcomes():
    rows = [
        _soil_row("A", "p1_equal", 2020, 1.0),
        _soil_row("B", "p1_equal", 2020, 3.0),
        _soil_row("A", "p2_diff", 2020, 3.0),
        _soil_row("B", "p2_diff", 2020, 1.0),
        _soil_row("A", "p3_tie", 2020, 2.0),
        _soil_row("B", "p3_tie", 2020, 2.0),
    ]
    report = {
        item.scenario_id: item
        for item in compare_with_expected_order(_table(rows), ("A", "B"))
    }
    assert report["p1_equal"].outcome == "equal"
    assert report["p2_diff"].outcome == "different"
    assert report["p3_tie"].outcome == "no order from the full method"
