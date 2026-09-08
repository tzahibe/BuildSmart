# Branched Circulation — Architecture Investigation

```
BRANCHED_CIRCULATION = SUPPORTED_WITH_SMALL_EXTENSION
```

**Recommended next implementation step: enforce the realized-connectivity invariant as a
validation check derived from walls and openings, replacing C5's declared-graph traversal.**

Investigation only. No implementation was performed. Every claim below is demonstrated against
the running code, not argued from the docstrings.

---

## 1. Why open connectivity currently requires sibling leaves

It does not, quite — and the precise statement matters, because it changes what the fix has to
be.

`engine._mark_open_interfaces` is the **only** place a wall is ever typed `OPEN`:

```python
subtree = set(leaves_of(node))
inside_one_group = any(subtree <= set(g) for g in open_groups)
if inside_one_group:
    ...  # mark the leaves touching this node's cut line as OPEN
```

Two consequences follow:

1. **The only boundaries that can be made OPEN are the internal cut lines of the slicing tree.**
   `leaves_touching()` does collect every leaf touching that cut line, so it is not literally
   restricted to two sibling *leaves* — a whole subtree may face another across one cut.
2. **The open group must contain an entire subtree** (`subtree <= group`). A group that is a
   strict subset of any ancestor's leaves is never marked.

And the sharper root cause underneath both:

> **Every node of a slicing tree occupies a rectangle** (`assign()` passes a `Rect` to every
> node and splits it). So an open group realized this way is *always a rectangle*. An L- or
> T-shaped open region is not "hard" in this representation — it is **unrepresentable**.

Demonstrated. In `V( H(A,B), C )`, A and C are non-siblings that genuinely touch:

```
A-C shared edge: 60 units (3.0 m — they DO touch)
A.E wall type  : PARTITION   <-- declared open group {A, C}, still a wall
C.W wall type  : PARTITION
group {A,B} (a whole subtree): A.S = OPEN
```

So the failure mode is exactly: *declared open, physically walled, silently.*

## 2. The invariant is violated today — in two ways, and one is worse than the corridor problem

`validation.C5` walks the **declared** access graph. It never reads a wall or a generated
opening:

```python
for e in fixture.access.edges:
    graph.setdefault(e.a, set()).add(e.b)
    ...
unreachable = sorted(all_zones - seen)
```

`C6` only checks that a door does **not** exist where it shouldn't. `C7` only checks doors that
were **generated**. Nothing checks that a declared edge produced anything at all.

**Hole 1 — declared OPEN_CONNECTION, no opening.** The non-sibling case above: wall stays
`PARTITION`, and `doors.generate_openings` deliberately skips `OPEN_CONNECTION`, so no opening is
cut either. Passage blocked; C5 green.

**Hole 2 — declared DOOR between rooms that do not touch.** This one has nothing to do with
corridors and is arguably more dangerous. `generate_interior_doors` skips silently when
`shared_edge_len_u <= 0`. Demonstrated on three rooms in a row `A | B | C` with a declared
`A–C` door:

```
A and C share edge: 0 units
declared DOOR edges: 1
generated doors    : 0      <-- edge silently produced no door
C5 says C reachable: True   <-- but there is no door and no shared wall
```

A room can currently be reported as reachable while being sealed. That is the invariant you
asked for, and it is broken now, independently of branched circulation.

## 3. Options compared

### A. Multiple corridor segments joined by explicit openings

Keep each corridor arm as its own zone; join them with `CASED_OPENING` instead of
`OPEN_CONNECTION`. The wall stays `PARTITION` and a real opening is cut in it.

- **Engine change: none.** `generate_interior_doors` already emits openings for
  `CASED_OPENING` whenever the zones share a boundary.
- Architecturally honest: a 1.4 m cased opening between corridor arms reads as continuous
  circulation, and it is what many real plans actually build.
- Costs: the arms remain separate zones for area accounting, and the joint costs a wall.
- **Available immediately, zero risk.** This is the fallback if anything below proves harder
  than expected.

