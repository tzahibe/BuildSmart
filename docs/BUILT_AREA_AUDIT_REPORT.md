# BUILT_AREA_AUDIT_REPORT

```
ROOT_CAUSE = GENERATOR_MINIMUM_BIAS
  contributing: VALUE_NOT_PROPAGATED (enabling condition)
  contributing: AREA_SEMANTICS      (contract ambiguity that the fix must resolve)
NOT the cause: FOOTPRINT_LIMIT, HARDCODED_DEFAULT
STATUS = confirmed, no code changed
```

**The bug is real and it is a correctness bug, not a tuning issue.** For a 2-bedroom programme the
generated house is **104.5 m² whether you ask for 150, 180 or 200 m²** — the same number to the
decimal. That figure is `Σ template target areas ÷ 0.90` for that programme and has nothing to do
with your input.

---

## The measurement

Same room programme, same 1:1 footprint proportion, only the requested area changes.

**2BR + 1 wet + open plan** — `Σ target_area_m2` = 94.0 → `target_gross` = **104.4 m²**

| requested | footprint | buildable | gross | net | Σ rooms | unused | gap |
|---|---|---|---|---|---|---|---|
| 120 m² | 10.95 × 10.95 | 119.9 | — | — | — | — | `PLAN_FAILED_VALIDATION` |
| 150 m² | 12.25 × 12.25 | 150.1 | **104.5** | 95.9 | 95.9 | 45.5 | −30.3% |
| 180 m² | 13.42 × 13.42 | 180.1 | **104.5** | 95.9 | 95.9 | 75.6 | −41.9% |
| 200 m² | 14.14 × 14.14 | 199.9 | **104.5** | 95.9 | 95.9 | 95.4 | −47.7% |

**3BR + safe room + 2 wet + open plan** — `Σ target_area_m2` = 123.5 → `target_gross` = **137.2 m²**

| requested | footprint | buildable | gross | net | Σ rooms | unused | gap |
|---|---|---|---|---|---|---|---|
| 120 m² | 10.95 × 10.95 | 119.9 | — | — | — | — | `PLAN_NOT_REALIZABLE` |
| 150 m² | 12.25 × 12.25 | 150.1 | — | — | — | — | `PLAN_NOT_REALIZABLE` |
| 180 m² | 13.42 × 13.42 | 180.1 | 159.5 | 144.3 | 144.3 | 20.6 | −11.4% |
| 200 m² | 14.14 × 14.14 | 199.9 | 153.7 | 138.7 | 138.7 | 46.2 | −23.2% |

Across the full supported scope (960 runs, 476 successes): **median gap −37.0%, worst −60.8%**, and
**461 of 476** plans came out more than 10% under the requested area.

The 3BR figures move a little only because the minimum-dimension floors force extra depth. They are
not tracking the request either — 180 → 159.5 but 200 → 153.7, which is *smaller for a larger
request*. The variation is search noise, not responsiveness.

---

## The seven questions

### 1. What does the UI field actually mean?

The label is **שטח הבנייה (מ״ר)**, and the codebase states its meaning twice, unambiguously:

- `frontend/src/design/footprint.ts:11` — *"TARGET BUILT AREA: `Project.built_area_m2` — the
  room-program area BUDGET the user requested."*
- `backend/app/projects/models.py:130` — the same four-concept distinction, naming it the
  **TARGET BUILT AREA**.

It is **not** the plot (that is `plot_area_m2`), and **not** the buildable envelope (setback- and
coverage-derived; deliberately not modelled anywhere yet).

The footprint step honours that meaning exactly: every preset is generated to that area, and the
backend re-validates it — `models.py:207-213` rejects a footprint whose real area drifts from
`built_area_m2` beyond a 0.5% tolerance.

**So the declared contract is TARGET BUILT AREA, and the whole flow honours it right up until
generation — where it is silently demoted to a maximum.** That is the `AREA_SEMANTICS` ambiguity:
the field means one thing in the form and the footprint step, and a different thing in the planner.

### 2. Where is that value stored?

`Project.built_area_m2: float = Field(gt=0)` (`app/projects/models.py:171`), persisted by
`repository.py:100`. It is also carried inside `Project.selected_footprint` as `target_area_m2`,
alongside the chosen `width_m` / `depth_m` / `area_m2`.

### 3. Does it reach ProgramSpec / the Concept Generator?

**ProgramSpec: no. There is no area field on it at all.**

```python
# app/vertical_slice/spec.py:39
class ProgramSpec:
    bedrooms: int = 3
    safe_room: bool = True
    open_plan_living: bool = True
    wet_rooms: int = 2
    parking_spaces: int = 2
```

`spec_for` (`app/demo/requirements_view.py:96`) builds `ProgramSpec` from counts only. The area is
never passed.

**Concept generator: only indirectly, and only as an upper bound.** The chain is

```
built_area_m2 → footprint width/depth → PlotSpec (+ setbacks)
              → _buildable_from → BuildableRegion (the footprint rectangle)
              → safe adapter candidate  → _build's max_width / max_depth
```

Measured for the 200 m² case: buildable rectangle **199.9 m²** → adapter candidate **198.8 m²**
(14.10 × 14.10, **retention 0.994**). The area is present and proven safe. The generator simply
does not use it.

`built_area_m2` also reaches `RequirementsReview` (`requirements_view.py:78`) but purely as a
display field.

### 4. Is the generator trying to hit the target, fill the footprint, or satisfy minimums?

**B — satisfy the template room areas.** Not A, not C. The evidence is the search itself:

