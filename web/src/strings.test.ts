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
