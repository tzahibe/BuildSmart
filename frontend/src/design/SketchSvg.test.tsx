import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Room } from '../types'
import { twoRoomDesign } from './geometricDesign.fixtures'
import SketchSvg from './SketchSvg'

/** Two rooms sharing a long wall, in the LEGACY `Room[]` shape — long/adjacent enough that the
 * pre-existing (and still-used-for-compatibility) shared-wall-length heuristic in `LegacyFloorPlan`
 * would draw a door for them. Used to prove that heuristic is still reachable for old payloads, and
 * that it is NEVER reachable once a matching `geometricDesign` is supplied for the same floor. */
function legacyAdjacentRooms(): Room[] {
  return [
    { type: 'living_room', floor: 1, area_m2: 12, x: 0, y: 0, width_m: 3, depth_m: 4, source: null },
    { type: 'bedroom', floor: 1, area_m2: 12, x: 3, y: 0, width_m: 3, depth_m: 4, source: null },
  ]
}

describe('SketchSvg', () => {
  it('falls back to the legacy renderer when no geometricDesign is supplied (old design payload)', () => {
    const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={null} />)

    // Legacy path is reachable and behaves exactly as before: it still infers an interior door from
    // the long shared wall, plus an exterior entry door (living_room touches the footprint's west
    // edge) — this is the isolated, unchanged compatibility fallback, not the new contract.
    expect(container.querySelectorAll('.sketch-svg-door')).toHaveLength(2)
    expect(container.querySelectorAll('.arch-door')).toHaveLength(0)
  })

  it('uses the authoritative ArchitecturalFloorPlan renderer once geometricDesign matches the active floor', () => {
    const design = twoRoomDesign({ withDoor: false })
    const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={design} />)

    // No door in `design.doors` for these two adjacent rooms -> none rendered, even though the same
    // two rooms would have produced a legacy inferred door (see the test above).
    expect(container.querySelectorAll('.arch-door')).toHaveLength(0)
    expect(container.querySelectorAll('.sketch-svg-door')).toHaveLength(0)
    // The authoritative renderer's own wall/room markup is present.
    expect(container.querySelectorAll('.arch-wall-exterior').length).toBeGreaterThan(0)
  })

  it('still renders the authoritative door when geometricDesign supplies one', () => {
    const design = twoRoomDesign({ withDoor: true })
    const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={design} />)

    expect(container.querySelectorAll('.arch-door')).toHaveLength(1)
  })

  it('renders the empty state for a project with no rooms yet, regardless of geometricDesign', () => {
    const { getByText } = render(<SketchSvg rooms={[]} geometricDesign={null} />)
    expect(getByText('אין עדיין נתוני תכנון להצגה')).toBeInTheDocument()
  })
})
