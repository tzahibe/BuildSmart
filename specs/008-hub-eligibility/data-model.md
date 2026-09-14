# Data Model: Hub Eligibility

Two small, immutable values inside `concept_generator.py`. Nothing is persisted; nothing crosses the
service boundary except the rationale text.

## HubBound *(frozen dataclass)*

The best the v2 hub tree can do on one outline for one room programme, under the access and
wet-adjacency rules — the Phase 0 "gated" bound.

| Field | Type | Meaning |
|---|---|---|
| `fw_m`, `fh_m` | float | outline width / depth the bound was computed for |
| `hub_widths_m` | tuple[float, ...] | lobby widths tried (the ones `_hub_concept` would) |
| `required_doors` | int | rooms needing a lobby door in this programme |
| `seated_doors` | int | most such rooms any sizing seated |
| `best_wet_adjacency` | float | best M5 share any feasible sizing reached (0–1) |
| `gated_bedroom_aspect` | float \| None | min over feasible, wet-gated sizings of max(bedroom-class aspect); None if no sizing reaches the wet gate |
| `gated_master_aspect` | float \| None | master aspect at that sizing |
| `gated_safe_aspect` | float \| None | safe-room aspect at that sizing (reported, not gated) |
| `evaluated` | int | sizings evaluated (for the cost test) |

Validation: `seated_doors ≤ required_doors`; `0 ≤ best_wet_adjacency ≤ 1`; aspects ≥ 1.

## HubEligibility *(enum + decision)*

| Value | Condition (`HUB_GATES` = §6: bedroom 1.35, master 1.40, wet 0.80) |
|---|---|
| `ELIGIBLE` | `gated_bedroom_aspect ≤ 1.35` and `gated_master_aspect ≤ 1.40` |
| `LAST_RESORT` | otherwise (including `gated_bedroom_aspect is None`, i.e. the wet gate unreachable) |

Derived, never stored: `decide(bound) -> HubEligibility`.

## Relationships and transitions

- `_hub_concept` → `ConceptCandidate` (unchanged) ─ `generate_concepts` computes `HubBound` for it →
  `HubEligibility` → ordering (ELIGIBLE: as today; LAST_RESORT: after every other candidate, forced
  before twin) → `rationale` suffix carries the bound.
- The unforced twin inherits its forced tree's eligibility (it is made from the same candidate).
- No state machine: a candidate's eligibility is decided once per `generate_concepts` call.
