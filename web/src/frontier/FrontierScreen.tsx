import { useState } from 'react'
import { c } from './copy'
import PreloadPanel from './PreloadPanel'
import RotationPanel from './RotationPanel'
import StressPanel from './StressPanel'
import DecisionPanel from './DecisionPanel'
import PlanPanel from './PlanPanel'
import { Segmented } from './ui'

const VIEWS = [
  { id: '1', label: c('view.1'), panel: <PreloadPanel /> },
  { id: '2', label: c('view.2'), panel: <RotationPanel /> },
  { id: '3', label: c('view.3'), panel: <StressPanel /> },
  { id: '4', label: c('view.4'), panel: <DecisionPanel /> },
  { id: '5', label: c('view.5'), panel: <PlanPanel /> },
]

/**
 * Frontier showcase (isolated demo branch): five views over synthetic data,
 * for recording the demo video. It calls no service and computes nothing
 * scientific; every number comes from mock.json and says so on screen.
 */
export default function FrontierScreen() {
  const [view, setView] = useState('1')
  const current = VIEWS.find((v) => v.id === view) ?? VIEWS[0]
  return (
    <div data-testid="frontier-screen">
      <div role="note" className="mb-4 rounded-lg border-2 border-fs-warning bg-fs-warning-bg px-4 py-3">
        <p className="font-extrabold text-fs-warning">{c('badge')}</p>
        <p className="text-sm text-fs-muted">{c('badge.sub')}</p>
      </div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3 print:hidden">
        <div>
          <h1 className="text-3xl font-extrabold leading-tight">{c('title')}</h1>
          <p className="text-sm text-fs-muted">{c('subtitle')}</p>
        </div>
        <Segmented label={c('views.label')} value={view} onChange={setView} options={VIEWS.map((v) => ({ id: v.id, label: v.label }))} />
      </div>
      {current.panel}
    </div>
  )
}
