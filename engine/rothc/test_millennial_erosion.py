"""Tests for ``engine/rothc/millennial_erosion.py`` (Frontier Unit F-13).

Every number in this file is a synthetic PLACEHOLDER chosen solely for
hand-verifiable arithmetic, boundary checks, and mass-conservation audits.
"""

from __future__ import annotations

import ast
import copy
import inspect
import math
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.rothc.millennial_erosion import (
    COUPLED_EROSION_STATUS,
    PROPOSED_STATUS,
    LateralCarbonLoss,
    LateralErosionInput,
    MillennialErosionParams,
    MillennialPoolState,
    MillennialRunResult,
    MillennialStepInput,
    MillennialStepResult,
    compute_lateral_c_loss,
    run_millennial_erosion,
    step_millennial_erosion,
)

MODULE_PATH = Path(__file__).with_name("millennial_erosion.py")

# PLACEHOLDER synthetic parameter set (no real agronomic values).
PLACEHOLDER_PARAMS = MillennialErosionParams(
    pom_input_fraction=0.6,
    pom_decay_fraction=0.5,
    pom_to_maom_fraction=0.4,
    maom_decay_fraction=0.1,
    maom_max_t_c_ha=30.0,
    excess_maom_to_pom_fraction=0.5,
)

ABSENT_INPUT = InputMissing(reason="NOT_DECLARED", detail="placeholder absent input")
ABSENT_RESULT = ResultMissing(reason="NO_COVERAGE", detail="placeholder absent result")
BOTH_MISSING_SHAPES = (ABSENT_INPUT, ABSENT_RESULT)
NOT_FINITE_VALUES = (math.nan, math.inf, -math.inf, 10**400)


