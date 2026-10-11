/** Concept Plan Communication Pass — measure label readability on rendered product plans.
 * Loads each SVG (produced by the real `DemoPlan`) with the product's stylesheets in a browser and
 * measures, from the REAL laid-out geometry, how often text collides with other text, with
 * furniture symbols, and with door swings. Pure measurement: it renders, it never edits. */
import { chromium } from 'playwright'
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const SVG = process.env.SVG_DIR, CSS = process.env.CSS_FILE, OUT = process.env.OUT_JSON
const css = readFileSync(CSS, 'utf8')
const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1200, height: 1200 } })
const rows = {}
for (const f of readdirSync(SVG).filter((x) => x.endsWith('.svg')).sort()) {
  const svg = readFileSync(join(SVG, f), 'utf8')
  await page.setContent(`<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#fff}
    svg{width:1100px;height:auto;display:block}${css}</style>${svg}`, { waitUntil: 'load' })
  rows[f.replace('.svg', '')] = await page.evaluate(() => {
    const AREA = (r) => Math.max(0, r.width) * Math.max(0, r.height)
    const inter = (a, b) => {
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left)
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
      return w > 0 && h > 0 ? w * h : 0
    }
    const box = (el) => el.getBoundingClientRect()
    const texts = [...document.querySelectorAll('svg text')]
      .filter((t) => (t.textContent || '').trim().length > 0)
      .map((t) => ({ el: t, cls: t.getAttribute('class') || '', r: box(t), txt: t.textContent.trim() }))
    const roomL = texts.filter((t) => t.cls.includes('demo-room-label'))
    const fixL = texts.filter((t) => t.cls.includes('demo-layout-object-label'))
    // matches BOTH markups: the old labelled rect and the new plan symbol, so before/after are comparable
    const fixRects = [...document.querySelectorAll('.demo-layout-object-rect, .demo-fixture-fill, .demo-fixture-focal')].map(box)
    const swings = [...document.querySelectorAll('.demo-door-arc, .demo-door-leaf')].map(box)

    let textPairs = 0, roomPairs = 0, fixPairs = 0
    for (let i = 0; i < texts.length; i++)
      for (let j = i + 1; j < texts.length; j++) {
        const o = inter(texts[i].r, texts[j].r)
        if (o <= 0) continue
        textPairs++
        const involvesRoom = texts[i].cls.includes('demo-room-label') || texts[j].cls.includes('demo-room-label')
        const involvesFix = texts[i].cls.includes('demo-layout-object-label') || texts[j].cls.includes('demo-layout-object-label')
        if (involvesRoom) roomPairs++
        if (involvesFix) fixPairs++
      }
    // a room label is "obscured" when a furniture symbol covers >=25% of its own text area
    const obscured = roomL.filter((t) => {
      const a = AREA(t.r); if (!a) return false
      const cov = fixRects.reduce((s, r) => s + inter(t.r, r), 0)
      return cov / a >= 0.25
    }).length
    const over = (t) => swings.some((s) => inter(t.r, s) > 0)
    const swingHits = texts.filter(over).length
    const swingHitsRoom = roomL.filter(over).length
    const swingHitsOther = swingHits - swingHitsRoom
    return {
      texts: texts.length, room_labels: roomL.length, fixture_labels: fixL.length,
      text_collision_pairs: textPairs,
      room_label_collision_pairs: roomPairs,
      fixture_label_collision_pairs: fixPairs,
      room_labels_obscured_by_furniture: obscured,
      texts_over_door_swings: swingHits,
      room_labels_over_door_swings: swingHitsRoom,
      other_texts_over_door_swings: swingHitsOther,
      fixture_label_texts: fixL.map((t) => t.txt).slice(0, 40),
    }
  })
}
await browser.close()
const tot = Object.values(rows).reduce((a, r) => {
  for (const k of Object.keys(r)) if (typeof r[k] === 'number') a[k] = (a[k] || 0) + r[k]
  return a
}, {})
writeFileSync(OUT, JSON.stringify({ totals: tot, per_plan: rows }, null, 1))
console.log('TOTALS', JSON.stringify(tot))
