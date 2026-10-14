# Architecture Decision Report — why BuildSmart's plans are architecturally weak, and what would change it

**Investigation only. No production code was changed.** Everything below is measured on `main`
(`55d1048`) through production's own entry points, or cited from an existing merged report.

---

## 1. Executive diagnosis

BuildSmart does not have an architectural design system with a weak concept stage. It has a
**constrained room-packing system with an architectural vocabulary bolted on afterwards**, and the
vocabulary describes the output rather than producing it.

Three structural facts, each measured, explain everything the owner observed in the B06 comparison:

1. **The only layouts the engine can express are guillotine partitions.** All 8 delivered plans are
   guillotine-separable, with 2–4 straight lines cutting each house from envelope to envelope. The
   same test on real professional plans returns **0 of 19**. The engine is not producing weak
   examples of real plans; it is producing a different family of drawings.
2. **The concept the engine chooses is "which rooms go in the west column and which in the east".**
   `concept_generator._allocations` returns at most five such allocations. Everything a person would
   call a concept — massing, entrance, orientation, circulation shape, indoor/outdoor — is either
   fixed by construction or derived after geometry exists.
3. **The objective is area proximity.** The generator's sort key begins with
   `|used_area − target_area|` and, once that and two fallback flags tie, falls through to the
   *alphabetical strategy name*. No architectural term appears in the key at all. Measured on the
   candidate pools: area is the largest single first-separator on 7 of 7 briefs that produce
   candidates, and the strategy name is the second largest.

The consequence is that #185's BRANCHED plan and the production SPINE plan really do look the
same. #185's was a bespoke, hand-built tree rather than one of the five allocations — but it is
still a *slicing tree*, on the same footprint chosen the same way, with the same post-hoc entrance,
the same leftover garden and the same area objective. Only the access graph differed. **Changing
the access graph was never going to produce a different building** — which is exactly the owner's
instruction not to equate the two, stated here as a measured result rather than as a caution.

The single most damning measurement is not a topology number. It is this:

> On **7 of 8 briefs no public room touches the garden at all**, while on **8 of 8 the bathrooms
> do**. On B06 the master bedroom gets the garden and the living room gets the parking. On B09 the
> largest garden-facing element in the house is a **54.3 m² block of unassigned area**.

No validator notices this, no score penalises it, and no stage ever decided it. It is a by-product
of tiling a rectangle. That is what "architecturally weak" means here, in a form that can be
measured and therefore fixed.

**What to do.** The target architecture is *concept-first*: a concept becomes a typed INPUT that
constrains realization, rather than a label computed from a realized plan; outdoor space becomes a
programme element rather than leftover; and selection becomes a Pareto profile over named
architectural measures rather than a scalar dominated by area. Most of the machinery needed already
exists on `main` and is wired to nothing. The recommended first experiment (§10) isolates exactly
one hypothesis from that architecture, costs little, and produces an owner-visible A/B on the
existing preview.

---

## 2. Root causes, with code evidence

Proven = measured in this investigation or in a cited merged report. Hypothesis = plausible and
untested, labelled as such.

### P1 — Geometry Core can only express guillotine partitions *(proven)*

