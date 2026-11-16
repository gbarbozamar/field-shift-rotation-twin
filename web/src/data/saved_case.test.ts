import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'

/**
 * The byte-identical guard of the saved case copy (D177, follow-up of #341).
 *
 * D177: "`demo/` writes it and checks it; the interface reads a
 * byte-identical copy under `web/src/data/`." This file is that guard for
 * the copy `saved_case.json`: it reads both files, the copy and the demo's
 * `demo/saved_cases/example-case.json`, and compares them byte for byte,
 * so the two can never drift silently. When the demo saves the case again
 * (there is one file per case; saving again replaces it, and the commit is
 * its version), the copy must be refreshed in the same change or this test
 * fails.
 *
 * The demo file sits outside `web/`, read the way `strings.test.ts` already
 * reads files from disk in this suite: `readFileSync` on a path resolved
 * from `import.meta.url` (the repository root is three levels above this
 * folder). No hash is interposed; the comparison is file to file.
 */

const dataDir = dirname(fileURLToPath(import.meta.url))
const copyPath = resolve(dataDir, 'saved_case.json')
const demoPath = resolve(dataDir, '..', '..', '..', 'demo', 'saved_cases', 'example-case.json')

describe('the saved case copy', () => {
  it('is byte-identical to demo/saved_cases/example-case.json', () => {
    const copy = readFileSync(copyPath)
    const demo = readFileSync(demoPath)
    expect(
      Buffer.compare(copy, demo) === 0,
      `the copy ${copyPath} (${copy.length} bytes) and the demo's ${demoPath} ` +
        `(${demo.length} bytes) must be the same file, byte for byte; when the ` +
        `demo saves the case again, refresh the copy in the same change`,
    ).toBe(true)
  })
})
