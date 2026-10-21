"""The screen-aware, bound-aware generator for the exact path (#208): every emitted layout passes
the screens it claims; the pre-check never refuses a layout the exact sizer accepts; the family
is OFF unless asked for and names its maker when it is."""
from __future__ import annotations

import json
import os
import time

import pytest

from app.ai_harness.shape_agnostic.run import CASES_PATH, _extra, _project_for
from app.demo.service import spec_for
from app.vertical_slice.band_embedding import (
    BandPlacement,
    _assign_columns,
    _edge_set,
    embed_band,
    verify_rows,
)
from app.vertical_slice.band_pipeline import hard_rejections, orient, placement_flags
from app.vertical_slice.band_sizing import contact_requirements
from app.vertical_slice.brain.proposer import DeterministicProposer, _hall_intent, programme_from_spec
from app.vertical_slice.brain.runner import _rebanded
from app.vertical_slice.exact.cells import from_bands, moves
from app.vertical_slice.exact.generator import (
    SCREENS,
    depth_frame,
    generate,
    layout_rejections,
    precheck,
)
from app.vertical_slice.exact.screens import transposed_envelope

FROZEN = ("F1-rect-control", "F2-L-envelope-fixed", "F3-wide-shallow-free", "F4-entry-court-notch", "F5-garden-court")


def _case(cid: str):
    spec = json.load(open(os.path.normpath(CASES_PATH)))
    return next(c for c in spec["cases"] if c["id"] == cid)


def _problem(cid: str, parti: str):
    """(zones at the loosest rung, union, access, wet rooms, envelope, arrival) for one frozen
    case and parti — the generator's own input, built the way the harness builds it."""
    case = _case(cid)
    project, env = _project_for(case)
    s = spec_for(project)
    W = env.width_u * 0.05
    p = programme_from_spec(s, (W, env.area_m2 / W))
    prop = next(x for x in DeterministicProposer().propose(p) if x.name == parti)
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    for z in prop.rooms:
        zones.setdefault(z, _hall_intent(z, target=7.0))
    spatial = list(prop.spatial) + _extra(case, "contacts_extra", zones)
    access = [(a, b) for a, b in prop.access if a != "ENTRANCE"] + _extra(case, "access_extra", zones)
    seen: set = set()
    access = [e for e in access if not (frozenset(e) in seen or seen.add(frozenset(e)))]
    union = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted(e)) for e in access})
    return _rebanded(zones, p, None), union, access, p.resolved_wet, env, prop.arrival


# ------------------------------------------------------- every emitted layout passes its screens

@pytest.mark.parametrize("cid,parti", [("F2-L-envelope-fixed", "HALL_SPINE+FOYER"), ("F4-entry-court-notch", "BEDROOM_WING"),
                                       ("F3-wide-shallow-free", "PUBLIC_BAND+FOYER")])
def test_every_emitted_layout_passes_the_screens_it_claims(cid, parti):
    zones, union, access, wet, env, arrival = _problem(cid, parti)
    n = 0
    for orient_tag, env_o in (("H", env), ("V", transposed_envelope(env))):
        for lay in generate(zones, union, access, wet, env_o, arrival=arrival, orient_tag=orient_tag, max_layouts=25):
            n += 1
            assert lay.problems() == [] and lay.admits(union)
            assert layout_rejections(lay, zones, wet, access, arrival=arrival, orient_tag=orient_tag) == []
            assert precheck(lay, zones, env_o) is None
            # the parti's own arrival room is where the front door can go, on the street
            assert arrival in (set(lay.rows[0]) if orient_tag == "H" else {r[0] for r in lay.rows})
            if not lay.spanning and orient_tag == "H":
                # a plain band layout: PRODUCTION's own SELECTION screen agrees, with no flip needed
                es = _edge_set(union)
                rows, n_cols = _assign_columns(lay.rows, es)
                assert verify_rows(rows, n_cols, union) == []
                bp = BandPlacement(rows, n_cols, 0.0, lay.rows)
                flags = placement_flags(bp, zones, wet, tuple(access))
                assert hard_rejections(flags) == (), (lay.rows, hard_rejections(flags))
                assert orient(bp, flags)[1] is False
    assert n > 0, "the generator emitted nothing"


def test_the_generator_is_deterministic_and_searches_several_row_counts_from_its_estimate_outward():
    zones, union, access, wet, env, arrival = _problem("F2-L-envelope-fixed", "HALL_SPINE+FOYER")
    sa, sb = {}, {}
    a = [lay.rows for lay in generate(zones, union, access, wet, env, arrival=arrival, max_layouts=40, stats=sa)]
    b = [lay.rows for lay in generate(zones, union, access, wet, env, arrival=arrival, max_layouts=40, stats=sb)]
    assert a == b and len(a) == 40 and len(set(a)) == 40
    counts = sa["row_counts"]
    assert len(counts) >= 3 and set(counts) >= {2, 3, 4}
    # the most plausible count first (F2: 172 m2 over a 14 m frame at ~4 m per row -> 3), then outward
    assert counts[0] == 3 and sorted(counts[1:3]) == [2, 4]
    # a caller may pin the row count; every layout then has it
    four = [lay for lay in generate(zones, union, access, wet, env, arrival=arrival, row_counts=(4,), max_layouts=5)]
    assert four and all(lay.n_rows in (4, 5) for lay in four)      # 5: a stack splits one row


