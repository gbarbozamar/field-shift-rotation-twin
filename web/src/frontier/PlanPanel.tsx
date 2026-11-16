import { useState } from 'react'
import { c } from './copy'
import { M } from './model'
import { cx } from './cx'
import { Card, PanelHead, Pill, Segmented } from './ui'

const CELL: { [code: string]: string } = { O: 'bg-fs-ok', W: 'bg-fs-crop-2', X: 'bg-fs-error' }

function FarmerPlan() {
  const p = M.plan
  const share = Math.round((p.loss / p.limit) * 100)
  return (
    <Card className="print-avoid-break max-w-3xl">
      <h3 className="text-xl font-extrabold">{c('p5.plan.title')}</h3>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="text-fs-muted">{c('p5.plan.field')}</dt><dd className="font-bold">{p.field}</dd></div>
        <div><dt className="text-fs-muted">{c('p5.plan.rotation')}</dt><dd className="font-bold">{p.rotation}</dd></div>
      </dl>
      <h4 className="mt-4 text-sm font-bold">{c('p5.plan.practices')}</h4>
      <ul className="mt-1 list-disc pl-5 text-sm">{p.practices.map((x) => <li key={x}>{x}</li>)}</ul>
      <h4 className="mt-4 text-sm font-bold">{c('p5.plan.loss')}</h4>
      <p className="font-mono text-sm">{p.loss.toFixed(1)} / {p.limit.toFixed(1)} {c('p1.limit.unit')} ({share}%)</p>
      <div className="mt-1 h-3 rounded bg-fs-faint"><div className="h-3 rounded bg-fs-primary" style={{ width: `${share}%` }} /></div>
      <p className="mt-4 text-sm"><span className="text-fs-muted">{c('p5.plan.status')}: </span><Pill tone="ok">{c('p5.grid.within')}</Pill></p>
      <p className="mt-6 rounded border border-fs-warning bg-fs-warning-bg px-3 py-2 text-sm text-fs-warning">{c('p5.plan.not_official')}</p>
      <button type="button" onClick={() => window.print()} className="mt-6 min-h-10 rounded-lg bg-fs-text px-4 text-sm font-bold text-fs-surface print:hidden">
        {c('p5.plan.print')}
      </button>
    </Card>
  )
}

function RegionGrid() {
  const [i, setI] = useState(0)
  const rows = M.grid.rows[i]
  const count = (ch: string) => rows.join('').split(ch).length - 1
  return (
    <div className="space-y-4">
      <Card title={c('p5.grid.period')}>
        <Segmented label={c('p5.grid.period')} value={String(i)} onChange={(id) => setI(Number(id))} options={M.grid.periods.map((t, n) => ({ id: String(n), label: t }))} />
      </Card>
      <Card title={c('p5.grid.title')}>
        <div className="mb-1 grid grid-cols-2 text-center text-xs font-bold text-fs-muted">
          {M.grid.sheds.map((s) => <span key={s}>{c('p5.grid.shed')} {s}</span>)}
        </div>
        <div className="grid gap-1" role="img" aria-label={c('p5.grid.title')}>
          {rows.map((row, r) => (
            <div key={r} className="grid grid-cols-10 gap-1">
              {row.split('').map((ch, n) => (
                <div key={n} className={cx('h-9', 'rounded', CELL[ch], n === 4 ? 'mr-2' : '', n === 5 ? 'ml-2' : '')} />
              ))}
            </div>
          ))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-4 text-sm">
          {([['O', 'p5.grid.within'], ['W', 'p5.grid.risk'], ['X', 'p5.grid.over']] as const).map(([ch, key]) => (
            <li key={ch}><span className={cx('mr-1', 'inline-block', 'h-3', 'w-3', 'rounded', CELL[ch])} />{c(key)}: <strong className="font-mono">{count(ch)}</strong> {c('p5.grid.count')}</li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

export default function PlanPanel() {
  const [mode, setMode] = useState<'farmer' | 'region'>('farmer')
  return (
    <>
      <PanelHead title={c('p5.title')} lead={c('p5.lead')} />
      <div className="mb-4 print:hidden">
        <Segmented
          label={c('p5.toggle.label')}
          value={mode}
          onChange={(id) => setMode(id === 'region' ? 'region' : 'farmer')}
          options={[{ id: 'farmer', label: c('p5.toggle.farmer') }, { id: 'region', label: c('p5.toggle.region') }]}
        />
      </div>
      {mode === 'farmer' ? <FarmerPlan /> : <RegionGrid />}
    </>
  )
}
