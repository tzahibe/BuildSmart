"""Generator-level pattern compilers (Issue #79, Concept Engine v2 5/5).

AC-1: every compiler emits candidates whose declared `circulation_class` is VERIFIED on the
realized plan (`concept_spec.verify_class`), on the canonical fixtures this module names — and a
candidate whose declared class disagrees with what it actually realizes to is DROPPED by
`concept_engine_v2._best_for_class`, never re-labelled and never scored.

AC-2: a canonical 4-bedroom fixture realizes a BRANCHED concept with every bedroom's door on a
hall segment (HALL_A or HALL_B) and C5/C14/C24 green.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.vertical_slice import concept_compilers
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.concept_engine_v2 import _best_for_class
from app.vertical_slice.concept_spec import CirculationClass, verify_class
from app.vertical_slice.general_pipeline import _realize
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.spec import (
    ArchitecturalSpec,
    CorridorRequirement,
    CorridorWidthMode,
    PlotSpec,
    ProgramSpec,
)


def _pattern_for(circulation_class: CirculationClass):
    return SimpleNamespace(circulation_class=circulation_class)


def _rect_buildable(width_m: float, depth_m: float) -> BuildableRegion:
    """A plain rectangle set back from the street edge by the same margin
    `demo.service._buildable_from` reserves for parking, so a realized plan's own entrance/
    parking checks pass without going through the full demo-service placement machinery."""
    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(0.0, 6.0, width_m, depth_m))),
        Provenance(Source.USER, Authority.AUTHORITATIVE, ref="test_concept_compilers"))


#: (spec, outline-candidates, expect-nonempty) per class this module's `compile` dispatches —
#: canonical fixtures chosen to actually reach each builder (measured, not assumed): a narrow
#: rectangle for SPINE, a wide one for FRONT_BAND, an L-shaped site for TWO_WING, and a plain
#: rectangle sized for `compile_hub_lobby`/`compile_branched`'s own programme requirements.
def _spine_case():
    buildable = _rect_buildable(10.0, 16.0)
    spec = ArchitecturalSpec(PlotSpec(16.0, 22.0),
                             ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2,
                                        parking_spaces=0))
    return spec, tuple(adapt(buildable).candidates), buildable


def _front_band_case():
    buildable = _rect_buildable(15.0, 11.0)
    spec = ArchitecturalSpec(PlotSpec(21.0, 17.0),
                             ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2,
                                        parking_spaces=0))
    return spec, tuple(adapt(buildable).candidates), buildable


def _two_wing_case():
    site = F.l_shaped_site_deep_primary()
    buildable = build_buildable_region(site)
    spec = ArchitecturalSpec(PlotSpec(24.0, 32.0),
                             ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2))
    return spec, tuple(adapt(buildable).candidates), buildable


def _hub_lobby_case():
    # `compile_hub_lobby` is a hand-sized tree for exactly this programme shape — see its own
    # docstring for why (`_hub_concept` is measured broken under the current hard room-area
    # maxima for every outline this Issue tried, corpus included).
    buildable = _rect_buildable(24.0, 22.0)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=2, safe_room=False, wet_rooms=2,
                                        open_plan_living=False, parking_spaces=0))
    return spec, tuple(adapt(buildable).candidates), buildable


def _branched_case():
    buildable = _rect_buildable(24.0, 22.0)
    corridor = CorridorRequirement(mode=CorridorWidthMode.MINIMUM, width_m=0.9)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=4, wet_rooms=2, safe_room=False,
                                        open_plan_living=False, parking_spaces=0,
                                        corridor=corridor))
    return spec, tuple(adapt(buildable).candidates), buildable


def _hub_lobby_safe_case():
    buildable = _rect_buildable(24.0, 22.0)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=2, safe_room=True, wet_rooms=2,
                                        open_plan_living=False, parking_spaces=0))
    return spec, tuple(adapt(buildable).candidates), buildable


def _hub_lobby_open_case():
    buildable = _rect_buildable(24.0, 22.0)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=2, safe_room=False, wet_rooms=2,
                                        open_plan_living=True, parking_spaces=0))
    return spec, tuple(adapt(buildable).candidates), buildable


def _hub_lobby_toilet_case():
    buildable = _rect_buildable(24.0, 22.0)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=2, safe_room=False, wet_rooms=3,
                                        open_plan_living=False, parking_spaces=0))
    return spec, tuple(adapt(buildable).candidates), buildable


def _hub_lobby_safe_open_case():
    buildable = _rect_buildable(24.0, 22.0)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=2, safe_room=True, wet_rooms=2,
                                        open_plan_living=True, parking_spaces=0))
    return spec, tuple(adapt(buildable).candidates), buildable


def _branched_safe_case():
    buildable = _rect_buildable(24.0, 22.0)
    corridor = CorridorRequirement(mode=CorridorWidthMode.MINIMUM, width_m=0.9)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=3, wet_rooms=2, safe_room=True,
                                        open_plan_living=False, parking_spaces=0,
                                        corridor=corridor))
    return spec, tuple(adapt(buildable).candidates), buildable


def _branched_open_case():
    buildable = _rect_buildable(24.0, 22.0)
    corridor = CorridorRequirement(mode=CorridorWidthMode.MINIMUM, width_m=0.9)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=4, wet_rooms=2, safe_room=False,
                                        open_plan_living=True, parking_spaces=0,
                                        corridor=corridor))
    return spec, tuple(adapt(buildable).candidates), buildable


def _branched_safe_open_case():
    buildable = _rect_buildable(24.0, 22.0)
    corridor = CorridorRequirement(mode=CorridorWidthMode.MINIMUM, width_m=0.9)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0),
                             ProgramSpec(bedrooms=3, wet_rooms=2, safe_room=True,
                                        open_plan_living=True, parking_spaces=0,
                                        corridor=corridor))
    return spec, tuple(adapt(buildable).candidates), buildable


_CASES = {
    CirculationClass.SPINE: _spine_case,
    CirculationClass.FRONT_BAND: _front_band_case,
    CirculationClass.TWO_WING: _two_wing_case,
    CirculationClass.HUB_LOBBY: _hub_lobby_case,
    CirculationClass.BRANCHED: _branched_case,
}

#: SAFE_ROOM-aware / open-plan-aware compiler variants (lead direction after attempt 2,
#: 2026-09-22): each precondition-relaxed case still emits a HUB_LOBBY/BRANCHED candidate that
#: verifies on the realized plan, exactly like the base cases above.
_VARIANT_CASES = {
    "hub_lobby_safe": (CirculationClass.HUB_LOBBY, _hub_lobby_safe_case, concept_compilers.compile_hub_lobby),
    "hub_lobby_open": (CirculationClass.HUB_LOBBY, _hub_lobby_open_case, concept_compilers.compile_hub_lobby),
    "hub_lobby_safe_open": (CirculationClass.HUB_LOBBY, _hub_lobby_safe_open_case, concept_compilers.compile_hub_lobby),
    "hub_lobby_toilet": (CirculationClass.HUB_LOBBY, _hub_lobby_toilet_case, concept_compilers.compile_hub_lobby),
    "branched_safe": (CirculationClass.BRANCHED, _branched_safe_case, concept_compilers.compile_branched),
    "branched_open": (CirculationClass.BRANCHED, _branched_open_case, concept_compilers.compile_branched),
    "branched_safe_open": (CirculationClass.BRANCHED, _branched_safe_open_case, concept_compilers.compile_branched),
}


def _realize_all(spec, buildable, candidates):
    out = []
    for index, candidate in enumerate(candidates):
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        plan = _realize(spec, buildable, None, candidate, index, solve, ())
        out.append((candidate, plan))
    return out


@pytest.mark.parametrize("circulation_class", list(_CASES))
def test_every_compiler_emits_verified_classes_and_drops_mismatches(circulation_class):
    spec, outline, buildable = _CASES[circulation_class]()
    candidates = concept_compilers.compile(_pattern_for(circulation_class), spec, outline)
    assert candidates, f"{circulation_class} compiled nothing on its own canonical fixture"
    assert all(c.circulation_class is circulation_class for c in candidates)

    realized = _realize_all(spec, buildable, candidates)
    ok_plans = [(c, p) for c, p in realized if p.ok]
    assert ok_plans, f"{circulation_class}'s canonical fixture never realized to a valid plan"
    for candidate, plan in ok_plans:
        assert verify_class(candidate, plan) is None, (
            circulation_class, plan.circulation_class, candidate.rationale)


@pytest.mark.parametrize("variant", list(_VARIANT_CASES))
def test_safe_room_and_open_plan_variants_emit_verified_classes(variant):
    """Lead direction after attempt 2 (2026-09-22): SAFE_ROOM-aware and open-plan-aware variants
    of `compile_hub_lobby`/`compile_branched` still emit a candidate that verifies on the realized
    plan, carries a SAFE_ROOM when the programme asked for one, and connects LIVING/KITCHEN with
    an OPEN_CONNECTION (no door between them) when the programme is open-plan."""
    circulation_class, case, compile_fn = _VARIANT_CASES[variant]
    spec, outline, buildable = case()
    candidates = compile_fn(spec, outline[0].rect)
    assert candidates, f"{variant} compiled nothing on its own canonical fixture"
    assert all(c.circulation_class is circulation_class for c in candidates)

    realized = _realize_all(spec, buildable, candidates)
    ok_plans = [(c, p) for c, p in realized if p.ok]
    assert ok_plans, (variant, [chk.detail for c, p in realized for chk in p.validation.checks
                                if not chk.passed])
    for candidate, plan in ok_plans:
        assert verify_class(candidate, plan) is None, (variant, plan.circulation_class)
        zone_ids = {r.zone_id for r in plan.design.rooms}
        if spec.program.safe_room:
            assert "SAFE_ROOM" in zone_ids, (variant, zone_ids)
        if spec.program.wet_rooms == 3:
            assert "TOILET_1" in zone_ids, (variant, zone_ids)
        if spec.program.open_plan_living:
            living_kitchen_door = any(
                {d.a, d.b} == {"LIVING", "KITCHEN"} for d in plan.design.interior_doors)
            assert not living_kitchen_door, (variant, "LIVING-KITCHEN should be an open connection")


def test_a_mismatching_candidate_is_dropped_not_relabelled():
    """AC-1's other half: `concept_engine_v2._best_for_class` never returns a candidate whose
    declared class disagrees with its realized one — a real SPINE candidate, relabelled to claim
    HUB_LOBBY, is dropped rather than scored or renamed."""
    spec, outline, buildable = _spine_case()
    candidates = concept_compilers.compile(_pattern_for(CirculationClass.SPINE), spec, outline)
    genuine = candidates[0]
    mismatching = replace(genuine, circulation_class=CirculationClass.HUB_LOBBY)

    def realize(index, candidate):
        solve = solve_fixture(candidate.concept.fixture)
        return _realize(spec, buildable, None, candidate, index, solve, ())

    result = _best_for_class(realize, [(0, mismatching)], [10])
    assert result is None, "a mismatching candidate must be dropped, not scored"

    # Sanity: the SAME candidate, correctly labelled, is not dropped.
    result_ok = _best_for_class(realize, [(0, genuine)], [10])
    assert result_ok is not None and result_ok.ok


def test_branched_concept_realizes_with_all_bedrooms_on_a_hall():
    """AC-2: the canonical 4-bedroom BRANCHED fixture realizes with every bedroom's door on a
    hall segment (HALL_A or HALL_B) and C5, C14, C24 green."""
    spec, outline, buildable = _branched_case()
    candidates = concept_compilers.compile_branched(spec, outline[0].rect)
    assert len(candidates) == 1
    candidate = candidates[0]

    solve = solve_fixture(candidate.concept.fixture)
    plan = _realize(spec, buildable, None, candidate, 0, solve, ())

    assert plan.ok, [c.detail for c in plan.validation.checks if not c.passed]
    assert plan.circulation_class is CirculationClass.BRANCHED
    assert verify_class(candidate, plan) is None

    hall_ids = {"HALL_A", "HALL_B"}
    bedroom_ids = {"MASTER", "BEDROOM_1", "BEDROOM_2", "BEDROOM_3"}
    doors_by_room = {rid: [] for rid in bedroom_ids}
    for door in plan.design.interior_doors:
        for rid in bedroom_ids:
            if rid in (door.a, door.b):
                other = door.b if door.a == rid else door.a
                doors_by_room[rid].append(other)
    for rid, others in doors_by_room.items():
        assert others and any(o in hall_ids for o in others), (rid, others)

    by_id = {c.check_id: c for c in plan.validation.checks}
    assert by_id["C5"].passed, by_id["C5"].detail
    assert by_id["C24"].passed, by_id["C24"].detail
    assert by_id["C14"].passed, by_id["C14"].detail
