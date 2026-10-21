"""R1 (#242) — a real ResPlan plan -> the cells `realize_cells` takes, under the FROZEN rules of
`frozen.py`. Pure geometry; no validator is run here.

Pipeline (one code path for every plan, no per-plan branch):

    ResPlan rooms  ->  drop slivers  ->  snap wall faces onto shared lines  ->  rectilinear tiling
                   ->  rotate (4 ways)  ->  wings (horizontal-slab decomposition of the union)
                   ->  cells per arm
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from app.vertical_slice.geometry_core.model import ProgramRole, Rect, m_to_u
from app.vertical_slice.spec import WetRoomKind

from . import frozen

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in metres, multiples of GRID_M


@dataclass
class ConvertedPlan:
    plan_id: str
    rooms: dict[str, Polygon]                      # snapped, rectilinear, tiling, metres
    roles: dict[str, ProgramRole]
    access: list[tuple[str, str]]
    wet: dict[str, tuple[WetRoomKind, str | None]]     # zone -> (kind, host zone for an ensuite)
    dropped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    footprint_area_m2: float = 0.0
    resplan_footprint_area_m2: float = 0.0
    hole_area_m2: float = 0.0
    non_rectangular_rooms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReprRefusal:
    """The plan cannot even be STATED as a tiling of rectilinear rooms under the frozen rules. Not a
    validator result; reported as such."""
    code: str
    detail: str


@dataclass
class Layout:
    """What `realize.realize` takes: cells and wings in grid units (before the realizer's own 2 m
    site margin), the zone each cell belongs to, and the multi-cell groups."""
    cells: dict[str, Rect]
    wings: tuple[Rect, ...]
    zone_of_cell: dict[str, str]
    groups: dict[str, tuple[str, ...]]
    roles: dict[str, ProgramRole]
    access: list[tuple[str, str]]
    wet: dict[str, tuple[WetRoomKind, str | None]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- snapping

def _cluster_map(values: list[float]) -> dict[float, float]:
    vs = sorted({round(v, 4) for v in values})
    out: dict[float, float] = {}
    cur = [vs[0]]

    def flush() -> None:
        val = round(round(mean(cur) / frozen.GRID_M) * frozen.GRID_M, 4)
        for c in cur:
            out[c] = val

    for v in vs[1:]:
        if v - cur[-1] <= frozen.SNAP_GAP_M and v - cur[0] <= frozen.SNAP_SPAN_M:
            cur.append(v)
        else:
            flush()
            cur = [v]
    flush()
    return out


def _parts(g) -> list[Polygon]:
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g] if g.area > 1e-9 else []
    if not hasattr(g, "geoms"):                    # a line or a point where two shapes only touch
        return []
    return [p for geom in g.geoms for p in _parts(geom)]


def _is_rectilinear(p: Polygon) -> bool:
    for ring in (p.exterior, *p.interiors):
        c = list(ring.coords)
        for a, b in zip(c, c[1:]):
            if abs(a[0] - b[0]) > 1e-6 and abs(a[1] - b[1]) > 1e-6:
                return False
    return True


def convert(plan_id: str, plan_ref: dict) -> ConvertedPlan | ReprRefusal:
    notes: list[str] = []
    rooms_in = sorted(plan_ref["rooms"], key=lambda r: r["id"])
    dropped = [r["id"] for r in rooms_in if r["area_m2"] < frozen.SLIVER_MIN_M2]
    kept = [r for r in rooms_in if r["area_m2"] >= frozen.SLIVER_MIN_M2]
    if not kept:
        return ReprRefusal("REPR-EMPTY", "no room above the sliver threshold")
    unmapped = sorted({r["type"] for r in kept if r["type"] not in frozen.ROLE_MAP})
    if unmapped:
        return ReprRefusal("REPR-ROLE", f"labels with no entry in the role-mapping table: {unmapped}")

    mx = _cluster_map([p[0] for r in kept for p in r["polygon"]])
    my = _cluster_map([p[1] for r in kept for p in r["polygon"]])
    snapped: dict[str, Polygon] = {}
    placed = None
    for r in kept:
        poly = Polygon([(mx[round(x, 4)], my[round(y, 4)]) for x, y in r["polygon"]])
        if not poly.is_valid:
            poly = poly.buffer(0)
        poly = poly.simplify(0)
        if placed is not None and not placed.is_empty:
            lost = poly.intersection(placed).area
            if lost > 1e-9:
                notes.append(f"{r['id']}: {lost:.2f} m2 overlapped an earlier room and was removed")
                poly = poly.difference(placed)
        parts = _parts(poly)
        if not parts:
            dropped.append(r["id"])
            notes.append(f"{r['id']}: nothing left after snapping")
            continue
        if len(parts) > 1:
            parts.sort(key=lambda g: -g.area)
            notes.append(f"{r['id']}: fell into {len(parts)} parts, kept the largest "
                         f"({parts[0].area:.2f} m2), discarded {sum(g.area for g in parts[1:]):.2f} m2")
        poly = parts[0].simplify(0)
        if poly.area < frozen.SLIVER_MIN_M2:
            dropped.append(r["id"])
            notes.append(f"{r['id']}: {poly.area:.2f} m2 after snapping, dropped as a sliver")
            continue
        if not _is_rectilinear(poly):
            return ReprRefusal("REPR-RECTILINEAR", f"{r['id']} has a non-axis-parallel edge after snapping")
        snapped[r["id"]] = poly
        placed = poly if placed is None else unary_union([placed, poly])
    if not snapped:
        return ReprRefusal("REPR-EMPTY", "no room left after snapping")

    roles = {rid: frozen.ROLE_MAP[next(r["type"] for r in kept if r["id"] == rid)] for rid in snapped}
    bedrooms = sorted((r for r in kept if r["id"] in snapped and r["type"] == "BEDROOM"),
                      key=lambda r: (-r["area_m2"], r["id"]))
    if len(bedrooms) >= frozen.MASTER_RULE_MIN_BEDROOMS:
        roles[bedrooms[0]["id"]] = ProgramRole.MASTER_BEDROOM

    access: list[tuple[str, str]] = []
    for e in plan_ref["access_edges"]:
        a, b = e["room_a"], e["room_b"]
        if a in snapped and b in snapped and a != b:
            pair = tuple(sorted((a, b)))
            if pair not in access:
                access.append(pair)

    wet: dict[str, tuple[WetRoomKind, str | None]] = {}
    bed_roles = {ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM}
    for rid, role in sorted(roles.items()):
        if role not in (ProgramRole.BATHROOM, ProgramRole.TOILET):
            continue
        nbrs = sorted({b if a == rid else a for a, b in access if rid in (a, b)})
        if role is ProgramRole.TOILET:
            wet[rid] = (WetRoomKind.GUEST_WC, None)
        elif len(nbrs) == 1 and roles[nbrs[0]] in bed_roles:
            wet[rid] = (WetRoomKind.ENSUITE, nbrs[0])
        else:
            wet[rid] = (WetRoomKind.SHARED_BATHROOM, None)

    union = unary_union(list(snapped.values()))
    hole_area = sum(Polygon(i).area for p in _parts(union) for i in p.interiors)
    nonrect = [rid for rid, p in snapped.items() if abs(p.area - p.envelope.area) > 1e-6]
    return ConvertedPlan(
        plan_id=plan_id, rooms=snapped, roles=roles, access=access, wet=wet, dropped=sorted(set(dropped)),
        notes=notes, footprint_area_m2=round(union.area, 2),
        resplan_footprint_area_m2=float(plan_ref["derived"]["footprint_area_m2"]),
        hole_area_m2=round(hole_area, 2), non_rectangular_rooms=sorted(nonrect))


# --------------------------------------------------------------------------- rotation

def rotate(rooms: dict[str, Polygon], deg: int) -> dict[str, Polygon]:
    """Exact quarter-turn rotation, translated so the union's minimum corner is the origin. The
    realizer's street is its y-min wall."""
    fn = {0: lambda x, y: (x, y), 90: lambda x, y: (-y, x),
          180: lambda x, y: (-x, -y), 270: lambda x, y: (y, -x)}[deg]
    rot = {rid: Polygon([fn(x, y) for x, y in p.exterior.coords]) for rid, p in rooms.items()}
    minx = min(p.bounds[0] for p in rot.values())
    miny = min(p.bounds[1] for p in rot.values())

    def shift(p: Polygon) -> Polygon:
        return Polygon([(round(x - minx, 4), round(y - miny, 4)) for x, y in p.exterior.coords])

    return {rid: shift(p) for rid, p in rot.items()}


