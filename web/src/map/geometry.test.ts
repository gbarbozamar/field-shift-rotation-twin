import { describe, expect, it } from 'vitest'
import { exampleCase } from '../identity/exampleCase'
import { strings } from '../strings'
import { attributionMarkup, fieldAreaHa, fieldPositions, fieldsBounds } from './geometry'
import type { ExampleField } from '../identity/exampleCase'

describe('map geometry helpers', () => {
  it('turns GeoJSON [lng, lat] rings into Leaflet [lat, lng] positions', () => {
    for (const field of exampleCase.fields) {
      const rings = fieldPositions(field)
      expect(rings.length).toBe(field.geometry.coordinates.length)
      const ring = rings[0]
      const source = field.geometry.coordinates[0]
      expect(ring.length).toBe(source.length)
      for (let i = 0; i < ring.length; i += 1) {
        expect(ring[i][0]).toBe(source[i][1])
        expect(ring[i][1]).toBe(source[i][0])
      }
    }
  })

  it('derives the view bounds from every position of every field', () => {
    // Expected values copied from web/src/data/example_case.json (the
    // person-written example data), not invented here.
    expect(fieldsBounds(exampleCase.fields)).toEqual([
      [-34.382317, -57.734666],
      [-34.332234, -57.681518],
    ])
  })

  it('returns no bounds when the case has no fields', () => {
    expect(fieldsBounds([])).toBe(null)
  })

  it('links the supplied attribution wording to the copyright page', () => {
    const markup = attributionMarkup()
    expect(markup).toContain(strings['map.layer.attribution'])
    expect(markup).toContain('https://www.openstreetmap.org/copyright')
    expect(markup.startsWith('<a')).toBe(true)
    expect(markup.endsWith('</a>')).toBe(true)
  })
})

describe('fieldAreaHa', () => {
  const square = (lat0: number, lat1: number, lon0: number, lon1: number): ExampleField => ({
    field_id: 'square',
    name: 'square',
    geometry: { type: 'Polygon', coordinates: [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]] },
  })

  it('a one-degree cell at the equator matches the closed form R^2 dLon (sin lat1 - sin lat0)', () => {
    const R = 6371008.8
    const expected = (R * R * (Math.PI / 180) * Math.sin(Math.PI / 180)) / 10000
    expect(fieldAreaHa(square(0, 1, 0, 1))).toBeCloseTo(expected, 3)
  })

  it('is the same whichever way the ring turns', () => {
    const cw = square(-34.3, -34.4, -57.7, -57.6)
    const ccw: ExampleField = { ...cw, geometry: { type: 'Polygon', coordinates: [[...cw.geometry.coordinates[0]].reverse()] } }
    expect(fieldAreaHa(ccw)).toBeCloseTo(fieldAreaHa(cw), 6)
  })

  it('subtracts a hole', () => {
    const outer = square(0, 1, 0, 1)
    const hole = square(0.25, 0.75, 0.25, 0.75).geometry.coordinates[0]
    const holed: ExampleField = { ...outer, geometry: { type: 'Polygon', coordinates: [outer.geometry.coordinates[0], hole] } }
    expect(fieldAreaHa(holed)).toBeCloseTo(fieldAreaHa(outer) - fieldAreaHa(square(0.25, 0.75, 0.25, 0.75)), 3)
  })
})
