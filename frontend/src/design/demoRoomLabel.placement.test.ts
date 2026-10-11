/** Concept Plan Communication Pass — deterministic room-label placement.
 *
 * The audit measured 85 room labels sitting on a furniture symbol and 120 on a door's swept
 * quarter. The label now slides inside the room to the clearest position. These tests pin the
 * properties that matter: it is deterministic, it never moves the ROOM, it prefers the centre when
 * nothing is in the way, and a room too small to hold the block anywhere still gets its label.
 */
import { describe, expect, it } from 'vitest'
import { doorSwingObstacle, roomLabelLayout, type LabelObstacle } from './demoRoomLabel'
import type { DemoRoom } from './demoDesign'

function room(overrides: Partial<DemoRoom> = {}): DemoRoom {
  return {
    id: 'MASTER', type: 'MASTER_BEDROOM', name: 'חדר הורים',
    x: 0, y: 0, width_m: 4, depth_m: 5, area_m2: 20,
    gross_width_m: 4, gross_depth_m: 5,
    walls: {},
    ...overrides,
  } as DemoRoom
}

describe('room label placement', () => {
  it('stays centred when nothing is in the way', () => {
    const layout = roomLabelLayout(room(), [])
    expect(layout.dx ?? 0).toBe(0)
    expect(layout.dy ?? 0).toBe(0)
  })

  it('moves off a furniture symbol that covers the centre', () => {
    const bed: LabelObstacle = { x: 0.5, y: 1.6, w: 3, h: 1.8 }   // straddles the room's centre
    const layout = roomLabelLayout(room(), [bed])
    expect(Math.abs(layout.dx ?? 0) + Math.abs(layout.dy ?? 0)).toBeGreaterThan(0)
  })

  it('is deterministic — the same room and obstacles always give the same offset', () => {
    const obstacles: LabelObstacle[] = [{ x: 0.5, y: 1.6, w: 3, h: 1.8 }]
    const a = roomLabelLayout(room(), obstacles)
    const b = roomLabelLayout(room(), obstacles)
    expect([a.dx, a.dy, a.rotated]).toEqual([b.dx, b.dy, b.rotated])
  })

  it('does not depend on the order the obstacles arrive in', () => {
    const o1: LabelObstacle = { x: 0.2, y: 0.2, w: 1.5, h: 1.2 }
    const o2: LabelObstacle = { x: 2.0, y: 3.2, w: 1.5, h: 1.2 }
    const a = roomLabelLayout(room(), [o1, o2])
    const b = roomLabelLayout(room(), [o2, o1])
    expect([a.dx, a.dy]).toEqual([b.dx, b.dy])
  })

  it('keeps the label inside the room it belongs to', () => {
    const covered: LabelObstacle[] = [{ x: 0, y: 0, w: 4, h: 2.4 }]
    const r = room()
    const layout = roomLabelLayout(r, covered)
    expect(Math.abs(layout.dy ?? 0)).toBeLessThanOrEqual(r.gross_depth_m / 2)
    expect(Math.abs(layout.dx ?? 0)).toBeLessThanOrEqual(r.gross_width_m / 2)
  })

  it('still labels a room far too small to dodge anything — it degrades, it never disappears', () => {
    const tiny = room({ id: 'WC', type: 'TOILET', name: 'שירותים', width_m: 1.1, depth_m: 1.3,
                        gross_width_m: 1.1, gross_depth_m: 1.3, area_m2: 1.4 })
    const layout = roomLabelLayout(tiny, [{ x: 0, y: 0, w: 1.1, h: 1.3 }])
    expect(layout.lines.length).toBeGreaterThan(0)
    expect(layout.lines[0].text).toContain('שירותים')
    expect(layout.dx ?? 0).toBe(0)
    expect(layout.dy ?? 0).toBe(0)
  })

  it('never changes the room geometry to make the label fit', () => {
    const r = room()
    const before = { ...r }
    roomLabelLayout(r, [{ x: 0, y: 0, w: 4, h: 5 }])
    expect(r).toEqual(before)
  })
})

describe('door swing obstacle', () => {
  it('is the quarter the leaf actually sweeps, from the engines own hinge and angle', () => {
    const box = doorSwingObstacle({ hinge_x: 2, hinge_y: 3, swing_deg: 0, width_m: 0.9 })!
    expect(box).toEqual({ x: 2, y: 3, w: 0.9, h: 0.9 })
    const back = doorSwingObstacle({ hinge_x: 2, hinge_y: 3, swing_deg: 180, width_m: 0.9 })!
    expect(back.x).toBeCloseTo(1.1, 6)
  })

  it('is absent when the engine did not decide a swing — never guessed', () => {
    expect(doorSwingObstacle({ width_m: 0.9 })).toBeNull()
    expect(doorSwingObstacle({ hinge_x: 1, width_m: 0.9 })).toBeNull()
  })
})
