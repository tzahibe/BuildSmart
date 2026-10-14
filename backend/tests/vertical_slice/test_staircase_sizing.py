"""The shape-agnostic sizer and its envelope (ADR-001, #197).

What is pinned here is the CONTRACT, not a shape: the envelope answers one question exactly, the
staircase sizer finds a layout where the same band pipeline's one-width-for-all-bands rule cannot,
a step only ever lands on a cell boundary of the neighbouring band (the "PARTIAL seam" C22
rejects), a split extent is refused as its own typed status, and nothing here names a letter.
"""
from app.vertical_slice.band_sizing import contact_requirements, solve_band_layout
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.geometry_core.model import ProgramRole as R, Rect
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
from app.vertical_slice.stage2.contract import ZoneIntent
from app.vertical_slice.staircase_sizing import solve_staircase_layout
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency

L_ENVELOPE = Envelope(((0, 0), (14, 0), (14, 9), (8, 9), (8, 16), (0, 16)))
COURT = Envelope(((0, 0), (16, 0), (16, 15), (11, 15), (11, 9), (5, 9), (5, 15), (0, 15)))


def _z(i, role, t, lo, hi, ss=2.4, asp=2.5):
    return ZoneIntent(zone_id=i, role=role, donor_room_id=None, target_area_m2=t, min_area_m2=lo,
                      max_area_m2=hi, min_short_side_m=ss, max_aspect_ratio=asp)


