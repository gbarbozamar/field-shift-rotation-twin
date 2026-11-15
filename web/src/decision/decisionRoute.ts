import type { MissingPart } from '../components/ValueDisplay'
import type { ExampleField } from '../identity/exampleCase'
import { API_URL } from '../lib/api'
import { siteReferenceOf } from '../seam/RotationRun'
import type { RotationDefinitionExample } from '../seam/rotationDefinition'
import { postToRoute } from '../seam/runRotationApi'
import type { SiteReference } from '../seam/runRotationApi'
import { parseLiveData } from '../seam/runRotationResponse'
import { parseDecisionOutput, parseMissing } from './decisionData'
import type { DecisionOutput } from './decisionData'

/**
 * The decision route of the decision section (issue #354, PROPOSED, interface
 * lane under D159 and D161): POST /api/decisions/run (api/decisions.py, D198)
 * runs two rotations of one field and returns the decision output of their
 * pair.
 *
 * This module only speaks HTTP and reads the envelope; the section renders.
 * The call goes through the same fetch boundary as the run seam
 * (postToRoute): a 2xx answer is parsed, every 4xx/5xx answer and a failed
 * connection leave as an ApiError carrying the code of api/errors.py, or
 * UNEXPECTED. The envelope always answers 200 for a valid request, with the
 * decision, or with no decision and the reason the route gives
 * (decision_missing). Nothing is invented: a decision that is not given is
 * never shown as one, and a reason travels as the route wrote it.
 */

/** The route path, with the /api prefix the backend serves under. */
export const RUN_DECISION_PATH = '/api/decisions/run'

/** The full URL of the route: the base URL of lib/api.ts plus the path. */
export function runDecisionUrl(): string {
  const base = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL
  return `${base}${RUN_DECISION_PATH}`
}

/** The request of the route: the site, and two rotation documents unchanged. */
export interface RunDecisionRequest {
  site: SiteReference
  rotations: Record<string, unknown>[]
}

/** How many rotations the route compares: one pair (D198, option 1). */
export const ROTATIONS_PER_REQUEST = 2

/**
 * Call the route. Resolves with the parsed JSON of the 200 envelope; rejects
 * with an ApiError otherwise.
 */
export async function runDecision(request: RunDecisionRequest): Promise<unknown> {
  return postToRoute(runDecisionUrl(), request)
}

/** What the route answered: a decision document, or none with its reason. */
export type DecisionAnswer =
  | { kind: 'decision'; document: DecisionOutput; liveData: boolean }
  | { kind: 'missing'; missing: MissingPart }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * Read the envelope of the route. decision_missing is set exactly when
 * decision is null (api/decisions.py); an envelope that breaks that rule, or
 * a document that does not parse, is an Error, never a guess.
 */
export function parseRunDecision(value: unknown): DecisionAnswer {
  if (!isRecord(value)) {
    throw new Error('invalid-decision-envelope:not-an-object')
  }
  const decision = value.decision
  const missing = value.decision_missing
  if (decision === null || decision === undefined) {
    if (missing === null || missing === undefined) {
      throw new Error('invalid-decision-envelope:no-decision-without-missing-part')
    }
    return {
      kind: 'missing',
      missing: parseMissing(missing, 'invalid-decision-envelope:decision-missing'),
    }
  }
  if (missing !== null && missing !== undefined) {
    throw new Error('invalid-decision-envelope:decision-and-missing-part')
  }
  return {
    kind: 'decision',
    document: parseDecisionOutput(decision),
    liveData: parseLiveData(value.sources),
  }
}

/**
 * The request the interface can make for a selected field, or null when it
 * cannot make one honestly:
 *
 * - the field's geometry yields no point (siteReferenceOf);
 * - the interface does not hold exactly two rotations of that field. The
 *   route compares one pair; with fewer there is no pair, and with more,
 *   which pair to compare is not decided (OPEN), so none is picked.
 *
 * The rotations are the definitions the interface holds, sent unchanged in
 * the order they are held; none is edited or made up.
 */
export function decisionRequestOf(
  caseId: string,
  field: ExampleField,
  held: readonly RotationDefinitionExample[],
): RunDecisionRequest | null {
  const site = siteReferenceOf(caseId, field)
  if (site === null) return null
  const rotations = rotationsOfField(caseId, field.field_id, held)
  if (rotations.length !== ROTATIONS_PER_REQUEST) return null
  return { site, rotations: rotations.map((rotation) => rotation.document) }
}

/** The rotations the interface holds for one field of one case, in the order held. */
export function rotationsOfField(
  caseId: string,
  fieldId: string,
  held: readonly RotationDefinitionExample[],
): RotationDefinitionExample[] {
  return held.filter((rotation) => rotation.case_id === caseId && rotation.field_id === fieldId)
}
