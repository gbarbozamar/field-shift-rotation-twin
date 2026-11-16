import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import FrontierScreen from './FrontierScreen'
import PlanPanel from './PlanPanel'
import { M, rotationRisk, tippingPrice, verdictAt, voiAt } from './model'

describe('frontier showcase', () => {
  it('shows the synthetic-scenario badge', () => {
    expect(renderToStaticMarkup(<FrontierScreen />)).toContain('Illustrative Synthetic Scenario')
  })
  it('renders the plan view', () => {
    expect(renderToStaticMarkup(<PlanPanel />)).toContain('Soil use and management plan summary')
  })
  it('the monthly clocks cover twelve months and the erosive share sums to 100', () => {
    expect(M.clocks.rain).toHaveLength(12)
    expect(M.clocks.rain.reduce((a, b) => a + b, 0)).toBe(100)
  })
  it('verdict follows the price: far from tipping is robust, between the tipping points abstains or is conditional', () => {
    expect(verdictAt(420)).toBe('robust')
    expect(verdictAt(250)).toBe('robust')
    expect(verdictAt(M.price.default)).toBe('conditional')
    expect(verdictAt(Math.round((tippingPrice(false) + tippingPrice(true)) / 2))).toBe('abstain')
  })
  it('value of information is largest near a tipping point', () => {
    expect(voiAt(10, tippingPrice(false))).toBeGreaterThan(voiAt(10, 420))
  })
  it('flowering risk is computed from the month counts', () => {
    expect(['low', 'medium', 'high']).toContain(rotationRisk(0))
  })
})

describe('every synthetic card says so on itself', async () => {
  const { strings } = await import('../strings')
  const PreloadPanel = (await import('./PreloadPanel')).default
  it('the preload cards each carry the synthetic mark; the plan carries no signature line', () => {
    const html = renderToStaticMarkup(<PreloadPanel />)
    expect((html.match(/data-testid="frontier-synthetic-tag"/g) ?? []).length).toBeGreaterThanOrEqual(4)
    const plan = renderToStaticMarkup(<PlanPanel />)
    expect(plan).toContain(strings['frontier.p5.plan.not_official'])
    expect(plan).not.toContain('Signed by')
  })
})
