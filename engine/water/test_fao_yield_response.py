"""Tests for ``engine/water/fao_yield_response.py``.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Covers:
- Pure-Python FAO-33 seasonal, stagewise multiplicative, and stagewise
  most-sensitive water-limited yield response with zero hardcoded crop
  ``Ky``/``Ym`` constants (AST hygiene & impure-import guard).
- Typed ``Missing`` propagation (G4) for zero ``ETc`` (``NOT_APPLICABLE``),
  missing ``ETa``/``Ky``/``Ym`` (``MISSING_INPUT``), non-finite inputs
  (``NOT_COMPUTABLE``), and excess ``ETa > ETc`` (clamped + flagged or
  ``NOT_COMPUTABLE``).
- Pasture guard: pastures without a declared livestock utilization/conversion
  module return ``Missing(reason="MISSING_INPUT", detail="pasture yield without
  livestock module is incomplete")``, never ``0.0``.
- ``YieldModelContrastBundle`` side-by-side multi-model contrast across
  ``"DECLARED"``, ``"FAO_WATER_KY"``, ``"AQUACROP_OSPY_CONTRAST"``, and
  ``"GECROS_HYPOTHESIS"`` (``license_verified=False``, ``label="HYPOTHESIS"``),
  with ``allow_multi_model_average=False``, min/max range, and per-model
  trajectories.
- G1 purity/non-mutation, frozen dataclasses, and G5 caller validation.

Every yield, ``Ky``, and evapotranspiration figure in this test module is
synthetic PLACEHOLDER data chosen solely to verify algebraic identities and
invariants; no real agronomic calibration or parameter is stated or implied.
"""

from __future__ import annotations

import ast
import copy
import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import get_args

import pytest

from contracts.results.models import Missing
from contracts.rotation_definition.rotation_definition import Purpose
from engine.water import fao_yield_response
from engine.water.fao_yield_response import (
    CROP_PURPOSES,
    GECROS_REQUIRED_LABEL,
    PASTURE_INCOMPLETE_DETAIL,
    UNIT_YIELD_KG_HA,
    YIELD_MODEL_IDS,
    CropPurpose,
    ExternalYieldContrastEnvelope,
    FaoAnnualYieldInput,
    FaoWaterLimitedYieldResult,
    LivestockUtilizationStatus,
    ModelYieldEstimate,
    ModelYieldPoint,
    ModelYieldRange,
    StageWaterInput,
    YieldModelContrastBundle,
    build_yield_model_contrast_bundle,
    compute_fao_water_limited_yield,
)

# PLACEHOLDER synthetic test inputs (never real crop parameters).
PLACEHOLDER_YM = 4000.0  # PLACEHOLDER kg ha-1
PLACEHOLDER_KY = 1.1  # PLACEHOLDER
PLACEHOLDER_ETA = 300.0  # PLACEHOLDER mm
PLACEHOLDER_ETC = 400.0  # PLACEHOLDER mm


# --- AST hygiene, purity, contract parity, and frozen dataclasses -----------


def test_module_has_zero_hardcoded_crop_numbers_or_impure_imports():
    source_path = Path(fao_yield_response.__file__)
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)

    numeric_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert numeric_constants <= {0, 1}

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    forbidden_impure = {
        "os",
        "pathlib",
        "datetime",
        "time",
        "random",
        "urllib",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "json",
        "aquacrop",
        "numpy",
        "pandas",
        "pydantic",
    }
    assert imported_modules.isdisjoint(forbidden_impure)
    assert imported_modules <= {
        "__future__",
        "collections",
        "contracts",
        "dataclasses",
        "math",
        "typing",
    }


def test_crop_purpose_matches_rotation_definition_contract():
    assert get_args(CropPurpose) == get_args(Purpose)
    assert CROP_PURPOSES == get_args(Purpose)


