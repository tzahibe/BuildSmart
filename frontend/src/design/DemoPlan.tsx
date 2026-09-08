import type { DemoDesign } from './demoDesign'
import './DemoPlan.css'

/** THE DEMO RENDERER — presentation only.
 *
 * Every architectural fact drawn here is read directly off `DemoDesign`, which the backend
 * produced and validated (C1–C13). This component decides NOTHING architectural: not where a door
 * is, not whether two spaces are open to each other, not where a window goes, not what is
 * reachable. If a fact is not on the object, it is not drawn.
 *
 * Wall weight follows the backend's own construction/context facts rather than a guess:
 * an exterior wall is heavy, an RC safe-room wall is heavier and coloured, a partition is light,
 * and an `OPEN` boundary is drawn as a deliberate absence. */

const PAD_M = 1.5

/** Exported so `PlanLegend` swatches are drawn from the SAME values as the plan itself — a legend
 * that keeps its own copy of the colours is a legend that eventually lies about the drawing. */
export const WALL_STYLE: Record<string, { color: string; width: number }> = {
  RC_SAFE_ROOM: { color: '#b03a2e', width: 0.3 },
  STRUCTURAL: { color: '#1a1a1a', width: 0.26 },
  STANDARD_PARTITION: { color: '#8b939c', width: 0.1 },
}

export const EXTERIOR_WALL_STYLE = { color: '#1a1a1a', width: 0.26 }

export function wallStyle(construction: string, context: string) {
  if (construction === 'RC_SAFE_ROOM') return WALL_STYLE.RC_SAFE_ROOM
  if (context === 'EXTERIOR') return EXTERIOR_WALL_STYLE
  return WALL_STYLE[construction] ?? WALL_STYLE.STANDARD_PARTITION
}

function DemoPlan({ design }: { design: DemoDesign }) {
  const { plot, footprint } = design
  const viewBox = `${plot.x - PAD_M} ${plot.y - PAD_M} ${plot.width_m + PAD_M * 2} ${plot.depth_m + PAD_M * 2}`

  return (
    <svg className="demo-plan" viewBox={viewBox} role="img" aria-label="תוכנית אדריכלית">
      {/* Site context — all authoritative. */}
      <rect x={plot.x} y={plot.y} width={plot.width_m} height={plot.depth_m} className="demo-plot" />
      {design.garden.map((g, i) => (
        <rect key={`garden-${i}`} x={g.x} y={g.y} width={g.width_m} height={g.depth_m} className="demo-garden" />
      ))}
      <rect
        x={design.entrance_walk.x} y={design.entrance_walk.y}
        width={design.entrance_walk.width_m} height={design.entrance_walk.depth_m}
        className="demo-walk"
      />
      {design.parking.map((p, i) => (
        <g key={`parking-${i}`}>
          <rect x={p.x} y={p.y} width={p.width_m} height={p.depth_m} className="demo-parking" />
          <text x={p.x + p.width_m / 2} y={p.y + p.depth_m / 2} className="demo-parking-label">P</text>
        </g>
      ))}

      <rect x={footprint.x} y={footprint.y} width={footprint.width_m} height={footprint.depth_m} className="demo-footprint" />

      {/* Rooms: label + authoritative area. */}
      {design.rooms.map((room) => (
        <g key={room.id}>
          <text x={room.x + room.width_m / 2} y={room.y + room.depth_m / 2 - 0.25} className="demo-room-name">
            {room.name}
          </text>
          <text x={room.x + room.width_m / 2} y={room.y + room.depth_m / 2 + 0.55} className="demo-room-area">
            {room.area_m2.toFixed(1)} מ״ר
          </text>
        </g>
      ))}

      {/* Walls, weighted by the backend's construction/context facts. An OPEN interface has no
          wall segment at all, so open-plan reads as one continuous space by construction. */}
      {design.walls.map((wall, i) => {
        const style = wallStyle(wall.construction, wall.boundary_context)
        const [x1, y1, x2, y2] =
          wall.orientation === 'vertical'
            ? [wall.coord, wall.start, wall.coord, wall.end]
            : [wall.start, wall.coord, wall.end, wall.coord]
        return (
          <line
            key={`wall-${i}`} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={style.color} strokeWidth={style.width} strokeLinecap="butt"
          />
        )
      })}

      {/* Doors: position, width and orientation all from the backend. */}
      {design.doors.map((door, i) => {
        const half = door.width_m / 2
        const [x1, y1, x2, y2] =
          door.orientation === 'vertical'
            ? [door.x, door.y - half, door.x, door.y + half]
            : [door.x - half, door.y, door.x + half, door.y]
        return (
          <line
            key={`door-${i}`} x1={x1} y1={y1} x2={x2} y2={y2}
            className={door.is_entrance ? 'demo-door demo-door--entrance' : 'demo-door'}
          />
        )
      })}

      {/* Windows: only where the backend says one exists. */}
      {design.windows.map((window, i) => {
        const half = window.width_m / 2
        const vertical = window.side === 'E' || window.side === 'W'
        const [x1, y1, x2, y2] = vertical
          ? [window.x, window.y - half, window.x, window.y + half]
          : [window.x - half, window.y, window.x + half, window.y]
        return <line key={`window-${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className="demo-window" />
      })}
    </svg>
  )
}

export default DemoPlan
