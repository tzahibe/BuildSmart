"""Generator-level pattern compilers (Issue #79, Concept Engine v2 5/5).

One interface, `compile(pattern, spec, outline) -> list[ConceptCandidate]`:

    SPINE, FRONT_BAND, TWO_WING   wrap `concept_generator.generate_concepts`'s own existing
                                  builders (`_build`/`_allocations`, `_front_band_concept`,
                                  `l_parti.l_concepts`) for the given outline, filtered to the
                                  pattern's own declared `circulation_class` — never a second
                                  generator path, never new geometry beyond what the generator
                                  already tries for that outline.
    HUB_LOBBY                    `compile_hub_lobby` — a NEW hand-authored tree, not
                                  `concept_generator._hub_concept`'s 005-template builder. Measured
                                  (this Issue, over the frozen 432-context corpus and a further
                                  ~550-combination synthetic sweep of widths/depths/bedrooms/wet-
                                  rooms/targets): `_hub_concept` — and `hub_bound`'s own witness
                                  search called directly, bypassing `_hub_concept` entirely — finds
                                  ZERO sizings that clear the §6 gates anywhere in that space. This
                                  is not this Issue's own regression: `tests/vertical_slice/
                                  test_concept_generator.py`'s `HUB_VS_HARD_MAXIMA` (`strict=True`
                                  xfail) already documents it — "Phase 1 of the room-size work
                                  (2026-09-15) made every template `max_area_m2` HARD... no hub
                                  sizing passes the §6 gates on these outlines" — as one of three
                                  undecided owner options ("relax the hub gates, raise BEDROOM/
                                  SAFE_ROOM maxima ... or accept the hub as rarely eligible").
                                  `compile_hub_lobby` is the "accept it, and still prove the class
                                  is reachable and honestly verified" answer: a hand-sized tree
                                  (compact lobby with rooms on 4-5 sides, the shared wet room at
                                  its head), calibrated to and VERIFIED against the real solver and
                                  every validator — never past a ROOM_TEMPLATES bound, so nothing
                                  here is a hard-limit relaxation — for 2 bedrooms/2 wet rooms
                                  (`_hub_lobby_unsupported`), WITH a SAFE_ROOM-aware variant and an
                                  open-plan-aware variant, independently combinable (lead direction
                                  after attempt 2, 2026-09-22: SAFE_ROOM/open-plan are the norm in
                                  this product, not the exception the original single shape
                                  covered). Because `patterns_for` still routinely NAMES
                                  `HUB_LOBBY` for common footprint families (the 21-plan census
                                  prior this Issue's own wiki page cites), `concept_engine_v2`
                                  tries this compiler on every brief that pattern is offered for —
                                  it simply returns `[]` wherever the programme does not match, at
                                  the cost of one cheap shape check, never a second generator call.
    BRANCHED                     `compile_branched` — a NEW hand-authored tree: two HALL zones,
                                  HALL_A (a corridor under the public band) and HALL_B (a corridor
                                  beside the bedroom stack), in adjacent but NOT sibling subtrees,
                                  meeting at a corner over a PARTIAL shared edge and joined by a
                                  declared CASED_OPENING edge — never an OPEN_CONNECTION
                                  (`geometry_core.engine._mark_open_interfaces` requires an open
                                  group's leaves to be siblings with a FULL matching edge, which a
                                  genuinely bent corridor never has; the seam-level wall-opening
                                  precedent this Issue points at is `app.demo.contract
                                  ._open_corridor_to_public`, which this module does not touch —
                                  see its own docstring for why the plain CASED_OPENING alone
                                  already satisfies C5/C14/C24 without it). Supported for the
                                  programme shape the canonical fixture and AC-2's test use — 4
                                  bedrooms (a master plus three), 2 wet rooms (the master's ensuite
                                  plus one shared bathroom), no FLEX/laundry — WITH a SAFE_ROOM-
                                  aware variant (3 bedrooms, not 4 — the safe room takes the third
                                  bedroom-class slot in the stack) and an open-plan-aware variant,
                                  independently combinable (attempt 3, same lead direction);
                                  declines (empty list) otherwise; see `compile_branched`'s own
                                  docstring for why a general arbitrary-programme version, or a
                                  4-bedroom-plus-safe-room shape, is out of scope here.

Every emitted `ConceptCandidate` already carries `circulation_class` (`_hub_concept`/`_build`/
etc. set it themselves, unchanged since Issue #75; `compile_branched` sets it explicitly here);
`concept_spec.realized_circulation_class` (extended by this Issue to recognise the BRANCHED
pattern this module is the first ever to produce) verifies it on the SOLVED geometry, and the
caller (`concept_engine_v2.plans_per_class`/`plans_per_class_cross_outline`) drops a candidate
whose realized class disagrees — this module never re-labels a candidate to make it match.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import concept_generator as cg
from .concept import Concept
from .concept_spec import CirculationClass
from .geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Rect,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)
from .wet_rooms import resolve_wet_rooms

if TYPE_CHECKING:
    from .concept_generator import ConceptCandidate, ConceptRejection
    from .concept_patterns import Pattern
    from .safe_adapter import SolverGeometryCandidate
    from .spec import ArchitecturalSpec


def compile(pattern: "Pattern", spec: "ArchitecturalSpec",
           outline: "tuple[SolverGeometryCandidate, ...]") -> "list[ConceptCandidate]":
    """The candidates `pattern`'s own `circulation_class` names, for this one outline.

    `outline` is the safe-geometry candidates ONE surveyed outline offers
    (`safe_adapter.adapt(buildable).candidates`) — plural because TWO_WING needs a pair of
    adjacent wings, exactly what `concept_generator.generate_concepts` already reads from this
    same list for every other class.
    """
    if not outline:
        return []
    circulation_class = pattern.circulation_class
    if circulation_class is CirculationClass.HUB_LOBBY:
        return compile_hub_lobby(spec, outline[0].rect)
    if circulation_class is CirculationClass.BRANCHED:
        return compile_branched(spec, outline[0].rect)
    generated = cg.generate_concepts(spec, list(outline))
    return [c for c in generated.candidates if c.circulation_class is circulation_class]


# --------------------------------------------------------------------------- HUB_LOBBY

#: The exact programme shape `compile_hub_lobby` supports — see the module docstring for why. 2
#: bedrooms (a master plus one), 2 wet rooms (the master's ensuite plus one shared bathroom, the
#: `resolve_wet_rooms` default for this exact combination). `safe_room`/`open_plan_living` are
#: BOTH supported (lead direction, 2026-09-22, attempt 3): a SAFE_ROOM row and/or an open-plan
#: LIVING/KITCHEN group, see `compile_hub_lobby`'s own docstring for how each changes the tree.
_HUB_LOBBY_BEDROOMS = 2
_HUB_LOBBY_WET_ROOMS = 2

#: Gross metres, hand-calibrated and verified against the real solver + every validator (C1-C29),
#: never past a `concept_generator.ROOM_TEMPLATES` bound — see the module docstring. `MASTER_W`
#: is the west column's width (MASTER over BATH_1, its ensuite); `LOBBY_W`/`BEDROOM1_W` the lobby
#: and its east flank; `MD`/`BD1` and `HD`/`FD` the two columns' own row depths — chosen so
#: `MD + BD1 == HD + FD` (both columns share the row-3 V-split's height), the same "force one
#: side, size the sibling to match" discipline `compile_branched` uses. `open_plan_living` never
#: changes any of these dimensions — it only changes the LIVING-KITCHEN access edge/open_groups
#: below, never the geometry (verified: widening/narrowing either room independently was never
#: needed to keep both in their own band once they share one open block).
_MASTER_W_M = 3.8
_MD_M = 3.4
_BD1_M = 2.3
_LOBBY_W_M = 3.0
_BEDROOM1_W_M = 3.4
_HD_M = 3.4
_FD_M = 2.3
_PB_M = 4.5

#: The SAFE_ROOM variant needs its OWN south-row split (`south_row`, below) — a taller shared row
#: (`_FD_SAFE_M`, up from `_FD_M`) so SAFE_ROOM's RC-walled net short side clears its 2.4 m floor,
#: a wider hall column (`_LOBBY_W_SAFE_M`, up from `_LOBBY_W_M`) so BOTH BATH_2's own sliver
#: (`_BATH2_SLIVER_M`) and SAFE_ROOM's own remainder each keep a real (>=0.9 m) shared edge with
#: HALL, and a narrower/deeper west column (`_MASTER_W_SAFE_M`/`_MD_SAFE_M`, so MASTER stays
#: within its own band at the new row height) — every number here was found empirically against
#: the real solver (`leaf_shapes`'s net-of-RC-inset shape curve), not derived from a formula; see
#: the module docstring for why a general arbitrary-programme search is out of scope.
_MASTER_W_SAFE_M = 3.5
_MD_SAFE_M = 3.6
_LOBBY_W_SAFE_M = 3.5
_HD_SAFE_M = 3.6
_BATH2_SLIVER_M = 2.2
_FD_SAFE_M = 2.9


def _hub_lobby_unsupported(spec: "ArchitecturalSpec") -> str | None:
    program = spec.program
    if program.bedrooms != _HUB_LOBBY_BEDROOMS:
        return f"compile_hub_lobby supports exactly {_HUB_LOBBY_BEDROOMS} bedrooms, not {program.bedrooms}"
    if program.wet_rooms != _HUB_LOBBY_WET_ROOMS:
        return f"compile_hub_lobby supports exactly {_HUB_LOBBY_WET_ROOMS} wet rooms, not {program.wet_rooms}"
    return None


def compile_hub_lobby(spec: "ArchitecturalSpec", candidate: Rect) -> "list[ConceptCandidate]":
    """The HUB_LOBBY parti: a compact lobby (aspect well under the 1.5 gate) with the public band
    on its north side (a CASED_OPENING), MASTER on its west flank, BEDROOM_1 on its east flank,
    and the shared wet room (BATH_2, "the shared wet rooms at its head") directly on its south
    side. Without a safe room that is 4 doors, rooms on 4 sides — the original (Issue #79 attempt
    2) shape. WITH one (`spec.program.safe_room`, attempt 3), the south row splits in two
    (`south_row`): BATH_2 keeps a real door-width slice of HALL's own width, and SAFE_ROOM takes
    the rest of that row PLUS all of BEDROOM_1's width, so it borders HALL directly (never through
    a bedroom — `access_rules.ALLOWED_ENTERED_FROM`) and reaches the EAST exterior wall in the
    same row (`exposure_policy`'s REQUIRED exterior+window for `ProgramRole.SAFE_ROOM`) — 5 doors,
    rooms on 5 sides. `spec.program.open_plan_living` (independently) only changes the LIVING-
    KITCHEN edge from DOOR to OPEN_CONNECTION plus `open_groups`; it never touches the tree. See
    the module docstring for why this is a hand-sized tree rather than
    `concept_generator._hub_concept`'s own (measured-broken) builder, and `_hub_lobby_unsupported`
    for the programme shape(s) it serves.
    """
    if _hub_lobby_unsupported(spec) is not None:
        return []
    has_safe = spec.program.safe_room
    open_plan = spec.program.open_plan_living
    master_w = _MASTER_W_SAFE_M if has_safe else _MASTER_W_M
    md = _MD_SAFE_M if has_safe else _MD_M
    lobby_w = _LOBBY_W_SAFE_M if has_safe else _LOBBY_W_M
    hd = _HD_SAFE_M if has_safe else _HD_M
    fd = _FD_SAFE_M if has_safe else _FD_M
    bd1 = fd  # invariant: md + bd1 == hd + fd, always bd1 == fd since md == hd in both variants

    max_w_m, max_h_m = cg.u_to_m(candidate.w), cg.u_to_m(candidate.h)
    east_w = lobby_w + _BEDROOM1_W_M
    total_w = master_w + east_w
    total_h = _PB_M + hd + fd
    if total_w > max_w_m + 1e-9 or total_h > max_h_m + 1e-9:
        return []

    def z(zid: str, roles: tuple[ProgramRole, ...], lo: float, target: float, hi: float,
          short: float, aspect: float = 2.5) -> ZoneSpec:
        return ZoneSpec(zid, roles, lo, target, hi, short, aspect)

    zones = [
        z("LIVING", (ProgramRole.LIVING,), 16, 22, 46, 3.0),
        z("KITCHEN", (ProgramRole.KITCHEN,), 9, 13, 26, 2.4, aspect=3.0),
        z("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 5, 8, 16, 1.2, aspect=1.5),
        z("MASTER", (ProgramRole.MASTER_BEDROOM,), 11, 14, 20, 3.0),
        z("BATH_1", (ProgramRole.BATHROOM,), 4.5, 6.5, 12, 1.6, aspect=3.0),
        z("BEDROOM_1", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
        z("BATH_2", (ProgramRole.BATHROOM,), 4.5, 6.5, 14, 1.6, aspect=3.0),
    ]
    if has_safe:
        zones.append(z("SAFE_ROOM", (ProgramRole.SAFE_ROOM,), 9.0, 10.5, 14.0, 2.4, aspect=2.5))

    def v(a, b, fixed_m: float | None) -> Split:
        return Split(Cut.V, a, b, m_to_u(fixed_m) if fixed_m is not None else None)

    def h(a, b, fixed_m: float | None) -> Split:
        return Split(Cut.H, a, b, m_to_u(fixed_m) if fixed_m is not None else None)

    L = Leaf
    living_w = round(total_w * (22.0 / (22.0 + 13.0)) / 0.05) * 0.05
    top = v(L("LIVING"), L("KITCHEN"), fixed_m=living_w)
    west_col = h(L("MASTER"), L("BATH_1"), fixed_m=md)
    hub_east = v(L("HALL"), L("BEDROOM_1"), fixed_m=lobby_w)
    if has_safe:
        south_row = v(L("BATH_2"), L("SAFE_ROOM"), fixed_m=_BATH2_SLIVER_M)
        east_part = h(hub_east, south_row, fixed_m=hd)
    else:
        east_part = h(hub_east, L("BATH_2"), fixed_m=hd)
    bottom = v(west_col, east_part, fixed_m=master_w)
    tree = h(top, bottom, fixed_m=_PB_M)

    footprint = cg.footprint_of(candidate, total_w, total_h)
    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    living_kitchen_kind = ConnectionKind.OPEN_CONNECTION if open_plan else ConnectionKind.DOOR
    edges = [
        DesiredAccessEdge("HALL", "LIVING", ConnectionKind.CASED_OPENING),
        DesiredAccessEdge("LIVING", "KITCHEN", living_kitchen_kind),
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH_2", ConnectionKind.DOOR),
    ]
    if has_safe:
        edges.append(DesiredAccessEdge("HALL", "SAFE_ROOM", ConnectionKind.DOOR))
    access = DesiredAccessTopology(tuple(edges))
    open_groups = (("LIVING", "KITCHEN"),) if open_plan else ()
    fixture = Fixture("GEN_HUB_LOBBY", (wing,), tuple(zones), access, open_groups=open_groups)
    concept = Concept(fixture, "HALL", Side.N, cg.u_to_m(footprint.w), cg.u_to_m(footprint.h))
    wet_rooms = resolve_wet_rooms(spec.program)
    rationale = "hand-sized compact lobby: rooms on 4 sides, the shared bathroom at its head"
    if has_safe:
        rationale = ("hand-sized compact lobby with a safe room: rooms on 5 sides, the safe room "
                    "and the shared bathroom both reached from the lobby directly")
    candidate_out = cg.ConceptCandidate(
        concept, cg.ConceptStrategy.HUB_PRIVATE_WING, (0,),
        circulation_class=CirculationClass.HUB_LOBBY,
        rationale=f"{rationale} (Issue #79)",
        used_area_m2=round(cg.u_to_m(footprint.w) * cg.u_to_m(footprint.h), 2),
        unused_wing_area_m2=round(candidate.area_m2() - cg.u_to_m(footprint.w) * cg.u_to_m(footprint.h), 2),
        wet_rooms=wet_rooms,
    )
    return [candidate_out]


# --------------------------------------------------------------------------- BRANCHED

#: The programme shapes `compile_branched` supports — see its own docstring. Without a safe room:
#: a master bedroom plus three more (matches AC-2's canonical fixture), one ensuite and one shared
#: bathroom. WITH one (`spec.program.safe_room`, attempt 3): a master plus TWO more (not three) —
#: the safe room takes the third bedroom-class slot in the stack, keeping the stack's own room
#: count (and so its total depth requirement) identical to the no-safe-room case; see
#: `compile_branched`'s own docstring for why 4 bedrooms + a safe room (5 stacked private rooms)
#: does not fit this hand-authored tree's depth budget.
_BRANCHED_BEDROOMS_NO_SAFE = 4
_BRANCHED_BEDROOMS_WITH_SAFE = 3
_BRANCHED_WET_ROOMS = 2

#: Gross metres, hand-calibrated and verified against the real solver + validator (never derived
#: from a formula — see the module docstring for why a general arbitrary-programme version is out
#: of scope). `MW`/`HB_W`/`EW` are the row-3 column widths (master wing | HALL_B | bedroom wing);
#: `PB`/`HA` the public band and HALL_A's own depth; `MASTER_D`/`BATH1_D` the forced master-wing
#: rows. The bedroom wing's own rows (`BEDROOM_1/2[/3]` + `BATH_2`[+`SAFE_ROOM`]) are UNFORCED
#: (`fixed_m=None`) so the solver sizes them to whatever depth `MASTER_D + BATH1_D` actually is —
#: the same "force one side, leave the other's internal seams to the solver" discipline
#: `concept.py`'s own `back_chain` uses, and the reason this fixture needs no per-programme search
#: at all. `_BATH1_D_SAFE_M` (up from `_BATH1_D_M`) gives the safe-room stack the extra depth
#: budget its RC-walled 2.4 m short-side floor needs, found empirically against the real solver;
#: `open_plan_living` never changes any of these — same reasoning as `compile_hub_lobby`.
_MW_M = 3.2
_HB_W_M = 1.6
_EW_M = 4.0
_PB_M = 4.5
_HA_M = 1.6
_MASTER_D_M = 6.5
_BATH1_D_M = 3.5
_BATH1_D_SAFE_M = 4.0


def _branched_unsupported(spec: "ArchitecturalSpec") -> str | None:
    program = spec.program
    expected_bedrooms = _BRANCHED_BEDROOMS_WITH_SAFE if program.safe_room else _BRANCHED_BEDROOMS_NO_SAFE
    if program.bedrooms != expected_bedrooms:
        return (f"compile_branched supports exactly {expected_bedrooms} bedrooms "
               f"{'with' if program.safe_room else 'without'} a safe room, not {program.bedrooms}")
    if program.wet_rooms != _BRANCHED_WET_ROOMS:
        return f"compile_branched supports exactly {_BRANCHED_WET_ROOMS} wet rooms, not {program.wet_rooms}"
    return None


def compile_branched(spec: "ArchitecturalSpec", candidate: Rect) -> "list[ConceptCandidate]":
    """The BRANCHED parti: HALL_A (public-facing, under LIVING/KITCHEN) meets HALL_B (serving the
    bedroom wing) at a corner, over a partial shared edge, joined by a CASED_OPENING — never an
    OPEN_CONNECTION (see the module docstring). Every bedroom's door sits on one of the two hall
    segments: MASTER on HALL_A, the rest of the stack on HALL_B.

    Without a safe room (attempt 2): BEDROOM_1/2/3 + BATH_2 stack off HALL_B. WITH one
    (`spec.program.safe_room`, attempt 3): SAFE_ROOM takes the third bedroom-class slot instead of
    BEDROOM_3 — `_BRANCHED_BEDROOMS_WITH_SAFE` (3, not 4) is the precondition for this — so the
    stack still has 4 members and needs no more depth than the no-safe-room case beyond
    `_BATH1_D_SAFE_M`'s own small increase; SAFE_ROOM reaches HALL_B directly (never through a
    bedroom) and the EAST exterior wall the same way every stack member already does (the stack is
    the building's own east edge). A 4-bedroom-plus-safe-room programme (5 stacked private rooms)
    was measured infeasible at this tree's own depth budget even after widening every lever that
    does not itself break MASTER/BATH_1's own `RoomTemplate` bands — named as a follow-up, not
    attempted here (see the module docstring for why a general search is separately out of scope).

    `spec.program.open_plan_living` (independently, like `compile_hub_lobby`) only changes the
    LIVING-KITCHEN edge/`open_groups`; it never touches the tree.

    Declines (empty list, not an exception) for any other programme, exactly like every other
    builder in this module declines a programme it cannot serve.
    """
    if _branched_unsupported(spec) is not None:
        return []
    has_safe = spec.program.safe_room
    open_plan = spec.program.open_plan_living
    bath1_d = _BATH1_D_SAFE_M if has_safe else _BATH1_D_M

    max_w_m, max_h_m = cg.u_to_m(candidate.w), cg.u_to_m(candidate.h)
    total_w = _MW_M + _HB_W_M + _EW_M
    total_h = _PB_M + _HA_M + _MASTER_D_M + bath1_d
    if total_w > max_w_m + 1e-9 or total_h > max_h_m + 1e-9:
        return []

    def z(zid: str, roles: tuple[ProgramRole, ...], lo: float, target: float, hi: float,
          short: float, aspect: float = 2.5) -> ZoneSpec:
        return ZoneSpec(zid, roles, lo, target, hi, short, aspect)

    zones = [
        z("LIVING", (ProgramRole.LIVING,), 16, 22, 46, 3.0),
        z("KITCHEN", (ProgramRole.KITCHEN,), 9, 13, 26, 2.4, aspect=3.0),
        z("HALL_A", (ProgramRole.HALL, ProgramRole.CIRCULATION), 4, 8, 30, 1.2, aspect=8.0),
        z("HALL_B", (ProgramRole.HALL, ProgramRole.CIRCULATION), 4, 8, 30, 1.2, aspect=8.0),
        z("MASTER", (ProgramRole.MASTER_BEDROOM,), 11, 14, 20, 3.0),
        z("BATH_1", (ProgramRole.BATHROOM,), 4.5, 6.5, 12, 1.6, aspect=3.0),
        z("BEDROOM_1", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
        z("BEDROOM_2", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
        z("BATH_2", (ProgramRole.BATHROOM,), 4.5, 6.5, 12, 1.6, aspect=3.0),
    ]
    if has_safe:
        zones.append(z("SAFE_ROOM", (ProgramRole.SAFE_ROOM,), 9.0, 10.5, 14.0, 2.4, aspect=2.5))
    else:
        zones.append(z("BEDROOM_3", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6))

    def v(a, b, fixed_m: float | None) -> Split:
        return Split(Cut.V, a, b, m_to_u(fixed_m) if fixed_m is not None else None)

    def h(a, b, fixed_m: float | None) -> Split:
        return Split(Cut.H, a, b, m_to_u(fixed_m) if fixed_m is not None else None)

    L = Leaf
    living_w = round(total_w * (22.0 / (22.0 + 13.0)) / 0.05) * 0.05
    top = v(L("LIVING"), L("KITCHEN"), fixed_m=living_w)
    west = h(L("MASTER"), L("BATH_1"), fixed_m=_MASTER_D_M)
    third_slot = L("SAFE_ROOM") if has_safe else L("BEDROOM_3")
    east_stack = h(L("BEDROOM_1"),
                   h(L("BEDROOM_2"), h(third_slot, L("BATH_2"), fixed_m=None), fixed_m=None),
                   fixed_m=None)
    middle = v(L("HALL_B"), east_stack, fixed_m=_HB_W_M)
    row3 = v(west, middle, fixed_m=_MW_M)
    lower = h(L("HALL_A"), row3, fixed_m=_HA_M)
    tree = h(top, lower, fixed_m=_PB_M)

    footprint = cg.footprint_of(candidate, total_w, total_h)
    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    living_kitchen_kind = ConnectionKind.OPEN_CONNECTION if open_plan else ConnectionKind.DOOR
    third_id = "SAFE_ROOM" if has_safe else "BEDROOM_3"
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL_A", "LIVING", ConnectionKind.CASED_OPENING),
        DesiredAccessEdge("LIVING", "KITCHEN", living_kitchen_kind),
        DesiredAccessEdge("HALL_A", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_A", "HALL_B", ConnectionKind.CASED_OPENING),
        DesiredAccessEdge("HALL_B", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_B", "BEDROOM_2", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_B", third_id, ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_B", "BATH_2", ConnectionKind.DOOR),
    ))
    open_groups = (("LIVING", "KITCHEN"),) if open_plan else ()
    fixture = Fixture("GEN_BRANCHED", (wing,), tuple(zones), access, open_groups=open_groups)
    concept = Concept(fixture, "HALL_A", Side.N, cg.u_to_m(footprint.w), cg.u_to_m(footprint.h))
    wet_rooms = resolve_wet_rooms(spec.program)
    rationale = ("branched hall: HALL_A under the public band meets HALL_B beside the bedroom "
                "wing at a corner, joined by a cased opening")
    if has_safe:
        rationale += "; the safe room stacks with the bedrooms off HALL_B"
    candidate_out = cg.ConceptCandidate(
        concept, cg.ConceptStrategy.BRANCHED_TWO_STACK, (0,),
        circulation_class=CirculationClass.BRANCHED,
        rationale=f"{rationale} (Issue #79)",
        used_area_m2=round(cg.u_to_m(footprint.w) * cg.u_to_m(footprint.h), 2),
        unused_wing_area_m2=round(candidate.area_m2() - cg.u_to_m(footprint.w) * cg.u_to_m(footprint.h), 2),
        wet_rooms=wet_rooms,
    )
    return [candidate_out]
