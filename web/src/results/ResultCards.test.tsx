import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import ResultCards from './ResultCards'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import {
  parseResultsPerRotation,
  resultsExampleRotations,
  resultsPerRotationExample,
  resultsPerRotationNotBuiltExample,
} from './resultsData'
import type { ResultsPerRotation } from './resultsData'
import type { ValueItem } from '../components/ValueDisplay'
import rawPerRotation from '../data/PLACEHOLDER_results_per_rotation.json'
import rawPerRotationNotBuilt from '../data/PLACEHOLDER_results_per_rotation_not_built.json'

/**
 * Acceptance test of the result cards (issue #141). The cards are a pure
 * function of the two contract examples, so their whole behaviour is their
 * static markup, rendered with the pure server renderer of react-dom. Every
 * expected text below is the supplied wording of strings.ts filled with the
 * values of the accepted contract examples, written out in full.
 *
 * The cases follow the brief:
 * (a) one card per rotation of the example;
 * (b) every value through the shared value display;
 * (c) carbon values labelled with model and computation, never averaged
 *     across models (C1.5);
 * (d) a part whose module is not built renders missing NOT_AVAILABLE,
 *     never zero;
 * (e) the example banner is visible.
 */

/** How many times a data-testid appears in a server-rendered markup. */
function countTestIds(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

/** The whole visible text of a markup, tags dropped, runs of spaces joined. */
function visibleText(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** The cards of a markup, as chunks split on the card's test id. */
function cardChunks(html: string): string[] {
  return html.split('data-testid="rotation-card"').slice(1)
}

/** The soil-loss part of a document, asserted present before it is read. */
function presentSoilLoss(doc: ResultsPerRotation) {
  if (doc.soil_loss.form !== 'present') throw new Error('expected the present soil-loss part')
  return doc.soil_loss
}

/** The carbon part of a document, asserted present before it is read. */
function presentCarbon(doc: ResultsPerRotation) {
  if (doc.soil_carbon_trend.form !== 'present') throw new Error('expected the present carbon part')
  return doc.soil_carbon_trend
}

/**
 * Every item the cards render for one document, in the order the cards show
 * them: the annual and the monthly soil-loss values, the water values, the
 * carbon values — or, for a wholly missing part, the one missing item the
 * card renders in its place.
 */
function renderedItems(doc: ResultsPerRotation): ValueItem[] {
  const items: ValueItem[] = []
  if (doc.soil_loss.form === 'present') {
    for (const annual of doc.soil_loss.annual) items.push(annual.item)
    for (const monthly of doc.soil_loss.monthly) items.push(monthly.item)
  } else {
    items.push({ value: null, unit: doc.soil_loss.units[0], missing: doc.soil_loss.missing })
  }
  if (doc.water_deficit_exposure.form === 'present') {
    for (const value of doc.water_deficit_exposure.values) items.push(value.item)
  } else {
    items.push({
      value: null,
      unit: doc.water_deficit_exposure.units[0],
      missing: doc.water_deficit_exposure.missing,
    })
  }
  if (doc.soil_carbon_trend.form === 'present') {
    for (const value of doc.soil_carbon_trend.values) items.push(value.item)
  } else {
    items.push({
      value: null,
      unit: doc.soil_carbon_trend.units[0],
      missing: doc.soil_carbon_trend.missing,
    })
  }
  return items
}

function renderedItemsOf(docs: ResultsPerRotation[]): ValueItem[] {
  return docs.flatMap(renderedItems)
}

const html = renderToString(<ResultCards />)
const cards = cardChunks(html)
const builtCard = cards.find((chunk) => chunk.includes('data-testid="annual-row"')) ?? ''
const notBuiltCard =
  cards.find((chunk) => !chunk.includes('data-testid="annual-row"') && chunk.includes('part-row')) ??
  ''

// --- (a) one card per rotation of the example -----------------------------------

describe('ResultCards: one card per rotation', () => {
  it('renders one card per rotation document of the example, each headed with its rotation id', () => {
    expect(cards.length).toBe(resultsExampleRotations.length)
    expect(countTestIds(html, 'rotation-heading')).toBe(resultsExampleRotations.length)
    for (const doc of resultsExampleRotations) {
      expect(html).toContain(formatString(strings['cards.per_rotation'], { id: doc.rotation_id }))
    }
    expect(html).toContain(strings['cards.title'])
    expect(countTestIds(html, 'availability-heading')).toBe(resultsExampleRotations.length)
    expect(html).toContain(strings['cards.availability'])
  })
})

// --- (b) every value through the shared value display ------------------------------

describe('ResultCards: every value through the value display', () => {
  it('renders exactly one display line per item of the example, present or missing', () => {
    const items = renderedItemsOf(resultsExampleRotations)
    const present = items.filter((item) => item.value !== null).length
    const missing = items.length - present
    expect(countTestIds(html, 'value-line') + countTestIds(html, 'missing-line')).toBe(items.length)
    expect(countTestIds(html, 'value-line')).toBe(present)
    expect(countTestIds(html, 'missing-line')).toBe(missing)
  })

  it('renders the annual and monthly rows of the present form, one per year and per month', () => {
    const soilLoss = presentSoilLoss(resultsPerRotationExample)
    expect(countTestIds(builtCard, 'annual-row')).toBe(soilLoss.annual.length)
    expect(countTestIds(builtCard, 'monthly-row')).toBe(soilLoss.monthly.length)
  })

  it('shows a value with its label, its unit, its provenance label, its source and its range', () => {
    const text = visibleText(html)
    expect(text).toContain('soil_loss 2001 12 t ha-1 yr-1 Derived')
    expect(text).toContain('Source: PLACEHOLDER source: written by hand, not the output of an engine')
    expect(text).toContain('6 to 18 (PLACEHOLDER_range_kind)')
    expect(text).toContain('soil_loss 2001-07 1 t ha-1 month-1 Derived')
    expect(text).toContain('soil_carbon_trend 0.5 t C ha-1 yr-1 Simulated')
  })

  it('shows a missing value with its reason, never zero or blank', () => {
    const text = visibleText(html)
    expect(text).toContain('soil_loss 2002: no coverage for this place or period')
    expect(text).toContain('soil_loss 2003-01: no coverage for this place or period')
    expect(text).toContain('water_deficit_exposure: module not built or not enabled')
    expect(text).toContain('soil_carbon_trend: not computable for this case')
    expect(html).not.toContain('>0</span>')
  })
})

// --- (c) carbon values: labelled per model and per computation, never averaged ------

describe('ResultCards: carbon values per model and per computation', () => {
  const carbon = presentCarbon(resultsPerRotationExample)
  const carbonChunks = html.split('data-testid="carbon-item"').slice(1)

  it('renders one labelled item per carbon value of the example', () => {
    expect(countTestIds(html, 'carbon-item')).toBe(carbon.values.length)
    expect(countTestIds(html, 'carbon-model-label')).toBe(carbon.values.length)
    expect(countTestIds(html, 'carbon-computation-label')).toBe(carbon.values.length)
  })

  it('labels every item with its model and its computation, one item per pair', () => {
    const pairs = carbonChunks.map((chunk) => {
      const model = /Model: (amg|rothc)/.exec(chunk)?.[1]
      const computation = /Computation: (end_minus_start|fitted_slope|mean_over_cycles)/.exec(
        chunk,
      )?.[1]
      return `${model}/${computation}`
    })
    const expected = carbon.values.map((value) => `${value.carbon_model}/${value.computation}`)
    expect([...pairs].sort()).toEqual([...expected].sort())
    expect(new Set(pairs).size).toBe(carbon.values.length)
  })

  it('never merges or averages across models: each value is shown as itself', () => {
    const text = visibleText(html)
    expect(text).toContain('0.5 t C ha-1 yr-1 Simulated')
    expect(text).toContain('0.25 t C ha-1 yr-1 Simulated')
    // The mean of the two amg values (0.375) is nowhere on the page.
    expect(text).not.toContain('0.375')
    // A model that is not enabled stays missing with its reason, three times.
    expect(builtCard.split('soil_carbon_trend: module not built or not enabled').length - 1).toBe(
      3,
    )
  })
})

// --- (d) a module not built renders missing NOT_AVAILABLE, never zero ----------------

describe('ResultCards: a module not built', () => {
  it('renders every wholly missing part as missing with NOT_AVAILABLE, and no value', () => {
    expect(notBuiltCard).not.toBe('')
    expect(countTestIds(notBuiltCard, 'missing-line')).toBe(3)
    expect(countTestIds(notBuiltCard, 'value-line')).toBe(0)
    for (const indicator of ['soil_loss', 'water_deficit_exposure', 'soil_carbon_trend']) {
      expect(notBuiltCard).toContain(
        `${indicator}: ${strings['missing.NOT_AVAILABLE']}`,
      )
    }
  })
})

// --- (e) the example banner ----------------------------------------------------------

describe('ResultCards: the example banner', () => {
  it('labels the results example with the example banner while its ids are not of this case', () => {
    expect(countTestIds(html, 'results-example-banner')).toBe(1)
    expect(html).toContain(strings['example.banner'])
  })
})

// --- the parts the display relies on ---------------------------------------------------

describe('resultsData: the parts the display relies on', () => {
  it('loads both examples: one in the present form, one wholly missing with NOT_AVAILABLE', () => {
    expect(resultsPerRotationExample.soil_loss.form).toBe('present')
    expect(resultsPerRotationNotBuiltExample.soil_loss.form).toBe('not_built')
    expect(resultsPerRotationNotBuiltExample.water_deficit_exposure.form).toBe('not_built')
    expect(resultsPerRotationNotBuiltExample.soil_carbon_trend.form).toBe('not_built')
    for (const part of [
      resultsPerRotationNotBuiltExample.soil_loss,
      resultsPerRotationNotBuiltExample.water_deficit_exposure,
      resultsPerRotationNotBuiltExample.soil_carbon_trend,
    ]) {
      if (part.form !== 'not_built') throw new Error('expected the wholly missing form')
      expect(part.missing.reason).toBe('NOT_AVAILABLE')
    }
  })

  it('rejects a wholly missing part whose reason is not NOT_AVAILABLE (D12)', () => {
    const variant = JSON.parse(JSON.stringify(rawPerRotationNotBuilt)) as {
      soil_loss: { missing: { reason: string } }
    }
    variant.soil_loss.missing.reason = 'NOT_APPLICABLE'
    expect(() => parseResultsPerRotation(variant)).toThrow('reason-not-not-available')
  })

  it('rejects a value without a provenance label (C4.1)', () => {
    const variant = JSON.parse(JSON.stringify(rawPerRotation)) as {
      soil_loss: { annual: { provenance?: string }[] }
    }
    delete variant.soil_loss.annual[0].provenance
    expect(() => parseResultsPerRotation(variant)).toThrow('provenance-not-a-label')
  })

  it('rejects a carbon value whose model is not amg or rothc (D1 of #77)', () => {
    const variant = JSON.parse(JSON.stringify(rawPerRotation)) as {
      soil_carbon_trend: { carbon_model: string }[]
    }
    variant.soil_carbon_trend[0].carbon_model = 'AMG'
    expect(() => parseResultsPerRotation(variant)).toThrow('carbon-model-not-in-list')
  })
})
