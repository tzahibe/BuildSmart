/** Plan symbols for the engine-placed layout objects (Concept Plan Communication Pass).
 *
 * WHY SYMBOLS AND NOT TEXT. The audit measured every text collision on the audited plans: all 280
 * of them involved a furniture/fixture label, because the label is printed at the object's centre
 * and a room's own name sits at the room's centre. A professional plan does not write `SOFA` across
 * the living room — it draws the sofa. So each object renders as a conventional plan symbol inside
 * the rectangle the ENGINE already placed, and its name moves into `<title>` (tooltip and screen
 * readers) in Hebrew, where it informs without occupying the drawing.
 *
 * NOTHING ARCHITECTURAL IS INVENTED HERE. Every symbol is drawn strictly inside `obj.x/y/
 * width_m/depth_m` — the placement the backend decided. No object is added, moved, resized or
 * guessed; an object the backend did not place is still simply absent. The symbol is presentation
 * for a rectangle that was already being drawn.
 */

/** The user-facing Hebrew name of each kind the current product contract emits. Kinds measured on
 * the audited plans: SINK, BED, TOILET, COUNTER_RUN, WARDROBE, SOFA, COFFEE_TABLE, REFRIGERATOR,
 * COOKTOP, FOCAL_WALL, SHOWER, DINING_TABLE, ISLAND. An unknown kind keeps its raw token in the
 * tooltip rather than being silently dropped. */
export const FIXTURE_LABEL_HE: Record<string, string> = {
  SINK: 'כיור',
  BED: 'מיטה',
  TOILET: 'אסלה',
  COUNTER_RUN: 'משטח עבודה',
  WARDROBE: 'ארון',
  SOFA: 'ספה',
  COFFEE_TABLE: 'שולחן סלון',
  REFRIGERATOR: 'מקרר',
  COOKTOP: 'כיריים',
  FOCAL_WALL: 'קיר מרכזי',
  SHOWER: 'מקלחת',
  DINING_TABLE: 'שולחן אוכל',
  ISLAND: 'אי מטבח',
}

export function fixtureLabel(kind: string): string {
  return FIXTURE_LABEL_HE[kind] ?? kind
}

interface Box {
  x: number
  y: number
  w: number
  h: number
}

/** A symbol is drawn from the object's own box only, so it is deterministic and never depends on
 * neighbours, the room, or the order objects arrive in. */
export function FixtureSymbol({ kind, x, y, w, h }: { kind: string } & Box) {
  const cx = x + w / 2
  const cy = y + h / 2
  const inset = Math.min(w, h) * 0.18
  const line = 'demo-fixture-line'
  switch (kind) {
    case 'BED': {
      // pillow strip along the head (the short side nearest the top-left of the placed box)
      const horizontal = w >= h
      const pillow = Math.min(w, h) * 0.28
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" rx={Math.min(w, h) * 0.06} />
          {horizontal ? (
            <line x1={x + pillow} y1={y} x2={x + pillow} y2={y + h} className={line} />
          ) : (
            <line x1={x} y1={y + pillow} x2={x + w} y2={y + pillow} className={line} />
          )}
        </g>
      )
    }
    case 'SOFA': {
      const horizontal = w >= h
      const back = Math.min(w, h) * 0.3
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" rx={Math.min(w, h) * 0.12} />
          {horizontal ? (
            <line x1={x} y1={y + back} x2={x + w} y2={y + back} className={line} />
          ) : (
            <line x1={x + back} y1={y} x2={x + back} y2={y + h} className={line} />
          )}
        </g>
      )
    }
    case 'DINING_TABLE':
    case 'COFFEE_TABLE':
    case 'ISLAND':
      return <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" rx={Math.min(w, h) * 0.08} />
    case 'TOILET':
      return (
        <g>
          <rect x={x} y={y} width={w} height={h * 0.28} className="demo-fixture-fill" />
          <ellipse cx={cx} cy={y + h * 0.62} rx={w * 0.34} ry={h * 0.3} className="demo-fixture-outline" />
        </g>
      )
    case 'SINK':
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" rx={inset * 0.5} />
          <ellipse cx={cx} cy={cy} rx={Math.max(0.01, w / 2 - inset)} ry={Math.max(0.01, h / 2 - inset)}
                   className="demo-fixture-outline" />
        </g>
      )
    case 'SHOWER':
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" />
          <line x1={x} y1={y} x2={x + w} y2={y + h} className={line} />
          <line x1={x + w} y1={y} x2={x} y2={y + h} className={line} />
        </g>
      )
    case 'COOKTOP': {
      const r = Math.min(w, h) * 0.17
      const px = [x + w * 0.3, x + w * 0.7]
      const py = [y + h * 0.3, y + h * 0.7]
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" />
          {px.map((a) => py.map((b) => (
            <circle key={`${a}-${b}`} cx={a} cy={b} r={r} className="demo-fixture-outline" />
          )))}
        </g>
      )
    }
    case 'REFRIGERATOR':
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" />
          {w >= h ? <line x1={cx} y1={y} x2={cx} y2={y + h} className={line} />
                  : <line x1={x} y1={cy} x2={x + w} y2={cy} className={line} />}
        </g>
      )
    case 'WARDROBE':
      // the drafting convention for a closet: the box plus its diagonal
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" />
          <line x1={x} y1={y} x2={x + w} y2={y + h} className={line} />
        </g>
      )
    case 'COUNTER_RUN':
      return <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" />
    case 'FOCAL_WALL':
      // not furniture: an architectural intent marker. Drawn as a thickened wall band, never named
      // across the room.
      return <rect x={x} y={y} width={w} height={h} className="demo-fixture-focal" />
    default:
      return <rect x={x} y={y} width={w} height={h} className="demo-fixture-fill" />
  }
}

export default FixtureSymbol
