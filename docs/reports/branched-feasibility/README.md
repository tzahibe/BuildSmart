# BRANCHED circulation — feasibility

**Question.** Can BRANCHED produce a credible second architectural concept for realistic houses, or
does the current geometry representation prevent it?

**Answer: it can, and the geometry representation does not prevent it.** A BRANCHED plan compiles,
solves, realizes and reads as a genuinely different organisation — an entrance hall that
distributes to the public zone and the master, handing off to a bedroom-wing corridor. It fails
**exactly one check**: C26's corridor dead-end limit. Everything else in the stack already works.

**No production code was changed.** The gate was bypassed in-process, in a harness script, to
measure what lies behind it.

---

## 1. Why it returns nothing on the eight briefs — four independent gates

| # | gate | where | effect on the audited briefs |
|---|---|---|---|
| 1 | programme shape: exactly **4 bedrooms (no safe room)** or **3 (with one)**, and exactly **2 wet rooms** | `_branched_unsupported` | **8 of 8 fail here**, before any other gate |
| 2 | **C26 dead ends, unconditional** — "declines unconditionally until the tree is redesigned" | `_branched_unsupported`'s final line | would decline even a shape that matched |
| 3 | minimum footprint ≈ **18 × 18 m** for the sizing search to find a witness | `_branched_sizing` + the fit check | 0 candidates at 16×16, 1 at 18×18 |
| 4 | the rect it is offered is the **primary's own wing**, not the plot | `concept_engine_v2._compiled_candidates_for` | a 24×24 m brief hands it **12.40 × 12.25 m** |

Gate 4 is the quiet one and it is fatal on its own. The compiled alternative is sized to
`chosen_plan.concept.concept.fixture.wings[0].rect()`, and that rect is capped by **programme
capacity**, not by the plot:

| brief footprint | rect handed to the compiler | primary gross |
|---|---|---:|
| 20 × 20 m | 14.90 × 14.10 m | 210 m² |
| 24 × 24 m | **12.40 × 12.25 m** | 152 m² |
| 20 × 20 m (3bd + safe) | 11.90 × 13.55 m | 161 m² |

A bigger plot does not produce a bigger rect. So a tree needing 18 × 18 m can never be offered
enough room, whatever the site.

## 2. What the parti actually is

Reconstructed from the compiler and confirmed on a realized plan:

- **primary distribution**: `HALL_A`, a horizontal entrance hall under the public band;
- **secondary circulation**: `HALL_B`, a vertical bedroom-wing corridor, meeting `HALL_A` at a
  corner over a partial shared edge, joined by a declared `CASED_OPENING` (never an open
  connection — the engine's open-group rule requires sibling leaves with a full matching edge,
  which a bent corridor never has);
- **zoning**: public band north, master and a bathroom off `HALL_A`, the bedroom stack off `HALL_B`;
- **entrance**: into `HALL_A`, i.e. arrival rank 0;
- **wet rooms**: one off each hall.

## 3. Where the failures originate

| layer | verdict |
|---|---|
| concept representation | **fine** — the realized plan verifies as `CirculationClass.BRANCHED`, two halls present |
| compiler constraints | the shape gate (gate 1) and the unconditional C26 gate (gate 2) |
| geometry feasibility | **fine** — the fixture solves; the tree is realizable at ≥18 × 18 m |
| room programme handling | fixed 4-member stack; 5–6 bedrooms are not expressible today |
| realization | **fine** — a complete plan with walls, doors, windows and furniture |
| validators | **C26 alone**, with 3 dead ends against a limit of 2 |

Measured, with the gate bypassed, on a 19 × 19 m rect:

```
4 bedrooms, no safe room   realized, class BRANCHED, failed=['C26']
   halls=['HALL_A','HALL_B']  DEAD_ENDS=3 (limit 2)  ratio=0.210  longest=10.65 m
3 bedrooms + safe room     realized, class BRANCHED, failed=['C26']
   halls=['HALL_A','HALL_B']  DEAD_ENDS=3 (limit 2)  ratio=0.205  longest=10.65 m
```

Only C26. Not C3, not C5, not C19, not C24.

## 4. Is it architecturally distinct? Yes — see the render

`figures/production-vs-branched-4bd.jpg`, both drawn by the product's own `DemoPlan`, same brief.

| | production | BRANCHED |
|---|---|---|
| circulation | **one** corridor 1.30 × 13.80 m | **two** halls: 7.90 × 1.30 m + 1.45 × 10.65 m, meeting at a corner |
| organisation | public block, bedroom strip beside one corridor | entrance hall → public zone and master; bedroom wing off a second corridor |
| bedrooms | 16.2–16.6 m² | 9.4 m² each, compact, in a wing |
| leftover | **29.1 m² "unassigned"** | none |
| entrance | into the corridor | into the entrance hall |

This is not a renamed spine and not the same rooms shifted: the access graph has a second
circulation node and the private wing is reached through it, which is precisely the distinction
asked for.

## 5. Programme coverage, honestly

- **3 bedrooms (with a safe room)** and **4 (without)**: supported by the tree, realize, fail only C26.
- **5 and 6 bedrooms**: not expressible — the stack is fixed at four members.

Unlike HUB_LOBBY, this is **not** a hard geometric bound. A hub is limited by its own perimeter
(measured in the previous experiment: a compact lobby serves two bedrooms, full stop). A corridor's
capacity grows with its length, so extending the bedroom stack is a tractable change rather than an
architectural impossibility. Dining, open-plan semantics, safe room and bathrooms are all carried
by the tree's existing variants; **DINING is dropped**, the same defect the hub compiler has.

## 6. The decision

> **BRANCHED can produce a credible second architectural concept. The geometry representation does
> not prevent it.** It is blocked by one validator rule and three reachability gates, none of which
> is about whether the geometry can be built.

C26's threshold of 2 was calibrated, by its own docstring, on spine and hub plans — "every measured
spine/hub plan has at most one real dead end". A two-hall plan structurally has four corridor ends,
so a limit of 2 requires three of them to terminate in a door. The current tree serves one. **The
rule is not wrong; the tree was never designed against it** — which is exactly what its own code
comment says is outstanding.

## 7. Recommended next step — exactly one

> **Redesign the BRANCHED tree so its corridor ends are served, bringing dead ends to ≤ 2.**
> Concretely: terminate `HALL_A`'s west end and `HALL_B`'s south end at a room door placed at the
> end rather than along the flank, so each hall ends in a destination instead of a wall.

Why this one: it is the only blocker that is about the concept itself. It changes a hand-authored
tree in the compiler — no validator change, no Geometry Core change, no new concept family, no
relaxed constraint. The evidence says everything downstream already works: the fixture solves, the
plan realizes, the class verifies, and the result reads as a different house.

Gates 1, 3 and 4 remain afterwards and are **not** part of this step: the shape gate and the
4-member stack would still restrict coverage, and gate 4 — the primary's rect being handed to the
alternative compiler — would still prevent it being reachable in production even once it passes
C26. Those are separate decisions, named here so the sequencing is explicit.

## 8. Scope

No production code changed. No Geometry Core change, no L-shapes, no validator change, no selection
change, no relaxed constraint to buy coverage. The gate bypass was an in-process monkeypatch inside
a throwaway script; nothing in the repository calls it.
