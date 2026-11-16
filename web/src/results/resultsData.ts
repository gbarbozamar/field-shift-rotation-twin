import rawPerRotation from '../data/PLACEHOLDER_results_per_rotation.json'
import rawPerRotationNotBuilt from '../data/PLACEHOLDER_results_per_rotation_not_built.json'
import type {
  MissingPart,
  ProvenanceLabel,
  ReasonCode,
  UncertaintyRange,
  ValueItem,
} from '../components/ValueDisplay'

/**
 * The results of the result cards: the two contract examples of results per
 * rotation, copied unchanged from contracts/results/examples/ into
 * web/src/data/ (issue #141). Their values are placeholders, written by hand;
 * no engine produced them. The second document is the form of D12: every part
 * wholly missing with NOT_AVAILABLE, because no engine is built.
 *
 * The parser below reads exactly the parts the cards render and enforces, on
 * those parts, the rules of the contract that the value display relies on:
 *
 * - an item holds a value or a missing part with its reason, never both,
 *   never neither (C3.1); zero is a real value, never a stand-in;
 * - a value that is not missing carries a provenance label and a source or
 *   the assumption mark (C4.1, C4.2); a missing one carries neither;
 * - a value holds a range or the reason it has none, never both (C2.2);
 * - a carbon value names its carbon model (amg or rothc, D1 of #77) and
 *   one of the three computations of C1.6, and stays one item of its own:
 *   nothing here merges or averages across models (C1.5);
 * - a wholly missing part (D12) carries only its indicator, its units and a
 *   missing part whose reason is NOT_AVAILABLE, no other code.
 *
 * Pure: value in, typed results out, or an Error naming what is wrong. The
 * errors are technical codes without wording; nothing user-visible lives
 * here. The whole-document checks of the contract (twelve consecutive months
 * per agricultural year, the three computations once per carbon model, one
 * water time basis per document) stay the contract's business; the cards
 * render whatever items travel, each through the shared value display.
 */

/** The three indicator identifiers of the conventions (C1.1). */
export type IndicatorId = 'soil_loss' | 'water_deficit_exposure' | 'soil_carbon_trend'

/** The two carbon models (D1 of #77). */
export type CarbonModelId = 'amg' | 'rothc'

/** The three trend computations of C1.6, in their order. */
export type TrendComputation = 'end_minus_start' | 'fitted_slope' | 'mean_over_cycles'

/** The two time bases a water-deficit-exposure value can carry (C1.3). */
export type WaterTimeBasis = 'rotation' | 'ag_year'

/** One annual soil-loss value: the agricultural year it belongs to (C5.3). */
export interface AnnualSoilLoss {
  ag_year: number
  item: ValueItem
}

/** One monthly soil-loss value: its calendar position (C5.1) and its year. */
export interface MonthlySoilLoss {
  year: number
  month: number // C5.1: January is 1 and December is 12
  ag_year: number
  item: ValueItem
}

/** One water-deficit-exposure value: its time basis, and its year when per year. */
export interface WaterValue {
  time_basis: WaterTimeBasis
  ag_year?: number
  item: ValueItem
}

/** One soil-carbon-trend value: one carbon model under one computation (C1.5). */
export interface CarbonValue {
  carbon_model: CarbonModelId
  computation: TrendComputation
  item: ValueItem
}

/** The wholly missing form of a part (D12): its units and its missing part. */
export interface PartWhollyMissing {
  form: 'not_built'
  indicator: IndicatorId
  units: string[]
  missing: MissingPart
}

/** The present form of the soil-loss part: annual values and their monthly breakdown. */
export interface SoilLossPresent {
  form: 'present'
  indicator: IndicatorId
  annual: AnnualSoilLoss[]
  monthly: MonthlySoilLoss[]
}

/** The present form of the water and carbon parts: their value lists. */
export interface ValueListPresent<Kind extends 'water' | 'carbon'> {
  form: 'present'
  indicator: IndicatorId
  values: Kind extends 'water' ? WaterValue[] : CarbonValue[]
}

