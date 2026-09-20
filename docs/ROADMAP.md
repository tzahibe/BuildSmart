# BuildSmart — Unified Product Roadmap (owner-approved)

Status: **OWNER-APPROVED ROADMAP** since 2026-09-18. The owner's roadmap task (EPIC 0 + 16 product Issues)
and the earlier proposed roadmap (2026-09-17, 32 topics) are merged here; overlapping topics were unified
into one ROOT Issue each. Every ROOT below carries `owner:approved`; the Team Lead executes them
autonomously (decomposition into child Issues, workers, PRs, CI, regression, review, repair) and pulls the
next ones from this list as capacity frees up (owner rule of 2026-09-18: "you may create Issues and approve
them for work from the roadmap; use every worker; release blocked work"). **Only the owner merges to
`main`** (normal periods: per PR; weekend/holiday periods: one rollup PR).

## How this roadmap is used

1. Priority and dependencies come from the DAG below, not from Issue numbers.
2. A ROOT Issue is executed as one task or decomposed into `agent:child` Issues that inherit its
   authorization and must stay inside its scope. Work a ROOT does not require is reported as a
   PROPOSED PRODUCT FOLLOW-UP and waits for the owner.
3. Topics in "Later / not yet a ROOT" are pulled by the Team Lead when their predecessors are done and
   capacity is free — as ROOT Issues with a contract and a knowledge check, `owner:approved` on
   creation (authorized by this roadmap).
4. Every implementation asks "which generic architectural invariant or quality principle is missing?" —
   topology, semantics, realized geometry, deterministic validation, quality metrics; never coordinate
   hacks, screenshot special cases, arbitrary constants or renderer tricks.

## EPIC 0 — Architectural reference & quality benchmark (P0 / foundation) — ROOT #28 (decomposed)

| Child | Issue | Depends on |
|---|---|---|
| Quality rubric A–O + anti-pattern library | #29 | — |
| Reference collection V1 (schema, rights policy, ≥30 entries) | #30 | — |
| Reference annotations (WHY THIS PLAN WORKS) | #31 | #29, #30 |
| Reference benchmark framework (plan vs rubric vs references) | #32 | #29, #30 |
| Reviewer integration (rubric in reviews, overfit downgrade, deterministic stays authoritative) | #33 | #29 |

Merged from the old roadmap: "סגירת איכות התכנון הבסיסי" (measurement side; the M1–M6 baseline is #17,
done) and "Plan Quality Evaluation / Benchmark" (P3).

## P0 product ROOTs

| Owner item | ROOT | Status | Depends on | Merged old-roadmap topics |
|---|---|---|---|---|
| Issue 1 Circulation efficiency & corridor minimization | #36 | approved | #29 | Hallways / Circulation Quality |
| Issue 2 Entrance & circulation integration | #22 (+ #20 entrance policy) | approved | #20 → (#17 ✓, #18); #22 → #20, #36 | Entrance / Exterior Door; Entrance Sequence Quality |
| Issue 3 Realized area & dimension consistency | #34 | approved | — | Exact Area / Room Area Fidelity (display side; requested-vs-realized fidelity stays a later topic) |
| Issue 4 Door placement / swing / clearance | #38 (after #18 access topology, in CI) | approved | #18 | Doors + Access Topology |
| Issue 5 Window & exterior exposure semantics | #19 | approved | #17 ✓, #18 | Windows + Exterior Exposure; North/Orientation (orientation field only) |
| Issue 6 Wet-room privacy & access quality | #37 | approved | #18 | — (wet-room quality tier is done) |
| Issue 7 SAFE_ROOM / MAMAD preservation | #35 | approved | — | — |
| Issue 8 Laundry room invariants | #21 | approved | #18, #19 | Laundry Room semantics |
| ReviewPage shows the quality data (pulled forward from P2 on 2026-09-19: the P0 wave is invisible without it) | #63 | approved | — | ReviewPage completion (data-display part) |

## P1 product ROOTs

| Owner item | ROOT | Depends on | Merged old-roadmap topics |
|---|---|---|---|
| Issue 9 Architectural interior layout MVP | #39 | #19, #38 | Kitchen / Bathroom fixture-aware planning; Storage / Closets (objects only) |
| Issue 10 Furnishability / usability validation | #40 | #39 | — |
| Issue 11 Public-zone composition | #41 | #39 | Concept Quality (public-zone part) |
| Issue 12 Master-suite access & privacy | #42 | #37, #38 | — |
| Issue 13 Dead space / residual pocket detection | #43 | #36, #22 | Hallways / Circulation Quality (dead-end part) |

## Concept Engine v2 — ROOT #74 (owner-approved 2026-09-20, decomposed)

Evidence and the three-way comparison (generative / retrieval / hybrid → hybrid): `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md`.
Owner conditions: the PRIMARY plan stays unchanged until the owner has seen #78's results; #79 is conditional
only (a draft until an explicit decision after #78).

| Child | Issue | Depends on |
|---|---|---|
| ConceptSpec contract, verified circulation-class tag, topological distinctness, corpus diversity baseline | #75 | — |
| Structured concept pattern prior (census aggregates + reference archetypes), deterministic lookup | #77 | #75 |
| Concept-level score from existing realized metrics + bounded realize–measure–adapt loop | #76 | #75 |
| Pipeline insertion behind `CONCEPT_ENGINE_V2_ENABLED`: one plan per circulation class, ReviewPage label, latency budget | #78 | #77, #76 |
| BRANCHED circulation class via a seam-level opening (conditional, draft) | #79 | #78 + owner decision |

Merged from the old roadmap: "Alternative Plans / Diversity" and "Concept Quality / Decomposition Engine".
#36 (circulation metrics) and #43 (dead space) feed the loop of #76/#78 when they land; #39/#41 consume the
concept tags later.

## P2 product ROOTs

| Owner item | ROOT | Depends on | Merged old-roadmap topics |
|---|---|---|---|
| Issue 14 Plumbing / wet-core efficiency | #44 | #37 | — |
| Issue 15 Wall semantic model | #45 | #38, #19 | — |
| Issue 16 Professional architectural drawing | #46 | #45, #39, #40 | SVG/DXF production quality (SVG part); Architectural Report / PDF (drawing part) |

## Dependency DAG (execution order)

```
#28 EPIC 0 ──┬─ #29 rubric ──┬─ #31 annotations (also #30)
             ├─ #30 refs ────┤─ #32 benchmark (also #30)
             │               └─ #33 reviewer integration
             └─────────────────► #36 circulation ──► #22 entrance integration ──► #43 dead space
#18 doors/access (CI) ──┬─ #20 entrance policy ──► #22
                        ├─ #19 windows ──┬─ #21 laundry
                        │                ├─ #39 interior layout ──┬─ #40 furnishability ──► #46 drawing
                        │                │                        └─ #41 public-zone composition
                        ├─ #37 wet privacy ──┬─ #42 master suite (also #38)
                        │                    └─ #44 plumbing efficiency
                        └─ #38 door swing ──┬─ #39, #42
                                            └─ #45 wall model (also #19) ──► #46
#34 area consistency (independent)      #35 safe room (independent)
#74 Concept Engine v2 ──► #75 ──┬─ #77 prior ──┬─ #78 pipeline (flag) ──► #79 branched (conditional)
                                └─ #76 score ──┘   (#36, #43 feed #76/#78 when merged)
```

## Execution waves (3 workers; locks serialize geometry-core / validator-core work)

- **Wave 1 (now, parallel):** #29, #30 (docs, light), #34 area consistency, #35 safe room, #18 finishing
  in CI; infra #24/#25.
- **Wave 2:** #31, #32, #33 (after #29/#30), #36 circulation (after #29), #20 entrance policy, #19
  windows, #37 wet privacy, #38 door swing (after #18).
- **Wave 3:** #22 entrance integration (after #20, #36), #21 laundry (after #18, #19).
- **Wave 4 (P1):** #39 → #40, #41; #42; #43.
- **Wave 5 (P2):** #44, #45 → #46.

## Later / not yet a ROOT (from the 2026-09-17 roadmap; pulled by the Team Lead when predecessors are done)

- **Buildable Region / Site Constraints** — parcel, setbacks, buildable polygon, orientation, footprint fit
  (feeds #46's plot context).
- **Exact area fidelity vs the requested area** — tolerance, realized vs requested, no silent shrinking
  (display consistency is #34).
- **Multi-Level Phase 2**, **Stairs / Vertical Core**, **Parking / Garage**, **Balconies / Patios / Outdoor
  Connections** (rubric section N), **Storage / Closets / Utility** beyond layout objects.
- **Massing selection quality** (incl. the recorded L-orientation eligibility-ordering follow-up), **Seam /
  Shape Recovery** (Alternative Plans / Diversity and the Concept Engine are ROOT #74 now).
- **North / Orientation / Solar reasoning** beyond the orientation field, **Regulation / Compliance
  Engine** (separate corpus — never mixed with the architectural references), **Clarification Agent**,
  **Plan Editing / Conversational Changes**, **Drag / Resize / Align UI**, **ReviewPage completion**,
  **Architectural Report / PDF output**, **DXF output**.
- **Plan Retrieval / Reference Library** (beyond the curated reference set), **Performance / Runtime**,
  **Knowledge system follow-ups**.
- **INFRA:** Agent-Team / Telegram operational hardening (ongoing: #24 work reports, #25 numbered titles).
- **INFRA — CI optimization (owner-approved 2026-09-19, `docs/CI_OPTIMIZATION_PROPOSAL.md`):** #66 O1
  invariants from the head snapshot → #67 O3 sharded corpus snapshot → #68 O2 trusted push-built snapshot
  store (`docs/CI_SNAPSHOT_CACHE_DESIGN.md`); each in shadow mode (old + new paths, compare step) until
  enough identical real runs, then the old path is removed gradually; then the risk-tier gate policy
  (LOW no corpus unless the contract demands it, MEDIUM only on planner/geometry/validator/requirements
  paths, HIGH + rollup always). Never a coverage or budget reduction.

## Review principles for these Issues

For geometry / circulation / interior PRs the independent reviewer evaluates: (1) does the implementation
satisfy the Issue; (2) does it improve the identified architectural principle; (3) is it consistent with
`docs/architecture_reference/quality_rubric.md`; (4) does it avoid overfitting one plan; (5) does
deterministic evidence support the behavior; (6) are regressions expected and within budget. Deterministic
tests remain authoritative for hard invariants — the semantic review never turns a failing deterministic
validation into PASS.