def test_dataclasses_are_frozen_and_bundle_has_no_average_method():
    stage = StageWaterInput(
        stage="flowering", eta_mm=PLACEHOLDER_ETA, etc_mm=PLACEHOLDER_ETC, ky=1.0
    )
    with pytest.raises(FrozenInstanceError):
        stage.eta_mm = 100.0  # type: ignore[misc]

    result = compute_fao_water_limited_yield(
        ym_kg_ha=PLACEHOLDER_YM,
        ky=1.0,
        eta_mm=PLACEHOLDER_ETA,
        etc_mm=PLACEHOLDER_ETC,
    )
    assert isinstance(result, FaoWaterLimitedYieldResult)
    with pytest.raises(FrozenInstanceError):
        result.ya_kg_ha = 0.0  # type: ignore[misc]

    pt = ModelYieldPoint(ag_year=2021, value=2500.0)
    with pytest.raises(FrozenInstanceError):
        pt.value = 1000.0  # type: ignore[misc]

    for forbidden_attr in ("average", "mean", "multi_model_average", "mean_yield"):
        assert not hasattr(YieldModelContrastBundle, forbidden_attr)
        assert not hasattr(ModelYieldRange, forbidden_attr)


def test_signature_has_no_default_ym_and_requires_keyword_arguments():
    sig = inspect.signature(compute_fao_water_limited_yield)
    assert sig.parameters["ym_kg_ha"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["ym_kg_ha"].default is inspect.Parameter.empty


# --- G1: purity & non-mutation ----------------------------------------------


def test_pure_deterministic_and_does_not_mutate_inputs():
    stages = [
        StageWaterInput(stage="vegetative", eta_mm=100.0, etc_mm=120.0, ky=0.5),
        StageWaterInput(stage="flowering", eta_mm=80.0, etc_mm=100.0, ky=1.2),
    ]
    stages_snapshot = copy.deepcopy(stages)

    first = compute_fao_water_limited_yield(
        ym_kg_ha=PLACEHOLDER_YM,
        stages=stages,
        method="stagewise_multiplicative",
    )
    second = compute_fao_water_limited_yield(
        ym_kg_ha=PLACEHOLDER_YM,
        stages=stages,
        method="stagewise_multiplicative",
    )
    assert first == second
    assert stages == stages_snapshot

    fao_inputs = [
        FaoAnnualYieldInput(
            ag_year=2021,
            ym_kg_ha=PLACEHOLDER_YM,
            ky=1.0,
            eta_mm=300.0,
            etc_mm=400.0,
        )
    ]
    fao_snapshot = copy.deepcopy(fao_inputs)
    bundle_a = build_yield_model_contrast_bundle(
        crop_id="placeholder_crop",
        crop_purpose="grain",
        fao_inputs=fao_inputs,
    )
    bundle_b = build_yield_model_contrast_bundle(
        crop_id="placeholder_crop",
        crop_purpose="grain",
        fao_inputs=fao_inputs,
    )
    assert bundle_a == bundle_b
    assert fao_inputs == fao_snapshot


# --- FAO-33 seasonal yield response -----------------------------------------


def test_seasonal_fao33_exact_equation_and_bounds():
    # Full ETa == ETc -> Ya == Ym
    full = compute_fao_water_limited_yield(
        ym_kg_ha=PLACEHOLDER_YM,
        ky=PLACEHOLDER_KY,
        eta_mm=PLACEHOLDER_ETC,
        etc_mm=PLACEHOLDER_ETC,
    )
    assert isinstance(full, FaoWaterLimitedYieldResult)
    assert full.ya_kg_ha == pytest.approx(PLACEHOLDER_YM)
    assert full.relative_yield == pytest.approx(1.0)
    assert full.yield_reduction_fraction == pytest.approx(0.0)
    assert full.eta_exceeded_etc is False
    assert full.clamped_at_zero is False
    assert full.unit == UNIT_YIELD_KG_HA
    assert full.provenance == "DERIVED"

    # Deficit: 1 - Ya/Ym = Ky * (1 - ETa/ETc)
    # 1 - 1.2 * (1 - 300/400) = 1 - 1.2 * 0.25 = 0.70 -> Ya = 4000 * 0.70 = 2800
    deficit = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        ky=1.2,
        eta_mm=300.0,
        etc_mm=400.0,
    )
    assert isinstance(deficit, FaoWaterLimitedYieldResult)
    assert deficit.relative_yield == pytest.approx(0.70)
    assert deficit.yield_reduction_fraction == pytest.approx(0.30)
    assert deficit.ya_kg_ha == pytest.approx(2800.0)
    assert deficit.clamped_at_zero is False

    # Ky == 0 -> completely insensitive -> Ya == Ym even under deficit
    insensitive = compute_fao_water_limited_yield(
        ym_kg_ha=3500.0,
        ky=0.0,
        eta_mm=100.0,
        etc_mm=400.0,
    )
    assert isinstance(insensitive, FaoWaterLimitedYieldResult)
    assert insensitive.ya_kg_ha == pytest.approx(3500.0)

    # Severe deficit with Ky > 1 clamps Ya >= 0.0 and marks clamped_at_zero
    # 1 - 1.5 * (1 - 50/400) = 1 - 1.5 * 0.875 = -0.3125 -> clamped to 0.0
    severe = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        ky=1.5,
        eta_mm=50.0,
        etc_mm=400.0,
    )
    assert isinstance(severe, FaoWaterLimitedYieldResult)
    assert severe.relative_yield == 0.0
    assert severe.ya_kg_ha == 0.0
    assert severe.clamped_at_zero is True


