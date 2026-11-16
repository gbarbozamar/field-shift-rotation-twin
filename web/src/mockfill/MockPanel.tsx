import { strings } from '../strings'
import type { MockReport } from './mockFill'

/** The mark on every value that is mock example data, not the backend's. */
export function MockBadge() {
  return (
    <span
      data-testid="mock-badge"
      className="ml-1.5 inline-flex items-center rounded border border-fs-warning bg-fs-warning-bg px-1 align-middle font-mono text-[10px] font-bold uppercase tracking-wide text-fs-warning"
    >
      {strings['mock.badge']}
    </span>
  )
}

/** What of the answer comes from the backend and what is mock, said once above the answer. */
export function MockPanel({ report }: { report: MockReport }) {
  const parts: string[] = []
  if (report.whole) parts.push(strings['mock.part.whole'])
  else {
    if (report.soilKinds.length !== 0) parts.push(strings['mock.part.soil'])
    if (report.record) parts.push(strings['mock.part.record'])
    if (report.marginKinds.length !== 0) parts.push(strings['mock.part.margin'])
    if (report.verdicts) parts.push(strings['mock.part.verdicts'])
  }
  return (
    <div id="mock-panel" data-testid="mock-panel" role="note" className="scroll-mt-4 rounded-xl border-2 border-fs-warning bg-fs-warning-bg px-4 py-3 text-sm">
      <p className="font-bold text-fs-warning">
        {strings['mock.panel.title']}
        <MockBadge />
      </p>
      {report.refused !== null ? (
        <p data-testid="mock-refused" className="mt-1">
          {strings[report.refused === 'incoherent' ? 'mock.refused.incoherent' : 'mock.refused.no_example']}
        </p>
      ) : (
        <>
          <ul className="mt-1 list-disc pl-5">
            {parts.map((part) => (
              <li key={part}>{part}</li>
            ))}
          </ul>
          {!report.whole && <p className="mt-1 text-fs-muted">{strings['mock.panel.real']}</p>}
        </>
      )}
      <p className="mt-1 text-xs text-fs-muted">{strings['mock.panel.switch']}</p>
    </div>
  )
}
