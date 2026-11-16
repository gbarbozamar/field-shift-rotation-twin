import type {
  MissingPart,
  ProvenanceLabel,
  ReasonCode,
  UncertaintyRange,
  ValueItem,
} from '../components/ValueDisplay'

/**
 * The pure parser of the platform route's success envelope (api/rotations.py,
 * RunRotationResponse). A 2xx answer always carries the envelope, also when
 * nothing could be computed: the result then travels as null with
 * result_missing, and every value inside the result travels as a value item
 * of the results contract, a number with its provenance, source and range,
 * or null with a missing part and its reason code (C3.1, C3.2), never zero.
 *
 * The parser copies what the interface renders into a view: the outcome, the
 * live-data flag (the climate source of the run answered fresh or cached),
 * one row per indicator item, including a wholly missing part, which keeps
 * its units and its reason (decision D12), and the reason a result is absent
 * altogether. Everything else (calendar, modules, sources beyond the flag) is
 * left unread: the route guarantees its shape, and the seam renders no more
 * than the goal asks.
 *
 * Pure: envelope in, view out, or an Error naming what is wrong. The errors
 * are technical codes without wording; nothing user-visible lives here.
 */

export type RunOutcome = 'complete' | 'partial' | 'no_result'

/** One indicator item of the result, ready for the shared value display. */
export interface IndicatorRow {
  /** Data-derived label: the indicator id and its position (year, model). */
  what: string
  item: ValueItem
}

/** One part of the result: the indicator id and its items (or its absences). */
export interface IndicatorPart {
  indicator: string
  rows: IndicatorRow[]
}

/** The envelope, reduced to what the seam renders. */
export interface RunRotationView {
  outcome: RunOutcome
  /** True when the climate source of the run answered fresh or cached data. */
  liveData: boolean
  parts: IndicatorPart[]
  /** Set exactly when the run produced no result at all. */
  resultMissing: MissingPart | null
}

// --- small guards (the same rules as the other parsers of the interface) ------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
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

const PROVENANCE_LABELS: readonly ProvenanceLabel[] = [
  'DECLARED',
  'OBSERVED',
  'DERIVED',
  'SIMULATED',
]

function isReasonCode(value: unknown): value is ReasonCode {
  return typeof value === 'string' && (REASON_CODES as readonly string[]).includes(value)
}

function isProvenanceLabel(value: unknown): value is ProvenanceLabel {
  return (
    typeof value === 'string' && (PROVENANCE_LABELS as readonly string[]).includes(value)
  )
}

function parseMissing(value: unknown, what: string): MissingPart {
  if (!isRecord(value)) {
    throw new Error(`${what}:missing-not-an-object`)
  }
  if (!isReasonCode(value.reason)) {
    throw new Error(`${what}:reason-not-a-code`)
  }
  const missing: MissingPart = { reason: value.reason }
  // The route keeps pydantic's nulls (no exclude_none), so an absent detail
  // also travels as null: both are an absent detail, never an invented one.
  if (value.detail !== undefined && value.detail !== null) {
    if (typeof value.detail !== 'string' || value.detail.length === 0) {
      throw new Error(`${what}:detail-empty`)
    }
    missing.detail = value.detail
  }
  return missing
}

function parseRange(value: unknown, what: string): UncertaintyRange {
  if (!isRecord(value)) {
    throw new Error(`${what}:range-not-an-object`)
  }
  if (!isFiniteNumber(value.low) || !isFiniteNumber(value.high)) {
    throw new Error(`${what}:range-bounds-not-finite`)
  }
  if (value.low > value.high) {
    throw new Error(`${what}:range-low-above-high`)
  }
  if (typeof value.kind !== 'string' || value.kind.length === 0) {
    throw new Error(`${what}:range-kind-empty`)
  }
  return { low: value.low, high: value.high, kind: value.kind }
}

// --- one indicator item (C3.1, C4.1, C4.2, C2.1, C2.2) ------------------------

/**
 * Parse one indicator item of the results contract into a value item of the
 * shared display: a number with its unit, provenance, source or assumption
 * mark and its range or range reason, or null with a missing part, keeping
 * the unit so the display names what is missing. Every rule enforced here is
 * a rule the contract itself enforces.
 */
