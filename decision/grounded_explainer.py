"""Grounded deterministic explainer and hypothesis-mode output verifier.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13): Frontier Unit F-22
(``l2/decision-grounded-explainer``, frontier plan §5.8 and integrated plan
rev13 §5).

This module implements:

1. ``GroundedFactLedger``: an explicit, immutable typed ledger of computed
   and declared facts (``metric_id``, ``value``, ``unit``, ``provenance``,
   ``source``, or typed ``Missing`` reason per ``contracts/CONVENTIONS.md``
   C3.1, C3.2, C4.1, C4.2), together with ``allowed_rotations`` and
   ``decision_state``.
2. ``render_deterministic_explanation(ledger)``: a deterministic template
   builder that formats computed/declared values with provenance, source or
   assumption, and example-data badges, and renders explicit ``Missing``
   notices without ever defaulting missing values to zero or calling a
   language model.
3. ``verify_explanation_grounding(candidate_text, ledger)``: a strict
   hypothesis-mode output verifier that parses every numeric literal,
   percentage, unit, and prohibited pattern (agronomic advice, prescriptive
   guarantees, or false NASA/official endorsement) in ``candidate_text``,
   verifies every numeric claim appears in ``ledger`` within declared
   formatting precision with matching metric, unit, and provenance, and
   rejects any ungrounded number, invented advice, fabricated missing value,
   or false official approval with
   ``GroundingVerificationResult(verified=False, reason="CONTROL_FAILED",
   violations=(...))``. Rejected candidate text is never surfaced.

Pure function (G1): no network calls, no language-model SDK imports, no file
access, no clock, no environment variables, and no global mutable state.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from contracts.decision_output import DecisionOutput
from contracts.decision_output.models import STATE_NAMES
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.common import Provenance, ReasonCode
from contracts.inputs.common import Range as InputRange
from contracts.results.models import Missing as ResultsMissing
from contracts.results.models import Range as ResultsRange
from contracts.results.models import ResultsTable

__all__ = [
    "GroundedFact",
    "GroundedFactLedger",
    "GroundingVerificationResult",
    "GroundingViolation",
    "ledger_from_decision_output",
    "render_deterministic_explanation",
    "verify_explanation_grounding",
]

MissingValue = InputMissing | ResultsMissing
RangeValue = InputRange | ResultsRange

_VALID_PROVENANCES: frozenset[str] = frozenset(
    {"DECLARED", "OBSERVED", "DERIVED", "SIMULATED"}
)
_KNOWN_STATE_NAMES: tuple[str, ...] = (*STATE_NAMES, "Not evaluated")

# Known compound and simple units from contracts/CONVENTIONS.md and common
# agronomic/economic quantities, matched longest-first.
_KNOWN_UNITS: tuple[str, ...] = (
    "t C ha-1 yr-1",
    "t ha-1 month-1",
    "USD ha-1 yr-1",
    "EUR ha-1 yr-1",
    "kg C ha-1 yr-1",
    "kg ha-1 yr-1",
    "t ha-1 yr-1",
    "t C ha-1",
    "kg C ha-1",
    "dimensionless",
    "mm month-1",
    "mm day-1",
    "mm yr-1",
    "USD yr-1",
    "kg ha-1",
    "g m-2",
    "ag_years",
    "ag_year",
    "percent",
    "months",
    "years",
    "month",
    "deg C",
    "days",
    "year",
    "day",
    "USD",
    "EUR",
    "mm",
    "cm",
    "kg",
    "ha",
    "yr",
    "°C",
    "%",
    "t",
    "m",
)

# Standalone unit tokens (outside _KNOWN_UNITS) that still identify a physical,
# area, mass, currency, or rate unit when attached to a number in prose.
_EXTRA_UNIT_WORDS: frozenset[str] = frozenset(
    {
        "ac",
        "acre",
        "acres",
        "ars",
        "bu",
        "bushel",
        "bushels",
        "ft",
        "g",
        "gal",
        "gallons",
        "hr",
        "hrs",
        "in",
        "km",
        "l",
        "lb",
        "lbs",
        "liter",
        "liters",
        "litre",
        "litres",
        "mg",
        "ml",
        "pct",
        "ton",
        "tonne",
        "tonnes",
        "tons",
        "uyu",
    }
)

# Unit exponents like ha-1, yr-1, month-1, day-1, m-2, ha^-1.
_UNIT_EXPONENT_RE = re.compile(r"(?<=[A-Za-z])\^?-\d+\b")

# Numeric literal pattern: optional sign (only when not preceded by a digit,
# avoiding splitting ranges like 1.9-2.8 into 1.9 and -2.8), digits with
# optional comma grouping and decimal part, optional scientific exponent,
# optional trailing percentage sign.
_NUMERIC_RE = re.compile(
    r"(?<![A-Za-z0-9_.])"
    r"(?P<sign>(?<!\d)[+-])?"
    r"(?P<mantissa>\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)"
    r"(?P<exp>[eE][+-]?\d+)?"
    r"(?P<pct>\s*%)?"
    r"(?![0-9_.])"
)

_SLASH_UNIT_RE = re.compile(
    r"^\s*([A-Za-z°%]+(?:\^?-?\d+)?(?:/[A-Za-z]+(?:\^?-?\d+)?)+)"
)
_WORD_UNIT_RE = re.compile(r"^\s*([A-Za-z]+(?:\^?-?\d+)?)\b")
_PRECEDING_CURRENCY_RE = re.compile(r"(\$|USD|EUR)\s*$")
_SOURCE_BADGE_RE = re.compile(r"\[SOURCE:\s*(?P<body>[^\]\r\n]+?)\]")

_EXPLICIT_PROVENANCE_RE = re.compile(
    r"(?:\[PROVENANCE:\s*(DECLARED|OBSERVED|DERIVED|SIMULATED)\]|"
    r"\bprovenance\s*:\s*(DECLARED|OBSERVED|DERIVED|SIMULATED)\b|"
    r"(?<![A-Za-z_])(DECLARED|OBSERVED|DERIVED|SIMULATED)(?![A-Za-z_]))"
)
_INLINE_PROVENANCE_RE = re.compile(
    r"\b(declared|observed|derived|simulated)\b(?=\s+(?:value|metric|loss|trend|exposure|soil_loss|water_deficit_exposure|soil_carbon_trend|\d))|"
    r"\((declared|observed|derived|simulated)\)",
    re.IGNORECASE,
)

# Prohibited patterns (27 §5.8): agronomic advice, prescriptive guarantees, and
# false official/NASA endorsements. Note: "NASA POWER" as a data source name is
# explicitly permitted and does not match these endorsement patterns.
_PROHIBITED_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "PROHIBITED_ADVICE",
        re.compile(
            r"\b(?:"
            r"agronomic\s+advice|"
            r"prescriptive\s+(?:advice|recommendation|guidance)|"
            r"(?:we|i|system|model|assistant)\s+(?:strongly\s+)?(?:recommend|advise|prescribe|urge)s?|"
            r"(?:recommend|advise)\s+(?:planting|sowing|growing|applying|switching|adopting)|"
            r"(?:is|are)\s+(?:strongly\s+)?recommended|"
            r"recommended\s+(?:rotation|crop|practice)|"
            r"(?:you|the\s+(?:farmer|producer|grower)|farmers|producers|growers)\s+"
            r"(?:should|must|ought\s+to|need\s+to)\s+"
            r"(?:plant|sow|grow|apply|switch|adopt|harvest|fertilize|irrigate|till)"
            r")\b",
            re.IGNORECASE,
        ),
        "prohibited agronomic advice or prescriptive recommendation detected",
    ),
    (
        "PROHIBITED_GUARANTEE",
        re.compile(
            r"\b(?:"
            r"prescriptive\s+guarantee|"
            r"guarantee(?:d|s)?\s+(?:to|that|of|yield|profit|margin|income|outcome|result|success|compliance|protection|zero\s+loss|no\s+erosion)|"
            r"(?:100\s*%|absolute|complete|full)\s+guarantee|"
            r"will\s+definitely\s+(?:increase|reduce|prevent|yield|succeed|outperform)|"
            r"zero\s+risk|"
            r"risk[- ]free|"
            r"no\s+uncertainty|"
            r"proven\s+to\s+work"
            r")\b",
            re.IGNORECASE,
        ),
        "prohibited prescriptive guarantee or false certainty claim detected",
    ),
    (
        "PROHIBITED_ENDORSEMENT",
        re.compile(
            r"\b(?:"
            r"NASA[\s-]+(?:endorsed|validated|approved|certified|official|backed|sanctioned)|"
            r"(?:endorsed|validated|approved|certified|sanctioned)\s+by\s+NASA|"
            r"official\s+NASA\s+(?:recommendation|endorsement|validation|approval|advice)|"
            r"NASA\s+(?:confirms|guarantees|recommends|certifies|endorses|validates)|"
            r"officially\s+(?:endorsed|validated|approved|certified)|"
            r"government\s+(?:endorsed|approved|certified)"
            r")\b",
            re.IGNORECASE,
        ),
        "prohibited false NASA or official endorsement/validation claim detected",
    ),
)

_ROTATION_MENTION_RE = re.compile(
    r"(?:"
    r"\brotation_id\s*[:=]\s*['\"]?(?P<id_kv>[A-Za-z0-9_.-]+)['\"]?|"
    r"\brotation\s+['\"](?P<id_q>[A-Za-z0-9_.-]+)['\"]|"
    r"\bpreferred\s+rotation\s*:\s*['\"]?(?P<id_pref>[A-Za-z0-9_.-]+)['\"]?"
    r")",
    re.IGNORECASE,
)

_NON_ROTATION_TOKENS: frozenset[str] = frozenset(
    {"none", "null", "n/a", "unresolved", "unknown", "missing"}
)


def _require_non_blank_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__} (G5)")
    if value.strip() == "":
        raise ValueError(f"{name}: must not be empty or blank")
    return value


def _require_strict_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}: expected int, got {type(value).__name__} (G5)")
    return value


def _require_finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name}: expected float, got {type(value).__name__} (G5)")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name}: must be finite, got {value!r} (C3.1)")
    return 0.0 if numeric == 0.0 else numeric


def _to_tuple(items: object, name: str) -> tuple:
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
        raise TypeError(f"{name}: expected a sequence, got {type(items).__name__} (G5)")
    return tuple(items)


@dataclass(frozen=True)
class GroundedFact:
    """One computed, declared, or explicitly missing fact in a decision ledger.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). Enforces C3.1, C3.2,
    C4.1, and C4.2 of ``contracts/CONVENTIONS.md``: every fact holds either a
    finite numeric ``value`` with its ``provenance`` and ``source`` (or
    ``assumption=True``), or ``value=None`` with a typed ``Missing`` reason and
    no provenance or source.
    """

    metric_id: str
    value: float | None
    unit: str
    provenance: Provenance | None = None
    source: str | None = None
    missing: MissingValue | None = None
    assumption: bool = False
    precision: int | None = None
    range: RangeValue | None = None
    range_missing: MissingValue | None = None
    rotation_id: str | None = None
    scenario_id: str | None = None
    ag_year: int | None = None

    def __post_init__(self) -> None:
        _require_non_blank_str(self.metric_id, "metric_id")
        _require_non_blank_str(self.unit, "unit")
        if not isinstance(self.assumption, bool):
            raise TypeError(
                f"assumption: expected bool, got {type(self.assumption).__name__} (G5)"
            )
        if self.precision is not None:
            prec = _require_strict_int(self.precision, "precision")
            if prec < 0 or prec > 12:
                raise ValueError(
                    f"precision: expected integer in 0..12, got {self.precision}"
                )
        if self.rotation_id is not None:
            _require_non_blank_str(self.rotation_id, "rotation_id")
        if self.scenario_id is not None:
            _require_non_blank_str(self.scenario_id, "scenario_id")
        if self.ag_year is not None:
            _require_strict_int(self.ag_year, "ag_year")

        if self.value is not None:
            numeric = _require_finite_float(self.value, "value")
            object.__setattr__(self, "value", numeric)
            if self.missing is not None:
                raise ValueError(
                    "a fact holds a numeric value or a Missing reason, never both (C3.1)"
                )
            if self.provenance not in _VALID_PROVENANCES:
                raise ValueError(
                    "a present fact requires provenance in "
                    f"{sorted(_VALID_PROVENANCES)}, got {self.provenance!r} (C4.1)"
                )
            if self.source is not None:
                _require_non_blank_str(self.source, "source")
            elif not self.assumption:
                raise ValueError(
                    "a present fact requires a source or assumption=True (C4.2)"
                )
            if self.range is not None:
                if not isinstance(self.range, (InputRange, ResultsRange)):
                    raise TypeError(
                        f"range: expected Range, got {type(self.range).__name__} (G5)"
                    )
                if self.range_missing is not None:
                    raise ValueError(
                        "a fact holds a range or range_missing, never both (C2.2)"
                    )
                if not (self.range.low <= numeric <= self.range.high):
                    raise ValueError(
                        "range: fact value lies outside [low, high] (C2.1)"
                    )
            if self.range_missing is not None and not isinstance(
                self.range_missing, (InputMissing, ResultsMissing)
            ):
                raise TypeError(
                    "range_missing: expected Missing, got "
                    f"{type(self.range_missing).__name__} (G5)"
                )
        else:
            if not isinstance(self.missing, (InputMissing, ResultsMissing)):
                raise TypeError(
                    "missing: a fact with value=None requires a typed Missing "
                    f"instance, got {type(self.missing).__name__} (C3.1, G5)"
                )
            if self.provenance is not None:
                raise ValueError("a missing fact carries no provenance label (C4.1)")
            if self.source is not None or self.assumption:
                raise ValueError(
                    "a missing fact carries no source and no assumption mark (C4.1)"
                )
            if self.range is not None or self.range_missing is not None:
                raise ValueError(
                    "a missing fact carries no range and no range_missing (C2.2)"
                )


@dataclass(frozen=True)
class GroundedFactLedger:
    """Explicit typed ledger backing deterministic and hypothesis-mode text.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). Holds an immutable
    tuple of ``GroundedFact`` records together with ``allowed_rotations``,
    ``decision_state``, and ``example_data``.
    """

    facts: tuple[GroundedFact, ...]
    allowed_rotations: tuple[str, ...]
    decision_state: str
    example_data: bool = False
    case_id: str | None = None
    field_id: str | None = None
    preferred_rotation_id: str | None = None
    indicators_not_resolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        facts_tuple = _to_tuple(self.facts, "facts")
        for idx, fact in enumerate(facts_tuple):
            if not isinstance(fact, GroundedFact):
                raise TypeError(
                    f"facts[{idx}]: expected GroundedFact, got "
                    f"{type(fact).__name__} (G5)"
                )
        object.__setattr__(self, "facts", facts_tuple)

        rotations_tuple = _to_tuple(self.allowed_rotations, "allowed_rotations")
        seen_rotations: set[str] = set()
        for idx, rot in enumerate(rotations_tuple):
            _require_non_blank_str(rot, f"allowed_rotations[{idx}]")
            if rot in seen_rotations:
                raise ValueError(f"allowed_rotations: duplicate rotation '{rot}'")
            seen_rotations.add(rot)
        object.__setattr__(self, "allowed_rotations", rotations_tuple)

        _require_non_blank_str(self.decision_state, "decision_state")
        if not isinstance(self.example_data, bool):
            raise TypeError(
                f"example_data: expected bool, got {type(self.example_data).__name__} (G5)"
            )
        if self.case_id is not None:
            _require_non_blank_str(self.case_id, "case_id")
        if self.field_id is not None:
            _require_non_blank_str(self.field_id, "field_id")
        if self.preferred_rotation_id is not None:
            _require_non_blank_str(self.preferred_rotation_id, "preferred_rotation_id")
            if self.preferred_rotation_id not in seen_rotations:
                raise ValueError(
                    f"preferred_rotation_id '{self.preferred_rotation_id}' is not in "
                    "allowed_rotations"
                )
        unresolved = _to_tuple(self.indicators_not_resolved, "indicators_not_resolved")
        for idx, name in enumerate(unresolved):
            _require_non_blank_str(name, f"indicators_not_resolved[{idx}]")
        object.__setattr__(self, "indicators_not_resolved", unresolved)

        for fact in facts_tuple:
            if fact.rotation_id is not None and fact.rotation_id not in seen_rotations:
                raise ValueError(
                    f"fact '{fact.metric_id}' names rotation '{fact.rotation_id}', "
                    "which is not in allowed_rotations"
                )


@dataclass(frozen=True)
class GroundingViolation:
    """One grounding, unit, provenance, or prohibited-pattern failure."""

    code: str
    detail: str

    def __post_init__(self) -> None:
        _require_non_blank_str(self.code, "code")
        _require_non_blank_str(self.detail, "detail")

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True)
class GroundingVerificationResult:
    """Outcome of ``verify_explanation_grounding``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). When ``verified`` is
    ``False``, ``reason`` is always ``"CONTROL_FAILED"`` (C3.2),
    ``violations`` is non-empty, and ``surfaced_text`` is strictly ``None`` so
    withheld candidate text is never surfaced.
    """

    verified: bool
    reason: ReasonCode | None
    violations: tuple[GroundingViolation, ...] = ()
    surfaced_text: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.verified, bool):
            raise TypeError(
                f"verified: expected bool, got {type(self.verified).__name__} (G5)"
            )
        violations_tuple = _to_tuple(self.violations, "violations")
        for idx, item in enumerate(violations_tuple):
            if not isinstance(item, GroundingViolation):
                raise TypeError(
                    f"violations[{idx}]: expected GroundingViolation, got "
                    f"{type(item).__name__} (G5)"
                )
        object.__setattr__(self, "violations", violations_tuple)
        if self.verified:
            if self.reason is not None:
                raise ValueError("verified=True must carry reason=None")
            if violations_tuple:
                raise ValueError("verified=True must carry empty violations")
        else:
            if self.reason != "CONTROL_FAILED":
                raise ValueError(
                    f"verified=False must carry reason='CONTROL_FAILED', got {self.reason!r}"
                )
            if not violations_tuple:
                raise ValueError("verified=False requires at least one violation")
            if self.surfaced_text is not None:
                raise ValueError(
                    "withheld candidate text must never be surfaced when verified=False"
                )


def _format_number(value: float, precision: int | None) -> str:
    clean = 0.0 if value == 0.0 else float(value)
    if precision is not None:
        return f"{clean:.{precision}f}"
    return str(clean)


def ledger_from_decision_output(
    document: DecisionOutput,
    *,
    table: ResultsTable | None = None,
) -> GroundedFactLedger:
    """Build a ``GroundedFactLedger`` from a ``DecisionOutput`` contract.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). Pure conversion; never
    invents thresholds, limits, or missing values.
    """
    if not isinstance(document, DecisionOutput):
        raise TypeError(
            f"document: expected DecisionOutput, got {type(document).__name__} (G5)"
        )
    if table is not None and not isinstance(table, ResultsTable):
        raise TypeError(
            f"table: expected ResultsTable, got {type(table).__name__} (G5)"
        )

    facts: list[GroundedFact] = []
    if table is not None:
        for row in table.rows:
            facts.append(
                GroundedFact(
                    metric_id=row.indicator,
                    value=row.value,
                    unit=row.unit,
                    provenance=row.provenance,
                    source=row.source,
                    assumption=row.assumption,
                    missing=row.missing,
                    range=row.range,
                    range_missing=row.range_missing,
                    rotation_id=row.rotation_id,
                    scenario_id=row.scenario_id,
                    ag_year=row.ag_year,
                )
            )
    for item in document.limits:
        facts.append(
            GroundedFact(
                metric_id=f"limit.{item.indicator}",
                value=item.limit.value,
                unit=item.limit.unit,
                provenance=item.limit.provenance,
                source=item.limit.source,
                assumption=item.limit.assumption,
                missing=item.limit.missing,
                range=item.limit.range,
                range_missing=item.limit.range_missing,
            )
        )
    for diff in document.paired_differences:
        facts.append(
            GroundedFact(
                metric_id=f"paired_difference.{diff.indicator}",
                value=diff.difference.value,
                unit=diff.difference.unit,
                provenance=diff.difference.provenance,
                source=diff.difference.source,
                assumption=diff.difference.assumption,
                missing=diff.difference.missing,
                range=diff.difference.range,
                range_missing=diff.difference.range_missing,
                scenario_id=diff.scenario_id,
                ag_year=diff.ag_year,
            )
        )

    preferred_rotation_id: str | None = None
    if document.state.value is not None:
        decision_state = document.state.value
    elif len(document.pair_states) == 1:
        only_pair = document.pair_states[0]
        decision_state = only_pair.value or "Not evaluated"
        preferred_rotation_id = only_pair.preferred_rotation_id
    elif document.state.missing is not None:
        decision_state = f"Not resolved ({document.state.missing.reason})"
    else:
        decision_state = "Not evaluated"

    return GroundedFactLedger(
        facts=tuple(facts),
        allowed_rotations=tuple(document.rotations),
        decision_state=decision_state,
        example_data=document.example_data,
        case_id=document.case_id,
        field_id=document.field_id,
        preferred_rotation_id=preferred_rotation_id,
        indicators_not_resolved=tuple(document.state.indicators_not_resolved),
    )


def render_deterministic_explanation(ledger: GroundedFactLedger) -> str:
    """Render a deterministic template explanation from ``ledger``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). Never calls an LLM,
    never invents numbers, formats every present value with its unit,
    provenance, source/assumption, and example-data badge, and renders
    explicit ``Missing`` notices for absent values.
    """
    if not isinstance(ledger, GroundedFactLedger):
        raise TypeError(
            f"ledger: expected GroundedFactLedger, got {type(ledger).__name__} (G5)"
        )

    lines: list[str] = []
    if ledger.example_data:
        lines.append("[EXAMPLE DATA — synthetic demonstration data, not a real field]")
    else:
        lines.append("[CASE DATA — non-example declaration]")

    lines.append(f"Decision state: {ledger.decision_state}")
    rotations_text = (
        ", ".join(ledger.allowed_rotations) if ledger.allowed_rotations else "none"
    )
    lines.append(f"Allowed rotations: {rotations_text}")
    if ledger.preferred_rotation_id is not None:
        lines.append(f"Preferred rotation: {ledger.preferred_rotation_id}")
    if ledger.indicators_not_resolved:
        lines.append(
            f"Indicators not resolved: {', '.join(ledger.indicators_not_resolved)}"
        )

    if not ledger.facts:
        lines.append("Facts: none recorded in ledger.")
    else:
        lines.append("Facts:")
        for fact in ledger.facts:
            scope_parts: list[str] = []
            if fact.rotation_id is not None:
                scope_parts.append(fact.rotation_id)
            if fact.scenario_id is not None:
                scope_parts.append(fact.scenario_id)
            if fact.ag_year is not None:
                scope_parts.append(f"ag_year={fact.ag_year}")
            scope_prefix = f"[{' | '.join(scope_parts)}] " if scope_parts else ""

            if fact.value is None:
                assert fact.missing is not None
                detail = (
                    f" ({fact.missing.detail})"
                    if fact.missing.detail is not None
                    else ""
                )
                lines.append(
                    f"- {scope_prefix}{fact.metric_id} ({fact.unit}): "
                    f"[MISSING: {fact.missing.reason}]{detail}"
                )
                continue

            formatted = _format_number(fact.value, fact.precision)
            unit_suffix = "%" if fact.unit == "%" else f" {fact.unit}"
            range_part = ""
            if fact.range is not None:
                low_str = _format_number(fact.range.low, fact.precision)
                high_str = _format_number(fact.range.high, fact.precision)
                range_unit = "%" if fact.unit == "%" else ""
                trailing_unit = "" if fact.unit == "%" else f" {fact.unit}"
                range_part = (
                    f" (range [{low_str}{range_unit}, {high_str}{range_unit}]"
                    f"{trailing_unit}, kind: {fact.range.kind})"
                )
            elif fact.range_missing is not None:
                range_part = f" (range missing: {fact.range_missing.reason})"

            badges: list[str] = [f"[PROVENANCE: {fact.provenance}]"]
            if fact.source is not None:
                badges.append(f"[SOURCE: {fact.source}]")
            if fact.assumption:
                badges.append("[ASSUMPTION]")

            lines.append(
                f"- {scope_prefix}{fact.metric_id}: {formatted}{unit_suffix}"
                f"{range_part} {' '.join(badges)}"
            )

    lines.append(
        "Deterministic ledger summary: computed and declared values only; "
        "missing entries are withheld with their typed reasons."
    )
    return "\n".join(lines)


def _count_decimals(mantissa_text: str) -> int:
    if "." not in mantissa_text:
        return 0
    return len(mantissa_text.split(".", 1)[1])


def _value_matches_precision(
    candidate: float,
    reference: float,
    candidate_decimals: int,
    precision: int | None,
) -> bool:
    exact_tol = 1e-9 * max(1.0, abs(reference))
    if abs(candidate - reference) <= exact_tol:
        return True
    if precision is None:
        return False
    if candidate_decimals > precision:
        return False
    rounding_tol = 0.5 * (10.0 ** (-precision)) + 1e-12
    return abs(candidate - reference) <= rounding_tol


def _fact_matches_number(
    fact: GroundedFact,
    candidate: float,
    candidate_decimals: int,
) -> bool:
    if fact.value is None:
        return False
    if _value_matches_precision(
        candidate, fact.value, candidate_decimals, fact.precision
    ):
        return True
    if fact.range is not None:
        if _value_matches_precision(
            candidate, fact.range.low, candidate_decimals, fact.precision
        ):
            return True
        if _value_matches_precision(
            candidate, fact.range.high, candidate_decimals, fact.precision
        ):
            return True
    return False


def _collect_known_units(ledger: GroundedFactLedger) -> tuple[str, ...]:
    units = set(_KNOWN_UNITS)
    for fact in ledger.facts:
        units.add(fact.unit)
    return tuple(sorted(units, key=len, reverse=True))


def _extract_unit_at(
    text: str,
    start: int,
    end: int,
    is_pct: bool,
    known_units: tuple[str, ...],
) -> str | None:
    if is_pct:
        return "%"
    after = text[end:]
    stripped = after.lstrip(" \t")
    for unit in known_units:
        if unit == "%":
            continue
        if stripped.startswith(unit):
            tail_idx = len(unit)
            if tail_idx == len(stripped) or not stripped[tail_idx].isalnum():
                return unit
    slash_match = _SLASH_UNIT_RE.match(after)
    if slash_match is not None:
        return slash_match.group(1)
    word_match = _WORD_UNIT_RE.match(after)
    if word_match is not None:
        candidate = word_match.group(1)
        if candidate.casefold() in _EXTRA_UNIT_WORDS:
            return candidate
    before = text[:start]
    curr_match = _PRECEDING_CURRENCY_RE.search(before)
    if curr_match is not None:
        symbol = curr_match.group(1)
        return "USD" if symbol == "$" else symbol
    # Handle range low or high bound written as '[10.0, 20.0]%'
    if re.match(r"^\s*(?:,\s*[+-]?\d[\d,.]*\s*)?\]\s*%", after):
        return "%"
    # Handle parenthesized unit before number, e.g. 'soil_loss (kg ha-1): 2.365'
    paren_match = re.search(r"\(([^()]{1,40})\)\s*[:=]?\s*$", before)
    if paren_match is not None:
        candidate_unit = paren_match.group(1).strip()
        if (
            candidate_unit in known_units
            or _SLASH_UNIT_RE.fullmatch(candidate_unit) is not None
            or candidate_unit.casefold() in _EXTRA_UNIT_WORDS
        ):
            return candidate_unit
    return None


def _build_metric_pattern(ledger: GroundedFactLedger) -> re.Pattern[str] | None:
    aliases: dict[str, str] = {}
    base_ids = {
        "soil_loss",
        "water_deficit_exposure",
        "soil_carbon_trend",
    }
    for fact in ledger.facts:
        base_ids.add(fact.metric_id)
    for metric_id in base_ids:
        aliases[metric_id] = metric_id
        spaced = metric_id.replace("_", " ").replace(".", " ")
        if spaced != metric_id:
            aliases.setdefault(spaced, metric_id)
        hyphened = metric_id.replace("_", "-")
        if hyphened != metric_id:
            aliases.setdefault(hyphened, metric_id)
    if not aliases:
        return None
    alternatives = "|".join(
        re.escape(alias) for alias in sorted(aliases, key=len, reverse=True)
    )
    return re.compile(
        rf"(?<![A-Za-z0-9_])(?:{alternatives})(?![A-Za-z0-9_])", re.IGNORECASE
    )


def _normalize_metric_alias(matched: str, ledger: GroundedFactLedger) -> str:
    candidate_cf = matched.casefold()
    known_ids = {
        "soil_loss",
        "water_deficit_exposure",
        "soil_carbon_trend",
        *(fact.metric_id for fact in ledger.facts),
    }
    for metric_id in sorted(known_ids, key=len, reverse=True):
        if candidate_cf in {
            metric_id.casefold(),
            metric_id.replace("_", " ").replace(".", " ").casefold(),
            metric_id.replace("_", "-").casefold(),
        }:
            return metric_id
    return matched


_MISSING_DETAIL_RE = re.compile(r"\[MISSING:\s*[A-Z_]+\]\s*\((?P<detail>[^()\r\n]+)\)")


def _verified_source_spans(
    line: str,
    ledger_sources: frozenset[str],
    ledger_missing_details: frozenset[str],
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _SOURCE_BADGE_RE.finditer(line):
        body = match.group("body").strip()
        if body in ledger_sources:
            spans.append(match.span())
    for match in _MISSING_DETAIL_RE.finditer(line):
        detail = match.group("detail").strip()
        if detail in ledger_missing_details:
            spans.append(match.span("detail"))
    for source in ledger_sources:
        if len(source) >= 4 and any(ch.isalpha() for ch in source):
            start = 0
            while True:
                idx = line.find(source, start)
                if idx == -1:
                    break
                spans.append((idx, idx + len(source)))
                start = idx + len(source)
    return spans


def _in_spans(pos: int, spans: Sequence[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def _split_clauses(line: str) -> list[tuple[int, str]]:
    """Split a line into (offset, clause_text) on semicolons or sentence ends."""
    clauses: list[tuple[int, str]] = []
    start = 0
    # Split on ';' or sentence-ending '.' (not decimal '.' or 'et al.').
    for match in re.finditer(r";|(?<!\d)\.(?!\d)(?=\s|$)", line):
        prefix = line[max(0, match.start() - 5) : match.start() + 1]
        if prefix.casefold().endswith("et al."):
            continue
        end = match.start()
        clauses.append((start, line[start:end]))
        start = match.end()
    if start <= len(line):
        clauses.append((start, line[start:]))
    return clauses


def _extract_provenance(segment: str) -> str | None:
    match = _EXPLICIT_PROVENANCE_RE.search(segment)
    if match is not None:
        return next(g for g in match.groups() if g is not None)
    inline = _INLINE_PROVENANCE_RE.search(segment)
    if inline is not None:
        found = next(g for g in inline.groups() if g is not None)
        return found.upper()
    return None


def _extract_rotation_scope(
    segment: str,
    allowed_rotations: tuple[str, ...],
    known_units: tuple[str, ...],
) -> str | None:
    cleaned = segment
    for unit in known_units:
        if any(ch.isalpha() for ch in unit):
            cleaned = re.sub(
                rf"(?<![A-Za-z0-9_]){re.escape(unit)}(?![A-Za-z0-9_])",
                " ",
                cleaned,
            )
    found: list[str] = []
    for rot in sorted(allowed_rotations, key=len, reverse=True):
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(rot)}(?![A-Za-z0-9_])")
        if pattern.search(cleaned):
            found.append(rot)
    if len(found) == 1:
        return found[0]
    return None


def _check_prohibited_patterns(text: str) -> list[GroundingViolation]:
    violations: list[GroundingViolation] = []
    for code, pattern, detail in _PROHIBITED_PATTERNS:
        if pattern.search(text):
            violations.append(GroundingViolation(code=code, detail=detail))
    return violations


def _check_decision_state_and_rotations(
    text: str, ledger: GroundedFactLedger
) -> list[GroundingViolation]:
    violations: list[GroundingViolation] = []
    allowed = set(ledger.allowed_rotations)
    ledger_state_cf = ledger.decision_state.casefold()

    for state_name in _KNOWN_STATE_NAMES:
        if state_name == "Not evaluated":
            state_re = re.compile(
                r"\bDecision\s+state\s*:\s*Not\s+evaluated\b", re.IGNORECASE
            )
        else:
            state_re = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(state_name)}(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
        if state_re.search(text) and state_name.casefold() != ledger_state_cf:
            violations.append(
                GroundingViolation(
                    code="DECISION_STATE_MISMATCH",
                    detail=(
                        f"claimed decision state '{state_name}' does not match "
                        f"ledger decision_state '{ledger.decision_state}'"
                    ),
                )
            )

    explicit_state = re.search(
        r"^\s*Decision\s+state\s*:\s*(?P<state>[^\r\n]+)$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if explicit_state is not None:
        claimed = explicit_state.group("state").strip()
        if claimed.casefold() != ledger_state_cf:
            violations.append(
                GroundingViolation(
                    code="DECISION_STATE_MISMATCH",
                    detail=(
                        f"claimed decision state '{claimed}' does not match "
                        f"ledger decision_state '{ledger.decision_state}'"
                    ),
                )
            )

    for match in _ROTATION_MENTION_RE.finditer(text):
        rot_id = match.group("id_kv") or match.group("id_q") or match.group("id_pref")
        if rot_id is None:
            continue
        if rot_id.casefold() in _NON_ROTATION_TOKENS:
            continue
        if rot_id not in allowed:
            violations.append(
                GroundingViolation(
                    code="UNALLOWED_ROTATION",
                    detail=f"rotation '{rot_id}' is not in allowed_rotations",
                )
            )
        elif (
            match.group("id_pref") is not None
            and ledger.preferred_rotation_id is not None
            and rot_id != ledger.preferred_rotation_id
        ):
            violations.append(
                GroundingViolation(
                    code="DECISION_STATE_MISMATCH",
                    detail=(
                        f"claimed preferred rotation '{rot_id}' does not match "
                        f"ledger preferred_rotation_id '{ledger.preferred_rotation_id}'"
                    ),
                )
            )
        elif (
            match.group("id_pref") is not None
            and ledger.preferred_rotation_id is None
            and ledger.decision_state.casefold() != "robust preference"
        ):
            violations.append(
                GroundingViolation(
                    code="DECISION_STATE_MISMATCH",
                    detail=(
                        "claimed a preferred rotation when ledger decision_state "
                        f"is '{ledger.decision_state}'"
                    ),
                )
            )

    if ledger.example_data and re.search(
        r"\b(?:not\s+example\s+data|non-example\s+declaration|real\s+producer(?:'s)?\s+field)\b",
        text,
        re.IGNORECASE,
    ):
        violations.append(
            GroundingViolation(
                code="EXAMPLE_DATA_MISMATCH",
                detail="candidate text denies synthetic example_data status of ledger",
            )
        )

    return violations


def _mask_unit_exponents(text: str) -> str:
    """Replace unit exponent suffixes like 'ha-1' -> 'haXX' preserving offsets."""
    return _UNIT_EXPONENT_RE.sub(lambda m: "X" * len(m.group(0)), text)


def _verify_numeric_grounding(
    text: str, ledger: GroundedFactLedger
) -> list[GroundingViolation]:
    violations: list[GroundingViolation] = []
    known_units = _collect_known_units(ledger)
    metric_pattern = _build_metric_pattern(ledger)
    ledger_sources = frozenset(
        fact.source for fact in ledger.facts if fact.source is not None
    )
    ledger_missing_details = frozenset(
        fact.missing.detail
        for fact in ledger.facts
        if fact.missing is not None and fact.missing.detail is not None
    )

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        source_spans = _verified_source_spans(
            raw_line, ledger_sources, ledger_missing_details
        )
        masked_line = _mask_unit_exponents(raw_line)

        for clause_offset, raw_clause in _split_clauses(raw_line):
            masked_clause = masked_line[clause_offset : clause_offset + len(raw_clause)]
            metric_mentions: list[tuple[int, int, str]] = []
            if metric_pattern is not None:
                for m in metric_pattern.finditer(raw_clause):
                    metric_mentions.append(
                        (
                            m.start(),
                            m.end(),
                            _normalize_metric_alias(m.group(0), ledger),
                        )
                    )

            for num_match in _NUMERIC_RE.finditer(masked_clause):
                line_pos = clause_offset + num_match.start()
                if _in_spans(line_pos, source_spans):
                    continue

                raw_num = num_match.group(0)
                is_pct = num_match.group("pct") is not None
                sign_str = num_match.group("sign") or ""
                mantissa_str = num_match.group("mantissa").replace(",", "")
                exp_str = num_match.group("exp") or ""
                num_str = f"{sign_str}{mantissa_str}{exp_str}"
                try:
                    candidate_val = float(num_str)
                except ValueError:
                    violations.append(
                        GroundingViolation(
                            code="UNGROUNDED_NUMBER",
                            detail=f"unparseable numeric literal '{raw_num.strip()}'",
                        )
                    )
                    continue
                if not math.isfinite(candidate_val):
                    violations.append(
                        GroundingViolation(
                            code="UNGROUNDED_NUMBER",
                            detail=f"non-finite numeric literal '{raw_num.strip()}'",
                        )
                    )
                    continue

                decimals = _count_decimals(mantissa_str)
                unit_token = _extract_unit_at(
                    raw_clause,
                    num_match.start(),
                    num_match.end(),
                    is_pct,
                    known_units,
                )

                # Determine metric scope & segment boundaries inside the clause.
                seg_start = 0
                seg_end = len(raw_clause)
                metric_scope: str | None = None
                active_idx = -1
                for idx, (m_start, _m_end, m_id) in enumerate(metric_mentions):
                    if m_start <= num_match.start():
                        metric_scope = m_id
                        active_idx = idx
                    elif m_start > num_match.end():
                        seg_end = m_start
                        break
                if active_idx > 0:
                    prev_metric_end = metric_mentions[active_idx - 1][1]
                    # Narrow past any prior comma/conjunction after the previous
                    # metric so badges on an earlier metric do not bleed over.
                    prefix_slice = raw_clause[
                        prev_metric_end : metric_mentions[active_idx][0]
                    ]
                    sep_match = None
                    for sep in re.finditer(
                        r"(?:,\s*(?:and\s+)?|\band\b|\bwhile\b|\bwhereas\b)",
                        prefix_slice,
                    ):
                        sep_match = sep
                    if sep_match is not None:
                        seg_start = prev_metric_end + sep_match.end()
                    else:
                        seg_start = metric_mentions[active_idx][0]
                if metric_scope is None and len(metric_mentions) == 1:
                    metric_scope = metric_mentions[0][2]

                segment = raw_clause[seg_start:seg_end]
                if active_idx >= 0:
                    active_start, active_end, _ = metric_mentions[active_idx]
                    provenance_scope = _extract_provenance(
                        raw_clause[active_start:seg_end]
                    ) or _extract_provenance(raw_clause[seg_start:active_end])
                else:
                    provenance_scope = _extract_provenance(segment)
                rotation_scope = _extract_rotation_scope(
                    segment, ledger.allowed_rotations, known_units
                )

                # Grounding ag_year metadata (only when explicitly written as ag_year=YYYY).
                before_num = raw_clause[seg_start : num_match.start()]
                if re.search(r"\bag_year\s*=\s*$", before_num, re.IGNORECASE) and any(
                    f.ag_year is not None
                    and candidate_val == float(f.ag_year)
                    and (metric_scope is None or f.metric_id == metric_scope)
                    and (rotation_scope is None or f.rotation_id == rotation_scope)
                    for f in ledger.facts
                ):
                    continue

                # Check if metric_scope refers exclusively to Missing fact(s).
                if metric_scope is not None:
                    scoped_facts = [
                        f for f in ledger.facts if f.metric_id == metric_scope
                    ]
                    if scoped_facts and all(f.value is None for f in scoped_facts):
                        violations.append(
                            GroundingViolation(
                                code="MISSING_VALUE_FABRICATED",
                                detail=(
                                    f"metric '{metric_scope}' is Missing in ledger "
                                    f"and cannot carry numeric literal '{raw_num.strip()}'"
                                ),
                            )
                        )
                        continue

                present_facts = [f for f in ledger.facts if f.value is not None]
                value_matches = [
                    f
                    for f in present_facts
                    if _fact_matches_number(f, candidate_val, decimals)
                ]
                if not value_matches:
                    violations.append(
                        GroundingViolation(
                            code="UNGROUNDED_NUMBER",
                            detail=(
                                f"numeric literal '{raw_num.strip()}' has no matching "
                                "fact in ledger within declared precision"
                            ),
                        )
                    )
                    continue

                # Enforce metric, rotation, unit, and provenance consistency on
                # at least one matching fact.
                matched_facts = value_matches
                if metric_scope is not None:
                    by_metric = [
                        f for f in matched_facts if f.metric_id == metric_scope
                    ]
                    if not by_metric:
                        violations.append(
                            GroundingViolation(
                                code="METRIC_PROVENANCE_MISMATCH",
                                detail=(
                                    f"numeric literal '{raw_num.strip()}' does not "
                                    f"belong to metric '{metric_scope}'"
                                ),
                            )
                        )
                        continue
                    matched_facts = by_metric

                if rotation_scope is not None:
                    by_rotation = [
                        f
                        for f in matched_facts
                        if f.rotation_id is None or f.rotation_id == rotation_scope
                    ]
                    if not by_rotation:
                        violations.append(
                            GroundingViolation(
                                code="METRIC_PROVENANCE_MISMATCH",
                                detail=(
                                    f"numeric literal '{raw_num.strip()}' does not "
                                    f"belong to rotation '{rotation_scope}'"
                                ),
                            )
                        )
                        continue
                    matched_facts = by_rotation

                if unit_token is not None:
                    by_unit = [f for f in matched_facts if f.unit == unit_token]
                    if not by_unit:
                        violations.append(
                            GroundingViolation(
                                code="UNIT_MISMATCH",
                                detail=(
                                    f"unit '{unit_token}' on literal '{raw_num.strip()}' "
                                    "does not match ledger fact unit"
                                ),
                            )
                        )
                        continue
                    matched_facts = by_unit
                elif any(f.unit == "%" for f in matched_facts) and not any(
                    f.unit != "%" for f in matched_facts
                ):
                    violations.append(
                        GroundingViolation(
                            code="UNIT_MISMATCH",
                            detail=(
                                f"percentage fact requires '%' unit on literal "
                                f"'{raw_num.strip()}'"
                            ),
                        )
                    )
                    continue

                if provenance_scope is not None:
                    by_prov = [
                        f for f in matched_facts if f.provenance == provenance_scope
                    ]
                    if not by_prov:
                        violations.append(
                            GroundingViolation(
                                code="PROVENANCE_MISMATCH",
                                detail=(
                                    f"provenance '{provenance_scope}' on literal "
                                    f"'{raw_num.strip()}' does not match ledger fact "
                                    "provenance"
                                ),
                            )
                        )
                        continue

    return violations


def verify_explanation_grounding(
    candidate_text: str,
    ledger: GroundedFactLedger,
) -> GroundingVerificationResult:
    """Verify hypothesis-mode candidate explanation text against ``ledger``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13, frontier plan §5.8).
    Rejects any hallucinated numeric literal, percentage mismatch, unit or
    provenance mismatch, fabricated missing value, unallowed rotation,
    contradicted decision state, agronomic advice, prescriptive guarantee, or
    false NASA/official endorsement with
    ``GroundingVerificationResult(verified=False, reason="CONTROL_FAILED",
    violations=(...))`` and never surfaces withheld candidate text.
    """
    if not isinstance(candidate_text, str):
        raise TypeError(
            f"candidate_text: expected str, got {type(candidate_text).__name__} (G5)"
        )
    if not isinstance(ledger, GroundedFactLedger):
        raise TypeError(
            f"ledger: expected GroundedFactLedger, got {type(ledger).__name__} (G5)"
        )

    if candidate_text.strip() == "":
        return GroundingVerificationResult(
            verified=False,
            reason="CONTROL_FAILED",
            violations=(
                GroundingViolation(
                    code="EMPTY_CANDIDATE",
                    detail="candidate explanation text is empty or blank",
                ),
            ),
            surfaced_text=None,
        )

    violations: list[GroundingViolation] = []
    violations.extend(_check_prohibited_patterns(candidate_text))
    violations.extend(_check_decision_state_and_rotations(candidate_text, ledger))
    violations.extend(_verify_numeric_grounding(candidate_text, ledger))

    if violations:
        return GroundingVerificationResult(
            verified=False,
            reason="CONTROL_FAILED",
            violations=tuple(violations),
            surfaced_text=None,
        )

    return GroundingVerificationResult(
        verified=True,
        reason=None,
        violations=(),
        surfaced_text=candidate_text,
    )
