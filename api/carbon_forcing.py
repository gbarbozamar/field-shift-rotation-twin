"""The producer of ``CarbonForcing`` (contracts/carbon_forcing/, producer L2a). PROPOSED.

``build_carbon_forcing(calendar, climate, soil_slope)`` builds the one forcing
of one rotation from what the runner already holds: the ``RotationCalendar``
of EP2, the ``SiteClimate`` and the ``SiteSoilSlope``. The runner gives it to
EP5 ``engine.amg.run_amg`` (and, once it exists, to EP6).

It computes nothing scientific. It aggregates no series, converts no unit,
fills no gap and never writes a number of its own: the only numbers it can
carry are soil properties copied unchanged from ``SiteSoilSlope``. Every
quantity whose definition, aggregation or source is not decided is written
missing with its reason, never zero (C3.1). The identifiers of the quantities
are those ``engine/amg/entry.py`` reads (``FORCING_QUANTITIES``, PROPOSED
there); they are written here as text, because this module never imports
``engine/``. ``api/test_carbon_forcing.py`` checks them against the engine
when it is importable.

What each part gets is the table "The producer of CarbonForcing" of
api/README.md. Every choice there is PROPOSED (blueprint section 3.7).

When the horizon cannot be laid out (the calendar has no start month, the
climate document has no daily series, or the record holds no whole
agricultural year), no forcing is built: the function returns the results
``Missing`` with its reason, and the runner does not call EP5.

Pure: no file, no network, no clock; no argument is changed.
"""

from __future__ import annotations

import datetime as dt
import re

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
SOIL_PROPERTIES: tuple[str, ...] = ("clay_content", "carbonate_content", "ph")
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
MEAN_TEMPERATURE_OPEN = (
    "the yearly aggregation of the daily mean air temperature (derived by the "
    "engine from the daily maximum and minimum, D30 of #77) is not decided "
    "(contracts/carbon_forcing/README.md, OPEN 7)"
)
WATER_BALANCE_OPEN = (
    "the quantity water_balance is not defined (asked on #18; "
    "engine/amg/README.md OPEN 4)"
)
CARBON_INPUTS_OPEN = "the residue ledger (EP4, engine/residues/) is not built"
SOIL_PROPERTY_OPEN = (
    "no source of this soil property is decided (asked on #18): site data: "
    "soil and slope carries no item with this quantity"
)
STARTING_CARBON_OPEN = (
    "no value or source of the starting soil organic carbon is decided (asked on #18)"
)

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
    ``origin``; one that is not is left out, never renamed (PROPOSED).
    """
    origins: list[str] = []
    for component in calendar.components:
        crop = component.crop_id
        if _IDENTIFIER.match(crop) and crop not in origins:
            origins.append(crop)
    return origins


def _soil_property(soil_slope: SiteSoilSlope, quantity: str) -> SoilProperty:
    for item in soil_slope.soil_properties:
        if item.quantity == quantity:
            return item  # unchanged: never converted, never renamed
    return SoilProperty(
        quantity=quantity,
        value=None,
        unit=UNIT_OPEN,
        missing=_missing("NOT_AVAILABLE", SOIL_PROPERTY_OPEN),
    )


# --- the producer ---------------------------------------------------------------------


def build_carbon_forcing(
    calendar: RotationCalendar, climate: SiteClimate, soil_slope: SiteSoilSlope
) -> CarbonForcing | ResultsMissing:
    """The ``CarbonForcing`` of one rotation, or why it cannot be laid out.

    The caller has already checked that climate and soil and slope carry the
    calendar's ``case_id`` and ``field_id`` (D14).
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

    carbon_inputs_missing = _missing("NOT_AVAILABLE", CARBON_INPUTS_OPEN)
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
            AnnualSeries(
                **_all_missing(
                    MEAN_TEMPERATURE,
                    UNIT_OPEN,
                    years,
                    _missing("NOT_AVAILABLE", MEAN_TEMPERATURE_OPEN),
                )
            ),
            AnnualSeries(
                **_all_missing(
                    WATER_BALANCE,
                    UNIT_OPEN,
                    years,
                    _missing("NOT_AVAILABLE", WATER_BALANCE_OPEN),
                )
            ),
        ],
        annual_carbon_inputs=[
            AnnualCarbonInputSeries(
                origin=origin,
                **_all_missing(origin, STOCK_UNIT, years, carbon_inputs_missing),
            )
            for origin in crop_origins(calendar)
        ],
        soil_properties=[
            _soil_property(soil_slope, quantity) for quantity in SOIL_PROPERTIES
        ],
        soil_cover=[],
        starting_state=[
            StartingStateValue(
                quantity=STARTING_CARBON,
                value=None,
                unit=STOCK_UNIT,
                missing=_missing("NOT_AVAILABLE", STARTING_CARBON_OPEN),
            )
        ],
    )
