"""Contract "GreenCoverStrip". PROPOSED (blueprint section 3.7, section 8 gated extra #2).

Satellite green-cover strip from Landsat and Sentinel-2 (HLS) or MODIS for one
field of one case. See ``README.md`` in this folder.
"""

from .models import GreenCoverObservation, GreenCoverStrip

__all__ = [
    "GreenCoverObservation",
    "GreenCoverStrip",
]
