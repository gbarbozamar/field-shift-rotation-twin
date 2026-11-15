"""Acceptance test of unit l2/economics-margin. PROPOSED (blueprint section 3.7).

Run from the repository root: ``uv run pytest economics/``.

Every number in this file is invented test data: no market, no producer, no
survey, no source. The crop_ids carry PLACEHOLDER and the facts say
``example_data`` true. Each expected margin is written as arithmetic on those
invented numbers, so a reader checks it by hand; every expected value is
PROPOSED.
"""

from __future__ import annotations

import dataclasses
import json
import numbers
import socket
from pathlib import Path

import pytest

from contracts.economic_facts import KINDS_OF_YEAR, EconomicFacts
from economics import MarginResult, RotationMargin, compute_rotation_margin

UNIT = "USD ha-1 yr-1"
EXAMPLE = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "economic_facts"
    / "examples"
    / "PLACEHOLDER_economic_facts.json"
)

# Invented test data (not parameters, from no source).
GRAIN_A = "PLACEHOLDER_grain_a"  # price 300, cost 500, yields 3.0 / 2.5 / 1.5
GRAIN_B = "PLACEHOLDER_grain_b"  # price 200, cost 250, yields 2.0 / 1.8 / 1.0
GRAIN_C = "PLACEHOLDER_grain_c"  # price 150, cost 400, yields 6.0 / 5.0 / 3.0
COVER = "PLACEHOLDER_cover"  # cost 90
PASTURE = "PLACEHOLDER_pasture"  # declared margin 120 / 100 / 40


def _present(number: float, unit: str) -> dict:
    return {
        "value": number,
        "unit": unit,
        "provenance": "DECLARED",
        "source": "user",
        "range_missing": {"reason": "NOT_DECLARED"},
    }


def _absent(unit: str) -> dict:
    return {"value": None, "unit": unit, "missing": {"reason": "NOT_DECLARED"}}


def _grain(crop_id: str, price, cost, yields: dict) -> dict:
    return {
        "crop_id": crop_id,
        "kind": "grain",
        "price": _present(price, "USD t-1")
        if price is not None
        else _absent("USD t-1"),
        "cost": _present(cost, "USD ha-1"),
        "yield": {
            kind: _present(y, "t ha-1") if y is not None else _absent("t ha-1")
            for kind, y in yields.items()
        },
    }


def _table(*, price_a=300.0, la_nina_yield_a=1.5) -> dict:
    """The hand-made table of invented test data."""
    return {
        "contract": "economic_facts",
        "example_data": True,
        "case_id": "test-case",
        "field_id": "test-field",
        "currency": "USD",
        "crops": [
            _grain(
                GRAIN_A,
                price_a,
                500.0,
                {"el_nino": 3.0, "neutral": 2.5, "la_nina": la_nina_yield_a},
            ),
            _grain(
                GRAIN_B, 200.0, 250.0, {"el_nino": 2.0, "neutral": 1.8, "la_nina": 1.0}
            ),
            _grain(
                GRAIN_C, 150.0, 400.0, {"el_nino": 6.0, "neutral": 5.0, "la_nina": 3.0}
            ),
            {"crop_id": COVER, "kind": "cover", "cost": _present(90.0, "USD ha-1")},
            {
                "crop_id": PASTURE,
                "kind": "declared_margin",
                "declared_margin": {
                    "el_nino": _present(120.0, UNIT),
                    "neutral": _present(100.0, UNIT),
                    "la_nina": _present(40.0, UNIT),
                },
            },
        ],
    }


def _facts(**kwargs) -> EconomicFacts:
    return EconomicFacts.model_validate(_table(**kwargs))


COUNTS = {"el_nino": 3, "neutral": 5, "la_nina": 2}  # invented test data


def _assert_present(result: MarginResult, expected: float) -> None:
    assert result.unit == UNIT
    assert result.reason is None
    assert result.detail is None
    assert result.value == pytest.approx(expected)


def _assert_missing(result: MarginResult, reason: str) -> None:
    assert result.unit == UNIT
    assert result.value is None  # never zero
    assert result.reason == reason
    assert result.detail


