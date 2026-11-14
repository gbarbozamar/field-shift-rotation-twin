"""Tests of the climatological monthly fraction of decision D69 (``climatology.py``).

The cases are PROPOSED (blueprint section 3.7) and are listed in ``README.md``,
section "Climatological monthly fraction (D69)"; a test checks that the two
lists agree.

**Every number in this file is a PLACEHOLDER**: small whole numbers chosen so
that the arithmetic is done by hand. None is a value of the climatology named
by D69 or of any other source, and no case holds an expected value of the
science.

Run from the repository root: ``python -m pytest engine/erosion/r_factor/``.
"""

from __future__ import annotations

import ast
import inspect
import math
import re
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion.r_factor import (
    R_UNIT,
    REASON_UNIT_NOT_ACCEPTED,
    climatological_monthly_fractions,
    climatological_r_by_year_and_month,
    monthly_fractions,
    monthly_sums,
    r_by_year_and_month,
    yearly_ratios,
)
from engine.erosion.r_factor import climatology

HERE = Path(__file__).parent
README = HERE / "README.md"

# Rounding of floating-point arithmetic only. Not a tolerance of the
# validation protocol.
ROUNDING = 1e-12

# PLACEHOLDER monthly values: month m is worth m, so the sum is 78.
PLACEHOLDER_MONTHS = {m: float(m) for m in range(1, 13)}
PLACEHOLDER_SUM = 78.0
LEVEL = (
    0.78  # PLACEHOLDER mean annual level, plainly not a real R: the sum over a hundred
)


def fractions_of_placeholder():
    fractions = climatological_monthly_fractions(monthly_erosivity=PLACEHOLDER_MONTHS)
    assert not isinstance(fractions, ResultMissing)
    return fractions


def test_fractions_are_each_month_over_the_sum_of_twelve():
    fractions = fractions_of_placeholder()
    assert set(fractions) == set(range(1, 13))
    for month, fraction in fractions.items():
        assert fraction == pytest.approx(month / PLACEHOLDER_SUM, abs=ROUNDING)
    assert math.fsum(fractions.values()) == pytest.approx(1.0, abs=ROUNDING)


def test_a_missing_month_makes_every_fraction_missing_and_names_it():
    for shape in (InputMissing, ResultMissing):
        months = dict(PLACEHOLDER_MONTHS)
        months[3] = shape(reason="NOT_AVAILABLE", detail="PLACEHOLDER detail")
        result = climatological_monthly_fractions(monthly_erosivity=months)
        assert isinstance(result, ResultMissing)
        assert result.reason == "MISSING_INPUT"
        assert "month 03" in result.detail
        assert "NOT_AVAILABLE" in result.detail


def test_negative_non_finite_or_zero_sum_months_are_not_computed():
    negative = dict(PLACEHOLDER_MONTHS)
    negative[5] = -1.0
    result = climatological_monthly_fractions(monthly_erosivity=negative)
    assert isinstance(result, ResultMissing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "month 05" in result.detail and "not clipped" in result.detail

    infinite = dict(PLACEHOLDER_MONTHS)
    infinite[7] = math.inf
    result = climatological_monthly_fractions(monthly_erosivity=infinite)
    assert isinstance(result, ResultMissing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "month 07" in result.detail

    zeros = {m: 0.0 for m in range(1, 13)}
    result = climatological_monthly_fractions(monthly_erosivity=zeros)
    assert isinstance(result, ResultMissing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "not split equally" in result.detail


def test_r_is_the_level_times_the_fraction_and_repeats_every_year():
    fractions = fractions_of_placeholder()
    table = climatological_r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
        fractions=fractions,
        ag_years=[2002, 2001],
        start_month=7,
    )
    assert not isinstance(table, ResultMissing)
    assert list(table) == [2001, 2002]
    first = list(table[2001])
    assert first[0] == (2001, 7) and first[-1] == (2002, 6)
    for ag_year, cells in table.items():
        assert len(cells) == 12
        for (_, month), value in cells.items():
            assert value == pytest.approx(month / 100, abs=ROUNDING)
        assert math.fsum(cells.values()) == pytest.approx(LEVEL, abs=1e-9)
    assert [table[2001][(2001, m)] for m in range(7, 13)] == [
        table[2002][(2002, m)] for m in range(7, 13)
    ]


def test_r_with_a_missing_or_foreign_level_or_missing_fractions():
    fractions = fractions_of_placeholder()
    for shape in (InputMissing, ResultMissing):
        result = climatological_r_by_year_and_month(
            mean_annual_r=shape(reason="NOT_AVAILABLE"),
            mean_annual_r_unit=R_UNIT,
            fractions=fractions,
            ag_years=[2001],
            start_month=1,
        )
        assert isinstance(result, ResultMissing)
        assert result.reason == "MISSING_INPUT" and "mean_annual_r" in result.detail

    result = climatological_r_by_year_and_month(
        mean_annual_r=math.nan,
        mean_annual_r_unit=R_UNIT,
        fractions=fractions,
        ag_years=[2001],
        start_month=1,
    )
    assert isinstance(result, ResultMissing) and result.reason == "NOT_COMPUTABLE"

    result = climatological_r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit="PLACEHOLDER unit",
        fractions=fractions,
        ag_years=[2001],
        start_month=1,
    )
    assert isinstance(result, ResultMissing)
    assert result.reason == REASON_UNIT_NOT_ACCEPTED

    result = climatological_r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
        fractions=ResultMissing(reason="NOT_AVAILABLE", detail="PLACEHOLDER detail"),
        ag_years=[2001],
        start_month=1,
    )
    assert isinstance(result, ResultMissing)
    assert result.reason == "MISSING_INPUT" and "fractions" in result.detail

    partial = dict(fractions)
    partial[2] = ResultMissing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER detail")
    table = climatological_r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
        fractions=partial,
        ag_years=[2001],
        start_month=1,
    )
    assert not isinstance(table, ResultMissing)
    missing = table[2001][(2001, 2)]
    assert isinstance(missing, ResultMissing)
    assert missing.reason == "MISSING_INPUT" and "month 02" in missing.detail
    assert table[2001][(2001, 3)] == pytest.approx(0.03, abs=ROUNDING)


