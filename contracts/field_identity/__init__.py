"""Contract "Field identity". PROPOSED (blueprint section 3.7).

The fields of one case, their names and their geometry (issue #103, D19 and
D41 of issue #77). See ``README.md`` in this folder.
"""

from .field_identity import CaseField, FieldIdentity, PolygonGeometry

__all__ = [
    "CaseField",
    "FieldIdentity",
    "PolygonGeometry",
]
