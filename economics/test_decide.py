"""Acceptance test of unit l2/decision-rule (S-015). PROPOSED (blueprint 3.7).

Run from the repository root: ``uv run pytest economics/``.

Every number in this file is invented test data: no field, no record, no
price, no source. The margins and the limit verdicts of the rotations A to E
are made up by hand; each expected answer follows from the PROPOSED rules of
``economics/README.md`` on those invented numbers, so a reader checks it by
hand. Every expected answer is PROPOSED.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
from pathlib import Path

import pytest

from contracts.economic_facts import KINDS_OF_YEAR
from economics import (
    Decision,
    LimitAssessment,
    LimitCheck,
    LimitCost,
    MarginResult,
    RotationOption,
    choose_rotation,
)

UNIT = "USD ha-1 yr-1"
DECIDE_SOURCE = Path(__file__).resolve().parent / "decide.py"

MEETS = LimitCheck("meets")
FAILS = LimitCheck("does_not_meet")
OPEN_CHECK = LimitCheck(
    "not_resolved", "MISSING_INPUT", "the soil loss on average is missing"
)


def _margin(value: float | None) -> MarginResult:
    if value is None:
        return MarginResult(
            value=None,
            reason="MISSING_INPUT",
            detail="the price of wheat (NOT_DECLARED)",
        )
    return MarginResult(value=value)


def _assessment(on_average: LimitCheck, every_kind: LimitCheck) -> LimitAssessment:
    """A LimitAssessment built by hand; by_kind follows every_kind."""
    by_kind = {kind: MEETS for kind in KINDS_OF_YEAR}
    if every_kind.verdict != "meets":
        by_kind[KINDS_OF_YEAR[0]] = every_kind
    first = (KINDS_OF_YEAR[0],)
    return LimitAssessment(
        limit=None,  # not read by choose_rotation
        unit="t ha-1 yr-1",
        on_average=on_average,
        every_kind=every_kind,
        by_kind=by_kind,
        kinds_not_met=first if every_kind.verdict == "does_not_meet" else (),
        kinds_not_resolved=first if every_kind.verdict == "not_resolved" else (),
    )


def _option(
    rotation_id: str,
    margin: float | None,
    on_average: LimitCheck,
    every_kind: LimitCheck | None = None,
) -> RotationOption:
    return RotationOption(
        rotation_id=rotation_id,
        margin=_margin(margin),
        limit=_assessment(on_average, every_kind or on_average),
    )


def _table() -> list[RotationOption]:
    """Five rotations A to E. Invented test data (margins in USD ha-1 yr-1)."""
    return [
        _option("A", 300.0, MEETS, FAILS),
        _option("B", 250.0, MEETS, MEETS),
        _option("C", 500.0, FAILS, FAILS),
        _option("D", 420.0, FAILS, FAILS),
        _option("E", 100.0, FAILS, FAILS),
    ]


def _states(decision: Decision) -> dict[str, str]:
    return {v.rotation_id: v.state for v in decision.options}


# 1. Five rotations, two meet on average: the one with more margin is chosen.
def test_chosen_on_average_and_cost_of_the_limit():
    decision = choose_rotation(_table(), "on_average")
    # PROPOSED expected answer: A (300) beats B (250); the best rotation that
    # does not meet is C (500), so meeting the limit costs 500 - 300 = 200.
    assert decision.answer == "chosen"
    assert decision.strictness == "on_average"
    assert decision.chosen == "A"
    assert decision.reason is None
    assert decision.detail is None
    assert decision.tied == ()
    assert _states(decision) == {
        "A": "chosen",
        "B": "meets",
        "C": "does_not_meet",
        "D": "does_not_meet",
        "E": "does_not_meet",
    }
    cost = decision.limit_cost
    assert cost.value == 200.0
    assert cost.unit == UNIT
    assert cost.against == "C"
    assert cost.costs_nothing is False
    assert cost.reason is None
    assert cost.detail is None


# 2. Every kind of year: A no longer meets, so B is chosen.
def test_every_kind_changes_the_answer():
    decision = choose_rotation(_table(), "every_kind")
    # PROPOSED expected answer: only B meets in every kind; cost 500 - 250 = 250.
    assert decision.answer == "chosen"
    assert decision.strictness == "every_kind"
    assert decision.chosen == "B"
    assert _states(decision)["A"] == "does_not_meet"
    assert _states(decision)["B"] == "chosen"
    assert decision.options[0].limit_check == FAILS
    assert decision.limit_cost.value == 250.0
    assert decision.limit_cost.against == "C"


# 3. None meets.
def test_none_meets():
    options = [
        _option("A", 300.0, FAILS),
        _option("B", 250.0, FAILS),
        _option("C", None, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: none_meets, nothing chosen, no cost.
    assert decision.answer == "none_meets"
    assert decision.chosen is None
    assert decision.reason == "NOT_APPLICABLE"
    assert decision.detail == "every rotation loses more soil than the limit on average"
    assert decision.tied == ()
    assert set(_states(decision).values()) == {"does_not_meet"}
    cost = decision.limit_cost
    assert cost.value is None
    assert cost.against is None
    assert cost.costs_nothing is False
    assert cost.reason == "NOT_APPLICABLE"
    assert cost.detail


def test_none_meets_in_every_kind_says_so():
    # A meets on average but not in every kind; B fails both.
    options = [_option("A", 300.0, MEETS, FAILS), _option("B", 250.0, FAILS)]
    decision = choose_rotation(options, "every_kind")
    # PROPOSED expected answer: none_meets; the detail names the kinds per option.
    assert decision.answer == "none_meets"
    kind = KINDS_OF_YEAR[0]
    assert decision.detail == (
        "every rotation loses more soil than the limit in at least one kind of "
        f"year: A ({kind}); B ({kind})"
    )


def test_no_candidate_but_one_not_resolved_is_not_resolved():
    options = [_option("A", 300.0, FAILS), _option("B", 50.0, OPEN_CHECK)]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: B could meet, so the answer is not resolved.
    assert decision.answer == "not_resolved"
    assert decision.chosen is None
    assert decision.reason == "MISSING_INPUT"
    assert "B" in decision.detail
    assert decision.limit_cost.value is None
    assert decision.limit_cost.costs_nothing is False
    assert decision.limit_cost.reason == "NOT_COMPUTABLE"


# 4. Two candidates tied at the best margin.
def test_tie_at_the_best_margin_is_not_resolved():
    options = [
        _option("A", 300.0, MEETS),
        _option("B", 120.0, MEETS),
        _option("C", 300.0, MEETS),
        _option("D", 500.0, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: A and C cannot be separated.
    assert decision.answer == "not_resolved"
    assert decision.chosen is None
    assert decision.reason == "NOT_COMPUTABLE"
    assert decision.tied == ("A", "C")
    assert "cannot separate" in decision.detail
    assert _states(decision) == {
        "A": "meets",
        "B": "meets",
        "C": "meets",
        "D": "does_not_meet",
    }
    assert decision.limit_cost.value is None
    assert decision.limit_cost.costs_nothing is False


def test_a_tie_below_the_best_does_not_block():
    options = [
        _option("A", 300.0, MEETS),
        _option("B", 120.0, MEETS),
        _option("C", 120.0, MEETS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: A, the single best.
    assert decision.answer == "chosen"
    assert decision.chosen == "A"
    assert decision.tied == ()


# 5. A candidate with a missing margin.
def test_candidate_with_missing_margin_is_not_resolved():
    options = [
        _option("A", 300.0, MEETS),
        _option("B", None, MEETS),
        _option("C", 500.0, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: not resolved, naming B and its reason.
    assert decision.answer == "not_resolved"
    assert decision.chosen is None
    assert decision.reason == "MISSING_INPUT"
    assert "B" in decision.detail
    assert "MISSING_INPUT" in decision.detail
    assert "the price of wheat" in decision.detail
    assert decision.tied == ()


# 6. An option whose limit check is not resolved.
@pytest.mark.parametrize("margin", [400.0, 300.0, None])
def test_not_resolved_option_that_could_win_blocks(margin):
    options = [
        _option("A", 300.0, MEETS),
        _option("B", 250.0, MEETS),
        _option("X", margin, OPEN_CHECK),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: X could be the answer, so not resolved.
    assert decision.answer == "not_resolved"
    assert decision.chosen is None
    assert decision.reason == "MISSING_INPUT"
    assert "X" in decision.detail
    assert "the soil loss on average is missing" in decision.detail
    if margin is None:
        assert "its margin is missing" in decision.detail
        assert "the price of wheat" in decision.detail
    else:
        assert f"its margin {margin!r} is at least" in decision.detail
        assert "300.0" in decision.detail
    assert _states(decision)["X"] == "not_resolved"
    assert _states(decision)["A"] == "meets"


def test_not_resolved_option_below_the_best_does_not_block():
    options = [
        _option("A", 300.0, MEETS),
        _option("X", 200.0, OPEN_CHECK),
        _option("C", 500.0, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: A; X (200) cannot beat it whatever its soil loss.
    assert decision.answer == "chosen"
    assert decision.chosen == "A"
    assert _states(decision)["X"] == "not_resolved"
    assert decision.options[1].limit_check == OPEN_CHECK
    assert decision.limit_cost.value == 200.0
    assert decision.limit_cost.against == "C"


# 7. The cost of the limit.
def test_chosen_is_best_overall_costs_nothing():
    options = [
        _option("A", 300.0, MEETS),
        _option("B", 280.0, FAILS),
        _option("C", 100.0, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: A; meeting the limit costs nothing here.
    assert decision.chosen == "A"
    cost = decision.limit_cost
    assert cost.costs_nothing is True
    assert cost.value is None
    assert cost.against is None
    assert cost.reason is None


def test_equal_margin_outside_the_limit_costs_nothing():
    options = [_option("A", 300.0, MEETS), _option("B", 300.0, FAILS)]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: B has no more margin than A, so no cost.
    assert decision.chosen == "A"
    assert decision.limit_cost.costs_nothing is True
    assert decision.limit_cost.value is None


def test_no_option_outside_the_limit_costs_nothing():
    options = [_option("A", 300.0, MEETS), _option("B", 100.0, MEETS)]
    decision = choose_rotation(options, "on_average")
    assert decision.chosen == "A"
    assert decision.limit_cost.costs_nothing is True
    assert decision.limit_cost.value is None


def test_non_meeting_option_with_missing_margin_leaves_the_cost_missing():
    options = [
        _option("A", 300.0, MEETS),
        _option("B", 100.0, FAILS),
        _option("C", None, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: A; the cost is missing because C's margin is.
    assert decision.chosen == "A"
    cost = decision.limit_cost
    assert cost.value is None
    assert cost.against is None
    assert cost.costs_nothing is False
    assert cost.reason == "MISSING_INPUT"
    assert "C" in cost.detail


def test_known_better_non_meeting_option_does_not_give_a_lower_bound():
    options = [
        _option("A", 300.0, MEETS),
        _option("B", 450.0, FAILS),
        _option("C", None, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer (fix round 1): A; C's missing margin could be
    # above B's, so no cost is given (no silent lower bound of 150).
    assert decision.chosen == "A"
    cost = decision.limit_cost
    assert cost.value is None
    assert cost.against is None
    assert cost.costs_nothing is False
    assert cost.reason == "MISSING_INPUT"
    assert "C" in cost.detail
    assert "B" not in cost.detail


def test_tie_outside_the_limit_names_the_first():
    options = [
        _option("A", 300.0, MEETS),
        _option("B", 450.0, FAILS),
        _option("C", 450.0, FAILS),
    ]
    decision = choose_rotation(options, "on_average")
    # PROPOSED expected answer: 450 - 300 = 150 against B, the first of the tie.
    assert decision.limit_cost.value == 150.0
    assert decision.limit_cost.against == "B"


# 8. Misuse.
def test_empty_is_refused():
    with pytest.raises(ValueError, match="at least one"):
        choose_rotation([], "on_average")


def test_empty_generator_is_refused():
    with pytest.raises(ValueError, match="at least one"):
        choose_rotation((o for o in []), "on_average")


def test_a_generator_is_read_once():
    decision = choose_rotation((o for o in _table()), "on_average")
    # PROPOSED expected answer: as test 1.
    assert decision.chosen == "A"
    assert decision.limit_cost.value == 200.0
    assert len(decision.options) == len(_table())


def test_different_limits_are_refused():
    first, second, *rest = _table()
    # Invented test data: two limits that differ.
    second = dataclasses.replace(
        second, limit=dataclasses.replace(second.limit, limit=5.0)
    )
    with pytest.raises(ValueError, match="another soil-loss limit"):
        choose_rotation([first, second, *rest], "on_average")
    other_unit = dataclasses.replace(
        first, limit=dataclasses.replace(first.limit, unit="t ha-1")
    )
    with pytest.raises(ValueError, match="another soil-loss limit"):
        choose_rotation([other_unit, second], "on_average")


def test_two_missing_limits_count_as_the_same():
    # _table() builds every assessment with limit None.
    assert choose_rotation(_table(), "on_average").chosen == "A"


def test_limit_cost_refuses_inconsistent_fields():
    with pytest.raises(ValueError):
        LimitCost(
            value=1.0, against=None, costs_nothing=False, reason=None, detail=None
        )
    with pytest.raises(ValueError):
        LimitCost(value=1.0, against="B", costs_nothing=True, reason=None, detail=None)
    with pytest.raises(ValueError):
        LimitCost(
            value=None,
            against=None,
            costs_nothing=True,
            reason="MISSING_INPUT",
            detail="x",
        )
    with pytest.raises(ValueError):
        LimitCost(
            value=None, against=None, costs_nothing=False, reason=None, detail=None
        )


def test_decision_refuses_inconsistent_fields():
    nothing = LimitCost(
        value=None, against=None, costs_nothing=True, reason=None, detail=None
    )
    missing = LimitCost(
        value=None,
        against=None,
        costs_nothing=False,
        reason="NOT_COMPUTABLE",
        detail="x",
    )
    with pytest.raises(ValueError):
        Decision("chosen", "on_average", None, None, None, (), (), nothing)
    with pytest.raises(ValueError):
        Decision(
            "not_resolved", "on_average", "A", "MISSING_INPUT", "x", (), (), missing
        )
    with pytest.raises(ValueError):
        Decision("chosen", "on_average", "A", "MISSING_INPUT", "x", (), (), nothing)
    with pytest.raises(ValueError):
        Decision("none_meets", "on_average", None, None, None, (), (), missing)
    with pytest.raises(ValueError):
        Decision("chosen", "on_average", "A", None, None, ("A", "B"), (), nothing)


def test_duplicate_id_is_refused():
    options = [_option("A", 300.0, MEETS), _option("A", 200.0, MEETS)]
    with pytest.raises(ValueError, match="duplicate"):
        choose_rotation(options, "on_average")


def test_wrong_margin_unit_is_refused():
    bad = RotationOption(
        rotation_id="A",
        margin=MarginResult(value=300.0, unit="EUR ha-1 yr-1"),
        limit=_assessment(MEETS, MEETS),
    )
    with pytest.raises(ValueError, match="unit"):
        choose_rotation([bad], "on_average")


@pytest.mark.parametrize("strictness", ["average", "", None, "every kind"])
def test_bad_strictness_is_refused(strictness):
    with pytest.raises(ValueError, match="strictness"):
        choose_rotation(_table(), strictness)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_non_finite_margin_is_refused(value):
    bad = RotationOption(
        rotation_id="A",
        margin=MarginResult(value=value),
        limit=_assessment(MEETS, MEETS),
    )
    with pytest.raises(ValueError, match="margin"):
        choose_rotation([bad], "on_average")


def test_other_counts_are_not_refused():
    # The story speaks of three to five rotations; the route checks the count.
    one = choose_rotation([_option("A", 300.0, MEETS)], "on_average")
    assert one.chosen == "A"
    six = choose_rotation([*_table(), _option("F", 260.0, MEETS)], "every_kind")
    assert six.chosen == "F"


# 9. No mutation, frozen results, order kept, no number in the module.
def test_inputs_are_not_mutated():
    options = _table()
    # The options are frozen; what could change is the list and its items.
    before = list(options)
    margins = [copy.copy(o.margin) for o in options]
    checks = [(o.limit.on_average, o.limit.every_kind) for o in options]
    choose_rotation(options, "on_average")
    assert options == before
    assert all(a is b for a, b in zip(options, before, strict=True))
    assert [o.margin for o in options] == margins
    assert [(o.limit.on_average, o.limit.every_kind) for o in options] == checks


def test_results_are_frozen_and_order_kept():
    options = _table()
    decision = choose_rotation(options, "on_average")
    assert isinstance(decision.options, tuple)
    assert [v.rotation_id for v in decision.options] == ["A", "B", "C", "D", "E"]
    assert decision.options[2].margin is options[2].margin
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.chosen = "B"
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.options[0].state = "meets"
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.limit_cost.value = 0.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        options[0].rotation_id = "Z"


def test_no_numeric_literal_in_the_module():
    tree = ast.parse(DECIDE_SOURCE.read_text(encoding="utf-8"))
    numbers = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ]
    assert numbers == []
