"""Topology -> placement bridge (Issue #160 — the spike this module exists to answer).

`rectilinear_realizer.RealizationIntent` requires placement already decided — `wings` IS the
placement (see that module's own docstring). A `schema.TopologyProposal` (Issue #151) is a GRAPH
with no placement at all: no coordinates, no slot order, no wing choice. Nothing before this module
turned one into the other. This is that missing piece, kept deliberately small:

  1. `build_realization_intent` decides placement by SEARCH, never by editing the proposal — the
     proposal object passed in is never mutated (proven by
     `tests/ai_harness/test_topology_placement_bridge.py::test_bridge_does_not_mutate_proposal`,
     AC-3). It tries exactly the two wing shapes `rectilinear_realizer` actually offers:

       * `PinwheelWing` — exactly 5 zones, non-guillotine, able to realize up to 8 spatial-adjacency
         pairs (4 spokes + 4 corner interlocks) among those 5 rooms. Used whenever the proposal has
         exactly 5 rooms (searches all 5! assignments of room -> slot, keeps the one whose
         achievable spoke/corner pairs overlap the requested `spatial_adjacency` graph the most).
       * `RowWing` — a single left-to-right chain. A chain of n slots touches at most n-1 pairs, by
         construction (each slot touches only its immediate neighbour(s)) — splitting the same n
         rooms across multiple `RowWing`s connected by cross-wing seams does not raise this ceiling
         either: each extra wing boundary buys exactly one more touching pair at the cost of one
         fewer internal slot-to-slot pair in that wing, so the TOTAL stays n-1 regardless of how the
         rooms are split across wings. Used when the proposal's requested
         `spatial_adjacency` edge count is <= n-1 (searches room orderings, keeps the one whose
         consecutive-pair adjacency overlaps the requested graph the most).

  2. **No row fallback** (AC-4, out-of-scope list): when neither shape can hold the requested graph
     — n != 5 and the requested edge count exceeds n-1 — `build_realization_intent` returns a
     `BridgeRefusal` naming the exact reason. It never emits a row anyway and calls it realized;
     that is the #134 donor-experiment failure mode this Issue exists to prevent.

  3. Room AREAS come from `concept_generator.ROOM_TEMPLATES` — the same role-keyed table
     `concept_generator.build_room_program` itself reads for every room of that role (there is one
     template per role, not per brief; see that module's own `add()` helper) — never invented
     numbers. A role the table does not size (e.g. `CIRCULATION`, a role `ROOM_TEMPLATES` has no
     entry for) gets one explicit, disclosed, generically-sized fallback — never a silent 0 or an
     unbounded range.

No validator, access rule, or production default is touched anywhere in this module — it only
calls the EXISTING `rectilinear_realizer.realize_layout` and reads `app.vertical_slice.access_rules`
(never writes to it).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from app.vertical_slice import access_rules
from app.vertical_slice.concept_generator import ROOM_TEMPLATES
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.rectilinear_realizer import (
    PinwheelWing,
    RealizationIntent,
    Refusal,
    RowWing,
    ZoneIntent,
)

from .schema import ENTRANCE_ID, TopologyProposal

_PINWHEEL_SLOTS = ("center", "n", "e", "s", "w")
#: The 8 slot-pairs a `PinwheelWing` can ever realize as a physically-touching pair: the 4 spokes
#: (center always touches every arm) plus the 4 corner interlocks (module docstring).
_PINWHEEL_ACHIEVABLE_SLOT_PAIRS = (
    ("center", "n"), ("center", "e"), ("center", "s"), ("center", "w"),
    ("n", "e"), ("e", "s"), ("s", "w"), ("w", "n"),
)

#: The proven pinwheel envelope/area point `spikes/geometry_shapes/stage1_gate.py` already
#: validated against the full validator chain, reused here (scaled) rather than re-derived —
#: see that module's own `build_pinwheel_intent` docstring for the provenance of these numbers.
_PROVEN_ENVELOPE_M = (9.4, 9.8)
_PROVEN_TOTAL_M2 = 29.0 + 19.3 + 24.0 + 9.0 + 6.2  # N + E + S + W + center

#: A role `ROOM_TEMPLATES` does not size (e.g. `CIRCULATION` — this engine only sizes `HALL`).
#: Deliberately generic and clearly disclosed, never a silent/invented precise number.
_FALLBACK_TEMPLATE_BOUNDS = (6.0, 10.0, 40.0, 1.2, 4.0)  # min, target, max, min_short, max_aspect


@dataclass(frozen=True)
class BridgeRefusal:
    """A requested graph this bridge will not even attempt to place — the failing structural
    reason, named, never silently downgraded to a row (AC-4)."""

    reason: str
    detail: str


def room_area_intent(room_id: str, role_value: str) -> ZoneIntent:
    """This room's own `ZoneIntent`, sized from `concept_generator.ROOM_TEMPLATES[role]` — the
    engine's own program table, never an invented number (module docstring, point 3)."""
    role = ProgramRole(role_value)
    template = ROOM_TEMPLATES.get(role)
    if template is None:
        min_m2, target_m2, max_m2, min_short_m, max_aspect = _FALLBACK_TEMPLATE_BOUNDS
        return ZoneIntent(room_id, role, target_m2, min_m2, max_m2, min_short_m, max_aspect)
    return ZoneIntent(room_id, role, template.target_area_m2, template.min_area_m2,
                       template.max_area_m2, template.min_short_side_m, template.max_aspect_ratio)


