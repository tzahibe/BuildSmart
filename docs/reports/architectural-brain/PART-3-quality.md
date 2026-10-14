# Part 3 — the entrance, the area, and what the renders actually show

Issue #197, second iteration. Part 1 and 2 are in `README.md`; **three of their headline claims are
corrected here**, and the corrections came from looking at the twelve renders as drawings rather
than at the numbers underneath them.

Reproduce: `PYTHONPATH=backend python -m app.ai_harness.brain_eval.compare <out.json>` for the
eight tuned briefs, `… .unseen <out.json>` for five the brain has never been tuned on.

---

## 1. What the render audit found

| claim in Part 2 | what the renders show |
|---|---|
| circulation aspect **7.85–11.92 : 1 → 1.11–4.02 : 1** | true, and bought with a **landlocked** hall: **21 of the 22 plans the demo surfaced** had circulation in an interior band, and in the large briefs it was **~1.7× bigger in absolute area** than production's. A 29.6 m² windowless box is not a better hall than a thin corridor. |
| **zero rooms without a window** | the metric filtered to public + private rooms. HALL and CIRCULATION have window policy **NONE in production by design** (`windows.py`), so this was never a defect — but it was also never the clean sweep the sentence implies, and five plans had a windowless wet room. |
| **area fidelity 53–110%** | the 53% end is two briefs whose room list cannot fill the footprint at any size, and the figure was **net reported as gross**. |

The worst drawings, named: **B09 `BEDROOM_WING`** (34.7% of a 440 m² brief; a 1.40 × 4.90 m WC with
a fixture at each end; a master bedroom smaller than the corridor), **B16 `SERVICE_CORE`** (the
kitchen in the bedroom band; a 1.15 × 4.00 m WC), **B16 `PUBLIC_BAND`** (a 10.0 × 3.0 m hall — the
defect Part 2 claimed to have fixed).

---

## 2. The entrance regression and the landlocked hall were **one defect**

Across the **22 plans the demo surfaced** from Part 2 (the engine produced 24 distinct; the demo
shows 3 per brief — the two populations are kept apart throughout this document):

| hall exterior faces | plans | arrival room |
|---|---:|---|
| 0 (landlocked) | **21** | LIVING — every one |
| 2 | **1** | **HALL** |

A perfect 1:1, and the mechanism is structural rather than a missing preference. The hall is a
**hub** — it touches every bedroom, every shared wet room and a public room. In a band layout a hub
must sit in a middle band to reach the bands above and below it, and a middle band has no exterior
wall. `ENTRANCE_ZONE_PRIORITY` already ranks HALL above LIVING, so nothing in the entrance policy
needed changing: **the hall simply had no wall to put a door in.**

### The fix: a degree-2 entry foyer

`ENTRY` is a separate room of degree 2 — street and hall. Degree 2 is the whole point: it places
trivially in the street band. It is `CIRCULATION`, not `HALL`, so a hall that *does* reach the
street still wins the door; and its ceiling is 9 m² so it cannot grow into the second hall that
would recreate the problem. Below 85 m² net the brief cannot spare one and is offered the plain
parti instead, which arrives in a public room — honest for a small house.

Each parti is now offered **with and without** a foyer. They are different contact graphs and
different buildings, not a tweak.

### Measured

