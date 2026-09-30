"""Issue #46 — the professional-drawing renderer never invents geometry.

The live plan drawing is entirely frontend (`frontend/src/design/DemoPlan.tsx` and the
`components/plan/*` it composes), fed by `app.demo.contract.DemoDesign` — the ONLY shape it may
read architecture from (see `DemoPlan.tsx`'s own module docstring: "This component decides NOTHING
architectural... If a fact is not on the object, it is not drawn."). `renderer.py`
(`app.vertical_slice.renderer`) is a separate, older debug PNG tool for the vertical-slice CLI, out
of the live product path — not audited here (same boundary `test_frontend_contract_audit.py`
already draws around `ArchitecturalFloorPlan.tsx`/`SketchSvg.tsx`).

This follows the exact static-audit technique `test_frontend_contract_audit.py` established for
Issue #34: grep the live renderer's own source for the pattern that proves a drawn element class is
SOURCED from a named `DemoDesign` field, and cross-check that field actually exists on the Pydantic
contract (so the manifest itself cannot silently go stale after a field rename).

AC-1's own list — walls by class, doors with arcs, windows, layout, labels, dimensions, north
arrow and scale — is covered element by element below. The one deliberate exception is the scale
bar: a drawing CONVENTION, not an architectural fact (its own length is picked from the drawing's
frame size, the same way any drawing states its own scale without the building naming one) — see
`ScaleBar.tsx`'s own docstring. It is asserted here to read NO per-room/door/window contract field,
precisely so it can never smuggle in an invented architectural fact under that exemption.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.demo.contract import DemoDesign, DoorOut, LayoutObjectOut, RoomOut, WallSegment, WindowOut


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    root = _repo_root()
    path = root / rel
    assert path.exists(), f"expected renderer file to exist: {rel}"
    return path.read_text(encoding="utf-8")


def _model_field_names(model) -> set[str]:
    return set(model.model_fields.keys())


#: One entry per AC-1 element class: the frontend file that draws it, the contract model whose
#: fields it must be reading from, and every source pattern that must appear in that file proving
#: the element's geometry/appearance comes from a NAMED field on that model, not a literal.
_ELEMENT_MANIFEST = [
    {
        "name": "walls by class",
        "file": "frontend/src/components/plan/Walls.tsx",
        "model": WallSegment,
        "fields": ["wall_class", "thickness_m", "orientation", "coord", "start", "end"],
        "patterns": [
            r"wall\.wall_class", r"wall\.thickness_m",
            r"wall\.orientation", r"wall\.coord", r"wall\.start", r"wall\.end",
        ],
    },
    {
        "name": "doors with arcs",
        "file": "frontend/src/components/plan/DoorSymbol.tsx",
        "model": DoorOut,
        "fields": ["hinge_x", "hinge_y", "swing_deg", "width_m", "orientation", "x", "y", "is_entrance"],
        "patterns": [
            r"door\.hinge_x", r"door\.hinge_y", r"door\.swing_deg", r"door\.width_m",
            r"door\.orientation", r"door\.is_entrance",
        ],
    },
    {
        "name": "windows",
        "file": "frontend/src/design/DemoPlan.tsx",
        "model": WindowOut,
        "fields": ["side", "width_m", "x", "y"],
        "patterns": [r"window\.side", r"window\.width_m", r"window\.x", r"window\.y"],
    },
    {
        "name": "layout (furniture/fixtures)",
        "file": "frontend/src/components/plan/InteriorLayout.tsx",
        "model": LayoutObjectOut,
        "fields": ["kind", "x", "y", "width_m", "depth_m"],
        "patterns": [r"obj\.kind", r"obj\.x", r"obj\.y", r"obj\.width_m", r"obj\.depth_m"],
    },
    {
        "name": "labels and dimension strings",
        "file": "frontend/src/design/demoRoomLabel.ts",
        "model": RoomOut,
        "fields": ["name", "width_m", "depth_m", "area_m2"],
        "patterns": [r"room\.width_m", r"room\.depth_m", r"room\.area_m2"],
    },
]


def test_every_element_maps_to_a_contract_field():
    """Every AC-1 element class is drawn from a field that really exists on `DemoDesign`'s own
    contract tree — never a hardcoded number standing in for one."""
    offenders: list[str] = []
    for entry in _ELEMENT_MANIFEST:
        real_fields = _model_field_names(entry["model"])
        missing_from_contract = [f for f in entry["fields"] if f not in real_fields]
        if missing_from_contract:
            offenders.append(
                f"{entry['name']}: manifest names field(s) {missing_from_contract} not on "
                f"{entry['model'].__name__} — the manifest itself is stale"
            )
            continue
        source = _read(entry["file"])
        missing_patterns = [p for p in entry["patterns"] if not re.search(p, source)]
        if missing_patterns:
            offenders.append(
                f"{entry['name']} ({entry['file']}): no reference to {missing_patterns} — "
                f"drawn without reading the field it claims to"
            )
    assert not offenders, "renderer element(s) not traceable to a contract field:\n" + "\n".join(offenders)


def test_north_arrow_and_scale_bar_read_only_orientation_and_frame_geometry():
    """The compass draws from `streetFacingSide` alone (never a room/door/window field), and the
    scale bar draws from the frame's own computed size alone (never any `DemoDesign` field) — the
    one AC-1 element deliberately exempt from the contract-field manifest above, and asserted here
    to justify that exemption instead of merely assuming it."""
    compass_ts = _read("frontend/src/design/compass.ts")
    assert "streetFacingSide" in compass_ts

    scale_bar = _read("frontend/src/design/ScaleBar.tsx")
    # The scale bar's own length comes only from `frameSizeM` — never a per-room/door/window
    # contract accessor, which is exactly what would turn a drawing convention into an invented
    # architectural fact.
    invented = re.findall(r"\b(?:room|door|window|obj)\.\w+", scale_bar)
    assert not invented, f"ScaleBar reads contract fields it should not: {invented}"
    assert "frameSizeM" in scale_bar


def test_no_north_arrow_without_orientation_and_no_plot_without_site():
    """AC-2: a design without a site orientation renders no north arrow, and a `DemoDesign`
    structurally cannot exist without real site geometry — so plot context is never invented.

    `DemoDesign.plot`/`footprint`/`garden`/`parking`/`entrance_walk` are REQUIRED fields (no
    default) on the Pydantic contract: a payload the frontend can render literally cannot be
    missing site geometry, which is what makes "no invented plot" hold by construction rather than
    by an unenforced convention.
    """
    for field in ("plot", "footprint", "garden", "parking", "entrance_walk"):
        info = DemoDesign.model_fields[field]
        assert info.is_required(), (
            f"DemoDesign.{field} must stay a required field — an optional one would let a "
            f"payload exist with no real site geometry, which the renderer could then only fill "
            f"in by inventing a plot"
        )

    # The compass rose's own null-guard: no cardinal side, no arrow, unconditionally.
    compass_ts = _read("frontend/src/design/compass.ts")
    assert re.search(r"if\s*\(typeof streetFacingSide !== ['\"]string['\"]\)\s*return null", compass_ts), (
        "compass.ts must return null unconditionally when no orientation string is given"
    )
    compass_rose = _read("frontend/src/design/CompassRose.tsx")
    assert re.search(r"if\s*\(orientation === null\)\s*return null", compass_rose), (
        "CompassRose.tsx must draw nothing when compassOrientation() found no orientation"
    )

    # The frontend never fabricates a fallback plot/garden/parking rectangle when the field is
    # absent (`?? {...}` / `|| {...}` immediately after a site-context accessor).
    demo_plan = _read("frontend/src/design/DemoPlan.tsx")
    invented_fallback = re.search(r"design\.(plot|garden|parking|entrance_walk)\s*(\?\?|\|\|)\s*\{", demo_plan)
    assert invented_fallback is None, (
        f"DemoPlan.tsx must not invent a fallback for missing site geometry: {invented_fallback}"
    )