def test_seasonal_fao33_accepts_stage_series_by_summing():
    stages = (
        StageWaterInput(stage="initial", eta_mm=40.0, etc_mm=50.0),
        StageWaterInput(stage="mid", eta_mm=160.0, etc_mm=200.0),
        StageWaterInput(stage="late", eta_mm=100.0, etc_mm=150.0),
    )
    # Sum ETa = 300, Sum ETc = 400; Ky = 1.0 -> 1 - 1*(1 - 300/400) = 0.75
    res = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        ky=1.0,
        stages=stages,
        method="seasonal",
    )
    assert isinstance(res, FaoWaterLimitedYieldResult)
    assert res.eta_mm == pytest.approx(300.0)
    assert res.etc_mm == pytest.approx(400.0)
    assert res.ya_kg_ha == pytest.approx(3000.0)
    assert res.stages == ()


# --- FAO-33 stagewise multiplicative & most-sensitive -----------------------


def test_stagewise_multiplicative_and_most_sensitive():
    stages = (
        StageWaterInput(stage="initial", eta_mm=50.0, etc_mm=50.0, ky=0.4),  # r = 1.0
        StageWaterInput(stage="dev", eta_mm=80.0, etc_mm=100.0, ky=0.8),  # r = 0.84
        StageWaterInput(stage="mid", eta_mm=100.0, etc_mm=100.0, ky=1.2),  # r = 1.0
        StageWaterInput(stage="late", eta_mm=40.0, etc_mm=50.0, ky=0.5),  # r = 0.90
    )

    mult = compute_fao_water_limited_yield(
        ym_kg_ha=5000.0,
        stages=stages,
        method="stagewise_multiplicative",
    )
    assert isinstance(mult, FaoWaterLimitedYieldResult)
    assert mult.relative_yield == pytest.approx(1.0 * 0.84 * 1.0 * 0.90)
    assert mult.ya_kg_ha == pytest.approx(5000.0 * 0.756)
    assert mult.ky is None
    assert len(mult.stages) == 4
    assert mult.stages[1].stage == "dev"
    assert mult.stages[1].relative_yield == pytest.approx(0.84)

    most = compute_fao_water_limited_yield(
        ym_kg_ha=5000.0,
        stages=stages,
        method="stagewise_most_sensitive",
    )
    assert isinstance(most, FaoWaterLimitedYieldResult)
    assert most.relative_yield == pytest.approx(0.84)
    assert most.ya_kg_ha == pytest.approx(5000.0 * 0.84)
    assert most.ya_kg_ha > mult.ya_kg_ha


# --- Excess ETa > ETc handling ----------------------------------------------


