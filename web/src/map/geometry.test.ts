import { describe, expect, it } from 'vitest'
import { exampleCase } from '../identity/exampleCase'
import { strings } from '../strings'
import { attributionMarkup, fieldPositions, fieldsBounds } from './geometry'

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
