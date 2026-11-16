import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { exampleCase } from '../identity/exampleCase'
import { strings } from '../strings'
import { IconClose, IconMark } from './icons'
import { NAV_GROUPS } from './nav'

/**
 * The left sidebar of the shell (PROPOSED, l3/erp-shell): the identity of
 * the application, the sections in groups with their icons, and the case on
 * screen at the foot. From 768px it stays beside the content; under 768px it
 * is a sheet that slides in over the content when the menu button opens it,
 * closes on Escape, on the backdrop, on its close button and on any section
 * picked, and is out of the tab order while closed.
 */
export default function Sidebar({
  route,
  open,
  onClose,
  title,
}: {
  route: string
  open: boolean
  onClose: () => void
  title: ReactNode
}) {
  const closeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      {open && (
        <button
          type="button"
          tabIndex={-1}
          aria-label={strings['shell.menu_close']}
          onClick={onClose}
          className="fixed inset-0 z-30 bg-fs-text/30 backdrop-blur-[2px] md:hidden"
        />
      )}
      <aside
        id="app-sidebar"
        data-open={open}
        className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-fs-border bg-fs-surface shadow-lg transition-[transform,visibility] duration-200 max-md:invisible max-md:-translate-x-full max-md:data-[open=true]:visible max-md:data-[open=true]:translate-x-0 md:sticky md:top-0 md:h-dvh md:w-56 md:shrink-0 md:shadow-none print:hidden"
      >
        <div className="flex items-center gap-2.5 border-b border-fs-border px-4 py-3.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-fs-brand text-fs-surface">
            <IconMark className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">{title}</div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={strings['shell.menu_close']}
            className="grid h-9 w-9 place-items-center rounded-md text-fs-muted transition hover:bg-fs-faint md:hidden"
          >
            <IconClose className="h-5 w-5" />
          </button>
        </div>

        <nav aria-label={strings['nav.label']} className="flex-1 overflow-y-auto px-3 py-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.heading} className="mb-5 last:mb-0">
              <p className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-fs-muted">
                {strings[group.heading]}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const ItemIcon = item.icon
                  return (
                    <li key={item.route}>
                      <a
                        data-testid="nav-link"
                        href={`#${item.route}`}
                        aria-current={route === item.route ? 'page' : undefined}
                        onClick={onClose}
                        className="group flex min-h-10 items-center gap-2.5 rounded-md border-l-2 border-transparent px-2 py-1 font-fs-heading text-sm font-medium text-fs-text transition-colors hover:bg-fs-faint aria-[current=page]:border-fs-primary aria-[current=page]:bg-fs-selection aria-[current=page]:font-semibold aria-[current=page]:text-fs-primary"
                      >
                        <span className="grid place-items-center rounded-[10px] bg-fs-faint p-1.5 text-fs-muted transition-colors group-aria-[current=page]:bg-fs-brand-soft group-aria-[current=page]:text-fs-primary">
                          <ItemIcon />
                        </span>
                        {strings[item.label]}
                      </a>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-fs-border px-4 py-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-fs-muted">
            {strings['shell.case_footer']}
          </p>
          <p className="mt-1 truncate text-sm font-semibold">{exampleCase.label}</p>
          {exampleCase.example_data && (
            <span className="mt-1.5 inline-flex items-center gap-1.5 rounded-full border border-fs-warning px-2 py-0.5 text-[11px] font-semibold text-fs-warning">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-fs-warning" />
              {strings['shell.example_chip']}
            </span>
          )}
        </div>
      </aside>
    </>
  )
}