```python
# app/vertical_slice/concept_generator.py:607
gross = target_gross_area_m2(rooms)        # Σ template target areas ÷ 0.90 — no user input
min_width = minimum_footprint_width_m(rooms)
...
w = min_width                              # walk UPWARD from the programme's own minimum
while w <= max_width and len(widths) < 14:
    widths.append(...); w += 0.5
for width in widths:
    base_depth = min(max_depth, gross / max(width, 1e-6))   # depth derived from `gross`
    ...
    if attempt is not None:
        footprint, plan = trial, attempt
        break                              # FIRST feasible proportion wins
```

Three compounding decisions, each individually reasonable:

1. `gross` is the **programme's** area, never the user's.
2. The width walk **starts at the minimum** (7.80 m for 2BR) and stops at the first success.
3. Depth is `gross / width`, and grows **only when the layout is rejected**, never to use space.

`general_pipeline.py:211-221` then takes the **first** candidate Geometry Core realizes
(`fast_path=True`). Nothing anywhere ranks candidates by area used or by fit to the request —
`ConceptCandidate` even carries `used_area_m2` and `unused_wing_area_m2`, and neither is read as a
selection criterion.

The result: the selected footprint acts as a **ceiling** ("do not exceed this"), while the
programme's template table acts as the **actual size**. Everything left over becomes garden.

### 5. Why do many runs converge near ~107 m²?

Because that is the 2-bedroom programme's own template sum, and nothing else:

```
LIVING 22.0 + DINING 14.0 + KITCHEN 13.0 + HALL 11.0
     + MASTER 15.0 + BEDROOM_1 12.5 + BATH_1 6.5      = 94.0 m² net
94.0 ÷ ASSUMED_EFFICIENCY (0.90)                       = 104.4 m² gross
```

Measured gross: **104.5 m²**. The 0.1 m² is grid rounding. A 2BR + 2 wet variant adds a second
bathroom and lands near 111 m², which is the ~107 you saw.

This number is a **fixed point of the room template table**. It is reached whenever the first width
in the walk is feasible — which for a small programme in a generous footprint is essentially
always.

### 6. Is any hard-coded / default / canonical area still affecting generation?

| Constant | On the demo path? | Effect |
|---|---|---|
| `ROOM_TEMPLATES` target areas | **yes** | **the de-facto fixed area budget — this is the driver** |
| `ASSUMED_EFFICIENCY = 0.90` | **yes** | converts that net budget to gross |
| `run_general(plot_size_m=(24.0, 28.0))` | no | `service.py` passes explicit values |
| `spec.demo_spec()` `PlotSpec(20, 24)` | no | canonical fixture, not reachable from `app/demo/` |
| `_FOOTPRINT_ASPECT_PREF = 0.82` | dead | the width search supersedes it |

**No stale canonical fixture area is leaking in** — the AST tests still hold. But the template table
functions as one: it is the only thing actually deciding how big the house is.

### 7. Which stage causes the gap?

`concept_generator._build` and `_front_band_concept` — the footprint proportion search. Ruled out:

- **Adapter** — delivers 198.8 of 199.9 m², retention 0.994. Not the constraint.
- **Geometry Core** — tiles whatever footprint it is handed *exactly*; `Σ rooms` equals `net` in
  every row of the tables above. It never loses area.
- **Review / spec_for** — carries the footprint through faithfully.
- **DemoDesign / renderer** — reports `gross_area_m2` correctly; the drawing is honest.

---

## Recommended smallest correct fix

**The requested area does not need to be plumbed anywhere.** The buildable rectangle already encodes
it faithfully (retention 0.994) and the generator already receives it as `max_width` / `max_depth`.
So the minimal fix is a **search-direction change**, not new state and not a new algorithm:

1. **Walk the footprint search down from the candidate, not up from the minimum.** In `_build`
   (and the equivalent loop in `_front_band_concept`), start at the candidate's own width/depth and
   step down toward `minimum_footprint_width_m`, taking the first proportion that plans. Same loop,
   same bound, same feasibility test, reversed order — the largest feasible house instead of the
   smallest. `scale_program` already absorbs surplus by elasticity, so the extra area goes to the
   living space rather than the safe room or the bathrooms.

2. **Refuse honestly when the programme cannot absorb the request.** Growth is capped at each
   template's `max_area_m2`, so every programme has a real ceiling — about **213 m² gross for
   2BR + 1 wet** (Σ `max_area_m2` = 192 m² net). Above it the house genuinely cannot use the area,
   and the correct product behaviour is to say so ("a 2-bedroom house cannot sensibly fill 260 m² —
   add a room or reduce the area"), not to return a 104 m² plan while reporting success.

3. **Resolve the semantic ambiguity in the UI, once the above lands.** With the fix, the field
   behaves as the codebase already declares it: a target the plan meets. Until then it silently
   means "maximum", which is what makes the current behaviour feel like a fixed number.

Expected effect: the −37% median gap collapses toward zero across the supported range, and the
success rate should rise as a side effect — many `PLAN_NOT_REALIZABLE` rejections today are the
search giving up after 14 width steps from an unnecessarily small starting point.

**Risk to watch:** Geometry Core tiles the footprint *exactly*, so a larger footprint must be fully
absorbable by the room targets. `scale_program` caps each room at `max_area_m2`, so above the
ceiling in (2) a residue would remain and the layout would fail. That is precisely why (2) is part
of the fix and not an optional extra.

No code changed. Stopping for review.
