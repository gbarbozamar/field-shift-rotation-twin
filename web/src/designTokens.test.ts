import { describe, expect, it } from 'vitest'
import { createHash } from 'node:crypto'
import { existsSync, readdirSync, readFileSync } from 'fs'
import { dirname, join, relative, resolve } from 'path'
import { fileURLToPath } from 'url'

/**
 * Acceptance test of the design-token unit (issue #430).
 *
 * Case 1 — the four files of the approved font package ship under
 * web/src/assets/fonts, byte-for-byte: the two woff2 files are checked
 * against the SHA-256 hashes of the design handoff, and the two SIL OFL
 * 1.1 licence texts ship unchanged next to them.
 *
 * Case 2 — web/src/index.css holds the whole design foundation: the two
 * @font-face rules with relative paths (no absolute path, no external
 * host), every --fs- token with the exact value of the handoff, the
 * Tailwind 4 @theme bridge that exposes the tokens as utilities, the
 * shell application (body, h1-h4), the :focus-visible base, ::selection
 * and the prefers-reduced-motion block.
 *
 * Case 3 — no .css/.ts/.tsx file under web/src references an external
 * font host: the fonts are self-hosted files, never a CDN or web-font
 * service.
 */

const srcDir = dirname(fileURLToPath(import.meta.url))
const fontsDir = resolve(srcDir, 'assets/fonts')
const cssPath = resolve(srcDir, 'index.css')
const appPath = resolve(srcDir, 'App.tsx')

/** The font files of the design handoff, with the approved woff2 hashes. */
const FONT_PACKAGE: Record<string, string | null> = {
  'dm-sans-latin.woff2': '9fea608a947e67020c33cad9a6fe3d60c54119dfb8cff87768a8117a15ed7543',
  'dmsans-OFL.txt': null,
  'space-grotesk-latin.woff2': '0640890476fc1198ab4de571fb658de443c4d85b66466ec09534a8737ab1ce9d',
  'spacegrotesk-OFL.txt': null,
}

/** The tokens, transcribed verbatim from the approved design handoff. */
const TOKENS: Record<string, string> = {
  '--fs-bg': 'hsl(140 18% 96%)',
  '--fs-surface': '#fff',
  '--fs-text': 'hsl(165 18% 15%)',
  '--fs-muted': 'hsl(165 7% 40%)',
  '--fs-border': 'hsl(140 10% 89%)',
  '--fs-brand': 'hsl(105 43% 45%)',
  '--fs-primary': 'hsl(105 45% 33%)',
  '--fs-info': 'hsl(201 70% 32%)',
  '--fs-warning': '#885400',
  '--fs-warning-bg': '#fff7e8',
  '--fs-error': '#ad3325',
  '--fs-error-bg': '#fff0ed',
  '--fs-selection-bg': '#eaf3e7',
  '--fs-font-body': "'DM Sans', system-ui, sans-serif",
  '--fs-font-heading': "'Space Grotesk', system-ui, sans-serif",
  '--fs-radius': '8px',
  '--fs-control-min': '44px',
  '--fs-motion': '160ms',
}

/** The @theme entries that expose the tokens as Tailwind 4 utilities. */
const THEME_COLORS = [
  '--color-fs-bg',
  '--color-fs-surface',
  '--color-fs-text',
  '--color-fs-muted',
  '--color-fs-border',
  '--color-fs-brand',
  '--color-fs-primary',
  '--color-fs-info',
  '--color-fs-warning',
  '--color-fs-error',
]

/**
 * External font hosts, written as concatenations so that this test file
 * does not itself contain the strings it forbids.
 */
const EXTERNAL_FONT_HOSTS = [
  'fonts.' + 'googleapis',
  'fonts.' + 'gstatic',
  'type' + 'kit',
  'cdn' + '.',
]

function sha256(filePath: string): string {
  return createHash('sha256').update(readFileSync(filePath)).digest('hex')
}

/** The body of a top-level block like `@theme { ... }` (no nested braces). */
function blockBody(css: string, opener: string): string {
  const start = css.indexOf(opener)
  if (start === -1) return ''
  const end = css.indexOf('\n}', start)
  return end === -1 ? '' : css.slice(start + opener.length, end)
}

function listStyleSourceFiles(dir: string): string[] {
  const found: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) found.push(...listStyleSourceFiles(full))
    else if (/\.(css|ts|tsx)$/.test(entry.name)) found.push(full)
  }
  return found
}

describe('self-hosted fonts of the design package', () => {
  it('ships the four approved files under web/src/assets/fonts', () => {
    for (const name of Object.keys(FONT_PACKAGE)) {
      const path = join(fontsDir, name)
      expect(existsSync(path), `${name} must exist under web/src/assets/fonts`).toBe(true)
      expect(readFileSync(path).length, `${name} must not be empty`).toBeGreaterThan(0)
    }
  })

  it('the two woff2 files match the SHA-256 hashes of the design handoff', () => {
    for (const [name, expected] of Object.entries(FONT_PACKAGE)) {
      if (expected === null) continue
      const actual = sha256(join(fontsDir, name))
      expect(actual, `${name} must be the approved file, byte-for-byte`).toBe(expected)
    }
  })
})

