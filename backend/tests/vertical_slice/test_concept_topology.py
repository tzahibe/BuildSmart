"""ConceptSpec contract (Issue #75): every candidate carries a verified `circulation_class`, and
`topologically_distinct` is a pure, deterministic fact over (class, zoning, wet-core grouping)."""
from __future__ import annotations

import pytest

from app.vertical_slice import concept_generator as cg
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.concept_spec import (
    CirculationClass,
    apply_architect_hints,
    concept_spec_of,
    hints_from_architect_spec,
    topologically_distinct,
    verify_class,
)
from app.vertical_slice.general_pipeline import _realize, run_general_from_site
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

# ------------------------------------------------------------------ canonical fixtures sample

#: Three of the four end-to-end sites `test_general_pipeline.py` uses (`SiteConstraints`
#: fixtures only — `concave_facade` returns a `BuildableRegion` directly and is exercised by
#: that module already), plus the L-parti's own real site — the canonical fixtures this Issue's
#: AC-1 names. Kept small and deterministic so this test costs one solver pass per candidate,
#: not a combinatorial sweep.
_SITES = {
    "A_rectangle": (F.exact_rectangle(), (20.0, 24.0)),
    "B_l_shape": (F.l_shaped_site(), (24.0, 28.0)),
    "D_obstacle": (F.rectangular_obstacle_site(), (24.0, 28.0)),
    "E_l_deep_primary": (F.l_shaped_site_deep_primary(), (24.0, 32.0)),
}

#: Programmes chosen to reach every builder this module can produce today: a plain 3BR (spine
#: family), an open-plan 3BR+safe+2wet with a target area (front band reachable), and the L
#: parti's own OPEN_3BR (two adjacent safe wings, `test_l_parti.py`'s own brief).
_PROGRAMS = {
    "3BR": ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2),
    "3BR_SAFE_OPEN_TARGET": ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2,
                                        open_plan_living=True, target_built_area_m2=170.0),
    "OPEN_3BR_L": ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=True, wet_rooms=2,
                              parking_spaces=2, target_built_area_m2=200),
}


def _realized_plans():
    """Every candidate `generate_concepts` produces for each (site, programme) pair, realized —
    the (candidate, plan) pairs `verify_class` is checked against."""
    out = []
    for site, plot in _SITES.values():
        buildable = build_buildable_region(site)
        adapted = adapt(buildable)
        for program in _PROGRAMS.values():
            spec = ArchitecturalSpec(PlotSpec(*plot), program)
            generated = cg.generate_concepts(spec, list(adapted.candidates))
            for index, candidate in enumerate(generated.candidates):
                try:
                    solve = solve_fixture(candidate.concept.fixture)
                except GeometryInfeasible:
                    continue
                plan = _realize(spec, buildable, site, candidate, index, solve, ())
                out.append((candidate, plan))
    return out


@pytest.fixture(scope="module")
def realized_sample():
    sample = _realized_plans()
    assert sample, "expected at least one realized candidate from the canonical fixtures"
    return sample


def test_every_candidate_carries_a_verified_circulation_class(realized_sample):
    classes_seen = set()
    for candidate, plan in realized_sample:
        assert candidate.circulation_class in CirculationClass
        classes_seen.add(candidate.circulation_class)
        assert verify_class(candidate, plan) is None, (
            candidate.strategy.value, candidate.circulation_class, plan.circulation_class,
            candidate.rationale)
    # Sanity: the sample genuinely exercises more than one builder, not just SPINE.
    assert classes_seen >= {CirculationClass.SPINE, CirculationClass.FRONT_BAND,
                           CirculationClass.TWO_WING}


def test_every_candidate_from_the_frozen_regression_baseline_is_verified():
    """AC-1's "realized primaries of the corpus sample used in the tests" — the frozen
    single-level baseline (`pipeline.run_demo`) every regression context replays through."""
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0),
                                   max_alternatives=3)
    assert result.outcome.name == "SOLVED"
    assert result.concept.circulation_class == result.circulation_class
    for alt in result.alternatives:
        assert verify_class(alt.concept, alt) is None


# ------------------------------------------------------------------ topologically_distinct

def test_topologically_distinct_spine_vs_hub_and_relabelings():
    site, plot = _SITES["A_rectangle"]
    buildable = build_buildable_region(site)
    adapted = adapt(buildable)
    spec = ArchitecturalSpec(PlotSpec(*plot), _PROGRAMS["3BR"])
    generated = cg.generate_concepts(spec, list(adapted.candidates))
    spine = next(c for c in generated.candidates
                if c.circulation_class is CirculationClass.SPINE)

    # A spine vs a hub candidate: different circulation_class -> distinct, regardless of
    # anything else (same programme, same footprint size).
    hub_like = replace_class(spine, CirculationClass.HUB_LOBBY)
    assert topologically_distinct(concept_spec_of(spine), concept_spec_of(hub_like))

    # Two spine RELABELINGS: `general_pipeline._family_signature`'s own docstring notes that
    # different generator strategies "regularly realize to IDENTICAL geometry" — a closed
    # (non-open-plan) 3BR/2-wet brief on this site is exactly such a case: SPINE_DOUBLE_LOADED
    # and SPINE_SERVICE_CLUSTER both realize to the same drawing, so they must not read as
    # topologically distinct even though the generator gave them different names.
    closed_spec = ArchitecturalSpec(PlotSpec(*plot),
                                    ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2,
                                               open_plan_living=False))
    closed_generated = cg.generate_concepts(closed_spec, list(adapted.candidates))
    plans_by_strategy: dict[str, tuple] = {}
    for index, candidate in enumerate(closed_generated.candidates):
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        plan = _realize(closed_spec, buildable, site, candidate, index, solve, ())
        plans_by_strategy.setdefault(candidate.strategy.value, []).append((candidate, plan))
    double_loaded = plans_by_strategy["SPINE_DOUBLE_LOADED"][0]
    service_cluster = plans_by_strategy["SPINE_SERVICE_CLUSTER"][0]
    assert double_loaded[1].layout_signature == service_cluster[1].layout_signature
    assert not topologically_distinct(concept_spec_of(double_loaded[0]),
                                      concept_spec_of(service_cluster[0]))