### B. Derive open interfaces from geometry instead of tree structure

Mark `(zone, side) = OPEN` when two zones are **in the same declared open group and actually
touch**, rather than when a subtree happens to sit inside a group.

This is the same shape as a mechanism the engine **already has**: `derive_wall_types` already
accepts injected `safe_room_neighbours`, discovered from solved geometry and fed back through
`solve_fixture`'s bounded re-solve loop. Open interfaces would use that identical path.

- `WallMap` is keyed `(zone_id, Side)` and knows nothing about the tree, so an L-shaped open
  region is **already representable** in the output structure. Only the *derivation* is
  structural.
- Convergence is not a new risk: adjacency in a guillotine tree is fixed by **tree topology**,
  not by the numeric split positions — I established and tested that in the perturbation test
  for the safe-room loop. So the discovered set is stable and settles in one extra pass.
- **Precondition, and it is a real one:** a wall side carries one type, so this is only sound
  when the shared boundary covers the **full side** of both zones. Partial contact reintroduces
  the part-exterior/part-interior problem (the spike's L2). The concept generator must align the
  cuts — which it already does for the branched hall.
- Estimated change: ~15 lines in `derive_wall_types` plus a loop condition. Shape curves,
  assignment and exact tiling are untouched.

### C. First-class multi-rectangle circulation region

A `CirculationRegion` domain object grouping N leaves.

- This is a **modelling** improvement, not an alternative: it does not by itself make the wall
  disappear. It still needs A or B underneath to fix the physical boundary.
- Worth doing later for area accounting and residual reasoning; wrong thing to do first.

### D. The alternative I would actually add — the invariant as a derived check

Independent of A/B/C: replace C5's declared-graph traversal with a graph built from **realized**
geometry — an edge exists only if there is a generated opening on that boundary, or a shared
boundary whose wall type is `OPEN`. This is the only option that *detects* the failure rather
than avoiding one instance of it, and it would have caught both holes in §2.

## 4. Recommendation and verdict

```
BRANCHED_CIRCULATION = SUPPORTED_WITH_SMALL_EXTENSION
```

Geometry Core does **not** fundamentally prevent this. It can be a bounded extension:
**D (the invariant) first, then B (geometric derivation), with A as the standing fallback.**
Nothing in the shape-curve or assignment machinery needs to change, and the injection path B
needs already exists and is already tested.

**The single recommended next step is D**, and deliberately not B, for three reasons: it is
independent of which representation wins; it is the thing that turns a silent failure into a
loud one; and installing it *before* B means B cannot introduce a new silent failure while
fixing an old one. It should also be expected to pass on arrival — every current scenario
declares doors only between rooms the hall genuinely borders — so it lands as a guard, not as a
demolition.

## 5. Re-evaluating the two blocked cases under the proposal

**L-shaped multi-wing.** The blocker was that a hall against a partial seam would be part
exterior and part seam. B does not remove that — it is the *same* full-side precondition. What
changes is that the hall may be **two aligned leaves**: one whose side is entirely exterior, one
whose side is entirely seam, joined by a geometric OPEN interface even though they sit in
different subtrees. That is exactly what B enables and what the tree structure currently
forbids. So multi-wing becomes reachable, conditional on the generator forcing the cut at the
seam extent — which it already knows how to do.

**4BR + safe room + 3 wet rooms.** Honest assessment: **B does not obviously fix it.** That case
now fails inside Geometry Core on forced-cut/shape-curve disagreement, not on connectivity. B
buys a bent corridor, which gives the concept generator a parti it cannot currently express and
therefore a real chance — but I will not claim a number I have not run. It should be re-measured
after B, not before.

## 6. What I did not do

No implementation, no fixture-specific handling, and no change to Geometry Core. The two
demonstrations in §1 and §2 were run as throwaway scripts against the existing engine and left
nothing behind.

Stopping for review.
