"""Acceptance test of unit l2/tipping-price (S-016). PROPOSED (blueprint 3.7).

Run from the repository root: ``uv run pytest economics/``.

Every number in this file is invented test data: no market, no producer, no
price, no source. The crop_ids carry PLACEHOLDER and the facts say
``example_data`` true. Each expected tipping price is worked out by hand in a
comment from those invented numbers; every expected value is PROPOSED.

The hand-made table (invented test data):

- SOY: today's price 400 USD t-1, cost 200 USD ha-1, yields 3 / 2 / 1 t ha-1
  in el_nino / neutral / la_nina.
- WHEAT: price 200 USD t-1, cost 150 USD ha-1, yields 4 / 3 / 2 t ha-1.
- COUNTS: 1 el_nino, 2 neutral, 1 la_nina year in the record.

Average margin of one SOY cycle at price p:
  (1 * (3p - 200) + 2 * (2p - 200) + 1 * (p - 200)) / 4 = (8p - 800) / 4
  = 2p - 200.
Average margin of one WHEAT cycle:
  (1 * 650 + 2 * 450 + 1 * 250) / 4 = 1800 / 4 = 450.

- Rotation A = [[SOY]]: 2p - 200.
- Rotation B = [[SOY], [WHEAT]]: (2p - 200 + 450) / 2 = p + 125.
- Rotation C = [[SOY, SOY]]: 2 * (2p - 200) = 4p - 400 (the steepest line).

A and B cross where 2p - 200 = p + 125, so p = 325. Above 325 A has more
margin, below it B has more.
"""

from __future__ import annotations

import dataclasses

import pytest

from contracts.economic_facts import KINDS_OF_YEAR, EconomicFacts
from economics import (
    LimitAssessment,
    LimitCheck,
    PriceRange,
    TippingOption,
    TippingPoint,
    TippingPrice,
    find_tipping_price,
)

PRICE_UNIT = "USD t-1"
NO_CHANGE = "no price in this range changes the answer"

# Invented test data (not parameters, from no source).
SOY = "PLACEHOLDER_soy"
SOY_SECOND = "PLACEHOLDER_soy_second"
WHEAT = "PLACEHOLDER_wheat"
COVER = "PLACEHOLDER_cover"
COUNTS = {"el_nino": 1, "neutral": 2, "la_nina": 1}
TODAY = 400.0
WIDE = PriceRange(low=100.0, high=800.0)

MEETS = LimitCheck("meets")
FAILS = LimitCheck("does_not_meet")


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


def _maybe(number: float | None, unit: str) -> dict:
    return _absent(unit) if number is None else _present(number, unit)


def _grain(crop_id: str, price, cost, yields: tuple[float, float, float]) -> dict:
    return {
        "crop_id": crop_id,
        "kind": "grain",
        "price": _maybe(price, PRICE_UNIT),
        "cost": _maybe(cost, "USD ha-1"),
        "yield": {
            kind: _present(y, "t ha-1")
            for kind, y in zip(KINDS_OF_YEAR, yields, strict=True)
        },
    }


def _facts(
    *, soy_price=TODAY, wheat_cost=150.0, soy_second_price=None
) -> EconomicFacts:
    """The hand-made table of invented test data."""
    crops = [
        _grain(SOY, soy_price, 200.0, (3.0, 2.0, 1.0)),
        _grain(WHEAT, 200.0, wheat_cost, (4.0, 3.0, 2.0)),
        {"crop_id": COVER, "kind": "cover", "cost": _present(90.0, "USD ha-1")},
    ]
    if soy_second_price is not None:
        crops.append(_grain(SOY_SECOND, soy_second_price, 200.0, (3.0, 2.0, 1.0)))
    return EconomicFacts.model_validate(
        {
            "contract": "economic_facts",
            "example_data": True,
            "case_id": "test-case",
            "field_id": "test-field",
            "currency": "USD",
            "crops": crops,
        }
    )


def _assessment(check: LimitCheck) -> LimitAssessment:
    """A LimitAssessment built by hand: the same check on average and every kind."""
    return LimitAssessment(
        limit=None,  # not read by choose_rotation
        unit="t ha-1 yr-1",
        on_average=check,
        every_kind=check,
        by_kind={kind: check for kind in KINDS_OF_YEAR},
        kinds_not_met=KINDS_OF_YEAR if check.verdict == "does_not_meet" else (),
        kinds_not_resolved=(),
    )


def _a(check: LimitCheck = MEETS) -> TippingOption:
    return TippingOption("A", [[SOY]], _assessment(check))


def _b(check: LimitCheck = MEETS) -> TippingOption:
    return TippingOption("B", [[SOY], [WHEAT]], _assessment(check))


