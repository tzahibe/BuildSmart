import { footprintsOf, type DemoDesign, type DemoRect } from './demoDesign'
import { CompassRose } from './CompassRose'
import { DoorSymbol } from '../components/plan/DoorSymbol'
import { Walls, WALL_STYLE, EXTERIOR_WALL_STYLE, wallStyle } from '../components/plan/Walls'
import { InteriorLayout } from '../components/plan/InteriorLayout'
import { roomLabelLayout } from './demoRoomLabel'
import './DemoPlan.css'

/** THE DEMO RENDERER — presentation only.
 *
 * Every architectural fact drawn here is read directly off `DemoDesign`, which the backend
 * produced and validated (C1–C13). This component decides NOTHING architectural: not where a door
 * is, not whether two spaces are open to each other, not where a window goes, not what is
 * reachable. If a fact is not on the object, it is not drawn.
 *
 * Wall weight follows the backend's own semantic class and real thickness (Issue #45) — an
 * exterior wall is heavy, an RC/PROTECTED safe-room wall is heavier and coloured, a partition is
 * light, and an `OPEN` boundary is drawn as a deliberate absence. The drawing itself lives in
 * `components/plan/Walls.tsx`; `WALL_STYLE`/`EXTERIOR_WALL_STYLE`/`wallStyle` are re-exported here
 * so `PlanLegend`'s swatches stay sourced from the SAME values as the plan. */
export { WALL_STYLE, EXTERIOR_WALL_STYLE, wallStyle }

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

      {/* Rooms: name, realized NET dimensions, authoritative NET area. The label centres on the
          room's GROSS box — the rectangle the walls actually draw — while the printed numbers are
          the usable (net) triple, so what's printed always multiplies out to the printed area. */}
      {design.rooms.map((room) => {
        const cx = room.x + room.gross_width_m / 2
        const cy = room.y + room.gross_depth_m / 2
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

      {/* Walls, weighted by the backend's own semantic class and real thickness (Issue #45). An
          OPEN interface has no wall segment at all, so open-plan reads as one continuous space by
          construction. */}
      <Walls walls={design.walls} />

      {/* Engine-placed semantic layout objects (Issue #39) — drawn under the doors/windows so a
          door's swing arc always stays legible over any furniture near it. */}
      <InteriorLayout objects={design.layout ?? []} />

      {/* DOORS, drawn as an architect draws them: the wall is interrupted, a leaf stands open at
          90°, and an arc sweeps the space it needs. The gap alone read as a wall that simply stops —
          "אין דבר כזה קיר פתוח לחדרים, אלא דלתות". A CASED_OPENING is the one exception: it is
          still a real interruption in the wall, but there is no leaf and no arc, because the
          backend declared this opening to have no door hardware at all — see `_build_access` in
          concept_generator.py for why the living room's entrance is always one of these.

          Every fact here comes from the backend (`swings_into`/`hinge_x`/`hinge_y`/`swing_deg`,
          Issue #38) — `DoorSymbol` does the trigonometry and nothing else, with no room lookup of
          its own, which is the same boundary that stopped this renderer inventing doors in the
          first place. */}
      {design.doors.map((door, i) => (
        <DoorSymbol
          key={`door-${i}`}
          door={{
            x: door.x, y: door.y, width_m: door.width_m, orientation: door.orientation,
            hinge_x: door.hinge_x, hinge_y: door.hinge_y, swing_deg: door.swing_deg,
            is_entrance: door.is_entrance, hasLeaf: door.kind !== 'CASED_OPENING',
          }}
        />
      ))}

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