def _assert_mass_conservation(result: MillennialStepResult) -> None:
    lhs = math.fsum((result.delta_pom, result.delta_maom))
    rhs = math.fsum((result.c_input, -result.c_respired, -result.c_eroded))
    assert math.isclose(lhs, rhs, rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(result.mass_balance_residual, 0.0, abs_tol=1e-12)


def test_status_labels_and_frozen_dataclasses():
    assert PROPOSED_STATUS == "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
    assert COUPLED_EROSION_STATUS == "HYPOTHESIS"

    state = MillennialPoolState(pom=5.0, maom=10.0)
    with pytest.raises(FrozenInstanceError):
        state.pom = 9.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        PLACEHOLDER_PARAMS.maom_max_t_c_ha = 99.0  # type: ignore[misc]

    erosion = LateralErosionInput(
        soil_loss_Mg_ha=2.0,
        topsoil_soc_fraction=0.02,
        enrichment_ratio=1.5,
    )
    with pytest.raises(FrozenInstanceError):
        erosion.soil_loss_Mg_ha = 4.0  # type: ignore[misc]


def test_hand_calculated_uncapped_step_without_erosion():
    # Start: pom=10.0, maom=20.0, c_input=5.0
    # input_to_pom = 5.0 * 0.6 = 3.0; input_to_maom = 2.0
    # pom_available = 13.0; pom_decomposed = 6.5; pom_remaining = 6.5
    # pom_to_maom = 6.5 * 0.4 = 2.6; pom_respired = 3.9
    # maom_respired = 20.0 * 0.1 = 2.0; maom_retained = 18.0
    # sorption_demand = 2.0 + 2.6 = 4.6 <= headroom (30.0 - 18.0 = 12.0)
    # end: pom=6.5, maom=22.6, c_respired=5.9, c_eroded=0.0
    state = MillennialPoolState(pom=10.0, maom=20.0)
    res = step_millennial_erosion(
        state=state,
        c_input=5.0,
        params=PLACEHOLDER_PARAMS,
    )
    assert isinstance(res, MillennialStepResult)
    assert res.end.pom == pytest.approx(6.5)
    assert res.end.maom == pytest.approx(22.6)
    assert res.end.maom <= PLACEHOLDER_PARAMS.maom_max_t_c_ha
    assert res.c_respired == pytest.approx(5.9)
    assert res.c_eroded == 0.0
    assert res.maom_sorption_excess == 0.0
    assert res.coupled_erosion_applied is False
    assert res.coupled_erosion_status == "HYPOTHESIS"
    assert res.status == PROPOSED_STATUS
    _assert_mass_conservation(res)


@pytest.mark.parametrize("excess_to_pom_frac", [0.0, 0.25, 1.0])
def test_maom_capacity_ceiling_and_excess_partition(excess_to_pom_frac: float):
    # maom starts near ceiling (29.0 vs max 30.0); large input saturates sorption.
    params = MillennialErosionParams(
        pom_input_fraction=0.5,
        pom_decay_fraction=0.5,
        pom_to_maom_fraction=0.5,
        maom_decay_fraction=0.0,
        maom_max_t_c_ha=30.0,
        excess_maom_to_pom_fraction=excess_to_pom_frac,
    )
    state = MillennialPoolState(pom=4.0, maom=29.0)
    # input_to_pom = 5.0, input_to_maom = 5.0
    # pom_available = 9.0, pom_decomposed = 4.5, pom_remaining = 4.5
    # pom_to_maom = 2.25, pom_respired = 2.25
    # sorption_demand = 7.25, headroom = 1.0 -> maom_sorbed = 1.0, excess = 6.25
    res = step_millennial_erosion(state=state, c_input=10.0, params=params)
    assert isinstance(res, MillennialStepResult)
    assert res.end.maom == pytest.approx(30.0)
    assert res.end.maom <= 30.0
    assert res.maom_sorption_excess == pytest.approx(6.25)
    expected_excess_pom = 6.25 * excess_to_pom_frac
    expected_excess_resp = 6.25 * (1.0 - excess_to_pom_frac)
    assert res.end.pom == pytest.approx(4.5 + expected_excess_pom)
    assert res.excess_respired == pytest.approx(expected_excess_resp)
    assert res.c_respired == pytest.approx(2.25 + expected_excess_resp)
    _assert_mass_conservation(res)


def test_coupled_erosion_is_opt_in_and_never_silently_alters_baseline():
    state = MillennialPoolState(pom=10.0, maom=20.0)
    erosion = LateralErosionInput(
        soil_loss_Mg_ha=10.0,
        topsoil_soc_fraction=0.02,
        enrichment_ratio=1.5,
    )
    baseline_no_arg = step_millennial_erosion(
        state=state,
        c_input=5.0,
        params=PLACEHOLDER_PARAMS,
    )
    baseline_flag_false = step_millennial_erosion(
        state=state,
        c_input=5.0,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=False,
        erosion_input=erosion,
    )
    assert baseline_no_arg == baseline_flag_false
    assert isinstance(baseline_flag_false, MillennialStepResult)
    assert baseline_flag_false.coupled_erosion_applied is False
    assert baseline_flag_false.coupled_erosion_status == "HYPOTHESIS"
    assert baseline_flag_false.c_eroded == 0.0

    coupled = step_millennial_erosion(
        state=state,
        c_input=5.0,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
        erosion_input=erosion,
    )
    assert isinstance(coupled, MillennialStepResult)
    assert coupled.coupled_erosion_applied is True
    assert coupled.coupled_erosion_status == "HYPOTHESIS"
    # c_eroded = 10.0 * 0.02 * 1.5 = 0.30 t C ha-1
    assert coupled.c_eroded == pytest.approx(0.30)
    assert coupled.end.total == pytest.approx(baseline_no_arg.end.total - 0.30)
    _assert_mass_conservation(coupled)


def test_compute_lateral_c_loss_exact_formula():
    loss = compute_lateral_c_loss(
        soil_loss_Mg_ha=4.0,
        topsoil_soc_fraction=0.025,
        enrichment_ratio=2.0,
    )
    assert isinstance(loss, LateralCarbonLoss)
    assert loss.c_eroded_t_c_ha == pytest.approx(0.20)
    assert loss.status == "HYPOTHESIS"


@pytest.mark.parametrize(
    "field",
    ["soil_loss_Mg_ha", "topsoil_soc_fraction", "enrichment_ratio"],
)
@pytest.mark.parametrize("bad_value", [*BOTH_MISSING_SHAPES, *NOT_FINITE_VALUES])
def test_lateral_c_loss_missing_or_non_finite_returns_missing_input(
    field: str, bad_value: object
):
    kwargs: dict[str, object] = {
        "soil_loss_Mg_ha": 4.0,
        "topsoil_soc_fraction": 0.025,
        "enrichment_ratio": 2.0,
    }
    kwargs[field] = bad_value
    result = compute_lateral_c_loss(**kwargs)  # type: ignore[arg-type]
    assert isinstance(result, ResultMissing)
    assert result.reason == "MISSING_INPUT"
    assert result.detail is not None and field in result.detail

    # Same guarantee when coupled into step_millennial_erosion
    step_res = step_millennial_erosion(
        state=MillennialPoolState(pom=10.0, maom=20.0),
        c_input=5.0,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
        erosion_input=LateralErosionInput(**kwargs),  # type: ignore[arg-type]
    )
    assert isinstance(step_res, ResultMissing)
    assert step_res.reason == "MISSING_INPUT"
    assert step_res.detail is not None and field in step_res.detail


def test_coupled_erosion_with_absent_erosion_input_returns_missing_input():
    res_none = step_millennial_erosion(
        state=MillennialPoolState(pom=10.0, maom=20.0),
        c_input=5.0,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
        erosion_input=None,
    )
    assert isinstance(res_none, ResultMissing)
    assert res_none.reason == "MISSING_INPUT"

    res_missing = step_millennial_erosion(
        state=MillennialPoolState(pom=10.0, maom=20.0),
        c_input=5.0,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
        erosion_input=ABSENT_INPUT,
    )
    assert isinstance(res_missing, ResultMissing)
    assert res_missing.reason == "MISSING_INPUT"


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {
            "soil_loss_Mg_ha": -0.1,
            "topsoil_soc_fraction": 0.02,
            "enrichment_ratio": 1.5,
        },
        {
            "soil_loss_Mg_ha": 4.0,
            "topsoil_soc_fraction": -0.01,
            "enrichment_ratio": 1.5,
        },
        {"soil_loss_Mg_ha": 4.0, "topsoil_soc_fraction": 1.01, "enrichment_ratio": 1.5},
        {
            "soil_loss_Mg_ha": 4.0,
            "topsoil_soc_fraction": 0.02,
            "enrichment_ratio": -1.0,
        },
    ],
)
def test_lateral_c_loss_out_of_domain_returns_not_computable(
    bad_kwargs: dict[str, float],
):
    res = compute_lateral_c_loss(**bad_kwargs)
    assert isinstance(res, ResultMissing)
    assert res.reason == "NOT_COMPUTABLE"


