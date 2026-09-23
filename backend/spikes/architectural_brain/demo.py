"""POC Architectural Brain demo driver (Issue #96, C/3).

Renders the side-by-side comparison this POC is judged by: the CURRENT engine's own baseline for
a fixed benchmark brief, against the brain's own retrieve -> synthesize -> adapt -> realize_concept
alternatives, under ``docs/reports/poc-architectural-brain/brief-N/``.

RUNTIME RULE (why this is a per-plan CLI, not one script that renders everything): a single
``realize_concept`` call can take 20-150s (the compiler's own deterministic search over depth/width
combinations, see ``realize.py``'s own docstring) — running a whole brief's worth of alternatives in
one process risks the 600s foreground budget. Each subcommand below does exactly ONE plan (one
current-engine baseline, or one brain alternative) and writes its own artifact(s) immediately, so a
demo run is a sequence of small, independently resumable commands:

    uv run python3 spikes/architectural_brain/demo.py current      --brief 1
    uv run python3 spikes/architectural_brain/demo.py references   --brief 1
    uv run python3 spikes/architectural_brain/demo.py alternative  --brief 1 --index 0
    uv run python3 spikes/architectural_brain/demo.py alternative  --brief 1 --index 1
    uv run python3 spikes/architectural_brain/demo.py compiled     --brief 1 --class HUB_LOBBY
    uv run python3 spikes/architectural_brain/demo.py compiled     --brief 1 --class BRANCHED
    uv run python3 spikes/architectural_brain/demo.py comparison   --brief 1

``alternative --index K`` realizes the K-th concept of ``synthesize(brief, retrieve(..., k=DEMO_K),
max_candidates=DEMO_MAX_CANDIDATES)`` — deterministic (both ``retrieve`` and ``synthesize`` are pure
functions of the brief/corpus), so the same ``--index`` always reproduces the same concept across
separate processes; it reaches HUB_LOBBY/BRANCHED only when a synthesized concept's OWN declared
``circulation_class`` names one (``realize.py``'s dispatch, Issue #110).

``compiled --class {HUB_LOBBY,BRANCHED}`` is Issue #110's own SECOND, independent way of trying
those two classes: a direct probe of ``concept_compilers.compile_hub_lobby``/``compile_branched``
against this brief's own authoritative programme/site (``realize.realize_compiled_topology``) —
never gated on whether the demo's own retrieval corpus happens to surface a donor reference of
that class (mirrors Concept Engine v2's OWN production dispatch, which tries these compilers on
every brief regardless of what ``patterns_for`` names). This is what lets ``comparison`` report an
honest ATTEMPTED/REALIZED/REFUSED answer for all four classes on every brief, not just the ones a
donor reference happened to suggest.

``comparison`` is the aggregation step: it reads every ``alt-*.json``/``compiled-*.json`` sidecar
already written in the brief's own output directory, assigns brain-A/B/C.svg (Required Behavior 3)
to the REALIZED-and-``ok`` ones in index order, and writes ``comparison.md``.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.demo.contract import to_demo_design
from app.vertical_slice.general_pipeline import run_general_from_site
from app.vertical_slice.spec import PlotSpec
from tests.architectural_brain.briefs import BENCHMARK_BRIEFS, BenchmarkBrief

from spikes.architectural_brain.adaptation import Rejection, adapt
from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.corpus_io import load_corpus_dir
from spikes.architectural_brain.preservation import PreservationReport, measure_preservation
from spikes.architectural_brain.realization_intent import intent_from
from spikes.architectural_brain.realize import (
    Refusal,
    donor_room_id_by_zone,
    layout_signature,
    realize_compiled_topology,
    realize_concept,
)
from spikes.architectural_brain.retrieval import retrieve
from spikes.architectural_brain.synthesis import ConceptSpec, synthesize

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPORT_ROOT = os.path.join(REPO_ROOT, "docs", "reports", "poc-architectural-brain")
CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus")

#: Retrieval/synthesis breadth used by the DEMO specifically — wider than each module's own
#: default (k=8, max_candidates=3) because the demo's own job is to show whatever topological
#: diversity the corpus offers for a brief, not just the first 3 distinct patterns a narrower
#: scan would stop at (measured: brief-3's one TWO_WING-tagged reference only surfaces once
#: retrieval looks past its own top 8 and synthesis is allowed to keep more than 3 candidates —
#: see ``comparison.md``'s own note for the exact index). Still fully deterministic.
DEMO_K = 15
DEMO_MAX_CANDIDATES = 8


def _brief_by_id(brief_id: str) -> BenchmarkBrief:
    return next(b for b in BENCHMARK_BRIEFS if b.brief_id == brief_id)


def _out_dir(brief_id: str) -> str:
    path = os.path.join(REPORT_ROOT, brief_id)
    os.makedirs(path, exist_ok=True)
    return path


def _synthesized_concepts(brief_def: BenchmarkBrief) -> tuple[Brief, PlotSpec, list, list]:
    corpus = load_corpus_dir(CORPUS_DIR)
    brief = Brief(program=brief_def.program(), stories=1)
    plot = PlotSpec(width_m=brief_def.plot_size_m[0], depth_m=brief_def.plot_size_m[1])
    refs = retrieve(brief, plot, corpus, k=DEMO_K)
    concepts = synthesize(brief, refs, max_candidates=DEMO_MAX_CANDIDATES)
    return brief, plot, concepts, refs


def _measurements(design, validation_report) -> dict:
    """M1-M6 + wet-core + exposure + entrance/area facts, off an already-realized
    ``GeometricDesign`` -- existing signals only (Required Behavior 4), read via the SAME
    ``app.demo.contract.to_demo_design``/``quality_metrics`` path the production demo service
    already uses (no new metric computation added by this POC)."""
    demo_design = to_demo_design(design, validation_report)
    m = demo_design.quality.metrics
    entrance_room = next((r for r in design.rooms if r.zone_id == design.entrance_door.b), None)
    return {
        "gross_area_m2": round(design.gross_area_m2, 2),
        "net_area_m2": round(design.net_area_m2, 2),
        "wall_iterations": design.wall_iterations,
        "over_preferred": bool(design.over_preferred),
        "entrance_opens_into": design.entrance_door.b,
        "entrance_room_roles": list(entrance_room.roles) if entrance_room else [],
        "m1_habitable_aspect_median": m.m1_habitable_aspect_median,
        "m1_habitable_aspect_max": m.m1_habitable_aspect_max,
        "m2_habitable_on_envelope_ratio": m.m2_habitable_on_envelope_ratio,
        "m3_circulation_share": m.m3_circulation_share,
        "m4_hall_door_count": m.m4_hall_door_count,
        "m4_hall_aspect_median": m.m4_hall_aspect_median,
        "m5_wet_adjacency_ratio": m.m5_wet_adjacency_ratio,
        "m6_public_zone_contiguous": m.m6_public_zone_contiguous,
        "wasted_circulation_share": m.wasted_circulation_share,
        "wet_core_cluster_count": design.wet_core.cluster_count if design.wet_core else 0,
        "wet_core_plumbing_complexity_index": (
            design.wet_core.plumbing_complexity_index if design.wet_core else None),
    }


def cmd_current(brief_id: str) -> None:
    brief_def = _brief_by_id(brief_id)
    out = _out_dir(brief_id)
    t0 = time.time()
    result = run_general_from_site(brief_def.site_constraints(), plot_size_m=brief_def.plot_size_m,
                                   program=brief_def.program())
    dt = time.time() - t0
    payload = {"brief_id": brief_id, "elapsed_s": round(dt, 1), "outcome": result.outcome.value,
              "ok": bool(result.design is not None and result.ok), "notes": list(result.notes)}
    if result.design is not None:
        from app.vertical_slice.renderer import render
        render(result.design, os.path.join(out, "current.svg"),
              title=f"{brief_def.title} -- current engine")
        payload["circulation_class"] = (result.circulation_class.value
                                        if result.circulation_class else None)
        payload["failing_checks"] = ([c.check_id for c in result.validation.failures()]
                                     if result.validation else [])
        payload["measurements"] = _measurements(result.design, result.validation)
    with open(os.path.join(out, "current.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[{brief_id}] current: outcome={result.outcome.value} ok={payload['ok']} "
         f"in {dt:.1f}s -> {out}/current.json"
         + ("" if result.design is None else f", {out}/current.svg"))


def cmd_references(brief_id: str) -> None:
    brief_def = _brief_by_id(brief_id)
    out = _out_dir(brief_id)
    _, _, concepts, _ = _synthesized_concepts(brief_def)
    corpus = load_corpus_dir(CORPUS_DIR)
    brief = Brief(program=brief_def.program(), stories=1)
    plot = PlotSpec(width_m=brief_def.plot_size_m[0], depth_m=brief_def.plot_size_m[1])
    refs = retrieve(brief, plot, corpus, k=DEMO_K)

    lines = [f"# References -- {brief_def.title} ({brief_id})", "",
            f"Retrieved (k={DEMO_K}) from the {len(corpus)}-plan corpus, best-first:", ""]
    for r in refs:
        p = r.pattern
        lines.append(f"## {r.plan_id} -- score {r.total_score:.3f}")
        lines.append(f"WHY: {r.why}")
        lines.append("")
        lines.append(
            f"- circulation_class={p.circulation_class}, zoning={p.zoning}, "
            f"wet_core_strategy={p.wet_core_strategy}, entrance_relationship={p.entrance_relationship}")
        lines.append(
            f"- bedroom_grouping={p.bedroom_grouping}, public_composition={p.public_composition}")
        lines.append(
            f"- measured on the donor plan: circulation_ratio={p.circulation_ratio:.3f}, "
            f"corridor_length_m={p.corridor_length_m:.1f}, circulation_nodes={p.circulation_nodes}, "
            f"topology_depth={p.topology_depth}")
        lines.append("")

    lines.append(f"## Synthesized concepts (max_candidates={DEMO_MAX_CANDIDATES})")
    lines.append("")
    for c in concepts:
        lines.append(f"### {c.concept_id}: circulation_class={c.circulation_class}, "
                     f"zoning={c.zoning}, wet_core_strategy={c.wet_core_strategy}")
        for ref in c.references:
            lines.append(f"- [{ref.pattern_used}] {ref.why}")
        lines.append("")

    with open(os.path.join(out, "references.md"), "w") as f:
        f.write("\n".join(lines))
    print(f"[{brief_id}] references: {len(refs)} retrieved, {len(concepts)} synthesized "
         f"-> {out}/references.md")


def cmd_alternative(brief_id: str, index: int) -> None:
    brief_def = _brief_by_id(brief_id)
    out = _out_dir(brief_id)
    brief, plot, concepts, refs = _synthesized_concepts(brief_def)
    if index >= len(concepts):
        raise SystemExit(f"{brief_id}: only {len(concepts)} synthesized concepts, index {index} "
                         "out of range")
    concept: ConceptSpec = concepts[index]
    site = brief_def.site_constraints()

    # Issue #109 Track 3: the RealizationIntent this concept's PRIMARY donor carries -- built here
    # (not inside `realize_concept`) so a `Refusal`/`Rejection` payload can still record WHICH
    # donor plan and facts were attempted, even when nothing realized.
    primary_ref = next(r.plan_reference for r in refs if r.plan_id == concept.references[0].plan_id)
    intent = intent_from(primary_ref, concept, brief)

    adapted = adapt(concept, brief, plot)
    payload = {"brief_id": brief_id, "index": index, "concept_id": concept.concept_id,
              "declared_circulation_class": concept.circulation_class, "zoning": concept.zoning,
              "wet_core_strategy": concept.wet_core_strategy,
              "realization_intent_source_plan_id": intent.source_plan_id}
    if isinstance(adapted, Rejection):
        payload["outcome"] = "REJECTED"
        payload["reason"] = adapted.reason
        _write_alt(out, index, payload)
        print(f"[{brief_id}] alt-{index} ({concept.concept_id}): REJECTED -- {adapted.reason}")
        return

    payload["adaptations"] = [dataclasses.asdict(a) for a in adapted.adaptations]
    t0 = time.time()
    plan = realize_concept(concept, adapted, brief, site, brief_def.plot_size_m, index=index,
                           intent=intent)
    dt = time.time() - t0
    payload["elapsed_s"] = round(dt, 1)

    if isinstance(plan, Refusal):
        payload["outcome"] = "REFUSED"
        payload["reason"] = plan.reason
        _write_alt(out, index, payload)
        print(f"[{brief_id}] alt-{index} ({concept.concept_id}): REFUSED in {dt:.1f}s -- {plan.reason}")
        return

    payload["outcome"] = "REALIZED"
    payload["ok"] = plan.ok
    payload["realized_circulation_class"] = plan.circulation_class.value if plan.circulation_class else None
    payload["failing_checks"] = [c.check_id for c in plan.validation.failures()]
    payload["rationale"] = plan.concept.rationale
    payload["measurements"] = _measurements(plan.design, plan.validation)
    payload["layout_signature"] = [[zid, list(rect)] for zid, rect in layout_signature(plan.design)]

    mapping = donor_room_id_by_zone(brief, adapted)
    preservation_report = measure_preservation(intent, plan, mapping)
    payload["preservation"] = preservation_report.to_dict()

    svg_path = os.path.join(out, f"alt-{index}.svg")
    from app.vertical_slice.renderer import render
    render(plan.design, svg_path,
          title=f"{brief_def.title} -- brain {concept.concept_id} "
                f"({payload['realized_circulation_class']})")
    _write_alt(out, index, payload)
    print(f"[{brief_id}] alt-{index} ({concept.concept_id}): REALIZED ok={plan.ok} "
         f"class={payload['realized_circulation_class']} in {dt:.1f}s -> {svg_path}")


def _write_alt(out: str, index: int, payload: dict) -> None:
    with open(os.path.join(out, f"alt-{index}.json"), "w") as f:
        json.dump(payload, f, indent=2)


def cmd_compiled(brief_id: str, topology: str) -> None:
    """Issue #110: an independent probe of `concept_compilers.compile_hub_lobby`/
    `compile_branched` against this brief's own authoritative programme/site — see
    `realize.realize_compiled_topology`'s own docstring for why this exists ALONGSIDE
    `cmd_alternative`'s retrieval-driven path rather than instead of it."""
    brief_def = _brief_by_id(brief_id)
    out = _out_dir(brief_id)
    brief = Brief(program=brief_def.program(), stories=1)
    site = brief_def.site_constraints()
    concept_id = f"compiled-{topology.lower()}"
    payload = {"brief_id": brief_id, "concept_id": concept_id,
              "declared_circulation_class": topology}
    t0 = time.time()
    plan = realize_compiled_topology(brief, site, brief_def.plot_size_m, topology)
    dt = time.time() - t0
    payload["elapsed_s"] = round(dt, 1)

    if isinstance(plan, Refusal):
        payload["outcome"] = "REFUSED"
        payload["reason"] = plan.reason
        _write_compiled(out, topology, payload)
        print(f"[{brief_id}] compiled-{topology}: REFUSED in {dt:.1f}s -- {plan.reason}")
        return

    payload["outcome"] = "REALIZED"
    payload["ok"] = plan.ok
    payload["realized_circulation_class"] = plan.circulation_class.value if plan.circulation_class else None
    payload["failing_checks"] = [c.check_id for c in plan.validation.failures()]
    payload["rationale"] = plan.concept.rationale
    payload["measurements"] = _measurements(plan.design, plan.validation)

    svg_path = os.path.join(out, f"compiled-{topology.lower()}.svg")
    from app.vertical_slice.renderer import render
    render(plan.design, svg_path,
          title=f"{brief_def.title} -- compiled {topology} "
                f"({payload['realized_circulation_class']})")
    _write_compiled(out, topology, payload)
    print(f"[{brief_id}] compiled-{topology}: REALIZED ok={plan.ok} "
         f"class={payload['realized_circulation_class']} in {dt:.1f}s -> {svg_path}")


