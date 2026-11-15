import { useState } from 'react'
import { c } from './copy'
import { M, tippingPrice, verdictAt, viewAt, voiAt } from './model'
import { Card, PanelHead, Pill, Workbench } from './ui'

const TONE = { robust: 'ok', conditional: 'warn', abstain: 'bad' } as const

function ViewCard({ title, price, extreme }: { title: string; price: number; extreme: boolean }) {
  const v = viewAt(price, extreme)
  return (
    <Card title={title}>
      <p className="text-xs text-fs-muted">{c('p4.winner')}</p>
      <p className="text-lg font-extrabold">{v.leader === null ? c('p4.none') : M.rotations[v.leader].name}</p>
      <p className="mt-2 text-xs text-fs-muted">{c('p4.tip')}</p>
      <p className="font-mono text-sm">{c('p4.tip.var')}: {Math.round(tippingPrice(extreme))} {c('p4.tip.unit')}</p>
    </Card>
  )
}

export default function DecisionPanel() {
  const [price, setPrice] = useState(M.price.default)
  const verdict = verdictAt(price)
  return (
    <>
      <PanelHead title={c('p4.title')} lead={c('p4.lead')} />
      <Workbench
        left={
          <>
            <Card title={c('p4.verdict')}>
              <Pill tone={TONE[verdict]}>{c(`p4.verdict.${verdict}` as 'p4.verdict.robust')}</Pill>
              <p className="mt-3 text-sm">{c(`p4.verdict.${verdict}.text` as 'p4.verdict.robust.text')}</p>
            </Card>
            <div className="grid gap-4 sm:grid-cols-2">
              <ViewCard title={c('p4.avg')} price={price} extreme={false} />
              <ViewCard title={c('p4.ext')} price={price} extreme />
            </div>
            <Card title={c('p4.input')}>
              <label className="flex flex-wrap items-center gap-3 text-sm font-semibold">
                <input
                  type="range"
                  min={240}
                  max={420}
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                  aria-label={c('p4.input')}
                  className="min-w-40 flex-1"
                />
                <input
                  type="number"
                  min={240}
                  max={420}
                  value={price}
                  onChange={(e) => setPrice(Math.min(420, Math.max(240, Number(e.target.value) || 240)))}
                  aria-label={c('p4.input')}
                  className="min-h-10 w-24 rounded-lg border border-fs-border bg-fs-surface px-2 font-mono"
                />
                <span className="text-fs-muted">{c('p4.input.unit')}</span>
              </label>
              <p className="mt-2 text-xs text-fs-muted">{c('p4.band')}: +/- {M.price.band} {c('p4.tip.unit')}</p>
            </Card>
          </>
        }
        right={
          <Card title={c('p4.measure')}>
            <ol className="space-y-3">
              {M.measures.map((m, i) => (
                <li key={m.label} className="flex items-center gap-3 rounded-lg border border-fs-border p-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fs-text font-bold text-fs-surface">{i + 1}</span>
                  <span className="flex-1 text-sm font-semibold">{m.label}</span>
                  <span className="text-right">
                    <span className="block text-xs text-fs-muted">{c('p4.voi')}</span>
                    <span className="font-mono text-lg font-bold">{voiAt(m.voi, price).toFixed(1)}</span>
                    <span className="ml-1 text-xs text-fs-muted">{c('p4.voi.unit')}</span>
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-3 text-xs text-fs-muted">{c('p4.voi.note')}</p>
          </Card>
        }
      />
    </>
  )
}