def test_excess_eta_clamps_and_flags_or_returns_not_computable():
    # Seasonal clamp (default)
    clamped = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        ky=1.1,
        eta_mm=450.0,
        etc_mm=400.0,
        excess_eta_policy="clamp",
    )
    assert isinstance(clamped, FaoWaterLimitedYieldResult)
    assert clamped.eta_mm == pytest.approx(450.0)
    assert clamped.etc_mm == pytest.approx(400.0)
    assert clamped.effective_eta_mm == pytest.approx(400.0)
    assert clamped.eta_exceeded_etc is True
    assert clamped.ya_kg_ha == pytest.approx(4000.0)

    # Seasonal strict rejection
    flagged = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        ky=1.1,
        eta_mm=450.0,
        etc_mm=400.0,
        excess_eta_policy="not_computable",
    )
    assert isinstance(flagged, Missing)
    assert flagged.reason == "NOT_COMPUTABLE"

    # Stagewise clamp flags the affected stage
    stages = (
        StageWaterInput(stage="initial", eta_mm=70.0, etc_mm=50.0, ky=0.4),
        StageWaterInput(stage="mid", eta_mm=80.0, etc_mm=100.0, ky=1.0),
    )
    stage_clamped = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        stages=stages,
        method="stagewise_multiplicative",
        excess_eta_policy="clamp",
    )
    assert isinstance(stage_clamped, FaoWaterLimitedYieldResult)
    assert stage_clamped.eta_exceeded_etc is True
    assert stage_clamped.stages[0].eta_exceeded_etc is True
    assert stage_clamped.stages[0].effective_eta_mm == pytest.approx(50.0)
    assert stage_clamped.stages[1].eta_exceeded_etc is False
    assert stage_clamped.ya_kg_ha == pytest.approx(4000.0 * 0.80)

    stage_rejected = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        stages=stages,
        method="stagewise_most_sensitive",
        excess_eta_policy="not_computable",
    )
    assert isinstance(stage_rejected, Missing)
    assert stage_rejected.reason == "NOT_COMPUTABLE"


# --- Zero ETc and missing ETa / Ky / Ym (G4) --------------------------------


def test_zero_etc_and_missing_inputs_return_typed_missing():
    # Zero ETc -> NOT_APPLICABLE
    zero_etc = compute_fao_water_limited_yield(
        ym_kg_ha=PLACEHOLDER_YM,
        ky=PLACEHOLDER_KY,
        eta_mm=0.0,
        etc_mm=0.0,
    )
    assert isinstance(zero_etc, Missing)
    assert zero_etc.reason == "NOT_APPLICABLE"

    # Zero ETc in a stage -> NOT_APPLICABLE
    stage_zero_etc = compute_fao_water_limited_yield(
        ym_kg_ha=PLACEHOLDER_YM,
        stages=(StageWaterInput(stage="mid", eta_mm=0.0, etc_mm=0.0, ky=1.0),),
        method="stagewise_multiplicative",
    )
    assert isinstance(stage_zero_etc, Missing)
    assert stage_zero_etc.reason == "NOT_APPLICABLE"

    # Empty stages -> NOT_APPLICABLE
    empty_stages = compute_fao_water_limited_yield(
        ym_kg_ha=PLACEHOLDER_YM,
        stages=(),
        method="stagewise_most_sensitive",
    )
    assert isinstance(empty_stages, Missing)
    assert empty_stages.reason == "NOT_APPLICABLE"

    # Missing Ym / Ky / ETa / ETc (None) -> MISSING_INPUT
    for kwargs in (
        {"ym_kg_ha": None, "ky": 1.0, "eta_mm": 100.0, "etc_mm": 200.0},
        {"ym_kg_ha": 4000.0, "ky": None, "eta_mm": 100.0, "etc_mm": 200.0},
        {"ym_kg_ha": 4000.0, "ky": 1.0, "eta_mm": None, "etc_mm": 200.0},
        {"ym_kg_ha": 4000.0, "ky": 1.0, "eta_mm": 100.0, "etc_mm": None},
        {"ym_kg_ha": 4000.0, "stages": None, "method": "stagewise_multiplicative"},
    ):
        res = compute_fao_water_limited_yield(**kwargs)  # type: ignore[arg-type]
        assert isinstance(res, Missing)
        assert res.reason == "MISSING_INPUT"

    # Stagewise missing stage Ky -> MISSING_INPUT
    missing_stage_ky = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        stages=(StageWaterInput(stage="mid", eta_mm=100.0, etc_mm=200.0, ky=None),),
        method="stagewise_multiplicative",
    )
    assert isinstance(missing_stage_ky, Missing)
    assert missing_stage_ky.reason == "MISSING_INPUT"

    # Propagates caller-supplied Missing unchanged
    upstream = Missing(reason="NO_COVERAGE", detail="upstream climate gap")
    prop = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        ky=1.0,
        eta_mm=upstream,
        etc_mm=200.0,
    )
    assert prop == upstream

    # Non-finite values -> NOT_COMPUTABLE
    nan_res = compute_fao_water_limited_yield(
        ym_kg_ha=4000.0,
        ky=1.0,
        eta_mm=float("nan"),
        etc_mm=200.0,
    )
    assert isinstance(nan_res, Missing)
    assert nan_res.reason == "NOT_COMPUTABLE"


# --- Pasture guard ----------------------------------------------------------


