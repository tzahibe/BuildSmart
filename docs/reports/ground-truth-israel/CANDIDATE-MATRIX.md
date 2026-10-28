# Candidate matrix — L0 to L3, and why none of the three reaches L3

**Issue:** #269 (ROOT #262, condition **C2**) · verified **2026-10-28**
Sources: `SOURCE-VERIFICATION.md` · quantities: `BOQ-EXTRACTION.md`

## The ladder, stated before it is applied

#263's and #267's reports live on branches not merged to `main` (PRs #264 and #268), so the ladder
is restated here rather than cited into a file that does not exist in this tree. The directive
fixes its middle rung explicitly — *"the expected finding is **L1** — a drawing plus a professional
tender BOQ — which is genuinely valuable for research and explicitly does not pass C2"* — and the
rest follows from it:

| rung | what it means | may it support an accuracy claim? |
|---|---|---|
| **L0** | a drawing with no professional quantities, or quantities with no drawing | no |
| **L1** | a drawing **plus a professional bill of quantities** prepared for tender — a **design estimate** | **no.** A professional estimate is not a measurement of anything built |
| **L2** | L1 **plus a final or approved quantity account measured against the work as executed** — a `חשבון סופי` with its `ספר מדידות` and `AS-MADE` | partially: it is a measurement of a building, taken by a party with a financial interest in it |
| **L3** | L2 **plus independent field verification of the physical structure**, with the method stated and an accuracy bound | **yes — and only this** |

**Only L3 may be proposed for C2.** The separation between L1 and L2 is not pedantry: it is the
exact distance between *what a professional expected to build* and *what was measured after
building it*, and ROOT #262's governing principle — a mathematically correct calculation is not
evidence that its input measurements are correct — lives entirely inside that gap.

## The classification

| | **A — Nahariya 17/2026** | **B — Nahariya 19/2026** | **C — Ramat Gan 03/2026** |
|---|---|---|---|
| project | office refurbishment | commercial refurbishment | **new-build** kindergartens / day-care |
| **classification** | **L1** | **L0** | **L1 (contingent)** |
| why that rung | a figured 1:50 plan **and** a professional 18-page Benarit bill, both in hand | the bill is professional, but the "drawing" is three elevations with no plan — and **the tender was cancelled** | the richest professional bill of the three, but **the drawings could not be opened**, so the pairing is asserted and not held |

### Against the criteria the Issue names

| criterion | A | B | C |
|---|---|---|---|
| **dimensional completeness** | **good for one storey, one sheet.** Figured chains throughout at 1:50; overall 1623 cm; chains close partially — several terminate without declaring which wall face they run to | **two widths and nothing else.** 7.00 and 13.30 from two orthogonal elevations; **no plan**, no south elevation, so the footprint shape is an inference | **register promises the best set of the three** — plan 1:50, flooring plans 510/511, ceiling plans 410/411, sections 200/201, finishes schedule — **and none of it was read** |
| **wall height** | **absent as a wall height.** Four *soffit* levels annotated (H=240/260/275/290) — but the acoustic ceiling hangs `בגובה עד 1.0 מ'` below the soffit, so the finished height is unknown, and the soffit is not the painting datum either | **present on the drawing** — 3.00 m eaves and 4.00 m high side, with levels +3.00 and +4.45. The one candidate that figures a wall height at all | **absent.** The register lists two sections (`200`, `201`) at 1:50 which would carry it; they were not read. The bills state block thickness (10/15/20 cm) and no height |
| **door and window schedule** | **doors partial, windows absent.** Door sizes are tagged on the plan (`נג 70/205`, `נג 80/205`); windows appear only as a BOQ price band `בשטח של מעל 2 מ"ר ועד 3 מ"ר` | **both present as drawing figures, no schedule document.** Windows 1.00×0.60 (×3) and 0.30×0.60; doors 1.10×2.10 | **a real schedule, by reference, in the bill itself.** Items `01.12.001.*` give size **and** mark and count: `A1` 440/190 ×8, `A2` 120/260 ×6, `A3` 125/190 ×8, `A4` 330/260 ×1, `A7` 80/90 ×1 and 60/180 ×2, `A8` 220/260 ×1, `A10` 220/260 ×1, `A11` ממ"ד 100/100, `AP3` 150/140 ×1. **But which number is the width is nowhere declared** — width-then-height is consistent across the items and is therefore an *inference*, not a stated fact. Internal joinery is in `LST NAG`, unread |
| **material specification** | **good.** Named products with substrates, thicknesses and coverages — Rockfon Pacific A αw 0.70 at 12–15 mm, CPS parquet 4 mm class CA6, Supercryl at 11–12 m²/litre, gypsum 95–100 mm | **adequate and generic.** Dekel catalogue wording: 50 mm panel, PU 40 kg/m³, render 2.4–3.3 kg/m² per coat | **the best of the three**, and it contains the one genuine **material contradiction**: the bill says Supercryl primer **+ two coats**, ג'2 11.03 says **three coats** |
| **drawing-to-BOQ consistency** | **unassessable — and that is the finding.** No item cites the sheet; the sheet tags no item. The BOQ's scope is patches (2.00 m² of flooring) while the sheet draws whole rooms. The two documents are about **different things** | **unassessable, and arithmetically strained.** One single-storey building carries a 114.00 m² slab, a 114.00 m² roof and a 95.00 m² ceiling, against a 7.00 × 13.30 footprint | **assertable but not demonstrated.** ג'2 and the bill contradict each other on reveals (metres vs m²) — so the pack is not even internally consistent where both halves *are* readable |
| **independently recomputable?** | **no.** The bill measures alterations; the drawing describes rooms. There is no quantity whose extent the drawing defines | **no.** No floor plan exists, so no area can be computed without assuming the plan shape | **no, today** — because the drawings are unverified. **It is the only candidate that would become recomputable** if the sheets were obtained: flooring plans, ceiling plans and room-typed cladding all exist |
| **field verification exists?** | **no — but the contractual route is written into this very tender.** §61.2 requires the actual quantities to be fixed by measurements by supervisor and contractor recorded in a **`ספר המדידות`** signed by both; §23.6 appoints a **control surveyor at 1 % of contract value** if measurement differences are material; the final-account appendix requires **`AS-MADE` signed by the contractor, the supervisor and a licensed surveyor (`מודד מוסמך`)**. **None of those documents is published** | **no, and no route.** The tender was cancelled, so nothing was built and nothing will be measured | **no, and the contract forbids it ever existing.** §16: `ולא תבוצע מדידת כמויות`. §56(ג): `מתכונת ההתקשרות ... "פאושלית" ללא מדידת כמויות`. The building quantities will **never** be measured. Only the external works (מבנה 02/03) are let `בשיטת מדידה` |
| **private research use?** | reading a published page is not restricted; **reuse of the drawing is** — title-block note 5 reserves it to the designer absent written permission | same restriction on the booklet; the JPEG carries no notice of its own | `המסמכים הינם רכוש החברה וחל איסור מוחלט לעשות בהם שימוש אחר פרט להשתתפות במכרז` — **an absolute prohibition on any use other than bidding** |
| **storage / redistribution?** | **not permitted.** Linked, described, cited — never copied into this repository | **not permitted** | **not permitted**, and the site footer repeats it: `אין להעתיק ו/או לשכפל ו/או לצלם` |