def test_the_table_of_r_has_the_shape_of_the_daily_index_route():
    # The daily-index route on a hand-made monthly table of two whole years.
    monthly = {(year, m): float(m) for year in (2001, 2002) for m in range(1, 13)}
    index_fractions = monthly_fractions(monthly=monthly, start_month=1)
    ratios = yearly_ratios(annual={2001: 1.0, 2002: 1.0})
    daily_route = r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
        monthly_fractions=index_fractions,
        yearly_ratios=ratios,
    )
    climatological = climatological_r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
        fractions=fractions_of_placeholder(),
        ag_years=[2001, 2002],
        start_month=1,
    )
    assert not isinstance(daily_route, ResultMissing)
    assert not isinstance(climatological, ResultMissing)
    assert list(daily_route) == list(climatological)
    for ag_year in daily_route:
        assert list(daily_route[ag_year]) == list(climatological[ag_year])
    assert monthly_sums is not None  # same package, imported from one place


def test_climatology_defects_of_the_caller_raise():
    for function in (
        climatological_monthly_fractions,
        climatological_r_by_year_and_month,
    ):
        for parameter in inspect.signature(function).parameters.values():
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, (
                function,
                parameter,
            )
            assert parameter.default is inspect.Parameter.empty, (function, parameter)

    eleven = {m: float(m) for m in range(1, 12)}
    with pytest.raises(ValueError, match="twelve"):
        climatological_monthly_fractions(monthly_erosivity=eleven)
    thirteen = dict(PLACEHOLDER_MONTHS)
    thirteen[13] = 1.0
    with pytest.raises(ValueError, match="twelve"):
        climatological_monthly_fractions(monthly_erosivity=thirteen)
    with pytest.raises(TypeError, match="monthly_erosivity"):
        climatological_monthly_fractions(monthly_erosivity=[1.0] * 12)
    for bad in (None, "1.0", True):
        months = dict(PLACEHOLDER_MONTHS)
        months[1] = bad
        with pytest.raises(TypeError, match="month 01"):
            climatological_monthly_fractions(monthly_erosivity=months)

    fractions = fractions_of_placeholder()
    for bad in (None, "780", True):
        with pytest.raises(TypeError, match="mean_annual_r"):
            climatological_r_by_year_and_month(
                mean_annual_r=bad,
                mean_annual_r_unit=R_UNIT,
                fractions=fractions,
                ag_years=[2001],
                start_month=1,
            )
    with pytest.raises(TypeError, match="ag_years"):
        climatological_r_by_year_and_month(
            mean_annual_r=LEVEL,
            mean_annual_r_unit=R_UNIT,
            fractions=fractions,
            ag_years=["2001"],
            start_month=1,
        )
    with pytest.raises(TypeError, match="fractions"):
        climatological_r_by_year_and_month(
            mean_annual_r=LEVEL,
            mean_annual_r_unit=R_UNIT,
            fractions={1: 1.0},
            ag_years=[2001],
            start_month=1,
        )
    with pytest.raises(ValueError, match="start_month"):
        climatological_r_by_year_and_month(
            mean_annual_r=LEVEL,
            mean_annual_r_unit=R_UNIT,
            fractions=fractions,
            ag_years=[2001],
            start_month=13,
        )


def test_climatology_module_holds_no_number_but_calendar_ones():
    tree = ast.parse(Path(climatology.__file__).read_text(encoding="utf-8"))
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1, 2, 12}, numbers


def test_readme_lists_the_cases_of_test_climatology():
    text = README.read_text(encoding="utf-8")
    match = re.search(
        r"^## Climatological monthly fraction \(D69\)\n(.*?)(?=^## |\Z)",
        text,
        flags=re.M | re.S,
    )
    assert match, "README.md has no section 'Climatological monthly fraction (D69)'"
    listed = set(re.findall(r"`(test_[a-z0-9_]+)`", match.group(1)))
    defined = {
        name
        for name, item in globals().items()
        if name.startswith("test_") and callable(item)
    }
    assert listed == defined