def _c(check: LimitCheck = FAILS) -> TippingOption:
    return TippingOption("C", [[SOY, SOY]], _assessment(check))


def _run(options, facts=None, price_range=WIDE, margin_of="average", **kwargs):
    return find_tipping_price(
        options,
        _facts() if facts is None else facts,
        kwargs.pop("year_counts", COUNTS),
        kwargs.pop("soybean_crop_ids", [SOY]),
        price_range,
        kwargs.pop("strictness", "on_average"),
        margin_of=margin_of,
    )


def _assert_no_change(point: TippingPoint, direction: str, price_range=WIDE):
    assert point.direction == direction
    assert point.price is None  # never a default zero
    assert point.unit == PRICE_UNIT
    assert point.takes_over is None
    assert point.answer_after is None
    assert point.distance_percent is None
    assert point.reason == "NOT_APPLICABLE"
    assert point.detail.startswith(NO_CHANGE)
    assert repr(price_range.low) in point.detail
    assert repr(price_range.high) in point.detail


def _assert_missing(point: TippingPoint, reason: str) -> None:
    assert point.price is None
    assert point.takes_over is None
    assert point.answer_after is None
    assert point.distance_percent is None
    assert point.reason == reason
    assert point.detail


# 1. Hand-made case: B overtakes A going down at 325.
def test_hand_made_case_down():
    result = _run([_a(), _b()])
    assert isinstance(result, TippingPrice)
    assert result.today == TODAY
    assert result.unit == PRICE_UNIT
    assert result.price_range == WIDE
    assert result.reason is None
    assert result.detail is None
    # At 400: A = 2 * 400 - 200 = 600, B = 400 + 125 = 525, so A is chosen.
    assert result.decision.answer == "chosen"
    assert result.decision.chosen == "A"
    down = result.down
    assert down.direction == "down"
    # PROPOSED expected value: 2p - 200 = p + 125 gives p = 325.
    assert down.price == pytest.approx(325.0)
    assert down.unit == PRICE_UNIT
    assert down.takes_over == "B"
    assert down.answer_after == "chosen"
    # (325 - 400) / 400 * 100 = -18.75.
    assert down.distance_percent == pytest.approx(-18.75)
    assert down.reason is None
    assert down.detail is None
    # Above 400 A keeps the most margin up to 800: no change.
    _assert_no_change(result.up, "up")


# 2. A third rotation outside the limit with the steepest line never takes over.
def test_rotation_outside_the_limit_never_takes_over():
    result = _run([_a(), _b(), _c()])
    # C = 4p - 400 crosses B at 4p - 400 = p + 125, p = 175, and A at p = 100
    # (the low bound, not inside the open range). Above 100 C has the most
    # margin, but it does not meet the limit, so it is never chosen.
    assert result.decision.chosen == "A"
    # PROPOSED expected value: the answer still changes only at 325, to B.
    assert result.down.price == pytest.approx(325.0)
    assert result.down.takes_over == "B"
    assert result.down.distance_percent == pytest.approx(-18.75)
    _assert_no_change(result.up, "up")
    assert "C" not in (result.up.takes_over, result.down.takes_over)


# 3. A range narrower than the breakpoint: no change either way.
def test_narrow_range_reports_no_change():
    narrow = PriceRange(low=350.0, high=800.0)  # invented test data
    result = _run([_a(), _b()], price_range=narrow)
    assert result.decision.chosen == "A"
    assert result.reason is None
    _assert_no_change(result.up, "up", narrow)
    _assert_no_change(result.down, "down", narrow)


# 4. Today's price missing.
def test_todays_price_missing():
    result = _run([_a(), _b()], facts=_facts(soy_price=None))
    assert result.today is None
    assert result.reason == "MISSING_INPUT"
    assert SOY in result.detail
    for point, direction in ((result.up, "up"), (result.down, "down")):
        assert point.direction == direction
        _assert_missing(point, "MISSING_INPUT")
        assert SOY in point.detail
    # The decision at today's price: every margin needs the soybean price.
    assert result.decision.answer == "not_resolved"


# 5. Another fact missing (a cost): the tipping points name the rotation.
def test_other_fact_missing_names_the_rotation():
    result = _run([_a(), _b()], facts=_facts(wheat_cost=None))
    assert result.today == TODAY
    assert result.reason == "MISSING_INPUT"
    for point in (result.up, result.down):
        _assert_missing(point, "MISSING_INPUT")
        assert "B" in point.detail
        assert "'A'" not in point.detail


