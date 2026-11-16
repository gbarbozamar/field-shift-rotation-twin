import { useState } from 'react'
import { c } from './copy'
import { M, labelPoint } from './model'
import { Card, Pill, PanelHead, Workbench } from './ui'

const CONF_TONE = { high: 'ok', medium: 'warn', low: 'bad' } as const

const pos = (x: number) => `${((x - 0.1) / 0.4) * 100}%`
const widthOf = (lo: number, hi: number) => `${((hi - lo) / 0.4) * 100}%`

function Range({ label, v }: { label: string; v: number[] }) {
  const [mid, lo, hi] = v
  return (
    <div className="mb-3">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-semibold">{label}</span>
        <span className="font-mono">
          {mid.toFixed(2)} <span className="text-fs-muted">[{lo.toFixed(2)} - {hi.toFixed(2)}] {c('p1.moisture.unit')}</span>
        </span>
      </div>
      <div className="relative mt-2 h-3 rounded bg-fs-faint" aria-label={`${label} ${c('p1.bounds')}`}>
        <div className="absolute h-3 rounded bg-fs-nina/40" style={{ left: pos(lo), width: widthOf(lo, hi) }} />
        <div className="absolute -top-1 h-5 w-1 rounded bg-fs-nina" style={{ left: pos(mid) }} />
      </div>
    </div>
  )
}

export default function PreloadPanel() {
  const [sel, setSel] = useState('f1')
  const f = M.fields.find((x) => x.id === sel) ?? M.fields[0]
  return (
    <>
      <PanelHead title={c('p1.title')} lead={c('p1.lead')} />
      <Workbench
        left={
          <Card title={c('p1.map')}>
            <svg viewBox="0 0 600 400" role="img" aria-label={c('p1.map')} className="w-full rounded bg-fs-faint">
              {M.fields.map((x) => {
                const on = x.id === sel
                const [lx, ly] = labelPoint(x.points)
                return (
                  <g key={x.id}>
                    <polygon
                      points={x.points}
                      fill={on ? 'var(--fs-primary)' : 'var(--fs-crop-1)'}
                      fillOpacity={on ? 0.55 : 0.3}
                      stroke={on ? 'var(--fs-text)' : 'var(--fs-crop-5)'}
                      strokeWidth={on ? 3 : 1.5}
                    />
                    <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize="15" fontWeight="700" fill="var(--fs-text)" pointerEvents="none">
                      {x.name}
                    </text>
                  </g>
                )
              })}
            </svg>
            <p className="mt-2 text-xs text-fs-muted">{c('p1.outlines')}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {M.fields.map((x) => (
                <button
                  key={x.id}
                  type="button"
                  aria-pressed={x.id === sel}
                  onClick={() => setSel(x.id)}
                  className="min-h-10 rounded-lg border border-fs-border px-3 text-sm font-semibold aria-pressed:border-fs-text aria-pressed:bg-fs-selection"
                >
                  {x.name}
                </button>
              ))}
            </div>
          </Card>
        }
        right={
          <>
            <Card title={f.name}>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <div><dt className="text-fs-muted">{c('p1.soil')}</dt><dd className="font-bold">{f.soil}</dd></div>
                <div><dt className="text-fs-muted">{c('p1.slope')}</dt><dd className="font-bold">{f.slope} {c('p1.slope.unit')}</dd></div>
                <div><dt className="text-fs-muted">{c('p1.k')}</dt><dd className="font-bold">{f.k} <span className="font-normal text-fs-muted">{c('p1.k.unit')}</span></dd></div>
                <div><dt className="text-fs-muted">{c('p1.limit')}</dt><dd className="font-bold">{f.limit.toFixed(1)} <span className="font-normal text-fs-muted">{c('p1.limit.unit')}</span></dd></div>
              </dl>
              <p className="mt-3 text-xs text-fs-muted">{c('p1.source')}: {c('p1.source.value')}</p>
            </Card>
            <Card title={c('p1.history')}>
              <ul className="grid grid-cols-5 gap-2 text-center text-sm">
                {f.history.map(([season, crop, conf]) => (
                  <li key={season} className="rounded-lg border border-fs-border p-2">
                    <div className="font-mono text-xs text-fs-muted">{season}</div>
                    <div className="my-1 font-bold">{crop}</div>
                    <Pill tone={CONF_TONE[conf as 'high' | 'medium' | 'low']}>{c(`p1.conf.${conf}` as 'p1.conf.high')}</Pill>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title={c('p1.moisture')}>
              <Range label={c('p1.surface')} v={f.surface} />
              <Range label={c('p1.root')} v={f.root} />
            </Card>
          </>
        }
      />
    </>
  )
}
