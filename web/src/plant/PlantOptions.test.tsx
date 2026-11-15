import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import { PlantView } from './PlantScreen'
import { parsePlantAnswers, plantExamples, selectAnswer } from './plantData'
import type { KindOfYear, MarginOf, PlantAnswerSet, Strictness } from './plantData'
import { buildRotationStrip, plantRotations, stripText } from './rotationStrip'
import type { RotationDefinition } from '../rotation/exampleRotation'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'

/**
 * Acceptance test of the option rows of the screen "What should I plant?"
 * (S-020). PROPOSED, designed before the code. Rendered with the pure server
 * renderer of react-dom, as PlantScreen.test.tsx does. Every expected number
 * is read from the example answers or the example request; every expected
 * text is the wording of strings.ts filled with those values.
 *
 * (1) each row carries its rotation label and its strip, whose text
 *     alternative is the strip text of its definition;
 * (3) the states in plain words: meets in every kind (a copy of the example
 *     where only the every-kind check and its kinds change); meets on average
 *     but not in the kinds named; out (does not meet) with the check that
 *     failed and its kinds; not resolved with its reason;
 * (4) the soil-loss bar has a limit line at the limit when the limit is set,
 *     and none, with the reason, when it is null;
 * (5) a missing margin or soil loss shows its reason and no bar, never 0;
 * (6) a rotation of the answer absent from the request shows its strip as
 *     not available, with its reason.
 * (2) and (7) are in rotationStrip.test.ts.
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

/** The markup of the option row at this index, and nothing after it. */
function optionRow(html: string, index: number): string {
  const parts = html.split('data-testid="plant-option"')
  expect(parts.length - 1).toBeGreaterThan(index)
  // A row is one article and holds no other article.
  return parts[index + 1].split('</article>')[0]
}

function render(
  set: PlantAnswerSet = plantExamples,
  strictness: Strictness = 'on_average',
  marginOf: MarginOf = 'average',
  rotations: RotationDefinition[] = plantRotations,
): string {
  const answer = selectAnswer(set, strictness, marginOf)!
  return renderToString(
    <PlantView
      set={set}
      strictness={strictness}
      marginOf={marginOf}
      price={answer.tipping_price.today}
      rotations={rotations}
    />,
  )
}

function exampleCopy(): Record<string, any> {
  return JSON.parse(JSON.stringify(rawExample))
}

function single(raw: Record<string, any>): PlantAnswerSet {
  return parsePlantAnswers({ example_data: true, answers: [raw] })
}

const kindsText = (kinds: string[]) =>
  kinds.map((k) => strings[`plant.kind.${k as KindOfYear}`]).join(', ')

const indexOf = (id: string) => rawExample.options.findIndex((o) => o.rotation_id === id)

describe('each option is a row with its label and its strip (1)', () => {
  const html = render()

  it('shows the label of its definition and a strip whose text alternative reads it year by year', () => {
    rawExample.options.forEach((option, index) => {
      const row = optionRow(html, index)
      const rotation = plantRotations.find((r) => r.rotation_id === option.rotation_id)!
      expect(visibleText(row)).toContain(rotation.label)
      expect(visibleText(row)).toContain(option.rotation_id)
      const match = row.match(/data-testid="plant-option-strip"[^>]*aria-label="([^"]*)"/)
        ?? row.match(/aria-label="([^"]*)"[^>]*data-testid="plant-option-strip"/)
      expect(match, option.rotation_id).not.toBeNull()
      expect(decode(match![1])).toBe(stripText(buildRotationStrip(rotation)))
    })
  })

  it('keeps the state line of each option', () => {
    rawExample.options.forEach((option, index) => {
      const row = optionRow(html, index)
      expect(row).toContain('data-testid="plant-option-state"')
      expect(visibleText(row)).toContain(strings[`plant.state.${option.state as 'chosen'}`])
    })
  })
})

