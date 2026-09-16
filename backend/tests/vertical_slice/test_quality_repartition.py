"""The quality tier (2026-09-16): rows re-partitioned for room PROPORTIONS.

Beside a plan that leaves a bedroom-class room past its preferred aspect (1.5), the same
proportion is planned again with the tier-2 pairing — a lone room takes the master's slot beside
the ensuite, the master goes full-width — and offered as an ADDITIONAL candidate, ordered after
every candidate the brief already had. Nothing is shrunk, no maximum relaxed, no wet room moved,
no ranking changed. See docs/ROOM_PROPORTION_REPARTITION_REPORT.md.
"""
from __future__ import annotations

import pytest

from app.vertical_slice import concept_generator as cg
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.concept_generator import (
    FREE_TWIN_RATIONALE,
    QUALITY_RATIONALE,
    ROOM_TEMPLATES,
    ConceptStrategy,
)
from app.vertical_slice.general_pipeline import _realize, run_general_from_site
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

BEDROOM_CLASS = {ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM, ProgramRole.SAFE_ROOM}

#: The reported brief (failure-log context, 2026-09-16): 1 BR + 2 wet, closed plan, 132 m² asked,
#: an 11 x 12 m outline on an 18 x 22.5 plot. Delivered as a 10.9 x 8.95 m house with MASTER
#: 3.1 x 6.3 m (aspect 2.03) beside its 2.15 x 6.3 m ensuite (2.93) and the shared bathroom
#: 5.35 x 2.25 m (2.38) under them — three strips where `[MASTER] + [BATH_2, BATH_1]` gives
#: three near-squares at the same footprint.
REPORTED = ProgramSpec(bedrooms=1, safe_room=False, open_plan_living=False, wet_rooms=2,
                       parking_spaces=0, target_built_area_m2=132.0)
NO_ENSUITE = ProgramSpec(bedrooms=2, safe_room=True, open_plan_living=True, wet_rooms=1,
                         parking_spaces=0, target_built_area_m2=150.0)
OPEN_3BR = ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=True, wet_rooms=2,
                       parking_spaces=2, target_built_area_m2=200)


def _rectangle_site(width_m: float, depth_m: float, plot=(18.0, 22.5)):
    """A rectangular buildable region of exactly `width_m x depth_m`, centred on the plot — the
    person's outline, as the demo hands it to the engine."""
    parcel = F.Ring.rectangle(0, 0, plot[0], plot[1], prefix="p")
    keep = F.Ring.rectangle((plot[0] - width_m) / 2, (plot[1] - depth_m) / 2, width_m, depth_m,
                            prefix="k")
    return F.SiteConstraints(
        parcel=F.Parcel("test-rectangle", F.MultiRegion.of(F.Region(parcel)), F.SURVEYED),
        constraints=(F._frame_setback(parcel, keep),))


def _generate(site, plot, program):
    adapted = adapt(build_buildable_region(site))
    return cg.generate_concepts(ArchitecturalSpec(PlotSpec(*plot), program),
                                list(adapted.candidates))


def _split(candidates):
    return ([c for c in candidates if not c.quality_repartitioned],
            [c for c in candidates if c.quality_repartitioned])


def _worst_bedroom_class(design) -> float:
    aspects = []
    for room in design.rooms:
        if ProgramRole(room.roles[0]) in BEDROOM_CLASS:
            aspects.append(max(room.net_w_m, room.net_h_m) / min(room.net_w_m, room.net_h_m))
    return max(aspects)


def _realized(spec, site, candidates):
    """Every candidate that solves, realized — (candidate, RealizedPlan)."""
    buildable = build_buildable_region(site)
    out = []
    for index, candidate in candidates:
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        out.append((candidate, _realize(spec, buildable, site, candidate, index, solve, ())))
    return out


# ------------------------------------------------------------------ the target is not a gate

#: Wet/service roles the quality tier was extended to (2026-09-16,
#: docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md) — BATHROOM at 2.0, TOILET at 2.5. ENSUITE-kind
#: BATHROOM rooms are excluded from the objective regardless (`_preferred_aspects`); LAUNDRY is
#: not touched (`LAUNDRY_ROOM_ENABLED` is not even wired on this branch).
WET_QUALITY_ROLES = {ProgramRole.BATHROOM: 2.0, ProgramRole.TOILET: 2.5}


