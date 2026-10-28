# Source verification — Israeli public tender documents

**Issue:** #269 (child of ROOT #262, condition **C2**) · **Date of verification: 2026-10-28** ·
**Branch:** `investigate/ground-truth-israel` at `c07bf71`

Research and documentation only. No production code, no ingestion, no pricing, no supplier work.

## How this was verified

Every statement below was obtained by **opening the official page and downloading the actual
document**, then reading it. No prior description of any candidate was relied on — including the
summaries in the Issue and the directive, one of which this document corrects (§4).

Documents were downloaded into a **session scratchpad outside the repository** and read there.
**Nothing was copied into this repository**, because all three candidates carry explicit reuse
prohibitions (§5). Every quantity cited in the sibling documents is cited with its publisher, its
document, its item number and its URL, and the document itself is linked rather than reproduced.

PDF structure (page count, text layer, producer, embedded creation date) was read from the files'
own metadata; drawing content was read from the rendered page. Where a figure is quoted in Hebrew
it is quoted as the document writes it.

## 1. Candidate A — Nahariya 17/2026 · **VERIFIED**

| field | value |
|---|---|
| Publisher | החברה הכלכלית נהריה בע"מ (the municipal economic company of Nahariya) |
| Project | עבודות שיפוץ למתחם משרדים — refurbishment of an office suite |
| Tender number | 17/2026 · type **פומבי** (open) |
| Landing page | <https://www.nahariya.muni.il/bids/519/> — HTTP 200 |
| Published | 24/03/2026 14:46 (as printed on the page) |
| Bids due | 09/04/2026 13:00 |
| Page status | reached under the breadcrumb **ארכיון** (archive) |
| Accessibility | **fully open** — no registration, no portal, no payment to view or download |

### Documents actually retrieved

| document | URL | bytes | pages | text layer | producer / embedded date |
|---|---|---|---|---|---|
| כתב כמויות (BOQ) | `/uploads/n/1774357543.5360.pdf` | 446,646 | **18** | **yes** (38,916 chars) | `בנארית - הפקת דוחות` via novaPDF SDK 11.9; author `4372.eliranas`; created 24/03/2026 13:02 |
| תכנית אדריכלית (architectural plan) | `/uploads/n/1774357563.5215.pdf` | 123,780 | **1** | **none (0 chars)** | KONICA MINOLTA bizhub C308 **scan**; created 24/03/2026 16:17 |
| קובץ דיוקים לפרק בינוי | `/uploads/n/1774357554.9486.pdf` | 264,665 | 4 | **none (0 chars)** | KONICA MINOLTA bizhub C308 **scan**; created 24/03/2026 14:55 |
| סיכום מפגש מציעים | `/uploads/n/1774952305.8692.pdf` | 206,187 | 2 | yes | Word 2021; author `איריס חזן | חברה כלכלית`; created 31/03/2026 |
| main tender booklet | `/uploads/n/1774357417.7297.pdf` | 1,791,807 | **94** | yes | Word 2021; title `מקלטים`; author `עו"ד קטיה גולובשקו`; created 24/03/2026 15:02 |

All five returned HTTP 200 and all five parsed. **No document is missing from the list the page
offers**; what is missing is a document the page never offered — see §1.3.

### 1.1 The drawing, read from the sheet

The single architectural sheet is a **figured floor plan**, and it is materially better evidence
than the 1923 fixture that set this Issue's prior. Read from the title block:

- architect **SHIR & STAV — Architecture & Engineering** (`הסבת מבנים | אדריכלות | עיצוב פנים`)
- `תכנית: אדריכלית` · `גיליון מס': א-1` · `גודל גיליון: A3` · **`קנ"מ 1:50`** · dated **12.03.2026**
- status row `לעיון / לאישור / למכרז / לביצוע` with **לביצוע** marked — *for construction*, **not** *for tender*
- `לקוח:` and `כתובת:` are **blanked out** on the published copy; `חתימת הלקוח לאישור התכניות` is **unsigned**

The sheet carries, contrary to the prior:

- **figured dimension chains** throughout (overall 1623; 740, 472, 350, 340, 326, 325, 319, 318, 295, 258, 235, 213, 210, 186, 180, 175, 167, 160, 150, 148, 130, 118, 108, 105, 94, 90, 61, 30, 28, 20, 19 …)
- **four annotated structural soffit levels** — `פני בטון תקרה H=240`, `H=260`, `H=275`, `H=290`
- **floor levels per area** — `+0.30`, `+0.15`, `±0.00`, `−0.01`, with `מדרגה טובה 15 ס"מ`
- **door sizes in the opening tags** — `נג 70/205`, `נג 80/205`
- named rooms — `שירותים`, `קפיטריה`, `אזור המתנה וקבלת קהל`, `משרד`, `משרד מנהל`, `ארון תקשורת`

