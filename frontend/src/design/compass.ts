/** The ONE mapping behind the compass rose drawn beside a plan.
 *
 * THE FRAME THE DRAWING IS IN. The demo pipeline draws every plan STREET-UP: the backend places the
 * street along the `y = 0` edge of the plot (parking bays, the entrance walk and the front door all sit
 * there — see `backend/app/demo/site_geometry.py`'s `SiteGeometry` and `vertical_slice/site.py`), and
 * nothing in the pipeline rotates or flips the result. So the top of the drawing is whichever plot
 * edge the person said faces the street, NOT north. The compass used to be a hardcoded "N" at the top,
 * which was correct for a NORTH street and wrong for the other three.
 *
 * WHAT THE BACKEND ESTABLISHES, AND WHAT IT DOES NOT. For a NORTH or SOUTH street the plot is drawn as
 * entered, street edge at the top; the rest of the ring is read as a rotated north-up map (a rotation,
 * never a reflection). For an EAST or WEST street `derive` only SWAPS the plot's width and depth so the
 * street lands at the top — no site-coordinate semantics anywhere (`site_geometry.py`, `site.py`, the
 * demo contract) say whether the drawing's left edge is then north or south. That handedness is
 * genuinely undefined, so for those two sides the mapping states only what is true: the street edge at
 * the top and the rear edge at the bottom, with no side letters and no north needle.
 *
 * Presentation only: nothing here feeds back into planning. */

export type CompassLetter = 'N' | 'E' | 'S' | 'W'

export interface CompassOrientation {
  /** The letter at the top of the drawing — always the street side. */
  top: CompassLetter
  /** The letter at the bottom — always the rear, i.e. the opposite of `top`. */
  bottom: CompassLetter
  /** The side letters, or `null` when the backend does not establish which way the drawing is handed
   * (EAST/WEST streets). */
  right: CompassLetter | null
  left: CompassLetter | null
  /** Clockwise degrees an up-pointing needle must turn to point at true north on this drawing, or
   * `null` when north's direction on the drawing is not established (EAST/WEST streets). */
  northAngleDeg: 0 | 180 | null
}

/** Clockwise around the ring, starting at the top. A north-up map reads N, E, S, W this way. */
const RING: readonly CompassLetter[] = ['N', 'E', 'S', 'W']

const STREET_SIDE_LETTER: Record<string, CompassLetter> = {
  NORTH: 'N',
  EAST: 'E',
  SOUTH: 'S',
  WEST: 'W',
}

/** The compass for a STREET-UP drawing whose top edge faces the given street side. `null` when the
 * side is missing or not one of the four cardinal values — the caller then draws NO compass, rather
 * than a needle pointing somewhere it cannot justify. Only call this for a drawing the pipeline
 * guarantees is street-up (the demo plan); the older spatial-solver drawings make no such promise. */
export function compassOrientation(streetFacingSide: string | null | undefined): CompassOrientation | null {
  if (typeof streetFacingSide !== 'string') return null
  const topLetter = STREET_SIDE_LETTER[streetFacingSide.trim().toUpperCase()]
  if (topLetter === undefined) return null

  const topIndex = RING.indexOf(topLetter)
  const at = (stepsClockwiseFromTop: number) => RING[(topIndex + stepsClockwiseFromTop) % 4]
  const handednessKnown = topLetter === 'N' || topLetter === 'S'
  return {
    top: at(0),
    bottom: at(2),
    right: handednessKnown ? at(1) : null,
    left: handednessKnown ? at(3) : null,
    // North is at the top (0°) for a north street and at the bottom (180°) for a south street.
    northAngleDeg: handednessKnown ? (topLetter === 'N' ? 0 : 180) : null,
  }
}
