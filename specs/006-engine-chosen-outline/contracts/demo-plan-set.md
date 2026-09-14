# Contract: Demo plan set and stream — additive changes

Applies to `POST /projects/{id}/design/demo` (JSON) and `POST /projects/{id}/design/demo/stream`
(server-sent events). Every field below is new and optional with a default; the existing shape is
unchanged, so current consumers keep working without modification.

## Request

No change to the payload. `ProjectCreate.selected_footprint` remains optional:

| `selected_footprint` | Meaning after this feature |
|---|---|
| omitted / `null` | main flow — the engine chooses the outline(s) |
| present (`PRESET` or `CUSTOM`) | advanced path — this outline is planned first and, if it plans, shown first |

Scope refusals: `FOOTPRINT_REQUIRED` is raised only for `shape_type != "RECTANGLE"` now. A request
whose requested area fits no outline inside the setbacks is refused with
`FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION` (text: the *area*, not a rectangle, does not fit) or
`NO_BUILDABLE_AREA`.

## `DemoDesign` — new fields

```json
{
  "...": "existing fields unchanged (rooms, walls, doors, footprint, validation, ...)",
  "outline": {
    "width_m": 12.35,
    "depth_m": 14.25,
    "area_m2": 175.99,
    "origin": "ENGINE"
  },
  "family": "V[H[B,B,S,W],H,H[P,P,M]]"
}
```

- `outline` — `null` only for callers that bypass the demo service. `origin ∈ {"ENGINE","PERSON"}`.
  The person-facing label is rendered from this object ("12.35 × 14.25 מ׳ · 176 מ"ר · מתאר שנבחר
  אוטומטית" / "המתאר שהזנת").
- `family` — opaque string for diagnostics and tests; clients MUST NOT parse it or show it.

## `DemoPlanSet` — new field

```json
{
  "plan": { "...": "DemoDesign" },
  "alternatives": [ { "...": "DemoDesign" } ],
  "search": {
    "outlines": [
      {"width_m": 12.35, "depth_m": 14.25, "origin": "ENGINE", "planned": true,  "plans_found": 3, "latency_ms": 1180.4},
      {"width_m": 13.59, "depth_m": 12.95, "origin": "ENGINE", "planned": false, "plans_found": 0, "latency_ms":  640.2}
    ],
    "total_latency_ms": 4210.9
  }
}
```

Guarantees:
- `plan` and every entry of `alternatives` passed the same validation and safety checks (unchanged).
- `len(alternatives) ≤ 2`.
- No two of `[plan, *alternatives]` share both `family` and `outline`.
- If the request carried `selected_footprint` and it planned, `plan.outline.origin == "PERSON"`
  and `plan` is byte-identical to today's response for the same request.

## Stream — event sequence

```
progress  {"outline": 1, "outlines": 4, "step": 1, "total": 6, "label": "בודקים את שטח הבנייה", "percent": 4}
progress  ...
plan      {"provisional": true, "design": { DemoDesign incl. outline }}      ← first validated plan, once
progress  {"outline": 2, "outlines": 4, ...}
...
done      { DemoPlanSet }                                                     ← exactly once
```
or `error {"code","message","detail"}` exactly once instead of `done`.

- `percent = round(((outline-1)*total + step) * 100 / (outlines*total))`.
- `plan` is emitted at most once, the first time any outline yields a validated plan. It is
  provisional: `done.plan` MAY be a different plan (a later outline nearer the requested area).
- Clients that ignore `plan` and the new `progress` keys behave exactly as today.

## Refusal text

`PLAN_NOT_REALIZABLE` no longer contains the sentence "מתאר של X×Y מ׳ … כן מתאפשר". When the
person supplied an outline that did not plan while an engine outline did, the response is a
**success** whose `plan.outline.origin == "ENGINE"` and whose `search.outlines[0]` (the person's)
has `planned: false`; the UI renders the note from that.

## Failure-log context

`_failure_context` gains `"outlines_tried": [{"width_m","depth_m","origin","planned"}]`; the
existing `footprint_width_m/depth_m` keys stay (null in the main flow).
