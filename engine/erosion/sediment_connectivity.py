"""Borselli (2008) sediment connectivity index (IC) on a regular D8 grid.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13), Frontier Unit F-03
(``l0/erosion-sediment-connectivity``).

Implements pure-Python regular-grid D8 flow routing (steepest descent over 8
neighbors with flat/sink, tie, and cycle guards) and the Borselli et al. (2008)
Index of Connectivity per cell::

    IC   = log10(D_up / D_dn)
    D_up = W_bar * S_bar * sqrt(A)
    D_dn = sum_i(d_i / (W_i * S_i))

where:

- ``W`` is the caller-supplied weighting / roughness impedance factor (for
  example a RUSLE C-like impedance grid);
- ``S_i = max(raw_slope_i, min_slope)`` is the local steepest-descent slope
  gradient floored at the caller-supplied ``min_slope``;
- ``A`` is the upslope contributing area (``m^2``) accumulated over the D8
  flow graph including the cell itself, with ``W_bar`` and ``S_bar`` the
  arithmetic means of ``W`` and ``S`` over the upslope contributing area;
- ``D_dn`` sums ``d_i / (W_i * S_i)`` along the steepest-descent path from the
  cell until it enters the nearest target (channel/outlet) cell.

Rev13 scientific guards
-----------------------
- ``ConnectivityGridResult`` explicitly marks ``is_exported_sediment_mass=False``
  and ``indicator_kind="RELATIVE_HOTSPOT_CONNECTIVITY"``. ``IC`` is a
  dimensionless relative hotspot connectivity index and is never multiplied into
  ``A_norm`` or treated as exported sediment mass.
- When ``has_external_hydrologic_buffer=False``, ``ConnectivityGridResult`` sets
  ``external_buffer_warning=True`` and records an explicit warning in
  ``warnings`` noting that DEM domain truncation without an external hydrologic
  buffer can distort edge contributing areas and target reachability.
- Zero invented parameter defaults: ``cell_size_m``, ``min_slope``,
  ``dem_source``, ``has_external_hydrologic_buffer``, and ``flat_tie_policy``
  are required keyword-only arguments with no default values.

Pure function (G1): stdlib + ``contracts.*`` only; zero third-party array or
geometry libraries; no file I/O, no network call, no clock, no environment
variable, no mutable global state, and arguments are never modified.
"""

from __future__ import annotations

import enum
import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

__all__ = [
    "INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY",
    "ConnectivityGridResult",
    "FlatTiePolicy",
    "compute_sediment_connectivity",
]

INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY: Literal[
    "RELATIVE_HOTSPOT_CONNECTIVITY"
] = "RELATIVE_HOTSPOT_CONNECTIVITY"

_INPUT_OR_RESULT_MISSING = (InputMissing, ResultMissing)

# Clockwise 8-neighbor offsets starting North: (dr, dc).
_D8_OFFSETS: tuple[tuple[int, int], ...] = (
    (-1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, -1),
)
_SQRT2 = math.sqrt(2.0)

GridCoord = tuple[int, int]


class FlatTiePolicy(enum.Enum):
    """How D8 steepest-descent routing handles tied maximum positive slopes.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    - ``FAIL``: any cell with two or more neighbors achieving the exact same
      strictly positive maximum slope (and any upslope cell routing through it)
      receives ``Missing(reason="NOT_COMPUTABLE")``.
    - ``FIRST_BY_ORDER``: breaks ties deterministically by fixed clockwise
      8-neighbor order starting North.

    Cells with no strictly lower neighbor (internal sinks and flat plateaus)
    always receive ``Missing(reason="NOT_COMPUTABLE")`` under both policies.
    """

    FAIL = "fail"
    FIRST_BY_ORDER = "first_by_order"


