# Product Readiness Audit — reference set (research done 2026-10-06, audit itself still gated)

Owner authorised independent web research for the reference set. Used ONLY for: what architectural
information is communicated; plan readability and conventions; what is necessary to evaluate a
concept; the boundary between concept-plan information and construction-document detail. Geometry is
NOT copied and BuildSmart is NOT judged against permit/construction-document standards.

Deliberately drawn from several independent sources so no single firm's drawing style becomes the
definition of architectural quality.

## A. Scope boundary — what a CONCEPT plan is expected to carry

| source | what it establishes |
|---|---|
| RIBA Plan of Work, Stage 2 Concept Design | Stage 2 is where the client first sees drawings of the design. Deliverables are massing studies, sketch plans, floor plans, elevations and sections, plus an outline specification and strategic engineering input — explicitly NOT technical design (Stage 4). |
| AIA Schematic Design vs Construction Documents | SD produces a conceptual site plan and preliminary plans, sections and elevations establishing "the scale and relationship of the Project components", typically with overall dimensions. CD is where every detail, dimension and annotation needed to build arrives. On residential work DD and CD commonly merge. |

**Consequence for the audit:** overall dimensions and room relationships are IN scope at concept
stage. Full dimension strings, schedules, construction detail and specification notes are NOT, and a
missing door schedule is not a BuildSmart deficiency.

## B. Drawing conventions — what readers rely on

| source | what it establishes |
|---|---|
| Cedreo, "Floor Plan Symbols & Abbreviations" | Door swing = wall break + quarter-circle arc + leaf line; single vs double arcs; sliding/pocket doors have distinct marks. |
| ArchitectGPT, "How to Read a Floor Plan" | North arrow conveys orientation, and plans may distinguish true/project/grid north. Scale bar or stated scale is required to relate drawing to reality. |
| MT Copeland, "Complete Guide to Blueprint Symbols" | **Line weight is information, not style**: walls, doors and windows are heaviest; fixtures thin; furniture lightest, so a reader can instantly tell what is building and what is contents. Poché/thick parallel lines mark exterior or load-bearing walls, and **wall thickness is drawn to scale so exterior walls read visibly fatter than partitions**. |

## C. Real plans actually inspected

### C1 — Gen. Israel Putnam House, Danvers, Massachusetts (HABS, US federal, public domain)
`commons.wikimedia.org/wiki/File:Putnam_House_-_floor_plans.jpg` — a measured survey drawing.
Carries: room labels on every space; running dimension strings on all four sides plus overall
dimensions; door swings, each numbered against a door schedule; window openings in the walls; stairs
with UP/DOWN and tread lines; closets and cupboards labelled; wall poché distinguishing thickness;
chimney masses; **north arrow**; **two scale bars (metric and feet)**; a title block naming the
structure, location, sheet number and draughtsman; and condition annotations.
**Carries no furniture at all** beyond built-ins — useful evidence that furniture is not required for
a plan to read as professional.

### C2 — "Sample Floorplan", residential CAD plan (public domain)
`commons.wikimedia.org/wiki/File:Sample_Floorplan.jpg`.
Carries: room labels; **furniture layout** (dining table and chairs, sofas, beds, kitchen island);
kitchen and bathroom fixtures; door swings; window symbols annotated with sill height (BRH 87.50);
stairs annotated with riser count and riser/tread dimensions; wall hatching distinguishing exterior
from partition; north arrow; the entrance named as a room.
**Carries no dimension strings** — the opposite trade from C1.

**What C1 and C2 agree on, despite opposite choices elsewhere** — room labels, door swings, window
openings in the wall line, a visible distinction between exterior wall and partition, stairs where
present, a north arrow, and an identified entrance.

> **PROVISIONAL (owner instruction, 2026-10-06).** This is a *candidate* minimum core derived from
> references alone. It is NOT a standard to measure against until the actual BuildSmart plans have
> been inspected, and it may well change once they are. Do not treat it as settled, and do not let it
> pre-decide the audit's findings.

## D. Market-specific reference — the Israeli MAMAD

Two independent sources, corroborating: Wikipedia "Merkhav Mugan" and the Realta MAMAD guide.

| requirement | value |
|---|---|
| floor area | ≥ 9 m² (5 m² only with Home Front Command approval); max 12 m² + optional 3 m² bathroom |
| clear height | ≥ 2.5 m |
| external RC wall | **25 cm** (30 cm with a sliding window, 40 cm if standalone) |
| internal RC wall | **20 cm** |
| ceiling/floor RC | 30 cm |
| window | blast-resistant, sill ≥ 1.5 m above floor, no external bars (it is an escape route) |
| door | steel, IS 4422, inward-opening, 80–150 kg |

Wikipedia independently gives 20–30 cm, consistent with the above.

**To check during the audit, not concluded now:** BuildSmart's `RC_SAFE_ROOM` wall inset is 0.15 m,
against a real requirement of 20–25 cm. The inset is a NET-area half-wall allowance and may or may
not correspond to modelled wall thickness, so the semantics must be read from the code before this is
called a finding. Also to check: whether the safe room's minimum area, minimum width and window
requirement are represented at all.

## E. Constraints the owner set for using this material (2026-10-06)

1. The candidate minimum core above stays **provisional** until real BuildSmart plans are inspected.
2. **Do not classify furniture, full dimensioning, title blocks, schedules or similar as mandatory**
   merely because an individual reference happens to contain them. C1 has no furniture and C2 has no
   dimension strings; presence in one drawing proves nothing about necessity.
3. **Separate two different things** in every finding: architectural information genuinely required to
   *evaluate whether the concept works*, versus drawing conventions that primarily improve
   *communication*. These are not the same deficiency class and must not be merged.
4. For any **regulatory** conclusion (the MAMAD above being the obvious case) prefer **authoritative
   and current Israeli sources** — Home Front Command / Israeli standards — over secondary guides.
   The Realta guide and Wikipedia are adequate orientation, not an authority to cite in a finding.
5. **Verify what BuildSmart's 0.15 m SAFE_ROOM inset actually represents** — read the code's own
   semantics — *before* comparing it with any physical wall-thickness requirement.

## F. Gaps in this set, to close when the audit gate opens
- No contemporary published architect's plan has been visually inspected yet. ArchDaily's gallery
  ordering returned photographs rather than drawings on the first attempt.
- No Israeli apartment plan with a MAMAD has been visually inspected yet; only the written standard.
Both are required additions once the gate opens, so the set spans a historic survey drawing, a
generic CAD plan, a contemporary practice drawing and a local-market plan with a MAMAD. The Israeli
example must come with an authoritative source for any regulatory claim drawn from it.

## Sources
- https://www.architecturenorth.co.uk/blogs/riba-work-stage-2-concept-design-
- https://architectureforlondon.com/news/the-riba-plan-of-work/
- https://studior-e-d.com/wp-content/uploads/2015/05/AIA-Standard-Services.pdf
- https://monograph.com/blog/guide-to-design-phases
- https://cedreo.com/blog/floor-plan-symbols/
- https://www.architectgpt.io/blog/how-to-read-a-floor-plan-symbols-scale-and-dimensions-explained
- https://mtcopeland.com/blog/complete-guide-to-blueprint-symbols-floor-plan-symbols-mep-symbols-rcp-symbols-and-more/
- https://commons.wikimedia.org/wiki/File:Putnam_House_-_floor_plans.jpg
- https://commons.wikimedia.org/wiki/File:Sample_Floorplan.jpg
- https://en.wikipedia.org/wiki/Merkhav_Mugan
- https://realta.co.il/en/guides/mamad/
