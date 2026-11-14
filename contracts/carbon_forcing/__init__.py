"""Contract "CarbonForcing". PROPOSED (blueprint section 3.7).

What both carbon models receive for one rotation of one field (blueprint
section 5). See ``README.md`` in this folder.
"""

from .models import CarbonForcing, CarbonInputSeries, ClimateSeries, ForcingHorizon

__all__ = [
    "CarbonForcing",
    "CarbonInputSeries",
    "ClimateSeries",
    "ForcingHorizon",
]
