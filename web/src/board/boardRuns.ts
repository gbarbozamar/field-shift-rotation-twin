import type { MissingPart } from '../components/ValueDisplay'
import { parseResultsPerRotation } from '../results/resultsData'
import type { ResultsPerRotation } from '../results/resultsData'
import { parseRunRotation } from '../seam/runRotationResponse'
import { ApiError, RUN_ROTATION_PATH, postToRoute } from '../seam/runRotationApi'
import type { ApiErrorCode, RunRotationRequest, SiteReference } from '../seam/runRotationApi'

/**
 * Water and carbon of the options of the board (PROPOSED, l3/original-mock).
 *
 * The plant answer carries margin and soil loss only. For water-deficit
 * exposure and the soil carbon trend, the board runs each compared rotation
 * once through POST /api/rotations/run, with the site and the rotation of
 * the board's own plant request, and shows the result as the route answers
 * it. Nothing is computed here: the envelope is read, its result parsed by
 * the results parser, and every absence keeps its reason.
 *
 * Pure except for the fetcher, which is the query function of TanStack Query.
 */

/** One run of the board: one rotation through the rotation route, with its body. */
export interface BoardRunRequest {
  rotation_id: string
  body: RunRotationRequest
}

/** What a finished run answered: its result, why it has none, or a result the screen cannot read. */
export type BoardRunAnswer =
  | { phase: 'result'; result: ResultsPerRotation }
  | { phase: 'no_result'; missing: MissingPart }
  | { phase: 'unreadable' }

/** The state of one run, as the comparison table shows it. */
export type BoardRun = { phase: 'pending' } | { phase: 'failed'; code: ApiErrorCode } | BoardRunAnswer

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * One run per rotation of the plant request, with the request's site.
 * Empty when there is no request, or it holds no site or no rotations.
 */
export function boardRunRequests(baseRequest: Record<string, unknown> | null): BoardRunRequest[] {
  if (baseRequest === null || !isRecord(baseRequest.site) || !Array.isArray(baseRequest.rotations)) {
    return []
  }
  const site = baseRequest.site as unknown as SiteReference
  return baseRequest.rotations.flatMap((rotation: unknown) =>
    isRecord(rotation) && typeof rotation.rotation_id === 'string'
      ? [{ rotation_id: rotation.rotation_id, body: { site, rotation } }]
      : [],
  )
}

/** The full URL of the rotation route on a base address, its trailing slash stripped. */
export function boardRunUrl(base: string): string {
  const trimmed = base.endsWith('/') ? base.slice(0, -1) : base
  return `${trimmed}${RUN_ROTATION_PATH}`
}

/**
 * Read the success envelope of the rotation route: its result parsed, or the
 * reason it has none. An envelope or a result this screen cannot read is
 * said as such, never shown as something else.
 */
export function readRunEnvelope(envelope: unknown): BoardRunAnswer {
  try {
    const view = parseRunRotation(envelope)
    if (view.resultMissing !== null) {
      return { phase: 'no_result', missing: view.resultMissing }
    }
    return { phase: 'result', result: parseResultsPerRotation((envelope as { result: unknown }).result) }
  } catch {
    return { phase: 'unreadable' }
  }
}

/** The query function of one run: POST, then the envelope read. Rejects with an ApiError. */
export async function fetchBoardRun(base: string, body: RunRotationRequest): Promise<BoardRunAnswer> {
  return readRunEnvelope(await postToRoute(boardRunUrl(base), body))
}

/** The query options of one run: one call per distinct request, no retry, never stale. */
export function boardRunQueryOptions(base: string | null, run: BoardRunRequest, enabled: boolean) {
  return {
    queryKey: ['board-rotation-run', base, run.body] as const,
    queryFn: () => fetchBoardRun(base!, run.body),
    enabled: enabled && base !== null,
    retry: false as const,
    staleTime: Infinity,
  }
}

/** The state of one run from its query. */
export function boardRunOf(query: { isError: boolean; error: unknown; data: BoardRunAnswer | undefined }): BoardRun {
  if (query.isError) {
    return { phase: 'failed', code: query.error instanceof ApiError ? query.error.code : 'UNEXPECTED' }
  }
  return query.data === undefined ? { phase: 'pending' } : query.data
}
