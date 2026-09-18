# [agent] Entrance-to-circulation integration: the front door leads to a circulation node, no dead-end wall or pocket at the entrance (C25)

### Goal

The entrance is integrated into the circulation system instead of landing at the end of a
corridor that was extended to the façade. Required sequence: exterior door → entrance/transition
zone → public circulation / main node → private corridor. No arbitrary wall in front of the
door, no dead-space pocket beside it, no tunnel-like walk past private rooms before the first
public node; an intentional foyer stays valid; accessibility (C5/C11/C16) never regresses; the
solution is topological and generic, not a patch for one fixture.

### Current behavior

The corridor's extent is a by-product of the slicing tree, not of the rooms it serves. In the
two-column ("spine") parti `HALL` is an unsplit `Leaf` under vertical cuts only
(`backend/app/vertical_slice/concept_generator.py:2896-2898`, `_concept_from`), so the corridor
always spans the full footprint depth and always touches the street wall; the demo contract
itself records it ("In every spine parti the hall runs the full depth of the house",
`backend/app/demo/contract.py:514-516`). `doors.resolve_entrance`
(`backend/app/vertical_slice/doors.py:147-204`) then chooses the arrival zone purely
geometrically — whichever realized rectangle touches `footprint.y`, by `ENTRANCE_ZONE_PRIORITY`
(HALL first), ties by width then leftmost — with no notion of what lies behind the door: so the
front door opens into the end of a full-depth corridor (spine), into a hall that runs the length
of the bedroom arm with the public rooms ~7 m back (`l_shaped_site_front_arm`,
`docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md` §5.1), or into whichever public
room happens to be widest at the street (front-band/hub/L partis) — which is not necessarily the
zone the hall opens into (`concept_generator.py:2467-2474`, `_build_access`), leaving the
corridor's street-facing end as a blind pocket beside the entrance. Observed by the owner on
2026-09-17: the corridor extends to the entrance façade and produces a wall/pocket immediately
at the entrance. Nothing detects it: C5 sees every zone reachable (a stub is part of the HALL
zone), C7 sees the door placeable, C11 sees the walk clear, C14 checks corridor width only, C16
sees the door on the wall of the room it names; `hub_guard`/`l_massing_guard` score aspect,
wet adjacency, area and exposure — no entrance-sequence term
(`backend/app/vertical_slice/general_pipeline.py:858`: "Entrance-sequence quality is a
separate, un-gated follow-up"). `DesiredAccessTopology` is deliberately interior-only
(`validation.py:366-367`); the entrance is resolved at site level. Issue #20 (C23) decides
WHICH room the door opens into; it does not decide where the corridor ends or whether the
entrance meets a circulation node. Evidence: read-only geometry domain-lead report
`.agent/proposals/p0/06-entrance-circulation-integration.investigation.json` (2026-09-17).

### Required behavior

0. **Reproduce first (phase 1, same PR).** A project-authored sweep
   (`backend/scripts/entrance_sequence_sweep.py`) runs the frozen regression corpus
   (`backend/tests/regression_corpus/corpus.json`, 432 contexts) and the geometry fixtures and
   reports, per shown plan: arrival zone, corridor stub length beyond the door (pocket), distance
   from the door to the first public opening, private/service doors passed before it, foyer flag.
   Its output (`docs/ENTRANCE_CIRCULATION_SWEEP.md`) names the contexts that show the owner's
   failure shape; the worst one becomes the failure fixture for the tests below. The fix in
   steps 1–4 is implemented only after this report exists.
1. **Topology first, in the engine.** The corridor's endpoint is derived from the last door it
   must serve (its access topology), never from the footprint boundary: in the spine parti the
   `HALL` leaf stops at the last served room (or becomes entrance segment + corridor), in the L
   parti the seam hall does not run past its last door toward the street. A corridor segment
   that serves no door is not generated. This is an engine change (`concept_generator.py`,
   `l_parti.py`, `doors.py`), NOT a demo-contract post-process: the corridor-opening guardrail
   (`docs/PROJECT_STATE.md`, `_open_corridor_to_public`) covers visual wall openings and stays
   as it is; the validator must see the fixed geometry. `DesiredAccessTopology` stays
   interior-only — the entrance→circulation rule lives beside `resolve_entrance` on realized
   geometry (the §5.1 recommendation).
2. **Entrance/transition zone.** The zone the front door opens into is a circulation node: it
   has at least one further opening to a PUBLIC-group room or open zone. When the arrival room
   is the corridor, the entrance segment is a junction, not a stub ending at a wall. A
   deliberate foyer (a HALL zone with its own program area, declared by the concept) stays valid
   and is never reported as a pocket.
3. **Detection.** New validator check **C25 "no dead-space pocket at the entrance"**
   (`backend/app/vertical_slice/validation.py`, SITE group, after C16): fails when the corridor
   continues past the entrance door toward the façade for more than `ENTRANCE_POCKET_MAX_M`
   (default 0.6 m, PARAMETER · UNVERIFIED, documented) without a door, or when the arrival zone
   has no opening to a public room/open zone. Fails closed on the product path (demo refusal
   code `ENTRANCE_DEAD_END`, same policy as C23). The tunnel condition — first public opening
   farther than `ENTRANCE_TUNNEL_MAX_M` (default 4.0 m, same status) with only private/service
   doors before it — is a **non-blocking** quality signal and a candidate tiebreak
   (`hub_guard`-style, never blocks a plan), because the fix for tunnels is a parti change (P2
   "Entrance Sequence Quality"), and a blocking check there would violate LOST = 0. Recorded
   decision; the owner may change it before approving.
4. **Quality signal.** `QualityOut` gains an additive `entrance_sequence` report: arrival zone,
   pocket length, distance to the first public opening, private doors passed, foyer flag.
5. **Generic.** The rule is expressed on the access topology and realized geometry (works for
   rectangular and L massings, both hall partis, mirrored/translated plans); no coordinate
   literals or fixture-specific branches. Not bundled with massing/quality work (root causes
   stay separate, per the L-massing investigation §5.1).

### Acceptance Criteria

- AC-1: the sweep report exists, lists every corpus context and fixture with a pocket or a tunnel (counts by parti), and names the failure fixture used by the tests
- AC-2: on the failure fixture the generated plan has no wall segment directly in front of the entrance door and no corridor stub beyond the door; C25 passes
- AC-3: the corridor endpoint equals the last served door's extent (± wall thickness) and not the footprint boundary, in the spine parti and in the L parti
- AC-4: the arrival zone is a circulation node: the realized access graph shows door → arrival zone → a public opening, on the canonical fixture and on the failure fixture
- AC-5: C25 fails on a hand-built fixture with a 1.5 m dead stub beside the entrance and names the stub length; the demo path refuses with ENTRANCE_DEAD_END
- AC-6: the tunnel fixture (5 m of corridor with only bedroom doors before the first public opening) is reported in `entrance_sequence` and ranked below its non-tunnel sibling, and is NOT refused
- AC-7: an intentional foyer fixture (declared HALL with program area) passes C25 and keeps its foyer
- AC-8: no accessibility regression: the realized-connectivity, concept-and-site, demo entrance, L-parti and hub tests stay green; the corpus shows LOST = 0, crashes 0, no status or refusal-code changes
- AC-9: the same fix holds on mirrored and translated variants of the failure fixture (parametrized test), and the diff contains no coordinate literal or fixture-name branch
- AC-10: every primary-signature change on the corpus is listed in the PR with its before/after entrance sequence and is entrance/circulation-affected; unexpected changes = 0
- AC-11: the Wiki documents C25, the entrance-sequence topology, the blocking/non-blocking split and both PARAMETER · UNVERIFIED constants

### Out of scope

Furniture, decorative foyer design, lighting, structural walls, full accessibility code
compliance, door styling/rendering, the arrival-room policy itself (#20), L-orientation
eligibility ordering (recorded follow-up).

### Affected domains

backend, geometry, validator, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#20

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> file:docs/ENTRANCE_CIRCULATION_SWEEP.md ; file:backend/scripts/entrance_sequence_sweep.py
- AC-2 -> pytest:backend/tests/vertical_slice/test_entrance_circulation.py::test_no_dead_end_wall_in_front_of_the_entrance_on_the_failure_fixture
- AC-3 -> pytest:backend/tests/vertical_slice/test_entrance_circulation.py::test_corridor_ends_at_the_last_served_door_not_at_the_boundary
- AC-4 -> pytest:backend/tests/vertical_slice/test_entrance_circulation.py::test_arrival_zone_is_a_circulation_node
- AC-5 -> pytest:backend/tests/vertical_slice/test_entrance_circulation.py::test_c25_flags_a_dead_stub_beside_the_entrance ; grep:backend/app/vertical_slice/validation.py:C25 ; grep:backend/app/demo/service.py:ENTRANCE_DEAD_END
- AC-6 -> pytest:backend/tests/vertical_slice/test_entrance_circulation.py::test_tunnel_sequence_is_reported_and_ranked_down_but_not_refused
- AC-7 -> pytest:backend/tests/vertical_slice/test_entrance_circulation.py::test_intentional_foyer_passes_c25
- AC-8 -> pytest:backend/tests/vertical_slice/test_realized_connectivity.py ; pytest:backend/tests/vertical_slice/test_concept_and_site.py ; pytest:backend/tests/test_demo_p0.py::test_the_entrance_never_opens_into_a_bedroom_or_a_bathroom ; pytest:backend/tests/test_demo_p0.py::test_the_realization_of_the_entrance_is_checked_not_assumed ; pytest:backend/tests/vertical_slice/test_l_parti.py ; pytest:backend/tests/vertical_slice/test_concept_generator.py ; regression:corpus
- AC-9 -> pytest:backend/tests/vertical_slice/test_entrance_circulation.py::test_fix_holds_on_mirrored_and_translated_fixtures ; review:the diff has no coordinate literals or fixture-name branches in concept_generator/l_parti/doors/validation
- AC-10 -> regression:corpus ; review:the PR lists every primary-signature change with its before/after entrance sequence and each is entrance/circulation-affected
- AC-11 -> grep:docs/wiki/architecture/geometry-validation.md:C25

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 40

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (C25, entrance-sequence topology, blocking vs
non-blocking split, constants); docs/ENTRANCE_CIRCULATION_SWEEP.md (new report);
docs/PROJECT_STATE.md (refusal code, corridor-endpoint rule next to the corridor-opening guardrail).

### Knowledge check

Consulted: `docs/ROADMAP.md` (P0 entrance topics), `docs/wiki/architecture/geometry-validation.md`,
`docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md` §5.1 (entrance-sequence defect,
deferred), `app/vertical_slice/doors.py` (`resolve_entrance`, `ENTRANCE_ZONE_PRIORITY`),
`app/vertical_slice/level_planner.py` (corridor spans the full depth), `validation.py` (C5, C7,
C11, C16 — none sees a pocket), the guest-WC spec's `EntranceZone`/`Pocket` vocabulary
(`specs/009-guest-wc-placement`), RAG search "entrance corridor dead-end wall pocket circulation
node foyer", `general_pipeline.py:858`, `app/demo/contract.py:514-516`, `PROJECT_STATE.md`
corridor-opening guardrail, and a read-only geometry domain-lead investigation
(`.agent/proposals/p0/06-entrance-circulation-integration.investigation.json`; citations
re-verified against the code on 2026-09-17).
What exists: geometry-derived entrance placement with placeability/walk/label gates; the
arrival-room policy is Issue #20. What remains (this Issue): corridor endpoint from topology,
an entrance→circulation-node rule, pocket/tunnel detection (C25), the quality signal, and the
generic fix. Nothing here is already implemented, so the Issue is opened for execution (not
closed as done).