@dataclass(frozen=True)
class ConnectivityGridResult:
    """Output grids and Rev13 metadata for Borselli sediment connectivity.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    ic_grid: tuple[tuple[float | ResultMissing, ...], ...]
    d_up_grid: tuple[tuple[float | ResultMissing, ...], ...]
    d_dn_grid: tuple[tuple[float | ResultMissing, ...], ...]
    contributing_area_m2_grid: tuple[tuple[float | ResultMissing, ...], ...]
    flow_direction_grid: tuple[tuple[GridCoord | None, ...], ...]
    n_rows: int
    n_cols: int
    cell_size_m: float
    min_slope: float
    dem_source: str
    has_external_hydrologic_buffer: bool
    external_buffer_warning: bool
    warnings: tuple[str, ...]
    is_exported_sediment_mass: Literal[False] = False
    indicator_kind: Literal["RELATIVE_HOTSPOT_CONNECTIVITY"] = (
        INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY
    )

    def __post_init__(self) -> None:
        if self.is_exported_sediment_mass is not False:
            raise ValueError(
                "Rev13 guard violated: is_exported_sediment_mass must be False"
            )
        if self.indicator_kind != INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY:
            raise ValueError(
                "Rev13 guard violated: indicator_kind must be "
                f"'{INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY}'"
            )
        if self.external_buffer_warning is not (
            not self.has_external_hydrologic_buffer
        ):
            raise ValueError(
                "external_buffer_warning must equal (not has_external_hydrologic_buffer)"
            )


def _is_strict_number(value: object) -> bool:
    """True for ``int`` or ``float``, excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _to_finite_float(value: object) -> float | None:
    """Return finite ``float`` or ``None`` if non-finite or overflowing."""
    if not _is_strict_number(value):
        return None
    try:
        num = float(value)  # type: ignore[arg-type]
    except OverflowError:
        return None
    return num if math.isfinite(num) else None


def _check_positive_finite_scalar(name: str, value: object) -> float:
    """Validate a scalar numeric parameter (G5)."""
    if not _is_strict_number(value):
        raise TypeError(
            f"{name}: expected int or float, got {type(value).__name__} (G5)"
        )
    num = _to_finite_float(value)
    if num is None or num <= 0.0:
        raise ValueError(f"{name}: expected a finite number > 0, got {value!r}")
    return num


def _check_2d_sequence(name: str, grid: object) -> tuple[int, int]:
    """Validate a non-empty rectangular 2D sequence and return ``(n_rows, n_cols)``."""
    if isinstance(grid, (str, bytes, bytearray)) or not isinstance(grid, Sequence):
        raise TypeError(
            f"{name}: expected a 2D sequence, got {type(grid).__name__} (G5)"
        )
    n_rows = len(grid)
    if n_rows == 0:
        raise ValueError(f"{name}: grid must have at least one row")
    n_cols: int | None = None
    for row_idx, row in enumerate(grid):
        if isinstance(row, (str, bytes, bytearray)) or not isinstance(row, Sequence):
            raise TypeError(
                f"{name}[{row_idx}]: expected a row sequence, "
                f"got {type(row).__name__} (G5)"
            )
        if n_cols is None:
            n_cols = len(row)
            if n_cols == 0:
                raise ValueError(f"{name}: grid must have at least one column")
        elif len(row) != n_cols:
            raise ValueError(
                f"{name}: ragged grid at row {row_idx} "
                f"(expected {n_cols} columns, got {len(row)})"
            )
    assert n_cols is not None
    return n_rows, n_cols


def _validate_numeric_or_missing_grid(
    name: str,
    grid: object,
    expected_shape: tuple[int, int] | None,
) -> tuple[int, int]:
    """Validate a 2D grid of numbers or contract ``Missing`` values."""
    shape = _check_2d_sequence(name, grid)
    if expected_shape is not None and shape != expected_shape:
        raise ValueError(f"{name}: expected shape {expected_shape}, got {shape}")
    assert isinstance(grid, Sequence)
    for r, row in enumerate(grid):
        for c, item in enumerate(row):
            if isinstance(item, _INPUT_OR_RESULT_MISSING):
                continue
            if not _is_strict_number(item):
                raise TypeError(
                    f"{name}[{r}][{c}]: expected int, float, or Missing; "
                    f"got {type(item).__name__} (G5)"
                )
    return shape


def _validate_bool_grid(
    name: str,
    grid: object,
    expected_shape: tuple[int, int],
) -> None:
    """Validate a 2D grid of strict ``bool`` values matching ``expected_shape``."""
    shape = _check_2d_sequence(name, grid)
    if shape != expected_shape:
        raise ValueError(f"{name}: expected shape {expected_shape}, got {shape}")
    assert isinstance(grid, Sequence)
    for r, row in enumerate(grid):
        for c, item in enumerate(row):
            if not isinstance(item, bool):
                raise TypeError(
                    f"{name}[{r}][{c}]: expected bool, got {type(item).__name__} (G5)"
                )