def _write_compiled(out: str, topology: str, payload: dict) -> None:
    with open(os.path.join(out, f"compiled-{topology.lower()}.json"), "w") as f:
        json.dump(payload, f, indent=2)


def cmd_comparison(brief_id: str) -> None:
    out = _out_dir(brief_id)
    alt_files = sorted(
        (fn for fn in os.listdir(out) if fn.startswith("alt-") and fn.endswith(".json")),
        key=lambda fn: int(fn[len("alt-"):-len(".json")]))
    alts = []
    for fn in alt_files:
        with open(os.path.join(out, fn)) as f:
            alts.append(json.load(f))

    # Issue #110: the independent HUB_LOBBY/BRANCHED compiler probes (`cmd_compiled`), separate
    # from `alts` (retrieval-driven) -- both feed the ATTEMPTED/REALIZED/REFUSED summary below.
    compiled_files = sorted(
        fn for fn in os.listdir(out) if fn.startswith("compiled-") and fn.endswith(".json"))
    compiled = []
    for fn in compiled_files:
        with open(os.path.join(out, fn)) as f:
            compiled.append(json.load(f))

    current_path = os.path.join(out, "current.json")
    current = None
    if os.path.exists(current_path):
        with open(current_path) as f:
            current = json.load(f)

    letters = "ABCDEFGH"
    realized_ok = [a for a in alts if a.get("outcome") == "REALIZED" and a.get("ok")]
    for letter, a in zip(letters, realized_ok):
        src = os.path.join(out, f"alt-{a['index']}.svg")
        dst = os.path.join(out, f"brain-{letter}.svg")
        if os.path.exists(src):
            with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
        a["letter"] = letter

    lines = [f"# Comparison -- {brief_id}", ""]
    lines.append("## Current engine baseline")
    if current is None:
        lines.append("(not yet run -- see `current.json`)")
    elif current.get("ok"):
        lines.append(f"REALIZED, ok=True, circulation_class={current.get('circulation_class')} "
                     f"in {current['elapsed_s']}s -> `current.svg`")
    elif current.get("outcome") == "SOLVED":
        lines.append(f"REALIZED but validation FAILED: {current.get('failing_checks')}")
    else:
        lines.append(f"REFUSED (outcome={current['outcome']}): {'; '.join(current['notes'])}")
    lines.append("")

    lines.append("## Brain alternatives")
    lines.append("")
    lines.append("| concept | declared class | outcome | realized class | ok | time (s) |")
    lines.append("|---|---|---|---|---|---|")
    for a in alts:
        letter = a.get("letter", "-")
        lines.append(
            f"| {a['concept_id']} ({letter}) | {a['declared_circulation_class']} | "
            f"{a['outcome']} | {a.get('realized_circulation_class', '-')} | "
            f"{a.get('ok', '-')} | {a.get('elapsed_s', '-')} |")
    lines.append("")

    lines.append("## Compiler probes (Issue #110): HUB_LOBBY / BRANCHED, independent of retrieval")
    lines.append("")
    lines.append("`concept_compilers.compile_hub_lobby`/`compile_branched` tried directly against "
                "this brief's own authoritative programme/site (`realize_compiled_topology`) -- "
                "never gated on whether a retrieved donor reference happened to declare that "
                "class (see `demo.py`'s own module docstring).")
    lines.append("")
    if compiled:
        lines.append("| class | outcome | realized class | ok | time (s) |")
        lines.append("|---|---|---|---|---|")
        for c in compiled:
            lines.append(
                f"| {c['declared_circulation_class']} | {c['outcome']} | "
                f"{c.get('realized_circulation_class', '-')} | {c.get('ok', '-')} | "
                f"{c.get('elapsed_s', '-')} |")
    else:
        lines.append("(not yet run -- see `compiled-*.json`)")
    lines.append("")

    lines.append("## What adaptation changed")
    lines.append("")
    for a in alts:
        if not a.get("adaptations"):
            continue
        lines.append(f"### {a['concept_id']}")
        for adpt in a["adaptations"]:
            lines.append(f"- **{adpt['kind']}**: {adpt['before']} -> {adpt['after']} "
                         f"({adpt['reason']})")
        lines.append("")

    lines.append("## Refusal / rejection reasons")
    lines.append("")
    for a in alts:
        if a["outcome"] in ("REJECTED", "REFUSED"):
            lines.append(f"- {a['concept_id']}: {a['outcome']} -- {a['reason']}")
    for c in compiled:
        if c["outcome"] == "REFUSED":
            lines.append(f"- {c['concept_id']}: {c['outcome']} -- {c['reason']}")
    lines.append("")

    # AC-1/AC-3 (Issue #110): per brief, which circulation classes were ATTEMPTED, REALIZED, or
    # REFUSED-with-reason -- SPINE/TWO_WING read off `alts`' own REALIZED class (retrieval-driven;
    # no synthesized concept ever DECLARES "SPINE" itself -- it is the default fallback topology,
    # see `realize.py`'s own `_TOPOLOGY_FOR_CLASS`), HUB_LOBBY/BRANCHED off `compiled` (always
    # attempted, declared class == the probed one).
    lines.append("## ATTEMPTED / REALIZED / REFUSED by circulation class (Issue #110)")
    lines.append("")
    lines.append("| circulation class | attempted | realized (ok, concept) | refused (reason) |")
    lines.append("|---|---|---|---|")
    for cls in ("SPINE", "TWO_WING", "HUB_LOBBY", "BRANCHED"):
        realized_alts = [a for a in alts
                         if a.get("realized_circulation_class") == cls and a.get("ok")]
        realized_compiled = [c for c in compiled
                             if c.get("realized_circulation_class") == cls and c.get("ok")]
        refused_compiled = [c for c in compiled
                            if c.get("declared_circulation_class") == cls and c["outcome"] == "REFUSED"]
        if cls == "SPINE":
            # SPINE is `realize.py`'s own DEFAULT/fallback topology (`_TOPOLOGY_FOR_CLASS.get(
            # concept.circulation_class, "SPINE")`) -- every alternative whose declared class is
            # NOT TWO_WING/HUB_LOBBY/BRANCHED routes through it, whether or not the result ever
            # reports "SPINE" as its OWN realized class (see the note below).
            declared_alts = [a for a in alts
                             if a.get("declared_circulation_class") not in ("TWO_WING", "HUB_LOBBY", "BRANCHED")]
        else:
            declared_alts = [a for a in alts if a.get("declared_circulation_class") == cls]
        attempted = bool(realized_alts or realized_compiled or refused_compiled or declared_alts)
        realized = realized_alts + realized_compiled
        realized_str = ", ".join(r["concept_id"] for r in realized) if realized else "-"
        refused_str = ("; ".join(f"{c['concept_id']}: {c['reason']}" for c in refused_compiled)
                      if refused_compiled else "-")
        lines.append(f"| {cls} | {'yes' if attempted else 'no'} | {realized_str} | {refused_str} |")
        # `_compile_spine`/`_compile_spine_double_loaded` ALWAYS split the hall into two
        # DIRECTLY-CONNECTED segments for private-room routing (see `_hall_and_private_splits`) --
        # which `concept_spec.realized_circulation_class` (extended by Issue #79, already merged
        # into this POC branch) classifies as BRANCHED, not SPINE, regardless of which compiler
        # built it. Measured directly on this branch: every SPINE-routed alternative across all 3
        # fixed briefs realizes as BRANCHED, never as SPINE -- a real, measured side effect of the
        # #79 merge this Issue starts from (`concept_spec.py` is out of scope to change here), not
        # a wiring bug or a forced topology.
        if cls == "SPINE" and declared_alts and not realized:
            lines.append(
                "  - Note: SPINE was attempted (a synthesized concept routed to it) but never "
                "REALIZED as SPINE -- its own two-hall-segment split always satisfies the merged "
                "BRANCHED classifier instead (see the BRANCHED row/note below).")
        # BRANCHED can legitimately show BOTH a realized concept AND a refused compiler probe on
        # the SAME brief: `concept_spec.realized_circulation_class` (extended by Issue #79,
        # already merged into this POC branch) classifies ANY two directly-connected HALL/
        # CIRCULATION zones as BRANCHED -- including `realize.py`'s OWN `_compile_spine`/
        # `_compile_spine_double_loaded` output (both always split the hall into two connected
        # segments for private-room routing, unrelated to Concept Engine v2's hand-authored
        # cased-opening tree). The realized-BRANCHED rows above therefore did NOT come from the
        # newly-imported `concept_compilers.compile_branched` (confirmed refused, same table row)
        # -- a real, measured side effect of the merge this Issue starts from, not a wiring bug.
        if cls == "BRANCHED" and realized and refused_compiled:
            lines.append(
                "  - Note: `realized_circulation_class` labels ANY two directly-connected "
                "HALL/CIRCULATION zones BRANCHED (Issue #79's own classifier extension) -- the "
                "realized concept(s) above came from `realize.py`'s own SPINE compiler (its "
                "hall-segment split happens to match that same geometric signature), NOT from "
                "the imported `concept_compilers.compile_branched`, which is REFUSED on this "
                "brief (see the reason column and the compiler-probes table above).")
    lines.append("")

    # AC-2: "the demo lists each realized plan's validation result" -- REALIZED-but-not-ok plans
    # carry a real validation report same as any other realized candidate (Required Behavior 1's
    # own docstring), so their own failing check ids are listed here just as plainly as a
    # REFUSED/REJECTED reason is above -- never a silently-dropped `ok: false`.
    failing = [a for a in alts + compiled if a.get("outcome") == "REALIZED" and not a.get("ok")
              and a.get("failing_checks")]
    if failing:
        lines.append("## Realized-but-failing-validation plans")
        lines.append("")
        for a in failing:
            lines.append(f"- {a['concept_id']}: REALIZED, ok=False -- failing checks: "
                         f"{', '.join(a['failing_checks'])}")
        lines.append("")

    # Issue #109 Track 3 AC-4: the PRESERVED/LOST block per realized alternative that carries a
    # `preservation` fact (every REALIZED plan produced by this Issue's own `cmd_alternative`;
    # older sidecars written before this Issue simply have no `preservation` key and are skipped
    # here, never crashing this command).
    lines.append("## RealizationIntent preservation (Issue #109 Track 3)")
    lines.append("")
    any_preservation = False
    for a in alts:
        if a.get("outcome") != "REALIZED" or "preservation" not in a:
            continue
        any_preservation = True
        report = PreservationReport.from_dict(a["preservation"])
        lines.append(report.to_markdown())
    if not any_preservation:
        lines.append("(no realized alternative carries a RealizationIntent preservation report)")
        lines.append("")

    # AC-4's own second requirement: when two plans of this brief realize to the SAME geometry,
    # name the constraint that caused the collapse -- grouped by `layout_signature` (a
    # JSON-serializable [[zone_id, [x, y, w, h]], ...] list; converted to a hashable tuple here).
    signature_groups: dict[tuple, list[str]] = {}
    for a in alts:
        if a.get("outcome") != "REALIZED" or "layout_signature" not in a:
            continue
        sig = tuple((zid, tuple(rect)) for zid, rect in a["layout_signature"])
        signature_groups.setdefault(sig, []).append(a["concept_id"])
    collapsed = [names for names in signature_groups.values() if len(names) > 1]
    if collapsed:
        lines.append("## Layout collapse (identical realized geometry from different donors)")
        lines.append("")
        for names in collapsed:
            lines.append(
                f"- {', '.join(names)} realized to BYTE-IDENTICAL geometry. Root cause (measured, "
                "see `tests/architectural_brain/test_realization_intent.py::"
                "test_two_donors_for_one_brief_realize_to_different_layouts`, xfail-documented): "
                "`realize.py`'s own compiler selects each private column's WIDTH from "
                "`ROOM_TEMPLATES`' [min, max] area bound only -- identical for both donors, since "
                "it comes from the brief's own authoritative room counts (the owner's explicit "
                "requirement), never from the donor plan. Only within THAT already-fixed width "
                "does `RealizationIntent.room_proportions`' donor-specific TARGET area get a say "
                "(`geometry_core.engine.assign`'s closest-to-target picker) -- here both donors' "
                "own proportional targets fall below the width-driven minimum feasible height, so "
                "both saturate at the same minimum regardless of their different donors.")
        lines.append("")

    lines.append("## Measurements table (realized-and-ok plans, plus the current baseline)")
    lines.append("")
    rows = []
    if current is not None and current.get("ok"):
        rows.append(("current", current.get("circulation_class"), current["measurements"]))
    for a in realized_ok:
        rows.append((f"brain-{a['letter']} ({a['concept_id']})", a["realized_circulation_class"],
                    a["measurements"]))
    for c in compiled:
        if c.get("outcome") == "REALIZED" and c.get("ok"):
            rows.append((c["concept_id"], c["realized_circulation_class"], c["measurements"]))
    if rows:
        keys = ["gross_area_m2", "net_area_m2", "m3_circulation_share", "m4_hall_door_count",
               "m4_hall_aspect_median", "m5_wet_adjacency_ratio", "m6_public_zone_contiguous",
               "wet_core_cluster_count", "entrance_opens_into"]
        lines.append("| plan | class | " + " | ".join(keys) + " |")
        lines.append("|" + "---|" * (len(keys) + 2))
        for name, cls, meas in rows:
            lines.append(f"| {name} | {cls} | " + " | ".join(str(meas.get(k)) for k in keys) + " |")
    else:
        lines.append("(no realized-and-ok plan to tabulate yet)")
    lines.append("")

    with open(os.path.join(out, "comparison.md"), "w") as f:
        f.write("\n".join(lines))
    print(f"[{brief_id}] comparison: {len(realized_ok)}/{len(alts)} alternatives realized-and-ok "
         f"-> {out}/comparison.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("current", "references", "comparison"):
        p = sub.add_parser(name)
        p.add_argument("--brief", required=True, choices=[b.brief_id for b in BENCHMARK_BRIEFS]
                       + ["1", "2", "3"])
    p = sub.add_parser("alternative")
    p.add_argument("--brief", required=True)
    p.add_argument("--index", required=True, type=int)
    p = sub.add_parser("compiled")
    p.add_argument("--brief", required=True)
    p.add_argument("--class", dest="topology", required=True, choices=["HUB_LOBBY", "BRANCHED"])

    args = parser.parse_args()
    brief_id = args.brief if args.brief.startswith("brief-") else f"brief-{args.brief}"

    if args.cmd == "current":
        cmd_current(brief_id)
    elif args.cmd == "references":
        cmd_references(brief_id)
    elif args.cmd == "alternative":
        cmd_alternative(brief_id, args.index)
    elif args.cmd == "compiled":
        cmd_compiled(brief_id, args.topology)
    elif args.cmd == "comparison":
        cmd_comparison(brief_id)


if __name__ == "__main__":
    main()
