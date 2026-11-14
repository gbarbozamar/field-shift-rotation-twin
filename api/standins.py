"""Stand-in implementations of the interfaces, used until the real ones exist.

Every stand-in returns only typed absences: ``None`` with a reason code of
contracts/CONVENTIONS.md C3.2. None of them ever returns a sample value.

Status: PROPOSED (blueprint section 3.7), including the identifiers below.
"""

from __future__ import annotations

from collections.abc import Sequence

from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
from api.ports import (
    CLIMATE_CONTRACT,
    SOIL_SLOPE_CONTRACT,
    EnginesResult,
    ErrorDetail,
    Missing,
    ModuleStatus,
    RotationPayload,
    SoilSlopeResult,
)

# PROPOSED: source identifiers of the stand-ins, so the interface can tell a
# stand-in from a real source.
CLIMATE_STANDIN_ID = "climate_not_connected"
SOIL_SLOPE_STANDIN_ID = "soil_slope_not_loaded"

# PROPOSED: the engine modules listed by the default app, one per engine
# folder of CLAUDE.md. Replaced by the list of contracts/ENTRYPOINTS.md.
DEFAULT_MODULE_IDS: tuple[str, ...] = (
    "calendar",
    "erosion",
    "water",
    "residues",
    "amg",
    "rothc",
)

NOT_BUILT = "the module is not built yet"


class EnginesNotBuilt:
    """Engines stand-in: no calendar, no result, every module ``not_available``.

    Replaced by an implementation that calls the engine entry points of
    contracts/ENTRYPOINTS.md, once they are agreed and the engines land
    (Block 1).
    """

    def __init__(self, module_ids: Sequence[str] = DEFAULT_MODULE_IDS) -> None:
        self._module_ids = tuple(module_ids)

    def run(
        self,
        rotation: RotationPayload,
        climate: ClimateResult,
        soil_slope: SoilSlopeResult,
    ) -> EnginesResult:
        return EnginesResult(
            calendar=None,
            result=None,
            result_missing=Missing(
                reason="NOT_AVAILABLE", detail="the engines are not built yet"
            ),
            modules=tuple(
                ModuleStatus(
                    id=module_id,
                    state="not_available",
                    reason="NOT_AVAILABLE",
                    detail=NOT_BUILT,
                )
                for module_id in self._module_ids
            ),
        )


class ClimateUnavailable:
    """Climate stand-in: always ``data=None``, ``unavailable``, ``NOT_AVAILABLE``.

    Replaced by the NASA POWER adapter of unit ``l2/power-adapter``, which
    implements ``adapters.ports.ClimateSource``.
    """

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return ClimateResult(
            data=None,
            source=SourceInfo(
                id=CLIMATE_STANDIN_ID,
                contract=CLIMATE_CONTRACT,
                state="unavailable",
                missing_reason="NOT_AVAILABLE",
                detail="no climate adapter is connected yet",
            ),
        )


class SoilSlopeNotLoaded:
    """Soil-and-slope stand-in: always ``data=None``, ``unavailable``.

    Replaced first by a loader of the accepted soil-and-slope contract example
    (``state="example"``), then by the soil and terrain adapters of Block 2.
    """

    def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult:
        return SoilSlopeResult(
            data=None,
            source=SourceInfo(
                id=SOIL_SLOPE_STANDIN_ID,
                contract=SOIL_SLOPE_CONTRACT,
                state="unavailable",
                missing_reason="NOT_AVAILABLE",
                detail="no soil and slope source is loaded yet",
            ),
        )


class AcceptAnyRotation:
    """Rotation validator stand-in: any JSON object is accepted.

    Replaced by validation against the "Rotation definition" contract model,
    once that contract is merged.
    """

    def validate(self, rotation: RotationPayload) -> list[ErrorDetail]:
        return []
