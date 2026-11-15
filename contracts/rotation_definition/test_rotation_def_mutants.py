"""Mutant-killing and boundary tests for ``contracts/rotation_definition/``.

Every crop, component, case, field, and rotation built here uses PLACEHOLDER
test inputs only.
"""

from __future__ import annotations

import copy
import datetime as dt
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, get_args
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from contracts.rotation_definition import common
from contracts.rotation_definition.common import DateValue, Missing, ReasonCode
from contracts.rotation_definition.rotation_definition import (
    AgYearStart,
    Management,
    RotationComponent,
    RotationDefinition,
)


def _date(text: str | None = "2027-01-15", **overrides: Any) -> dict[str, Any]:
    if text is None:
        item: dict[str, Any] = {
            "date": None,
            "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER detail"},
        }
    else:
        item = {
            "date": text,
            "provenance": "DECLARED",
            "source": "PLACEHOLDER source",
        }
    item.update(overrides)
    return item


def _management(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "residue": "left_on_surface",
        "grazing": {"missing": {"reason": "NOT_DECLARED"}},
        "termination": {"missing": {"reason": "NOT_DECLARED"}},
    }
    item.update(overrides)
    return item


def _component(
    component_id: str = "PLACEHOLDER-c1",
    position: int = 1,
    **overrides: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "component_id": component_id,
        "position": position,
        "crop_id": "PLACEHOLDER_crop",
        "purpose": "grain",
        "sowing": _date("2027-01-15"),
        "harvest": _date("2027-05-20"),
        "management": _management(),
    }
    item.update(overrides)
    return item


def _definition(
    components: list[dict[str, Any]] | None = None, **overrides: Any
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "contract": "rotation_definition",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "rotation_id": "PLACEHOLDER-rotation",
        "label": "PLACEHOLDER label",
        "ag_year_start": {
            "month": 1,
            "provisional": True,
            "provenance": "DECLARED",
            "source": "PLACEHOLDER source",
        },
        "repeats": True,
        "components": components if components is not None else [_component()],
    }
    doc.update(overrides)
    return doc


@contextmanager
def _weaken_model_validator(
    cls: type[BaseModel], name: str, replacement: Any
) -> Iterator[None]:
    """Temporarily replace a Pydantic model_validator and rebuild the schema."""
    decorator = cls.__pydantic_decorators__.model_validators[name]
    with patch.object(decorator, "func", replacement):
        cls.model_rebuild(force=True)
        try:
            yield
        finally:
            pass
    cls.model_rebuild(force=True)


# --- ag_year_start boundaries (1..12, strict int, source/assumption) ---------


@pytest.mark.parametrize("month", [1, 12])
def test_ag_year_start_month_endpoints_accepted(month: int) -> None:
    loaded = RotationDefinition.model_validate(
        _definition(
            ag_year_start={
                "month": month,
                "provisional": False,
                "provenance": "DECLARED",
                "assumption": True,
            }
        )
    )
    assert loaded.ag_year_start.month == month


@pytest.mark.parametrize("bad_month", [0, 13, -1, True, False, 1.0, "1"])
def test_ag_year_start_rejects_out_of_range_bool_and_non_int(bad_month: Any) -> None:
    doc = _definition()
    doc["ag_year_start"]["month"] = bad_month
    with pytest.raises(ValidationError):
        RotationDefinition.model_validate(doc)


@pytest.mark.parametrize("bad_source", [None, "", "  \t"])
def test_ag_year_start_without_source_and_without_assumption_rejected(
    bad_source: Any,
) -> None:
    doc = _definition(
        ag_year_start={
            "month": 6,
            "provisional": True,
            "provenance": "DECLARED",
            "source": bad_source,
            "assumption": False,
        }
    )
    with pytest.raises(ValidationError):
        RotationDefinition.model_validate(doc)


# --- IsoDate, Missing, and DateValue boundaries ------------------------------


