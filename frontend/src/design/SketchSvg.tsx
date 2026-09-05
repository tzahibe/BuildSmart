import { useEffect, useState } from 'react'
import type { Room } from '../types'
import './SketchSvg.css'

interface SketchSvgProps {
  rooms: Room[]
}

const ROOM_LABELS: Record<string, string> = {
  kitchen: 'מטבח',
  bathroom: 'חדר רחצה',
  safe_room: 'ממ"ד',
  living_room: 'סלון',
  bedroom: 'חדר שינה',
}

// Real-world-ish constants (meters) purely for how the drawing reads — walls, door swings, and
// dimension-line offsets. These are drafting conventions, not measured data: the underlying room
// geometry (position/size) still comes entirely from the backend Geometry Solver; nothing here
// invents or adjusts a room's actual size or position.
const DOOR_WIDTH_M = 0.9
const TOP_PAD_M = 1.5
const RIGHT_PAD_M = 1.35
const SIDE_PAD_M = 0.5
const EPSILON = 1e-6

function roomLabel(room: Room, indexAmongSameType: number, countOfSameType: number): string {
  const base = ROOM_LABELS[room.type] ?? room.type
  return countOfSameType > 1 ? `${base} ${indexAmongSameType + 1}` : base
}

/** A short architectural-style door symbol: a leaf line from the hinge to its open position, plus the
 * quarter-circle arc showing the swept path back to the opening's other side. Standard floor-plan
 * drafting convention — see e.g. any architectural graphic-standards reference for "door swing". */
function doorSymbolPath(hinge: [number, number], leafTip: [number, number], otherSide: [number, number], radius: number) {
  return `M ${hinge[0]} ${hinge[1]} L ${leafTip[0]} ${leafTip[1]} A ${radius} ${radius} 0 0 1 ${otherSide[0]} ${otherSide[1]}`
}

interface SharedEdge {
  orientation: 'vertical' | 'horizontal'
  coord: number
  start: number
  end: number
}

/** The real, geometric wall segment two rooms share (if any) — mirrors the backend Geometry Solver's
 * `_shared_edge_length`, computed here from the same x/y/width/depth so the drawing reflects actual
 * adjacency rather than assuming rooms are laid out in a single row (the old generator's shape, not
 * the solver's — see below). */
function sharedEdge(a: Room, b: Room): SharedEdge | null {
  const aRight = a.x + a.width_m
  const aBottom = a.y + a.depth_m
  const bRight = b.x + b.width_m
  const bBottom = b.y + b.depth_m

  if (Math.abs(aRight - b.x) < EPSILON || Math.abs(bRight - a.x) < EPSILON) {
    const coord = Math.abs(aRight - b.x) < EPSILON ? aRight : bRight
    const start = Math.max(a.y, b.y)
    const end = Math.min(aBottom, bBottom)
    if (end - start > EPSILON) return { orientation: 'vertical', coord, start, end }
  }
  if (Math.abs(aBottom - b.y) < EPSILON || Math.abs(bBottom - a.y) < EPSILON) {
    const coord = Math.abs(aBottom - b.y) < EPSILON ? aBottom : bBottom
    const start = Math.max(a.x, b.x)
    const end = Math.min(aRight, bRight)
    if (end - start > EPSILON) return { orientation: 'horizontal', coord, start, end }
  }
  return null
}

type Edge = 'north' | 'south' | 'east' | 'west'

/** Which outer edge of the [0,0]-[maxX,maxDepth] bounding box `room` is flush against, or `null` if
 * it isn't on the boundary at all (e.g. fully interior, or the layout doesn't tile all the way out). */
function outerEdgeTouched(room: Room, maxX: number, maxDepth: number): Edge | null {
  if (Math.abs(room.y) < EPSILON) return 'north'
  if (Math.abs(room.y + room.depth_m - maxDepth) < EPSILON) return 'south'
  if (Math.abs(room.x) < EPSILON) return 'west'
  if (Math.abs(room.x + room.width_m - maxX) < EPSILON) return 'east'
  return null
}

