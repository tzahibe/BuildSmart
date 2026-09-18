"""Reference benchmark (Issue #32): per rubric-section, deterministic findings for one realized
plan, compared against the matching-footprint-family entries of the curated reference-plan index
(`docs/architecture_reference/references/index.json`).

    benchmark(design, references) -> BenchmarkReport

`design` is duck-typed against `app.demo.contract.DemoDesign`'s shape, the same convention
`quality_metrics.py` already uses: `.rooms` (`.id`, `.type`, `.width_m`, `.depth_m`, `.area_m2`),
`.walls` (`.boundary_context`, `.room_ids`), `.open_interfaces` (`.room_ids`), `.doors` (`.a`, `.b`,
`.is_entrance`), `.windows` (`.room_id`, `.width_m`), `.footprint` (`.width_m`, `.depth_m`), and
optionally `.outline` (`.shape`) and `.validation` (`.checks`, a dict of check-id -> bool). Nothing
here mutates or re-validates the design — it only reads realized geometry that already exists.

`references` is the `entries` list from `references/index.json` (or an equivalent list of dicts
with the same keys: `id`, `footprint_family`, ...). Comparison uses ONLY those metadata fields and
ratios derived from them — never the reference plans' own geometry, which the V1 set does not even
carry on disk (every entry today is `rights: "metadata-only"` — see that directory's README).

Six rubric sections have a deterministic signal today. They are lettered exactly as Issue #32's
own contract text names them — A, B, C, H, K, L — which is a DIFFERENT lettering than
`docs/architecture_reference/quality_rubric.md`'s own A-O sections use for the same or adjacent
topics (that document's A is Room Proportion, not Entrance; its H is Entrance, not Exposure; and
so on). The two schemes share only the letter, not the topic, at these six positions — this
module's docstring and `docs/architecture_reference/quality_rubric.md`'s own updated text are the
disambiguation. `benchmark()` still returns one `SectionFinding` per full rubric section (A-O, 15
entries) so a caller never has to guess which sections exist; the nine NOT measured here
(D, E, F, G, I, J, M, N, O) use `quality_rubric.md`'s own titles at those letters, since none of
those nine collide with the six this module defines its own way.

    A  entrance    — does the entrance open into a public/circulation room (arrival zone)
    B  circulation — dedicated circulation area, its share of the plan, and corridor length;
                     `reference_range` is the matching-family entries' own `total_area_sqm`
                     (min, max) — genuinely computed from `references/index.json`, not merely
                     attributed to it (see `CIRCULATION_ENGINEERING_FLOOR_RATIO`'s own docstring
                     for why the circulation-SHARE floor itself stays a fixed constant instead)
    C  zoning      — is each of PUBLIC / PRIVATE / SERVICE a spatially contiguous group
    H  exposure    — share of daylight-required rooms that got a window (C8's own data)
    K  dead space  — residual interior area (C2; always 0 today — a correctness floor, not a band)
    L  consistency — how far each room's declared area_m2 sits from its own width_m x depth_m
                     (net finished area vs. gross rect — expected to differ a little by wall
                     thickness; reported as a measured fact, not a pass/fail gate)
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from app.vertical_slice import quality_metrics as qm
from app.vertical_slice.windows import DAYLIGHT_ROLES

if TYPE_CHECKING:
    from app.demo.contract import DemoDesign

PRIVATE = ("BED", "MASTER", "SAFE", "STUDY", "DRESSING")
SERVICE = ("BATH", "TOILET", "LAUNDRY", "STORAGE")

#: A FIXED engineering floor, not derived from `references/index.json` (whose schema carries no
#: circulation field at all) — the documented census band M3 (circulation share) already sits
#: inside on today's corpus, 8-14% of total plan area
#: (`docs/wiki/architecture/geometry-validation.md`). Used ONLY to decide the "high relative
#: dedicated circulation" finding's wording (AC-2); section B's `reference_range` (AC-3) is a
#: SEPARATE, genuinely entry-derived figure — see `_matching_family_area_range_m2` — because this
#: constant itself cannot vary by footprint family (the census it comes from was never segmented
#: that way, and no field in the index carries a circulation number to compute one from).
CIRCULATION_ENGINEERING_FLOOR_RATIO = (0.08, 0.14)

#: Every daylight-required room having a window is the expectation this benchmark holds a plan to
#: (C8 gates on exactly this set, `app/vertical_slice/windows.py::DAYLIGHT_ROLES`) — not a band.
EXPOSURE_REFERENCE_RATIO_RANGE = (1.0, 1.0)

#: `quality_rubric.md`'s own titles for the nine sections this benchmark does not measure — kept
#: verbatim so a reader can find the matching rubric prose. None of these nine letters collide with
#: this module's own A/B/C/H/K/L (see module docstring).
_NOT_MEASURED_TITLES = {
    "D": "Circulation Efficiency & Compactness",
    "E": "Circulation Topology & Access Sequence",
    "F": "Wet-Room Adjacency & Plumbing Efficiency",
    "G": "Public-Zone Contiguity & Open-Plan Coherence",
    "I": "Doors & Access Topology",
    "J": "Adjacency & Privacy Zoning",
    "M": "Multi-Level Vertical Coherence",
    "N": "Fixture & Clearance Awareness",
    "O": "Site & Orientation Fit",
}

_SECTION_ORDER = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O")


@dataclass(frozen=True)
class SectionFinding:
    """One rubric section's result. `measured=False` sections carry no `value`."""

    section: str
    title: str
    measured: bool
    value: Any = None
    #: (low, high), or `None` when no numeric band applies to this section.
    reference_range: tuple[float, float] | None = None
    #: `references/index.json` entry ids this section's reference comparison is attributed to.
    reference_entries: list[str] = field(default_factory=list)
    finding: str = ""


