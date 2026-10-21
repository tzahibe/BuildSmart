"""Issue #221 — `realize_cells` expresses an OPEN interface between two adjacent cells.

THE DEFECT these tests pin. `realize_cells` created `open_pairs` empty and never added to it, so
no plan the brain produced carried an open interface: `Fixture.open_groups` was always `()`, the
demo payload's `open_interfaces` was always empty, and an open-plan brief was drawn with a wall
and a door between living, dining and kitchen (#213: 0 open interfaces in 56 of 56 brain payloads,
0 of 9 open-plan briefs drawn as open plan, against production's 9 of 9).

WHAT IS *NOT* BEING DONE HERE, and the tests say so structurally. The module's own PARTIAL
ABUTMENTS comment records a measured refusal: splitting ONE room into same-zone OPEN-walled
fragments is rejected by C20/C9/C24/C31, so a layout whose steps do not land on cell boundaries is
refused rather than fragmented. This Issue marks the interface between TWO WHOLE, SEPARATE cells
that already share a complete wall segment —
`test_opening_an_interface_creates_no_cell_and_moves_no_geometry` is the check that it stays that
way: the cell decomposition, every rectangle and `zone_of_cell`/`groups` are identical with the
declaration and without it. Only the wall type on one side of each of the two cells changes.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.ai_harness.shape_agnostic.cells import from_bands
from app.vertical_slice.geometry_core.model import ProgramRole as R
from app.vertical_slice.geometry_core.model import Rect, Side, WallType, m_to_u
from app.vertical_slice.rectilinear_realizer import (
    RealizedLayout,
    _open_cell_pairs,
    realize_cells,
)
from tests.vertical_slice.test_spine_embedding import _hub_programme

#: The doors `_hub_programme`'s rooms ask for — the same list `test_cells.py` uses.
ACCESS = [("HALL", "LIVING"), ("LIVING", "KITCHEN"), ("HALL", "BED1"), ("HALL", "BED2"),
          ("HALL", "MASTER"), ("HALL", "BATH")]

#: The declared group under test: production's own open-plan group for a two-public-room brief
#: (`concept_compilers`: `open_groups = (("LIVING", "KITCHEN"),) if open_plan`).
LIVING_KITCHEN = (("LIVING", "KITCHEN"),)


def _union(edges):
    return sorted({tuple(sorted(e)) for e in edges} | {tuple(sorted(e)) for e in ACCESS})


@pytest.fixture(scope="module")
def placed():
    """A REAL exact placement of a band layout whose LIVING and KITCHEN are neighbours in one row.

    Nothing is hand-placed: the embedding, the MILP placement and the cell geometry are the
    production/brain path's own (`embed_band` -> `cells_placement` -> `cells_rects`), so the
    rectangles under test are rectangles the sizer actually produces.
    """
    pytest.importorskip("scipy")
    from app.ai_harness.shape_agnostic.milp_cells import (
        cells_placement,
        cells_rects,
        cells_wings,
    )
    from app.vertical_slice.band_embedding import embed_band
    from app.vertical_slice.band_sizing import contact_requirements
    from app.vertical_slice.envelope import Envelope
    from tests.vertical_slice.test_milp_spine import WET

    zones, edges = _hub_programme()
    union = _union(edges)
    contacts = contact_requirements(zones, union, ACCESS)
    env = Envelope.rectangle(14, 12)
    arrival = {R.HALL, R.CIRCULATION, R.LIVING}
    for cand in embed_band(zones, union, max_candidates=40).candidates:
        # both orientations, exactly as `exact_pipeline._orientations` flips a candidate so the
        # entrance band fronts the street
        for bands in (cand.bands, tuple(reversed(cand.bands))):
            lay = from_bands(bands)
            if not any(zones[z].role in arrival for z in lay.rows[0]):
                continue                        # production's own entrance screen
            res = cells_placement(lay, zones, union, env, min_contact_u=contacts, k=6)
            if res.status != "FEASIBLE":
                continue
            rects, wings = cells_rects(lay, res), cells_wings(lay, res)
            closed = realize_cells("closed", dict(rects), zones, wings, ACCESS, wet_rooms=WET)
            if not isinstance(closed, RealizedLayout):
                continue
            out = realize_cells("open", dict(rects), zones, wings, ACCESS, wet_rooms=WET,
                                open_groups=LIVING_KITCHEN)
            if not isinstance(out, RealizedLayout) or not out.fixture.open_groups:
                continue                        # this placement cannot express the pair; try the next
            return {"zones": zones, "rects": rects, "wings": wings, "wet": WET, "closed": closed}
    pytest.fail("no band placement realized with LIVING and KITCHEN fully adjacent")


def _opened(placed, groups):
    return realize_cells("open", dict(placed["rects"]), placed["zones"], placed["wings"], ACCESS,
                         wet_rooms=placed["wet"], open_groups=groups)


# --------------------------------------------------------------- AC-1: the group is named at all

def test_the_closed_plan_is_the_defect_this_issue_fixes(placed):
    """Without a declared group nothing opens — the behaviour before this Issue, unchanged."""
    assert placed["closed"].fixture.open_groups == ()
    assert placed["closed"].design.open_groups == ()


def test_a_declared_open_pair_of_adjacent_cells_is_named_on_the_design(placed):
    out = _opened(placed, LIVING_KITCHEN)
    assert isinstance(out, RealizedLayout), getattr(out, "detail", out)
    assert out.fixture.open_groups == (("KITCHEN", "LIVING"),)
    # the same pair production reports for the same group, and the group the payload reads
    assert out.design.open_groups == (("KITCHEN", "LIVING"),)


def test_the_brains_programme_carries_the_briefs_own_open_plan_intent():
    """AC-1's first half: the intent reaches the realizer through the programme, not a side
    channel. The group is the brief's public chain, by the brief's own semantics — no room is
    named in the code that builds it."""
    from app.vertical_slice.brain.proposer import programme_from_spec
    from tests.vertical_slice.test_brain import _brief, _spec_and_footprint

    spec, fp = _spec_and_footprint("B08")                      # an open-plan brief
    assert _brief("B08").open_plan and spec.program.open_plan_living
    prog = programme_from_spec(spec, fp)
    assert prog.open_plan and prog.open_group == prog.public and len(prog.open_group) > 1

    closed = replace(spec, program=replace(spec.program, open_plan_living=False))
    assert programme_from_spec(closed, fp).open_group == ()


# ------------------------------------------- AC-2: the interface is OPEN, with nothing placed on it

def test_the_shared_interface_is_open_on_both_cells(placed):
    out = _opened(placed, LIVING_KITCHEN)
    a, b = "LIVING", "KITCHEN"
    ra, rb = out.rects[a], out.rects[b]
    opened = [(z, side) for (z, side), kind in out.walls.items()
              if kind is WallType.OPEN and z in (a, b)]
    assert len(opened) == 2, opened                            # exactly one side of each cell
    assert {z for z, _ in opened} == {a, b}
    # and it is the side they actually share, covering the whole of it
    sides = dict(opened)
    horizontal = sides[a] in (Side.E, Side.W)
    shared = ra.shared_edge_len_u(rb)
    assert shared == (ra.h if horizontal else ra.w) == (rb.h if horizontal else rb.w)


def test_no_door_and_no_window_lands_on_an_open_interface(placed):
    out = _opened(placed, LIVING_KITCHEN)
    pair = frozenset(("LIVING", "KITCHEN"))
    assert not [d for d in out.interior_doors if frozenset((d.a, d.b)) == pair]
    # the closed plan DID have that door — this is the change, not an accident of the layout
    assert [d for d in placed["closed"].interior_doors if frozenset((d.a, d.b)) == pair]
    open_sides = {(z, side) for (z, side), kind in out.walls.items() if kind is WallType.OPEN}
    assert not [w for w in out.windows if (w.zone_id, w.side) in open_sides]


def test_the_open_pair_is_declared_open_connection_not_a_door(placed):
    from app.vertical_slice.geometry_core.model import ConnectionKind

    out = _opened(placed, LIVING_KITCHEN)
    kinds = {frozenset((e.a, e.b)): e.kind for e in out.fixture.access.edges}
    assert kinds[frozenset(("LIVING", "KITCHEN"))] is ConnectionKind.OPEN_CONNECTION
    assert kinds[frozenset(("HALL", "LIVING"))] is ConnectionKind.DOOR


# ------------------------------------------------- AC-3: the unchanged validators keep passing

def test_the_unchanged_validators_pass_on_the_open_plan(placed):
    out = _opened(placed, LIVING_KITCHEN)
    assert isinstance(out, RealizedLayout)
    failed = [c.check_id for c in out.report.checks if not c.passed]
    assert out.report.ok and not failed, failed
    # C6 (no artificial door in an open group), C13 (the declared OPEN_CONNECTION is realized)
    # and C5 (everything reachable) are the three the change could have broken.
    passed = {c.check_id for c in out.report.checks if c.passed}
    assert {"C5", "C6", "C13", "C24"} <= passed


def test_opening_an_interface_creates_no_cell_and_moves_no_geometry(placed):
    """THE FRAGMENTATION CHECK. The rooms, their rectangles and the cell decomposition are
    identical to the closed plan; only two wall sides differ."""
    closed, out = placed["closed"], _opened(placed, LIVING_KITCHEN)
    assert out.rects == closed.rects
    assert out.zone_of_cell == closed.zone_of_cell and out.groups == closed.groups == {}
    assert sorted(out.rects) == sorted(closed.rects)
    assert sorted(out.walls) == sorted(closed.walls)
    differing = sorted(k for k in closed.walls if closed.walls[k] != out.walls[k])
    assert [z for z, _ in differing] == ["KITCHEN", "LIVING"]
    assert all(out.walls[k] is WallType.OPEN for k in differing)


def test_a_pair_the_placement_left_partially_adjacent_stays_walled_and_says_so(placed):
    """A typed refusal to REPORT, never a wall forced open or a room split. The hall runs under
    the whole public row, so it never covers a public cell's full side."""
    out = _opened(placed, (("HALL", "LIVING"),))
    assert isinstance(out, RealizedLayout)
    assert out.fixture.open_groups == ()
    assert any("open plan not expressed between" in n and "stays walled" in n for n in out.notes), out.notes
    assert out.walls == placed["closed"].walls                 # nothing opened, nothing re-typed
    assert out.report.ok


