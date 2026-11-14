import rawCase from '../data/example_case.json'
/** GeoJSON polygon, WGS84 longitude/latitude, exterior ring closed. */
export interface PolygonGeometry {
  type: 'Polygon'
  coordinates: number[][][]
}

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
    throw new Error(`invalid-geometry[${fieldId}]:not-an-object`)
  }
  const geometry = value as { type?: unknown; coordinates?: unknown }
  if (geometry.type !== 'Polygon') {
    throw new Error(`invalid-geometry[${fieldId}]:type-not-polygon`)
  }
  if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length === 0) {
    throw new Error(`invalid-geometry[${fieldId}]:coordinates-not-rings`)
  }
  for (const ring of geometry.coordinates) {
    if (!Array.isArray(ring) || ring.length < 3) {
      throw new Error(`invalid-geometry[${fieldId}]:ring-too-short`)
    }
    for (const position of ring) {
      if (!Array.isArray(position) || !isFiniteNumber(position[0]) || !isFiniteNumber(position[1])) {
        throw new Error(`invalid-geometry[${fieldId}]:position-not-finite`)
      }
    }
  }
  return geometry as unknown as PolygonGeometry
}

function parseField(value: unknown): ExampleField {
  if (typeof value !== 'object' || value === null) {
    throw new Error('invalid-case:field-not-an-object')
  }
  const field = value as Record<string, unknown>
  if (typeof field.field_id !== 'string' || field.field_id.length === 0) {
    throw new Error('invalid-case:field-id-empty')
  }
  if (typeof field.name !== 'string' || field.name.length === 0) {
    throw new Error(`invalid-field[${field.field_id}]:name-empty`)
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
    throw new Error('invalid-case:not-an-object')
  }
  const data = value as Record<string, unknown>
  if (data.example_data !== true) {
    throw new Error('invalid-case:example-data-not-true')
  }
  if (typeof data.case_id !== 'string' || data.case_id.length === 0) {
    throw new Error('invalid-case:case-id-empty')
  }
  if (typeof data.label !== 'string' || data.label.length === 0) {
    throw new Error('invalid-case:label-empty')
  }
  if (!Array.isArray(data.fields)) {
    throw new Error('invalid-case:fields-not-array')
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
