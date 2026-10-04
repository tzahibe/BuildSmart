"""Issue #142H — architectural candidate selection in the production band pipeline.

The proven #142F findings, now production behaviour: entrance-aware orientation BEFORE realization
(never a fake entrance after), door-width-aware sizing (a required door must fit on the boundary the
sizing gives it), required contacts = spatial ∪ direct access (a contradiction is typed, never
silently fixed), mandatory-exposure filtering (REQUIRED is hard, PREFERRED is recorded only), and
compatibility with the #142G SAFE_ROOM RC walls. Every validator is unchanged.
"""
from __future__ import annotations

from app.vertical_slice.band_embedding import BandPlacement
from app.vertical_slice.band_pipeline import (
    HARD_FLAGS,
    PipelineDiagnosis,
    PipelineInput,
    PipelineSuccess,
    hard_rejections,
    input_warnings,
    orient,
    placement_flags,
    required_contacts,
    run_band_pipeline,
)
from app.vertical_slice.band_sizing import contact_requirements, door_contact_u, solve_band_layout
from app.vertical_slice.exposure_policy import EXPOSURE_POLICY, ExposureRequirement
from app.vertical_slice.geometry_core.model import ProgramRole, Side, WallType
from app.vertical_slice.rectilinear_realizer import (
    GridCell,
    GridWing,
    RealizationIntent,
    RealizedLayout,
    Refusal,
    ZoneIntent,
    realize_layout,
)
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.wet_rooms import ResolvedWetRoom


def _zi(zid, role, target, lo, hi, short=2.4, aspect=2.5):
    return ZoneIntent(zid, role, target, lo, hi, short, aspect)


LIVING = _zi("LIVING", ProgramRole.LIVING, 26.0, 16.0, 46.0, 3.0)
KITCHEN = _zi("KITCHEN", ProgramRole.KITCHEN, 13.0, 9.0, 26.0, 2.4)
HALL = _zi("HALL", ProgramRole.HALL, 7.0, 5.0, 12.0, 1.2, 4.0)
BED1 = _zi("BEDROOM_1", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6)
BED2 = _zi("BEDROOM_2", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6)
BED3 = _zi("BEDROOM_3", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6)
BATH = _zi("BATHROOM", ProgramRole.BATHROOM, 5.0, 3.5, 7.0, 1.6)
SAFE = _zi("SAFE_ROOM", ProgramRole.SAFE_ROOM, 10.5, 9.0, 14.0, 2.4)


def _zones(*zs):
    return {z.zone_id: z for z in zs}


def _rows(*bands):
    return tuple(tuple((z, 1) for z in band) for band in bands)


