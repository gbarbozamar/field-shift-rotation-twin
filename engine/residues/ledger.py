"""EP4 ``build_residue_ledger``: the residue ledger of one rotation of one field.

Unit l1/residue-ledger-ep4 (brief in issue #220; Q13 of
contracts/ENTRYPOINTS.md). Status: PROPOSED (blueprint section 3.7). Every
form below is written in ``README.md`` in this folder, with what stays OPEN.

What it does, in order:

1. The agricultural years: every whole agricultural year (C5.3, C5.5) of the
   days that every daily series of ``climate`` covers, cut by the calendar's
   start month: the years the platform gives ``CarbonForcing.horizon``
   (``api/carbon_forcing.py``).
2. The rotation repeated over the record (D47), with the helper of EP1,
   ``engine.calendar.repeat_over_record``.
3. One entry per component in each cycle. For a ``grain`` component (D129 (c)):

   - aboveground residue at harvest = ``residue_yield_ratio`` x ``crop_yield``;
   - exported = residue x ``residue_removed_fraction`` when the component
     declares its residue ``removed``; nothing when it declares
     ``left_on_surface`` or ``incorporated``; retained = residue - exported;
   - carbon of each = its mass x ``residue_carbon_fraction``, with retained
     carbon = produced carbon - exported carbon;
   - roots: ``root_mass_at_harvest``, and its carbon x ``root_carbon_fraction``;
   - rhizodeposits: ``rhizodeposit_carbon``.

   Every record is read by crop. A ``cover`` or ``pasture`` component has no
   yield, so none of its values is computed (``NOT_COMPUTABLE``, OPEN).
4. Per crop, purpose and part that enters the soil (retained aboveground
   carbon, root carbon, rhizodeposit carbon), one annual series: the sum over
   the components of that crop and purpose harvested in that agricultural
   year; a year in which none is harvested is zero.

An infeasible calendar makes every value ``NOT_COMPUTABLE`` (G4). A pure
function (G1): no file, no network, no clock, and its arguments are not changed.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import dataclass

from contracts.carbon_forcing.models import AnnualCarbonInputSeries, AnnualValue
from contracts.inputs.common import DateValue, Missing, Value
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.residue_ledger import LedgerComponent, NotGiven, ResidueLedger
from contracts.rotation_definition import (
    MissingManagementField,
    RotationComponent,
    RotationDefinition,
)
from engine.calendar.repeat import RepeatedComponent, repeat_over_record

from ._parameters import CARBON_UNIT, MASS_UNIT, Catalogue

__all__ = ["PARTS", "build_residue_ledger"]

FUNCTION = "engine.residues.build_residue_ledger"
DERIVED = "DERIVED"  # C4.3: a fixed formula of declared values
GRAIN = "grain"
REMOVED = "removed"
KEPT = ("left_on_surface", "incorporated")

# The parts of an entry that enter the soil, one annual series each.
PARTS = ("aboveground_carbon_retained", "root_carbon", "rhizodeposit_carbon")

# The pattern of ``QuantityId`` of contracts/inputs/common.py; ``origin`` and
# ``quantity`` of a series must follow it.
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_ONE_DAY = dt.timedelta(days=1)

NO_RANGE = Missing(
    reason="NOT_AVAILABLE",
    detail="no uncertainty range is propagated (Q6 of contracts/ENTRYPOINTS.md)",
)
LEAD_IN = (
    "nothing is laid out before the first cycle of the rotation repeated over "
    "the record (point 6 of engine/calendar/repeat.py), so a harvest on those "
    "days is not known"
)


# --- small numbers that may be missing --------------------------------------------


@dataclass(frozen=True)
class _Amount:
    """A number with how it was obtained, or missing with its reason."""

    number: float | None
    missing: Missing | None
    source: str

    def value(self, unit: str) -> Value:
        if self.number is None:
            return Value(value=None, unit=unit, missing=self.missing)
        return Value(
            value=self.number,
            unit=unit,
            provenance=DERIVED,
            source=self.source,
            range_missing=NO_RANGE,
        )


def _known(number: float, source: str) -> _Amount:
    return _Amount(number, None, source)


def _gone(reason: str, detail: str) -> _Amount:
    return _Amount(None, Missing(reason=reason, detail=detail), "")  # type: ignore[arg-type]


def _record(catalogue: Catalogue, name: str, crop_id: str) -> tuple[str, _Amount]:
    number = catalogue.value(name, crop_id)
    label = f"{name} of crop {crop_id!r}"
    if isinstance(number, Missing):
        return label, _Amount(None, number, "")
    return label, _known(number, f"{FUNCTION}: record {label} (DECLARED, C4.5)")


def _combine(
    what: str, formula: str, operands: list[tuple[str, _Amount]], number
) -> _Amount:
    """``what`` from its operands, or ``MISSING_INPUT`` naming each one missing (C3.3)."""
    absent = [(name, item.missing) for name, item in operands if item.missing]
    if absent:
        return _gone(
            "MISSING_INPUT",
            f"{what} = {formula} is not computed: "
            + "; ".join(
                f"{name} is missing ({gone.reason}: {gone.detail})"
                for name, gone in absent
            ),
        )
    return _known(
        number(*(item.number for _, item in operands)),
        f"{FUNCTION}: {what} = {formula} (PROPOSED; brief #220, D129 (c))",
    )


# --- the agricultural years ------------------------------------------------------


def _record_period(climate: SiteClimate) -> tuple[dt.date, dt.date] | Missing:
    """The days every daily series covers: latest start, earliest end."""
    if not climate.daily_series:
        return Missing(
            reason="MISSING_INPUT",
            detail="the period of the climate record: site data: climate has no daily series",
        )
    start = max(series.start_date for series in climate.daily_series)
    end = min(series.end_date for series in climate.daily_series)
    if end < start:
        return Missing(
            reason="NO_COVERAGE",
            detail="the daily series of site data: climate share no day",
        )
    return start, end


def _whole_years(
    start_month: int, first_day: dt.date, last_day: dt.date
) -> tuple[int, int] | None:
    """First and last agricultural year the days cover in full (C5.3, C5.5)."""
    first = first_day.year
    if first_day.replace(month=start_month, day=1) < first_day:
        first += 1
    after = last_day + _ONE_DAY
    last = (
        after.year
        if after.replace(month=start_month, day=1) <= after
        else after.year - 1
    )
    last -= 1
    return None if last < first else (first, last)


def _ag_year(day: dt.date, start_month: int) -> int:
    return day.year if day.month >= start_month else day.year - 1


# --- one entry ---------------------------------------------------------------------


def _residue_word(declared: RotationComponent) -> str | NotGiven:
    residue = declared.management.residue
    if isinstance(residue, MissingManagementField):
        return NotGiven(
            missing=Missing(
                reason=residue.missing.reason, detail=residue.missing.detail
            )
        )
    return residue


def _values(
    repeated: RepeatedComponent,
    declared: RotationComponent | None,
    catalogue: Catalogue,
    infeasible: Missing | None,
) -> dict[str, _Amount]:
    """The nine values of one entry, by the field names of ``LedgerComponent``."""
    names = (
        "aboveground_mass_produced",
        "aboveground_mass_exported",
        "aboveground_mass_retained",
        "aboveground_carbon_produced",
        "aboveground_carbon_exported",
        "aboveground_carbon_retained",
        "root_mass",
        "root_carbon",
        "rhizodeposit_carbon",
    )
    who = f"component {repeated.component_id!r}"
    if infeasible is not None:
        return {name: _Amount(None, infeasible, "") for name in names}
    if declared is None:
        detail = f"{who} of the calendar has no component in the rotation definition"
        return {name: _gone("MISSING_INPUT", detail) for name in names}
    if declared.purpose != GRAIN:
        detail = (
            f"{who} has purpose {declared.purpose!r}: the residue at harvest is "
            "computed from a yield (D129 (c)), which this purpose does not have, "
            "and no method is decided for it (OPEN 5 of engine/residues/README.md)"
        )
        return {name: _gone("NOT_COMPUTABLE", detail) for name in names}

    crop = repeated.crop_id
    ratio = _record(catalogue, "residue_yield_ratio", crop)
    crop_yield = _record(catalogue, "crop_yield", crop)
    carbon_fraction = _record(catalogue, "residue_carbon_fraction", crop)
    roots = _record(catalogue, "root_mass_at_harvest", crop)
    root_fraction = _record(catalogue, "root_carbon_fraction", crop)
    rhizodeposits = _record(catalogue, "rhizodeposit_carbon", crop)

    produced = _combine(
        "aboveground_mass_produced",
        "residue_yield_ratio x crop_yield",
        [ratio, crop_yield],
        lambda a, b: a * b,
    )
    residue = _residue_word(declared)
    if residue == REMOVED:
        exported = _combine(
            "aboveground_mass_exported",
            "aboveground_mass_produced x residue_removed_fraction",
            [
                ("aboveground_mass_produced", produced),
                _record(catalogue, "residue_removed_fraction", crop),
            ],
            lambda a, b: a * b,
        )
    elif residue in KEPT:
        exported = _known(
            0.0,
            f"{FUNCTION}: {who} declares its residue {residue!r}: nothing is "
            "exported (PROPOSED; brief #220)",
        )
    else:
        gone = residue.missing  # type: ignore[union-attr]
        exported = _gone(
            "MISSING_INPUT",
            f"aboveground_mass_exported is not computed: the residue of {who} "
            f"(management.residue of the rotation definition) is missing "
            f"({gone.reason}: {gone.detail})",
        )
    retained = _combine(
        "aboveground_mass_retained",
        "aboveground_mass_produced - aboveground_mass_exported",
        [
            ("aboveground_mass_produced", produced),
            ("aboveground_mass_exported", exported),
        ],
        lambda a, b: a - b,
    )
    carbon_produced = _combine(
        "aboveground_carbon_produced",
        "aboveground_mass_produced x residue_carbon_fraction",
        [("aboveground_mass_produced", produced), carbon_fraction],
        lambda a, b: a * b,
    )
    carbon_exported = _combine(
        "aboveground_carbon_exported",
        "aboveground_mass_exported x residue_carbon_fraction",
        [("aboveground_mass_exported", exported), carbon_fraction],
        lambda a, b: a * b,
    )
    carbon_retained = _combine(
        "aboveground_carbon_retained",
        "aboveground_carbon_produced - aboveground_carbon_exported",
        [
            ("aboveground_carbon_produced", carbon_produced),
            ("aboveground_carbon_exported", carbon_exported),
        ],
        lambda a, b: a - b,
    )
    root_carbon = _combine(
        "root_carbon",
        "root_mass_at_harvest x root_carbon_fraction",
        [roots, root_fraction],
        lambda a, b: a * b,
    )
    return {
        "aboveground_mass_produced": produced,
        "aboveground_mass_exported": exported,
        "aboveground_mass_retained": retained,
        "aboveground_carbon_produced": carbon_produced,
        "aboveground_carbon_exported": carbon_exported,
        "aboveground_carbon_retained": carbon_retained,
        "root_mass": roots[1],
        "root_carbon": root_carbon,
        "rhizodeposit_carbon": rhizodeposits[1],
    }


def _harvest(repeated: RepeatedComponent, calendar: RotationCalendar) -> DateValue:
    """The end date of the component in this cycle, with the calendar's label and source."""
    (original,) = [
        item
        for item in calendar.components
        if item.component_id == repeated.component_id
    ]
    end = original.end
    if repeated.end is None:
        return DateValue(date=None, missing=end.missing)
    source = end.source or "the calendar (assumption mark)"
    return DateValue(
        date=repeated.end,
        provenance=end.provenance,
        source=f"{source}; moved by {repeated.cycle} cycle(s) of the rotation "
        "repeated over the record (D47, engine/calendar/repeat.py)",
        assumption=end.assumption,
    )


