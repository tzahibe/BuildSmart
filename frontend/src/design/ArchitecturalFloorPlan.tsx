import type { DoorConnection, GeometricDesign, Wall } from './geometricDesign'
import { roomLabel } from './roomLabel'
import './SketchSvg.css'
import './ArchitecturalFloorPlan.css'

interface ArchitecturalFloorPlanProps {
  design: GeometricDesign
}

const TOP_PAD_M = 1.5
const RIGHT_PAD_M = 1.35
const SIDE_PAD_M = 0.5
// Half-length of each door-opening "jamb tick" — a short mark perpendicular to the wall at each edge
// of the opening. See the module docstring below for why this, and not a swing arc, is what a door
// renders as here.
const JAMB_TICK_M = 0.12

/** Renders `GeometricDesign` — the backend's authoritative, already-solved geometry (see
 * `backend/app/geometry/geometric_design.py` and `design/geometricDesign.ts`) — as an architectural
 * floor plan: WALLS + OPENINGS, not colored rectangles with inferred borders.
 *
 * This component is a pure renderer. It reads `design.rooms`/`walls`/`doors`/`footprint` and draws
 * exactly what's there; it never computes adjacency, never decides a door exists, and never derives an
 * exterior boundary from room extents — all of that already happened once, authoritatively, on the
 * backend (see that module's docstring for exactly which already-computed fact backs each field). This
 * is the enforcement point for `frontend/src/design/SketchSvg.tsx`'s required invariant: RENDERED_DOOR
 * ⇔ BACKEND_DOOR_CONNECTION.
 *
 * **Door swing presentation** (BUILDSMART_ARCHITECTURAL_UI_V1 §5): the backend's `DoorConnection`
 * carries no swing/hinge direction — it's a proxy for "an opening of this width exists here," not a
 * modeled door leaf (see `DoorConnection.note`). Rather than invent a plausible-looking swing arc that
 * would silently read as authoritative floor-plan detail, doors render as a NEUTRAL opening: a gap in
 * the wall plus two short perpendicular "jamb tick" marks at the opening's edges (a standard drafting
 * convention for an unspecified/cased opening). This choice is presentation-only and never affects
 * `design.doors` itself or anything downstream of it.
 */
function ArchitecturalFloorPlan({ design }: ArchitecturalFloorPlanProps) {
  const { footprint, rooms, walls, doors } = design
  const maxX = footprint.width_m
  const maxDepth = footprint.depth_m
  const viewBox = `${-SIDE_PAD_M} ${-TOP_PAD_M} ${maxX + SIDE_PAD_M + RIGHT_PAD_M} ${maxDepth + TOP_PAD_M + SIDE_PAD_M}`

  const doorsByWall = new Map<string, DoorConnection[]>()
  for (const door of doors) {
    const list = doorsByWall.get(door.wall_id)
    if (list) list.push(door)
    else doorsByWall.set(door.wall_id, [door])
  }

  const typeCounts = new Map<string, number>()
  for (const room of rooms) typeCounts.set(room.type, (typeCounts.get(room.type) ?? 0) + 1)
  const typeSeen = new Map<string, number>()

  const roomCount = rooms.length
  const footprintAreaM2 = maxX * maxDepth

  return (
    <div className="arch-plan">
      <div className="arch-plan-stats" role="note">
        <span>{roomCount} חדרים</span>
        <span>{design.programmed_area_m2.toFixed(1)} מ&quot;ר תכנון</span>
        <span>{footprintAreaM2.toFixed(1)} מ&quot;ר טביעת רגל</span>
        {design.circulation_area_m2 > 0 && <span>{design.circulation_area_m2.toFixed(1)} מ&quot;ר חלוקה</span>}
      </div>

      <svg
        className="sketch-svg"
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`שרטוט אדריכלי של קומה ${footprint.floor}`}
      >
        <defs>
          <pattern id="sketch-grid" width={1} height={1} patternUnits="userSpaceOnUse">
            <path d="M 1 0 L 0 0 0 1" fill="none" className="sketch-svg-grid-line" />
          </pattern>
          <pattern
            id="arch-circulation-hatch"
            width={0.32}
            height={0.32}
            patternTransform="rotate(45)"
            patternUnits="userSpaceOnUse"
          >
            <line x1={0} y1={0} x2={0} y2={0.32} className="arch-circulation-hatch-line" />
          </pattern>
        </defs>

        <rect
          x={-SIDE_PAD_M}
          y={-TOP_PAD_M}
          width={maxX + SIDE_PAD_M + RIGHT_PAD_M}
          height={maxDepth + TOP_PAD_M + SIDE_PAD_M}
          className="sketch-svg-base"
        />
        <rect
          x={-SIDE_PAD_M}
          y={-TOP_PAD_M}
          width={maxX + SIDE_PAD_M + RIGHT_PAD_M}
          height={maxDepth + TOP_PAD_M + SIDE_PAD_M}
          fill="url(#sketch-grid)"
        />

        {rooms.map((room) => {
          const seen = typeSeen.get(room.type) ?? 0
          typeSeen.set(room.type, seen + 1)
          const cx = room.x + room.width_m / 2
          const cy = room.y + room.depth_m / 2
          const narrow = room.width_m < room.depth_m * 0.55
          const fontSize = Math.max(0.15, Math.min(0.32, Math.min(room.width_m, room.depth_m) * 0.24))

          return (
            <g key={room.id}>
              <rect
                className={`sketch-svg-room sketch-svg-room--${room.type}`}
                x={room.x}
                y={room.y}
                width={room.width_m}
                height={room.depth_m}
              />
              {room.is_circulation && (
                <rect
                  x={room.x}
                  y={room.y}
                  width={room.width_m}
                  height={room.depth_m}
                  fill="url(#arch-circulation-hatch)"
                  className="arch-circulation-overlay"
                />
              )}
              {room.width_m >= 0.9 ? (
                <text
                  className="sketch-svg-room-label"
                  x={cx}
                  y={cy}
                  style={{ fontSize }}
                  transform={narrow ? `rotate(-90 ${cx} ${cy})` : undefined}
                >
                  <tspan x={cx} dy="-0.2em">
                    {roomLabel(room.type, seen, typeCounts.get(room.type) ?? 1)}
                  </tspan>
                  <tspan x={cx} dy="1.3em" className="sketch-svg-room-dims" style={{ fontSize: fontSize * 0.62 }}>
                    {room.width_m.toFixed(1)}×{room.depth_m.toFixed(1)} מ&apos; · {room.area_m2.toFixed(1)} מ&quot;ר
                  </tspan>
                </text>
              ) : (
                <text
                  className="sketch-svg-room-label"
                  x={cx}
                  y={cy}
                  style={{ fontSize: Math.min(fontSize, 0.22) }}
                  transform={`rotate(-90 ${cx} ${cy})`}
                >
                  {roomLabel(room.type, seen, typeCounts.get(room.type) ?? 1)}
                </text>
              )}
            </g>
          )
        })}

        {walls.map((wall) => (
          <WallSegments key={wall.id} wall={wall} doors={doorsByWall.get(wall.id) ?? []} />
        ))}

        {doors.map((door) => (
          <DoorSymbol key={door.id} door={door} />
        ))}

        <g>
          <line x1={0} y1={-0.55} x2={maxX} y2={-0.55} className="sketch-svg-dim-line" />
          <line x1={0} y1={0} x2={0} y2={-0.55} className="sketch-svg-dim-ext" />
          <line x1={maxX} y1={0} x2={maxX} y2={-0.55} className="sketch-svg-dim-ext" />
          <text x={maxX / 2} y={-0.75} className="sketch-svg-dim-text" style={{ fontSize: 0.26 }}>
            {maxX.toFixed(1)} מ&apos;
          </text>
        </g>

        <g>
          <line x1={maxX + 0.55} y1={0} x2={maxX + 0.55} y2={maxDepth} className="sketch-svg-dim-line" />
          <line x1={maxX} y1={0} x2={maxX + 0.55} y2={0} className="sketch-svg-dim-ext" />
          <line x1={maxX} y1={maxDepth} x2={maxX + 0.55} y2={maxDepth} className="sketch-svg-dim-ext" />
          <text
            x={maxX + 0.8}
            y={maxDepth / 2}
            className="sketch-svg-dim-text"
            style={{ fontSize: 0.26 }}
            transform={`rotate(-90 ${maxX + 0.8} ${maxDepth / 2})`}
          >
            {maxDepth.toFixed(1)} מ&apos;
          </text>
        </g>

        <g transform={`translate(${maxX + RIGHT_PAD_M - 0.5} ${-TOP_PAD_M + 0.6})`}>
          <circle r={0.5} className="sketch-svg-compass-ring" />
          <path d="M 0 -0.32 L 0.12 0.08 L 0 -0.05 L -0.12 0.08 Z" className="sketch-svg-compass-needle" />
          <text y={0.35} className="sketch-svg-compass-label" style={{ fontSize: 0.22 }}>
            N
          </text>
        </g>
      </svg>
    </div>
  )
}

