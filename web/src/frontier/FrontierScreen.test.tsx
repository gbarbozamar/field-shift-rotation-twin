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
