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

const CORRIDOR_MODE_LABEL: Record<string, string> = {
  minimum: 'רוחב מסדרון מינימלי',
  exact: 'רוחב מסדרון',
  preference: 'רוחב מסדרון מועדף',
}

function ReviewPage({ review, onConfirm, onBack, busy = false }: ReviewPageProps) {
  const corridor = review.corridor_width ?? null
  // Ambiguous ones never reach here as a statement — the backend asks for clarification first.
  const relationships = (review.room_relationships ?? []).filter((r) => !r.ambiguous)
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

      {review.footprint_width_m && review.footprint_depth_m ? (
        <p className="review-footprint">
          מתאר הבניין שנבחר: {review.footprint_width_m} × {review.footprint_depth_m} מ׳
        </p>
      ) : null}

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