@dataclass(frozen=True)
class BenchmarkReport:
    footprint_family: str
    sections: list[SectionFinding]

    def section(self, code: str) -> SectionFinding:
        return next(s for s in self.sections if s.section == code)


# --------------------------------------------------------------------------- footprint family


def classify_footprint_family(design: "DemoDesign") -> str:
    """A simple, deterministic heuristic over the realized footprint — never geometry from a
    reference plan, only this plan's own `footprint`/`outline`. `"irregular"` is never returned:
    the engine has no massing capability that would produce one today (see the module docstring's
    scope note); it exists in the enum purely because `references/index.json` documents it as a
    family of real professional plans.
    """
    outline = getattr(design, "outline", None)
    if outline is not None and getattr(outline, "shape", "RECTANGLE") == "L":
        return "L"
    fp = design.footprint
    w, d = fp.width_m, fp.depth_m
    ratio = max(w, d) / max(min(w, d), 1e-6)
    if ratio <= 1.15:
        return "rectangle"
    return "wide-rectangle" if w >= d else "narrow-deep"


def _matching_entries(references: list[dict], footprint_family: str) -> list[dict]:
    return [e for e in references if e.get("footprint_family") == footprint_family]


def _matching_family_area_range_m2(entries: list[dict]) -> tuple[float, float] | None:
    """The (min, max) `total_area_sqm` among these (already footprint-family-filtered) entries —
    a reference range genuinely COMPUTED from `references/index.json`'s own metadata field, not a
    constant merely attributed to the entries for citation. `None` when no entry matches."""
    areas = [e["total_area_sqm"] for e in entries if "total_area_sqm" in e]
    return (min(areas), max(areas)) if areas else None


# --------------------------------------------------------------------------- adjacency (zoning)


def _physical_adjacency(design: "DemoDesign") -> dict[str, set[str]]:
    """Rooms touching by a shared interior wall OR a shared open-plan interface — the union of
    both is "physically connected" for zoning purposes; an open-plan join carries no wall at all,
    so wall-adjacency alone would wrongly read an open-plan public group as disconnected."""
    adj: dict[str, set[str]] = defaultdict(set)
    for w in design.walls:
        if w.boundary_context == "INTERIOR" and len(w.room_ids) >= 2:
            for rid in w.room_ids:
                adj[rid].update(x for x in w.room_ids if x != rid)
    for o in design.open_interfaces:
        for rid in o.room_ids:
            adj[rid].update(x for x in o.room_ids if x != rid)
    return adj


