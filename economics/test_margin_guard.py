"""The C3.1 guard of ``economics/margin.py`` (unit l2/review-whole-2). PROPOSED.

Run from the repository root: ``uv run pytest economics/``.

The facts are the invented test data of ``test_margin.py`` (no source).
"""

from __future__ import annotations

import pytest

from contracts.inputs.common import Value
from economics import compute_rotation_margin
from economics.test_margin import COVER, GRAIN_A, _facts


def test_a_missing_value_without_its_missing_part_is_a_value_error():
    # A Value built without validation (model_construct) may break C3.1; the
    # guard is an explicit check, so it holds also under python -O.
    facts = _facts()
    broken = Value.model_construct(value=None, unit="USD ha-1", missing=None)
    crops = [
        crop.model_copy(update={"cost": broken}) if crop.crop_id == COVER else crop
        for crop in facts.crops
    ]
    facts = facts.model_copy(update={"crops": crops})
    with pytest.raises(ValueError, match="C3.1"):
        compute_rotation_margin([[GRAIN_A, COVER]], facts, None)
