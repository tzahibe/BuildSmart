"""Issue #155, AC-1/AC-2 evidence.

AC-1: `spikes.two_path_demo.selection.select_briefs` picks 8 briefs from the frozen 432-context
regression corpus by a stable (sha256) hash of each context's own `source_key`, spanning
small/medium/large built area, 2-5 bedrooms, with/without SAFE_ROOM, and at least one narrow and
one wide plot — proven here by re-running the selection against the corpus and checking both that
it reproduces the SAME ids every time and that it matches the ids committed in
`docs/reports/two-path-demo/selected_briefs.json`.

AC-2: both path A (`app.demo.service.generate_demo_design`) and path B
(`app.vertical_slice.rectilinear_realizer.realize_layout`, forced on in this process only) hand
their solved geometry to the exact SAME contract-building entry point,
`app.demo.contract.to_demo_design` — the one function that produces the `DemoDesign` JSON that
Issue #146's shipping drawing layer (`DemoPlan.tsx`) draws. Proven two ways: (1) a static identity
check — the name each call site (`app.demo.service`, `spikes.two_path_demo.run_demo`) imported is
the literal same function object as `app.demo.contract.to_demo_design`; (2) a dynamic call-count
check — patching each call site's own bound name with a spy that wraps the original function,
running one brief through both paths, and asserting both spies actually fired.

What this backend-only proof does NOT cover: that `DemoPlan.tsx` itself was executed against
either path's output. That is a separate, frontend-only step
(`frontend/src/design/twoPathDemoComposites.test.tsx`) this repo's headless test session cannot
run (no `frontend/node_modules` install, `npm install` outside the approved command surface — see
`docs/reports/two-path-demo/results.md`'s "Reproducing this report"). These tests prove identity
and invocation of the shared CONTRACT-BUILDING entry point only, not that the React renderer ran.
"""
from __future__ import annotations

import json
from unittest import mock

import app.demo.service as demo_service
from app.demo.contract import to_demo_design
from app.vertical_slice import rectilinear_realizer
from spikes.two_path_demo import run_demo, selection


def test_realizer_flag_default_is_untouched_by_this_module() -> None:
    """AC-6: `RECTILINEAR_REALIZER_ENABLED` stays `False` on main — `run_path_b`'s own
    `_realizer_forced_on` context manager restores it on every exit, success or refusal."""
    assert rectilinear_realizer.RECTILINEAR_REALIZER_ENABLED is False
    corpus = selection.load_corpus()
    ids = selection.select_briefs(corpus)
    cases = {c["source_key"]: c for c in corpus["cases"]}
    run_demo.run_path_b(cases[ids[0]], run_demo.family_for(ids[0]))
    assert rectilinear_realizer.RECTILINEAR_REALIZER_ENABLED is False


def test_selection_is_deterministic_across_reruns() -> None:
    corpus = selection.load_corpus()
    ids_1 = selection.select_briefs(corpus)
    ids_2 = selection.select_briefs(corpus)
    assert ids_1 == ids_2
    assert len(ids_1) == 8
    assert len(set(ids_1)) == 8


def test_selection_matches_the_committed_ids() -> None:
    """The sample must never silently change after being committed (Issue #155's own Required
    Behavior #1) — this test would fail the moment `select_briefs`'s output no longer matches
    what `docs/reports/two-path-demo/selected_briefs.json` committed."""
    corpus = selection.load_corpus()
    ids = selection.select_briefs(corpus)
    with open(selection.COMMITTED_BRIEFS_PATH, encoding="utf-8") as f:
        committed = json.load(f)["brief_ids"]
    assert ids == committed


def test_selection_spans_the_required_spread() -> None:
    corpus = selection.load_corpus()
    ids = selection.select_briefs(corpus)
    cases = {c["source_key"]: c for c in corpus["cases"]}
    contexts = [cases[i]["context"] for i in ids]

    assert all(selection.MIN_BEDROOMS <= c["bedrooms"] <= selection.MAX_BEDROOMS
               for c in contexts)
    assert any(c["safe_room"] for c in contexts)
    assert any(not c["safe_room"] for c in contexts)

    ratios = [c["plot_width_m"] / c["plot_depth_m"] for c in contexts]
    assert any(r <= selection.NARROW_MAX_RATIO for r in ratios)
    assert any(r >= selection.WIDE_MIN_RATIO for r in ratios)

    areas = sorted(c["context"]["built_area_m2"]
                    for c in selection._eligible_pool(corpus))  # noqa: SLF001
    n = len(areas)
    p33, p66 = areas[n // 3], areas[(2 * n) // 3]
    tiers = {selection._size_tier(c["built_area_m2"], p33, p66)  # noqa: SLF001
              for c in contexts}
    assert tiers == {"SMALL", "MEDIUM", "LARGE"}


def test_both_paths_use_the_same_contract_entry_point_by_identity() -> None:
    """Static proof: the name path A's own module (`app.demo.service`) imported IS the literal
    same function object `app.demo.contract.to_demo_design` — not a copy, not a re-implementation
    — and so is the name path B's own module (`spikes.two_path_demo.run_demo`) imported."""
    assert demo_service.to_demo_design is to_demo_design
    assert run_demo.to_demo_design is to_demo_design


def test_both_paths_actually_call_the_same_entry_point() -> None:
    """Dynamic proof, on one real brief: path A (the real product call) and path B (the
    realizer, forced on only for this call) each produce a `DemoDesign` by calling their own
    bound `to_demo_design` name — both patched here, wrapping the SAME original function, so a
    call through EITHER path is observable, and both must fire for this test to pass."""
    corpus = selection.load_corpus()
    ids = selection.select_briefs(corpus)
    cases = {c["source_key"]: c for c in corpus["cases"]}

    with mock.patch.object(demo_service, "to_demo_design", wraps=to_demo_design) as spy_a, \
            mock.patch.object(run_demo, "to_demo_design", wraps=to_demo_design) as spy_b:
        # Path A: real product call, always succeeds on a PLANNED corpus brief.
        a = run_demo.run_path_a(cases[ids[0]])
        assert a.outcome == "REALIZED"
        assert spy_a.call_count >= 1

        # Path B: try the committed briefs in order until one REALIZES (a refusal never reaches
        # `to_demo_design` at all — see this module's own AC-3 discipline) — deterministic given
        # the frozen corpus, no brief is ever substituted for a "nicer" one outside this set.
        realized_b = None
        for brief_id in ids:
            b = run_demo.run_path_b(cases[brief_id], run_demo.family_for(brief_id))
            if b.outcome == "REALIZED":
                realized_b = b
                break
        assert realized_b is not None, (
            "none of the 8 committed briefs' path-B construction realized — this test's own "
            "entry-point proof needs at least one; see docs/reports/two-path-demo/results.md "
            "for the full per-brief outcome")
        assert spy_b.call_count >= 1

    assert isinstance(a.demo_design.gross_area_m2, float)
    assert isinstance(realized_b.demo_design.gross_area_m2, float)
