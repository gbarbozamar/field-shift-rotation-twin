import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { renderToString } from 'react-dom/server'
import { decisionExample } from '../decision/decisionData'
import { strings } from '../strings'
import { LiveDecisionView } from './LiveDecision'
import { liveDecisionRequest, pairTone } from './liveDecision'
import NAMES from './pairStateNames.json'

const here = dirname(fileURLToPath(import.meta.url))

describe('the live decision of the frontier panel', () => {
  it('the pair state names it colours are names of the decision output contract', () => {
    const models = readFileSync(resolve(here, '../../../contracts/decision_output/models.py'), 'utf8')
    const block = models.slice(models.indexOf('StateName = Literal['), models.indexOf(']', models.indexOf('StateName = Literal[')))
    const names = [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1])
    expect(names).toContain(NAMES.robust)
    expect(names).toContain(NAMES.notRobust)
    expect(names).toContain(NAMES.identical)
    expect(names.some((name) => name.startsWith(NAMES.notSeparatedPrefix))).toBe(true)
    expect(names.map(pairTone)).not.toContain(undefined)
  })

  it('colours each state as robust, conditional or not separated', () => {
    expect(pairTone(NAMES.robust)).toBe('ok')
    expect(pairTone(NAMES.notRobust)).toBe('warn')
    expect(pairTone(`${NAMES.notSeparatedPrefix}: within uncertainty`)).toBe('bad')
    expect(pairTone(NAMES.identical)).toBe('neutral')
  })

  it('asks for the first field and the two rotations held for it', () => {
    const request = liveDecisionRequest()
    expect(request).not.toBeNull()
    expect(request!.rotations).toHaveLength(2)
  })

  it('without a backend it says so; a missing decision shows its reason; a decision shows its measure-first list', () => {
    expect(renderToString(<LiveDecisionView phase={{ kind: 'not_configured' }} />)).toContain(strings['frontier.live.not_configured'])
    const missing = renderToString(
      <LiveDecisionView phase={{ kind: 'answered', answer: { kind: 'missing', missing: { reason: 'MISSING_INPUT', detail: 'no climate' } } }} />,
    )
    expect(missing).toContain('data-testid="frontier-live-missing"')
    const decided = renderToString(
      <LiveDecisionView phase={{ kind: 'answered', answer: { kind: 'decision', document: decisionExample, liveData: false } }} />,
    )
    expect(decided).toContain(decisionExample.measure_first[0].what)
  })
})

describe('the live indicators of the stress-test panel', async () => {
  const { LiveIndicatorsView, liveRunRequests } = await import('./LiveIndicators')

  it('asks once per rotation held for Field 1', () => {
    expect(liveRunRequests()).toHaveLength(2)
  })

  it('a run with no result shows its reason; no backend, it says so', () => {
    const html = renderToString(
      <LiveIndicatorsView
        configured
        runs={[{ label: 'A', phase: { kind: 'answered', view: { outcome: 'no_result', liveData: false, parts: [], resultMissing: { reason: 'MISSING_INPUT', detail: 'no climate' } } } }]}
      />,
    )
    expect(html).toContain('data-testid="frontier-kpi-missing"')
    expect(renderToString(<LiveIndicatorsView configured={false} runs={[]} />)).toContain(strings['frontier.live.not_configured'])
  })
})
