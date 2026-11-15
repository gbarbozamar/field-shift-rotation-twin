"""The simple margin of a rotation, its soil loss against the declared limit,
and the rotation to plant. PROPOSED.

See ``README.md`` in this folder.
"""

from .decide import (
    Answer,
    Decision,
    LimitCost,
    OptionState,
    OptionVerdict,
    RotationOption,
    Strictness,
    choose_rotation,
)
from .limit import (
    LimitAssessment,
    LimitCheck,
    SoilLossLevel,
    Verdict,
    assess_limit,
)
from .margin import MarginResult, RotationMargin, compute_rotation_margin

__all__ = [
    "Answer",
    "Decision",
    "LimitAssessment",
    "LimitCheck",
    "LimitCost",
    "MarginResult",
    "OptionState",
    "OptionVerdict",
    "RotationMargin",
    "RotationOption",
    "SoilLossLevel",
    "Strictness",
    "Verdict",
    "assess_limit",
    "choose_rotation",
    "compute_rotation_margin",
]
