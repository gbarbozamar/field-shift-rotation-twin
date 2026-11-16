import rawDecisionOutput from '../data/PLACEHOLDER_decision_output.json'
import type {
  MissingPart,
  ProvenanceLabel,
  ReasonCode,
  UncertaintyRange,
  ValueItem,
} from '../components/ValueDisplay'

/**
 * The decision of the decision section. Two documents reach it, read by the
 * one parser below:
 *
 * - the contract example of decision output, copied unchanged from
 *   contracts/decision_output/examples/ into web/src/data/ (issue #241). Its
 *   values are placeholders, written by hand; no decision layer produced
 *   them. It is the labelled fallback of the section;
 * - the document POST /api/decisions/run returns (D198, issue #354), which
 *   the platform serializes with every null kept (model_dump(mode="json"),
 *   never exclude_none). On a key whose null carries no meaning of its own,
 *   an explicit null is read as the key being absent (withoutOptionalNulls).
 *
 * The parser reads exactly the parts the section renders, the field
 * identifier, the state of the decision with its reasons (D7), the state of
 * each rotation pair with its reason, its preferred rotation and its coverage
 * (D85, D86, D91), the two counts of a pair's cells shown apart and never
 * added, each naming its carbon model and computation when it carries them
 * (D87, D99, D169), the range across scenarios of the years within the limit
 * (D96), the counts by year (D1, D94, D95), the paired differences (D2), and
 * the measurement priority (D4), and enforces, on those parts, the rules of
 * the contract that the render relies on:
 *
 * - a pair holds two different non-empty rotation ids (D2);
 * - a state holds a value or a missing part with its reason, never both,
 *   never neither (C3.1); its reason and its reason-missing part are never
 *   both present (C3.1); a preferred rotation is one of the pair, and a pair
 *   that is not evaluated names none (D74, D85);
 * - the coverage holds non-negative counts and "k of N" never has k above N
 *   (D91);
 * - the count by the sign of the point value holds counts or a missing part
 *   with its reason, the tolerance of "equal", never both (C3.1, D87);
 * - a range across scenarios gives its minimum, its maximum and the scenario
 *   of the minimum together, or a missing part with its reason, never both
 *   (C3.1, D96), and the minimum never exceeds the maximum;
 * - a count by year counts only non-carbon ag-year rows, with
 *   years_within_limits null or <= years_evaluated, and each not_evaluated row
 *   carrying its ag_year and missing reason (D1, D95);
 * - a paired difference carries an ag_year iff time_basis is ag_year, and a
 *   C2.1/C3.1 ValueItem;
 * - measure_first items carry rank >= 1, non-empty what and why, in
 *   non-decreasing rank order (D4).
 *
 * Pure: value in, typed decision out, or an Error naming what is wrong. The
 * errors are technical codes without wording; nothing user-visible lives
 * here. The parts of the document the section does not render, the limits
 * and the tolerances, are not parsed; nothing is invented for them.
 */

/** The three indicator identifiers of the conventions (C1.1). */
export type IndicatorId = 'soil_loss' | 'water_deficit_exposure' | 'soil_carbon_trend'

/** A pair of rotations: two different rotation ids (D2). */
export type Pair = [string, string]

/** The coverage of a pair: the cells compared over all the cells of the pair (D91). */
export interface Coverage {
  cells_compared: number
  cells_of_the_pair: number
}

/**
 * The state of a pair that is evaluated: its value verbatim, its reason or
 * the reason-missing part (D85, D86), and the rotation a robust preference
 * prefers when the state names one (D74).
 */
export interface PairStateEvaluated {
  pair: Pair
  value: string
  reason?: string
  reason_missing?: MissingPart
  preferred_rotation_id?: string
  coverage: Coverage
}

/** The state of a pair that is not evaluated: no state, a missing part with its reason (D85). */
export interface PairStateNotEvaluated {
  pair: Pair
  value: null
  missing: MissingPart
  coverage: Coverage
}

