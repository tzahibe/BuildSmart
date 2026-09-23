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
                                  is reachable and honestly verified" answer: a hand-authored TREE
                                  (compact lobby with rooms on 4-5 sides, the shared wet room at
                                  its head) whose SIZING is a bound/witness search over
                                  `concept_generator.ROOM_TEMPLATES` (`_hub_lobby_sizing`, review
                                  follow-up, attempt 5 — see the witness-search section below for
                                  why the earlier hand-calibrated literal table was itself the
                                  finding a review rejected) — never past a ROOM_TEMPLATES bound,
                                  so nothing here is a hard-limit relaxation — for 2 bedrooms/2-or-3
                                  wet rooms (`_hub_lobby_unsupported`), WITH a SAFE_ROOM-aware
                                  variant and an open-plan-aware variant, independently combinable
                                  (lead direction after attempt 2, 2026-09-22: SAFE_ROOM/open-plan
                                  are the norm in this product, not the exception the original
                                  single shape covered), and a third-wet-room (GUEST_WC) variant.
                                  Because `patterns_for` still routinely NAMES
                                  `HUB_LOBBY` for common footprint families (the 21-plan census
                                  prior this Issue's own wiki page cites), `concept_engine_v2`
                                  tries this compiler on every brief that pattern is offered for —
                                  it simply returns `[]` wherever the programme does not match, at
                                  the cost of one cheap shape check, never a second generator call.
    BRANCHED                     `compile_branched` — a NEW hand-authored tree (its own SIZING
                                  likewise a bound/witness search, `_branched_sizing`): two HALL
                                  zones,
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
                                  already satisfies C5/C14/C24 without it). Was supported (attempt
                                  3) for a 4-bedroom/2-wet-room programme (a master plus three, the
                                  master's ensuite plus one shared bathroom, no FLEX/laundry), WITH
                                  a SAFE_ROOM-aware variant (3 bedrooms, the safe room taking the
                                  third bedroom-class slot) and an open-plan-aware variant,
                                  independently combinable. Issue #130 (2026-09-23): C26's
                                  dead-end rule (Issue #36) merged into `main` after this tree was
                                  authored and now refuses it on EVERY one of those shapes — the
                                  tree puts a dead end at each of HALL_A's own two ends and HALL_B's
                                  own south end, 3 over C26's limit of 2, structurally rather than
                                  by sizing — so `compile_branched` now declines UNCONDITIONALLY
                                  (`_BRANCHED_C26_CONFLICT_REASON`); see `compile_branched`'s own
                                  docstring for why a general arbitrary-programme version, a
                                  4-bedroom-plus-safe-room shape, or the retopologizing this C26
                                  conflict would need, is out of scope here.

Every emitted `ConceptCandidate` already carries `circulation_class` (`_hub_concept`/`_build`/
etc. set it themselves, unchanged since Issue #75; `compile_branched` sets it explicitly here);
`concept_spec.realized_circulation_class` (extended by this Issue to recognise the BRANCHED
pattern this module is the first ever to produce) verifies it on the SOLVED geometry, and the
caller (`concept_engine_v2.plans_per_class`/`plans_per_class_cross_outline`) drops a candidate
whose realized class disagrees — this module never re-labels a candidate to make it match.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from . import concept_generator as cg
from .circulation_metrics import EXTREME_DEAD_END_COUNT
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


# --------------------------------------------------------------------------- witness search (008)
#
# `compile_hub_lobby`/`compile_branched` hand-author a TREE (which room touches which, sharing
# which edge) but never a SIZING: every gross width/depth a `Split` fixes is a witness this search
# finds from `concept_generator.ROOM_TEMPLATES` and `room_depth_band_m` — the same calibrated
# shape-and-size rule (min short side, max aspect ratio, [min, max] area) every OTHER planner path
# in this module already holds every row to (`concept_generator.hub_bound`'s own bound/witness
# search is the direct precedent: a bound narrows the feasible sizings, a witness is one point
# inside it). Review follow-up (Issue #79 attempt 5): before this, every gross dimension but the
# wet_rooms==3 GUEST_WC leaf was a hand-picked literal, selected by a `has_safe`/`has_toilet`
# boolean branch rather than computed from the programme's own room templates — eligible for
# exactly the handful of (bedrooms, wet_rooms, safe_room) combinations someone had hand-calibrated
# a table entry for. These three helpers replace every one of those literals with a value the
# search finds and verifies against each room's own template band; a combination the search cannot
# seat inside every room's band returns `None`, and the caller declines (returns `[]`) exactly like
# it already does for a programme shape neither tree serves at all.


def _grid_clamp_m(target: float, lo: float, hi: float) -> float | None:
    """`target` clamped into `[lo, hi]`, rounded to the engine's 0.05 m cut grid WITHOUT ever
    rounding back out of the band — plain `round()` can (a value at `lo` can round DOWN past it):
    the grid point is chosen by rounding the band's own edges inward first (`lo` up, `hi` down),
    then rounding the clamped target to the nearest grid point inside that narrower band. None
    when the band holds no grid point at all."""
    lo_grid = math.ceil(lo / 0.05 - 1e-9) * 0.05
    hi_grid = math.floor(hi / 0.05 + 1e-9) * 0.05
    if lo_grid > hi_grid + 1e-9:
        return None
    return round(min(max(target, lo_grid), hi_grid) / 0.05) * 0.05


#: The LEAST any leaf's own free dimension can lose to its walls — two partition halves — used
#: only to convert a band's own CEILING back to gross (`_witness_band_m`). `_EDGE_INSET_ALLOWANCE_M`
#: ("one exterior half + one partition half") is the right conversion for a FLOOR — using the
#: biggest plausible inset there can only make the gross floor a little taller than strictly
#: needed, never too short — but the same assumption on a CEILING can OVERSHOOT it: a leaf whose
#: own two sides on that dimension are BOTH partitions (`compile_branched`'s MASTER, boxed in by
#: HALL_A and BATH_1 rather than an exterior wall) loses less than `_EDGE_INSET_ALLOWANCE_M`, so a
#: gross value converted with the bigger allowance nets MORE depth than the ceiling intended —
#: past the template's own maximum, the exact failure `leaf_shapes` reported before this constant
#: existed ("leaf 'MASTER' cannot be 3.2x6.85 m"). Converting the ceiling with the SMALLEST
#: possible inset instead guarantees the real net value is never bigger than intended, whichever
#: of the two the leaf's real neighbours turn out to be — a little conservative when they are not
#: both partitions, never wrong.
_MIN_EDGE_INSET_M = 0.10


def _witness_band_m(template: "cg.RoomTemplate", other_gross_m: float,
                    hard: bool = False) -> tuple[float, float] | None:
    """The GROSS band for a room's free dimension that keeps it inside `template`'s own shape-and-
    size rule at a known GROSS `other_gross_m` — `room_depth_band_m`'s own NET band (symmetric in
    its two dimensions: a room's short side/aspect/area bounds do not care which side is which),
    translated to/from gross with `concept_generator._EDGE_INSET_ALLOWANCE_M` (the floor) and
    `_MIN_EDGE_INSET_M` (the ceiling — see its own docstring for why the two conversions are not
    the same allowance). `hard`: the band under the role's
    HARD maximum rather than its preferred one — for a room this tree deliberately lets run to its
    hard ceiling because its own gross rectangle is forced by a neighbour's width, not its own
    (`compile_hub_lobby`'s BATH_2, exactly like `concept_generator.hub_bound`'s foot band). None
    when the band is empty at this width: the BOUND half of the search finding no sizing at all,
    so the caller declines rather than forcing a strip or an over-maximum room.
    """
    # SAFE_ROOM is RC on every side (`concept_generator._depth_allowance_m`), losing a FULL RC
    # half to EACH of its two walls on a dimension (0.30 m total) rather than the flat "one
    # exterior half + one partition half" every other role's envelope carries — using the flat
    # allowance here handed Geometry Core a safe room that nets under its own regulated 2.4 m
    # floor once real RC walls applied, the forced tree refused (`concept_generator`'s own report
    # of the same bug before this floor existed).
    is_safe_room = template is cg.ROOM_TEMPLATES.get(ProgramRole.SAFE_ROOM)
    inset = cg.WALL_THICKNESS_M[cg.WallType.RC_SAFE_ROOM] if is_safe_room else cg._EDGE_INSET_ALLOWANCE_M
    band = cg.room_depth_band_m(template, other_gross_m - inset, hard)
    if band is None:
        return None
    lo_grid = math.ceil((band[0] + inset) / 0.05 - 1e-9) * 0.05
    hi_grid = math.floor((band[1] + _MIN_EDGE_INSET_M) / 0.05 + 1e-9) * 0.05
    if lo_grid > hi_grid + 1e-9:
        return None
    return lo_grid, hi_grid


def _witness_dim_m(template: "cg.RoomTemplate", other_gross_m: float,
                   hard: bool = False) -> float | None:
    """The single GROSS WITNESS for a room's free dimension: the point in `_witness_band_m`'s own
    band closest to `template`'s own target area at this `other_gross_m` — never past the band
    either way — on the engine's 0.05 m cut grid. None exactly when `_witness_band_m` is."""
    band = _witness_band_m(template, other_gross_m, hard)
    if band is None:
        return None
    lo, hi = band
    target = template.target_area_m2 / max(other_gross_m, 1e-6)
    return _grid_clamp_m(target, lo, hi)


def _witness_floor_m(template: "cg.RoomTemplate", other_gross_m: float,
                     hard: bool = False, at_most: float | None = None) -> float | None:
    """The single GROSS witness at the LOW end of `_witness_band_m`'s own band — never past
    `at_most` when given — for a "sliver" leaf whose own job is to clear its template's floor and
    seat a door, not to reach its target area (`compile_hub_lobby`'s south-row split: BATH_2's
    sliver beside SAFE_ROOM, TOILET_1's sliver beside BATH_2 — sizing either one to its OWN target
    area the way every other leaf in this tree is sized would make the sliver AS BIG as the room
    it is meant to leave most of the row to). None when the band (narrowed by `at_most`) is empty.
    """
    band = _witness_band_m(template, other_gross_m, hard)
    if band is None:
        return None
    lo, hi = band
    if at_most is not None:
        hi = min(hi, at_most)
    return _grid_clamp_m(lo, lo, hi)


def _witness_shared_dim_m(members: list[tuple["cg.RoomTemplate", float, bool]]) -> float | None:
    """The single GROSS witness for ONE dimension shared by several rooms, each at its OWN known
    GROSS other-dimension (`members`: `(template, other_gross_m, hard)`) — the INTERSECTION of
    every member's own `_witness_band_m`, at the point closest to the average of their own targets.
    None when the intersection is empty: no single shared value seats every member inside its own
    band, so the caller declines rather than forcing one member out of its template."""
    lo, hi = -math.inf, math.inf
    targets = []
    for template, other_gross_m, hard in members:
        band = _witness_band_m(template, other_gross_m, hard)
        if band is None:
            return None
        lo, hi = max(lo, band[0]), min(hi, band[1])
        targets.append(template.target_area_m2 / max(other_gross_m, 1e-6))
    if lo > hi + 1e-9:
        return None
    return _grid_clamp_m(sum(targets) / len(targets), lo, hi)


def _grid_range_m(lo: float, hi: float, step: float = 0.05):
    """`lo` itself, then every grid point above it up to `hi` — `concept_generator.hub_bound`'s
    own `_bound_grid`, the grid a bound/witness search samples a bounded interval on."""
    if lo > hi + 1e-9:
        return
    x = math.floor(lo / step + 1e-9) * step
    if x < lo - 1e-9:
        x += step
    while x <= hi + 1e-9:
        yield round(x, 2)
        x += step


def _witness_anchor_m(template: "cg.RoomTemplate") -> float:
    """A room's own SELF-anchored gross dimension — the square root of its target area, floored by
    its own minimum short side — used only where no OTHER dimension is fixed yet to compute the
    free one from (`compile_hub_lobby`'s west column, `compile_branched`'s row-3 columns): the
    search's own starting point, not a final witness by itself — every room this anchors still gets
    its OWN shape verified by `_witness_dim_m`/`_witness_band_m` downstream of it."""
    inset = cg._EDGE_INSET_ALLOWANCE_M
    anchor = math.sqrt(template.target_area_m2)
    floor = template.min_short_side_m + inset
    if anchor <= floor:
        return math.ceil(floor / 0.05 - 1e-9) * 0.05
    return round(anchor / 0.05) * 0.05


# --------------------------------------------------------------------------- HUB_LOBBY

#: The programme shape `compile_hub_lobby` supports — see the module docstring for why. 2
#: bedrooms (a master plus one). `safe_room`/`open_plan_living` are BOTH supported (lead
#: direction, 2026-09-22, attempt 3): a SAFE_ROOM row and/or an open-plan LIVING/KITCHEN group,
#: see `compile_hub_lobby`'s own docstring for how each changes the tree. `wet_rooms` (attempt 4,
#: review follow-up): 2 (the master's ensuite plus one shared bathroom, `resolve_wet_rooms`'s
#: default) OR 3 (the same two PLUS a GUEST_WC, `resolve_wet_rooms`'s zone id TOILET_1) — the
#: extra room's own size comes from `cg.ROOM_TEMPLATES[ProgramRole.TOILET]` (its real min/target/
#: max area and min short side), not a fixed literal, so the tree adapts to the ACTUAL role the
#: programme adds rather than staying blind to any wet-room count but exactly 2. Not yet combined
#: with `safe_room` — a 3-way south-row split (BATH_2 | SAFE_ROOM | TOILET_1) is a further step,
#: named as a follow-up rather than attempted here.
_HUB_LOBBY_BEDROOMS = 2
_HUB_LOBBY_WET_ROOMS_NO_TOILET = 2
_HUB_LOBBY_WET_ROOMS_WITH_TOILET = 3

#: The lobby's own zone — "HALL" role for C14/the twin's root->HALL rule and every label keyed on
#: the hall, but a TIGHTER shape than `ROOM_TEMPLATES[HALL]`'s corridor policy: compact, aspect
#: well under the 1.5 gate (module docstring) — a product choice about how this specific room
#: reads, not a room-SIZE limit, so it stays a separate template from `ROOM_TEMPLATES[HALL]`'s own
#: (much looser, corridor-shaped) one; `_hub_lobby_sizing` sizes it against THIS template's own
#: band, exactly like every other leaf in the tree.
_HUB_LOBBY_HALL_TEMPLATE = cg.RoomTemplate(5.0, 8.0, 16.0, 1.2, 1.5)


def _hub_lobby_unsupported(spec: "ArchitecturalSpec") -> str | None:
    program = spec.program
    if program.bedrooms != _HUB_LOBBY_BEDROOMS:
        return f"compile_hub_lobby supports exactly {_HUB_LOBBY_BEDROOMS} bedrooms, not {program.bedrooms}"
    if program.wet_rooms == _HUB_LOBBY_WET_ROOMS_WITH_TOILET and program.safe_room:
        return "compile_hub_lobby's 3-wet-room GUEST_WC row is not yet combined with a safe room"
    if program.wet_rooms not in (_HUB_LOBBY_WET_ROOMS_NO_TOILET, _HUB_LOBBY_WET_ROOMS_WITH_TOILET):
        return (f"compile_hub_lobby supports {_HUB_LOBBY_WET_ROOMS_NO_TOILET} or "
               f"{_HUB_LOBBY_WET_ROOMS_WITH_TOILET} wet rooms, not {program.wet_rooms}")
    return None


def _hub_lobby_sizing(has_safe: bool, has_toilet: bool
                      ) -> tuple[float, float, float, float, float, float, float, float] | None:
    """The witness search for every gross dimension `compile_hub_lobby`'s tree fixes (see the
    witness-search section above) — "force one side, size the sibling to match"
    (`compile_branched`'s own docstring names the same discipline): the west column (MASTER over
    BATH_1) anchors itself from MASTER's own target area (`_witness_anchor_m`), which fixes the
    row-3 V-split's shared height too (`hd == md`, so BATH_1's own depth is what the south row
    inherits — the SAME equality the old hand-picked table had, now found rather than picked); the
    east column's widths (`lobby_w`, BEDROOM_1's width) then follow from that shared height; the
    south row's own depth is the INTERSECTION of BATH_1's own band at `master_w` and whichever
    room ends up spanning the row's own width (BATH_2 alone, or split with SAFE_ROOM/TOILET_1) —
    the coupling the old table's SAFE-variant numbers existed to satisfy by hand, resolved here by
    a short fixed-point search (the split width depends on the row's depth and vice versa) instead
    of an empirically-tuned literal. Returns `(master_w, md, lobby_w, bedroom1_w, hd, fd,
    south_sliver_w, pb)`, or None the moment any leaf's band is empty — the bound reporting no
    sizing exists for this precondition/footprint, so the caller declines.
    """
    MASTER = cg.ROOM_TEMPLATES[ProgramRole.MASTER_BEDROOM]
    BATH = cg.ROOM_TEMPLATES[ProgramRole.BATHROOM]
    BEDROOM = cg.ROOM_TEMPLATES[ProgramRole.BEDROOM]
    SAFE = cg.ROOM_TEMPLATES[ProgramRole.SAFE_ROOM]
    TOILET = cg.ROOM_TEMPLATES[ProgramRole.TOILET]
    LIVING = cg.ROOM_TEMPLATES[ProgramRole.LIVING]
    KITCHEN = cg.ROOM_TEMPLATES[ProgramRole.KITCHEN]

    master_w = _witness_anchor_m(MASTER)
    md = _witness_dim_m(MASTER, master_w)
    bath1_d = _witness_dim_m(BATH, master_w)
    if md is None or bath1_d is None:
        return None
    hd = md

    bedroom1_w = _witness_dim_m(BEDROOM, hd)
    if bedroom1_w is None:
        return None

    if has_safe or has_toilet:
        # The south row's WEST leaf (BATH_2's sliver beside SAFE_ROOM, or TOILET_1's sliver
        # beside BATH_2) must stay narrower than `lobby_w` by a real door opening: whichever room
        # this row's EAST leaf is, its own edge with HALL is `lobby_w - sliver_w`, and both the
        # SAFE_ROOM and the TOILET-variant BATH_2 need that door (docstring). Sized at its
        # template's own FLOOR (`_witness_floor_m`), not its target — this leaf's job is to clear
        # its own minimum and seat a door, not to reach the area a full-sized room would (a
        # target-driven witness made this leaf as wide as BATH's own 6.5 m2 target needs at a
        # shallow depth — as big as the room it was meant to leave most of the row to).
        #
        # Two nested searches, both over a BAND rather than a fixed point: `lobby_w` (HALL's own
        # band at `hd`, narrowest first) because a sliver narrow enough to clear the door-opening
        # cap needs the room this cap leaves it — the same reason the old hand-picked table widened
        # `LOBBY_W` for its SAFE variant; and `fd` (BATH_1's own band at `master_w`, also narrowest
        # first) because a sliver's own floor does not shrink with depth as fast as its minimum
        # AREA does. First combination that seats every leaf wins.
        from .doors import DOOR_MARGIN_M, INTERIOR_DOOR_WIDTH_M
        opening_m = INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M
        sliver_template = TOILET if has_toilet else BATH
        remainder_template = BATH if has_toilet else SAFE
        lobby_band = _witness_band_m(_HUB_LOBBY_HALL_TEMPLATE, hd)
        bath1_band = _witness_band_m(BATH, master_w, False)
        if lobby_band is None or bath1_band is None:
            return None
        lobby_w = fd = sliver_w = None
        for candidate_lobby_w in _grid_range_m(*lobby_band):
            east_w = candidate_lobby_w + bedroom1_w
            sliver_cap = candidate_lobby_w - opening_m
            for candidate_fd in _grid_range_m(*bath1_band):
                candidate_sliver = _witness_floor_m(sliver_template, candidate_fd, at_most=sliver_cap)
                if candidate_sliver is None or candidate_sliver >= east_w - 0.05:
                    continue
                remainder_band = _witness_band_m(remainder_template, east_w - candidate_sliver, True)
                if remainder_band is None:
                    continue
                r_lo, r_hi = remainder_band
                if r_lo - 1e-9 <= candidate_fd <= r_hi + 1e-9:
                    lobby_w, fd, sliver_w = candidate_lobby_w, candidate_fd, candidate_sliver
                    break
            if lobby_w is not None:
                break
        if lobby_w is None:
            return None
        east_w = lobby_w + bedroom1_w
    else:
        lobby_w = _witness_dim_m(_HUB_LOBBY_HALL_TEMPLATE, hd)
        if lobby_w is None:
            return None
        east_w = lobby_w + bedroom1_w
        sliver_w = 0.0
        fd = _witness_shared_dim_m([(BATH, master_w, False), (BATH, east_w, True)])
        if fd is None:
            return None

    total_w = master_w + east_w
    living_share = LIVING.target_area_m2 / (LIVING.target_area_m2 + KITCHEN.target_area_m2)
    living_w = round(total_w * living_share / 0.05) * 0.05
    kitchen_w = total_w - living_w
    pb = _witness_shared_dim_m([(LIVING, living_w, False), (KITCHEN, kitchen_w, False)])
    if pb is None:
        return None

    return master_w, md, lobby_w, bedroom1_w, hd, fd, sliver_w, pb


def compile_hub_lobby(spec: "ArchitecturalSpec", candidate: Rect) -> "list[ConceptCandidate]":
    """The HUB_LOBBY parti: a compact lobby (aspect well under the 1.5 gate) with the public band
    on its north side (a CASED_OPENING), MASTER on its west flank, BEDROOM_1 on its east flank,
    and the shared wet room (BATH_2, "the shared wet rooms at its head") directly on its south
    side. Without a safe room that is 4 doors, rooms on 4 sides. WITH one
    (`spec.program.safe_room`), the south row splits in two (`south_row`): BATH_2 keeps a real
    door-width slice of HALL's own width, and SAFE_ROOM takes the rest of that row PLUS all of
    BEDROOM_1's width, so it borders HALL directly (never through a bedroom —
    `access_rules.ALLOWED_ENTERED_FROM`) and reaches the EAST exterior wall in the same row
    (`exposure_policy`'s REQUIRED exterior+window for `ProgramRole.SAFE_ROOM`) — 5 doors, rooms on
    5 sides. WITH a third wet room instead (`spec.program.wet_rooms == 3`), the south row splits
    the OTHER way: TOILET_1 (a GUEST_WC) takes the west sliver under HALL, and BATH_2 keeps the
    remainder — the same "one leaf keeps a real slice of HALL's own width, the other takes the
    rest of the row" split `SAFE_ROOM` uses above, with the two rooms' structural roles swapped.
    Not yet combined with a safe room (`_hub_lobby_unsupported`). `spec.program.open_plan_living`
    (independently) only changes the LIVING-KITCHEN edge from DOOR to OPEN_CONNECTION plus
    `open_groups`; it never touches the tree.

    Every gross dimension the tree fixes (`_hub_lobby_sizing`) is a WITNESS the search finds from
    `concept_generator.ROOM_TEMPLATES`'s own [min, max] area / min short side / max aspect bands
    (the witness-search section above; review follow-up, Issue #79 attempt 5) — never a fixed
    literal picked per precondition, and never past a template's own bound, so nothing here is a
    hard-limit relaxation. See the module docstring for why this is a hand-authored TREE (as
    opposed to `concept_generator._hub_concept`'s own, measured-broken, builder), and
    `_hub_lobby_unsupported` for the programme shape(s) it serves.
    """
    if _hub_lobby_unsupported(spec) is not None:
        return []
    has_safe = spec.program.safe_room
    has_toilet = spec.program.wet_rooms == _HUB_LOBBY_WET_ROOMS_WITH_TOILET
    open_plan = spec.program.open_plan_living
    sizing = _hub_lobby_sizing(has_safe, has_toilet)
    if sizing is None:
        return []
    master_w, md, lobby_w, bedroom1_w, hd, fd, toilet_w, pb = sizing

    max_w_m, max_h_m = cg.u_to_m(candidate.w), cg.u_to_m(candidate.h)
    east_w = lobby_w + bedroom1_w
    total_w = master_w + east_w
    total_h = pb + hd + fd
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
    if has_toilet:
        toilet_template = cg.ROOM_TEMPLATES[ProgramRole.TOILET]
        zones.append(z("TOILET_1", (ProgramRole.TOILET,), toilet_template.min_area_m2,
                       toilet_template.target_area_m2, toilet_template.max_area_m2,
                       toilet_template.min_short_side_m, aspect=toilet_template.max_aspect_ratio))

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
        south_row = v(L("BATH_2"), L("SAFE_ROOM"), fixed_m=toilet_w)
        east_part = h(hub_east, south_row, fixed_m=hd)
    elif has_toilet:
        south_row = v(L("TOILET_1"), L("BATH_2"), fixed_m=toilet_w)
        east_part = h(hub_east, south_row, fixed_m=hd)
    else:
        east_part = h(hub_east, L("BATH_2"), fixed_m=hd)
    bottom = v(west_col, east_part, fixed_m=master_w)
    tree = h(top, bottom, fixed_m=pb)

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
    if has_toilet:
        edges.append(DesiredAccessEdge("HALL", "TOILET_1", ConnectionKind.DOOR))
    access = DesiredAccessTopology(tuple(edges))
    open_groups = (("LIVING", "KITCHEN"),) if open_plan else ()
    fixture = Fixture("GEN_HUB_LOBBY", (wing,), tuple(zones), access, open_groups=open_groups)
    concept = Concept(fixture, "HALL", Side.N, cg.u_to_m(footprint.w), cg.u_to_m(footprint.h))
    wet_rooms = resolve_wet_rooms(spec.program)
    rationale = "hand-sized compact lobby: rooms on 4 sides, the shared bathroom at its head"
    if has_safe:
        rationale = ("hand-sized compact lobby with a safe room: rooms on 5 sides, the safe room "
                    "and the shared bathroom both reached from the lobby directly")
    if has_toilet:
        rationale = ("hand-sized compact lobby with a guest WC: rooms on 5 sides, a GUEST_WC "
                    "sized from its own room template sits under the lobby beside the shared bath")
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


def _branched_sizing(has_safe: bool) -> tuple[float, float, float, float, float, float, float] | None:
    """The witness search for every gross dimension `compile_branched`'s tree fixes — `(mw, hb_w,
    ew, pb, ha, master_d, bath1_d)`, or None. `MW`/`HB_W`/`EW` are the row-3 column widths (master
    wing | HALL_B | bedroom wing); `PB`/`HA` the public band and HALL_A's own depth; `MASTER_D`/
    `BATH1_D` the forced master-wing rows. The bedroom wing's own rows (`BEDROOM_1/2[/3]` +
    `BATH_2`[+`SAFE_ROOM`]) stay UNFORCED (`fixed_m=None` in `compile_branched`) so the solver
    sizes them to whatever depth `MASTER_D + BATH1_D` actually supplies — the same "force one
    side, leave the other's internal seams to the solver" discipline `concept.py`'s own
    `back_chain` uses; this search's own job is only to make that supplied depth ENOUGH for the
    stack's four members, each at its own template's minimum short side (`required_stack_depth`).

    `MW` is fixed at MASTER's own FLOOR (`min_short_side_m` + the edge-inset allowance), not an
    area-driven anchor: MASTER's target area at that narrow a width already needs more depth than
    its own target-driven witness would give it, and `MASTER_D`/`BATH1_D` are each taken at their
    OWN template's band CEILING at that width (not the target) for the same reason — the row-3
    column's job here is to supply the stack depth, not to hit its own rooms' target areas (the
    old hand-picked table's `_MASTER_D_M`/`_BATH1_D_M` did the same thing by hand: a narrow master
    wing, deliberately deep). `open_plan_living` never changes any of these — same reasoning as
    `compile_hub_lobby`.
    """
    MASTER = cg.ROOM_TEMPLATES[ProgramRole.MASTER_BEDROOM]
    BATH = cg.ROOM_TEMPLATES[ProgramRole.BATHROOM]
    BEDROOM = cg.ROOM_TEMPLATES[ProgramRole.BEDROOM]
    SAFE = cg.ROOM_TEMPLATES[ProgramRole.SAFE_ROOM]
    HALL = cg.ROOM_TEMPLATES[ProgramRole.HALL]
    LIVING = cg.ROOM_TEMPLATES[ProgramRole.LIVING]
    KITCHEN = cg.ROOM_TEMPLATES[ProgramRole.KITCHEN]
    inset = cg._EDGE_INSET_ALLOWANCE_M

    mw = math.ceil((MASTER.min_short_side_m + inset) / 0.05 - 1e-9) * 0.05
    master_band = _witness_band_m(MASTER, mw)
    bath1_band = _witness_band_m(BATH, mw)
    if master_band is None or bath1_band is None:
        return None
    master_d, bath1_d = master_band[1], bath1_band[1]

    # The bedroom wing's own width (`ew`, shared by every stacked member) must leave EACH member
    # enough of the `master_d + bath1_d` budget for its OWN band's floor at that width — not just
    # its min short side (`_witness_band_m` already folds in the area-minimum floor, which BINDS
    # first at a narrow width: a 9 m2 bedroom on a wide-enough BEDROOM anchor still needs more
    # depth per m2 than its short side alone would floor it at). Starts at BEDROOM's own anchor,
    # widening on the grid until the stack's own floors fit the budget — the search the old hand-
    # picked `_EW_M` existed to skip.
    stack = [BEDROOM, BEDROOM, SAFE if has_safe else BEDROOM, BATH]
    budget = master_d + bath1_d
    ew = _witness_anchor_m(BEDROOM)
    for _ in range(400):
        bands = [_witness_band_m(t, ew) for t in stack]
        if all(b is not None for b in bands) and sum(b[0] for b in bands) <= budget + 1e-9:
            break
        ew = round(ew + 0.05, 2)
    else:
        return None

    # HALL_B's own height is FORCED to `master_d + bath1_d` (the row-3 V-split gives it the same
    # full height as the master wing beside it) — its width has to clear HALL's max aspect ratio
    # at THAT height, not just its own min short side, once the master wing is this deep.
    hb_w = _witness_dim_m(HALL, budget)
    if hb_w is None:
        return None
    ha = math.ceil((HALL.min_short_side_m + inset) / 0.05 - 1e-9) * 0.05

    total_w = mw + hb_w + ew
    living_share = LIVING.target_area_m2 / (LIVING.target_area_m2 + KITCHEN.target_area_m2)
    living_w = round(total_w * living_share / 0.05) * 0.05
    kitchen_w = total_w - living_w
    pb = _witness_shared_dim_m([(LIVING, living_w, False), (KITCHEN, kitchen_w, False)])
    if pb is None:
        return None
    return mw, hb_w, ew, pb, ha, master_d, bath1_d


#: Issue #130 (2026-09-23, rollup repair): C26's dead-end rule (Issue #36) merged into `main`
#: after this tree was authored and now refuses it on EVERY shape this compiler otherwise
#: supports (measured on the realized canonical fixture and all three SAFE_ROOM/open-plan
#: variants — identical failure each time): HALL_A's own west AND east ends sit on the building's
#: exterior wall with no door at either END (MASTER's door lands on HALL_A's long SOUTH side, and
#: the HALL_A/HALL_B `CASED_OPENING` lands away from both ends too, over the middle block's own
#: width, never at x=0 or x=total_w), and HALL_B's own south end has nothing south of the bedroom
#: stack to serve it either — 3 dead ends, structurally, regardless of sizing (`_branched_sizing`
#: cannot change WHICH zone borders which end, only how big each one is). A retopologized tree
#: (moving MASTER beside HALL_A's own west end rather than beneath it, so a door can land there)
#: is a real follow-up, not attempted here — see `docs/reports/concept-engine-v2-diversity-
#: report.md`.
_BRANCHED_DEAD_END_COUNT = 3
_BRANCHED_C26_CONFLICT_REASON = (
    f"compile_branched's own two-hall tree produces {_BRANCHED_DEAD_END_COUNT} corridor dead "
    f"ends (HALL_A's own west and east ends, HALL_B's own south end) on every supported "
    f"programme shape, exceeding C26's limit of {EXTREME_DEAD_END_COUNT} (Issue #36) — declines "
    f"unconditionally until the tree is redesigned (Issue #130)"
)


def _branched_unsupported(spec: "ArchitecturalSpec") -> str | None:
    """Why `compile_branched` declines `spec` — a shape mismatch, or (Issue #130, now always)
    the C26 dead-end conflict every shape it does match still hits."""
    program = spec.program
    expected_bedrooms = _BRANCHED_BEDROOMS_WITH_SAFE if program.safe_room else _BRANCHED_BEDROOMS_NO_SAFE
    if program.bedrooms != expected_bedrooms:
        return (f"compile_branched supports exactly {expected_bedrooms} bedrooms "
               f"{'with' if program.safe_room else 'without'} a safe room, not {program.bedrooms}")
    if program.wet_rooms != _BRANCHED_WET_ROOMS:
        return f"compile_branched supports exactly {_BRANCHED_WET_ROOMS} wet rooms, not {program.wet_rooms}"
    return _BRANCHED_C26_CONFLICT_REASON


def compile_branched(spec: "ArchitecturalSpec", candidate: Rect) -> "list[ConceptCandidate]":
    """The BRANCHED parti: HALL_A (public-facing, under LIVING/KITCHEN) meets HALL_B (serving the
    bedroom wing) at a corner, over a partial shared edge, joined by a CASED_OPENING — never an
    OPEN_CONNECTION (see the module docstring). Every bedroom's door sits on one of the two hall
    segments: MASTER on HALL_A, the rest of the stack on HALL_B.

    Without a safe room (attempt 2): BEDROOM_1/2/3 + BATH_2 stack off HALL_B. WITH one
    (`spec.program.safe_room`, attempt 3): SAFE_ROOM takes the third bedroom-class slot instead of
    BEDROOM_3 — `_BRANCHED_BEDROOMS_WITH_SAFE` (3, not 4) is the precondition for this — so the
    stack still has 4 members, and `_branched_sizing`'s own `required_stack_depth` check already
    accounts for SAFE_ROOM's own (taller) minimum short side in the stack's depth budget; SAFE_ROOM
    reaches HALL_B directly (never through a bedroom) and the EAST exterior wall the same way every
    stack member already does (the stack is the building's own east edge). A 4-bedroom-plus-safe-
    room programme (5 stacked private rooms) was measured infeasible at this tree's own depth
    budget even after widening every lever that does not itself break MASTER/BATH_1's own
    `RoomTemplate` bands — named as a follow-up, not attempted here (see the module docstring for
    why a general search is separately out of scope).

    `spec.program.open_plan_living` (independently, like `compile_hub_lobby`) only changes the
    LIVING-KITCHEN edge/`open_groups`; it never touches the tree.

    Declines (empty list, not an exception) for any other programme, exactly like every other
    builder in this module declines a programme it cannot serve.

    Issue #130 (2026-09-23): this now declines EVERY programme, including its own previously-
    supported shapes — see `_BRANCHED_C26_CONFLICT_REASON`/`_branched_unsupported`. The tree and
    sizing search below are kept, unreached, as the starting point for the retopologizing
    follow-up named there (the same "keep the code, gate it off" pattern `LAUNDRY_ROOM_ENABLED`/
    `CONCEPT_ENGINE_V2_ENABLED` already use elsewhere in this codebase), not dead code left over
    by accident.
    """
    if _branched_unsupported(spec) is not None:
        return []
    has_safe = spec.program.safe_room
    open_plan = spec.program.open_plan_living
    sizing = _branched_sizing(has_safe)
    if sizing is None:
        return []
    mw, hb_w, ew, pb, ha, master_d, bath1_d = sizing

    max_w_m, max_h_m = cg.u_to_m(candidate.w), cg.u_to_m(candidate.h)
    total_w = mw + hb_w + ew
    total_h = pb + ha + master_d + bath1_d
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
    west = h(L("MASTER"), L("BATH_1"), fixed_m=master_d)
    third_slot = L("SAFE_ROOM") if has_safe else L("BEDROOM_3")
    east_stack = h(L("BEDROOM_1"),
                   h(L("BEDROOM_2"), h(third_slot, L("BATH_2"), fixed_m=None), fixed_m=None),
                   fixed_m=None)
    middle = v(L("HALL_B"), east_stack, fixed_m=hb_w)
    row3 = v(west, middle, fixed_m=mw)
    lower = h(L("HALL_A"), row3, fixed_m=ha)
    tree = h(top, lower, fixed_m=pb)

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