def test_the_preferred_aspect_is_a_target_and_the_hard_limits_are_untouched():
    for role in BEDROOM_CLASS:
        assert ROOM_TEMPLATES[role].preferred_aspect_ratio == 1.5
        assert ROOM_TEMPLATES[role].max_aspect_ratio == 2.5
    for role, ratio in WET_QUALITY_ROLES.items():
        assert ROOM_TEMPLATES[role].preferred_aspect_ratio == ratio
    for role, template in ROOM_TEMPLATES.items():
        if role not in BEDROOM_CLASS and role not in WET_QUALITY_ROLES:
            assert template.preferred_aspect_ratio is None
    # The shape band a planner floors a row with, and the ZoneSpec the solver and C20 are held
    # to, still carry the HARD aspect: a 5.0 m wide bedroom may still be planned 2.6 m deep.
    band = cg.room_depth_band_m(ROOM_TEMPLATES[ProgramRole.BEDROOM], 5.0)
    assert band is not None and band[0] == pytest.approx(2.6)
    room = cg.ProgramRoom("BEDROOM_1", ProgramRole.BEDROOM, cg.ZoneGroup.PRIVATE,
                          ROOM_TEMPLATES[ProgramRole.BEDROOM])
    assert cg._zone_spec(room, 5.0, 2.6, 0.6, 1.6).max_aspect_ratio == 2.5


# ------------------------------------------------------------------ the reported brief

@pytest.fixture(scope="module")
def reported():
    site = _rectangle_site(11.0, 12.0)
    return site, _generate(site, (18.0, 22.5), REPORTED)


def test_the_reported_brief_gets_a_quality_candidate_beside_every_normal_one(reported, monkeypatch):
    site, result = reported
    normal, quality = _split(result.candidates)
    assert quality, "a plan with a 2.03 master beside a 2.93 ensuite must get a re-partitioned peer"
    # The normal candidates are EXACTLY the list the generator produced before the tier existed:
    # same candidates, same order, same trees.
    monkeypatch.setattr(cg, "_MAX_QUALITY_PAIRINGS", 0)
    before = _generate(site, (18.0, 22.5), REPORTED)
    assert not _split(before.candidates)[1]
    assert [c.rationale for c in before.candidates] == [c.rationale for c in normal]
    assert [c.concept.fixture for c in before.candidates] == [c.concept.fixture for c in normal]
    # Every quality candidate is an extra: it comes after every candidate that existed before,
    # is marked as re-partitioned, and has a base of the same strategy, footprint, sizing tier,
    # zones and wet-room requirements.
    last_normal = max(result.candidates.index(c) for c in normal)
    for c in quality:
        assert result.candidates.index(c) > last_normal
        assert c.repartitioned and c.quality_repartitioned
        assert QUALITY_RATIONALE in c.rationale
        base = [b for b in normal if b.strategy is c.strategy and not b.repartitioned
                and b.concept.footprint_width_m == c.concept.footprint_width_m
                and b.concept.footprint_depth_m == c.concept.footprint_depth_m
                and b.shrunk == c.shrunk and b.over_preferred == c.over_preferred
                and b.rationale.endswith(FREE_TWIN_RATIONALE) == c.rationale.endswith(FREE_TWIN_RATIONALE)]
        assert base, c.rationale
        assert c.used_area_m2 == base[0].used_area_m2
        assert {z.zone_id for z in c.concept.fixture.zones} == {z.zone_id for z in base[0].concept.fixture.zones}
        assert c.wet_rooms == base[0].wet_rooms
        assert c.concept.fixture.access == base[0].concept.fixture.access


