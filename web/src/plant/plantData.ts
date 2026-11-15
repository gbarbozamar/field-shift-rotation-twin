import rawPlantAnswers from '../data/PLACEHOLDER_plant_answers.json'
import type { MissingPart, ReasonCode } from '../components/ValueDisplay'

/**
 * The answers of the screen "What should I plant?" (S-019, PROPOSED).
 *
 * Where the data comes from. Without a backend the screen reads example
 * answers of the contract contracts/plant_answer/:
 *
 * - data/PLACEHOLDER_plant_answer.json is the contract example
 *   (contracts/plant_answer/examples/PLACEHOLDER_plant_answer.json), copied
 *   unchanged; a test keeps the copy equal to the contract file.
 * - data/PLACEHOLDER_plant_answers.json holds one answer per combination of
 *   strictness (on_average, every_kind) and margin_of (average, el_nino,
 *   neutral, la_nina), at today's price. It was written by a scratch script,
 *   never committed: a copy of the S-018a generator of the contract example
 *   that varies the questions only (the same example inputs, the same example
 *   soil loss) and runs the real pure functions (economics/ and
 *   kinds_of_year/). Each answer was validated with PlantAnswer and with
 *   check_answer_against_request; the on_average and average answer equals
 *   the contract example. No number in it was typed by hand.
 *
 * EVERY NUMBER IN THESE FILES IS EXAMPLE DATA: the soil loss, the limit, the
 * prices and the economic facts are example inputs taken from no source; the
 * kinds of year come from the transcribed ONI record. The screen labels them
 * as example data.
 *
 * The parser reads the parts the screen renders and refuses what the
 * contract refuses on those parts: a value with a reason, a missing value
 * without its reason (C3.1), a chosen answer without a rotation, a rotation
 * chosen when the answer is not, an answer that is not chosen without its
 * reason, a state "chosen" on another rotation than the chosen one, "none
 * meets" while an option is in another state, a limit check that is not
 * resolved without its reason, a tipping point with a price and a reason
 * together. Pure: value in, typed answer out, or an Error with a technical
 * code (no wording; nothing user-visible lives here).
 */

export type KindOfYear = 'el_nino' | 'neutral' | 'la_nina'
export type MarginOf = 'average' | KindOfYear
export type Strictness = 'on_average' | 'every_kind'
export type AnswerKind = 'chosen' | 'none_meets' | 'not_resolved'
export type OptionState = 'chosen' | 'meets' | 'does_not_meet' | 'not_resolved'
export type Verdict = 'meets' | 'does_not_meet' | 'not_resolved'

export const KINDS_OF_YEAR: readonly KindOfYear[] = ['el_nino', 'neutral', 'la_nina']
export const MARGINS_OF: readonly MarginOf[] = ['average', ...KINDS_OF_YEAR]
export const STRICTNESSES: readonly Strictness[] = ['on_average', 'every_kind']
const ANSWERS: readonly AnswerKind[] = ['chosen', 'none_meets', 'not_resolved']
const STATES: readonly OptionState[] = ['chosen', 'meets', 'does_not_meet', 'not_resolved']
const VERDICTS: readonly Verdict[] = ['meets', 'does_not_meet', 'not_resolved']

/** A number with its unit, or null with the reason it is missing (C3.1). */
export type Measured =
  | { value: number; unit: string; missing: null }
  | { value: null; unit: string; missing: MissingPart }

/** A soil-loss mean: a measured value with the sources or the assumption mark (C4.2). */
export type SoilLossItem = Measured & { sources: string[]; assumption: boolean }

/** A limit check: its verdict, and its reason when it is not resolved. */
export interface LimitCheck {
  verdict: Verdict
  missing: MissingPart | null
}

export interface PlantOption {
  rotation_id: string
  state: OptionState
  margin: Record<MarginOf, Measured>
  soil_loss: Record<MarginOf, SoilLossItem>
  limit: number | null
  limit_unit: string
  on_average: LimitCheck
  every_kind: LimitCheck
  limit_check: LimitCheck
  kinds_not_met: KindOfYear[]
  kinds_not_resolved: KindOfYear[]
  kinds_not_in_record: KindOfYear[]
}

export type LimitCost =
  | { kind: 'value'; value: number; against: string; unit: string }
  | { kind: 'nothing' }
  | { kind: 'missing'; missing: MissingPart }