`geometry_core.engine.solve_fixture` walks a binary slicing tree (`Split(Cut.V|Cut.H, a, b)`), so
"every partition is a straight cut across a subtree". `rectilinear_realizer.py`'s own header states
the measured consequence: **1 of 199 real plans qualifies**; the full investigation
(`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §3.2) measured 19 plans in detail and found
**19/19 non-guillotine (0% separable)**.

Measured here on what BuildSmart actually delivers (`app/ai_harness/arch_direction/separability.py`):

| brief | rooms | full-span x-cuts | full-span y-cuts | guillotine-separable |
|---|---:|---:|---:|---|
| B08 | 8 | 2 | 0 | **yes** |
| B20 | 10 | 2 | 0 | **yes** |
| B02 | 7 | 3 | 0 | **yes** |
| B11 | 11 | 3 | 0 | **yes** |
| B16 | 13 | 4 | 0 | **yes** |
| B19 | 12 | 2 | 1 | **yes** |
| B06 | 8 | 2 | 0 | **yes** |
| B09 | 9 | 2 | 0 | **yes** |

8/8 versus 0/19. This is the deepest cause: no amount of concept work changes the drawing family
while the realizer is a slicing tree. **It is also already solved and unwired** — see §6.

### P2 — The concept space is a two-column allocation *(proven)*

`concept_generator._allocations` returns at most five `(strategy, west_rooms, east_rooms)` tuples:
public-vs-private, double-loaded, wet-clustered, balanced-by-row-count, bedrooms-opposite. Each is
then built as *rows stacked in two columns beside a hall*. `BRANCHED_TWO_STACK` — the name that
sounds like a different parti — is item 5 of that list: "bedrooms grouped opposite public and
service". It is a column allocation, not a circulation topology.

`FRONT_PUBLIC_BAND` is the one genuinely different arrangement, and its tree is one line:

```python
tree = Split(Cut.H, band_tree, rear, m_to_u(band_depth))   # concept_generator.py:3250
```

The public band is the *first* (street-side) child of a single horizontal split. There is no
rear-band variant anywhere in the module. §10 uses exactly this.

### P3 — The objective is area, then alphabetical order *(proven)*

`generate_concepts`'s sort key is `(|used_area − target|, fallback_tier, over_preferred, used_area,
strategy.value, priors…)`. The two priors are off by default and documented as 0/404 no-ops. So
after area, candidates are ordered by **the strategy's name in alphabetical order**.

Measured — which key component first separates each adjacent pair in the delivered ordering
(`app/ai_harness/arch_direction/decisions.py`):

| brief | candidates | ranked | area_delta | over_preferred | fallback_tier | strategy name | fully tied |
|---|---:|---:|---:|---:|---:|---:|---:|
| B08 | 30 | 30 | **9** | 0 | 6 | 8 | 6 |
| B20 | 12 | 12 | **5** | 0 | 0 | 6 | 0 |
| B02 | 10 | 10 | **9** | 0 | 0 | 0 | 0 |
| B11 | 74 | 46 | **23** | 4 | 0 | 18 | 0 |
| B19 | 8 | 4 | **3** | 0 | 0 | 0 | 0 |
| B06 | 82 | 60 | **27** | 4 | 0 | 16 | 12 |
| B09 | 56 | 50 | **31** | 0 | 0 | 18 | 0 |

`general_pipeline.run_general`'s own selection adds entrance rank first and then, strictly below
area proximity, `entrance_sequence_prefers` and `composition_prefers` as tie-only terms. #142M
measured those two across 206 real pairs: **0 / 0 / 0 first-separations** for composition,
wet-privacy and suite quality, against 63–64 % for area delta
(`docs/reports/142m-realized-selection/`). The architectural terms exist and essentially never fire.

### P4 — There is no indoor/outdoor relationship anywhere in the system *(proven)*

`site.classify_garden` is explicit that garden is *the plot's leftover area*, computed after the
footprint is placed. Searching the vertical slice for consumers of `garden` finds the renderer, the
payload, C12 ("outdoor regions explicitly classified" — a bookkeeping check), one L-parti comment
and `wet_privacy`'s tiebreak. **No stage places a room with respect to the garden, and no check or
score asks whether a public room reaches it.**

Measured on the delivered plans:

| brief | public rooms | public rooms touching the garden | public rooms on the street only | wet rooms touching the garden |
|---|---|---|---|---|
| B08 | LIVING, DINING, KITCHEN | KITCHEN | LIVING | BATH_1 |
| B20 | LIVING, DINING, KITCHEN | **none** | LIVING | BATH_1, BATH_2 |
| B02 | LIVING, DINING, KITCHEN | **none** | LIVING | BATH_1 |
| B11 | LIVING, DINING, KITCHEN | **none** | LIVING | BATH_1, BATH_2 |
| B16 | LIVING, DINING, KITCHEN | **none** | LIVING, DINING, KITCHEN | BATH_1, BATH_2 |
| B19 | LIVING, DINING, KITCHEN | **none** | LIVING, DINING, KITCHEN | BATH_1, BATH_2 |
| B06 | LIVING+KITCHEN | **none** | LIVING+KITCHEN | BATH_1, BATH_2 |
| B09 | LIVING+KITCHEN | **none** | LIVING+KITCHEN | BATH_2 |

B06's room-by-room exposure makes the point concrete:

| room | area m² | aspect | envelope faces |
|---|---:|---:|---|
| HALL | 17.48 | **10.35** | street, rear |
| MASTER | 16.80 | 1.87 | **rear (the garden)** |
| BEDROOM_1 | 13.13 | 1.94 | street, east |
| BEDROOM_2 | 13.39 | 1.98 | east |
| BATH_1 | 8.40 | 1.07 | **rear**, west |
| BATH_2 | 7.93 | 1.17 | **rear**, east |
| FLEX (unassigned) | 27.62 | 2.62 | west |
| LIVING+KITCHEN | 58.65 | 1.21 | **street**, west |

The master bedroom and both bathrooms get the garden; the 58.65 m² living/kitchen gets the street
and the parking. Nothing in the system had an opinion about that.

### P5 — The entrance is derived after geometry, not designed *(proven)*

`doors.resolve_entrance` reads the realized rectangles and picks whichever room already touches the
footprint's `y = min` edge, in role priority order (HALL, CIRCULATION, LIVING). Its own docstring
explains that it replaced a worse defect, and it is the right *repair*. But it means the entrance
sequence — which an architect designs first — is in BuildSmart a consequence of row ordering.
`EntranceSide` exists as an enum in `concept_spec.py` **with no field on `ConceptSpec`** (#182).

### P6 — Massing is committed first, on information that contains no architecture *(proven)*

The commitment order is:

1. `demo/site_geometry.feasible_options` enumerates up to 4 outlines of the requested area at fixed
   proportions `PREFERRED_RATIOS = (0.95, 1.15, 0.75, 1.45)`, plus up to 3 L massings.
2. `service._plan_outlines_until_one_plans`: *"The person's outline is authoritative: when they gave
   one and it plans, the engine's outlines are not run at all."* #182 measured that every audited
   project carries a selected footprint, so **one outline is planned on 6 of 8 briefs** and the two
   L massings are never tried. `massing_signature` is `1W` on all eight.
3. `safe_adapter.adapt` reduces the buildable region to maximal inscribed rectangles; the generator
   then uses `primary = usable[0]` — **the largest rectangle only** — for every one-wing strategy.
4. `choose_footprint` takes a sub-rectangle at a constant aspect preference (`_FOOTPRINT_ASPECT_PREF
   = 0.82`), **anchored to the street edge and centred across it**.

By the time any room is placed, the building's shape, proportion and position are fixed by area
arithmetic and one constant. None of these four steps can see the programme's organisation, the
garden, orientation, or the brief's intent.

### P7 — The concept vocabulary is computed *from* candidates, not used to produce them *(proven, #182)*

`concept_spec.concept_spec_of(candidate)` derives a `ConceptSpec` from an already-built candidate.
Concept Engine v2's S2 **filters the candidates the existing generator already built** down to those
whose declared class matches a pattern. The direction of dependency is backwards from what the name
suggests. #182's headline: **82 candidates on B06 → 1 topologically distinct concept**; and
`compile_hub_lobby`/`compile_branched` returned 0 candidates on 8/8 briefs.

### P8 — The LLM proposal layer does not widen the concept space either *(proven, measured here)*

The 20 frozen LLM-generated proposals (`backend/tests/fixtures/frozen_briefs_142.json`) are the one
place in the system where a model expresses architectural intent. Measured:

- **20/20 proposals contain exactly one circulation room.**
- In **19/20** that single HALL is the (joint) highest-degree node in the access graph — up to
  degree 12. The proposals are hub-and-spoke stars around one corridor.
- **0/20 contain any outdoor room** — no courtyard, terrace, patio or porch exists in the
  vocabulary the proposer writes in.

So the "brain" proposes the same hub-and-spoke corridor house the deterministic generator builds.
**Approach B as currently constituted is not a source of architectural diversity.** This is a
finding about the representation the LLM is asked to fill in, not about LLMs.

### P9 — Circulation is a residual slot, not a designed space *(proven)*

Measured hall aspect ratios on the delivered plans: **7.85, 8.58, 9.00, 9.75, 10.35, 11.12, 11.46,
11.92**. Every one is a single full-depth corridor running street-to-garden, 8–12 % of the house.
`ROOM_TEMPLATES[HALL].max_aspect_ratio` is 8.0, and six of the eight exceed it — because **C20
excludes circulation on purpose**, in its own words: *"Circulation is excluded on purpose: a
corridor is a strip by definition, and its width is what C14 measures."*

That exclusion is a deliberate, defensible decision for a *corridor*. But it is also the moment the
system stops being able to ask whether circulation is a place. C14 measures a width, C26 catches
only extremes, and nothing anywhere asks whether the house's circulation is a space a person would
want to be in. There is no representation of *circulation as a place* — only of corridor as a
tolerated residue.

### P10 — The validators are a correctness system, and correctly so *(proven)*

32 checks run on every plan (C1–C31 and C33; C32 is unused). Classified by what they assert:

| what the check asserts | checks |
|---|---|
| geometric/structural correctness | C1, C2, C7, C13, C22, C27, C33 |
| programme and code compliance | C3, C4, C9, C14, C17, C19, C21, C24, C30 |
| access and safety | C5, C10, C11, C15, C18, C28, C31 |
| bookkeeping/disclosure | C6, C12, C16, C23 |
| **quality-adjacent, binary** | C8 (a window exists), C20 (aspect cap), C25 (entrance pocket), C26 (extreme corridor), C29 (wet privacy) |
| **architectural quality** | *none* |

This is not a defect. Validators should be fail-closed correctness gates. The defect is that
**nothing else exists**: there is no layer that says a plan is *good*, so "passes 27 validators" has
been doing work it was never designed to do. The owner's instruction — do not infer architectural
quality from validator PASS — is the correct reading of this table.

### Hypotheses, explicitly not proven

- **H1.** Making orientation an explicit concept dimension changes the delivered plan on a majority
  of briefs. *(This is what §10 tests.)*
- **H2.** `rectilinear_realizer` can carry a real brief end to end. It is gate-passed on its own
  constructions and on hand-encoded layouts; **no brief has ever been realized through it.**
- **H3.** The courtyard partis in §9 are realizable at these areas and envelopes. Untested; a
  courtyard removes area from the programme and the engine has no outdoor-room type.
- **H4.** A Pareto profile would surface plans a person prefers. Needs the calibration set in §8.

---

## 3. Investigation 1 — the decision inventory

Every decision the pipeline makes, where it is made, what it can see, and whether it can be revised.

| # | decision | where | information available | reversible? | constrains later stages | intent preserved? |
|---|---|---|---|---|---|---|
| 1 | building outline W×D | `demo/site_geometry.feasible_options`, `l_massings` | requested area, buildable rectangle | **no, in practice** — the person's outline short-circuits the survey (6/8 briefs) | everything | no architectural intent exists yet |
| 2 | which safe rectangle | `safe_adapter.adapt` → `usable[0]` | rectangle areas | no — only the largest is used by one-wing strategies | wing count, L eligibility | n/a |
| 3 | footprint sub-rectangle | `concept_generator.choose_footprint` | target gross area, one aspect constant 0.82 | no, within a candidate | every room's available depth | n/a |
| 4 | public/private zoning | `_allocations` (≤5 allocations) | room groups only | **yes** — all are generated and ranked | row structure | partially: "public together, bedrooms grouped" is encoded in comments and in the allocation list |
| 5 | circulation | implied by the parti | — | **not a variable** | the whole plan | lost: a hall column/band is assumed, never chosen |
| 6 | room adjacency | `_rows_of`, `_orient_row`, `_daylight_order` | row membership, C8 risk | yes, by candidate | door graph | partial: adjacency is a side effect of row order |
| 7 | room dimensions | `scale_program`, `_row_depths`, `ROOM_TEMPLATES` | areas, min short side, aspect caps, elasticity | yes (tiers, quality twin) | validation outcomes | **preserved well** — this layer is genuinely good |
| 8 | wet-room organisation | `programme_variants`, `wet_rooms.resolve_wet_rooms` | declared ensuites, counts | **yes** — real variants are generated | row pairing | **preserved** |
| 9 | entrance | `doors.resolve_entrance` — **after realization** | realized rects, role priority | no — geometry already exists | nothing; it is last | **lost**: the entrance sequence is a consequence, not a choice |
| 10 | garden / outdoor | `site.classify_garden` — **after placement** | plot minus footprint minus parking | no | nothing | **absent**: never an input |
| 11 | daylight / orientation | `_daylight_order` (a C8 rescue), C8 (binary) | which rows risk enclosure | yes | window feasibility | **near-absent**: one rescue heuristic, no orientation objective |
| 12 | alternatives | `_alternative_plans` / `concept_engine_v2.plans_per_class` / `service._select_plans` | realized plans, family and massing signatures | n/a | what the person sees | partial: de-duplication is correct, but the pool holds one topology (#182) |

**Does the system commit to geometry too early? Yes — decisions 1–3 are exact geometry chosen
before any architectural question is asked**, and they are the decisions that cannot be revised. The
decisions that *are* reversible (4, 6, 7, 8) are the ones that matter least to how the house reads.

There is also almost no feedback. The only loops that exist are `_guard_demoted_hub` and
`_prefer_quality_twin` — single-step comparisons of two already-realized plans — and
`concept_score.adapt`, a bounded ladder that only runs inside Concept Engine v2 (flag off). There
is **no repair**: a candidate that fails validation is discarded, never adjusted.

---

## 4. Investigation 2 — why the output resembles rectangular packing

Against the owner's own candidate list:

| candidate cause | verdict | evidence |
|---|---|---|
| premature footprint selection | **proven, decisive** | P6: outline → largest rect → aspect 0.82, all before any room |
| fixed room bands | **proven** | P2: rows spanning a column's full width; `band_embedding` widens this family but is unwired |
| guillotine-style subdivision | **proven, deepest** | P1: 8/8 delivered vs 0/19 real |
| hand-authored circulation templates | **proven, but a symptom** | `compile_hub_lobby`/`compile_branched` return 0 on 8/8 (#182); #183 proved the hub's 2-bedroom ceiling is geometric, not arbitrary |
| insufficient architectural intent representation | **proven** | P7: `ConceptSpec` is derived from candidates; `MasterPlacement`/`EntranceSide` have no field |
| weak public/private organisation | **not proven — this part works** | zoning is a real variable with five allocations; the audit found arrival quality good on 7/8 |
| missing indoor/outdoor relationships | **proven, and the most visible to a human** | P4: 7/8 no public room at the garden, 8/8 wet rooms at it |
| inadequate exploration of alternatives | **proven, but downstream** | 82 candidates → 1 topology (#182): the pool is large and homogeneous, so more search would not help |
| objectives rewarding validity over quality | **proven** | P3 + P10: the generator ranks on area, and PASS is the only quality signal that exists |

Two of the owner's hypotheses deserve correction:

- **"Weak public/private spatial organisation" is not a cause.** It is the one architectural
  dimension the engine genuinely varies and the audit found it competent.
- **"Hand-authored compilers" is a symptom, not a cause.** More compilers would each hit the same
  wall #183 measured for HUB_LOBBY: a compact lobby's longest face is 4.90 m and a bedroom consumes
  2.80 m of it, so exactly two bedrooms fit. That is a *geometry representation* limit expressing
  itself as a compiler limit. Writing a third compiler would buy one more special case.

---

## 5. Investigation 3 — what a concept must represent

A concept is worth representing explicitly when (a) a human architect decides it before drawing,
(b) it changes the plan in a way no later stage can recover, and (c) it is checkable. On that test:

### Must be explicit (an INPUT that constrains realization)

| dimension | why it cannot be derived | exists today? |
|---|---|---|
| **massing / parti** (single volume, L, C/courtyard, two volumes + link) | determines every room's possible exposure; cannot be recovered after a footprint is fixed | partly — `l_massings` exists and is never reached |
| **orientation of the public zone** (street / garden / court) | the single measured defect in P4; invisible to every later stage | **no** |
| **entrance sequence** (direct / foyer / court / side) | an architectural decision with a real sequence of spaces | `EntranceSide` enum only, **no field**; `entrance_strategy` holds a zone id |
| **circulation type AND its spatial character** (slot, gallery, room, loop) | determines whether circulation reads as space or residue | class exists; *character* does not |
| **outdoor rooms** (courtyard, terrace, entry court) as programme with area and adjacency | cannot emerge from leftover classification; must consume area | **no** |
| **public/private zoning split** | already explicit | yes — keep |
| **wet-core grouping** | already explicit and good | yes — keep |

### Can be derived (do not represent twice)

Room adjacency beyond the concept's required contacts; exact room dimensions and proportions (the
template/elasticity layer is the system's strongest component); door positions and swings; window
placement; the access graph's leaf edges; family and massing signatures.

### Should stay flexible during realization

Which side of a corridor a given bedroom lands on; the exact split ratio between two columns; the
depth of a band within its feasible interval; wet-room pairing among brief-legal variants; the
footprint's exact proportion **within a parti-compatible interval** (today it is a single constant).

### The shape this implies

```
brief ──► CONCEPT (typed, explicit, several)                    ← new: an input, not a label
            parti · public orientation · entrance · circulation
            character · outdoor rooms · zoning · wet core
          │
          ├─► MASSING chosen BY the concept (not by area arithmetic)
          ├─► required contacts + access graph derived from the concept
          ├─► EXACT EMBEDDING (band_embedding today; + pinwheel / GridWing later)
          ├─► EXACT SIZING (band_sizing / templates — unchanged)
          ├─► REALIZATION (_realize — unchanged)
          └─► VALIDATORS (unchanged, fail-closed)
                          │
                          └─► PROFILE (§8), not a scalar → portfolio of distinct concepts
```

Note what is *not* in this diagram: a new realizer, a new validator, a weakened constraint, or a
third compiler.

---

## 6. Investigation 5 — the existing assets

| component | disposition | why |
|---|---|---|
| **Geometry Core** (`geometry_core/`) | **preserve, decouple** | exact, deterministic, trusted. But it is the guillotine constraint (P1). It must stop being the *only* realizer — not be replaced. |
| **Validators** (`validation.py`, 32 checks) | **preserve unchanged** | fail-closed correctness is exactly right. Never a quality layer. |
| **`ROOM_TEMPLATES` + sizing/elasticity/quality tier** | **preserve** | the system's best component; it already encodes real architectural size knowledge |
| **`rectilinear_realizer.py`** (pinwheel, notch-carve L/U/T, GridWing) | **wire, carefully** | on `main`, gate-passed, **zero callers**. The one asset that attacks P1 directly. Caveat: notch-carve produces L-shaped rooms, which the owner has excluded; **pinwheel and GridWing do not** and should be wired first. |
| **`band_embedding` / `band_sizing` / `band_pipeline`** | **extend and wire** | an *exact, complete* decision procedure for the band family with typed refusals. This is the right shape for a concept→geometry stage. Its ceiling: every room spans its band's full depth — wider than today's two columns, still not a courtyard. |
| **`proposal_critic` (#142J)** | **preserve, promote** | deterministic pre-geometry invariants with typed HARD/WARN findings and no repair. Exactly the gate a concept layer needs. Reusable unchanged for concepts. |
| **`proposal_selection` (#142O)** | **extend** | realize-all-then-rank is the right control flow. Its ordering needs the §8 profile instead of arrival-rank-then-score. |
| **`concept_spec.py` vocabulary** | **extend** | the right nouns. Add the missing fields (`master_placement`, `entrance_side`, orientation, outdoor rooms) and **invert the dependency**: build candidates *from* a spec. |
| **`concept_patterns.py` prior** | **preserve, re-point** | a defensible evidence-cited prior over concepts. #182 showed it asks for HUB_LOBBY first on 8/8 and is ignored because nothing can build one. |
| **`concept_score.py` + `adapt`** | **replace the scalar, keep the loop** | the weighted total is exactly what the owner forbids presenting as objective quality. The *measure → adapt → re-realize* loop is the right control structure. |
| **`concept_engine_v2.py`** | **re-scope** | it is an alternatives *selector* over a pool it does not control. Keep as the portfolio/de-duplication stage; stop expecting it to create concepts. |
| **LLM proposal generation (#142K)** | **re-prompt, do not retire** | P8: the current representation forces one-hall star topologies. The LLM is being asked to fill in a form with no space for a concept. |
| **`stage2/contract.py` + the #109 retrieval POC** | **preserve, revisit later** | types-only on `main`; the retrieval/donor-adaptation approach is a credible Approach E (§7) and the most under-explored. *(Note: `docs/stage2/CONTRACT.md` is stale — it says `realize_layout` never passes `wet_rooms` to `validate`; on `main` it does, `rectilinear_realizer.py:1372`.)* |
| **`DemoPlan` renderer** | **preserve** | #179/#180 established it as the evidence baseline and fixed legibility. It is the owner-visible surface for every experiment below. |
| **`circulation_prefers`** | **deprecate as an ordering key** | #142N proved it is a veto reused as a preference, non-transitive, with an undocumented `area` disjunct. Keep as explanatory data (#142O already does). |
| **`hub_guard` / `l_massing_guard` / quality twin** | **preserve for now, fold in later** | each is a correct single-purpose repair; collectively they are the symptom of having no profile. The §8 profile should eventually subsume them. |

**Nothing above is recommended for a rewrite.** The two components that must change in kind are the
*direction* of the concept dependency (P7) and the *content* of the objective (P3) — both are
additive changes to existing modules.

---

## 7. Investigation 4 — comparison of generation strategies

Scored against the owner's criteria. ●●● strong, ●● adequate, ● weak.

| | **A** more deterministic compilers | **B** LLM intent → constraint realization | **C** hierarchical procedural (site→massing→zones→circulation→rooms) | **D** hybrid search: generate → realize → evaluate → refine | **E** case-based: retrieve real plan → adapt → realize |
|---|---|---|---|---|---|
| architectural diversity | ● bounded by what is hand-written; #183/#182 showed each compiler covers ~1 programme shape | ●● *as currently represented, ●* — P8: 20/20 one-hall stars, 0 outdoor rooms | ●●● massing and orientation become variables | ●● amplifies whatever the generator offers; cannot create a family | ●●● inherits real partis, including non-guillotine ones |
| geometric feasibility | ●●● proven by construction | ●● needs a critic + exact embedder (both exist) | ●● each level must guarantee the next is solvable | ●●● realizes before judging | ● adaptation to a different envelope/programme is the hard, unsolved part |
| exact dimensions | ●●● | ●●● via `band_sizing` | ●●● | ●●● | ●● |
| constraint preservation | ●●● | ●● critic is deterministic; the model can still propose the impossible | ●●● | ●●● | ● #109's `preservation.py` reports **136 lost facts**, 38 of them from a donor-correspondence lookup bug alone |
| computational cost | ●●● cheap | ●● one model call per brief | ●● bounded | ● the expensive one: realize-many | ●● retrieval is cheap, adaptation is not |
| maintainability | ● each compiler is a special case that must be kept alive | ●●● prompt + schema | ●● clear stage boundaries | ●●● mostly orchestration | ● a corpus and its licensing become a dependency |
| scales to complex programmes | ● **disproven** — #183: HUB_LOBBY supports exactly 2 bedrooms | ●● | ●●● | ●●● | ●● |
| compatible with Geometry Core | ●●● it *is* Geometry Core | ●●● through the band path | ●● needs non-guillotine families for C/courtyard partis | ●●● | ● real plans are non-guillotine by measurement |
| meaningful alternatives | ● | ●● | ●●● alternatives differ at the massing level | ●●● but only over a diverse pool | ●●● |

**Conclusion: C as the spine, D as the control loop, B as a proposer over C's vocabulary, A kept
only for what already exists, E as a research track.**

The reasoning, stated as a disagreement with each pure option:

- **Not A.** The evidence is already in: #183 measured the hub's ceiling as a geometric fact and
  #185 needed a bespoke tree to make one BRANCHED plan validate on one brief. Each compiler is one
  brief shape. The owner's instruction not to add another is supported by measurement.
- **Not B alone.** P8 is decisive: the model already produces the same topology the deterministic
  engine does. An LLM cannot propose a courtyard house into a schema with no outdoor room. B becomes
  valuable *after* C defines a vocabulary worth filling in — and then it is cheap and high-value,
  because proposing a parti is a judgement task and solving geometry is not.
- **Not C alone.** Hierarchical generation with no feedback simply moves the premature-commitment
  problem up a level: massing chosen before rooms are known fails the same way footprint-before-
  programme fails today. It needs D's loop.
- **Not D alone.** D over today's pool is 82 candidates and one concept. Search amplifies a
  generator; it does not give it a new family.
- **E is the most under-explored and the highest-variance.** It is the only approach that would
  import real non-guillotine partis wholesale. It also has the weakest evidence here, a corpus
  dependency, and an unsolved adaptation problem. Recommended as a *parallel research track*, not as
  the spine.

---

## 8. Investigation 6 — an architectural quality framework

**Principle: no weighted total.** #142N proved what happens when a disjunctive veto is reused as a
preference, and `concept_score`'s weighted sum is exactly the artefact the owner forbids presenting
as objective quality. The framework below produces a **profile**: a named vector of measures, each
individually meaningful, compared by **Pareto dominance** with explicit, declarable priority only
where a product decision has actually been made.

| # | criterion | measure | deterministic? |
|---|---|---|---|
| 1 | geometric correctness | the 32 validators, unchanged | **yes** — already exists, fail-closed |
| 2 | architectural functionality | furnishability (C30), clearances, wet access (C17), safe-room compliance (C4) | **yes** — already exists |
| 3 | spatial organisation | zoning purity: fraction of private rooms reachable without crossing a public room; wing coherence | **yes** — new, cheap, from the door graph |
| 4 | circulation quality | circulation share; longest segment; dead ends; **hall aspect**; *and* "is any circulation space ≥ a given short side" (slot vs room) | **yes** — `circulation_metrics` has most of it; use as a profile, never as the non-transitive `circulation_prefers` |
| 5 | public/private relationship | arrival rank (exists); buffer depth between entrance and the first private door; acoustic adjacency count (bedroom sharing a wall with a public room) | **yes** |
| 6 | **indoor/outdoor** | public-room garden frontage in metres; fraction of public area with garden exposure; wet/service area occupying garden frontage; outdoor rooms realized | **yes** — new, and the measure P4 shows the system most needs |
| 7 | daylight and orientation | exterior faces per room; rooms with one face only; glazing orientation relative to the plot's declared north | **yes** for exposure; orientation needs a real north on the brief, which the system does not model today |
| 8 | space utilization | gross vs programme capacity; unassigned (FLEX) area as a share; circulation share | **yes** — already computed; #180 already discloses it |
| 9 | architectural diversity | pairwise `topologically_distinct` over the shown portfolio; massing diversity; concept-dimension coverage | **yes** — exists, currently returns 1 |
| 10 | visual and experiential quality | sequence legibility, proportion of principal rooms, how the plan *reads* | **no — expert judgement** |

**Separation of duties**: 1–2 are gates (pass/fail, fail-closed). 3–9 form the profile and are
compared by dominance. 10 is never automated and never scored; it is the *calibration input*.

**How to keep 3–9 honest.** Build a calibration set: 30–50 plans (BuildSmart output plus the
professional reference set already documented in the #179 audit) rated pairwise by a residential
architect on criterion 10. Then measure which of 3–9 *predict* the human preference. A measure that
predicts nothing is removed, not weighted. This is the only defensible way to claim a measure means
architectural quality — and it is also the honest answer to "which criteria require expert
judgement": the expert's role is to *validate the measures*, not to rate every plan forever.

**What this replaces.** Not the validators. It replaces the implicit claim that `|area − target|`
plus 27 PASSes is a quality judgement.

---

## 9. Investigation 7 — three concepts per brief

Three frozen briefs with genuinely different requirements. For each, three partis a residential
architect might actually consider. **These are concept proposals. None has been realized, sized or
validated. Realizability is an open question, stated per concept.** Diagrams:
`figures/B06-partis.svg`, `figures/B16-partis.svg`, `figures/B09-partis.svg` — each carries the same
warning in its own title.

### B06 — 3 bedrooms, 2 wet rooms, no safe room, not open-plan, 312 m² requested, 13 × 24 m envelope
*Production delivers 177.4 m²: master at the garden, living+kitchen at the street, 27.6 m²
unassigned, one 10.35 : 1 corridor.*

| | **A — rear public band** | **B — courtyard (C-plan)** | **C — two volumes on a link** |
|---|---|---|---|
| parti | invert the existing front-band parti: arrival hall on the street, public band across the garden | a C wrapped round an outdoor room that organises the plan | public and private as two masses joined by a glazed link |
| massing | single rectangle (unchanged) | single rectangle with a void bitten out of the long side | two rectangles + a narrow connector |
| circulation | a shallow **cross corridor** between the entry band and the public band — short, not full-depth | a gallery along the courtyard: circulation that is also a view | the link itself is the circulation |
| entrance | hall on the street wall, which `ENTRANCE_ZONE_PRIORITY` already ranks first | through an entry court into the gallery | at the joint, between the two volumes |
| zoning | front→rear: service/arrival, bedrooms, public | wrapped — bedrooms one arm, public the other | by volume, the cleanest possible separation |
| outdoor | the whole public band opens to the rear garden | the court is a second, private outdoor room on a 13 m wide plot | the gap between volumes becomes a sheltered court |
| advantages | the living room gets the garden; the corridor stops being a 13.75 m slot | every room gets two orientations; depth-of-plan solved on a deep narrow lot | total acoustic separation; strong street presence |
| trade-offs | bedrooms land between the street and the public band — needs acoustic care | a court costs area the brief has not got spare, and the engine cannot represent one | a link is circulation that is nearly all envelope — expensive |
| realizable today? | **plausibly yes** — the existing front-band tree with its top split reversed and three orientation assumptions flipped (§10). Untested; this is exactly what §10 tests | **no** — requires a non-rectangular envelope and an outdoor-room type | **no** — requires two wings from one outline; `l_massings` exists but is never reached |

### B16 — 5 bedrooms + MAMAD, 3 wet rooms, open-plan, 216 m², wide 18 × 12 m envelope
*Production delivers 188.3 m²: LIVING, DINING and KITCHEN all on the west side, an 11.92 : 1
corridor, 0 alternatives.*

| | **A — street gallery, garden bedrooms** | **B — service corner + cross spine** | **C — L around a patio** |
|---|---|---|---|
| parti | a full-width gallery along the street wall; public band behind it; bedrooms at the garden | the MAMAD and a bathroom take the street corner nobody wants; a short spine crosses the plan | the wide envelope's natural parti: two arms around an outdoor room |
| massing | single rectangle | single rectangle | L, both arms on the plot's good sides |
| circulation | the gallery *is* the buffer — one move that gives circulation a reason to exist | a cross spine, roughly square in proportion, not a slot | an L gallery along the patio |
| entrance | mid-gallery; arrival is along the house, not into it | foyer beside the MAMAD | through the crook, between the arms |
| zoning | street→garden: circulation, public, private | service corner / quiet wing / public wing | public arm and children's arm |
| outdoor | every bedroom opens to the garden | public wing opens to the garden | a patio with two enclosing faces |
| advantages | turns the one architectural liability (a long corridor) into the acoustic buffer a street-facing house needs | puts the windowless-by-nature MAMAD where no habitable room wants to be | best daylight; a real outdoor room on a short, wide lot |
| trade-offs | 5 bedrooms + MAMAD across 18 m is tight; each gets ~3 m of frontage | the spine must still reach five bedrooms | an L costs envelope and the engine never reaches its L outlines |
| realizable today? | **partly** — an inverted front band plus a gallery-proportioned hall; untested | **unknown** — MAMAD placement is constrained by C4 (RC envelope) | **no in practice** — the L outlines are offered and never planned (#182) |

### B09 — 3 bedrooms, 3 wet rooms, 440 m², 20 × 22 m envelope
*Production delivers 227.2 m² — 114 % of the programme's own capacity — in which the single largest
garden-facing element is a 54.3 m² unassigned block, and TOILET_1 has no exterior face at all.*

| | **A — courtyard house** | **B — circulation as a room** | **C — great room to the garden** |
|---|---|---|---|
| parti | at 440 m² on a near-square plot, the void is affordable and solves what depth-of-plan always breaks | the surplus becomes a generous hall that is a *place* — the one room a 440 m² house can justify | the surplus becomes ONE great public room, not FLEX |
| massing | square donut / C | single rectangle | single rectangle, public mass to the garden |
| circulation | a gallery on two sides of the court | a double-height hall: the organising space | a cross corridor behind a street-side master wing |
| entrance | into an entry court, then the gallery | on axis, into the hall | foyer, then the great room |
| zoning | guest suite / master suite on opposite arms | quiet wing west, public wing east | master screened at the street; children at the garden |
| outdoor | a private court plus the rear garden | the garden, from the public wing | garden plus a terrace carved from the surplus |
| advantages | solves the deep-plan problem this exact brief has (TOILET_1 is landlocked today) | gives the 54 m² a name and a purpose | the simplest honest answer to "what is the extra area for" |
| trade-offs | the most envelope per m²; the most expensive | a large hall is still circulation; it must earn its area | a very large single room needs structural spans the engine does not model |
| realizable today? | **no** — needs a hole in the envelope | **partly** — nothing stops a large HALL except `HUB_TEMPLATE`'s 16 m² cap and C26 | **plausibly yes** — this is the closest to A/B06, plus raising the public elasticity ceiling |

**The pattern across all three briefs**: every concept a professional would reach for needs at least
one of (i) public zone oriented to the garden, (ii) an outdoor room in the programme, (iii) a
non-rectangular envelope, (iv) circulation treated as space. BuildSmart can express **none** of them
today, and (i) is a one-line change away.

---

## 10. The one recommended first experiment

> ### E1 — Orientation as an explicit concept dimension
>
> **Hypothesis (exactly one).** The public zone's orientation is an architectural decision the
> system cannot currently express; making it explicit — and choosing it by a measured criterion —
> changes the delivered plan on a majority of briefs and raises public-room garden frontage without
> weakening any validator.

**Why this one.** It isolates the single measured deficiency with the largest gap between
"architecturally obvious" and "currently impossible" (P4: 7/8 and 8/8). It is the only §9 concept
that today's geometry can host. It does **not** add a compiler, does not touch Geometry Core, does
not change a validator, and does not change an access graph — so it cannot be confused with "a
different access graph is a different concept". And it tests the load-bearing claim of the whole
target architecture: *that a concept dimension, once explicit and selected on, changes the building.*

**What is built** (behind a flag, default off):

1. A `public_orientation` field on `ConceptSpec` with values `STREET` / `GARDEN`. (`EntranceSide`
   and `MasterPlacement` can be given their missing fields in the same change — they are the same
   one-line omission.)
2. A `REAR_PUBLIC_BAND` variant of the existing front-band builder: the same sizing, the same
   access graph, the same rooms, with the band as the *second* child of the top split instead of
   the first, and the hall taking the street frontage so `resolve_entrance` finds `HALL` — which
   `ENTRANCE_ZONE_PRIORITY` already ranks first. Three places in `concept_generator.py` carry the
   orientation and must flip together — this is small, not trivial:

   | place | today | rear band |
   |---|---|---|
   | `:3250` `tree = Split(Cut.H, band_tree, rear, band_depth)` | band first (street) | band second (garden) |
   | `:3087/:3097/:3099` `north_is_envelope=False` | the band covers the columns' north ends | the band covers their **south** ends |
   | `_daylight_order` (`:931`) | assumes the LAST row is always at an exterior end | needs the symmetric `south_is_envelope` it does not have |

   The third is the only real work: `_daylight_order` currently hard-codes that a column's south end
   is envelope (`i == last`). That assumption is true for every parti that exists today and false
   for a rear band. It is a parameter, not a redesign — and the fact that an orientation assumption
   is baked into a C8 rescue heuristic is itself evidence for §2's diagnosis.
3. A deterministic measure, `public_garden_frontage_m`, added to the profile as **explanatory data
   only** in this experiment — not as a ranking key. The experiment measures; it does not yet decide.

**What is measured**, on all 8 frozen audit briefs, before and after:

| measure | today |
|---|---|
| briefs where the rear-band candidate **compiles** | 0 (does not exist) |
| briefs where it **realizes and passes all validators** | — |
| public-room garden frontage, metres | **0 m on 7 of 8** |
| wet-room garden frontage | 8/8 non-zero |
| plans where the winner changes (if the term were promoted) | — |
| validator failures introduced | must be **0** |
| geometry of the existing winner | must be **byte-identical with the flag off** |

**Success**: the rear-band candidate realizes and passes all validators on ≥ 3 of 8 briefs, with
public-room garden frontage > 0 on those briefs and no validator regression anywhere.
**Failure is also a result**: if it compiles but fails validation, the failing check names the next
real obstacle (my expectation is C8/C19 on the bedrooms now sandwiched between street and band), and
that is precisely the evidence needed to decide between widening the band family and wiring the
non-guillotine realizer.

**Owner-visible evidence**: the existing `?engine=` preview seam from #181 already renders two plans
side by side through the real `DemoPlan`. A third value shows the rear-band plan beside the
production plan. No new UI.

**Reversible**: one flag, default off; byte-identical output when off; the variant is additive to a
builder that already exists.

**Explicitly out of scope for E1**: promoting orientation into the ranking, outdoor rooms, courtyard
partis, wiring `rectilinear_realizer`, re-prompting the LLM, and the Pareto profile. Each is a later
phase that E1's result should inform.

---

## 11. Main technical risks

| risk | severity | mitigation |
|---|---|---|
| **The guillotine constraint is not removable incrementally.** Courtyard and C-plan partis need a hole in the envelope; pinwheel/notch help, a true court does not follow from them. | **high** | treat courtyards as a *later, separate* decision with its own evidence; do not let E1 or Phase 1 depend on it |
| **Wiring `rectilinear_realizer` is a bigger integration than it looks.** It is gate-passed on its own constructions; no brief has ever gone through it (H2), and notch-carve produces L-shaped rooms the owner has excluded. | **high** | wire **pinwheel and GridWing only**, on one brief, behind the existing flag, measured — never as a default |
| **A profile without calibration is just more numbers.** §8's measures could all be plausible and none predictive. | medium | build the calibration set *before* any measure is promoted to a ranking key; delete measures that predict nothing |
| **Explicit concepts increase refusals.** A concept the engine cannot host becomes a typed refusal where today something always comes out. | medium | concepts are *additive candidates*; the existing pool stays. Never refuse because a preferred concept failed |
| **The person's outline short-circuit (P6) defeats massing work.** Any massing-level concept is unreachable while one outline is planned on 6/8 briefs. | medium | this is a product decision, not a bug — but it must be made consciously before Phase 2 |
| **Area fidelity regresses.** The current objective is relentlessly good at hitting the requested area; anything added competes with it. | medium | keep area as a gate with a tolerance band, not as the ranking key — and measure the regression explicitly |
| **Scope creep into a rewrite.** Everything here is additive; the temptation to "do the concept layer properly" is a multi-month project. | **high** | every phase below ships behind a flag with byte-identical output when off, and is justified by the previous phase's measurement |

---

## 12. Phased migration

Each phase is gated on the previous phase's measured result and is independently reversible.

| phase | what | gate to start | reversible by |
|---|---|---|---|
| **0 — E1** | orientation as an explicit dimension; rear public band; frontage measured | — (this is the proposal) | one flag |
| **1 — concept as input** | `ConceptSpec` gains its missing fields; a small concept *generator* produces 3–6 typed concepts per brief; existing builders become *realizers of a concept*; `proposal_critic` gates them pre-geometry | E1 shows an explicit dimension changes the plan | flag; the existing pool is untouched |
| **2 — profile and portfolio** | §8's measures computed on every realized plan; selection becomes Pareto + declared priorities; the shown set is 3 genuinely distinct concepts or fewer, never padded | the calibration set exists and ≥ 3 measures predict expert preference | selection flag; `_select_plans` unchanged when off |
| **3 — widen the geometry family** | wire `GridWing`/`band_pipeline` as a second realizer for concepts the slicing tree cannot host; then pinwheel. Not notch-carve (L-shaped rooms). | Phase 1 produces concepts the slicing tree refuses, with typed reasons | realizer flag per family |
| **4 — outdoor as programme** | courtyard/terrace/entry-court as room types with area, adjacency and exposure semantics; unlocks RING and the C-plans in §9 | Phase 3 can host a non-convex envelope | programme flag |
| **5 — LLM as concept proposer** | re-prompt the proposer over Phase 1's vocabulary (parti, orientation, entrance, outdoor); critic-gated; never geometry | Phase 1's vocabulary is stable and Phase 2 can judge the result | the deterministic concept generator remains the default |
| **(parallel) R — case-based** | revisit the #109 retrieval/donor-adaptation track against a real-plan corpus | independent; research budget only | nothing ships |

Phases 0–2 are the ones that change what the owner sees. Phases 3–5 are what make the §9 concepts
possible at all.

---

## 13. Method, and what would falsify this

**Measured here** (`backend/app/ai_harness/arch_direction/`, imported by nothing):

- `decisions.py` — exposure, indoor/outdoor and objective-composition facts for all 8 briefs,
  through `app.demo.service.generate_demo_design`. Output: `data/arch_decisions.json`.
- `separability.py` — the guillotine test on the delivered plans.
- `parti_diagrams.py` — the §9 conceptual figures (schematics, not plans).

**Cited, not re-derived**: #182 (82 candidates → 1 topology; `compile_hub_lobby` 0/8), #183 (the
hub's 2-bedroom ceiling), #142M/#142N (selection term statistics; `circulation_prefers`
intransitivity), #179 (the area table and the reference set),
`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §3.2 (0/19 real plans guillotine-separable).

**What would falsify the central claim.** The claim is that the output is weak because the system
has no architectural concept, not because it searches or ranks badly. It would be falsified if:

- a richer search over today's candidate pool produced materially different buildings — **contradicted**
  by #182's 82 → 1;
- the delivered plans turned out not to be guillotine-separable — **contradicted** above, 8/8;
- some stage were found that does consider the garden or orientation — **searched for and not found**
  (P4); or
- E1's rear-band variant realized and *nothing about the plans changed* — **not yet tested**, and the
  reason E1 is the recommended first experiment rather than a conclusion.

---

**Recommendation in one sentence.** Approve E1; treat its result — success or failure — as the gate
for Phase 1, and do not fund any further compiler, access-graph or selection work until an explicit
concept dimension has been shown, on real briefs through the real renderer, to change the building.
