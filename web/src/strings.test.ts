import { describe, expect, it } from 'vitest'
import { readdirSync } from 'fs'
import { dirname, join, relative, resolve } from 'path'
import { fileURLToPath } from 'url'
import { readFileSync } from 'fs'
import { strings } from './strings'

/**
 * Acceptance test of the strings unit.
 *
 * Case 1 — the strings file exports exactly the keys of the wording sheet,
 * with exactly the supplied values.
 *
 * Case 2 — no file under web/src other than the strings file contains a
 * user-visible text literal: the former shell page text and the two
 * diagnostics render from the strings file instead.
 *
 * The "user-visible text literal" check is a source-level scan, not a
 * compiler check. It flags:
 * - R1  text written directly between JSX tags (>"Field Shift..."<);
 * - R1b text written in JSX right after an expression container ({x} text<);
 * - R2  a quoted string literal used as a JSX child ({'text'});
 * - R3  a literal value of a text-bearing attribute (title, alt,
 *       placeholder, aria-label, ...);
 * - R4  any phrase-like string or template literal (a letter and a space)
 *       that survives removal of import/export lines and JSX attribute
 *       values such as className.
 *
 * Technical strings (import paths, className values, event names, URLs,
 * test names) do not look like any of the above and pass. The scan is a
 * heuristic with a proof of teeth: it is asserted to flag the original
 * hardcoded shell page, kept below as a fixture.
 */

const srcDir = dirname(fileURLToPath(import.meta.url))
const stringsFilePath = resolve(srcDir, 'strings.ts')

