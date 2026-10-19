// DRAWING-any-shape audit (#197): rasterise the product renderer's SVG output with the product's own
// stylesheets in a real browser (Playwright chromium, already a frontend devDependency).
// usage: node rasterise.mjs <svg_dir> <png_dir> <frontend_dir>
import { readdirSync, readFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'

const [svgDir, pngDir, frontendDir] = process.argv.slice(2)
const { chromium } = await import(join(frontendDir, 'node_modules', 'playwright-core', 'index.mjs'))
mkdirSync(pngDir, { recursive: true })
const css = ['DemoPlan.css', 'SketchSvg.css', 'PlanLegend.css', 'Dim.css', 'DemoWorkspace.css']
  .map((f) => readFileSync(join(frontendDir, 'src', 'design', f), 'utf8')).join('\n')
// the browser the frontend's e2e suite already cached on this machine; a newer one via `npx playwright install chromium-headless-shell`
const exe = process.env.DRAWING_AUDIT_CHROME ?? join(process.env.HOME, 'Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell')
const browser = await chromium.launch({ executablePath: exe })
const page = await browser.newPage({ viewport: { width: 1500, height: 1200 }, deviceScaleFactor: 1 })
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
  console.log('rasterised', file)
}
await browser.close()