def test_a_member_absent_from_the_layout_is_simply_not_opened(placed):
    out = _opened(placed, (("LIVING", "KITCHEN", "SUNROOM"),))
    assert isinstance(out, RealizedLayout)
    assert out.fixture.open_groups == (("KITCHEN", "LIVING"),)


# ------------------------------------------------------- the rule itself, on synthetic rectangles

def _r(x, y, w, h):
    return Rect(m_to_u(x), m_to_u(y), m_to_u(w), m_to_u(h))


def test_the_full_side_precondition_is_the_rule_discover_open_interfaces_uses():
    """`geometry_core.engine._discover_open_interfaces`'s precondition, mirrored: a `WallMap` side
    carries exactly ONE type, so a partial overlap is skipped rather than approximated."""
    roles = {"A": (R.LIVING,), "B": (R.KITCHEN,), "C": (R.DINING,)}
    full = {"A": _r(0, 0, 5, 4), "B": _r(5, 0, 4, 4)}                   # 4 m side, 4 m shared
    pairs, notes = _open_cell_pairs((("A", "B"),), full, roles)
    assert pairs == {frozenset(("A", "B"))} and notes == []

    partial = {"A": _r(0, 0, 5, 4), "B": _r(5, 0, 4, 2)}                # B is half as deep
    pairs, notes = _open_cell_pairs((("A", "B"),), partial, roles)
    assert pairs == set() and len(notes) == 1 and "stays walled" in notes[0]

    apart = {"A": _r(0, 0, 5, 4), "B": _r(6, 0, 4, 4)}                  # not touching at all
    pairs, notes = _open_cell_pairs((("A", "B"),), apart, roles)
    assert pairs == set() and notes == []                               # nothing to report

    chain = {"A": _r(0, 0, 5, 4), "B": _r(5, 0, 4, 4), "C": _r(9, 0, 3, 4)}
    pairs, _ = _open_cell_pairs((("A", "B", "C"),), chain, roles)
    assert pairs == {frozenset(("A", "B")), frozenset(("B", "C"))}      # A and C never touch


