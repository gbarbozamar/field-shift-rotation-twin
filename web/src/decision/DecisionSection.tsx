import { useQuery } from '@tanstack/react-query'
import { missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import { useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import type { RotationDefinitionExample } from '../seam/rotationDefinition'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import type {
  DecisionOutput,
  DecisionState,
  PairCellCount,
  PairState,
  RangeAcrossScenarios,
} from './decisionData'
import { decisionExample, samePair } from './decisionData'
import { demoRotationsD128 } from './demoRotations'
import {
  ROTATIONS_PER_REQUEST,
  decisionRequestOf,
  parseRunDecision,
  rotationsOfField,
  runDecision,
} from './decisionRoute'
import type { DecisionAnswer, RunDecisionRequest } from './decisionRoute'

/**
 * The decision section (issue #241; the route's document, issue #354,
 * PROPOSED, interface lane under D159 and D161). It renders one decision
 * output document as it travels:
 *
 * - the document POST /api/decisions/run returns for the two rotations the
 *   interface holds for the selected field (decisionRoute.ts) — the two
 *   rotations of D128 for example-field-1 (demoRotations.ts) — with the
 *   live-data label of the seam when the route's climate source answered
 *   real data;
 * - otherwise the bundled contract example, always under the example banner,
 *   after the reason it is shown: the route's own reason when it answered
 *   without a decision (decision_missing), the message and code of its error
 *   or of a failed connection, or, when the interface does not hold a pair of
 *   rotations for the field, the missing pattern of the rotation pairs
 *   (NOT_DECLARED: no second rotation is declared). No call is made then.
 *
 * In a document:
 *
 * - the state of the decision, verbatim, or the missing pattern with its
 *   reason, and its reasons, each a sentence of the decision layer rendered
 *   as data (D7);
 * - one block per rotation pair, named by its two rotations, with the state
 *   of the pair verbatim — the science wording of D88 and D97 travels as
 *   data, and so do its reason (D86) and the rotation a robust preference
 *   prefers (D74); a pair that is not evaluated shows the shared missing
 *   pattern with its reason (D85, C3.1);
 * - the coverage "k of N" (D91);
 * - the two counts of the pair's cells, by point value and by range, shown
 *   apart and never added (D87, D99), each labelled by its indicator, its
 *   scenario and, for soil carbon trend, its carbon model and computation
 *   (D169), rendered as data; a count by point value that does not travel
 *   (no tolerance of "equal") shows the shared missing pattern with its
 *   reason, never zeros;
 * - the years-within summary of each rotation of the pair: the range across
 *   the admitted scenarios with the scenario of the minimum (D96), or the
 *   missing pattern with its reason.
 *
 * The section decides nothing and interprets nothing (D74): no winner is
 * named beyond the document's own preferred rotation and no count is summed.
 * The limits, the counts by year, the paired differences, the tolerances,
 * the indicators not resolved and the measurement priority are not rendered
 * (their labels are not in the wording sheet); nothing is invented for them.
 *
 * The panel is a pure function of its state, so its whole behaviour is its
 * static markup in the tests; the container holds the call in one TanStack
 * Query query. All user-visible wording lives in strings.ts; indicator,
 * scenario, rotation, model, computation and category identifiers render as
 * data, verbatim. Class lists are arrays of single-word tokens joined at
 * runtime.
 */

/** One count row: the label of the category, and the count as it travels. */
function CountRow({ label, count, mono }: { label: string; count: number; mono?: boolean }) {
  return (
    <li
      data-testid="decision-count-row"
      className={['flex', 'gap-2'].join(' ')}
    >
      <span
        data-testid="decision-count-label"
        className={mono ? ['font-mono', 'text-sm'].join(' ') : ['text-sm'].join(' ')}
      >
        {label}
      </span>
      <span data-testid="decision-count-number" className={['text-sm', 'font-medium'].join(' ')}>
        {count}
      </span>
    </li>
  )
}

/**
 * The label of one counted cell of the pair: the indicator identifier and
 * the scenario identifier of the contract, then the carbon model and the
 * computation when the count carries them (D169), rendered as data.
 */
function cellLabel(count: PairCellCount): string {
  return [count.indicator, count.scenario_id, count.carbon_model, count.computation]
    .filter((part): part is string => part !== undefined)
    .join(' ')
}

/** One counted cell: its label, then the two counts apart under their headings. */
function CountGroup({ count }: { count: PairCellCount }) {
  return (
    <div data-testid="decision-counts-group" className={['mt-3'].join(' ')}>
      <p
        data-testid="decision-counts-cell-label"
        className={['font-mono', 'text-xs', 'text-fs-muted'].join(' ')}
      >
        {cellLabel(count)}
      </p>
      <div className={['mt-1'].join(' ')}>
        <p
          data-testid="decision-counts-by-point-heading"
          className={['text-xs', 'font-semibold', 'text-fs-muted'].join(' ')}
        >
          {strings['decision.counts_by_point']}
        </p>
        {count.by_sign_of_point_value !== null ? (
          <ul data-testid="decision-counts-by-point" className={['mt-1', 'space-y-0.5'].join(' ')}>
            <CountRow label={strings['decision.better']} count={count.by_sign_of_point_value.better} />
            <CountRow label={strings['decision.worse']} count={count.by_sign_of_point_value.worse} />
            <CountRow label={strings['decision.equal']} count={count.by_sign_of_point_value.equal} />
            <CountRow
              label={strings['decision.missing_side']}
              count={count.by_sign_of_point_value.missing_side}
            />
          </ul>
        ) : (
          <p
            data-testid="decision-counts-by-point-missing"
            className={['mt-1', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
          >
            {missingPatternText(
              strings['decision.counts_by_point'],
              count.by_sign_of_point_value_missing,
            )}
          </p>
        )}
      </div>
      <div className={['mt-2'].join(' ')}>
        <p
          data-testid="decision-counts-by-range-heading"
          className={['text-xs', 'font-semibold', 'text-fs-muted'].join(' ')}
        >
          {strings['decision.counts_by_range']}
        </p>
        <ul data-testid="decision-counts-by-range" className={['mt-1', 'space-y-0.5'].join(' ')}>
          {Object.entries(count.by_difference_range).map(([label, entryCount]) => (
            <CountRow key={label} label={label} count={entryCount} mono />
          ))}
        </ul>
      </div>
    </div>
  )
}

/** The label of one years-within summary: its identifiers, rendered as data. */
function rangeLabel(entry: RangeAcrossScenarios): string {
  const label = `${entry.rotation_id} ${entry.indicator}`
  if (entry.carbon_model !== undefined) {
    return entry.computation !== undefined
      ? `${label} ${entry.carbon_model} ${entry.computation}`
      : `${label} ${entry.carbon_model}`
  }
  return label
}

/** One years-within summary: the sentence of D96, or the missing pattern that says why none is given. */
function YearsWithinRow({ entry }: { entry: RangeAcrossScenarios }) {
  return (
    <li data-testid="decision-years-within" className={['flex', 'gap-2'].join(' ')}>
      <span
        data-testid="decision-years-label"
        className={['font-mono', 'text-sm', 'text-fs-muted'].join(' ')}
      >
        {rangeLabel(entry)}
      </span>
      {entry.minimum !== null ? (
        <span data-testid="decision-years-sentence" className={['text-sm'].join(' ')}>
          {formatString(strings['decision.years_within'], {
            min: entry.minimum,
            max: entry.maximum,
            scenario: entry.scenario_of_the_minimum,
          })}
        </span>
      ) : (
        <span
          data-testid="decision-years-missing"
          className={['text-sm', 'italic', 'text-fs-muted'].join(' ')}
        >
          {missingPatternText(rangeLabel(entry), entry.missing)}
        </span>
      )}
    </li>
  )
}

/** One rotation pair: its state, its coverage, its two counts apart, and the years-within summary of its rotations. */
function PairBlock({ state, document }: { state: PairState; document: DecisionOutput }) {
  const counts = document.pair_cell_counts.filter((count) => samePair(count.pair, state.pair))
  const years = document.range_across_scenarios.filter((entry) =>
    state.pair.includes(entry.rotation_id),
  )
  const pairName = formatString(strings['decision.pair_of'], {
    first: state.pair[0],
    second: state.pair[1],
  })

  return (
    <article
      data-testid="decision-pair"
      className={[
        'mt-4',
        'rounded-lg',
        'border',
        'border-fs-border',
        'bg-fs-surface',
        'px-4',
        'py-3',
      ].join(' ')}
    >
      <h4 data-testid="decision-pair-heading" className={['text-sm', 'font-semibold'].join(' ')}>
        {pairName}
      </h4>

      <h5
        data-testid="decision-state-heading"
        className={['mt-3', 'text-xs', 'font-semibold', 'text-fs-muted'].join(' ')}
      >
        {strings['decision.state']}
      </h5>
      {state.value !== null ? (
        <div className={['mt-1'].join(' ')}>
          <p data-testid="decision-state-value" className={['text-sm', 'font-medium'].join(' ')}>
            {state.value}
          </p>
          {state.preferred_rotation_id !== undefined ? (
            <p
              data-testid="decision-state-preferred"
              className={['font-mono', 'text-sm'].join(' ')}
            >
              {state.preferred_rotation_id}
            </p>
          ) : null}
          {state.reason !== undefined ? (
            <p
              data-testid="decision-state-reason"
              className={['text-sm', 'text-fs-muted'].join(' ')}
            >
              {state.reason}
            </p>
          ) : null}
          {state.reason_missing !== undefined ? (
            <p
              data-testid="decision-state-reason-missing"
              className={['text-sm', 'italic', 'text-fs-muted'].join(' ')}
            >
              {missingPatternText(state.value, state.reason_missing)}
            </p>
          ) : null}
        </div>
      ) : (
        <p
          data-testid="decision-state-missing"
          className={['mt-1', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
        >
          {missingPatternText(pairName, state.missing)}
        </p>
      )}

      <p data-testid="decision-coverage" className={['mt-3', 'text-sm'].join(' ')}>
        {formatString(strings['decision.coverage'], {
          k: state.coverage.cells_compared,
          n: state.coverage.cells_of_the_pair,
        })}
      </p>

      <h5
        data-testid="decision-counts-heading"
        className={['mt-3', 'text-xs', 'font-semibold', 'text-fs-muted'].join(' ')}
      >
        {strings['decision.counts']}
      </h5>
      {counts.map((count) => (
        <CountGroup
          key={`${count.indicator}:${count.scenario_id}:${count.carbon_model ?? ''}:${count.computation ?? ''}`}
          count={count}
        />
      ))}

      {years.length > 0 ? (
        <ul data-testid="decision-years-list" className={['mt-3', 'space-y-1'].join(' ')}>
          {years.map((entry) => (
            <YearsWithinRow
              key={`${entry.rotation_id}:${entry.indicator}:${entry.carbon_model ?? ''}:${entry.computation ?? ''}`}
              entry={entry}
            />
          ))}
        </ul>
      ) : null}
    </article>
  )
}

/** The state of the whole decision (D7): its value or why there is none, and its reasons as data. */
function OverallState({ state }: { state: DecisionState }) {
  return (
    <div data-testid="decision-overall" className={['mt-4'].join(' ')}>
      <h4
        data-testid="decision-overall-heading"
        className={['text-sm', 'font-semibold'].join(' ')}
      >
        {strings['decision.state']}
      </h4>
      {state.value !== null ? (
        <p data-testid="decision-overall-value" className={['mt-1', 'text-sm', 'font-medium'].join(' ')}>
          {state.value}
        </p>
      ) : (
        <p
          data-testid="decision-overall-missing"
          className={['mt-1', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
        >
          {missingPatternText(strings['decision.state'], state.missing)}
        </p>
      )}
      {state.reasons.length > 0 ? (
        <ul className={['mt-1', 'space-y-0.5'].join(' ')}>
          {state.reasons.map((reason, index) => (
            <li
              key={index}
              data-testid="decision-overall-reason"
              className={['text-sm', 'text-fs-muted'].join(' ')}
            >
              {reason}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/** Where the rendered document comes from: the route, or the bundled example. */
export type DecisionSource = 'route' | 'example'

/** One document: the live-data label, the example banner, the state of the decision, one block per pair. */
function DecisionDocument({
  document,
  source,
  liveData,
}: {
  document: DecisionOutput
  source: DecisionSource
  liveData: boolean
}) {
  return (
    <div data-testid="decision-document" data-source={source}>
      {liveData ? (
        <p
          data-testid="decision-live"
          className={['mt-3', 'text-sm', 'font-medium', 'text-fs-primary'].join(' ')}
        >
          {strings['seam.with_real_data']}
        </p>
      ) : null}

      {document.example_data && (
        <div
          role="note"
          className={[
            'mt-3',
            'rounded-lg',
            'border',
            'border-fs-warning',
            'bg-fs-warning-bg',
            'px-4',
            'py-3',
          ].join(' ')}
        >
          <p
            data-testid="decision-example-banner"
            className={['text-sm', 'text-fs-warning'].join(' ')}
          >
            {strings['example.banner']}
          </p>
        </div>
      )}

      <OverallState state={document.state} />

      <h4
        data-testid="decision-pairs-heading"
        className={['mt-4', 'text-sm', 'font-semibold'].join(' ')}
      >
        {strings['decision.pairs']}
      </h4>

      {document.pair_states.map((state) => (
        <PairBlock
          key={`${state.pair[0]}:${state.pair[1]}`}
          state={state}
          document={document}
        />
      ))}
    </div>
  )
}

/** A failed call: its code's own string and the raw code, or the shared error. */
function DecisionRouteError({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    return (
      <div data-testid="decision-route-error" role="alert" className={['mt-3'].join(' ')}>
        <p className={['text-sm', 'text-fs-error'].join(' ')}>{strings[`api.${error.code}`]}</p>
        <p data-testid="decision-route-error-code" className={['text-xs', 'text-fs-muted'].join(' ')}>
          {formatString(strings['api.code.shown'], { code: error.code })}
        </p>
      </div>
    )
  }
  return (
    <div data-testid="decision-route-error" role="alert" className={['mt-3'].join(' ')}>
      <p className={['text-sm', 'text-fs-error'].join(' ')}>{strings['common.error']}</p>
    </div>
  )
}

/** The state of the section, as the panel renders it. */
export type DecisionSectionState =
  /** No call: no pair of rotations to send, with the reason when there is one. */
  | { phase: 'not-called'; missing: MissingPart | null }
  | { phase: 'pending' }
  | { phase: 'answered'; answer: DecisionAnswer }
  | { phase: 'error'; error: unknown }

/** The reason the bundled example is shown instead of the route's document. */
function FallbackReason({ state }: { state: DecisionSectionState }) {
  if (state.phase === 'answered' && state.answer.kind === 'missing') {
    return (
      <p
        data-testid="decision-route-missing"
        className={['mt-3', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
      >
        {missingPatternText(strings['decision.title'], state.answer.missing)}
      </p>
    )
  }
  if (state.phase === 'error') {
    return <DecisionRouteError error={state.error} />
  }
  if (state.phase === 'not-called' && state.missing !== null) {
    return (
      <p
        data-testid="decision-not-called"
        className={['mt-3', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
      >
        {missingPatternText(strings['decision.pairs'], state.missing)}
      </p>
    )
  }
  return null
}

/** The section's panel: its title, then the route's document, the loading line, or the reason and the bundled example. */
export function DecisionPanel({ state }: { state: DecisionSectionState }) {
  return (
    <section aria-labelledby="decision-title" className={['mt-8'].join(' ')}>
      <h3
        id="decision-title"
        data-testid="decision-title"
        className={['text-base', 'font-semibold'].join(' ')}
      >
        {strings['decision.title']}
      </h3>

      {state.phase === 'pending' ? (
        <p data-testid="decision-loading" className={['mt-3', 'text-sm', 'text-fs-muted'].join(' ')}>
          {strings['common.loading']}
        </p>
      ) : state.phase === 'answered' && state.answer.kind === 'decision' ? (
        <DecisionDocument
          document={state.answer.document}
          source="route"
          liveData={state.answer.liveData}
        />
      ) : (
        <>
          <FallbackReason state={state} />
          <DecisionDocument document={decisionExample} source="example" liveData={false} />
        </>
      )}
    </section>
  )
}

/**
 * The rotation definitions the section can send: the two rotations of D128
 * for example-field-1 (demoRotations.ts, added at the request of the
 * orchestrating session, citing D128 and D72). For that field the section
 * calls the route; for every other field it holds none, and the fallback
 * applies. The contract example of the run seam (issue #119) is not one of
 * them: its crops are PLACEHOLDER, so the route would only answer missing
 * values.
 */
export const HELD_ROTATIONS: readonly RotationDefinitionExample[] = demoRotationsD128

/** The reason of a field without a pair of rotations: the second one is not declared (C3.2). */
const NO_PAIR_DECLARED: MissingPart = { reason: 'NOT_DECLARED' }

/**
 * The reason no call is made for a selected field: the second rotation is
 * not declared when the interface holds fewer than two for it. Otherwise
 * (no field, no usable point, more than two rotations) no reason is given.
 */
export function notCalledReason(fieldSelected: boolean, heldForField: number): MissingPart | null {
  return fieldSelected && heldForField < ROTATIONS_PER_REQUEST ? NO_PAIR_DECLARED : null
}

/** The state of the section, from the call when one is made. */
export function sectionStateOf(
  request: RunDecisionRequest | null,
  reasonWhenNotCalled: MissingPart | null,
  query: { isPending: boolean; isError: boolean; error: unknown; data: DecisionAnswer | undefined },
): DecisionSectionState {
  if (request === null) {
    return { phase: 'not-called', missing: reasonWhenNotCalled }
  }
  if (query.isError) return { phase: 'error', error: query.error }
  if (query.isPending || query.data === undefined) return { phase: 'pending' }
  return { phase: 'answered', answer: query.data }
}

/**
 * The section on the fields view: for the selected field, the call of the
 * route with the two rotations the interface holds for it, once per field
 * and pair (no retry, no refetch on focus), and the panel of its state.
 */
export default function DecisionSection({
  held = HELD_ROTATIONS,
}: {
  held?: readonly RotationDefinitionExample[]
}) {
  const selectedFieldId = useSelectedFieldId()
  const field =
    selectedFieldId === null
      ? null
      : (exampleCase.fields.find((f) => f.field_id === selectedFieldId) ?? null)
  const request = field === null ? null : decisionRequestOf(exampleCase.case_id, field, held)
  const heldForField =
    field === null ? 0 : rotationsOfField(exampleCase.case_id, field.field_id, held).length

  const query = useQuery({
    queryKey: ['decision-run', request],
    queryFn: async (): Promise<DecisionAnswer> => {
      if (request === null) {
        throw new Error('decision-request-unavailable')
      }
      return parseRunDecision(await runDecision(request))
    },
    enabled: request !== null,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  return (
    <DecisionPanel
      state={sectionStateOf(request, notCalledReason(field !== null, heldForField), query)}
    />
  )
}
