import { exampleCase } from '../identity/exampleCase'
import { useSelectedFieldId } from '../identity/selection'
import { exampleRotation } from '../rotation/exampleRotation'
import { useRunAnswered } from '../seam/runAnswer'
import { strings } from '../strings'

/**
 * The stage rail of the fields screen (issue #435): the case in six ordered
 * stages, each with the state it is really in — done, the one stage the
 * reader is on, or waiting with the reason it waits for. Every state reads
 * a signal the screen already holds: the case stage when the example case
 * carries its label, the field stage when the selection store holds a
 * field, the rotations stage when the selected field is the example
 * rotation's field, the compare stage when the seam's run has answered,
 * the decision stage when a field is selected, and the handoff stage when
 * the decision is done and the run answered. The first stage not done is
 * the one the reader is on; when all six are done, the handoff closes the
 * case. No state is invented and nothing is measured: the rail names where
 * the reader is, it draws no percentage.
 */

/** One stage of the rail: its name, whether it is done, its waiting reason. */
interface Stage {
  name: string
  done: boolean
  reason: string
}

export default function StageRail() {
  const selectedFieldId = useSelectedFieldId()
  const runAnswered = useRunAnswered()

  const stages: Stage[] = [
    {
      name: strings['rail.stage.case'],
      // the case stage is done when the screen really holds an open case
      // (its label), not by a hard-coded flag; today the parser guarantees
      // a label, so the waiting reason never shows
      done: exampleCase.label !== '',
      reason: strings['rail.waiting.case'],
    },
    {
      name: strings['rail.stage.field'],
      done: selectedFieldId !== null,
      reason: strings['rail.waiting.field'],
    },
    {
      name: strings['rail.stage.rotations'],
      done: selectedFieldId === exampleRotation.field_id,
      reason: strings['rail.waiting.rotations'],
    },
    {
      name: strings['rail.stage.compare'],
      done: runAnswered,
      reason: strings['rail.waiting.compare'],
    },
    {
      name: strings['rail.stage.decision'],
      done: selectedFieldId !== null,
      reason: strings['rail.waiting.decision'],
    },
    {
      name: strings['rail.stage.handoff'],
      done: selectedFieldId !== null && runAnswered,
      reason: strings['rail.waiting.handoff'],
    },
  ]

  // The reader is on the first stage not done; with every stage done, the
  // handoff closes the case. Exactly one stage is the current one.
  const firstNotDone = stages.findIndex((stage) => !stage.done)
  const currentIndex = firstNotDone === -1 ? stages.length - 1 : firstNotDone

  return (
    <ol
      data-testid="stage-rail"
      aria-label={strings['rail.label']}
      className="mt-4 space-y-2 min-[1100px]:flex min-[1100px]:flex-row min-[1100px]:flex-wrap min-[1100px]:gap-2 min-[1100px]:space-y-0"
    >
      {stages.map((stage, index) => {
        const isCurrent = index === currentIndex
        const nameClass = isCurrent
          ? ['font-semibold', 'text-fs-primary'].join(' ')
          : stage.done
            ? 'text-fs-muted'
            : 'text-fs-text'
        return (
          <li
            key={stage.name}
            data-testid={`stage-rail-item-${index + 1}`}
            aria-current={isCurrent ? 'step' : undefined}
            className={[
              'flex',
              'flex-wrap',
              'items-baseline',
              'gap-x-2',
              'gap-y-0.5',
              'rounded-lg',
              'border',
              'border-fs-border',
              'bg-fs-surface',
              'px-3',
              'py-2',
              'text-sm',
            ].join(' ')}
          >
            <span className={nameClass}>{stage.name}</span>
            {stage.done ? (
              <span className="text-fs-muted">{strings['rail.state.done']}</span>
            ) : (
              <>
                <span className="text-fs-muted">{strings['rail.state.waiting']}</span>
                <span className="text-fs-muted">{stage.reason}</span>
              </>
            )}
            {isCurrent ? (
              <span className={['font-semibold', 'text-fs-primary'].join(' ')}>
                {strings['rail.state.current']}
              </span>
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}
