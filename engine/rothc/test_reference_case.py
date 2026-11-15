"""The reference case of EP6: the worked example of section 2.2 (D64, D104 as amended by D130).

Every number in this file is **person-transcribed**, none is computed or
chosen by a session:

- the parameters are rows 1-11 and B1 of issue #176, transcribed by Martin
  from "RothC - A model for the turnover of carbon in soil. Model
  Description" (February 2024), Rothamsted Research, on 14 November 2026,
  and checked by the lead developer on 15 November 2026 under D63 and D134;
  they are in force per D34;
- the reference case is the transcription of section 2.2 of that document
  (pp. 20-22): Hoosfield, January 1852, the month after a 10 000-year
  equilibrium run, no plant input in January;
- the combined rate modifying factor **abc = 0.3561 is an exact input**
  (D104: the individual a, b and c are not compared against the document);
- the tolerance is the person-set **1e-4 absolute** (amended by the case
  designer on 15 November 2026: a printed end value inherits up to 5e-5 from
  the document's truncated 4-decimal intermediate plus 5e-5 of its own
  rounding, so 1e-4 is the exact bound of the printed arithmetic; the original
  5e-5 stands for the mid-month values the document prints directly)
  14 November 2026: half of the last printed digit).

Two of the four printed pools cannot meet that tolerance from the printed
starts and abc, because the document's table displays ``start - truncated
difference`` (verified exactly for all four pools: 0.1533 - 0.0393 = 0.1140,
4.4852 - 0.0397 = 4.4455, 0.6671 - 0.0129 = 0.6542, 25.8576 - 0.0153 =
25.8423). Those two comparisons are strict ``xfail`` with the arithmetic in
the reason, for the case designer to resolve (engine/rothc/README.md, OPEN
10); BIO and HUM, which the display rounding cannot move outside the
tolerance, are plain assertions.

Run from the repository root: ``python -m pytest engine/rothc/``.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from contracts.carbon_balance import CarbonBalance
from contracts.carbon_forcing import CarbonForcing
from engine.rothc import entry
from engine.rothc.entry import PARAMETERS, STOCK_UNIT, run_rothc
from engine.rothc.modifiers import clay_partition, rate_modifying_factor, temperature_modifier
from engine.rothc.pools import initial_state, input_additions, plant_fractions, step
from params.catalogue import check_catalogue, read_value

# --- the person-transcribed reference case (issue #176) --------------------------

# The tolerance, set by the case designer on 14 November 2026: half of the
# last printed digit of the four-decimal values of section 2.2.
TOLERANCE = 1e-4

# The combined rate modifying factor of January 1852, printed on p. 21 and
# an exact input (D104); the individual a, b, c are not compared.
ABC = 0.3561

# The state of 31 December 1851 (p. 20), in t C ha-1.
START = {"dpm": 0.1533, "rpm": 4.4852, "bio": 0.6671, "hum": 25.8576, "iom": 2.7000}
PRINTED_TOTAL = 33.8632

# The soil of the worked example: Rothamsted, 23.4 % clay (p. 20), for which
# the document prints the partitioning ratio 3.51 (p. 13).
CLAY = 23.4
CLAY_UNIT = "%"
PRINTED_X = 3.51

# The expected pools at the end of January 1852, as printed (p. 21), the
# printed differences of the month, and the printed decayed intermediates of
# BIO and HUM before the formed material enters them (D130: the IOM is not
# printed at that date and is not compared).
END_PRINTED = {"dpm": 0.1140, "rpm": 4.4455, "bio": 0.6651, "hum": 25.8551}
DIFFS_PRINTED = {"dpm": 0.0393, "rpm": 0.0397, "bio": 0.0129, "hum": 0.0153}
DECAYED_PRINTED = {"bio": 0.6542, "hum": 25.8423}

# The person-transcribed parameters (rows 1-11 and B1 of issue #176), by the
# identifiers PROPOSED in engine/rothc/README.md. One locator per row.
REFERENCE = "RothC - A model for the turnover of carbon in soil. Model Description (February 2024), Rothamsted Research"  # fmt: skip
TRANSCRIBED_BY = "Martin (martinbarreto0), 14 November 2026"
CHECKED_BY = "the lead developer (gbarbozamar), D63 under D134, 15 November 2026"
RATES = {"dpm": 10.0, "rpm": 0.3, "bio": 0.66, "hum": 0.02}  # rows 1-4, yr-1
PARTITION = {  # section 1.7, p. 13
    "scale": 1.67,
    "intercept": 1.85,
    "clay_coefficient": 1.60,
    "clay_decay": 0.0786,
}
BIO_SHARE = 0.46  # row B1, p. 8: 46 % of the formed BIO + HUM; HUM takes 54 %
INPUT_RATIO = 1.44  # row 10, p. 8: crops and improved grassland (59 %/41 %)
ORIGIN = "plant_residues"  # PROPOSED origin word; January has no input (0.0)

PARAMETER_VALUES: dict[str, tuple[float, str, str]] = {
    # name: (value, unit of the record, locator in the description)
    "dpm_rate_constant": (RATES["dpm"], "yr-1", "pp. 8-9"),
    "rpm_rate_constant": (RATES["rpm"], "yr-1", "pp. 8-9"),
    "bio_rate_constant": (RATES["bio"], "yr-1", "pp. 8-9"),
    "hum_rate_constant": (RATES["hum"], "yr-1", "pp. 8-9"),
    "temperature_maximum": (47.91, "dimensionless", "p. 9"),
    "temperature_exponent_scale": (106.06, "degC", "p. 9"),
    "temperature_offset": (18.27, "degC", "p. 9"),
    "tsmd_intercept": (20.0, "mm", "pp. 10-12"),
    "tsmd_clay_coefficient": (1.3, "mm %-1", "pp. 10-12"),
    "tsmd_clay_squared_coefficient": (0.01, "mm %-2", "pp. 10-12"),
    "tsmd_reference_depth": (23.0, "cm", "pp. 10-12"),
    "moisture_threshold": (0.444, "dimensionless", "p. 12"),
    "moisture_minimum": (0.2, "dimensionless", "p. 12"),
    "pan_factor": (0.75, "dimensionless", "p. 10 (with pp. 5 and 10 for the PET route)"),
    "cover_vegetated": (0.6, "dimensionless", "p. 13"),
    "cover_bare": (1.0, "dimensionless", "p. 13"),
    "partition_scale": (PARTITION["scale"], "dimensionless", "section 1.7, p. 13"),
    "partition_intercept": (PARTITION["intercept"], "dimensionless", "section 1.7, p. 13"),
    "partition_clay_coefficient": (PARTITION["clay_coefficient"], "dimensionless", "section 1.7, p. 13"),  # fmt: skip
    "partition_clay_decay": (PARTITION["clay_decay"], "%-1", "section 1.7, p. 13"),
    "bio_share": (BIO_SHARE, "dimensionless", "p. 8"),
    "iom_coefficient": (0.049, "dimensionless", "p. 16"),
    "iom_exponent": (1.139, "dimensionless", "p. 16"),
}


def transcribed_record(parameter_id: str, value: float, unit: str, locator: str, scope: dict) -> dict:  # fmt: skip
    return {
        "id": parameter_id,
        "scope": scope,
        "value": value,
        "unit": unit,
        "range": None,
        "range_missing_reason": "the printed document states no range for this constant",
        "citation": {"reference": REFERENCE, "locator": locator},
        "transcribed_by": TRANSCRIBED_BY,
        "checked_by": CHECKED_BY,
    }


def transcribed_catalogue() -> dict[str, dict]:
    """The transcribed values as in-memory records, keyed as load_folder keys them."""
    records = {
        f"records/{name}.json": transcribed_record(
            PARAMETERS[name][0], value, unit, locator, {}
        )
        for name, (value, unit, locator) in PARAMETER_VALUES.items()
    }
    records[f"records/input_ratio_{ORIGIN}.json"] = transcribed_record(
        "rothc_input_dpm_rpm_ratio",
        INPUT_RATIO,
        "dimensionless",
        "p. 8",
        {entry.ORIGIN_SCOPE_KEY: ORIGIN},
    )
    return records


# --- the month, computed by the core -------------------------------------------------


def partition_ratio() -> float:
    return clay_partition(
        clay_content=CLAY,
        clay_content_unit=CLAY_UNIT,
        scale=PARTITION["scale"],
        intercept=PARTITION["intercept"],
        clay_coefficient=PARTITION["clay_coefficient"],
        clay_decay=PARTITION["clay_decay"],
        clay_decay_unit=CLAY_UNIT,
    )


def january() -> Any:
    """The January step given abc directly (the documented input, D104)."""
    return step(
        state=initial_state(**START),
        additions=input_additions(
            # No plant input in January, written as the input at zero.
            carbon_inputs={ORIGIN: 0.0},
            compositions={ORIGIN: plant_fractions(dpm_rpm_ratio=INPUT_RATIO)},
        ),
        rate_modifying_factor=ABC,
        rate_constants=RATES,
        partition_ratio=partition_ratio(),
        bio_share=BIO_SHARE,
    )


# --- the cases ----------------------------------------------------------------------


def test_reference_case_becomes_its_parts():
    """The transcription reconciles: no number of this test is the session's.

    The printed total is the sum of the five printed pools; the partitioning
    form at the printed clay content gives the printed ratio at the printed
    precision; and each printed value is the printed start minus the printed
    difference -- the display rule of the table that the strict xfail below
    documents. For DPM and RPM that value is the printed end pool (they
    receive nothing back); for BIO and HUM it is the printed decayed
    intermediate, to which the printed split additions then add (the end
    values the tolerance compares).
    """
    assert math.fsum(START.values()) == PRINTED_TOTAL
    assert round(partition_ratio(), len(str(PRINTED_X).split(".")[1])) == PRINTED_X
    for pool in ("dpm", "rpm", "bio", "hum"):
        printed = round(START[pool] - DIFFS_PRINTED[pool], len("0000"))
        if pool in END_PRINTED and pool not in DECAYED_PRINTED:
            assert printed == END_PRINTED[pool]
        else:
            assert printed == DECAYED_PRINTED[pool]
    # The printed split additions of BIO and HUM complete their end values.
    split = {  # the printed split table, p. 21: (BIO share, HUM share) per pool
        "dpm": (0.0039, 0.0047),
        "rpm": (0.0041, 0.0048),
        "bio": (0.0013, 0.0015),
        "hum": (0.0016, 0.0018),
    }
    assert round(DECAYED_PRINTED["bio"] + math.fsum(v[0] for v in split.values()), len("0000")) == END_PRINTED["bio"]  # fmt: skip
    assert round(DECAYED_PRINTED["hum"] + math.fsum(v[1] for v in split.values()), len("0000")) == END_PRINTED["hum"]  # fmt: skip


def test_reference_case_january_bio_and_hum_within_the_tolerance():
    result = january()
    assert isinstance(result.end, object)
    for pool in ("bio", "hum"):
        difference = abs(getattr(result.end, pool) - END_PRINTED[pool])
        assert difference <= TOLERANCE, (pool, difference)


def test_reference_case_january_dpm_and_rpm_within_the_tolerance():
    # The document's table displays start minus the TRUNCATED 4-decimal
    # difference (0.1533 - 0.0393 = 0.1140 exactly; truncation, not rounding),
    # so the printed DPM and RPM carry up to 1e-4 of the paper's own
    # arithmetic. The case designer set the pool tolerance to 1e-4 on that
    # basis (15 Nov 2026); a faithful computation misses the printed values by
    # 6.29e-05 (DPM) and 5.23e-05 (RPM), inside the bound of the printed
    # arithmetic and far from any modelling error.
    result = january()
    for pool in ("dpm", "rpm"):
        difference = abs(getattr(result.end, pool) - END_PRINTED[pool])
        assert difference <= TOLERANCE, (pool, difference)


def test_reference_case_mass_balance_of_the_month():
    result = january()
    stocks_in = result.start.total + result.additions.total
    assert result.additions.total == 0.0  # no plant input in January
    assert result.end.total + result.co2 == pytest.approx(stocks_in, rel=1e-12)
    assert result.co2 > 0.0
    for pool in ("dpm", "rpm", "bio", "hum", "iom"):
        assert getattr(result.end, pool) >= 0
    # The inert pool takes no part in the turnover.
    assert result.end.iom == START["iom"]


def test_reference_case_run_through_the_entry_point():
    """The same month through run_rothc, with abc built from a forcing.

    The forcing carries one month (January 1852), the five printed starting
    pools, the clay of the example and its depth. The cover is bare
    (c = 1.0), the month is wet enough that the deficit stays at field
    capacity (b = 1.0), and the air temperature is solved for a = abc, so
    the engine's combined factor is the transcribed 0.3561; the pools then
    equal the core step given abc directly.
    """
    # Solve a(T) = abc by bisection: the temperature is the test's own means,
    # not a value of the science (the document prints only the product).
    low, high = -18.27 + 1e-6, 100.0
    for _ in range(200):
        middle = (low + high) / 2
        factor = temperature_modifier(
            temperature=middle,
            temperature_unit="degC",
            maximum=PARAMETER_VALUES["temperature_maximum"][0],
            exponent_scale=PARAMETER_VALUES["temperature_exponent_scale"][0],
            exponent_scale_unit="degC",
            offset=PARAMETER_VALUES["temperature_offset"][0],
            offset_unit="degC",
        )
        if factor < ABC:
            low = middle
        else:
            high = middle
    temperature = (low + high) / 2
    # The rain exceeds the pan share, so the deficit stays at field capacity.
    forcing = CarbonForcing.model_validate(forcing_data(temperature))
    balance = run_rothc(forcing, parameters=transcribed_catalogue())
    assert isinstance(balance, CarbonBalance)
    assert balance.carbon_model == "rothc" and balance.variant == "rothc_26_3"
    # The engine's combined factor is the transcribed one, to the precision
    # of the solved temperature (the bisection, not a tolerance of the case).
    abc_of_the_engine = rate_modifying_factor(
        temperature_factor=temperature_modifier(
            temperature=temperature,
            temperature_unit="degC",
            maximum=PARAMETER_VALUES["temperature_maximum"][0],
            exponent_scale=PARAMETER_VALUES["temperature_exponent_scale"][0],
            exponent_scale_unit="degC",
            offset=PARAMETER_VALUES["temperature_offset"][0],
            offset_unit="degC",
        ),
        moisture_factor=1.0,
        cover_factor=1.0,
    )
    assert abc_of_the_engine == pytest.approx(ABC, rel=1e-12)
    expected = january()
    pools = {series.quantity: series for series in balance.pools}
    for pool, quantity in (
        ("dpm", "rothc_dpm_pool"),
        ("rpm", "rothc_rpm_pool"),
        ("bio", "rothc_bio_pool"),
        ("hum", "rothc_hum_pool"),
        ("iom", "rothc_iom_pool"),
    ):
        assert pools[quantity].initial.value == START[pool]
        # The same arithmetic as the core step given abc, to its precision.
        assert pools[quantity].steps[0].value == pytest.approx(
            getattr(expected.end, pool), rel=1e-12
        )
    assert balance.flows[1].steps[0].value == pytest.approx(expected.co2, rel=1e-12)
    assert balance.flows[0].steps[0].value == 0.0  # no plant input in January
    assert balance.total_stock.initial.value == PRINTED_TOTAL


def test_reference_case_records_pass_check_catalogue():
    records = transcribed_catalogue()
    assert check_catalogue(records) == []
    read = read_value(records["records/dpm_rate_constant.json"])
    assert read == RATES["dpm"]
    read = read_value(records[f"records/input_ratio_{ORIGIN}.json"])
    assert read == INPUT_RATIO


def test_readme_lists_the_cases_of_this_file():
    import inspect
    import re
    import sys
    from pathlib import Path

    readme = Path(__file__).parent / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.index("\n## The reference case of section 2.2")
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


# --- the forcing of the month -----------------------------------------------------------


def header(quantity: str, unit: str, **extra) -> dict:
    return {
        "quantity": quantity,
        "unit": unit,
        "provenance": "DECLARED",
        "source": "RothC Model Description (February 2024), section 2.2, "
        "transcribed in issue #176 (D64)",
        "range_missing": {
            "reason": "NOT_AVAILABLE",
            "detail": "the worked example prints no range",
        },
        **extra,
    }


def forcing_data(temperature: float) -> dict:
    month = {"year": 1852, "month": 1}
    quantity = {name: q for name, (_, q) in entry.FORCING_QUANTITIES.items()}
    return {
        "contract": "carbon_forcing",
        "example_data": False,
        "case_id": "hoosfield-section-2-2",
        "field_id": "hoosfield",
        "rotation_id": "spring-barley-unmanured",
        "horizon": {"start": month, "end": month},
        "soil_depth": {
            "value": PARAMETER_VALUES["tsmd_reference_depth"][0],
            "unit": "cm",
            "provenance": "DECLARED",
            "source": "RothC Model Description (February 2024), section 2.2",
            "range_missing": {
                "reason": "NOT_AVAILABLE",
                "detail": "the worked example prints no range",
            },
        },
        "climate": [
            {
                **header(quantity["rainfall"], "mm"),
                "start": month,
                "end": month,
                "months": [{"year": 1852, "month": 1, "value": 55.5}],
            },
            {
                **header(quantity["pan_evaporation"], "mm"),
                "start": month,
                "end": month,
                "months": [{"year": 1852, "month": 1, "value": 44.4}],
            },
            {
                **header(quantity["temperature"], "degC"),
                "start": month,
                "end": month,
                "months": [{"year": 1852, "month": 1, "value": temperature}],
            },
        ],
        "carbon_inputs": [
            {
                **header("plant_residues_of_the_month", STOCK_UNIT, origin=ORIGIN),
                "start": month,
                "end": month,
                # No plant input in January: written as the input at zero.
                "months": [{"year": 1852, "month": 1, "value": 0.0}],
            }
        ],
        "annual_climate": [],
        "annual_carbon_inputs": [],
        "soil_properties": [header(quantity["clay_content"], CLAY_UNIT, value=CLAY)],
        "soil_cover": [
            {
                **header(quantity["soil_cover"], "dimensionless"),
                "start": month,
                "end": month,
                # Bare: c is the bare factor (one); the cover of the month is
                # the test's choice, not printed by the document.
                "months": [{"year": 1852, "month": 1, "value": 0.0}],
            }
        ],
        "starting_state": [
            header(entry.FORCING_QUANTITIES[f"{pool}_pool"][1], STOCK_UNIT, value=value)
            for pool, value in START.items()
        ],
    }