def test_iso_date_calendar_boundaries_and_format() -> None:
    # Valid leap day and Python date object
    RotationDefinition.model_validate(
        _definition(
            [_component(sowing=_date("2024-02-29"), harvest=_date("2024-03-01"))]
        )
    )
    DateValue.model_validate(
        {
            "date": dt.date(2024, 2, 29),
            "provenance": "DECLARED",
            "source": "PLACEHOLDER source",
        }
    )

    for bad_date in (
        "2025-02-29",
        "2025-04-31",
        "2025-13-01",
        "2025-00-10",
        "2025-01-00",
        "2025-01-32",
        "2025-1-5",
        "20250105",
        "2025-01-05T00:00Z",
        dt.datetime(2025, 1, 5, 0, 0),
        20250105,
    ):
        with pytest.raises(ValidationError):
            DateValue.model_validate(
                {
                    "date": bad_date,
                    "provenance": "DECLARED",
                    "source": "PLACEHOLDER source",
                }
            )


def test_missing_input_detail_and_other_reason_codes() -> None:
    for bad_detail in (None, "", "  "):
        with pytest.raises(ValidationError):
            Missing.model_validate({"reason": "MISSING_INPUT", "detail": bad_detail})

    Missing.model_validate({"reason": "MISSING_INPUT", "detail": "PLACEHOLDER input"})
    for code in get_args(ReasonCode):
        if code != "MISSING_INPUT":
            Missing.model_validate({"reason": code})


def test_date_value_present_and_missing_invariants() -> None:
    # Present date with assumption=True and no source is valid
    DateValue.model_validate(
        {"date": "2027-01-15", "provenance": "DECLARED", "assumption": True}
    )
    # Present + missing -> rejected
    with pytest.raises(ValidationError, match="never both"):
        DateValue.model_validate(
            _date("2027-01-15", missing={"reason": "NOT_DECLARED"})
        )
    # Present without provenance -> rejected
    with pytest.raises(ValidationError, match="provenance label"):
        DateValue.model_validate({"date": "2027-01-15", "source": "PLACEHOLDER source"})
    # Missing without missing part -> rejected
    with pytest.raises(ValidationError, match="missing part with its reason"):
        DateValue.model_validate({"date": None})
    # Missing with provenance -> rejected
    with pytest.raises(ValidationError, match="no provenance label"):
        DateValue.model_validate(_date(None, provenance="DECLARED"))
    # Missing with assumption=True -> rejected
    with pytest.raises(ValidationError, match="not an assumption"):
        DateValue.model_validate(_date(None, assumption=True))


# --- Management discriminators & null guards ---------------------------------


@pytest.mark.parametrize("field_name", ["residue", "grazing", "termination"])
def test_management_rejects_null_with_d39_error(field_name: str) -> None:
    mgmt = _management(**{field_name: None})
    with pytest.raises(ValidationError, match=r"\(D39\)"):
        Management.model_validate(mgmt)


def test_management_discriminators_reject_cross_form_payloads() -> None:
    # Dict without 'missing' passed to residue -> rejected
    with pytest.raises(ValidationError):
        Management.model_validate(_management(residue={"intensity": "PLACEHOLDER"}))
    # String passed to grazing -> rejected
    with pytest.raises(ValidationError):
        Management.model_validate(_management(grazing="PLACEHOLDER_light"))
    # Object with both declared fields and 'missing' passed to termination -> rejected
    with pytest.raises(ValidationError):
        Management.model_validate(
            _management(
                termination={
                    "date": "2027-03-01",
                    "method": "chemical",
                    "missing": {"reason": "NOT_DECLARED"},
                }
            )
        )
    # Extra key alongside 'missing' -> rejected
    with pytest.raises(ValidationError):
        Management.model_validate(
            _management(
                grazing={"missing": {"reason": "NOT_DECLARED"}, "detail": "PLACEHOLDER"}
            )
        )


# --- component date ordering, positions, D21, and uniqueness -----------------


def test_harvest_on_same_day_as_sowing_accepted_and_one_day_before_rejected() -> None:
    RotationDefinition.model_validate(
        _definition(
            [_component(sowing=_date("2027-05-10"), harvest=_date("2027-05-10"))]
        )
    )
    with pytest.raises(ValidationError, match="harvest is before sowing"):
        RotationDefinition.model_validate(
            _definition(
                [_component(sowing=_date("2027-05-10"), harvest=_date("2027-05-09"))]
            )
        )
    # Only one date present in component does not trigger ordering rejection
    RotationDefinition.model_validate(
        _definition([_component(sowing=_date(None), harvest=_date("2027-05-09"))])
    )


