"""The daily FAO-56 reference evapotranspiration that EP3 uses, as a public function (D256). PROPOSED.

Decision D256 of issue #77: the daily reference evapotranspiration of D44
that the runner needs for the carbon forcing (D220, D181) comes from a public
function of lane L1, ``engine.water.daily_reference_evapotranspiration``,
listed in ``contracts/ENTRYPOINTS.md`` beside EP3 and found by name, and it
gives exactly the series EP3 uses.

How it gives the same series. It makes the call EP3 makes in ``_run_chain``
of ``engine/water/exposure.py`` (step 1, "The reference evapotranspiration of
every day of the record"), with EP3's own pieces, imported from that module
and not copied:

- the identifiers of the constants, ``exposure.ET0_PARAMETERS`` (one per
  field of ``et0.Et0Constants``, ``<group>_<field>``), and of the two bounds
  of D82, ``exposure.ET0_BOUND_PARAMETERS``;
- the catalogue reader of the water engine (``_parameters.Catalogue``) and
  EP3's ``_site``, so every record is looked up by ``id`` and the empty scope,
  with the same reasons when it is absent, holds no value or is not read;
- EP3's point units (``exposure.POINT_UNITS``) and unit-guard reason
  (``exposure._UNIT_GUARD_REASON``);
- the function of ``engine/water/et0/`` that EP3 calls,
  ``reference_evapotranspiration_from_climate_with_bounds``.

No constant and no bound is written here, and nothing is converted. EP3 still
builds its own call in ``_run_chain``: D256 asks that EP3 call this function
too, which is a change of ``exposure.py`` left to a later unit (that file is
open in another pull request). Until then the test of this module checks, day
by day, that the two give the same series.

Pure (G1): no file, no clock, no network; no argument is changed.
"""

from __future__ import annotations

import datetime as dt

from contracts.inputs.site_climate import SiteClimate
from contracts.results.models import Missing
from engine.water import exposure as ep3
from engine.water._parameters import Catalogue, check_parameters
from engine.water.et0 import (
    Et0Bounds,
    Et0Constants,
    reference_evapotranspiration_from_climate_with_bounds,
)

__all__ = ["daily_reference_evapotranspiration"]


def daily_reference_evapotranspiration(
    climate: SiteClimate, *, parameters: dict[str, dict]
) -> dict[dt.date, float | Missing]:
    """The daily FAO-56 reference evapotranspiration of D44, as EP3 uses it (D256).

    - ``climate``: the ``SiteClimate`` of the site (the same object EP3
      receives).
    - ``parameters``: the parameter catalogue as loaded by the runner (Q3,
      D46, D56), passed by keyword, with no default.

    Returns one item per day of the climate record (every day covered by at
    least one of the series the reference evapotranspiration reads), in date
    order: the value in the unit of ``engine/water/et0/`` (mm per day), or the
    ``Missing`` of ``contracts/results/models.py`` with the reason EP3's chain
    gives that day. A constant or bound without a record makes every day
    missing, ``MISSING_INPUT``, naming it by ``id`` and scope, as in EP3. A
    climate with no daily series gives an empty mapping.

    Raises ``TypeError`` when ``climate`` is not a ``SiteClimate`` or
    ``parameters`` is not the catalogue shape EP3 accepts (G3, G5).
    """
    if not isinstance(climate, SiteClimate):
        raise TypeError(
            f"climate: expected SiteClimate, got {type(climate).__name__} (G5)"
        )
    check_parameters(parameters)
    if not climate.daily_series:
        return {}
    # The day a record is read for; it changes no value or reason, only when
    # the catalogue notes a problem (``Catalogue.value``).
    first = min(series.start_date for series in climate.daily_series)
    catalogue = Catalogue(parameters)
    constants = Et0Constants(
        **{
            group: ep3._ET0_GROUPS[group](
                **{
                    name: ep3._site(catalogue, f"{group}_{name}", first)
                    for name in names
                }
            )
            for group, names in ep3.ET0_PARAMETERS.items()
        }
    )
    bounds = Et0Bounds(
        **{
            group: ep3._BOUND_GROUPS[group](
                **{
                    field: ep3._site(catalogue, parameter_id, first)
                    for field, parameter_id in names.items()
                }
            )
            for group, names in ep3.ET0_BOUND_PARAMETERS.items()
        }
    )
    days = reference_evapotranspiration_from_climate_with_bounds(
        climate,
        point_units=ep3.POINT_UNITS,
        constants=constants,
        bounds=bounds,
        unit_guard_reason=ep3._UNIT_GUARD_REASON,
    )
    return {item.date: item.value for item in days}