export type SoilLossPart = SoilLossPresent | PartWhollyMissing
export type WaterPart = ValueListPresent<'water'> | PartWhollyMissing
export type CarbonPart = ValueListPresent<'carbon'> | PartWhollyMissing

/** One results-per-rotation document, reduced to the parts the cards render. */
export interface ResultsPerRotation {
  case_id: string
  field_id: string
  rotation_id: string
  soil_loss: SoilLossPart
  water_deficit_exposure: WaterPart
  soil_carbon_trend: CarbonPart
}

// --- small guards -------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
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

const INDICATOR_IDS: readonly IndicatorId[] = [
  'soil_loss',
  'water_deficit_exposure',
  'soil_carbon_trend',
]

const CARBON_MODELS: readonly CarbonModelId[] = ['amg', 'rothc']

const TREND_COMPUTATIONS: readonly TrendComputation[] = [
  'end_minus_start',
  'fitted_slope',
  'mean_over_cycles',
]

function oneOf<T extends string>(value: unknown, list: readonly T[]): value is T {
  return typeof value === 'string' && (list as readonly string[]).includes(value)
}

function isReasonCode(value: unknown): value is ReasonCode {
  return oneOf(value, REASON_CODES)
}

function isProvenanceLabel(value: unknown): value is ProvenanceLabel {
  return oneOf(value, PROVENANCE_LABELS)
}

// --- the missing part (C3.1, C3.2) ----------------------------------------------

function parseMissing(value: unknown, what: string): MissingPart {
  if (!isRecord(value)) {
    throw new Error(`${what}:missing-not-an-object`)
  }
  if (!isReasonCode(value.reason)) {
    throw new Error(`${what}:reason-not-a-code`)
  }
  const missing: MissingPart = { reason: value.reason }
  // The route keeps pydantic's nulls (no exclude_none): a null detail is an absent one.
  if (value.detail !== undefined && value.detail !== null) {
    if (!isNonEmptyString(value.detail)) {
      throw new Error(`${what}:detail-empty`)
    }
    missing.detail = value.detail
  }
  return missing
}

// --- the uncertainty range (C2.1) ------------------------------------------------

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
  if (!isNonEmptyString(value.kind)) {
    throw new Error(`${what}:range-kind-empty`)
  }
  return { low: value.low, high: value.high, kind: value.kind }
}

// --- one indicator value -----------------------------------------------------------

/**
 * Parse one IndicatorValue of the results contract: a number with its unit,
 * its provenance label, its source or assumption mark and its range or range
 * reason, or null with a missing part, keeping its unit (C3.1). Every rule
 * enforced here is a rule the contract itself enforces; the example files
 * satisfy all of them.
 */
