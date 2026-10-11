import { chromium } from 'playwright'
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
const SVG = process.env.SVG_DIR, OUT = process.env.PNG_DIR, CSS = process.env.CSS_FILE
mkdirSync(OUT, { recursive: true })
const css = readFileSync(CSS, 'utf8')
const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1100, height: 1100 }, deviceScaleFactor: 2 })
const files = readdirSync(SVG).filter(f => f.endsWith('.svg')).sort()
for (const f of files) {
  const svg = readFileSync(join(SVG, f), 'utf8')
  const html = `<!doctype html><meta charset="utf-8"><style>
    html,body{margin:0;background:#fff;font-family:system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif}
    .wrap{padding:14px;width:1072px}
    .ttl{font:600 15px system-ui;margin:0 0 8px;color:#111}
    svg{width:1040px;height:auto;display:block}
    ${css}</style>
    <div class="wrap"><p class="ttl">${f.replace('.svg','').replace('__',' — ')}</p>${svg}</div>`
  await page.setContent(html, { waitUntil: 'load' })
  const el = await page.$('.wrap')
  await el.screenshot({ path: join(OUT, f.replace('.svg', '.png')) })
}
await browser.close()
console.log('rendered', files.length, 'PNGs')
