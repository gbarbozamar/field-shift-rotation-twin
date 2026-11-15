"""Acceptance tests of the tipping block over the real route (issue #267).

Unit ``l2/real-tipping``. The block under test runs the two rotations of
the demonstration of D128 through the real route (``demo/real.py``), at the
two levels of the residue-cover block of D75 that D115 decides, with the
phases nested inside each level (D117), and asserts the honest outcome the
brief's D176 conditions state:

- condition 3: **no tipping point**, because with the declared ``C``
  (D148, D158) EP1 does not read the cover and gives one figure for both
  rotations, and the only engine that reads the declared cover, the water
  balance (D110, D116), has no number yet (D157). The tests assert it on
  the route's own outputs: nothing the route computes moves between the
  levels, and on the repository's own inputs every row is missing with its
  reason, so no paired difference holds a value anywhere.
- condition 2: the upper level D115 leaves missing for the wheat rotation
  (no cap before a winter cereal) makes that member **not evaluated**, and
  is never read as a tipping point of the cover — the guard is tested on a
  structural table where the machinery alone would report a bracket.
- condition 4: the measured input of D10 and the check of D12 **wait** for
  a path that reruns the engines with the measured cover; the demo never
  calls ``recompute_with_measurement`` for the cover, and implements only
  the placement of a measured cover against the two levels.

Every value of the sweep comes from the route's own responses or is a
typed absence with its reason; nothing is hand-typed, nothing missing is
ever zero. The structural cases at the end use a made-up table and made-up
numbers for the rules alone, marked as such; no expected value of the
science is asserted anywhere.

The route runs in process on the engines and the catalogue of the
repository; when an engine the pair needs is not built, the tests skip, as
the tests of ``api/`` do. Run from the repository root::

    python -m pytest demo/
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts.results.models import (
    Missing,
    Range,
    ResultsTable,
    ResultsTableRow,
)
from decision.functions import (
    NOT_EVALUATED,
    ROBUST_PREFERENCE,
    UncertainInput,
    pair_state,
    tipping_point,
)

from demo import real


@pytest.fixture(autouse=True)
def the_engines_of_the_route_are_built() -> None:
    """The block runs the route, so it needs its engines; without them it
    skips, as the tests of ``api/`` do."""
    from api.engines import discover_engine_functions

    found = discover_engine_functions()
    if found.compute_soil_loss is None or found.build_rotation_calendar is None:
        pytest.skip("the engines the pair needs are not built")


# --- the committed inputs of the sweep -------------------------------------------


def test_the_rotations_are_the_committed_pair_of_the_demonstration() -> None:
    rotations = real.demo_rotations()
    assert [rotation["rotation_id"] for rotation in rotations] == list(real.PAIR)
    # The committed file of #363: the same case and field, two components on
    # one side and three on the other (D128, on the calendar of row USER-AP).
    for rotation in rotations:
        assert (rotation["case_id"], rotation["field_id"]) == (
            "example-case",
            "example-field-1",
        )
        assert rotation["example_data"] is True
    assert len(rotations[0]["components"]) == 1  # soybean with winter fallow
    assert len(rotations[1]["components"]) == 3  # wheat, soybean, maize


def test_the_levels_are_the_two_d115_decides() -> None:
    # Lower: 0 % (bare soil). Upper: the cap of the table for the sequence —
    # 0.40 for continuous soybean; the wheat rotation has none (the table
    # gives no cap before a winter cereal).
    assert real.LOWER_COVER == 0.0
    assert real.CAP_OF["soybean-winter-fallow"] == 0.40
    assert real.CAP_OF["wheat-soybean-maize"] is None
    assert "no cap" in real.NO_CAP_BEFORE_A_WINTER_CEREAL
    assert "before a winter cereal" in real.NO_CAP_BEFORE_A_WINTER_CEREAL
    assert "D115" in real.NO_CAP_BEFORE_A_WINTER_CEREAL


def test_the_catalogues_hold_only_the_records_of_the_level() -> None:
    from params.catalogue import check_catalogue, load_folder

    service = load_folder(real.PARAMETERS_FOLDER)[0]
    # The service catalogue drafts no cover record (engine/water/EXPOSURE.md:
    # "no record drafted"); only the demo's in-memory catalogues hold them.
    assert not any(
        record.get("id") == "surface_residue_cover" for record in service.values()
    )
    lower, upper = real.catalogue_at(0.0), real.catalogue_at(0.40)
    assert check_catalogue(lower) == [] and check_catalogue(upper) == []
    records_of = lambda catalogue: {  # noqa: E731
        (record["id"], tuple(sorted(record["scope"].items())))
        for record in catalogue.values()
        if record.get("id") == "surface_residue_cover"
    }
    from engine.water.exposure import SURFACE_RESIDUE_COVER

    # Lower: every fallow of both rotations bare, whatever crop follows it.
    assert records_of(lower) == {
        (SURFACE_RESIDUE_COVER, (("crop", crop), ("management", "no_crop")))
        for crop in ("soybean", "wheat", "maize")
    }
    assert all(
        record["value"] == 0.0
        for record in lower.values()
        if record.get("id") == SURFACE_RESIDUE_COVER
    )
    # Upper: the continuous-soybean cap alone (the only cap of the pair).
    assert records_of(upper) == {
        (SURFACE_RESIDUE_COVER, (("crop", "soybean"), ("management", "no_crop")))
    }
    cap = next(
        record
        for record in upper.values()
        if record.get("id") == SURFACE_RESIDUE_COVER
    )
    assert cap["value"] == 0.40
    assert "MGAP" in cap["citation"]["reference"]
    assert "Facultad de Agronom" in cap["citation"]["reference"]


# --- the runs through the route ---------------------------------------------------


def test_the_route_runs_the_phases_of_d109_for_both_rotations() -> None:
    # Soybean with winter fallow: one phase; wheat, second-crop soybean,
    # then maize: two (the per-phase route, D109/D132/D141).
    soybean = real.run_of("soybean-winter-fallow", 0.0)
    wheat = real.run_of("wheat-soybean-maize", 0.0)
    assert [phase.scenario_id for phase in soybean.phases] == ["phase_1"]
    assert [phase.scenario_id for phase in wheat.phases] == ["phase_1", "phase_2"]


def test_the_rotation_without_a_cap_does_not_run_at_the_upper_level() -> None:
    # Condition 2 at the source: the wheat rotation runs at 0 % only, and
    # asking for its upper level is refused with the reason of D115.
    with pytest.raises(ValueError) as raised:
        real.run_of("wheat-soybean-maize", 0.40)
    assert "no cap before a winter cereal" in str(raised.value)


def test_the_tables_of_the_levels_pair_the_phases_of_both_rotations() -> None:
    # D172: every combination of one phase of each rotation is one scenario.
    table_low, scenarios_low = real.level_table(0.0)
    table_cap, scenarios_cap = real.level_table(0.40)
    assert scenarios_low == (
        "cover-0/phase_1+phase_1",
        "cover-0/phase_1+phase_2",
    )
    assert scenarios_cap == (
        "cover-cap/phase_1+phase_1",
        "cover-cap/phase_1+phase_2",
    )
    assert len(table_low.rows) == len(table_cap.rows) == 32
    assert {row.scenario_id for row in table_low.rows} == set(scenarios_low)
    assert {row.scenario_id for row in table_cap.rows} == set(scenarios_cap)
    # Every rotation holds the same cells in every scenario (the contract).
    for table in (table_low, table_cap):
        cells = {
            (
                row.rotation_id,
                row.indicator,
                row.time_basis,
                row.ag_year,
                row.carbon_model,
                row.computation,
            )
            for row in table.rows
            if row.scenario_id.endswith("phase_1+phase_1")
        }
        assert len(cells) == 16  # 2 rotations x 8 cells (1 soil, 1 water, 6 carbon)


def test_the_rows_of_the_table_are_the_route_own_answers() -> None:
    # The rows are re-derived from a fresh answer of the route and compared
    # cell for cell: the table adds nothing to what the route answered.
    rotation = real.demo_rotations()[0]
    answer = real.post_the_route(real.client_at(0.0), rotation)
    from api.results_table import VALUE_FIELDS, _rows
    from contracts.results.models import ResultsPerRotation

    expected = {}
    for scenario in answer["scenarios"]:
        result = ResultsPerRotation.model_validate(scenario["result"])
        for row in _rows(result):
            key = (
                scenario["scenario_id"],
                row["indicator"],
                row.get("ag_year"),
                row.get("carbon_model"),
                row.get("computation"),
            )
            expected[key] = row
    table, _ = real.level_table(0.0)
    for row in table.rows:
        if row.rotation_id != rotation["rotation_id"]:
            continue
        # The table's scenario pairs one phase of each rotation (D172); the
        # soybean rotation is the first of the pair, so its phase is the
        # first part of the paired identifier.
        paired = row.scenario_id.removeprefix("cover-0/")
        phase = paired.split("+")[0]
        source = expected[
            (phase, row.indicator, row.ag_year, row.carbon_model, row.computation)
        ]
        for field in VALUE_FIELDS:
            assert getattr(row, field) == source[field], f"{row.indicator} {field}"


# --- condition 3: the honest outcome, on the route's own outputs -------------------


def test_nothing_the_route_computes_moves_between_the_levels() -> None:
    # The only difference between the two runs is the cover record of the
    # level; with the declared C (D148, D158) EP1 does not read it, and the
    # water balance (D110, D116) has no number yet (D157) — so the whole
    # result of the soybean rotation is the same at both levels, row for
    # row. This is the observed face of "erosion cannot move between the
    # levels".
    low = real.run_of("soybean-winter-fallow", 0.0).result
    cap = real.run_of("soybean-winter-fallow", 0.40).result
    assert low.model_dump() == cap.model_dump()


def test_every_row_of_the_route_is_missing_with_its_reason() -> None:
    # On the repository's own inputs (the chain examples) the route answers
    # no number: the ls factor is not computable (the example soil's
    # slope-length unit is the example's, not the metre of the LS records),
    # and the water and carbon records are not drafted. Missing with its
    # reason, never zero — the honest state of the route today.
    table, _ = real.level_table(0.0)
    for row in table.rows:
        assert row.value is None
        assert row.missing is not None
        assert row.missing.reason == "MISSING_INPUT"
        assert row.provenance is None  # C4.1: no label when missing
    soil = [row for row in table.rows if row.indicator == "soil_loss"]
    assert all("ls" in row.missing.detail for row in soil)
    water_rows = [
        row for row in table.rows if row.indicator == "water_deficit_exposure"
    ]
    assert all("no record in parameters" in row.missing.detail for row in water_rows)


def test_the_sweep_reads_both_levels_with_the_phases_nested() -> None:
    table = real.the_sweep_table()
    uncertain = real.the_uncertain_input(table)
    assert uncertain.unit == "fraction"
    assert uncertain.values == (
        (0.0, ("cover-0/phase_1+phase_1", "cover-0/phase_1+phase_2")),
        (0.40, ("cover-cap/phase_1+phase_1", "cover-cap/phase_1+phase_2")),
    )
    # The scenarios the mapping names are exactly the scenarios of the table.
    named = {item for _, scenarios in uncertain.values for item in scenarios}
    assert named == {row.scenario_id for row in table.rows}
    assert len(table.rows) == 64


def test_the_pair_is_not_evaluated_at_both_levels() -> None:
    # No paired difference holds a value at either level, so the pair has no
    # state (D85) at both levels — the honest state of the sweep today.
    assert real.the_states_at_levels() == ((0.0, None), (0.40, None))
    point = real.the_tipping_point()
    assert point.states == ((0.0, None), (0.40, None))


def test_the_honest_outcome_is_no_tipping_point_for_the_decided_reason() -> None:
    point = real.the_tipping_point()
    assert point.bracket is None
    assert point.guard is None
    # The machinery's own reason (D3): the state never changes.
    assert point.machinery_reason is not None
    assert "at every admitted value" in point.machinery_reason
    assert NOT_EVALUATED in point.machinery_reason
    # The decided reason of condition 3, verbatim in force.
    assert "declared C (D148, D158)" in point.reason
    assert "erosion cannot move between the levels" in point.reason
    assert "water balance (D110, D116)" in point.reason
    assert "no number yet (D157)" in point.reason
    assert "no tipping point" in point.reason
    # The observed reason: everything the route answers is missing.
    assert "missing with its reason" in point.reason


# --- condition 2: the level D115 leaves missing is not evaluated --------------------


def test_the_upper_level_of_the_rotation_without_a_cap_is_not_evaluated() -> None:
    # The wheat rotation's rows at the upper level are the typed absence
    # over the cells of its 0 % run: the identifiers, units and directions
    # stay, every value is missing with the reason of D115, and none is
    # ever zero. The member is not evaluated (state None, D85).
    table, _ = real.level_table(0.40)
    wheat = [
        row for row in table.rows if row.rotation_id == "wheat-soybean-maize"
    ]
    assert wheat
    for row in wheat:
        assert row.value is None
        assert row.missing is not None
        assert row.missing.reason == "MISSING_INPUT"
        assert row.missing.detail == real.NO_CAP_BEFORE_A_WINTER_CEREAL
    at_cap = ResultsTable(
        case_id=table.case_id,
        field_id=table.field_id,
        rows=[row for row in table.rows if row.scenario_id.startswith("cover-cap/")],
    )
    state = pair_state(at_cap, *real.PAIR)
    assert state.state is None
    # The cells of the member are still the cells of its 0 % run: nothing
    # is added, nothing leaves.
    low, _ = real.level_table(0.0)
    cells_of = lambda rows: {  # noqa: E731
        (row.indicator, row.time_basis, row.ag_year, row.carbon_model, row.computation)
        for row in rows
        if row.rotation_id == "wheat-soybean-maize"
        and row.scenario_id.endswith("phase_1+phase_1")
    }
    assert cells_of(table.rows) == cells_of(low.rows)


def test_a_missing_level_is_never_read_as_a_tipping_point() -> None:
    # The guard, on a structural table made for the rule (no science value
    # in it): the state at 0 % is a robust preference, the upper level is
    # not evaluated. The machinery alone would report the bracket between
    # the two levels; the sweep does not, per condition 2.
    def soil(
        rotation_id: str,
        scenario_id: str,
        ag_year: int,
        triple: tuple[float, float, float] | None,
    ) -> ResultsTableRow:
        value, low, high = triple or (None, None, None)
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=value,
            unit="t ha-1 yr-1",
            range=(
                Range(low=low, high=high, kind="PLACEHOLDER_kind")
                if triple is not None
                else None
            ),
            missing=(
                None
                if triple is not None
                else Missing(
                    reason="MISSING_INPUT", detail="the structural case's absence"
                )
            ),
            provenance="DERIVED" if triple is not None else None,
            source=(
                "the structural table of the guard, no science value"
                if triple is not None
                else None
            ),
        )

    table = ResultsTable(
        case_id="structural-case",
        field_id="structural-field",
        rows=[
            # At 0 %: wholly better for Y in the one phase — a robust preference.
            soil("X", "low/phase_1", 2020, (8.0, 7.9, 8.1)),
            soil("Y", "low/phase_1", 2020, (6.0, 5.9, 6.1)),
            # At the cap: Y holds no value — the member is not evaluated.
            soil("X", "cap/phase_1", 2020, (8.0, 7.9, 8.1)),
            soil("Y", "cap/phase_1", 2020, None),
        ],
    )
    uncertain = UncertainInput(
        name="structural cover",
        unit="fraction",
        cell=("X", "soil_loss", "ag_year", 2020, None, None),
        values=((0.0, ("low/phase_1",)), (0.4, ("cap/phase_1",))),
    )
    # The machinery alone reads a bracket off the missing level...
    machinery = tipping_point(table, "X", "Y", uncertain)
    assert machinery.states == ((0.0, ROBUST_PREFERENCE), (0.4, None))
    assert machinery.bracket == (0.0, 0.4)
    # ...and the sweep refuses it, with the reason of condition 2.
    sweep = real.the_tipping_point(
        table, uncertain, first_rotation="X", second_rotation="Y"
    )
    assert sweep.bracket is None
    assert sweep.guard is not None
    assert "condition 2" in sweep.guard
    assert "never read as a tipping point" in sweep.guard


# --- D4: the priority list over the same table --------------------------------------


def test_the_measurement_priority_of_the_cover() -> None:
    priority = real.the_measurement_priority()
    assert priority.base_state is None  # the pair is not evaluated (D85)
    assert len(priority.items) == 1
    item = priority.items[0]
    # The values of the cover never change the state (nothing computed can
    # move), so the input holds rank 2 (D4), with the states it was read from.
    assert item.rank == 2
    assert "surface residue cover" in item.input_name
    assert item.states == ((0.0, None), (0.40, None))
    assert "never change the state" in item.why
    assert NOT_EVALUATED in item.why
    # The one-cell gap of the PROPOSED form: the cover drives the water rows
    # of every rotation and phase, and the form holds one cell — the demo
    # names the water cell of the first rotation (the mapping says so).
    assert item.cell[:2] == (real.PAIR[0], "water_deficit_exposure")


# --- condition 4: what waits, and the placement the present path allows --------------


def test_the_wait_of_d10_and_d12_is_reported_not_faked() -> None:
    assert (
        "recompute_with_measurement (D10) rewrites a cell" in real.MEASURED_COVER_WAITS
    )
    assert "engines rerun with a new catalogue" in real.MEASURED_COVER_WAITS
    assert "never calls it for the cover" in real.MEASURED_COVER_WAITS
    assert "does not fake the rerun" in real.MEASURED_COVER_WAITS
    # The demo really never calls it: the name appears in the module only
    # inside the wait text, never as a call.
    source = Path(real.__file__).read_text(encoding="utf-8")
    assert "recompute_with_measurement(" not in source


def test_the_placement_of_a_measured_cover_against_the_levels() -> None:
    # Structural examples of the placement, not measurements: no measured
    # cover exists today, and none is invented. With the levels 0 % and the
    # cap, a cover lies inside the bracket unless above the cap.
    assert real.place_against_the_levels(0.2) == "inside the bracket"
    assert real.place_against_the_levels(0.0) == "inside the bracket"
    assert real.place_against_the_levels(0.40) == "inside the bracket"
    assert real.place_against_the_levels(0.5) == "above the bracket"
    assert real.place_against_the_levels(-0.1) == "below the bracket"


# --- the route's own decision document corroborates the sweep (D198) -----------------


def test_the_decision_route_serves_the_document_of_the_pair() -> None:
    # The same pair through POST /api/decisions/run (D198), on the catalogue
    # of the lower level: the document is served, its scenarios are the
    # phase combinations of D172, and its one pair is not evaluated — the
    # state the sweep read, from the route itself.
    client = real.client_at(0.0)
    climate = real.the_climate()
    rotation = real.demo_rotations()[0]
    body = {
        "site": {
            "case_id": rotation["case_id"],
            "field_id": rotation["field_id"],
            "latitude": climate.point.latitude.value,
            "longitude": climate.point.longitude.value,
        },
        "rotations": list(real.demo_rotations()),
    }
    response = client.post("/api/decisions/run", json=body)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["decision"] is not None, answer["decision_missing"]
    assert [s["scenario_id"] for s in answer["scenarios"]] == [
        "phase_1+phase_1",
        "phase_1+phase_2",
    ]
    (pair,) = answer["decision"]["pair_states"]
    assert pair["pair"] == list(real.PAIR)
    assert pair["value"] is None
    assert pair["missing"]["reason"] == "NOT_AVAILABLE"
    assert "not evaluated" in pair["missing"]["detail"]
    # The tipping block is not the route's document (the contract carries no
    # field for it): what the route serves and what the sweep reads agree on
    # the state of the pair.
    assert answer["decision"]["measure_first"] == []


# --- the report ----------------------------------------------------------------------


def test_main_prints_the_honest_report(capsys) -> None:
    real.main()
    printed = capsys.readouterr().out
    assert "the bracket of D3: None" in printed
    assert "declared C (D148, D158)" in printed
    assert "no number yet (D157)" in printed
    assert "'Not evaluated'" in printed
    assert "D10/D12:" in printed
    assert "never calls it for the cover" in printed
