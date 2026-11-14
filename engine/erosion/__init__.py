"""Erosion engine. PROPOSED (blueprint section 3.7).

Entry point EP1 of ``contracts/ENTRYPOINTS.md``: ``compute_soil_loss``.
See ``SOIL_LOSS.md`` in this folder.
"""

from .soil_loss import compute_soil_loss

__all__ = [
    "compute_soil_loss",
]
