"""#213 AC-1 — the comparison harness runs BOTH engines on one brief and produces, for each, a
payload the product's own renderer can draw.

This is a test of the HARNESS, not of architectural quality: it asserts that one brief goes
through `app.demo.service.generate_demo_design` twice (production, then `brain=True`, which is
exactly what `?engine=brain` sets) and that both results carry the fields `DemoPlan` reads. It
deliberately asserts nothing about which plan is better — that judgment belongs in the report,
where a human signs it.

The brain's exact sizer is a real MILP search, so the single brief used here is the smallest in
the corpus (B08, 11 x 12 m). It still costs about 30 s of solver time — deliberate: a cheaper
test would not prove that the harness drives the real product path.
"""
from __future__ import annotations

import json

from app.ai_harness.comparison_corpus import corpus as corpus_mod
from app.ai_harness.comparison_corpus import run as cc
from app.ai_harness.topology_poc import briefs as briefs_mod

BRIEF = "B08"


def test_corpus_covers_the_declared_envelope_families():
    """AC-2's corpus shape, pinned: 20-30 briefs, every declared family present, every entry
    naming the file it came from."""
    briefs = briefs_mod.select_briefs()
    entries = cc.build_corpus(briefs)
    assert 20 <= len(entries) <= 30, len(entries)
    assert {e.source for e in entries} == {"real", "frozen"}
    families = {e.family for e in entries}
    for required in (corpus_mod.SQUARE, corpus_mod.RECT, corpus_mod.NARROW,
                     corpus_mod.L_SHAPE, corpus_mod.COURT, corpus_mod.IRREGULAR):
        assert required in families, f"{required} missing from the corpus"
    # AC-3: the three briefs the owner named are in it, as real briefs.
    by_id = {e.brief_id: e for e in entries}
    for bid in corpus_mod.HEADLINE:
        assert by_id[bid].source == "real"


def test_rectangle_family_bands_are_reproducible():
    assert corpus_mod.rectangle_family(11, 12) == corpus_mod.SQUARE
    assert corpus_mod.rectangle_family(12, 18) == corpus_mod.RECT
    assert corpus_mod.rectangle_family(18, 12) == corpus_mod.WIDE
    assert corpus_mod.rectangle_family(24, 9.5) == corpus_mod.NARROW


def test_both_engines_run_on_one_brief_and_produce_renderable_payloads(tmp_path):
    """AC-1. Both engines, one brief, through the product's own entry point; each result is
    written as the `DemoDesign` JSON the product renderer consumes."""
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[BRIEF]
    project = cc.project_for(b)
    out = str(tmp_path)

    results = {}
    for label, brain in (("production", False), ("brain", True)):
        results[label] = cc.run_engine(project, b.built_area_m2, brain=brain,
                                       out_dir=out, name=f"{BRIEF}__{label}")

    for label, rec in results.items():
        assert rec["outcome"] == "PLAN", f"{label}: {rec}"
        payload = json.load(open(tmp_path / "designs" / rec["render"]))
        # exactly the fields `frontend/src/design/DemoPlan.tsx` reads off the design
        for field in ("plot", "footprint", "rooms", "walls", "doors", "windows", "garden",
                      "entrance_walk", "parking", "layout", "validation"):
            assert field in payload, f"{label} payload has no {field}"
        assert payload["rooms"], f"{label} drew no rooms"
        assert any(d.get("is_entrance") for d in payload["doors"]), f"{label} has no entrance door"
        # objective measurement is present and is a number, so the report's table cannot be empty
        assert isinstance(rec["gross_m2"], (int, float))
        assert isinstance(rec["circulation_share"], float)
        assert rec["validators_total"] > 0

    # the two engines are genuinely two engines: the brain labels its plan with its parti
    assert results["brain"]["family"].startswith("brain:")
    assert not results["production"]["family"].startswith("brain:")
