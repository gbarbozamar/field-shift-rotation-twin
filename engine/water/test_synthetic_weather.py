"""Tests for ``engine/water/synthetic_weather.py`` (Frontier Unit F-08).

Covers deterministic seeded Markov calibration & simulation, conditional
multi-variable empirical resampling, summary diagnostics (``wet_spell_count``,
``annual_precip_distribution``), Rev13 Guard 1 (no zero-filling of missing
historical days; clean ``MISSING_INPUT`` / ``NO_COVERAGE`` failures), Rev13
Guard 2 (``provenance="SIMULATED"``, ``horizon="synthetic"``,
``can_replace_observed=False``, and refusal of mixing synthetic records into
``OBSERVED`` normative calculations), ``SiteClimate`` integration, G1 purity /
immutability, G5 caller validation, and AST hygiene (zero hardcoded climate
parameters or impure imports).

Every threshold, date, and weather value in this file is synthetic PLACEHOLDER
test data, plainly not real.
"""

from __future__ import annotations

import ast
import calendar
import copy
import datetime as dt
import math
import random
import statistics
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import (
    ClimatePoint,
    DailySeries,
    DailyValue,
    SiteClimate,
)
from contracts.results.models import Missing
from engine.water import synthetic_weather
from engine.water.synthetic_weather import (
    ACCEPTED_CLIMATE_UNITS,
    PRECIPITATION,
    RELATIVE_HUMIDITY_2M,
    SOLAR_RADIATION,
    SYNTHETIC_CAN_REPLACE_OBSERVED,
    SYNTHETIC_HORIZON,
    SYNTHETIC_PROVENANCE,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WIND_SPEED_2M,
    AnnualPrecipDistribution,
    DailyWeatherVector,
    MonthlyMarkovParameters,
    SyntheticWeatherConfig,
    SyntheticWeatherDiagnostics,
    SyntheticWeatherSeries,
    daily_vectors_from_site_climate,
    fit_monthly_markov_parameters,
    generate_synthetic_weather,
    require_observed_for_normative,
)

# PLACEHOLDER test configuration constants (synthetic only, not real climate values).
PLACEHOLDER_WET_THRESHOLD_MM = 1.5  # PLACEHOLDER
PLACEHOLDER_SEED = 42  # PLACEHOLDER
PLACEHOLDER_AG_START_JULY = 7  # PLACEHOLDER


def _make_vector(
    day_date: dt.date,
    *,
    is_wet: bool,
    precip_override: float | Missing | None = None,
) -> DailyWeatherVector:
    """Create a distinct deterministic PLACEHOLDER weather vector tagged by month & state."""
    month_offset = float(day_date.month)
    day_offset = float(day_date.day) * 0.01
    if precip_override is not None:
        precip: float | Missing = precip_override
    elif is_wet:
        precip = PLACEHOLDER_WET_THRESHOLD_MM + month_offset + day_offset
    else:
        precip = 0.0

    if is_wet:
        return DailyWeatherVector(
            date=day_date,
            precip_mm=precip,
            tmax_c=20.0 + month_offset + day_offset,
            tmin_c=10.0 + month_offset + day_offset,
            radiation=12.0 + month_offset * 0.5 + day_offset,
            wind=4.0 + month_offset * 0.1 + day_offset,
            rh=85.0 + month_offset * 0.2 + day_offset,
        )
    return DailyWeatherVector(
        date=day_date,
        precip_mm=precip,
        tmax_c=28.0 + month_offset + day_offset,
        tmin_c=14.0 + month_offset + day_offset,
        radiation=24.0 + month_offset * 0.5 + day_offset,
        wind=2.0 + month_offset * 0.1 + day_offset,
        rh=45.0 + month_offset * 0.2 + day_offset,
    )


def _default_wet_predicate(day_date: dt.date) -> bool:
    return (day_date.day + day_date.month) % 3 == 0


def _build_multi_year_history(
    years: tuple[int, ...],
    *,
    wet_predicate=None,
) -> list[DailyWeatherVector]:
    """Build complete multi-year daily history with caller-supplied wet pattern."""
    if wet_predicate is None:
        wet_predicate = _default_wet_predicate
    vectors: list[DailyWeatherVector] = []
    for year in years:
        for month in range(1, 13):
            _, days_in_month = calendar.monthrange(year, month)
            for day_num in range(1, days_in_month + 1):
                cur = dt.date(year, month, day_num)
                vectors.append(_make_vector(cur, is_wet=bool(wet_predicate(cur))))
    return vectors