describe('the state in plain words (3)', () => {
  it('meets in every kind of year (a copy where only the every-kind check and its kinds change)', () => {
    const raw = exampleCopy()
    const chosen = raw.options.find((o: { rotation_id: string }) => o.rotation_id === raw.chosen)
    chosen.limit.every_kind = { verdict: 'meets', reason: null, detail: null }
    chosen.limit.kinds_not_met = []
    chosen.limit.kinds_not_resolved = []
    const row = visibleText(optionRow(render(single(raw)), indexOf(raw.chosen)))
    expect(row).toContain(strings['plant.state.every_kind_meets'])
    expect(row).not.toContain(formatString(strings['plant.state.on_average_only'], { kinds: '' }).trim())
    expect(row).toContain(
      formatString(strings['plant.kinds.not_in_record'], {
        kinds:
          chosen.limit.kinds_not_in_record.length === 0
            ? strings['plant.kinds.none']
            : kindsText(chosen.limit.kinds_not_in_record),
      }),
    )
  })

  it('meets on average but not in the kinds named, from the every-kind check', () => {
    const chosen = rawExample.options.find((o) => o.rotation_id === rawExample.chosen)!
    expect(chosen.limit.every_kind.verdict).toBe('does_not_meet')
    const row = visibleText(optionRow(render(), indexOf(rawExample.chosen)))
    expect(row).toContain(
      formatString(strings['plant.state.on_average_only'], {
        kinds: kindsText(chosen.limit.kinds_not_met),
      }),
    )
    expect(row).not.toContain(strings['plant.state.every_kind_meets'])
  })

  it('out: does not meet the limit, with the check that failed and the kinds over it', () => {
    const out = rawExample.options.find((o) => o.state === 'does_not_meet')!
    const row = visibleText(optionRow(render(), indexOf(out.rotation_id)))
    expect(row).toContain(strings['plant.state.does_not_meet'])
    expect(row).toContain(
      formatString(strings['plant.state.out_by'], { check: strings['plant.check.on_average'] }),
    )
    expect(row).toContain(
      formatString(strings['plant.kinds.not_met'], { kinds: kindsText(out.limit.kinds_not_met) }),
    )
  })

  it('out under every kind of year names the every-kind check', () => {
    const answer = plantExamples.answers.find(
      (a) => a.strictness === 'every_kind' && a.margin_of === 'average',
    )!
    const index = answer.options.findIndex((o) => o.state === 'does_not_meet')
    const row = visibleText(optionRow(render(plantExamples, 'every_kind'), index))
    expect(row).toContain(
      formatString(strings['plant.state.out_by'], { check: strings['plant.check.every_kind'] }),
    )
  })

  it('not resolved, with its reason', () => {
    const open = rawExample.options.find((o) => o.state === 'not_resolved')!
    const row = optionRow(render(), indexOf(open.rotation_id))
    const detail = row.match(/data-testid="plant-option-state-detail"[\s\S]*?<\/div>/)![0]
    expect(visibleText(detail)).toContain(
      missingPatternText(strings['plant.state.why'], {
        reason: open.limit_check.reason as MissingPart['reason'],
        detail: open.limit_check.detail!,
      }),
    )
  })
})

describe('the soil-loss bar and its limit line (4)', () => {
  it('draws a limit line at the limit, on the scale of the largest soil loss shown and the limit', () => {
    const html = render()
    const shown = rawExample.options
      .map((o) => o.soil_loss.average.value)
      .filter((v): v is number => v !== null)
    const limits = rawExample.options.map((o) => o.limit.limit)
    const scale = Math.max(...shown, ...limits)
    rawExample.options.forEach((option, index) => {
      const row = optionRow(html, index)
      if (option.soil_loss.average.value === null) return
      expect(row).toContain('data-testid="plant-bar-soil"')
      const line = row.match(/data-testid="plant-bar-limit"[^>]*style="left:([^"]*)%"/)
        ?? row.match(/style="left:([^"]*)%"[^>]*data-testid="plant-bar-limit"/)
      expect(line, option.rotation_id).not.toBeNull()
      expect(Number(line![1])).toBeCloseTo((option.limit.limit / scale) * 100, 6)
      const fill = row.match(/data-testid="plant-bar-soil-fill"[^>]*data-verdict="([^"]*)"/)
      expect(fill![1]).toBe(option.limit_check.verdict)
    })
  })

  it('draws no limit line when the limit is null, and says why', () => {
    const raw = exampleCopy()
    raw.answer = 'not_resolved'
    raw.chosen = null
    raw.reason = 'NOT_DECLARED'
    raw.detail = raw.options.map((o: { rotation_id: string }) => o.rotation_id).join('; ')
    for (const option of raw.options) {
      const open = { verdict: 'not_resolved', reason: 'NOT_DECLARED', detail: raw.detail }
      option.limit.limit = null
      option.limit.on_average = { ...open }
      option.limit.every_kind = { ...open }
      option.limit_check = { ...open }
      option.state = 'not_resolved'
    }
    raw.limit_cost = { ...raw.limit_cost, value: null, against: null, reason: 'NOT_DECLARED', detail: raw.detail }
    const html = render(single(raw))
    raw.options.forEach((option: { soil_loss: { average: { value: number | null } } }, index: number) => {
      const row = optionRow(html, index)
      expect(row).not.toContain('data-testid="plant-bar-limit"')
      if (option.soil_loss.average.value !== null) {
        expect(row).toContain('data-testid="plant-bar-soil"')
        expect(visibleText(row)).toContain(
          missingPatternText(strings['plant.bar.limit_line'], { reason: 'NOT_DECLARED', detail: raw.detail }),
        )
      }
    })
  })
})