def test_pasture_without_livestock_module_returns_exact_missing_never_zero():
    res = compute_fao_water_limited_yield(
        ym_kg_ha=6000.0,
        ky=1.0,
        eta_mm=400.0,
        etc_mm=400.0,
        crop_purpose="pasture",
        livestock_module_declared=False,
    )
    assert isinstance(res, Missing)
    assert res == Missing(
        reason="MISSING_INPUT",
        detail="pasture yield without livestock module is incomplete",
    )
    assert res != 0.0

    # With livestock module declared + conversion factor
    with_livestock = compute_fao_water_limited_yield(
        ym_kg_ha=6000.0,
        ky=1.0,
        eta_mm=300.0,
        etc_mm=400.0,
        crop_purpose="pasture",
        livestock_module_declared=True,
        livestock_conversion_factor=0.6,
    )
    assert isinstance(with_livestock, FaoWaterLimitedYieldResult)
    # 6000 * 0.75 * 0.6 = 2700.0
    assert with_livestock.ya_kg_ha == pytest.approx(2700.0)
    assert with_livestock.livestock_conversion_factor == pytest.approx(0.6)


# --- YieldModelContrastBundle -----------------------------------------------


def test_contrast_bundle_side_by_side_ranges_and_gecros_hypothesis_rules():
    fao_inputs = (
        FaoAnnualYieldInput(
            ag_year=2021,
            ym_kg_ha=4000.0,
            ky=1.0,
            eta_mm=300.0,
            etc_mm=400.0,
        ),  # 3000.0
        FaoAnnualYieldInput(
            ag_year=2022,
            ym_kg_ha=4000.0,
            ky=1.0,
            eta_mm=400.0,
            etc_mm=400.0,
        ),  # 4000.0
    )
    declared_traj = (
        ModelYieldPoint(ag_year=2021, value=2600.0),
        ModelYieldPoint(ag_year=2022, value=3800.0),
    )
    aquacrop_env = ExternalYieldContrastEnvelope(
        model_id="AQUACROP_OSPY_CONTRAST",
        trajectory=(
            ModelYieldPoint(ag_year=2021, value=3200.0),
            ModelYieldPoint(ag_year=2022, value=3900.0),
        ),
        license_verified=True,
        label="EXTERNAL_CONTRAST",
        source="PLACEHOLDER external AquaCrop-OSPy contrast",
    )
    gecros_env = ExternalYieldContrastEnvelope(
        model_id="GECROS_HYPOTHESIS",
        trajectory=(
            ModelYieldPoint(ag_year=2021, value=3500.0),
            ModelYieldPoint(ag_year=2022, value=4200.0),
        ),
        license_verified=False,
        label=GECROS_REQUIRED_LABEL,
        source="PLACEHOLDER GECROS hypothesis run",
    )

    bundle = build_yield_model_contrast_bundle(
        crop_id="placeholder_soybean",
        crop_purpose="grain",
        fao_inputs=fao_inputs,
        declared_trajectory=declared_traj,
        declared_source="PLACEHOLDER declared yield",
        aquacrop_contrast=aquacrop_env,
        gecros_hypothesis=gecros_env,
    )

    assert bundle.allow_multi_model_average is False
    assert tuple(bundle.models.keys()) == YIELD_MODEL_IDS
    assert bundle.gecros_hypothesis.license_verified is False
    assert bundle.gecros_hypothesis.label == "HYPOTHESIS"

    trajectories = bundle.per_model_trajectories()
    assert [pt.value for pt in trajectories["DECLARED"]] == [2600.0, 3800.0]
    assert [pt.value for pt in trajectories["FAO_WATER_KY"]] == [3000.0, 4000.0]
    assert [pt.value for pt in trajectories["AQUACROP_OSPY_CONTRAST"]] == [
        3200.0,
        3900.0,
    ]
    assert [pt.value for pt in trajectories["GECROS_HYPOTHESIS"]] == [3500.0, 4200.0]

    # Including hypothesis
    ranges_all = bundle.range_by_year(include_hypothesis=True)
    assert ranges_all[2021] == ModelYieldRange(
        ag_year=2021,
        min_kg_ha=2600.0,
        max_kg_ha=3500.0,
        min_model_id="DECLARED",
        max_model_id="GECROS_HYPOTHESIS",
        included_model_ids=YIELD_MODEL_IDS,
        includes_hypothesis=True,
    )
    assert ranges_all[2022] == ModelYieldRange(
        ag_year=2022,
        min_kg_ha=3800.0,
        max_kg_ha=4200.0,
        min_model_id="DECLARED",
        max_model_id="GECROS_HYPOTHESIS",
        included_model_ids=YIELD_MODEL_IDS,
        includes_hypothesis=True,
    )

    # Excluding hypothesis
    ranges_verified = bundle.range_by_year(include_hypothesis=False)
    assert ranges_verified[2021] == ModelYieldRange(
        ag_year=2021,
        min_kg_ha=2600.0,
        max_kg_ha=3200.0,
        min_model_id="DECLARED",
        max_model_id="AQUACROP_OSPY_CONTRAST",
        included_model_ids=("DECLARED", "FAO_WATER_KY", "AQUACROP_OSPY_CONTRAST"),
        includes_hypothesis=False,
    )
    assert ranges_verified[2022] == ModelYieldRange(
        ag_year=2022,
        min_kg_ha=3800.0,
        max_kg_ha=4000.0,
        min_model_id="DECLARED",
        max_model_id="FAO_WATER_KY",
        included_model_ids=("DECLARED", "FAO_WATER_KY", "AQUACROP_OSPY_CONTRAST"),
        includes_hypothesis=False,
    )


