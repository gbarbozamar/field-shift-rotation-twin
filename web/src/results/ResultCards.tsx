import { ValueDisplay } from '../components/ValueDisplay'
import type { MissingPart, ValueItem } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import type {
  CarbonPart,
  CarbonValue,
  IndicatorId,
  ResultsPerRotation,
  SoilLossPart,
  WaterPart,
} from './resultsData'
import { resultsExampleRotations } from './resultsData'

/**
 * The result cards (issue #141): one card per rotation of the results
 * example, after the field list of the fields screen. Every value the
 * example carries goes through the shared value display — its unit, its
 * provenance label and its source, its range or the reason it has none —
 * and every absence renders as a missing value with its reason, never zero
 * or blank.
 *
 * Each carbon value is one item of its own, labelled with its carbon model
 * and its computation (C1.5): nothing here merges or averages across models.
 * A part whose engine is not built (D12) renders through the value display's
 * missing pattern with NOT_AVAILABLE.
 *
 * The example describes its own placeholder case and field, whose ids are
 * not the ids of the example case of the identity screen; the example banner
 * is on for as long as they differ, the same honest rule the site sheet
 * applies to its examples. The name each value is displayed under is the
 * indicator identifier of the contract (soil_loss, water_deficit_exposure,
 * soil_carbon_trend) with its calendar position, rendered as data — the
 * person-approved display names of the indicators are not in the strings
 * file at the date of this unit. Decision-state wording is deliberately
 * absent: it belongs to the science reviewers (OPEN of #96).
 *
 * All user-visible wording lives in strings.ts; class lists are arrays of
 * single-word tokens joined at runtime.
 */

