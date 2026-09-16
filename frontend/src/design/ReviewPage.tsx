import { useState } from 'react'
import type {
  PublicOpenSide, RequirementsReview, ReviewEdit, WetRoomKindEdit, WetRoomKindNote,
} from './demoDesign'
import { PUBLIC_OPEN_SIDES } from './demoDesign'
import { Dim } from './Dim'
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

const PUBLIC_OPEN_SIDE_LABEL: Record<PublicOpenSide, string> = {
  engine: 'המנוע יחליט',
  street: 'לרחוב',
  garden: 'לגינה',
}

/** A value the backend sent that this build does not know reads as "the engine decides". */
function publicOpenSideOf(value: unknown): PublicOpenSide {
  return PUBLIC_OPEN_SIDES.includes(value as PublicOpenSide) ? (value as PublicOpenSide) : 'engine'
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

/** What a wet room can be, in the person's words. The value is what the backend stores. */
const WET_ROOM_KIND_OPTIONS: { value: string; host: WetRoomKindEdit['host']; label: string }[] = [
  { value: 'unspecified', host: null, label: 'לא צוין (ברירת מחדל)' },
  { value: 'shared_bathroom', host: null, label: 'חדר רחצה משותף' },
  { value: 'ensuite', host: 'MASTER_BEDROOM', label: 'חדר רחצה צמוד לחדר ההורים' },
  { value: 'ensuite', host: 'BEDROOM', label: 'חדר רחצה צמוד לחדר שינה' },
  { value: 'guest_wc', host: null, label: 'שירותי אורחים' },
]

const optionKey = (kind: string, host: string | null) => (kind === 'ensuite' ? `${kind}:${host ?? 'MASTER_BEDROOM'}` : kind)

/** The rows the person edits, seeded from what the backend resolved. A row the backend marked as a
 * default starts as "unspecified" — editing it is how the person STATES a kind; leaving it keeps the
 * default, which the backend will still show as a default. */
function seedWetRoomRows(notes: WetRoomKindNote[], count: number): WetRoomKindEdit[] {
  const rows: WetRoomKindEdit[] = notes.map((n) =>
    n.specified
      ? { kind: n.kind as WetRoomKindEdit['kind'], host: n.kind === 'ensuite' ? n.host : null, strength: n.strength as WetRoomKindEdit['strength'] }
      : { kind: 'unspecified', host: null, strength: n.strength === 'flexible' ? 'flexible' : 'required' },
  )
  while (rows.length < count) rows.push({ kind: 'unspecified', host: null, strength: 'required' })
  return rows.slice(0, count)
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
    front_setback_m: site?.front_setback_m ?? 0,
    rear_setback_m: site?.rear_setback_m ?? 0,
    side_setback_m: site?.side_setback_m ?? 0,
  })
  const unsupported = review.unsupported_requests ?? []
  // Anything not worded as a preference stops generation on the backend (scope.py). Saying so here,
  // before the button is pressed, beats letting the person press it and read a refusal.
  const blocking = unsupported.filter((r) => r.severity !== 'preference')
  // THE COUNTS THIS STAGE CAN ACTUALLY PLAN, from the backend rather than typed in here. The
  // bedroom input used to allow 1..6 while generation accepted 2..5, so a value the product itself
  // offered was refused after the loading screen — the worst possible moment to say no.
  const limits = review.limits
  const bedroomsMin = limits?.bedrooms_min ?? 1
  const bedroomsMax = limits?.bedrooms_max ?? 6
  const wetMin = limits?.wet_rooms_min ?? 1
  const wetMax = limits?.wet_rooms_max ?? 3
  const parkingMax = limits?.parking_max ?? 2
  const floorsMax = limits?.floors ?? 1

  const [bedrooms, setBedrooms] = useState(Number(review.bedrooms.value ?? 3))
  // THE STOREY COUNT, shown with its provenance like every other requirement. The parser reads it
  // from the brief and defaults to one when nothing is said; until now the review screen was the
  // one place it was NOT shown, so a person who wrote "בית דו-קומתי" saw every other requirement
  // echoed back and this one silently dropped — and learned of it only from the refusal after the
  // loading screen. Same rule as bedrooms: a count generation would refuse is said here.
  const [floors, setFloors] = useState(Number(review.floors?.value ?? 1))
  const [wetRooms, setWetRoomsState] = useState(Number(review.wet_rooms.value ?? 1))
  // WHAT EACH WET ROOM IS (specs/007). One row per counted room; the count drives the row list.
  const wetNotes = review.wet_room_kinds ?? []
  const [wetRows, setWetRows] = useState<WetRoomKindEdit[]>(() => seedWetRoomRows(wetNotes, Number(review.wet_rooms.value ?? 1)))
  // Whether the rows have moved since the backend last judged them. The backend's verdict on the
  // STORED rows (`wet_room_problem`) blocks Generate until the person changes something; after that,
  // the next Generate press sends the rows for a fresh verdict and is refused again if they still
  // leave a bedroom without a bathroom — the judgement stays on the backend, never duplicated here.
  const [wetRowsDirty, setWetRowsDirty] = useState(false)
  const wetProblem = review.wet_room_problem ?? null
  const wetBlocked = wetProblem !== null && !wetRowsDirty
  // THE ANSWER THE BACKEND OFFERS. Accepting it is an ordinary edit — the rows land in the editor
  // and travel with Generate like any correction — so what is confirmed is what is stored.
  const wetProposal = review.wet_room_proposal ?? null

  function applyWetProposal() {
    if (!wetProposal) return
    setWetRoomsState(wetProposal.wet_rooms)
    setWetRows(wetProposal.wet_room_kinds.map((r) => ({ kind: r.kind, host: r.host, strength: r.strength })))
    setWetRowsDirty(true)
  }

  function setWetRooms(count: number) {
    setWetRoomsState(count)
    setWetRows((rows) => {
      const next = rows.slice(0, Math.max(0, count))
      while (next.length < count) next.push({ kind: 'unspecified', host: null, strength: 'required' })
      return next
    })
    setWetRowsDirty(true)
  }

  function setWetRow(index: number, patch: Partial<WetRoomKindEdit>) {
    setWetRows((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)))
    setWetRowsDirty(true)
  }
  const [parking, setParking] = useState(Number(review.parking_spaces.value ?? 0))
  const [safeRoom, setSafeRoom] = useState(Boolean(review.safe_room.value))
  const [openPlan, setOpenPlan] = useState(Boolean(review.open_plan.value))
  const [publicOpenSide, setPublicOpenSide] = useState<PublicOpenSide>(
    publicOpenSideOf(review.public_open_side?.value),
  )

  // A count outside the envelope is refused at generation. Saying so HERE, where it can be
  // corrected, is the whole difference between a two-second fix and a wasted journey.
  const outOfRange = bedrooms < bedroomsMin || bedrooms > bedroomsMax
  const floorsOutOfRange = floors < 1 || floors > floorsMax

  // WHY GENERATE IS DISABLED, in the same priority order the button already used for its
  // tooltip — computed once so the tooltip and the text under the button never say two
  // different things. A hard requirement names itself: "יש בקשות" told the person something was
  // wrong without saying what, so they had to scroll up to find it.
  const blockingReason =
    blocking.length === 1
      ? `לא ניתן ליצור תוכנית: ״${blocking[0].text}״ הוא דרישה מחייבת שהמתכנן לא יודע לכבד. ` +
        'אפשר לנסח אותה כהעדפה או להסיר מהתיאור.'
      : blocking.length > 1
        ? `לא ניתן ליצור תוכנית: ${blocking.map((r) => `״${r.text}״`).join(', ')} הן דרישות ` +
          'מחייבות שהמתכנן לא יודע לכבד. אפשר לנסח אותן כהעדפה או להסיר מהתיאור.'
        : null
  const disabledReason: string | undefined =
    outOfRange
      ? `בשלב זה אפשר לתכנן ${bedroomsMin} עד ${bedroomsMax} חדרי שינה`
      : floorsOutOfRange
        ? (floorsMax === 1 ? 'בשלב זה אפשר לתכנן בית בקומה אחת בלבד' : `בשלב זה אפשר לתכנן עד ${floorsMax} קומות`)
        : (blockingReason ??
          (wetBlocked ? 'צריך להשלים את חדרי הרחצה קודם' : undefined))

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
                    type="number" min={0} step={0.1} value={setbacks[key]}
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
              {/* An axis the setbacks used up leaves no rectangle to state the size of — the
                  region is EMPTY, and is said in words rather than as a negative length. */}
              <dd>{site.has_buildable_area
                ? <><Dim a={site.buildable_width_m} b={site.buildable_depth_m} /> מ׳ ({site.buildable_area_m2.toFixed(2)} מ״ר)</>
                : 'אין אזור בנייה — הנסיגות מכסות את המגרש כולו'}</dd>
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
            ) : (
              // No outline was entered (feature 006): the engine plans the shapes that fit the
              // buildable area and shows the ones that work. Said here so the review is complete.
              <div>
                <dt>מתאר הבניין</dt>
                <dd>ייקבע אוטומטית לפי השטח המבוקש — המערכת תבדוק כמה צורות ותציג את אלה שמתוכננות</dd>
              </div>
            )}
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
            type="number" min={bedroomsMin} max={bedroomsMax} value={bedrooms}
            aria-label="חדרי שינה"
            onChange={(event) => setBedrooms(Number(event.target.value))}
          />
        </label>
        {outOfRange ? (
          <p className="review-out-of-range" role="alert">
            {`בשלב זה אפשר לתכנן ${bedroomsMin} עד ${bedroomsMax} חדרי שינה. `}
            {`הערך ${bedrooms} לא ייווצר — יש לתקן אותו כאן.`}
          </p>
        ) : null}

        <label className="review-row">
          <span className="review-label">קומות <Provenance source={review.floors?.source ?? 'inferred'} /></span>
          <input
            type="number" min={1} max={floorsMax} value={floors}
            aria-label="קומות"
            onChange={(event) => setFloors(Number(event.target.value))}
          />
        </label>
        {floorsOutOfRange ? (
          <p className="review-out-of-range" role="alert">
            {floorsMax === 1
              ? 'בשלב זה אפשר לתכנן בית בקומה אחת בלבד. '
              : `בשלב זה אפשר לתכנן עד ${floorsMax} קומות. `}
            {`הערך ${floors} לא ייווצר — יש לתקן אותו כאן.`}
          </p>
        ) : null}

        <label className="review-row">
          <span className="review-label">חדרי רחצה <Provenance source={review.wet_rooms.source} /></span>
          <input
            type="number" min={wetMin} max={wetMax} value={wetRooms}
            aria-label="חדרי רחצה"
            onChange={(event) => setWetRooms(Number(event.target.value))}
          />
        </label>

        {/* WHO REACHES EACH WET ROOM. A count alone hid the difference between "ensuite + guest WC"
            and "two shared bathrooms"; now each room is named as it will be built, a default is
            called a default, and a shared bathroom can be marked flexible — the one case in which
            the planner may attach it to a bedroom. */}
        <section className="review-wet-rooms" aria-label="סוגי חדרי הרחצה">
          {wetRows.map((row, i) => {
            const note = wetNotes[i]
            const selectValue = optionKey(row.kind, row.host)
            const canBeFlexible = row.kind === 'shared_bathroom' || row.kind === 'unspecified'
            return (
              <div className="review-wet-room" key={i}>
                <label className="review-row">
                  <span className="review-label">
                    חדר רחצה {i + 1}
                    {note ? <Provenance source={note.specified ? 'requested' : 'inferred'} /> : null}
                  </span>
                  <span className="review-select-wrap">
                    <select
                      className="review-select"
                      aria-label={`סוג חדר רחצה ${i + 1}`}
                      value={selectValue}
                      onChange={(event) => {
                        const option = WET_ROOM_KIND_OPTIONS.find((o) => optionKey(o.value, o.host) === event.target.value)!
                        setWetRow(i, {
                          kind: option.value as WetRoomKindEdit['kind'],
                          host: option.host,
                          strength: option.value === 'shared_bathroom' || option.value === 'unspecified' ? row.strength : 'required',
                        })
                      }}
                    >
                      {WET_ROOM_KIND_OPTIONS.map((o) => (
                        <option key={optionKey(o.value, o.host)} value={optionKey(o.value, o.host)}>{o.label}</option>
                      ))}
                    </select>
                  </span>
                </label>
                <label className="review-row review-row--toggle">
                  <span className="review-label">גמיש — המתכנן רשאי להצמיד לחדר שינה</span>
                  <input
                    type="checkbox"
                    aria-label={`חדר רחצה ${i + 1} גמיש`}
                    checked={row.strength === 'flexible'}
                    disabled={!canBeFlexible}
                    onChange={(event) => setWetRow(i, { strength: event.target.checked ? 'flexible' : 'required' })}
                  />
                </label>
                {note && !wetRowsDirty ? (
                  <p className="review-wet-room-note">
                    {note.label}
                    {note.source_text ? <> — &ldquo;{note.source_text}&rdquo;</> : null}
                  </p>
                ) : null}
              </div>
            )
          })}
          {wetProblem && !wetRowsDirty ? (
            <p className="review-out-of-range" role="alert">{wetProblem}</p>
          ) : null}
          {/* The backend has not re-judged these rows yet — that only happens on the next
              Generate — so the ORIGINAL verdict ("צריך להגיד לנו מה נכון") would keep telling the
              person to answer a question they already answered. This says the truer thing: the
              edit is noted and will be checked, not accepted or rejected yet. */}
          {wetProblem && wetRowsDirty ? (
            <p className="review-wet-room-pending">השינוי בחדרי הרחצה ייבדק בלחיצה על יצירת תוכנית</p>
          ) : null}
          {wetProblem && wetProposal && !wetRowsDirty ? (
            <button type="button" className="review-back review-wet-proposal" onClick={applyWetProposal}>
              {wetProposal.summary}
            </button>
          ) : null}
        </section>

        <label className="review-row">
          <span className="review-label">מקומות חניה <Provenance source={review.parking_spaces.source} /></span>
          <input
            type="number" min={0} max={parkingMax} value={parking}
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

        {/* A preference, not a requirement: it decides between plans the engine otherwise rates
            the same (the two ways an L can face), so a house that only fits one way is still
            offered. The note under the row says so, so nobody reads "לגינה" as a promise. */}
        <label className="review-row">
          <span className="review-label">
            הסלון פונה <Provenance source={review.public_open_side?.source ?? 'inferred'} />
            <br />
            <span className="review-rooms-note">העדפה: מכריעה בין תוכניות שוות ערך, לא דרישה</span>
          </span>
          <span className="review-select-wrap">
            <select
              className="review-select"
              value={publicOpenSide}
              aria-label="הסלון פונה"
              onChange={(event) => setPublicOpenSide(publicOpenSideOf(event.target.value))}
            >
              {PUBLIC_OPEN_SIDES.map((side) => (
                <option key={side} value={side}>{PUBLIC_OPEN_SIDE_LABEL[side]}</option>
              ))}
            </select>
          </span>
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
          disabled={busy || blocking.length > 0 || outOfRange || floorsOutOfRange || wetBlocked}
          title={disabledReason}
          onClick={() =>
            onConfirm({
              ...setbacks,
              bedrooms,
              floors,
              wet_rooms: wetRooms,
              wet_room_kinds: wetRows,
              parking_spaces: parking,
              safe_room: safeRoom,
              open_plan: openPlan,
              public_open_side: publicOpenSide,
            })
          }
        >
          {busy ? 'מייצר תוכנית…' : 'יצירת תוכנית'}
        </button>
      </div>
      {/* The tooltip alone hid the reason above the fold, on a screen that already scrolls: the
          person saw a disabled button and a generic wet-room alert higher up, with nothing tying
          the two together. The same reason the title carries is said again here, in the place the
          eye actually lands after Generate does nothing. */}
      {disabledReason ? (
        <p className="review-generate-reason">{disabledReason}</p>
      ) : null}
    </section>
  )
}

export default ReviewPage
