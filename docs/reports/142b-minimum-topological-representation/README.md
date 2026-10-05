# Minimum topological representation beyond GridWing (#142A follow-up, investigation only)

**Question.** #142A/#162 gave the realizer a real 2D carrier (`GridWing`) and 0/4 of the n>5 briefs
(B10, B13, B15, B16) embedded; B01 stayed refused as `SHORT_SIDE_INFEASIBLE`. What representation
capability is actually missing — and how much of the loss is the search rather than the representation?

**Answer in one paragraph.** The four failures have two different causes and neither is "GridWing is
too weak" in the way #142A's numbers suggest. (1) **B13 is a pure search failure**: a layout inside the
*existing* `GridWing` dataclass carries all 12/12 edges; the production search never tries it because
it fixes balanced row lengths and the `1,1,…,remainder` span pattern, which caps every slot at ≤4
neighbours while B13's HALL needs 6. (2) **B10, B15 and B16 are provably impossible for any dissection
into rectangles** — not GridWing, not the Geometry Core's slicing trees, not the non-guillotine
realizer, not any rectangular dual: each contains a *separating-triangle obstruction* (B10: a K4 on
HALL/LIVING/BEDROOM_1/BATHROOM_1; B15 and B16: an edge whose two rooms share three common
neighbours). For all three, exactly **one edge** is unrepresentable (13/14, 14/15, 18/19 are
achievable by a band layout), and **one L-shaped room** (any of 4–5 named candidates per brief,
HALL always among them) restores the full graph — even inside a band layout. (3) B01 is not blocked by
its brief: the same 6-edge graph realized **and passed the validator** as a GridWing band layout in
16 of its 68 distinct band layouts (6/6 spatial, 4/4 access); the pinwheel-first rule for n=5 chose a
carrier that cannot be sized. Across all 20 frozen briefs, 13 are carried by the existing GridWing
dataclass, 6 need one L-shaped room, and 1 (B19) is non-planar — impossible under *any* partition of
the plane. On the 17,107-plan ResPlan corpus, real touching graphs are sparse (median 6 rooms, 8
edges, hub degree 4), 98.0% have no rectangular obstruction, and in a random sample the band layout
carries ~99%; the remaining ~1–2% are fixed by one L-shaped room. **Minimum sufficient
representation: the GridWing band layout as already defined, driven by an exact embedder, plus a
single merged-cell (L-shaped) room as the next relaxation.** Nothing in this investigation changes
production code.

Everything below is measured with exact decision procedures (SAT over every dissection in a family,
on grids proven large enough), not heuristics; every "impossible" is either a SAT UNSAT over the
complete family or an instance of the separating-triangle theorem (§7). Scripts, witnesses and the
failure matrix are under `backend/spikes/topology_representation/` and `data/` here.

---

## 1. Knowledge preflight

- index refresh: `index --changed` — 72 indexed / 82 unchanged (hash embedder fallback; no Ollama
  embedding model installed).
- canonical pages used: `docs/PROJECT_STATE.md`, `docs/wiki/INDEX.md`, Geometry/Validation page;
  raw evidence: `docs/reports/142a-realizability-gap-closure/results.md` (origin/main a7f1ad2),
  #160's `docs/reports/topology-placement-bridge/results.md` (branch agent/160), #149's
  `docs/reports/real-plan-priors/adjacency-fullcorpus.md`, #106's full-corpus shape re-measurement.
- verified against code at origin/main `a7f1ad2`: `app/vertical_slice/graph_embedding.py`
  (search: `_row_lengths_for`, `_slot_positions`, `_assign_rooms_to_slots`, `_MAX_GRID_ROWS = 6`),
  `rectilinear_realizer.py` (`GridWing`, `_solve_grid` rank-1 fit, `_build_grid_wing`),
  `gap_closure_142a.py` (selection = best policy-valid proposal in each brief's top-8; edges =
  `proposal.spatial_adjacency`), `topology_preservation.measure_spatial_adjacency` (preserved iff
  `shared_edge_len_u > 0`), `geometry_core/model.py` (`Node = Leaf | Split`: an arbitrary binary
  slicing tree, no depth/shape restriction; `engine.solve_fixture` sizes any such tree).
- Local `main` checkout is at `4484886`; the #142A code lives on `origin/main` (`a7f1ad2`). All code
  was read from `origin/main` via `git show`/`git archive` into a scratch directory; nothing was
  checked out, stashed or reset in the working tree.

