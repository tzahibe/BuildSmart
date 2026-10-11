/** Product Readiness Audit — render real `DemoDesign` payloads through the PRODUCT renderer
 * (`DemoPlan`) and write each one out as SVG markup, so the audit inspects what the product draws
 * rather than a diagnostic drawing.
 *
 * Audit tooling, not a behavioural test: it asserts only that the product renderer produced an
 * `<svg>` for every payload. It is a no-op (skipped) unless `AUDIT_DESIGNS_DIR` points at a
 * directory of DemoDesign JSON files, so the normal suite is unaffected.
 */
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import DemoPlan from './DemoPlan'
import type { DemoDesign } from './demoDesign'

const DIR = process.env.AUDIT_DESIGNS_DIR
const OUT = process.env.AUDIT_SVG_DIR ?? (DIR ? join(DIR, '..', 'svg') : undefined)

describe.skipIf(!DIR)('audit: product renderer output', () => {
  it('renders every audited design through DemoPlan and writes its SVG', () => {
    mkdirSync(OUT!, { recursive: true })
    const files = readdirSync(DIR!).filter((f) => f.endsWith('.json')).sort()
    expect(files.length).toBeGreaterThan(0)
    for (const file of files) {
      const design = JSON.parse(readFileSync(join(DIR!, file), 'utf8')) as DemoDesign
      const { container, unmount } = render(<DemoPlan design={design} streetFacingSide="NORTH" />)
      const svg = container.querySelector('svg')
      expect(svg, `${file} produced no <svg>`).toBeTruthy()
      writeFileSync(join(OUT!, file.replace(/\.json$/, '.svg')), svg!.outerHTML, 'utf8')
      unmount()
    }
  })
})
