"""The simple margin of a rotation, its soil loss against the declared limit,
the rotation to plant and the soybean price at which it changes. PROPOSED.

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
from .tipping import (
    MARGINS_OF,
    Direction,
    PriceRange,
    TippingOption,
    TippingPoint,
    TippingPrice,
    find_tipping_price,
)

__all__ = [
    "MARGINS_OF",
    "Answer",
    "Decision",
    "Direction",
    "LimitAssessment",
    "LimitCheck",
    "LimitCost",
    "MarginResult",
    "OptionState",
    "OptionVerdict",
    "PriceRange",
    "RotationMargin",
    "RotationOption",
    "SoilLossLevel",
    "Strictness",
    "TippingOption",
    "TippingPoint",
    "TippingPrice",
    "Verdict",
    "assess_limit",
    "choose_rotation",
    "compute_rotation_margin",
    "find_tipping_price",
]
