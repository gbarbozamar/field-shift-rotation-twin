import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import { formatString } from '../lib/format'
import { fieldAreaHa } from '../map/geometry'
import { MockBadge } from '../mockfill/MockPanel'
import { strings } from '../strings'
import { cropName, unitText } from './boardModel'
import { FACT_KINDS } from './factsDraft'
import { FACT_UNITS, planFieldId, siteOf, usePlan } from './planStore'
import type { Plan } from './planStore'

/**
 * The user's plan as it stands (PROPOSED, l3/original-mock), for the print
 * sheet: the field, the questions, the rotations compared with their crops
 * by year, the user's numbers, and the last answer the board showed for this
 * field. Everything is read from the plan store; nothing is computed. An
 * answer for another field, or none yet, says so.
 */

function sownYear(date: string | null): string {
  return date === null ? strings['plant.table.no_value'] : date.slice(0, 4)
}

export function PlanSummaryView({ plan, fieldId }: { plan: Plan; fieldId: string }) {
  const field = exampleCase.fields.find((each) => each.field_id === fieldId) ?? null
  const site = siteOf(fieldId)
  const facts = plan.factsSent
  const last = plan.lastAnswer !== null && plan.lastAnswer.fieldId === fieldId ? plan.lastAnswer : null
  const kind = plan.state.marginOf
  const nameOf = (rotationId: string) => plan.sent.find((r) => r.rotation_id === rotationId)?.label ?? rotationId
  return (
    <section data-testid="plan-summary" aria-labelledby="plan-summary-title" className="print-avoid-break mt-6 space-y-4">
      <h3 id="plan-summary-title" className="text-base font-semibold">
        {strings['plan.title']}
      </h3>
      {field !== null && (
        <p className="text-sm">
          <strong>{field.name}</strong>{' '}
          {formatString(strings['field.area'], { ha: fieldAreaHa(field).toFixed(1) })}
          {site !== null && <> · {formatString(strings['board.field.point'], { lat: site.latitude.toFixed(4), lon: site.longitude.toFixed(4) })}</>}
        </p>
      )}
      <div>
        <h4 className="text-sm font-semibold">{strings['plan.answer']}</h4>
        {last === null ? (
          <p data-testid="plan-no-answer" className="text-sm text-fs-muted">{strings['plan.no_answer']}</p>
        ) : (
          <div data-testid="plan-answer" className="text-sm">
            <p className="font-bold">
              {last.answer.chosen !== null ? nameOf(last.answer.chosen) : strings[`plant.answer.${last.answer.answer}`]}
              {last.mocked && <MockBadge />}
            </p>
            {last.answer.missing !== null && <p className="text-fs-muted">{missingPatternText(strings['plan.answer'], last.answer.missing)}</p>}
            <table className="mt-2 w-full text-left text-xs">
              <thead>
                <tr className="text-fs-muted">
                  <th className="py-1">{strings['plan.rotation']}</th>
                  <th>{formatString(strings['plant.margin_of'], { kind: strings[`plant.kind.${kind}`] })}</th>
                  <th>{formatString(strings['plant.soil_loss_of'], { kind: strings[`plant.kind.${kind}`] })}</th>
                  <th>{strings['plan.state']}</th>
                </tr>
              </thead>
              <tbody>
                {last.answer.options.map((option) => (
                  <tr key={option.rotation_id} className="border-t border-fs-faint align-top">
                    <td className="py-1 font-semibold">{nameOf(option.rotation_id)}</td>
                    <td className="tabular-nums">
                      {option.margin[kind].value !== null
                        ? `${displayNumber(option.margin[kind].value)} ${unitText(option.margin[kind].unit)}`
                        : strings['plant.table.no_value']}
                    </td>
                    <td className="tabular-nums">
                      {option.soil_loss[kind].value !== null
                        ? `${displayNumber(option.soil_loss[kind].value)} ${unitText(option.soil_loss[kind].unit)}`
                        : strings['plant.table.no_value']}
                    </td>
                    <td>{strings[`plant.state.${option.state}`]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div>
        <h4 className="text-sm font-semibold">{strings['plan.rotations']}</h4>
        <ul className="text-sm">
          {plan.sent.map((rotation) => (
            <li key={rotation.rotation_id}>
              <strong>{rotation.label}</strong>:{' '}
              {rotation.components.map((c) => `${cropName(c.crop_id)} (${sownYear(c.sowing.date)})`).join(strings['board.crops_join'])}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4 className="text-sm font-semibold">{strings['plan.numbers']}</h4>
        <ul data-testid="plan-numbers" className="text-sm tabular-nums">
          <li>{strings['board.facts.soybean']}: {strings['board.facts.price']} {facts.price} {unitText(FACT_UNITS.price)}, {strings['board.facts.cost']} {facts.cost} {unitText(FACT_UNITS.cost)}, {FACT_KINDS.map((k) => `${strings[`plant.kind.${k}`]} ${facts.yields[k]}`).join(', ')} {unitText(FACT_UNITS.yield)}</li>
          <li>{strings['board.facts.cover']}: {strings['board.facts.cost']} {facts.coverCost} {unitText(FACT_UNITS.cost)}</li>
          <li>{strings['board.facts.pasture']}: {FACT_KINDS.map((k) => `${strings[`plant.kind.${k}`]} ${facts.pasture[k]}`).join(', ')} {unitText(FACT_UNITS.margin)}</li>
          {Object.entries(facts.extra).map(([id, crop]) => (
            <li key={id}>
              {cropName(id)}:{' '}
              {crop.kind === 'grain' ? (
                <>
                  {strings['board.facts.price']} {crop.price} {unitText(FACT_UNITS.price)}, {strings['board.facts.cost']} {crop.cost} {unitText(FACT_UNITS.cost)}, {FACT_KINDS.map((k) => `${strings[`plant.kind.${k}`]} ${crop.yields[k]}`).join(', ')} {unitText(FACT_UNITS.yield)}
                </>
              ) : (
                <>
                  {FACT_KINDS.map((k) => `${strings[`plant.kind.${k}`]} ${crop.margins[k]}`).join(', ')} {unitText(FACT_UNITS.margin)}
                </>
              )}
            </li>
          ))}
          <li>{strings['board.facts.limit']}: {facts.limit} {unitText(FACT_UNITS.limit)}</li>
          <li>{formatString(strings['board.facts.range_line'], { low: facts.priceLow, high: facts.priceHigh, unit: unitText(FACT_UNITS.price) })}</li>
          {facts.rain !== null && plan.state.rain && <li>{formatString(strings['board.rain.factor'], { factor: facts.rain })}</li>}
        </ul>
        <p className="mt-1 text-xs text-fs-muted">{strings['plan.declared_note']}</p>
      </div>
    </section>
  )
}

export default function PlanSummary({ selectedFieldId }: { selectedFieldId: string | null }) {
  const plan = usePlan()
  return <PlanSummaryView plan={plan} fieldId={planFieldId(selectedFieldId)} />
}
