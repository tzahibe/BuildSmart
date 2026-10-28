# BOQ extraction — the six quantity categories, as the source states them

**Issue:** #269 (ROOT #262, condition **C2**) · verified **2026-10-28** · sources verified in
`SOURCE-VERIFICATION.md`

## The rule this document is built on

Every number below is **a quantity a source document states**. Nothing here is computed, scaled,
converted, inferred or reconciled. Where a field is absent the cell says **`—` (absent)** and the
reason; it is never filled from a sibling document, from a drawing, from a national standard or
from a plausible value.

**No BuildSmart-computed figure appears in this document at all.** Independent computation and its
comparison against these references live in `MEASUREMENT-GAPS.md`, which keeps the two columns
apart by construction. That separation is the point: #267's R2 cleared for the first time in this
ROOT only when the circularity was removed, and a reference that has been "tidied" against a
calculation is a circular reference again.

**Nothing is reproduced.** No table, plate or page from any source is copied here; items are cited
by publisher, document, page and item number so a reader can open the original at the links in
`SOURCE-VERIFICATION.md`. All three sources prohibit redistribution.

### Units as the documents write them

`מ"ר` = m² · `מ'` / `מ"א` = linear metre · `יח'` = unit · `קומפ'` / `קומפלט` = lump item ·
`טון` = tonne. Prices are ₪ excluding VAT and are recorded only as authorship/provenance evidence.

---

## A. Nahariya 17/2026 — office refurbishment

**Document:** `כתב כמויות`, `/uploads/n/1774357543.5360.pdf`, 18 pp, generated **24/03/2026
13:02**.
**Authorship evidence:** header on every page `עיריית נהריה - אגף טכני - ניהול פרויקטים` with the
department telephone and fax; footer on every page `בנארית בענן (04.24.0)` — **Benarit**, a
standard Israeli quantity-surveying package — software user `4372.eliranas`. The engineer's **unit
prices and totals are published**, so this is the client's priced estimate, not a blank bidding
schedule. **No quantity surveyor is named anywhere.**
**Drawing reference:** the pack contains exactly one architectural sheet — SHIR & STAV `א-1`, A3,
**1:50**, `לביצוע` **12.03.2026**. **No BOQ item cites a drawing, a sheet or a room.**
**Contract status of these numbers, in the tender's own words** (booklet §61.1):
`הכמויות הנקובות בכתב הכמויות הן אומדן בלבד של הכמויות הדרושות לביצוע העבודות ואין לראותן ככמויות
הסופיות שעל הקבלן לבצען בפועל` — *an estimate only, not to be regarded as the final quantities.*

