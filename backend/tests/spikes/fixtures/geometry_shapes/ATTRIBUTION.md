# Attribution

This fixture set is a copy of the 20-plan test fixture built for the POC Architectural Brain
(Issue #94, branch `integration/poc-architectural-brain`,
`backend/tests/architectural_brain/fixtures/`), reused here so Issue #102's measurement script has
a real, licensed, deterministic corpus committed directly on this branch — see
`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` section 3.

19 of the 20 plans (`plans/*.json` other than `synthetic-spine-01.json`) are derived from
**ResPlan: A Large-Scale Vector-Graph Dataset of 17,000 Residential Floor Plans** (Abouagour &
Garyfallidis, 2025, arXiv:2508.14006).

Licence: **CC BY 4.0** (data). See the original dataset's `LICENSE` file for the full grant.

Each `plans/<id>.json` file is a normalised `PlanReference` (see
`docs/reports/poc-architectural-brain/dataset.md` on the branch above for the full field-by-field
schema) plus its derived `ArchitecturalPattern`. `provenance.source_plan_id` on each file records
the original ResPlan `id`. `plans/synthetic-spine-01.json` is a hand-built synthetic fixture (its
own `provenance.source_dataset` is `"SYNTHETIC"`) used only to exercise the guillotine-separability
test against a known-positive control — never claimed as a real ResPlan plan.

No ResPlan source images, listing text, prices, addresses or personally identifying information are
included (ResPlan itself contains none).
