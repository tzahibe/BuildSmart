"""Builds the actual LLM prompt (Issue #151, requirements 1-3).

The LLM produces NO geometry — this is stated to the model, not just enforced after the fact by
`schema.validate_no_geometry`. The prompt embeds `context.render_context_text` verbatim (the
corrected #149 + #140 grounding) and the brief's own room programme (ids the model MUST reuse
exactly, so instance identity is unambiguous — requirement 1: "every graph and every grouping works
on room IDs, never on roles").
"""
from __future__ import annotations

from app.ai_harness.topology_poc.briefs import Brief, brief_wet_room_kinds
from app.ai_harness.topology_poc.context import PromptContext, render_context_text

SYSTEM_PROMPT = (
    "You are a residential architecture CONCEPT layer. You propose spatial ideas only: which rooms "
    "sit next to which (adjacency), which rooms are reached from which through a door or opening "
    "(access), how rooms group into public/private/service/circulation zones, how wet rooms cluster, "
    "and how the entrance relates to the rest of the plan. "
    "You NEVER produce geometry: no coordinates, no widths, no depths, no areas, no polygons, no "
    "walls, no drawing of any kind. Any such field in your output is a hard failure. "
    "ADJACENCY AND ACCESS ARE DIFFERENT FACTS, BUT A DOOR NEEDS A WALL: two rooms can share a wall "
    "with no door (adjacent but not accessed), but a DIRECT door between A and B REQUIRES that A and B "
    "share a wall — every access pair must also appear in spatial_adjacency. A corridor between A and B "
    "is A->corridor and corridor->B, never A->B. "
    "PRIVATE ROOMS: a bedroom, master bedroom, safe room, study or dressing room is entered ONLY from a "
    "hall or circulation space — never from the living room, the kitchen, the dining room, or another "
    "bedroom. "
    "WET ROOMS: every bathroom or WC has EXACTLY ONE door. An ENSUITE is entered only from its one host "
    "bedroom (named in the programme). A SHARED_BATHROOM or GUEST_WC is entered from the public side of "
    "the house — the hall or circulation, or the living room as the fallback — never from a bedroom, "
    "never from the kitchen or dining room. Use the wet-room kinds and hosts given in the programme; "
    "do not invent different ones. "
    "REQUIRED versus PREFERRED: spatial_adjacency is a HARD requirement — every pair you list must be "
    "an actual geometric wall contact in the built plan, and the plan is refused if it cannot be. "
    "Preferences such as 'near', 'clustered' or 'wet core' are NOT wall contacts: express them in "
    "clusters and relative_position, not in spatial_adjacency, unless you truly require the shared wall. "
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
    # wet rooms carry their KIND and host from the brief (Issue #142J): never a flat list of BATHROOMs
    wet = brief_wet_room_rooms(brief)
    rooms += [(rid, role) for rid, role, _desc in wet]
    desc = {rid: d for rid, _role, d in wet}
    program_text = ", ".join(f"{rid}({role}{', ' + desc[rid] if rid in desc else ''})" for rid, role in rooms)
    return tuple(rooms), program_text


def brief_wet_room_rooms(brief: Brief) -> tuple:
    """(room id, role, description) per wet room the brief declares — `briefs.brief_wet_room_kinds`
    (the person's stated kinds, or the programme's count-derived defaults). BATHROOM_n for full
    bathrooms (ensuite or shared), TOILET_n for a guest WC."""
    from app.vertical_slice.spec import ENSUITE_HOST_BEDROOM, WetRoomKind
    out = []; baths = toilets = 0
    for req in brief_wet_room_kinds(brief):
        if req.kind is WetRoomKind.GUEST_WC:
            toilets += 1
            out.append((f"TOILET_{toilets}", "TOILET", "GUEST_WC: exactly one door, from HALL/circulation or LIVING"))
        elif req.kind is WetRoomKind.ENSUITE:
            baths += 1
            host = "a secondary BEDROOM" if req.host == ENSUITE_HOST_BEDROOM else "MASTER"
            out.append((f"BATHROOM_{baths}", "BATHROOM", f"ENSUITE of {host}: exactly one door, from {host} only"))
        else:
            baths += 1
            out.append((f"BATHROOM_{baths}", "BATHROOM", "SHARED_BATHROOM: exactly one door, from HALL/circulation or LIVING"))
    return tuple(out)


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
        f"ROOM PROGRAMME — use EXACTLY these room ids, every one, in every proposal: {program_text}\n"
        "Wet-room kinds and hosts above are the brief's requirements: keep them; give each wet room exactly "
        "one door from the entrant its kind allows.\n\n"
        f"Generate exactly {n_proposals} MATERIALLY DIFFERENT structured spatial topology proposals "
        "as a JSON array. Each element is one proposal object with EXACTLY these keys:\n"
        '  "rooms": [{"id": ROOM_ID, "role": ROLE}, ...]  — copy the room programme above verbatim\n'
        '  "spatial_adjacency": [[id_a, id_b], ...]  — unordered pairs of room ids that MUST share a wall '
        "(a hard requirement; include every access pair here too)\n"
        '  "access_graph": [[from_id, to_id], ...]  — DIRECTED door pairs; a door requires the shared wall '
        'above; "ENTRANCE" is a valid from_id (never a to_id); every room must be reachable from ENTRANCE '
        "through legal doors; every wet room has exactly one door\n"
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
