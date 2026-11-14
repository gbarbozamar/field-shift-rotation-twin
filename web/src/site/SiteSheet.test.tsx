import { beforeEach, describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import SiteSheet, { MonthlySeriesBlock } from './SiteSheet'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId } from '../identity/selection'
import { siteClimate } from './siteData'
import type { MonthlySeries } from './siteData'
import { strings } from '../strings'

/**
 * Acceptance test of the site sheet (issue #108). The sheet is a pure
 * function of the shared selection and of the two contract examples, so its
 * whole behaviour is its static markup, rendered with the pure server
 * renderer of react-dom. Every expected text below is the supplied wording
 * of strings.ts filled with the values of the accepted contract examples,
 * written out in full.
 */

/** How many times a data-testid appears in a server-rendered markup. */
function countTestIds(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

/** The whole visible text of a markup, tags dropped, runs of spaces joined. */
function visibleText(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

describe('SiteSheet: no field selected', () => {
  beforeEach(() => {
    setSelectedFieldId(null)
  })

  it('shows the site title and the select hint, and no site data', () => {
    const html = renderToString(<SiteSheet />)
    expect(html).toContain(strings['site.title'])
    expect(html).toContain(strings['site.select_hint'])
    expect(html).not.toContain(strings['example.banner'])
    expect(html).not.toContain(strings['site.climate_section'])
    expect(html).not.toContain(strings['site.soil_section'])
    expect(countTestIds(html, 'value-line')).toBe(0)
    expect(countTestIds(html, 'missing-line')).toBe(0)
  })
})

describe('SiteSheet: a field selected', () => {
  beforeEach(() => {
    setSelectedFieldId(exampleCase.fields[0].field_id)
  })

  it('labels the example site data with the example banner', () => {
    const html = renderToString(<SiteSheet />)
    expect(html).toContain(strings['example.banner'])
    expect(countTestIds(html, 'site-example-banner')).toBe(1)
  })

  it('shows the climate and the soil sections', () => {
    const html = renderToString(<SiteSheet />)
    expect(html).toContain(strings['site.climate_section'])
    expect(html).toContain(strings['site.soil_section'])
  })

  it('heads each series with its quantity and its unit', () => {
    const html = renderToString(<SiteSheet />)
    expect(countTestIds(html, 'series-heading')).toBe(siteClimate.monthly_series.length)
    for (const series of siteClimate.monthly_series) {
      const heading = `${series.quantity} (${series.unit})`
      expect(html).toContain(heading)
    }
  })

  it('shows the number of months of each series', () => {
    const html = renderToString(<SiteSheet />)
    for (const series of siteClimate.monthly_series) {
      expect(html).toContain(`${series.months.length} months`)
    }
  })

  it('renders every present month through the value display, one row per month', () => {
    const html = renderToString(<SiteSheet />)
    const presentMonths = siteClimate.monthly_series.reduce(
      (count, series) => count + series.months.filter((month) => month.value !== null).length,
      0,
    )
    expect(countTestIds(html, 'month-row')).toBe(
      siteClimate.monthly_series.reduce((count, series) => count + series.months.length, 0),
    )
    // plus the three soil-and-slope values that are not missing
    expect(countTestIds(html, 'value-line')).toBe(presentMonths + 3)
    // each month row carries its calendar position (C5.1), January being 1
    expect(html).toContain('2001-12')
    expect(html).toContain('2002-01')
    expect(html).toContain('2002-02')
  })

  it('renders slope length, slope steepness and the soil properties through the value display', () => {
    const html = renderToString(<SiteSheet />)
    const text = visibleText(html)
    // slope_length: 1 PLACEHOLDER_unit Observed, with its source
    expect(text).toContain('1 PLACEHOLDER_unit Observed')
    // slope_steepness: 2 PLACEHOLDER_unit Declared, an assumption, and its range
    expect(text).toContain('2 PLACEHOLDER_unit Declared')
    expect(text).toContain(strings['assumption.mark'])
    expect(text).toContain('1 to 3 (PLACEHOLDER_range_kind)')
    // the observed soil property, with its source
    expect(text).toContain('4 PLACEHOLDER_unit Observed')
    expect(text).toContain('Source: PLACEHOLDER: example data, no real source')
  })

  it('renders the missing soil property as missing with its reason, never zero', () => {
    const html = renderToString(<SiteSheet />)
    expect(html).toContain('placeholder_soil_property_b: no coverage for this place or period')
    expect(countTestIds(html, 'missing-line')).toBe(1)
  })
})

describe('MonthlySeriesBlock: a missing month', () => {
  // A series of the shape of the contract example, with the missing month the
  // climate example carries at day level shown here at month level: the same
  // C3.1 form, value null with a missing part and its reason code.
  const series: MonthlySeries = {
    quantity: 'precipitation',
    unit: 'PLACEHOLDER_unit',
    provenance: 'OBSERVED',
    source: 'PLACEHOLDER_source',
    range_missing: { reason: 'NOT_AVAILABLE' },
    months: [
      { year: 2001, month: 11, value: 1.5 },
      { year: 2001, month: 12, value: null, missing: { reason: 'NO_COVERAGE' } },
      { year: 2002, month: 1, value: null, missing: { reason: 'MISSING_INPUT', detail: 'gauge record' } },
    ],
  }

  it('renders the missing pattern with its reason, never zero or blank', () => {
    const html = renderToString(<MonthlySeriesBlock series={series} />)
    // the present month renders as a value
    expect(countTestIds(html, 'value-number')).toBe(1)
    // each missing month renders the pattern naming the quantity, the month and the reason
    expect(html).toContain('precipitation 2001-12: no coverage for this place or period')
    expect(html).toContain('precipitation 2002-01: missing input: gauge record')
    expect(countTestIds(html, 'missing-line')).toBe(2)
    // a missing month never renders a number: no zero, no blank, no unit
    expect(visibleText(html)).not.toContain(': 0')
  })

  it('heads the series with its quantity and its unit and counts its months', () => {
    const html = renderToString(<MonthlySeriesBlock series={series} />)
    expect(html).toContain('precipitation (PLACEHOLDER_unit)')
    expect(html).toContain('3 months')
  })
})
