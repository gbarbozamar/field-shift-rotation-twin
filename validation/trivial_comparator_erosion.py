"""The trivial comparator of the soil loss (entry E0 of ``docs/VALIDATION.md``;
decision D211 of issue #77; unit l0/trivial-comparator-e0-d211, issue #311).

D211: "The erosivity-weighted share of the year without a living crop, per
rotation, scenario, phase and agricultural year, ordered by its mean over
agricultural years (lower is better), compared with the order of the full
``soil_loss`` by the reading of D0." For one agricultural year the share is
the sum over its twelve months of the climatological fraction of the month's
erosivity times the share of the days of that month on which no component of
the repeated calendar carries a living crop. It is a validation record for the
science reviewers and is never a soil loss.

What is called, not re-implemented:

- the monthly fractions: ``climatological_monthly_fractions`` of
  ``engine/erosion/r_factor/`` (M1.2, D69, D84), on the twelve monthly
  erosivity values the caller passes;
- the months of an agricultural year and the agricultural year of a month:
  ``months_of_ag_year`` and ``ag_year_of`` of the same package (C5.3);
- the order of the full ``soil_loss`` values by their mean over agricultural
  years, read in the direction of the row (C1.1), ignoring ranges: the reading
  of entry D0, ``trivial_orders`` of ``validation/trivial_comparator.py``.

What is taken as an input (OPEN 1): which days carry a living crop. EP3 decides
it inside its chain for the window of D157 (a component of the repeated
calendar on the day, and not a day of the tail after maturity, D105, D106,
D136); the stage lengths it needs come from the catalogue, and no public
function of ``engine/`` returns the flags. So this module reads, for each
rotation and scenario, a flag per day: ``True`` when a living crop is on the
field, ``False`` when none is, or a ``Missing`` with its reason (the
``Missing`` of the results contract or of the inputs contract, as the engine
accepts either). It decides no day itself. Any other flag (``None``, the
integers 0 and 1, text) is a defect of the caller and raises ``TypeError``:
it is never counted as a day with or without a crop.

Rules of the order, as entry D0 has them (D211: "A tie, a missing year and a
single rotation give no order, with the reason; nothing is filled and nothing
is read as zero"): each scenario on its own (D166); an agricultural year whose
share cannot be computed for a rotation (a day without a flag, a ``Missing``
flag, or the fractions missing) is a missing year, and that scenario gets no
order; two equal means, or a single rotation, give no order; a scenario whose
rotations all have empty flags reads no agricultural year and gives no order.
The means are compared exactly, as rational numbers built from the stored
values (OPEN 7 of the D0 comparator applies here too).

Pure functions: no file, no clock, no network. The module holds no value of
the method and no threshold: the fractions come from the erosivity the caller
passes, the flags from the caller, and the soil loss from the caller's table.

OPEN, for the lead developer:

1. The daily flags of a living crop are an input (above). Options: (a) as
   built, flags passed by the caller; (b) a public function in ``engine/``
   that gives the flags of D157 for a calendar and a catalogue, called here.
2. The agricultural years read are those the flags touch, for every rotation
   of the scenario; a year that one rotation lacks or does not cover whole is
   a missing year, so the edge years of a record give no order. Options: (a)
   as built; (b) only the years every rotation covers whole; (c) the years of
   the ``soil_loss`` rows of the table. This is OPEN 1 of the D0 comparator
   seen from the flags.
3. A scenario that the flags hold and the table does not, or the reverse,
   gives no order on the missing side, with its reason. Options: (a) as built;
   (b) refuse the inputs.
4. A scenario whose rotations differ between the flags and the table
   (``compare_with_soil_loss``) raises ``ValueError``: an order is compared
   only over the same rotations. Options: (a) as built, the inputs refused;
   (b) no order on both sides, with the reason; (c) compare over the
   rotations both sides hold.
"""

from __future__ import annotations

import calendar
import datetime as dt
import itertools
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing, ResultsTable
from engine.erosion.r_factor import climatological_monthly_fractions
from engine.erosion.r_factor._checks import ag_year_of, months_of_ag_year
from validation.trivial_comparator import TrivialOrder, trivial_orders

