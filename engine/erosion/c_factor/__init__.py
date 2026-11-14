"""Cover-management factor ``C`` from its sub-factors (docs/METHODS.md M1.5, D45). PROPOSED.

Pure functions; every constant of the method is an argument without a
default, supplied by the caller. See ``README.md`` in this folder.

Not an entry point of ``contracts/ENTRYPOINTS.md``: these are parts of the
erosion engine, for a later unit that computes ``C`` for each period.
"""

from .residue import (
    residue_cover_from_mass,
    residue_mass_after_decay,
    residue_mass_over_time,
)
from .rotation import MonthOfRotation, RotationC, rotation_c
from .subfactors import (
    DECLARED_LIMIT,
    SET_TO_ONE,
    SoilLossRatio,
    canopy_subfactor,
    effective_canopy_cover,
    soil_loss_ratio,
    surface_cover_subfactor,
    surface_cover_subfactor_percent,
)

__all__ = [
    "DECLARED_LIMIT",
    "SET_TO_ONE",
    "MonthOfRotation",
    "RotationC",
    "SoilLossRatio",
    "canopy_subfactor",
    "effective_canopy_cover",
    "residue_cover_from_mass",
    "residue_mass_after_decay",
    "residue_mass_over_time",
    "rotation_c",
    "soil_loss_ratio",
    "surface_cover_subfactor",
    "surface_cover_subfactor_percent",
]
