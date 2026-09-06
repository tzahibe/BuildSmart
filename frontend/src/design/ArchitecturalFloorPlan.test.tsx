import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ArchitecturalFloorPlan from './ArchitecturalFloorPlan'
import { twoRoomDesign } from './geometricDesign.fixtures'

describe('ArchitecturalFloorPlan', () => {
  it('renders a door only when the backend supplies a DoorConnection', () => {
    const { container } = render(<ArchitecturalFloorPlan design={twoRoomDesign({ withDoor: true })} />)

    const doors = container.querySelectorAll('.arch-door')
    expect(doors).toHaveLength(1)
    expect(doors[0].getAttribute('data-door-id')).toBe('DOOR_LIVING_ROOM_BEDROOM')
  })

  it('never renders a door for a plain adjacency with no DoorConnection', () => {
    // Same two adjacent rooms/shared wall as the door-rendering case above, but `doors: []` — this is
    // the exact scenario the removed "shared wall long enough -> hasDoor" inference used to invent a
    // door for. The authoritative renderer must not.
    const { container } = render(<ArchitecturalFloorPlan design={twoRoomDesign({ withDoor: false })} />)

    expect(container.querySelectorAll('.arch-door')).toHaveLength(0)

    // The shared wall itself must still be drawn, as a single uninterrupted segment (no gap invented
    // where no door exists).
    const interiorWallLines = container.querySelectorAll('.arch-wall-interior')
    expect(interiorWallLines).toHaveLength(1)
    expect(interiorWallLines[0].getAttribute('y1')).toBe('0')
    expect(interiorWallLines[0].getAttribute('y2')).toBe('4')
  })

  it('renders every supplied DoorConnection exactly once, each cutting its own wall gap', () => {
    const design = twoRoomDesign({ withDoor: true })
    // Add a second room + a second door on a different wall, to confirm doors aren't deduplicated
    // or dropped once there's more than one.
    design.rooms.push({
      id: 'KITCHEN',
      type: 'kitchen',
      floor: 1,
      x: 0,
      y: 4,
      width_m: 6,
      depth_m: 2,
      area_m2: 12,
      is_circulation: false,
      source: null,
    })
    design.walls.push({
      id: 'INT_LIVING_ROOM_KITCHEN',
      kind: 'interior',
      orientation: 'horizontal',
      coord: 4,
      start: 0,
      end: 3,
      room_ids: ['LIVING_ROOM', 'KITCHEN'],
    })
    design.doors.push({
      id: 'DOOR_LIVING_ROOM_KITCHEN',
      wall_id: 'INT_LIVING_ROOM_KITCHEN',
      orientation: 'horizontal',
      coord: 4,
      center: 1.5,
      width_m: 0.9,
      room_ids: ['LIVING_ROOM', 'KITCHEN'],
      provenance: 'direct_access_proxy',
      note: 'test fixture door',
    })

    const { container } = render(<ArchitecturalFloorPlan design={design} />)

    const doorIds = [...container.querySelectorAll('.arch-door')].map((el) => el.getAttribute('data-door-id'))
    expect(doorIds.sort()).toEqual(['DOOR_LIVING_ROOM_BEDROOM', 'DOOR_LIVING_ROOM_KITCHEN'])

    // Each of the two doored walls is split into two segments (one on each side of its own gap) — 4
    // line elements total, none of them spanning across a door's opening.
    expect(container.querySelectorAll('.arch-wall-interior')).toHaveLength(4)
  })

  it('renders circulation styling only for rooms the backend flags as circulation', () => {
    // `render()`'s default queries search the whole document body, not just their own container — with
    // two renders live at once in this single test, scope explicitly via each result's own `container`.
    const withoutCirculation = render(<ArchitecturalFloorPlan design={twoRoomDesign({ circulation: false })} />)
    expect(withoutCirculation.container.querySelectorAll('.arch-circulation-overlay')).toHaveLength(0)
    expect(withoutCirculation.container.querySelector('[role="note"]')?.textContent).not.toMatch(/חלוקה/)

    const withCirculation = render(<ArchitecturalFloorPlan design={twoRoomDesign({ circulation: true })} />)
    expect(withCirculation.container.querySelectorAll('.arch-circulation-overlay')).toHaveLength(1)
    expect(withCirculation.container.querySelector('[role="note"]')?.textContent).toMatch(/חלוקה/)
  })

  it('derives the SVG viewBox from the footprint, not from room extents', () => {
    const design = twoRoomDesign()
    const { container } = render(<ArchitecturalFloorPlan design={design} />)

    const svg = container.querySelector('svg')
    // SIDE_PAD_M=0.5, TOP_PAD_M=1.5, RIGHT_PAD_M=1.35 — see ArchitecturalFloorPlan.tsx.
    expect(svg?.getAttribute('viewBox')).toBe('-0.5 -1.5 7.85 6')
  })

  it('renders each room label and area', () => {
    const { getByText, getAllByText } = render(<ArchitecturalFloorPlan design={twoRoomDesign()} />)
    expect(getByText('סלון')).toBeInTheDocument()
    expect(getByText('חדר שינה')).toBeInTheDocument()
    // Both fixture rooms happen to share the same 3x4 / 12 m² dims — assert the area string appears
    // once per room, not that it's unique.
    expect(getAllByText(/12\.0 מ"ר/)).toHaveLength(2)
  })

  it('does not crash for a valid design with zero circulation area', () => {
    const design = twoRoomDesign({ circulation: false })
    expect(design.circulation_area_m2).toBe(0)
    expect(() => render(<ArchitecturalFloorPlan design={design} />)).not.toThrow()
  })
})