## 2. Method

### 2.1 The graphs
The exact graphs #142A embedded: for each brief, `best_policy_valid_proposal` over the frozen
dataset (`generation-dataset.json`, sha `03c52be5…`), required edges = `spatial_adjacency`
(undirected). Reproduced for all 20 briefs in `data/selected_graphs.json`.

### 2.2 Nested representation families, each decided exactly

| level | family | what it is | decided by |
|---|---|---|---|
| L0 | GridWing **as searched** | the slot structures `graph_embedding` enumerates: `n_rows` 1…6, balanced row lengths, every cell span 1 except the last cell of a row | exact SAT room→slot assignment per structure (`l0_exact`), plus exact max-edges per structure (`run_extra2.py`) |
| L1 | GridWing **as defined** (band layout) | any partition into horizontal bands, every room spans its band's full height, arbitrary row lengths and spans (= any `GridWing(rows, n_cols)`) | SAT tiling with band constraint (`solve_family(..., "band_y")`) |
| L2 | slicing / guillotine | any recursive guillotine dissection — exactly the Geometry Core's `Split/Leaf` trees | SAT tiling + recursive-cut constraint; witness re-checked by `is_guillotine` |
| L3 | rectangular (non-guillotine allowed) | any dissection into rectangles = any subgraph of a rectangular dual | SAT tiling |
| L4 | rectangles + k L-shaped rooms | k named rooms may be the union of two rectangles sharing an aligned edge | SAT tiling with piece pairs |

Extra contacts are **allowed** (two rooms touching without a door is not a violation — this matches
`measure_spatial_adjacency`, which only asks that requested pairs touch). A required edge is a
shared boundary of positive length; corner-only contact does not count (as in the realizer).

### 2.3 Why the SAT answers are complete
A dissection into *p* rectangles has at most *p−1* maximal interior segments, so at most *W−1*
vertical and *H−1* horizontal cut lines with (W−1)+(H−1) ≤ p−1. Every dissection therefore fits an
integer grid with **W+H = p+1**; the solver tries every such (W,H). UNSAT on all of them is a proof
for the whole family, not a budget artefact (no budget was used for the 20 briefs; a conflict
budget was used only in the corpus sample and "UNKNOWN" is reported separately there). Sanity
checks (`sanity.py`): K4 is UNSAT for rectangles and SAT with one L; the 5-room pinwheel *graph* is
SAT even for band layouts (extra contacts allowed — see §7.3); an edge with three common
neighbours is UNSAT for rectangles and SAT with one L.