def _entry(
    repeated: RepeatedComponent,
    declared: RotationComponent | None,
    calendar: RotationCalendar,
    catalogue: Catalogue,
    infeasible: Missing | None,
    start_month: int,
) -> LedgerComponent:
    values = _values(repeated, declared, catalogue, infeasible)
    if declared is None:
        absent = NotGiven(
            missing=Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"component {repeated.component_id!r} of the calendar has no "
                    "component in the rotation definition"
                ),
            )
        )
        purpose, residue = absent, absent
    else:
        purpose, residue = declared.purpose, _residue_word(declared)
    return LedgerComponent(
        component_id=repeated.component_id,
        crop_id=repeated.crop_id,
        cycle=repeated.cycle,
        purpose=purpose,
        residue_management=residue,
        harvest=_harvest(repeated, calendar),
        ag_year=None if repeated.end is None else _ag_year(repeated.end, start_month),
        **{
            name: amount.value(MASS_UNIT if "mass" in name else CARBON_UNIT)
            for name, amount in values.items()
        },
    )


# --- the annual series ---------------------------------------------------------------


def _possible_years(repeated: RepeatedComponent, start_month: int) -> range:
    """The agricultural years an undated harvest could fall in (point 7 of repeat.py)."""
    earliest = repeated.start or repeated.calendar_start
    return range(
        _ag_year(earliest, start_month),
        _ag_year(repeated.cycle_last_day, start_month) + 1,
    )


