import { useState } from 'react'
import type { RequirementsReview, ReviewEdit } from './demoDesign'
import './ReviewPage.css'

interface ReviewPageProps {
  review: RequirementsReview
  onConfirm: (edit: ReviewEdit) => void
  onBack: () => void
  busy?: boolean
}

/** SCREEN B — "זה מה שהבנתי".
 *
 * Shows the requirements extracted from the brief and lets the user correct them BEFORE anything
 * is generated. Two rules this screen exists to honour:
 *
 *  - Provenance is visible. A value the person actually asked for is marked differently from one
 *    we assumed, so a wrong assumption is easy to spot and fix.
 *  - Whatever leaves this screen is authoritative. Generation reads the corrected values, never
 *    the originally parsed ones. */

const SOURCE_LABEL: Record<string, string> = {
  requested: 'ביקשת',
  inferred: 'הנחנו',
  unknown: 'לא זוהה',
}

function Provenance({ source }: { source: string }) {
  return <span className={`review-source review-source--${source}`}>{SOURCE_LABEL[source] ?? source}</span>
}

/** Grouping slugs the parser emits -> what to call them on screen. An unknown slug falls back to a
 * neutral label rather than showing the raw slug. */
const TOPIC_LABEL: Record<string, string> = {
  room_adjacency: 'יחסים בין חדרים',
  corridor_width: 'רוחב מסדרון',
  orientation: 'כיווני אוויר',
  ceiling_height: 'גובה תקרה',
  storage: 'אחסון',
  style: 'סגנון',
  budget: 'תקציב',
  outdoor: 'שטחי חוץ',
  accessibility: 'נגישות',
  other: 'לא נתמך',
}

/** How the person worded it, in their language. Only a preference can be set aside. */
const SEVERITY_LABEL: Record<string, string> = {
  preference: 'העדפה',
  hard_requirement: 'דרישה מחייבת',
  ambiguous: 'לא ברור',
}

/** A width x depth pair, isolated from the surrounding RTL run.
 *
 * Without this, "20.00 × 24.00" is reordered by the bidi algorithm and displayed as
 * "24.00 × 20.00" — the reader sees a different plot from the one they entered, and the buildable
 * rectangle and footprint had the same problem. The numbers were right; the reading order was not.
 */
function Dim({ a, b }: { a: number; b: number }) {
  return (
    <span className="dim">
      {a.toFixed(2)} × {b.toFixed(2)}
    </span>
  )
}

const STREET_SIDE_LABEL: Record<string, string> = {
  NORTH: 'צפון', SOUTH: 'דרום', EAST: 'מזרח', WEST: 'מערב',
}

const CORRIDOR_MODE_LABEL: Record<string, string> = {
  minimum: 'רוחב מסדרון מינימלי',
  exact: 'רוחב מסדרון',
  preference: 'רוחב מסדרון מועדף',
}