@pytest.mark.parametrize(
    "param_field",
    [
        "pom_input_fraction",
        "pom_decay_fraction",
        "pom_to_maom_fraction",
        "maom_decay_fraction",
        "maom_max_t_c_ha",
        "excess_maom_to_pom_fraction",
    ],
)
@pytest.mark.parametrize("shape", BOTH_MISSING_SHAPES)
def test_missing_parameter_returns_missing_input_naming_it(
    param_field: str, shape: InputMissing | ResultMissing
):
    params = MillennialErosionParams(
        **{**vars(PLACEHOLDER_PARAMS), param_field: shape}  # type: ignore[arg-type]
    )
    res = step_millennial_erosion(
        state=MillennialPoolState(pom=10.0, maom=20.0),
        c_input=5.0,
        params=params,
    )
    assert isinstance(res, ResultMissing)
    assert res.reason == "MISSING_INPUT"
    assert res.detail is not None and param_field in res.detail


def test_out_of_domain_step_inputs_return_not_computable():
    # state.maom > maom_max_t_c_ha
    res_over = step_millennial_erosion(
        state=MillennialPoolState(pom=5.0, maom=31.0),
        c_input=1.0,
        params=PLACEHOLDER_PARAMS,
    )
    assert isinstance(res_over, ResultMissing)
    assert res_over.reason == "NOT_COMPUTABLE"

    # c_eroded > available SOC
    res_eroded_over = step_millennial_erosion(
        state=MillennialPoolState(pom=0.5, maom=0.5),
        c_input=0.0,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
        erosion_input=LateralErosionInput(
            soil_loss_Mg_ha=100.0,
            topsoil_soc_fraction=0.5,
            enrichment_ratio=1.0,
        ),
    )
    assert isinstance(res_eroded_over, ResultMissing)
    assert res_eroded_over.reason == "NOT_COMPUTABLE"

    # negative c_input
    res_neg = step_millennial_erosion(
        state=MillennialPoolState(pom=5.0, maom=5.0),
        c_input=-1.0,
        params=PLACEHOLDER_PARAMS,
    )
    assert isinstance(res_neg, ResultMissing)
    assert res_neg.reason == "NOT_COMPUTABLE"