def test_a_safe_room_is_never_opened():
    """Its envelope is RC on every side (C4/C33) — the same skip `_discover_open_interfaces` makes."""
    roles = {"A": (R.LIVING,), "MAMAD": (R.SAFE_ROOM,)}
    rects = {"A": _r(0, 0, 5, 4), "MAMAD": _r(5, 0, 3, 4)}
    pairs, notes = _open_cell_pairs((("A", "MAMAD"),), rects, roles)
    assert pairs == set() and notes == []


def test_the_realized_group_is_the_component_that_was_actually_opened():
    """`Fixture.open_groups` names what the geometry provides, not what was declared — which is
    what keeps C6 and C13 true at the same time."""
    from app.vertical_slice.rectilinear_realizer import _open_components

    assert _open_components(set()) == ()
    assert _open_components({frozenset(("A", "B")), frozenset(("B", "C"))}) == (("A", "B", "C"),)
    assert _open_components({frozenset(("A", "B")), frozenset(("X", "Y"))}) == (("A", "B"), ("X", "Y"))


# ------------------------------- AC-4 (payload half): the demo contract carries the open interface

def test_the_demo_payload_carries_the_open_interface_and_drops_its_wall(placed):
    """The renderer draws open plan by the ABSENCE of a wall segment (`DemoPlan.tsx`: "an OPEN
    interface has no wall segment at all, so open-plan reads as one continuous space"), and names
    it in `open_interfaces` for the legend. Both are checked here on the real geometry."""
    from app.demo.contract import to_demo_design

    out = _opened(placed, LIVING_KITCHEN)
    payload = to_demo_design(out.design, out.report)
    named = [sorted(o.room_ids) for o in payload.open_interfaces]
    assert ["KITCHEN", "LIVING"] in named, named

    iface = next(o for o in payload.open_interfaces if sorted(o.room_ids) == ["KITCHEN", "LIVING"])
    overlapping = [w for w in payload.walls
                   if w.orientation == iface.orientation and abs(w.coord - iface.coord) < 1e-6
                   and min(w.end, iface.end) - max(w.start, iface.start) > 1e-6]
    assert not overlapping, overlapping                       # no wall is drawn across it
    assert not [d for d in payload.doors if {d.a, d.b} == {"LIVING", "KITCHEN"}]

    closed_payload = to_demo_design(placed["closed"].design, placed["closed"].report)
    assert not closed_payload.open_interfaces                 # the defect, for contrast
    assert [d for d in closed_payload.doors if {d.a, d.b} == {"LIVING", "KITCHEN"}]


