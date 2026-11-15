import type { CSSProperties, ReactNode } from 'react'
import { displayNumber } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { drawnSoilVerdict, stateTone } from './optionBars'
import { swatchOf } from './PlantOptionParts'
import { MARGINS_OF } from './plantData'
import type { MarginOf, Measured, OptionState, PlantOption } from './plantData'
import { monthName } from './rotationStrip'
import type { RotationStrip } from './rotationStrip'
import { buildTimeline } from './timeline'

/**
 * The visual layer of the screen "What should I plant?" (PROPOSED,
 * l3/plant-redesign): the timeline of a rotation, the table of an option by
 * kind of year, the headline figures and the state pill.
 *
 * Display only. Every number is one the answer carries, shown as it travels;
 * a missing number shows a short "no value" here and its full reason in the
 * details of the row, never 0. Whether a soil loss is over the limit is read
 * from the answer (drawnSoilVerdict), never compared here. Colour is never
 * the only carrier: a figure over the limit also says so in words, and the
 * timeline is hidden from assistive technology because the strip in the
 * details of the row carries the same crops as text.
 *
 * Variants are styled through data attributes (data-state, data-selected,
 * data-over, data-open-end), so every class list stays a plain attribute.
 */

/** The legend of the crop colours: each crop once, with its id as it travels. */
export function CropLegend({ order }: { order: readonly string[] }) {
  if (order.length === 0) {
    return null
  }
  return (
    <ul data-testid="plant-legend" aria-label={strings['plant.legend']} className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fs-muted">
      {order.map((cropId) => (
        <li key={cropId} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-flex h-3 w-4 overflow-hidden rounded-sm">
            <span className={swatchOf(cropId, order)} style={{ flex: 1 }} />
          </span>
          <span className="font-mono">{cropId}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * The timeline of a rotation: one column per month, twelve per agricultural
 * year, each crop a bar from its sowing month through its harvest month.
 */
export function RotationTimeline({ strip, order }: { strip: RotationStrip; order: readonly string[] }) {
  const timeline = buildTimeline(strip)
  if (timeline.years === 0) {
    return null
  }
  const perYear = timeline.months.length
  const columns = timeline.years * perYear
  const grid: CSSProperties = { display: 'grid', gridTemplateColumns: `repeat(${columns},minmax(0,1fr))` }
  const years = Array.from({ length: timeline.years }, (_, i) => i)
  return (
    <div data-testid="plant-timeline" aria-hidden="true" className="mt-2 select-none">
      <div style={grid} className="text-[10px] font-semibold uppercase tracking-wide text-fs-muted">
        {years.map((year) => (
          <span
            key={year}
            style={{ gridColumn: `${year * perYear + 1} / ${(year + 1) * perYear + 1}` }}
            className="border-l border-fs-border pl-1"
          >
            {formatString(strings['plant.strip.year_label'], { n: year + 1 })}
          </span>
        ))}
      </div>
      <div style={grid} className="text-center font-mono text-[9px] leading-4 text-fs-muted">
        {years.flatMap((year) =>
          timeline.months.map((month, i) => (
            <span
              key={`${year}-${month}`}
              data-first={String(i === 0)}
              className="data-[first=true]:border-l data-[first=true]:border-fs-border"
            >
              {monthName(month).charAt(0)}
            </span>
          )),
        )}
      </div>
      <div
        style={{ ...grid, gridTemplateRows: `repeat(${Math.max(1, timeline.lanes)},0.875rem)`, rowGap: '2px' }}
        className="rounded bg-fs-faint p-0.5"
      >
        {timeline.bars.map((bar) => (
          <span
            key={bar.component_id}
            data-testid="plant-timeline-bar"
            data-open-end={String(bar.open_end)}
            style={{ gridColumn: `${bar.from + 1} / ${bar.to + 2}`, gridRow: bar.lane + 1 }}
            className="flex overflow-hidden rounded data-[open-end=true]:rounded-r-none data-[open-end=true]:border-r-2 data-[open-end=true]:border-dashed data-[open-end=true]:border-fs-text data-[open-end=true]:opacity-70"
          >
            <span className={swatchOf(bar.crop_id, order)} style={{ flex: 1 }} />
          </span>
        ))}
      </div>
    </div>
  )
}

/** The state of an option as a short label; its full sentence stays in the row. */
export function StatePill({ state }: { state: OptionState }) {
  return (
    <span
      data-testid="plant-pill"
      data-state={state}
      data-tone={stateTone(state)}
      className="inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold data-[tone=chosen]:border-fs-primary data-[tone=chosen]:bg-fs-primary data-[tone=chosen]:text-white data-[tone=meets]:border-fs-ok data-[tone=meets]:text-fs-ok data-[tone=open]:border-fs-warning data-[tone=open]:bg-fs-warning-bg data-[tone=open]:text-fs-warning data-[tone=over]:border-fs-error data-[tone=over]:bg-fs-error-bg data-[tone=over]:text-fs-error"
    >
      {strings[`plant.pill.${state}`]}
    </span>
  )
}

/** One headline figure: a large number with its unit, and what it is. */
export function Figure({
  what,
  item,
  note = null,
}: {
  what: string
  item: Measured
  /** A line under the caption (its mark or source), when there is one. */
  note?: ReactNode
}) {
  return (
    <div data-testid="plant-figure" className="border-t-2 border-fs-border pt-2">
      {item.value !== null ? (
        <p className="font-fs-heading text-2xl font-bold leading-tight tabular-nums" title={String(item.value)}>
          {displayNumber(item.value)} <span className="text-sm font-medium text-fs-muted">{item.unit}</span>
        </p>
      ) : (
        <p className="font-fs-heading text-lg font-semibold italic text-fs-muted">{strings['plant.table.no_value']}</p>
      )}
      <p className="text-sm text-fs-muted">{what}</p>
      {note}
    </div>
  )
}

function Cell({ item, selected, over }: { item: Measured; selected: boolean; over: boolean }) {
  return (
    <td
      data-selected={String(selected)}
      data-over={String(over)}
      className="px-2 py-1 text-right tabular-nums data-[over=true]:font-semibold data-[over=true]:text-fs-error data-[selected=true]:bg-fs-selection"
    >
      {item.value !== null ? (
        <span title={String(item.value)}>{displayNumber(item.value)}</span>
      ) : (
        <span className="italic text-fs-muted">{strings['plant.table.no_value']}</span>
      )}
      {over ? (
        <span className="block text-[10px] font-normal uppercase">{strings['plant.table.over_limit']}</span>
      ) : null}
    </td>
  )
}

function RowHead({ what, unit }: { what: string; unit: string }) {
  return (
    <th scope="row" className="py-1 pr-2 text-left text-xs font-medium text-fs-muted">
      {formatString(strings['plant.table.row'], { what, unit })}
    </th>
  )
}

/**
 * An option by kind of year: its margin and its soil loss on average and in
 * each kind of year, the kind looked at highlighted, a soil loss the answer
 * says is over the limit marked in words.
 */
export function KindTable({ option, marginOf }: { option: PlantOption; marginOf: MarginOf }) {
  return (
    <table data-testid="plant-kind-table" className="w-full table-fixed border-collapse text-sm">
      <caption className="sr-only">{strings['plant.table.heading']}</caption>
      <colgroup>
        <col className="w-[30%]" />
      </colgroup>
      <thead>
        <tr className="text-xs text-fs-muted">
          <td />
          {MARGINS_OF.map((kind) => (
            <th
              key={kind}
              scope="col"
              data-selected={String(kind === marginOf)}
              className="px-2 py-1 text-right align-bottom font-semibold leading-tight data-[selected=true]:bg-fs-selection data-[selected=true]:text-fs-text"
            >
              {strings[`plant.kind.${kind}`]}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        <tr className="border-t border-fs-border">
          <RowHead what={strings['plant.table.margin']} unit={option.margin.average.unit} />
          {MARGINS_OF.map((kind) => (
            <Cell key={kind} item={option.margin[kind]} selected={kind === marginOf} over={false} />
          ))}
        </tr>
        <tr className="border-t border-fs-border">
          <RowHead what={strings['plant.table.soil_loss']} unit={option.soil_loss.average.unit} />
          {MARGINS_OF.map((kind) => {
            const drawn = drawnSoilVerdict(option, kind)
            const item = option.soil_loss[kind]
            return (
              <Cell
                key={kind}
                item={item}
                selected={kind === marginOf}
                over={item.value !== null && drawn.kind === 'verdict' && drawn.verdict === 'does_not_meet'}
              />
            )
          })}
        </tr>
      </tbody>
    </table>
  )
}

/** A bar with its name on the left: the rows of an option read as a small chart. */
export function LabelledBar({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] items-center gap-2">
      <span aria-hidden="true" className="text-xs text-fs-muted">
        {label}
      </span>
      <div>{children}</div>
    </div>
  )
}
