import type { StringKey } from '../strings'
import { IconArchive, IconMap, IconOverview, IconPrinter, IconReport, IconSprout } from './icons'
import type { Icon } from './icons'

/**
 * The sections of the app, grouped in the order of the work: the case and
 * its fields, the plan of a field and its full report, then what leaves the
 * screen (the print sheet and the saved case). PROPOSED, l3/erp-shell; a
 * navigation entry is the lane owner's decision.
 */
export interface NavItem {
  route: string
  label: StringKey
  icon: Icon
}

export interface NavGroup {
  heading: StringKey
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    heading: 'shell.group.overview',
    items: [
      { route: '/', label: 'nav.case', icon: IconOverview },
      { route: '/fields', label: 'nav.fields', icon: IconMap },
    ],
  },
  {
    heading: 'shell.group.planning',
    items: [
      { route: '/board', label: 'nav.board', icon: IconSprout },
      { route: '/plant', label: 'nav.report', icon: IconReport },
    ],
  },
  {
    heading: 'shell.group.outputs',
    items: [
      { route: '/print', label: 'nav.print', icon: IconPrinter },
      { route: '/saved', label: 'nav.saved', icon: IconArchive },
    ],
  },
]

/** The navigation item of a route, or null for a route outside the menu. */
export function navItemOf(route: string): NavItem | null {
  for (const group of NAV_GROUPS) {
    const item = group.items.find((each) => each.route === route)
    if (item !== undefined) return item
  }
  return null
}