describe('the margin bar, and a missing value with no bar (5)', () => {
  it('draws each margin on the scale of the largest absolute margin shown, a negative one marked', () => {
    const answer = plantExamples.answers.find(
      (a) => a.strictness === 'on_average' && a.margin_of === 'la_nina',
    )!
    const values = answer.options.map((o) => o.margin.la_nina.value)
    const scale = Math.max(...values.filter((v): v is number => v !== null).map(Math.abs))
    expect(values.some((v) => v !== null && v < 0)).toBe(true)
    const html = render(plantExamples, 'on_average', 'la_nina')
    answer.options.forEach((option, index) => {
      const value = option.margin.la_nina.value!
      const row = optionRow(html, index)
      const bar = row.match(/data-testid="plant-bar-margin-fill"[^>]*/)![0]
      expect(bar).toContain(`data-negative="${value < 0}"`)
      const width = bar.match(/width:([^%"]*)%/)!
      expect(Number(width[1])).toBeCloseTo((Math.abs(value) / scale) * 100, 6)
      // The sign travels in the number.
      expect(visibleText(row)).toContain(displayNumber(value))
    })
  })

  it('a missing soil loss shows its reason and no soil-loss bar', () => {
    const open = rawExample.options.find((o) => o.soil_loss.average.value === null)!
    const row = optionRow(render(), indexOf(open.rotation_id))
    expect(row).not.toContain('data-testid="plant-bar-soil"')
    expect(visibleText(row)).toContain(
      missingPatternText(
        formatString(strings['plant.soil_loss_of'], { kind: strings['plant.kind.average'] }),
        { reason: open.soil_loss.average.reason as MissingPart['reason'], detail: open.soil_loss.average.detail! },
      ),
    )
  })

  it('a missing margin shows its reason and no margin bar, never 0', () => {
    const raw = exampleCopy()
    const out = raw.options.find((o: { state: string }) => o.state === 'does_not_meet')
    out.margin.average = { value: null, unit: out.margin.average.unit, reason: 'NOT_COMPUTABLE', detail: null }
    const row = optionRow(render(single(raw)), indexOf(out.rotation_id))
    const what = formatString(strings['plant.margin_of'], { kind: strings['plant.kind.average'] })
    expect(row).not.toContain('data-testid="plant-bar-margin"')
    expect(visibleText(row)).toContain(missingPatternText(what, { reason: 'NOT_COMPUTABLE' }))
    expect(visibleText(row)).not.toContain(`${what}: 0`)
  })
})

describe('a rotation of the answer absent from the request (6)', () => {
  it('shows its strip as not available, with its reason, never an empty strip', () => {
    const absent = rawExample.options[0].rotation_id
    const rotations = plantRotations.filter((r) => r.rotation_id !== absent)
    const row = optionRow(render(plantExamples, 'on_average', 'average', rotations), 0)
    expect(row).not.toContain('data-testid="plant-option-strip"')
    expect(row).toContain('data-testid="plant-strip-unavailable"')
    expect(visibleText(row)).toContain(
      missingPatternText(strings['plant.strip.what'], {
        reason: 'MISSING_INPUT',
        detail: strings['plant.strip.no_definition_detail'],
      }),
    )
    // The other rows keep their strips.
    expect(optionRow(render(plantExamples, 'on_average', 'average', rotations), 1)).toContain(
      'data-testid="plant-option-strip"',
    )
  })
})