def test_positions_and_component_id_uniqueness_boundaries() -> None:
    # Out-of-order {2, 1} is accepted
    RotationDefinition.model_validate(
        _definition(
            [
                _component("PLACEHOLDER-c1", 2),
                _component("PLACEHOLDER-c2", 1),
            ]
        )
    )

    # Non-adjacent duplicate component_id rejected
    with pytest.raises(ValidationError, match="share one component_id"):
        RotationDefinition.model_validate(
            _definition(
                [
                    _component("PLACEHOLDER-c1", 1),
                    _component("PLACEHOLDER-c2", 2),
                    _component("PLACEHOLDER-c1", 3),
                ]
            )
        )

    for bad_positions in ([0, 1], [-1, 1], [1, 3], [2, 3], [1, 1]):
        with pytest.raises(ValidationError, match="from 1"):
            RotationDefinition.model_validate(
                _definition(
                    [
                        _component("PLACEHOLDER-c1", bad_positions[0]),
                        _component("PLACEHOLDER-c2", bad_positions[1]),
                    ]
                )
            )

    # Strict int on position rejects bool and float
    for bad_pos in (True, 1.0):
        with pytest.raises(ValidationError):
            RotationDefinition.model_validate(
                _definition([_component("PLACEHOLDER-c1", bad_pos)])  # type: ignore[arg-type]
            )


def test_d21_requires_at_least_one_sowing_or_harvest_date() -> None:
    with pytest.raises(ValidationError, match=r"\(D21\)"):
        RotationDefinition.model_validate(_definition([]))

    all_missing = [
        _component("PLACEHOLDER-c1", 1, sowing=_date(None), harvest=_date(None)),
        _component("PLACEHOLDER-c2", 2, sowing=_date(None), harvest=_date(None)),
    ]
    with pytest.raises(ValidationError, match=r"\(D21\)"):
        RotationDefinition.model_validate(_definition(all_missing))

    # One harvest date on the second component suffices
    one_date = copy.deepcopy(all_missing)
    one_date[1]["harvest"] = _date("2027-06-01")
    RotationDefinition.model_validate(_definition(one_date))


# --- injected mutants proving guards fail when weakened ----------------------


def test_mutant_weakened_iso_date_regex_is_detected() -> None:
    compact = {
        "date": "20270115",
        "provenance": "DECLARED",
        "source": "PLACEHOLDER source",
    }
    with pytest.raises(ValidationError):
        DateValue.model_validate(compact)
    with patch.object(common, "_ISO_DATE", re.compile(r".*")):
        loaded = DateValue.model_validate(compact)
        assert loaded.date == dt.date(2027, 1, 15)


def test_mutant_weakened_ag_year_start_source_guard_is_detected() -> None:
    bad = {
        "month": 3,
        "provisional": True,
        "provenance": "DECLARED",
        "source": None,
        "assumption": False,
    }
    with pytest.raises(ValidationError):
        AgYearStart.model_validate(bad)
    with _weaken_model_validator(
        AgYearStart, "_source_or_assumption", lambda self: self
    ):
        AgYearStart.model_validate(bad)


def test_mutant_weakened_harvest_before_sowing_guard_is_detected() -> None:
    bad = _component(sowing=_date("2027-05-10"), harvest=_date("2027-05-09"))
    with pytest.raises(ValidationError, match="harvest is before sowing"):
        RotationComponent.model_validate(bad)
    with _weaken_model_validator(
        RotationComponent, "_harvest_not_before_sowing", lambda self: self
    ):
        RotationComponent.model_validate(bad)


def test_mutant_weakened_definition_consistent_guard_is_detected() -> None:
    bad = _definition(
        [
            _component("PLACEHOLDER-c1", 1, sowing=_date(None), harvest=_date(None)),
            _component("PLACEHOLDER-c1", 3, sowing=_date(None), harvest=_date(None)),
        ]
    )
    with pytest.raises(ValidationError):
        RotationDefinition.model_validate(bad)
    with _weaken_model_validator(RotationDefinition, "_consistent", lambda self: self):
        RotationDefinition.model_validate(bad)


def test_mutant_weakened_management_null_guard_loses_d39_diagnostic() -> None:
    bad = _management(grazing=None)
    with pytest.raises(ValidationError, match=r"\(D39\)"):
        Management.model_validate(bad)
    with _weaken_model_validator(
        Management, "_no_null_in_place_of_a_field", lambda cls, data: data
    ):
        with pytest.raises(ValidationError) as exc_info:
            Management.model_validate(bad)
        assert "(D39)" not in str(exc_info.value)
