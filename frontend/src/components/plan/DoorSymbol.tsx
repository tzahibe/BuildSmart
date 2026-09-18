/** One door's floor-plan symbol (Issue #38): the wall opening, and — when the door has a real
 * leaf — the leaf line plus its swing arc, drawn the way an architect draws it.
 *
 * EVERY FACT HERE COMES FROM THE ENGINE: `x`/`y`/`width_m`/`orientation` place the opening,
 * `hinge_x`/`hinge_y` name the hinged jamb, and `swing_deg` names the open leaf's own direction
 * (`doors.py::Door.swing_deg` — degrees, 0=+x, 90=+y, 180=-x, 270=-y). This component derives
 * NOTHING from a room lookup or an adjacency guess — that is exactly the inference the backend
 * contract (Issue #38) replaced, so a door drawn here reflects only what the plan actually
 * decided. A door missing `swing_deg` draws its opening with no leaf and no arc — an unknown
 * swing is drawn as unknown, never guessed.
 */

export interface DoorSymbolFields {
  x: number
  y: number
  width_m: number
  orientation: 'vertical' | 'horizontal'
  hinge_x?: number
  hinge_y?: number
  swing_deg?: number
  is_entrance?: boolean
  /** `false` for a CASED_OPENING: a real interruption in the wall, but no door hardware — drawn
   * with jamb ticks instead of a leaf, never a swing arc. */
  hasLeaf: boolean
}

interface Point {
  x: number
  y: number
}

/** Which way the arc turns, so it sweeps the quarter the leaf actually travels through rather
 * than the opposite one. The cross product of (closed leaf) x (open leaf) about the hinge gives
 * it. */
function sweep(hx: number, hy: number, far: Point, leaf: Point): 0 | 1 {
  const cross = (far.x - hx) * (leaf.y - hy) - (far.y - hy) * (leaf.x - hx)
  return cross > 0 ? 1 : 0
}

/** The opening's two endpoints, the far jamb (the arc's other end), the hinge, and the open
 * leaf's tip (`null` when there is no leaf, or no `swing_deg` to place one from) — everything
 * `DoorSymbol` draws, exposed separately so a caller (or a test) can inspect the geometry without
 * rendering it. */
export function doorSymbolGeometry(door: DoorSymbolFields) {
  const { x, y, width_m, orientation } = door
  const half = width_m / 2
  const vertical = orientation === 'vertical'
  const [x1, y1, x2, y2] = vertical ? [x, y - half, x, y + half] : [x - half, y, x + half, y]
  const hx = door.hinge_x ?? x1
  const hy = door.hinge_y ?? y1

  // The far jamb — where the arc ends, and where the leaf would lie when closed.
  const far: Point = vertical ? { x, y: hy === y1 ? y2 : y1 } : { x: hx === x1 ? x2 : x1, y }

  let leaf: Point | null = null
  if (door.hasLeaf && door.swing_deg != null) {
    const rad = (door.swing_deg * Math.PI) / 180
    leaf = { x: hx + width_m * Math.cos(rad), y: hy + width_m * Math.sin(rad) }
  }
  return { x1, y1, x2, y2, hx, hy, far, leaf }
}

export function DoorSymbol({ door }: { door: DoorSymbolFields }) {
  const { x1, y1, x2, y2, hx, hy, far, leaf } = doorSymbolGeometry(door)
  const vertical = door.orientation === 'vertical'

  // A cased opening (or a leaf-less door with no swing direction) has no leaf to mark its
  // bounds, so short jamb ticks — perpendicular to the opening, at each end — stand in for the
  // door symbol an architect would otherwise draw there.
  const jamb = 0.12
  const jambDx = vertical ? jamb : 0
  const jambDy = vertical ? 0 : jamb

  return (
    <g>
      {/* the opening itself: the wall does not run through here */}
      <line
        x1={x1} y1={y1} x2={x2} y2={y2}
        className={
          door.is_entrance ? 'demo-door demo-door--entrance'
            : leaf ? 'demo-door'
            : 'demo-door demo-door--cased'
        }
      />
      {leaf ? (
        <>
          <path
            d={`M ${far.x} ${far.y} A ${door.width_m} ${door.width_m} 0 0 ${
              sweep(hx, hy, far, leaf)} ${leaf.x} ${leaf.y}`}
            className="demo-door-arc"
          />
          <line x1={hx} y1={hy} x2={leaf.x} y2={leaf.y} className="demo-door-leaf" />
        </>
      ) : !door.hasLeaf && !door.is_entrance ? (
        <>
          <line x1={x1 - jambDx} y1={y1 - jambDy} x2={x1 + jambDx} y2={y1 + jambDy}
                className="demo-door-jamb" />
          <line x1={x2 - jambDx} y1={y2 - jambDy} x2={x2 + jambDx} y2={y2 + jambDy}
                className="demo-door-jamb" />
        </>
      ) : null}
    </g>
  )
}

export default DoorSymbol