### 1.2 Six notes in the title block, and three of them are conventions

Quoted verbatim from the sheet:

1. `על המבצע לבדוק את התאמת התכנית בשטח, לפני הבניה, ולבקר את המידות. על כל טעות ו/או אי התאמה יש לעדכן משרד מתכנן.`
2. **`אין לקבוע מידות עפ"י שרטוט. המידות המחייבות הן מידות שנמדדו בשטח לאחר ביצוע`**
3. **`המידות בתכנית הן ברוטו - ללא חיפוי גמר`**
4. `יתכנו שינויים בהתאם להוראות הביצוע הסופי`
5. **`כל התכניות נשארות רכוש המתכנן: אין לעשות בהן שימוש ללא אישור בכתב מהמתכנן`**
6. `כל ההערות תקפות אלא אם צויין אחרת`

Note 2 is #267's "figures govern, or scale the drawing" convention found in a live Israeli
document — and it goes one step further than #267 did. It forbids scaling **and** declines to make
the printed figures binding: the binding dimensions are *those measured on site after execution*.
Note 3 states the dimensional datum — **gross, excluding finish cladding**. Note 5 is the licence
(§5).

### 1.3 Same project revision? **Not establishable.**

- The drawing is dated **12.03.2026** and stamped **לביצוע**; the BOQ was generated **24/03/2026**, twelve days later; the tender was published the same day as the BOQ.
- There is **no revision table, no revision cloud and no drawing register** anywhere in the pack, and **one** architectural sheet is published for a 94-page tender of a multi-room refurbishment.
- So the only defensible statement is the negative one: **no superseding sheet is published, and no document asserts that this sheet is the sheet the BOQ was measured from.** Correspondence is *consistent with* but **not demonstrated by** the pack.

## 2. Candidate B — Nahariya 19/2026 · **VERIFIED, and the tender was CANCELLED**

| field | value |
|---|---|
| Publisher | החברה הכלכלית נהריה בע"מ |
| Project | עבודות שיפוץ לשיקום מבנה מסחרי — refurbishment to rehabilitate a commercial building |
| Tender number | 19/2026 · **פומבי** |
| Landing page | <https://www.nahariya.muni.il/bids/542/> — HTTP 200 |
| Published | 27/05/2026 15:33 · bids due 10/06/2026 13:00 |
| **Status** | **CANCELLED 09/06/2026** |
| Accessibility | fully open |

The cancellation notice (`/uploads/n/1781010682.7433.pdf`, 1 p, created 09/06/2026, signed
**יניב קריאף, מנכ"ל חכ"ל נהריה**) gives the reason in the publisher's words:
`לאחר בחינה מחודשת של צרכי הפרויקט ובשל שינויים מהותיים במכרז ובהיקף העבודות הנדרשות, הוחלט על ביטול המכרז`
— *following a renewed examination of the project's needs and because of material changes in the
tender and in the scope of the works required.*

A cancelled tender's quantities were never contracted, never built and never measured. That does
not make them worthless as a *drawing-to-BOQ* exercise, but it removes any route to field evidence.

| document | URL | bytes | pages | notes |
|---|---|---|---|---|
| הודעה על ביטול המכרז | `/uploads/n/1781010682.7433.pdf` | 159,430 | 1 | Word 2021, 09/06/2026 |
| כתב כמויות | `/uploads/n/1779885305.7523.pdf` | 188,052 | **6** | Winnovative HTML-to-PDF; **no embedded creation date**; body footer: `הופק ע"י "תוכנת דקל" - חיפה`, `מספר פנימי 37858`, `מספר ייחודי 1545615`, dated **26/04/2026** |
| **תוכנית** | `/uploads/n/1779885320.2209.jpg` | 118,593 | — | **JPEG 1536×1024** |
| סיכום מפגש מציעים | `/uploads/n/1780396123.4119.pdf` | 207,634 | 2 | Word 2021, 02/06/2026 |
| main tender booklet | `/uploads/n/1779887368.6813.pdf` | 1,742,081 | 90 | Word 2021, 27/05/2026 |

### 2.1 The "תוכנית" is not a plan

Read from the image: it is **three elevations** — `חזית צפונית`, `חזית מזרחית`, `חזית מערבית`.
There is **no floor plan**, no title block, no sheet number, no scale, no date, no north arrow and
no named author. It carries, however, exactly the data this project has never had:

- **wall heights figured** — 3.00 m at the eaves and 4.00 m at the high side, with levels +3.00 and +4.45 (a mono-pitch roof)
- footprint widths — **7.00** (north elevation) and **13.30** (east and west elevations)
- **opening sizes figured** — windows 1.00 × 0.60 (three) and 0.30 × 0.60, doors 1.10 × 2.10

