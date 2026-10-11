# The architectural brain, delivered end to end (#197)

**What an owner can now do:** request `?engine=brain` and get **several genuinely distinct floor
plans** for the same brief, each proposed as an architectural concept *before* any geometry exists,
each preserving the requested spatial graph exactly, each drawn by the product's own `DemoPlan`.

**Cost: $0. Latency: 0.5–11.4 s. No model call, no API key, no network.**

---

## 1. The decision that shaped this

#194 proved the brain chain works but that its only proposal source was an LLM — ~$0.12 and ~90 s
per brief, an external dependency, a nondeterministic result on the critical path, and (today) no
configured key in production. A product cannot be defined by that.

**So the proposer became an interface, and the primary implementation is deterministic.** The LLM
is now one source among several rather than the one the product stands on.

```
brief
  ├─ DeterministicProposer   HALL_SPINE · PUBLIC_BAND · BEDROOM_WING · TWO_HALL · SERVICE_CORE
  ├─ (RecordedProposer)      the committed #142K proposals
  └─ (LlmProposer)           the existing path — optional, costed, additive
        ↓ all emit the same contact + access graph the critic and pipeline already consume
  proposal_critic   →  gate BEFORE placement
  band_embedding    →  exact 2D placement
  band_sizing → rectilinear_realizer → UNCHANGED validators
  topology_preservation → quality profile → de-duplication → DemoPlan
```

### Representable by construction

#194 measured **7 of 20** LLM proposals dying on a K4 or a triple-lens. Every parti here is a
**tree of contacts plus at most one path**, which contains neither. Bedrooms touch only their
circulation node and their own ensuite — the moment three bedrooms must also touch LIVING they form
a triple-lens ("a straight wall has only two sides") and no rectangle layout exists. Two tests
assert this directly on every generated proposal.

---

## 2. Results — 8 frozen audit briefs

| brief | distinct plans | contacts preserved | doors preserved | bands | seconds |
|---|---:|---|---|---:|---:|
| B08 | 4 | n/n | n/n | ≥2 | 1.1 |
| B20 | 3 | n/n | n/n | ≥2 | 1.7 |
| B02 | 2 | n/n | n/n | ≥2 | 0.5 |
| B11 | 3 | n/n | n/n | ≥2 | 6.3 |
| B16 | 3 | n/n | n/n | ≥2 | 11.4 |
| B19 | 2 | n/n | n/n | ≥2 | 7.9 |
| B06 | 3 | n/n | n/n | ≥2 | 2.4 |
| B09 | 4 | n/n | n/n | ≥2 | 1.8 |

**8/8 briefs produce ≥2 genuinely distinct plans; 24 distinct plans in total.** Every accepted plan
clears the full bar: critic-clean before placement, realizes, every unchanged validator passes,
contacts n/n, doors n/n, **bands ≥ 2** (a row-collapsed plan is a FAIL, not a pass).

### Distinctness is measured on geometry, not on names

