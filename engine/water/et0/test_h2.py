"""[H2] of docs/VALIDATION.md: the reference evapotranspiration against a worked FAO-56 example.

Run with ``python -m pytest engine/water/et0/`` from the repository root.

The test is written and skipped. It waits for what a person transcribes and
a second person checks (decision D34 of issue #77), and for the science
reviewers, who define [H2] and its tolerance ("Definition", "Expected
value" and "Tolerance" of H2 are OPEN in docs/VALIDATION.md).

The worked example issue #13 identifies is EXAMPLE 18 of Chapter 4 of FAO-56
("Determination of ETo with daily data"). That example is given relative
humidity, hours of sunshine and wind at another height, while this engine
takes dew point, solar radiation and wind at 2 m (D25 to D27). So the test
enters the example's own rows for the actual vapour pressure (Eq. 17), the
solar radiation (Eq. 35) and the wind speed at 2 m (Eq. 47), and checks
every step this engine computes against the example's rows. Whether that is
an acceptable definition of [H2] is OPEN (engine/water/et0/README.md).

Nothing below holds a value. ``EXAMPLE_18`` and ``CONSTANTS`` stay ``None``
until a person fills them; the test then runs without any other change.
"""

from __future__ import annotations

import dataclasses

import pytest

from contracts.results.models import Missing
from engine.water.et0.constants import Et0Bounds, Et0Constants
from engine.water.et0.daily import Et0Steps, reference_evapotranspiration_day

# Filled by a person from FAO-56, Chapter 4, EXAMPLE 18, with the record D34
# asks for (full reference, locator, verbatim text, date read) and checked
# by a second person. Keys:
#   "inputs": day_of_year (Table 2.5), latitude_radians, elevation,
#       temperature_max, temperature_min, actual_vapour_pressure (row of
#       Eq. 17), wind_speed_2m (row of Eq. 47), solar_radiation (row of
#       Eq. 35);
#   "steps": the example's printed row for each field of Et0Steps that it
#       prints (atmospheric_pressure, mean_temperature, slope,
#       psychrometric_constant, mean_saturation_vapour_pressure,
#       vapour_pressure_deficit, inverse_relative_distance,
#       solar_declination, sunset_hour_angle, extraterrestrial_radiation,
#       clear_sky_solar_radiation, net_shortwave_radiation,
#       net_longwave_radiation, net_radiation, soil_heat_flux,
#       reference_evapotranspiration);
#   "tolerance": {field: absolute tolerance}, set by the science reviewers.
EXAMPLE_18: dict | None = None

# Filled by a person: the constants of the table "Constants a person has to
# transcribe" of engine/water/et0/README.md, transcribed and checked (D34).
CONSTANTS: Et0Constants | None = None

# Filled by a person: the two bounds of decision D82 (PC-4), rows
# "relative_shortwave_bound.upper_bound" and "wind_speed_bound.lower_bound"
# of the same table, transcribed and checked (D34).
BOUNDS: Et0Bounds | None = None

WAITS_FOR = (
    "[H2] waits for: (1) the inputs, intermediate results, final value of "
    "FAO-56 Chapter 4 EXAMPLE 18, transcribed from the manual and checked by "
    "a person (D34 of issue #77); (2) the tolerance and the printed precision "
    "used, set by the science reviewers (H2 in docs/VALIDATION.md is OPEN); "
    "(3) the constants of the table in engine/water/et0/README.md, "
    "transcribed and checked, the two bounds of D82 included; (4) a person's "
    "check of the PROPOSED forms of the equations"
)


@pytest.mark.skipif(
    EXAMPLE_18 is None or CONSTANTS is None or BOUNDS is None, reason=WAITS_FOR
)
def test_h2_worked_example_18_of_fao_56():
    steps = reference_evapotranspiration_day(
        **EXAMPLE_18["inputs"], constants=CONSTANTS, bounds=BOUNDS
    )
    names = {item.name for item in dataclasses.fields(Et0Steps)}
    expected = EXAMPLE_18["steps"]
    tolerance = EXAMPLE_18["tolerance"]
    assert set(expected) <= names
    assert "reference_evapotranspiration" in expected
    for name, printed in expected.items():
        computed = getattr(steps, name)
        assert not isinstance(computed, Missing), f"{name}: {computed}"
        assert computed == pytest.approx(printed, abs=tolerance[name]), name


def test_h2_the_skip_says_what_it_waits_for():
    assert "EXAMPLE 18" in WAITS_FOR
    assert "D34" in WAITS_FOR
    assert "tolerance" in WAITS_FOR
    assert "D82" in WAITS_FOR
