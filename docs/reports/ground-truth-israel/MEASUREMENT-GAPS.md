# Independent calculation — what could be recomputed, and what the attempt actually proved

**Issue:** #269 (ROOT #262, condition **C2**) · **2026-10-28** · sources: `SOURCE-VERIFICATION.md`
· references: `BOQ-EXTRACTION.md`

## Rules this attempt was run under

Taken from the directive and followed without exception:

1. **A printed figure is the only thing that may supply a length.** No value was scaled off any drawing. Pixel measurement was used once — to establish *which drawn faces a printed figure runs between* — and never to produce a number.
2. **No missing dimension was filled.** Where a datum, a height or a plan shape is absent, the calculation **abstains and says so**, and never substitutes a standard, a default or a plausible value.
3. **A disagreement between source documents is distinguished from a BuildSmart calculation error.** Where our own assumption could be the error, that possibility is named and the status is set to the weaker of the two readings.
4. **No threshold and no frozen reference was changed.** `frozen.py` was not opened, let alone edited. The ±2.0 % and the abstention band quoted below are #267's, cited for comparison only; nothing here re-freezes or revises them.
5. **Source quantities and computed quantities are kept in separate columns** and the computed ones are labelled `[computed]` wherever they appear.

## Choosing the smallest suitable group — and why it is B

The directive asks for the smallest suitable room group. Candidate **A** has the better drawing but
cannot host the attempt at all: its service group (`שירותים`) carries the densest dimension chains
in the whole corpus — `160 | 19 | 160` across, `180 | 19 | 160 | 19` across the lower pair, and
`94 | 30 | 30 | 94 | 61 | 118 | 28` down the left — **and its bill contains not one quantity for
those rooms.** The only figure touching them, `03.1.320`'s 7.20 m², is shared with the kitchenette
(`BOQ-EXTRACTION.md` A11). A geometry with no reference is not a comparison.

*A side observation on that chain, stated with its uncertainty:* the recurring `19` reads as a wall
thickness, which would make those walls 19 cm — a standard Israeli block, and **not** the 95–100 mm
gypsum the bill prices. A's bill contains **no masonry item of any kind**. The likeliest reading is
that the plan draws *existing* walls the bill never mentions because they are not being built,
which is more evidence for the different-scopes conclusion below. It is not offered as a finding.

Candidate **C**'s drawings are `UNVERIFIED`, so nothing can be computed from them at all.

So the attempt runs on **B — Nahariya 19/2026**: a single-storey volume, the one subject in this
Issue whose **wall height** and **every opening size** are figured on the same sheet.

## The attempt on B, in full

### Printed figures used — and nothing else

From the three elevations: widths **7.00** (north) and **13.30** (east and west); heights **3.00**
(low side) and **4.00** (high side); levels **+3.00** and **+4.45**; windows **1.00 × 0.60** (three,
west) and **0.30 × 0.60** (one, east); doors **1.10 × 2.10** (one figured, west).

### Three assumptions that had to be named before any number existed

- **A-1 — the plan is a rectangle.** There is **no floor plan and no south elevation**. 7.00 × 13.30 is two orthogonal elevation widths; the shape joining them is **not in the document**. Every figure below inherits this.
- **A-2 — the second door matches the first.** Two doors are drawn on the west elevation; **one** is figured 1.10 × 2.10. The second is taken as identical, which the drawing shows but does not state.
- **A-3 — the dimension pairs read width × height.** Consistent across every opening and never declared.

### The envelope — the one genuine result

| basis | computed | vs BOQ `19.030.0310` = **145.00 m²** |
|---|---|---|
| perimeter 40.60 m `[computed]` × mean of the **figured wall heights** 3.500 m, **gross** | **142.10 m²** `[computed]` | **−2.00 %** |
| the same, **net of 6.60 m² of openings** `[computed]` | **135.50 m²** `[computed]` | **−6.55 %** |
| perimeter × mean of the **level datums** (+3.00 / +4.45) 3.725 m, **gross** | **151.24 m²** `[computed]` | **+4.30 %** |
| the same, **net of openings** | **144.64 m²** `[computed]` | **−0.25 %** |

