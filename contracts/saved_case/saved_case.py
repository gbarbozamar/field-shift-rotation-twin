"""Contract "Saved case". PROPOSED (blueprint section 3.7).

One case and the run of one of its fields, in one JSON document (D177 of
issue #77). The document carries, unchanged, the documents of the contracts
that already exist: the field identity of the case, the results table, one
``CarbonBalance`` per rotation and carbon model, and the decision output.
Their models are imported from their own folders, never copied.

Producer and consumer: Interface (sub-lane L2b writes it under ``demo/``;
lane L3 reads it from ``web/src/data/``). Landed by a builder session of
lane L0 (D177 of issue #77). See ``README.md`` in this folder for the field
list, what is PROPOSED, the differences from issue #251 and what is OPEN.

Every part is its document, or null with a ``missing`` part beside it named
after it (C3.1): never both and never neither. The date the case was saved
is a value of the document; nothing here reads a clock.

Models and pure validation only. No network calls, no file access, no
parameter values, no thresholds, no citations.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, model_validator

from contracts.carbon_balance import CarbonBalance
from contracts.decision_output import DecisionOutput
from contracts.field_identity import FieldIdentity
from contracts.inputs.common import ContractModel, IsoDate, Missing, NonEmptyStr
from contracts.results.models import CarbonModel, ResultsTable


def _check_part_or_missing(
    name: str, part: BaseModel | None, missing: Missing | None
) -> None:
    """C3.1: a part holds its document or a missing part, never both, never neither."""
    if part is not None and missing is not None:
        raise ValueError(
            f"{name}: a part holds its document or {name}_missing, never both (C3.1)"
        )
    if part is None and missing is None:
        raise ValueError(
            f"{name}: a part that is null carries {name}_missing with its reason (C3.1)"
        )


class CarbonBalanceItem(ContractModel):
    """One rotation and one carbon model, with its ``CarbonBalance`` or the reason it has none.

    ``rotation_id`` and ``carbon_model`` say which balance the item stands
    for, so that a missing balance still says what is missing (C3.1). When
    the balance is present, they are its own ``rotation_id`` and
    ``carbon_model``.
    """

    rotation_id: NonEmptyStr
    carbon_model: CarbonModel  # D1 of issue #77
    carbon_balance: CarbonBalance | None  # null when missing (C3.1)
    carbon_balance_missing: Missing | None = None

    @model_validator(mode="after")
    def _balance_or_missing(self) -> CarbonBalanceItem:
        _check_part_or_missing(
            "carbon_balance", self.carbon_balance, self.carbon_balance_missing
        )
        balance = self.carbon_balance
        if balance is None:
            return self
        if balance.rotation_id != self.rotation_id:
            raise ValueError(
                "carbon_balance: the rotation_id of the item is the rotation_id of "
                "the balance it holds"
            )
        if balance.carbon_model != self.carbon_model:
            raise ValueError(
                "carbon_balance: the carbon_model of the item is the carbon_model of "
                "the balance it holds"
            )
        return self


class SavedCase(ContractModel):
    """One case and the run of one of its fields (D177 of issue #77)."""

    contract: Literal["saved_case"]
    example_data: bool  # true when any part it carries is example data (D177)
    case_id: NonEmptyStr  # the identifier the other contracts use
    field_id: NonEmptyStr  # the field whose run the document holds
    saved_on: IsoDate  # given by whoever writes the document (D177, C5.2)
    field_identity: FieldIdentity | None  # null when missing (C3.1)
    field_identity_missing: Missing | None = None
    results_table: ResultsTable | None  # null when missing (C3.1)
    results_table_missing: Missing | None = None
    carbon_balances: list[CarbonBalanceItem]  # one per rotation and carbon model
    decision_output: DecisionOutput | None  # null when missing (C3.1)
    decision_output_missing: Missing | None = None

    @model_validator(mode="after")
    def _each_part_or_its_missing_part(self) -> SavedCase:
        _check_part_or_missing(
            "field_identity", self.field_identity, self.field_identity_missing
        )
        _check_part_or_missing(
            "results_table", self.results_table, self.results_table_missing
        )
        _check_part_or_missing(
            "decision_output", self.decision_output, self.decision_output_missing
        )
        return self

    @model_validator(mode="after")
    def _carried_documents_belong_to_the_case_and_field(self) -> SavedCase:
        identity = self.field_identity
        if identity is not None:
            if identity.case_id != self.case_id:
                raise ValueError(
                    "field_identity: its case_id is not the case_id of the saved case"
                )
            if self.field_id not in [field.field_id for field in identity.fields]:
                raise ValueError(
                    "field_identity: the field_id of the saved case is not a field "
                    "of the case"
                )
        carried: list[tuple[str, BaseModel | None]] = [
            ("results_table", self.results_table),
            *(
                (f"carbon_balances.{index}.carbon_balance", item.carbon_balance)
                for index, item in enumerate(self.carbon_balances)
            ),
            ("decision_output", self.decision_output),
        ]
        for name, document in carried:
            if document is None:
                continue
            for key in ("case_id", "field_id"):
                if getattr(document, key) != getattr(self, key):
                    raise ValueError(
                        f"{name}: its {key} is not the {key} of the saved case"
                    )
        return self

    @model_validator(mode="after")
    def _one_carbon_item_per_rotation_and_model(self) -> SavedCase:
        keys = Counter(
            (item.rotation_id, item.carbon_model) for item in self.carbon_balances
        )
        repeated = sorted(key for key, count in keys.items() if count > 1)
        if repeated:
            rotation_id, carbon_model = repeated[0]
            raise ValueError(
                f"carbon_balances: two carbon items for rotation {rotation_id!r} and "
                f"carbon model {carbon_model!r}; there is one per rotation and carbon "
                "model (D177)"
            )
        return self

    @model_validator(mode="after")
    def _example_data_when_a_part_is(self) -> SavedCase:
        if self.example_data:
            return self
        flagged: list[tuple[str, bool]] = []
        if self.field_identity is not None:
            flagged.append(("field_identity", self.field_identity.example_data))
        for index, item in enumerate(self.carbon_balances):
            if item.carbon_balance is not None:
                flagged.append(
                    (
                        f"carbon_balances.{index}.carbon_balance",
                        item.carbon_balance.example_data,
                    )
                )
        if self.decision_output is not None:
            flagged.append(("decision_output", self.decision_output.example_data))
        for name, example_data in flagged:
            if example_data:
                raise ValueError(
                    f"example_data: {name} is example data, so the saved case is "
                    "example data too (D177)"
                )
        return self
