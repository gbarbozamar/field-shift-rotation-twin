"""Targeted validator-boundary and mutant-killing tests for ``contracts/results/models.py``.

Covers C1.1-C1.6, C2.1-C2.2, C3.1-C3.2, C4.1-C4.6, C5.3-C5.4, D12, and D163
boundaries plus injected validator mutants proving failure if rules are weakened.
Every identifier, source, and number here is PLACEHOLDER test data only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.results import models as results_models
from contracts.results.models import (
    PROVENANCE_OF_SOIL_LOSS,
    UNIT_SOIL_CARBON_TREND,
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_SOIL_LOSS_MONTHLY,
    UNIT_WATER_DEFICIT_EXPOSURE,
    AnnualSoilLoss,
    IndicatorValue,
    Missing,
    MonthlySoilLoss,
    Range,
    ResultsPerRotation,
    ResultsTable,
    ResultsTableRow,
    SoilCarbonTrend,
    SoilLossNotBuilt,
    SoilLossResults,
    WaterDeficitExposure,
    WaterDeficitExposureNotBuilt,
)

EXAMPLES = Path(__file__).parent / "examples"
SOURCE = "PLACEHOLDER source"
KIND = "PLACEHOLDER_kind"


def _load_rotation() -> dict[str, Any]:
    return json.loads(
        (EXAMPLES / "PLACEHOLDER_results_per_rotation.json").read_text(encoding="utf-8")
    )


def _load_table() -> dict[str, Any]:
    return json.loads(
        (EXAMPLES / "PLACEHOLDER_results_table.json").read_text(encoding="utf-8")
    )


def _monthly_year(
    ag_year: int, start_month: int = 1, *, value: float = 1.0
) -> list[MonthlySoilLoss]:
    items: list[MonthlySoilLoss] = []
    for offset in range(12):
        cal_year, month_zero = divmod(ag_year * 12 + (start_month - 1) + offset, 12)
        items.append(
            MonthlySoilLoss(
                indicator="soil_loss",
                direction="lower_is_better",
                value=value,
                unit=UNIT_SOIL_LOSS_MONTHLY,
                range_missing=Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER"),
                provenance="DERIVED",
                source=SOURCE,
                year=cal_year,
                month=month_zero + 1,
                ag_year=ag_year,
            )
        )
    return items


# --- 1. Range inclusive bounds vs degenerate equal bounds (C2.1, C2.2) ---------


@pytest.mark.parametrize("value", [1.0, 2.0], ids=["at-low", "at-high"])
def test_range_inclusive_bounds_accepted_and_degenerate_rejected(value: float) -> None:
    item = IndicatorValue(
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=value,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        range=Range(low=1.0, high=2.0, kind=KIND),
        provenance="SIMULATED",
        source=SOURCE,
    )
    assert item.value == value

    # Strictly outside by epsilon is rejected.
    with pytest.raises(ValidationError, match="outside its own range"):
        IndicatorValue(
            indicator="water_deficit_exposure",
            direction="higher_is_better",
            value=0.9999,
            unit=UNIT_WATER_DEFICIT_EXPOSURE,
            range=Range(low=1.0, high=2.0, kind=KIND),
            provenance="SIMULATED",
            source=SOURCE,
        )

    # Degenerate range low == high == value is rejected by C2.2.
    with pytest.raises(ValidationError, match="two bounds equal to the value"):
        IndicatorValue(
            indicator="water_deficit_exposure",
            direction="higher_is_better",
            value=1.0,
            unit=UNIT_WATER_DEFICIT_EXPOSURE,
            range=Range(low=1.0, high=1.0, kind=KIND),
            provenance="SIMULATED",
            source=SOURCE,
        )


def test_assumption_without_source_accepted_and_missing_assumption_rejected() -> None:
    accepted = IndicatorValue(
        indicator="soil_carbon_trend",
        direction="higher_is_better",
        value=0.0,
        unit=UNIT_SOIL_CARBON_TREND,
        range_missing=Missing(reason="NOT_AVAILABLE"),
        provenance="DERIVED",
        assumption=True,
    )
    assert accepted.assumption is True

    with pytest.raises(ValidationError, match="no source and no assumption"):
        IndicatorValue(
            indicator="soil_carbon_trend",
            direction="higher_is_better",
            value=None,
            unit=UNIT_SOIL_CARBON_TREND,
            missing=Missing(reason="NOT_AVAILABLE"),
            assumption=True,
        )


# --- 2. Provenance labels (C4.1, C4.6) ----------------------------------------


@pytest.mark.parametrize("label", ["DECLARED", "OBSERVED", "DERIVED", "SIMULATED"])
def test_water_and_carbon_accept_all_provenance_labels(label: str) -> None:
    water = WaterDeficitExposure(
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        time_basis="ag_year",
        ag_year=2001,
        value=0.5,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        range_missing=Missing(reason="NOT_AVAILABLE"),
        provenance=label,  # type: ignore[arg-type]
        source=SOURCE,
    )
    assert water.provenance == label


@pytest.mark.parametrize("bad_label", ["DECLARED", "OBSERVED", "SIMULATED"])
def test_soil_loss_rejects_every_provenance_except_derived(bad_label: str) -> None:
    with pytest.raises(ValidationError, match="C4.6"):
        AnnualSoilLoss(
            indicator="soil_loss",
            direction="lower_is_better",
            ag_year=2001,
            value=1.0,
            unit=UNIT_SOIL_LOSS_ANNUAL,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            provenance=bad_label,  # type: ignore[arg-type]
            source=SOURCE,
        )


# --- 3. C5.3 / C5.4 agricultural year & 12 consecutive months -----------------


def test_non_january_start_month_accepted_and_mismatched_start_rejected() -> None:
    annual = [
        AnnualSoilLoss(
            indicator="soil_loss",
            direction="lower_is_better",
            ag_year=yr,
            value=1.0,
            unit=UNIT_SOIL_LOSS_ANNUAL,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            provenance=PROVENANCE_OF_SOIL_LOSS,
            source=SOURCE,
        )
        for yr in (2001, 2002)
    ]
    valid = SoilLossResults(
        annual=annual,
        monthly=_monthly_year(2001, start_month=7) + _monthly_year(2002, start_month=7),
    )
    assert valid.monthly[0].month == 7

    # Mixing start months across years violates C5.4.
    with pytest.raises(ValidationError, match="C5.4"):
        SoilLossResults(
            annual=annual,
            monthly=_monthly_year(2001, start_month=7)
            + _monthly_year(2002, start_month=8),
        )

    # 12 consecutive months shifted into calendar year 2000 for ag_year 2001 fails C5.3.
    shifted = _monthly_year(2000, start_month=7)
    for item in shifted:
        object.__setattr__(item, "ag_year", 2001)
    with pytest.raises(ValidationError, match="C5.3"):
        SoilLossResults(annual=[annual[0]], monthly=shifted)


# --- 4. D163 time bases & ResultsTable / D12 PartNotBuilt ---------------------


def test_d163_water_time_basis_consistency() -> None:
    data = _load_rotation()
    w0 = copy.deepcopy(data["water_deficit_exposure"][0])
    w1 = copy.deepcopy(w0)
    w1["ag_year"] = w0["ag_year"] + 1
    data["water_deficit_exposure"] = [w0, w1]
    loaded = ResultsPerRotation.model_validate(data)
    assert len(loaded.water_deficit_exposure) == 2

    # Duplicate ag_year on water_deficit_exposure is rejected.
    data["water_deficit_exposure"][1]["ag_year"] = w0["ag_year"]
    with pytest.raises(ValidationError, match="repeats agricultural year"):
        ResultsPerRotation.model_validate(data)

    # Two rotation-level values are rejected.
    for item in data["water_deficit_exposure"]:
        item["time_basis"] = "rotation"
        item.pop("ag_year", None)
    with pytest.raises(ValidationError, match="more than one value"):
        ResultsPerRotation.model_validate(data)


def test_d12_part_not_built_units_order_and_reason_boundaries() -> None:
    # Wrong unit order for soil_loss is rejected.
    with pytest.raises(ValidationError, match="in that order"):
        SoilLossNotBuilt(
            indicator="soil_loss",
            direction="lower_is_better",
            units=[UNIT_SOIL_LOSS_MONTHLY, UNIT_SOIL_LOSS_ANNUAL],
            missing=Missing(reason="NOT_AVAILABLE"),
        )
    # Wrong reason for PartNotBuilt is rejected.
    with pytest.raises(ValidationError, match="NOT_AVAILABLE"):
        WaterDeficitExposureNotBuilt(
            indicator="water_deficit_exposure",
            direction="higher_is_better",
            units=[UNIT_WATER_DEFICIT_EXPOSURE],
            missing=Missing(reason="NOT_DECLARED"),
        )


def test_results_table_rejects_mismatched_cells_and_wrong_indicator_time_basis() -> (
    None
):
    data = _load_table()
    # Drop one row from one rotation -> mismatched cells rejected.
    dropped = copy.deepcopy(data)
    dropped["rows"].pop()
    with pytest.raises(ValidationError, match="do not have the same cells"):
        ResultsTable.model_validate(dropped)

    # soil_loss row with time_basis="rotation" is rejected.
    with pytest.raises(ValidationError, match="C1.2"):
        ResultsTableRow(
            rotation_id="PLACEHOLDER_rot",
            scenario_id="PLACEHOLDER_scen",
            indicator="soil_loss",
            direction="lower_is_better",
            time_basis="rotation",
            value=1.0,
            unit=UNIT_SOIL_LOSS_ANNUAL,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            provenance="DERIVED",
            source=SOURCE,
        )

    # soil_carbon_trend row with time_basis="ag_year" is rejected.
    with pytest.raises(ValidationError, match="C1.5"):
        ResultsTableRow(
            rotation_id="PLACEHOLDER_rot",
            scenario_id="PLACEHOLDER_scen",
            indicator="soil_carbon_trend",
            direction="higher_is_better",
            time_basis="ag_year",
            ag_year=2001,
            carbon_model="amg",
            computation="end_minus_start",
            value=0.1,
            unit=UNIT_SOIL_CARBON_TREND,
            range_missing=Missing(reason="NOT_AVAILABLE"),
            provenance="SIMULATED",
            source=SOURCE,
        )


# --- 5. Injected validator mutants --------------------------------------------


def test_mutant_weakened_soil_loss_provenance_fails_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = AnnualSoilLoss.model_construct(
        indicator="soil_loss",
        direction="lower_is_better",
        ag_year=2001,
        value=1.0,
        unit=UNIT_SOIL_LOSS_ANNUAL,
        range_missing=Missing(reason="NOT_AVAILABLE"),
        provenance="SIMULATED",
        source=SOURCE,
    ).model_dump()

    with pytest.raises(ValidationError, match="C4.6"):
        AnnualSoilLoss.model_validate(bad)

    monkeypatch.setattr(results_models, "PROVENANCE_OF_SOIL_LOSS", "SIMULATED")
    accepted = AnnualSoilLoss.model_validate(bad)
    assert accepted.provenance == "SIMULATED"


def test_mutant_weakened_time_basis_check_allows_mixed_d163_bases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load_rotation()
    second = copy.deepcopy(data["water_deficit_exposure"][0])
    second["time_basis"] = "rotation"
    second.pop("ag_year", None)
    data["water_deficit_exposure"].append(second)

    with pytest.raises(ValidationError, match="mixes the time bases"):
        ResultsPerRotation.model_validate(data)

    monkeypatch.setattr(results_models, "_check_one_time_basis", lambda values: None)
    accepted = ResultsPerRotation.model_validate(data)
    assert len(accepted.water_deficit_exposure) == 3


def test_mutant_weakened_indicator_problems_allows_missing_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = {
        "indicator": "soil_carbon_trend",
        "direction": "higher_is_better",
        "carbon_model": "amg",
        "computation": "end_minus_start",
        "value": 0.2,
        "unit": UNIT_SOIL_CARBON_TREND,
    }
    with pytest.raises(ValidationError, match="provenance label"):
        SoilCarbonTrend.model_validate(bad)

    monkeypatch.setattr(results_models.IndicatorValue, "_problems", lambda self: [])
    accepted = SoilCarbonTrend.model_validate(bad)
    assert accepted.provenance is None


def test_mutant_weakened_direction_map_allows_wrong_soil_loss_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = {
        "indicator": "soil_loss",
        "direction": "higher_is_better",
        "ag_year": 2001,
        "value": 1.0,
        "unit": UNIT_SOIL_LOSS_ANNUAL,
        "range_missing": {"reason": "NOT_AVAILABLE"},
        "provenance": PROVENANCE_OF_SOIL_LOSS,
        "source": SOURCE,
    }
    with pytest.raises(ValidationError, match="lower_is_better"):
        AnnualSoilLoss.model_validate(bad)

    monkeypatch.setitem(results_models.DIRECTION_OF, "soil_loss", "higher_is_better")
    accepted = AnnualSoilLoss.model_validate(bad)
    assert accepted.direction == "higher_is_better"
