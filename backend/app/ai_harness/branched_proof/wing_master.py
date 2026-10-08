"""#185 final variant — MASTER and its ENSUITE move INTO the wing, the entry hall stays compact.

#185's first attempt put the master and its ensuite in the entry row, which forced that row deep,
forced the entry hall wider than its own depth to keep its ends at west/east, and pushed the plan
past the bedroom templates' own size caps. This variant removes that conflict at the source.

                LIVING      |     KITCHEN              public band, north
    ----------------------------------------------
      HALL_A   |   MASTER      |  ENSUITE             entry hall; master in the wing with its
      ----------|---------------------------         ensuite beside it (direct door, C17)
      HALL_B   |      BEDROOM_1                       wing corridor, directly BELOW HALL_A so the
      HALL_B   |      BEDROOM_2                       two share a FULL corridor-width wall
      BATH_2   |      ...                             a wet room serves HALL_B's south end

The two circulation spaces sit in ONE column, one above the other, so their shared wall is the whole
corridor width — a real door, with the engine's normal clearances, rather than the 0.60 m sliver the
previous variant left. Every corridor end is then either the public opening, the other corridor's
door, or a room's door.

EXPERIMENTAL PATH. Harness only; no production file is modified and BRANCHED is enabled nowhere.
"""
from __future__ import annotations

from app.vertical_slice import concept_compilers as cc
from app.vertical_slice import concept_generator as cg
from app.vertical_slice.concept import Concept
from app.vertical_slice.concept_spec import CirculationClass
from app.vertical_slice.geometry_core.model import (ConnectionKind, Cut, DesiredAccessEdge,
                                                    DesiredAccessTopology, Fixture, Leaf,
                                                    ProgramRole, Rect, Side, Split, Wing, ZoneSpec,
                                                    m_to_u)
from app.vertical_slice.wet_rooms import resolve_wet_rooms

STEP = 0.05
#: A door plus the engine's own two corner margins — the shared wall the two halls must really have.
DOOR_WALL_M = 1.1


def _g(v: float) -> float:
    return round(v / STEP) * STEP


def split_programme(spec):
    rooms = cg.build_room_program(spec)
    public = [r for r in rooms if r.role in (ProgramRole.LIVING, ProgramRole.DINING,
                                             ProgramRole.KITCHEN, ProgramRole.FAMILY_ROOM)]
    master = next((r for r in rooms if r.role is ProgramRole.MASTER_BEDROOM), None)
    beds = [r for r in rooms if r.role in (ProgramRole.BEDROOM, ProgramRole.SAFE_ROOM)]
    wets = [r for r in rooms if r.wet is not None]
    if master is None or not public or not beds or not wets:
        return None, "programme lacks a master, a public room, a bedroom or a wet room"
    ensuite = next((r for r in wets if r.entered_from == master.zone_id), None)
    shared = [r for r in wets if r is not ensuite]
    if not shared:
        return None, "no shared wet room to terminate the wing corridor"
    return (public, master, ensuite, beds, shared[0], shared[1:]), None


def _band(t, other):
    return cc._witness_band_m(t, other)


def size(public, master, ensuite, beds, end_wet, extra_wets, max_w, max_h):
    """Search the layout above; keep the largest plan that fits, never past any template band."""
    inset = cg._EDGE_INSET_ALLOWANCE_M
    best, reason = None, "no sizing found"
    k = len(beds)
    bed_min = max(r.template.min_short_side_m for r in beds) + inset

    for right_steps in range(0, 90):
        right_w = _g(bed_min + right_steps * STEP)
        if right_w > max_w:
            break
        bbands = [_band(r.template, right_w) for r in beds]
        if any(b is None for b in bbands):
            continue
        per_lo, per_hi = max(b[0] for b in bbands), min(b[1] for b in bbands)
        if per_lo > per_hi + 1e-9:
            continue
        per = _g(per_hi)                                   # bedrooms as generous as their own band

        for mw_steps in range(0, 90):                      # the master's own width inside the wing
            master_w = _g(master.template.min_short_side_m + inset + mw_steps * STEP)
            ens_w = _g(right_w - master_w)
            if ensuite is not None and ens_w < ensuite.template.min_short_side_m + inset:
                break
            mband = _band(master.template, master_w)
            if mband is None:
                continue
            if ensuite is not None:
                eband = _band(ensuite.template, ens_w)
                if eband is None:
                    continue
                md_lo, md_hi = max(mband[0], eband[0]), min(mband[1], eband[1])
            else:
                md_lo, md_hi = mband
            if md_lo > md_hi + 1e-9:
                continue
            master_d = _g(md_hi)
            beds_d = _g(per * k)
            right_h = _g(master_d + beds_d)

            for lw_steps in range(0, 30):                  # the corridor column's own width
                left_w = _g(max(1.2 + inset, DOOR_WALL_M) + lw_steps * STEP)
                total_w = _g(left_w + right_w)
                if total_w > max_w + 1e-9:
                    break
                wband = _band(end_wet.template, left_w)
                if wband is None:
                    continue
                wet_d = _g(min(wband[1], max(wband[0], end_wet.template.target_area_m2 / left_w)))
                # HALL_A spans EXACTLY the bedroom stack so every bedroom meets it along its full
                # width (a 0.50 m sliver is not a door); HALL_B then spans the master block, with
                # the shared wet room taking the rest and serving HALL_B's south end.
                ha = beds_d
                hb = _g(master_d - wet_d)
                if ha < 1.2 + inset or hb < 1.2 + inset:
                    continue
                tot = sum(r.template.target_area_m2 for r in public)
                shares = [max(STEP, total_w * r.template.target_area_m2 / tot) for r in public]
                pb_bands = [_band(r.template, w) for r, w in zip(public, shares)]
                if any(b is None for b in pb_bands):
                    reason = "no public-band depth suits every public room at its share of the width"
                    continue
                pb_lo, pb_hi = max(b[0] for b in pb_bands), min(b[1] for b in pb_bands)
                if pb_lo > pb_hi + 1e-9:
                    continue
                pb = _g(min(pb_hi, max(pb_lo, (max_h - right_h))))
                total_h = _g(pb + right_h)
                if total_h > max_h + 1e-9:
                    reason = f"the tree needs {total_w:.2f} x {total_h:.2f} m, deeper than the envelope"
                    continue
                dims = (total_w, total_h, pb, left_w, right_w, ha, hb, wet_d, master_w, ens_w,
                        master_d, per)
                if best is None or total_w * total_h > best[0]:
                    best = (total_w * total_h, dims)
    return (best[1], None) if best else (None, reason)