# 1. One-year rotation, grain and cover.
def test_one_year_grain_and_cover():
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), None)
    assert isinstance(margin, RotationMargin)
    assert set(margin.by_kind) == set(KINDS_OF_YEAR)
    # PROPOSED expected values: price * yield[t] - cost - cover cost, over 1 year.
    _assert_present(margin.by_kind["el_nino"], (300 * 3.0 - 500 + (-90)) / 1)
    _assert_present(margin.by_kind["neutral"], (300 * 2.5 - 500 + (-90)) / 1)
    _assert_present(margin.by_kind["la_nina"], (300 * 1.5 - 500 + (-90)) / 1)


# 2. Two-year rotation: the sum of every cycle divided by 2.
def test_two_year_rotation_divides_by_two():
    years = [[GRAIN_A, GRAIN_B], [GRAIN_C, COVER]]
    margin = compute_rotation_margin(years, _facts(), None)
    # PROPOSED expected values.
    _assert_present(
        margin.by_kind["el_nino"],
        ((300 * 3.0 - 500) + (200 * 2.0 - 250) + (150 * 6.0 - 400) + (-90)) / 2,
    )
    _assert_present(
        margin.by_kind["neutral"],
        ((300 * 2.5 - 500) + (200 * 1.8 - 250) + (150 * 5.0 - 400) + (-90)) / 2,
    )
    _assert_present(
        margin.by_kind["la_nina"],
        ((300 * 1.5 - 500) + (200 * 1.0 - 250) + (150 * 3.0 - 400) + (-90)) / 2,
    )


# 3. A declared-margin crop over three entries: added once per entry.
def test_declared_margin_added_once_per_entry():
    years = [[GRAIN_A], [PASTURE], [PASTURE]]
    margin = compute_rotation_margin(years, _facts(), None)
    # PROPOSED expected values.
    _assert_present(margin.by_kind["el_nino"], ((300 * 3.0 - 500) + 120 + 120) / 3)
    _assert_present(margin.by_kind["neutral"], ((300 * 2.5 - 500) + 100 + 100) / 3)
    _assert_present(margin.by_kind["la_nina"], ((300 * 1.5 - 500) + 40 + 40) / 3)


# 4. The average weighted by year_counts.
def test_average_weighted_by_year_counts():
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), COUNTS)
    el_nino = 300 * 3.0 - 500 - 90
    neutral = 300 * 2.5 - 500 - 90
    la_nina = 300 * 1.5 - 500 - 90
    # PROPOSED expected value.
    _assert_present(
        margin.average, (el_nino * 3 + neutral * 5 + la_nina * 2) / (3 + 5 + 2)
    )


# 5. year_counts None: the average is missing NOT_AVAILABLE, the kinds present.
def test_year_counts_none_gives_average_not_available():
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), None)
    _assert_missing(margin.average, "NOT_AVAILABLE")
    assert "not classified" in margin.average.detail
    for kind in KINDS_OF_YEAR:
        assert margin.by_kind[kind].value is not None


# 6. A grain price missing NOT_DECLARED: every kind missing.
def test_missing_price_makes_every_kind_missing():
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(price_a=None), COUNTS)
    for kind in KINDS_OF_YEAR:
        result = margin.by_kind[kind]
        _assert_missing(result, "MISSING_INPUT")
        assert GRAIN_A in result.detail
        assert "NOT_DECLARED" in result.detail
        assert "price" in result.detail
    _assert_missing(margin.average, "MISSING_INPUT")


# 7. A yield missing only in la_nina.
def test_missing_yield_in_one_kind():
    facts = _facts(la_nina_yield_a=None)
    margin = compute_rotation_margin([[GRAIN_A, COVER]], facts, COUNTS)
    _assert_missing(margin.by_kind["la_nina"], "MISSING_INPUT")
    assert GRAIN_A in margin.by_kind["la_nina"].detail
    assert "la_nina" in margin.by_kind["la_nina"].detail
    assert "NOT_DECLARED" in margin.by_kind["la_nina"].detail
    _assert_present(margin.by_kind["el_nino"], 300 * 3.0 - 500 - 90)
    _assert_present(margin.by_kind["neutral"], 300 * 2.5 - 500 - 90)
    _assert_missing(margin.average, "MISSING_INPUT")
    assert "la_nina" in margin.average.detail

    # A kind with count 0 does not enter the average (PROPOSED).
    counts = {"el_nino": 3, "neutral": 5, "la_nina": 0}
    margin = compute_rotation_margin([[GRAIN_A, COVER]], facts, counts)
    _assert_missing(margin.by_kind["la_nina"], "MISSING_INPUT")
    # PROPOSED expected value.
    _assert_present(
        margin.average,
        ((300 * 3.0 - 500 - 90) * 3 + (300 * 2.5 - 500 - 90) * 5) / (3 + 5),
    )