def test_the_quality_candidate_squares_the_master_and_keeps_every_rule(reported):
    site, result = reported
    spec = ArchitecturalSpec(PlotSpec(18.0, 22.5), REPORTED)
    normal, quality = _split(result.candidates)
    realized_q = _realized(spec, site, [(i, c) for i, c in enumerate(result.candidates) if c.quality_repartitioned])
    realized_n = _realized(spec, site, [(i, c) for i, c in enumerate(result.candidates)
                                        if not c.quality_repartitioned and not c.repartitioned][:6])
    valid_q = [(c, p) for c, p in realized_q if p.ok]
    assert valid_q, "at least one quality candidate must solve and pass every check"
    best_q = min(_worst_bedroom_class(p.design) for _, p in valid_q)
    best_n = min(_worst_bedroom_class(p.design) for _, p in realized_n if p.ok)
    assert best_q <= 1.5 + 1e-6, best_q
    assert best_q < best_n - cg._QUALITY_MIN_GAIN
    for candidate, plan in valid_q:
        failed = {c.check_id for c in plan.validation.failures()}
        assert not failed & {"C17", "C20", "C21"}
        # the ensuite still opens from its bedroom, the shared bathroom from the hall
        pairs = {frozenset((d.a, d.b)) for d in plan.design.interior_doors}
        assert frozenset(("MASTER", "BATH_1")) in pairs
        assert frozenset(("HALL", "BATH_2")) in pairs
        # the same house: same footprint, same rooms, and every room inside its hard limits
        base = next(b for b in normal if b.strategy is candidate.strategy
                    and b.concept.footprint_width_m == candidate.concept.footprint_width_m
                    and b.concept.footprint_depth_m == candidate.concept.footprint_depth_m)
        assert plan.design.footprint_m[2:] == (base.concept.footprint_width_m, base.concept.footprint_depth_m)
        for room in plan.design.rooms:
            role = ProgramRole(room.roles[0])
            template = ROOM_TEMPLATES.get(role)
            if template is None or role in (ProgramRole.HALL, ProgramRole.CIRCULATION):
                continue
            aspect = max(room.net_w_m, room.net_h_m) / min(room.net_w_m, room.net_h_m)
            assert aspect <= template.max_aspect_ratio + 1e-6
            assert room.net_area_m2 <= template.hard_max + 0.05


def test_no_quality_candidate_without_an_ensuite():
    """One wet room: no dependent, no host slot, nothing to pair — however poor the bedrooms."""
    result = _generate(F.exact_rectangle(), (20.0, 24.0), NO_ENSUITE)
    assert result.candidates
    assert not _split(result.candidates)[1]


def test_the_quality_search_is_bounded(monkeypatch):
    """Per base plan: at most `_MAX_QUALITY_PAIRINGS` pairings (plus the one call that finds the
    base again and stops), each over the normal nine seams — never the tier-2 window."""
    seams = {"quality": 0}
    bases = {"n": 0}
    original_seam = cg._columns_at_seam
    original_layouts = cg._quality_layouts

    def counting_seam(*args, **kwargs):
        fallback = kwargs.get("fallback", args[6] if len(args) > 6 else None)
        if fallback is not None and fallback.quality:
            seams["quality"] += 1
        return original_seam(*args, **kwargs)

    def counting_layouts(rooms, west, east, hall_ids, corridor, repartition, found):
        bases["n"] += sum(1 for f in found if not f[2])
        return original_layouts(rooms, west, east, hall_ids, corridor, repartition, found)

    monkeypatch.setattr(cg, "_columns_at_seam", counting_seam)
    monkeypatch.setattr(cg, "_quality_layouts", counting_layouts)
    site = _rectangle_site(11.0, 12.0)
    result = _generate(site, (18.0, 22.5), REPORTED)
    assert _split(result.candidates)[1]
    assert bases["n"] > 0
    assert seams["quality"] <= bases["n"] * cg._MAX_SEAM_OPTIONS * (cg._MAX_QUALITY_PAIRINGS + 1)


def test_the_pipeline_primary_changes_only_to_its_own_quality_peer(monkeypatch):
    """Phase 2: the plan a brief already had is still the plan it gets — unless its OWN quality
    peer (same strategy, wings and sizing tier) realizes, validates and clears the acceptance
    rule on the drawing; then the peer is the primary, at the same footprint and area, and the
    displaced base is not offered as an alternative."""
    program = ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2, target_built_area_m2=180)
    with_tier = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program,
                                      max_alternatives=3)
    assert with_tier.ok
    monkeypatch.setattr(cg, "_MAX_QUALITY_PAIRINGS", 0)
    without = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program,
                                    max_alternatives=3)
    assert without.ok and not without.concept.quality_repartitioned
    if not with_tier.concept.quality_repartitioned:
        assert with_tier.concept.rationale == without.concept.rationale
        assert with_tier.design.rooms == without.design.rooms
        return
    chosen, base = with_tier.concept, without.concept
    assert chosen.strategy is base.strategy
    assert [w.rect() for w in chosen.concept.fixture.wings] == [w.rect() for w in base.concept.fixture.wings]
    assert (chosen.shrunk, chosen.over_preferred) == (base.shrunk, base.over_preferred)
    assert chosen.used_area_m2 == base.used_area_m2
    assert with_tier.design.gross_area_m2 == without.design.gross_area_m2
    assert _worst_bedroom_class(with_tier.design) < _worst_bedroom_class(without.design) - 0.05 \
        or _strips(with_tier.design) < _strips(without.design)
    assert with_tier.validation.ok
    assert all(alt.concept.rationale != base.rationale for alt in with_tier.alternatives)