export type TippingPoint =
  | {
      direction: 'up' | 'down'
      price: number
      takes_over: string | null
      answer_after: AnswerKind
      distance_percent: number | null
      distance_missing: MissingPart | null
      unit: string
    }
  | { direction: 'up' | 'down'; price: null; missing: MissingPart; unit: string }

export interface TippingPrice {
  today: number | null
  unit: string
  low: number
  high: number
  up: TippingPoint
  down: TippingPoint
  missing: MissingPart | null
}

export interface PlantAnswer {
  example_data: boolean
  strictness: Strictness
  margin_of: MarginOf
  answer: AnswerKind
  chosen: string | null
  /** Why nothing is chosen: set exactly when the answer is not "chosen". */
  missing: MissingPart | null
  tied: string[]
  options: PlantOption[]
  limit_cost: LimitCost
  tipping_price: TippingPrice
  sources: { id: string; detail: string | null }[]
}

export interface PlantAnswerSet {
  example_data: boolean
  answers: PlantAnswer[]
}

// --- small guards -------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function oneOf<T extends string>(value: unknown, list: readonly T[]): value is T {
  return typeof value === 'string' && (list as readonly string[]).includes(value)
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

function record(value: unknown, what: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  return value
}

/** A reason code and its optional detail, from the reason and detail fields. */
function missingPart(reason: unknown, detail: unknown, what: string): MissingPart {
  if (!oneOf(reason, REASON_CODES)) {
    throw new Error(`${what}:reason-not-a-code`)
  }
  const missing: MissingPart = { reason }
  if (detail !== null && detail !== undefined) {
    if (!isNonEmptyString(detail)) {
      throw new Error(`${what}:detail-empty`)
    }
    missing.detail = detail
  }
  return missing
}

/** A value or a reason, never both, never neither (C3.1). */
function measured(value: unknown, what: string): Measured {
  const item = record(value, what)
  if (!isNonEmptyString(item.unit)) {
    throw new Error(`${what}:unit-empty`)
  }
  if (item.value !== null) {
    if (!isFiniteNumber(item.value)) {
      throw new Error(`${what}:value-not-a-number`)
    }
    if (item.reason !== null && item.reason !== undefined) {
      throw new Error(`${what}:value-with-a-reason`)
    }
    return { value: item.value, unit: item.unit, missing: null }
  }
  if (item.reason === null || item.reason === undefined) {
    throw new Error(`${what}:missing-without-a-reason`)
  }
  return { value: null, unit: item.unit, missing: missingPart(item.reason, item.detail, what) }
}

function soilLoss(value: unknown, what: string): SoilLossItem {
  const item = record(value, what)
  const base = measured(item, what)
  if (!Array.isArray(item.sources) || !item.sources.every(isNonEmptyString)) {
    throw new Error(`${what}:sources-not-a-list-of-texts`)
  }
  if (typeof item.assumption !== 'boolean') {
    throw new Error(`${what}:assumption-not-a-flag`)
  }
  if (base.value !== null && item.sources.length === 0 && !item.assumption) {
    throw new Error(`${what}:value-without-source-or-assumption`)
  }
  return { ...base, sources: [...item.sources], assumption: item.assumption }
}

function byMarginOf<T>(value: unknown, what: string, read: (v: unknown, w: string) => T) {
  const item = record(value, what)
  const out = {} as Record<MarginOf, T>
  for (const key of MARGINS_OF) {
    out[key] = read(item[key], `${what}:${key}`)
  }
  return out
}

function limitCheck(value: unknown, what: string): LimitCheck {
  const item = record(value, what)
  if (!oneOf(item.verdict, VERDICTS)) {
    throw new Error(`${what}:verdict-not-in-the-list`)
  }
  const hasReason = item.reason !== null && item.reason !== undefined
  if ((item.verdict === 'not_resolved') !== hasReason) {
    throw new Error(`${what}:reason-exactly-when-not-resolved`)
  }
  return {
    verdict: item.verdict,
    missing: hasReason ? missingPart(item.reason, item.detail, what) : null,
  }
}

function kinds(value: unknown, what: string): KindOfYear[] {
  if (!Array.isArray(value) || !value.every((k) => oneOf(k, KINDS_OF_YEAR))) {
    throw new Error(`${what}:not-a-list-of-kinds`)
  }
  return [...value]
}

