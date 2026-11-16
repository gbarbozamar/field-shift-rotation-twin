import { formatString } from '../lib/format'
import { strings } from '../strings'
import { cropName } from './boardModel'
import { useState } from 'react'
import {
  asUserRotation,
  MAX_ROTATIONS,
  MIN_ROTATIONS,
  SEASONS,
  cropCatalogue,
  draftProblems,
  dropLastRow,
  duplicateRotation,
  gridOf,
  isUserRotation,
  removeRotation,
  renameRotation,
  sameDraft,
  setComponentDate,
  setSlot,
} from './rotationDraft'
import type { DraftProblem, DraftRotation, Season, SlotContent } from './rotationDraft'

/**
 * The candidates of the plan (PROPOSED, l3/board): the rotations that will be
 * compared, each one editable. "Duplicate and edit": a rotation is copied,
 * named, given or relieved of crops the request declares, and dated by the
 * user. Nothing is sent while the user edits: "Compare these rotations"
 * sends them, so every edit has one visible consequence.
 */

const FIRST_LETTER = 65

function problemText(problem: DraftProblem): string {
  switch (problem.kind) {
    case 'too_few':
      return formatString(strings['board.builder.problem.too_few'], { min: MIN_ROTATIONS })
    case 'too_many':
      return formatString(strings['board.builder.problem.too_many'], { max: MAX_ROTATIONS })
    case 'no_soybean':
      return strings['board.builder.problem.no_soybean']
    case 'no_crop':
      return formatString(strings['board.builder.problem.no_crop'], {
        letter: String.fromCharCode(FIRST_LETTER + problem.index),
      })
    case 'no_name':
      return formatString(strings['board.builder.problem.no_name'], {
        letter: String.fromCharCode(FIRST_LETTER + problem.index),
      })
    case 'overlap':
      return formatString(strings['board.builder.problem.overlap'], {
        letter: String.fromCharCode(FIRST_LETTER + problem.index),
        crop: cropName(problem.crop_id),
        after: cropName(problem.after),
      })
    case 'harvest_before_sowing':
      return formatString(strings['board.builder.problem.harvest_before_sowing'], {
        letter: String.fromCharCode(FIRST_LETTER + problem.index),
        crop: cropName(problem.crop_id),
      })
  }
}

/** A rotation named after its crops, in sowing order, each once. */
function cropsName(rotation: DraftRotation): string {
  const crops = [...new Set(rotation.components.map((component) => cropName(component.crop_id)))]
  return crops.join(strings['board.crops_join'])
}

/** What a copy is named after: the name the user gave, or the crops of a rotation of the example. */
export function copyName(rotation: DraftRotation): string {
  if (isUserRotation(rotation.rotation_id)) {
    return rotation.label
  }
  const crops = [...new Set(rotation.components.map((component) => cropName(component.crop_id)))]
  return crops.join(strings['board.crops_join'])
}

const EMPTY = ''

function slotValue(content: SlotContent): string {
  return content.kind === 'sown' ? content.crop_id : EMPTY
}

function slotLabel(content: SlotContent): string {
  return content.kind === 'continues'
    ? formatString(strings['board.builder.slot.continues'], { crop: cropName(content.crop_id) })
    : strings['board.builder.slot.empty']
}

/**
 * The rotation as a grid: one row per year, a winter and a summer slot in
 * each, every slot a choice among the crops of the catalogue sown in that
 * season. A crop with no harvest (a cover crop, a pasture) shows as
 * continuing in the slots it still stands in.
 */
