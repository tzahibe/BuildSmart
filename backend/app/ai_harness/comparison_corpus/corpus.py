"""THE CORPUS (#213): 26 briefs, each labelled by the ENVELOPE FAMILY it exercises, each with the
file it came from. Nothing here is invented — every brief is one the repo already carries.

Two sources, and the difference between them is the whole point:

* `real` — the 20 briefs of `app/ai_harness/topology_poc/briefs.py` (`select_briefs()`, the
  deterministic selection off the real corpus). These are what the PRODUCT can actually receive:
  `Project.selected_footprint` is a width x depth rectangle and `demo/scope.py:362` refuses any
  other `shape_type`, so every real brief's envelope is a rectangle and the families they cover
  are rectangle families (square, rectangular, wide, narrow/deep).
* `frozen` — the six declared cases of `docs/reports/shape-agnostic-realizer/cases/frozen-six.json`,
  which carry ORTHOGONAL POLYGON envelopes (L, wide-shallow strip, entry-court notch, garden
  court). They are the only non-rectangular envelopes in the repo. The product cannot be handed
  one of these at all (same two lines above), which is a RESULT, not a gap in the corpus.

`family` is assigned, not measured, so the report's table can be read without re-deriving it:
rectangles are classified by aspect (square < 1.2 <= rectangular < 1.7 <= wide/narrow), the
polygons by the shape their own frozen spec declares.
"""
from __future__ import annotations

from dataclasses import dataclass

SQUARE = "rectangular/square"
RECT = "rectangular"
WIDE = "rectangular/wide"
NARROW = "narrow/constrained"
L_SHAPE = "L-shaped"
COURT = "U-shaped/courtyard"
IRREGULAR = "irregular rectilinear"


@dataclass(frozen=True)
class Entry:
    brief_id: str
    source: str            # "real" | "frozen"
    family: str
    note: str = ""


#: Aspect bands for the rectangle families, so the label in the report is reproducible.
def rectangle_family(w: float, d: float) -> str:
    aspect = max(w, d) / min(w, d)
    if aspect < 1.2:
        return SQUARE
    if aspect < 1.7:
        return RECT if d >= w else WIDE
    return NARROW


#: The three the owner named explicitly (#213 AC-3) — the larger, denser briefs.
HEADLINE = ("B16", "B19", "B09")

FROZEN = (
    Entry("F1-rect-control", "frozen", RECT,
          "the frozen set's own rectangle control (12 x 18), so the polygon cases have a baseline"),
    Entry("F2-L-envelope-fixed", "frozen", L_SHAPE,
          "an L envelope as a fixed INPUT: a corner of the parcel is unbuildable"),
    Entry("F3-wide-shallow-free", "frozen", NARROW,
          "a 24 x 9.5 m buildable strip — the narrow/constrained extreme, still a rectangle"),
    Entry("F4-entry-court-notch", "frozen", IRREGULAR,
          "a notch on the STREET side (entry court): the arrival room must front the street in it"),
    Entry("F5-garden-court", "frozen", COURT,
          "a rear notch (garden court) the open-plan LDK must wrap — the U/courtyard case"),
    Entry("F6-unsatisfiable-K4", "frozen", RECT,
          "declared UNSATISFIABLE by representation (K4); a plan here is a FAIL by the spec's own rule"),
)


def real_entries(briefs) -> tuple[Entry, ...]:
    """The 20 real briefs, labelled by their own footprint's aspect."""
    out = []
    for b in briefs:
        note = "owner-named headline brief" if b.brief_id in HEADLINE else ""
        out.append(Entry(b.brief_id, "real", rectangle_family(b.footprint_width_m, b.footprint_depth_m), note))
    return tuple(out)
