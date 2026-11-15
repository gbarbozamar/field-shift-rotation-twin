"""The results table of the rotations of one field, built from their runs.

Q15 (b) of contracts/ENTRYPOINTS.md asks which code builds a ``ResultsTable``
"from several calls, and in which folder". PROPOSED here, for the route that
serves a decision output (``api/decisions.py``): the platform builds it, in
this module, from what ``RotationEngines.run`` returned for each rotation.

What it does, and nothing more:

- **Rows.** Each value of a ``ResultsPerRotation`` becomes one row, copied
  unchanged: indicator, direction, value, unit, range or ``range_missing``,
  ``missing``, provenance, source and assumption mark. Annual soil loss is a
  row per agricultural year; the monthly breakdown is not in the table
  (contracts/results/README.md). Water keeps its own time basis and
  agricultural year. The soil carbon trend is a row per rotation with its
  carbon model and computation. Nothing is computed, converted, filled,
  summed or left out.
- **Scenarios.** The route gives one result per phase of a rotation (D109,
  D132: ``phase_1`` ... ``phase_N``). Two rotations whose cycles differ have
  different phases, and every rotation of a table has the same cells,
  ``scenario_id`` included. D172 of issue #77: **every combination of one
  phase of each rotation is one scenario**, so D74 asks for robustness in
  every phase of each (D109). D172 leaves the form of the name to this unit:
  PROPOSED, the identifier of a scenario joins the phases it holds, in the
  order of the rotations of the request, with ``SCENARIO_SEPARATOR``
  (``phase_1+phase_2``); the legend travels in ``PairedScenario``.
- **No table** when a rotation has a phase without a result, when a part of
  a result is in the not-built form (D12; the results table has no form for
  it, contracts/results/README.md question 14), or when the runs of one
  scenario do not hold the same cells. The answer is then a typed absence
  whose detail names the rotation by its position in the request, never by
  an identifier the request carried.

Pure: no file, no network, no clock. It never imports ``engine/`` or
``decision/``.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from api.ports import EnginesResult, Missing
from contracts.results.models import (
    PartNotBuilt,
    ResultsPerRotation,
    ResultsTable,
    ResultsTableRow,
)

__all__ = [
    "SCENARIO_SEPARATOR",
    "PairedScenario",
    "PhaseOfRotation",
    "RotationRun",
    "TableAnswer",
    "build_results_table",
    "scenario_id_of",
]

# PROPOSED: the separator of the phases a scenario holds.
SCENARIO_SEPARATOR = "+"
# The identifier the route gives a run with no phases (api/rotations.py).
FIRST_PHASE = "phase_1"

# The fields of a value that a row copies unchanged (IndicatorValue).
VALUE_FIELDS = (
    "indicator",
    "direction",
    "value",
    "unit",
    "range",
    "range_missing",
    "missing",
    "provenance",
    "source",
    "assumption",
)

# PROPOSED detail texts: English for developers. They name a rotation by its
# position in the request (1, 2, ...) and a phase by the identifier the route
# gives it, never by an identifier or a value the request carried.
NO_RESULT = "the run of rotation {position} of the request holds no result in {phase}"
NOT_BUILT = (
    "the part '{part}' of rotation {position} of the request is in the not-built "
    "form in {phase} (D12); a results table has no form for a part whose engine "
    "is not built (contracts/results/README.md, question 14)"
)
OTHER_CELLS = (
    "in scenario {scenario}, the runs of the rotations do not hold the same cells "
    "(indicator, time basis, agricultural year, carbon model, computation); every "
    "rotation of a results table has the same cells (contracts/results/README.md)"
)


@dataclass(frozen=True)
class RotationRun:
    """What the engines returned for one rotation of the request."""

    rotation_id: str
    run: EnginesResult


@dataclass(frozen=True)
class PhaseOfRotation:
    """One phase of one rotation, as the route names it (``phase_1`` ...)."""

    rotation_id: str
    phase: str


@dataclass(frozen=True)
class PairedScenario:
    """One scenario of the table: the phase of each rotation it holds."""

    scenario_id: str
    phases: tuple[PhaseOfRotation, ...]


@dataclass(frozen=True)
class TableAnswer:
    """The table, or the reason there is none (never both, never neither)."""

    table: ResultsTable | None
    missing: Missing | None
    scenarios: tuple[PairedScenario, ...] = ()

    def __post_init__(self) -> None:
        if (self.table is None) == (self.missing is None):
            raise ValueError("TableAnswer: a table or a missing part, exactly one")
        if self.table is None and self.scenarios:
            raise ValueError("TableAnswer: scenarios belong to a table")


def scenario_id_of(phases: Sequence[str]) -> str:
    """The identifier of the scenario that holds these phases, in order. PROPOSED."""
    return SCENARIO_SEPARATOR.join(phases)


def _phases_of(run: EnginesResult) -> list[tuple[str, EnginesResult]]:
    """The phases of one run, as the route writes them: one item per phase, or
    the run itself as ``phase_1`` when the engines gave no phases."""
    if run.phases:
        return [(phase.scenario_id, phase.result) for phase in run.phases]
    return [(FIRST_PHASE, run)]


def _rows(result: ResultsPerRotation) -> list[dict[str, Any]]:
    """The rows of one result, without their ``scenario_id``. Copies only."""
    rows: list[dict[str, Any]] = []
    common = {"rotation_id": result.rotation_id}
    for item in result.soil_loss.annual:
        rows.append(
            {
                **common,
                "time_basis": "ag_year",
                "ag_year": item.ag_year,
                **{name: getattr(item, name) for name in VALUE_FIELDS},
            }
        )
    for item in result.water_deficit_exposure:
        rows.append(
            {
                **common,
                "time_basis": item.time_basis,
                "ag_year": item.ag_year,
                **{name: getattr(item, name) for name in VALUE_FIELDS},
            }
        )
    for item in result.soil_carbon_trend:
        rows.append(
            {
                **common,
                "time_basis": "rotation",
                "carbon_model": item.carbon_model,
                "computation": item.computation,
                **{name: getattr(item, name) for name in VALUE_FIELDS},
            }
        )
    return rows


def _cells(rows: Sequence[dict[str, Any]]) -> set[tuple]:
    """The cells of some rows, without the scenario."""
    return {
        (
            row["indicator"],
            row["time_basis"],
            row.get("ag_year"),
            row.get("carbon_model"),
            row.get("computation"),
        )
        for row in rows
    }


def build_results_table(
    case_id: str, field_id: str, runs: Sequence[RotationRun]
) -> TableAnswer:
    """The results table of the runs of the rotations of one field, or the
    reason there is none (module docstring).

    ``runs`` keeps the order of the request. A result whose ``case_id``,
    ``field_id`` or ``rotation_id`` is not the one expected, or a run without
    a result and without the reason of its absence, is a defect of the
    caller or of the engines: ``ValueError``.
    """
    if len(runs) < 2:
        raise ValueError("a results table for a decision holds two rotations or more")
    per_rotation: list[list[tuple[str, list[dict[str, Any]]]]] = []
    for position, item in enumerate(runs, start=1):
        phases = []
        for phase, run in _phases_of(item.run):
            result = run.result
            if result is None:
                if run.result_missing is None:
                    raise ValueError("a run without a result carries the reason")
                detail = NO_RESULT.format(position=position, phase=phase)
                if run.result_missing.detail:
                    detail = f"{detail}: {run.result_missing.detail}"
                return TableAnswer(
                    table=None,
                    missing=Missing(reason=run.result_missing.reason, detail=detail),
                )
            if (result.case_id, result.field_id, result.rotation_id) != (
                case_id,
                field_id,
                item.rotation_id,
            ):
                raise ValueError(
                    f"the result of rotation {position} does not carry the identifiers "
                    "of its request"
                )
            for part in ("soil_loss", "water_deficit_exposure", "soil_carbon_trend"):
                if isinstance(getattr(result, part), PartNotBuilt):
                    return TableAnswer(
                        table=None,
                        missing=Missing(
                            reason="NOT_AVAILABLE",
                            detail=NOT_BUILT.format(
                                part=part, position=position, phase=phase
                            ),
                        ),
                    )
            phases.append((phase, _rows(result)))
        per_rotation.append(phases)

    rows: list[ResultsTableRow] = []
    scenarios: list[PairedScenario] = []
    for combination in itertools.product(*per_rotation):
        scenario = scenario_id_of([phase for phase, _ in combination])
        if len({frozenset(_cells(phase_rows)) for _, phase_rows in combination}) > 1:
            return TableAnswer(
                table=None,
                missing=Missing(
                    reason="NOT_COMPUTABLE",
                    detail=OTHER_CELLS.format(scenario=scenario),
                ),
            )
        scenarios.append(
            PairedScenario(
                scenario_id=scenario,
                phases=tuple(
                    PhaseOfRotation(rotation_id=item.rotation_id, phase=phase)
                    for item, (phase, _) in zip(runs, combination, strict=True)
                ),
            )
        )
        for _, phase_rows in combination:
            rows.extend(
                ResultsTableRow(**row, scenario_id=scenario) for row in phase_rows
            )
    return TableAnswer(
        table=ResultsTable(case_id=case_id, field_id=field_id, rows=rows),
        missing=None,
        scenarios=tuple(scenarios),
    )
