# Toilet as a fixture, WC as a room — before/after on the corpus

Measured 2026-09-15/16 with `measure.py` (offline) and `measure.py --live` (real gpt-5-nano), on
`tests/wet_room_corpus/corpus.json`: the 61 distinct wet-room briefs behind 95 stored projects,
hand-labelled. Re-run both before changing a claim here.

## What changed (Phases 0–3)

- The model no longer returns a wet-room COUNT. It returns `FixtureDemand` — bathrooms named on
  their own, wet rooms attached to a bedroom (`bath` / `toilet_only`), toilets named as rooms, and
  bare "שירותים" mentions — and `requirements/wet_room_normalizer.py` turns that into rooms by
  rule (R1–R5). `wet_rooms` is the length of the list.
- A toilet is a fixture every bathroom already holds; only the surplus becomes a `GUEST_WC`, and
  such a room is `origin=count_derived`. A room the person named is `explicit`. The tag travels
  to the record, the resolved room and the review screen ("נגזר מהספירה: שירותים").
- "חדר הורים עם שירותים" is NOT an ensuite: no shower is invented. It is a stored question
  (`ATTACHED_TOILET_ONLY`) that blocks generation and proposes an ensuite; "N שירותים" with no
  bathroom word and N ≥ 2 is `TOILETS_WITHOUT_BATHROOM`, proposing one bathroom + N−1 WCs.
- I4 (a bedroom with no bathroom it can reach) now carries a one-click proposal, "add a shared
  bathroom", completed by `wet_rooms.complete_with_shared_bathroom`.
- Untouched: `default_wet_room_kinds`, room templates, C17/C19, Geometry Core. Laundry not built.

## Gate: existing records are byte-identical

All 95 stored wet-room records regenerated after the change: the 37 that planned produce the
identical primary plan and alternatives (every room id, type, area, dimensions); the 57 that
refused refuse with the identical code.

## Offline: the labelled demand through the new pipeline, planned on the same records

37 records planned before. After: 25 plan, 11 become a question, 1 refuses elsewhere (parking C11
once the requested WC and shared bathroom are both built).

On the 25 that plan both ways:

| | before | after |
|---|---|---|
| wet rooms exactly the brief's functions | 11/25 | **25/25** |
| surplus full bathrooms (m²) | 12 (102 m²) | **0** |
| requested WC missing | 6 | **0** |
| TOILET rooms built (m²) | 8 (39 m²) | 14 (75 m²) |
| wet-room area, mean per plan | 16.2 m² | 12.8 m² |

TOILET rooms went UP — every one of the 14 is asked for (5 explicit guest WCs, 9 surplus
toilets); none exists for a toilet a bathroom already holds. The 11 questions: 7 × "חדר הורים עם
שירותים" (silently planned as ensuite + full bathroom before) and 4 × I4 for "ensuite + guest WC"
with 2–4 other bedrooms (silently given a second full bathroom before). Each now shows its
proposed answer.

## Live: the real model on all 61 briefs

Per-brief output in `live.json`.

gpt-5-nano, default settings (the production parser's), ~40 s per brief; 61 briefs + 15 stability
re-parses on 2026-09-16.

| | before (old count parser, stored) | after (FixtureDemand → normalizer) |
|---|---|---|
| bath + toilet briefs where every toilet became a room | 16/29 records (55%) | 0/61 briefs |
| `FixtureDemand` matches the hand labels | — | 55/61 (90%) |
| rooms match the labelled rooms | 41 % of P2+P3 records | 57/61 (93%): P1 16/16, P2 10/10, P3 9/10, P4 10/13, P5 12/12 |
| questions raised exactly as labelled | — | 61/61 |
| same text, different rooms on re-parse | 7 of 15 repeated briefs | 0 of the 5 worst (3 parses each) |

The four room misses, all in the two classes with the most wording variety:

- [30] "חדר הורים עם מקלחת ושירותים, **ועוד שירותים**": the additional toilet was filed as a bare
  mention (absorbed) instead of a separate WC — the person's extra toilet is dropped.
- [46] "חדר הורים עם מקלחת, מרפסת, **2 שירותים**": the two toilets were filed as separate WCs —
  one WC more than the absorbing reading (the brief is genuinely ambiguous; the labels chose
  absorption).
- [52], [53] "חדר הורים עם מקלחת, שירותי אורחים": the master's shower was ALSO listed as a
  standalone bathroom — one full bathroom more than the brief names. It happens to be the answer
  I4 would have proposed, but it was not asked for.
- [31], [45] "מקלחת שירותים" with no comma: the toilet mention was missed; harmless, since it is
  absorbed either way.

Both directions of error remain visible: a dropped room shows on the review list, an invented one
is labelled with its (empty) source text. None of the 61 turned a fixture into a room on its own.

## Backstop: extraction consistency (2026-09-16, pre-merge)

`wet_room_normalizer.extraction_mismatches` holds the model's demand against a few strong phrases
in the raw brief — guest / additional / separate WC, a bathroom word, wet-room wording attached to
a bedroom, an explicit "N שירותים" — and against the numbers the text writes. A phrase with no
entry behind it, an entry with no phrase behind it, or a count nobody wrote is an
`EXTRACTION_MISMATCH` question: the rooms stored are exactly what was extracted, the proposal
shows the likely reading, and generation waits. A bare "שירותים" on its own is never converted.
Counts from the model are clamped (`MAX_COUNT`); the model was seen to emit absurd counts in 2 of
30 repeat parses.

| | result |
|---|---|
| labelled corpus (61), consistent demand → false questions | 0 |
| empty extraction on a wet-word brief → passes silently | 1 of 61 (a lone bare "שירותים" — by design; the legacy path gives it its one bathroom) |
| live 61 (same extractions as above, re-scored) — silent under-extractions | **0** (was 1: the dropped "ועוד שירותים") |
| live 61 — silent over-extractions | **0** (were 3) |
| live 61 — converted to clarification | **4** (briefs 30, 46, 52, 53); correct extractions questioned: 0 |
| live repeatability, 5 briefs × 3 parses | 15 calls, 1 wrong room list (a nine-bathroom count for one "מקלחת") → converted, 0 silent |
| backward compatibility | stored records never pass through the check; on the same planner, plans and refusals with vs. without this work: 94/94 identical (37 plans byte-identical incl. alternatives, 57 refusal codes) |

The differential gate above is the honest one: the working tree also carries unrelated planner
edits (`concept_generator.py` fallback gating, `geometry_core/engine.py`) made during this work,
which move the geometry of 4 of the 37 baseline plans on their own; the wet-room programme (room
ids and kinds) of all 37 is unchanged either way.
