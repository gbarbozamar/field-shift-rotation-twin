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
  cropLibrary,
  draftProblems,
  duplicateRotation,
  exampleRotations,
  isUserRotation,
  normalizeDraft,
  removeRotation,
  renameRotation,
  sameDraft,
  setComponentDate,
  soybeanCropIds,
  toggleCrop,
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

  it('the crops to build from are the crops the request declares economic facts for, each once', () => {
    const declared = rawRequest.economic_facts.crops.map((crop) => crop.crop_id).sort()
    expect(cropLibrary().map((component) => component.crop_id).sort()).toEqual(declared)
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

  it('takes a crop out, and brings it back as the request declares it, in sowing order and renumbered', () => {
    const full = rawRequest.rotations[2]
    const crop = full.components[1].crop_id
    const without = toggleCrop(exampleRotations(), 2, crop)[2]
    expect(without.components.map((c) => c.crop_id)).toEqual(
      full.components.filter((c) => c.crop_id !== crop).map((c) => c.crop_id),
    )
    expect(without.components.map((c) => c.position)).toEqual(without.components.map((_, i) => i + 1))
    const back = toggleCrop([without, without, without], 0, crop)[0]
    expect(back.components.map((c) => c.crop_id)).toEqual(full.components.map((c) => c.crop_id))
    expect(back.components.find((c) => c.crop_id === crop)!.sowing).toEqual(
      cropLibrary().find((c) => c.crop_id === crop)!.sowing,
    )
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
    draft = toggleCrop(draft, index, draft[index].components[1].crop_id)
    draft = toggleCrop(duplicateRotation(draft, 0, 'With pasture'), draft.length, cropLibrary()[2].crop_id)
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
    for (const cropId of soybeanCropIds()) {
      draft.forEach((rotation, index) => {
        if (rotation.components.some((c) => c.crop_id === cropId)) draft = toggleCrop(draft, index, cropId)
      })
    }
    expect(draftProblems(draft)).toContainEqual({ kind: 'no_soybean' })
  })

  it('a rotation with no crop, and a rotation with no name', () => {
    let draft = exampleRotations()
    for (const component of rawRequest.rotations[0].components) draft = toggleCrop(draft, 0, component.crop_id)
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