SOIL_LOSS = "soil_loss"

# A flag that is missing: the ``Missing`` of either contract, as the engine
# accepts either (``engine/rothc/_numbers.py``, ``MISSING_SHAPES``).
MISSING_FLAGS = (Missing, InputMissing)
Flag = bool | Missing | InputMissing

Outcome = Literal[
    "equal",
    "different",
    "no order from the trivial comparator",
    "no order from the full method",
    "no order from either",
]


@dataclass(frozen=True)
class YearShare:
    """The erosivity-weighted share of one agricultural year without a living
    crop, for one rotation and scenario; ``None`` with ``missing`` when it
    cannot be computed. It is not a soil loss."""

    rotation_id: str
    scenario_id: str
    ag_year: int
    share: float | None
    missing: Missing | None


@dataclass(frozen=True)
class ErosionOrder:
    """The order the trivial comparator of E0 gives one scenario: the
    rotations best first (lowest mean share first), or ``None`` with the
    reason. ``means`` holds the mean share of each rotation, or ``None`` when
    a mean would need a missing year filled."""

    scenario_id: str
    means: tuple[tuple[str, float], ...] | None
    order: tuple[str, ...] | None
    reason: str | None


@dataclass(frozen=True)
class ErosionComparison:
    """One line of the report of entry E0: for one scenario, the order of the
    trivial comparator, the order of the full ``soil_loss`` by the reading of
    D0, whether they are equal, and how many rotations each side ordered.
    "Equal" or "different" only when both orders exist."""

    scenario_id: str
    trivial: ErosionOrder
    full: TrivialOrder | None
    full_reason: str | None
    outcome: Outcome
    trivial_rotations_ordered: int
    full_rotations_ordered: int


def _month_share_without_crop(
    flags: Mapping[dt.date, Flag], year: int, month: int
) -> Fraction | Missing:
    """The share of the days of one calendar month with no living crop."""
    days = [
        dt.date(year, month, day)
        for day in range(1, calendar.monthrange(year, month)[1] + 1)
    ]
    absent = [day for day in days if day not in flags]
    if absent:
        return Missing(
            reason="NO_COVERAGE",
            detail=(
                f"{len(absent)} day(s) of {year:04d}-{month:02d} carry no flag of a "
                "living crop: the month is not covered whole"
            ),
        )
    for day in days:
        if isinstance(flags[day], MISSING_FLAGS):
            given = flags[day]
            return Missing(
                reason=given.reason,
                detail=(
                    f"whether a living crop is on the field on {day.isoformat()} is "
                    f"missing: {given.detail or given.reason}"
                ),
            )
    without = sum(1 for day in days if flags[day] is False)
    return Fraction(without, len(days))


def _year_share(
    flags: Mapping[dt.date, Flag],
    fractions: Mapping[int, float] | Missing,
    ag_year: int,
    start_month: int,
) -> Fraction | Missing:
    """The erosivity-weighted share of one agricultural year without a living
    crop (D211), or why it cannot be computed."""
    if isinstance(fractions, Missing):
        return fractions
    total = Fraction(0)
    for year, month in months_of_ag_year(ag_year, start_month):
        fraction = fractions[month]
        if isinstance(fraction, Missing):
            return fraction
        part = _month_share_without_crop(flags, year, month)
        if isinstance(part, Missing):
            return part
        total += Fraction(fraction) * part
    return total


def _fractions(
    monthly_erosivity: Mapping[int, float | Missing],
) -> Mapping[int, float] | Missing:
    return climatological_monthly_fractions(monthly_erosivity=monthly_erosivity)


def _ag_years(flags: Mapping[dt.date, Flag], start_month: int) -> set[int]:
    return {ag_year_of((day.year, day.month), start_month) for day in flags}


def _check_flags(living: Mapping[tuple[str, str], Mapping[dt.date, Flag]]) -> None:
    """Every flag is ``True``, ``False`` or a ``Missing`` of either contract.

    Anything else (``None``, the integers 0 and 1, text) is a defect of the
    caller: ``TypeError``, never a day counted with or without a crop.
    """
    for (rotation_id, scenario_id), flags in living.items():
        for day, flag in flags.items():
            if isinstance(flag, bool) or isinstance(flag, MISSING_FLAGS):
                continue
            raise TypeError(
                f"the flag of rotation '{rotation_id}', scenario '{scenario_id}' "
                f"on {day} is {type(flag).__name__}: a flag of a living crop is "
                "True, False or a Missing with its reason (a missing flag is never "
                "None, and an integer is not a flag)"
            )


