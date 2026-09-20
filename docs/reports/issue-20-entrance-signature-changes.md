# Issue #20 — entrance policy: primary-signature changes (AC-5)

Every corpus context whose realized primary changed shape (`layout_signature`) as a result of
the entrance arrival-room policy, with its entrance room before and after. Regenerated against
this branch's current HEAD (`ae73f9b`, the entrance-policy commits merged onto
`origin/integration/holiday-yom-kippur-2026`) using the same corpus (`tests/regression_corpus/
corpus.json`, 432 contexts) and the same replay path (`app.demo.service.generate_demo_design`)
the CI regression gate uses.

## Method

For every context, two runs of `generate_demo_design` were compared:

- **after** — this branch's code exactly as committed.
- **before** — the same commit, with the entrance-policy product change reverted in-process only
  for the duration of the comparison (`ENTRANCE_ZONE_PRIORITY` restored to its pre-#20 5-role
  tuple including DINING/KITCHEN, `ALLOWED_ENTRANCE_ROLES`/C23 widened to match so C23 does not
  gate a case it did not gate before, and `general_pipeline._entrance_rank` replaced with a
  constant so candidate selection stops at the first validating candidate exactly as it did
  before this Issue). This reconstructs "this branch's code minus only Issue #20's product diff"
  on the exact same merged base — the same comparison CI's gate-4 makes against the integration
  branch tip, since this branch's HEAD already contains every other change on that tip and
  nothing else differs.

A context counts as a primary-signature change when its `PLANNED` layout signature (every room's
type and rectangle) differs between the two runs. Every other regression-budget dimension was
also checked over the full 432-context corpus, matching CI's expected numbers exactly:

| Metric | Before → After |
|---|---|
| Planned | 404 → 404 |
| Refused | 28 → 28 |
| Crashes | 0 → 0 |
| LOST | 0 |
| GAINED | 0 |
| Status changes | 0 |
| Refusal-code changes | 0 |
| **Primary-signature changes** | **19** |

## The 19 changes

Every one is the candidate-ranking preference (Required behavior #2 / AC-3) taking effect: a
candidate that used to be the first to validate with a LIVING entrance is now passed over for a
better-ranked one. 17 of the 19 gained a HALL/CIRCULATION entrance where one exists; the
remaining 2 have no HALL/CIRCULATION-entrance candidate available for that brief, so the entrance
room itself is unchanged (still LIVING), but the ranking loop no longer stops at the literal
first validating candidate while still searching for a better rank, so a different LIVING-entrance
candidate was selected — a real (if cosmetic) primary-signature change with no entrance-room
change. **None of the 19 involves a kitchen or dining entrance in either direction** — the
pre-existing C16 check ("the entrance opens into the room it names") already excluded a
KITCHEN/DINING-entrance candidate from ever becoming a corpus primary, before this Issue existed.

| # | Context (bedrooms / wet_rooms / safe_room / open_plan / built_area_m² / plot W×D) | Before entrance | After entrance |
|---|---|---|---|
| 1 | 1 / 2 / safe_room=True / open_plan=False / 132.0 / 18.0×22.5 | LIVING | HALL |
| 2 | 2 / 2 / safe_room=False / open_plan=False / 132.0 / 18.0×22.5 | LIVING | HALL |
| 3 | 2 / 2 / safe_room=False / open_plan=True / 181.25 / 19.5×25.0 | LIVING | HALL |
| 4 | 2 / 3 / safe_room=True / open_plan=False / 200.0 / 17.0×30.5 | LIVING | HALL |
| 5 | 3 / 2 / safe_room=True / open_plan=True / 188.5 / 23.25×22.1 | LIVING | HALL |
| 6 | 3 / 3 / safe_room=True / open_plan=False / 200.0 / 17.0×30.5 | LIVING | HALL |
| 7 | 4 / 1 / safe_room=False / open_plan=False / 132.0 / 18.0×22.5 | LIVING | HALL |
| 8 | 4 / 2 / safe_room=False / open_plan=False / 200.0 / 17.0×30.5 | LIVING | HALL |
| 9 | 4 / 3 / safe_room=False / open_plan=False / 200.0 / 17.0×30.5 | LIVING | HALL |
| 10 | 4 / 1 / safe_room=False / open_plan=True / 216.0 / 19.0×28.5 | LIVING | HALL |
| 11 | 5 / 1 / safe_room=True / open_plan=False / 181.25 / 19.5×25.0 | LIVING | HALL |
| 12 | 5 / 2 / safe_room=True / open_plan=False / 181.25 / 19.5×25.0 | LIVING | HALL |
| 13 | 5 / 3 / safe_room=True / open_plan=False / 216.0 / 25.0×22.5 | LIVING | LIVING (candidate swapped; room unchanged) |
| 14 | 5 / 3 / safe_room=False / open_plan=False / 216.0 / 19.0×28.5 | LIVING | HALL |
| 15 | 5 / 2 / safe_room=False / open_plan=True / 216.0 / 19.0×28.5 | LIVING | HALL |
| 16 | 6 / 1 / safe_room=False / open_plan=False / 181.25 / 19.5×25.0 | LIVING | HALL |
| 17 | 6 / 1 / safe_room=True / open_plan=False / 181.25 / 19.5×25.0 | LIVING | HALL |
| 18 | 6 / 3 / safe_room=False / open_plan=False / 216.0 / 25.0×22.5 | LIVING | HALL |
| 19 | 6 / 2 / safe_room=True / open_plan=False / 216.0 / 25.0×22.5 | LIVING | LIVING (candidate swapped; room unchanged) |

All 19 contexts have `street_facing_side=NORTH`, `footprint_width_m`/`footprint_depth_m` matching
the built area 1:1 with the plot dimensions above (the corpus does not vary footprint shape
independently of area for these cases).

**Row count: 19 — matches the regression report's `primary_signature_changes` count exactly.**

No context lost its plan (LOST=0): every candidate that used to plan a KITCHEN/DINING-entrance
primary under the old, wider `ENTRANCE_ZONE_PRIORITY` was, in fact, never the corpus primary to
begin with (see above), so narrowing the policy never removed anyone's only working candidate on
this corpus. Consequently there is no PROPOSED FOLLOW-UP (foyer synthesis) case to report from
this corpus; the Wiki's foyer-synthesis section documents the follow-up for a future context that
might need it.