# 8. A crop_id in years that is absent from the facts.
def test_unknown_crop_id_is_missing_input():
    unknown = "PLACEHOLDER_not_declared"
    margin = compute_rotation_margin([[GRAIN_A, unknown]], _facts(), COUNTS)
    for kind in KINDS_OF_YEAR:
        _assert_missing(margin.by_kind[kind], "MISSING_INPUT")
        assert unknown in margin.by_kind[kind].detail
    _assert_missing(margin.average, "MISSING_INPUT")


# 9. Structural misuse raises ValueError.
@pytest.mark.parametrize(
    ("years", "counts"),
    [
        pytest.param([], COUNTS, id="empty-years"),
        pytest.param([[GRAIN_A], []], COUNTS, id="empty-entry"),
        pytest.param([[GRAIN_A]], {**COUNTS, "dry": 1}, id="year-counts-unknown-key"),
        pytest.param(
            [[GRAIN_A]], {"el_nino": 3, "neutral": 5}, id="year-counts-missing-key"
        ),
        pytest.param([[GRAIN_A]], {**COUNTS, "la_nina": -1}, id="year-counts-negative"),
        pytest.param(
            [[GRAIN_A]], {**COUNTS, "la_nina": 1.5}, id="year-counts-not-integer"
        ),
        pytest.param(
            [[GRAIN_A]], {**COUNTS, "la_nina": True}, id="year-counts-boolean"
        ),
        pytest.param(
            [[GRAIN_A]],
            {"el_nino": 0, "neutral": 0, "la_nina": 0},
            id="year-counts-all-zero",
        ),
        pytest.param(GRAIN_A, COUNTS, id="years-is-a-text"),
        pytest.param([GRAIN_A], COUNTS, id="entry-is-a-text"),
        pytest.param(
            [[GRAIN_A, PASTURE]], COUNTS, id="declared-margin-shares-its-year"
        ),
    ],
)
def test_structural_misuse_raises(years, counts):
    with pytest.raises(ValueError):
        compute_rotation_margin(years, _facts(), counts)


def test_all_none_counts_give_average_no_coverage():
    # S-027 F1 and R1 (PROPOSED): what count_kinds gives when a year has no
    # kind. Not NOT_AVAILABLE: the years were classified, one has no coverage.
    counts = {kind: None for kind in KINDS_OF_YEAR}
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), counts)
    reference = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), None)
    _assert_missing(margin.average, "NO_COVERAGE")
    assert "no kind of year" in margin.average.detail
    assert "not classified" not in margin.average.detail
    # year_counts=None keeps NOT_AVAILABLE and its detail.
    _assert_missing(reference.average, "NOT_AVAILABLE")
    assert "not classified" in reference.average.detail
    for kind in KINDS_OF_YEAR:
        assert margin.by_kind[kind] == reference.by_kind[kind]


def test_some_none_counts_are_refused():
    # S-027 F1 and R3 (PROPOSED): some None and some integers is structural
    # misuse, with its own message.
    counts = {"el_nino": 3, "neutral": None, "la_nina": 2}  # invented test data
    with pytest.raises(
        ValueError, match="year_counts: counts are either all known or all None"
    ):
        compute_rotation_margin([[GRAIN_A]], _facts(), counts)


def test_all_none_counts_still_check_the_keys():
    # S-027 R3 (PROPOSED): the key checks come first.
    with pytest.raises(ValueError, match="no count for"):
        compute_rotation_margin(
            [[GRAIN_A]], _facts(), {"el_nino": None, "neutral": None}
        )