/**
 * The state of one pair of rotations across the scenarios (D85, D86, D88,
 * D97): its value verbatim, the science wording travels as data, or its
 * missing part when the pair is not evaluated (D85), its reason or the
 * reason-missing part of a state no decision gives a reason (D86), the
 * preferred rotation of a robust preference (D74), and its coverage "k of N"
 * (D91).
 */
export type PairState = PairStateEvaluated | PairStateNotEvaluated

/**
 * The state of the whole decision (D7): its value verbatim, or the missing
 * part that says why the decision layer gives none, and its reasons, each a
 * sentence of the decision layer rendered as data.
 */
export type DecisionState =
  | { value: string; reasons: string[] }
  | { value: null; missing: MissingPart; reasons: string[] }

/** The cells of a pair whose paired difference has a range, classed by that range (D99). */
export interface CountByDifferenceRange {
  strict_improvement: number
  deterioration: number
  not_separated: number
}

/** Every cell of the pair, classed by the sign of the point value (D87, D99). */
export interface CountBySignOfPointValue {
  better: number
  worse: number
  equal: number
  missing_side: number
}

/** The counts of a pair's cells when the tolerance of "equal" is set: both counts travel (D87, D99). */
export interface PairCellCountGiven {
  pair: Pair
  scenario_id: string
  indicator: IndicatorId
  carbon_model?: string
  computation?: string
  by_difference_range: CountByDifferenceRange
  by_sign_of_point_value: CountBySignOfPointValue
}

/** The counts of a pair's cells without the tolerance of "equal": the second count is missing with its reason (D87, C3.1). */
export interface PairCellCountToleranceMissing {
  pair: Pair
  scenario_id: string
  indicator: IndicatorId
  carbon_model?: string
  computation?: string
  by_difference_range: CountByDifferenceRange
  by_sign_of_point_value: null
  by_sign_of_point_value_missing: MissingPart
}

/**
 * The two counts of one pair of rotations, in one scenario, for one
 * indicator (D87): by difference range and by sign of the point value,
 * shown apart and never added (D99). A count of soil carbon trend names its
 * carbon model and computation (D169): the counts of two models are two
 * counts, never one.
 */
export type PairCellCount = PairCellCountGiven | PairCellCountToleranceMissing

/** The range across the admitted scenarios, given with the scenario of its minimum (D96). */
export interface RangeGiven {
  rotation_id: string
  indicator: IndicatorId
  carbon_model?: string
  computation?: string
  minimum: number
  maximum: number
  scenario_of_the_minimum: string
}

/** The range across the admitted scenarios that is not given, with the reason (D96, C3.1). */
export interface RangeMissing {
  rotation_id: string
  indicator: IndicatorId
  carbon_model?: string
  computation?: string
  minimum: null
  maximum: null
  scenario_of_the_minimum: null
  missing: MissingPart
}

/**
 * The range across the admitted scenarios of the years within the limit of
 * one rotation and one indicator (D96). A carbon model and a computation
 * name the cell of soil carbon trend (C1.5) when the entry carries them.
 */
export type RangeAcrossScenarios = RangeGiven | RangeMissing

/** The time basis of a results-table cell or paired difference (C1.2, C1.3, C1.5). */
export type TimeBasis = 'ag_year' | 'rotation'

/** One agricultural-year row of the results table not evaluated against a limit (D1, D95). */
export interface NotEvaluatedRow {
  time_basis: 'ag_year'
  ag_year: number
  carbon_model?: string
  computation?: string
  missing: MissingPart
}

/** The counts of one rotation, one scenario and one indicator against its limit (D1, D94, D95). */
export interface CountByYear {
  rotation_id: string
  scenario_id: string
  indicator: IndicatorId
  carbon_model?: string
  computation?: string
  years_evaluated: number
  years_within_limits: number | null
  not_evaluated: NotEvaluatedRow[]
}

