import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ValueDisplay, missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import { useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import type { RotationDefinitionExample } from '../seam/rotationDefinition'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import type {
  CountByYear,
  DecisionOutput,
  DecisionState,
  MeasureFirstItem,
  NotEvaluatedRow,
  PairCellCount,
  PairState,
  PairedDifferenceItem,
  RangeAcrossScenarios,
} from './decisionData'
import { agriculturalYearsOf, decisionExample, samePair } from './decisionData'
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
 * The decision section (issue #241; the route's document, issue #354; Block 4
 * "Measure first" with its field and named-years selector; PROPOSED,
 * interface lane under D159 and D161). It renders one decision output
 * document as it travels:
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
 *   missing pattern with its reason;
 * - the named-years selector (`decision.named_years`), built strictly from
 *   the agricultural years present in `counts_by_year` or
 *   `paired_differences` (`"all"` plus each discovered year, never inventing
 *   years), filtering the displayed `counts_by_year` rows and scenario-year
 *   (`ag_year`) paired differences;
 * - the measurement priority (`measure_first`, D4) with the document's field
 *   (`field_id`): each ranked item's rank, scope (`what`) and priority
 *   reason (`why`), or the shared missing pattern (`NOT_DECLARED`) when
 *   `measure_first` is empty.
 *
 * The section decides nothing and interprets nothing (D74): no winner is
 * named beyond the document's own preferred rotation and no count is summed.
 * The limits, the tolerances, the paired-difference method and rotation-basis
 * paired differences are not rendered; nothing is invented for them.
 *
 * The panel is a pure function of its state (with optional controlled year
 * selection for tests, defaulting to local state), so its whole behaviour is
 * its static markup in the tests; the container holds the call in one TanStack
 * Query query. All user-visible wording lives in strings.ts; indicator,
 * scenario, rotation, model, computation, field and category identifiers
 * render as data, verbatim. Class lists are arrays of single-word tokens
 * joined at runtime.
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

/** The selected agricultural year in the named-years filter, or all years. */
export type YearSelection = 'all' | number

/** One count-by-year entry paired with its not-evaluated rows matching the selected year. */
export interface FilteredCountByYear {
  entry: CountByYear
  notEvaluated: NotEvaluatedRow[]
}

/** Filter counts_by_year entries and their not_evaluated rows by agricultural year. */
export function filterCountsByYear(
  counts: readonly CountByYear[],
  selectedYear: YearSelection,
): FilteredCountByYear[] {
  if (selectedYear === 'all') {
    return counts.map((entry) => ({ entry, notEvaluated: entry.not_evaluated }))
  }
  return counts
    .map((entry) => ({
      entry,
      notEvaluated: entry.not_evaluated.filter((row) => row.ag_year === selectedYear),
    }))
    .filter((item) => item.notEvaluated.length > 0 || item.entry.years_evaluated > 0)
}

/** Filter scenario-year (time_basis === 'ag_year') paired differences by agricultural year. */
export function filterScenarioYearDifferences(
  differences: readonly PairedDifferenceItem[],
  selectedYear: YearSelection,
): PairedDifferenceItem[] {
  return differences.filter(
    (diff) =>
      diff.time_basis === 'ag_year' &&
      diff.ag_year !== undefined &&
      (selectedYear === 'all' || diff.ag_year === selectedYear),
  )
}

/** Named-years selector with the filtered counts_by_year and scenario-year difference rows. */
function NamedYearsSection({
  document,
  selectedYear,
  onSelectYear,
}: {
  document: DecisionOutput
  selectedYear: YearSelection
  onSelectYear: (year: YearSelection) => void
}) {
  const years = agriculturalYearsOf(document)
  const activeYear: YearSelection =
    selectedYear === 'all' || years.includes(selectedYear) ? selectedYear : 'all'
  const filteredCounts = filterCountsByYear(document.counts_by_year, activeYear)
  const filteredDiffs = filterScenarioYearDifferences(document.paired_differences, activeYear)

  return (
    <div
      data-testid="decision-named-years"
      className={[
        'mt-4',
        'rounded-lg',
        'border',
        'border-fs-border',
        'bg-white',
        'px-4',
        'py-3',
      ].join(' ')}
    >
      <div>
        <label
          htmlFor="decision-named-years-select"
          data-testid="decision-named-years-label"
          className={['block', 'text-xs', 'font-semibold', 'text-fs-muted'].join(' ')}
        >
          {strings['decision.named_years']}
        </label>
        <select
          id="decision-named-years-select"
          data-testid="decision-named-years-select"
          value={String(activeYear)}
          disabled={years.length === 0}
          onChange={(event) => {
            const raw = event.target.value
            onSelectYear(raw === 'all' ? 'all' : Number(raw))
          }}
          className={[
            'mt-1',
            'rounded',
            'border',
            'border-fs-border',
            'bg-white',
            'px-2',
            'py-1',
            'text-sm',
          ].join(' ')}
        >
          <option value="all">{strings['decision.named_years_all']}</option>
          {years.map((year) => (
            <option key={year} value={String(year)}>
              {year}
            </option>
          ))}
        </select>
        {years.length === 0 ? (
          <p
            data-testid="decision-named-years-none"
            className={['mt-1', 'text-xs', 'italic', 'text-fs-muted'].join(' ')}
          >
            {strings['decision.named_years_none']}
          </p>
        ) : null}
      </div>

      <div data-testid="decision-counts-by-year" className={['mt-3'].join(' ')}>
        <h5
          data-testid="decision-counts-by-year-heading"
          className={['text-xs', 'font-semibold', 'text-fs-muted'].join(' ')}
        >
          {strings['decision.counts_by_year']}
        </h5>
        {filteredCounts.length === 0 ? (
          <p
            data-testid="decision-counts-by-year-empty"
            className={['mt-1', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
          >
            {strings['decision.counts_by_year_empty']}
          </p>
        ) : (
          <ul className={['mt-2', 'space-y-2'].join(' ')}>
            {filteredCounts.map(({ entry, notEvaluated }) => (
              <li
                key={`${entry.rotation_id}:${entry.scenario_id}:${entry.indicator}:${entry.carbon_model ?? ''}:${entry.computation ?? ''}`}
                data-testid="decision-count-by-year-item"
                className={['text-sm'].join(' ')}
              >
                <p
                  data-testid="decision-count-by-year-label"
                  className={['font-mono', 'text-xs', 'text-fs-muted'].join(' ')}
                >
                  {`${entry.rotation_id} ${entry.scenario_id} ${entry.indicator}`}
                </p>
                {entry.years_within_limits !== null ? (
                  <p data-testid="decision-count-by-year-summary">
                    {formatString(strings['decision.counts_by_year_summary'], {
                      evaluated: entry.years_evaluated,
                      within: entry.years_within_limits,
                    })}
                  </p>
                ) : (
                  <div>
                    <p data-testid="decision-count-by-year-summary">
                      {formatString(strings['decision.counts_by_year_evaluated'], {
                        evaluated: entry.years_evaluated,
                      })}
                    </p>
                    <p
                      data-testid="decision-count-by-year-within-missing"
                      className={['text-sm', 'italic', 'text-fs-muted'].join(' ')}
                    >
                      {missingPatternText(strings['decision.counts_by_year_within'], {
                        reason: 'NOT_DECLARED',
                      })}
                    </p>
                  </div>
                )}
                {notEvaluated.length > 0 ? (
                  <ul
                    data-testid="decision-not-evaluated-list"
                    className={['mt-1', 'space-y-0.5'].join(' ')}
                  >
                    {notEvaluated.map((row) => (
                      <li
                        key={`${row.ag_year}:${row.carbon_model ?? ''}:${row.computation ?? ''}`}
                        data-testid="decision-not-evaluated-row"
                        className={['text-sm', 'italic', 'text-fs-muted'].join(' ')}
                      >
                        {missingPatternText(
                          `${strings['decision.counts_by_year_not_evaluated']} ${row.ag_year}`,
                          row.missing,
                        )}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div data-testid="decision-scenario-years" className={['mt-3'].join(' ')}>
        <h5
          data-testid="decision-scenario-years-heading"
          className={['text-xs', 'font-semibold', 'text-fs-muted'].join(' ')}
        >
          {strings['decision.scenario_years']}
        </h5>
        {filteredDiffs.length === 0 ? (
          <p
            data-testid="decision-scenario-years-empty"
            className={['mt-1', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
          >
            {strings['decision.scenario_years_empty']}
          </p>
        ) : (
          <ul className={['mt-2', 'space-y-2'].join(' ')}>
            {filteredDiffs.map((diff) => (
              <li
                key={`${diff.pair[0]}:${diff.pair[1]}:${diff.scenario_id}:${diff.indicator}:${diff.ag_year}`}
                data-testid="decision-scenario-year-row"
                className={['text-sm'].join(' ')}
              >
                <p
                  data-testid="decision-scenario-year-label"
                  className={['font-mono', 'text-xs', 'text-fs-muted'].join(' ')}
                >
                  {`${formatString(strings['decision.pair_of'], {
                    first: diff.pair[0],
                    second: diff.pair[1],
                  })} ${diff.scenario_id} ${diff.indicator} ${diff.ag_year}`}
                </p>
                <ValueDisplay
                  what={`${diff.indicator} ${diff.ag_year}`}
                  item={diff.difference}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** The measurement priority (D4) with its field: ranked items or NOT_DECLARED when empty. */
export function MeasureFirstBlock({
  fieldId,
  items,
}: {
  fieldId: string
  items: readonly MeasureFirstItem[]
}) {
  return (
    <div
      data-testid="decision-measure-first"
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
      <h4
        data-testid="decision-measure-first-heading"
        className={['text-sm', 'font-semibold'].join(' ')}
      >
        {strings['decision.measure_first']}
      </h4>
      <p
        data-testid="decision-measure-first-field"
        className={['mt-1', 'font-mono', 'text-xs', 'text-fs-muted'].join(' ')}
      >
        {formatString(strings['decision.measure_first_field'], { field: fieldId })}
      </p>
      {items.length > 0 ? (
        <ol data-testid="decision-measure-first-list" className={['mt-2', 'space-y-2'].join(' ')}>
          {items.map((item, index) => (
            <li
              key={`${item.rank}:${index}`}
              data-testid="decision-measure-first-item"
              className={['text-sm'].join(' ')}
            >
              <p className={['font-medium'].join(' ')}>
                <span
                  data-testid="decision-measure-first-rank"
                  className={['font-mono', 'text-xs', 'text-fs-muted'].join(' ')}
                >
                  {formatString(strings['decision.measure_first_rank'], { rank: item.rank })}
                </span>{' '}
                <span data-testid="decision-measure-first-what">{item.what}</span>
              </p>
              <p
                data-testid="decision-measure-first-why"
                className={['text-sm', 'text-fs-muted'].join(' ')}
              >
                {item.why}
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <p
          data-testid="decision-measure-first-empty"
          className={['mt-2', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
        >
          {missingPatternText(strings['decision.measure_first'], {
            reason: 'NOT_DECLARED',
            detail: strings['decision.measure_first_not_declared'],
          })}
        </p>
      )}
    </div>
  )
}

/** Where the rendered document comes from: the route, or the bundled example. */
export type DecisionSource = 'route' | 'example'

/** One document: the live-data label, the example banner, the state of the decision, one block per pair, named years, and measure first. */
function DecisionDocument({
  document,
  source,
  liveData,
  selectedYear,
  onSelectYear,
}: {
  document: DecisionOutput
  source: DecisionSource
  liveData: boolean
  selectedYear?: YearSelection
  onSelectYear?: (year: YearSelection) => void
}) {
  const [internalYear, setInternalYear] = useState<YearSelection>('all')
  const currentYear = selectedYear ?? internalYear
  const handleSelectYear = onSelectYear ?? setInternalYear

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

      <NamedYearsSection
        document={document}
        selectedYear={currentYear}
        onSelectYear={handleSelectYear}
      />

      <MeasureFirstBlock fieldId={document.field_id} items={document.measure_first} />
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
export function DecisionPanel({
  state,
  selectedYear,
  onSelectYear,
}: {
  state: DecisionSectionState
  selectedYear?: YearSelection
  onSelectYear?: (year: YearSelection) => void
}) {
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
          selectedYear={selectedYear}
          onSelectYear={onSelectYear}
        />
      ) : (
        <>
          <FallbackReason state={state} />
          <DecisionDocument
            document={decisionExample}
            source="example"
            liveData={false}
            selectedYear={selectedYear}
            onSelectYear={onSelectYear}
          />
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
