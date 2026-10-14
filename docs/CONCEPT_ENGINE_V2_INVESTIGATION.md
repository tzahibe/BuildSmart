# Concept Engine v2 — investigation: generative vs retrieval vs hybrid

Status: **INVESTIGATION / PROPOSAL — nothing implemented.** Written by the Team Lead on 2026-09-20 at the
owner's request ("approve the investigation stage… compare three directions explicitly… come back with a
ROOT + 2–5 children, a proposed architecture and the comparison; no implementation before the proposal").
Every number below was measured on `main` at `648292f2` (the Yom Kippur rollup) with read-only scripts;
three read-only Sonnet domain-lead briefs (geometry / knowledge / backend) fed the facts and are cited
where used. Proposed contracts: `.agent/proposals/roadmap/cev2-*.md`.

## 0. תקציר למנהל

- **למה הקונספטים מתכנסים:** לא בגלל הדירוג — בגלל אוצר המילים של המחולל. 5 מתוך 6 אסטרטגיות ה-spine
  בונות את *אותו* עץ (`V[עמודה, מסדרון, עמודה]`) ורק משנות אילו חדרים בכל צד; hub נוצר רק כשחסם
  חישובי מאשר אותו (0 מתוך 60 briefs במדידה), L רק כשיש שני אגפים (7/60). הדירוג (קרבה לשטח המבוקש
  בלבד) והבחירה (הראשון שמתממש) רק מקבעים את זה. **תוצאה נמדדת: ב-60 briefs — 0 תוכניות עם מבואת
  חדרים, 0 עם מסדרון קומפקטי (M4 ≤ 1.5), חציון יחס המסדרון 9.07 — בעוד שבסקר 21 התוכניות המקצועיות
  18/21 בנויות סביב מבואה ו-0 עם מסדרון ישר.**
- **מה הרפרנסים יכולים לתת כ-prior:** 36 הרשומות ב-`references/index.json` הן ארכיטיפים סינתטיים
  שנגזרו מהסקר שלנו עצמו (metadata-only, בלי תוכניות אמיתיות) — טובות כ*אוצר דפוסים* (spine / hub-lobby /
  front-band / two-wing / courtyard) אבל לא כ-prior סטטיסטי. ה-prior האמיתי הוא סקר 21 התוכניות
  (hub 18/21, חדרים רטובים גב-אל-גב 20/21, 13/21 מעטפת לא-מלבנית). מדיניות הזכויות מתירה רשומות
  תיאוריות (מבנה, לא גיאומטריה).
- **איך האיכות מזינה חזרה:** אף מדד לא רץ לפני גיאומטריה, אבל מימוש עולה ~165ms למועמד — לכן הלולאה
  היא "ממש → מדוד → התאם" ברמת דפוס, בדיוק כמו שה-hub witness (008) כבר עושה בקטן.
- **המלצה: היברידי (כיוון 3)**, בנוי על תפר ה-`ConceptCandidate/Fixture` הקיים, מאחורי דגל; התוכנית
  הראשית נשארת זהה בייט-לבייט (LOST 0, primary 0) עד להחלטת בעלים; החלופות הופכות ל"אחת לכל
  מבנה תנועה". ROOT + 5 ילדים מוצעים (§10); 4 החלטות מוצר לבעלים (§11).

## 1. Scope and method

Questions asked by the owner: (1) why today's concepts converge to the same partis; (2) what in the
references can serve as a real prior; (3) how M1–M6 / circulation / privacy / dead-space can feed back into
the concept stage; (4) how to produce 2–3 topologically different concepts; (5) what to reuse. Directions
compared: **D1 generative** concept/decomposition from the brief, **D2 retrieval** of concepts/patterns from
real plans, **D3 hybrid** retrieval → adaptation → quality feedback → realization.

Method: code reading (`concept_generator.py`, `general_pipeline.py`, `demo/service.py`, `geometry_core`,
`quality_metrics.py`, `hub_guard.py`, `l_massing_guard.py`, `wet_core.py`, `reference_benchmark.py`,
`spec.py::HouseConcept`), the evidence history (`specs/005-hub-private-wing/{spec,RESULTS}.md`, `specs/008`,
`docs/MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md`, `docs/CONCEPT_GENERATOR_REFINE_V1_REPORT.md`,
memories `repetition-root-and-outline-sweep`, `architectural-quality-gaps-measured`), two corpus
measurements (80 and 60 PLANNED contexts of the frozen 432-context corpus, through the real service), a
profile of the reference set, and three read-only domain-lead investigations (`agentctl investigate`,
Sonnet, tools Read/Grep/Glob; briefs kept in the session scratchpad and summarised here).

