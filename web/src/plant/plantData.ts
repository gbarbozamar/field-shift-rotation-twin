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
 * meets" while an option is in another state, an option whose state is not
 * the verdict of its limit check, a chosen option that does not meet the
 * limit, a limit check that is not the check of the strictness used, a limit
 * check that is not resolved without its reason and detail, a missing limit
 * cost without its reason and detail, tied rotations fewer than two or not
 * all in state meets, a costs_nothing that is not a flag, the rules of
 * TippingPointOut (a missing tipping price carries only a reason and its
 * detail; a reason travels with its detail; a present price with its answer
 * after and its distance or the distance's reason) and of TippingPriceOut (a
 * shared reason on both points, today's price inside the range unless a
 * reason is shared, the tipping prices inside the range, up at or above
 * today, down at or below today, the sign of each distance), and a source of
 * an unknown state or unavailable without its missing_reason. Pure: value in, typed answer out, or an Error with a technical
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
  sources: PlantSource[]
}

/**
 * PROPOSED (S-031): 'transcribed' is the state of a record transcribed into
 * the repository from its published source (the ONI record), a state of the
 * plant contract's SourceOut only.
 */
export type SourceState = 'fresh' | 'cached' | 'unavailable' | 'example' | 'transcribed'
const SOURCE_STATES: readonly SourceState[] = ['fresh', 'cached', 'unavailable', 'example', 'transcribed']

