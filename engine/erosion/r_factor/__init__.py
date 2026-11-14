"""Rainfall erosivity factor R of docs/METHODS.md M1.2. PROPOSED (blueprint section 3.7).

The daily erosivity index, its monthly and annual sums, the monthly fractions
and the yearly ratios (relative terms only), R by year and month from a mean
annual level supplied by the caller, and the control regression on monthly
precipitation. Every constant is an argument without a default. See
``README.md`` in this folder.
"""

from ._checks import REASON_UNIT_NOT_ACCEPTED
from .control import (
    FractionComparison,
    compare_monthly_fractions,
    control_monthly_erosivity,
)
from .erosivity import (
    PRECIPITATION_UNIT,
    R_UNIT,
    RFactorParts,
    annual_sums,
    checked_daily_precipitation,
    daily_erosivity_index,
    monthly_fractions,
    monthly_sums,
    r_by_year_and_month,
    r_factor_parts,
    yearly_ratios,
)

__all__ = [
    "PRECIPITATION_UNIT",
    "R_UNIT",
    "REASON_UNIT_NOT_ACCEPTED",
    "FractionComparison",
    "RFactorParts",
    "annual_sums",
    "checked_daily_precipitation",
    "compare_monthly_fractions",
    "control_monthly_erosivity",
    "daily_erosivity_index",
    "monthly_fractions",
    "monthly_sums",
    "r_by_year_and_month",
    "r_factor_parts",
    "yearly_ratios",
]