function parseValueItem(raw: unknown, what: string): ValueItem {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  // The live route serializes the contract with pydantic's defaults as
  // explicit nulls (model_dump without exclude_none): a null here means the
  // field was never set, so it is read as absent before the checks below.
  const value: Record<string, unknown> = { ...raw }
  for (const key of ['missing', 'range', 'range_missing', 'provenance', 'source']) {
    if (value[key] === null) {
      delete value[key]
    }
  }
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

/** The indicator a part's items name, checked against the part that holds them. */
function partIndicator(value: unknown, expected: IndicatorId, what: string): IndicatorId {
  if (!oneOf(value, INDICATOR_IDS)) {
    throw new Error(`${what}:indicator-not-an-id`)
  }
  if (value !== expected) {
    throw new Error(`${what}:indicator-of-another-part`)
  }
  return value
}

/** The indicator the first item of a part's list names, for the whole part. */
function firstItemIndicator(
  list: unknown[],
  expected: IndicatorId,
  what: string,
): IndicatorId {
  const first = list[0]
  if (!isRecord(first)) {
    throw new Error(`${what}:values-not-objects`)
  }
  return partIndicator(first.indicator, expected, what)
}

// --- the soil-loss part -------------------------------------------------------------

function parseAnnual(value: unknown, what: string): AnnualSoilLoss {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (typeof value.ag_year !== 'number' || !Number.isInteger(value.ag_year)) {
    throw new Error(`${what}:ag-year-not-an-integer`)
  }
  return { ag_year: value.ag_year, item: parseValueItem(value, `${what}:ag_year[${value.ag_year}]`) }
}

function parseMonthly(value: unknown, what: string): MonthlySoilLoss {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (typeof value.year !== 'number' || !Number.isInteger(value.year)) {
    throw new Error(`${what}:year-not-an-integer`)
  }
  if (
    typeof value.month !== 'number' ||
    !Number.isInteger(value.month) ||
    value.month < 1 ||
    value.month > 12
  ) {
    throw new Error(`${what}:month-not-in-1-to-12`)
  }
  if (typeof value.ag_year !== 'number' || !Number.isInteger(value.ag_year)) {
    throw new Error(`${what}:ag-year-not-an-integer`)
  }
  const label = `${value.year}-${String(value.month).padStart(2, '0')}`
  return {
    year: value.year,
    month: value.month,
    ag_year: value.ag_year,
    item: parseValueItem(value, `${what}:month[${label}]`),
  }
}

/**
 * The soil-loss part: an object in both forms. An object with a missing part
 * is the wholly missing form (D12); the present form has none.
 */
function parseSoilLoss(value: unknown): SoilLossPart {
  if (!isRecord(value)) {
    throw new Error('invalid-results:soil-loss-not-an-object')
  }
  if (value.missing !== undefined) {
    return parseWhollyMissing(value, 'soil_loss', 'invalid-results:soil-loss')
  }
  if (!Array.isArray(value.annual) || value.annual.length === 0) {
    throw new Error('invalid-results:soil-loss-annual-not-a-list')
  }
  if (!Array.isArray(value.monthly)) {
    throw new Error('invalid-results:soil-loss-monthly-not-a-list')
  }
  return {
    form: 'present',
    indicator: firstItemIndicator(value.annual, 'soil_loss', 'invalid-results:soil-loss'),
    annual: value.annual.map((entry, index) => parseAnnual(entry, `invalid-results:soil-loss:annual[${index}]`)),
    monthly: value.monthly.map((entry, index) => parseMonthly(entry, `invalid-results:soil-loss:monthly[${index}]`)),
  }
}

// --- the water-deficit-exposure part -------------------------------------------------

function parseWaterValue(value: unknown, what: string): WaterValue {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (value.time_basis !== 'rotation' && value.time_basis !== 'ag_year') {
    throw new Error(`${what}:time-basis-not-in-list`)
  }
  if (value.time_basis === 'ag_year') {
    if (typeof value.ag_year !== 'number' || !Number.isInteger(value.ag_year)) {
      throw new Error(`${what}:ag-year-not-an-integer`)
    }
    return { time_basis: value.time_basis, ag_year: value.ag_year, item: parseValueItem(value, what) }
  }
  if (value.ag_year !== undefined && value.ag_year !== null) {
    throw new Error(`${what}:ag-year-with-rotation-basis`)
  }
  return { time_basis: value.time_basis, item: parseValueItem(value, what) }
}

/** The water part: a list in the present form, an object when wholly missing (D12). */
function parseWater(value: unknown): WaterPart {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      throw new Error('invalid-results:water-not-a-list')
    }
    return {
      form: 'present',
      indicator: firstItemIndicator(value, 'water_deficit_exposure', 'invalid-results:water'),
      values: value.map((entry, index) =>
        parseWaterValue(entry, `invalid-results:water:value[${index}]`),
      ),
    }
  }
  if (isRecord(value)) {
    return parseWhollyMissing(value, 'water_deficit_exposure', 'invalid-results:water')
  }
  throw new Error('invalid-results:water-not-a-list')
}

// --- the soil-carbon-trend part --------------------------------------------------------