/** One source of the answer, the parts of SourceOut the screen renders. */
export interface PlantSource {
  id: string
  state: SourceState
  attribution: string | null
  /** Set exactly when the state is unavailable (SourceOut requires it then). */
  missing_reason: ReasonCode | null
  detail: string | null
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

/**
 * A reason code and its optional detail, from the reason and detail fields.
 * Exported for the rain-stress factor of a request (plantRoute.ts, fix round
 * 1 of S-021).
 */
export function missingPart(reason: unknown, detail: unknown, what: string): MissingPart {
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
  // As LimitCheckOut: a reason and a detail exactly when it is not resolved.
  const unresolved = item.verdict === 'not_resolved'
  const hasReason = item.reason !== null && item.reason !== undefined
  if (unresolved !== hasReason) {
    throw new Error(`${what}:reason-exactly-when-not-resolved`)
  }
  const hasDetail = item.detail !== null && item.detail !== undefined
  if (unresolved !== hasDetail) {
    throw new Error(`${what}:detail-exactly-when-not-resolved`)
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
  if (
    limit.limit === null &&
    (onAverage.verdict !== 'not_resolved' || everyKind.verdict !== 'not_resolved')
  ) {
    // With no limit no check is resolved, so the check carries the reason.
    throw new Error(`${what}:limit:missing-with-a-resolved-check`)
  }
  const check = limitCheck(item.limit_check, `${what}:limit-check`)
  const ofStrictness = strictness === 'on_average' ? onAverage : everyKind
  // As PlantAnswer: the limit_check is the check of the strictness used,
  // verdict, reason and detail alike.
  if (
    check.verdict !== ofStrictness.verdict ||
    check.missing?.reason !== ofStrictness.missing?.reason ||
    check.missing?.detail !== ofStrictness.missing?.detail
  ) {
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
  // As LimitCostOut: costs_nothing is a boolean.
  if (typeof item.costs_nothing !== 'boolean') {
    throw new Error(`${what}:costs-nothing-not-a-flag`)
  }
  if (item.value !== null) {
    if (!isFiniteNumber(item.value)) {
      throw new Error(`${what}:value-not-a-number`)
    }
    if (!isNonEmptyString(item.against)) {
      throw new Error(`${what}:value-without-against`)
    }
    if (
      (item.reason !== null && item.reason !== undefined) ||
      (item.detail !== null && item.detail !== undefined) ||
      item.costs_nothing !== false
    ) {
      throw new Error(`${what}:value-with-a-reason`)
    }
    if (!isNonEmptyString(item.unit)) {
      throw new Error(`${what}:unit-empty`)
    }
    return { kind: 'value', value: item.value, against: item.against, unit: item.unit }
  }
  if (item.against !== null && item.against !== undefined) {
    // As LimitCostOut: a rotation it is against exactly with a cost value.
    throw new Error(`${what}:against-without-a-value`)
  }
  if (item.costs_nothing === true) {
    if (
      (item.reason !== null && item.reason !== undefined) ||
      (item.detail !== null && item.detail !== undefined)
    ) {
      throw new Error(`${what}:nothing-with-a-reason`)
    }
    return { kind: 'nothing' }
  }
  if (item.reason === null || item.reason === undefined) {
    throw new Error(`${what}:missing-without-a-reason`)
  }
  // As LimitCostOut: a missing cost carries a reason and a detail.
  if (item.detail === null || item.detail === undefined) {
    throw new Error(`${what}:missing-without-a-detail`)
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
  const hasReason = item.reason !== null && item.reason !== undefined
  const hasDetail = item.detail !== null && item.detail !== undefined
  if (item.price === null) {
    if (!hasReason) {
      throw new Error(`${what}:missing-without-a-reason`)
    }
    // As TippingPointOut: a missing tipping price carries only a reason and a detail.
    if (
      (item.takes_over !== null && item.takes_over !== undefined) ||
      (item.answer_after !== null && item.answer_after !== undefined) ||
      (item.distance_percent !== null && item.distance_percent !== undefined)
    ) {
      throw new Error(`${what}:missing-price-with-an-answer`)
    }
    if (!hasDetail) {
      throw new Error(`${what}:reason-without-its-detail`)
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
  } else if (!hasReason) {
    throw new Error(`${what}:missing-distance-without-a-reason`)
  }
  // As TippingPointOut: a reason travels with its detail.
  if (hasReason !== hasDetail) {
    throw new Error(`${what}:reason-without-its-detail`)
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
  // As PriceRange: a price is not negative.
  if (range.low < 0 || range.high < 0) {
    throw new Error(`${what}:price-range-negative`)
  }
  if (!isNonEmptyString(item.unit)) {
    throw new Error(`${what}:unit-empty`)
  }
  if (item.today !== null && !isFiniteNumber(item.today)) {
    throw new Error(`${what}:today-not-a-number`)
  }
  const today = item.today as number | null
  const shared = item.reason !== null && item.reason !== undefined
  // As TippingPriceOut: a reason travels with its detail.
  if (shared !== (item.detail !== null && item.detail !== undefined)) {
    throw new Error(`${what}:reason-without-its-detail`)
  }
  const up = tippingPoint(item.up, `${what}:up`, 'up')
  const down = tippingPoint(item.down, `${what}:down`, 'down')
  const missing = shared ? missingPart(item.reason, item.detail, what) : null
  // The rules of TippingPriceOut, in its order.
  if (missing !== null) {
    // A shared cause: both points missing with it.
    for (const point of [up, down]) {
      if (
        point.price !== null ||
        point.missing.reason !== missing.reason ||
        point.missing.detail !== missing.detail
      ) {
        throw new Error(`${what}:shared-reason-not-on-both-points`)
      }
    }
  } else if (today === null) {
    throw new Error(`${what}:today-missing-without-a-reason`)
  } else if (!(range.low <= today && today <= range.high)) {
    throw new Error(`${what}:today-outside-the-range-without-a-reason`)
  }
  for (const point of [up, down]) {
    if (point.price !== null && !(range.low <= point.price && point.price <= range.high)) {
      throw new Error(`${what}:tipping-price-outside-the-range`)
    }
  }
  if (today !== null) {
    if (up.price !== null && up.price < today) {
      throw new Error(`${what}:up-price-below-today`)
    }
    if (down.price !== null && down.price > today) {
      throw new Error(`${what}:down-price-above-today`)
    }
  }
  const upDistance = up.price !== null ? up.distance_percent : null
  const downDistance = down.price !== null ? down.distance_percent : null
  if ((upDistance !== null && upDistance < 0) || (downDistance !== null && downDistance > 0)) {
    throw new Error(`${what}:distance-of-the-wrong-sign`)
  }
  return {
    today,
    unit: item.unit,
    low: range.low,
    high: range.high,
    up,
    down,
    missing,
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
  // As PlantAnswer: the reason travels with its detail.
  if (isChosen === (item.detail !== null && item.detail !== undefined)) {
    throw new Error(`${what}:detail-exactly-when-nothing-is-chosen`)
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
  // As PlantAnswer: exactly one option in state chosen when the answer is
  // chosen, and it is the chosen rotation; none otherwise.
  const inStateChosen = options.filter((o) => o.state === 'chosen')
  const chosenStateWrong = isChosen
    ? inStateChosen.length !== 1 || inStateChosen[0].rotation_id !== item.chosen
    : inStateChosen.length !== 0
  if (chosenStateWrong) {
    throw new Error(`${what}:state-chosen-not-on-the-chosen-rotation`)
  }
  if (item.answer === 'none_meets' && options.some((o) => o.state !== 'does_not_meet')) {
    throw new Error(`${what}:none-meets-with-an-option-in-another-state`)
  }
  // As PlantAnswer: the chosen rotation meets the limit, and the state of
  // every other option is the verdict of its limit check.
  for (const [index, o] of options.entries()) {
    if (o.state === 'chosen') {
      if (o.limit_check.verdict !== 'meets') {
        throw new Error(`${what}:options[${index}]:chosen-does-not-meet-the-limit`)
      }
    } else if (o.state !== o.limit_check.verdict) {
      throw new Error(`${what}:options[${index}]:state-not-the-verdict-of-its-check`)
    }
  }
  if (!Array.isArray(item.tied) || !item.tied.every((t) => oneOf(t, ids))) {
    throw new Error(`${what}:tied-not-options`)
  }
  if (new Set(item.tied).size !== item.tied.length) {
    throw new Error(`${what}:tied-not-distinct`)
  }
  if (item.tied.length > 0 && item.answer !== 'not_resolved') {
    throw new Error(`${what}:tied-when-the-answer-is-resolved`)
  }
  // As choose_rotation: tied rotations are at least two, each in state meets.
  if (item.tied.length === 1) {
    throw new Error(`${what}:tied-fewer-than-two`)
  }
  const stateOf = new Map(options.map((o) => [o.rotation_id, o.state]))
  if (item.tied.some((t) => stateOf.get(t) !== 'meets')) {
    throw new Error(`${what}:tied-not-in-state-meets`)
  }
  if (!Array.isArray(item.sources)) {
    throw new Error(`${what}:sources-not-a-list`)
  }
  const sources = item.sources.map((entry, index) => {
    const source = record(entry, `${what}:sources[${index}]`)
    const at = `${what}:sources[${index}]`
    if (!isNonEmptyString(source.id)) {
      throw new Error(`${at}:id-empty`)
    }
    if (!oneOf(source.state, SOURCE_STATES)) {
      throw new Error(`${at}:state-not-in-the-list`)
    }
    if (source.attribution !== null && typeof source.attribution !== 'string') {
      throw new Error(`${at}:attribution-not-a-text`)
    }
    if (source.missing_reason !== null && !oneOf(source.missing_reason, REASON_CODES)) {
      throw new Error(`${at}:missing-reason-not-a-code`)
    }
    // As SourceOut: an unavailable source carries its missing_reason.
    if (source.state === 'unavailable' && source.missing_reason === null) {
      throw new Error(`${at}:unavailable-without-a-reason`)
    }
    if (source.detail !== null && typeof source.detail !== 'string') {
      throw new Error(`${at}:detail-not-a-text`)
    }
    const plantSource: PlantSource = {
      id: source.id,
      state: source.state,
      attribution: isNonEmptyString(source.attribution) ? source.attribution : null,
      missing_reason: source.missing_reason as ReasonCode | null,
      detail: isNonEmptyString(source.detail) ? source.detail : null,
    }
    return plantSource
  })
  const cost = limitCost(item.limit_cost, `${what}:limit-cost`)
  // As PlantAnswer: a cost only when a rotation is chosen, against another option.
  if (!isChosen && cost.kind !== 'missing') {
    throw new Error(`${what}:limit-cost:cost-when-nothing-is-chosen`)
  }
  if (cost.kind === 'value' && (!ids.includes(cost.against) || cost.against === item.chosen)) {
    throw new Error(`${what}:limit-cost:against-not-another-option`)
  }
  return {
    example_data: item.example_data,
    strictness,
    margin_of: questions.margin_of,
    answer: item.answer,
    chosen: isChosen ? String(item.chosen) : null,
    missing: hasReason ? missingPart(item.reason, item.detail, what) : null,
    tied: [...item.tied],
    options,
    limit_cost: cost,
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
 * The soybean price the slider starts at for an answer: its price of today,
 * kept inside its price range; null when the answer has no price of today
 * (or there is no answer). The parser already refuses a price of today
 * outside the range without a shared reason; the clamp keeps the slider
 * inside the range in every case.
 */
export function startPrice(answer: PlantAnswer | null): number | null {
  const tipping = answer?.tipping_price ?? null
  if (tipping === null || tipping.today === null) {
    return null
  }
  return Math.min(Math.max(tipping.today, tipping.low), tipping.high)
}

/** The questions asked on the screen. */
export interface PlantQuestions {
  strictness: Strictness
  marginOf: MarginOf
  price: number | null
}

/**
 * The questions after the user selects how strict and the kind of year:
 * another answer is selected, so the price looked at goes back to that
 * answer's price of today (inside its range). A price moved on one answer is
 * never carried to another.
 */
export function selectQuestions(
  set: PlantAnswerSet,
  strictness: Strictness,
  marginOf: MarginOf,
): PlantQuestions {
  return { strictness, marginOf, price: startPrice(selectAnswer(set, strictness, marginOf)) }
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

/**
 * The rain-stress part of one answer (S-021, PROPOSED): the applied form
 * (RainStressApplied: the declared factor, its unit, the detail, the label
 * and whether it was applied) or the missing form (RainStressMissingOut: the
 * reason, the detail, the label); null when no factor was asked.
 *
 * Read for the answer of one service request only (plantRoute.ts); the
 * example set does not read it, so parsePlantAnswer is unchanged. Pure:
 * value in, typed part out, or an Error with a technical code.
 */
export type RainStressPart =
  | { kind: 'applied'; factor: number; unit: string; detail: string; label: string; applied: boolean }
  | { kind: 'missing'; missing: MissingPart; detail: string; label: string }

export function parseRainStress(value: unknown, what = 'invalid-rain-stress'): RainStressPart | null {
  if (value === null) {
    return null
  }
  const item = record(value, what)
  if (!isNonEmptyString(item.detail)) {
    throw new Error(`${what}:detail-empty`)
  }
  if (!isNonEmptyString(item.label)) {
    throw new Error(`${what}:label-empty`)
  }
  if (item.missing !== undefined) {
    const missing = record(item.missing, `${what}:missing`)
    return {
      kind: 'missing',
      missing: missingPart(missing.reason, missing.detail, `${what}:missing`),
      detail: item.detail,
      label: item.label,
    }
  }
  if (!isFiniteNumber(item.factor)) {
    throw new Error(`${what}:factor-not-a-number`)
  }
  if (typeof item.applied !== 'boolean') {
    throw new Error(`${what}:applied-not-a-flag`)
  }
  const declared = record(item.declared, `${what}:declared`)
  // As RainStressApplied: the factor is the declared value.
  if (declared.value !== item.factor) {
    throw new Error(`${what}:factor-not-the-declared-value`)
  }
  if (!isNonEmptyString(declared.unit)) {
    throw new Error(`${what}:declared:unit-empty`)
  }
  return {
    kind: 'applied',
    factor: item.factor,
    unit: declared.unit,
    detail: item.detail,
    label: item.label,
    applied: item.applied,
  }
}

/** The example answers of the screen. */
export const plantExamples: PlantAnswerSet = parsePlantAnswers(rawPlantAnswers)