function SeasonGrid({
  rotation,
  index,
  rotations,
  onChange,
}: {
  rotation: DraftRotation
  index: number
  rotations: DraftRotation[]
  onChange: (rotations: DraftRotation[]) => void
}) {
  // Rows the user added stay until removed, even before a crop is put in them.
  const [rowsWanted, setRowsWanted] = useState(1)
  const grid = gridOf(rotation, rowsWanted)
  const catalogue = cropCatalogue()
  const letter = String.fromCharCode(FIRST_LETTER + index)
  return (
    <div data-testid="board-season-grid" className="mt-3">
      <div className="grid grid-cols-[4.5rem_minmax(0,1fr)_minmax(0,1fr)] gap-1.5 text-sm">
        <span />
        {SEASONS.map((season) => (
          <span key={season} className="font-mono text-[10px] uppercase tracking-widest text-fs-muted">
            {strings[`board.builder.season.${season}`]}
          </span>
        ))}
        {grid.map((row, r) => (
          <div key={r} className="contents">
            <span className="self-center text-xs font-semibold text-fs-muted">
              {formatString(strings['board.builder.year'], { n: r + 1 })}
            </span>
            {SEASONS.map((season: Season, s) => {
              const content = row[s]
              return (
                <select
                  key={season}
                  data-testid="board-slot"
                  data-content={content.kind}
                  aria-label={formatString(strings['board.builder.slot_label'], {
                    letter,
                    n: r + 1,
                    season: strings[`board.builder.season.${season}`],
                  })}
                  value={slotValue(content)}
                  onChange={(event) => {
                    const next = setSlot(rotations, index, r, season, event.target.value === EMPTY ? null : event.target.value)
                    // An example rotation the user changes becomes theirs, named after its crops.
                    onChange(asUserRotation(next, index, cropsName(next[index])))
                  }}
                  className="min-h-10 w-full min-w-0 rounded-lg border border-fs-border bg-fs-bg px-2 data-[content=continues]:italic data-[content=sown]:border-fs-primary data-[content=sown]:bg-fs-selection data-[content=sown]:font-semibold"
                >
                  <option value={EMPTY}>{slotLabel(content)}</option>
                  {catalogue
                    .filter((crop) => crop.season === season)
                    .map((crop) => (
                      <option key={crop.crop_id} value={crop.crop_id}>
                        {cropName(crop.crop_id)}
                      </option>
                    ))}
                </select>
              )
            })}
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-fs-muted">{strings['board.builder.cycle_note']}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="board-add-year"
          className="min-h-9 cursor-pointer rounded-lg border border-fs-border px-3 text-sm font-semibold"
          onClick={() => setRowsWanted(grid.length + 1)}
        >
          {strings['board.builder.add_year']}
        </button>
        <button
          type="button"
          data-testid="board-remove-year"
          disabled={grid.length <= 1}
          className="min-h-9 cursor-pointer rounded-lg border border-fs-border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => {
            onChange(dropLastRow(rotations, index, grid.length))
            setRowsWanted(grid.length - 1)
          }}
        >
          {strings['board.builder.remove_year']}
        </button>
      </div>
    </div>
  )
}

function RotationEditor({
  rotation,
  index,
  rotations,
  onChange,
}: {
  rotation: DraftRotation
  index: number
  rotations: DraftRotation[]
  onChange: (rotations: DraftRotation[]) => void
}) {
  const letter = String.fromCharCode(FIRST_LETTER + index)
  return (
    <li data-testid="board-candidate" className="min-w-0 fs-card p-4">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[11px] uppercase tracking-widest text-fs-muted">
          {formatString(strings['board.option'], { letter })}
        </span>
        <span className="flex-1" />
        <button
          type="button"
          data-testid="board-candidate-duplicate"
          disabled={rotations.length >= MAX_ROTATIONS}
          className="min-h-9 cursor-pointer rounded-lg border border-fs-border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() =>
            onChange(
              duplicateRotation(
                rotations,
                index,
                formatString(strings['board.builder.copy_name'], { name: copyName(rotation) }),
              ),
            )
          }
        >
          {strings['board.builder.duplicate']}
        </button>
        <button
          type="button"
          data-testid="board-candidate-remove"
          className="min-h-9 cursor-pointer rounded-lg border border-fs-border px-3 text-sm font-semibold text-fs-error"
          onClick={() => onChange(removeRotation(rotations, index))}
        >
          {strings['board.builder.remove']}
        </button>
      </div>
      <label className="mt-2 block">
        <span className="font-mono text-[10px] uppercase tracking-widest text-fs-muted">{strings['board.builder.name']}</span>
        <input
          type="text"
          data-testid="board-candidate-name"
          className="mt-0.5 w-full rounded-lg border border-fs-border bg-fs-bg px-3 py-1.5 font-fs-heading text-lg font-bold"
          value={rotation.label}
          onChange={(event) => onChange(renameRotation(rotations, index, event.target.value))}
        />
      </label>
      <SeasonGrid rotation={rotation} index={index} rotations={rotations} onChange={onChange} />
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-semibold text-fs-muted">{strings['board.builder.dates']}</summary>
      <ul className="mt-3 space-y-2">
        {rotation.components.map((component) => (
          <li key={component.component_id} data-testid="board-candidate-crop" className="grid grid-cols-2 items-end gap-2 text-sm sm:grid-cols-[minmax(0,1fr)_auto_auto]">
            <span className="col-span-2 font-semibold sm:col-span-1">
              {cropName(component.crop_id)}
            </span>
            {(['sowing', 'harvest'] as const).map((part) => (
              <label key={part} className="block">
                <span className="block font-mono text-[10px] uppercase tracking-widest text-fs-muted">
                  {strings[`board.builder.${part}`]}
                </span>
                {component[part].date !== null ? (
                  <input
                    type="date"
                    className="w-full min-w-0 rounded-lg border border-fs-border bg-fs-bg px-2 py-1 tabular-nums"
                    value={component[part].date}
                    onChange={(event) =>
                      onChange(setComponentDate(rotations, index, component.component_id, part, event.target.value))
                    }
                  />
                ) : (
                  <span className="block px-2 py-1 italic text-fs-muted">{strings['missing.NOT_APPLICABLE']}</span>
                )}
              </label>
            ))}
          </li>
        ))}
      </ul>
      </details>
    </li>
  )
}

