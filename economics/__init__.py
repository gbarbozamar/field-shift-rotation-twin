"""The simple margin of a rotation and its soil loss against the declared limit. PROPOSED.

See ``README.md`` in this folder.
"""

from .limit import (
    LimitAssessment,
    LimitCheck,
    SoilLossLevel,
    Verdict,
    assess_limit,
)
from .margin import MarginResult, RotationMargin, compute_rotation_margin

__all__ = [
    "LimitAssessment",
    "LimitCheck",
    "MarginResult",
    "RotationMargin",
    "SoilLossLevel",
    "Verdict",
    "assess_limit",
    "compute_rotation_margin",
]