def is_access_policy_valid(proposal: TopologyProposal) -> bool:
    """Is every `access_graph` edge a door the REAL production `access_rules.ALLOWED_ENTERED_FROM`
    table would allow (AC-1)? Checked against the actual `app.vertical_slice.access_rules` module
    — never the ai_harness's own, separate, bespoke hard-violation heuristic in `critic.py` — since
    this is specifically "does the EXISTING realizer's own access-policy table accept this edge,"
    not "does the critic's own proposal-quality rubric." `ENTRANCE_ID` maps to `ProgramRole.
    ENTRANCE` — it is a reserved access-graph anchor (never a room), but the real engine's own
    entrance zone IS of that role, and `ALLOWED_ENTERED_FROM` already has an entry for it (`PUBLIC_
    ROLES` includes `ProgramRole.ENTRANCE`)."""
    role_lookup: dict[str, ProgramRole] = {
        rid: ProgramRole(role) for rid, role in proposal.role_by_id.items()}
    role_lookup[ENTRANCE_ID] = ProgramRole.ENTRANCE
    for a, b in proposal.access_graph:
        if not access_rules.edge_role_pair_allowed((role_lookup[a],), (role_lookup[b],)):
            return False
    return True


def _row_capacity(n: int) -> int:
    return max(n - 1, 0)


def _best_pinwheel_assignment(proposal: TopologyProposal) -> tuple[dict[str, str], int]:
    room_ids = tuple(r.id for r in proposal.rooms)
    req_pairs = {frozenset(p) for p in proposal.spatial_adjacency}
    best_mapping: dict[str, str] | None = None
    best_score = -1
    for perm in permutations(room_ids):
        mapping = dict(zip(_PINWHEEL_SLOTS, perm))
        achieved = {frozenset((mapping[a], mapping[b])) for a, b in _PINWHEEL_ACHIEVABLE_SLOT_PAIRS}
        score = len(req_pairs & achieved)
        if score > best_score:
            best_score, best_mapping = score, mapping
    assert best_mapping is not None
    return best_mapping, best_score


def _best_row_assignment(proposal: TopologyProposal) -> tuple[list[str], int]:
    room_ids = list(r.id for r in proposal.rooms)
    req_pairs = {frozenset(p) for p in proposal.spatial_adjacency}
    n = len(room_ids)

    def _score(order) -> int:
        achieved = {frozenset((order[i], order[i + 1])) for i in range(len(order) - 1)}
        return len(req_pairs & achieved)

    if n <= 8:
        best_order, best_score = None, -1
        for perm in permutations(room_ids):
            s = _score(perm)
            if s > best_score:
                best_score, best_order = s, perm
        return list(best_order), best_score

    # Greedy nearest-neighbour fallback for n > 8 — never exercised by this Issue's own selected
    # cases (every one of them with n > 5 fails the row-capacity check below before reaching this),
    # kept general rather than raising so the bridge has SOME answer for a sparse large-n graph.
    remaining = set(room_ids)
    order = [room_ids[0]]
    remaining.discard(room_ids[0])
    while remaining:
        last = order[-1]
        nxt = next((r for r in remaining if frozenset((last, r)) in req_pairs), None)
        if nxt is None:
            nxt = next(iter(remaining))
        order.append(nxt)
        remaining.discard(nxt)
    return order, _score(order)


def _pinwheel_envelope(zones_by_slot: dict[str, ZoneIntent], scale: float = 1.0) -> tuple[float, float]:
    total = sum(z.target_area_m2 for z in zones_by_slot.values())
    lam = max(0.5, total / _PROVEN_TOTAL_M2) * scale
    root_lam = lam ** 0.5
    return round(_PROVEN_ENVELOPE_M[0] * root_lam, 2), round(_PROVEN_ENVELOPE_M[1] * root_lam, 2)


