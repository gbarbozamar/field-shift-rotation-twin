"""Daily surface runoff by the Curve Number method (decision D44 of issue #77).

Status: PROPOSED (blueprint section 3.7). An internal part of the water
engine (``engine/water/``, entry point EP3 of contracts/ENTRYPOINTS.md); the
route does not call it. See engine/water/runoff/README.md.
"""

from .curve_number import (
    PRECIPITATION,
    PRECIPITATION_UNIT,
    CurveNumberConstants,
    PrecipitationValue,
    RunoffDayInput,
    RunoffDayResult,
    initial_abstraction,
    potential_retention,
    run_runoff,
    runoff_day,
    runoff_depth,
)

__all__ = [
    "PRECIPITATION",
    "PRECIPITATION_UNIT",
    "CurveNumberConstants",
    "PrecipitationValue",
    "RunoffDayInput",
    "RunoffDayResult",
    "initial_abstraction",
    "potential_retention",
    "run_runoff",
    "runoff_day",
    "runoff_depth",
]
