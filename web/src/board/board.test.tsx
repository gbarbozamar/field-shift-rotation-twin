import { describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { exampleCase } from '../identity/exampleCase'
import { parsePlantAnswer } from '../plant/plantData'
import type { PlantAnswer, RainStressPart, TippingPrice } from '../plant/plantData'
import type { ServicePhase } from '../plant/PlantScreen'
import { buildRotationStrip, plantRotations } from '../plant/rotationStrip'
import { strings } from '../strings'
import { SORT_KEYS, answerChanges, unitText, boardCards, boardColumns, cropName, isExampleCrop, priceTrack, worstKind } from './boardModel'
import { CompareTable, cropsText, orderNote, uniformItem } from './CompareTable'
import { BoardView, initialBoardState } from './BoardScreen'
import { PriceTrackPanel } from './BoardParts'

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
    const letters = (sort: (typeof SORT_KEYS)[number]) =>
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
    expect(visibleText(`<${after(html, 'board-chosen').split('</p>')[0]}`)).toBe(
      formatString(strings['board.option_title'], {
        letter: String.fromCharCode(65 + rawExample.options.findIndex((o) => o.rotation_id === rawExample.chosen)),
        title: cropsText(buildRotationStrip(chosen))!,
      }),
    )
    const columns = html.split('data-testid="board-option"').slice(1)
    expect(columns.length).toBe(rawExample.options.length)
    boardColumns(example, 'rule').forEach((column, index) => {
      const header = columns[index].split('</th>')[0]
      expect(header).toContain(`data-state="${column.option.state}"`)
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

describe('quantities and required labels (5)', () => {
  const html = view(FIELD, answered(example))

  it('each kind of year carries the number of agricultural years of the record behind it', () => {
    const kinds = after(html, 'board-kind').split('</fieldset>')[0]
    const text = visibleText(`<${kinds}`)
    expect(text).toContain(
      formatString(strings['board.kind.years'], {
        kind: strings['board.kind.average'],
        n: rawExample.kinds_of_year.years.length,
      }),
    )
    for (const kind of ['el_nino', 'neutral', 'la_nina'] as const) {
      expect(text).toContain(
        formatString(strings['board.kind.years'], {
          kind: strings[`plant.kind.${kind}`],
          n: rawExample.kinds_of_year.counts[kind],
        }),
      )
    }
  })

  it('before an answer the kinds of year carry no number: none is assumed', () => {
    const kinds = after(view(FIELD, { phase: 'pending' }), 'board-kind').split('</fieldset>')[0]
    expect(visibleText(`<${kinds}`)).not.toMatch(/\d/)
  })

  it('the limit rule names the limit the request declares, with its unit', () => {
    const rule = after(html, 'board-rule').split('</fieldset>')[0]
    const limit = rawRequest.soil_loss_limit
    for (const key of ['on_average', 'every_kind'] as const) {
      expect(visibleText(`<${rule}`)).toContain(
        formatString(strings[`board.rule.${key}.limit`], { limit: displayNumber(limit.value), unit: unitText(limit.unit) }),
      )
    }
  })

  it('the record ribbon has one cell per agricultural year and the count of each kind', () => {
    const ribbon = after(html, 'board-record').split('</section>')[0]
    expect(count(ribbon, 'data-testid="board-record-year"')).toBe(rawExample.kinds_of_year.years.length)
    for (const kind of ['el_nino', 'neutral', 'la_nina'] as const) {
      expect(visibleText(`<${ribbon}`)).toContain(
        formatString(strings['board.record.count'], {
          kind: strings[`plant.kind.${kind}`],
          n: rawExample.kinds_of_year.counts[kind],
          total: rawExample.kinds_of_year.years.length,
        }),
      )
    }
    expect(visibleText(`<${ribbon}`)).toContain(strings['board.record.note'])
    expect(visibleText(`<${ribbon}`)).toContain(rawExample.kinds_of_year.source)
  })

  it('the banner keeps the scope of the answer in its own words (D245), not a shortened one', () => {
    expect(visibleText(`<${after(html, 'board-scope').split('</p>')[0]}`)).toBe(rawExample.scope)
  })

  it('the cost of the limit names the rotation it is measured against', () => {
    const against = example.options.find((o) => o.rotation_id === rawExample.limit_cost.against)!
    const letter = String.fromCharCode(65 + example.options.indexOf(against))
    const text = visibleText(`<${after(html, 'board-cost-against').split('</p>')[0]}`)
    expect(text).toBe(
      formatString(strings['board.cost.against'], {
        rotation: formatString(strings['board.option_title'], {
          letter,
          title: cropsText(buildRotationStrip(plantRotations.rotations!.find((r) => r.rotation_id === against.rotation_id)!))!,
        }),
      }),
    )
  })

  it('shows every limit the answer declares (D250)', () => {
    const limits = after(html, 'board-limits').split('</section>')[0]
    expect(count(limits, 'data-testid="board-declared-limit"')).toBe(rawExample.declared_limits.length)
    for (const limit of rawExample.declared_limits) {
      expect(visibleText(`<${limits}`)).toContain(formatString(strings['plant.declared_limit'], { limit }))
    }
  })

  it('every soil-loss figure carries the mark of its note, and the note says the label of D148 and its sources', () => {
    const table = after(html, 'board-compare').split('</table>')[0]
    const shown = example.options.flatMap((o) =>
      (['el_nino', 'neutral', 'la_nina'] as const).filter((kind) => o.soil_loss[kind].value !== null),
    ).length
    const main = example.options.filter((o) => o.soil_loss[example.margin_of].value !== null).length
    const margins = example.options.filter((o) => o.margin[example.margin_of].value !== null).length
    expect(count(table, 'data-testid="board-mark"')).toBe(shown + main + margins)
    const note = after(html, 'board-note-soil').split('</li>')[0]
    expect(decode(after(note, 'board-soil-label').split('</span>')[0])).toBe(`>${strings['soil_loss.headline_label']}`)
    for (const source of new Set(example.options.flatMap((o) => o.soil_loss[example.margin_of].sources))) {
      expect(decode(note)).toContain(source)
    }
    expect(decode(after(html, 'board-note-margin').split('</li>')[0])).toContain(strings['plant.source.economics'])
  })

  it('a number without a range says why, once, in its note', () => {
    const missing = example.options[0].margin[example.margin_of].labels!.range_missing!
    expect(decode(after(html, 'board-note-margin').split('</li>')[0])).toContain(
      missingPatternText(strings['board.no_range'], missing),
    )
    expect(count(html, 'data-testid="board-range"')).toBe(0)
  })

  it('a range the answer carries is shown under its number', () => {
    const kind = example.margin_of
    const first = example.options[0]
    const item = first.margin[kind]
    const ranged: PlantAnswer = {
      ...example,
      options: [
        {
          ...first,
          margin: {
            ...first.margin,
            [kind]: { ...item, labels: { ...item.labels!, range: { low: 1.5, high: 9.5, kind: 'RANGE_KIND_MARKER' }, range_missing: null } },
          },
        },
        ...example.options.slice(1),
      ],
    }
    const rendered = view(FIELD, answered(ranged))
    expect(count(rendered, 'data-testid="board-range"')).toBe(1)
    expect(decode(after(rendered, 'board-range').split('</span>')[0])).toContain(
      formatString(strings['value.range'], { low: displayNumber(1.5), high: displayNumber(9.5), kind: 'RANGE_KIND_MARKER' }),
    )
  })

  it('a row where every option holds the same value is said once, across the columns', () => {
    const kind = example.margin_of
    const one = example.options[0].soil_loss[kind]
    const same: PlantAnswer = {
      ...example,
      options: example.options.map((option) => ({ ...option, soil_loss: { ...option.soil_loss, [kind]: one } })),
    }
    const rendered = view(FIELD, answered(same))
    expect(count(rendered, 'data-testid="board-merged"')).toBe(1)
    expect(count(rendered, 'data-testid="board-bar-soil"')).toBe(0)
    expect(visibleText(after(rendered, 'board-merged').split('</td>')[0])).toContain(strings['board.same_for_all'])
    expect(count(view(FIELD, answered(example)), 'data-testid="board-merged"')).toBe(0)
    expect(uniformItem([one])).toBeNull()
  })

  it('a missing number says why, not only "no value"', () => {
    const missing = example.options.flatMap((o) => (o.soil_loss[example.margin_of].missing !== null ? [o.soil_loss[example.margin_of].missing!] : []))
    expect(missing.length).toBeGreaterThan(0)
    expect(decode(html)).toContain(missingPatternText(strings['plant.table.no_value'], missing[0]))
  })
})

describe('the rain stress test, as the service says it (6)', () => {
  const applied = { kind: 'applied', factor: 1.2, unit: 'dimensionless', detail: 'DETAIL_MARKER', label: 'stress test' } as const

  function withRain(part: RainStressPart | null): string {
    return view(FIELD, { phase: 'answered', answer: { answer: example, rainStress: part } })
  }

  it('no stress test asked: no line about it', () => {
    expect(count(withRain(null), 'data-testid="board-rain-echo"')).toBe(0)
  })

  it('applied: it says so with the detail of the service', () => {
    const html = withRain({ ...applied, applied: true })
    const echo = after(html, 'board-rain-echo').split('</p>')[0]
    expect(echo).toContain('data-applied="true"')
    expect(visibleText(`<${echo}`)).toBe(
      formatString(strings['plant.service.rain_applied'], { label: applied.label, detail: applied.detail }),
    )
  })

  it('asked but not applied: it says not applied, never as if it were', () => {
    const html = withRain({ ...applied, applied: false })
    const echo = after(html, 'board-rain-echo').split('</p>')[0]
    expect(echo).toContain('data-applied="false"')
    expect(visibleText(`<${echo}`)).toBe(
      formatString(strings['plant.service.rain_not_applied'], { label: applied.label, detail: applied.detail }),
    )
  })
})

describe('the other orders, ties and the worst kind of year (7)', () => {
  const kinds = ['el_nino', 'neutral', 'la_nina'] as const

  it('every order keeps every option, once', () => {
    for (const sort of SORT_KEYS) {
      const ids = boardColumns(example, sort).map((c) => c.option.rotation_id)
      expect([...ids].sort(), sort).toEqual(example.options.map((o) => o.rotation_id).sort())
    }
  })

  it('your order is the order of the answer, with no position', () => {
    const columns = boardColumns(example, 'yours')
    expect(columns.map((c) => c.option.rotation_id)).toEqual(example.options.map((o) => o.rotation_id))
    expect(columns.every((c) => c.position === null && !c.tied)).toBe(true)
  })

  it('the worst kind of year is the kind of the smallest margin among the kinds the record holds', () => {
    for (const option of example.options) {
      const raw = rawExample.options.find((o) => o.rotation_id === option.rotation_id)!
      const held = kinds.filter((kind) => rawExample.kinds_of_year.counts[kind] > 0)
      const smallest = Math.min(...held.map((kind) => raw.margin[kind].value as number))
      expect(raw.margin[worstKind(example, option)!].value).toBe(smallest)
    }
  })

  it('no worst kind is named when the record is not classified', () => {
    const unclassified: PlantAnswer = {
      ...example,
      kinds_of_year: { ...example.kinds_of_year, counts: { el_nino: null, neutral: null, la_nina: null } },
    }
    expect(example.options.every((option) => worstKind(unclassified, option) === null)).toBe(true)
    expect(boardColumns(unclassified, 'worst').every((c) => c.position === null)).toBe(true)
  })

  it('by the worst kind: the larger of those margins first', () => {
    const columns = boardColumns(example, 'worst')
    const values = columns.map((c) => c.option.margin[worstKind(example, c.option)!].value!)
    expect(values).toEqual([...values].sort((a, b) => b - a))
  })

  it('by kinds over the limit: the fewer first; an option with a kind not resolved has no position', () => {
    const columns = boardColumns(example, 'kinds_over')
    const placed = columns.filter((c) => c.position !== null)
    expect(placed.map((c) => c.option.kinds_not_met.length)).toEqual(
      [...placed.map((c) => c.option.kinds_not_met.length)].sort((a, b) => a - b),
    )
    for (const column of columns) {
      expect(column.position === null, column.option.rotation_id).toBe(column.option.kinds_not_resolved.length !== 0)
    }
  })

  it('options with the same value share a position and are marked tied', () => {
    const kind = example.margin_of
    const [first, second, ...rest] = example.options
    const same: PlantAnswer = {
      ...example,
      options: [first, { ...second, margin: { ...second.margin, [kind]: first.margin[kind] } }, ...rest],
    }
    const columns = boardColumns(same, 'margin')
    const tied = columns.filter((c) => c.option === same.options[0] || c.option === same.options[1])
    expect(tied.every((c) => c.tied)).toBe(true)
    expect(new Set(tied.map((c) => c.position)).size).toBe(1)
    expect(columns.filter((c) => !tied.includes(c)).every((c) => !c.tied)).toBe(true)
  })

  it('only the order of the rule gives a first place in the colour of the choice', () => {
    for (const sort of SORT_KEYS) {
      const html = renderToString(
        <CompareTable
          answer={example}
          columns={boardColumns(example, sort)}
          info={() => ({ rotation: null, strip: null })}
          order={[]}
          scales={{ margin: null, soilLoss: null }}
          sort={sort}
        />,
      )
      expect(count(html, 'data-testid="board-position" data-first="true"'), sort).toBe(sort === 'rule' ? 1 : 0)
    }
  })

  it('the price panel says what the answer becomes past a tipping point and how far it is from today', () => {
    const html = view(FIELD, answered(example))
    for (const direction of ['down', 'up'] as const) {
      const point = rawExample.tipping_price[direction]
      const line = after(html, `board-price-${direction}`).split('</li>')[0]
      if (point.price === null) {
        expect(count(line, 'data-testid="board-price-distance"')).toBe(0)
        continue
      }
      expect(visibleText(`<${line}`)).toContain(displayNumber(point.price))
      expect(visibleText(`<${line}`)).toContain(
        formatString(strings['plant.tip.distance'], { distance: displayNumber(point.distance_percent!) }),
      )
      if (point.answer_after !== 'chosen') {
        expect(visibleText(`<${line}`)).toContain(strings[`plant.after.${point.answer_after as 'not_resolved'}`])
      }
    }
  })
})

describe('the steps of the plan (8)', () => {
  it('the limit the request declares is shown as the user\'s own, with its unit and its declared mark', () => {
    const tile = after(view(null, null), 'board-your-limit').split('</div>')[0]
    const limit = rawRequest.soil_loss_limit
    expect(visibleText(`<${tile}`)).toContain(strings['board.limit.yours'])
    expect(visibleText(`<${tile}`)).toContain(`${displayNumber(limit.value)} ${unitText(limit.unit)}`)
    expect(visibleText(`<${tile}`)).toContain(strings['plant.declared'])
  })

  it('before an answer: the steps of the field and of the scenario; with an answer, all five in order', () => {
    const steps = (html: string) =>
      html.split('data-testid="board-step"').slice(1).map((part) => visibleText(`<${part.split('</h3>')[0]}`))
    expect(steps(view(null, null))).toEqual([`1 ${strings['board.step.field']}`, `2 ${strings['board.step.scenario']}`])
    expect(steps(view(FIELD, answered(example)))).toEqual([
      `1 ${strings['board.step.field']}`,
      `2 ${strings['board.step.scenario']}`,
      `3 ${strings['board.compare.title']}`,
      `4 ${strings['board.step.holds']}`,
      `5 ${strings['board.step.keep']}`,
    ])
  })

  it('the map is shown when open and left out when hidden; the list of the fields stays', () => {
    const map = <div data-testid="map-stand-in" />
    const render = (mapOpen: boolean) =>
      renderToString(
        <BoardView
          selectedFieldId={FIELD}
          state={initialBoardState()}
          apiBase={BASE}
          service={answered(example)}
          map={map}
          mapOpen={mapOpen}
          onToggleMap={() => {}}
        />,
      )
    expect(count(render(true), 'data-testid="map-stand-in"')).toBe(1)
    expect(count(render(false), 'data-testid="map-stand-in"')).toBe(0)
    expect(count(render(false), 'data-testid="board-fields"')).toBe(1)
    expect(visibleText(after(render(true), 'board-map-toggle').split('</button>')[0])).toContain(strings['board.map.hide'])
    expect(visibleText(after(render(false), 'board-map-toggle').split('</button>')[0])).toContain(strings['board.map.show'])
  })

  it('keeping the plan links to the printable sheet and to the full report', () => {
    const html = view(FIELD, answered(example))
    expect(after(html, 'board-print').split('>')[0]).toContain('href="#/print"')
    expect(after(html, 'board-report').split('>')[0]).toContain('href="#/plant"')
  })
})

describe('what changed between two answers (9)', () => {
  const open = answerOf('every_kind', 'average')

  it('the same answer: no change', () => {
    expect(answerChanges(example, example)).toEqual([])
  })

  it('names the change of the answer first, then each option whose state is another', () => {
    const changes = answerChanges(example, open)
    expect(changes[0]).toEqual({
      kind: 'answer',
      before: { answer: example.answer, chosen: example.chosen },
      after: { answer: open.answer, chosen: open.chosen },
    })
    const expected = open.options
      .map((option) => ({ option, was: example.options.find((o) => o.rotation_id === option.rotation_id)! }))
      .filter(({ option, was }) => was.state !== option.state)
      .map(({ option, was }) => ({ kind: 'state', rotation_id: option.rotation_id, before: was.state, after: option.state }))
    expect(changes.slice(1)).toEqual(expected)
    expect(expected.length).toBeGreaterThan(0)
  })

  it('an option that is in one answer only is not a change of state', () => {
    const fewer: PlantAnswer = { ...open, options: open.options.slice(0, 1) }
    expect(answerChanges(example, fewer).filter((c) => c.kind === 'state').length).toBeLessThanOrEqual(1)
  })

  it('the board says it once there is an answer before, and says nothing changed when nothing did', () => {
    const render = (previous: PlantAnswer | null) =>
      renderToString(
        <BoardView
          selectedFieldId={FIELD}
          state={initialBoardState()}
          apiBase={BASE}
          service={answered(open)}
          previous={previous}
        />,
      )
    expect(count(render(null), 'data-testid="board-changes"')).toBe(0)
    expect(count(render(example), 'data-testid="board-change"')).toBe(answerChanges(example, open).length)
    expect(visibleText(after(render(open), 'board-changes-none').split('</p>')[0])).toContain(strings['board.changed.none'])
  })
})

describe('names, the order note and a board that does not blank (10)', () => {
  it('one mark says the crops are example crops, and the legend reads them as names', () => {
    const html = view(FIELD, answered(example))
    expect(count(html, 'data-testid="board-example-crops"')).toBe(1)
    const legend = after(html, 'plant-legend').split('</ul>')[0]
    expect(visibleText(`<${legend}`)).not.toContain('PLACEHOLDER')
    expect(visibleText(`<${legend}`)).toContain(cropName(rawRequest.rotations[0].components[0].crop_id))
  })

  it('says so when the order picked cannot place the options', () => {
    const columns = (sort: (typeof SORT_KEYS)[number], answer: PlantAnswer = example) => boardColumns(answer, sort)
    const open = answerOf('every_kind', 'average')
    expect(orderNote(columns('margin'), 'margin')).toBeNull()
    expect(orderNote(columns('yours'), 'yours')).toBeNull()
    expect(orderNote(columns('rule', open), 'rule')).toBe(strings['board.sort.none_rule'])
    expect(orderNote(columns('rule'), 'rule')).toBeNull()
    const unplaced = columns('soil').filter((c) => c.position === null).length
    expect(unplaced).toBeGreaterThan(0)
    expect(orderNote(columns('soil'), 'soil')).toBe(formatString(strings['board.sort.some'], { n: unplaced }))
    const unclassified: PlantAnswer = {
      ...example,
      kinds_of_year: { ...example.kinds_of_year, counts: { el_nino: null, neutral: null, la_nina: null } },
    }
    expect(orderNote(columns('worst', unclassified), 'worst')).toBe(strings['board.sort.none'])
  })

  it('while a new answer is on its way the one before stays, marked as updating', () => {
    const render = (updating: boolean) =>
      renderToString(
        <BoardView
          selectedFieldId={FIELD}
          state={initialBoardState()}
          apiBase={BASE}
          service={answered(example)}
          updating={updating}
        />,
      )
    expect(count(render(true), 'data-testid="board-option"')).toBe(example.options.length)
    expect(render(true)).toContain('data-updating="true"')
    expect(visibleText(after(render(true), 'board-updating').split('</p>')[0])).toContain(strings['board.updating'])
    expect(count(render(false), 'data-testid="board-updating"')).toBe(0)
  })
})

describe('polish (11)', () => {
  it('the controls are shown but not offered when no field can be asked for', () => {
    const disabled = (html: string) => count(after(html, 'board-controls').split('</div></div>')[0], 'disabled=""')
    expect(disabled(view(null, null))).toBeGreaterThan(0)
    expect(disabled(view(OTHER_FIELD, null))).toBeGreaterThan(0)
    expect(disabled(view(FIELD, null, null))).toBeGreaterThan(0)
    expect(after(view(FIELD, answered(example)), 'board-kind').split('>')[0]).not.toContain('disabled=""')
  })

  it('the average carries no count when a year of the record has no kind', () => {
    const unclassified: PlantAnswer = {
      ...example,
      kinds_of_year: {
        ...example.kinds_of_year,
        years: example.kinds_of_year.years.map((year, index) => (index === 0 ? { ...year, kind: null } : year)),
        counts: { el_nino: null, neutral: null, la_nina: null },
      },
    }
    const kinds = after(view(FIELD, answered(unclassified)), 'board-kind').split('</fieldset>')[0]
    expect(visibleText(`<${kinds}`)).not.toMatch(/\d/)
  })

  it('each year of the ribbon carries the letter of its kind, not only its colour', () => {
    const ribbon = after(view(FIELD, answered(example)), 'board-record').split('</ol>')[0]
    const cells = ribbon.split('data-testid="board-record-year"').slice(1)
    rawExample.kinds_of_year.years.forEach((year, index) => {
      const letter = strings[`plant.kind.${year.kind as 'el_nino'}`].charAt(0).toUpperCase()
      expect(visibleText(`<${cells[index]}`)).toContain(`${letter} ${year.ag_year}`)
    })
  })
})

describe('units as they are read (12)', () => {
  it('a unit of the contract with wording is read with a slash; another is shown as it travels', () => {
    expect(unitText('t ha-1 yr-1')).toBe(strings['unit.t ha-1 yr-1'])
    expect(unitText('USD t-1')).toBe(strings['unit.USD t-1'])
    expect(unitText('UNIT_MARKER')).toBe('UNIT_MARKER')
  })

  it('the board shows the units of the example answer in that form, and never changes a number', () => {
    const html = decode(view(FIELD, answered(example)))
    expect(html).toContain(strings['unit.USD ha-1 yr-1'])
    expect(html).toContain(strings['unit.t ha-1 yr-1'])
    expect(html).toContain(displayNumber(example.options[0].margin[example.margin_of].value!))
  })
})

describe('the price the user looks at (13)', () => {
  const tipping = example.tipping_price
  const at = (price: number | null) =>
    renderToString(<PriceTrackPanel tipping={tipping} nameOf={(id) => id} initialPrice={price} />)
  const kindOf = (html: string) => after(html, 'board-price-at').split('>')[0]

  it('opens at the price of today, and says so', () => {
    const html = at(null)
    expect(kindOf(html)).toContain('data-at="today"')
    expect(visibleText(`<${after(html, 'board-price-at').split('</p>')[0]}`)).toBe(strings['plant.price.today'])
    expect(decode(html)).toContain(
      formatString(strings['plant.q.price_looked_at'], { price: displayNumber(tipping.today!), unit: unitText(tipping.unit) }),
    )
  })

  it('between today and a tipping price: the same answer; past it: what the service says it becomes', () => {
    for (const direction of ['down', 'up'] as const) {
      const point = tipping[direction]
      const end = direction === 'down' ? tipping.low : tipping.high
      if (point.price === null) {
        expect(kindOf(at(end))).toContain(
          `data-at="${point.missing.reason === 'NOT_APPLICABLE' ? 'same' : 'unknown'}"`,
        )
        continue
      }
      expect(kindOf(at((tipping.today! + point.price) / 2))).toContain('data-at="same"')
      const past = at(end)
      expect(kindOf(past)).toContain('data-at="past"')
      if (point.answer_after !== 'chosen') {
        expect(decode(past)).toContain(strings[`plant.after.${point.answer_after as 'not_resolved'}`])
      }
    }
  })
})
