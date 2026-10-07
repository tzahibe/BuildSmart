"""Where architectural intent becomes structurally trivial — measured UPSTREAM of selection.

Generation, not display:  brief -> adapter -> generate_concepts -> ConceptCandidate(s)
                                 -> ConceptSpec per candidate -> realization -> validation

For each of the eight frozen audit briefs this reports, at the CANDIDATE stage (before any plan is
realized and long before any plan is shown), how many genuinely distinct concepts the engine even
proposes — using production's OWN concept vocabulary (`concept_spec.ConceptSpec`: circulation
class, zoning split, wet-core grouping, master placement, entrance side) plus the structural facts
of each realized plan.

Nothing is modified. `generate_concepts` and `concept_spec_of` are called as production calls them.

    PYTHONPATH=backend python -m app.ai_harness.diversity_probe.upstream <out.json>
"""
from __future__ import annotations

import json
import os
import sys

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.vertical_slice import concept_generator as generator
from app.vertical_slice import concept_spec as cs
from app.vertical_slice.safe_adapter import adapt

BRIEFS = ("B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09")

#: Every value production's own vocabulary can express, so "how many are USED" is measurable
#: against "how many exist" rather than against an opinion.
VOCABULARY = {
    "circulation_class": [e.value for e in cs.CirculationClass],
    "zoning_split": [e.value for e in cs.ZoningSplit],
    "wet_core_grouping": [e.value for e in cs.WetCoreGrouping],
    "master_placement": [e.value for e in cs.MasterPlacement],
    "entrance_side": [e.value for e in cs.EntranceSide],
}


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


def spec_facts(candidate) -> dict:
    """One candidate's own concept identity, in production's vocabulary."""
    spec = cs.concept_spec_of(candidate)
    out = {"strategy": getattr(candidate.strategy, "value", str(candidate.strategy)),
           "circulation_class": getattr(candidate.circulation_class, "value",
                                        str(candidate.circulation_class))}
    # NOTE the vocabulary gap this probe exists to expose: `MasterPlacement` and `EntranceSide`
    # are declared enums with NO FIELD on `ConceptSpec` at all, so they cannot vary because nothing
    # carries them. `zoning` and `massing` are real fields.
    for field in ("zoning", "massing", "wet_core_strategy", "entrance_strategy", "family"):
        value = getattr(spec, field, None)
        out[field] = getattr(value, "value", None if value is None else str(value))
    out["has_master_placement_field"] = hasattr(spec, "master_placement")
    out["has_entrance_side_field"] = hasattr(spec, "entrance_side")
    return out


def run_brief(bid: str) -> dict:
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    project = _project_for(b)
    spec = svc.spec_for(project)
    buildable = svc._buildable_from(spec, project, None)
    adapted = adapt(buildable)
    generated = generator.generate_concepts(spec, list(adapted.candidates))

    rows = [spec_facts(c) for c in generated.candidates]
    def distinct(field: str) -> list:
        return sorted({r[field] for r in rows if r.get(field) is not None})

    # how many candidates are TOPOLOGICALLY distinct by production's own test
    specs = [cs.concept_spec_of(c) for c in generated.candidates]
    groups: list[int] = []
    for i, a in enumerate(specs):
        if not any(not cs.topologically_distinct(a, specs[j]) for j in groups):
            groups.append(i)

    return {
        "brief": bid,
        "wings_offered_by_adapter": len(adapted.candidates),
        "concept_candidates": len(generated.candidates),
        "topologically_distinct_candidates": len(groups),
        "distinct_strategy": distinct("strategy"),
        "distinct_circulation_class": distinct("circulation_class"),
        "distinct_zoning": distinct("zoning"),
        "distinct_massing": distinct("massing"),
        "distinct_wet_core_strategy": distinct("wet_core_strategy"),
        "distinct_entrance_strategy": distinct("entrance_strategy"),
        "distinct_family": distinct("family"),
        "master_placement_has_no_field": not rows[0]["has_master_placement_field"] if rows else None,
        "entrance_side_has_no_field": not rows[0]["has_entrance_side_field"] if rows else None,
        "candidates": rows,
    }


def main(out_path: str) -> dict:
    out = {"note": "concept diversity at the CANDIDATE stage, upstream of realization and selection",
           "vocabulary": VOCABULARY, "briefs": {}}
    print(f"{'brief':5s} {'wings':>5s} {'cands':>5s} {'topo':>4s} | {'strategies':46s} "
          f"{'class':12s} {'zoning':14s} {'massing':8s} {'families':>8s}")
    for bid in BRIEFS:
        row = run_brief(bid)
        out["briefs"][bid] = row
        print(f"{bid:5s} {row['wings_offered_by_adapter']:>5} {row['concept_candidates']:>5} "
              f"{row['topologically_distinct_candidates']:>4} | "
              f"{','.join(row['distinct_strategy'])[:46]:46s} "
              f"{','.join(row['distinct_circulation_class'])[:12]:12s} "
              f"{','.join(row['distinct_zoning'])[:14]:14s} "
              f"{','.join(row['distinct_massing'])[:8]:8s} "
              f"{len(row['distinct_family']):>8}", flush=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1])
