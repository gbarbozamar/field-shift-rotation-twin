import rawRotation from '../data/rotation_definition.json'
import type { MissingPart, ProvenanceLabel, ReasonCode } from '../components/ValueDisplay'

/**
 * The rotation of the example field, as the rotation_definition contract
 * travels it (contracts/rotation_definition, example file copied unchanged
 * into web/src/data/rotation_definition.json).
 *
 * The unit is display-only: this module parses and types the file, the ribbon
 * renders it, and nothing here decides whether a rotation is feasible, that
 * belongs to the calendar engine. Values such as crop ids, purposes, residues
 * or methods are identifiers of the contract: they render exactly as they
 * travel and are never translated.
 *
 * Parts that can be absent travel as a missing part with its reason code
 * (C3.1, C3.2), here as everywhere: an absence is named, never left blank.
 */

/** The four provenance labels of the conventions (C4.1). */
const PROVENANCE_LABELS: readonly ProvenanceLabel[] = ['DECLARED', 'OBSERVED', 'DERIVED', 'SIMULATED']

/** The eight reason codes of the conventions (C3.2); a closed list. */
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

/** The start of the agricultural year: a month, with its provenance. */
export interface AgYearStart {
  month: number
  provisional: boolean
  provenance: ProvenanceLabel
  source: string
}

/**
 * A dated event of a component (sowing, harvest): the date with its
 * provenance label and its source, or the reason it is missing (C3.1).
 */
export type DatedPart =
  | { date: string; provenance: ProvenanceLabel; source: string; missing?: undefined }
  | { date: null; missing: MissingPart; provenance?: undefined; source?: undefined }

/** The residue management of a component: a value, or the reason it is missing. */
export type ResiduePart = string | { missing: MissingPart }

/** The grazing management of a component: an intensity, or a missing part. */
export type GrazingPart = { intensity: string } | { missing: MissingPart }

/** The termination of a component: a dated method, or a missing part. */
export type TerminationPart = { date: string; method: string } | { missing: MissingPart }

/** The management block of a component, each part present or missing. */
export interface ManagementPart {
  residue: ResiduePart
  grazing: GrazingPart
  termination: TerminationPart
}

/** One component of the rotation, at its position in the order. */
export interface RotationComponent {
  component_id: string
  position: number
  crop_id: string
  purpose: string
  sowing: DatedPart
  harvest: DatedPart
  management: ManagementPart
}

