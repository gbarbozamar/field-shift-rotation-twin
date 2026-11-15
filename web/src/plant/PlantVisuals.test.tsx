import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import { missingPatternText } from '../components/ValueDisplay'
import { strings } from '../strings'
import { PlantView } from './PlantScreen'
import { parsePlantAnswers, plantExamples } from './plantData'
import type { PlantAnswerSet } from './plantData'
import { buildRotationStrip, plantRotations } from './rotationStrip'
import { buildTimeline } from './timeline'

/**
 * Acceptance test of the visual layer of the screen "What should I plant?"
 * (l3/plant-redesign). PROPOSED. Rendered with the pure server renderer, as
 * the other tests of the screen. Every expected number or count is read from
 * the example answer and the example request; every expected text is the
 * wording of strings.ts.
 *
 * (1) each option carries its state pill and a timeline with one bar per
 *     crop of its definition;
 * (2) the table by kind of year marks "over the limit" exactly where the
 *     answer says the soil loss does not meet the limit, and shows "no
 *     value", never 0, where a number is missing;
 * (3) the card shows the label of the chosen rotation and its figures;
 * (4) the sources an answer lacks are said once, in a notice, and only when
 *     a source is unavailable.
 */

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

function optionRow(html: string, index: number): string {
  const parts = html.split('data-testid="plant-option"')
  expect(parts.length - 1).toBeGreaterThan(index)
  return parts[index + 1].split('</article>')[0]
}

function card(html: string): string {
  return html.split('data-testid="plant-card"')[1].split('</article>')[0]
}

function render(set: PlantAnswerSet = plantExamples): string {
  return renderToString(
    <PlantView set={set} strictness="on_average" marginOf="average" price={rawExample.tipping_price.today} />,
  )
}

const rotations = plantRotations.rotations!
const KINDS = ['el_nino', 'neutral', 'la_nina'] as const

describe('each option carries its pill and its timeline (1)', () => {
  const html = render()

  it('shows the short state label of its state', () => {
    rawExample.options.forEach((option, index) => {
      const row = optionRow(html, index)
      expect(row).toContain(`data-state="${option.state}"`)
      const pill = row.split('data-testid="plant-pill"')[1].split('</span>')[0]
      expect(visibleText(`<${pill}`)).toBe(strings[`plant.pill.${option.state as 'chosen'}`])
    })
  })

  it('draws one bar per crop of the definition, open-ended where the harvest date is missing', () => {
    rawExample.options.forEach((option, index) => {
      const row = optionRow(html, index)
      const rotation = rotations.find((r) => r.rotation_id === option.rotation_id)!
      const timeline = buildTimeline(buildRotationStrip(rotation))
      expect(timeline.bars.length).toBe(rotation.components.filter((c) => c.sowing.date !== null).length)
      expect(count(row, 'data-testid="plant-timeline-bar"')).toBe(timeline.bars.length)
      expect(count(row, 'data-open-end="true"')).toBe(
        rotation.components.filter((c) => c.sowing.date !== null && c.harvest.date === null).length,
      )
    })
  })
})

describe('the table by kind of year (2)', () => {
  const html = render()

  it('marks "over the limit" exactly where the answer says the soil loss does not meet the limit', () => {
    rawExample.options.forEach((option, index) => {
      const table = optionRow(html, index).split('data-testid="plant-kind-table"')[1].split('</table>')[0]
      const onAverage = option.limit.on_average.verdict === 'does_not_meet' && option.soil_loss.average.value !== null
      const kinds = KINDS.filter(
        (kind) => (option.limit.kinds_not_met as string[]).includes(kind) && option.soil_loss[kind].value !== null,
      )
      expect(count(visibleText(`<${table}`), strings['plant.table.over_limit']), option.rotation_id).toBe(
        (onAverage ? 1 : 0) + kinds.length,
      )
    })
  })

  it('shows "no value" for each missing number of the table, never 0', () => {
    rawExample.options.forEach((option, index) => {
      const table = optionRow(html, index).split('data-testid="plant-kind-table"')[1].split('</table>')[0]
      const all = ['average', ...KINDS] as const
      const missing =
        all.filter((kind) => option.margin[kind].value === null).length +
        all.filter((kind) => option.soil_loss[kind].value === null).length
      expect(count(visibleText(`<${table}`), strings['plant.table.no_value']), option.rotation_id).toBe(missing)
    })
  })
})

describe('the card of the answer (3)', () => {
  it('shows the label of the chosen rotation, its id and three figures', () => {
    const html = card(render())
    const chosen = rotations.find((r) => r.rotation_id === rawExample.chosen)!
    expect(visibleText(`<${html.split('data-testid="plant-chosen-label"')[1].split('</p>')[0]}`)).toBe(chosen.label)
    expect(count(html, 'data-testid="plant-figure"')).toBe(3)
    expect(count(html, 'data-testid="plant-kind-table"')).toBe(1)
  })
})

describe('the sources an answer lacks (4)', () => {
  it('no notice when no source is unavailable', () => {
    expect(rawExample.sources.some((s) => s.state === 'unavailable')).toBe(false)
    expect(count(render(), 'data-testid="plant-sources-notice"')).toBe(0)
  })

  it('one notice in the card names each unavailable source with its reason, when nothing is chosen', () => {
    // An example answer where nothing is chosen (every kind of year, average),
    // with one source made unavailable.
    const raw = JSON.parse(
      JSON.stringify(
        rawAnswers.answers.find(
          (a) => a.questions.strictness === 'every_kind' && a.questions.margin_of === 'average',
        ),
      ),
    )
    expect(raw.chosen).toBeNull()
    const lacking = { reason: 'NOT_AVAILABLE', detail: 'SOURCE_DETAIL_MARKER' } as const
    raw.sources = [
      ...raw.sources,
      { ...raw.sources[0], id: 'source_marker', state: 'unavailable', missing_reason: lacking.reason, detail: lacking.detail },
    ]
    const set = parsePlantAnswers({ example_data: true, answers: [raw] })
    const html = card(
      renderToString(
        <PlantView set={set} strictness="every_kind" marginOf="average" price={raw.tipping_price.today} />,
      ),
    )
    expect(count(html, 'data-testid="plant-sources-notice"')).toBe(1)
    const notice = html.split('data-testid="plant-sources-notice"')[1].split('</ul>')[0]
    expect(visibleText(`<${notice}`)).toContain(missingPatternText('source_marker', lacking))
    // The reason nothing is chosen stays in the card, once.
    expect(count(visibleText(`<${html}`), missingPatternText(strings['plant.answer.why'], { reason: raw.reason, detail: raw.detail }))).toBe(1)
  })
})
