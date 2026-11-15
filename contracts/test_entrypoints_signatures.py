"""Signature, export and G5 type-check audit for the engine entry points.

Audits the live callables listed in ``contracts/ENTRYPOINTS.md`` (EP1 through
EP6, plus ``daily_reference_evapotranspiration`` beside EP3 under D256):

- exact package module path, defining submodule, ``__all__`` membership, and
  alignment with ``api.engines`` (``DISCOVERED`` and ``REFERENCE_ET0``);
- agreement between ``contracts/ENTRYPOINTS.md`` and ``docs/METHODS.md`` on
  shared engine paths and dotted symbol names;
- live ``inspect.signature`` parameter order, parameter kinds (keyword-only
  ``parameters`` with no default), raw annotations, resolved
  ``typing.get_type_hints`` types, and return annotations;
- rule G5 ``TypeError`` when any parameter receives an object of the wrong
  type (including raw dicts per G3, and malformed ``parameters`` mappings).
"""

from __future__ import annotations

import datetime as dt
import importlib
import inspect
import re
import typing
from dataclasses import dataclass
from pathlib import Path

import pytest

from api.engines import DISCOVERED, REFERENCE_ET0
from contracts.carbon_balance import CarbonBalance
from contracts.carbon_forcing import CarbonForcing
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.residue_ledger import ResidueLedger
from contracts.results.models import Missing as ResultsMissing
from contracts.results.models import SoilLossResults, WaterDeficitExposure
from contracts.rotation_definition import RotationDefinition

ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINTS_DOC = ROOT / "contracts" / "ENTRYPOINTS.md"
METHODS_DOC = ROOT / "docs" / "METHODS.md"

_BACKTICKED_ENGINE_REF = re.compile(r"`(engine[./][^`()\s]+)")


@dataclass(frozen=True)
class ParamSpec:
    """Expected signature specification for one parameter."""

    name: str
    kind: inspect._ParameterKind
    annotation_text: str
    resolved_type: object


@dataclass(frozen=True)
class EntryPointSpec:
    """Expected contract specification for one engine public callable."""

    entry: str
    package_path: str
    impl_path: str
    function_name: str
    params: tuple[ParamSpec, ...]
    return_annotation_text: str
    return_type: object
    listed_in_discovered: bool = True


SPECS: tuple[EntryPointSpec, ...] = (
    EntryPointSpec(
        entry="EP1",
        package_path="engine.erosion",
        impl_path="engine.erosion.soil_loss",
        function_name="compute_soil_loss",
        params=(
            ParamSpec(
                "calendar",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "RotationCalendar",
                RotationCalendar,
            ),
            ParamSpec(
                "climate",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "SiteClimate",
                SiteClimate,
            ),
            ParamSpec(
                "soil_slope",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "SiteSoilSlope",
                SiteSoilSlope,
            ),
            ParamSpec(
                "parameters",
                inspect.Parameter.KEYWORD_ONLY,
                "dict[str, dict]",
                dict[str, dict],
            ),
        ),
        return_annotation_text="SoilLossResults | Missing",
        return_type=SoilLossResults | ResultsMissing,
    ),
    EntryPointSpec(
        entry="EP2",
        package_path="engine.calendar",
        impl_path="engine.calendar.build",
        function_name="build_rotation_calendar",
        params=(
            ParamSpec(
                "rotation",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "RotationDefinition",
                RotationDefinition,
            ),
        ),
        return_annotation_text="RotationCalendar",
        return_type=RotationCalendar,
    ),
    EntryPointSpec(
        entry="EP3",
        package_path="engine.water",
        impl_path="engine.water.exposure",
        function_name="compute_water_deficit_exposure",
        params=(
            ParamSpec(
                "calendar",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "RotationCalendar",
                RotationCalendar,
            ),
            ParamSpec(
                "climate",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "SiteClimate",
                SiteClimate,
            ),
            ParamSpec(
                "soil_slope",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "SiteSoilSlope",
                SiteSoilSlope,
            ),
            ParamSpec(
                "parameters",
                inspect.Parameter.KEYWORD_ONLY,
                "dict[str, dict]",
                dict[str, dict],
            ),
        ),
        return_annotation_text="list[WaterDeficitExposure]",
        return_type=list[WaterDeficitExposure],
    ),
    EntryPointSpec(
        entry="D256",
        package_path="engine.water",
        impl_path="engine.water.reference_et0",
        function_name="daily_reference_evapotranspiration",
        params=(
            ParamSpec(
                "climate",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "SiteClimate",
                SiteClimate,
            ),
            ParamSpec(
                "parameters",
                inspect.Parameter.KEYWORD_ONLY,
                "dict[str, dict]",
                dict[str, dict],
            ),
        ),
        return_annotation_text="dict[dt.date, float | Missing]",
        return_type=dict[dt.date, float | ResultsMissing],
        listed_in_discovered=False,
    ),
    EntryPointSpec(
        entry="EP4",
        package_path="engine.residues",
        impl_path="engine.residues.ledger",
        function_name="build_residue_ledger",
        params=(
            ParamSpec(
                "rotation",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "RotationDefinition",
                RotationDefinition,
            ),
            ParamSpec(
                "calendar",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "RotationCalendar",
                RotationCalendar,
            ),
            ParamSpec(
                "climate",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "SiteClimate",
                SiteClimate,
            ),
            ParamSpec(
                "parameters",
                inspect.Parameter.KEYWORD_ONLY,
                "dict[str, dict]",
                dict[str, dict],
            ),
        ),
        return_annotation_text="ResidueLedger",
        return_type=ResidueLedger,
    ),
    EntryPointSpec(
        entry="EP5",
        package_path="engine.amg",
        impl_path="engine.amg.entry",
        function_name="run_amg",
        params=(
            ParamSpec(
                "forcing",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "CarbonForcing",
                CarbonForcing,
            ),
            ParamSpec(
                "parameters",
                inspect.Parameter.KEYWORD_ONLY,
                "dict[str, dict]",
                dict[str, dict],
            ),
        ),
        return_annotation_text="CarbonBalance",
        return_type=CarbonBalance,
    ),
    EntryPointSpec(
        entry="EP6",
        package_path="engine.rothc",
        impl_path="engine.rothc.entry",
        function_name="run_rothc",
        params=(
            ParamSpec(
                "forcing",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                "CarbonForcing",
                CarbonForcing,
            ),
            ParamSpec(
                "parameters",
                inspect.Parameter.KEYWORD_ONLY,
                "dict[str, dict]",
                dict[str, dict],
            ),
        ),
        return_annotation_text="CarbonBalance",
        return_type=CarbonBalance,
    ),
)