# --------------------------------------------------------------------------- slab decomposition

def _grid(v: float) -> float:
    return round(round(v / frozen.GRID_M) * frozen.GRID_M, 4)


def slab_rects(geom) -> list[Box]:
    """A rectilinear region (holes allowed) as a list of non-overlapping rectangles: cut at every
    y where the horizontal profile can change, then merge vertically adjacent slabs with the same
    x-extent. A rectangle yields itself."""
    parts = _parts(geom)
    if not parts:
        return []
    ys = sorted({round(y, 4) for p in parts for ring in (p.exterior, *p.interiors) for _, y in ring.coords})
    minx, _, maxx, _ = geom.bounds
    raw: list[Box] = []
    for y0, y1 in zip(ys, ys[1:]):
        inter = geom.intersection(LineString([(minx - 1.0, (y0 + y1) / 2), (maxx + 1.0, (y0 + y1) / 2)]))
        segs = [inter] if inter.geom_type == "LineString" else (
            [g for g in inter.geoms if g.geom_type == "LineString"] if hasattr(inter, "geoms") else [])
        for s in segs:
            xs = sorted(c[0] for c in s.coords)
            if xs[-1] - xs[0] > 1e-6:
                raw.append((_grid(xs[0]), _grid(y0), _grid(xs[-1]), _grid(y1)))
    raw.sort(key=lambda b: (b[0], b[2], b[1]))
    merged: list[list[float]] = []
    for x0, y0, x1, y1 in raw:
        if merged and merged[-1][0] == x0 and merged[-1][2] == x1 and abs(merged[-1][3] - y0) < 1e-6:
            merged[-1][3] = y1
        else:
            merged.append([x0, y0, x1, y1])
    return [tuple(m) for m in sorted(merged, key=lambda b: (b[1], b[0]))]  # type: ignore[misc]


