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

function ReviewPage({ review, onConfirm, onBack, busy = false }: ReviewPageProps) {
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
          disabled={busy}
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
