import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { formatString } from '../lib/format'
import { parsePlantRequestRotations } from '../plant/rotationStrip'
import { strings } from '../strings'
import { RotationBuilder, copyName } from './RotationBuilder'
import {
  MAX_ROTATIONS,
  MIN_ROTATIONS,
  cropCatalogue,
  draftProblems,
  duplicateRotation,
  exampleRotations,
  isUserRotation,
  normalizeDraft,
  removeRotation,
  renameRotation,
  sameDraft,
  setComponentDate,
  gridOf,
  setSlot,
  soybeanCropIds,
} from './rotationDraft'
import type { DraftRotation } from './rotationDraft'

/**
 * Acceptance test of the rotations a user puts together on the board
 * (l3/board). PROPOSED. Every expected value is read from the example plant
 * request; dates set in a case are test inputs of the user, not values of
 * the science.
 *
 * (1) the draft starts as the rotations of the request, and the crops to
 *     build from are those it declares;
 * (2) duplicate, rename, remove; crops in and out; dates;
 * (3) every draft a user can reach is still a rotation the screen can read;
 * (4) what keeps a draft from being compared;
 * (5) the builder: nothing is sent while editing.
 */

/** The request with these rotations, read by the parser of the screen: throws if one is not a rotation definition. */
function parsed(rotations: DraftRotation[]) {
  return parsePlantRequestRotations({ ...rawRequest, rotations })
}

