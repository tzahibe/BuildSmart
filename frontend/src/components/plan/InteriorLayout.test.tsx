import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { InteriorLayout } from './InteriorLayout'
import type { DemoLayoutObject } from '../../design/demoDesign'

/** Contract test (Issue #39, AC-3): the frontend draws `DemoDesign.layout` AS-IS — one rectangle
 * per object, at the object's own coordinates, labelled with its own `kind` — never inventing,
 * repositioning, or dropping an object the backend placed. */

const BED: DemoLayoutObject = {
  kind: 'BED', room_id: 'MASTER', x: 3.0, y: 1.0, width_m: 1.8, depth_m: 2.0, rotation_deg: 0.0,
  clearance_x: 3.0, clearance_y: 1.0, clearance_width_m: 1.8, clearance_depth_m: 2.7,
}
const WARDROBE: DemoLayoutObject = {
  kind: 'WARDROBE', room_id: 'MASTER', x: 3.0, y: 3.7, width_m: 1.8, depth_m: 0.6, rotation_deg: 180.0,
  clearance_x: 3.0, clearance_y: 3.1, clearance_width_m: 1.8, clearance_depth_m: 1.2,
}

describe('InteriorLayout', () => {
  it('renders exactly one rect per object, at the object\'s own footprint', () => {
    const { container } = render(<InteriorLayout objects={[BED, WARDROBE]} />)
    const rects = container.querySelectorAll('.demo-layout-object-rect')
    expect(rects).toHaveLength(2)

    const bedRect = container.querySelector('.demo-layout-object--bed .demo-layout-object-rect')!
    expect(bedRect.getAttribute('x')).toBe('3')
    expect(bedRect.getAttribute('y')).toBe('1')
    expect(bedRect.getAttribute('width')).toBe('1.8')
    expect(bedRect.getAttribute('height')).toBe('2')
  })

  it('labels each object with its own kind, never a decorative guess', () => {
    const { container } = render(<InteriorLayout objects={[WARDROBE]} />)
    const label = container.querySelector('.demo-layout-object-label')!
    expect(label.textContent).toBe('WARDROBE')
  })

  it('draws nothing for an empty layout — no invented furniture', () => {
    const { container } = render(<InteriorLayout objects={[]} />)
    expect(container.querySelectorAll('.demo-layout-object')).toHaveLength(0)
  })

  it('groups each object under its own kind class, so styling never has to branch on strings', () => {
    const { container } = render(<InteriorLayout objects={[BED]} />)
    expect(container.querySelector('.demo-layout-object--bed')).not.toBeNull()
  })
})
