# Architect Model investigation — what it could hint at the POC Architectural Brain (Issue #95)

Read-only investigation of `app/architect/` (`gateway.py`, `models.py`, `authoritative_merge.py`,
`local_gateway.py`, `real_gateway.py`, `model_schema.py`, `config.py`, `adapter.py`, `area_budget.py`).
Nothing in `app/` was changed to produce this report. See `backend/tests/architectural_brain
/test_architect_hints.py` for the proof (AC-4) that a hint contradicting an authoritative
requirement is dropped and reported, not applied.

## What the Architect Model subsystem actually is today

`ArchitectModelGateway.generate(request: ArchitectModelRequest) -> ArchitecturalSpec` is the
whole contract (`app/architect/gateway.py`). Three implementations exist:

- **`MockArchitectModelGateway`** — deterministic, rule-based, no model call. Derives a plausible
  `ArchitecturalSpec` directly from the request's typed hard constraints. Used in dev/tests as a
  stand-in, not a real prediction.
- **`LocalArchitectModelGateway`** (`local_gateway.py`) — runs the ACCEPTED, fine-tuned Architect
  Model V1 (Qwen2.5-Coder-7B-Instruct + LoRA) in-process: a real, trained model, verified against
  the fine-tuning project's own prompt/schema contract (`model_schema.py`'s `ModelRoomType`/
  `ModelZoneType`/`ModelRelationshipType` enums are a verbatim copy of the training schema).
- **`RealArchitectModelGateway`** (`real_gateway.py`) — an HTTP client to an external inference
  endpoint. Explicitly marked `WIRE PROTOCOL STATUS: UNCONFIRMED PLACEHOLDER` — no real endpoint
  has been verified against it. Not evidence of a working remote model, only of the boundary shape.

`ArchitecturalSpec` (the OUTPUT, `app/architect/models.py`) is validated: `program` (room types +
counts + areas), `zones` (named room-type groupings), `relationships` (adjacency/direct-access/
separation between room TYPES), `circulation` (one entry-room type + whether a hallway is
required). `authoritative_merge.py` then forcibly injects/corrects SAFE_ROOM and bedroom count
from BuildSmart's own hard requirements regardless of what the model said — the model has **no
SAFE_ROOM concept at all** (`model_schema.ModelRoomType` has no such value; confirmed against the
real trained vocabulary), and this is the ONE place in the whole codebase that already treats a
model's output as strictly advisory against a specific hard fact.

