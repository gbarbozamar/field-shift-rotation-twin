import { useState } from 'react'
import { c } from './copy'
import { M, monthRisk, rotationRisk } from './model'
import { cx } from './cx'
import { Card, Pill, PanelHead, Workbench } from './ui'

const KIND_CLASS: { [kind: string]: string } = {
  crop: cx('bg-fs-crop-2', 'text-fs-text'),
  cover: cx('bg-fs-crop-5', 'text-fs-surface'),
  pasture: cx('bg-fs-crop-1', 'text-fs-text'),
}
const RISK_TONE = { low: 'ok', medium: 'warn', high: 'bad' } as const

function MonthBars({ values, max, unit, tone }: { values: number[]; max: number; unit: string; tone: string }) {
  return (
    <div className="grid grid-cols-12 gap-1" role="img" aria-label={unit}>
      {values.map((v, i) => (
        <div key={M.months[i]} className="flex flex-col items-center">
          <span className="font-mono text-[11px] text-fs-muted">{v}</span>
          <div className="flex h-16 w-full items-end rounded bg-fs-faint">
            <div className={cx('w-full', 'rounded', tone)} style={{ height: `${(v / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function MonthAxis() {
  return (
    <div className="grid grid-cols-12 gap-1 text-center font-mono text-[11px] text-fs-muted">
      {M.months.map((m) => <span key={m}>{m}</span>)}
    </div>
  )
}

function Ribbons({ index }: { index: number }) {
  const rot = M.rotations[index]
  return (
    <div className="space-y-2">
      {rot.years.map((year, yi) => (
        <div key={yi} className="grid grid-cols-[3.5rem_1fr] items-center gap-2">
          <span className="text-xs font-semibold text-fs-muted">{c('p2.year')} {yi + 1}</span>
          <div className="grid grid-cols-12 gap-1">
            {year.map(([name, kind, from, to, flower]) => (
              <div
                key={`${name}${from}`}
                className={cx('relative', 'flex', 'h-9', 'items-center', 'justify-center', 'overflow-hidden', 'rounded', 'px-1', 'text-xs', 'font-bold', KIND_CLASS[kind as string])}
                style={{ gridColumn: `${(from as number) + 1} / ${(to as number) + 2}` }}
              >
                {name}
                {(flower as number) >= 0 ? (
                  <span
                    title={c('p2.flower')}
                    className="absolute -bottom-0.5 -ml-1 h-2 w-2 rounded-full border border-fs-text bg-fs-surface"
                    style={{ left: `${((((flower as number) - (from as number)) + 0.5) / ((to as number) - (from as number) + 1)) * 100}%` }}
                  />
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function RotationPanel() {
  const [pick, setPick] = useState(0)
  const risk = rotationRisk(pick)
  return (
    <>
      <PanelHead title={c('p2.title')} lead={c('p2.lead')} />
      <Workbench
        left={
          <>
            <div className="flex flex-wrap gap-2" role="group" aria-label={c('p2.pick')}>
              {M.rotations.map((r, i) => (
                <button
                  key={r.id}
                  type="button"
                  aria-pressed={i === pick}
                  onClick={() => setPick(i)}
                  className="min-h-10 rounded-lg border border-fs-border px-3 text-sm font-semibold aria-pressed:border-fs-text aria-pressed:bg-fs-selection"
                >
                  {r.name}
                </button>
              ))}
            </div>
            <Card title={M.rotations[pick].name}>
              <Ribbons index={pick} />
              <ul className="mt-3 flex flex-wrap gap-3 text-xs text-fs-muted">
                <li><span className="mr-1 inline-block h-2.5 w-2.5 rounded bg-fs-crop-2" />{c('p2.kind.crop')}</li>
                <li><span className="mr-1 inline-block h-2.5 w-2.5 rounded bg-fs-crop-5" />{c('p2.kind.cover')}</li>
                <li><span className="mr-1 inline-block h-2.5 w-2.5 rounded bg-fs-crop-1" />{c('p2.kind.pasture')}</li>
                <li><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full border border-fs-text" />{c('p2.flower')}</li>
              </ul>
            </Card>
            <Card title={c('p2.risk')}>
              <div className="flex items-center gap-3">
                <Pill tone={RISK_TONE[risk]}>{c(`p2.risk.${risk}` as 'p2.risk.low')}</Pill>
                <p className="text-sm text-fs-muted">{c('p2.risk.note')}</p>
              </div>
            </Card>
          </>
        }
        right={
          <>
            <Card title={c('p2.clock.rain')}>
              <MonthBars values={M.clocks.rain} max={14} unit={c('p2.rain.unit')} tone="bg-fs-nina" />
              <MonthAxis />
              <p className="mt-1 text-xs text-fs-muted">{c('p2.rain.unit')}</p>
            </Card>
            <Card title={c('p2.clock.et0')}>
              <MonthBars values={M.clocks.et0} max={180} unit={c('p2.et0.unit')} tone="bg-fs-nino" />
              <MonthAxis />
              <p className="mt-1 text-xs text-fs-muted">{c('p2.et0.unit')}</p>
            </Card>
            <Card>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <h4 className="mb-1 text-sm font-bold">{c('p2.frost')}</h4>
                  <MonthBars values={M.clocks.frost} max={6} unit={c('p2.frost')} tone="bg-fs-info" />
                </div>
                <div>
                  <h4 className="mb-1 text-sm font-bold">{c('p2.heat')}</h4>
                  <MonthBars values={M.clocks.heat} max={8} unit={c('p2.heat')} tone="bg-fs-warning" />
                </div>
              </div>
              <MonthAxis />
              <p className="mt-2 text-xs text-fs-muted">
                {M.months.map((m, i) => (monthRisk(i) === 'high' ? m : null)).filter(Boolean).join(', ')}: {c('p2.risk.high')}
              </p>
            </Card>
          </>
        }
      />
    </>
  )
}