/** One wall, split into however many solid segments remain once every door opening on it is cut out —
 * a wall with no door in `doorsByWall` renders as a single, uninterrupted segment. This is the ONLY
 * place a wall gets a gap; the gap's position/width comes entirely from the matching `DoorConnection`,
 * never from the wall's own length (see the module docstring's invariant). */
function WallSegments({ wall, doors }: { wall: Wall; doors: DoorConnection[] }) {
  const sorted = [...doors].sort((a, b) => a.center - b.center)
  const segments: { start: number; end: number }[] = []
  let cursor = wall.start
  for (const door of sorted) {
    const gapStart = door.center - door.width_m / 2
    const gapEnd = door.center + door.width_m / 2
    if (gapStart > cursor) segments.push({ start: cursor, end: gapStart })
    cursor = Math.max(cursor, gapEnd)
  }
  if (cursor < wall.end) segments.push({ start: cursor, end: wall.end })

  const isVertical = wall.orientation === 'vertical'
  const wallClass = wall.kind === 'exterior' ? 'arch-wall-exterior' : 'arch-wall-interior'

  return (
    <>
      {segments.map((segment, index) => (
        <line
          key={index}
          x1={isVertical ? wall.coord : segment.start}
          y1={isVertical ? segment.start : wall.coord}
          x2={isVertical ? wall.coord : segment.end}
          y2={isVertical ? segment.end : wall.coord}
          className={wallClass}
        />
      ))}
    </>
  )
}

/** Neutral opening symbol — see the module docstring's "Door swing presentation" note. */
function DoorSymbol({ door }: { door: DoorConnection }) {
  const isVertical = door.orientation === 'vertical'
  const gapStart = door.center - door.width_m / 2
  const gapEnd = door.center + door.width_m / 2

  const tickAt = (pos: number) =>
    isVertical
      ? `M ${door.coord - JAMB_TICK_M} ${pos} L ${door.coord + JAMB_TICK_M} ${pos}`
      : `M ${pos} ${door.coord - JAMB_TICK_M} L ${pos} ${door.coord + JAMB_TICK_M}`

  return (
    <g className="arch-door" data-door-id={door.id} data-room-ids={door.room_ids.join(',')}>
      <path d={tickAt(gapStart)} className="arch-door-jamb" />
      <path d={tickAt(gapEnd)} className="arch-door-jamb" />
    </g>
  )
}

export default ArchitecturalFloorPlan
