"""Production's SELECTION questions asked of the cross-band layouts BEFORE anything is sized
(`band_pipeline.placement_flags` asks them of a band candidate): can an allowed arrival room front
the street, does a foyer front it, does every REQUIRED-exposure room and the safe room have an
exterior wall. And the two orientation helpers: bands across the street are the same algorithm on
the transposed envelope, transposed back."""
from __future__ import annotations

from app.vertical_slice.envelope import Envelope
from app.vertical_slice.geometry_core.model import Rect


def cells_selection(layout, zones, orient_tag: str) -> list[str]:
    """Production's SELECTION questions for a cell layout (cf. `_spine_selection`): an arrival
    room can front the street; every REQUIRED-exposure room and the safe room has an exterior
    wall — a cell is exterior when it is first or last in one of its rows, in row 0, or in the
    last row (bands along the street); across the street (V) the street wall is the left edge."""
    from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
    from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
    from app.vertical_slice.geometry_core.model import ProgramRole
    role = lambda z: getattr(zones[z], "role", None)
    failed = []
    R = layout.n_rows
    fronting = set(layout.rows[0]) if orient_tag == "H" else {row[0] for row in layout.rows}
    if not any(role(z) in ALLOWED_ENTRANCE_ROLES for z in fronting):
        failed.append("entrance_feasible")
    foyers = [z for z in layout.zones if role(z) is ProgramRole.CIRCULATION]
    if foyers and not any(z in fronting for z in foyers):
        failed.append("foyer_fronts_street")
    exterior = set(layout.rows[0]) | set(layout.rows[-1])
    for row in layout.rows:
        exterior.add(row[0]); exterior.add(row[-1])
    buried = [z for z in layout.zones
              if (role(z) in REQUIRED_EXTERIOR_ROLES or role(z) is ProgramRole.SAFE_ROOM) and z not in exterior]
    if buried:
        failed.append("exposure_ok")
    return failed
def spine_selection(layout, zones, orient_tag: str) -> list[str]:
    """The production SELECTION questions for a spine layout, before any geometry is sized — the
    HARD flags `placement_flags` asks of a band candidate, read off the layout's structure:

    entrance_feasible — can an allowed arrival room front the street? Bands along the street (H):
    the embedding already guarantees it (a spine that fronts is three door widths wide, else the
    street band holds an arrival room). Bands across the street (V): the street wall is the layout's
    LEFT edge, so the outermost-left cells front it — a section band with no left part puts the
    spine's long wall there.
    exposure_ok — every REQUIRED-exposure room (and the safe room) has an exterior wall: the outer
    cell of a side row, any cell of the top/bottom plain band, the end cells of a plain band, or a
    cell in the section's first/last row when nothing sits above/below it. A room inside a side row
    of a middle band is buried, as in the band family; it is skipped, not sized and refused."""
    from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
    from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
    from app.vertical_slice.geometry_core.model import ProgramRole
    failed = []
    role = lambda z: getattr(zones[z], "role", None)
    if orient_tag == "V":
        fronting = {band[0] for band in layout.top + layout.bottom}
        for left, _right in layout.bands:
            fronting.add(left[0] if left else layout.spine)
        if not any(role(z) in ALLOWED_ENTRANCE_ROLES for z in fronting):
            failed.append("entrance_feasible")
    # a FOYER (a CIRCULATION room off the spine with at most one other neighbour — the brain's
    # degree-2 ENTRY) exists to hold the front door: it must front the street, else the parti's
    # point is lost (the door would open into the living room and the foyer float at the back)
    foyers = [z for z in layout.cells if z != layout.spine and role(z) is ProgramRole.CIRCULATION]
    if foyers:
        if orient_tag == "H":
            fronting = set(layout.top[0]) if layout.top else set()
        if not any(z in fronting for z in foyers):
            failed.append("foyer_fronts_street")
    exterior = {layout.spine}
    for band in layout.top + layout.bottom:
        exterior.update(band[0:1]); exterior.update(band[-1:])
    if layout.top:
        exterior.update(layout.top[0])
    if layout.bottom:
        exterior.update(layout.bottom[-1])
    for r, (left, right) in enumerate(layout.bands):
        exterior.update(left[0:1]); exterior.update(right[-1:])
        if (r == 0 and not layout.top) or (r == len(layout.bands) - 1 and not layout.bottom):
            exterior.update(left); exterior.update(right)
    buried = [z for z in layout.cells
              if (role(z) in REQUIRED_EXTERIOR_ROLES or role(z) is ProgramRole.SAFE_ROOM) and z not in exterior]
    if buried:
        failed.append("exposure_ok")
    return failed
def transposed_envelope(env: Envelope) -> Envelope:
    return Envelope(tuple((y, x) for x, y in env.vertices_m))
def transpose_rects(rects: dict) -> dict:
    return {z: Rect(r.y, r.x, r.h, r.w) for z, r in rects.items()}
