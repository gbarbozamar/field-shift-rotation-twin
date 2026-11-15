import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import App from '../App'
import PlantScreen, { PlantView } from './PlantScreen'
import { parsePlantAnswers, plantExamples } from './plantData'
import type { MarginOf, PlantAnswerSet, Strictness } from './plantData'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'

/**
 * Acceptance test of the screen "What should I plant?" (S-019). PROPOSED,
 * designed before the screen. The screen is a pure function of the answers
 * and of the questions asked, so its behaviour is its static markup, rendered
 * with the pure server renderer of react-dom (no DOM environment, no new
 * dependency). Every expected number is read from the contract example or
 * from the generated answers, never typed here; every expected text is the
 * wording of strings.ts filled with those values.
 *
 * (1) the screen renders the chosen rotation of the example answer with its
 *     margin, soil loss, limit and tipping price;
 * (2) an answer where none meets the limit (a copy of the example where only
 *     the answer and state fields change) shows "none meets" with its reason;
 * (3) changing a question (how strict, the kind of year, the price past the
 *     tipping point) changes the answer shown;
 * (4) a missing value shows its reason, never 0;
 * (6) the example data banner is shown.
 * (5) and (7) are in plantData.test.ts.
 */

// leaflet needs a real browser window, so the map of the fields screen is
// stubbed for the route check, as in App.test.tsx.
vi.mock('../map/FieldsMap', () => ({
  default: () => <div data-testid="fields-map" />,
}))

