import rawDecisionOutput from '../data/PLACEHOLDER_decision_output.json'
import type { MissingPart, ReasonCode } from '../components/ValueDisplay'

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
 * The parser reads exactly the parts the section renders — the state of the
 * decision with its reasons (D7), the state of each rotation pair with its
 * reason, its preferred rotation and its coverage (D85, D86, D91), the two
 * counts of a pair's cells shown apart and never added, each naming its
 * carbon model and computation when it carries them (D87, D99, D169), and
 * the range across scenarios of the years within the limit (D96) — and
 * enforces, on those parts, the rules of the contract that the render relies
 * on:
 *
 * - a pair holds two different non-empty rotation ids (D2);
 * - a state holds a value or a missing part with its reason, never both,
 *   never neither (C3.1); its reason and its reason-missing part are never
 *   both present (C3.1); a preferred rotation is one of the pair, and a pair
 *   that is not evaluated names none (D74, D85);
 * - the coverage holds non-negative counts and "k of N" never has k above N
 *   (D91);
 * - the count by the sign of the point value holds counts or a missing part
 *   with its reason — the tolerance of "equal" — never both (C3.1, D87);
 * - a range across scenarios gives its minimum, its maximum and the scenario
 *   of the minimum together, or a missing part with its reason, never both
 *   (C3.1, D96), and the minimum never exceeds the maximum.
 *
 * Pure: value in, typed decision out, or an Error naming what is wrong. The
 * errors are technical codes without wording; nothing user-visible lives
 * here. The parts of the document the section does not render — the limits,
 * the counts by year, the paired differences, the tolerances, the indicators
 * not resolved, the measurement priority — are not parsed; nothing is
 * invented for them.
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
 * D97): its value verbatim — the science wording travels as data — or its
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

/** One decision-output document, reduced to the parts the section renders. */
export interface DecisionOutput {
  example_data: boolean
  state: DecisionState
  pair_states: PairState[]
  pair_cell_counts: PairCellCount[]
  range_across_scenarios: RangeAcrossScenarios[]
}

// --- small guards -------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * The keys whose explicit null carries a meaning of the contract: a state
 * that is not given (value) and a count by sign that is not given
 * (by_sign_of_point_value). Their null is kept.
 */
const NULL_MEANS_SOMETHING: readonly string[] = ['value', 'by_sign_of_point_value']

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

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
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
  return {
    example_data: value.example_data,
    state: parseDecisionState(value.state, 'invalid-decision:state'),
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
  }
}

/** The decision example, reduced to the parts the section renders. */
export const decisionExample: DecisionOutput = parseDecisionOutput(rawDecisionOutput)