def _zone_contiguous(design: "DemoDesign", kinds: tuple[str, ...]) -> bool | None:
    """Is every room of this zone reachable from any other by passing only through OTHER rooms of
    the SAME zone, or through a HALL/CIRCULATION room — never through a room of a different zone?
    `None` when the zone has fewer than two rooms (nothing to test)."""
    ids = {r.id for r in design.rooms if qm.is_(kinds, r.type)}
    if len(ids) < 2:
        return None
    connectors = {r.id for r in design.rooms if qm.is_(qm.HALL, r.type)}
    adj = _physical_adjacency(design)
    seen: set[str] = set()
    stack = [next(iter(ids))]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(nb for nb in adj[n] if nb not in seen and (nb in ids or nb in connectors))
    return ids <= seen


# --------------------------------------------------------------------------- section A: entrance


def _section_a(design: "DemoDesign", family: str, references: list[dict]) -> SectionFinding:
    entrance = next((d for d in design.doors if d.is_entrance), None)
    entries = [e["id"] for e in _matching_entries(references, family)]
    if entrance is None:
        return SectionFinding("A", "Entrance & Arrival Zone", True, value=None,
                              reference_entries=entries,
                              finding="no entrance door on this plan")
    target = next((r for r in design.rooms if r.id == entrance.b), None)
    role = target.type if target is not None else entrance.b
    is_public = target is not None and qm.is_(qm.PUBLIC + qm.HALL, target.type)
    value = {"opens_into_role": role, "is_public_or_circulation": is_public}
    finding = (f"the entrance opens into {role} ({'public/circulation' if is_public else 'NOT public/circulation'}); "
               f"every {family} reference entry ({', '.join(entries) or 'none in index.json'}) is "
               f"expected to arrive into a hall or the public zone")
    return SectionFinding("A", "Entrance & Arrival Zone", True, value=value,
                          reference_entries=entries, finding=finding)


# --------------------------------------------------------------------------- section B: circulation


def _section_b(design: "DemoDesign", family: str, references: list[dict]) -> SectionFinding:
    metrics = qm.measure_design(design)
    halls = [r for r in design.rooms if qm.is_(qm.HALL, r.type)]
    circulation_area_m2 = sum(r.width_m * r.depth_m for r in halls)
    corridor_length_m = max((max(r.width_m, r.depth_m) for r in halls), default=0.0)
    ratio = metrics.m3_circulation_share
    matching = _matching_entries(references, family)
    entries = [e["id"] for e in matching]
    area_range = _matching_family_area_range_m2(matching)
    plan_area_m2 = design.gross_area_m2
    low, high = CIRCULATION_ENGINEERING_FLOOR_RATIO
    value = {
        "circulation_area_m2": round(circulation_area_m2, 2),
        "circulation_ratio": ratio,
        "corridor_length_m": round(corridor_length_m, 2),
        "plan_area_m2": round(plan_area_m2, 2),
        "within_reference_size_range": (area_range[0] <= plan_area_m2 <= area_range[1])
                                        if area_range is not None else None,
    }
    named = ', '.join(entries) or f"no {family} entries in index.json"
    if area_range is not None:
        size_note = (f"plan is {plan_area_m2:.1f} m², within the {family} reference size range "
                    f"{area_range[0]:.0f}-{area_range[1]:.0f} m² ({named})"
                    if value["within_reference_size_range"] else
                    f"plan is {plan_area_m2:.1f} m², OUTSIDE the {family} reference size range "
                    f"{area_range[0]:.0f}-{area_range[1]:.0f} m² ({named})")
    else:
        size_note = f"no {family} entries in index.json to size-compare against"
    if ratio > high:
        finding = (f"high relative dedicated circulation: {ratio:.1%} of the plan is circulation, "
                   f"above the {low:.0%}-{high:.0%} engineering floor (fixed, not index-derived); {size_note}")
    else:
        finding = (f"circulation share {ratio:.1%} is within the {low:.0%}-{high:.0%} engineering "
                   f"floor (fixed, not index-derived); {size_note}")
    return SectionFinding("B", "Circulation", True, value=value,
                          reference_range=area_range,
                          reference_entries=entries, finding=finding)


# --------------------------------------------------------------------------- section C: zoning


