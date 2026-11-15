import { formatString } from '../lib/format'
import { strings } from '../strings'
import { cropName, isExampleCrop } from './boardModel'
import {
  MAX_ROTATIONS,
  MIN_ROTATIONS,
  cropLibrary,
  draftProblems,
  duplicateRotation,
  removeRotation,
  renameRotation,
  sameDraft,
  setComponentDate,
  toggleCrop,
} from './rotationDraft'
import type { DraftProblem, DraftRotation } from './rotationDraft'

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
  }
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
  const library = cropLibrary()
  const letter = String.fromCharCode(FIRST_LETTER + index)
  return (
    <li data-testid="board-candidate" className="rounded-2xl border border-fs-border bg-fs-surface p-4">
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
                formatString(strings['board.builder.copy_name'], { name: rotation.label }),
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
      <fieldset className="mt-3">
        <legend className="font-mono text-[10px] uppercase tracking-widest text-fs-muted">{strings['board.builder.crops']}</legend>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {library.map((crop) => (
            <label
              key={crop.crop_id}
              className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-fs-border bg-fs-bg px-3 text-sm has-[:checked]:border-fs-primary has-[:checked]:bg-fs-selection has-[:checked]:font-semibold"
            >
              <input
                type="checkbox"
                className="accent-fs-primary"
                checked={rotation.components.some((component) => component.crop_id === crop.crop_id)}
                onChange={() => onChange(toggleCrop(rotations, index, crop.crop_id))}
              />
              {cropName(crop.crop_id)}
            </label>
          ))}
        </div>
      </fieldset>
      <ul className="mt-3 space-y-2">
        {rotation.components.map((component) => (
          <li key={component.component_id} data-testid="board-candidate-crop" className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-end gap-2 text-sm">
            <span className="font-semibold">
              {cropName(component.crop_id)}
              {isExampleCrop(component.crop_id) ? (
                <span className="ml-1.5 text-[11px] font-normal text-fs-warning">{strings['board.example_crop']}</span>
              ) : null}
            </span>
            {(['sowing', 'harvest'] as const).map((part) => (
              <label key={part} className="block">
                <span className="block font-mono text-[10px] uppercase tracking-widest text-fs-muted">
                  {strings[`board.builder.${part}`]}
                </span>
                {component[part].date !== null ? (
                  <input
                    type="date"
                    className="rounded-lg border border-fs-border bg-fs-bg px-2 py-1 tabular-nums"
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
}: {
  /** The rotations as the user is editing them. */
  draft: DraftRotation[]
  /** The rotations of the comparison shown. */
  sent: DraftRotation[]
  onChange: (rotations: DraftRotation[]) => void
  onCompare: () => void
  onReset: () => void
}) {
  const problems = draftProblems(draft)
  const changed = !sameDraft(draft, sent)
  return (
    <div data-testid="board-builder">
      <p className="mb-2 text-sm text-fs-muted">
        {formatString(strings['board.builder.count'], { n: draft.length, max: MAX_ROTATIONS })}{' '}
        {strings['board.builder.note']}
      </p>
      <ul className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {draft.map((rotation, index) => (
          <RotationEditor
            key={rotation.rotation_id}
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
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="board-builder-compare"
          disabled={problems.length !== 0 || !changed}
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
        {changed ? (
          <p data-testid="board-builder-changed" className="text-sm font-semibold text-fs-warning">
            {strings['board.builder.changed']}
          </p>
        ) : null}
      </div>
    </div>
  )
}
