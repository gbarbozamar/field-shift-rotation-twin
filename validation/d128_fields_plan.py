"""Deterministic in-process D128 test-plan harness on two demonstration fields.

Runs the shipped D128 chain end to end over two synthetic PLACEHOLDER
``SiteSoilSlope`` demonstration fields (``field_demo_gentle`` and
``field_demo_steep``), synthetic PLACEHOLDER ``SiteClimate``, the two D128
rotations (``web/src/data/demo_rotations_d128.json``), and the shipped
``params/records/`` catalogue (132 records):

1. ``EP2`` (``build_rotation_calendar``, ``list_phases``, ``phase_calendar``)
2. ``daily_reference_evapotranspiration`` (FAO-56 Penman-Monteith ET0)
3. ``EP1`` (``compute_soil_loss``)
4. ``EP3`` (``compute_water_deficit_exposure``)
5. ``EP4`` (``build_residue_ledger``)
6. ``[D0]`` (``compare_with_decision``) and ``[W0]`` (``compare_with_full_indicator``)

Pure core functions take caller-supplied inputs and touch no network, clock, or
randomness; small convenience loaders handle reading the shipped JSON files.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import (
    ClimatePoint,
    DailySeries,
    DailyValue,
    SiteClimate,
)
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    IndicatorValue,
    Missing,
    ResultsTable,
    ResultsTableRow,
    SoilLossResults,
    WaterDeficitExposure,
)
from contracts.rotation_definition.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import list_phases, phase_calendar
from engine.erosion import compute_soil_loss
from engine.residues import build_residue_ledger
from engine.residues.ledger import ResidueLedger
from engine.water import (
    compute_water_deficit_exposure,
    daily_reference_evapotranspiration,
)
from engine.water._parameters import Catalogue
from engine.water.exposure import (
    BASAL_CROP_COEFFICIENT,
    CROP_KEY,
    DAILY_INPUTS,
    NO_CROP_ON_THE_DAY,
    PRECIPITATION,
    STAGE_KEY,
    STAGES,
    _ag_year_of,
)
from engine.water.living_crop import live_crop_over_record
from engine.water.stages import by_stage
from params.catalogue import check_catalogue, load_folder
from validation.trivial_comparator import ComparisonItem, compare_with_decision
from validation.trivial_comparator_water import (
    WaterComparisonItem,
    WaterDay,
    compare_with_full_indicator,
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_ROTATIONS_PATH: Final[Path] = (
    REPO_ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
)
DEFAULT_RECORDS_DIR: Final[Path] = REPO_ROOT / "params" / "records"

DEFAULT_CASE_ID: Final[str] = "d128-two-fields-plan"
FIELD_DEMO_GENTLE: Final[str] = "field_demo_gentle"
FIELD_DEMO_STEEP: Final[str] = "field_demo_steep"

CLIMATE_START: Final[dt.date] = dt.date(2001, 1, 1)
CLIMATE_END: Final[dt.date] = dt.date(2024, 12, 31)
BOUNDARY_AG_YEARS: Final[tuple[int, int]] = (2000, 2024)
FULL_AG_YEARS: Final[tuple[int, ...]] = tuple(range(2001, 2024))

SCENARIO_SEPARATOR: Final[str] = "+"

# Default PLACEHOLDER topographic and soil values for the two synthetic fields.
# Both fields share the same non-topographic soil properties so EP3/EP4 match
# identically while EP1 reflects the steeper slope length and steepness.
DEFAULT_GENTLE_SLOPE_LENGTH_M: Final[float] = 25.0
DEFAULT_GENTLE_SLOPE_STEEPNESS_PERCENT: Final[float] = 1.5
DEFAULT_STEEP_SLOPE_LENGTH_M: Final[float] = 120.0
DEFAULT_STEEP_SLOPE_STEEPNESS_PERCENT: Final[float] = 12.0
DEFAULT_PLACEHOLDER_K_FACTOR: Final[float] = 0.032

DEFAULT_SHARED_HYDRAULIC_PROPERTIES: Final[tuple[dict[str, Any], ...]] = (
    {
        "quantity": "soil_available_water_capacity",
        "value": 160.0,
        "unit": "mm m-1",
        "provenance": "DECLARED",
        "source": (
            "PLACEHOLDER: synthetic shared soil hydraulic capacity for D128 "
            "two-fields harness, not a real site measurement"
        ),
        "range_missing": {
            "reason": "NOT_AVAILABLE",
            "detail": "PLACEHOLDER synthetic harness value; no measured range",
        },
    },
    {
        "quantity": "soil_saturation_water_content",
        "value": 0.45,
        "unit": "m3 m-3",
        "provenance": "DECLARED",
        "source": (
            "PLACEHOLDER: synthetic shared soil hydraulic porosity for D128 "
            "two-fields harness, not a real site measurement"
        ),
        "range_missing": {
            "reason": "NOT_AVAILABLE",
            "detail": "PLACEHOLDER synthetic harness value; no measured range",
        },
    },
)

EXPECTED_ROTATION_B_MISSING_PARAMS: Final[frozenset[str]] = frozenset(
    {
        "fao56_stage_length_initial/crop=wheat",
        "fao56_stage_length_development/crop=wheat",
        "fao56_stage_length_mid/crop=wheat",
        "fao56_stage_length_late/crop=wheat",
        "fao56_stage_length_initial/crop=maize",
        "fao56_stage_length_development/crop=maize",
        "fao56_stage_length_mid/crop=maize",
        "fao56_stage_length_late/crop=maize",
        "surface_residue_cover/crop=wheat,management=no_crop",
        "surface_residue_cover/crop=maize,management=no_crop",
    }
)

_VALUE_FIELDS: Final[tuple[str, ...]] = (
    "indicator",
    "direction",
    "value",
    "unit",
    "range",
    "range_missing",
    "missing",
    "provenance",
    "source",
    "assumption",
)


@dataclass(frozen=True)
class PhaseRunResult:
    """Outputs of EP2 -> EP1, EP3, EP4 for one rotation and starting phase."""

    rotation_id: str
    phase_index: int
    phase_label: str
    calendar: RotationCalendar
    soil_loss: SoilLossResults
    water_deficit_exposure: tuple[WaterDeficitExposure, ...]
    residue_ledger: ResidueLedger


@dataclass(frozen=True)
class FieldPlanResult:
    """Complete deterministic plan run on one demonstration field."""

    field_id: str
    soil_slope: SiteSoilSlope
    climate: SiteClimate
    et0: Mapping[dt.date, float | Missing]
    phases_by_rotation: Mapping[str, tuple[PhaseRunResult, ...]]
    results_table: ResultsTable
    water_series: Mapping[tuple[str, str, int], tuple[WaterDay, ...]]
    decision_comparison: tuple[ComparisonItem, ...]
    water_comparison: tuple[WaterComparisonItem, ...]


@dataclass(frozen=True)
class TwoFieldsPlanResult:
    """Combined deterministic plan run across both demonstration fields."""

    rotations: tuple[RotationDefinition, ...]
    parameters: Mapping[str, Mapping[str, Any]]
    gentle: FieldPlanResult
    steep: FieldPlanResult


def _placeholder_value(
    *,
    value: float,
    unit: str,
    description: str,
    quantity: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "value": value,
        "unit": unit,
        "provenance": "DECLARED",
        "source": (
            f"PLACEHOLDER: synthetic {description} for D128 two-fields harness, "
            "not a real measurement"
        ),
        "range_missing": {
            "reason": "NOT_AVAILABLE",
            "detail": "PLACEHOLDER synthetic value; no uncertainty range",
        },
    }
    if quantity is not None:
        payload["quantity"] = quantity
    return payload


def build_demo_field(
    *,
    field_id: str,
    slope_length_m: float,
    slope_steepness_percent: float,
    rusle_k_factor: float = DEFAULT_PLACEHOLDER_K_FACTOR,
    case_id: str = DEFAULT_CASE_ID,
    shared_hydraulic_properties: Sequence[
        Mapping[str, Any]
    ] = DEFAULT_SHARED_HYDRAULIC_PROPERTIES,
) -> SiteSoilSlope:
    """Build one synthetic PLACEHOLDER ``SiteSoilSlope`` demonstration field."""
    soil_properties: list[dict[str, Any]] = [
        _placeholder_value(
            quantity="rusle_k_factor",
            value=rusle_k_factor,
            unit="t ha h ha-1 MJ-1 mm-1",
            description=f"RUSLE K factor for {field_id}",
        ),
        *[dict(prop) for prop in shared_hydraulic_properties],
    ]
    return SiteSoilSlope.model_validate(
        {
            "contract": "site_data_soil_slope",
            "example_data": True,
            "case_id": case_id,
            "field_id": field_id,
            "slope_length": _placeholder_value(
                value=slope_length_m,
                unit="m",
                description=f"slope length for {field_id}",
            ),
            "slope_steepness": _placeholder_value(
                value=slope_steepness_percent,
                unit="percent",
                description=f"slope steepness for {field_id}",
            ),
            "soil_properties": soil_properties,
        }
    )


def build_demo_fields(
    *,
    case_id: str = DEFAULT_CASE_ID,
    gentle_slope_length_m: float = DEFAULT_GENTLE_SLOPE_LENGTH_M,
    gentle_slope_steepness_percent: float = DEFAULT_GENTLE_SLOPE_STEEPNESS_PERCENT,
    steep_slope_length_m: float = DEFAULT_STEEP_SLOPE_LENGTH_M,
    steep_slope_steepness_percent: float = DEFAULT_STEEP_SLOPE_STEEPNESS_PERCENT,
    rusle_k_factor: float = DEFAULT_PLACEHOLDER_K_FACTOR,
    shared_hydraulic_properties: Sequence[
        Mapping[str, Any]
    ] = DEFAULT_SHARED_HYDRAULIC_PROPERTIES,
) -> tuple[SiteSoilSlope, SiteSoilSlope]:
    """Build the gentle and steep synthetic PLACEHOLDER demonstration fields."""
    gentle = build_demo_field(
        field_id=FIELD_DEMO_GENTLE,
        slope_length_m=gentle_slope_length_m,
        slope_steepness_percent=gentle_slope_steepness_percent,
        rusle_k_factor=rusle_k_factor,
        case_id=case_id,
        shared_hydraulic_properties=shared_hydraulic_properties,
    )
    steep = build_demo_field(
        field_id=FIELD_DEMO_STEEP,
        slope_length_m=steep_slope_length_m,
        slope_steepness_percent=steep_slope_steepness_percent,
        rusle_k_factor=rusle_k_factor,
        case_id=case_id,
        shared_hydraulic_properties=shared_hydraulic_properties,
    )
    return gentle, steep


def build_placeholder_climate(
    *,
    case_id: str = DEFAULT_CASE_ID,
    field_id: str,
    start: dt.date = CLIMATE_START,
    end: dt.date = CLIMATE_END,
) -> SiteClimate:
    """Build a deterministic PLACEHOLDER daily ``SiteClimate`` series."""
    if end < start:
        raise ValueError(f"end date {end} precedes start date {start}")

    days = [
        start + dt.timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]

    def make_series(
        quantity: str, unit: str, values: list[float]
    ) -> DailySeries:
        return DailySeries(
            quantity=quantity,
            unit=unit,
            provenance="DECLARED",
            source=(
                "PLACEHOLDER: synthetic deterministic climate series for D128 "
                "two-fields harness, not weather observations"
            ),
            range_missing=InputMissing(
                reason="NOT_AVAILABLE",
                detail="PLACEHOLDER synthetic climate series; no uncertainty range",
            ),
            time_zone="UTC",
            start_date=start,
            end_date=end,
            days=[
                DailyValue(date=day, value=val)
                for day, val in zip(days, values, strict=True)
            ],
        )

    temp_min_vals: list[float] = []
    temp_max_vals: list[float] = []
    dew_point_vals: list[float] = []
    precip_vals: list[float] = []
    rad_vals: list[float] = []
    rh_min_vals: list[float] = []
    wind_vals: list[float] = []

    for idx, day in enumerate(days):
        day_of_year = (day - dt.date(day.year, 1, 1)).days
        angle = 2.0 * math.pi * (day_of_year - 15) / 365.0
        t_mean = 16.5 + 6.5 * math.sin(angle)
        t_min = round(t_mean - 5.0, 4)
        temp_min_vals.append(t_min)
        temp_max_vals.append(round(t_mean + 5.0, 4))
        dew_point_vals.append(round(t_min - 1.5, 4))
        rad_vals.append(round(max(6.0, 16.0 + 8.0 * math.sin(angle)), 4))
        precip_vals.append(14.0 if (idx % 5 == 0) else 0.0)
        rh_min_vals.append(48.0)
        wind_vals.append(2.4)

    return SiteClimate(
        contract="site_data_climate",
        example_data=True,
        case_id=case_id,
        field_id=field_id,
        point=ClimatePoint.model_validate(
            {
                "latitude": _placeholder_value(
                    value=-34.34,
                    unit="degree",
                    description=f"site latitude for {field_id}",
                ),
                "longitude": _placeholder_value(
                    value=-57.69,
                    unit="degree",
                    description=f"site longitude for {field_id}",
                ),
                "elevation": _placeholder_value(
                    value=81.0,
                    unit="m",
                    description=f"site elevation for {field_id}",
                ),
            }
        ),
        daily_series=[
            make_series("air_temperature_max_2m", "degC", temp_max_vals),
            make_series("air_temperature_min_2m", "degC", temp_min_vals),
            make_series("dew_point_temperature_2m", "degC", dew_point_vals),
            make_series("precipitation", "mm day-1", precip_vals),
            make_series("solar_radiation", "MJ m-2 day-1", rad_vals),
            make_series("minimum_relative_humidity", "percent", rh_min_vals),
            make_series("wind_speed_2m", "m s-1", wind_vals),
        ],
        monthly_series=[],
    )


def _indicator_fields(item: IndicatorValue) -> dict[str, Any]:
    return {name: getattr(item, name) for name in _VALUE_FIELDS}


def _phase_rows(
    phase_run: PhaseRunResult,
    *,
    covered_years: frozenset[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in phase_run.soil_loss.annual:
        if item.ag_year not in covered_years:
            continue
        rows.append(
            {
                "rotation_id": phase_run.rotation_id,
                "time_basis": "ag_year",
                "ag_year": item.ag_year,
                **_indicator_fields(item),
            }
        )
    for item in phase_run.water_deficit_exposure:
        if item.ag_year not in covered_years:
            continue
        rows.append(
            {
                "rotation_id": phase_run.rotation_id,
                "time_basis": item.time_basis,
                "ag_year": item.ag_year,
                **_indicator_fields(item),
            }
        )
    return rows


def _daily_precipitation(climate: SiteClimate) -> dict[dt.date, float | Missing]:
    for series in climate.daily_series:
        if series.quantity == PRECIPITATION:
            out: dict[dt.date, float | Missing] = {}
            for dv in series.days:
                if dv.missing is not None:
                    out[dv.date] = dv.missing
                elif dv.value is not None:
                    out[dv.date] = dv.value
            return out
    raise ValueError(f"climate is missing {PRECIPITATION!r} series")


def _build_water_day_series(
    *,
    calendar: RotationCalendar,
    climate: SiteClimate,
    et0: Mapping[dt.date, float | Missing],
    parameters: Mapping[str, Mapping[str, Any]],
    covered_years: frozenset[int],
) -> tuple[WaterDay, ...]:
    """Build daily ``WaterDay`` inputs matching EP3 demand over covered years."""
    precip_by_day = _daily_precipitation(climate)
    if not precip_by_day:
        return ()

    record_start = min(precip_by_day)
    record_end = max(precip_by_day)
    over = live_crop_over_record(
        calendar, record_start, record_end, parameters=dict(parameters)
    )
    catalogue = Catalogue(dict(parameters))
    start_month = calendar.ag_year_start.month

    days: list[WaterDay] = []
    for offset in range((record_end - record_start).days + 1):
        day = record_start + dt.timedelta(days=offset)
        if _ag_year_of(day, start_month) not in covered_years:
            continue

        precip = precip_by_day.get(day)
        if precip is None:
            precip = Missing(
                reason="MISSING_INPUT",
                detail=f"{DAILY_INPUTS}/{PRECIPITATION} has no value on {day.isoformat()}",
            )

        comp = over.component(day)
        if isinstance(comp, Missing):
            demand: float | Missing = comp
        elif comp is None:
            demand = Missing(
                reason=NO_CROP_ON_THE_DAY,
                detail="no living crop on the day",
            )
        else:
            live = over.live_days(comp, day)
            if isinstance(live, Missing):
                demand = live
            elif not live.is_live(day):
                demand = Missing(
                    reason=NO_CROP_ON_THE_DAY,
                    detail="no living crop on the day",
                )
            else:
                stage_day = live.stages[day]
                kcb = by_stage(
                    stage_day,
                    catalogue.value(
                        BASAL_CROP_COEFFICIENT,
                        ((CROP_KEY, comp.crop_id), (STAGE_KEY, STAGES[0])),
                        day,
                    ),
                    catalogue.value(
                        BASAL_CROP_COEFFICIENT,
                        ((CROP_KEY, comp.crop_id), (STAGE_KEY, STAGES[1])),
                        day,
                    ),
                    catalogue.value(
                        BASAL_CROP_COEFFICIENT,
                        ((CROP_KEY, comp.crop_id), (STAGE_KEY, STAGES[2])),
                        day,
                    ),
                )
                et0_day = et0.get(day)
                if isinstance(kcb, Missing):
                    demand = kcb
                elif isinstance(et0_day, Missing):
                    demand = et0_day
                elif et0_day is None:
                    demand = Missing(
                        reason="MISSING_INPUT",
                        detail=f"ET0 has no value on {day.isoformat()}",
                    )
                else:
                    demand = kcb * et0_day

        days.append(
            WaterDay(
                date=day,
                precipitation=precip,
                transpiration_demanded=demand,
            )
        )
    return tuple(days)


def run_field_plan(
    *,
    rotations: Sequence[RotationDefinition],
    soil_slope: SiteSoilSlope,
    climate: SiteClimate,
    parameters: Mapping[str, Mapping[str, Any]],
    covered_ag_years: Sequence[int] = FULL_AG_YEARS,
) -> FieldPlanResult:
    """Run EP2 -> EP1, EP3, EP4, ET0, [D0], and [W0] on one demonstration field."""
    if len(rotations) < 2:
        raise ValueError("at least two rotations are required for decision pairing")
    if soil_slope.case_id != climate.case_id or soil_slope.field_id != climate.field_id:
        raise ValueError(
            "soil_slope and climate must share case_id and field_id"
        )

    param_dict = dict(parameters)
    covered_years_set = frozenset(covered_ag_years)
    et0 = daily_reference_evapotranspiration(climate, parameters=param_dict)

    phases_by_rotation: dict[str, tuple[PhaseRunResult, ...]] = {}
    phase_water_series: dict[tuple[str, str], tuple[WaterDay, ...]] = {}
    ordered_phase_lists: list[tuple[PhaseRunResult, ...]] = []

    for rotation in rotations:
        field_rotation = rotation.model_copy(
            update={
                "case_id": soil_slope.case_id,
                "field_id": soil_slope.field_id,
            }
        )
        base_calendar = build_rotation_calendar(field_rotation)
        phases = list_phases(base_calendar)
        phase_results: list[PhaseRunResult] = []
        for phase_idx in phases:
            phased_cal = phase_calendar(base_calendar, phase_idx)
            phase_label = f"phase_{phase_idx + 1}"
            soil_loss = compute_soil_loss(
                phased_cal, climate, soil_slope, parameters=param_dict
            )
            water_exp = tuple(
                compute_water_deficit_exposure(
                    phased_cal, climate, soil_slope, parameters=param_dict
                )
            )
            residue = build_residue_ledger(
                field_rotation, phased_cal, climate, parameters=param_dict
            )
            phase_run = PhaseRunResult(
                rotation_id=rotation.rotation_id,
                phase_index=phase_idx,
                phase_label=phase_label,
                calendar=phased_cal,
                soil_loss=soil_loss,
                water_deficit_exposure=water_exp,
                residue_ledger=residue,
            )
            phase_results.append(phase_run)
            phase_water_series[(rotation.rotation_id, phase_label)] = (
                _build_water_day_series(
                    calendar=phased_cal,
                    climate=climate,
                    et0=et0,
                    parameters=param_dict,
                    covered_years=covered_years_set,
                )
            )

        tuple_results = tuple(phase_results)
        phases_by_rotation[rotation.rotation_id] = tuple_results
        ordered_phase_lists.append(tuple_results)

    table_rows: list[ResultsTableRow] = []
    water_series: dict[tuple[str, str, int], tuple[WaterDay, ...]] = {}

    for combo in itertools.product(*ordered_phase_lists):
        scenario_id = SCENARIO_SEPARATOR.join(pr.phase_label for pr in combo)
        for pr in combo:
            for row_dict in _phase_rows(pr, covered_years=covered_years_set):
                table_rows.append(
                    ResultsTableRow(**row_dict, scenario_id=scenario_id)
                )
            daily_series = phase_water_series[(pr.rotation_id, pr.phase_label)]
            start_month = pr.calendar.ag_year_start.month
            by_year: dict[int, list[WaterDay]] = {}
            for water_day in daily_series:
                ag_year = _ag_year_of(water_day.date, start_month)
                by_year.setdefault(ag_year, []).append(water_day)
            for ag_year, year_days in by_year.items():
                water_series[(pr.rotation_id, scenario_id, ag_year)] = tuple(
                    year_days
                )

    results_table = ResultsTable(
        case_id=soil_slope.case_id,
        field_id=soil_slope.field_id,
        rows=table_rows,
    )
    decision_comparison = compare_with_decision(results_table)
    water_comparison = compare_with_full_indicator(water_series, results_table)

    return FieldPlanResult(
        field_id=soil_slope.field_id,
        soil_slope=soil_slope,
        climate=climate,
        et0=et0,
        phases_by_rotation=phases_by_rotation,
        results_table=results_table,
        water_series=water_series,
        decision_comparison=decision_comparison,
        water_comparison=water_comparison,
    )


def run_two_fields_plan(
    *,
    rotations: Sequence[RotationDefinition],
    parameters: Mapping[str, Mapping[str, Any]],
    gentle_field: SiteSoilSlope | None = None,
    steep_field: SiteSoilSlope | None = None,
    gentle_climate: SiteClimate | None = None,
    steep_climate: SiteClimate | None = None,
    covered_ag_years: Sequence[int] = FULL_AG_YEARS,
) -> TwoFieldsPlanResult:
    """Run the D128 plan deterministically across both demonstration fields."""
    if gentle_field is None or steep_field is None:
        default_gentle, default_steep = build_demo_fields()
        gentle_field = gentle_field or default_gentle
        steep_field = steep_field or default_steep

    if gentle_climate is None:
        gentle_climate = build_placeholder_climate(
            case_id=gentle_field.case_id,
            field_id=gentle_field.field_id,
        )
    if steep_climate is None:
        steep_climate = build_placeholder_climate(
            case_id=steep_field.case_id,
            field_id=steep_field.field_id,
        )

    gentle_result = run_field_plan(
        rotations=rotations,
        soil_slope=gentle_field,
        climate=gentle_climate,
        parameters=parameters,
        covered_ag_years=covered_ag_years,
    )
    steep_result = run_field_plan(
        rotations=rotations,
        soil_slope=steep_field,
        climate=steep_climate,
        parameters=parameters,
        covered_ag_years=covered_ag_years,
    )
    return TwoFieldsPlanResult(
        rotations=tuple(rotations),
        parameters=parameters,
        gentle=gentle_result,
        steep=steep_result,
    )


def load_d128_rotations(
    path: Path = DEFAULT_ROTATIONS_PATH,
) -> tuple[RotationDefinition, ...]:
    """Load and validate the D128 demonstration rotations JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload["rotations"] if isinstance(payload, dict) else payload
    return tuple(RotationDefinition.model_validate(item) for item in raw_items)


def load_shipped_catalogue(
    records_dir: Path = DEFAULT_RECORDS_DIR,
) -> dict[str, dict[str, Any]]:
    """Load the shipped parameter catalogue and assert zero validation errors."""
    records, load_errors = load_folder(records_dir)
    if load_errors:
        raise ValueError(
            f"failed to load parameter records from {records_dir}: {load_errors}"
        )
    check_errors = check_catalogue(records)
    if check_errors:
        raise ValueError(
            f"invalid parameter catalogue in {records_dir}: {check_errors}"
        )
    return records


def run_shipped_d128_fields_plan(
    *,
    rotations_path: Path = DEFAULT_ROTATIONS_PATH,
    records_dir: Path = DEFAULT_RECORDS_DIR,
) -> TwoFieldsPlanResult:
    """Convenience runner loading shipped D128 rotations and 132 param records."""
    rotations = load_d128_rotations(rotations_path)
    parameters = load_shipped_catalogue(records_dir)
    return run_two_fields_plan(rotations=rotations, parameters=parameters)
