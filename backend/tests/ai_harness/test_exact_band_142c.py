"""#142C driver — the stage separation and the witness artifact's own integrity.

No solver here: the witnesses are a committed artifact; this test checks that every witness the
driver would trust is (a) a well-formed GridWing (rows tile n_cols) and (b) carries every required
edge by the realizer's own `Rect.shared_edge_len_u`, and that the stage mapping never reports a
downstream refusal as a topology failure.
"""
import json
import os

import pytest

from app.ai_harness.topology_poc import exact_band_142c as x
from app.vertical_slice.geometry_core.model import Rect


def test_stage_of_refusal_never_maps_downstream_to_embedding():
    assert x.stage_of_refusal("AREA_INFEASIBLE") == "SIZING"
    assert x.stage_of_refusal("SHORT_SIDE_INFEASIBLE") == "SIZING"
    assert x.stage_of_refusal("GRID_INFEASIBLE") == "SIZING"
    assert x.stage_of_refusal("ENVELOPE_TOO_LARGE") == "REALIZATION"
    assert x.stage_of_refusal("NO_ENTRANCE") == "REALIZATION"
    assert x.stage_of_refusal("VALIDATION_FAILED") == "VALIDATORS"
    for c in ("AREA_INFEASIBLE", "ENVELOPE_TOO_LARGE", "VALIDATION_FAILED", "SOMETHING_ELSE"):
        assert x.stage_of_refusal(c) != "EMBEDDING"


def test_verify_embedding_rejects_a_missing_contact():
    rows = [[("A", 1), ("B", 1)], [("C", 2)]]
    ok, missing = x.verify_embedding(rows, 2, [("A", "B"), ("A", "C"), ("B", "C")])
    assert ok and not missing
    rows2 = [[("A", 1), ("B", 1)], [("C", 1), ("D", 1)]]
    ok2, missing2 = x.verify_embedding(rows2, 2, [("A", "D")])   # diagonal = corner only
    assert not ok2 and missing2 == [("A", "D")]
    with pytest.raises(ValueError):
        x.verify_embedding([[("A", 1)]], 2, [])


@pytest.mark.skipif(not os.path.exists(x.DEFAULT_WITNESSES_JSON), reason="witness artifact absent")
def test_committed_witness_artifact_is_exact():
    wit = json.load(open(x.DEFAULT_WITNESSES_JSON))
    n_band = 0
    for bid, rec in wit["briefs"].items():
        edges = [tuple(e) for e in rec["edges"]]
        if rec["classification"] != "BAND_REPRESENTABLE":
            assert not rec["witnesses"], f"{bid}: an UNSAT brief must carry no witness"
            assert rec["classification"] in ("NON_PLANAR", "RECTANGULAR_OBSTRUCTION", "BAND_UNSAT")
            continue
        n_band += 1
        assert rec["witnesses"], f"{bid}: BAND_REPRESENTABLE needs >= 1 witness"
        for w in rec["witnesses"]:
            rows = [[(z, int(s)) for z, s in row] for row in w["rows"]]
            ok, missing = x.verify_embedding(rows, int(w["n_cols"]), edges)
            assert ok, f"{bid}: witness drops {missing}"
            zones = sorted(z for row in rows for z, _ in row)
            assert zones == sorted({r for e in edges for r in e} | set(zones)), f"{bid}: zone set mismatch"
    assert n_band == 13
