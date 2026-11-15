"""The equilibrium initialisation of the RothC pools (D218, D219 of issue #77). PROPOSED.

D218: when the starting state carries only the total soil organic carbon,
EP6 runs RothC to equilibrium, cycling the rotation's own monthly climate,
cover and input pattern over the horizon, and scales the input once by

    C_eq = C_i * (SOC - IOM) / (SOC_sim - IOM)

(GSOCseq Technical Manual eq. 5.1, after Smith et al. 2005), so that the
active pools at equilibrium plus the inert pool hold the starting total. The
equilibrium is an initialisation convention, not a claim about the soil
(D80).

D219: the length of the run is the analytic fixed point of the cycle, checked
in a test against a long run of the cycle (10 000 years, as p. 20 of the
model description prints).

**The fixed point.** One month of ``pools.step`` is affine in the pools: the
pools after the month are a matrix of the month times the pools before it,
plus the same matrix times the additions of the month. A cycle of months is
then ``x -> M x + b``. This module builds ``M`` and ``b`` by running the cycle
with ``pools.run`` itself (``M``: from each unit pool with no additions;
``b``: from empty pools with the additions), so the step is not written a
second time, and solves ``(I - M) x = b`` by Gaussian elimination. The
solution is the state at the start of the cycle that the cycle returns to.

**The scaling.** Every addition of the cycle is multiplied by the factor
``(SOC - IOM) / (SOC_sim - IOM)`` and the fixed point is solved again with
the scaled additions. ``M`` does not depend on the additions and ``b`` is
linear in them, so the scaled solution holds the active total ``SOC - IOM``
to the precision of the arithmetic.

Every constant is an argument with no default; no value of the method is
written in this module. Pure functions: no file, no network, no clock. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason, never zero.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from contracts.results.models import Missing as ResultMissing

from ._numbers import NumberOrMissing, check_types, describe_missing, is_missing
from .pools import ACTIVE_POOLS, InputSplit, MonthInput, PoolState, run

__all__ = ["cycle_fixed_point", "equilibrium_state"]


def _not_computable(detail: str) -> ResultMissing:
    return ResultMissing(reason="NOT_COMPUTABLE", detail=f"equilibrium: {detail}")


def _first_missing(months: Sequence[MonthInput]) -> ResultMissing | None:
    """The first month of the cycle whose additions or factor is missing, named."""
    for position, month in enumerate(months):
        for what, item in (
            ("the additions", month.additions),
            ("the rate modifying factor", month.rate_modifying_factor),
        ):
            if is_missing(item):
                return ResultMissing(
                    reason=item.reason,
                    detail=(
                        f"the equilibrium of the cycle is not computed: {what} of "
                        f"month {position} of the cycle is missing, and nothing is "
                        f"filled ({describe_missing(what, item)})"
                    ),
                )
    return None


def _end_of_cycle(
    start: PoolState,
    months: Sequence[MonthInput],
    rate_constants: Mapping[str, NumberOrMissing],
    partition_ratio: NumberOrMissing,
    bio_share: NumberOrMissing,
) -> list[float] | ResultMissing:
    """The active pools after one cycle from ``start``, by ``pools.run``."""
    the_run = run(
        initial_state=start,
        months=months,
        rate_constants=rate_constants,
        partition_ratio=partition_ratio,
        bio_share=bio_share,
    )
    last = the_run.steps[-1]
    if is_missing(last):
        return last
    return [getattr(last.end, pool) for pool in ACTIVE_POOLS]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """The solution of ``matrix x = vector`` by Gaussian elimination with
    partial pivoting; ``None`` when the matrix is singular."""
    size = len(vector)
    rows = [list(row) + [value] for row, value in zip(matrix, vector, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if rows[pivot][column] == 0:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for row in range(column + 1, size):
            factor = rows[row][column] / rows[column][column]
            for position in range(column, size + 1):
                rows[row][position] -= factor * rows[column][position]
    solution = [0.0] * size
    for row in reversed(range(size)):
        known = math.fsum(
            rows[row][position] * solution[position]
            for position in range(row + 1, size)
        )
        solution[row] = (rows[row][size] - known) / rows[row][row]
    return solution


def _zero_split() -> InputSplit:
    return InputSplit(dpm=0.0, rpm=0.0, bio=0.0, hum=0.0)


def _unit_state(pool: str | None) -> PoolState:
    """The pools all empty, or one active pool holding one unit of carbon."""
    return PoolState(
        **{name: (1.0 if name == pool else 0.0) for name in ACTIVE_POOLS}, iom=0.0
    )


def cycle_fixed_point(
    *,
    months: Sequence[MonthInput],
    rate_constants: Mapping[str, NumberOrMissing],
    partition_ratio: NumberOrMissing,
    bio_share: NumberOrMissing,
) -> PoolState | ResultMissing:
    """The state of the active pools that one cycle of ``months`` returns to.

    The cycle is applied as ``pools.run`` applies it: month after month, from
    the first item. Returns a ``PoolState`` whose inert pool is zero (the
    inert pool takes no part in the turnover), or the ``Missing`` of the
    results contract: the reason of the first month whose additions or factor
    is missing; the reason ``pools.step`` gives when a month is not computed;
    ``NOT_COMPUTABLE`` when the cycle is empty, when it decomposes nothing so
    that no state is returned to, or when the solution is not a finite state
    of pools that are not negative.

    Raises ``TypeError`` for an argument of another type.
    """
    if isinstance(months, (str, bytes)) or not isinstance(months, Sequence):
        raise TypeError(
            f"months: expected a sequence of MonthInput, got {type(months).__name__}"
        )
    for position, item in enumerate(months):
        if not isinstance(item, MonthInput):
            raise TypeError(
                f"months[{position}]: expected a MonthInput, got {type(item).__name__}"
            )
    check_types({"partition_ratio": partition_ratio, "bio_share": bio_share})
    if not months:
        return _not_computable("the cycle holds no month")
    missing = _first_missing(months)
    if missing is not None:
        return missing
    without_additions = [
        MonthInput(
            additions=_zero_split(), rate_modifying_factor=month.rate_modifying_factor
        )
        for month in months
    ]
    columns = []
    for pool in ACTIVE_POOLS:
        column = _end_of_cycle(
            _unit_state(pool),
            without_additions,
            rate_constants,
            partition_ratio,
            bio_share,
        )
        if is_missing(column):
            return column
        columns.append(column)
    offset = _end_of_cycle(
        _unit_state(None), months, rate_constants, partition_ratio, bio_share
    )
    if is_missing(offset):
        return offset
    size = len(ACTIVE_POOLS)
    # (I - M), M[row][column] = columns[column][row]
    system = [
        [
            (1.0 if row == column else 0.0) - columns[column][row]
            for column in range(size)
        ]
        for row in range(size)
    ]
    solution = _solve(system, offset)
    if solution is None:
        return _not_computable(
            "the cycle decomposes nothing in some pool (its rate modifying factor "
            "or rate constant is zero over the whole cycle), so no state of the "
            "pools is returned to"
        )
    if not all(math.isfinite(value) and value >= 0 for value in solution):
        return _not_computable(
            "the fixed point of the cycle is not a finite state of pools that are "
            "not negative"
        )
    return PoolState(**dict(zip(ACTIVE_POOLS, solution, strict=True)), iom=0.0)


def equilibrium_state(
    *,
    months: Sequence[MonthInput],
    rate_constants: Mapping[str, NumberOrMissing],
    partition_ratio: NumberOrMissing,
    bio_share: NumberOrMissing,
    total_organic_carbon: NumberOrMissing,
    inert_organic_matter: NumberOrMissing,
) -> PoolState | ResultMissing:
    """The five pools at the start of the cycle, by the inverse mode of D218.

    The fixed point of the cycle with its own additions gives the simulated
    active total ``SOC_sim - IOM``; every addition is then scaled once by
    ``(SOC - IOM) / (SOC_sim - IOM)`` (GSOCseq eq. 5.1) and the fixed point
    solved again. The result holds the active pools of that second fixed
    point and the inert pool given, so its total is ``SOC``.

    Returns the ``PoolState``, or the ``Missing`` of the results contract:
    ``MISSING_INPUT`` naming the total or the inert pool when one is missing;
    the reason ``cycle_fixed_point`` gives; ``NOT_COMPUTABLE`` when the total
    is not above the inert pool, or when the cycle with its own additions
    holds no active carbon at equilibrium (no addition), so no scaling makes
    it hold the total.

    Raises ``TypeError`` for an argument of another type.
    """
    check_types(
        {
            "total_organic_carbon": total_organic_carbon,
            "inert_organic_matter": inert_organic_matter,
        }
    )
    absent = [
        describe_missing(name, item)
        for name, item in (
            ("the total soil organic carbon", total_organic_carbon),
            ("the inert organic matter", inert_organic_matter),
        )
        if is_missing(item)
    ]
    if absent:
        return ResultMissing(
            reason="MISSING_INPUT",
            detail="the equilibrium is not computed: " + "; ".join(absent),
        )
    active_target = total_organic_carbon - inert_organic_matter
    if not active_target > 0:
        return _not_computable(
            "the total soil organic carbon is not above the inert organic matter, "
            "so no active pool can hold the rest"
        )
    first = cycle_fixed_point(
        months=months,
        rate_constants=rate_constants,
        partition_ratio=partition_ratio,
        bio_share=bio_share,
    )
    if is_missing(first):
        return first
    simulated = math.fsum(getattr(first, pool) for pool in ACTIVE_POOLS)
    if not simulated > 0:
        return _not_computable(
            "the cycle with its own carbon inputs holds no active carbon at "
            "equilibrium, so no scaling of the inputs makes it hold the total"
        )
    scale = active_target / simulated
    scaled = [
        MonthInput(
            additions=InputSplit(
                **{
                    pool: getattr(month.additions, pool) * scale
                    for pool in ACTIVE_POOLS
                }
            ),
            rate_modifying_factor=month.rate_modifying_factor,
        )
        for month in months
    ]
    second = cycle_fixed_point(
        months=scaled,
        rate_constants=rate_constants,
        partition_ratio=partition_ratio,
        bio_share=bio_share,
    )
    if is_missing(second):
        return second
    return PoolState(
        **{pool: getattr(second, pool) for pool in ACTIVE_POOLS},
        iom=inert_organic_matter,
    )
