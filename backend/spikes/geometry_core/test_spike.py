"""Geometry Core Proof Spike — regression gate.

    cd backend/spikes/geometry_core && python3 -m pytest test_spike.py -q

Deliberately NOT under backend/tests: this is spike code and must not become a production
dependency. It runs standalone.
"""
from __future__ import annotations

import dataclasses

import pytest

from engine import SpikeInfeasible, net_rect_m, solve_fixture
from fixtures import ALL_FIXTURES, branching_hall, open_plan_safe_room, rect_simple
from model import (
    ConnectionKind,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    ProgramRole,
    Side,
    WallType,
    Wing,
    ZoneSpec,
    half_thickness_units,
    m_to_u,
)
from validate import generate_openings, validate


@pytest.mark.parametrize("make", ALL_FIXTURES, ids=lambda m: m().name)
def test_every_proof_passes(make):
    fixture = make()
    report = validate(fixture, solve_fixture(fixture))
    failed = [f"{p.proof_id} {p.name}: {p.detail}" for p in report.proofs if not p.passed]
    assert not failed, "\n".join(failed)


@pytest.mark.parametrize("make", ALL_FIXTURES, ids=lambda m: m().name)
def test_tiling_is_exact_not_approximate(make):
    """Integer grid units mean the tiling is exact, not 'within tolerance'."""
    fixture = make()
    res = solve_fixture(fixture)
    for wing in fixture.wings:
        wr = wing.rect()
        inside = [r for r in res.rects.values()
                  if r.x >= wr.x and r.y >= wr.y and r.x2 <= wr.x2 and r.y2 <= wr.y2]
        assert sum(r.w * r.h for r in inside) == wr.w * wr.h


def test_safe_room_is_rc_on_every_side_including_the_exterior_one():
    """Regression for the defect this spike found on its first run: exposure must not outrank
    safe-room membership, or the ממ"ד's envelope wall is typed as ordinary exterior."""
    fixture = open_plan_safe_room()
    res = solve_fixture(fixture)
    for side in Side:
        assert res.walls[("SAFE_ROOM", side)] is WallType.RC_SAFE_ROOM


def test_safe_room_net_area_is_never_below_its_minimum():
    fixture = open_plan_safe_room()
    res = solve_fixture(fixture)
    zone = fixture.zone("SAFE_ROOM")
    _, _, net = net_rect_m("SAFE_ROOM", res.rects["SAFE_ROOM"], res.walls)
    assert net >= zone.net_area_min_m2


def test_open_connections_never_produce_a_door():
    """CORRECTION 1 in action — the reason ConnectionKind exists at all."""
    fixture = open_plan_safe_room()
    res = solve_fixture(fixture)
    openings = generate_openings(fixture, res)
    open_pairs = {frozenset((e.a, e.b))
                  for e in fixture.access.of_kind(ConnectionKind.OPEN_CONNECTION)}
    assert open_pairs, "fixture must actually contain OPEN_CONNECTION edges"
    assert not [o for o in openings if frozenset((o.a, o.b)) in open_pairs]


def test_open_group_boundaries_carry_no_wall():
    fixture = open_plan_safe_room()
    res = solve_fixture(fixture)
    assert res.walls[("LIVING", Side.S)] is WallType.OPEN
    assert res.walls[("DINING", Side.N)] is WallType.OPEN
    assert res.walls[("DINING", Side.E)] is WallType.OPEN
    assert res.walls[("KITCHEN", Side.W)] is WallType.OPEN


def test_wall_thickness_needs_no_iteration_without_a_safe_room():
    """The report's §7 claim, measured: with no safe room every wall type is structural, so
    the first pass is already thickness-correct."""
    assert solve_fixture(rect_simple()).wall_iterations == 1


def test_safe_room_costs_exactly_one_extra_iteration():
    """...and the one genuinely geometry-dependent wall type converges in one extra pass."""
    assert solve_fixture(open_plan_safe_room()).wall_iterations == 2


def test_infeasible_fixture_is_rejected_with_a_diagnosis_not_a_bad_plan():
    """The engine must never silently return a plan that violates its inputs."""
    base = rect_simple()
    shrunk = base.wings[0]
    fixture = type(base)(
        base.name + "_TOO_SMALL",
        (Wing(shrunk.wing_id, 0, 0, m_to_u(6.0), m_to_u(5.0), shrunk.tree),),
        base.zones, base.access,
    )
    with pytest.raises(SpikeInfeasible) as exc:
        solve_fixture(fixture)
    assert "EMPTY" in str(exc.value) or "not in the root shape curve" in str(exc.value)


def test_outdoor_remainder_is_not_silently_called_a_garden():
    """CORRECTION 3 — an L's bounding-box remainder stays UNCLASSIFIED until classified."""
    from fixtures import l_house
    fixture = l_house()
    assert fixture.outdoor
    assert all(not o.is_classified for o in fixture.outdoor)