def _rotations_by_scenario(
    living: Mapping[tuple[str, str], Mapping[dt.date, Flag]],
) -> dict[str, list[str]]:
    by_scenario: dict[str, list[str]] = {}
    for rotation_id, scenario_id in living:
        by_scenario.setdefault(scenario_id, []).append(rotation_id)
    return by_scenario


def _exact_shares(
    living: Mapping[tuple[str, str], Mapping[dt.date, Flag]],
    monthly_erosivity: Mapping[int, float | Missing],
    start_month: int,
) -> dict[tuple[str, str, int], Fraction | Missing]:
    _check_flags(living)
    fractions = _fractions(monthly_erosivity)
    shares: dict[tuple[str, str, int], Fraction | Missing] = {}
    for scenario_id, rotations in _rotations_by_scenario(living).items():
        years = set().union(
            *(_ag_years(living[(r, scenario_id)], start_month) for r in rotations)
        )
        for rotation_id in rotations:
            flags = living[(rotation_id, scenario_id)]
            for ag_year in sorted(years):
                shares[(rotation_id, scenario_id, ag_year)] = _year_share(
                    flags, fractions, ag_year, start_month
                )
    return shares


def year_shares(
    living: Mapping[tuple[str, str], Mapping[dt.date, Flag]],
    monthly_erosivity: Mapping[int, float | Missing],
    *,
    start_month: int,
) -> tuple[YearShare, ...]:
    """The erosivity-weighted share of each agricultural year without a living
    crop, per rotation and scenario (D211). ``living`` maps (rotation_id,
    scenario_id) to the daily flags of a living crop; ``monthly_erosivity``
    holds the twelve monthly erosivity values (C5.1); ``start_month`` is the
    start of the agricultural year (C5.4)."""
    shares = _exact_shares(living, monthly_erosivity, start_month)
    return tuple(
        YearShare(
            rotation_id,
            scenario_id,
            ag_year,
            None if isinstance(share, Missing) else float(share),
            share if isinstance(share, Missing) else None,
        )
        for (rotation_id, scenario_id, ag_year), share in sorted(shares.items())
    )


def _order_scenario(
    scenario_id: str,
    rotations: list[str],
    shares: dict[tuple[str, str, int], Fraction | Missing],
) -> ErosionOrder:
    """The order of one scenario. ``rotations``: those the flags hold for it."""
    of_scenario = {
        (rotation_id, ag_year): share
        for (rotation_id, scenario, ag_year), share in shares.items()
        if scenario == scenario_id
    }
    rotations = sorted(rotations)
    if len(rotations) < 2:
        return ErosionOrder(
            scenario_id,
            None,
            None,
            f"the scenario holds one rotation ('{rotations[0]}'): as in entry D0, a "
            "single rotation gives no order (OPEN of D0)",
        )
    if not of_scenario:
        listed = ", ".join(f"'{rotation_id}'" for rotation_id in rotations)
        return ErosionOrder(
            scenario_id,
            None,
            None,
            f"the flags of {listed} are empty: no agricultural year is read, so "
            "there is no share to order",
        )
    missing = sorted(
        (rotation_id, ag_year, share.reason)
        for (rotation_id, ag_year), share in of_scenario.items()
        if isinstance(share, Missing)
    )
    if missing:
        listed = "; ".join(
            f"'{rotation_id}' in {ag_year} ({reason})"
            for rotation_id, ag_year, reason in missing
        )
        return ErosionOrder(
            scenario_id,
            None,
            None,
            f"a rotation has no share in an agricultural year ({listed}): as in "
            "entry D0, a missing year gives no order; it is never filled or taken "
            "as zero",
        )
    exact = {}
    for rotation_id in rotations:
        values = [
            share
            for (rotation, _), share in of_scenario.items()
            if rotation == rotation_id
        ]
        exact[rotation_id] = sum(values, Fraction(0)) / len(values)
    means = tuple((rotation_id, float(exact[rotation_id])) for rotation_id in rotations)
    tied = [
        (first, second)
        for first, second in itertools.combinations(rotations, 2)
        if exact[first] == exact[second]
    ]
    if tied:
        listed = "; ".join(f"'{first}' and '{second}'" for first, second in tied)
        return ErosionOrder(
            scenario_id,
            means,
            None,
            f"the mean shares of {listed} are equal: as in entry D0, a tie gives no "
            "order",
        )
    order = tuple(sorted(rotations, key=lambda rotation_id: exact[rotation_id]))
    return ErosionOrder(scenario_id, means, order, None)


