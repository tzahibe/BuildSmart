"""Issue #142E/#142G/#142H — permanent regression suite over the 20 frozen briefs
(`tests/fixtures/frozen_briefs_142.json`).

Controls (never weakened):
  B01  exact topology, sizing, realization, spatial 6/6, access 4/4, complete validator PASS
  B13  12/12 topology, feasible sizing, LIVING net aspect <= 2.5, realization, >= 1 validator PASS
  B04/B11/B18  SAFE_ROOM briefs: RC walls on all four sides, C4 PASS (#142G); B11/B18 need the
       #142H selection (door-width sizing + orientation + HARD filter) to pass in production
  every direct-access edge of a passing brief is a real, placeable door (#142H)
  representation-limit briefs refuse explicitly (never partial topology); B19 is NON_PLANAR
  input problems are typed: B07/B09/B17 ACCESS_SPATIAL_CONTRADICTION, B20 ACCESS_POLICY_CONFLICT,
       B06/B12 EXPOSURE_INFEASIBLE (complete family) — none of them is a realizer failure (#142I)
  sizing coverage materially exceeds the rank-1 baseline (#142C: 4/13 band briefs sized)
  runtime is bounded (interactive application)
"""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.vertical_slice.band_embedding import BandEmbedding, embed_band, verify_rows
from app.vertical_slice.band_pipeline import STAGES, PipelineDiagnosis, PipelineSuccess, run_band_pipeline
from app.vertical_slice.geometry_core.engine import net_rect_m
from app.vertical_slice.geometry_core.model import Side, WallType

from frozen_briefs import load_fixture, pipeline_input, zones_of  # noqa: E402

FX = load_fixture()
BAND = sorted(b for b, v in FX["briefs"].items() if v["expected_embedding"] == "BAND_REPRESENTABLE")
LIMIT = sorted(b for b, v in FX["briefs"].items() if v["expected_embedding"] == "TOPOLOGY_REPRESENTATION_LIMIT")
assert len(BAND) == 13 and len(LIMIT) == 6 and FX["briefs"]["B19"]["expected_embedding"] == "TOPOLOGY_NON_PLANAR"

#: Interactive bound per proposal (embedding + selection + sizing of every candidate + up to 150
#: realizations; measured worst ~1.3 s).
PER_BRIEF_SECONDS = 8.0
#: #142C measured the rank-1 `_solve_grid` sizing 4 of the 13 band briefs; "materially exceeds".
RANK1_SIZING_BASELINE = 4
#: The measured production result after #142H (= the #142F selection path + #142G RC walls).
PROVEN_PASSES = {"B01", "B04", "B05", "B08", "B11", "B13", "B18"}
SAFE_ROOM_BRIEFS = ("B04", "B11", "B18")


@pytest.fixture(scope="module")
def results():
    out = {}
    for bid, brief in FX["briefs"].items():
        t = time.perf_counter()
        out[bid] = (run_band_pipeline(pipeline_input(bid, brief)), time.perf_counter() - t)
    return out


# --------------------------------------------------------------------------- embedding

@pytest.mark.parametrize("bid", BAND)
def test_every_band_brief_embeds_exactly(bid):
    brief = FX["briefs"][bid]
    edges = [tuple(e) for e in brief["spatial_adjacency"]]
    r = embed_band(zones_of(brief), edges)
    assert isinstance(r, BandEmbedding), r
    assert r.candidates
    for c in r.candidates:
        assert verify_rows(c.rows, c.n_cols, edges) == [], (bid, c.rows)
        assert sorted(z for row in c.rows for z, _ in row) == sorted(brief["zones"])


@pytest.mark.parametrize("bid", LIMIT)
def test_representation_limit_briefs_refuse_explicitly(bid):
    res, _ = run_band_pipeline(pipeline_input(bid, FX["briefs"][bid])), None
    assert isinstance(res, PipelineDiagnosis)
    assert res.code == "TOPOLOGY_REPRESENTATION_LIMIT" and res.stage == "EMBEDDING"
    assert res.candidates_tried == 0          # never a partial layout


def test_b19_is_non_planar():
    res = run_band_pipeline(pipeline_input("B19", FX["briefs"]["B19"]))
    assert isinstance(res, PipelineDiagnosis)
    assert res.code == "TOPOLOGY_NON_PLANAR" and res.candidates_tried == 0


# --------------------------------------------------------------------------- controls

def test_b01_regression_control(results):
    res, _ = results["B01"]
    assert isinstance(res, PipelineSuccess), res
    assert res.spatial_preserved == "6/6" and res.access_preserved == "4/4"
    assert res.realized.report.ok and res.realized.c27.passed


def test_b13_positive_control(results):
    res, _ = results["B13"]
    assert isinstance(res, PipelineSuccess), res
    assert res.spatial_preserved == "12/12"
    assert res.realized.report.ok
    rects, walls = res.realized.rects, res.realized.walls
    nw, nh, _ = net_rect_m("LIVING", rects["LIVING"], walls)
    assert max(nw, nh) / min(nw, nh) <= 2.5 + 1e-6


# --------------------------------------------------------------------------- coverage / bounds

def test_sizing_materially_exceeds_the_rank1_baseline(results):
    sized = 0
    for bid in BAND:
        res, _ = results[bid]
        if isinstance(res, PipelineSuccess) or any(r.stage_reached not in ("EMBEDDING", "SELECTION") for r in res.records):
            sized += 1
    assert sized > RANK1_SIZING_BASELINE + 2, sized


