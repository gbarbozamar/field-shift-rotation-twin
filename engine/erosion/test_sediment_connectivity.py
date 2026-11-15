"""Tests for Frontier Unit F-03: Borselli sediment connectivity (IC).

Covers:
- Exact Borselli et al. (2008) analytical calculations (1D slope, diagonal D8
  steepest-descent vs drop-only disambiguation, convergent 2D catchment, and
  ``min_slope`` flooring);
- Monotonicity in weight ``W``, slope ``S``, proximity to target, and resolution
  scaling across DEM sources (e.g. ``"IDE_MDT_2_5M"`` vs ``"NASADEM_30M"``);
- D8 flat, internal sink, tie (``FlatTiePolicy.FAIL`` vs
  ``FlatTiePolicy.FIRST_BY_ORDER``), target-unreachable, and cycle guards;
- Missing-data and masking semantics (``NO_COVERAGE``, ``MISSING_INPUT`` for
  non-finite elevation/weight and upslope/downslope propagation, ``NOT_APPLICABLE``
  on targets, ``NOT_COMPUTABLE`` on non-positive weights);
- Rev13 guards (``is_exported_sediment_mass=False``,
  ``indicator_kind="RELATIVE_HOTSPOT_CONNECTIVITY"``, external hydrologic buffer
  warning/flag, no multiplication into ``A_norm``, zero invented defaults);
- G1 purity, frozen dataclass immutability, AST dependency hygiene, and G5
  caller-defect validation.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import inspect
import math
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion import sediment_connectivity as sc
from engine.erosion.sediment_connectivity import (
    INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY,
    ConnectivityGridResult,
    FlatTiePolicy,
    _accumulate_connectivity_from_directions,
    _CellStatus,
    compute_sediment_connectivity,
)

MODULE_PATH = Path(sc.__file__).resolve()
FLOAT_TOL = 1e-12


def _run(
    *,
    elevation_grid,
    weight_grid,
    target_mask,
    cell_size_m=10.0,
    min_slope=0.005,
    dem_source="IDE_MDT_2_5M",
    has_external_hydrologic_buffer=True,
    flat_tie_policy=FlatTiePolicy.FAIL,
    coverage_mask=None,
) -> ConnectivityGridResult:
    """Invoke ``compute_sediment_connectivity`` with explicit test fixtures."""
    return compute_sediment_connectivity(
        elevation_grid=elevation_grid,
        weight_grid=weight_grid,
        cell_size_m=cell_size_m,
        target_mask=target_mask,
        min_slope=min_slope,
        dem_source=dem_source,
        has_external_hydrologic_buffer=has_external_hydrologic_buffer,
        flat_tie_policy=flat_tie_policy,
        coverage_mask=coverage_mask,
    )


# ---------------------------------------------------------------------------
# 1. Exact Borselli (2008) analytical calculations & D8 geometry
# ---------------------------------------------------------------------------


def test_1d_cardinal_slope_exact_borselli_values() -> None:
    """Verify exact D_up, D_dn, contributing area, and IC on a 3x1 cardinal slope."""
    elev = [[12.0], [11.0], [10.0]]
    weights = [[0.5], [0.5], [0.5]]
    targets = [[False], [False], [True]]

    res = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        cell_size_m=10.0,
        min_slope=0.005,
    )

    assert res.n_rows == 3
    assert res.n_cols == 1
    assert res.flow_direction_grid == (((1, 0),), ((2, 0),), (None,))

    # Row 0: n_up=1, A=100, W_bar=0.5, S_bar=0.1 -> D_up=0.5, D_dn=200+200=400
    assert res.contributing_area_m2_grid[0][0] == pytest.approx(100.0, abs=FLOAT_TOL)
    assert res.d_up_grid[0][0] == pytest.approx(0.5, abs=FLOAT_TOL)
    assert res.d_dn_grid[0][0] == pytest.approx(400.0, abs=FLOAT_TOL)
    assert res.ic_grid[0][0] == pytest.approx(math.log10(0.5 / 400.0), abs=FLOAT_TOL)

    # Row 1: n_up=2, A=200, D_up=0.5*0.1*sqrt(200), D_dn=200
    expected_d_up_1 = 0.5 * 0.1 * math.sqrt(200.0)
    assert res.contributing_area_m2_grid[1][0] == pytest.approx(200.0, abs=FLOAT_TOL)
    assert res.d_up_grid[1][0] == pytest.approx(expected_d_up_1, abs=FLOAT_TOL)
    assert res.d_dn_grid[1][0] == pytest.approx(200.0, abs=FLOAT_TOL)
    assert res.ic_grid[1][0] == pytest.approx(
        math.log10(expected_d_up_1 / 200.0), abs=FLOAT_TOL
    )

    # Row 2 (target): contributing area is 300, D_dn is 0.0, IC/D_up are NOT_APPLICABLE
    assert res.contributing_area_m2_grid[2][0] == pytest.approx(300.0, abs=FLOAT_TOL)
    assert res.d_dn_grid[2][0] == 0.0
    assert isinstance(res.ic_grid[2][0], ResultMissing)
    assert res.ic_grid[2][0].reason == "NOT_APPLICABLE"
    assert isinstance(res.d_up_grid[2][0], ResultMissing)
    assert res.d_up_grid[2][0].reason == "NOT_APPLICABLE"

    # Downslope cell closer to outlet with higher contributing area has higher IC
    assert res.ic_grid[1][0] > res.ic_grid[0][0]  # type: ignore[operator]


def test_diagonal_vs_cardinal_steepest_descent_uses_distance() -> None:
    """Diagonal step divides drop by sqrt(2)*cell_size_m, so cardinal wins equal drops."""
    # From (0, 0) at z=10.0:
    # - South neighbor (1, 0) has z=8.8 -> drop=1.2, d=10 -> slope=0.12
    # - SE neighbor (1, 1) has z=8.6 -> drop=1.4, d=10*sqrt(2) -> slope=1.4/14.1421 < 0.10
    # Steepest descent MUST choose South (1, 0), not SE (1, 1) despite larger drop!
    elev = [
        [10.0, 11.0],
        [8.8, 8.6],
    ]
    weights = [
        [0.4, 0.4],
        [0.4, 0.4],
    ]
    targets = [
        [False, False],
        [True, True],
    ]

    res = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        cell_size_m=10.0,
        min_slope=0.005,
    )
    assert res.flow_direction_grid[0][0] == (1, 0)

    # Now make SE much lower so diagonal genuinely has steepest slope:
    # SE z=7.0 -> drop=3.0, slope=3.0/(10*sqrt(2)) ≈ 0.2121 > 0.12
    elev_diag = [
        [10.0, 11.0],
        [8.8, 7.0],
    ]
    res_diag = _run(
        elevation_grid=elev_diag,
        weight_grid=weights,
        target_mask=targets,
        cell_size_m=10.0,
        min_slope=0.005,
    )
    assert res_diag.flow_direction_grid[0][0] == (1, 1)

    d_diag = 10.0 * math.sqrt(2.0)
    s_diag = 3.0 / d_diag
    expected_d_up = 0.4 * s_diag * math.sqrt(100.0)
    expected_d_dn = d_diag / (0.4 * s_diag)
    assert res_diag.d_up_grid[0][0] == pytest.approx(expected_d_up, abs=FLOAT_TOL)
    assert res_diag.d_dn_grid[0][0] == pytest.approx(expected_d_dn, abs=FLOAT_TOL)
    assert res_diag.ic_grid[0][0] == pytest.approx(
        math.log10(expected_d_up / expected_d_dn), abs=FLOAT_TOL
    )


def test_convergent_2d_catchment_topological_accumulation() -> None:
    """Verify exact W_bar, S_bar, and contributing area where two branches merge."""
    # Layout (cell_size_m = 5.0, min_slope = 0.001):
    # (0,0) z=15, W=0.2  \
    #                     -> (1,1) z=10, W=0.6 -> (2,1) target z=5, W=0.5
    # (0,2) z=20, W=0.4  /
    # Other cells are higher ridges draining to (1,1) or direct to target;
    # keep a clean 3x3 basin where (0,1) z=30 drains South to (1,1),
    # (1,0) z=30 drains East to (1,1), (1,2) z=30 drains West to (1,1),
    # and corners/bottom drain cleanly.
    elev = [
        [15.0, 30.0, 20.0],
        [12.0, 10.0, 12.0],
        [11.0, 5.0, 11.0],
    ]
    # Note:
    # (0,0) z=15: neighbors (0,1)=30, (1,0)=12 (dz=3, d=5, s=0.6), (1,1)=10 (dz=5, d=5*sqrt2, s=0.7071) -> goes to (1,1)!
    # (0,1) z=30: (1,1)=10 (dz=20, d=5, s=4.0) -> goes to (1,1)!
    # (0,2) z=20: (1,1)=10 (dz=10, d=5*sqrt2, s=sqrt2=1.4142), (1,2)=12 (dz=8, d=5, s=1.6) -> goes to (1,2)!
    # Let's raise (1,0) and (1,2) so (0,0), (0,1), (0,2) all flow directly to (1,1),
    # and (1,0), (1,2) flow directly to target (2,1), while (2,0), (2,2) flow to (2,1).
    elev = [
        [15.0, 30.0, 20.0],
        [25.0, 10.0, 25.0],
        [6.0, 5.0, 6.0],
    ]
    # Check (1,0) z=25: neighbors (0,0)=15 (dz=10, d=5, s=2.0), (1,1)=10 (dz=15, d=5, s=3.0), (2,0)=6 (dz=19, d=5, s=3.8) -> (2,0)
    # To make a clean 3-cell funnel into (1,1), set target only at (2,1) and test (1,1):
    # Wait: (0,0)=15 -> (1,1)=10 (s=5/(5sqrt2)=1/sqrt2=0.7071)
    # (0,1)=30 -> (1,1)=10 (s=20/5=4.0)
    # (0,2)=20 -> (1,1)=10 (s=10/(5sqrt2)=sqrt2=1.4142)
    # (1,0)=14 -> (2,0)=6 (s=1.6), etc. So ONLY (0,0), (0,1), (0,2) enter (1,1)!
    weights = [
        [0.2, 0.3, 0.4],
        [0.5, 0.6, 0.5],
        [0.5, 0.5, 0.5],
    ]
    targets = [
        [False, False, False],
        [False, False, False],
        [False, True, False],
    ]
    res = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        cell_size_m=5.0,
        min_slope=0.001,
    )

    assert res.flow_direction_grid[0][0] == (1, 1)
    assert res.flow_direction_grid[0][1] == (1, 1)
    assert res.flow_direction_grid[0][2] == (1, 1)
    assert res.flow_direction_grid[1][1] == (2, 1)

    # Upslope set of (1,1) is {(0,0), (0,1), (0,2), (1,1)} -> 4 cells * 25 m^2 = 100 m^2
    assert res.contributing_area_m2_grid[1][1] == pytest.approx(100.0, abs=FLOAT_TOL)

    s_00 = (15.0 - 10.0) / (5.0 * math.sqrt(2.0))
    s_01 = (30.0 - 10.0) / 5.0
    s_02 = (20.0 - 10.0) / (5.0 * math.sqrt(2.0))
    s_11 = (10.0 - 5.0) / 5.0
    w_bar = (0.2 + 0.3 + 0.4 + 0.6) / 4.0
    s_bar = (s_00 + s_01 + s_02 + s_11) / 4.0
    d_up_11 = w_bar * s_bar * math.sqrt(100.0)
    d_dn_11 = 5.0 / (0.6 * s_11)

    assert res.d_up_grid[1][1] == pytest.approx(d_up_11, abs=FLOAT_TOL)
    assert res.d_dn_grid[1][1] == pytest.approx(d_dn_11, abs=FLOAT_TOL)
    assert res.ic_grid[1][1] == pytest.approx(
        math.log10(d_up_11 / d_dn_11), abs=FLOAT_TOL
    )


def test_min_slope_floor_clamps_gentle_gradients_after_routing() -> None:
    """Gentle positive slopes below ``min_slope`` route normally and clamp to ``min_slope``."""
    # raw_slope = 0.001 / 10.0 = 0.0001 < min_slope = 0.01
    elev = [[10.002], [10.001], [10.0]]
    weights = [[0.5], [0.5], [0.5]]
    targets = [[False], [False], [True]]

    res = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        cell_size_m=10.0,
        min_slope=0.01,
    )
    # Expect S_0 = S_1 = 0.01 (not 0.0001)
    expected_d_up_0 = 0.5 * 0.01 * math.sqrt(100.0)
    expected_d_dn_0 = 2.0 * (10.0 / (0.5 * 0.01))
    assert res.d_up_grid[0][0] == pytest.approx(expected_d_up_0, abs=FLOAT_TOL)
    assert res.d_dn_grid[0][0] == pytest.approx(expected_d_dn_0, abs=FLOAT_TOL)
    assert res.ic_grid[0][0] == pytest.approx(
        math.log10(expected_d_up_0 / expected_d_dn_0), abs=FLOAT_TOL
    )


# ---------------------------------------------------------------------------
# 2. Monotonicity & DEM resolution metadata
# ---------------------------------------------------------------------------


def test_ic_monotonic_in_weight_and_slope() -> None:
    """Increasing W or slope strictly increases IC."""
    targets = [[False], [False], [True]]
    base = _run(
        elevation_grid=[[12.0], [11.0], [10.0]],
        weight_grid=[[0.2], [0.2], [0.2]],
        target_mask=targets,
    )
    higher_w = _run(
        elevation_grid=[[12.0], [11.0], [10.0]],
        weight_grid=[[0.6], [0.6], [0.6]],
        target_mask=targets,
    )
    steeper = _run(
        elevation_grid=[[16.0], [13.0], [10.0]],
        weight_grid=[[0.2], [0.2], [0.2]],
        target_mask=targets,
    )

    assert higher_w.ic_grid[0][0] > base.ic_grid[0][0]  # type: ignore[operator]
    assert steeper.ic_grid[0][0] > base.ic_grid[0][0]  # type: ignore[operator]


def test_dem_source_metadata_and_cell_size_scaling() -> None:
    """DEM source metadata travels cleanly and IC is scale-invariant for fixed slopes."""
    targets = [[False], [False], [True]]
    # Same slopes (0.1) at 2.5m vs 30m: elevations scaled proportionally to cell_size_m.
    fine = _run(
        elevation_grid=[[10.5], [10.25], [10.0]],
        weight_grid=[[0.4], [0.4], [0.4]],
        target_mask=targets,
        cell_size_m=2.5,
        dem_source="IDE_MDT_2_5M",
    )
    coarse = _run(
        elevation_grid=[[16.0], [13.0], [10.0]],
        weight_grid=[[0.4], [0.4], [0.4]],
        target_mask=targets,
        cell_size_m=30.0,
        dem_source="NASADEM_30M",
    )
    assert fine.dem_source == "IDE_MDT_2_5M"
    assert fine.cell_size_m == 2.5
    assert coarse.dem_source == "NASADEM_30M"
    assert coarse.cell_size_m == 30.0
    assert fine.ic_grid[0][0] == pytest.approx(coarse.ic_grid[0][0], abs=FLOAT_TOL)


# ---------------------------------------------------------------------------
# 3. Flat, sink, tie, unreachable target, and cycle guards
# ---------------------------------------------------------------------------


def test_internal_sink_and_upslope_cells_return_not_computable() -> None:
    """An internal sink and all cells draining to it fail with NOT_COMPUTABLE."""
    # (0,0)=12 -> (0,1)=9 (internal sink!), while (0,2)=10 -> (0,3)=2 (target)
    elev = [[12.0, 9.0, 10.0, 2.0]]
    weights = [[0.5, 0.5, 0.5, 0.5]]
    targets = [[False, False, False, True]]

    res = _run(elevation_grid=elev, weight_grid=weights, target_mask=targets)

    # Sink (0,1) has no lower neighbor
    assert isinstance(res.ic_grid[0][1], ResultMissing)
    assert res.ic_grid[0][1].reason == "NOT_COMPUTABLE"
    assert isinstance(res.d_up_grid[0][1], ResultMissing)
    assert res.d_up_grid[0][1].reason == "NOT_COMPUTABLE"
    assert isinstance(res.d_dn_grid[0][1], ResultMissing)
    assert res.d_dn_grid[0][1].reason == "NOT_COMPUTABLE"

    # (0,0) drains into sink (0,1), so target is unreachable
    assert isinstance(res.ic_grid[0][0], ResultMissing)
    assert res.ic_grid[0][0].reason == "NOT_COMPUTABLE"
    assert isinstance(res.d_dn_grid[0][0], ResultMissing)
    assert res.d_dn_grid[0][0].reason == "NOT_COMPUTABLE"
    # Local D_up at (0,0) is still defined since (0,0) has a downslope step to (0,1)
    assert isinstance(res.d_up_grid[0][0], float)

    # (0,2) cleanly reaches target (0,3)
    assert isinstance(res.ic_grid[0][2], float)


def test_flat_plateau_returns_not_computable() -> None:
    """Equal-elevation plateau with no strictly lower neighbor returns NOT_COMPUTABLE."""
    elev = [[10.0, 10.0, 10.0]]
    weights = [[0.5, 0.5, 0.5]]
    targets = [[False, False, True]]

    res_fail = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        flat_tie_policy=FlatTiePolicy.FAIL,
    )
    res_order = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        flat_tie_policy=FlatTiePolicy.FIRST_BY_ORDER,
    )

    for res in (res_fail, res_order):
        for col in (0, 1):
            assert isinstance(res.ic_grid[0][col], ResultMissing)
            assert res.ic_grid[0][col].reason == "NOT_COMPUTABLE"


def test_steepest_descent_tie_policies() -> None:
    """FlatTiePolicy.FAIL rejects tied steepest slopes; FIRST_BY_ORDER breaks deterministically."""
    # From (0,1) z=15: West (0,0) z=10 and East (0,2) z=10 have slope 0.5,
    # steeper than diagonals (1,0)=9 and (1,2)=9 (slope 6/(10*sqrt2) ~= 0.424).
    # (0,0) flows South to target (1,0); (0,2) flows South to target (1,2).
    elev = [
        [10.0, 15.0, 10.0],
        [9.0, 20.0, 9.0],
    ]
    weights = [
        [0.5, 0.5, 0.5],
        [0.5, 0.5, 0.5],
    ]
    targets = [
        [False, False, False],
        [True, False, True],
    ]

    res_fail = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        flat_tie_policy=FlatTiePolicy.FAIL,
    )
    assert isinstance(res_fail.ic_grid[0][1], ResultMissing)
    assert res_fail.ic_grid[0][1].reason == "NOT_COMPUTABLE"
    assert res_fail.flow_direction_grid[0][1] is None
    # (0,0) and (0,2) still compute cleanly
    assert isinstance(res_fail.ic_grid[0][0], float)
    assert isinstance(res_fail.ic_grid[0][2], float)

    # Under FIRST_BY_ORDER, clockwise from North visits East (0, 1) before West (0, -1).
    res_order = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        flat_tie_policy=FlatTiePolicy.FIRST_BY_ORDER,
    )
    assert res_order.flow_direction_grid[0][1] == (0, 2)
    assert isinstance(res_order.ic_grid[0][1], float)


def test_no_targets_in_grid_makes_all_cells_not_computable() -> None:
    """When target_mask has no True cells, all hillslope cells are NOT_COMPUTABLE."""
    res = _run(
        elevation_grid=[[12.0, 11.0], [10.0, 9.0]],
        weight_grid=[[0.5, 0.5], [0.5, 0.5]],
        target_mask=[[False, False], [False, False]],
    )
    for r in range(2):
        for c in range(2):
            assert isinstance(res.ic_grid[r][c], ResultMissing)
            assert res.ic_grid[r][c].reason == "NOT_COMPUTABLE"


def test_cycle_guard_handles_cyclic_direction_graph() -> None:
    """Cycle guard detects cycles in directed flow graphs and flags cycle + feeders."""
    cells = [
        [
            _CellStatus(True, None, 10.0, None, 0.5, None, None, False),
            _CellStatus(True, None, 10.0, None, 0.5, None, None, False),
        ],
        [
            _CellStatus(True, None, 12.0, None, 0.5, None, None, False),
            _CellStatus(True, None, 5.0, None, 0.5, None, None, True),
        ],
    ]
    # Synthetic cycle: (0,0) <-> (0,1), and (1,0) -> (0,0)
    next_cell = [
        [(0, 1), (0, 0)],
        [(0, 0), None],
    ]
    slope_i = [
        [0.1, 0.1],
        [0.2, None],
    ]
    step_dist = [
        [10.0, 10.0],
        [10.0, None],
    ]
    route_issue = [
        [None, None],
        [None, None],
    ]

    res = _accumulate_connectivity_from_directions(
        cells=cells,
        next_cell=next_cell,
        slope_i=slope_i,
        step_dist=step_dist,
        route_issue=route_issue,
        n_rows=2,
        n_cols=2,
        cell_size_m=10.0,
        min_slope=0.005,
        dem_source="SYNTHETIC_CYCLE_TEST",
        has_external_hydrologic_buffer=True,
    )

    for coord in ((0, 0), (0, 1), (1, 0)):
        r, c = coord
        cell_ic = res.ic_grid[r][c]
        assert isinstance(cell_ic, ResultMissing)
        assert cell_ic.reason == "NOT_COMPUTABLE"
        assert cell_ic.detail is not None and "cycle" in cell_ic.detail.lower()


# ---------------------------------------------------------------------------
# 4. Coverage masking & missing/non-finite inputs
# ---------------------------------------------------------------------------


def test_coverage_mask_and_no_coverage_missing_cells() -> None:
    """Masked cells yield NO_COVERAGE and block routing into masked terrain."""
    elev = [
        [12.0, 11.0, 10.0],
        [12.0, 11.0, 10.0],
    ]
    weights = [
        [0.5, 0.5, 0.5],
        [0.5, 0.5, 0.5],
    ]
    targets = [
        [False, False, True],
        [False, False, True],
    ]
    coverage = [
        [True, False, True],
        [True, True, True],
    ]

    res = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        coverage_mask=coverage,
    )

    # (0,1) is masked -> NO_COVERAGE across all output grids
    for grid in (
        res.ic_grid,
        res.d_up_grid,
        res.d_dn_grid,
        res.contributing_area_m2_grid,
    ):
        item = grid[0][1]
        assert isinstance(item, ResultMissing)
        assert item.reason == "NO_COVERAGE"
    assert res.flow_direction_grid[0][1] is None

    # (0,0) cannot route East into masked (0,1); its steepest valid neighbor is SE (1,1)
    assert res.flow_direction_grid[0][0] == (1, 1)
    assert isinstance(res.ic_grid[0][0], float)

    # Also verify InputMissing/ResultMissing with NO_COVERAGE inside grid cells
    elev_with_nocov = [
        [12.0, InputMissing(reason="NO_COVERAGE"), 10.0],
    ]
    res_nocov = _run(
        elevation_grid=elev_with_nocov,
        weight_grid=[[0.5, 0.5, 0.5]],
        target_mask=[[False, False, True]],
    )
    assert isinstance(res_nocov.ic_grid[0][1], ResultMissing)
    assert res_nocov.ic_grid[0][1].reason == "NO_COVERAGE"
    # (0,0) now has no valid lower neighbor -> NOT_COMPUTABLE
    assert isinstance(res_nocov.ic_grid[0][0], ResultMissing)
    assert res_nocov.ic_grid[0][0].reason == "NOT_COMPUTABLE"


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_non_finite_elevation_produces_missing_input(bad_value: float) -> None:
    """Non-finite elevation on a cell yields MISSING_INPUT on that cell."""
    res = _run(
        elevation_grid=[[bad_value, 11.0, 10.0]],
        weight_grid=[[0.5, 0.5, 0.5]],
        target_mask=[[False, False, True]],
    )
    assert isinstance(res.ic_grid[0][0], ResultMissing)
    assert res.ic_grid[0][0].reason == "MISSING_INPUT"
    assert isinstance(res.ic_grid[0][1], float)


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_non_finite_weight_propagates_missing_input_along_paths(
    bad_value: float,
) -> None:
    """Non-finite weight yields MISSING_INPUT and propagates upslope & downslope."""
    # Chain: (0,0) -> (0,1) -> (0,2) -> (0,3) target
    # Put bad_value at (0,1):
    # - (0,1) itself is MISSING_INPUT
    # - (0,0) needs W(0,1) for D_dn -> D_dn and IC are MISSING_INPUT, D_up is valid!
    # - (0,2) needs W(0,1) for D_up -> D_up and IC are MISSING_INPUT, D_dn is valid!
    res = _run(
        elevation_grid=[[13.0, 12.0, 11.0, 10.0]],
        weight_grid=[[0.5, bad_value, 0.5, 0.5]],
        target_mask=[[False, False, False, True]],
    )

    assert isinstance(res.ic_grid[0][1], ResultMissing)
    assert res.ic_grid[0][1].reason == "MISSING_INPUT"

    assert isinstance(res.d_up_grid[0][0], float)
    assert isinstance(res.d_dn_grid[0][0], ResultMissing)
    assert res.d_dn_grid[0][0].reason == "MISSING_INPUT"
    assert isinstance(res.ic_grid[0][0], ResultMissing)
    assert res.ic_grid[0][0].reason == "MISSING_INPUT"

    assert isinstance(res.d_dn_grid[0][2], float)
    assert isinstance(res.d_up_grid[0][2], ResultMissing)
    assert res.d_up_grid[0][2].reason == "MISSING_INPUT"
    assert isinstance(res.ic_grid[0][2], ResultMissing)
    assert res.ic_grid[0][2].reason == "MISSING_INPUT"


def test_contract_missing_weight_and_non_positive_weight() -> None:
    """Contract Missing in weight yields MISSING_INPUT; W <= 0 yields NOT_COMPUTABLE."""
    res_miss = _run(
        elevation_grid=[[12.0, 11.0, 10.0]],
        weight_grid=[
            [InputMissing(reason="MISSING_INPUT", detail="C missing"), 0.5, 0.5]
        ],
        target_mask=[[False, False, True]],
    )
    assert isinstance(res_miss.ic_grid[0][0], ResultMissing)
    assert res_miss.ic_grid[0][0].reason == "MISSING_INPUT"
    assert isinstance(res_miss.ic_grid[0][1], ResultMissing)
    assert res_miss.ic_grid[0][1].reason == "MISSING_INPUT"

    for bad_w in (0.0, -0.25):
        res_nonpos = _run(
            elevation_grid=[[12.0, 11.0, 10.0]],
            weight_grid=[[0.5, bad_w, 0.5]],
            target_mask=[[False, False, True]],
        )
        assert isinstance(res_nonpos.ic_grid[0][0], ResultMissing)
        assert res_nonpos.ic_grid[0][0].reason == "NOT_COMPUTABLE"
        assert isinstance(res_nonpos.ic_grid[0][1], ResultMissing)
        assert res_nonpos.ic_grid[0][1].reason == "NOT_COMPUTABLE"


# ---------------------------------------------------------------------------
# 5. Rev13 guards, external buffer warning, & hygiene
# ---------------------------------------------------------------------------


def test_rev13_guards_and_external_buffer_warning() -> None:
    """ConnectivityGridResult marks relative hotspot connectivity and flags missing buffer."""
    elev = [[12.0, 11.0, 10.0]]
    weights = [[0.5, 0.5, 0.5]]
    targets = [[False, False, True]]

    res_no_buf = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        has_external_hydrologic_buffer=False,
    )
    assert res_no_buf.is_exported_sediment_mass is False
    assert res_no_buf.indicator_kind == INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY
    assert res_no_buf.indicator_kind == "RELATIVE_HOTSPOT_CONNECTIVITY"
    assert res_no_buf.has_external_hydrologic_buffer is False
    assert res_no_buf.external_buffer_warning is True
    assert len(res_no_buf.warnings) == 1
    assert "NO_EXTERNAL_HYDROLOGIC_BUFFER" in res_no_buf.warnings[0]

    res_with_buf = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        has_external_hydrologic_buffer=True,
    )
    assert res_with_buf.is_exported_sediment_mass is False
    assert res_with_buf.indicator_kind == "RELATIVE_HOTSPOT_CONNECTIVITY"
    assert res_with_buf.has_external_hydrologic_buffer is True
    assert res_with_buf.external_buffer_warning is False
    assert res_with_buf.warnings == ()

    # Guard cannot be bypassed on direct construction
    with pytest.raises(ValueError, match="is_exported_sediment_mass"):
        ConnectivityGridResult(
            ic_grid=res_with_buf.ic_grid,
            d_up_grid=res_with_buf.d_up_grid,
            d_dn_grid=res_with_buf.d_dn_grid,
            contributing_area_m2_grid=res_with_buf.contributing_area_m2_grid,
            flow_direction_grid=res_with_buf.flow_direction_grid,
            n_rows=1,
            n_cols=3,
            cell_size_m=10.0,
            min_slope=0.005,
            dem_source="IDE_MDT_2_5M",
            has_external_hydrologic_buffer=True,
            external_buffer_warning=False,
            warnings=(),
            is_exported_sediment_mass=True,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="indicator_kind"):
        ConnectivityGridResult(
            ic_grid=res_with_buf.ic_grid,
            d_up_grid=res_with_buf.d_up_grid,
            d_dn_grid=res_with_buf.d_dn_grid,
            contributing_area_m2_grid=res_with_buf.contributing_area_m2_grid,
            flow_direction_grid=res_with_buf.flow_direction_grid,
            n_rows=1,
            n_cols=3,
            cell_size_m=10.0,
            min_slope=0.005,
            dem_source="IDE_MDT_2_5M",
            has_external_hydrologic_buffer=True,
            external_buffer_warning=False,
            warnings=(),
            indicator_kind="EXPORTED_SEDIMENT_MASS",  # type: ignore[arg-type]
        )


def test_zero_invented_defaults_and_frozen_dataclasses() -> None:
    """Scientific/configuration arguments have no defaults and dataclasses are frozen."""
    sig = inspect.signature(compute_sediment_connectivity)
    required_no_default = {
        "elevation_grid",
        "weight_grid",
        "cell_size_m",
        "target_mask",
        "min_slope",
        "dem_source",
        "has_external_hydrologic_buffer",
        "flat_tie_policy",
    }
    for name in required_no_default:
        param = sig.parameters[name]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty

    res = _run(
        elevation_grid=[[12.0, 11.0, 10.0]],
        weight_grid=[[0.5, 0.5, 0.5]],
        target_mask=[[False, False, True]],
    )
    assert dataclasses.is_dataclass(res)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.dem_source = "OTHER"  # type: ignore[misc]


def test_g1_ast_purity_and_dependency_hygiene() -> None:
    """Module uses stdlib + contracts.* only, zero numpy/shapely/soil_loss/I/O."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_modules = {
        "numpy",
        "shapely",
        "os",
        "pathlib",
        "urllib",
        "socket",
        "http",
        "httpx",
        "requests",
        "time",
        "datetime",
        "subprocess",
        "warnings",
        "engine.erosion.soil_loss",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_modules
                assert alias.name not in forbidden_modules
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] not in forbidden_modules
            assert node.module not in forbidden_modules
        elif isinstance(node, ast.Name):
            assert node.id != "A_norm"
        elif isinstance(node, ast.Attribute):
            assert node.attr != "A_norm"

    assert "C:\\" not in source


