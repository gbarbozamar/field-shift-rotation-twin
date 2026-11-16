import { describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { parsePlantAnswer, MARGINS_OF } from '../plant/plantData'
import type { PlantAnswer } from '../plant/plantData'
import type { ServicePhase } from '../plant/PlantScreen'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { BoardView, initialBoardState } from './BoardScreen'
import { BoardCharts } from './BoardCharts'
import { answerAttention, NO_ANSWER_ITEM } from './attention'

/**
 * Tests of the answer in charts, the KPI tiles and "Needs attention" on the
 * board (l3/original-mock). Every expected number or count is read from the
 * example answers; every expected text is the wording of strings.ts.
 */

vi.mock('../map/FieldsMap', () => ({ default: () => null }))

const FIELD = rawRequest.site.field_id
const example: PlantAnswer = parsePlantAnswer(rawExample)

function count(html: string, needle: string): number {
  return html.split(needle).length - 1
}

function after(html: string, testid: string): string {
  const parts = html.split(`data-testid="${testid}"`)
  expect(parts.length, testid).toBeGreaterThan(1)
  return parts[1]
}

function decode(html: string): string {
  return html.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&')
}

function answered(answer: PlantAnswer): ServicePhase {
  return { phase: 'answered', answer: { answer, rainStress: null } }
}

function view(answer: PlantAnswer, exampleNumbers = false): string {
  return renderToString(
    <BoardView selectedFieldId={FIELD} state={initialBoardState()} apiBase="http://service.invalid" service={answered(answer)} exampleNumbers={exampleNumbers} />,
  )
}

const nameOf = (id: string) => id

function charts(answer: PlantAnswer, mockKinds: readonly string[] = []): string {
  return renderToString(
    <BoardCharts answer={answer} options={answer.options} nameOf={nameOf} mockMarginKinds={mockKinds} mockSoilKinds={mockKinds} />,
  )
}

describe('the answer in charts', () => {
  it('the board shows two charts and the three KPI tiles of the chosen rotation', () => {
    const html = view(example)
    expect(html).toContain('data-testid="board-chart-margin"')
    expect(html).toContain('data-testid="board-chart-soil"')
    expect(count(html, 'data-testid="board-tile"')).toBe(3)
  })

  it('draws one slot per option and kind of year, a bar for each present value and a hatched slot for each missing one', () => {
    const html = charts(example)
    const margin = after(html, 'board-chart-margin').split('data-testid="board-chart-soil"')[0]
    const soil = after(html, 'board-chart-soil')
    const slots = example.options.length * MARGINS_OF.length
    const presentMargins = example.options.flatMap((o) => MARGINS_OF.map((k) => o.margin[k].value)).filter((v) => v !== null)
    const presentSoil = example.options.flatMap((o) => MARGINS_OF.map((k) => o.soil_loss[k].value)).filter((v) => v !== null)
    expect(count(margin, 'data-testid="chart-slot"')).toBe(slots)
    expect(count(margin, 'data-testid="chart-bar"')).toBe(presentMargins.length)
    expect(count(margin, 'data-testid="chart-missing"')).toBe(slots - presentMargins.length)
    expect(count(soil, 'data-testid="chart-bar"')).toBe(presentSoil.length)
    expect(count(soil, 'data-testid="chart-missing"')).toBe(slots - presentSoil.length)
  })

  it('every bar carries the value of the answer, exactly', () => {
    const html = charts(example)
    const soil = after(html, 'board-chart-soil')
    const drawn = [...soil.matchAll(/data-testid="chart-bar" data-value="([^"]+)"/g)].map((m) => Number(m[1]))
    const present = MARGINS_OF.flatMap((k) => example.options.map((o) => o.soil_loss[k].value)).filter((v): v is number => v !== null)
    expect(drawn).toEqual(present)
  })

  it('a missing soil loss is never drawn as a bar of zero, and its label says it has no value', () => {
    const missing = example.options.flatMap((o) => MARGINS_OF.map((k) => o.soil_loss[k])).filter((v) => v.value === null)
    const soil = decode(after(charts(example), 'board-chart-soil'))
    expect(soil).not.toContain('data-value="0"')
    if (missing.length !== 0) {
      expect(soil).toContain(strings['plant.table.no_value'])
    }
  })

  it('the soil-loss chart draws the user limit as a labelled reference line', () => {
    const limited = example.options.find((o) => o.limit !== null)!
    const soil = after(charts(example), 'board-chart-soil')
    expect(soil).toContain(`data-testid="chart-reference" data-value="${limited.limit}"`)
    expect(decode(soil)).toContain(formatString(strings['board.charts.limit'], { value: '' }).trim())
  })

  it('a soil loss over the limit is said in its label, not only in colour', () => {
    const over = example.options.some((o) => o.state === 'does_not_meet')
    const soil = decode(after(charts(example), 'board-chart-soil'))
    if (over) {
      expect(soil).toContain(strings['plant.table.over_limit'])
      expect(soil).toContain('data-testid="chart-flag"')
    }
  })

  it('the kinds of year filled with mock values carry the mock tag, in each chart', () => {
    const html = charts(example, ['el_nino'])
    expect(count(html, 'data-testid="chart-group-tag"')).toBe(2)
    expect(count(charts(example), 'data-testid="chart-group-tag"')).toBe(0)
  })

  it('the kind of year looked at is the emphasised group', () => {
    const html = charts(example)
    expect(count(html, 'data-testid="chart-emphasis"')).toBe(2)
  })
})

describe('needs attention', () => {
  it('names the options over the limit and leads to the candidates', () => {
    const items = answerAttention(example, { mocked: false, exampleNumbers: false, nameOf })
    const over = example.options.filter((o) => o.state === 'does_not_meet')
    const item = items.find((each) => each.id === 'over-limit')
    if (over.length === 0) {
      expect(item).toBeUndefined()
    } else {
      expect(item!.title).toBe(formatString(strings['attention.over_limit'], { n: over.length, total: example.options.length }))
      for (const option of over) expect(item!.detail).toContain(option.rotation_id)
      expect(item!.target).toBe('candidates')
    }
  })

  it('an answer not resolved gives its reason and leads to what to measure first', () => {
    const open = parsePlantAnswer(rawAnswers.answers.find((a) => a.questions.strictness === 'every_kind' && a.questions.margin_of === 'average'))
    expect(open.answer).toBe('not_resolved')
    const item = answerAttention(open, { mocked: false, exampleNumbers: false, nameOf }).find((each) => each.id === 'not-resolved')
    expect(item).toBeDefined()
    expect(item!.target).toBe('measure')
  })

  it('example numbers and mock values each give one item, only when true', () => {
    const none = answerAttention(example, { mocked: false, exampleNumbers: false, nameOf })
    const both = answerAttention(example, { mocked: true, exampleNumbers: true, nameOf })
    expect(both.length - none.length).toBe(2)
    expect(both.map((i) => i.id)).toContain('example-numbers')
    expect(both.map((i) => i.id)).toContain('mock')
  })

  it('each unavailable source gives an item that leads to the report', () => {
    const unavailable = example.sources.filter((s) => s.state === 'unavailable' && s.missing_reason !== null)
    const items = answerAttention(example, { mocked: false, exampleNumbers: false, nameOf }).filter((i) => i.id.startsWith('source-'))
    expect(items.length).toBe(unavailable.length)
    for (const item of items) expect(item.target).toBe('report')
  })

  it('the board shows the block with one card per item, each with its next step', () => {
    const items = answerAttention(example, { mocked: false, exampleNumbers: true, nameOf })
    const html = view(example, true)
    expect(html).toContain('data-testid="attention"')
    expect(count(html, 'data-testid="attention-item"')).toBe(items.length)
    expect(count(html, 'data-testid="attention-action"')).toBe(items.length)
  })

  it('the item of a case with no answer leads to the board', () => {
    expect(NO_ANSWER_ITEM.target).toBe('board')
    expect(NO_ANSWER_ITEM.action).toBe(strings['attention.open_board'])
  })
})
