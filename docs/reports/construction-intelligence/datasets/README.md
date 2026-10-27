# Acquired reference data — licences, provenance and permitted use

Acquired for #263 (ROOT #262). **Two projects**, both under a verified **CC BY 4.0** grant. Read
`../DATASET-contract-and-acquisition.md` §4.A and §6 before using any value here: these are
**inputs and cross-check values, not accuracy ground truth**, and §6 says exactly why.

Nothing here was paid for. Nothing here is synthetic. Nothing here was produced by BuildSmart.

## What is committed, and what is not

The upstream COBie workbooks are freely re-downloadable under the grant below, so this directory
commits **CSV extracts** rather than multi-megabyte binaries — they are reviewable in a diff, which
a spreadsheet is not. Each extract is a faithful transcription: no value was rounded, recomputed,
unit-converted or cleaned. Column names ending `_as_published` carry the source's own label even
where it is wrong (see the volume-unit defect below).

To re-derive, download the workbook and read the `Space`, `Type`, `Component` and `Attribute`
sheets. SHA-256 of the exact upstream files used:

| File | SHA-256 |
|---|---|
| `2012-03-23-Duplex-Handover.xlsx` | `26cdaf0bbf34b67f0f68c78de5bc3c1c3a285df97223c2704c9175b1936fdd4a` |
| `2013-10-09-Clinic-Handover-v14.xlsx` | `cc539fe27e3a8df5c80bc6710c17f96f329c3d5d1b023b4246536333bcd77b7a` |

---

## 1. Duplex Apartment — `duplex-apartment/`

**Source**: buildingSMART International community repository,
`https://github.com/buildingsmart-community/Community-Sample-Test-Files`, folder
`IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment`.

**Licence, quoted from that folder's own `README.md`**:

> These files were originally provided under Creative Commons Liscence. These files are provided
> here under this same liscence. Creative Commons (CC BY 4.0). You are free (1) to copy and
> resitribute this material any way you like, (2) you may change the information any way you want,
> (3) you must identify the source of the infomation as "BSI (2020) "Duplex Apartment Test Files,"
> buildingSMART International" and add this GitHub URL, and (4) if you may changes to these files
> you must indicate the types of changes made.

**Required attribution** (clause 3): BSI (2020) "Duplex Apartment Test Files," buildingSMART
International — https://github.com/buildingsmart-community/Community-Sample-Test-Files

**Changes made** (clause 4): extracted a subset of four COBie sheets to CSV. No value altered.

**Provenance of the values**: `ExtSystem` on every space row reads
`Autodesk Revit Architecture 2011`, and `CreatedBy` is a USACE address. The project was first
published in Germany, provided to the US Construction Engineering Research Laboratory, hosted by
NIBS 2009–2020, and mirrored here after NIBS removed it. So the areas are a **design-model export**,
self-declared as such — reliability grade **`DERIVED`** under the contract's V5, never `VERIFIED`.

| File | Contents |
|---|---|
| `spaces.csv` | 22 spaces: `GrossArea`, `NetArea` (m²), `UsableHeight` (mm), `Perimeter`, `Volume` |
| `opening-types.csv` | 9 door / window / skylight types with the published description string |
| `opening-instances.csv` | 36 opening instances mapped to the spaces each serves |

**Three defects found and recorded rather than cleaned:**

1. **`UsableHeight` is `0` for all 22 spaces** — no height is stated.
2. **A height is *not* recoverable from `Volume`.** Measured: `Volume / GrossArea` ranges
   **2.045 m to 4.225 m**, a 2.18 m spread, and differs between a bathroom (2.045) and a kitchen
   (2.411) on the same storey. A real duplex has no such variation, so the field is an `IfcSpace`
   extrusion artifact. Deriving a wall height from it would be both the inference ROOT #262's AC-4
   forbids **and** wrong.
3. **`Volume` is published with `Unit = "meter"`** where the values are plainly cubic metres, and
   the structured `NominalLength` / `NominalWidth` / `NominalHeight` fields are **`0` for 7 of the
   9 opening types** — so the opening dimensions exist only inside the free-text description
   (`Single-Flush:0762 x 2032mm`). The `0762 = leaf width in mm` reading is a Revit family-naming
   convention, **not stated by the source**.

**Usable for**: per-room area and perimeter as a `DERIVED` cross-check; door and window
width × height as stated opening dimensions (P6/P7), and therefore opening areas (P9).
**Not usable for**: wall paintable area (no height), any accuracy claim, any finish quantity.

---

## 2. Medical-Dental Clinic — `medical-dental-clinic/`

**Source**: same repository, folder `IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic`.

**Licence**: the same CC BY 4.0 grant, quoted verbatim in that folder's `README.md`, with the
attribution string **BSI (2020) "Medical-Dental Test Files," buildingSMART International** and the
same four clauses. **Changes made**: extracted the `Space` sheet to CSV; no value altered.

**Provenance**: provided to the US Construction Engineering Research Laboratory, hosted by NIBS
2010–2020, used as the second common test model in the US "COBie Challenge" events. Grade
**`DERIVED`**, for the same reason as the Duplex.

| File | Contents |
|---|---|
| `spaces.csv` | 269 spaces: `GrossArea`, `NetArea` (m²), `UsableHeight` (mm), floor, room description |

**Why this one was acquired despite not being residential**: it is the only cleanly licensed source
found that states a **per-room height**. Measured: `UsableHeight` is populated for **236 of 269**
spaces — 2400 mm (199), 2700 mm (16), 2600 mm (16), 3000 mm (2), 2740 mm (2), 3350 mm (1) — with
`n/a` on 26 and `0` on 7. That is P8 *stated by the source*, which is the field the contract cannot
infer and which nothing else public supplies per room.

**Usable for**: per-room height as a stated input with provenance (P8); per-room area as a
`DERIVED` cross-check. **Not usable for**: anything residential-specific, and any accuracy claim.

**Note on the accompanying drawings**: a 316-sheet redacted construction set for this building —
including door, finish and window schedules authored by the original design team, which would be
genuinely independent of the model — is hosted on WBDG at
`wbdg.org/FFC/BIM/LCie/Clinic Model/2012-03-27-ClinicDrawingsRedacted.zip`. **Its licence is
UNSTATED** and the WBDG footer asserts all rights reserved, so it was **not acquired**. Only the
CC BY 4.0 COBie data is here.

---

## 3. What is deliberately absent

**No reference quantity for flooring, ceiling paint, baseboard or wall paint, for any building.**
That is not an omission in this directory — §6 of the report records that no public, licensed source
states one, which is the finding that decides the verdict.
