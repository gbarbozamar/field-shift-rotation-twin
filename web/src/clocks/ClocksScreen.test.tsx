import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import ClocksScreen from './ClocksScreen'
import { resultsTable, rotationsOfTable } from './clockData'
import { strings } from '../strings'

/**
 * Acceptance test of the two clocks (issue #140). The section is a pure
 * function of the accepted results-table example, so its whole behaviour is
 * its static markup, rendered with the pure server renderer of react-dom.
 * Every expected text below is the supplied wording of strings.ts filled
 * with the values of the accepted contract example, written out in full.
 *
 * The acceptance cases of the unit brief:
 * (a) two clocks per rotation, one column per agricultural year of the
 *     example;
 * (b) every value renders through the value display, with its unit and its
 *     provenance label (and its source and range where the example has
 *     them);
 * (c) a missing year shows the missing pattern with its reason, never 0
 *     and never a blank;
 * (d) the example-data label is visible.
 */

/** How many times a data-testid appears in a server-rendered markup. */
function countTestIds(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

/** How many times an exact text appears in a markup. */
function countText(html: string, text: string): number {
  return html.split(text).length - 1
}

/** The whole visible text of a markup, tags dropped, runs of spaces joined. */
function visibleText(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** The markup after the nth rotation block opener, up to the next one. */
function rotationBlock(html: string, index: number): string {
  return html.split('data-testid="clocks-rotation"')[index + 1] ?? ''
}

const ROTATIONS = rotationsOfTable(resultsTable)

describe('ClocksScreen', () => {
  // -- the section and the example banner (d) -----------------------------------

  it('renders the section title and the years hint', () => {
    const html = renderToString(<ClocksScreen />)
    expect(html).toContain(strings['clocks.title'])
    expect(html).toContain(strings['clocks.years_hint'])
  })

  it('labels the example data with the example banner and the clocks note (d)', () => {
    const html = renderToString(<ClocksScreen />)
    expect(html).toContain(strings['example.banner'])
    expect(html).toContain(strings['clocks.example_note'])
    expect(countTestIds(html, 'clocks-example-banner')).toBe(1)
    expect(countTestIds(html, 'clocks-example-note')).toBe(1)
  })

  // -- (a) two clocks per rotation, one column per agricultural year -------------

  it('renders one block per rotation of the example, headed by the rotation id', () => {
    const html = renderToString(<ClocksScreen />)
    expect(countTestIds(html, 'clocks-rotation')).toBe(ROTATIONS.length)
    expect(countTestIds(html, 'clocks-rotation-id')).toBe(ROTATIONS.length)
    for (const rotation of ROTATIONS) {
      expect(html).toContain(rotation.rotation_id)
    }
  })

  it('renders the soil clock and the water clock in every rotation block (a)', () => {
    const html = renderToString(<ClocksScreen />)
    expect(countTestIds(html, 'soil-clock')).toBe(ROTATIONS.length)
    expect(countTestIds(html, 'water-clock')).toBe(ROTATIONS.length)
    for (let index = 0; index < ROTATIONS.length; index += 1) {
      const block = rotationBlock(html, index)
      expect(block).toContain('data-testid="soil-clock"')
      expect(block).toContain('data-testid="water-clock"')
      expect(block).toContain(strings['clocks.soil'])
      expect(block).toContain(strings['clocks.water'])
    }
  })

  it('renders one soil column per agricultural year of the example (a)', () => {
    const html = renderToString(<ClocksScreen />)
    // The example carries two agricultural years of soil loss per rotation;
    // its water rows travel per rotation, so they hold no year column.
    expect(countTestIds(html, 'clock-column')).toBe(ROTATIONS.length * 2)
    expect(countTestIds(html, 'clock-year')).toBe(ROTATIONS.length * 2)
    expect(countText(html, '>2001<')).toBe(ROTATIONS.length)
    expect(countText(html, '>2002<')).toBe(ROTATIONS.length)
    for (let index = 0; index < ROTATIONS.length; index += 1) {
      expect(countTestIds(rotationBlock(html, index), 'clock-column')).toBe(2)
    }
  })

  it('shows the water clock as the value the example carries for the whole rotation', () => {
    const html = renderToString(<ClocksScreen />)
    expect(countTestIds(html, 'clock-item')).toBe(ROTATIONS.length)
  })

  // -- (b) every value through the value display ----------------------------------

  it('renders the present soil values with unit, provenance, source and range (b)', () => {
    const html = renderToString(<ClocksScreen />)
    expect(countTestIds(html, 'value-line')).toBe(ROTATIONS.length)
    expect(countTestIds(html, 'value-number')).toBe(ROTATIONS.length)
    expect(countTestIds(html, 'value-unit')).toBe(ROTATIONS.length)
    expect(countTestIds(html, 'value-label')).toBe(ROTATIONS.length)
    expect(countTestIds(html, 'source-line')).toBe(ROTATIONS.length)
    expect(countTestIds(html, 'range-line')).toBe(ROTATIONS.length)
    const text = visibleText(html)
    expect(text).toContain('12 t ha-1 yr-1 Derived')
    expect(text).toContain('8 t ha-1 yr-1 Derived')
    expect(text).toContain(
      'Source: PLACEHOLDER source: written by hand, not the output of an engine',
    )
    expect(text).toContain('6 to 18 (PLACEHOLDER_range_kind)')
    expect(text).toContain('4 to 12 (PLACEHOLDER_range_kind)')
  })

  // -- (c) a missing year shows the missing pattern with its reason ---------------

  it('renders the missing soil year as missing with its reason, never 0 or blank (c)', () => {
    const html = renderToString(<ClocksScreen />)
    expect(countTestIds(html, 'missing-line')).toBe(ROTATIONS.length * 2)
    expect(countText(html, 'soil_loss: no coverage for this place or period')).toBe(
      ROTATIONS.length,
    )
    // nothing renders a zero in place of the missing year
    expect(html).not.toContain('<span data-testid="value-number">0</span>')
    expect(countTestIds(html, 'value-number')).toBe(ROTATIONS.length)
  })

  it('renders the missing water value as missing with its reason (c)', () => {
    const html = renderToString(<ClocksScreen />)
    expect(countText(html, 'water_deficit_exposure: module not built or not enabled')).toBe(
      ROTATIONS.length,
    )
  })
})
