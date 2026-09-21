# BuildSmart — Unified Product Roadmap (owner-approved)

Status: **OWNER-APPROVED ROADMAP** since 2026-09-18. The owner's roadmap task (EPIC 0 + 16 product Issues)
and the earlier proposed roadmap (2026-09-17, 32 topics) are merged here; overlapping topics were unified
into one ROOT Issue each. Every ROOT below carries `owner:approved`; the Team Lead executes them
autonomously (decomposition into child Issues, workers, PRs, CI, regression, review, repair) and pulls the
next ones from this list as capacity frees up (owner rule of 2026-09-18: "you may create Issues and approve
them for work from the roadmap; use every worker; release blocked work"). **Only the owner merges to
`main`** (normal periods: per PR; weekend/holiday periods: one rollup PR; a ROOT with its own integration
branch — Concept Engine v2, `integration/concept-engine-v2` — one rollup PR at a stable integration point).

**Owner priority order (2026-09-20):** 1. finish work already in CI / repair; 2. the open basic P0; 3. Concept
Engine v2 (#74) — the central planning layer from now on; 4. Interior / Furnishability (#39, #40); 5. the rest of
P1; 6. drawing / polish / lower-impact work. Infra: the CI chain #66 → #67 → #68 with at most ONE infra worker,
then no new infra work without a real blocker. No separate Massing / Multi-Level ROOT for now. Encoded in
`.agent/config.yaml` (`governance.priority_roots`, `max_active_by_domain`).

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

## Concept Engine v2 — Hybrid Architectural Planning — ROOT #74 (owner-approved 2026-09-20, decomposed; priority above most P1)

Goal: move BuildSmart from an engine that generates a few fixed partis and checks them to an engine that generates
different architectural concepts, realizes them, measures them and improves them with feedback from the existing
layers. Evidence and the three-way comparison (generative / retrieval / hybrid → hybrid):
`docs/CONCEPT_ENGINE_V2_INVESTIGATION.md`. **The Concept Engine becomes the central planning layer; the existing
layers (validators C1–C29, M1–M6, circulation, wet privacy, dead space, furnishability, public-zone composition)
serve both as validators and as feedback into it.**

Branching: all work against `integration/concept-engine-v2` (from `main` `648292f2`); each child has its own branch,
its PR targets the integration branch, passes CI + regression + ACs + independent review, and is merged there by the
Team Lead with integration validation after every merge; ONE final rollup PR → `main` (freeze, update against main,
full tests, full corpus regression, diversity / quality / runtime p50–p95 benchmarks, combined review, limitations
report) stops at READY_FOR_OWNER — never merged without the owner's explicit approval.

Owner conditions: the PRIMARY plan stays unchanged until the owner has seen #78's benchmark (delivered 2026-09-21:
mechanism correct and safe, diversity 17.6 % vs the 40 % bar, HUB_LOBBY never realized — the generator's per-outline
hub/front-band acceptance is the ceiling). Owner decision: option (b) — #78 merges as infrastructure (flag OFF) and
#79 is expanded into generator-level work; the primary still does not change until a new benchmark.

| Child | Issue | Depends on | State |
|---|---|---|---|
| 1 — ConceptSpec (zoning, circulation style, entrance strategy, wet-core strategy, massing hints, relationships, family/signature, distinctness) + `ArchitectModelGateway` hint slot (never a source of truth) + corpus diversity baseline | #75 | — | in progress |
| 2 — Reference priors: which concepts to try and in what order (SPINE / FRONT_BAND / HUB_LOBBY / TWO_WING / L, wet-core clustering, zoning patterns); never geometry | #77 | #75 | queued |
| 3 — Quality-guided concept search: concept → realize → measure → adapt → realize again (M1–M6, circulation, wet privacy, wet-core, area quality; later dead space / furnishability / public zone) | #76 | #75 | queued |
| 4 — Pipeline integration behind a flag: 2–3 genuinely different alternatives, one per concept family, concept label on the ReviewPage, quality / diversity / runtime / realization-success measurement, owner benchmark, massing / multi-level integration proposal | #78 | #77, #76 | queued |
| 5 — EXPANDED (owner decision 2026-09-21 after child 4's benchmark): generator-level pattern compilers — HUB_LOBBY and BRANCHED independent of the legacy hub template + cross-outline concept search, raising the measured 17.6 % diversity ceiling to the 40 % bar | #79 | #78 | queued |

Merged from the old roadmap: "Alternative Plans / Diversity" and "Concept Quality / Decomposition Engine".
Feedback inputs into the engine as they land: #36 circulation metrics, #43 dead space, #40 furnishability,
#41 public-zone composition. After #78: a proposal for Rectangle / L / Irregular massing, massing selection,
Multi-Level Phase 2 and stairs / vertical core inside the new architecture.

## P1 product ROOTs (order after the Concept Engine; #39/#40 may run in parallel with children 1–3 once the concept ↔ realized-plan interface is stable)

| Owner item | ROOT | Depends on | Priority (owner 2026-09-20) | Merged old-roadmap topics |
|---|---|---|---|---|
| Issue 9 Architectural interior layout MVP | #39 | #19, #38 | 4 — very important; after or alongside #75–#76 | Kitchen / Bathroom fixture-aware planning; Storage / Closets (objects only) |
| Issue 10 Furnishability / usability validation | #40 | #39 | 4 — very important; also a future feedback input to the Concept Engine | — |
| Issue 11 Public-zone composition | #41 | #39 | 5 — and a future feedback input to the Concept Engine, not only post-validation | Concept Quality (public-zone part) |
| Issue 13 Dead space / residual pocket detection | #43 | #36, #22 | 5 — and a future feedback input to the Concept Engine | Hallways / Circulation Quality (dead-end part) |
| Issue 12 Master-suite access & privacy | #42 | #37, #38 | lowered for now | — |

## P2 product ROOTs

| Owner item | ROOT | Depends on | Merged old-roadmap topics |
|---|---|---|---|
| Issue 14 Plumbing / wet-core efficiency | #44 | #37 | — (DONE: landed with the Yom Kippur rollup) |
| Issue 15 Wall semantic model | #45 | #38, #19 | lowered for now (owner 2026-09-20) |
| Issue 16 Professional architectural drawing | #46 | #45, #39, #40 | lowered for now (owner 2026-09-20); SVG/DXF production quality (SVG part); Architectural Report / PDF (drawing part) |

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

## Execution order now (3 workers; owner priority 2026-09-20; locks serialize geometry-core / validator-core work)

1. **In flight to `main`:** #34 (PR #72), #36 (PR #73), #66 (PR #71, READY) — finish without restarts.
2. **Basic P0 still open:** #35 SAFE_ROOM (back on track after PR #57 closed unmerged), #38 door swing (repair), then
   #22 entrance integration once #36 lands on `main`. These stay on the `main` track — never forced into the
   Concept Engine branch.
3. **Concept Engine v2:** #75 → (#77 ∥ #76) → #78 → (#79 only on measured need); child 1 starts as soon as a
   product worker is free — no waiting for all of P0 unless a real lock or dependency conflict exists.
4. **Interior / Furnishability:** #39 → #40 (alongside children 1–3 once the interface is stable).
5. **Rest of P1:** #41, #43 (also as feedback into the engine); #42 lowered.
6. **Drawing / polish:** #45 → #46 lowered.
- **Infra:** #66 → #67 → #68, one infra worker at most (`max_active_by_domain: {infra: 1}`); afterwards no new
  infra work without a real blocker.

## Later / not yet a ROOT (from the 2026-09-17 roadmap; pulled by the Team Lead when predecessors are done)

- **Buildable Region / Site Constraints** — parcel, setbacks, buildable polygon, orientation, footprint fit
  (feeds #46's plot context).
- **Exact area fidelity vs the requested area** — tolerance, realized vs requested, no silent shrinking
  (display consistency is #34).
- **Multi-Level Phase 2**, **Stairs / Vertical Core** — no separate ROOT now (owner 2026-09-20): the Concept
  Engine keeps representation room for rectangle / L / irregular / massing family / future multi-level concepts,
  and #78 delivers a proposal for how they fit; **Parking / Garage**, **Balconies / Patios / Outdoor
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
