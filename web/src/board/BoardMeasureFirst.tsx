import { useQuery } from '@tanstack/react-query'
import { missingPatternText } from '../components/ValueDisplay'
import { MeasureFirstBlock } from '../decision/DecisionSection'
import { parseRunDecision, RUN_DECISION_PATH } from '../decision/decisionRoute'
import type { DecisionAnswer } from '../decision/decisionRoute'
import { formatString } from '../lib/format'
import type { PlantAnswer } from '../plant/plantData'
import { ApiError, postToRoute } from '../seam/runRotationApi'
import { strings } from '../strings'

/**
 * What to measure first when the board's answer does not pick a rotation
 * (PROPOSED, l3/original-mock): the first two options of the answer sent as a
 * pair to POST /api/decisions/run, and the measure-first ranking the decision
 * layer returns, shown as the decision section shows it. The plant answer
 * itself carries no such ranking; nothing here computes one.
 */

export type MeasurePhase =
  | { kind: 'pending' }
  | { kind: 'failed'; message: string }
  | { kind: 'answered'; answer: DecisionAnswer }

export function BoardMeasureFirstView({ phase, pair, fieldId }: { phase: MeasurePhase; pair: [string, string]; fieldId: string }) {
  return (
    <section data-testid="board-measure-first" className="rounded-2xl border border-fs-border bg-fs-surface px-5 py-4">
      <p className="text-sm text-fs-muted">{formatString(strings['board.measure.pair'], { a: pair[0], b: pair[1] })}</p>
      {phase.kind === 'pending' && <p role="status" className="mt-2 text-sm text-fs-muted">{strings['board.measure.pending']}</p>}
      {phase.kind === 'failed' && <p className="mt-2 text-sm text-fs-error">{phase.message}</p>}
      {phase.kind === 'answered' && phase.answer.kind === 'missing' && (
        <p data-testid="board-measure-missing" className="mt-2 text-sm">
          {missingPatternText(strings['decision.measure_first'], phase.answer.missing)}
        </p>
      )}
      {phase.kind === 'answered' && phase.answer.kind === 'decision' && (
        <MeasureFirstBlock fieldId={fieldId} items={phase.answer.document.measure_first} />
      )}
    </section>
  )
}

/** The pair and its call: only for an answer that picks no rotation, with a backend and two options. */
export default function BoardMeasureFirst({
  answer,
  baseRequest,
  apiBase,
  nameOf,
}: {
  answer: PlantAnswer
  baseRequest: Record<string, unknown>
  apiBase: string
  nameOf: (rotationId: string) => string
}) {
  const ids = answer.options.slice(0, 2).map((option) => option.rotation_id)
  const rotations = (baseRequest.rotations as Record<string, unknown>[]).filter((r) => ids.includes(r.rotation_id as string))
  const site = baseRequest.site as Record<string, unknown>
  const body = { site, rotations }
  const trimmed = apiBase.endsWith('/') ? apiBase.slice(0, -1) : apiBase
  const enabled = answer.chosen === null && rotations.length === 2
  const query = useQuery({
    queryKey: ['board-measure-first', trimmed, body] as const,
    queryFn: async (): Promise<DecisionAnswer> => parseRunDecision(await postToRoute(`${trimmed}${RUN_DECISION_PATH}`, body)),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
  if (!enabled) return null
  const phase: MeasurePhase = query.isError
    ? { kind: 'failed', message: strings[`api.${query.error instanceof ApiError ? query.error.code : 'UNEXPECTED'}`] }
    : query.data === undefined
      ? { kind: 'pending' }
      : { kind: 'answered', answer: query.data }
  return (
    <BoardMeasureFirstView phase={phase} pair={[nameOf(ids[0]), nameOf(ids[1])]} fieldId={site.field_id as string} />
  )
}
