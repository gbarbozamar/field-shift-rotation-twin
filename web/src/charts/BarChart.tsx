import { useId, useState } from 'react'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { chartTicks, linearScale, tickText } from './scale'

/**
 * The grouped vertical bar chart of the chart kit (l3/original-mock): one
 * group per category, one bar per series, on a dashed horizontal grid with
 * round ticks, bars with rounded ends, an optional dashed reference line
 * (labelled), a zero line when values go negative, a legend with colour
 * dots and a hover or focus tooltip.
 *
 * Display only: each bar is a value it is given, exactly. A missing value
 * (null) is never drawn as zero: its slot is hatched, takes no part in the
 * scale, and its tooltip and accessible label carry its reason. Every bar
 * slot is keyboard focusable and says its value in its label.
 */

/** One series: what a colour stands for (an option, a rotation). */
export interface ChartSeries {
  id: string
  label: string
  /** A colour token, as a CSS value: var(--fs-chart-1). */
  color: string
}

/** One value of a series in a group: present, or missing with the text of its reason. */
export interface ChartValue {
  value: number | null
  /** The reason a missing value is missing, as the screen words it. */
  missingText?: string
  /** What else the value carries, said in its tooltip and label: MOCK, over the limit. */
  notes?: string[]
  /** True to draw a small warning mark over the bar (the words are in the notes). */
  flagged?: boolean
}

export interface ChartGroup {
  id: string
  label: string
  /** One value per series, in the order of the series. */
  values: ChartValue[]
  /** A short tag under the label (MOCK). */
  tag?: string
  /** True for the group the screen looks at: its band is tinted and its label bold. */
  emphasis?: boolean
}

export interface ChartReference {
  value: number
  /** The label drawn on the line and said in the tooltip. */
  label: string
}

const WIDTH = 640
const MARGIN = { top: 18, right: 12, bottom: 40, left: 48 }
/** The radius of the rounded end of a bar. */
const RADIUS = 4

/**
 * The outline of a bar from the zero line y0 to y1, rounded at its far end
 * (the top for a positive bar, the bottom for a negative one).
 */
export function barPath(x: number, y0: number, y1: number, width: number, radius = RADIUS): string {
  const height = Math.abs(y1 - y0)
  const r = Math.max(0, Math.min(radius, width / 2, height))
  if (y1 <= y0) {
    // Grows upward: rounded top.
    return `M${x},${y0}V${y1 + r}Q${x},${y1},${x + r},${y1}H${x + width - r}Q${x + width},${y1},${x + width},${y1 + r}V${y0}Z`
  }
  return `M${x},${y0}V${y1 - r}Q${x},${y1},${x + r},${y1}H${x + width - r}Q${x + width},${y1},${x + width},${y1 - r}V${y0}Z`
}

/** The accessible label of one bar slot: the series, the group, and the value or the reason it is missing. */
export function barLabel(series: ChartSeries, group: ChartGroup, value: ChartValue, format: (n: number) => string): string {
  const base =
    value.value !== null
      ? formatString(strings['chart.bar'], { series: series.label, group: group.label, value: format(value.value) })
      : formatString(strings['chart.bar_missing'], {
          series: series.label,
          group: group.label,
          missing: value.missingText ?? strings['plant.table.no_value'],
        })
  const notes = value.notes ?? []
  return notes.length === 0 ? base : formatString(strings['chart.with_notes'], { text: base, notes: notes.join(strings['chart.notes_join']) })
}

/** The legend of a chart: one colour dot and name per series. */
export function ChartLegend({ series }: { series: readonly ChartSeries[] }) {
  return (
    <ul data-testid="chart-legend" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fs-muted">
      {series.map((each) => (
        <li key={each.id} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: each.color }} />
          {each.label}
        </li>
      ))}
    </ul>
  )
}

