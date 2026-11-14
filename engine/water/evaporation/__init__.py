"""Soil evaporation, FAO-56 dual crop coefficient (decision D44). Status: PROPOSED.

An internal part of the water engine: it computes the evaporation
coefficient ``Ke`` that engine/water/balance takes per day. See
engine/water/evaporation/README.md.
"""

from engine.water.evaporation.surface_layer import (
    RESULT_QUANTITIES,
    DayInput,
    DayResult,
    UpperLimitClimateConstants,
    climate_adjusted_upper_limit,
    cover_fraction_from_basal_coefficient,
    evaporation_coefficient,
    evaporation_reduction_coefficient,
    exposed_and_wetted_fraction,
    run_surface_layer,
    step,
    total_evaporable_water,
    upper_limit_of_crop_coefficient,
)

__all__ = [
    "RESULT_QUANTITIES",
    "DayInput",
    "DayResult",
    "UpperLimitClimateConstants",
    "climate_adjusted_upper_limit",
    "cover_fraction_from_basal_coefficient",
    "evaporation_coefficient",
    "evaporation_reduction_coefficient",
    "exposed_and_wetted_fraction",
    "run_surface_layer",
    "step",
    "total_evaporable_water",
    "upper_limit_of_crop_coefficient",
]