function parseCarbonValue(value: unknown, what: string): CarbonValue {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (!oneOf(value.carbon_model, CARBON_MODELS)) {
    throw new Error(`${what}:carbon-model-not-in-list`)
  }
  if (!oneOf(value.computation, TREND_COMPUTATIONS)) {
    throw new Error(`${what}:computation-not-in-list`)
  }
  return {
    carbon_model: value.carbon_model,
    computation: value.computation,
    item: parseValueItem(value, `${what}:${value.carbon_model}/${value.computation}`),
  }
}

/** The carbon part: a list in the present form, an object when wholly missing (D12). */
function parseCarbon(value: unknown): CarbonPart {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      throw new Error('invalid-results:carbon-not-a-list')
    }
    return {
      form: 'present',
      indicator: firstItemIndicator(value, 'soil_carbon_trend', 'invalid-results:carbon'),
      values: value.map((entry, index) =>
        parseCarbonValue(entry, `invalid-results:carbon:value[${index}]`),
      ),
    }
  }
  if (isRecord(value)) {
    return parseWhollyMissing(value, 'soil_carbon_trend', 'invalid-results:carbon')
  }
  throw new Error('invalid-results:carbon-not-a-list')
}

// --- a part whose engine is not built (D12) ---------------------------------------------

/**
 * The wholly missing form of a part: its indicator, its direction, its units
 * and a missing part whose reason is NOT_AVAILABLE, the only code D12
 * allows here. No value of any kind travels with it; each would be rejected
 * by the contract, and the parser keeps to the fields the cards render.
 */
function parseWhollyMissing(
  value: Record<string, unknown>,
  expected: IndicatorId,
  what: string,
): PartWhollyMissing {
  const indicator = partIndicator(value.indicator, expected, what)
  if (!Array.isArray(value.units) || value.units.length === 0) {
    throw new Error(`${what}:units-not-a-list`)
  }
  for (const unit of value.units) {
    if (!isNonEmptyString(unit)) {
      throw new Error(`${what}:unit-empty`)
    }
  }
  const missing = parseMissing(value.missing, what)
  if (missing.reason !== 'NOT_AVAILABLE') {
    throw new Error(`${what}:reason-not-not-available`)
  }
  return { form: 'not_built', indicator, units: value.units, missing }
}

// --- one document -------------------------------------------------------------------------

/**
 * Parse and validate one results-per-rotation document. Pure: value in,
 * typed results out, or an Error naming what is wrong.
 */
export function parseResultsPerRotation(value: unknown): ResultsPerRotation {
  if (!isRecord(value)) {
    throw new Error('invalid-results:not-an-object')
  }
  if (!isNonEmptyString(value.case_id)) {
    throw new Error('invalid-results:case-id-empty')
  }
  if (!isNonEmptyString(value.field_id)) {
    throw new Error('invalid-results:field-id-empty')
  }
  if (!isNonEmptyString(value.rotation_id)) {
    throw new Error('invalid-results:rotation-id-empty')
  }
  return {
    case_id: value.case_id,
    field_id: value.field_id,
    rotation_id: value.rotation_id,
    soil_loss: parseSoilLoss(value.soil_loss),
    water_deficit_exposure: parseWater(value.water_deficit_exposure),
    soil_carbon_trend: parseCarbon(value.soil_carbon_trend),
  }
}

/** The results example with its parts in the present form: values, and missing values with their reasons. */
export const resultsPerRotationExample: ResultsPerRotation = parseResultsPerRotation(rawPerRotation)

/** The results example of D12: every part wholly missing with NOT_AVAILABLE, because no engine is built. */
export const resultsPerRotationNotBuiltExample: ResultsPerRotation =
  parseResultsPerRotation(rawPerRotationNotBuilt)

/** The rotations of the results example, in the order the cards show them. */
export const resultsExampleRotations: ResultsPerRotation[] = [
  resultsPerRotationExample,
  resultsPerRotationNotBuiltExample,
]