def _format_missing_detail(
    grid_name: str,
    r: int,
    c: int,
    item: object,
) -> str:
    """Format an explicit English detail for a missing or non-finite raster cell."""
    if isinstance(item, _INPUT_OR_RESULT_MISSING):
        base = f"{grid_name}[{r}][{c}] is missing ({item.reason}"
        if item.detail is not None:
            return f"{base}: {item.detail})"
        return f"{base})"
    return f"{grid_name}[{r}][{c}] is non-finite ({item!r})"


@dataclass(frozen=True)
class _CellStatus:
    """Validated per-cell input state prior to D8 routing."""

    covered: bool
    no_coverage_detail: str | None
    elevation: float | None
    elev_missing_detail: str | None
    weight: float | None
    weight_missing_detail: str | None
    weight_nonpos_detail: str | None
    is_target: bool


def _classify_cells(
    *,
    elevation_grid: Sequence[Sequence[float | int | InputMissing | ResultMissing]],
    weight_grid: Sequence[Sequence[float | int | InputMissing | ResultMissing]],
    target_mask: Sequence[Sequence[bool]],
    coverage_mask: Sequence[Sequence[bool]] | None,
    n_rows: int,
    n_cols: int,
) -> list[list[_CellStatus]]:
    """Classify coverage, elevation validity, and weight validity for every cell."""
    cells: list[list[_CellStatus]] = []
    for r in range(n_rows):
        row_cells: list[_CellStatus] = []
        for c in range(n_cols):
            raw_z = elevation_grid[r][c]
            raw_w = weight_grid[r][c]
            is_target = target_mask[r][c]

            if coverage_mask is not None and not coverage_mask[r][c]:
                row_cells.append(
                    _CellStatus(
                        covered=False,
                        no_coverage_detail=f"cell ({r}, {c}) is masked out by coverage_mask",
                        elevation=None,
                        elev_missing_detail=None,
                        weight=None,
                        weight_missing_detail=None,
                        weight_nonpos_detail=None,
                        is_target=is_target,
                    )
                )
                continue

            if (
                isinstance(raw_z, _INPUT_OR_RESULT_MISSING)
                and raw_z.reason == "NO_COVERAGE"
            ):
                row_cells.append(
                    _CellStatus(
                        covered=False,
                        no_coverage_detail=_format_missing_detail(
                            "elevation_grid", r, c, raw_z
                        ),
                        elevation=None,
                        elev_missing_detail=None,
                        weight=None,
                        weight_missing_detail=None,
                        weight_nonpos_detail=None,
                        is_target=is_target,
                    )
                )
                continue

            if (
                isinstance(raw_w, _INPUT_OR_RESULT_MISSING)
                and raw_w.reason == "NO_COVERAGE"
            ):
                row_cells.append(
                    _CellStatus(
                        covered=False,
                        no_coverage_detail=_format_missing_detail(
                            "weight_grid", r, c, raw_w
                        ),
                        elevation=None,
                        elev_missing_detail=None,
                        weight=None,
                        weight_missing_detail=None,
                        weight_nonpos_detail=None,
                        is_target=is_target,
                    )
                )
                continue

            z_val = (
                None
                if isinstance(raw_z, _INPUT_OR_RESULT_MISSING)
                else _to_finite_float(raw_z)
            )
            elev_missing = (
                None
                if z_val is not None
                else _format_missing_detail("elevation_grid", r, c, raw_z)
            )

            w_val = (
                None
                if isinstance(raw_w, _INPUT_OR_RESULT_MISSING)
                else _to_finite_float(raw_w)
            )
            weight_missing = (
                None
                if w_val is not None
                else _format_missing_detail("weight_grid", r, c, raw_w)
            )
            weight_nonpos = (
                f"weight_grid[{r}][{c}] must be > 0 for connectivity resistance (got {w_val!r})"
                if w_val is not None and w_val <= 0.0
                else None
            )

            row_cells.append(
                _CellStatus(
                    covered=True,
                    no_coverage_detail=None,
                    elevation=z_val,
                    elev_missing_detail=elev_missing,
                    weight=w_val,
                    weight_missing_detail=weight_missing,
                    weight_nonpos_detail=weight_nonpos,
                    is_target=is_target,
                )
            )
        cells.append(row_cells)
    return cells


