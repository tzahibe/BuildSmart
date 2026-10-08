"""#185 — a BRANCHED tree whose corridor ends are SERVED, compiled for the brief's real programme.

#184 established that BRANCHED realizes and is architecturally distinct, and fails exactly one
check: C26, because the production tree leaves three corridor ends at a blank wall (HALL_A's west
and east, HALL_B's south). This module redesigns the tree so every corridor end TERMINATES AT A
DESTINATION instead, which is what makes C26 pass without C26 changing:

                 LIVING  |  DINING  |  KITCHEN          <- public band, north
    -------------------------------------------------
      MASTER   |        HALL_A        |   BATH_1        <- entry hall, a room at EACH end
    -------------------------------------------------
      HALL_B   |              BEDROOM_1                 <- bedroom wing, HALL_B under HALL_A
      HALL_B   |              BEDROOM_2                    so their junction serves HALL_B's north
      BATH_2   |              BEDROOM_3                 <- a room at HALL_B's south end

    HALL_A west end -> MASTER's door          HALL_B north end -> the junction with HALL_A
    HALL_A east end -> BATH_1's door          HALL_B south end -> BATH_2's door

Nothing is relabelled and no dead end is hidden: the ends are genuinely served, and
`circulation_metrics.measure` is left to count them.

EXPERIMENTAL PATH. This lives in the harness, calls production's own witness helpers, room
templates and realizer, and changes no production file. BRANCHED is not enabled anywhere.
"""
from __future__ import annotations

from app.vertical_slice import concept_compilers as cc
from app.vertical_slice import concept_generator as cg
from app.vertical_slice.concept_spec import CirculationClass
from app.vertical_slice.concept import Concept
from app.vertical_slice.geometry_core.model import (ConnectionKind, Cut, DesiredAccessEdge,
                                                    DesiredAccessTopology, Fixture, Leaf,
                                                    ProgramRole, Rect, Side, Split, Wing, ZoneSpec,
                                                    m_to_u)
from app.vertical_slice.wet_rooms import resolve_wet_rooms

STEP_M = 0.05
#: Bounded on purpose (#185 scope): the proof covers 3-4 bedrooms. 5-6 is explicitly out.
MIN_BEDROOMS, MAX_BEDROOMS = 3, 4


def _grid(value: float) -> float:
    return round(value / STEP_M) * STEP_M


def programme(spec):
    """The brief's real rooms, in the roles this tree places. `None` when the shape is out of the
    proof's bounded scope — never a silent substitution."""
    rooms = cg.build_room_program(spec)
    public = [r for r in rooms if r.role in (ProgramRole.LIVING, ProgramRole.DINING,
                                             ProgramRole.KITCHEN, ProgramRole.FAMILY_ROOM)]
    master = next((r for r in rooms if r.role is ProgramRole.MASTER_BEDROOM), None)
    stack = [r for r in rooms if r.role in (ProgramRole.BEDROOM, ProgramRole.SAFE_ROOM)]
    wets = [r for r in rooms if r.wet is not None]
    if master is None or not public or not wets:
        return None, "programme has no master, no public room, or no wet room"
    bedrooms = 1 + sum(1 for r in stack if r.role is ProgramRole.BEDROOM)
    if not (MIN_BEDROOMS <= bedrooms <= MAX_BEDROOMS):
        return None, f"#185 is bounded to {MIN_BEDROOMS}-{MAX_BEDROOMS} bedrooms, not {bedrooms}"
    if len(wets) < 2:
        return None, "this tree places one wet room off the entry hall and one at the wing's end"
    # C17: an ENSUITE is required to be entered from its host, so it sits behind the master and
    # never off the hall. The entry hall's east end is therefore terminated by a BEDROOM, and a
    # SHARED wet room terminates the wing corridor's south end.
    ensuite = next((r for r in wets if r.entered_from == master.zone_id), None)
    shared = [r for r in wets if r is not ensuite]
    if not shared:
        return None, "no shared wet room to terminate the wing corridor (every wet room is an ensuite)"
    if not stack:
        return None, "no bedroom to terminate the entry hall's east end"
    wing_wet = shared[0]
    extra_wets = shared[1:]
    entry_end = stack[0]
    wing_stack = stack[1:] or [stack[0]]
    if len(stack) < 2:
        return None, "this tree needs one bedroom at the hall's end and at least one in the wing"
    return (public, master, ensuite, entry_end, wing_wet, extra_wets, stack[1:]), None