def test_count_kinds_with_a_missing_year_feeds_the_margin():
    # S-027 F1, R1 and R4 (PROPOSED): the seam between kinds_of_year and
    # economics. EXAMPLE DATA: the ONI record is not in the repository until a
    # person signs it (D240 (5)), so the record is written by hand, with the
    # rule of D240 (1) (+/- 0.5 met for 5 consecutive overlapping seasons) and
    # synthetic seasons, every one of 2013..2014 at 0.0 (not the real
    # anomalies). The agricultural year 2014 with start month 7 is decided by
    # DJF 2015, which is not in them, so that year is missing NO_COVERAGE.
    pytest.importorskip("kinds_of_year", reason="kinds_of_year/ is not importable")
    from kinds_of_year import (
        SEASONS,
        classify_agricultural_years,
        count_kinds,
    )

    record = {
        "threshold": 0.5,
        "min_consecutive_seasons": 5,
        "seasons": [
            {"season": name, "year": year, "anom": 0.0}
            for year in (2013, 2014)
            for name in SEASONS
        ],
    }
    classified = classify_agricultural_years(record, 2013, 2014, 7)
    assert classified[2014].missing_reason == "NO_COVERAGE"
    counts = count_kinds(classified)
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), counts)
    _assert_missing(margin.average, "NO_COVERAGE")
    # The same expected values as test 1.
    _assert_present(margin.by_kind["el_nino"], 300 * 3.0 - 500 - 90)
    _assert_present(margin.by_kind["neutral"], 300 * 2.5 - 500 - 90)
    _assert_present(margin.by_kind["la_nina"], 300 * 1.5 - 500 - 90)


@pytest.mark.parametrize(
    "item",
    [
        pytest.param(7, id="int"),
        pytest.param(None, id="none"),
        pytest.param([], id="list"),
    ],
)
def test_a_crop_id_that_is_not_a_text_is_refused(item):
    # S-027 F4 (PROPOSED).
    with pytest.raises(ValueError, match=r"years\[0\]\[1\]"):
        compute_rotation_margin([[GRAIN_A, item]], _facts(), COUNTS)


class _IntegralStandIn:
    """A stand-in for an integral number that is not a Python int (such as numpy's)."""

    def __init__(self, number: int) -> None:
        self._number = number

    def __index__(self) -> int:
        return self._number


numbers.Integral.register(_IntegralStandIn)


def test_year_counts_accept_any_integral():
    counts = {kind: _IntegralStandIn(n) for kind, n in COUNTS.items()}
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), counts)
    el_nino = 300 * 3.0 - 500 - 90
    neutral = 300 * 2.5 - 500 - 90
    la_nina = 300 * 1.5 - 500 - 90
    # PROPOSED expected value: the same as test 4.
    _assert_present(
        margin.average, (el_nino * 3 + neutral * 5 + la_nina * 2) / (3 + 5 + 2)
    )


def test_result_cannot_be_changed():
    margin = compute_rotation_margin([[GRAIN_A, COVER]], _facts(), COUNTS)
    with pytest.raises(TypeError):
        margin.by_kind["el_nino"] = margin.average
    with pytest.raises(dataclasses.FrozenInstanceError):
        margin.average = margin.by_kind["el_nino"]


# 10. No network call, no mutation of the inputs.
def test_no_network_and_no_mutation(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("compute_rotation_margin opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    facts = _facts()
    years = [[GRAIN_A, GRAIN_B], [PASTURE]]
    counts = dict(COUNTS)
    facts_before = facts.model_dump(mode="json")
    years_before = json.dumps(years)
    counts_before = dict(counts)
    compute_rotation_margin(years, facts, counts)
    assert facts.model_dump(mode="json") == facts_before
    assert json.dumps(years) == years_before
    assert counts == counts_before


# 11. The contract example gives present margins for every kind.
def test_contract_example_gives_present_margins():
    facts = EconomicFacts.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    years = [
        ["PLACEHOLDER_soybean", "PLACEHOLDER_cover_crop"],
        ["PLACEHOLDER_pasture"],
    ]
    margin = compute_rotation_margin(years, facts, COUNTS)
    # PROPOSED expected values, from the invented numbers of the contract
    # example: soybean price 400, cost 600, yields 2.6 / 3.0 / 1.6; cover crop
    # cost 90; pasture declared margin 198 / 180 / 126. Two years.
    el_nino = ((400 * 2.6 - 600) + (-90) + 198) / 2
    neutral = ((400 * 3.0 - 600) + (-90) + 180) / 2
    la_nina = ((400 * 1.6 - 600) + (-90) + 126) / 2
    _assert_present(margin.by_kind["el_nino"], el_nino)
    _assert_present(margin.by_kind["neutral"], neutral)
    _assert_present(margin.by_kind["la_nina"], la_nina)
    _assert_present(
        margin.average, (el_nino * 3 + neutral * 5 + la_nina * 2) / (3 + 5 + 2)
    )
