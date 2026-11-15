import { describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { missingPatternText } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import { parsePlantAnswer } from '../plant/plantData'
import type { PlantAnswer, TippingPrice } from '../plant/plantData'
import type { ServicePhase } from '../plant/PlantScreen'
import { plantRotations } from '../plant/rotationStrip'
import { strings } from '../strings'
import { boardCards, priceTrack } from './boardModel'
import { BoardView, initialBoardState } from './BoardScreen'

/**
 * Acceptance test of the rotation board (l3/board). PROPOSED. The view is
 * rendered with the pure server renderer, without the map. Every expected
 * number, order or count is read from the example answers and the example
 * request; every expected text is the wording of strings.ts.
 *
 * (1) the order and the places of the cards;
 * (2) the price track: where today and each tipping point fall, and what
 *     each side says;
 * (3) the view by state: no field picked, a field the request does not
 *     describe, no service, a call on its way, an answer.
 */

// leaflet needs a real browser window (importing it in node throws), so the
// map is replaced by nothing here: the view takes the map as a prop.
vi.mock('../map/FieldsMap', () => ({
  default: () => null,
}))

const FIELD = rawRequest.site.field_id
const OTHER_FIELD = exampleCase.fields.find((field) => field.field_id !== FIELD)!.field_id
const BASE = 'http://service.invalid'

function decode(html: string): string {
  return html
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function visibleText(html: string): string {
  return decode(html.replace(/<!-- -->/g, '').replace(/<[^>]+>/g, ' '))
    .replace(/\s+/g, ' ')
    .trim()
}

function count(html: string, needle: string): number {
  return html.split(needle).length - 1
}

function after(html: string, testid: string): string {
  const parts = html.split(`data-testid="${testid}"`)
  expect(parts.length, `testid ${testid}`).toBeGreaterThan(1)
  return parts[1]
}

const example: PlantAnswer = parsePlantAnswer(rawExample)

function answerOf(strictness: string, marginOf: string): PlantAnswer {
  return parsePlantAnswer(
    rawAnswers.answers.find((a) => a.questions.strictness === strictness && a.questions.margin_of === marginOf),
  )
}

function answered(answer: PlantAnswer): ServicePhase {
  return { phase: 'answered', answer: { answer, rainStress: null } }
}

function view(selectedFieldId: string | null, service: ServicePhase | null, apiBase: string | null = BASE): string {
  return renderToString(
    <BoardView selectedFieldId={selectedFieldId} state={initialBoardState()} apiBase={apiBase} service={service} />,
  )
}

describe('the order and the places of the cards (1)', () => {
  it('the chosen rotation is first with place 1; a rotation over the limit or not resolved has no place', () => {
    const cards = boardCards(example)
    expect(cards.length).toBe(rawExample.options.length)
    expect(cards[0].option.rotation_id).toBe(rawExample.chosen)
    expect(cards[0].rank).toBe(1)
    for (const card of cards) {
      const within = card.option.state === 'chosen' || card.option.state === 'meets'
      expect(card.rank === null, card.option.rotation_id).toBe(!within)
    }
  })

  it('the groups come in order: chosen, within the limit, not resolved, over the limit', () => {
    const order = { chosen: 0, meets: 1, not_resolved: 2, does_not_meet: 3 }
    const groups = boardCards(example).map((card) => order[card.option.state])
    expect(groups).toEqual([...groups].sort((a, b) => a - b))
  })

  it('rotations within the limit get no place when the answer chooses none of them (a tie)', () => {
    // The example answer, with its chosen rotation only within the limit and nothing chosen.
    const tied: PlantAnswer = {
      ...example,
      answer: 'not_resolved',
      chosen: null,
      options: example.options.map((option) => (option.state === 'chosen' ? { ...option, state: 'meets' } : option)),
    }
    expect(tied.options.some((option) => option.state === 'meets')).toBe(true)
    expect(boardCards(tied).every((card) => card.rank === null)).toBe(true)
  })

  it('an answer that chooses nothing gives no place to any card', () => {
    const open = answerOf('every_kind', 'average')
    expect(open.chosen).toBeNull()
    expect(boardCards(open).every((card) => card.rank === null)).toBe(true)
    expect(boardCards(open).length).toBe(open.options.length)
  })
})

describe('the price track (2)', () => {
  const tipping = example.tipping_price
  const percent = (price: number) => ((price - tipping.low) / (tipping.high - tipping.low)) * 100

  it('puts the price of today and each tipping point where they fall in the declared range', () => {
    const track = priceTrack(tipping)!
    expect(track.today).toBeCloseTo(percent(tipping.today!))
    for (const direction of ['down', 'up'] as const) {
      const point = tipping[direction]
      const side = track[direction]
      if (point.price !== null) {
        expect(side.kind).toBe('tips')
        expect(side.kind === 'tips' ? side.percent : null).toBeCloseTo(percent(point.price))
      } else {
        expect(side.kind).toBe(point.missing.reason === 'NOT_APPLICABLE' ? 'holds' : 'unknown')
      }
    }
    expect(track.holdsFrom).toBeLessThanOrEqual(track.today)
    expect(track.holdsTo).toBeGreaterThanOrEqual(track.today)
  })

  it('a side whose tipping point is missing for another reason is not computed: the answer is not said to hold there', () => {
    const unknown: TippingPrice = {
      ...tipping,
      up: { direction: 'up', price: null, missing: { reason: 'NOT_COMPUTABLE' }, unit: tipping.unit },
    }
    const track = priceTrack(unknown)!
    expect(track.up.kind).toBe('unknown')
    expect(track.holdsTo).toBeCloseTo(track.today)
  })

  it('no track without a price of today', () => {
    expect(priceTrack({ ...tipping, today: null, missing: { reason: 'NOT_DECLARED' } })).toBeNull()
  })
})

describe('the view by state (3)', () => {
  it('no field picked: the hint to pick one, the controls, and no card', () => {
    const html = view(null, null)
    expect(visibleText(after(html, 'board-pick'))).toContain(strings['map.select_hint'])
    expect(count(html, 'data-testid="board-controls"')).toBe(1)
    expect(count(html, 'data-testid="board-card"')).toBe(0)
    expect(count(html, 'data-testid="board-answer"')).toBe(0)
  })

  it('lists every field of the case; only the field the request describes has rotations declared', () => {
    const list = after(view(null, null), 'board-fields').split('</ul>')[0]
    for (const field of exampleCase.fields) {
      expect(visibleText(`<${list}`)).toContain(field.name)
    }
    expect(count(list, 'data-described="true"')).toBe(1)
    expect(count(visibleText(`<${list}`), strings['board.field.ready'])).toBe(1)
    expect(count(visibleText(`<${list}`), missingPatternText(strings['board.rotations'], { reason: 'NOT_DECLARED' }))).toBe(
      exampleCase.fields.length - 1,
    )
  })

  it('a field the request does not describe: rotations not declared, and no answer borrowed', () => {
    const html = view(OTHER_FIELD, answered(example))
    expect(visibleText(after(html, 'board-not-declared'))).toContain(
      missingPatternText(strings['board.rotations'], { reason: 'NOT_DECLARED' }),
    )
    expect(count(html, 'data-testid="board-card"')).toBe(0)
    expect(count(html, 'data-testid="board-answer"')).toBe(0)
  })

  it('no service configured: it says so and shows no answer (D251)', () => {
    const html = view(FIELD, answered(example), null)
    expect(visibleText(after(html, 'board-no-service'))).toContain(strings['plant.service.not_available'])
    expect(count(html, 'data-testid="board-card"')).toBe(0)
  })

  it('a call on its way: the pending line, no card', () => {
    const html = view(FIELD, { phase: 'pending' })
    expect(visibleText(after(html, 'plant-service-pending'))).toContain(strings['plant.service.pending'])
    expect(count(html, 'data-testid="board-card"')).toBe(0)
  })

  it('a failed call: the error panel with its code, no card', () => {
    const html = view(FIELD, { phase: 'failed', code: 'INTERNAL_ERROR' })
    expect(visibleText(after(html, 'plant-service-error'))).toContain(strings['plant.service.error.INTERNAL_ERROR'])
    expect(count(html, 'data-testid="board-card"')).toBe(0)
  })

  it('an answer: the banner names the chosen rotation, one card per option in board order, the chosen with place 1', () => {
    const html = view(FIELD, answered(example))
    const chosen = plantRotations.rotations!.find((r) => r.rotation_id === rawExample.chosen)!
    expect(visibleText(`<${after(html, 'board-chosen').split('</p>')[0]}`)).toBe(chosen.label)
    expect(count(html, 'data-testid="board-card"')).toBe(rawExample.options.length)
    const cards = html.split('data-testid="board-card"').slice(1)
    boardCards(example).forEach((card, index) => {
      expect(cards[index]).toContain(card.option.rotation_id)
      expect(cards[index]).toContain(`data-state="${card.option.state}"`)
    })
    expect(count(html, 'data-testid="board-rank"')).toBe(boardCards(example).filter((card) => card.rank !== null).length)
    expect(count(html, 'data-testid="board-rank" data-first="true"')).toBe(1)
    expect(count(html, 'data-testid="board-price-holds"')).toBe(1)
    expect(visibleText(after(html, 'board-report'))).toContain(strings['board.report'])
  })

  it('a missing number is "no value" on an empty meter, never 0', () => {
    const html = view(FIELD, answered(example))
    const cards = html.split('data-testid="board-card"').slice(1)
    boardCards(example).forEach((card, index) => {
      const margin = card.option.margin[example.margin_of].value
      const loss = card.option.soil_loss[example.margin_of].value
      const marginMeter = after(cards[index], 'board-meter-margin').split('>')[0]
      const soilMeter = after(cards[index], 'board-meter-soil').split('>')[0]
      expect(marginMeter, card.option.rotation_id).toContain(`data-empty="${String(margin === null)}"`)
      expect(soilMeter, card.option.rotation_id).toContain(`data-empty="${String(loss === null)}"`)
    })
  })

  it('a missing margin is an empty meter too', () => {
    const kind = example.margin_of
    const first = example.options[0]
    const without: PlantAnswer = {
      ...example,
      options: [
        {
          ...first,
          margin: {
            ...first.margin,
            [kind]: { value: null, unit: first.margin[kind].unit, missing: { reason: 'NOT_AVAILABLE' }, labels: null },
          },
        },
        ...example.options.slice(1),
      ],
    }
    const html = view(FIELD, answered(without))
    const card = html.split('data-testid="board-card"').slice(1).find((c) => c.includes(`>${first.rotation_id}<`))!
    expect(after(card, 'board-meter-margin').split('>')[0]).toContain('data-empty="true"')
    expect(visibleText(`<${card}`)).toContain(strings['plant.table.no_value'])
  })

  it('an answer that chooses nothing: the banner says so and no card has a place', () => {
    const open = answerOf('every_kind', 'average')
    const html = view(FIELD, answered(open))
    expect(visibleText(after(html, 'board-not-chosen'))).toContain(strings['plant.answer.not_resolved'])
    expect(count(html, 'data-testid="board-chosen"')).toBe(0)
    expect(count(html, 'data-testid="board-rank"')).toBe(0)
    // No source is unavailable in this answer, so the banner gives its reason.
    expect(visibleText(`<${after(html, 'board-why').split('</p>')[0]}`)).toBe(
      missingPatternText(strings['plant.answer.why'], open.missing!),
    )
    expect(count(html, 'data-testid="board-card"')).toBe(open.options.length)
  })
})