def _spec_ids(spec: EntryPointSpec) -> str:
    return f"{spec.entry}:{spec.package_path}.{spec.function_name}"


def _load_valid_models() -> dict[str, object]:
    """Load validated contract model instances sharing one case_id and field_id."""
    calendar = RotationCalendar.model_validate_json(
        (
            ROOT
            / "contracts"
            / "inputs"
            / "examples"
            / "PLACEHOLDER_rotation_calendar.json"
        ).read_text(encoding="utf-8")
    )
    climate = SiteClimate.model_validate_json(
        (
            ROOT / "contracts" / "inputs" / "examples" / "PLACEHOLDER_site_climate.json"
        ).read_text(encoding="utf-8")
    )
    soil_slope = SiteSoilSlope.model_validate_json(
        (
            ROOT
            / "contracts"
            / "inputs"
            / "examples"
            / "PLACEHOLDER_site_soil_slope.json"
        ).read_text(encoding="utf-8")
    )
    forcing = CarbonForcing.model_validate_json(
        (
            ROOT
            / "contracts"
            / "carbon_forcing"
            / "examples"
            / "PLACEHOLDER_carbon_forcing.json"
        ).read_text(encoding="utf-8")
    )
    rotation = RotationDefinition.model_validate_json(
        (
            ROOT
            / "contracts"
            / "rotation_definition"
            / "examples"
            / "PLACEHOLDER_rotation_definition.json"
        ).read_text(encoding="utf-8")
    ).model_copy(update={"case_id": calendar.case_id, "field_id": calendar.field_id})
    return {
        "rotation": rotation,
        "calendar": calendar,
        "climate": climate,
        "soil_slope": soil_slope,
        "forcing": forcing,
        "parameters": {},
    }


def _valid_kwargs_for(spec: EntryPointSpec) -> dict[str, object]:
    """Return valid keyword arguments for all parameters of ``spec``."""
    pool = _load_valid_models()
    return {param.name: pool[param.name] for param in spec.params}


@pytest.mark.parametrize("spec", SPECS, ids=_spec_ids)
def test_package_exports_and_all(spec: EntryPointSpec) -> None:
    """Every entry point is exported in its package ``__all__`` and matches its impl."""
    package = importlib.import_module(spec.package_path)
    impl_module = importlib.import_module(spec.impl_path)

    pkg_all = getattr(package, "__all__", None)
    assert isinstance(pkg_all, list)
    assert spec.function_name in pkg_all

    fn = getattr(package, spec.function_name)
    impl_fn = getattr(impl_module, spec.function_name)
    assert callable(fn)
    assert fn is impl_fn

    if hasattr(impl_module, "__all__"):
        assert spec.function_name in impl_module.__all__


def test_api_runner_discovery_matches_specs() -> None:
    """``api.engines.DISCOVERED`` and ``REFERENCE_ET0`` match ``ENTRYPOINTS.md``."""
    discovered_map = {
        (ep.entry, ep.module, ep.function) for ep in DISCOVERED
    }
    expected_discovered = {
        (spec.entry, spec.package_path, spec.function_name)
        for spec in SPECS
        if spec.listed_in_discovered
    }
    assert discovered_map == expected_discovered

    et0_spec = next(spec for spec in SPECS if not spec.listed_in_discovered)
    assert (REFERENCE_ET0.entry, REFERENCE_ET0.module, REFERENCE_ET0.function) == (
        et0_spec.entry,
        et0_spec.package_path,
        et0_spec.function_name,
    )


