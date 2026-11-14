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
 * - missing.*    missing-value pattern and the reason codes of C3.2
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
  'ribbon.repeats': 'Repeats',
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
} as const

/**
 * Placeholder names of the templates above that a caller fills through an
 * object key. Defined once here, beside the template that carries them, so
 * that no other file has to quote interface wording to fill a placeholder.
 * They are tokens of the supplied wording, not wording of their own.
 */
export const REASON_PHRASE_PLACEHOLDER = 'reason phrase'

export type StringKey = keyof typeof strings