function parseIndicatorItem(raw: unknown, what: string): ValueItem {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  // The route serializes the contract with pydantic's defaults as explicit
  // nulls (model_dump without exclude_none): a null here means the field was
  // never set, the contract has no null shape for these fields, so a null
  // is normalized away before the key-presence checks below.
  const value: Record<string, unknown> = { ...raw }
  for (const key of ['missing', 'range', 'range_missing', 'provenance', 'source']) {
    if (value[key] === null) {
      delete value[key]
    }
  }
  if (typeof value.unit !== 'string' || value.unit.length === 0) {
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
  const source =
    value.source === undefined
      ? undefined
      : typeof value.source === 'string' && value.source.length > 0
        ? value.source
        : undefined
  if (source === undefined && value.assumption !== true) {
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
    assumption: value.assumption === true ? true : undefined,
    range,
    range_missing: rangeMissing,
  }
}

// --- the parts of the result ---------------------------------------------------

/** The calendar position of a monthly item, as the site sheet labels months. */
function monthPosition(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

/** The display label of an item: its indicator id and its position in it. */
function whatOf(indicator: string, position: string): string {
  return position.length === 0 ? indicator : `${indicator} ${position}`
}

/**
 * Parse one indicator item with its calendar position: an annual value of
 * soil loss carries its agricultural year, a monthly one its calendar month.
 */
function parsePositionedItem(
  value: unknown,
  indicator: string,
  position: string,
  what: string,
): IndicatorRow {
  return { what: whatOf(indicator, position), item: parseIndicatorItem(value, what) }
}

function parseInteger(value: unknown, what: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    throw new Error(`${what}:not-an-integer`)
  }
  return value
}

/** Soil loss: annual items then monthly items, each with its position. */
function parseSoilLoss(value: unknown): IndicatorPart {
  if (!isRecord(value)) {
    throw new Error('invalid-result:soil-loss-not-an-object')
  }
  const rows: IndicatorRow[] = []
  const annual = value.annual
  if (!Array.isArray(annual) || annual.length === 0) {
    throw new Error('invalid-result:soil-loss-annual-not-a-list')
  }
  for (const [index, item] of annual.entries()) {
    const agYear = parseInteger(
      isRecord(item) ? item.ag_year : undefined,
      `invalid-soil-loss:annual[${index}]:ag-year`,
    )
    rows.push(
      parsePositionedItem(item, 'soil_loss', String(agYear), `invalid-soil-loss:annual[${index}]`),
    )
  }
  const monthly = value.monthly
  if (!Array.isArray(monthly)) {
    throw new Error('invalid-result:soil-loss-monthly-not-a-list')
  }
  for (const [index, item] of monthly.entries()) {
    const what = `invalid-soil-loss:monthly[${index}]`
    if (!isRecord(item)) {
      throw new Error(`${what}:not-an-object`)
    }
    const year = parseInteger(item.year, `${what}:year`)
    const month = parseInteger(item.month, `${what}:month`)
    if (month < 1 || month > 12) {
      throw new Error(`${what}:month-not-in-1-to-12`)
    }
    rows.push(parsePositionedItem(item, 'soil_loss', monthPosition(year, month), what))
  }
  return { indicator: 'soil_loss', rows }
}

/**
 * Parse a part that is a list of items in its present form: water-deficit
 * exposure (its position is the agricultural year on the ag_year basis) and
 * soil carbon trend (its position is the carbon model and the computation).
 */
function parseListPart(
  value: unknown,
  indicator: string,
  positionOf: (item: Record<string, unknown>, what: string) => string,
): IndicatorPart {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`invalid-result:${indicator}-not-a-list`)
  }
  const rows: IndicatorRow[] = []
  for (const [index, item] of value.entries()) {
    const what = `invalid-${indicator}[${index}]`
    if (!isRecord(item)) {
      throw new Error(`${what}:not-an-object`)
    }
    rows.push(parsePositionedItem(item, indicator, positionOf(item, what), what))
  }
  return { indicator, rows }
}

function waterPosition(item: Record<string, unknown>, what: string): string {
  if (item.ag_year === undefined || item.ag_year === null) return ''
  return String(parseInteger(item.ag_year, `${what}:ag-year`))
}