Knowledge preflight: index unchanged (no re-index needed for a read-only investigation); canonical pages
used: `docs/wiki/architecture/geometry-validation.md`, `docs/wiki/features/{l-massing,wet-rooms,
room-proportion-quality-tier,review-page}.md`; RAG not needed (the raw reports were opened directly);
verified against code at `648292f2` (line numbers below refer to that commit).

## 2. How a concept is produced today (facts)

**The data model.** A concept is a Geometry Core `Fixture`: `wings` (one rectangle per wing, positioned on
the plot), each with a slicing `tree` (`Split(Cut.V|H, first, second, fixed?)` / `Leaf(zone_id)`), `zones`
(`ZoneSpec(id, roles, lo/target/hi area, min short side, max aspect)`), `access` (`DesiredAccessTopology`
of `DOOR` / `OPEN_CONNECTION` / `CASED_OPENING` edges) and `open_groups`. The generator wraps it as
`ConceptCandidate(concept, strategy, wing_orders, rationale, used_area_m2, wet_rooms, repartitioned,
quality_repartitioned, shrunk, over_preferred, hub_last_resort)` (`concept_generator.py:451`). **This is
already a concept contract**: `_realize` (`general_pipeline.py:742`) and `_alternative_plans` (`:805`)
read only `.concept.fixture` plus those scalar fields; doors, windows, furniture, validation, assembly
and Geometry Core never learn *how* the fixture was produced (geometry lead, finding c).

**The generator.** `generate_concepts` (`concept_generator.py:4423`) builds, per safe outline candidate:
- `_allocations` (`:2926–2969`): five `(strategy, west, east)` room splits — SPINE_PUBLIC_PRIVATE,
  SPINE_DOUBLE_LOADED ×2, SPINE_SERVICE_CLUSTER, BRANCHED_TWO_STACK — all realized by `_build` (`:2529`)
  as **one tree shape** `V[west column, HALL, east column]` (`:2899`); they differ only in which rooms sit
  in which column;
- `_front_band_concept` (`:2981`): the second tree shape (public band across the front, hall + bedrooms
  behind);
- `_hub_concept` / `_plan_hub_wing` (`:3699`, `:3938`): the room-lobby parti, offered as a peer only where
  `hub_bound()` finds a sizing that passes the 8 gates on *this* outline (feature 008), otherwise
  appended as a last resort after every other candidate and its twin (`:4500–4508`);
- `l_parti.l_concepts`: the two-wing L, only when two adjacent safe wings exist; appended last without an
  area target (`:4529–4533`);
- unforced twins, tier-2 repartitions, quality-tier re-partitions of the same trees.

**The ranking** (`:4560–4567`): `(|used_area − target|, over_preferred/shrunk, used_area, strategy name)`
— area proximity only; no topology, quality or diversity term. **The selection** (`run_general`,
`general_pipeline.py:479–528`): first candidate that solves and validates, with the entrance-rank tie
rule of #20; then `_guard_demoted_hub` (`:680`) and `_prefer_quality_twin` (`:626`) compare the winner with
one specific peer each. **Alternatives** (`:805`): up to 3 more realized plans of not-yet-seen
`family_signature` within 8 solver attempts, plus one guaranteed slot per massing family gated by
`l_massing_guard`. **Display** (`service._select_plans`, `:689`): primary = nearest requested area across
outlines; alternatives de-duplicated by massing, then family, then outline.

**Cost.** Solver ≈ 165 ms per candidate, everything else ≈ 17 ms per candidate (`general_pipeline.py:114–121`);
the corpus sweep runs 431 briefs in 540 s (≈ 1.25 s per brief including alternatives). No latency SLA
test exists for the demo endpoint (backend lead, finding b).

## 3. Why the concepts converge (question 1)

Measured through the real service (`generate_demo_design`) on PLANNED corpus contexts:

| Measurement | 80 contexts (2026-09-19) | 60 contexts, seed 7 (2026-09-20) |
|---|---|---|
| chosen parti | SPINE_PUBLIC_PRIVATE 39 · SPINE_DOUBLE_LOADED 25 · FRONT_PUBLIC_BAND 9 · SPINE_SERVICE_CLUSTER 4 · BRANCHED_TWO_STACK 3 · HUB 0 · L 0 | 29 · 21 · 8 · 2 · 0 · 0 · 0 |
| candidates per brief | median 28 (0–114) | strategy totals: DOUBLE_LOADED 620, PUBLIC_PRIVATE 506, BRANCHED 414, SERVICE_CLUSTER 340, MULTI_WING 274, FRONT_BAND 60, **HUB 0** |
| briefs offered a hub candidate at all | — | **0 / 60** |
| briefs offered an L candidate | — | 7 / 60 |
| plans shown (primary + alternatives) | one massing family in 80/80 | 1 plan: 16 · 2 plans: 22 · 3 plans: 22 |
| distinct `family_signature` among shown | — | 1: 22 briefs · 2: 21 · 3: 17 — **but all 41 distinct structures share the root `V[column, HALL, column]`** |
| plans with a compact hall (M4 ≤ 1.5) or a HUB: prefix | — | **0 / 60 briefs**; hall long/short median **9.07**, min 3.39 |
| M3 circulation share / M5 wet adjacency (shown plans) | — | median 10.4 % (reference 8–14 %) / **median 0.0** (reference 85–90 %) |

The professional census the product measures itself against (`specs/005-hub-private-wing/spec.md` §1, 21
Israeli house plans supplied by the owner): compact room lobby in ~18/21, straight double-loaded corridor
in **0/21**, 4–7 doors on the lobby, wet rooms back-to-back in ~20/21, 13/21 non-rectangular envelopes.

**The cause, in order of weight (geometry lead + measurements):**
1. **The candidate SET.** Routinely only two tree shapes exist (spine and front band). Five strategy
   names re-label one tree. The hub exists as a *separately hand-built planner* and is offered as a peer
   on 4 of 432 corpus contexts (008 measurement; 0 of the 60 sampled here); the L needs two safe wings.
   With ≤ 2 topologies in the list, no ranking can produce topological diversity.
2. **The RANKING** has no topology term, so among the spine relabelings the one nearest the requested
   area wins — this is why SPINE_PUBLIC_PRIVATE and SPINE_DOUBLE_LOADED (present for every brief, listed
   first) take 78 % of the primaries. Memory `repetition-root-and-outline-sweep` measured the same on
   2026-09-13: the area sort changes the parti in < 10 % of briefs; the generator decides.
3. **The SELECTION** takes the first realizable candidate, and the two post-selection guards compare the
   winner only with its own hub twin / quality twin — never with a plan of another organisation.
4. **A real engine limit** (verified in `geometry_core/engine.py:97–116 _mark_open_interfaces`): an open
   group must be one subtree, i.e. its leaves are aligned rectangles — a bent (L/T) corridor cannot be one
   open circulation space (`docs/CONCEPT_GENERATOR_REFINE_V1_REPORT.md` §"bent corridor"). Branched and
   ring circulation therefore cannot be expressed as "one more strategy"; they need a seam-level
   opening between hall leaves (precedent: the hall↔LDK wall opened at segment level in `contract.py`,
   memory `corridor-opening-is-a-contract-post-process`) or a Geometry Core extension.
5. **Why "more heuristics" did not work:** the hub parti went through v1 → v2 → v2.1 → v3 Phase 0 → 008
   → 008 follow-up (`specs/005/RESULTS.md` §3–§9): each iteration hand-authored a template tree and a
   sizing rule; v3's exhaustive bound proved "no topology passes geometry + access + wet adjacency" on
   outlines ≥ 14 m wide, and 008 rescued 4 eligible hubs by computing the sizing from the bound's witness
   — the only step that worked was the one that *measured and adapted* instead of adding a rule.

## 4. What the references can be as a prior (question 2)