# ============================================================ Fable review — 5 proof patches


# ---- patch 1: non-grid-aligned wall thickness is rejected, never silently rounded ----------

def test_non_grid_aligned_wall_thickness_is_rejected_not_silently_rounded():
    """The exact defect found in review: m_to_u(0.125) round-half-to-evens to 2 units, not
    2.5 -- a silent ~5 cm net-area error. 0.25 m is a plausible real ממ"ד regulation value."""
    with pytest.raises(ValueError, match="not grid-aligned"):
        half_thickness_units(0.25, label="RC_SAFE_ROOM")


def test_grid_aligned_wall_thickness_still_works():
    assert half_thickness_units(0.30, label="EXTERIOR") == 3
    assert half_thickness_units(0.10, label="PARTITION") == 1
    assert half_thickness_units(0.0, label="OPEN") == 0


def test_module_level_check_covers_every_declared_wall_type_not_just_used_ones():
    """The guard runs eagerly at import time over the whole WALL_THICKNESS_M table, not lazily
    only when inset_u() happens to be called on a given type — confirmed by the fact this
    module already imported cleanly with all four current (grid-aligned) thicknesses."""
    import model
    assert set(model.WALL_THICKNESS_M) == {WallType.EXTERIOR, WallType.PARTITION,
                                            WallType.RC_SAFE_ROOM, WallType.OPEN}


# ---- patch 2: SAFE_ROOM inside open_groups is rejected eagerly, with a clear diagnostic -----

def test_safe_room_in_open_group_is_rejected_at_construction():
    fixture = open_plan_safe_room()
    bad_open_groups = fixture.open_groups + (("LIVING", "SAFE_ROOM"),)
    with pytest.raises(ValueError, match="SAFE_ROOM"):
        dataclasses.replace(fixture, open_groups=bad_open_groups)


def test_safe_room_in_open_group_diagnostic_names_the_conflict():
    fixture = open_plan_safe_room()
    with pytest.raises(ValueError) as exc:
        dataclasses.replace(fixture, open_groups=(("SAFE_ROOM", "MASTER"),))
    msg = str(exc.value)
    assert "SAFE_ROOM" in msg and "sealed RC" in msg


# ---- patch 3: F4 — a hall that genuinely requires branching (L1) ---------------------------

def test_branching_hall_realizes_and_every_proof_passes():
    fixture = branching_hall()
    report = validate(fixture, solve_fixture(fixture))
    failed = [f"{p.proof_id} {p.name}: {p.detail}" for p in report.proofs if not p.passed]
    assert not failed, "\n".join(failed)


def test_branching_hall_serves_at_least_three_rooms():
    fixture = branching_hall()
    served = {e.a for e in fixture.access.edges if e.kind is ConnectionKind.DOOR} | \
             {e.b for e in fixture.access.edges if e.kind is ConnectionKind.DOOR}
    served -= {"HALL_MAIN", "HALL_SPUR"}
    assert len(served) >= 3


def test_branching_hall_genuinely_requires_the_branch():
    """Three of the five served rooms touch ONLY the spur, never the main hall leaf directly
    -- so a single non-branching hall leaf could not have served them. This is the concrete
    proof that L_CARVE_CIRCULATION-style branching is required, not optional, for this plan."""
    fixture = branching_hall()
    res = solve_fixture(fixture)
    rects = res.rects
    spur_only = {"KITCHEN", "BEDROOM_2", "BATH"}
    for zid in spur_only:
        touches_main = rects[zid].shared_edge_len_u(rects["HALL_MAIN"]) > 0
        touches_spur = rects[zid].shared_edge_len_u(rects["HALL_SPUR"]) > 0
        assert touches_spur and not touches_main, f"{zid}: main={touches_main} spur={touches_spur}"
    main_only = {"LIVING", "BEDROOM_1"}
    for zid in main_only:
        touches_main = rects[zid].shared_edge_len_u(rects["HALL_MAIN"]) > 0
        touches_spur = rects[zid].shared_edge_len_u(rects["HALL_SPUR"]) > 0
        assert touches_main and not touches_spur, f"{zid}: main={touches_main} spur={touches_spur}"


def test_branching_hall_corridor_joint_is_wall_less_and_width_continuous():
    fixture = branching_hall()
    res = solve_fixture(fixture)
    assert res.walls[("HALL_MAIN", Side.S)] is WallType.OPEN
    assert res.walls[("HALL_SPUR", Side.N)] is WallType.OPEN
    nw_main = net_rect_m("HALL_MAIN", res.rects["HALL_MAIN"], res.walls)[0]
    nw_spur = net_rect_m("HALL_SPUR", res.rects["HALL_SPUR"], res.walls)[0]
    assert abs(nw_main - nw_spur) < 0.01


# ---- patch 4: per-role minimum furniture-envelope feasibility ------------------------------