def _route_d8_steepest_descent(
    *,
    cells: list[list[_CellStatus]],
    n_rows: int,
    n_cols: int,
    cell_size_m: float,
    min_slope: float,
    flat_tie_policy: FlatTiePolicy,
) -> tuple[
    list[list[GridCoord | None]],
    list[list[float | None]],
    list[list[float | None]],
    list[list[str | None]],
]:
    """Compute D8 steepest-descent neighbor, clamped slope ``S_i``, step distance, and failure reason.

    Target cells and cells without valid elevation are terminal (``next_cell = None``).
    """
    next_cell: list[list[GridCoord | None]] = [[None] * n_cols for _ in range(n_rows)]
    slope_i: list[list[float | None]] = [[None] * n_cols for _ in range(n_rows)]
    step_dist: list[list[float | None]] = [[None] * n_cols for _ in range(n_rows)]
    route_issue: list[list[str | None]] = [[None] * n_cols for _ in range(n_rows)]

    diag_dist = _SQRT2 * cell_size_m

    for r in range(n_rows):
        for c in range(n_cols):
            cell = cells[r][c]
            if not cell.covered or cell.elevation is None or cell.is_target:
                continue

            z_here = cell.elevation
            best_slope = 0.0
            best_neighbors: list[tuple[GridCoord, float]] = []

            for dr, dc in _D8_OFFSETS:
                nr = r + dr
                nc = c + dc
                if not (0 <= nr < n_rows and 0 <= nc < n_cols):
                    continue
                nbr = cells[nr][nc]
                if not nbr.covered or nbr.elevation is None:
                    continue
                dz = z_here - nbr.elevation
                if dz <= 0.0:
                    continue
                dist = cell_size_m if (dr == 0 or dc == 0) else diag_dist
                slope = dz / dist
                if slope > best_slope:
                    best_slope = slope
                    best_neighbors = [((nr, nc), dist)]
                elif slope == best_slope:
                    best_neighbors.append(((nr, nc), dist))

            if not best_neighbors:
                route_issue[r][c] = (
                    f"cell ({r}, {c}) is an internal sink or flat plateau with no "
                    "strictly lower valid neighbor (target unreachable)"
                )
                continue

            if len(best_neighbors) > 1 and flat_tie_policy is FlatTiePolicy.FAIL:
                tied = ", ".join(str(coord) for coord, _ in best_neighbors)
                route_issue[r][c] = (
                    f"cell ({r}, {c}) has tied steepest-descent slope {best_slope!r} "
                    f"to neighbors {tied} under FlatTiePolicy.FAIL"
                )
                continue

            chosen_coord, chosen_dist = best_neighbors[0]
            next_cell[r][c] = chosen_coord
            slope_i[r][c] = max(best_slope, min_slope)
            step_dist[r][c] = chosen_dist

    return next_cell, slope_i, step_dist, route_issue


