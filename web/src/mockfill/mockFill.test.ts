import { describe, expect, it } from 'vitest'
import rawExamples from '../data/PLACEHOLDER_plant_answers.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { readPlantServiceAnswer } from '../plant/plantRoute'
import { exampleFor, fillPlantBody, mockFillOn } from './mockFill'

type Json = Record<string, unknown>

/** A backend body like the one with no climate record: margins computed, soil loss and verdicts missing. */
function noClimateBody(): Json {
  const body = structuredClone((rawExamples as { answers: Json[] }).answers[0])
  for (const option of body.options as Json[]) {
    const losses = option.soil_loss as Record<string, Json>
    for (const kind of Object.keys(losses)) {
      losses[kind] = { ...losses[kind], value: null, reason: 'MISSING_INPUT', detail: 'no climate' }
    }
    option.state = 'not_resolved'
  }
  body.answer = 'not_resolved'
  body.chosen = null
  return body
}

describe('mock fill switch', () => {
  it('is on only for exactly "on"', () => {
    expect(mockFillOn({ VITE_MOCK_FILL: 'on' })).toBe(true)
    expect(mockFillOn({})).toBe(false)
    expect(mockFillOn({ VITE_MOCK_FILL: 'yes' })).toBe(false)
  })
})

describe('fillPlantBody', () => {
  const example = exampleFor(rawRequest)

  it('finds the example answer to the same questions', () => {
    expect(example).not.toBeNull()
  })

  it('fills the missing soil loss and takes the verdicts with it, and reports both', () => {
    const { body, mock } = fillPlantBody(noClimateBody(), example)
    expect(mock).toMatchObject({ whole: false, soil: true, verdicts: true, refused: null })
    const filled = body as Json
    expect(filled.chosen).toBe((example as Json).chosen)
    const option = (filled.options as Json[])[0]
    expect(((option.soil_loss as Record<string, Json>).average).value).not.toBeNull()
  })

  it('the filled body still passes the screen parser', () => {
    const { body } = fillPlantBody(noClimateBody(), example)
    expect(() => readPlantServiceAnswer(body, rawRequest)).not.toThrow()
  })

  it('refuses when a margin the backend computed differs from the example', () => {
    const real = noClimateBody()
    const margin = ((real.options as Json[])[0].margin as Record<string, Json>).neutral
    margin.value = (margin.value as number) + 1
    const { body, mock } = fillPlantBody(real, example)
    expect(mock.refused).toBe('incoherent')
    expect(mock.soil).toBe(false)
    expect((body as Json).chosen).toBeNull()
  })

  it('fills a missing average margin and names its kind', () => {
    const real = noClimateBody()
    for (const option of real.options as Json[]) {
      const margins = option.margin as Record<string, Json>
      margins.average = { ...margins.average, value: null, reason: 'NOT_AVAILABLE', detail: 'kinds not classified' }
    }
    const { body, mock } = fillPlantBody(real, example)
    expect(mock.marginKinds).toEqual(['average'])
    const margins = ((body as Json).options as Json[])[0].margin as Record<string, Json>
    expect(margins.average.value).not.toBeNull()
  })

  it('refuses when no example answers the questions', () => {
    const { mock } = fillPlantBody(noClimateBody(), null)
    expect(mock.refused).toBe('no_example')
  })

  it('fills nothing when nothing is missing', () => {
    const complete = structuredClone((rawExamples as { answers: Json[] }).answers[0])
    expect(fillPlantBody(complete, example).mock).toMatchObject({ soil: false, record: false, verdicts: false, refused: null })
  })

  it('does not change its arguments', () => {
    const real = noClimateBody()
    const before = JSON.stringify(real)
    fillPlantBody(real, example)
    expect(JSON.stringify(real)).toBe(before)
  })
})
