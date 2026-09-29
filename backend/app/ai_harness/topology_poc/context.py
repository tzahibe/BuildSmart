"""Assembles the grounding context handed to the LLM prompt (Issue #151, AC-2).

Built ONLY from `priors.load_priors()` (the corrected #149 artifacts) and #140's room-proportions
artifact. States explicitly which `ProgramRole`s the corpus cannot measure (`priors.
UNMEASURABLE_ROLES`), so the model is never told something false by omission. Keeps adjacency and
access as two clearly separate sections — "ADJACENCY IS NOT ACCESS" is stated literally, not left
implicit, per requirement 2.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ai_harness.topology_poc.priors import MEASURABLE_ROLES, UNMEASURABLE_ROLES, Priors

#: Minimum sample_count/support to surface a pair in the prompt at all — a below-floor row is
#: statistical noise, not a fact worth grounding a proposal in.
_HEADLINE_MIN_LIFT = 1.05
_TOP_N_PAIRS = 12


@dataclass(frozen=True)
class PairFact:
    role_a: str
    role_b: str
    rate: float  # p_smoothed
    lift: float


@dataclass(frozen=True)
class PromptContext:
    measurable_roles: tuple
    unmeasurable_roles: tuple
    adjacency_facts: tuple  # tuple[PairFact, ...] — from spatial_touching ONLY
    access_facts: tuple  # tuple[PairFact, ...] — from access ONLY, kept separate from adjacency
    front_door_direct_access: dict
    room_proportion_notes: tuple  # tuple[str, ...] — human-readable, from #140
    train_count: int
    holdout_count: int


def _top_facts(table, n: int = _TOP_N_PAIRS) -> tuple:
    supported = [r for r in table.rows if r.meets_min_support and r.lift >= _HEADLINE_MIN_LIFT]
    supported.sort(key=lambda r: -r.lift)
    return tuple(PairFact(role_a=r.role_a, role_b=r.role_b, rate=r.p_smoothed, lift=r.lift)
                 for r in supported[:n])


def _room_proportion_notes(rows: tuple) -> tuple:
    notes = []
    for row in rows:
        notes.append(
            f"{row['role']} in a {row['house_size_bucket']} house with "
            f"{row['bedroom_count_bucket']} bedrooms: median area {row['median_area_m2']} m2, "
            f"~{round(row['area_share_of_plan'] * 100, 1)}% of the plan's area "
            f"(n={row['sample_count']})")
    return tuple(notes)


def build_prompt_context(priors: Priors) -> PromptContext:
    return PromptContext(
        measurable_roles=tuple(MEASURABLE_ROLES),
        unmeasurable_roles=tuple(UNMEASURABLE_ROLES),
        adjacency_facts=_top_facts(priors.adjacency_table),
        access_facts=_top_facts(priors.access_table),
        front_door_direct_access=dict(priors.front_door_direct_access),
        room_proportion_notes=_room_proportion_notes(priors.room_proportions_rows),
        train_count=priors.train_count, holdout_count=priors.holdout_count)


def render_context_text(context: PromptContext) -> str:
    """Human/LLM-readable rendering of `PromptContext` — the text `prompt.py` embeds verbatim."""
    lines = [
        "GROUND TRUTH FROM REAL FLOOR PLANS (ResPlan corpus, corrected #149 measurement):",
        f"- Measured on {context.train_count} training plans, calibrated on {context.holdout_count} "
        "held-out plans never used to build the numbers below.",
        "",
        "ADJACENCY IS NOT ACCESS. Two rooms sharing a wall (adjacency) is a DIFFERENT fact from a "
        "door connecting them (access). Both are reported below, kept strictly separate.",
        "",
        "Roles this corpus CAN measure: " + ", ".join(context.measurable_roles) + ".",
        "Roles this corpus CANNOT measure at all (never claim a statistic for these — treat them as "
        "unmeasured, not as 'rarely adjacent'): " + ", ".join(context.unmeasurable_roles) + ".",
        "",
        "SPATIAL ADJACENCY facts (rooms whose walls actually touch in real plans; "
        "rate = P(touching | both roles present), lift = rate / baseline):",
    ]
    for f in context.adjacency_facts:
        lines.append(f"  - {f.role_a} <-> {f.role_b}: rate={f.rate}, lift={f.lift}")
    lines += [
        "",
        "ACCESS facts (rooms bridged by a door, or opening directly off the front door — a "
        "SEPARATE fact from adjacency above):",
    ]
    for f in context.access_facts:
        lines.append(f"  - {f.role_a} <-> {f.role_b}: rate={f.rate}, lift={f.lift}")
    lines += ["", "P(role opens directly off the front door | role present):"]
    for role, stats in sorted(context.front_door_direct_access.items()):
        lines.append(f"  - {role}: rate={stats['rate']}")
    lines += ["", "Real-plan room proportions (Issue #140, small in-sample fixture):"]
    for note in context.room_proportion_notes:
        lines.append(f"  - {note}")
    return "\n".join(lines) + "\n"