/** One paired difference between two rotations in one cell (D2). */
export interface PairedDifferenceItem {
  pair: Pair
  scenario_id: string
  indicator: IndicatorId
  time_basis: TimeBasis
  ag_year?: number
  carbon_model?: string
  computation?: string
  difference: ValueItem
  method: string
}

/** One item of the measurement priority (D4): qualitative, no monetary value. */
export interface MeasureFirstItem {
  rank: number
  what: string
  why: string
}

/** One decision-output document, reduced to the parts the section renders. */
export interface DecisionOutput {
  example_data: boolean
  field_id: string
  state: DecisionState
  counts_by_year: CountByYear[]
  paired_differences: PairedDifferenceItem[]
  pair_states: PairState[]
  pair_cell_counts: PairCellCount[]
  range_across_scenarios: RangeAcrossScenarios[]
  measure_first: MeasureFirstItem[]
}

// --- small guards -------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * The keys whose explicit null carries a meaning of the contract: a state
 * that is not given (value), a count by sign that is not given
 * (by_sign_of_point_value), and an unjudged limit count (years_within_limits).
 * Their null is kept.
 */
const NULL_MEANS_SOMETHING: readonly string[] = [
  'value',
  'by_sign_of_point_value',
  'years_within_limits',
]

/**
 * The platform serializes the contract models with every null kept. On
 * every other key an explicit null means the part is absent, so it is read
 * as absent: a copy of the object without those keys. The object passed in
 * is not changed.
 */
