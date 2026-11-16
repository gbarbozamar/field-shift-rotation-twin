import { useState } from 'react'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { ChartTooltip } from './BarChart'
import { chartTicks, linearScale, tickText } from './scale'

/**
 * The horizontal bar list of the chart kit (l3/original-mock): one row per
 * item, its name, a bar from zero on a dashed vertical grid with round
 * ticks, and its value printed at the end. A missing value is a hatched
 * track with its reason, never a bar of zero. Each row is focusable and says
 * its value in its label; hover or focus shows the tooltip card.
 */

export interface BarListItem {
  id: string
  label: string
  value: number | null
  /** The reason a missing value is missing, as the screen words it. */
  missingText?: string
  /** A colour token, as a CSS value; the primary colour when not given. */
  color?: string
}

export function BarList({
  label,
  items,
  format,
}: {
  /** What the list shows, for assistive technology. */
  label: string
  items: readonly BarListItem[]
  /** How a value is printed, with its unit. */
  format: (value: number) => string
}) {
  const [active, setActive] = useState<number | null>(null)
  const ticks = chartTicks(items.map((item) => item.value), [], 4)
  const x = linearScale([ticks[0], ticks[ticks.length - 1]], [0, 100])
  const zero = x(0)
  const shown = active !== null ? items[active] : null
  return (
    <div data-testid="bar-list" role="group" aria-label={label} className="relative" onMouseLeave={() => setActive(null)}>
      <ul className="space-y-2.5">
        {items.map((item, index) => {
          const text = item.value !== null ? format(item.value) : (item.missingText ?? strings['plant.table.no_value'])
          const from = item.value !== null ? Math.min(zero, x(item.value)) : 0
          const to = item.value !== null ? Math.max(zero, x(item.value)) : 0
          return (
            <li
              key={item.id}
              data-testid="bar-list-row"
              tabIndex={0}
              aria-label={formatString(strings['chart.row'], { name: item.label, value: text })}
              className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)_7rem] items-center gap-3 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-fs-info"
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
            >
              <span aria-hidden="true" className="truncate text-sm text-fs-text">
                {item.label}
              </span>
              <span aria-hidden="true" className="relative h-3.5">
                {ticks.map((tick) => (
                  <span
                    key={tick}
                    className="absolute inset-y-[-5px] border-l border-dashed border-fs-chart-grid"
                    style={{ left: `${x(tick)}%` }}
                  />
                ))}
                {item.value !== null ? (
                  <span
                    data-testid="bar-list-bar"
                    data-value={item.value}
                    data-negative={String(item.value < 0)}
                    className="absolute inset-y-0 rounded-r-[4px] data-[negative=true]:rounded-l-[4px] data-[negative=true]:rounded-r-none"
                    style={{ left: `${from}%`, width: `${to - from}%`, background: item.color ?? 'var(--fs-primary)' }}
                  />
                ) : (
                  <span data-testid="bar-list-missing" className="fs-fog absolute inset-0 rounded-[4px]" />
                )}
              </span>
              <span
                aria-hidden="true"
                data-missing={String(item.value === null)}
                className="truncate text-right text-sm font-semibold tabular-nums data-[missing=true]:font-normal data-[missing=true]:italic data-[missing=true]:text-fs-muted"
              >
                {text}
              </span>
            </li>
          )
        })}
      </ul>
      <div aria-hidden="true" className="mt-1 grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)_7rem] gap-3">
        <span />
        <span className="relative h-4">
          {ticks.map((tick) => (
            <span
              key={tick}
              data-testid="bar-list-tick"
              className="absolute -translate-x-1/2 text-[12px] text-fs-muted"
              style={{ left: `${x(tick)}%` }}
            >
              {tickText(tick)}
            </span>
          ))}
        </span>
        <span />
      </div>
      {shown !== null && active !== null ? (
        <ChartTooltip
          left={50}
          top={((active + 0.2) / Math.max(1, items.length + 0.4)) * 100}
          title={shown.label}
          color={shown.color ?? 'var(--fs-primary)'}
          name={label}
          text={shown.value !== null ? format(shown.value) : (shown.missingText ?? strings['plant.table.no_value'])}
          notes={[]}
          missing={shown.value === null}
        />
      ) : null}
    </div>
  )
}
