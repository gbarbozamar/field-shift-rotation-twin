"""The producer of ``CarbonForcing`` (contracts/carbon_forcing/, producer L2a). PROPOSED.

``build_carbon_forcing(calendar, climate, soil_slope)`` builds the one forcing
of one rotation from what the runner already holds: the ``RotationCalendar``
of EP2, the ``SiteClimate`` and the ``SiteSoilSlope``, and the daily FAO-56
reference evapotranspiration of D44 that the runner computes
(``reference_evapotranspiration``). The runner gives it to EP5
``engine.amg.run_amg`` and EP6 ``engine.rothc.run_rothc``.

It converts no unit and fills no gap. The values it computes are those
decisions fix: the yearly ``mean_temperature`` of D118 of #77, the
arithmetic mean over each agricultural year of the daily mean of D30 (from
the daily maximum and minimum); and the monthly ``climate`` of RothC of D220:
``rainfall``, the sum over the calendar month of the daily ``precipitation``;
``potential_evapotranspiration``, the sum over the month of the daily
reference evapotranspiration, which stands in for the potential
evapotranspiration (D80); and ``mean_temperature``, the mean over the month
of the daily means of D30. A month with any day missing is missing with its
reason (C3.3, C3.4). The yearly ``water_balance`` of AMG is that of D181: the
sum over the agricultural year of the daily ``precipitation`` minus the sum of
the daily reference evapotranspiration, which stands in for the Penman (1948)
PET of the source, with no irrigation (IW = 0), in m; a year with any day
missing is missing with its reason. ``soil_depth`` is the 20 cm of D180. Soil properties and the starting carbon are
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
import math
import re
import statistics
from collections.abc import Callable, Mapping, Sequence

from contracts.carbon_forcing import (
    AnnualCarbonInputSeries,
    AnnualSeries,
    AnnualValue,
    CarbonForcing,
    CarbonInputSeries,
    ClimateSeries,
    ForcingHorizon,
    StartingStateValue,
)
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import DailySeries, MonthlyValue, YearMonth
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
# The monthly climate of RothC (D220), as engine/rothc/entry.py reads it
# (FORCING_QUANTITIES). No ``open_pan_evaporation`` series is written: EP6 then
# divides the potential evapotranspiration by the pan factor (D220).
RAINFALL = "rainfall"  # climate
POTENTIAL_EVAPOTRANSPIRATION = "potential_evapotranspiration"  # climate
# ``mean_temperature`` of the monthly climate is MEAN_TEMPERATURE, the same
# identifier as the yearly series of annual_climate, in another part.

# --- units ----------------------------------------------------------------------

# A unit nobody has decided yet: the text ``OPEN``, as for slope in #167. The
# contract needs a unit string even for a missing value (C3.1).
UNIT_OPEN = "OPEN"
# The unit engine/amg/entry.py requires for the starting carbon and the carbon
# inputs (its ``STOCK_UNIT``, engine/amg/README.md "EP5 run_amg"): the unit of
# C1.5 without "per year". Derived here the same way, from the contract constant.
STOCK_UNIT = UNIT_SOIL_CARBON_TREND.removesuffix(" yr-1")
# The daily depth of water of the precipitation series (CQ1 of
# contracts/CLIMATE_QUANTITIES.md) and of the FAO-56 reference
# evapotranspiration (eq. 6), and the depth of a month: a month's sum of daily
# depths, mm day-1 times days. A definition, not a value of the method.
DAILY_DEPTH_UNIT = "mm day-1"
MONTHLY_DEPTH_UNIT = "mm"

# --- D181: the annual water balance of AMG ----------------------------------------

# D181 of #77: "P + IW − ET0, each summed over the agricultural year, with ET0
# of FAO-56 (D44) declared as a substitute for the Penman (1948) PET; IW = 0
# (rainfed rotations); in m (mm / 1000)." IW = 0 adds nothing, so no
# irrigation term is read. The unit is the one D181 writes; engine/amg
# compares it with the unit of amg_moisture_sensitivity (``m-1``).
WATER_BALANCE_UNIT = "m"
# Millimetres in one metre, by the SI definition of the prefixes: the
# conversion D181 states ("mm / 1000"). A definition, not a value of the method.
MM_PER_M = 1000
# D181 of #77 quotes the range of P − PET over which the source calibrated AMG,
# "−290 to 595 mm yr-1 (p. 107)" (Clivot et al. 2019), and says that outside it
# the sensitivity is not known and is stated. The values of a decision, written
# as decided; they only label a year in the source text, never change its number.
D181_CALIBRATED_RANGE_MM = (-290.0, 595.0)

# --- D180: the soil depth --------------------------------------------------------

# D180 of #77: "`soil_depth` = 20 cm, the carbon benchmark depth of D71,
# written in `cm` because RothC compares it with the unit of
# `rothc_tsmd_reference_depth` (AMG copies it without using it)." The value
# of a decision, written as decided.
SOIL_DEPTH_D180 = 20.0
SOIL_DEPTH_UNIT = "cm"
SOIL_DEPTH_SOURCE = (
    "D180 of #77: the carbon benchmark depth of D71 (0-20 cm), written in cm "
    "because RothC compares it with the unit of rothc_tsmd_reference_depth"
)

# --- the detail texts (PROPOSED; English for developers, never shown to users) --

PET_NOT_PASSED = (
    "potential_evapotranspiration (D220 of #77) is the monthly sum of the daily "
    "FAO-56 reference evapotranspiration of D44, which the runner did not pass"
)
WATER_BALANCE_NO_ET0 = (
    "water_balance (D181 of #77: precipitation minus the FAO-56 reference "
    "evapotranspiration of D44, each summed over the agricultural year, in m) "
    "needs the daily reference evapotranspiration, which the runner did not pass"
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

# The daily series of CQ1 (D23), by identifier, never by position. Never the
# control series ``precipitation_reanalysis`` (CQ1b, D24).
PRECIPITATION = "precipitation"

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

    The same form as ``mean_temperature`` of the FAO-56 equations of lane L1
    (file ``equations.py`` of the ET0 package of the water engine, PROPOSED there);
    written here because this module never imports ``engine/``.
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


# --- D220: the monthly climate of RothC --------------------------------------------

# One day of a daily series: a number, or why it is missing.
DayValue = float | InputMissing
# What the runner passes as the daily reference evapotranspiration (see
# ``build_carbon_forcing``): a mapping, a single Missing, or None.
ReferenceEvapotranspiration = (
    Mapping[dt.date, float | InputMissing | ResultsMissing]
    | InputMissing
    | ResultsMissing
    | None
)


def _months(horizon: ForcingHorizon) -> list[tuple[int, int]]:
    """The calendar months of the horizon, in order."""
    months = []
    year, month = horizon.start.year, horizon.start.month
    while (year, month) <= (horizon.end.year, horizon.end.month):
        months.append((year, month))
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    return months


def _days_of(year: int, month: int) -> list[dt.date]:
    first = dt.date(year, month, 1)
    after = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return [first + dt.timedelta(days=n) for n in range((after - first).days)]


def _span(months: list[tuple[int, int]]) -> dict:
    return {
        "start": YearMonth(year=months[0][0], month=months[0][1]),
        "end": YearMonth(year=months[-1][0], month=months[-1][1]),
    }


def _by_month(
    quantity: str,
    unit: str,
    months: list[tuple[int, int]],
    by_day: Mapping[dt.date, DayValue],
    what: str,
    combine: Callable[[list[float]], float],
    header: dict,
) -> ClimateSeries:
    """One monthly series: ``combine`` over the days of each month, or why not.

    A day with no item is ``NO_COVERAGE`` and a day held missing keeps its
    reason; either makes its month missing, never filled or partly combined
    (C3.3, C3.4). The ``header`` (provenance, source, range_missing,
    assumption) is written only when at least one month holds a value.
    """
    items: list[MonthlyValue] = []
    for year, month in months:
        values: list[float] = []
        gap: InputMissing | None = None
        for day in _days_of(year, month):
            value = by_day.get(day)
            if value is None:
                gap = _missing(
                    "NO_COVERAGE",
                    f"{quantity} (D220): {what} has no item for {day.isoformat()}",
                )
                break
            if isinstance(value, InputMissing):
                gap = _missing(
                    value.reason,
                    f"{quantity} (D220): {what} is missing on {day.isoformat()}"
                    + (f" ({value.detail})" if value.detail else "")
                    + "; a month with a missing day is not filled (C3.3, C3.4)",
                )
                break
            values.append(value)
        if gap is not None:
            items.append(MonthlyValue(year=year, month=month, value=None, missing=gap))
        else:
            items.append(MonthlyValue(year=year, month=month, value=combine(values)))
    present = any(item.value is not None for item in items)
    return ClimateSeries(
        quantity=quantity,
        unit=unit,
        months=items,
        **_span(months),
        **(header if present else {}),
    )


def _every_month_missing(
    quantity: str, unit: str, months: list[tuple[int, int]], missing: InputMissing
) -> ClimateSeries:
    return ClimateSeries(
        quantity=quantity,
        unit=unit,
        months=[
            MonthlyValue(year=year, month=month, value=None, missing=missing)
            for year, month in months
        ],
        **_span(months),
    )


def _range_missing(series: Sequence[DailySeries]) -> InputMissing:
    reasons = {item.range_missing.reason for item in series if item.range_missing}
    return _missing(
        reasons.pop() if len(reasons) == 1 else "NOT_AVAILABLE",
        "the input series carry no range, and none is derived (C2.2)",
    )


def _daily_values(series: DailySeries) -> dict[dt.date, DayValue]:
    """The days of a daily series: the number, or why it is missing."""
    values: dict[dt.date, DayValue] = {}
    for day in series.days:
        if day.value is not None:
            values[day.date] = day.value
            continue
        assert day.missing is not None
        values[day.date] = _missing(
            day.missing.reason,
            f"{series.quantity!r} holds it missing, reason {day.missing.reason}"
            + (f": {day.missing.detail}" if day.missing.detail else ""),
        )
    return values


def _monthly_rainfall(
    climate: SiteClimate, months: list[tuple[int, int]]
) -> ClimateSeries:
    """D220: the sum over each calendar month of the daily ``precipitation``, in mm."""
    found = {series.quantity: series for series in climate.daily_series}
    series = found.get(PRECIPITATION)
    if series is None:
        return _every_month_missing(
            RAINFALL,
            MONTHLY_DEPTH_UNIT,
            months,
            _missing(
                "MISSING_INPUT",
                f"rainfall (D220) needs the daily series {PRECIPITATION!r} of site "
                "data: climate, which it does not carry",
            ),
        )
    if series.unit != DAILY_DEPTH_UNIT:
        return _every_month_missing(
            RAINFALL,
            MONTHLY_DEPTH_UNIT,
            months,
            _missing(
                "NOT_COMPUTABLE",
                f"rainfall (D220): the daily series {PRECIPITATION!r} is in "
                f"{series.unit!r}, not {DAILY_DEPTH_UNIT!r}; nothing is converted",
            ),
        )
    return _by_month(
        RAINFALL,
        MONTHLY_DEPTH_UNIT,
        months,
        _daily_values(series),
        f"the daily series {PRECIPITATION!r}",
        math.fsum,
        {
            "provenance": "DERIVED",
            "source": (
                "derived by api.carbon_forcing: sum over the calendar month (D220 "
                f"of #77) of the daily {PRECIPITATION} (CQ1, D23)"
                + (f"; input series: {series.source}" if series.source else "")
            ),
            "assumption": series.assumption,
            "range_missing": _range_missing([series]),
        },
    )


def _reference_evapotranspiration_by_day(
    reference_evapotranspiration: Mapping[
        dt.date, float | InputMissing | ResultsMissing
    ],
) -> dict[dt.date, DayValue]:
    """The days of the runner's daily reference evapotranspiration: the
    number, or why it is missing."""
    by_day: dict[dt.date, DayValue] = {}
    for day, value in reference_evapotranspiration.items():
        if isinstance(value, InputMissing | ResultsMissing):
            by_day[day] = _missing(
                value.reason,
                "the reference evapotranspiration of the day is missing"
                + (f": {value.detail}" if value.detail else ""),
            )
        else:
            by_day[day] = float(value)
    return by_day


def _monthly_potential_evapotranspiration(
    reference_evapotranspiration: ReferenceEvapotranspiration,
    months: list[tuple[int, int]],
) -> ClimateSeries:
    """D220: the sum over each calendar month of the daily FAO-56 reference
    evapotranspiration of D44, in mm, standing in for the potential
    evapotranspiration of RothC (D80)."""
    if reference_evapotranspiration is None:
        return _every_month_missing(
            POTENTIAL_EVAPOTRANSPIRATION,
            MONTHLY_DEPTH_UNIT,
            months,
            _missing("NOT_AVAILABLE", PET_NOT_PASSED),
        )
    if isinstance(reference_evapotranspiration, InputMissing | ResultsMissing):
        given = reference_evapotranspiration
        return _every_month_missing(
            POTENTIAL_EVAPOTRANSPIRATION,
            MONTHLY_DEPTH_UNIT,
            months,
            _missing(
                given.reason,
                "potential_evapotranspiration (D220): the daily FAO-56 reference "
                "evapotranspiration of D44 could not be computed"
                + (f": {given.detail}" if given.detail else ""),
            ),
        )
    return _by_month(
        POTENTIAL_EVAPOTRANSPIRATION,
        MONTHLY_DEPTH_UNIT,
        months,
        _reference_evapotranspiration_by_day(reference_evapotranspiration),
        "the daily FAO-56 reference evapotranspiration (D44)",
        math.fsum,
        {
            "provenance": "DERIVED",
            "source": (
                "derived by api.carbon_forcing: sum over the calendar month (D220 "
                "of #77) of the daily FAO-56 Penman-Monteith reference "
                "evapotranspiration of D44 (eq. 6), which stands in for the "
                "potential evapotranspiration of RothC (D80): an adaptation"
            ),
            "range_missing": _missing(
                "NOT_AVAILABLE",
                "no range is derived for the reference evapotranspiration (C2.2)",
            ),
        },
    )


def _monthly_mean_temperature(
    climate: SiteClimate, months: list[tuple[int, int]]
) -> ClimateSeries:
    """D220: the mean over each calendar month of the daily means of D30, in
    the unit of the daily series."""
    found = {series.quantity: series for series in climate.daily_series}
    absent = [q for q in (TEMPERATURE_MAX, TEMPERATURE_MIN) if q not in found]
    if absent:
        return _every_month_missing(
            MEAN_TEMPERATURE,
            UNIT_OPEN,
            months,
            _missing(
                "MISSING_INPUT",
                "mean_temperature (D220, D30) needs the daily series "
                + " and ".join(repr(q) for q in absent)
                + " of site data: climate, which it does not carry",
            ),
        )
    high, low = found[TEMPERATURE_MAX], found[TEMPERATURE_MIN]
    if high.unit != low.unit:
        return _every_month_missing(
            MEAN_TEMPERATURE,
            UNIT_OPEN,
            months,
            _missing(
                "NOT_COMPUTABLE",
                f"mean_temperature (D220, D30): the daily series {TEMPERATURE_MAX!r} "
                f"and {TEMPERATURE_MIN!r} are in different units; nothing is converted",
            ),
        )
    highs, lows = _daily_values(high), _daily_values(low)
    by_day: dict[dt.date, DayValue] = {}
    for day in highs.keys() & lows.keys():
        high_value, low_value = highs[day], lows[day]
        if isinstance(high_value, InputMissing):
            by_day[day] = high_value
        elif isinstance(low_value, InputMissing):
            by_day[day] = low_value
        else:
            by_day[day] = daily_mean_temperature(high_value, low_value)
    return _by_month(
        MEAN_TEMPERATURE,
        high.unit,
        months,
        by_day,
        f"the daily series {TEMPERATURE_MAX!r} and {TEMPERATURE_MIN!r}",
        statistics.fmean,
        {
            "provenance": "DERIVED",
            "source": (
                "derived by api.carbon_forcing: arithmetic mean over the calendar "
                "month (D220 of #77) of the daily mean of "
                f"{TEMPERATURE_MAX} and {TEMPERATURE_MIN} (D30 of #77)"
            ),
            "assumption": high.assumption or low.assumption,
            "range_missing": _range_missing([high, low]),
        },
    )


def _annual_water_balance(
    climate: SiteClimate,
    start_month: int,
    years: tuple[int, int],
    reference_evapotranspiration: ReferenceEvapotranspiration,
) -> AnnualSeries:
    """D181: (Σ daily precipitation − Σ daily FAO-56 ET0) / 1000 over each
    agricultural year, in m, with IW = 0.

    The precipitation is the daily series ``precipitation`` (CQ1, D23) that
    EP1 and EP3 read; the ET0 is the runner's daily FAO-56 reference
    evapotranspiration of D44. A year with a day absent from either is
    ``NO_COVERAGE``, a day held missing keeps its reason; the year is never
    filled or partly summed (C3.3, C3.4). A year outside the range of P − PET
    the source calibrated keeps its number; the source text names it.
    """

    def every_year(reason: str, detail: str) -> AnnualSeries:
        return AnnualSeries(
            **_all_missing(
                WATER_BALANCE, WATER_BALANCE_UNIT, years, _missing(reason, detail)
            )
        )

    found = {series.quantity: series for series in climate.daily_series}
    series = found.get(PRECIPITATION)
    if series is None:
        return every_year(
            "MISSING_INPUT",
            f"water_balance (D181) needs the daily series {PRECIPITATION!r} of site "
            "data: climate, which it does not carry",
        )
    if series.unit != DAILY_DEPTH_UNIT:
        return every_year(
            "NOT_COMPUTABLE",
            f"water_balance (D181): the daily series {PRECIPITATION!r} is in "
            f"{series.unit!r}, not {DAILY_DEPTH_UNIT!r}; nothing is converted",
        )
    if reference_evapotranspiration is None:
        return every_year("NOT_AVAILABLE", WATER_BALANCE_NO_ET0)
    if isinstance(reference_evapotranspiration, InputMissing | ResultsMissing):
        given = reference_evapotranspiration
        return every_year(
            given.reason,
            "water_balance (D181): the daily FAO-56 reference evapotranspiration "
            "of D44 could not be computed"
            + (f": {given.detail}" if given.detail else ""),
        )
    inputs = (
        (f"the daily series {PRECIPITATION!r}", _daily_values(series)),
        (
            "the daily FAO-56 reference evapotranspiration (D44)",
            _reference_evapotranspiration_by_day(reference_evapotranspiration),
        ),
    )
    low, high = D181_CALIBRATED_RANGE_MM
    items: list[AnnualValue] = []
    outside: list[int] = []
    for year in range(years[0], years[1] + 1):
        first = dt.date(year, start_month, 1)
        after = dt.date(year + 1, start_month, 1)
        days = [first + dt.timedelta(days=n) for n in range((after - first).days)]
        sums: list[float] = []
        gap: InputMissing | None = None
        for what, by_day in inputs:
            values: list[float] = []
            for day in days:
                value = by_day.get(day)
                if value is None:
                    gap = _missing(
                        "NO_COVERAGE",
                        f"water_balance (D181): {what} has no item for {day.isoformat()}",
                    )
                    break
                if isinstance(value, InputMissing):
                    gap = _missing(
                        value.reason,
                        f"water_balance (D181): {what} is missing on {day.isoformat()}"
                        + (f" ({value.detail})" if value.detail else "")
                        + "; a year with a missing day is not filled (C3.3, C3.4)",
                    )
                    break
                values.append(value)
            if gap is not None:
                break
            sums.append(math.fsum(values))
        if gap is not None:
            items.append(AnnualValue(ag_year=year, value=None, missing=gap))
            continue
        precipitation, evapotranspiration = sums
        depth = precipitation - evapotranspiration  # mm over the year; IW = 0
        if not low <= depth <= high:
            outside.append(year)
        items.append(AnnualValue(ag_year=year, value=depth / MM_PER_M))

    header: dict = {}
    if any(item.value is not None for item in items):
        calibrated = (
            f"The source calibrated AMG for P - PET from {low:g} to {high:g} mm yr-1 "
            "(Clivot et al. 2019, p. 107; D181): outside that range its sensitivity "
            "is not known. "
            + (
                "Outside the calibrated range, kept as computed: agricultural "
                f"year(s) {', '.join(str(year) for year in outside)}"
                if outside
                else "Every year with a value lies inside that range"
            )
        )
        header = {
            "provenance": "DERIVED",  # C4.3: a fixed formula of other values
            "source": (
                "derived by api.carbon_forcing: D181 of #77, P + IW - ET0 over each "
                "agricultural year: the sum of the daily "
                f"{PRECIPITATION} (CQ1, D23) minus the sum of the daily FAO-56 "
                "Penman-Monteith reference evapotranspiration of D44 (eq. 6), which "
                "stands in for the Penman (1948) potential evapotranspiration of the "
                "source: a declared adaptation; IW = 0 (rainfed rotations); mm "
                f"divided by {MM_PER_M} to m. "
                + calibrated
                + (f". Input series: {series.source}" if series.source else "")
            ),
            "assumption": series.assumption,
            "range_missing": _missing(
                "NOT_AVAILABLE",
                "no range is derived for the water balance (C2.2)",
            ),
        }
    return AnnualSeries(
        quantity=WATER_BALANCE,
        unit=WATER_BALANCE_UNIT,
        first_ag_year=years[0],
        last_ag_year=years[1],
        years=items,
        **header,
    )


def monthly_climate(
    climate: SiteClimate,
    horizon: ForcingHorizon,
    reference_evapotranspiration: ReferenceEvapotranspiration,
) -> list[ClimateSeries]:
    """The monthly ``climate`` of the forcing for RothC (D220): ``rainfall``,
    ``potential_evapotranspiration`` and ``mean_temperature``, over the months
    of the horizon. No ``open_pan_evaporation`` series."""
    months = _months(horizon)
    return [
        _monthly_rainfall(climate, months),
        _monthly_potential_evapotranspiration(reference_evapotranspiration, months),
        _monthly_mean_temperature(climate, months),
    ]


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


def monthly_carbon_input_series(
    horizon: ForcingHorizon,
    monthly_carbon_inputs: Sequence[CarbonInputSeries] | None,
) -> list[CarbonInputSeries]:
    """``carbon_inputs`` of the forcing (D221 of #77). PROPOSED.

    - ``None`` (EP4 not built, or a ledger without years): no series. EP6 then
      finds no carbon input and says so; nothing is written as zero.
    - A sequence (the ``monthly_carbon_inputs`` of a residue ledger): copied
      unchanged, the same objects in the same order (D221: "the platform copies
      it into ``carbon_inputs`` unchanged"; D147: no arithmetic, no unit
      converted). A series that is not a ``CarbonInputSeries``, or that does not
      run over the months of the horizon, is a defect of the producer:
      ``TypeError``, as for the annual series.
    """
    if monthly_carbon_inputs is None:
        return []
    if isinstance(monthly_carbon_inputs, str | bytes) or not isinstance(
        monthly_carbon_inputs, Sequence
    ):
        raise TypeError(
            "monthly_carbon_inputs: expected a sequence of CarbonInputSeries"
        )
    copied: list[CarbonInputSeries] = []
    for series in monthly_carbon_inputs:
        if not isinstance(series, CarbonInputSeries):
            raise TypeError(
                f"monthly_carbon_inputs: expected CarbonInputSeries, not "
                f"{type(series).__name__}"
            )
        if (series.start, series.end) != (horizon.start, horizon.end):
            raise TypeError(
                "monthly_carbon_inputs: a series of the residue ledger does not run "
                "over the months of the forcing horizon"
            )
        copied.append(series)
    return copied


def build_carbon_forcing(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    carbon_inputs: Sequence[AnnualCarbonInputSeries] | InputMissing | None = None,
    reference_evapotranspiration: ReferenceEvapotranspiration = None,
    monthly_carbon_inputs: Sequence[CarbonInputSeries] | None = None,
) -> CarbonForcing | ResultsMissing:
    """The ``CarbonForcing`` of one rotation, or why it cannot be laid out.

    The caller has already checked that climate and soil and slope carry the
    calendar's ``case_id`` and ``field_id`` (D14). ``carbon_inputs`` is what
    the residue ledger (EP4) gives for ``annual_carbon_inputs``, or ``None``
    when EP4 is not built (``carbon_input_series``).
    ``reference_evapotranspiration`` is the daily FAO-56 reference
    evapotranspiration of D44 the runner computes: a mapping from the day to
    a number in mm day-1 (FAO-56 eq. 6) or a ``Missing`` of either contract
    shape; a single ``Missing`` when it could not be computed at all; ``None``
    when the runner passed none. It is plain data: this module imports nothing
    of ``engine/``. ``monthly_carbon_inputs`` is the ``monthly_carbon_inputs``
    of the residue ledger, copied into ``carbon_inputs`` unchanged (D221), or
    ``None`` (``monthly_carbon_input_series``).
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
    horizon = horizon_of(start.month, years)
    return CarbonForcing(
        contract="carbon_forcing",
        example_data=(
            calendar.example_data or climate.example_data or soil_slope.example_data
        ),
        case_id=calendar.case_id,
        field_id=calendar.field_id,
        rotation_id=calendar.rotation_id,
        horizon=horizon,
        soil_depth=Value(
            value=SOIL_DEPTH_D180,
            unit=SOIL_DEPTH_UNIT,
            provenance="DECLARED",
            source=SOIL_DEPTH_SOURCE,
            range_missing=_missing(
                "NOT_AVAILABLE", "D180 of #77 states the depth without a range"
            ),
        ),
        climate=monthly_climate(climate, horizon, reference_evapotranspiration),
        carbon_inputs=monthly_carbon_input_series(horizon, monthly_carbon_inputs),
        annual_climate=[
            _annual_mean_temperature(climate, start.month, years),
            _annual_water_balance(
                climate, start.month, years, reference_evapotranspiration
            ),
        ],
        annual_carbon_inputs=annual_carbon_inputs,
        soil_properties=[
            _soil_property(soil_slope, quantity) for quantity in SOIL_PROPERTIES
        ],
        soil_cover=[],
        starting_state=[_starting_carbon(soil_slope)],
    )