def _year_value(
    year: int,
    part: str,
    group: list[tuple[LedgerComponent, RepeatedComponent]],
    blockers: list[str],
    infeasible: Missing | None,
    described_from: dt.date,
    start_month: int,
) -> AnnualValue:
    if infeasible is not None:
        return AnnualValue(ag_year=year, value=None, missing=infeasible)
    problems = list(blockers)
    first_day = described_from.replace(year=year, month=start_month, day=1)
    if first_day < described_from:
        problems.append(
            f"the days of agricultural year {year} before "
            f"{described_from.isoformat()}: {LEAD_IN}"
        )
    total = 0.0
    for entry, repeated in group:
        who = f"component {entry.component_id!r} cycle {entry.cycle}"
        if entry.ag_year is None:
            if year in _possible_years(repeated, start_month):
                gone = entry.harvest.missing
                problems.append(
                    f"the harvest date of {who} is missing ({gone.reason}: "  # type: ignore[union-attr]
                    f"{gone.detail}), so it may fall in agricultural year {year}"  # type: ignore[union-attr]
                )
            continue
        if entry.ag_year != year:
            continue
        item: Value = getattr(entry, part)
        if item.value is None:
            problems.append(
                f"{part} of {who} is missing "
                f"({item.missing.reason}: {item.missing.detail})"  # type: ignore[union-attr]
            )
        else:
            total += item.value
    if problems:
        return AnnualValue(
            ag_year=year,
            value=None,
            missing=Missing(
                reason="MISSING_INPUT",
                detail=f"{part} of agricultural year {year} is not computed: "
                + "; ".join(problems),
            ),
        )
    return AnnualValue(ag_year=year, value=total)