| # | item | page | quantity | unit | room / area | material specification as stated | measurement convention | ambiguity or contradiction |
|---|---|---|---|---|---|---|---|---|
| A1 | `03.1.170` מחיצות גבס חד-קרומיות (בשני הצדדים) | 3 | **151.00** | מ"ר | `—` (absent) | total thickness **95–100 mm**; galvanised steel top and bottom track and studs; `עד גמר מושלם, מוכן לצביעה` | **stated in the item**: `המדידה נטו - ללא פתחים` (net, openings excluded); stiffening to openings and acoustic insulation measured separately | **no height**. A partition area in m² with openings excluded cannot be checked without the height the sheet does not figure for partitions |
| A2 | `03.1.190` תוספת עבור בידוד אקוסטי | 3 | **151.00** | מ"ר | `—` | 2″ glass wool wrapped in FLAB, 24 kg/m³ | follows A1 by cross-reference | consistent with A1 by construction, so it is not an independent check on A1 |
| A3 | `03.1.180` תוספת ללוח דוחה מים וחסין אש | 3 | **92.80** | מ"ר | `—` | water-repellent + fire-resistant board in place of standard, **one side** | `—` (absent) | 92.80 of 151.00 is a partial, unlocated subset — nothing says which partitions |
| A4 | `03.1.200` חיפוי עמודים מרובעים בלוח גבס | 3 | **16.60** | מ"ר | `—` (columns, unlocated) | 12.5 mm board, plaster-adhesive fixed, no frame, no insulation | `—` | columns are drawn on the sheet but not tagged; no mapping is possible |
| A5 | `03.1.210` חיפוי קירות בלוח גבס | 3 | **10.40** | מ"ר | **`(ירוק - מטבח)`** — green board, kitchen | 12.5 mm board, adhesive fixed | `—` | the only room attribution in the entire chapter, and it is parenthetical |
| A6 | `03.1.260` צבע "סופרקריל מ.ד" או ש"ע | 4 | **294.00** | מ"ר | `—` | **`על טיח חוץ`** — on **external** plaster; coverage `11–12 מ"ר/ליטר`; primer `יסוד קושר` + two coats | `—` (absent) | **the contradiction of this BOQ.** 151.00 m² of partitions are specified `מוכן לצביעה` — *ready for painting* — and **no interior painting item exists**. The only paint item is on external plaster |
| A7 | `03.1.270` תקרה אקוסטית מאריחים מינרליים | 4 | **114.00** | מ"ר | `—` | Rockfon "Pacific A" or eq., αw = 0.70, tiles 60/60, 16/16, 16/122 cm, **12–15 mm** thick; base price ₪75/m² | price includes carrying and secondary profiles, **hangers `בגובה עד 1.0 מ'`**, and **`פרופילי גמר ''L'' מאלומיניום סביב הקירות`** — an L trim **around the walls**, i.e. measured to the wall face | the hanger depth makes the **finished ceiling height unknown**: the sheet figures the concrete soffit, the ceiling hangs up to 1.0 m below it, and no item states by how much |
| A8 | `03.1.280` רצפת פרקט פולימרי CPS | 4 | **120.00** | מ"ר | `—` | "Pluto" or eq., **4 mm**, abrasion class CA6, wood-effect; floating, base price ₪125/m² | `ע"ג משטח מיושר וקשיח (הנמדד בנפרד)` — the levelled substrate is measured separately | 120.00 m² of floor against 114.00 m² of ceiling and 294.00 m² of paint: three different extents, none of them located |
| A9 | `03.1.300` פירוק ריצוף קיים | 4 | **2.00** | מ"ר | `—` | removal of existing flooring | `—` | **two square metres.** This is a patch, not a floor |
| A10 | `03.1.310` ריצוף באריחי גרניט פורצלן/קרמיקה | 4 | **2.00** | מ"ר | `—` | 33/33 or 60/60 cm, base price ₪60/m² | `—` | matches A9 exactly; both are repair of a local area |
| A11 | `03.1.320` חיפוי קירות באריחי קרמיקה | 4 | **7.20** | מ"ר | **`(במטבחון + שירותים)`** | any size, architect's choice, base ₪60/m²; adhesive onto masonry/gypsum **including a levelling cement render on masonry walls**; 3 mm joints, acrylic grout | the levelling render is **inside** this item and is not measured separately | **two rooms in one figure.** The kitchenette and the toilets are different rooms on the sheet; 7.20 m² cannot be attributed to either |
| A12 | `03.1.340` יציקת מדה מתפלסת | 4 | **10.00** | מ"ר | `—` | self-levelling screed, **up to 3 cm**, under carpet/PVC/parquet | `במידת הצורך יאושר ע"י מפקח` — **on the supervisor's approval if needed** | a contingent quantity: it may be built in full, in part or not at all |
| A13 | `03.1.120` פירוק פנלים מבודדים מקיר קיים | 2 | **85.00** | מ"ר | `—` | insulated panels, no steel frame | the price band is stated as `בשטח עד 250 מ"ר, בגובה עד 3.5 מ` — **a height *band*, used to price the work, not a measured height** | the only height-shaped figure in the whole bill, and it bounds a price bracket rather than measuring anything |

**Baseboard / skirting in this BOQ: `—` absent. Zero items.** Searched the full 18-page text for
`שיפול`, `פנל רצפה` and every variant: the only `פנל` hits are `פנלים מבודדים`, insulated sandwich
panels (A13), an unrelated element.
**Wall plaster: `—` absent as a measured item.** Plaster appears only *inside* A11, as a levelling
render beneath tiling.
**Wall construction: `—` absent.** No block, brick or concrete walling item exists; the only new
walls are the gypsum partitions of A1, whose **thickness is stated (95–100 mm) and whose height is
not**.

---

## B. Nahariya 19/2026 — commercial refurbishment · **the tender was cancelled 09/06/2026**

**Document:** `כתב כמויות`, `/uploads/n/1779885305.7523.pdf`, 6 pp.
**Authorship evidence:** footer on every page `הופק ע"י "תוכנת דקל" - חיפה · www.dekel.co.il ·
מספר פנימי 37858 · מספר ייחודי 1545615`, body dated **26/04/2026** — **Dekel**, the other standard
Israeli package. Every item number is a **Dekel catalogue code**, so the descriptions and their
embedded conventions are the catalogue's standard wording and not this project's. **No author in
the file metadata and no quantity surveyor named.**
**Drawing reference:** one JPEG of **three elevations**, with no title block, no scale, no date and
no author. **No BOQ item cites it.**

| # | item | page | quantity | unit | room / area | material specification as stated | measurement convention | ambiguity or contradiction |
|---|---|---|---|---|---|---|---|---|
| B1 | `02.050.0020` מרצפי בטון ב-30 | 1 | **114.00** | מ"ר | `—` | concrete B-30, slump 5″, exposure 2-4, cast on 10 cm sub-base or on grade | `(המצע נמדד בנפרד)` — the sub-base is measured separately | this is the **slab**, not a floor finish |
| B2 | `11.012.0182` שליכט צבעוני אקרילי "TM50" | 3 | **140.00** | מ"ר | `—` | fine/medium texture, **2.4–3.3 kg/m² per coat**, acrylic primer tinted to the render; the catalogue text says `על קירות טיח, בטון גבס פנל **(פנים וחוץ)**` | `—` (absent) | the description reads **interior *and* exterior** while a single figure is given. Which faces the 140.00 covers is unstated |
| B3 | `19.030.0310` סיכוך קירות חוץ בפנל מבודד | 4 | **145.00** | מ"ר | `—` (the external envelope) | 50 mm sandwich panel, 0.4 mm galvanised sheet both faces, RAL 9016 outside, foamed polyurethane **40 kg/m³** | `—` | — |
| B4 | `19.015.0100` שלד תקרות וקירות מפרופיל פלדה | 4 | **145.00** | מ"ר | `—` | light galvanised steel framing to **walls and ceilings** | `—` | **145.00 for walls-and-ceilings together** and 145.00 for walls alone (B3). One figure is doing two jobs, or they coincide |
| B5 | `19.030.0108` סיכוך גגות מפנל מבודד | 4 | **114.00** | מ"ר | `—` (roof) | 50 mm insulated roof panel incl. ridge | `—` | equals the slab B1 exactly. A mono-pitch roof over a slab cannot have the same area as the slab unless the roof is measured on plan |
| B6 | `22.021.0155` תקרה אקוסטית מאריחים מינרליים | 4 | **95.00** | מ"ר | `—` | modular mineral tiles "Artic" or eq.; base price ₪61/m²; incl. the suspension frame | `—` | **95.00 against a 114.00 slab and a 114.00 roof** — three different areas for one single-storey building |

**Flooring finish, wall plaster, baseboard: `—` all absent. Zero items each.** This building is a
light-steel and sandwich-panel structure; the bill goes from the concrete slab straight to the
suspended ceiling with no floor finish of any kind.
**Wall construction: thickness stated (50 mm panel, B3); height `—` absent from the BOQ**, though
3.00 m and 4.00 m *are* figured on the elevations — which is a drawing fact, recorded in
`SOURCE-VERIFICATION.md` §2.1, and deliberately **not** imported into this table.

---

## C. Ramat Gan 03/2026 — new-build kindergartens · the richest set, and the drawings are unverified

**Document:** `כתבי כמויות מעודכנים - גני ילדים`, 84 pp, Dekel **V10K**, dated **11/05/2026**,
reissued under `הבהרה מס' 5` of 25/05/2026. A second bill of 83 pp covers the `מעונות`.
**Authorship evidence:** Dekel catalogue codes throughout; every page footed
`הופק ע"י "תוכנת דקל" - חיפה`; headed `תמל 1023 - רמת גן - גני ילדים ומעונות`. Prices published.
**No quantity surveyor named.**
**Drawing reference:** a full register exists (`מסמכי יועצים` pp. 2–4) including **dedicated
flooring plans `510`/`511`**, **ceiling plans `410`/`411`**, sections `200`/`201` and a
`רשימת גמרים`, all `למכרז` **21/04/2026**. **The sheets themselves are UNVERIFIED** — see
`SOURCE-VERIFICATION.md` §3.2. **No BOQ item cites a sheet number.**

