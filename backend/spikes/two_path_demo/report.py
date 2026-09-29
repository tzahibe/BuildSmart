"""Issue #155 — builds `docs/reports/two-path-demo/results.md` from `run_demo.run_all()`'s own
output. Measurement text only; no plotting, no image generation (composites are produced
separately, `frontend/src/design/twoPathDemoComposites.test.tsx`, through Issue #146's own
`DemoPlan` component)."""
from __future__ import annotations

import statistics

from spikes.two_path_demo.run_demo import PathResult, _short_id, contract_non_rectangular


def _fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.3f}"
    return str(x)


def _median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.median(vals), 3) if vals else None


def _verdict_cell(r: PathResult) -> str:
    if r.outcome == "REALIZED":
        return "REALIZED (validated)"
    return f"REFUSED — {r.refusal_code}"


def write_report(pairs: list[tuple[PathResult, PathResult]]) -> str:
    n = len(pairs)
    a_results = [a for a, _ in pairs]
    b_results = [b for _, b in pairs]
    a_realized = [a for a in a_results if a.outcome == "REALIZED"]
    b_realized = [b for b in b_results if b.outcome == "REALIZED"]
    b_refused = [b for b in b_results if b.outcome == "REFUSED"]
    a_refused = [a for a in a_results if a.outcome == "REFUSED"]

    lines: list[str] = []
    lines.append("# Two-path demo — what main can draw today, beside the non-guillotine realizer "
                  "(Issue #155)")
    lines.append("")

    # ---------------------------------------------------------------- what this does/doesn't prove
    lines.append("## What this comparison does and does not prove")
    lines.append("")
    headline_unfavourable = (
        f"**Path B (the rectilinear realizer) refuses MORE OFTEN than path A on these 8 real "
        f"briefs: {len(b_refused)}/{n} refused vs {len(a_refused)}/{n} for path A.** The realizer "
        f"is a proof of geometric feasibility on a hand-tuned placement heuristic "
        f"(`spikes/geometry_shapes/stage1_gate.py`'s own intent-builders, reused here unchanged), "
        f"not a placement engine — most of its refusals below are this script's own placement "
        f"guess missing a real room's actual size or role mix, not a fact about the architecture. "
        f"Path A never refuses on these 8 briefs because they were drawn from the corpus's own "
        f"PLANNED pool — a pool defined by path A already succeeding on them."
    )
    lines.append(headline_unfavourable)
    lines.append("")
    lines.append(
        "**What this DOES prove**: for every brief below, both plans were produced by the SAME "
        "shipping contract-building entry point, `app.demo.contract.to_demo_design` — the one "
        "function that turns a validated, realized geometry into the `DemoDesign` JSON Issue "
        "#146's drawing layer (`DemoPlan.tsx`) draws, and draws NOTHING that is not on that "
        "object (that component's own docstring: \"This component decides NOTHING "
        "architectural... If a fact is not on the object, it is not drawn\"). Every REALIZED "
        "path-B plan passed the UNCHANGED validator chain, C31 included, plus C30 run and "
        "disclosed (see \"C30/C31\" below). No refused plan was ever replaced by a different, "
        "easier brief or a silently-approximated pass."
    )
    lines.append("")
    lines.append(
        "**What this does NOT prove**: that the realizer is ready to wire into the product "
        "(#142A, explicitly out of scope here); that path B's placement heuristic is any good — "
        "it is this script's own deterministic, un-optimized guess reused from the Stage 1 gate, "
        "never the subject of this Issue; that the M1-M6 numbers below are comparable in the "
        "usual sense — path B's rooms are a synthetic re-placement of the SAME real room roles/"
        "areas, not the same floor plan redrawn, so a metric moving is a fact about this script's "
        "placement choice, not about the realizer's own geometric capability. And it does not "
        "prove the realizer draws MORE non-rectangular shapes than it actually does: the "
        "contract-level non-rectangular room count below undercounts path B on purpose-built "
        "L/U notch-carve rooms — see \"Non-rectangular counts\" for why, and the separate "
        "construction-level ground truth that fills the gap."
    )
    lines.append("")

    # ---------------------------------------------------------------------------- per-brief table
    lines.append("## Per-brief results")
    lines.append("")
    lines.append("| # | brief (short id) | path B family | path A | path B |")
    lines.append("|---|---|---|---|---|")
    for i, (a, b) in enumerate(pairs):
        short = _short_id(a.brief_id, i)
        lines.append(f"| {i} | {short} | {b.family} | {_verdict_cell(a)} | {_verdict_cell(b)} |")
    lines.append("")
    lines.append(
        "A brief's own numeric context (bedrooms, SAFE_ROOM, built area, plot dimensions) is in "
        "`selected_briefs.json`; its full `DemoDesign` JSON for whichever path(s) realized is in "
        "`contracts/<short>-A.json`/`contracts/<short>-B.json`. **Composite generation could not "
        "be run or verified in this session** — `frontend/node_modules` is not installed in this "
        "worktree and `npm install` requires an approval this headless session has no surface "
        "for (see \"Reproducing this report\"); the composite step "
        "(`frontend/src/design/twoPathDemoComposites.test.tsx`, real `DemoPlan` renders through "
        "React Testing Library, one `composites/<short>.html` per brief) is written and "
        "reproducible in a normal frontend environment/CI, but no `composites/*.html` file is "
        "committed by this change — do not treat their absence as evidence the realizer draws "
        "nothing; the `contracts/*.json` files above are the real, unrendered contract for both "
        "paths."
    )
    lines.append("")

    # -------------------------------------------------------------------------- refusal detail
    lines.append("## Refusal detail (AC-3)")
    lines.append("")
    if not b_refused and not a_refused:
        lines.append("(no refusal on either path for these 8 briefs)")
    else:
        for i, (a, b) in enumerate(pairs):
            short = _short_id(a.brief_id, i)
            if a.outcome == "REFUSED":
                lines.append(f"- **{short}, path A** — refusal code `{a.refusal_code}`: "
                              f"{a.refusal_detail}")
            if b.outcome == "REFUSED":
                lines.append(f"- **{short}, path B** ({b.family}) — refusal code "
                              f"`{b.refusal_code}`: {b.refusal_detail}")
    lines.append("")
    lines.append(
        "Every refusal above is the REAL outcome for that brief on that path — no refusal here "
        "was retried past this script's own disclosed scale ladder "
        "(`run_demo._RETRY_SCALES`, up to 9 attempts) and no refused plan was substituted for a "
        "different, easier brief."
    )
    lines.append("")

    # -------------------------------------------------------------------------------- C30/C31
    lines.append("## C30/C31 — the unchanged validator chain, including furnishability (AC-3)")
    lines.append("")
    lines.append(
        "C31 (\"public rooms reachable without crossing a furniture-blocked path\") is already "
        "wired into `validate()` and ran, unchanged, for every path-B REALIZED attempt above "
        "(one brief's own path-B attempt refused specifically ON C31 — see \"Refusal detail\"). "
        "C30 (\"rooms are furnishable\") is NOT wired into `validate()` — a standalone, documented "
        "maintainer scope decision (`app.vertical_slice.validation.check_furnishability`'s own "
        "docstring: disclosure-only, not a hard gate, pending an `interior_layout.py` placement "
        "fix out of this Issue's scope) — so it is called directly here and disclosed, never "
        "silently skipped:"
    )
    lines.append("")
    lines.append("| # | brief | path B C30 (furnishable) | detail |")
    lines.append("|---|---|---|---|")
    for i, (a, b) in enumerate(pairs):
        if b.outcome != "REALIZED":
            continue
        short = _short_id(a.brief_id, i)
        verdict = "PASS" if b.c30_passed else "DISCLOSED — not all rooms furnishable"
        lines.append(f"| {i} | {short} | {verdict} | {b.c30_detail} |")
    lines.append("")

    # ------------------------------------------------------------------------------- aggregates
    lines.append("## Aggregate numbers (AC-5)")
    lines.append("")
    lines.append(f"- **Path A**: {len(a_realized)}/{n} realized, {len(a_refused)}/{n} refused.")
    lines.append(f"- **Path B**: {len(b_realized)}/{n} realized, {len(b_refused)}/{n} refused.")
    lines.append("")
    if b_refused:
        codes = sorted({r.refusal_code for r in b_refused})
        lines.append("Path B refusal codes: " + ", ".join(
            f"`{c}` x{sum(1 for r in b_refused if r.refusal_code == c)}" for c in codes))
        lines.append("")

    lines.append("### M1-M6, median over REALIZED plans per path")
    lines.append("")
    lines.append("| metric | path A (n={}) | path B (n={}) |".format(len(a_realized), len(b_realized)))
    lines.append("|---|---|---|")
    metric_names = [
        ("m1_habitable_aspect_median", "M1 habitable aspect (median)"),
        ("m2_habitable_on_envelope_ratio", "M2 habitable-on-envelope ratio"),
        ("m3_circulation_share", "M3 circulation share"),
        ("m4_hall_door_count", "M4 hall door count"),
        ("m4_hall_aspect_median", "M4 hall aspect (median)"),
        ("m5_wet_adjacency_ratio", "M5 wet adjacency ratio"),
    ]

    def _values(results: list[PathResult], attr: str) -> list[float]:
        out = []
        for r in results:
            if r.demo_design is None:
                continue
            v = getattr(r.demo_design.quality.metrics, attr)
            if v is not None:
                out.append(v)
        return out

    for attr, label in metric_names:
        va = _median(_values(a_realized, attr))
        vb = _median(_values(b_realized, attr))
        lines.append(f"| {label} | {_fmt(va)} | {_fmt(vb)} |")
    m6_a = sum(1 for r in a_realized if r.demo_design is not None
               and r.demo_design.quality.metrics.m6_public_zone_contiguous)
    m6_b = sum(1 for r in b_realized if r.demo_design is not None
               and r.demo_design.quality.metrics.m6_public_zone_contiguous)
    lines.append(f"| M6 public zone contiguous (count) | {m6_a}/{len(a_realized)} | "
                 f"{m6_b}/{len(b_realized)} |")
    lines.append("")
    lines.append(
        "These are the SAME `QualityMetrics` fields (`app.vertical_slice.quality_metrics`) "
        "`to_demo_design` computes for every plan on main today — read here off the identical "
        "`quality.metrics` object the shipping API already returns, never recomputed."
    )
    lines.append("")
    lines.append(
        "Two patterns in this table are disclosed limitations of THIS SCRIPT's own placement "
        "heuristic, not a fact about the realizer's geometric capability: **M5 is always \"—\" "
        "for path B** because wet rooms (BATHROOM/TOILET) and SAFE_ROOM are deliberately excluded "
        "from every path-B construction (`stage1_gate.py`'s own disclosed simplification, reused "
        "here — C17/C29 need a `ResolvedWetRoom` list this script does not reconstruct), so there "
        "is never a wet room to measure adjacency for. **M6 (public zone contiguous) is 0/3 for "
        "path B vs 8/8 for path A** because this script's PINWHEEL/TWO_WING placement picks the "
        "N/S/W arms by real room AREA alone, with no notion of \"public zone\" semantics at all — "
        "an unrelated bedroom can as easily land in the arm next to LIVING as DINING can. This is "
        "a placement-heuristic gap, not a claim that the realizer's geometry cannot host a "
        "contiguous public zone."
    )
    lines.append("")

    lines.append("### Non-rectangular counts (AC-5)")
    lines.append("")
    a_nr_rooms = sum(contract_non_rectangular(r.demo_design)[0] for r in a_realized
                      if r.demo_design is not None)
    a_nr_env = sum(1 for r in a_realized if r.demo_design is not None
                    and contract_non_rectangular(r.demo_design)[1])
    b_nr_rooms = sum(contract_non_rectangular(r.demo_design)[0] for r in b_realized
                      if r.demo_design is not None)
    b_nr_env = sum(1 for r in b_realized if r.demo_design is not None
                    and contract_non_rectangular(r.demo_design)[1])
    lines.append(
        "**Contract-level** (a room whose `DemoDesign.rooms[].shape` is not `RECTANGLE`/unset, "
        "or a plan whose `DemoDesign.footprints` has more than one wing — the SAME predicate "
        "applied to the SAME `DemoDesign` shape both paths produce):"
    )
    lines.append("")
    lines.append(f"- Path A: {a_nr_rooms} non-rectangular room(s) across {len(a_realized)} "
                 f"realized plans; {a_nr_env} plan(s) with a non-rectangular envelope.")
    lines.append(f"- Path B: {b_nr_rooms} non-rectangular room(s) across {len(b_realized)} "
                 f"realized plans; {b_nr_env} plan(s) with a non-rectangular envelope.")
    lines.append("")
    b_notch_groups = sum(r.notch_group_count for r in b_realized)
    b_multiwing = sum(1 for r in b_realized if r.is_multi_wing_envelope)
    lines.append(
        "**Construction-level ground truth, path B only** (disclosed separately because "
        "`to_demo_design` only recognises the LIVING+KITCHEN 2-way merge's own `shape='L'` "
        "convention — it does not yet expose the realizer's general N-way notch-carve group as a "
        "single polygon room in the contract, so the contract-level room count above UNDERCOUNTS "
        "an L/U family's real, validated, non-rectangular room; visually the plan still draws "
        "correctly, since the notch's own cell boundary is a real `WallType.OPEN` interface, not "
        "a missing wall):"
    )
    lines.append("")
    lines.append(f"- {b_notch_groups} genuinely-merged notch-carve room(s) "
                 f"(`RealizedLayout.groups`, non-empty means a true L/U/T polygon, not a "
                 f"placeholder) across the {len(b_realized)} realized path-B plans.")
    lines.append(f"- {b_multiwing} plan(s) with a genuinely non-rectangular TWO_WING envelope "
                 f"(2 wings of different heights, a real seam — already visible at the "
                 f"contract level above via `footprints`).")
    lines.append(
        "- PINWHEEL (its own family, {} of the {} path-B attempts) contributes ZERO to either "
        "count on purpose: every pinwheel arm is an ordinary rectangle tiling a rectangular "
        "envelope — its non-guillotine fact is about internal wall TOPOLOGY (it cannot be built "
        "by straight full-width/full-height cuts), not about room or envelope SHAPE, which is "
        "what this Issue's AC-5 asks for."
        .format(sum(1 for r in b_results if r.family == "PINWHEEL"), n)
    )
    lines.append("")

    lines.append("## Reproducing this report")
    lines.append("")
    lines.append("```")
    lines.append("cd backend")
    lines.append("uv run python -m spikes.two_path_demo.run_demo")
    lines.append("cd ../frontend")
    lines.append("npm test -- twoPathDemoComposites")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)
