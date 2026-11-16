import { formatString } from '../lib/format'
import { strings } from '../strings'
import { unitText } from './boardModel'
import { FACT_KINDS, changedFacts, factsProblems } from './factsDraft'
import type { FactKey, FactKind, FactProblem, FactUnits, FactsDraft } from './factsDraft'

/**
 * The user's own numbers (PROPOSED, l3/original-mock): price, costs, yields,
 * the pasture margin and the soil-loss limit, edited as a draft and sent only
 * with "Compare with these numbers", like the rotations of the builder.
 */

function kindName(kind: FactKind): string {
  return strings[`plant.kind.${kind}`]
}

function labelOf(key: FactKey): string {
  if (key === 'price') return `${strings['board.facts.soybean']}: ${strings['board.facts.price']}`
  if (key === 'cost') return `${strings['board.facts.soybean']}: ${strings['board.facts.cost']}`
  if (key === 'coverCost') return `${strings['board.facts.cover']}: ${strings['board.facts.cost']}`
  if (key === 'limit') return strings['board.facts.limit']
  const [group, kind] = key.split('.') as ['yields' | 'pasture', FactKind]
  return group === 'yields'
    ? `${strings['board.facts.soybean']}: ${formatString(strings['board.facts.yield'], { kind: kindName(kind) })}`
    : `${strings['board.facts.pasture']}: ${formatString(strings['board.facts.margin'], { kind: kindName(kind) })}`
}

function problemText(problem: FactProblem): string {
  return formatString(strings[`board.facts.problem.${problem.kind}`], { field: labelOf(problem.key) })
}

function NumberField({
  testid,
  label,
  unit,
  value,
  invalid,
  onChange,
}: {
  testid: string
  label: string
  unit: string
  value: string
  invalid: boolean
  onChange: (text: string) => void
}) {
  return (
    <label className="block text-sm">
      <span className="block font-semibold">{label}</span>
      <span className="mt-1 flex items-center gap-2">
        <input
          data-testid={testid}
          type="number"
          inputMode="decimal"
          step="any"
          aria-invalid={invalid}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-11 w-full min-w-0 rounded-lg border border-fs-border bg-fs-bg px-2 tabular-nums aria-[invalid=true]:border-fs-error"
        />
        <span className="shrink-0 text-xs text-fs-muted">{unitText(unit)}</span>
      </span>
    </label>
  )
}

export function FactsEditor({
  draft,
  sent,
  units,
  onChange,
  onCompare,
  onReset,
}: {
  draft: FactsDraft
  /** The units the request declares, shown beside each field. */
  units: FactUnits
  sent: FactsDraft
  onChange: (draft: FactsDraft) => void
  onCompare: () => void
  onReset: () => void
}) {
  const problems = factsProblems(draft)
  const bad = new Set(problems.map((problem) => problem.key))
  const changed = changedFacts(draft, sent)
  const field = (key: FactKey, label: string, unit: string, value: string, set: (text: string) => FactsDraft) => (
    <NumberField key={key} testid={`board-fact-${key}`} label={label} unit={unit} value={value} invalid={bad.has(key)} onChange={(text) => onChange(set(text))} />
  )
  return (
    <div data-testid="board-facts" className="mt-6">
      <h4 className="text-lg font-bold">{strings['board.facts.title']}</h4>
      <p className="mb-3 text-sm text-fs-muted">{strings['board.facts.note']}</p>
      <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-4">
        <fieldset className="space-y-2 rounded-xl border border-fs-border bg-fs-surface p-3">
          <legend className="px-1 font-bold">{strings['board.facts.soybean']}</legend>
          {field('price', strings['board.facts.price'], units.price, draft.price, (t) => ({ ...draft, price: t }))}
          {field('cost', strings['board.facts.cost'], units.cost, draft.cost, (t) => ({ ...draft, cost: t }))}
          {FACT_KINDS.map((k) =>
            field(`yields.${k}`, formatString(strings['board.facts.yield'], { kind: kindName(k) }), units.yield, draft.yields[k], (t) => ({
              ...draft,
              yields: { ...draft.yields, [k]: t },
            })),
          )}
        </fieldset>
        <fieldset className="space-y-2 rounded-xl border border-fs-border bg-fs-surface p-3">
          <legend className="px-1 font-bold">{strings['board.facts.cover']}</legend>
          {field('coverCost', strings['board.facts.cost'], units.cost, draft.coverCost, (t) => ({ ...draft, coverCost: t }))}
        </fieldset>
        <fieldset className="space-y-2 rounded-xl border border-fs-border bg-fs-surface p-3">
          <legend className="px-1 font-bold">{strings['board.facts.pasture']}</legend>
          {FACT_KINDS.map((k) =>
            field(`pasture.${k}`, formatString(strings['board.facts.margin'], { kind: kindName(k) }), units.margin, draft.pasture[k], (t) => ({
              ...draft,
              pasture: { ...draft.pasture, [k]: t },
            })),
          )}
        </fieldset>
        <fieldset className="space-y-2 rounded-xl border border-fs-border bg-fs-surface p-3">
          <legend className="px-1 font-bold">{strings['board.facts.limit']}</legend>
          {field('limit', strings['board.facts.limit'], units.limit, draft.limit, (t) => ({ ...draft, limit: t }))}
        </fieldset>
      </div>
      {problems.length !== 0 && (
        <ul data-testid="board-facts-problems" role="alert" className="mt-3 list-disc rounded-xl border border-fs-error bg-fs-error-bg py-2 pl-8 pr-4 text-sm text-fs-error">
          {problems.map((problem) => (
            <li key={problem.key}>{problemText(problem)}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="board-facts-compare"
          disabled={problems.length !== 0 || changed === 0}
          className="min-h-11 cursor-pointer rounded-lg bg-fs-primary px-4 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          onClick={onCompare}
        >
          {strings['board.facts.compare']}
        </button>
        <button
          type="button"
          data-testid="board-facts-reset"
          className="min-h-11 cursor-pointer rounded-lg border border-fs-border bg-fs-surface px-4 font-semibold"
          onClick={onReset}
        >
          {strings['board.facts.reset']}
        </button>
        <p
          data-testid="board-facts-state"
          data-changed={String(changed !== 0)}
          className="text-sm text-fs-muted data-[changed=true]:font-semibold data-[changed=true]:text-fs-warning"
        >
          {changed !== 0 ? formatString(strings['board.facts.changed'], { n: changed }) : strings['board.facts.no_changes']}
        </p>
      </div>
    </div>
  )
}
