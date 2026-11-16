import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { BarList } from './BarList'
import { GroupedBarChart, barLabel, barPath } from './BarChart'
import type { ChartGroup, ChartSeries } from './BarChart'
import { chartTicks, linearScale, niceStep, niceTicks, tickText } from './scale'

/**
 * Tests of the chart kit (l3/original-mock): the scales and ticks, missing
 * values never drawn as zero, the reference and zero lines, and the
 * accessible labels of the bar slots. Rendered with the server renderer.
 */

function decode(html: string): string {
  return html.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&')
}

function count(html: string, needle: string): number {
  return html.split(needle).length - 1
}

function labels(html: string): string[] {
  return [...decode(html).matchAll(/aria-label="([^"]*)"/g)].map((m) => m[1])
}

const format = (value: number) => `${value}u`

const SERIES: ChartSeries[] = [
  { id: 'a', label: 'Option A', color: 'var(--fs-chart-1)' },
  { id: 'b', label: 'Option B', color: 'var(--fs-chart-2)' },
]

describe('scales and ticks', () => {
  it('a nice step is 1, 2, 2.5 or 5 times a power of ten', () => {
    expect(niceStep(10, 5)).toBe(2)
    expect(niceStep(312, 5)).toBe(100)
    expect(niceStep(7, 5)).toBe(2)
    expect(niceStep(0.9, 5)).toBe(0.2)
    expect(niceStep(0, 5)).toBe(1)
  })

  it('ticks cover the values, start at zero for positive values and are evenly spaced', () => {
    expect(niceTicks(0, 312)).toEqual([0, 100, 200, 300, 400])
    expect(niceTicks(1.5, 11)).toEqual([0, 2.5, 5, 7.5, 10, 12.5])
    const ticks = niceTicks(0, 0.7)
    expect(ticks[0]).toBe(0)
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(0.7)
    expect(ticks).toEqual(ticks.map((t) => Number(t.toPrecision(12))))
  })

  it('negative values bring zero inside the axis', () => {
    const ticks = niceTicks(-40, 120)
    expect(ticks[0]).toBeLessThanOrEqual(-40)
    expect(ticks).toContain(0)
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(120)
  })

  it('missing values take no part in the scale, reference lines do', () => {
    expect(chartTicks([null, 5, null])).toEqual(niceTicks(0, 5))
    expect(chartTicks([null, null])).toEqual([0, 1])
    expect(chartTicks([2, 3], [9])).toEqual(niceTicks(0, 9))
  })

  it('a linear scale maps the domain onto the range, a flat domain onto its start', () => {
    const y = linearScale([0, 100], [200, 0])
    expect(y(0)).toBe(200)
    expect(y(50)).toBe(100)
    expect(y(100)).toBe(0)
    expect(linearScale([3, 3], [10, 20])(3)).toBe(10)
  })

  it('large ticks are shortened, small ones printed as they are', () => {
    expect(tickText(25000)).toBe('25k')
    expect(tickText(2500)).toBe('2500')
    expect(tickText(0.2)).toBe('0.2')
  })

  it('a bar path is rounded at its far end and closes on the zero line', () => {
    const up = barPath(10, 100, 40, 20)
    expect(up.startsWith('M10,100')).toBe(true)
    expect(up).toContain('Q10,40,14,40')
    expect(up.endsWith('V100Z')).toBe(true)
    const down = barPath(10, 100, 160, 20)
    expect(down).toContain('Q10,160,14,160')
  })
})

