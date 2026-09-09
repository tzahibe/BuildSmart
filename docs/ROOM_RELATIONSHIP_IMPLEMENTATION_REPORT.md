# ROOM_RELATIONSHIP_IMPLEMENTATION_REPORT

```
STATUS = DONE
TESTS  = 708 backend (was 699, +9), 69 frontend (was 67, +2), tsc clean
SCOPE  = adjacency / separation / proximity / direct access only
```

`"לא רוצה חדר שינה צמוד למטבח"` used to be dropped as an unsupported request. It now reaches the
planner as structure, decides **which realized candidate is chosen**, and is checked against the
walls the plan actually has.

---

## The table

| brief | parsed relation | realized relation | result |
|---|---|---|---|
| "חדר הרחצה של ההורים חייב להיות צמוד לחדר ההורים" | MASTER_BEDROOM → ENSUITE `adjacent` (hard) | satisfied | plan produced, stated |
| "לא רוצה חדר שינה צמוד למטבח" | BEDROOM → KITCHEN `not_adjacent` (hard) | satisfied | plan produced, stated |
| "אני רוצה שהממ״ד יהיה קרוב לחדרי הילדים" | SAFE_ROOM → BEDROOM `near` (hard) | satisfied | plan produced, stated |
| "עדיף שהממ״ד יהיה קרוב לחדרי הילדים" | SAFE_ROOM → BEDROOM `near` (pref) | satisfied | plan produced, stated |
| "שירותי האורחים ליד הכניסה" | GUEST_BATHROOM → ENTRANCE `near` (pref) | satisfied | plan produced, stated |
| "כניסה מחדר ההורים לחדר הרחצה" | MASTER_BEDROOM → ENSUITE `direct_access` (hard) | satisfied | plan produced, stated |
| "המטבח חייב להיות צמוד לממ״ד" | KITCHEN → SAFE_ROOM `adjacent` (hard) | — | **`ROOM_RELATIONSHIP_NOT_FEASIBLE`** |
| "עדיף שהמטבח יהיה צמוד לממ״ד" | KITCHEN → SAFE_ROOM `adjacent` (pref) | not satisfied | plan produced, **warned** |

The last two are the same geometric request worded two ways, and they end differently. That is the
whole point.

---

## PARSER_CONTRACT

`RoomRelationship { source_role, target_role, relation, strength, source_text, ambiguous }` on
`RequirementExtraction`. `source_text` quotes the person's own words for that one relationship. A
relationship reported here must not also appear in `other_requests`.

## SUPPORTED_RELATIONS

`ADJACENT` · `DIRECT_ACCESS` · `NEAR` · `NOT_ADJACENT`, with strength `hard_requirement` or
`preference`. The prompt states that these are **not interchangeable** and specifically that `near`
must never be upgraded to `adjacent`; `test_near_is_not_quietly_upgraded_to_adjacent` pins it.

**`NEAR` has one deterministic, documented meaning**, fixed in `relationships.py`:

> the shortest path between the two rooms over the **realized access graph** is at most
> `NEAR_MAX_GRAPH_STEPS` (2) steps — out of one room, through at most one other space, and you are
> there.

Measured over `realized_connections`, the same physical evidence C5 and C13 use. Centroid distance
was considered and rejected: two rooms 3 m apart with a sealed safe-room wall between them are not
near each other in any sense a person means.

`ADJACENT` requires a shared boundary of at least `MIN_MEANINGFUL_SHARED_BOUNDARY_M = 0.9 m` — a
door's width, on the reasoning that a boundary too short to hold a door does not make two rooms
adjacent. `NOT_ADJACENT` is deliberately stricter: **any** shared boundary breaks it, because a
40 cm shared wall is not what someone asking for separation had in mind.

## ROOM_REFERENCE_RESOLUTION

Ten tokens: `MASTER_BEDROOM`, `BEDROOM`, `SAFE_ROOM`, `KITCHEN`, `LIVING`, `DINING`, `BATHROOM`,
`ENSUITE`, `GUEST_BATHROOM`, `ENTRANCE`. `ENSUITE` is derived from the concept's own access
topology (a bathroom entered from a master bedroom), and `GUEST_BATHROOM` is its complement.