function carbonPosition(item: Record<string, unknown>, what: string): string {
  const model = item.carbon_model
  const computation = item.computation
  if (typeof model !== 'string' || model.length === 0) {
    throw new Error(`${what}:carbon-model-empty`)
  }
  if (typeof computation !== 'string' || computation.length === 0) {
    throw new Error(`${what}:computation-empty`)
  }
  return `${model} ${computation}`
}

/**
 * A part whose engine is not built (decision D12): the indicator id, its
 * direction and every unit it carries, and one missing part for them all.
 * Each unit keeps its missing item: a part that is wholly missing is shown
 * in every unit it would have carried, never as an invented blank.
 */
function parseNotBuiltPart(value: unknown, what: string): IndicatorPart {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (typeof value.indicator !== 'string' || value.indicator.length === 0) {
    throw new Error(`${what}:indicator-empty`)
  }
  if (!Array.isArray(value.units) || value.units.length === 0) {
    throw new Error(`${what}:units-not-a-list`)
  }
  const missing = parseMissing(value.missing, what)
  const rows: IndicatorRow[] = []
  for (const [index, unit] of value.units.entries()) {
    if (typeof unit !== 'string' || unit.length === 0) {
      throw new Error(`${what}:unit[${index}]-empty`)
    }
    rows.push({ what: value.indicator, item: { value: null, unit, missing } })
  }
  return { indicator: value.indicator, rows }
}

/** A part of the result is wholly missing when it is one object, not a list. */
function isNotBuilt(value: unknown): boolean {
  return isRecord(value) && !Array.isArray(value)
}

function parseSoilLossPart(value: unknown): IndicatorPart {
  // The wholly missing form of soil loss is told apart by its missing part.
  if (isRecord(value) && value.missing !== undefined) {
    return parseNotBuiltPart(value, 'invalid-soil-loss:not-built')
  }
  return parseSoilLoss(value)
}

function parseListPartOrNotBuilt(
  value: unknown,
  indicator: string,
  positionOf: (item: Record<string, unknown>, what: string) => string,
): IndicatorPart {
  if (isNotBuilt(value)) {
    return parseNotBuiltPart(value, `invalid-${indicator}:not-built`)
  }
  return parseListPart(value, indicator, positionOf)
}

// --- the envelope ----------------------------------------------------------------

/**
 * The live-data flag: the run used real data when its climate source, the
 * NASA POWER source behind the platform route, answered fresh or cached
 * data (adapters/ports.py). An unavailable or example climate source leaves
 * the flag off: the live-data label then does not show, whatever the values.
 * Exported for the decision route, whose envelope carries the same sources
 * list (issue #354).
 */
export function parseLiveData(value: unknown): boolean {
  if (!Array.isArray(value)) {
    throw new Error('invalid-envelope:sources-not-a-list')
  }
  return value.some(
    (source) =>
      isRecord(source) &&
      source.contract === 'site_data_climate' &&
      (source.state === 'fresh' || source.state === 'cached'),
  )
}

function parseOutcome(value: unknown): RunOutcome {
  if (value === 'complete' || value === 'partial' || value === 'no_result') {
    return value
  }
  throw new Error('invalid-envelope:outcome-not-a-known-value')
}

/** Parse the success envelope of the platform route into the seam's view. */
export function parseRunRotation(value: unknown): RunRotationView {
  if (!isRecord(value)) {
    throw new Error('invalid-envelope:not-an-object')
  }
  const outcome = parseOutcome(value.outcome)
  const liveData = parseLiveData(value.sources)
  const result = value.result
  if (result === null) {
    if (value.result_missing === undefined) {
      throw new Error('invalid-envelope:result-missing-absent')
    }
    return {
      outcome,
      liveData,
      parts: [],
      resultMissing: parseMissing(value.result_missing, 'invalid-envelope:result-missing'),
    }
  }
  if (!isRecord(result)) {
    throw new Error('invalid-envelope:result-not-an-object')
  }
  if (value.result_missing !== null && value.result_missing !== undefined) {
    throw new Error('invalid-envelope:result-and-result-missing')
  }
  return {
    outcome,
    liveData,
    parts: [
      parseSoilLossPart(result.soil_loss),
      parseListPartOrNotBuilt(result.water_deficit_exposure, 'water_deficit_exposure', waterPosition),
      parseListPartOrNotBuilt(result.soil_carbon_trend, 'soil_carbon_trend', carbonPosition),
    ],
    resultMissing: null,
  }
}
