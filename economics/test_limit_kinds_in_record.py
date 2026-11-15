"""Tests of ``kinds_in_record`` of ``assess_limit`` (unit l2/review-whole-2).

PROPOSED (blueprint section 3.7). Run from the repository root:
``uv run pytest economics/``.

Every number in this file is invented test data: no field, no record, no
source, and no soil-loss limit of any real field. Each expected verdict
follows from the PROPOSED rules of ``economics/README.md`` on those invented
numbers; every expected verdict is PROPOSED.
"""

from __future__ import annotations

import dataclasses

import pytest

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import Value
from economics import LimitAssessment, assess_limit

UNIT = "t ha-1 yr-1"

# Invented test data (not parameters, from no source).
TEST_LIMIT = 5.0


@dataclasses.dataclass(frozen=True)
class Level:
    """A soil-loss level with the three attributes assess_limit reads."""

    value: float | None
    reason: str | None = None
    detail: str | None = None


def _limit(number: float | None) -> Value:
    if number is None:
        return Value.model_validate(
            {"value": None, "unit": UNIT, "missing": {"reason": "NOT_DECLARED"}}
        )
    return Value.model_validate(
        {
            "value": number,
            "unit": UNIT,
            "provenance": "DECLARED",
            "source": "user",
            "range_missing": {"reason": "NOT_DECLARED"},
        }
    )


def _absent() -> Level:
    return Level(value=None, reason="NO_COVERAGE", detail="no year of this kind")


def _kinds(el_nino: Level, neutral: Level, la_nina: Level) -> dict:
    return {"el_nino": el_nino, "neutral": neutral, "la_nina": la_nina}


def test_a_left_out_kind_with_no_coverage_lets_every_kind_meet():
    by_kind = _kinds(_absent(), Level(2.0), Level(3.0))
    result = assess_limit(
        _limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record={"neutral", "la_nina"}
    )
    assert result.every_kind.verdict == "meets"
    assert result.kinds_not_resolved == ()
    assert result.kinds_not_met == ()
    assert result.kinds_not_in_record == ("el_nino",)
    # The by_kind check of the left-out kind is what its level gives.
    assert result.by_kind["el_nino"].verdict == "not_resolved"
    assert result.by_kind["el_nino"].reason == "MISSING_INPUT"


def test_a_failing_kind_in_the_record_still_fails():
    by_kind = _kinds(_absent(), Level(6.0), Level(3.0))
    result = assess_limit(
        _limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record=["neutral", "la_nina"]
    )
    assert result.every_kind.verdict == "does_not_meet"
    assert result.kinds_not_met == ("neutral",)
    assert result.kinds_not_in_record == ("el_nino",)


def test_a_left_out_kind_with_a_value_is_still_left_out():
    by_kind = _kinds(Level(6.0), Level(2.0), Level(3.0))
    result = assess_limit(
        _limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record={"neutral", "la_nina"}
    )
    assert result.every_kind.verdict == "meets"
    assert result.kinds_not_met == ()
    assert result.by_kind["el_nino"].verdict == "does_not_meet"


def test_an_unresolved_kind_names_the_left_out_kinds():
    by_kind = _kinds(_absent(), Level(None, "MISSING_INPUT", "gap"), Level(3.0))
    result = assess_limit(
        _limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record={"neutral", "la_nina"}
    )
    assert result.every_kind.verdict == "not_resolved"
    assert result.kinds_not_resolved == ("neutral",)
    assert "left out, no year in the record: el_nino" in result.every_kind.detail


@pytest.mark.parametrize(
    "by_kind",
    [
        _kinds(_absent(), Level(2.0), Level(3.0)),
        _kinds(Level(1.0), Level(6.0), _absent()),
        _kinds(Level(1.0), Level(2.0), Level(3.0)),
    ],
)
def test_none_keeps_the_result_of_a_call_without_the_keyword(by_kind):
    without = assess_limit(_limit(TEST_LIMIT), Level(2.0), by_kind)
    with_none = assess_limit(
        _limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record=None
    )
    assert with_none == without
    assert with_none.kinds_not_in_record == ()


def test_every_kind_in_the_record_keeps_the_result_of_a_call_without_it():
    by_kind = _kinds(_absent(), Level(2.0), Level(3.0))
    without = assess_limit(_limit(TEST_LIMIT), Level(2.0), by_kind)
    given = assess_limit(
        _limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record=KINDS_OF_YEAR
    )
    assert given == without


def test_no_kind_in_the_record_leaves_every_kind_not_resolved():
    by_kind = _kinds(_absent(), _absent(), _absent())
    result = assess_limit(_limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record=())
    assert result.every_kind.verdict == "not_resolved"
    assert result.every_kind.reason == "NO_COVERAGE"
    assert "no kind of year is in the record" in result.every_kind.detail
    assert result.kinds_not_in_record == KINDS_OF_YEAR
    assert result.kinds_not_resolved == ()
    assert result.kinds_not_met == ()
    assert result.on_average.verdict == "meets"


def test_a_missing_limit_lists_only_the_kinds_in_the_record():
    by_kind = _kinds(_absent(), Level(2.0), Level(3.0))
    result = assess_limit(
        _limit(None), Level(2.0), by_kind, kinds_in_record={"neutral", "la_nina"}
    )
    assert result.every_kind.verdict == "not_resolved"
    assert result.kinds_not_resolved == ("neutral", "la_nina")
    assert result.kinds_not_in_record == ("el_nino",)
    assert "left out, no year in the record: el_nino" in result.every_kind.detail


@pytest.mark.parametrize("bad", [{"el_nino", "drought"}, ["unknown"]])
def test_an_unknown_kind_is_refused(bad):
    by_kind = _kinds(Level(1.0), Level(2.0), Level(3.0))
    with pytest.raises(ValueError, match="kinds_in_record"):
        assess_limit(_limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record=bad)


def test_one_text_is_refused():
    by_kind = _kinds(Level(1.0), Level(2.0), Level(3.0))
    with pytest.raises(ValueError, match="kinds_in_record"):
        assess_limit(_limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record="neutral")


def test_the_field_defaults_to_empty_and_keeps_kinds_of_year_order():
    field = {f.name: f for f in dataclasses.fields(LimitAssessment)}
    assert field["kinds_not_in_record"].default == ()
    by_kind = _kinds(_absent(), Level(2.0), _absent())
    result = assess_limit(
        _limit(TEST_LIMIT), Level(2.0), by_kind, kinds_in_record=["neutral"]
    )
    assert result.kinds_not_in_record == ("el_nino", "la_nina")