A token may name **several** zones, which is not ambiguity — quantification is fixed per relation
and matches how people speak: a positive relation asks for **at least one** pair ("the safe room
near the children's rooms" — near one of them is near them), a separation asks for **every** pair
("no bedroom next to the kitchen" — one offending bedroom breaks it).

Genuine ambiguity — "החדר הגדול", a room this system has no concept of — is reported, never guessed:
the parser sets `ambiguous`, and `scope.check_supported` returns `AMBIGUOUS_ROOM_REFERENCE` naming
the phrase and listing the room names it does understand.

## AUTHORITATIVE_FIELD

`ProgramSpec.relationships: tuple[RoomRelationshipRequirement, ...]`, each with `source_role`,
`target_role`, `relation`, `strength`, `source_text` — role tokens rather than zone ids, so a
requirement stays valid whichever concept the planner picks. Built by
`requirements_view._relationships_of`; ambiguous records are excluded because they never get past
the scope gate.

## CONCEPT_INTEGRATION

**The smallest extension that works: selection, not redesign.** The generator builds candidates
exactly as before. The pipeline's existing candidate loop now measures each *realized* candidate,
passes over any that breaks a hard relationship, and among the survivors takes the one satisfying
the most preferences — with the generator's own ordering as the tiebreak, so a preference can never
promote a candidate the generator ranked lower on its own merits by more than the preference it
actually delivers. With no relationships the loop behaves exactly as before, fast path included.

One bug worth recording, because it was mine and it was subtle: assigning `solve` inside the loop
left `chosen` and `solve` out of step whenever a later candidate was rejected, and the pipeline then
measured one fixture against another's rectangles — C2 reported thousands of unassigned units.
`solve` is now set once, after the loop, from the candidate that actually won.

## REALIZED_VALIDATION

**C15 — "requested room relationships are realized."** It does not read the concept graph. It
measures shared boundaries off the realized rectangles and walks the realized access graph, through
the *same* `relationships.evaluate` the selection loop uses — so a plan cannot be selected on one
reading of "adjacent" and validated on another. Only hard relationships gate the plan; C15 does not
run at all when none were requested.

## DIRECT_ACCESS_DISTINCTION

**Adjacency is not access, and asking for one never produces the other.** `"חדר הורים צמוד לחדר
הרחצה"` asks for a shared wall; fabricating a door through it would be inventing an architectural
decision nobody made — the same class of defect as the renderer inferring doors.
`test_G_adjacency_alone_never_fabricates_a_door` compares the doors of the same plan with and
without the adjacency request and asserts the set difference is empty.

`DIRECT_ACCESS` reuses the existing mechanism rather than adding a second one: it is satisfied by a
realized connection from `validation.realized_connections` — a placeable door or a genuinely
wall-less join — which is the same evidence C5 and C13 accept.

## FEASIBILITY_BEHAVIOR

A hard relationship no candidate can realize returns `ROOM_RELATIONSHIP_NOT_FEASIBLE`, naming the
requirement in the person's terms and offering three real levers: more built area, drop one
requirement, or reword it as a preference. It says the rooms could not be arranged that way **with
this programme and this footprint** — never that no such house exists.

## PREFERENCE_BEHAVIOR

A preference never blocks. It ranks candidates, and whichever way it lands it is reported: satisfied
preferences become statements on the plan, unsatisfied ones become
`העדפה שלא התממשה: …` warnings, and the plan still passes validation.

## UI_REVIEW_BEHAVIOR

The review screen shows the understood relationships above the editable fields, each with its
strength badge:

```
דרישה מחייבת   חדר ההורים צמוד לחדר הרחצה של ההורים
העדפה          הממ"ד קרוב לחדרי השינה
```

Shown before Generate precisely so a misreading — "near" heard as "adjacent", the wrong room, a
preference read as a requirement — is catchable by the person who wrote the brief. The wording is
composed in the backend so the UI never has to author architectural language, and it carries no
solver vocabulary: no zone ids, no graph steps.

The plan screen reports the same statements alongside the validation checks.

## TEST_RESULTS

**708 backend, 69 frontend, tsc clean.** Nine new backend tests through the full real path
(parser → `POST /projects` → `/requirements` → `/review` → `/design/demo` → validation):

| Test | Case |
|---|---|
| A | hard adjacency realized — asserted by measuring the shared wall on the returned plan |
| B | separation — zero shared boundary between any bedroom and the kitchen |
| C | preference reported either way, statement or warning |
| D | hard relationship that cannot be realized → `ROOM_RELATIONSHIP_NOT_FEASIBLE` |
| E | the same relationship as a preference → plan + warning, validation still passes |
| F | ambiguous reference → `AMBIGUOUS_ROOM_REFERENCE`, quoting the phrase |
| G | adjacency fabricates no door (set difference against the same plan without it) |
| H | direct access satisfied by a real door between master and its ensuite |
| — | `near` is not quietly upgraded to `adjacent` |

Two frontend tests cover the review panel and its absence.

---

## Not done, by instruction

No 4BR, no new room types, no Geometry Core or Safe Geometry Adapter changes, no GIS/regulation, no
LLM architectural reasoning, no new spatial engine, no unrelated UI polish.

Worth naming for whenever you pick it up: relationships are honoured by **choosing** among the
candidates the generator already offers. A hard relationship none of them happens to satisfy is
refused rather than searched for — the generator is not yet steered to *construct* a layout meeting
it. That is the next capability step, and it is a generator change, not a selection one.

Stopping for review.
