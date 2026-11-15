"""Acceptance test of units l2/saved-case-d177 (issue #251, D177) and
l0/saved-case-review-297 (brief #370).

The saved case of the thin matrix, ``demo/saved_cases/example-case.json``,
validates against the saved-case contract and every contract it carries;
every absence in it carries its reason code; and loading it back
reproduces the run's outputs exactly: the file is what the writer writes
today from the approved matrix, with the date and time the file names.
Since #297, its carbon items are complete and name their variant, and the
time is to the minute, in UTC.

Run from the repository root: ``python -m pytest demo/``.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import re
from typing import Any, get_args

from contracts.carbon_balance import CarbonBalance
from contracts.decision_output import DecisionOutput
from contracts.field_identity import FieldIdentity
from contracts.inputs.common import ReasonCode
from contracts.results.models import CARBON_MODELS, ResultsTable
from contracts.saved_case import SavedCase

from demo import matrix, run, saved_case

REASON_CODES = set(get_args(ReasonCode))


def _saved() -> SavedCase:
    return saved_case.read_saved_case()


def _text() -> str:
    # read_text reads line feeds whatever line ending the checkout gives the file.
    return saved_case.SAVED_CASE_FILE.read_text(encoding="utf-8")


def test_the_saved_case_validates_against_every_contract_it_carries() -> None:
    document = _saved()
    assert type(document) is SavedCase
    assert document.case_id == matrix.CASE_ID
    assert document.field_id == matrix.FIELD_ID
    assert type(document.field_identity) is FieldIdentity
    assert type(document.results_table) is ResultsTable
    assert type(document.decision_output) is DecisionOutput
    written = json.loads(_text())
    # Each part also loads into its own model on its own.
    FieldIdentity.model_validate(written["field_identity"])
    ResultsTable.model_validate(written["results_table"])
    DecisionOutput.model_validate(written["decision_output"])
    for item in written["carbon_balances"]:
        if item["carbon_balance"] is not None:
            CarbonBalance.model_validate(item["carbon_balance"])


def test_the_file_is_what_the_writer_writes_from_the_matrix() -> None:
    """Loading it back reproduces the run's outputs exactly (#251)."""
    document = _saved()
    rebuilt = saved_case.build_saved_case(
        document.saved_on, saved_case.read_field_identity()
    )
    assert rebuilt == document
    assert saved_case.saved_case_text(rebuilt) == _text()


def test_loading_it_back_gives_the_documents_of_the_run() -> None:
    document = _saved()
    assert document.results_table == matrix.thin_matrix()
    assert document.decision_output == run.build_decision_output()
    assert document.field_identity == saved_case.read_field_identity()


def test_the_carbon_items_are_complete_each_missing_with_its_reason() -> None:
    """D177 and #297: one item per rotation and carbon model, with its variant;
    no forcing, so no balance. AMG names the missing forcing; RothC is
    NOT_AVAILABLE (#297, change 3)."""
    items = _saved().carbon_balances
    assert [(item.rotation_id, item.carbon_model, item.variant) for item in items] == [
        (rotation_id, carbon_model, saved_case.VARIANT_OF[carbon_model])
        for rotation_id in matrix.ROTATIONS
        for carbon_model in CARBON_MODELS
    ]
    rotations_of_the_table = {row.rotation_id for row in matrix.thin_matrix().rows}
    assert set(matrix.ROTATIONS) == rotations_of_the_table
    for item in items:
        assert item.carbon_balance is None
        assert item.carbon_balance_missing is not None
        detail = item.carbon_balance_missing.detail
        assert f"rotation '{item.rotation_id}'" in detail
        assert {"amg": "EP5", "rothc": "EP6"}[item.carbon_model] in detail
        if item.carbon_model == "rothc":
            assert item.carbon_balance_missing.reason == "NOT_AVAILABLE"
        else:
            assert item.carbon_balance_missing.reason == "MISSING_INPUT"
            assert f"the CarbonForcing of rotation '{item.rotation_id}'" in detail


def test_the_variants_are_those_the_engines_write() -> None:
    """#297, change 2: the variant of each model is the VARIANT of its engine."""
    from engine.amg.entry import VARIANT as AMG_VARIANT
    from engine.rothc.entry import VARIANT as ROTHC_VARIANT

    assert saved_case.VARIANT_OF == {"amg": AMG_VARIANT, "rothc": ROTHC_VARIANT}


