/**
 * Acceptance test of the rotation ribbon (display-only unit).
 *
 * The fixture is the contract example itself, copied unchanged into
 * web/src/data/rotation_definition.json: label "Illustrative rotation",
 * three components in position order, harvests missing with NOT_APPLICABLE
 * on the cover crop and the pasture, grazing and termination missing with
 * NOT_DECLARED where they are absent. Every expected render is written out
 * in full from the supplied strings, so the test pins both the layout order
 * and the missing-value pattern.
 *
 * The component is a pure function of its props, so its whole behaviour is
 * its static markup: it is rendered with the static renderer of react-dom,
 * part of the existing dependencies. No DOM environment and no new
 * dependency.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { RotationRibbon } from './RotationRibbon'
import { exampleRotation } from './exampleRotation'
import type { RotationComponent, RotationDefinition } from './exampleRotation'
import { formatString } from '../lib/format'
import { strings } from '../strings'

/** The exact missing renders expected for the reason codes of the example. */
const MISSING_HARVEST = `${strings['ribbon.harvest']}: ${strings['missing.NOT_APPLICABLE']}`
const MISSING_GRAZING = `${strings['ribbon.mgmt_grazing']}: ${strings['missing.NOT_DECLARED']}`
const MISSING_TERMINATION = `${strings['ribbon.mgmt_termination']}: ${strings['missing.NOT_DECLARED']}`

function markupOf(rotation: RotationDefinition = exampleRotation): string {
  return renderToStaticMarkup(<RotationRibbon rotation={rotation} />)
}

/** The markup of each component card, left to right as rendered. */
function cardChunks(markup: string): string[] {
  return markup.split('data-testid="rotation-component"').slice(1)
}

/** The whole visible text of a markup fragment, tags dropped, spaces folded. */
function visibleText(fragment: string): string {
  return fragment.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** The example components in position order. */
function orderedComponents(): RotationComponent[] {
  return [...exampleRotation.components].sort((a, b) => a.position - b.position)
}

/** The sowing date of a component; the example sows every component. */
function sowingDate(component: RotationComponent): string {
  if (component.sowing.missing || component.sowing.date === null) {
    throw new Error('fixture: the example sowing is dated')
  }
  return component.sowing.date
}

/** The source of the sowing of a component; the example sources every sowing. */
function sowingSource(component: RotationComponent): string {
  if (component.sowing.missing || component.sowing.source === undefined) {
    throw new Error('fixture: the example sowing is sourced')
  }
  return component.sowing.source
}

describe('RotationRibbon: the rotation lines above the timeline', () => {
  it('renders the title, the rotation label, the agricultural-year start and the repeats line', () => {
    const markup = markupOf()
    expect(markup).toContain(strings['ribbon.title'])
    expect(markup).toContain(
      formatString(strings['ribbon.rotation_of'], { label: exampleRotation.label }),
    )
    expect(markup).toContain(
      formatString(strings['ribbon.ag_year_start'], {
        month: exampleRotation.ag_year_start.month,
      }),
    )
    expect(markup).toContain(strings['ribbon.repeats'])
  })

  it('carries the month number of the contract as it travels', () => {
    expect(exampleRotation.ag_year_start.month).toBe(7)
    expect(markupOf()).toContain('Agricultural year starts in month 7')
  })

  it('shows the example banner of the example rotation', () => {
    expect(markupOf()).toContain(strings['example.banner'])
  })
})

describe('RotationRibbon: the timeline', () => {
  it('renders the components left to right in position order, whatever order the file lists', () => {
    const shuffled: RotationDefinition = {
      ...exampleRotation,
      components: [...exampleRotation.components].reverse(),
    }
    const chunks = cardChunks(markupOf(shuffled))
    expect(chunks).toHaveLength(3)
    const ordered = orderedComponents()
    chunks.forEach((chunk, index) => {
      expect(chunk).toContain(`Component ${ordered[index].position}`)
      expect(chunk).toContain(ordered[index].crop_id)
    })
    // The heading of each card names its position, in ascending order.
    expect(chunks[0]).toContain('Component 1')
    expect(chunks[1]).toContain('Component 2')
    expect(chunks[2]).toContain('Component 3')
  })

  it('each card shows the crop, the purpose and the sowing date with its provenance', () => {
    const chunks = cardChunks(markupOf())
    expect(chunks).toHaveLength(3)
    for (const component of orderedComponents()) {
      const text = visibleText(chunks[component.position - 1])
      expect(text).toContain(`${strings['ribbon.crop']}: ${component.crop_id}`)
      expect(text).toContain(`${strings['ribbon.purpose']}: ${component.purpose}`)
      expect(text).toContain(
        `${strings['ribbon.sowing']}: ${sowingDate(component)} ${strings['provenance.DECLARED']}`,
      )
      expect(text).toContain(
        formatString(strings['value.source'], { source: sowingSource(component) }),
      )
      expect(text).toContain(strings['ribbon.management'])
    }
  })

  it('shows both dates on the component that carries them', () => {
    const first = visibleText(cardChunks(markupOf())[0])
    expect(first).toContain(
      `${strings['ribbon.sowing']}: 2027-11-15 ${strings['provenance.DECLARED']}`,
    )
    expect(first).toContain(
      `${strings['ribbon.harvest']}: 2028-04-10 ${strings['provenance.DECLARED']}`,
    )
  })

  it('a missing harvest shows the missing pattern with its reason, never a blank', () => {
    const markup = markupOf()
    // The cover crop and the pasture each miss a harvest, each with a reason.
    expect(markup.match(new RegExp(MISSING_HARVEST, 'g'))).toHaveLength(2)
    const chunks = cardChunks(markup)
    expect(visibleText(chunks[1])).toContain(MISSING_HARVEST)
    expect(visibleText(chunks[2])).toContain(MISSING_HARVEST)
    // No harvest row is blank: every card names its harvest, dated or missing.
    for (const chunk of chunks) {
      expect(visibleText(chunk)).toContain(strings['ribbon.harvest'])
    }
  })

  it('renders the management block: residue values, and the missing parts with their reasons', () => {
    const chunks = cardChunks(markupOf()).map(visibleText)
    // Component 1: residue present, grazing and termination missing with reasons.
    expect(chunks[0]).toContain(`${strings['ribbon.mgmt_residue']}: left_on_surface`)
    expect(chunks[0]).toContain(MISSING_GRAZING)
    expect(chunks[0]).toContain(MISSING_TERMINATION)
    // Component 2: grazing missing, termination dated with its method.
    expect(chunks[1]).toContain(MISSING_GRAZING)
    expect(chunks[1]).toContain(`${strings['ribbon.mgmt_termination']}: 2028-08-15 chemical`)
    // Component 3: grazing carried as an intensity, termination missing.
    expect(chunks[2]).toContain(`${strings['ribbon.mgmt_grazing']}: PLACEHOLDER_light`)
    expect(chunks[2]).toContain(MISSING_TERMINATION)
    // Every card carries a residue value, as the example travels one.
    for (const chunk of chunks) {
      expect(chunk).toContain(`${strings['ribbon.mgmt_residue']}: left_on_surface`)
    }
  })
})
