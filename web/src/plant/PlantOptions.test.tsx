import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { PlantView } from './PlantScreen'
import { parsePlantAnswers, plantExamples, selectAnswer } from './plantData'
import type { KindOfYear, MarginOf, PlantAnswerSet, Strictness } from './plantData'
import { buildRotationStrip, plantRotations, readPlantRotations, stripText } from './rotationStrip'
import type { PlantRotations } from './rotationStrip'
import { drawnSoilVerdict } from './optionBars'
import { drawnVerdictText } from './PlantOptionParts'
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

// Fix round 1 of S-020: plantRotations is now a typed read; the example
// request parses, so its definitions are here.
const exampleRotations: RotationDefinition[] = plantRotations.rotations!

function render(
  set: PlantAnswerSet = plantExamples,
  strictness: Strictness = 'on_average',
  marginOf: MarginOf = 'average',
  rotations: RotationDefinition[] | PlantRotations = exampleRotations,
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
      const rotation = exampleRotations.find((r) => r.rotation_id === option.rotation_id)!
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
    const limits = rawExample.options.map((o) => o.limit.limit.value)
    const scale = Math.max(...shown, ...limits)
    rawExample.options.forEach((option, index) => {
      const row = optionRow(html, index)
      if (option.soil_loss.average.value === null) return
      expect(row).toContain('data-testid="plant-bar-soil"')
      const line = row.match(/data-testid="plant-bar-limit"[^>]*style="left:([^"]*)%"/)
        ?? row.match(/style="left:([^"]*)%"[^>]*data-testid="plant-bar-limit"/)
      expect(line, option.rotation_id).not.toBeNull()
      expect(Number(line![1])).toBeCloseTo((option.limit.limit.value / scale) * 100, 6)
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
      // The limit is a declared Value (#424): missing, with its reason, never zero.
      option.limit.limit = {
        value: null,
        unit: option.limit.limit.unit,
        missing: { reason: 'NOT_DECLARED', detail: raw.detail },
      }
      option.limit.on_average = { ...open }
      option.limit.every_kind = { ...open }
      option.limit_check = { ...open }
      option.state = 'not_resolved'
    }
    raw.limit_cost = { ...raw.limit_cost, value: null, against: null, reason: 'NOT_DECLARED', detail: raw.detail }
    // A missing cost carries no D249 labels.
    delete raw.limit_cost.provenance
    delete raw.limit_cost.range_missing
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
    const rotations = exampleRotations.filter((r) => r.rotation_id !== absent)
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

/*
 * Fix round 1 of S-020 (PROPOSED, one case per remark). Every expected value
 * is read from the example answers and request, or from a copy where only the
 * fields named in the case change.
 */

function count(text: string, part: string): number {
  return text.split(part).length - 1
}

function fillOf(row: string): string | null {
  const fill = row.match(/data-testid="plant-bar-soil-fill"[^>]*data-verdict="([^"]*)"/)
  return fill === null ? null : fill[1]
}