describe('the start of a draft (1)', () => {
  it('is the rotations of the example request, as a copy', () => {
    const draft = exampleRotations()
    expect(draft).toEqual(rawRequest.rotations)
    draft[0].label = 'changed'
    expect(exampleRotations()[0].label).toBe(rawRequest.rotations[0].label)
  })

  it('the crops to build from are those the request declares facts for, plus wheat and maize of D128, each once', () => {
    const ids = cropCatalogue().map((crop) => crop.crop_id)
    for (const crop of rawRequest.economic_facts.crops) expect(ids).toContain(crop.crop_id)
    expect(ids).toContain('wheat')
    expect(ids).toContain('maize')
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('each crop sits in the sowing window of its dates', () => {
    const season = Object.fromEntries(cropCatalogue().map((crop) => [crop.crop_id, crop.season]))
    expect(season.wheat).toBe('winter')
    expect(season.maize).toBe('summer')
    expect(season[soybeanCropIds()[0]]).toBe('summer')
  })
})

describe('editing (2)', () => {
  it('duplicates a rotation as a rotation of the user, named as given, and leaves the original', () => {
    const draft = duplicateRotation(exampleRotations(), 1, 'Mine')
    expect(draft.length).toBe(rawRequest.rotations.length + 1)
    const added = draft[draft.length - 1]
    expect(added.label).toBe('Mine')
    expect(isUserRotation(added.rotation_id)).toBe(true)
    expect(added.components).toEqual(rawRequest.rotations[1].components)
    expect(draft.slice(0, -1)).toEqual(rawRequest.rotations)
    expect(new Set(draft.map((r) => r.rotation_id)).size).toBe(draft.length)
  })

  it('never goes past the most rotations a comparison takes', () => {
    let draft = exampleRotations()
    for (let i = 0; i < MAX_ROTATIONS + 2; i += 1) draft = duplicateRotation(draft, 0, `copy ${i}`)
    expect(draft.length).toBe(MAX_ROTATIONS)
    expect(new Set(draft.map((r) => r.rotation_id)).size).toBe(MAX_ROTATIONS)
  })

  it('renames and removes', () => {
    expect(renameRotation(exampleRotations(), 0, 'New name')[0].label).toBe('New name')
    const removed = removeRotation(exampleRotations(), 0)
    expect(removed.map((r) => r.rotation_id)).toEqual(rawRequest.rotations.slice(1).map((r) => r.rotation_id))
  })

  it('reads an example rotation as a grid of years and sowing windows', () => {
    const grid = gridOf(exampleRotations()[2])
    const ids = rawRequest.rotations[2].components.map((c) => c.crop_id)
    expect(grid[0][1]).toMatchObject({ kind: 'sown', crop_id: ids[0] })
    expect(grid[1][0]).toMatchObject({ kind: 'sown', crop_id: ids[1] })
    expect(grid[1][1]).toMatchObject({ kind: 'sown', crop_id: ids[2] })
  })

  it('builds a several-year succession: wheat then second-crop soybean, then maize, and repeats the soybean', () => {
    const soy = soybeanCropIds()[0]
    let draft = exampleRotations()
    draft = setSlot(draft, 0, 0, 'winter', 'wheat')
    draft = setSlot(draft, 0, 1, 'summer', 'maize')
    draft = setSlot(draft, 0, 2, 'summer', soy)
    const rotation = draft[0]
    expect(rotation.components.map((c) => c.crop_id)).toEqual(['wheat', soy, 'maize', soy])
    expect(rotation.components.map((c) => c.position)).toEqual([1, 2, 3, 4])
    // The soybean after the wheat of its year takes the second-crop dates: sown after the wheat harvest.
    expect(rotation.components[1].sowing.date! >= rotation.components[0].harvest.date!).toBe(true)
    expect(draftProblems(draft).some((p) => p.kind === 'overlap')).toBe(false)
    expect(() => parsed(draft)).not.toThrow()
  })

  it('a crop with no harvest continues until the next sowing; clearing a slot takes its crop out', () => {
    const grid = gridOf(exampleRotations()[2], 3)
    expect(grid[2][0].kind).toBe('continues')
    const cleared = setSlot(exampleRotations(), 2, 1, 'summer', null)[2]
    expect(cleared.components.map((c) => c.crop_id)).not.toContain(rawRequest.rotations[2].components[2].crop_id)
  })

  it('a crop sown before the one before it is harvested is a problem', () => {
    let draft = setSlot(exampleRotations(), 0, 0, 'winter', 'wheat')
    draft = setSlot(draft, 0, 0, 'summer', 'maize')
    expect(draftProblems(draft)).toContainEqual({ kind: 'overlap', index: 0, crop_id: 'maize', after: 'wheat' })
  })

  it('sets a date the user declares, and leaves a part that is missing with its reason as it is', () => {
    const draft = exampleRotations()
    const component = draft[1].components[1]
    expect(component.harvest.date).toBeNull()
    const dated = setComponentDate(draft, 1, draft[1].components[0].component_id, 'sowing', '2027-10-01')
    expect(dated[1].components[0].sowing.date).toBe('2027-10-01')
    const untouched = setComponentDate(draft, 1, component.component_id, 'harvest', '2028-09-01')
    expect(untouched[1].components[1].harvest).toEqual(component.harvest)
  })

  it('an emptied date field changes nothing: a date is never cleared to a blank', () => {
    const draft = exampleRotations()
    const id = draft[0].components[0].component_id
    expect(setComponentDate(draft, 0, id, 'sowing', '')).toEqual(draft)
  })
})

describe('a draft stays a rotation the screen can read (3)', () => {
  it('after duplicating, renaming, taking a crop out, bringing one in and dating', () => {
    let draft = duplicateRotation(exampleRotations(), 2, 'Mine')
    const index = draft.length - 1
    draft = renameRotation(draft, index, 'Soybean then pasture')
    draft = setSlot(draft, index, 1, 'winter', null)
    draft = setSlot(duplicateRotation(draft, 0, 'With wheat'), draft.length, 0, 'winter', 'wheat')
    draft = setComponentDate(draft, index, draft[index].components[0].component_id, 'sowing', '2027-11-01')
    expect(() => parsed(draft)).not.toThrow()
    expect(parsed(draft).map((r) => r.label)).toContain('Soybean then pasture')
  })
})

describe('what keeps a draft from being compared (4)', () => {
  it('the example rotations have no problem', () => {
    expect(draftProblems(exampleRotations())).toEqual([])
  })

  it('fewer than the least a comparison needs', () => {
    const draft = removeRotation(exampleRotations(), 0)
    expect(draft.length).toBe(MIN_ROTATIONS - 1)
    expect(draftProblems(draft)).toContainEqual({ kind: 'too_few' })
  })

  it('no rotation sows the soybean crop of the tipping price', () => {
    let draft = exampleRotations()
    draft = draft.map((rotation) => ({
      ...rotation,
      components: rotation.components.filter((c) => !soybeanCropIds().includes(c.crop_id)),
    }))
    expect(draftProblems(draft)).toContainEqual({ kind: 'no_soybean' })
  })

  it('a rotation with no crop, and a rotation with no name', () => {
    let draft = exampleRotations()
    draft = setSlot(draft, 0, 0, 'summer', null)
    expect(draftProblems(draft)).toContainEqual({ kind: 'no_crop', index: 0 })
    expect(draftProblems(renameRotation(exampleRotations(), 1, '  '))).toContainEqual({ kind: 'no_name', index: 1 })
  })
})

describe('dates while typing and when compared (4b)', () => {
  it('a date that passes another crop does not move the crops while the user types; comparing orders them', () => {
    const draft = exampleRotations()
    const [first, second] = draft[1].components
    const typed = setComponentDate(draft, 1, first.component_id, 'sowing', '2029-01-01')
    expect(typed[1].components.map((c) => c.crop_id)).toEqual([first.crop_id, second.crop_id])
    const sent = normalizeDraft(typed)
    expect(sent[1].components.map((c) => c.crop_id)).toEqual([second.crop_id, first.crop_id])
    expect(sent[1].components.map((c) => c.position)).toEqual([1, 2])
  })

  it('a crop harvested before it is sown is a problem, named with its option and crop', () => {
    const draft = exampleRotations()
    const crop = draft[0].components[0]
    const wrong = setComponentDate(draft, 0, crop.component_id, 'harvest', '2020-01-01')
    expect(draftProblems(wrong)).toContainEqual({ kind: 'harvest_before_sowing', index: 0, crop_id: crop.crop_id })
    expect(draftProblems(draft).some((p) => p.kind === 'harvest_before_sowing')).toBe(false)
  })

  it('a copy of an example rotation is named after its crops, never after the example label; a copy of the user\'s keeps their name', () => {
    for (const rotation of exampleRotations()) {
      expect(copyName(rotation)).not.toContain(rotation.label)
      expect(copyName(rotation)).not.toContain('PLACEHOLDER')
    }
    const mine = duplicateRotation(exampleRotations(), 0, 'Mine')
    expect(copyName(mine[mine.length - 1])).toBe('Mine')
  })
})

describe('the builder (5)', () => {
  function render(draft: DraftRotation[], sent: DraftRotation[] = exampleRotations()): string {
    return renderToString(
      <RotationBuilder draft={draft} sent={sent} onChange={() => {}} onCompare={() => {}} onReset={() => {}} />,
    )
  }
  const tag = (html: string, testid: string) => html.split(`data-testid="${testid}"`)[1].split('>')[0]

  it('shows one editor per rotation and how many of the most there are', () => {
    const html = render(exampleRotations())
    expect(html.split('data-testid="board-candidate"').length - 1).toBe(rawRequest.rotations.length)
    expect(html).toContain(
      formatString(strings['board.builder.count'], { n: rawRequest.rotations.length, max: MAX_ROTATIONS }),
    )
  })

  it('unchanged: comparing is not offered, and nothing says it changed', () => {
    const html = render(exampleRotations())
    expect(tag(html, 'board-builder-compare')).toContain('disabled=""')
    expect(html).not.toContain('data-testid="board-builder-changed"')
    expect(html).toContain(strings['board.builder.no_changes'])
  })

  it('changed and valid: comparing is offered and the change is said', () => {
    const draft = duplicateRotation(exampleRotations(), 0, 'Mine')
    expect(sameDraft(draft, exampleRotations())).toBe(false)
    const html = render(draft)
    expect(tag(html, 'board-builder-compare')).not.toContain('disabled=""')
    expect(html).toContain(strings['board.builder.changed'])
  })

  it('changed with a problem: the problem is said and comparing is not offered', () => {
    const html = render(removeRotation(exampleRotations(), 0))
    expect(tag(html, 'board-builder-compare')).toContain('disabled=""')
    expect(html).toContain(formatString(strings['board.builder.problem.too_few'], { min: MIN_ROTATIONS }))
  })

  it('at the most rotations, duplicating is not offered', () => {
    let draft = exampleRotations()
    while (draft.length < MAX_ROTATIONS) draft = duplicateRotation(draft, 0, `copy ${draft.length}`)
    const buttons = render(draft).split('data-testid="board-candidate-duplicate"').slice(1)
    expect(buttons.length).toBe(MAX_ROTATIONS)
    expect(buttons.every((button) => button.split('>')[0].includes('disabled=""'))).toBe(true)
  })
})

describe('an example rotation the user changes becomes theirs', async () => {
  const { asUserRotation } = await import('./rotationDraft')
  it('gets a user identifier and the name given; a user rotation is left as it is', () => {
    const changed = asUserRotation(exampleRotations(), 0, 'wheat, soybean')
    expect(isUserRotation(changed[0].rotation_id)).toBe(true)
    expect(changed[0].label).toBe('wheat, soybean')
    expect(asUserRotation(changed, 0, 'other')).toBe(changed)
  })
})

describe('alfalfa, a crop the backend knows (D72)', async () => {
  const { extraCropIds } = await import('./planStore')
  const { applyFacts, readFacts, withExtraCrops, factsProblems } = await import('./factsDraft')
  it('is in the catalogue as a winter crop sown on 25 April, kept with no harvest, and priced by a declared margin', () => {
    const alfalfa = cropCatalogue().find((crop) => crop.crop_id === 'alfalfa')!
    expect(alfalfa.season).toBe('winter')
    expect(alfalfa.template.sowing.date!.slice(5)).toBe('04-25')
    expect(alfalfa.template.harvest.date).toBeNull()
    const draft = setSlot(exampleRotations(), 0, 1, 'winter', 'alfalfa')
    expect(extraCropIds(draft)).toEqual([{ id: 'alfalfa', kind: 'declared_margin' }])
    const facts = withExtraCrops(readFacts(rawRequest), extraCropIds(draft))
    expect(factsProblems(facts).some((p) => p.key === 'extra.alfalfa.margins.neutral')).toBe(true)
    const typed = { ...facts, extra: { alfalfa: { ...facts.extra.alfalfa, margins: { el_nino: '150', neutral: '170', la_nina: '-20' } } } }
    expect(factsProblems(typed)).toEqual([])
    const sent = applyFacts(rawRequest, typed) as Record<string, unknown>
    const entry = ((sent.economic_facts as Record<string, unknown>).crops as Record<string, unknown>[]).find((c) => c.crop_id === 'alfalfa')!
    expect(entry.kind).toBe('declared_margin')
    expect(() => parsed(draft)).not.toThrow()
  })
})