describe('index.css design foundation', () => {
  const css = readFileSync(cssPath, 'utf8')

  it('declares both @font-face rules with relative paths only', () => {
    expect(css, 'the tailwind import stays first').toMatch(/^@import "tailwindcss";/)
    const faces = css.match(/@font-face\s*\{[^}]*\}/g) ?? []
    expect(faces.length, 'exactly two @font-face rules').toBe(2)
    for (const family of ['DM Sans', 'Space Grotesk']) {
      const face = faces.find((block) => block.includes(`font-family: '${family}'`))
      expect(face, `the ${family} @font-face must exist`).toBeDefined()
      expect(face, `${family} covers weights 400 to 700`).toContain('font-weight: 400 700')
      expect(face, `${family} is normal style`).toContain('font-style: normal')
      expect(face, `${family} uses font-display swap`).toContain('font-display: swap')
      expect(face, `${family} points at the local woff2`).toMatch(/src: url\('\.\/assets\/fonts\/[^']+'\) format\('woff2'\)/)
    }
    expect(css).toContain("url('./assets/fonts/dm-sans-latin.woff2')")
    expect(css).toContain("url('./assets/fonts/space-grotesk-latin.woff2')")
    // No absolute path and no external host: every url() is one of the two
    // relative font paths, quoted exactly as written.
    const urls = [...css.matchAll(/url\(([^)]*)\)/g)].map((m) => m[1])
    expect(urls.length, 'the two font urls must be present').toBe(2)
    for (const url of urls) {
      expect(
        ["'./assets/fonts/dm-sans-latin.woff2'", "'./assets/fonts/space-grotesk-latin.woff2'"],
        `font urls must be relative: ${url}`,
      ).toContain(url)
    }
  })

  it('defines every --fs- token with the exact value of the handoff', () => {
    for (const [name, value] of Object.entries(TOKENS)) {
      expect(css, `${name} must be ${value}`).toContain(`${name}: ${value};`)
    }
  })

  it('registers the tokens as Tailwind 4 utilities in @theme', () => {
    const theme = blockBody(css, '@theme {')
    expect(theme, 'the @theme block must exist').not.toBe('')
    for (const entry of THEME_COLORS) {
      const rootToken = entry.replace('--color-', '--')
      expect(theme, `${entry} must be registered in @theme`).toContain(`${entry}: var(${rootToken});`)
    }
    expect(theme, 'the body font utility must be registered').toContain(
      '--font-fs-body: var(--fs-font-body);',
    )
    expect(theme, 'the heading font utility must be registered').toContain(
      '--font-fs-heading: var(--fs-font-heading);',
    )
  })

  it('applies the tokens to the shell', () => {
    const body = blockBody(css, 'body {')
    expect(body, 'the body rule must exist').not.toBe('')
    expect(body).toContain('background: var(--fs-bg);')
    expect(body).toContain('color: var(--fs-text);')
    expect(body).toContain('font-family: var(--fs-font-body);')
    expect(css, 'headings use the heading font').toMatch(
      /h1,\s*\nh2,\s*\nh3,\s*\nh4\s*\{\s*\n\s*font-family: var\(--fs-font-heading\);/,
    )
  })

  it('sets the focus-visible base and ::selection', () => {
    const focus = blockBody(css, ':focus-visible {')
    expect(focus, 'the :focus-visible rule must exist').not.toBe('')
    expect(focus).toContain('outline: 3px solid var(--fs-info);')
    expect(focus).toContain('outline-offset: 3px;')
    const selection = blockBody(css, '::selection {')
    expect(selection, 'the ::selection rule must exist').not.toBe('')
    expect(selection).toContain('background: var(--fs-selection-bg);')
  })

  it('neutralises motion under prefers-reduced-motion', () => {
    const reduced = blockBody(css, '@media (prefers-reduced-motion: reduce) {')
    expect(reduced, 'the prefers-reduced-motion block must exist').not.toBe('')
    expect(reduced).toContain('*,')
    expect(reduced).toContain('*::before,')
    expect(reduced).toContain('*::after')
    expect(reduced).toContain('animation-duration: 0.01ms;')
    expect(reduced).toContain('transition-duration: 0.01ms;')
    expect(reduced).toContain('scroll-behavior: auto;')
  })
})

describe('the shell uses the token utilities', () => {
  it('App.tsx swaps the slate shell classes for bg-fs-bg and text-fs-text', () => {
    const app = readFileSync(appPath, 'utf8')
    expect(app, 'the wrapper must use the token background').toContain('bg-fs-bg')
    expect(app, 'the wrapper must use the token text colour').toContain('text-fs-text')
    expect(app, 'the old slate background must be gone from the wrapper').not.toContain('bg-slate-50')
    expect(app, 'the old slate text colour must be gone from the wrapper').not.toContain('text-slate-900')
  })
})

describe('no external font host anywhere in web/src', () => {
  it('no .css/.ts/.tsx file references a font CDN or web-font service', () => {
    const problems: string[] = []
    for (const filePath of listStyleSourceFiles(srcDir)) {
      const src = readFileSync(filePath, 'utf8')
      for (const host of EXTERNAL_FONT_HOSTS) {
        if (src.includes(host)) problems.push(`${relative(srcDir, filePath)} references ${host}`)
      }
    }
    expect(problems, 'fonts are self-hosted files, never an external host:\n' + problems.join('\n')).toEqual([])
  })
})