def erosion_orders(
    living: Mapping[tuple[str, str], Mapping[dt.date, Flag]],
    monthly_erosivity: Mapping[int, float | Missing],
    *,
    start_month: int,
) -> tuple[ErosionOrder, ...]:
    """The trivial comparator of E0 (D211): per scenario, the rotations
    ordered by the mean over agricultural years of the erosivity-weighted
    share of the year without a living crop, lowest first; or no order, with
    the reason."""
    shares = _exact_shares(living, monthly_erosivity, start_month)
    by_scenario = _rotations_by_scenario(living)
    return tuple(
        _order_scenario(scenario_id, by_scenario[scenario_id], shares)
        for scenario_id in sorted(by_scenario)
    )


def compare_with_soil_loss(
    living: Mapping[tuple[str, str], Mapping[dt.date, Flag]],
    monthly_erosivity: Mapping[int, float | Missing],
    table: ResultsTable,
    *,
    start_month: int,
) -> tuple[ErosionComparison, ...]:
    """The report of entry E0 (D211): per scenario, whether the order of the
    trivial comparator equals the order of the full ``soil_loss`` of the table
    by their mean over agricultural years, read in the direction of the row,
    ignoring ranges (``trivial_orders`` of the D0 comparator), and how many
    rotations each side ordered. The rotations of a scenario must be the same
    on both sides."""
    trivial = {
        item.scenario_id: item
        for item in erosion_orders(living, monthly_erosivity, start_month=start_month)
    }
    full = {
        item.scenario_id: item
        for item in trivial_orders(table)
        if item.indicator == SOIL_LOSS
    }
    rotations_of_table: dict[str, set[str]] = {}
    for row in table.rows:
        if row.indicator == SOIL_LOSS:
            rotations_of_table.setdefault(row.scenario_id, set()).add(row.rotation_id)
    items = []
    for scenario_id in sorted(set(trivial) | set(full)):
        rotations_of_flags = {r for r, s in living if s == scenario_id}
        if (
            scenario_id in trivial
            and scenario_id in full
            and rotations_of_flags != rotations_of_table[scenario_id]
        ):
            raise ValueError(
                f"scenario '{scenario_id}': the flags hold the rotations "
                f"{sorted(rotations_of_flags)} and the table "
                f"{sorted(rotations_of_table[scenario_id])}; an order is compared "
                "only over the same rotations"
            )
        ours = trivial.get(scenario_id) or ErosionOrder(
            scenario_id,
            None,
            None,
            f"the flags of a living crop hold no rotation of scenario '{scenario_id}'",
        )
        theirs = full.get(scenario_id)
        full_reason = (
            f"the table holds no '{SOIL_LOSS}' of scenario '{scenario_id}'"
            if theirs is None
            else theirs.reason
        )
        full_order = None if theirs is None else theirs.order
        if ours.order is None and full_order is None:
            outcome: Outcome = "no order from either"
        elif ours.order is None:
            outcome = "no order from the trivial comparator"
        elif full_order is None:
            outcome = "no order from the full method"
        elif ours.order == full_order:
            outcome = "equal"
        else:
            outcome = "different"
        items.append(
            ErosionComparison(
                scenario_id=scenario_id,
                trivial=ours,
                full=theirs,
                full_reason=full_reason,
                outcome=outcome,
                trivial_rotations_ordered=len(ours.order or ()),
                full_rotations_ordered=len(full_order or ()),
            )
        )
    return tuple(items)
