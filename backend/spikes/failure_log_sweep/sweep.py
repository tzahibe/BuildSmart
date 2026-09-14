"""Library: the failure log as reproducible `Project`s, plus the recorders the A/B and metrics need.

Only `app.*` imports. Run scripts from `backend/` so `app` resolves.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.projects.models import (
    Project, SelectedFootprint, SourceTag, TaggedBool, TaggedInt, StreetSide,
)

FAILURES = Path(__file__).resolve().parents[2] / "app" / "data" / "failures.json"

NEEDED = ("plot_width_m", "plot_depth_m", "street_facing_side", "built_area_m2",
          "footprint_width_m", "footprint_depth_m", "bedrooms", "wet_rooms",
          "safe_room", "open_plan")


def project_from_context(ctx: dict, *, with_footprint: bool = True) -> Project:
    """A log context (the demo request payload) as the `Project` the service would have seen.

    `with_footprint=False` withholds the outline the person chose, which is how feature 006's main
    flow — the engine picks the outline — is replayed against the same log.
    """
    now = datetime.now(timezone.utc)
    fw, fd = ctx["footprint_width_m"], ctx["footprint_depth_m"]
    requested, unknown = SourceTag.requested, SourceTag.unknown
    footprint = SelectedFootprint(
        source="CUSTOM", shape_type="RECTANGLE", target_area_m2=ctx["built_area_m2"],
        width_m=fw, depth_m=fd, area_m2=round(fw * fd, 4),
    ) if with_footprint else None
    return Project(
        project_id=ctx.get("project_id", "SWEEP"),
        city="TLV", street="S", plot_area_m2=ctx["plot_width_m"] * ctx["plot_depth_m"],
        plot_width_m=ctx["plot_width_m"], plot_depth_m=ctx["plot_depth_m"],
        street_facing_side=StreetSide(ctx["street_facing_side"]),
        built_area_m2=ctx["built_area_m2"],
        description=ctx.get("description", ""),
        status="active", created_at=now, updated_at=now,
        selected_footprint=footprint,
        floors=TaggedInt(value=1, source=SourceTag.inferred),
        bedrooms=TaggedInt(value=ctx["bedrooms"], source=requested),
        safe_room=TaggedBool(value=bool(ctx["safe_room"]),
                             source=requested if ctx["safe_room"] else unknown),
        parking_spaces=TaggedInt(value=0, source=requested),
        wet_rooms=TaggedInt(value=ctx["wet_rooms"], source=requested),
        open_plan=TaggedBool(value=bool(ctx["open_plan"]), source=requested),
        requirements_parsed_at=now,
    )


def key_of(ctx: dict) -> str:
    return json.dumps({k: ctx[k] for k in NEEDED}, sort_keys=True)


def distinct_contexts(path: Path = FAILURES) -> list[dict]:
    """The log's distinct reproducible request contexts, in a stable order."""
    with open(path) as f:
        entries = json.load(f)
    seen: dict[str, dict] = {}
    for entry in entries:
        ctx = entry.get("context") or {}
        if all(k in ctx and ctx[k] is not None for k in NEEDED):
            seen.setdefault(key_of(ctx), ctx)
    return [seen[k] for k in sorted(seen)]


def signature(design) -> tuple:
    """Everything a person would see of a plan's geometry: every room's type and rectangle."""
    return tuple(sorted((r.type, r.x, r.y, r.width_m, r.depth_m) for r in design.rooms))


def plans_shown(result) -> list:
    """The plan and its alternatives, in the order the screen shows them."""
    return [result.design, *result.alternatives]


class StrategyRecorder:
    """Records which concept candidate the pipeline realized, and every rejection, per run.

    Wraps `general_pipeline._realize` (the chosen candidate) and `concept_generator.generate_concepts`
    (the candidate list and the rejections) — the pipeline resolves both names at call time, so
    swapping the module attributes is enough. `install()`/`remove()` are idempotent.
    """

    def __init__(self):
        from app.vertical_slice import general_pipeline as gp
        from app.vertical_slice import concept_generator as cg
        self._gp, self._cg = gp, cg
        self._orig_realize = gp._realize
        self._orig_generate = cg.generate_concepts
        self.reset()

    def reset(self):
        self.chosen_strategy: str | None = None
        self.chosen_is_twin: bool = False
        self.chosen_rationale: str = ""
        self.candidate_strategies: list[str] = []
        self.rejections: list[tuple[str, str]] = []

    def install(self):
        rec = self

        def realize(spec, buildable, site_constraints, chosen, chosen_index, solve, relationships,
                    on_stage=None):
            # The FIRST realization in a run is the chosen plan; `_alternative_plans` realizes
            # further candidates afterwards for the demo screen and must not overwrite it.
            if rec.chosen_strategy is None:
                rec.chosen_strategy = chosen.strategy.value
                rec.chosen_is_twin = chosen.rationale.endswith(rec._cg.FREE_TWIN_RATIONALE)
                rec.chosen_rationale = chosen.rationale
            return rec._orig_realize(spec, buildable, site_constraints, chosen, chosen_index, solve,
                                     relationships, on_stage=on_stage)

        def generate(spec, candidates):
            res = rec._current_generate(spec, candidates)
            rec.candidate_strategies = [c.strategy.value for c in res.candidates]
            rec.rejections = [(r.strategy.value, r.reason.value) for r in res.rejections]
            return res

        self._current_generate = self._cg.generate_concepts
        self._gp._realize = realize
        self._cg.generate_concepts = generate

    def remove(self):
        self._gp._realize = self._orig_realize
        self._cg.generate_concepts = self._orig_generate
