"""The drawing audit's RASTERISER (#213's harness, `investigate/preview-comparison`).

Copied here by Issue #223, deliberately as the two files that do the drawing and nothing else:

* `rasterise.mjs` — loads the product's own stylesheets into a real chromium and screenshots the
  SVG `frontend/src/design/drawing-audit-render.test.tsx` renders from a `DemoDesign` payload
  through `DemoPlan` + `PlanLegend`. The figure is the product's renderer; there is no harness
  drawer anywhere in it.
* `figures_223.py` — the one brief, two payloads (parcel carried / parcel absent) #223's
  before/after pair needs.

#213's own `run.py` analysis harness and `comparison_corpus/` were NOT copied: #223 measures the
site from the payload directly (`tests/demo/test_site_from_brief.py`) and needs only the drawing.
"""