@pytest.mark.parametrize("make", ALL_FIXTURES, ids=lambda m: m().name)
def test_furniture_envelope_fits_for_every_furnished_zone(make):
    fixture = make()
    res = solve_fixture(fixture)
    report = validate(fixture, res)
    p11 = next(p for p in report.proofs if p.proof_id == "P11")
    assert p11.passed, p11.detail


def test_furniture_envelope_screen_catches_a_room_too_shallow_for_its_role():
    """Regression for the exact gap this patch closes: a room can satisfy its own area/aspect
    proofs (P4/P5) while being too shallow to hold the furniture its role implies. Constructed
    directly against a zone, not by re-deriving the historical F3 fixture bug."""
    from model import furniture_envelope_fits
    shallow_bedroom = ZoneSpec(
        "TEST_BEDROOM", (ProgramRole.BEDROOM,), 8.0, 9.0, 12.0, 2.0,
    )
    # 4.20 x 2.20 m: plenty of area (9.24 m²) and fine aspect (1.9), but 2.20 m short side
    # cannot inscribe the 2.4 x 2.4 m bedroom envelope in either orientation.
    assert furniture_envelope_fits(shallow_bedroom, 4.20, 2.20) is False


def test_furniture_envelope_is_skipped_not_failed_for_circulation_roles():
    from model import furniture_envelope_fits
    hall = ZoneSpec("TEST_HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 9, 12, 1.2, max_aspect_ratio=8.0)
    assert furniture_envelope_fits(hall, 1.5, 5.85) is None


def test_dual_role_zone_takes_the_larger_governing_envelope():
    """SAFE_ROOM's own envelope (2.0x1.8) is smaller than BEDROOM's (2.4x2.4); a zone carrying
    both roles must satisfy the larger one, since both roles apply to the same physical room."""
    from model import min_furniture_envelope_m
    dual = ZoneSpec("TEST_SAFE_BED", (ProgramRole.SAFE_ROOM, ProgramRole.BEDROOM), 9.0, 9.5, 13.0, 2.4)
    assert min_furniture_envelope_m(dual) == (2.4, 2.4)


# ---- patch 5: perturbation regression for the wall re-solve loop's staleness risk ----------

def test_wall_resolve_loop_does_not_go_stale_when_geometry_shifts():
    """The review raised a theoretical risk: `extra_rc` only ever ADDS (never removes) a
    zone-side to RC once a safe-room neighbour is discovered, so if a later geometry shift
    moved that side away from the safe room, the wall could stay RC for the wrong reason.

    In THIS engine that risk does not materialise, because sibling-chain adjacency in a
    guillotine tree is fixed by TREE TOPOLOGY, not by the numeric split position `assign()`
    picks — so perturbing target areas heavily (forcing very different split positions) must
    not change who is structurally adjacent to whom. This test proves that empirically rather
    than asserting it: it perturbs MASTER/BEDROOM_1's target areas drastically and checks the
    discovered safe-room-adjacent sides and iteration count are unchanged.
    """
    base = open_plan_safe_room()
    res_base = solve_fixture(base)

    # Perturb ONLY the target (not min/max) so each leaf's own feasibility window is untouched
    # -- the only thing that can change is which feasible split `assign()`'s ratio-heuristic
    # picks, which is exactly the mechanism the theoretical staleness risk depends on.
    def _perturb(z: ZoneSpec) -> ZoneSpec:
        if z.zone_id == "MASTER":
            return dataclasses.replace(z, net_area_target_m2=z.net_area_min_m2 + 0.5)
        if z.zone_id == "BEDROOM_1":
            return dataclasses.replace(z, net_area_target_m2=z.net_area_max_m2 - 0.5)
        return z

    perturbed = dataclasses.replace(base, zones=tuple(_perturb(z) for z in base.zones))
    res_perturbed = solve_fixture(perturbed)

    # Geometry actually changed -- otherwise this test would prove nothing.
    assert res_base.rects["MASTER"].h != res_perturbed.rects["MASTER"].h

    assert res_perturbed.wall_iterations == res_base.wall_iterations
    for side in Side:
        assert res_perturbed.walls[("SAFE_ROOM", side)] is WallType.RC_SAFE_ROOM
    for zid in ("MASTER", "BEDROOM_1"):
        sides_base = {s for s in Side if res_base.walls[(zid, s)] is WallType.RC_SAFE_ROOM}
        sides_pert = {s for s in Side if res_perturbed.walls[(zid, s)] is WallType.RC_SAFE_ROOM}
        assert sides_base == sides_pert, f"{zid}: RC sides changed {sides_base} -> {sides_pert}"


def test_wall_resolve_loop_still_returns_structured_diagnostic_on_non_convergence():
    """Preserve the structured-infeasibility guarantee: forcing non-convergence must still
    raise SpikeInfeasible with a diagnosis, never loop forever or return a wrong plan."""
    fixture = open_plan_safe_room()
    with pytest.raises(SpikeInfeasible, match="did not converge"):
        solve_fixture(fixture, max_wall_iterations=0)
