"""Tests of ``api/decision_layer.py``: the decision function found by name, and its checks.

Run with ``uv run pytest api/test_decision_layer.py`` from the repository root.

Status: PROPOSED test cases (unit ``l2/decision-route``). The decision function
is a fake that writes the smallest document the contract accepts (the
accepted case ``no-counts-no-differences`` of contracts/decision_output/): no
test asserts a value of the decision.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from api.decision_layer import (
    DECISION_FUNCTION,
    DECISION_MODULE,
    DiscoveredDecisionLayer,
    NamedDecisionLayer,
    check_document,
    discover_decision_function,
    import_named,
)
from api.ports import Missing
from api.test_results_table import FIRST, SECOND, build, result, run_of
from contracts.decision_output import DecisionOutput
from contracts.results.models import ResultsTable


def table() -> ResultsTable:
    return build(run_of(result(FIRST)), run_of(result(SECOND), result(SECOND))).table


def smallest_document(
    table: ResultsTable, *, example_data: bool, **changes
) -> DecisionOutput:
    """The smallest decision output the contract accepts for this table."""
    fields = {
        "contract": "decision_output",
        "example_data": example_data,
        "case_id": table.case_id,
        "field_id": table.field_id,
        "rotations": sorted({row.rotation_id for row in table.rows}),
        "scenarios": sorted({row.scenario_id for row in table.rows}),
        "limits": [],
        "counts_by_year": [],
        "range_across_scenarios": [],
        "paired_differences": [],
        "equal_tolerances": [],
        "pair_cell_counts": [],
        "pair_states": [],
        "state": {
            "value": None,
            "missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
            "indicators_not_resolved": [],
            "reasons": [],
        },
        "measure_first": [],
    }
    fields.update(changes)
    return DecisionOutput.model_validate(fields)


class FakeFunction:
    def __init__(self, answer=None, **changes):
        self.answer = answer
        self.changes = changes
        self.calls: list[tuple[ResultsTable, bool]] = []

    def __call__(self, table, *, example_data):
        self.calls.append((table, example_data))
        if self.answer is not None:
            return self.answer
        changes = {"example_data": example_data, **self.changes}
        return smallest_document(table, **changes)


# --- the function found by name ----------------------------------------------------


def test_the_name_the_platform_looks_for():
    assert (DECISION_MODULE, DECISION_FUNCTION) == (
        "decision.output",
        "assemble_decision_output",
    )


def test_a_module_that_does_not_exist_is_not_built():
    assert import_named("decision.PLACEHOLDER_absent_module", "f") is None
    assert import_named("PLACEHOLDER_absent_package.output", "f") is None


def test_a_function_that_does_not_exist_is_not_built():
    assert import_named("decision.functions", "PLACEHOLDER_absent_function") is None


def test_a_name_that_is_not_a_function_is_a_defect():
    # ``NOT_EVALUATED`` is a text constant of decision/functions.py.
    with pytest.raises(TypeError, match="not a function"):
        import_named("decision.functions", "NOT_EVALUATED")


def test_a_module_that_imports_something_absent_is_a_defect(tmp_path, monkeypatch):
    package = tmp_path / "PLACEHOLDER_decision_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "output.py").write_text(
        "import PLACEHOLDER_absent_dependency\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        with pytest.raises(ModuleNotFoundError):
            import_named("PLACEHOLDER_decision_pkg.output", "f")
    finally:
        for name in [
            n for n in sys.modules if n.startswith("PLACEHOLDER_decision_pkg")
        ]:
            del sys.modules[name]


def test_discovery_answers_a_function_or_none():
    found = discover_decision_function()
    assert found is None or callable(found)


def test_this_module_never_imports_decision_directly():
    text = (Path(__file__).parent / "decision_layer.py").read_text(encoding="utf-8")
    assert "from decision" not in text and "import decision" not in text


# --- the default: looked up on each request ---------------------------------------------


def test_the_default_layer_looks_the_function_up_on_each_request_not_before():
    calls: list[int] = []

    def discover():
        calls.append(1)
        return FakeFunction()

    layer = DiscoveredDecisionLayer(discover)
    assert calls == []
    assert isinstance(layer.decide(table(), example_data=True), DecisionOutput)
    assert isinstance(layer.decide(table(), example_data=True), DecisionOutput)
    assert len(calls) == 2


def test_the_default_layer_without_the_function_answers_not_available():
    answer = DiscoveredDecisionLayer(lambda: None).decide(table(), example_data=True)
    assert isinstance(answer, Missing) and answer.reason == "NOT_AVAILABLE"


def test_the_default_layer_lets_a_lookup_failure_reach_the_route():
    def discover():
        raise ModuleNotFoundError("PLACEHOLDER", name="PLACEHOLDER_absent_dependency")

    with pytest.raises(ModuleNotFoundError):
        DiscoveredDecisionLayer(discover).decide(table(), example_data=True)


# --- not built --------------------------------------------------------------------------


def test_not_built_answers_not_available_naming_the_function():
    answer = NamedDecisionLayer(None).decide(table(), example_data=True)
    assert isinstance(answer, Missing)
    assert answer.reason == "NOT_AVAILABLE"
    assert f"{DECISION_MODULE}.{DECISION_FUNCTION}" in answer.detail


# --- built ------------------------------------------------------------------------------


@pytest.mark.parametrize("example_data", [True, False])
def test_the_function_gets_the_table_and_the_example_mark(example_data):
    function = FakeFunction()
    given = table()
    answer = NamedDecisionLayer(function).decide(given, example_data=example_data)
    assert isinstance(answer, DecisionOutput)
    assert function.calls == [(given, example_data)]
    assert answer.example_data is example_data


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"case_id": "PLACEHOLDER_other"}, "another case"),
        ({"rotations": [FIRST, "PLACEHOLDER_other"]}, "rotations"),
        ({"scenarios": ["phase_1+phase_1"]}, "scenarios"),
        ({"example_data": False}, "example mark"),
    ],
)
def test_a_document_that_does_not_match_its_table_is_a_defect(changes, message):
    function = FakeFunction(**changes)
    with pytest.raises(TypeError, match=message):
        NamedDecisionLayer(function).decide(table(), example_data=True)


def test_an_answer_that_is_not_a_document_is_a_defect():
    with pytest.raises(TypeError, match="not DecisionOutput"):
        NamedDecisionLayer(FakeFunction(answer={"contract": "decision_output"})).decide(
            table(), example_data=True
        )


def test_a_document_built_without_validation_is_checked_again():
    """Everything the other checks read matches the table; only the contract
    refuses the document (a state with neither a value nor a missing part,
    C3.1), so only the validation done again can catch it."""
    from pydantic import ValidationError

    from contracts.decision_output import State

    given = table()
    fields = dict(smallest_document(given, example_data=True).__dict__)
    fields["state"] = State.model_construct(
        value=None, missing=None, indicators_not_resolved=[], reasons=[]
    )
    broken = DecisionOutput.model_construct(**fields)
    with pytest.raises(ValidationError, match="missing"):
        check_document(broken, given, example_data=True)


def test_what_the_function_raises_propagates():
    def raises(table, *, example_data):
        raise RuntimeError("PLACEHOLDER")

    with pytest.raises(RuntimeError):
        NamedDecisionLayer(raises).decide(table(), example_data=True)


def test_a_decision_function_that_is_not_callable_is_refused():
    with pytest.raises(TypeError):
        NamedDecisionLayer("PLACEHOLDER")  # type: ignore[arg-type]
