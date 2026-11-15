"""The producer of ``CarbonForcing`` (contracts/carbon_forcing/, producer L2a). PROPOSED.

``build_carbon_forcing(calendar, climate, soil_slope)`` builds the one forcing
of one rotation from what the runner already holds: the ``RotationCalendar``
of EP2, the ``SiteClimate`` and the ``SiteSoilSlope``. The runner gives it to
EP5 ``engine.amg.run_amg`` (and, once it exists, to EP6).

It converts no unit and fills no gap. The one value it computes is the one
a decision fixes: the yearly ``mean_temperature`` of D118 of #77, the
arithmetic mean over each agricultural year of the daily mean of D30 (from
the daily maximum and minimum). Soil properties and the starting carbon are
copied unchanged from ``SiteSoilSlope`` when present (D120, D121). Every
quantity whose definition, aggregation or source is not decided, or not yet
usable, is written missing with its reason, never zero (C3.1). The identifiers of the quantities
are those ``engine/amg/entry.py`` reads (``FORCING_QUANTITIES``, PROPOSED
there); they are written here as text, because this module never imports
``engine/``. ``api/test_carbon_forcing.py`` checks them against the engine
when it is importable.

What each part gets is the table "The producer of CarbonForcing" of
api/README.md. Every choice there is PROPOSED (blueprint section 3.7).

``annual_carbon_inputs`` are the series of the residue ledger (EP4) when the
runner has one, copied unchanged and never converted (D147 of issue #77: EP4
writes them in the unit ``run_amg`` requires); otherwise one all-missing
series per crop (D122). See ``carbon_input_series``.

When the horizon cannot be laid out (the calendar has no start month, the
climate document has no daily series, or the record holds no whole
agricultural year), no forcing is built: the function returns the results
``Missing`` with its reason, and the runner does not call EP5.

Pure: no file, no network, no clock; no argument is changed.
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from collections.abc import Sequence

from contracts.carbon_forcing import (
    AnnualCarbonInputSeries,
    AnnualSeries,
    AnnualValue,
    CarbonForcing,
    ForcingHorizon,
    StartingStateValue,
)
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import YearMonth
from contracts.inputs.site_soil_slope import SoilProperty
from contracts.results.models import UNIT_SOIL_CARBON_TREND
from contracts.results.models import Missing as ResultsMissing

# --- identifiers, as engine/amg/entry.py reads them (FORCING_QUANTITIES) -------

MEAN_TEMPERATURE = "mean_temperature"  # annual_climate
WATER_BALANCE = "water_balance"  # annual_climate
SOIL_CN_RATIO = "soil_cn_ratio"  # soil_properties (D193 of #77)
SOIL_PROPERTIES: tuple[str, ...] = (
    "clay_content",
    "carbonate_content",
    "ph",
    SOIL_CN_RATIO,
)
STARTING_CARBON = "soil_organic_carbon"  # starting_state

# --- units ----------------------------------------------------------------------

# A unit nobody has decided yet: the text ``OPEN``, as for slope in #167. The
# contract needs a unit string even for a missing value (C3.1).
UNIT_OPEN = "OPEN"
# The unit engine/amg/entry.py requires for the starting carbon and the carbon
# inputs (its ``STOCK_UNIT``, engine/amg/README.md "EP5 run_amg"): the unit of
# C1.5 without "per year". Derived here the same way, from the contract constant.
STOCK_UNIT = UNIT_SOIL_CARBON_TREND.removesuffix(" yr-1")

# --- the detail texts (PROPOSED; English for developers, never shown to users) --

SOIL_DEPTH_OPEN = (
    "the soil depth and its unit are OPEN (C1.6 of contracts/CONVENTIONS.md, "
    "for the science reviewers)"
)
WATER_BALANCE_OPEN = (
    "water_balance (D119 of #77: precipitation minus the FAO-56 reference "
    "evapotranspiration, each summed over the agricultural year) is not written: "
    "D119 waits for a science reviewer to check it against the AMG description, "
    "and no reference evapotranspiration series reaches the producer"
)
CARBON_INPUTS_OPEN = (
    "the residue ledger (EP4, engine/residues/) is not built (D122 of #77)"
)
SOIL_PROPERTY_OPEN = (
    "not read yet: D120 of #77 takes it from the soil profile of D112, read by "
    "a person with its page (D34); site data: soil and slope carries no item "
    "with this quantity"
)
SOIL_CN_RATIO_OPEN = (
    "not read yet: D193 of #77, which amends D120, takes the soil C:N ratio "
    "from the organic matter and the total nitrogen of one reference soil "
    "profile, read by a person with its page (D34); site data: soil and slope "
    "carries no item soil_cn_ratio"
)
STARTING_CARBON_OPEN = (
    "not read yet: D121 of #77 takes it from the soil profile of D112, read by a "
    "person with its page (D34); site data: soil and slope carries no item "
    "soil_organic_carbon"
)

# --- D118: the yearly mean of the daily mean temperature of D30 ------------------

# The two daily series D30 derives the daily mean from, by their identifiers in
# contracts/CLIMATE_QUANTITIES.md (CQ2, CQ3), never by position.
TEMPERATURE_MAX = "air_temperature_max_2m"
TEMPERATURE_MIN = "air_temperature_min_2m"

# The pattern of ``QuantityId`` of contracts/inputs/common.py, which ``origin``
# and ``quantity`` of a carbon-input series must follow.
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def _missing(reason: str, detail: str) -> InputMissing:
    return InputMissing(reason=reason, detail=detail)  # type: ignore[arg-type]


# --- the horizon ------------------------------------------------------------------


def record_period(climate: SiteClimate) -> tuple[dt.date, dt.date] | None:
    """The days every daily series of the record covers: latest start, earliest end.

    PROPOSED. ``None`` when the document has no daily series. The period is
    read from the document, never from a constant; the record of D29 is daily,
    so monthly series are not read. When the series share no day, the end is
    before the start and no agricultural year is whole.
    """
    if not climate.daily_series:
        return None
    return (
        max(series.start_date for series in climate.daily_series),
        min(series.end_date for series in climate.daily_series),
    )


def whole_ag_years(
    start_month: int, first_day: dt.date, last_day: dt.date
) -> tuple[int, int] | None:
    """First and last agricultural year that the days cover in full (C5.3, C5.5).

    An agricultural year is identified by the calendar year in which it begins
    and runs twelve months from ``start_month``. ``None`` when not one is whole.
    """
    first = first_day.year
    if dt.date(first, start_month, 1) < first_day:
        first += 1
    after = last_day + dt.timedelta(days=1)  # the day after the record
    last = (
        after.year if dt.date(after.year, start_month, 1) <= after else after.year - 1
    )
    last -= 1  # the year that ends on the day before ``after`` began a year earlier
    if last < first:
        return None
    return first, last


def horizon_of(start_month: int, years: tuple[int, int]) -> ForcingHorizon:
    """From the first month of the first year to the last month of the last one."""
    first, last = years
    if start_month == 1:
        end = YearMonth(year=last, month=12)
    else:
        end = YearMonth(year=last + 1, month=start_month - 1)
    return ForcingHorizon(start=YearMonth(year=first, month=start_month), end=end)


# --- the parts ----------------------------------------------------------------------


def _all_missing(
    quantity: str, unit: str, years: tuple[int, int], missing: InputMissing
) -> dict:
    """An annual series with every year missing: no provenance, source or range."""
    first, last = years
    return {
        "quantity": quantity,
        "unit": unit,
        "first_ag_year": first,
        "last_ag_year": last,
        "years": [
            AnnualValue(ag_year=year, value=None, missing=missing)
            for year in range(first, last + 1)
        ],
    }


def crop_origins(calendar: RotationCalendar) -> list[str]:
    """The crops of the calendar, once each, in the order they first appear.

    Only a ``crop_id`` that is a quantity identifier (``QuantityId``) can be an
    ``origin``; one that is not is left out, never renamed, and counted by
    ``crops_left_out`` (PROPOSED).
    """
    origins: list[str] = []
    for component in calendar.components:
        crop = component.crop_id
        if _IDENTIFIER.match(crop) and crop not in origins:
            origins.append(crop)
    return origins


def crops_left_out(calendar: RotationCalendar) -> list[str]:
    """The crops of the calendar that cannot be an ``origin``, once each.

    ``CarbonForcing`` has no field that could say so, so the runner notes their
    number in the detail of the ``amg`` module (PROPOSED).
    """
    left_out: list[str] = []
    for component in calendar.components:
        crop = component.crop_id
        if not _IDENTIFIER.match(crop) and crop not in left_out:
            left_out.append(crop)
    return left_out


def daily_mean_temperature(temperature_max: float, temperature_min: float) -> float:
    """D30: "mean from the daily maximum and minimum": the arithmetic mean of the two.

    The same form as ``mean_temperature`` of engine/water/et0/equations.py
    (PROPOSED there); written here because this module never imports ``engine/``.
    """
    return statistics.fmean([temperature_max, temperature_min])


def _annual_mean_temperature(
    climate: SiteClimate, start_month: int, years: tuple[int, int]
) -> AnnualSeries:
    """D118: the arithmetic mean over each agricultural year of the daily means of D30.

    A year with any day missing in either input series is missing with its
    reason (C3.3), never filled or partially averaged (C3.4). Two input
    units that differ: every year missing, nothing converted.
    """
    found = {series.quantity: series for series in climate.daily_series}
    absent = [q for q in (TEMPERATURE_MAX, TEMPERATURE_MIN) if q not in found]
    if absent:
        missing = _missing(
            "MISSING_INPUT",
            "mean_temperature (D118, D30) needs the daily series "
            + " and ".join(repr(q) for q in absent)
            + " of site data: climate, which it does not carry",
        )
        return AnnualSeries(**_all_missing(MEAN_TEMPERATURE, UNIT_OPEN, years, missing))
    high, low = found[TEMPERATURE_MAX], found[TEMPERATURE_MIN]
    if high.unit != low.unit:
        missing = _missing(
            "NOT_COMPUTABLE",
            f"mean_temperature (D118, D30): the daily series {TEMPERATURE_MAX!r} "
            f"and {TEMPERATURE_MIN!r} are in different units; nothing is converted",
        )
        return AnnualSeries(**_all_missing(MEAN_TEMPERATURE, UNIT_OPEN, years, missing))

    by_day = {
        name: {day.date: day for day in series.days}
        for name, series in ((TEMPERATURE_MAX, high), (TEMPERATURE_MIN, low))
    }
    items: list[AnnualValue] = []
    for year in range(years[0], years[1] + 1):
        first = dt.date(year, start_month, 1)
        after = dt.date(year + 1, start_month, 1)
        means: list[float] = []
        gap: InputMissing | None = None
        day = first
        while day < after and gap is None:
            pair = []
            for name in (TEMPERATURE_MAX, TEMPERATURE_MIN):
                item = by_day[name].get(day)
                if item is None:
                    gap = _missing(
                        "NO_COVERAGE",
                        f"mean_temperature (D118): {name!r} has no item for "
                        f"{day.isoformat()}",
                    )
                    break
                if item.value is None:
                    assert item.missing is not None
                    gap = _missing(
                        "MISSING_INPUT",
                        f"mean_temperature (D118): {name!r} is missing on "
                        f"{day.isoformat()}, reason {item.missing.reason}"
                        + (f" ({item.missing.detail})" if item.missing.detail else "")
                        + "; a year with a missing day is not filled (C3.3, C3.4)",
                    )
                    break
                pair.append(item.value)
            else:
                means.append(daily_mean_temperature(*pair))
            day += dt.timedelta(days=1)
        if gap is not None:
            items.append(AnnualValue(ag_year=year, value=None, missing=gap))
        else:
            items.append(AnnualValue(ag_year=year, value=statistics.fmean(means)))

    header: dict = {"quantity": MEAN_TEMPERATURE, "unit": high.unit}
    if any(item.value is not None for item in items):
        sources = "; ".join(
            f"{series.quantity}: {series.source}"
            for series in (high, low)
            if series.source is not None
        )
        reasons = {
            series.range_missing.reason
            for series in (high, low)
            if series.range_missing is not None
        }
        header.update(
            provenance="DERIVED",  # C4.3: a fixed formula of observed values
            source=(
                "derived by api.carbon_forcing: arithmetic mean over the "
                "agricultural year (D118 of #77) of the daily mean of "
                f"{TEMPERATURE_MAX} and {TEMPERATURE_MIN} (D30 of #77)"
                + (f"; input series: {sources}" if sources else "")
            ),
            assumption=high.assumption or low.assumption,
            range_missing=_missing(
                reasons.pop() if len(reasons) == 1 else "NOT_AVAILABLE",
                "the input series carry no range, and none is derived (C2.2)",
            ),
        )
    return AnnualSeries(
        **header,
        first_ag_year=years[0],
        last_ag_year=years[1],
        years=items,
    )


def _starting_carbon(soil_slope: SiteSoilSlope) -> StartingStateValue:
    """D121 (PROPOSED source): the soil item ``soil_organic_carbon`` in the stock unit.

    Copied unchanged only when its unit is the unit ``run_amg`` requires; a
    concentration, or any other unit, is never converted.
    """
    for item in soil_slope.soil_properties:
        if item.quantity != STARTING_CARBON:
            continue
        if item.unit == STOCK_UNIT:
            return StartingStateValue.model_validate(item.model_dump())
        return StartingStateValue(
            quantity=STARTING_CARBON,
            value=None,
            unit=STOCK_UNIT,
            missing=_missing(
                "NOT_COMPUTABLE",
                f"site data: soil and slope carries {STARTING_CARBON} in a unit "
                f"other than {STOCK_UNIT!r}; D121 of #77 converts nothing (a "
                "concentration would need a bulk density and a depth)",
            ),
        )
    return StartingStateValue(
        quantity=STARTING_CARBON,
        value=None,
        unit=STOCK_UNIT,
        missing=_missing("NOT_AVAILABLE", STARTING_CARBON_OPEN),
    )


def _soil_property(soil_slope: SiteSoilSlope, quantity: str) -> SoilProperty:
    for item in soil_slope.soil_properties:
        if item.quantity == quantity:
            return item  # unchanged: never converted, never renamed
    return SoilProperty(
        quantity=quantity,
        value=None,
        unit=UNIT_OPEN,
        missing=_missing(
            "NOT_AVAILABLE",
            SOIL_CN_RATIO_OPEN if quantity == SOIL_CN_RATIO else SOIL_PROPERTY_OPEN,
        ),
    )


# --- the producer ---------------------------------------------------------------------


def carbon_input_series(
    calendar: RotationCalendar,
    years: tuple[int, int],
    carbon_inputs: Sequence[AnnualCarbonInputSeries] | InputMissing | None,
) -> list[AnnualCarbonInputSeries]:
    """``annual_carbon_inputs`` of the forcing. PROPOSED.

    - ``None`` (EP4 not built): one series per crop, every year missing
      ``NOT_AVAILABLE`` with the D122 text, as before EP4 existed.
    - A ``Missing`` (the ``years_missing`` of a residue ledger without years):
      the same per-crop series, every year missing with that reason.
    - A sequence (the ``annual_carbon_inputs`` of a residue ledger): copied
      unchanged, the same objects in the same order. No unit is converted
      (D147: EP4 writes the unit ``run_amg`` requires). A series that is not an
      ``AnnualCarbonInputSeries``, or whose agricultural years are not those
      of the horizon, is a defect of the producer: ``TypeError``.
    """
    if carbon_inputs is None or isinstance(carbon_inputs, InputMissing):
        missing = (
            _missing("NOT_AVAILABLE", CARBON_INPUTS_OPEN)
            if carbon_inputs is None
            else carbon_inputs
        )
        return [
            AnnualCarbonInputSeries(
                origin=origin, **_all_missing(origin, STOCK_UNIT, years, missing)
            )
            for origin in crop_origins(calendar)
        ]
    if isinstance(carbon_inputs, str | bytes) or not isinstance(
        carbon_inputs, Sequence
    ):
        raise TypeError("carbon_inputs: expected a sequence of AnnualCarbonInputSeries")
    copied: list[AnnualCarbonInputSeries] = []
    for series in carbon_inputs:
        if not isinstance(series, AnnualCarbonInputSeries):
            raise TypeError(
                f"carbon_inputs: expected AnnualCarbonInputSeries, not "
                f"{type(series).__name__}"
            )
        if (series.first_ag_year, series.last_ag_year) != years:
            raise TypeError(
                "carbon_inputs: a series of the residue ledger does not run over "
                "the agricultural years of the forcing horizon"
            )
        copied.append(series)
    return copied


def build_carbon_forcing(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    carbon_inputs: Sequence[AnnualCarbonInputSeries] | InputMissing | None = None,
) -> CarbonForcing | ResultsMissing:
    """The ``CarbonForcing`` of one rotation, or why it cannot be laid out.

    The caller has already checked that climate and soil and slope carry the
    calendar's ``case_id`` and ``field_id`` (D14). ``carbon_inputs`` is what
    the residue ledger (EP4) gives for ``annual_carbon_inputs``, or ``None``
    when EP4 is not built (``carbon_input_series``).
    """
    for name, given, model in (
        ("calendar", calendar, RotationCalendar),
        ("climate", climate, SiteClimate),
        ("soil_slope", soil_slope, SiteSoilSlope),
    ):
        if not isinstance(given, model):
            raise TypeError(f"{name}: expected {model.__name__}")

    start = calendar.ag_year_start
    if start.month is None:
        assert start.missing is not None
        return ResultsMissing(
            reason="MISSING_INPUT",
            detail=(
                "the start month of the agricultural year (ag_year_start of the "
                f"calendar) is missing: {start.missing.reason}"
                + (f" ({start.missing.detail})" if start.missing.detail else "")
            ),
        )
    period = record_period(climate)
    if period is None:
        return ResultsMissing(
            reason="MISSING_INPUT",
            detail=(
                "the period of the climate record: site data: climate has no daily series"
            ),
        )
    years = whole_ag_years(start.month, *period)
    if years is None:
        return ResultsMissing(
            reason="NO_COVERAGE",
            detail=(
                f"the climate record from {period[0].isoformat()} to "
                f"{period[1].isoformat()} covers no whole agricultural year "
                f"starting in month {start.month} (C5.3, C5.5)"
            ),
        )

    annual_carbon_inputs = carbon_input_series(calendar, years, carbon_inputs)
    return CarbonForcing(
        contract="carbon_forcing",
        example_data=(
            calendar.example_data or climate.example_data or soil_slope.example_data
        ),
        case_id=calendar.case_id,
        field_id=calendar.field_id,
        rotation_id=calendar.rotation_id,
        horizon=horizon_of(start.month, years),
        soil_depth=Value(
            value=None,
            unit=UNIT_OPEN,
            missing=_missing("NOT_AVAILABLE", SOIL_DEPTH_OPEN),
        ),
        climate=[],
        carbon_inputs=[],
        annual_climate=[
            _annual_mean_temperature(climate, start.month, years),
            AnnualSeries(
                **_all_missing(
                    WATER_BALANCE,
                    UNIT_OPEN,
                    years,
                    _missing("NOT_AVAILABLE", WATER_BALANCE_OPEN),
                )
            ),
        ],
        annual_carbon_inputs=annual_carbon_inputs,
        soil_properties=[
            _soil_property(soil_slope, quantity) for quantity in SOIL_PROPERTIES
        ],
        soil_cover=[],
        starting_state=[_starting_carbon(soil_slope)],
    )