/** The wording sheet, supplied by the interface developer. Do not change. */
const WORDING_SHEET: Record<string, string> = {
  'app.title': 'Field Shift Rotation Twin',
  'app.subtitle': 'Compares crop rotations for a field against the observed climate record',
  'example.banner': 'Example data — synthetic, not a real field',
  'disclaimer.full':
    'This is a research prototype made for a hackathon. It is not agronomic advice and it does not replace a professional soil-use plan. It is not affiliated with, nor endorsed by, NASA or any data provider.',
  'assumption.mark': 'assumption',
  'value.source': 'Source: {source}',
  'value.range': '{low} to {high} ({kind})',
  'provenance.DECLARED': 'Declared',
  'provenance.OBSERVED': 'Observed',
  'provenance.DERIVED': 'Derived',
  'provenance.SIMULATED': 'Simulated',
  'missing.pattern': '{what}: {reason phrase}',
  'missing.NOT_DECLARED': 'not declared for this case',
  'missing.SOURCE_UNAVAILABLE': 'source unavailable',
  'missing.NO_COVERAGE': 'no coverage for this place or period',
  'missing.MISSING_INPUT': 'missing input: {detail}',
  'missing.NOT_COMPUTABLE': 'not computable for this case',
  'missing.CONTROL_FAILED': 'a control failed and the value is withheld',
  'missing.NOT_AVAILABLE': 'module not built or not enabled',
  'missing.NOT_APPLICABLE': 'not applicable',
  'missing.detail_suffix': '({detail})',
  'api.MALFORMED_JSON': 'The request was not valid JSON.',
  'api.INVALID_REQUEST': 'The request is missing something it needs.',
  'api.SITE_INVALID': 'The site as declared cannot be used. Check the location.',
  'api.ROTATION_INVALID': 'The rotation as declared cannot be used. Check crops and dates.',
  'api.NOT_FOUND': 'There is nothing at this address.',
  'api.METHOD_NOT_ALLOWED': 'This address does not accept that method.',
  'api.INTERNAL_ERROR': 'The calculation failed. Nothing was invented to fill in.',
  'api.UNEXPECTED': 'Something failed on the connection.',
  'api.code.shown': 'code: {code}',
  'home.heading': 'Field Shift Rotation Twin',
  'home.intro': 'Compares crop rotations for a field against the observed climate record.',
  'home.shell': 'Placeholder shell page. Screens will be added by later units.',
  'home.route': 'Current hash route: {route}',
  'home.backend': 'Backend: {api}',
  'identity.title': 'Fields',
  'identity.case_label': 'Case',
  'identity.banner_title': 'Example data',
  'identity.banner_text':
    'This screen shows illustrative placeholder fields over a generic rural area. No real field is described.',
  'identity.selected': 'Selected',
  'identity.field_id_label': 'Identifier',
  'identity.empty_list': 'The example case has no fields.',
  'map.title': 'Fields',
  'map.select_hint': 'Select a field on the map or the list',
  'map.layer.attribution': '© OpenStreetMap contributors',
  'site.title': 'Site data',
  'site.select_hint': 'Select a field to see its site data',
  'site.climate_section': 'Climate',
  'site.soil_section': 'Soil and slope',
  'site.slope_length': 'Slope length',
  'site.slope_steepness': 'Slope steepness',
  'site.series_heading': '{quantity} ({unit})',
  'site.months_count': '{count} months',
  'ribbon.title': 'Rotation timeline',
  'ribbon.rotation_of': 'Rotation: {label}',
  'ribbon.ag_year_start': 'Agricultural year starts in month {month}',
  'ribbon.provisional': 'Provisional',
  'ribbon.repeats': 'Repeats',
  'ribbon.not_repeating': 'Does not repeat',
  'ribbon.component': 'Component {position}',
  'ribbon.crop': 'Crop',
  'ribbon.purpose': 'Purpose',
  'ribbon.sowing': 'Sowing',
  'ribbon.harvest': 'Harvest',
  'ribbon.management': 'Management',
  'ribbon.mgmt_residue': 'Residue',
  'ribbon.mgmt_grazing': 'Grazing',
  'ribbon.mgmt_termination': 'Termination',
  'clocks.title': 'Two clocks',
  'clocks.soil': 'The soil clock',
  'clocks.water': 'The water clock',
  'clocks.years_hint': 'Each column is one agricultural year',
  'clocks.example_note': 'Example data — real years arrive with the seam',
  'seam.with_real_data': 'Live data — NASA POWER through the platform route',
  // Science wording decided verbatim by D148 (issue #77) and the reason
  // approved by the interface developer (15/11/2026); decided wording.
  'soil_loss.headline_label':
    'based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)',
  'soil_loss.withdrawn_c':
    'Not shown: the computed cover factor of this release overestimates the measured loss (see the check in docs/VALIDATION.md).',
  'common.loading': 'Loading…',
  'common.error': 'Something failed. Nothing was invented to fill in.',
  'entry.title': 'Case',
  'entry.open_field': 'Open field',
  'entry.fields_count': '{n} fields',
  'cards.title': 'Results',
  'cards.per_rotation': 'Rotation {id}',
  'cards.availability': 'Availability',
  'cards.model_label': 'Model: {model}',
  'cards.computation_label': 'Computation: {computation}',
  'decision.title': 'Decision',
  'decision.pairs': 'Rotation pairs',
  'decision.pair_of': '{first} against {second}',
  'decision.state': 'State',
  'decision.counts': 'Counts',
  'decision.counts_by_point': 'By point value',
  'decision.counts_by_range': 'By range',
  'decision.better': 'Better',
  'decision.worse': 'Worse',
  'decision.equal': 'Equal',
  'decision.missing_side': 'Missing side',
  'decision.coverage': '{k} of {n} cells compared',
  'decision.years_within': 'Years within the limit: {min} to {max}, minimum at {scenario}',
  // PROPOSED (Block 4, D4 + named-years selector): measurement priority with
  // its field, agricultural-year filter, counts by year, and scenario-year
  // paired differences.
  'decision.measure_first': 'Measure first',
  'decision.measure_first_field': 'Field: {field}',
  'decision.measure_first_rank': 'Rank {rank}',
  'decision.measure_first_not_declared': 'no uncertain input is declared for this case',
  'decision.named_years': 'Agricultural year',
  'decision.named_years_all': 'All years',
  'decision.named_years_none': 'No agricultural years in this decision',
  'decision.counts_by_year': 'Counts by year',
  'decision.counts_by_year_summary': '{evaluated} evaluated, {within} within the limit',
  'decision.counts_by_year_evaluated': '{evaluated} evaluated',
  'decision.counts_by_year_within': 'Years within the limit',
  'decision.counts_by_year_not_evaluated': 'Not evaluated',
  'decision.counts_by_year_empty': 'No counts by year for this selection',
  'decision.scenario_years': 'Scenario-year differences',
  'decision.scenario_years_empty': 'No scenario-year differences for this selection',
  // PROPOSED (S-019, l2/plant-screen): the screen "What should I plant?".
  // Wording is a person's decision; the operator approves it.
  'plant.title': 'What should I plant?',
  'plant.rule':
    'The rule: the most margin per hectare and year among the rotations that do not lose more soil than the limit. Soil loss is a limit, not a cost.',
  'plant.questions': 'Four questions',
  'plant.q.price': 'What is soybean worth?',
  'plant.q.price_hint': 'A tipping price, not a forecast: the screen shows where the answer changes.',
  'plant.q.price_looked_at': 'Price looked at: {price} {unit}',
  'plant.q.price_today': 'Today: {price} {unit}',
  'plant.q.price_range': 'Range: {low} to {high} {unit}',
  'plant.q.kind': 'Which kind of year?',
  'plant.q.rain': 'And if the rain is heavier?',
  'plant.q.rain_control': 'Heavier rain stress test',
  'plant.q.rain_unavailable_detail': 'the stress test needs the service, which this page does not call',
  'plant.q.strict': 'How strict?',
  'plant.kind.average': 'average of the record',
  'plant.kind.el_nino': 'El Nino',
  'plant.kind.neutral': 'neutral',
  'plant.kind.la_nina': 'La Nina',
  'plant.strict.on_average': 'Meet the limit on average',
  'plant.strict.every_kind': 'Meet the limit in every kind of year',
  'plant.answer.heading': 'The answer at the price of today',
  // Wording of D245 (issue #77), in place of "Plant this rotation".
  'plant.answer.chosen': 'The most margin within the limit you declared; water and soil carbon are not part of this answer',
  // D250 (#77): each limit of this release the answer declares, as given.
  'plant.declared_limit': 'Limit of this release: {limit}',
  'plant.answer.none_meets': 'None of the rotations meets the soil-loss limit',
  'plant.answer.not_resolved': 'Not resolved: the data cannot pick one rotation',
  'plant.answer.why': 'Why',
  'plant.answer.tied': 'Tied: {rotations}',
  'plant.answer.missing_what': 'Answer to these questions',
  'plant.answer.missing_detail': 'no example answer holds these questions',
  'plant.value_line': '{what}: {value} {unit}',
  'plant.margin_of': 'Margin, {kind}',
  'plant.soil_loss_of': 'Soil loss, {kind}',
  'plant.limit': 'Soil-loss limit',
  'plant.by_kind': 'Margin in each kind of year',
  'plant.check.on_average': 'Limit check on average',
  'plant.check.every_kind': 'Limit check in every kind of year',
  'plant.check_line': '{check}: {verdict}',
  'plant.verdict.meets': 'meets the limit',
  'plant.verdict.does_not_meet': 'does not meet the limit',
  'plant.cost.heading': 'What meeting the limit costs',
  'plant.cost.what': 'Cost of meeting the limit',
  'plant.cost.value': 'Meeting the limit costs {value} {unit} against {against}, the rotation outside the limit with the most margin',
  'plant.cost.nothing': 'Meeting the limit costs nothing: no rotation outside the limit has more margin',
  'plant.tip.heading': 'Tipping price',
  'plant.tip.up': 'If soybean rises',
  'plant.tip.down': 'If soybean falls',
  'plant.tip.point': 'At {price} {unit} the answer becomes: {after}',
  'plant.tip.distance': '{distance} % from the price of today',
  'plant.tip.distance_what': 'Distance from the price of today',
  'plant.after.chosen': '{rotation} is chosen',
  'plant.after.none_meets': 'none of the rotations meets the limit',
  'plant.after.not_resolved': 'not resolved',
  'plant.price.today': 'This is the price of today.',
  'plant.price.same':
    'No tipping price lies between this price and the price of today: the answer is the one at the price of today. The margins shown are at the price of today.',
  'plant.price.past':
    'Past the tipping price of {price} {unit} the answer becomes: {after}. Whether it changes again further from today is not computed. The margins shown are at the price of today.',
  'plant.price.unknown_what': 'Answer at {price} {unit}',
  'plant.options.heading': 'Each option',
  'plant.state.chosen': 'Chosen: the most margin among the rotations within the limit',
  'plant.state.meets': 'Meets the soil-loss limit',
  'plant.state.does_not_meet': 'Loses more soil than the limit: left out',
  'plant.state.not_resolved': 'Not resolved: the data cannot tell whether it meets the limit',
  'plant.kinds.not_met': 'Kinds of year over the limit: {kinds}',
  'plant.kinds.not_resolved': 'Kinds of year not resolved: {kinds}',
  'plant.kinds.not_in_record': 'Kinds of year not in the record: {kinds}',
  'plant.kinds.none': 'none',
  'plant.sources.heading': 'Sources',
  'plant.source_line': '{id}: {detail}',
  'plant.source.economics':
    'margins, the cost of meeting the limit and the tipping price, computed by the economics functions from the economic facts of this answer',
  // PROPOSED (S-019 fix round 1): the mark of a value the user declares.
  'plant.declared': 'Declared by the user in the request (example data)',
  // PROPOSED (S-019 code review fixes): the attribution of a source.
  'plant.source.attribution': 'Attribution: {attribution}',
  // PROPOSED (S-020): the option rows (strip, bars, state in plain words).
  'plant.month.1': 'January',
  'plant.month.2': 'February',
  'plant.month.3': 'March',
  'plant.month.4': 'April',
  'plant.month.5': 'May',
  'plant.month.6': 'June',
  'plant.month.7': 'July',
  'plant.month.8': 'August',
  'plant.month.9': 'September',
  'plant.month.10': 'October',
  'plant.month.11': 'November',
  'plant.month.12': 'December',
  'plant.strip.what': 'Crops year by year',
  'plant.strip.no_definition_detail': 'the request holds no definition of this rotation',
  'plant.strip.year': 'Year {n}: {crops}',
  'plant.strip.year_empty': 'Year {n}: no crop declared in it',
  'plant.strip.year_label': 'Year {n}',
  'plant.strip.year_join': '; ',
  'plant.strip.crop_join': ', then ',
  'plant.strip.crop': '{crop} sown {sowing}, harvested {harvest}',
  'plant.strip.crop_kept': '{crop} kept from its sowing in {sowing}, harvested {harvest}',
  'plant.strip.crop_harvest_missing': '{crop} sown {sowing}, {harvest}',
  'plant.strip.harvest': 'harvest',
  'plant.strip.month_of_year': '{month} of year {n}',
  'plant.strip.purpose': 'purpose: {purpose}',
  'plant.strip.unplaced': 'Sowing date of {crop}, placed in no year',
  'plant.bar.limit_line': 'Limit line',
  'plant.state.every_kind_meets': 'Meets the limit in every kind of year in the record',
  'plant.state.on_average_only': 'Meets the limit on average, but not in: {kinds}',
  'plant.state.out_by': 'Out, by this check: {check}',
  'plant.state.why': 'Why it is not resolved',
  // PROPOSED (S-020 fix round 1): row verdicts, strip text and marks, bar marks.
  'plant.verdict.not_resolved': 'not resolved',
  'plant.strip.crop_alt': '{crop} ({purpose})',
  'plant.strip.request_invalid_detail': 'the rotations of the request could not be read',
  'plant.strip.dates_provenance': 'Dates of the strip: {provenance}',
  'plant.bar.margin_loss': 'Below zero: a loss',
  'plant.bar.soil_against': '{what} against the limit',
  'plant.bar.not_in_record': 'this kind of year is not in the record, so there is no verdict',
  // PROPOSED (S-021, l2/plant-screen-service): "Ask the service" on the screen
  // "What should I plant?": where the answer comes from, the pending line, the
  // error panel (one text per error code of api/errors.py, plus UNEXPECTED),
  // the factor heavier rain sends, and the rain-stress part of the answer.
  // D251 (#77): without a configured service the screen says so and shows
  // no example values in place of an answer.
  'plant.service.not_available': 'The service is not available: no answer can be shown.',
  'plant.service.origin_service': 'Answer from the service at {api}',
  'plant.service.ask': 'Ask the service',
  'plant.service.back': 'Back to the questions',
  // D251 (#77), read strictly: no sample answer values are shown, with or
  // without the service. The questions start from the example request.
  'plant.service.not_asked': 'No answer yet: ask the service for the answer to these questions.',
  'plant.q.example_inputs':
    'These questions start from the example request (PLACEHOLDER inputs, declared by the user): change them to your own before asking the service.',
  'plant.service.pending': 'Asking the service for the answer to these questions',
  'plant.service.error_heading': 'The service did not answer',
  'plant.service.error.MALFORMED_JSON': 'The service could not read the request as JSON.',
  'plant.service.error.INVALID_REQUEST': 'The service refused the request: a part of it breaks the plant request contract.',
  'plant.service.error.SITE_INVALID': 'The service refused the site of the request.',
  'plant.service.error.ROTATION_INVALID': 'The service refused a rotation of the request.',
  'plant.service.error.INTERNAL_ERROR': 'The service failed while computing the answer. Nothing was invented to fill in.',
  'plant.service.error.NOT_FOUND': 'The service has no plant route at this address.',
  'plant.service.error.METHOD_NOT_ALLOWED': 'The plant route of the service does not accept this method.',
  'plant.service.error.UNEXPECTED': 'The connection to the service failed, or its answer could not be read as an answer to these questions.',
  'plant.service.rain_factor': 'Factor sent: {value} {unit} ({provenance})',
  'plant.service.rain_no_factor_detail': 'the example request declares no rain-stress factor',
  'plant.service.rain_what': 'Heavier rain, {label}',
  'plant.service.rain_applied': 'Heavier rain, {label}: {detail}',
  'plant.service.rain_not_applied': 'Heavier rain, {label}, not applied: {detail}',
  // PROPOSED (fix round 1 of S-021): heavier rain with a backend in example
  // mode, and a request that cannot be read.
  'plant.service.rain_next_answer': 'Applies to the next answer from the service.',
  'plant.service.rain_request_invalid_detail': 'the rain-stress factor of the example request could not be read',
  // Wording addendum Block 6, 15 Nov 2026 (l3/stage-rail, issue #435): the
  // stage rail of the fields screen — the label of the whole rail, the six
  // stages in their order, the state a stage is in, and the reason each
  // stage would show while it waits.
  'rail.label': 'The case in six stages',
  'rail.stage.case': 'Open the case',
  'rail.stage.field': 'Read the field',
  'rail.stage.rotations': 'Set the rotations',
  'rail.stage.compare': 'Compare the runs',
  'rail.stage.decision': 'Read the decision',
  'rail.stage.handoff': 'Take the case with you',
  'rail.state.done': 'done',
  'rail.state.current': 'you are here',
  'rail.state.waiting': 'waiting',
  'rail.waiting.case': 'open a case first',
  'rail.waiting.field': 'no field chosen yet',
  'rail.waiting.rotations': 'the field is not read yet',
  'rail.waiting.compare': 'no run has answered yet',
  'rail.waiting.decision': 'nothing has been compared yet',
  'rail.waiting.handoff': 'no decision to hand over yet',
  // PROPOSED (l3/plant-redesign, 15 Nov 2026): the visual layer of the screen
  // "What should I plant?": the short state label of an option, the table of
  // an option by kind of year, the labels of its bars, the notice of the
  // sources an answer lacks, and the disclosure that holds the detail lines.
  // Wording is a person's decision; the operator approves it.
  'plant.pill.chosen': 'Chosen',
  'plant.pill.meets': 'Within the limit',
  'plant.pill.does_not_meet': 'Over the limit',
  'plant.pill.not_resolved': 'Not resolved',
  'plant.table.heading': 'By kind of year',
  'plant.table.margin': 'Margin',
  'plant.table.soil_loss': 'Soil loss',
  'plant.table.row': '{what}, {unit}',
  'plant.table.no_value': 'no value',
  'plant.table.over_limit': 'over the limit',
  'plant.notice.sources': 'Not available for this answer',
  'plant.details': 'Details and sources',
  'plant.legend': 'Crops',
  // PROPOSED (l3/board, 15 Nov 2026): the rotation board at #/board: its
  // title, the short labels of the controls, the state of a field, the
  // banner of the answer, the soil loss of a kind of year, the price track
  // and the link to the screen with every detail line. Wording is a person's
  // decision; the operator approves it.
  'nav.label': 'Sections',
  'nav.case': 'Case',
  'nav.fields': 'Fields',
  'nav.board': 'Plan a field',
  'nav.report': 'Full report',
  'board.title': 'Plan this field',
  'board.step.field': 'Field',
  'board.step.candidates': 'Candidate rotations',
  'board.step.scenario': 'Scenario',
  'board.step.holds': 'How far the answer holds',
  'board.step.keep': 'Keep the plan',
  'board.map.show': 'Show the map',
  'board.map.hide': 'Hide the map',
  'board.limit.yours': 'Your soil-loss limit',
  'board.rotations': 'Rotations',
  'board.field.ready': 'Rotations declared',
  'board.hud.year': 'Kind of year',
  'board.hud.rule': 'Limit rule',
  'board.hud.rain': 'Rain erosivity',
  'board.kind.average': 'Average',
  'board.rule.on_average': 'On average',
  'board.rule.every_kind': 'Every kind of year',
  'board.rule.on_average.limit': 'Record mean ≤ {limit} {unit}',
  'board.rule.every_kind.limit': 'Mean of each kind ≤ {limit} {unit}',
  'board.kind.years': '{kind} · {n} yr',
  'board.rain.recorded': 'As recorded',
  'board.rain.factor': 'Stress test × {factor}',
  'board.limit_is': 'your limit {limit} {unit}',
  'board.cost.none': 'No cost',
  'board.kind.soil': 'soil {value}',
  'board.kind.soil_missing': 'soil: {missing}',
  'board.price.title': 'Soybean price',
  'board.price.holds_to': 'same answer all the way to {price} {unit}',
  'board.price.unknown': 'not computed',
  'board.price.same': 'Same answer as at the price of today.',
  'board.price.past': 'Past a tipping price: {after}. Further changes are not computed.',
  'board.report': 'Open the full report',
  'board.compare.title': 'Compare the options',
  'board.option': 'Option {letter}',
  'board.cycle': '{n}-year cycle',
  'board.crops_join': ' → ',
  'board.example_crops': 'example crops',
  'board.updating': 'Updating the answer',
  'board.same_for_all': 'Same for every option',
  'unit.t ha-1 yr-1': 't/ha/yr',
  'unit.USD ha-1 yr-1': 'USD/ha/yr',
  'unit.USD t-1': 'USD/t',
  'unit.USD ha-1': 'USD/ha',
  'unit.t ha-1': 't/ha',
  'board.no_range': 'No range',
  'board.row.crops': 'Crops by month',
  'board.row.kind_units': 'margin {margin} · soil {soil}',
  'board.sort.label': 'Rank by',
  'board.sort.rule': 'Recommended: most margin within your limit',
  'board.sort.margin': 'Most profitable (ignores the limit)',
  'board.sort.soil': 'Safest for the soil (least soil loss)',
  'board.sort.worst': 'Most resilient (best margin in its worst kind of year)',
  'board.sort.kinds_over': 'Fewest kinds of year over your limit',
  'board.sort.yours': 'As entered',
  'board.sort.none': 'Not ranked: no option has this value.',
  'board.sort.some': '{n} not ranked: the value is missing.',
  'board.sort.none_rule': 'Not ranked: the answer chose no rotation.',
  'board.tied': 'tied',
  'board.worst_mark': 'worst year',
  'board.option_title': '{letter} · {title}',
  'board.cost.against': 'less margin than {rotation}, which is over your limit',
  'board.record.title': 'The record, year by year',
  'board.record.span': 'Agricultural years {first} to {last} · {n} years',
  'board.record.count': '{kind}: {n} of {total} years',
  'board.record.count_missing': '{kind}: years not classified',
  'board.record.note': 'A past record, not a forecast.',
  'board.limits.heading': 'Limits of this answer',
  'board.changed.title': 'What changed',
  'board.changed.none': 'Nothing: the same answer and the same states as before.',
  'board.changed.answer': 'The answer: {before} → {after}',
  'board.changed.state': '{rotation}: {before} → {after}',
  'board.builder.open': 'Edit or add rotations',
  'board.builder.close': 'Close the editor',
  'board.builder.count': '{n} of {max} rotations.',
  'board.builder.note': 'Build each rotation year by year: a winter and a summer crop for every year, as many years as the cycle takes. Each crop comes with dates you can change. A crop without prices yet (wheat, maize) asks for yours below before it can be compared.',
  'board.builder.name': 'Name',
  'board.builder.sowing': 'Sown',
  'board.builder.harvest': 'Harvested',
  'board.builder.duplicate': 'Duplicate',
  'board.builder.remove': 'Remove',
  'board.builder.copy_name': '{name} (copy)',
  'board.builder.compare': 'Compare these rotations',
  'board.builder.reset': 'Back to the example rotations',
  'board.builder.changed': 'Edits not compared yet',
  'board.builder.no_changes': 'No changes to compare',
  'board.builder.problem.harvest_before_sowing': 'Option {letter}: {crop} is harvested before it is sown.',
  'board.builder.problem.too_few': 'A comparison needs at least {min} rotations.',
  'board.builder.problem.too_many': 'A comparison takes at most {max} rotations.',
  'board.builder.problem.no_soybean': 'At least one rotation must sow the soybean crop: the tipping price is its price.',
  'board.builder.problem.no_crop': 'Option {letter} has no crop.',
  'board.builder.problem.no_name': 'Option {letter} has no name.',
  // PROPOSED (l3/printable-field-sheet): printable field sheet at #/print.
  'print.open_link': 'Printable field sheet',
  'print.title': 'Printable field sheet',
  'print.action': 'Print sheet',
  'print.back_to_fields': 'Back to fields',
  'print.select_hint': 'Select a field on the fields screen before printing its sheet.',
  'print.field_section': 'Field',
  'print.field_name_label': 'Field name',
  'print.case_id_label': 'Case identifier',
  'print.geometry_section': 'Geometry and location',
  'print.geometry': 'Field geometry',
  'print.geometry_type': 'Geometry type',
  'print.geometry_vertices': '{count} vertices in exterior ring',
  'print.geometry_center': 'Bounding-box centre (decimal degrees)',
  'print.geometry_bounds': 'Bounding box (south, west to north, east)',
  'print.site_section': 'Site notes',
  'print.site_example_scope':
    'Site data is example data for {field_id}, not a measurement of {selected_field_id}.',
  'print.rotations_section': 'Declared rotations',
  'print.rotations': 'Declared rotations',
  'print.rotation_id_label': 'Rotation identifier',
  // Mixed answers (l3/original-mock, PROPOSED). Wording is a person's decision.
  'mock.badge': 'Mock',
  'mock.panel.title': 'Mixed answer: backend values and mock example values',
  'mock.panel.real': 'From the backend: every number without a MOCK mark, the prices and your declared limit.',
  'mock.part.whole': 'The whole answer is mock example data: the backend has no plant answer yet.',
  'mock.part.soil': 'Soil loss of every option: mock example data, because the backend has no climate record to compute it.',
  'mock.part.record': 'Kinds of year of the record: mock example data.',
  'mock.part.margin': 'The margin averaged over the record: mock, because it weights the backend\'s margins by the mock kinds of year.',
  'mock.part.verdicts': 'The limit verdicts, the answer, its cost and the tipping price: mock, because they follow from the mock soil loss.',
  'mock.refused.incoherent': 'Mock not applied: your rotations or numbers, or the values the backend computed, differ from the example answer, so mixing them would put numbers that do not belong together on one screen.',
  'mock.refused.no_example': 'Mock not applied: there is no example answer for these questions, so the missing values stay missing.',
  'mock.panel.switch': 'Mock fill is on (VITE_MOCK_FILL=on). Switch it off to see only what the backend computes.',
  // The user's own numbers on the board (l3/original-mock, PROPOSED).
  'cards.live': 'From the backend: the result of the run above, for this field.',
  'cards.live_none': 'The run above answered no result for this field (its reason is shown above), so no card is shown and the example stays hidden.',
  'cards.live_unreadable': 'The backend answered a result this screen cannot read; nothing is shown in its place.',
  'board.builder.season.winter': 'Winter crop (sown Mar to Jun)',
  'board.builder.season.summer': 'Summer crop (sown Jul to Feb)',
  'board.builder.year': 'Year {n} ({year})',
  'board.builder.slot_label': 'Option {letter}, year {n}, {season}',
  'board.builder.slot.empty': 'Nothing sown',
  'board.builder.slot.continues': '{crop} continues',
  'board.builder.add_year': 'Add a year',
  'board.builder.facts_blocked': 'A number below is missing or wrong (a new crop needs your price, cost and yields): type it to compare.',
  'board.builder.remove_year': 'Remove the last year',
  'board.builder.dates': 'Dates of each crop',
  'board.builder.problem.overlap': 'Option {letter}: {crop} is sown before {after} is harvested. Change a date or a crop.',
  'field.area': '{ha} ha, measured on the outline',
  'board.field.point': 'Climate point {lat}, {lon} (centre of the outline)',
  'board.rain.your_factor': 'Your rain factor',
  'board.rain.declared_note': 'Your declaration: the record does not yet say how often rain this erosive happens.',
  'board.rain.invalid': 'Type a number above zero; the factor sent stays the last valid one.',
  'board.facts.title': 'Your prices, costs and limit',
  'board.facts.extra_note': 'A crop of your rotations with no numbers yet: type yours to compare it.',
  'board.facts.note': 'Your own numbers, sent exactly as you type them (declared by you). Nothing changes until you compare.',
  'board.facts.soybean': 'Soybean',
  'board.facts.price': 'Price',
  'board.facts.cost': 'Cost',
  'board.facts.yield': 'Yield, {kind}',
  'board.facts.cover': 'Cover crop',
  'board.facts.pasture': 'Pasture',
  'board.facts.margin': 'Margin, {kind}',
  'board.facts.limit': 'Soil-loss limit',
  'board.facts.compare': 'Compare with these numbers',
  'board.facts.reset': 'Back to the example numbers',
  'board.facts.changed': 'Changed, not compared yet: {n}',
  'board.facts.no_changes': 'The comparison shown uses these numbers',
  'board.facts.problem.not_a_number': '{field}: type a number',
  'board.facts.problem.negative': '{field}: cannot be below zero',
  'board.facts.problem.not_positive': '{field}: must be above zero',
  // PROPOSED (W4-08, l3/saved-case-offline-view): offline saved-case viewer (#/saved).
  'saved.open_case': 'Open saved case',
  'saved.title': 'Saved case',
  'saved.back_entry': 'Back to case',
  'saved.case_id': 'Case identifier: {id}',
  'saved.field_id': 'Field identifier: {id}',
  'saved.saved_on': 'Saved on (UTC): {timestamp}',
  'saved.load_file': 'Open a saved case file (.json)',
  'saved.source_bundled': 'Showing bundled saved case',
  'saved.source_file': 'Showing file: {name}',
  'saved.reset_bundled': 'Show bundled saved case',
  'saved.error_invalid_json': 'The selected file is not valid JSON. Nothing was invented to fill in.',
  'saved.error_invalid_case': 'The selected file is not a valid saved case document. Nothing was invented to fill in.',
  'saved.field_identity_heading': 'Field identity',
  'saved.run_field_badge': 'Run field',
  'saved.results_heading': 'Results table',
  'saved.results_rows_count': '{n} rows',
  'saved.results_availability': '{present} present, {missing} missing',
  'saved.results_rotations': 'Rotations: {rotations}',
  'saved.results_scenarios': 'Scenarios: {scenarios}',
  'saved.carbon_heading': 'Carbon balances',
  'saved.carbon_empty': 'No carbon balance items in this saved case.',
  'saved.carbon_variant': 'Variant: {variant}',
  'saved.carbon_item_label': '{rotation} · {model} ({variant})',
  'saved.carbon_horizon': 'Horizon: {start} to {end}',
  'saved.carbon_depth': 'Soil depth',
  'saved.carbon_trend_heading': 'Soil carbon trend',
}

