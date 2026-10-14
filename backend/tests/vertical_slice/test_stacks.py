"""The 2D wing's minimal form (ADR-001 path B, #197): a stack of two small rooms in one band
column — the embedding sees one pseudo-zone, the sizer sizes the members, the geometry expands."""
from app.ai_harness.shape_agnostic.stacks import (
    PSEUDO_PREFIX,
    expand_rects,
    expand_wings,
    merge_stack,
    propose_stacks,
)
from app.vertical_slice.geometry_core.model import ProgramRole as R
from app.vertical_slice.geometry_core.model import Rect
from tests.vertical_slice.test_spine_embedding import _hub_programme, _z


def _programme_with_wc():
    zones, edges = _hub_programme()
    zones["WC"] = _z("WC", R.TOILET, 4, 3.5, 5.5, 1.4, 2.5)
    return zones, edges + [("HALL", "WC")]


def test_only_small_stackable_rooms_are_proposed_both_orders_shared_neighbour_first():
    zones, edges = _programme_with_wc()
    assert propose_stacks(zones, edges) == [("BATH", "WC"), ("WC", "BATH")]
    zones["STORE"] = _z("STORE", R.STORAGE, 3, 2, 4, 1.2, 3.0)         # no neighbour shared with the wet rooms
    out = propose_stacks(zones, edges)
    assert out[0] == ("BATH", "WC") and set(out) == {("BATH", "WC"), ("WC", "BATH"), ("BATH", "STORE"), ("STORE", "BATH"),
                                                      ("WC", "STORE"), ("STORE", "WC")}


def test_a_merged_stack_is_one_pseudo_zone_with_the_union_of_contacts_and_summed_bounds():
    zones, edges = _programme_with_wc()
    access = [("HALL", "BATH"), ("HALL", "WC"), ("HALL", "LIVING")]
    z2, e2, a2, pid = merge_stack(zones, edges, access, ("BATH", "WC"))
    assert pid == PSEUDO_PREFIX + "BATH+WC"
    assert "BATH" not in z2 and "WC" not in z2 and pid in z2
    assert z2[pid].target_area_m2 == 10 and z2[pid].min_area_m2 == 8.5 and z2[pid].max_area_m2 == 13.5
    assert z2[pid].min_short_side_m == 1.6                                 # the wider member's
    assert sorted(e for e in e2 if pid in e) == [("HALL", pid)]            # one contact, not two
    assert sorted(e for e in a2 if pid in e) == [("HALL", pid)]
    assert all(pid in e or ("BATH" not in e and "WC" not in e) for e in e2 + a2)


def test_expand_rects_splits_the_column_top_to_bottom_at_the_members_heights():
    rects = {"HALL": Rect(0, 0, 100, 60), "STACK:BATH+WC": Rect(100, 0, 40, 60)}
    out = expand_rects(rects, {"STACK:BATH+WC": ("BATH", "WC")}, {"BATH": 36, "WC": 24})
    assert out["BATH"] == Rect(100, 0, 40, 36) and out["WC"] == Rect(100, 36, 40, 24)
    assert out["HALL"] == rects["HALL"] and "STACK:BATH+WC" not in out


def test_expand_wings_makes_the_column_its_own_wing_and_splits_the_band_around_it():
    band = (Rect(0, 0, 200, 60),)
    rects = {"A": Rect(0, 0, 60, 60), "STACK:B+C": Rect(60, 0, 40, 60), "D": Rect(100, 0, 100, 60)}
    wings = expand_wings(band, rects, {"STACK:B+C": ("B", "C")})
    assert wings == (Rect(0, 0, 60, 60), Rect(60, 0, 40, 60), Rect(100, 0, 100, 60))
    assert sum(w.w for w in wings) == 200


def test_a_stack_sizes_realizes_and_frees_the_hall(monkeypatch):
    """The exact sizer expands the pseudo-column into two members with their own heights; the
    realizer sees two ordinary cells (every contact and door kept) — and the hall, no longer
    forced to the wet rooms' band depth, is sized at its own target rather than as the sink."""
    import pytest
    pytest.importorskip("scipy")
    from app.ai_harness.shape_agnostic.milp_oracle import (
        milp_placement,
        placement_rects,
    )
    from app.vertical_slice.band_embedding import BandEmbedding, embed_band
    from app.vertical_slice.band_sizing import contact_requirements
    from app.vertical_slice.envelope import Envelope
    from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
    from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
    from app.vertical_slice.topology_preservation import (
        measure_access_graph,
        measure_spatial_adjacency,
    )
    from app.vertical_slice.wet_rooms import ResolvedWetRoom

    zones, edges = _programme_with_wc()
    access = [("HALL", "LIVING"), ("LIVING", "KITCHEN"), ("HALL", "BED1"), ("HALL", "BED2"), ("HALL", "MASTER"),
              ("HALL", "BATH"), ("HALL", "WC")]
    wet = (ResolvedWetRoom("BATH", WetRoomKind.SHARED_BATHROOM, None, WetRoomStrength.REQUIRED, False),
           ResolvedWetRoom("WC", WetRoomKind.GUEST_WC, None, WetRoomStrength.REQUIRED, False))
    stack = ("BATH", "WC")
    z2, e2, a2, pid = merge_stack(zones, edges, access, stack)
    union2 = sorted({tuple(sorted(e)) for e in e2} | {tuple(sorted(e)) for e in a2})
    union_m = sorted({tuple(sorted(e)) for e in edges} | {tuple(sorted(e)) for e in access})
    contacts = contact_requirements(zones, union_m, access)
    emb = embed_band(z2, union2, max_candidates=60)
    assert isinstance(emb, BandEmbedding)
    env = Envelope.rectangle(14, 12)
    stacks = {pid: (zones["BATH"], zones["WC"])}
    for cand in emb.candidates:
        o = milp_placement(cand.bands, z2, union_m, env, min_contact_u=contacts, objective="target", stacks=stacks)
        if o.status != "FEASIBLE":
            continue
        sz = o.as_sizing()
        rects, intents = placement_rects(cand.bands, z2, o, stacks)
        bath, wc = rects["BATH"], rects["WC"]
        assert (bath.x, bath.w) == (wc.x, wc.w) and bath.y2 == wc.y, (bath, wc)        # one column, stacked
        assert bath.h + wc.h == sz.rects(cand.bands)[pid].h
        wings = expand_wings(sz.band_rects(cand.bands), sz.rects(cand.bands), {pid: stack})
        out = realize_cells("stack", rects, intents, wings, access, wet_rooms=wet)
        if not isinstance(out, RealizedLayout):
            continue
        sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in edges))
        ac = measure_access_graph(out.fixture.access.edges, access)
        assert sp.preserved == sp.requested and ac.preserved == ac.requested
        hall = next(r.net_area_m2 for r in out.design.rooms if r.zone_id == "HALL")
        assert hall <= zones["HALL"].target_area_m2 + 2.0, hall        # at its target, not the sink
        return
    pytest.fail("no stacked candidate realized")
