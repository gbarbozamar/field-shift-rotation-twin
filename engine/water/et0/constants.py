"""The constants of the daily reference evapotranspiration, supplied by the caller.

Status: PROPOSED (blueprint section 3.7). See engine/water/et0/README.md,
table "Constants a person has to transcribe".

Every constant of the equations is a field of one of the classes below. No
field has a default and this module holds no value: a person transcribes
each value from the method's text and a second person checks it (decision
D34 of issue #77). Until a value is transcribed, the caller passes it as the
``Missing`` of contracts/results/models.py, and every quantity that needs it
is missing with reason ``MISSING_INPUT``, naming the constant.

The identifier of a constant is ``<field of Et0Constants>.<field of its
class>``, for example ``net_longwave.stefan_boltzmann``. It is the identifier
used in the README table and in the ``detail`` of a missing result.

How each constant enters its equation is written in the docstring of the
function of engine/water/et0/equations.py that uses it. Those forms are
PROPOSED: a person checks them against the equations of the method.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.results.models import Missing

# A constant is a number, or missing with its reason (C3.1).
Constant = float | Missing


@dataclass(frozen=True)
class AtmosphericPressureConstants:
    """Constants of the atmospheric pressure from elevation (FAO-56 Eq. 7).

    Form (PROPOSED): ``sea_level_pressure * ((reference_temperature -
    lapse_rate * elevation) / reference_temperature) ** exponent``.
    """

    sea_level_pressure: Constant
    reference_temperature: Constant
    lapse_rate: Constant
    exponent: Constant


@dataclass(frozen=True)
class PsychrometricConstants:
    """Constant of the psychrometric constant (FAO-56 Eq. 8).

    Form (PROPOSED): ``coefficient * pressure``. Whether the coefficient is
    transcribed as one number or as the physical quantities it combines is
    OPEN (README, OPEN list).
    """

    coefficient: Constant


@dataclass(frozen=True)
class SaturationVapourPressureConstants:
    """Constants of the saturation vapour pressure at a temperature (FAO-56 Eq. 11).

    Form (PROPOSED): ``scale * exp(numerator * T / (T + offset))``. The same
    three constants are used by the slope of the curve (Eq. 13) and by the
    PROPOSED route from dew point (D25).
    """

    scale: Constant
    numerator: Constant
    offset: Constant


@dataclass(frozen=True)
class SlopeConstants:
    """Constant of the slope of the saturation vapour pressure curve (FAO-56 Eq. 13).

    Form (PROPOSED): ``multiplier * e(T) / ((T + offset) * (T + offset))``,
    where ``e(T)`` and ``offset`` are those of Eq. 11.
    """

    multiplier: Constant


@dataclass(frozen=True)
class InverseRelativeDistanceConstants:
    """Constants of the inverse relative distance Earth-Sun (FAO-56 Eq. 23).

    Form (PROPOSED): ``offset + amplitude * cos(tau * J / days_in_year)``.
    """

    offset: Constant
    amplitude: Constant
    days_in_year: Constant


@dataclass(frozen=True)
class SolarDeclinationConstants:
    """Constants of the solar declination (FAO-56 Eq. 24).

    Form (PROPOSED): ``amplitude * sin(tau * J / days_in_year - phase)``.
    """

    amplitude: Constant
    days_in_year: Constant
    phase: Constant


@dataclass(frozen=True)
class ExtraterrestrialRadiationConstants:
    """Constants of the extraterrestrial radiation for daily periods (FAO-56 Eq. 21).

    Form (PROPOSED): ``time_factor / pi * solar_constant * dr * (ws sin(phi)
    sin(delta) + cos(phi) cos(delta) sin(ws))``.
    """

    time_factor: Constant
    solar_constant: Constant


@dataclass(frozen=True)
class ClearSkyRadiationConstants:
    """Constants of the clear-sky solar radiation (FAO-56 Eq. 37).

    Form (PROPOSED): ``(base + elevation_coefficient * elevation) * Ra``.
    """

    base: Constant
    elevation_coefficient: Constant


@dataclass(frozen=True)
class NetShortwaveConstants:
    """Constant of the net shortwave radiation (FAO-56 Eq. 38).

    Form (PROPOSED): ``Rs - albedo * Rs``.
    """

    albedo: Constant


@dataclass(frozen=True)
class NetLongwaveConstants:
    """Constants of the net longwave radiation (FAO-56 Eq. 39).

    Form (PROPOSED): ``stefan_boltzmann * mean(fourth power of (Tmax +
    kelvin_offset), fourth power of (Tmin + kelvin_offset)) *
    (humidity_intercept - humidity_slope * sqrt(ea)) *
    (cloudiness_multiplier * Rs / Rso - cloudiness_offset)``.
    The fourth power is the one of the Stefan-Boltzmann law.
    """

    stefan_boltzmann: Constant
    kelvin_offset: Constant
    humidity_intercept: Constant
    humidity_slope: Constant
    cloudiness_multiplier: Constant
    cloudiness_offset: Constant


@dataclass(frozen=True)
class SoilHeatFluxConstants:
    """The soil heat flux of a daily period (FAO-56 Eq. 42, case "For day and ten-day periods").

    The engine computes nothing for it: the caller supplies the value.
    """

    daily_value: Constant


@dataclass(frozen=True)
class PenmanMonteithConstants:
    """Constants of the FAO Penman-Monteith equation (FAO-56 Eq. 6).

    Form (PROPOSED): ``(radiation_factor * D * (Rn - G) + g *
    (numerator_constant / (T + kelvin_offset)) * u2 * (es - ea)) / (D + g +
    g * denominator_constant * u2)``, with ``D`` the slope of the curve and
    ``g`` the psychrometric constant. ``kelvin_offset`` is separate from the
    one of Eq. 39 because the text prints them differently (issue #13,
    section 3).
    """

    radiation_factor: Constant
    numerator_constant: Constant
    kelvin_offset: Constant
    denominator_constant: Constant


@dataclass(frozen=True)
class Et0Constants:
    """All the constants of one daily reference evapotranspiration, by equation."""

    atmospheric_pressure: AtmosphericPressureConstants
    psychrometric: PsychrometricConstants
    saturation_vapour_pressure: SaturationVapourPressureConstants
    slope: SlopeConstants
    inverse_relative_distance: InverseRelativeDistanceConstants
    solar_declination: SolarDeclinationConstants
    extraterrestrial_radiation: ExtraterrestrialRadiationConstants
    clear_sky_radiation: ClearSkyRadiationConstants
    net_shortwave: NetShortwaveConstants
    net_longwave: NetLongwaveConstants
    soil_heat_flux: SoilHeatFluxConstants
    penman_monteith: PenmanMonteithConstants