# 6. margin_of a kind of year ranks by that kind and gives its own breakpoint.
def test_margin_of_a_kind_of_year():
    # la_nina: A = p - 200; B = (p - 200 + 250) / 2 = (p + 50) / 2.
    # They cross at p - 200 = (p + 50) / 2, so p = 450. At 400: A = 200,
    # B = 225, so B is chosen today and A takes over above 450.
    result = _run([_a(), _b()], margin_of="la_nina")
    assert result.decision.chosen == "B"
    up = result.up
    # PROPOSED expected value: 450, A, (450 - 400) / 400 * 100 = 12.5.
    assert up.price == pytest.approx(450.0)
    assert up.takes_over == "A"
    assert up.answer_after == "chosen"
    assert up.distance_percent == pytest.approx(12.5)
    _assert_no_change(result.down, "down")


# Not chosen today: computed the same way.
def test_none_meets_stays_none_meets():
    result = _run([_a(FAILS), _b(FAILS)])
    assert result.decision.answer == "none_meets"
    _assert_no_change(result.up, "up")
    _assert_no_change(result.down, "down")


def test_today_outside_the_range():
    result = _run([_a(), _b()], price_range=PriceRange(low=100.0, high=300.0))
    assert result.today == TODAY
    assert result.reason == "NOT_APPLICABLE"
    for point in (result.up, result.down):
        _assert_missing(point, "NOT_APPLICABLE")
        assert "outside" in point.detail


def test_today_zero_gives_no_distance():
    # Invented test data: today's price 0, a range from 0. At 0 B (125)
    # beats A (-200).
    result = _run(
        [_a(), _b()],
        facts=_facts(soy_price=0.0),
        price_range=PriceRange(low=0.0, high=800.0),
    )
    assert result.decision.chosen == "B"
    up = result.up
    assert up.price == pytest.approx(325.0)
    assert up.takes_over == "A"
    assert up.distance_percent is None
    assert up.reason == "NOT_COMPUTABLE"
    assert up.detail


def test_today_on_the_breakpoint():
    # PROPOSED: at 325 A and B tie, so the answer is not resolved today and
    # changes right at today's price in both directions (distance 0).
    result = _run([_a(), _b()], facts=_facts(soy_price=325.0))
    assert result.decision.answer == "not_resolved"
    assert result.up.price == pytest.approx(325.0)
    assert result.up.takes_over == "A"
    assert result.up.distance_percent == pytest.approx(0.0)
    assert result.down.price == pytest.approx(325.0)
    assert result.down.takes_over == "B"


# 7. Misuse.
def test_unknown_soybean_crop_is_refused():
    with pytest.raises(ValueError, match="not in the economic facts"):
        _run([_a(), _b()], soybean_crop_ids=["PLACEHOLDER_unknown"])


def test_cover_crop_named_as_soybean_is_refused():
    with pytest.raises(ValueError, match="grain"):
        _run([_a(), _b()], soybean_crop_ids=[COVER])


def test_differing_prices_are_refused():
    facts = _facts(soy_second_price=350.0)
    with pytest.raises(ValueError, match="one soybean price"):
        _run([_a(), _b()], facts=facts, soybean_crop_ids=[SOY, SOY_SECOND])


def test_empty_soybean_ids_are_refused():
    with pytest.raises(ValueError, match="soybean_crop_ids"):
        _run([_a(), _b()], soybean_crop_ids=[])
    with pytest.raises(ValueError, match="soybean_crop_ids"):
        _run([_a(), _b()], soybean_crop_ids=SOY)


@pytest.mark.parametrize(
    ("low", "high"),
    [(300.0, 300.0), (500.0, 300.0), (-1.0, 300.0), (float("nan"), 300.0)],
)
def test_bad_price_range_is_refused(low, high):
    with pytest.raises(ValueError):
        PriceRange(low=low, high=high)


def test_price_range_unit_is_checked():
    with pytest.raises(ValueError, match="unit"):
        PriceRange(low=100.0, high=800.0, unit="EUR t-1")


def test_bad_margin_of_is_refused():
    with pytest.raises(ValueError, match="margin_of"):
        _run([_a(), _b()], margin_of="dry")


# 8. Inputs not mutated, results frozen.
def test_inputs_not_mutated_and_results_frozen():
    facts = _facts()
    before = facts.model_dump(mode="json")
    options = [_a(), _b()]
    options_before = list(options)
    counts = dict(COUNTS)
    ids = [SOY]
    result = _run(options, facts=facts, year_counts=counts, soybean_crop_ids=ids)
    assert facts.model_dump(mode="json") == before
    assert options == options_before
    assert counts == COUNTS
    assert ids == [SOY]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.today = 1.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.down.price = 1.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        WIDE.low = 1.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        options[0].rotation_id = "Z"