function ReviewPage({ review, onConfirm, onBack, busy = false }: ReviewPageProps) {
  const corridor = review.corridor_width ?? null
  // Ambiguous ones never reach here as a statement — the backend asks for clarification first.
  const relationships = (review.room_relationships ?? []).filter((r) => !r.ambiguous)
  const plannedRooms = review.planned_rooms ?? []
  const site = review.site ?? null
  // Seeded from the site the backend derived, so the fields show the assumptions actually in force.
  const [setbacks, setSetbacks] = useState({
    front_setback_m: site?.front_setback_m ?? 5.5,
    rear_setback_m: site?.rear_setback_m ?? 4.0,
    side_setback_m: site?.side_setback_m ?? 3.0,
  })
  const unsupported = review.unsupported_requests ?? []
  // Anything not worded as a preference stops generation on the backend (scope.py). Saying so here,
  // before the button is pressed, beats letting the person press it and read a refusal.
  const blocking = unsupported.filter((r) => r.severity !== 'preference')
  const [bedrooms, setBedrooms] = useState(Number(review.bedrooms.value ?? 3))
  const [wetRooms, setWetRooms] = useState(Number(review.wet_rooms.value ?? 1))
  const [parking, setParking] = useState(Number(review.parking_spaces.value ?? 0))
  const [safeRoom, setSafeRoom] = useState(Boolean(review.safe_room.value))
  const [openPlan, setOpenPlan] = useState(Boolean(review.open_plan.value))

  return (
    <section className="review" aria-label="סקירת דרישות">
      <h1 className="review-title">זה מה שהבנתי</h1>
      <p className="review-subtitle">אפשר לתקן כל דבר לפני שמייצרים את התוכנית.</p>

      <blockquote className="review-brief">{review.description}</blockquote>

      {/* WHAT WE CANNOT PLAN. The brief is quoted in full just above, which made silence here read
          as agreement: a request for non-adjacent bathrooms or a 5 m corridor was dropped without a
          word and the plan came back looking complete. Anything the planner cannot act on is now
          said out loud, in the person's own words, before they press generate. */}
      {unsupported.length > 0 ? (
        <section
          className={blocking.length > 0 ? 'review-unsupported review-unsupported--blocking' : 'review-unsupported'}
          aria-label="בקשות שלא ייכללו בתכנון"
        >
          <h2 className="review-unsupported-title">
            {blocking.length > 0 ? 'צריך להכריע בבקשות האלה לפני שנתכנן' : 'מה שלא ייכלל בתכנון בשלב זה'}
          </h2>
          <p className="review-unsupported-lead">
            {blocking.length > 0
              ? 'המתכנן עדיין לא יודע לכבד אותן, ולכן לא נייצר תוכנית שמתעלמת מהן. אפשר לנסח מחדש בתיאור — "עדיף ש..." להעדפה או "חייב להיות..." לדרישה — או להסיר אותן.'
              : 'זיהינו את הבקשות האלה בתיאור שלך, אבל המתכנן עדיין לא יודע לכבד אותן. הן לא ישתנו ולא יימחקו — הן פשוט לא ישפיעו על התוכנית.'}
          </p>
          <ul className="review-unsupported-list">
            {unsupported.map((request) => (
              <li key={`${request.topic}:${request.text}`}>
                <span className={`review-severity review-severity--${request.severity}`}>
                  {SEVERITY_LABEL[request.severity] ?? SEVERITY_LABEL.ambiguous}
                </span>
                <span className="review-unsupported-text">&ldquo;{request.text}&rdquo;</span>
                <span className="review-unsupported-topic">{TOPIC_LABEL[request.topic] ?? 'לא נתמך'}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* The understood corridor requirement, shown BEFORE generate — the mode is spelled out
          because "at least 1.8 m" and "exactly 1.8 m" are different requests and the person is the
          only one who can tell us we read it wrong. */}
      {corridor ? (
        <p className="review-corridor">
          {CORRIDOR_MODE_LABEL[corridor.mode] ?? 'רוחב מסדרון'}:{' '}
          <strong>{corridor.value_m.toFixed(2)} מ׳</strong>
        </p>
      ) : null}

      {/* THE SITE. Shown before Generate because it is what everything else is measured against,
          and because the setbacks are ASSUMPTIONS — nobody verified them — yet on a small parcel
          they decide almost everything about what can be built. They are editable here for exactly
          that reason. The planner subtracts them from this plot; it never grows the plot. */}
      {site ? (
        <section className="review-site" aria-label="המגרש והנחות התכנון">
          <h2 className="review-site-title">המגרש</h2>
          <dl className="review-site-facts">
            <div><dt>מידות</dt><dd><Dim a={site.plot_width_m} b={site.plot_depth_m} /> מ׳</dd></div>
            <div><dt>שטח</dt><dd>{site.plot_area_m2.toFixed(2)} מ״ר</dd></div>
            <div><dt>חזית לרחוב</dt><dd>{STREET_SIDE_LABEL[site.street_facing_side] ?? site.street_facing_side}</dd></div>
          </dl>

          <h3 className="review-site-subtitle">הנחות נסיגה לדמו</h3>
          <div className="review-setbacks">
            {([['front_setback_m', 'חזית'], ['rear_setback_m', 'אחורית'], ['side_setback_m', 'צדדים']] as const).map(
              ([key, label]) => (
                <label key={key}>
                  {label} (מ׳)
                  <input
                    type="number" min={0.1} step={0.1} value={setbacks[key]}
                    aria-label={`נסיגה ${label}`}
                    onChange={(event) =>
                      setSetbacks({ ...setbacks, [key]: Number(event.target.value) })
                    }
                  />
                </label>
              ),
            )}
          </div>
          <p className="review-site-disclaimer">{site.setback_disclaimer}</p>

          <dl className="review-site-facts">
            <div>
              <dt>אזור בנייה שנגזר</dt>
              <dd><Dim a={site.buildable_width_m} b={site.buildable_depth_m} /> מ׳ ({site.buildable_area_m2.toFixed(2)} מ״ר)</dd>
            </div>
            {site.footprint_width_m !== null && site.footprint_depth_m !== null ? (
              <div>
                <dt>מתאר הבית שנבחר</dt>
                <dd>
                  <Dim a={site.footprint_width_m} b={site.footprint_depth_m} /> מ׳
                  {site.footprint_fits === false ? (
                    <strong className="review-site-nofit"> — אינו נכנס בשטח שנותר לבנייה</strong>
                  ) : null}
                </dd>
              </div>
            ) : null}
          </dl>
        </section>
      ) : null}

      {/* WHAT THE HOUSE WILL ACTUALLY CONTAIN. The counts below answer "how many bedrooms"; they
          cannot answer "did you understand my study?". A brief asking for one came back as
          "3 bedrooms, 1 bathroom" and the study was simply absent — planned nowhere and reported
          nowhere. Naming every room the plan will have makes an omission visible in one glance. */}
      {plannedRooms.length > 0 ? (
        <section className="review-rooms" aria-label="חדרים שייכללו בתוכנית">
          <h2 className="review-rooms-title">החדרים שייכללו בתוכנית</h2>
          <ul className="review-rooms-list">
            {plannedRooms.map((room) => (
              <li key={room}>{room}</li>
            ))}
          </ul>
          <p className="review-rooms-note">
            חדר שביקשת ואינו ברשימה — לא ייבנה. אפשר לתקן את הדרישות כאן או לחזור לתיאור.
          </p>
        </section>
      ) : null}

      {/* The understood room relationships. Shown before Generate precisely so a misreading —
          "near" heard as "adjacent", the wrong room, a preference read as a requirement — is
          catchable by the person who wrote the brief, not discovered in the finished plan. */}
      {relationships.length > 0 ? (
        <section className="review-relations" aria-label="יחסים בין חדרים">
          <h2 className="review-relations-title">יחסים בין חדרים שהבנו</h2>
          <ul className="review-relations-list">
            {relationships.map((relation) => (
              <li key={relation.source_text + relation.statement}>
                <span className={`review-severity review-severity--${relation.strength}`}>
                  {relation.strength === 'hard_requirement' ? 'דרישה מחייבת' : 'העדפה'}
                </span>
                <span className="review-relations-text">{relation.statement}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="review-grid">
        <label className="review-row">
          <span className="review-label">חדרי שינה <Provenance source={review.bedrooms.source} /></span>
          <input
            type="number" min={1} max={6} value={bedrooms}
            aria-label="חדרי שינה"
            onChange={(event) => setBedrooms(Number(event.target.value))}
          />
        </label>

        <label className="review-row">
          <span className="review-label">חדרי רחצה <Provenance source={review.wet_rooms.source} /></span>
          <input
            type="number" min={1} max={4} value={wetRooms}
            aria-label="חדרי רחצה"
            onChange={(event) => setWetRooms(Number(event.target.value))}
          />
        </label>

        <label className="review-row">
          <span className="review-label">מקומות חניה <Provenance source={review.parking_spaces.source} /></span>
          <input
            type="number" min={0} max={4} value={parking}
            aria-label="מקומות חניה"
            onChange={(event) => setParking(Number(event.target.value))}
          />
        </label>

        <label className="review-row review-row--toggle">
          <span className="review-label">ממ"ד <Provenance source={review.safe_room.source} /></span>
          <input
            type="checkbox" checked={safeRoom}
            aria-label='ממ"ד'
            onChange={(event) => setSafeRoom(event.target.checked)}
          />
        </label>

        <label className="review-row review-row--toggle">
          <span className="review-label">מטבח פתוח לסלון <Provenance source={review.open_plan.source} /></span>
          <input
            type="checkbox" checked={openPlan}
            aria-label="מטבח פתוח לסלון"
            onChange={(event) => setOpenPlan(event.target.checked)}
          />
        </label>
      </div>

      {/* The footprint used to be stated here on its own. It now appears in the site block above,
          next to the buildable rectangle it has to fit inside — which is the only place the number
          means anything. Repeating it at the bottom just asked the reader to compare two figures
          across the screen. */}

      <div className="review-actions">
        <button type="button" className="review-back" onClick={onBack} disabled={busy}>
          חזרה לתיאור
        </button>
        <button
          type="button"
          className="review-generate"
          disabled={busy || blocking.length > 0}
          title={blocking.length > 0 ? 'יש בקשות שצריך להכריע בהן קודם' : undefined}
          onClick={() =>
            onConfirm({
              ...setbacks,
              bedrooms,
              wet_rooms: wetRooms,
              parking_spaces: parking,
              safe_room: safeRoom,
              open_plan: openPlan,
            })
          }
        >
          {busy ? 'מייצר תוכנית…' : 'יצירת תוכנית'}
        </button>
      </div>
    </section>
  )
}

export default ReviewPage
