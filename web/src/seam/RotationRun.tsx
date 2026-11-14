import { useMutation } from '@tanstack/react-query'
import { ValueDisplay, missingPattern } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import type { ExampleField } from '../identity/exampleCase'
import { useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { rotationDefinition } from './rotationDefinition'
import { ApiError, runRotation } from './runRotationApi'
import type { SiteReference } from './runRotationApi'
import { parseRunRotation } from './runRotationResponse'
import type { RunRotationView } from './runRotationResponse'

/**
 * The CP1 seam (issue #119): the interface stops reading the site-data
 * example for one rotation and calls the platform route instead. For the
 * selected field that matches the example rotation's field, one action runs
 * that rotation end to end through POST /api/rotations/run on real NASA POWER
 * data; the response renders below through the shared value display — every
 * value with its unit, provenance, source and range, every absence as a
 * missing value with its reason, never zero.
 *
 * The action shows only when a request is honestly supported: the rotation's
 * case and field ids must match the example case and the selected field, and
 * the field's geometry must yield the point that stands for it. Otherwise the
 * seam shows nothing rather than inventing data.
 *
 * The panel is a pure function of its state (idle, pending, error, success),
 * so its whole behaviour is its static markup in the tests; the container
 * holds the state in one TanStack Query mutation whose fetcher is the
 * platform-route call of runRotationApi.ts.
 */

/**
 * The point that stands for a field: the centre of the bounding box of its
 * exterior ring, in decimal degrees. How the point is chosen for a field is
 * OPEN (adapters/ports.py); this is the seam's PROPOSED choice — derived from
 * the declared geometry alone, never hand-picked. Null when the geometry
 * yields no usable point: nothing is invented to fill it.
 */
export function siteReferenceOf(caseId: string, field: ExampleField): SiteReference | null {
  const ring = field.geometry.coordinates[0]
  if (ring === undefined || ring.length === 0) return null
  let south = Infinity
  let north = -Infinity
  let west = Infinity
  let east = -Infinity
  for (const position of ring) {
    const lng = position[0]
    const lat = position[1]
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null
    if (lat < south) south = lat
    if (lat > north) north = lat
    if (lng < west) west = lng
    if (lng > east) east = lng
  }
  const latitude = (south + north) / 2
  const longitude = (west + east) / 2
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
    return null
  }
  return { case_id: caseId, field_id: field.field_id, latitude, longitude }
}

/** The state of the run, as the panel renders it. */
export type RotationRunState =
  | { phase: 'idle' }
  | { phase: 'pending' }
  | { phase: 'error'; error: unknown }
  | { phase: 'success'; view: RunRotationView }

/** Props of the panel: its state, the run action, and the rotation's label. */
export interface RotationRunPanelProps {
  state: RotationRunState
  onRun: () => void
  runName: string
}

/** One failed run: its code's own string and the raw code, or the shared error. */
function RotationRunError({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    return (
      <div data-testid="rotation-run-error" role="alert" className="mt-2">
        <p className="text-sm text-red-700">{strings[`api.${error.code}`]}</p>
        <p data-testid="rotation-run-error-code" className="text-xs text-slate-500">
          {formatString(strings['api.code.shown'], { code: error.code })}
        </p>
      </div>
    )
  }
  return (
    <div data-testid="rotation-run-error" role="alert" className="mt-2">
      <p className="text-sm text-red-700">{strings['common.error']}</p>
    </div>
  )
}

/** The response below the action: the label of real data, then every value. */
function RunResult({ view, runName }: { view: RunRotationView; runName: string }) {
  return (
    <div data-testid="rotation-run-response" className="mt-3">
      <p data-testid="rotation-run-name" className="font-medium">
        {runName}
      </p>
      {view.liveData ? (
        <p
          data-testid="rotation-run-live"
          className="mt-1 text-sm font-medium text-emerald-700"
        >
          {strings['seam.with_real_data']}
        </p>
      ) : null}
      <p
        data-testid="rotation-run-outcome"
        className="mt-1 font-mono text-xs text-slate-500"
      >
        {view.outcome}
      </p>
      {view.resultMissing !== null ? (
        <p
          data-testid="rotation-run-result-missing"
          className="mt-2 text-sm italic text-slate-500"
        >
          {missingPattern(runName, view.resultMissing)}
        </p>
      ) : (
        view.parts.map((part) => (
          <div key={part.indicator} data-testid="rotation-run-part" className="mt-3">
            <h4 className="text-sm font-semibold">{part.indicator}</h4>
            <ul className="mt-2 space-y-2">
              {part.rows.map((row) => (
                <li key={`${row.what}-${row.item.unit}`}>
                  <ValueDisplay what={row.what} item={row.item} />
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  )
}

/** The seam's panel: the run action, its loading and error, and the response. */
export function RotationRunPanel({ state, onRun, runName }: RotationRunPanelProps) {
  const busy = state.phase === 'pending'
  return (
    <div data-testid="rotation-run" className="mt-8">
      <button
        type="button"
        data-testid="rotation-run-action"
        onClick={onRun}
        disabled={busy}
        className={[
          'rounded-lg',
          'bg-emerald-600',
          'px-4',
          'py-2',
          'text-sm',
          'font-semibold',
          'text-white',
          'transition',
          'hover:bg-emerald-700',
          'disabled:cursor-not-allowed',
          'disabled:opacity-60',
        ].join(' ')}
      >
        {strings['seam.with_real_data']}
      </button>
      {state.phase === 'pending' ? (
        <p data-testid="rotation-run-loading" className="mt-2 text-sm text-slate-500">
          {strings['common.loading']}
        </p>
      ) : null}
      {state.phase === 'error' ? (
        <RotationRunError error={state.error} />
      ) : null}
      {state.phase === 'success' ? (
        <RunResult view={state.view} runName={runName} />
      ) : null}
    </div>
  )
}

/**
 * The seam on the fields view: nothing unless the selected field matches the
 * example rotation's field and its geometry yields the request's point; the
 * action and the response below it when it does.
 */
export default function RotationRun() {
  const selectedFieldId = useSelectedFieldId()
  const field =
    selectedFieldId === null
      ? null
      : (exampleCase.fields.find((f) => f.field_id === selectedFieldId) ?? null)
  const site = field === null ? null : siteReferenceOf(exampleCase.case_id, field)
  const idsMatch =
    field !== null &&
    rotationDefinition.case_id === exampleCase.case_id &&
    rotationDefinition.field_id === field.field_id

  const run = useMutation({
    mutationFn: async (): Promise<RunRotationView> => {
      if (site === null) {
        throw new Error('run-site-unavailable')
      }
      return parseRunRotation(await runRotation(site, rotationDefinition.document))
    },
  })

  if (!idsMatch || site === null) return null

  const state: RotationRunState = run.isPending
    ? { phase: 'pending' }
    : run.isError
      ? { phase: 'error', error: run.error }
      : run.isSuccess && run.data !== undefined
        ? { phase: 'success', view: run.data }
        : { phase: 'idle' }

  return (
    <RotationRunPanel
      state={state}
      onRun={() => run.mutate()}
      runName={rotationDefinition.label}
    />
  )
}