def test_multi_step_run_mass_conservation_and_ceiling():
    initial = MillennialPoolState(pom=8.0, maom=27.0)
    steps = [
        MillennialStepInput(
            c_input=4.0,
            erosion_input=LateralErosionInput(
                soil_loss_Mg_ha=2.0, topsoil_soc_fraction=0.02, enrichment_ratio=1.5
            ),
        ),
        MillennialStepInput(
            c_input=12.0,
            erosion_input=LateralErosionInput(
                soil_loss_Mg_ha=5.0, topsoil_soc_fraction=0.02, enrichment_ratio=1.2
            ),
        ),
        MillennialStepInput(
            c_input=0.0,
            erosion_input=LateralErosionInput(
                soil_loss_Mg_ha=0.0, topsoil_soc_fraction=0.02, enrichment_ratio=1.0
            ),
        ),
    ]
    run_res = run_millennial_erosion(
        initial_state=initial,
        steps=steps,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
    )
    assert isinstance(run_res, MillennialRunResult)
    assert run_res.coupled_erosion_applied is True
    assert run_res.coupled_erosion_status == "HYPOTHESIS"
    assert len(run_res.steps) == 3

    total_in = 0.0
    total_resp = 0.0
    total_eroded = 0.0
    for item in run_res.steps:
        assert isinstance(item, MillennialStepResult)
        assert item.end.maom <= PLACEHOLDER_PARAMS.maom_max_t_c_ha
        assert item.end.pom >= 0.0
        assert item.end.maom >= 0.0
        _assert_mass_conservation(item)
        total_in = math.fsum((total_in, item.c_input))
        total_resp = math.fsum((total_resp, item.c_respired))
        total_eroded = math.fsum((total_eroded, item.c_eroded))

    stocks = run_res.total_stocks()
    assert len(stocks) == 4
    assert isinstance(stocks[-1], float)
    cumulative_delta = stocks[-1] - initial.total
    cumulative_net = math.fsum((total_in, -total_resp, -total_eroded))
    assert math.isclose(cumulative_delta, cumulative_net, rel_tol=1e-12, abs_tol=1e-12)


def test_run_propagates_missing_step_forward():
    initial = MillennialPoolState(pom=8.0, maom=15.0)
    steps = [
        MillennialStepInput(c_input=3.0),
        MillennialStepInput(c_input=ABSENT_INPUT),
        MillennialStepInput(c_input=3.0),
    ]
    run_res = run_millennial_erosion(
        initial_state=initial,
        steps=steps,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=False,
    )
    assert isinstance(run_res.steps[0], MillennialStepResult)
    assert isinstance(run_res.steps[1], ResultMissing)
    assert run_res.steps[1].reason == "MISSING_INPUT"
    assert isinstance(run_res.steps[2], ResultMissing)
    assert run_res.steps[2].reason == "MISSING_INPUT"
    assert "step 2" in (run_res.steps[2].detail or "")


def test_g5_caller_type_errors():
    state = MillennialPoolState(pom=5.0, maom=5.0)
    with pytest.raises(TypeError):
        step_millennial_erosion(
            state=(5.0, 5.0),  # type: ignore[arg-type]
            c_input=1.0,
            params=PLACEHOLDER_PARAMS,
        )
    with pytest.raises(TypeError):
        step_millennial_erosion(
            state=state,
            c_input=True,  # type: ignore[arg-type]
            params=PLACEHOLDER_PARAMS,
        )
    with pytest.raises(TypeError):
        step_millennial_erosion(
            state=state,
            c_input=1.0,
            params=PLACEHOLDER_PARAMS,
            coupled_erosion=1,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        compute_lateral_c_loss(
            soil_loss_Mg_ha=None,  # type: ignore[arg-type]
            topsoil_soc_fraction=0.02,
            enrichment_ratio=1.0,
        )
    with pytest.raises(TypeError):
        run_millennial_erosion(
            initial_state=state,
            steps="not-a-sequence",  # type: ignore[arg-type]
            params=PLACEHOLDER_PARAMS,
        )


def test_g1_purity_non_mutation_and_determinism():
    state = MillennialPoolState(pom=10.0, maom=20.0)
    steps = [
        MillennialStepInput(
            c_input=4.0,
            erosion_input=LateralErosionInput(
                soil_loss_Mg_ha=3.0,
                topsoil_soc_fraction=0.02,
                enrichment_ratio=1.5,
            ),
        )
    ]
    snapshot_state = copy.deepcopy(state)
    snapshot_params = copy.deepcopy(PLACEHOLDER_PARAMS)
    snapshot_steps = copy.deepcopy(steps)

    r1 = run_millennial_erosion(
        initial_state=state,
        steps=steps,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
    )
    r2 = run_millennial_erosion(
        initial_state=state,
        steps=steps,
        params=PLACEHOLDER_PARAMS,
        coupled_erosion=True,
    )
    assert r1 == r2
    assert state == snapshot_state
    assert PLACEHOLDER_PARAMS == snapshot_params
    assert steps == snapshot_steps


def test_no_hardcoded_method_constants_no_defaults_and_stdlib_plus_contracts_only():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 1. No numeric literals outside {0, 1, 0.0, 1.0}
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}

    # 2. Only Python 3.12 stdlib + contracts.* imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in sys.stdlib_module_names or root == "contracts", root
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            root = node.module.split(".")[0]
            assert root in sys.stdlib_module_names or root == "contracts", root

    # 3. Zero defaults on MillennialErosionParams
    for param in inspect.signature(MillennialErosionParams).parameters.values():
        assert param.default is inspect.Parameter.empty, param
