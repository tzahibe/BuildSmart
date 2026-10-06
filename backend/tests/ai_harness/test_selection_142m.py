"""Issue #142M — guards for the realized-plan ranking chain (experiment code, wired into nothing).

Pins the two properties the recommendation rests on: the chain is a deterministic TOTAL order built
only from production's own preference terms, and `circulation_prefers` is correctly kept out of it
because it is not transitive.
"""
from __future__ import annotations

import itertools
import json
import os

import pytest

from app.ai_harness.selection_142m import ranking

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RESULT = os.path.join(_REPO, "docs", "reports", "142m-realized-selection", "data", "selection_142m.json")
pytestmark = pytest.mark.skipif(not os.path.exists(RESULT), reason="#142M result not present")


@pytest.fixture(scope="module")
def rows():
    d = json.load(open(RESULT))
    return [r for ds in d["datasets"].values() for r in ds["rows"] if r.get("facts")]


def test_every_term_names_a_production_source():
    for term, source, direction in ranking.TERMS:
        assert source and direction in ("lower", "higher", "pairwise"), term
    # circulation is the only non-scalar and must not be part of the total order
    assert "circulation" not in ranking.KEY_TERMS
    assert ranking.KEY_TERMS[0] == "entrance_rank"
    assert ranking.KEY_TERMS[-2:] == ("neg_heuristic_score", "candidate_index")


def test_the_key_is_a_strict_total_order_on_every_measured_pool(rows):
    """No two plans of a brief share a key, and the ordering is antisymmetric and transitive by
    construction (a tuple comparison), so a winner is always well defined."""
    for r in rows:
        keys = {}
        for cand, f in r["facts"].items():
            k = tuple(tuple(v) if isinstance(v, list) else v for v in
                      (f[t] for t in ranking.KEY_TERMS))
            assert k not in keys, (r["brief"], cand, keys.get(k))
            keys[k] = cand
        order = [int(c) for _k, c in sorted(((tuple(tuple(v) if isinstance(v, list) else v
                                                    for v in (f[t] for t in ranking.KEY_TERMS)), c)
                                             for c, f in r["facts"].items()))]
        assert order == r["new_order"], (r["brief"], order, r["new_order"])
        for a, b, c in itertools.permutations(order, 3):      # transitivity of the realized order
            if order.index(a) < order.index(b) < order.index(c):
                assert order.index(a) < order.index(c)


def test_circulation_prefers_is_observed_to_cycle(rows):
    """The measured justification for excluding it from the total order."""
    assert sum(len(r.get("circulation_cycles", [])) for r in rows) > 0


def test_entrance_rank_never_degrades_in_a_changed_winner(rows):
    """The one claim the recommendation makes: where the chain moves the winner on entrance rank, it
    only ever improves it."""
    for r in rows:
        if not r.get("winner_changed") or r.get("deciding_term") != "entrance_rank":
            continue
        old = r["facts"][str(r["old_winner"])]["entrance_rank"]
        new = r["facts"][str(r["new_winner"])]["entrance_rank"]
        assert new < old, (r["brief"], old, new)
