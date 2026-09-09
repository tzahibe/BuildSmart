import './Dim.css'

/** A width × depth pair, isolated from the surrounding RTL run.
 *
 * Without the isolation the bidi algorithm reorders the pair: in an RTL paragraph the numbers are
 * European-number runs and the "×" between them resolves to the paragraph's own right-to-left
 * direction, so the whole run is reversed and "200.00 × 3.00" is DISPLAYED as "3.00 × 200.00". The
 * reader then sees a different plot from the one they entered — the values were right, the reading
 * order was not. Every width × depth pair in the app goes through this component so the rule is
 * kept in one place rather than re-derived per screen.
 *
 * `dir="ltr"` is carried on the element as well as in the stylesheet on purpose: browsers isolate
 * on the attribute in their own UA stylesheet, so the reading order does not depend on this app's
 * CSS having loaded, and a test can assert the isolation without evaluating a stylesheet. */
export function Dim({ a, b }: { a: number; b: number }) {
  return (
    <span className="dim" dir="ltr">
      {a.toFixed(2)} × {b.toFixed(2)}
    </span>
  )
}

export default Dim