def largest_inscribed(poly: Polygon) -> Box | None:
    """The largest-area axis-aligned rectangle inside a rectilinear polygon (ties: smallest y0, x0).
    Brute force over the polygon's own coordinate lines."""
    xs = sorted({round(x, 4) for x, _ in poly.exterior.coords})
    ys = sorted({round(y, 4) for _, y in poly.exterior.coords})
    best: tuple[float, Box] | None = None
    for i, x0 in enumerate(xs):
        for x1 in xs[i + 1:]:
            for j, y0 in enumerate(ys):
                for y1 in ys[j + 1:]:
                    area = (x1 - x0) * (y1 - y0)
                    if best is not None and (area < best[0] - 1e-9 or
                                             (abs(area - best[0]) <= 1e-9 and (y0, x0) >= (best[1][1], best[1][0]))):
                        continue
                    if poly.buffer(1e-7).covers(box(x0, y0, x1, y1)):
                        best = (area, (x0, y0, x1, y1))
    return best[1] if best else None


# --------------------------------------------------------------------------- wings and cells

def wings_of(rooms: dict[str, Polygon]) -> list[Box]:
    return slab_rects(unary_union(list(rooms.values())))


def _split(cells: list[tuple[str, Box]], idx: int, axis: str, at: float) -> None:
    zone, (x0, y0, x1, y1) = cells[idx]
    a, b = ((x0, y0, at, y1), (at, y0, x1, y1)) if axis == "x" else ((x0, y0, x1, at), (x0, at, x1, y1))
    cells[idx] = (zone, a)
    cells.append((zone, b))


def _refine_wing_seams(cells: list[tuple[str, Box]], wings: list[Box]) -> None:
    """Split cells that sit on a wing boundary at the points where the facing wing starts/stops, so
    every cell side on a seam is abutted by the other wing along its WHOLE length or not at all
    (C22 rejects a partial seam). Geometry does not move; only the cell decomposition does."""
    for a in wings:
        for b in wings:
            if a is b or abs(a[3] - b[1]) > 1e-6:
                continue
            lo, hi = max(a[0], b[0]), min(a[2], b[2])
            if hi - lo <= 1e-6:
                continue
            for point in (lo, hi):
                for i in range(len(cells)):
                    _, (x0, y0, x1, y1) = cells[i]
                    on_seam = (abs(y1 - a[3]) < 1e-6 and x0 >= a[0] - 1e-6 and x1 <= a[2] + 1e-6) or \
                              (abs(y0 - b[1]) < 1e-6 and x0 >= b[0] - 1e-6 and x1 <= b[2] + 1e-6)
                    if on_seam and x0 + 1e-6 < point < x1 - 1e-6:
                        _split(cells, i, "x", point)