def replace_class(candidate, circulation_class):
    """Test-only: a candidate identical to `candidate` except for its declared class — used to
    prove `topologically_distinct` reacts to the class alone, without needing a second builder
    that can actually realize a HUB_LOBBY candidate on this outline (see `HUB_VS_HARD_MAXIMA` in
    `test_concept_generator.py`)."""
    from dataclasses import replace as dc_replace
    return dc_replace(candidate, circulation_class=circulation_class)


def test_topologically_distinct_is_pure_and_deterministic():
    site, plot = _SITES["A_rectangle"]
    buildable = build_buildable_region(site)
    adapted = adapt(buildable)
    spec = ArchitecturalSpec(PlotSpec(*plot), _PROGRAMS["3BR"])
    generated = cg.generate_concepts(spec, list(adapted.candidates))
    a = concept_spec_of(generated.candidates[0])
    b = concept_spec_of(generated.candidates[0])
    assert a == b
    assert topologically_distinct(a, b) is False
    # Calling it again gives the exact same answer (no hidden state).
    assert topologically_distinct(a, b) is False


# ------------------------------------------------------------------ Architect Model hints (AC-5)

def test_architect_model_hints_never_override_authoritative_requirements():
    """A fake `ArchitectModelGateway` whose response hints at an OPEN-plan (no hallway) concept —
    contradicting a real SPINE candidate's own authoritative `circulation_class` — must never
    change that candidate's `ConceptSpec`: the hint is attached for the record and the
    contradiction is dropped and reported, the same precedent
    `app.architect.authoritative_merge.merge_authoritative_requirements` sets for BuildSmart's own
    hard requirements winning over anything a model returned."""
    from app.architect.gateway import ArchitectModelGateway
    from app.architect.models import (
        ArchitectModelRequest,
        ArchitecturalSpec as ArchitectModelSpec,
        Circulation,
        ProgramItem,
        SiteSpec,
        Zone,
    )

    class FakeGateway(ArchitectModelGateway):
        """Returns a fixed response naming an OPEN-plan circulation strategy — deliberately the
        opposite of `requires_hallway=True`, so its hint contradicts a SPINE candidate on
        purpose."""

        def generate(self, request: ArchitectModelRequest) -> ArchitectModelSpec:
            return ArchitectModelSpec(
                program=[ProgramItem(room_type="living_room", count=1)],
                zones=[Zone(name="public", room_types=["living_room"])],
                relationships=[],
                circulation=Circulation(entry_room_type="living_room", requires_hallway=False),
            )

    site, plot = _SITES["A_rectangle"]
    buildable = build_buildable_region(site)
    adapted = adapt(buildable)
    spec = ArchitecturalSpec(PlotSpec(*plot), _PROGRAMS["3BR"])
    generated = cg.generate_concepts(spec, list(adapted.candidates))
    spine = next(c for c in generated.candidates
                if c.circulation_class is CirculationClass.SPINE)
    authoritative = concept_spec_of(spine)
    assert authoritative.circulation_class is CirculationClass.SPINE

    gateway = FakeGateway()
    request = ArchitectModelRequest(brief="a house", site=SiteSpec(width_m=10.0, depth_m=10.0))
    architect_spec = gateway.generate(request)
    hints = hints_from_architect_spec(architect_spec)
    assert hints.circulation_style_hint == "OPEN"

    merged, dropped = apply_architect_hints(authoritative, hints)
    # Attached for the record...
    assert merged.architect_hints == hints
    # ...but the authoritative fact is untouched: OPEN never maps to a class, so it cannot drop
    # anything (it isn't precise enough to contradict SPINE) — the merged spec keeps SPINE either way.
    assert merged.circulation_class is CirculationClass.SPINE
    assert merged.zoning == authoritative.zoning
    assert merged.wet_core_groups == authoritative.wet_core_groups

    # Now force an UNAMBIGUOUS contradiction: a hallway-requiring ("SPINE") hint compared against
    # a candidate this Issue's own generator built as FRONT_BAND.
    front_band = next(c for c in generated.candidates
                      if c.circulation_class is CirculationClass.FRONT_BAND)
    front_band_spec = concept_spec_of(front_band)
    contradicting_hints = hints_from_architect_spec(
        ArchitectModelSpec(
            program=[ProgramItem(room_type="living_room", count=1)],
            zones=[Zone(name="public", room_types=["living_room"])],
            relationships=[],
            circulation=Circulation(entry_room_type="living_room", requires_hallway=True),
        )
    )
    assert contradicting_hints.circulation_style_hint == "SPINE"

    merged2, dropped2 = apply_architect_hints(front_band_spec, contradicting_hints)
    # The hint is dropped and reported...
    assert len(dropped2) == 1
    assert dropped2[0].field == "circulation_class"
    assert dropped2[0].hinted_value == "SPINE"
    assert dropped2[0].authoritative_value == "FRONT_BAND"
    # ...and NEVER applied: the authoritative FRONT_BAND fact is unchanged.
    assert merged2.circulation_class is CirculationClass.FRONT_BAND
    assert merged2.architect_hints == contradicting_hints
