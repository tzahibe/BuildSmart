# Structured topology proposal schema (Issue #151, AC-1)

Source of truth: `backend/app/ai_harness/topology_poc/schema.py`. This page is a compact summary —
the module docstring and `tests/ai_harness/test_topology_proposal_schema.py` are authoritative.

## Fields

A proposal is a JSON object with:

- `rooms`: list of `{"id": <room id, e.g. "BEDROOM_2">, "role": <ProgramRole value, e.g. "BEDROOM">}`.
  **Identity and role are separate fields** — two rooms of the same role (two bedrooms, two
  bathrooms) are always distinct `id`s and stay distinct nodes end to end.
- `spatial_adjacency`: list of unordered `[id_a, id_b]` pairs — two rooms whose walls touch.
- `access_graph`: list of DIRECTED `[from_id, to_id]` pairs — a door or open threshold connects
  them. `"ENTRANCE"` is a reserved id, valid only as a `from_id` here (never in `rooms`, never in
  `spatial_adjacency` — the front door has no shared wall with a room, only access).
- `zones`: object with keys drawn from `public`/`private`/`service`/`circulation`, each a list of
  room ids. Every room belongs to exactly one zone.
- `clusters`: object, e.g. `{"wet_core": [...]}"` — grouped room ids.
- `relative_position`: list of `{"room_id", "relation", "reference_room_id"}`, `relation` one of
  `NORTH_OF`/`SOUTH_OF`/`EAST_OF`/`WEST_OF` — qualitative only, never a number.
- `entrance_relation`: `{"opens_into": <room id>, "sequence": [<room id or "ENTRANCE">, ...]}`.
- `design_tradeoff`: free text — the model's own reasoning. **Explicitly NOT evidence**: the critic
  never reads this field.

**No geometry field of any kind** — no coordinates, no widths/depths/areas, no polygons, no walls.
`schema.validate_no_geometry` rejects any of a fixed list of geometry-shaped key names (`x`, `y`,
`width_m`, `area_m2`, `polygon`, `wall`, ...) anywhere in the raw dict, at any nesting depth.

## Provenance vs scored object

`schema.TopologyProposal` (the dataclass `critic.score_topology` accepts) carries ONLY the fields
above — no `source`, no `realizability`. Provenance (which side produced a proposal) and
realizability (a metadata-only label) live on the separate `schema.ProposalRecord` wrapper, which
the critic never sees. See `critic.py`'s own docstring for the test that proves this.

## Regenerate

This page is written by hand (a schema description, not a scanner artifact) — kept in sync with
`schema.py` manually whenever a field changes.