def _accumulate_connectivity_from_directions(
    *,
    cells: list[list[_CellStatus]],
    next_cell: list[list[GridCoord | None]],
    slope_i: list[list[float | None]],
    step_dist: list[list[float | None]],
    route_issue: list[list[str | None]],
    n_rows: int,
    n_cols: int,
    cell_size_m: float,
    min_slope: float,
    dem_source: str,
    has_external_hydrologic_buffer: bool,
) -> ConnectivityGridResult:
    """Run topological upslope accumulation, reverse-BFS downslope accumulation, and IC assembly.

    Separated from ``_route_d8_steepest_descent`` so cycle-guard logic is
    explicit and directly testable against synthetic directed graphs.
    """
    cell_area_m2 = cell_size_m * cell_size_m

    # Reverse adjacency list and in-degree for topological (Kahn BFS) upslope pass.
    rev_adj: list[list[list[GridCoord]]] = [
        [[] for _ in range(n_cols)] for _ in range(n_rows)
    ]
    in_degree: list[list[int]] = [[0] * n_cols for _ in range(n_rows)]

    for r in range(n_rows):
        for c in range(n_cols):
            cell = cells[r][c]
            if not cell.covered or cell.elevation is None:
                continue
            nxt = next_cell[r][c]
            if nxt is not None:
                nr, nc = nxt
                rev_adj[nr][nc].append((r, c))
                in_degree[nr][nc] += 1

    # --- 1. Upslope topological accumulation (Kahn's BFS) ---
    n_up: list[list[int]] = [[0] * n_cols for _ in range(n_rows)]
    sum_w: list[list[float]] = [[0.0] * n_cols for _ in range(n_rows)]
    sum_s: list[list[float]] = [[0.0] * n_cols for _ in range(n_rows)]
    up_missing_w: list[list[str | None]] = [[None] * n_cols for _ in range(n_rows)]
    up_nonpos_w: list[list[str | None]] = [[None] * n_cols for _ in range(n_rows)]
    topo_visited: list[list[bool]] = [[False] * n_cols for _ in range(n_rows)]

    topo_queue: deque[GridCoord] = deque()
    for r in range(n_rows):
        for c in range(n_cols):
            cell = cells[r][c]
            if not cell.covered or cell.elevation is None:
                continue
            n_up[r][c] = 1
            if cell.weight is not None:
                sum_w[r][c] = cell.weight
            else:
                up_missing_w[r][c] = cell.weight_missing_detail
            if cell.weight_nonpos_detail is not None:
                up_nonpos_w[r][c] = cell.weight_nonpos_detail
            s_val = slope_i[r][c]
            if s_val is not None:
                sum_s[r][c] = s_val
            if in_degree[r][c] == 0:
                topo_queue.append((r, c))

    while topo_queue:
        r, c = topo_queue.popleft()
        topo_visited[r][c] = True
        nxt = next_cell[r][c]
        if nxt is None:
            continue
        nr, nc = nxt
        n_up[nr][nc] += n_up[r][c]
        sum_w[nr][nc] += sum_w[r][c]
        sum_s[nr][nc] += sum_s[r][c]
        if up_missing_w[nr][nc] is None and up_missing_w[r][c] is not None:
            up_missing_w[nr][nc] = up_missing_w[r][c]
        if up_nonpos_w[nr][nc] is None and up_nonpos_w[r][c] is not None:
            up_nonpos_w[nr][nc] = up_nonpos_w[r][c]
        in_degree[nr][nc] -= 1
        if in_degree[nr][nc] == 0:
            topo_queue.append((nr, nc))

    # --- 2. Downslope reverse-BFS from target cells ---
    reaches_target: list[list[bool]] = [[False] * n_cols for _ in range(n_rows)]
    d_dn_val: list[list[float]] = [[0.0] * n_cols for _ in range(n_rows)]
    dn_missing_w: list[list[str | None]] = [[None] * n_cols for _ in range(n_rows)]
    dn_nonpos_w: list[list[str | None]] = [[None] * n_cols for _ in range(n_rows)]

    rev_queue: deque[GridCoord] = deque()
    for r in range(n_rows):
        for c in range(n_cols):
            cell = cells[r][c]
            if cell.covered and cell.elevation is not None and cell.is_target:
                reaches_target[r][c] = True
                d_dn_val[r][c] = 0.0
                rev_queue.append((r, c))

    while rev_queue:
        vr, vc = rev_queue.popleft()
        for ur, uc in rev_adj[vr][vc]:
            if reaches_target[ur][uc]:
                continue
            reaches_target[ur][uc] = True
            u_cell = cells[ur][uc]
            if u_cell.weight_missing_detail is not None:
                dn_missing_w[ur][uc] = u_cell.weight_missing_detail
            elif dn_missing_w[vr][vc] is not None:
                dn_missing_w[ur][uc] = dn_missing_w[vr][vc]

            if u_cell.weight_nonpos_detail is not None:
                dn_nonpos_w[ur][uc] = u_cell.weight_nonpos_detail
            elif dn_nonpos_w[vr][vc] is not None:
                dn_nonpos_w[ur][uc] = dn_nonpos_w[vr][vc]

            if (
                dn_missing_w[ur][uc] is None
                and dn_nonpos_w[ur][uc] is None
                and u_cell.weight is not None
                and slope_i[ur][uc] is not None
                and step_dist[ur][uc] is not None
            ):
                d_dn_val[ur][uc] = d_dn_val[vr][vc] + (
                    step_dist[ur][uc] / (u_cell.weight * slope_i[ur][uc])
                )
            rev_queue.append((ur, uc))

    # --- 3. Reverse-BFS propagation of terminal routing issue (sink/flat-tie/cycle) ---
    terminal_issue: list[list[str | None]] = [
        [route_issue[r][c] for c in range(n_cols)] for r in range(n_rows)
    ]
    issue_queue: deque[GridCoord] = deque()
    for r in range(n_rows):
        for c in range(n_cols):
            cell = cells[r][c]
            if (
                cell.covered
                and cell.elevation is not None
                and not topo_visited[r][c]
                and terminal_issue[r][c] is None
            ):
                terminal_issue[r][c] = (
                    f"flow routing cycle detected on path from cell ({r}, {c}); "
                    "upslope area and target path are undefined"
                )
            if terminal_issue[r][c] is not None:
                issue_queue.append((r, c))
    while issue_queue:
        vr, vc = issue_queue.popleft()
        for ur, uc in rev_adj[vr][vc]:
            if terminal_issue[ur][uc] is None:
                terminal_issue[ur][uc] = terminal_issue[vr][vc]
                issue_queue.append((ur, uc))

    # --- 4. Assemble immutable output grids ---
    ic_rows: list[tuple[float | ResultMissing, ...]] = []
    d_up_rows: list[tuple[float | ResultMissing, ...]] = []
    d_dn_rows: list[tuple[float | ResultMissing, ...]] = []
    area_rows: list[tuple[float | ResultMissing, ...]] = []
    dir_rows: list[tuple[GridCoord | None, ...]] = []

    for r in range(n_rows):
        ic_row: list[float | ResultMissing] = []
        d_up_row: list[float | ResultMissing] = []
        d_dn_row: list[float | ResultMissing] = []
        area_row: list[float | ResultMissing] = []
        dir_row: list[GridCoord | None] = []

        for c in range(n_cols):
            cell = cells[r][c]
            dir_row.append(next_cell[r][c])

            if not cell.covered:
                no_cov = ResultMissing(
                    reason="NO_COVERAGE",
                    detail=cell.no_coverage_detail,
                )
                ic_row.append(no_cov)
                d_up_row.append(no_cov)
                d_dn_row.append(no_cov)
                area_row.append(no_cov)
                continue

            if cell.elev_missing_detail is not None:
                miss_elev = ResultMissing(
                    reason="MISSING_INPUT",
                    detail=cell.elev_missing_detail,
                )
                ic_row.append(miss_elev)
                d_up_row.append(miss_elev)
                d_dn_row.append(miss_elev)
                area_row.append(miss_elev)
                continue

            if not topo_visited[r][c]:
                cycle_miss = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=terminal_issue[r][c],
                )
                area_row.append(cycle_miss)
                if cell.weight_missing_detail is not None:
                    miss_w = ResultMissing(
                        reason="MISSING_INPUT",
                        detail=cell.weight_missing_detail,
                    )
                    ic_row.append(miss_w)
                    d_up_row.append(miss_w)
                    d_dn_row.append(miss_w)
                else:
                    ic_row.append(cycle_miss)
                    d_up_row.append(cycle_miss)
                    d_dn_row.append(cycle_miss)
                continue

            area_m2 = n_up[r][c] * cell_area_m2
            area_row.append(area_m2)

            if cell.weight_missing_detail is not None:
                miss_w = ResultMissing(
                    reason="MISSING_INPUT",
                    detail=cell.weight_missing_detail,
                )
                ic_row.append(miss_w)
                d_up_row.append(miss_w)
                d_dn_row.append(miss_w)
                continue

            if cell.is_target:
                not_app = ResultMissing(
                    reason="NOT_APPLICABLE",
                    detail=(
                        f"cell ({r}, {c}) is a target (channel/outlet) cell; "
                        "hillslope connectivity to target is not applicable"
                    ),
                )
                ic_row.append(not_app)
                d_up_row.append(not_app)
                d_dn_row.append(0.0)
                continue

            # Compute D_up independently where cell has a downslope slope S_i.
            cell_d_up: float | ResultMissing
            if slope_i[r][c] is None:
                detail = (
                    terminal_issue[r][c]
                    or f"cell ({r}, {c}) has no valid downslope neighbor"
                )
                cell_d_up = ResultMissing(reason="NOT_COMPUTABLE", detail=detail)
            elif up_missing_w[r][c] is not None:
                cell_d_up = ResultMissing(
                    reason="MISSING_INPUT",
                    detail=up_missing_w[r][c],
                )
            elif up_nonpos_w[r][c] is not None:
                cell_d_up = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=up_nonpos_w[r][c],
                )
            else:
                w_bar = sum_w[r][c] / n_up[r][c]
                s_bar = sum_s[r][c] / n_up[r][c]
                val_up = w_bar * s_bar * math.sqrt(area_m2)
                if math.isfinite(val_up) and val_up > 0.0:
                    cell_d_up = val_up
                else:
                    cell_d_up = ResultMissing(
                        reason="NOT_COMPUTABLE",
                        detail=f"D_up at cell ({r}, {c}) is not finite and positive ({val_up!r})",
                    )
            d_up_row.append(cell_d_up)

            # Compute D_dn along steepest-descent path to nearest target.
            cell_d_dn: float | ResultMissing
            if not reaches_target[r][c]:
                detail = (
                    terminal_issue[r][c] or f"target unreachable from cell ({r}, {c})"
                )
                cell_d_dn = ResultMissing(reason="NOT_COMPUTABLE", detail=detail)
            elif dn_missing_w[r][c] is not None:
                cell_d_dn = ResultMissing(
                    reason="MISSING_INPUT",
                    detail=dn_missing_w[r][c],
                )
            elif dn_nonpos_w[r][c] is not None:
                cell_d_dn = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=dn_nonpos_w[r][c],
                )
            else:
                val_dn = d_dn_val[r][c]
                if math.isfinite(val_dn) and val_dn > 0.0:
                    cell_d_dn = val_dn
                else:
                    cell_d_dn = ResultMissing(
                        reason="NOT_COMPUTABLE",
                        detail=f"D_dn at cell ({r}, {c}) is not finite and positive ({val_dn!r})",
                    )
            d_dn_row.append(cell_d_dn)

            # Combine into IC = log10(D_up / D_dn), prioritizing MISSING_INPUT (C3.3).
            if isinstance(cell_d_up, ResultMissing) and (
                cell_d_up.reason == "MISSING_INPUT"
            ):
                ic_row.append(cell_d_up)
            elif isinstance(cell_d_dn, ResultMissing) and (
                cell_d_dn.reason == "MISSING_INPUT"
            ):
                ic_row.append(cell_d_dn)
            elif isinstance(cell_d_up, ResultMissing):
                ic_row.append(cell_d_up)
            elif isinstance(cell_d_dn, ResultMissing):
                ic_row.append(cell_d_dn)
            else:
                ratio = cell_d_up / cell_d_dn
                if math.isfinite(ratio) and ratio > 0.0:
                    ic_val = math.log10(ratio)
                    if math.isfinite(ic_val):
                        ic_row.append(ic_val)
                    else:
                        ic_row.append(
                            ResultMissing(
                                reason="NOT_COMPUTABLE",
                                detail=f"IC at cell ({r}, {c}) is not finite",
                            )
                        )
                else:
                    ic_row.append(
                        ResultMissing(
                            reason="NOT_COMPUTABLE",
                            detail=f"D_up / D_dn ratio at cell ({r}, {c}) is not finite and positive",
                        )
                    )

        ic_rows.append(tuple(ic_row))
        d_up_rows.append(tuple(d_up_row))
        d_dn_rows.append(tuple(d_dn_row))
        area_rows.append(tuple(area_row))
        dir_rows.append(tuple(dir_row))

    warnings_list: list[str] = []
    if not has_external_hydrologic_buffer:
        warnings_list.append(
            "NO_EXTERNAL_HYDROLOGIC_BUFFER: DEM grid lacks an external hydrologic "
            "buffer; boundary contributing areas and target reachability may be "
            "truncated at domain edges."
        )

    return ConnectivityGridResult(
        ic_grid=tuple(ic_rows),
        d_up_grid=tuple(d_up_rows),
        d_dn_grid=tuple(d_dn_rows),
        contributing_area_m2_grid=tuple(area_rows),
        flow_direction_grid=tuple(dir_rows),
        n_rows=n_rows,
        n_cols=n_cols,
        cell_size_m=cell_size_m,
        min_slope=min_slope,
        dem_source=dem_source,
        has_external_hydrologic_buffer=has_external_hydrologic_buffer,
        external_buffer_warning=not has_external_hydrologic_buffer,
        warnings=tuple(warnings_list),
        is_exported_sediment_mass=False,
        indicator_kind=INDICATOR_KIND_RELATIVE_HOTSPOT_CONNECTIVITY,
    )


