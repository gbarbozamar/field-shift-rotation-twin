"""The committed settings template loads into ``PowerSettings``.

``adapters/examples/PLACEHOLDER_power_settings.json`` is the shape a person
copies to write the real settings. Every value in it is a placeholder; this
test only keeps the documented shape from drifting from the code.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from adapters.power import ParameterSpec, PowerSettings

TEMPLATE = Path(__file__).parent / "examples" / "PLACEHOLDER_power_settings.json"


def test_the_placeholder_settings_file_loads():
    settings = PowerSettings.from_mapping(
        json.loads(TEMPLATE.read_text(encoding="utf-8"))
    )
    assert isinstance(settings, PowerSettings)


def test_the_placeholder_settings_file_has_every_setting_and_no_other():
    document = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert set(document) == {field.name for field in dataclasses.fields(PowerSettings)}
    for item in document["parameters"]:
        assert set(item) == {field.name for field in dataclasses.fields(ParameterSpec)}


def test_the_placeholder_settings_file_says_it_is_a_placeholder():
    document = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert ".invalid" in document["base_url"]
    for name in ("community", "attribution"):
        assert document[name].startswith("PLACEHOLDER")
    for item in document["parameters"]:
        assert item["source_parameter"].startswith("PLACEHOLDER")
        assert item["quantity"].startswith("placeholder")
        assert item["unit"].startswith("PLACEHOLDER")