/** The tooltip card of a chart: real DOM over the plot, placed at a point given as shares of the plot. */
export function ChartTooltip({
  left,
  top,
  title,
  color,
  name,
  text,
  notes,
  missing,
}: {
  /** Horizontal place, as a percentage of the chart width. */
  left: number
  /** Vertical place, as a percentage of the chart height. */
  top: number
  title: string
  color: string
  name: string
  text: string
  notes: readonly string[]
  missing: boolean
}) {
  return (
    <div
      data-testid="chart-tooltip"
      role="presentation"
      className="pointer-events-none absolute z-20 w-max min-w-40 max-w-72 -translate-x-1/2 -translate-y-full rounded-xl border border-fs-border bg-fs-surface px-3 py-2 text-xs shadow-fs-pop"
      style={{ left: `${left}%`, top: `${top}%`, marginTop: -8 }}
    >
      <p className="font-semibold text-fs-text">{title}</p>
      <p className="mt-1 flex items-start gap-1.5 text-fs-muted">
        <span aria-hidden="true" className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
        {name}
      </p>
      <p data-missing={String(missing)} className="mt-0.5 pl-3.5 text-sm font-semibold tabular-nums text-fs-text data-[missing=true]:text-xs data-[missing=true]:font-normal data-[missing=true]:italic data-[missing=true]:text-fs-muted">
        {text}
      </p>
      {notes.map((note) => (
        <p key={note} className="mt-0.5 font-semibold text-fs-warning">
          {note}
        </p>
      ))}
    </div>
  )
}

/** The bar slot under the pointer or the keyboard focus. */
interface Active {
  group: number
  series: number
}

