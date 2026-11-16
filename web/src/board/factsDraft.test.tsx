import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { strings } from '../strings'
import { FactsEditor } from './FactsEditor'
import { applyFacts, changedFacts, factsProblems, readFactUnits, readFacts, sameFacts, withExtraCrops } from './factsDraft'

type Json = Record<string, unknown>

describe('the user’s own numbers', () => {
  const example = readFacts(rawRequest)

  it('reads the numbers the request declares, as declared', () => {
    expect(example.price).toBe(String(rawRequest.economic_facts.crops[0].price!.value))
    expect(example.limit).toBe(String(rawRequest.soil_loss_limit.value))
  })

  it('writes a draft into a copy of the request and leaves the request unchanged', () => {
    const before = JSON.stringify(rawRequest)
    const sent = applyFacts(rawRequest, { ...example, price: '450', limit: '5' })
    expect(JSON.stringify(rawRequest)).toBe(before)
    const grain = ((sent.economic_facts as Json).crops as Json[]).find((c) => c.kind === 'grain')!
    expect((grain.price as Json).value).toBe(450)
    expect((grain.price as Json).provenance).toBe('DECLARED')
    expect((sent.soil_loss_limit as Json).value).toBe(5)
  })

  it('the example numbers written back give the example request', () => {
    expect(applyFacts(rawRequest, example)).toEqual(rawRequest)
  })

  it('refuses what is not a number, a negative price or yield, a limit not above zero; a pasture loss is allowed', () => {
    const problems = factsProblems({
      ...example,
      price: '',
      yields: { ...example.yields, la_nina: '-1' },
      pasture: { ...example.pasture, la_nina: '-20' },
      limit: '0',
    })
    expect(problems).toEqual([
      { key: 'price', kind: 'not_a_number' },
      { key: 'yields.la_nina', kind: 'negative' },
      { key: 'limit', kind: 'not_positive' },
    ])
  })

  it('counts the changed numbers and compares as numbers', () => {
    expect(sameFacts(example, { ...example, price: `${example.price}.0` })).toBe(true)
    expect(changedFacts(example, { ...example, price: '1', cost: '2' })).toBe(2)
  })

  it('the editor says what is wrong and keeps compare off', () => {
    const html = renderToString(
      <FactsEditor draft={{ ...example, limit: '0' }} sent={example} units={readFactUnits(rawRequest)} onChange={() => {}} onCompare={() => {}} onReset={() => {}} />,
    )
    expect(html).toContain('data-testid="board-facts-problems"')
    expect(html).toMatch(/data-testid="board-facts-compare"[^>]*disabled/)
    expect(html).toContain(strings['board.facts.note'])
  })

  it('a crop the request has no facts for comes in empty, is a problem until typed, and is written like the soybean', () => {
    const withWheat = withExtraCrops(example, ['wheat'])
    expect(withWheat.extra.wheat.price).toBe('')
    expect(factsProblems(withWheat).some((p) => p.key === 'extra.wheat.price')).toBe(true)
    const typed = { ...withWheat, extra: { wheat: { price: '220', cost: '450', yields: { el_nino: '3', neutral: '3.5', la_nina: '2' } } } }
    expect(factsProblems(typed)).toEqual([])
    const sent = applyFacts(rawRequest, typed)
    const wheat = ((sent.economic_facts as Json).crops as Json[]).find((c) => c.crop_id === 'wheat')!
    expect(wheat.kind).toBe('grain')
    expect((wheat.price as Json).value).toBe(220)
    expect(((wheat.yield as Json).la_nina as Json).value).toBe(2)
    expect(withExtraCrops(typed, ['wheat']).extra.wheat.price).toBe('220')
    expect(withExtraCrops(typed, []).extra).toEqual({})
    expect(changedFacts(typed, example)).toBe(5)
  })

  it('the price range: read from the request, sent as typed, in order and around today\'s price', () => {
    expect(example.priceLow).toBe(String(rawRequest.questions.soybean_price_range.low))
    const sent = applyFacts(rawRequest, { ...example, priceLow: '150', priceHigh: '700' })
    expect(((sent.questions as Json).soybean_price_range as Json).high).toBe(700)
    expect(factsProblems({ ...example, priceLow: '500', priceHigh: '300' })).toContainEqual({ key: 'priceHigh', kind: 'range_order' })
    expect(factsProblems({ ...example, price: '650' })).toContainEqual({ key: 'price', kind: 'price_outside_range' })
  })

  it('the rain factor is a number above zero, sent with the comparison', () => {
    expect(example.rain).toBe(String(rawRequest.questions.rain_stress_factor.value))
    expect(factsProblems({ ...example, rain: '0' })).toContainEqual({ key: 'rain', kind: 'not_positive' })
    const sent = applyFacts(rawRequest, { ...example, rain: '1.5' })
    expect(((sent.questions as Json).rain_stress_factor as Json).value).toBe(1.5)
  })
})

