import { missingPatternText } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import type {
  PairCellCount,
  PairState,
  RangeAcrossScenarios,
} from './decisionData'
import { decisionExample, samePair } from './decisionData'

/**
 * The decision section (issue #241): the decision output example, rendered
 * as it travels. One block per rotation pair the example carries, named by
 * its two rotations. In each block:
 *
 * - the state of the pair, verbatim — the science wording of D88 and D97
 *   travels as data, and so does its reason (D86); a pair that is not
 *   evaluated shows the shared missing pattern with its reason (D85, C3.1);
 * - the coverage "k of N" (D91);
 * - the two counts of the pair's cells, by point value and by range, shown
 *   apart and never added (D87, D99); the categories of the first count
 *   render under their person-approved labels, the categories of the second
 *   are the contract's own identifiers, rendered as data; a count by point
 *   value that does not travel (no tolerance of "equal") shows the shared
 *   missing pattern with its reason, never zeros;
 * - the years-within summary of each rotation of the pair: the range across
 *   the admitted scenarios with the scenario of the minimum (D96).
 *
 * The section decides nothing and interprets nothing (D74): no winner is
 * named and no count is summed; the preferred rotation of a robust
 * preference, the limits, the counts by year, the paired differences, the
 * tolerances, the state of the whole decision and the measurement priority
 * are fields the brief of this unit does not name, and nothing is rendered
 * or invented for them.
 *
 * The example describes its own placeholder case; the example banner is
 * driven by its example_data flag. All user-visible wording lives in
 * strings.ts; indicator, scenario, rotation and category identifiers render
 * as data, verbatim. Class lists are arrays of single-word tokens joined at
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
 * the scenario identifier of the contract, rendered as data.
 */
function cellLabel(count: PairCellCount): string {
  return `${count.indicator} ${count.scenario_id}`
}

/** One counted cell: its label, then the two counts apart under their headings. */
function CountGroup({ count }: { count: PairCellCount }) {
  return (
    <div data-testid="decision-counts-group" className={['mt-3'].join(' ')}>
      <p
        data-testid="decision-counts-cell-label"
        className={['font-mono', 'text-xs', 'text-slate-500'].join(' ')}
      >
        {cellLabel(count)}
      </p>
      <div className={['mt-1'].join(' ')}>
        <p
          data-testid="decision-counts-by-point-heading"
          className={['text-xs', 'font-semibold', 'text-slate-600'].join(' ')}
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
            className={['mt-1', 'text-sm', 'italic', 'text-slate-500'].join(' ')}
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
          className={['text-xs', 'font-semibold', 'text-slate-600'].join(' ')}
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
        className={['font-mono', 'text-sm', 'text-slate-500'].join(' ')}
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
          className={['text-sm', 'italic', 'text-slate-500'].join(' ')}
        >
          {missingPatternText(rangeLabel(entry), entry.missing)}
        </span>
      )}
    </li>
  )
}

/** One rotation pair: its state, its coverage, its two counts apart, and the years-within summary of its rotations. */
function PairBlock({ state }: { state: PairState }) {
  const counts = decisionExample.pair_cell_counts.filter((count) => samePair(count.pair, state.pair))
  const years = decisionExample.range_across_scenarios.filter((entry) =>
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
        'border-slate-200',
        'bg-white',
        'px-4',
        'py-3',
      ].join(' ')}
    >
      <h4 data-testid="decision-pair-heading" className={['text-sm', 'font-semibold'].join(' ')}>
        {pairName}
      </h4>

      <h5
        data-testid="decision-state-heading"
        className={['mt-3', 'text-xs', 'font-semibold', 'text-slate-500'].join(' ')}
      >
        {strings['decision.state']}
      </h5>
      {state.value !== null ? (
        <div className={['mt-1'].join(' ')}>
          <p data-testid="decision-state-value" className={['text-sm', 'font-medium'].join(' ')}>
            {state.value}
          </p>
          {state.reason !== undefined ? (
            <p
              data-testid="decision-state-reason"
              className={['text-sm', 'text-slate-500'].join(' ')}
            >
              {state.reason}
            </p>
          ) : null}
          {state.reason_missing !== undefined ? (
            <p
              data-testid="decision-state-reason-missing"
              className={['text-sm', 'italic', 'text-slate-500'].join(' ')}
            >
              {missingPatternText(state.value, state.reason_missing)}
            </p>
          ) : null}
        </div>
      ) : (
        <p
          data-testid="decision-state-missing"
          className={['mt-1', 'text-sm', 'italic', 'text-slate-500'].join(' ')}
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
        className={['mt-3', 'text-xs', 'font-semibold', 'text-slate-500'].join(' ')}
      >
        {strings['decision.counts']}
      </h5>
      {counts.map((count) => (
        <CountGroup key={`${count.indicator}:${count.scenario_id}`} count={count} />
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

/** The decision section: its title, the example banner, one block per rotation pair of the example. */
export default function DecisionSection() {
  return (
    <section aria-labelledby="decision-title" className={['mt-8'].join(' ')}>
      <h3
        id="decision-title"
        data-testid="decision-title"
        className={['text-base', 'font-semibold'].join(' ')}
      >
        {strings['decision.title']}
      </h3>

      {decisionExample.example_data && (
        <div
          role="note"
          className={[
            'mt-3',
            'rounded-lg',
            'border',
            'border-amber-300',
            'bg-amber-50',
            'px-4',
            'py-3',
          ].join(' ')}
        >
          <p
            data-testid="decision-example-banner"
            className={['text-sm', 'text-amber-900'].join(' ')}
          >
            {strings['example.banner']}
          </p>
        </div>
      )}

      <h4
        data-testid="decision-pairs-heading"
        className={['mt-4', 'text-sm', 'font-semibold'].join(' ')}
      >
        {strings['decision.pairs']}
      </h4>

      {decisionExample.pair_states.map((state) => (
        <PairBlock
          key={`${state.pair[0]}:${state.pair[1]}`}
          state={state}
        />
      ))}
    </section>
  )
}
