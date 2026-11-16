import { describe, expect, it } from 'vitest'
import { createHash } from 'node:crypto'
import { existsSync, readdirSync, readFileSync } from 'fs'
import { dirname, join, relative, resolve } from 'path'
import { fileURLToPath } from 'url'

/**
 * Acceptance test of the design tokens and fonts of the interface
 * (issue #430; values replaced by l3/own-identity with the interface's own
 * identity, chosen by the owner of the interface lane).
 *
 * Case 1: the font files ship under web/src/assets/fonts, byte-for-byte as
 * downloaded from the official Google Fonts repository: the five ttf files
 * are checked against their SHA-256 hashes, and the three SIL OFL 1.1
 * licence texts ship next to them.
 *
 * Case 2: web/src/index.css holds the whole design foundation: the
 * @font-face rules with relative paths (no absolute path, no external
 * host), every --fs- token with its exact value, the Tailwind 4 @theme
 * bridge that exposes the tokens as utilities, the shell application
 * (body, h1-h4), the :focus-visible base, ::selection and the
 * prefers-reduced-motion block.
 *
 * Case 3: no .css/.ts/.tsx file under web/src references an external font
 * host: the fonts are self-hosted files, never a CDN or web-font service.
 */

const srcDir = dirname(fileURLToPath(import.meta.url))
const fontsDir = resolve(srcDir, 'assets/fonts')
const cssPath = resolve(srcDir, 'index.css')
const appPath = resolve(srcDir, 'App.tsx')

/**
 * The font files, with the SHA-256 of each ttf as downloaded on 15 Nov 2026
 * from github.com/google/fonts (ofl/bricolagegrotesque,
 * ofl/atkinsonhyperlegible, ofl/ibmplexmono), unmodified.
 */
const FONT_PACKAGE: Record<string, string | null> = {
  'bricolage-grotesque-variable.ttf': '413e7357809ddd12fd80a96a8a396de0e401638d4acd3cb3e37532f0472ac682',
  'bricolagegrotesque-OFL.txt': null,
  'atkinson-hyperlegible-regular.ttf': '7fb917c89019896d0b52ee84b7cbb3304c18cb90b19a62f5e32712bd23e97669',
  'atkinson-hyperlegible-bold.ttf': '5a3b0c8cc8ca545155150b4512a1fa248298df121c50d6557e651e61fbdab92f',
  'atkinson-hyperlegible-italic.ttf': '021beda4d3c6edfc78872e436d74009f9a1bcb294331908fe5747c61d3dcc514',
  'atkinsonhyperlegible-OFL.txt': null,
  'ibm-plex-mono-medium.ttf': 'a9b4c49bb299e05b5f6c481e7fb5e78943d2793249a0c8874ab574a2d1ea6755',
  'ibmplexmono-OFL.txt': null,
}

/** The @font-face rules: family, style, weight and file, one per ttf. */
const FONT_FACES = [
  { family: 'Bricolage Grotesque', style: 'normal', weight: '200 800', file: 'bricolage-grotesque-variable.ttf' },
  { family: 'Atkinson Hyperlegible', style: 'normal', weight: '400', file: 'atkinson-hyperlegible-regular.ttf' },
  { family: 'Atkinson Hyperlegible', style: 'normal', weight: '700', file: 'atkinson-hyperlegible-bold.ttf' },
  { family: 'Atkinson Hyperlegible', style: 'italic', weight: '400', file: 'atkinson-hyperlegible-italic.ttf' },
  { family: 'IBM Plex Mono', style: 'normal', weight: '500', file: 'ibm-plex-mono-medium.ttf' },
]