function option(value: unknown, what: string, strictness: Strictness): PlantOption {
  const item = record(value, what)
  if (!isNonEmptyString(item.rotation_id)) {
    throw new Error(`${what}:rotation-id-empty`)
  }
  if (!oneOf(item.state, STATES)) {
    throw new Error(`${what}:state-not-in-the-list`)
  }
  const limit = record(item.limit, `${what}:limit`)
  if (limit.limit !== null && !isFiniteNumber(limit.limit)) {
    throw new Error(`${what}:limit:not-a-number`)
  }
  if (!isNonEmptyString(limit.unit)) {
    throw new Error(`${what}:limit:unit-empty`)
  }
  const onAverage = limitCheck(limit.on_average, `${what}:limit:on-average`)
  const everyKind = limitCheck(limit.every_kind, `${what}:limit:every-kind`)
  if (limit.limit === null && onAverage.verdict !== 'not_resolved') {
    // With no limit no check is resolved, so the check carries the reason.
    throw new Error(`${what}:limit:missing-with-a-resolved-check`)
  }
  const check = limitCheck(item.limit_check, `${what}:limit-check`)
  const ofStrictness = strictness === 'on_average' ? onAverage : everyKind
  if (check.verdict !== ofStrictness.verdict) {
    throw new Error(`${what}:limit-check-not-of-the-strictness`)
  }
  return {
    rotation_id: item.rotation_id,
    state: item.state,
    margin: byMarginOf(item.margin, `${what}:margin`, measured),
    soil_loss: byMarginOf(item.soil_loss, `${what}:soil-loss`, soilLoss),
    limit: limit.limit as number | null,
    limit_unit: limit.unit,
    on_average: onAverage,
    every_kind: everyKind,
    limit_check: check,
    kinds_not_met: kinds(limit.kinds_not_met, `${what}:limit:kinds-not-met`),
    kinds_not_resolved: kinds(limit.kinds_not_resolved, `${what}:limit:kinds-not-resolved`),
    kinds_not_in_record: kinds(limit.kinds_not_in_record, `${what}:limit:kinds-not-in-record`),
  }
}

function limitCost(value: unknown, what: string): LimitCost {
  const item = record(value, what)
  if (item.value !== null) {
    if (!isFiniteNumber(item.value)) {
      throw new Error(`${what}:value-not-a-number`)
    }
    if (!isNonEmptyString(item.against)) {
      throw new Error(`${what}:value-without-against`)
    }
    if (item.reason !== null || item.costs_nothing !== false) {
      throw new Error(`${what}:value-with-a-reason`)
    }
    if (!isNonEmptyString(item.unit)) {
      throw new Error(`${what}:unit-empty`)
    }
    return { kind: 'value', value: item.value, against: item.against, unit: item.unit }
  }
  if (item.costs_nothing === true) {
    if (item.reason !== null) {
      throw new Error(`${what}:nothing-with-a-reason`)
    }
    return { kind: 'nothing' }
  }
  if (item.reason === null || item.reason === undefined) {
    throw new Error(`${what}:missing-without-a-reason`)
  }
  return { kind: 'missing', missing: missingPart(item.reason, item.detail, what) }
}

function tippingPoint(value: unknown, what: string, direction: 'up' | 'down'): TippingPoint {
  const item = record(value, what)
  if (item.direction !== direction) {
    throw new Error(`${what}:direction-not-${direction}`)
  }
  if (!isNonEmptyString(item.unit)) {
    throw new Error(`${what}:unit-empty`)
  }
  if (item.price === null) {
    if (item.reason === null || item.reason === undefined) {
      throw new Error(`${what}:missing-without-a-reason`)
    }
    return {
      direction,
      price: null,
      missing: missingPart(item.reason, item.detail, what),
      unit: item.unit,
    }
  }
  if (!isFiniteNumber(item.price)) {
    throw new Error(`${what}:price-not-a-number`)
  }
  if (!oneOf(item.answer_after, ANSWERS)) {
    throw new Error(`${what}:answer-after-not-in-the-list`)
  }
  if (item.takes_over !== null && !isNonEmptyString(item.takes_over)) {
    throw new Error(`${what}:takes-over-empty`)
  }
  if ((item.answer_after === 'chosen') !== (item.takes_over !== null)) {
    throw new Error(`${what}:takes-over-exactly-when-chosen`)
  }
  if (item.distance_percent !== null) {
    if (!isFiniteNumber(item.distance_percent)) {
      throw new Error(`${what}:distance-not-a-number`)
    }
    if (item.reason !== null && item.reason !== undefined) {
      throw new Error(`${what}:value-with-a-reason`)
    }
  } else if (item.reason === null || item.reason === undefined) {
    throw new Error(`${what}:missing-distance-without-a-reason`)
  }
  return {
    direction,
    price: item.price,
    takes_over: item.takes_over as string | null,
    answer_after: item.answer_after,
    distance_percent: item.distance_percent as number | null,
    distance_missing:
      item.distance_percent === null ? missingPart(item.reason, item.detail, what) : null,
    unit: item.unit,
  }
}