def _two_band_programme():
    zones = {"LIVING": _z("LIVING", R.LIVING, 30, 24, 38, 3.5, 2.0),
             "KITCHEN": _z("KITCHEN", R.KITCHEN, 13, 10, 17, 2.4, 2.5),
             "HALL": _z("HALL", R.HALL, 10, 8, 14, 1.6, 3.0),
             "BED1": _z("BED1", R.BEDROOM, 13, 11, 16, 2.6, 1.8)}
    bands = (("LIVING", "KITCHEN"), ("HALL", "BED1"))
    required = [("LIVING", "KITCHEN"), ("HALL", "BED1"), ("LIVING", "HALL"), ("KITCHEN", "BED1")]
    access = [("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("HALL", "BED1")]
    return zones, bands, required, access


# ------------------------------------------------------------------- the envelope

def test_a_rectangle_is_the_degenerate_envelope():
    e = Envelope.rectangle(12, 18)
    assert e.is_orthogonal and e.width_u == 240 and e.depth_u == 360
    assert e.extent_u(0, 360) == [(0, 240)]


def test_the_l_envelope_narrows_exactly_at_its_step_and_is_conservative_over_a_range():
    assert L_ENVELOPE.extent_u(0, 180) == [(0, 280)]          # above the step: the full width
    assert L_ENVELOPE.extent_u(180, 320) == [(0, 160)]        # below it: the leg only
    assert L_ENVELOPE.extent_u(0, 320) == [(0, 160)]          # a range crossing the step: the intersection


def test_a_court_is_reported_as_two_intervals_never_collapsed():
    assert COURT.extent_u(0, 180) == [(0, 320)]
    assert COURT.extent_u(190, 300) == [(0, 100), (220, 320)]


def test_a_non_orthogonal_polygon_is_refused_by_the_sizer():
    zones, bands, required, _ = _two_band_programme()
    slanted = Envelope(((0, 0), (14, 0), (12, 16), (0, 16)))
    assert not slanted.is_orthogonal
    assert solve_staircase_layout(bands, zones, required, slanted).status == "INFEASIBLE"


# ------------------------------------------------------------------- the sizer

def test_a_rectangle_that_fits_comes_out_flush_not_stepped():
    """The objective: a step is a decision a constraint forced, never decoration."""
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    s = solve_staircase_layout(bands, zones, required, Envelope.rectangle(10, 9),
                               min_contact_u=contact_requirements(zones, union, access))
    assert s.status == "FEASIBLE", s.detail
    wings = s.band_rects(bands)
    assert len({(w.x, w.w) for w in wings}) == 1, [(w.x, w.w) for w in wings]


def test_the_leg_of_an_l_forces_a_step_and_every_band_stays_inside_the_envelope():
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    s = solve_staircase_layout(bands, zones, required, L_ENVELOPE,
                               min_contact_u=contact_requirements(zones, union, access))
    assert s.status == "FEASIBLE", s.detail
    for w in s.band_rects(bands):
        assert L_ENVELOPE.contains_rect_u(w), w


def test_a_step_lands_on_a_cell_boundary_of_the_band_above_or_outside_it():
    """The C22 rule, stated without a shape: no cell side is part exterior and part shared."""
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    s = solve_staircase_layout(bands, zones, required, L_ENVELOPE,
                               min_contact_u=contact_requirements(zones, union, access))
    assert s.status == "FEASIBLE", s.detail
    above, below = s.band_x_u[0], s.band_x_u[1]
    for endpoint in (below[0], below[-1]):
        inside = above[0] < endpoint < above[-1]
        assert not inside or endpoint in above, (endpoint, above)


def test_a_court_is_refused_as_band_gap_not_as_a_timeout_or_a_distorted_plan():
    zones, bands, required, access = _two_band_programme()
    deep = {k: _z(k, v.role, v.target_area_m2, v.min_area_m2, v.max_area_m2, v.min_short_side_m,
                  v.max_aspect_ratio) for k, v in zones.items()}
    # three bands so that one must sit at the court's depth
    bands3 = (("LIVING", "KITCHEN"), ("HALL",), ("BED1",))
    req3 = [("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("HALL", "BED1")]
    s = solve_staircase_layout(bands3, deep, req3, COURT)
    assert s.status != "UNKNOWN", s.detail
    if s.status == "FEASIBLE":
        # a house that fits ABOVE the court is a legitimate answer; one that crosses it is not
        assert sum(s.row_h_u) <= 180, s.row_h_u
    else:
        # typed, and the refusal says the search never used the depth beyond the split
        assert s.status in ("BAND_GAP", "ALIGNMENT_UNSAT"), (s.status, s.detail)
        assert "split" in s.detail, s.detail
    # the unaligned family is feasible above the court: the court itself is not the obstacle
    free = solve_staircase_layout(bands3, deep, req3, COURT, align=False)
    assert free.status == "FEASIBLE" and sum(free.row_h_u) <= 180, (free.status, free.detail)
    # and a programme too deep to sit above the court is refused as the gap it is, instantly
    tall = {k: _z(k, v.role, v.target_area_m2 * 3, v.min_area_m2 * 3, v.max_area_m2 * 3,
                  v.min_short_side_m, v.max_aspect_ratio) for k, v in zones.items()}
    t = solve_staircase_layout(bands3, tall, req3, COURT)
    assert t.status in ("BAND_GAP", "ALIGNMENT_UNSAT"), (t.status, t.detail)
    assert "split" in t.detail or "two intervals" in t.detail, t.detail


def test_per_band_widths_strictly_enlarge_what_the_one_width_band_sizer_can_do():
    """Measured, not asserted from theory: the same input, the same bounds; the band sizer forces
    every band to one width and refuses, the staircase sizer does not."""
    zones = {"ENTRY": _z("ENTRY", R.CIRCULATION, 5, 4, 7, 1.5, 2.5),
             "LIVING": _z("LIVING", R.LIVING, 32, 26, 40, 3.5, 2.0),
             "KITCHEN": _z("KITCHEN", R.KITCHEN, 14, 11, 18, 2.4, 2.5),
             "HALL": _z("HALL", R.HALL, 12, 9, 16, 1.6, 3.0),
             "BED1": _z("BED1", R.BEDROOM, 13, 11, 16, 2.6, 1.8),
             "BED2": _z("BED2", R.BEDROOM, 13, 11, 16, 2.6, 1.8),
             "MASTER": _z("MASTER", R.MASTER_BEDROOM, 17, 14, 20, 3.0, 1.8),
             "BATH": _z("BATH", R.BATHROOM, 6, 5, 8, 1.6, 2.2)}
    bands = (("ENTRY", "LIVING", "KITCHEN"), ("HALL", "BATH"), ("BED1", "MASTER", "BED2"))
    required = [("ENTRY", "LIVING"), ("LIVING", "KITCHEN"), ("ENTRY", "HALL"), ("HALL", "BATH"),
                ("HALL", "BED1"), ("HALL", "MASTER"), ("HALL", "BED2"), ("LIVING", "HALL")]
    one_width = solve_band_layout(bands, zones, required, w_max_m=14, h_max_m=16)
    assert one_width.status == "INFEASIBLE"
    free = solve_staircase_layout(bands, zones, required, Envelope.rectangle(14, 16), align=False)
    assert free.status == "FEASIBLE", free.detail


# ------------------------------------------------------------------- end to end

def test_the_realized_l_passes_the_unchanged_validators_and_preserves_every_contact_and_door():
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    s = solve_staircase_layout(bands, zones, required, L_ENVELOPE,
                               min_contact_u=contact_requirements(zones, union, access))
    assert s.status == "FEASIBLE", s.detail
    out = realize_cells("L", s.rects(bands), zones, s.band_rects(bands), access)
    assert isinstance(out, RealizedLayout), getattr(out, "detail", out)
    assert out.ok
    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in required))
    ac = measure_access_graph(out.fixture.access.edges, access)
    assert sp.preserved == sp.requested and ac.preserved == ac.requested, (sp, ac)
    assert len(out.design.footprints_m) == len(s.band_rects(bands))


# ------------------------------------------------------------------- the two orientations

ENTRY_COURT = Envelope(((0, 0), (6, 0), (6, 5), (11, 5), (11, 0), (17, 0), (17, 16), (0, 16)))


def test_a_split_at_the_street_edge_is_an_entry_court_and_the_building_starts_below_it():
    """A notch on the street side splits the envelope from depth 0: the building may not start
    there, so it starts at the first depth where the envelope is one interval — and its own
    street wall is then its top edge. The street-side court is outside the building's box."""
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    assert ENTRY_COURT.split_depth_windows_u() == [(0, 100)]
    s = solve_staircase_layout(bands, zones, required, ENTRY_COURT,
                               min_contact_u=contact_requirements(zones, union, access))
    assert s.status == "FEASIBLE", s.detail
    assert s.y_start_u == 100
    for w in s.band_rects(bands):
        assert w.y >= 100 and ENTRY_COURT.contains_rect_u(w), w
    out = realize_cells("court", s.rects(bands), zones, s.band_rects(bands), access)
    assert isinstance(out, RealizedLayout), getattr(out, "detail", out)
    assert out.ok


def test_the_same_algorithm_on_the_transposed_envelope_gives_bands_across_the_street():
    """A wide, shallow envelope cannot hold bands along the street deep enough for the rooms;
    transposing the envelope, solving, and transposing back is the same algorithm with bands
    across it — no second solver, no shape named. Contacts and doors survive the round trip."""
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    strip = Envelope.rectangle(24, 7.5)
    transposed = Envelope(tuple((y, x) for x, y in strip.vertices_m))
    s = solve_staircase_layout(bands, zones, required, transposed,
                               min_contact_u=contact_requirements(zones, union, access))
    assert s.status == "FEASIBLE", s.detail
    back = {z: Rect(r.y, r.x, r.h, r.w) for z, r in s.rects(bands).items()}
    wings = tuple(Rect(r.y, r.x, r.h, r.w) for r in s.band_rects(bands))
    for w in wings:
        assert strip.contains_rect_u(w), w
    assert len({w.x for w in wings}) == len(wings), "bands lie side by side across the street"
    out = realize_cells("strip", back, zones, wings, access)
    assert isinstance(out, RealizedLayout), getattr(out, "detail", out)
    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in required))
    ac = measure_access_graph(out.fixture.access.edges, access)
    assert sp.preserved == sp.requested and ac.preserved == ac.requested, (sp, ac)