def test_contrast_bundle_pasture_without_livestock_module_never_zero():
    bundle = build_yield_model_contrast_bundle(
        crop_id="placeholder_alfalfa",
        crop_purpose="pasture",
        fao_inputs=(
            FaoAnnualYieldInput(
                ag_year=2021,
                ym_kg_ha=8000.0,
                ky=1.0,
                eta_mm=400.0,
                etc_mm=400.0,
            ),
        ),
        declared_trajectory=(ModelYieldPoint(ag_year=2021, value=7500.0),),
        declared_source="PLACEHOLDER",
        livestock_status=LivestockUtilizationStatus(declared=False),
    )

    expected_missing = Missing(
        reason="MISSING_INPUT",
        detail=PASTURE_INCOMPLETE_DETAIL,
    )
    for model_id, est in bundle.models.items():
        assert len(est.trajectory) == 1
        assert est.trajectory[0].value == expected_missing, model_id
        assert est.provenance is None

    ranges = bundle.range_by_year()
    assert ranges[2021] == expected_missing


def test_contrast_bundle_handles_absent_envelopes_and_all_missing_year():
    bundle = build_yield_model_contrast_bundle(
        crop_id="placeholder_soybean",
        crop_purpose="grain",
        fao_inputs=(
            FaoAnnualYieldInput(
                ag_year=2021,
                ym_kg_ha=4000.0,
                ky=1.0,
                eta_mm=0.0,
                etc_mm=0.0,  # NOT_APPLICABLE
            ),
        ),
    )
    assert bundle.declared.missing is not None
    assert bundle.declared.missing.reason == "NOT_DECLARED"
    assert bundle.aquacrop_ospy_contrast.missing is not None
    assert bundle.aquacrop_ospy_contrast.missing.reason == "NOT_AVAILABLE"
    assert bundle.gecros_hypothesis.license_verified is False
    assert bundle.gecros_hypothesis.label == "HYPOTHESIS"
    assert bundle.gecros_hypothesis.missing is not None
    assert bundle.gecros_hypothesis.missing.reason == "NOT_AVAILABLE"

    ranges = bundle.range_by_year()
    assert isinstance(ranges[2021], Missing)
    assert ranges[2021].reason == "NOT_APPLICABLE"


# --- Invariant & G5 caller defect checks ------------------------------------


