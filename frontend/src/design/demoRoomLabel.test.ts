import { describe, expect, it } from 'vitest'
import { roomLabelLayout } from './demoRoomLabel'
import type { DemoRoom } from './demoDesign'

function room(width_m: number, depth_m: number, name = 'חדר שינה'): DemoRoom {
  return { id: 'R', type: 'BEDROOM', name, x: 0, y: 0, width_m, depth_m, area_m2: 11.8, walls: {} }
}

describe('roomLabelLayout', () => {
  it('stacks name, realized dimensions and area for an ordinary room', () => {
    const { lines, rotated } = roomLabelLayout(room(3.2, 3.7))
    expect(rotated).toBe(false)
    expect(lines.map((l) => l.text)).toEqual(['חדר שינה', '3.20 × 3.70 מ׳', '11.8 מ״ר'])
    // Lines run top to bottom and are centred on the room.
    expect(lines[0].dy).toBeLessThan(lines[1].dy)
    expect(lines[1].dy).toBeLessThan(lines[2].dy)
    const top = lines[0].dy - lines[0].fontSize / 2
    const bottom = lines[2].dy + lines[2].fontSize / 2
    expect(top + bottom).toBeCloseTo(0, 5)
  })

  it('writes the rectangle as realized, not a rounded template size', () => {
    const { lines } = roomLabelLayout(room(6.15, 5.75, 'סלון'))
    expect(lines[1].text).toBe('6.15 × 5.75 מ׳')
  })

  it('collapses dimensions and area to one line in a room too shallow for three', () => {
    const { lines, rotated } = roomLabelLayout(room(4.25, 1.2, 'שירותים'))
    expect(rotated).toBe(false)
    expect(lines.map((l) => l.kind)).toEqual(['name', 'compact'])
    expect(lines[1].text).toBe('4.25 × 1.20 מ׳ · 11.8 מ״ר')
  })

  it('turns a corridor label sideways rather than shrinking it to nothing', () => {
    const { lines, rotated } = roomLabelLayout(room(1.4, 12, 'מסדרון'))
    expect(rotated).toBe(true)
    expect(lines.every((l) => l.fontSize >= 0.3)).toBe(true)
  })

  it('never shrinks below the readable floor even when the room cannot hold the label', () => {
    const { lines } = roomLabelLayout(room(1.0, 1.0))
    expect(Math.min(...lines.map((l) => l.fontSize))).toBeGreaterThanOrEqual(0.4 * 0.55 - 1e-9)
  })
})