An early version offered four "alternatives" of which **three were byte-identical drawings** — same
contact graph, same plan, three concept names. That is precisely the fake diversity this work
exists to avoid. The partis were redesigned so their contact graphs genuinely differ, and
`BrainResult.distinct` now de-duplicates on the realized rectangles. Where two partis legitimately
converge (a brief with only two public rooms makes "chain off the hall" and "every public room
meets the hall" the same statement), only one is offered.

---

## 3. Production vs the brain — the honest comparison

| brief | area fidelity (prod → brain) | alternatives | **circulation aspect** | arrival |
|---|---|---|---|---|
| B08 | 98.2% → 89.2% | 2 → 2 | **9.00 → 1.32** | HALL → LIVING |
| B20 | 99.1% → 97.0% | 0 → **2** | **9.75 → 1.70** | HALL → LIVING |
| B02 | 62.6% → **70.0%** | 1 → 1 | **8.58 → 4.02** | HALL → HALL |
| B11 | 77.4% → **91.7%** | 1 → **2** | **11.46 → 1.49** | HALL → LIVING |
| B16 | 87.2% → **88.2%** | 0 → **2** | **11.92 → 2.67** | HALL → LIVING |
| B19 | 95.2% → **109.7%** | 1 → 1 | **7.85 → 3.08** | LIVING → LIVING |
| B06 | 56.9% → 53.1% | 2 → 2 | **10.35 → 1.44** | HALL → LIVING |
| B09 | 51.6% → 39.7% | 1 → **2** | **11.12 → 1.11** | HALL → LIVING |

### The headline win: circulation stops being a residue

Production's circulation is a **7.85 : 1 to 11.92 : 1** slot on every brief — the defect the
architecture report (#185/#186) named as the clearest evidence that these plans are packed rather
than designed. The brain's is **1.11 : 1 to 4.02 : 1**: a room, not a leftover. Visible in
`figures/B06__2-brain-PUBLIC_BAND.png` — a 5.40 × 4.10 m hall against production's 1.27 × 13.75 m
corridor.

Also: **zero rooms without a window** across all 8 briefs, and on B08/B20/B02 the brain takes the
wet rooms **off** the garden elevation where production put them there.

### The regression I am not hiding

**Arrival: production reaches a HALL on 7/8; the brain reaches one on 1/8.** The brain usually
arrives into the living room, which is an entrance-quality regression by production's own
`_entrance_rank`.

The cause is precise and is the same missing dimension E1 found: **`band_pipeline` has no way to
express "this room should front the street."** It orients a layout so that *some* entrance-eligible
room is in band 0, and both HALL and LIVING qualify. The brain cannot ask for the hall. Fixing it
means giving the embedder a placement preference — real work, not a tweak, and not attempted here.

### Area

Sizing rooms at their template targets delivered 78 m² against a 216 m² request. The brain now uses
**production's own `scale_program`**, which moved area fidelity from 39–70% to 53–110% and made the
brain **better than production on 4 of 8 briefs**. It is still short on B06 (53%) and B09 (40%) —
both briefs where the request exceeds the programme's own capacity, the condition #179 documented.

### Circulation share

The brain spends more area on circulation (up to 0.194 on B06 against production's 0.107). That is
the other side of the same trade: a 22 m² hall instead of a 17 m² slot. Whether a generous hall is
worth it is an architectural judgement, and 22 m² is arguably more than this brief needs — recorded
as an open question, not claimed as a win.

---

## 4. What is wired, and what is not

`?engine=brain` on both demo endpoints, through the **existing #181 preview seam**. The brain's
distinct plans become the plan set — primary plus alternatives — each carrying its parti name and
its preservation figures, all drawn by the real `DemoPlan`.

**No silent fallback:** a brief the brain cannot plan returns `BRAIN_NO_PLAN` with every parti's own
refusal reason, never the guillotine plan.

**Production is untouched.** No default moved, no flag flipped, no validator, access rule or
template bound changed. Without `?engine=brain` the demo path is exactly what it was.

---

## 5. Honest failures

Recorded per parti rather than hidden: `TWO_HALL` fails sizing on B11 and B16, `BEDROOM_WING` fails
sizing on B16, and `HALL_SPINE`/`TWO_HALL` fail selection on B19. Those briefs still deliver 2–3
distinct plans from the partis that did work.

---

## 6. What would make this production-ready

1. **An entrance preference in the embedder** — the arrival regression above. The single highest-value
   next step, and it also unlocks the garden/street orientation dimension E1 identified.
2. **Area on over-capacity briefs** (B06, B09) — the brain inherits production's own capacity
   ceiling; the honest fix is the disclosure #180 already ships, or more rooms.
3. **A circulation-share bound** so a hall cannot grow to 19% of the house.
4. **The LLM proposer as an additive source**, costed per request, once a key is authorised — it
   would add concepts the deterministic partis do not contain, on top of a system that already works
   without it.

**Method.** Every number is from executing code on this branch against the frozen briefs; all
figures are the real `DemoPlan` rendered in a browser with the product's own stylesheets. Data in
`data/`, renders in `figures/`.