def _point(*, provenance: str = "OBSERVED") -> ClimatePoint:
    range_missing = InputsMissing(
        reason="NOT_AVAILABLE",
        detail="PLACEHOLDER: synthetic test point has no range",
    )
    return ClimatePoint(
        latitude=Value(
            value=1.11,
            unit="degree",
            provenance=provenance,
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        longitude=Value(
            value=2.22,
            unit="degree",
            provenance=provenance,
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        elevation=Value(
            value=3.33,
            unit="m",
            provenance=provenance,
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
    )


def _daily_series_from_values(
    quantity: str,
    start: dt.date,
    values: list[float | InputsMissing],
    *,
    unit: str,
    provenance: str = "OBSERVED",
    time_zone: str = "UTC",
) -> DailySeries:
    end = start + dt.timedelta(days=len(values) - 1)
    days = []
    for offset, item in enumerate(values):
        cur = start + dt.timedelta(days=offset)
        if isinstance(item, InputsMissing):
            days.append(DailyValue(date=cur, value=None, missing=item))
        else:
            days.append(DailyValue(date=cur, value=item, missing=None))
    has_present = any(not isinstance(item, InputsMissing) for item in values)
    return DailySeries(
        quantity=quantity,
        unit=unit,
        time_zone=time_zone,
        start_date=start,
        end_date=end,
        provenance=provenance if has_present else None,
        source="PLACEHOLDER synthetic series" if has_present else None,
        range_missing=(
            InputsMissing(
                reason="NOT_AVAILABLE",
                detail="PLACEHOLDER synthetic series has no range",
            )
            if has_present
            else None
        ),
        days=days,
    )


def _site_climate_from_vectors(
    vectors: list[DailyWeatherVector],
    *,
    provenance: str = "OBSERVED",
    unit_overrides: dict[str, str] | None = None,
    tz_overrides: dict[str, str] | None = None,
    omit_quantities: set[str] | None = None,
) -> SiteClimate:
    unit_overrides = unit_overrides or {}
    tz_overrides = tz_overrides or {}
    omit_quantities = omit_quantities or set()
    start = vectors[0].date
    mapping = [
        ("precip_mm", PRECIPITATION),
        ("tmax_c", TEMPERATURE_MAX),
        ("tmin_c", TEMPERATURE_MIN),
        ("radiation", SOLAR_RADIATION),
        ("wind", WIND_SPEED_2M),
        ("rh", RELATIVE_HUMIDITY_2M),
    ]
    daily_series = []
    for field_name, quantity in mapping:
        if quantity in omit_quantities:
            continue
        vals: list[float | InputsMissing] = []
        for vec in vectors:
            val = getattr(vec, field_name)
            if isinstance(val, Missing):
                vals.append(InputsMissing(reason=val.reason, detail=val.detail))
            else:
                vals.append(val)
        daily_series.append(
            _daily_series_from_values(
                quantity,
                start,
                vals,
                unit=unit_overrides.get(quantity, ACCEPTED_CLIMATE_UNITS[quantity]),
                provenance=provenance,
                time_zone=tz_overrides.get(quantity, "UTC"),
            )
        )
    return SiteClimate(
        contract="site_data_climate",
        example_data=True,
        case_id="PLACEHOLDER-case",
        field_id="PLACEHOLDER-field",
        point=_point(provenance=provenance),
        daily_series=daily_series,
        monthly_series=[],
    )


# --- AST hygiene, frozen dataclasses & G1 purity ----------------------------


def test_module_contains_zero_hardcoded_climate_parameters_or_impure_imports():
    source_path = Path(synthetic_weather.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    numeric_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert numeric_constants <= {0, 1}

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    forbidden_impure = {
        "os",
        "pathlib",
        "time",
        "urllib",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "json",
        "numpy",
    }
    assert imported_modules.isdisjoint(forbidden_impure)

    # Ensure module-level global PRNG functions are never called directly.
    forbidden_random_calls = {"seed", "random", "choice", "randint", "randrange"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "random"
        ):
            assert node.func.attr == "Random"
            assert node.func.attr not in forbidden_random_calls


def test_dataclasses_are_frozen():
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=1,
        n_synthetic_years=1,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    vec = _make_vector(dt.date(2001, 1, 1), is_wet=True)
    params = MonthlyMarkovParameters(
        month=1,
        p_wet_given_wet=0.5,
        p_wet_given_dry=0.2,
        p_wet_unconditional=0.3,
        wet_pool_size=10,
        dry_pool_size=21,
        valid_years_observed=1,
        valid_day_count=31,
        ww_transitions=5,
        wd_transitions=5,
        dw_transitions=4,
        dd_transitions=16,
    )
    dist = AnnualPrecipDistribution(
        annual_totals_mm=(100.0,),
        mean_mm=100.0,
        std_mm=0.0,
        min_mm=100.0,
        median_mm=100.0,
        max_mm=100.0,
    )
    diag = SyntheticWeatherDiagnostics(
        wet_spell_count=1,
        wet_day_count=1,
        dry_day_count=0,
        annual_precip_distribution=dist,
    )
    series = SyntheticWeatherSeries(
        config=cfg,
        monthly_parameters=(params,),
        days=(vec,),
        diagnostics=diag,
    )

    for obj, attr in (
        (cfg, "seed"),
        (vec, "precip_mm"),
        (params, "p_wet_given_wet"),
        (dist, "mean_mm"),
        (diag, "wet_spell_count"),
        (series, "provenance"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, attr, 999)


def test_pure_deterministic_seeded_and_no_input_or_global_rng_mutation():
    history = list(reversed(_build_multi_year_history((2001, 2002))))
    history_snapshot = copy.deepcopy(history)
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=2,
        n_synthetic_years=3,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=PLACEHOLDER_AG_START_JULY,
    )

    random.seed(999)
    rng_state_before = random.getstate()

    first = generate_synthetic_weather(history, config=cfg)
    second = generate_synthetic_weather(history, config=cfg)

    rng_state_after = random.getstate()
    assert rng_state_after == rng_state_before
    assert history == history_snapshot
    assert first == second

    cfg_other_seed = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=2,
        n_synthetic_years=3,
        seed=PLACEHOLDER_SEED + 1,
        ag_year_start_month=PLACEHOLDER_AG_START_JULY,
    )
    other = generate_synthetic_weather(history, config=cfg_other_seed)
    assert first.monthly_parameters == other.monthly_parameters
    assert first.days != other.days


# --- Analytical Markov transition fitting & empirical resampling -------------


def test_analytical_transition_probabilities_and_threshold_boundary():
    # Month 1 (Jan, 31 days):
    # - Day 1..10: W (at exact boundary == wet_day_threshold_mm -> kills >= vs > mutant)
    # - Day 11..20: D (just below wet_day_threshold_mm)
    # - Day 21..31: W
    # Transitions in Jan (30 consecutive within-month pairs):
    #   W->W: (1..9)->(2..10) [9] + (21..30)->(22..31) [10] = 19
    #   W->D: 10->11 [1]
    #   D->W: 20->21 [1]
    #   D->D: (11..19)->(12..20) [9]
    # So P(W|W) = 19/20 = 0.95, P(W|D) = 1/10 = 0.10.
    # Month 2 (Feb 2001, 28 days): strictly alternating W, D, W, D...
    #   14 W, 14 D -> 14 W->D, 13 D->W -> P(W|W)=0.0, P(W|D)=1.0.
    # Month 3 (Mar): all W -> P(W|W)=1.0, P(W|D)=Missing(NOT_COMPUTABLE).
    # Month 4 (Apr): all D -> P(W|W)=Missing(NOT_COMPUTABLE), P(W|D)=0.0.
    history: list[DailyWeatherVector] = []
    for month in range(1, 13):
        _, dim = calendar.monthrange(2001, month)
        for day_num in range(1, dim + 1):
            d = dt.date(2001, month, day_num)
            if month == 1:
                if day_num <= 10 or day_num >= 21:
                    history.append(
                        _make_vector(
                            d, is_wet=True, precip_override=PLACEHOLDER_WET_THRESHOLD_MM
                        )
                    )
                else:
                    history.append(
                        _make_vector(
                            d,
                            is_wet=False,
                            precip_override=PLACEHOLDER_WET_THRESHOLD_MM - 0.01,
                        )
                    )
            elif month == 2:
                history.append(_make_vector(d, is_wet=(day_num % 2 == 1)))
            elif month == 3:
                history.append(_make_vector(d, is_wet=True))
            elif month == 4:
                history.append(_make_vector(d, is_wet=False))
            else:
                history.append(_make_vector(d, is_wet=(day_num % 2 == 0)))

    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=1,
        n_synthetic_years=2,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    fitted = fit_monthly_markov_parameters(history, config=cfg)
    assert len(fitted) == 12

    jan = fitted[0]
    assert jan.month == 1
    assert jan.ww_transitions == 19
    assert jan.wd_transitions == 1
    assert jan.dw_transitions == 1
    assert jan.dd_transitions == 9
    assert jan.p_wet_given_wet == pytest.approx(19 / 20)
    assert jan.p_wet_given_dry == pytest.approx(1 / 10)
    assert jan.p_wet_unconditional == pytest.approx(21 / 31)
    assert jan.wet_pool_size == 21
    assert jan.dry_pool_size == 10
    assert jan.coverage_missing is None

    feb = fitted[1]
    assert feb.ww_transitions == 0
    assert feb.wd_transitions == 14
    assert feb.dw_transitions == 13
    assert feb.dd_transitions == 0
    assert feb.p_wet_given_wet == pytest.approx(0.0)
    assert feb.p_wet_given_dry == pytest.approx(1.0)

    mar = fitted[2]
    assert mar.p_wet_given_wet == pytest.approx(1.0)
    assert isinstance(mar.p_wet_given_dry, Missing)
    assert mar.p_wet_given_dry.reason == "NOT_COMPUTABLE"

    apr = fitted[3]
    assert isinstance(apr.p_wet_given_wet, Missing)
    assert apr.p_wet_given_wet.reason == "NOT_COMPUTABLE"
    assert apr.p_wet_given_dry == pytest.approx(0.0)

    # Simulation across all-wet Mar -> all-dry Apr -> mixed May runs cleanly!
    sim = generate_synthetic_weather(history, config=cfg)
    assert not isinstance(sim.days, Missing)
    assert len(sim.days) == 365 + 365
    # Every March day must be wet, every April day must be dry.
    for day_vec in sim.days:
        assert not isinstance(day_vec.precip_mm, Missing)
        if day_vec.date.month == 3:
            assert day_vec.precip_mm >= PLACEHOLDER_WET_THRESHOLD_MM
        if day_vec.date.month == 4:
            assert day_vec.precip_mm < PLACEHOLDER_WET_THRESHOLD_MM


def test_multivariate_conditional_empirical_resampling_preserves_joint_vectors():
    history = _build_multi_year_history((2001, 2002, 2003))
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=3,
        n_synthetic_years=4,  # Includes leap year 0004 (Feb 29)
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=PLACEHOLDER_AG_START_JULY,
    )

    pools: dict[
        tuple[int, bool], set[tuple[float, float, float, float, float, float]]
    ] = {}
    for vec in history:
        assert not isinstance(vec.precip_mm, Missing)
        is_wet = vec.precip_mm >= cfg.wet_day_threshold_mm
        tuple_val = (
            vec.precip_mm,
            vec.tmax_c,
            vec.tmin_c,
            vec.radiation,
            vec.wind,
            vec.rh,
        )
        pools.setdefault((vec.date.month, is_wet), set()).add(tuple_val)

    sim = generate_synthetic_weather(history, config=cfg)
    assert not isinstance(sim.days, Missing)
    # 0001-07-01..0005-06-30 includes 0004-02-29 => 365 + 365 + 366 + 365 = 1461 days
    assert len(sim.days) == 1461
    assert any(d.date.month == 2 and d.date.day == 29 for d in sim.days)

    for day_vec in sim.days:
        assert not isinstance(day_vec.precip_mm, Missing)
        is_wet = day_vec.precip_mm >= cfg.wet_day_threshold_mm
        tuple_val = (
            day_vec.precip_mm,
            day_vec.tmax_c,
            day_vec.tmin_c,
            day_vec.radiation,
            day_vec.wind,
            day_vec.rh,
        )
        # Joint 6-tuple MUST belong identically to the matching (month, wet/dry) pool.
        assert tuple_val in pools[(day_vec.date.month, is_wet)]
        assert tuple_val not in pools[(day_vec.date.month, not is_wet)]


def test_diagnostics_wet_spell_count_and_annual_precip_distribution():
    # Construct deterministic all-wet Jan/Mar/May/Jul/Sep/Nov and all-dry even months
    # so transitions are deterministic regardless of seed!
    history = _build_multi_year_history(
        (2001, 2002),
        wet_predicate=lambda d: d.month % 2 == 1,
    )
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=2,
        n_synthetic_years=4,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=PLACEHOLDER_AG_START_JULY,
    )
    sim = generate_synthetic_weather(history, config=cfg)
    assert not isinstance(sim.days, Missing)
    assert not isinstance(sim.diagnostics, Missing)

    # Independently recompute wet_spell_count and ag-year precipitation totals.
    expected_spells = 0
    in_spell = False
    expected_wet = 0
    expected_dry = 0
    ag_totals: dict[int, list[float]] = {}
    for vec in sim.days:
        assert not isinstance(vec.precip_mm, Missing)
        wet = vec.precip_mm >= cfg.wet_day_threshold_mm
        if wet:
            expected_wet += 1
            if not in_spell:
                expected_spells += 1
                in_spell = True
        else:
            expected_dry += 1
            in_spell = False
        ag_year = (
            vec.date.year
            if vec.date.month >= cfg.ag_year_start_month
            else vec.date.year - 1
        )
        ag_totals.setdefault(ag_year, []).append(vec.precip_mm)

    ordered_totals = tuple(math.fsum(ag_totals[y]) for y in sorted(ag_totals))
    assert len(ordered_totals) == cfg.n_synthetic_years
    assert sim.diagnostics.wet_spell_count == expected_spells
    assert sim.diagnostics.wet_day_count == expected_wet
    assert sim.diagnostics.dry_day_count == expected_dry
    # 6 odd wet months per ag year -> 6 wet spells per ag year -> 24 spells total
    assert sim.diagnostics.wet_spell_count == 24

    dist = sim.diagnostics.annual_precip_distribution
    assert dist.annual_totals_mm == ordered_totals
    assert dist.mean_mm == pytest.approx(statistics.fmean(ordered_totals))
    assert dist.std_mm == pytest.approx(statistics.pstdev(ordered_totals))
    assert dist.min_mm == pytest.approx(min(ordered_totals))
    assert dist.median_mm == pytest.approx(statistics.median(ordered_totals))
    assert dist.max_mm == pytest.approx(max(ordered_totals))


# --- Rev13 Guard 1: No zero-filling & clean Missing coverage failure ----------


def test_rev13_guard1_missing_days_never_zero_filled_and_break_transitions():
    # 3 years of history (2001..2003), min_history_years=2.
    # In 2001-01, mark 2001-01-15 with Missing(reason="SOURCE_UNAVAILABLE") on precip_mm,
    # and make all other Jan days in 2001..2003 WET!
    # If missing day were filled as zero, dry_pool_size would be 1 and wd/dw would be 1!
    # Under Rev13 Guard 1, missing day is NEVER filled as zero:
    #   - valid_years_observed for Jan = 2 (2002 and 2003; >= min_history_years=2)
    #   - dry_pool_size == 0 (missing day did NOT enter dry_pool!)
    #   - valid_day_count == 30 + 31 + 31 = 92 (not 93)
    #   - ww_transitions == 13 (1..14) + 15 (16..31) + 30 (2002) + 30 (2003) = 88
    #   - wd_transitions == 0, dw_transitions == 0, dd_transitions == 0
    history = _build_multi_year_history(
        (2001, 2002, 2003),
        wet_predicate=lambda d: True,
    )
    patched: list[DailyWeatherVector] = []
    for vec in history:
        if vec.date == dt.date(2001, 1, 15):
            patched.append(
                _make_vector(
                    vec.date,
                    is_wet=True,
                    precip_override=Missing(
                        reason="SOURCE_UNAVAILABLE", detail="PLACEHOLDER outage"
                    ),
                )
            )
        else:
            patched.append(vec)

    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=2,
        n_synthetic_years=1,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    fitted = fit_monthly_markov_parameters(patched, config=cfg)
    jan = fitted[0]
    assert jan.coverage_missing is None
    assert jan.valid_years_observed == 2
    assert jan.valid_day_count == 92
    assert jan.dry_pool_size == 0
    assert jan.wet_pool_size == 92
    assert jan.ww_transitions == 88
    assert jan.wd_transitions == 0
    assert jan.dw_transitions == 0
    assert jan.dd_transitions == 0


def test_rev13_guard1_insufficient_valid_years_due_to_missing_input_fails_cleanly():
    # 2 years of history, min_history_years=2, with 1 missing tmax_c day in 2002-05
    # and 1 NaN radiation day in 2002-08.
    history = _build_multi_year_history((2001, 2002))
    patched: list[DailyWeatherVector] = []
    for vec in history:
        if vec.date == dt.date(2002, 5, 10):
            patched.append(
                DailyWeatherVector(
                    date=vec.date,
                    precip_mm=vec.precip_mm,
                    tmax_c=Missing(reason="SOURCE_UNAVAILABLE", detail="PLACEHOLDER"),
                    tmin_c=vec.tmin_c,
                    radiation=vec.radiation,
                    wind=vec.wind,
                    rh=vec.rh,
                )
            )
        elif vec.date == dt.date(2002, 8, 12):
            patched.append(
                DailyWeatherVector(
                    date=vec.date,
                    precip_mm=vec.precip_mm,
                    tmax_c=vec.tmax_c,
                    tmin_c=vec.tmin_c,
                    radiation=math.nan,
                    wind=vec.wind,
                    rh=vec.rh,
                )
            )
        else:
            patched.append(vec)

    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=2,
        n_synthetic_years=1,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    sim = generate_synthetic_weather(patched, config=cfg)
    assert sim.provenance == SYNTHETIC_PROVENANCE
    assert sim.horizon == SYNTHETIC_HORIZON
    assert sim.can_replace_observed is False

    may = sim.monthly_parameters[4]
    aug = sim.monthly_parameters[7]
    assert isinstance(may.coverage_missing, Missing)
    assert may.coverage_missing.reason == "MISSING_INPUT"
    assert isinstance(may.p_wet_given_wet, Missing)
    assert isinstance(aug.coverage_missing, Missing)
    assert aug.coverage_missing.reason == "MISSING_INPUT"

    assert isinstance(sim.days, Missing)
    assert sim.days.reason == "MISSING_INPUT"
    assert isinstance(sim.diagnostics, Missing)
    assert sim.diagnostics.reason == "MISSING_INPUT"


def test_rev13_guard1_insufficient_calendar_coverage_fails_with_no_coverage():
    # Empty history -> NO_COVERAGE
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=2,
        n_synthetic_years=1,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    empty_sim = generate_synthetic_weather([], config=cfg)
    assert isinstance(empty_sim.days, Missing)
    assert empty_sim.days.reason == "NO_COVERAGE"
    assert isinstance(empty_sim.diagnostics, Missing)
    assert empty_sim.diagnostics.reason == "NO_COVERAGE"

    # 1 year provided when min_history_years=2 -> NO_COVERAGE
    one_year = _build_multi_year_history((2001,))
    short_sim = generate_synthetic_weather(one_year, config=cfg)
    assert isinstance(short_sim.days, Missing)
    assert short_sim.days.reason == "NO_COVERAGE"

    # 2 years provided except 2002-02 missing a day -> Feb fails NO_COVERAGE
    two_years = [
        v
        for v in _build_multi_year_history((2001, 2002))
        if v.date != dt.date(2002, 2, 14)
    ]
    partial_sim = generate_synthetic_weather(two_years, config=cfg)
    feb = partial_sim.monthly_parameters[1]
    assert isinstance(feb.coverage_missing, Missing)
    assert feb.coverage_missing.reason == "NO_COVERAGE"
    assert isinstance(partial_sim.days, Missing)
    assert partial_sim.days.reason == "NO_COVERAGE"


# --- Rev13 Guard 2: Provenance tags & anti-mixing normative guard ------------


def test_rev13_guard2_provenance_horizon_and_can_replace_observed_enforced():
    history = _build_multi_year_history((2001,))
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=1,
        n_synthetic_years=1,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    sim = generate_synthetic_weather(history, config=cfg)
    assert sim.provenance == SYNTHETIC_PROVENANCE
    assert sim.horizon == SYNTHETIC_HORIZON
    assert sim.can_replace_observed is SYNTHETIC_CAN_REPLACE_OBSERVED

    with pytest.raises(ValueError, match="provenance"):
        SyntheticWeatherSeries(
            config=cfg,
            monthly_parameters=sim.monthly_parameters,
            days=sim.days,
            diagnostics=sim.diagnostics,
            provenance="OBSERVED",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="horizon"):
        SyntheticWeatherSeries(
            config=cfg,
            monthly_parameters=sim.monthly_parameters,
            days=sim.days,
            diagnostics=sim.diagnostics,
            horizon="historical",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="can_replace_observed"):
        SyntheticWeatherSeries(
            config=cfg,
            monthly_parameters=sim.monthly_parameters,
            days=sim.days,
            diagnostics=sim.diagnostics,
            can_replace_observed=True,  # type: ignore[arg-type]
        )


def test_rev13_guard2_normative_helper_refuses_synthetic_mixing():
    history = _build_multi_year_history((2001,))
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=1,
        n_synthetic_years=1,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    sim = generate_synthetic_weather(history, config=cfg)
    observed_climate = _site_climate_from_vectors(history, provenance="OBSERVED")
    simulated_climate = _site_climate_from_vectors(history, provenance="SIMULATED")

    # Pure OBSERVED records succeed cleanly.
    require_observed_for_normative(observed_climate)
    require_observed_for_normative(observed_climate.daily_series)

    # Any synthetic record (alone or mixed with OBSERVED) raises ValueError.
    with pytest.raises(ValueError, match="SIMULATED"):
        require_observed_for_normative(sim)
    with pytest.raises(ValueError, match="SIMULATED"):
        require_observed_for_normative(observed_climate, sim)
    with pytest.raises(ValueError, match="SIMULATED"):
        require_observed_for_normative([observed_climate, sim])
    with pytest.raises(ValueError, match="SIMULATED"):
        require_observed_for_normative(simulated_climate)
    with pytest.raises(ValueError, match="SIMULATED"):
        require_observed_for_normative(simulated_climate.daily_series[0])

    # Custom synthetic-marked duck-typed object is also refused.
    @dataclass(frozen=True)
    class _FakeSynthetic:
        provenance: str = "SIMULATED"
        horizon: str = "synthetic"
        can_replace_observed: bool = False

    with pytest.raises(ValueError, match="synthetic"):
        require_observed_for_normative(_FakeSynthetic())


# --- SiteClimate integration ------------------------------------------------


def test_site_climate_integration_and_guards():
    history = _build_multi_year_history((2001, 2002))
    obs_climate = _site_climate_from_vectors(history, provenance="OBSERVED")
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=2,
        n_synthetic_years=2,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    extracted = daily_vectors_from_site_climate(obs_climate)
    assert len(extracted) == len(history)

    sim_from_climate = generate_synthetic_weather(obs_climate, config=cfg)
    sim_from_vectors = generate_synthetic_weather(history, config=cfg)
    assert sim_from_climate == sim_from_vectors

    # Refuses SIMULATED SiteClimate as calibration history.
    sim_climate = _site_climate_from_vectors(history, provenance="SIMULATED")
    with pytest.raises(ValueError, match="SIMULATED"):
        generate_synthetic_weather(sim_climate, config=cfg)

    # Wrong unit -> MISSING_INPUT (never converts silently).
    bad_unit_climate = _site_climate_from_vectors(
        history, unit_overrides={PRECIPITATION: "cm day-1"}
    )
    bad_unit_sim = generate_synthetic_weather(bad_unit_climate, config=cfg)
    assert isinstance(bad_unit_sim.days, Missing)
    assert bad_unit_sim.days.reason == "MISSING_INPUT"

    # Omitted required series -> MISSING_INPUT.
    missing_rh_climate = _site_climate_from_vectors(
        history, omit_quantities={RELATIVE_HUMIDITY_2M}
    )
    missing_rh_sim = generate_synthetic_weather(missing_rh_climate, config=cfg)
    assert isinstance(missing_rh_sim.days, Missing)
    assert missing_rh_sim.days.reason == "MISSING_INPUT"

    # Mixed time zones -> fails cleanly (not computable / missing input).
    mixed_tz_climate = _site_climate_from_vectors(
        history, tz_overrides={WIND_SPEED_2M: "Etc/GMT+3"}
    )
    mixed_tz_sim = generate_synthetic_weather(mixed_tz_climate, config=cfg)
    assert isinstance(mixed_tz_sim.days, Missing)
    assert mixed_tz_sim.days.reason == "MISSING_INPUT"


# --- G5 caller TypeError & ValueError checks --------------------------------


@pytest.mark.parametrize("bad_thresh", [True, False, "1.5", None, []])
def test_config_wrong_types_raise_type_error(bad_thresh):
    with pytest.raises(TypeError, match="wet_day_threshold_mm"):
        SyntheticWeatherConfig(
            wet_day_threshold_mm=bad_thresh,  # type: ignore[arg-type]
            min_history_years=1,
            n_synthetic_years=1,
            seed=1,
            ag_year_start_month=1,
        )


@pytest.mark.parametrize("bad_int", [True, False, 1.5, "1", None])
def test_config_wrong_int_fields_raise_type_error(bad_int):
    with pytest.raises(TypeError, match="min_history_years"):
        SyntheticWeatherConfig(
            wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
            min_history_years=bad_int,  # type: ignore[arg-type]
            n_synthetic_years=1,
            seed=1,
            ag_year_start_month=1,
        )
    with pytest.raises(TypeError, match="n_synthetic_years"):
        SyntheticWeatherConfig(
            wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
            min_history_years=1,
            n_synthetic_years=bad_int,  # type: ignore[arg-type]
            seed=1,
            ag_year_start_month=1,
        )
    with pytest.raises(TypeError, match="seed"):
        SyntheticWeatherConfig(
            wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
            min_history_years=1,
            n_synthetic_years=1,
            seed=bad_int,  # type: ignore[arg-type]
            ag_year_start_month=1,
        )
    with pytest.raises(TypeError, match="ag_year_start_month"):
        SyntheticWeatherConfig(
            wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
            min_history_years=1,
            n_synthetic_years=1,
            seed=1,
            ag_year_start_month=bad_int,  # type: ignore[arg-type]
        )


def test_config_invalid_domain_values_raise_value_error():
    for bad_thresh in (0.0, -1.0, math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="wet_day_threshold_mm"):
            SyntheticWeatherConfig(
                wet_day_threshold_mm=bad_thresh,
                min_history_years=1,
                n_synthetic_years=1,
                seed=1,
                ag_year_start_month=1,
            )
    with pytest.raises(ValueError, match="min_history_years"):
        SyntheticWeatherConfig(
            wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
            min_history_years=0,
            n_synthetic_years=1,
            seed=1,
            ag_year_start_month=1,
        )
    with pytest.raises(ValueError, match="n_synthetic_years"):
        SyntheticWeatherConfig(
            wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
            min_history_years=1,
            n_synthetic_years=0,
            seed=1,
            ag_year_start_month=1,
        )
    for bad_month in (0, 13):
        with pytest.raises(ValueError, match="ag_year_start_month"):
            SyntheticWeatherConfig(
                wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
                min_history_years=1,
                n_synthetic_years=1,
                seed=1,
                ag_year_start_month=bad_month,
            )


def test_caller_validation_for_vectors_history_config_and_normative_helper():
    cfg = SyntheticWeatherConfig(
        wet_day_threshold_mm=PLACEHOLDER_WET_THRESHOLD_MM,
        min_history_years=1,
        n_synthetic_years=1,
        seed=PLACEHOLDER_SEED,
        ag_year_start_month=1,
    )
    with pytest.raises(TypeError, match="datetime.date"):
        DailyWeatherVector(
            date=dt.datetime(2001, 1, 1),  # type: ignore[arg-type]
            precip_mm=0.0,
            tmax_c=20.0,
            tmin_c=10.0,
            radiation=15.0,
            wind=2.0,
            rh=50.0,
        )
    with pytest.raises(TypeError, match="precip_mm"):
        DailyWeatherVector(
            date=dt.date(2001, 1, 1),
            precip_mm=True,  # type: ignore[arg-type]
            tmax_c=20.0,
            tmin_c=10.0,
            radiation=15.0,
            wind=2.0,
            rh=50.0,
        )

    for bad_history in (None, "history", b"bytes", {}, {1}, 123):
        with pytest.raises(TypeError, match="history"):
            generate_synthetic_weather(bad_history, config=cfg)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="DailyWeatherVector"):
        fit_monthly_markov_parameters(["bad"], config=cfg)  # type: ignore[list-item]

    with pytest.raises(TypeError, match="SyntheticWeatherConfig"):
        generate_synthetic_weather([], config="bad")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="SiteClimate"):
        daily_vectors_from_site_climate("not_a_climate")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="unsupported record type"):
        require_observed_for_normative("not_a_record")

    dup_day = _make_vector(dt.date(2001, 1, 1), is_wet=False)
    with pytest.raises(ValueError, match="duplicate"):
        generate_synthetic_weather([dup_day, dup_day], config=cfg)

    with pytest.raises(ValueError, match="start_year"):
        generate_synthetic_weather([], config=cfg, start_year=dt.MAXYEAR)
