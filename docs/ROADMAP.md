# BuildSmart — Proposed Roadmap (owner-maintained)

Status: PROPOSED ROADMAP, not a backlog. Written by the owner on 2026-09-17. Nothing here is an
Issue. The owner decides, topic by topic, what enters the backlog (see "How this roadmap is used").

## How this roadmap is used

1. The owner says, in the IDE or on Telegram, for example: "בוא נקדם Windows + Exterior Exposure".
2. The Opus Team Lead investigates the current state (Wiki, code, tests, audit trail; a read-only
   Sonnet domain lead when useful) and returns a **proposal**: 2–5 well-formed Issues, ordered,
   with dependencies, risk/resource class, locks, regression budget and deterministic Acceptance
   Criteria — in the PROPOSED FOLLOW-UP format. Proposals are text, never GitHub Issues.
3. The owner approves what actually enters the backlog (Telegram: draft → Create only / Create &
   Queue; or a contract file the owner approves). Only then does execution start, and only with
   `owner:approved`.
4. Nothing on this list is opened as an Issue on its own initiative; the list is never "worked
   through" automatically.

## P0 — must close before anything else

- **סגירת איכות התכנון הבסיסי** — לוודא שהתוכניות שאנחנו כבר יודעים לייצר הן ברמה אדריכלית
  טובה: ניצול שטח, פרופורציות חדרים, מניעת dead space, adjacency נכון, circulation הגיוני, בלי חדר
  בתוך חדר ובלי פתרונות שרשרת גרועים.
- **Entrance / Exterior Door** — כניסה אמיתית לבית: דלת חיצונית, מיקום כניסה, foyer/מבואה במידת
  הצורך, קשר נכון לאזור הציבורי ולא כניסה אקראית לתוך חדר.
- **Doors + Access Topology** — להשלים חוקי דלתות: לכל חדר נגישות תקינה, בלי bedroom-to-bedroom
  כפתרון רגיל, דלתות שירות, פתחים הגיוניים, בדיקות deterministic.
- **Windows + Exterior Exposure** — חלונות כחלק אמיתי מהתכנון, לא ציור בלבד. אילו חדרים חייבים
  קיר חיצוני, אילו חייבים חלון, מיקום חלון, וה-validator שמוודא את זה.
- **Laundry Room semantics** — לסגור סופית את ההגדרה שכבר קבענו: חדר כביסה הוא חדר סגור שאפשר
  להיכנס אליו, דלת, מקום שימושי למכונה, וחלון חיצוני חובה. לבדוק שה-generator וה-validator באמת
  מבטיחים את זה.
- **Exact Area / Room Area Fidelity** — המשתמש מבקש מטרים — התוכנית צריכה לכבד אותם. להגדיר
  tolerance ברור, לבדוק שטח ממומש ולא רק target, ולהימנע מ-silent shrinking.
- **Buildable Region / Site Constraints** — לעבור מתכנון בתוך מלבן מופשט לתכנון בתוך מגרש אמיתי:
  parcel, setbacks, buildable polygon, orientation, footprint fit.

## P1

- **Multi-Level Phase 2** — להמשיך מה-Phase 1 שכבר קיים: חלוקת פונקציות בין קומות, stairs/core
  אמיתי, קשר אנכי, footprint שונה בין קומות במידת הצורך, validation ברמת building ולא רק level.
- **Stairs / Vertical Core** — גרם מדרגות כאלמנט גיאומטרי אמיתי עם שטח, רוחב, נחיתה, גישה ופתחים —
  לא placeholder.
- **Parking / Garage** — חניה פתוחה, חניה מקורה ו-Garage כחלק מה-site planning. מידות, גישה
  מהרחוב, קשר לבית, orientation ומניעת חסימת כניסה.
- **Balconies / Patios / Outdoor Connections** — מרפסות, יציאה לגינה, patio, וקשר בין
  living/kitchen לשטח החוץ.
- **Hallways / Circulation Quality** — לא רק "יש גישה", אלא איכות circulation: רוחבים, אורך
  מסדרונות, מינימום שטח מבוזבז, junctions הגיוניים, dead-end detection.
