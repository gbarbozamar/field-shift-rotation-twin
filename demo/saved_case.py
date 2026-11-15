"""The saved case of the thin matrix (unit l2/saved-case-d177, issue #251).

D177 of issue #77: one JSON document per case, described by the PROPOSED
contract ``contracts/saved_case/``, kept as a file under ``demo/``;
nothing is stored in the service. ``demo/`` writes it and checks it. This
module builds the saved case of ``example-case`` / ``example-field-1`` from
what the demo already holds, and writes and reads its file:

- ``field_identity``: the field identity of ``example-case``, read from the
  example of ``contracts/field_identity/`` (the synthetic shapes of D33 and
  D41, the one field identity of this case in the repository), unchanged;
- ``results_table``: the approved thin matrix of ``demo/matrix.py``
  (issue #240), unchanged;
- ``carbon_balances``: complete, one item per rotation of the matrix and
  carbon model (D177; #297, change 1), each naming the variant the engine
  of its model writes (#297, change 2): ``amg_a`` for AMG
  (``engine/amg/entry.py``), ``rothc_26_3`` for RothC
  (``engine/rothc/entry.py``). Each balance is **missing**: the thin matrix
  is a results table approved by the designer of the case, its AMG trend
  included, and no ``CarbonForcing`` exists for its rotations, so neither
  EP5 (``run_amg``) nor EP6 (``run_rothc``) is run and no balance is
  computed. The AMG balance is missing with ``MISSING_INPUT`` naming the
  forcing; the RothC balance with ``NOT_AVAILABLE`` (#297, change 3,
  consistent with D122). Nothing is invented in its place (C3.1, C3.3);
- ``decision_output``: the document ``demo/run.py`` builds over the same
  matrix, unchanged.

The date and time the case was saved is a value of the document, given by
whoever writes it (D177), to the minute and in UTC (#297, change 3): every
function that builds the document takes it as an argument. Only the command
line reads the clock, when it is run without a time: the time in the file is
then the time the writer was run. The file is written with every null kept
(``model_dump(mode="json")``, never ``exclude_none=True``; D177 and
``CLAUDE.md``). Write it, from the repository root, at the time it is run,
or with a time given as ``YYYY-MM-DDTHH:MMZ``::

    python -m demo.saved_case
    python -m demo.saved_case 2026-11-15T12:00Z
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from contracts.field_identity import FieldIdentity
from contracts.inputs.common import Missing
from contracts.results.models import CARBON_MODELS, ResultsTable
from contracts.saved_case import CarbonBalanceItem, SavedCase

from demo import matrix, run

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent

# D177: one file per case, under demo/. Saving again replaces it; the
# commit is its version.
SAVED_CASES = DEMO / "saved_cases"
SAVED_CASE_FILE = SAVED_CASES / f"{matrix.CASE_ID}.json"

# The field identity of example-case: the example of its contract.
FIELD_IDENTITY_FILE = (
    ROOT
    / "contracts"
    / "field_identity"
    / "examples"
    / "PLACEHOLDER_field_identity.json"
)

# The engine entry point that would compute the balance of each carbon
# model (contracts/ENTRYPOINTS.md).
_ENTRY_POINT_OF = {"amg": "EP5 (run_amg)", "rothc": "EP6 (run_rothc)"}

# #297, change 2: the variant of each carbon model, as its engine writes it
# (``VARIANT`` of engine/amg/entry.py and engine/rothc/entry.py; the
# vocabulary is OPEN 2 of contracts/carbon_balance/README.md).
VARIANT_OF = {"amg": "amg_a", "rothc": "rothc_26_3"}

# #297, change 3: saved_on is written with the date and the time to the
# minute, in UTC, as the contract writes it.
SAVED_ON_FORMAT = "%Y-%m-%dT%H:%MZ"


def read_field_identity(path: Path = FIELD_IDENTITY_FILE) -> FieldIdentity:
    """The field identity of the case, loaded by its own contract model."""
    return FieldIdentity.model_validate_json(path.read_text(encoding="utf-8"))


def _no_forcing(rotation_id: str, carbon_model: str) -> str:
    return (
        "the thin matrix (issue #240) is a results table approved by the designer "
        "of the case, and no forcing exists for its rotations, so "
        f"{_ENTRY_POINT_OF[carbon_model]} is not run and no balance is computed"
    )


def missing_balance(rotation_id: str, carbon_model: str) -> CarbonBalanceItem:
    """The balance of one rotation and carbon model, missing with its reason.

    AMG: ``MISSING_INPUT`` names the input the balance would be computed
    from (C3.2), the ``CarbonForcing`` of the rotation, which the thin
    matrix does not have. RothC: ``NOT_AVAILABLE``, the reason the producer
    and consumer of the saved case gives a missing RothC balance (#297,
    change 3, consistent with D122), with the same cause in the detail.
    """
    if carbon_model == "rothc":
        missing = Missing(
            reason="NOT_AVAILABLE",
            detail=(
                f"the RothC balance of rotation '{rotation_id}' is not available: "
                f"{_no_forcing(rotation_id, carbon_model)} (#297, change 3; D122)"
            ),
        )
    else:
        missing = Missing(
            reason="MISSING_INPUT",
            detail=(
                f"the CarbonForcing of rotation '{rotation_id}': "
                f"{_no_forcing(rotation_id, carbon_model)}"
            ),
        )
    return CarbonBalanceItem(
        rotation_id=rotation_id,
        carbon_model=carbon_model,
        variant=VARIANT_OF[carbon_model],
        carbon_balance=None,
        carbon_balance_missing=missing,
    )


def carbon_balance_items() -> list[CarbonBalanceItem]:
    """Complete: one item per rotation of the matrix and carbon model, in order (#297)."""
    return [
        missing_balance(rotation_id, carbon_model)
        for rotation_id in matrix.ROTATIONS
        for carbon_model in CARBON_MODELS
    ]


def saved_on_of(text: str) -> dt.datetime:
    """A time written ``YYYY-MM-DDTHH:MMZ``, as an aware datetime in UTC."""
    return dt.datetime.strptime(text, SAVED_ON_FORMAT).replace(tzinfo=dt.UTC)


def saved_now() -> dt.datetime:
    """The time the writer is run, in UTC, to the minute (#297, change 3)."""
    return dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)


