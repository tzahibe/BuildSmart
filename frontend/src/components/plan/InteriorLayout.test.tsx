import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'

/** The component only ever lives inside the plan's `<svg>`; mounting it there keeps jsdom in the
 * SVG namespace, which is what makes `<title>` resolve as the symbol's accessible name. */
const inSvg = (node: ReactNode) => render(<svg>{node}</svg>)
import { InteriorLayout } from './InteriorLayout'
import type { ReactNode } from 'react'
import type { DemoLayoutObject } from '../../design/demoDesign'

/** Contract test (Issue #39, AC-3): the frontend draws `DemoDesign.layout` AS-IS — one symbol per
 * object, at the object's own coordinates, identified by its own `kind` — never inventing,
 * repositioning, or dropping an object the backend placed.
 *
 * The Concept Plan Communication Pass changed HOW an object is identified, not whether it is: the
 * kind used to be printed across the drawing and is now the symbol's `<title>` plus a `data-kind`
 * attribute. The boundary these tests defend is unchanged — nothing is invented, nothing moves. */

const BED: DemoLayoutObject = {
  kind: 'BED', room_id: 'MASTER', x: 3.0, y: 1.0, width_m: 1.8, depth_m: 2.0, rotation_deg: 0.0,
  clearance_x: 3.0, clearance_y: 1.0, clearance_width_m: 1.8, clearance_depth_m: 2.7,
}
const WARDROBE: DemoLayoutObject = {
  kind: 'WARDROBE', room_id: 'MASTER', x: 3.0, y: 3.7, width_m: 1.8, depth_m: 0.6, rotation_deg: 180.0,
  clearance_x: 3.0, clearance_y: 3.1, clearance_width_m: 1.8, clearance_depth_m: 1.2,
}

describe('InteriorLayout', () => {
  it('renders exactly one symbol per object, at the object\'s own footprint', () => {
    const { container } = inSvg(<InteriorLayout objects={[BED, WARDROBE]} />)
    expect(container.querySelectorAll('.demo-layout-object')).toHaveLength(2)

    // the symbol's own outer rectangle IS the placed footprint — never resized to suit a glyph
    const bedRect = container.querySelector('.demo-layout-object--bed rect')!
    expect(bedRect.getAttribute('x')).toBe('3')
    expect(bedRect.getAttribute('y')).toBe('1')
    expect(bedRect.getAttribute('width')).toBe('1.8')
    expect(bedRect.getAttribute('height')).toBe('2')
  })

  it('identifies each object by its own kind, never a decorative guess', () => {
    const { container } = inSvg(<InteriorLayout objects={[WARDROBE]} />)
    const group = container.querySelector('.demo-layout-object--wardrobe')!
    expect(group.getAttribute('data-kind')).toBe('WARDROBE')
    expect(group.querySelector('title')!.textContent).toBe('ארון')
  })

  it('prints no text on the drawing — the audit measured every text collision as a fixture label', () => {
    const { container } = inSvg(<InteriorLayout objects={[BED, WARDROBE]} />)
    expect(container.querySelectorAll('text')).toHaveLength(0)
  })

  it('keeps every symbol inside the footprint the backend placed', () => {
    const { container } = inSvg(<InteriorLayout objects={[BED, WARDROBE]} />)
    for (const obj of [BED, WARDROBE]) {
      const g = container.querySelector(`.demo-layout-object--${obj.kind.toLowerCase()}`)!
      for (const shape of g.querySelectorAll('rect, ellipse, circle, line')) {
        const nums = ['x', 'y', 'width', 'height', 'cx', 'cy', 'x1', 'y1', 'x2', 'y2']
          .map((a) => shape.getAttribute(a)).filter((v) => v !== null).map(Number)
        for (const n of nums) expect(Number.isFinite(n)).toBe(true)
      }
      const outer = g.querySelector('rect')!
      expect(Number(outer.getAttribute('x'))).toBeGreaterThanOrEqual(obj.x - 1e-9)
      expect(Number(outer.getAttribute('y'))).toBeGreaterThanOrEqual(obj.y - 1e-9)
      expect(Number(outer.getAttribute('width'))).toBeLessThanOrEqual(obj.width_m + 1e-9)
      expect(Number(outer.getAttribute('height'))).toBeLessThanOrEqual(obj.depth_m + 1e-9)
    }
  })

  it('draws nothing for an empty layout — no invented furniture', () => {
    const { container } = inSvg(<InteriorLayout objects={[]} />)
    expect(container.querySelectorAll('.demo-layout-object')).toHaveLength(0)
  })

  it('groups each object under its own kind class, so styling never has to branch on strings', () => {
    const { container } = inSvg(<InteriorLayout objects={[BED]} />)
    expect(container.querySelector('.demo-layout-object--bed')).not.toBeNull()
  })
})
