# Topology -> placement bridge spike (Issue #160)

Answers one question: when the EXISTING `rectilinear_realizer` is handed a high-scoring LLM topology (Issue #151's own frozen dataset) that already satisfies CURRENT access policy, does it build it while PRESERVING the requested graph? No validator, access rule, or production default is changed anywhere in this spike (AC-8); the frozen 432-context corpus is byte-identical (see the regression run below).

## AC-1 — ranking, all 20 frozen briefs

`absolute best` is the top-scoring LLM proposal regardless of access policy. `best policy-valid` is the top-scoring proposal, among the top-8 by `total_score`, whose `access_graph` is accepted in full by the REAL `app.vertical_slice.access_rules.ALLOWED_ENTERED_FROM` table (`placement_bridge.is_access_policy_valid`) — never the ai_harness's own separate critic-side hard-violation heuristic. `rank` is that proposal's own position (1-based) among the top-8. `score loss` is `absolute best - best policy-valid` (0.0 when rank is 1).

| brief | absolute best | best policy-valid | rank (of top-8) | score loss |
|---|---|---|---|---|
| B01 | 0.651797 | 0.651797 | 1 | 0.000000 |
| B02 | 0.651797 | -1.897253 | 2 | 2.549050 |
| B03 | 0.271786 | 0.271786 | 1 | 0.000000 |
| B04 | -1.070773 | -1.070773 | 1 | 0.000000 |
| B05 | -0.038917 | -0.038917 | 1 | 0.000000 |
| B06 | -0.719786 | -0.719786 | 1 | 0.000000 |
| B07 | -0.642711 | -0.642711 | 1 | 0.000000 |
| B08 | 0.514455 | 0.514455 | 1 | 0.000000 |
| B09 | 0.298441 | 0.298441 | 1 | 0.000000 |
| B10 | 0.609144 | 0.609144 | 1 | 0.000000 |
| B11 | -1.002740 | -1.624146 | 3 | 0.621406 |
| B12 | 0.198735 | 0.198735 | 1 | 0.000000 |
| B13 | 0.825159 | 0.825159 | 1 | 0.000000 |
| B14 | -0.111968 | -0.111968 | 1 | 0.000000 |
| B15 | 0.902234 | 0.902234 | 1 | 0.000000 |
| B16 | 1.190307 | 1.190307 | 1 | 0.000000 |
| B17 | -1.649084 | -1.697197 | 2 | 0.048113 |
| B18 | -0.034893 | -0.034893 | 1 | 0.000000 |
| B19 | -0.372291 | -0.372291 | 1 | 0.000000 |
| B20 | 0.348861 | 0.348861 | 1 | 0.000000 |

**20/20 briefs have a policy-valid proposal in their own top-8; 17/20 briefs' absolute-best proposal is already policy-valid** (rank 1, zero score loss) — reproducing the lead's own measurement exactly, from the committed dataset, with no new LLM call.

## AC-2 — selected representative briefs

Selected: **B01, B10, B13, B15, B16** — all rank-1 policy-valid with zero score loss (see the table above). This is the lead's own selection (Issue #160's "Required behavior" §2), not re-derived here: it spans 1-5 bedrooms, 1-3 wet rooms, with and without SAFE_ROOM, open and closed plans, small and large footprints — a representative spread, not five similar cases. No deviation from the named set.

## AC-5 / AC-7 — per-case result and failure classification

