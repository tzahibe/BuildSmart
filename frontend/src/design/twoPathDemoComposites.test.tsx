import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import DemoPlan from './DemoPlan'
import type { DemoDesign } from './demoDesign'

/** Issue #155, AC-2/AC-4 — renders both path A and path B of each selected brief through the
 * SAME shipping drawing layer (`DemoPlan`, Issue #146's own renderer — see that component's own
 * docstring: it decides nothing architectural, it only draws what `DemoDesign` says), and writes
 * one side-by-side composite HTML per brief. The backend half of this Issue
 * (`backend/spikes/two_path_demo/run_demo.py`) must have already run and written
 * `docs/reports/two-path-demo/contracts/<short>-{A,B,meta}.json` — this file only draws what that
 * script measured, exactly the same "no bespoke renderer" discipline the Issue itself asks for. */

const REPO_ROOT = path.resolve(__dirname, '../../../')
// Not "data" — the repo's own root `.gitignore` has a bare `data/` rule that matches a
// directory of that name anywhere in the tree.
const DATA_DIR = path.join(REPO_ROOT, 'docs/reports/two-path-demo/contracts')
const COMPOSITE_DIR = path.join(REPO_ROOT, 'docs/reports/two-path-demo/composites')
const SELECTED_BRIEFS_PATH = path.join(REPO_ROOT, 'docs/reports/two-path-demo/selected_briefs.json')

interface PathMeta {
  outcome: 'REALIZED' | 'REFUSED'
  refusal_code: string | null
  refusal_detail: string | null
  metrics: Record<string, number | boolean | null> | null
  c30_passed?: boolean | null
}

interface BriefMeta {
  brief_id: string
  street_facing_side: string
  family_b: string
  a: PathMeta
  b: PathMeta
}

function shortId(index: number): string {
  return `brief-${String(index).padStart(2, '0')}`
}

function renderSvg(design: DemoDesign, streetFacingSide: string | null): string {
  const { container } = render(<DemoPlan design={design} streetFacingSide={streetFacingSide} />)
  const svg = container.querySelector('svg.demo-plan')
  if (!svg) throw new Error('DemoPlan did not render an <svg class="demo-plan">')
  return svg.outerHTML
}

function metricsRow(label: string, key: string, meta: PathMeta): string {
  const v = meta.metrics?.[key]
  return `<tr><td>${label}</td><td>${v === null || v === undefined ? '—' : v}</td></tr>`
}

function verdictLabel(meta: PathMeta): string {
  return meta.outcome === 'REALIZED'
    ? 'REALIZED (validated)'
    : `REFUSED — ${meta.refusal_code}: ${meta.refusal_detail ?? ''}`
}

function panel(letter: 'A' | 'B', meta: PathMeta, svg: string | null): string {
  const title = letter === 'A' ? 'Path A — shipping product' : 'Path B — rectilinear realizer'
  const body = svg ?? `<p class="no-plan">no plan — ${verdictLabel(meta)}</p>`
  return `
    <section class="panel">
      <h2>${title}</h2>
      <p class="verdict">${verdictLabel(meta)}</p>
      ${body}
      <table class="metrics">
        <tbody>
          ${metricsRow('M1 habitable aspect (median)', 'm1_habitable_aspect_median', meta)}
          ${metricsRow('M2 habitable-on-envelope ratio', 'm2_habitable_on_envelope_ratio', meta)}
          ${metricsRow('M3 circulation share', 'm3_circulation_share', meta)}
          ${metricsRow('M4 hall door count', 'm4_hall_door_count', meta)}
          ${metricsRow('M4 hall aspect (median)', 'm4_hall_aspect_median', meta)}
          ${metricsRow('M5 wet adjacency ratio', 'm5_wet_adjacency_ratio', meta)}
          ${metricsRow('M6 public zone contiguous', 'm6_public_zone_contiguous', meta)}
        </tbody>
      </table>
    </section>`
}

const hasData = fs.existsSync(DATA_DIR) && fs.existsSync(SELECTED_BRIEFS_PATH)

describe('two-path demo composites (Issue #155)', () => {
  if (!hasData) {
    it.skip('no docs/reports/two-path-demo/contracts — run backend/spikes/two_path_demo/run_demo.py '
      + 'first', () => {})
    return
  }

  const selected = JSON.parse(fs.readFileSync(SELECTED_BRIEFS_PATH, 'utf-8')) as {
    brief_ids: string[]
  }
  fs.mkdirSync(COMPOSITE_DIR, { recursive: true })

  selected.brief_ids.forEach((briefId, i) => {
    const short = shortId(i)

    it(`${short}: both paths render through the SAME DemoPlan entry point`, () => {
      const metaPath = path.join(DATA_DIR, `${short}-meta.json`)
      expect(fs.existsSync(metaPath)).toBe(true)
      const meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8')) as BriefMeta
      expect(meta.brief_id).toBe(briefId)

      const aPath = path.join(DATA_DIR, `${short}-A.json`)
      const bPath = path.join(DATA_DIR, `${short}-B.json`)

      let svgA: string | null = null
      let svgB: string | null = null

      if (fs.existsSync(aPath)) {
        const designA = JSON.parse(fs.readFileSync(aPath, 'utf-8')) as DemoDesign
        svgA = renderSvg(designA, meta.street_facing_side)
        expect(svgA).toContain('<svg')
      }
      if (fs.existsSync(bPath)) {
        const designB = JSON.parse(fs.readFileSync(bPath, 'utf-8')) as DemoDesign
        svgB = renderSvg(designB, meta.street_facing_side)
        expect(svgB).toContain('<svg')
      }

      // AC-2: both renders in this test come from the ONE `render(<DemoPlan .../>)` call site
      // above — there is no second, bespoke renderer anywhere in this file.
      expect(meta.a.outcome === 'REALIZED' ? svgA !== null : svgA === null).toBe(true)
      expect(meta.b.outcome === 'REALIZED' ? svgB !== null : svgB === null).toBe(true)

      const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Two-path demo — ${short}</title>
<style>
  body { font-family: sans-serif; margin: 2rem; }
  .composite { display: flex; gap: 2rem; }
  .panel { flex: 1; border: 1px solid #ccc; padding: 1rem; }
  svg.demo-plan { width: 100%; height: 400px; border: 1px solid #eee; }
  .verdict { font-weight: bold; }
  table.metrics { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.85rem; }
  table.metrics td { border-top: 1px solid #eee; padding: 0.2rem 0.4rem; }
  .no-plan { color: #a00; }
</style>
</head>
<body>
<h1>${short} — family ${meta.family_b}</h1>
<div class="composite">
${panel('A', meta.a, svgA)}
${panel('B', meta.b, svgB)}
</div>
</body>
</html>`
      fs.writeFileSync(path.join(COMPOSITE_DIR, `${short}.html`), html, 'utf-8')
    })
  })
})