def _series(
    entries: list[tuple[LedgerComponent, RepeatedComponent]],
    years: tuple[int, int],
    infeasible: Missing | None,
    described_from: dt.date,
    start_month: int,
) -> list[AnnualCarbonInputSeries]:
    blockers = [
        f"component {entry.component_id!r} cycle {entry.cycle} has no component in "
        "the rotation definition, so the crop and purpose it carries carbon for "
        "are not known"
        for entry, _ in entries
        if isinstance(entry.purpose, NotGiven)
    ]
    groups: dict[tuple[str, str], list[tuple[LedgerComponent, RepeatedComponent]]] = {}
    for entry, repeated in entries:
        if isinstance(entry.purpose, NotGiven) or not _IDENTIFIER.match(entry.crop_id):
            continue
        groups.setdefault((entry.crop_id, entry.purpose), []).append((entry, repeated))
    result: list[AnnualCarbonInputSeries] = []
    for (crop, purpose), group in groups.items():
        for part in PARTS:
            values = [
                _year_value(
                    year, part, group, blockers, infeasible, described_from, start_month
                )
                for year in range(years[0], years[1] + 1)
            ]
            header: dict[str, object] = {}
            if any(item.value is not None for item in values):
                header = {
                    "provenance": DERIVED,
                    "source": (
                        f"{FUNCTION}: sum of {part} over the components of crop "
                        f"{crop!r} with purpose {purpose!r} harvested in the "
                        "agricultural year; a year without such a harvest is zero "
                        "(PROPOSED; brief #220)"
                    ),
                    "range_missing": NO_RANGE,
                }
            result.append(
                AnnualCarbonInputSeries(
                    quantity=f"{crop}_{purpose}_{part}",
                    unit=CARBON_UNIT,
                    origin=crop,
                    first_ag_year=years[0],
                    last_ag_year=years[1],
                    years=values,
                    **header,
                )
            )
    return result


# --- the entry point -----------------------------------------------------------------