**`app.vertical_slice.concept_spec` (Concept Engine v2, Issue #75) already built the exact
non-authoritative hint boundary this Issue's Required Behavior 4 asks for** — `ArchitectModelHints`,
`hints_from_architect_spec`, `apply_architect_hints`, `DroppedHint`. It duck-types against
`ArchitecturalSpec`'s shape (`.circulation`, `.zones`, `.relationships`) rather than importing
`app.architect` at runtime, and `apply_architect_hints` NEVER changes an authoritative
`ConceptSpec` field — it either attaches the hint for the record or drops-and-reports it when it
contradicts what a builder already decided. This is the same precedent
`authoritative_merge.merge_authoritative_requirements` sets. **This investigation's conclusion is
that this existing machinery, not a new one, is what should carry Architect Model hints into the
POC's retrieval/synthesis/adaptation pipeline** — see "What to build" below.

## Which of the five candidate hint uses the gateway could serve

| Candidate use | Can the gateway serve it? | Basis |
|---|---|---|
| **Brief interpretation** (turning free text into structured facts) | **No, not from this gateway.** `ArchitectModelRequest.brief` is already a `str` — the gateway is fed AFTER interpretation (Feature 02's requirement parser does that job), not before it. The model never sees raw user text through this boundary. | `ArchitectModelRequest.brief: str` (`models.py`) |
| **Zoning suggestion** (which rooms group into a public/private zone) | **Yes, as a hint.** `ArchitecturalSpec.zones` is exactly a named room-type grouping. `MockArchitectModelGateway` already emits `"public"`/`"private"` zones from bedroom/safe_room presence; the real (local) gateway emits the trained model's own zone vocabulary via `model_schema.ModelZoneType`. | `ArchitecturalSpec.zones: list[Zone]` |
| **Relationship suggestion** (which room types should be adjacent/near/separated) | **Yes, as a hint.** `ArchitecturalSpec.relationships` is a list of typed `AdjacencyConstraint`/`DirectAccessConstraint`/`SeparationConstraint`, already the same vocabulary `Brief.program.relationships` (`app.vertical_slice.spec.RoomRelation`) partially overlaps with (ADJACENT/DIRECT_ACCESS have a direct match; the model's `SEPARATED` maps to `NOT_ADJACENT`). | `ArchitecturalSpec.relationships: list[RelationalConstraint]` |
| **Choosing among retrieved patterns** (which of the k references best fits) | **No.** The gateway has no concept of a corpus, a `RetrievedReference`, or a ranking over several candidate plans — its output is one `ArchitecturalSpec` per request, generated from a brief+site+constraints, never a choice among externally supplied options. Repurposing it for this would mean a new prompt/response contract this Issue's scope (`no new fine-tuning`, `no changing app/`) forbids building. | `ArchitectModelRequest`/`ArchitecturalSpec` shape (`models.py`) — no corpus-relative field exists |
| **ConceptSpec hints** (circulation style / entry room) | **Yes, already implemented.** `hints_from_architect_spec` reads `ArchitecturalSpec.circulation` (`requires_hallway` -> `"SPINE"`/`"OPEN"`, `entry_room_type` -> `concept_hint`) into `ArchitectModelHints`, and `apply_architect_hints` attaches or drops it against an authoritative `ConceptSpec.circulation_class`. | `app.vertical_slice.concept_spec.hints_from_architect_spec`/`apply_architect_hints` |

**Net: 3 of 5 candidate uses are servable (zoning, relationship, ConceptSpec hints), all
non-authoritative; brief interpretation is out of the gateway's boundary entirely; choosing among
retrieved patterns would need a new contract this Issue does not build.**

## Non-authoritative, no fine-tuning: how this actually holds

Every one of the three servable uses above is a HINT, never a fact this POC's own pipeline would
compute differently because of it:

- **Zoning**: `retrieval.py`'s `public_private_org` term and `patterns.py`'s `zoning` field are
  computed from measured `PlanReference` geometry (area-weighted centroids, entrance-side
  alignment) — a model's `Zone` guess could only ever be an ADDITIONAL, separately-labelled
  annotation next to that measured fact, never a replacement for it.
- **Relationships**: `Brief.program.relationships` (`app.vertical_slice.spec
  .RoomRelationshipRequirement`) is the authoritative source `retrieval.py`'s `adjacency` term
  already scores against (Required Behavior 1). A model-suggested relationship could be surfaced
  as a SOFT addition a person could accept into their brief, but must never silently become part
  of `Brief.program.relationships` itself — the same "requirements always win" rule
  `authoritative_merge.py` already enforces for SAFE_ROOM/bedroom count.
- **ConceptSpec hints**: this is `apply_architect_hints`'s existing job, verbatim, and it is
  provably safe — see `test_architect_hints.py`: a hint that contradicts the authoritative
  `circulation_class` a builder already decided is DROPPED and appears in the returned
  `DroppedHint` list, never silently applied.

No fine-tuning is proposed or needed here: `LocalArchitectModelGateway` runs the ALREADY-fine-tuned
Architect Model V1 as-is; nothing in this investigation asks for a new training run, a new prompt
template, or a change to `model_schema.py`'s vocabulary.

## What to build (not built in this Issue — Realization/C is out of scope)

If this POC continues past the spike, the concrete integration is: construct an
`ArchitectModelRequest` from a `Brief`+`PlotSpec` (translating `ProgramSpec` into
`RequiredRoomConstraint`s, roughly what `app/demo/requirements_view.py` already does for the live
product), call an `ArchitectModelGateway`, convert the response with the EXISTING
`hints_from_architect_spec`, and thread the resulting `ArchitectModelHints` through
`synthesis.ConceptSpec` the same way `app.vertical_slice.concept_spec.ConceptSpec.architect_hints`
already does — reusing the pattern, not inventing a parallel one. This is explicitly NOT
implemented in this Issue (spec/synthesis/adaptation.py carry no gateway call); the investigation's
deliverable is this report plus the proof test, not the wiring itself.
