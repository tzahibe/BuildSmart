"""The exact sizer as the brain's realization step (#197 item 4, 2026-10-15).

`run_brain(..., sizer="exact")` sends every parti through this instead of `run_band_pipeline`'s
production sizer: the same embedding and the same production SELECTION screen, then the exact
MILP placement (`milp_placement`, target objective — every room pulled to its own target, the
hall not the sink), then `realize_cells` and the UNCHANGED validators, then the brain's own
preference over what passed. `families` adds the cross-band layouts measured on the frozen six
(#197/#200): the spine (a hub corridor across bands), the stack (two rooms in one column), the
cells (a hub or public room two rows deep). One wall-clock `deadline` bounds the whole request;
what did not run is said in `warnings`, never silently skipped.

Falls back, typed: without `scipy` (`ImportError`) or when a solve returns UNKNOWN for every
candidate, the caller runs the production sizer and says so.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.vertical_slice.band_embedding import BandEmbeddingRefusal, embed_band
from app.vertical_slice.band_pipeline import (
    PipelineDiagnosis,
    PipelineInput,
    PipelineSuccess,
    hard_rejections,
    orient,
    placement_flags,
)
from app.vertical_slice.band_sizing import contact_requirements
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.exact.screens import (
    cells_selection,
    spine_selection,
    transpose_rects,
    transposed_envelope,
)
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
from app.vertical_slice.topology_preservation import (
    measure_access_graph,
    measure_spatial_adjacency,
)

ALL_FAMILIES = ("band", "spine", "stack", "cells")
#: candidates actually sized per parti per family; a product request sizes a handful, never hundreds
MAX_SIZINGS = 6
MAX_CANDIDATES = 60
CELLS_K = 6


@dataclass
class ExactPlacement:
    """What `PipelineSuccess.placement` carries for an exact plan: the family and its layout."""
    family: str
    bands: tuple = ()
    rows: tuple = ()
    label: str = ""


@dataclass
class _Best:
    key: tuple
    realized: RealizedLayout
    placement: ExactPlacement
    spatial: object
    access: object
    tried: int = 0
    warnings: list = field(default_factory=list)


def _ladder(zones, rebanded, ladder):
    for rung in ladder:
        yield rung, (rebanded(zones, rung) if rung != ladder[0] else zones)


def run_exact_pipeline(inp: PipelineInput, *, prefer, ladder, rebanded, families=("band",),
                       deadline: float | None = None, max_sizings: int = MAX_SIZINGS,
                       objective: str = "target") -> PipelineSuccess | PipelineDiagnosis:
    """`prefer(realized, placement, inp) -> key` (lower is better) decides between everything that
    passes; `ladder`/`rebanded` are the brain's widening ladder; `deadline` is a `time.monotonic()`
    instant after which nothing new is sized."""
    try:
        from app.vertical_slice.exact.milp_cells import (
            cells_placement,
            cells_rects,
            cells_wings,
        )
        from app.vertical_slice.exact.milp_oracle import (
            milp_placement,
            milp_spine_placement,
            placement_rects,
            spine_geometry,
            spine_intents,
        )
    except ImportError as exc:                                   # scipy absent: the caller falls back
        return PipelineDiagnosis("EXACT_SIZER_UNAVAILABLE", "SIZING", f"scipy is not installed ({exc})")
    t0 = time.monotonic()
    deadline = deadline if deadline is not None else t0 + 30.0
    zones = dict(inp.zones)
    access = [tuple(e) for e in inp.access_edges]
    union = sorted({tuple(sorted(e)) for e in inp.required_edges} | {tuple(sorted(e)) for e in access})
    contacts = contact_requirements(zones, union, access)
    env = Envelope.rectangle(*inp.footprint_m)
    orientations = (("H", env), ("V", transposed_envelope(env)))
    best: _Best | None = None
    tried = 0
    unknown = 0
    warnings: list[str] = []
    histogram: dict = {}

    def note(stage, reason):
        d = histogram.setdefault(stage, {})
        d[reason] = d.get(reason, 0) + 1

    def consider(realized, placement):
        nonlocal best
        sp = measure_spatial_adjacency(realized.rects, frozenset(frozenset(e) for e in inp.required_edges))
        ac = measure_access_graph(realized.fixture.access.edges, access)
        if sp.preserved != sp.requested or ac.preserved != ac.requested:
            note("PRESERVATION", "lost"); return
        key = prefer(realized, placement, inp)
        if best is None or key < best.key:
            best = _Best(key, realized, placement, sp, ac)

    def out_of_time():
        return time.monotonic() > deadline

    def realize(name, rects, intents, wings, orient_tag, placement):
        nonlocal tried, unknown
        if orient_tag == "V":
            rects = transpose_rects(rects)
            wings = tuple(transpose_rects(dict(enumerate(wings))).values())
        out = realize_cells(name, rects, intents, wings, access, wet_rooms=inp.wet_rooms)
        tried += 1
        if not isinstance(out, RealizedLayout):
            note("REALIZATION", out.constraint); return False
        consider(out, placement); return True

    # ---- the band family: production's embedding and screen, the exact placement
    emb = embed_band(zones, union, max_candidates=MAX_CANDIDATES)
    if isinstance(emb, BandEmbeddingRefusal):
        return PipelineDiagnosis(emb.code, "EMBEDDING", emb.detail, seconds=round(time.monotonic() - t0, 3))
    screened = []
    for cand in emb.candidates:
        flags = placement_flags(cand, zones, inp.wet_rooms, tuple(access))
        rejected = hard_rejections(flags)
        if rejected:
            for k in rejected:
                note("SELECTION", k)
            continue
        screened.append(orient(cand, flags)[0])
    if "band" in families:
        sized = 0
        for cand in screened:
            if sized >= max_sizings or out_of_time():
                break
            for orient_tag, env_o in orientations:
                for rung, zr in _ladder(zones, rebanded, ladder):
                    if out_of_time():
                        break
                    o = milp_placement(cand.bands, zr, union, env_o, min_contact_u=contacts, objective=objective)
                    note("SIZING", f"band:{o.status}")
                    if o.status == "UNKNOWN":
                        unknown += 1
                    if o.status != "FEASIBLE":
                        if o.status == "BAND_GAP":
                            break
                        continue
                    sized += 1
                    sz = o.as_sizing()
                    realize(f"{inp.name}:band", sz.rects(cand.bands), zr, sz.band_rects(cand.bands), orient_tag,
                            ExactPlacement("band", bands=tuple(cand.bands), label=f"{orient_tag} rung {rung}"))
                    break

    # ---- the spine family
    if "spine" in families and not out_of_time():
        from app.vertical_slice.exact.spine import choose_spine, embed_spine
        spine = choose_spine(zones, union)
        if spine is not None:
            sized = 0
            for layout in embed_spine(zones, union, spine, max_candidates=24):
                if sized >= max_sizings or out_of_time():
                    break
                for orient_tag, env_o in orientations:
                    if spine_selection(layout, zones, orient_tag):
                        note("SELECTION", "spine"); continue
                    for rung, zr in _ladder(zones, rebanded, ladder):
                        if out_of_time():
                            break
                        o = milp_spine_placement(layout, zr, union, env_o, min_contact_u=contacts, objective=objective)
                        note("SIZING", f"spine:{o.status}")
                        if o.status != "FEASIBLE":
                            if o.status == "BAND_GAP":
                                break
                            continue
                        sized += 1
                        rects, wings = spine_geometry(layout, o)
                        realize(f"{inp.name}:spine", rects, spine_intents(layout, zr), wings, orient_tag,
                                ExactPlacement("spine", rows=tuple(layout.bands), label=f"{orient_tag} rung {rung}"))
                        break

    # ---- the stack family
    if "stack" in families and not out_of_time():
        from app.vertical_slice.exact.stacks import (
            _tier,
            expand_wings,
            merge_stack,
            propose_stacks,
        )
        options, seen_tiers = [], {}
        for a, b in propose_stacks(zones, union):
            t = _tier(zones[a].role)
            if seen_tiers.setdefault(t, frozenset((a, b))) != frozenset((a, b)):
                continue
            options.append((a, b))
        spatial = [tuple(e) for e in inp.required_edges]
        sized = 0
        for stack in options[:4]:
            if sized >= max_sizings or out_of_time():
                break
            z2, e2, a2, pid = merge_stack(zones, spatial, access, stack)
            union2 = sorted({tuple(sorted(e)) for e in e2} | {tuple(sorted(e)) for e in a2})
            emb2 = embed_band(z2, union2, max_candidates=MAX_CANDIDATES)
            if isinstance(emb2, BandEmbeddingRefusal):
                continue
            for cand in emb2.candidates:
                if sized >= max_sizings or out_of_time():
                    break
                flags = placement_flags(cand, z2, inp.wet_rooms, tuple(a2))
                if hard_rejections(flags):
                    continue
                oriented = orient(cand, flags)[0]
                for orient_tag, env_o in orientations:
                    for rung, zr in _ladder(zones, rebanded, ladder):
                        if out_of_time():
                            break
                        z2r = {z: zr.get(z, zi) for z, zi in z2.items()}
                        stacks = {pid: tuple(zr[m] for m in stack)}
                        o = milp_placement(oriented.bands, z2r, union, env_o, min_contact_u=contacts,
                                           objective=objective, stacks=stacks)
                        note("SIZING", f"stack:{o.status}")
                        if o.status != "FEASIBLE":
                            if o.status == "BAND_GAP":
                                break
                            continue
                        sized += 1
                        sz = o.as_sizing()
                        rects, intents = placement_rects(oriented.bands, z2r, o, stacks)
                        wings = expand_wings(sz.band_rects(oriented.bands), sz.rects(oriented.bands),
                                             {pid: tuple(m.zone_id for m in stacks[pid])})
                        realize(f"{inp.name}:stack", rects, intents, wings, orient_tag,
                                ExactPlacement("stack", bands=tuple(oriented.bands), label=f"{stack} {orient_tag}"))
                        break

    # ---- the cells family
    if "cells" in families and not out_of_time():
        from app.vertical_slice.exact.cells import (
            CIRC,
            PUBLIC,
            duplicated_layouts,
            from_bands,
            moves,
        )
        layouts, seen = [], set()
        for cand in screened[:12]:
            for lay in moves(from_bands(cand.bands), zones, union):
                if lay.spanning and lay.rows not in seen:
                    seen.add(lay.rows); layouts.append(lay)
        for z in [z for z in zones if zones[z].role in CIRC] + [z for z in zones if zones[z].role in PUBLIC]:
            if out_of_time():
                break
            for lay in duplicated_layouts(zones, union, z, max_candidates=16, max_partitions=6):
                if lay.rows not in seen:
                    seen.add(lay.rows); layouts.append(lay)
        sized = 0
        for lay in layouts:
            if sized >= max_sizings or out_of_time():
                break
            for orient_tag, env_o in orientations:
                if cells_selection(lay, zones, orient_tag):
                    note("SELECTION", "cells"); continue
                for rung, zr in _ladder(zones, rebanded, ladder):
                    if out_of_time():
                        break
                    o = cells_placement(lay, zr, union, env_o, min_contact_u=contacts, k=CELLS_K, objective=objective)
                    note("SIZING", f"cells:{o.status}")
                    if o.status != "FEASIBLE":
                        if o.status == "BAND_GAP":
                            break
                        continue
                    sized += 1
                    realize(f"{inp.name}:cells", cells_rects(lay, o), zr, cells_wings(lay, o), orient_tag,
                            ExactPlacement("cells", rows=tuple(lay.rows), label=f"{lay.spanning} {orient_tag}"))
                    break

    secs = round(time.monotonic() - t0, 3)
    if out_of_time():
        warnings.append(f"request budget reached after {secs} s; later candidates and families were not sized")
    if best is None:
        if tried == 0 and unknown and unknown == sum(histogram.get("SIZING", {}).values()):
            return PipelineDiagnosis("EXACT_SIZER_UNKNOWN", "SIZING", "every exact solve hit its time limit",
                                     candidates_tried=0, stage_histogram=histogram, warnings=tuple(warnings), seconds=secs)
        return PipelineDiagnosis("NO_EXACT_PLAN", "REALIZATION" if tried else "SIZING",
                                 f"{tried} placements realized, none kept; {histogram}",
                                 candidates_tried=tried, stage_histogram=histogram, warnings=tuple(warnings), seconds=secs)
    sp, ac = best.spatial, best.access
    return PipelineSuccess(realized=best.realized, placement=best.placement, candidate_index=0,
                           candidates_tried=tried, spatial_preserved=f"{sp.preserved}/{sp.requested}",
                           access_preserved=f"{ac.preserved}/{ac.requested}",
                           access_lost=tuple(str(e) for e in ac.lost), warnings=tuple(warnings),
                           seconds=secs, selection={"histogram": histogram})
