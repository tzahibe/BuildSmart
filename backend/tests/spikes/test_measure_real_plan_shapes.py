"""AC-2 for Issue #102: the measurement script runs deterministically on the committed POC corpus
fixture (tests/spikes/fixtures/geometry_shapes/plans/, 19 real ResPlan plans + 1 synthetic control,
CC BY 4.0 -- see ATTRIBUTION.md next to it). These numbers are quoted in
docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md section 3 -- if this test's expectations ever need
to change, that report's numbers need to change with them.
"""
from __future__ import annotations

from spikes.geometry_shapes.measure_real_plan_shapes import (
    ARTIFACT,
    DEFAULT_CORPUS_DIR,
    L_SHAPED,
    OTHER,
    RECTANGLE,
    classify_room_shape,
    load_corpus,
    measure_plan,
    summarize,
)


def _load_and_measure():
    plans = load_corpus(DEFAULT_CORPUS_DIR)
    return [measure_plan(p) for p in plans]


def test_fixture_corpus_has_20_plans_19_real_1_synthetic():
    results = _load_and_measure()
    assert len(results) == 20
    synthetic = [r for r in results if r.is_synthetic]
    assert len(synthetic) == 1
    assert synthetic[0].plan_id == "synthetic-spine-01"


def test_measurement_is_deterministic_across_runs():
    first = summarize(_load_and_measure())
    second = summarize(_load_and_measure())
    assert first.room_shape_counts == second.room_shape_counts
    assert first.envelope_shape_counts == second.envelope_shape_counts
    assert first.guillotine_counts == second.guillotine_counts


def test_synthetic_spine_control_is_guillotine_separable():
    """A trivially separable layout (a straight corridor with three bedrooms in a row) must come
    back True -- proves the algorithm is not vacuously always False."""
    results = _load_and_measure()
    synthetic = next(r for r in results if r.is_synthetic)
    assert synthetic.guillotine_separable is True


def test_frozen_room_shape_shares_on_real_plans():
    summary = summarize(_load_and_measure())
    assert summary.n_plans_real == 19
    assert summary.n_rooms_total == 179
    assert summary.room_shape_counts[RECTANGLE] == 75
    assert summary.room_shape_counts[L_SHAPED] == 35
    assert summary.room_shape_counts[OTHER] == 49
    assert summary.room_shape_counts[ARTIFACT] == 20


def test_frozen_room_shape_shares_on_3_5_bedroom_subset():
    summary = summarize(_load_and_measure())
    assert summary.n_plans_3_5br == 17
    assert summary.n_rooms_3_5br == 154
    assert summary.room_shape_counts_3_5br[RECTANGLE] == 68
    assert summary.room_shape_counts_3_5br[L_SHAPED] == 32
    assert summary.room_shape_counts_3_5br[OTHER] == 38
    assert summary.room_shape_counts_3_5br[ARTIFACT] == 16


def test_frozen_envelope_shapes_are_all_non_rectangular_on_this_sample():
    summary = summarize(_load_and_measure())
    assert summary.envelope_shape_counts.get(RECTANGLE, 0) == 0
    assert summary.envelope_shape_counts.get(L_SHAPED, 0) == 0
    assert summary.envelope_shape_counts[OTHER] == 19


def test_frozen_zero_of_19_real_plans_are_guillotine_separable():
    """The headline finding: every real plan measured needs at least one cut that would cross a
    room to separate its rooms with straight lines."""
    summary = summarize(_load_and_measure())
    assert summary.guillotine_counts.get("True", 0) == 0
    assert summary.guillotine_counts["False"] == 19


def test_classify_room_shape_unit_rectangle():
    square = [[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0], [0.0, 0.0]]
    assert classify_room_shape(square) == RECTANGLE


def test_classify_room_shape_unit_l_shape():
    # A 4x4 square with a 2x2 notch bitten out of one corner: 6 vertices, one reflex, orthogonal.
    l_shape = [
        [0.0, 0.0], [4.0, 0.0], [4.0, 2.0], [2.0, 2.0], [2.0, 4.0], [0.0, 4.0], [0.0, 0.0],
    ]
    assert classify_room_shape(l_shape) == L_SHAPED


def test_classify_room_shape_unit_other_for_a_triangle():
    triangle = [[0.0, 0.0], [4.0, 0.0], [2.0, 3.0], [0.0, 0.0]]
    assert classify_room_shape(triangle) == OTHER


def test_classify_room_shape_self_intersecting_bowtie_ring_keeps_largest_piece():
    """Issue #106: a self-intersecting ("bowtie") ring -- two squares joined at a single crossing
    point, as seen on the full 199-plan corpus's resplan_3728 BATHROOM_2 -- makes Shapely's
    buffer(0) repair split into a MultiPolygon (a 2x2 and a 3x3 square) instead of one Polygon.
    _polygon_from_ring must keep the largest piece rather than crashing on `.exterior`."""
    bowtie = [
        [0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0],
        [3.0, 0.0], [6.0, 0.0], [6.0, 3.0], [3.0, 3.0], [3.0, 0.0],
    ]
    assert classify_room_shape(bowtie) == RECTANGLE
