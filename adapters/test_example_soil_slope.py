"""Tests of ``ExampleSoilSlopeSource`` (unit l2/engine-runner, section 7).

The file served is the PLACEHOLDER example of contracts/inputs/examples/.
Variants are written only under ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.ports import SoilSlopeSource
from contracts.inputs import SiteSoilSlope

EXAMPLE = (
    Path(__file__).parent.parent
    / "contracts"
    / "inputs"
    / "examples"
    / "PLACEHOLDER_site_soil_slope.json"
)


def test_serves_the_placeholder_example_as_example():
    source: SoilSlopeSource = ExampleSoilSlopeSource(EXAMPLE)
    result = source.get_soil_slope("PLACEHOLDER-case", "PLACEHOLDER-field")
    assert isinstance(result.data, SiteSoilSlope)
    file = SiteSoilSlope.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    assert result.data == file.model_copy(
        update={"case_id": "PLACEHOLDER-case", "field_id": "PLACEHOLDER-field"}
    )
    assert result.source.state == "example"
    assert result.source.retrieved_at is None
    assert result.source.missing_reason is None
    assert result.source.id == source.source_id
    assert result.source.contract == source.contract == "site_data_soil_slope"


def test_the_path_has_no_default():
    with pytest.raises(TypeError):
        ExampleSoilSlopeSource()  # type: ignore[call-arg]


def check_unavailable(source: ExampleSoilSlopeSource, words: str) -> None:
    result = source.get_soil_slope("PLACEHOLDER-case", "PLACEHOLDER-field")
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "NOT_AVAILABLE"
    assert words in result.source.detail


def test_absent_file_is_unavailable(tmp_path):
    check_unavailable(
        ExampleSoilSlopeSource(tmp_path / "absent.json"), "cannot be read"
    )


def test_a_folder_is_unavailable(tmp_path):
    check_unavailable(ExampleSoilSlopeSource(tmp_path), "cannot be read")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not JSON",
        "[]",
        json.dumps({"PLACEHOLDER_KEY": "PLACEHOLDER_VALUE"}),
    ],
)
def test_invalid_file_is_unavailable(tmp_path, text):
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")
    check_unavailable(ExampleSoilSlopeSource(path), "does not load")


def test_file_that_is_not_utf8_is_unavailable(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff\xfe\x00")
    check_unavailable(ExampleSoilSlopeSource(path), "cannot be read")


def test_document_not_marked_as_example_is_refused(tmp_path):
    document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    document["example_data"] = False
    path = tmp_path / "not_example.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    check_unavailable(ExampleSoilSlopeSource(path), "not marked as example data")


# --- D38: the example stands in for any field ---------------------------------

FILE_IDS = ("PLACEHOLDER_FILE_CASE", "PLACEHOLDER_FILE_FIELD")


def write_example_with_own_ids(tmp_path: Path) -> Path:
    """The PLACEHOLDER example under identifiers no request uses."""
    document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    document["case_id"], document["field_id"] = FILE_IDS
    path = tmp_path / "example.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_each_request_gets_its_own_identifiers(tmp_path):
    path = write_example_with_own_ids(tmp_path)
    before = path.read_bytes()
    source = ExampleSoilSlopeSource(path)
    first = source.get_soil_slope("PLACEHOLDER_CASE_1", "PLACEHOLDER_FIELD_1")
    second = source.get_soil_slope("PLACEHOLDER_CASE_2", "PLACEHOLDER_FIELD_2")
    assert (first.data.case_id, first.data.field_id) == (
        "PLACEHOLDER_CASE_1",
        "PLACEHOLDER_FIELD_1",
    )
    assert (second.data.case_id, second.data.field_id) == (
        "PLACEHOLDER_CASE_2",
        "PLACEHOLDER_FIELD_2",
    )
    for result in (first, second):
        assert result.data.example_data is True
        assert result.source.state == "example"
        text = result.data.model_dump_json()
        assert all(identifier not in text for identifier in FILE_IDS)
    assert path.read_bytes() == before  # the file is never written


def test_everything_but_the_identifiers_is_the_file(tmp_path):
    path = write_example_with_own_ids(tmp_path)
    file = SiteSoilSlope.model_validate_json(path.read_text(encoding="utf-8"))
    served = ExampleSoilSlopeSource(path).get_soil_slope(
        "PLACEHOLDER_C", "PLACEHOLDER_F"
    )
    ids = {"case_id", "field_id"}
    assert served.data.model_dump(exclude=ids) == file.model_dump(exclude=ids)


def test_identifiers_the_model_refuses_are_unavailable(tmp_path):
    source = ExampleSoilSlopeSource(write_example_with_own_ids(tmp_path))
    result = source.get_soil_slope(" ", "PLACEHOLDER_FIELD")
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "NOT_AVAILABLE"
    assert "refused" in result.source.detail