/**
 * The step of the candidates: the rotations of the draft, each editable; the
 * problems that keep them from being compared; and the two actions, compare
 * them and go back to the rotations of the example.
 */
export function RotationBuilder({
  draft,
  sent,
  onChange,
  onCompare,
  onReset,
  factsBlocked = false,
  factsChanged = false,
}: {
  /** True when a number the comparison needs (below) is missing or wrong: nothing can be sent. */
  factsBlocked?: boolean
  /** True when the numbers below changed: comparing sends them with the rotations. */
  factsChanged?: boolean
  /** The rotations as the user is editing them. */
  draft: DraftRotation[]
  /** The rotations of the comparison shown. */
  sent: DraftRotation[]
  onChange: (rotations: DraftRotation[]) => void
  onCompare: () => void
  onReset: () => void
}) {
  const problems = draftProblems(draft)
  const changed = !sameDraft(draft, sent) || factsChanged
  return (
    <div data-testid="board-builder">
      <p className="mb-2 text-sm text-fs-muted">
        {formatString(strings['board.builder.count'], { n: draft.length, max: MAX_ROTATIONS })}{' '}
        {strings['board.builder.note']}
      </p>
      <ul className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {draft.map((rotation, index) => (
          <RotationEditor
            // By position, not identifier: an example rotation the user changes gets a new identifier,
            // and a remount would drop the focus and the years added to its grid.
            key={index}
            rotation={rotation}
            index={index}
            rotations={draft}
            onChange={onChange}
          />
        ))}
      </ul>
      {problems.length !== 0 ? (
        <ul data-testid="board-builder-problems" role="alert" className="mt-3 list-disc rounded-xl border border-fs-error bg-fs-error-bg py-2 pl-8 pr-4 text-sm text-fs-error">
          {problems.map((problem) => (
            <li key={JSON.stringify(problem)}>{problemText(problem)}</li>
          ))}
        </ul>
      ) : null}
      {factsBlocked && (
        <p data-testid="board-builder-facts-blocked" role="alert" className="mt-3 rounded-xl border border-fs-warning bg-fs-warning-bg px-4 py-2 text-sm text-fs-warning">
          {strings['board.builder.facts_blocked']}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="board-builder-compare"
          disabled={problems.length !== 0 || !changed || factsBlocked}
          className="min-h-11 cursor-pointer rounded-lg bg-fs-primary px-4 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          onClick={onCompare}
        >
          {strings['board.builder.compare']}
        </button>
        <button
          type="button"
          data-testid="board-builder-reset"
          className="min-h-11 cursor-pointer rounded-lg border border-fs-border bg-fs-surface px-4 font-semibold"
          onClick={onReset}
        >
          {strings['board.builder.reset']}
        </button>
        <p
          data-testid={changed ? 'board-builder-changed' : 'board-builder-unchanged'}
          data-changed={String(changed)}
          className="text-sm text-fs-muted data-[changed=true]:font-semibold data-[changed=true]:text-fs-warning"
        >
          {strings[changed ? 'board.builder.changed' : 'board.builder.no_changes']}
        </p>
      </div>
    </div>
  )
}
