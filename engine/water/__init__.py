"""Water engine. PROPOSED (blueprint section 3.7).

Entry point EP3 of ``contracts/ENTRYPOINTS.md``: ``compute_water_deficit_exposure``.
See ``EXPOSURE.md`` in this folder. ``et0/`` and ``balance/`` are internal parts.
"""

from .exposure import compute_water_deficit_exposure
from .reference_et0 import daily_reference_evapotranspiration

__all__ = [
    "compute_water_deficit_exposure",
    "daily_reference_evapotranspiration",
]
