import { useState } from 'react'
import { c } from './copy'
import { exceeds } from './cx'
import { M, tippingPrice } from './model'
import { Bar, Card, PanelHead, Segmented, Workbench } from './ui'
import LiveIndicators from './LiveIndicators'

const LIMIT = M.fields[0].limit

function Rows({ children }: { children: (i: number) => React.ReactNode }) {
  return (
    <ul className="space-y-2">
      {M.rotations.map((r, i) => (
        <li key={r.id} className="grid grid-cols-[8.5rem_1fr] items-center gap-2 text-sm">
          <span className="font-semibold">{r.name}</span>
          <div>{children(i)}</div>
        </li>
      ))}
    </ul>
  )
}

export default function StressPanel() {
  const [h, setH] = useState('h1')
  const [k, setK] = useState(0)
  const horizon = M.horizons.find((x) => x.id === h) ?? M.horizons[0]
  const cs = horizon.cases[k] ?? horizon.cases[0]
  const m = cs.m
  const b = M.base
  return (
    <>
      <PanelHead title={c('p3.title')} lead={c('p3.lead')} />
      <div className="mb-4">
        <LiveIndicators />
      </div>
      <Workbench
        left={
          <>
            <Card title={c('p3.horizon')}>
              <Segmented
                label={c('p3.horizon')}
                value={h}
                onChange={(id) => { setH(id); setK(0) }}
                options={M.horizons.map((x) => ({ id: x.id, label: x.span }))}
              />
              <p className="mt-3 text-sm font-bold">{horizon.label}</p>
            </Card>
            <Card title={c('p3.case')}>
              <Segmented
                label={c('p3.case')}
                value={String(k)}
                onChange={(id) => setK(Number(id))}
                options={horizon.cases.map((x, i) => ({ id: String(i), label: x.label }))}
              />
              <p className="mt-3 text-xs font-semibold text-fs-muted">{c('p3.agreement')}</p>
              <p className="text-sm font-bold">{cs.agree}</p>
            </Card>
            <Card title={c('p3.k.margin')}>
              <Rows>
                {(i) => {
                  const v = Math.round(b.margin[i] * m.margin)
                  return (
                    <div className="flex items-center gap-2">
                      <div className="flex-1"><Bar value={v} max={200} /></div>
                      <span className="w-14 text-right font-mono">{v}</span>
                    </div>
                  )
                }}
              </Rows>
              <p className="mt-2 text-xs text-fs-muted">{c('p3.k.margin.unit')}</p>
              <p className="mt-3 rounded-lg bg-fs-selection p-2 text-sm">
                {c('p3.k.margin.tip')}: <strong className="font-mono">{Math.round(tippingPrice(false))}</strong> {c('p3.k.margin.tip.unit')}
              </p>
            </Card>
          </>
        }
        right={
          <div className="grid gap-4 sm:grid-cols-2">
            <Card title={c('p3.k.loss')} className="sm:col-span-2">
              <Rows>
                {(i) => {
                  const n = b.lossNormative[i]
                  const e = Math.round(n * m.loss * 10) / 10
                  return (
                    <div className="space-y-1">
                      <div className="flex items-center gap-2"><span className="w-24 text-xs text-fs-muted">{c('p3.k.loss.norm')}</span><div className="flex-1"><Bar value={n} max={10} limit={LIMIT} tone="muted" /></div><span className="w-10 text-right font-mono">{n.toFixed(1)}</span></div>
                      <div className="flex items-center gap-2"><span className="w-24 text-xs text-fs-muted">{c('p3.k.loss.expl')}</span><div className="flex-1"><Bar value={e} max={10} limit={LIMIT} tone={exceeds(e, LIMIT) ? 'bad' : 'primary'} /></div><span className="w-10 text-right font-mono">{e.toFixed(1)}</span></div>
                    </div>
                  )
                }}
              </Rows>
              <p className="mt-2 text-xs text-fs-muted">{c('p3.k.loss.unit')} - {c('p3.k.loss.limit')}: {LIMIT.toFixed(1)}</p>
            </Card>
            <Card title={c('p3.k.deficit')}>
              <Rows>
                {(i) => {
                  const v = Math.min(60, Math.round(b.deficit[i] * m.deficit))
                  return <div className="flex items-center gap-2"><div className="flex-1"><Bar value={v} max={60} tone="bad" /></div><span className="w-8 text-right font-mono">{v}</span></div>
                }}
              </Rows>
              <p className="mt-2 text-xs text-fs-muted">{c('p3.k.deficit.unit')}</p>
            </Card>
            <Card title={c('p3.k.residue')}>
              <Rows>
                {(i) => {
                  const v = Math.round(b.residue[i] * m.residue)
                  return <div className="flex items-center gap-2"><div className="flex-1"><Bar value={v} max={100} /></div><span className="w-8 text-right font-mono">{v}</span></div>
                }}
              </Rows>
              <p className="mt-2 text-xs text-fs-muted">{c('p3.k.residue.unit')}</p>
            </Card>
            <Card title={c('p3.k.soc')} className="sm:col-span-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-fs-muted"><th />{[c('p3.k.soc.a'), c('p3.k.soc.b')].map((t) => <th key={t} className="py-1 text-right">{t}</th>)}</tr>
                </thead>
                <tbody>
                  {M.rotations.map((r, i) => (
                    <tr key={r.id} className="border-t border-fs-faint">
                      <td className="py-1.5 font-semibold">{r.name}</td>
                      <td className="text-right font-mono">{(b.socA[i] + m.soc).toFixed(1)}</td>
                      <td className="text-right font-mono">{(b.socB[i] + m.soc).toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-fs-muted">{c('p3.k.soc.unit')}</p>
            </Card>
          </div>
        }
      />
    </>
  )
}
