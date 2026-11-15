"""Acceptance test of unit l2/soil-loss-limit. PROPOSED (blueprint section 3.7).

Run from the repository root: ``uv run pytest economics/``.

Every number in this file is invented test data: no field, no record, no
source, and no soil-loss limit of any real field. Each expected verdict
follows from the PROPOSED rules of ``economics/README.md`` on those invented
numbers, so a reader checks it by hand; every expected verdict is PROPOSED.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
from pathlib import Path

import pytest

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import Value
from contracts.results.models import UNIT_SOIL_LOSS_ANNUAL
from economics import LimitAssessment, LimitCheck, assess_limit

UNIT = "t ha-1 yr-1"
LIMIT_SOURCE = Path(__file__).resolve().parent / "limit.py"

# Invented test data (not parameters, from no source).
TEST_LIMIT = 5.0


@dataclasses.dataclass(frozen=True)
class Level:
    """A soil-loss level with the three attributes assess_limit reads."""

    value: float | None
    reason: str | None = None
    detail: str | None = None


@dataclasses.dataclass(frozen=True)
class LevelWithUnit:
    """A soil-loss level that also carries a unit attribute."""

    value: float | None
    unit: str
    reason: str | None = None
    detail: str | None = None


def _limit(number: float | None, unit: str = UNIT) -> Value:
    if number is None:
        return Value.model_validate(
            {"value": None, "unit": unit, "missing": {"reason": "NOT_DECLARED"}}
        )
    return Value.model_validate(
        {
            "value": number,
            "unit": unit,
            "provenance": "DECLARED",
            "source": "user",
            "range_missing": {"reason": "NOT_DECLARED"},
        }
    )


def _absent(reason: str = "NO_COVERAGE") -> Level:
    return Level(value=None, reason=reason, detail="no year of this kind")


def _kinds(el_nino: Level, neutral: Level, la_nina: Level) -> dict:
    return {"el_nino": el_nino, "neutral": neutral, "la_nina": la_nina}


def _all_below() -> dict:
    return _kinds(Level(1.0), Level(2.0), Level(3.0))


def test_unit_matches_the_results_contract():
    assert UNIT == UNIT_SOIL_LOSS_ANNUAL
    assert KINDS_OF_YEAR == ("el_nino", "neutral", "la_nina")


# 1. All levels below the limit.
def test_all_below_the_limit_meets():
    result = assess_limit(_limit(TEST_LIMIT), Level(2.0), _all_below())
    assert isinstance(result, LimitAssessment)
    assert result.limit == TEST_LIMIT
    assert result.unit == UNIT
    assert result.on_average == LimitCheck("meets", None, None)  # PROPOSED
    assert result.every_kind == LimitCheck("meets", None, None)  # PROPOSED
    assert tuple(result.by_kind) == KINDS_OF_YEAR
    for check in result.by_kind.values():
        assert check.verdict == "meets"  # PROPOSED
    assert result.kinds_not_met == ()
    assert result.kinds_not_resolved == ()


# 2. Average below, la_nina above.
def test_one_kind_above_fails_every_kind_but_not_the_average():
    by_kind = _kinds(Level(1.0), Level(2.0), Level(7.5))
    result = assess_limit(_limit(TEST_LIMIT), Level(3.0), by_kind)
    assert result.on_average.verdict == "meets"  # PROPOSED
    assert result.every_kind.verdict == "does_not_meet"  # PROPOSED
    assert result.every_kind.reason is None
    assert result.every_kind.detail is None
    assert result.by_kind["la_nina"].verdict == "does_not_meet"  # PROPOSED
    assert result.by_kind["el_nino"].verdict == "meets"  # PROPOSED
    assert result.kinds_not_met == ("la_nina",)
    assert result.kinds_not_resolved == ()


def test_average_above_does_not_meet():
    result = assess_limit(_limit(TEST_LIMIT), Level(6.0), _all_below())
    assert result.on_average.verdict == "does_not_meet"  # PROPOSED
    assert result.every_kind.verdict == "meets"  # PROPOSED


def test_kinds_not_met_keep_the_order_of_kinds_of_year():
    by_kind = _kinds(Level(9.0), Level(1.0), Level(8.0))
    result = assess_limit(_limit(TEST_LIMIT), Level(4.0), by_kind)
    assert result.kinds_not_met == ("el_nino", "la_nina")


# 3. Exactly at the limit meets.
def test_level_exactly_at_the_limit_meets():
    by_kind = _kinds(Level(TEST_LIMIT), Level(1.0), Level(1.0))
    result = assess_limit(_limit(TEST_LIMIT), Level(TEST_LIMIT), by_kind)
    assert result.on_average.verdict == "meets"  # PROPOSED
    assert result.by_kind["el_nino"].verdict == "meets"  # PROPOSED
    assert result.every_kind.verdict == "meets"  # PROPOSED


def test_no_rounding_just_above_the_limit():
    just_above = TEST_LIMIT + 1e-9
    result = assess_limit(_limit(TEST_LIMIT), Level(just_above), _all_below())
    assert result.on_average.verdict == "does_not_meet"  # PROPOSED


def test_zero_limit_is_a_declared_limit():
    result = assess_limit(_limit(0.0), Level(0.0), _kinds(*[Level(0.5)] * 3))
    assert result.limit == 0.0
    assert result.on_average.verdict == "meets"  # PROPOSED
    assert result.every_kind.verdict == "does_not_meet"  # PROPOSED


# 4. Limit missing.
def test_limit_missing_resolves_nothing():
    result = assess_limit(_limit(None), Level(2.0), _all_below())
    assert result.limit is None
    assert result.unit == UNIT
    checks = [result.on_average, result.every_kind, *result.by_kind.values()]
    assert len(checks) == 2 + len(KINDS_OF_YEAR)
    for check in checks:
        assert check.verdict == "not_resolved"  # PROPOSED
        assert check.reason == "MISSING_INPUT"
        assert "NOT_DECLARED" in check.detail
        assert "soil-loss limit" in check.detail
    assert result.kinds_not_met == ()
    assert result.kinds_not_resolved == KINDS_OF_YEAR


# 5. el_nino missing NO_COVERAGE, others below.
def test_kind_missing_leaves_every_kind_not_resolved():
    by_kind = _kinds(_absent("NO_COVERAGE"), Level(2.0), Level(3.0))
    result = assess_limit(_limit(TEST_LIMIT), Level(2.0), by_kind)
    el_nino = result.by_kind["el_nino"]
    assert el_nino.verdict == "not_resolved"  # PROPOSED
    assert el_nino.reason == "MISSING_INPUT"
    assert "el_nino" in el_nino.detail
    assert "NO_COVERAGE" in el_nino.detail
    assert result.every_kind.verdict == "not_resolved"  # PROPOSED
    assert result.every_kind.reason == "MISSING_INPUT"
    assert "el_nino" in result.every_kind.detail
    assert "neutral" not in result.every_kind.detail
    assert result.kinds_not_resolved == ("el_nino",)
    assert result.kinds_not_met == ()
    assert result.on_average.verdict == "meets"  # PROPOSED


# 6. el_nino missing and neutral above.
def test_one_failing_kind_is_enough_even_with_one_not_resolved():
    by_kind = _kinds(_absent("NO_COVERAGE"), Level(6.0), Level(3.0))
    result = assess_limit(_limit(TEST_LIMIT), Level(2.0), by_kind)
    assert result.every_kind.verdict == "does_not_meet"  # PROPOSED
    assert result.every_kind.reason is None
    assert result.kinds_not_met == ("neutral",)
    assert result.kinds_not_resolved == ("el_nino",)


# 7. Average missing.
def test_average_missing_still_assesses_each_kind():
    by_kind = _kinds(Level(1.0), Level(2.0), Level(7.0))
    average = Level(value=None, reason="NOT_AVAILABLE", detail=None)
    result = assess_limit(_limit(TEST_LIMIT), average, by_kind)
    assert result.on_average.verdict == "not_resolved"  # PROPOSED
    assert result.on_average.reason == "MISSING_INPUT"
    assert "average" in result.on_average.detail
    assert "NOT_AVAILABLE" in result.on_average.detail
    assert result.by_kind["el_nino"].verdict == "meets"  # PROPOSED
    assert result.every_kind.verdict == "does_not_meet"  # PROPOSED
    assert result.kinds_not_met == ("la_nina",)


def test_level_with_the_right_unit_attribute_is_accepted():
    by_kind = {k: LevelWithUnit(1.0, UNIT) for k in KINDS_OF_YEAR}
    result = assess_limit(_limit(TEST_LIMIT), LevelWithUnit(1.0, UNIT), by_kind)
    assert result.every_kind.verdict == "meets"  # PROPOSED


# 8. Structural misuse.
@pytest.mark.parametrize(
    "by_kind",
    [
        {"el_nino": Level(1.0), "neutral": Level(1.0)},
        {**_all_below(), "drought": Level(1.0)},
        {},
    ],
    ids=["key_missing", "key_extra", "empty"],
)
def test_by_kind_keys_must_be_the_kinds_of_year(by_kind):
    with pytest.raises(ValueError, match="KINDS_OF_YEAR"):
        assess_limit(_limit(TEST_LIMIT), Level(1.0), by_kind)


def test_negative_limit_is_refused():
    with pytest.raises(ValueError, match="negative"):
        assess_limit(_limit(-1.0), Level(1.0), _all_below())


def test_limit_in_another_unit_is_refused():
    with pytest.raises(ValueError, match="unit"):
        assess_limit(_limit(TEST_LIMIT, "t ha-1 month-1"), Level(1.0), _all_below())


def test_missing_limit_in_another_unit_is_refused():
    with pytest.raises(ValueError, match="unit"):
        assess_limit(_limit(None, "kg ha-1"), Level(1.0), _all_below())


def test_level_with_another_unit_is_refused():
    by_kind = _all_below()
    by_kind["neutral"] = LevelWithUnit(1.0, "t ha-1 month-1")
    with pytest.raises(ValueError, match="unit"):
        assess_limit(_limit(TEST_LIMIT), Level(1.0), by_kind)
    with pytest.raises(ValueError, match="unit"):
        assess_limit(
            _limit(TEST_LIMIT), LevelWithUnit(1.0, "kg ha-1 yr-1"), _all_below()
        )


def test_limit_check_holds_reason_exactly_when_not_resolved():
    with pytest.raises(ValueError):
        LimitCheck("meets", "MISSING_INPUT", "x")
    with pytest.raises(ValueError):
        LimitCheck("not_resolved", None, None)
    with pytest.raises(ValueError):
        LimitCheck("not_resolved", "MISSING_INPUT", None)
    with pytest.raises(ValueError):
        LimitCheck("does_not_meet", None, "x")


# 9. No mutation, frozen results, no constant limit.
def test_inputs_are_not_mutated():
    limit = _limit(TEST_LIMIT)
    by_kind = _kinds(_absent(), Level(6.0), Level(3.0))
    limit_before = limit.model_dump(mode="json")
    by_kind_before = copy.deepcopy(by_kind)
    assess_limit(limit, Level(2.0), by_kind)
    assert limit.model_dump(mode="json") == limit_before
    assert by_kind == by_kind_before
    assert list(by_kind) == list(by_kind_before)


def test_results_are_frozen():
    result = assess_limit(_limit(TEST_LIMIT), Level(2.0), _all_below())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.limit = 1.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.on_average.verdict = "does_not_meet"
    with pytest.raises(TypeError):
        result.by_kind["el_nino"] = LimitCheck("meets", None, None)


def _is_number(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp):
        node = node.operand
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    )


def test_no_constant_limit_in_the_module():
    tree = ast.parse(LIMIT_SOURCE.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            names += [t.attr for t in targets if isinstance(t, ast.Attribute)]
            if node.value is not None and _is_number(node.value):
                offenders += [n for n in names if "limit" in n.lower()]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = node.args.defaults + [
                d for d in node.args.kw_defaults if d is not None
            ]
            if any(_is_number(d) for d in defaults):
                offenders.append(node.name)
    assert offenders == []