/** The tokens of the interface (l3/own-identity, colours moved by l3/erp-shell). */
const TOKENS: Record<string, string> = {
  '--fs-bg': '#f4f7f5',
  '--fs-surface': '#ffffff',
  '--fs-text': '#1f2d2b',
  '--fs-muted': '#5f6f6b',
  '--fs-border': '#d9e0dc',
  '--fs-faint': '#eef2f0',
  '--fs-brand': '#1a7a3b',
  '--fs-primary': '#3e7b2c',
  '--fs-info': '#19648b',
  '--fs-ok': '#3e7b2c',
  '--fs-warning': '#86500e',
  '--fs-warning-bg': 'color-mix(in srgb, var(--fs-warning-accent) 10%, var(--fs-surface))',
  '--fs-error': '#c0392b',
  '--fs-error-bg': 'color-mix(in srgb, var(--fs-error) 9%, var(--fs-surface))',
  '--fs-selection-bg': 'color-mix(in srgb, var(--fs-primary) 12%, var(--fs-surface))',
  '--fs-crop-1': '#7a9a2e',
  '--fs-crop-2': '#c99a2e',
  '--fs-crop-3': '#b5562f',
  '--fs-crop-4': '#17766d',
  '--fs-crop-5': '#3b7633',
  '--fs-crop-6': '#7b5e8a',
  '--fs-font-body': "'Atkinson Hyperlegible', system-ui, sans-serif",
  '--fs-font-heading': "'Bricolage Grotesque', system-ui, sans-serif",
  '--fs-font-mono': "'IBM Plex Mono', ui-monospace, monospace",
  '--fs-radius': '8px',
  '--fs-control-min': '44px',
  '--fs-motion': '160ms',
  '--fs-brand-soft': 'color-mix(in srgb, var(--fs-primary) 18%, var(--fs-surface))',
  '--fs-furrow': 'color-mix(in srgb, var(--fs-primary) 5%, transparent)',
  '--fs-warning-accent': '#f2a900',
  '--fs-radius-card': '10px',
  '--fs-shadow-card': '0 1px 2px rgb(31 45 43 / 0.05)',
  '--fs-shadow-pop': '0 4px 6px -1px rgb(31 45 43 / 0.1), 0 2px 4px -2px rgb(31 45 43 / 0.1)',
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
  '--color-fs-ok',
  '--color-fs-faint',
  '--color-fs-crop-1',
  '--color-fs-crop-2',
  '--color-fs-crop-3',
  '--color-fs-crop-4',
  '--color-fs-crop-5',
  '--color-fs-crop-6',
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

describe('self-hosted fonts', () => {
  it('ships the font files and their licence texts under web/src/assets/fonts, and no other file', () => {
    for (const name of Object.keys(FONT_PACKAGE)) {
      const path = join(fontsDir, name)
      expect(existsSync(path), `${name} must exist under web/src/assets/fonts`).toBe(true)
      expect(readFileSync(path).length, `${name} must not be empty`).toBeGreaterThan(0)
    }
    expect(readdirSync(fontsDir).sort()).toEqual(Object.keys(FONT_PACKAGE).sort())
  })

  it('the ttf files match the SHA-256 hashes of the official files', () => {
    for (const [name, expected] of Object.entries(FONT_PACKAGE)) {
      if (expected === null) continue
      const actual = sha256(join(fontsDir, name))
      expect(actual, `${name} must be the official file, byte-for-byte`).toBe(expected)
    }
  })
})

describe('index.css design foundation', () => {
  const css = readFileSync(cssPath, 'utf8')

  it('declares one @font-face rule per font file, with relative paths only', () => {
    expect(css, 'the tailwind import stays first').toMatch(/^@import "tailwindcss";/)
    const faces = css.match(/@font-face\s*\{[^}]*\}/g) ?? []
    expect(faces.length, 'one @font-face rule per ttf').toBe(FONT_FACES.length)
    for (const { family, style, weight, file } of FONT_FACES) {
      const face = faces.find((block) => block.includes(`url('./assets/fonts/${file}')`))
      expect(face, `the @font-face of ${file} must exist`).toBeDefined()
      expect(face, `${file} is ${family}`).toContain(`font-family: '${family}';`)
      expect(face, `${file} has weight ${weight}`).toContain(`font-weight: ${weight};`)
      expect(face, `${file} has style ${style}`).toContain(`font-style: ${style};`)
      expect(face, `${file} uses font-display swap`).toContain('font-display: swap')
      expect(face, `${file} is declared as truetype`).toContain("format('truetype')")
    }
    // No absolute path and no external host: every url() is one of the
    // relative font paths, quoted exactly as written.
    const urls = [...css.matchAll(/url\(([^)]*)\)/g)].map((m) => m[1])
    expect(urls.sort()).toEqual(FONT_FACES.map(({ file }) => `'./assets/fonts/${file}'`).sort())
  })

  it('defines every --fs- token with its exact value', () => {
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
    expect(theme, 'the mono font utility must be registered').toContain('--font-fs-mono: var(--fs-font-mono);')
    expect(theme, 'font-mono follows the mono token').toContain('--font-mono: var(--fs-font-mono);')
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