### Same physical scope, measurements and revisions?

Only L3 may be proposed for C2, and only after confirming that measurements, quantities and drawing
revisions correspond to the same physical scope. **None of the three survives that test**, and each
fails it differently:

- **A** — one sheet stamped `לביצוע` 12.03.2026 against a bill generated 24/03/2026, with **no revision table, no revision cloud and no drawing register anywhere**. The negative is all that can be said: no superseding sheet is published.
- **B** — a bill dated 26/04/2026, a tender published 27/05/2026, a plan JPEG with **no date of any kind**, and a cancellation on 09/06/2026 citing *material changes in scope*. The scope the documents describe is, on the publisher's own account, not the scope that was wanted.
- **C** — a bill revised 25/05/2026 against a drawing set unrevised since 21/04/2026. Clarification 5 asserts `יישארו כל יתר הוראות המכרז ... ללא שינוי`, which is the publisher's assertion and not a demonstration, and the **superseded 158-page bill is still published beside the new one with no warning**.

## Ranking, and what each candidate is actually good for

1. **A — Nahariya 17/2026 — the best evidence in hand.** The only candidate where a figured, scaled, dated, authored drawing and a professional priced bill are *both* openly downloadable and both readable. It is also the one that supplied the three conventions this project most needed to find in the wild (`SOURCE-VERIFICATION.md` §1.2). Its ceiling is that the bill and the drawing describe different scopes.
2. **C — Ramat Gan 03/2026 — the best evidence that exists.** The richest bill by a wide margin: plaster split wall-from-ceiling, skirting as its own linear item, cladding attributed to room types, masonry by thickness, an opening schedule by mark, and a 308-page special specification that **states its own measurement conventions and overrides the national one in writing**. Two things keep it below A: the drawings are **UNVERIFIED**, and the contract has abolished measurement, so it can never rise above L1.
3. **B — Nahariya 19/2026 — L0, and still worth keeping.** Cancelled, no floor plan, no flooring, plaster or skirting items. Its one value is real: it is the **only** candidate in this Issue that figures a **wall height** and **every opening size** on the same sheet, which makes it the only usable subject for the independent-calculation attempt in `MEASUREMENT-GAPS.md`.

## The ceiling, stated plainly

**No candidate is proposed for C2, and none can be.** A is L1, C is L1 contingent on drawings
nobody here could open, B is L0. The gap between L1 and L2 is not a document that was overlooked —
it is a document that **the publishers do not publish** (A, where the contract requires it to exist)
or that **the contract has abolished** (C, where it never will). Reaching L1 on two real Israeli
projects is a genuine research result and it is the result the directive predicted. It does not pass
C2.
