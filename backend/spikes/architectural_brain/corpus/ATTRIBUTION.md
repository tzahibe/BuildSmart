# Attribution

This corpus is derived from **ResPlan: A Large-Scale Vector-Graph Dataset of 17,000 Residential
Floor Plans** (Abouagour & Garyfallidis, 2025, arXiv:2508.14006).

Licence: **CC BY 4.0** (data). See the original dataset's `LICENSE` file for the full grant.

Each `*.json` file in this directory is a normalised `PlanReference` derived from one ResPlan plan
(`provenance.source_plan_id` records the original ResPlan `id`) plus its `ArchitecturalPattern`.
Geometry has been rescaled to metres and re-expressed in BuildSmart's schema; no ResPlan source
images, listing text, prices, addresses or personally identifying information are included (ResPlan
itself contains none).

See `docs/reports/poc-architectural-brain/dataset.md` for the full field-by-field description.
