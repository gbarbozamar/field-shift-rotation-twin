import { useQuery } from '@tanstack/react-query'
import { missingPatternText } from '../components/ValueDisplay'
import type { DecisionAnswer } from '../decision/decisionRoute'
import { configuredApiBase } from '../plant/plantRoute'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import { c } from './copy'
import { liveDecisionQueryOptions, pairTone } from './liveDecision'
import { Card, Pill } from './ui'

/** What the panel shows of the backend: not configured, asking, failed, or its answer. */
export type LivePhase =
  | { kind: 'not_configured' }
  | { kind: 'pending' }
  | { kind: 'failed'; message: string }
  | { kind: 'answered'; answer: DecisionAnswer }

/** The backend's decision for the first field, shown verbatim (a pure view of the phase). */
export function LiveDecisionView({ phase }: { phase: LivePhase }) {
  return (
    <Card title={c('live.title')}>
      <div data-testid="frontier-live" data-phase={phase.kind}>
        {phase.kind === 'not_configured' && <p className="text-sm text-fs-muted">{c('live.not_configured')}</p>}
        {phase.kind === 'pending' && <p role="status" className="text-sm text-fs-muted">{c('live.pending')}</p>}
        {phase.kind === 'failed' && <p className="text-sm text-fs-error">{phase.message}</p>}
        {phase.kind === 'answered' && phase.answer.kind === 'missing' && (
          <p data-testid="frontier-live-missing" className="text-sm">
            {missingPatternText(c('live.decision_what'), phase.answer.missing)}
          </p>
        )}
        {phase.kind === 'answered' && phase.answer.kind === 'decision' && (
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-xs text-fs-muted">{c('live.state')}</p>
              <p className="font-bold">
                {phase.answer.document.state.value ?? missingPatternText(c('live.decision_what'), phase.answer.document.state.missing)}
              </p>
              <ul className="mt-1 list-disc pl-5 text-fs-muted">
                {phase.answer.document.state.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
            <ul className="space-y-1">
              {phase.answer.document.pair_states.map((pair) => (
                <li key={pair.pair.join('|')} className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs">{pair.pair.join(' / ')}</span>
                  {pair.value !== null ? (
                    <Pill tone={pairTone(pair.value)}>{pair.value}</Pill>
                  ) : (
                    <Pill tone="neutral">{missingPatternText(c('live.pair_not_evaluated'), pair.missing)}</Pill>
                  )}
                </li>
              ))}
            </ul>
            <div>
              <p className="text-xs text-fs-muted">{c('live.measure')}</p>
              {phase.answer.document.measure_first.length === 0 ? (
                <p>{c('live.measure_none')}</p>
              ) : (
                <ol className="list-decimal pl-5">
                  {phase.answer.document.measure_first.map((item) => (
                    <li key={item.rank}>
                      <span className="font-semibold">{item.what}</span>
                      <span className="text-fs-muted"> - {item.why}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        )}
        <p className="mt-3 text-xs text-fs-muted">{c('live.synthetic_below')}</p>
      </div>
    </Card>
  )
}

/** The card with its call: the configured backend (VITE_API_URL), or none. */
export default function LiveDecision({ base = configuredApiBase() }: { base?: string | null }) {
  const query = useQuery(liveDecisionQueryOptions(base))
  const phase: LivePhase =
    base === null
      ? { kind: 'not_configured' }
      : query.isError
        ? { kind: 'failed', message: strings[`api.${query.error instanceof ApiError ? query.error.code : 'UNEXPECTED'}`] }
        : query.data === undefined
          ? { kind: 'pending' }
          : { kind: 'answered', answer: query.data }
  return (
    <LiveDecisionView phase={phase} />
  )
}
