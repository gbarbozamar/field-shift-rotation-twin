import { describe, expect, it } from 'vitest'
import * as mapStyles from './mapStyles'

/**
 * Guardian of the map style unit (issue #461): the two exported style
 * objects carry the polygon styles of the design handoff package of
 * 15 Nov 2026, file assets/map-styles.json (SHA-256
 * 20ab2acd091824d75b70cb1f1bb93f3ac0d996ff6853efd8f071e4c30b261d5d)
 * key for key — every key present, no key extra — and the module
 * exports exactly the two names.
 */

/** The polygon styles, transcribed verbatim from the design handoff. */
const HANDOFF: Record<string, Record<string, string | number>> = {
  fieldOptions: {
    color: '#52685d',
    fillColor: '#b9c8ae',
    fillOpacity: 0.22,
    weight: 2,
  },
  selectedOptions: {
    color: '#3e7b2c',
    fillColor: '#5ba543',
    fillOpacity: 0.3,
    weight: 3,
  },
}

describe('map polygon styles of the design handoff', () => {
  it('each exported object matches the handoff value key for key', () => {
    for (const name of Object.keys(HANDOFF)) {
      const style = (mapStyles as Record<string, unknown>)[name]
      expect(style, `${name} must be exported`).toBeDefined()
      expect(Object.keys(style as object).sort(), `${name} must carry exactly the handoff keys`).toEqual([
        'color',
        'fillColor',
        'fillOpacity',
        'weight',
      ])
      expect(style, `${name} must match the handoff values, key for key`).toEqual(HANDOFF[name])
    }
  })

  it('the module exports exactly the two names', () => {
    expect(Object.keys(mapStyles).sort()).toEqual(['fieldOptions', 'selectedOptions'])
  })
})
