import { API_URL } from '../lib/api'

/**
 * The platform route of the seam: POST /api/rotations/run (api/rotations.py).
 *
 * The call is the fetcher boundary of TanStack Query: the hook holds the
 * loading and error state, this module only speaks HTTP. A response exists
 * (status 2xx) and is returned as parsed JSON for the pure parser of the
 * response module; anything else leaves here as an ApiError:
 *
 * - a 4xx/5xx answer carries the one error shape of api/errors.py,
 *   { "error": { "code", "message", "details" } }, and the code travels on;
 * - a connection that fails, or a body that is not the promised shape, is
 *   UNEXPECTED — the interface's own code for "something failed on the
 *   connection".
 *
 * No number, no wording and no code is ever invented here: an error body
 * without a code of the closed list is UNEXPECTED, not a guess.
 */

/** The codes of api/errors.py, plus UNEXPECTED for a failed connection. */
export type ApiErrorCode =
  | 'MALFORMED_JSON'
  | 'INVALID_REQUEST'
  | 'SITE_INVALID'
  | 'ROTATION_INVALID'
  | 'INTERNAL_ERROR'
  | 'NOT_FOUND'
  | 'METHOD_NOT_ALLOWED'
  | 'UNEXPECTED'

const API_ERROR_CODES: readonly ApiErrorCode[] = [
  'MALFORMED_JSON',
  'INVALID_REQUEST',
  'SITE_INVALID',
  'ROTATION_INVALID',
  'INTERNAL_ERROR',
  'NOT_FOUND',
  'METHOD_NOT_ALLOWED',
]

/** An error of the platform route, carrying its code. Never user-visible text. */
export class ApiError extends Error {
  readonly code: ApiErrorCode

  constructor(code: ApiErrorCode) {
    super(code)
    this.name = 'ApiError'
    this.code = code
  }
}

/** The site of a run: which field of which case, and the point that stands for it. */
export interface SiteReference {
  case_id: string
  field_id: string
  latitude: number
  longitude: number
}

/** The request of a run: the site and the rotation, the contract's own shapes. */
export interface RunRotationRequest {
  site: SiteReference
  rotation: Record<string, unknown>
}

/** The route path, with the /api prefix the backend serves under. */
export const RUN_ROTATION_PATH = '/api/rotations/run'

/** The full URL of the route: the base URL of lib/api.ts plus the path. */
export function runRotationUrl(): string {
  const base = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL
  return `${base}${RUN_ROTATION_PATH}`
}

/** The parsed error code of an error body, or UNEXPECTED when there is none. */
async function errorCodeOf(response: Response): Promise<ApiErrorCode> {
  try {
    const body: unknown = await response.json()
    if (
      typeof body === 'object' &&
      body !== null &&
      typeof (body as { error?: unknown }).error === 'object' &&
      (body as { error?: unknown }).error !== null
    ) {
      const code = (body as { error: { code?: unknown } }).error.code
      if (
        typeof code === 'string' &&
        (API_ERROR_CODES as readonly string[]).includes(code)
      ) {
        return code as ApiErrorCode
      }
    }
  } catch {
    // A body that is not JSON carries no code: UNEXPECTED below.
  }
  return 'UNEXPECTED'
}

/**
 * Run one rotation through the platform route. Resolves with the parsed JSON
 * of a 2xx answer (always the success envelope of api/rotations.py, also when
 * nothing could be computed); rejects with an ApiError for every 4xx/5xx
 * answer and for a failed connection.
 */
export async function runRotation(
  site: SiteReference,
  rotation: Record<string, unknown>,
): Promise<unknown> {
  const body: RunRotationRequest = { site, rotation }
  return postToRoute(runRotationUrl(), body)
}

/**
 * POST a JSON body to a platform route, with the rules above: the parsed
 * JSON of a 2xx answer, or an ApiError carrying the code of the error shape
 * of api/errors.py, or UNEXPECTED for a failed connection or a body that is
 * not JSON. Shared by every route the interface calls.
 */
export async function postToRoute(url: string, body: unknown): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    // fetch rejects only for a connection that failed: network, DNS, CORS.
    throw new ApiError('UNEXPECTED')
  }
  if (!response.ok) {
    throw new ApiError(await errorCodeOf(response))
  }
  try {
    return await response.json()
  } catch {
    throw new ApiError('UNEXPECTED')
  }
}