def compile_wing_master(spec, envelope: Rect):
    parts, why = split_programme(spec)
    if parts is None:
        return None, why
    public, master, ensuite, beds, end_wet, extra_wets = parts
    dims, why = size(public, master, ensuite, beds, end_wet, extra_wets,
                     cg.u_to_m(envelope.w), cg.u_to_m(envelope.h))
    if dims is None:
        return None, why
    (total_w, total_h, pb, left_w, right_w, ha, hb, wet_d, master_w, ens_w, master_d, per) = dims
    beds_d = _g(per * len(beds))

    def z(room):
        t = room.template
        return ZoneSpec(room.zone_id, (room.role,), t.min_area_m2, t.target_area_m2,
                        t.hard_max_area_m2 or t.max_area_m2, t.min_short_side_m, t.max_aspect_ratio)

    zones = [z(r) for r in public] + [
        ZoneSpec("HALL_A", (ProgramRole.HALL, ProgramRole.CIRCULATION), 4, 8, 26, 1.2, 8.0),
        ZoneSpec("HALL_B", (ProgramRole.HALL, ProgramRole.CIRCULATION), 4, 8, 26, 1.2, 8.0),
        z(master), z(end_wet)] + [z(r) for r in beds] + [z(r) for r in extra_wets]
    if ensuite is not None:
        zones.append(z(ensuite))

    L = Leaf
    V = lambda a, b, m: Split(Cut.V, a, b, m_to_u(m) if m is not None else None)
    H = lambda a, b, m: Split(Cut.H, a, b, m_to_u(m) if m is not None else None)

    def vchain(rooms, extent):
        node = L(rooms[-1].zone_id)
        tot = sum(r.template.target_area_m2 for r in rooms)
        for r in reversed(rooms[:-1]):
            node = V(L(r.zone_id), node, _g(extent * r.template.target_area_m2 / tot))
        return node

    top = vchain(public, total_w) if len(public) > 1 else L(public[0].zone_id)
    # the two corridors in ONE column, one above the other: their shared wall is the full width
    left_col = H(L("HALL_A"), H(L("HALL_B"), L(end_wet.zone_id), hb), ha)
    master_blk = V(L(master.zone_id), L(ensuite.zone_id), master_w) if ensuite is not None \
        else L(master.zone_id)
    # BEDROOMS FIRST, MASTER BLOCK LAST: the master block then sits on the building's south edge,
    # so the master has an exterior wall (C19) and a window (C8); with it at the top it was
    # landlocked between the public band, the hall and its own ensuite.
    node = L(beds[-1].zone_id)
    for r in reversed(beds[:-1]):
        node = H(L(r.zone_id), node, per)
    right_col = H(node, master_blk, beds_d)
    body = V(left_col, right_col, left_w)
    tree = H(top, body, pb)

    footprint = cg.footprint_of(envelope, total_w, total_h)
    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    open_plan = spec.program.open_plan_living
    edges = [DesiredAccessEdge("HALL_A", public[0].zone_id, ConnectionKind.CASED_OPENING)]
    for a, b in zip(public, public[1:]):
        edges.append(DesiredAccessEdge(a.zone_id, b.zone_id,
                                       ConnectionKind.OPEN_CONNECTION if open_plan else ConnectionKind.DOOR))
    edges += [DesiredAccessEdge("HALL_A", "HALL_B", ConnectionKind.DOOR),
              DesiredAccessEdge("HALL_B", master.zone_id, ConnectionKind.DOOR),
              DesiredAccessEdge("HALL_B", end_wet.zone_id, ConnectionKind.DOOR)]
    if ensuite is not None:
        edges.append(DesiredAccessEdge(master.zone_id, ensuite.zone_id, ConnectionKind.DOOR))
    for r in beds:
        edges.append(DesiredAccessEdge("HALL_A", r.zone_id, ConnectionKind.DOOR))
    for r in extra_wets:
        edges.append(DesiredAccessEdge("HALL_A", r.zone_id, ConnectionKind.DOOR))

    fixture = Fixture("BRANCHED_WING_MASTER", (wing,), tuple(zones),
                      DesiredAccessTopology(tuple(edges)),
                      open_groups=((tuple(r.zone_id for r in public),)
                                   if open_plan and len(public) > 1 else ()))
    concept = Concept(fixture, "HALL_A", Side.N, cg.u_to_m(footprint.w), cg.u_to_m(footprint.h))
    used = cg.u_to_m(footprint.w) * cg.u_to_m(footprint.h)
    return cg.ConceptCandidate(
        concept, cg.ConceptStrategy.BRANCHED_TWO_STACK, (0,),
        circulation_class=CirculationClass.BRANCHED,
        rationale="#185: compact entry hall over a wing corridor; master and ensuite in the wing",
        used_area_m2=round(used, 2),
        unused_wing_area_m2=round(envelope.area_m2() - used, 2),
        wet_rooms=resolve_wet_rooms(spec.program)), None