**Two conventions times two datums give four answers spanning 135.50 to 151.24 m², and the source's
145.00 sits inside that span.** Three of the four miss #267's ±2.0 % tolerance and the fourth —
parapet datum, net of openings — lands within **0.25 %**.

**There is no basis in any document for preferring that fourth reading.** Nothing states whether the
panel is measured to the fascia or to the eave, and nothing states whether openings are deducted. So
the 0.25 % is **not** a validation; it is one of four answers that happens to be close, and treating
it as the right one would be choosing the convention that flatters the result after seeing the
result. #267's closing sentence survives this test intact and is now evidenced on Israeli data:
**two numbers under two conventions are two answers, not an error bar.**

The datum ambiguity is not imported from anywhere — it is **on the sheet**. The high side carries a
figured wall height of **4.00** and a level of **+4.45** at the same place, a 0.45 m difference with
nothing to say which governs the painted or panelled face.

### The floor, the roof and the ceiling — and the honest refusal

| reference | computed footprint `[computed]` | difference |
|---|---|---|
| `02.050.0020` concrete slab **114.00 m²** | 93.10 m² | **−18.33 %** |
| `19.030.0108` roof panel **114.00 m²** | 93.10 m² | **−18.33 %** |
| `22.021.0155` acoustic ceiling **95.00 m²** | 93.10 m² | **−2.00 %** |

The roof was also computed as a *surface* rather than on plan, since it is mono-pitch: **95.08 m²**
using the level rise of 1.45 m, **94.05 m²** using the figured-height rise of 1.00 m `[computed]`.
Neither approaches 114.00. Inverting instead, 114.00 ÷ 13.30 implies a depth of **8.571 m**
`[computed]` against the figured 7.00 — **+22.45 % deeper than the drawing says the building is**.

It would be easy, and wrong, to call that a source contradiction. **Assumption A-1 may be the error
instead** — the plan may not be a rectangle, or the slab and roof may extend past the enclosed
envelope as an apron or canopy. Nothing in the pack excludes either, because the floor plan is not
published. The directive requires that a disagreement between sources be distinguished from our own
calculation error, so the status is **`INSUFFICIENT_DATA`**, and the 22.45 % is recorded as the size
of what the missing plan is hiding rather than as a defect of the source.

The ceiling deserves a separate note: at **95.00 m²** it **exceeds the computed gross external
footprint of 93.10 m²**, and an internal ceiling cannot be larger than the building's gross
footprint. That direction is the one a convention cannot explain. But at 2.00 % it is well inside
what assumption A-1 could absorb on its own, so it too is `INSUFFICIENT_DATA` and not a
contradiction — the finding being the *direction*, not the magnitude.

## Status of every candidate quantity

`COMPUTABLE` · `CONVENTION_DEPENDENT` · `INSUFFICIENT_DATA` · `SOURCE_CONTRADICTION`

### A — Nahariya 17/2026