| | Part 2 | now |
|---|---:|---:|
| **briefs with ≥1 plan arriving at circulation** | **1 / 8** | **8 / 8** |
| distinct plans the brain produces, 8 briefs | 24 | **46** |
| of those, arriving at circulation | *(1 of the 22 the demo surfaced)* | **25 / 46** |
| plans the DEMO shows | 3 per brief | 3 per brief (`_SHOWN_LIMIT`, the product's own cap) |

The brief-level row is the apples-to-apples one: Part 2 was measured over the plans the demo
surfaced, this over every distinct plan the engine produces.

The 46 is what the engine produces; the demo payload carries a primary plus two alternatives, which
is the product's existing limit and was not changed here. Raising it is a product decision, not an
engine one.

`figures-after/B09__1-brain-HALL_SPINE+FOYER.png` — street → **8.9 m² foyer** → hall → rooms, where
Part 2's B09 opened straight into the living room.

---

## 3. Area: two unrelated problems wearing one number

**Every one of the eight briefs has a footprint exactly equal to its requested built area.** There
is no geometry problem. What differs is whether the *room list* can fill it, measured with
production's own `program_capacity_gross_m2(hard=True)` — the canonical formula, not a second
opinion about it:

| brief | requested | the programme's own capacity | can it fill? |
|---|---:|---:|---|
| B20 | 132 | 269 | yes (204%) |
| B08 | 132 | 250 | yes (189%) |
| B19 | 181 | 330 | yes (182%) |
| B16 | 216 | 337 | yes (156%) |
| B11 | 216 | 309 | yes (143%) |
| B02 | 216 | 218 | just (101%) |
| **B06** | 312 | 243 | **78%** |
| **B09** | 440 | 250 | **57%** |

**B09 asks for a 440 m² house from a room list that tops out at 250 m².** No layout of that
programme reaches it — production delivers 51.6% and the brain 40%, and neither is wrong. The brief
does not add up.

**Production already knew this and already says so.** `capacity_notice_text` has been attached to
every design, brain ones included, telling the customer in Hebrew that their programme fills about
N m² against a target of M. My first report should have found that before calling the shortfall a
brain defect. What the brain adds is not the disclosure but two things the notice does not do: it
**gates** on the number instead of only printing it, and it tells "the brief does not add up" apart
from "the layout fell short", which the notice cannot.

**Production still beats the brain on B09** and the reason is honest: production's FLEX room is
elastic to 54.3 m², while the brain sizes FLEX against its template maximum like any other room.
Closing that would mean letting one room grow without bound, which is how the 29.6 m² hall
happened. Left open deliberately.

### `AreaVerdict` — typed, with the numbers in it

| code | meaning | delivered? | claimed as meeting the brief? |
|---|---|---|---|
| `WITHIN_TOLERANCE` | within **10%** of the request | yes | **yes** |
| `BELOW_TARGET_DISCLOSED` | 10–50% short, programme could have reached it | yes, **with the shortfall in writing** | no |
| `PROGRAMME_UNDERFILLS_FOOTPRINT` | the room list cannot reach the area at any size | yes, **with that explained and the numbers given** | no |
| `AREA_TOLERANCE_EXCEEDED` | more than 50% short, or over by >10% | **no** | — |

**Why two thresholds and why the second is loose.** Production lands at 98.2 / 99.1 / 62.6 / 77.4 /
87.2 / 95.2 / 56.9 / 51.6 percent on these briefs. A single 10% bar rejects the shipping product on
four of eight, and setting it at 20% — enough to pass the brain and fail production — would be the
same dishonesty pointed the other way. So 10% is what may be **claimed** and 50% is a floor on what
may be **drawn**; between them the plan ships with the number stated. The bar on `BrainPlan.counts`
went **up**, not down: a plan with an unacceptable verdict no longer counts.

### Gross and net are now separate everywhere

Part 2 quoted one and labelled it the other. `GeometricDesign` computes both; net runs 7–9 points
below gross on these briefs, and both are reported.

### FLEX

Production puts the area a named room list cannot absorb into a **FLEX** room — 54.3 m² on B09,
27.6 on B06, 14.3 on B02, exactly the three underfilled briefs. The brain was dropping FLEX on the
floor. It is now a spare room off the circulation, and B09 went from 3 distinct plans to 9, B02
from 0 to 4.

---

## 4. Results, eight tuned briefs

| | production | brain, Part 2 | brain, now |
|---|---|---|---|
| briefs planning | 8/8 | 8/8 | **8/8** |
| distinct plans produced | — | 24 | **46** (3 shown per brief) |
| arrive at circulation | 7/8 | **1/22 plans** | **25/46 plans, 8/8 briefs** |
| within 10% of requested area | 4/8 | — | **4/8 briefs, every plan on them** |
| area shortfall explained, never claimed | no | no | **yes, typed** |
| cost per request | $0 | $0 | **$0** |
| latency, per brief | 0.4–0.6 s | 0.5–11.4 s | **0.9–23.5 s** |

Area by brief (gross, against the brief's own requested figure):

| brief | production | brain now | verdict |
|---|---:|---:|---|
| B08 | 98.2% | 96–99% | `WITHIN_TOLERANCE` |
| B20 | 99.1% | 97–103% | `WITHIN_TOLERANCE` |
| B16 | 87.2% | **92–104%** | `WITHIN_TOLERANCE` |
| B19 | 95.2% | 95–106% | `WITHIN_TOLERANCE` |
| B11 | 77.4% | **89–91%** | mostly `BELOW_TARGET_DISCLOSED` |
| B02 | 62.6% | **70%** | `BELOW_TARGET_DISCLOSED` |
| B06 | 56.9% | 53–57% | `PROGRAMME_UNDERFILLS_FOOTPRINT` |
| B09 | 51.6% | 38–42% | `PROGRAMME_UNDERFILLS_FOOTPRINT` |

Also, unreported in Part 2 and a genuine advantage: **kitchen↔living door — production 0/8, brain
11/23.** Production never connects the kitchen directly to a living space on these briefs.

---

## 5. Five briefs the brain has never been tuned on

Written after every decision above, chosen to attack what has failed before.

| brief | footprint | production | brain | arrival |
|---|---|---:|---:|---|
| U1 — long and thin | 8 × 20 | 100.0% | **110.0%** | CIRCULATION |
| U2 — compact, tight | 10 × 10.4 | 99.0% | 94.7% | CIRCULATION |
| U3 — six bedrooms | 14 × 17 | 77.9% | **90.6%** | LIVING |
| U4 — wide and shallow | 22 × 8.5 | **refused** | **refused** | — |
| U5 — small, below the foyer threshold | 8 × 9 | 97.5% | 102.9% | HALL |

U4 is refused by **both** paths and that is the right answer: no outline survives the room-shape
constraints at 22 × 8.5 m. U5 shows the foyer threshold working — too small for one, and it still
arrives at the hall.

---

## 6. Limitations and residual risks — stated, not buried

1. **Circulation is the elastic filler, and that is unresolved.** The band grid tiles the footprint
   exactly, so whatever the rooms' own maxima do not absorb lands in the hall. Capping the hall at
   20 m² took B16 from three plans to one, every loss a `SIZING_INFEASIBLE`; the pipeline now asks
   for the better-proportioned house first and **widens the hall rather than refuse**. Production's
   14 m long corridor and the brain's 26 m² box are the same mechanism, not two different defects.
2. **A new bad plan, caused by this iteration's own preference.** `figures-after/B16__1-brain-PUBLIC_BAND+FOYER.png`
   is `WITHIN_TOLERANCE` at 91.9% and architecturally poor: a **12.50 × 1.60 m hall** (7.8:1 — the
   defect Part 2 claimed to have fixed) and bedrooms mixed into the public band. Ranking area above
   circulation shape bought the square metres and paid in proportion. Named here rather than left
   for the next audit to find.
3. **Latency up to 23.5 s** on the largest briefs, from 11.4 s. Ten proposals instead of five, and a
   preference that can no longer stop at the first accepted candidate. Not acceptable for a live
   request path; the plans are independent and nothing has been parallelised yet.
4. **Wet-room proportions improved but are not fixed.** 1.40 × 4.90 m is gone; 1.25 × 3.90 m is
   still there. The preference ranks it last, so it only ever breaks ties.
5. **Small-room label overflow** in every render — dimension text printed outside the room onto
   neighbours and fixtures. Cosmetic, and the first thing a customer sees.
6. **The foyer costs area.** 3.5–9 m² of circulation that a brief under 85 m² net cannot spare,
   which is why the threshold exists and why both variants are always offered.

## 7. What is unchanged

No validator, access rule, room bound, exposure policy or entrance policy was modified. The
production path is byte-unchanged and the brain remains behind a default-off `?engine=brain` flag.
`prefer` is additive: a caller that does not pass it gets the pipeline's previous behaviour exactly.
Zero model calls, no API key, no network — asserted by a test that makes `urlopen` raise.
