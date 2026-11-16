"""Cross-seam round-trip, identifier alignment, and C3.1/C3.2 invariants test.

Covers every shipped ``contracts/*/examples/PLACEHOLDER_*.json`` file and its
Pydantic model across all twelve contract packages:

- ``contracts/inputs/``
- ``contracts/results/``
- ``contracts/rotation_definition/``
- ``contracts/residue_ledger/``
- ``contracts/carbon_forcing/``
- ``contracts/carbon_balance/``
- ``contracts/decision_output/``
- ``contracts/saved_case/``
- ``contracts/field_identity/``
- ``contracts/economic_facts/``
- ``contracts/plant_answer/``
- ``contracts/green_cover/``
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import BaseModel, ValidationError

from contracts.carbon_balance import CarbonBalance
from contracts.carbon_forcing import CarbonForcing
from contracts.decision_output import DecisionOutput
from contracts.economic_facts import EconomicFacts
from contracts.field_identity import FieldIdentity
from contracts.green_cover import GreenCoverStrip
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.inputs.common import DateValue, Missing, ReasonCode, Value
from contracts.inputs.site_climate import DailyValue, MonthlyValue
from contracts.plant_answer import (
    PlantAnswer,
    PlantRequest,
    check_answer_against_request,
)
from contracts.residue_ledger import ResidueLedger
from contracts.results.models import (
    AnnualSoilLoss,
    Missing as ResultsMissing,
    ResultsPerRotation,
    ResultsTable,
)
from contracts.rotation_definition import RotationDefinition
from contracts.saved_case import SavedCase

CONTRACTS_DIR = Path(__file__).resolve().parent
VALID_REASON_CODES: frozenset[str] = frozenset(get_args(ReasonCode))

EXAMPLE_MODELS: dict[str, type[BaseModel]] = {
    "carbon_balance/examples/PLACEHOLDER_carbon_balance.json": CarbonBalance,
    "carbon_forcing/examples/PLACEHOLDER_carbon_forcing.json": CarbonForcing,
    "decision_output/examples/PLACEHOLDER_decision_output.json": DecisionOutput,
    "economic_facts/examples/PLACEHOLDER_economic_facts.json": EconomicFacts,
    "field_identity/examples/PLACEHOLDER_field_identity.json": FieldIdentity,
    "green_cover/examples/PLACEHOLDER_green_cover.json": GreenCoverStrip,
    "inputs/examples/PLACEHOLDER_chain_site_climate.json": SiteClimate,
    "inputs/examples/PLACEHOLDER_chain_site_soil_slope.json": SiteSoilSlope,
    "inputs/examples/PLACEHOLDER_rotation_calendar.json": RotationCalendar,
    "inputs/examples/PLACEHOLDER_site_climate.json": SiteClimate,
    "inputs/examples/PLACEHOLDER_site_soil_slope.json": SiteSoilSlope,
    "plant_answer/examples/PLACEHOLDER_plant_answer.json": PlantAnswer,
    "plant_answer/examples/PLACEHOLDER_plant_request.json": PlantRequest,
    "residue_ledger/examples/PLACEHOLDER_residue_ledger.json": ResidueLedger,
    "results/examples/PLACEHOLDER_results_per_rotation.json": ResultsPerRotation,
    "results/examples/PLACEHOLDER_results_per_rotation_not_built.json": ResultsPerRotation,
    "results/examples/PLACEHOLDER_results_table.json": ResultsTable,
    "rotation_definition/examples/PLACEHOLDER_rotation_definition.json": RotationDefinition,
    "saved_case/examples/PLACEHOLDER_saved_case.json": SavedCase,
}

RESULTS_EXAMPLES: frozenset[str] = frozenset(
    {
        "results/examples/PLACEHOLDER_results_per_rotation.json",
        "results/examples/PLACEHOLDER_results_per_rotation_not_built.json",
        "results/examples/PLACEHOLDER_results_table.json",
    }
)


def _read_example_text(rel_path: str) -> str:
    return (CONTRACTS_DIR / rel_path).read_text(encoding="utf-8")


def _load_example(rel_path: str) -> BaseModel:
    model_cls = EXAMPLE_MODELS[rel_path]
    return model_cls.model_validate_json(_read_example_text(rel_path))


def _roundtrip(rel_path: str) -> tuple[BaseModel, BaseModel]:
    model_cls = EXAMPLE_MODELS[rel_path]
    loaded = model_cls.model_validate_json(_read_example_text(rel_path))
    reloaded = model_cls.model_validate_json(loaded.model_dump_json())
    return loaded, reloaded


def _assert_missing_record(missing: Any, location: str) -> None:
    assert isinstance(missing, dict), f"{location}: missing must be an object"
    reason = missing.get("reason")
    assert reason in VALID_REASON_CODES, (
        f"{location}: invalid or missing C3.2 reason code {reason!r}"
    )
    if reason == "MISSING_INPUT":
        detail = missing.get("detail")
        assert isinstance(detail, str) and detail.strip() != "", (
            f"{location}: MISSING_INPUT requires a non-blank detail (C3.2)"
        )


def _assert_c3_invariants_in_tree(node: Any, path: str = "root") -> None:
    """Recursively verify C3.1/C3.2 missingness invariants on dumped JSON data."""
    if isinstance(node, list):
        for idx, item in enumerate(node):
            _assert_c3_invariants_in_tree(item, f"{path}[{idx}]")
        return
    if not isinstance(node, dict):
        return

    # Validate explicit `missing` field when present.
    if "missing" in node and node["missing"] is not None:
        _assert_missing_record(node["missing"], f"{path}.missing")

    # Validate sibling `*_missing` fields (e.g., range_missing, field_identity_missing).
    for key, val in node.items():
        if key.endswith("_missing") and val is not None:
            _assert_missing_record(val, f"{path}.{key}")

    # StatedValue / _SeriesItem / IndicatorValue / SoilLossResults-style items:
    # payload is never non-null alongside a missing record, and never null without one.
    if "value" in node and "missing" in node:
        if node["value"] is None:
            assert node["missing"] is not None, (
                f"{path}: null value must carry a missing reason (C3.1)"
            )
            assert node.get("provenance") is None, (
                f"{path}: missing value must carry no provenance (C4.1)"
            )
            assert node.get("source") is None, (
                f"{path}: missing value must carry no source"
            )
            assert not node.get("assumption", False), (
                f"{path}: missing value must not be marked as an assumption"
            )
            assert node.get("range") is None, (
                f"{path}: missing value must carry no range (C2.2)"
            )
            assert node.get("range_missing") is None, (
                f"{path}: missing value must carry no range_missing (C2.2)"
            )
        else:
            assert node["missing"] is None, (
                f"{path}: present value must not carry a missing part (C3.1)"
            )

    if "date" in node and "missing" in node and "value" not in node:
        if node["date"] is None:
            assert node["missing"] is not None, (
                f"{path}: null date must carry a missing reason (C3.1)"
            )
            assert node.get("provenance") is None
            assert node.get("source") is None
            assert not node.get("assumption", False)
        else:
            assert node["missing"] is None, (
                f"{path}: present date must not carry a missing part (C3.1)"
            )

    if "month" in node and "missing" in node and "value" not in node:
        if node["month"] is None:
            assert node["missing"] is not None, (
                f"{path}: null month must carry a missing reason (C3.1)"
            )
            assert node.get("provenance") is None
            assert node.get("source") is None
            assert not node.get("assumption", False)
        else:
            assert node["missing"] is None, (
                f"{path}: present month must not carry a missing part (C3.1)"
            )

    # Paired `part` / `part_missing` contracts (SavedCase, FieldIdentity, DecisionOutput).
    for part_key in (
        "field_identity",
        "results_table",
        "decision_output",
        "carbon_balance",
        "geometry",
        "by_sign_of_point_value",
    ):
        miss_key = f"{part_key}_missing"
        if part_key in node:
            if node[part_key] is None:
                assert node.get(miss_key) is not None, (
                    f"{path}: null {part_key} must carry {miss_key} (C3.1)"
                )
            else:
                assert node.get(miss_key) is None, (
                    f"{path}: present {part_key} must not carry {miss_key} (C3.1)"
                )

    # ResidueLedger years pair.
    if "first_ag_year" in node and "years_missing" in node:
        if node["first_ag_year"] is None or node["last_ag_year"] is None:
            assert node["first_ag_year"] is None and node["last_ag_year"] is None
            assert node["years_missing"] is not None
        else:
            assert node["years_missing"] is None

    # DecisionOutput RangeAcrossScenarios.
    if {"minimum", "maximum", "scenario_of_the_minimum"}.issubset(node):
        triple = (
            node["minimum"],
            node["maximum"],
            node["scenario_of_the_minimum"],
        )
        if any(v is None for v in triple):
            assert all(v is None for v in triple)
            assert node.get("missing") is not None
        else:
            assert node.get("missing") is None

    # PlantAnswer flat value-or-reason shapes.
    if "reason" in node and "value" in node and "missing" not in node:
        # MarginOut, SoilLossOut, LimitCostOut
        if node["value"] is None:
            if not node.get("costs_nothing", False):
                assert node["reason"] in VALID_REASON_CODES, (
                    f"{path}: missing value requires C3.2 reason"
                )
            assert node.get("provenance") is None
            assert node.get("range") is None
            assert node.get("range_missing") is None
        else:
            assert node["reason"] is None, (
                f"{path}: present value must not carry a missing reason (C3.1)"
            )

    if "kind" in node and "missing_reason" in node:
        # YearKind
        if node["kind"] is None:
            assert node["missing_reason"] in VALID_REASON_CODES
        else:
            assert node["missing_reason"] is None

    if "price" in node and "takes_over" in node and "reason" in node:
        # TippingPointOut
        if node["price"] is None:
            assert node["reason"] in VALID_REASON_CODES
            assert node.get("takes_over") is None
            assert node.get("answer_after") is None
            assert node.get("distance_percent") is None
            assert node.get("provenance") is None

    for key, val in node.items():
        _assert_c3_invariants_in_tree(val, f"{path}.{key}")


def _collect_nested_example_data(node: Any, path: str = "root") -> list[tuple[str, bool]]:
    found: list[tuple[str, bool]] = []
    if isinstance(node, dict):
        if "example_data" in node:
            found.append((path, node["example_data"]))
        for key, val in node.items():
            found.extend(_collect_nested_example_data(val, f"{path}.{key}"))
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            found.extend(_collect_nested_example_data(item, f"{path}[{idx}]"))
    return found


# --- 1 & 2. Discovery, loading, and JSON round-trip --------------------------


def test_every_shipped_placeholder_example_is_mapped() -> None:
    on_disk = sorted(
        p.relative_to(CONTRACTS_DIR).as_posix()
        for p in CONTRACTS_DIR.glob("*/examples/PLACEHOLDER_*.json")
    )
    assert on_disk == sorted(EXAMPLE_MODELS)


@pytest.mark.parametrize("rel_path", sorted(EXAMPLE_MODELS))
def test_example_loads_and_roundtrips_with_identical_model_dump(rel_path: str) -> None:
    model_cls = EXAMPLE_MODELS[rel_path]
    raw_text = _read_example_text(rel_path)

    loaded = model_cls.model_validate_json(raw_text)
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(
        raw_text
    )

    serialized = loaded.model_dump_json()
    reloaded = model_cls.model_validate_json(serialized)

    assert reloaded.model_dump() == loaded.model_dump()
    assert reloaded.model_dump(mode="json") == loaded.model_dump(mode="json")
    assert reloaded == loaded

    reloaded_twice = model_cls.model_validate_json(reloaded.model_dump_json())
    assert reloaded_twice.model_dump() == loaded.model_dump()


# --- 3. example_data preservation --------------------------------------------


@pytest.mark.parametrize("rel_path", sorted(EXAMPLE_MODELS))
def test_example_data_is_preserved_across_roundtrip(rel_path: str) -> None:
    loaded, reloaded = _roundtrip(rel_path)
    if rel_path in RESULTS_EXAMPLES:
        assert "example_data" not in type(loaded).model_fields
        return

    assert getattr(loaded, "example_data") is True
    assert getattr(reloaded, "example_data") is True

    nested_before = _collect_nested_example_data(loaded.model_dump())
    nested_after = _collect_nested_example_data(reloaded.model_dump())
    assert nested_before == nested_after
    assert all(flag is True for _, flag in nested_after)


def test_example_data_false_preserved_and_composite_propagation_enforced() -> None:
    for rel_path in (
        "field_identity/examples/PLACEHOLDER_field_identity.json",
        "economic_facts/examples/PLACEHOLDER_economic_facts.json",
        "rotation_definition/examples/PLACEHOLDER_rotation_definition.json",
        "inputs/examples/PLACEHOLDER_chain_site_climate.json",
        "inputs/examples/PLACEHOLDER_chain_site_soil_slope.json",
        "inputs/examples/PLACEHOLDER_rotation_calendar.json",
        "residue_ledger/examples/PLACEHOLDER_residue_ledger.json",
        "carbon_forcing/examples/PLACEHOLDER_carbon_forcing.json",
        "carbon_balance/examples/PLACEHOLDER_carbon_balance.json",
        "decision_output/examples/PLACEHOLDER_decision_output.json",
        "green_cover/examples/PLACEHOLDER_green_cover.json",
    ):
        raw = json.loads(_read_example_text(rel_path))
        raw["example_data"] = False
        model_cls = EXAMPLE_MODELS[rel_path]
        loaded = model_cls.model_validate_json(json.dumps(raw))
        reloaded = model_cls.model_validate_json(loaded.model_dump_json())
        assert getattr(reloaded, "example_data") is False
        assert reloaded.model_dump() == loaded.model_dump()

    # SavedCase forbids example_data=False when any carried part has example_data=True.
    saved_raw = json.loads(_read_example_text("saved_case/examples/PLACEHOLDER_saved_case.json"))
    saved_false = copy.deepcopy(saved_raw)
    saved_false["example_data"] = False
    with pytest.raises(ValidationError, match="example_data"):
        SavedCase.model_validate_json(json.dumps(saved_false))

    # Setting example_data=False everywhere in SavedCase succeeds and round-trips.
    saved_false["field_identity"]["example_data"] = False
    saved_false["decision_output"]["example_data"] = False
    for item in saved_false["carbon_balances"]:
        if item["carbon_balance"] is not None:
            item["carbon_balance"]["example_data"] = False
    saved_loaded = SavedCase.model_validate_json(json.dumps(saved_false))
    saved_reloaded = SavedCase.model_validate_json(saved_loaded.model_dump_json())
    assert saved_reloaded.example_data is False
    assert saved_reloaded.model_dump() == saved_loaded.model_dump()


# --- 4. case_id / field_id / rotation_id alignment ---------------------------


def test_example_case_family_id_alignment_across_seams() -> None:
    _, identity = _roundtrip("field_identity/examples/PLACEHOLDER_field_identity.json")
    _, climate = _roundtrip("inputs/examples/PLACEHOLDER_chain_site_climate.json")
    _, soil = _roundtrip("inputs/examples/PLACEHOLDER_chain_site_soil_slope.json")
    _, rotation = _roundtrip(
        "rotation_definition/examples/PLACEHOLDER_rotation_definition.json"
    )
    _, facts = _roundtrip("economic_facts/examples/PLACEHOLDER_economic_facts.json")
    _, decision = _roundtrip("decision_output/examples/PLACEHOLDER_decision_output.json")
    _, saved = _roundtrip("saved_case/examples/PLACEHOLDER_saved_case.json")
    _, req = _roundtrip("plant_answer/examples/PLACEHOLDER_plant_request.json")
    _, ans = _roundtrip("plant_answer/examples/PLACEHOLDER_plant_answer.json")
    _, green_cover = _roundtrip("green_cover/examples/PLACEHOLDER_green_cover.json")

    assert isinstance(identity, FieldIdentity)
    assert isinstance(climate, SiteClimate)
    assert isinstance(soil, SiteSoilSlope)
    assert isinstance(rotation, RotationDefinition)
    assert isinstance(facts, EconomicFacts)
    assert isinstance(decision, DecisionOutput)
    assert isinstance(saved, SavedCase)
    assert isinstance(req, PlantRequest)
    assert isinstance(ans, PlantAnswer)
    assert isinstance(green_cover, GreenCoverStrip)

    expected_case = "example-case"
    expected_field = "example-field-1"
    known_fields = {f.field_id for f in identity.fields}
    assert expected_field in known_fields

    for doc in (climate, soil, rotation, facts, decision, saved, ans, green_cover):
        assert doc.case_id == expected_case
        assert doc.field_id == expected_field

    assert identity.case_id == expected_case
    assert req.site.case_id == expected_case
    assert req.site.field_id == expected_field
    assert rotation.rotation_id == "example-rotation-1"
    assert rotation.rotation_id in decision.rotations


def test_standalone_engine_seam_family_id_alignment() -> None:
    _, climate = _roundtrip("inputs/examples/PLACEHOLDER_site_climate.json")
    _, soil = _roundtrip("inputs/examples/PLACEHOLDER_site_soil_slope.json")
    _, calendar = _roundtrip("inputs/examples/PLACEHOLDER_rotation_calendar.json")
    _, ledger = _roundtrip("residue_ledger/examples/PLACEHOLDER_residue_ledger.json")
    _, forcing = _roundtrip("carbon_forcing/examples/PLACEHOLDER_carbon_forcing.json")
    _, balance = _roundtrip("carbon_balance/examples/PLACEHOLDER_carbon_balance.json")

    assert isinstance(climate, SiteClimate)
    assert isinstance(soil, SiteSoilSlope)
    assert isinstance(calendar, RotationCalendar)
    assert isinstance(ledger, ResidueLedger)
    assert isinstance(forcing, CarbonForcing)
    assert isinstance(balance, CarbonBalance)

    for doc in (climate, soil, calendar, ledger, forcing, balance):
        assert doc.case_id == "PLACEHOLDER-case"
        assert doc.field_id == "PLACEHOLDER-field"

    for rot_doc in (calendar, ledger, forcing, balance):
        assert rot_doc.rotation_id == "PLACEHOLDER-rotation"


def test_results_seam_family_id_alignment() -> None:
    _, per_rot = _roundtrip("results/examples/PLACEHOLDER_results_per_rotation.json")
    _, per_rot_nb = _roundtrip(
        "results/examples/PLACEHOLDER_results_per_rotation_not_built.json"
    )
    _, table = _roundtrip("results/examples/PLACEHOLDER_results_table.json")

    assert isinstance(per_rot, ResultsPerRotation)
    assert isinstance(per_rot_nb, ResultsPerRotation)
    assert isinstance(table, ResultsTable)

    for doc in (per_rot, per_rot_nb, table):
        assert doc.case_id == "PLACEHOLDER_case"
        assert doc.field_id == "PLACEHOLDER_field"

    table_rotations = {row.rotation_id for row in table.rows}
    assert per_rot.rotation_id in table_rotations
    assert per_rot_nb.rotation_id in table_rotations


def test_saved_case_internal_alignment_and_mismatch_rejection() -> None:
    _, saved = _roundtrip("saved_case/examples/PLACEHOLDER_saved_case.json")
    assert isinstance(saved, SavedCase)
    assert saved.field_identity is not None
    assert saved.results_table is not None
    assert saved.decision_output is not None

    assert saved.field_identity.case_id == saved.case_id
    assert saved.field_id in {f.field_id for f in saved.field_identity.fields}
    assert saved.results_table.case_id == saved.case_id
    assert saved.results_table.field_id == saved.field_id
    assert saved.decision_output.case_id == saved.case_id
    assert saved.decision_output.field_id == saved.field_id

    table_rotations = {row.rotation_id for row in saved.results_table.rows}
    item_rotations = {item.rotation_id for item in saved.carbon_balances}
    decision_rotations = set(saved.decision_output.rotations)
    assert table_rotations == item_rotations == decision_rotations

    for item in saved.carbon_balances:
        if item.carbon_balance is not None:
            assert item.carbon_balance.case_id == saved.case_id
            assert item.carbon_balance.field_id == saved.field_id
            assert item.carbon_balance.rotation_id == item.rotation_id

    # Cross-seam mismatches must fail validation.
    raw = json.loads(_read_example_text("saved_case/examples/PLACEHOLDER_saved_case.json"))

    bad_case = copy.deepcopy(raw)
    bad_case["results_table"]["case_id"] = "other-case"
    with pytest.raises(ValidationError, match="case_id"):
        SavedCase.model_validate_json(json.dumps(bad_case))

    bad_field = copy.deepcopy(raw)
    bad_field["decision_output"]["field_id"] = "other-field"
    with pytest.raises(ValidationError, match="field_id"):
        SavedCase.model_validate_json(json.dumps(bad_field))

    bad_rot = copy.deepcopy(raw)
    bad_rot["carbon_balances"][0]["carbon_balance"]["rotation_id"] = "example-rotation-2"
    with pytest.raises(ValidationError, match="rotation_id"):
        SavedCase.model_validate_json(json.dumps(bad_rot))


def test_plant_request_and_answer_alignment_and_mismatch_rejection() -> None:
    _, req = _roundtrip("plant_answer/examples/PLACEHOLDER_plant_request.json")
    _, ans = _roundtrip("plant_answer/examples/PLACEHOLDER_plant_answer.json")
    assert isinstance(req, PlantRequest)
    assert isinstance(ans, PlantAnswer)

    assert req.economic_facts.case_id == req.site.case_id
    assert req.economic_facts.field_id == req.site.field_id
    for rot in req.rotations:
        assert rot.case_id == req.site.case_id
        assert rot.field_id == req.site.field_id

    assert ans.case_id == req.site.case_id
    assert ans.field_id == req.site.field_id
    assert [o.rotation_id for o in ans.options] == [r.rotation_id for r in req.rotations]
    check_answer_against_request(req, ans)

    # Cross-seam mismatches must fail validation / check_answer_against_request.
    req_raw = json.loads(
        _read_example_text("plant_answer/examples/PLACEHOLDER_plant_request.json")
    )
    bad_req = copy.deepcopy(req_raw)
    bad_req["rotations"][0]["field_id"] = "other-field"
    with pytest.raises(ValidationError, match="field_id"):
        PlantRequest.model_validate_json(json.dumps(bad_req))

    ans_bad_case = ans.model_copy(update={"case_id": "other-case"})
    with pytest.raises(ValueError, match="case_id"):
        check_answer_against_request(req, ans_bad_case)

    ans_bad_rot = copy.deepcopy(ans.model_dump(mode="json"))
    ans_bad_rot["options"][0], ans_bad_rot["options"][1] = (
        ans_bad_rot["options"][1],
        ans_bad_rot["options"][0],
    )
    with pytest.raises(ValueError, match="rotation"):
        check_answer_against_request(req, PlantAnswer.model_validate(ans_bad_rot))


# --- 5. C3.1 / C3.2 missingness invariants -----------------------------------


@pytest.mark.parametrize("rel_path", sorted(EXAMPLE_MODELS))
def test_example_satisfies_c3_missingness_invariants(rel_path: str) -> None:
    loaded, reloaded = _roundtrip(rel_path)
    _assert_c3_invariants_in_tree(loaded.model_dump(mode="json"), rel_path)
    _assert_c3_invariants_in_tree(reloaded.model_dump(mode="json"), f"{rel_path}(rt)")


def test_c3_missing_reason_and_value_none_enforced_by_models() -> None:
    # C3.2: closed list of reason codes & MISSING_INPUT requires detail in both Missing models.
    for missing_cls in (Missing, ResultsMissing):
        for code in VALID_REASON_CODES:
            kwargs: dict[str, Any] = {"reason": code}
            if code == "MISSING_INPUT":
                with pytest.raises(ValidationError):
                    missing_cls.model_validate(kwargs)
                kwargs["detail"] = "PLACEHOLDER_input"
            m = missing_cls.model_validate(kwargs)
            rt = missing_cls.model_validate_json(m.model_dump_json())
            assert rt.model_dump() == m.model_dump()

        for bad_code in ("UNKNOWN_REASON", "not_available", ""):
            with pytest.raises(ValidationError):
                missing_cls.model_validate({"reason": bad_code})

    # C3.1: value is None when missing; never both value and missing, never neither.
    with pytest.raises(ValidationError):
        Value.model_validate({"value": None, "unit": "PLACEHOLDER_unit"})
    with pytest.raises(ValidationError):
        Value.model_validate(
            {
                "value": 0.0,
                "unit": "PLACEHOLDER_unit",
                "missing": {"reason": "NOT_AVAILABLE"},
            }
        )
    with pytest.raises(ValidationError):
        DateValue.model_validate({"date": None})
    with pytest.raises(ValidationError):
        DateValue.model_validate(
            {"date": "2026-01-01", "missing": {"reason": "NOT_DECLARED"}}
        )
    with pytest.raises(ValidationError):
        DailyValue.model_validate({"date": "2026-01-01", "value": None})
    with pytest.raises(ValidationError):
        DailyValue.model_validate(
            {
                "date": "2026-01-01",
                "value": 0.0,
                "missing": {"reason": "NO_COVERAGE"},
            }
        )
    with pytest.raises(ValidationError):
        MonthlyValue.model_validate({"year": 2026, "month": 1, "value": None})
    with pytest.raises(ValidationError):
        AnnualSoilLoss.model_validate(
            {
                "indicator": "soil_loss",
                "direction": "lower_is_better",
                "ag_year": 2026,
                "value": None,
                "unit": "t ha-1 yr-1",
            }
        )
    with pytest.raises(ValidationError):
        AnnualSoilLoss.model_validate(
            {
                "indicator": "soil_loss",
                "direction": "lower_is_better",
                "ag_year": 2026,
                "value": 0.0,
                "unit": "t ha-1 yr-1",
                "missing": {"reason": "NOT_AVAILABLE"},
            }
        )
