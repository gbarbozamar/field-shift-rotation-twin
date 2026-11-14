import assert from 'node:assert/strict'
import { readFile, stat } from 'node:fs/promises'
import { resolve } from 'node:path'

const base = '/field-shift-rotation-twin/'
const html = await readFile('dist/index.html', 'utf8')
assert.match(html, /<html lang="en">/)
assert.match(html, /<div id="root"><\/div>/)
const assets = [...html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)].map(match => match[1])
assert.ok(assets.some(path => path.endsWith('.js')), 'A compiled JavaScript entry is required')
assert.ok(assets.some(path => path.endsWith('.css')), 'A compiled stylesheet is required')
for (const asset of assets) {
  assert.ok(asset.startsWith(`${base}assets/`), `Incorrect Pages asset base: ${asset}`)
  const local = resolve('dist', asset.slice(base.length))
  assert.ok((await stat(local)).size > 0, `Empty asset: ${asset}`)
}
console.log(`Deployment acceptance passed: ${assets.length} compiled assets use ${base}`)