def test_at_least_the_proven_briefs_pass(results):
    passed = sorted(b for b in BAND if isinstance(results[b][0], PipelineSuccess))
    # B04 joined in Issue #142G (SAFE_ROOM RC walls); B11/B18 in Issue #142H (candidate selection)
    assert PROVEN_PASSES <= set(passed), passed
    assert len(passed) >= 7


def test_every_pass_preserves_every_direct_access_edge_as_a_door(results):
    """#142H: required direct access implies a contact able to carry its door — so every declared
    access edge of a passing brief is realized as a placeable door, none lost."""
    for bid in BAND:
        res, _ = results[bid]
        if not isinstance(res, PipelineSuccess):
            continue
        n = sum(1 for a, b in FX["briefs"][bid]["access_graph"] if a != "ENTRANCE")
        assert res.access_preserved == f"{n}/{n}" and res.access_lost == (), (bid, res.access_preserved, res.access_lost)
        assert res.spatial_preserved.split("/")[0] == res.spatial_preserved.split("/")[1], (bid, res.spatial_preserved)
        placed = {frozenset((d.a, d.b)) for d in res.realized.interior_doors if d.placeable}
        for a, b in FX["briefs"][bid]["access_graph"]:
            if a != "ENTRANCE":
                assert frozenset((a, b)) in placed, (bid, a, b)


@pytest.mark.parametrize("bid", SAFE_ROOM_BRIEFS)
def test_safe_room_briefs_pass_with_rc_walls(results, bid):
    res, _ = results[bid]
    assert isinstance(res, PipelineSuccess), res
    assert all(res.realized.walls[("SAFE_ROOM", s)] is WallType.RC_SAFE_ROOM for s in Side)
    assert next(c for c in res.realized.report.checks if c.check_id == "C4").passed
    assert res.records[-1].flags["safe_room_on_envelope"] is True


def test_entrance_is_chosen_by_orientation_never_invented(results):
    """Every pass has its front door in an ALLOWED_ENTRANCE room that the selected (possibly
    flipped) placement put in the street band — no entrance is added after geometry exists."""
    from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
    for bid in BAND:
        res, _ = results[bid]
        if not isinstance(res, PipelineSuccess):
            continue
        front = res.realized.entrance_door.b
        assert zones_of(FX["briefs"][bid])[front].role in ALLOWED_ENTRANCE_ROLES, (bid, front)
        assert front in {z for z, _ in res.placement.rows[0]}, (bid, front, res.placement.rows[0])
        assert res.records[-1].flags["entrance_now"] is True


def test_input_problems_are_typed(results):
    for bid in ("B07", "B09", "B17"):
        res, _ = results[bid]
        assert isinstance(res, PipelineDiagnosis) and res.code == "ACCESS_SPATIAL_CONTRADICTION", (bid, res)
        assert res.stage == "EMBEDDING" and res.candidates_tried == 0
    # #142I: with the canonical wet-room policy (LIVING = specs/009 public fallback) B12's LIVING door is
    # legal and the proposal's real defect shows: the hall door it asks for into BATHROOM_2 has no wall,
    # and once that contact is required every band layout buries a REQUIRED room. B20 still asks for a
    # two-door bathroom (BEDROOM_1 + HALL), a policy conflict decided from the proposal alone.
    res, _ = results["B12"]
    assert isinstance(res, PipelineDiagnosis) and res.code == "EXPOSURE_INFEASIBLE", res
    assert res.stage == "SELECTION" and "complete family" in res.detail
    res, _ = results["B20"]
    assert isinstance(res, PipelineDiagnosis) and res.code == "ACCESS_POLICY_CONFLICT", res
    assert res.stage == "SELECTION" and res.candidates_tried > 0
    assert all(r.stage_reached == "EMBEDDING" for r in res.records)        # nothing sized or realized
    res, _ = results["B06"]
    assert isinstance(res, PipelineDiagnosis) and res.code == "EXPOSURE_INFEASIBLE", res
    assert res.stage == "SELECTION" and "complete family" in res.detail


def test_every_failure_has_a_typed_diagnosis(results):
    known = {"TOPOLOGY_NON_PLANAR", "TOPOLOGY_REPRESENTATION_LIMIT", "BAND_UNSAT", "EMBEDDING_SEARCH_EXHAUSTED",
             "ACCESS_SPATIAL_CONTRADICTION", "ACCESS_POLICY_CONFLICT",
             "BAND_GEOMETRY_LIMIT", "SIZING_INFEASIBLE", "NO_ENTRANCE", "SAFE_ROOM_RC_MISSING",
             "ACCESS_SPATIAL_MISMATCH", "EXPOSURE_INFEASIBLE", "VALIDATION_FAILED", "REALIZATION_FAILED"}
    for bid, (res, _) in results.items():
        if isinstance(res, PipelineDiagnosis):
            assert res.code in known, (bid, res.code)
            assert res.stage in STAGES


def test_runtime_is_bounded(results):
    slow = {bid: round(dt, 2) for bid, (_, dt) in results.items() if dt > PER_BRIEF_SECONDS}
    assert not slow, slow


@pytest.mark.parametrize("bid", ("B01", "B18"))
def test_pipeline_is_deterministic(bid):
    a = run_band_pipeline(pipeline_input(bid, FX["briefs"][bid]))
    b = run_band_pipeline(pipeline_input(bid, FX["briefs"][bid]))
    assert isinstance(a, PipelineSuccess) and isinstance(b, PipelineSuccess)
    assert a.placement.rows == b.placement.rows and a.candidate_index == b.candidate_index
    assert {k: (r.x, r.y, r.w, r.h) for k, r in a.realized.rects.items()} == \
           {k: (r.x, r.y, r.w, r.h) for k, r in b.realized.rects.items()}
