import type { ReactNode } from 'react'
import { cx } from './cx'

export function Card({ title, children, className = '' }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-lg', 'border', 'border-fs-border', 'bg-fs-surface', 'p-4', className)}>
      {title && <h3 className="mb-3 text-base font-bold">{title}</h3>}
      {children}
    </section>
  )
}

export function Pill({ children, tone }: { children: ReactNode; tone: 'ok' | 'warn' | 'bad' | 'neutral' }) {
  const cls = {
    ok: ['border-fs-ok', 'text-fs-ok'],
    warn: ['border-fs-warning', 'bg-fs-warning-bg', 'text-fs-warning'],
    bad: ['border-fs-error', 'bg-fs-error-bg', 'text-fs-error'],
    neutral: ['border-fs-border', 'text-fs-muted'],
  }[tone]
  const base = ['inline-flex', 'items-center', 'rounded-full', 'border', 'px-2.5', 'py-0.5', 'text-xs', 'font-bold']
  return <span className={[...base, ...cls].join(' ')}>{children}</span>
}

export function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: { id: string; label: string }[]
  onChange: (id: string) => void
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1 rounded-lg border border-fs-border bg-fs-bg p-1">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={o.id === value}
          onClick={() => onChange(o.id)}
          className="min-h-10 rounded-md px-3 text-sm font-semibold text-fs-muted aria-pressed:bg-fs-text aria-pressed:text-fs-surface"
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Horizontal bar: a value against a scale maximum, with an optional limit mark. */
export function Bar({ value, max, limit, tone = 'primary' }: { value: number; max: number; limit?: number; tone?: 'primary' | 'bad' | 'muted' }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100))
  const color = tone === 'bad' ? 'bg-fs-error' : tone === 'muted' ? 'bg-fs-neutral' : 'bg-fs-primary'
  return (
    <div className="relative h-3 w-full rounded bg-fs-faint">
      <div className={cx('h-3', 'rounded', color)} style={{ width: `${w}%` }} />
      {limit !== undefined && (
        <div className="absolute -top-1 h-5 w-0.5 bg-fs-text" style={{ left: `${Math.min(100, (limit / max) * 100)}%` }} />
      )}
    </div>
  )
}

export function Workbench({ left, right }: { left: ReactNode; right: ReactNode }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div className="space-y-4">{left}</div>
      <div className="space-y-4">{right}</div>
    </div>
  )
}

export function PanelHead({ title, lead }: { title: string; lead: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-2xl font-extrabold leading-tight">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm text-fs-muted">{lead}</p>
    </div>
  )
}
