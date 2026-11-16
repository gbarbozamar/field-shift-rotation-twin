import type { ReactNode } from 'react'
import { ValueDisplay, displayNumber, missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { barPercent, drawnSoilVerdict, stateTone, verdictTone } from '../plant/optionBars'
import { RotationTimeline, StatePill } from '../plant/PlantVisuals'
import { KINDS_OF_YEAR, MARGINS_OF } from '../plant/plantData'
import type { Measured, PlantAnswer, PlantOption } from '../plant/plantData'
import { cropOrder } from '../plant/rotationStrip'
import type { RotationStrip } from '../plant/rotationStrip'
import type { RotationDefinition } from '../rotation/exampleRotation'
import { strings } from '../strings'
import { MockBadge } from '../mockfill/MockPanel'
import { indicatorName } from '../results/ResultCards'
import type { CarbonModelId, CarbonPart, CarbonValue, IndicatorId, ResultsPerRotation, WaterPart } from '../results/resultsData'
import type { BoardRun } from './boardRuns'
import { SORT_KEYS, cropName, isExampleCrop, unitText, worstKind } from './boardModel'
import type { BoardColumn, SortKey } from './boardModel'
import { isUserRotation } from './rotationDraft'

/**
 * The options side by side (PROPOSED, l3/board): one column per rotation, in
 * the order picked, and one row per thing to compare, so that every value of
 * an option sits beside the same value of the others.
 *
 * Display only. A column is named by its letter and its crops; a missing
 * value is a hatched bar and "no value", never 0; a soil loss the answer
 * says is over the limit is marked in words as well as in colour.
 */

/** What the request says of the rotation of an option. */
export interface OptionInfo {
  rotation: RotationDefinition | null
  strip: RotationStrip | null
}

export interface CompareScales {
  margin: number | null
  soilLoss: number | null
}

/** The crops of a rotation in the order they are first sown, as names to read. */
export function cropsText(strip: RotationStrip | null): string | null {
  if (strip === null) {
    return null
  }
  const crops = cropOrder([strip])
  return crops.length === 0 ? null : crops.map(cropName).join(strings['board.crops_join'])
}

/**
 * How the board names an option, everywhere: by the name the user gave it,
 * or, for a rotation of the request, by its crops; its id when the request
 * says nothing of it.
 */
export function optionTitle(option: PlantOption, { rotation, strip }: OptionInfo): string {
  if (rotation !== null && isUserRotation(rotation.rotation_id)) {
    return rotation.label
  }
  return cropsText(strip) ?? option.rotation_id
}

/**
 * What the picker says when the order picked cannot place every option:
 * none of them (nothing was ordered), or how many are left out. Null when
 * every option is placed, and for the order of the request.
 */
export function orderNote(columns: BoardColumn[], sort: SortKey): string | null {
  if (sort === 'yours') {
    return null
  }
  const unplaced = columns.filter((column) => column.position === null).length
  if (unplaced === 0) {
    return null
  }
  if (unplaced === columns.length) {
    return strings[sort === 'rule' ? 'board.sort.none_rule' : 'board.sort.none']
  }
  // Under the rule, options outside the limit have no place by design: their
  // state already says why, so no note is added.
  return sort === 'rule' ? null : formatString(strings['board.sort.some'], { n: unplaced })
}

/** True when a crop of the rotation is a placeholder of the example data. */
export function hasExampleCrops(strip: RotationStrip | null): boolean {
  return strip !== null && cropOrder([strip]).some(isExampleCrop)
}

/** The selector of what the options are ordered by. */
export function SortPicker({ sort, onSort }: { sort: SortKey; onSort: (sort: SortKey) => void }) {
  return (
    <label data-testid="board-sort" className="inline-flex min-w-0 max-w-full flex-wrap items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-widest text-fs-muted">{strings['board.sort.label']}</span>
      <select
        className="min-h-9 min-w-0 max-w-full cursor-pointer rounded-lg border border-fs-border bg-fs-surface px-3 py-1 text-sm font-semibold"
        value={sort}
        onChange={(event) => {
          const picked = SORT_KEYS.find((key) => key === event.target.value)
          if (picked !== undefined) onSort(picked)
        }}
      >
        {SORT_KEYS.map((key) => (
          <option key={key} value={key}>
            {strings[`board.sort.${key}`]}
          </option>
        ))}
      </select>
    </label>
  )
}

/** A missing number: "no value" with its reason, cut to two lines; the whole reason on hover. */
function Missing({ item }: { item: Measured }) {
  const text = item.missing !== null ? missingPatternText(strings['plant.table.no_value'], item.missing) : strings['plant.table.no_value']
  return (
    <span data-testid="board-missing" className="line-clamp-2 text-xs italic text-fs-muted" title={text}>
      {text}
    </span>
  )
}

/** The mark of the note a number carries: its label, its source and its range are said once, under the table. */
export const SOIL_MARK = '1'
export const MARGIN_MARK = '2'

function Mark({ mark }: { mark: string }) {
  return (
    <sup data-testid="board-mark" className="ml-0.5 font-mono text-[10px] font-normal text-fs-muted">
      {mark}
    </sup>
  )
}

/**
 * The uncertainty of a number, said beside it: its range, or that it has
 * none (the reason the answer gives travels in the title). Nothing for a
 * missing number, whose reason is already shown.
 */
export function RangeLine({ item, className = 'block text-[11px] text-fs-muted' }: { item: Measured; className?: string }) {
  if (item.labels === null) return null
  if (item.labels.range !== null) {
    return (
      <span data-testid="board-range" className={className}>
        {formatString(strings['value.range'], {
          low: displayNumber(item.labels.range.low),
          high: displayNumber(item.labels.range.high),
          kind: item.labels.range.kind,
        })}
      </span>
    )
  }
  const reason = item.labels.range_missing
  return (
    <span
      data-testid="board-no-range-line"
      className={className}
      title={reason === null ? undefined : missingPatternText(strings['board.no_range'], reason)}
    >
      {strings['board.no_range']}
    </span>
  )
}

/**
 * A number of the table: its unit is said once, in the head of its row, and
 * its mark points at its note. Its range, when the answer carries one, is
 * shown under it.
 */
function Number({ item, mark }: { item: Measured; mark: string }) {
  if (item.value === null) {
    return (
      <Missing item={item} />
    )
  }
  return (
    <span className="tabular-nums" title={String(item.value)}>
      <span className="font-fs-heading text-xl font-extrabold">{displayNumber(item.value)}</span>
      <Mark mark={mark} />
      <RangeLine item={item} />
    </span>
  )
}

/**
 * The one value a row holds when every option has the same: the same number,
 * or the same missing value with the same reason. Null when the options
 * differ, or there is a single option. Equality of values the answer
 * carries; nothing is computed.
 */
export function uniformItem(items: Measured[]): Measured | null {
  if (items.length < 2) {
    return null
  }
  const [first, ...rest] = items
  const same = rest.every((item) =>
    first.value !== null
      ? item.value === first.value
      : item.value === null && JSON.stringify(item.missing) === JSON.stringify(first.missing),
  )
  return same ? first : null
}

/** A row that holds one value for every option: said once, across the columns. */
function MergedCell({ item, mark, span }: { item: Measured; mark: string; span: number }) {
  const text =
    item.missing !== null ? missingPatternText(strings['plant.table.no_value'], item.missing) : null
  return (
    <td data-testid="board-merged" colSpan={span} className="border-l border-fs-border px-4 py-3 align-top">
      <span className="font-mono text-[10px] uppercase tracking-widest text-fs-muted">{strings['board.same_for_all']}</span>
      {text !== null ? (
        <span className="block text-sm italic text-fs-muted">{text}</span>
      ) : (
        <span className="block">
          <Number item={item} mark={mark} />
        </span>
      )}
    </td>
  )
}

/** A bar from zero: its share of the largest value shown; hatched when the value is missing. */
function Bar({
  testid,
  item,
  scale,
  tone,
  limit = null,
}: {
  testid: string
  item: Measured
  scale: number | null
  tone: string
  limit?: number | null
}) {
  const drawn = item.value !== null && scale !== null
  return (
    <div
      data-testid={testid}
      data-empty={String(!drawn)}
      aria-hidden="true"
      className="relative mt-1 h-3 rounded-full bg-fs-faint data-[empty=true]:fs-fog"
    >
      {drawn ? (
        <span
          data-tone={tone}
          data-negative={String(item.value! < 0)}
          className="absolute inset-y-0 left-0 rounded-full bg-fs-primary data-[negative=true]:border-2 data-[negative=true]:border-dashed data-[negative=true]:border-fs-error data-[negative=true]:bg-fs-error-bg data-[tone=meets]:bg-fs-ok data-[tone=none]:bg-fs-muted data-[tone=open]:bg-fs-warning data-[tone=over]:bg-fs-error"
          style={{ width: `${barPercent(item.value!, scale!)}%` }}
        />
      ) : null}
      {limit !== null && scale !== null ? (
        <span
          data-testid="board-limit-tick"
          className="absolute -bottom-1 -top-1 w-0.5 rounded bg-fs-text"
          style={{ left: `${barPercent(limit, scale)}%` }}
        />
      ) : null}
    </div>
  )
}

function Row({
  label,
  note = null,
  selected = false,
  columns,
  cell,
  merged = null,
}: {
  label: string
  /** What is said once for the whole row: its unit, the limit it is read against. */
  note?: ReactNode
  /** True for the row of the kind of year looked at. */
  selected?: boolean
  columns: BoardColumn[]
  cell: (option: PlantOption) => ReactNode
  /** Given when every option holds the same value: one cell across the columns, in place of theirs. */
  merged?: ReactNode
}) {
  return (
    <tr data-selected={String(selected)} className="border-t border-fs-border data-[selected=true]:font-semibold">
      <th scope="row" className="sticky left-0 z-10 bg-fs-surface px-4 py-3 text-left align-top text-xs font-semibold uppercase tracking-wide text-fs-muted">
        {label}
        {note !== null ? (
          <span className="mt-0.5 block font-normal normal-case tracking-normal">{note}</span>
        ) : null}
      </th>
      {merged !== null
        ? merged
        : columns.map(({ option }) => (
            <td
              key={option.rotation_id}
              data-tone={stateTone(option.state)}
              className="border-l border-fs-border px-4 py-3 align-top data-[tone=chosen]:bg-fs-selection"
            >
              {cell(option)}
            </td>
          ))}
    </tr>
  )
}

/** One kind of year of an option: its margin, and its soil loss with what the answer says of it. */
function KindCell({
  option,
  kind,
  worst,
  mockSoil,
  mockMargin,
}: {
  /** True when the margin shown is mock example data. */
  mockMargin: boolean
  /** True when the soil loss shown is mock example data. */
  mockSoil: boolean
  option: PlantOption
  kind: (typeof KINDS_OF_YEAR)[number]
  /** True when this is the kind of year in which the option has its smallest margin. */
  worst: boolean
}) {
  const margin = option.margin[kind]
  const loss = option.soil_loss[kind]
  const tone = verdictTone(drawnSoilVerdict(option, kind))
  return (
    <div className="tabular-nums">
      {margin.value !== null ? (
        <p title={String(margin.value)}>
          <span className="font-fs-heading text-base font-bold">{displayNumber(margin.value)}</span>
          {mockMargin && <MockBadge />}
          <RangeLine item={margin} className="ml-1.5 text-[10px] font-normal text-fs-muted" />
          {worst ? (
            <span data-testid="board-worst" className="ml-1.5 rounded border border-fs-border px-1 text-[10px] font-semibold uppercase text-fs-muted">
              {strings['board.worst_mark']}
            </span>
          ) : null}
        </p>
      ) : (
        <p className="text-sm italic text-fs-muted">{strings['plant.table.no_value']}</p>
      )}
      {loss.value !== null ? (
        <p
          data-tone={tone}
          className="text-xs text-fs-muted data-[tone=over]:font-bold data-[tone=over]:text-fs-error"
          title={String(loss.value)}
        >
          {formatString(strings['board.kind.soil'], { value: displayNumber(loss.value) })}
          <Mark mark={SOIL_MARK} />
          {mockSoil && <MockBadge />}
          {tone === 'over' ? (
            <span className="ml-1 uppercase">{strings['plant.table.over_limit']}</span>
          ) : tone === 'open' ? (
            <span data-testid="board-kind-not-resolved" className="ml-1 uppercase text-fs-warning">{strings['plant.pill.not_resolved']}</span>
          ) : tone === 'none' ? (
            <span data-testid="board-kind-not-in-record" className="ml-1 uppercase">{strings['board.kind.not_in_record']}</span>
          ) : null}
          <span data-testid="board-kind-years" className="block text-[10px] text-fs-muted">
            {formatString(strings['board.kind.mean_years'], { n: loss.n_years })}
          </span>
        </p>
      ) : (
        <p className="text-xs italic text-fs-muted">
          {formatString(strings['board.kind.soil_missing'], { missing: strings['plant.table.no_value'] })}
        </p>
      )}
    </div>
  )
}

/** A part that is wholly missing (its engine not built): its absence, with its reason. */
function WhollyMissing({ indicator, unit, missing }: { indicator: IndicatorId; unit: string; missing: MissingPart }) {
  return <ValueDisplay what={indicatorName(indicator)} item={{ value: null, unit, missing }} />
}

/** Water-deficit exposure of one run: each value as the result gives it, by agricultural year when it is per year. */
function WaterValues({ part }: { part: WaterPart }) {
  if (part.form === 'not_built') {
    return <WhollyMissing indicator={part.indicator} unit={part.units[0]} missing={part.missing} />
  }
  const name = indicatorName(part.indicator)
  return (
    <ul data-testid="board-water" className="space-y-1">
      {part.values.map((value, index) => (
        <li key={value.ag_year ?? `r-${index}`} className={['flex', 'gap-2', '[&>div]:min-w-0', '[&>div]:flex-1'].join(' ')}>
          {value.ag_year !== undefined && value.item.value !== null ? (
            <span data-testid="board-water-year" className="font-mono text-xs text-fs-muted">
              {value.ag_year}
            </span>
          ) : null}
          <ValueDisplay what={value.ag_year === undefined ? name : name + ' ' + String(value.ag_year)} item={value.item} />
        </li>
      ))}
    </ul>
  )
}

/** The carbon values of a result, one group per carbon model in the order they travel; never merged. */
function byModel(values: CarbonValue[]): { model: CarbonModelId; values: CarbonValue[] }[] {
  const groups: { model: CarbonModelId; values: CarbonValue[] }[] = []
  for (const value of values) {
    const group = groups.find((each) => each.model === value.carbon_model)
    if (group !== undefined) group.values.push(value)
    else groups.push({ model: value.carbon_model, values: [value] })
  }
  return groups
}

/** Soil carbon trend of one run: one line per carbon model, each value with its computation, as the data gives it. */
function CarbonValues({ part }: { part: CarbonPart }) {
  if (part.form === 'not_built') {
    return <WhollyMissing indicator={part.indicator} unit={part.units[0]} missing={part.missing} />
  }
  const name = indicatorName(part.indicator)
  return (
    <ul className="space-y-2">
      {byModel(part.values).map(({ model, values }) => (
        <li key={model} data-testid="board-carbon-model">
          <p className="text-xs font-semibold text-fs-muted">{formatString(strings['cards.model_label'], { model })}</p>
          <ul className="space-y-1">
            {values.map((value) => (
              <li key={value.computation} data-testid="board-carbon-item">
                <p className="text-[11px] text-fs-muted">
                  {formatString(strings['cards.computation_label'], { computation: value.computation })}
                </p>
                <ValueDisplay what={name} item={value.item} />
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  )
}

/**
 * One cell of a row read from the run of an option: its result through
 * `show`, or the state of the run (on its way, failed with the route's
 * error, no result with its reason, a result this screen cannot read).
 * An option the request holds no rotation for has no run: no value.
 */
function RunCell({
  run,
  indicator,
  show,
}: {
  run: BoardRun | undefined
  indicator: IndicatorId
  show: (result: ResultsPerRotation) => ReactNode
}) {
  if (run === undefined) {
    return <span className="text-sm italic text-fs-muted">{strings['plant.table.no_value']}</span>
  }
  switch (run.phase) {
    case 'pending':
      return (
        <span data-testid="board-run-pending" role="status" className="text-xs text-fs-muted">
          {strings['board.run.pending']}
        </span>
      )
    case 'failed':
      return (
        <span data-testid="board-run-failed" className="text-xs text-fs-error">
          {strings[`api.${run.code}`]}
        </span>
      )
    case 'no_result':
      return (
        <span data-testid="board-run-missing" className="text-xs italic text-fs-muted">
          {missingPatternText(indicatorName(indicator), run.missing)}
        </span>
      )
    case 'unreadable':
      return (
        <span data-testid="board-run-unreadable" className="text-xs text-fs-error">
          {strings['cards.live_unreadable']}
        </span>
      )
    case 'result':
      return <>{show(run.result)}</>
  }
}

/**
 * The comparison: a column per option with its position, letter, crops and
 * state; then its crops by month, its margin and its soil loss for the kind
 * of year looked at, its water-deficit exposure and soil carbon trend (from
 * the run of its rotation, when runs are given), and each kind of year.
 */
export function CompareTable({
  answer,
  columns,
  info,
  order,
  scales,
  sort,
  mockSoilKinds = [],
  mockMarginKinds = [],
  runs = null,
}: {
  /** The run of each option's rotation, by rotation id; null shows no water and carbon rows. */
  runs?: ReadonlyMap<string, BoardRun> | null
  /** The kinds of year whose margin is mock example data (the board mixing). */
  mockMarginKinds?: readonly string[]
  answer: PlantAnswer
  columns: BoardColumn[]
  /** The kinds of year (or average) whose soil loss is mock example data (the board mixing). */
  mockSoilKinds?: readonly string[]
  /** What the columns are ordered by: only the rule of the answer gives a first place. */
  sort: SortKey
  info: (option: PlantOption) => OptionInfo
  /** The crops of all the options, for one set of colours. */
  order: readonly string[]
  scales: CompareScales
}) {
  const kind = answer.margin_of
  // The units and the limit are those of the answer, said once per row. Every
  // option is judged against one limit (a rule of the contract), so the first
  // option that carries it speaks for the row.
  const first = answer.options[0]
  const marginUnit = unitText(first.margin[kind].unit)
  const soilUnit = unitText(first.soil_loss[kind].unit)
  const limited = answer.options.find((option) => option.limit !== null)
  const limit = limited !== undefined ? { value: limited.limit!, unit: limited.limit_unit } : null
  const sameMargin = uniformItem(columns.map((column) => column.option.margin[kind]))
  const sameSoil = uniformItem(columns.map((column) => column.option.soil_loss[kind]))
  return (
    <div className="overflow-x-auto rounded-2xl border border-fs-border bg-fs-surface">
      <table
        data-testid="board-compare"
        className="w-full table-fixed border-collapse"
        style={{ minWidth: `${9 + columns.length * 12}rem` }}
      >
        <colgroup>
          <col className="w-36" />
        </colgroup>
        <thead>
          <tr>
            <td className="sticky left-0 z-10 bg-fs-surface" />
            {columns.map(({ option, letter, position, tied }) => {
              const { rotation, strip } = info(option)
              return (
                <th
                  key={option.rotation_id}
                  scope="col"
                  data-testid="board-option"
                  data-state={option.state}
                  data-tone={stateTone(option.state)}
                  className="border-l border-fs-border px-4 pb-3 pt-4 text-left align-top font-normal data-[tone=chosen]:bg-fs-selection data-[tone=chosen]:shadow-[inset_0_4px_0_var(--fs-primary)]"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {position !== null ? (
                      <span
                        data-testid="board-position"
                        data-first={String(position === 1 && sort === 'rule')}
                        className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-fs-border font-fs-heading text-base font-extrabold text-fs-muted data-[first=true]:border-fs-primary data-[first=true]:bg-fs-primary data-[first=true]:text-white"
                      >
                        {position}
                      </span>
                    ) : null}
                    <span data-testid="board-letter" className="font-mono text-[11px] uppercase tracking-widest text-fs-muted">
                      {formatString(strings['board.option'], { letter })}
                    </span>
                    {tied ? (
                      <span data-testid="board-tied" className="rounded-full border border-fs-border px-2 py-0.5 text-[11px] font-semibold text-fs-muted">
                        {strings['board.tied']}
                      </span>
                    ) : null}
                    <StatePill state={option.state} />
                  </div>
                  <p
                    data-testid="board-option-crops"
                    className="mt-2 font-fs-heading text-xl font-extrabold leading-tight"
                    title={rotation !== null ? rotation.label : undefined}
                  >
                    {optionTitle(option, { rotation, strip })}
                  </p>
                  {rotation !== null && isUserRotation(rotation.rotation_id) && cropsText(strip) !== null ? (
                    <p data-testid="board-option-crops-line" className="text-sm font-semibold">
                      {cropsText(strip)}
                    </p>
                  ) : null}
                  {strip !== null && strip.years.length !== 0 ? (
                    <p className="text-xs text-fs-muted">
                      {formatString(strings['board.cycle'], { n: strip.years.length })}
                    </p>
                  ) : null}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          <Row
            label={strings['board.row.crops']}
            columns={columns}
            cell={(option) => {
              const { strip } = info(option)
              return strip !== null ? (
                <RotationTimeline strip={strip} order={order} />
              ) : (
                <span className="text-sm italic text-fs-muted">{strings['plant.table.no_value']}</span>
              )
            }}
          />
          <Row
            label={formatString(strings['plant.margin_of'], { kind: strings[`plant.kind.${kind}`] })}
            note={
              <>
                {marginUnit}
                {mockMarginKinds.includes(kind) && <MockBadge />}
              </>
            }
            columns={columns}
            merged={
              sameMargin !== null ? (
                <MergedCell item={sameMargin} mark={MARGIN_MARK} span={columns.length} />
              ) : null
            }
            cell={(option) => (
              <div>
                <Number item={option.margin[kind]} mark={MARGIN_MARK} />
                <Bar testid="board-bar-margin" item={option.margin[kind]} scale={scales.margin} tone="chosen" />
              </div>
            )}
          />
          <Row
            label={formatString(strings['plant.soil_loss_of'], { kind: strings[`plant.kind.${kind}`] })}
            note={
              <>
                {soilUnit}
                {mockSoilKinds.includes(kind) && <MockBadge />}
                {limit !== null ? (
                  <span data-testid="board-row-limit" className="block font-semibold text-fs-text">
                    {formatString(strings['board.limit_is'], { limit: displayNumber(limit.value), unit: unitText(limit.unit) })}
                  </span>
                ) : null}
              </>
            }
            columns={columns}
            merged={
              sameSoil !== null ? (
                <MergedCell item={sameSoil} mark={SOIL_MARK} span={columns.length} />
              ) : null
            }
            cell={(option) => (
              <div>
                <Number item={option.soil_loss[kind]} mark={SOIL_MARK} />
                <Bar
                  testid="board-bar-soil"
                  item={option.soil_loss[kind]}
                  scale={scales.soilLoss}
                  tone={verdictTone(drawnSoilVerdict(option, kind))}
                  limit={option.limit}
                />
              </div>
            )}
          />
          {runs !== null ? (
            <>
              <Row
                label={indicatorName('water_deficit_exposure')}
                columns={columns}
                cell={(option) => (
                  <RunCell
                    run={runs.get(option.rotation_id)}
                    indicator="water_deficit_exposure"
                    show={(result) => <WaterValues part={result.water_deficit_exposure} />}
                  />
                )}
              />
              <Row
                label={indicatorName('soil_carbon_trend')}
                columns={columns}
                cell={(option) => (
                  <RunCell
                    run={runs.get(option.rotation_id)}
                    indicator="soil_carbon_trend"
                    show={(result) => <CarbonValues part={result.soil_carbon_trend} />}
                  />
                )}
              />
            </>
          ) : null}
          {KINDS_OF_YEAR.map((each) => (
            <Row
              key={each}
              label={strings[`plant.kind.${each}`]}
              note={formatString(strings['board.row.kind_units'], { margin: marginUnit, soil: soilUnit })}
              selected={each === kind}
              columns={columns}
              cell={(option) => (
                <KindCell option={option} kind={each} worst={worstKind(answer, option) === each} mockSoil={mockSoilKinds.includes(each)} mockMargin={mockMarginKinds.includes(each)} />
              )}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The first number present among these, or null when none is. */
function firstPresent(items: Measured[]): Extract<Measured, { value: number }> | null {
  for (const item of items) {
    if (item.value !== null) return item
  }
  return null
}

/**
 * The notes of the numbers of the table, said once: what every soil-loss
 * figure carries (its label of D148, its sources or the assumption mark) and
 * where the margins come from; and, when a number has no range, the reason
 * the answer gives. Shown only for the kinds of number the table holds.
 */
export function TableNotes({ answer }: { answer: PlantAnswer }) {
  const kinds = MARGINS_OF
  const soil = answer.options.flatMap((option) => kinds.map((kind) => option.soil_loss[kind]))
  const margins = answer.options.flatMap((option) => kinds.map((kind) => option.margin[kind]))
  const soilShown = soil.filter((item) => item.value !== null)
  const marginShown = firstPresent(margins)
  if (soilShown.length === 0 && marginShown === null) {
    return null
  }
  const sources = [...new Set(soilShown.flatMap((item) => item.sources))]
  const soilFirst = firstPresent(soilShown)
  return (
    <ol data-testid="board-notes" className="mt-3 space-y-1.5 text-xs text-fs-muted">
      {soilFirst !== null ? (
        <li data-testid="board-note-soil">
          <span className="font-mono font-semibold text-fs-text">{SOIL_MARK}</span>{' '}
          <span className="font-semibold text-fs-text">{strings['plant.table.soil_loss']}.</span>{' '}
          <span data-testid="board-soil-label">{strings['soil_loss.headline_label']}</span>{' '}
          {sources.length !== 0 ? (
            <span>{formatString(strings['value.source'], { source: sources.join('; ') })}. </span>
          ) : null}
          {soilShown.some((item) => item.assumption) ? (
            <span>{strings['assumption.mark']}. </span>
          ) : null}
          {soilFirst.labels.range === null && soilFirst.labels.range_missing !== null ? (
            <span data-testid="board-no-range">
              {missingPatternText(strings['board.no_range'], soilFirst.labels.range_missing)}
            </span>
          ) : null}
        </li>
      ) : null}
      {marginShown !== null ? (
        <li data-testid="board-note-margin">
          <span className="font-mono font-semibold text-fs-text">{MARGIN_MARK}</span>{' '}
          <span className="font-semibold text-fs-text">{strings['plant.table.margin']}.</span>{' '}
          <span>{formatString(strings['value.source'], { source: strings['plant.source.economics'] })}. </span>
          {marginShown.labels.range === null && marginShown.labels.range_missing !== null ? (
            <span data-testid="board-no-range">
              {missingPatternText(strings['board.no_range'], marginShown.labels.range_missing)}
            </span>
          ) : null}
        </li>
      ) : null}
    </ol>
  )
}