def _walk(node: Any, path: str = ""):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def test_every_absence_carries_its_reason_code() -> None:
    """C3.1, C3.2: a null value has a missing part with a reason; never a number."""
    written = json.loads(_text())
    checked = 0
    for path, node in _walk(written):
        if "value" in node and node["value"] is None:
            assert node.get("missing") is not None, path
            assert node["missing"]["reason"] in REASON_CODES, path
            checked += 1
        if node.get("missing") is not None and "value" in node:
            assert node["value"] is None, f"{path}: a number beside a reason"
        for key, value in node.items():
            if value is None and f"{key}_missing" in node and "value" not in node:
                missing = node[f"{key}_missing"]
                assert missing is not None, f"{path}.{key}"
                assert missing["reason"] in REASON_CODES, f"{path}.{key}"
                checked += 1
    assert checked > 0


def test_the_file_keeps_every_null() -> None:
    """D177: written with every null kept, never with exclude_none."""
    text = _text()
    assert '"carbon_balance": null' in text
    assert '"field_identity_missing": null' in text
    assert '"value": null' in text


def test_the_saved_case_is_example_data() -> None:
    """D177: true when a part it carries is example data."""
    document = _saved()
    assert document.example_data is True
    assert document.field_identity.example_data is True
    assert document.decision_output.example_data is True


def test_the_file_carries_the_time_it_was_saved_to_the_minute() -> None:
    """#297, change 3: date and time to the minute, in UTC, written as such."""
    assert re.search(r'\n  "saved_on": "\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z",\n', _text())
    saved_on = _saved().saved_on
    assert saved_on.utcoffset() == dt.timedelta(0)
    assert saved_on.second == 0 and saved_on.microsecond == 0


def test_the_date_is_the_writers() -> None:
    """D177: the date and time are given by whoever writes; building reads no clock."""
    assert "saved_on" in inspect.signature(saved_case.build_saved_case).parameters
    identity = saved_case.read_field_identity()
    first = saved_case.build_saved_case(
        dt.datetime(2001, 1, 1, 9, 0, tzinfo=dt.UTC), identity
    )
    second = saved_case.build_saved_case(
        dt.datetime(2001, 1, 1, 9, 1, tzinfo=dt.UTC), identity
    )
    assert first.model_dump(exclude={"saved_on"}) == second.model_dump(
        exclude={"saved_on"}
    )
    # Two saves of one day, a minute apart, are two cases (#297, change 3).
    assert first.saved_on != second.saved_on
    assert first.saved_on.date() == second.saved_on.date()


def test_main_writes_the_file_with_the_time_given(
    tmp_path, monkeypatch, capsys
) -> None:
    target = tmp_path / "saved_cases" / "example-case.json"
    monkeypatch.setattr(saved_case, "SAVED_CASE_FILE", target)
    assert saved_case.main(["2001-01-01T09:30Z"]) == 0
    written = saved_case.read_saved_case(target)
    assert written.saved_on == dt.datetime(2001, 1, 1, 9, 30, tzinfo=dt.UTC)
    assert '"saved_on": "2001-01-01T09:30Z"' in target.read_text(encoding="utf-8")
    assert "wrote example-case.json" in capsys.readouterr().out


def test_main_without_a_time_writes_the_time_it_is_run(
    tmp_path, monkeypatch, capsys
) -> None:
    target = tmp_path / "example-case.json"
    monkeypatch.setattr(saved_case, "SAVED_CASE_FILE", target)
    run_at = dt.datetime(2001, 1, 1, 9, 45, tzinfo=dt.UTC)
    monkeypatch.setattr(saved_case, "saved_now", lambda: run_at)
    assert saved_case.main([]) == 0
    assert saved_case.read_saved_case(target).saved_on == run_at
    assert "wrote example-case.json" in capsys.readouterr().out


def test_the_time_it_is_run_is_utc_to_the_minute() -> None:
    now = saved_case.saved_now()
    assert now.utcoffset() == dt.timedelta(0)
    assert now.second == 0 and now.microsecond == 0


def test_main_with_a_date_without_a_time_writes_nothing(
    tmp_path, monkeypatch, capsys
) -> None:
    target = tmp_path / "example-case.json"
    monkeypatch.setattr(saved_case, "SAVED_CASE_FILE", target)
    assert saved_case.main(["2001-01-01"]) == 2
    assert saved_case.main(["2001-01-01T09:30Z", "extra"]) == 2
    assert not target.exists()
    assert "usage" in capsys.readouterr().err
