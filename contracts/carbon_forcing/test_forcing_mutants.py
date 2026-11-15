"""Mutant-resistance, round-trip, G5 guard, unit, missing-reason, and boundary tests.

Targets ``contracts/carbon_forcing/models.py`` and the ``CarbonForcing``
contract boundary. Every identifier, unit, source, and numeric value here is
clearly marked PLACEHOLDER data; zero real soil/carbon constants and zero
simulated carbon outputs appear in this module.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from contracts.carbon_forcing import (
    AnnualCarbonInputSeries,
    AnnualSeries,
    AnnualValue,
    CarbonForcing,
    CarbonInputSeries,
    ClimateSeries,
    ForcingHorizon,
    SoilCoverSeries,
    StartingStateValue,
)
from contracts.carbon_forcing import models as cf_models
from contracts.inputs.common import Missing, ReasonCode, Value
from contracts.inputs.site_climate import MonthlyValue, YearMonth

EXAMPLE = Path(__file__).parent / "examples" / "PLACEHOLDER_carbon_forcing.json"
PLACEHOLDER_UNIT = "PLACEHOLDER_unit"
PLACEHOLDER_SOURCE = "PLACEHOLDER source"
PLACEHOLDER_DETAIL = "PLACEHOLDER detail"
PLACEHOLDER_KIND = "PLACEHOLDER_kind"
ALL_REASON_CODES: tuple[str, ...] = get_args(ReasonCode)


def _load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _ym(year: int, month: int) -> dict[str, int]:
    return {"year": year, "month": month}


def _rehorizon(
    data: dict[str, Any],
    start: tuple[int, int],
    months_count: int,
    *,
    value: float = 1.0,
) -> None:
    sy, sm = start
    first = sy * 12 + (sm - 1)
    ey, em0 = divmod(first + months_count - 1, 12)
    data["horizon"] = {"start": _ym(sy, sm), "end": _ym(ey, em0 + 1)}
    for series in data["climate"] + data["carbon_inputs"] + data["soil_cover"]:
        series["start"] = copy.deepcopy(data["horizon"]["start"])
        series["end"] = copy.deepcopy(data["horizon"]["end"])
        series["months"] = [
            {
                "year": divmod(first + i, 12)[0],
                "month": divmod(first + i, 12)[1] + 1,
                "value": value,
            }
            for i in range(months_count)
        ]


def _set_annual_years(
    data: dict[str, Any], first_ag_year: int, last_ag_year: int
) -> None:
    years = [
        {"ag_year": yr, "value": float(idx + 1)}
        for idx, yr in enumerate(range(first_ag_year, last_ag_year + 1))
    ]
    for series in data["annual_climate"] + data["annual_carbon_inputs"]:
        series["first_ag_year"] = first_ag_year
        series["last_ag_year"] = last_ag_year
        series["provenance"] = "DERIVED"
        series["source"] = PLACEHOLDER_SOURCE
        series["range_missing"] = {
            "reason": "NOT_AVAILABLE",
            "detail": PLACEHOLDER_DETAIL,
        }
        series["years"] = copy.deepcopy(years)


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


# --- 1. Round-trip JSON serialization ----------------------------------------


def test_full_placeholder_round_trip_json_and_dict_preservation() -> None:
    raw = _load()
    raw["example_data"] = False
    raw["soil_depth"] = {
        "value": 15.0,
        "unit": PLACEHOLDER_UNIT,
        "provenance": "DECLARED",
        "assumption": True,
        "range": {"low": 10.0, "high": 20.0, "kind": PLACEHOLDER_KIND},
    }
    raw["soil_properties"][0] = {
        "quantity": "placeholder_soil_property_a",
        "value": 5.0,
        "unit": PLACEHOLDER_UNIT,
        "provenance": "OBSERVED",
        "source": PLACEHOLDER_SOURCE,
        "range": {"low": 5.0, "high": 5.0, "kind": PLACEHOLDER_KIND},
    }
    raw["starting_state"][0] = {
        "quantity": "placeholder_state_quantity_a",
        "value": 0.0,
        "unit": PLACEHOLDER_UNIT,
        "provenance": "DECLARED",
        "assumption": True,
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": PLACEHOLDER_DETAIL},
    }

    model = CarbonForcing.model_validate(raw)
    dumped_json = model.model_dump_json(exclude_unset=True)
    reloaded_from_json = CarbonForcing.model_validate_json(dumped_json)
    reloaded_from_mode_json = CarbonForcing.model_validate(
        model.model_dump(mode="json")
    )
    reloaded_from_dict = CarbonForcing.model_validate(model.model_dump())

    assert reloaded_from_json == model
    assert reloaded_from_mode_json == model
    assert reloaded_from_dict == model
    assert json.loads(dumped_json) == raw
    assert reloaded_from_json.example_data is False
    assert reloaded_from_json.soil_depth.assumption is True
    assert reloaded_from_json.soil_depth.source is None
    assert reloaded_from_json.starting_state[0].value == 0.0


def test_empty_lists_and_multi_year_non_january_round_trip() -> None:
    data = _load()
    _rehorizon(data, (2001, 7), 24, value=0.0)
    _set_annual_years(data, 2001, 2002)
    data["soil_cover"] = []
    data["starting_state"] = []
    data["soil_properties"] = []

    model = CarbonForcing.model_validate(data)
    round_tripped = CarbonForcing.model_validate_json(
        model.model_dump_json(exclude_unset=True)
    )
    assert round_tripped == model
    assert round_tripped.annual_climate[0].first_ag_year == 2001
    assert round_tripped.annual_climate[0].last_ag_year == 2002
    assert round_tripped.soil_cover == []
    assert round_tripped.starting_state == []


# --- 2. G5 caller-defect guards & strict contract model checks ---------------


def test_contract_import_route_identity_for_g5() -> None:
    assert CarbonForcing is cf_models.CarbonForcing
    assert ForcingHorizon is cf_models.ForcingHorizon
    assert StartingStateValue is cf_models.StartingStateValue


@pytest.mark.parametrize(
    "bad_forcing",
    [
        None,
        {},
        {"contract": "carbon_forcing"},
        '{"contract": "carbon_forcing"}',
        42,
        SimpleNamespace(contract="carbon_forcing", case_id="PLACEHOLDER-case"),
    ],
    ids=["none", "empty-dict", "raw-dict", "json-text", "int", "duck-namespace"],
)
def test_g5_entrypoints_reject_non_carbon_forcing_with_type_error(
    bad_forcing: Any,
) -> None:
    from engine.amg import run_amg
    from engine.rothc import run_rothc

    with pytest.raises(TypeError, match="forcing"):
        run_amg(bad_forcing, parameters={})
    with pytest.raises(TypeError, match="forcing"):
        run_rothc(bad_forcing, parameters={})


@pytest.mark.parametrize(
    "bad_parameters",
    [
        None,
        [],
        "parameters",
        {"PLACEHOLDER/path.json": "not-a-record"},
        {1: {}},
    ],
    ids=["none", "list", "str", "non-dict-value", "non-str-key"],
)
def test_g5_entrypoints_reject_malformed_parameters_with_type_error(
    bad_parameters: Any,
) -> None:
    from engine.amg import run_amg
    from engine.rothc import run_rothc

    valid_forcing = CarbonForcing.model_validate(_load())
    with pytest.raises(TypeError, match="parameters"):
        run_amg(valid_forcing, parameters=bad_parameters)
    with pytest.raises(TypeError, match="parameters"):
        run_rothc(valid_forcing, parameters=bad_parameters)


def test_strict_type_enforcement_rejects_coercion_and_non_finite() -> None:
    base = _load()

    # Booleans must never coerce to int or float.
    for bad_bool_int in (True, False):
        bad_ym = copy.deepcopy(base)
        bad_ym["horizon"]["start"]["month"] = bad_bool_int
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad_ym)

        bad_ag = copy.deepcopy(base)
        bad_ag["annual_climate"][0]["years"][0]["ag_year"] = bad_bool_int
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad_ag)

        bad_val = copy.deepcopy(base)
        bad_val["climate"][0]["months"][0]["value"] = bad_bool_int
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad_val)

    # Strings and floats must never coerce to int or bool.
    for bad_flag in ("true", 1, 0, None):
        bad = copy.deepcopy(base)
        bad["example_data"] = bad_flag
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad)

    for bad_int in (1.0, "1"):
        bad = copy.deepcopy(base)
        bad["horizon"]["start"]["month"] = bad_int
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad)

        bad_yr = copy.deepcopy(base)
        bad_yr["annual_climate"][0]["first_ag_year"] = bad_int
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad_yr)

    # Non-finite floats must be rejected everywhere FiniteFloat is used.
    for non_finite in (math.nan, math.inf, -math.inf):
        bad_monthly = copy.deepcopy(base)
        bad_monthly["climate"][0]["months"][0]["value"] = non_finite
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad_monthly)

        with pytest.raises(ValidationError):
            StartingStateValue(
                quantity="placeholder_state",
                value=non_finite,
                unit=PLACEHOLDER_UNIT,
                provenance="DECLARED",
                assumption=True,
                range_missing=Missing(reason="NOT_AVAILABLE"),
            )


def test_extra_fields_forbidden_on_every_forcing_model() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        YearMonth(year=2001, month=1, extra_field=1)
    with pytest.raises(ValidationError, match="Extra inputs"):
        ForcingHorizon(
            start=YearMonth(year=2001, month=1),
            end=YearMonth(year=2001, month=1),
            extra_field=1,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        AnnualValue(ag_year=2001, value=1.0, extra_field=1)
    with pytest.raises(ValidationError, match="Extra inputs"):
        AnnualSeries(
            quantity="placeholder_q",
            unit=PLACEHOLDER_UNIT,
            provenance="DERIVED",
            assumption=True,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            first_ag_year=2001,
            last_ag_year=2001,
            years=[AnnualValue(ag_year=2001, value=1.0)],
            extra_field=1,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        AnnualCarbonInputSeries(
            quantity="placeholder_q",
            unit=PLACEHOLDER_UNIT,
            origin="placeholder_origin",
            provenance="DERIVED",
            assumption=True,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            first_ag_year=2001,
            last_ag_year=2001,
            years=[AnnualValue(ag_year=2001, value=1.0)],
            extra_field=1,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        ClimateSeries(
            quantity="placeholder_q",
            unit=PLACEHOLDER_UNIT,
            provenance="DERIVED",
            assumption=True,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            start=YearMonth(year=2001, month=1),
            end=YearMonth(year=2001, month=1),
            months=[MonthlyValue(year=2001, month=1, value=1.0)],
            extra_field=1,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        SoilCoverSeries(
            quantity="placeholder_q",
            unit=PLACEHOLDER_UNIT,
            provenance="DERIVED",
            assumption=True,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            start=YearMonth(year=2001, month=1),
            end=YearMonth(year=2001, month=1),
            months=[MonthlyValue(year=2001, month=1, value=1.0)],
            extra_field=1,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        CarbonInputSeries(
            quantity="placeholder_q",
            unit=PLACEHOLDER_UNIT,
            origin="placeholder_origin",
            provenance="DERIVED",
            assumption=True,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            start=YearMonth(year=2001, month=1),
            end=YearMonth(year=2001, month=1),
            months=[MonthlyValue(year=2001, month=1, value=1.0)],
            extra_field=1,
        )


# --- 3. Strict unit checks ---------------------------------------------------


@pytest.mark.parametrize("bad_unit", ["", " ", "\t\n", None, 123, True])
def test_strict_unit_checks_reject_empty_whitespace_and_non_string(
    bad_unit: Any,
) -> None:
    # Missing Value must still carry a valid non-empty unit string (C3.1).
    with pytest.raises(ValidationError):
        Value(value=None, unit=bad_unit, missing=Missing(reason="NOT_DECLARED"))

    with pytest.raises(ValidationError):
        StartingStateValue(
            quantity="placeholder_state",
            value=None,
            unit=bad_unit,
            missing=Missing(reason="NOT_DECLARED"),
        )

    # All-missing monthly and annual series still enforce strict non-empty unit.
    data = _load()
    data["climate"][1]["unit"] = bad_unit
    data["climate"][1]["months"] = [
        {
            "year": m["year"],
            "month": m["month"],
            "value": None,
            "missing": {"reason": "NO_COVERAGE"},
        }
        for m in data["climate"][1]["months"]
    ]
    del data["climate"][1]["provenance"]
    del data["climate"][1]["source"]
    del data["climate"][1]["range_missing"]
    with pytest.raises(ValidationError):
        CarbonForcing.model_validate(data)

    data_annual = _load()
    data_annual["annual_climate"][1]["unit"] = bad_unit
    with pytest.raises(ValidationError):
        CarbonForcing.model_validate(data_annual)


def test_unit_strings_preserved_verbatim_without_normalization() -> None:
    custom_unit = "PLACEHOLDER_Custom_Unit_1"
    data = _load()
    data["soil_depth"]["unit"] = custom_unit
    data["climate"][0]["unit"] = custom_unit
    data["annual_carbon_inputs"][0]["unit"] = custom_unit
    data["soil_cover"][0]["unit"] = custom_unit
    data["starting_state"][1]["unit"] = custom_unit

    loaded = CarbonForcing.model_validate_json(json.dumps(data))
    assert loaded.soil_depth.unit == custom_unit
    assert loaded.climate[0].unit == custom_unit
    assert loaded.annual_carbon_inputs[0].unit == custom_unit
    assert loaded.soil_cover[0].unit == custom_unit
    assert loaded.starting_state[1].unit == custom_unit


# --- 4. Missing-reason preservation ------------------------------------------


@pytest.mark.parametrize("reason", ALL_REASON_CODES)
def test_all_reason_codes_preserved_across_forcing_parts_and_json_round_trip(
    reason: str,
) -> None:
    missing_obj = {"reason": reason, "detail": f"PLACEHOLDER {reason}"}
    data = _load()
    data["soil_depth"] = {
        "value": None,
        "unit": PLACEHOLDER_UNIT,
        "missing": copy.deepcopy(missing_obj),
    }
    data["climate"][0]["months"][0] = {
        "year": 2001,
        "month": 1,
        "value": None,
        "missing": copy.deepcopy(missing_obj),
    }
    data["carbon_inputs"][0]["months"][0] = {
        "year": 2001,
        "month": 1,
        "value": None,
        "missing": copy.deepcopy(missing_obj),
    }
    data["soil_cover"][0]["months"][0] = {
        "year": 2001,
        "month": 1,
        "value": None,
        "missing": copy.deepcopy(missing_obj),
    }
    data["annual_climate"][1]["years"][0] = {
        "ag_year": 2001,
        "value": None,
        "missing": copy.deepcopy(missing_obj),
    }
    data["annual_carbon_inputs"][0]["years"][0] = {
        "ag_year": 2001,
        "value": None,
        "missing": copy.deepcopy(missing_obj),
    }
    del data["annual_carbon_inputs"][0]["provenance"]
    del data["annual_carbon_inputs"][0]["source"]
    del data["annual_carbon_inputs"][0]["range_missing"]
    data["soil_properties"][1]["missing"] = copy.deepcopy(missing_obj)
    data["starting_state"][1]["missing"] = copy.deepcopy(missing_obj)

    loaded = CarbonForcing.model_validate_json(json.dumps(data))
    reloaded = CarbonForcing.model_validate_json(
        loaded.model_dump_json(exclude_unset=True)
    )

    assert reloaded.soil_depth.missing == Missing(
        reason=reason, detail=f"PLACEHOLDER {reason}"
    )
    assert reloaded.climate[0].months[0].value is None
    assert reloaded.climate[0].months[0].missing.reason == reason
    assert reloaded.carbon_inputs[0].months[0].missing.reason == reason
    assert reloaded.soil_cover[0].months[0].missing.reason == reason
    assert reloaded.annual_climate[1].years[0].missing.reason == reason
    assert reloaded.annual_carbon_inputs[0].years[0].missing.reason == reason
    assert reloaded.soil_properties[1].missing.reason == reason
    assert reloaded.starting_state[1].missing.reason == reason


def test_missing_input_requires_non_empty_detail_and_unknown_reason_rejected() -> None:
    with pytest.raises(ValidationError, match="MISSING_INPUT"):
        Missing(reason="MISSING_INPUT", detail=None)
    for bad_detail in ("", "   "):
        with pytest.raises(ValidationError):
            Missing(reason="MISSING_INPUT", detail=bad_detail)

    data = _load()
    data["climate"][0]["range_missing"] = {"reason": "MISSING_INPUT"}
    with pytest.raises(ValidationError, match="MISSING_INPUT"):
        CarbonForcing.model_validate(data)

    for bad_reason in ("UNKNOWN_CODE", "not_declared", "", 123):
        bad = _load()
        bad["soil_depth"]["missing"] = {"reason": bad_reason}
        with pytest.raises(ValidationError):
            CarbonForcing.model_validate(bad)


def test_single_present_item_in_otherwise_missing_series_requires_header() -> None:
    """Kills mutants using ``all(...)`` or ``values[0]`` instead of ``any(...)``."""
    for present_idx in (0, 5, 11):
        months = [
            {
                "year": 2001,
                "month": i + 1,
                "value": None,
                "missing": {"reason": "NO_COVERAGE"},
            }
            for i in range(12)
        ]
        months[present_idx] = {"year": 2001, "month": present_idx + 1, "value": 0.0}
        with pytest.raises(ValidationError, match="provenance label"):
            ClimateSeries(
                quantity="placeholder_mixed",
                unit=PLACEHOLDER_UNIT,
                start=YearMonth(year=2001, month=1),
                end=YearMonth(year=2001, month=12),
                months=months,
            )

    for present_idx in (0, 1):
        years = [
            {"ag_year": 2001, "value": None, "missing": {"reason": "NO_COVERAGE"}},
            {"ag_year": 2002, "value": None, "missing": {"reason": "NO_COVERAGE"}},
        ]
        years[present_idx] = {"ag_year": 2001 + present_idx, "value": 0.0}
        with pytest.raises(ValidationError, match="provenance label"):
            AnnualSeries(
                quantity="placeholder_annual_mixed",
                unit=PLACEHOLDER_UNIT,
                first_ag_year=2001,
                last_ag_year=2002,
                years=years,
            )


def test_all_missing_annual_series_forbids_provenance_assumption_and_range_missing() -> (
    None
):
    base_years = [
        {"ag_year": 2001, "value": None, "missing": {"reason": "NO_COVERAGE"}}
    ]
    AnnualSeries(
        quantity="placeholder_annual_missing",
        unit=PLACEHOLDER_UNIT,
        first_ag_year=2001,
        last_ag_year=2001,
        years=base_years,
    )
    with pytest.raises(ValidationError, match="no provenance label"):
        AnnualSeries(
            quantity="placeholder_annual_missing",
            unit=PLACEHOLDER_UNIT,
            provenance="DERIVED",
            first_ag_year=2001,
            last_ag_year=2001,
            years=base_years,
        )
    with pytest.raises(ValidationError, match="not an assumption"):
        AnnualSeries(
            quantity="placeholder_annual_missing",
            unit=PLACEHOLDER_UNIT,
            assumption=True,
            first_ag_year=2001,
            last_ag_year=2001,
            years=base_years,
        )
    with pytest.raises(ValidationError, match="no range"):
        AnnualSeries(
            quantity="placeholder_annual_missing",
            unit=PLACEHOLDER_UNIT,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            first_ag_year=2001,
            last_ag_year=2001,
            years=base_years,
        )


# --- 5. Monthly / annual forcing boundary tests ------------------------------


@pytest.mark.parametrize("bad_month", [0, 13, -1])
def test_month_number_bounds_rejected(bad_month: int) -> None:
    with pytest.raises(ValidationError):
        YearMonth(year=2001, month=bad_month)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ((2001, 1), (2001, 12), (2001, 2001)),
        ((2001, 7), (2002, 6), (2001, 2001)),
        ((2001, 7), (2003, 6), (2001, 2002)),
        ((2001, 12), (2004, 11), (2001, 2003)),
        ((2001, 1), (2001, 1), None),
        ((2001, 1), (2001, 11), None),
        ((2001, 1), (2002, 1), None),
        ((2001, 1), (2002, 11), None),
        ((2001, 1), (2003, 1), None),
    ],
)
def test_ag_years_of_boundaries(
    start: tuple[int, int],
    end: tuple[int, int],
    expected: tuple[int, int] | None,
) -> None:
    horizon = ForcingHorizon(
        start=YearMonth(year=start[0], month=start[1]),
        end=YearMonth(year=end[0], month=end[1]),
    )
    assert cf_models._ag_years_of(horizon) == expected


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ((2001, 1), (2000, 12)),
        ((2001, 6), (2001, 5)),
        ((2001, 6), (2000, 6)),
    ],
    ids=["dec-to-jan-backwards", "same-year-one-month-backwards", "one-year-backwards"],
)
def test_horizon_ordered_boundaries(
    start: tuple[int, int], end: tuple[int, int]
) -> None:
    with pytest.raises(ValidationError, match="ends before it starts"):
        ForcingHorizon(
            start=YearMonth(year=start[0], month=start[1]),
            end=YearMonth(year=end[0], month=end[1]),
        )


def test_only_annual_carbon_inputs_still_enforces_whole_ag_years() -> None:
    data = _load()
    _rehorizon(data, (2001, 1), 11)
    data["annual_climate"] = []
    with pytest.raises(ValidationError, match="whole number of agricultural years"):
        CarbonForcing.model_validate(data)

    data_ok = _load()
    _rehorizon(data_ok, (2001, 1), 15)
    data_ok["annual_climate"] = []
    data_ok["annual_carbon_inputs"] = []
    loaded = CarbonForcing.model_validate(data_ok)
    assert loaded.horizon.end == YearMonth(year=2002, month=3)


def test_non_adjacent_duplicate_quantities_rejected_in_every_list() -> None:
    # Monthly lists: climate, carbon_inputs, soil_cover
    for list_key in ("climate", "carbon_inputs", "soil_cover"):
        data = _load()
        first = copy.deepcopy(data[list_key][0])
        middle = copy.deepcopy(first)
        middle["quantity"] = "placeholder_middle_distinct"
        dup = copy.deepcopy(first)
        data[list_key] = [first, middle, dup]
        with pytest.raises(ValidationError, match="appears more than once"):
            CarbonForcing.model_validate(data)

    # Annual lists: annual_climate, annual_carbon_inputs
    for list_key in ("annual_climate", "annual_carbon_inputs"):
        data = _load()
        first = copy.deepcopy(data[list_key][0])
        middle = copy.deepcopy(first)
        middle["quantity"] = "placeholder_annual_middle_distinct"
        dup = copy.deepcopy(first)
        data[list_key] = [first, middle, dup]
        with pytest.raises(ValidationError, match="appears more than once"):
            CarbonForcing.model_validate(data)

    # Item lists: soil_properties, starting_state
    for list_key in ("soil_properties", "starting_state"):
        data = _load()
        first = copy.deepcopy(data[list_key][0])
        middle = copy.deepcopy(first)
        middle["quantity"] = "placeholder_item_middle_distinct"
        dup = copy.deepcopy(first)
        data[list_key] = [first, middle, dup]
        with pytest.raises(ValidationError, match="appears more than once"):
            CarbonForcing.model_validate(data)


def test_same_quantity_allowed_simultaneously_in_all_seven_lists() -> None:
    shared_q = "placeholder_shared_across_all"
    data = _load()
    data["climate"] = [copy.deepcopy(data["climate"][0])]
    data["climate"][0]["quantity"] = shared_q
    data["carbon_inputs"][0]["quantity"] = shared_q
    data["annual_climate"] = [copy.deepcopy(data["annual_climate"][0])]
    data["annual_climate"][0]["quantity"] = shared_q
    data["annual_carbon_inputs"][0]["quantity"] = shared_q
    data["soil_properties"] = [copy.deepcopy(data["soil_properties"][0])]
    data["soil_properties"][0]["quantity"] = shared_q
    data["soil_cover"][0]["quantity"] = shared_q
    data["starting_state"] = [copy.deepcopy(data["starting_state"][0])]
    data["starting_state"][0]["quantity"] = shared_q

    loaded = CarbonForcing.model_validate(data)
    assert loaded.climate[0].quantity == shared_q
    assert loaded.starting_state[0].quantity == shared_q


def test_monthly_series_shifted_by_one_month_rejected_for_every_monthly_part() -> None:
    for list_key in ("climate", "carbon_inputs", "soil_cover"):
        data = _load()
        series = data[list_key][0]
        series["start"] = _ym(2001, 2)
        series["end"] = _ym(2002, 1)
        series["months"] = [
            {"year": 2001 + (m // 12), "month": (m % 12) + 1, "value": 1.0}
            for m in range(1, 13)
        ]
        with pytest.raises(
            ValidationError, match="start and end are those of the horizon"
        ):
            CarbonForcing.model_validate(data)


def test_annual_series_boundaries_and_origin_validation() -> None:
    # Non-adjacent duplicate year in 3-year series rejected.
    with pytest.raises(ValidationError, match="every agricultural year"):
        AnnualSeries(
            quantity="placeholder_annual",
            unit=PLACEHOLDER_UNIT,
            provenance="DERIVED",
            source=PLACEHOLDER_SOURCE,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            first_ag_year=2001,
            last_ag_year=2003,
            years=[
                AnnualValue(ag_year=2001, value=1.0),
                AnnualValue(ag_year=2002, value=2.0),
                AnnualValue(ag_year=2001, value=3.0),
            ],
        )

    # Empty years with last_ag_year >= first_ag_year rejected ("stop before last_ag_year").
    with pytest.raises(ValidationError, match="stop before last_ag_year"):
        AnnualSeries(
            quantity="placeholder_annual",
            unit=PLACEHOLDER_UNIT,
            first_ag_year=2001,
            last_ag_year=2001,
            years=[],
        )

    # Extra year beyond last_ag_year rejected.
    with pytest.raises(ValidationError, match="stop before last_ag_year"):
        AnnualSeries(
            quantity="placeholder_annual",
            unit=PLACEHOLDER_UNIT,
            provenance="DERIVED",
            source=PLACEHOLDER_SOURCE,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            first_ag_year=2001,
            last_ag_year=2001,
            years=[
                AnnualValue(ag_year=2001, value=1.0),
                AnnualValue(ag_year=2002, value=2.0),
            ],
        )

    # Invalid origin patterns rejected on both CarbonInputSeries and AnnualCarbonInputSeries.
    for bad_origin in ("", "PLACEHOLDER_origin", "1origin", "origin-a", "_origin"):
        data = _load()
        data["carbon_inputs"][0]["origin"] = bad_origin
        with pytest.raises(ValidationError, match="origin"):
            CarbonForcing.model_validate(data)

        data_ann = _load()
        data_ann["annual_carbon_inputs"][0]["origin"] = bad_origin
        with pytest.raises(ValidationError, match="origin"):
            CarbonForcing.model_validate(data_ann)


# --- 6. Injected validator mutants -------------------------------------------


def test_mutant_weakened_month_index_allows_backwards_horizon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = {"start": _ym(2001, 2), "end": _ym(2001, 1)}
    with pytest.raises(ValidationError, match="ends before it starts"):
        ForcingHorizon.model_validate(bad)

    monkeypatch.setattr(cf_models, "_month_index", lambda m: 0)
    accepted = ForcingHorizon.model_validate(bad)
    assert accepted.start.month == 2 and accepted.end.month == 1


def test_mutant_weakened_horizon_ordered_validator_allows_reversed_horizon() -> None:
    bad = {"start": _ym(2002, 1), "end": _ym(2001, 12)}
    with pytest.raises(ValidationError, match="ends before it starts"):
        ForcingHorizon.model_validate(bad)

    with _weaken_model_validator(ForcingHorizon, "_ordered", lambda self: self):
        accepted = ForcingHorizon.model_validate(bad)
        assert accepted.end.year == 2001


def test_mutant_weakened_annual_series_consistent_allows_year_gap() -> None:
    bad = {
        "quantity": "placeholder_annual",
        "unit": PLACEHOLDER_UNIT,
        "provenance": "DERIVED",
        "source": PLACEHOLDER_SOURCE,
        "range_missing": {"reason": "NOT_AVAILABLE"},
        "first_ag_year": 2001,
        "last_ag_year": 2003,
        "years": [
            {"ag_year": 2001, "value": 1.0},
            {"ag_year": 2003, "value": 3.0},
        ],
    }
    with pytest.raises(ValidationError, match="every agricultural year"):
        AnnualSeries.model_validate(bad)

    with _weaken_model_validator(AnnualSeries, "_consistent", lambda self: self):
        accepted = AnnualSeries.model_validate(bad)
        assert len(accepted.years) == 2


def test_mutant_weakened_covers_horizon_allows_shifted_carbon_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    ci = data["carbon_inputs"][0]
    ci["start"] = _ym(2001, 2)
    ci["end"] = _ym(2002, 1)
    ci["months"] = [
        {"year": 2001 + (m // 12), "month": (m % 12) + 1, "value": 1.0}
        for m in range(1, 13)
    ]
    with pytest.raises(ValidationError, match="start and end are those of the horizon"):
        CarbonForcing.model_validate(data)

    monkeypatch.setattr(cf_models, "_covers_horizon", lambda s, h, w: None)
    accepted = CarbonForcing.model_validate(data)
    assert accepted.carbon_inputs[0].start == YearMonth(year=2001, month=2)


def test_mutant_weakened_covers_ag_years_allows_extra_annual_climate_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    ac = data["annual_climate"][0]
    ac["last_ag_year"] = 2002
    ac["years"].append({"ag_year": 2002, "value": 2.0})
    with pytest.raises(ValidationError, match="agricultural years of the horizon"):
        CarbonForcing.model_validate(data)

    monkeypatch.setattr(cf_models, "_covers_ag_years", lambda s, y, w: None)
    accepted = CarbonForcing.model_validate(data)
    assert accepted.annual_climate[0].last_ag_year == 2002


def test_mutant_weakened_carbon_forcing_consistent_allows_duplicate_climate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["climate"][1]["quantity"] = data["climate"][0]["quantity"]
    with pytest.raises(ValidationError, match="appears more than once"):
        CarbonForcing.model_validate(data)

    with _weaken_model_validator(CarbonForcing, "_consistent", lambda self: self):
        accepted = CarbonForcing.model_validate(data)
        assert accepted.climate[0].quantity == accepted.climate[1].quantity
