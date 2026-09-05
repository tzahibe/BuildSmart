/** Single source of truth for every room `type` string BuildSmart's backend can produce — the 14 real
 * Architect Model V1 room types (mapped to this snake_case vocabulary by `app/architect/adapter.py`'s
 * `_ROOM_TYPE_MAP` on the backend) plus `safe_room` (BuildSmart's own authoritative-only room type — see
 * `app/architect/authoritative_merge.py` — never produced by the model itself).
 *
 * `SketchSvg.tsx` and `TechnicalDetailsPage.tsx` both read `ROOM_LABELS` from here instead of keeping
 * their own copies, so a room type only needs a label added in one place. `SketchSvg.css` still owns the
 * per-type fill colors directly (as `.sketch-svg-room--<type>` rules) since colors are presentation, not
 * data — but every type listed here has a corresponding rule there; see that file's own completeness
 * fallback for any type this list doesn't yet know about. */
export const ROOM_LABELS: Record<string, string> = {
  bedroom: 'חדר שינה',
  master_bedroom: 'חדר הורים',
  bathroom: 'חדר רחצה',
  wc: 'שירותים',
  living_room: 'סלון',
  kitchen: 'מטבח',
  dining: 'פינת אוכל',
  balcony: 'מרפסת',
  corridor: 'מסדרון',
  entrance: 'כניסה',
  storage: 'מחסן',
  utility: 'חדר שירות',
  staircase: 'גרם מדרגות',
  parking: 'חניה',
  safe_room: 'ממ"ד',
}