function withoutOptionalNulls(value: Record<string, unknown>): Record<string, unknown> {
  const copy: Record<string, unknown> = {}
  for (const [key, item] of Object.entries(value)) {
    if (item === null && !NULL_MEANS_SOMETHING.includes(key)) {
      continue
    }
    copy[key] = item
  }
  return copy
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

const PROVENANCE_LABELS: readonly ProvenanceLabel[] = [
  'DECLARED',
  'OBSERVED',
  'DERIVED',
  'SIMULATED',
]

function isProvenanceLabel(value: unknown): value is ProvenanceLabel {
  return typeof value === 'string' && (PROVENANCE_LABELS as readonly string[]).includes(value)
}

const INDICATOR_IDS: readonly IndicatorId[] = [
  'soil_loss',
  'water_deficit_exposure',
  'soil_carbon_trend',
]

function isIndicatorId(value: unknown): value is IndicatorId {
  return typeof value === 'string' && (INDICATOR_IDS as readonly string[]).includes(value)
}

const REASON_CODES: readonly ReasonCode[] = [
  'NOT_DECLARED',
  'SOURCE_UNAVAILABLE',
  'NO_COVERAGE',
  'MISSING_INPUT',
  'NOT_COMPUTABLE',
  'CONTROL_FAILED',
  'NOT_AVAILABLE',
  'NOT_APPLICABLE',
]

function isReasonCode(value: unknown): value is ReasonCode {
  return typeof value === 'string' && (REASON_CODES as readonly string[]).includes(value)
}

/** A missing part: a reason code of C3.2, and its detail when it carries one (C3.1). */
export function parseMissing(raw: unknown, what: string): MissingPart {
  if (!isRecord(raw)) {
    throw new Error(`${what}:missing-not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  if (!isReasonCode(value.reason)) {
    throw new Error(`${what}:reason-not-a-code`)
  }
  const missing: MissingPart = { reason: value.reason }
  if (value.detail !== undefined) {
    if (!isNonEmptyString(value.detail)) {
      throw new Error(`${what}:detail-empty`)
    }
    missing.detail = value.detail
  }
  return missing
}

/** A pair: two different non-empty rotation ids (D2). */
function parsePair(value: unknown, what: string): Pair {
  if (!Array.isArray(value) || value.length !== 2) {
    throw new Error(`${what}:pair-not-two-ids`)
  }
  if (!isNonEmptyString(value[0]) || !isNonEmptyString(value[1])) {
    throw new Error(`${what}:pair-id-empty`)
  }
  if (value[0] === value[1]) {
    throw new Error(`${what}:pair-holds-one-rotation-twice`)
  }
  return [value[0], value[1]]
}

/** True when two pairs hold the same two rotations, in either order. */
export function samePair(a: Pair, b: Pair): boolean {
  return (a[0] === b[0] && a[1] === b[1]) || (a[0] === b[1] && a[1] === b[0])
}

// --- the state of a pair (D85, D86, D91) ----------------------------------------

function parseCoverage(value: unknown, what: string): Coverage {
  if (!isRecord(value)) {
    throw new Error(`${what}:coverage-not-an-object`)
  }
  if (!isCount(value.cells_compared) || !isCount(value.cells_of_the_pair)) {
    throw new Error(`${what}:coverage-not-a-count`)
  }
  if (value.cells_compared > value.cells_of_the_pair) {
    throw new Error(`${what}:coverage-compared-above-the-pair`)
  }
  return { cells_compared: value.cells_compared, cells_of_the_pair: value.cells_of_the_pair }
}

function parsePairState(raw: unknown, what: string): PairState {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  const pair = parsePair(value.pair, what)
  const coverage = parseCoverage(value.coverage, `${what}:coverage`)
  const preferred = parseOptionalId(value.preferred_rotation_id, `${what}:preferred-rotation-id`)
  if (value.value === null) {
    if (value.missing === undefined) {
      throw new Error(`${what}:value-null-without-missing-part`)
    }
    if (value.reason !== undefined || value.reason_missing !== undefined) {
      throw new Error(`${what}:not-evaluated-with-a-reason`)
    }
    if (preferred !== undefined) {
      throw new Error(`${what}:not-evaluated-with-a-preferred-rotation`)
    }
    return { pair, value: null, missing: parseMissing(value.missing, what), coverage }
  }
  if (preferred !== undefined && !pair.includes(preferred)) {
    throw new Error(`${what}:preferred-rotation-not-of-the-pair`)
  }
  if (!isNonEmptyString(value.value)) {
    throw new Error(`${what}:value-not-a-state-name`)
  }
  if (value.missing !== undefined) {
    throw new Error(`${what}:value-and-missing-part`)
  }
  if (value.reason !== undefined && value.reason_missing !== undefined) {
    throw new Error(`${what}:reason-and-reason-missing`)
  }
  const state: PairStateEvaluated = { pair, value: value.value, coverage }
  if (value.reason !== undefined) {
    if (!isNonEmptyString(value.reason)) {
      throw new Error(`${what}:reason-empty`)
    }
    state.reason = value.reason
  }
  if (value.reason_missing !== undefined) {
    state.reason_missing = parseMissing(value.reason_missing, `${what}:reason-missing`)
  }
  if (preferred !== undefined) {
    state.preferred_rotation_id = preferred
  }
  return state
}

// --- the state of the decision (D7) ----------------------------------------------

function parseDecisionState(raw: unknown, what: string): DecisionState {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  const reasons = parseList(value.reasons, `${what}:reasons`).map((reason, index) => {
    if (!isNonEmptyString(reason)) {
      throw new Error(`${what}:reasons[${index}]-empty`)
    }
    return reason
  })
  if (value.value === null) {
    if (value.missing === undefined) {
      throw new Error(`${what}:value-null-without-missing-part`)
    }
    return { value: null, missing: parseMissing(value.missing, what), reasons }
  }
  if (!isNonEmptyString(value.value)) {
    throw new Error(`${what}:value-not-a-state-name`)
  }
  if (value.missing !== undefined) {
    throw new Error(`${what}:value-and-missing-part`)
  }
  return { value: value.value, reasons }
}

// --- the two counts of a pair's cells (D87, D99) ---------------------------------

function parseCounts(
  value: Record<string, unknown>,
  keys: readonly string[],
  what: string,
): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const key of keys) {
    if (!isCount(value[key])) {
      throw new Error(`${what}:${key.replace(/_/g, '-')}-not-a-count`)
    }
    counts[key] = value[key]
  }
  return counts
}

function parsePairCellCount(raw: unknown, what: string): PairCellCount {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  const pair = parsePair(value.pair, what)
  if (!isNonEmptyString(value.scenario_id)) {
    throw new Error(`${what}:scenario-id-empty`)
  }
  if (!isIndicatorId(value.indicator)) {
    throw new Error(`${what}:indicator-not-an-id`)
  }
  // The key of D169: a count of soil carbon trend names its model and
  // computation; they travel as data, and the count is never merged.
  const cell = {
    pair,
    scenario_id: value.scenario_id,
    indicator: value.indicator,
    carbon_model: parseOptionalId(value.carbon_model, `${what}:carbon-model`),
    computation: parseOptionalId(value.computation, `${what}:computation`),
  }
  if (!isRecord(value.by_difference_range)) {
    throw new Error(`${what}:by-difference-range-not-an-object`)
  }
  const byDifferenceRange = parseCounts(
    value.by_difference_range,
    ['strict_improvement', 'deterioration', 'not_separated'],
    `${what}:by-difference-range`,
  )
  const given = value.by_sign_of_point_value
  if (given === null) {
    if (value.by_sign_of_point_value_missing === undefined) {
      throw new Error(`${what}:by-sign-of-point-value-null-without-missing-part`)
    }
    if (!isRecord(value.by_sign_of_point_value_missing)) {
      throw new Error(`${what}:by-sign-of-point-value-missing-not-an-object`)
    }
    return {
      ...cell,
      by_difference_range: {
        strict_improvement: byDifferenceRange.strict_improvement,
        deterioration: byDifferenceRange.deterioration,
        not_separated: byDifferenceRange.not_separated,
      },
      by_sign_of_point_value: null,
      by_sign_of_point_value_missing: parseMissing(
        value.by_sign_of_point_value_missing,
        `${what}:by-sign-of-point-value-missing`,
      ),
    }
  }
  if (value.by_sign_of_point_value_missing !== undefined) {
    throw new Error(`${what}:by-sign-of-point-value-and-missing-part`)
  }
  if (!isRecord(given)) {
    throw new Error(`${what}:by-sign-of-point-value-not-an-object`)
  }
  const bySign = parseCounts(
    given,
    ['better', 'worse', 'equal', 'missing_side'],
    `${what}:by-sign-of-point-value`,
  )
  return {
    ...cell,
    by_difference_range: {
      strict_improvement: byDifferenceRange.strict_improvement,
      deterioration: byDifferenceRange.deterioration,
      not_separated: byDifferenceRange.not_separated,
    },
    by_sign_of_point_value: {
      better: bySign.better,
      worse: bySign.worse,
      equal: bySign.equal,
      missing_side: bySign.missing_side,
    },
  }
}

// --- the range across scenarios (D96) ---------------------------------------------

function parseOptionalId(value: unknown, what: string): string | undefined {
  if (value === undefined) {
    return undefined
  }
  if (!isNonEmptyString(value)) {
    throw new Error(`${what}:empty`)
  }
  return value
}

function parseRangeAcrossScenarios(raw: unknown, what: string): RangeAcrossScenarios {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  // The route serializes the contract without exclude_none: an explicit null
  // of a bound, of the scenario of the minimum or of the missing part means
  // the part was never set, so it is read as absent before the key-presence
  // checks (the same rule the run seam applies).
  const value = withoutOptionalNulls(raw)
  if (!isNonEmptyString(value.rotation_id)) {
    throw new Error(`${what}:rotation-id-empty`)
  }
  if (!isIndicatorId(value.indicator)) {
    throw new Error(`${what}:indicator-not-an-id`)
  }
  const carbonModel = parseOptionalId(value.carbon_model, `${what}:carbon-model`)
  const computation = parseOptionalId(value.computation, `${what}:computation`)
  const given =
    value.minimum !== undefined ||
    value.maximum !== undefined ||
    value.scenario_of_the_minimum !== undefined
  if (!given) {
    if (value.missing === undefined) {
      throw new Error(`${what}:range-absent-without-missing-part`)
    }
    return {
      rotation_id: value.rotation_id,
      indicator: value.indicator,
      carbon_model: carbonModel,
      computation,
      minimum: null,
      maximum: null,
      scenario_of_the_minimum: null,
      missing: parseMissing(value.missing, what),
    }
  }
  if (value.missing !== undefined) {
    throw new Error(`${what}:range-and-missing-part`)
  }
  if (!isCount(value.minimum) || !isCount(value.maximum)) {
    throw new Error(`${what}:bounds-not-a-count`)
  }
  if (!isNonEmptyString(value.scenario_of_the_minimum)) {
    throw new Error(`${what}:scenario-of-the-minimum-empty`)
  }
  if (value.minimum > value.maximum) {
    throw new Error(`${what}:minimum-above-maximum`)
  }
  return {
    rotation_id: value.rotation_id,
    indicator: value.indicator,
    carbon_model: carbonModel,
    computation,
    minimum: value.minimum,
    maximum: value.maximum,
    scenario_of_the_minimum: value.scenario_of_the_minimum,
  }
}

// --- counts by year (D1, D94, D95) -------------------------------------------------

function parseNotEvaluatedRow(raw: unknown, what: string): NotEvaluatedRow {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  if (value.time_basis !== 'ag_year') {
    throw new Error(`${what}:time-basis-not-ag-year`)
  }
  if (!isInteger(value.ag_year)) {
    throw new Error(`${what}:ag-year-not-an-integer`)
  }
  return {
    time_basis: 'ag_year',
    ag_year: value.ag_year,
    carbon_model: parseOptionalId(value.carbon_model, `${what}:carbon-model`),
    computation: parseOptionalId(value.computation, `${what}:computation`),
    missing: parseMissing(value.missing, what),
  }
}

function parseCountByYear(raw: unknown, what: string): CountByYear {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  if (!isNonEmptyString(value.rotation_id)) {
    throw new Error(`${what}:rotation-id-empty`)
  }
  if (!isNonEmptyString(value.scenario_id)) {
    throw new Error(`${what}:scenario-id-empty`)
  }
  if (!isIndicatorId(value.indicator)) {
    throw new Error(`${what}:indicator-not-an-id`)
  }
  if (value.indicator === 'soil_carbon_trend') {
    throw new Error(`${what}:soil-carbon-trend-has-no-count-by-year`)
  }
  if (!isCount(value.years_evaluated)) {
    throw new Error(`${what}:years-evaluated-not-a-count`)
  }
  let yearsWithinLimits: number | null
  if (value.years_within_limits === null) {
    yearsWithinLimits = null
  } else if (isCount(value.years_within_limits)) {
    if (value.years_within_limits > value.years_evaluated) {
      throw new Error(`${what}:within-greater-than-evaluated`)
    }
    yearsWithinLimits = value.years_within_limits
  } else {
    throw new Error(`${what}:years-within-limits-invalid`)
  }
  const notEvaluated = parseList(value.not_evaluated, `${what}:not-evaluated`).map(
    (entry, index) => parseNotEvaluatedRow(entry, `${what}:not-evaluated[${index}]`),
  )
  return {
    rotation_id: value.rotation_id,
    scenario_id: value.scenario_id,
    indicator: value.indicator,
    carbon_model: parseOptionalId(value.carbon_model, `${what}:carbon-model`),
    computation: parseOptionalId(value.computation, `${what}:computation`),
    years_evaluated: value.years_evaluated,
    years_within_limits: yearsWithinLimits,
    not_evaluated: notEvaluated,
  }
}

// --- paired differences (D2) --------------------------------------------------------

function parseRange(raw: unknown, what: string): UncertaintyRange {
  if (!isRecord(raw)) {
    throw new Error(`${what}:range-not-an-object`)
  }
  if (!isFiniteNumber(raw.low) || !isFiniteNumber(raw.high)) {
    throw new Error(`${what}:range-bounds-not-finite`)
  }
  if (raw.low > raw.high) {
    throw new Error(`${what}:range-low-above-high`)
  }
  if (!isNonEmptyString(raw.kind)) {
    throw new Error(`${what}:range-kind-empty`)
  }
  return { low: raw.low, high: raw.high, kind: raw.kind }
}

function parseValueItem(raw: unknown, what: string): ValueItem {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  if (!isNonEmptyString(value.unit)) {
    throw new Error(`${what}:unit-empty`)
  }
  const unit = value.unit
  if (value.value === null) {
    if (value.missing === undefined) {
      throw new Error(`${what}:missing-part-absent`)
    }
    if (value.range !== undefined || value.range_missing !== undefined) {
      throw new Error(`${what}:missing-with-range`)
    }
    if (value.provenance !== undefined || value.source !== undefined) {
      throw new Error(`${what}:missing-with-provenance`)
    }
    return { value: null, unit, missing: parseMissing(value.missing, what) }
  }
  if (!isFiniteNumber(value.value)) {
    throw new Error(`${what}:value-not-a-number`)
  }
  if (value.missing !== undefined) {
    throw new Error(`${what}:value-and-missing`)
  }
  if (!isProvenanceLabel(value.provenance)) {
    throw new Error(`${what}:provenance-not-a-label`)
  }
  if (value.assumption !== undefined && typeof value.assumption !== 'boolean') {
    throw new Error(`${what}:assumption-not-a-boolean`)
  }
  let source: string | undefined
  if (value.source === undefined) {
    source = undefined
  } else if (isNonEmptyString(value.source)) {
    source = value.source
  } else {
    throw new Error(`${what}:source-empty`)
  }
  const assumption = value.assumption === true
  if (source === undefined && !assumption) {
    throw new Error(`${what}:source-or-assumption-absent`)
  }
  if (value.range !== undefined && value.range_missing !== undefined) {
    throw new Error(`${what}:range-and-range-missing`)
  }
  const range = value.range === undefined ? undefined : parseRange(value.range, what)
  const rangeMissing =
    value.range_missing === undefined
      ? undefined
      : parseMissing(value.range_missing, `${what}:range-missing`)
  if (range === undefined && rangeMissing === undefined) {
    throw new Error(`${what}:range-or-range-missing-absent`)
  }
  return {
    value: value.value,
    unit,
    provenance: value.provenance,
    source,
    assumption: assumption ? true : undefined,
    range,
    range_missing: rangeMissing,
  }
}

function parsePairedDifferenceItem(raw: unknown, what: string): PairedDifferenceItem {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  const value = withoutOptionalNulls(raw)
  const pair = parsePair(value.pair, what)
  if (!isNonEmptyString(value.scenario_id)) {
    throw new Error(`${what}:scenario-id-empty`)
  }
  if (!isIndicatorId(value.indicator)) {
    throw new Error(`${what}:indicator-not-an-id`)
  }
  if (value.time_basis !== 'ag_year' && value.time_basis !== 'rotation') {
    throw new Error(`${what}:time-basis-invalid`)
  }
  let agYear: number | undefined
  if (value.time_basis === 'ag_year') {
    if (!isInteger(value.ag_year)) {
      throw new Error(`${what}:ag-year-not-an-integer`)
    }
    agYear = value.ag_year
  } else if (value.ag_year !== undefined) {
    throw new Error(`${what}:rotation-basis-with-ag-year`)
  }
  if (!isNonEmptyString(value.method)) {
    throw new Error(`${what}:method-empty`)
  }
  return {
    pair,
    scenario_id: value.scenario_id,
    indicator: value.indicator,
    time_basis: value.time_basis,
    ag_year: agYear,
    carbon_model: parseOptionalId(value.carbon_model, `${what}:carbon-model`),
    computation: parseOptionalId(value.computation, `${what}:computation`),
    difference: parseValueItem(value.difference, `${what}:difference`),
    method: value.method,
  }
}

// --- measurement priority (D4) ------------------------------------------------------

function parseMeasureFirstItem(raw: unknown, what: string): MeasureFirstItem {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (!isInteger(raw.rank) || raw.rank < 1) {
    throw new Error(`${what}:rank-not-positive-integer`)
  }
  if (!isNonEmptyString(raw.what)) {
    throw new Error(`${what}:what-empty`)
  }
  if (!isNonEmptyString(raw.why)) {
    throw new Error(`${what}:why-empty`)
  }
  return { rank: raw.rank, what: raw.what, why: raw.why }
}

function parseMeasureFirst(raw: unknown, what: string): MeasureFirstItem[] {
  const items = parseList(raw, what).map((entry, index) =>
    parseMeasureFirstItem(entry, `${what}[${index}]`),
  )
  for (let index = 1; index < items.length; index += 1) {
    if (items[index].rank < items[index - 1].rank) {
      throw new Error(`${what}:not-in-rank-order`)
    }
  }
  return items
}

// --- one document -------------------------------------------------------------------

function parseList(value: unknown, what: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new Error(`${what}:not-a-list`)
  }
  return value
}

/**
 * Parse and validate the parts of one decision-output document the section
 * renders. Pure: value in, typed decision out, or an Error naming what is
 * wrong.
 */
export function parseDecisionOutput(value: unknown): DecisionOutput {
  if (!isRecord(value)) {
    throw new Error('invalid-decision:not-an-object')
  }
  if (typeof value.example_data !== 'boolean') {
    throw new Error('invalid-decision:example-data-not-a-boolean')
  }
  if (!isNonEmptyString(value.field_id)) {
    throw new Error('invalid-decision:field-id-empty')
  }
  return {
    example_data: value.example_data,
    field_id: value.field_id,
    state: parseDecisionState(value.state, 'invalid-decision:state'),
    counts_by_year: parseList(value.counts_by_year, 'invalid-decision:counts-by-year').map(
      (entry, index) => parseCountByYear(entry, `invalid-decision:counts-by-year[${index}]`),
    ),
    paired_differences: parseList(
      value.paired_differences,
      'invalid-decision:paired-differences',
    ).map((entry, index) =>
      parsePairedDifferenceItem(entry, `invalid-decision:paired-differences[${index}]`),
    ),
    pair_states: parseList(value.pair_states, 'invalid-decision:pair-states').map(
      (entry, index) => parsePairState(entry, `invalid-decision:pair-states[${index}]`),
    ),
    pair_cell_counts: parseList(
      value.pair_cell_counts,
      'invalid-decision:pair-cell-counts',
    ).map((entry, index) =>
      parsePairCellCount(entry, `invalid-decision:pair-cell-counts[${index}]`),
    ),
    range_across_scenarios: parseList(
      value.range_across_scenarios,
      'invalid-decision:range-across-scenarios',
    ).map((entry, index) =>
      parseRangeAcrossScenarios(entry, `invalid-decision:range-across-scenarios[${index}]`),
    ),
    measure_first: parseMeasureFirst(value.measure_first, 'invalid-decision:measure-first'),
  }
}

/**
 * Distinct agricultural years present in counts_by_year or paired_differences,
 * sorted ascending. Discovered strictly from the document data; never invented.
 */
export function agriculturalYearsOf(document: DecisionOutput): number[] {
  const years = new Set<number>()
  for (const count of document.counts_by_year) {
    for (const row of count.not_evaluated) {
      years.add(row.ag_year)
    }
  }
  for (const diff of document.paired_differences) {
    if (diff.ag_year !== undefined) {
      years.add(diff.ag_year)
    }
  }
  return [...years].sort((a, b) => a - b)
}

/** The decision example, reduced to the parts the section renders. */
export const decisionExample: DecisionOutput = parseDecisionOutput(rawDecisionOutput)