### C.0 The status of these numbers, in the publisher's own words — read this before the table

חוברת א' §16: `כתב הכמויות המצורף למסמכי המכרז הינו אינפורמטיבי בלבד ואין הכרח כי כל העבודות
הנדרשות לצורך השלמת הפרויקט מפורטות בו. כתב הכמויות האינפורמטיבי אינו מחייב את החברה כתכולה מלאה
של הפרויקט, ונועד רק לשמש כעזר לקבלן לצורך הגשת הצעתו ואולם למציע לא תהיה כל טענת הסתמכות עליו
**ולא תבוצע מדידת כמויות**.`

חוברת א' §56(ג): `למען הסר ספק יובהר כי מתכונת ההתקשרות למכרז זה הינה "פאושלית" **ללא מדידת
כמויות** למעט עבודות אשר צוין במפורש בחוזה כי תימדדנה.`

And the bill's own first line: `רמת גן-כתב כמויות מנחה 1023 גנים תמל **בלבד**` — *guiding bill
only*.

So for the buildings (מבנה 01) these quantities are **informative, a disclosed estimate
(`אומדן גלוי`), attached to a lump-sum contract under which no quantity will ever be measured.**
Only the external development works (מבנה 02/03) are let `בשיטת מדידה`. The precedence rule is
stated too (§15): **drawings prevail over specifications, specifications prevail over the BOQ.**

| # | item | page | quantity | unit | room / area | material specification as stated | measurement convention | ambiguity or contradiction |
|---|---|---|---|---|---|---|---|---|
| **flooring** |
| C1 | `01.10.031.0042` ריצוף גרניט פורצלן/קרמיקה | 34 | **753.00** | מ"ר | `—` | 33/33, 25/50, 45/45, 50/50 or 60/60 cm; **base price ₪60/m²** | bedding of cement mortar and coarse or stabilised fine aggregate is **in** the price; acrylic grout **in** the price; no distinction between bedded and adhesive-fixed (ג'2 10.02(ב)) | one figure spanning five tile sizes |
| C2 | `01.10.031.0551` ריצוף נגד החלקה **R11** | 34 | **88.00** | מ"ר | `—` | 60/60 cm, **13–15 mm**, base ₪100/m² | as C1 | the description is **byte-identical to C3** at a different quantity |
| C3 | `01.10.031.0552` ריצוף נגד החלקה **R11** | 34 | **246.00** | מ"ר | `—` | identical text to C2 | as C1 | two catalogue codes, identical descriptions, 88.00 and 246.00 — the distinction between them is **not in the document** |
| C4 | `01.10.032.0230` ריצוף אריחי שיש גרניט סיני | 34 | **15.00** | מ"ר | `—` | models 602/603, light speckled grey, 30/60 cm, **2 cm**, base ₪135/m² | as C1 | — |
| **baseboard — present, and the only candidate where it is** |
| C5 | `01.10.031.0043` **שיפולים** לריצוף | 34 | **386.00** | **מ'** | `—` | skirting to the tiles of C1, **height 7 or 10 cm** | measured in **running metres**, cross-referenced to `10.031.0042` | **`7,10 ס"מ` — two heights in one item.** Which rooms get which is not stated, and the length does not say whether door openings were deducted. This is #267's joiner-versus-plasterer question (−23.94 %) arriving unanswered |
| C6 | `01.10.031.0592` **שיפולים** לריצוף | 34 | **107.00** | **מ'** | `—` | skirting to the anti-slip tiles, **height 7 or 10 cm** | running metres, cross-referenced to `10.031.0591` | the cross-reference points at `0591`, but the bill's anti-slip items are `0551` and `0552`. **The referenced item number does not appear in this bill** |
| C7 | `01.10.032.1030` חיפוי מדרגות בשיש גרניט | 35 | **81.00** | **מ'** | stairs | tread 33 cm, riser 15 cm, both 2 cm thick, anti-slip strip, base ₪135/m"א | running metres | tread and riser in one linear metre — a composite unit |
| **wall plaster** |
| C8 | `01.09.011.0010` טיח פנים — **קירות** | 33 | **930.00** | מ"ר | `—` | two screeded coats, straightedge in both directions, on planar surfaces, incl. arris and angle-bead working | ג'2 **09.6(ב)**: the `הרבצה` render coat is **in** the price and not measured separately. ג'2 **09.02**: interior plaster **15–20 mm total**, three layers (render, levelling, white skim) | the item says `שתי שכבות` and the specification says three layers — reconcilable only if the render is the layer the specification already declared unmeasured |
| C9 | `01.09.011.0011` טיח פנים — **תקרות** | 33 | **205.00** | מ"ר | `—` | identical text, ceilings | as C8 | walls and ceilings **split into separate items** — the only candidate that does this |
| C10 | `01.09.013.0030` טיח רב-תכליתי לממ"ד | 33 | **360.00** | מ"ר | **ממ"ד** (protected rooms) | PL130/770 or eq. approved for ממ"ד, **10 mm**, glass-fibre mesh, skim **up to 5 mm** | as C8 | room *type* attributed, individual rooms not |
| C11 | `01.09.021.0010` טיח חוץ | 33 | **1,442.00** | מ"ר | external | lower render, levelling coat, black skim | ג'2 **09.6(ד)** overrides the national standard — see below | — |
| C12 | `01.09.021.0120` טיח חוץ על חשפים (גליפים) | 33 | **381.00** | **מ'** | reveals | planar reveals **up to 22 cm wide**, incl. arrises and angle beads | measured in **running metres** here | **and ג'2 09.6(ד) says the opposite**: `בניגוד לאמור במפרט הכללי לעבודות טיח לא ישולם בנפרד עבור הפשלים (גליפים) ושטחם יימדד לפי שטח במ"ר לפי סעיף הטיח` — not paid separately, measured in **m² under the plaster item**. The bill measures them in metres as their own item. **Direct contradiction between the bill and the special specification of the same tender** |
| **wall painting** |
| C13 | `01.11.011.0200` צבע "סופרקריל" — **קירות** | 36 | **1,535.00** | מ"ר | `—` | on interior plaster or gypsum, brush or spray, `טמבורפיל` primer **+ two coats** | `—` in the bill. ג'2 **11.03** says `בשלוש שכבות` — **three coats** | **two coats in the bill against three in the specification.** An area dispute this is not; a *material* dispute it is, and it lands on the purchase quantity |
| C14 | `01.11.011.0201` צבע "סופרקריל" — **תקרות וסינרי גבס** | 36 | **186.00** | מ"ר | ceilings and gypsum bulkheads | identical text | as C13 | — |
| C15 | `01.11.011.0010` סיוד ב"פוליסיד" | 36 | **214.00** | מ"ר | `—` | synthetic limewash on interior plaster, **three coats** | `—` | a second interior wall finish with no stated boundary against C13 |
| C16 | `01.11.011.0030` סיוד ב"פוליסיד" על בטון | 36 | **74.00** | מ"ר | `—` | on concrete, three coats | `—` | 74.00 also appears as the corridor cladding C19 — coincidence or copy is undeterminable |
| C17 | `01.11.012.0184` שליכט צבעוני "TM70" | 37 | **1,535.00** | מ"ר | `—` | coarse texture, `(פנים וחוץ)`, **2.3–3.0 kg/m² per coat**, acrylic primer tinted to the render | `(הנמדדת בנפרד במידה ונידרש)` — a levelling substrate is measured separately **if required** | **1,535.00 appears exactly twice in this bill** — here, and as the interior Supercryl C13. Two items of different scope carrying an identical figure to the hundredth. Recorded as an **anomaly**, not asserted as an error: no document explains it |
| **ceiling finishing** |
| C9 (above) | `01.09.011.0011` plastered ceilings | 33 | 205.00 | מ"ר | — | — | — | — |
| C14 (above) | `01.11.011.0201` painted ceilings | 36 | 186.00 | מ"ר | — | — | — | 186.00 painted against 205.00 plastered: a 19 m² difference with nothing to explain it |
| **wall cladding — the only room-attributed quantities in any of the three candidates** |
| C18 | `01.10.050.0013` חיפוי קירות פנים | 35 | **145.00** | מ"ר | **`שירותים`** (toilets) | porcelain/ceramic **10/30 cm**, base ₪70/m² | ג'2 **10.02(ז)**: `חיפוי באריחים יימדד לפי שטח **נטו** במ"ר` — **net** area; levelling plaster and render on masonry are **in** the cladding price and not measured separately (09.6(ה)) | the room is a *type*, and the register shows **four** separate PRS toilet layouts (`600`–`603`). 145.00 covers all of them |
| C19 | `01.10.050.0015` חיפוי קירות פנים | 35 | **65.00** | מ"ר | **`מטבחון`** (kitchenette) | base ₪70/m² | as C18, **net** | — |
| C20 | `01.10.050.0025` חיפוי קירות פנים | 35 | **74.00** | מ"ר | **`מסדרון`** (corridor) | base ₪60/m² | as C18, **net** | — |
| C21 | `01.10.050.0029` חיפוי קירות פנים | 35 | **93.00** | מ"ר | `—` | 60/60 cm, base ₪100/m² | as C18, **net** | the one cladding item with no room, beside three that have one |
| **wall construction — thickness yes, height no** |
| C22 | `01.04.010.0020` מחיצות בלוקי בטון חלולים | 6 | **50.00** | מ"ר | `—` | hollow concrete block, **10 cm** | `—` | — |
| C23 | `01.04.010.0030` קירות בלוקי בטון חלולים | 6 | **20.00** | מ"ר | `—` | 4-cell hollow block, **15 cm** | `—` | — |
| C24 | `01.04.010.0040` קירות בלוקי בטון חלולים | 6 | **360.00** | מ"ר | `—` | 4-cell hollow block, **20 cm** | `—` | **wall height is absent from all three.** Masonry measured in m² with the thickness in the description and the height nowhere |

---

## The national convention these bills defer to — and it is public

Both Nahariya and Ramat Gan incorporate the measurement conventions **by reference to a document
not included in either pack**:

- Nahariya 17/2026, booklet appendix: `כל העבודות יבוצעו לפי המפרט הכללי בעבודות בניה (הספר הכחול) וההוצאה הבין משרדית של משרד השיכון, משרד הבטחון ומ.ע.צ.`
- Ramat Gan, bill general note: `כל העבודות בפרק זה כפופות לנאמר ב"מפרט כללי לעבודות בנין" ("האוגדן הכחול"), **כולל אופני המדידה**, אלא אם צויין אחרת בסעיף.`
- Ramat Gan, ג'2 chapter 10: cladding `כמתואר במפרט הכללי פרק 10 סעיף 10065`.

**That document is published free by the Ministry of Defence** at
<https://mifratclali.mod.gov.il/>. Its catalogue was read from the site's own unauthenticated API
and the relevant chapters exist with editions:

| chapter | title | editions listed |
|---|---|---|
| `04` | עבודות בנייה | 1995, correction sheet 1997 |
| `09` | **עבודות טיח** | 2005, 2007, correction sheet תמוז תש"פ **July 2020** |
| `10` | **עבודות ריצוף וחיפוי** | 2001, **תשרי תשע"ט September 2018** |
| `11` | **עבודות צביעה** | 2005 |
| `22` | רכיבים מתועשים בבניין (מחיצות, תקרות, רצפות) | 2007 |

So the convention layer that #267's **C3** requires has a **free national anchor**, and the
conventions are retrievable rather than lost. Two limits must be stated with it, and neither is
small:

1. **The chapter PDFs were not retrieved from this environment — `UNVERIFIED`.** The catalogue API answers, and the PDF.js viewer page for chapter 10 loads, but every direct path to the file bytes returned the application shell instead. Whether the chapter text — and therefore its `אופני מדידה` — is extractable has **not** been demonstrated here.
2. **A national convention is a default, and this tender overrides it in writing.** ג'2 09.6(ד) begins `בניגוד לאמור במפרט הכללי` — *contrary to the General Specification* — and changes how reveals are measured. So reading the Blue Folder tells you the default, not the answer. The answer is per job, which is exactly C3's claim, now evidenced from a live tender rather than argued.

## What the extraction found, in one paragraph

Across the three candidates, **64 of the quantity cells that a takeoff needs are present and 9 are
room-attributed** — all nine in Ramat Gan, and `שירותים`, `מטבחון` and `מסדרון` are room *types*
rather than rooms. **Not one quantity in any of the three cites a drawing, a sheet number or a
measured room.** Baseboard exists in exactly one candidate. Wall height exists in **none** of the
three bills; it exists only as a price band (A13), as a hanger depth (A7), as soffit annotations on
one drawing and as elevation figures on another, and the directive forbids promoting any of those
into a measured wall height. Three internal contradictions are recorded and attributed to their
documents rather than resolved: the 151 m² of Nahariya partitions `מוכן לצביעה` with no interior
paint item (A6), Ramat Gan's reveals measured in metres by the bill and in m² by its own
specification (C12), and Ramat Gan's `1,535.00` standing against two items of different scope
(C17).
