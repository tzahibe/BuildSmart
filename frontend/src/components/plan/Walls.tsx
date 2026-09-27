import type { DemoWallSegment } from '../../design/demoDesign'

/** Every wall on a floor plan, weighted and coloured by the backend's own facts — never a
 * frontend guess. Issue #45: the backend's wall semantic model (`app.vertical_slice.walls`)
 * collapses `construction`/`boundary_context` into one `wall_class`
 * (EXTERIOR | INTERIOR | WET_SERVICE | PROTECTED) and reports the REAL solved `thickness_m`; this
 * component draws from those two fields when present. A `DemoWallSegment` built before this Issue
 * (a hand-made test fixture, or an older cached payload) carries neither — `wallStyle` falls back
 * to the legacy `construction`/`boundary_context` pair, exactly as it read before this Issue, so
 * nothing that predates it changes appearance. */

/** Colour by semantic class. Width, when a segment has no real `thickness_m`, falls back to the
 * same values the legacy table used — RC/PROTECTED and EXTERIOR read the same as before. */
export const WALL_CLASS_STYLE: Record<string, { color: string; width: number }> = {
  PROTECTED: { color: '#b03a2e', width: 0.3 },
  EXTERIOR: { color: '#1a1a1a', width: 0.26 },
  WET_SERVICE: { color: '#2e6fa0', width: 0.1 },
  INTERIOR: { color: '#8b939c', width: 0.1 },
}

/** Legacy construction/boundary_context styling — unchanged from before Issue #45. */
export const WALL_STYLE: Record<string, { color: string; width: number }> = {
  RC_SAFE_ROOM: { color: '#b03a2e', width: 0.3 },
  STRUCTURAL: { color: '#1a1a1a', width: 0.26 },
  STANDARD_PARTITION: { color: '#8b939c', width: 0.1 },
}

export const EXTERIOR_WALL_STYLE = { color: '#1a1a1a', width: 0.26 }

export function wallStyle(wall: DemoWallSegment): { color: string; width: number } {
  if (wall.wall_class) {
    const byClass = WALL_CLASS_STYLE[wall.wall_class] ?? WALL_CLASS_STYLE.INTERIOR
    return { color: byClass.color, width: wall.thickness_m ?? byClass.width }
  }
  if (wall.construction === 'RC_SAFE_ROOM') return WALL_STYLE.RC_SAFE_ROOM
  if (wall.boundary_context === 'EXTERIOR') return EXTERIOR_WALL_STYLE
  return WALL_STYLE[wall.construction] ?? WALL_STYLE.STANDARD_PARTITION
}

export function Walls({ walls }: { walls: DemoWallSegment[] }) {
  return (
    <>
      {walls.map((wall, i) => {
        const style = wallStyle(wall)
        const [x1, y1, x2, y2] =
          wall.orientation === 'vertical'
            ? [wall.coord, wall.start, wall.coord, wall.end]
            : [wall.start, wall.coord, wall.end, wall.coord]
        return (
          <line
            key={wall.id ?? `wall-${i}`} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={style.color} strokeWidth={style.width} strokeLinecap="butt"
          />
        )
      })}
    </>
  )
}

export default Walls