def _section_c(design: "DemoDesign", family: str, references: list[dict]) -> SectionFinding:
    public_ok = _zone_contiguous(design, qm.PUBLIC)
    private_ok = _zone_contiguous(design, PRIVATE)
    service_ok = _zone_contiguous(design, SERVICE)
    value = {"public_contiguous": public_ok, "private_contiguous": private_ok,
             "service_contiguous": service_ok}
    parts = [f"{name} {'contiguous' if ok else ('not contiguous' if ok is False else 'n/a (fewer than 2 rooms)')}"
             for name, ok in (("public", public_ok), ("private", private_ok), ("service", service_ok))]
    entries = [e["id"] for e in _matching_entries(references, family)]
    finding = f"zoning: {'; '.join(parts)}"
    return SectionFinding("C", "Zoning", True, value=value, reference_entries=entries, finding=finding)


# --------------------------------------------------------------------------- section H: exposure


def _section_h(design: "DemoDesign", family: str, references: list[dict]) -> SectionFinding:
    required_ids = {r.id for r in design.rooms if r.type in DAYLIGHT_ROLES}
    windowed_ids = {w.room_id for w in design.windows if w.width_m > 0}
    covered = required_ids & windowed_ids
    ratio = (len(covered) / len(required_ids)) if required_ids else None
    checks = getattr(getattr(design, "validation", None), "checks", {}) or {}
    value = {"windowed_ratio": ratio, "required": len(required_ids), "windowed": len(covered),
             "c8_passed": checks.get("C8")}
    entries = [e["id"] for e in _matching_entries(references, family)]
    if ratio is None:
        finding = "no daylight-required rooms on this plan"
    elif ratio >= 1.0:
        finding = f"all {len(required_ids)} daylight-required rooms have a window (C8 data)"
    else:
        finding = f"only {len(covered)}/{len(required_ids)} daylight-required rooms have a window (C8 data)"
    return SectionFinding("H", "Exposure", True, value=value,
                          reference_range=EXPOSURE_REFERENCE_RATIO_RANGE,
                          reference_entries=entries, finding=finding)


# --------------------------------------------------------------------------- section K: dead space


def _section_k(design: "DemoDesign", family: str, references: list[dict]) -> SectionFinding:
    quality = getattr(design, "quality", None)
    metrics = getattr(quality, "metrics", None)
    dead_space_m2 = metrics.dead_space_m2 if metrics is not None else 0.0
    finding = (f"residual interior area is {dead_space_m2:.2f} m² (C2 already gates every "
              f"delivered plan to zero — a correctness floor, not a reference band)")
    return SectionFinding("K", "Dead Space", True, value=dead_space_m2,
                          reference_range=(0.0, 0.0), reference_entries=[], finding=finding)


# --------------------------------------------------------------------------- section L: consistency


def _section_l(design: "DemoDesign", family: str, references: list[dict]) -> SectionFinding:
    gaps = []
    for r in design.rooms:
        gross = r.width_m * r.depth_m
        if gross <= 0:
            continue
        gaps.append(abs(gross - r.area_m2) / gross)
    if not gaps:
        return SectionFinding("L", "Consistency", True, value=None,
                              finding="no rooms on this plan")
    value = {"max_relative_gap": max(gaps), "median_relative_gap": statistics.median(gaps)}
    finding = (f"declared RoomOut area differs from width×depth by up to {value['max_relative_gap']:.1%} "
              f"(net finished area vs. gross rect, expected by wall thickness — index.json carries no "
              f"per-room geometry, so no reference band is compared here)")
    return SectionFinding("L", "Consistency", True, value=value, finding=finding)


_SECTION_FUNCS = {"A": _section_a, "B": _section_b, "C": _section_c,
                  "H": _section_h, "K": _section_k, "L": _section_l}


def benchmark(design: "DemoDesign", references: list[dict]) -> BenchmarkReport:
    """One `SectionFinding` per full rubric section (A-O). The six this module measures (see the
    module docstring) carry real values off `design`'s realized geometry; the other nine are
    `measured=False` placeholders naming `quality_rubric.md`'s own section at that letter."""
    family = classify_footprint_family(design)
    sections = []
    for code in _SECTION_ORDER:
        if code in _SECTION_FUNCS:
            sections.append(_SECTION_FUNCS[code](design, family, references))
        else:
            sections.append(SectionFinding(code, _NOT_MEASURED_TITLES[code], False,
                                           finding="not_measured"))
    return BenchmarkReport(footprint_family=family, sections=sections)