Every failure below is classified as one of BRIDGE / PLACEMENT / REALIZER / VALIDATOR (decided before any code change — Issue #160's own "Required behavior" §6): **BRIDGE** — `placement_bridge.build_realization_intent` itself refused, no assignment was even attempted (the row-capacity check: a single row can realize at most n-1 spatial-adjacency pairs among n rooms, and this proposal's graph needs more, with n != 5 so the only other wing shape, `PinwheelWing`, is unavailable too). **PLACEMENT** — a wing shape was selected and a search ran, but no room-to-slot assignment of that shape could ever satisfy it (not observed in this run's 5 cases; also not currently reachable from `classify_failure` at all — `_best_pinwheel_assignment`/`_best_row_assignment` always hand the realizer their own best-scoring assignment regardless of match quality, so this bridge cannot yet distinguish "no assignment of this shape could ever have worked" from a REALIZER-stage geometric failure. Disclosed gap, not exercised by any test; acceptable for this Issue's deliberately minimal bridge, per the Issue's own "smallest possible bridge" instruction). **REALIZER** — `rectilinear_realizer.realize_layout` refused for a geometric reason (area/short-side/aspect/shape infeasible at every envelope scale this run's own disclosed retry ladder tried). **VALIDATOR** — `realize_layout` refused because `validation.validate` rejected the realized geometry.

| brief | n rooms | spatial-adjacency edges requested | n-1 (row capacity) | outcome | failure class | reason |
|---|---|---|---|---|---|---|
| B01 | 5 | 6 | 4 | REFUSED | REALIZER | SHORT_SIDE_INFEASIBLE |
| B10 | 9 | 14 | 8 | REFUSED | BRIDGE | ROW_CAPACITY_EXCEEDED |
| B13 | 10 | 12 | 9 | REFUSED | BRIDGE | ROW_CAPACITY_EXCEEDED |
| B15 | 11 | 15 | 10 | REFUSED | BRIDGE | ROW_CAPACITY_EXCEEDED |
| B16 | 13 | 19 | 12 | REFUSED | BRIDGE | ROW_CAPACITY_EXCEEDED |

### B01

**REFUSED** — classified **REALIZER**: `SHORT_SIDE_INFEASIBLE` — KITCHEN: pinwheel-realized short side 1.50 m (gross) < 2.4 m (net) + 0.3 m inset margin

The chosen placement ({'center': 'LIVING', 'n': 'KITCHEN', 'e': 'HALL', 's': 'MASTER', 'w': 'BATHROOM_1'}) achieves 6/6 of the requested spatial-adjacency pairs STRUCTURALLY (the best of all 5! room-to-slot assignments) — this is a sizing failure of the pinwheel's own band-thickness solver, not a placement/matching failure: an exhaustive 31x31 (961-point) width/height grid search over this SAME placement found zero feasible envelopes.

### B10

**REFUSED** — classified **BRIDGE**: `ROW_CAPACITY_EXCEEDED` — requested graph needs 14 spatial-adjacency relationship(s) among 9 rooms; a single row can realize at most 8 (n-1), and n=9 != 5 so the realizer's only other structure (PinwheelWing, exactly 5 zones) is not available either — no row fallback is attempted

### B13

**REFUSED** — classified **BRIDGE**: `ROW_CAPACITY_EXCEEDED` — requested graph needs 12 spatial-adjacency relationship(s) among 10 rooms; a single row can realize at most 9 (n-1), and n=10 != 5 so the realizer's only other structure (PinwheelWing, exactly 5 zones) is not available either — no row fallback is attempted

### B15

**REFUSED** — classified **BRIDGE**: `ROW_CAPACITY_EXCEEDED` — requested graph needs 15 spatial-adjacency relationship(s) among 11 rooms; a single row can realize at most 10 (n-1), and n=11 != 5 so the realizer's only other structure (PinwheelWing, exactly 5 zones) is not available either — no row fallback is attempted

### B16

**REFUSED** — classified **BRIDGE**: `ROW_CAPACITY_EXCEEDED` — requested graph needs 19 spatial-adjacency relationship(s) among 13 rooms; a single row can realize at most 12 (n-1), and n=13 != 5 so the realizer's only other structure (PinwheelWing, exactly 5 zones) is not available either — no row fallback is attempted

## AC-6 — preservation, per realized case

No selected case realized in this run (see AC-5/AC-7 above for why each refused) — there is nothing to measure preservation on. This is itself the spike's own answer: **every one of the 5 selected high-scoring, policy-valid real topologies failed to reach a built house**, 4/5 structurally (BRIDGE, before the realizer ever ran) and 1/5 geometrically (REALIZER, no envelope scale this run's retry ladder tried fit the chosen placement) — not a single VALIDATOR-stage loss, because no case got far enough to reach `validate()`.

## Reproducing this spike

```
cd backend
uv run python -m app.ai_harness.topology_poc.bridge_report
```