export function GroupedBarChart({
  label,
  series,
  groups,
  format,
  reference = null,
  height = 260,
}: {
  /** What the chart shows, for assistive technology (the card header says it to the eye). */
  label: string
  series: readonly ChartSeries[]
  groups: readonly ChartGroup[]
  /** How a value is printed, with its unit: in the tooltip and the labels. */
  format: (value: number) => string
  reference?: ChartReference | null
  height?: number
}) {
  const hatch = `chart-hatch-${useId().replace(/[^A-Za-z0-9_-]/g, '')}`
  const [active, setActive] = useState<Active | null>(null)
  const values = groups.flatMap((group) => group.values.map((value) => value.value))
  const ticks = chartTicks(values, reference !== null ? [reference.value] : [])
  const plotTop = MARGIN.top
  const plotBottom = height - MARGIN.bottom
  const plotLeft = MARGIN.left
  const plotRight = WIDTH - MARGIN.right
  const y = linearScale([ticks[0], ticks[ticks.length - 1]], [plotBottom, plotTop])
  const zero = y(0)
  const band = (plotRight - plotLeft) / Math.max(1, groups.length)
  const inner = band * 0.72
  const gap = series.length > 1 ? Math.min(6, inner / series.length / 4) : 0
  const barWidth = (inner - gap * (series.length - 1)) / Math.max(1, series.length)
  const barX = (g: number, s: number) => plotLeft + g * band + (band - inner) / 2 + s * (barWidth + gap)
  const shown = active !== null ? { group: groups[active.group], series: series[active.series], value: groups[active.group].values[active.series] } : null
  return (
    <div data-testid="chart" role="group" aria-label={label} className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="block h-auto w-full overflow-visible"
        onMouseLeave={() => setActive(null)}
      >
        <defs>
          <pattern id={hatch} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="var(--fs-faint)" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--fs-border)" strokeWidth="2.5" />
          </pattern>
        </defs>
        {groups.map((group, g) =>
          group.emphasis ? (
            <rect
              key={group.id}
              data-testid="chart-emphasis"
              x={plotLeft + g * band + 2}
              y={plotTop - 8}
              width={band - 4}
              height={plotBottom - plotTop + 8}
              rx="6"
              fill="var(--fs-selection-bg)"
            />
          ) : null,
        )}
        {ticks.map((tick) => (
          <g key={tick} data-testid="chart-tick">
            <line
              x1={plotLeft}
              x2={plotRight}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--fs-chart-grid)"
              strokeDasharray="3 3"
            />
            <text x={plotLeft - 8} y={y(tick)} dy="0.32em" textAnchor="end" fontSize="12" fill="var(--fs-muted)">
              {tickText(tick)}
            </text>
          </g>
        ))}
        {ticks[0] < 0 ? (
          <line data-testid="chart-zero" x1={plotLeft} x2={plotRight} y1={zero} y2={zero} stroke="var(--fs-muted)" strokeWidth="1.25" />
        ) : null}
        {groups.map((group, g) => (
          <g key={group.id}>
            {series.map((each, s) => {
              const value = group.values[s]
              const x = barX(g, s)
              if (value === undefined || value.value === null) {
                return (
                  <rect
                    key={each.id}
                    data-testid="chart-missing"
                    x={x}
                    y={plotTop}
                    width={barWidth}
                    height={plotBottom - plotTop}
                    rx="3"
                    fill={`url(#${hatch})`}
                    stroke="var(--fs-border)"
                    strokeDasharray="3 2"
                  />
                )
              }
              const top = y(value.value)
              return (
                <g key={each.id}>
                  <path
                    data-testid="chart-bar"
                    data-value={value.value}
                    d={barPath(x, zero, top, barWidth)}
                    fill={each.color}
                    opacity={active === null || (active.group === g && active.series === s) ? 1 : 0.55}
                  />
                  {value.flagged ? (
                    <circle data-testid="chart-flag" cx={x + barWidth / 2} cy={Math.min(top, zero) - 6} r="3" fill="var(--fs-error)" />
                  ) : null}
                </g>
              )
            })}
            <text
              x={plotLeft + g * band + band / 2}
              y={plotBottom + 18}
              textAnchor="middle"
              fontSize="12"
              fontWeight={group.emphasis ? 700 : 400}
              fill={group.emphasis ? 'var(--fs-text)' : 'var(--fs-muted)'}
            >
              {group.label}
            </text>
            {group.tag !== undefined ? (
              <text
                data-testid="chart-group-tag"
                x={plotLeft + g * band + band / 2}
                y={plotBottom + 33}
                textAnchor="middle"
                fontSize="10"
                fontWeight={700}
                fill="var(--fs-warning)"
              >
                {group.tag}
              </text>
            ) : null}
          </g>
        ))}
        {reference !== null ? (
          <g data-testid="chart-reference" data-value={reference.value}>
            <line
              x1={plotLeft}
              x2={plotRight}
              y1={y(reference.value)}
              y2={y(reference.value)}
              stroke="var(--fs-error)"
              strokeWidth="1.5"
              strokeDasharray="6 4"
            />
            <text x={plotRight} y={y(reference.value) - 6} textAnchor="end" fontSize="11" fontWeight={700} fill="var(--fs-error)" stroke="var(--fs-surface)" strokeWidth="3" paintOrder="stroke">
              {reference.label}
            </text>
          </g>
        ) : null}
        {groups.map((group, g) =>
          series.map((each, s) => {
            const value = group.values[s] ?? { value: null }
            return (
              <rect
                key={`${group.id}-${each.id}`}
                data-testid="chart-slot"
                tabIndex={0}
                role="img"
                aria-label={barLabel(each, group, value, format)}
                x={barX(g, s)}
                y={plotTop}
                width={barWidth}
                height={plotBottom - plotTop}
                fill="transparent"
                className="cursor-default outline-none focus-visible:stroke-fs-info"
                strokeWidth="2"
                onMouseEnter={() => setActive({ group: g, series: s })}
                onFocus={() => setActive({ group: g, series: s })}
                onBlur={() => setActive(null)}
              />
            )
          }),
        )}
      </svg>
      {shown !== null && active !== null ? (
        <ChartTooltip
          left={((barX(active.group, active.series) + barWidth / 2) / WIDTH) * 100}
          top={
            ((shown.value.value !== null ? Math.min(y(shown.value.value), zero) : (plotTop + plotBottom) / 2) / height) * 100
          }
          title={shown.group.label}
          color={shown.series.color}
          name={shown.series.label}
          text={shown.value.value !== null ? format(shown.value.value) : (shown.value.missingText ?? strings['plant.table.no_value'])}
          notes={shown.value.notes ?? []}
          missing={shown.value.value === null}
        />
      ) : null}
    </div>
  )
}