def compute_sediment_connectivity(
    *,
    elevation_grid: Sequence[Sequence[float | int | InputMissing | ResultMissing]],
    weight_grid: Sequence[Sequence[float | int | InputMissing | ResultMissing]],
    cell_size_m: float,
    target_mask: Sequence[Sequence[bool]],
    min_slope: float,
    dem_source: str,
    has_external_hydrologic_buffer: bool,
    flat_tie_policy: FlatTiePolicy,
    coverage_mask: Sequence[Sequence[bool]] | None = None,
) -> ConnectivityGridResult:
    """Compute Borselli et al. (2008) Index of Connectivity (IC) over a regular D8 grid.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    All scientific and configuration arguments are keyword-only with zero
    invented defaults:

    - ``elevation_grid``: 2D grid of elevations (``m``) or contract ``Missing``.
    - ``weight_grid``: 2D grid of dimensionless weighting / roughness impedance
      factors ``W > 0`` (e.g., C-like cover-management factor) or ``Missing``.
    - ``cell_size_m``: uniform square raster spacing in meters (``> 0``).
    - ``target_mask``: 2D boolean grid marking target channel/outlet cells.
    - ``min_slope``: strictly positive slope floor (``m m-1``, ``> 0``) applied
      after D8 steepest-descent direction selection.
    - ``dem_source``: non-blank DEM provenance identifier (for example
      ``"IDE_MDT_2_5M"`` or ``"NASADEM_30M"``).
    - ``has_external_hydrologic_buffer``: whether the DEM includes an external
      hydrologic buffer; ``False`` emits a warning/flag on the result.
    - ``flat_tie_policy``: ``FlatTiePolicy`` controlling equal steepest-descent
      slopes.
    - ``coverage_mask``: optional 2D boolean grid where ``False`` marks cells
      outside domain coverage (``Missing(reason="NO_COVERAGE")``).

    Raises ``TypeError`` for invalid argument types and ``ValueError`` for
    empty/ragged/mismatched grids, non-positive scalar parameters, or blank
    ``dem_source`` (G5).
    """
    shape = _validate_numeric_or_missing_grid("elevation_grid", elevation_grid, None)
    _validate_numeric_or_missing_grid("weight_grid", weight_grid, shape)
    _validate_bool_grid("target_mask", target_mask, shape)
    if coverage_mask is not None:
        _validate_bool_grid("coverage_mask", coverage_mask, shape)

    cell_size_val = _check_positive_finite_scalar("cell_size_m", cell_size_m)
    min_slope_val = _check_positive_finite_scalar("min_slope", min_slope)

    if not isinstance(dem_source, str):
        raise TypeError(
            f"dem_source: expected str, got {type(dem_source).__name__} (G5)"
        )
    if dem_source.strip() == "":
        raise ValueError("dem_source: must not be empty or blank")

    if not isinstance(has_external_hydrologic_buffer, bool):
        raise TypeError(
            "has_external_hydrologic_buffer: expected bool, "
            f"got {type(has_external_hydrologic_buffer).__name__} (G5)"
        )
    if not isinstance(flat_tie_policy, FlatTiePolicy):
        raise TypeError(
            "flat_tie_policy: expected FlatTiePolicy, "
            f"got {type(flat_tie_policy).__name__} (G5)"
        )

    n_rows, n_cols = shape
    cells = _classify_cells(
        elevation_grid=elevation_grid,
        weight_grid=weight_grid,
        target_mask=target_mask,
        coverage_mask=coverage_mask,
        n_rows=n_rows,
        n_cols=n_cols,
    )
    next_cell, slope_i, step_dist, route_issue = _route_d8_steepest_descent(
        cells=cells,
        n_rows=n_rows,
        n_cols=n_cols,
        cell_size_m=cell_size_val,
        min_slope=min_slope_val,
        flat_tie_policy=flat_tie_policy,
    )
    return _accumulate_connectivity_from_directions(
        cells=cells,
        next_cell=next_cell,
        slope_i=slope_i,
        step_dist=step_dist,
        route_issue=route_issue,
        n_rows=n_rows,
        n_cols=n_cols,
        cell_size_m=cell_size_val,
        min_slope=min_slope_val,
        dem_source=dem_source,
        has_external_hydrologic_buffer=has_external_hydrologic_buffer,
    )