/** A rotation as the rotation_definition contract travels it. */
export interface RotationDefinition {
  contract: 'rotation_definition'
  example_data: true
  case_id: string
  field_id: string
  rotation_id: string
  label: string
  ag_year_start: AgYearStart
  repeats: boolean
  components: RotationComponent[]
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function parseProvenance(value: unknown, where: string): ProvenanceLabel {
  if (typeof value !== 'string' || !PROVENANCE_LABELS.includes(value as ProvenanceLabel)) {
    throw new Error(`${where}:provenance-not-a-label`)
  }
  return value as ProvenanceLabel
}

function parseMissing(value: unknown, where: string): MissingPart {
  if (!isRecord(value)) {
    throw new Error(`${where}:missing-not-an-object`)
  }
  if (typeof value.reason !== 'string' || !REASON_CODES.includes(value.reason as ReasonCode)) {
    throw new Error(`${where}:missing-reason-not-a-code`)
  }
  const missing: MissingPart = { reason: value.reason as ReasonCode }
  if (value.detail !== undefined) {
    if (!isNonEmptyString(value.detail)) {
      throw new Error(`${where}:missing-detail-not-a-string`)
    }
    missing.detail = value.detail
  }
  return missing
}

function parseDatedPart(value: unknown, where: string): DatedPart {
  if (!isRecord(value)) {
    throw new Error(`${where}:not-an-object`)
  }
  if (value.date === null) {
    return { date: null, missing: parseMissing(value.missing, where) }
  }
  if (!isNonEmptyString(value.date)) {
    throw new Error(`${where}:date-not-a-string`)
  }
  if (!isNonEmptyString(value.source)) {
    throw new Error(`${where}:source-empty`)
  }
  return {
    date: value.date,
    provenance: parseProvenance(value.provenance, where),
    source: value.source,
  }
}

function parseResidue(value: unknown, where: string): ResiduePart {
  if (isRecord(value)) {
    return { missing: parseMissing(value.missing, where) }
  }
  if (!isNonEmptyString(value)) {
    throw new Error(`${where}:residue-not-a-string`)
  }
  return value
}

function parseGrazing(value: unknown, where: string): GrazingPart {
  if (!isRecord(value)) {
    throw new Error(`${where}:grazing-not-an-object`)
  }
  if (value.missing !== undefined) {
    return { missing: parseMissing(value.missing, where) }
  }
  if (!isNonEmptyString(value.intensity)) {
    throw new Error(`${where}:grazing-intensity-not-a-string`)
  }
  return { intensity: value.intensity }
}

function parseTermination(value: unknown, where: string): TerminationPart {
  if (!isRecord(value)) {
    throw new Error(`${where}:termination-not-an-object`)
  }
  if (value.missing !== undefined) {
    return { missing: parseMissing(value.missing, where) }
  }
  if (!isNonEmptyString(value.date)) {
    throw new Error(`${where}:termination-date-not-a-string`)
  }
  if (!isNonEmptyString(value.method)) {
    throw new Error(`${where}:termination-method-not-a-string`)
  }
  return { date: value.date, method: value.method }
}

function parseManagement(value: unknown, where: string): ManagementPart {
  if (!isRecord(value)) {
    throw new Error(`${where}:management-not-an-object`)
  }
  return {
    residue: parseResidue(value.residue, `${where}.residue`),
    grazing: parseGrazing(value.grazing, `${where}.grazing`),
    termination: parseTermination(value.termination, `${where}.termination`),
  }
}

function parseComponent(value: unknown, index: number): RotationComponent {
  if (!isRecord(value)) {
    throw new Error(`invalid-rotation:component[${index}]-not-an-object`)
  }
  const where = `invalid-rotation:component[${index}]`
  if (!isNonEmptyString(value.component_id)) {
    throw new Error(`${where}:component-id-empty`)
  }
  if (!isFiniteNumber(value.position) || !Number.isInteger(value.position)) {
    throw new Error(`${where}:position-not-an-integer`)
  }
  if (!isNonEmptyString(value.crop_id)) {
    throw new Error(`${where}:crop-id-empty`)
  }
  if (!isNonEmptyString(value.purpose)) {
    throw new Error(`${where}:purpose-empty`)
  }
  return {
    component_id: value.component_id,
    position: value.position,
    crop_id: value.crop_id,
    purpose: value.purpose,
    sowing: parseDatedPart(value.sowing, `${where}.sowing`),
    harvest: parseDatedPart(value.harvest, `${where}.harvest`),
    management: parseManagement(value.management, `${where}`),
  }
}

function parseAgYearStart(value: unknown): AgYearStart {
  if (!isRecord(value)) {
    throw new Error('invalid-rotation:ag-year-not-an-object')
  }
  if (!isFiniteNumber(value.month) || !Number.isInteger(value.month) || value.month < 1 || value.month > 12) {
    throw new Error('invalid-rotation:ag-year-month-not-a-month')
  }
  if (typeof value.provisional !== 'boolean') {
    throw new Error('invalid-rotation:ag-year-provisional-not-a-boolean')
  }
  if (!isNonEmptyString(value.source)) {
    throw new Error('invalid-rotation:ag-year-source-empty')
  }
  return {
    month: value.month,
    provisional: value.provisional,
    provenance: parseProvenance(value.provenance, 'invalid-rotation:ag-year'),
    source: value.source,
  }
}

/**
 * Parse and validate a rotation of the contract. Pure: value in, typed
 * rotation out, or an Error naming what is wrong. The ribbon shows example
 * data only, so a file without the example_data flag is rejected, exactly as
 * the example case parser does.
 */
export function parseRotationDefinition(value: unknown): RotationDefinition {
  if (!isRecord(value)) {
    throw new Error('invalid-rotation:not-an-object')
  }
  if (value.contract !== 'rotation_definition') {
    throw new Error('invalid-rotation:contract-not-rotation-definition')
  }
  if (value.example_data !== true) {
    throw new Error('invalid-rotation:example-data-not-true')
  }
  if (!isNonEmptyString(value.case_id)) {
    throw new Error('invalid-rotation:case-id-empty')
  }
  if (!isNonEmptyString(value.field_id)) {
    throw new Error('invalid-rotation:field-id-empty')
  }
  if (!isNonEmptyString(value.rotation_id)) {
    throw new Error('invalid-rotation:rotation-id-empty')
  }
  if (!isNonEmptyString(value.label)) {
    throw new Error('invalid-rotation:label-empty')
  }
  if (typeof value.repeats !== 'boolean') {
    throw new Error('invalid-rotation:repeats-not-a-boolean')
  }
  if (!Array.isArray(value.components)) {
    throw new Error('invalid-rotation:components-not-an-array')
  }
  return {
    contract: 'rotation_definition',
    example_data: true,
    case_id: value.case_id,
    field_id: value.field_id,
    rotation_id: value.rotation_id,
    label: value.label,
    ag_year_start: parseAgYearStart(value.ag_year_start),
    repeats: value.repeats,
    components: value.components.map(parseComponent),
  }
}

/** The example rotation: illustrative placeholder data that describes no real field. */
export const exampleRotation: RotationDefinition = parseRotationDefinition(rawRotation)
