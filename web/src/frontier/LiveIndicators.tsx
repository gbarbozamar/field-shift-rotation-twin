import { useQueries } from '@tanstack/react-query'
import { missingPatternText, ValueDisplay } from '../components/ValueDisplay'
import { rotationsOfField } from '../decision/decisionRoute'
import { demoRotationsD128 } from '../decision/demoRotations'
import { exampleCase } from '../identity/exampleCase'
import { configuredApiBase } from '../plant/plantRoute'
import { siteReferenceOf } from '../seam/RotationRun'
import { ApiError, postToRoute, RUN_ROTATION_PATH } from '../seam/runRotationApi'
import { parseRunRotation } from '../seam/runRotationResponse'
import type { RunRotationView } from '../seam/runRotationResponse'
import { strings } from '../strings'
import { c } from './copy'
import { Card } from './ui'

/**
 * The live part of the stress-test panel (PROPOSED, l3/frontier-showcase):
 * each demonstration rotation of Field 1 sent once to POST /api/rotations/run
 * of the configured backend, its indicators shown verbatim with the shared
 * value display (value, unit, provenance, source) or the reason the run gives
 * none. The backend runs the observed record only: the three horizons and
 * their stress cases stay synthetic, and the card says so.
 */

export type RunPhase =
  | { kind: 'pending' }
  | { kind: 'failed'; message: string }
  | { kind: 'answered'; view: RunRotationView }

export interface LiveRun {
  label: string
  phase: RunPhase
}

function RunBlock({ run }: { run: LiveRun }) {
  return (
    <li className="rounded-lg border border-fs-border p-3">
      <p className="font-bold">{run.label}</p>
      {run.phase.kind === 'pending' && <p role="status" className="text-sm text-fs-muted">{c('live.kpi_pending')}</p>}
      {run.phase.kind === 'failed' && <p className="text-sm text-fs-error">{run.phase.message}</p>}
      {run.phase.kind === 'answered' && run.phase.view.resultMissing !== null && (
        <p data-testid="frontier-kpi-missing" className="text-sm">
          {missingPatternText(c('live.kpi_result_what'), run.phase.view.resultMissing)}
        </p>
      )}
      {run.phase.kind === 'answered' && run.phase.view.resultMissing === null && (
        <ul className="mt-1 space-y-1 text-sm">
          {run.phase.view.parts.flatMap((part) =>
            part.rows.map((row) => (
              <li key={`${part.indicator}:${row.what}`}>
                <ValueDisplay what={row.what} item={row.item} />
              </li>
            )),
          )}
        </ul>
      )}
    </li>
  )
}

/** The backend's indicators for the rotations of Field 1 (a pure view). */
export function LiveIndicatorsView({ configured, runs }: { configured: boolean; runs: LiveRun[] }) {
  return (
    <Card title={c('live.kpi_title')}>
      <div data-testid="frontier-kpi-live">
        {!configured ? (
          <p className="text-sm text-fs-muted">{c('live.not_configured')}</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {runs.map((run) => (
              <RunBlock key={run.label} run={run} />
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-fs-muted">{c('live.kpi_synthetic_note')}</p>
      </div>
    </Card>
  )
}

/** The rotations of Field 1 and the request of each, or none when the case holds none. */
export function liveRunRequests() {
  const field = exampleCase.fields[0]
  const site = field === undefined ? null : siteReferenceOf(exampleCase.case_id, field)
  if (field === undefined || site === null) return []
  return rotationsOfField(exampleCase.case_id, field.field_id, demoRotationsD128).map((rotation) => ({
    label: rotation.label,
    body: { site, rotation: rotation.document },
  }))
}

export default function LiveIndicators({ base = configuredApiBase() }: { base?: string | null }) {
  const trimmed = base === null ? null : base.endsWith('/') ? base.slice(0, -1) : base
  const requests = liveRunRequests()
  const queries = useQueries({
    queries: requests.map((request) => ({
      queryKey: ['frontier-run', trimmed, request.body] as const,
      queryFn: async (): Promise<RunRotationView> =>
        parseRunRotation(await postToRoute(`${trimmed}${RUN_ROTATION_PATH}`, request.body)),
      enabled: trimmed !== null,
      retry: false as const,
      staleTime: Infinity,
      refetchOnWindowFocus: false as const,
    })),
  })
  const runs: LiveRun[] = requests.map((request, i) => {
    const query = queries[i]
    const phase: RunPhase = query.isError
      ? { kind: 'failed', message: strings[`api.${query.error instanceof ApiError ? query.error.code : 'UNEXPECTED'}`] }
      : query.data === undefined
        ? { kind: 'pending' }
        : { kind: 'answered', view: query.data }
    return { label: request.label, phase }
  })
  return (
    <LiveIndicatorsView configured={trimmed !== null} runs={runs} />
  )
}
