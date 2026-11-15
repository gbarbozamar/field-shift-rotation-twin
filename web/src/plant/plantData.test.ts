import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import {
  MARGINS_OF,
  STRICTNESSES,
  answerAtPrice,
  parsePlantAnswer,
  parsePlantAnswers,
  plantExamples,
  selectAnswer,
} from './plantData'

/**
 * Acceptance test of the parser of the screen "What should I plant?" (S-019).
 * PROPOSED, designed before the screen.
 *
 * (5) the copied example equals the contract file, byte for byte, and the
 *     generated answer to the same questions equals it too;
 * (7) the parser refuses a value with a reason, and the other shapes the
 *     contract refuses on the parts the screen renders;
 * plus: the generated set holds one answer per combination of the questions,
 *     and the price looked at gives the answer of the tipping price function,
 *     never an extrapolation.
 */

const here = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(here, '..', '..')
const contractFile = resolve(
  webRoot,
  '..',
  'contracts',
  'plant_answer',
  'examples',
  'PLACEHOLDER_plant_answer.json',
)
const copyFile = resolve(webRoot, 'src', 'data', 'PLACEHOLDER_plant_answer.json')

/** A deep copy of the raw contract example, to change in memory. */
function exampleCopy(): Record<string, any> {
  return JSON.parse(JSON.stringify(rawExample))
}

describe('the copied example (5)', () => {
  it('equals the contract file', () => {
    expect(readFileSync(copyFile, 'utf8')).toBe(readFileSync(contractFile, 'utf8'))
  })

  it('equals the generated answer to the same questions', () => {
    const same = (rawAnswers.answers as unknown[]).filter((a) => {
      const q = (a as { questions: { strictness: string; margin_of: string } }).questions
      return q.strictness === 'on_average' && q.margin_of === 'average'
    })
    expect(same).toHaveLength(1)
    expect(same[0]).toEqual(JSON.parse(readFileSync(contractFile, 'utf8')))
  })
})

describe('the generated set of example answers', () => {
  it('is example data, and every answer is', () => {
    expect(plantExamples.example_data).toBe(true)
    expect(plantExamples.answers.every((a) => a.example_data)).toBe(true)
  })

  it('holds one answer per combination of strictness and kind of year', () => {
    for (const strictness of STRICTNESSES) {
      for (const marginOf of MARGINS_OF) {
        expect(selectAnswer(plantExamples, strictness, marginOf), `${strictness} ${marginOf}`).not.toBeNull()
      }
    }
    expect(plantExamples.answers).toHaveLength(STRICTNESSES.length * MARGINS_OF.length)
  })

  it('refuses two answers to the same questions', () => {
    const doc = { example_data: true, answers: [exampleCopy(), exampleCopy()] }
    expect(() => parsePlantAnswers(doc)).toThrow('two-answers-to-the-same-questions')
  })

  it('refuses an answer that is not example data in a set of example data', () => {
    const answer = exampleCopy()
    answer.example_data = false
    expect(() => parsePlantAnswers({ example_data: true, answers: [answer] })).toThrow(
      'answer-not-example-data',
    )
  })
})

