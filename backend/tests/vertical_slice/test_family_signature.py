"""`RealizedPlan.family_signature` — the dimension- and mirror-independent organisation of a plan.

Metadata only (feature 006, owner constraint 2026-09-13): it is never read by `run_general`,
`_alternative_plans` or the concept generator. The service uses it solely to de-duplicate which
alternatives are SHOWN. These tests pin what "same family" means.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.vertical_slice import concept_generator as cg
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.geometry_core.model import Cut, Leaf, Split
from app.vertical_slice.safe_adapter import AdapterOutcome, adapt
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

PROGRAMS = {
    "2BR_open": ProgramSpec(bedrooms=2, wet_rooms=1, safe_room=False, open_plan_living=True,
                            target_built_area_m2=132.0),
    "3BR_safe_open": ProgramSpec(bedrooms=3, wet_rooms=2, safe_room=True, open_plan_living=True,
                                 target_built_area_m2=181.0),
    "3BR_3wet_closed": ProgramSpec(bedrooms=3, wet_rooms=3, safe_room=True, open_plan_living=False,
                                   target_built_area_m2=195.0),
    "4BR_closed": ProgramSpec(bedrooms=4, wet_rooms=1, safe_room=False, open_plan_living=False,
                              target_built_area_m2=132.0),
}
FOOTPRINTS = {"2BR_open": (11.0, 12.0), "3BR_safe_open": (12.5, 14.5),
              "3BR_3wet_closed": (13.0, 15.0), "4BR_closed": (11.0, 12.0)}


def _buildable(w: float, d: float) -> BuildableRegion:
    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(3.0, 5.5, w, d))),
        Provenance(Source.USER, Authority.AUTHORITATIVE, ref="test"))


def _realized_candidates(name: str) -> list[gp.RealizedPlan]:
    """Every candidate the generator offers for the brief, realized where the solver can."""
    program = PROGRAMS[name]
    w, d = FOOTPRINTS[name]
    spec = ArchitecturalSpec(plot=PlotSpec(width_m=w + 6, depth_m=d + 9.5), program=program)
    buildable = _buildable(w, d)
    adapter = adapt(buildable)
    assert adapter.outcome is AdapterOutcome.SOLVED
    generated = cg.generate_concepts(spec, list(adapter.candidates))
    out = []
    for index, candidate in enumerate(generated.candidates):
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        out.append(gp._realize(spec, buildable, None, candidate, index, solve, ()))
    assert out, f"{name}: no candidate solved"
    return out


@pytest.fixture(scope="module")
def realized() -> dict[str, list[gp.RealizedPlan]]:
    return {name: _realized_candidates(name) for name in PROGRAMS}


def _twin_base(plan: gp.RealizedPlan) -> str:
    rationale = plan.concept.rationale
    suffix = "; " + cg.FREE_TWIN_RATIONALE
    return rationale[: -len(suffix)] if rationale.endswith(suffix) else rationale


def test_a_forced_tree_and_its_unforced_twin_share_a_family(realized):
    pairs = 0
    for plans in realized.values():
        by_base: dict[str, dict[bool, str]] = {}
        for plan in plans:
            is_twin = plan.concept.rationale.endswith(cg.FREE_TWIN_RATIONALE)
            by_base.setdefault(_twin_base(plan), {})[is_twin] = plan.family_signature
        for sigs in by_base.values():
            if True in sigs and False in sigs:
                assert sigs[True] == sigs[False]
                pairs += 1
    assert pairs > 0, "no forced/twin pair solved — the fixture no longer exercises the property"


def test_forced_positions_do_not_change_the_family(realized):
    plan = realized["3BR_safe_open"][0]
    fixture = plan.concept.concept.fixture

    def strip(node):
        if isinstance(node, Leaf):
            return node
        return Split(node.cut, strip(node.first), strip(node.second), None)

    stripped = replace(fixture, wings=tuple(replace(w, tree=strip(w.tree)) for w in fixture.wings))
    assert gp._family_signature(stripped, plan.concept.strategy) == plan.family_signature


def test_a_mirrored_tree_is_the_same_family(realized):
    plan = realized["3BR_safe_open"][0]
    fixture = plan.concept.concept.fixture

    def mirror(node):
        if isinstance(node, Leaf):
            return node
        if node.cut is Cut.V:
            return Split(Cut.V, mirror(node.second), mirror(node.first), None)
        return Split(Cut.H, mirror(node.first), mirror(node.second), None)

    mirrored = replace(fixture, wings=tuple(replace(w, tree=mirror(w.tree)) for w in fixture.wings))
    assert gp._family_signature(mirrored, plan.concept.strategy) == plan.family_signature


def test_two_strategy_names_with_the_same_allocation_are_one_family(realized):
    """SPINE_DOUBLE_LOADED and SPINE_SERVICE_CLUSTER regularly produce the identical tree
    (measured: 66 of 77 co-occurrences). A name is not a family."""
    from app.vertical_slice.geometry_core.model import leaves_of

    found = 0
    for plans in realized.values():
        by_leaves: dict[tuple, dict[str, str]] = {}
        for plan in plans:
            strategy = plan.concept.strategy.value
            if strategy not in ("SPINE_DOUBLE_LOADED", "SPINE_SERVICE_CLUSTER"):
                continue
            key = tuple(leaves_of(plan.concept.concept.fixture.wings[0].tree))
            by_leaves.setdefault(key, {})[strategy] = plan.family_signature
        for sigs in by_leaves.values():
            if len(sigs) == 2:
                assert len(set(sigs.values())) == 1
                found += 1
    assert found > 0, "fixture no longer has an SDL/SSC pair with the same leaves"


def test_the_signature_carries_no_dimensions(realized):
    for plans in realized.values():
        for plan in plans:
            assert not any(ch.isdigit() for ch in plan.family_signature), plan.family_signature
            assert plan.family_signature.startswith(("V[", "H[", "HUB:"))


def test_the_signature_distinguishes_the_two_partis(realized):
    """A front band (root H, public across the front) and a spine (root V) are different houses."""
    families = {plan.family_signature for plan in realized["4BR_closed"]}
    roots = {f.split("[")[0] for f in families if not f.startswith("HUB:")}
    assert roots == {"H", "V"}, families


def test_a_hub_strategy_is_prefixed_even_though_its_root_is_a_band():
    """The hub parti (branch 005) also puts a public band at the root; without the prefix it would
    collapse into the band family. Exercised through the helper directly so this holds whether or
    not the hub strategy exists on the current branch."""
    hub_strategy = getattr(cg.ConceptStrategy, "HUB_PRIVATE_WING", None)
    if hub_strategy is None:
        pytest.skip("HUB_PRIVATE_WING is not on this branch")
    plan = _realized_candidates("3BR_safe_open")[0]
    fixture = plan.concept.concept.fixture
    assert gp._family_signature(fixture, hub_strategy).startswith("HUB:")
