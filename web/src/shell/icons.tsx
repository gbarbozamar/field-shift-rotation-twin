import type { ReactNode } from 'react'

/**
 * Line icons of the interface, drawn inline (no icon dependency): a 24-unit
 * grid, round caps, the stroke in the current text colour. Every icon is
 * decorative (aria-hidden); the text beside it carries the meaning.
 */

interface IconProps {
  className?: string
}

/** 16px, the size of an icon in the menu and on cards. */
const DEFAULT_SIZE = ['h-4', 'w-4', 'shrink-0'].join(' ')

function Svg({ className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className ?? DEFAULT_SIZE}
    >
      {children}
    </svg>
  )
}

export type Icon = (props: IconProps) => ReactNode

export function IconOverview(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </Svg>
  )
}

export function IconMap(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 4 3.5 6.3v13.5L9 17.5l6 2.5 5.5-2.3V4.2L15 6.5 9 4Z" />
      <path d="M9 4v13.5M15 6.5V20" />
    </Svg>
  )
}

export function IconSprout(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 21v-9" />
      <path d="M12 12c0-4.2 3-7 8-7 0 4.2-3 7-8 7Z" />
      <path d="M12 14.5C12 11.3 9.6 9 5 9c0 3.2 2.4 5.5 7 5.5Z" />
    </Svg>
  )
}

export function IconReport(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5" />
      <path d="M9 17v-3M12 17v-5M15 17v-2" />
    </Svg>
  )
}

export function IconPrinter(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7 9V3.5h10V9" />
      <rect x="3.5" y="9" width="17" height="8" rx="2" />
      <path d="M7 14h10v6.5H7Z" />
    </Svg>
  )
}

export function IconArchive(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="4" width="18" height="5" rx="1.2" />
      <path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9" />
      <path d="M10 13h4" />
    </Svg>
  )
}

export function IconRuler(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 16.5 16.5 3l4.5 4.5L7.5 21 3 16.5Z" />
      <path d="m7 12.5 2 2M10 9.5l2 2M13 6.5l2 2" />
    </Svg>
  )
}

export function IconRotate(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M17 2.5 20.5 6 17 9.5" />
      <path d="M3.5 11V9.5a3.5 3.5 0 0 1 3.5-3.5h13.5" />
      <path d="M7 21.5 3.5 18 7 14.5" />
      <path d="M20.5 13v1.5A3.5 3.5 0 0 1 17 18H3.5" />
    </Svg>
  )
}

export function IconCheckCircle(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </Svg>
  )
}

export function IconArrowRight(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Svg>
  )
}

export function IconMenu(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 6.5h16M4 12h16M4 17.5h16" />
    </Svg>
  )
}

export function IconClose(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Svg>
  )
}

/** The mark of the application: a leaf over furrows. */
export function IconMark(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 14c0-5 3.2-8.5 8.5-8.5 0 5-3.2 8.5-8.5 8.5Z" />
      <path d="M12 14c0-3.5-2.2-6-6-6 0 3.5 2.2 6 6 6Z" />
      <path d="M3.5 18.5h17M6.5 21h11" />
    </Svg>
  )
}
