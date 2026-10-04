"""Issue #142E — permanent regression suite over the 20 frozen briefs (`tests/fixtures/frozen_briefs_142.json`).

Controls (never weakened):
  B01  exact topology, sizing, realization, spatial 6/6, access 4/4, complete validator PASS
  B13  12/12 topology, feasible sizing, LIVING net aspect <= 2.5, realization, >= 1 validator PASS
  representation-limit briefs refuse explicitly (never partial topology); B19 is NON_PLANAR
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
from app.vertical_slice.band_pipeline import PipelineDiagnosis, PipelineSuccess, run_band_pipeline
from app.vertical_slice.geometry_core.engine import net_rect_m

from frozen_briefs import load_fixture, pipeline_input, zones_of  # noqa: E402

FX = load_fixture()
BAND = sorted(b for b, v in FX["briefs"].items() if v["expected_embedding"] == "BAND_REPRESENTABLE")
LIMIT = sorted(b for b, v in FX["briefs"].items() if v["expected_embedding"] == "TOPOLOGY_REPRESENTATION_LIMIT")
assert len(BAND) == 13 and len(LIMIT) == 6 and FX["briefs"]["B19"]["expected_embedding"] == "TOPOLOGY_NON_PLANAR"

#: Interactive bound per proposal (embedding + sizing of every candidate + up to 150 realizations; measured worst ~1 s).
PER_BRIEF_SECONDS = 8.0
#: #142C measured the rank-1 `_solve_grid` sizing 4 of the 13 band briefs; "materially exceeds".
RANK1_SIZING_BASELINE = 4


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
        if isinstance(res, PipelineSuccess) or any(r.stage_reached != "EMBEDDING" for r in res.records):
            sized += 1
    assert sized > RANK1_SIZING_BASELINE + 2, sized


def test_at_least_the_proven_briefs_pass(results):
    passed = sorted(b for b in BAND if isinstance(results[b][0], PipelineSuccess))
    assert {"B01", "B13"} <= set(passed), passed
    assert len(passed) >= 3


def test_every_failure_has_a_typed_diagnosis(results):
    known = {"TOPOLOGY_NON_PLANAR", "TOPOLOGY_REPRESENTATION_LIMIT", "BAND_UNSAT", "EMBEDDING_SEARCH_EXHAUSTED",
             "BAND_GEOMETRY_LIMIT", "SIZING_INFEASIBLE", "NO_ENTRANCE", "SAFE_ROOM_RC_MISSING",
             "ACCESS_SPATIAL_MISMATCH", "EXPOSURE_INFEASIBLE", "VALIDATION_FAILED", "REALIZATION_FAILED"}
    for bid, (res, _) in results.items():
        if isinstance(res, PipelineDiagnosis):
            assert res.code in known, (bid, res.code)
            assert res.stage in ("EMBEDDING", "SIZING", "REALIZATION", "VALIDATORS")


def test_runtime_is_bounded(results):
    slow = {bid: round(dt, 2) for bid, (_, dt) in results.items() if dt > PER_BRIEF_SECONDS}
    assert not slow, slow


def test_pipeline_is_deterministic():
    a = run_band_pipeline(pipeline_input("B01", FX["briefs"]["B01"]))
    b = run_band_pipeline(pipeline_input("B01", FX["briefs"]["B01"]))
    assert isinstance(a, PipelineSuccess) and isinstance(b, PipelineSuccess)
    assert a.placement.rows == b.placement.rows
    assert {k: (r.x, r.y, r.w, r.h) for k, r in a.realized.rects.items()} == \
           {k: (r.x, r.y, r.w, r.h) for k, r in b.realized.rects.items()}
