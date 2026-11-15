"""The decision layer, as the route that serves a decision output sees it.

``contracts/decision_output/README.md`` names the producer of the decision
output document: "Platform, decision (L2b, ``decision/``)". The route
(``api/decisions.py``) depends on the interface below, never on
``decision/`` itself, as the runner depends on the engines: the default
implementation finds one function **by name** (``DECISION_MODULE``,
``DECISION_FUNCTION``), the way ``api.engines.discover_engine_functions``
finds an entry point, and never imports it directly.

PROPOSED, for the interface developer (sub-lane L2b) to accept or rename: the
module path, the function name and its signature,

    assemble_decision_output(table: ResultsTable, *, example_data: bool) -> DecisionOutput

``table`` is the results table the platform built (``api/results_table.py``);
the rotations and scenarios of the document are those of the table. No limit
and no tolerance of "equal" is passed: the route of today takes none, so the
document carries them missing with their reason (D60, D87). What the function
returns is checked here; anything else is a defect.

While the function is not found, the answer is a typed absence,
``NOT_AVAILABLE``, never an error: a valid request still answers ``200``.

**Nothing of the decision layer is imported when the app starts** (PROPOSED,
asked by the orchestrating session for the night: every merge to ``main``
redeploys the service before CI ends). The default implementation,
``DiscoveredDecisionLayer``, looks the function up on each request; Python
keeps a module once it is imported, so the lookup costs nothing after the
first. Neither ``decision/`` nor ``contracts.decision_output`` is imported at
module level here. A decision layer that fails to load, raises or returns a
document that does not match its table never breaks start-up or another
route: the route answers ``200`` with ``decision_missing`` (``api/decisions.py``).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

# The interface lives with the other interfaces of the route, in api/ports.py;
# it is re-exported here for the callers of this module.
from api.ports import DecisionLayer, Missing
from contracts.results.models import ResultsTable

if TYPE_CHECKING:
    from contracts.decision_output import DecisionOutput

__all__ = [
    "DECISION_FUNCTION",
    "DECISION_MODULE",
    "DecisionLayer",
    "DiscoveredDecisionLayer",
    "NamedDecisionLayer",
    "check_document",
    "discover_decision_function",
    "import_named",
]

# PROPOSED: where the platform looks for the function that assembles the
# decision output document (sub-lane L2b). One place to change if renamed.
DECISION_MODULE = "decision.output"
DECISION_FUNCTION = "assemble_decision_output"
DECISION_NAME = f"{DECISION_MODULE}.{DECISION_FUNCTION}"

# PROPOSED detail text: English for developers.
NOT_BUILT = "the decision layer is not built yet: " + DECISION_NAME


def import_named(module_path: str, name: str) -> Callable[..., Any] | None:
    """A function found by module path and name, or ``None`` when it does not exist.

    The rule of ``api.engines._import_function``: only the absence of the
    module itself (or of a package above it) or of the function means "not
    built". Any other import error, including a module that imports something
    absent, is a defect and propagates; a name that exists and is not
    callable is a ``TypeError``.
    """
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as error:
        parts = module_path.split(".")
        own = {".".join(parts[: i + 1]) for i in range(len(parts))}
        if error.name in own:
            return None
        raise
    function = getattr(module, name, None)
    if function is None:
        return None
    if not callable(function):
        raise TypeError(f"{module_path}.{name} exists and is not a function")
    return function


def discover_decision_function() -> Callable[..., Any] | None:
    """The function of ``DECISION_MODULE`` named ``DECISION_FUNCTION``, or ``None``."""
    return import_named(DECISION_MODULE, DECISION_FUNCTION)


def check_document(
    document: object, table: ResultsTable, *, example_data: bool
) -> DecisionOutput:
    """What the decision function returned, checked against the table it was given.

    A ``DecisionOutput`` of contracts/decision_output/ (validated again, so a
    model built without validation cannot pass), for the same case and field,
    with the rotations and the scenarios of the table, and the example mark
    the route passed. Anything else is a defect: ``TypeError``, or the
    ``ValidationError`` of the contract when the document does not
    validate again.
    """
    from contracts.decision_output import DecisionOutput

    if not isinstance(document, DecisionOutput):
        raise TypeError(
            f"{DECISION_NAME} returned {type(document).__name__}, not DecisionOutput"
        )
    document = DecisionOutput.model_validate(document.model_dump())
    if (document.case_id, document.field_id) != (table.case_id, table.field_id):
        raise TypeError(f"{DECISION_NAME} returned a document of another case or field")
    rotations = {row.rotation_id for row in table.rows}
    if set(document.rotations) != rotations or len(document.rotations) != len(
        rotations
    ):
        raise TypeError(
            f"{DECISION_NAME} returned a document whose rotations are not those of "
            "the table"
        )
    scenarios = {row.scenario_id for row in table.rows}
    if set(document.scenarios) != scenarios or len(document.scenarios) != len(
        scenarios
    ):
        raise TypeError(
            f"{DECISION_NAME} returned a document whose scenarios are not those of "
            "the table"
        )
    if document.example_data is not example_data:
        raise TypeError(
            f"{DECISION_NAME} returned a document whose example mark is not the one "
            "it was given"
        )
    return document


class NamedDecisionLayer:
    """``DecisionLayer`` on the function found by name (``None``: not built)."""

    def __init__(self, function: Callable[..., Any] | None) -> None:
        if function is not None and not callable(function):
            raise TypeError("the decision function is a function or None")
        self._function = function

    @property
    def built(self) -> bool:
        return self._function is not None

    def decide(
        self, table: ResultsTable, *, example_data: bool
    ) -> DecisionOutput | Missing:
        if self._function is None:
            return Missing(reason="NOT_AVAILABLE", detail=NOT_BUILT)
        document = self._function(table, example_data=example_data)
        return check_document(document, table, example_data=example_data)


class DiscoveredDecisionLayer:
    """The default ``DecisionLayer``: the function found by name on each request.

    Never at start-up (module docstring). ``discover`` is
    ``discover_decision_function`` unless a test passes another. What the
    lookup or the function raises propagates to the route, which answers it
    as a typed absence.
    """

    def __init__(
        self,
        discover: Callable[[], Callable[..., Any] | None] = discover_decision_function,
    ) -> None:
        self._discover = discover

    def decide(
        self, table: ResultsTable, *, example_data: bool
    ) -> DecisionOutput | Missing:
        return NamedDecisionLayer(self._discover()).decide(
            table, example_data=example_data
        )