| category | reference | status | what blocks it |
|---|---|---|---|
| flooring | `03.1.280` 120.00 m²; `03.1.310` 2.00 m² | **`INSUFFICIENT_DATA`** | the plan is figured and readable, but **no item names a room and no room names an item**. 2.00 m² is a patch whose location is nowhere given |
| wall plaster | — (no item) | **`INSUFFICIENT_DATA`** | plaster is measured only inside the tiling item A11 and has no extent of its own |
| wall painting | `03.1.260` 294.00 m² | **`SOURCE_CONTRADICTION`** | 151.00 m² of partitions are specified `מוכן לצביעה` and **no interior painting item exists**; the only paint is on **external** plaster. The bill does not account for painting the walls it builds |
| ceiling finishing | `03.1.270` 114.00 m² | **`CONVENTION_DEPENDENT`** | the plan is figured, so a ceiling area is in reach — but title-block note 3 fixes its dimensions as `ברוטו - ללא חיפוי גמר` while the item is trimmed with an `L` profile **`סביב הקירות`**, i.e. to the finished face. The same ceiling has two defensible areas, and the cladding thickness that separates them is given for the tiling and nowhere else |
| baseboard | — (no item) | **`INSUFFICIENT_DATA`** | zero skirting items in 18 pages |
| wall construction | `03.1.170` 151.00 m², 95–100 mm, net of openings | **`INSUFFICIENT_DATA`** | the convention is stated, the thickness is stated, **the height is not**. The four annotated soffits are structural, and the ceiling hangs up to 1.0 m beneath them |

### B — Nahariya 19/2026

| category | reference | status | what blocks it |
|---|---|---|---|
| flooring | — (no item) | **`INSUFFICIENT_DATA`** | no floor finish exists in the bill; the slab is not a finish |
| wall plaster | — (no item) | **`INSUFFICIENT_DATA`** | — |
| wall painting | `11.012.0182` 140.00 m² | **`INSUFFICIENT_DATA`** | the catalogue text reads `(פנים וחוץ)` — **interior and exterior** — against one figure. Which faces it covers is unstated, so there is nothing definite to compare to |
| ceiling finishing | `22.021.0155` 95.00 m² | **`INSUFFICIENT_DATA`** | no floor plan; and the computed footprint is **smaller** than the ceiling, a direction no convention explains |
| baseboard | — (no item) | **`INSUFFICIENT_DATA`** | — |
| **wall construction** | `19.030.0310` **145.00 m²** | **`CONVENTION_DEPENDENT`** | **the one quantity in this Issue that reached a comparison.** Four defensible answers, 135.50 to 151.24 m², from two opening conventions and two height datums — all three gaps are convention, not data, once A-1 is granted |
| (slab / roof) | `02.050.0020`, `19.030.0108` 114.00 m² | **`INSUFFICIENT_DATA`** | 22.45 % unexplained, attributable to the missing plan or to A-1, and the documents separate neither |

### C — Ramat Gan 03/2026

| category | reference | status | what blocks it |
|---|---|---|---|
| flooring | `01.10.031.0042` 753.00 m² + 88.00 + 246.00 + 15.00 | **`INSUFFICIENT_DATA`** | dedicated flooring plans `510`/`511` exist in the register and **could not be opened**. Also `0551` and `0552` carry byte-identical descriptions at 88.00 and 246.00, and nothing distinguishes them |
| wall plaster | `01.09.011.0010` 930.00 m² | **`INSUFFICIENT_DATA`** | drawings unverified; no height anywhere |
| wall painting | `01.11.011.0200` 1,535.00 m² | **`SOURCE_CONTRADICTION`** | two separate ones. **1,535.00 appears to the hundredth under both this item and the exterior render `01.11.012.0184`**, two items of different scope. And the bill specifies primer **+ two coats** where ג'2 11.03 specifies **three** — a material contradiction that lands on the purchase quantity, not the area |
| ceiling finishing | `01.09.011.0011` 205.00 m²; `01.11.011.0201` 186.00 m² | **`INSUFFICIENT_DATA`** | ceiling plans `410`/`411` unverified; 205.00 plastered against 186.00 painted, with no document explaining the 19 m² |
| **baseboard** | `01.10.031.0043` **386.00 m**; `01.10.031.0592` **107.00 m** | **`CONVENTION_DEPENDENT`** | the only skirting in the corpus, in running metres — but at `7,10 ס"מ`, **two heights in one item**, with **no statement of whether door openings were deducted**. That is #267's −23.94 % joiner-versus-plasterer question arriving unanswered. And `0592` cross-references item `10.031.0591`, **which does not appear in this bill** |
| wall construction | `01.04.010.0020/0030/0040` 50.00 / 20.00 / 360.00 m² at 10 / 15 / 20 cm | **`INSUFFICIENT_DATA`** | thickness stated for all three, **height for none**, drawings unverified |
| (reveals) | `01.09.021.0120` 381.00 m | **`SOURCE_CONTRADICTION`** | the bill measures reveals in **running metres as their own item**; ג'2 09.6(ד) of the same tender says `בניגוד לאמור במפרט הכללי ... לא ישולם בנפרד עבור הפשלים (גליפים) ושטחם יימדד לפי שטח במ"ר לפי סעיף הטיח` — **not paid separately, measured in m² under the plaster item**. Two documents of one tender, opposite rules, different units |

