// DRAWING-any-shape audit (#197): rasterise the product renderer's SVG output with the product's own
// stylesheets in a real browser (Playwright chromium, already a frontend devDependency).
// usage: node rasterise.mjs <svg_dir> <png_dir> <frontend_dir> [designs_dir]
//
// With <designs_dir> it also MEASURES the drawing's legibility in the same browser pass and writes
// <png_dir>/label-metrics.json: for each figure, how many room-label blocks overlap another label,
// and how many sit outside the room they belong to. Both are measured from the real rendered text
// boxes (getBBox, SVG user units = plan metres), never estimated from string lengths. `DemoPlan`
// draws one <text class="demo-room-label"> per entry of `design.rooms`, in that order, which is
// what ties a measured box back to its room.
import { readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const [svgDir, pngDir, frontendDir, designsDir] = process.argv.slice(2)
const { chromium } = await import(join(frontendDir, 'node_modules', 'playwright-core', 'index.mjs'))
mkdirSync(pngDir, { recursive: true })
const css = ['DemoPlan.css', 'SketchSvg.css', 'PlanLegend.css', 'Dim.css', 'DemoWorkspace.css']
  .map((f) => readFileSync(join(frontendDir, 'src', 'design', f), 'utf8')).join('\n')
// the browser the frontend's e2e suite already cached on this machine; a newer one via `npx playwright install chromium-headless-shell`
const exe = process.env.DRAWING_AUDIT_CHROME ?? join(process.env.HOME, 'Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell')
const browser = await chromium.launch({ executablePath: exe })
const page = await browser.newPage({ viewport: { width: 1500, height: 1200 }, deviceScaleFactor: 1 })
const metrics = {}
for (const file of readdirSync(svgDir).filter((f) => f.endsWith('.svg')).sort()) {
  const svg = readFileSync(join(svgDir, file), 'utf8')
  const legendFile = join(svgDir, file.replace(/\.svg$/, '.legend.html'))
  let legend = ''
  try { legend = readFileSync(legendFile, 'utf8') } catch {}
  const html = `<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>${css}
    body{margin:0;background:#fff;font-family:-apple-system,"Segoe UI",Arial,sans-serif}
    #frame{width:1200px;height:900px}
    #cap{font-size:14px;color:#333;padding:4px 8px;direction:ltr}
    #row{display:flex;flex-direction:row;align-items:flex-start}
    .legend{width:260px;padding:8px;font-size:13px}
  </style></head><body><div id="cap">${file}</div><div id="row"><div id="frame">${svg}</div>${legend}</div></body></html>`
  await page.setContent(html)
  await page.locator('body').screenshot({ path: join(pngDir, file.replace(/\.svg$/, '.png')) })
  if (designsDir) {
    let design = null
    try { design = JSON.parse(readFileSync(join(designsDir, file.replace(/\.svg$/, '.json')), 'utf8')) } catch {}
    if (design) metrics[file.replace(/\.svg$/, '')] = await measure(page, design)
  }
  console.log('rasterised', file)
}
if (designsDir) writeFileSync(join(pngDir, 'label-metrics.json'), JSON.stringify(metrics, null, 1))
await browser.close()

/** Legibility, measured in the browser from the rendered text boxes. */
async function measure(page, design) {
  const rooms = design.rooms.map((r) => ({
    id: r.id, x: r.x, y: r.y, w: r.gross_width_m, h: r.gross_depth_m,
    poly: r.polygon_m ?? null,
  }))
  return page.evaluate((rooms) => {
    const svg = document.querySelector('svg.demo-plan')
    const labels = [...svg.querySelectorAll('text.demo-room-label')]
    const boxes = labels.map((el) => {
      const b = el.getBBox()
      return { x: b.x, y: b.y, w: b.width, h: b.height }
    })
    const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
    const collisions = []
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        if (hit(boxes[i], boxes[j])) {
          collisions.push([rooms[i]?.id ?? `#${i}`, rooms[j]?.id ?? `#${j}`])
        }
      }
    }
    // a label block that is not contained in the rectangle of its own room (an L room's polygon
    // bounding box is used, which is what `x`/`gross_*` already carry for it)
    const escaped = []
    const TOL = 0.05
    boxes.forEach((b, i) => {
      const r = rooms[i]
      if (!r) return
      const inside = b.x >= r.x - TOL && b.y >= r.y - TOL &&
        b.x + b.w <= r.x + r.w + TOL && b.y + b.h <= r.y + r.h + TOL
      if (!inside) {
        escaped.push({
          room: r.id,
          overflow_m: Math.round(100 * Math.max(r.x - b.x, b.x + b.w - (r.x + r.w),
                                                r.y - b.y, b.y + b.h - (r.y + r.h))) / 100,
        })
      }
    })
    return { labels: boxes.length, label_collisions: collisions, labels_outside_their_room: escaped }
  }, rooms)
}
