import { afterEach, describe, expect, it, vi } from 'vitest'
import rawExamples from '../data/PLACEHOLDER_plant_answers.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { readPlantServiceAnswer } from '../plant/plantRoute'
import { exampleFor, fillPlantBody, isExampleRequest, mockFillOn, runPlantMixed } from './mockFill'
import { PlantNotAvailableError } from '../plant/plantRoute'

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
    const { body, mock } = fillPlantBody(noClimateBody(), example, rawRequest)
    expect(mock).toMatchObject({ whole: false, verdicts: true, refused: null })
    expect(mock.soilKinds).toEqual(['average', 'el_nino', 'neutral', 'la_nina'])
    const filled = body as Json
    expect(filled.chosen).toBe((example as Json).chosen)
    const option = (filled.options as Json[])[0]
    expect(((option.soil_loss as Record<string, Json>).average).value).not.toBeNull()
  })

  it('the filled body still passes the screen parser', () => {
    const { body } = fillPlantBody(noClimateBody(), example, rawRequest)
    expect(() => readPlantServiceAnswer(body, rawRequest)).not.toThrow()
  })

  it('refuses when a margin the backend computed differs from the example', () => {
    const real = noClimateBody()
    const margin = ((real.options as Json[])[0].margin as Record<string, Json>).neutral
    margin.value = (margin.value as number) + 1
    const { body, mock } = fillPlantBody(real, example, rawRequest)
    expect(mock.refused).toBe('incoherent')
    expect(mock.soilKinds).toEqual([])
    expect((body as Json).chosen).toBeNull()
  })

  it('fills a missing average margin and names its kind', () => {
    const real = noClimateBody()
    for (const option of real.options as Json[]) {
      const margins = option.margin as Record<string, Json>
      margins.average = { ...margins.average, value: null, reason: 'NOT_AVAILABLE', detail: 'kinds not classified' }
    }
    const { body, mock } = fillPlantBody(real, example, rawRequest)
    expect(mock.marginKinds).toEqual(['average'])
    const margins = ((body as Json).options as Json[])[0].margin as Record<string, Json>
    expect(margins.average.value).not.toBeNull()
  })

  it('refuses when no example answers the questions', () => {
    const { mock } = fillPlantBody(noClimateBody(), null, rawRequest)
    expect(mock.refused).toBe('no_example')
  })

  it('fills nothing when nothing is missing', () => {
    const complete = structuredClone((rawExamples as { answers: Json[] }).answers[0])
    expect(fillPlantBody(complete, example, rawRequest).mock).toMatchObject({ soilKinds: [], record: false, verdicts: false, refused: null })
  })

  it('does not change its arguments', () => {
    const real = noClimateBody()
    const before = JSON.stringify(real)
    fillPlantBody(real, example, rawRequest)
    expect(JSON.stringify(real)).toBe(before)
  })

  it('refuses when only the record is missing and the backend soil loss differs from the example', () => {
    const real = structuredClone((rawExamples as { answers: Json[] }).answers[0])
    const record = real.kinds_of_year as Json
    record.years = (record.years as Json[]).map((year) => ({ ...year, kind: null }))
    const loss = ((real.options as Json[])[0].soil_loss as Record<string, Json>).average
    loss.value = (loss.value as number) + 2
    const { body, mock } = fillPlantBody(real, example, rawRequest)
    expect(mock.refused).toBe('incoherent')
    expect((body as Json).chosen).toBe(real.chosen)
  })

  it('refuses for a request that is not the example request (edited rotations)', () => {
    const edited = structuredClone(rawRequest) as Json
    ;(edited.rotations as Json[])[0].rotation_id = 'user-rotation-1'
    expect(isExampleRequest(edited)).toBe(false)
    expect(fillPlantBody(noClimateBody(), example, edited).mock.refused).toBe('incoherent')
  })

  it('treats an empty record as not missing', () => {
    const real = structuredClone((rawExamples as { answers: Json[] }).answers[0])
    ;(real.kinds_of_year as Json).years = []
    expect(fillPlantBody(real, example, rawRequest).mock).toMatchObject({ record: false, refused: null })
  })

  it('each report is a new object: filling one never changes another', () => {
    const a = fillPlantBody({}, example, rawRequest).mock
    a.marginKinds.push('average')
    expect(fillPlantBody({}, example, rawRequest).mock.marginKinds).toEqual([])
  })
})

describe('runPlantMixed, whole answer', () => {
  const noAnswer = { answer: null, answer_missing: { reason: 'NOT_AVAILABLE', detail: 'plant layer not built' } }

  function stubFetch(body: unknown) {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })))
  }

  afterEach(() => vi.unstubAllGlobals())

  it('stands in the whole example for the example request, reported as whole', async () => {
    stubFetch(noAnswer)
    const answer = await runPlantMixed('http://service.invalid', structuredClone(rawRequest))
    expect(answer.mock?.whole).toBe(true)
  })

  it('does not stand in the example for edited rotations: the absence is kept', async () => {
    stubFetch(noAnswer)
    const edited = structuredClone(rawRequest) as Json
    ;(edited.rotations as Json[])[0].rotation_id = 'user-rotation-1'
    await expect(runPlantMixed('http://service.invalid', edited)).rejects.toBeInstanceOf(PlantNotAvailableError)
  })
})