def _refine_uniform_sides(cells: list[tuple[str, Box]]) -> None:
    """Diagnostic arm only: split until every cell side is covered by its neighbours in a way that
    never changes along the side (the realizer gives a side ONE wall type)."""
    changed = True
    while changed:
        changed = False
        for i in range(len(cells)):
            _, (x0, y0, x1, y1) = cells[i]
            for j, (_, (u0, v0, u1, v1)) in enumerate(cells):
                if j == i:
                    continue
                # a neighbour across the right/left side bounds the side in y; across the bottom/top in x
                if abs(u0 - x1) < 1e-6 or abs(u1 - x0) < 1e-6:
                    if min(y1, v1) - max(y0, v0) > 1e-6:
                        for point in (v0, v1):
                            if y0 + 1e-6 < point < y1 - 1e-6:
                                _split(cells, i, "y", point)
                                changed = True
                                break
                elif abs(v0 - y1) < 1e-6 or abs(v1 - y0) < 1e-6:
                    if min(x1, u1) - max(x0, u0) > 1e-6:
                        for point in (u0, u1):
                            if x0 + 1e-6 < point < x1 - 1e-6:
                                _split(cells, i, "x", point)
                                changed = True
                                break
                if changed:
                    break
            if changed:
                break


def _units(b: Box) -> Rect:
    x0, y0, x1, y1 = (m_to_u(v) for v in b)
    return Rect(x0, y0, x1 - x0, y1 - y0)


def build_layout(conv: ConvertedPlan, rooms: dict[str, Polygon], arm: str) -> Layout | ReprRefusal:
    """`rooms` is the rotated tiling. Arm 1: one rectangle per room (the room itself when it is
    one, else its largest inscribed rectangle inside one wing). Arm 2 / 2R: every room in full, as
    the cells of its slab decomposition per wing — more than one cell makes a same-zone group."""
    wings = wings_of(rooms)
    notes: list[str] = []
    per_zone: dict[str, list[Box]] = {}
    if arm == frozen.ARM_1:
        for rid, poly in rooms.items():
            best: tuple[float, Box] | None = None
            for w in wings:
                piece = poly.intersection(box(*w))
                for part in _parts(piece):
                    r = largest_inscribed(part)
                    if r is not None:
                        a = (r[2] - r[0]) * (r[3] - r[1])
                        if best is None or a > best[0] + 1e-9:
                            best = (a, r)
            if best is None:
                return ReprRefusal("REPR-NO-RECT", f"{rid} contains no rectangle")
            per_zone[rid] = [best[1]]
            if abs(best[0] - poly.area) > 1e-6:
                notes.append(f"{rid}: single rectangle {best[0]:.2f} of {poly.area:.2f} m2")
        flat = [(z, b) for z, bs in per_zone.items() for b in bs]
    else:
        flat = []
        for rid, poly in rooms.items():
            for w in wings:
                for part in _parts(poly.intersection(box(*w))):
                    for b in slab_rects(part):
                        flat.append((rid, b))
        _refine_wing_seams(flat, wings)
        if arm == frozen.ARM_2R:
            _refine_uniform_sides(flat)
    cells: dict[str, Rect] = {}
    zone_of_cell: dict[str, str] = {}
    groups: dict[str, tuple[str, ...]] = {}
    by_zone: dict[str, list[Box]] = {}
    for z, b in flat:
        by_zone.setdefault(z, []).append(b)
    for z in rooms:
        bs = sorted(by_zone.get(z, []), key=lambda b: (b[1], b[0]))
        if len(bs) == 1:
            cells[z] = _units(bs[0])
            zone_of_cell[z] = z
        else:
            ids = tuple(f"{z}__c{i}" for i in range(len(bs)))
            for cid, b in zip(ids, bs):
                cells[cid] = _units(b)
                zone_of_cell[cid] = z
            groups[z] = ids
    return Layout(cells=cells, wings=tuple(_units(w) for w in wings), zone_of_cell=zone_of_cell,
                  groups=groups, roles=dict(conv.roles), access=list(conv.access), wet=dict(conv.wet),
                  notes=notes)
