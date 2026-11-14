"""Calendar engine. PROPOSED (blueprint section 3.7).

Entry point EP2 of ``contracts/ENTRYPOINTS.md``: ``build_rotation_calendar``.
See ``README.md`` in this folder.
"""

from .build import NoValidCalendarForm, build_rotation_calendar

__all__ = [
    "NoValidCalendarForm",
    "build_rotation_calendar",
]
