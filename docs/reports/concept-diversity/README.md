# Production Concept Diversity — where architectural intent becomes structurally trivial

**Question.** Why does Concept Engine v2 fail to produce a strong spatial concept before geometry
realization?

**Answer, in one line.** It never gets a second concept to choose from. The architectural knowledge
is right — the pattern prior asks for a **hub-lobby** organisation first on every audited brief —
but the only compiler that can build one **supports exactly two bedrooms**, so it refuses seven of
the eight briefs outright and the eighth for an uncombined safe-room case. With no hub and no
branched candidate, every candidate in the pool carries the same circulation class, and Concept
Engine v2 — which exists to return *one best plan per class, excluding the primary's own class* —
correctly returns **nothing**.

**No production code was changed.**

---

## 1. The forensic case

`figures/B06__concept-engine-v2.png` — generated through the new preview UI path, drawn by the
product's own `DemoPlan`.

A single rectangle, divided by one 1.30 × 13.45 m corridor into a public block on the left and a
bedroom strip on the right, with a 27.6 m² block labelled "unassigned". The owner's reading — room
packing inside a rectangle rather than a deliberate concept — is exactly what the measurements
below say the engine is structurally capable of producing.

**Concept Engine v2 returns the identical primary plan to production**, byte for byte on gross area,
with zero alternatives. The flag changes only how *alternatives* are chosen; it has no influence on
the concept of the winning plan at all.

| brief | production alternatives | Concept Engine v2 | primary gross area |
|---|---:|---:|---|
| B08 | 2 | **0** | 129.6 both |
| B06 | 2 | **0** | 177.4 both |
| B09 | 1 | **0** | 227.2 both |

## 2. The decision trace, stage by stage

| stage | what it could vary | what it actually produced |
|---|---|---|
| brief → outlines | 7 outlines offered: 1 person, 4 engine rectangles, **2 L massings** | only the person's outline is ever planned (below) |
| outline → adapter | wings available to build on | **1 wing**, every brief |
| adapter → `generate_concepts` | 7 strategies incl. `HUB_PRIVATE_WING`, `MULTI_WING_SPLIT` | 1–3 strategies, all mapping to one class |
| candidates → `ConceptSpec` | 6 circulation classes, 3 zoning splits | **SPINE** (7/8) or FRONT_BAND (1/8); **SIDE_BY_SIDE** (7/8) |
| candidates → topology | — | **1 topologically distinct candidate per brief**, out of up to 82 |
| → realization/validation | — | 1–4 plans, all one access graph |
| → `_select_plans` | family + massing de-duplication | works correctly; shows up to 3 plans of 3 families |
| → Concept Engine v2 | one plan per class | **0**, because there is only one class |

### Candidate stage, measured (`data/candidate_stage.json`)

| brief | wings | candidates | **topologically distinct** | circulation classes | zoning | massing | families |
|---|---:|---:|---:|---|---|---|---:|
| B08 | 1 | 30 | **1** | SPINE | SIDE_BY_SIDE | 1W | 3 |
| B20 | 1 | 12 | **1** | SPINE | SIDE_BY_SIDE | 1W | 1 |
| B02 | 1 | 10 | **1** | SPINE | SIDE_BY_SIDE | 1W | 1 |
| B11 | 1 | 74 | **1** | SPINE | SIDE_BY_SIDE | 1W | 7 |
| B16 | 1 | 0 | 0 | — | — | — | 0 |
| B19 | 1 | 8 | **1** | FRONT_BAND | FRONT_REAR | 1W | 2 |
| B06 | 1 | 82 | **1** | SPINE | SIDE_BY_SIDE | 1W | 6 |
| B09 | 1 | 56 | **1** | SPINE | SIDE_BY_SIDE | 1W | 6 |

**82 candidates, one concept.** This is the headline number of the investigation.

### Does `family` represent a real structural difference?
**No.** B11 produces 7 distinct families and B06 six, and in every brief `topologically_distinct`
— production's own test — collapses all of them to **one**. Family answers "which rooms share a
column or band". It is metadata over one topology, which is precisely why de-duplicating by it
produced alternatives the audit measured at access-graph distance 0.

## 3. Which architectural distinctions the engine can even represent

| distinction the output lacks | representable today? | evidence |
|---|---|---|
| central vs side circulation | **yes** — `CirculationClass` has SPINE, FRONT_BAND, HUB_LOBBY, BRANCHED, RING, TWO_WING | only 2 of 6 ever produced |
| public/private wings | **yes** — `ZoningSplit.SIDE_BY_SIDE / FRONT_REAR / WRAPPED` | WRAPPED never produced |
| L organization around outdoor space | **yes** — `MULTI_WING_SPLIT` strategy, `l_massings` outlines, `massing_signature` "2W" | 2 L outlines offered per brief, **0 two-wing plans** on all 8 |
| courtyard / patio | partly — `CirculationClass.RING` exists | its own docstring: "not produced by any builder today" |
| compact vs distributed wet core | **yes** — `WetCoreGrouping`, `wet_core_strategy` | single value per brief |
| entrance foyer as organizer | **declared only** — `EntranceSide` enum exists with **no field on `ConceptSpec`** | cannot vary; nothing carries it |
| bedroom wing / master placement | **declared only** — `MasterPlacement` enum, **no field on `ConceptSpec`** | its docstring: "not read by any generator today" |
| orientation to garden/exposure | not represented as a concept dimension | — |
| multiple building wings | representable, never produced | as above |