There is **no south elevation**, so the footprint is two orthogonal widths and nothing more. A
rectangular plan is an **inference**, not a fact of the document, and §5 of
`MEASUREMENT-GAPS.md` treats it as one.

### 2.2 Same project revision?

The BOQ's body is dated **26/04/2026**, the tender was published **27/05/2026**, the plan JPEG
carries **no date at all**, and the tender was cancelled on **09/06/2026** for *material changes in
scope*. There is no revision marking on any of the three. **Not establishable.**

## 3. Candidate C — Ramat Gan 03/2026 · **VERIFIED for the documents, UNVERIFIED for the drawings**

| field | value |
|---|---|
| Publisher | **החברה הכלכלית לפיתוח רמת גן בע"מ** — wholly owned by Ramat Gan Municipality; תובל 13 (קומה 2), רמת-גן 5252228; tel 03-7591000 |
| Project | הקמת גני ילדים ומעונות יום ע"ש אריאל וכפיר ביבס — **new-build** kindergartens and day-care centres, plots 203–205, תמ"ל 1023, תל השומר דרום |
| Tender number | **03/2026** · פומבי |
| Landing page | <https://calcalit-rg.co.il/michrazim/032024-copy/> — HTTP 200 |
| Accessibility | document PDFs fully open; **the drawings are not on this site** (§3.2) |

**Correction worth recording:** the URL slug reads `032024-copy`, but the tender is **03/2026**.
The page is a copy of an earlier tender's page and its slug was never changed. The slug is not
evidence of the tender number; the documents are.

### Documents actually retrieved (12 of 12 offered, all HTTP 200)

| document | pages | bytes |
|---|---|---|
| חוברת א' — מסמכי המכרז | 49 | 722,888 |
| חוברת ב' — הסכם ההתקשרות | 115 | 1,563,499 |
| **מסמך ג'2 — מפרט טכני מיוחד ואופני מדידה מיוחדים** | **308** | 4,653,974 |
| מסמך ג'3 — רשימת התוכניות | **1** | 146,341 |
| מסמך ד' — כתבי כמויות אינפורמטיבי + הבהרות והערות | 158 | 1,840,549 |
| מסמכי יועצים (**the actual drawing register**) | 4 | 665,120 |
| הבהרה 1 / 2 / 5 | 7 / 2 / 1 | — |
| פרוטוקול מפגש מציעים (10.5.2026) | 5 | 225,809 |
| **כתבי כמויות מעודכנים — גני ילדים** | **84** | 905,555 |
| **כתבי כמויות מעודכנים — מעונות** | **83** | 898,188 |

### 3.1 The drawing register is real and complete

`מסמך ג'3 - רשימת התוכניות` is **not** a register: it is a one-page cover sheet carrying a
file-transfer link. The actual register is inside `מסמכי יועצים` (pp. 2–4), and it lists every
sheet with number, name, **scale** and **status + date**. The architectural set, all
status `למכרז` dated **21/04/2026**:

`100` תכנית העמדה 1:200 · `110` תכנית קומת קרקע · `111` תכנית קומה א' 1:50 · `112` תכנית גגות ·
`200` חתכים 1-3 1:50 · `201` חתכים א-ג 1:50 · `300`/`301` חזיתות · **`410`/`411` תכנית תקרה** ·
**`510`/`511` תכנית ריצוף** · `600`–`603` PRS פריסות חדרי שירותים · `900`–`904` STR גרמי מדרגות ·
`LST ALU`/`MAS`/`NAG` · **`רשימת גמרים`** (a finishes schedule)

plus structure (10 sheets, 14/09/2025 – 16/04/2026), electrical (12, status `לביצוע`),
waterproofing (~40 at 1:10), lifts (5), development (5) and plumbing/sprinklers (~18).

This is the only candidate whose set contains **dedicated flooring plans, dedicated ceiling plans,
sections, and a finishes schedule** — i.e. the drawings a finishes takeoff would actually be
measured from.

### 3.2 The drawings themselves — **UNVERIFIED**, and this is the blocker

The sheets are not published on the municipal company's site. Both the tender drawings and the
consultants' drawings are delivered through **JumboMail**, a commercial file-transfer service:

- `https://www.jumbomail.me/j/K9Or95g-kUi7jey` — gallery title **"תוכניות למכרז 03-2026"**
- `https://www.jumbomail.me/j/kK18ptddL0uUE5Z` — gallery title **"תמ"ל 1023- תוכניות יועצים למכרז"**