/** Pure presentational component: renders a floor's `Room[]` (already-computed x/y/width_m/depth_m, in
 * meters — see backend/app/geometry/solver.py) as an architectural-style floor plan sketch — exterior/
 * interior wall lines drawn along the rooms' ACTUAL shared edges, door openings, dimension callouts, a
 * north marker, and pale per-room tints with type + size labels. The `viewBox` is in meters and scales
 * via CSS (width/height: 100%), so it stays responsive with no resize listener needed.
 *
 * This is a drafting/rendering pass only: the rooms' actual positions and sizes are exactly what the
 * backend generated — nothing here changes the underlying geometry. Walls/doors are derived from real
 * geometric adjacency between every pair of rooms (not from array order), because the Geometry Solver
 * produces genuine 2D layouts (multiple rows, varying depths per room) — an earlier version of this
 * component assumed the old generator's single-row-per-floor shape and rendered rooms outside the
 * visible area for any layout that wasn't a single row; see the exact bug and fix discussion this
 * component's own review left behind. */
function SketchSvg({ rooms }: SketchSvgProps) {
  const floors = [...new Set(rooms.map((room) => room.floor))].sort((a, b) => a - b)
  const [activeFloor, setActiveFloor] = useState<number>(floors[0] ?? 1)

  useEffect(() => {
    if (floors.length > 0 && !floors.includes(activeFloor)) {
      setActiveFloor(floors[0])
    }
    // Only re-run when the set of available floors actually changes (e.g. after regeneration).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floors.join(',')])

  if (rooms.length === 0) {
    return <p className="sketch-svg-empty">אין עדיין נתוני תכנון להצגה</p>
  }

  const floorRooms = rooms.filter((room) => room.floor === activeFloor)
  // Bounding box of the ACTUAL room extents — must use each room's far edge (x/y + its own
  // width/depth), not just the largest single width/depth value, since rooms can sit at different
  // rows/columns with different sizes in a genuine 2D layout.
  const maxX = Math.max(...floorRooms.map((room) => room.x + room.width_m), 0)
  const maxDepth = Math.max(...floorRooms.map((room) => room.y + room.depth_m), 0)
  const viewBox = `${-SIDE_PAD_M} ${-TOP_PAD_M} ${maxX + SIDE_PAD_M + RIGHT_PAD_M} ${maxDepth + TOP_PAD_M + SIDE_PAD_M}`

  // The ground floor's living room gets a stylized front entry, placed on whichever outer edge it's
  // actually flush against (never assumed) — this is a drafting convention for legibility, not a
  // claim about the real entry's location.
  const groundFloor = floors[0]
  const livingRoom =
    activeFloor === groundFloor ? floorRooms.find((room) => room.type === 'living_room') : undefined
  const entryEdge = livingRoom ? outerEdgeTouched(livingRoom, maxX, maxDepth) : null

  let exteriorWallPath: string
  let exteriorDoorPath: string | null = null
  if (livingRoom && entryEdge) {
    const isHorizontalEdge = entryEdge === 'north' || entryEdge === 'south'
    const span = isHorizontalEdge ? livingRoom.width_m : livingRoom.depth_m
    const half = Math.min(DOOR_WIDTH_M / 2, span / 2 - 0.1)
    const center = isHorizontalEdge ? livingRoom.x + livingRoom.width_m / 2 : livingRoom.y + livingRoom.depth_m / 2
    const gapStart = center - half
    const gapEnd = center + half

    if (entryEdge === 'south') {
      exteriorWallPath =
        `M 0 0 L ${maxX} 0 L ${maxX} ${maxDepth} L ${gapEnd} ${maxDepth} ` +
        `M ${gapStart} ${maxDepth} L 0 ${maxDepth} L 0 0`
      exteriorDoorPath = doorSymbolPath([gapStart, maxDepth], [gapStart, maxDepth - DOOR_WIDTH_M], [gapEnd, maxDepth], DOOR_WIDTH_M)
    } else if (entryEdge === 'north') {
      exteriorWallPath = `M ${gapEnd} 0 L ${maxX} 0 L ${maxX} ${maxDepth} L 0 ${maxDepth} L 0 0 L ${gapStart} 0`
      exteriorDoorPath = doorSymbolPath([gapStart, 0], [gapStart, DOOR_WIDTH_M], [gapEnd, 0], DOOR_WIDTH_M)
    } else if (entryEdge === 'west') {
      exteriorWallPath = `M 0 ${gapEnd} L 0 ${maxDepth} L ${maxX} ${maxDepth} L ${maxX} 0 L 0 0 L 0 ${gapStart}`
      exteriorDoorPath = doorSymbolPath([0, gapStart], [DOOR_WIDTH_M, gapStart], [0, gapEnd], DOOR_WIDTH_M)
    } else {
      exteriorWallPath = `M ${maxX} ${gapEnd} L ${maxX} ${maxDepth} L 0 ${maxDepth} L 0 0 L ${maxX} 0 L ${maxX} ${gapStart}`
      exteriorDoorPath = doorSymbolPath([maxX, gapStart], [maxX - DOOR_WIDTH_M, gapStart], [maxX, gapEnd], DOOR_WIDTH_M)
    }
  } else {
    exteriorWallPath = `M 0 0 L ${maxX} 0 L ${maxX} ${maxDepth} L 0 ${maxDepth} Z`
  }

  // Interior walls/doors: derived from REAL pairwise adjacency (every room compared against every
  // other), not from array order — the old "consecutive rooms in a sorted row" assumption produced
  // nonsensical walls (cutting through unrelated rooms, or missing real boundaries entirely) once
  // rooms could occupy more than one row.
  const interiorEdges: { key: string; wallPath: string; doorPath: string | null }[] = []
  for (let i = 0; i < floorRooms.length; i++) {
    for (let j = i + 1; j < floorRooms.length; j++) {
      const edge = sharedEdge(floorRooms[i], floorRooms[j])
      if (!edge) continue

      const segmentLength = edge.end - edge.start
      const doorSpan = Math.min(DOOR_WIDTH_M, segmentLength * 0.7)
      const hasDoor = segmentLength > doorSpan + 0.2
      const mid = (edge.start + edge.end) / 2
      const gapStart = mid - doorSpan / 2
      const gapEnd = mid + doorSpan / 2

      let wallPath: string
      let doorPath: string | null = null
      if (edge.orientation === 'vertical') {
        wallPath = hasDoor
          ? `M ${edge.coord} ${edge.start} L ${edge.coord} ${gapStart} M ${edge.coord} ${gapEnd} L ${edge.coord} ${edge.end}`
          : `M ${edge.coord} ${edge.start} L ${edge.coord} ${edge.end}`
        if (hasDoor) {
          doorPath = doorSymbolPath([edge.coord, gapStart], [edge.coord + doorSpan, gapStart], [edge.coord, gapEnd], doorSpan)
        }
      } else {
        wallPath = hasDoor
          ? `M ${edge.start} ${edge.coord} L ${gapStart} ${edge.coord} M ${gapEnd} ${edge.coord} L ${edge.end} ${edge.coord}`
          : `M ${edge.start} ${edge.coord} L ${edge.end} ${edge.coord}`
        if (hasDoor) {
          doorPath = doorSymbolPath([gapStart, edge.coord], [gapStart, edge.coord + doorSpan], [gapEnd, edge.coord], doorSpan)
        }
      }
      interiorEdges.push({ key: `${i}-${j}`, wallPath, doorPath })
    }
  }

  const typeCounts = new Map<string, number>()
  for (const room of floorRooms) {
    typeCounts.set(room.type, (typeCounts.get(room.type) ?? 0) + 1)
  }
  const typeSeen = new Map<string, number>()

  return (
    <div className="sketch-svg-wrapper">
      {floors.length > 1 && (
        <div className="sketch-svg-floor-tabs" role="tablist" aria-label="בחירת קומה">
          {floors.map((floor) => (
            <button
              key={floor}
              type="button"
              role="tab"
              aria-selected={floor === activeFloor}
              className={
                floor === activeFloor
                  ? 'sketch-svg-floor-tab sketch-svg-floor-tab--active'
                  : 'sketch-svg-floor-tab'
              }
              onClick={() => setActiveFloor(floor)}
            >
              קומה {floor}
            </button>
          ))}
        </div>
      )}

      <svg
        className="sketch-svg"
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`שרטוט סקיצה של קומה ${activeFloor}`}
      >
        <defs>
          <pattern id="sketch-grid" width={1} height={1} patternUnits="userSpaceOnUse">
            <path d="M 1 0 L 0 0 0 1" fill="none" className="sketch-svg-grid-line" />
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

        {floorRooms.map((room, index) => {
          const seen = typeSeen.get(room.type) ?? 0
          typeSeen.set(room.type, seen + 1)
          const cx = room.x + room.width_m / 2
          const cy = room.y + room.depth_m / 2
          const narrow = room.width_m < room.depth_m * 0.55
          const fontSize = Math.max(0.15, Math.min(0.32, Math.min(room.width_m, room.depth_m) * 0.24))

          return (
            <g key={`${room.type}-${index}`}>
              <rect
                className={`sketch-svg-room sketch-svg-room--${room.type}`}
                x={room.x}
                y={room.y}
                width={room.width_m}
                height={room.depth_m}
              />
              {/* A room wide enough for two lines gets type + dimensions; a sliver too narrow for
                  that gets just its type name, to avoid the two lines overlapping the next room. */}
              {room.width_m >= 0.9 ? (
                <text
                  className="sketch-svg-room-label"
                  x={cx}
                  y={cy}
                  style={{ fontSize }}
                  transform={narrow ? `rotate(-90 ${cx} ${cy})` : undefined}
                >
                  <tspan x={cx} dy="-0.2em">
                    {roomLabel(room, seen, typeCounts.get(room.type) ?? 1)}
                  </tspan>
                  <tspan
                    x={cx}
                    dy="1.3em"
                    className="sketch-svg-room-dims"
                    style={{ fontSize: fontSize * 0.62 }}
                  >
                    {room.width_m.toFixed(1)}×{room.depth_m.toFixed(1)} מ&apos; · {room.area_m2.toFixed(1)}{' '}
                    מ&quot;ר
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
                  {roomLabel(room, seen, typeCounts.get(room.type) ?? 1)}
                </text>
              )}
            </g>
          )
        })}

        {interiorEdges.map(({ key, wallPath, doorPath }) => (
          <g key={key}>
            <path d={wallPath} className="sketch-svg-wall-interior" />
            {doorPath && <path d={doorPath} className="sketch-svg-door" />}
          </g>
        ))}

        <path d={exteriorWallPath} className="sketch-svg-wall-exterior" />
        {exteriorDoorPath && <path d={exteriorDoorPath} className="sketch-svg-door" />}

        <g>
          <line x1={0} y1={-0.55} x2={maxX} y2={-0.55} className="sketch-svg-dim-line" />
          <line x1={0} y1={0} x2={0} y2={-0.55} className="sketch-svg-dim-ext" />
          <line x1={maxX} y1={0} x2={maxX} y2={-0.55} className="sketch-svg-dim-ext" />
          <text x={maxX / 2} y={-0.75} className="sketch-svg-dim-text" style={{ fontSize: 0.26 }}>
            {maxX.toFixed(1)} מ&apos;
          </text>
        </g>

        <g>
          <line
            x1={maxX + 0.55}
            y1={0}
            x2={maxX + 0.55}
            y2={maxDepth}
            className="sketch-svg-dim-line"
          />
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

export default SketchSvg