So the vocabulary is substantially richer than the output. Two of its dimensions are enums with no
field at all; two more have values no builder emits.

## 4. Where it collapses — two nested causes, the second decisive

### Cause A — the outline survey short-circuits (massing)
`_plan_outlines_until_one_plans`: *"The person's outline is authoritative: when they gave one and it
plans, the engine's outlines are not run at all."* Every audited project carries a selected
footprint, so on 6 of 8 briefs exactly **one** outline is ever planned. The two L massings offered
on every brief are never tried, which is why `massing_signature` is "1W" everywhere and the WRAPPED
zoning split never appears. The one escape hatch, `_better_engine_outline`, fires only when the
person's plan is SHORT and then offers a single outline chosen by **area proximity alone** — never
by concept.

### Cause B — the only non-spine compiler is hard-coded to one programme *(the decisive one)*
`concept_engine_v2.plans_per_class` is built correctly: it takes the pattern prior's ordered
classes, and for a class the generator did not produce it **compiles one**. Measured on all eight
briefs, the prior's first choice is **HUB_LOBBY** every time. And:

```
B08  hub unsupported -> compile_hub_lobby supports exactly 2 bedrooms, not 3
B02  ...                                                          not 1
B11  ...                                                          not 4
B16  ...                                                          not 5
B19  ...                                                          not 6
B06, B09 ...                                                      not 3
B20  hub unsupported -> 3-wet-room GUEST_WC row is not yet combined with a safe room
```

`compile_hub_lobby` returns 0 candidates on **8 of 8**. `compile_branched` returns 0 on 8 of 8.
So the pool holds exactly one circulation class, and `plans_per_class` — which deliberately
excludes the primary's own class so an alternative is genuinely different — has nothing left.

**The architecture knowledge is correct and the plumbing is correct. The generator simply cannot
build the organisation its own prior asks for.**

## 5. Why #142 achieves diversity, and what that teaches

#142 produced genuinely different alternatives on 6 of 8 briefs. The mechanism is not its embedder,
its realizer or its retention policy: it is that **diversity originates at the topology level,
before geometry**. An LLM proposes several *access graphs* for one brief, each is criticised, and
each is embedded and realized independently. Production does the opposite — it generates one
topology and then enumerates proportions and band assignments of it (82 candidates, one concept).

The transferable lesson is the ordering, not the LLM: **vary the access topology first and realize
each one**, rather than realize one topology many ways. Production already has the machinery to
exploit that (`topologically_distinct`, `plans_per_class`, the family/massing passes in
`_select_plans`, and now the preview UI's Concept 1..N). It lacks only the supply.

Importing #142 itself is still blocked by its measured regressions — 44–67% of programme capacity
against production's 56–114%, a hall arrival on 2 of 8 briefs against 7 of 8, and no open-plan
semantics at all.

## 6. Quality of the genuinely distinct alternatives
There are none to compare: on these eight briefs the engine produces **zero** structurally distinct
alternatives, so the quality comparison the brief asks for has no rows. That is itself the result.
The production winner remains the quality baseline and is unchallenged.

## 7. The earliest decision that prevents genuine concept diversity

> **`compile_hub_lobby`'s programme precondition.** It is the only builder that can produce a
> second circulation class for a given outline, and it accepts exactly two bedrooms. Every
> downstream stage is already built to exploit a second class and does nothing because none
> arrives.

Cause A (the outline short-circuit) is *earlier in the pipeline* but weaker: fixing it alone would
plant the same single topology on more footprints. Cause B is where architectural intent actually
becomes trivial.

## 8. Smallest change that attacks the cause — recommended, not implemented

> **Generalise `compile_hub_lobby` from "exactly 2 bedrooms" to the brief's actual programme**, so
> the hub organisation the pattern prior already asks for can be built for a real brief.

Why this and nothing larger: the prior already names HUB_LOBBY first; `plans_per_class` already
calls the compiler for a missing class; `topologically_distinct` already counts a different class
as a different concept; `_select_plans` already shows a different family or massing before any
repeat; and the preview UI already exposes whatever comes back as Concept 1 / Concept 2. Every
other part of the chain is waiting for one supply. Nothing needs a new template, a new score, a new
validator or a random perturbation.

**Risks and regressions to measure before adopting it**
- a hub plan may deliver less area or fail validators on larger programmes — `hub_guard` exists for
  exactly this and would need re-measuring rather than trusting;
- `compile_hub_lobby` is hand-authored; generalising it is real work and could regress the
  two-bedroom case it currently serves;
- a second class raises per-brief realization cost (bounded by `CONCEPT_ENGINE_V2_MAX_REALIZATIONS`);
- it does **not** address massing: L and courtyard organisations stay unreachable until Cause A is
  also addressed. That is a separate, later decision.

## 9. Scope

No production code changed. No L-shape template added, no random room movement, no validator or
scoring change, #142 not wired, no diversity manufactured after realization. Probes are harness-only
in `backend/app/ai_harness/diversity_probe/`.

**Artefacts.** `figures/` (production vs Concept Engine v2 for B08/B06/B09 through the product
renderer) · `data/candidate_stage.json` · `data/selection_funnel.json`.