def sizing(public, master, ensuite, entry_end, wing_wet, extra_wets, stack, max_w_m: float, max_h_m: float):
    """Every dimension the tree fixes, searched with production's own witness helpers.

    Driven from the ENTRY ROW, because that row carries three rooms side by side (master, a real
    hall, a wet room) and is therefore the widest thing in the plan; the wing below shares that
    width as a corridor plus a bedroom stack. Driving it from the stack instead makes the plan
    narrower than its own entry row and the hall collapses to nothing.

    The master's width, the hall's width and the wing corridor's width are all searched, and the
    LARGEST feasible plan inside the envelope wins — the first one found is the narrowest hall and
    the smallest rooms, which would deliver far less area than the production primary for no
    architectural reason. Every value still sits inside the room's OWN template band, so this grows
    the house toward its programme and never past it.

    Returns `(dims, None)` or `(None, reason)`.
    """
    inset = cg._EDGE_INSET_ALLOWANCE_M
    k = len(stack)
    reason = "no sizing found"
    anchor_w = cc._witness_anchor_m(master.template)
    entry_end_w = _grid(entry_end.template.min_short_side_m + inset)
    best = None

    for master_steps in range(0, 30):
        master_w = _grid(anchor_w + master_steps * STEP_M)
        master_band = cc._witness_band_m(master.template, master_w)
        if master_band is None:
            break
        for hall_a_steps in range(0, 90):   # must be able to exceed the hall's own depth
            hall_a_w = _grid(1.2 + inset + hall_a_steps * STEP_M)
            total_w = _grid(master_w + hall_a_w + entry_end_w)
            if total_w > max_w_m + 1e-9:
                break
            end_band = cc._witness_band_m(entry_end.template, entry_end_w)
            if end_band is None:
                continue
            # the WEST column is the master with its ensuite behind it, so the row's depth is the
            # pair's depth — and the bedroom at the east end must share that same depth
            ens_d = cc._witness_dim_m(ensuite.template, master_w) if ensuite is not None else 0.0
            if ensuite is not None and ens_d is None:
                continue
            md_lo, md_hi = master_band
            ha_lo = max(md_lo + ens_d, end_band[0])
            ha_hi = min(md_hi + ens_d, end_band[1])
            if ha_lo > ha_hi + 1e-9:
                reason = "the master column and the hall-end bedroom have no common depth"
                continue
            ha = _grid(min(ha_hi, max(ha_lo, master.template.target_area_m2 / master_w + ens_d)))
            md = _grid(ha - ens_d)
            # THE ENTRY HALL MUST READ AS A HORIZONTAL BAND. `circulation_metrics._end_sides`
            # takes a room's ENDS to be the two sides of its own LONG axis, so a hall narrower
            # than it is deep has its ends at the north and south — and the rooms placed at its
            # west and east would sit on its flanks, serving nothing. Requiring the hall to be
            # wider than deep is what makes "a room at each end" true in the realized geometry.
            if hall_a_w <= ha + 1e-9:
                continue

            for hallb_steps in range(0, 60):   # wide enough to absorb the entry row's width
                hallb_w = _grid(1.2 + inset + hallb_steps * STEP_M)
                # C7/C13: the wing corridor must underlap the ENTRY HALL by a real door width,
                # otherwise the two halls share too little wall for an opening and the whole wing
                # is cut off. HALL_A starts at `master_w`, so HALL_B must reach past it.
                if hallb_w < master_w + 1.1:
                    continue
                bed_w = _grid(total_w - hallb_w)
                if bed_w < max(r.template.min_short_side_m for r in stack) + inset:
                    break
                # Let the bedrooms grow INSIDE their own bands rather than stopping at the
                # template's target: production's own area distribution does the same, and a wing
                # of target-sized rooms would deliver far less than the production primary. The
                # top of the intersected band is the largest the templates themselves allow.
                sbands = [cc._witness_band_m(r.template, bed_w) for r in stack]
                if any(b is None for b in sbands):
                    continue
                per_lo, per_hi = max(b[0] for b in sbands), min(b[1] for b in sbands)
                if per_lo > per_hi + 1e-9:
                    continue
                room_depth_cap = max(STEP_M, (max_h_m - 1.0) / k)
                per = _grid(min(per_hi, room_depth_cap))
                if per < per_lo - 1e-9:
                    per = _grid(per_lo)
                wing_d = _grid(per * k)
                wet_d = cc._witness_dim_m(wing_wet.template, hallb_w)
                if wet_d is None:
                    continue
                hallb_d = _grid(wing_d - wet_d)
                if hallb_d < 1.2 + inset:
                    reason = "the wing corridor has no length left once its end room is placed"
                    continue
                total_target = sum(r.template.target_area_m2 for r in public)
                shares = [max(STEP_M, total_w * r.template.target_area_m2 / total_target)
                          for r in public]
                pbands = [cc._witness_band_m(r.template, w) for r, w in zip(public, shares)]
                if any(b is None for b in pbands):
                    reason = "no public-band depth suits every public room at its share of the width"
                    continue
                pb_lo, pb_hi = max(b[0] for b in pbands), min(b[1] for b in pbands)
                if pb_lo > pb_hi + 1e-9:
                    reason = "the public rooms' depth bands do not overlap across this width"
                    continue
                # the public band likewise takes the deepest its own rooms allow, within what the
                # envelope still has left after the entry row and the wing
                room_left = max_h_m - ha - wing_d
                pb = _grid(min(pb_hi, max(pb_lo, room_left)))
                total_h = _grid(pb + ha + wing_d)
                if total_h > max_h_m + 1e-9:
                    reason = (f"the tree needs {total_w:.2f} x {total_h:.2f} m, deeper than the "
                              f"{max_w_m:.2f} x {max_h_m:.2f} m envelope offered")
                    continue
                dims = (total_w, total_h, pb, ha, wing_d, master_w, hall_a_w, entry_end_w,
                        hallb_w, hallb_d, bed_w, per, md)
                if best is None or total_w * total_h > best[0]:
                    best = (total_w * total_h, dims)
    if best is not None:
        return best[1], None
    return None, reason