describe('the parser refuses what the contract refuses (7)', () => {
  it('accepts the contract example', () => {
    const answer = parsePlantAnswer(exampleCopy())
    expect(answer.answer).toBe('chosen')
    expect(answer.chosen).toBe(rawExample.chosen)
  })

  it('refuses a soil-loss value with a reason', () => {
    const answer = exampleCopy()
    answer.options[0].soil_loss.average.reason = 'MISSING_INPUT'
    expect(() => parsePlantAnswer(answer)).toThrow('value-with-a-reason')
  })

  it('refuses a margin value with a reason', () => {
    const answer = exampleCopy()
    answer.options[1].margin.el_nino.reason = 'NOT_COMPUTABLE'
    expect(() => parsePlantAnswer(answer)).toThrow('value-with-a-reason')
  })

  it('refuses a missing value without its reason', () => {
    const answer = exampleCopy()
    answer.options[2].soil_loss.average.reason = null
    expect(() => parsePlantAnswer(answer)).toThrow('missing-without-a-reason')
  })

  it('refuses a chosen answer without a rotation', () => {
    const answer = exampleCopy()
    answer.chosen = null
    expect(() => parsePlantAnswer(answer)).toThrow('chosen-without-a-rotation')
  })

  it('refuses a rotation chosen when the answer is not chosen', () => {
    const answer = exampleCopy()
    answer.answer = 'not_resolved'
    expect(() => parsePlantAnswer(answer)).toThrow('rotation-chosen-when-the-answer-is-not')
  })

  it('refuses an answer that is not chosen without its reason', () => {
    const answer = exampleCopy()
    answer.answer = 'not_resolved'
    answer.chosen = null
    answer.options[1].state = 'meets'
    expect(() => parsePlantAnswer(answer)).toThrow('reason-exactly-when-nothing-is-chosen')
  })

  it('refuses the state chosen on another rotation than the chosen one', () => {
    const answer = exampleCopy()
    answer.options[0].state = 'chosen'
    expect(() => parsePlantAnswer(answer)).toThrow('state-chosen-not-on-the-chosen-rotation')
  })

  it('refuses none meets while an option is in another state', () => {
    const answer = exampleCopy()
    answer.answer = 'none_meets'
    answer.chosen = null
    answer.reason = 'NOT_APPLICABLE'
    answer.detail = rawExample.options[0].limit.on_average.verdict
    answer.options[1].state = 'meets'
    expect(() => parsePlantAnswer(answer)).toThrow('none-meets-with-an-option-in-another-state')
  })

  it('refuses a limit check that is not resolved without its reason', () => {
    const answer = exampleCopy()
    answer.options[2].limit_check.reason = null
    expect(() => parsePlantAnswer(answer)).toThrow('reason-exactly-when-not-resolved')
  })

  it('refuses a tipping point with a price and a reason', () => {
    const answer = exampleCopy()
    answer.tipping_price.down.reason = 'NOT_COMPUTABLE'
    answer.tipping_price.down.detail = answer.tipping_price.up.detail
    expect(() => parsePlantAnswer(answer)).toThrow('value-with-a-reason')
  })

  it('refuses a missing tipping point without its reason', () => {
    const answer = exampleCopy()
    answer.tipping_price.up.reason = null
    expect(() => parsePlantAnswer(answer)).toThrow('missing-without-a-reason')
  })

  it('refuses an option whose state is not the verdict of its limit check', () => {
    // The copy test (2) of PlantScreen.test.tsx used before fix round 1: every
    // state forced to does_not_meet while the limit checks stay as they are.
    const answer = exampleCopy()
    answer.answer = 'none_meets'
    answer.chosen = null
    answer.reason = 'NOT_APPLICABLE'
    answer.detail = rawExample.options.map((o) => o.rotation_id).join('; ')
    for (const option of answer.options) option.state = 'does_not_meet'
    answer.limit_cost = {
      ...answer.limit_cost,
      value: null,
      against: null,
      reason: 'NOT_APPLICABLE',
      detail: answer.detail,
    }
    expect(() => parsePlantAnswer(answer)).toThrow('state-not-the-verdict-of-its-check')
  })

  it('refuses a chosen option that does not meet the limit', () => {
    const answer = exampleCopy()
    const chosen = answer.options.find((o: { state: string }) => o.state === 'chosen')
    const doesNotMeet = { verdict: 'does_not_meet', reason: null, detail: null }
    chosen.limit.on_average = { ...doesNotMeet }
    chosen.limit_check = { ...doesNotMeet }
    expect(() => parsePlantAnswer(answer)).toThrow('chosen-does-not-meet-the-limit')
  })

  it('refuses a limit check that is not the check of the strictness used', () => {
    const answer = exampleCopy()
    answer.options[2].limit_check.detail = answer.options[2].limit.every_kind.detail
    expect(() => parsePlantAnswer(answer)).toThrow('limit-check-not-of-the-strictness')
  })

  it('refuses a limit check that is not resolved without its detail', () => {
    const answer = exampleCopy()
    answer.options[2].limit_check.detail = null
    expect(() => parsePlantAnswer(answer)).toThrow('detail-exactly-when-not-resolved')
  })

  it('refuses a missing limit cost without its detail', () => {
    const answer = exampleCopy()
    answer.answer = 'not_resolved'
    answer.chosen = null
    answer.reason = 'NOT_APPLICABLE'
    answer.detail = rawExample.options[2].limit_check.detail
    answer.options[1].state = 'meets'
    answer.limit_cost = {
      ...answer.limit_cost,
      value: null,
      against: null,
      reason: 'NOT_APPLICABLE',
      detail: null,
    }
    expect(() => parsePlantAnswer(answer)).toThrow('missing-without-a-detail')
  })

  it('refuses tied rotations fewer than two, or not all in state meets', () => {
    const answer = exampleCopy()
    answer.answer = 'not_resolved'
    answer.chosen = null
    answer.reason = 'NOT_APPLICABLE'
    answer.detail = rawExample.options[2].limit_check.detail
    answer.options[1].state = 'meets'
    answer.limit_cost = {
      ...answer.limit_cost,
      value: null,
      against: null,
      reason: 'NOT_APPLICABLE',
      detail: answer.detail,
    }
    // The copy without tied rotations is accepted, so each refusal below is the tied rule.
    expect(() => parsePlantAnswer(answer)).not.toThrow()
    answer.tied = [rawExample.options[1].rotation_id]
    expect(() => parsePlantAnswer(answer)).toThrow('tied-fewer-than-two')
    answer.tied = [rawExample.options[1].rotation_id, rawExample.options[0].rotation_id]
    expect(() => parsePlantAnswer(answer)).toThrow('tied-not-in-state-meets')
  })

  it('refuses a present soil loss with no source and no assumption mark', () => {
    const answer = exampleCopy()
    answer.options[0].soil_loss.el_nino.sources = []
    expect(() => parsePlantAnswer(answer)).toThrow('value-without-source-or-assumption')
  })
})