describe('fix 1: the soil-loss bar says what the answer says of the quantity it draws', () => {
  const answerOf = (strictness: Strictness, marginOf: MarginOf) =>
    plantExamples.answers.find((a) => a.strictness === strictness && a.margin_of === marginOf)!

  it('of the average of the record: the on-average check of the option', () => {
    for (const answer of plantExamples.answers.filter((a) => a.margin_of === 'average')) {
      for (const option of answer.options) {
        expect(drawnSoilVerdict(option, 'average')).toEqual({
          kind: 'verdict',
          verdict: option.on_average.verdict,
          missing: option.on_average.missing,
        })
      }
    }
  })

  it('of a kind of year: from the kinds lists, never from the strictness in use', () => {
    const answer = answerOf('on_average', 'el_nino')
    const html = render(plantExamples, 'on_average', 'el_nino')
    let differs = 0
    answer.options.forEach((option, index) => {
      const drawn = drawnSoilVerdict(option, 'el_nino')
      if (option.kinds_not_met.includes('el_nino')) {
        expect(drawn).toEqual({ kind: 'verdict', verdict: 'does_not_meet', missing: null })
      } else if (option.kinds_not_resolved.includes('el_nino')) {
        expect(drawn).toEqual({ kind: 'verdict', verdict: 'not_resolved', missing: option.every_kind.missing })
      }
      const row = optionRow(html, index)
      if (option.soil_loss.el_nino.value === null) return
      const key = drawn.kind === 'not_in_record' ? 'not_in_record' : drawn.verdict
      expect(fillOf(row), option.rotation_id).toBe(key)
      const what = formatString(strings['plant.soil_loss_of'], { kind: strings['plant.kind.el_nino'] })
      expect(visibleText(row)).toContain(drawnVerdictText(what, drawn))
      if (key !== option.limit_check.verdict) differs += 1
    })
    // The example holds an option whose check on average meets while its El
    // Nino years do not: the bar follows the El Nino years.
    expect(differs).toBeGreaterThan(0)
  })

  it('a kind named in none of the lists meets when the lists cover a not-resolved every-kind check', () => {
    const option = answerOf('on_average', 'average').options.find(
      (o) => o.every_kind.verdict === 'not_resolved' && o.kinds_not_resolved.length !== 0,
    )!
    const free = (['el_nino', 'neutral', 'la_nina'] as const).find(
      (k) =>
        !option.kinds_not_met.includes(k) &&
        !option.kinds_not_resolved.includes(k) &&
        !option.kinds_not_in_record.includes(k),
    )!
    expect(drawnSoilVerdict(option, free)).toEqual({ kind: 'verdict', verdict: 'meets', missing: null })
  })

  it('a not-resolved every-kind check that names no kind gives the neutral not-resolved bar with its reason', () => {
    const option = answerOf('on_average', 'average').options.find(
      (o) => o.every_kind.verdict === 'not_resolved',
    )!
    const bare = { ...option, kinds_not_met: [], kinds_not_resolved: [], kinds_not_in_record: [] }
    expect(drawnSoilVerdict(bare, 'el_nino')).toEqual({
      kind: 'verdict',
      verdict: 'not_resolved',
      missing: option.every_kind.missing,
    })
  })

  it('a kind not in the record has no verdict colour, and says so', () => {
    const raw = JSON.parse(JSON.stringify(rawPlantAnswerOf('on_average', 'neutral')))
    const target = raw.options.find(
      (o: { soil_loss: { neutral: { value: number | null } } }) => o.soil_loss.neutral.value !== null,
    )
    target.limit.kinds_not_met = target.limit.kinds_not_met.filter((k: string) => k !== 'neutral')
    target.limit.kinds_not_resolved = target.limit.kinds_not_resolved.filter((k: string) => k !== 'neutral')
    target.limit.kinds_not_in_record = ['neutral']
    const html = render(single(raw), 'on_average', 'neutral')
    const index = raw.options.indexOf(target)
    const row = optionRow(html, index)
    expect(fillOf(row)).toBe('not_in_record')
    const what = formatString(strings['plant.soil_loss_of'], { kind: strings['plant.kind.neutral'] })
    expect(visibleText(row)).toContain(drawnVerdictText(what, { kind: 'not_in_record' }))
    expect(visibleText(row)).toContain(strings['plant.bar.not_in_record'])
  })

  it('of the average on average, the check line is its text verdict: no second line', () => {
    const html = render()
    rawExample.options.forEach((_, index) => {
      expect(optionRow(html, index)).not.toContain('data-testid="plant-bar-soil-verdict"')
    })
  })
})

function rawPlantAnswerOf(strictness: Strictness, marginOf: MarginOf): Record<string, any> {
  const index = plantExamples.answers.findIndex(
    (a) => a.strictness === strictness && a.margin_of === marginOf,
  )
  return rawAnswers.answers[index]
}

describe('fix 2: an option out under every kind of year names its kinds over the limit once', () => {
  it('prints the kinds over the limit once', () => {
    const answer = plantExamples.answers.find(
      (a) => a.strictness === 'every_kind' && a.margin_of === 'average',
    )!
    const index = answer.options.findIndex((o) => o.state === 'does_not_meet')
    const option = answer.options[index]
    const row = visibleText(optionRow(render(plantExamples, 'every_kind'), index))
    const line = formatString(strings['plant.kinds.not_met'], {
      kinds: option.kinds_not_met.map((k) => strings[`plant.kind.${k}`]).join(', '),
    })
    expect(count(row, line)).toBe(1)
  })
})

describe('fix 3: an option not resolved shows the reason of its check once', () => {
  it('the state detail says why; the check line names the check and its verdict', () => {
    const open = rawExample.options.find((o) => o.state === 'not_resolved')!
    const missing = { reason: open.limit_check.reason as MissingPart['reason'], detail: open.limit_check.detail! }
    const row = visibleText(optionRow(render(), indexOf(open.rotation_id)))
    expect(count(row, missingPatternText(strings['plant.state.why'], missing))).toBe(1)
    expect(row).not.toContain(missingPatternText(strings['plant.check.on_average'], missing))
    expect(row).toContain(
      formatString(strings['plant.check_line'], {
        check: strings['plant.check.on_average'],
        verdict: strings['plant.verdict.not_resolved'],
      }),
    )
    // The reason phrase itself, whatever names it, is printed once.
    expect(count(row, missingPatternText('', missing))).toBe(1)
  })
})

