import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
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
  selectQuestions,
  startPrice,
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
  // The contract file comes with contracts/plant_answer (#424); until that is
  // on the base branch, the comparison with it is skipped, not failed.
  it.skipIf(!existsSync(contractFile))('equals the contract file', () => {
    expect(readFileSync(copyFile, 'utf8')).toBe(readFileSync(contractFile, 'utf8'))
  })

  it.skipIf(!existsSync(contractFile))('equals the generated answer to the same questions', () => {
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
      // a missing cost carries no D249 labels
      provenance: undefined,
      range_missing: undefined,
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
      // a missing cost carries no D249 labels
      provenance: undefined,
      range_missing: undefined,
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
      // a missing cost carries no D249 labels
      provenance: undefined,
      range_missing: undefined,
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

describe('the parser mirrors TippingPointOut and TippingPriceOut (code review fixes)', () => {
  const today = rawExample.tipping_price.today
  const low = rawExample.tipping_price.price_range.low
  const high = rawExample.tipping_price.price_range.high

  it('the example has a present tipping point down and a missing one up', () => {
    expect(rawExample.tipping_price.down.price).not.toBeNull()
    expect(rawExample.tipping_price.up.price).toBeNull()
    expect(rawExample.tipping_price.reason).toBeNull()
    expect(today).toBeGreaterThan(low)
    expect(today).toBeLessThan(high)
  })

  it('refuses a missing tipping price that still names a rotation, an answer or a distance', () => {
    for (const [field, value] of [
      ['takes_over', rawExample.options[0].rotation_id],
      ['answer_after', 'chosen'],
      ['distance_percent', rawExample.tipping_price.down.distance_percent],
    ] as const) {
      const answer = exampleCopy()
      answer.tipping_price.up[field] = value
      expect(() => parsePlantAnswer(answer), field).toThrow('missing-price-with-an-answer')
    }
  })

  it('refuses a missing tipping price whose reason comes without its detail', () => {
    const answer = exampleCopy()
    answer.tipping_price.up.detail = null
    expect(() => parsePlantAnswer(answer)).toThrow('reason-without-its-detail')
  })

  it('refuses a present tipping price with a detail and no reason', () => {
    const answer = exampleCopy()
    answer.tipping_price.down.detail = rawExample.tipping_price.up.detail
    expect(() => parsePlantAnswer(answer)).toThrow('reason-without-its-detail')
  })

  it('refuses a shared reason without its detail', () => {
    const answer = exampleCopy()
    answer.tipping_price.reason = rawExample.tipping_price.up.reason
    expect(() => parsePlantAnswer(answer)).toThrow('reason-without-its-detail')
  })

  it('refuses a shared reason that is not on both points', () => {
    const answer = exampleCopy()
    answer.tipping_price.reason = rawExample.tipping_price.up.reason
    answer.tipping_price.detail = rawExample.tipping_price.up.detail
    expect(() => parsePlantAnswer(answer)).toThrow('shared-reason-not-on-both-points')
  })

  it('accepts a shared reason on both points with no price of today', () => {
    const answer = exampleCopy()
    const up = rawExample.tipping_price.up
    answer.tipping_price.today = null
    // a missing today carries no D249 labels
    answer.tipping_price.provenance = undefined
    answer.tipping_price.range_missing = undefined
    answer.tipping_price.reason = up.reason
    answer.tipping_price.detail = up.detail
    answer.tipping_price.down = { ...up, direction: 'down' }
    const parsed = parsePlantAnswer(answer).tipping_price
    expect(parsed.today).toBeNull()
    expect(parsed.missing).toEqual({ reason: up.reason, detail: up.detail })
  })

  it("refuses today's price outside the range without a shared reason", () => {
    const answer = exampleCopy()
    answer.tipping_price.today = high + (high - low)
    expect(() => parsePlantAnswer(answer)).toThrow('today-outside-the-range-without-a-reason')
  })

  it('refuses a tipping price outside the range', () => {
    const answer = exampleCopy()
    answer.tipping_price.down.price = low - (high - low)
    expect(() => parsePlantAnswer(answer)).toThrow('tipping-price-outside-the-range')
  })

  it('refuses up.price below today', () => {
    const answer = exampleCopy()
    answer.tipping_price.up = { ...rawExample.tipping_price.down, direction: 'up' }
    expect(() => parsePlantAnswer(answer)).toThrow('up-price-below-today')
  })

  it('refuses down.price above today', () => {
    const answer = exampleCopy()
    answer.tipping_price.down.price = (today + high) / 2
    expect(() => parsePlantAnswer(answer)).toThrow('down-price-above-today')
  })

  it('refuses a distance of the wrong sign', () => {
    const answer = exampleCopy()
    const distance = rawExample.tipping_price.down.distance_percent
    expect(distance).not.toBe(0)
    answer.tipping_price.down.distance_percent = -distance
    expect(() => parsePlantAnswer(answer)).toThrow('distance-of-the-wrong-sign')
  })
})

describe('the parser mirrors LimitCostOut and the chosen rule (code review fixes)', () => {
  it('refuses a costs_nothing that is not a boolean', () => {
    for (const value of [null, 'false', 0]) {
      const answer = exampleCopy()
      answer.limit_cost.costs_nothing = value
      expect(() => parsePlantAnswer(answer), String(value)).toThrow('costs-nothing-not-a-flag')
    }
  })

  it('refuses a chosen answer with no option in state chosen', () => {
    const answer = exampleCopy()
    const chosen = answer.options.find((o: { state: string }) => o.state === 'chosen')
    chosen.state = chosen.limit_check.verdict
    expect(() => parsePlantAnswer(answer)).toThrow('state-chosen-not-on-the-chosen-rotation')
  })

  it('refuses an option in state chosen when the answer is not chosen', () => {
    const answer = exampleCopy()
    answer.answer = 'not_resolved'
    answer.chosen = null
    answer.reason = 'NOT_APPLICABLE'
    answer.detail = rawExample.options[2].limit_check.detail
    expect(() => parsePlantAnswer(answer)).toThrow('state-chosen-not-on-the-chosen-rotation')
  })
})

describe('the parser keeps the sources as SourceOut gives them (code review fixes)', () => {
  it('keeps the state, the attribution and the missing reason', () => {
    const parsed = parsePlantAnswer(exampleCopy()).sources
    expect(parsed).toEqual(
      rawExample.sources.map((s) => ({
        id: s.id,
        state: s.state,
        attribution: s.attribution,
        missing_reason: s.missing_reason,
        detail: s.detail,
      })),
    )
    const oni = rawExample.sources.find((s) => s.attribution !== null)
    expect(oni).toBeDefined()
  })

  it('refuses an unavailable source without its missing_reason', () => {
    const answer = exampleCopy()
    answer.sources[0].state = 'unavailable'
    expect(() => parsePlantAnswer(answer)).toThrow('unavailable-without-a-reason')
  })

  it('refuses a source of an unknown state, or with a reason that is not a code', () => {
    const answer = exampleCopy()
    answer.sources[0].state = 'stale'
    expect(() => parsePlantAnswer(answer)).toThrow('state-not-in-the-list')
    const other = exampleCopy()
    other.sources[0].missing_reason = 'GONE'
    expect(() => parsePlantAnswer(other)).toThrow('missing-reason-not-a-code')
  })
})

describe('the price looked at follows the answer selected (code review fixes)', () => {
  it("starts at the selected answer's price of today", () => {
    for (const strictness of STRICTNESSES) {
      for (const marginOf of MARGINS_OF) {
        const answer = selectAnswer(plantExamples, strictness, marginOf)!
        const q = selectQuestions(plantExamples, strictness, marginOf)
        expect(q).toEqual({ strictness, marginOf, price: answer.tipping_price.today })
      }
    }
  })

  it('is reset when another answer is selected, never carried from the previous one', () => {
    const low = rawExample.tipping_price.price_range.low
    const moved = { ...selectQuestions(plantExamples, 'on_average', 'average'), price: low }
    const next = selectQuestions(plantExamples, 'every_kind', moved.marginOf)
    const selected = selectAnswer(plantExamples, 'every_kind', 'average')!
    expect(next.price).toBe(selected.tipping_price.today)
    expect(next.price).not.toBe(moved.price)
    const back = selectQuestions(plantExamples, moved.strictness, 'la_nina')
    expect(back.price).toBe(selectAnswer(plantExamples, 'on_average', 'la_nina')!.tipping_price.today)
  })

  it('is kept inside the range, and null without a price of today', () => {
    const answer = parsePlantAnswer(exampleCopy())
    const { low, high } = answer.tipping_price
    const above = { ...answer, tipping_price: { ...answer.tipping_price, today: high + (high - low) } }
    const below = { ...answer, tipping_price: { ...answer.tipping_price, today: low - (high - low) } }
    const none = { ...answer, tipping_price: { ...answer.tipping_price, today: null } }
    expect(startPrice(above)).toBe(high)
    expect(startPrice(below)).toBe(low)
    expect(startPrice(none)).toBeNull()
    expect(startPrice(null)).toBeNull()
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

describe('the parser reads the D249 labels of #424 strictly', () => {
  it('reads the labels of a margin, the limit, the cost, the tipping point and its distance', () => {
    const parsed = parsePlantAnswer(exampleCopy())
    const option = parsed.options[0]
    expect(option.margin.average.labels?.provenance).toBe('DERIVED')
    expect(option.limit).toBe(rawExample.options[0].limit.limit.value)
    expect(option.limit_labels?.provenance).toBe('DECLARED')
    expect(option.limit_missing).toBeNull()
    expect(parsed.tipping_price.range_provenance).toBe('DECLARED')
    const down = parsed.tipping_price.down
    expect(down.price === null ? null : down.distance_labels?.provenance).toBe('DERIVED')
    expect(parsed.scope.length).toBeGreaterThan(0)
    expect(parsed.declared_limits.length).toBeGreaterThan(0)
  })

  it('refuses a present margin without its source or its provenance', () => {
    const noSource = exampleCopy()
    delete noSource.options[0].margin.average.source
    expect(() => parsePlantAnswer(noSource)).toThrow('source-not-the-margin-source')
    const noProvenance = exampleCopy()
    delete noProvenance.options[0].margin.average.provenance
    expect(() => parsePlantAnswer(noProvenance)).toThrow('provenance-not-a-label')
  })

  it('refuses a present value with both a range and range_missing, or with neither', () => {
    const neither = exampleCopy()
    delete neither.limit_cost.range_missing
    expect(() => parsePlantAnswer(neither)).toThrow('range-or-range-missing-exactly-one')
    const both = exampleCopy()
    both.limit_cost.range = { low: 0, high: 1000, kind: 'PLACEHOLDER_kind' }
    expect(() => parsePlantAnswer(both)).toThrow('range-or-range-missing-exactly-one')
  })

  it('refuses a tipping distance without its labels', () => {
    const answer = exampleCopy()
    delete answer.tipping_price.down.distance_provenance
    expect(() => parsePlantAnswer(answer)).toThrow('distance:provenance-not-a-label')
  })

  it('keeps a missing limit missing with its reason, never zero', () => {
    const answer = exampleCopy()
    const option = answer.options[0]
    const open = { verdict: 'not_resolved', reason: 'NOT_DECLARED', detail: 'PLACEHOLDER detail' }
    option.limit.limit = { value: null, unit: option.limit.unit, missing: { reason: 'NOT_DECLARED' } }
    option.limit.on_average = { ...open }
    option.limit.every_kind = { ...open }
    option.limit_check = { ...open }
    option.state = 'not_resolved'
    const parsed = parsePlantAnswer(answer).options[0]
    expect(parsed.limit).toBeNull()
    expect(parsed.limit_missing).toEqual({ reason: 'NOT_DECLARED' })
    const present = exampleCopy()
    present.options[0].limit.limit.provenance = 'DERIVED'
    expect(() => parsePlantAnswer(present)).toThrow('limit:limit:provenance-not-DECLARED')
  })

  it('refuses a price range not declared', () => {
    const answer = exampleCopy()
    answer.tipping_price.price_range.provenance = 'DERIVED'
    expect(() => parsePlantAnswer(answer)).toThrow('price-range-not-declared')
  })
})

describe('the parser reads the D249 labels of #424 strictly: four more checks', () => {
  it('refuses a missing value that carries labels', () => {
    const answer = exampleCopy()
    const item = answer.options[0].margin.average
    item.value = null
    item.reason = 'NOT_COMPUTABLE'
    item.detail = 'PLACEHOLDER detail'
    delete item.source
    // provenance and range_missing are kept: a missing value carries none of them
    expect(() => parsePlantAnswer(answer)).toThrow('margin:average:missing-value-with-labels')
  })

  it("refuses a missing tipping point's distance that carries labels", () => {
    const answer = exampleCopy()
    const down = answer.tipping_price.down
    expect(down.price).not.toBeNull()
    down.distance_percent = null
    down.reason = 'NOT_COMPUTABLE'
    down.detail = 'PLACEHOLDER detail'
    // distance_provenance and distance_range_missing are kept
    expect(() => parsePlantAnswer(answer)).toThrow('down:distance:missing-value-with-labels')
    delete down.distance_provenance
    delete down.distance_range_missing
    const parsed = parsePlantAnswer(answer).tipping_price.down
    expect(parsed.price === null ? 'no price' : parsed.distance_labels).toBeNull()
  })

  it("reads the labels of today's price", () => {
    const parsed = parsePlantAnswer(exampleCopy()).tipping_price
    const raw = rawExample.tipping_price
    expect(parsed.today).toBe(raw.today)
    expect(parsed.today_labels).toEqual({
      provenance: raw.provenance,
      range: null,
      range_missing: raw.range_missing,
    })
  })

  it('refuses a value outside its range', () => {
    const answer = exampleCopy()
    delete answer.limit_cost.range_missing
    answer.limit_cost.range = { low: answer.limit_cost.value + 1, high: answer.limit_cost.value + 2, kind: 'PLACEHOLDER_kind' }
    expect(() => parsePlantAnswer(answer)).toThrow('limit-cost:value-outside-its-range')
    answer.limit_cost.range = { low: answer.limit_cost.value - 1, high: answer.limit_cost.value + 1, kind: 'PLACEHOLDER_kind' }
    expect(parsePlantAnswer(answer).limit_cost).toMatchObject({ kind: 'value' })
  })
})
