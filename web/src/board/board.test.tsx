import { describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { exampleCase } from '../identity/exampleCase'
import { parsePlantAnswer } from '../plant/plantData'
import type { PlantAnswer, TippingPrice } from '../plant/plantData'
import type { ServicePhase } from '../plant/PlantScreen'
import { buildRotationStrip, plantRotations } from '../plant/rotationStrip'
import { strings } from '../strings'
import { boardCards, boardColumns, cropName, isExampleCrop, priceTrack } from './boardModel'
import { cropsText } from './CompareTable'
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
 * (3) the order picked for the columns, and the names of the crops;
 * (4) the view by state: no field picked, a field the request does not
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

describe('the order picked and the names (3)', () => {
  const kind = example.margin_of

  it('by the rule: the order and the places of the answer', () => {
    const columns = boardColumns(example, 'rule')
    expect(columns.map((c) => c.option.rotation_id)).toEqual(boardCards(example).map((c) => c.option.rotation_id))
    expect(columns.map((c) => c.position)).toEqual(boardCards(example).map((c) => c.rank))
  })

  it('by margin: the larger margin first; by soil loss: the smaller first; a missing value last and without a position', () => {
    for (const [sort, values, direction] of [
      ['margin', (id: string) => example.options.find((o) => o.rotation_id === id)!.margin[kind].value, -1],
      ['soil', (id: string) => example.options.find((o) => o.rotation_id === id)!.soil_loss[kind].value, 1],
    ] as const) {
      const columns = boardColumns(example, sort)
      expect(columns.length).toBe(example.options.length)
      const read = columns.map((c) => values(c.option.rotation_id))
      const present = read.filter((v): v is number => v !== null)
      expect(read.slice(0, present.length), sort).toEqual(present)
      expect(present, sort).toEqual([...present].sort((a, b) => direction * (a - b)))
      columns.forEach((column, index) => {
        expect(column.position, sort).toBe(read[index] !== null ? index + 1 : null)
      })
    }
  })

  it('the example answer has a missing soil loss, so the soil order is exercised with one', () => {
    expect(example.options.some((o) => o.soil_loss[kind].value === null)).toBe(true)
  })

  it('a letter belongs to an option whatever the order', () => {
    const letters = (sort: 'rule' | 'margin' | 'soil') =>
      Object.fromEntries(boardColumns(example, sort).map((c) => [c.option.rotation_id, c.letter]))
    expect(letters('margin')).toEqual(letters('rule'))
    expect(letters('soil')).toEqual(letters('rule'))
    expect(Object.values(letters('rule')).sort()).toEqual(['A', 'B', 'C'].slice(0, example.options.length))
  })

  it('a crop id reads as a name: the placeholder marker dropped, underscores as spaces', () => {
    expect(cropName('PLACEHOLDER_cover_crop')).toBe('cover crop')
    expect(cropName('wheat')).toBe('wheat')
    for (const rotation of plantRotations.rotations!) {
      const text = cropsText(buildRotationStrip(rotation))!
      expect(text).not.toContain('PLACEHOLDER')
      for (const component of rotation.components) {
        expect(text).toContain(cropName(component.crop_id))
      }
    }
    expect(cropsText(null)).toBeNull()
    expect(isExampleCrop('PLACEHOLDER_soybean')).toBe(true)
    expect(isExampleCrop('soybean')).toBe(false)
  })
})

describe('the view by state (4)', () => {
  it('no field picked: the hint to pick one, the controls, and no option', () => {
    const html = view(null, null)
    expect(visibleText(after(html, 'board-pick'))).toContain(strings['map.select_hint'])
    expect(count(html, 'data-testid="board-controls"')).toBe(1)
    expect(count(html, 'data-testid="board-option"')).toBe(0)
    expect(count(html, 'data-testid="board-answer"')).toBe(0)
  })

  it('the rain stress test names the factor the request declares, not a vague word', () => {
    const factor = rawRequest.questions.rain_stress_factor.value
    const rain = after(view(null, null), 'board-rain').split('</fieldset>')[0]
    expect(visibleText(`<${rain}`)).toContain(
      formatString(strings['board.rain.factor'], { factor: displayNumber(factor) }),
    )
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
    expect(count(html, 'data-testid="board-option"')).toBe(0)
    expect(count(html, 'data-testid="board-answer"')).toBe(0)
  })

  it('no service configured: it says so and shows no answer (D251)', () => {
    const html = view(FIELD, answered(example), null)
    expect(visibleText(after(html, 'board-no-service'))).toContain(strings['plant.service.not_available'])
    expect(count(html, 'data-testid="board-option"')).toBe(0)
  })

  it('a call on its way: the pending line, no option', () => {
    const html = view(FIELD, { phase: 'pending' })
    expect(visibleText(after(html, 'plant-service-pending'))).toContain(strings['plant.service.pending'])
    expect(count(html, 'data-testid="board-option"')).toBe(0)
  })

  it('a failed call: the error panel with its code, no option', () => {
    const html = view(FIELD, { phase: 'failed', code: 'INTERNAL_ERROR' })
    expect(visibleText(after(html, 'plant-service-error'))).toContain(strings['plant.service.error.INTERNAL_ERROR'])
    expect(count(html, 'data-testid="board-option"')).toBe(0)
  })

  it('an answer: the banner names the crops of the chosen rotation; one column per option in the order of the rule, the chosen first', () => {
    const html = view(FIELD, answered(example))
    const chosen = plantRotations.rotations!.find((r) => r.rotation_id === rawExample.chosen)!
    expect(visibleText(`<${after(html, 'board-chosen').split('</p>')[0]}`)).toBe(cropsText(buildRotationStrip(chosen)))
    const columns = html.split('data-testid="board-option"').slice(1)
    expect(columns.length).toBe(rawExample.options.length)
    boardColumns(example, 'rule').forEach((column, index) => {
      const header = columns[index].split('</th>')[0]
      expect(header).toContain(`data-state="${column.option.state}"`)
      expect(header).toContain('data-testid="board-example-crops"')
      expect(visibleText(`<${header}`)).toContain(formatString(strings['board.option'], { letter: column.letter }))
      expect(count(header, 'data-testid="board-position"')).toBe(column.position !== null ? 1 : 0)
    })
    expect(count(html, 'data-testid="board-position" data-first="true"')).toBe(1)
    expect(count(html, 'data-testid="board-price-holds"')).toBe(1)
    expect(visibleText(after(html, 'board-report'))).toContain(strings['board.report'])
  })

  it('no column is named by the label of the example request: the crops name it', () => {
    const table = after(view(FIELD, answered(example)), 'board-compare').split('</table>')[0]
    for (const rotation of plantRotations.rotations!) {
      expect(visibleText(`<${table}`)).not.toContain(rotation.label)
    }
  })

  it('a missing number is "no value" on an empty bar, never 0', () => {
    const html = view(FIELD, answered(example))
    const columns = boardColumns(example, 'rule')
    for (const [testid, values] of [
      ['board-bar-margin', columns.map((c) => c.option.margin[example.margin_of].value)],
      ['board-bar-soil', columns.map((c) => c.option.soil_loss[example.margin_of].value)],
    ] as const) {
      const bars = html.split(`data-testid="${testid}"`).slice(1)
      expect(bars.length).toBe(columns.length)
      values.forEach((value, index) => {
        expect(bars[index].split('>')[0], `${testid} ${index}`).toContain(`data-empty="${String(value === null)}"`)
      })
    }
  })

  it('a missing margin is an empty bar too', () => {
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
    const index = boardColumns(without, 'rule').findIndex((c) => c.option.rotation_id === first.rotation_id)
    const bar = html.split('data-testid="board-bar-margin"').slice(1)[index]
    expect(bar.split('>')[0]).toContain('data-empty="true"')
  })

  it('an answer that chooses nothing: the banner says so with its reason, and no option has a position', () => {
    const open = answerOf('every_kind', 'average')
    const html = view(FIELD, answered(open))
    expect(visibleText(after(html, 'board-not-chosen'))).toContain(strings['plant.answer.not_resolved'])
    expect(count(html, 'data-testid="board-chosen"')).toBe(0)
    expect(count(html, 'data-testid="board-position"')).toBe(0)
    // No source is unavailable in this answer, so the banner gives its reason.
    expect(visibleText(`<${after(html, 'board-why').split('</p>')[0]}`)).toBe(
      missingPatternText(strings['plant.answer.why'], open.missing!),
    )
    expect(count(html, 'data-testid="board-option"')).toBe(open.options.length)
  })
})
