/**
 * All user-visible English strings of the interface.
 *
 * Single source of wording: every text a person can read on screen lives in
 * this file, and no component holds a text literal of its own. Components
 * reference a string by its key and render `strings[key]`.
 *
 * Keys are flat and dotted by area:
 * - app.*        identity of the application
 * - example.*    banners about the example dataset
 * - disclaimer.* the research-prototype disclaimer
 * - assumption   the "assumption" mark required by the conventions (C4.5)
 * - value.*      wording of the value display (source line, range line)
 * - provenance.* the four labels of the conventions (C4.1)
 * - missing.*    missing-value pattern, the reason codes of C3.2 and the
 *                parenthesised detail suffix that follows any reason phrase
 *                whose code does not name the detail itself
 * - api.*        messages for the error codes defined by api/errors.py,
 *                plus api.code.shown for the raw code
 * - home.*       the shell page (heading, intro, placeholder, diagnostics)
 * - common.*     shared loading and error wording
 * - entry.*      the entry screen (case title, fields count, open action)
 * - identity.*   the fields screen (title, banner, list wording)
 * - map.*        the map screen (title, select hint, base-layer attribution)
 * - site.*       the site sheet of the selected field (climate monthly series,
 *                soil and slope), wording addendum Block 3
 * - ribbon.*     the rotation timeline of the selected field
 * - clocks.*     the two clocks of a rotation of the results example (soil
 *                clock, water clock, year columns), Block 2 addendum
 * - cards.*      the results cards (title, rotation heading, availability
 *                heading, carbon model and computation labels)
 * - decision.*   the decision section of the decision output example (title,
 *                rotation pairs, pair state, the two counts apart, coverage
 *                and the years-within summary), Block 5 addendum
 * - seam.*       the platform-route seam (live-data label), Block 4 addendum
 * - soil_loss.*  the D148 display rules of the soil-loss values of a run: the
 *                science label beside the declared-C headline figure, the
 *                not-shown reason of a withdrawn computed-C value
 *
 * Values are supplied wording; they are not to be changed here.
 * Placeholders in braces ({source}, {route}, {reason phrase}, ...) are filled
 * by the pure helper in lib/format.ts. A placeholder with no value stays
 * visible as-is; nothing is ever invented to fill it.
 */
export const strings = {
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
  // Science wording decided verbatim by D148 (issue #77); the interface
  // renders it, it does not edit it.
  'soil_loss.headline_label':
    'based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)',
  // Approved by the interface developer, 15/11/2026.
  'soil_loss.withdrawn_c':
    'Not shown: the computed cover factor of this release overestimates the measured loss (see the check in docs/VALIDATION.md).',
  // PROPOSED (S-019, l2/plant-screen): the screen "What should I plant?".
  // Wording is a person's decision; the operator approves it. No kind of
  // year is called "dry": which kind is dry is OPEN.
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
  'plant.answer.chosen': 'Plant this rotation',
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
} as const

/**
 * Placeholder names of the templates above that a caller fills through an
 * object key. Defined once here, beside the template that carries them, so
 * that no other file has to quote interface wording to fill a placeholder.
 * They are tokens of the supplied wording, not wording of their own.
 */
export const REASON_PHRASE_PLACEHOLDER = 'reason phrase'

export type StringKey = keyof typeof strings