def _check_arguments(
    rotation: object, calendar: object, climate: object, parameters: object
) -> None:
    for name, item, kind in (
        ("rotation", rotation, RotationDefinition),
        ("calendar", calendar, RotationCalendar),
        ("climate", climate, SiteClimate),
    ):
        if not isinstance(item, kind):
            raise TypeError(
                f"{name}: expected a {kind.__name__}, got {type(item).__name__}"
            )
    if not isinstance(parameters, dict) or not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in parameters.items()
    ):
        raise TypeError("parameters: expected a dict[str, dict] (the catalogue)")
    for field in ("case_id", "field_id"):
        named = {getattr(item, field) for item in (rotation, calendar, climate)}
        if len(named) != 1:
            raise ValueError(
                f"rotation, calendar and climate name different {field} values (G5)"
            )


def _ledger(
    rotation: RotationDefinition,
    calendar: RotationCalendar,
    climate: SiteClimate,
    **parts: object,
) -> ResidueLedger:
    return ResidueLedger(
        contract="residue_ledger",
        example_data=(
            rotation.example_data or calendar.example_data or climate.example_data
        ),
        case_id=calendar.case_id,
        field_id=calendar.field_id,
        rotation_id=calendar.rotation_id,
        mass_unit=MASS_UNIT,
        carbon_unit=CARBON_UNIT,
        **parts,  # type: ignore[arg-type]
    )


def _no_years(
    rotation: RotationDefinition,
    calendar: RotationCalendar,
    climate: SiteClimate,
    why: Missing,
) -> ResidueLedger:
    return _ledger(
        rotation,
        calendar,
        climate,
        first_ag_year=None,
        last_ag_year=None,
        years_missing=why,
        components=[],
        annual_carbon_inputs=[],
    )


def _infeasible(calendar: RotationCalendar) -> Missing | None:
    if calendar.feasibility.feasible:
        return None
    rules: Iterable[str] = (item.rule for item in calendar.feasibility.violations)
    return Missing(
        reason="NOT_COMPUTABLE",
        detail="the calendar is infeasible (G4): it breaks "
        + ", ".join(repr(rule) for rule in dict.fromkeys(rules)),
    )


def build_residue_ledger(
    rotation: RotationDefinition,
    calendar: RotationCalendar,
    climate: SiteClimate,
    *,
    parameters: dict[str, dict],
) -> ResidueLedger:
    """The residue ledger of one rotation of one field. PROPOSED (EP4, Q13).

    Raises ``TypeError`` when an argument is not of its type and
    ``ValueError`` when the three arguments name different ``case_id`` or
    ``field_id`` (G5). Anything that cannot be computed is missing with its
    reason (G4).
    """
    _check_arguments(rotation, calendar, climate, parameters)

    start_month = calendar.ag_year_start.month
    if start_month is None:
        return _no_years(
            rotation,
            calendar,
            climate,
            Missing(
                reason="MISSING_INPUT",
                detail=(
                    "the start month of the agricultural year "
                    "(calendar.ag_year_start.month) is missing"
                ),
            ),
        )
    period = _record_period(climate)
    if isinstance(period, Missing):
        return _no_years(rotation, calendar, climate, period)
    years = _whole_years(start_month, *period)
    if years is None:
        return _no_years(
            rotation,
            calendar,
            climate,
            Missing(
                reason="NO_COVERAGE",
                detail=(
                    f"the climate record from {period[0].isoformat()} to "
                    f"{period[1].isoformat()} covers no whole agricultural year "
                    f"starting in month {start_month} (C5.3, C5.5)"
                ),
            ),
        )
    repeated = repeat_over_record(calendar, *period)
    if isinstance(repeated, Missing):  # only without a start month, checked above
        return _no_years(rotation, calendar, climate, repeated)

    catalogue = Catalogue(parameters)
    declared = {item.component_id: item for item in rotation.components}
    infeasible = _infeasible(calendar)
    entries = [
        (
            _entry(
                item,
                declared.get(item.component_id),
                calendar,
                catalogue,
                infeasible,
                start_month,
            ),
            item,
        )
        for item in repeated.components
    ]
    return _ledger(
        rotation,
        calendar,
        climate,
        first_ag_year=years[0],
        last_ag_year=years[1],
        components=[entry for entry, _ in entries],
        annual_carbon_inputs=_series(
            entries, years, infeasible, repeated.described_from, start_month
        ),
    )