### 2.4 Theory used
Two graph patterns make the rectangle families UNSAT without a solver (proof in §7): a **K4**
(four mutually adjacent rooms) and a **triple lens** (an edge whose endpoints have ≥3 common
neighbours). Both force a separating triangle in every planar embedding; rectangular duals exist
exactly when there is none (Koźmiński–Kinnen 1985; Felsner's survey states it as *"A planar
triangulation with designated outer vertex v∞ of degree four admits a rectangular dual exactly if
it has no separating triangle, i.e., if it is 4-connected."*).

---

## 3. Reconstruction of the four failures

Figures: `figures/B10_failure.png`, `B13_failure.png`, `B15_failure.png`, `B16_failure.png` — each
shows (a) the required graph with node degrees and the obstruction ringed red, (b) the production
search's best embedding with preserved (green) / lost (red dashed) edges, (c) that GridWing slot
layout, (d) an exact witness layout in the smallest family that carries all edges.

### B10 — 9 rooms, 14 edges (brief: 4 bedrooms, 2 wet rooms, 16×18 m)
- Degrees: HALL 8, LIVING 4, BATHROOM_1 3, BEDROOM_1 3, BATHROOM_2 3, KITCHEN 2, BEDROOM_2 2,
  MASTER_BEDROOM 2, BEDROOM_3 1.
- Production best: GRID 3×3 (rows 3,3,3), **9/14**, lost 5. Exact max inside the production slot
  structures: 9/14 (the heuristic is optimal within its own search space).
- Obstruction: **K4 {HALL, LIVING, BEDROOM_1, BATHROOM_1}** and a triple lens on HALL–LIVING with
  common neighbours {BATHROOM_1, BEDROOM_1, KITCHEN}.
- Max carried by any band layout 13/14; any slicing 13/14; any rectangles 13/14.
- Removing any one of HALL–LIVING, HALL–BEDROOM_1, HALL–BATHROOM_1, LIVING–BEDROOM_1,
  LIVING–BATHROOM_1 makes the rest band-representable; removing BEDROOM_1–BATHROOM_1 does not (the
  triple lens survives).
- One L-shaped room restores 14/14 even in a band layout: LIVING, HALL, BEDROOM_1 or BATHROOM_1
  (any K4 member). KITCHEN/MASTER/BEDROOM_2/BEDROOM_3/BATHROOM_2 as the L room: UNSAT.

### B13 — 10 rooms, 12 edges (brief: 4 bedrooms, 2 wet rooms, 11×12 m, closed plan)
- Degrees: HALL 6, LIVING 4, DINING 3, KITCHEN 2, BATHROOM_2 2, BEDROOM_1 2, MASTER_BEDROOM 2,
  BATHROOM_1 1, BEDROOM_2 1, BEDROOM_3 1.
- Production best: GRID 3×4 (rows 4,3,3), **9/12**, lost 3. Exact max inside the production slot
  structures: 9/12.
- Obstruction: **none** (planar, no K4, no triple lens).
- **A band layout carries 12/12** (witness in the figure, e.g. HALL as one full-width middle band
  with the bedrooms above and the public rooms below). Slicing 12/12, rectangles 12/12.
- Every lost edge is a search loss; no new representation is needed.

### B15 — 11 rooms, 15 edges (brief: 5 bedrooms + safe room, 2 wet rooms, 12.5×14.5 m)
- Degrees: HALL 9, BATHROOM_2 4, BATHROOM_1 3, LIVING 3, KITCHEN 2, MASTER_BEDROOM 2, BEDROOM_2 2,
  BEDROOM_3 2, BEDROOM_1 1, BEDROOM_4 1, SAFE_ROOM 1.
- Production best: GRID 4×3 (rows 3,3,3,2), **9/15**, lost 6. Exact max inside the production slot
  structures: 10/15 (here the greedy+swap heuristic is one edge short of its own structures' optimum).
- Obstruction: **triple lens on HALL–BATHROOM_2** with common neighbours {BATHROOM_1, BEDROOM_2,
  BEDROOM_3} (a wet core touching the hall, two bedrooms and the other bathroom).
- Max carried by any band layout 14/15; slicing 14/15; rectangles 14/15.
- One L-shaped room restores 15/15 even in a band layout: HALL, BATHROOM_2, BATHROOM_1, BEDROOM_2 or
  BEDROOM_3.

### B16 — 13 rooms, 19 edges (brief: 5 bedrooms + safe room, 3 wet rooms, 18×12 m, open plan)
- Degrees: HALL 10, LIVING 6, KITCHEN 3, BEDROOM_1 2, BEDROOM_2 2, BEDROOM_4 2, DINING 2,
  BATHROOM_1 2, BATHROOM_2 2, BATHROOM_3 2, MASTER 2, SAFE_ROOM 2, BEDROOM_3 1.
- Production best: GRID 5×3 (rows 3,3,3,2,2), **11/19**, lost 8. Exact max inside the production
  slot structures: 12/19.
- Obstruction: **triple lens on HALL–LIVING** with common neighbours {BATHROOM_3, BEDROOM_1,
  BEDROOM_4} — three rooms each required to touch both the hall and the living room.
- Max carried by any band layout 18/19; slicing 18/19; rectangles 18/19.
- One L-shaped room restores 19/19 even in a band layout: HALL, LIVING, BATHROOM_3, BEDROOM_1 or
  BEDROOM_4.

The per-edge table (`failure_matrix.md`) lists every lost edge of every brief with its class, the
structural reason and the minimal capability.

---

## 4. Taxonomy of the lost adjacencies

Only two causes occur; the others on the candidate list were tested and ruled out as causes.

| cause | occurs | evidence |
|---|---|---|
| **A. Search-space restriction of the production GridWing search** (balanced row lengths; `1,1,…,remainder` spans; `n_rows ≤ 6`) — equivalently a **per-slot degree cap**: a span-1 cell touches ≤ 2 row-neighbours + 1 above + 1 below = 4, while the hubs need 6–10 | B13: 3/3 lost edges; B10: 4/5; B15: 5/6; B16: 7/8 | exact SAT inside the production structures is 9/14, 9/12, 10/15, 12/19 but inside the full GridWing dataclass it is 13/14, 12/12, 14/15, 18/19; max slot degree of any production structure is 4 (`data/slot_degree_caps.json`) vs HALL degree 8/6/9/10 |
| **B. Separating-triangle obstruction** (K4 or an edge with ≥3 common neighbours) — unrepresentable by *any* dissection into rectangles | B10: 1 edge (the K4), B15: 1 edge (lens HALL–BATHROOM_2), B16: 1 edge (lens HALL–LIVING) | theorem §7 + SAT UNSAT over every rectangle family; max-edge solver stops at m−1 for all three |
| grid vertex degree limitation | **not a cause** at the representation level — a band cell spanning the full width touches every cell of both adjacent rows (a K1,8 star is band-representable, `sanity.py`); it is only a cause inside the *searched* span pattern (= cause A) | |
| room needing contacts on several portions of one side / multiple neighbours along one wall | representable by GridWing as defined (a wide cell over several narrow cells) — lost only via A | B13 witness |
| T-junctions | every band layout already has T-junctions; not a limiting factor | |
| unequal subdivision | representable (free spans) — lost only via A | |
| cycle / branching structure | cycles are carried by band layouts (C4, wheel W4 tested SAT); branching is the hub case above | |
| rectangular-dual constraints | **this is cause B**; the specific constraint is "no separating triangle", not the edge count (`m ≤ 3n−7` holds for all four graphs) | |
| embedding/search weakness (heuristic quality) | minor: the greedy+swap is optimal within its structures for B10/B13 and 1 edge short for B15/B16; the *structures* are the problem, not the local search | `data/slot_exact.json` |
| fixed-cell assumption, row/column restriction, room-shape restriction | these are the three ingredients of cause A; the band restriction itself (every room spans its band) was never binding — band and general rectangles have identical maxima on all four graphs | |
| requirement for non-rectangular (L-shaped) space | **this is the fix for cause B**, and one L room always suffices for these four | §6 |
| impossible under any rectangular partition | B10/B15/B16 for exact adjacency; **B19** (not in the four) is non-planar and impossible under *any* partition of the plane, polygons included | `levels_*.json` |

Also measured and **not** a cause for the four: the dimension solver (`_solve_grid`) — Gate A never
reached it. It is the dominant risk for the next step (§10, §11).

---

## 5. Algorithm failure vs representation failure

| brief | m | production search | exact optimum in the production slot structures | any band layout (GridWing dataclass) | any slicing tree (Geometry Core) | any rectangles | lost to search / lost to representation |
|---|---|---|---|---|---|---|---|
| B10 | 14 | 9 | 9 | 13 | 13 | 13 | 4 / 1 |
| B13 | 12 | 9 | 9 | **12** | 12 | 12 | 3 / 0 |
| B15 | 15 | 9 | 10 | 14 | 14 | 14 | 5 / 1 |
| B16 | 19 | 11 | 12 | 18 | 18 | 18 | 7 / 1 |

Verdict per graph:
- **B13 → A (algorithm).** A valid layout exists inside the current GridWing representation; the
  search cannot reach it. Evidence: SAT witness in `levels_B10_B13_B15_B16.json` → `B13.levels.band_y`.
- **B10, B15, B16 → B (representation), but only by one edge each**, and the representation that
  fails is "rooms are rectangles", not GridWing specifically: band layouts, slicing trees and
  non-guillotine rectangular layouts all stop at m−1. Switching GridWing for the Geometry Core's
  slicing trees or for the non-guillotine realizer would gain **nothing** on these graphs.
- Note on #142A's disclosed gap: the AC-6 `PLACEMENT` bucket ("a structure was selected but no
  assignment of it could satisfy the request") is exactly what every one of the 4×6 production
  structures is — the exact SAT shows no assignment of any of them carries the full graph.

---

## 6. Minimum additional expressive power

| brief | smallest relaxation that carries the full graph | tested alternatives that do NOT help |
|---|---|---|
| B13 | **none** — the existing `GridWing` dataclass; replace the search (free row lengths and spans, exact assignment) | — |
| B10 | GridWing band layout **+ one L-shaped room** (a room occupying two cells in adjacent rows that share an aligned edge — a "merged cell"), the L being any of HALL / LIVING / BEDROOM_1 / BATHROOM_1 | slicing trees (13/14), non-guillotine rectangles (13/14), variable-width cells, multiple neighbours per side, T-junctions — all still rectangles |
| B15 | same, L ∈ {HALL, BATHROOM_2, BATHROOM_1, BEDROOM_2, BEDROOM_3} | same |
| B16 | same, L ∈ {HALL, LIVING, BATHROOM_3, BEDROOM_1, BEDROOM_4} | same |

Observations that constrain the design:
- The L room never needs to leave the band structure: "band + 1 L" is SAT for all three. In
  GridWing terms this is **one `zone_id` appearing in two vertically adjacent rows with one shared
  column boundary** — the smallest conceivable change to the dataclass (today `GridWing` has no
  `groups`; only `RowWing` slots may be a `ShapeGroupIntent`, see `rectilinear_realizer.py:1267`).
- HALL is a valid L candidate in all three — architecturally the natural one (an L-shaped
  corridor wrapping a wet core or the living room), and it keeps every habitable room rectangular.
- Two L rooms are never needed for these briefs; k=2 was not required anywhere in the 20.
- Removing one edge is the *only* alternative, and the removable edges are listed per brief in
  `failure_matrix.json` (`edges_whose_removal_alone_restores_rectangles`). This report does not
  recommend dropping them; it records which single requirement each obstruction hinges on.

---

## 7. Theory, connected to these graphs

### 7.1 Rectangular duals and the separating triangle
A dissection of a rectangle into rectangles, with the four sides of the envelope added as four
outer vertices, has a contact graph that is a planar triangulation with no separating triangle
(Koźmiński & Kinnen 1985; Bhasker & Sahni 1988; Ungar 1953 in the dual setting; survey: Felsner,
*Rectangle and Square Representations of Planar Graphs*, Thm 2.2). The converse holds too, which is
why rectangular-dual algorithms exist (Bhasker–Sahni linear time; He 1993; Kant–He 1997; Fusy's
transversal structures). Our required graphs ask only for a **subgraph** of the contact graph
(extra contacts allowed), so the question is: can G be extended to such a triangulation on the same
room set plus the 4 outer vertices? Two patterns in G make this impossible in *every* embedding:

- **K4 ⊆ G** (B10). Any planar drawing of a K4 puts one vertex inside the triangle of the other
  three; the four outer vertices (and every other room) are outside that triangle → a separating
  triangle. Architecturally: three mutually touching rectangular rooms meet at one T-junction and
  enclose nothing, so a fourth rectangle touching all three has nowhere to be.
- **An edge ab with three common neighbours x, y, z** (B15, B16; also B03, B14, B19). Around the
  wall ab there are only two sides; the three triangles abx, aby, abz nest, and the middle one
  separates the inner from the outer → separating triangle. Architecturally: at most two rooms can
  touch both sides of one straight wall segment's two ends — a third needs the wall to bend, i.e. an
  L-shaped room.

Both are decided in O(n·Δ²) with no solver (`diagnostics()`), which is why they are also a cheap
pre-check for the proposer (§11, variant). The edge bound `m ≤ 3n−7` is a weaker necessary
condition: all four graphs satisfy it, so density is not the issue — *local* triangle structure is.

### 7.2 Rectilinear duals: how many bends are needed
Every planar triangulation has a rectilinear dual with rooms of at most 8 sides, and 8 is necessary
in general (Yeap & Sarrafzadeh 1993; He 1999; Liao–Lu–Yen 2003). L-shapes (6 sides, one bend) are
*not* universally sufficient, which is why "limited L-shaped rooms" has to be tested per graph rather
than assumed — here it suffices for every one of the 20 briefs that is planar (SAT witnesses).
Related: Sun & Sarrafzadeh, *Floorplanning by graph dualization: L-shaped modules* (Algorithmica
1993); Shekhawat et al., *Automated generation of floor plans with minimum bends* (AI EDAM 2024);
Rinsma 1987 (a planar graph with no rectangular floorplan even with free areas).

### 7.3 Slicing vs non-slicing — a distinction that does not bite here
Slicing floorplans are exactly the mosaic floorplans with no pinwheel/windmill; they correspond to
separable permutations, mosaic floorplans to Baxter permutations (Ackerman–Barequet–Pinter 2006;
Yao et al. 2003). That is a statement about the *dissection*, not about which graphs it can carry
as a subgraph: the wheel graph W4 (the pinwheel's own contact graph) is carried by a band layout
with two extra contacts (`sanity.py`), and on all four briefs slicing and non-guillotine rectangles
have identical maxima. **"Non-guillotine solves it" is false for these graphs** — demonstrated, not
argued. The Geometry Core's slicing trees already span the same reachable topologies as the
non-guillotine realizer for subgraph-realization; what the realizer adds (exact pinwheel adjacency,
fewer forced extra contacts) is a different benefit.

### 7.4 Band layouts (what GridWing is)
A `GridWing` is a depth-2 slicing tree (horizontal cuts into bands, then vertical cuts) with all
vertical cut positions drawn from one global set. Cross-band contacts between consecutive bands form
a monotone staircase (two interval sequences tiling the same width), so a hub can touch every cell of
both neighbouring bands; the structural limit is that rooms in non-adjacent bands never touch and a
room's left/right neighbour is unique. On this corpus and these briefs that limit never binds
(band = slicing = rectangles everywhere measured), which is the strongest argument for keeping the
representation and fixing the search.

### 7.5 Topology-first floorplanning
The pipeline shape BuildSmart is converging on (graph → rectangular/rectilinear layout → sizing) is the
classical rectangular-dual pipeline (Bhasker–Sahni; Shekhawat's generic rectangular floor plans;
graph-based generators such as Graph2Plan). The two theory facts that matter for us are exactly the
two found above: feasibility is a local triangle condition (cheap to check at proposal time), and
one bend per obstruction is the standard escape.

---

## 8. Candidate representation families, evaluated

| candidate | B10 | B13 | B15 | B16 | 20 briefs | ResPlan sample (§9) | reuse / 2nd engine | complexity | search space | main risk |
|---|---|---|---|---|---|---|---|---|---|---|
| **C1. GridWing as defined + exact embedder** (free row lengths/spans, SAT/CP or exhaustive band enumeration) | 13/14 | **12/12** | 14/15 | 18/19 | 13/20 full | ~99% | reuses `GridWing`, `_build_grid_wing`, `realize_layout`; replaces one function (`_assign_rooms_to_slots`); no second engine | low (a SAT model of ~10³–10⁴ clauses solved in ms; or enumerate row partitions for n ≤ 13) | band layouts of n rooms ≈ ordered set partitions × interleavings; exact solve is instant at n ≤ 13 | `_solve_grid` rank-1 sizing cannot hit per-cell areas (B01: 16/68 band layouts size) — the topological witness is not always sizable |
| **C2. Geometry Core slicing tree built from the graph** | 13/14 | 12/12 | 14/15 | 18/19 | 13/20 | same as C1 (no graph here separates them) | reuses `solve_fixture` (any `Split/Leaf` tree); needs a new graph→tree builder; stays in the product path (no realizer) | medium: tree synthesis from adjacency is a search over 2^(n−1) shapes × leaf orders | larger than C1 for no topological gain | same topological ceiling as C1; the product's forced-cut/exposure semantics constrain trees further |
| **C3. Non-guillotine rectangular (rectangular dual)** | 13/14 | 12/12 | 14/15 | 18/19 | 13/20 | same | the realizer path: parallel engine, dead flag, 13 validator checks need polygon variants only for notch-carve groups | high (Bhasker–Sahni or SAT over all dissections, then a 2D sizing solver) | all rectangular dissections (Baxter numbers) | **no topological gain over C1 on any measured graph** |
| **C4. GridWing + one merged-cell (L-shaped) room** | **14/14** | 12/12 | **15/15** | **19/19** | 19/20 (all planar briefs) | ~100% of planar sample | extends `GridWing` with one `zone_id` in two adjacent rows (like `RowWing.groups`); validator path exists for 2-rect rooms (`room_merge.validate_merged_room`, C1/C2/C3/C20/C27 redesigned) but only for LIVING+KITCHEN | medium: dataclass + `_build_grid_wing` merge + reuse of `_group_checks`; sizing of the L cell | C1's space × (n choices of L room) | validators C8/C19 exposure for L fragments; door placement on the L's inner corner; the dimension solver again |
| C5. Free orthogonal layouts (polygons) | 14/14 | 12/12 | 15/15 | 19/19 | 19/20 | 100% | new engine, new validators | very high | huge | over-powered: nothing measured needs more than one bend |

Non-planar B19 is unrepresentable by every family — it is a proposal defect, not a representation gap.

**Conclusion of the comparison.** C1 is the floor (it alone closes B13 and, if sizable, all 13
band-representable briefs); C4 is the one additional capability the measured failures justify; C2 and
C3 buy nothing topological and C3 is a second engine. The decisive unknown is not topology any more
but **dimensioning** (`_solve_grid`), which is why the next experiment (§11) measures it.

---

## 9. Beyond the four graphs

### 9.1 The other 16 frozen briefs (same selection rule, `levels_*.json`)
| level | briefs |
|---|---|
| band layout (GridWing dataclass) carries all edges | B01, B04, B05, B06, B07, B08, B09, B11, B12, B13, B17, B18, B20 → **13/20** |
| rectangles impossible; one L-shaped room suffices | B02 (K4), B03 (lens), B10 (K4), B14 (lens), B15 (lens), B16 (lens) → **6/20**, all six confirmed SAT with one L-shaped room (B16: LIVING, HALL, BEDROOM_1, BEDROOM_4 or BATHROOM_3) |
| non-planar — impossible under any partition of the plane | **B19** (25 edges on 12 rooms, two K4s, a lens of six) → 1/20 |

The production search embeds **0/20** of these (it also fails every band-representable one), so the
search-space defect of §4-A is systematic, not specific to B13.

### 9.2 ResPlan corpus (17,107 plans, external pickle; measurement scripts `corpus_extract3.py`, `corpus_stats4.py`)
Methodology. Spatial *touching* graphs were computed geometrically from each plan's room polygons
(indoor rooms: living, kitchen, bedroom, bathroom, storage; balconies excluded): two rooms touch if
their polygons, each grown by half the plan's wall thickness + 5 cm, overlap along ≥ 1.0 m (sensitivity
at 1.5 m also reported). Two ResPlan quirks had to be handled and are disclosed: 4,852 plans repeat
one polygon under several node ids (deduplicated by geometry), and the `inner` polygon is the union of
the rooms, not a corridor — **ResPlan has no circulation node at all**; the hall is absorbed into
`living`, which is non-rectangular in 97% of plans. The corpus therefore cannot test HALL-hub
topologies directly; it tests how often real touching graphs exceed rectangles. ResPlan's own typed
`adjacency ∪ via_door` graph (the #149 Table-C definition) was also measured and is far sparser (mean
6.1 edges, 93% tree-like) — it under-records touching, as #149 already noted, so it is not used for
the conclusions.

| statistic (≥1.0 m touching, 17,107 plans) | value |
|---|---|
| rooms per plan: q10/25/50/75/90 | 6 / 6 / 6 / 8 / 9 (mean 6.9) |
| edges per plan | 5 / 6 / 8 / 9 / 11 (mean 7.8) |
| density | 0.24 / 0.33 / 0.40 / 0.50 / 0.53 |
| max degree (hub = living in 96% of plans) | 3 / 3 / 4 / 5 / 6 |
| room degree distribution | d=1 20%, d=2 42%, d=3 22%, d=4 7%, d≥5 5% |
| cycle rank (independent cycles) | 0 / 1 / 2 / 3 / 4; tree-like 13% |
| planar | 99.9% |
| K4 present / triple lens present / either (provably needs a non-rectangular room) | 1.6% / 1.4% / **2.0%** (at 1.5 m: 0.4% / 0.3% / 0.5%) |
| `m > 3n−7` | 0.02% |
| obstruction role patterns | K4: bathroom-bedroom-kitchen-living, bathroom-bathroom-bedroom-living; lens edges: bedroom–living, bathroom–living |

Representation levels on a random sample of 800 plans (seed 142; exact SAT with a 150k-conflict
budget per grid): **782 band layout (GridWing dataclass), 17 band + one L-shaped room, 1 non-planar
(a spurious geometric edge), 0 unknown, 0 needing slicing/non-guillotine beyond band, 0 needing more
than one L** (`data/corpus_levels_v3.json`). The band layout carries every real touching graph that has
no obstruction, and one L-shaped room carries every obstructed one in the sample.

Reading. Real plans are much sparser than the LLM proposals (hub degree 4 vs 8–10; 2% obstructed vs
30% of the briefs). The two causes found on B10–B16 are the right two for real plans too — band
layouts cover real touching topology almost entirely, and the residual needs exactly one bend — but
the LLM proposer over-specifies adjacency relative to real plans by an order of magnitude, which is a
proposer/critic finding rather than a representation finding (see §11, variant).

---

## 10. Side finding: B01 is not blocked by its brief

#160 and #142A refused B01 (`SHORT_SIDE_INFEASIBLE`, KITCHEN 1.5 m) after an exhaustive 31×31
envelope search over the **pinwheel**, chosen because `n == 5` is tried first. B01's 6-edge graph is
also a band layout: there are exactly 68 distinct band layouts carrying it (`b01_enum.py`), and the
*existing* `GridWing` + `_solve_grid` + `realize_layout` dimension **16 of them** with the same
31×31 envelope grid and the same wet-room resolution #142A used — each **realized, validator PASS,
spatial 6/6, access 4/4** (`data/b01_realized.json`, `figures/B01_pinwheel_vs_band.png`). The other
52 fail `AREA_INFEASIBLE` (rank-1 sizing), which quantifies the dimensioning risk for §11. No
validator, minimum or rule was touched; this is a caller-side choice of carrier.

---

## 11. Recommended bounded next experiment

**Title.** Exact band embedding on the existing GridWing: does the carrier size what it can carry?

**Architectural question.** Given that the GridWing dataclass topologically carries 13/20 frozen
briefs and ~99% of real touching graphs, is the binding constraint now the **dimension solver**
(`_solve_grid`'s rank-1 fit) rather than topology? I.e. is the next investment a sizing solver, not a
representation?

**Hypothesis (falsifiable).** With an exact band-layout embedder (SAT/CP or exhaustive enumeration
of band layouts, n ≤ 13) feeding the *unchanged* `GridWing` → `realize_layout` path, at least
**9 of the 13** band-representable briefs reach a realized, validator-passing house that preserves
100% of requested spatial adjacency and ≥ 90% of requested access edges, using the #142A envelope
retry ladder.

**Implementation boundary.**
- One new, isolated module (e.g. `ai_harness/topology_poc/band_embedder.py`): enumerate/solve band
  layouts that carry the full graph; emit `GridWing`s (several per brief, ranked by a trivial area
  plausibility score). May depend on `python-sat` as an *optional* harness dependency, or use pure
  enumeration (68 layouts at n=5; bounded by ordered set partitions at n ≤ 13 — measure and cap).
- A driver mirroring `gap_closure_142a.py` that tries each candidate `GridWing` through the existing
  retry ladder and records per-brief: #layouts, #dimensioned, failure constraint histogram.
- **Not changed:** `GridWing`, `_solve_grid`, `_build_grid_wing`, `realize_layout`, validators, room
  minimums, the frozen dataset, the selection rule. No production caller.

**Dataset.** The 20 frozen briefs (`generation-dataset.json`, same sha, same `best_policy_valid`
selection). Report the 13 band-representable ones as the primary set and the 6 obstructed ones as
"refused: SEPARATING_TRIANGLE" with the named obstruction (a new, honest refusal class, no silent
drop).

**Success criteria.** ≥ 9/13 realized + validator PASS + spatial 100%; refusals for the other ≤ 4
classified `DIMENSION_SOLVER` with the constraint named.
**Failure criteria.** ≤ 5/13 realized → the band carrier is topologically sufficient but
`_solve_grid` is the blocker; the next step is a per-cell area solver (LP over row heights/column
widths with per-cell bounds), **not** a new representation.
**Ambiguous zone (6–8/13).** Report per-brief which cell violated which bound; decide between
solver and representation on that evidence.
**Stop rule.** Stop when all 20 briefs have a classified outcome, or after one working day of
implementation, or the moment anything outside the boundary above needs to change. Do not add the
L-shaped cell in this experiment; it is the next one, only if this one passes.

**Variant worth running alongside (zero implementation risk).** Add the §7.1 check (planarity, K4,
triple lens) as a *reported* field on proposals in the harness — 6/20 briefs would be flagged before
any geometry is attempted, and the critic/prompt owners can decide whether a proposal that needs a
bent room is what they want the proposer to produce.

---

## 12. Constraints honoured

No realizer built, no production code or validator touched, no requirement relaxed, no adjacency
dropped (edge-deletion results are reported as analysis, not applied), acceptance criteria unchanged,
non-guillotine not credited without demonstration (it is demonstrated **not** to help), no LLM
geometry generation assumed, no refactor. All code is disposable analysis under
`backend/spikes/topology_representation/` and needs an isolated environment with `python-sat`
(`uv venv … && uv pip install python-sat networkx matplotlib`); it is not part of the dev
`.venv` or CI. Working tree: new untracked files only; nothing committed, nothing checked out.