**Facts.**
- `docs/architecture_reference/references/index.json`: 36 entries, all `rights: metadata-only`, no files.
  Populated fields: `footprint_family` (rectangle 10, wide-rectangle 8, narrow-deep 8, L 6, irregular 4),
  `bedrooms` 2–6, `bathrooms`, `levels` (single 28 / multi 8), `total_area_sqm`, `tags`, `notes`, prose
  `annotation.md`. **No structured concept fields** (circulation structure, zoning, entrance, wet-core
  grouping, master placement) in `schema.json`; the concepts live in prose only — annotations mention
  lobby/hub in 19, spine/corridor in 25, entrance in 21, front band in 3, courtyard in 2, double-loaded
  in 1; tags: two-storey 8, narrow-plot 8, two-wing 6, spine 5, hub-lobby 4, front-band 3, courtyard 2.
- **The V1 set is not real plans.** `references/README.md` §"V1 provenance": "architecturally-grounded
  archetypes … derived from this repository's own internal reference-plan census", built with no network
  access. Using them as a statistical prior would be circular (they encode what we already believe).
- The real prior is the **21-plan census** (owner-supplied images, visually counted; aggregates in spec
  005 §1 and memory `architectural-quality-gaps-measured`). The plans themselves are not in the repo.
- **Rights policy** (`references/README.md`): metadata-only entries' *descriptive fields* are
  "analysis-safe to reference in documentation and benchmarks"; the drawing itself is never copied or
  trained on. A structured concept record (adjacency graph, circulation class, zoning, wet-core pattern —
  no coordinates, no images) is descriptive metadata of the same kind as the existing `notes`/`tags`.
  Extending the schema with such fields is inside the policy; **curating them for the 21 census plans is a
  product decision** (owner-supplied material; hours of architect-level annotation per set).
- The benchmark (`reference_benchmark.py`, #32) uses references only through `footprint_family` matching
  and the family's `total_area_sqm` range; `classify_footprint_family(design)` (`:118`) is the reusable
  key function. `backend/app/knowledge` (KnowledgeStore, FTS5/hash) is a document search layer — the
  wrong tool for a 30–60-row structured table; a plain in-memory table keyed by (family, width band,
  bedrooms, wet rooms) is deterministic and testable.

**What a prior can honestly be today:** a *pattern language* with frequencies — "for this footprint
family × programme size, architects use these circulation structures / zoning splits / wet-core
groupings, with these frequencies" — seeded from the census aggregates (hub 18/21, wet back-to-back
20/21, non-rect 13/21) and the archetypes' tags, refined later by per-plan records. It answers *which
topologies to try first* for a brief. It cannot supply geometry, and it must not be the only source of
concepts (36 + 21 items overfit trivially).

## 5. How quality can feed back into the concept stage (question 3)

**Facts (backend lead, verified):** every deterministic signal reads realized geometry — M1–M6
(`quality_metrics.measure_design` on the `DemoDesign` shape), `hub_guard.proportions_of`,
`l_massing_guard.exposure_of`, `wet_privacy.compute_wet_privacy` (C29), C24 (`access_rules`), C19
(`exposure_policy`), `wet_core.compute_wet_core`; none runs on a bare tree. Two things *can* be checked
symbolically before geometry: the C24 `ALLOWED_ENTERED_FROM` table against the access edges, and the C19
role table against the tree's envelope-touching leaves — cheap, new code. `dead_space_m2` is 0 by
construction (C2 forces zero residual); #43 will define residual *pockets*; #36 (circulation metrics) is
in repair after the rollup and not on main yet.

**The loop that already exists, in miniature:** `hub_bound()` → witness → `_plan_hub_wing(witness=…)`
(008 follow-up: 4/4 eligible hubs pass all 8 gates after re-sizing from the bound), `hub_guard`
(winner vs displaced hub, both realized), `_prefer_quality_twin` (winner vs its own re-proportioned
peer), `l_massing_guard` (L vs best rectangle). Each is "realize → measure → keep the better one", each
compares exactly one pair.

**Because realization costs ≈ 165 ms, the feedback loop is realize-then-measure at pattern level**, not
pre-geometry prediction: for each circulation class the stage realizes its best candidate, measures, and
either accepts, adapts the concept (bounded), or drops the class. Metric → adaptation mapping:

| Signal (exists) | What it tells the concept stage | Adaptation of the concept (not the geometry) |
|---|---|---|
| M4 hall aspect / door count | whether the declared circulation class was realized (lobby ≤ 1.5 with ≥ 4 doors vs spine) | verify the class tag; drop a candidate whose realized class differs from its declaration |
| M5 wet adjacency, `wet_core` groups | wet rooms scattered | re-allocate: cluster the shared wet rooms at the hub head / back-to-back with the ensuite (the `SPINE_SERVICE_CLUSTER` allocation already encodes this move) |
| M1 bedroom/master aspect, `hub_guard` proportions | sizing wrong for this outline | witness-based re-sizing (008 pattern); swap flank/foot placement |
| entrance rank (#20), C23 | arrival room quality | move the public zone to the street side / choose the front-band variant |
| M3 / #36 circulation metrics (when merged) | corridor too long / dead-end | prefer the hub or double-loaded variant; shorten by moving the wet core |
| #43 residual pockets (when merged) | wasted space | drop or re-allocate |
| C24 / C19 tables (symbolic, pre-geometry) | illegal access pair / role on an interior leaf | reject before solving (saves the 165 ms) |

## 6. Producing 2–3 topologically different concepts (question 4)

**Definition to adopt (deterministic):** two concepts are topologically distinct when they differ in at
least one of: (a) **circulation class** — SPINE (one hall, long/short > 3), FRONT_BAND (public band spans
the width, hall behind), HUB_LOBBY (compact lobby, aspect ≤ 1.5, ≥ 4 doors, rooms on ≥ 3 sides), BRANCHED
(two hall segments meeting at an angle), RING (around a patio — out of reach today), TWO_WING (L massing);
(b) **zoning split** — public front / private back vs public side / private side vs split wings;
(c) **wet-core grouping** — `wet_core.WetCoreAlignment.groups()` partition (clustered vs distributed).
`family_signature` (letters over the slicing tree) already separates arrangements within a class and
carries a `HUB:` prefix; the class must become an explicit tag that is **verified on the realized plan**
(M4 + adjacency), never inferred from the tree alone (geometry lead, AC 2).

**What is reachable without touching Geometry Core:** SPINE, FRONT_BAND, HUB_LOBBY (existing builders),
TWO_WING (existing `l_parti`). BRANCHED needs an opening between two hall leaves at the seam level (the
`contract.py` corridor-opening precedent, plus C5/C24 acceptance) — a decision-gated child. RING is out of
scope (engine limit).

**The shown set** becomes "one plan per circulation class, best within its class", extending the massing
→ family → outline de-duplication `_select_plans` already does; the primary stays the requested-area rule
until the owner decides otherwise (§11).

## 7. What to reuse, what not (question 5)

Reuse unchanged: Geometry Core types (`Fixture/Wing/Node/ZoneSpec/DesiredAccessTopology`), `ProgramRoom`
/ `ZoneGroup` vocabulary, the pattern builders (`_build`, `_front_band_concept`, `_hub_concept` +
`hub_bound` witness, `l_parti.l_concepts`, `_free_twin`, quality/tier-2 re-partitions), the whole
realization chain (`solve_fixture`, `_realize`, doors/windows/furniture/validation/assemble), the
comparators (`hub_guard`, `l_massing_guard`, `wet_privacy`, `wet_core`), M1–M6 and the quality baseline,
`family_signature`/`massing_signature`/`layout_signature`, `_alternative_plans`/`_select_plans`,
`HouseConcept.circulation_style` (`spec.py:333`, today read by nothing — the natural home of the class
vocabulary), `reference_benchmark.classify_footprint_family`, the corpus snapshot/compare tooling and the
`LAUNDRY_ROOM_ENABLED` flag pattern, the QualityPanel data path (#63) for concept labels.
Not reused as-is: `concept.py` (the frozen hand-authored demo concept), `_allocations`' role as *the*
concept source (it becomes one pattern compiler among several), the `HouseConcept` idea of concept =
"ordering preference over ConceptStrategy" (`MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md` §2 —
a preference model cannot create topologies that are not generated).

## 8. The three directions compared

| Criterion | D1 generative from the brief | D2 retrieval from real plans | D3 hybrid |
|---|---|---|---|
| Can it produce 2–3 distinct classes per brief? | yes, if the vocabulary is extended (hub, branched) — but each new class is a hand-built compiler (the hub took six iterations) | no by itself: a retrieved concept is a *label*; someone must still compile and size it for the outline | yes: the prior says which classes to try, the compilers build them, the loop verifies and adapts |
| Architectural grounding | internal (our census-derived rules) | external, but thin today (36 synthetic archetypes; census aggregates; per-plan records need curation) | external prior + internal verification; degrades gracefully to D1 when the prior is silent |
| "More heuristics" risk | high — same bias as today; ranking terms tuned by hand | low at concept choice, high at sizing (retrieval says nothing about dimensions) | medium: the loop replaces hand thresholds with measured comparisons (008 witness precedent) |
| Determinism / corpus regression | fully deterministic; new candidates change primaries unless flagged | deterministic table lookup | deterministic; flag-off byte-identical; flag-on changes alternatives first |
| Cost per brief | ~0 extra generation; +165 ms per extra realized candidate | ~0 | bounded: ≤ N realizations per class (proposal: ≤ 6 extra ≈ 1 s worst case) |
| Data curation needed | none | yes (schema + 21 census plans; rights OK for metadata) | optional: starts from aggregates + tags, improves with records |
| Reuse of existing code | high | medium (benchmark keys, tags) | high (everything of D1 + D2) |
| Overfitting risk | to our own rules | to 36 + 21 items | mitigated: the prior orders, the loop decides on measured quality |

**Verdict: D3, staged.** D1 alone re-creates the hub saga; D2 alone cannot produce a `Fixture`. The hybrid
uses the references for the decision they can inform (which topologies, in what order, with what wet-core
and zoning pattern) and the engine's own metrics for the decision they cannot (does this concept actually
work on this outline).

## 9. Proposed architecture

```
brief (ProgramSpec / ProgramRooms / outline / HouseConcept)
   │
   ▼
[S1] concept prior  ──  concept_patterns.py: structured pattern records (class × zoning × wet-core ×
   │                    applicability), seeded from the census aggregates + archetype tags; deterministic
   │                    lookup by (footprint family, width/depth band, bedrooms, wet rooms) → ordered
   │                    list of 2–3 pattern classes to try
   ▼
[S2] concept synthesis  ──  ConceptSpec → ConceptCandidate compilers (existing builders, re-exposed as
   │                        pattern compilers: spine/_build, front band, hub + witness, l_parti; later
   │                        branched); every candidate carries circulation_class + zoning + wet_core tags
   ▼
[S3] realize–measure–adapt loop (per class, bounded)  ──  solve_fixture + _realize (unchanged) →
   │      measure (M1–M6, wet_core, entrance rank, hub_guard proportions; #36/#43 when merged) →
   │      verify the class tag → accept / adapt the ConceptSpec (wet-core cluster, witness sizing,
   │      zoning flip) / drop the class
   ▼
[S4] selection & display  ──  primary: unchanged rule (flag-off byte-identical); flag-on: alternatives =
                              one best plan per circulation class, labelled (concept name + why)
```

Contracts: `ConceptSpec` (pattern + programme + outline → what to build), `circulation_class` tag on
`ConceptCandidate`, `concept_score` (pure function of a `RealizedPlan`'s existing metrics with a documented
tie-break), `topologically_distinct(a, b)`. Insertion: S1–S3 run inside `run_general` after
`generate_concepts` returns and before `_alternative_plans`, behind `CONCEPT_ENGINE_V2_ENABLED = False`
(module boolean, the `LAUNDRY_ROOM_ENABLED` pattern); the existing main loop, guards and `_alternative_plans`
stay as they are. Regression posture for every child: flag-off ⇒ `LOST 0, primary_signature_changes 0`;
flag-on measured in the child's own report with the list of alternative-set changes; the quality baseline
(`test_quality_baseline.py`) must not regress. Latency: a wallclock budget test (`tests/wallclock.py`
pattern) bounding flag-on cost per brief.

## 10. Proposed ROOT + children

| # | Proposal file | What lands | Behavior change | Depends on |
|---|---|---|---|---|
| ROOT | `cev2-root-concept-engine-v2.md` | the hybrid concept stage as a whole, feature-flagged | none until the owner flips the flag | #28 ✓, #17 ✓ |
| CE2-1 | `cev2-1-conceptspec-and-distinctness.md` | `ConceptSpec` contract, `circulation_class` tag + realized-plan verifier, `topologically_distinct`, corpus **diversity report** (the number this ROOT must move: briefs with ≥ 2 classes shown — today 0/60) | none | — |
| CE2-2 | `cev2-2-concept-pattern-prior.md` | `concept_patterns.py` records + deterministic lookup; schema extension `concept` block for references (census aggregates + archetype tags; per-plan records optional) | none | CE2-1 |
| CE2-3 | `cev2-3-concept-score-and-adaptation.md` | `concept_score` + the bounded realize–measure–adapt loop as pure functions (wet-core cluster, witness sizing, zoning flip); measured offline on the corpus | none | CE2-1 |
| CE2-4 | `cev2-4-pipeline-insertion-per-class-alternatives.md` | S1–S4 wired behind `CONCEPT_ENGINE_V2_ENABLED`; alternatives = one plan per class; concept label in `DemoDesign`/QualityPanel; latency budget test; flag-on corpus report | flag-off none; flag-on alternatives only | CE2-2, CE2-3 |
| CE2-5 | `cev2-5-branched-corridor-pattern.md` (decision-gated) | BRANCHED class via a seam-level opening between two hall leaves + C5/C24 acceptance | none (flag) | CE2-4 + owner decision |

Execution: CE2-1 first (measurement + contracts, light); CE2-2 ∥ CE2-3 (knowledge ∥ backend, no shared
lock); CE2-4 (planner-core lock — serialize with #36/#22/#43 work in `general_pipeline.py`); CE2-5 only
after the decision in §11.3. Relation to the roadmap: replaces the "Concept Quality / Decomposition
Engine" and "Alternative Plans / Diversity" topics of the Later list; #36 and #43 become inputs of S3 when
they land; #39/#41 (interior layout, public-zone composition) consume the concept tags later.

## 11. Product decisions for the owner

1. **Primary plan.** This ROOT changes only the alternatives (one per circulation class). Whether a hub or
   front-band plan may become the *primary* when the score says it is better is a separate decision with
   measured evidence after CE2-4 (spec 005 §11 (c) reached the same conclusion). Recommendation: decide
   after CE2-4's report.
2. **Curation of the 21 census plans** into structured concept records (metadata only, rights-safe; ~2–4 h
   of architect time per set). Recommendation: not a prerequisite — CE2-2 starts from the aggregates and
   the archetype tags; per-plan records are an optional upgrade with its own knowledge Issue.
3. **BRANCHED corridor (CE2-5)** requires a seam-level opening between hall leaves — a validator/engine
   decision, not a heuristic. Recommendation: gate on CE2-4's diversity numbers; if SPINE/FRONT_BAND/HUB
   already give ≥ 2 classes on most briefs, defer.
4. **Latency budget** for the demo endpoint (no SLA test exists). Recommendation: flag-on cost ≤ +1.5 s
   worst case per brief on the developer machine, enforced by a wallclock test.

## 12. Risks

- Primary-signature churn once new classes are realizable and area-competitive: mitigated by the flag and
  the "alternatives first" scope; the regression budget of every child says `primary_signature_changes: 0`.
- Class tag drift ("three differently labelled spines"): mitigated by the realized-plan verifier (CE2-1)
  and by the diversity report being the ROOT's acceptance number.
- Overfitting to the small reference set: the prior only orders classes; acceptance is measured per plan.
- Interaction with `hub_guard` / `l_massing_guard` / quality twin: the loop composes *after* the existing
  selection (never replaces it) in CE2-4; a later child may subsume them only with measured evidence.
- Multi-level (backend-only, not wired to the product) stays out of scope; the concept tags must not break
  `building_validation` tests.

## Appendix — measurement scripts and lead briefs

`diversity.py` (session scratchpad; `PYTHONPATH=. OPENAI_API_KEY=x uv run python … 60`): samples PLANNED
corpus contexts with `random.seed(7)`, runs `generate_demo_design`, records `family`, M3/M4/M5 of every
shown plan and `StrategyRecorder` candidates. The 80-context run of 2026-09-19 used the same helpers. The
three domain-lead briefs (`out_generative.json`, `out_hybrid.json`, `out_retrieval2.json`) are kept in the
session scratchpad; their findings are folded into §2–§7 with the file:line citations verified by the
Team Lead.
