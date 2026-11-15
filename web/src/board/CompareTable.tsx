import type { ReactNode } from 'react'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { barPercent, drawnSoilVerdict, stateTone, verdictTone } from '../plant/optionBars'
import { RotationTimeline, StatePill } from '../plant/PlantVisuals'
import { KINDS_OF_YEAR } from '../plant/plantData'
import type { Measured, PlantAnswer, PlantOption } from '../plant/plantData'
import { cropOrder } from '../plant/rotationStrip'
import type { RotationStrip } from '../plant/rotationStrip'
import type { RotationDefinition } from '../rotation/exampleRotation'
import { strings } from '../strings'
import { SORT_KEYS, cropName, isExampleCrop, worstKind } from './boardModel'
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

/** True when a crop of the rotation is a placeholder of the example data. */
export function hasExampleCrops(strip: RotationStrip | null): boolean {
  return strip !== null && cropOrder([strip]).some(isExampleCrop)
}

/** The selector of what the options are ordered by. */
export function SortPicker({ sort, onSort }: { sort: SortKey; onSort: (sort: SortKey) => void }) {
  return (
    <label data-testid="board-sort" className="inline-flex flex-wrap items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-widest text-fs-muted">{strings['board.sort.label']}</span>
      <select
        className="min-h-9 cursor-pointer rounded-lg border border-fs-border bg-fs-surface px-3 py-1 text-sm font-semibold"
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

function Number({ item }: { item: Measured }) {
  if (item.value === null) {
    return (
      <Missing item={item} />
    )
  }
  return (
    <span className="whitespace-nowrap tabular-nums" title={String(item.value)}>
      <span className="font-fs-heading text-xl font-extrabold">{displayNumber(item.value)}</span>{' '}
      <span className="text-[11px] text-fs-muted">{item.unit}</span>
    </span>
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
  selected = false,
  columns,
  cell,
}: {
  label: string
  /** True for the row of the kind of year looked at. */
  selected?: boolean
  columns: BoardColumn[]
  cell: (option: PlantOption) => ReactNode
}) {
  return (
    <tr data-selected={String(selected)} className="border-t border-fs-border data-[selected=true]:font-semibold">
      <th scope="row" className="px-4 py-3 text-left align-top text-xs font-semibold uppercase tracking-wide text-fs-muted">
        {label}
      </th>
      {columns.map(({ option }) => (
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
}: {
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
          <span className="font-fs-heading text-base font-bold">{displayNumber(margin.value)}</span>{' '}
          <span className="text-[11px] text-fs-muted">{margin.unit}</span>
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
          {formatString(strings['board.kind.soil'], { value: displayNumber(loss.value), unit: loss.unit })}
          {tone === 'over' ? (
            <span className="ml-1 uppercase">{strings['plant.table.over_limit']}</span>
          ) : null}
        </p>
      ) : (
        <p className="text-xs italic text-fs-muted">
          {formatString(strings['board.kind.soil_missing'], { missing: strings['plant.table.no_value'] })}
        </p>
      )}
    </div>
  )
}

/**
 * The comparison: a column per option with its position, letter, crops and
 * state; then its crops by month, its margin and its soil loss for the kind
 * of year looked at, and each kind of year.
 */
export function CompareTable({
  answer,
  columns,
  info,
  order,
  scales,
  sort,
}: {
  answer: PlantAnswer
  columns: BoardColumn[]
  /** What the columns are ordered by: only the rule of the answer gives a first place. */
  sort: SortKey
  info: (option: PlantOption) => OptionInfo
  /** The crops of all the options, for one set of colours. */
  order: readonly string[]
  scales: CompareScales
}) {
  const kind = answer.margin_of
  return (
    <div className="overflow-x-auto rounded-2xl border border-fs-border bg-fs-surface">
      <table data-testid="board-compare" className="w-full min-w-[44rem] table-fixed border-collapse">
        <colgroup>
          <col className="w-36" />
        </colgroup>
        <thead>
          <tr>
            <td />
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
                    {rotation !== null && isUserRotation(rotation.rotation_id)
                      ? rotation.label
                      : (cropsText(strip) ?? option.rotation_id)}
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
                  {hasExampleCrops(strip) ? (
                    <p data-testid="board-example-crops" className="text-[11px] font-semibold text-fs-warning">
                      {strings['board.example_crops']}
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
            columns={columns}
            cell={(option) => (
              <div>
                <Number item={option.margin[kind]} />
                <Bar testid="board-bar-margin" item={option.margin[kind]} scale={scales.margin} tone="chosen" />
              </div>
            )}
          />
          <Row
            label={formatString(strings['plant.soil_loss_of'], { kind: strings[`plant.kind.${kind}`] })}
            columns={columns}
            cell={(option) => (
              <div>
                <Number item={option.soil_loss[kind]} />
                <Bar
                  testid="board-bar-soil"
                  item={option.soil_loss[kind]}
                  scale={scales.soilLoss}
                  tone={verdictTone(drawnSoilVerdict(option, kind))}
                  limit={option.limit}
                />
                {option.limit !== null ? (
                  <p className="mt-1 text-[11px] text-fs-muted">
                    {formatString(strings['board.limit_is'], {
                      limit: displayNumber(option.limit),
                      unit: option.limit_unit,
                    })}
                  </p>
                ) : null}
              </div>
            )}
          />
          {KINDS_OF_YEAR.map((each) => (
            <Row
              key={each}
              label={strings[`plant.kind.${each}`]}
              selected={each === kind}
              columns={columns}
              cell={(option) => (
                <KindCell option={option} kind={each} worst={worstKind(answer, option) === each} />
              )}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
