"""Stand-in implementations of the interfaces, used until the real ones exist.

The engines have no stand-in any more: ``api/engines.py`` reports every engine
that is not built as a typed absence. Every stand-in here returns only typed
absences: ``None`` with a reason code of
contracts/CONVENTIONS.md C3.2. None of them ever returns a sample value.

Status: PROPOSED (blueprint section 3.7), including the identifiers below.
"""

from __future__ import annotations

from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
from api.ports import (
    CLIMATE_CONTRACT,
    SOIL_SLOPE_CONTRACT,
    SoilSlopeResult,
)

# PROPOSED: source identifiers of the stand-ins, so the interface can tell a
# stand-in from a real source.
CLIMATE_STANDIN_ID = "climate_not_connected"
SOIL_SLOPE_STANDIN_ID = "soil_slope_not_loaded"


class ClimateUnavailable:
    """Climate stand-in: always ``data=None``, ``unavailable``, ``NOT_AVAILABLE``.

    Replaced by the NASA POWER adapter of unit ``l2/power-adapter``, which
    implements ``adapters.ports.ClimateSource``.
    """

    source_id = CLIMATE_STANDIN_ID
    contract = CLIMATE_CONTRACT

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return ClimateResult(
            data=None,
            source=SourceInfo(
                id=self.source_id,
                contract=self.contract,
                state="unavailable",
                missing_reason="NOT_AVAILABLE",
                detail="no climate adapter is connected yet",
            ),
        )


class SoilSlopeNotLoaded:
    """Soil-and-slope stand-in: always ``data=None``, ``unavailable``.

    Replaced first by a loader of the accepted soil-and-slope contract example
    (``adapters.example_soil_slope.ExampleSoilSlopeSource``, once a person
    names the accepted file) or by ``adapters.soil_tables.SoilTableSource``
    (soil by soil group, D48, D49), then by slope from an elevation model.
    """

    source_id = SOIL_SLOPE_STANDIN_ID
    contract = SOIL_SLOPE_CONTRACT

    def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult:
        return SoilSlopeResult(
            data=None,
            source=SourceInfo(
                id=self.source_id,
                contract=self.contract,
                state="unavailable",
                missing_reason="NOT_AVAILABLE",
                detail="no soil and slope source is loaded yet",
            ),
        )