# --------------------------------------------------- the whole brain path, on one open-plan brief

def test_the_brain_delivers_the_open_plan_an_open_plan_brief_asked_for():
    """End to end through `run_brain(sizer="exact")` — the intent travels brief -> programme ->
    `PipelineInput.open_groups` -> `realize_cells` -> `GeometricDesign.open_groups`.

    The budget is raised well above the product's 30 s because this asserts a COUNT, not a time:
    under the product budget on a loaded machine the exact sizer can fall back to the production
    sizer, which cannot type an interface OPEN and says so in the plan's notes.
    """
    pytest.importorskip("scipy")
    from app.vertical_slice.brain.proposer import programme_from_spec
    from app.vertical_slice.brain.runner import run_brain
    from tests.vertical_slice.test_brain import _spec_and_footprint

    spec, fp = _spec_and_footprint("B08")
    res = run_brain(spec, fp, brief="B08", sizer="exact",
                    families=("band", "spine", "stack", "cells"), budget_s=120.0)
    primary = next(p for p in res.plans if p.realized is not None)
    groups = primary.realized.design.open_groups
    assert groups, primary.notes
    # The group is a connected run of the brief's OWN public chain. Which members join depends on
    # the placement: a pair the exact sizer left only partially adjacent stays walled and is
    # reported in the plan's notes (`test_a_pair_the_placement_left_partially_adjacent...`),
    # never forced open — so this asserts "at least one real open interface inside the chain",
    # which is exactly what #213 measured as 0 of 9.
    chain = set(programme_from_spec(spec, fp).open_group)
    assert chain == {"LIVING", "DINING", "KITCHEN"}
    assert len(groups) == 1 and 2 <= len(groups[0]) and set(groups[0]) <= chain
    assert not [d for d in primary.realized.interior_doors if {d.a, d.b} <= set(groups[0])]
    if set(groups[0]) != chain:
        assert any("open plan not expressed between" in n for n in primary.notes), primary.notes