### The tally

| status | count |
|---|---|
| `COMPUTABLE` | **0** |
| `CONVENTION_DEPENDENT` | **3** — A ceiling, B wall construction, C baseboard |
| `INSUFFICIENT_DATA` | **13** |
| `SOURCE_CONTRADICTION` | **4** — A painting, C painting (×2 grounds), C reveals |

**Nothing is `COMPUTABLE`.** Not one quantity in three real Israeli tenders can be independently
recomputed and compared without first choosing a convention the documents do not fix, or supplying a
dimension they do not carry.

## What this attempt actually proved, and it is not what was expected

ROOT #262 recorded one structural fact in the experiment's favour: of the four materials, **three
need only plan-view geometry plus door widths**, so the third dimension is a dataset requirement
rather than an engine gap. **That fact is true and it was not the binding constraint here.**

- On **A** the plan-view geometry is *present* — figured, scaled, dated, authored, at 1:50 — and flooring and ceiling still could not be checked.
- On **B** the wall height is *present*, the thing nothing in this ROOT has ever had, and the floor and ceiling still could not be checked.
- On **C** the per-room finishes takeoff is *present*, skirting and all, and nothing could be checked.

Each failed for a different reason, and none of the three reasons was the missing height. **The
binding constraint on Israeli tender data is that no bill item is bound to a drawn room.** Not one
of the 24 extracted quantities cites a sheet, a grid reference or a room, and the one candidate that
attributes anything attributes it to room *types* behind which the register shows four separate
layouts. A takeoff is a per-room measurement **summed**, and a tender publishes the sum. The
addends — which are the comparison — stay in the quantity surveyor's working papers, which is
precisely what `AS-BUILT-ACQUISITION.md` §"What to ask for" item 2 asks for by name: the
`חישובי כמויות וסקיצות לכל סעיף`.

That reframes what a dataset must contain. It is not "plans plus quantities". It is **plans plus
quantities plus the mapping between them** — and the mapping is the artefact nobody publishes.

## Unverified in this document

1. **All three assumptions A-1, A-2 and A-3**, which every B figure inherits. A-1 in particular is load-bearing and unfalsifiable from the pack.
2. **Which of the four envelope readings the source intended.** Unknowable from the documents; the −0.25 % match is explicitly not claimed as a validation.
3. **The `0.30 × 0.60` east window.** The figures give a tall narrow opening; the box as drawn reads closer to square. This is #267's "the plate figures one thing and draughts another" on Israeli data, and it was **not** resolved — at 0.18 m² it cannot move the envelope result, which is the only reason it did not stop the attempt.
4. **The `19` in A's service-group chain** as a wall thickness (above).
5. **Whether `1,535.00` in C is a shared quantity or a transcription.** Recorded as an anomaly; no document explains it and this report does not guess.
6. **The national `אופני מדידה` chapters themselves.** The catalogue is verified and free; the chapter PDFs were not retrieved here (`BOQ-EXTRACTION.md`). So where a candidate is silent, what the default *says* is still unread — though ג'2 09.6(ד) proves a tender may override it in writing anyway.
