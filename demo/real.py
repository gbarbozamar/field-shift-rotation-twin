"""The tipping block (D3, D4, D10, D12) over the real route (issue #267).

Unit ``l2/real-tipping``. The approved case of issue #267, confirmed by
decision D176 of issue #77: the uncertain input of the D3 sweep is **the
residue-cover block of D75 at the two levels of D115** — the bare 0 % level
and the cap of the table of D115 for the sequence — with **the phases of the
rotations nested inside each level** (D117, built in ``decision/`` by D166;
this module uses them and rebuilds nothing). The pair is the two rotations
of the demonstration of D128 (soybean with winter fallow; wheat,
second-crop soybean, then maize), the pair the interface of #363 sends to
the decision route, on the calendar of row USER-AP (D72).

How the real results are obtained — the check D176 condition 3 asks for:

- the rotations are read from the committed pair of #363
  (``web/src/data/demo_rotations_d128.json``), never re-typed here;
- each rotation, at each level, goes through the real route
  ``POST /api/rotations/run``, in process (``TestClient`` through
  ``api.main.create_app``, the same machinery the service builds: the
  engines found at their entry-point paths, the climate and the soil and
  slope of the chain examples of ``contracts/inputs/examples/`` — the only
  committed inputs of ``example-field-1`` — and the catalogue
  ``params/records/`` plus the cover records of the level);
- the runs behind the responses are rebuilt (``_run_behind``) from the
  per-phase results the route itself answered, and the tables of the
  levels are built by the platform's own builder
  (``api.results_table.build_results_table``), the same builder the
  decision route uses (D172: every combination of one phase of each
  rotation is one scenario);
  the tests also check the sweep against the route ``POST
  /api/decisions/run`` (D198), which serves the document of the same pair.

Each level of the cover is one catalogue (D115, D116 and
``engine/water/EXPOSURE.md``): the demo adds, in memory only, the
``surface_residue_cover`` records of the level — their values verbatim from
D115 (0 % for every fallow at the lower level; the cap of the table for the
sequence at the upper level), their citation the source D115 names. No
record is written to ``params/`` (a record there needs a person's
signature, and ``params/`` is not this unit's folder).

The levels, read off D115 verbatim:

- lower: 0 % (bare soil, FAO-56 with no mulch) — both rotations run;
- upper: the cap of the table for the sequence — **0.40** for continuous
  soybean (the soybean rotation); **missing** for the wheat rotation: the
  table gives no cap before a winter cereal, so for that rotation "only the
  0 % level runs and the upper level is missing with its reason" (D115).
  Per condition 2 of D176 that member is **not evaluated** at the upper
  level — its rows there are the typed absence over the cells of its 0 %
  run, never zero — and it is never read as a tipping point of the cover.
  (The other case D176 names, no row after alfalfa, is the third template
  of D72, not part of this pair.) The upper level of the sweep is the
  continuous-soybean cap, the only cap of the two sequences that exists.

The honest outcome this unit asserts (D176 condition 3): with the declared
``C`` (D148, D158) EP1 does not read the cover and gives one figure for
both rotations, so erosion cannot move between the levels; the only engine
that reads the declared cover is the water balance (D110, D116), which has
no number yet (D157). Until it has one, the expected result is **no tipping
point**, for that reason. The route's own outputs on the repository's
inputs make the outcome stronger still, and the demo reports it as
observed: every soil-loss row the route answers is missing with its reason
(the ``ls`` factor of the example soil is not computable — its slope-length
unit is the example's, not the metre of the LS records), every water row is
missing ``MISSING_INPUT`` naming the records not drafted, and so is every
carbon row; no paired difference holds a value at either level, the pair is
not evaluated at both levels, and the sweep reports no bracket. The soybean
rotation's outputs at the two levels are equal, row for row: nothing the
route computes today moves between the levels. When the water axis has a
number, this unit changes with it.

D10 and D12 (condition 4): the measured input of D10 and the check of D12
**wait** — the cover is an input of the engines, not a cell of the results
table, and a measured cover needs the engines rerun with a new catalogue;
``recompute_with_measurement`` (D10) rewrites a cell of the table instead,
so the demo never calls it for the cover and does not fake the rerun. What
the present path allows is implemented: the placement of a measured cover
against the two levels (the sides of D12) — with the levels 0 % and the
cap, a measured cover lies inside the bracket unless above the cap.

This module reads files of the repository (the committed rotations, the
examples, the catalogue through ``api.config``) and runs the route in
process; no network, no clock, no write. Run, from the repository root::

    python -m pytest demo/
    python -m demo.real
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
from api.config import PARAMETERS_FOLDER, load_parameters
from api.engines import count_values, result_values
from api.main import create_app
from api.ports import (
    EnginesResult,
    Missing as RunMissing,
    ModuleStatus,
    PhaseResult,
    RunSettings,
)
from api.results_table import RotationRun, build_results_table
from contracts.inputs import RotationCalendar, SiteClimate
from contracts.results.models import Missing, ResultsPerRotation, ResultsTable
from decision.functions import (
    NOT_EVALUATED,
    MeasurementPriority,
    TippingPoint,
    UncertainInput,
    measurement_priority,
    pair_state,
    tipping_point,
)
from engine.water import exposure as water

__all__ = [
    "CAP_OF",
    "UPPER_COVER",
    "LOWER_COVER",
    "MEASURED_COVER_WAITS",
    "PAIR",
    "SweepTippingPoint",
    "cover_record",
    "demo_rotations",
    "honest_reason",
    "level_table",
    "place_against_the_levels",
    "the_measurement_priority",
    "the_sweep_table",
    "the_tipping_point",
    "the_uncertain_input",
]

ROOT = Path(__file__).resolve().parent.parent
DEMO_ROTATIONS_FILE = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
CLIMATE_FILE = EXAMPLES / "PLACEHOLDER_chain_site_climate.json"
SOIL_FILE = EXAMPLES / "PLACEHOLDER_chain_site_soil_slope.json"

# The pair of the demonstration (D128, D72): first, second.
PAIR: tuple[str, str] = ("soybean-winter-fallow", "wheat-soybean-maize")

# The two levels of the residue-cover block of D75, as D115 decides them.
# Lower: bare soil for every fallow. Upper: the cap of the table for the
# sequence — 0.40 for continuous soybean; for the wheat rotation the table
# gives no cap before a winter cereal, so its upper level is missing (None)
# and that member is not evaluated (condition 2 of D176).
LOWER_COVER = 0.0
# The upper level of the sweep: the continuous-soybean cap, the only cap of
# the two sequences that exists.
UPPER_COVER = 0.40
CAP_OF: dict[str, float | None] = {
    "soybean-winter-fallow": 0.40,
    "wheat-soybean-maize": None,
}
# PROPOSED: the prefix that namespaces the scenarios of a level inside the
# one table the sweep reads, so the two levels never share a scenario_id.
LEVEL_PREFIX: dict[float, str] = {LOWER_COVER: "cover-0", UPPER_COVER: "cover-cap"}

# The crops the fallows of the two rotations are followed by (the scope the
# water engine looks the cover up with, D110/D115); at the lower level every
# fallow of both rotations is bare.
FOLLOWING_CROPS: tuple[str, ...] = ("soybean", "wheat", "maize")

# D115, verbatim on the missing upper level: "Where the table gives no cap
# (before a winter cereal) or has no row (after alfalfa), only the 0 %
# level runs and the upper level is missing with its reason."
NO_CAP_BEFORE_A_WINTER_CEREAL = (
    "decision D115 of issue #77: the table of the cover at sowing gives no "
    "cap before a winter cereal, so only the 0 % level runs for the rotation "
    "'wheat-soybean-maize' and its upper level is missing with this reason — "
    "the member is not evaluated at that level (condition 2 of the brief of "
    "issue #267) and is never read as a tipping point of the cover"
)

# Condition 4 of D176: what waits, and what the present path allows.
MEASURED_COVER_WAITS = (
    "The measured input of D10 and the check of D12 wait: the surface "
    "residue cover is an input of the engines (each level of the block of "
    "D75 is one catalogue, D115 with D116), not a cell of the results table, "
    "and recompute_with_measurement (D10) rewrites a cell of the table; a "
    "measured cover needs the engines rerun with a new catalogue of the "
    "measured cover, and no path of the platform does that yet, so the demo "
    "never calls it for the cover and does not fake the rerun. What the "
    "present path allows is the placement of a measured cover against the "
    "two levels (the sides of D12): with the levels 0 % and the cap, a "
    "measured cover lies inside the bracket unless above the cap. The state "
    "of the pair after the measurement waits with it."
)

# Condition 3 of D176, the decided reason the sweep cannot move.
DECLARED_C_REASON = (
    "with the declared C (D148, D158) EP1 does not read the cover and gives "
    "one figure for both rotations, so erosion cannot move between the levels"
)
WATER_NO_NUMBER_REASON = (
    "the only engine that reads the declared cover is the water balance "
    "(D110, D116), which has no number yet (D157): its records are not "
    "drafted, so every water row the route answers is missing with its reason"
)


# --- the committed inputs -------------------------------------------------------


@cache
def demo_rotations() -> tuple[dict[str, Any], dict[str, Any]]:
    """The two rotations of the demonstration of D128, as #363 committed them.

    Read from ``web/src/data/demo_rotations_d128.json`` (added by the
    interface lane at the request of the orchestrating session, checked by
    ``web/test_demo_rotations_d128.py`` against the pair DEMO_ROTATIONS of
    ``api/test_runner_residues.py`` and the calendar of row USER-AP, D72):
    the pair the interface sends to the decision route, never re-typed here.
    """
    rotations = tuple(json.loads(DEMO_ROTATIONS_FILE.read_text(encoding="utf-8")))
    if [rotation.get("rotation_id") for rotation in rotations] != list(PAIR):
        raise ValueError(
            "the committed file of the demonstration rotations does not hold "
            f"the pair {PAIR}: it holds "
            f"{[rotation.get('rotation_id') for rotation in rotations]}"
        )
    return rotations  # type: ignore[return-value]


@cache
def the_climate() -> SiteClimate:
    """The chain example climate, the only committed climate of the field."""
    return SiteClimate.model_validate_json(CLIMATE_FILE.read_text(encoding="utf-8"))


class _ExampleClimate:
    """The chain example climate behind the source of the route.

    The same stand-in ``api.test_phases.ChainClimate`` is: the example
    climate answers every request, with the source marked ``example``.
    """

    source_id = "chain-climate-example"
    contract = "site_data_climate"

    def __init__(self, data: SiteClimate) -> None:
        self._data = data

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return ClimateResult(
            data=self._data,
            source=SourceInfo(
                id=self.source_id, contract=self.contract, state="example"
            ),
        )


# --- the two catalogues (each level of D75 is one catalogue, D115) ---------------


def cover_record(scope: dict[str, str], value: float) -> dict[str, Any]:
    """One in-memory ``surface_residue_cover`` record of a level (D110, D115).

    The value and the source are D115's, verbatim; the record lives in the
    catalogue of the demo's runs only — nothing is written to ``params/``.
    The scope is the one the water engine looks the cover up with (D115:
    the crop sown after the fallow, with ``management: no_crop``).
    """
    return {
        "id": water.SURFACE_RESIDUE_COVER,
        "scope": scope,
        "value": value,
        "unit": "fraction",
        "range": None,
        "range_missing_reason": (
            "the two levels of the residue-cover block of D75 (D115) are a "
            "declared cap of a table and a bare-soil reading, not "
            "measurements, so no uncertainty range is given"
        ),
        "citation": {
            "reference": (
                "Technical update of the Uruguayan USLE/RUSLE model (MGAP "
                "and Facultad de Agronomía, hosted on gub.uy in January "
                "2020), Table 1: maximum cover at sowing by sequence"
            ),
            "locator": (
                "Table 1, as decision D115 of issue #77 reads it: continuous "
                "soybean 40 %; the lower level 0 % (bare soil, FAO-56 with "
                "no mulch)"
            ),
        },
        "transcribed_by": (
            "the demo of unit l2/real-tipping (issue #267), from decision "
            "D115 of issue #77"
        ),
        "checked_by": "the lead developer, in decision D115 of issue #77",
    }


def _scope_of(following_crop: str) -> dict[str, str]:
    """The scope of the cover of a fallow: no crop, and the crop that follows."""
    scope = dict(water.NO_CROP)
    scope[water.CROP_KEY] = following_crop
    return scope


@cache
def catalogue_at(level: float) -> dict[str, dict]:
    """The catalogue of one level of the cover (the service's plus its records).

    The lower level declares 0 % (bare soil) for every fallow of both
    rotations; the upper level declares the cap for the fallows of the
    rotations that have one — here the soybean rotation alone (0.40,
    continuous soybean). The records are checked as the service checks its
    own catalogue; a problem is a defect of this module.
    """
    from params.catalogue import check_catalogue

    catalogue = dict(load_parameters(PARAMETERS_FOLDER))
    if level == LOWER_COVER:
        covers = {crop: LOWER_COVER for crop in FOLLOWING_CROPS}
    else:
        covers = {
            crop: cap
            for rotation, cap in CAP_OF.items()
            if cap is not None
            for crop in _crops_of(rotation)
        }
    for crop, value in covers.items():
        name = f"demo/{water.SURFACE_RESIDUE_COVER}.{level}.{crop}.json"
        catalogue[name] = cover_record(_scope_of(crop), value)
    problems = check_catalogue(catalogue)
    if problems:
        raise ValueError(
            "the catalogue of the level holds a malformed record: "
            + "; ".join(problems)
        )
    return catalogue


def _crops_of(rotation_id: str) -> tuple[str, ...]:
    """The crops whose fallows a rotation's cover records name (its following
    crops), read off the committed definition, never re-typed."""
    rotation = next(
        item for item in demo_rotations() if item["rotation_id"] == rotation_id
    )
    return tuple(
        dict.fromkeys(component["crop_id"] for component in rotation["components"])
    )


@cache
def client_at(level: float) -> TestClient:
    """The route in process, on the catalogue of one level of the cover.

    ``create_app`` with no engines of its own discovers them at their
    entry-point paths, the way the service builds them, so the phases of
    D109 run (the runner lays them out with the phase functions of
    ``engine.calendar.repeat``; an engine tree without them runs phase 1
    only, and the route's own notes say so).
    """
    record = the_climate().daily_series[0]
    app = create_app(
        [],
        climate=_ExampleClimate(the_climate()),
        soil_slope=ExampleSoilSlopeSource(SOIL_FILE),
        settings=RunSettings(start_date=record.start_date, end_date=record.end_date),
        parameters=catalogue_at(level),
    )
    return TestClient(app, raise_server_exceptions=False)


# --- the runs through the route --------------------------------------------------


def post_the_route(client: TestClient, rotation: dict[str, Any]) -> dict[str, Any]:
    """``POST /api/rotations/run`` for one rotation: the route's own answer."""
    climate = the_climate()
    body = {
        "site": {
            "case_id": rotation["case_id"],
            "field_id": rotation["field_id"],
            "latitude": climate.point.latitude.value,
            "longitude": climate.point.longitude.value,
        },
        "rotation": rotation,
    }
    response = client.post("/api/rotations/run", json=body)
    if response.status_code != 200:
        raise ValueError(
            f"the route answered {response.status_code} for the rotation "
            f"'{rotation['rotation_id']}': {response.text}"
        )
    return response.json()


def _counted(result: ResultsPerRotation) -> dict[str, int]:
    counted = count_values(result_values(result))
    return {
        "values_present": counted.present,
        "values_missing": counted.missing,
    }


def _run_behind(answer: dict[str, Any]) -> EnginesResult:
    """The run behind one answer of the route, rebuilt phase by phase.

    Every result is the route's own (``ResultsPerRotation`` validated back
    from the response); the counts are recomputed with the runner's own
    ``count_values`` over them; the calendar and the module states are the
    response's. Nothing is edited, filled or converted.
    """
    phases = []
    for scenario in answer["scenarios"]:
        result = (
            ResultsPerRotation.model_validate(scenario["result"])
            if scenario["result"] is not None
            else None
        )
        missing = scenario["result_missing"]
        phases.append(
            PhaseResult(
                scenario_id=scenario["scenario_id"],
                first_ag_year=scenario["first_ag_year"],
                result=EnginesResult(
                    calendar=(
                        RotationCalendar.model_validate(scenario["calendar"])
                        if scenario["calendar"] is not None
                        else None
                    ),
                    result=result,
                    result_missing=(
                        RunMissing(
                            reason=missing["reason"], detail=missing["detail"]
                        )
                        if missing is not None
                        else None
                    ),
                    modules=tuple(
                        ModuleStatus(
                            id=item["id"],
                            state=item["state"],
                            reason=item.get("reason"),
                            detail=item.get("detail"),
                        )
                        for item in scenario["modules"]
                    ),
                    **(_counted(result) if result is not None else {}),
                ),
            )
        )
    first = phases[0].result
    return EnginesResult(
        calendar=first.calendar,
        result=first.result,
        result_missing=first.result_missing,
        modules=first.modules,
        values_present=first.values_present,
        values_missing=first.values_missing,
        phases=tuple(phases),
    )


@cache
def run_of(rotation_id: str, level: float) -> EnginesResult:
    """The run of one rotation at one level of the cover, through the route.

    Only the rotations D115 lets run at the level: the wheat rotation runs
    at the lower level alone (no cap before its winter cereal), and asking
    for its upper level is a defect of the caller.
    """
    rotation = next(
        item
        for item in demo_rotations()
        if item["rotation_id"] == rotation_id
    )
    if level != LOWER_COVER and CAP_OF[rotation_id] is None:
        raise ValueError(
            f"the rotation '{rotation_id}' does not run at the level {level}: "
            + NO_CAP_BEFORE_A_WINTER_CEREAL
        )
    return _run_behind(post_the_route(client_at(level), rotation))


def member_not_evaluated(run: EnginesResult) -> EnginesResult:
    """The member of a pair a level leaves missing (D115), as a typed absence.

    Every value of every phase of the rotation's own run at the level that
    runs (the lower one) becomes missing with the reason of D115 — the cells
    stay the rotation's real cells, the identifiers, units and directions
    stay, and no value is ever zero. This is condition 2 of D176: the level
    the table leaves missing makes that member not evaluated.
    """
    reason = Missing(reason="MISSING_INPUT", detail=NO_CAP_BEFORE_A_WINTER_CEREAL)

    def blank(item: Any) -> Any:
        return item.model_copy(
            update={
                "value": None,
                "range": None,
                "range_missing": None,
                "missing": reason,
                "provenance": None,
                "source": None,
                "assumption": False,
            }
        )

    def without_values(result: ResultsPerRotation) -> ResultsPerRotation:
        soil_loss = result.soil_loss
        if hasattr(soil_loss, "annual"):  # a result, not a not-built part
            soil_loss = soil_loss.model_copy(
                update={
                    "annual": [blank(item) for item in soil_loss.annual],
                    "monthly": [blank(item) for item in soil_loss.monthly],
                }
            )
        return result.model_copy(
            update={
                "soil_loss": soil_loss,
                "water_deficit_exposure": [
                    blank(item) for item in result.water_deficit_exposure
                ],
                "soil_carbon_trend": [
                    blank(item) for item in result.soil_carbon_trend
                ],
            }
        )

    def without_values_run(item: EnginesResult) -> EnginesResult:
        return EnginesResult(
            calendar=item.calendar,
            result=(
                without_values(item.result) if item.result is not None else None
            ),
            result_missing=item.result_missing,
            modules=item.modules,
            values_present=0,
            values_missing=item.values_missing,
        )

    phases = tuple(
        PhaseResult(
            scenario_id=phase.scenario_id,
            first_ag_year=phase.first_ag_year,
            result=without_values_run(phase.result),
        )
        for phase in run.phases
    )
    rebuilt = without_values_run(run)
    return EnginesResult(
        calendar=rebuilt.calendar,
        result=rebuilt.result,
        result_missing=rebuilt.result_missing,
        modules=rebuilt.modules,
        values_present=0,
        values_missing=rebuilt.values_missing,
        phases=phases,
    )


# --- the tables of the levels, and the one table of the sweep ---------------------


def _renamed(table: ResultsTable, prefix: str) -> ResultsTable:
    """The rows of a level's table, their scenarios namespaced by the level."""
    return ResultsTable(
        case_id=table.case_id,
        field_id=table.field_id,
        rows=[
            row.model_copy(update={"scenario_id": f"{prefix}/{row.scenario_id}"})
            for row in table.rows
        ],
    )


@cache
def level_table(level: float) -> tuple[ResultsTable, tuple[str, ...]]:
    """The results table of one level of the cover, and its scenarios.

    The scenarios are the phase combinations of D172 the platform's own
    builder pairs (``phase_1+phase_1``, ``phase_1+phase_2``), nested inside
    the level by D117; their ids carry the prefix of the level
    (``cover-0/``, ``cover-cap/``) so the two levels live in one table
    without sharing a scenario. At the upper level the member D115 leaves
    missing (the wheat rotation) is the typed absence of
    ``member_not_evaluated``; everything else is the route's own output.
    """
    first, second = PAIR
    case = demo_rotations()[0]["case_id"]
    field = demo_rotations()[0]["field_id"]
    runs = [RotationRun(rotation_id=first, run=run_of(first, level))]
    if level == LOWER_COVER:
        runs.append(RotationRun(rotation_id=second, run=run_of(second, level)))
    else:
        if CAP_OF[second] is not None:  # a rotation the table caps
            runs.append(RotationRun(rotation_id=second, run=run_of(second, level)))
        else:  # D115 leaves the level missing for it (condition 2)
            runs.append(
                RotationRun(
                    rotation_id=second,
                    run=member_not_evaluated(run_of(second, LOWER_COVER)),
                )
            )
    answer = build_results_table(case, field, runs)
    if answer.table is None:
        detail = answer.missing.detail if answer.missing is not None else ""
        raise ValueError(f"no results table at the level {level}: {detail}")
    prefix = LEVEL_PREFIX[level]
    return (
        _renamed(answer.table, prefix),
        tuple(f"{prefix}/{scenario.scenario_id}" for scenario in answer.scenarios),
    )


@cache
def the_sweep_table() -> ResultsTable:
    """The one table the sweep reads: both levels, phases nested (D117)."""
    rows: list[Any] = []
    for level in (LOWER_COVER, UPPER_COVER):
        table, _ = level_table(level)
        rows.extend(table.rows)
    rotation = demo_rotations()[0]
    return ResultsTable(
        case_id=rotation["case_id"], field_id=rotation["field_id"], rows=rows
    )


def the_uncertain_input(
    table: ResultsTable | None = None,
) -> UncertainInput:
    """The person's mapping of the residue cover onto the table (D103, D117).

    Each of the two values of the block of D75 names the scenarios of the
    phases at that level, nested inside it (D117: the state at a value is
    the state over all the phases at that value, D166/D175). ``cell`` is the
    form's one cell: the cover drives the water rows of every rotation and
    phase through the water balance (D110, D116) and no soil-loss cell while
    the declared C is in force (D158), so no single cell names what it
    drives — the same gap of the PROPOSED form ``demo/matrix.py`` reports
    for its input; the demo names the water cell of the first rotation, and
    the priority item says so.
    """
    table = the_sweep_table() if table is None else table
    first, second = PAIR
    water_row = next(
        row
        for row in table.rows
        if row.rotation_id == first and row.indicator == "water_deficit_exposure"
    )
    values = tuple(
        (level, level_table(level)[1]) for level in (LOWER_COVER, UPPER_COVER)
    )
    return UncertainInput(
        name="surface residue cover (the residue-cover block of D75, D115)",
        unit="fraction",
        cell=(
            first,
            water_row.indicator,
            water_row.time_basis,
            water_row.ag_year,
            None,
            None,
        ),
        values=values,
    )


# --- D3: the tipping point of the cover, with the guard of condition 2 ------------


def honest_reason(point: TippingPoint) -> str:
    """Why no tipping point is expected, as D176 condition 3 states it."""
    decided = (
        f"{DECLARED_C_REASON}; {WATER_NO_NUMBER_REASON}. Until the water "
        "axis has a number, the expected result is 'no tipping point', for "
        "that reason"
    )
    observed = (
        "observed on the repository's own inputs (the chain examples of "
        "contracts/inputs/examples/): every soil-loss, water and carbon row "
        "the route answers is missing with its reason, so no paired "
        "difference holds a value at either level and the pair is not "
        "evaluated at both levels"
    )
    parts = [decided, observed]
    if point.reason is not None:
        parts.append(f"the machinery's own reason: {point.reason}")
    return "; ".join(parts)


@dataclass(frozen=True)
class SweepTippingPoint:
    """The tipping point of the residue cover over the real route (D3), with
    the honest reason of the unit (condition 3) and the guard of condition 2.

    ``machinery`` is what ``tipping_point`` reports; ``bracket`` is it, unless
    the guard fired: a level whose state is None (a member not evaluated,
    D115 through condition 2) never anchors a bracket, so a bracket the
    machinery would read off a missing level is not reported as a tipping
    point of the cover. ``guard`` names the guard when it fired.
    """

    first_rotation: str
    second_rotation: str
    input_name: str
    unit: str
    states: tuple[tuple[float, str | None], ...]
    bracket: tuple[float, float] | None
    machinery_reason: str | None
    reason: str
    guard: str | None


def the_tipping_point(
    table: ResultsTable | None = None,
    uncertain_input: UncertainInput | None = None,
    *,
    first_rotation: str | None = None,
    second_rotation: str | None = None,
) -> SweepTippingPoint:
    """The tipping point of the residue cover, or the honest reason there is
    none (D3 with the conditions of D176).

    Called without arguments it sweeps the real table of the route with the
    mapping of the cover; the arguments let a caller sweep another table
    and mapping (the structural cases of the tests). The machinery
    (``tipping_point``) reads the state at each level over the phases
    nested inside it (D117, D166, D175). The guard of condition 2 then
    applies: a level without a state — the member D115 leaves missing is
    not evaluated — is never read as a tipping point of the cover, so a
    bracket it anchors is suppressed and said so.
    """
    table = the_sweep_table() if table is None else table
    first = PAIR[0] if first_rotation is None else first_rotation
    second = PAIR[1] if second_rotation is None else second_rotation
    if uncertain_input is None:
        uncertain_input = the_uncertain_input(table)
    point = tipping_point(table, first, second, uncertain_input)
    guard = None
    bracket = point.bracket
    if bracket is not None:
        state_of = dict(point.states)
        without_a_state = [value for value in bracket if state_of[value] is None]
        if without_a_state:
            guard = (
                "condition 2 of the brief of issue #267: the level(s) "
                f"{without_a_state} hold no state (a member not evaluated, "
                "D115), and such a level is never read as a tipping point of "
                "the cover, so the bracket the machinery read is not reported"
            )
            bracket = None
    reason = honest_reason(point)
    if guard is not None:
        reason = f"{guard}. {reason}"
    return SweepTippingPoint(
        first_rotation=first,
        second_rotation=second,
        input_name=uncertain_input.name,
        unit=uncertain_input.unit,
        states=point.states,
        bracket=bracket,
        machinery_reason=point.reason,
        reason=reason,
        guard=guard,
    )



# --- D4: the priority list over the same table ------------------------------------


def the_measurement_priority(
    table: ResultsTable | None = None,
) -> MeasurementPriority:
    """What to measure first, over the real table (D4).

    The only uncertain input is the cover; its two admitted values are the
    levels of D115. On the real outputs of today the state of the pair never
    changes between them (nothing computed can move: the declared C and the
    water axis without a number), so the input holds rank 2 — the honest
    outcome, with the states it was read from.
    """
    table = the_sweep_table() if table is None else table
    first, second = PAIR
    return measurement_priority(
        table, first, second, (the_uncertain_input(table),)
    )


# --- D10/D12: what waits (condition 4), and the placement the path allows ----------


def place_against_the_levels(
    measured: float, levels: tuple[float, float] = (LOWER_COVER, UPPER_COVER)
) -> str:
    """Where a measured cover lies against the two levels of the sweep (D12).

    The sides are D12's: below, inside or above the bracket. With the two
    levels 0 % and the cap, a measured cover lies inside the bracket unless
    above the cap (condition 4 of the brief). The placement is all of D12
    the present path allows; the state after the measurement waits for the
    rerun (``MEASURED_COVER_WAITS``). No measured cover exists today; the
    callers of this function say so themselves.
    """
    below, above = levels
    if measured < below:
        return "below the bracket"
    if measured > above:
        return "above the bracket"
    return "inside the bracket"


# --- the report -------------------------------------------------------------------


def the_states_at_levels() -> tuple[tuple[float, str | None], ...]:
    """The state of the pair at each level, over the phases at that level."""
    table = the_sweep_table()
    first, second = PAIR
    states = []
    for level in (LOWER_COVER, UPPER_COVER):
        wanted = set(level_table(level)[1])
        at_level = ResultsTable(
            case_id=table.case_id,
            field_id=table.field_id,
            rows=[row for row in table.rows if row.scenario_id in wanted],
        )
        states.append(
            (level, pair_state(at_level, first, second).state)
        )
    return tuple(states)


def main() -> None:
    """Print the honest report of the tipping block over the real route."""
    first, second = PAIR
    print(
        f"The tipping block (D3, D4, D10, D12) over the real route: the pair "
        f"('{first}', '{second}') of D128, the residue-cover block of D75 "
        "at the two levels of D115, phases nested by D117."
    )
    for level, scenarios in (
        (LOWER_COVER, level_table(LOWER_COVER)[1]),
        (UPPER_COVER, level_table(UPPER_COVER)[1]),
    ):
        print(f"  level {level}: the phases of the rotations in {scenarios}")
    for level, state in the_states_at_levels():
        print(f"  the state of the pair at {level}: '{state or NOT_EVALUATED}'")
    point = the_tipping_point()
    print(f"  the states the sweep read: {point.states}")
    print(f"  the bracket of D3: {point.bracket}")
    print(f"  {point.reason}")
    priority = the_measurement_priority()
    print(
        f"  D4: the base state over the whole admitted set is "
        f"'{priority.base_state or NOT_EVALUATED}'"
    )
    for item in priority.items:
        print(f"    rank {item.rank}: {item.input_name} — {item.why}")
    print(f"  D10/D12: {MEASURED_COVER_WAITS}")


if __name__ == "__main__":
    main()
