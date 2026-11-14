/**
 * User-visible text of the multi-field identity screen, in one place.
 *
 * The repository-wide strings file (web/src/strings.ts, unit l3/strings-file)
 * is not merged yet. Until it is, every user-visible string of this screen
 * lives in this local module; it moves to the strings file in a follow-up.
 */
export const FIELDS_SCREEN_TEXT = {
  title: 'Fields',
  caseLabelPrefix: 'Case',
  bannerTitle: 'Example data',
  bannerText:
    'This screen shows illustrative placeholder fields over a generic rural area. No real field is described.',
  selectedLabel: 'Selected',
  fieldIdLabel: 'Identifier',
  areaUnit: 'ha',
  areaProvenanceLabel: 'DERIVED',
  areaFootnote:
    'Area is computed from each field boundary with a spherical approximation of the Earth (provenance DERIVED). It is not stored.',
  emptyList: 'The example case has no fields.',
} as const
