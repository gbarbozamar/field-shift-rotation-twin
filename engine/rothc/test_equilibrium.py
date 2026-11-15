"""Acceptance test of the equilibrium initialisation, the bare-soil deficit and
the label of EP6 (unit l2/rothc-spinup-d218, issue #325; D218, D219, D223 and
D224 of issue #77).

Every number here is a PLACEHOLDER, plainly unreal with repeated digits, as in
``test_entry.py`` (whose forcing and catalogue builders this file reuses),
except in the long-run case, which reads the person-transcribed parameters of
``test_reference_case.py`` and drives them with a PLACEHOLDER twelve-month
cycle: the monthly climate and inputs of the Hoosfield example are not
transcribed. No expected value of the science is written: the pools are
compared with the starting total, with the core run a second time, or with a
long run of the same cycle.

Run from the repository root: ``python -m pytest engine/rothc/``.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

from engine.rothc import test_reference_case as reference
from engine.rothc.entry import (
    FORCING_QUANTITIES,
    LABEL,
    PARAMETERS,
    STOCK_UNIT,
    run_rothc,
)
from engine.rothc.equilibrium import cycle_fixed_point, equilibrium_state
from engine.rothc.modifiers import bare_soil_deficit
from engine.rothc.pools import InputSplit, MonthInput, PoolState, plant_fractions, run
from engine.rothc.test_entry import (
    MARK,
    catalogue,
    catalogue_with,
    every_value,
    forcing,
    forcing_data,
    series_header,
)
from contracts.results.models import Missing

HERE = Path(__file__).parent
README = HERE / "README.md"
TOTAL = 99.9  # PLACEHOLDER starting total, t C ha-1
POOLS = ("rothc_dpm_pool", "rothc_rpm_pool", "rothc_bio_pool", "rothc_hum_pool")


def total_only(data: dict | None = None) -> dict:
    """The forcing of ``test_entry.py`` whose starting state is the total alone."""
    data = forcing_data() if data is None else data
    data["starting_state"] = [
        {
            **series_header(FORCING_QUANTITIES["total_carbon"][1], STOCK_UNIT),
            "value": TOTAL,
            "provenance": "DECLARED",
        }
    ]
    return data


def pools_of(balance) -> dict:
    return {series.quantity: series for series in balance.pools}


# --- D218: the pools from equilibrium --------------------------------------------


def test_the_pools_from_equilibrium_hold_the_starting_total():
    balance = run_rothc(forcing(total_only()), parameters=catalogue())
    pools = pools_of(balance)
    initial = {quantity: pools[quantity].initial.value for quantity in pools}
    assert all(value is not None and value >= 0 for value in initial.values())
    assert sum(initial.values()) == pytest.approx(TOTAL, rel=1e-12)
    assert balance.total_stock.initial.value == pytest.approx(TOTAL, rel=1e-12)
    # The forward run goes on from there, month by month.
    assert all(step.value is not None for step in balance.total_stock.steps)


def test_the_pools_from_equilibrium_are_derived_and_say_so():
    pools = pools_of(run_rothc(forcing(total_only()), parameters=catalogue()))
    for quantity in POOLS:
        initial = pools[quantity].initial
        assert initial.provenance == "DERIVED", quantity
        assert (
            "D218" in initial.source and "not a claim about the soil" in initial.source
        )
        assert "eq. 5.1" in initial.source
    iom = pools["rothc_iom_pool"].initial
    assert iom.provenance == "DERIVED" and "p. 16" in iom.source


def test_the_equilibrium_is_the_state_the_scaled_cycle_returns_to():
    # PLACEHOLDER cycle of three months; the scaled additions are found from
    # the total, and one cycle from the result comes back to it.
    rates = {"dpm": 2.22, "rpm": 0.33, "bio": 0.44, "hum": 0.011}
    split = plant_fractions(dpm_rpm_ratio=1.55)
    months = [
        MonthInput(
            additions=InputSplit(
                dpm=split.dpm * amount, rpm=split.rpm * amount, bio=0.0, hum=0.0
            ),
            rate_modifying_factor=factor,
        )
        for amount, factor in ((1.11, 0.55), (0.0, 0.22), (2.22, 0.88))
    ]
    state = equilibrium_state(
        months=months,
        rate_constants=rates,
        partition_ratio=3.33,
        bio_share=0.44,
        total_organic_carbon=55.5,
        inert_organic_matter=5.55,
    )
    assert state.total == pytest.approx(55.5, rel=1e-12)
    assert state.iom == 5.55
    scale = (55.5 - 5.55) / sum(
        getattr(
            cycle_fixed_point(
                months=months,
                rate_constants=rates,
                partition_ratio=3.33,
                bio_share=0.44,
            ),
            pool,
        )
        for pool in ("dpm", "rpm", "bio", "hum")
    )
    scaled = [
        MonthInput(
            additions=InputSplit(
                dpm=m.additions.dpm * scale,
                rpm=m.additions.rpm * scale,
                bio=0.0,
                hum=0.0,
            ),
            rate_modifying_factor=m.rate_modifying_factor,
        )
        for m in months
    ]
    the_run = run(
        initial_state=state,
        months=scaled,
        rate_constants=rates,
        partition_ratio=3.33,
        bio_share=0.44,
    )
    end = the_run.steps[-1].end
    for pool in ("dpm", "rpm", "bio", "hum", "iom"):
        assert getattr(end, pool) == pytest.approx(getattr(state, pool), rel=1e-12)


def test_with_the_five_pools_given_nothing_changes():
    # The forcing of test_entry.py carries the five pools: they are taken as
    # given, DECLARED, and test_entry.py checks every month against the core.
    data = forcing_data()
    pools = pools_of(run_rothc(forcing(data), parameters=catalogue()))
    given = {item["quantity"]: item["value"] for item in data["starting_state"]}
    for quantity, series in pools.items():
        assert series.initial.value == given[quantity]
        assert series.initial.provenance == "DECLARED"
        assert "D218" not in series.initial.source


def test_a_missing_forcing_month_leaves_the_equilibrium_pools_missing():
    data = total_only()
    cover = data["soil_cover"][0]["months"][5]
    cover["value"] = None
    cover["missing"] = {"reason": "NO_COVERAGE", "detail": f"{MARK}: not observed"}
    balance = run_rothc(forcing(data), parameters=catalogue())
    pools = pools_of(balance)
    for quantity in POOLS:
        initial = pools[quantity].initial
        assert initial.value is None
        # The factor of the month is missing for want of its cover, so the
        # modifiers name the cover and repeat its reason.
        assert initial.missing.reason == "MISSING_INPUT"
        assert "NO_COVERAGE" in initial.missing.detail
        assert "nothing is filled" in initial.missing.detail
    assert all(step.value is None for step in balance.total_stock.steps)


def test_no_carbon_input_gives_no_equilibrium_with_the_reason():
    data = total_only()
    for series in data["carbon_inputs"]:
        for item in series["months"]:
            item["value"] = 0.0
    pools = pools_of(run_rothc(forcing(data), parameters=catalogue()))
    initial = pools["rothc_hum_pool"].initial
    assert initial.value is None and initial.missing.reason == "NOT_COMPUTABLE"
    assert "no active carbon" in initial.missing.detail


# --- D219: the analytic fixed point against the long run --------------------------


def test_the_fixed_point_equals_a_ten_thousand_year_run_on_the_reference_case():
    # The transcribed constants of the reference case (rate constants,
    # partitioning of 23.4 % clay, BIO share, the DPM:RPM ratio of crops);
    # a PLACEHOLDER cycle of twelve months of abc and plant input.
    split = plant_fractions(dpm_rpm_ratio=reference.INPUT_RATIO)
    factors = (0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.66, 0.55, 0.44, 0.33, 0.22)
    amounts = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.11, 0.0, 0.0, 0.0, 0.0, 0.0)
    months = [
        MonthInput(
            additions=InputSplit(
                dpm=split.dpm * amount, rpm=split.rpm * amount, bio=0.0, hum=0.0
            ),
            rate_modifying_factor=factor,
        )
        for factor, amount in zip(factors, amounts, strict=True)
    ]
    arguments = {
        "rate_constants": reference.RATES,
        "partition_ratio": reference.partition_ratio(),
        "bio_share": reference.BIO_SHARE,
    }
    fixed = cycle_fixed_point(months=months, **arguments)
    state = PoolState(dpm=0.0, rpm=0.0, bio=0.0, hum=0.0, iom=0.0)
    for _ in range(10_000):  # years, as p. 20 of the description prints
        state = run(initial_state=state, months=months, **arguments).steps[-1].end
    for pool in ("dpm", "rpm", "bio", "hum"):
        assert getattr(fixed, pool) == pytest.approx(getattr(state, pool), rel=1e-9)


def test_a_cycle_that_decomposes_nothing_has_no_fixed_point():
    months = [
        MonthInput(
            additions=InputSplit(dpm=1.11, rpm=0.0, bio=0.0, hum=0.0),
            rate_modifying_factor=0.0,
        )
    ]
    result = cycle_fixed_point(
        months=months,
        rate_constants={"dpm": 2.22, "rpm": 0.33, "bio": 0.44, "hum": 0.011},
        partition_ratio=3.33,
        bio_share=0.44,
    )
    assert result.reason == "NOT_COMPUTABLE" and "decomposes nothing" in result.detail


# --- D223: the bare-soil deficit --------------------------------------------------


def test_bare_soil_deficit_holds_a_bare_dry_month_at_the_limit():
    # PLACEHOLDER: maximum -22.2, divisor 2.22, so the bare limit is -10.0.
    common = {"maximum": -22.2, "divisor": 2.22}
    # Bare, drying past the limit: held at it.
    assert bare_soil_deficit(
        deficit_before=-1.11, advanced=-15.5, cover_state=0.0, **common
    ) == pytest.approx(-10.0)
    # Bare, already below the limit: held where it was.
    assert (
        bare_soil_deficit(
            deficit_before=-12.2, advanced=-15.5, cover_state=0.0, **common
        )
        == -12.2
    )
    # Bare, drying but not to the limit: as advanced.
    assert (
        bare_soil_deficit(
            deficit_before=-1.11, advanced=-3.33, cover_state=0.0, **common
        )
        == -3.33
    )


def test_bare_soil_deficit_is_off_on_a_covered_month():
    assert (
        bare_soil_deficit(
            deficit_before=-1.11,
            advanced=-15.5,
            maximum=-22.2,
            cover_state=1.0,
            divisor=2.22,
        )
        == -15.5
    )


def test_a_missing_divisor_record_is_named_where_a_bare_month_dries():
    balance = run_rothc(forcing(), parameters=catalogue_with("bare_tsmd_divisor", None))
    missing = [s.missing for s in balance.total_stock.steps if s.value is None]
    assert missing and missing[0].reason == "MISSING_INPUT"
    assert PARAMETERS["bare_tsmd_divisor"][0] in missing[0].detail
    # A bare month that wets the soil, or a covered month, does not need it.
    wetting = bare_soil_deficit(
        deficit_before=-15.5,
        advanced=-3.33,
        maximum=-22.2,
        cover_state=0.0,
        divisor=Missing(reason="MISSING_INPUT", detail=f"{MARK}: no record"),
    )
    assert wetting == -3.33
    data = forcing_data()
    for item in data["soil_cover"][0]["months"]:
        item["value"] = 1.0
    covered = run_rothc(
        forcing(data), parameters=catalogue_with("bare_tsmd_divisor", None)
    )
    assert all(step.value is not None for step in covered.total_stock.steps)


# --- D224: the label ----------------------------------------------------------------


@pytest.mark.parametrize(
    "data", [forcing_data, total_only], ids=["five pools", "total only"]
)
def test_the_label_comes_first_in_every_numeric_source(data):
    balance = run_rothc(forcing(data()), parameters=catalogue())
    assert balance.variant == "rothc_26_3"
    headers = [balance.total_stock, *balance.pools, *balance.flows]
    for series in headers:
        assert series.source.startswith(LABEL), series.quantity
    for where, item in every_value(balance):
        if getattr(item, "value", None) is not None and getattr(item, "source", None):
            assert item.source.startswith(LABEL), where
    for trend in balance.soil_carbon_trend:
        if trend.value is not None:
            assert trend.source.startswith(LABEL), trend.computation
        else:
            assert trend.source is None, trend.computation


def test_a_missing_value_carries_no_source():
    balance = run_rothc(forcing(total_only()), parameters={})
    for where, item in every_value(balance):
        assert item.value is None, where
        assert getattr(item, "source", None) is None, where
    for series in [balance.total_stock, *balance.pools, *balance.flows]:
        assert series.source is None, series.quantity


def test_readme_lists_the_cases_of_this_file():
    text = README.read_text(encoding="utf-8")
    start = text.index("\n## Equilibrium, bare soil and label: PROPOSED cases\n")
    end = text.find("\n## ", start + 1)
    section = text[start : end if end != -1 else len(text)]
    listed = set(re.findall(r"`(test_\w+)`", section))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written, sorted(listed ^ written)