def _hallb_w_guess(wet, inset):
    return max(1.2 + inset, wet.template.min_short_side_m + inset)


def _band_admits(template, other_m: float, value_m: float) -> bool:
    band = cc._witness_band_m(template, other_m)
    return band is not None and band[0] - 1e-9 <= value_m <= band[1] + 1e-9


def compile_branched_served(spec, envelope: Rect):
    """The redesigned BRANCHED candidate for `spec` inside `envelope`, or `(None, reason)`."""
    parts, why = programme(spec)
    if parts is None:
        return None, why
    public, master, ensuite, entry_end, wing_wet, extra_wets, wing_stack = parts
    dims, why = sizing(public, master, ensuite, entry_end, wing_wet, extra_wets, wing_stack,
                       cg.u_to_m(envelope.w), cg.u_to_m(envelope.h))
    if dims is None:
        return None, why
    (total_w, total_h, pb, ha, wing_d, master_w, hall_a_w, entry_end_w,
     hallb_w, hallb_d, bed_w, per, md) = dims

    def z(room):
        t = room.template
        return ZoneSpec(room.zone_id, (room.role,), t.min_area_m2, t.target_area_m2,
                        t.hard_max_area_m2 or t.max_area_m2, t.min_short_side_m, t.max_aspect_ratio)

    zones = [z(r) for r in public] + [
        ZoneSpec("HALL_A", (ProgramRole.HALL, ProgramRole.CIRCULATION), 4, 9, 26, 1.2, 8.0),
        ZoneSpec("HALL_B", (ProgramRole.HALL, ProgramRole.CIRCULATION), 4, 9, 26, 1.2, 8.0),
        z(master), z(entry_end), z(wing_wet)] + [z(r) for r in wing_stack] + [z(r) for r in extra_wets]
    if ensuite is not None:
        zones.append(z(ensuite))

    L = Leaf
    V = lambda a, b, m: Split(Cut.V, a, b, m_to_u(m) if m is not None else None)
    H = lambda a, b, m: Split(Cut.H, a, b, m_to_u(m) if m is not None else None)

    def chain(rooms, cut, extent):
        node = L(rooms[-1].zone_id)
        total = sum(r.template.target_area_m2 for r in rooms)
        for room in reversed(rooms[:-1]):
            share = _grid(extent * room.template.target_area_m2 / total)
            node = (V if cut is Cut.V else H)(L(room.zone_id), node, share)
        return node

    top = chain(public, Cut.V, total_w) if len(public) > 1 else L(public[0].zone_id)
    # the entry hall with a room at EACH end — this is what serves HALL_A's two ends
    west_col = H(L(master.zone_id), L(ensuite.zone_id), md) if ensuite is not None else L(master.zone_id)
    entry_row = V(west_col, V(L("HALL_A"), L(entry_end.zone_id), hall_a_w), master_w)
    # the wing: HALL_B under HALL_A (junction serves its north end), a wet room at its south end
    hall_b_col = H(L("HALL_B"), L(wing_wet.zone_id), hallb_d)
    east_stack = chain(wing_stack, Cut.H, wing_d)
    wing_row = V(hall_b_col, east_stack, hallb_w)
    tree = H(top, H(entry_row, wing_row, ha), pb)

    footprint = cg.footprint_of(envelope, total_w, total_h)
    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    open_plan = spec.program.open_plan_living
    edges = [DesiredAccessEdge("HALL_A", public[0].zone_id, ConnectionKind.CASED_OPENING)]
    for a, b in zip(public, public[1:]):
        edges.append(DesiredAccessEdge(a.zone_id, b.zone_id,
                                       ConnectionKind.OPEN_CONNECTION if open_plan else ConnectionKind.DOOR))
    edges += [
        DesiredAccessEdge("HALL_A", master.zone_id, ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_A", entry_end.zone_id, ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_A", "HALL_B", ConnectionKind.CASED_OPENING),
        DesiredAccessEdge("HALL_B", wing_wet.zone_id, ConnectionKind.DOOR),
    ]
    if ensuite is not None:
        edges.append(DesiredAccessEdge(master.zone_id, ensuite.zone_id, ConnectionKind.DOOR))
    for room in wing_stack:
        edges.append(DesiredAccessEdge("HALL_B", room.zone_id, ConnectionKind.DOOR))
    for room in extra_wets:
        edges.append(DesiredAccessEdge("HALL_B", room.zone_id, ConnectionKind.DOOR))

    fixture = Fixture("BRANCHED_SERVED", (wing,), tuple(zones),
                      DesiredAccessTopology(tuple(edges)),
                      open_groups=((tuple(r.zone_id for r in public),) if open_plan and len(public) > 1 else ()))
    concept = Concept(fixture, "HALL_A", Side.N, cg.u_to_m(footprint.w), cg.u_to_m(footprint.h))
    used = cg.u_to_m(footprint.w) * cg.u_to_m(footprint.h)
    return cg.ConceptCandidate(
        concept, cg.ConceptStrategy.BRANCHED_TWO_STACK, (0,),
        circulation_class=CirculationClass.BRANCHED,
        rationale=("#185 BRANCHED with served corridor ends: entry hall between the master and a "
                   "wet room, bedroom wing off a second hall ending at a wet room"),
        used_area_m2=round(used, 2),
        unused_wing_area_m2=round(envelope.area_m2() - used, 2),
        wet_rooms=resolve_wet_rooms(spec.program)), None
