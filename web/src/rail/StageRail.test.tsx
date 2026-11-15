import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import StageRail from './StageRail'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId } from '../identity/selection'
import { exampleRotation } from '../rotation/exampleRotation'
import { setRunAnswered } from '../seam/runAnswer'
import { strings } from '../strings'

/**
 * Acceptance test of the stage rail (issue #435). The rail is a pure
 * function of the two shared stores (the selected field, the seam's
 * answered flag), so its whole behaviour is its static markup, rendered
 * with the pure server renderer of react-dom: every state a stage shows
 * is set through the real store setters, never through a prop.
 */

function renderRail(): string {
  return renderToString(<StageRail />)
}

/** The markup of one rail item, from its testid to the end of its li. */
function itemHtml(html: string, n: number): string {
  const at = html.indexOf(`data-testid="stage-rail-item-${n}"`)
  if (at === -1) throw new Error(`stage-rail-item-${n} was not rendered`)
  const end = html.indexOf('</li>', at)
  return html.slice(at, end)
}

function count(html: string, text: string): number {
  return html.split(text).length - 1
}

describe('StageRail', () => {
  beforeEach(() => {
    setSelectedFieldId(null)
    setRunAnswered(false)
  })

  afterEach(() => {
    setSelectedFieldId(null)
    setRunAnswered(false)
  })

  it('shows the six stages in order under the rail label', () => {
    const html = renderRail()
    const names = [
      strings['rail.stage.case'],
      strings['rail.stage.field'],
      strings['rail.stage.rotations'],
      strings['rail.stage.compare'],
      strings['rail.stage.decision'],
      strings['rail.stage.handoff'],
    ]
    for (const [index, name] of names.entries()) {
      expect(itemHtml(html, index + 1), `stage ${index + 1} must be ${name}`).toContain(name)
    }
    for (let index = 1; index < names.length; index += 1) {
      expect(
        html.indexOf(`data-testid="stage-rail-item-${index + 1}"`),
        'the stages must render in their order',
      ).toBeGreaterThan(html.indexOf(`data-testid="stage-rail-item-${index}"`))
    }
    expect(count(html, 'data-testid="stage-rail-item-')).toBe(6)
  })

  it('with no field selected: the case done, the field current, the rest waiting for their reasons', () => {
    const html = renderRail()

    expect(itemHtml(html, 1)).toContain(strings['rail.state.done'])
    expect(itemHtml(html, 1)).not.toContain(strings['rail.state.current'])

    expect(itemHtml(html, 2)).toContain(strings['rail.state.current'])
    expect(itemHtml(html, 2)).toContain(strings['rail.waiting.field'])
    expect(itemHtml(html, 2)).not.toContain(strings['rail.state.done'])

    expect(itemHtml(html, 3)).toContain(strings['rail.state.waiting'])
    expect(itemHtml(html, 3)).toContain(strings['rail.waiting.rotations'])
    expect(itemHtml(html, 4)).toContain(strings['rail.state.waiting'])
    expect(itemHtml(html, 4)).toContain(strings['rail.waiting.compare'])
    expect(itemHtml(html, 5)).toContain(strings['rail.state.waiting'])
    expect(itemHtml(html, 5)).toContain(strings['rail.waiting.decision'])
    expect(itemHtml(html, 6)).toContain(strings['rail.state.waiting'])
    expect(itemHtml(html, 6)).toContain(strings['rail.waiting.handoff'])

    expect(count(html, strings['rail.state.current']), 'exactly one current stage').toBe(1)
  })

  it('the rotation field selected, no run: field and rotations done, compare current, decision done, handoff waiting', () => {
    setSelectedFieldId(exampleRotation.field_id)
    const html = renderRail()

    expect(itemHtml(html, 1)).toContain(strings['rail.state.done'])
    expect(itemHtml(html, 2)).toContain(strings['rail.state.done'])
    expect(itemHtml(html, 2)).not.toContain(strings['rail.state.current'])
    expect(itemHtml(html, 3)).toContain(strings['rail.state.done'])
    expect(itemHtml(html, 3)).not.toContain(strings['rail.waiting.rotations'])

    expect(itemHtml(html, 4)).toContain(strings['rail.state.current'])
    expect(itemHtml(html, 4)).toContain(strings['rail.waiting.compare'])
    expect(itemHtml(html, 4)).not.toContain(strings['rail.state.done'])

    expect(itemHtml(html, 5)).toContain(strings['rail.state.done'])

    expect(itemHtml(html, 6)).toContain(strings['rail.state.waiting'])
    expect(itemHtml(html, 6)).toContain(strings['rail.waiting.handoff'])

    expect(count(html, strings['rail.state.current']), 'exactly one current stage').toBe(1)
  })

  it('the rotation field selected and the run answered: all six done, the handoff current', () => {
    setSelectedFieldId(exampleRotation.field_id)
    setRunAnswered(true)
    const html = renderRail()

    for (let n = 1; n <= 6; n += 1) {
      expect(itemHtml(html, n), `stage ${n} must be done`).toContain(strings['rail.state.done'])
      expect(itemHtml(html, n), `stage ${n} must not be waiting`).not.toContain(
        strings['rail.state.waiting'],
      )
    }
    expect(itemHtml(html, 6)).toContain(strings['rail.state.current'])
    expect(count(html, strings['rail.state.current']), 'exactly one current stage').toBe(1)
  })

  it('a field the rotation does not belong to: the rotations stage waits for its reason', () => {
    const withoutRotation = exampleCase.fields.find(
      (field) => field.field_id !== exampleRotation.field_id,
    )
    if (withoutRotation === undefined) throw new Error('fixture: a field without a rotation exists')
    setSelectedFieldId(withoutRotation.field_id)
    const html = renderRail()

    expect(itemHtml(html, 3)).toContain(strings['rail.state.waiting'])
    expect(itemHtml(html, 3)).toContain(strings['rail.waiting.rotations'])
    expect(itemHtml(html, 3)).not.toContain(strings['rail.state.done'])
    expect(itemHtml(html, 2)).toContain(strings['rail.state.done'])
  })

  it('marks exactly the current stage with aria-current="step"', () => {
    const html = renderRail()
    expect(count(html, 'aria-current="step"'), 'exactly one stage is the current one').toBe(1)
    for (let n = 1; n <= 6; n += 1) {
      expect(
        itemHtml(html, n).includes('aria-current="step"'),
        `stage ${n} carries aria-current only when it is the current one`,
      ).toBe(n === 2)
    }

    // with every stage done the marker follows the handoff stage
    setSelectedFieldId(exampleRotation.field_id)
    setRunAnswered(true)
    const done = renderRail()
    expect(count(done, 'aria-current="step"')).toBe(1)
    expect(itemHtml(done, 6)).toContain('aria-current="step"')
    expect(itemHtml(done, 2)).not.toContain('aria-current="step"')
  })

  it('becomes a wrapping horizontal row on wide screens', () => {
    const html = renderRail()
    const at = html.indexOf('data-testid="stage-rail"')
    if (at === -1) throw new Error('stage-rail was not rendered')
    const tag = html.slice(at, html.indexOf('>', at))
    expect(tag).toContain('min-[1100px]:flex-row')
    expect(tag).toContain('min-[1100px]:flex-wrap')
  })

  it('names the rail for assistive technology, shows every waiting reason, and draws no percentage', () => {
    const html = renderRail()

    expect(html).toContain(`aria-label="${strings['rail.label']}"`)
    expect(strings['rail.label']).toBe('The case in six stages')

    // with nothing selected five stages wait, and each shows its own reason
    for (const reason of [
      strings['rail.waiting.field'],
      strings['rail.waiting.rotations'],
      strings['rail.waiting.compare'],
      strings['rail.waiting.decision'],
      strings['rail.waiting.handoff'],
    ]) {
      expect(html, `the reason must render: ${reason}`).toContain(reason)
    }
    expect(html, 'no percentage anywhere in the rail').not.toContain('%')
  })
})
