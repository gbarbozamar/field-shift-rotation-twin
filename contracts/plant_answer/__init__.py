"""Contract "Plant answer". PROPOSED (blueprint section 3.7).

The request and the answer of "What should I plant?". See ``README.md`` in
this folder.
"""

from .plant_answer import (
    DIMENSIONLESS,
    MARGINS_OF,
    MAX_ROTATIONS,
    MIN_ROTATIONS,
    STRESS_TEST_LABEL,
    Answer,
    AnswerMissing,
    Direction,
    Erosivity,
    MarginOf,
    OptionState,
    PlantAnswer,
    PlantAnswerNotBuilt,
    PlantOption,
    PlantRequest,
    Questions,
    SiteReference,
    Strictness,
    Verdict,
    check_answer_against_request,
)

__all__ = [
    "DIMENSIONLESS",
    "MARGINS_OF",
    "MAX_ROTATIONS",
    "MIN_ROTATIONS",
    "STRESS_TEST_LABEL",
    "Answer",
    "AnswerMissing",
    "Direction",
    "Erosivity",
    "MarginOf",
    "OptionState",
    "PlantAnswer",
    "PlantAnswerNotBuilt",
    "PlantOption",
    "PlantRequest",
    "Questions",
    "SiteReference",
    "Strictness",
    "Verdict",
    "check_answer_against_request",
]
