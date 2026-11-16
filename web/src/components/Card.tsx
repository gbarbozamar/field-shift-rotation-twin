import type { ReactNode } from 'react'
import type { Icon } from '../shell/icons'

/**
 * The parts every card of the interface shares (l3/original-mock): the
 * header row of a card and the KPI tile. Display only.
 */

/**
 * The header of a card: a small icon chip in the tinted primary, the small
 * uppercase title, and on the right an optional count or badge.
 */
export function CardHeader({
  id,
  icon: HeaderIcon,
  title,
  aside = null,
  level = 'h3',
  className = 'mb-3',
  headingTestId,
}: {
  id?: string
  /** The test id of the heading itself, when a test reads it. */
  headingTestId?: string
  icon: Icon
  title: string
  /** What sits on the right of the title: a count, a badge, a small control. */
  aside?: ReactNode
  /** The heading level of the title, as the outline of the screen needs it. */
  level?: 'h2' | 'h3' | 'h4'
  /** The spacing under the header. */
  className?: string
}) {
  const Heading = level
  return (
    <div data-testid="card-header" className={['flex', 'items-center', 'gap-2.5', className].join(' ')}>
      <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-fs-brand-soft/60 text-fs-primary">
        <HeaderIcon />
      </span>
      <Heading id={id} data-testid={headingTestId} className="fs-eyebrow min-w-0 flex-1 text-fs-text">
        {title}
      </Heading>
      {aside}
    </div>
  )
}

/** The count on the right of a card header: a small rounded number. */
export function CardCount({ n }: { n: number }) {
  return (
    <span data-testid="card-count" className="rounded-full bg-fs-faint px-2 py-0.5 text-[11px] font-semibold tabular-nums text-fs-muted">
      {n}
    </span>
  )
}

/**
 * A KPI tile: the icon chip, the big number in the heading font and under it
 * the small muted label that carries the unit. The number is given as a
 * node so a missing value can say so in its place.
 */
export function KpiTile({
  icon: TileIcon,
  label,
  children,
  testId,
  tone = 'plain',
  wide = false,
}: {
  icon: Icon
  label: string
  children: ReactNode
  testId?: string
  /** The tint of the icon chip: plain, or the tone of a state. */
  tone?: 'plain' | 'over' | 'open'
  wide?: boolean
}) {
  return (
    <div
      data-testid={testId}
      data-wide={String(wide)}
      className="fs-card flex min-w-0 items-start gap-3 p-4 text-fs-text data-[wide=true]:col-span-2"
    >
      <span
        aria-hidden="true"
        data-tone={tone}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-fs-brand-soft/60 text-fs-primary data-[tone=open]:bg-fs-warning-bg data-[tone=open]:text-fs-warning data-[tone=over]:bg-fs-error-bg data-[tone=over]:text-fs-error"
      >
        <TileIcon className="h-[18px] w-[18px]" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="tabular-nums">{children}</div>
        <p className="mt-1 text-[11px] leading-snug text-fs-muted">{label}</p>
      </div>
    </div>
  )
}