/** The calendar position of one monthly value: the year and C5.1's month number. */
function monthLabel(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

/**
 * True when a results document does not belong to the case the screen shows:
 * another case id, or a field the example case does not hold. The results
 * example is placeholder data that describes no field of the example case,
 * so the banner is on; when real results of the case replace it, ids match
 * and the banner goes off by itself.
 */
function describesAnotherCase(doc: ResultsPerRotation): boolean {
  return (
    doc.case_id !== exampleCase.case_id ||
    !exampleCase.fields.some((field) => field.field_id === doc.field_id)
  )
}

/**
 * One wholly missing part (D12): its absence through the value display's
 * missing pattern. The missing render names what is missing and why and
 * shows no unit; the first of the part's units travels with the item to
 * satisfy the display's item shape, and the whole list stays in the parsed
 * data. Nothing is ever written in place of the absent values.
 */
function WhollyMissingRow({
  indicator,
  units,
  missing,
}: {
  indicator: IndicatorId
  units: string[]
  missing: MissingPart
}) {
  return <ValueDisplay what={indicator} item={{ value: null, unit: units[0], missing }} />
}

/**
 * One row of a card: the label names the item — the indicator identifier
 * of the contract with its calendar position, rendered as data — beside the
 * shared value display. The label shows for a present value, which the
 * display itself names only in its missing pattern; a missing value is
 * named by that pattern already, and no label is repeated beside it.
 */
function ItemRow({
  label,
  item,
  rowTestId,
}: {
  label: string
  item: ValueItem
  rowTestId: string
}) {
  return (
    <li data-testid={rowTestId} className={['flex', 'gap-3'].join(' ')}>
      {item.value !== null && (
        <span data-testid="row-label" className={['font-mono', 'text-sm', 'text-slate-500'].join(' ')}>
          {label}
        </span>
      )}
      <ValueDisplay what={label} item={item} />
    </li>
  )
}

/** The soil-loss part: one row per agricultural year and one row per month, or its absence. */
function SoilLossRows({ part }: { part: SoilLossPart }) {
  if (part.form === 'not_built') {
    return (
      <ul className={['mt-2', 'space-y-2'].join(' ')}>
        <li data-testid="part-row">
          <WhollyMissingRow indicator={part.indicator} units={part.units} missing={part.missing} />
        </li>
      </ul>
    )
  }
  return (
    <ul className={['mt-2', 'space-y-2'].join(' ')}>
      {part.annual.map((annual) => (
        <ItemRow
          key={`a-${annual.ag_year}`}
          rowTestId="annual-row"
          label={part.indicator + ' ' + String(annual.ag_year)}
          item={annual.item}
        />
      ))}
      {part.monthly.map((monthly) => (
        <ItemRow
          key={`m-${monthLabel(monthly.year, monthly.month)}-${monthly.ag_year}`}
          rowTestId="monthly-row"
          label={part.indicator + ' ' + monthLabel(monthly.year, monthly.month)}
          item={monthly.item}
        />
      ))}
    </ul>
  )
}

/** The water-deficit-exposure part: one row per value, or its absence. */
function WaterRows({ part }: { part: WaterPart }) {
  if (part.form === 'not_built') {
    return (
      <ul className={['mt-2', 'space-y-2'].join(' ')}>
        <li data-testid="part-row">
          <WhollyMissingRow indicator={part.indicator} units={part.units} missing={part.missing} />
        </li>
      </ul>
    )
  }
  return (
    <ul className={['mt-2', 'space-y-2'].join(' ')}>
      {part.values.map((value, index) => (
        <ItemRow
          key={`w-${value.ag_year ?? index}`}
          rowTestId="water-row"
          label={
            value.ag_year === undefined
              ? part.indicator
              : part.indicator + ' ' + String(value.ag_year)
          }
          item={value.item}
        />
      ))}
    </ul>
  )
}

/** One carbon value: labelled with its model and its computation, then the shared value display. */
function CarbonItemRow({
  indicator,
  value,
}: {
  indicator: IndicatorId
  value: CarbonValue
}) {
  return (
    <li
      data-testid="carbon-item"
      className={['space-y-1', 'pt-2', 'first:pt-0'].join(' ')}
    >
      <p data-testid="carbon-model-label" className={['text-xs', 'text-slate-500'].join(' ')}>
        {formatString(strings['cards.model_label'], { model: value.carbon_model })}
      </p>
      <p
        data-testid="carbon-computation-label"
        className={['text-xs', 'text-slate-500'].join(' ')}
      >
        {formatString(strings['cards.computation_label'], { computation: value.computation })}
      </p>
      <div className={['flex', 'gap-3'].join(' ')}>
        {value.item.value !== null && (
          <span
            data-testid="row-label"
            className={['font-mono', 'text-sm', 'text-slate-500'].join(' ')}
          >
            {indicator}
          </span>
        )}
        <ValueDisplay what={indicator} item={value.item} />
      </div>
    </li>
  )
}

/** The soil-carbon-trend part: one labelled item per model and per computation (C1.5), or its absence. */
function CarbonRows({ part }: { part: CarbonPart }) {
  if (part.form === 'not_built') {
    return (
      <ul className={['mt-2', 'space-y-2'].join(' ')}>
        <li data-testid="part-row">
          <WhollyMissingRow indicator={part.indicator} units={part.units} missing={part.missing} />
        </li>
      </ul>
    )
  }
  return (
    <ul className={['mt-3', 'space-y-2'].join(' ')}>
      {part.values.map((value) => (
        <CarbonItemRow
          key={`c-${value.carbon_model}-${value.computation}`}
          indicator={part.indicator}
          value={value}
        />
      ))}
    </ul>
  )
}

/** One card: the rotation it reports, and the availability of every part of its results. */
function RotationCard({ doc }: { doc: ResultsPerRotation }) {
  return (
    <article
      data-testid="rotation-card"
      className={[
        'mt-4',
        'rounded-lg',
        'border',
        'border-slate-200',
        'bg-white',
        'px-4',
        'py-3',
      ].join(' ')}
    >
      <h4 data-testid="rotation-heading" className={['text-sm', 'font-semibold'].join(' ')}>
        {formatString(strings['cards.per_rotation'], { id: doc.rotation_id })}
      </h4>
      <h5
        data-testid="availability-heading"
        className={['mt-3', 'text-xs', 'font-semibold', 'text-slate-500'].join(' ')}
      >
        {strings['cards.availability']}
      </h5>
      <SoilLossRows part={doc.soil_loss} />
      <WaterRows part={doc.water_deficit_exposure} />
      <CarbonRows part={doc.soil_carbon_trend} />
    </article>
  )
}

/** The results section: its title, the example banner when the data is not of this case, one card per rotation. */
export default function ResultCards() {
  const showsExampleBanner = resultsExampleRotations.some(describesAnotherCase)

  return (
    <section aria-labelledby="results-title" className="mt-8">
      <h3 id="results-title" className="text-base font-semibold">
        {strings['cards.title']}
      </h3>
      {showsExampleBanner && (
        <div
          role="note"
          className={[
            'mt-3',
            'rounded-lg',
            'border',
            'border-amber-300',
            'bg-amber-50',
            'px-4',
            'py-3',
          ].join(' ')}
        >
          <p
            data-testid="results-example-banner"
            className={['text-sm', 'text-amber-900'].join(' ')}
          >
            {strings['example.banner']}
          </p>
        </div>
      )}
      <div>
        {resultsExampleRotations.map((doc, index) => (
          <RotationCard key={`${doc.rotation_id}-${index}`} doc={doc} />
        ))}
      </div>
    </section>
  )
}