def _placement(*bands):
    n = max(len(b) for b in bands)
    rows = tuple(tuple((z, (n // len(b)) if i < len(b) - 1 else n - (n // len(b)) * (len(b) - 1)) for i, z in enumerate(b))
                 for b in bands)
    return BandPlacement(rows, n, 0.0, tuple(tuple(b) for b in bands))


def _realize(bands, zones, edges, access=(), wet=()):
    contacts = contact_requirements(zones, edges, access)
    sz = solve_band_layout(bands, zones, edges, w_max_m=16.0, h_max_m=16.0, min_contact_u=contacts)
    assert sz.status == "FEASIBLE", sz
    W, H = round(sum(sz.col_w_u) * 0.05, 2), round(sum(sz.row_h_u) * 0.05, 2)
    wing = GridWing("T", W, H, sz.n_cols, tuple(tuple(GridCell(z, s) for z, s in r) for r in sz.rows), zones,
                    access_pairs=tuple(access))
    return realize_layout(RealizationIntent(name="T", wings=(wing,), wet_rooms=tuple(wet))), sz


# --------------------------------------------------------------------------- 1. orientation

def test_entrance_band_in_the_last_row_is_flipped_before_realization():
    zones = _zones(LIVING, KITCHEN, HALL, BED1, BED2)
    # bedrooms in the (would-be) street band, the only entrance rooms at the back
    p = _placement(("BEDROOM_1", "BEDROOM_2"), ("HALL", "KITCHEN"), ("LIVING",))
    f = placement_flags(p, zones, ())
    assert f["entrance_now"] is False and f["entrance_flip"] is True and f["entrance_feasible"] is True
    q, oriented = orient(p, f)
    assert oriented and q.bands == tuple(reversed(p.bands)) and q.rows == tuple(reversed(p.rows))
    assert placement_flags(q, zones, ())["entrance_now"] is True
    edges = [("BEDROOM_1", "BEDROOM_2"), ("BEDROOM_1", "HALL"), ("BEDROOM_2", "HALL"), ("HALL", "KITCHEN"),
             ("HALL", "LIVING"), ("KITCHEN", "LIVING")]
    access = [("HALL", "BEDROOM_1"), ("HALL", "BEDROOM_2"), ("HALL", "KITCHEN"), ("LIVING", "HALL")]
    # the un-oriented layout has no entrance; the oriented one realizes with its front door into LIVING/HALL
    res_bad, _ = _realize(p.bands, zones, edges, access)
    assert isinstance(res_bad, Refusal) and res_bad.constraint == "NO_ENTRANCE", res_bad
    res_ok, _ = _realize(q.bands, zones, edges, access)
    assert isinstance(res_ok, RealizedLayout), res_ok
    assert res_ok.entrance_door.b in ("LIVING", "HALL")


def test_orientation_keeps_a_layout_that_already_fronts_the_street():
    zones = _zones(LIVING, HALL, BED1)
    p = _placement(("LIVING", "HALL"), ("BEDROOM_1",))
    q, oriented = orient(p, placement_flags(p, zones, ()))
    assert not oriented and q is p


def test_no_entrance_room_anywhere_is_a_typed_selection_diagnosis_not_a_fake_door():
    zones = _zones(KITCHEN, BED1, BED2)
    inp = PipelineInput("no-entrance", zones, (("KITCHEN", "BEDROOM_1"), ("BEDROOM_1", "BEDROOM_2")), (10.0, 8.0))
    res = run_band_pipeline(inp)
    assert isinstance(res, PipelineDiagnosis), res
    assert res.code == "NO_ENTRANCE" and res.stage == "SELECTION"
    assert res.candidates_tried > 0
    assert res.stage_histogram["SELECTION"]["entrance_feasible"] == res.candidates_tried
    assert all(r.stage_reached == "EMBEDDING" and "entrance_feasible" in r.rejected_by for r in res.records)


# --------------------------------------------------------------------------- 2. door-width-aware sizing

def test_contact_requirements_use_the_realizers_door_rule():
    zones = _zones(HALL, BED1, BATH)
    req = contact_requirements(zones, [("HALL", "BEDROOM_1"), ("HALL", "BATHROOM")], [("HALL", "BEDROOM_1")])
    assert req[frozenset(("HALL", "BEDROOM_1"))] == door_contact_u(ProgramRole.HALL, ProgramRole.BEDROOM) == 22  # 0.9 + 2*0.1 m
    assert req[frozenset(("HALL", "BATHROOM"))] == 1                                      # spatial only: any positive contact
    assert door_contact_u(ProgramRole.HALL, ProgramRole.TOILET) == 20                     # service door 0.8 + 2*0.1 m


def _overlaps(sz, pairs):
    P = [0]
    for w in sz.col_w_u:
        P.append(P[-1] + w)
    cells = {}
    for r, row in enumerate(sz.rows):
        c0 = 0
        for z, span in row:
            cells[z] = (r, c0, c0 + span); c0 += span
    out = {}
    for a, b in pairs:
        (ra, a0, a1), (rb, b0, b1) = cells[a], cells[b]
        out[(a, b)] = sz.row_h_u[ra] if ra == rb else P[min(a1, b1)] - P[max(a0, b0)]
    return out


# a hall beside the living room over two bedrooms: the hall must reach INTO the second bedroom. Plain
# topology contact lets it overlap by a single 5 cm unit (the proportional target keeps the hall small);
# a door from the hall into that bedroom needs 1.10 m of shared boundary, so the sizing must widen the hall
_HALL_NARROW = _zi("HALL", ProgramRole.HALL, 8.0, 4.0, 20.0, 1.2, 6.0)
_BANDS = (("HALL", "LIVING"), ("BEDROOM_1", "BEDROOM_2"))
_SPATIAL = [("HALL", "LIVING"), ("HALL", "BEDROOM_1"), ("HALL", "BEDROOM_2"), ("LIVING", "BEDROOM_2")]
_ACCESS = [("HALL", "BEDROOM_1"), ("HALL", "BEDROOM_2"), ("HALL", "LIVING")]


def test_door_aware_layout_sizing_gives_every_access_pair_its_door_width():
    zones = _zones(LIVING, _HALL_NARROW, BED1, BED2)
    plain = solve_band_layout(_BANDS, zones, _SPATIAL, w_max_m=16.0, h_max_m=16.0)
    assert plain.status == "FEASIBLE"
    assert min(_overlaps(plain, _ACCESS).values()) < 22      # topology contact alone: a door may not fit
    doors = solve_band_layout(_BANDS, zones, _SPATIAL, w_max_m=16.0, h_max_m=16.0,
                              min_contact_u=contact_requirements(zones, _SPATIAL, _ACCESS))
    assert doors.status == "FEASIBLE", doors
    assert all(v >= 22 for v in _overlaps(doors, _ACCESS).values()), _overlaps(doors, _ACCESS)


def test_door_aware_sizing_refuses_when_no_sizing_can_host_the_doors():
    tiny_hall = _zi("HALL", ProgramRole.HALL, 8.0, 4.0, 11.0, 1.2, 6.0)    # wide enough to touch, not to host the door
    zones = _zones(LIVING, tiny_hall, BED1, BED2)
    assert solve_band_layout(_BANDS, zones, _SPATIAL, w_max_m=16.0, h_max_m=16.0).status == "FEASIBLE"
    res = solve_band_layout(_BANDS, zones, _SPATIAL, w_max_m=16.0, h_max_m=16.0,
                            min_contact_u=contact_requirements(zones, _SPATIAL, _ACCESS))
    assert res.status == "INFEASIBLE", res                                  # a proof, before any realization


def test_realizer_resolve_honours_the_same_doors_and_places_them():
    """The GridWing carries its access pairs, so `_build_grid_wing`'s own re-solve (`_solve_grid`)
    keeps every declared pair's boundary >= its door and the unchanged door-ability rule then admits
    the pair — no mock injection (as the #142F harness needed) and no door patched on afterwards."""
    from app.vertical_slice import rectilinear_realizer as rr
    zones = _zones(LIVING, _HALL_NARROW, BED1, BED2)
    contacts = contact_requirements(zones, _SPATIAL, _ACCESS)
    sz = solve_band_layout(_BANDS, zones, _SPATIAL, w_max_m=16.0, h_max_m=16.0, min_contact_u=contacts)
    assert sz.status == "FEASIBLE", sz
    W, H = round(sum(sz.col_w_u) * 0.05, 2), round(sum(sz.row_h_u) * 0.05, 2)
    rows = tuple(tuple(GridCell(z, s) for z, s in r) for r in sz.rows)
    with_doors = rr._build_grid_wing(GridWing("T", W, H, sz.n_cols, rows, zones, access_pairs=tuple(_ACCESS)), (0, 0))
    assert not isinstance(with_doors, Refusal), with_doors
    doorable = {frozenset(e) for e in with_doors.access_edges}
    for a, b in _ACCESS:
        assert frozenset((a, b)) in doorable, (a, b, with_doors.access_edges)
        assert with_doors.rects[a].shared_edge_len_u(with_doors.rects[b]) >= 22
    # the same rows re-solved WITHOUT the pairs: the realizer's own widths leave HALL<->BEDROOM_2 door-less
    plain = rr._build_grid_wing(GridWing("T", W, H, sz.n_cols, rows, zones), (0, 0))
    assert not isinstance(plain, Refusal), plain
    assert frozenset(("HALL", "BEDROOM_2")) not in {frozenset(e) for e in plain.access_edges}


def test_same_band_door_bounds_the_band_depth():
    from app.vertical_slice.band_sizing import solve_band_sizing
    closet = _zi("STORAGE", ProgramRole.STORAGE, 1.0, 0.6, 1.4, 0.6, 3.0)      # could be 0.6 m deep on its own
    hall = _zi("HALL", ProgramRole.HALL, 3.0, 1.5, 4.0, 0.6, 6.0)
    zones = _zones(hall, closet)
    rows = ((("HALL", 3), ("STORAGE", 1)),)
    free = solve_band_sizing(rows, 4, zones, w_max_m=8.0, h_max_m=8.0)
    doors = solve_band_sizing(rows, 4, zones, w_max_m=8.0, h_max_m=8.0,
                              min_contact_u=contact_requirements(zones, [("HALL", "STORAGE")], [("HALL", "STORAGE")]))
    assert free.status == "FEASIBLE" and doors.status == "FEASIBLE"
    assert doors.row_h_u[0] >= 20                                            # service door 0.8 + 2 x 0.1 m


# --------------------------------------------------------------------------- 3. required contacts

def test_required_contacts_are_the_union_and_made_explicit():
    zones = _zones(LIVING, HALL, BED1)
    inp = PipelineInput("u", zones, (("LIVING", "HALL"),), (10.0, 8.0), access_edges=(("HALL", "BEDROOM_1"), ("ENTRANCE", "LIVING")))
    union, extra = required_contacts(inp)
    assert union == (("BEDROOM_1", "HALL"), ("HALL", "LIVING")) and extra == (("HALL", "BEDROOM_1"),)
    assert any(w.startswith("ACCESS_CONTACTS_REQUIRED") and "HALL->BEDROOM_1" in w for w in input_warnings(inp))


def test_access_that_contradicts_the_adjacency_is_a_typed_diagnosis():
    # the spatial graph is a path (embeds); the direct-access pairs complete it to a K4 (no rectangles)
    zones = _zones(LIVING, HALL, KITCHEN, _zi("DINING", ProgramRole.DINING, 10.0, 7.0, 14.0, 2.2))
    spatial = (("LIVING", "HALL"), ("HALL", "KITCHEN"), ("KITCHEN", "DINING"))
    access = (("LIVING", "KITCHEN"), ("LIVING", "DINING"), ("HALL", "DINING"))
    res = run_band_pipeline(PipelineInput("k4", zones, spatial, (12.0, 10.0), access_edges=access))
    assert isinstance(res, PipelineDiagnosis), res
    assert res.code == "ACCESS_SPATIAL_CONTRADICTION" and res.stage == "EMBEDDING"
    assert res.candidates_tried == 0                      # never a partial layout, never a silently dropped edge
    assert "TOPOLOGY_REPRESENTATION_LIMIT" in res.detail


def test_illegal_access_pair_is_a_policy_conflict_not_a_realizer_failure():
    zones = _zones(LIVING, HALL, BED1, BATH)
    wet = (ResolvedWetRoom("BATHROOM", WetRoomKind.SHARED_BATHROOM, None, WetRoomStrength.REQUIRED, True),)
    spatial = (("LIVING", "HALL"), ("HALL", "BEDROOM_1"), ("HALL", "BATHROOM"), ("LIVING", "BATHROOM"))
    access = (("LIVING", "HALL"), ("HALL", "BEDROOM_1"), ("LIVING", "BATHROOM"))     # a shared bathroom off the living room
    res = run_band_pipeline(PipelineInput("policy", zones, spatial, (12.0, 10.0), wet, access))
    assert isinstance(res, PipelineDiagnosis), res
    assert res.code == "ACCESS_POLICY_CONFLICT" and res.stage == "SELECTION"
    assert "LIVING->BATHROOM" in res.detail
    assert res.candidates_tried > 0 and all(r.stage_reached == "EMBEDDING" for r in res.records)


# --------------------------------------------------------------------------- 4. exposure

def test_required_exposure_is_hard_and_preferred_exposure_is_not():
    preferred_role = next(r for r, p in EXPOSURE_POLICY.items() if p.exterior_wall is ExposureRequirement.PREFERRED)
    none_role = next(r for r, p in EXPOSURE_POLICY.items() if p.exterior_wall is ExposureRequirement.NONE
                     and r not in (ProgramRole.HALL, ProgramRole.CIRCULATION, ProgramRole.ENTRANCE))
    pref = _zi("PREF", preferred_role, 10.0, 7.0, 14.0, 2.2)
    none = _zi("NONE", none_role, 6.0, 4.0, 9.0, 1.5)
    zones = _zones(LIVING, HALL, KITCHEN, BED1, BED2, pref, none)
    # 3 bands; the middle band's centre cell is buried
    buried_bed = _placement(("LIVING", "KITCHEN", "PREF"), ("HALL", "BEDROOM_1", "NONE"), ("BEDROOM_2",))
    f = placement_flags(buried_bed, zones, ())
    assert f["exposure_ok"] is False and f["buried_required"] == ["BEDROOM_1"]
    assert "exposure_ok" in hard_rejections(f)
    buried_pref = _placement(("LIVING", "KITCHEN", "BEDROOM_1"), ("HALL", "PREF", "NONE"), ("BEDROOM_2",))
    g = placement_flags(buried_pref, zones, ())
    assert g["exposure_ok"] is True and "exposure_ok" not in hard_rejections(g)
    assert g["preferred_total"] == 1 and g["preferred_on_envelope"] == 0        # recorded, never enforced
    buried_none = _placement(("LIVING", "KITCHEN", "BEDROOM_1"), ("HALL", "NONE", "PREF"), ("BEDROOM_2",))
    assert "exposure_ok" not in hard_rejections(placement_flags(buried_none, zones, ()))


def test_hard_flags_are_exactly_the_proven_set():
    assert HARD_FLAGS == ("entrance_feasible", "access_contact_ok", "exposure_ok", "reachable_from_entrance",
                          "safe_room_on_envelope")
    assert hard_rejections({k: None for k in HARD_FLAGS}) == ()          # not applicable never rejects


# --------------------------------------------------------------------------- 5. SAFE_ROOM compatibility

def test_safe_room_brief_passes_through_selection_with_rc_walls_and_doors():
    zones = _zones(LIVING, KITCHEN, HALL, BED1, BED2, SAFE)
    spatial = (("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("KITCHEN", "HALL"), ("HALL", "BEDROOM_1"),
               ("HALL", "SAFE_ROOM"), ("HALL", "BEDROOM_2"), ("SAFE_ROOM", "BEDROOM_2"))
    access = (("LIVING", "HALL"), ("LIVING", "KITCHEN"), ("HALL", "BEDROOM_1"), ("HALL", "BEDROOM_2"), ("HALL", "SAFE_ROOM"))
    res = run_band_pipeline(PipelineInput("safe", zones, spatial, (12.0, 10.0), access_edges=access))
    assert isinstance(res, PipelineSuccess), res
    rl = res.realized
    assert all(rl.walls[("SAFE_ROOM", s)] is WallType.RC_SAFE_ROOM for s in Side)
    assert next(c for c in rl.report.checks if c.check_id == "C4").passed
    assert res.access_preserved == "5/5" and res.access_lost == ()
    assert any(d.placeable and "SAFE_ROOM" in (d.a, d.b) for d in rl.interior_doors)
    assert rl.rects["SAFE_ROOM"].shared_edge_len_u(rl.rects["HALL"]) >= 22
    assert any(w.placeable and w.zone_id == "SAFE_ROOM" for w in rl.windows)
    assert res.records[res.candidate_index].flags["safe_room_on_envelope"] is True


# --------------------------------------------------------------------------- funnel / determinism

def test_rejected_candidates_are_never_sized_or_realized_and_the_result_is_deterministic():
    zones = _zones(LIVING, KITCHEN, HALL, BED1, BED2, BATH)
    wet = (ResolvedWetRoom("BATHROOM", WetRoomKind.SHARED_BATHROOM, None, WetRoomStrength.REQUIRED, True),)
    spatial = (("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("HALL", "BEDROOM_1"), ("HALL", "BEDROOM_2"), ("HALL", "BATHROOM"),
               ("BEDROOM_1", "BATHROOM"))
    access = (("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("HALL", "BEDROOM_1"), ("HALL", "BEDROOM_2"), ("HALL", "BATHROOM"))
    inp = PipelineInput("funnel", zones, spatial, (12.0, 10.0), wet, access)
    a, b = run_band_pipeline(inp), run_band_pipeline(inp)
    assert isinstance(a, PipelineSuccess), a
    for r in a.records:
        if r.rejected_by:
            assert r.stage_reached == "EMBEDDING" and r.refusal == "SELECTION_REJECTED"
    # every candidate is either HARD-rejected (recorded) or HARD-feasible; a pass returns before the rest are recorded
    assert a.selection["hard_feasible"] + sum(1 for r in a.records if r.rejected_by) == a.selection["candidates"]
    assert a.access_preserved == "5/5"
    assert a.placement.rows == b.placement.rows and a.candidate_index == b.candidate_index
    assert {k: (r.x, r.y, r.w, r.h) for k, r in a.realized.rects.items()} == \
           {k: (r.x, r.y, r.w, r.h) for k, r in b.realized.rects.items()}
