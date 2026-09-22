import { footprintsOf, type DemoDesign, type DemoRect } from './demoDesign'
import { CompassRose } from './CompassRose'
import { roomLabelLayout } from './demoRoomLabel'
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

/** The compass rose is drawn about 1 m across at scale 1 — right for a building-sized frame, a speck
 * on a site-sized one. It grows with the frame's shorter side, and sits inset from the top-right
 * corner by its own half-size so it stays inside the frame at any scale. */
const COMPASS_FRAME_SHARE = 1 / 14
const COMPASS_HALF_SIZE_M = 0.85

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
  const { plot } = design
  // The wings, not the bounding box — the same frame for one wing; for an L the crook stays inside.
  const subjects: DemoRect[] = [...footprintsOf(design), design.entrance_walk, ...design.parking]

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

/** Architecture A spike (Issue #107): a merged room's own label centres on its polygon's AREA
 *  centroid, not its bounding-box centre — the bbox centre of an L can land in the room's own
 *  crook, outside the room entirely. Standard shoelace-formula polygon centroid; falls back to
 *  the plain vertex average for a degenerate (near-zero-area) polygon. */
function polygonCentroid(points: [number, number][]): { x: number; y: number } {
  let area = 0, cx = 0, cy = 0
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i]
    const [x1, y1] = points[(i + 1) % points.length]
    const cross = x0 * y1 - x1 * y0
    area += cross
    cx += (x0 + x1) * cross
    cy += (y0 + y1) * cross
  }
  area /= 2
  if (Math.abs(area) < 1e-9) {
    const n = points.length
    return { x: points.reduce((s, p) => s + p[0], 0) / n, y: points.reduce((s, p) => s + p[1], 0) / n }
  }
  return { x: cx / (6 * area), y: cy / (6 * area) }
}

/** Which way the arc turns, so it sweeps the quarter the leaf actually travels through rather than
 *  the opposite one. The cross product of (closed leaf) x (open leaf) about the hinge gives it. */
function sweep(hx: number, hy: number, far: { x: number; y: number },
               leaf: { x: number; y: number }): 0 | 1 {
  const cross = (far.x - hx) * (leaf.y - hy) - (far.y - hy) * (leaf.x - hx)
  return cross > 0 ? 1 : 0
}

/** `streetFacingSide` is the plot edge the person said faces the street. This drawing is STREET-UP by
 * construction — the backend puts the street, the parking bays and the entrance walk along `y = 0`
 * (`vertical_slice/site.py`) — which is what makes a compass truthful here and nowhere else in the
 * app. Omitted (a thumbnail, or a caller without the site): no compass is drawn. */
