"""Acceptance test of the intermediate quantities (engine/water/et0/equations.py).

Run with ``python -m pytest engine/water/et0/`` from the repository root.

The cases are PROPOSED (blueprint section 3.7) and are listed with the same
codes in engine/water/et0/README.md under "PROPOSED cases".

Every number in this file is a PLACEHOLDER: it is plainly not a constant of
the method, not a real input and not an expected value of the science. The
numbers are chosen so that each result can be checked by hand; the hand
computation is written next to each case. These cases test the structure of
each function (which operands it uses, and how), not the method.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.results.models import Missing
from engine.water.et0 import equations as eq
from engine.water.et0.constants import (
    AtmosphericPressureConstants,
    ClearSkyRadiationConstants,
    Et0Constants,
    ExtraterrestrialRadiationConstants,
    InverseRelativeDistanceConstants,
    NetLongwaveConstants,
    NetShortwaveConstants,
    PenmanMonteithConstants,
    PsychrometricConstants,
    SaturationVapourPressureConstants,
    SlopeConstants,
    SoilHeatFluxConstants,
    SolarDeclinationConstants,
)

NOT_TRANSCRIBED = Missing(
    reason="NOT_DECLARED", detail="PLACEHOLDER: not transcribed yet"
)

# PLACEHOLDER constants, one set per equation. None is a constant of the method.
PRESSURE = AtmosphericPressureConstants(
    sea_level_pressure=40.0, reference_temperature=8.0, lapse_rate=2.0, exponent=3.0
)
PSYCHROMETRIC = PsychrometricConstants(coefficient=3.0)
SATURATION = SaturationVapourPressureConstants(scale=3.0, numerator=2.0, offset=5.0)
SLOPE = SlopeConstants(multiplier=7.0)
DISTANCE = InverseRelativeDistanceConstants(offset=2.0, amplitude=3.0, days_in_year=4.0)
DECLINATION = SolarDeclinationConstants(amplitude=3.0, days_in_year=4.0, phase=math.pi)
EXTRATERRESTRIAL = ExtraterrestrialRadiationConstants(
    time_factor=3.0, solar_constant=5.0
)
CLEAR_SKY = ClearSkyRadiationConstants(base=2.0, elevation_coefficient=3.0)
SHORTWAVE = NetShortwaveConstants(albedo=3.0)
LONGWAVE = NetLongwaveConstants(
    stefan_boltzmann=2.0,
    kelvin_offset=2.0,
    humidity_intercept=11.0,
    humidity_slope=3.0,
    cloudiness_multiplier=3.0,
    cloudiness_offset=5.0,
)
SOIL = SoilHeatFluxConstants(daily_value=3.0)
PENMAN = PenmanMonteithConstants(
    radiation_factor=2.0,
    numerator_constant=10.0,
    kelvin_offset=2.0,
    denominator_constant=1.5,
)

# The same PLACEHOLDER sets, as one argument of the daily composition.
PLACEHOLDER_CONSTANTS = Et0Constants(
    atmospheric_pressure=PRESSURE,
    psychrometric=PSYCHROMETRIC,
    saturation_vapour_pressure=SATURATION,
    slope=SLOPE,
    inverse_relative_distance=DISTANCE,
    solar_declination=DECLINATION,
    extraterrestrial_radiation=EXTRATERRESTRIAL,
    clear_sky_radiation=CLEAR_SKY,
    net_shortwave=SHORTWAVE,
    net_longwave=LONGWAVE,
    soil_heat_flux=SOIL,
    penman_monteith=PENMAN,
)


@dataclasses.dataclass(frozen=True)
class Case:
    """One function with PLACEHOLDER operands and its hand-computed result."""

    function: object
    inputs: dict[str, object]
    constants: dict[str, object]  # argument name -> constants dataclass
    expected: float

    def call(self, inputs=None, constants=None):
        return self.function(**(inputs or self.inputs), **(constants or self.constants))


CASES: dict[str, Case] = {
    # ((8 - 2 x 2) / 8) ** 3 = 0.5 ** 3 = 0.125; 40 x 0.125 = 5
    "atmospheric_pressure": Case(
        eq.atmospheric_pressure, {"elevation": 2.0}, {"constants": PRESSURE}, 5.0
    ),
    # 3 x 5 = 15
    "psychrometric_constant": Case(
        eq.psychrometric_constant,
        {"pressure": 5.0},
        {"constants": PSYCHROMETRIC},
        15.0,
    ),
    # (7 + 3) / 2 = 5
    "mean_temperature": Case(
        eq.mean_temperature,
        {"temperature_max": 7.0, "temperature_min": 3.0},
        {},
        5.0,
    ),
    # 2 x 5 / (5 + 5) = 1; 3 x e ** 1
    "saturation_vapour_pressure": Case(
        eq.saturation_vapour_pressure,
        {"temperature": 5.0},
        {"constants": SATURATION},
        3.0 * math.e,
    ),
    # at 5: 3 e; at 0: 2 x 0 / 5 = 0, 3 x e ** 0 = 3; mean (3 e + 3) / 2
    "mean_saturation_vapour_pressure": Case(
        eq.mean_saturation_vapour_pressure,
        {"temperature_max": 5.0, "temperature_min": 0.0},
        {"constants": SATURATION},
        (3.0 * math.e + 3.0) / 2.0,
    ),
    # 7 x 3 e / ((5 + 5) x (5 + 5)) = 21 e / 100
    "slope_of_saturation_vapour_pressure_curve": Case(
        eq.slope_of_saturation_vapour_pressure_curve,
        {"temperature": 5.0},
        {"saturation_constants": SATURATION, "constants": SLOPE},
        21.0 * math.e / 100.0,
    ),
    # Eq. 11 at the dew point 5: 3 e
    "actual_vapour_pressure_from_dew_point": Case(
        eq.actual_vapour_pressure_from_dew_point,
        {"dew_point_temperature": 5.0},
        {"constants": SATURATION},
        3.0 * math.e,
    ),
    # 11 - 4 = 7
    "vapour_pressure_deficit": Case(
        eq.vapour_pressure_deficit,
        {"mean_saturation_vapour_pressure": 11.0, "actual_vapour_pressure": 4.0},
        {},
        7.0,
    ),
    # 45 degrees is a quarter of pi
    "latitude_in_radians": Case(
        eq.latitude_in_radians,
        {"latitude_decimal_degrees": 45.0},
        {},
        math.pi / 4.0,
    ),
    # cos(2 pi x 4 / 4) = 1; 2 + 3 x 1 = 5
    "inverse_relative_distance": Case(
        eq.inverse_relative_distance,
        {"day_of_year": 4},
        {"constants": DISTANCE},
        5.0,
    ),
    # sin(2 pi x 3 / 4 - pi) = sin(pi / 2) = 1; 3 x 1 = 3
    "solar_declination": Case(
        eq.solar_declination,
        {"day_of_year": 3},
        {"constants": DECLINATION},
        3.0,
    ),
    # arccos(-tan(pi / 4) x tan(0)) = arccos(0) = pi / 2
    "sunset_hour_angle": Case(
        eq.sunset_hour_angle,
        {"latitude_radians": math.pi / 4.0, "solar_declination": 0.0},
        {},
        math.pi / 2.0,
    ),
    # bracket: (pi / 2) x 0 x 0 + 1 x 1 x sin(pi / 2) = 1; 3 / pi x 5 x 7 x 1 = 105 / pi
    "extraterrestrial_radiation": Case(
        eq.extraterrestrial_radiation,
        {
            "latitude_radians": 0.0,
            "inverse_relative_distance": 7.0,
            "solar_declination": 0.0,
            "sunset_hour_angle": math.pi / 2.0,
        },
        {"constants": EXTRATERRESTRIAL},
        105.0 / math.pi,
    ),
    # (2 + 3 x 5) x 7 = 119
    "clear_sky_solar_radiation": Case(
        eq.clear_sky_solar_radiation,
        {"elevation": 5.0, "extraterrestrial_radiation": 7.0},
        {"constants": CLEAR_SKY},
        119.0,
    ),
    # 5 - 3 x 5 = -10
    "net_shortwave_radiation": Case(
        eq.net_shortwave_radiation,
        {"solar_radiation": 5.0},
        {"constants": SHORTWAVE},
        -10.0,
    ),
    # (1 + 2) ** 4 = 81, (-1 + 2) ** 4 = 1, mean 41; 11 - 3 x sqrt(4) = 5;
    # 3 x 4 / 2 - 5 = 1; 2 x 41 x 5 x 1 = 410
    "net_longwave_radiation": Case(
        eq.net_longwave_radiation,
        {
            "temperature_max": 1.0,
            "temperature_min": -1.0,
            "actual_vapour_pressure": 4.0,
            "solar_radiation": 4.0,
            "clear_sky_radiation": 2.0,
        },
        {"constants": LONGWAVE},
        410.0,
    ),
    # 11 - 4 = 7
    "net_radiation": Case(
        eq.net_radiation,
        {"net_shortwave_radiation": 11.0, "net_longwave_radiation": 4.0},
        {},
        7.0,
    ),
    # the constant itself
    "soil_heat_flux_daily": Case(eq.soil_heat_flux_daily, {}, {"constants": SOIL}, 3.0),
    # numerator: 2 x 3 x (7 - 2) = 30; 5 x (10 / (3 + 2)) x 4 x (11 - 7) = 160; 190
    # denominator: 3 + 5 + 5 x 1.5 x 4 = 38; 190 / 38 = 5
    "reference_evapotranspiration": Case(
        eq.reference_evapotranspiration,
        {
            "slope": 3.0,
            "net_radiation": 7.0,
            "soil_heat_flux": 2.0,
            "psychrometric_constant": 5.0,
            "mean_temperature": 3.0,
            "wind_speed_2m": 4.0,
            "mean_saturation_vapour_pressure": 11.0,
            "actual_vapour_pressure": 7.0,
        },
        {"constants": PENMAN},
        5.0,
    ),
}

INPUT_CASES = [(name, field) for name, case in CASES.items() for field in case.inputs]
CONSTANT_CASES = [
    (name, argument, item.name)
    for name, case in CASES.items()
    for argument, group in case.constants.items()
    for item in dataclasses.fields(group)
]


def _group_name(group: object) -> str:
    """The identifier prefix of a constants class, as the README table writes it."""
    return {
        AtmosphericPressureConstants: "atmospheric_pressure",
        PsychrometricConstants: "psychrometric",
        SaturationVapourPressureConstants: "saturation_vapour_pressure",
        SlopeConstants: "slope",
        InverseRelativeDistanceConstants: "inverse_relative_distance",
        SolarDeclinationConstants: "solar_declination",
        ExtraterrestrialRadiationConstants: "extraterrestrial_radiation",
        ClearSkyRadiationConstants: "clear_sky_radiation",
        NetShortwaveConstants: "net_shortwave",
        NetLongwaveConstants: "net_longwave",
        SoilHeatFluxConstants: "soil_heat_flux",
        PenmanMonteithConstants: "penman_monteith",
    }[type(group)]


# --- EQ1: each intermediate quantity is a separate function with its own result ---


@pytest.mark.parametrize("name", list(CASES))
def test_eq1_each_function_gives_its_hand_computed_placeholder_result(name):
    result = CASES[name].call()
    assert isinstance(result, float)
    assert result == pytest.approx(CASES[name].expected, rel=1e-12, abs=1e-12)


def test_eq1_every_public_function_of_the_module_has_a_case():
    public = {
        name
        for name, value in vars(eq).items()
        if callable(value)
        and not name.startswith("_")
        and getattr(value, "__module__", None) == eq.__name__
    }
    helpers = {"check_operands", "pass_through", "day_of_year"}
    assert public - helpers == set(CASES)


# --- EQ2: a missing input gives a missing result that names it ---


@pytest.mark.parametrize(("name", "field"), INPUT_CASES)
def test_eq2_a_missing_input_gives_a_missing_result_that_names_it(name, field):
    case = CASES[name]
    inputs = dict(case.inputs)
    inputs[field] = Missing(reason="NO_COVERAGE", detail="PLACEHOLDER detail")
    result = case.call(inputs=inputs)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert f"input '{field}'" in result.detail
    assert "NO_COVERAGE" in result.detail


def test_eq2_every_missing_input_is_named_not_only_the_first():
    case = CASES["net_radiation"]
    result = case.call(
        inputs={
            "net_shortwave_radiation": NOT_TRANSCRIBED,
            "net_longwave_radiation": NOT_TRANSCRIBED,
        }
    )
    assert "net_shortwave_radiation" in result.detail
    assert "net_longwave_radiation" in result.detail


# --- EQ3: a missing constant gives a missing result that names it ---


@pytest.mark.parametrize(("name", "argument", "field"), CONSTANT_CASES)
def test_eq3_a_missing_constant_gives_a_missing_result_that_names_it(
    name, argument, field
):
    case = CASES[name]
    group = case.constants[argument]
    constants = dict(case.constants)
    constants[argument] = dataclasses.replace(group, **{field: NOT_TRANSCRIBED})
    result = case.call(constants=constants)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert f"constant '{_group_name(group)}.{field}'" in result.detail
    assert "NOT_DECLARED" in result.detail


# --- EQ4: a non-finite input or constant is not computed ---


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
@pytest.mark.parametrize(("name", "field"), INPUT_CASES)
def test_eq4_a_non_finite_input_is_not_computed(name, field, bad):
    case = CASES[name]
    inputs = dict(case.inputs)
    inputs[field] = bad
    result = case.call(inputs=inputs)
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"
    assert field in result.detail


@pytest.mark.parametrize(("name", "argument", "field"), CONSTANT_CASES)
def test_eq4_a_non_finite_constant_is_not_computed(name, argument, field):
    case = CASES[name]
    group = case.constants[argument]
    constants = dict(case.constants)
    constants[argument] = dataclasses.replace(group, **{field: math.nan})
    result = case.call(constants=constants)
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"
    assert f"{_group_name(group)}.{field}" in result.detail


def test_eq4_a_missing_operand_is_reported_before_a_non_finite_one():
    result = CASES["net_radiation"].call(
        inputs={
            "net_shortwave_radiation": math.inf,
            "net_longwave_radiation": NOT_TRANSCRIBED,
        }
    )
    assert result.reason == "MISSING_INPUT"


# --- EQ5: arithmetic without a finite real result is missing, not an exception ---


@pytest.mark.parametrize(
    ("name", "inputs", "constants"),
    [
        # (8 - 2 x 8) / 8 = -1, and -1 ** 0.5 is not real
        (
            "atmospheric_pressure",
            {"elevation": 8.0},
            {"constants": dataclasses.replace(PRESSURE, exponent=0.5)},
        ),
        # the offset cancels the temperature: division by zero
        ("saturation_vapour_pressure", {"temperature": -5.0}, None),
        # -tan(1.5) x tan(1.5) is far below -1: no arc cosine
        (
            "sunset_hour_angle",
            {"latitude_radians": 1.5, "solar_declination": -1.5},
            None,
        ),
        # a negative vapour pressure has no square root
        (
            "net_longwave_radiation",
            {
                "temperature_max": 1.0,
                "temperature_min": -1.0,
                "actual_vapour_pressure": -4.0,
                "solar_radiation": 4.0,
                "clear_sky_radiation": 2.0,
            },
            None,
        ),
        # a clear-sky radiation of zero: division by zero
        (
            "net_longwave_radiation",
            {
                "temperature_max": 1.0,
                "temperature_min": -1.0,
                "actual_vapour_pressure": 4.0,
                "solar_radiation": 4.0,
                "clear_sky_radiation": 0.0,
            },
            None,
        ),
        # an exponent that overflows
        (
            "saturation_vapour_pressure",
            {"temperature": 5.0},
            {"constants": dataclasses.replace(SATURATION, numerator=1e6)},
        ),
        # a denominator of zero: 3 + (-3) + (-3) x 1.5 x 0 = 0
        (
            "reference_evapotranspiration",
            {
                "slope": 3.0,
                "net_radiation": 7.0,
                "soil_heat_flux": 2.0,
                "psychrometric_constant": -3.0,
                "mean_temperature": 3.0,
                "wind_speed_2m": 0.0,
                "mean_saturation_vapour_pressure": 11.0,
                "actual_vapour_pressure": 7.0,
            },
            None,
        ),
    ],
)
def test_eq5_no_finite_real_result_is_not_computable(name, inputs, constants):
    result = CASES[name].call(inputs=inputs, constants=constants)
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"


# --- EQ6: operands of the wrong type are a defect of the caller ---


@pytest.mark.parametrize(
    "bad",
    [True, "5", None, InputsMissing(reason="NO_COVERAGE")],
    ids=["boolean", "text", "none", "missing-of-the-input-contracts"],
)
def test_eq6_an_input_of_the_wrong_type_raises(bad):
    with pytest.raises(TypeError):
        eq.net_radiation(bad, 4.0)


def test_eq6_a_constant_of_the_wrong_type_raises():
    with pytest.raises(TypeError):
        eq.psychrometric_constant(
            5.0, dataclasses.replace(PSYCHROMETRIC, coefficient=None)
        )


def test_eq6_constants_of_another_equation_raise():
    with pytest.raises(TypeError):
        eq.psychrometric_constant(5.0, SLOPE)


# --- EQ7: the day of the year comes from the date of the series ---


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        (dt.date(2001, 1, 1), 1),  # PLACEHOLDER dates
        (dt.date(2001, 2, 3), 34),  # 31 + 3
        (dt.date(2001, 3, 1), 60),  # 31 + 28 + 1
        (dt.date(2004, 3, 1), 61),  # 31 + 29 + 1, a leap year
        (dt.date(2001, 12, 31), 365),
        (dt.date(2004, 12, 31), 366),
    ],
)
def test_eq7_day_of_year_counts_the_days_of_the_calendar_year(date, expected):
    assert eq.day_of_year(date) == expected


@pytest.mark.parametrize("bad", ["2001-01-01", dt.datetime(2001, 1, 1), 1])
def test_eq7_day_of_year_takes_a_date_only(bad):
    with pytest.raises(TypeError):
        eq.day_of_year(bad)


# --- EQ8: pass_through keeps a missing input as it is ---


def test_eq8_pass_through_keeps_a_missing_input_and_checks_a_number():
    assert eq.pass_through("x", NOT_TRANSCRIBED) is NOT_TRANSCRIBED
    assert eq.pass_through("x", 3) == 3.0
    result = eq.pass_through("x", math.inf)
    assert result.reason == "NOT_COMPUTABLE"
    assert "'x'" in result.detail
    with pytest.raises(TypeError):
        eq.pass_through("x", "3")