describe('the answer at a soybean price looked at', () => {
  const example = parsePlantAnswer(exampleCopy())
  const tipping = example.tipping_price
  const today = rawExample.tipping_price.today
  const down = rawExample.tipping_price.down.price
  const low = rawExample.tipping_price.price_range.low
  const high = rawExample.tipping_price.price_range.high

  it('is the answer of today at the price of today', () => {
    expect(answerAtPrice(tipping, today)).toEqual({ kind: 'today' })
  })

  it('is the answer of today between today and the tipping point', () => {
    expect(answerAtPrice(tipping, (today + down) / 2).kind).toBe('same')
  })

  it('is the answer_after of the tipping point past it, as the function computed it', () => {
    const at = answerAtPrice(tipping, low)
    expect(at.kind).toBe('past')
    if (at.kind === 'past') {
      expect(at.point.price).toBe(down)
      expect(at.point.answer_after).toBe(rawExample.tipping_price.down.answer_after)
    }
  })

  it('is the answer of today in a direction where no price in the range changes it', () => {
    // up is missing NOT_APPLICABLE in the example: no price in the range changes the answer.
    expect(rawExample.tipping_price.up.reason).toBe('NOT_APPLICABLE')
    expect(answerAtPrice(tipping, high).kind).toBe('same')
  })

  it('is unknown, with its reason, in a direction whose tipping point is missing for another reason', () => {
    const answer = exampleCopy()
    answer.tipping_price.up.reason = 'MISSING_INPUT'
    const at = answerAtPrice(parsePlantAnswer(answer).tipping_price, high)
    expect(at).toEqual({
      kind: 'unknown',
      missing: { reason: 'MISSING_INPUT', detail: rawExample.tipping_price.up.detail },
    })
  })
})