# ---------------------------------------------------------------------------
# 6. G1 determinism/immutability & G5 caller-defect checks
# ---------------------------------------------------------------------------


def test_g1_determinism_and_argument_immutability() -> None:
    """Repeated calls produce identical outputs without mutating caller lists."""
    elev = [[14.0, 13.0], [11.0, 10.0]]
    weights = [[0.3, 0.4], [0.5, 0.6]]
    targets = [[False, False], [False, True]]
    coverage = [[True, True], [True, True]]

    elev_before = copy.deepcopy(elev)
    weights_before = copy.deepcopy(weights)
    targets_before = copy.deepcopy(targets)
    coverage_before = copy.deepcopy(coverage)

    r1 = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        coverage_mask=coverage,
    )
    r2 = _run(
        elevation_grid=elev,
        weight_grid=weights,
        target_mask=targets,
        coverage_mask=coverage,
    )

    assert r1 == r2
    assert elev == elev_before
    assert weights == weights_before
    assert targets == targets_before
    assert coverage == coverage_before


def test_g5_caller_defect_type_and_value_errors() -> None:
    """Invalid types and malformed grid shapes/scalars raise TypeError or ValueError."""
    valid_elev = [[12.0, 10.0]]
    valid_w = [[0.5, 0.5]]
    valid_t = [[False, True]]

    with pytest.raises(TypeError):
        _run(elevation_grid="bad", weight_grid=valid_w, target_mask=valid_t)
    with pytest.raises(TypeError):
        _run(elevation_grid=[[True, 10.0]], weight_grid=valid_w, target_mask=valid_t)
    with pytest.raises(TypeError):
        _run(elevation_grid=[[None, 10.0]], weight_grid=valid_w, target_mask=valid_t)
    with pytest.raises(TypeError):
        _run(elevation_grid=valid_elev, weight_grid=valid_w, target_mask=[[0, 1]])
    with pytest.raises(TypeError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            cell_size_m=True,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            dem_source=123,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            has_external_hydrologic_buffer=1,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            flat_tie_policy="fail",  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError):
        _run(elevation_grid=[], weight_grid=[], target_mask=[])
    with pytest.raises(ValueError):
        _run(
            elevation_grid=[[12.0], [11.0, 10.0]],
            weight_grid=valid_w,
            target_mask=valid_t,
        )
    with pytest.raises(ValueError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=[[0.5]],
            target_mask=valid_t,
        )
    with pytest.raises(ValueError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            cell_size_m=0.0,
        )
    with pytest.raises(ValueError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            min_slope=-0.01,
        )
    with pytest.raises(ValueError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            min_slope=math.nan,
        )
    with pytest.raises(ValueError):
        _run(
            elevation_grid=valid_elev,
            weight_grid=valid_w,
            target_mask=valid_t,
            dem_source="   ",
        )