describe('fix 4: a negative margin differs by more than its colour', () => {
  it('a negative bar is dashed and carries a text mark; the number keeps its sign', () => {
    const answer = plantExamples.answers.find(
      (a) => a.strictness === 'on_average' && a.margin_of === 'la_nina',
    )!
    const html = render(plantExamples, 'on_average', 'la_nina')
    answer.options.forEach((option, index) => {
      const value = option.margin.la_nina.value!
      const row = optionRow(html, index)
      const bar = row.match(/data-testid="plant-bar-margin-fill"[^>]*/)![0]
      expect(bar).toContain(`data-pattern="${value < 0 ? 'dashed' : 'solid'}"`)
      expect(row.includes('data-testid="plant-bar-margin-loss"')).toBe(value < 0)
      expect(visibleText(row).includes(strings['plant.bar.margin_loss'])).toBe(value < 0)
      if (value < 0) expect(displayNumber(value).startsWith('-')).toBe(true)
      expect(visibleText(row)).toContain(displayNumber(value))
    })
  })
})

describe('fix 5: the text alternative of the strip reads each crop with its purpose', () => {
  it('names the purpose of every placed crop', () => {
    const html = render()
    rawExample.options.forEach((option, index) => {
      const rotation = exampleRotations.find((r) => r.rotation_id === option.rotation_id)!
      const label = decode(
        optionRow(html, index).match(/data-testid="plant-option-strip"[^>]*aria-label="([^"]*)"/)![1],
      )
      for (const component of rotation.components.filter((c) => c.sowing.date !== null)) {
        expect(label).toContain(formatString(strings['plant.strip.purpose'], { purpose: component.purpose }))
      }
    })
  })
})

describe('fix 6: a request whose rotations cannot be read', () => {
  it('shows every strip as not available with its reason, and the rest of the screen', () => {
    const read = readPlantRotations({ contract: 'plant_request', rotations: [{}] })
    expect(read.rotations).toBeNull()
    const html = render(plantExamples, 'on_average', 'average', read)
    expect(html).not.toContain('data-testid="plant-option-strip"')
    expect(html).toContain('data-testid="plant-card"')
    rawExample.options.forEach((option, index) => {
      const row = optionRow(html, index)
      expect(visibleText(row)).toContain(option.rotation_id)
      expect(row).toContain('data-testid="plant-strip-unavailable"')
      expect(visibleText(row)).toContain(
        missingPatternText(strings['plant.strip.what'], {
          reason: 'MISSING_INPUT',
          detail: strings['plant.strip.request_invalid_detail'],
        }),
      )
    })
  })
})

describe('fix 7: the strip shows the provisional start month and the provenance of its dates', () => {
  it('marks the start month provisional when the definition does, with its provenance', () => {
    const html = render()
    rawExample.options.forEach((option, index) => {
      const raw = rawRequest.rotations.find((r) => r.rotation_id === option.rotation_id)!
      const row = optionRow(html, index)
      const line = visibleText(row.match(/data-testid="plant-strip-ag-year"[\s\S]*?<\/p>/)![0])
      expect(line).toContain(formatString(strings['ribbon.ag_year_start'], { month: raw.ag_year_start.month }))
      expect(line.includes(strings['ribbon.provisional'])).toBe(raw.ag_year_start.provisional)
      expect(line).toContain(strings[`provenance.${raw.ag_year_start.provenance as 'DECLARED'}`])
      expect(visibleText(row)).toContain(formatString(strings['value.source'], { source: raw.ag_year_start.source }))
      const dated = raw.components.flatMap((c) => [c.sowing, c.harvest]).filter((p) => p.date !== null)
      for (const part of dated as { provenance: 'DECLARED'; source: string }[]) {
        expect(visibleText(row)).toContain(
          formatString(strings['plant.strip.dates_provenance'], { provenance: strings[`provenance.${part.provenance}`] }),
        )
        expect(visibleText(row)).toContain(formatString(strings['value.source'], { source: part.source }))
      }
    })
  })

  it('shows no provisional mark when the start month is not provisional', () => {
    const raw = JSON.parse(JSON.stringify(rawRequest))
    raw.rotations[0].ag_year_start.provisional = false
    const read = readPlantRotations(raw)
    const index = rawExample.options.findIndex((o) => o.rotation_id === raw.rotations[0].rotation_id)
    const row = optionRow(render(plantExamples, 'on_average', 'average', read), index)
    expect(row).toContain('data-testid="plant-strip-ag-year"')
    expect(row).not.toContain('data-testid="plant-strip-provisional"')
  })
})