def test_bundle_forbids_averaging_and_gecros_license_or_pasture_bypass():
    def _missing_slot(mid, lbl="REF", lv=True):
        return ModelYieldEstimate(
            model_id=mid,
            trajectory=(),
            license_verified=lv,
            label=lbl,
            missing=Missing(reason="NOT_AVAILABLE", detail="none"),
        )

    with pytest.raises(ValueError, match="allow_multi_model_average"):
        YieldModelContrastBundle(
            crop_id="c",
            crop_purpose="grain",
            livestock_module_declared=False,
            declared=_missing_slot("DECLARED"),
            fao_water_ky=_missing_slot("FAO_WATER_KY"),
            aquacrop_ospy_contrast=_missing_slot("AQUACROP_OSPY_CONTRAST"),
            gecros_hypothesis=_missing_slot("GECROS_HYPOTHESIS", "HYPOTHESIS", False),
            allow_multi_model_average=True,
        )

    with pytest.raises(ValueError, match="license_verified=False"):
        ExternalYieldContrastEnvelope(
            model_id="GECROS_HYPOTHESIS",
            trajectory=(),
            license_verified=True,
            label="HYPOTHESIS",
            source="PLACEHOLDER",
        )

    with pytest.raises(ValueError, match="label='HYPOTHESIS'"):
        ModelYieldEstimate(
            model_id="GECROS_HYPOTHESIS",
            trajectory=(),
            license_verified=False,
            label="PRODUCTION",
            missing=Missing(reason="NOT_AVAILABLE", detail="none"),
        )

    with pytest.raises(ValueError, match="pasture yield without livestock module"):
        YieldModelContrastBundle(
            crop_id="alfalfa",
            crop_purpose="pasture",
            livestock_module_declared=False,
            declared=ModelYieldEstimate(
                model_id="DECLARED",
                trajectory=(ModelYieldPoint(ag_year=2021, value=0.0),),
                license_verified=True,
                label="DECLARED",
                provenance="DECLARED",
                source="PLACEHOLDER",
            ),
            fao_water_ky=_missing_slot("FAO_WATER_KY"),
            aquacrop_ospy_contrast=_missing_slot("AQUACROP_OSPY_CONTRAST"),
            gecros_hypothesis=_missing_slot("GECROS_HYPOTHESIS", "HYPOTHESIS", False),
        )


def test_g5_caller_type_and_domain_errors():
    # bool rejected as number
    with pytest.raises(TypeError):
        compute_fao_water_limited_yield(
            ym_kg_ha=True,  # type: ignore[arg-type]
            ky=1.0,
            eta_mm=100.0,
            etc_mm=200.0,
        )
    with pytest.raises(TypeError):
        ModelYieldPoint(ag_year=True, value=100.0)  # type: ignore[arg-type]

    # negative physical numbers rejected
    with pytest.raises(ValueError):
        compute_fao_water_limited_yield(
            ym_kg_ha=-1.0, ky=1.0, eta_mm=100.0, etc_mm=200.0
        )
    with pytest.raises(ValueError):
        compute_fao_water_limited_yield(
            ym_kg_ha=4000.0, ky=-0.1, eta_mm=100.0, etc_mm=200.0
        )

    # ambiguous seasonal input (both scalar and stages)
    with pytest.raises(ValueError):
        compute_fao_water_limited_yield(
            ym_kg_ha=4000.0,
            ky=1.0,
            eta_mm=100.0,
            etc_mm=200.0,
            stages=(StageWaterInput(stage="mid", eta_mm=100.0, etc_mm=200.0),),
            method="seasonal",
        )

    # scalar eta/etc rejected in stagewise mode
    with pytest.raises(ValueError):
        compute_fao_water_limited_yield(
            ym_kg_ha=4000.0,
            eta_mm=100.0,
            etc_mm=200.0,
            method="stagewise_multiplicative",
        )

    # duplicate stage name rejected
    with pytest.raises(ValueError):
        compute_fao_water_limited_yield(
            ym_kg_ha=4000.0,
            stages=(
                StageWaterInput(stage="mid", eta_mm=50.0, etc_mm=100.0, ky=1.0),
                StageWaterInput(stage="mid", eta_mm=60.0, etc_mm=100.0, ky=1.0),
            ),
            method="stagewise_multiplicative",
        )

    # livestock_conversion_factor on non-pasture rejected
    with pytest.raises(ValueError):
        compute_fao_water_limited_yield(
            ym_kg_ha=4000.0,
            ky=1.0,
            eta_mm=100.0,
            etc_mm=200.0,
            crop_purpose="grain",
            livestock_conversion_factor=0.5,
        )

    # duplicate or unsorted ag_year rejected in trajectory
    with pytest.raises(ValueError):
        ModelYieldEstimate(
            model_id="DECLARED",
            trajectory=(
                ModelYieldPoint(ag_year=2022, value=3000.0),
                ModelYieldPoint(ag_year=2021, value=2500.0),
            ),
            license_verified=True,
            label="DECLARED",
            provenance="DECLARED",
            source="PLACEHOLDER",
        )