Both landing pages return HTTP 200 and resolve to a gallery with the correct Hebrew title, so the
transfer records still exist. **The file manifest and the files themselves could not be
retrieved from this environment.** Exactly what blocked it: the gallery is a client-side
application that fetches its contents by `POST` to controller `Mails`, function
`ReactGetGalleryBootstrap`, against the production API base `https://api.jumbomail.me` (read from
the application's own configuration bundle). Six route spellings were tried against two hosts and
all returned 404, so the manifest was never obtained and **it is not known whether the files are
still present, whether the galleries have expired, or whether a download would be permitted**.
Recorded as **UNVERIFIED**; the register above is what *is* verified about the drawings.

A **public contact channel for this exact problem is printed in the pack**:
`במידה ויש תקלות בהורדת הקבצים, ניתן לפנות למנהלת חוזים, התקשרויות וכ"א, גב' ריקי קורן, בדואר
אלקטרוני rikik@calcalit-rg.co.il או בטלפון 03-3850800`. No contact was made (§6).

### 3.3 Same project revision? **Partially establishable, and the pairing is uneven**

`הבהרה מס' 5` (25/05/2026) replaced the bills of quantities — `החברה מודיעה בזאת על עדכון כתבי
הכמויות המצורפים לחוברת ד'` — and states that `למעט השינויים ... יישארו כל יתר הוראות המכרז,
תנאיו ונספחיו ללא שינוי`. So:

- the drawing register stays at **21/04/2026** (`למכרז`),
- the operative BOQ is the **11/05/2026** Dekel issue, reissued under clarification 5 of **25/05/2026**,
- the superseded BOQ (חוברת ד', 158 pp) is **still published alongside it**.

A revised BOQ against an unrevised drawing set, with the publisher asserting — but not
demonstrating — that nothing else changed. Anyone using this pack must take the **מעודכנים** bills
and not חוברת ד'; the page offers both with no warning on the older one.

## 4. What the three candidates are not

The directive asked that no prior description be trusted, including the owner's own summary. Two
corrections follow from the documents:

- **Neither Nahariya tender is a new building.** 17/2026 is an office fit-out and 19/2026 is the refurbishment of a commercial structure. Their BOQs are therefore **patch-and-alteration measures**, not takeoffs of rooms — 17/2026 prices *two square metres* of new flooring. This matters more than any licence question and is why §2 of `MEASUREMENT-GAPS.md` reaches the conclusion it does.
- **Only Ramat Gan 03/2026 is a new build**, and it is the only one whose BOQ is a complete finishes takeoff — and the only one whose drawings cannot be opened.

## 5. Licensing and reuse — all three restrict it, explicitly

| candidate | the term, as the document states it | effect |
|---|---|---|
| Nahariya 17/2026 | title-block note 5: `כל התכניות נשארות רכוש המתכנן: אין לעשות בהן שימוש ללא אישור בכתב מהמתכנן` | the **drawing** may not be reused without the designer's written permission |
| Nahariya 17 & 19 | tender booklet appendix: works per `המפרט הכללי בעבודות בניה (הספר הכחול)`; no general grant of reuse appears anywhere in either booklet | no permission to reuse is given |
| Ramat Gan 03/2026 | חוברת א': `המסמכים הינם רכוש החברה וחל איסור מוחלט לעשות בהם שימוש אחר פרט להשתתפות במכרז` | **absolute prohibition** on any use other than bidding |
| Ramat Gan — site | footer: `כל הזכויות שמורות. אין להעתיק ו/או לשכפל ו/או לצלם חומרים ותמונות מאתר זה ללא הרשאה מראש` | no copying, duplicating or photographing without prior permission |

**Consequence, applied throughout this report:** every document is **linked and described, never
copied into the repository**, and no drawing, plate, table or page is reproduced. Factual
quantities and the documents' own stated conventions are **cited with attribution** — the same
reading #263 recorded for the Indian course material, that copyright protects expression and not
facts. None of the three is available under any open licence, and **none of the three may be
redistributed**.

## 6. Nothing was sent

No message was sent to any publisher, architect, consultant or contractor, and no registration was
performed anywhere. The contact details recorded here and in `OUTREACH-HE.md` were read from
published pages and documents.

## 7. Everything marked UNVERIFIED by this document

1. **The Ramat Gan drawing files** — galleries resolve, manifest unreachable, expiry unknown (§3.2). Everything said about those drawings here comes from the **register**, not from the sheets.
2. **Same-revision correspondence** for Nahariya 17/2026 (§1.3) and 19/2026 (§2.2) — no revision marking exists to check.
3. **Whether the `לביצוע` stamp on the Nahariya 17/2026 sheet means it is the construction issue** — the status row is marked but the client approval line is blank, and the pack says nothing.
4. **Who measured either Nahariya BOQ.** The 17/2026 file carries only the software user `4372.eliranas` and the header `עיריית נהריה - אגף טכני - ניהול פרויקטים`; the 19/2026 file carries no author at all. Neither names a quantity surveyor.
5. **Whether the Nahariya 19/2026 plan JPEG belongs to the same design iteration** as its BOQ — it carries no title block of any kind.
