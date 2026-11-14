"""Tests of ``SoilTableSource`` and its file loaders (unit l2/soil-tables).

Status: PROPOSED test cases (blueprint section 3.7). Every identifier, unit,
number and source here is a placeholder; the templates of
``adapters/examples/`` are served as they are, and variants are written only
under ``tmp_path``. No network.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from adapters.ports import SoilSlopeSource
from adapters.soil_tables import (
    SLOPE_DETAIL,
    SLOPE_UNIT,
    SOIL_TABLES_ID,
    SoilFileError,
    SoilTableSource,
    check_tables,
    load_soil_groups,
    load_soil_table,
    load_soil_tables,
)
from contracts.inputs import SiteSoilSlope

EXAMPLES = Path(__file__).parent / "examples"
TABLE = EXAMPLES / "PLACEHOLDER_soil_table.json"
GROUPS = EXAMPLES / "PLACEHOLDER_soil_groups.json"
CASE, FIELD = "PLACEHOLDER_CASE", "PLACEHOLDER_FIELD"
MOMENT = dt.datetime(1900, 1, 1, 12, 0, tzinfo=dt.UTC)
SECRET = "PLACEHOLDER_FILE_CONTENT_MARKER"


def template(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(tmp_path: Path, name: str, document: Any) -> Path:
    path = tmp_path / name
    path.write_text(
        document if isinstance(document, str) else json.dumps(document),
        encoding="utf-8",
    )
    return path


def present(quantity: str, value: float = 1.0) -> dict[str, Any]:
    return {
        "quantity": quantity,
        "value": value,
        "unit": "PLACEHOLDER_unit",
        "provenance": "DERIVED",
        "source": "PLACEHOLDER: example data, no real source",
        "range_missing": {"reason": "NOT_AVAILABLE"},
    }


def table(groups: dict[str, list[dict[str, Any]]], *, example: bool = False):
    return {
        "source": "PLACEHOLDER: dataset reference",
        "example_data": example,
        "groups": [
            {"soil_group": name, "soil_properties": rows}
            for name, rows in groups.items()
        ],
    }


def declarations(*entries: tuple[str, str, str], example: bool = False):
    return {
        "example_data": example,
        "declarations": [
            {"case_id": c, "field_id": f, "soil_group": g} for c, f, g in entries
        ],
    }


def source(tables: list[Path], groups: Path) -> SoilTableSource:
    return SoilTableSource(tables, groups, now=lambda: MOMENT)


def assert_unavailable(result, reason: str) -> str:
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == reason
    assert result.source.detail
    assert SECRET not in result.source.detail
    return result.source.detail


# --- 1: a declared field whose group is in the table --------------------------


def test_a_declared_field_gets_its_groups_properties_unchanged():
    soil: SoilSlopeSource = source([TABLE], GROUPS)
    result = soil.get_soil_slope(CASE, FIELD)
    data = result.data
    assert isinstance(data, SiteSoilSlope)
    again = SiteSoilSlope.model_validate(data.model_dump(mode="json"))
    assert again == data
    assert (data.case_id, data.field_id) == (CASE, FIELD)
    rows = template(TABLE)["groups"][0]
    assert rows["soil_group"] == "PLACEHOLDER_GROUP_A"
    assert [
        p.model_dump(mode="json", exclude_defaults=True) for p in data.soil_properties
    ] == [row for row in rows["soil_properties"]]
    assert result.source.id == soil.source_id == SOIL_TABLES_ID
    assert result.source.contract == soil.contract == "site_data_soil_slope"
    assert dict(result.source.request) == {
        "case_id": CASE,
        "field_id": FIELD,
        "soil_group": "PLACEHOLDER_GROUP_A",
    }
    assert result.source.attribution == template(TABLE)["source"]


def test_slope_is_missing_not_available_naming_d48():
    data = source([TABLE], GROUPS).get_soil_slope(CASE, FIELD).data
    for value in (data.slope_length, data.slope_steepness):
        assert value.value is None
        assert value.unit == SLOPE_UNIT
        assert value.missing.reason == "NOT_AVAILABLE"
        assert value.missing.detail == SLOPE_DETAIL
        assert "D48" in value.missing.detail
        assert value.provenance is None


def test_a_property_missing_in_the_table_stays_missing_with_its_reason():
    data = source([TABLE], GROUPS).get_soil_slope(CASE, FIELD).data
    by_quantity = {p.quantity: p for p in data.soil_properties}
    missing = by_quantity["placeholder_soil_property_b"]
    assert missing.value is None
    assert missing.missing.reason == "NO_COVERAGE"
    row = template(TABLE)["groups"][0]["soil_properties"][1]
    assert missing.missing.detail == row["missing"]["detail"]


def test_each_field_gets_its_own_group(tmp_path):
    data = source([TABLE], GROUPS).get_soil_slope(CASE, "PLACEHOLDER_FIELD_B").data
    assert data.field_id == "PLACEHOLDER_FIELD_B"
    assert [(p.quantity, p.value) for p in data.soil_properties] == [
        ("placeholder_soil_property_a", 2.0)
    ]


def test_the_identifiers_are_never_rewritten(tmp_path):
    groups = write(
        tmp_path,
        "groups.json",
        declarations(("OTHER_CASE", FIELD, "PLACEHOLDER_GROUP_A")),
    )
    result = source([TABLE], groups).get_soil_slope(CASE, FIELD)
    assert_unavailable(result, "NOT_DECLARED")
    data = source([TABLE], groups).get_soil_slope("OTHER_CASE", FIELD).data
    assert (data.case_id, data.field_id) == ("OTHER_CASE", FIELD)


# --- 2: several tables --------------------------------------------------------


def test_two_tables_are_merged_per_group_in_their_order(tmp_path):
    first = write(
        tmp_path,
        "a.json",
        table({"G1": [present("q_one", 1.0)], "G2": [present("q_one", 5.0)]}),
    )
    second = write(tmp_path, "b.json", table({"G1": [present("q_two", 2.0)]}))
    groups = write(
        tmp_path, "groups.json", declarations((CASE, FIELD, "G1"), (CASE, "F2", "G2"))
    )
    soil = source([first, second], groups)
    data = soil.get_soil_slope(CASE, FIELD).data
    assert [(p.quantity, p.value) for p in data.soil_properties] == [
        ("q_one", 1.0),
        ("q_two", 2.0),
    ]
    only_first = soil.get_soil_slope(CASE, "F2").data
    assert [(p.quantity, p.value) for p in only_first.soil_properties] == [
        ("q_one", 5.0)
    ]
    assert soil.get_soil_slope(CASE, FIELD).source.attribution == (
        "PLACEHOLDER: dataset reference; PLACEHOLDER: dataset reference"
    )
    assert soil.get_soil_slope(CASE, "F2").source.attribution == (
        "PLACEHOLDER: dataset reference"
    )


@pytest.mark.parametrize("example", [False, True])
def test_a_group_some_tables_do_not_list_is_said_in_the_detail(tmp_path, example):
    first = write(tmp_path, "a.json", table({"G1": [present("q_one")]}))
    second = write(tmp_path, "b.json", table({"G2": [present("q_two")]}))
    third = write(tmp_path, "c.json", table({"G2": [present("q_three")]}))
    groups = write(
        tmp_path, "g.json", declarations((CASE, FIELD, "G1"), example=example)
    )
    result = source([first, second, third], groups).get_soil_slope(CASE, FIELD)
    assert result.source.state == ("example" if example else "fresh")
    assert [p.quantity for p in result.data.soil_properties] == ["q_one"]
    assert result.source.detail.startswith("2 of the 3 soil tables do not list")
    assert "G1" not in result.source.detail


def test_a_group_every_table_lists_has_no_detail(tmp_path):
    first = write(tmp_path, "a.json", table({"G1": [present("q_one")]}))
    second = write(tmp_path, "b.json", table({"G1": [present("q_two")]}))
    groups = write(tmp_path, "g.json", declarations((CASE, FIELD, "G1")))
    result = source([first, second], groups).get_soil_slope(CASE, FIELD)
    assert result.source.detail is None


def test_the_same_quantity_in_two_tables_is_refused(tmp_path):
    first = write(tmp_path, "a.json", table({"G1": [present("q_one", 1.0)]}))
    second = write(tmp_path, "b.json", table({"G1": [present("q_one", 2.0)]}))
    with pytest.raises(SoilFileError, match="number 1 and 2"):
        check_tables([load_soil_table(first), load_soil_table(second)])
    groups = write(tmp_path, "groups.json", declarations((CASE, FIELD, "G1")))
    assert_unavailable(
        source([first, second], groups).get_soil_slope(CASE, FIELD), "NOT_AVAILABLE"
    )


def test_the_same_quantity_for_two_different_groups_is_fine(tmp_path):
    first = write(tmp_path, "a.json", table({"G1": [present("q_one")]}))
    second = write(tmp_path, "b.json", table({"G2": [present("q_one")]}))
    assert len(load_soil_tables([first, second])) == 2


# --- 3: every absence is an answer, never an exception, never zero ------------


def test_an_undeclared_field_is_not_declared():
    result = source([TABLE], GROUPS).get_soil_slope(CASE, "PLACEHOLDER_NOT_DECLARED")
    detail = assert_unavailable(result, "NOT_DECLARED")
    assert "declaration" in detail
    assert "PLACEHOLDER_NOT_DECLARED" not in detail  # a submitted value is not repeated


def test_a_group_no_table_lists_is_no_coverage_without_repeating_the_group():
    result = source([TABLE], GROUPS).get_soil_slope(
        CASE, "PLACEHOLDER_FIELD_NOT_IN_ANY_TABLE"
    )
    detail = assert_unavailable(result, "NO_COVERAGE")
    assert "PLACEHOLDER_GROUP_NOT_IN_ANY_TABLE" not in detail
    assert "listed by no soil table" in detail
    assert result.source.request["soil_group"] == "PLACEHOLDER_GROUP_NOT_IN_ANY_TABLE"


def test_a_table_file_absent_is_not_available(tmp_path):
    result = source([tmp_path / "absent.json"], GROUPS).get_soil_slope(CASE, FIELD)
    assert "does not exist" in assert_unavailable(result, "NOT_AVAILABLE")


def test_a_declaration_file_absent_is_not_available(tmp_path):
    result = source([TABLE], tmp_path / "absent.json").get_soil_slope(CASE, FIELD)
    assert "does not exist" in assert_unavailable(result, "NOT_AVAILABLE")


def _without(document: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in document.items() if k != key}


def _table_variants() -> list[Any]:
    base = template(TABLE)
    empty_unit = copy.deepcopy(base)
    empty_unit["groups"][0]["soil_properties"][0]["unit"] = ""
    no_reason = copy.deepcopy(base)
    del no_reason["groups"][0]["soil_properties"][1]["missing"]
    as_text = copy.deepcopy(base)
    as_text["groups"][0]["soil_properties"][0]["value"] = "1.0"
    twice = copy.deepcopy(base)
    twice["groups"][1]["soil_group"] = twice["groups"][0]["soil_group"]
    same_quantity = copy.deepcopy(base)
    rows = same_quantity["groups"][0]["soil_properties"]
    rows[1]["quantity"] = rows[0]["quantity"]
    unknown = {**base, SECRET: SECRET}
    empty_group = copy.deepcopy(base)
    empty_group["groups"][0]["soil_properties"] = []
    return [
        f"{{ {SECRET}",
        [SECRET],
        _without(base, "source"),
        _without(base, "example_data"),
        _without(base, "groups"),
        {**base, "source": " "},
        {**base, "example_data": "true"},
        {**base, "groups": {}},
        unknown,
        empty_unit,
        no_reason,
        as_text,
        twice,
        same_quantity,
        empty_group,
    ]


@pytest.mark.parametrize("document", _table_variants())
def test_a_malformed_table_is_not_available(tmp_path, document):
    path = write(tmp_path, "table.json", document)
    with pytest.raises(SoilFileError) as caught:
        load_soil_table(path)
    assert SECRET not in str(caught.value)
    result = source([path], GROUPS).get_soil_slope(CASE, FIELD)
    assert assert_unavailable(result, "NOT_AVAILABLE").startswith("soil table number 1")


def _groups_variants() -> list[Any]:
    base = template(GROUPS)
    twice = copy.deepcopy(base)
    twice["declarations"].append(dict(twice["declarations"][0]))
    blank = copy.deepcopy(base)
    blank["declarations"][0]["soil_group"] = ""
    return [
        f"{{ {SECRET}",
        [SECRET],
        _without(base, "example_data"),
        _without(base, "declarations"),
        {**base, "example_data": 1},
        {**base, "declarations": {}},
        {**base, SECRET: SECRET},
        twice,
        blank,
    ]


@pytest.mark.parametrize("document", _groups_variants())
def test_a_malformed_declaration_is_not_available(tmp_path, document):
    path = write(tmp_path, "groups.json", document)
    with pytest.raises(SoilFileError) as caught:
        load_soil_groups(path)
    assert SECRET not in str(caught.value)
    result = source([TABLE], path).get_soil_slope(CASE, FIELD)
    detail = assert_unavailable(result, "NOT_AVAILABLE")
    assert detail.startswith("soil-groups declaration")


def test_the_files_are_read_on_each_call(tmp_path):
    path = write(tmp_path, "table.json", template(TABLE))
    soil = source([path], GROUPS)
    assert soil.get_soil_slope(CASE, FIELD).data is not None
    path.write_text("not json", encoding="utf-8")
    assert_unavailable(soil.get_soil_slope(CASE, FIELD), "NOT_AVAILABLE")


def test_a_present_zero_in_the_table_is_served_as_it_is(tmp_path):
    """A zero written by a person is a value; the source neither adds nor drops one."""
    path = write(tmp_path, "table.json", table({"G1": [present("q_one", 0.0)]}))
    groups = write(tmp_path, "groups.json", declarations((CASE, FIELD, "G1")))
    data = source([path], groups).get_soil_slope(CASE, FIELD).data
    assert [(p.quantity, p.value) for p in data.soil_properties] == [("q_one", 0.0)]


# --- 4: example_data and the reported state -----------------------------------


@pytest.mark.parametrize(
    "table_example, groups_example, expected",
    [
        (False, False, False),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ],
)
def test_example_data_propagates_and_sets_the_state(
    tmp_path, table_example, groups_example, expected
):
    path = write(
        tmp_path, "t.json", table({"G1": [present("q_one")]}, example=table_example)
    )
    groups = write(
        tmp_path, "g.json", declarations((CASE, FIELD, "G1"), example=groups_example)
    )
    result = source([path], groups).get_soil_slope(CASE, FIELD)
    assert result.data.example_data is expected
    if expected:
        assert result.source.state == "example"
        assert result.source.retrieved_at is None
    else:
        assert result.source.state == "fresh"
        assert result.source.retrieved_at == MOMENT
    assert result.source.missing_reason is None


def test_an_example_table_listing_the_group_makes_the_document_example(tmp_path):
    first = write(tmp_path, "a.json", table({"G1": [present("q_one")]}))
    second = write(tmp_path, "b.json", table({"G1": [present("q_two")]}, example=True))
    groups = write(tmp_path, "g.json", declarations((CASE, FIELD, "G1")))
    result = source([first, second], groups).get_soil_slope(CASE, FIELD)
    assert result.data.example_data is True
    assert result.source.state == "example"


def test_an_example_table_not_listing_the_group_does_not_count(tmp_path):
    first = write(tmp_path, "a.json", table({"G1": [present("q_one")]}))
    second = write(tmp_path, "b.json", table({"G9": [present("q_two")]}, example=True))
    groups = write(tmp_path, "g.json", declarations((CASE, FIELD, "G1")))
    result = source([first, second], groups).get_soil_slope(CASE, FIELD)
    assert result.data.example_data is False
    assert result.source.state == "fresh"
    assert result.source.retrieved_at == MOMENT


def test_a_clock_without_a_time_zone_is_a_defect(tmp_path):
    path = write(tmp_path, "t.json", table({"G1": [present("q_one")]}))
    groups = write(tmp_path, "g.json", declarations((CASE, FIELD, "G1")))
    soil = SoilTableSource([path], groups, now=lambda: dt.datetime(1900, 1, 1))
    with pytest.raises(ValueError, match="time zone|timezone"):
        soil.get_soil_slope(CASE, FIELD)


# --- construction --------------------------------------------------------------


@pytest.mark.parametrize("tables", [TABLE, str(TABLE), [], [1]])
def test_construction_needs_a_sequence_of_paths(tables):
    with pytest.raises((TypeError, ValueError)):
        SoilTableSource(tables, GROUPS)


def test_construction_needs_a_groups_path_and_a_source_id():
    with pytest.raises(TypeError):
        SoilTableSource([TABLE], None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SoilTableSource([TABLE], GROUPS, source_id=" ")


def test_a_generator_of_paths_is_copied_before_it_is_checked():
    soil = SoilTableSource((path for path in [TABLE]), GROUPS, now=lambda: MOMENT)
    first = soil.get_soil_slope(CASE, FIELD)
    second = soil.get_soil_slope(CASE, FIELD)
    assert first.data is not None and second.data == first.data


def test_an_empty_group_is_refused_by_position(tmp_path):
    document = table({"PLACEHOLDER_SECRET_GROUP": []})
    path = write(tmp_path, "t.json", document)
    with pytest.raises(SoilFileError, match="group number 1") as caught:
        load_soil_table(path)
    assert "is empty" in str(caught.value)
    assert "PLACEHOLDER_SECRET_GROUP" not in str(caught.value)


def test_no_table_is_refused_by_the_loader():
    with pytest.raises(SoilFileError):
        load_soil_tables([])


# --- the templates ------------------------------------------------------------


def test_the_templates_are_placeholders_marked_as_example_data():
    soil_table, groups = template(TABLE), template(GROUPS)
    assert soil_table["example_data"] is True and groups["example_data"] is True
    assert soil_table["source"].startswith("PLACEHOLDER")
    for group in soil_table["groups"]:
        assert group["soil_group"].startswith("PLACEHOLDER")
        for row in group["soil_properties"]:
            assert row["quantity"].startswith("placeholder")
            assert row["unit"] == "PLACEHOLDER_unit"
    assert any(
        "missing" in row for g in soil_table["groups"] for row in g["soil_properties"]
    )
    for entry in groups["declarations"]:
        assert all(value.startswith("PLACEHOLDER") for value in entry.values())