def test_a_foyer_parti_keeps_the_hall_off_the_street_and_a_hall_parti_puts_it_there():
    zones, union, access, wet, env, arrival = _problem("F2-L-envelope-fixed", "HALL_SPINE+FOYER")
    for lay in generate(zones, union, access, wet, env, arrival=arrival, max_layouts=20):
        assert "ENTRY" in lay.rows[0] and "HALL" not in lay.rows[0]
    zones, union, access, wet, env, arrival = _problem("F2-L-envelope-fixed", "HALL_SPINE")
    for lay in generate(zones, union, access, wet, env, arrival=arrival, max_layouts=20):
        assert "HALL" in lay.rows[0]


def test_the_deadline_stops_the_enumeration():
    zones, union, access, wet, env, arrival = _problem("F3-wide-shallow-free", "BEDROOM_WING+FOYER")
    t0 = time.monotonic()
    list(generate(zones, union, access, wet, env, arrival=arrival, max_layouts=10_000, deadline=t0 + 0.5))
    assert time.monotonic() - t0 < 3.0


# ------------------------------- the pre-check never refuses what the exact sizer finds feasible

@pytest.mark.parametrize("cid", FROZEN)
def test_the_precheck_never_rejects_a_layout_the_milp_finds_feasible(cid):
    """Compared against the MILP screen (`milp_cells`, no objective, the loosest rung, k=6 — the
    15 ms screen of #200) over the band family's own screened candidates and their moves, in both
    orientations: whatever the MILP accepts, the pre-check accepts. The pre-check is a relaxation
    of the sizer's constraints, and this is the test that keeps it one."""
    pytest.importorskip("scipy")
    from app.vertical_slice.exact.milp_cells import milp_cells
    zones, union, access, wet, env, arrival = _problem(cid, "HALL_SPINE+FOYER")
    contacts = contact_requirements(zones, union, access)
    emb = embed_band(zones, union, max_candidates=40)
    layouts = []
    for cand in getattr(emb, "candidates", ()):
        flags = placement_flags(cand, zones, wet, tuple(access))
        if hard_rejections(flags):
            continue
        base = from_bands(orient(cand, flags)[0].bands)
        layouts.append(base)
        layouts.extend(moves(base, zones, union, max_out=6))
    feasible = refused = 0
    for orient_tag, env_o in (("H", env), ("V", transposed_envelope(env))):
        for lay in layouts[:60]:
            verdict = precheck(lay, zones, env_o)
            res = milp_cells(lay, zones, union, env_o, min_contact_u=contacts, k=6, objective="feasible", time_limit_s=2.0)
            if res.status == "FEASIBLE":
                feasible += 1
                assert verdict is None, f"{cid} {orient_tag}: pre-check refused a MILP-feasible layout: {verdict}\n{lay.rows}"
            elif verdict is not None:
                refused += 1
    if cid == "F1-rect-control":
        assert feasible > 0, "the rectangle control must give the comparison something to compare"


def test_the_precheck_refuses_what_cannot_fit():
    """A row whose cells need more width than the envelope offers at any depth, and rows whose
    minimum depths exceed the usable depth."""
    zones, union, access, wet, env, arrival = _problem("F1-rect-control", "HALL_SPINE")
    everything_in_one_row = from_bands((tuple(zones),))
    assert "width" in (precheck(everything_in_one_row, zones, env) or "")
    one_per_row = from_bands(tuple((z,) for z in zones))
    assert "depth" in (precheck(one_per_row, zones, env) or "")
    assert depth_frame(env) is not None


# ----------------------------------------------------------------- the family in the pipeline

def _brief(bid: str):
    from tests.vertical_slice.test_brain import _spec_and_footprint
    return _spec_and_footprint(bid)


def test_the_family_is_off_unless_asked_for_and_names_its_maker_when_on():
    pytest.importorskip("scipy")
    from app.vertical_slice.brain.exact_pipeline import ALL_FAMILIES, GENERATOR_FAMILY
    from app.vertical_slice.brain.runner import run_brain
    assert GENERATOR_FAMILY not in ALL_FAMILIES
    from app.demo import service as svc
    assert GENERATOR_FAMILY not in svc.BRAIN_FAMILIES        # the preview: OFF until the day-3 gate
    spec, fp = _brief("B08")
    off = run_brain(spec, fp, brief="B08", sizer="exact", families=("band",), budget_s=12.0)
    assert all(pl.family != GENERATOR_FAMILY for pl in off.plans)
    on = run_brain(spec, fp, brief="B08", sizer="exact", families=(GENERATOR_FAMILY,), budget_s=25.0)
    assert on.plans and all(pl.sizer in ("production", "exact") for pl in on.plans)
    exact = [pl for pl in on.plans if pl.sizer == "exact"]
    for pl in exact:
        assert pl.family == GENERATOR_FAMILY and pl.realized is not None
        assert pl.rank_key is not None
    # the typed signal when the family runs: the histogram carries its screen verdicts
    assert all(pl.stage != "UNAVAILABLE" for pl in on.plans)


def test_the_claimed_screens_are_the_documented_ones():
    assert SCREENS == ("arrival_fronts_street", "foyer_holds_the_door", "entrance_feasible", "foyer_fronts_street",
                       "exposure_ok", "access_contact_ok", "reachable_from_entrance")
