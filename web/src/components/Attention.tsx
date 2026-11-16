import type { AttentionItem, AttentionTarget } from '../board/attention'
import { IconAlert, IconArrowRight, IconCheckCircle } from '../shell/icons'
import { strings } from '../strings'
import { CardCount } from './Card'

/**
 * The "Needs attention" block (l3/original-mock, PROPOSED): one soft card per
 * item, its tone in the icon chip and a thin stripe, what is wrong, the
 * detail the data gives, and the next step as a link. Display only: the
 * items come from board/attention.ts; where each step leads is given by the
 * screen showing the block.
 */

/** Where the next step of an item leads, on the screen showing the block: a link, or a jump within the screen. */
export type AttentionLink = { href: string } | { onClick: () => void }

export function AttentionPanel({
  items,
  linkOf,
  columns = 1,
  subtitle = null,
  emptyText = strings['attention.all_clear'],
}: {
  items: readonly AttentionItem[]
  linkOf: (target: AttentionTarget) => AttentionLink
  /** One column (a side column) or two (the width of the board). */
  columns?: 1 | 2
  /** What the list is about, under the title. */
  subtitle?: string | null
  emptyText?: string
}) {
  return (
    <section data-testid="attention" aria-labelledby="attention-title">
      <div className="mb-2 flex items-center gap-2">
        <h3 id="attention-title" className="fs-eyebrow flex-1">
          {strings['attention.title']}
        </h3>
        <CardCount n={items.length} />
      </div>
      {subtitle !== null ? (
        <p className="-mt-1 mb-2 text-xs text-fs-muted">{subtitle}</p>
      ) : null}
      {items.length === 0 ? (
        <p data-testid="attention-clear" className="flex items-center gap-2 rounded-2xl border border-fs-border bg-fs-surface px-4 py-3 text-sm shadow-fs-card">
          <span className="text-fs-ok">
            <IconCheckCircle className="h-5 w-5" />
          </span>
          {emptyText}
        </p>
      ) : (
        <ul data-columns={columns} className="grid gap-3 data-[columns=2]:xl:grid-cols-2">
          {items.map((item) => (
            <AttentionCard key={item.id} item={item} link={linkOf(item.target)} />
          ))}
        </ul>
      )}
    </section>
  )
}

function AttentionCard({ item, link }: { item: AttentionItem; link: AttentionLink }) {
  const actionClass = ['mt-2', 'inline-flex', 'min-h-8', 'cursor-pointer', 'items-center', 'gap-1.5', 'rounded-md', 'text-sm', 'font-semibold', 'text-fs-primary', 'hover:underline'].join(' ')
  return (
    <li
      data-testid="attention-item"
      data-tone={item.tone}
      data-item={item.id}
      className="relative flex gap-3 overflow-hidden rounded-2xl border border-fs-border bg-fs-surface py-3.5 pl-5 pr-4 shadow-fs-attention"
    >
      <span
        aria-hidden="true"
        data-tone={item.tone}
        className="absolute inset-y-0 left-0 w-1 bg-fs-info data-[tone=open]:bg-fs-warning-accent data-[tone=over]:bg-fs-error"
      />
      <span
        aria-hidden="true"
        data-tone={item.tone}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-fs-faint text-fs-info data-[tone=open]:bg-fs-warning-bg data-[tone=open]:text-fs-warning data-[tone=over]:bg-fs-error-bg data-[tone=over]:text-fs-error"
      >
        <IconAlert className="h-[18px] w-[18px]" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold leading-snug text-fs-text">{item.title}</p>
        {item.detail !== null ? (
          <p className="mt-0.5 text-sm leading-snug text-fs-muted">{item.detail}</p>
        ) : null}
        {'href' in link ? (
          <a data-testid="attention-action" href={link.href} className={actionClass}>
            {item.action}
            <IconArrowRight className="h-3.5 w-3.5" />
          </a>
        ) : (
          <button data-testid="attention-action" type="button" onClick={link.onClick} className={actionClass}>
            {item.action}
            <IconArrowRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </li>
  )
}