function DemoPlan({ design, streetFacingSide }: { design: DemoDesign; streetFacingSide?: string | null }) {
  const { plot } = design
  const viewBox = planViewBox(design)
  const [frameX, frameY, frameW, frameH] = viewBox.split(' ').map(Number)
  const compassScale = Math.max(1, Math.min(frameW, frameH) * COMPASS_FRAME_SHARE)
  const compassInset = COMPASS_HALF_SIZE_M * compassScale

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

      {/* The footprint is its WINGS — one rectangle each. A one-wing house draws exactly the one
          rectangle it always did; an L draws two and leaves the crook to the garden. */}
      {footprintsOf(design).map((wing, i) => (
        <rect key={`footprint-${i}`} x={wing.x} y={wing.y} width={wing.width_m} height={wing.depth_m} className="demo-footprint" />
      ))}

      {/* FLEX is not a room anyone asked for — it is the honest remainder when the requested
          built area exceeds what the room programme can responsibly use. Filled distinctly so it
          reads as "unallocated," never mistaken for a room the plan forgot to name. */}
      {design.rooms.filter((room) => room.type === 'FLEX').map((room) => (
        <rect key={`flex-${room.id}`} x={room.x} y={room.y}
              width={room.gross_width_m} height={room.gross_depth_m}
              className="demo-room-flex" />
      ))}

      {/* Architecture A spike (Issue #107): a merged room's own outer boundary, drawn as a real
          SVG polygon — additive, alongside every other room's existing rectangle (drawn instead
          via `design.walls`' own line segments, which the merge's wall-removal already makes
          read as one continuous room with no extra code here). Absent/`null` for every ordinary
          room, so this block draws nothing at all with the flag off. */}
      {design.rooms.filter((room) => room.polygon_m && room.polygon_m.length > 0).map((room) => (
        <polygon
          key={`merged-${room.id}`}
          points={room.polygon_m!.map(([px, py]) => `${px},${py}`).join(' ')}
          className="demo-room-merged"
        />
      ))}

      {/* Rooms: name, realized NET dimensions, authoritative NET area. The label centres on the
          room's GROSS box — the rectangle the walls actually draw — while the printed numbers are
          the usable (net) triple, so what's printed always multiplies out to the printed area.
          A merged room (Issue #107) centres on its own polygon's AREA CENTROID instead — its
          bounding-box centre can land in the room's own crook, outside the room. */}
      {design.rooms.map((room) => {
        const centroid = room.polygon_m && room.polygon_m.length > 0 ? polygonCentroid(room.polygon_m) : null
        const cx = centroid ? centroid.x : room.x + room.gross_width_m / 2
        const cy = centroid ? centroid.y : room.y + room.gross_depth_m / 2
        const layout = roomLabelLayout(room)
        return (
          <text
            key={room.id}
            className="demo-room-label"
            transform={layout.rotated ? `rotate(-90 ${cx} ${cy})` : undefined}
          >
            {layout.lines.map((line) => (
              <tspan
                key={line.kind}
                x={cx}
                y={cy + line.dy}
                className={`demo-room-${line.kind}`}
                style={{ fontSize: line.fontSize }}
              >
                {line.segments.map((segment, i) =>
                  segment.isolate ? (
                    <tspan key={i} className="demo-room-dim-pair" direction="ltr" unicodeBidi="isolate">
                      {segment.text}
                    </tspan>
                  ) : (
                    segment.text
                  ),
                )}
              </tspan>
            ))}
          </text>
        )
      })}

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
          "אין דבר כזה קיר פתוח לחדרים, אלא דלתות". A CASED_OPENING is the one exception: it is
          still a real interruption in the wall (the door line below draws that), but there is no
          leaf and no arc, because the backend declared this opening to have no door hardware at
          all — see `_build_access` in concept_generator.py for why the living room's entrance is
          always one of these.

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
        const hasLeaf = door.kind !== 'CASED_OPENING'

        let leaf: { x: number; y: number } | null = null
        if (room && hasLeaf) {
          // Perpendicular to the wall, toward the room's own side of it — the room's GROSS
          // (built) centre, since the door sits on the gross rectangle's own boundary.
          const inward = vertical
            ? Math.sign(room.x + room.gross_width_m / 2 - door.x)
            : Math.sign(room.y + room.gross_depth_m / 2 - door.y)
          leaf = vertical
            ? { x: hx + inward * door.width_m, y: hy }
            : { x: hx, y: hy + inward * door.width_m }
        }

        // The far jamb — where the arc ends, and where the leaf would lie when closed.
        const far = vertical
          ? { x: door.x, y: hy === y1 ? y2 : y1 }
          : { x: hx === x1 ? x2 : x1, y: door.y }

        // A cased opening has no leaf to mark its bounds, so short jamb ticks — perpendicular to
        // the opening, at each end — stand in for the door symbol an architect would otherwise
        // draw there.
        const jamb = 0.12
        const jambDx = vertical ? jamb : 0
        const jambDy = vertical ? 0 : jamb

        return (
          <g key={`door-${i}`}>
            {/* the opening itself: the wall does not run through here */}
            <line x1={x1} y1={y1} x2={x2} y2={y2}
                  className={
                    door.is_entrance ? 'demo-door demo-door--entrance'
                      : hasLeaf ? 'demo-door'
                      : 'demo-door demo-door--cased'
                  } />
            {leaf ? (
              <>
                <path
                  d={`M ${far.x} ${far.y} A ${door.width_m} ${door.width_m} 0 0 ${
                    sweep(hx, hy, far, leaf)} ${leaf.x} ${leaf.y}`}
                  className="demo-door-arc"
                />
                <line x1={hx} y1={hy} x2={leaf.x} y2={leaf.y} className="demo-door-leaf" />
              </>
            ) : !hasLeaf && !door.is_entrance ? (
              <>
                <line x1={x1 - jambDx} y1={y1 - jambDy} x2={x1 + jambDx} y2={y1 + jambDy}
                      className="demo-door-jamb" />
                <line x1={x2 - jambDx} y1={y2 - jambDy} x2={x2 + jambDx} y2={y2 + jambDy}
                      className="demo-door-jamb" />
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

      <CompassRose
        streetFacingSide={streetFacingSide}
        cx={frameX + frameW - compassInset}
        cy={frameY + compassInset}
        scale={compassScale}
      />
    </svg>
  )
}

export default DemoPlan
