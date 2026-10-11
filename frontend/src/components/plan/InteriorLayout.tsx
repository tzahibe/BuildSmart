import type { DemoLayoutObject } from '../../design/demoDesign'
import { FixtureSymbol, fixtureLabel } from './fixtureSymbols'

/** Engine-placed semantic layout objects (Issue #39) — drawn AS-IS, one symbol per object, inside
 * the rectangle the backend placed. This component decides nothing architectural: it never invents
 * a decorative object, never guesses a position, never draws an item the backend did not place —
 * the same boundary `DoorSymbol` already holds for doors. An object whose placement failed is
 * simply absent from `design.layout` (`RoomLayout.unplaceable`, backend-only diagnostic data) —
 * never drawn as a guess.
 *
 * The object's NAME is a `<title>`, not printed text (Concept Plan Communication Pass): the audit
 * measured that every text collision on the audited plans involved one of these labels, and a plan
 * that writes `SOFA` across the living room is not a plan an architect would show a client. The
 * name is still there for a tooltip and for screen readers, in Hebrew.
 */

function kindClass(kind: string): string {
  return `demo-layout-object--${kind.toLowerCase().replace(/_/g, '-')}`
}

export function InteriorLayout({ objects }: { objects: DemoLayoutObject[] }) {
  return (
    <g className="demo-layout">
      {objects.map((obj, i) => (
        <g key={`layout-${obj.room_id}-${obj.kind}-${i}`}
           className={`demo-layout-object ${kindClass(obj.kind)}`}
           data-kind={obj.kind}>
          <title>{fixtureLabel(obj.kind)}</title>
          <FixtureSymbol kind={obj.kind} x={obj.x} y={obj.y} w={obj.width_m} h={obj.depth_m} />
        </g>
      ))}
    </g>
  )
}

export default InteriorLayout
