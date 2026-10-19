/** DRAWING-any-shape audit (#197, 2026-10-18) — render real `DemoDesign` payloads through the
 * PRODUCT renderer (`DemoPlan`, with the compass and scale bar the primary plan view gets) AND the
 * product legend (`PlanLegend`), and write both out as markup so the audit inspects what the product
 * draws. Same shape as `audit-render.test.tsx`: a no-op unless `DRAWING_AUDIT_DESIGNS_DIR` is set. */
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import DemoPlan from './DemoPlan'
import PlanLegend from './PlanLegend'
import type { DemoDesign } from './demoDesign'

const DIR = process.env.DRAWING_AUDIT_DESIGNS_DIR
const OUT = process.env.DRAWING_AUDIT_SVG_DIR ?? (DIR ? join(DIR, '..', 'svg') : undefined)

describe.skipIf(!DIR)('drawing audit: product renderer output', () => {
  it('renders every design through DemoPlan + PlanLegend and writes the markup', () => {
    mkdirSync(OUT!, { recursive: true })
    const files = readdirSync(DIR!).filter((f) => f.endsWith('.json')).sort()
    expect(files.length).toBeGreaterThan(0)
    const failures: string[] = []
    for (const file of files) {
      const design = JSON.parse(readFileSync(join(DIR!, file), 'utf8')) as DemoDesign
      try {
        const { container, unmount } = render(<DemoPlan design={design} streetFacingSide="NORTH" />)
        const svg = container.querySelector('svg')
        expect(svg, `${file} produced no <svg>`).toBeTruthy()
        writeFileSync(join(OUT!, file.replace(/\.json$/, '.svg')), svg!.outerHTML, 'utf8')
        unmount()
        const legend = render(<PlanLegend design={design} />)
        writeFileSync(join(OUT!, file.replace(/\.json$/, '.legend.html')), legend.container.innerHTML, 'utf8')
        legend.unmount()
      } catch (err) {
        failures.push(`${file}: ${String(err).slice(0, 300)}`)
      }
    }
    writeFileSync(join(OUT!, 'render-failures.txt'), failures.join('\n'), 'utf8')
    expect(failures, failures.join('\n')).toEqual([])
  })
})
