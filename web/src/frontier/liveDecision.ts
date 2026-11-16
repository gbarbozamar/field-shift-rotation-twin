import { exampleCase } from '../identity/exampleCase'
import { decisionRequestOf, parseRunDecision, RUN_DECISION_PATH } from '../decision/decisionRoute'
import type { DecisionAnswer } from '../decision/decisionRoute'
import { demoRotationsD128 } from '../decision/demoRotations'
import { postToRoute } from '../seam/runRotationApi'
import NAMES from './pairStateNames.json'

/**
 * The live part of the decision panel (PROPOSED, l3/frontier-showcase): the
 * first field of the example case and the two demonstration rotations held
 * for it, sent to POST /api/decisions/run of the configured backend. The
 * answer is read by the decision section's own parser; nothing here computes.
 * Without a configured backend nothing is called.
 */

/** The request of the panel, or null when the example case holds no pair for its first field. */
export function liveDecisionRequest() {
  const field = exampleCase.fields[0]
  return field === undefined ? null : decisionRequestOf(exampleCase.case_id, field, demoRotationsD128)
}

export function liveDecisionQueryOptions(base: string | null) {
  const request = liveDecisionRequest()
  const trimmed = base === null ? null : base.endsWith('/') ? base.slice(0, -1) : base
  return {
    queryKey: ['frontier-decision', trimmed, request] as const,
    queryFn: async (): Promise<DecisionAnswer> =>
      parseRunDecision(await postToRoute(`${trimmed}${RUN_DECISION_PATH}`, request)),
    enabled: trimmed !== null && request !== null,
    retry: false as const,
    staleTime: Infinity,
    refetchOnWindowFocus: false as const,
  }
}

export type PairTone = 'ok' | 'warn' | 'bad' | 'neutral'

/**
 * The colour of a pair state name of the decision output contract (D88, D97):
 * a robust preference is green, not robust across scenarios is amber, not
 * separated is red, identical is neutral. The name itself is shown verbatim;
 * the names are those of contracts/decision_output/models.py (StateName),
 * checked against it by the test.
 */
export function pairTone(value: string): PairTone {
  if (value === NAMES.robust) return 'ok'
  if (value === NAMES.notRobust) return 'warn'
  if (value.startsWith(NAMES.notSeparatedPrefix)) return 'bad'
  return 'neutral'
}
