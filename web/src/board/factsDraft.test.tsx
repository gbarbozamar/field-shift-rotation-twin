import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { strings } from '../strings'
import { FactsEditor } from './FactsEditor'
import { applyFacts, changedFacts, factsProblems, readFactUnits, readFacts, sameFacts } from './factsDraft'

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
    expect(html).toContain(strings['board.facts.title'])
  })
})
