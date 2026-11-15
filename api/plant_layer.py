"""The plant layer, as the route ``POST /api/plant/run`` sees it. PROPOSED.

Unit ``l2/plant-layer-by-name`` (brief S-031, decision R24 of the loop; point
1 of the platform review of PR 310). The pattern is ``api/decision_layer.py``:
the route depends on the interface ``PlantLayer`` of ``api/ports.py``, never
on ``economics/`` or ``contracts.plant_answer`` themselves. The default
implementation, ``DiscoveredPlantLayer``, finds on each request, **by name**:

- the request and answer models of the contract, ``PlantRequest`` and
  ``PlantAnswer`` of ``CONTRACT_MODULE`` (``contracts.plant_answer``), first;
- then the entry function ``PLANT_FUNCTION`` of ``PLANT_MODULE``
  (``economics.plant.answer_plant``).

Only the absence of one of those modules (or of a package above it) or of
one of those names means "not built": ``Missing`` ``NOT_AVAILABLE``, and the
route answers ``200`` with the not-built body (``not_built_body``). Any other
import error, a module that imports something absent included, propagates
and the plant route answers ``500`` ``INTERNAL_ERROR``; the other routes are
untouched, because nothing of the plant layer is imported when the app
starts. Python keeps a module once it is imported, so the lookup costs
nothing after the first request.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.decision_layer import import_named
from api.ports import Missing, PlantLayer, PlantParts

__all__ = [
    "ANSWER_MODEL",
    "CONTRACT_MODULE",
    "NOT_BUILT_CONTRACT",
    "PLANT_FUNCTION",
    "PLANT_MODULE",
    "REQUEST_MODEL",
    "DiscoveredPlantLayer",
    "PlantLayer",
    "not_built_body",
]

# PROPOSED: where the platform looks for the plant layer. One place to change.
PLANT_MODULE = "economics.plant"
PLANT_FUNCTION = "answer_plant"
CONTRACT_MODULE = "contracts.plant_answer"
REQUEST_MODEL = "PlantRequest"
ANSWER_MODEL = "PlantAnswer"

# PROPOSED (S-031): the ``contract`` of the body of a plant answer that is not
# built (``PlantAnswerNotBuilt`` of contracts/plant_answer/).
NOT_BUILT_CONTRACT = "plant_answer_not_built"

# PROPOSED detail text: English for developers; it names what is absent,
# never a submitted value.
NOT_BUILT = "the plant layer is not built yet: {name} is absent"


def _not_built(module: str, name: str) -> Missing:
    return Missing(
        reason="NOT_AVAILABLE", detail=NOT_BUILT.format(name=f"{module}.{name}")
    )


def not_built_body(missing: Missing) -> dict[str, Any]:
    """The ``200`` body of a plant answer that is not built (PROPOSED, S-031).

    Exactly ``{"contract": "plant_answer_not_built", "answer_missing":
    {"reason", "detail"}}``, written here as a dict so the route needs no
    contract import; ``PlantAnswerNotBuilt`` of contracts/plant_answer/ loads it.
    """
    return {
        "contract": NOT_BUILT_CONTRACT,
        "answer_missing": {"reason": missing.reason, "detail": missing.detail},
    }


class DiscoveredPlantLayer:
    """The default ``PlantLayer``: the parts found by name on each request.

    Never at start-up (module docstring). The names default to the constants
    above; a test passes others (an absent module, a module that raises).
    """

    def __init__(
        self,
        *,
        plant_module: str = PLANT_MODULE,
        plant_function: str = PLANT_FUNCTION,
        contract_module: str = CONTRACT_MODULE,
    ) -> None:
        self._plant_module = plant_module
        self._plant_function = plant_function
        self._contract_module = contract_module

    def parts(self) -> PlantParts | Missing:
        found: Mapping[str, Any] = {}
        for name in (REQUEST_MODEL, ANSWER_MODEL):
            item = import_named(self._contract_module, name)
            if item is None:
                return _not_built(self._contract_module, name)
            found = {**found, name: item}
        function = import_named(self._plant_module, self._plant_function)
        if function is None:
            return _not_built(self._plant_module, self._plant_function)
        return PlantParts(
            request_model=found[REQUEST_MODEL],
            answer_model=found[ANSWER_MODEL],
            answer_plant=function,
        )