describe('the grouped bar chart', () => {
  const groups: ChartGroup[] = [
    { id: 'g1', label: 'Average', values: [{ value: 222 }, { value: 312 }], emphasis: true },
    {
      id: 'g2',
      label: 'El Nino',
      values: [{ value: null, missingText: 'no value: module not built' }, { value: 11, notes: ['over the limit'], flagged: true }],
      tag: 'Mock',
    },
  ]

  it('draws one bar per present value and a hatched slot, never a zero bar, for a missing one', () => {
    const html = renderToString(<GroupedBarChart label="Margin" series={SERIES} groups={groups} format={format} />)
    expect(count(html, 'data-testid="chart-bar"')).toBe(3)
    expect(count(html, 'data-testid="chart-missing"')).toBe(1)
    expect(html).not.toContain('data-value="0"')
    expect(count(html, 'data-testid="chart-slot"')).toBe(4)
  })

  it('every slot is focusable and says its value, or the reason it is missing, in its label', () => {
    const html = renderToString(<GroupedBarChart label="Margin" series={SERIES} groups={groups} format={format} />)
    expect(count(html, 'tabindex="0"')).toBe(4)
    const said = labels(html)
    expect(said).toContain(formatString(strings['chart.bar'], { series: 'Option A', group: 'Average', value: '222u' }))
    expect(said).toContain(
      formatString(strings['chart.bar_missing'], { series: 'Option A', group: 'El Nino', missing: 'no value: module not built' }),
    )
    expect(said).toContain(
      formatString(strings['chart.with_notes'], {
        text: formatString(strings['chart.bar'], { series: 'Option B', group: 'El Nino', value: '11u' }),
        notes: 'over the limit',
      }),
    )
  })

  it('a missing value without a reason given says no value', () => {
    expect(barLabel(SERIES[0], groups[0], { value: null }, format)).toBe(
      formatString(strings['chart.bar_missing'], { series: 'Option A', group: 'Average', missing: strings['plant.table.no_value'] }),
    )
  })

  it('draws the reference line, labelled, and takes it into the scale', () => {
    const html = renderToString(
      <GroupedBarChart label="Soil" series={SERIES} groups={groups} format={format} reference={{ value: 600, label: 'Your limit 600' }} />,
    )
    expect(html).toContain('data-testid="chart-reference" data-value="600"')
    expect(decode(html)).toContain('Your limit 600')
    // The top tick reaches the reference, above every bar.
    expect(html).toContain('>600<')
  })

  it('draws a zero line only when values go negative', () => {
    const plain = renderToString(<GroupedBarChart label="M" series={SERIES} groups={groups} format={format} />)
    expect(plain).not.toContain('data-testid="chart-zero"')
    const negative: ChartGroup[] = [{ id: 'n', label: 'Neutral', values: [{ value: -40 }, { value: 80 }] }]
    const html = renderToString(<GroupedBarChart label="M" series={SERIES} groups={negative} format={format} />)
    expect(html).toContain('data-testid="chart-zero"')
  })

  it('marks the group looked at, the tag of a group and a flagged bar', () => {
    const html = renderToString(<GroupedBarChart label="M" series={SERIES} groups={groups} format={format} />)
    expect(count(html, 'data-testid="chart-emphasis"')).toBe(1)
    expect(count(html, 'data-testid="chart-group-tag"')).toBe(1)
    expect(count(html, 'data-testid="chart-flag"')).toBe(1)
  })

  it('names the chart for assistive technology and draws no tooltip until a bar is pointed at', () => {
    const html = renderToString(<GroupedBarChart label="Margin by kind" series={SERIES} groups={groups} format={format} />)
    expect(html).toContain('role="group" aria-label="Margin by kind"')
    expect(html).not.toContain('data-testid="chart-tooltip"')
  })
})

describe('the horizontal bar list', () => {
  it('draws a bar per present value, a hatched track for a missing one, and labels every row', () => {
    const html = renderToString(
      <BarList
        label="Areas"
        format={format}
        items={[
          { id: 'f1', label: 'Field 1', value: 41.2 },
          { id: 'f2', label: 'Field 2', value: null, missingText: 'no outline' },
        ]}
      />,
    )
    expect(count(html, 'data-testid="bar-list-bar"')).toBe(1)
    expect(count(html, 'data-testid="bar-list-missing"')).toBe(1)
    const said = labels(html)
    expect(said).toContain(formatString(strings['chart.row'], { name: 'Field 1', value: '41.2u' }))
    expect(said).toContain(formatString(strings['chart.row'], { name: 'Field 2', value: 'no outline' }))
    expect(count(html, 'data-testid="bar-list-tick"')).toBe(niceTicks(0, 41.2, 4).length)
  })
})
