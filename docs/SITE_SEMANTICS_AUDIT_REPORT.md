# SITE_SEMANTICS_AUDIT_REPORT

```
SITE_CORRECTNESS_STATUS    = NEEDS_FIX
ROOM_PROGRAM_EXTENSIBILITY = NEEDS_EXTENSION
STATUS                     = audit only, no code changed
```

The defect is not a wrong number. It is a **reversed derivation**: the demo path computes the site
*from* the building instead of the building *from* the site, so the plot is an output of planning
rather than a constraint on it. Under that direction, land can only ever be created.

---

## 1 · What each field means today

| Field | Meaning | Who reads it on the demo path |
|---|---|---|
| `Project.plot_area_m2` | the parcel area the person entered | **nobody** — see §2 |
| `Project.built_area_m2` | TARGET BUILT AREA; sizes the footprint presets and the generator's area target | `footprint.ts`, `spec_for`, `ProgramSpec.target_built_area_m2` |
| `Project.selected_footprint` | the chosen building outline, width × depth × polygon | `spec_for` → **becomes the buildable region exactly** |
| `SiteSpec` (`app/architect/models.py`) | width × depth, documented *"informational only, not a room-placement boundary"* | not on the demo path at all (legacy `app/design` only) |
| `BuildableRegion` | authoritative geometry with provenance; the planner's only notion of usable land | built in `service._buildable_from` from the footprint rectangle |
| `FRONT/SIDE/REAR_SETBACK_M` | 5.5 / 3.0 / 4.0, module constants in `app/demo/requirements_view.py` | `spec_for`, to build a plot **around** the footprint |

The `BuildableRegion` is stamped `Provenance(Source.USER, Authority.ASSUMED, ref="selected building
footprint")` — so the provenance system already records that this land is **assumed**, not
authoritative. The information was there; nothing acted on it.

## 2 · Where the real plot stops affecting planning

**At the schema boundary.** `plot_area_m2` has exactly one consumer on the demo path:

```python
# app/projects/models.py:127
def _check_built_area_fits_plot(plot_area_m2, built_area_m2):
    if built_area_m2 >= plot_area_m2:
        raise ValueError("built_area_m2 must be smaller than plot_area_m2")
```

After that single comparison it is never read again. `spec_for` does not reference it.
`_buildable_from` does not reference it. No stage of the pipeline knows it exists. (On the *legacy*
`app/design` path it does survive, as a square site `sqrt(plot_area_m2)` — a different placeholder,
also not a containment boundary.)

## 3 · Why `spec_for` synthesizes a larger site

Because the demo path made the **footprint** authoritative, and then still needed somewhere to put
the parking, the entrance walk and the garden:

```python
# app/demo/requirements_view.py:234
plot=PlotSpec(
    width_m=footprint.width_m + 2 * SIDE_SETBACK_M,
    depth_m=footprint.depth_m + FRONT_SETBACK_M + REAR_SETBACK_M,
    ...)
```

That is the honest relationship run backwards. It should be

```
plot (authoritative)  −  setbacks  →  buildable region  →  footprint must fit inside
```

and it is currently

```
footprint (authoritative)  +  setbacks  →  plot (invented)
```

With `+`, the site grows to whatever the building needs and the parcel can never be the binding
constraint. The reported case: a 220 m² BALANCED footprint is 17.23 × 12.77, which with these
setbacks demands **23.23 × 22.27 = 517 m²** — on a plot the person said was **300 m²**. The plan was
laid out on 1.7× the land they own.

## 4 · Are 5.5 / 4 / 3 authoritative?

**Explicit demo assumptions, and the code already says so:**

> `#: PARAMETER, not a regulation figure.`

They are not sourced from any municipal plan, not user-supplied, and not shown to the user anywhere.
The problem is not their *values* — it is their **role**. They are used as a derivation rule
(generate a plot) when the only correct use is as a constraint (subtract from a plot). Even a
perfectly regulated setback figure would be wrong used that way.

## 5 · Tests depending on those constants

Narrow, and less than expected:

- `tests/vertical_slice/test_concept_generator.py` — 9 explicit `PlotSpec(..., front_setback_m=5.5, side_setback_m=3.0, rear_setback_m=4.0)` constructions.
- `tests/test_demo_p0.py` — every case declares `plot_area_m2: 500.0` and then picks a footprint. Checked against a real containment rule:

| case | footprint | plot it would need | vs the declared 500 m² |
|---|---|---|---|
| A_2BR | 11.0 × 12.0 | 17.0 × 21.5 = 366 | ok |
| B_2BR_SAFE | 12.0 × 13.0 | 18.0 × 22.5 = 405 | ok |
| C_3BR_SAFE_OPEN | 12.5 × 14.5 | 18.5 × 24.0 = 444 | ok |
| D_3BR_THREE_WET | 13.0 × 15.0 | 19.0 × 24.5 = 466 | ok |
| corridor / relationships | 14.14 × 14.14 | 20.1 × 23.6 = 476 | ok |
| corridor default | 15.5 × 15.5 | 21.5 × 25.0 = 538 | **exceeds** |

**One of seven** is already impossible on its own declared numbers. A real containment gate is
therefore cheap to introduce: one test fixture needs a bigger plot, not a redesign.

## 6 · Can a plot AREA alone determine whether a footprint fits?

**No. Area is a scalar; fit is a two-dimensional containment question.** An 11 × 10 footprint needs
17.0 × 19.5 m of plot with these setbacks. Holding the area at 400 m² and varying only the shape:

| plot | area | fits? |
|---|---|---|
| 20.0 × 20.0 | 400 m² | **fits** |
| 25.0 × 16.0 | 400 m² | does not fit (16 < 19.5 deep) |
| 16.0 × 25.0 | 400 m² | does not fit (16 < 17.0 wide) |
| 40.0 × 10.0 | 400 m² | does not fit |

Same area, four different answers. And there is a second reason area cannot decide it: setbacks are
**edge-relative** — front, rear and side are different numbers — so the answer also depends on
**which edge faces the street**, which an area cannot express either.

`built_area_m2 < plot_area_m2` is therefore not a weak check. It is a check of the wrong quantity:
it can pass for a plot that cannot hold the building, and it would fail for a perfectly buildable
long narrow parcel.

## 7 · Minimum site information for a mathematically honest demo

For a rectangular parcel, three facts and no more:

1. **plot width (m)**
2. **plot depth (m)**
3. **which edge faces the street** (the front, since the setbacks are asymmetric)

That is sufficient to derive a buildable rectangle by subtraction and to answer containment exactly.
Everything richer — a real polygon, corner plots, orientation, coverage ratios, GIS parcel lookup —
is beyond an honest P0 and is not needed to stop inventing land.

Area may stay as a convenience input, but it must not be the planning quantity.

## 8 · What setbacks should be until regulation exists

**Explicit demo assumptions, shown to the user, and overridable — never UNKNOWN, never silent.**

| Option | Verdict |
|---|---|
| stay hard-coded and silent | **no** — this is today's defect |
| `UNKNOWN` | **no** — nothing could be planned at all, and the geometry domain's `UNKNOWN` is for genuinely unknown *geometry*, not for a parameter we have chosen |
| user-supplied, required | **no** for P0 — most people do not know their setbacks, and demanding them blocks the demo |
| **stated defaults, visible on the review screen, editable** | **yes** — honest about their status, usable without knowing them, and ready to be replaced by a regulation source later without changing any caller |

The essential change is not which value they hold. It is that they must be **subtracted from a
supplied plot**, never used to conjure one.

## 9 · The invariant

> **The planner may only use land that the authoritative site geometry supplied to it actually
> contains.**
>
> Every buildable region is derived from that geometry by **subtraction** — setbacks, exclusions,
> obstacles — and never by addition. No stage may enlarge, pad or synthesize a site in order to make
> a programme fit. When the programme does not fit the land supplied, that is a refusal, not a
> licence to widen the land.

This is the site-level twin of the adapter's existing rule — *"may lose usable area, but must never
create area that does not exist"* — which the adapter enforces below the buildable region while
nothing enforced it above.

## 10 · Smallest P0 correction

Four steps, no GIS and no regulation:

1. **Collect plot width and depth** at the project form, alongside (or instead of) area. Two number
   fields; the existing area field can be derived and shown.
2. **Invert `spec_for`.** Build `PlotSpec` from the supplied plot, and derive the buildable rectangle
   by subtracting the setbacks — the direction §3 says it should already have.
3. **Gate the footprint step on containment.** A preset or custom footprint that does not fit inside
   the buildable rectangle is not offered / not accepted, with a message naming both dimensions.
   This also removes the confusing case where the *area* check passes and planning then fails.
4. **Show the setbacks on the review screen** as the stated assumptions they are.

Cost is contained: one test fixture (§5), `spec_for`, the form, and the footprint step. No change to
Geometry Core, the adapter, the concept generator or validation — the buildable region they consume
keeps exactly the same type and meaning, and only becomes honest about where it came from.

---

## Room programme extensibility — `NEEDS_EXTENSION`

**The current model cannot absorb an OFFICE without a one-off change in six places.**

`ProgramRole` is a closed enum of ten members, and adding one requires edits in: the enum,
`ROOM_TEMPLATES`, `build_room_program`, `DAYLIGHT_ROLES` (windows), `_ROOM_NAMES` (the demo
contract), and `relationships._ROLE_TOKENS` / `_ROOM_WORDS`. Role references are spread across
30 sites in `concept_generator.py` alone.

Worse, the **shape** of `ProgramSpec` is per-room-kind:

```python
bedrooms: int = 3
safe_room: bool = True
wet_rooms: int = 2
```

One named scalar field per kind of room. Every new room type needs a new field, a new parser rule, a
new review row, and a new scope check. That is the "one-off parser hack forever" the task names, and
it is structural, not a matter of discipline.

**The shape it wants instead** — a room programme as *data*:

```
ProgramSpec.rooms: tuple[RequestedRoom, ...]      # (role, count, optional attributes)
```

with `ROOM_TEMPLATES` as the **registry** that decides plannability: a role with a template can be
planned; a role without one is reported as an unsupported room type through the machinery that
already exists. Adding OFFICE then costs one enum value, one template row and one display name —
and no parser rule at all, because the parser would emit a role rather than fill a named field.

Two things already point this way and should be reused rather than reinvented:
`app/architect/models.py` already defines `ConstraintKind.required_room` with a `RequirementState`
distinguishing UNKNOWN from ZERO; and `other_requests` already carries and grades room types we
cannot plan, so the refusal path for an unsupported role exists today.

This is a real but *separate* piece of work. It is a capability gap; the site issue is a correctness
bug.

---

## Recommended next task — exactly one

**`IMPLEMENT_AUTHORITATIVE_SITE_GEOMETRY_P0`** — §10, steps 1–4.

Chosen over the room-programme extension because it is the one that is currently **wrong** rather
than merely limited: today the planner lays out houses on land the person does not own, and every
downstream guarantee we have built — the safe adapter's "never create area", the built-area target,
the corridor and relationship feasibility refusals — is computed against a site that was invented.
Those guarantees are only as sound as the region they are measured in.

The room-programme extension should follow it, not precede it.

Stopping for review. Nothing implemented.