- **Storage / Closets / Utility Spaces** — ארונות, pantry, utility closet, mechanical/service
  areas — אבל רק כאשר התוכנית או דרישת המשתמש מצדיקה אותם.
- **Kitchen / Bathroom fixture-aware planning** — לעבור מחדר מלבני בשם KITCHEN/BATHROOM לתכנון
  שיודע שיש fixtures וצריך clearance אמיתי סביבם.
- **Alternative Plans / Diversity** — עבור אותו brief לייצר 2–3 תוכניות שבאמת שונות בקונספט, לא
  אותה תוכנית עם mirror קטן. למשל central public zone, split-wing, L-massing וכו'.
- **Concept Quality / Decomposition Engine** — כנראה אחד המנועים החשובים ביותר. לשפר את השלב שבו
  מחליטים איך הבית מאורגן לפני שמתחילים לפתור coordinates.
- **Massing selection quality** — Rectangle/L/irregular צריכים להיבחר בגלל איכות התוצאה ולא כי
  "L יותר מעניין". לסגור גם את נושא eligibility-before-orientation שכבר זוהה.

## P2

- **Seam / Shape Recovery** — לשפר מקרים שבהם concept טוב נכשל בגלל realization/partition seam
  ולא בגלל שהתוכנית בלתי אפשרית.
- **Entrance Sequence Quality** — מעבר מ-"יש דלת חיצונית" ל-arrival sequence אמיתי: street →
  entrance → public circulation, בלי כניסה גרועה דרך אזור פרטי.
- **North / Orientation / Solar reasoning** — חץ צפון, façade orientation, כיוון חלונות ואזורים
  ציבוריים, וקבלת preference מהמשתמש בלי להמציא דרישה אם היא לא נמסרה.
- **Regulation / Compliance Engine** — להפוך את ה-RAG/Knowledge לחוקי validation אמיתיים:
  regulation source → typed rule → deterministic check → citation/report. ה-LLM לא מחליט אם תוכנית
  חוקית.
- **Clarification Agent** — לפני תכנון, לזהות מידע קריטי חסר ולשאול מעט שאלות טובות: מגרש, קומות,
  כניסה, orientation, parking, safe room וכו'. לא לשאול עשרים שאלות על כל brief.
- **Plan Editing / Conversational Changes** — "תזיז את חדר השינה מזרחה", "תגדיל מטבח ב-3 מ״ר",
  "תחליף בין חדרים" → proposal → validation → confirmation → version חדש.
- **Drag / Resize / Align UI** — עריכה חזותית שמשתמשת באותו deterministic spatial-edit API, ולא UI
  שמצייר משהו שה-backend לא מכיר.
- **ReviewPage completion** — לחבר את כל המידע החדש למשתמש: warnings, trade-offs, blocked
  changes, realized vs requested area, reasons for refusal.
- **Architectural Report / PDF output** — תוכנית + areas + orientation + assumptions + warnings +
  regulatory evidence + version metadata. בסוף גם PDF מקצועי.
- **SVG/DXF production quality** — קווים, wall thickness, doors, windows, dimensions, labels, north
  arrow, scale — renderer לא ממציא כלום.

## P3

- **Plan Retrieval / Reference Library** — מאגר גדול של תוכניות: retrieval לפי geometry/program
  ולא רק area, ואז adaptation מבוקר. אחרי שה-generator הנוכחי יציב יותר.
- **Plan Quality Evaluation / Benchmark** — benchmark קבוע שמודד לא רק planned/refused אלא
  architectural quality: circulation, wasted area, proportions, exterior exposure, privacy,
  adjacency ו-diversity.
- **Performance / Runtime** — אחרי שהאיכות נכונה: profiling, caching, candidate pruning,
  incremental validation, parallel execution איפה שבטוח.
- **Knowledge system follow-ups** — verified_checksum, persistent embedding model, retrieval
  latency, drift detection ושיפורי Knowledge נוספים — חשובים, אבל לא עוקפים את איכות המוצר.

## INFRA

- **Agent-Team / Telegram operational hardening** — לסיים את Telegram control plane,
  owner-controlled backlog, READY notifications, remote merge, pause/resume, audit ו-resource
  management. אחרי שזה יציב — לא לתת לתשתית להפוך שוב לפרויקט המרכזי.