function tippingPrice(value: unknown, what: string): TippingPrice {
  const item = record(value, what)
  const range = record(item.price_range, `${what}:price-range`)
  if (!isFiniteNumber(range.low) || !isFiniteNumber(range.high) || !(range.low < range.high)) {
    throw new Error(`${what}:price-range-not-low-below-high`)
  }
  if (!isNonEmptyString(item.unit)) {
    throw new Error(`${what}:unit-empty`)
  }
  const shared = item.reason !== null && item.reason !== undefined
  if (item.today !== null) {
    if (!isFiniteNumber(item.today)) {
      throw new Error(`${what}:today-not-a-number`)
    }
  } else if (!shared) {
    throw new Error(`${what}:today-missing-without-a-reason`)
  }
  return {
    today: item.today as number | null,
    unit: item.unit,
    low: range.low,
    high: range.high,
    up: tippingPoint(item.up, `${what}:up`, 'up'),
    down: tippingPoint(item.down, `${what}:down`, 'down'),
    missing: shared ? missingPart(item.reason, item.detail, what) : null,
  }
}

/**
 * Parse one answer of the contract plant_answer, reduced to the parts the
 * screen renders. Pure: value in, typed answer out, or an Error.
 */
export function parsePlantAnswer(value: unknown, what = 'invalid-plant-answer'): PlantAnswer {
  const item = record(value, what)
  if (item.contract !== 'plant_answer') {
    throw new Error(`${what}:contract-not-plant-answer`)
  }
  if (typeof item.example_data !== 'boolean') {
    throw new Error(`${what}:example-data-not-a-flag`)
  }
  const questions = record(item.questions, `${what}:questions`)
  if (!oneOf(questions.strictness, STRICTNESSES)) {
    throw new Error(`${what}:questions:strictness-not-in-the-list`)
  }
  if (!oneOf(questions.margin_of, MARGINS_OF)) {
    throw new Error(`${what}:questions:margin-of-not-in-the-list`)
  }
  const strictness = questions.strictness
  if (!oneOf(item.answer, ANSWERS)) {
    throw new Error(`${what}:answer-not-in-the-list`)
  }
  const isChosen = item.answer === 'chosen'
  if (isChosen && !isNonEmptyString(item.chosen)) {
    throw new Error(`${what}:chosen-without-a-rotation`)
  }
  if (!isChosen && item.chosen !== null) {
    throw new Error(`${what}:rotation-chosen-when-the-answer-is-not`)
  }
  const hasReason = item.reason !== null && item.reason !== undefined
  if (isChosen === hasReason) {
    throw new Error(`${what}:reason-exactly-when-nothing-is-chosen`)
  }
  if (!Array.isArray(item.options)) {
    throw new Error(`${what}:options-not-a-list`)
  }
  const options = item.options.map((entry, index) =>
    option(entry, `${what}:options[${index}]`, strictness),
  )
  const ids = options.map((o) => o.rotation_id)
  if (new Set(ids).size !== ids.length) {
    throw new Error(`${what}:options-share-a-rotation-id`)
  }
  const inStateChosen = options.filter((o) => o.state === 'chosen').map((o) => o.rotation_id)
  if (inStateChosen.join('\n') !== (isChosen ? String(item.chosen) : '')) {
    throw new Error(`${what}:state-chosen-not-on-the-chosen-rotation`)
  }
  if (item.answer === 'none_meets' && options.some((o) => o.state !== 'does_not_meet')) {
    throw new Error(`${what}:none-meets-with-an-option-in-another-state`)
  }
  if (!Array.isArray(item.tied) || !item.tied.every((t) => oneOf(t, ids))) {
    throw new Error(`${what}:tied-not-options`)
  }
  if (item.tied.length > 0 && item.answer !== 'not_resolved') {
    throw new Error(`${what}:tied-when-the-answer-is-resolved`)
  }
  if (!Array.isArray(item.sources)) {
    throw new Error(`${what}:sources-not-a-list`)
  }
  const sources = item.sources.map((entry, index) => {
    const source = record(entry, `${what}:sources[${index}]`)
    if (!isNonEmptyString(source.id)) {
      throw new Error(`${what}:sources[${index}]:id-empty`)
    }
    return { id: source.id, detail: isNonEmptyString(source.detail) ? source.detail : null }
  })
  return {
    example_data: item.example_data,
    strictness,
    margin_of: questions.margin_of,
    answer: item.answer,
    chosen: isChosen ? String(item.chosen) : null,
    missing: hasReason ? missingPart(item.reason, item.detail, what) : null,
    tied: [...item.tied],
    options,
    limit_cost: limitCost(item.limit_cost, `${what}:limit-cost`),
    tipping_price: tippingPrice(item.tipping_price, `${what}:tipping-price`),
    sources,
  }
}

