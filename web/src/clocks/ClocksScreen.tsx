import { ValueDisplay } from '../components/ValueDisplay'
import { strings } from '../strings'
import { resultsTable, rotationsOfTable } from './clockData'
import type { ClockRow } from './clockData'

/**
 * The two clocks of the results example (issue #140): for each rotation of
 * the table, the soil clock — soil loss per agricultural year, one column
 * per year — and the water clock — water-deficit exposure, one column per
 * year on the years the indicator travels per year, or the value the
 * indicator carries for the whole rotation when it travels per rotation,
 * which is what the example carries. Every value, present or missing, goes
 * through the shared value display: a missing year is shown as missing with
 * its reason, never as zero and never as a blank.
 *
 * There is no rotation selector in the interface, so every rotation of the
 * example has its own block, headed by the rotation identifier as data, the
 * way the site sheet heads its rows by their contract identifiers. The
 * example's field is not a field of the example case and no engine produced
 * its numbers, so the section always shows the example banner; the banner
 * carries that honesty, as it does on the site sheet.
 *
 * The display name of an indicator ("Block 1" of the wording) has not
 * reached the strings file yet; until it does, the value display names what
 * is missing by the indicator identifier of the contract, rendered as data,
 * the way the site sheet names its soil properties by their quantity.
 *
 * All user-visible wording lives in strings.ts. Class lists are arrays of
 * single-word tokens joined at runtime.
 */

/** One year column: the agricultural year as data, and the value of that year. */
function YearColumn({ row }: { row: ClockRow }) {
  return (
    <div
      data-testid="clock-column"
      className={[
        'w-44', 'rounded-lg', 'border', 'border-slate-200', 'bg-white', 'px-3', 'py-2',
      ].join(' ')}
    >
      <p data-testid="clock-year" className="font-mono text-sm font-semibold text-slate-700">
        {row.ag_year}
      </p>
      <div className="mt-1">
        <ValueDisplay what={row.indicator} item={row} />
      </div>
    </div>
  )
}

/** One value the indicator carries for the whole rotation, on no year column. */
function RotationBasisItem({ row }: { row: ClockRow }) {
  return (
    <div data-testid="clock-item" className="mt-2">
      <ValueDisplay what={row.indicator} item={row} />
    </div>
  )
}

/** One clock: its heading, its year columns, and any rotation-basis item. */
function ClockPanel({ rows, title }: { rows: ClockRow[]; title: string }) {
  const yearRows = rows.filter((row) => row.time_basis === 'ag_year')
  const rotationRows = rows.filter((row) => row.time_basis === 'rotation')
  return (
    <div>
      <h4 className="text-sm font-semibold">{title}</h4>
      {yearRows.length > 0 ? (
        <div
          className={['mt-2', 'flex', 'flex-wrap', 'items-start', 'gap-3'].join(' ')}
        >
          {yearRows.map((row) => (
            <YearColumn key={row.ag_year} row={row} />
          ))}
        </div>
      ) : null}
      {rotationRows.map((row) => (
        <RotationBasisItem key={`${row.indicator}:${row.scenario_id}`} row={row} />
      ))}
    </div>
  )
}

/** The two clocks of every rotation of the results example, under the example banner. */
export default function ClocksScreen() {
  const rotations = rotationsOfTable(resultsTable)

  return (
    <section aria-labelledby="clocks-title" className="mt-8">
      <h3 id="clocks-title" data-testid="clocks-title" className="text-base font-semibold">
        {strings['clocks.title']}
      </h3>
      <p className="mt-1 text-sm text-slate-500">{strings['clocks.years_hint']}</p>

      <div
        role="note"
        className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3"
      >
        <p data-testid="clocks-example-banner" className="text-sm text-amber-900">
          {strings['example.banner']}
        </p>
        <p data-testid="clocks-example-note" className="mt-1 text-sm text-amber-800">
          {strings['clocks.example_note']}
        </p>
      </div>

      {rotations.map((rotation) => (
        <div key={rotation.rotation_id} data-testid="clocks-rotation" className="mt-6">
          <h4
            data-testid="clocks-rotation-id"
            className="font-mono text-sm font-semibold text-slate-700"
          >
            {rotation.rotation_id}
          </h4>
          <div data-testid="soil-clock" className="mt-2">
            <ClockPanel rows={rotation.soil} title={strings['clocks.soil']} />
          </div>
          <div data-testid="water-clock" className="mt-4">
            <ClockPanel rows={rotation.water} title={strings['clocks.water']} />
          </div>
        </div>
      ))}
    </section>
  )
}