function decode(html: string): string {
  return html
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

/** The whole visible text of a markup, tags dropped, runs of spaces joined. */
function visibleText(html: string): string {
  return decode(html.replace(/<!-- -->/g, '').replace(/<[^>]+>/g, ' '))
    .replace(/\s+/g, ' ')
    .trim()
}

/** The markup inside the first element carrying this data-testid. */
function section(html: string, testid: string, index = 0): string {
  const parts = html.split(`data-testid="${testid}"`)
  expect(parts.length - 1, `testid ${testid}`).toBeGreaterThan(index)
  return parts[index + 1]
}

function render(
  set: PlantAnswerSet = plantExamples,
  strictness: Strictness = 'on_average',
  marginOf: MarginOf = 'average',
  price: number = rawExample.tipping_price.today,
): string {
  return renderToString(
    <PlantView set={set} strictness={strictness} marginOf={marginOf} price={price} />,
  )
}

function valueLine(what: string, value: number, unit: string): string {
  return formatString(strings['plant.value_line'], { what, value: displayNumber(value), unit })
}

const kind = (k: MarginOf) => strings[`plant.kind.${k}`]
const chosenOption = rawExample.options.find((o) => o.rotation_id === rawExample.chosen)!

describe('PlantScreen: the chosen rotation (1)', () => {
  const html = render()
  const card = visibleText(section(html, 'plant-card'))

  it('renders the title and the rule', () => {
    expect(visibleText(html)).toContain(strings['plant.title'])
    expect(visibleText(html)).toContain(strings['plant.rule'])
  })

  it('names the chosen rotation of the example answer', () => {
    expect(card).toContain(strings['plant.answer.chosen'])
    expect(card).toContain(rawExample.chosen)
  })

  it('shows its margin of the kind of year asked', () => {
    const margin = chosenOption.margin.average
    expect(card).toContain(
      valueLine(formatString(strings['plant.margin_of'], { kind: kind('average') }), margin.value, margin.unit),
    )
  })

  it('shows its soil loss against the limit, and the check of the strictness', () => {
    const loss = chosenOption.soil_loss.average
    expect(card).toContain(
      valueLine(formatString(strings['plant.soil_loss_of'], { kind: kind('average') }), loss.value!, loss.unit),
    )
    expect(card).toContain(valueLine(strings['plant.limit'], chosenOption.limit.limit, chosenOption.limit.unit))
    expect(card).toContain(
      formatString(strings['plant.check_line'], {
        check: strings['plant.check.on_average'],
        verdict: strings['plant.verdict.meets'],
      }),
    )
  })

  it('shows its margin in each kind of year, labelled El Nino, neutral and La Nina', () => {
    expect(card).toContain(strings['plant.by_kind'])
    for (const k of ['el_nino', 'neutral', 'la_nina'] as const) {
      const margin = chosenOption.margin[k]
      expect(card).toContain(valueLine(kind(k), margin.value, margin.unit))
    }
  })

  it('shows what meeting the limit costs', () => {
    const cost = rawExample.limit_cost
    expect(card).toContain(
      formatString(strings['plant.cost.value'], {
        value: displayNumber(cost.value),
        unit: cost.unit,
        against: cost.against,
      }),
    )
  })

  it('shows the tipping price down with its distance, and up missing with its reason', () => {
    const down = rawExample.tipping_price.down
    expect(card).toContain(
      formatString(strings['plant.tip.point'], {
        price: displayNumber(down.price),
        unit: down.unit,
        after: strings['plant.after.not_resolved'],
      }),
    )
    expect(card).toContain(
      formatString(strings['plant.tip.distance'], { distance: displayNumber(down.distance_percent) }),
    )
    const up = rawExample.tipping_price.up
    expect(card).toContain(
      missingPatternText(strings['plant.tip.up'], { reason: up.reason as MissingPart['reason'], detail: up.detail }),
    )
  })

  it('shows the state of each option in plain words', () => {
    const options = visibleText(section(html, 'plant-options'))
    expect(options).toContain(strings['plant.state.chosen'])
    expect(options).toContain(strings['plant.state.does_not_meet'])
    expect(options).toContain(strings['plant.state.not_resolved'])
    for (const option of rawExample.options) {
      expect(options).toContain(option.rotation_id)
    }
  })

  it('shows the heavier-rain stress test as not available, with its reason, and disabled', () => {
    const rain = section(html, 'plant-q-rain')
    expect(visibleText(rain)).toContain(
      missingPatternText(strings['plant.q.rain_control'], {
        reason: 'NOT_AVAILABLE',
        detail: strings['plant.q.rain_unavailable_detail'],
      }),
    )
    expect(rain).toMatch(/disabled=""/)
  })

  it('the default screen renders the example answer of the questions it starts with', () => {
    expect(renderToString(<PlantScreen />)).toBe(html)
  })
})

describe('PlantScreen: none meets the limit (2)', () => {
  // A copy of the example where only the answer and state fields change.
  const raw = JSON.parse(JSON.stringify(rawExample))
  raw.answer = 'none_meets'
  raw.chosen = null
  raw.reason = 'NOT_APPLICABLE'
  raw.detail = rawExample.options.map((o) => o.rotation_id).join('; ')
  for (const option of raw.options) option.state = 'does_not_meet'
  raw.limit_cost = {
    ...raw.limit_cost,
    value: null,
    against: null,
    reason: 'NOT_APPLICABLE',
    detail: raw.detail,
  }
  const set = parsePlantAnswers({ example_data: true, answers: [raw] })
  const card = visibleText(section(render(set), 'plant-card'))

  it('says none meets, with its reason in plain words', () => {
    expect(card).toContain(strings['plant.answer.none_meets'])
    expect(card).toContain(
      missingPatternText(strings['plant.answer.why'], { reason: 'NOT_APPLICABLE', detail: raw.detail }),
    )
  })

  it('names no rotation to plant', () => {
    expect(card).not.toContain(strings['plant.answer.chosen'])
  })
})

describe('PlantScreen: changing a question changes the answer shown (3)', () => {
  const base = visibleText(section(render(), 'plant-card'))

  it('how strict: every kind of year gives the generated answer, not resolved', () => {
    const card = visibleText(section(render(plantExamples, 'every_kind'), 'plant-card'))
    expect(card).toContain(strings['plant.answer.not_resolved'])
    expect(card).not.toContain(strings['plant.answer.chosen'])
    expect(base).toContain(strings['plant.answer.chosen'])
  })

  it('how strict: every kind of year shows each option with its every-kind check and the kinds not in the record', () => {
    const answer = plantExamples.answers.find(
      (a) => a.strictness === 'every_kind' && a.margin_of === 'average',
    )!
    const html = render(plantExamples, 'every_kind')
    answer.options.forEach((option, index) => {
      const block = visibleText(section(html, 'plant-option', index))
      expect(block).toContain(strings['plant.check.every_kind'])
      const kinds =
        option.kinds_not_in_record.length === 0
          ? strings['plant.kinds.none']
          : option.kinds_not_in_record.map(kind).join(', ')
      expect(block).toContain(formatString(strings['plant.kinds.not_in_record'], { kinds }))
    })
  })

  it('the kind of year: a La Nina year gives the generated answer, not resolved', () => {
    const card = visibleText(section(render(plantExamples, 'on_average', 'la_nina'), 'plant-card'))
    expect(card).toContain(strings['plant.answer.not_resolved'])
    expect(card).not.toContain(strings['plant.answer.chosen'])
  })

  it('the price: past the tipping point down, the answer shown is the one past it', () => {
    const down = rawExample.tipping_price.down
    const low = rawExample.tipping_price.price_range.low
    const atToday = visibleText(section(render(), 'plant-price-answer'))
    const pastIt = visibleText(section(render(plantExamples, 'on_average', 'average', low), 'plant-price-answer'))
    const expected = formatString(strings['plant.price.past'], {
      price: displayNumber(down.price),
      unit: down.unit,
      after: strings['plant.after.not_resolved'],
    })
    expect(pastIt).toContain(expected)
    expect(atToday).not.toContain(expected)
    expect(atToday).toContain(strings['plant.price.today'])
  })
})

describe('PlantScreen: a missing value shows its reason, never 0 (4)', () => {
  const html = render()
  const missingOption = rawExample.options.find((o) => o.soil_loss.average.value === null)!
  const index = rawExample.options.indexOf(missingOption)
  const block = visibleText(section(html, 'plant-option', index))
  const loss = missingOption.soil_loss.average
  const what = formatString(strings['plant.soil_loss_of'], { kind: kind('average') })

  it('shows the missing soil loss with its reason', () => {
    expect(block).toContain(
      missingPatternText(what, { reason: loss.reason as MissingPart['reason'], detail: loss.detail! }),
    )
  })

  it('never writes a zero for it', () => {
    expect(block).not.toContain(`${what}: 0`)
    expect(block).not.toContain(valueLine(what, 0, loss.unit))
  })
})

describe('PlantScreen: the route #/plant', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the screen at #/plant', () => {
    vi.stubGlobal('window', { location: { hash: '#/plant' } })
    const html = renderToString(<App />)
    expect(html).toContain('data-testid="plant-card"')
    expect(visibleText(html)).toContain(strings['plant.title'])
  })
})

describe('PlantScreen: example data (6)', () => {
  it('shows the example data banner and the disclaimer', () => {
    const html = render()
    expect(visibleText(section(html, 'plant-example-banner'))).toContain(strings['example.banner'])
    expect(visibleText(html)).toContain(strings['disclaimer.full'])
  })
})