def build_saved_case(
    saved_on: dt.datetime,
    field_identity: FieldIdentity,
    table: ResultsTable | None = None,
) -> SavedCase:
    """The saved case of the thin matrix, validated by its contract.

    Every part is the document its own unit produces, unchanged; the date
    and time are the caller's (D177; #297, change 3).
    """
    table = matrix.thin_matrix() if table is None else table
    decision = run.build_decision_output(table)
    return SavedCase(
        contract="saved_case",
        example_data=(
            field_identity.example_data or decision.example_data
        ),  # D177: true when a part it carries is example data
        case_id=table.case_id,
        field_id=table.field_id,
        saved_on=saved_on,
        field_identity=field_identity,
        field_identity_missing=None,
        results_table=table,
        results_table_missing=None,
        carbon_balances=carbon_balance_items(),
        decision_output=decision,
        decision_output_missing=None,
    )


def saved_case_text(document: SavedCase) -> str:
    """The text of the file: every null kept, two-space indent, a final newline."""
    return (
        json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=False)
        + "\n"
    )


def write_saved_case(document: SavedCase, path: Path = SAVED_CASE_FILE) -> Path:
    """Write the document to its file, replacing the one before (D177)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(saved_case_text(document).encode("utf-8"))
    return path


def read_saved_case(path: Path = SAVED_CASE_FILE) -> SavedCase:
    """Read a saved case and check it against its contract and the contracts it carries."""
    return SavedCase.model_validate_json(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    """Write the saved case at the time it is run, or at the time given."""
    args = sys.argv[1:] if argv is None else argv
    usage = "usage: python -m demo.saved_case [YYYY-MM-DDTHH:MMZ]"
    if len(args) > 1:
        print(usage, file=sys.stderr)
        return 2
    if args:
        try:
            saved_on = saved_on_of(args[0])
        except ValueError:
            print(usage, file=sys.stderr)
            return 2
    else:
        saved_on = saved_now()
    document = build_saved_case(saved_on, read_field_identity())
    path = write_saved_case(document, SAVED_CASE_FILE)
    read_saved_case(path)
    print(f"wrote {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
