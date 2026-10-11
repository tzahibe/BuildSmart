import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { DoorSymbol, doorSymbolGeometry, type DoorSymbolFields } from './DoorSymbol'

/** Contract test (Issue #38, AC-3): `DoorSymbol` draws the leaf and its swing arc from
 * `hinge_x`/`hinge_y`/`swing_deg` alone — never from a room lookup or an inferred direction. A
 * fixed fixture, an exact expected geometry: this pins the contract, not just "something rendered". */
const FIXTURE: DoorSymbolFields = {
  x: 8, y: 8, width_m: 0.9, orientation: 'vertical',
  hinge_x: 8, hinge_y: 8 - 0.45, swing_deg: 180, hasLeaf: true,
}

describe('doorSymbolGeometry', () => {
  it('places the leaf tip purely from hinge_x/hinge_y/swing_deg, at radius width_m', () => {
    const { hx, hy, leaf } = doorSymbolGeometry(FIXTURE)
    expect(hx).toBe(8)
    expect(hy).toBeCloseTo(7.55)
    // swing_deg=180 -> the leaf tip is width_m to the WEST of the hinge, same y.
    expect(leaf).not.toBeNull()
    expect(leaf!.x).toBeCloseTo(8 - 0.9)
    expect(leaf!.y).toBeCloseTo(7.55)
  })

  it('the far jamb is the OTHER end of the opening from the hinge', () => {
    const { y1, y2, far } = doorSymbolGeometry(FIXTURE)
    expect(far.x).toBe(8)
    expect(far.y).toBe(y2)
    expect(far.y).not.toBe(y1)
  })

  it('draws no leaf when swing_deg is absent — an unknown swing is drawn as unknown', () => {
    const { leaf } = doorSymbolGeometry({ ...FIXTURE, swing_deg: undefined })
    expect(leaf).toBeNull()
  })

  it('draws no leaf for a door with no leaf hardware (a cased opening), even with swing_deg set', () => {
    const { leaf } = doorSymbolGeometry({ ...FIXTURE, hasLeaf: false })
    expect(leaf).toBeNull()
  })

  it('falls back to the opening\'s own jamb when hinge_x/hinge_y are absent', () => {
    const { x1, hx, hy } = doorSymbolGeometry({ ...FIXTURE, hinge_x: undefined, hinge_y: undefined })
    expect(hx).toBe(x1)
    expect(hy).toBe(FIXTURE.y - FIXTURE.width_m / 2)
  })
})

describe('DoorSymbol', () => {
  it('renders exactly one leaf line and one arc for an ordinary door', () => {
    const { container } = render(<DoorSymbol door={FIXTURE} />)
    expect(container.querySelectorAll('.demo-door-leaf')).toHaveLength(1)
    expect(container.querySelectorAll('.demo-door-arc')).toHaveLength(1)
    expect(container.querySelectorAll('.demo-door-jamb')).toHaveLength(0)

    const leafLine = container.querySelector('.demo-door-leaf')!
    expect(leafLine.getAttribute('x1')).toBe('8')
    expect(Number(leafLine.getAttribute('y1'))).toBeCloseTo(7.55)
    expect(Number(leafLine.getAttribute('x2'))).toBeCloseTo(7.1)
    expect(Number(leafLine.getAttribute('y2'))).toBeCloseTo(7.55)
  })

  it('renders jamb ticks, never a leaf or arc, for a cased opening', () => {
    const { container } = render(<DoorSymbol door={{ ...FIXTURE, hasLeaf: false }} />)
    expect(container.querySelectorAll('.demo-door-leaf')).toHaveLength(0)
    expect(container.querySelectorAll('.demo-door-arc')).toHaveLength(0)
    expect(container.querySelectorAll('.demo-door-jamb')).toHaveLength(2)
    expect(container.querySelector('.demo-door--cased')).not.toBeNull()
  })

  it('renders neither a leaf/arc nor jamb ticks for a real door missing swing_deg', () => {
    const { container } = render(<DoorSymbol door={{ ...FIXTURE, swing_deg: undefined }} />)
    expect(container.querySelectorAll('.demo-door-leaf')).toHaveLength(0)
    expect(container.querySelectorAll('.demo-door-arc')).toHaveLength(0)
    expect(container.querySelectorAll('.demo-door-jamb')).toHaveLength(0)
  })

  it('never draws jamb ticks for the entrance door, even without a leaf', () => {
    const { container } = render(
      <DoorSymbol door={{ ...FIXTURE, hasLeaf: false, is_entrance: true }} />,
    )
    expect(container.querySelectorAll('.demo-door-jamb')).toHaveLength(0)
    expect(container.querySelector('.demo-door--entrance')).not.toBeNull()
  })
})
