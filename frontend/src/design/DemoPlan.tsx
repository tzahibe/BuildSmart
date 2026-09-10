import type { DemoDesign, DemoRect } from './demoDesign'
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

/** How much surrounding site to keep around the building, as a share of its longest side. */
const CONTEXT_MARGIN_RATIO = 0.3

/** Frames the drawing on the BUILDING, not on the parcel.
 *
 * A 400 x 200 m plot holding a 19 x 10.5 m house is a legitimate site, and framing the parcel
 * makes the plan a stamp in a green field. The subject is the building plus the site work that
 * touches it (the entrance walk, the parking bays), padded with a margin proportional to the
 * building so the drawing reads at the same weight on any parcel. The frame is then clipped to
 * the parcel, so a plot barely larger than the house still shows the whole site. Everything
 * outside the frame — the rest of the garden — simply falls off the edges of the SVG. */
export function planViewBox(design: DemoDesign): string {
  const { plot, footprint } = design
  const subjects: DemoRect[] = [footprint, design.entrance_walk, ...design.parking]

  const minX = Math.min(...subjects.map((r) => r.x))
  const minY = Math.min(...subjects.map((r) => r.y))
  const maxX = Math.max(...subjects.map((r) => r.x + r.width_m))
  const maxY = Math.max(...subjects.map((r) => r.y + r.depth_m))

  const margin = Math.max(PAD_M, CONTEXT_MARGIN_RATIO * Math.max(maxX - minX, maxY - minY))

  const x0 = Math.max(minX - margin, plot.x - PAD_M)
  const y0 = Math.max(minY - margin, plot.y - PAD_M)
  const x1 = Math.min(maxX + margin, plot.x + plot.width_m + PAD_M)
  const y1 = Math.min(maxY + margin, plot.y + plot.depth_m + PAD_M)

  return `${x0} ${y0} ${x1 - x0} ${y1 - y0}`
}

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

/** Which way the arc turns, so it sweeps the quarter the leaf actually travels through rather than
 *  the opposite one. The cross product of (closed leaf) x (open leaf) about the hinge gives it. */
function sweep(hx: number, hy: number, far: { x: number; y: number },
               leaf: { x: number; y: number }): 0 | 1 {
  const cross = (far.x - hx) * (leaf.y - hy) - (far.y - hy) * (leaf.x - hx)
  return cross > 0 ? 1 : 0
}

function DemoPlan({ design }: { design: DemoDesign }) {
  const { plot, footprint } = design
  const viewBox = planViewBox(design)

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

      {/* FLEX is not a room anyone asked for — it is the honest remainder when the requested
          built area exceeds what the room programme can responsibly use. Filled distinctly so it
          reads as "unallocated," never mistaken for a room the plan forgot to name. */}
      {design.rooms.filter((room) => room.type === 'FLEX').map((room) => (
        <rect key={`flex-${room.id}`} x={room.x} y={room.y} width={room.width_m} height={room.depth_m}
              className="demo-room-flex" />
      ))}

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

      {/* DOORS, drawn as an architect draws them: the wall is interrupted, a leaf stands open at
          90°, and an arc sweeps the space it needs. The gap alone read as a wall that simply stops —
          "אין דבר כזה קיר פתוח לחדרים, אלא דלתות".

          Every fact here comes from the backend: where the opening is, which room the leaf swings
          into, and which jamb it hangs from. The renderer does the trigonometry and nothing else,
          which is the same boundary that stopped it inventing doors in the first place. */}
      {design.doors.map((door, i) => {
        const half = door.width_m / 2
        const vertical = door.orientation === 'vertical'
        const [x1, y1, x2, y2] = vertical
          ? [door.x, door.y - half, door.x, door.y + half]
          : [door.x - half, door.y, door.x + half, door.y]

        // The hinge is one end of the opening; the leaf swings from there into `swings_into`.
        const hx = door.hinge_x ?? x1
        const hy = door.hinge_y ?? y1
        const room = design.rooms.find((r) => r.id === door.swings_into)

        let leaf: { x: number; y: number } | null = null
        if (room) {
          // Perpendicular to the wall, toward the room's own side of it.
          const inward = vertical
            ? Math.sign(room.x + room.width_m / 2 - door.x)
            : Math.sign(room.y + room.depth_m / 2 - door.y)
          leaf = vertical
            ? { x: hx + inward * door.width_m, y: hy }
            : { x: hx, y: hy + inward * door.width_m }
        }

        // The far jamb — where the arc ends, and where the leaf would lie when closed.
        const far = vertical
          ? { x: door.x, y: hy === y1 ? y2 : y1 }
          : { x: hx === x1 ? x2 : x1, y: door.y }

        return (
          <g key={`door-${i}`}>
            {/* the opening itself: the wall does not run through here */}
            <line x1={x1} y1={y1} x2={x2} y2={y2}
                  className={door.is_entrance ? 'demo-door demo-door--entrance' : 'demo-door'} />
            {leaf ? (
              <>
                <path
                  d={`M ${far.x} ${far.y} A ${door.width_m} ${door.width_m} 0 0 ${
                    sweep(hx, hy, far, leaf)} ${leaf.x} ${leaf.y}`}
                  className="demo-door-arc"
                />
                <line x1={hx} y1={hy} x2={leaf.x} y2={leaf.y} className="demo-door-leaf" />
              </>
            ) : null}
          </g>
        )
      })}

      {/* Windows: only where the backend says one exists. */}
      {design.windows.map((window, i) => {
        const half = window.width_m / 2
        const vertical = window.side === 'E' || window.side === 'W'
        const [x1, y1, x2, y2] = vertical
          ? [window.x, window.y - half, window.x, window.y + half]
          : [window.x - half, window.y, window.x + half, window.y]
        // The width, written alongside — a drawing that shows an opening without its size is a
        // sketch. Offset outward from the wall so the number sits in the garden, not on a room.
        const outward = window.side === 'N' ? -0.45 : window.side === 'S' ? 0.55 : 0
        const sideways = window.side === 'W' ? -0.25 : window.side === 'E' ? 0.25 : 0
        return (
          <g key={`window-${i}`}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} className="demo-window" />
            <text
              x={window.x + sideways}
              y={window.y + outward}
              className="demo-window-label"
              transform={vertical ? `rotate(-90 ${window.x + sideways} ${window.y + outward})` : undefined}
            >
              {window.width_m.toFixed(2)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default DemoPlan
