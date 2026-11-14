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
    assert result.data == SiteSoilSlope.model_validate_json(EXAMPLE.read_text())
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
