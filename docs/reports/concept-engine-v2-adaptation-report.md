# Concept Engine v2 — concept adaptation report (Issue #76)

Offline measurement of the bounded realize-measure-adapt loop's first rung, over the frozen 432-context regression corpus's PLANNED cases: for each brief's FIRST realized candidate (generator order, before ranking/selection), whether `concept_score` already accepts it, `adapt` names a target concept that another already-realized candidate for the same brief already matches (`adapted`), or neither (`dropped`). No runtime behavior change — see `app.vertical_slice.concept_score` and `spikes/failure_log_sweep/concept_adaptation_report.py`.

- PLANNED briefs measured: 404

## Per circulation class: accepted / adapted / dropped

- FRONT_BAND: accepted=52
- SPINE: accepted=352

## Score deltas where a sibling was found (`adapted` cases)

- none in this corpus — see the per-class counts above.

Every brief's first realized candidate was already `accepted` on this frozen corpus — the ladder never had a case to bite on here. `run_general`'s existing candidate ordering and validation (C24/C19 among them) already reject or reorder away most of what `adapt` would otherwise be asked to fix before the FIRST candidate this measurement looks at is even reached; a corpus of harder or adversarial briefs — or a caller that measures every ATTEMPTED candidate, not only the first — is where `adapted`/`dropped` counts would first appear. No HUB_LOBBY or TWO_WING first candidate appears either, consistent with Issue #75's diversity baseline (`concept-engine-v2-diversity-baseline.md`): a hub-lobby plan never yet sizes within the hard template maxima on this corpus, and a two-wing candidate is never the FIRST one the generator tries.