def test_entrypoints_and_methods_docs_agree_on_paths_and_symbols() -> None:
    """``contracts/ENTRYPOINTS.md`` and ``docs/METHODS.md`` agree on paths and symbols."""
    entrypoints_text = ENTRYPOINTS_DOC.read_text(encoding="utf-8")
    methods_text = METHODS_DOC.read_text(encoding="utf-8")

    # Every entry point module path and function name appears in ENTRYPOINTS.md.
    for spec in SPECS:
        assert spec.package_path in entrypoints_text
        assert spec.function_name in entrypoints_text
        folder_path = spec.package_path.replace(".", "/") + "/"
        assert folder_path in entrypoints_text

    # Every engine.* dotted symbol in METHODS.md also appears in ENTRYPOINTS.md,
    # resolves to a live callable, and belongs to its module's __all__.
    methods_refs = set(_BACKTICKED_ENGINE_REF.findall(methods_text))
    dotted_in_methods = sorted(ref for ref in methods_refs if ref.startswith("engine."))
    assert dotted_in_methods, "expected dotted engine.* symbols in docs/METHODS.md"

    for dotted in dotted_in_methods:
        assert dotted in entrypoints_text, (
            f"{dotted!r} in docs/METHODS.md is missing from contracts/ENTRYPOINTS.md"
        )
        mod_path, attr = dotted.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        assert hasattr(mod, attr) and callable(getattr(mod, attr))
        mod_all = getattr(mod, "__all__", None)
        assert mod_all is not None and attr in mod_all

    # Shared engine folder/file paths referenced in METHODS.md exist and are
    # consistent with ENTRYPOINTS.md where both cite them.
    entrypoints_refs = set(_BACKTICKED_ENGINE_REF.findall(entrypoints_text))
    shared_paths = sorted(
        ref
        for ref in (methods_refs & entrypoints_refs)
        if ref.startswith("engine/")
    )
    assert "engine/erosion/" in shared_paths
    assert "engine/water/" in shared_paths
    assert "engine/rothc/" in shared_paths
    for rel in shared_paths:
        assert (ROOT / rel.rstrip("/")).exists(), f"missing path {rel}"


@pytest.mark.parametrize("spec", SPECS, ids=_spec_ids)
def test_live_signature_names_kinds_and_annotations(spec: EntryPointSpec) -> None:
    """``inspect.signature`` and ``get_type_hints`` match the contract."""
    package = importlib.import_module(spec.package_path)
    fn = getattr(package, spec.function_name)

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    assert tuple(p.name for p in params) == tuple(p.name for p in spec.params)

    hints = typing.get_type_hints(fn)
    for live_param, expected in zip(params, spec.params, strict=True):
        assert live_param.kind is expected.kind
        assert live_param.default is inspect.Parameter.empty
        assert live_param.annotation == expected.annotation_text
        assert hints[expected.name] == expected.resolved_type

    assert sig.return_annotation == spec.return_annotation_text
    assert hints["return"] == spec.return_type


@pytest.mark.parametrize(
    "spec",
    [spec for spec in SPECS if any(p.name == "parameters" for p in spec.params)],
    ids=lambda spec: _spec_ids(spec),
)
def test_parameters_is_keyword_only_at_call_site(spec: EntryPointSpec) -> None:
    """Passing ``parameters`` positionally fails with ``TypeError``."""
    package = importlib.import_module(spec.package_path)
    fn = getattr(package, spec.function_name)
    kwargs = _valid_kwargs_for(spec)
    positional_args = [kwargs[p.name] for p in spec.params]

    with pytest.raises(TypeError, match="positional"):
        fn(*positional_args)


def _wrong_type_cases() -> list[tuple[EntryPointSpec, str, object]]:
    """Build (spec, param_name, bad_value) cases for G5 TypeError checks."""
    valid = _load_valid_models()
    cases: list[tuple[EntryPointSpec, str, object]] = []
    for spec in SPECS:
        for param in spec.params:
            if param.name == "parameters":
                for bad_params in (None, "bad", [], {1: {}}, {"k": "not-a-dict"}):
                    cases.append((spec, param.name, bad_params))
            else:
                # Raw dict from model_dump() (G3 forbids dicts) and None.
                dumped = valid[param.name].model_dump()  # type: ignore[attr-defined]
                cases.append((spec, param.name, None))
                cases.append((spec, param.name, dumped))
    return cases


@pytest.mark.parametrize(
    ("spec", "bad_param", "bad_value"),
    _wrong_type_cases(),
    ids=lambda val: (
        _spec_ids(val)
        if isinstance(val, EntryPointSpec)
        else f"{type(val).__name__}" if not isinstance(val, str) else val
    ),
)
def test_g5_wrong_argument_type_raises_type_error(
    spec: EntryPointSpec, bad_param: str, bad_value: object
) -> None:
    """Rule G5: every entry point raises ``TypeError`` on wrong argument types."""
    package = importlib.import_module(spec.package_path)
    fn = getattr(package, spec.function_name)
    kwargs = _valid_kwargs_for(spec)
    kwargs[bad_param] = bad_value

    with pytest.raises(TypeError):
        fn(**kwargs)