/**
 * Parse the set of example answers: one answer per combination of strictness
 * and margin_of, no combination twice. An answer to example data is example
 * data.
 */
export function parsePlantAnswers(value: unknown): PlantAnswerSet {
  const what = 'invalid-plant-answers'
  const item = record(value, what)
  if (typeof item.example_data !== 'boolean') {
    throw new Error(`${what}:example-data-not-a-flag`)
  }
  if (!Array.isArray(item.answers) || item.answers.length === 0) {
    throw new Error(`${what}:answers-not-a-list`)
  }
  const answers = item.answers.map((entry, index) =>
    parsePlantAnswer(entry, `${what}:answers[${index}]`),
  )
  const seen = new Set<string>()
  for (const answer of answers) {
    const key = `${answer.strictness}:${answer.margin_of}`
    if (seen.has(key)) {
      throw new Error(`${what}:two-answers-to-the-same-questions`)
    }
    seen.add(key)
    if (item.example_data && !answer.example_data) {
      throw new Error(`${what}:answer-not-example-data`)
    }
  }
  return { example_data: item.example_data, answers }
}

/** The answer to these two questions, or null when the set holds none. */
export function selectAnswer(
  set: PlantAnswerSet,
  strictness: Strictness,
  marginOf: MarginOf,
): PlantAnswer | null {
  return (
    set.answers.find((a) => a.strictness === strictness && a.margin_of === marginOf) ?? null
  )
}

/**
 * What the answer says at a soybean price looked at: today's answer, the
 * answer just past a tipping point (as the tipping price function computed
 * it), or unknown with its reason. Never computed here, never extrapolated:
 * a price on the far side of a tipping point gets that point's answer_after
 * only, and a direction whose tipping point is missing for another reason
 * than NOT_APPLICABLE ("no price in this range changes the answer") is
 * unknown.
 */
export type AnswerAtPrice =
  | { kind: 'today' }
  | { kind: 'same'; point: TippingPoint }
  | { kind: 'past'; point: Extract<TippingPoint, { price: number }> }
  | { kind: 'unknown'; missing: MissingPart }

export function answerAtPrice(tipping: TippingPrice, price: number): AnswerAtPrice {
  if (tipping.missing !== null) {
    return { kind: 'unknown', missing: tipping.missing }
  }
  if (tipping.today === null) {
    // The parser refuses this without a shared reason; kept for the type.
    throw new Error('invalid-plant-answer:tipping-price:today-missing-without-a-reason')
  }
  if (price === tipping.today) {
    return { kind: 'today' }
  }
  const point = price > tipping.today ? tipping.up : tipping.down
  if (point.price === null) {
    return point.missing.reason === 'NOT_APPLICABLE'
      ? { kind: 'same', point }
      : { kind: 'unknown', missing: point.missing }
  }
  const beyond = point.direction === 'up' ? price > point.price : price < point.price
  return beyond ? { kind: 'past', point } : { kind: 'same', point }
}

/** The example answers of the screen. */
export const plantExamples: PlantAnswerSet = parsePlantAnswers(rawPlantAnswers)
