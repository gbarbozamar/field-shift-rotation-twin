"""Contract "Economic facts". PROPOSED (blueprint section 3.7).

The economic facts a producer declares for one field. See ``README.md`` in
this folder.
"""

from .economic_facts import (
    COST_UNIT,
    KINDS_OF_YEAR,
    MARGIN_UNIT,
    PRICE_UNIT,
    YIELD_UNIT,
    CoverCrop,
    DeclaredMarginCrop,
    EconomicFacts,
    GrainCrop,
    MarginByYear,
    YieldByYear,
)

__all__ = [
    "COST_UNIT",
    "KINDS_OF_YEAR",
    "MARGIN_UNIT",
    "PRICE_UNIT",
    "YIELD_UNIT",
    "CoverCrop",
    "DeclaredMarginCrop",
    "EconomicFacts",
    "GrainCrop",
    "MarginByYear",
    "YieldByYear",
]
