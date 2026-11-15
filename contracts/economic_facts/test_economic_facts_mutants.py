"""Targeted validator-boundary and mutant-killing tests for ``contracts/economic_facts/economic_facts.py``.

Covers currency (USD), exact C1.1 unit strings (present and missing), zero vs
negative sign boundaries on values and range bounds, DECLARED provenance,
CropId whitespace & uniqueness rules, and injected validator mutants.
Every identifier and number here is PLACEHOLDER test data only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.economic_facts import economic_facts as ef_module
from contracts.economic_facts.economic_facts import (
    COST_UNIT,
    MARGIN_UNIT,
    PRICE_UNIT,
    YIELD_UNIT,
    CoverCrop,
    CropId,
    DeclaredMarginCrop,
    EconomicFacts,
    GrainCrop,
)
from contracts.inputs.common import Missing, Range, Value

EXAMPLE = Path(__file__).parent / "examples" / "PLACEHOLDER_economic_facts.json"
SOURCE = "PLACEHOLDER source"
KIND = "PLACEHOLDER_kind"


def _load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _declared(
    val: float | None, unit: str, *, low: float | None = None, high: float | None = None
) -> dict[str, Any]:
    if val is None:
        return {"value": None, "unit": unit, "missing": {"reason": "NOT_DECLARED"}}
    item: dict[str, Any] = {
        "value": val,
        "unit": unit,
        "provenance": "DECLARED",
        "source": SOURCE,
    }
    if low is not None and high is not None:
        item["range"] = {"low": low, "high": high, "kind": KIND}
    else:
        item["range_missing"] = {"reason": "NOT_DECLARED"}
    return item


# --- 1. Currency & exact unit boundaries (present and missing) ----------------


@pytest.mark.parametrize(
    "bad_currency", ["usd", "EUR", "UYU", ""], ids=["lower", "eur", "uyu", "empty"]
)
def test_currency_rejects_anything_other_than_usd(bad_currency: str) -> None:
    data = _load()
    data["currency"] = bad_currency
    with pytest.raises(ValidationError, match="USD"):
        EconomicFacts.model_validate(data)


@pytest.mark.parametrize(
    ("crop_kind", "field_path", "bad_unit", "expected_unit"),
    [
        ("grain", ["price"], "USD kg-1", PRICE_UNIT),
        ("grain", ["cost"], "USD ha-1 yr-1", COST_UNIT),
        ("grain", ["yield", "el_nino"], "t ha-1 yr-1", YIELD_UNIT),
        ("cover", ["cost"], "USD t-1", COST_UNIT),
        ("declared_margin", ["declared_margin", "la_nina"], "USD ha-1", MARGIN_UNIT),
    ],
)
def test_missing_values_still_enforce_exact_units(
    crop_kind: str, field_path: list[str], bad_unit: str, expected_unit: str
) -> None:
    data = _load()
    crop = next(c for c in data["crops"] if c["kind"] == crop_kind)
    target = crop
    for key in field_path:
        target = target[key]
    target.clear()
    target.update(
        {"value": None, "unit": bad_unit, "missing": {"reason": "NOT_DECLARED"}}
    )
    with pytest.raises(ValidationError, match=expected_unit):
        EconomicFacts.model_validate(data)


# --- 2. Sign boundaries (0.0 vs -1e-9; range.low == 0.0 vs -1e-6) -------------


def test_zero_value_and_zero_range_low_accepted_while_epsilon_negative_rejected() -> (
    None
):
    data = _load()
    grain = data["crops"][0]
    grain["price"] = _declared(0.0, PRICE_UNIT, low=0.0, high=10.0)
    grain["cost"] = _declared(0.0, COST_UNIT, low=0.0, high=10.0)
    for kind in ("el_nino", "neutral", "la_nina"):
        grain["yield"][kind] = _declared(0.0, YIELD_UNIT, low=0.0, high=5.0)
    data["crops"][1]["cost"] = _declared(0.0, COST_UNIT, low=0.0, high=10.0)
    loaded = EconomicFacts.model_validate(data)
    assert loaded.crops[0].price.value == 0.0

    # Epsilon below zero on value -> rejected.
    bad_val = copy.deepcopy(data)
    bad_val["crops"][0]["yield"]["neutral"] = _declared(-1e-9, YIELD_UNIT)
    with pytest.raises(ValidationError, match="must not be negative"):
        EconomicFacts.model_validate(bad_val)

    # Epsilon below zero on range.low even when value >= 0 -> rejected.
    bad_low = copy.deepcopy(data)
    bad_low["crops"][1]["cost"] = _declared(0.0, COST_UNIT, low=-1e-6, high=10.0)
    with pytest.raises(ValidationError, match="low bound is below zero"):
        EconomicFacts.model_validate(bad_low)


def test_declared_margin_allows_negative_value_and_negative_range() -> None:
    crop = DeclaredMarginCrop(
        crop_id="PLACEHOLDER_pasture",
        kind="declared_margin",
        declared_margin={
            "el_nino": Value(
                value=-25.0,
                unit=MARGIN_UNIT,
                provenance="DECLARED",
                source=SOURCE,
                range=Range(low=-50.0, high=-10.0, kind=KIND),
            ),
            "neutral": _declared(10.0, MARGIN_UNIT),
            "la_nina": _declared(None, MARGIN_UNIT),
        },
    )
    assert crop.declared_margin.el_nino.value == -25.0


# --- 3. Provenance, assumption mark, and CropId whitespace boundaries ---------


@pytest.mark.parametrize("bad_prov", ["OBSERVED", "DERIVED", "SIMULATED"])
def test_all_economic_values_reject_non_declared_provenance(bad_prov: str) -> None:
    data = _load()
    data["crops"][2]["declared_margin"]["el_nino"]["provenance"] = bad_prov
    with pytest.raises(ValidationError, match="DECLARED"):
        EconomicFacts.model_validate(data)


def test_assumption_true_accepted_and_crop_id_surrounding_whitespace_rejected() -> None:
    cover = CoverCrop(
        crop_id="PLACEHOLDER cover",  # internal space is valid
        kind="cover",
        cost=Value(
            value=1.0,
            unit=COST_UNIT,
            provenance="DECLARED",
            assumption=True,
            range_missing=Missing(reason="NOT_DECLARED"),
        ),
    )
    assert cover.cost.assumption is True

    for bad_id in (" PLACEHOLDER", "PLACEHOLDER ", "\tPLACEHOLDER", "PLACEHOLDER\n"):
        with pytest.raises(ValidationError, match="leading or trailing white space"):
            CoverCrop(
                crop_id=bad_id,
                kind="cover",
                cost=Value.model_validate(_declared(1.0, COST_UNIT)),
            )


def test_duplicate_crop_id_across_different_crop_kinds_rejected() -> None:
    data = _load()
    data["crops"][2]["crop_id"] = data["crops"][0]["crop_id"]
    with pytest.raises(ValidationError, match="share one crop_id"):
        EconomicFacts.model_validate(data)


# --- 4. Injected validator mutants --------------------------------------------


def _sandbox_economic_facts(old: str, new: str) -> type[Any]:
    """Compile an isolated in-memory mutant of EconomicFacts (never in sys.modules)."""
    source = Path(ef_module.__file__).read_text(encoding="utf-8")
    mutated_source = source.replace(old, new)
    assert mutated_source != source
    ns: dict[str, Any] = {"__name__": "test_economic_facts_mutant_sandbox"}
    exec(compile(mutated_source, "<mutant_economic_facts>", "exec"), ns)
    for model_name in (
        "YieldByYear",
        "MarginByYear",
        "GrainCrop",
        "CoverCrop",
        "DeclaredMarginCrop",
        "EconomicFacts",
    ):
        ns[model_name].model_rebuild(_types_namespace=ns, force=True)
    return ns["EconomicFacts"]


def test_mutant_weakened_declared_constant_allows_observed_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    # Keep a single cover crop so only one value carries provenance.
    data["crops"] = [copy.deepcopy(data["crops"][1])]
    data["crops"][0]["cost"]["provenance"] = "OBSERVED"
    with pytest.raises(ValidationError, match="provenance is DECLARED"):
        EconomicFacts.model_validate(data)

    monkeypatch.setattr(ef_module, "DECLARED", "OBSERVED")
    accepted = EconomicFacts.model_validate(data)
    assert accepted.crops[0].cost.provenance == "OBSERVED"


def test_mutant_weakened_unique_crop_ids_allows_duplicates() -> None:
    mutant_cls = _sandbox_economic_facts(
        "if len(ids) != len(set(ids)):",
        "if False:",
    )
    data = _load()
    data["crops"][1]["crop_id"] = data["crops"][0]["crop_id"]
    with pytest.raises(ValidationError, match="share one crop_id"):
        EconomicFacts.model_validate(data)

    accepted = mutant_cls.model_validate(data)
    assert accepted.crops[0].crop_id == accepted.crops[1].crop_id


def test_mutant_weakened_non_negative_rule_in_sandbox_allows_negative_price() -> None:
    mutant_cls = _sandbox_economic_facts(
        "non_negative=True",
        "non_negative=False",
    )
    data = _load()
    data["crops"][0]["price"]["value"] = -5.0
    with pytest.raises(ValidationError, match="must not be negative"):
        EconomicFacts.model_validate(data)

    accepted = mutant_cls.model_validate(data)
    assert accepted.crops[0].price.value == -5.0
    # Keep unused imports checked as active references.
    assert GrainCrop is not None and CropId is not None
