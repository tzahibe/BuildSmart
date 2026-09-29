"""Builds the actual LLM prompt (Issue #151, requirements 1-3).

The LLM produces NO geometry — this is stated to the model, not just enforced after the fact by
`schema.validate_no_geometry`. The prompt embeds `context.render_context_text` verbatim (the
corrected #149 + #140 grounding) and the brief's own room programme (ids the model MUST reuse
exactly, so instance identity is unambiguous — requirement 1: "every graph and every grouping works
on room IDs, never on roles").
"""
from __future__ import annotations

from app.ai_harness.topology_poc.briefs import Brief
from app.ai_harness.topology_poc.context import PromptContext, render_context_text

SYSTEM_PROMPT = (
    "You are a residential architecture CONCEPT layer. You propose spatial ideas only: which rooms "
    "sit next to which (adjacency), which rooms are reached from which through a door or opening "
    "(access), how rooms group into public/private/service/circulation zones, how wet rooms cluster, "
    "and how the entrance relates to the rest of the plan. "
    "You NEVER produce geometry: no coordinates, no widths, no depths, no areas, no polygons, no "
    "walls, no drawing of any kind. Any such field in your output is a hard failure. "
    "ADJACENCY IS NOT ACCESS: two rooms can share a wall with no door (adjacent but not accessed), "
    "or be joined by a door across a corridor (accessed but not touching). Keep them separate. "
    "Every room you use MUST be exactly one of the room ids given to you — never invent, rename, "
    "merge, or drop a room id. Every proposal MUST include ALL of the given room ids, every time — "
    "never omit one. A role (e.g. BEDROOM) may apply to several distinct room ids "
    "(e.g. BEDROOM_1, BEDROOM_2) — treat every id as its own node; do not collapse two rooms of the "
    "same role into one. "
    '"ENTRANCE" is NEVER a room: never put it in "rooms", never put it in "spatial_adjacency", '
    'never put it in "zones" or "clusters". It may ONLY appear as the first element of a pair in '
    '"access_graph" (e.g. ["ENTRANCE", "HALL"]), or as the first element of "entrance_relation.'
    'sequence".'
)


def build_brief_program_text(brief: Brief) -> tuple:
    """Returns `(room_ids_and_roles, program_text)` — the FIXED room-id vocabulary every proposal
    for this brief must use (requirement 1)."""
    rooms = [("LIVING", "LIVING")]
    if brief.open_plan:
        rooms += [("DINING", "DINING"), ("KITCHEN", "KITCHEN")]
    else:
        rooms += [("KITCHEN", "KITCHEN")]
    rooms.append(("HALL", "HALL"))
    if brief.bedrooms >= 1:
        rooms.append(("MASTER", "MASTER_BEDROOM"))
    for i in range(1, brief.bedrooms):
        rooms.append((f"BEDROOM_{i}", "BEDROOM"))
    if brief.safe_room:
        rooms.append(("SAFE_ROOM", "SAFE_ROOM"))
    for i in range(1, brief.wet_rooms + 1):
        rooms.append((f"BATHROOM_{i}", "BATHROOM"))
    program_text = ", ".join(f"{rid}({role})" for rid, role in rooms)
    return tuple(rooms), program_text


def build_prompt(context: PromptContext, brief: Brief, *, n_proposals: int = 6) -> tuple:
    """Returns `(system_prompt, user_prompt)`."""
    rooms, program_text = build_brief_program_text(brief)
    room_ids = [rid for rid, _ in rooms]
    user_prompt = (
        f"{render_context_text(context)}\n"
        f"BRIEF (id={brief.brief_id}): {brief.bedrooms} bedroom(s), {brief.wet_rooms} wet room(s), "
        f"safe_room={brief.safe_room}, open_plan={brief.open_plan}, "
        f"footprint aspect={brief.aspect_tier}, house size={brief.size_tier} "
        f"({brief.built_area_m2} m2 built area).\n\n"
        f"ROOM PROGRAMME — use EXACTLY these room ids, every one, in every proposal: {program_text}\n\n"
        f"Generate exactly {n_proposals} MATERIALLY DIFFERENT structured spatial topology proposals "
        "as a JSON array. Each element is one proposal object with EXACTLY these keys:\n"
        '  "rooms": [{"id": ROOM_ID, "role": ROLE}, ...]  — copy the room programme above verbatim\n'
        '  "spatial_adjacency": [[id_a, id_b], ...]  — unordered pairs of room ids that share a wall\n'
        '  "access_graph": [[from_id, to_id], ...]  — DIRECTED pairs; "ENTRANCE" is a valid from_id '
        "(never a to_id); every room must be reachable from ENTRANCE\n"
        '  "zones": {"public": [...], "private": [...], "service": [...], "circulation": [...]} — '
        "every room id in exactly one zone\n"
        '  "clusters": {"wet_core": [...]}  — the wet room ids that are grouped together (omit if none)\n'
        '  "relative_position": [{"room_id": ..., "relation": "NORTH_OF"|"SOUTH_OF"|"EAST_OF"|'
        '"WEST_OF", "reference_room_id": ...}, ...]  — qualitative only, never a number\n'
        '  "entrance_relation": {"opens_into": ROOM_ID, "sequence": [ROOM_ID, ...]}\n'
        '  "design_tradeoff": "one sentence — your own reasoning, NOT evidence, ignored by scoring"\n\n'
        f"Make each of the {n_proposals} proposals differ in at least one of: the adjacency graph, "
        "the access graph, the public/private organisation, the wet-core placement, the entrance "
        "sequence, corridor usage, or spatial hierarchy — a renamed variable is not a difference. "
        "Return ONLY the JSON array. No prose, no markdown code fences, no explanation outside the "
        "JSON.\n\n"
        "EXACT SHAPE EXAMPLE — copy this structure precisely (\"rooms\" is a list of OBJECTS, never "
        "a list of bare strings):\n"
        '{"rooms": [{"id": "LIVING", "role": "LIVING"}, {"id": "HALL", "role": "HALL"}], '
        '"spatial_adjacency": [["LIVING", "HALL"]], '
        '"access_graph": [["ENTRANCE", "HALL"], ["HALL", "LIVING"]], '
        '"zones": {"public": ["LIVING"], "private": [], "service": [], "circulation": ["HALL"]}, '
        '"clusters": {}, '
        '"relative_position": [{"room_id": "LIVING", "relation": "EAST_OF", "reference_room_id": "HALL"}], '
        '"entrance_relation": {"opens_into": "HALL", "sequence": ["HALL", "LIVING"]}, '
        '"design_tradeoff": "example only, not a real proposal"}'
    )
    return SYSTEM_PROMPT, user_prompt
