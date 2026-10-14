"""Path B (ADR-001, #197): the spine embedding's facts — each one a downstream rule read off the
realizer (`doors.resolve_entrance`, C22), never a new rule of its own."""
from app.ai_harness.shape_agnostic.spine import SpineLayout, choose_spine, embed_spine
from app.vertical_slice.geometry_core.model import ProgramRole as R
from app.vertical_slice.stage2.contract import ZoneIntent


def _z(i, role, t, lo, hi, ss=2.4, asp=2.5):
    return ZoneIntent(zone_id=i, role=role, donor_room_id=None, target_area_m2=t, min_area_m2=lo, max_area_m2=hi,
                      min_short_side_m=ss, max_aspect_ratio=asp)


def _hub_programme():
    zones = {"HALL": _z("HALL", R.HALL, 14, 9, 24, 1.6, 3.0), "LIVING": _z("LIVING", R.LIVING, 32, 26, 40, 3.5, 2.0),
             "KITCHEN": _z("KITCHEN", R.KITCHEN, 14, 11, 18), "BED1": _z("BED1", R.BEDROOM, 13, 11, 16, 2.6, 1.8),
             "BED2": _z("BED2", R.BEDROOM, 13, 11, 16, 2.6, 1.8),
             "MASTER": _z("MASTER", R.MASTER_BEDROOM, 17, 14, 20, 3.0, 1.8),
             "BATH": _z("BATH", R.BATHROOM, 6, 5, 8, 1.6, 2.2)}
    edges = [("HALL", "LIVING"), ("LIVING", "KITCHEN"), ("HALL", "BED1"), ("HALL", "BED2"), ("HALL", "MASTER"),
             ("HALL", "BATH"), ("BED1", "BED2")]
    return zones, edges


def _neighbours(edges, spine):
    return {b if a == spine else a for a, b in edges if spine in (a, b)}


def test_the_spine_is_the_circulation_hub():
    zones, edges = _hub_programme()
    assert choose_spine(zones, edges) == "HALL"
    assert choose_spine({k: v for k, v in zones.items() if k != "HALL"}, edges) is None


def test_every_layout_places_each_room_exactly_once():
    zones, edges = _hub_programme()
    layouts = embed_spine(zones, edges, "HALL")
    assert layouts
    for lay in layouts:
        assert sorted(lay.cells) == sorted(zones)


def test_every_spine_neighbour_touches_the_spine_by_construction():
    """Innermost on its side, or in the plain band that touches the section's end."""
    zones, edges = _hub_programme()
    nbrs = _neighbours(edges, "HALL")
    for lay in embed_spine(zones, edges, "HALL"):
        a, b = lay.section
        touching = set()
        for left, right in lay.bands:
            if left:
                touching.add(left[-1])
            if right:
                touching.add(right[0])
        if lay.top:
            touching |= set(lay.top[-1])
        if lay.bottom:
            touching |= set(lay.bottom[0])
        assert nbrs <= touching, (lay, nbrs - touching)


def test_c22_an_occupied_left_and_right_side_run_the_same_number_of_bands():
    zones, edges = _hub_programme()
    for lay in embed_spine(zones, edges, "HALL"):
        lefts = [bool(l) for l, _ in lay.bands]
        rights = [bool(r) for _, r in lay.bands]
        assert all(lefts) or not any(lefts), lay
        assert all(rights) or not any(rights), lay


def test_the_street_band_holds_an_arrival_room():
    """A section that starts below a plain band leaves the front door to that band: it must hold
    a HALL / CIRCULATION / LIVING (the realizer's `ENTRANCE_ZONE_PRIORITY`)."""
    zones, edges = _hub_programme()
    arrival = {R.HALL, R.CIRCULATION, R.LIVING}
    seen_top = False
    for lay in embed_spine(zones, edges, "HALL", max_candidates=200):
        if lay.top:
            seen_top = True
            assert any(zones[z].role in arrival for z in lay.top[0]), lay
    assert seen_top


def test_a_component_that_never_reaches_the_spine_has_no_layout():
    zones, edges = _hub_programme()
    edges = [e for e in edges if e != ("HALL", "BATH")]      # BATH now hangs off nothing
    assert embed_spine(zones, edges, "HALL") == []


def test_the_layouts_with_the_fewest_rows_come_first():
    zones, edges = _hub_programme()
    rows = [lay.n_rows for lay in embed_spine(zones, edges, "HALL")]
    assert rows == sorted(rows)
    assert rows[0] <= 3


def test_row_of_and_section_agree_with_the_layout():
    lay = SpineLayout("HALL", ((("KITCHEN",), ("BED1",)), (("LIVING",), ("BED2",))), top=(), bottom=(("BATH", "MASTER"),))
    assert lay.section == (0, 2) and lay.n_rows == 3
    assert lay.row_of("LIVING") == 1 and lay.row_of("MASTER") == 2