def test_the_reported_brief_is_delivered_with_a_square_master(reported):
    """Phase 2 end to end on the reported brief: the 2.03 master is not what the person gets."""
    site, _ = reported
    result = run_general_from_site(site, plot_size_m=(18.0, 22.5), program=REPORTED)
    assert result.ok and result.validation.ok
    assert result.concept.quality_repartitioned
    assert _worst_bedroom_class(result.design) <= 1.5 + 1e-6
    assert result.design.gross_area_m2 == pytest.approx(10.9 * 8.95)


def test_the_peer_never_replaces_a_plan_it_does_not_beat(monkeypatch):
    """A peer that realizes worse than its planned shapes — here: every peer forced to look like
    its base — leaves the primary alone."""
    from app.vertical_slice import general_pipeline as gp
    monkeypatch.setattr(cg, "_quality_accepts", lambda base, new, by_zone: False)
    site = _rectangle_site(11.0, 12.0)
    result = run_general_from_site(site, plot_size_m=(18.0, 22.5), program=REPORTED)
    assert result.ok and not result.concept.quality_repartitioned
    assert gp is not None


# ------------------------------------------------------------------ the L arm, through the same hook

def test_the_l_arm_gets_a_quality_candidate_through_the_generic_hook():
    site, plot = F.l_shaped_site_deep_primary(), (24.0, 32.0)
    spec = ArchitecturalSpec(PlotSpec(*plot), OPEN_3BR)
    result = _generate(site, plot, OPEN_3BR)
    L = ConceptStrategy.MULTI_WING_SPLIT
    l_normal = [(i, c) for i, c in enumerate(result.candidates) if c.strategy is L and not c.repartitioned]
    l_quality = [(i, c) for i, c in enumerate(result.candidates) if c.strategy is L and c.quality_repartitioned]
    assert l_normal and l_quality
    assert all(i > max(j for j, _ in l_normal) for i, _ in l_quality)
    realized_n = {c.rationale: p for c, p in _realized(spec, site, l_normal)}
    valid_q = [(c, p) for c, p in _realized(spec, site, l_quality) if p.ok]
    assert valid_q
    improved = 0
    for c, p in valid_q:
        assert len(p.design.footprints_m) == 2
        assert not {x.check_id for x in p.validation.failures()} & {"C17", "C20", "C21", "C22"}
        # its base: the normal L candidate with the SAME wings, sizing tier and twin-ness
        bases = [b for _, b in l_normal if not b.quality_repartitioned
                 and b.concept.fixture.wings[0].rect() == c.concept.fixture.wings[0].rect()
                 and b.concept.fixture.wings[1].rect() == c.concept.fixture.wings[1].rect()
                 and (b.shrunk, b.over_preferred) == (c.shrunk, c.over_preferred)
                 and b.rationale.endswith(FREE_TWIN_RATIONALE) == c.rationale.endswith(FREE_TWIN_RATIONALE)
                 and b.rationale.split("L: ")[1].split(";")[0] == c.rationale.split("L: ")[1].split(";")[0]]
        assert bases, c.rationale
        assert c.used_area_m2 == bases[0].used_area_m2
        base_plan = next((realized_n[b.rationale] for b in bases if b.rationale in realized_n), None)
        if base_plan is not None and base_plan.ok:
            # the realized plan beats its base: the worst bedroom-class room moved (the planned
            # gain is 0.1; the solver's wall insets move a realized aspect by a few hundredths),
            # or — its worst no worse — one room fewer sits past 1.6
            worst_q, worst_b = _worst_bedroom_class(p.design), _worst_bedroom_class(base_plan.design)
            if worst_q < worst_b - 0.05 or (worst_q <= worst_b + 0.05
                                            and _strips(p.design) < _strips(base_plan.design)):
                improved += 1
    assert improved >= 1


def _strips(design) -> int:
    return sum(1 for room in design.rooms if ProgramRole(room.roles[0]) in BEDROOM_CLASS
               and max(room.net_w_m, room.net_h_m) / min(room.net_w_m, room.net_h_m) > 1.6)