def _row_envelope(zones_by_id: dict[str, ZoneIntent]) -> tuple[float, float]:
    height_m = max(z.min_short_side_m for z in zones_by_id.values()) + 1.5
    total_target = sum(z.target_area_m2 for z in zones_by_id.values())
    return round(total_target / height_m, 2), round(height_m, 2)


def build_realization_intent(proposal: TopologyProposal, name: str, envelope_scale: float = 1.0,
                              envelope_override: "tuple[float, float] | None" = None
                              ) -> "RealizationIntent | BridgeRefusal":
    """Converts a frozen `TopologyProposal` into the realizer's own `RealizationIntent` by
    searching placements, never by editing `proposal` (AC-3) — every `ZoneIntent`/room id/role
    below is read off `proposal`, nothing is added or renamed. Refuses (AC-4), never falls back to
    a row, when the requested graph cannot fit any wing shape this realizer has.

    `envelope_scale` is this function's OWN input knob, not a hidden adjustment: a caller may
    retry the SAME chosen placement at a different envelope scale when `realize_layout` refuses for
    a geometric (not structural) reason — exactly the retry policy
    `spikes/geometry_shapes/stage1_gate.py` already uses and discloses (see that module's own
    `_run_one` docstring: `realize_layout` itself never approximates; only the caller's retry loop
    tries a different, still fully-specified input next). The PLACEMENT decided here never changes
    across scales — only the envelope's own size does. `envelope_override`, when given, bypasses
    `envelope_scale`/the proven-point formula entirely with an exact (width_m, height_m) — the same
    kind of caller-driven retry input, for a caller doing its own 2D grid search rather than a
    1D scale ladder (PinwheelWing only; ignored for a RowWing)."""
    room_ids = tuple(r.id for r in proposal.rooms)
    n = len(room_ids)
    edges = len(proposal.spatial_adjacency)
    declared_adjacency = tuple(sorted(tuple(sorted(p)) for p in proposal.spatial_adjacency))

    if n == 5:
        mapping, _score = _best_pinwheel_assignment(proposal)
        zones = {slot: room_area_intent(mapping[slot], proposal.role_by_id[mapping[slot]])
                 for slot in _PINWHEEL_SLOTS}
        width_m, height_m = envelope_override or _pinwheel_envelope(zones, envelope_scale)
        wing = PinwheelWing(wing_id="MAIN", width_m=width_m, height_m=height_m,
                             n=zones["n"], e=zones["e"], s=zones["s"], w=zones["w"],
                             center=zones["center"])
        return RealizationIntent(name=name, wings=(wing,), declared_adjacency=declared_adjacency)

    capacity = _row_capacity(n)
    if edges > capacity:
        return BridgeRefusal(
            "ROW_CAPACITY_EXCEEDED",
            f"requested graph needs {edges} spatial-adjacency relationship(s) among {n} rooms; a "
            f"single row can realize at most {capacity} (n-1), and n={n} != 5 so the realizer's "
            f"only other structure (PinwheelWing, exactly 5 zones) is not available either — no "
            f"row fallback is attempted")

    order, _score = _best_row_assignment(proposal)
    zones_by_id = {rid: room_area_intent(rid, proposal.role_by_id[rid]) for rid in room_ids}
    width_m, height_m = _row_envelope(zones_by_id)
    width_m, height_m = round(width_m * envelope_scale ** 0.5, 2), round(
        height_m * envelope_scale ** 0.5, 2)
    wing = RowWing(wing_id="MAIN", width_m=width_m, height_m=height_m, slots=tuple(order),
                   zones=zones_by_id)
    return RealizationIntent(name=name, wings=(wing,), declared_adjacency=declared_adjacency)


#: The classification vocabulary AC-7 names, decided BEFORE any code change (Issue text, point 6).
#: BRIDGE: `build_realization_intent` itself refused — no assignment was even attempted.
#: PLACEMENT: a wing shape was selected and a search ran, but no assignment it tried could satisfy
#:   that wing's own shape constraints at all (distinct from REALIZER: not "these specific areas
#:   don't fit," but "no room-to-slot assignment of this shape could ever have worked").
#: REALIZER: `realize_layout` refused for a geometric reason (area/short-side/aspect/shape).
#: VALIDATOR: `realize_layout` refused because `validation.validate` rejected the realized plan.
FailureClass = str


def classify_failure(result: "BridgeRefusal | Refusal") -> FailureClass:
    if isinstance(result, BridgeRefusal):
        return "BRIDGE"
    if isinstance(result, Refusal):
        if result.constraint == "VALIDATION_FAILED":
            return "VALIDATOR"
        return "REALIZER"
    raise TypeError(f"not a bridge or realizer refusal: {result!r}")