/** Source of the shell page as it was before the strings unit. */
const HARDCODED_APP_TSX = `
import { useHashRoute } from './lib/useHashRoute'
import { API_URL } from './lib/api'

export default function App() {
  const route = useHashRoute()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 px-6 py-4">
        <h1 className="text-xl font-semibold">Field Shift Rotation Twin</h1>
        <p className="text-sm text-slate-500">Web interface — skeleton shell</p>
      </header>
      <main className="px-6 py-8">
        <p>Placeholder shell page. Screens will be added by later units.</p>
        <p className="mt-2 text-sm text-slate-500">Current hash route: {route}</p>
        <p className="text-sm text-slate-500">Backend: {API_URL}</p>
      </main>
    </div>
  )
}
`

function listSourceFiles(dir: string): string[] {
  const found: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) found.push(...listSourceFiles(full))
    else if (/\.(ts|tsx)$/.test(entry.name)) found.push(full)
  }
  return found
}

function isScannable(filePath: string): boolean {
  if (resolve(filePath) === stringsFilePath) return false
  return !/\.test\.(ts|tsx)$/.test(filePath)
}

function stripComments(src: string): string {
  const withoutBlocks = src.replace(/\/\*[\s\S]*?\*\//g, ' ')
  return withoutBlocks
    .split('\n')
    .map((line) => line.replace(/(^|\s)\/\/.*$/, '$1'))
    .join('\n')
}

function dropModuleLines(src: string): string {
  return src
    .split('\n')
    .filter((line) => !/^\s*(import|export)\b/.test(line))
    .join('\n')
}

function dropJsxAttributeValues(src: string): string {
  // JSX attributes are written without spaces around "=", unlike assignments.
  return src.replace(/[A-Za-z_$][-\w]*(?::[-\w]+)*=(?:"[^"]*"|'[^']*')/g, '')
}

/** A text run counts as visible wording if it reads like text, not code. */
function looksLikeVisibleText(run: string): boolean {
  const text = run.trim()
  if (!/[A-Za-z]/.test(text)) return false
  if (/[(){};<>=&|!]/.test(text)) return false
  if (text.startsWith('/') || text.endsWith('/')) return false
  return true
}

interface Violation {
  rule: string
  text: string
}

function visibleTextViolations(source: string, isTsx: boolean): Violation[] {
  const violations: Violation[] = []
  const src = stripComments(source)

  if (isTsx) {
    // R1: text written directly after a JSX tag (not =>, >=, !>, ->).
    for (const match of src.matchAll(/(?<![=!-])>([^<>{}]*[A-Za-z][^<>{}]*)/g)) {
      if (looksLikeVisibleText(match[1])) violations.push({ rule: 'R1 jsx text', text: match[1].trim() })
    }
    // R1b: text written in JSX right after an expression container.
    for (const match of src.matchAll(/\}([^<>{}]*[A-Za-z][^<>{}]*)(?=<)/g)) {
      if (looksLikeVisibleText(match[1])) violations.push({ rule: 'R1b jsx text after expression', text: match[1].trim() })
    }
    // R2: a quoted string literal rendered as a JSX child.
    for (const match of src.matchAll(/>\s*\{\s*(['"])([A-Za-z][^'"\n]*)\1\s*\}\s*</g)) {
      violations.push({ rule: 'R2 jsx child literal', text: match[2].trim() })
    }
  }

  // R3: literal values of text-bearing attributes.
  const textBearing =
    /\b(title|alt|placeholder|summary|aria-label|aria-description|aria-placeholder|aria-roledescription|aria-valuetext)\s*=\s*(['"])([^'"\n]*)\2/g
  for (const match of src.matchAll(textBearing)) {
    if (/[A-Za-z]/.test(match[3])) violations.push({ rule: 'R3 text attribute', text: match[3].trim() })
  }

  // R4: phrase-like literals anywhere else in the file.
  const prepared = dropJsxAttributeValues(dropModuleLines(src))
  const literal = /'([^'\n]*)'|"([^"\n]*)"|`([^`]*)`/g
  for (const match of prepared.matchAll(literal)) {
    const content = (match[1] ?? match[2] ?? match[3] ?? '').replace(/\$\{[^}]*\}/g, '')
    if (/[A-Za-z]/.test(content) && /\s/.test(content)) {
      violations.push({ rule: 'R4 phrase literal', text: content.trim() })
    }
  }

  return violations
}

function scanSrcTree(): string[] {
  const problems: string[] = []
  for (const filePath of listSourceFiles(srcDir)) {
    if (!isScannable(filePath)) continue
    const isTsx = filePath.endsWith('.tsx')
    const violations = visibleTextViolations(readFileSync(filePath, 'utf8'), isTsx)
    for (const v of violations) {
      problems.push(`${relative(srcDir, filePath)} [${v.rule}]: ${JSON.stringify(v.text)}`)
    }
  }
  return problems
}

describe('strings file', () => {
  it('exports exactly the keys of the wording sheet, with exactly these values', () => {
    const actualKeys = Object.keys(strings).sort()
    const expectedKeys = Object.keys(WORDING_SHEET).sort()
    expect(actualKeys, 'the strings file must export exactly the wording sheet keys').toEqual(expectedKeys)
    expect({ ...strings }, 'every value must be the supplied wording, unchanged').toEqual(WORDING_SHEET)
  })
})

describe('no user-visible text literal outside the strings file', () => {
  it('no file under web/src other than the strings file carries user-visible text', () => {
    const problems = scanSrcTree()
    expect(problems, 'user-visible text must live in strings.ts only:\n' + problems.join('\n')).toEqual([])
  })

  it('the shell page renders its text and its diagnostics from the strings file', () => {
    const app = readFileSync(resolve(srcDir, 'App.tsx'), 'utf8')
    expect(app).toContain("from './strings'")
    for (const key of ['app.title', 'app.subtitle', 'home.shell', 'home.route', 'home.backend']) {
      expect(app, `App.tsx must render strings['${key}']`).toContain(`strings['${key}']`)
    }
    for (const gone of [
      'Field Shift Rotation Twin</',
      'Web interface — skeleton shell',
      'Placeholder shell page',
      'Current hash route: {',
      'Backend: {',
    ]) {
      expect(app, `the old hardcoded text must be gone: ${gone}`).not.toContain(gone)
    }
  })

  it('the check has teeth: it flags the pre-refactor hardcoded shell page', () => {
    const violations = visibleTextViolations(HARDCODED_APP_TSX, true)
    const texts = violations.map((v) => v.text)
    expect(texts).toContain('Field Shift Rotation Twin')
    expect(texts).toContain('Web interface — skeleton shell')
    expect(texts).toContain('Placeholder shell page. Screens will be added by later units.')
    expect(texts.some((t) => t.startsWith('Current hash route')), 'the route diagnostic must be flagged').toBe(true)
    expect(texts.some((t) => t.startsWith('Backend')), 'the backend diagnostic must be flagged').toBe(true)
  })

  it('the check has teeth: it flags literals rendered in the other common positions', () => {
    const jsxChild = visibleTextViolations("<p>{'Loading screen'}</p>", true)
    expect(jsxChild.map((v) => v.text)).toContain('Loading screen')

    const attribute = visibleTextViolations('<input placeholder="Enter the field name" />', true)
    expect(attribute.map((v) => v.text)).toContain('Enter the field name')

    const assigned = visibleTextViolations("const message = 'Something failed on the way'", false)
    expect(assigned.map((v) => v.text)).toContain('Something failed on the way')
  })
})
