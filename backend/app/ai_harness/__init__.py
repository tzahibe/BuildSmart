"""Non-production AI research harness (Issue #151 and successors).

Nothing under this package is imported by `app.demo`, `app.vertical_slice`, `app.requirements`,
`app.geometry*` or any UI-facing router — see each subpackage's own module docstring for its own
"no product path changes" statement. This mirrors `app/knowledge/`'s own measurement-only modules
(e.g. `adjacency_priors_fullcorpus.py`): real code, committed, tested, but never wired into the
generator/validator/realizer/ranking path.
"""
