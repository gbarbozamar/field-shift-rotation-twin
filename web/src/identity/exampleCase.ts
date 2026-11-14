import rawCase from '../data/example_case.json'
import type { PolygonGeometry } from './geometry'

/** A field of the example case (illustrative placeholder, no real field). */
export interface ExampleField {
  field_id: string
  name: string
  geometry: PolygonGeometry
}

/** Shape of the example case file written by the interface developer. */
export interface ExampleCase {
  example_data: true
  case_id: string
  label: string
  fields: ExampleField[]
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function parseGeometry(value: unknown, fieldId: string): PolygonGeometry {
  if (typeof value !== 'object' || value === null) {
    throw new Error(`Field ${fieldId}: geometry must be an object`)
  }
  const geometry = value as { type?: unknown; coordinates?: unknown }
  if (geometry.type !== 'Polygon') {
    throw new Error(`Field ${fieldId}: geometry.type must be "Polygon"`)
  }
  if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length === 0) {
    throw new Error(`Field ${fieldId}: geometry.coordinates must be a non-empty array of rings`)
  }
  for (const ring of geometry.coordinates) {
    if (!Array.isArray(ring) || ring.length < 3) {
      throw new Error(`Field ${fieldId}: each ring needs at least three positions`)
    }
    for (const position of ring) {
      if (!Array.isArray(position) || !isFiniteNumber(position[0]) || !isFiniteNumber(position[1])) {
        throw new Error(`Field ${fieldId}: each position needs a finite longitude and latitude`)
      }
    }
  }
  return geometry as unknown as PolygonGeometry
}

function parseField(value: unknown): ExampleField {
  if (typeof value !== 'object' || value === null) {
    throw new Error('Each entry of fields must be an object')
  }
  const field = value as Record<string, unknown>
  if (typeof field.field_id !== 'string' || field.field_id.length === 0) {
    throw new Error('Each field needs a non-empty field_id')
  }
  if (typeof field.name !== 'string' || field.name.length === 0) {
    throw new Error(`Field ${field.field_id}: name must be a non-empty string`)
  }
  return {
    field_id: field.field_id,
    name: field.name,
    geometry: parseGeometry(field.geometry, field.field_id),
  }
}

/**
 * Parse and validate the example case file. Pure: value in, typed case out,
 * or an Error naming what is wrong. The screen shows example data only, so a
 * file without the example_data flag is rejected.
 */
export function parseExampleCase(value: unknown): ExampleCase {
  if (typeof value !== 'object' || value === null) {
    throw new Error('The example case file must contain an object')
  }
  const data = value as Record<string, unknown>
  if (data.example_data !== true) {
    throw new Error('The case file must carry "example_data": true (this screen shows example data only)')
  }
  if (typeof data.case_id !== 'string' || data.case_id.length === 0) {
    throw new Error('The case file needs a non-empty case_id')
  }
  if (typeof data.label !== 'string' || data.label.length === 0) {
    throw new Error('The case file needs a non-empty label')
  }
  if (!Array.isArray(data.fields)) {
    throw new Error('The case file needs a fields array')
  }
  return {
    example_data: true,
    case_id: data.case_id,
    label: data.label,
    fields: data.fields.map(parseField),
  }
}

/** The example case: illustrative placeholder data that describes no real field. */
export const exampleCase: ExampleCase = parseExampleCase(rawCase)
